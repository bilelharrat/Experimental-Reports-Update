"""Bootstrap an investment-memo run.

Resolves a fully-qualified company record, mints a non-destructive run
folder under ``data/memos/<slug>/<YYYY-MM-DD>__<HHMMSS>__<slug>__memo-run/``,
stages source materials from ``data/uploads/<slug>/`` as symlinks, runs a
late-stage / pre-IPO scope check (the bsh-investment-memo-latestage skill
refuses early-stage deals), and writes a run-manifest skeleton plus an
SSE-streamable progress log that surfaces in the unified Active Jobs rail.

This module is the synchronous handshake between ``POST /api/memos/prep``
and the long-running analysis composite job. Everything in the returned
``RunContext`` is contractual — the analysis layer never re-derives any
of it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import files_store, job_progress, storage

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMOS_ROOT = DATA_DIR / "memos"
SETTINGS_FILE = DATA_DIR / "settings" / "serena_background.md"

SKILL_NAME = "bsh-investment-memo-latestage-v1"
SKILL_VERSION = 1
JOB_KIND = "memo"
REPORT_TYPE = "Investment Memo (Late-Stage)"

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

# Total funding raised below which we treat the deal as early-stage absent
# any other evidence. Late-stage rounds typically come after $50M+ raised.
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
    under late-stage assumption with a recorded warning).
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
                "outcome": "fail",
                "classification": "early-stage",
                "reason": (
                    f"Latest funding round '{round_raw}' is early-stage; the "
                    f"{SKILL_NAME} skill is scoped to late-stage and pre-IPO only. "
                    "Use the early-stage memo workflow instead."
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
                "outcome": "fail",
                "classification": "early-stage",
                "reason": (
                    f"Total funding (~${total/1_000_000:.1f}M) is below the "
                    "late-stage floor; treating as early-stage and refusing the "
                    "late-stage memo skill."
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


def _make_run_dir(slug: str, run_id: str) -> Path:
    base = MEMOS_ROOT / slug / f"{run_id}__{slug}__memo-run"
    folder = base
    n = 2
    while folder.exists():
        folder = base.with_name(f"{base.name}__{n}")
        n += 1
    for sub in ("inputs", "analysis", "memo", "logs/previews", "logs/previews_cn"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    return folder


def stream_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / "logs" / "stream.jsonl"


# --- Input staging ---------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _stage_inputs(company_id: str, run_dir: Path) -> list[dict]:
    """Symlink uploaded files into ``<run_dir>/inputs/`` and return provenance."""
    out: list[dict] = []
    inputs_dir = run_dir / "inputs"
    for entry in files_store.list_files(company_id):
        rec = files_store.get_file(company_id, entry.get("id", ""))
        if rec is None:
            continue
        meta, src_path = rec
        link_name = meta.get("filename") or src_path.name
        link_path = inputs_dir / link_name
        i = 2
        while link_path.exists():
            stem, suffix = Path(link_name).stem, Path(link_name).suffix
            link_path = inputs_dir / f"{stem}__{i}{suffix}"
            i += 1
        try:
            os.symlink(os.path.abspath(src_path), link_path)
        except OSError:
            shutil.copy2(src_path, link_path)
        out.append({
            "path": str(link_path.relative_to(run_dir)),
            "original_upload_id": meta.get("id"),
            "original_path": str(src_path),
            "sha256": _sha256(src_path),
            "kind": meta.get("kind"),
            "language": meta.get("language") or "en",
            "source_class": "company-originated",
            "size_bytes": meta.get("size_bytes"),
            "uploaded_at": meta.get("uploaded_at"),
        })

    with (inputs_dir / "inputs.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)
    return out


# --- Manifest writers ------------------------------------------------------

def _memo_filename(company_name: str, run_id: str, language: str) -> str:
    if language == "zh":
        return f"{company_name} - 投资备忘录 - {run_id}.docx"
    return f"{company_name} - Investment Memo - {run_id}.docx"


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
    inputs: list[dict],
    memo_paths: dict[str, str],
    warnings: list[str],
) -> Path:
    lines: list[str] = ["# Investment Memo Run Manifest", ""]
    lines.append(f"- run_id: {run_id}")
    lines.append(f"- company: {company.get('name')} ({company.get('id')})")
    lines.append(f"- skill: {SKILL_NAME}")
    lines.append(f"- skill_version: {SKILL_VERSION}")
    lines.append(f"- created_at: {_now().isoformat()}")
    lines.append("- status: ready_for_analysis")
    lines.append(
        f"- stage_assessment: {stage.get('classification')} "
        f"({stage.get('outcome')})"
    )
    if stage.get("signals"):
        lines.append(f"- stage_signals: {', '.join(stage['signals'])}")
    lines += ["", "## Staged inputs", ""]
    if inputs:
        lines.append("| # | File | Kind | Source class | Language |")
        lines.append("|---|------|------|--------------|----------|")
        for i, item in enumerate(inputs, 1):
            lines.append(
                f"| {i} | {Path(item['path']).name} | {item.get('kind') or '?'} | "
                f"{item.get('source_class') or '?'} | {item.get('language') or '?'} |"
            )
    else:
        lines.append("_No inputs staged._")
    if warnings:
        lines += ["", "## Warnings", ""]
        for w in warnings:
            lines.append(f"- {w}")
    lines += ["", "## Predicted artifacts", ""]
    lines.append(f"- {_rel(memo_paths['en'])}")
    lines.append(f"- {_rel(memo_paths['zh'])}")
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

def bootstrap_memo_run(company_id: str) -> dict:
    """Run the synchronous prep stage for an investment-memo job.

    Returns a RunContext-shaped dict. On scope-check failure, ``failed`` is
    True, the run folder is preserved for browsing, and the report record
    is marked ``failed_scope_check``. Raises ``ValueError`` for caller-
    facing errors (unknown company, missing settings) that should surface
    as 4xx without minting a run folder.
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
    run_id = _run_id()
    run_dir = _make_run_dir(slug, run_id)
    stream = job_progress.ProgressLog(stream_path(run_dir))

    company_name = company.get("name") or slug
    memo_paths = {
        "en": str(run_dir / "memo" / _memo_filename(company_name, run_id, "en")),
        "zh": str(run_dir / "memo" / _memo_filename(company_name, run_id, "zh")),
    }

    # Mint the report record up front so the run is browseable even if we
    # fail downstream.
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
        skill=SKILL_NAME,
        skill_version=SKILL_VERSION,
        run_id=run_id,
        warnings=[],
    )

    stream.emit(
        "job_init",
        kind=JOB_KIND,
        title=f"Investment memo — {company_name}",
        subtitle="Late-stage / pre-IPO bootstrap",
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

    inputs = _stage_inputs(slug, run_dir)
    stream.emit(
        "stage",
        stage="inputs_staged",
        message=f"Staged {len(inputs)} input file(s)",
        count=len(inputs),
        files=[
            {
                "name": Path(i["path"]).name,
                "kind": i.get("kind"),
                "language": i.get("language"),
                "size_bytes": i.get("size_bytes"),
            }
            for i in inputs
        ],
    )
    if not inputs:
        warnings.append(
            "No source materials present in data/uploads/<slug>/. Late-stage "
            "analysis bar still applies — missing PitchBook / partner notes "
            "will be surfaced as a gating diligence question."
        )
        stream.emit(
            "input_warnings",
            missing=["PitchBook summary", "partner notes", "deck"],
            impact="reduces confidence; flagged as gating question",
        )

    manifest_path = _write_manifest_skeleton(
        run_dir,
        run_id=run_id,
        company=company,
        stage=stage_assessment,
        inputs=inputs,
        memo_paths=memo_paths,
        warnings=warnings,
    )

    storage.update_report(
        report["id"],
        status="ready_for_analysis",
        stage="Ready for analysis",
        progress=10,
        warnings=warnings,
        scope_check=stage_assessment,
    )

    stream.emit(
        "stage",
        stage="prep_complete",
        message="Prep finished — handing off to analysis worker",
        warnings=warnings,
    )

    # Hand off to the analysis worker. It re-opens the same stream.jsonl in
    # append mode and emits the real terminal `done` when both .docx files
    # land. Import locally to avoid a circular module import at startup.
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
        "input_paths": [str(run_dir / i["path"]) for i in inputs],
        "memo_paths": memo_paths,
        "manifest_path": str(manifest_path),
        "stream_path": str(stream_path(run_dir)),
        "warnings": warnings,
    }
