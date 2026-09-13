"""Console orchestration — per-session FIFO queue, watchdog wiring, and the
startup recovery sweep. Stateless wrapper around ``console_store`` + the
streaming helpers in ``claude_runner``.

The two public concerns this module owns:

1. **Concurrency.** ``claude -p --resume <id>`` mutates the on-disk
   Claude session file. Two concurrent runs against the same id corrupt
   that file, so we serialize asks per session. Across sessions we run
   in parallel — different ``claude_session_id`` values mean different
   on-disk session files.

2. **Recovery.** Subprocesses survive across HTTP handler returns but
   not across process restarts. ``recover()`` (called from the FastAPI
   startup hook) scans every session and writes a synthesized
   ``"Interrupted by server restart"`` assistant turn for any user
   record that lost its in-flight partner.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, console_store, files_store, job_progress, research_store, storage

logger = logging.getLogger(__name__)


# Two analyst personas — the runtime picks one per session based on the
# target company's company_type. See docs/public-company-trader-view.md §5.
SKILLS_DIR = Path(__file__).parent / "skills"
PRIVATE_SKILL_PATH = SKILLS_DIR / "bsh_company_console.md"
PUBLIC_SKILL_PATH = SKILLS_DIR / "bsh_company_console_public.md"
SKILL_PATH = PRIVATE_SKILL_PATH  # back-compat alias; some call sites still import this
IOS_ASK_SKILL_PATH = SKILLS_DIR / "bsh_copilot_ask_ios.md"

# Session kinds that use the fast Ask profile (not Deep Console).
_QUICK_ASK_KINDS = frozenset({"copilot_quick", "copilot_quick_ios"})


def _env_strip(name: str, default: str) -> str:
    value = (os.environ.get(name) or default).strip()
    return value or default


def quick_ask_cli_options(session_kind: str | None) -> dict[str, Any]:
    """CLI overrides for Co-Pilot quick / iOS Ask. Deep Console returns {}.

    Defaults favor quality-at-speed: sonnet + low effort. Tools-off is the
    main latency lever (avoids Read/WebSearch round-trips); set
    ``BSH_COPILOT_QUICK_MODEL=haiku`` to reclaim Haiku's cheaper/faster
    TTFT. iOS disables tools entirely; web quick keeps Read so hydrated
    dossier files still work.
    """
    kind = str(session_kind or "")
    if kind not in _QUICK_ASK_KINDS:
        return {}
    model = _env_strip("BSH_COPILOT_QUICK_MODEL", "sonnet")
    effort = _env_strip("BSH_COPILOT_QUICK_EFFORT", "low")
    opts: dict[str, Any] = {
        "model": model,
        "effort": effort,
        "exclude_dynamic_system_prompt": True,
    }
    if kind == "copilot_quick_ios":
        # Unset → disable tools. Set to e.g. "Read" to re-enable.
        if "BSH_COPILOT_IOS_TOOLS" in os.environ:
            opts["tools"] = os.environ.get("BSH_COPILOT_IOS_TOOLS") or ""
        else:
            opts["tools"] = ""
        opts["lean_language_directive"] = True
        if IOS_ASK_SKILL_PATH.exists():
            opts["skill_path"] = IOS_ASK_SKILL_PATH
    else:
        if "BSH_COPILOT_QUICK_TOOLS" in os.environ:
            opts["tools"] = os.environ.get("BSH_COPILOT_QUICK_TOOLS") or ""
        else:
            opts["tools"] = "Read"
    return opts


def _resolve_skill_path(company_id: str) -> Path:
    """Pick the right --append-system-prompt file given a company id.

    Public companies get the trader-analyst persona; private (and all
    fallbacks, including not-found) get the default analyst persona.
    """
    company = storage.get_company(company_id) if company_id else None
    if not company:
        return PRIVATE_SKILL_PATH
    company_type = company.get("company_type") or storage.infer_company_type(company)
    return PUBLIC_SKILL_PATH if company_type == "public" else PRIVATE_SKILL_PATH


# ---- Cancel-event registry ---------------------------------------------

# (company_id, session_id, turn_id) -> threading.Event
_CANCEL_EVENTS: dict[tuple[str, str, str], threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


def _register_cancel(
    company_id: str, session_id: str, turn_id: str
) -> threading.Event:
    event = threading.Event()
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[(company_id, session_id, turn_id)] = event
    return event


def _unregister_cancel(company_id: str, session_id: str, turn_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop((company_id, session_id, turn_id), None)


def cancel_turn(company_id: str, session_id: str, turn_id: str) -> bool:
    """Signal the in-flight turn's subprocess to interrupt (SIGINT). Returns
    True if a cancellable turn was found, False if the turn doesn't exist
    or is already complete.
    """
    with _CANCEL_LOCK:
        event = _CANCEL_EVENTS.get((company_id, session_id, turn_id))
    if event is None:
        return False
    event.set()
    return True


# ---- Per-session dispatcher --------------------------------------------


class _SessionDispatcher:
    """A queue + worker thread for one session. ``submit()`` always
    succeeds and returns the queue position (0 = head, running next).

    Idle workers exit after ``IDLE_EXIT_S``; a new submit lazily spawns
    a fresh worker. This keeps the thread count bounded by *active*
    sessions, not historical ones.
    """

    IDLE_EXIT_S = 120.0

    def __init__(self, company_id: str, session_id: str):
        self.company_id = company_id
        self.session_id = session_id
        self.q: queue.Queue = queue.Queue()
        self.pending_ids: list[str] = []
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def submit(
        self,
        turn_id: str,
        prompt: str,
        attachments: list[str],
        runtime_prompt: str | None = None,
    ) -> int:
        with self.lock:
            self.pending_ids.append(turn_id)
            position = len(self.pending_ids) - 1
        self.q.put((turn_id, prompt, attachments, runtime_prompt))
        self._ensure_worker()
        return position

    def position(self, turn_id: str) -> int | None:
        with self.lock:
            try:
                return self.pending_ids.index(turn_id)
            except ValueError:
                return None

    def _ensure_worker(self) -> None:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(
                target=self._worker,
                name=f"console-{self.session_id[:8]}",
                daemon=True,
            )
            self.thread.start()

    def _worker(self) -> None:
        while True:
            try:
                turn_id, prompt, attachments, runtime_prompt = self.q.get(
                    timeout=self.IDLE_EXIT_S
                )
            except queue.Empty:
                return
            try:
                self._run_one(turn_id, prompt, attachments, runtime_prompt)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "console worker crashed for sid=%s turn=%s",
                    self.session_id, turn_id,
                )
                _write_error_assistant_turn(
                    self.company_id, self.session_id, turn_id,
                    error="Worker crashed unexpectedly",
                )
            finally:
                with self.lock:
                    if self.pending_ids and self.pending_ids[0] == turn_id:
                        self.pending_ids.pop(0)

    def _run_one(
        self,
        turn_id: str,
        prompt: str,
        attachments: list[str],
        runtime_prompt: str | None = None,
    ) -> None:
        meta = console_store.load_meta(self.company_id, self.session_id)
        if meta is None:
            _write_error_assistant_turn(
                self.company_id, self.session_id, turn_id,
                error="Session metadata not found",
            )
            return
        if meta.get("status") != "active":
            _write_error_assistant_turn(
                self.company_id, self.session_id, turn_id,
                error="Session is not active",
            )
            return

        cancel_event = _register_cancel(
            self.company_id, self.session_id, turn_id
        )

        progress_path = console_store.ask_progress_path(
            self.company_id, self.session_id, turn_id
        )
        progress = job_progress.ProgressLog(progress_path)
        progress.emit(
            "job_init",
            kind="console_ask",
            title=f"Q&A: {prompt[:40]}",
            session_id=self.session_id,
            turn_id=turn_id,
        )

        # Use the skill path recorded at session-create time so re-typing
        # the company mid-session doesn't change the analyst persona
        # mid-conversation. Falls back to PRIVATE for older sessions
        # that predate Phase 4 and never wrote skill_path to disk.
        recorded_skill = meta.get("skill_path")
        skill_path = Path(recorded_skill) if recorded_skill else PRIVATE_SKILL_PATH
        if not skill_path.exists():
            skill_path = PRIVATE_SKILL_PATH

        started = time.monotonic()
        ask_prompt = runtime_prompt or prompt
        # Quick Co-Pilot sessions skip hydrate, so Claude never saw
        # ``--session-id``. The first ask must create the session; later
        # asks resume it. Hydrate-error sessions get the same bootstrap.
        hydration = str(meta.get("hydration_status") or "")
        bootstrap_session = (
            not bool(meta.get("claude_session_ready"))
            and hydration in {"skipped", "error", ""}
        )
        ask_opts = quick_ask_cli_options(meta.get("session_kind"))
        if ask_opts.get("skill_path") is not None:
            skill_path = ask_opts.pop("skill_path")
        try:
            outcome = claude_runner.run_console_ask(
                claude_session_id=meta["claude_session_id"],
                work_dir=console_store.workdir(self.company_id, self.session_id),
                user_prompt=ask_prompt,
                skill_path=skill_path,
                progress=progress,
                attachments=attachments,
                output_language=meta.get("output_language"),
                cancel_event=cancel_event,
                bootstrap_session=bootstrap_session,
                **ask_opts,
            )
        finally:
            _unregister_cancel(self.company_id, self.session_id, turn_id)

        duration_ms = int((time.monotonic() - started) * 1000)

        record: dict[str, Any] = {
            "ts": _now(),
            "id": turn_id,
            "role": "assistant",
            "text": outcome.get("text") or "",
            "duration_ms": duration_ms,
            "cost_usd": outcome.get("cost_usd"),
            "tokens": outcome.get("usage") or {},
            "subtype": outcome.get("subtype")
                or ("success" if outcome.get("ok") else "error"),
        }
        if not outcome.get("ok"):
            record["error"] = outcome.get("error") or "Ask failed"
            if outcome.get("interrupt_reason"):
                record["interrupt_reason"] = outcome["interrupt_reason"]
            # Persist a visible fallback so UIs that only render ``text``
            # still show why the turn failed (blank replies look broken).
            if not record["text"]:
                record["text"] = record["error"]

        console_store.append_turn(self.company_id, self.session_id, record)
        if outcome.get("usage") and outcome.get("cost_usd") is not None:
            console_store.update_tokens(
                self.company_id, self.session_id,
                usage=outcome["usage"],
                cost_usd=outcome.get("cost_usd") or 0.0,
            )

        # Auto-rename after the first successful turn lands. Cheap one-shot
        # Claude call; failure falls back to the timestamp title silently.
        if outcome.get("ok"):
            if bootstrap_session:
                console_store.update_meta(
                    self.company_id,
                    self.session_id,
                    claude_session_ready=True,
                )
            self._maybe_auto_rename(prompt, outcome.get("text") or "")
            try:
                from . import push_notify

                preview = (outcome.get("text") or "").strip().replace("\n", " ")
                if len(preview) > 120:
                    preview = preview[:117] + "…"
                push_notify.notify(
                    "ask",
                    "Ask ready",
                    preview or f"Reply for {self.company_id}",
                    data={
                        "company_id": self.company_id,
                        "session_id": self.session_id,
                        "turn_id": turn_id,
                        "deep_link": f"bshresearch://company/{self.company_id}",
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("ask push notify failed for %s", self.company_id)

    def _maybe_auto_rename(self, user_prompt: str, assistant_text: str) -> None:
        meta = console_store.load_meta(self.company_id, self.session_id)
        if meta is None:
            return
        if not (meta.get("title") or "").startswith("Session ·"):
            return  # User or a prior auto-rename already set a title.
        # Only fire when we have exactly the first user/assistant pair.
        turns = console_store.read_turns(self.company_id, self.session_id)
        assistants = [t for t in turns if t.get("role") == "assistant"]
        if len(assistants) != 1:
            return
        company_id = self.company_id
        session_id = self.session_id

        def _worker() -> None:
            try:
                title = claude_runner.run_console_title(
                    user_prompt=user_prompt,
                    assistant_text=assistant_text,
                )
            except Exception:  # noqa: BLE001
                title = None
            if title:
                console_store.update_meta(
                    company_id, session_id, title=title,
                )

        threading.Thread(
            target=_worker,
            name=f"console-title-{self.session_id[:8]}",
            daemon=True,
        ).start()


# ---- Dispatcher registry -----------------------------------------------

_DISPATCHERS: dict[tuple[str, str], _SessionDispatcher] = {}
_DISPATCHERS_LOCK = threading.Lock()


def _dispatcher(company_id: str, session_id: str) -> _SessionDispatcher:
    key = (company_id, session_id)
    with _DISPATCHERS_LOCK:
        d = _DISPATCHERS.get(key)
        if d is None:
            d = _SessionDispatcher(company_id, session_id)
            _DISPATCHERS[key] = d
        return d


def queue_position(
    company_id: str, session_id: str, turn_id: str
) -> int | None:
    with _DISPATCHERS_LOCK:
        d = _DISPATCHERS.get((company_id, session_id))
    if d is None:
        return None
    return d.position(turn_id)


# ---- Public surface (used by api.py) -----------------------------------


def create_session(
    *,
    company_id: str,
    include_background_docs: bool,
    include_library_docs: bool,
    output_language: str = console_store.DEFAULT_OUTPUT_LANGUAGE,
    title: str | None = None,
    session_kind: str | None = None,
    skill_path: Path | None = None,
    research_file_ids: list[str] | None = None,
    skip_hydrate: bool = False,
) -> dict:
    """Resolve included files, lay out the on-disk session, and kick off
    hydration in a background thread. Returns the persisted meta plus the
    stream URL for the hydration job.
    """
    included: list[dict] = []
    sources: list[Path] = []

    if include_background_docs:
        allowed = {str(fid) for fid in (research_file_ids or [])}
        for entry in research_store.list_files(company_id):
            if research_file_ids and str(entry["id"]) not in allowed:
                continue
            resolved = research_store.get_file(company_id, entry["id"])
            if resolved is None:
                continue
            _, path = resolved
            included.append({
                "id": entry["id"], "kind": "research",
                "filename": entry["filename"],
            })
            sources.append(path)
    if include_library_docs:
        for entry in files_store.list_files(company_id):
            resolved = files_store.get_file(company_id, entry["id"])
            if resolved is None:
                continue
            _, path = resolved
            included.append({
                "id": entry["id"], "kind": "library",
                "filename": entry["filename"],
            })
            sources.append(path)

    meta = console_store.create_session(
        company_id=company_id,
        include_background_docs=include_background_docs,
        include_library_docs=include_library_docs,
        included_files=included,
        output_language=output_language,
        title=title,
    )
    # Lock in the right analyst persona for this session — recorded so
    # the choice is stable across the session's lifetime even if the
    # underlying company gets re-typed later.
    resolved_skill = skill_path or _resolve_skill_path(company_id)
    patch: dict[str, Any] = {
        "hydration_status": "in_progress",
        "skill_path": str(resolved_skill),
    }
    if session_kind:
        patch["session_kind"] = session_kind
    meta = console_store.update_meta(
        company_id, meta["id"],
        **patch,
    ) or meta

    console_store.stage_docs(
        company_id=company_id, session_id=meta["id"], source_paths=sources,
    )

    if skip_hydrate:
        return console_store.update_meta(
            company_id,
            meta["id"],
            hydration_status="skipped",
        ) or meta

    progress_path = console_store.hydrate_progress_path(company_id, meta["id"])
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init", kind="console_hydrate",
        title="Hydrating console",
        session_id=meta["id"],
        file_count=len(included),
    )

    def _worker() -> None:
        try:
            outcome = claude_runner.run_console_hydrate(
                claude_session_id=meta["claude_session_id"],
                work_dir=console_store.workdir(company_id, meta["id"]),
                file_list=sources,
                skill_path=resolved_skill,
                progress=progress,
                output_language=output_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("hydrate crashed for sid=%s", meta["id"])
            console_store.update_meta(
                company_id, meta["id"],
                hydration_status="error",
                hydration_error=f"{type(exc).__name__}: {exc}",
            )
            return
        new_status = "done" if outcome.get("ok") else "error"
        patch = {"hydration_status": new_status}
        if not outcome.get("ok"):
            patch["hydration_error"] = outcome.get("error")
        console_store.update_meta(company_id, meta["id"], **patch)
        if outcome.get("usage") and outcome.get("cost_usd") is not None:
            console_store.update_tokens(
                company_id, meta["id"],
                usage=outcome["usage"],
                cost_usd=outcome.get("cost_usd") or 0.0,
            )

    threading.Thread(
        target=_worker,
        name=f"console-hydrate-{meta['id'][:8]}",
        daemon=True,
    ).start()

    return meta


def hydrate_existing_session(
    *,
    company_id: str,
    session_id: str,
    research_file_ids: list[str] | None = None,
    output_language: str = console_store.DEFAULT_OUTPUT_LANGUAGE,
) -> dict:
    """Stage scoped research files and run hydration for an existing session."""
    meta = console_store.load_meta(company_id, session_id)
    if meta is None:
        raise ValueError("session_not_found")
    status = str(meta.get("hydration_status") or "")
    if status in {"in_progress", "done"}:
        return meta

    included: list[dict] = []
    sources: list[Path] = []
    allowed = {str(fid) for fid in (research_file_ids or [])}
    for entry in research_store.list_files(company_id):
        if research_file_ids and str(entry["id"]) not in allowed:
            continue
        resolved = research_store.get_file(company_id, entry["id"])
        if resolved is None:
            continue
        _, path = resolved
        included.append({
            "id": entry["id"],
            "kind": "research",
            "filename": entry["filename"],
        })
        sources.append(path)

    if not sources:
        return console_store.update_meta(
            company_id,
            session_id,
            hydration_status="skipped",
        ) or meta

    console_store.update_meta(
        company_id,
        session_id,
        include_background_docs=True,
        included_files=included,
    )
    console_store.stage_docs(
        company_id=company_id,
        session_id=session_id,
        source_paths=sources,
    )

    resolved_skill = Path(str(meta.get("skill_path") or _resolve_skill_path(company_id)))
    meta = console_store.update_meta(
        company_id,
        session_id,
        hydration_status="in_progress",
        skill_path=str(resolved_skill),
    ) or meta

    progress_path = console_store.hydrate_progress_path(company_id, session_id)
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="console_hydrate",
        title="Hydrating console",
        session_id=session_id,
        file_count=len(included),
    )

    def _worker() -> None:
        try:
            outcome = claude_runner.run_console_hydrate(
                claude_session_id=meta["claude_session_id"],
                work_dir=console_store.workdir(company_id, session_id),
                file_list=sources,
                skill_path=resolved_skill,
                progress=progress,
                output_language=output_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("hydrate crashed for sid=%s", session_id)
            console_store.update_meta(
                company_id,
                session_id,
                hydration_status="error",
                hydration_error=f"{type(exc).__name__}: {exc}",
            )
            return
        new_status = "done" if outcome.get("ok") else "error"
        patch = {"hydration_status": new_status}
        if not outcome.get("ok"):
            patch["hydration_error"] = outcome.get("error")
        console_store.update_meta(company_id, session_id, **patch)
        if outcome.get("usage") and outcome.get("cost_usd") is not None:
            console_store.update_tokens(
                company_id,
                session_id,
                usage=outcome["usage"],
                cost_usd=outcome.get("cost_usd") or 0.0,
            )

    threading.Thread(
        target=_worker,
        name=f"console-hydrate-{session_id[:8]}",
        daemon=True,
    ).start()
    return meta


def submit_ask(
    *,
    company_id: str,
    session_id: str,
    prompt: str,
    attachments: list[str],
    runtime_prompt: str | None = None,
) -> dict:
    """Append a user turn and enqueue the ask. Returns ``{turn_id,
    queue_position}``. Returns 0 for position if running immediately.

    Raises ``ValueError`` if the session is not active.
    """
    meta = console_store.load_meta(company_id, session_id)
    if meta is None:
        raise ValueError("session_not_found")
    if meta.get("status") != "active":
        raise ValueError("session_archived")

    turn_id = console_store.new_turn_id()
    record = {
        "ts": _now(),
        "id": turn_id,
        "role": "user",
        "text": prompt,
        "attachments": [
            {"id": _strip_ext(name), "name": name} for name in attachments
        ],
    }
    if runtime_prompt and runtime_prompt != prompt:
        record["runtime_prompt"] = runtime_prompt
    console_store.append_turn(company_id, session_id, record)

    # Touch the progress file immediately so SSE clients don't hit
    # "No progress for this job" while this turn waits behind another ask.
    # Leave it empty — the worker truncates and writes real events.
    progress_path = console_store.ask_progress_path(company_id, session_id, turn_id)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.touch()

    d = _dispatcher(company_id, session_id)
    position = d.submit(turn_id, prompt, attachments, runtime_prompt)
    return {"turn_id": turn_id, "queue_position": position}


def archive_session(*, company_id: str, session_id: str) -> dict | None:
    """Mark archived and kick off a background summarize."""
    meta = console_store.archive_session(company_id, session_id)
    if meta is None:
        return None

    progress = job_progress.ProgressLog(
        console_store.summary_progress_path(company_id, session_id)
    )

    def _worker() -> None:
        turns = console_store.read_turns(company_id, session_id)
        try:
            result = claude_runner.run_console_summary(turns=turns, progress=progress)
        except Exception as exc:  # noqa: BLE001
            logger.exception("summary crashed for sid=%s", session_id)
            result = {"error": f"{type(exc).__name__}: {exc}"}
        if "error" in result and not result.get("headline"):
            console_store.update_meta(
                company_id, session_id,
                summary_error=result.get("error"),
            )
            return
        summary = {
            "headline": result.get("headline"),
            "bullets": result.get("bullets") or [],
            "generated_at": _now(),
        }
        console_store.update_meta(company_id, session_id, summary=summary)

    threading.Thread(
        target=_worker,
        name=f"console-summary-{session_id[:8]}",
        daemon=True,
    ).start()
    return meta


# ---- Startup recovery sweep --------------------------------------------


def recover() -> None:
    """Scan every session on disk; synthesize an error assistant turn for
    any user turn that lost its in-flight partner across a restart. Also
    flips any ``hydration_status == "in_progress"`` to ``"error"`` for the
    same reason.

    Idempotent — re-running has no effect after the first pass.
    """
    root = console_store.CONSOLES_ROOT
    if not root.exists():
        return
    for company in root.iterdir():
        if not company.is_dir():
            continue
        sessions = company / "sessions"
        if not sessions.exists():
            continue
        for sdir in sessions.iterdir():
            if not sdir.is_dir():
                continue
            company_id = company.name
            session_id = sdir.name
            try:
                meta = console_store.load_meta(company_id, session_id)
            except ValueError:
                continue
            if meta is None:
                continue

            if meta.get("hydration_status") == "in_progress":
                console_store.update_meta(
                    company_id, session_id,
                    hydration_status="error",
                    hydration_error="Interrupted by server restart",
                )

            try:
                turns = console_store.read_turns(company_id, session_id)
            except OSError:
                continue
            # Match users to assistants by turn id.
            assistant_ids = {
                t.get("id") for t in turns if t.get("role") == "assistant"
            }
            orphaned: list[str] = [
                t.get("id") for t in turns
                if t.get("role") == "user" and t.get("id") not in assistant_ids
                and t.get("id")
            ]
            for tid in orphaned:
                _write_error_assistant_turn(
                    company_id, session_id, tid,
                    error="Interrupted by server restart",
                )


# ---- Helpers -----------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_ext(filename: str) -> str:
    """Map an attachment ``stored_name`` like ``<sha>.png`` back to its
    sha id. Used to populate the user-turn record alongside ``name``.
    """
    if "." in filename:
        return filename.rsplit(".", 1)[0]
    return filename


def _write_error_assistant_turn(
    company_id: str, session_id: str, turn_id: str, *, error: str
) -> None:
    """Append a synthesized assistant turn marking a user turn as failed.

    Called from the recovery sweep and from the worker's crash handler.
    """
    # Avoid double-writing if some assistant record already exists.
    for t in console_store.read_turns(company_id, session_id):
        if t.get("id") == turn_id and t.get("role") == "assistant":
            return
    console_store.append_turn(
        company_id, session_id,
        {
            "ts": _now(),
            "id": turn_id,
            "role": "assistant",
            "text": "",
            "subtype": "error",
            "error": error,
        },
    )


__all__ = [
    "SKILL_PATH",
    "PRIVATE_SKILL_PATH",
    "PUBLIC_SKILL_PATH",
    "create_session",
    "submit_ask",
    "archive_session",
    "cancel_turn",
    "queue_position",
    "recover",
]
