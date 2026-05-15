"""Background worker that runs Serena's investment-memo skill.

This worker spawns **one Claude subprocess** that executes Serena's
`bsh-investment-memo-latestage` skill verbatim. The skill itself does
all the analytical work, renders both ``.docx`` files, and finalizes
the run manifest. Python's only job here is to:

  1. Reload context from the prep stage's report record.
  2. Spawn the Claude subprocess (via ``claude_runner.run_investment_memo``).
  3. Verify the expected output files exist when Claude finishes.
  4. Update the report record + emit the terminal ``done`` / ``error``.

What this worker deliberately does **not** do (see `docs/architecture.md`):

  - Does **not** pre-extract files. The skill handles its own input
    reading.
  - Does **not** render ``.docx``. The skill does that itself via the
    docx skill (or its fallback).
  - Does **not** touch ``data/uploads/`` — that's the Document
    Library, a separate feature, not a memo input.
  - Does **not** split the skill into multiple Claude subprocesses.
    Parallelism is achieved by the skill issuing parallel tool calls
    for the 8 orthogonal passes inside its single subprocess.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from . import claude_runner, docx_pdf, job_progress, memo_prep, storage

logger = logging.getLogger(__name__)


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


def _run_safe(report_id: str) -> None:
    try:
        _run(report_id)
    except Exception:  # noqa: BLE001
        logger.exception("memo analysis crashed")
        report = storage.get_report(report_id)
        if report:
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Analysis crashed",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Analysis worker crashed; see server log.")


def _resolve_run_dir(report: dict) -> Path | None:
    run_dir_rel = report.get("run_dir")
    if not run_dir_rel:
        return None
    return memo_prep.DATA_DIR.parent / run_dir_rel


def _run(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = job_progress.ProgressLog(
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

    storage.update_report(
        report_id,
        status="analyzing",
        stage="Running BSH investment memo skill (Serena's version)",
        progress=15,
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
        progress=stream,
        timeout_sec=3600,
    )

    if not result.get("ok"):
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Claude skill run failed",
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit(
            "error",
            error=result.get("error") or "Claude skill run failed",
            phase="analysis",
        )
        return

    # --- Post-run: verify the skill produced the expected outputs -----
    en_exists = memo_paths_abs.get("en") and memo_paths_abs["en"].exists()
    zh_exists = memo_paths_abs.get("zh") and memo_paths_abs["zh"].exists()
    missing = []
    if not en_exists:
        missing.append(f"English .docx: {memo_paths_rel.get('en')}")
    if not zh_exists:
        missing.append(f"Chinese .docx: {memo_paths_rel.get('zh')}")

    if missing:
        msg = (
            "Skill finished but the expected output files are missing: "
            + "; ".join(missing)
            + ". The skill is responsible for producing these — check the "
            "tool-call trace in the run folder's stream.jsonl."
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

    # --- Render PDF previews from the .docx files --------------------
    # The .docx is the real deliverable; the PDF is a faithful rendition
    # used only for the in-app preview popup. A conversion failure must
    # NOT fail the run — we just won't offer a preview for that language.
    storage.update_report(
        report_id,
        stage="Rendering PDF previews",
        progress=95,
    )
    stream.emit("stage", stage="rendering_pdf", message="Rendering PDF previews")

    updated_memo_files: list[dict] = []
    for entry in memo_files:
        lang = entry.get("language")
        new_entry = dict(entry)
        docx_abs = memo_paths_abs.get(lang)
        if docx_abs and docx_abs.exists():
            pdf_abs = docx_abs.with_suffix(".pdf")
            ok, err = docx_pdf.convert_docx_to_pdf(docx_abs, pdf_abs)
            if ok:
                new_entry["pdf_path"] = memo_prep._rel(pdf_abs)
            else:
                logger.warning(
                    "PDF render failed for %s memo (%s): %s",
                    lang, report_id, err,
                )
                stream.emit(
                    "claude_action",
                    action="tool_result",
                    tool="docx→pdf",
                    is_error=True,
                    preview=(err or "PDF conversion failed")[:200],
                )
        updated_memo_files.append(new_entry)

    storage.update_report(report_id, memo_files=updated_memo_files)

    # The skill is supposed to update the manifest itself with an
    # "Analysis finalization" block. We do not append our own. If the
    # skill forgot, the run folder still reflects what landed on disk.

    storage.update_report(
        report_id,
        status="complete",
        stage="Memo ready",
        progress=100,
        claude_cost_usd=result.get("cost_usd"),
        claude_duration_ms=result.get("duration_ms"),
    )
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        cost_usd=result.get("cost_usd"),
        duration_ms=result.get("duration_ms"),
    )
