"""Background worker that runs the investment-memo analysis composite.

Sequence (one worker per memo run):

    1. Prep already produced run_dir + inputs/ symlinks + manifest skeleton
       + a stream.jsonl with prep events. We continue appending to the same
       stream so the unified rail sees one logical job from start to finish.

    2. Call claude_runner.run_investment_memo() — single long Claude
       invocation that writes all analysis/*.md artifacts plus
       memo/memo_structured_{en,zh}.json and memo/memo_*.md drafts.

    3. Load the two structured JSONs, render both .docx files via
       memo_renderer.render_pair(), then run memo_renderer.validate_rendered()
       on each.

    4. Append validation results to logs/run_manifest.md, write
       logs/validation.txt and logs/validation_cn.txt, and update the
       report record's status (`complete` or `failed_*`).

    5. Emit a terminal `done` (or `error`) on the stream.

Failures at any step are non-destructive: the run folder and its prep
artifacts stay intact and remain browseable in the sidebar with the
appropriate failed-status badge.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import yaml

from . import claude_runner, job_progress, memo_prep, memo_renderer, storage

logger = logging.getLogger(__name__)


def start_analysis(report_id: str) -> threading.Thread:
    """Kick off the analysis composite in a daemon thread. Returns the thread."""
    t = threading.Thread(
        target=_run_analysis_safe,
        args=(report_id,),
        name=f"memo-analysis-{report_id}",
        daemon=True,
    )
    t.start()
    return t


def _run_analysis_safe(report_id: str) -> None:
    try:
        _run_analysis(report_id)
    except Exception:  # noqa: BLE001
        logger.exception("memo analysis crashed")
        # Best-effort failure marker; the stream may already have closed.
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


def _run_analysis(report_id: str) -> None:
    report = storage.get_report(report_id)
    if report is None:
        raise RuntimeError(f"Unknown report: {report_id}")
    run_dir = _resolve_run_dir(report)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError(f"Run folder missing for report {report_id}")

    stream = job_progress.ProgressLog(
        memo_prep.stream_path(run_dir), truncate=False
    )

    # --- 1. Pull RunContext-equivalent from the run folder. -------------
    company_name = report.get("company_name") or report.get("company_id")
    company_slug = report.get("company_id")
    run_id = report.get("run_id")
    memo_files = report.get("memo_files") or []
    memo_paths_rel = {f["language"]: f["path"] for f in memo_files}
    memo_paths_abs = {
        lang: memo_prep.DATA_DIR.parent / rel for lang, rel in memo_paths_rel.items()
    }
    inputs_yaml = run_dir / "inputs" / "inputs.yaml"
    if inputs_yaml.exists():
        inputs = yaml.safe_load(inputs_yaml.read_text(encoding="utf-8")) or []
    else:
        inputs = []

    storage.update_report(
        report_id,
        status="analyzing",
        stage="Running falsification-first analysis",
        progress=20,
    )

    # --- 2. Long Claude invocation -------------------------------------
    claude_result = claude_runner.run_investment_memo(
        run_dir=run_dir,
        company_name=str(company_name or ""),
        company_slug=str(company_slug or ""),
        run_id=str(run_id or ""),
        settings_path=memo_prep.SETTINGS_FILE,
        inputs=inputs,
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        progress=stream,
        timeout_sec=3600,
    )
    if not claude_result.get("ok"):
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Claude analysis failed",
        )
        stream.emit(
            "error",
            error=claude_result.get("error") or "Claude analysis failed",
            phase="analysis",
        )
        return

    storage.update_report(
        report_id,
        status="rendering",
        stage="Rendering English + Chinese .docx",
        progress=80,
    )
    stream.emit("stage", stage="rendering", message="Rendering .docx files")

    # --- 3. Render both .docx files from the structured JSONs ----------
    structured_en_path = run_dir / "memo" / "memo_structured_en.json"
    structured_zh_path = run_dir / "memo" / "memo_structured_zh.json"
    if not structured_en_path.exists() or not structured_zh_path.exists():
        msg = (
            "Claude finished but did not produce the structured JSONs: "
            f"en={'ok' if structured_en_path.exists() else 'missing'}, "
            f"zh={'ok' if structured_zh_path.exists() else 'missing'}"
        )
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Structured output missing",
        )
        stream.emit("error", error=msg, phase="rendering")
        return

    try:
        structured_en = json.loads(structured_en_path.read_text(encoding="utf-8"))
        structured_zh = json.loads(structured_zh_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Structured output malformed",
        )
        stream.emit(
            "error", error=f"memo_structured_*.json malformed: {exc}", phase="rendering"
        )
        return

    try:
        memo_renderer.render_pair(
            structured_en,
            structured_zh,
            en_path=memo_paths_abs["en"],
            zh_path=memo_paths_abs["zh"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("renderer crashed")
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Renderer crashed",
        )
        stream.emit(
            "error",
            error=f"Renderer crashed: {type(exc).__name__}: {exc}",
            phase="rendering",
        )
        return

    stream.emit(
        "stage",
        stage="rendered",
        message="Both .docx files rendered",
        files=[str(p) for p in memo_paths_abs.values()],
    )

    # --- 4. Validate rendered output -----------------------------------
    storage.update_report(
        report_id,
        status="validating",
        stage="Validating rendered .docx",
        progress=92,
    )
    val_en = memo_renderer.validate_rendered(memo_paths_abs["en"])
    val_zh = memo_renderer.validate_rendered(memo_paths_abs["zh"])
    (run_dir / "logs" / "validation.txt").write_text(
        _format_validation(val_en, "English"), encoding="utf-8"
    )
    (run_dir / "logs" / "validation_cn.txt").write_text(
        _format_validation(val_zh, "Simplified Chinese"), encoding="utf-8"
    )
    stream.emit(
        "stage",
        stage="validation_done",
        message="Validation complete",
        en=val_en,
        zh=val_zh,
    )

    # --- 5. Update manifest + finalize --------------------------------
    _append_manifest_summary(
        run_dir,
        claude_result=claude_result,
        val_en=val_en,
        val_zh=val_zh,
        memo_paths_rel=memo_paths_rel,
    )

    ok = val_en["ok"] and val_zh["ok"]
    preview_en = _exec_summary_preview(structured_en, language="en")
    preview_zh = _exec_summary_preview(structured_zh, language="zh")
    storage.update_report(
        report_id,
        status="complete" if ok else "complete_with_warnings",
        stage="Memo ready",
        progress=100,
        content=preview_en,        # back-compat default for the legacy field
        content_en=preview_en,
        content_zh=preview_zh,
        validation={"en": val_en, "zh": val_zh},
        claude_cost_usd=claude_result.get("cost_usd"),
        claude_duration_ms=claude_result.get("duration_ms"),
    )
    stream.emit(
        "done",
        report_id=report_id,
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        validation={"en": val_en, "zh": val_zh},
        cost_usd=claude_result.get("cost_usd"),
        duration_ms=claude_result.get("duration_ms"),
    )


# --- Helpers --------------------------------------------------------------

def _format_validation(result: dict, label: str) -> str:
    lines = [f"# Validation — {label}", ""]
    lines.append(f"- ok: {result.get('ok')}")
    checks = result.get("checks") or {}
    for k, v in checks.items():
        lines.append(f"- {k}: {v}")
    errors = result.get("errors") or []
    if errors:
        lines.append("")
        lines.append("## Errors")
        for e in errors:
            lines.append(f"- {e}")
    lines.append("")
    return "\n".join(lines)


def _append_manifest_summary(
    run_dir: Path,
    *,
    claude_result: dict,
    val_en: dict,
    val_zh: dict,
    memo_paths_rel: dict[str, str],
) -> None:
    """Append a finalization block to logs/run_manifest.md."""
    manifest = run_dir / "logs" / "run_manifest.md"
    block = ["", "## Analysis finalization", ""]
    block.append(f"- cost_usd: {claude_result.get('cost_usd')}")
    block.append(f"- duration_ms: {claude_result.get('duration_ms')}")
    block.append("- artifacts:")
    for p in memo_paths_rel.values():
        block.append(f"  - {p}")
    block.append("- validation:")
    block.append(f"  - english: ok={val_en.get('ok')}, checks={val_en.get('checks')}")
    block.append(f"  - chinese: ok={val_zh.get('ok')}, checks={val_zh.get('checks')}")
    for e in (val_en.get("errors") or []):
        block.append(f"  - english_error: {e}")
    for e in (val_zh.get("errors") or []):
        block.append(f"  - chinese_error: {e}")
    block.append("")
    with manifest.open("a", encoding="utf-8") as f:
        f.write("\n".join(block))


_PREVIEW_LABELS = {
    "en": {
        "recommendation": "Recommendation",
        "opportunity": "## Opportunity",
        "top3": "## Top 3 Gating Questions",
        "footer": (
            "*(See the rendered .docx files for the full memo. This panel "
            "shows a one-screen preview.)*"
        ),
    },
    "zh": {
        "recommendation": "投资建议",
        "opportunity": "## 投资机会",
        "top3": "## 三大核心决策问题",
        "footer": (
            "*（完整备忘录请下载 .docx 文件查看。此处仅显示一屏预览。）*"
        ),
    },
}


def _exec_summary_preview(structured: dict, *, language: str = "en") -> str:
    """Build a short markdown preview shown in the report panel."""
    es = (structured or {}).get("executive_summary") or {}
    rec = es.get("investment_recommendation") or {}
    opp = es.get("investment_opportunity") or {}
    oq = es.get("open_questions") or {}
    labels = _PREVIEW_LABELS.get(language, _PREVIEW_LABELS["en"])

    parts: list[str] = []
    parts.append(
        f"# {(structured.get('cover') or {}).get('company_display_name') or 'Investment Memo'}"
    )
    if rec.get("verdict"):
        parts.append(f"**{labels['recommendation']}:** {rec['verdict']}")
    if rec.get("logic"):
        parts.append(rec["logic"])
    if opp.get("narrative"):
        parts.append(labels["opportunity"])
        parts.append(opp["narrative"])
    questions = oq.get("top_3_gating_questions") or []
    if questions:
        parts.append(labels["top3"])
        for q in questions:
            parts.append(f"- {q}")
    parts.append("")
    parts.append(labels["footer"])
    return "\n\n".join(parts)
