"""Background worker that runs the Hormuz V3 appendix skill.

Spawns one Claude subprocess that executes ``bsh_hormuz_appendix.md``
verbatim against the target-date (and previous-date) source reports. The
skill writes four files into the run folder — CN/EN Markdown + their
PDFs. Python only: reload context, spawn the subprocess, verify the four
outputs exist, finalize the report record. Mirrors ``memo_analysis``.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from . import claude_runner, hormuz_store, job_progress, hormuz_prep, storage

logger = logging.getLogger(__name__)


def start_analysis(report_id: str) -> threading.Thread:
    t = threading.Thread(
        target=_run_safe,
        args=(report_id,),
        name=f"hormuz-appendix-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def _run_safe(report_id: str) -> None:
    try:
        _run(report_id)
    except Exception:  # noqa: BLE001
        logger.exception("hormuz appendix worker crashed")
        report = storage.get_report(report_id)
        if report:
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Appendix worker crashed",
            )
            run_dir = _resolve_run_dir(report)
            if run_dir and run_dir.exists():
                stream = job_progress.ProgressLog(
                    hormuz_prep.stream_path(run_dir), truncate=False
                )
                stream.emit(
                    "error", error="Appendix worker crashed; see server log."
                )


def _resolve_run_dir(report: dict) -> Path | None:
    rel = report.get("run_dir")
    if not rel:
        return None
    return hormuz_store.REPO_ROOT / rel


def _run(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = job_progress.ProgressLog(
        hormuz_prep.stream_path(run_dir), truncate=False
    )

    target_date = str(report.get("target_date"))
    prev_date = report.get("previous_date")
    date_range = str(report.get("date_range") or target_date)
    cn_base, en_base = hormuz_store.output_basenames(target_date)

    src_abs = [
        hormuz_store.REPO_ROOT / p for p in (report.get("source_files") or [])
    ]
    prev_abs = [
        hormuz_store.REPO_ROOT / p
        for p in (report.get("previous_source_files") or [])
    ]

    result = claude_runner.run_hormuz_appendix(
        run_dir=run_dir,
        target_date=target_date,
        previous_date=prev_date,
        date_range=date_range,
        source_paths=[str(p) for p in src_abs],
        previous_source_paths=[str(p) for p in prev_abs],
        sources_root=str(hormuz_store.SOURCES_ROOT),
        output_basename_cn=cn_base,
        output_basename_en=en_base,
        progress=stream,
        timeout_sec=3600,
    )

    if not result.get("ok"):
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Appendix skill run failed",
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit(
            "error",
            error=result.get("error") or "Appendix skill run failed",
            phase="analysis",
        )
        return

    # Verify the four expected outputs landed.
    out = hormuz_store.appendix_output_paths(target_date)
    missing = [k for k, v in out.items() if not v.exists()]
    if missing:
        label = {
            "cn_md": "Chinese .md",
            "cn_pdf": "Chinese .pdf",
            "en_md": "English .md",
            "en_pdf": "English .pdf",
        }
        msg = (
            "Skill finished but expected output files are missing: "
            + "; ".join(label[k] for k in missing)
            + ". Check the tool-call trace in logs/stream.jsonl."
        )
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Skill completed but outputs missing",
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit("error", error=msg, phase="post_run_check")
        return

    storage.update_report(
        report_id,
        status="complete",
        stage="Appendix ready",
        progress=100,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit(
        "done",
        report_id=report_id,
        target_date=target_date,
        appendix_files={k: hormuz_store._rel(v) for k, v in out.items()},
        cost_usd=result.get("cost_usd"),
        duration_ms=result.get("duration_ms"),
    )
