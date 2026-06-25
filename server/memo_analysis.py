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

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
import os
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
    memo_quality_lint,
    memo_prep,
    research_store,
    serena_analysis,
    storage,
)

logger = logging.getLogger(__name__)


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


def _memo_fast_max_workers() -> int:
    raw = os.environ.get("BSH_MEMO_FAST_MAX_WORKERS")
    try:
        value = int(raw) if raw is not None else 4
    except ValueError:
        value = 4
    return max(1, min(value, 8))


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

    def emit(self, type_: str, **fields: Any) -> None:
        fields.setdefault("thread", self._thread)
        if type_ == "claude_action" and fields.get("action") == "result":
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


_FAST_MEMO_PASSES: tuple[_FastMemoPassSpec, ...] = (
    _FastMemoPassSpec(
        pass_id="arithmetic_denominators",
        label="Arithmetic / pressure tests",
        artifact_filename="pressure_tests.md",
        focus=(
            "Pressure-test valuation, contract values, SAFE/SPV economics, "
            "revenue recognition, ARR/revenue proxies, unit arithmetic, and "
            "what the disclosed numbers imply. Build ranges instead of false "
            "precision."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="time_base",
        label="Time-base integrity",
        artifact_filename="time_base_checks.md",
        focus=(
            "Date-tag every valuation, round, contract, pipeline, ARR/revenue, "
            "funding, and customer metric. Separate contemporaneous, stale-mark, "
            "forward, and trailing claims."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="growth_bridge",
        label="Growth bridge",
        artifact_filename="growth_bridge.md",
        focus=(
            "Bridge disclosed commercial activity into modeled revenue or value: "
            "binding contracts, cancellable contracts, MOUs, LOIs, pipeline, "
            "conversion ranges, implementation capacity, and recognition timing."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="deployment_behavior",
        label="Adoption ladder",
        artifact_filename="adoption_ladder.md",
        focus=(
            "Assess deployment depth and adoption maturity by product/use case. "
            "Separate announced, pilot, named production, repeatable production, "
            "renewal/upsell, and broad deployment evidence."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="gtm_operating_burden",
        label="Distribution / GTM",
        artifact_filename="distribution_notes.md",
        focus=(
            "Assess distribution model, customer acquisition path, sales cycle, "
            "implementation burden, budget owner, channel leverage, carrier or "
            "enterprise access, and GTM strain."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="replacement_coexistence",
        label="Replacement vs coexistence",
        artifact_filename="replacement_vs_coexistence.md",
        focus=(
            "Determine whether the company replaces incumbents, coexists as an "
            "additive layer, licenses through incumbents, or depends on standards "
            "and ecosystem adoption."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="competitive_rights",
        label="Competitive compression",
        artifact_filename="competitive_notes.md",
        focus=(
            "Assess competitive compression, IP/patent durability, rights or "
            "standards leverage, defensibility, alternative technical approaches, "
            "and what could reduce pricing power."
        ),
    ),
    _FastMemoPassSpec(
        pass_id="alternative_explanations",
        label="Alternative explanations",
        artifact_filename="disconfirming_evidence.md",
        focus=(
            "Generate the strongest non-bullish interpretations of the facts. "
            "Identify disconfirming evidence, pass/revisit triggers, and the "
            "specific expected bars needed to change the decision."
        ),
    ),
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


def _memo_package_render_validation_error(package_path: Path) -> str | None:
    if not package_path.exists():
        return None
    try:
        memo_docx_renderer.load_package(package_path)
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    return None


def _archive_memo_package(package_path: Path, *, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = package_path.with_name(f"memo_package.{label}.{stamp}.json")
    package_path.replace(archive_path)
    return archive_path


def _archive_invalid_memo_package(package_path: Path) -> Path:
    return _archive_memo_package(package_path, label="invalid")


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

    PDF previews are QA affordances only. A conversion failure must never
    block access to the underlying DOCX, and failed quality/parity runs must
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

    storage.update_report(report_id, memo_files=updated_memo_files)
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
                "Generated Chinese memo failed the parity gate with "
                f"{parity_payload['p0_count']} P0 finding"
                f"{'' if parity_payload['p0_count'] == 1 else 's'}. "
                f"See {memo_prep._rel(parity_path)}."
            )
            timing["status"] = "failed"
            timing["error"] = msg
            failure_message = msg
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
            failure_payload = payload

    if failure_payload:
        stream.emit(
            "thread_failed",
            thread=claude_runner.MEMO_PHASE5_THREAD,
            error=failure_message,
        )
        stream.emit("error", **failure_payload)
        return False

    storage.update_report(report_id, memo_chinese_parity=parity_payload)
    return True


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
        lint_result = memo_quality_lint.lint_memo_docx(memo_path)
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
        str(data.get("summary") or "No summary returned.").strip(),
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
        lines.append("- No key findings returned.")

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
        lines.append("- No supporting evidence returned.")

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
        lines.append("- No disconfirming evidence returned.")

    lines.extend(["", "## Unresolved Expected Bars", ""])
    questions = data.get("open_questions") if isinstance(data.get("open_questions"), list) else []
    lines.extend(f"- {str(item).strip()}" for item in questions if str(item).strip())
    if not questions:
        lines.append("- No unresolved expected bars returned.")

    lines.extend(["", "## Memo Uses", ""])
    memo_uses = data.get("memo_uses") if isinstance(data.get("memo_uses"), list) else []
    lines.extend(f"- {str(item).strip()}" for item in memo_uses if str(item).strip())
    if not memo_uses:
        lines.append("- No memo-use guidance returned.")

    lines.append("")
    return "\n".join(lines)


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
    mapping = {
        "claim_register_md": "claim_register.md",
        "scenario_swim_lanes_md": "scenario_swim_lanes.md",
        "pre_mortem_md": "pre_mortem.md",
        "reverse_ic_md": "reverse_ic.md",
        "validation_log_md": "validation_log.md",
        "gating_questions_md": "gating_questions.md",
    }
    for key, filename in mapping.items():
        content = str(artifacts.get(key) or "").strip()
        if not content:
            title = filename.rsplit(".", 1)[0].replace("_", " ").title()
            content = f"# {title}\n\nNo content returned."
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
) -> _FastMemoPassResult:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    sub_progress = _ThreadProgress(stream, spec.label)
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
    try:
        data, error = claude_runner.run_memo_fast_analysis_pass(
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

    stream.emit(
        "stage",
        stage="memo_fast_pipeline_starting",
        message="Running fast memo pipeline with real parallel Claude workers",
        max_workers=_memo_fast_max_workers(),
        packet_mode=bool(analysis_session_path),
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
    stream.emit("thread_finished", thread=claude_runner._MEMO_PHASE1_THREAD)

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
        phase2_started_at = _now_iso()
        phase2_started = time.monotonic()
        stream.emit(
            "thread_started",
            thread=claude_runner._MEMO_PHASE2_THREAD,
            title=claude_runner._MEMO_PHASE2_THREAD,
        )
        stream.emit(
            "stage",
            stage="memo_fast_parallel_dispatch",
            message=f"Running {len(_FAST_MEMO_PASSES)} memo analysis passes in parallel",
            thread=claude_runner._MEMO_PHASE2_THREAD,
            passes=[spec.label for spec in _FAST_MEMO_PASSES],
            max_workers=_memo_fast_max_workers(),
        )
        _emit_phase_timing(
            stream,
            phase="memo_fast_parallel_analysis",
            status="started",
            started_at=phase2_started_at,
            started_monotonic=phase2_started,
        )
        worker_count = min(_memo_fast_max_workers(), len(_FAST_MEMO_PASSES))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            pass_results = list(
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
                    ),
                    _FAST_MEMO_PASSES,
                )
            )
        cost_usd += sum(result.cost_usd for result in pass_results)
        worker_duration_ms += sum(result.duration_ms for result in pass_results)
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
            message = "All fast memo analysis passes failed."
            storage.update_report(
                report_id,
                status="failed_during_analysis",
                stage="Fast memo analysis failed",
                failure_phase="fast_parallel_analysis",
                failure_detail=message,
                error=message,
            )
            stream.emit("error", error=message, phase="fast_parallel_analysis")
            return {"ok": False, "error": message, "cost_usd": cost_usd}

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
    english_result, english_error = claude_runner.run_memo_fast_english_package(
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
    )
    if english_error or not isinstance(english_result, dict):
        message = english_error or "English package pass returned no data."
        phase3_progress.emit("thread_failed", error=message)
        _emit_phase_timing(
            stream,
            phase="memo_fast_english_package",
            status="failed",
            started_at=phase3_started_at,
            started_monotonic=phase3_started,
            error=message,
        )
        return {"ok": False, "error": message, "cost_usd": cost_usd}
    cost_usd += _as_float(english_result.get("claude_cost_usd")) or phase3_progress.cost_usd
    worker_duration_ms += _as_int(english_result.get("claude_duration_ms")) or phase3_progress.duration_ms
    artifacts = english_result.get("analysis_artifacts")
    if isinstance(artifacts, dict):
        _write_fast_synthesis_artifacts(run_dir, artifacts)
    english_package = english_result.get("memo_package")
    if not isinstance(english_package, dict):
        message = "English package pass did not return memo_package."
        phase3_progress.emit("thread_failed", error=message)
        return {"ok": False, "error": message, "cost_usd": cost_usd}
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
        cost_usd=_as_float(english_result.get("claude_cost_usd")),
        claude_duration_ms=_as_int(english_result.get("claude_duration_ms")),
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
    bilingual_result, bilingual_error = claude_runner.run_memo_fast_bilingual_package(
        run_dir=run_dir,
        company_name=company_name,
        run_id=run_id,
        english_package_path=english_package_path,
        progress=phase4_progress,
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
        _maybe_render_memo_pdf_previews(
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
        lint_result, lint_path = _lint_memo_quality_gate(
            run_dir=run_dir,
            memo_paths_abs=memo_paths_abs,
            stream=stream,
            recovered=True,
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
    storage.update_report(
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
        storage.update_report(
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
        return False

    _maybe_render_memo_pdf_previews(
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
    lint_result, lint_path = _lint_memo_quality_gate(
        run_dir=run_dir,
        memo_paths_abs=memo_paths_abs,
        stream=stream,
        recovered=recovered,
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

    storage.update_report(
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
        claude_cost_usd=combined_result.get("cost_usd"),
        claude_duration_ms=combined_result.get("duration_ms"),
    )
    done_payload = {
        "report_id": report_id,
        "memo_paths": {k: str(v) for k, v in memo_paths_abs.items()},
        "cost_usd": combined_result.get("cost_usd"),
        "duration_ms": combined_result.get("duration_ms"),
    }
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
    quality_failed = (
        report.get("status") == "failed_quality_gate"
        or report.get("failure_phase") == "quality_gate"
        or report.get("resume_from_status") == "failed_quality_gate"
        or report.get("resume_from_failure_phase") == "quality_gate"
    )
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    prior_package_path = _latest_archived_memo_package(
        run_dir,
        label="quality_failed",
    )
    quality_failed = quality_failed or (
        quality_lint_path.exists() and prior_package_path is not None
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

    if quality_failed and package_path.exists():
        if not analysis_artifacts:
            message = (
                "Previous memo failed the DOCX quality gate, but no analysis "
                "artifacts are available to regenerate the memo package."
            )
            storage.update_report(
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
        storage.update_report(
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
                storage.update_report(
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
            storage.update_report(
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
        analysis_session_path = _analysis_session_path_for_report(company_slug, report)
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
            quality_lint_path=quality_lint_path if quality_lint_path.exists() else None,
            prior_package_path=prior_package_path,
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

    storage.update_report(
        report_id,
        status="analyzing",
        stage="Running BSH investment memo skill (Serena's version)",
        progress=15,
    )

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

    _finalize_memo_from_package(
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
    return
