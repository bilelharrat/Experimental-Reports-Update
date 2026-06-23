"""Bootstrap an investment-memo run.

This module is the synchronous handshake between
``POST /api/reports`` (with `report_type = "Investment Memo (Late-Stage)"`)
and the long-running analysis worker in ``memo_analysis.py``.

What this module does:

  1. Resolves the company against ``data/companies.yaml``.
  2. Runs the late-stage / pre-IPO scope check.
  3. Mints a versioned, non-destructive run folder under
     ``data/memos/<slug>/<YYYY-MM-DD>__<HHMMSS>__<slug>__memo-run/``.
  4. Writes a manifest skeleton at ``logs/run_manifest.md``.
  5. Creates the report record in ``data/reports/`` and emits the prep
     events on the run-folder's ``logs/stream.jsonl``.

What this module **deliberately does not do** (see `docs/architecture.md`):

  - It does **not** touch ``data/uploads/<slug>/``. That folder is the
    user's **Document Library** and is owned by a separate feature.
    The memo skill consumes ``data/settings/serena_background.md`` and
    the ``data/companies.yaml`` entry — nothing else.
  - It does **not** stage any input files for the skill. The skill
    reads its inputs itself using the tools its own text prescribes
    (``markitdown`` for PDFs, ``pandoc`` for docx, Read for images).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import job_progress, serena_analysis, storage

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMOS_ROOT = DATA_DIR / "memos"
SETTINGS_FILE = DATA_DIR / "settings" / "serena_background.md"
COMPANIES_FILE = DATA_DIR / "companies.yaml"

SKILL_NAME = "bsh-investment-memo-latestage-v1"
SKILL_VERSION = 1
JOB_KIND = "memo"
REPORT_TYPE = "Investment Memo (Late-Stage)"


class AnalysisSessionNotReadyError(ValueError):
    """Raised when a requested analysis session cannot drive memo generation."""


# --- Stage classification --------------------------------------------------

_LATE_STAGE_ROUNDS = {
    "series d", "series e", "series f", "series g", "series h", "series i",
    "series j", "series k", "late", "late-stage", "late stage", "growth",
    "pre-ipo", "pre ipo", "preipo", "secondary", "ipo",
}

_EARLY_STAGE_ROUNDS = {
    "pre-seed", "pre seed", "preseed", "seed", "angel",
    "series a", "series a-1", "series a-2", "series b", "series b-1", "series b-2",
}

_LATE_STAGE_FUNDING_FLOOR_USD = 50_000_000
_EARLY_STAGE_FUNDING_CEILING_USD = 5_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_id() -> str:
    n = _now()
    return f"{n.strftime('%Y-%m-%d')}__{n.strftime('%H%M%S')}"


def _parse_funding_usd(raw: Any) -> float | None:
    """Parse strings like '~$6.35 billion', '$420M', '500 million', '1.2B'."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    val = float(m.group(1))
    if "billion" in s or re.search(r"\bb(?:n)?\b", s):
        return val * 1_000_000_000
    if "million" in s or re.search(r"\bm(?:m)?\b", s):
        return val * 1_000_000
    if "thousand" in s or s.endswith("k"):
        return val * 1_000
    return val


def _assess_stage(company: dict) -> dict:
    """Best-effort late-stage / pre-IPO classifier.

    Returns ``{outcome, classification, reason, signals}`` where ``outcome``
    is ``pass`` (proceed), ``fail`` (hard refuse), or ``warn`` (proceed
    with a recorded scope warning).
    """
    status = (company.get("status") or "").strip().lower()
    if status == "nonprofit":
        return {
            "outcome": "fail",
            "classification": "out-of-scope",
            "reason": (
                "Company is registered as a nonprofit; this skill is scoped to "
                "for-profit late-stage / pre-IPO investments."
            ),
            "signals": ["status: nonprofit"],
        }

    signals: list[str] = []

    exchange = (company.get("exchange") or "").strip()
    if exchange:
        signals.append(f"public on {exchange}")
        return {
            "outcome": "pass",
            "classification": "public",
            "reason": (
                "Company is publicly traded; treated as in-scope (e.g. PIPE / "
                "secondary at a late-stage mark)."
            ),
            "signals": signals,
        }

    lf = company.get("latest_funding") or {}
    round_raw = (lf.get("round") or lf.get("round_name") or "").strip().lower()
    if round_raw:
        signals.append(f"latest round: {round_raw}")
        if any(k in round_raw for k in _LATE_STAGE_ROUNDS):
            return {
                "outcome": "pass",
                "classification": "late-stage",
                "reason": f"Latest funding round '{round_raw}' is late-stage / pre-IPO.",
                "signals": signals,
            }
        if any(k in round_raw for k in _EARLY_STAGE_ROUNDS):
            return {
                "outcome": "warn",
                "classification": "early-stage",
                "reason": (
                    f"Latest funding round '{round_raw}' is early-stage for the "
                    f"{SKILL_NAME} memo workflow. Proceeding as a scope-warning "
                    "exception; treat stage fit and thin late-stage diligence as "
                    "explicit caveats in the memo."
                ),
                "signals": signals,
            }

    total = _parse_funding_usd(company.get("total_funding_usd"))
    if total is not None:
        signals.append(f"total funding ~ ${total/1_000_000:.0f}M")
        if total >= _LATE_STAGE_FUNDING_FLOOR_USD:
            return {
                "outcome": "pass",
                "classification": "late-stage",
                "reason": (
                    f"Total funding (~${total/1_000_000:.0f}M) clears the "
                    f"late-stage floor (${_LATE_STAGE_FUNDING_FLOOR_USD/1_000_000:.0f}M)."
                ),
                "signals": signals,
            }
        if total < _EARLY_STAGE_FUNDING_CEILING_USD:
            return {
                "outcome": "warn",
                "classification": "early-stage",
                "reason": (
                    f"Total funding (~${total/1_000_000:.1f}M) is below the "
                    "late-stage floor. Proceeding as a scope-warning exception; "
                    "treat stage fit and thin late-stage diligence as explicit "
                    "caveats in the memo."
                ),
                "signals": signals,
            }

    signals.append("no clean stage signal in registry")
    return {
        "outcome": "warn",
        "classification": "indeterminate",
        "reason": (
            "Could not determine funding stage from the company record. Proceeding "
            "under the late-stage assumption; verify in Section II / Key Metrics."
        ),
        "signals": signals,
    }


# --- Run-folder primitives -------------------------------------------------

def _company_slug(company: dict) -> str:
    """The company id is already a slug (storage._slugify produced it)."""
    return str(company.get("id"))


def _validate_analysis_session_for_memo(
    slug: str,
    analysis_session_id: str,
    analysis_session: dict,
) -> None:
    """Accept any existing Memo Studio session as optional memo context.

    Approval and readiness gates still matter for signaling quality in the UI,
    but they no longer block memo generation. A draft packet is source material,
    not an approval stamp.
    """
    if analysis_session.get("company_id") != slug:
        raise AnalysisSessionNotReadyError(
            f"Analysis session {analysis_session_id} does not belong to {slug}."
        )


def _make_run_dir(slug: str, run_id: str) -> Path:
    base = MEMOS_ROOT / slug / f"{run_id}__{slug}__memo-run"
    folder = base
    n = 2
    while folder.exists():
        folder = base.with_name(f"{base.name}__{n}")
        n += 1
    # Subdirectories the skill writes into. Note: no `inputs/` — the skill
    # has no input-staging step. The skill reads from companies.yaml +
    # Serena_Background.md directly.
    for sub in ("analysis", "memo", "logs/previews", "logs/previews_cn"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    return folder


def stream_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / "logs" / "stream.jsonl"


# --- Manifest writers ------------------------------------------------------

def _memo_filename(company_name: str, run_id: str, language: str) -> str:
    if language == "zh":
        return f"{company_name} - 投资备忘录 - {run_id}.docx"
    return f"{company_name} - Investment Memo - {run_id}.docx"


def _internal_memo_filename(company_name: str, run_id: str, suffix: str) -> str:
    return f"{company_name} - Internal Diligence Memo - {run_id}.{suffix}"


def _rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(DATA_DIR.parent))
    except ValueError:
        return str(p)


def _write_manifest_skeleton(
    run_dir: Path,
    *,
    run_id: str,
    company: dict,
    stage: dict,
    memo_paths: dict[str, str],
    warnings: list[str],
    internal_memo_paths: dict[str, str] | None = None,
    analysis_session_id: str | None = None,
) -> Path:
    lines: list[str] = ["# Investment Memo Run Manifest", ""]
    lines.append(f"- run_id: {run_id}")
    lines.append(f"- company: {company.get('name')} ({company.get('id')})")
    lines.append(f"- skill: {SKILL_NAME}")
    lines.append(f"- skill_version: {SKILL_VERSION}")
    if analysis_session_id:
        lines.append(f"- analysis_session_id: {analysis_session_id}")
    lines.append(f"- created_at: {_now().isoformat()}")
    lines.append("- status: ready_for_analysis")
    lines.append(
        f"- stage_assessment: {stage.get('classification')} "
        f"({stage.get('outcome')})"
    )
    if stage.get("signals"):
        lines.append(f"- stage_signals: {', '.join(stage['signals'])}")
    lines += ["", "## Inputs the skill will read", ""]
    lines.append(
        "Serena's skill reads only its declared inputs. Python does not "
        "stage anything for the skill."
    )
    lines.append("")
    lines.append("- `data/settings/serena_background.md`")
    lines.append(f"- `data/companies.yaml` entry for `{company.get('id')}`")
    if warnings:
        lines += ["", "## Warnings", ""]
        for w in warnings:
            lines.append(f"- {w}")
    lines += ["", "## Predicted artifacts", ""]
    lines.append(f"- {_rel(memo_paths['en'])}")
    lines.append(f"- {_rel(memo_paths['zh'])}")
    if internal_memo_paths and internal_memo_paths.get("internal_md"):
        lines.append(f"- {_rel(internal_memo_paths['internal_md'])}")
    if internal_memo_paths and internal_memo_paths.get("internal_docx"):
        lines.append(f"- {_rel(internal_memo_paths['internal_docx'])}")
    lines += ["", "## Validation", ""]
    lines.append("- english: pending")
    lines.append("- chinese: pending")
    lines.append("- visual_qa: pending")
    lines.append("")

    path = run_dir / "logs" / "run_manifest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_scope_failure(run_dir: Path, *, company: dict, stage: dict) -> Path:
    lines = [
        "# Scope Check Failed",
        "",
        f"- company: {company.get('name')} ({company.get('id')})",
        f"- skill: {SKILL_NAME}",
        f"- assessed_at: {_now().isoformat()}",
        f"- classification: {stage.get('classification')}",
        "",
        "## Reason",
        "",
        stage.get("reason") or "(no reason given)",
        "",
        "## Signals observed",
        "",
    ]
    for s in stage.get("signals", []):
        lines.append(f"- {s}")
    lines += [
        "",
        "This skill is scoped to late-stage and pre-IPO deals. Run the "
        "early-stage memo workflow instead.",
        "",
    ]
    path = run_dir / "logs" / "scope_check.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --- Public entry ----------------------------------------------------------

def bootstrap_memo_run(
    company_id: str, *, analysis_session_id: str | None = None
) -> dict:
    """Run the synchronous prep stage for an investment-memo job.

    Returns a result dict. Hard scope failures (for example nonprofit /
    out-of-scope) mark the report ``failed_scope_check``. Early-stage
    signals are warnings: prep continues and the analysis worker receives
    the warning context. Raises ``ValueError`` for caller-facing errors
    (unknown company, missing settings).
    """
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company_id: {company_id}")
    if not SETTINGS_FILE.exists():
        raise RuntimeError(
            f"Settings file missing: {SETTINGS_FILE}. Place serena_background.md "
            "in data/settings/ before running prep."
    )

    slug = _company_slug(company)
    company_name = company.get("name") or slug
    analysis_session = None
    if analysis_session_id:
        analysis_session = serena_analysis.get_session(slug, analysis_session_id)
        if analysis_session is None:
            raise ValueError(
                f"Unknown analysis_session_id for {slug}: {analysis_session_id}"
            )
        _validate_analysis_session_for_memo(
            slug,
            analysis_session_id,
            analysis_session,
        )
        analysis_session = serena_analysis.ensure_memo_packet_current(
            analysis_session
        )

    run_id = _run_id()
    run_dir = _make_run_dir(slug, run_id)
    stream = job_progress.ProgressLog(stream_path(run_dir))
    memo_paths = {
        "en": str(run_dir / "memo" / _memo_filename(company_name, run_id, "en")),
        "zh": str(run_dir / "memo" / _memo_filename(company_name, run_id, "zh")),
    }
    internal_md = run_dir / "memo" / _internal_memo_filename(company_name, run_id, "md")
    internal_docx = run_dir / "memo" / _internal_memo_filename(company_name, run_id, "docx")

    # Mint the report record up front so the run is browseable even if
    # we fail downstream.
    report = storage.create_report(
        company_id=slug,
        report_type=REPORT_TYPE,
        audience="Internal",
        language="en",
    )
    storage.update_report(
        report["id"],
        kind="investment_memo_latestage",
        status="prepping",
        stage="Preparing run",
        run_dir=_rel(run_dir),
        memo_files=[
            {"language": "en", "path": _rel(memo_paths["en"])},
            {"language": "zh", "path": _rel(memo_paths["zh"])},
        ],
        internal_memo_files=[
            {
                "kind": "internal_diligence_memo",
                "language": "en",
                "markdown_path": _rel(internal_md),
                "path": _rel(internal_docx),
            }
        ],
        skill=SKILL_NAME,
        skill_version=SKILL_VERSION,
        run_id=run_id,
        warnings=[],
        analysis_session_id=analysis_session_id,
        analysis_session_approved=(
            bool(analysis_session.get("approved_for_memo"))
            if analysis_session
            else False
        ),
    )

    stream.emit(
        "job_init",
        kind=JOB_KIND,
        title=f"Investment memo — {company_name}",
        subtitle="Late-stage / pre-IPO",
        report_id=report["id"],
        company_id=slug,
        run_id=run_id,
        run_dir=str(run_dir),
        skill=SKILL_NAME,
    )
    stream.emit(
        "stage",
        stage="prep_started",
        message="Resolving company and preparing run folder",
    )
    stream.emit(
        "company_resolved",
        id=slug,
        name=company_name,
        ticker=company.get("ticker"),
        sector=company.get("sector"),
        hq=company.get("hq"),
        website=company.get("website"),
        status=company.get("status"),
    )
    stream.emit(
        "stage",
        stage="run_dir_created",
        message="Run folder created",
        run_dir=str(run_dir),
        memo_paths=memo_paths,
    )

    stage_assessment = _assess_stage(company)
    stream.emit(
        "stage",
        stage="scope_check",
        message=stage_assessment.get("reason"),
        outcome=stage_assessment.get("outcome"),
        classification=stage_assessment.get("classification"),
        signals=stage_assessment.get("signals", []),
    )

    if stage_assessment["outcome"] == "fail":
        _write_scope_failure(run_dir, company=company, stage=stage_assessment)
        storage.update_report(
            report["id"],
            status="failed_scope_check",
            stage="Scope check failed",
            scope_check=stage_assessment,
        )
        stream.emit(
            "error",
            error=stage_assessment.get("reason"),
            classification=stage_assessment.get("classification"),
        )
        return {
            "failed": True,
            "report_id": report["id"],
            "run_dir": str(run_dir),
            "run_dir_rel": _rel(run_dir),
            "scope_check": stage_assessment,
            "stream_path": str(stream_path(run_dir)),
        }

    warnings: list[str] = []
    if stage_assessment["outcome"] == "warn":
        warnings.append(stage_assessment.get("reason") or "Stage assessment indeterminate")

    manifest_path = _write_manifest_skeleton(
        run_dir,
        run_id=run_id,
        company=company,
        stage=stage_assessment,
        memo_paths=memo_paths,
        internal_memo_paths={
            "internal_md": str(internal_md),
            "internal_docx": str(internal_docx),
        },
        warnings=warnings,
        analysis_session_id=analysis_session_id,
    )

    storage.update_report(
        report["id"],
        status="ready_for_analysis",
        stage="Ready for analysis",
        progress=10,
        warnings=warnings,
        scope_check=stage_assessment,
    )
    prepared_report = storage.get_report(report["id"])

    stream.emit(
        "stage",
        stage="prep_complete",
        message="Prep finished — handing off to analysis worker",
        warnings=warnings,
    )

    # Hand off to the analysis worker. It re-opens the same stream.jsonl
    # in append mode and emits the real terminal `done` when both .docx
    # files land. Import locally to avoid a circular module import at
    # startup.
    from . import memo_analysis
    memo_analysis.start_analysis(report["id"])

    return {
        "failed": False,
        "report_id": report["id"],
        "company": {
            "id": slug,
            "name": company_name,
            "ticker": company.get("ticker"),
            "sector": company.get("sector"),
            "stage_classification": stage_assessment.get("classification"),
        },
        "run_dir": str(run_dir),
        "run_dir_rel": _rel(run_dir),
        "memo_paths": memo_paths,
        "manifest_path": str(manifest_path),
        "stream_path": str(stream_path(run_dir)),
        "warnings": warnings,
        "report": prepared_report,
    }
