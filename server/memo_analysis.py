"""Background worker for investment-memo generation.

The default worker path runs a fast multi-subprocess Claude pipeline:
independent analysis passes fan out in parallel, one synthesis pass writes the
English source package, and one Chinese-completion pass writes the final
structured memo package. Python then invokes the tracked DOCX renderer and
finalizes the run manifest. The legacy one-Claude skill run is still available
with ``BSH_MEMO_FAST_PIPELINE=0``. This worker's job is to:

  1. Reload context from the prep stage's report record.
  2. Produce ``logs/memo_package.json`` through the fast or legacy Claude path.
  3. Render the DOCX files from Claude's structured ``memo_package.json``.
  4. Verify the expected output files and renderer logs exist.
  5. Update the report record + emit the terminal ``done`` / ``error``.

What this worker deliberately does **not** do (see `docs/architecture.md`):

  - Does **not** pre-extract files. The skill handles its own input
    reading.
  - Does **not** author per-run render code. The skill writes a structured
    package and the worker calls the tracked ``server.memo_docx_renderer``.
  - Does **not** touch ``data/uploads/`` — that's the Document
    Library, a separate feature, not a memo input.
  - Does **not** let Claude write final `.docx` files. Python owns rendering
    for both the fast and legacy paths.
"""
from __future__ import annotations

import atexit
import itertools
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import inspect
import json
import logging
import os
import re
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    claude_runner,
    docx_pdf,
    internal_memo_renderer,
    job_progress,
    memo_chinese_parity,
    memo_docx_renderer,
    memo_engine,
    memo_flags,
    memo_pin_check,
    memo_prep,
    memo_prompts,
    memo_quality_lint,
    memo_structure,
    product_store,
    research_store,
    serena_analysis,
    storage,
)

logger = logging.getLogger(__name__)


# Report ids whose run was halted from outside its worker (cancelled by the
# user, interrupted by server shutdown). The halting call writes the terminal
# state itself; the worker thread that unwinds afterwards must not overwrite
# it, so its report writes, stream events and tracking finalize are dropped
# until the report is started again (``_with_run_slot``).
_HALTED_RUNS: set[str] = set()
_HALTED_RUNS_LOCK = threading.Lock()


def _halt_run(report_id: str) -> None:
    with _HALTED_RUNS_LOCK:
        _HALTED_RUNS.add(report_id)


def _clear_run_halt(report_id: str) -> None:
    with _HALTED_RUNS_LOCK:
        _HALTED_RUNS.discard(report_id)


def _run_halted(report_id: str) -> bool:
    with _HALTED_RUNS_LOCK:
        return report_id in _HALTED_RUNS


def _update_report(report_id: str, **fields: Any) -> dict | None:
    """``storage.update_report`` for memo workers: a no-op once the run is halted."""
    if _run_halted(report_id):
        return storage.get_report(report_id)
    return storage.update_report(report_id, **fields)


class _RunStream(job_progress.ProgressLog):
    """A memo run's stream as its worker writes it: silent once the run is halted."""

    def __init__(self, report_id: str, path: Path, *, truncate: bool = True):
        super().__init__(path, truncate=truncate)
        self._report_id = report_id

    def emit(self, type_: str, **fields: Any) -> None:
        if _run_halted(self._report_id):
            return
        super().emit(type_, **fields)


def _sync_tracking_auto_run(
    report: dict | None,
    *,
    success: bool,
    error: str | None = None,
) -> None:
    """Finalize a tracking auto-run when a memo job ends (success or failure)."""
    if isinstance(report, dict) and _run_halted(str(report.get("id") or "").strip()):
        return
    _complete_tracking_auto_run(report, success=success, error=error)


def _complete_tracking_auto_run(
    report: dict | None,
    *,
    success: bool,
    error: str | None = None,
) -> None:
    if not isinstance(report, dict):
        return
    report_id = str(report.get("id") or "").strip()
    company_id = str(report.get("company_id") or "").strip()
    if not report_id or not company_id:
        return
    try:
        from . import tracking_updates

        tracking_updates.complete_auto_run_for_job(
            company_id,
            job_kind="memo_report",
            report_id=report_id,
            success=success,
            error=error,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "tracking auto-run finalize failed for memo %s (success=%s)",
            report_id,
            success,
        )


def _write_recent_news_file(company_id: str, research_dir: Path) -> None:
    """Refresh the tracked-news digest (``recent_news.md``) the analysis
    passes read from the research folder.

    Best-effort by design: a broken tracking store must never fail a
    memo run. When the store has no items the existing file (if any) is
    left alone — the loader's kill switch covers full disable.
    """
    try:
        from . import tracking_updates

        text = tracking_updates.render_research_news_md(company_id)
        if not text:
            return
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / claude_runner.MEMO_RECENT_NEWS_FILENAME).write_text(
            text + "\n", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        logger.exception("tracked-news digest write failed for %s", company_id)


def _write_decision_record_file(company_id: str, research_dir: Path) -> None:
    """Refresh the human decision-record digest (``decision_record.md``)
    the analysis passes and the spine read from the research folder.

    Same contract as the tracked-news digest: best-effort, never fails a
    run, leaves any existing file alone when the store has no decisions
    (the loader's kill switch covers full disable)."""
    try:
        from . import decisions_store

        text = decisions_store.render_decision_record_md(company_id)
        if not text:
            return
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / claude_runner.MEMO_DECISION_RECORD_FILENAME).write_text(
            text, encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        logger.exception("decision-record digest write failed for %s", company_id)


def _write_known_sources_file(company_id: str, research_dir: Path) -> None:
    """Refresh the known-sources digest (``known_sources.md``) from the
    company's source cache before Phase 2, so every pass and the spine see
    the pages earlier runs and sweeps already fetched. Best-effort, like
    the tracked-news digest; leaves an existing file alone when the cache
    is empty."""
    try:
        from . import source_cache

        source_cache.write_known_sources_file(
            company_id, research_dir, claude_runner.MEMO_KNOWN_SOURCES_FILENAME
        )
    except Exception:  # noqa: BLE001
        logger.exception("known-sources digest write failed for %s", company_id)


RUN_INPUTS_FILENAME = "run_inputs.json"


def _stage_run_inputs(
    report: dict, run_dir: Path, research_dir: Path, stream
) -> dict:
    """Stage the firm's own material for this run (reference-call notes,
    founder updates and KPIs, the deal terms on file, open reader flags;
    see ``memo_inputs``), record what the run is built from on the report
    and in ``logs/run_inputs.json`` (stamped into the package at
    acceptance), and list the staged files in the run manifest.
    Best-effort: staging never fails a run."""
    company_id = str(report.get("company_id") or run_dir.parent.name)
    try:
        from . import memo_inputs

        staged = memo_inputs.stage_run_inputs(company_id, research_dir, run_dir)
    except Exception:  # noqa: BLE001
        logger.exception("run input staging failed for %s", company_id)
        return {}
    excluded = list(staged.get("registry_placeholders_excluded") or [])
    record = {
        "built_from": staged.get("built_from"),
        "deal_terms_on_file": bool(staged.get("deal_terms_on_file")),
        "deal_terms_source": staged.get("deal_terms_source"),
        "reader_flags": staged.get("reader_flags") or 0,
        "staged": list(staged.get("staged") or []),
        "registry_entry": (
            memo_prep._rel(Path(staged["registry_entry"]))
            if staged.get("registry_entry")
            else None
        ),
        "registry_placeholders_excluded": len(excluded),
        "registry_placeholders": excluded[:20],
    }
    try:
        _write_json(run_dir / "logs" / RUN_INPUTS_FILENAME, record)
    except OSError:
        logger.warning("could not record the run inputs", exc_info=True)
    if excluded:
        stream.emit(
            "stage",
            stage="memo_registry_placeholders_excluded",
            message=(
                f"{len(excluded)} registry field(s) excluded from the run: "
                "placeholders with no document"
            ),
            excluded=excluded[:20],
        )
    try:
        _update_report(
            str(report.get("id")),
            built_from=record["built_from"],
            deal_terms_on_file=record["deal_terms_on_file"],
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not record built_from on the report", exc_info=True)
    memo_prep.append_manifest_inputs(
        run_dir,
        [f"`{memo_prep._rel(research_dir / name)}`" for name in record["staged"]]
        + (
            [f"`{memo_prep._rel(run_dir / 'logs' / 'open_reader_flags.md')}` (inlined)"]
            if record["reader_flags"]
            else []
        ),
    )
    built = record["built_from"] or {}
    stream.emit(
        "stage",
        stage="memo_inputs_staged",
        message=(
            f"Built from {built.get('research_docs', 0)} research document(s), "
            f"{built.get('calls', 0)} call(s), "
            f"{built.get('founder_updates', 0)} founder update(s)"
            + ("; deal terms on file" if record["deal_terms_on_file"] else "")
            + (
                f"; {record['reader_flags']} open reader flag(s)"
                if record["reader_flags"]
                else ""
            )
        ),
        **record,
    )
    return record


def _run_inputs(run_dir: Path) -> dict:
    try:
        payload = json.loads(
            (run_dir / "logs" / RUN_INPUTS_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_companies_yaml(run_dir: Path | None) -> Path:
    """The registry file this run's agents read: the run's own
    placeholder-free copy of the company's entry
    (``logs/registry_entry.yaml``, staged by ``memo_inputs``) when it
    exists, else ``data/companies.yaml`` as before."""
    if run_dir is not None:
        try:
            from . import memo_inputs

            staged = Path(run_dir) / "logs" / memo_inputs.REGISTRY_ENTRY_FILENAME
            if staged.is_file():
                return staged
        except Exception:  # noqa: BLE001
            logger.warning("could not resolve the staged registry entry", exc_info=True)
    return memo_prep.COMPANIES_FILE


def _reader_flags_block(run_dir: Path) -> str:
    """The open reader flags staged for this run, as inline text for the
    analysis passes' shared context ('' when there are none)."""
    try:
        return (run_dir / "logs" / "open_reader_flags.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _research_dir_for(company_id: str) -> Path:
    """The company's research folder as the research store keys it
    (``company_paths.storage_key``): a dotted or CJK id's uploads live under
    the hashed key, so building the path from the raw id missed them."""
    from . import company_paths

    try:
        key = company_paths.storage_key(company_id)
    except ValueError:
        key = str(company_id)
    return research_store.RESEARCH_ROOT / key


def _register_source_capture(report: dict, run_dir: Path) -> None:
    """Point the subprocess funnel's source capture at this report's
    company, for the resume and investigate entry points that do not go
    through the fast pipeline's own registration."""
    company_slug = run_dir.parent.name
    company_id = str(report.get("company_id") or company_slug)
    try:
        claude_runner.register_memo_run_source_capture(
            run_dir,
            company_id=company_id,
            run_id=str(report.get("run_id") or run_dir.name),
            research_dir=_research_dir_for(company_slug),
        )
    except Exception:  # noqa: BLE001
        logger.exception("source capture registration failed for %s", company_id)


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _memo_pdf_previews_enabled() -> bool:
    """PDF previews are expensive Word automation; keep them opt-in."""
    return _env_flag("BSH_MEMO_RENDER_PDF_PREVIEWS", default=False)


def _internal_diligence_memo_enabled() -> bool:
    """The LP-facing memo is ready before the optional internal memo."""
    return _env_flag("BSH_MEMO_GENERATE_INTERNAL", default=False)


def _memo_fast_pipeline_enabled() -> bool:
    """Use real parallel Claude workers unless explicitly disabled."""
    return _env_flag("BSH_MEMO_FAST_PIPELINE", default=True)


@contextmanager
def _creeping_report_progress(
    report_id: str,
    *,
    floor: int = 15,
    ceiling: int = 78,
    interval_sec: float = 10.0,
    half_life_sec: float = 300.0,
    stage: str | None = None,
):
    """Keep ``report.progress`` moving during long Claude waits.

    The memo pipeline used to park at 15% for 5–15 minutes while analysis
    ran, which made every client look frozen. This heartbeat creeps
    asymptotically from ``floor`` toward ``ceiling`` so the meter moves,
    without overtaking the real render milestones (~85+).
    """
    stop = threading.Event()
    started = time.monotonic()

    def _tick() -> None:
        while not stop.wait(interval_sec):
            try:
                elapsed = max(0.0, time.monotonic() - started)
                # Halfway from floor→ceiling at half_life_sec.
                frac = 1.0 - (0.5 ** (elapsed / max(half_life_sec, 1.0)))
                target = int(floor + (ceiling - floor) * frac)
                target = max(floor, min(ceiling, target))
                report = storage.get_report(report_id)
                if report is None:
                    return
                status = str(report.get("status") or "")
                if (
                    status.startswith("complete")
                    or status.startswith("failed")
                    or status in {"cancelled", "awaiting_studio"}
                ):
                    return
                current = int(report.get("progress") or 0)
                if target <= current:
                    continue
                patch: dict[str, Any] = {"progress": target}
                if stage:
                    patch["stage"] = stage
                _update_report(report_id, **patch)
            except Exception:  # noqa: BLE001 — never kill the memo for UI polish
                logger.exception(
                    "creeping progress tick failed for %s", report_id
                )

    thread = threading.Thread(
        target=_tick,
        name=f"memo-progress-{report_id[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval_sec + 1.0)


def _memo_zh_chasing_enabled() -> bool:
    """Speculative Chinese translation of English sections as they finish.

    Only meaningful when the parallel English path is on — without it there
    are no per-section English drafts to chase.
    """
    return (
        memo_flags.enabled("BSH_MEMO_ZH_CHASING")
        and memo_flags.enabled("BSH_MEMO_ENGLISH_PARALLEL")
    )


def _memo_pin_check_enabled() -> bool:
    """Deterministic pin-echo verification (report-only by default).

    Costs milliseconds, reads only the assembled candidate and the spine's
    shared facts, so it defaults ON wherever the parallel path produced a
    spine. It exists both as observability (how often would speculation
    have drifted?) and as the safety net for the speculative levers.
    """
    return _env_flag("BSH_MEMO_PIN_CHECK", default=True)


def _memo_pin_check_repair_enabled() -> bool:
    """Feed pin-echo findings into the repair loop (default OFF: report
    only). Turn on once live runs show the findings are trustworthy."""
    return memo_flags.enabled("BSH_MEMO_PIN_CHECK_REPAIR")


def _memo_fast_max_workers() -> int:
    """Phase-2 pass pool width. The per-run subprocess ceiling
    (claude_runner._memo_run_max_procs, owner cap 10) is enforced
    separately at the subprocess funnel."""
    raw = os.environ.get("BSH_MEMO_FAST_MAX_WORKERS")
    try:
        value = int(raw) if raw is not None else 10
    except ValueError:
        value = 10
    return max(1, min(value, 10))


def _memo_fast_english_package_retries() -> int:
    raw = os.environ.get("BSH_MEMO_FAST_ENGLISH_PACKAGE_RETRIES")
    try:
        value = int(raw) if raw is not None else 2
    except ValueError:
        value = 2
    return max(0, min(value, 3))


def _memo_resume_package_retries() -> int:
    raw = os.environ.get("BSH_MEMO_RESUME_PACKAGE_RETRIES")
    try:
        value = int(raw) if raw is not None else 1
    except ValueError:
        value = 1
    return max(0, min(value, 3))


def _memo_fast_retry_backoff_sec() -> float:
    raw = os.environ.get("BSH_MEMO_FAST_RETRY_BACKOFF_SEC")
    try:
        value = float(raw) if raw is not None else 0.0
    except ValueError:
        value = 0.0
    return max(0.0, min(value, 60.0))


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Warnings a delivered memo carries -------------------------------------
# ``quality_warnings`` (English strings) stays what tests and Warren read;
# ``quality_warnings_zh`` is its aligned Chinese twin, and
# ``quality_warning_items`` the structured form the web banner renders:
# [{gate, language "EN"|"ZH", section, severity, code, summary_en,
# summary_zh, detail_path?}]. New wording must never contain "quality gate"
# or "memo quality": Resume reads those words as "the English failed its
# gate" and regenerates the whole English package
# (_english_quality_gate_needs_package_regen).

ENGLISH_READY_STAGE = (
    "English memo ready — Chinese in progress / 英文版已就绪，中文版生成中"
)
CHINESE_FAILED_WARNING = (
    "Chinese version failed — English delivered",
    "中文版生成失败，已交付英文版",
)
CHINESE_CANCELLED_WARNING = (
    "Chinese version cancelled — English delivered",
    "中文版已取消，已交付英文版",
)
CHINESE_PACKAGE_PHASE = "chinese_package"
# A run launched with ``pause_after_english`` stops here once its English
# memo is accepted and rendered; Resume ("Retry Chinese" mechanics) writes
# the Chinese from the accepted English package.
PAUSED_AFTER_ENGLISH_STATUS = "english_ready_paused"
ENGLISH_PAUSED_STAGE = (
    "English ready — review before Chinese / 英文版已就绪，请审阅后再生成中文版"
)
_MAX_WARNING_ITEMS_PER_GATE = 12


def _warning_item(
    *,
    gate: str,
    language: str,
    summary_en: str,
    summary_zh: str,
    section: str | None = None,
    severity: str = "warning",
    code: str | None = None,
    detail_path: str | None = None,
) -> dict:
    item = {
        "gate": gate,
        "language": language,
        "section": section,
        "severity": severity,
        "code": code or gate,
        "summary_en": summary_en,
        "summary_zh": summary_zh,
    }
    if detail_path:
        item["detail_path"] = detail_path
    return item


class _RunWarnings:
    """The warnings a run delivers with: the English strings, their aligned
    Chinese twins and the structured items, kept in step."""

    def __init__(self) -> None:
        self.en: list[str] = []
        self.zh: list[str] = []
        self.items: list[dict] = []

    def add(self, en: str, zh: str, items: list[dict] | None = None) -> None:
        self.en.append(en)
        self.zh.append(zh)
        self.items.extend(items or [])

    def __bool__(self) -> bool:
        return bool(self.en)

    def record_fields(self) -> dict:
        return {
            "quality_warnings": list(self.en) or None,
            "quality_warnings_zh": list(self.zh) or None,
            "quality_warning_items": list(self.items) or None,
        }


def _finding_items(
    findings, *, gate: str, language: str, detail_path: str | None
) -> list[dict]:
    """One structured item per blocking finding (lint / parity), capped.
    Findings may be the gates' dataclasses or their ``to_dict()`` form."""

    def field(finding, name: str) -> str:
        if isinstance(finding, dict):
            return str(finding.get(name) or "")
        return str(getattr(finding, name, "") or "")

    items: list[dict] = []
    for finding in list(findings or [])[:_MAX_WARNING_ITEMS_PER_GATE]:
        snippet = re.sub(r"\s+", " ", field(finding, "snippet")).strip()
        suggestion = field(finding, "suggestion").strip()
        code = field(finding, "code") or gate
        summary_en = f"{code}: \"{snippet[:160]}\"" + (
            f" — {suggestion[:200]}" if suggestion else ""
        )
        items.append(
            _warning_item(
                gate=gate,
                language=language,
                section=field(finding, "location") or None,
                severity=field(finding, "severity") or "P0",
                code=code,
                summary_en=summary_en,
                summary_zh=f"{code}：“{snippet[:160]}”",
                detail_path=detail_path,
            )
        )
    return items


def _emit_phase_timing(
    stream: job_progress.ProgressLog,
    *,
    phase: str,
    status: str,
    started_at: str,
    started_monotonic: float,
    **fields: Any,
) -> None:
    payload = {
        "phase": phase,
        "status": status,
        "started_at": started_at,
        **fields,
    }
    if status in {"finished", "failed", "skipped"}:
        payload["finished_at"] = _now_iso()
        payload["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
    stream.emit("phase_timing", **payload)


@contextmanager
def _timed_phase(
    stream: job_progress.ProgressLog,
    *,
    phase: str,
    **fields: Any,
):
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    _emit_phase_timing(
        stream,
        phase=phase,
        status="started",
        started_at=started_at,
        started_monotonic=started_monotonic,
        **fields,
    )
    outcome: dict[str, Any] = {}
    try:
        yield outcome
    except Exception as exc:  # noqa: BLE001
        outcome.setdefault("error", f"{type(exc).__name__}: {exc}")
        status = str(outcome.pop("status", "failed"))
        _emit_phase_timing(
            stream,
            phase=phase,
            status=status,
            started_at=started_at,
            started_monotonic=started_monotonic,
            **fields,
            **outcome,
        )
        raise
    else:
        status = str(outcome.pop("status", "finished"))
        _emit_phase_timing(
            stream,
            phase=phase,
            status=status,
            started_at=started_at,
            started_monotonic=started_monotonic,
            **fields,
            **outcome,
        )


class _ThreadProgress:
    """Attach a stable progress thread to events from one fast memo worker."""

    def __init__(self, base: job_progress.ProgressLog, thread: str):
        self._base = base
        self._thread = thread
        self.cost_usd = 0.0
        self.duration_ms = 0
        # Several worker threads can share one _ThreadProgress (the parallel
        # English sections, the bilingual units); the accumulation must not
        # lose updates.
        self._totals_lock = threading.Lock()

    def emit(self, type_: str, **fields: Any) -> None:
        fields.setdefault("thread", self._thread)
        if type_ == "claude_action" and fields.get("action") == "result":
            with self._totals_lock:
                self.cost_usd += _as_float(fields.get("cost_usd"))
                self.duration_ms += _as_int(fields.get("duration_ms"))
        self._base.emit(type_, **fields)

    @property
    def is_terminated(self) -> bool:
        try:
            return self._base.is_terminated
        except Exception:  # noqa: BLE001
            return False


@dataclass(frozen=True)
class _FastMemoPassSpec:
    pass_id: str
    label: str
    artifact_filename: str
    focus: str


# A pass that answers with placeholder text passes schema validation and
# poisons everything downstream. Observed live on 2026-09-16: market_sizing
# ran for 2.4 minutes, spent 16k output tokens and returned
# summary="test" with a single finding of claim="a", finding="b" — the
# memo's whole TAM section was then written from "a | b | c | d". Nothing
# in the pipeline noticed, because the shape was valid.
# A floor for obviously-empty answers, not a quality judge: a pass whose
# summary is this short has not written a summary at all.
_FAST_PASS_MIN_SUMMARY_CHARS = 20
_FAST_PASS_MIN_FINDING_CHARS = 40
_FAST_PASS_PLACEHOLDER_WORDS = frozenset(
    {"test", "todo", "tbd", "placeholder", "n/a", "na", "none", "example", "foo"}
)


def _fast_pass_degenerate_reason(data: dict | None) -> str | None:
    """Why this pass result is unusable, or None when it looks like work.

    Both halves must fail before a pass is thrown away: a thin summary on
    top of real findings is terse, not broken, and a pass that genuinely
    found nothing is allowed to say so. Only an answer that is empty at
    BOTH ends is placeholder text.
    """
    if not isinstance(data, dict):
        return None  # a missing result is already an error
    summary = str(data.get("summary") or "").strip()
    looks_placeholder = (
        len(summary) < _FAST_PASS_MIN_SUMMARY_CHARS
        or summary.strip(" .").lower() in _FAST_PASS_PLACEHOLDER_WORDS
    )
    if not looks_placeholder:
        return None
    findings = data.get("key_findings")
    findings = findings if isinstance(findings, list) else []
    for item in findings:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        finding = str(item.get("finding") or "").strip()
        if len(claim) + len(finding) >= _FAST_PASS_MIN_FINDING_CHARS:
            return None
    return (
        f"summary is {summary[:40]!r} and none of its {len(findings)} "
        f"key_findings carry {_FAST_PASS_MIN_FINDING_CHARS} characters of "
        "claim and finding"
    )


@dataclass
class _FastMemoPassResult:
    spec: _FastMemoPassSpec
    data: dict | None
    error: str | None
    duration_ms: int
    cost_usd: float
    usage: dict | None = None

    @property
    def ok(self) -> bool:
        return isinstance(self.data, dict) and not self.error


# Editorial prompts — the pass ids, labels, artifacts and focus texts
# live in skills/memo/passes.md (zh twin under skills/memo/zh/); the
# file order is the dispatch order.
_FAST_MEMO_PASSES: tuple[_FastMemoPassSpec, ...] = tuple(
    memo_prompts.load_passes(_FastMemoPassSpec)
)


def _memo_paths_abs(report: dict) -> dict[str, Path]:
    memo_files = report.get("memo_files") or []
    paths: dict[str, Path] = {}
    for entry in memo_files:
        lang = entry.get("language")
        rel = entry.get("path")
        if lang and rel:
            paths[str(lang)] = memo_prep.DATA_DIR.parent / rel
    return paths


def _internal_memo_paths_abs(report: dict) -> dict[str, Path]:
    """The IC decision memo's files: ``md`` / ``docx`` / ``pdf`` for the
    English entry (or the only entry of an older record) and ``md_zh`` /
    ``docx_zh`` / ``pdf_zh`` for the Chinese one."""
    entries = [
        entry
        for entry in report.get("internal_memo_files") or []
        if isinstance(entry, dict)
    ]
    if not entries:
        return {}
    paths: dict[str, Path] = {}
    english = next(
        (e for e in entries if str(e.get("language") or "en") == "en"), entries[0]
    )
    chinese = next((e for e in entries if e.get("language") == "zh"), None)
    for entry, suffix in ((english, ""), (chinese, "_zh")):
        if not entry:
            continue
        if entry.get("markdown_path"):
            paths[f"md{suffix}"] = memo_prep.DATA_DIR.parent / entry["markdown_path"]
        if entry.get("path"):
            paths[f"docx{suffix}"] = memo_prep.DATA_DIR.parent / entry["path"]
        if entry.get("pdf_path"):
            paths[f"pdf{suffix}"] = memo_prep.DATA_DIR.parent / entry["pdf_path"]
    return paths


def _analysis_session_path_for_report(
    company_slug: str,
    report: dict,
    *,
    require_approved: bool = False,
) -> Path | None:
    if require_approved and not report.get("analysis_session_approved"):
        return None
    analysis_session_id = report.get("analysis_session_id")
    if not analysis_session_id:
        return None
    candidate = serena_analysis.session_dir(company_slug, str(analysis_session_id))
    if candidate.exists():
        return candidate
    return None


def _memo_package_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "memo_package.json"


def _package_on_disk(path: Path) -> dict | None:
    """A package file's JSON object, or None (missing, unreadable, not an
    object) — for checks that are more precise with the package and still
    run without it."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


# A handful of paragraphs can come back from the translation wave with an
# empty `zh` — the chaser refuses a translation that dropped or renumbered a
# citation, and if its retry also misses, the slot stays blank. The renderer
# requires `zh`, so on 2026-09-16 one such paragraph failed a run that had
# already finished every phase. English in one Chinese paragraph is a far
# smaller defect than no memo at all, so a FEW gaps are filled from the
# English and reported. Many gaps mean the translation wave itself broke,
# which is not something to paper over — those still fail the run.
_MAX_ZH_FALLBACK_GAPS = 3


def _fill_sparse_zh_gaps(payload: Any, limit: int = _MAX_ZH_FALLBACK_GAPS) -> list[str]:
    """Fill blank ``zh`` slots from their English, in place.

    Returns one description per filled slot, or an empty list when there was
    nothing to fill or when there were too many to be a translation miss.
    """
    gaps: list[tuple[dict, str]] = []

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if "en" in node and "zh" in node:
                english = str(node.get("en") or "").strip()
                if english and not str(node.get("zh") or "").strip():
                    gaps.append((node, where))
            for key, value in node.items():
                walk(value, f"{where}.{key}")
            return
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{where}[{index}]")

    walk(payload, "package")
    if not gaps or len(gaps) > limit:
        return []
    filled = []
    for node, where in gaps:
        node["zh"] = node["en"]
        filled.append(f"{where}.zh: fell back to the English text")
    return filled


# Regenerating a section has never brought it under its ceiling. Across
# three Anthropic runs (2026-09-14 x2, 2026-09-16) every one of them spent
# two full retry rounds on word-budget errors and still failed; on the last
# of those company_team went 1358 -> 1187 -> 1018 words against a 750
# ceiling, and the surgical repair pass — which EDITS the package it is
# given instead of writing a new one — then fixed it in a single call.
# Rewriting from the same inputs lands at the same natural length; only
# editing converges. So a failure that is nothing but over-length sections
# skips the retries and goes straight to the repair.
#
# This must stay the exact phrase `memo_docx_renderer._word_budget_errors`
# writes. It said "-word ceiling" until the soft-budget change renamed the
# message to "...-word target and its ...-word hard cap", and the shortcut
# went silently dead: the 2026-09-16 re-run paid a full section
# regeneration for company_team being 42 words over. `test_memo_budget_loop`
# now builds its fixture from the renderer so the two cannot drift again.
_WORD_BUDGET_ERROR_MARKER = "-word hard cap"


def _only_word_budget_errors(validation_errors: list[str]) -> bool:
    return bool(validation_errors) and all(
        _WORD_BUDGET_ERROR_MARKER in str(err) for err in validation_errors
    )


def _only_envelope_or_budget_errors(
    validation_errors: list[str], package: dict | None
) -> bool:
    """Every error is either a word-budget overrun or lives in the package
    envelope (sources, company, run) — defects the per-section repair fixes
    without writing a section, and a regeneration would not.

    Live on 2026-09-21 (RadixArk 2026-09-21__195426) two sources cited
    without a URL — IDC's and Gartner's spending guides — sent the run into
    a full regeneration: a new spine and all seven sections rewritten, for
    two missing strings in the source list. The envelope repair that fixes
    exactly that already existed, one step further on."""
    if not validation_errors or not isinstance(package, dict):
        return False
    return all(
        _WORD_BUDGET_ERROR_MARKER in str(err)
        or claude_runner._is_envelope_repair_finding(package, str(err))
        for err in validation_errors
    )


# ---- Small word-cap overruns are delivered, not failed -------------------
# ZaiNar 2026-09-23__023008 died at the final English check with `risks`
# 69 words (1.3%) over its 5,200-word cap, after the per-section repair of
# that section could not fit its answer in one call and the whole-package
# repair timed out. A section within LENGTH_TOLERANCE of its cap now ships
# with a warning (gate "length", code section_over_cap); a larger overrun
# keeps the repair-or-fail path.
LENGTH_TOLERANCE = 0.10
LENGTH_WARNINGS_FILENAME = "length_warnings.json"
_WORD_BUDGET_ERROR_RE = re.compile(
    r"section (\S+) runs (\d+) English words against its (\d+)-word target "
    r"and its (\d+)-word hard cap"
)


def _over_cap_sections(package: dict | None) -> list[dict]:
    """Every budgeted section over its hard cap, with the SAME arithmetic
    as ``memo_docx_renderer._word_budget_errors``: the package's own
    structure (so a company type's emphasis re-cut is in the budgets), the
    renderer's word counter, and its grace multiple for a section that
    declares no hard multiple of its own."""
    if not isinstance(package, dict):
        return []
    sections = package.get("sections")
    if not isinstance(sections, list):
        return []
    try:
        structure = memo_structure.for_package(package)
    except Exception:  # noqa: BLE001
        return []
    grace = float(getattr(memo_docx_renderer, "_BUDGET_GRACE", 1.10))
    by_id = {str(s.get("id") or ""): s for s in sections if isinstance(s, dict)}
    out: list[dict] = []
    for sdef in structure.sections:
        if not sdef.budget_words:
            continue
        section = by_id.get(sdef.id)
        if section is None:
            continue
        words = memo_docx_renderer.section_en_word_count(section)
        hard_cap = sdef.budget_words * (sdef.budget_hard_multiple or grace)
        if words > hard_cap:
            cap = int(hard_cap)
            out.append(
                {
                    "section": sdef.id,
                    "words": words,
                    "cap": cap,
                    "target": sdef.budget_words,
                    "over_pct": round((words - cap) / cap * 100, 1) if cap else 0.0,
                }
            )
    return out


def _word_budget_overrun(error: str, package: dict | None) -> dict | None:
    """The ``{section, words, cap, target, over_pct}`` a word-cap error
    describes (parsed from the renderer's own message; recomputed from the
    package when the wording does not parse), or None for any other
    error."""
    text = str(error or "")
    if _WORD_BUDGET_ERROR_MARKER not in text:
        return None
    match = _WORD_BUDGET_ERROR_RE.search(text)
    if match:
        cap = int(match.group(4))
        words = int(match.group(2))
        if cap > 0:
            return {
                "section": match.group(1),
                "words": words,
                "cap": cap,
                "target": int(match.group(3)),
                "over_pct": round((words - cap) / cap * 100, 1),
            }
    for item in _over_cap_sections(package):
        if re.search(rf"\bsection {re.escape(item['section'])}\b", text):
            return item
    return None


def _overrun_within_tolerance(item: dict) -> bool:
    cap = int(item.get("cap") or 0)
    words = int(item.get("words") or 0)
    return cap > 0 and words <= cap * (1 + LENGTH_TOLERANCE)


def _blocking_validation_errors(
    errors: list[str], package: dict | None
) -> list[str]:
    """The validation errors that still fail the package once word-cap
    overruns within ``LENGTH_TOLERANCE`` are tolerated. Everything else —
    larger overruns included — keeps today's behaviour."""
    blocking: list[str] = []
    for err in errors or []:
        item = _word_budget_overrun(err, package)
        if item is not None and _overrun_within_tolerance(item):
            continue
        blocking.append(err)
    return blocking


def _tolerated_overruns(errors: list[str], package: dict | None) -> list[dict]:
    """The small overruns among ``errors`` (one entry per section)."""
    seen: set[str] = set()
    out: list[dict] = []
    for err in errors or []:
        item = _word_budget_overrun(err, package)
        if item is None or not _overrun_within_tolerance(item):
            continue
        if item["section"] in seen:
            continue
        seen.add(item["section"])
        out.append(item)
    return out


def _accept_with_small_overruns(
    *,
    run_dir: Path,
    package: dict | None,
    errors: list[str],
    progress,
    attempt: int | None = None,
) -> bool:
    """True when ``errors`` are nothing but word-cap overruns within the
    tolerance: the package is accepted, the overruns recorded in
    ``logs/length_warnings.json`` and announced. Any other error, or a
    larger overrun, returns False and changes nothing."""
    if not errors or not isinstance(package, dict):
        return False
    if _blocking_validation_errors(errors, package):
        return False
    overruns = _tolerated_overruns(errors, package)
    if not overruns:
        return False
    try:
        _write_json(
            run_dir / "logs" / LENGTH_WARNINGS_FILENAME,
            {"accepted_at": _now_iso(), "tolerance": LENGTH_TOLERANCE, "sections": overruns},
        )
    except OSError:
        logger.warning("could not record the length warnings", exc_info=True)
    progress.emit(
        "stage",
        stage="memo_package_length_accepted",
        message=(
            "Accepting the English package with "
            f"{len(overruns)} section(s) within {int(LENGTH_TOLERANCE * 100)}% "
            "of the word cap; delivered with a length warning instead of "
            "failing the run"
        ),
        sections=overruns,
        attempt=attempt,
    )
    return True


def _length_warning(
    run_dir: Path, warnings: "_RunWarnings", package: dict | None = None
) -> None:
    """A section delivered over its hard cap ships as a warning (gate
    "length", code section_over_cap: section, words, cap). Computed from
    the delivered package, so it names what the reader actually has."""
    package = package if isinstance(package, dict) else _delivered_package(run_dir)
    try:
        overruns = _over_cap_sections(package)
    except Exception:  # noqa: BLE001
        logger.warning("length check failed", exc_info=True)
        return
    if not overruns:
        return
    count = len(overruns)
    warnings.add(
        f"Length: {count} section{'' if count == 1 else 's'} over the word cap",
        f"篇幅：{count} 个章节超出字数上限",
        [
            _warning_item(
                gate="length",
                language="EN",
                section=item["section"],
                severity="warning",
                code="section_over_cap",
                summary_en=(
                    f"{item['section']}: {item['words']} words against a "
                    f"{item['cap']}-word cap ({item['over_pct']}% over)"
                ),
                summary_zh=(
                    f"{item['section']}：{item['words']} 词，上限 {item['cap']} 词"
                    f"（超出 {item['over_pct']}%）"
                ),
            )
            for item in overruns[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


# ---- Trim one subsection of an over-cap section -------------------------
# Regenerating a section never shortened it (see _WORD_BUDGET_ERROR_MARKER),
# and re-emitting a whole 5,000-word section to cut 69 words is what could
# not fit in one call. The trim asks for ONE subsection — the largest — to
# be rewritten to a target (claude_runner.run_section_trim, I1), then the
# section is re-assembled here from its subsection slices.
_TRIM_DIRNAME = "trim"


def _trim_slices_dir(run_dir: Path, section_id: str) -> Path:
    """The trim works on the section AS IT IS NOW (a repair may have
    changed it since the wave), so it is cut into fresh slices here rather
    than trimming the wave's own piece files in
    ``claude_runner.memo_section_pieces_dir``."""
    return claude_runner._memo_english_units_dir(run_dir) / _TRIM_DIRNAME / section_id


def _subsection_slices(
    run_dir: Path, section: dict, section_def
) -> list[dict] | None:
    """Cut an assembled section into its numbered subsections and write
    each as ``{"id", "blocks"}`` under ``logs/english_units/trim/<id>/``.
    Returns ``[{number, heading_en, path, words, blocks}]`` in document
    order, or None when the headings do not line up with the structure."""
    section_id = str(section.get("id") or "")
    try:
        plan = claude_runner._section_piece_plan(run_dir, section_id, section_def)
        groups = claude_runner._split_section_draft(section, plan)
    except Exception:  # noqa: BLE001
        logger.warning("could not slice section %s for a trim", section_id, exc_info=True)
        return None
    if not groups:
        return None
    slices_dir = _trim_slices_dir(run_dir, section_id)
    out: list[dict] = []
    for number, heading_en, _heading_zh, _path in plan:
        blocks = list(groups.get(number) or [])
        path = slices_dir / f"{number:02d}.json"
        try:
            _write_json(path, {"id": section_id, "blocks": blocks})
        except OSError:
            return None
        out.append(
            {
                "number": number,
                "heading_en": heading_en,
                "path": path,
                "words": memo_docx_renderer.section_en_word_count({"blocks": blocks}),
                "blocks": blocks,
            }
        )
    return out


def _trim_section_once(
    *,
    run_dir: Path,
    package: dict,
    item: dict,
    structure: memo_structure.MemoStructure,
    progress,
    role: str = "REPAIR",
    company_name: str | None = None,
) -> bool:
    """One trim of the largest subsection of the over-cap section ``item``
    names, then re-assembly in place. True when the section was rewritten."""
    section_id = str(item.get("section") or "")
    sections = package.get("sections") if isinstance(package, dict) else None
    section = next(
        (s for s in sections or [] if isinstance(s, dict) and s.get("id") == section_id),
        None,
    )
    section_def = next((d for d in structure.sections if d.id == section_id), None)
    if section is None or section_def is None or len(section_def.subsections) < 2:
        return False
    slices = _subsection_slices(run_dir, section, section_def)
    if not slices:
        progress.emit(
            "stage",
            stage="memo_section_trim_skipped",
            message=(
                f"Section {section_id} could not be cut into its subsections "
                "for a trim; leaving it to the repair"
            ),
            section=section_id,
        )
        return False
    largest = max(slices, key=lambda s: s["words"])
    excess = int(item["words"]) - int(item["cap"])
    margin = max(25, int(int(item["cap"]) * 0.03))
    target = max(int(largest["words"] * 0.4), largest["words"] - excess - margin)
    progress.emit(
        "stage",
        stage="memo_section_trim",
        message=(
            f"Section {section_id} runs {item['words']} words against its "
            f"{item['cap']}-word cap; trimming its largest subsection "
            f"({largest['heading_en']}, {largest['words']} words) to about "
            f"{target}"
        ),
        section=section_id,
        subsection=largest["number"],
        words=item["words"],
        cap=item["cap"],
        target_words=target,
    )
    try:
        result = claude_runner.run_section_trim(
            run_dir,
            section_id=section_id,
            subsection_path=largest["path"],
            target_words=target,
            hard_cap_words=int(item["cap"]),
            structure=structure,
            progress=progress,
            role=role,
            company_name=company_name,
        )
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict) or not result.get("ok"):
        progress.emit(
            "stage",
            stage="memo_section_trim_failed",
            message=f"Trim of section {section_id} failed; leaving it to the repair",
            section=section_id,
            error=str((result or {}).get("error") if isinstance(result, dict) else result)[:500],
        )
        return False
    try:
        payload = json.loads(Path(largest["path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = None
    blocks = payload.get("blocks") if isinstance(payload, dict) else payload
    if not isinstance(blocks, list) or not blocks:
        progress.emit(
            "stage",
            stage="memo_section_trim_failed",
            message=f"Trim of section {section_id} returned no blocks; leaving it to the repair",
            section=section_id,
        )
        return False
    assembled: list = []
    for piece in slices:
        assembled.extend(blocks if piece["number"] == largest["number"] else piece["blocks"])
    words_before = int(item["words"])
    section["blocks"] = assembled
    words_after = memo_docx_renderer.section_en_word_count(section)
    progress.emit(
        "stage",
        stage="memo_section_trimmed",
        message=(
            f"Section {section_id}: {words_before} -> {words_after} words "
            f"(cap {item['cap']})"
        ),
        section=section_id,
        words_before=words_before,
        words_after=words_after,
        cap=item["cap"],
        under_cap=words_after <= int(item["cap"]),
    )
    return True


def _trim_oversized_sections(
    *,
    run_dir: Path,
    package: dict | None,
    progress,
    trimmed: set[str],
    only: set[str] | None = None,
    company_name: str | None = None,
) -> list[str]:
    """After the wave assembled the sections (or a per-section repair
    could not fit its answer), every section over its hard cap gets ONE
    trim of its largest subsection — never a second one in the same
    attempt (``trimmed`` remembers). Returns the ids that were rewritten."""
    if not isinstance(package, dict):
        return []
    overruns = [
        item
        for item in _over_cap_sections(package)
        if item["section"] not in trimmed
        and (only is None or item["section"] in only)
    ]
    if not overruns:
        return []
    try:
        structure = memo_structure.for_package(package)
    except Exception:  # noqa: BLE001
        return []
    done: list[str] = []
    for item in overruns:
        trimmed.add(item["section"])
        if _trim_section_once(
            run_dir=run_dir,
            package=package,
            item=item,
            structure=structure,
            progress=progress,
            company_name=company_name,
        ):
            done.append(item["section"])
    return done


# ---- Per-section repair that keeps what succeeded ------------------------
# claude_runner.run_memo_package_sectional_repair returns nothing when ANY
# section's repair fails: on ZaiNar 2026-09-23__023008 the envelope and
# company_team repairs succeeded, the risks repair could not fit its answer
# in one call, and all three were thrown away. This orchestrator drives
# the same per-section and envelope repair calls, applies every success,
# and names the failures — an "output too large" failure is then trimmed
# instead of re-emitted.
def _error_code(error: Any) -> str:
    """The typed code of a repair error (``claude_runner.repair_error_code``:
    a ``MemoStageError``'s ``code``, or the phrase it recognises)."""
    if isinstance(error, dict):
        return str(error.get("error_code") or error.get("code") or "")
    return str(claude_runner.repair_error_code(error) or "")


def _is_output_too_large(error: Any) -> bool:
    return _error_code(error) == claude_runner.REPAIR_ERROR_OUTPUT_TOO_LARGE


def _edits_mode_kwargs(func) -> dict:
    """``{"mode": "edits"}`` for the repair runner (I2): the model returns
    edits and the runner applies them, instead of re-emitting the whole
    section. Passed explicitly so a fake in a test sees the contract."""
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return {}
    if "mode" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    ):
        return {"mode": "edits"}
    return {}


@dataclass
class _SectionalRepairOutcome:
    package: dict
    repaired: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    too_large: list[str] = field(default_factory=list)
    envelope_repaired: bool = False
    envelope_error: str | None = None
    unmapped: list[str] = field(default_factory=list)

    @property
    def any_success(self) -> bool:
        return bool(self.repaired) or self.envelope_repaired


def _repair_package_by_section(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    package: dict,
    findings: list[str],
    progress,
    stream=None,
    attempt: int | None = None,
    timeout_sec: int = 900,
) -> _SectionalRepairOutcome:
    """Repair ``findings`` per section (and the envelope) in parallel and
    keep every repair that succeeded (I3). Findings attributable to
    neither are returned in ``unmapped`` and left for the caller."""
    structure = memo_structure.for_package(package)
    mapping, envelope_findings, unmapped = claude_runner._partition_repair_findings(
        package, findings
    )
    outcome = _SectionalRepairOutcome(
        package=json.loads(json.dumps(package)), unmapped=list(unmapped)
    )
    sections_by_id = {
        section.get("id"): section
        for section in package.get("sections") or []
        if isinstance(section, dict)
    }
    mapping = {sid: errs for sid, errs in mapping.items() if sid in sections_by_id}
    if not mapping and not envelope_findings:
        return outcome
    section_repair = claude_runner.run_memo_section_repair
    envelope_repair = claude_runner.run_memo_envelope_repair
    extra = _edits_mode_kwargs(section_repair)
    suffix = f" (attempt {attempt})" if attempt and attempt > 1 else ""

    def _row_events(row: str, phase_name: str, description: str, phase_index: float):
        started_at = _now_iso()
        started_monotonic = time.monotonic()
        if stream is not None:
            stream.emit(
                "thread_planned",
                thread=row,
                title=row,
                phase_index=phase_index,
                parent_thread=claude_runner._MEMO_PHASE3_THREAD,
                group="memo_repair",
                estimate_ms=180_000,
                description=description,
            )
            stream.emit("thread_started", thread=row, title=row)
            stream.emit(
                "phase_timing",
                phase=phase_name,
                status="started",
                started_at=started_at,
                thread=row,
            )

        def _close(result, error) -> None:
            if stream is None:
                return
            duration_ms = int((time.monotonic() - started_monotonic) * 1000)
            finished_at = _now_iso()
            if error is None and isinstance(result, dict):
                stream.emit("thread_finished", thread=row, duration_ms=duration_ms)
                stream.emit(
                    "phase_timing",
                    phase=phase_name,
                    status="finished",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row,
                    cost_usd=result.get("claude_cost_usd"),
                    claude_duration_ms=result.get("claude_duration_ms"),
                )
            else:
                text = str(error or "no result")[:500]
                stream.emit(
                    "thread_failed", thread=row, duration_ms=duration_ms, error=text
                )
                stream.emit(
                    "phase_timing",
                    phase=phase_name,
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row,
                    error=text,
                    error_code=_error_code(error) or None,
                )

        return _close

    ordered = sorted(mapping)

    def _repair_one(section_id: str):
        close = _row_events(
            f"Repair - {section_id}{suffix}",
            f"english_repair:{section_id}",
            f"Surgically repair the {section_id} section",
            round(3.51 + ordered.index(section_id) / 100, 4),
        )
        try:
            result, error = section_repair(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                section=sections_by_id[section_id],
                section_id=section_id,
                findings=mapping[section_id],
                progress=progress,
                timeout_sec=timeout_sec,
                structure=structure,
                **extra,
            )
        except Exception as exc:  # noqa: BLE001
            result, error = None, f"repair crashed: {exc}"
        close(result, error)
        return result, error

    def _repair_envelope():
        close = _row_events(
            f"Repair - envelope{suffix}",
            "english_repair:envelope",
            "Surgically repair the package envelope",
            3.50,
        )
        envelope = {k: v for k, v in package.items() if k != "sections"}
        try:
            result, error = envelope_repair(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                envelope=envelope,
                findings=envelope_findings,
                progress=progress,
                timeout_sec=timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            result, error = None, f"envelope repair crashed: {exc}"
        close(result, error)
        return result, error

    max_procs = getattr(claude_runner, "_memo_run_max_procs", None)
    try:
        procs = int(max_procs()) if callable(max_procs) else 4
    except Exception:  # noqa: BLE001
        procs = 4
    workers = max(1, min(len(ordered) + (1 if envelope_findings else 0), procs))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="memo-repair") as pool:
        futures = {sid: pool.submit(_repair_one, sid) for sid in ordered}
        envelope_future = pool.submit(_repair_envelope) if envelope_findings else None
        for section_id, future in futures.items():
            try:
                result, error = future.result()
            except Exception as exc:  # noqa: BLE001
                result, error = None, f"repair crashed: {exc}"
            section = result.get("section") if isinstance(result, dict) else None
            if error is None and isinstance(section, dict):
                outcome.repaired.append(section_id)
                outcome.package["sections"] = [
                    section if isinstance(s, dict) and s.get("id") == section_id else s
                    for s in outcome.package.get("sections") or []
                ]
                continue
            outcome.failed[section_id] = str(error or "no section returned")
            if _is_output_too_large(error):
                outcome.too_large.append(section_id)
        if envelope_future is not None:
            try:
                env_result, env_error = envelope_future.result()
            except Exception as exc:  # noqa: BLE001
                env_result, env_error = None, f"envelope repair crashed: {exc}"
            envelope = env_result.get("envelope") if isinstance(env_result, dict) else None
            if env_error is None and isinstance(envelope, dict):
                for key, value in envelope.items():
                    if key != "sections":
                        outcome.package[key] = value
                outcome.envelope_repaired = True
            else:
                outcome.envelope_error = str(env_error or "no envelope returned")
    return outcome


# ---- Side agents on a failure path ---------------------------------------
def _shutdown_side_agent(agent, *, cancel: bool = True) -> float:
    """Shut a chaser or artifacts handle down — cancelling its pending
    work and reaping its live subprocesses when the runner supports
    ``shutdown(cancel=True)`` (I14) — and return the spend it reports
    afterwards (``cost_usd``, 0 when it exposes none), so a failure path
    can add what was spent after the failure to ``claude_cost_usd``."""
    if agent is None:
        return 0.0
    outcome = None
    try:
        try:
            outcome = agent.shutdown(cancel=cancel)
        except TypeError:
            outcome = agent.shutdown()
    except Exception:  # noqa: BLE001
        logger.warning("side agent shutdown failed", exc_info=True)
    if isinstance(outcome, dict):
        return _as_float(outcome.get("post_cancel_cost_usd"))
    cost = getattr(agent, "cost_usd", 0.0)
    return _as_float(cost) if isinstance(cost, (int, float)) else 0.0


# ---- Cost guard -------------------------------------------------------------
# The run stops BEFORE a paid phase starts once its accumulated cost has
# passed the ceiling — the per-run ``cost_ceiling_usd`` on the record, else
# BSH_MEMO_COST_CEILING_USD (default 60) — and delivers what is finished
# (the English-only delivery path) with a warning (gate "cost"). A phase
# already running is never interrupted.
COST_CEILING_ENV = "BSH_MEMO_COST_CEILING_USD"
DEFAULT_COST_CEILING_USD = 60.0
COST_GUARD_FILENAME = "cost_guard.json"


def _env_number(name: str, default: float) -> float:
    """``memo_flags``-style read of a numeric switch: the environment when
    it holds a number, else ``default``."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _cost_ceiling_usd(report: dict | None) -> float:
    raw = (report or {}).get("cost_ceiling_usd")
    try:
        value = float(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        value = None
    if value is not None and value > 0:
        return value
    return _env_number(COST_CEILING_ENV, DEFAULT_COST_CEILING_USD)


def _cost_guard_stops(run_dir: Path) -> list[dict]:
    try:
        payload = json.loads(
            (run_dir / "logs" / COST_GUARD_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return []
    stops = payload.get("stops") if isinstance(payload, dict) else None
    return [s for s in stops or [] if isinstance(s, dict)]


def _cost_guard_stop(
    *,
    report_id: str | None,
    run_dir: Path,
    cost_usd: float,
    phase: str,
    stream,
) -> dict | None:
    """The stop record when the next paid phase (``phase``) must not
    start because the run's cost has reached its ceiling, else None."""
    report = storage.get_report(report_id) if report_id else None
    ceiling = _cost_ceiling_usd(report)
    if ceiling <= 0 or _as_float(cost_usd) < ceiling:
        return None
    stop = {
        "phase": phase,
        "cost_usd": round(_as_float(cost_usd), 6),
        "ceiling_usd": ceiling,
        "at": _now_iso(),
    }
    stops = _cost_guard_stops(run_dir) + [stop]
    try:
        _write_json(run_dir / "logs" / COST_GUARD_FILENAME, {"stops": stops})
    except OSError:
        logger.warning("could not record the cost guard stop", exc_info=True)
    stream.emit(
        "stage",
        stage="memo_cost_ceiling",
        message=(
            f"Cost ceiling reached (US${stop['cost_usd']:.2f} of "
            f"US${ceiling:.2f}) before the {phase}; delivering what is finished"
        ),
        **stop,
    )
    return stop


def _cost_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    stops = _cost_guard_stops(run_dir)
    if not stops:
        return
    phases = ", ".join(str(s.get("phase") or "?") for s in stops)
    last = stops[-1]
    warnings.add(
        f"Cost ceiling reached — skipped: {phases}",
        f"已达到费用上限——跳过：{phases}",
        [
            _warning_item(
                gate="cost",
                language="EN",
                severity="warning",
                code="cost_ceiling",
                summary_en=(
                    f"Run cost US${_as_float(last.get('cost_usd')):.2f} reached the "
                    f"US${_as_float(last.get('ceiling_usd')):.2f} ceiling before the "
                    f"{last.get('phase')}; raise cost_ceiling_usd or "
                    f"{COST_CEILING_ENV} and resume to finish"
                ),
                summary_zh=(
                    f"运行费用 US${_as_float(last.get('cost_usd')):.2f} 在"
                    f"{last.get('phase')}之前达到 US${_as_float(last.get('ceiling_usd')):.2f} "
                    "上限；提高上限后可继续"
                ),
                detail_path=memo_prep._rel(run_dir / "logs" / COST_GUARD_FILENAME),
            )
        ],
    )


def _skip_artifacts_for_cost(run_dir: Path) -> bool:
    """Make the section wave treat the analysis artifacts as already
    written (empty), so no artifacts agent starts: the wave reads
    ``logs/english_units/analysis_artifacts.json`` as its cache. Stub
    artifact files are written at delivery as on any degraded run."""
    units_dir = getattr(claude_runner, "_memo_english_units_dir", None)
    if not callable(units_dir):
        return False
    try:
        _write_json(units_dir(run_dir) / "analysis_artifacts.json", {})
    except OSError:
        return False
    return True


# ---- Pause after the English ------------------------------------------------
def _keep_chased_translations(run_dir: Path, english_package: dict, zh_chaser) -> float:
    """When a run stops before its Chinese stage, adopt the chase units
    that already finished (no waiting for the rest) into
    ``logs/memo_package.en.chased.json``, which the resume reads first.
    Returns their cost; never raises."""
    if zh_chaser is None or not getattr(zh_chaser, "has_units", False):
        return 0.0
    try:
        outcome = zh_chaser.collect(join_timeout_sec=0.0)
        merged = json.loads(json.dumps(english_package))
        zh_chaser.merge_into(merged, outcome["units"])
        _write_json(run_dir / "logs" / "memo_package.en.chased.json", merged)
        return _as_float(outcome.get("cost_usd"))
    except Exception:  # noqa: BLE001
        logger.warning("could not keep the chased translations", exc_info=True)
        return 0.0


def _pause_after_english_requested(report_id: str | None) -> bool:
    if not report_id:
        return False
    report = storage.get_report(report_id) or {}
    return bool(report.get("pause_after_english"))


def _pause_run_after_english(
    *,
    report_id: str,
    run_dir: Path,
    english_package: dict,
    memo_paths: dict[str, str],
    stream,
    zh_chaser,
    cost_usd: float,
    worker_duration_ms: int,
    started_at: str,
    started_monotonic: float,
) -> dict:
    """Stop the run after its English memo (I11): keep the chased Chinese
    that already landed for the resume, record the paused state and close
    the stream. The pipeline result says ``paused_after_english`` so no
    caller finalizes."""
    cost_usd += _keep_chased_translations(run_dir, english_package, zh_chaser)
    cost_usd += _shutdown_side_agent(zh_chaser, cancel=True)
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    _update_report(
        report_id,
        status=PAUSED_AFTER_ENGLISH_STATUS,
        stage=ENGLISH_PAUSED_STAGE,
        progress=80,
        error=None,
        failure_phase=None,
        failure_detail=None,
        english_only=None,
        paused_after_english_at=_now_iso(),
        claude_cost_usd=round(cost_usd, 6),
        claude_duration_ms=duration_ms,
    )
    en_path = memo_paths.get("en")
    stream.emit(
        "stage",
        stage="memo_paused_after_english",
        message=ENGLISH_PAUSED_STAGE,
        english_memo=memo_prep._rel(Path(en_path)) if en_path else None,
        paused_after_english=True,
    )
    _emit_phase_timing(
        stream,
        phase="memo_fast_pipeline",
        status="finished",
        started_at=started_at,
        started_monotonic=started_monotonic,
        worker_duration_ms=worker_duration_ms,
        cost_usd=round(cost_usd, 6),
        paused_after_english=True,
    )
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={"en": str(en_path)} if en_path else {},
        english_only=True,
        paused_after_english=True,
        cost_usd=round(cost_usd, 6),
        duration_ms=duration_ms,
    )
    report = storage.get_report(report_id) or {}
    company = storage.get_company(str(report.get("company_id") or "")) or {}
    name = company.get("name") or report.get("company_name") or "Memo"
    _notify_memo(
        report_id,
        "English memo ready — paused",
        f"{name} — review the English memo, then resume to write the Chinese",
    )
    return {
        "ok": True,
        "paused_after_english": True,
        "english_only": True,
        "cost_usd": round(cost_usd, 6),
        "duration_ms": duration_ms,
        "worker_duration_ms": worker_duration_ms,
        "fast_pipeline": True,
    }


# ---- Red team -----------------------------------------------------------------
# One cheap-tier call after the English is accepted that argues against
# the memo's load-bearing claims (claude_runner.run_memo_red_team, I12).
# Its challenges ride the surgical repair as findings; whatever the repair
# did not address ships as a warning (gate "red_team"). Never a hard gate.
RED_TEAM_FLAG = "BSH_MEMO_RED_TEAM"
RED_TEAM_FILENAME = "red_team.json"


def _memo_red_team_enabled() -> bool:
    return claude_runner.memo_red_team_enabled()


def _red_team_challenge_findings(challenges: list[dict]) -> list[str]:
    findings: list[str] = []
    for challenge in challenges:
        section_id = str(challenge.get("section_id") or "").strip()
        claim = re.sub(r"\s+", " ", str(challenge.get("claim") or "")).strip()
        why = re.sub(r"\s+", " ", str(challenge.get("why") or "")).strip()
        if not claim:
            continue
        head = f"section {section_id}: " if section_id else ""
        findings.append(
            f'{head}red-team challenge — "{claim[:200]}" — {why[:300] or "unsupported as written"}'
            "; restate the claim only as far as the cited evidence carries it"
        )
    return findings


def _normalized_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _package_english_text(package: dict) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            en = value.get("en")
            if isinstance(en, str):
                parts.append(en)
            for key, item in value.items():
                if key != "en":
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(package.get("sections"))
    return _normalized_text(" ".join(parts))


def _unresolved_challenges(
    before: dict, after: dict, challenges: list[dict]
) -> list[dict]:
    """A challenge is addressed once the claim it quotes — present in the
    English before the repair — no longer appears after it. A challenge
    whose claim was never quoted verbatim cannot be checked and stays
    open for the reader."""
    before_text = _package_english_text(before)
    after_text = _package_english_text(after)
    open_items: list[dict] = []
    for challenge in challenges:
        claim = _normalized_text(challenge.get("claim"))
        if not claim or claim not in before_text or claim in after_text:
            open_items.append(challenge)
    return open_items


def _run_red_team_pass(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    package: dict,
    attempt: int,
    progress,
    stream,
    report_id: str | None,
    cost_so_far: float,
) -> tuple[dict, float]:
    """The red-team pass on the accepted English package: returns the
    package (repaired where the challenges could be addressed) and the
    pass's own reported cost (its calls also report through ``progress``;
    the caller takes whichever is larger). Does nothing while the switch
    is off; never fails the run."""
    if not _memo_red_team_enabled():
        return package, 0.0
    runner = claude_runner.run_memo_red_team
    if _cost_guard_stop(
        report_id=report_id,
        run_dir=run_dir,
        cost_usd=cost_so_far,
        phase="red-team pass",
        stream=stream,
    ):
        return package, 0.0
    progress.emit(
        "stage",
        stage="memo_red_team",
        message="Red-teaming the accepted English memo's load-bearing claims",
    )
    try:
        result = runner(
            run_dir,
            package,
            role="SPINE_CHECK",
            company_name=company_name,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "stage",
            stage="memo_red_team_failed",
            message="Red-team pass failed; continuing without it",
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
        return package, 0.0
    result = result if isinstance(result, dict) else {}
    challenges = [c for c in result.get("challenges") or [] if isinstance(c, dict)]
    cost = _as_float(result.get("cost_usd"))
    if result.get("error") and not challenges:
        progress.emit(
            "stage",
            stage="memo_red_team_failed",
            message="Red-team pass returned no challenges; continuing without it",
            error=str(result.get("error"))[:500],
            cost_usd=None,
        )
    record: dict[str, Any] = {
        "ran_at": _now_iso(),
        "cost_usd": round(cost, 6),
        "challenges": challenges,
        "repaired": False,
        "unresolved": [],
    }
    if challenges:
        original = package
        repaired = _surgical_quality_repair(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            candidate=package,
            findings=_red_team_challenge_findings(challenges),
            attempt=attempt,
            progress=progress,
            stream=stream,
        )
        if repaired is not None:
            package = repaired
            record["repaired"] = True
        record["unresolved"] = _unresolved_challenges(original, package, challenges)
    try:
        _write_json(run_dir / "logs" / RED_TEAM_FILENAME, record)
    except OSError:
        logger.warning("could not record the red-team pass", exc_info=True)
    progress.emit(
        "stage",
        stage="memo_red_team_finished",
        message=(
            f"Red team raised {len(challenges)} challenge(s); "
            f"{len(record['unresolved'])} left open for the reader"
        ),
        challenges=len(challenges),
        unresolved=len(record["unresolved"]),
        repaired=record["repaired"],
        cost_usd=round(cost, 6),
    )
    return package, cost


def _red_team_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    try:
        payload = json.loads(
            (run_dir / "logs" / RED_TEAM_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return
    unresolved = [
        c for c in (payload.get("unresolved") if isinstance(payload, dict) else None) or []
        if isinstance(c, dict)
    ]
    if not unresolved:
        return
    count = len(unresolved)
    warnings.add(
        f"Red team: {count} challenge{'' if count == 1 else 's'} left open",
        f"红队质疑：{count} 项未解决",
        [
            _warning_item(
                gate="red_team",
                language="EN",
                section=str(c.get("section_id") or "") or None,
                severity=str(c.get("severity") or "warning") or "warning",
                code="red_team_challenge",
                summary_en=(
                    f"{str(c.get('claim') or '')[:160]} — "
                    f"{str(c.get('why') or '')[:200]}"
                ),
                summary_zh="红队质疑未解决：" + str(c.get("claim") or "")[:160],
                detail_path=memo_prep._rel(run_dir / "logs" / RED_TEAM_FILENAME),
            )
            for c in unresolved[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


# ---- Report-only gates from the fact check and the quality metrics -------
PIN_WARNINGS_FILENAME = "pin_warnings.json"


def _pins_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    """The pin check's P1 warnings (a spine fact the memo does not echo
    where it should — base_case_not_echoed) ship as warnings, gate "pins";
    the P0 pin gate itself is unchanged."""
    try:
        payload = json.loads(
            (run_dir / "logs" / PIN_WARNINGS_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return
    findings = [f for f in payload or [] if isinstance(f, dict)] if isinstance(payload, list) else []
    if not findings:
        return
    count = len(findings)
    warnings.add(
        f"Pins: {count} spine fact{'' if count == 1 else 's'} not echoed where expected",
        f"锚定事实：{count} 项未在应出现的位置复述",
        [
            _warning_item(
                gate="pins",
                language="EN",
                section=str(f.get("location") or "").split(" ", 1)[0] or None,
                severity="warning",
                code=str(f.get("code") or "pin_warning"),
                summary_en=(
                    f"{f.get('code')}: {str(f.get('pin') or '')[:120]} — "
                    f"{str(f.get('detail') or '')[:200]}"
                ),
                summary_zh="锚定事实未复述：" + str(f.get("pin") or "")[:120],
                detail_path=memo_prep._rel(run_dir / "logs" / "pin_check.md"),
            )
            for f in findings[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _claims_warning(
    run_dir: Path, warnings: "_RunWarnings", company_id: str | None = None
) -> None:
    """Evidence quotes the passes recorded that the cached source text does
    not contain (memo_fact_check.check_quotes, I6) — gate "claims"."""
    from . import memo_fact_check

    check = getattr(memo_fact_check, "check_quotes", None)
    if not callable(check):
        return
    try:
        result = check(run_dir, company_id=company_id)
    except Exception:  # noqa: BLE001
        logger.warning("quote check failed", exc_info=True)
        return
    unmatched = [
        u for u in ((result or {}).get("unmatched") if isinstance(result, dict) else None) or []
    ]
    if not unmatched:
        return
    count = len(unmatched)
    items: list[dict] = []
    for entry in unmatched[:_MAX_WARNING_ITEMS_PER_GATE]:
        entry = entry if isinstance(entry, dict) else {"quote": str(entry)}
        quote = re.sub(r"\s+", " ", str(entry.get("quote") or "")).strip()
        url = str(entry.get("url") or "").strip()
        items.append(
            _warning_item(
                gate="claims",
                language="EN",
                severity="warning",
                code="quote_unmatched",
                summary_en=f'Quote not found in the cached source: "{quote[:140]}"'
                + (f" ({url[:120]})" if url else ""),
                summary_zh=f"引文未在缓存来源中找到：“{quote[:140]}”",
                detail_path=memo_prep._rel(run_dir / "logs" / "evidence_quotes.json"),
            )
        )
    warnings.add(
        f"Claims: {count} evidence quote{'' if count == 1 else 's'} not found in the cached sources",
        f"引证：{count} 条引文未在缓存来源中找到",
        items,
    )


def _fact_check_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    """What the final fact check (``_final_fact_check``) found in the
    delivered memo, gate "fact_check": calculation inputs that were cited
    to a source that does not carry them (now shown as our assumptions), and
    headline figures — executive summary, key metrics, recommendation — that
    no source on file carries. Until now a run whose executive summary
    rested on untraced numbers shipped with no warning saying so."""
    from . import memo_fact_check

    logs_dir = run_dir / "logs"
    try:
        relabelled = json.loads(
            (logs_dir / memo_fact_check.CALCULATION_INPUTS_FILENAME).read_text(encoding="utf-8")
        ).get("relabelled") or []
    except (OSError, ValueError, AttributeError):
        relabelled = []
    relabelled = [r for r in relabelled if isinstance(r, dict)]
    if relabelled:
        count = len(relabelled)
        warnings.add(
            f"Calculations: {count} input{'' if count == 1 else 's'} cited to a source that "
            "does not carry the figure — shown as our assumption",
            f"计算说明：{count} 项输入所引来源并未载明该数字——已改标为我们的假设",
            [
                _warning_item(
                    gate="fact_check",
                    language="EN",
                    section="calculations",
                    code="calculation_input_unsourced",
                    summary_en=(
                        f"{r.get('calc_id')}: {str(r.get('name') or '')[:80]} = "
                        f"{str(r.get('value') or '')[:60]} was cited to {r.get('ref')}, "
                        "and no source on file carries it"
                    ),
                    summary_zh=(
                        f"{r.get('calc_id')}：{str(r.get('name') or '')[:80]} = "
                        f"{str(r.get('value') or '')[:60]}，所引 {r.get('ref')} 及任何在档来源均未载明"
                    ),
                    detail_path=memo_prep._rel(logs_dir / memo_fact_check.CALCULATION_INPUTS_FILENAME),
                )
                for r in relabelled[:_MAX_WARNING_ITEMS_PER_GATE]
            ],
        )
    payload = _fact_check_payload(run_dir)
    if not isinstance(payload, dict) or payload.get("error"):
        return
    comparisons = [f for f in payload.get("comparison_findings") or [] if isinstance(f, dict)]
    if comparisons:
        _add_comparison_warning(
            warnings,
            [(str(f.get("section_id") or "") or None, str(f.get("snippet") or ""), str(f.get("suggestion") or "")) for f in comparisons],
            detail_path=memo_prep._rel(logs_dir / "fact_check.md"),
            where_en="the memo",
            where_zh="备忘录",
            total=payload.get("comparison_count") if isinstance(payload.get("comparison_count"), int) else None,
        )
    if payload.get("thin_corpus"):
        return
    count = payload.get("unsupported_headline")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        return
    findings = [f for f in payload.get("headline_findings") or [] if isinstance(f, dict)]
    warnings.add(
        f"Fact check: {count} figure{'' if count == 1 else 's'} in the executive summary, "
        "key metrics or recommendation not found in any source on file",
        f"事实核查：执行摘要、关键指标或投资建议中有 {count} 个数字未在任何在档来源中找到",
        [
            _warning_item(
                gate="fact_check",
                language="EN",
                section=str(f.get("section_id") or "") or None,
                code="headline_figure_untraced",
                summary_en=f"{f.get('figure')}: {str(f.get('snippet') or '')[:200]}",
                summary_zh=f"{f.get('figure')}：未在任何在档来源中找到",
                detail_path=memo_prep._rel(logs_dir / "fact_check.md"),
            )
            for f in findings[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _add_comparison_warning(
    warnings: "_RunWarnings",
    rows: list[tuple[str | None, str, str]],
    *,
    detail_path: str | None,
    where_en: str,
    where_zh: str,
    total: int | None = None,
) -> None:
    # ``rows`` may be a cut list (the report keeps 20); ``total`` is the count.
    count = max(len(rows), total or 0)
    warnings.add(
        f"Arithmetic: {count} comparison{'' if count == 1 else 's'} in {where_en} "
        "contradicted by its own figures",
        f"算术：{where_zh}中有 {count} 处比较与其自身数字相矛盾",
        [
            _warning_item(
                gate="fact_check",
                language="EN",
                section=section,
                code="comparison_error",
                summary_en=f"{detail.split(';')[0]} — \"{snippet[:180]}\"",
                summary_zh=f"比较方向与数字不符：{detail.split(';')[0]}",
                detail_path=detail_path,
            )
            for section, snippet, detail in rows[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _ic_comparison_warning(md_path: Path | None, warnings: "_RunWarnings") -> None:
    """The IC decision memo has no repair loop, so a comparison its own
    figures contradict (ZaiNar 2026-09-23: "about $597M — still below …
    $579.37M") is reported, gate "fact_check"."""
    from . import memo_fact_check

    if md_path is None:
        return
    try:
        text = Path(md_path).read_text(encoding="utf-8")
    except OSError:
        return
    rows = [
        (None, error["snippet"], error["detail"])
        for line in text.splitlines()
        for error in memo_fact_check.comparison_errors(line)
    ]
    if rows:
        _add_comparison_warning(
            warnings,
            rows,
            detail_path=memo_prep._rel(Path(md_path)),
            where_en="the IC decision memo",
            where_zh="投委会决策备忘录",
        )


def _consistency_warning(
    run_dir: Path, warnings: "_RunWarnings", package: dict | None = None
) -> None:
    """The same metric stated with different values in different places
    (memo_fact_check.metric_conflicts, I7) — gate "consistency"."""
    from . import memo_fact_check

    conflicts_fn = getattr(memo_fact_check, "metric_conflicts", None)
    if not callable(conflicts_fn):
        return
    package = package if isinstance(package, dict) else _delivered_package(run_dir)
    if not isinstance(package, dict):
        return
    try:
        conflicts = conflicts_fn(package)
    except Exception:  # noqa: BLE001
        logger.warning("metric conflict check failed", exc_info=True)
        return
    conflicts = [c for c in conflicts or [] if isinstance(c, dict)]
    if not conflicts:
        return
    count = len(conflicts)
    warnings.add(
        f"Consistency: {count} metric{'' if count == 1 else 's'} stated with conflicting values",
        f"一致性：{count} 项指标在不同位置数值不一致",
        [
            _warning_item(
                gate="consistency",
                language="EN",
                severity="warning",
                code="metric_conflict",
                summary_en=(
                    f"{c.get('metric')}: "
                    + ", ".join(str(v) for v in (c.get("values") or [])[:6])
                    + (
                        " (" + ", ".join(str(loc) for loc in (c.get("locations") or [])[:4]) + ")"
                        if c.get("locations")
                        else ""
                    )
                )[:300],
                summary_zh=f"{c.get('metric')}：数值不一致（"
                + "、".join(str(v) for v in (c.get("values") or [])[:6])
                + "）",
            )
            for c in conflicts[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _quality_metrics(run_dir: Path, package: dict | None, report: dict | None) -> dict | None:
    """memo_quality_metrics.compute (I10), written to
    ``logs/quality_metrics.json`` and returned for the record. None until
    the module exists or when it fails; never raises."""
    try:
        import importlib

        module = importlib.import_module("server.memo_quality_metrics")
    except Exception:  # noqa: BLE001
        return None
    compute = getattr(module, "compute", None)
    if not callable(compute):
        return None
    package = package if isinstance(package, dict) else _delivered_package(run_dir)
    try:
        metrics = compute(run_dir, package, report or {})
    except Exception:  # noqa: BLE001
        logger.warning("quality metrics failed", exc_info=True)
        return None
    if not isinstance(metrics, dict):
        return None
    try:
        _write_json(run_dir / "logs" / "quality_metrics.json", metrics)
    except (OSError, TypeError, ValueError):
        logger.warning("could not write the quality metrics", exc_info=True)
    return metrics


def _memo_package_render_validation_error(
    package_path: Path,
    *,
    allow_zh_fallback: bool = False,
) -> str | None:
    if not package_path.exists():
        return None
    try:
        memo_docx_renderer.load_package(package_path)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        # Before reporting failure, try the conservative deterministic
        # repair (missing callout titles, plain strings in bilingual slots,
        # analysis-pass source vocabulary). Persist the repaired package
        # only when it fully clears validation, so every caller of this
        # gate — phase 4 merge, resume, finalize — self-heals mechanical
        # defects instead of burning a regeneration round.
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return error
        repaired, repairs = memo_docx_renderer.repair_package_structure(payload)
        repairs = list(repairs)
        if allow_zh_fallback:
            # Last resort only, and only for the caller that has already run
            # the monolithic Chinese repair: re-translation had its turn.
            repairs += _fill_sparse_zh_gaps(repaired)
        if not repairs:
            return error
        try:
            memo_docx_renderer.validate_package(repaired)
        except Exception:  # noqa: BLE001
            return error
        _write_json(package_path, repaired)
        logger.info(
            "memo package %s auto-repaired: %s",
            package_path,
            "; ".join(repairs[:10]),
        )
        return None
    return None


_PLACEHOLDER_THESIS_NAMES = frozenset({"t", "x", "test", "tmp", "todo", "placeholder", "name"})


def prior_view_for_report(report: dict) -> dict | None:
    """BSH's most recent delivered memo of the same kind on the same
    company before this run — its verdict, score, entry mark and date — as
    the sentence the pipeline pins (``sentence``), plus the recommendation
    the spine prompt quotes. None for a company's first memo, or when no
    earlier run left a v2 verdict to state (a v1 memo, a Buffett memo).
    The previous memo's evidence never travels: a verdict is history, a
    figure would be contamination."""
    company_id = str(report.get("company_id") or "").strip()
    if not company_id:
        return None
    from . import memo_diff, report_reader

    def moment(value: Any) -> datetime | None:
        # Compared as instants: "…+00:00" and "…Z" stamps do not sort as text.
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    this_id = str(report.get("id") or "")
    created = moment(report.get("created_at")) if report.get("created_at") else None
    for candidate in storage.list_reports_for(company_id):  # newest first
        if str(candidate.get("id") or "") == this_id:
            continue
        if candidate.get("kind") != report.get("kind"):
            continue
        if not memo_diff.version_eligible(candidate):
            continue
        if created is not None:
            when = moment(candidate.get("created_at"))
            if when is None or when >= created:
                continue
        facts = report_reader.load_spine_facts(candidate)
        if not facts:
            continue
        verdict = str(facts.get("verdict") or "").strip()
        if not verdict:
            continue
        scorecard = facts.get("scorecard")
        total = scorecard.get("total") if isinstance(scorecard, dict) else None
        entry = facts.get("entry")
        entry_text = (
            str(entry.get("valuation") or "").strip() if isinstance(entry, dict) else ""
        )
        date = str(candidate.get("created_at") or "")[:10]
        name = str(report.get("company_name") or company_id).strip()
        head = f"BSH's previous memo on {name} ({date}) concluded {verdict}"
        if isinstance(total, int) and not isinstance(total, bool):
            head += f" — {total}/100"
        # The pin's schema caps the sentence; one that would not fit is
        # shortened here (the entry mark goes first), never silently left
        # unpinned while the prompt says it is pinned.
        sentence = f"{head} at {entry_text}." if entry_text else f"{head}."
        limit = int(claude_runner.MEMO_PRIOR_VIEW_SCHEMA["maxLength"])
        if len(sentence) > limit:
            sentence = f"{head}."
        if len(sentence) > limit:
            return None
        return {
            "sentence": sentence,
            "recommendation": str(facts.get("recommendation_sentence") or "").strip(),
            "report_id": str(candidate.get("id") or ""),
            "date": date,
            "verdict": verdict,
        }
    return None


def _register_prior_view(report: dict, run_dir: Path) -> None:
    """Pin BSH's previous view for the run (``BSH_MEMO_PRIOR_VIEW=0``
    disables it). Best-effort: a lookup failure means no prior view, never
    a failed run."""
    prior = None
    if os.environ.get("BSH_MEMO_PRIOR_VIEW", "1") == "1":
        try:
            prior = prior_view_for_report(report)
        except Exception:  # noqa: BLE001
            logger.warning("prior view lookup failed", exc_info=True)
    claude_runner.register_memo_run_prior_view(run_dir, prior)


def _check_size_text() -> str | None:
    """BSH's check size for a deal, as one sentence for the spine — only
    when the owner set a real band in the thesis settings. The thesis file
    on the machines today looks auto-written ("name: t"), so a placeholder
    name, a missing save date or an inverted band count as unset."""
    try:
        from . import thesis_store

        thesis = thesis_store.get_thesis()
    except Exception:  # noqa: BLE001
        return None
    low = thesis.get("check_size_min_musd")
    high = thesis.get("check_size_max_musd")
    name = str(thesis.get("name") or "").strip().lower()
    if not thesis.get("updated_at") or len(name) < 3 or name in _PLACEHOLDER_THESIS_NAMES:
        return None
    if not isinstance(low, (int, float)) and not isinstance(high, (int, float)):
        return None
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        if low <= 0 or high <= 0 or low > high:
            return None
        band = f"US${low:g}–{high:g} million"
    else:
        value = low if isinstance(low, (int, float)) else high
        if value <= 0:
            return None
        band = f"US${value:g} million"
    return (
        f"BSH's check size for a deal like this is {band} (the firm's thesis "
        "settings)."
    )


def _spine_pinned_values(shared_facts: dict | None) -> list[str]:
    """The figures and sentences the spine pinned — the recommendation, key
    metric values, scenario strings, fair value, entry, hurdle — which the
    lint's repetition check must not count (sections echo pins verbatim by
    design)."""
    values: list[str] = []
    if not isinstance(shared_facts, dict):
        return values

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    for key in ("recommendation_sentence", "decision_history_sentence", "return_hurdle"):
        add(shared_facts.get(key))
    for metric in shared_facts.get("key_metrics") or []:
        if isinstance(metric, dict):
            add(metric.get("value"))
    scenarios = shared_facts.get("scenarios")
    if isinstance(scenarios, dict):
        for scenario in scenarios.values():
            if isinstance(scenario, dict):
                for key in ("exit_value", "exit_revenue", "exit_multiple", "moic", "irr"):
                    add(scenario.get(key))
            else:
                add(scenario)
    fair_value = shared_facts.get("fair_value_range")
    if isinstance(fair_value, dict):
        add(fair_value.get("low"))
        add(fair_value.get("high"))
    entry = shared_facts.get("entry")
    if isinstance(entry, dict):
        add(entry.get("valuation"))
    return values


def _hurdle_moic(run_dir: Path | None, structure=None) -> float | None:
    """The firm's target MOIC for the run's stage, when the owner saved one."""
    try:
        from . import fund_policy

        stage = getattr(structure, "declared_stage", None) or (
            _structure_for_run(run_dir).declared_stage if run_dir is not None else "late"
        )
        entry = fund_policy.stage_policy(stage)
    except Exception:  # noqa: BLE001
        return None
    value = (entry or {}).get("target_moic")
    return float(value) if isinstance(value, (int, float)) else None


def _lint_context(run_dir: Path | None, structure=None) -> dict:
    """The run facts the quality lint's P1/P2 checks need (all optional):
    whether BSH's check size was supplied, whether deal terms are on file,
    the stage's hurdle MOIC and the spine's pinned values."""
    if run_dir is None:
        return {}
    context: dict[str, Any] = {
        "sizing_supplied": bool(claude_runner.memo_run_check_size(run_dir) or _check_size_text()),
    }
    inputs = _run_inputs(run_dir)
    if "deal_terms_on_file" in inputs:
        context["deal_terms_on_file"] = bool(inputs["deal_terms_on_file"])
    hurdle = _hurdle_moic(run_dir, structure)
    if hurdle is not None:
        context["hurdle_moic"] = hurdle
    pinned = _spine_pinned_values(_memo_shared_facts_from_disk(run_dir))
    if pinned:
        context["pinned_values"] = pinned
    return context


def _lint_memo(path: Path, structure, run_dir: Path | None = None):
    """``memo_quality_lint.lint_memo_docx`` with the run's facts."""
    return memo_quality_lint.lint_memo_docx(path, structure, **_lint_context(run_dir, structure))


def _memo_package_prerender_quality_findings(
    package: dict | Path,
    *,
    check_parity: bool = True,
    run_dir: Path | None = None,
) -> list[str]:
    """Render a package to a throwaway dir and run the finalize-time quality
    gates on it, so blocking findings feed the generation retry loop instead
    of surfacing after the run declares success (each post-render miss costs
    a full regeneration round). Applies the same deterministic voice rewrites
    finalize applies, so this can't flag text finalize would have fixed.

    Returns the list of finding summaries, empty when the gates pass. A
    failure of the check itself is returned as one finding. Rendering is
    local and takes about a second, so this is cheap relative to one Claude
    generation pass.
    """
    import tempfile

    try:
        if isinstance(package, Path):
            payload = json.loads(package.read_text(encoding="utf-8"))
        else:
            payload = package
        payload, _ = _rewritten_memo_package_voice(payload)
        structure = memo_structure.for_package(payload)
        with tempfile.TemporaryDirectory(prefix="memo-prelint-") as tmp:
            tmp_dir = Path(tmp)
            out_en = tmp_dir / "memo" / "prelint_en.docx"
            out_zh = tmp_dir / "memo" / "prelint_zh.docx"
            memo_docx_renderer.render_memos(
                payload,
                out_en=out_en,
                out_zh=out_zh,
                validation_en=tmp_dir / "logs" / "validation.txt",
                validation_zh=tmp_dir / "logs" / "validation_cn.txt",
                inventory_path=tmp_dir / "logs" / "file_inventory.md",
                manifest_path=tmp_dir / "logs" / "run_manifest.md",
            )
            problems: list[str] = []
            lint_result = _lint_memo(out_en, structure, run_dir)
            for finding in lint_result.p0_findings[:12]:
                problems.append(
                    f"quality gate {finding.code} at {finding.location}: "
                    f"\"{finding.snippet}\" — {finding.suggestion}"
                )
            if check_parity:
                parity_result = memo_chinese_parity.lint_chinese_memo_pair(
                    out_en,
                    out_zh,
                    structure,
                    package=payload,
                    run_dir=run_dir,
                )
                for finding in parity_result.p0_findings[:12]:
                    problems.append(
                        f"Chinese parity gate {finding.code} at "
                        f"{finding.location}: \"{finding.snippet}\" — "
                        f"{finding.suggestion}"
                    )
            return problems
    except Exception as exc:  # noqa: BLE001
        return [f"pre-render quality check failed: {type(exc).__name__}: {exc}"]


def _memo_package_prerender_quality_error(
    package: dict | Path,
    *,
    check_parity: bool = True,
    run_dir: Path | None = None,
) -> str | None:
    """Joined-string form of ``_memo_package_prerender_quality_findings``."""
    problems = _memo_package_prerender_quality_findings(
        package, check_parity=check_parity, run_dir=run_dir
    )
    return "; ".join(problems) if problems else None


def _report_structure_version(report: dict | None) -> str | None:
    """The memo template the run was started with ("v1" | "v2"), or None
    for records that predate the choice (they follow the env flag)."""
    value = str((report or {}).get("structure_version") or "").strip().lower()
    return value if value in ("v1", "v2") else None


def _report_structure(report: dict) -> memo_structure.MemoStructure:
    """The structure a report's run writes, from what the record pinned:
    the classified stage, the compact/full mode, the company type and the
    template version. Resume uses it so a v2 run is never regenerated as v1
    (and the reverse)."""
    stage_info = report.get("structure_stage")
    stage = (
        str(stage_info.get("stage") or "late")
        if isinstance(stage_info, dict)
        else "late"
    )
    type_info = report.get("company_type")
    company_type = (
        str(type_info.get("type") or "") or None
        if isinstance(type_info, dict)
        else None
    )
    return memo_structure.active_structure(
        stage,
        str(report.get("structure_mode") or "full"),
        company_type,
        version=_report_structure_version(report),
    )


def _structure_is_v1(structure: memo_structure.MemoStructure) -> bool:
    return structure.meta() == memo_structure.LATE.meta()


def _register_run_structure(
    run_dir: Path, structure: memo_structure.MemoStructure
) -> None:
    """Pin the run's template on the subprocess funnel: a v2-family
    structure has no monolithic English twin, so it always takes the
    parallel wave (``claude_runner._memo_english_parallel_enabled``)."""
    try:
        claude_runner.register_memo_run_structure_version(
            run_dir, "v1" if _structure_is_v1(structure) else "v2"
        )
    except Exception:  # noqa: BLE001 — a registry fault never fails a run
        logger.warning("structure version pin failed", exc_info=True)


def _english_package_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "memo_package.en.json"


def _zh_partial_package_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "memo_package.zh_partial.json"


def _structure_for_run(run_dir: Path) -> memo_structure.MemoStructure:
    """Resolve the structure the run's accepted package was written
    against (from the meta stamp in ``memo_package.json``, else the
    accepted English package — an English-only delivery has no bilingual
    package); late v1 for legacy runs and unreadable packages."""
    for path in (_memo_package_path(run_dir), _english_package_path(run_dir)):
        try:
            package = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(package, dict):
            return memo_structure.for_package(package)
    return memo_structure.LATE


def _memo_shared_facts_from_disk(run_dir: Path) -> dict | None:
    """The spine's pinned shared facts, when the parallel path wrote them."""
    spine_path = run_dir / "logs" / "english_units" / "spine.json"
    if not spine_path.exists():
        return None
    try:
        shared_facts = json.loads(
            spine_path.read_text(encoding="utf-8")
        ).get("shared_facts")
    except Exception:  # noqa: BLE001
        return None
    return shared_facts if isinstance(shared_facts, dict) else None


def _run_memo_pin_check(
    *,
    run_dir: Path,
    candidate: dict,
    progress,
    attempt: int | None = None,
) -> list[str]:
    """Deterministically verify the candidate echoes the spine's pins.

    Writes ``logs/pin_check.md`` and emits one stage event either way;
    returns the finding feedback lines (the caller feeds them to repair
    only when BSH_MEMO_PIN_CHECK_REPAIR is on). Never raises — the checker
    must not be able to sink a run.
    """
    if not _memo_pin_check_enabled():
        return []
    shared_facts = _memo_shared_facts_from_disk(run_dir)
    if not shared_facts or not isinstance(candidate, dict):
        return []
    try:
        result = memo_pin_check.check_package_pins(candidate, shared_facts)
        report_path = run_dir / "logs" / "pin_check.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            memo_pin_check.render_markdown_report(result, attempt=attempt),
            encoding="utf-8",
        )
        # The P1 pin warnings (base_case_not_echoed …) are recorded for
        # finalize (gate "pins"), never fed to the repair or the gate.
        pin_warnings = [
            finding.to_dict() if hasattr(finding, "to_dict") else dict(finding)
            for finding in (getattr(result, "warnings", None) or [])
        ]
        try:
            _write_json(run_dir / "logs" / PIN_WARNINGS_FILENAME, pin_warnings)
        except OSError:
            logger.warning("could not record the pin warnings", exc_info=True)
        progress.emit(
            "stage",
            stage="memo_pin_check",
            message=(
                f"Pin-echo check: {result.pins_checked} pins checked, "
                f"{len(result.findings)} finding(s)"
                + (f", {len(pin_warnings)} warning(s)" if pin_warnings else "")
            ),
            pins_checked=result.pins_checked,
            pins_skipped=result.pins_skipped,
            findings=[finding.to_dict() for finding in result.findings][:8],
            warnings=pin_warnings[:8],
            repair_feed=_memo_pin_check_repair_enabled(),
            attempt=attempt,
        )
        return result.summary_lines()
    except Exception:  # noqa: BLE001
        logger.warning("memo pin check failed", exc_info=True)
        return []


def _memo_fact_check_enabled() -> bool:
    return _env_flag("BSH_MEMO_FACT_CHECK", default=True)


def _run_memo_fact_check(
    *,
    run_dir: Path,
    candidate: dict,
    company_id: str,
    research_dir: Path | None,
    progress,
    attempt: int | None = None,
    session_dir: Path | None = None,
) -> list[str]:
    """Deterministically trace every figure in the candidate to a source on
    file (``memo_fact_check``).

    Writes ``logs/fact_check.md`` and ``logs/fact_check.json`` and emits one
    stage event either way; returns the repair feedback lines, which are
    empty unless the corpus is rich enough for enforcement (see
    ``BSH_MEMO_FACT_CHECK_REPAIR``). Never raises — like the pin check, the
    checker must not be able to sink a run.
    """
    if not _memo_fact_check_enabled() or not isinstance(candidate, dict):
        return []
    try:
        from . import memo_fact_check

        result = memo_fact_check.check_memo_run(
            run_dir=run_dir,
            package=candidate,
            company_id=company_id,
            research_dir=research_dir,
            session_dir=session_dir,
        )
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "fact_check.md").write_text(
            memo_fact_check.render_markdown_report(result, attempt=attempt),
            encoding="utf-8",
        )
        _write_json(logs_dir / "fact_check.json", result.to_dict())
        coverage = (
            f"{result.coverage_pct}% traceable"
            if result.coverage_pct is not None
            else "no figures"
        )
        progress.emit(
            "stage",
            stage="memo_fact_check",
            message=(
                f"Fact check: {result.checked} figures, {result.unsupported} "
                f"unsupported ({coverage}); "
                + ("enforced via repair" if result.repair_feed else "report only")
                + (f" — {result.error}" if result.error else "")
            ),
            checked=result.checked,
            verified=result.verified,
            supported=result.supported,
            derived=result.derived,
            unsupported=result.unsupported,
            coverage_pct=result.coverage_pct,
            evidence_chars=result.evidence_chars,
            thin_corpus=result.thin_corpus,
            repair_feed=result.repair_feed,
            repair_feed_reason=result.repair_feed_reason,
            findings=[f.to_dict() for f in result.findings][:8],
            attempt=attempt,
        )
        return result.summary_lines()
    except Exception:  # noqa: BLE001
        logger.warning("memo fact check failed", exc_info=True)
        return []


# The run's private inventory ({id, kind, title, ref} per item the run may
# read) is stamped REPORT-ONLY, under a key the renderer's source gate does
# not read. The gate tightens once run.private_inventory is present — a
# URL-less private-class source must then name an inventory item by its
# exact title or private_ref — and no writer prompt tells the model to cite
# private documents that way yet, so stamping it would fail live runs on
# citations the private_material_on_file rule accepts today. Switch to
# memo_fact_check.stamp_private_inventory together with that prompt text.
PRIVATE_ITEMS_KEY = "private_items_on_file"


def _stamp_private_items_on_file(package: dict, inventory: list[dict]) -> list[dict]:
    from . import memo_fact_check

    # Normalised exactly as stamp_private_inventory would, on a scratch
    # envelope so the gated key never reaches the package.
    rows = memo_fact_check.stamp_private_inventory({}, inventory)
    run = package.get("run")
    if not isinstance(run, dict):
        run = {}
        package["run"] = run
    run[PRIVATE_ITEMS_KEY] = rows
    run.pop("private_inventory", None)
    return rows


def _private_items_on_file(package: dict | None) -> list | None:
    """The stamped inventory (None when the run never stamped one)."""
    run = package.get("run") if isinstance(package, dict) else None
    if not isinstance(run, dict):
        return None
    for key in (PRIVATE_ITEMS_KEY, "private_inventory"):
        value = run.get(key)
        if isinstance(value, list):
            return value
    return None


def _attach_memo_source_urls(
    *,
    run_dir: Path,
    candidate: dict,
    company_id: str,
    progress,
    attempt: int | None = None,
    session_dir: Path | None = None,
) -> list[str]:
    """Fill in source URLs the analysis passes, earlier retrievals or the
    Memo Studio session already recorded, before the renderer's URL rule
    judges the envelope. The URL status (seen, unseen, reused homepages) is
    appended to ``logs/source_urls.md`` by memo_fact_check; never raises."""
    if not isinstance(candidate, dict):
        return []
    try:
        from . import memo_fact_check

        # Before the URL rule judges the envelope: whether any source here
        # can honestly be private, and WHICH private items the run holds.
        # Stamped every attempt, because an envelope repair can rewrite
        # `run`.
        memo_fact_check.stamp_private_material(candidate, company_id=company_id)
        _stamp_private_items_on_file(
            candidate,
            memo_fact_check.private_inventory(
                run_dir,
                storage.get_company(company_id) or company_id,
                extra_items=_staged_private_items(run_dir),
            ),
        )
    except Exception:  # noqa: BLE001
        logger.warning("private-material stamp failed", exc_info=True)
    try:
        from . import memo_fact_check

        notes = memo_fact_check.attach_source_urls(
            candidate,
            company_id=company_id,
            run_dir=run_dir,
            session_dir=session_dir,
            attempt=attempt,
        )
    except Exception:  # noqa: BLE001
        logger.warning("source URL attachment failed", exc_info=True)
        return []
    if not notes:
        return []
    progress.emit(
        "stage",
        stage="memo_source_urls_attached",
        message=(
            f"Attached {len(notes)} source URL(s) recorded by the analysis "
            "passes and earlier retrievals"
        ),
        attachments=notes[:20],
        attempt=attempt,
    )
    return notes


def _staged_private_items(run_dir: Path | None) -> list[dict]:
    """Private items the pipeline staged for this run itself (the reference
    call and founder-update digests), as private-inventory rows. Read from
    ``logs/staged_private_items.json`` (written when the digests are
    staged); empty when nothing was."""
    if run_dir is None:
        return []
    try:
        rows = json.loads(
            (run_dir / "logs" / "staged_private_items.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _fact_check_payload(run_dir: Path | None) -> dict | None:
    """The last fact-check result written for the run, for the report record."""
    if run_dir is None:
        return None
    path = Path(run_dir) / "logs" / "fact_check.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _surgical_quality_repair(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    candidate: dict,
    findings: list[str],
    attempt: int,
    progress,
    stream=None,
) -> dict | None:
    """Fix quality-gate findings on a structurally valid candidate with the
    ~2-minute surgical repair pass instead of a 10-18 minute full
    regeneration.

    Quality findings are localized string defects (an em dash, a banned
    phrase, an untreated disclosure cell) — exactly what the repair pass is
    built for. With BSH_MEMO_SECTIONAL_REPAIR=1 the findings are first
    grouped by owning section and repaired per-section in parallel (each
    repair re-emits one section instead of the whole ~50-80KB package —
    the re-emission is most of the observed ~8-minute rounds); any
    unmappable finding or per-section failure falls back to the
    whole-package repair. Returns the repaired package only when it passes
    BOTH structural validation and a re-run of the quality gates; any other
    outcome returns None and the caller falls back to the normal
    full-regeneration retry, so this can only save time, never lose
    correctness.
    """
    input_path = (
        run_dir / "logs" / f"memo_package.en.quality-repair.attempt-{attempt}.json"
    )
    _write_json(input_path, candidate)
    progress.emit(
        "stage",
        stage="memo_quality_surgical_repair",
        message=(
            f"Quality gate flagged {len(findings)} finding(s); trying a "
            "surgical repair pass before regenerating the package"
        ),
        findings=findings[:10],
        attempt=attempt,
    )
    repaired: dict | None = None
    if claude_runner._memo_sectional_repair_enabled():
        sectional, sectional_reason = (
            claude_runner.run_memo_package_sectional_repair(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                package=candidate,
                findings=findings,
                progress=progress,
                stream=stream,
                attempt=attempt,
            )
        )
        if isinstance(sectional, dict):
            repaired = sectional
            progress.emit(
                "stage",
                stage="memo_quality_sectional_repair_succeeded",
                message=(
                    "Sectional repair returned repaired sections; "
                    "re-running the acceptance gates"
                ),
                attempt=attempt,
            )
        else:
            progress.emit(
                "stage",
                stage="memo_quality_sectional_repair_fallback",
                message=(
                    "Sectional repair unavailable "
                    f"({str(sectional_reason)[:300]}); running the "
                    "whole-package repair pass"
                ),
                attempt=attempt,
            )
    if repaired is None:
        repair_result, repair_error = (
            claude_runner.run_memo_package_structure_repair(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                package_path=input_path,
                validation_errors=findings,
                progress=progress,
            )
        )
        repaired = (
            repair_result.get("memo_package")
            if not repair_error and isinstance(repair_result, dict)
            else None
        )
        if not isinstance(repaired, dict):
            progress.emit(
                "stage",
                stage="memo_quality_surgical_repair_failed",
                message=(
                    "Surgical quality repair pass failed; regenerating instead"
                ),
                error=str(repair_error or "no package returned")[:2000],
                attempt=attempt,
            )
            return None
    repaired, _ = memo_docx_renderer.repair_package_structure(repaired)
    # Risk-card WORDING left after the repair is not a reason to throw the
    # repair away: it ships as a warning (_risk_card_warning), never a
    # regeneration. Nor is a small word-cap overrun (_length_warning).
    structural_errors = _blocking_validation_errors(
        memo_docx_renderer.english_package_validation_errors(
            repaired, editorial_risk_checks=False
        ),
        repaired,
    )
    remaining = (
        structural_errors
        or _memo_package_prerender_quality_findings(
            memo_docx_renderer.fill_blank_zh_placeholders(repaired),
            check_parity=False,
            run_dir=run_dir,
        )
    )
    if not remaining and _memo_pin_check_repair_enabled():
        # When pin findings feed the repair, the repaired package must also
        # clear the pin check before it is accepted.
        shared_facts = _memo_shared_facts_from_disk(run_dir)
        if shared_facts:
            try:
                remaining = memo_pin_check.check_package_pins(
                    repaired, shared_facts
                ).summary_lines()
            except Exception:  # noqa: BLE001
                logger.warning("post-repair pin check failed", exc_info=True)
    if remaining:
        progress.emit(
            "stage",
            stage="memo_quality_surgical_repair_failed",
            message=(
                "Surgical quality repair did not clear validation; "
                "regenerating instead"
            ),
            validation_errors=remaining[:10],
            attempt=attempt,
        )
        return None
    progress.emit(
        "stage",
        stage="memo_quality_surgical_repair_succeeded",
        message="Surgical repair cleared the quality findings",
        attempt=attempt,
    )
    return repaired


def _archive_memo_package(package_path: Path, *, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = package_path.with_name(f"memo_package.{label}.{stamp}.json")
    package_path.replace(archive_path)
    return archive_path


def _archive_invalid_memo_package(package_path: Path) -> Path:
    return _archive_memo_package(package_path, label="invalid")


def _opens_sentence(match: re.Match) -> bool:
    before = match.string[: match.start()].rstrip()
    return not before or before[-1] in ".!?\n"


def _sentence_case(match: re.Match, replacement: str) -> str:
    """``replacement`` capitalised where the match opens a sentence."""
    if _opens_sentence(match):
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _pass_rewrite(match: re.Match) -> str:
    """ "we do not recommend participating (in X)" → "Recommendation: pass
    on X" where it opens a sentence ("the recommendation passes on X"
    mid-sentence)."""
    target = (match.group(1) or "").strip()
    if _opens_sentence(match):
        return f"Recommendation: pass on {target}" if target else "Recommendation: pass"
    return f"the recommendation passes on {target}" if target else "the recommendation passes"


def _commit_capital_rewrite(match: re.Match) -> str:
    """ "we recommend participating (in)" → the house recommendation form:
    "Recommendation: BSH commits capital (to)" where it opens a sentence,
    "the recommendation commits capital (to)" mid-sentence — neither is the
    lint's banned "the recommendation is…"."""
    target = " to" if match.group(1) else ""
    if _opens_sentence(match):
        return f"Recommendation: BSH commits capital{target}"
    return f"the recommendation commits capital{target}"


_MEMO_PACKAGE_VOICE_REWRITES: tuple[tuple[re.Pattern[str], Any], ...] = (
    (
        re.compile(r"\bWhat Must Be Confirmed Before Funding\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bWhat Must Be Confirmed\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bClosing Confirmations?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bClosing Confirmation Bars?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bConfirmation Items?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bExpected Bars?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bValuation Sensitivity Bars?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bInvestment Conditions?\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bStop or Revisit Conditions?\b", re.IGNORECASE),
        "Downside Sensitivities",
    ),
    (
        re.compile(r"\bStop\s*/\s*Revisit Triggers?\b", re.IGNORECASE),
        "Downside Sensitivities",
    ),
    (
        re.compile(r"\bWhat Would Make Us Revisit or Decline\b", re.IGNORECASE),
        "Downside Sensitivities",
    ),
    (
        re.compile(
            r"\bBSH thesis fit relies on the late-stage financial-return "
            r"exception\. The disclosed founders are not Asian-immigrant per "
            r"the BSH preference\. Late-stage rules allow financial return to "
            r"justify thesis exceptions if moat and multiple are compelling; "
            r"the case therefore rests on the IP, channel, and "
            r"contracted-traction case clearing on its own\.?",
            re.IGNORECASE,
        ),
        (
            "ZaiNar has to clear on technical moat, channel access, and "
            "contracted traction at this entry."
        ),
    ),
    (
        re.compile(
            r"\b[Ss]izing should reflect this distribution, the late-stage "
            r"financial-return exception under the BSH thesis, and the "
            r"single-asset SPV illiquidity profile\.?",
        ),
        (
            "Sizing should reflect the return distribution and the single-asset "
            "SPV illiquidity profile."
        ),
    ),
    (
        re.compile(r"\blate-stage financial-return exception\b", re.IGNORECASE),
        "return-based late-stage investment case",
    ),
    (
        re.compile(r"\bAsian-immigrant\b", re.IGNORECASE),
        "founder-background",
    ),
    (
        re.compile(
            r"\bSeries A2 slips materially beyond the May 2026 "
            r"\"closing imminent\" framing, or reprices above approximately "
            r"\$3\.53B pre-money, in which case the cap binds and the SAFE "
            r"discount benefit erodes\.?",
            re.IGNORECASE,
        ),
        (
            "Series A2 closing timing and pricing remain material to entry "
            "economics. A material delay beyond the May 2026 closing-imminent "
            "disclosure leaves the SPV holding an unpriced SAFE for longer; an "
            "A2 above approximately $3.53B pre-money shifts conversion toward "
            "the $3B cap rather than the 15% discount."
        ),
    ),
    (
        re.compile(
            r"\bThe binding-contract share inside the \$500M\+ figure proves "
            r"to be a small fraction of the headline, or the Kajima per-site "
            r"economic is restated below approximately \$5M ARR per site on a "
            r"recurring basis\.?",
            re.IGNORECASE,
        ),
        (
            "A material share of the $500M+ figure remains MOUs. "
            "Kajima's per-site recurring value is the other named risk "
            "behind the disclosed $10M ARR claim."
        ),
    ),
    (
        re.compile(
            r"\bSeries B pricing materially below the disclosed \$15B target "
            r"on a recapitalization or down-round path, shifting the SPV from "
            r"a paper-mark outcome into a flat-to-modest carry for the holding "
            r"period\.?",
            re.IGNORECASE,
        ),
        (
            "Series B pricing materially below the disclosed $15B target would "
            "move the SPV from an unrealized valuation-gain case toward a "
            "flat-to-modest return profile for the holding period."
        ),
    ),
    (
        re.compile(r"\bpaper-mark outcome\b", re.IGNORECASE),
        "unrealized valuation-gain case",
    ),
    (
        re.compile(r"\bflat-to-modest carry\b", re.IGNORECASE),
        "flat-to-modest return",
    ),
    (
        re.compile(r"\bImmediate Confirmation Work\b", re.IGNORECASE),
        "Risk And Deal Mechanics",
    ),
    (
        re.compile(r"\bClosing bar:\s*", re.IGNORECASE),
        "Risk: ",
    ),
    (
        re.compile(
            r"\bWe recommend proceeding once ([^.]+?) are confirmed\.?",
            re.IGNORECASE,
        ),
        (
            "Recommendation: BSH commits to the SPV. "
            r"\1 drive entry economics."
        ),
    ),
    (
        re.compile(
            r"\bWe recommend proceeding if ([^.]+?) confirm the current "
            r"investment case\.?",
            re.IGNORECASE,
        ),
        (
            "Recommendation: BSH commits to the SPV. "
            r"\1 are central to the disclosed terms."
        ),
    ),
    (
        re.compile(
            r"\bWe recommend proceeding with a participation in ([^.]+?) "
            r"subject to the closing confirmations below\.?",
            re.IGNORECASE,
        ),
        r"Recommendation: BSH commits capital to \1.",
    ),
    (
        re.compile(
            r"\bWe recommend proceeding with a participation in ([^.]+?) "
            r"subject to (?:the )?Valuation Sensitivity below\.?",
            re.IGNORECASE,
        ),
        r"Recommendation: BSH commits capital to \1.",
    ),
    (
        re.compile(
            r"\bWe recommend ([^.]+?) subject to ([^.]+?)\.?",
            re.IGNORECASE,
        ),
        r"Recommendation: \1. \2 is a named risk.",
    ),
    (
        re.compile(
            r"\bthe unresolved questions sit around ([^.]+?)\.",
            re.IGNORECASE,
        ),
        r"the named risk is \1.",
    ),
    (
        re.compile(
            r"\bWe would revisit if ([^.]+?)\.",
            re.IGNORECASE,
        ),
        r"The downside case begins if \1.",
    ),
    (
        re.compile(r"\bDiligence Thresholds\b", re.IGNORECASE),
        "Valuation Sensitivity",
    ),
    (
        re.compile(r"\bNext Diligence Actions\b", re.IGNORECASE),
        "Risk and Valuation Follow-Through",
    ),
    (
        re.compile(
            r"\bTreat as forward until the A2 lead and final pre-money are "
            r"confirmed; confirm before funding the SPV\.?",
            re.IGNORECASE,
        ),
        (
            "The round is a forward marker. Final A2 lead, pre-money, and "
            "closing evidence determine whether the disclosed entry economics "
            "hold."
        ),
    ),
    (
        re.compile(r"\bConfirm before funding:\s*([^.]+)\.?", re.IGNORECASE),
        r"The named risk is \1.",
    ),
    (
        re.compile(
            r"\bConfirm A2 lead investor identity, final pre-money, and that "
            r"the priced round actually closes \(memo language was [^)]+\)\.?",
            re.IGNORECASE,
        ),
        (
            "A2 lead investor identity, final pre-money, and priced-round "
            "closing evidence determine whether the disclosed Series A2 "
            "economics hold."
        ),
    ),
    (
        re.compile(
            r"\bConfirm the A2 closes on disclosed terms\.?",
            re.IGNORECASE,
        ),
        "A2 closing terms determine whether the disclosed entry economics hold.",
    ),
    (
        re.compile(
            r"\bConfirm in subscription docs that the SAFE applies "
            r"lower-of-cap-or-discount mechanics so the discount controls\.?",
            re.IGNORECASE,
        ),
        (
            "SAFE lower-of-cap-or-discount mechanics determine whether the "
            "15% discount controls at the disclosed A2 economics."
        ),
    ),
    (
        re.compile(
            r"\bConfirm the SAFE applies lower-of cap or discount, with the "
            r"15% discount controlling at a \$3\.0B A2 pre-money\.?",
            re.IGNORECASE,
        ),
        (
        "The SAFE's lower-of-cap-or-discount mechanics set the effective entry. "
            "The 15% discount controls at a $3.0B A2 pre-money."
        ),
    ),
    (
        re.compile(
            r"\bConfirm the split between signed contracts and MOUs inside the "
            r"\$500M\+ figure, and a 12-month recognition outlook on the "
            r"signed share\.?",
            re.IGNORECASE,
        ),
        (
            "The signed-contract mix, MOU mix, and 12-month recognition outlook "
            "inside the $500M+ figure are the named commercial risks."
        ),
    ),
    (
        re.compile(
            r"\bConfirm the DoD \$36M contract vehicle type and IP rights "
            r"regime under DFARS so we understand commercial restrictions on "
            r"derivative tech\.?",
            re.IGNORECASE,
        ),
        (
            "DoD contract vehicle type and DFARS IP-rights regime determine "
            "whether derivative-tech monetization is materially restricted."
        ),
    ),
    (
        re.compile(
            r"\bA2 lead investor, final pre-money, and the priced round "
            r"actually closes\.?",
            re.IGNORECASE,
        ),
        "A2 lead, final pre-money, and priced-round closing economics determine the effective entry.",
    ),
    (
        re.compile(
            r"\bA2 close and final terms match the SPV subscription economics\.?",
            re.IGNORECASE,
        ),
        "Final A2 economics shape the SPV's effective entry.",
    ),
    (
        re.compile(
            r"\bSAFE document confirms lower-of cap or discount mechanic with "
            r"the 15% discount controlling at a \$3\.0B A2\.?",
            re.IGNORECASE,
        ),
        "The SAFE's lower-of-cap-or-discount mechanics determine whether the 15% discount controls at a $3.0B A2.",
    ),
    (
        re.compile(
            r"\bDoD contract vehicle type and DFARS IP rights regime so we "
            r"understand commercial restrictions on derivative tech\.?",
            re.IGNORECASE,
        ),
        "DoD contract vehicle type and DFARS IP-rights regime shape commercial restrictions on derivative tech.",
    ),
    (
        re.compile(
            r"\bRequest signed-vs-MOU split, Kajima cohort detail, and any "
            r"healthcare deployment named with revenue attribution\.?",
            re.IGNORECASE,
        ),
        (
            "Signed-vs-MOU mix, Kajima cohort detail, and healthcare revenue "
            "attribution are the commercial facts that matter."
        ),
    ),
    (
        re.compile(
            r"\bSigned-vs-MOU split, Kajima cohort detail, and any healthcare "
            r"deployment named with revenue attribution support the base case\.?",
            re.IGNORECASE,
        ),
        (
            "Signed-vs-MOU mix, Kajima cohort detail, and healthcare revenue "
            "attribution remain unproven."
        ),
    ),
    (
        re.compile(
            r"\bRequire split of signed vs\. MOU; risk-weight MOU using a "
            r"15-35% conversion range for scenario work\.?",
            re.IGNORECASE,
        ),
        (
            "A material share of the headline may remain MOUs. The commercial "
            "value is lower if the binding share is small."
        ),
    ),
    (
        re.compile(
            r"\brequire a signed-vs-MOU split as a Valuation Sensitivity\b",
            re.IGNORECASE,
        ),
        "the signed-vs-MOU mix is a commercial risk",
    ),
    (
        re.compile(
            r"\bRequire claim-scope and freedom-to-operate read versus "
            r"([^.]+?) before underwriting as multi-year monopoly\.?",
            re.IGNORECASE,
        ),
        (
            "Claim-scope and freedom-to-operate determine whether the patent "
            r"estate has durable leverage versus \1."
        ),
    ),
    (
        re.compile(
            r"\bWe should confirm claim-scope and freedom-to-operate versus "
            r"([^.]+?) before treating the patent estate as a multi-year monopoly\.?",
            re.IGNORECASE,
        ),
        (
            "Claim-scope and freedom-to-operate determine whether the patent "
            r"estate has durable leverage versus \1."
        ),
    ),
    (
        re.compile(
            r"\bbefore we underwrite the licensing fallback\b",
            re.IGNORECASE,
        ),
        "until the licensing fallback is documented",
    ),
    (
        re.compile(
            r"\bWe treat this as a credible defensive perimeter; we still need "
            r"a claim-scope and freedom-to-operate read against ([^.]+?) "
            r"before we give full "
            r"credit to the licensing fallback that the "
            r"sponsor implies under 3GPP standardization\.?",
            re.IGNORECASE,
        ),
        (
            "This is a credible defensive perimeter. Claim-scope and "
            r"freedom-to-operate determine whether licensing leverage against \1 "
            "survives 3GPP standardization."
        ),
    ),
    (
        re.compile(
            r"\bWe still need a claim-scope read that the sponsor implies is "
            r"covered by the IP portfolio\.?",
            re.IGNORECASE,
        ),
        "Patent coverage remains a risk until claim scope is documented.",
    ),
    (
        re.compile(r"\bwe still need\b", re.IGNORECASE),
        "The named risk is:",
    ),
    (
        re.compile(
            r"\bThe sponsor itself flags this as the primary standardization "
            r"risk and frames ZaiNar's IP portfolio as the licensing fallback\.?",
            re.IGNORECASE,
        ),
        (
            "Future SRS-based positioning is the primary standardization risk; "
            "the licensing-fallback case depends on ZaiNar patent claims "
            "covering the standardized function."
        ),
    ),
    (
        re.compile(
            r"\bThe sponsor itself flags carrier sales cycles of 18 to 36 "
            r"months, so this layer is a credible distribution thesis rather "
            r"than a near-term revenue thesis\.?",
            re.IGNORECASE,
        ),
        (
            "Carrier sales cycles run 18 to 36 months. This is a distribution "
            "thesis, not near-term revenue."
        ),
    ),
    (
        re.compile(
            r"\.\s+the investment case identifies carrier sales cycles of 18 "
            r"to 36 months, so this layer is a credible distribution thesis "
            r"rather than a near-term revenue thesis\.?",
            re.IGNORECASE,
        ),
        (
            ". Carrier sales cycles run 18 to 36 months. This is a distribution "
            "thesis, not near-term revenue."
        ),
    ),
    (
        re.compile(
            r"\bThe sponsor itself acknowledges that a meaningful portion is "
            r"in MOU form and that pipeline figures are company-provided and "
            r"unaudited\.?",
            re.IGNORECASE,
        ),
        (
            "A meaningful portion is in MOU form, and pipeline figures are "
            "company-provided and unaudited."
        ),
    ),
    (
        re.compile(r"\bsponsor acknowledges MOU-heavy\b", re.IGNORECASE),
        "includes material MOU component",
    ),
    (
        re.compile(
            r"\bthe references that the sponsor relied on are economically "
            r"aligned with the company\b",
            re.IGNORECASE,
        ),
        "the reported references remain economically aligned with the company",
    ),
    (
        re.compile(
            r"\bSponsor explicitly discloses 18 to 36 month carrier sales cycles\.?",
            re.IGNORECASE,
        ),
        "Carrier sales cycles run 18 to 36 months.",
    ),
    (
        re.compile(
            r"\bSponsor reference calls with ([^.]+?) reportedly returned "
            r"uniformly positive views, while remaining economically aligned "
            r"with the company\.?",
            re.IGNORECASE,
        ),
        (
            r"Reference calls with \1 reportedly returned uniformly positive "
            "views; those references remain economically aligned with the company."
        ),
    ),
    (
        re.compile(r"\bthe sponsor implies\b", re.IGNORECASE),
        "the disclosed terms assume",
    ),
    (
        re.compile(r"\bthe sponsor frames\b", re.IGNORECASE),
        "the disclosed terms treat",
    ),
    (
        re.compile(r"\bthe sponsor itself flags\b", re.IGNORECASE),
        "the disclosed materials identify",
    ),
    (
        re.compile(r"\bmemo language was\b", re.IGNORECASE),
        "the disclosed timing was",
    ),
    (
        re.compile(r"\binside the memo\b", re.IGNORECASE),
        "in sponsor materials",
    ),
    (
        # Not "BSH invests in …": that manufactures a per-deal mandate
        # sentence, which the voice contract forbids (the mandate line is
        # the firm's own, from the settings background, or none).
        re.compile(r"\bWe invest behind\b", re.IGNORECASE),
        lambda match: _sentence_case(match, "the recommendation backs"),
    ),
    (
        # (?!-) keeps hyphenated verbs ("we back-solve", "we back-test")
        # out of the sell-side rewrite; they are modeling vocabulary.
        re.compile(r"\bWe back\b(?!-)", re.IGNORECASE),
        lambda match: _sentence_case(match, "the recommendation backs"),
    ),
    (
        re.compile(r"\bwhy we want exposure\b", re.IGNORECASE),
        "why the opportunity fits BSH's mandate",
    ),
    (
        re.compile(r"\bwe want exposure to\b", re.IGNORECASE),
        "the recommendation commits capital to",
    ),
    (
        re.compile(r"\bwe are being offered\b", re.IGNORECASE),
        "Investors can subscribe to",
    ),
    (
        re.compile(r"\bwe are participating through\b", re.IGNORECASE),
        "the recommended participation is through",
    ),
    (
        # "the recommendation is to commit capital…" was itself the lint's
        # "the recommendation is" P0 (the ZaiNar memo shipped with it): the
        # house form is "Recommendation: BSH commits capital to …".
        re.compile(r"\bwe recommend participating( in)?\b", re.IGNORECASE),
        lambda match: _commit_capital_rewrite(match),
    ),
    # The same slogans negated (the lint bans them since R19): a pass is
    # "Recommendation: pass on <target>.", never a slogan.
    (
        re.compile(
            r"\bwe (?:do not|don't|would not|wouldn't) recommend participating"
            r"(?: in ([^.;]+?))?(?=[.;]|$)",
            re.IGNORECASE,
        ),
        lambda match: _pass_rewrite(match),
    ),
    (
        re.compile(r"\bwe are not being offered\b", re.IGNORECASE),
        lambda match: _sentence_case(match, "investors are not offered"),
    ),
    (
        re.compile(r"\bwe are not participating (through|via)\b", re.IGNORECASE),
        lambda match: _sentence_case(
            match, f"the recommended participation is not {match.group(1).lower()}"
        ),
    ),
    # ---- Decided-language inverse net -------------------------------------
    # The memo's conclusion is a recommendation; nothing is decided when it
    # is written. These convert residual decided constructions into
    # recommendation modality. The history sentence ("BSH made the decision
    # to ...") is shelved before any rule runs, so it is never touched.
    (
        re.compile(
            r"\bBSH is committing (capital )?to ([^.]+?)\.", re.IGNORECASE
        ),
        r"Recommendation: BSH commits \1to \2.",
    ),
    (
        re.compile(r"\bBSH is committing \$", re.IGNORECASE),
        "Recommendation: BSH commits $",
    ),
    (
        re.compile(r"\bBSH is investing in ([^.]+?)\.", re.IGNORECASE),
        r"Recommendation: BSH invests in \1.",
    ),
    (
        re.compile(
            r"\bBSH is not (?:committing capital to|committing to|"
            r"participating in) ([^.]+?)\.",
            re.IGNORECASE,
        ),
        r"Recommendation: pass on \1.",
    ),
    (
        re.compile(r"\binvest behind\b", re.IGNORECASE),
        "invest in",
    ),
    (
        re.compile(r"\bcontrol layer underneath\b", re.IGNORECASE),
        "control layer for",
    ),
    (
        re.compile(r"\bonly scaled platform delivering\b", re.IGNORECASE),
        "platform delivering",
    ),
    (
        re.compile(r"\bon the framed terms\b", re.IGNORECASE),
        "on the disclosed terms",
    ),
    (
        re.compile(r"\bprices as framed\b", re.IGNORECASE),
        "prices at the disclosed economics",
    ),
    (
        re.compile(r"\bclosing as framed\b", re.IGNORECASE),
        "closing at the disclosed economics",
    ),
    (
        re.compile(r"\bat the framed A2\b", re.IGNORECASE),
        "at the disclosed A2 economics",
    ),
    (
        re.compile(r"\bat the framed Series A2\b", re.IGNORECASE),
        "at the disclosed Series A2 economics",
    ),
    (
        re.compile(r"\bas framed\b", re.IGNORECASE),
        "at the disclosed economics",
    ),
    (
        re.compile(r"\bframed terms\b", re.IGNORECASE),
        "disclosed terms",
    ),
    (
        re.compile(
            r"\bproduced for (?:the|this|our) memo\b",
            re.IGNORECASE,
        ),
        "used as source evidence",
    ),
    (
        re.compile(r"\bfor (?:the|this|our) memo\b", re.IGNORECASE),
        "for the disclosed terms",
    ),
    (
        re.compile(r"\bWisdom Ventures SPV memo\b", re.IGNORECASE),
        "Wisdom Ventures SPV materials",
    ),
    (
        re.compile(r"\bWV SPV memo\b", re.IGNORECASE),
        "Wisdom Ventures SPV materials",
    ),
    (
        re.compile(r"\bwe mirror that posture\b", re.IGNORECASE),
        "we treat those figures as pipeline rather than bookings",
    ),
    (
        re.compile(
            r"\bwe treat those figures as pipeline rather than bookings rather "
            r"than restate the totals as bookings\b",
            re.IGNORECASE,
        ),
        "we treat those figures as pipeline rather than bookings",
    ),
    (
        re.compile(
            r"\bThe Information's \$5B figure matches the May 2026 sponsor "
            r"restatement, which we flag rather than double-count\.?",
            re.IGNORECASE,
        ),
        (
            "The Information's $5B figure matches the May 2026 sponsor figure, "
            "so we do not double-count it."
        ),
    ),
    (
        re.compile(r"\bsource material\b", re.IGNORECASE),
        "available evidence",
    ),
    (
        re.compile(
            r"\bThe competitor list embedded in the registry\b",
            re.IGNORECASE,
        ),
        "The listed competitor set",
    ),
    (
        re.compile(r"\bembedded in the registry\b", re.IGNORECASE),
        "listed in available materials",
    ),
    (
        re.compile(
            r"\bWe will look for a refreshed signed-vs-MOU split before closing\.?",
            re.IGNORECASE,
        ),
        "The refreshed signed-vs-MOU split is a commercial risk. A small binding share weakens the base scenario.",
    ),
    (
        re.compile(
            r"\bWe underwrite the displacement TAM as bounded;",
            re.IGNORECASE,
        ),
        "The displacement TAM is bounded;",
    ),
    (
        re.compile(
            r"\bwhich is the right way to view the underwriting:\s*",
            re.IGNORECASE,
        ),
        "which supports the case: ",
    ),
    (
        re.compile(
            r"\bbefore underwriting derivative-tech monetization\b",
            re.IGNORECASE,
        ),
        "until derivative-tech monetization is documented",
    ),
    (
        re.compile(
            r"\bwe confirm the executed document before funding\.?",
            re.IGNORECASE,
        ),
        (
            "The executed document determines the conversion mechanics."
        ),
    ),
    (
        re.compile(
            r"\bCross-check DoD signings on SAM\.gov and USAspending\.gov\.?",
            re.IGNORECASE,
        ),
        "SAM.gov and USAspending.gov support the defense-contract evidence base.",
    ),
    (
        re.compile(
            r"\bPatent counsel claim-scope and freedom-to-operate read supports "
            r"durable patent leverage\.?",
            re.IGNORECASE,
        ),
        "Patent durability depends on claim-scope and freedom-to-operate support.",
    ),
    (
        re.compile(
            r"\bSource two non-investor technical references through the BSH "
            r"and partner networks\.?",
            re.IGNORECASE,
        ),
        (
            "Independent technical-reference depth remains a sensitivity for "
            "deployment readiness."
        ),
    ),
    (
        re.compile(
            r"\bIf the A2 reprices below \$3\.0B, conversion mechanics and "
            r"effective entry should be re-evaluated\.?",
            re.IGNORECASE,
        ),
        "If the A2 reprices below $3.0B, we revisit conversion mechanics and effective entry.",
    ),
    (
        re.compile(
            r"\bThe \$36M\+ DoD contracts may carry DFARS government-purpose "
            r"or unlimited rights in delivered software and data\. Without "
            r"disclosure, we cannot rule out constraints on commercial "
            r"monetization of derivative tech in adjacent verticals\.?",
            re.IGNORECASE,
        ),
        (
            "DFARS terms determine whether government-purpose or unlimited "
            "rights constrain commercial monetization of derivative tech in "
            "adjacent verticals."
        ),
    ),
    (
        re.compile(
            r"\bConfirm A2 close and final terms with Wisdom Ventures before "
            r"signing subscription documents\.?",
            re.IGNORECASE,
        ),
        "A2 close and final terms match the SPV subscription economics.",
    ),
    (
        re.compile(
            r"\bCommission claim-scope and freedom-to-operate read on the "
            r"patent estate\.?",
            re.IGNORECASE,
        ),
        "Patent counsel claim-scope and freedom-to-operate read supports durable patent leverage.",
    ),
    (
        re.compile(
            r"\bWe frame it as technology paradigms rather than a logo list, "
            r"because the durable pricing-power question is whether incumbent "
            r"paradigms absorb the function ZaiNar performs\.?",
            re.IGNORECASE,
        ),
        (
            "Durable pricing power turns on whether incumbent technology "
            "paradigms absorb the function ZaiNar performs."
        ),
    ),
    (
        re.compile(r"\bwe frame it as\b", re.IGNORECASE),
        "this is",
    ),
    (
        re.compile(
            r"\bno preference, no voting, and no information rights at the LP level\b",
            re.IGNORECASE,
        ),
        "a SAFE is not equity and has no LP voting",
    ),
    (
        re.compile(r"\bno voting(?: rights)?\b", re.IGNORECASE),
        "no LP voting",
    ),
    (
        re.compile(r"\binformation rights\b", re.IGNORECASE),
        "LP-level reporting",
    ),
    (
        re.compile(r"\bvoting rights\b", re.IGNORECASE),
        "LP voting",
    ),
    # Only the phrases the quality lint bans (memo_quality_lint: "we / BSH
    # underwrite…", "underwriting case / view / posture / assumption /
    # basis / lens") are rewritten, each into a grammatical equivalent.
    # The bare noun or gerund elsewhere ("Valuation Multiple Underwriting
    # and Return Profile", "Underwriting the $1.0B post-money valuation
    # against…") is ordinary English and is left alone: the word-level
    # rewrite this replaces produced "Valuation Multiple investment case
    # and Return Profile" and "investment case the $1.0B post-money
    # valuation against…" in the Gemini v1 ZaiNar memo
    # (2026-09-23__015923__zainar-inc__memo-run__2).
    (
        re.compile(r"\b(we|bsh)\s+(have|had|has)\s+underwritten\b", re.IGNORECASE),
        r"\1 \2 relied on",
    ),
    (
        re.compile(
            r"\b(we|bsh)\s+(are|were|is|was)\s+underwriting\b", re.IGNORECASE
        ),
        r"\1 \2 relying on",
    ),
    (
        re.compile(r"\b(we|bsh)\s+underwrite\b", re.IGNORECASE),
        r"\1 rely on",
    ),
    (
        re.compile(r"\b(we|bsh)\s+underwrites\b", re.IGNORECASE),
        r"\1 relies on",
    ),
    (
        re.compile(r"\b(we|bsh)\s+underwrote\b", re.IGNORECASE),
        r"\1 relied on",
    ),
    (
        re.compile(r"\b(we|bsh)\s+underwriting\b", re.IGNORECASE),
        r"\1 relying on",
    ),
    (
        re.compile(r"\b(we|bsh)\s+underwritten\b", re.IGNORECASE),
        r"\1 supported",
    ),
    (
        re.compile(
            r"\b(underwriting)\s+(case|view|posture|assumption|basis|lens)\b",
            re.IGNORECASE,
        ),
        lambda m: ("Investment" if m.group(1)[0].isupper() else "investment")
        + " "
        + m.group(2),
    ),
    (
        re.compile(r"\bwe give credit to\b", re.IGNORECASE),
        "the disclosed terms count",
    ),
    (
        re.compile(r"\bour base case credits\b", re.IGNORECASE),
        "the disclosed terms count",
    ),
    (
        re.compile(r"\bthe investment case rests on\b", re.IGNORECASE),
        "the case depends on",
    ),
)


# Sentences recording an actual past decision ("BSH made the decision to
# pass on 2026-01-05 because ...") are pinned factual history: the pin-echo
# gate enforces them verbatim, so no voice rewrite may touch them — not
# even when the human-entered reason inside the sentence happens to use
# decided-sounding phrasing.
_DECISION_HISTORY_SENTENCE = re.compile(
    r"[^.!?]*\bmade the decision\b[^.!?]*[.!?]?", re.IGNORECASE
)


def _rewrite_memo_package_voice_text(text: str) -> str:
    protected: list[str] = []

    def _shelve(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00DH{len(protected) - 1}\x00"

    updated = _DECISION_HISTORY_SENTENCE.sub(_shelve, text)
    for pattern, replacement in _MEMO_PACKAGE_VOICE_REWRITES:
        updated = pattern.sub(replacement, updated)
    for index, sentence in enumerate(protected):
        updated = updated.replace(f"\x00DH{index}\x00", sentence)
    return updated


# Late v1 keeps source ids in the fact reference index: a bracket id in the
# body is a P0 the quality gate sends to a repair round, and the lint's own
# suggestion is to move it to the index. Gemini writes them freely — 100 in
# one Koch, Inc. memo, against none from Claude on the same prompt — and the
# surgical repair could not clear them, so the memo shipped with 50
# warnings. Removing the token is that move, done deterministically before
# the pre-render check and the render. Structure-v2 memos cite inline by
# design and are left alone; the sources index is never touched.
_BODY_SOURCE_TOKEN_RE = re.compile(r"\s*\[\s*[sS]\d+(?:\s*[,;]\s*[sS]\d+)*\s*\]")


def _strip_body_source_tokens(text: str) -> str:
    stripped = _BODY_SOURCE_TOKEN_RE.sub("", text)
    if stripped == text:
        return text
    return re.sub(r"[ \t]{2,}", " ", stripped).strip()


def _body_keeps_source_ids_in_the_index(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        structure = memo_structure.for_package(payload)
    except Exception:  # noqa: BLE001
        structure = memo_structure.LATE
    return not structure.scorecard_weights()


def _rewritten_memo_package_voice(payload: Any) -> tuple[Any, list[dict[str, str]]]:
    """Apply the deterministic voice rewrites to a package payload copy."""
    changes: list[dict[str, str]] = []
    strip_tokens = _body_keeps_source_ids_in_the_index(payload)

    def record(path: str, before: str, after: str) -> None:
        if after != before:
            changes.append({"path": path, "before": before[:220], "after": after[:220]})

    def visit(value: Any, path: str = "") -> Any:
        if isinstance(value, dict):
            return {
                key: visit(item, f"{path}.{key}" if path else str(key))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [visit(item, f"{path}[{index}]") for index, item in enumerate(value)]
        in_body = strip_tokens and path.startswith("sections")
        if isinstance(value, str) and path.endswith(".en"):
            rewritten = _rewrite_memo_package_voice_text(value)
            if in_body:
                rewritten = _strip_body_source_tokens(rewritten)
            record(path, value, rewritten)
            return rewritten
        if isinstance(value, str) and path.endswith(".zh") and in_body:
            rewritten = _strip_body_source_tokens(value)
            record(path, value, rewritten)
            return rewritten
        return value

    return visit(payload), changes


def _clean_memo_package_voice(package_path: Path, stream: job_progress.ProgressLog) -> int:
    if not package_path.exists():
        return 0
    try:
        payload = json.loads(package_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("failed to read memo package for voice cleanup: %s", package_path)
        return 0

    cleaned, changes = _rewritten_memo_package_voice(payload)
    if not changes:
        return 0
    package_path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stream.emit(
        "stage",
        stage="memo_package_voice_cleanup",
        message="Cleaned buyer-side underwriting/process language before DOCX rendering",
        memo_package=memo_prep._rel(package_path),
        rewrite_count=len(changes),
        rewrites=changes[:8],
    )
    return len(changes)


def _latest_archived_memo_package(run_dir: Path, *, label: str) -> Path | None:
    logs_dir = run_dir / "logs"
    if not logs_dir.exists():
        return None
    archives = sorted(
        logs_dir.glob(f"memo_package.{label}.*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return archives[0] if archives else None


def _block_generated_renderer_scripts(
    *,
    report_id: str,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
) -> bool:
    with _timed_phase(
        stream,
        phase="memo_renderer_script_precheck",
        recovered=recovered,
        run_dir=memo_prep._rel(run_dir),
    ) as timing:
        forbidden_scripts = memo_docx_renderer.find_generated_renderer_scripts(run_dir)
        timing["generated_renderer_script_count"] = len(forbidden_scripts)
        if not forbidden_scripts:
            return False
        rel_paths = [memo_prep._rel(path) for path in forbidden_scripts]
        msg = (
            "Memo run generated bespoke renderer code instead of using "
            "server.memo_docx_renderer: "
            + "; ".join(rel_paths[:8])
        )
        timing["status"] = "failed"
        timing["error"] = msg
        timing["generated_renderer_scripts"] = rel_paths
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Generated renderer script blocked",
        error=msg,
        failure_phase="renderer_contract",
        failure_detail=msg,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    payload = {
        "error": msg,
        "phase": "renderer_contract",
        "generated_renderer_scripts": rel_paths,
    }
    if recovered:
        payload["recovered"] = True
    stream.emit(
        "thread_failed",
        thread=claude_runner.MEMO_PHASE5_THREAD,
        error=msg,
    )
    stream.emit("error", **payload)
    return True


def _renderer_contract_diagnostics(
    *,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    locales: tuple[str, ...] = ("en", "zh"),
    package_path: Path | None = None,
) -> dict:
    """What the renderer contract expects on disk, per rendered language.

    ``locales`` narrows the check to the languages this render produced
    (an English-only delivery checks only the English files);
    ``package_path`` is the package that was rendered (the accepted English
    package for an English-only delivery)."""
    errors: list[str] = []
    package_path = package_path or _memo_package_path(run_dir)
    expected: dict[str, Path | None] = {"memo_package": package_path}
    if "en" in locales:
        expected["english_memo"] = memo_paths_abs.get("en")
    if "zh" in locales:
        expected["chinese_memo"] = memo_paths_abs.get("zh")
    if "en" in locales:
        expected["validation_en"] = run_dir / "logs" / "validation.txt"
    if "zh" in locales:
        expected["validation_zh"] = run_dir / "logs" / "validation_cn.txt"
    expected["file_inventory"] = run_dir / "logs" / "file_inventory.md"
    expected["run_manifest"] = run_dir / "logs" / "run_manifest.md"
    expected_files: list[dict] = []
    for label, path in expected.items():
        exists = bool(path and path.exists())
        item = {
            "label": label,
            "path": memo_prep._rel(path) if path else None,
            "exists": exists,
        }
        if exists and path:
            try:
                item["size_bytes"] = path.stat().st_size
            except OSError:
                pass
        expected_files.append(item)
        if not exists:
            errors.append(f"{label} missing")
    manifest = expected["run_manifest"]
    if manifest and manifest.exists():
        text = manifest.read_text(encoding="utf-8", errors="replace")
        if "server.memo_docx_renderer" not in text:
            errors.append("run_manifest missing server.memo_docx_renderer")
        if "validation_status: passed" not in text:
            errors.append("run_manifest missing validation_status: passed")
    inventory = expected["file_inventory"]
    if inventory and inventory.exists():
        text = inventory.read_text(encoding="utf-8", errors="replace")
        if any(f"memo_{locale}:" not in text for locale in locales):
            errors.append("file_inventory missing rendered memo entries")
    result = {
        "run_dir": memo_prep._rel(run_dir),
        "memo_package": memo_prep._rel(package_path),
        "errors": errors,
        "expected_files": expected_files,
    }
    if tuple(locales) != ("en", "zh"):
        result["locales"] = list(locales)
    return result


def _render_single_locale(
    package: dict,
    locale: str,
    out_path: Path,
    *,
    run_dir: Path,
) -> dict:
    """Render ONE language of the memo and leave the other language's file
    alone: the English memo before the Chinese exists, the Chinese alone
    on "Retry Chinese" (``memo_docx_renderer.render_memo_locale``: that
    language's document, its validation log, the inventory lines and one
    manifest block — the per-language contract check reads those)."""
    del run_dir  # the renderer writes its logs next to out_path's run
    return memo_docx_renderer.render_memo_locale(package, locale, out_path)


def _english_render_payload(english_package: dict) -> dict:
    """The accepted English package as the renderer should see it for an
    English-only document: the same deterministic voice rewrites finalize
    applies, so the early English memo reads exactly as the bilingual
    render's English will (blank Chinese halves are allowed for "en")."""
    rewritten, _ = _rewritten_memo_package_voice(english_package)
    return rewritten


def _render_memo_pdf_previews(
    *,
    report_id: str,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    progress: int | None = None,
    recovered: bool = False,
) -> list[dict]:
    """Best-effort PDF previews for the LP-facing memo DOCX files.

    PDF previews are QA affordances only. A conversion failure must never
    block access to the underlying DOCX, and failed quality/parity runs must
    still expose whatever rendered memo artifacts exist.
    """
    if progress is not None:
        _update_report(
            report_id,
            stage="Rendering memo PDF previews",
            progress=progress,
        )
    stream.emit(
        "stage",
        stage="rendering_pdf",
        message="Rendering memo PDF previews",
        recovered=recovered,
    )

    with _timed_phase(
        stream,
        phase="memo_pdf_previews",
        recovered=recovered,
        enabled=True,
    ) as timing:
        current_report = storage.get_report(report_id) or {}
        updated_memo_files: list[dict] = []
        converted_count = 0
        skipped_existing_count = 0
        failed_count = 0
        for entry in current_report.get("memo_files") or []:
            lang = entry.get("language")
            new_entry = dict(entry)
            docx_abs = memo_paths_abs.get(lang)
            if docx_abs and docx_abs.exists():
                existing_pdf = new_entry.get("pdf_path")
                if existing_pdf and (
                    memo_prep.DATA_DIR.parent / existing_pdf
                ).exists():
                    skipped_existing_count += 1
                    updated_memo_files.append(new_entry)
                    continue
                pdf_abs = docx_abs.with_suffix(".pdf")
                try:
                    ok, err = docx_pdf.convert_docx_to_pdf(docx_abs, pdf_abs)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "PDF render crashed for %s memo (%s)", lang, report_id
                    )
                    ok = False
                    err = f"PDF conversion crashed: {type(exc).__name__}: {exc}"
                if ok:
                    converted_count += 1
                    new_entry["pdf_path"] = memo_prep._rel(pdf_abs)
                else:
                    failed_count += 1
                    logger.warning(
                        "PDF render failed for %s memo (%s): %s",
                        lang,
                        report_id,
                        err,
                    )
                    stream.emit(
                        "claude_action",
                        action="tool_result",
                        tool="docx→pdf",
                        is_error=True,
                        preview=(err or "PDF conversion failed")[:200],
                        recovered=recovered,
                    )
            updated_memo_files.append(new_entry)
        timing["memo_file_count"] = len(updated_memo_files)
        timing["converted_count"] = converted_count
        timing["skipped_existing_count"] = skipped_existing_count
        timing["failed_count"] = failed_count

    _update_report(report_id, memo_files=updated_memo_files)
    return updated_memo_files


def _maybe_render_memo_pdf_previews(
    *,
    report_id: str,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    progress: int | None = None,
    recovered: bool = False,
) -> list[dict]:
    if _memo_pdf_previews_enabled():
        return _render_memo_pdf_previews(
            report_id=report_id,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            progress=progress,
            recovered=recovered,
        )
    stream.emit(
        "stage",
        stage="pdf_previews_skipped",
        message=(
            "Skipping memo PDF previews; set "
            "BSH_MEMO_RENDER_PDF_PREVIEWS=1 to enable them."
        ),
        recovered=recovered,
    )
    _emit_phase_timing(
        stream,
        phase="memo_pdf_previews",
        status="skipped",
        started_at=_now_iso(),
        started_monotonic=time.monotonic(),
        recovered=recovered,
        enabled=False,
        reason="BSH_MEMO_RENDER_PDF_PREVIEWS not enabled",
    )
    current_report = storage.get_report(report_id) or {}
    return list(current_report.get("memo_files") or [])


def _render_internal_pdf_previews(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
) -> list[dict]:
    with _timed_phase(
        stream,
        phase="memo_internal_pdf_previews",
        enabled=True,
    ) as timing:
        current_report = storage.get_report(report_id) or {}
        updated_internal_files: list[dict] = []
        converted_count = 0
        skipped_existing_count = 0
        failed_count = 0
        for entry in current_report.get("internal_memo_files") or []:
            new_entry = dict(entry)
            docx_rel = new_entry.get("path")
            if docx_rel:
                docx_abs = memo_prep.DATA_DIR.parent / docx_rel
                if docx_abs.exists():
                    existing_pdf = new_entry.get("pdf_path")
                    if existing_pdf and (
                        memo_prep.DATA_DIR.parent / existing_pdf
                    ).exists():
                        skipped_existing_count += 1
                        updated_internal_files.append(new_entry)
                        continue
                    pdf_abs = docx_abs.with_suffix(".pdf")
                    try:
                        ok, err = docx_pdf.convert_docx_to_pdf(docx_abs, pdf_abs)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception(
                            "PDF render crashed for internal memo (%s)", report_id
                        )
                        ok = False
                        err = f"PDF conversion crashed: {type(exc).__name__}: {exc}"
                    if ok:
                        converted_count += 1
                        new_entry["pdf_path"] = memo_prep._rel(pdf_abs)
                    else:
                        failed_count += 1
                        logger.warning(
                            "PDF render failed for internal memo (%s): %s",
                            report_id,
                            err,
                        )
                        stream.emit(
                            "claude_action",
                            action="tool_result",
                            tool="internal-docx→pdf",
                            is_error=True,
                            preview=(err or "PDF conversion failed")[:200],
                        )
            updated_internal_files.append(new_entry)
        timing["internal_file_count"] = len(updated_internal_files)
        timing["converted_count"] = converted_count
        timing["skipped_existing_count"] = skipped_existing_count
        timing["failed_count"] = failed_count
    _update_report(report_id, internal_memo_files=updated_internal_files)
    return updated_internal_files


def _render_memo_outputs(
    *,
    report_id: str,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
) -> bool:
    package_path = _memo_package_path(run_dir)
    if not package_path.exists():
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message=f"Claude finished without writing {memo_prep._rel(package_path)}.",
            contract=_renderer_contract_diagnostics(
                run_dir=run_dir,
                memo_paths_abs=memo_paths_abs,
            ),
            recovered=recovered,
        )
        return False
    if not memo_paths_abs.get("en") or not memo_paths_abs.get("zh"):
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message="Report record is missing expected English or Chinese memo paths.",
            contract=_renderer_contract_diagnostics(
                run_dir=run_dir,
                memo_paths_abs=memo_paths_abs,
            ),
            recovered=recovered,
        )
        return False
    _update_report(
        report_id,
        stage="Rendering memo DOCX",
        progress=85,
    )
    stream.emit(
        "stage",
        stage="rendering_docx",
        message="Rendering memo DOCX from structured package",
        memo_package=memo_prep._rel(package_path),
        recovered=recovered,
    )
    voice_rewrite_count = _clean_memo_package_voice(package_path, stream)
    package_size_bytes = None
    try:
        package_size_bytes = package_path.stat().st_size
    except OSError:
        pass
    with _timed_phase(
        stream,
        phase="memo_docx_render",
        recovered=recovered,
        memo_package=memo_prep._rel(package_path),
        package_size_bytes=package_size_bytes,
        voice_rewrite_count=voice_rewrite_count,
        output_en=memo_prep._rel(memo_paths_abs["en"]),
        output_zh=memo_prep._rel(memo_paths_abs["zh"]),
    ) as timing:
        try:
            memo_docx_renderer.render_memos(
                package_path,
                out_en=memo_paths_abs["en"],
                out_zh=memo_paths_abs["zh"],
                manifest_path=run_dir / "logs" / "run_manifest.md",
                inventory_path=run_dir / "logs" / "file_inventory.md",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("memo package render failed for report %s", report_id)
            message = (
                "Memo package render failed: "
                f"{type(exc).__name__}: {exc}"
            )
            timing["status"] = "failed"
            timing["error"] = message
            _maybe_render_memo_pdf_previews(
                report_id=report_id,
                memo_paths_abs=memo_paths_abs,
                stream=stream,
                recovered=recovered,
            )
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=_renderer_contract_diagnostics(
                    run_dir=run_dir,
                    memo_paths_abs=memo_paths_abs,
                ),
                recovered=recovered,
            )
            return False

        contract = _renderer_contract_diagnostics(
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
        )
        errors = list(contract.get("errors") or [])
        timing["renderer_contract_error_count"] = len(errors)
        timing["expected_files"] = contract.get("expected_files")
        if errors:
            message = "Renderer contract failed: " + "; ".join(errors)
            timing["status"] = "failed"
            timing["error"] = message
            timing["renderer_contract_errors"] = errors
            _maybe_render_memo_pdf_previews(
                report_id=report_id,
                memo_paths_abs=memo_paths_abs,
                stream=stream,
                recovered=recovered,
            )
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=contract,
                recovered=recovered,
            )
            return False
    return True


def _run_chinese_parity_gate(
    *,
    report_id: str,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
) -> tuple[dict, str | None]:
    """Run the Chinese parity lint and return ``(payload, warning)``.

    Blocking findings no longer fail the run: the generation loops already
    retried with the findings fed back, so at this point delivering the memo
    WITH its issues listed beats blocking the user with nothing. The caller
    aggregates the warning into a ``complete_with_warnings`` terminal state,
    and resume keeps working to regenerate toward a clean memo.
    """
    _update_report(
        report_id,
        stage="Running Chinese memo parity gate",
        progress=88,
    )
    stream.emit(
        "stage",
        stage="chinese_parity_gate",
        message="Checking Chinese memo structure and CJK parity",
        recovered=recovered,
    )
    with _timed_phase(
        stream,
        phase="memo_chinese_parity_gate",
        recovered=recovered,
        english_memo=memo_prep._rel(memo_paths_abs["en"]),
        chinese_memo=memo_prep._rel(memo_paths_abs["zh"]),
    ) as timing:
        failure_payload = None
        failure_message = None
        parity_result = memo_chinese_parity.lint_chinese_memo_pair(
            memo_paths_abs["en"],
            memo_paths_abs["zh"],
            _structure_for_run(run_dir),
            package=_package_on_disk(_memo_package_path(run_dir)),
            run_dir=run_dir,
        )
        parity_path = run_dir / "logs" / "memo_chinese_parity.md"
        parity_path.write_text(
            memo_chinese_parity.render_markdown_report(parity_result),
            encoding="utf-8",
        )
        parity_payload = parity_result.to_dict()
        timing["parity_report"] = memo_prep._rel(parity_path)
        timing["finding_count"] = parity_payload.get("finding_count")
        timing["p0_count"] = parity_payload.get("p0_count")
        if parity_result.has_blocking_findings:
            msg = (
                "Chinese memo parity gate found "
                f"{parity_payload['p0_count']} P0 finding"
                f"{'' if parity_payload['p0_count'] == 1 else 's'}. "
                f"See {memo_prep._rel(parity_path)}."
            )
            timing["status"] = "warning"
            timing["warning"] = msg
            failure_message = msg
            payload = {
                "stage": "chinese_parity_warning",
                "message": msg,
                "phase": "chinese_parity_gate",
                "parity_report": memo_prep._rel(parity_path),
                "findings": parity_payload["findings"][:10],
            }
            if recovered:
                payload["recovered"] = True
            failure_payload = payload

    if failure_payload:
        stream.emit("stage", **failure_payload)

    _update_report(report_id, memo_chinese_parity=parity_payload)
    return parity_payload, failure_message


def _lint_memo_quality_gate(
    *,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    recovered: bool = False,
) -> tuple[memo_quality_lint.MemoLintResult, Path]:
    memo_path = memo_paths_abs["en"]
    with _timed_phase(
        stream,
        phase="memo_quality_gate",
        recovered=recovered,
        english_memo=memo_prep._rel(memo_path),
    ) as timing:
        lint_result = _lint_memo(memo_path, _structure_for_run(run_dir), run_dir)
        lint_path = run_dir / "logs" / "memo_quality_lint.md"
        lint_path.write_text(
            memo_quality_lint.render_markdown_report(lint_result),
            encoding="utf-8",
        )
        lint_payload = lint_result.to_dict()
        timing["lint_report"] = memo_prep._rel(lint_path)
        timing["finding_count"] = lint_payload.get("finding_count")
        timing["p0_count"] = lint_payload.get("p0_count")
        if lint_result.has_blocking_findings:
            timing["status"] = "failed"
    return lint_result, lint_path


def _ic_memo_frame(company_name: str, locale: str) -> dict:
    """The document frame of the IC decision memo: it never leaves BSH, and
    the file says so on every page."""
    if locale == "zh":
        return {
            "locale": "zh",
            "header_text": f"{company_name} | 投委会决策备忘录（内部）",
            "stamp_text": "内部文件 — 仅供投委会",
            "footer_label": "伯克利峰会资本 — 内部文件，请勿外传",
            "doc_title": f"{company_name} — 投委会决策备忘录",
        }
    return {
        "locale": "en",
        "header_text": f"{company_name} | IC decision memo — internal",
        "stamp_text": "INTERNAL — IC ONLY",
        "footer_label": "Berkeley Summit House — internal, do not forward",
        "doc_title": f"{company_name} — IC Decision Memo",
    }


def _run_internal_diligence_memo(
    *,
    report_id: str,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    memo_paths_abs: dict[str, Path],
    internal_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    result: dict,
    analysis_session_path: Path | None,
    lessons_path: Path | None,
    scope_check: dict | None,
    warnings: list[str],
    english_only: bool = False,
) -> dict:
    """Write and render the internal IC decision memo (English and Chinese
    from one call). Returns the runner result (``ok`` False with ``error``
    on any failure) — never fails the run: the LP memo is already rendered
    and gated, and the caller turns a failure into a warning."""
    with _timed_phase(
        stream,
        phase="memo_internal_diligence",
        run_id=run_id,
    ) as timing:
        md_path = internal_paths_abs.get("md")
        docx_path = internal_paths_abs.get("docx")
        md_zh = internal_paths_abs.get("md_zh")
        docx_zh = internal_paths_abs.get("docx_zh")
        if not md_path or not docx_path:
            message = "Report record is missing internal diligence memo paths."
            timing["status"] = "failed"
            timing["error"] = message
            _note_internal_memo_failure(stream=stream, message=message)
            return {"ok": False, "error": message}

        timing["markdown_path"] = memo_prep._rel(md_path)
        timing["docx_path"] = memo_prep._rel(docx_path)
        _update_report(
            report_id,
            stage="Writing the IC decision memo",
            progress=92,
        )
        # The LP memo's accepted package is what the IC memo's numbers must
        # match; an English-only delivery has only the English package.
        package_path = (
            _english_package_path(run_dir)
            if english_only or not _memo_package_path(run_dir).exists()
            else _memo_package_path(run_dir)
        )
        # The IC memo only reads the finished package, so it runs on Claude
        # whatever engine wrote the LP memo: a Gemini run used to lose its
        # IC memo to the Claude-only stage error. The pin is restored
        # afterwards so the rest of the run stays on its own engine.
        run_engine = memo_engine.run_engine(run_dir)
        engine_pinned = run_engine == "gemini"
        if engine_pinned:
            memo_engine.register_run_engine(run_dir, "claude")
            timing["engine"] = "claude"
            stream.emit(
                "stage",
                stage="internal_memo_engine",
                message=(
                    "Writing the IC decision memo on Claude (the LP memo was "
                    f"written on {run_engine}; the IC memo only reads it)"
                ),
            )
        try:
            internal_result = claude_runner.run_internal_diligence_memo(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                settings_path=memo_prep.SETTINGS_FILE,
                companies_yaml_path=_run_companies_yaml(run_dir),
                memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
                internal_markdown_path=md_path,
                internal_markdown_path_zh=md_zh,
                package_path=package_path,
                research_dir=_research_dir_for(company_slug),
                analysis_session_path=analysis_session_path,
                lessons_path=lessons_path,
                scope_check=scope_check,
                warnings=warnings,
                progress=stream,
                timeout_sec=1200,
            )
        finally:
            if engine_pinned:
                memo_engine.register_run_engine(run_dir, run_engine)
        timing["claude_cost_usd"] = internal_result.get("cost_usd")
        timing["claude_duration_ms"] = internal_result.get("duration_ms")
        if not internal_result.get("ok"):
            message = internal_result.get("error") or "Internal diligence memo failed."
            timing["status"] = "failed"
            timing["error"] = message
            _note_internal_memo_failure(stream=stream, message=message)
            return {**internal_result, "ok": False, "error": message}

        _update_report(
            report_id,
            stage="Rendering the IC decision memo DOCX",
            progress=94,
        )
        stream.emit(
            "stage",
            stage="rendering_internal_memo_docx",
            message="Rendering the IC decision memo DOCX",
            markdown_path=memo_prep._rel(md_path),
        )
        internal_files: list[dict] = []
        for locale, md, docx in (("en", md_path, docx_path), ("zh", md_zh, docx_zh)):
            if not md or not docx:
                continue
            if locale == "zh" and not md.exists():
                # The Chinese half is a companion to the companion: its
                # absence costs a warning line, never the English IC memo.
                stream.emit(
                    "stage",
                    stage="internal_memo_zh_missing",
                    message="The IC decision memo came back without its Chinese version",
                )
                timing["zh_missing"] = True
                continue
            try:
                internal_memo_renderer.render_internal_memo(
                    md,
                    docx,
                    zh_money_form=True,
                    **_ic_memo_frame(company_name, locale),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "IC decision memo render failed for report %s (%s)",
                    report_id,
                    locale,
                )
                message = (
                    "Internal diligence memo render failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                if locale == "zh":
                    timing["zh_error"] = message
                    stream.emit("stage", stage="internal_memo_zh_render_failed", message=message)
                    continue
                timing["status"] = "failed"
                timing["error"] = message
                _note_internal_memo_failure(stream=stream, message=message)
                return {**internal_result, "ok": False, "error": message}
            internal_files.append(
                {
                    "kind": "internal_diligence_memo",
                    "language": locale,
                    "markdown_path": memo_prep._rel(md),
                    "path": memo_prep._rel(docx),
                }
            )
        _update_report(report_id, internal_memo_files=internal_files)
        timing["languages"] = [entry["language"] for entry in internal_files]
        return internal_result


def _note_internal_memo_failure(
    *,
    stream: job_progress.ProgressLog,
    message: str,
) -> None:
    """The IC decision memo failed: say so on the stream. The run itself
    goes on — the caller records a warning."""
    stream.emit(
        "thread_failed",
        thread=claude_runner.MEMO_PHASE6_THREAD,
        error=message,
    )
    stream.emit(
        "stage",
        stage="internal_memo_failed",
        message=f"IC decision memo was not written: {message[:500]}",
        phase="internal_diligence_memo",
    )


def _combined_result(primary: dict, secondary: dict | None) -> dict:
    if not secondary:
        return dict(primary)
    out = dict(primary)
    total_cost = (primary.get("cost_usd") or 0) + (secondary.get("cost_usd") or 0)
    total_duration = (primary.get("duration_ms") or 0) + (
        secondary.get("duration_ms") or 0
    )
    out["cost_usd"] = total_cost or primary.get("cost_usd") or secondary.get("cost_usd")
    out["duration_ms"] = (
        total_duration
        or primary.get("duration_ms")
        or secondary.get("duration_ms")
    )
    return out


def _fast_pass_markdown(
    spec: _FastMemoPassSpec,
    payload: dict | None,
    error: str | None,
) -> str:
    lines = [f"# {spec.label}", ""]
    if error:
        lines.extend([
            "## Status",
            "",
            f"Pass failed: {error}",
            "",
            "The memo package pass must treat this as an explicit evidence gap.",
            "",
        ])
        return "\n".join(lines)

    data = payload if isinstance(payload, dict) else {}
    lines.extend([
        "## Summary",
        "",
        str(
            data.get("summary")
            or "No source-backed summary was available for this analysis pass."
        ).strip(),
        "",
        "## Key Findings",
        "",
    ])
    findings = data.get("key_findings") if isinstance(data.get("key_findings"), list) else []
    if findings:
        lines.append("| Claim | Finding | Evidence Class | Implication | Confidence |")
        lines.append("|---|---|---|---|---|")
        for item in findings:
            if not isinstance(item, dict):
                continue
            cells = [
                str(item.get(key) or "").replace("\n", " ").strip()
                for key in (
                    "claim",
                    "finding",
                    "evidence_class",
                    "implication",
                    "confidence",
                )
            ]
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("- No source-backed key findings were available.")

    lines.extend(["", "## Supporting Evidence", ""])
    evidence = (
        data.get("supporting_evidence")
        if isinstance(data.get("supporting_evidence"), list)
        else []
    )
    if evidence:
        for item in evidence:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "Source").strip()
            klass = str(item.get("source_class") or "source").strip()
            detail = str(item.get("detail") or "").strip()
            as_of = str(item.get("as_of") or "").strip()
            suffix = f" ({as_of})" if as_of else ""
            lines.append(f"- **{source}** [{klass}]{suffix}: {detail}")
    else:
        lines.append("- No supporting source evidence was available.")

    lines.extend(["", "## Disconfirming Evidence", ""])
    disconfirming = (
        data.get("disconfirming_evidence")
        if isinstance(data.get("disconfirming_evidence"), list)
        else []
    )
    lines.extend(
        f"- {str(item).strip()}" for item in disconfirming if str(item).strip()
    )
    if not disconfirming:
        lines.append("- No disconfirming evidence was identified in this pass.")

    lines.extend(["", "## Evidence Limits And Valuation Treatment", ""])
    questions = data.get("remaining_evidence_limits")
    if not isinstance(questions, list):
        questions = (
            data.get("open_questions")
            if isinstance(data.get("open_questions"), list)
            else []
        )
    lines.extend(f"- {str(item).strip()}" for item in questions if str(item).strip())
    if not questions:
        lines.append("- No material evidence limits were identified beyond the source base.")

    lines.extend(["", "## Investment Implications", ""])
    memo_uses = data.get("investment_implications")
    if not isinstance(memo_uses, list):
        memo_uses = data.get("memo_uses") if isinstance(data.get("memo_uses"), list) else []
    lines.extend(f"- {str(item).strip()}" for item in memo_uses if str(item).strip())
    if not memo_uses:
        lines.append("- No incremental investment implication guidance was available.")

    lines.append("")
    return "\n".join(lines)


def _normalize_private_analysis_artifact(content: str) -> str:
    replacements = (
        (r"(?im)^#\s*Pre-Mortem\s*$", "# Downside Scenario"),
        (r"(?im)^#\s*Reverse IC\s*$", "# Countercase"),
        (
            r"(?im)^#\s*(Validation Log|Validation & Assumptions Log)\s*$",
            "# Source Treatment And Assumptions",
        ),
    )
    normalized = content
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def _write_fast_pass_outputs(*, run_dir: Path, result: _FastMemoPassResult) -> None:
    analysis_dir = run_dir / "analysis"
    fast_dir = analysis_dir / "fast"
    fast_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (fast_dir / f"{result.spec.pass_id}.json").write_text(
        json.dumps(
            {
                "pass_id": result.spec.pass_id,
                "label": result.spec.label,
                "artifact_filename": result.spec.artifact_filename,
                "status": "ok" if result.ok else "failed",
                "error": result.error,
                "duration_ms": result.duration_ms,
                "cost_usd": result.cost_usd,
                "usage": result.usage,
                "data": result.data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (analysis_dir / result.spec.artifact_filename).write_text(
        _fast_pass_markdown(result.spec, result.data, result.error),
        encoding="utf-8",
    )


def _write_fast_synthesis_artifacts(run_dir: Path, artifacts: dict) -> None:
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    mapping = (
        ("claim_register_md", "claim_register.md", (), "Claim Register"),
        (
            "scenario_swim_lanes_md",
            "scenario_swim_lanes.md",
            (),
            "Scenario Swim Lanes",
        ),
        (
            "downside_scenario_md",
            "downside_scenario.md",
            ("pre_mortem_md",),
            "Downside Scenario",
        ),
        (
            "countercase_md",
            "countercase.md",
            ("reverse_ic_md",),
            "Countercase",
        ),
        (
            "source_treatment_assumptions_md",
            "source_treatment_assumptions.md",
            ("validation_log_md",),
            "Source Treatment And Assumptions",
        ),
        (
            "risk_sensitivities_md",
            "risk_sensitivities.md",
            ("gating_questions_md",),
            "Risk Sensitivities",
        ),
        (
            "content_coverage_md",
            "content_coverage.md",
            (),
            "Content Coverage",
        ),
    )
    for key, filename, aliases, title in mapping:
        content = str(artifacts.get(key) or "").strip()
        if not content:
            for alias in aliases:
                content = str(artifacts.get(alias) or "").strip()
                if content:
                    break
        if not content:
            content = (
                f"# {title}\n\n"
                "No source-backed material was available for this private analysis artifact."
            )
        content = _normalize_private_analysis_artifact(content)
        (analysis_dir / filename).write_text(content.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_fast_memo_pass(
    *,
    spec: _FastMemoPassSpec,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    stream: job_progress.ProgressLog,
    research_dir: Path | None,
    lessons_path: Path | None,
    scope_check: dict | None,
    warnings: list[str],
    structure: memo_structure.MemoStructure | None = None,
    common_context: str | None = None,
) -> _FastMemoPassResult:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    sub_progress = _ThreadProgress(stream, spec.label)
    type_focus = (
        memo_structure.company_type_research_focus(structure, spec.pass_id)
        if structure is not None
        else ""
    )
    type_profile = (
        memo_structure.load_company_type(structure.company_type)
        if structure is not None
        else None
    )
    sub_progress.emit(
        "thread_started",
        title=spec.label,
        pass_id=spec.pass_id,
        artifact=spec.artifact_filename,
    )
    _emit_phase_timing(
        stream,
        phase=f"fast_pass:{spec.pass_id}",
        status="started",
        started_at=started_at,
        started_monotonic=started_monotonic,
        thread=spec.label,
    )
    def _attempt() -> tuple[dict | None, str | None]:
        return claude_runner.run_memo_fast_analysis_pass(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            pass_id=spec.pass_id,
            pass_label=spec.label,
            artifact_filename=spec.artifact_filename,
            focus=spec.focus,
            settings_path=memo_prep.SETTINGS_FILE,
            companies_yaml_path=_run_companies_yaml(run_dir),
            research_dir=research_dir,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            progress=sub_progress,
            type_focus=type_focus or None,
            type_label=type_profile.label["en"] if type_profile else None,
            common_context=common_context,
        )

    try:
        data, error = _attempt()
        # The CLI rejecting every structured answer is a stumble, not a
        # verdict: the model submits an object missing a required property
        # (or the JSON as a string), and runs out of retries. The SAME
        # schema and prompt succeed on the sibling passes in the same run —
        # on 2026-09-16 seven of eight landed while `alternative_explanations`
        # died after four rejections, all of them "must have required
        # property 'key_findings'". A lost pass costs the memo a whole line
        # of argument, so it is worth one more attempt.
        if error and claude_runner.is_structured_output_failure(error):
            logger.warning(
                "fast memo pass %s had every structured answer rejected (%s); "
                "retrying",
                spec.pass_id,
                error,
            )
            sub_progress.emit(
                "stage",
                stage="memo_pass_schema_retry",
                message=(
                    f"{spec.label}: the tool rejected every structured "
                    "answer — running it again"
                ),
            )
            data, error = _attempt()
        elif error and _retryable_pass_error(error):
            # A dropped connection or a pass that stalled or timed out is
            # worth one more go: a lost pass costs the memo a line of
            # argument. Never a provider limit, a dead login or a cancel —
            # those fail the same way again, at a cost.
            logger.warning(
                "fast memo pass %s hit a retryable failure (%s); retrying",
                spec.pass_id,
                error,
            )
            sub_progress.emit(
                "stage",
                stage="memo_pass_transient_retry",
                message=(
                    f"{spec.label}: {str(error)[:160]} — running it again"
                ),
            )
            data, error = _attempt()
        # A placeholder answer is worse than no answer: it is indistinguishable
        # from real work downstream. Try once more, then fail the pass loudly.
        if not error:
            reason = _fast_pass_degenerate_reason(data)
            if reason:
                logger.warning(
                    "fast memo pass %s returned placeholder output (%s); retrying",
                    spec.pass_id,
                    reason,
                )
                sub_progress.emit(
                    "stage",
                    stage="memo_pass_retry",
                    message=(
                        f"{spec.label}: answer looked like placeholder text "
                        f"({reason}) — running it again"
                    ),
                )
                data, error = _attempt()
                if not error:
                    reason = _fast_pass_degenerate_reason(data)
                    if reason:
                        data, error = None, (
                            f"pass returned placeholder output twice: {reason}"
                        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("fast memo pass crashed: %s", spec.pass_id)
        data, error = None, f"{type(exc).__name__}: {exc}"
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    result = _FastMemoPassResult(
        spec=spec,
        data=data,
        error=error,
        duration_ms=duration_ms,
        cost_usd=round(
            _as_float((data or {}).get("claude_cost_usd")) or sub_progress.cost_usd,
            6,
        ),
        usage=(data or {}).get("claude_usage")
        if isinstance((data or {}).get("claude_usage"), dict)
        else None,
    )
    _write_fast_pass_outputs(run_dir=run_dir, result=result)
    sub_progress.emit(
        "thread_finished" if result.ok else "thread_failed",
        error=result.error or None,
        pass_id=spec.pass_id,
        artifact=spec.artifact_filename,
        duration_ms=duration_ms,
    )
    _emit_phase_timing(
        stream,
        phase=f"fast_pass:{spec.pass_id}",
        status="finished" if result.ok else "failed",
        started_at=started_at,
        started_monotonic=started_monotonic,
        thread=spec.label,
        error=result.error,
        cost_usd=result.cost_usd,
        claude_duration_ms=_as_int((data or {}).get("claude_duration_ms")),
        usage=result.usage,
    )
    return result


_PASS_TIMEOUT_MARKERS = ("timed out", "stalled after", "without output", "did not exit cleanly")


def _retryable_pass_error(error: str | None) -> bool:
    """One more attempt is worth it: a transient transport error, or a pass
    that timed out or stalled. Never a provider limit, a dead login, a
    cancel or a shutdown."""
    text = str(error or "")
    if not text:
        return False
    if (
        claude_runner.provider_limit_reason(text)
        or claude_runner.auth_failure_reason(text)
        or text in (
            claude_runner.MEMO_RUN_CANCELLED_ERROR,
            claude_runner.SERVER_SHUTTING_DOWN_ERROR,
            claude_runner.CLAUDE_NOT_SIGNED_IN_ERROR,
        )
    ):
        return False
    if claude_runner.is_transient_claude_error(text):
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in _PASS_TIMEOUT_MARKERS)


def _pass_stop_cause(error: str | None) -> str | None:
    """The cause a resume must stop on instead of spending more: a provider
    limit, a dead login or a cancel, named for the reader."""
    text = str(error or "")
    if not text:
        return None
    if text == claude_runner.MEMO_RUN_CANCELLED_ERROR:
        return "cancelled by user"
    if text == claude_runner.SERVER_SHUTTING_DOWN_ERROR:
        return "the server is shutting down"
    if claude_runner.auth_failure_reason(text) or text == claude_runner.CLAUDE_NOT_SIGNED_IN_ERROR:
        return "the Claude CLI is not signed in"
    if claude_runner.provider_limit_reason(text):
        return f"Claude usage limit: {text[:200]}"
    return None


_ALL_FAST_PASSES_FAILED_MESSAGE = "All fast memo analysis passes failed."


def _fast_passes_failure_message(pass_results: list[_FastMemoPassResult]) -> str:
    """The all-passes-failed message, naming the first pass error."""
    for result in pass_results:
        detail = str(result.error or "").strip()
        if detail and detail != claude_runner.MEMO_RUN_CANCELLED_ERROR:
            return f"All fast memo analysis passes failed: {detail}"
    return _ALL_FAST_PASSES_FAILED_MESSAGE


def _recorded_fast_phase2_failure(report_id: str) -> str:
    """The failure message ``_run_fast_phase2`` recorded on the report."""
    report = storage.get_report(report_id) or {}
    return str(report.get("failure_detail") or _ALL_FAST_PASSES_FAILED_MESSAGE)


def _pass_common_context(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    research_dir: Path | None,
    lessons_path: Path | None,
    scope_check: dict | None,
    warnings: list[str],
    structure: memo_structure.MemoStructure | None = None,
) -> str:
    """The analysis passes' shared context for this run: the run-wide block
    plus, when on file, the fund-policy stage and jurisdiction (passed only
    once the builder takes them) and the open reader flags inlined as
    untrusted reader notes. A function of run-wide inputs only, so every
    pass still sends identical bytes."""
    import inspect

    kwargs: dict[str, Any] = dict(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        settings_path=memo_prep.SETTINGS_FILE,
        companies_yaml_path=_run_companies_yaml(run_dir),
        research_dir=research_dir,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
    )
    accepted = inspect.signature(claude_runner.memo_fast_pass_common_context).parameters
    report = _report_for_run_dir(run_dir)
    jurisdiction = str((report or {}).get("jurisdiction") or "") or None
    if jurisdiction and "jurisdiction" in accepted:
        kwargs["jurisdiction"] = jurisdiction
    stage = _fund_policy_stage(report, structure)
    if stage and "fund_policy_stage" in accepted:
        kwargs["fund_policy_stage"] = stage
    context = claude_runner.memo_fast_pass_common_context(**kwargs)
    flags = _reader_flags_block(run_dir)
    if flags:
        context = context.rstrip("\n") + "\n\n" + flags + "\n"
    return context


def _report_for_run_dir(run_dir: Path) -> dict | None:
    """The report whose run folder this is (the record carries the run's
    prep-time facts: jurisdiction, stage, template)."""
    rel = memo_prep._rel(run_dir)
    for report in storage.list_reports():
        if str(report.get("run_dir") or "") == rel:
            return report
    return None


def _fund_policy_stage(report: dict | None, structure) -> str | None:
    """The fund-policy stage (early | growth | late) a run is judged
    against: the structure's declared stage — what the spine and the IC
    memo default to — else the stage prep classified."""
    for candidate in (
        getattr(structure, "declared_stage", None) if structure is not None else None,
        ((report or {}).get("structure_stage") or {}).get("stage")
        if isinstance((report or {}).get("structure_stage"), dict)
        else None,
    ):
        value = str(candidate or "").strip().lower().replace("_compact", "")
        if value in ("early", "growth", "late"):
            return value
    return None


def _run_fast_phase2(
    *,
    report_id: str,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    company_name: str,
    company_slug: str,
    run_id: str,
    research_dir: Path,
    lessons_path: Path | None,
    scope_check: dict | None,
    warnings: list[str],
    speculator=None,
    structure: memo_structure.MemoStructure | None = None,
) -> tuple[list[_FastMemoPassResult] | None, float, int]:
    """Phase 2: the parallel analysis passes (12 of them).

    Extracted from the straight-line pipeline so Memo Studio's standalone
    investigation can run it without Phase 3+. Writes only
    ``analysis/fast/*.json`` and ``analysis/*.md``. Returns
    ``(pass_results, cost_usd, worker_duration_ms)``; when every pass fails
    it records the failure on the report, emits the stream error, and
    returns ``None`` pass results — shutting down the caller's speculator
    and chaser stays with the caller.
    """
    phase2_started_at = _now_iso()
    phase2_started = time.monotonic()
    stream.emit(
        "thread_started",
        thread=claude_runner._MEMO_PHASE2_THREAD,
        title=claude_runner._MEMO_PHASE2_THREAD,
    )
    worker_count = min(_memo_fast_max_workers(), len(_FAST_MEMO_PASSES))
    for index, spec in enumerate(_FAST_MEMO_PASSES, start=1):
        stream.emit(
            "thread_planned",
            thread=spec.label,
            title=spec.label,
            phase_index=2 + (index / 100),
            parent_thread=claude_runner._MEMO_PHASE2_THREAD,
            group="memo_fast_pass",
            pass_id=spec.pass_id,
            artifact=spec.artifact_filename,
            estimate_ms=180_000,
            description=(
                f"Fast memo analysis pass {index}/{len(_FAST_MEMO_PASSES)}. "
                f"Runs with up to {worker_count} parallel Claude workers."
            ),
        )
    # One shared, cached system-prompt block for the whole fan-out. Built
    # here and not inside each pass so every pass sends byte-identical
    # bytes and they collapse into a single prompt-cache entry.
    pass_common_context = _pass_common_context(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        research_dir=research_dir,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        structure=structure,
    )
    stream.emit(
        "stage",
        stage="memo_fast_parallel_dispatch",
        message=(
            f"Running {len(_FAST_MEMO_PASSES)} memo analysis passes "
            f"with up to {worker_count} parallel workers"
        ),
        thread=claude_runner._MEMO_PHASE2_THREAD,
        passes=[spec.label for spec in _FAST_MEMO_PASSES],
        max_workers=worker_count,
    )
    _emit_phase_timing(
        stream,
        phase="memo_fast_parallel_analysis",
        status="started",
        started_at=phase2_started_at,
        started_monotonic=phase2_started,
    )
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        # as_completed (not pool.map): each completion is a signal the
        # speculative spine may be waiting on.
        futures = {
            pool.submit(
                _run_fast_memo_pass,
                spec=spec,
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                stream=stream,
                research_dir=research_dir,
                lessons_path=lessons_path,
                scope_check=scope_check,
                warnings=warnings,
                structure=structure,
                common_context=pass_common_context,
            ): spec
            for spec in _FAST_MEMO_PASSES
        }
        results_by_id: dict[str, _FastMemoPassResult] = {}
        for future in as_completed(futures):
            spec = futures[future]
            try:
                pass_result = future.result()
            except Exception as exc:  # noqa: BLE001
                pass_result = _FastMemoPassResult(
                    spec=spec,
                    data=None,
                    error=f"pass crashed: {exc}",
                    duration_ms=0,
                    cost_usd=0.0,
                )
            results_by_id[spec.pass_id] = pass_result
            if speculator is not None:
                try:
                    speculator.note_pass_result(
                        spec.pass_id, pass_result.ok
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "speculative spine pass notification failed",
                        exc_info=True,
                    )
        pass_results = [
            results_by_id[spec.pass_id] for spec in _FAST_MEMO_PASSES
        ]
    cost_usd = sum(result.cost_usd for result in pass_results)
    worker_duration_ms = sum(result.duration_ms for result in pass_results)
    stream.emit("thread_finished", thread=claude_runner._MEMO_PHASE2_THREAD)
    _emit_phase_timing(
        stream,
        phase="memo_fast_parallel_analysis",
        status="finished",
        started_at=phase2_started_at,
        started_monotonic=phase2_started,
        ok_count=sum(1 for result in pass_results if result.ok),
        error_count=sum(1 for result in pass_results if not result.ok),
        pass_count=len(pass_results),
        worker_count=worker_count,
        worker_duration_ms=worker_duration_ms,
    )
    if not any(result.ok for result in pass_results):
        message = _fast_passes_failure_message(pass_results)
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Fast memo analysis failed",
            failure_phase="fast_parallel_analysis",
            failure_detail=message,
            error=message,
        )
        stream.emit("error", error=message, phase="fast_parallel_analysis")
        return None, cost_usd, worker_duration_ms
    return pass_results, cost_usd, worker_duration_ms


def _resolve_company_type(
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
) -> dict | None:
    """Phase 1 company type: the registry-sourced value prep persisted,
    else one tool-free classifier call. A classifier failure files the
    company under `other` and never blocks the run. Publishes the result
    to the report (UI card) and the stream either way."""
    existing = report.get("company_type")
    if (
        isinstance(existing, dict)
        and existing.get("type") in memo_structure.COMPANY_TYPE_KEYS
    ):
        return existing
    company = storage.get_company(str(report.get("company_id") or "")) or {}
    info: dict | None = None
    try:
        info = claude_runner.run_memo_company_type_classifier(
            run_dir=run_dir, company=company, progress=stream
        )
    except Exception:  # noqa: BLE001
        logger.exception("company type classifier crashed")
    if not info:
        info = {"type": "other", "source": "classifier_failed"}
    try:
        storage.update_report(report_id, company_type=info)
    except Exception:  # noqa: BLE001
        logger.warning("company-type publish failed", exc_info=True)
    label = memo_structure.COMPANY_TYPE_LABELS.get(info["type"], {}).get(
        "en", info["type"]
    )
    stream.emit(
        "stage",
        stage="company_type",
        message=f"Company type: {label} ({info.get('source')})",
        thread=claude_runner._MEMO_PHASE1_THREAD,
        company_type=info["type"],
        source=info.get("source"),
        confidence=info.get("confidence"),
    )
    return info


def _run_fast_memo_pipeline(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    company_name: str,
    company_slug: str,
    run_id: str,
    memo_paths_abs: dict[str, Path],
    analysis_session_path: Path | None,
    lessons_path: Path | None,
) -> dict:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    cost_usd = 0.0
    worker_duration_ms = 0
    warnings = list(report.get("warnings") or [])
    scope_check = report.get("scope_check")
    research_dir = _research_dir_for(company_slug)
    memo_paths = {k: str(v) for k, v in memo_paths_abs.items()}
    # The report structure for this run: prep classified the stage
    # (auto type) or pinned late (explicit type); active_structure maps
    # it to a profile — late v1 for everyone until the v2 flag flips.
    stage_info = report.get("structure_stage")
    structure_stage = (
        str(stage_info.get("stage") or "late")
        if isinstance(stage_info, dict)
        else "late"
    )
    structure_mode = str(report.get("structure_mode") or "full")
    # The run's own memo template ("v1" | "v2", written at prep from the
    # per-run override / Settings / env default); legacy records carry none
    # and follow the env flag as before.
    structure_version = _report_structure_version(report)
    # Provisional (type-less) structure for the starting event; the Phase
    # 1 thread classifies the company type below and re-resolves it with
    # the type's lens and weight overlay.
    structure = memo_structure.active_structure(
        structure_stage, structure_mode, version=structure_version
    )
    _register_run_structure(run_dir, structure)
    model_quality = str(report.get("model_quality") or "best")
    claude_runner.register_memo_run_quality(run_dir, model_quality)
    # Pinned per run, like the quality tier: a resume or repair pass must use
    # the engine the report was started with, not whatever the default is now.
    memo_engine.register_run_engine(run_dir, report.get("engine"))
    # BSH's check size, only when the owner set a real band: the one amount
    # the spine's recommendation sentence may commit.
    claude_runner.register_memo_run_check_size(run_dir, _check_size_text())
    _register_prior_view(report, run_dir)
    # Every page the run's agents fetch lands in the company's source cache
    # and the run's own manifest, so the next run starts from what this one
    # found and the fact check can trace the memo's figures to text on file.
    claude_runner.register_memo_run_source_capture(
        run_dir,
        company_id=str(report.get("company_id") or company_slug),
        run_id=run_id,
        research_dir=research_dir,
    )

    stream.emit(
        "stage",
        stage="memo_fast_pipeline_starting",
        message="Running fast memo pipeline with real parallel Claude workers",
        max_workers=_memo_fast_max_workers(),
        packet_mode=bool(analysis_session_path),
        structure_stage=structure.stage,
        structure_version=structure.version,
        model_quality=model_quality,
    )
    _emit_phase_timing(
        stream,
        phase="memo_fast_pipeline",
        status="started",
        started_at=started_at,
        started_monotonic=started_monotonic,
    )
    claude_runner.emit_memo_phase_planned(stream)

    stream.emit(
        "thread_started",
        thread=claude_runner._MEMO_PHASE1_THREAD,
        title=claude_runner._MEMO_PHASE1_THREAD,
    )
    stream.emit(
        "stage",
        stage="fast_intake_ready",
        message="Using prepared run folder, registry entry, and source folders",
        thread=claude_runner._MEMO_PHASE1_THREAD,
    )
    # The ledger is loaded again inside each prompt builder; this read is
    # observability only, so benchmark records show whether curated facts
    # were an input to this run.
    fact_ledger = claude_runner.load_memo_fact_ledger(research_dir)
    if fact_ledger:
        stream.emit(
            "stage",
            stage="memo_fact_ledger",
            message=(
                f"Curated fact ledger loaded ({len(fact_ledger)} chars); "
                "injecting into analysis passes and the spine"
            ),
            thread=claude_runner._MEMO_PHASE1_THREAD,
            chars=len(fact_ledger),
            path=str(research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME),
        )
    elif claude_runner._memo_fact_ledger_enabled():
        # Say so out loud: without a ledger the run's headline facts depend
        # on what each analysis pass happens to retrieve (the fact lottery).
        stream.emit(
            "stage",
            stage="memo_fact_ledger_missing",
            message=(
                "No curated fact ledger for this company; headline facts "
                "depend on per-pass retrieval. Add dated facts at "
                f"{research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME}"
            ),
            thread=claude_runner._MEMO_PHASE1_THREAD,
            path=str(research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME),
        )
    company_type_info = _resolve_company_type(report_id, report, run_dir, stream)
    company_type = (
        str(company_type_info.get("type") or "") if company_type_info else ""
    )
    if company_type:
        structure = memo_structure.active_structure(
            structure_stage,
            structure_mode,
            company_type,
            version=structure_version,
        )
        _register_run_structure(run_dir, structure)
    stream.emit("thread_finished", thread=claude_runner._MEMO_PHASE1_THREAD)

    # The chaser exists before Phase 2 so the speculative spine can hand it
    # the envelope the moment the spine lands (idle until hooks fire).
    zh_chaser = None
    if _memo_zh_chasing_enabled():
        zh_chaser = claude_runner.BilingualChaser(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            stream=stream,
            structure=structure,
        )
    speculator = None

    if analysis_session_path:
        stream.emit(
            "thread_started",
            thread=claude_runner._MEMO_PHASE2_THREAD,
            title=claude_runner._MEMO_PHASE2_THREAD,
        )
        stream.emit(
            "stage",
            stage="memo_fast_packet_mode",
            message=(
                "Approved Memo Studio packet found; skipping parallel analysis "
                "subprocesses"
            ),
            thread=claude_runner._MEMO_PHASE2_THREAD,
            analysis_session_path=str(analysis_session_path),
        )
        stream.emit("thread_finished", thread=claude_runner._MEMO_PHASE2_THREAD)
        pass_results: list[_FastMemoPassResult] = []
    else:
        if claude_runner._memo_spine_speculative_enabled():
            speculator = claude_runner.SpeculativeEnglish(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                settings_path=memo_prep.SETTINGS_FILE,
                companies_yaml_path=_run_companies_yaml(run_dir),
                memo_paths=memo_paths,
                research_dir=research_dir,
                analysis_session_path=analysis_session_path,
                lessons_path=lessons_path,
                scope_check=scope_check,
                warnings=warnings,
                stream=stream,
                all_pass_ids=[spec.pass_id for spec in _FAST_MEMO_PASSES],
                on_spine=zh_chaser.on_spine if zh_chaser is not None else None,
                on_section=(
                    zh_chaser.on_section if zh_chaser is not None else None
                ),
                early_sections=claude_runner._memo_section_early_start_enabled(),
                structure=structure,
            )
        pass_results, phase2_cost_usd, phase2_duration_ms = _run_fast_phase2(
            report_id=report_id,
            run_dir=run_dir,
            stream=stream,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            research_dir=research_dir,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            speculator=speculator,
            structure=structure,
        )
        cost_usd += phase2_cost_usd
        worker_duration_ms += phase2_duration_ms
        if pass_results is None:
            if speculator is not None:
                cost_usd += speculator.cost_usd
                speculator.shutdown()
            cost_usd += _shutdown_side_agent(zh_chaser, cancel=True)
            return {
                "ok": False,
                "error": _recorded_fast_phase2_failure(report_id),
                "cost_usd": cost_usd,
            }

    return _run_fast_synthesis(
        run_dir=run_dir,
        stream=stream,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        zh_chaser=zh_chaser,
        speculator=speculator,
        cost_usd=cost_usd,
        worker_duration_ms=worker_duration_ms,
        started_at=started_at,
        started_monotonic=started_monotonic,
        structure=structure,
        report_id=report_id,
    )


def _assert_spine_pin_allowed(
    pinned_spine_path: Path | None, memo_mode: str
) -> None:
    """Belt-and-braces: a pinned spine carries studio card edits, and only
    the studio generate path may supply one. One-Click ("auto") memos must
    never inherit cards from a previous investigation — a violated
    invariant here means possible studio contamination and must fail loudly
    rather than silently produce a card-influenced One-Click memo."""
    if pinned_spine_path is not None and memo_mode != "studio":
        raise ValueError(
            "pinned_spine_path is studio-only; "
            f"memo_mode={memo_mode!r} must not carry card pins"
        )


def _company_stage_spine_hook(report_id: str, stream):
    """Publish the company's stage the moment a run's spine is accepted.

    The spine pins ``shared_facts.stage`` right after Phase 2 research,
    and the pin gate holds sections to it — that is the first
    evidence-confirmed stage judgment of a run, so it (not the prep-time
    registry guess) is what the UI shows as "Company stage". Fires once;
    spines without a stage pin (late v1 / studio-composed) publish
    nothing."""
    fired = {"done": False}

    def _publish(spine_payload) -> None:
        if fired["done"]:
            return
        shared = (spine_payload or {}).get("shared_facts") or {}
        stage = str(shared.get("stage") or "").strip().lower()
        if stage not in ("early", "growth", "late"):
            return
        fired["done"] = True
        try:
            _update_report(
                report_id,
                company_stage={"stage": stage, "source": "memo_spine"},
            )
        except Exception:  # noqa: BLE001
            logger.warning("company-stage publish failed", exc_info=True)
        stream.emit(
            "stage",
            stage="company_stage",
            message=f"Company stage confirmed from the pinned spine: {stage}",
            classification=stage,
        )

    return _publish


def _compose_spine_hooks(*hooks):
    active = [hook for hook in hooks if hook is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    def _fire(spine_payload) -> None:
        for hook in active:
            hook(spine_payload)

    return _fire


def _stamp_run_facts(package: dict, run_dir: Path) -> None:
    """What the memo was written from, stamped on the accepted English
    package's ``run`` block as plain data (no en/zh slots for the translator
    to fill): ``analysis_coverage`` (the Phase-2 passes it had),
    ``built_from`` ({research_docs, calls, founder_updates}) and
    ``deal_terms_on_file``. All optional; never raises."""
    try:
        run_block = package.setdefault("run", {})
        if not isinstance(run_block, dict):
            return
        coverage = _analysis_coverage(run_dir)
        if coverage is not None:
            run_block["analysis_coverage"] = {
                "passes_total": coverage["passes_total"],
                "passes_ok": coverage["passes_ok"],
                "missing": list(coverage["missing"]),
            }
        inputs = _run_inputs(run_dir)
        if isinstance(inputs.get("built_from"), dict):
            run_block["built_from"] = dict(inputs["built_from"])
        if "deal_terms_on_file" in inputs:
            run_block["deal_terms_on_file"] = bool(inputs["deal_terms_on_file"])
    except Exception:  # noqa: BLE001
        logger.warning("run facts stamp failed", exc_info=True)


# ---- what generated the run ---------------------------------------------------------------


def _writer_role(models: dict[str, str]) -> str | None:
    """The role whose model wrote the delivered English prose: the resume
    agent when it rewrote the package; the monolithic English call when it
    ran (alone, or as the parallel wave's fallback); else the section wave;
    else the legacy one-shot skill or the Buffett skill."""
    if "RESUME" in models:
        return "RESUME"
    if "ENGLISH" in models:
        return "ENGLISH"
    for role in ("SECTION", "SKILL", "BUFFETT"):
        if role in models:
            return role
    return None


def _generated_with(
    report: dict | None,
    run_dir: Path,
    *,
    structure: memo_structure.MemoStructure | None = None,
    buffett: bool = False,
) -> dict:
    """What generated this run, as recorded — never the tier's alias: the
    engine, the quality tier, the template, the structure, the model that
    actually answered for each role that ran (claude_runner.memo_run_models),
    the English writer's and the translator's model, and the server's code
    version. Stamped as ``package["run"]["generated_with"]`` (the renderer's
    page-one line) and as the record's ``generated_with``."""
    report = report or {}
    models = claude_runner.memo_run_models(run_dir)
    engine = str(report.get("engine") or "").strip().lower() or memo_engine.run_engine(run_dir)
    writer_role = _writer_role(models)
    out: dict[str, Any] = {
        # Buffett memos run on Claude only.
        "engine": "claude" if buffett else (engine or "claude"),
        "quality": str(report.get("model_quality") or "best"),
        "models": models,
        "writer_model": models.get(writer_role) if writer_role else None,
        "translation_model": models.get("TRANSLATION")
        or models.get("SKILL")
        or models.get("BUFFETT"),
        "code_version": claude_runner.server_code_version(),
    }
    if not buffett:
        structure = structure or _structure_for_run(run_dir)
        version = _report_structure_version(report)
        if version is None:
            version = "v2" if structure.scorecard_weights() else "v1"
        mode = str(report.get("structure_mode") or "").strip() or (
            "compact" if structure.stage.endswith("_compact") else "full"
        )
        out["template"] = "ic_v2" if version == "v2" else "standard"
        out["structure"] = {
            "stage": structure.stage,
            "version": structure.version,
            "mode": mode,
        }
    else:
        out["template"] = "buffett"
    return out


def _stamp_generated_with(
    package: dict,
    report: dict | None,
    run_dir: Path,
    *,
    structure: memo_structure.MemoStructure | None = None,
    buffett: bool = False,
) -> dict | None:
    """``package["run"]["generated_with"]``; never raises. Returns it."""
    if not isinstance(package, dict):
        return None
    try:
        facts = _generated_with(report, run_dir, structure=structure, buffett=buffett)
    except Exception:  # noqa: BLE001
        logger.warning("generated_with stamp failed", exc_info=True)
        return None
    run_block = package.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        package["run"] = run_block
    previous = run_block.get("generated_with")
    if isinstance(previous, dict) and previous.get("code_version"):
        # The code that wrote the English is the memo's; a later Chinese
        # stage (Retry Chinese after a restart) adds its model, not its code.
        facts["code_version"] = previous["code_version"]
    run_block["generated_with"] = facts
    return facts


def _package_generated_with(package_path: Path) -> dict | None:
    """The ``generated_with`` stamp a package on disk carries (None for a
    package that predates it — never reconstructed after the fact)."""
    package = _package_on_disk(package_path)
    run_block = package.get("run") if isinstance(package, dict) else None
    stamp = run_block.get("generated_with") if isinstance(run_block, dict) else None
    return stamp if isinstance(stamp, dict) else None


def _generated_with_or_none(report: dict | None, run_dir: Path, **kwargs) -> dict | None:
    """``_generated_with`` for a record write; None (field untouched as
    null) if it cannot be built — never costs a finalize."""
    try:
        return _generated_with(report, run_dir, **kwargs)
    except Exception:  # noqa: BLE001
        logger.warning("generated_with failed", exc_info=True)
        return None


def _stamp_generated_with_on_disk(
    package_path: Path, report: dict | None, run_dir: Path
) -> dict | None:
    """Stamp ``generated_with`` into a package file (the bilingual package
    before it is rendered); a missing or unreadable file is left alone."""
    package = _package_on_disk(package_path)
    if package is None:
        return None
    facts = _stamp_generated_with(package, report, run_dir)
    if facts is not None:
        try:
            _write_json(package_path, package)
        except OSError:
            logger.warning("could not write generated_with into %s", package_path, exc_info=True)
    return facts


# ---- deterministic envelope facts ---------------------------------------------------------
#
# Stamped in Python on the accepted English package, before the English
# DOCX and the Chinese stage: what the model should never be trusted to
# write (the day the memo was written, when a page was retrieved, what the
# checks found) and the cover fields the translator must see as {en, zh}
# slots. Every step is optional and never raises; a package without these
# fields renders exactly as before.

_COVER_TEXT_FIELDS = ("descriptor", "stage", "sector", "location", "round")
_STAGE_COVER_LABELS = {
    "early": {"en": "Early stage", "zh": "早期"},
    "growth": {"en": "Growth stage", "zh": "成长期"},
    "late": {"en": "Late stage", "zh": "后期"},
}
_RUN_DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})")


def _run_date(run_id: str | None, run_dir: Path | None = None) -> str | None:
    """The day the run was written (``YYYY-MM-DD``), from its run id or its
    folder name — never the raw run id."""
    from . import source_tiers

    for text in (run_id, run_dir.name if run_dir is not None else None):
        match = _RUN_DATE_RE.match(str(text or ""))
        if match:
            parsed = source_tiers.parse_partial_date(match.group(1))
            if parsed:
                return parsed
    return None


def _same_text(left: Any, right: Any) -> bool:
    a = " ".join(str(left or "").lower().split())
    return bool(a) and a == " ".join(str(right or "").lower().split())


def _stamp_cover_facts(
    package: dict,
    *,
    company_id: str | None,
    run_date: str | None,
    structure: memo_structure.MemoStructure | None,
) -> None:
    """``run.as_of`` is the run date; the company's cover fields become
    ``{en, zh}`` slots (``hq`` → ``location``) so the translation fills
    them, with the registry's own Chinese prefilled where the English is
    the registry's; a missing stage comes from the run's structure and a
    missing round from the round on the deal-pipeline record. A round is
    never invented: absent stays absent (the renderer leaves the row out)."""
    run_block = package.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        package["run"] = run_block
    if run_date:
        run_block["as_of"] = run_date
    company = package.get("company")
    if not isinstance(company, dict):
        return
    if not str(company.get("location") or "").strip() and company.get("hq"):
        company["location"] = company.pop("hq")
    if not company.get("stage") and structure is not None:
        label = _STAGE_COVER_LABELS.get(structure.declared_stage)
        if label:
            company["stage"] = dict(label)
    record = (storage.get_company(company_id) or {}) if company_id else {}
    if "round" not in company and company_id and storage.infer_company_type(record or {}) == "private":
        try:
            from . import deal_pipeline

            proposed = str(deal_pipeline.get_deal_pipeline(company_id).get("round") or "").strip()
        except Exception:  # noqa: BLE001
            proposed = ""
        if proposed:
            company["round"] = proposed
    for field in _COVER_TEXT_FIELDS:
        value = company.get(field)
        if isinstance(value, str) and value.strip():
            company[field] = {"en": value, "zh": ""}
        elif isinstance(value, dict) and "en" in value and "zh" not in value:
            value["zh"] = ""
    translation: dict = {}
    if company_id:
        try:
            ext = storage.get_company_ext(company_id) or {}
        except Exception:  # noqa: BLE001
            ext = {}
        candidate = ext.get("translation") if isinstance(ext, dict) else None
        if isinstance(candidate, dict) and str(candidate.get("language") or "zh") == "zh":
            translation = candidate
    for field, registry_key in (("sector", "sector"), ("location", "hq")):
        value = company.get(field)
        zh = str(translation.get(registry_key) or "").strip()
        if (
            isinstance(value, dict)
            and zh
            and not str(value.get("zh") or "").strip()
            and _same_text(value.get("en"), record.get(registry_key))
        ):
            value["zh"] = zh


def _upstream_evidence(run_dir: Path, session_dir: Path | None) -> dict[str, dict]:
    """What the analysis recorded about each page it cited, by canonical
    URL: the pass evidence's ``source_class`` and, from a Memo Studio
    session's risk map, its ``confidence``."""
    from . import source_cache

    found: dict[str, dict] = {}

    def note(url: Any, source_class: Any, confidence: Any = None) -> None:
        canon = source_cache.canonical_url(url)
        if not canon:
            return
        entry = found.setdefault(canon, {})
        if str(source_class or "").strip() and "source_class" not in entry:
            entry["source_class"] = str(source_class).strip()[:120]
        level = str(confidence or "").strip().lower()
        if level in ("low", "medium", "high") and "confidence" not in entry:
            entry["confidence"] = level

    for record in _fast_pass_records(run_dir).values():
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        for item in data.get("supporting_evidence") or []:
            if isinstance(item, dict):
                note(item.get("url"), item.get("source_class"))
    risk_map = None
    if session_dir is not None:
        try:
            import yaml

            risk_map = yaml.safe_load(
                (Path(session_dir) / "strategic_risks.yaml").read_text(encoding="utf-8")
            )
        except Exception:  # noqa: BLE001 — optional input
            risk_map = None
    risks = risk_map.get("risks") if isinstance(risk_map, dict) else None
    for risk in risks if isinstance(risks, list) else []:
        items = risk.get("supporting_evidence") if isinstance(risk, dict) else None
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                note(item.get("locator"), item.get("source_class"), item.get("confidence"))
    return found


def _stamp_source_dates(
    package: dict,
    run_dir: Path,
    *,
    company_id: str | None,
    run_date: str | None,
    session_dir: Path | None = None,
) -> None:
    """Honest source dates (source_tiers.normalize_source_dates): a web page
    "dated" the day the run read it becomes undated unless its URL carries a
    date; ``retrieved_at`` comes only from the run's own source manifest or
    the company's source cache. The analysis's ``source_class`` and
    ``confidence`` for the same page ride along as ``evidence_source_class``
    / ``evidence_confidence``. ``run.evidence_cutoff`` is derived from the
    sources when the model left it out or set it to the run date."""
    from . import source_cache, source_tiers

    sources = package.get("sources")
    if not isinstance(sources, list):
        return
    fetched: dict[str, str] = {}
    for row in source_cache.run_manifest(run_dir):
        canon = source_cache.canonical_url(row.get("url"))
        if canon and row.get("at") and canon not in fetched:
            fetched[canon] = str(row["at"])
    upstream = _upstream_evidence(run_dir, session_dir)
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        canon = source_cache.canonical_url(source.get("url"))
        fetched_at = fetched.get(canon) if canon else None
        if canon and not fetched_at and company_id:
            record = source_cache.find_by_url(company_id, source.get("url"))
            fetched_at = (record or {}).get("fetched_at")
        normalized = source_tiers.normalize_source_dates(
            source, run_date, fetched_at=fetched_at
        )
        evidence = upstream.get(canon) if canon else None
        if evidence:
            if evidence.get("source_class"):
                normalized.setdefault("evidence_source_class", evidence["source_class"])
            if evidence.get("confidence"):
                normalized.setdefault("evidence_confidence", evidence["confidence"])
        sources[index] = normalized
    run_block = package.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        package["run"] = run_block
    stated = source_tiers.parse_partial_date(
        run_block.get("evidence_cutoff")
    ) or source_tiers.parse_partial_date(run_block.get("evidence_ceiling"))
    if not stated or (run_date and stated == run_date):
        derived = source_tiers.evidence_cutoff(sources, run_date)
        if derived:
            run_block["evidence_cutoff"] = derived


_FACT_CHECK_GATE_WORDS = {"pass": "passed", "warn": "warnings", "fail": "warnings"}


def _stamp_fact_check_checks(package: dict, run_dir: Path) -> None:
    """``run.checks.fact_check`` (the provenance line at the top of the
    sources section) from the run's last fact check. The line's total is
    the checked count: company-reported figures count as found elsewhere
    and registry-only ones as not traced (never as verified). Unsupported
    figures ship as findings on the report, so the gate reads "warnings",
    never "failed"."""
    from . import memo_fact_check

    payload = _fact_check_payload(run_dir)
    if not payload:
        return
    summary = memo_fact_check.summarize_fact_check(payload)
    status = summary.get("status")
    if status in ("not_run", "error", "no_figures"):
        return

    def count(key: str) -> int:
        value = summary.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    run_block = package.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        package["run"] = run_block
    checks = run_block.get("checks") if isinstance(run_block.get("checks"), dict) else {}
    checks["fact_check"] = {
        "verified": count("verified"),
        "found_elsewhere": count("found_elsewhere") + count("company_reported"),
        "derived": count("derived"),
        "not_traced": count("not_traced") + count("registry_only"),
        "thin_corpus": bool(summary.get("thin_corpus")),
    }
    gates = checks.get("gates") if isinstance(checks.get("gates"), dict) else {}
    word = _FACT_CHECK_GATE_WORDS.get(str(status))
    if word:
        gates["fact_check"] = word
    else:
        gates.pop("fact_check", None)
    if gates:
        checks["gates"] = gates
    run_block["checks"] = checks


def _localize_calculation_input_names(package: dict) -> None:
    """Plain calculation input names and values, and plain results, become
    {en, zh} slots, so the Chinese 计算说明 table is translated like the
    label and meaning beside it."""
    for calculation in package.get("calculations") or []:
        if not isinstance(calculation, dict):
            continue
        if "result" in calculation and not isinstance(calculation.get("result"), dict):
            calculation["result"] = claude_runner.localized_calculation_text(
                calculation.get("result")
            )
        for item in calculation.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            for key in ("name", "value"):
                if key in item and not isinstance(item.get(key), dict):
                    item[key] = claude_runner.localized_calculation_text(item.get(key))


def _stamp_envelope_facts(
    package: dict,
    run_dir: Path,
    *,
    company_id: str | None,
    run_id: str | None,
    structure: memo_structure.MemoStructure | None = None,
    session_dir: Path | None = None,
) -> None:
    """Every deterministic envelope fact on the accepted English package
    (see the section comment above); never raises."""
    if not isinstance(package, dict):
        return
    run_date = _run_date(run_id, run_dir)
    for step in (
        lambda: _localize_calculation_input_names(package),
        lambda: _stamp_cover_facts(
            package, company_id=company_id, run_date=run_date, structure=structure
        ),
        lambda: _stamp_source_dates(
            package,
            run_dir,
            company_id=company_id,
            run_date=run_date,
            session_dir=session_dir,
        ),
        lambda: _final_fact_check(package, run_dir, company_id=company_id, session_dir=session_dir),
        lambda: _stamp_fact_check_checks(package, run_dir),
    ):
        try:
            step()
        except Exception:  # noqa: BLE001
            logger.warning("envelope facts stamp failed", exc_info=True)


def _final_fact_check(
    package: dict,
    run_dir: Path,
    *,
    company_id: str | None,
    session_dir: Path | None = None,
) -> None:
    """The fact check of the English package as delivered — after every
    repair and the red-team pass. The gate's own check runs on the candidate
    BEFORE its surgical repair, so the provenance line and the record used
    to describe text the reader never got (ZaiNar 2026-09-23: "184 not
    traced" on a package two repairs later). Calculation inputs no source
    carries are relabelled as our assumptions here (see
    ``memo_fact_check.unsourced_calculation_inputs``) and listed in
    ``logs/calculation_inputs.json`` for the run's warnings. Report only."""
    if not company_id or not _memo_fact_check_enabled() or not isinstance(package, dict):
        return
    from . import memo_fact_check

    result, relabelled = memo_fact_check.final_check(
        run_dir=run_dir,
        package=package,
        company_id=company_id,
        research_dir=_research_dir_for(company_id),
        session_dir=session_dir,
    )
    logs_dir = run_dir / "logs"
    inputs_path = logs_dir / memo_fact_check.CALCULATION_INPUTS_FILENAME
    # A second stamp of the same package (a resume) finds nothing left to
    # relabel; the first stamp's entries stand while their input still reads
    # as an assumption.
    try:
        earlier = json.loads(inputs_path.read_text(encoding="utf-8")).get("relabelled") or []
    except (OSError, ValueError, AttributeError):
        earlier = []
    notes = {
        str(calc.get("id") or ""): calc
        for calc in package.get("calculations") or []
        if isinstance(calc, dict)
    }

    def still_assumption(entry: dict) -> bool:
        inputs = (notes.get(str(entry.get("calc_id") or "")) or {}).get("inputs")
        index = entry.get("input_index")
        return (
            isinstance(inputs, list)
            and isinstance(index, int)
            and 0 <= index < len(inputs)
            and isinstance(inputs[index], dict)
            and str(inputs[index].get("ref") or "") == "assumption"
        )

    seen = {(r.get("calc_id"), r.get("input_index")) for r in relabelled}
    kept = [
        r for r in earlier
        if isinstance(r, dict) and (r.get("calc_id"), r.get("input_index")) not in seen and still_assumption(r)
    ]
    _write_json(inputs_path, {"relabelled": kept + relabelled})
    if result.error:
        # Keep the gate's last report rather than overwrite it with nothing.
        return
    (logs_dir / "fact_check.md").write_text(
        memo_fact_check.render_markdown_report(result, attempt=None), encoding="utf-8"
    )
    _write_json(logs_dir / "fact_check.json", result.to_dict())


def _stamp_prerender_gates(package_path: Path, findings: list[str]) -> None:
    """``run.checks.gates`` quality / chinese_parity from the pre-render
    pass over the final bilingual package — the same lint and parity checks
    finalize runs on the same package — so the delivered documents carry
    them without a second render. A failed check stamps nothing."""
    if any(str(line).startswith("pre-render quality check failed") for line in findings):
        return
    package = _package_on_disk(package_path)
    if package is None:
        return
    run_block = package.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        package["run"] = run_block
    checks = run_block.get("checks") if isinstance(run_block.get("checks"), dict) else {}
    gates = checks.get("gates") if isinstance(checks.get("gates"), dict) else {}
    gates["quality"] = (
        "warnings" if any(str(line).startswith("quality gate") for line in findings) else "passed"
    )
    gates["chinese_parity"] = (
        "warnings"
        if any(str(line).startswith("Chinese parity gate") for line in findings)
        else "passed"
    )
    checks["gates"] = gates
    run_block["checks"] = checks
    _write_json(package_path, package)


def _notify_memo(report_id: str, title: str, body: str) -> None:
    """A push notification about a memo run; never raises, and silent once
    the run was halted (a cancel or shutdown already said what happened)."""
    if _run_halted(report_id):
        return
    try:
        from . import push_notify

        report = storage.get_report(report_id) or {}
        push_notify.notify(
            "memo",
            title,
            body,
            data={
                "report_id": report_id,
                "company_id": report.get("company_id"),
                "deep_link": f"bshresearch://report/{report_id}",
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("memo push notify failed for %s", report_id)


def _deliver_english_first(
    *,
    report_id: str | None,
    run_dir: Path,
    english_package: dict,
    memo_paths: dict[str, str],
    stream: job_progress.ProgressLog,
) -> bool:
    """Write the English DOCX the moment the English package is accepted,
    before the Chinese stage starts: a reader can open the English memo
    while the Chinese is written, and no Chinese failure can cost them it.

    The run stays ``analyzing`` (the viewer shows the English because the
    file exists); ``english_ready_at`` records when it landed and the stage
    moves to "English memo ready — Chinese in progress" at 80%, above the
    progress ticker's ceiling so the ticker cannot write the old stage back.
    Best-effort: a render failure here only means the reader waits for the
    finalize render, as before."""
    en_path = memo_paths.get("en")
    if not report_id or not en_path:
        return False
    if _run_halted(report_id):
        return False
    out_path = Path(en_path)
    try:
        _render_single_locale(
            _english_render_payload(english_package),
            "en",
            out_path,
            run_dir=run_dir,
        )
    except Exception as exc:  # noqa: BLE001 — never costs the run
        logger.warning("early English render failed for %s", report_id, exc_info=True)
        stream.emit(
            "stage",
            stage="memo_english_early_render_failed",
            message=(
                "Could not write the English memo ahead of the Chinese; it "
                f"will be written with both languages ({type(exc).__name__})"
            ),
        )
        return False
    current = storage.get_report(report_id) or {}
    _update_report(
        report_id,
        stage=ENGLISH_READY_STAGE,
        progress=max(80, int(current.get("progress") or 0)),
        english_ready_at=_now_iso(),
    )
    stream.emit(
        "stage",
        stage="memo_english_ready",
        message=ENGLISH_READY_STAGE,
        english_memo=memo_prep._rel(out_path),
    )
    company = storage.get_company(str(current.get("company_id") or "")) or {}
    name = company.get("name") or current.get("company_name") or "Memo"
    _notify_memo(
        report_id,
        "English memo ready",
        f"{name} — English memo ready; the Chinese is still being written",
    )
    return True


def _save_zh_partial(run_dir: Path, partial: dict | None, fallback: dict) -> Path:
    """Keep whatever Chinese the failed stage finished, so "Retry Chinese"
    translates only what is still blank: the partly translated package when
    there is one, else the accepted English (with any chased translations)."""
    path = _zh_partial_package_path(run_dir)
    _write_json(path, partial if isinstance(partial, dict) else fallback)
    return path


@dataclass
class _ChineseStageResult:
    memo_package: dict | None
    error: str | None
    cost_usd: float
    duration_ms: int
    usage: dict | None = None
    partial: dict | None = None


def _run_chinese_package_stage(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    bilingual_input_path: Path,
    progress,
    stream,
) -> _ChineseStageResult:
    """Phase 4 proper: translate the package, write ``memo_package.json``,
    and fill any Chinese that did not land (one per-section gap-fill, then
    the sparse-gap fallback). Returns the accepted bilingual package, or the
    error plus the most complete partial package (English + every Chinese
    string that did land) for ``logs/memo_package.zh_partial.json``.

    Never touches English: the translation merge adopts only ``zh``."""
    cost_usd = 0.0
    duration_ms = 0
    stage_started = time.time()
    bilingual_result, bilingual_error = (
        claude_runner.run_memo_fast_bilingual_package_parallel(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            english_package_path=bilingual_input_path,
            progress=progress,
            stream=stream,
        )
    )
    if bilingual_error or not isinstance(bilingual_result, dict):
        message = bilingual_error or "Chinese package pass returned no data."
        partial = None
        partial_path = _zh_partial_package_path(run_dir)
        try:
            # The parallel pass keeps what its finished units translated —
            # this stage's file only, never one an earlier attempt left.
            if partial_path.stat().st_mtime >= stage_started - 1:
                loaded = json.loads(partial_path.read_text(encoding="utf-8"))
                partial = loaded if isinstance(loaded, dict) else None
        except (OSError, ValueError):
            partial = None
        return _ChineseStageResult(None, message, cost_usd, duration_ms, partial=partial)
    cost_usd += _as_float(bilingual_result.get("claude_cost_usd")) or _as_float(
        getattr(progress, "cost_usd", 0.0)
    )
    duration_ms += _as_int(bilingual_result.get("claude_duration_ms")) or _as_int(
        getattr(progress, "duration_ms", 0)
    )
    memo_package = bilingual_result.get("memo_package")
    if not isinstance(memo_package, dict):
        return _ChineseStageResult(
            None,
            "Chinese package pass did not return memo_package.",
            cost_usd,
            duration_ms,
        )
    usage = (
        bilingual_result.get("claude_usage")
        if isinstance(bilingual_result.get("claude_usage"), dict)
        else None
    )
    final_package_path = _memo_package_path(run_dir)
    _write_json(final_package_path, memo_package)
    package_error = _memo_package_render_validation_error(final_package_path)
    if package_error:
        # The English gate already validated structure, so any error here is
        # Chinese fill that didn't land (blank `zh` after a unit drifted).
        # The monolithic bilingual pass only fills blank `zh` strings — run
        # it once over the merged package as a targeted repair.
        # Per unit, not in one call. The monolithic pass asks for the whole
        # bilingual package in one response, which on Gemini is past its
        # 64k output ceiling: a 2026-09-19 Databricks run reached the final
        # render with EIGHT untranslated cells in one table, and the repair
        # that should have filled them could not fit the answer. The
        # parallel pass translates one section at a time and, with
        # `only_missing`, touches only the strings that are still blank.
        # Claude is unaffected in substance — it gets the same gap-fill,
        # split across calls rather than one, which is what its own chasing
        # path already does.
        progress.emit(
            "stage",
            stage="memo_package_zh_repair",
            message=(
                "Merged package failed renderer validation; filling the "
                "blank Chinese per section"
            ),
            validation_error=package_error[:2000],
        )
        repair_result, repair_error = (
            claude_runner.run_memo_fast_bilingual_package_parallel(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                english_package_path=final_package_path,
                progress=progress,
                stream=stream,
                only_missing=True,
            )
        )
        if not repair_error and isinstance(repair_result, dict):
            repaired = repair_result.get("memo_package")
            if isinstance(repaired, dict):
                cost_usd += _as_float(repair_result.get("claude_cost_usd"))
                duration_ms += _as_int(repair_result.get("claude_duration_ms"))
                claude_runner._adopt_zh_translations(memo_package, repaired)
                _write_json(final_package_path, memo_package)
                package_error = _memo_package_render_validation_error(
                    final_package_path,
                    allow_zh_fallback=True,
                )
    if package_error:
        message = (
            "Memo package failed renderer validation after the Chinese "
            f"fill: {package_error}"
        )
        # The merged package is the most complete partial there is; keep it
        # as the retry's starting point, and take the invalid file out of
        # the path that resume and recovery read as "the accepted package".
        partial = memo_package
        try:
            _archive_memo_package(final_package_path, label="zh_failed")
        except OSError:
            logger.warning("could not archive the failed bilingual package", exc_info=True)
        return _ChineseStageResult(
            None, message, cost_usd, duration_ms, usage=usage, partial=partial
        )
    return _ChineseStageResult(memo_package, None, cost_usd, duration_ms, usage=usage)


def _run_fast_synthesis(
    *,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    company_name: str,
    company_slug: str,
    run_id: str,
    memo_paths: dict[str, str],
    research_dir: Path,
    analysis_session_path: Path | None,
    lessons_path: Path | None,
    scope_check: dict | None,
    warnings: list[str],
    zh_chaser=None,
    speculator=None,
    cost_usd: float = 0.0,
    worker_duration_ms: int = 0,
    started_at: str = "",
    started_monotonic: float = 0.0,
    pinned_spine_path: Path | None = None,
    memo_mode: str = "auto",
    structure: memo_structure.MemoStructure | None = None,
    report_id: str | None = None,
) -> dict:
    """Phases 3-4: English synthesis, Chinese fill, and the gates.

    Extracted from the straight-line pipeline so Memo Studio can re-enter
    here on "Generate Report". Everything Phase 3 reads from Phase 2 is on
    disk (``analysis/fast/*.json`` + ``analysis/*.md``) — the packet-mode
    precedent proves no in-process Phase-2 state is needed.
    ``pinned_spine_path`` makes the parallel English pass reuse that spine
    verbatim instead of calling the spine agent: the user's card edits ARE
    the pins. ``cost_usd``/``worker_duration_ms`` carry totals accumulated
    before this half; ``started_at``/``started_monotonic`` close the
    whole-pipeline phase timing.
    """
    _assert_spine_pin_allowed(pinned_spine_path, memo_mode)
    if memo_mode == "studio":
        # Studio spines are composed from v1 cards; the studio flow stays
        # on late v1 until the restructure's studio bridge lands.
        structure = memo_structure.LATE
    else:
        structure = structure or memo_structure.active_structure("late")
    _register_run_structure(run_dir, structure)
    phase3_started_at = _now_iso()
    phase3_started = time.monotonic()
    phase3_progress = _ThreadProgress(stream, claude_runner._MEMO_PHASE3_THREAD)
    phase3_progress.emit("thread_started", title=claude_runner._MEMO_PHASE3_THREAD)
    _emit_phase_timing(
        stream,
        phase="memo_fast_english_package",
        status="started",
        started_at=phase3_started_at,
        started_monotonic=phase3_started,
    )
    english_result: dict | None = None
    english_error: str | None = None
    attempts_used = 0
    last_transient = False
    validation_feedback: str | None = None
    cumulative_errors: list[str] = []
    last_invalid_candidate: dict | None = None
    last_validation_errors: list[str] = []
    last_attempt_result: dict | None = None
    last_attempt_path: Path | None = None
    max_attempts = 1 + _memo_fast_english_package_retries()
    async_artifacts = None
    if _cost_guard_stop(
        report_id=report_id,
        run_dir=run_dir,
        cost_usd=cost_usd,
        phase="analysis artifacts",
        stream=stream,
    ) and _skip_artifacts_for_cost(run_dir):
        # The artifacts agent is a paid phase of its own; past the ceiling
        # the wave finds them "cached" (empty) and writes none.
        pass
    elif claude_runner._memo_artifacts_async_enabled():
        async_artifacts = claude_runner.AsyncArtifacts(
            run_dir=run_dir,
            company_name=company_name,
            stream=stream,
        )
    phase3_cost_before = phase3_progress.cost_usd
    phase3_duration_before = phase3_progress.duration_ms
    company_stage_hook = (
        _company_stage_spine_hook(report_id, stream) if report_id else None
    )
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        attempt_started_at = _now_iso()
        attempt_started = time.monotonic()
        attempt_cost_before = phase3_progress.cost_usd
        attempt_duration_before = phase3_progress.duration_ms
        if attempt > 1:
            # Name the real cause. This used to say "after a retryable
            # Claude interruption" on every retry, so a package that was
            # simply too long read in the job rail as an infrastructure
            # failure.
            cause = (
                str(english_error).strip()
                if english_error
                else "renderer validation"
            )
            phase3_progress.emit(
                "stage",
                stage="memo_fast_english_package_retry",
                message=(
                    "Retrying English package synthesis after "
                    f"{cause[:160]} (attempt {attempt}/{max_attempts})"
                ),
                attempt=attempt,
                max_attempts=max_attempts,
                previous_error=english_error,
            )
        _emit_phase_timing(
            stream,
            phase="memo_fast_english_package_attempt",
            status="started",
            started_at=attempt_started_at,
            started_monotonic=attempt_started,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        attempt_result, attempt_error = (
            claude_runner.run_memo_fast_english_package_parallel(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                settings_path=memo_prep.SETTINGS_FILE,
                companies_yaml_path=_run_companies_yaml(run_dir),
                memo_paths=memo_paths,
                research_dir=research_dir,
                analysis_session_path=analysis_session_path,
                lessons_path=lessons_path,
                scope_check=scope_check,
                warnings=warnings,
                progress=phase3_progress,
                validation_feedback=validation_feedback,
                previous_validation_errors=last_validation_errors or None,
                previous_package_path=last_attempt_path,
                stream=stream,
                attempt=attempt,
                # Chase only the clean first attempt: retries and repairs
                # rewrite English, which would strand the speculative
                # translations (bounded-waste rule). The company-stage
                # hook rides every attempt — a respun spine still pins
                # the stage, and the hook fires only once.
                on_spine=_compose_spine_hooks(
                    company_stage_hook,
                    (
                        zh_chaser.on_spine
                        if zh_chaser is not None
                        and attempt == 1
                        and not validation_feedback
                        else None
                    ),
                ),
                on_section=(
                    zh_chaser.on_section
                    if zh_chaser is not None
                    and attempt == 1
                    and not validation_feedback
                    else None
                ),
                async_artifacts=async_artifacts,
                speculative_english=speculator,
                pinned_spine_path=pinned_spine_path,
                structure=structure,
            )
        )
        attempt_cost = max(0.0, phase3_progress.cost_usd - attempt_cost_before)
        attempt_duration = max(
            0, phase3_progress.duration_ms - attempt_duration_before
        )
        if attempt_error or not isinstance(attempt_result, dict):
            message = attempt_error or "English package pass returned no data."
            last_transient = claude_runner.is_transient_claude_error(message)
            english_error = message
            _emit_phase_timing(
                stream,
                phase="memo_fast_english_package_attempt",
                status="failed",
                started_at=attempt_started_at,
                started_monotonic=attempt_started,
                attempt=attempt,
                max_attempts=max_attempts,
                transient=last_transient,
                error=message,
                cost_usd=round(attempt_cost, 6),
                claude_duration_ms=attempt_duration,
            )
            if last_transient and attempt < max_attempts:
                backoff_sec = _memo_fast_retry_backoff_sec()
                phase3_progress.emit(
                    "stage",
                    stage="memo_fast_english_package_retry_scheduled",
                    message=(
                        "English package synthesis hit a retryable Claude "
                        f"interruption; retrying attempt {attempt + 1}/"
                        f"{max_attempts}"
                    ),
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    retry_in_sec=backoff_sec,
                    previous_error=message,
                )
                if backoff_sec > 0:
                    time.sleep(backoff_sec)
                continue
            break
        # Validate the package NOW (zh-tolerant) instead of letting the
        # renderer discover the same defects 20 minutes later. Both fresh
        # runs on record emitted the analysis-pass source vocabulary
        # (label/source_class/detail) and died at the render gate; feeding
        # the errors back lets the synthesis pass self-correct the way the
        # resume path already does.
        candidate = attempt_result.get("memo_package")
        if isinstance(candidate, dict):
            # Persist every candidate so a failed run leaves its work product
            # on disk for debugging and surgical repair instead of vanishing.
            last_attempt_path = (
                run_dir / "logs" / f"memo_package.en.attempt-{attempt}.json"
            )
            _write_json(last_attempt_path, candidate)
            # Mechanical defects (missing callout title, plain strings in
            # bilingual slots, analysis-pass source vocabulary) are fixed
            # deterministically instead of burning a full regeneration.
            repaired_candidate, structure_repairs = (
                memo_docx_renderer.repair_package_structure(candidate)
            )
            if structure_repairs:
                candidate = repaired_candidate
                attempt_result["memo_package"] = repaired_candidate
                # Keep the on-disk attempt in sync with what validation sees;
                # a selective section retry splices unchanged sections from
                # this file.
                _write_json(last_attempt_path, repaired_candidate)
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_auto_repair",
                    message=(
                        f"Auto-repaired {len(structure_repairs)} mechanical "
                        "package defect(s) before validation"
                    ),
                    repairs=structure_repairs[:20],
                    attempt=attempt,
                )
        if isinstance(candidate, dict):
            # Deterministic first: a source whose page the passes already
            # recorded gets its URL here, so the URL rule below only fails
            # sources nothing on file can vouch for.
            url_notes = _attach_memo_source_urls(
                run_dir=run_dir,
                candidate=candidate,
                company_id=company_slug,
                progress=phase3_progress,
                attempt=attempt,
                session_dir=analysis_session_path,
            )
            if url_notes and last_attempt_path is not None:
                _write_json(last_attempt_path, candidate)
        if isinstance(candidate, dict):
            # One trim of the largest subsection of every section the wave
            # assembled over its hard cap — before validation sees it, and
            # never twice for the same section in one attempt.
            trimmed_now = _trim_oversized_sections(
                run_dir=run_dir,
                package=candidate,
                progress=phase3_progress,
                trimmed=set(),
                company_name=company_name,
            )
            if trimmed_now and last_attempt_path is not None:
                _write_json(last_attempt_path, candidate)
        # The risk cards' WORDING (an economic consequence in "Why it
        # matters", a signal rather than a command in "What we watch", the
        # row count) is triaged out of the structural validation: those
        # findings ride the surgical repair below and whatever is left
        # ships as a warning — never a regeneration of the package.
        validation_errors = memo_docx_renderer.english_package_validation_errors(
            candidate, editorial_risk_checks=False
        )
        if validation_errors and _accept_with_small_overruns(
            run_dir=run_dir,
            package=candidate,
            errors=validation_errors,
            progress=phase3_progress,
            attempt=attempt,
        ):
            # Nothing but small word-cap overruns: delivered with a length
            # warning rather than repaired or regenerated.
            validation_errors = []
        if not validation_errors:
            # Structure is good — also run the finalize-time English quality
            # gate on a throwaway render, so banned vocabulary retries here
            # with the findings fed back instead of costing a whole
            # regeneration round after the Chinese fill.
            quality_findings = _memo_package_prerender_quality_findings(
                memo_docx_renderer.fill_blank_zh_placeholders(candidate),
                check_parity=False,
                run_dir=run_dir,
            )
            risk_card_findings = (
                memo_docx_renderer.risk_card_quality_findings(candidate)
                if isinstance(candidate, dict)
                else []
            )
            fact_lines: list[str] = []
            if isinstance(candidate, dict):
                pin_lines = _run_memo_pin_check(
                    run_dir=run_dir,
                    candidate=candidate,
                    progress=phase3_progress,
                    attempt=attempt,
                )
                if pin_lines and _memo_pin_check_repair_enabled():
                    quality_findings = list(quality_findings) + pin_lines
                fact_lines = _run_memo_fact_check(
                    run_dir=run_dir,
                    candidate=candidate,
                    company_id=company_slug,
                    research_dir=research_dir,
                    progress=phase3_progress,
                    attempt=attempt,
                    session_dir=analysis_session_path,
                )
            if (
                quality_findings or fact_lines or risk_card_findings
            ) and isinstance(candidate, dict):
                # Try the cheap surgical repair first: quality findings are
                # localized string defects, and a full regeneration costs
                # 10-18 minutes per round (the 40-60 minute runs on record
                # were exactly these retries). Unsupported figures and the
                # risk cards' wording ride the same repair.
                repaired = _surgical_quality_repair(
                    run_dir=run_dir,
                    company_name=company_name,
                    run_id=run_id,
                    candidate=candidate,
                    findings=list(quality_findings)
                    + fact_lines
                    + list(risk_card_findings),
                    attempt=attempt,
                    progress=phase3_progress,
                    stream=stream,
                )
                if repaired is not None:
                    candidate = repaired
                    attempt_result["memo_package"] = repaired
                    if last_attempt_path is not None:
                        _write_json(last_attempt_path, repaired)
                    quality_findings = []
                    fact_lines = []
                    risk_card_findings = (
                        memo_docx_renderer.risk_card_quality_findings(repaired)
                    )
                if risk_card_findings and not quality_findings:
                    # Left after the repair (or no repair could run): the
                    # renderer draws these cards, so they ship as a warning
                    # finalize records (_risk_card_warning).
                    phase3_progress.emit(
                        "stage",
                        stage="memo_risk_card_wording_warning",
                        message=(
                            f"{len(risk_card_findings)} risk-card wording "
                            "finding(s) remain; continuing with warnings"
                        ),
                        findings=risk_card_findings[:10],
                        attempt=attempt,
                    )
                if repaired is None and fact_lines:
                    # Unsupported figures alone never cost a regeneration
                    # round: the report keeps them as findings for the
                    # analyst, and the memo ships.
                    phase3_progress.emit(
                        "stage",
                        stage="memo_fact_check_unrepaired",
                        message=(
                            f"{len(fact_lines)} fact-check finding(s) (unsupported "
                            "figures or contradicted comparisons) could not be "
                            "repaired; continuing with them recorded on the report"
                        ),
                        attempt=attempt,
                    )
            quality_error = (
                "; ".join(quality_findings) if quality_findings else None
            )
            if quality_error:
                if attempt < max_attempts:
                    # One finding per list entry: the selective section
                    # retry maps each error to its owning section, and a
                    # single joined string collapses every finding onto
                    # the first section mentioned (observed live
                    # 2026-09-11: a financial_analysis finding never
                    # reached its section across three attempts).
                    validation_errors = list(quality_findings)
                else:
                    # Out of retries; the package renders, so carry the
                    # findings forward as warnings instead of failing the
                    # run (finalize marks it complete_with_warnings).
                    phase3_progress.emit(
                        "stage",
                        stage="memo_english_quality_warning",
                        message=(
                            "English package still has quality findings "
                            "after retries; continuing with warnings"
                        ),
                        validation_error=quality_error[:4000],
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
        if validation_errors:
            for err in validation_errors:
                if err not in cumulative_errors:
                    cumulative_errors.append(err)
            if isinstance(candidate, dict):
                last_invalid_candidate = candidate
                last_validation_errors = list(validation_errors)
                last_attempt_result = attempt_result
            english_error = (
                "English package failed renderer validation: "
                + "; ".join(validation_errors[:12])
            )
            _emit_phase_timing(
                stream,
                phase="memo_fast_english_package_attempt",
                status="failed",
                started_at=attempt_started_at,
                started_monotonic=attempt_started,
                attempt=attempt,
                max_attempts=max_attempts,
                transient=False,
                validation=True,
                error=english_error,
                cost_usd=round(attempt_cost, 6),
                claude_duration_ms=attempt_duration,
            )
            if _only_word_budget_errors(validation_errors):
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_budget_repair_shortcut",
                    message=(
                        "Only word-budget errors remain; going straight to "
                        "the trim repair instead of regenerating sections "
                        "that would come back the same length"
                    ),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    validation_errors=validation_errors[:10],
                )
                break
            if _only_envelope_or_budget_errors(validation_errors, candidate):
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_envelope_repair_shortcut",
                    message=(
                        "Only source-list and word-budget errors remain; "
                        "repairing those directly instead of regenerating "
                        "every section"
                    ),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    validation_errors=validation_errors[:10],
                )
                break
            if attempt < max_attempts:
                # Feed back the cumulative error list, not just this
                # attempt's: retry 2 of the Axiom run fixed the fed-back
                # quality finding but regressed on structure it had gotten
                # right in attempt 1, because that structure was never
                # mentioned in the feedback.
                validation_feedback = "\n".join(
                    f"- {err}" for err in cumulative_errors[:30]
                )
                phase3_progress.emit(
                    "stage",
                    stage="memo_fast_english_package_validation_retry",
                    message=(
                        "English package failed renderer validation; "
                        f"regenerating with errors fed back (attempt "
                        f"{attempt + 1}/{max_attempts})"
                    ),
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    validation_errors=validation_errors[:10],
                )
                continue
            break
        english_result = attempt_result
        english_error = None
        last_transient = False
        _emit_phase_timing(
            stream,
            phase="memo_fast_english_package_attempt",
            status="finished",
            started_at=attempt_started_at,
            started_monotonic=attempt_started,
            attempt=attempt,
            max_attempts=max_attempts,
            cost_usd=round(attempt_cost, 6),
            claude_duration_ms=attempt_duration,
            usage=attempt_result.get("claude_usage")
            if isinstance(attempt_result.get("claude_usage"), dict)
            else None,
        )
        break
    if (
        english_error
        and english_result is None
        and isinstance(last_invalid_candidate, dict)
        and last_validation_errors
    ):
        # Every full attempt is spent and the last candidate still fails
        # structural validation. Instead of abandoning the run (and its
        # accumulated analysis cost), run one surgical repair pass over the
        # invalid package: fix ONLY the listed defects, preserving content.
        invalid_path = run_dir / "logs" / "memo_package.en.invalid.json"
        _write_json(invalid_path, last_invalid_candidate)
        phase3_progress.emit(
            "stage",
            stage="memo_package_structure_repair",
            message=(
                "English package still fails renderer validation after all "
                "attempts; running a surgical structure repair pass instead "
                "of failing the run"
            ),
            validation_errors=last_validation_errors[:10],
        )
        repaired_package = None
        working_errors = list(last_validation_errors)
        length_accepted = False
        if claude_runner._memo_sectional_repair_enabled() and isinstance(
            last_invalid_candidate, dict
        ):
            # Word-budget overruns are per-section by construction, and the
            # whole-package pass cannot carry a 16,000-word memo in one
            # response. Repair per section first — in edits mode where the
            # runner offers it — and KEEP every section and envelope repair
            # that succeeded when another fails; a section whose repair
            # could not fit its answer in one call is trimmed instead.
            outcome = _repair_package_by_section(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                package=last_invalid_candidate,
                findings=last_validation_errors,
                progress=phase3_progress,
                stream=stream,
            )
            ran = bool(
                outcome.repaired
                or outcome.failed
                or outcome.envelope_repaired
                or outcome.envelope_error
            )
            if ran:
                working = outcome.package
                if outcome.too_large:
                    _trim_oversized_sections(
                        run_dir=run_dir,
                        package=working,
                        progress=phase3_progress,
                        trimmed=set(),
                        only=set(outcome.too_large),
                        company_name=company_name,
                    )
                working, _ = memo_docx_renderer.repair_package_structure(working)
                working_errors = (
                    memo_docx_renderer.english_package_validation_errors(
                        working, editorial_risk_checks=False
                    )
                )
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_sectional_repair_applied",
                    message=(
                        f"Kept {len(outcome.repaired)} repaired section(s)"
                        + ("; envelope repaired" if outcome.envelope_repaired else "")
                        + (
                            f"; {len(outcome.failed)} section repair(s) failed"
                            if outcome.failed
                            else ""
                        )
                        + (
                            f"; trimmed instead: {', '.join(outcome.too_large)}"
                            if outcome.too_large
                            else ""
                        )
                    ),
                    repaired=list(outcome.repaired),
                    failed=dict(outcome.failed),
                    too_large=list(outcome.too_large),
                    envelope_repaired=outcome.envelope_repaired,
                    envelope_error=outcome.envelope_error,
                    unmapped=list(outcome.unmapped)[:10],
                    remaining_errors=working_errors[:10],
                )
                if not working_errors:
                    repaired_package = working
                elif _accept_with_small_overruns(
                    run_dir=run_dir,
                    package=working,
                    errors=working_errors,
                    progress=phase3_progress,
                ):
                    repaired_package = working
                    length_accepted = True
                else:
                    # The whole-package pass starts from what is already
                    # fixed, with only what is still wrong.
                    _write_json(invalid_path, working)
                    last_invalid_candidate = working
            if repaired_package is None:
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_sectional_repair_fallback",
                    message=(
                        (
                            f"Per-section repair left {len(working_errors)} "
                            "error(s)"
                            if ran
                            else "Per-section repair unavailable (no finding "
                            "attributable to a section or the envelope)"
                        )
                        + "; falling back to the whole-package pass"
                    ),
                    validation_errors=working_errors[:10],
                )
        repair_result, repair_error = (None, None)
        if repaired_package is None:
            repair_result, repair_error = (
                claude_runner.run_memo_package_structure_repair(
                    run_dir=run_dir,
                    company_name=company_name,
                    run_id=run_id,
                    package_path=invalid_path,
                    validation_errors=working_errors,
                    progress=phase3_progress,
                )
            )
        repaired_package = repaired_package or (
            repair_result.get("memo_package")
            if not repair_error and isinstance(repair_result, dict)
            else None
        )
        if isinstance(repaired_package, dict):
            repaired_package, _ = memo_docx_renderer.repair_package_structure(
                repaired_package
            )
            remaining_errors = (
                memo_docx_renderer.english_package_validation_errors(
                    repaired_package, editorial_risk_checks=False
                )
            )
            if remaining_errors and (
                length_accepted
                or _accept_with_small_overruns(
                    run_dir=run_dir,
                    package=repaired_package,
                    errors=remaining_errors,
                    progress=phase3_progress,
                )
            ):
                remaining_errors = []
            if not remaining_errors:
                quality_error = _memo_package_prerender_quality_error(
                    memo_docx_renderer.fill_blank_zh_placeholders(
                        repaired_package
                    ),
                    check_parity=False,
                    run_dir=run_dir,
                )
                if quality_error:
                    phase3_progress.emit(
                        "stage",
                        stage="memo_english_quality_warning",
                        message=(
                            "Repaired English package still has quality "
                            "findings; continuing with warnings"
                        ),
                        validation_error=quality_error[:4000],
                    )
                # The deterministic checks run inside the attempt loop, on
                # a candidate that passed validation. A package rescued here
                # never passed an attempt, so without this it shipped with no
                # pin check and no fact check at all — silently: RadixArk
                # 2026-09-21__195426 had the best evidence of any run (40
                # fetched pages, 79% of figures traceable) and its report
                # showed no fact check. Report only: the attempts are spent,
                # so the findings go on the record rather than to a repair.
                _run_memo_pin_check(
                    run_dir=run_dir,
                    candidate=repaired_package,
                    progress=phase3_progress,
                    attempt=None,
                )
                _run_memo_fact_check(
                    run_dir=run_dir,
                    candidate=repaired_package,
                    company_id=company_slug,
                    research_dir=research_dir,
                    progress=phase3_progress,
                    attempt=None,
                    session_dir=analysis_session_path,
                )
                english_result = dict(last_attempt_result or {})
                english_result["memo_package"] = repaired_package
                english_error = None
                last_transient = False
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_structure_repair_succeeded",
                    message=(
                        "Surgical structure repair fixed the package; "
                        "resuming the pipeline"
                    ),
                )
            else:
                phase3_progress.emit(
                    "stage",
                    stage="memo_package_structure_repair_failed",
                    message=(
                        "Surgical structure repair did not clear renderer "
                        "validation"
                    ),
                    validation_errors=remaining_errors[:10],
                )
        elif repair_error:
            phase3_progress.emit(
                "stage",
                stage="memo_package_structure_repair_failed",
                message="Surgical structure repair pass failed",
                error=str(repair_error)[:2000],
            )
    phase3_cost_delta = max(0.0, phase3_progress.cost_usd - phase3_cost_before)
    phase3_duration_delta = max(
        0, phase3_progress.duration_ms - phase3_duration_before
    )
    if speculator is not None:
        # The speculative spine and its delta check ran outside the Phase-3
        # side-channel; count their real spend (used or wasted) here so
        # every downstream total sees it.
        speculator_cost = speculator.cost_usd
        if speculator_cost:
            phase3_cost_delta += speculator_cost
        speculator.shutdown()
    if english_error or not isinstance(english_result, dict):
        message = english_error or "English package pass returned no data."
        # Cancel the side agents — pending chase units, the artifacts
        # agent — and count what they spent after the failure.
        phase3_cost_delta += _shutdown_side_agent(zh_chaser, cancel=True)
        phase3_cost_delta += _shutdown_side_agent(async_artifacts, cancel=True)
        phase3_progress.emit("thread_failed", error=message)
        _emit_phase_timing(
            stream,
            phase="memo_fast_english_package",
            status="failed",
            started_at=phase3_started_at,
            started_monotonic=phase3_started,
            error=message,
            attempts=attempts_used,
            max_attempts=max_attempts,
            transient=last_transient,
            cost_usd=round(phase3_cost_delta, 6),
            claude_duration_ms=phase3_duration_delta,
        )
        return {
            "ok": False,
            "error": message,
            "cost_usd": round(cost_usd + phase3_cost_delta, 6),
            "worker_duration_ms": worker_duration_ms + phase3_duration_delta,
        }
    phase3_added_cost = phase3_cost_delta or _as_float(
        english_result.get("claude_cost_usd")
    )
    # Duration prefers the parallel path's true wall-clock: the side-channel
    # delta SUMS the concurrent workers' durations (spine + artifacts + five
    # sections), which reported phase 3 as ~6x its real length. Cost keeps
    # the side-channel-first precedence — it must include failed attempts
    # and repair passes the final return value cannot see.
    phase3_added_duration = (
        _as_int(english_result.get("claude_wall_ms"))
        or phase3_duration_delta
        or _as_int(english_result.get("claude_duration_ms"))
    )
    cost_usd += phase3_added_cost
    worker_duration_ms += phase3_added_duration
    artifacts = english_result.get("analysis_artifacts")
    if (
        async_artifacts is not None
        and not isinstance(artifacts, dict)
        and not async_artifacts.done
        and not _internal_diligence_memo_enabled()
    ):
        # Report-ready detach: the package is accepted but the artifacts
        # agent is still writing. Park the handle instead of blocking —
        # _finalize_memo_from_package joins it after the DOCX renders, so
        # the user reads the report while the artifacts finish. Internal
        # diligence forces the inline join below (Phase 6 reads these
        # files); a monolithic fallback that returned artifacts inline
        # keeps the inline harvest too (cost accounting).
        _park_pending_artifacts(run_dir, async_artifacts)
        phase3_progress.emit(
            "stage",
            stage="memo_fast_english_artifacts_deferred",
            message=(
                "Analysis-artifacts agent still running; the run continues "
                "and collects it after the report is ready"
            ),
        )
        async_artifacts = None
    if async_artifacts is not None:
        # Harvest the detached artifacts agent. It started at wrapper entry
        # and the attempt loop ran spine + wave + gates since, so this join
        # is near-instant in practice; a slow agent still blocks strictly
        # later than the in-wave gate it replaced. Its cost never crossed
        # the attempt side-channel, so it is added here explicitly.
        join_result, join_error = async_artifacts.join(timeout_sec=900.0)
        cost_usd += _as_float((join_result or {}).get("claude_cost_usd"))
        worker_duration_ms += _as_int(
            (join_result or {}).get("claude_duration_ms")
        )
        if not isinstance(artifacts, dict):
            delivered = (
                join_result.get("analysis_artifacts")
                if isinstance(join_result, dict)
                else None
            )
            if not join_error and isinstance(delivered, dict):
                artifacts = delivered
            else:
                phase3_progress.emit(
                    "stage",
                    stage="memo_fast_english_artifacts_degraded",
                    message=(
                        "Detached analysis-artifacts agent failed; writing "
                        "stub artifacts "
                        f"({str(join_error or 'no artifacts returned')[:300]})"
                    ),
                )
                artifacts = {}
        async_artifacts.shutdown()
    if isinstance(artifacts, dict):
        _write_fast_synthesis_artifacts(run_dir, artifacts)
    english_package = english_result.get("memo_package")
    if not isinstance(english_package, dict):
        message = "English package pass did not return memo_package."
        cost_usd += _shutdown_side_agent(zh_chaser, cancel=True)
        phase3_progress.emit("thread_failed", error=message)
        _emit_phase_timing(
            stream,
            phase="memo_fast_english_package",
            status="failed",
            started_at=phase3_started_at,
            started_monotonic=phase3_started,
            error=message,
            attempts=attempts_used,
            max_attempts=max_attempts,
            cost_usd=round(phase3_added_cost, 6),
            claude_duration_ms=phase3_added_duration,
        )
        return {
            "ok": False,
            "error": message,
            "cost_usd": round(cost_usd, 6),
            "worker_duration_ms": worker_duration_ms,
        }
    # Red team the accepted English before it is rendered: challenges the
    # surgical repair can address are fixed here, the rest ship as warnings.
    # Phase 3's side-channel total was closed above, so the pass's spend
    # (its own call and the repair it drives) is measured here.
    red_team_cost_before = phase3_progress.cost_usd
    english_package, red_team_reported = _run_red_team_pass(
        run_dir=run_dir,
        company_name=company_name,
        run_id=run_id,
        package=english_package,
        attempt=attempts_used + 1,
        progress=phase3_progress,
        stream=stream,
        report_id=report_id,
        cost_so_far=cost_usd,
    )
    red_team_cost = max(
        max(0.0, phase3_progress.cost_usd - red_team_cost_before),
        red_team_reported,
    )
    if red_team_cost:
        cost_usd += red_team_cost
    english_result["memo_package"] = english_package
    try:
        claude_runner.extend_memo_glossary(run_dir, english_package)
    except Exception:  # noqa: BLE001
        logger.warning("glossary extension failed", exc_info=True)
    _stamp_envelope_facts(
        english_package,
        run_dir,
        company_id=company_slug,
        run_id=run_id,
        structure=structure,
        session_dir=analysis_session_path,
    )
    # Which models wrote it (the English memo is delivered before the
    # Chinese exists, so it carries the stamp too).
    _stamp_generated_with(
        english_package,
        storage.get_report(report_id) if report_id else None,
        run_dir,
        structure=structure,
    )
    _stamp_run_facts(english_package, run_dir)
    english_package_path = _english_package_path(run_dir)
    _write_json(english_package_path, english_package)
    phase3_progress.emit("thread_finished")
    _emit_phase_timing(
        stream,
        phase="memo_fast_english_package",
        status="finished",
        started_at=phase3_started_at,
        started_monotonic=phase3_started,
        memo_package=memo_prep._rel(english_package_path),
        attempts=attempts_used,
        max_attempts=max_attempts,
        cost_usd=round(phase3_added_cost, 6),
        claude_duration_ms=phase3_added_duration,
        usage=english_result.get("claude_usage")
        if isinstance(english_result.get("claude_usage"), dict)
        else None,
    )
    # English first: the reader has the English memo while the Chinese is
    # written, and nothing in the Chinese stage can take it away.
    _deliver_english_first(
        report_id=report_id,
        run_dir=run_dir,
        english_package=english_package,
        memo_paths=memo_paths,
        stream=stream,
    )
    if report_id and _pause_after_english_requested(report_id):
        # The analyst asked to review the English before the Chinese is
        # written: stop here; Resume continues from the accepted package.
        return _pause_run_after_english(
            report_id=report_id,
            run_dir=run_dir,
            english_package=english_package,
            memo_paths=memo_paths,
            stream=stream,
            zh_chaser=zh_chaser,
            cost_usd=cost_usd,
            worker_duration_ms=worker_duration_ms,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
    cost_stop = _cost_guard_stop(
        report_id=report_id,
        run_dir=run_dir,
        cost_usd=cost_usd,
        phase="Chinese version",
        stream=stream,
    )
    if cost_stop:
        # Past the ceiling before the Chinese starts: the English is
        # delivered alone, exactly as when the Chinese fails, so Resume
        # offers "Retry Chinese" once the ceiling is raised.
        cost_usd += _keep_chased_translations(run_dir, english_package, zh_chaser)
        cost_usd += _shutdown_side_agent(zh_chaser, cancel=True)
        _save_zh_partial(run_dir, None, english_package)
        chinese_error = (
            "Chinese version not started: the run's cost "
            f"(US${cost_stop['cost_usd']:.2f}) reached its "
            f"US${cost_stop['ceiling_usd']:.2f} ceiling"
        )
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        _emit_phase_timing(
            stream,
            phase="memo_fast_pipeline",
            status="finished",
            started_at=started_at,
            started_monotonic=started_monotonic,
            worker_duration_ms=worker_duration_ms,
            cost_usd=round(cost_usd, 6),
            english_only=True,
            cost_ceiling=True,
        )
        return {
            "ok": True,
            "english_only": True,
            "chinese_error": chinese_error,
            "cost_ceiling": cost_stop,
            "cost_usd": round(cost_usd, 6),
            "duration_ms": duration_ms,
            "worker_duration_ms": worker_duration_ms,
            "fast_pipeline": True,
        }

    phase4_started_at = _now_iso()
    phase4_started = time.monotonic()
    phase4_progress = _ThreadProgress(stream, claude_runner._MEMO_PHASE4_THREAD)
    phase4_progress.emit("thread_started", title=claude_runner._MEMO_PHASE4_THREAD)
    _emit_phase_timing(
        stream,
        phase="memo_fast_chinese_package",
        status="started",
        started_at=phase4_started_at,
        started_monotonic=phase4_started,
    )
    # Chinese chasing: join the speculative per-section translations that
    # raced Phase 3, merge whatever still matches the accepted English
    # (repaired strings are silently dropped by the exact-en-match rule),
    # and let the normal pass below gap-fill the rest. memo_package.en.json
    # stays the pure accepted-English artifact; the merged input gets its
    # own file.
    bilingual_input_path = english_package_path
    if zh_chaser is not None and zh_chaser.has_units:
        chase_started_at = _now_iso()
        chase_started = time.monotonic()
        phase4_progress.emit(
            "stage",
            stage="memo_zh_chase_join",
            message=(
                f"Joining {zh_chaser.unit_count} speculative Chinese "
                "chase units"
            ),
        )
        chase_outcome = zh_chaser.collect()
        chase_stats = zh_chaser.merge_into(
            english_package, chase_outcome["units"]
        )
        cost_usd += _as_float(chase_outcome.get("cost_usd"))
        worker_duration_ms += _as_int(chase_outcome.get("duration_ms"))
        _emit_phase_timing(
            stream,
            phase="memo_zh_chase",
            status="finished",
            started_at=chase_started_at,
            started_monotonic=chase_started,
            cost_usd=chase_outcome.get("cost_usd"),
            units_chased=len(chase_outcome["units"]),
            units_missed=len(chase_outcome["missed"])
            + len(chase_outcome["failed"]),
            strings_adopted=chase_stats["adopted"],
            strings_blank_remaining=chase_stats["blank_after"],
        )
        phase4_progress.emit(
            "stage",
            stage="memo_zh_chase_merge",
            message=(
                f"Adopted {chase_stats['adopted']} chased translations; "
                f"{chase_stats['blank_after']} strings left for the gap-fill"
            ),
            units_chased=len(chase_outcome["units"]),
            units_missed=len(chase_outcome["missed"])
            + len(chase_outcome["failed"]),
            strings_adopted=chase_stats["adopted"],
            strings_blank_remaining=chase_stats["blank_after"],
        )
        bilingual_input_path = run_dir / "logs" / "memo_package.en.chased.json"
        _write_json(bilingual_input_path, english_package)
    if zh_chaser is not None:
        zh_chaser.shutdown()
    # Fan the pure-translation Chinese pass out per-section (R6d); it
    # falls back to the monolithic pass on any unexpected shape/failure.
    # With only_missing=True this is the gap-fill when chasing ran, and
    # exactly the historical full translation when it didn't.
    chinese = _run_chinese_package_stage(
        run_dir=run_dir,
        company_name=company_name,
        run_id=run_id,
        bilingual_input_path=bilingual_input_path,
        progress=phase4_progress,
        stream=stream,
    )
    cost_usd += chinese.cost_usd
    worker_duration_ms += chinese.duration_ms
    if chinese.error:
        # The Chinese never costs the reader the English: the accepted
        # English package is on disk (and its DOCX already rendered), so
        # the run finishes on it — complete_with_warnings, failure_phase
        # chinese_package — and "Retry Chinese" (a branch of Resume)
        # translates only what is still blank from the saved partial.
        partial_path = _save_zh_partial(run_dir, chinese.partial, english_package)
        phase4_progress.emit("thread_failed", error=chinese.error)
        _emit_phase_timing(
            stream,
            phase="memo_fast_chinese_package",
            status="failed",
            started_at=phase4_started_at,
            started_monotonic=phase4_started,
            error=chinese.error,
            english_delivered=True,
            zh_partial=memo_prep._rel(partial_path),
        )
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        _emit_phase_timing(
            stream,
            phase="memo_fast_pipeline",
            status="finished",
            started_at=started_at,
            started_monotonic=started_monotonic,
            worker_duration_ms=worker_duration_ms,
            cost_usd=round(cost_usd, 6),
            english_only=True,
        )
        return {
            "ok": True,
            "english_only": True,
            "chinese_error": chinese.error,
            "cost_usd": round(cost_usd, 6),
            "duration_ms": duration_ms,
            "worker_duration_ms": worker_duration_ms,
            "fast_pipeline": True,
        }
    final_package_path = _memo_package_path(run_dir)
    # Now the translator has run too.
    _stamp_generated_with_on_disk(
        final_package_path,
        storage.get_report(report_id) if report_id else None,
        run_dir,
    )
    # English vocabulary was gated in phase 3; this pass surfaces the
    # bilingual findings (Chinese parity) early. They never block — the
    # memo is delivered and finalize marks it complete_with_warnings. Its
    # outcome is what the documents' provenance line states (run.checks).
    prerender_findings = _memo_package_prerender_quality_findings(
        final_package_path, run_dir=run_dir
    )
    try:
        _stamp_prerender_gates(final_package_path, prerender_findings)
    except Exception:  # noqa: BLE001
        logger.warning("gate stamp failed", exc_info=True)
    quality_warning = "; ".join(prerender_findings) if prerender_findings else None
    if quality_warning:
        phase4_progress.emit(
            "stage",
            stage="memo_package_quality_warning",
            message=(
                "Merged bilingual package has quality findings; delivering "
                "with warnings"
            ),
            validation_error=quality_warning[:4000],
        )
    phase4_progress.emit("thread_finished")
    _emit_phase_timing(
        stream,
        phase="memo_fast_chinese_package",
        status="finished",
        started_at=phase4_started_at,
        started_monotonic=phase4_started,
        memo_package=memo_prep._rel(final_package_path),
        cost_usd=round(chinese.cost_usd, 6),
        claude_duration_ms=chinese.duration_ms,
        usage=chinese.usage,
    )

    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    _emit_phase_timing(
        stream,
        phase="memo_fast_pipeline",
        status="finished",
        started_at=started_at,
        started_monotonic=started_monotonic,
        worker_duration_ms=worker_duration_ms,
        cost_usd=round(cost_usd, 6),
    )
    return {
        "ok": True,
        "cost_usd": round(cost_usd, 6),
        "duration_ms": duration_ms,
        "worker_duration_ms": worker_duration_ms,
        "fast_pipeline": True,
    }


def _fail_renderer_contract(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
    result: dict,
    message: str,
    contract: dict | None = None,
    recovered: bool = False,
) -> None:
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Renderer contract failed",
        error=message,
        failure_phase="renderer_contract",
        failure_detail=message,
        renderer_contract=contract or {},
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    payload = {
        "error": message,
        "phase": "renderer_contract",
        "failure_phase": "renderer_contract",
    }
    if contract:
        payload["contract_errors"] = list(contract.get("errors") or [])
        payload["expected_files"] = list(contract.get("expected_files") or [])
        payload["run_dir"] = contract.get("run_dir")
        payload["memo_package"] = contract.get("memo_package")
    if recovered:
        payload["recovered"] = True
    stream.emit(
        "thread_failed",
        thread=claude_runner.MEMO_PHASE5_THREAD,
        error=message,
    )
    stream.emit("error", **payload)


def _scan_memo_stream(run_dir: Path) -> dict:
    """Summarize the memo stream enough for stale-run recovery."""
    path = memo_prep.stream_path(run_dir)
    state = {
        "terminal": None,
        "success_result": None,
        "open_threads": set(),
    }
    if not path.exists():
        return state
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = entry.get("type")
                if etype in ("done", "error"):
                    state["terminal"] = entry
                elif etype == "thread_started" and entry.get("thread"):
                    state["open_threads"].add(entry["thread"])
                elif (
                    etype in ("thread_finished", "thread_failed")
                    and entry.get("thread")
                ):
                    state["open_threads"].discard(entry["thread"])
                elif (
                    etype == "claude_action"
                    and entry.get("action") == "result"
                    and entry.get("subtype") != "error"
                    and not entry.get("is_error")
                    and state["success_result"] is None
                ):
                    state["success_result"] = entry
    except Exception:
        logger.exception("failed to scan memo progress stream for %s", run_dir)
    return state


def _recover_done_memo_report(
    *,
    report: dict,
    run_dir: Path,
    terminal: dict,
) -> bool:
    report_id = str(report.get("id") or "")
    if not report_id:
        return False
    memo_paths_abs = _memo_paths_abs(report)
    if not memo_paths_abs.get("en") or not memo_paths_abs.get("zh"):
        return False
    package_path = _memo_package_path(run_dir)
    if _memo_package_render_validation_error(package_path):
        return False
    contract = _renderer_contract_diagnostics(
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
    )
    if contract.get("errors"):
        return False
    expected_files = contract.get("expected_files") or []
    if any(not item.get("exists") for item in expected_files):
        return False

    parity_result = memo_chinese_parity.lint_chinese_memo_pair(
        memo_paths_abs["en"],
        memo_paths_abs["zh"],
        _structure_for_run(run_dir),
        package=_package_on_disk(package_path),
        run_dir=run_dir,
    )
    if parity_result.has_blocking_findings:
        return False
    parity_path = run_dir / "logs" / "memo_chinese_parity.md"
    parity_path.write_text(
        memo_chinese_parity.render_markdown_report(parity_result),
        encoding="utf-8",
    )

    lint_result = _lint_memo(memo_paths_abs["en"], _structure_for_run(run_dir), run_dir)
    if lint_result.has_blocking_findings:
        return False
    lint_path = run_dir / "logs" / "memo_quality_lint.md"
    lint_path.write_text(
        memo_quality_lint.render_markdown_report(lint_result),
        encoding="utf-8",
    )

    # This re-finalize recomputes only the English lint and the Chinese
    # parity gates. Every other warning the run delivered with (coverage,
    # cost, length, claims, risk cards, signposts …) is preserved: a
    # restart used to wipe them all and re-record the run as a clean
    # `complete`.
    kept = _preserved_warning_items(report)
    _update_report(
        report_id,
        status="complete_with_warnings" if kept.items else "complete",
        stage="Memo ready (quality warnings)" if kept.items else "Memo ready",
        progress=100,
        error=None,
        failure_phase=None,
        failure_detail=None,
        resume_from_status=None,
        resume_from_failure_phase=None,
        resume_from_failure_detail=None,
        artifacts_available=True,
        renderer_contract=contract,
        memo_chinese_parity=parity_result.to_dict(),
        memo_quality_lint=lint_result.to_dict(),
        memo_fact_check=_fact_check_payload(run_dir),
        claude_cost_usd=terminal.get("cost_usd"),
        claude_duration_ms=terminal.get("duration_ms"),
        generated_with=_package_generated_with(package_path),
        **kept.record_fields(),
    )
    _run_completion_hooks(report_id)
    return True


# The gates a startup re-finalize recomputes; warning items from every
# other gate are carried over unchanged.
_RECOMPUTED_WARNING_GATES = frozenset({"quality", "chinese_parity"})


def _preserved_warning_items(report: dict) -> "_RunWarnings":
    """The record's warnings minus the gates ``_recover_done_memo_report``
    recomputes. The English strings and their Chinese twins are kept only
    when at least one structured item survives (they are the banner text
    for those items); the quality/parity strings are dropped by their
    wording."""
    kept = _RunWarnings()
    items = [
        item
        for item in list(report.get("quality_warning_items") or [])
        if isinstance(item, dict)
        and str(item.get("gate") or "") not in _RECOMPUTED_WARNING_GATES
    ]
    if not items:
        return kept
    en_lines = [str(w) for w in list(report.get("quality_warnings") or []) if w]
    zh_lines = [str(w) for w in list(report.get("quality_warnings_zh") or []) if w]
    aligned = len(en_lines) == len(zh_lines)
    for index, line in enumerate(en_lines):
        lowered = line.lower()
        if "quality gate" in lowered or "memo quality" in lowered or "parity" in lowered:
            continue
        kept.en.append(line)
        kept.zh.append(zh_lines[index] if aligned else "恢复运行时保留的检查结果（详见运行日志）。")
    kept.items = items
    return kept


# A run whose stream has been silent this long, with no live worker thread,
# was orphaned (e.g. a restart killed the daemon thread mid-generation).
ORPHAN_IDLE_THRESHOLD_SEC = 30 * 60


def _memo_worker_alive(report_id: str) -> bool:
    names = {
        f"memo-analysis-{report_id}",
        f"memo-resume-{report_id}",
        f"memo-investigate-{report_id}",
        f"memo-generate-{report_id}",
        f"buffett-memo-analysis-{report_id}",
        f"buffett-memo-resume-{report_id}",
    }
    return any(
        t.name in names and t.is_alive() for t in threading.enumerate()
    )


def _demote_orphaned_report(report: dict, run_dir: Path) -> bool:
    """Flip a restart-orphaned ``analyzing`` run to ``failed_during_analysis``.

    A run stuck in a non-terminal status whose stream has been idle beyond
    the threshold, with no live worker thread, can never finish on its own —
    and while it stays ``analyzing`` it is invisible to the resume path
    (which requires ``status.startswith("failed")``). Demoting it makes the
    Resume button appear.
    """
    report_id = str(report.get("id") or "")
    status = str(report.get("status") or "")
    if not report_id or status.startswith("failed") or status == "complete":
        return False
    stream_path = memo_prep.stream_path(run_dir)
    try:
        ref = stream_path if stream_path.exists() else run_dir
        idle_sec = time.time() - ref.stat().st_mtime
    except OSError:
        return False
    if idle_sec < ORPHAN_IDLE_THRESHOLD_SEC:
        return False
    if _memo_worker_alive(report_id):
        return False
    message = "orphaned by server restart"
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Analysis orphaned",
        error=message,
        failure_phase="orphaned",
        failure_detail=message,
    )
    stream = job_progress.ProgressLog(stream_path, truncate=False)
    stream.emit("error", error=message, phase="orphaned", recovered=True)
    _sync_tracking_auto_run(report, success=False, error=message)
    logger.warning(
        "memo run %s demoted to failed_during_analysis after %ds idle",
        report_id,
        int(idle_sec),
    )
    return True


INTERRUPTED_BEFORE_PACKAGE = "interrupted before the memo package was written"


def _stream_last_activity(run_dir: Path) -> str | None:
    """When the run's stream was last written (ISO, UTC) — read before a
    recovery sweep appends to it."""
    try:
        mtime = memo_prep.stream_path(run_dir).stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _demote_interrupted_report(
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    *,
    last_activity_at: str | None = None,
) -> None:
    """A hard kill (SIGKILL, crash) stopped the run before its package was
    written: say so, as failure_phase "interrupted" — resumable, and
    auto-resumed at startup while the run is recent
    (``api.resume_interrupted_memo_runs`` reads ``last_activity_at``)."""
    report_id = str(report.get("id") or "")
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Analysis interrupted",
        error=INTERRUPTED_BEFORE_PACKAGE,
        failure_phase="interrupted",
        failure_detail=INTERRUPTED_BEFORE_PACKAGE,
        **({"last_activity_at": last_activity_at} if last_activity_at else {}),
    )
    stream.emit(
        "error", error=INTERRUPTED_BEFORE_PACKAGE, phase="interrupted", recovered=True
    )
    _sync_tracking_auto_run(report, success=False, error=INTERRUPTED_BEFORE_PACKAGE)


def recover_stale_reports() -> int:
    """Repair memo runs whose worker died before finalization.

    Two cases:
      - Claude succeeded but the worker was interrupted before rendering →
        finish the render and mark ``complete`` (conservative: requires a
        successful Claude result and a renderer-valid package).
      - The worker was killed mid-generation (no result, stream cold, no
        live thread) → demote to ``failed_during_analysis`` so the existing
        resume path can pick the run up.
    """
    recovered = 0
    for report in storage.list_reports():
        if report.get("kind") != "investment_memo_latestage":
            continue
        if report.get("status") in ("complete", "failed_scope_check"):
            continue
        if report.get("status") in ("awaiting_studio", PAUSED_AFTER_ENGLISH_STATUS):
            # A parked Memo Studio investigation, or a run paused after its
            # English for review, is a deliberate terminal state (its
            # stream already carries `done`); nothing to recover.
            continue
        run_dir = _resolve_run_dir(report)
        if run_dir is None or not run_dir.exists():
            continue
        stream_state = _scan_memo_stream(run_dir)
        terminal = stream_state.get("terminal")
        if terminal is not None:
            if (
                terminal.get("type") == "done"
                and report.get("status") == "complete_with_warnings"
            ):
                # Delivered, with its warnings on the record and a `done`
                # in the stream: finished. Re-finalizing it here used to
                # rewrite the record as a clean `complete`, wiping every
                # warning the run had recorded.
                continue
            if (
                terminal.get("type") == "done"
                and _recover_done_memo_report(
                    report=report,
                    run_dir=run_dir,
                    terminal=terminal,
                )
            ):
                recovered += 1
            continue
        result = stream_state.get("success_result")
        if not result:
            # Killed mid-generation: nothing to render, but don't abandon
            # the run at "analyzing" forever — make it resume-eligible.
            if _demote_orphaned_report(report, run_dir):
                recovered += 1
            continue
        memo_paths_abs = _memo_paths_abs(report)
        if not memo_paths_abs:
            continue
        if _memo_worker_alive(str(report.get("id") or "")):
            # A run started in this process since the restart.
            continue
        last_activity_at = _stream_last_activity(run_dir)

        stream = job_progress.ProgressLog(
            memo_prep.stream_path(run_dir), truncate=False
        )
        for thread_label in sorted(stream_state.get("open_threads") or ()):
            stream.emit("thread_finished", thread=thread_label)
        if _block_generated_renderer_scripts(
            report_id=report["id"],
            run_dir=run_dir,
            stream=stream,
            result=result,
            recovered=True,
        ):
            continue
        package_path = _memo_package_path(run_dir)
        if not package_path.exists() or _memo_package_render_validation_error(
            package_path
        ):
            # One successful Claude call (an analysis pass, the spine) is
            # not a finished run. Rendering from it used to record
            # "Memo rendering failed" for runs a hard kill interrupted
            # (ATE, Anthropic, AMD). At startup no worker of the killed
            # process is alive, so there is no idle wait here.
            if _english_delivered(report, run_dir):
                # The English was delivered before the kill: keep it, and
                # let Resume retry only the Chinese.
                _complete_english_only_after_cancel(
                    report["id"], report, run_dir, reason="interrupted"
                )
            else:
                _demote_interrupted_report(
                    report, run_dir, stream, last_activity_at=last_activity_at
                )
            recovered += 1
            continue
        if not _render_memo_outputs(
            report_id=report["id"],
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=True,
        ):
            continue
        _maybe_render_memo_pdf_previews(
            report_id=report["id"],
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            progress=86,
            recovered=True,
        )
        recovery_warnings: list[str] = []
        _parity_payload, parity_warning = _run_chinese_parity_gate(
            report_id=report["id"],
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=True,
        )
        if parity_warning:
            recovery_warnings.append(parity_warning)
        lint_result, lint_path = _lint_memo_quality_gate(
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            recovered=True,
        )
        lint_payload = lint_result.to_dict()
        _update_report(
            report["id"],
            memo_quality_lint=lint_payload,
            memo_fact_check=_fact_check_payload(run_dir),
        )
        if lint_result.has_blocking_findings:
            msg = (
                "Memo quality gate found "
                f"{lint_payload['p0_count']} P0 finding"
                f"{'' if lint_payload['p0_count'] == 1 else 's'}. "
                f"See {memo_prep._rel(lint_path)}."
            )
            recovery_warnings.append(msg)
            stream.emit(
                "stage",
                stage="quality_gate_warning",
                message=msg,
                phase="quality_gate",
                recovered=True,
                lint_report=memo_prep._rel(lint_path),
                findings=lint_payload["findings"][:10],
            )
        _update_report(
            report["id"],
            status=(
                "complete_with_warnings" if recovery_warnings else "complete"
            ),
            stage=(
                "Memo ready (quality warnings)"
                if recovery_warnings
                else "Memo ready"
            ),
            progress=100,
            quality_warnings=recovery_warnings or None,
            quality_warnings_zh=[
                "恢复运行时检查发现问题（详见运行日志）。" for _ in recovery_warnings
            ]
            or None,
            quality_warning_items=[
                _warning_item(
                    gate="chinese_parity" if "parity" in w.lower() else "quality",
                    language="ZH" if "parity" in w.lower() else "EN",
                    summary_en=w,
                    summary_zh="恢复运行时检查发现问题（详见运行日志）。",
                    code="recovered_run",
                )
                for w in recovery_warnings
            ]
            or None,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        done_payload = {
            "report_id": report["id"],
            "memo_paths": {k: str(v) for k, v in memo_paths_abs.items()},
            "cost_usd": result.get("cost_usd"),
            "duration_ms": result.get("duration_ms"),
            "recovered": True,
        }
        if recovery_warnings:
            done_payload["quality_warnings"] = recovery_warnings
        stream.emit("done", **done_payload)
        _run_completion_hooks(report["id"])
        recovered += 1
    return recovered


# ---- Run slots -------------------------------------------------------------
# Every memo worker (One-Click, investigate, generate, resume, Buffett)
# takes a slot before doing any real work. User-started runs share
# `product_store.memo_parallel_runs()` slots (the Settings knob — each run
# spawns many claude subprocesses, so uncapped launches can OOM the
# machine) and wait FIFO in a "queued" state when full. Tracking
# auto-runs (trigger=tracking_auto_run) have their own small reserved
# lane so News/Updates never competes with the user's cap.
TRACKING_RESERVED_SLOTS = 2
# Registry entries older than this with no live worker thread are leaked
# (a crash that skipped release) and get swept on the next acquire.
_SLOT_LEAK_GRACE_SEC = 60.0

_SLOT_COND = threading.Condition()
_SLOT_ACTIVE: dict[str, tuple[bool, float]] = {}  # id -> (reserved, acquired_at)
_SLOT_WAITERS: list[tuple[int, str, bool]] = []  # (ticket, report_id, reserved)
_SLOT_TICKETS = itertools.count()
_SLOT_CANCELLED: set[str] = set()


def _sweep_leaked_slots_locked() -> None:
    now = time.monotonic()
    for rid, (_reserved, acquired_at) in list(_SLOT_ACTIVE.items()):
        if now - acquired_at < _SLOT_LEAK_GRACE_SEC:
            continue
        if not _memo_worker_alive(rid):
            logger.warning("run slot for %s leaked (worker gone); reclaiming", rid)
            _SLOT_ACTIVE.pop(rid, None)


def _slot_eligible_locked(ticket: int, reserved: bool) -> bool:
    cap = (
        TRACKING_RESERVED_SLOTS
        if reserved
        else product_store.memo_parallel_runs()
    )
    active = sum(1 for r, _t in _SLOT_ACTIVE.values() if r == reserved)
    if active >= cap:
        return False
    # FIFO within each lane: an earlier waiter of the same lane goes first.
    return not any(
        t < ticket for t, _rid, r in _SLOT_WAITERS if r == reserved
    )


def _announce_run_queued(report_id: str) -> None:
    try:
        report = storage.get_report(report_id)
        if not report:
            return
        _update_report(
            report_id, status="queued", stage="Waiting for a run slot"
        )
        run_dir = _resolve_run_dir(report)
        if run_dir is not None and run_dir.exists():
            job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            ).emit(
                "stage",
                stage="run_slot_queued",
                message=(
                    "Waiting for a free run slot (parallel-run limit in "
                    "Settings)"
                ),
            )
    except Exception:  # noqa: BLE001
        logger.exception("failed to mark run %s queued", report_id)


def acquire_run_slot(report_id: str, *, reserved: bool) -> bool:
    """Block until this run may proceed. False = cancelled while queued or
    the server is shutting down."""
    queued_announced = False
    with _SLOT_COND:
        _SLOT_CANCELLED.discard(report_id)  # a fresh start overrides old cancels
        ticket = next(_SLOT_TICKETS)
        entry = (ticket, report_id, reserved)
        _SLOT_WAITERS.append(entry)
        try:
            while True:
                if report_id in _SLOT_CANCELLED:
                    _SLOT_CANCELLED.discard(report_id)
                    return False
                if claude_runner.shutting_down():
                    return False
                _sweep_leaked_slots_locked()
                if _slot_eligible_locked(ticket, reserved):
                    _SLOT_ACTIVE[report_id] = (reserved, time.monotonic())
                    break
                if not queued_announced:
                    queued_announced = True
                    _announce_run_queued(report_id)
                # Timed wait doubles as the re-check when the Settings cap
                # is raised mid-queue (no cross-module notify needed).
                _SLOT_COND.wait(2.0)
        finally:
            _SLOT_WAITERS.remove(entry)
    if queued_announced:
        try:
            _update_report(
                report_id, status="analyzing", stage="Run slot acquired"
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to un-queue run %s", report_id)
    return True


def release_run_slot(report_id: str) -> None:
    with _SLOT_COND:
        _SLOT_ACTIVE.pop(report_id, None)
        _SLOT_CANCELLED.discard(report_id)
        _SLOT_COND.notify_all()


def cancel_queued_run_slot(report_id: str) -> None:
    """Abort a run waiting for a slot (no-op for active/unknown runs)."""
    with _SLOT_COND:
        if any(rid == report_id for _t, rid, _r in _SLOT_WAITERS):
            _SLOT_CANCELLED.add(report_id)
            _SLOT_COND.notify_all()


def reserved_run_slots_available() -> bool:
    """Cheap pre-check for the tracking loop: is a reserved slot free now?"""
    with _SLOT_COND:
        _sweep_leaked_slots_locked()
        active = sum(1 for r, _t in _SLOT_ACTIVE.values() if r)
        waiting = sum(1 for _t, _rid, r in _SLOT_WAITERS if r)
        return active + waiting < TRACKING_RESERVED_SLOTS


# ---- Deferred artifacts tail ------------------------------------------
# When the detached artifacts agent (BSH_MEMO_ARTIFACTS_ASYNC) is still
# running at package acceptance, the run no longer waits for it: the
# handle parks here (keyed by run dir) and _finalize_memo_from_package
# joins it AFTER the DOCX is rendered and the report is marked complete —
# the "report ready, finalizing artifacts" tail the jobs rail shows.
# Failure paths abandon the handle via _abandon_pending_artifacts (called
# from the worker's finally) so a dead run never leaves a paid agent
# running unattended.
_PENDING_ARTIFACTS: dict[str, "claude_runner.AsyncArtifacts"] = {}
_PENDING_ARTIFACTS_LOCK = threading.Lock()


def _park_pending_artifacts(run_dir: Path, handle) -> None:
    with _PENDING_ARTIFACTS_LOCK:
        _PENDING_ARTIFACTS[str(run_dir)] = handle


def _pop_pending_artifacts(run_dir: Path):
    with _PENDING_ARTIFACTS_LOCK:
        return _PENDING_ARTIFACTS.pop(str(run_dir), None)


def _abandon_pending_artifacts(report_id: str) -> None:
    """Reap a parked artifacts agent whose run never reached finalize."""
    report = storage.get_report(report_id)
    run_dir = _resolve_run_dir(report or {})
    if run_dir is None:
        return
    handle = _pop_pending_artifacts(run_dir)
    if handle is None:
        return
    try:
        claude_runner.terminate_claude_procs_under(str(run_dir))
    except Exception:  # noqa: BLE001
        logger.warning(
            "failed to reap abandoned artifacts agent for %s",
            report_id,
            exc_info=True,
        )
    handle.shutdown()


def _with_run_slot(report_id: str, worker) -> None:
    """Slot + cancel bookkeeping around one memo worker body."""
    report = storage.get_report(report_id)
    run_dir = _resolve_run_dir(report or {})
    _clear_run_halt(report_id)
    if run_dir is not None:
        claude_runner.reset_run_dir_state(str(run_dir))
    reserved = bool((report or {}).get("trigger") == "tracking_auto_run")
    if not acquire_run_slot(report_id, reserved=reserved):
        # Cancelled while queued or shutting down; cancel_run / the shutdown
        # hook already wrote the terminal status and stream event.
        return
    try:
        worker()
    finally:
        release_run_slot(report_id)
        _abandon_pending_artifacts(report_id)
        if run_dir is not None:
            claude_runner.reset_run_dir_state(str(run_dir))


def _english_delivered(report: dict, run_dir: Path) -> bool:
    """The run already delivered its English memo: English-first wrote the
    DOCX and the accepted English package is on disk."""
    if not report.get("english_ready_at"):
        return False
    en_path = _memo_paths_abs(report).get("en")
    return bool(
        en_path and en_path.exists() and _english_package_path(run_dir).exists()
    )


CHINESE_INTERRUPTED_WARNING = (
    "Chinese version interrupted — English delivered",
    "中文版生成被中断，已交付英文版",
)


def _complete_english_only_after_cancel(
    report_id: str, report: dict, run_dir: Path, *, reason: str = "cancelled"
) -> None:
    """Terminal state for a run stopped after its English memo was
    delivered: a cancel (written by the cancelling call itself — the worker
    is halted, so nothing it does while unwinding reaches the record) or a
    hard kill found at startup (``reason="interrupted"``)."""
    interrupted = reason == "interrupted"
    memo_paths_abs = _memo_paths_abs(report)
    both_languages = bool(
        memo_paths_abs.get("zh")
        and memo_paths_abs["zh"].exists()
        and _memo_package_path(run_dir).exists()
    )
    warnings = _RunWarnings()
    if both_languages:
        # The Chinese had already landed; the cancel stopped the final
        # checks. Both documents stay; the checks can be re-run by Resume.
        warnings.add(
            (
                "Interrupted during the final checks — memo delivered without them"
                if interrupted
                else "Cancelled during the final checks — memo delivered without them"
            ),
            (
                "在最终检查阶段被中断——备忘录已交付，但检查未完成"
                if interrupted
                else "在最终检查阶段被取消——备忘录已交付，但检查未完成"
            ),
            [
                _warning_item(
                    gate="run",
                    language="EN",
                    summary_en="Cancelled during the final checks; both languages were already written.",
                    summary_zh="在最终检查阶段被取消；中英文版本均已生成。",
                    code="cancelled_during_checks",
                )
            ],
        )
    else:
        _retire_stale_chinese_docx(memo_paths_abs)
        en_text, zh_text = (
            CHINESE_INTERRUPTED_WARNING if interrupted else CHINESE_CANCELLED_WARNING
        )
        warnings.add(
            en_text,
            zh_text,
            [
                _warning_item(
                    gate=CHINESE_PACKAGE_PHASE,
                    language="ZH",
                    summary_en=f"{en_text}. Resume retries the Chinese only.",
                    summary_zh=f"{zh_text}。“重试中文版”只重新生成中文。",
                    code="chinese_interrupted" if interrupted else "chinese_cancelled",
                    detail_path=memo_prep._rel(_zh_partial_package_path(run_dir)),
                )
            ],
        )
        partial_path = _zh_partial_package_path(run_dir)
        if not partial_path.exists():
            # Retry Chinese starts from here: whatever chased translations
            # were merged, else the accepted English.
            for candidate in (
                run_dir / "logs" / "memo_package.en.chased.json",
                _english_package_path(run_dir),
            ):
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(payload, dict):
                    _write_json(partial_path, payload)
                    break
    halted = "interrupted" if interrupted else "cancelled"
    storage.update_report(
        report_id,
        status="complete_with_warnings",
        stage=(
            f"Memo ready ({halted} during final checks)"
            if both_languages
            else f"Memo ready — English only (Chinese {halted})"
        ),
        progress=100,
        error=None,
        failure_phase=None if both_languages else CHINESE_PACKAGE_PHASE,
        failure_detail=(
            None
            if both_languages
            else (
                "Interrupted by a server restart during the Chinese step"
                if interrupted
                else "Cancelled by user during the Chinese step"
            )
        ),
        artifacts_available=True,
        english_only=None if both_languages else True,
        report_ready_at=_now_iso(),
        run_finished_at=_now_iso(),
        **warnings.record_fields(),
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=False)
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={
            k: str(v)
            for k, v in memo_paths_abs.items()
            if both_languages or k == "en"
        },
        english_only=not both_languages,
        quality_warnings=list(warnings.en),
        **({"recovered": True} if interrupted else {"cancelled": True}),
    )
    _complete_tracking_auto_run(report, success=True)
    _run_completion_hooks(report_id, force=True)


def cancel_run(report_id: str) -> None:
    """Cancel a queued or in-flight memo run.

    Kills the run's claude subprocesses (matched by spawn cwd, plus the
    run's pid file for processes an earlier server left behind), blocks
    respawns via the run-dir marker, writes the terminal report status and
    stream event, and finalizes any tracking auto-run. The worker thread
    then unwinds on its own as its in-flight calls return cancelled; the
    run is halted first so nothing it writes while unwinding replaces the
    cancelled state.

    Once the English memo was delivered (``english_ready_at`` and its DOCX
    on disk), a cancel means "stop the Chinese", not "discard everything":
    the run ends ``complete_with_warnings`` on the English alone, and
    Resume offers "Retry Chinese".
    """
    report = storage.get_report(report_id)
    if not report:
        raise ValueError("report_not_found")
    message = "Cancelled by user"
    _halt_run(report_id)
    cancel_queued_run_slot(report_id)
    run_dir = _resolve_run_dir(report)
    if run_dir is not None:
        claude_runner.mark_run_dir_cancelled(str(run_dir))
        # Reaping waits up to a few seconds per process; do it off the
        # request path.
        threading.Thread(
            target=claude_runner.terminate_claude_procs_under,
            args=(str(run_dir),),
            name=f"memo-cancel-{report_id}",
            daemon=True,
        ).start()
    if run_dir is not None and _english_delivered(report, run_dir):
        _complete_english_only_after_cancel(report_id, report, run_dir)
        return
    storage.update_report(
        report_id,
        status="failed_during_analysis",
        stage="Cancelled",
        error=message,
        # Distinct phase on purpose: the startup auto-resume sweep only
        # relaunches failure_phase == "shutdown".
        failure_phase="cancelled",
        failure_detail=message,
    )
    if run_dir is not None and run_dir.exists():
        stream = job_progress.ProgressLog(
            memo_prep.stream_path(run_dir), truncate=False
        )
        stream.emit("error", error=message, phase="cancelled")
    _complete_tracking_auto_run(report, success=False, error=message)


# Report ids with a live in-process worker. Used by the shutdown hook to
# write a terminal error event for anything a clean restart would otherwise
# orphan at "analyzing" forever (the demote sweep covers hard kills).
_ACTIVE_RUNS: set[str] = set()
_ACTIVE_RUNS_LOCK = threading.Lock()


def _register_active_run(report_id: str) -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS.add(report_id)


def _unregister_active_run(report_id: str) -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS.discard(report_id)


@atexit.register
def halt_active_runs_for_shutdown() -> None:
    """Write a terminal error for in-flight memo runs when the server stops.

    Called from the server's shutdown hook before the claude subprocesses
    are reaped (atexit stays as a backstop). The workers are daemon
    threads, so a clean shutdown (Ctrl-C, --reload, SIGTERM via uvicorn's
    handler) kills them silently. This makes the interruption visible and
    resume-eligible immediately instead of waiting for the 30-minute orphan
    sweep; each run is halted first so the failures its worker records
    while unwinding cannot replace ``failure_phase="shutdown"``. A SIGKILL
    skips all of this — that path is covered by ``_demote_orphaned_report``.
    """
    with _ACTIVE_RUNS_LOCK:
        active = list(_ACTIVE_RUNS)
    for report_id in active:
        try:
            report = storage.get_report(report_id)
            status = str((report or {}).get("status") or "")
            if not report or status.startswith("failed") or status == "complete":
                continue
            _halt_run(report_id)
            message = "interrupted by server shutdown"
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Analysis interrupted",
                error=message,
                failure_phase="shutdown",
                failure_detail=message,
            )
            run_dir = _resolve_run_dir(report)
            if run_dir is not None:
                stream = job_progress.ProgressLog(
                    memo_prep.stream_path(run_dir), truncate=False
                )
                stream.emit("error", error=message, phase="shutdown")
        except Exception:  # noqa: BLE001 — never let shutdown hooks raise
            logger.exception(
                "failed to mark memo run %s interrupted at shutdown", report_id
            )


def start_analysis(report_id: str) -> threading.Thread:
    """Kick off the analysis worker in a daemon thread."""
    t = threading.Thread(
        target=_run_safe,
        args=(report_id,),
        name=f"memo-analysis-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def start_resume(report_id: str) -> threading.Thread:
    """Resume a failed memo worker in a daemon thread."""
    t = threading.Thread(
        target=_resume_safe,
        args=(report_id,),
        name=f"memo-resume-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def start_investigation(report_id: str) -> threading.Thread:
    """Memo Studio deep investigation (Phases 1-2 + spine) in a daemon
    thread; parks the report at ``awaiting_studio``."""
    t = threading.Thread(
        target=_investigate_safe,
        args=(report_id,),
        name=f"memo-investigate-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def start_generate_from_studio(report_id: str) -> threading.Thread:
    """Memo Studio generation (Phases 3-4 from the composed spine) in a
    daemon thread."""
    t = threading.Thread(
        target=_generate_safe,
        args=(report_id,),
        name=f"memo-generate-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def _write_crash_log(run_dir: Path | None, *, phase: str, detail: str) -> str | None:
    """Save the crash's traceback to ``<run>/logs/crash.txt`` (appended, so a
    resume that crashes again keeps the first one). The server log rotates;
    this file stays with the run. Returns its repo-relative path."""
    if run_dir is None or not run_dir.exists():
        return None
    import traceback

    path = run_dir / "logs" / "crash.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"## {_now_iso()} — {phase}\n\n{detail}\n\n")
            handle.write(traceback.format_exc())
            handle.write("\n")
    except OSError:
        logger.warning("could not write %s", path, exc_info=True)
        return None
    return memo_prep._rel(path)


def _record_worker_crash(
    report_id: str,
    exc: BaseException,
    *,
    phase: str,
    stage: str,
    label: str,
    sync_tracking: bool = True,
) -> None:
    """A worker died on an exception nothing below caught. Record WHY on the
    report — ``failure_detail = "ValueError: Invalid company id"``, never
    "see server log", which no partner can open — with the traceback in
    ``logs/crash.txt``, and end the stream with the same line."""
    detail = f"{type(exc).__name__}: {exc}"[:300]
    report = storage.get_report(report_id)
    run_dir = _resolve_run_dir(report or {})
    crash_path = _write_crash_log(run_dir, phase=phase, detail=detail)
    message = f"{label}: {detail}"
    if report:
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage=stage,
            error=message,
            failure_phase=phase,
            failure_detail=detail,
            **({"crash_log": crash_path} if crash_path else {}),
        )
        _note_provider_limit(detail)
        if sync_tracking:
            _sync_tracking_auto_run(report, success=False, error=message)
    if run_dir and run_dir.exists():
        stream = _RunStream(report_id, memo_prep.stream_path(run_dir), truncate=False)
        stream.emit(
            "error",
            error=message,
            phase=phase,
            **({"crash_log": crash_path} if crash_path else {}),
        )


def _note_provider_limit(message: str | None) -> None:
    """A provider usage limit seen by the pipeline is remembered process-wide
    (``provider_limits``), so the report pre-flight can say "Claude is
    limited until 15:00" before anyone spends on a doomed run."""
    text = str(message or "")
    if not text:
        return
    try:
        reason = claude_runner.provider_limit_reason(text)
    except Exception:  # noqa: BLE001
        return
    if not reason:
        return
    try:
        from . import provider_limits

        provider_limits.record_provider_limit(text, source="memo")
    except Exception:  # noqa: BLE001
        logger.warning("provider limit record failed", exc_info=True)


def _investigate_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _investigate(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("memo studio investigation crashed")
        _record_worker_crash(
            report_id,
            exc,
            phase="investigation",
            stage="Investigation crashed",
            label="Investigation worker crashed",
        )
    finally:
        _unregister_active_run(report_id)


def _generate_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _generate_from_studio(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("memo studio generation crashed")
        _record_worker_crash(
            report_id,
            exc,
            phase="studio_generate",
            stage="Studio generation crashed",
            label="Studio generation worker crashed",
            sync_tracking=False,
        )
    finally:
        _unregister_active_run(report_id)


def _run_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _run(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("memo analysis crashed")
        _record_worker_crash(
            report_id,
            exc,
            phase="analysis",
            stage="Analysis crashed",
            label="Analysis worker crashed",
        )
    finally:
        _unregister_active_run(report_id)


def _resume_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _resume(report_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("memo resume crashed")
        _record_worker_crash(
            report_id,
            exc,
            phase="resume",
            stage="Resume crashed",
            label="Resume worker crashed",
        )
    finally:
        _unregister_active_run(report_id)


def _english_quality_gate_needs_package_regen(
    report: dict,
    *,
    quality_lint_path: Path | None = None,
) -> bool:
    """True only when the English DOCX quality gate needs a package rewrite.

    ``complete_with_warnings`` often means Chinese parity alone failed. That
    must not archive and regenerate the English package — that path is what
    stranded users on "Regenerating memo package after quality gate failure".
    """
    if report.get("failure_phase") == "quality_gate":
        return True
    if report.get("resume_last_failure_phase") == "quality_gate":
        return True
    if report.get("resume_from_failure_phase") == "quality_gate":
        return True
    if str(report.get("status") or "") == "failed_quality_gate":
        return True
    if str(report.get("resume_last_status") or "") == "failed_quality_gate":
        return True

    lint = report.get("memo_quality_lint")
    if isinstance(lint, dict):
        if int(lint.get("p0_count") or 0) > 0:
            return True
        if str(lint.get("status") or "").lower() == "failed":
            return True

    for warning in report.get("quality_warnings") or []:
        text = str(warning).lower()
        if "chinese" in text or "parity" in text:
            continue
        if "quality gate" in text or "memo quality" in text:
            return True

    if quality_lint_path and quality_lint_path.exists():
        try:
            text = quality_lint_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if re.search(r"(?im)^-\s*status:\s*failed\b", text):
            return True
        if re.search(r"(?im)^-\s*p0_count:\s*[1-9]\d*\b", text):
            return True
        # Older lint stubs used in tests / early resumes.
        if re.search(r"(?im)^\s*p0\b", text) and "status: passed" not in text.lower():
            return True

    return False


def _resolve_run_dir(report: dict) -> Path | None:
    run_dir_rel = report.get("run_dir")
    if not run_dir_rel:
        return None
    return memo_prep.DATA_DIR.parent / run_dir_rel


def _is_failure_stub(path: Path) -> bool:
    """A pass that failed leaves a placeholder markdown ("## Status" /
    "Pass failed: …") instead of findings — nothing a resume can build on."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(4000)
    except OSError:
        return True
    return "Pass failed:" in head or bool(re.search(r"(?m)^##\s+Status\s*$", head))


def _analysis_artifact_paths(run_dir: Path) -> list[Path]:
    """The run's usable analysis artifacts (failure stubs excluded: a run
    made entirely of failed passes is not resumable analysis)."""
    analysis_dir = run_dir / "analysis"
    if not analysis_dir.is_dir():
        return []
    return sorted(
        p for p in analysis_dir.iterdir()
        if p.is_file() and p.suffix == ".md" and not _is_failure_stub(p)
    )


def _fast_pass_records(run_dir: Path) -> dict[str, dict]:
    """``analysis/fast/<pass>.json`` by pass id (whatever is on disk)."""
    fast_dir = run_dir / "analysis" / "fast"
    records: dict[str, dict] = {}
    if not fast_dir.is_dir():
        return records
    for path in fast_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            records[str(payload.get("pass_id") or path.stem)] = payload
    return records


# The passes the figure and pin checks lean on: a memo written without
# them says so explicitly.
_LOAD_BEARING_PASSES = ("numbers_integrity", "valuation_exit")


def _analysis_coverage(run_dir: Path) -> dict | None:
    """Which Phase-2 passes this run's memo was written from:
    ``{passes_total, passes_ok, ok, missing}`` — None for runs without the
    fast passes (legacy one-shot, approved Studio packet)."""
    records = _fast_pass_records(run_dir)
    if not records:
        return None
    expected = [spec.pass_id for spec in _FAST_MEMO_PASSES]
    ok = [
        pass_id
        for pass_id in expected
        if str((records.get(pass_id) or {}).get("status") or "") == "ok"
    ]
    missing = [pass_id for pass_id in expected if pass_id not in ok]
    return {
        "passes_total": len(expected),
        "passes_ok": len(ok),
        "ok": ok,
        "missing": missing,
    }


def _coverage_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    """A memo written from fewer than all analysis passes is delivered, and
    says so: the missing passes are named, and the load-bearing ones
    (numbers, valuation) called out."""
    coverage = _analysis_coverage(run_dir)
    if not coverage or not coverage["missing"]:
        return
    labels = {spec.pass_id: spec.label for spec in _FAST_MEMO_PASSES}
    names = [labels.get(pass_id, pass_id) for pass_id in coverage["missing"]]
    load_bearing = [p for p in coverage["missing"] if p in _LOAD_BEARING_PASSES]
    en = (
        f"Written from {coverage['passes_ok']} of {coverage['passes_total']} "
        f"analysis passes; missing: {', '.join(names)}."
    )
    zh = (
        f"本备忘录基于 {coverage['passes_total']} 项分析中的 {coverage['passes_ok']} 项撰写；"
        f"缺少：{'、'.join(coverage['missing'])}。"
    )
    if load_bearing:
        en += (
            " The figure and valuation checks lean on "
            + " and ".join(labels.get(p, p) for p in load_bearing)
            + ", so treat the numbers with extra care."
        )
        zh += "数字与估值核对依赖其中缺失的分析，请审慎对待相关数字。"
    warnings.add(
        en,
        zh,
        [
            _warning_item(
                gate="analysis_coverage",
                language="EN",
                summary_en=en,
                summary_zh=zh,
                severity="warning",
                code="missing_passes",
                detail_path=memo_prep._rel(run_dir / "analysis" / "fast"),
            )
        ],
    )




def _archive_stream(run_dir: Path, *, label: str) -> None:
    stream_path = memo_prep.stream_path(run_dir)
    if not stream_path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = stream_path.with_name(
        f"stream.before_{label}.{stamp}.jsonl"
    )
    try:
        stream_path.replace(archive_path)
    except OSError:
        logger.exception(
            "failed to archive memo stream before %s: %s", label, stream_path
        )


def _archive_stream_for_resume(run_dir: Path) -> None:
    _archive_stream(run_dir, label="resume")


# ---- Agent boundary audit ------------------------------------------------
# The agents' inputs are the run folder, the company's research folder, the
# settings file and the registry entry. Past runs read the quality gates'
# source (server/, tests/), other companies' and other runs' memo artifacts
# and the Document Library (data/uploads) — contaminated inputs, not gamed
# gates. The tool pin and filtered environment narrow what an agent CAN do;
# this reads what it DID, from the stream's tool-use previews, and says so.

_ENV_FILE_RE = re.compile(r"(?:^|[\s\"'/=])\.env(?![\w.])")
# Previews are JSON: a quoted path arrives as `...memo-run\"`, so the
# backslash ends a path too (ZaiNar 2026-09-23 flagged the run's own
# `cd "<run folder>" && ls` as another run's files).
_MEMO_RUN_PATH_RE = re.compile(r"data/memos/[^\s\"',)\\]+")
_MAX_BOUNDARY_HITS = 40


def _audit_agent_boundary(run_dir: Path) -> list[dict]:
    """Tool uses in this run's streams that reached outside its inputs:
    [{kind, tool, preview}] — kinds: server_source, tests, frontend_source,
    env_file, uploads, other_memo_run. Never raises."""
    repo = str(memo_prep.DATA_DIR.parent.resolve())
    own_run = memo_prep._rel(run_dir).rstrip("/") + "/"
    checks = (
        ("server_source", f"{repo}/server/"),
        ("tests", f"{repo}/tests/"),
        ("frontend_source", f"{repo}/frontend/"),
    )
    hits: list[dict] = []
    try:
        streams = sorted((run_dir / "logs").glob("stream*.jsonl"))
    except OSError:
        return hits
    for stream_file in streams:
        try:
            lines = stream_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"tool_use"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("action") != "tool_use":
                continue
            tool = str(event.get("tool") or "")
            if tool in ("WebSearch", "WebFetch", "StructuredOutput"):
                continue
            preview = str(event.get("preview") or "")
            kinds = [kind for kind, needle in checks if needle in preview]
            if _ENV_FILE_RE.search(preview):
                kinds.append("env_file")
            if "data/uploads/" in preview:
                kinds.append("uploads")
            for match in _MEMO_RUN_PATH_RE.finditer(preview):
                if not (match.group(0).rstrip("/") + "/").startswith(own_run):
                    kinds.append("other_memo_run")
                    break
            for kind in dict.fromkeys(kinds):
                hits.append({"kind": kind, "tool": tool, "preview": preview[:300]})
                if len(hits) >= _MAX_BOUNDARY_HITS:
                    return hits
    return hits


_BOUNDARY_LABELS = {
    "server_source": ("server source code", "服务器源代码"),
    "tests": ("test code", "测试代码"),
    "frontend_source": ("frontend source code", "前端源代码"),
    "env_file": ("the .env secrets file", ".env 密钥文件"),
    "uploads": ("the Document Library (data/uploads)", "文档库（data/uploads）"),
    "other_memo_run": ("another memo run's files", "其他备忘录运行的文件"),
}


def _boundary_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    """Add a warning when the run's agents read outside their inputs, with
    the list in ``logs/boundary_audit.md``. Best-effort."""
    try:
        hits = _audit_agent_boundary(run_dir)
    except Exception:  # noqa: BLE001
        logger.warning("agent boundary audit failed", exc_info=True)
        return
    if not hits:
        return
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit["kind"]] = counts.get(hit["kind"], 0) + 1
    en_parts = [f"{_BOUNDARY_LABELS[k][0]} ×{n}" for k, n in counts.items()]
    zh_parts = [f"{_BOUNDARY_LABELS[k][1]} ×{n}" for k, n in counts.items()]
    audit_path = run_dir / "logs" / "boundary_audit.md"
    try:
        audit_path.write_text(
            "# Agent boundary audit\n\n"
            "Tool uses that reached outside the run's inputs (run folder, "
            "research folder, settings, registry entry).\n\n"
            + "\n".join(
                f"- {hit['kind']} — {hit['tool']}: `{hit['preview']}`" for hit in hits
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.warning("could not write %s", audit_path, exc_info=True)
    detail = memo_prep._rel(audit_path)
    warnings.add(
        "Agents read outside the run's inputs: " + ", ".join(en_parts) + f". See {detail}.",
        "代理读取了本次运行输入之外的文件：" + "、".join(zh_parts) + f"。详见 {detail}。",
        [
            _warning_item(
                gate="boundary",
                language="EN",
                summary_en=(
                    "Agents read outside the run's inputs: " + ", ".join(en_parts)
                ),
                summary_zh="代理读取了本次运行输入之外的文件：" + "、".join(zh_parts),
                severity="warning",
                code="agent_boundary",
                detail_path=detail,
            )
        ],
    )


NO_DILIGENCE_WARNING = (
    "No BSH diligence on file: every figure is public or registry",
    "没有 BSH 尽调资料：所有数字均来自公开信息或登记记录",
)


def _delivered_package(run_dir: Path) -> dict | None:
    """The package the delivered memo was rendered from: the bilingual one,
    else the accepted English one (an English-only delivery)."""
    for path in (_memo_package_path(run_dir), _english_package_path(run_dir)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _private_diligence_warning(
    report: dict, run_dir: Path, warnings: "_RunWarnings", package: dict | None = None
) -> None:
    """A private company's memo written without any of the firm's own
    material (the run's private inventory is empty) says so: every figure
    in it is public or from the registry. Keyed on the stamped inventory,
    never on a file count (a public-source memo is not a defect)."""
    inventory = _private_items_on_file(package)
    if inventory is None and not isinstance(package, dict):
        # The bilingual package first, then the accepted English one (the
        # stamp is made on the English envelope).
        for path in (_memo_package_path(run_dir), _english_package_path(run_dir)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            inventory = _private_items_on_file(payload)
            if inventory is not None:
                break
    if not isinstance(inventory, list) or inventory:
        return
    company = storage.get_company(str(report.get("company_id") or "")) or {}
    if not company or storage.infer_company_type(company) != "private":
        return
    en_text, zh_text = NO_DILIGENCE_WARNING
    warnings.add(
        en_text,
        zh_text,
        [
            _warning_item(
                gate="private_diligence",
                language="EN",
                summary_en=en_text,
                summary_zh=zh_text,
                severity="warning",
                code="no_private_material",
            )
        ],
    )


_SCENARIO_ZH = {"bear": "悲观", "base": "基准", "bull": "乐观"}
_RETURNS_WARNING_ZH = {
    "exit_value_mismatch": "{scenario}情景的退出估值与其退出收入乘以退出倍数的结果不符",
    "moic_mismatch": "{scenario}情景的 MOIC 与其退出估值、入场估值和稀释假设不符",
    "moic_above_undiluted": "{scenario}情景的 MOIC 高于未计稀释的退出估值与入场估值之比",
    "irr_mismatch": "{scenario}情景的 IRR 与其 MOIC 和持有期不符",
    "label_sign_mismatch": "{scenario}情景的文字表述（如“低于入场价”）与其数字方向不符",
    "probabilities_do_not_sum": "三种情景的概率合计不等于 100",
    "commit_above_walk_away": "建议中的出资价格高于按本基金回报门槛推算的最高可接受估值",
    "scenario_order": "{scenario}情景的退出估值或 MOIC 高于其上一档情景",
    "dilution_not_pinned": "基准情景的 MOIC 未计任何稀释，而持有期在三年以上",
    "position_above_policy": "拟出资额占基金的比例超过基金政策中的单笔上限",
}


def _returns_warning(run_dir: Path, warnings: "_RunWarnings") -> None:
    """The v2 pins' returns arithmetic, recomputed in Python from the
    accepted spine (memo_pin_check.spine_warnings_v2): every disagreement
    is a warning on the report — the memo ships as written."""
    shared_facts = _memo_shared_facts_from_disk(run_dir)
    if not shared_facts:
        return
    structure = _structure_for_run(run_dir)
    try:
        inputs = claude_runner.memo_returns_inputs(run_dir.parent.name)
        found = memo_pin_check.spine_warnings_v2(
            shared_facts,
            structure,
            policy=claude_runner._memo_stage_policy(structure.declared_stage),
            as_of_year=claude_runner._memo_run_year(run_dir),
            deal_terms=inputs["deal_terms"],
            fund_size_usd=inputs["fund_size_usd"],
        )
    except Exception:  # noqa: BLE001
        logger.warning("returns recomputation failed", exc_info=True)
        return
    if not found:
        return
    count = len(found)
    items = []
    for warning in found[:_MAX_WARNING_ITEMS_PER_GATE]:
        code = str(warning.get("code") or "returns")
        scenario = str(warning.get("scenario") or "")
        template = _RETURNS_WARNING_ZH.get(code, "回报测算与锁定数字不一致")
        items.append(
            _warning_item(
                gate="returns",
                language="EN",
                severity="warning",
                code=code,
                summary_en=str(warning.get("detail") or code)[:300],
                summary_zh=template.format(scenario=_SCENARIO_ZH.get(scenario, "")),
            )
        )
    noun = "figure disagrees" if count == 1 else "figures disagree"
    warnings.add(
        f"Returns arithmetic: {count} pinned {noun} with the recomputation",
        f"回报测算：{count} 处锁定数字与重新计算的结果不一致",
        items,
    )


SIGNPOSTS_FILENAME = "signposts.json"


def _record_signposts(
    run_dir: Path, warnings: "_RunWarnings", package: dict | None = None
) -> None:
    """Signposts, phase 1 (server/memo_signposts.py): what the delivered
    memo says it will watch, written to ``logs/signposts.json`` for the
    tracking store to pick up, and a warning for each signpost the writer
    listed that the memo never states. Never raises."""
    package = package if isinstance(package, dict) else _delivered_package(run_dir)
    if not isinstance(package, dict):
        return
    try:
        from . import memo_signposts

        signposts = memo_signposts.extract(package)
        findings = memo_signposts.echo_findings(package)
    except Exception:  # noqa: BLE001
        logger.warning("signpost extraction failed", exc_info=True)
        return
    try:
        _write_json(
            run_dir / "logs" / SIGNPOSTS_FILENAME,
            {"extracted_at": _now_iso(), "signposts": signposts},
        )
    except OSError:
        logger.warning("could not write the run's signposts", exc_info=True)
    if not findings:
        return
    count = len(findings)
    noun = "signpost is" if count == 1 else "signposts are"
    warnings.add(
        f"Signposts: {count} listed {noun} not stated in the memo",
        f"跟踪信号：{count} 条列出的信号未在备忘录正文中出现",
        [
            _warning_item(
                gate="signposts",
                language="EN",
                severity="warning",
                code="signpost_not_stated",
                summary_en=finding["detail"][:300],
                summary_zh=f"跟踪信号 {finding['id']} 未在备忘录正文中出现",
            )
            for finding in findings[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _risk_card_warning(
    run_dir: Path, warnings: "_RunWarnings", package: dict | None = None
) -> None:
    """Risk-card wording the surgical repair did not clear (an economic
    consequence missing from "Why it matters", a "What we watch" that is a
    command, a card without its declared rows) ships as a warning: the
    renderer draws the cards, and the wording never costs a regeneration."""
    package = package if isinstance(package, dict) else _delivered_package(run_dir)
    if not isinstance(package, dict):
        return
    try:
        findings = memo_docx_renderer.risk_card_quality_findings(package)
    except Exception:  # noqa: BLE001
        logger.warning("risk-card wording check failed", exc_info=True)
        return
    if not findings:
        return
    count = len(findings)
    plural = "finding" if count == 1 else "findings"
    warnings.add(
        f"Risk cards: {count} wording {plural} left to fix",
        f"风险卡片：尚有 {count} 处措辞需要修改",
        [
            _warning_item(
                gate="risk_cards",
                language="EN",
                section=finding.split(" ", 1)[0] or None,
                severity="warning",
                code="risk_card_wording",
                summary_en=finding[:300],
                summary_zh="风险卡片措辞：" + finding[:200],
            )
            for finding in findings[:_MAX_WARNING_ITEMS_PER_GATE]
        ],
    )


def _retire_stale_chinese_docx(memo_paths_abs: dict[str, Path]) -> Path | None:
    """An English-only delivery must not serve a Chinese memo an earlier
    attempt wrote for different English: move it aside (kept, not deleted)
    so the viewer offers only the English."""
    zh_path = memo_paths_abs.get("zh")
    if not zh_path or not zh_path.exists():
        return None
    stale = zh_path.with_name(f"{zh_path.stem}.superseded{zh_path.suffix}")
    try:
        zh_path.replace(stale)
    except OSError:
        logger.warning("could not move aside the stale Chinese memo %s", zh_path, exc_info=True)
        return None
    return stale


def _render_english_only_outputs(
    *,
    report_id: str,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
    keep_existing: bool = False,
) -> bool:
    """Render the English memo alone from the accepted English package (the
    Chinese stage failed or was cancelled). Same contract failure handling
    as the pair render, checked for the English files only.

    ``keep_existing`` (a failed "Retry Chinese") leaves an English DOCX that
    is already on disk exactly as delivered and only re-checks the contract."""
    package_path = _english_package_path(run_dir)
    en_path = memo_paths_abs.get("en")
    contract_args = dict(
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        locales=("en",),
        package_path=package_path,
    )
    if not package_path.exists() or not en_path:
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message=(
                "The Chinese stage failed and there is no accepted English "
                f"package to deliver ({memo_prep._rel(package_path)})."
            ),
            contract=_renderer_contract_diagnostics(**contract_args),
            recovered=recovered,
        )
        return False
    _update_report(report_id, stage="Rendering the English memo DOCX", progress=85)
    stream.emit(
        "stage",
        stage="rendering_docx",
        message="Rendering the English memo DOCX (the Chinese version failed)",
        memo_package=memo_prep._rel(package_path),
        english_only=True,
        recovered=recovered,
    )
    with _timed_phase(
        stream,
        phase="memo_docx_render",
        recovered=recovered,
        memo_package=memo_prep._rel(package_path),
        output_en=memo_prep._rel(en_path),
        english_only=True,
    ) as timing:
        try:
            if not (keep_existing and en_path.exists()):
                payload = json.loads(package_path.read_text(encoding="utf-8"))
                _render_single_locale(
                    _english_render_payload(payload), "en", en_path, run_dir=run_dir
                )
            else:
                timing["kept_existing"] = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("English-only render failed for report %s", report_id)
            message = f"Memo package render failed: {type(exc).__name__}: {exc}"
            timing["status"] = "failed"
            timing["error"] = message
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=_renderer_contract_diagnostics(**contract_args),
                recovered=recovered,
            )
            return False
        contract = _renderer_contract_diagnostics(**contract_args)
        errors = list(contract.get("errors") or [])
        timing["renderer_contract_error_count"] = len(errors)
        timing["expected_files"] = contract.get("expected_files")
        if errors:
            message = "Renderer contract failed: " + "; ".join(errors)
            timing["status"] = "failed"
            timing["error"] = message
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=contract,
                recovered=recovered,
            )
            return False
    stale = _retire_stale_chinese_docx(memo_paths_abs)
    if stale is not None:
        stream.emit(
            "stage",
            stage="memo_stale_chinese_retired",
            message=(
                "Moved aside a Chinese memo from an earlier attempt; it does "
                "not match this English"
            ),
            path=memo_prep._rel(stale),
        )
    return True


def _render_chinese_only_outputs(
    *,
    report_id: str,
    run_dir: Path,
    memo_paths_abs: dict[str, Path],
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
) -> bool:
    """"Retry Chinese": render the Chinese memo alone from the new bilingual
    package; the English DOCX (and its validation log) stay exactly as they
    were delivered. The contract is then checked for both languages."""
    package_path = _memo_package_path(run_dir)
    zh_path = memo_paths_abs.get("zh")
    contract_args = dict(run_dir=run_dir, memo_paths_abs=memo_paths_abs)
    if not package_path.exists() or not zh_path:
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message=(
                "Retry Chinese finished without a bilingual package or a "
                "Chinese memo path."
            ),
            contract=_renderer_contract_diagnostics(**contract_args),
            recovered=recovered,
        )
        return False
    _update_report(report_id, stage="Rendering the Chinese memo DOCX", progress=85)
    stream.emit(
        "stage",
        stage="rendering_docx",
        message=(
            "Rendering the Chinese memo DOCX (the English is kept as "
            "delivered)"
        ),
        memo_package=memo_prep._rel(package_path),
        chinese_only=True,
        recovered=recovered,
    )
    # The same deterministic rewrites the delivered English went through.
    voice_rewrite_count = _clean_memo_package_voice(package_path, stream)
    with _timed_phase(
        stream,
        phase="memo_docx_render",
        recovered=recovered,
        memo_package=memo_prep._rel(package_path),
        voice_rewrite_count=voice_rewrite_count,
        output_zh=memo_prep._rel(zh_path),
        chinese_only=True,
    ) as timing:
        try:
            _render_single_locale(
                json.loads(package_path.read_text(encoding="utf-8")),
                "zh",
                zh_path,
                run_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chinese-only render failed for report %s", report_id)
            message = f"Memo package render failed: {type(exc).__name__}: {exc}"
            timing["status"] = "failed"
            timing["error"] = message
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=_renderer_contract_diagnostics(**contract_args),
                recovered=recovered,
            )
            return False
        contract = _renderer_contract_diagnostics(**contract_args)
        errors = list(contract.get("errors") or [])
        timing["renderer_contract_error_count"] = len(errors)
        timing["expected_files"] = contract.get("expected_files")
        if errors:
            message = "Renderer contract failed: " + "; ".join(errors)
            timing["status"] = "failed"
            timing["error"] = message
            _fail_renderer_contract(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
                contract=contract,
                recovered=recovered,
            )
            return False
    return True


def _run_completion_hooks(report_id: str, *, force: bool = False) -> None:
    """What hangs off a finished memo: the reader block (the list row's
    verdict, headline and age) and the lazily made PDF. Best-effort — a
    hook fault never changes the delivered run. ``force`` runs them for a
    halted run whose halting call delivered the memo (a cancel after the
    English was ready)."""
    if _run_halted(report_id) and not force:
        return
    try:
        from . import report_reader

        report_reader.persist_reader_block(report_id)
    except Exception:  # noqa: BLE001
        logger.warning("reader block failed for %s", report_id, exc_info=True)
    try:
        from . import memo_pdf

        memo_pdf.schedule_pdf(report_id)
    except Exception:  # noqa: BLE001
        logger.warning("PDF scheduling failed for %s", report_id, exc_info=True)


def _internal_memo_wanted(report: dict) -> bool:
    """The IC decision memo is written when prep planned its files (the
    run's audience, or the override at prep time) and the override does not
    switch it off now."""
    return bool(_internal_memo_paths_abs(report)) and memo_prep._internal_diligence_memo_enabled(
        report.get("audience")
    )


def _finalize_memo_from_package(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
    background_started_at: str | None = None,
    background_started_monotonic: float | None = None,
    background_fields: dict[str, Any] | None = None,
) -> bool:
    """Render, gate and deliver the memo from the accepted package.

    ``result["english_only"]`` (the Chinese stage failed; its error in
    ``result["chinese_error"]``) delivers the English memo alone from
    ``logs/memo_package.en.json``: the English quality lint and fact check
    still run, the Chinese parity gate and the Chinese PDF are skipped, and
    the run ends ``complete_with_warnings`` with ``failure_phase =
    "chinese_package"`` and the bilingual warning, so Resume offers
    "Retry Chinese"."""
    if _run_halted(report_id):
        # A cancel or shutdown already wrote this run's terminal state.
        return False
    english_only = bool(result.get("english_only"))
    chinese_error = str(result.get("chinese_error") or "").strip() if english_only else ""
    locales: tuple[str, ...] = ("en",) if english_only else ("en", "zh")
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_paths_abs = _memo_paths_abs(report)
    memo_paths_rel = {
        f["language"]: f["path"]
        for f in report.get("memo_files") or []
        if f.get("language") and f.get("path")
    }
    internal_paths_abs = _internal_memo_paths_abs(report)
    analysis_session_path = _analysis_session_path_for_report(company_slug, report)
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None

    stream.emit(
        "thread_started",
        thread=claude_runner.MEMO_PHASE5_THREAD,
        title=claude_runner.MEMO_PHASE5_THREAD,
    )
    if _block_generated_renderer_scripts(
        report_id=report_id,
        run_dir=run_dir,
        stream=stream,
        result=result,
        recovered=recovered,
    ):
        return False
    if english_only:
        rendered = _render_english_only_outputs(
            report_id=report_id,
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=recovered,
            keep_existing=bool(result.get("keep_english_docx")),
        )
    elif result.get("chinese_only"):
        rendered = _render_chinese_only_outputs(
            report_id=report_id,
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=recovered,
        )
    else:
        rendered = _render_memo_outputs(
            report_id=report_id,
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=recovered,
        )
    if not rendered:
        return False
    _update_report(
        report_id,
        renderer_contract=_renderer_contract_diagnostics(
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            locales=locales,
            package_path=_english_package_path(run_dir) if english_only else None,
        ),
    )

    missing = []
    for locale, label in (("en", "English"), ("zh", "Chinese")):
        if locale not in locales:
            continue
        path = memo_paths_abs.get(locale)
        if not (path and path.exists()):
            missing.append(f"{label} .docx: {memo_paths_rel.get(locale)}")

    if missing:
        msg = (
            "Renderer finished but the expected output files are missing: "
            + "; ".join(missing)
            + ". Check the renderer logs and run folder's stream.jsonl."
        )
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Renderer completed but outputs missing",
            error=msg,
            failure_phase="post_run_check",
            failure_detail=msg,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit(
            "thread_failed",
            thread=claude_runner.MEMO_PHASE5_THREAD,
            error=msg,
        )
        payload = {"error": msg, "phase": "post_run_check"}
        if recovered:
            payload["recovered"] = True
        stream.emit("error", **payload)
        _sync_tracking_auto_run(report, success=False, error=msg)
        return False

    _maybe_render_memo_pdf_previews(
        report_id=report_id,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        progress=86,
        recovered=recovered,
    )

    warnings = _RunWarnings()
    if english_only:
        en_text, zh_text = CHINESE_FAILED_WARNING
        warnings.add(
            en_text,
            zh_text,
            [
                _warning_item(
                    gate=CHINESE_PACKAGE_PHASE,
                    language="ZH",
                    summary_en=(
                        f"{en_text}. Resume retries the Chinese only"
                        + (f" ({chinese_error[:200]})" if chinese_error else "")
                    ),
                    summary_zh=f"{zh_text}。“重试中文版”只重新生成中文。",
                    severity="warning",
                    code="chinese_failed",
                    detail_path=memo_prep._rel(_zh_partial_package_path(run_dir)),
                )
            ],
        )
        stream.emit(
            "stage",
            stage="chinese_version_failed",
            message=f"{en_text} / {zh_text}",
            error=chinese_error[:500] or None,
            recovered=recovered,
        )
        _update_report(report_id, memo_chinese_parity=None)
    else:
        parity_payload, parity_warning = _run_chinese_parity_gate(
            report_id=report_id,
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=recovered,
        )
        if parity_warning:
            p0 = int(parity_payload.get("p0_count") or 0)
            parity_rel = memo_prep._rel(run_dir / "logs" / "memo_chinese_parity.md")
            warnings.add(
                parity_warning,
                f"中文对照检查发现 {p0} 个 P0 问题。详见 {parity_rel}。",
                _finding_items(
                    [
                        f
                        for f in parity_payload.get("findings") or []
                        if isinstance(f, dict) and f.get("severity") == "P0"
                    ],
                    gate="chinese_parity",
                    language="ZH",
                    detail_path=parity_rel,
                ),
            )

    _update_report(
        report_id,
        stage="Running memo quality gate",
        progress=90,
    )
    stream.emit(
        "stage",
        stage="quality_gate",
        message="Running memo quality gate",
        recovered=recovered,
    )
    lint_result, lint_path = _lint_memo_quality_gate(
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        recovered=recovered,
    )
    if lint_result.has_blocking_findings:
        # Deliver the memo with its issues listed instead of blocking: the
        # generation loops already retried with these findings fed back,
        # and a complete-with-warnings report keeps Resume available to
        # regenerate toward a clean memo.
        lint_payload = lint_result.to_dict()
        lint_rel = memo_prep._rel(lint_path)
        msg = (
            "Memo quality gate found "
            f"{lint_payload['p0_count']} P0 finding"
            f"{'' if lint_payload['p0_count'] == 1 else 's'}. "
            f"See {lint_rel}."
        )
        warnings.add(
            msg,
            f"英文质量检查发现 {lint_payload['p0_count']} 个 P0 问题。详见 {lint_rel}。",
            _finding_items(
                lint_result.p0_findings,
                gate="quality",
                language="EN",
                detail_path=lint_rel,
            ),
        )
        payload = {
            "stage": "quality_gate_warning",
            "message": msg,
            "phase": "quality_gate",
            "lint_report": lint_rel,
            "findings": lint_payload["findings"][:10],
        }
        if recovered:
            payload["recovered"] = True
        stream.emit("stage", **payload)
    _update_report(
        report_id,
        memo_quality_lint=lint_result.to_dict(),
        memo_fact_check=_fact_check_payload(run_dir),
    )
    stream.emit("thread_finished", thread=claude_runner.MEMO_PHASE5_THREAD)

    stream.emit(
        "thread_started",
        thread=claude_runner.MEMO_PHASE6_THREAD,
        title=claude_runner.MEMO_PHASE6_THREAD,
    )
    internal_generated = False
    combined_result = dict(result)
    ic_docx = internal_paths_abs.get("docx")
    keep_ic_memo = bool(
        (result.get("chinese_only") or result.get("keep_english_docx"))
        and ic_docx
        and ic_docx.exists()
    )
    if keep_ic_memo:
        # "Retry Chinese" rewrites only the Chinese LP memo; the IC memo was
        # written with the English and stays as it is.
        internal_generated = True
        stream.emit(
            "stage",
            stage="internal_memo_kept",
            message="Keeping the IC decision memo written with the English",
        )
    elif (
        internal_paths_abs
        and _internal_memo_wanted(report)
        and _cost_guard_stop(
            report_id=report_id,
            run_dir=run_dir,
            cost_usd=_as_float(result.get("cost_usd")),
            phase="IC decision memo",
            stream=stream,
        )
    ):
        # Past the ceiling: the LP memo is delivered; the IC memo waits
        # for a resume once the ceiling is raised.
        warnings.add(
            "IC decision memo not written: cost ceiling reached",
            "投委会决策备忘录未生成：已达到费用上限",
            [
                _warning_item(
                    gate="ic_memo",
                    language="EN",
                    summary_en="The internal IC decision memo was skipped because the run reached its cost ceiling; the LP memo is unaffected.",
                    summary_zh="因运行达到费用上限，内部投委会决策备忘录已跳过；LP 备忘录不受影响。",
                    severity="warning",
                    code="ic_memo_skipped_cost",
                )
            ],
        )
        stream.emit(
            "stage",
            stage="internal_memo_skipped",
            message="Skipping the IC decision memo: cost ceiling reached",
            recovered=recovered,
        )
    elif internal_paths_abs and _internal_memo_wanted(report):
        internal_result = _run_internal_diligence_memo(
            report_id=report_id,
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            memo_paths_abs=memo_paths_abs,
            internal_paths_abs=internal_paths_abs,
            stream=stream,
            result=result,
            analysis_session_path=analysis_session_path,
            lessons_path=lessons_path,
            scope_check=report.get("scope_check"),
            warnings=list(report.get("warnings") or []),
            english_only=english_only,
        )
        if internal_result is not None and internal_result.get("ok"):
            combined_result = _combined_result(result, internal_result)
            internal_generated = True
            if _memo_pdf_previews_enabled():
                _update_report(
                    report_id,
                    stage="Rendering PDF previews",
                    progress=96,
                )
                stream.emit(
                    "stage",
                    stage="rendering_pdf",
                    message="Rendering PDF previews",
                    recovered=recovered,
                )
                _render_internal_pdf_previews(report_id=report_id, stream=stream)
        else:
            # The IC memo is a companion document: its failure never costs
            # the reader the LP memo, which is already rendered and gated.
            error = str((internal_result or {}).get("error") or "IC memo failed")
            combined_result = _combined_result(result, internal_result)
            boundary = (
                str((internal_result or {}).get("error_code") or "") == "boundary_violation"
            )
            boundary_hit = str((internal_result or {}).get("boundary_hit") or "")[:200]
            warnings.add(
                "IC decision memo was not written: " + error[:300],
                "投委会决策备忘录未能生成：" + error[:300],
                [
                    _warning_item(
                        gate="ic_memo",
                        language="EN",
                        summary_en=(
                            "The IC decision memo agent read outside its sandbox "
                            f"({boundary_hit}) and was stopped; the LP memo is unaffected."
                            if boundary
                            else "The internal IC decision memo was not written; the LP memo is unaffected."
                        ),
                        summary_zh=(
                            "投委会决策备忘录代理越出沙箱读取文件，已被终止；LP 备忘录不受影响。"
                            if boundary
                            else "内部投委会决策备忘录未能生成；LP 备忘录不受影响。"
                        ),
                        severity="warning",
                        code="ic_memo_boundary" if boundary else "ic_memo_failed",
                    )
                ],
            )
    else:
        stream.emit(
            "stage",
            stage="internal_memo_skipped",
            message=(
                "Skipping internal diligence memo; set "
                "BSH_MEMO_GENERATE_INTERNAL=1 to enable it."
            ),
            recovered=recovered,
        )
        _emit_phase_timing(
            stream,
            phase="memo_internal_diligence",
            status="skipped",
            started_at=_now_iso(),
            started_monotonic=time.monotonic(),
            recovered=recovered,
            enabled=False,
            reason="BSH_MEMO_GENERATE_INTERNAL not enabled or no internal memo paths",
        )
    stream.emit("thread_finished", thread=claude_runner.MEMO_PHASE6_THREAD)
    _coverage_warning(run_dir, warnings)
    _private_diligence_warning(report, run_dir, warnings)
    _boundary_warning(run_dir, warnings)
    _risk_card_warning(run_dir, warnings)
    _returns_warning(run_dir, warnings)
    _record_signposts(run_dir, warnings)
    # Report-only gates: none of these can fail the run.
    delivered_package = _delivered_package(run_dir)
    for gate in (
        lambda: _length_warning(run_dir, warnings, delivered_package),
        lambda: _cost_warning(run_dir, warnings),
        lambda: _red_team_warning(run_dir, warnings),
        lambda: _pins_warning(run_dir, warnings),
        lambda: _fact_check_warning(run_dir, warnings),
        lambda: _ic_comparison_warning(internal_paths_abs.get("md"), warnings),
        lambda: _claims_warning(run_dir, warnings, company_slug),
        lambda: _consistency_warning(run_dir, warnings, delivered_package),
    ):
        try:
            gate()
        except Exception:  # noqa: BLE001
            logger.warning("report-only gate failed", exc_info=True)
    quality_metrics = _quality_metrics(
        run_dir, delivered_package, storage.get_report(report_id) or report
    )

    final_status = "complete_with_warnings" if warnings else "complete"
    if english_only:
        final_stage = "Memo ready — English only (Chinese failed)"
    else:
        final_stage = (
            "Memo ready (quality warnings)" if warnings else "Memo ready"
        )
    _update_report(
        report_id,
        status=final_status,
        stage=final_stage,
        progress=100,
        error=None,
        failure_phase=CHINESE_PACKAGE_PHASE if english_only else None,
        failure_detail=(chinese_error[:500] or CHINESE_FAILED_WARNING[0]) if english_only else None,
        resume_from_status=None,
        resume_from_failure_phase=None,
        resume_from_failure_detail=None,
        artifacts_available=True,
        english_only=True if english_only else None,
        claude_cost_usd=combined_result.get("cost_usd"),
        claude_duration_ms=combined_result.get("duration_ms"),
        report_ready_at=_now_iso(),
        # What the delivered package says generated it (stamped where it was
        # written; a package from before the stamp says nothing).
        generated_with=_package_generated_with(
            _english_package_path(run_dir) if english_only else _memo_package_path(run_dir)
        ),
        **({"quality_metrics": quality_metrics} if quality_metrics is not None else {}),
        **warnings.record_fields(),
    )
    company = storage.get_company(str(report.get("company_id") or "")) or {}
    name = company.get("name") or report.get("company_id") or "Memo"
    _notify_memo(report_id, "Memo ready", f"{name} — {final_stage}")
    _run_completion_hooks(report_id)
    # ---- Artifacts tail: the report is complete and viewable above; a
    # parked artifacts agent (report-ready detach) is collected here, so
    # the rail shows "Done — finalizing artifacts" instead of holding the
    # whole run hostage to the slowest private artifact.
    pending_artifacts = _pop_pending_artifacts(run_dir)
    if pending_artifacts is not None:
        tail_started_at = _now_iso()
        tail_started = time.monotonic()
        stream.emit(
            "stage",
            stage="memo_report_ready",
            message=(
                "Report is ready to view — finalizing private analysis "
                "artifacts in the background"
            ),
            report_ready=True,
        )
        join_result, join_error = pending_artifacts.join(timeout_sec=900.0)
        pending_artifacts.shutdown()
        tail_artifacts = (
            (join_result or {}).get("analysis_artifacts")
            if not join_error and isinstance(join_result, dict)
            else None
        )
        if not isinstance(tail_artifacts, dict):
            stream.emit(
                "stage",
                stage="memo_fast_english_artifacts_degraded",
                message=(
                    "Detached analysis-artifacts agent failed; writing "
                    "stub artifacts "
                    f"({str(join_error or 'no artifacts returned')[:300]})"
                ),
            )
            tail_artifacts = {}
        _write_fast_synthesis_artifacts(run_dir, tail_artifacts)
        tail_cost = _as_float((join_result or {}).get("claude_cost_usd"))
        if tail_cost:
            combined_result["cost_usd"] = round(
                _as_float(combined_result.get("cost_usd")) + tail_cost, 6
            )
        _emit_phase_timing(
            stream,
            phase="memo_artifacts_tail",
            status="failed" if join_error else "finished",
            started_at=tail_started_at,
            started_monotonic=tail_started,
            cost_usd=tail_cost or None,
            error=str(join_error)[:500] if join_error else None,
        )
    _update_report(
        report_id,
        run_finished_at=_now_iso(),
        claude_cost_usd=combined_result.get("cost_usd"),
    )
    done_payload = {
        "report_id": report_id,
        "memo_paths": {
            k: str(v) for k, v in memo_paths_abs.items() if k in locales
        },
        "cost_usd": combined_result.get("cost_usd"),
        "duration_ms": combined_result.get("duration_ms"),
    }
    if warnings:
        done_payload["quality_warnings"] = list(warnings.en)
    if english_only:
        done_payload["english_only"] = True
        done_payload["failure_phase"] = CHINESE_PACKAGE_PHASE
    if internal_generated:
        done_payload["internal_memo_paths"] = {
            k: str(v) for k, v in internal_paths_abs.items()
        }
    if recovered:
        done_payload["recovered"] = True
    if background_started_at and background_started_monotonic is not None:
        _emit_phase_timing(
            stream,
            phase="memo_background_run",
            status="finished",
            started_at=background_started_at,
            started_monotonic=background_started_monotonic,
            **(background_fields or {}),
            cost_usd=combined_result.get("cost_usd"),
            claude_duration_ms=combined_result.get("duration_ms"),
            worker_duration_ms=combined_result.get("worker_duration_ms"),
            internal_generated=internal_generated,
        )
    stream.emit("done", **done_payload)
    _sync_tracking_auto_run(report, success=True)
    return True


def _chinese_retry_requested(report: dict, run_dir: Path) -> bool:
    """Resume of an English-only delivery = "Retry Chinese": the Chinese
    stage failed (or was cancelled) after the English was accepted, and the
    accepted English package is on disk. The resume endpoint moves the
    failure into ``resume_last_failure_phase`` before the worker starts."""
    if not _english_package_path(run_dir).exists():
        return False
    if _paused_after_english(report) and not _memo_package_path(run_dir).exists():
        # A run paused after its English for review continues with the
        # Chinese through the same mechanics.
        return True
    phase = report.get("resume_last_failure_phase") or report.get("failure_phase")
    return phase == CHINESE_PACKAGE_PHASE


def _paused_after_english(report: dict) -> bool:
    return PAUSED_AFTER_ENGLISH_STATUS in (
        report.get("status"),
        report.get("resume_from_status"),
    )


def _retry_chinese(report_id: str, report: dict, run_dir: Path) -> None:
    """"Retry Chinese": translate only what is still blank, starting from
    ``logs/memo_package.zh_partial.json`` (the Chinese that did land), then
    the usual gap-fill repair and finalize. The accepted English package
    and the delivered English DOCX are never rewritten; works on every
    structure (v1 and v2) and for Memo Studio runs. A run paused after its
    English (``pause_after_english``) continues the same way."""
    _archive_stream_for_resume(run_dir)
    stream = _RunStream(report_id, memo_prep.stream_path(run_dir), truncate=True)
    company_name = str(report.get("company_name") or report.get("company_id"))
    continuing = _paused_after_english(report)
    stream.emit(
        "job_init",
        kind="memo",
        title=(
            f"Continue to Chinese — {company_name}"
            if continuing
            else f"Retry Chinese — {company_name}"
        ),
        subtitle="Chinese version only; the English is kept as delivered",
        report_id=report_id,
        company_id=str(report.get("company_id")),
        run_id=str(report.get("run_id") or ""),
        resumed=True,
        retry_chinese=True,
        **({"continue_after_pause": True} if continuing else {}),
    )
    _update_report(
        report_id,
        status="analyzing",
        stage=(
            "Writing the Chinese memo / 生成中文版"
            if continuing
            else "Retrying the Chinese memo / 重试中文版"
        ),
        progress=82,
        error=None,
        failure_phase=None,
        failure_detail=None,
        quality_warnings=None,
        quality_warnings_zh=None,
        quality_warning_items=None,
        english_only=None,
    )
    english_path = _english_package_path(run_dir)
    try:
        english = json.loads(english_path.read_text(encoding="utf-8"))
        if not isinstance(english, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        message = (
            "Retry Chinese cannot start: the accepted English package is "
            f"unreadable ({type(exc).__name__}: {exc})"
        )
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Retry Chinese failed",
            error=message,
            failure_phase="resume",
            failure_detail=message,
        )
        stream.emit("error", error=message, phase="resume")
        return
    _chinese_from_english(
        report_id,
        report,
        run_dir,
        stream,
        english,
        prior_cost=_as_float(report.get("claude_cost_usd")),
        deliver_english=False,
    )


def _chinese_from_english(
    report_id: str,
    report: dict,
    run_dir: Path,
    stream,
    english: dict,
    *,
    prior_cost: float = 0.0,
    deliver_english: bool,
    started_at: str | None = None,
    started_monotonic: float | None = None,
) -> None:
    """Phase 4 and finalize from an accepted English package on disk:
    adopt every Chinese string that already landed (chase merge, the saved
    partial), translate the rest, then deliver — both languages, or the
    English alone when the Chinese fails again.

    ``deliver_english`` renders the English DOCX first (a resume that
    reuses the English package); "Retry Chinese" passes False — the English
    DOCX it already delivered is never rewritten."""
    company_name = str(report.get("company_name") or report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    _register_run_structure(run_dir, memo_structure.for_package(english))
    if deliver_english:
        _deliver_english_first(
            report_id=report_id,
            run_dir=run_dir,
            english_package=english,
            memo_paths={k: str(v) for k, v in _memo_paths_abs(report).items()},
            stream=stream,
        )
    # Start from the English, then adopt every Chinese string that already
    # landed (the adopt is zh-only and keyed on identical English, so it
    # cannot alter a word of the English).
    retry_input = json.loads(json.dumps(english))
    for candidate in (
        run_dir / "logs" / "memo_package.en.chased.json",
        _zh_partial_package_path(run_dir),
    ):
        try:
            partial = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(partial, dict):
            claude_runner._adopt_zh_translations(retry_input, partial)
    retry_input_path = run_dir / "logs" / "memo_package.zh_retry_input.json"
    _write_json(retry_input_path, retry_input)

    if deliver_english:
        # A resume that reuses the English is still bound by the ceiling
        # before its next paid phase; an explicit "Retry Chinese" is the
        # analyst asking for exactly that one phase and runs.
        cost_stop = _cost_guard_stop(
            report_id=report_id,
            run_dir=run_dir,
            cost_usd=prior_cost,
            phase="Chinese version",
            stream=stream,
        )
        if cost_stop:
            _save_zh_partial(run_dir, retry_input, english)
            _finalize_memo_from_package(
                report_id=report_id,
                report=storage.get_report(report_id) or report,
                run_dir=run_dir,
                stream=stream,
                result={
                    "ok": True,
                    "resumed": True,
                    "retry_chinese": False,
                    "english_only": True,
                    "chinese_error": (
                        "Chinese version not started: the run's cost "
                        f"(US${cost_stop['cost_usd']:.2f}) reached its "
                        f"US${cost_stop['ceiling_usd']:.2f} ceiling"
                    ),
                    "cost_ceiling": cost_stop,
                    "cost_usd": round(prior_cost, 6),
                    "duration_ms": report.get("claude_duration_ms"),
                },
                recovered=True,
                background_started_at=started_at,
                background_started_monotonic=started_monotonic,
            )
            return

    phase4_started_at = _now_iso()
    phase4_started = time.monotonic()
    phase4_progress = _ThreadProgress(stream, claude_runner._MEMO_PHASE4_THREAD)
    phase4_progress.emit("thread_started", title=claude_runner._MEMO_PHASE4_THREAD)
    _emit_phase_timing(
        stream,
        phase="memo_fast_chinese_package",
        status="started",
        started_at=phase4_started_at,
        started_monotonic=phase4_started,
        retry_chinese=not deliver_english,
    )
    chinese = _run_chinese_package_stage(
        run_dir=run_dir,
        company_name=company_name,
        run_id=run_id,
        bilingual_input_path=retry_input_path,
        progress=phase4_progress,
        stream=stream,
    )
    result: dict[str, Any] = {
        "ok": True,
        "resumed": True,
        "retry_chinese": not deliver_english,
        "cost_usd": round(prior_cost + chinese.cost_usd, 6),
        "duration_ms": report.get("claude_duration_ms"),
    }
    if not deliver_english:
        # Whatever happens, the English DOCX stays as delivered.
        result["keep_english_docx"] = True
    if chinese.error:
        _save_zh_partial(run_dir, chinese.partial, retry_input)
        phase4_progress.emit("thread_failed", error=chinese.error)
        _emit_phase_timing(
            stream,
            phase="memo_fast_chinese_package",
            status="failed",
            started_at=phase4_started_at,
            started_monotonic=phase4_started,
            error=chinese.error,
            english_delivered=True,
        )
        result.update(english_only=True, chinese_error=chinese.error)
    else:
        phase4_progress.emit("thread_finished")
        # The Chinese was just written: its model joins the stamp.
        _stamp_generated_with_on_disk(_memo_package_path(run_dir), report, run_dir)
        _emit_phase_timing(
            stream,
            phase="memo_fast_chinese_package",
            status="finished",
            started_at=phase4_started_at,
            started_monotonic=phase4_started,
            memo_package=memo_prep._rel(_memo_package_path(run_dir)),
            cost_usd=round(chinese.cost_usd, 6),
            claude_duration_ms=chinese.duration_ms,
        )
        if not deliver_english:
            result.update(chinese_only=True)
    _finalize_memo_from_package(
        report_id=report_id,
        report=storage.get_report(report_id) or report,
        run_dir=run_dir,
        stream=stream,
        result=result,
        recovered=True,
        background_started_at=started_at,
        background_started_monotonic=started_monotonic,
    )


def _accepted_english_package(run_dir: Path) -> dict | None:
    """The accepted English package, when it still passes the English
    structural validation (the code may have changed since it was written);
    None otherwise. Risk-card wording is a warning the package was accepted
    with, not a reason to redo the English."""
    path = _english_package_path(run_dir)
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(package, dict):
        return None
    try:
        # A package accepted with a small word-cap overrun (delivered with
        # a length warning) still counts as accepted here.
        if _blocking_validation_errors(
            memo_docx_renderer.english_package_validation_errors(
                package, editorial_risk_checks=False
            ),
            package,
        ):
            return None
    except Exception:  # noqa: BLE001
        return None
    return package


def _resume_fail(report_id: str, stream, message: str, *, cost_usd: float | None = None) -> None:
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Memo resume failed",
        error=message,
        failure_phase="resume",
        failure_detail=message,
        **({"claude_cost_usd": cost_usd} if cost_usd is not None else {}),
    )
    _note_provider_limit(message)
    stream.emit("error", error=message, phase="resume")


def _resume_fast(
    report_id: str,
    report: dict,
    run_dir: Path,
    stream,
    *,
    reuse_english: bool = True,
) -> None:
    """Resume a fast-pipeline run from what is on disk instead of rewriting
    it: the analysis passes that succeeded are kept and only the failed or
    missing ones run again; an accepted English package that still
    validates is reused and the run continues at the Chinese step; else
    the English is synthesized again from the passes — with the run's OWN
    structure (never forced to v1) and engine — and finalized.

    A pass that fails again on a provider limit, a dead login or a cancel
    stops the resume and names the cause instead of spending more.
    ``reuse_english=False`` (a regeneration after an English quality
    failure) always writes the English again."""
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    prior_cost = _as_float(report.get("claude_cost_usd"))
    structure = _report_structure(report)
    _register_run_structure(run_dir, structure)
    stream.emit(
        "stage",
        stage="resume_fast",
        message=(
            "Resuming from the run's own analysis: keeping the passes that "
            "succeeded"
        ),
        structure_stage=structure.stage,
        structure_version=structure.version,
        recovered=True,
    )
    english = _accepted_english_package(run_dir) if reuse_english else None
    if english is not None:
        stream.emit(
            "stage",
            stage="resume_english_reuse",
            message="The accepted English package still validates; continuing at the Chinese step",
            memo_package=memo_prep._rel(_english_package_path(run_dir)),
            recovered=True,
        )
        _chinese_from_english(
            report_id,
            report,
            run_dir,
            stream,
            english,
            prior_cost=prior_cost,
            deliver_english=True,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
        return

    research_dir = _research_dir_for(company_slug)
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None
    warnings = list(report.get("warnings") or [])
    scope_check = report.get("scope_check")
    analysis_session_path = _analysis_session_path_for_report(
        company_slug, report, require_approved=True
    )
    cost_usd = 0.0
    if analysis_session_path is None:
        records = _fast_pass_records(run_dir)
        rerun = [
            spec
            for spec in _FAST_MEMO_PASSES
            if str((records.get(spec.pass_id) or {}).get("status") or "") != "ok"
        ]
        kept = len(_FAST_MEMO_PASSES) - len(rerun)
        stream.emit(
            "stage",
            stage="resume_passes",
            message=(
                f"Keeping {kept} analysis pass(es) from the run; "
                f"re-running {len(rerun)}"
            ),
            kept=kept,
            rerun=[spec.pass_id for spec in rerun],
            recovered=True,
        )
        if rerun:
            common_context = _pass_common_context(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                research_dir=research_dir,
                lessons_path=lessons_path,
                scope_check=scope_check,
                warnings=warnings,
                structure=structure,
            )
            with ThreadPoolExecutor(
                max_workers=min(_memo_fast_max_workers(), len(rerun))
            ) as pool:
                results = list(
                    pool.map(
                        lambda spec: _run_fast_memo_pass(
                            spec=spec,
                            run_dir=run_dir,
                            company_name=company_name,
                            company_slug=company_slug,
                            run_id=run_id,
                            stream=stream,
                            research_dir=research_dir,
                            lessons_path=lessons_path,
                            scope_check=scope_check,
                            warnings=warnings,
                            structure=structure,
                            common_context=common_context,
                        ),
                        rerun,
                    )
                )
            cost_usd += sum(result.cost_usd for result in results)
            for result in results:
                cause = _pass_stop_cause(result.error)
                if cause:
                    _resume_fail(
                        report_id,
                        stream,
                        f"Resume stopped: {cause}. The analysis passes that "
                        "succeeded are kept; Resume again reruns only the rest.",
                        cost_usd=round(prior_cost + cost_usd, 6),
                    )
                    return
            if kept == 0 and not any(result.ok for result in results):
                _resume_fail(
                    report_id,
                    stream,
                    _fast_passes_failure_message(results),
                    cost_usd=round(prior_cost + cost_usd, 6),
                )
                return

    zh_chaser = None
    if _memo_zh_chasing_enabled():
        zh_chaser = claude_runner.BilingualChaser(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            stream=stream,
            structure=structure,
        )
    memo_paths = {k: str(v) for k, v in _memo_paths_abs(report).items()}
    result = _run_fast_synthesis(
        run_dir=run_dir,
        stream=stream,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        zh_chaser=zh_chaser,
        speculator=None,
        cost_usd=cost_usd,
        worker_duration_ms=0,
        started_at=started_at,
        started_monotonic=started_monotonic,
        structure=structure,
        report_id=report_id,
    )
    if not result.get("ok"):
        _resume_fail(
            report_id,
            stream,
            str(result.get("error") or "Resume could not write the memo package"),
            cost_usd=round(prior_cost + _as_float(result.get("cost_usd")), 6),
        )
        return
    if result.get("paused_after_english"):
        _update_report(
            report_id,
            claude_cost_usd=round(prior_cost + _as_float(result.get("cost_usd")), 6),
        )
        return
    result["cost_usd"] = round(prior_cost + _as_float(result.get("cost_usd")), 6)
    result["resumed"] = True
    _finalize_memo_from_package(
        report_id=report_id,
        report=storage.get_report(report_id) or report,
        run_dir=run_dir,
        stream=stream,
        result=result,
        recovered=True,
    )


def _resume(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    if report.get("kind") != "investment_memo_latestage":
        raise RuntimeError(f"Report {report_id} is not an investment memo")
    if report.get("status") == "failed_scope_check":
        raise RuntimeError("Scope-check failures cannot be resumed")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")
    claude_runner.register_memo_run_quality(
        run_dir, str(report.get("model_quality") or "best")
    )
    memo_engine.register_run_engine(run_dir, report.get("engine"))
    claude_runner.register_memo_run_check_size(run_dir, _check_size_text())
    _register_prior_view(report, run_dir)
    _register_source_capture(report, run_dir)

    if _chinese_retry_requested(report, run_dir):
        # "Retry Chinese": the English was delivered; only the Chinese runs.
        _retry_chinese(report_id, report, run_dir)
        return

    package_path = _memo_package_path(run_dir)
    analysis_artifacts = _analysis_artifact_paths(run_dir)
    if (
        not package_path.exists()
        and not analysis_artifacts
        and not _english_package_path(run_dir).exists()
    ):
        raise RuntimeError(
            "Cannot resume: no memo_package.json or analysis artifacts exist"
        )
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    prior_package_path = _latest_archived_memo_package(
        run_dir,
        label="quality_failed",
    )
    # Only regenerate the English package when the English DOCX quality gate
    # actually failed. Chinese-parity-only complete_with_warnings must reuse
    # the package — regenerating for 30+ minutes was the "keeps happening" loop.
    quality_failed = _english_quality_gate_needs_package_regen(
        report,
        quality_lint_path=quality_lint_path,
    )
    # Where a regeneration goes: the fast resume continues from disk with
    # the run's own structure; the legacy one-shot agent (BSH_MEMO_FAST_
    # PIPELINE=0, and the v1 quality regeneration) writes only late v1.
    resume_structure = _report_structure(report)
    v2_run = not _structure_is_v1(resume_structure)
    fast_resume = _memo_fast_pipeline_enabled() and (v2_run or not quality_failed)

    _archive_stream_for_resume(run_dir)
    stream = _RunStream(report_id, memo_prep.stream_path(run_dir), truncate=True)
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_paths_abs = _memo_paths_abs(report)

    stream.emit(
        "job_init",
        kind="memo",
        title=f"Resume investment memo — {company_name}",
        subtitle="Resume from existing run artifacts",
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
        resumed=True,
    )
    _update_report(
        report_id,
        status="analyzing",
        stage="Resuming memo from existing artifacts",
        progress=65 if not package_path.exists() else 82,
        error=None,
        failure_phase=None,
        failure_detail=None,
        # The resumed run delivers new documents and states its own warnings.
        quality_warnings=None,
        quality_warnings_zh=None,
        quality_warning_items=None,
        english_only=None,
        english_ready_at=None,
    )

    if quality_failed and package_path.exists() and not fast_resume and v2_run:
        # Nothing can regenerate this structure here; say so BEFORE the
        # delivered package is archived, never after.
        message = (
            "Resume cannot regenerate this memo: the run uses the "
            f"{resume_structure.stage} v{resume_structure.version} report "
            "structure, and with BSH_MEMO_FAST_PIPELINE=0 the resume agent "
            "only writes the legacy structure. Run a fresh report instead."
        )
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Memo resume failed",
            error=message,
            failure_phase="resume",
            failure_detail=message,
        )
        stream.emit("error", error=message, phase="resume")
        return
    if quality_failed and package_path.exists():
        if not analysis_artifacts:
            message = (
                "Previous memo failed the DOCX quality gate, but no analysis "
                "artifacts are available to regenerate the memo package."
            )
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Memo resume failed",
                error=message,
                failure_phase="resume",
                failure_detail=message,
            )
            stream.emit("error", error=message, phase="resume")
            return
        archive_path = _archive_memo_package(package_path, label="quality_failed")
        prior_package_path = archive_path
        stage_message = (
            "Previous memo package failed the DOCX quality gate; "
            "regenerating from analysis artifacts"
        )
        stream.emit(
            "stage",
            stage="resume_package_quality_failed",
            message=stage_message,
            memo_package=memo_prep._rel(archive_path),
            quality_lint=(
                memo_prep._rel(quality_lint_path)
                if quality_lint_path.exists()
                else None
            ),
            recovered=True,
        )
        _update_report(
            report_id,
            stage="Regenerating memo package after quality gate failure",
            progress=65,
        )
    elif quality_failed and prior_package_path and not package_path.exists():
        stream.emit(
            "stage",
            stage="resume_package_quality_failed_continue",
            message=(
                "Continuing memo package regeneration from archived "
                "quality-gate package"
            ),
            memo_package=memo_prep._rel(prior_package_path),
            quality_lint=(
                memo_prep._rel(quality_lint_path)
                if quality_lint_path.exists()
                else None
            ),
            recovered=True,
        )

    if package_path.exists():
        package_error = _memo_package_render_validation_error(package_path)
        if package_error:
            if not analysis_artifacts:
                message = (
                    "Existing memo_package.json failed renderer validation and "
                    "no analysis artifacts are available to regenerate it: "
                    f"{package_error}"
                )
                _update_report(
                    report_id,
                    status="failed_during_analysis",
                    stage="Memo resume failed",
                    error=message,
                    failure_phase="resume",
                    failure_detail=message,
                )
                stream.emit("error", error=message, phase="resume")
                return
            archive_path = _archive_invalid_memo_package(package_path)
            stream.emit(
                "stage",
                stage="resume_package_invalid",
                message=(
                    "Existing memo package failed renderer validation; "
                    "regenerating from analysis artifacts"
                ),
                memo_package=memo_prep._rel(archive_path),
                validation_error=package_error,
                recovered=True,
            )
            _update_report(
                report_id,
                stage="Regenerating invalid memo package from existing artifacts",
                progress=65,
            )

    if package_path.exists():
        stream.emit(
            "stage",
            stage="resume_package_reuse",
            message="Using existing memo package and resuming rendering",
            memo_package=memo_prep._rel(package_path),
            recovered=True,
        )
        result = {
            "ok": True,
            "resumed": True,
            "cost_usd": report.get("claude_cost_usd"),
            "duration_ms": report.get("claude_duration_ms"),
        }
    else:
        if fast_resume:
            # Continue the run from disk (kept passes, reused English, the
            # run's own structure and engine) instead of rewriting it.
            _resume_fast(
                report_id,
                storage.get_report(report_id) or report,
                run_dir,
                stream,
                reuse_english=not quality_failed,
            )
            return
        # The resume regeneration agent (run_resume_memo_package) writes
        # the historical late v1 package shape; a run classified into a
        # v2-family structure cannot be regenerated by it — that would
        # silently downgrade the report's structure. Fail loudly instead.
        # The structure is the run's own: its recorded template version,
        # never the env flag of the day.
        if resume_structure.scorecard_weights():
            message = (
                "Resume cannot regenerate this memo: the run uses the "
                f"{resume_structure.stage} v{resume_structure.version} "
                "report structure, and the resume agent only writes the "
                "legacy structure. Run a fresh report instead."
            )
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Memo resume failed",
                error=message,
                failure_phase="resume",
                failure_detail=message,
            )
            stream.emit("error", error=message, phase="resume")
            return
        analysis_session_path = _analysis_session_path_for_report(company_slug, report)
        lessons_path = serena_analysis.memo_lessons_path(company_slug)
        if not lessons_path.exists():
            lessons_path = None
        result = {"ok": False, "error": "Resume memo package did not run"}
        max_attempts = 1 + _memo_resume_package_retries()
        validation_feedback: str | None = None
        for attempt in range(1, max_attempts + 1):
            attempt_started_at = _now_iso()
            attempt_started = time.monotonic()
            if attempt > 1:
                retry_reason = (
                    "renderer validation errors"
                    if validation_feedback
                    else "transient Claude transport error"
                )
                stream.emit(
                    "stage",
                    stage="resume_package_retry",
                    message=(
                        f"Retrying memo package resume after {retry_reason} "
                        f"(attempt {attempt}/{max_attempts})"
                    ),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    previous_error=result.get("error"),
                    recovered=True,
                )
            _emit_phase_timing(
                stream,
                phase="memo_resume_package_attempt",
                status="started",
                started_at=attempt_started_at,
                started_monotonic=attempt_started,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            result = claude_runner.run_resume_memo_package(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                settings_path=memo_prep.SETTINGS_FILE,
                companies_yaml_path=_run_companies_yaml(run_dir),
                memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
                research_dir=_research_dir_for(company_slug),
                analysis_session_path=analysis_session_path,
                lessons_path=lessons_path,
                scope_check=report.get("scope_check"),
                warnings=list(report.get("warnings") or []),
                quality_lint_path=(
                    quality_lint_path if quality_lint_path.exists() else None
                ),
                prior_package_path=prior_package_path,
                validation_feedback=validation_feedback,
                progress=stream,
                timeout_sec=1800,
            )
            validation_feedback = None
            if result.get("ok"):
                # The generation agent reporting success is not the gate —
                # validate the freshly written package against the renderer
                # contract now, so a contract violation retries here with
                # the errors fed back instead of failing at render time.
                if not package_path.exists():
                    result = {
                        "ok": False,
                        "error": (
                            "Resume run reported success but wrote no "
                            f"memo package at {memo_prep._rel(package_path)}"
                        ),
                        "cost_usd": result.get("cost_usd"),
                        "duration_ms": result.get("duration_ms"),
                        "usage": result.get("usage"),
                    }
                else:
                    package_error = _memo_package_render_validation_error(
                        package_path
                    )
                    archive_label = "invalid"
                    failed_gate = "renderer validation"
                    if not package_error:
                        package_error = _memo_package_prerender_quality_error(
                            package_path, run_dir=run_dir
                        )
                        archive_label = "quality_failed"
                        failed_gate = "pre-render quality checks"
                        if package_error and attempt >= max_attempts:
                            # Out of retries but the package renders — carry
                            # the findings as warnings and deliver the memo
                            # (finalize marks it complete_with_warnings)
                            # instead of blocking with nothing.
                            stream.emit(
                                "stage",
                                stage="resume_package_quality_warning",
                                message=(
                                    "Memo package still has quality findings "
                                    "after retries; delivering with warnings"
                                ),
                                validation_error=package_error[:4000],
                                attempt=attempt,
                                max_attempts=max_attempts,
                                recovered=True,
                            )
                            package_error = None
                    if package_error:
                        archive_path = _archive_memo_package(
                            package_path, label=archive_label
                        )
                        prior_package_path = archive_path
                        validation_feedback = package_error
                        stream.emit(
                            "stage",
                            stage="resume_package_invalid",
                            message=(
                                "Regenerated memo package failed "
                                f"{failed_gate}"
                            ),
                            memo_package=memo_prep._rel(archive_path),
                            validation_error=package_error[:4000],
                            attempt=attempt,
                            max_attempts=max_attempts,
                            recovered=True,
                        )
                        result = {
                            "ok": False,
                            "error": (
                                "Regenerated memo package failed "
                                f"{failed_gate}: {package_error}"
                            ),
                            "validation_error": package_error,
                            "cost_usd": result.get("cost_usd"),
                            "duration_ms": result.get("duration_ms"),
                            "usage": result.get("usage"),
                        }
            if result.get("ok"):
                _emit_phase_timing(
                    stream,
                    phase="memo_resume_package_attempt",
                    status="finished",
                    started_at=attempt_started_at,
                    started_monotonic=attempt_started,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    cost_usd=result.get("cost_usd"),
                    claude_duration_ms=result.get("duration_ms"),
                    usage=result.get("usage"),
                )
                break
            message = result.get("error") or "Resume memo package run failed"
            transient = claude_runner.is_transient_claude_error(message)
            _emit_phase_timing(
                stream,
                phase="memo_resume_package_attempt",
                status="failed",
                started_at=attempt_started_at,
                started_monotonic=attempt_started,
                attempt=attempt,
                max_attempts=max_attempts,
                transient=transient,
                error=message,
                cost_usd=result.get("cost_usd"),
                claude_duration_ms=result.get("duration_ms"),
                usage=result.get("usage"),
            )
            if (transient or validation_feedback) and attempt < max_attempts:
                backoff_sec = _memo_fast_retry_backoff_sec() if transient else 0.0
                retry_reason = (
                    "renderer validation errors"
                    if validation_feedback
                    else "a transient Claude transport error"
                )
                stream.emit(
                    "stage",
                    stage="resume_package_retry_scheduled",
                    message=(
                        f"Memo resume hit {retry_reason}; "
                        f"retrying attempt {attempt + 1}/{max_attempts}"
                    ),
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    retry_in_sec=backoff_sec,
                    previous_error=message,
                    recovered=True,
                )
                if backoff_sec > 0:
                    time.sleep(backoff_sec)
                continue
            break

    if not result.get("ok"):
        message = result.get("error") or "Resume memo package run failed"
        if package_path.exists():
            stream.emit(
                "stage",
                stage="resume_salvaging_memo_package",
                message="Resume returned an error after writing memo package; rendering for QA",
                memo_package=memo_prep._rel(package_path),
                recovered=True,
            )
            if _finalize_memo_from_package(
                report_id=report_id,
                report=storage.get_report(report_id) or report,
                run_dir=run_dir,
                stream=stream,
                result=result,
                recovered=True,
            ):
                return
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Memo resume failed",
            error=message,
            failure_phase="resume",
            failure_detail=message,
            artifacts_available=False,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit("error", error=message, phase="resume")
        return

    _finalize_memo_from_package(
        report_id=report_id,
        report=storage.get_report(report_id) or report,
        run_dir=run_dir,
        stream=stream,
        result=result,
        recovered=True,
    )


def _run(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = _RunStream(report_id, 
        memo_prep.stream_path(run_dir), truncate=False
    )

    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_files = report.get("memo_files") or []
    memo_paths_rel = {f["language"]: f["path"] for f in memo_files}
    memo_paths_abs = {
        lang: memo_prep.DATA_DIR.parent / rel
        for lang, rel in memo_paths_rel.items()
    }
    internal_paths_abs = _internal_memo_paths_abs(report)
    analysis_session_path = _analysis_session_path_for_report(company_slug, report)
    approved_analysis_session_path = _analysis_session_path_for_report(
        company_slug,
        report,
        require_approved=True,
    )
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None
    fast_pipeline_enabled = _memo_fast_pipeline_enabled()
    background_started_at = _now_iso()
    background_started = time.monotonic()
    _emit_phase_timing(
        stream,
        phase="memo_background_run",
        status="started",
        started_at=background_started_at,
        started_monotonic=background_started,
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
        fast_pipeline=fast_pipeline_enabled,
        approved_packet_mode=bool(approved_analysis_session_path),
        internal_memo_enabled=_internal_diligence_memo_enabled(),
        pdf_previews_enabled=_memo_pdf_previews_enabled(),
    )

    analyzing_stage = (
        "Running parallel analysis passes"
        if fast_pipeline_enabled
        else "Running BSH investment memo skill (Serena's version)"
    )
    _update_report(
        report_id,
        status="analyzing",
        stage=analyzing_stage,
        progress=15,
    )

    _write_recent_news_file(
        str(report.get("company_id") or company_slug),
        _research_dir_for(company_slug),
    )
    _write_decision_record_file(
        str(report.get("company_id") or company_slug),
        _research_dir_for(company_slug),
    )
    _stage_run_inputs(report, run_dir, _research_dir_for(company_slug), stream)
    _write_known_sources_file(
        str(report.get("company_id") or company_slug),
        _research_dir_for(company_slug),
    )

    with _creeping_report_progress(
        report_id,
        floor=15,
        ceiling=78,
        stage=analyzing_stage,
    ):
        if fast_pipeline_enabled:
            result = _run_fast_memo_pipeline(
                report_id=report_id,
                report=report,
                run_dir=run_dir,
                stream=stream,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                memo_paths_abs=memo_paths_abs,
                analysis_session_path=approved_analysis_session_path,
                lessons_path=lessons_path,
            )
        else:
            legacy_started_at = _now_iso()
            legacy_started = time.monotonic()
            _emit_phase_timing(
                stream,
                phase="memo_legacy_claude",
                status="started",
                started_at=legacy_started_at,
                started_monotonic=legacy_started,
                timeout_sec=3600,
            )
            stream.emit(
                "stage",
                stage="memo_legacy_pipeline_starting",
                message=(
                    "Running legacy single-Claude memo pipeline because "
                    "BSH_MEMO_FAST_PIPELINE=0"
                ),
            )
            # --- One Claude subprocess; Serena's skill runs end-to-end ---------
            result = claude_runner.run_investment_memo(
                run_dir=run_dir,
                company_name=company_name,
                company_slug=company_slug,
                run_id=run_id,
                settings_path=memo_prep.SETTINGS_FILE,
                companies_yaml_path=memo_prep.COMPANIES_FILE,
                memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
                research_dir=_research_dir_for(company_slug),
                analysis_session_path=analysis_session_path,
                lessons_path=lessons_path,
                scope_check=report.get("scope_check"),
                warnings=list(report.get("warnings") or []),
                progress=stream,
                timeout_sec=3600,
            )
            _emit_phase_timing(
                stream,
                phase="memo_legacy_claude",
                status="finished" if result.get("ok") else "failed",
                started_at=legacy_started_at,
                started_monotonic=legacy_started,
                cost_usd=result.get("cost_usd"),
                claude_duration_ms=result.get("duration_ms"),
                usage=result.get("usage"),
                error=result.get("error"),
            )
            if result.get("ok"):
                # The one-shot skill just wrote the whole package.
                _stamp_generated_with_on_disk(_memo_package_path(run_dir), report, run_dir)

    if not result.get("ok"):
        message = result.get("error") or "Claude skill run failed"
        package_path = _memo_package_path(run_dir)
        salvaged = False
        if (
            package_path.exists()
            and memo_paths_abs.get("en")
            and memo_paths_abs.get("zh")
        ):
            stream.emit(
                "stage",
                stage="salvaging_memo_artifacts",
                message="Rendering partial memo artifacts for QA",
            )
            if _render_memo_outputs(
                report_id=report_id,
                run_dir=run_dir,
                memo_paths_abs=memo_paths_abs,
                stream=stream,
                result=result,
            ):
                _maybe_render_memo_pdf_previews(
                    report_id=report_id,
                    memo_paths_abs=memo_paths_abs,
                    stream=stream,
                    progress=86,
                )
                salvaged = True
            else:
                return
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage=(
                "Claude skill run failed; partial memo available"
                if salvaged
                else "Claude skill run failed"
            ),
            error=message,
            failure_phase="analysis",
            failure_detail=message,
            artifacts_available=salvaged,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        _sync_tracking_auto_run(report, success=False, error=message)
        _emit_phase_timing(
            stream,
            phase="memo_background_run",
            status="failed",
            started_at=background_started_at,
            started_monotonic=background_started,
            report_id=report_id,
            company_id=company_slug,
            run_id=run_id,
            fast_pipeline=fast_pipeline_enabled,
            approved_packet_mode=bool(approved_analysis_session_path),
            error=message,
            artifacts_available=salvaged,
            cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
            worker_duration_ms=result.get("worker_duration_ms"),
        )
        stream.emit(
            "error",
            error=message,
            phase="analysis",
            artifacts_available=salvaged,
        )
        return

    if result.get("paused_after_english"):
        # The run stopped after its English for review: its record and its
        # stream (closed with `done`) already say so; Resume writes the
        # Chinese.
        return

    finalized = _finalize_memo_from_package(
        report_id=report_id,
        report=report,
        run_dir=run_dir,
        stream=stream,
        result=result,
        background_started_at=background_started_at,
        background_started_monotonic=background_started,
        background_fields={
            "report_id": report_id,
            "company_id": company_slug,
            "run_id": run_id,
            "fast_pipeline": fast_pipeline_enabled,
            "approved_packet_mode": bool(approved_analysis_session_path),
        },
    )
    if finalized:
        # One-Click card publish: after acceptance + gates, outside the
        # pipeline, so a failed run never publishes and the pipeline
        # itself stays byte-identical.
        _publish_studio_cards(
            report_id=report_id,
            report=report,
            run_dir=run_dir,
            stream=stream,
        )
    return

def _publish_studio_cards(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
) -> None:
    """One-Click publish: refresh the studio cards from this run's spine.

    Best-effort observability for the user — a publish failure must never
    alter the run's terminal status. Studio-mode runs skip this: their
    cards already carry the user's edits (re-seeding would overwrite user
    bullets with agent stubs). Monolithic runs have no spine.json and skip
    silently.
    """
    if str(report.get("memo_mode") or "auto") == "studio":
        return
    spine_path = run_dir / "logs" / "english_units" / "spine.json"
    try:
        spine = json.loads(spine_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.debug("no spine.json to publish studio cards from")
        return
    except Exception:  # noqa: BLE001
        logger.warning("studio card publish: unreadable spine", exc_info=True)
        return
    try:
        from . import memo_editor_store

        state = memo_editor_store.apply_agent_spine(
            str(report.get("company_id")),
            spine,
            {
                "report_id": report_id,
                "run_id": str(report.get("run_id") or ""),
                "mode": "auto",
            },
        )
        stream.emit(
            "stage",
            stage="memo_studio_cards_published",
            message="Studio cards updated from this run's spine",
            revision_id=state.get("revision_id"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("studio card publish failed", exc_info=True)
        stream.emit(
            "stage",
            stage="memo_studio_cards_publish_failed",
            message="Studio card update failed; the memo is unaffected",
        )


def _investigate(report_id: str) -> None:
    """Memo Studio "Start Deep Investigate".

    Phase 1 observability + the Phase-2 fan-out + one deterministic
    standalone spine, card seeding, then park at ``awaiting_studio`` with
    a terminal ``done`` on the stream. That terminal event is what makes
    the parked state safe everywhere: SSE closes, the jobs rail clears,
    and the orphan sweep (which only fires on terminal-less streams)
    leaves the run alone.
    """
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")
    claude_runner.register_memo_run_quality(
        run_dir, str(report.get("model_quality") or "best")
    )
    memo_engine.register_run_engine(run_dir, report.get("engine"))
    claude_runner.register_memo_run_check_size(run_dir, _check_size_text())
    _register_prior_view(report, run_dir)
    _register_source_capture(report, run_dir)
    stream = _RunStream(report_id, 
        memo_prep.stream_path(run_dir), truncate=False
    )
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_paths = {
        f["language"]: str(memo_prep.DATA_DIR.parent / f["path"])
        for f in report.get("memo_files") or []
        if f.get("language") and f.get("path")
    }
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None
    warnings = list(report.get("warnings") or [])
    scope_check = report.get("scope_check")
    research_dir = _research_dir_for(company_slug)
    _write_recent_news_file(
        str(report.get("company_id") or company_slug), research_dir
    )
    _write_decision_record_file(
        str(report.get("company_id") or company_slug), research_dir
    )
    _stage_run_inputs(report, run_dir, research_dir, stream)
    _write_known_sources_file(
        str(report.get("company_id") or company_slug), research_dir
    )

    started_at = _now_iso()
    started_monotonic = time.monotonic()
    _emit_phase_timing(
        stream,
        phase="memo_studio_investigation",
        status="started",
        started_at=started_at,
        started_monotonic=started_monotonic,
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
    )
    _update_report(
        report_id,
        status="analyzing",
        stage="Deep investigation — running analysis passes",
        progress=15,
    )
    stream.emit(
        "stage",
        stage="memo_studio_investigation_starting",
        message=(
            "Running deep investigation: analysis passes, then the "
            "studio spine"
        ),
        max_workers=_memo_fast_max_workers(),
    )
    stream.emit(
        "thread_started",
        thread=claude_runner._MEMO_PHASE1_THREAD,
        title=claude_runner._MEMO_PHASE1_THREAD,
    )
    fact_ledger = claude_runner.load_memo_fact_ledger(research_dir)
    if fact_ledger:
        stream.emit(
            "stage",
            stage="memo_fact_ledger",
            message=(
                f"Curated fact ledger loaded ({len(fact_ledger)} chars); "
                "injecting into analysis passes and the spine"
            ),
            thread=claude_runner._MEMO_PHASE1_THREAD,
            chars=len(fact_ledger),
            path=str(research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME),
        )
    elif claude_runner._memo_fact_ledger_enabled():
        # Say so out loud: without a ledger the run's headline facts depend
        # on what each analysis pass happens to retrieve (the fact lottery).
        stream.emit(
            "stage",
            stage="memo_fact_ledger_missing",
            message=(
                "No curated fact ledger for this company; headline facts "
                "depend on per-pass retrieval. Add dated facts at "
                f"{research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME}"
            ),
            thread=claude_runner._MEMO_PHASE1_THREAD,
            path=str(research_dir / claude_runner.MEMO_FACT_LEDGER_FILENAME),
        )
    stream.emit("thread_finished", thread=claude_runner._MEMO_PHASE1_THREAD)

    with _creeping_report_progress(
        report_id,
        floor=15,
        ceiling=42,
        stage="Deep investigation — running analysis passes",
    ):
        pass_results, cost_usd, worker_duration_ms = _run_fast_phase2(
            report_id=report_id,
            run_dir=run_dir,
            stream=stream,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            research_dir=research_dir,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            speculator=None,
        )
    if pass_results is None:
        # _run_fast_phase2 already recorded the failure and emitted the
        # stream error.
        failure = _recorded_fast_phase2_failure(report_id)
        _emit_phase_timing(
            stream,
            phase="memo_studio_investigation",
            status="failed",
            started_at=started_at,
            started_monotonic=started_monotonic,
            error=failure,
            cost_usd=round(cost_usd, 6),
        )
        _sync_tracking_auto_run(report, success=False, error=failure)
        return
    failed_ids = [r.spec.pass_id for r in pass_results if not r.ok]

    _update_report(
        report_id,
        stage="Deep investigation — pinning the studio spine",
        progress=45,
    )
    spine_label = "Studio spine"
    spine_progress = _ThreadProgress(stream, spine_label)
    spine_started_at = _now_iso()
    spine_started = time.monotonic()
    spine_progress.emit("thread_started", title=spine_label)
    _emit_phase_timing(
        stream,
        phase="memo_studio_spine",
        status="started",
        started_at=spine_started_at,
        started_monotonic=spine_started,
        thread=spine_label,
    )
    spine_payload = None
    spine_error: str | None = None
    for attempt in (1, 2):
        spine_payload, spine_error = claude_runner.run_memo_english_spine_standalone(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            settings_path=memo_prep.SETTINGS_FILE,
            companies_yaml_path=_run_companies_yaml(run_dir),
            memo_paths=memo_paths,
            research_dir=research_dir,
            analysis_session_path=None,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            progress=spine_progress,
            missing_pass_ids=failed_ids,
        )
        if spine_payload is not None:
            break
        if attempt == 1:
            spine_progress.emit(
                "stage",
                stage="memo_studio_spine_retry",
                message=(
                    "Studio spine failed; retrying once "
                    f"({str(spine_error)[:300]})"
                ),
            )
    cost_usd += spine_progress.cost_usd
    worker_duration_ms += spine_progress.duration_ms
    if spine_payload is None:
        message = f"Studio spine failed: {spine_error}"
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Studio spine failed",
            error=message,
            failure_phase="studio_spine",
            failure_detail=message,
            claude_cost_usd=round(cost_usd, 6),
        )
        spine_progress.emit("thread_failed", error=str(spine_error)[:500])
        _emit_phase_timing(
            stream,
            phase="memo_studio_spine",
            status="failed",
            started_at=spine_started_at,
            started_monotonic=spine_started,
            thread=spine_label,
            error=str(spine_error)[:500],
        )
        stream.emit("error", error=message, phase="studio_spine")
        _sync_tracking_auto_run(report, success=False, error=message)
        return
    spine_progress.emit("thread_finished")
    _emit_phase_timing(
        stream,
        phase="memo_studio_spine",
        status="finished",
        started_at=spine_started_at,
        started_monotonic=spine_started,
        thread=spine_label,
        cost_usd=round(spine_progress.cost_usd, 6),
        claude_duration_ms=spine_progress.duration_ms,
    )
    _company_stage_spine_hook(report_id, stream)(spine_payload)

    seeded_revision_id = None
    try:
        from . import memo_editor_store

        state = memo_editor_store.apply_agent_spine(
            company_slug,
            spine_payload,
            {"report_id": report_id, "run_id": run_id, "mode": "studio"},
        )
        seeded_revision_id = state.get("revision_id")
        stream.emit(
            "stage",
            stage="memo_studio_cards_seeded",
            message="Studio cards seeded from the investigation spine",
            revision_id=seeded_revision_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("studio card seeding failed")
        message = f"Studio card seeding failed: {exc}"
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Studio card seeding failed",
            error=message,
            failure_phase="studio_seed",
            failure_detail=message,
            claude_cost_usd=round(cost_usd, 6),
        )
        stream.emit("error", error=message, phase="studio_seed")
        _sync_tracking_auto_run(report, success=False, error=message)
        return

    total_cost = round(cost_usd, 6)
    _update_report(
        report_id,
        status="awaiting_studio",
        stage="Investigation complete — review the studio cards",
        progress=55,
        claude_cost_usd=total_cost,
        studio_investigation={
            "completed_at": _now_iso(),
            "pass_ok": [r.spec.pass_id for r in pass_results if r.ok],
            "pass_failed": failed_ids,
            "cost_usd": total_cost,
            "seeded_revision_id": seeded_revision_id,
        },
    )
    _emit_phase_timing(
        stream,
        phase="memo_studio_investigation",
        status="finished",
        started_at=started_at,
        started_monotonic=started_monotonic,
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
        cost_usd=total_cost,
        worker_duration_ms=worker_duration_ms,
    )
    stream.emit(
        "done",
        phase="investigation",
        awaiting_studio=True,
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
        cost_usd=total_cost,
        pass_failed=failed_ids,
    )
    # The awaiting_studio park is this worker's terminal state — finalize
    # a tracking auto-run here since no memo finalize hook ever fires.
    _sync_tracking_auto_run(report, success=True)


def _generate_from_studio(report_id: str) -> None:
    """Memo Studio "Generate Report": Phases 3-4 from the composed spine.

    The endpoint already composed and wrote ``spine.json`` from the user's
    cards (freeze semantics: this worker reads only that file). The stream
    is archived and restarted so the jobs rail and SSE reattach to a fresh
    generation run.
    """
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_paths = {
        f["language"]: str(memo_prep.DATA_DIR.parent / f["path"])
        for f in report.get("memo_files") or []
        if f.get("language") and f.get("path")
    }
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None
    warnings = list(report.get("warnings") or [])
    scope_check = report.get("scope_check")
    research_dir = _research_dir_for(company_slug)

    _archive_stream(run_dir, label="generate")
    final_package_path = _memo_package_path(run_dir)
    if final_package_path.exists():
        _archive_memo_package(final_package_path, label="studio_regenerate")
    english_package_path = run_dir / "logs" / "memo_package.en.json"
    if english_package_path.exists():
        _archive_memo_package(
            english_package_path, label="en.studio_regenerate"
        )

    stream = _RunStream(report_id, 
        memo_prep.stream_path(run_dir), truncate=True
    )
    _update_report(report_id, english_ready_at=None, english_only=None)
    claude_runner.register_memo_run_check_size(run_dir, _check_size_text())
    _register_prior_view(report, run_dir)
    generation = report.get("studio_generate") or {}
    stream.emit(
        "job_init",
        kind=memo_prep.JOB_KIND,
        title=f"Investment memo — {company_name}",
        subtitle="Memo Studio generate",
        report_id=report_id,
        company_id=company_slug,
        run_id=run_id,
        run_dir=str(run_dir),
        memo_mode="studio",
        studio_generate=True,
    )
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    stream.emit(
        "stage",
        stage="memo_studio_generate_starting",
        message="Generating the memo from the studio-composed spine",
        revision_id=generation.get("revision_id"),
        generation_count=generation.get("generation_count"),
    )
    _emit_phase_timing(
        stream,
        phase="memo_fast_pipeline",
        status="started",
        started_at=started_at,
        started_monotonic=started_monotonic,
    )

    zh_chaser = None
    if _memo_zh_chasing_enabled():
        zh_chaser = claude_runner.BilingualChaser(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            stream=stream,
        )

    result = _run_fast_synthesis(
        run_dir=run_dir,
        stream=stream,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=None,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        zh_chaser=zh_chaser,
        speculator=None,
        cost_usd=0.0,
        worker_duration_ms=0,
        started_at=started_at,
        started_monotonic=started_monotonic,
        pinned_spine_path=run_dir / "logs" / "english_units" / "spine.json",
        memo_mode="studio",
        report_id=report_id,
    )
    if not result.get("ok"):
        message = result.get("error") or "Studio memo generation failed"
        _update_report(
            report_id,
            status="failed_during_analysis",
            stage="Studio memo generation failed",
            error=message,
            failure_phase="studio_generate",
            failure_detail=message,
            claude_cost_usd=result.get("cost_usd"),
        )
        stream.emit("error", error=message, phase="studio_generate")
        return
    if result.get("paused_after_english"):
        return

    _finalize_memo_from_package(
        report_id=report_id,
        report=report,
        run_dir=run_dir,
        stream=stream,
        result=result,
        background_started_at=started_at,
        background_started_monotonic=started_monotonic,
        background_fields={
            "report_id": report_id,
            "company_id": company_slug,
            "run_id": run_id,
            "fast_pipeline": True,
            "studio_generate": True,
        },
    )
