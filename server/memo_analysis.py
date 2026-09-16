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
from dataclasses import dataclass
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
        os.environ.get("BSH_MEMO_ZH_CHASING", "0") == "1"
        and os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") == "1"
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
    return _env_flag("BSH_MEMO_PIN_CHECK_REPAIR", default=False)


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
    entries = report.get("internal_memo_files") or []
    if not entries:
        return {}
    entry = entries[0]
    paths: dict[str, Path] = {}
    if entry.get("markdown_path"):
        paths["md"] = memo_prep.DATA_DIR.parent / entry["markdown_path"]
    if entry.get("path"):
        paths["docx"] = memo_prep.DATA_DIR.parent / entry["path"]
    if entry.get("pdf_path"):
        paths["pdf"] = memo_prep.DATA_DIR.parent / entry["pdf_path"]
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


def _memo_package_prerender_quality_findings(
    package: dict | Path,
    *,
    check_parity: bool = True,
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
            lint_result = memo_quality_lint.lint_memo_docx(out_en, structure)
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
) -> str | None:
    """Joined-string form of ``_memo_package_prerender_quality_findings``."""
    problems = _memo_package_prerender_quality_findings(
        package, check_parity=check_parity
    )
    return "; ".join(problems) if problems else None


def _structure_for_run(run_dir: Path) -> memo_structure.MemoStructure:
    """Resolve the structure the run's accepted package was written
    against (from the meta stamp in ``memo_package.json``); late v1 for
    legacy runs and unreadable packages."""
    try:
        package = json.loads(
            _memo_package_path(run_dir).read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001
        return memo_structure.LATE
    return memo_structure.for_package(package)


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
        progress.emit(
            "stage",
            stage="memo_pin_check",
            message=(
                f"Pin-echo check: {result.pins_checked} pins checked, "
                f"{len(result.findings)} finding(s)"
            ),
            pins_checked=result.pins_checked,
            pins_skipped=result.pins_skipped,
            findings=[finding.to_dict() for finding in result.findings][:8],
            repair_feed=_memo_pin_check_repair_enabled(),
            attempt=attempt,
        )
        return result.summary_lines()
    except Exception:  # noqa: BLE001
        logger.warning("memo pin check failed", exc_info=True)
        return []


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
    structural_errors = memo_docx_renderer.english_package_validation_errors(
        repaired
    )
    remaining = (
        structural_errors
        or _memo_package_prerender_quality_findings(
            memo_docx_renderer.fill_blank_zh_placeholders(repaired),
            check_parity=False,
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


_MEMO_PACKAGE_VOICE_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
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
        re.compile(r"\bWe invest behind\b", re.IGNORECASE),
        "BSH invests in",
    ),
    (
        # (?!-) keeps hyphenated verbs ("we back-solve", "we back-test")
        # out of the sell-side rewrite; they are modeling vocabulary.
        re.compile(r"\bWe back\b(?!-)", re.IGNORECASE),
        "BSH invests in",
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
        re.compile(r"\bwe recommend participating in\b", re.IGNORECASE),
        "the recommendation is to commit capital to",
    ),
    (
        re.compile(r"\bwe recommend participating\b", re.IGNORECASE),
        "the recommendation is to commit capital",
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
    (
        re.compile(r"\bunderwriting\b", re.IGNORECASE),
        "investment case",
    ),
    (
        re.compile(r"\bunderwritten\b", re.IGNORECASE),
        "supported",
    ),
    (
        re.compile(r"\bunderwrites\b", re.IGNORECASE),
        "supports",
    ),
    (
        re.compile(r"\bunderwrite\b", re.IGNORECASE),
        "rely on",
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


def _rewritten_memo_package_voice(payload: Any) -> tuple[Any, list[dict[str, str]]]:
    """Apply the deterministic voice rewrites to a package payload copy."""
    changes: list[dict[str, str]] = []

    def visit(value: Any, path: str = "") -> Any:
        if isinstance(value, dict):
            return {
                key: visit(item, f"{path}.{key}" if path else str(key))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [visit(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, str) and path.endswith(".en"):
            rewritten = _rewrite_memo_package_voice_text(value)
            if rewritten != value:
                changes.append(
                    {
                        "path": path,
                        "before": value[:220],
                        "after": rewritten[:220],
                    }
                )
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
) -> dict:
    errors: list[str] = []
    package_path = _memo_package_path(run_dir)
    expected = {
        "memo_package": package_path,
        "english_memo": memo_paths_abs.get("en"),
        "chinese_memo": memo_paths_abs.get("zh"),
        "validation_en": run_dir / "logs" / "validation.txt",
        "validation_zh": run_dir / "logs" / "validation_cn.txt",
        "file_inventory": run_dir / "logs" / "file_inventory.md",
        "run_manifest": run_dir / "logs" / "run_manifest.md",
    }
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
        if "memo_en:" not in text or "memo_zh:" not in text:
            errors.append("file_inventory missing rendered memo entries")
    return {
        "run_dir": memo_prep._rel(run_dir),
        "memo_package": memo_prep._rel(package_path),
        "errors": errors,
        "expected_files": expected_files,
    }


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
        lint_result = memo_quality_lint.lint_memo_docx(
            memo_path, _structure_for_run(run_dir)
        )
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
) -> dict | None:
    with _timed_phase(
        stream,
        phase="memo_internal_diligence",
        run_id=run_id,
    ) as timing:
        md_path = internal_paths_abs.get("md")
        docx_path = internal_paths_abs.get("docx")
        if not md_path or not docx_path:
            message = "Report record is missing internal diligence memo paths."
            timing["status"] = "failed"
            timing["error"] = message
            _fail_internal_memo(
                report_id=report_id,
                stream=stream,
                result=result,
                message=message,
            )
            return None

        timing["markdown_path"] = memo_prep._rel(md_path)
        timing["docx_path"] = memo_prep._rel(docx_path)
        _update_report(
            report_id,
            stage="Writing internal diligence memo",
            progress=92,
        )
        internal_result = claude_runner.run_internal_diligence_memo(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            settings_path=memo_prep.SETTINGS_FILE,
            companies_yaml_path=memo_prep.COMPANIES_FILE,
            memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
            internal_markdown_path=md_path,
            research_dir=research_store.RESEARCH_ROOT / company_slug,
            analysis_session_path=analysis_session_path,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            progress=stream,
            timeout_sec=1200,
        )
        timing["claude_cost_usd"] = internal_result.get("cost_usd")
        timing["claude_duration_ms"] = internal_result.get("duration_ms")
        if not internal_result.get("ok"):
            message = internal_result.get("error") or "Internal diligence memo failed."
            timing["status"] = "failed"
            timing["error"] = message
            _fail_internal_memo(
                report_id=report_id,
                stream=stream,
                result=_combined_result(result, internal_result),
                message=message,
            )
            return None

        _update_report(
            report_id,
            stage="Rendering internal diligence memo DOCX",
            progress=94,
        )
        stream.emit(
            "stage",
            stage="rendering_internal_memo_docx",
            message="Rendering internal diligence memo DOCX",
            markdown_path=memo_prep._rel(md_path),
        )
        try:
            internal_memo_renderer.render_internal_memo(md_path, docx_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "internal diligence memo render failed for report %s",
                report_id,
            )
            message = (
                "Internal diligence memo render failed: "
                f"{type(exc).__name__}: {exc}"
            )
            timing["status"] = "failed"
            timing["error"] = message
            _fail_internal_memo(
                report_id=report_id,
                stream=stream,
                result=_combined_result(result, internal_result),
                message=message,
            )
            return None

        internal_files = [
            {
                "kind": "internal_diligence_memo",
                "language": "en",
                "markdown_path": memo_prep._rel(md_path),
                "path": memo_prep._rel(docx_path),
            }
        ]
        _update_report(report_id, internal_memo_files=internal_files)
        return internal_result


def _fail_internal_memo(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
    result: dict,
    message: str,
) -> None:
    _update_report(
        report_id,
        status="failed_during_analysis",
        stage="Internal diligence memo failed",
        error=message,
        failure_phase="internal_diligence_memo",
        failure_detail=message,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit(
        "thread_failed",
        thread=claude_runner.MEMO_PHASE6_THREAD,
        error=message,
    )
    stream.emit("error", error=message, phase="internal_diligence_memo")


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
            companies_yaml_path=memo_prep.COMPANIES_FILE,
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
    pass_common_context = claude_runner.memo_fast_pass_common_context(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        settings_path=memo_prep.SETTINGS_FILE,
        companies_yaml_path=memo_prep.COMPANIES_FILE,
        research_dir=research_dir,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
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
    research_dir = research_store.RESEARCH_ROOT / company_slug
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
    # Provisional (type-less) structure for the starting event; the Phase
    # 1 thread classifies the company type below and re-resolves it with
    # the type's lens and weight overlay.
    structure = memo_structure.active_structure(
        structure_stage, structure_mode
    )
    model_quality = str(report.get("model_quality") or "best")
    claude_runner.register_memo_run_quality(run_dir, model_quality)

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
    company_type_info = _resolve_company_type(report_id, report, run_dir, stream)
    company_type = (
        str(company_type_info.get("type") or "") if company_type_info else ""
    )
    if company_type:
        structure = memo_structure.active_structure(
            structure_stage, structure_mode, company_type
        )
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
                companies_yaml_path=memo_prep.COMPANIES_FILE,
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
            if zh_chaser is not None:
                zh_chaser.shutdown()
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
    if claude_runner._memo_artifacts_async_enabled():
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
                companies_yaml_path=memo_prep.COMPANIES_FILE,
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
        validation_errors = memo_docx_renderer.english_package_validation_errors(
            candidate
        )
        if not validation_errors:
            # Structure is good — also run the finalize-time English quality
            # gate on a throwaway render, so banned vocabulary retries here
            # with the findings fed back instead of costing a whole
            # regeneration round after the Chinese fill.
            quality_findings = _memo_package_prerender_quality_findings(
                memo_docx_renderer.fill_blank_zh_placeholders(candidate),
                check_parity=False,
            )
            if isinstance(candidate, dict):
                pin_lines = _run_memo_pin_check(
                    run_dir=run_dir,
                    candidate=candidate,
                    progress=phase3_progress,
                    attempt=attempt,
                )
                if pin_lines and _memo_pin_check_repair_enabled():
                    quality_findings = list(quality_findings) + pin_lines
            if quality_findings and isinstance(candidate, dict):
                # Try the cheap surgical repair first: quality findings are
                # localized string defects, and a full regeneration costs
                # 10-18 minutes per round (the 40-60 minute runs on record
                # were exactly these retries).
                repaired = _surgical_quality_repair(
                    run_dir=run_dir,
                    company_name=company_name,
                    run_id=run_id,
                    candidate=candidate,
                    findings=quality_findings,
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
        repair_result, repair_error = (
            claude_runner.run_memo_package_structure_repair(
                run_dir=run_dir,
                company_name=company_name,
                run_id=run_id,
                package_path=invalid_path,
                validation_errors=last_validation_errors,
                progress=phase3_progress,
            )
        )
        repaired_package = (
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
                    repaired_package
                )
            )
            if not remaining_errors:
                quality_error = _memo_package_prerender_quality_error(
                    memo_docx_renderer.fill_blank_zh_placeholders(
                        repaired_package
                    ),
                    check_parity=False,
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
        if zh_chaser is not None:
            zh_chaser.shutdown()
        if async_artifacts is not None:
            async_artifacts.shutdown()
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
        if zh_chaser is not None:
            zh_chaser.shutdown()
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
    english_package_path = run_dir / "logs" / "memo_package.en.json"
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
    bilingual_result, bilingual_error = (
        claude_runner.run_memo_fast_bilingual_package_parallel(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            english_package_path=bilingual_input_path,
            progress=phase4_progress,
            stream=stream,
        )
    )
    if bilingual_error or not isinstance(bilingual_result, dict):
        message = bilingual_error or "Chinese package pass returned no data."
        phase4_progress.emit("thread_failed", error=message)
        _emit_phase_timing(
            stream,
            phase="memo_fast_chinese_package",
            status="failed",
            started_at=phase4_started_at,
            started_monotonic=phase4_started,
            error=message,
        )
        return {"ok": False, "error": message, "cost_usd": cost_usd}
    cost_usd += _as_float(bilingual_result.get("claude_cost_usd")) or phase4_progress.cost_usd
    worker_duration_ms += _as_int(bilingual_result.get("claude_duration_ms")) or phase4_progress.duration_ms
    memo_package = bilingual_result.get("memo_package")
    if not isinstance(memo_package, dict):
        message = "Chinese package pass did not return memo_package."
        phase4_progress.emit("thread_failed", error=message)
        return {"ok": False, "error": message, "cost_usd": cost_usd}
    final_package_path = _memo_package_path(run_dir)
    _write_json(final_package_path, memo_package)
    package_error = _memo_package_render_validation_error(final_package_path)
    if package_error:
        # The English gate already validated structure, so any error here is
        # Chinese fill that didn't land (blank `zh` after a unit drifted).
        # The monolithic bilingual pass only fills blank `zh` strings — run
        # it once over the merged package as a targeted repair.
        phase4_progress.emit(
            "stage",
            stage="memo_package_zh_repair",
            message=(
                "Merged package failed renderer validation; running one "
                "monolithic Chinese fill repair pass"
            ),
            validation_error=package_error[:2000],
        )
        repair_result, repair_error = claude_runner.run_memo_fast_bilingual_package(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            english_package_path=final_package_path,
            progress=phase4_progress,
        )
        if not repair_error and isinstance(repair_result, dict):
            repaired = repair_result.get("memo_package")
            if isinstance(repaired, dict):
                cost_usd += _as_float(repair_result.get("claude_cost_usd"))
                worker_duration_ms += _as_int(
                    repair_result.get("claude_duration_ms")
                )
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
        phase4_progress.emit("thread_failed", error=message)
        _emit_phase_timing(
            stream,
            phase="memo_fast_chinese_package",
            status="failed",
            started_at=phase4_started_at,
            started_monotonic=phase4_started,
            error=message,
        )
        return {"ok": False, "error": message, "cost_usd": round(cost_usd, 6)}
    # English vocabulary was gated in phase 3; this pass surfaces the
    # bilingual findings (Chinese parity) early. They never block — the
    # memo is delivered and finalize marks it complete_with_warnings.
    quality_warning = _memo_package_prerender_quality_error(final_package_path)
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
        cost_usd=_as_float(bilingual_result.get("claude_cost_usd")),
        claude_duration_ms=_as_int(bilingual_result.get("claude_duration_ms")),
        usage=bilingual_result.get("claude_usage")
        if isinstance(bilingual_result.get("claude_usage"), dict)
        else None,
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
    )
    if parity_result.has_blocking_findings:
        return False
    parity_path = run_dir / "logs" / "memo_chinese_parity.md"
    parity_path.write_text(
        memo_chinese_parity.render_markdown_report(parity_result),
        encoding="utf-8",
    )

    lint_result = memo_quality_lint.lint_memo_docx(
        memo_paths_abs["en"], _structure_for_run(run_dir)
    )
    if lint_result.has_blocking_findings:
        return False
    lint_path = run_dir / "logs" / "memo_quality_lint.md"
    lint_path.write_text(
        memo_quality_lint.render_markdown_report(lint_result),
        encoding="utf-8",
    )

    _update_report(
        report_id,
        status="complete",
        stage="Memo ready",
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
        claude_cost_usd=terminal.get("cost_usd"),
        claude_duration_ms=terminal.get("duration_ms"),
    )
    return True


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
        if report.get("status") == "awaiting_studio":
            # A parked Memo Studio investigation is a deliberate terminal
            # state (its stream already carries `done`); nothing to recover.
            continue
        run_dir = _resolve_run_dir(report)
        if run_dir is None or not run_dir.exists():
            continue
        stream_state = _scan_memo_stream(run_dir)
        terminal = stream_state.get("terminal")
        if terminal is not None:
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
        _update_report(report["id"], memo_quality_lint=lint_payload)
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


def cancel_run(report_id: str) -> None:
    """Cancel a queued or in-flight memo run.

    Kills the run's claude subprocesses (matched by spawn cwd, plus the
    run's pid file for processes an earlier server left behind), blocks
    respawns via the run-dir marker, writes the terminal report status and
    stream event, and finalizes any tracking auto-run. The worker thread
    then unwinds on its own as its in-flight calls return cancelled; the
    run is halted first so nothing it writes while unwinding replaces the
    cancelled state.
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


def _investigate_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _investigate(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("memo studio investigation crashed")
        report = storage.get_report(report_id)
        if report:
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Investigation crashed",
                failure_phase="investigation",
                failure_detail="Investigation worker crashed; see server log.",
            )
            _sync_tracking_auto_run(
                report,
                success=False,
                error="Investigation worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = _RunStream(report_id, 
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit(
                "error", error="Investigation worker crashed; see server log."
            )
    finally:
        _unregister_active_run(report_id)


def _generate_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _generate_from_studio(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("memo studio generation crashed")
        report = storage.get_report(report_id)
        if report:
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Studio generation crashed",
                failure_phase="studio_generate",
                failure_detail=(
                    "Studio generation worker crashed; see server log."
                ),
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = _RunStream(report_id, 
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit(
                "error",
                error="Studio generation worker crashed; see server log.",
            )
    finally:
        _unregister_active_run(report_id)


def _run_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _run(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("memo analysis crashed")
        report = storage.get_report(report_id)
        if report:
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Analysis crashed",
            )
            _sync_tracking_auto_run(
                report,
                success=False,
                error="Analysis worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = _RunStream(report_id, 
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Analysis worker crashed; see server log.")
    finally:
        _unregister_active_run(report_id)


def _resume_safe(report_id: str) -> None:
    _register_active_run(report_id)
    try:
        _with_run_slot(report_id, lambda: _resume(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("memo resume crashed")
        report = storage.get_report(report_id)
        if report:
            _update_report(
                report_id,
                status="failed_during_analysis",
                stage="Resume crashed",
                failure_phase="resume",
                failure_detail="Resume worker crashed; see server log.",
            )
            _sync_tracking_auto_run(
                report,
                success=False,
                error="Resume worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = _RunStream(report_id, 
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Resume worker crashed; see server log.")
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


def _analysis_artifact_paths(run_dir: Path) -> list[Path]:
    analysis_dir = run_dir / "analysis"
    if not analysis_dir.is_dir():
        return []
    return sorted(
        p for p in analysis_dir.iterdir()
        if p.is_file() and p.suffix == ".md"
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
    if not _render_memo_outputs(
        report_id=report_id,
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        result=result,
        recovered=recovered,
    ):
        return False
    _update_report(
        report_id,
        renderer_contract=_renderer_contract_diagnostics(
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
        ),
    )

    en_exists = memo_paths_abs.get("en") and memo_paths_abs["en"].exists()
    zh_exists = memo_paths_abs.get("zh") and memo_paths_abs["zh"].exists()
    missing = []
    if not en_exists:
        missing.append(f"English .docx: {memo_paths_rel.get('en')}")
    if not zh_exists:
        missing.append(f"Chinese .docx: {memo_paths_rel.get('zh')}")

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

    quality_warnings: list[str] = []
    _parity_payload, parity_warning = _run_chinese_parity_gate(
        report_id=report_id,
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        result=result,
        recovered=recovered,
    )
    if parity_warning:
        quality_warnings.append(parity_warning)

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
        msg = (
            "Memo quality gate found "
            f"{lint_payload['p0_count']} P0 finding"
            f"{'' if lint_payload['p0_count'] == 1 else 's'}. "
            f"See {memo_prep._rel(lint_path)}."
        )
        quality_warnings.append(msg)
        payload = {
            "stage": "quality_gate_warning",
            "message": msg,
            "phase": "quality_gate",
            "lint_report": memo_prep._rel(lint_path),
            "findings": lint_payload["findings"][:10],
        }
        if recovered:
            payload["recovered"] = True
        stream.emit("stage", **payload)
    _update_report(report_id, memo_quality_lint=lint_result.to_dict())
    stream.emit("thread_finished", thread=claude_runner.MEMO_PHASE5_THREAD)

    stream.emit(
        "thread_started",
        thread=claude_runner.MEMO_PHASE6_THREAD,
        title=claude_runner.MEMO_PHASE6_THREAD,
    )
    internal_generated = False
    if internal_paths_abs and _internal_diligence_memo_enabled():
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
        )
        if internal_result is None:
            return False
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
        combined_result = dict(result)
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

    final_status = "complete_with_warnings" if quality_warnings else "complete"
    final_stage = (
        "Memo ready (quality warnings)" if quality_warnings else "Memo ready"
    )
    _update_report(
        report_id,
        status=final_status,
        stage=final_stage,
        progress=100,
        error=None,
        failure_phase=None,
        failure_detail=None,
        resume_from_status=None,
        resume_from_failure_phase=None,
        resume_from_failure_detail=None,
        artifacts_available=True,
        quality_warnings=quality_warnings or None,
        claude_cost_usd=combined_result.get("cost_usd"),
        claude_duration_ms=combined_result.get("duration_ms"),
        report_ready_at=_now_iso(),
    )
    try:
        from . import push_notify

        company = storage.get_company(str(report.get("company_id") or "")) or {}
        name = company.get("name") or report.get("company_id") or "Memo"
        push_notify.notify(
            "memo",
            "Memo ready",
            f"{name} — {final_stage}",
            data={
                "report_id": report_id,
                "company_id": report.get("company_id"),
                "deep_link": f"bshresearch://report/{report_id}",
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("memo push notify failed for %s", report_id)
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
        "memo_paths": {k: str(v) for k, v in memo_paths_abs.items()},
        "cost_usd": combined_result.get("cost_usd"),
        "duration_ms": combined_result.get("duration_ms"),
    }
    if quality_warnings:
        done_payload["quality_warnings"] = quality_warnings
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

    package_path = _memo_package_path(run_dir)
    analysis_artifacts = _analysis_artifact_paths(run_dir)
    if not package_path.exists() and not analysis_artifacts:
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
    )

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
        # The resume regeneration agent (run_resume_memo_package) writes
        # the historical late v1 package shape; a run classified into a
        # v2-family structure cannot be regenerated by it — that would
        # silently downgrade the report's structure. Fail loudly instead.
        stage_info = report.get("structure_stage")
        resume_stage = (
            str(stage_info.get("stage") or "late")
            if isinstance(stage_info, dict)
            else "late"
        )
        resume_type_info = report.get("company_type")
        resume_structure = memo_structure.active_structure(
            resume_stage,
            str(report.get("structure_mode") or "full"),
            (
                str(resume_type_info.get("type") or "") or None
                if isinstance(resume_type_info, dict)
                else None
            ),
        )
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
                companies_yaml_path=memo_prep.COMPANIES_FILE,
                memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
                research_dir=research_store.RESEARCH_ROOT / company_slug,
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
                            package_path
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
        research_store.RESEARCH_ROOT / company_slug,
    )
    _write_decision_record_file(
        str(report.get("company_id") or company_slug),
        research_store.RESEARCH_ROOT / company_slug,
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
                research_dir=research_store.RESEARCH_ROOT / company_slug,
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
    research_dir = research_store.RESEARCH_ROOT / company_slug
    _write_recent_news_file(
        str(report.get("company_id") or company_slug), research_dir
    )
    _write_decision_record_file(
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
            companies_yaml_path=memo_prep.COMPANIES_FILE,
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
    research_dir = research_store.RESEARCH_ROOT / company_slug

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
