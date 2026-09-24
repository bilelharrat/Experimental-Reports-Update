"""Bootstrap an investment-memo run.

This module is the synchronous handshake between
``POST /api/reports`` (late-stage or Buffett memo types)
and the matching long-running analysis worker.

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
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, job_progress, memo_structure, serena_analysis, storage
from .company_names import clean_display_name

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMOS_ROOT = DATA_DIR / "memos"
SETTINGS_FILE = DATA_DIR / "settings" / "serena_background.md"
SEED_SETTINGS_FILE = (
    Path(__file__).resolve().parent / "seed_data" / "serena_background.md"
)
COMPANIES_FILE = DATA_DIR / "companies.yaml"

SKILL_NAME = "bsh-investment-memo-latestage-v1"
SKILL_VERSION = 1
JOB_KIND = "memo"
REPORT_TYPE = "Investment Memo (Late-Stage)"
LATESTAGE_KIND = "investment_memo_latestage"

BUFFETT_REPORT_TYPE = "Buffett Investment Memo"
BUFFETT_KIND = "buffett_investment_memo"
BUFFETT_SKILL_NAME = "bsh-buffett-investment-memo-v1"
BUFFETT_SKILL_VERSION = 1
MEMO_KINDS = frozenset({LATESTAGE_KIND, BUFFETT_KIND})

# "Investment Report (Auto)": the same late-stage pipeline and kind, but
# the stage classification is guidance, not a gate — agents determine the
# company's actual stage (early, late, post-IPO) and calibrate.
AUTO_STAGE_REPORT_TYPE = "Investment Report (Auto)"


def is_memo_kind(kind: str | None) -> bool:
    return kind in MEMO_KINDS


def is_buffett_kind(kind: str | None) -> bool:
    return kind == BUFFETT_KIND


def is_buffett_report_type(report_type: str | None) -> bool:
    return report_type == BUFFETT_REPORT_TYPE


def is_auto_stage_report_type(report_type: str | None) -> bool:
    return report_type == AUTO_STAGE_REPORT_TYPE


def is_memo_report_type(report_type: str | None) -> bool:
    return report_type in {
        REPORT_TYPE,
        BUFFETT_REPORT_TYPE,
        AUTO_STAGE_REPORT_TYPE,
    }


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Who a memo run is written for (POST /api/reports ``audience``). The LP
# offer memo is written for every audience; the internal IC decision memo
# (walk-away, kill criteria, conditions, the debate) is written alongside it
# for the firm's own readers only — never for an LP-audience run.
AUDIENCES = ("LP", "Assistant", "Partner", "Internal")
DEFAULT_AUDIENCE = "Internal"
IC_MEMO_AUDIENCES = frozenset({"Internal", "Partner", "Assistant"})

# The per-run memo template (Settings → Reports → Memo template, or the
# Generate dialog's override): "v1" is the standard late v1 memo, "v2" the
# IC template (memo_structure.active_structure(version=...)).
STRUCTURE_VERSIONS = ("v1", "v2")


def normalize_audience(audience: str | None) -> str:
    value = str(audience or "").strip()
    return value if value in AUDIENCES else DEFAULT_AUDIENCE


def _internal_diligence_memo_enabled(audience: str | None = None) -> bool:
    """Whether a run writes the internal IC decision memo.

    ``BSH_MEMO_GENERATE_INTERNAL`` set to a value is an override either way
    (1 = every run, 0 = none). Unset, the run's audience decides: Internal,
    Partner and Assistant runs get the IC memo next to the LP memo; an LP
    run gets the LP memo only."""
    raw = os.environ.get("BSH_MEMO_GENERATE_INTERNAL")
    if raw is not None and raw.strip():
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return normalize_audience(audience) in IC_MEMO_AUDIENCES


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
    # Suffixes hug the number ("$420M", "1.2B") — a \b between digit and
    # letter never matches, so test the digit-suffix shape directly.
    if "billion" in s or re.search(r"\d\s*b(?:n)?\b", s):
        return val * 1_000_000_000
    if "million" in s or re.search(r"\d\s*m(?:m)?\b", s):
        return val * 1_000_000
    if "thousand" in s or s.endswith("k"):
        return val * 1_000
    return val


def _assess_stage(company: dict, *, calibrate_only: bool = False) -> dict:
    """Best-effort late-stage / pre-IPO classifier.

    Returns ``{outcome, classification, reason, signals}`` where ``outcome``
    is ``pass`` (proceed), ``fail`` (hard refuse), or ``warn`` (proceed
    with a recorded scope warning).

    ``calibrate_only`` (the "Investment Report (Auto)" type): the
    classification is guidance rather than a stage gate — early-stage and
    indeterminate reasons become neutral calibration instructions for the
    agents. The nonprofit hard failure stays either way.
    """
    assessment = _classify_stage(company)
    if calibrate_only:
        assessment = {**assessment, "calibrate_only": True}
        # A subsidiary's reason names the security that would own it —
        # keep it; the generic calibration text is about stage alone.
        if assessment["outcome"] == "warn" and assessment.get("classification") != "subsidiary":
            classification = assessment.get("classification") or "indeterminate"
            signals = ", ".join(assessment.get("signals") or []) or "none"
            assessment["reason"] = (
                f"Stage classification: {classification} (signals: "
                f"{signals}). This report type carries no stage gate — "
                "determine the company's actual stage (early, late, or "
                "post-IPO) from the evidence and calibrate source depth, "
                "unit economics, and valuation framing to it."
            )
    return assessment


def _assess_buffett_scope(company: dict) -> dict:
    """Scope check for the Buffett-method memo: only the nonprofit hard
    failure. There is no venture stage gate — an owner's analysis judges a
    business at a price at any stage — so every other company passes, with
    the security facts (ticker, exchange, registry status, parent) recorded
    as signals. The run's prompt carries them as a "## Security" block
    instead of the late-stage "stage note"."""
    status = (company.get("status") or "").strip().lower()
    if status == "nonprofit":
        return _classify_stage(company)
    ticker = str(company.get("ticker") or "").strip()
    exchange = str(company.get("exchange") or "").strip()
    parent = str(company.get("parent_company") or company.get("parent") or "").strip()
    if status == "subsidiary":
        classification = "subsidiary"
    else:
        classification = storage.infer_company_type(company)
    signals = [f"registry status: {status or 'not recorded'}"]
    if ticker:
        signals.append(f"ticker: {ticker}")
    if exchange:
        signals.append(f"exchange: {exchange}")
    if parent:
        signals.append(f"parent: {parent}")
    return {
        "outcome": "pass",
        "classification": classification,
        "reason": (
            "Buffett-method memo: no stage gate. The memo judges the business "
            "at a price and names the security that would own it."
        ),
        "signals": signals,
    }


def _parent_name(company: dict) -> str:
    return str(company.get("parent_company") or company.get("parent") or "").strip()


def _subsidiary_security(parent: str) -> str:
    return f"parent ({parent})" if parent else "parent (unknown until researched)"


def _public_signal(company: dict) -> str:
    """Why the registry says this company is listed ("" when it does not):
    an exchange, or the registry's own public/private rule (status public,
    else a ticker) — the exchange is blank on most listed records, which
    left AMD, KO, OXY and Google "indeterminate"."""
    exchange = str(company.get("exchange") or "").strip()
    if exchange:
        return f"public on {exchange}"
    if storage.infer_company_type(company) != "public":
        return ""
    ticker = str(company.get("ticker") or "").strip()
    return f"public (ticker {ticker})" if ticker else "public (registry status)"


def classify_actionability(company: dict) -> dict:
    """What an outside investor could actually buy, from the registry alone
    (R29 A(b)): ``{kind, investable_security, parent?, ticker?, source}``.
    ``kind``: ``private_round`` | ``listed`` | ``subsidiary`` | ``nonprofit``.
    Recorded on the report next to ``scope_check`` so the UI can say
    "Listed: consider the Buffett memo" or "Subsidiary of X"."""
    status = str(company.get("status") or "").strip().lower()
    out: dict[str, Any] = {"source": "registry"}
    if status == "nonprofit":
        out.update(kind="nonprofit", investable_security="none (nonprofit)")
    elif status == "subsidiary" and not str(company.get("exchange") or "").strip():
        parent = _parent_name(company)
        out.update(kind="subsidiary", investable_security=_subsidiary_security(parent))
        if parent:
            out["parent"] = parent
    elif _public_signal(company):
        ticker = str(company.get("ticker") or "").strip()
        exchange = str(company.get("exchange") or "").strip()
        listing = " on ".join(part for part in (ticker, exchange) if part)
        out.update(
            kind="listed",
            investable_security=f"listed equity ({listing})" if listing else "listed equity",
        )
        if ticker:
            out["ticker"] = ticker
    else:
        out.update(
            kind="private_round",
            investable_security="private shares (a primary round or a secondary; terms to be confirmed)",
        )
    return out


def _classify_stage(company: dict) -> dict:
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

    if status == "subsidiary" and not str(company.get("exchange") or "").strip():
        # Nothing to buy directly: the investable security is the parent.
        # (A subsidiary with its own listing is listed: see below.)
        parent = _parent_name(company)
        security = _subsidiary_security(parent)
        signals.append("status: subsidiary")
        if parent:
            signals.append(f"parent: {parent}")
        return {
            "outcome": "warn",
            "classification": "subsidiary",
            "investable_security": security,
            "reason": (
                "Company is recorded as a subsidiary"
                + (f" of {parent}" if parent else "")
                + f"; the investable security is the {security}. Name the "
                "security that would own this business and say whether "
                "owning it is a meaningful way to own this one; do not "
                "value a round that does not exist."
            ),
            "signals": signals,
        }

    public_signal = _public_signal(company)
    if public_signal:
        signals.append(public_signal)
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
                    f"{SKILL_NAME} memo workflow. Proceeding with stage "
                    "calibration; treat source depth, unit economics, and "
                    "stage fit as valuation sensitivities."
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
                    "late-stage floor. Proceeding with stage calibration; "
                    "treat source depth, unit economics, and stage fit as "
                    "valuation sensitivities."
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


# --- Structure-stage classification ----------------------------------------
#
# Separate from the scope gate above: this picks which REPORT STRUCTURE a
# run writes (early / growth / late profiles in skills/memo/structures/),
# never whether the run proceeds. Indeterminate resolves to late — the
# richest structure, whose data-honesty rules state the gaps.

_STRUCTURE_EARLY_ROUNDS = (
    "pre-seed", "pre seed", "preseed", "seed", "angel", "series a",
)
_STRUCTURE_GROWTH_ROUNDS = ("series b", "series c")
_STRUCTURE_EARLY_FUNDING_CEILING_USD = 30_000_000
_STRUCTURE_LATE_FUNDING_FLOOR_USD = 150_000_000


def classify_company_type(company: dict) -> dict | None:
    """Phase 1 company type from the registry: the record's `vertical`
    (one of memo_structure.COMPANY_TYPE_KEYS) when set. None means the
    pipeline's tool-free classifier decides at run time."""
    if not isinstance(company, dict):
        return None
    vertical = storage._valid_vertical(company.get("vertical"))
    if not vertical:
        return None
    return {"type": vertical, "source": "registry"}


def classify_structure_stage(company: dict) -> dict:
    """Which structure profile a run should write: early, growth, or late.

    Returns ``{stage, source, signals}``. Round labels beat funding
    totals; public companies and indeterminate records are late.
    """
    signals: list[str] = []

    public_signal = _public_signal(company)
    if public_signal:
        return {
            "stage": "late",
            "source": "public listing",
            "signals": [public_signal],
        }

    lf = company.get("latest_funding") or {}
    round_raw = (lf.get("round") or lf.get("round_name") or "").strip().lower()
    if round_raw:
        signals.append(f"latest round: {round_raw}")
        if any(k in round_raw for k in _STRUCTURE_GROWTH_ROUNDS):
            return {
                "stage": "growth",
                "source": "funding round",
                "signals": signals,
            }
        if any(k in round_raw for k in _STRUCTURE_EARLY_ROUNDS):
            return {
                "stage": "early",
                "source": "funding round",
                "signals": signals,
            }
        if any(k in round_raw for k in _LATE_STAGE_ROUNDS):
            return {
                "stage": "late",
                "source": "funding round",
                "signals": signals,
            }

    total = _parse_funding_usd(company.get("total_funding_usd"))
    if total is not None:
        signals.append(f"total funding ~ ${total/1_000_000:.0f}M")
        if total >= _STRUCTURE_LATE_FUNDING_FLOOR_USD:
            return {
                "stage": "late",
                "source": "total funding",
                "signals": signals,
            }
        if total < _STRUCTURE_EARLY_FUNDING_CEILING_USD:
            return {
                "stage": "early",
                "source": "total funding",
                "signals": signals,
            }
        return {
            "stage": "growth",
            "source": "total funding",
            "signals": signals,
        }

    signals.append("no clean stage signal in registry")
    return {"stage": "late", "source": "default", "signals": signals}


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


def _make_run_dir(slug: str, run_id: str, *, run_suffix: str = "memo-run") -> Path:
    base = MEMOS_ROOT / slug / f"{run_id}__{slug}__{run_suffix}"
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

def company_display_name(company: dict | None, *, fallback: str = "") -> str:
    """The name a memo run shows for ``company``: the registry name minus
    EDGAR state/suffix tokens (" /De/", "/NEW/", …), with path separators
    and control characters replaced (``company_names.clean_display_name``).
    It feeds the prompts, the Word cover/header and ``_memo_filename``; the
    company id (the slug) is never changed."""
    record = company if isinstance(company, dict) else {}
    for raw in (record.get("name"), record.get("id"), fallback):
        cleaned = clean_display_name(raw)
        if cleaned:
            return cleaned
    return ""


# Display/file labels. The wire and storage values stay "Buffett Investment
# Memo" / "buffett_investment_memo"; only what a reader sees is renamed.
BUFFETT_FILE_LABEL = {"en": "Buffett-Method Memo", "zh": "巴菲特方法备忘录"}


def _memo_filename(
    company_name: str,
    run_id: str,
    language: str,
    *,
    buffett: bool = False,
) -> str:
    # One path component, always: an EDGAR name such as "Occidental
    # Petroleum Corp /De/" once nested the docx under a "/De/" folder.
    name = clean_display_name(company_name) or "Company"
    if buffett:
        label = BUFFETT_FILE_LABEL["zh" if language == "zh" else "en"]
        return f"{name} - {label} - {run_id}.docx"
    if language == "zh":
        return f"{name} - 投资备忘录 - {run_id}.docx"
    return f"{name} - Investment Memo - {run_id}.docx"


def _internal_memo_filename(
    company_name: str, run_id: str, suffix: str, *, language: str = "en"
) -> str:
    # One path component, like _memo_filename: an EDGAR "/De/" must never
    # nest the file under a folder.
    name = clean_display_name(company_name) or "Company"
    if language == "zh":
        return f"{name} - 投委会决策备忘录 - {run_id}.{suffix}"
    return f"{name} - Internal Diligence Memo - {run_id}.{suffix}"


def internal_memo_files_for_run(
    run_dir: Path, company_name: str, run_id: str
) -> tuple[list[dict], dict[str, str]]:
    """The IC decision memo's predicted files (English and Chinese), as the
    report's ``internal_memo_files`` entries (one per language, kind
    ``internal_diligence_memo``) and the manifest's absolute paths."""
    entries: list[dict] = []
    paths: dict[str, str] = {}
    for language in ("en", "zh"):
        md = run_dir / "memo" / _internal_memo_filename(
            company_name, run_id, "md", language=language
        )
        docx = run_dir / "memo" / _internal_memo_filename(
            company_name, run_id, "docx", language=language
        )
        entries.append(
            {
                "kind": "internal_diligence_memo",
                "language": language,
                "markdown_path": _rel(md),
                "path": _rel(docx),
            }
        )
        suffix = "" if language == "en" else f"_{language}"
        paths[f"internal_md{suffix}"] = str(md)
        paths[f"internal_docx{suffix}"] = str(docx)
    return entries, paths


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
    skill_name: str = SKILL_NAME,
    skill_version: int = SKILL_VERSION,
    title: str = "Investment Memo Run Manifest",
    include_settings: bool = True,
) -> Path:
    lines: list[str] = [f"# {title}", ""]
    lines.append(f"- run_id: {run_id}")
    lines.append(f"- company: {company.get('name')} ({company.get('id')})")
    lines.append(f"- skill: {skill_name}")
    lines.append(f"- skill_version: {skill_version}")
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
    if include_settings:
        lines.append("- `data/settings/serena_background.md`")
    lines.append(f"- `data/companies.yaml` entry for `{company.get('id')}`")
    if warnings:
        lines += ["", "## Warnings", ""]
        for w in warnings:
            lines.append(f"- {w}")
    lines += ["", "## Predicted artifacts", ""]
    lines.append(f"- {_rel(memo_paths['en'])}")
    lines.append(f"- {_rel(memo_paths['zh'])}")
    for key in ("internal_md", "internal_docx", "internal_md_zh", "internal_docx_zh"):
        if internal_memo_paths and internal_memo_paths.get(key):
            lines.append(f"- {_rel(internal_memo_paths[key])}")
    lines += ["", "## Validation", ""]
    lines.append("- english: pending")
    lines.append("- chinese: pending")
    lines.append("- visual_qa: pending")
    lines.append("")

    path = run_dir / "logs" / "run_manifest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def append_manifest_inputs(run_dir: Path, lines: list[str]) -> None:
    """Record, in ``logs/run_manifest.md``, the inputs the worker actually
    staged for the run (reference-call notes, founder updates, deal terms,
    reader flags) under the prep-time "Inputs the skill will read" list.
    Best-effort."""
    if not lines:
        return
    path = run_dir / "logs" / "run_manifest.md"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        block = "\n## Inputs staged for this run\n\n" + "\n".join(f"- {line}" for line in lines) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")
    except OSError:
        logger.warning("could not list the staged inputs in %s", path, exc_info=True)


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


def ensure_settings_file() -> Path:
    """Create ``data/settings/serena_background.md`` from the tracked seed
    when a checkout has never materialized it. Idempotent.
    """
    if SETTINGS_FILE.exists():
        return SETTINGS_FILE
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SEED_SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(
            SEED_SETTINGS_FILE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        SETTINGS_FILE.write_text(
            "# Serena Background\n\nDefault BSH late-stage memo context.\n",
            encoding="utf-8",
        )
    return SETTINGS_FILE


# --- Public entry ----------------------------------------------------------

def bootstrap_memo_run(
    company_id: str,
    *,
    analysis_session_id: str | None = None,
    report_type: str | None = None,
    memo_mode: str = "auto",
    report_mode: str = "full",
    quality: str = "best",
    engine: str | None = None,
    evidence_files: list[str] | None = None,
    trigger: str | None = None,
    auto_run_id: str | None = None,
    audience: str | None = None,
    structure_version: str | None = None,
    structure_version_source: str | None = None,
    pause_after_english: bool = False,
    cost_ceiling_usd: float | None = None,
) -> dict:
    """Run the synchronous prep stage for an investment-memo job.

    ``pause_after_english`` stops the run once its English memo is accepted
    and rendered (status ``english_ready_paused``); Resume writes the
    Chinese. ``cost_ceiling_usd`` caps this run's spend (the pipeline stops
    before the next paid phase once it is reached and delivers what is
    finished); unset, the server default applies (BSH_MEMO_COST_CEILING_USD,
    60). Both are stored on the record only when set.

    Returns a result dict. Hard scope failures (for example nonprofit /
    out-of-scope) mark the report ``failed_scope_check``. Early-stage
    signals are warnings: prep continues and the analysis worker receives
    the warning context. Raises ``ValueError`` for caller-facing errors
    (unknown company, missing settings).

    ``memo_mode="studio"`` dispatches the Memo Studio investigation worker
    (Phase 1-2 + standalone spine, then park at ``awaiting_studio``)
    instead of the full One-Click pipeline.

    ``audience`` is who the run is written for (``AUDIENCES``; unknown or
    absent → Internal). It is stored on the record and decides whether the
    internal IC decision memo is written next to the LP memo
    (``_internal_diligence_memo_enabled``).

    ``structure_version`` ("v1" | "v2") is the memo template the caller
    resolved (per-run override, Settings, or the env default) for a
    late-stage / Auto run; it is on the record BEFORE the worker starts, so
    the pipeline resolves the structure from it
    (``memo_structure.active_structure(version=...)``). Buffett runs and
    ``None`` store nothing (the pipeline then follows the env flag).
    """
    if memo_mode not in ("auto", "studio"):
        raise ValueError(f"Unknown memo_mode: {memo_mode}")
    if structure_version is not None and structure_version not in STRUCTURE_VERSIONS:
        raise ValueError(f"Unknown structure_version: {structure_version}")
    audience = normalize_audience(audience)
    # "full" is the complete IC report; "compact" prefers the stage's
    # short profile (memo_structure.active_structure resolves it, and
    # falls back to full when the stage has no compact profile yet).
    if report_mode not in ("full", "compact"):
        raise ValueError(f"Unknown report_mode: {report_mode}")
    # "best" = every agent on the CLI default model (today's behavior);
    # "balanced"/"economy" route roles to cheaper models per the tier
    # table in claude_runner (env overrides still win).
    if quality not in claude_runner.MEMO_QUALITY_LEVELS:
        raise ValueError(f"Unknown quality: {quality}")
    if cost_ceiling_usd is not None:
        try:
            cost_ceiling_usd = float(cost_ceiling_usd)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid cost_ceiling_usd: {cost_ceiling_usd!r}") from exc
        if cost_ceiling_usd <= 0:
            raise ValueError("cost_ceiling_usd must be a positive amount")
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company_id: {company_id}")
    ensure_settings_file()

    buffett = is_buffett_report_type(report_type)
    if buffett and memo_mode == "studio":
        raise ValueError(
            "Memo Studio investigation is not available for Buffett memos"
        )
    auto_stage = is_auto_stage_report_type(report_type)
    if buffett:
        selected_report_type = BUFFETT_REPORT_TYPE
    elif auto_stage:
        selected_report_type = AUTO_STAGE_REPORT_TYPE
    else:
        selected_report_type = REPORT_TYPE
    # Auto-stage keeps the late-stage KIND on purpose: the pipeline is
    # identical and every kind gate (recovery, resume, rail) stays valid.
    selected_kind = BUFFETT_KIND if buffett else LATESTAGE_KIND
    selected_skill = BUFFETT_SKILL_NAME if buffett else SKILL_NAME
    selected_skill_version = BUFFETT_SKILL_VERSION if buffett else SKILL_VERSION

    slug = _company_slug(company)
    company_name = company_display_name(company, fallback=slug) or slug
    job_title = (
        f"Buffett memo — {company_name}"
        if buffett
        else f"Investment memo — {company_name}"
    )
    if buffett:
        job_subtitle = "Owner's investment analysis"
    elif auto_stage:
        job_subtitle = "Stage-calibrated (auto)"
    else:
        job_subtitle = "Late-stage / pre-IPO"
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
    run_dir = _make_run_dir(
        slug,
        run_id,
        run_suffix="buffett-memo-run" if buffett else "memo-run",
    )
    stream = job_progress.ProgressLog(stream_path(run_dir))
    # Pinned before any phase starts, so resume and every later phase read
    # the same set of documents the analyst chose at launch.
    claude_runner.write_memo_evidence_selection(run_dir, evidence_files)
    memo_paths = {
        "en": str(
            run_dir
            / "memo"
            / _memo_filename(company_name, run_id, "en", buffett=buffett)
        ),
        "zh": str(
            run_dir
            / "memo"
            / _memo_filename(company_name, run_id, "zh", buffett=buffett)
        ),
    }
    internal_memo_files: list[dict] = []
    internal_memo_paths: dict[str, str] | None = None
    if (not buffett) and _internal_diligence_memo_enabled(audience):
        # The IC decision memo: English and Chinese from one call, each
        # rendered to its own docx (kind internal_diligence_memo, one entry
        # per language — the API exposes them as `internal` / `internal_zh`).
        internal_memo_files, internal_memo_paths = internal_memo_files_for_run(
            run_dir, company_name, run_id
        )

    # Mint the report record up front so the run is browseable even if
    # we fail downstream.
    report = storage.create_report(
        company_id=slug,
        report_type=selected_report_type,
        audience=audience,
        language="en",
    )
    storage.update_report(
        report["id"],
        kind=selected_kind,
        # The clean display name (no EDGAR " /De/" tokens) is what the
        # analysis workers put in prompts, covers and headers.
        company_name=company_name,
        status="prepping",
        stage="Preparing run",
        run_dir=_rel(run_dir),
        memo_files=[
            {"language": "en", "path": _rel(memo_paths["en"])},
            {"language": "zh", "path": _rel(memo_paths["zh"])},
        ],
        internal_memo_files=internal_memo_files,
        skill=selected_skill,
        skill_version=selected_skill_version,
        run_id=run_id,
        warnings=[],
        memo_mode=memo_mode,
        report_flavor="auto_stage" if auto_stage else None,
        analysis_session_id=analysis_session_id,
        analysis_session_approved=(
            bool(analysis_session.get("approved_for_memo"))
            if analysis_session
            else False
        ),
        # The memo template, written before any worker can read the record
        # (it used to land a moment after the worker had started, so a fast
        # worker resolved its structure without it). Late-stage / Auto only.
        **(
            {
                "structure_version": structure_version,
                "structure_version_source": structure_version_source or "request",
            }
            if structure_version and not buffett
            else {}
        ),
        # Provenance for runs launched by tracked-news auto-runs; manual
        # runs keep their record shape unchanged (no null keys).
        **({"trigger": trigger, "auto_run_id": auto_run_id} if trigger else {}),
        # Per-run pipeline controls, stored only when set (see the
        # docstring): the worker reads them from the record.
        **({"pause_after_english": True} if pause_after_english and not buffett else {}),
        **(
            {"cost_ceiling_usd": cost_ceiling_usd}
            if cost_ceiling_usd is not None and not buffett
            else {}
        ),
    )

    stream.emit(
        "job_init",
        kind=JOB_KIND,
        title=(
            f"Deep investigation — {company_name}"
            if memo_mode == "studio"
            else job_title
        ),
        subtitle=(
            "Memo Studio investigation" if memo_mode == "studio" else job_subtitle
        ),
        report_id=report["id"],
        company_id=slug,
        run_id=run_id,
        run_dir=str(run_dir),
        skill=selected_skill,
        memo_mode=memo_mode,
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

    if buffett:
        # Owner's analysis: only the nonprofit hard failure; no venture
        # stage warning reaches the Buffett prompt.
        stage_assessment = _assess_buffett_scope(company)
    else:
        stage_assessment = _assess_stage(company, calibrate_only=auto_stage)
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
            actionability=classify_actionability(company),
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

    # Stage-classification "warn" outcomes are calibration guidance for
    # the agents, not user-facing problems — the stage-aware structures
    # cover every stage, so a fuzzy registry label is not a warning. The
    # agents still read the full assessment via ``scope_check``; the UI
    # shows the evidence-confirmed "Company stage" once the run's spine
    # pins it (report.company_stage).
    warnings: list[str] = []

    manifest_path = _write_manifest_skeleton(
        run_dir,
        run_id=run_id,
        company=company,
        stage=stage_assessment,
        memo_paths=memo_paths,
        internal_memo_paths=internal_memo_paths,
        warnings=warnings,
        analysis_session_id=analysis_session_id,
        skill_name=selected_skill,
        skill_version=selected_skill_version,
        title=(
            "Buffett Investment Memo Run Manifest"
            if buffett
            else "Investment Memo Run Manifest"
        ),
        include_settings=not buffett,
    )

    # Which report structure the run writes (early/growth/late profile).
    # Only the auto type classifies; the explicit late-stage type pins
    # late. Advisory until the structure-v2 rollout flips the default —
    # memo_structure.active_structure() decides what the stage maps to.
    structure_stage = None
    if not buffett:
        if auto_stage:
            structure_stage = classify_structure_stage(company)
        else:
            structure_stage = {
                "stage": "late",
                "source": "report type",
                "signals": [f"report type: {selected_report_type}"],
            }
        stream.emit(
            "stage",
            stage="structure_stage",
            message=(
                f"Report structure stage: {structure_stage['stage']} "
                f"({structure_stage['source']})"
            ),
            structure_stage=structure_stage["stage"],
            source=structure_stage["source"],
            signals=structure_stage["signals"],
        )

    # The fund's company type, when the registry already carries it
    # (`vertical`). Otherwise the pipeline's Phase 1 thread runs the
    # classifier and publishes the result the same way.
    company_type = classify_company_type(company) if not buffett else None
    # Where the company is domiciled, for the research overlay (Chinese
    # registries, filings and press for a mainland company).
    from . import memo_inputs

    jurisdiction = memo_inputs.detect_jurisdiction(company) if not buffett else None
    if company_type is not None:
        type_label = memo_structure.COMPANY_TYPE_LABELS[company_type["type"]]["en"]
        stream.emit(
            "stage",
            stage="company_type",
            message=f"Company type: {type_label} (registry)",
            company_type=company_type["type"],
            source=company_type["source"],
        )

    storage.update_report(
        report["id"],
        status="ready_for_analysis",
        stage="Ready for analysis",
        progress=10,
        warnings=warnings,
        scope_check=stage_assessment,
        # What an outside investor could buy (listed, a subsidiary's
        # parent, a private round) — registry-based, next to the scope check.
        actionability=classify_actionability(company),
        **(
            {"structure_stage": structure_stage}
            if structure_stage is not None
            else {}
        ),
        **({"company_type": company_type} if company_type is not None else {}),
        **({"jurisdiction": jurisdiction} if jurisdiction else {}),
        **(
            {"structure_mode": report_mode}
            if not buffett and report_mode != "full"
            else {}
        ),
        **(
            {"model_quality": quality}
            if not buffett and quality != "best"
            else {}
        ),
        # Stored on the report, not just registered in memory, so a resume
        # or a repair pass after a restart runs on the engine the memo was
        # started with rather than the current default.
        **({"engine": engine} if engine and engine != "claude" else {}),
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
    if buffett:
        from . import buffett_memo_analysis
        buffett_memo_analysis.start_analysis(report["id"])
    elif memo_mode == "studio":
        from . import memo_analysis
        memo_analysis.start_investigation(report["id"])
    else:
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
