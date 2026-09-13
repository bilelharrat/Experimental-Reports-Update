"""Background worker for Buffett investment-memo generation.

Mirrors the late-stage memo handshake (run folder, stream.jsonl, bilingual
DOCX) but uses a dedicated skill and renderer. Claude writes
``logs/memo_package.json``; Python validates and renders.
"""
from __future__ import annotations

import atexit
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    buffett_memo_renderer,
    claude_runner,
    job_progress,
    memo_prep,
    research_store,
    storage,
)

logger = logging.getLogger(__name__)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RUNS: set[str] = set()


def _register_active_run(report_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS.add(report_id)


def _unregister_active_run(report_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS.discard(report_id)


def is_active(report_id: str) -> bool:
    with _ACTIVE_LOCK:
        return report_id in _ACTIVE_RUNS


@atexit.register
def _fail_active_runs_at_exit() -> None:
    with _ACTIVE_LOCK:
        active = list(_ACTIVE_RUNS)
    for report_id in active:
        try:
            report = storage.get_report(report_id)
            status = str((report or {}).get("status") or "")
            if not report or status.startswith("failed") or status == "complete":
                continue
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
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to mark Buffett memo run %s interrupted at shutdown",
                report_id,
            )


def _resolve_run_dir(report: dict) -> Path | None:
    run_dir_rel = report.get("run_dir")
    if not run_dir_rel:
        return None
    return memo_prep.DATA_DIR.parent / str(run_dir_rel)


def _memo_paths_abs(report: dict) -> dict[str, Path]:
    return {
        str(entry.get("language")): memo_prep.DATA_DIR.parent / str(entry.get("path"))
        for entry in report.get("memo_files") or []
        if entry.get("language") and entry.get("path")
    }


def _fail(
    report_id: str,
    stream: job_progress.ProgressLog,
    *,
    message: str,
    stage: str,
    phase: str,
    result: dict[str, Any] | None = None,
) -> None:
    result = result or {}
    storage.update_report(
        report_id,
        status="failed_during_analysis",
        stage=stage,
        error=message,
        failure_phase=phase,
        failure_detail=message,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit("error", error=message, phase=phase)


def _finalize_from_package(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict[str, Any],
) -> bool:
    memo_paths_abs = _memo_paths_abs(report)
    if "en" not in memo_paths_abs or "zh" not in memo_paths_abs:
        _fail(
            report_id,
            stream,
            message="Buffett memo report is missing English/Chinese output paths",
            stage="Renderer paths missing",
            phase="renderer_contract",
            result=result,
        )
        return False
    try:
        package = buffett_memo_renderer.load_package(run_dir)
        rendered = buffett_memo_renderer.render_package(
            package,
            run_dir=run_dir,
            memo_paths=memo_paths_abs,
        )
    except buffett_memo_renderer.BuffettMemoPackageError as exc:
        _fail(
            report_id,
            stream,
            message=str(exc),
            stage="Buffett memo package invalid",
            phase="renderer_contract",
            result=result,
        )
        return False

    en_ok = memo_paths_abs["en"].exists()
    zh_ok = memo_paths_abs["zh"].exists()
    if not en_ok or not zh_ok:
        missing = []
        if not en_ok:
            missing.append("English .docx")
        if not zh_ok:
            missing.append("Chinese .docx")
        _fail(
            report_id,
            stream,
            message="Renderer finished but outputs are missing: " + ", ".join(missing),
            stage="Renderer completed but outputs missing",
            phase="post_run_check",
            result=result,
        )
        return False

    decision = rendered.get("decision")
    storage.update_report(
        report_id,
        status="complete",
        stage="Memo ready",
        progress=100,
        error=None,
        failure_phase=None,
        failure_detail=None,
        artifacts_available=True,
        content=rendered.get("content_en") or "",
        content_en=rendered.get("content_en"),
        content_zh=rendered.get("content_zh"),
        decision=decision,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        cost_usd=result.get("cost_usd"),
        duration_ms=result.get("duration_ms"),
        decision=decision,
    )
    return True


def start_analysis(report_id: str) -> threading.Thread:
    t = threading.Thread(
        target=_run_safe,
        args=(report_id,),
        name=f"buffett-memo-analysis-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def start_resume(report_id: str) -> threading.Thread:
    t = threading.Thread(
        target=_resume_safe,
        args=(report_id,),
        name=f"buffett-memo-resume-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def _run_safe(report_id: str) -> None:
    # Lazy import: memo_analysis owns the shared run-slot registry and does
    # not import this module, so there is no cycle at call time.
    from . import memo_analysis

    _register_active_run(report_id)
    try:
        memo_analysis._with_run_slot(report_id, lambda: _run(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("Buffett memo analysis crashed")
        report = storage.get_report(report_id)
        if report:
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Analysis crashed",
                failure_phase="analysis",
                failure_detail="Buffett memo analysis worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Buffett memo analysis worker crashed; see server log.")
    finally:
        _unregister_active_run(report_id)


def _resume_safe(report_id: str) -> None:
    from . import memo_analysis

    _register_active_run(report_id)
    try:
        memo_analysis._with_run_slot(report_id, lambda: _resume(report_id))
    except Exception:  # noqa: BLE001
        logger.exception("Buffett memo resume crashed")
        report = storage.get_report(report_id)
        if report:
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Resume crashed",
                failure_phase="resume",
                failure_detail="Buffett memo resume worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Buffett memo resume worker crashed; see server log.")
    finally:
        _unregister_active_run(report_id)


def _run(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    if not memo_prep.is_buffett_kind(report.get("kind")):
        raise RuntimeError(f"Report {report_id} is not a Buffett investment memo")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=False)
    company_name = str(report.get("company_name") or report.get("company_id"))
    company_slug = str(report.get("company_id"))
    run_id = str(report.get("run_id") or "")
    memo_paths_abs = _memo_paths_abs(report)
    research_dir = research_store.RESEARCH_ROOT / company_slug
    if not research_dir.exists():
        research_dir = None

    storage.update_report(
        report_id,
        status="analyzing",
        stage="Running Buffett investment-memo skill",
        progress=15,
    )
    stream.emit(
        "stage",
        stage="analysis_starting",
        message="Running Buffett investment analysis and memorandum",
    )

    from . import memo_analysis as _memo_analysis

    with _memo_analysis._creeping_report_progress(
        report_id,
        floor=15,
        ceiling=78,
        stage="Running Buffett investment-memo skill",
    ):
        result = claude_runner.run_buffett_investment_memo(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            companies_yaml_path=memo_prep.COMPANIES_FILE,
            memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
            research_dir=research_dir,
            scope_check=report.get("scope_check"),
            warnings=list(report.get("warnings") or []),
            progress=stream,
            timeout_sec=3600,
        )
    if not result.get("ok"):
        message = result.get("error") or "Claude skill run failed"
        if buffett_memo_renderer.package_path(run_dir).exists():
            stream.emit(
                "stage",
                stage="claude_failed_with_package",
                message="Claude returned an error; attempting to render the package on disk",
            )
            if _finalize_from_package(
                report_id=report_id,
                report=report,
                run_dir=run_dir,
                stream=stream,
                result=result,
            ):
                return
        _fail(
            report_id,
            stream,
            message=message,
            stage="Buffett memo skill failed",
            phase="analysis",
            result=result,
        )
        return

    storage.update_report(report_id, stage="Rendering Buffett memorandum", progress=85)
    _finalize_from_package(
        report_id=report_id,
        report=report,
        run_dir=run_dir,
        stream=stream,
        result=result,
    )


def _resume(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    if not memo_prep.is_buffett_kind(report.get("kind")):
        raise RuntimeError(f"Report {report_id} is not a Buffett investment memo")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream_path = memo_prep.stream_path(run_dir)
    if stream_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = stream_path.with_name(f"stream.before_resume.{stamp}.jsonl")
        try:
            stream_path.replace(archive)
        except OSError:
            logger.exception("failed to archive Buffett memo stream before resume")

    stream = job_progress.ProgressLog(stream_path, truncate=True)
    stream.emit("stage", stage="resume_started", message="Resuming Buffett investment memo")
    storage.update_report(
        report_id,
        status="analyzing",
        stage="Resume queued",
        progress=max(int(report.get("progress") or 0), 60),
    )

    if buffett_memo_renderer.package_path(run_dir).exists():
        if _finalize_from_package(
            report_id=report_id,
            report=report,
            run_dir=run_dir,
            stream=stream,
            result={
                "cost_usd": report.get("claude_cost_usd"),
                "duration_ms": report.get("claude_duration_ms"),
            },
        ):
            return

    _run(report_id)


def recover_stale_reports() -> int:
    """Demote abandoned Buffett memo runs so they become resume-eligible."""
    recovered = 0
    for report in storage.list_reports():
        if not memo_prep.is_buffett_kind(report.get("kind")):
            continue
        status = str(report.get("status") or "")
        if status in {"complete", "failed_scope_check"} or status.startswith("failed"):
            continue
        report_id = str(report.get("id") or "")
        if not report_id or is_active(report_id):
            continue
        run_dir = _resolve_run_dir(report)
        if run_dir is None or not run_dir.exists():
            continue
        package = buffett_memo_renderer.package_path(run_dir)
        if package.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            if _finalize_from_package(
                report_id=report_id,
                report=report,
                run_dir=run_dir,
                stream=stream,
                result={
                    "cost_usd": report.get("claude_cost_usd"),
                    "duration_ms": report.get("claude_duration_ms"),
                },
            ):
                recovered += 1
                continue
        message = "orphaned by server restart"
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Analysis orphaned",
            error=message,
            failure_phase="orphaned",
            failure_detail=message,
        )
        stream = job_progress.ProgressLog(
            memo_prep.stream_path(run_dir), truncate=False
        )
        stream.emit("error", error=message, phase="orphaned", recovered=True)
        recovered += 1
    return recovered
