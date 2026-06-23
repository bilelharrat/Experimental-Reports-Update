"""Background worker that runs Serena's investment-memo skill.

This worker spawns **one Claude subprocess** that executes Serena's
`bsh-investment-memo-latestage` skill verbatim. The skill itself does
the analytical work and writes a structured memo package. Python then
invokes the tracked DOCX renderer and finalizes the run manifest. This
worker's job is to:

  1. Reload context from the prep stage's report record.
  2. Spawn the Claude subprocess (via ``claude_runner.run_investment_memo``).
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
  - Does **not** split the skill into multiple Claude subprocesses.
    Parallelism is achieved by the skill issuing parallel tool calls
    for the 8 orthogonal passes inside its single subprocess.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import (
    claude_runner,
    docx_pdf,
    internal_memo_renderer,
    job_progress,
    memo_chinese_parity,
    memo_docx_renderer,
    memo_quality_lint,
    memo_prep,
    research_store,
    serena_analysis,
    storage,
)

logger = logging.getLogger(__name__)


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


def _memo_package_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "memo_package.json"


def _block_generated_renderer_scripts(
    *,
    report_id: str,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
) -> bool:
    forbidden_scripts = memo_docx_renderer.find_generated_renderer_scripts(run_dir)
    if not forbidden_scripts:
        return False
    rel_paths = [memo_prep._rel(path) for path in forbidden_scripts]
    msg = (
        "Memo run generated bespoke renderer code instead of using "
        "server.memo_docx_renderer: "
        + "; ".join(rel_paths[:8])
    )
    storage.update_report(
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

    PDF previews are QA affordances only. A conversion failure should never
    block access to the underlying DOCX, and failed quality/parity runs should
    still expose whatever rendered memo artifacts exist.
    """
    if progress is not None:
        storage.update_report(
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

    current_report = storage.get_report(report_id) or {}
    updated_memo_files: list[dict] = []
    for entry in current_report.get("memo_files") or []:
        lang = entry.get("language")
        new_entry = dict(entry)
        docx_abs = memo_paths_abs.get(lang)
        if docx_abs and docx_abs.exists():
            existing_pdf = new_entry.get("pdf_path")
            if existing_pdf and (
                memo_prep.DATA_DIR.parent / existing_pdf
            ).exists():
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
                new_entry["pdf_path"] = memo_prep._rel(pdf_abs)
            else:
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

    storage.update_report(report_id, memo_files=updated_memo_files)
    return updated_memo_files


def _render_internal_pdf_previews(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
) -> list[dict]:
    current_report = storage.get_report(report_id) or {}
    updated_internal_files: list[dict] = []
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
                    new_entry["pdf_path"] = memo_prep._rel(pdf_abs)
                else:
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
    storage.update_report(report_id, internal_memo_files=updated_internal_files)
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
    storage.update_report(
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
        _render_memo_pdf_previews(
            report_id=report_id,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            recovered=recovered,
        )
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message=(
                "Memo package render failed: "
                f"{type(exc).__name__}: {exc}"
            ),
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
    if errors:
        _render_memo_pdf_previews(
            report_id=report_id,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            recovered=recovered,
        )
        _fail_renderer_contract(
            report_id=report_id,
            stream=stream,
            result=result,
            message="Renderer contract failed: " + "; ".join(errors),
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
) -> bool:
    storage.update_report(
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
    parity_result = memo_chinese_parity.lint_chinese_memo_pair(
        memo_paths_abs["en"],
        memo_paths_abs["zh"],
    )
    parity_path = run_dir / "logs" / "memo_chinese_parity.md"
    parity_path.write_text(
        memo_chinese_parity.render_markdown_report(parity_result),
        encoding="utf-8",
    )
    parity_payload = parity_result.to_dict()
    if parity_result.has_blocking_findings:
        msg = (
            "Generated Chinese memo failed the parity gate with "
            f"{parity_payload['p0_count']} P0 finding"
            f"{'' if parity_payload['p0_count'] == 1 else 's'}. "
            f"See {memo_prep._rel(parity_path)}."
        )
        storage.update_report(
            report_id,
            status="failed_quality_gate",
            stage="Memo failed Chinese parity gate",
            progress=89,
            error=msg,
            failure_phase="chinese_parity_gate",
            failure_detail=msg,
            artifacts_available=True,
            memo_chinese_parity=parity_payload,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        payload = {
            "error": msg,
            "phase": "chinese_parity_gate",
            "parity_report": memo_prep._rel(parity_path),
            "findings": parity_payload["findings"][:10],
        }
        if recovered:
            payload["recovered"] = True
        stream.emit(
            "thread_failed",
            thread=claude_runner.MEMO_PHASE5_THREAD,
            error=msg,
        )
        stream.emit("error", **payload)
        return False

    storage.update_report(report_id, memo_chinese_parity=parity_payload)
    return True


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
    md_path = internal_paths_abs.get("md")
    docx_path = internal_paths_abs.get("docx")
    if not md_path or not docx_path:
        _fail_internal_memo(
            report_id=report_id,
            stream=stream,
            result=result,
            message="Report record is missing internal diligence memo paths.",
        )
        return None

    storage.update_report(
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
    if not internal_result.get("ok"):
        _fail_internal_memo(
            report_id=report_id,
            stream=stream,
            result=_combined_result(result, internal_result),
            message=internal_result.get("error") or "Internal diligence memo failed.",
        )
        return None

    storage.update_report(
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
        logger.exception("internal diligence memo render failed for report %s", report_id)
        _fail_internal_memo(
            report_id=report_id,
            stream=stream,
            result=_combined_result(result, internal_result),
            message=(
                "Internal diligence memo render failed: "
                f"{type(exc).__name__}: {exc}"
            ),
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
    storage.update_report(report_id, internal_memo_files=internal_files)
    return internal_result


def _fail_internal_memo(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
    result: dict,
    message: str,
) -> None:
    storage.update_report(
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


def _fail_renderer_contract(
    *,
    report_id: str,
    stream: job_progress.ProgressLog,
    result: dict,
    message: str,
    contract: dict | None = None,
    recovered: bool = False,
) -> None:
    storage.update_report(
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


def recover_stale_reports() -> int:
    """Mark memo runs complete when Claude succeeded but finalization was lost.

    The memo skill can finish and write its structured memo package while the
    Python worker is later interrupted before rendering or finalization.
    This startup sweep is deliberately conservative: it only repairs runs
    with a successful Claude result and a renderer-valid package.
    """
    recovered = 0
    for report in storage.list_reports():
        if report.get("kind") != "investment_memo_latestage":
            continue
        if report.get("status") in ("complete", "failed_scope_check"):
            continue
        run_dir = _resolve_run_dir(report)
        if run_dir is None or not run_dir.exists():
            continue
        stream_state = _scan_memo_stream(run_dir)
        if stream_state.get("terminal") is not None:
            continue
        result = stream_state.get("success_result")
        if not result:
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
        _render_memo_pdf_previews(
            report_id=report["id"],
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            progress=86,
            recovered=True,
        )
        if not _run_chinese_parity_gate(
            report_id=report["id"],
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            result=result,
            recovered=True,
        ):
            continue
        lint_result = memo_quality_lint.lint_memo_docx(memo_paths_abs["en"])
        lint_path = run_dir / "logs" / "memo_quality_lint.md"
        lint_path.write_text(
            memo_quality_lint.render_markdown_report(lint_result),
            encoding="utf-8",
        )
        if lint_result.has_blocking_findings:
            lint_payload = lint_result.to_dict()
            msg = (
                "Recovered memo failed the DOCX quality gate with "
                f"{lint_payload['p0_count']} P0 finding"
                f"{'' if lint_payload['p0_count'] == 1 else 's'}. "
                f"See {memo_prep._rel(lint_path)}."
            )
            storage.update_report(
                report["id"],
                status="failed_quality_gate",
                stage="Memo failed quality gate",
                progress=98,
                error=msg,
                failure_phase="quality_gate",
                failure_detail=msg,
                memo_quality_lint=lint_payload,
                claude_cost_usd=result.get("cost_usd"),
                claude_duration_ms=result.get("duration_ms"),
            )
            stream.emit(
                "error",
                error=msg,
                phase="quality_gate",
                recovered=True,
                lint_report=memo_prep._rel(lint_path),
                findings=lint_payload["findings"][:10],
            )
            continue
        storage.update_report(
            report["id"],
            status="complete",
            stage="Memo ready",
            progress=100,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit(
            "done",
            report_id=report["id"],
            memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
            cost_usd=result.get("cost_usd"),
            duration_ms=result.get("duration_ms"),
            recovered=True,
        )
        recovered += 1
    return recovered


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


def _resume_safe(report_id: str) -> None:
    try:
        _resume(report_id)
    except Exception:  # noqa: BLE001
        logger.exception("memo resume crashed")
        report = storage.get_report(report_id)
        if report:
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Resume crashed",
                failure_phase="resume",
                failure_detail="Resume worker crashed; see server log.",
            )
        run_dir = _resolve_run_dir(report or {})
        if run_dir and run_dir.exists():
            stream = job_progress.ProgressLog(
                memo_prep.stream_path(run_dir), truncate=False
            )
            stream.emit("error", error="Resume worker crashed; see server log.")


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


def _archive_stream_for_resume(run_dir: Path) -> None:
    stream_path = memo_prep.stream_path(run_dir)
    if not stream_path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = stream_path.with_name(f"stream.before_resume.{stamp}.jsonl")
    try:
        stream_path.replace(archive_path)
    except OSError:
        logger.exception("failed to archive memo stream before resume: %s", stream_path)


def _finalize_memo_from_package(
    *,
    report_id: str,
    report: dict,
    run_dir: Path,
    stream: job_progress.ProgressLog,
    result: dict,
    recovered: bool = False,
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
    analysis_session_path = None
    analysis_session_id = report.get("analysis_session_id")
    if analysis_session_id:
        candidate = serena_analysis.session_dir(company_slug, str(analysis_session_id))
        if candidate.exists():
            analysis_session_path = candidate
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
            + ". Check the tool-call trace in the run folder's stream.jsonl."
        )
        storage.update_report(
            report_id,
            status="failed_during_analysis",
            stage="Skill completed but outputs missing",
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
        return False

    _render_memo_pdf_previews(
        report_id=report_id,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        progress=86,
        recovered=recovered,
    )

    if not _run_chinese_parity_gate(
        report_id=report_id,
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        result=result,
        recovered=recovered,
    ):
        return False

    storage.update_report(
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
    lint_result = memo_quality_lint.lint_memo_docx(memo_paths_abs["en"])
    lint_path = run_dir / "logs" / "memo_quality_lint.md"
    lint_path.write_text(
        memo_quality_lint.render_markdown_report(lint_result),
        encoding="utf-8",
    )
    if lint_result.has_blocking_findings:
        lint_payload = lint_result.to_dict()
        msg = (
            "Generated memo failed the DOCX quality gate with "
            f"{lint_payload['p0_count']} P0 finding"
            f"{'' if lint_payload['p0_count'] == 1 else 's'}. "
            f"See {memo_prep._rel(lint_path)}."
        )
        storage.update_report(
            report_id,
            status="failed_quality_gate",
            stage="Memo failed quality gate",
            progress=98,
            error=msg,
            failure_phase="quality_gate",
            failure_detail=msg,
            artifacts_available=True,
            memo_quality_lint=lint_payload,
            claude_cost_usd=result.get("cost_usd"),
            claude_duration_ms=result.get("duration_ms"),
        )
        stream.emit(
            "thread_failed",
            thread=claude_runner.MEMO_PHASE5_THREAD,
            error=msg,
        )
        payload = {
            "error": msg,
            "phase": "quality_gate",
            "lint_report": memo_prep._rel(lint_path),
            "findings": lint_payload["findings"][:10],
        }
        if recovered:
            payload["recovered"] = True
        stream.emit("error", **payload)
        return False
    storage.update_report(report_id, memo_quality_lint=lint_result.to_dict())
    stream.emit("thread_finished", thread=claude_runner.MEMO_PHASE5_THREAD)

    stream.emit(
        "thread_started",
        thread=claude_runner.MEMO_PHASE6_THREAD,
        title=claude_runner.MEMO_PHASE6_THREAD,
    )
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

    storage.update_report(
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
    stream.emit("thread_finished", thread=claude_runner.MEMO_PHASE6_THREAD)

    storage.update_report(
        report_id,
        status="complete",
        stage="Memo ready",
        progress=100,
        error=None,
        failure_phase=None,
        failure_detail=None,
        artifacts_available=True,
        claude_cost_usd=combined_result.get("cost_usd"),
        claude_duration_ms=combined_result.get("duration_ms"),
    )
    done_payload = {
        "report_id": report_id,
        "memo_paths": {k: str(v) for k, v in memo_paths_abs.items()},
        "internal_memo_paths": {k: str(v) for k, v in internal_paths_abs.items()},
        "cost_usd": combined_result.get("cost_usd"),
        "duration_ms": combined_result.get("duration_ms"),
    }
    if recovered:
        done_payload["recovered"] = True
    stream.emit("done", **done_payload)
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

    package_path = _memo_package_path(run_dir)
    analysis_artifacts = _analysis_artifact_paths(run_dir)
    if not package_path.exists() and not analysis_artifacts:
        raise RuntimeError(
            "Cannot resume: no memo_package.json or analysis artifacts exist"
        )

    _archive_stream_for_resume(run_dir)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=True)
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
    storage.update_report(
        report_id,
        status="analyzing",
        stage="Resuming memo from existing artifacts",
        progress=65 if not package_path.exists() else 82,
        error=None,
        failure_phase=None,
        failure_detail=None,
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
        analysis_session_path = None
        analysis_session_id = report.get("analysis_session_id")
        if analysis_session_id:
            candidate = serena_analysis.session_dir(
                company_slug,
                str(analysis_session_id),
            )
            if candidate.exists():
                analysis_session_path = candidate
        lessons_path = serena_analysis.memo_lessons_path(company_slug)
        if not lessons_path.exists():
            lessons_path = None
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
            progress=stream,
            timeout_sec=1800,
        )

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
        storage.update_report(
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
    internal_paths_abs = _internal_memo_paths_abs(report)
    analysis_session_path = None
    analysis_session_id = report.get("analysis_session_id")
    if analysis_session_id:
        candidate = serena_analysis.session_dir(company_slug, str(analysis_session_id))
        if candidate.exists():
            analysis_session_path = candidate
    lessons_path = serena_analysis.memo_lessons_path(company_slug)
    if not lessons_path.exists():
        lessons_path = None

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
        research_dir=research_store.RESEARCH_ROOT / company_slug,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=report.get("scope_check"),
        warnings=list(report.get("warnings") or []),
        progress=stream,
        timeout_sec=3600,
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
                _render_memo_pdf_previews(
                    report_id=report_id,
                    memo_paths_abs=memo_paths_abs,
                    stream=stream,
                    progress=86,
                )
                salvaged = True
            else:
                return
        storage.update_report(
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
        stream.emit(
            "error",
            error=message,
            phase="analysis",
            artifacts_available=salvaged,
        )
        return

    _finalize_memo_from_package(
        report_id=report_id,
        report=report,
        run_dir=run_dir,
        stream=stream,
        result=result,
    )
    return
