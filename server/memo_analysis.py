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
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
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


def _memo_zh_chasing_enabled() -> bool:
    """Speculative Chinese translation of English sections as they finish.

    Only meaningful when the parallel English path is on — without it there
    are no per-section English drafts to chase.
    """
    return (
        os.environ.get("BSH_MEMO_ZH_CHASING", "0") == "1"
        and os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") == "1"
    )


def _memo_fast_max_workers() -> int:
    raw = os.environ.get("BSH_MEMO_FAST_MAX_WORKERS")
    try:
        value = int(raw) if raw is not None else 8
    except ValueError:
        value = 8
    return max(1, min(value, 8))


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
            "Identify disconfirming evidence, downside sensitivity, and the "
            "specific risk or valuation sensitivities that would change the "
            "decision."
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
            lint_result = memo_quality_lint.lint_memo_docx(out_en)
            for finding in lint_result.p0_findings[:12]:
                problems.append(
                    f"quality gate {finding.code} at {finding.location}: "
                    f"\"{finding.snippet}\" — {finding.suggestion}"
                )
            if check_parity:
                parity_result = memo_chinese_parity.lint_chinese_memo_pair(
                    out_en,
                    out_zh,
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


def _surgical_quality_repair(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    candidate: dict,
    findings: list[str],
    attempt: int,
    progress,
) -> dict | None:
    """Fix quality-gate findings on a structurally valid candidate with the
    ~2-minute surgical repair pass instead of a 10-18 minute full
    regeneration.

    Quality findings are localized string defects (an em dash, a banned
    phrase, an untreated disclosure cell) — exactly what the repair pass is
    built for. Returns the repaired package only when it passes BOTH
    structural validation and a re-run of the quality gates; any other
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
    repair_result, repair_error = claude_runner.run_memo_package_structure_repair(
        run_dir=run_dir,
        company_name=company_name,
        run_id=run_id,
        package_path=input_path,
        validation_errors=findings,
        progress=progress,
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
            message="Surgical quality repair pass failed; regenerating instead",
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
            "The investment case rests on whether ZaiNar's technical moat, "
            "channel access, and contracted traction support the disclosed "
            "entry valuation on their own."
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
            "Commercial quality depends on the binding-contract share inside "
            "the $500M+ figure and the recurring economics behind Kajima. "
            "Valuation support weakens if binding contracts are only a small "
            "share or if Kajima's per-site recurring value is materially below "
            "the disclosed $10M ARR claim."
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
        "Risk And Valuation Sensitivity",
    ),
    (
        re.compile(r"\bClosing bar:\s*", re.IGNORECASE),
        "Valuation sensitivity: ",
    ),
    (
        re.compile(
            r"\bWe recommend proceeding once ([^.]+?) are confirmed\.?",
            re.IGNORECASE,
        ),
        (
            "We recommend participating in the SPV; "
            r"\1 drive the investment's valuation sensitivity."
        ),
    ),
    (
        re.compile(
            r"\bWe recommend proceeding if ([^.]+?) confirm the current "
            r"investment case\.?",
            re.IGNORECASE,
        ),
        (
            "We recommend participating in the SPV; "
            r"\1 are central to valuation support."
        ),
    ),
    (
        re.compile(
            r"\bWe recommend proceeding with a participation in ([^.]+?) "
            r"subject to the closing confirmations below\.?",
            re.IGNORECASE,
        ),
        r"We recommend participating in \1.",
    ),
    (
        re.compile(
            r"\bWe recommend proceeding with a participation in ([^.]+?) "
            r"subject to (?:the )?Valuation Sensitivity below\.?",
            re.IGNORECASE,
        ),
        r"We recommend participating in \1.",
    ),
    (
        re.compile(
            r"\bWe recommend ([^.]+?) subject to ([^.]+?)\.?",
            re.IGNORECASE,
        ),
        r"We recommend \1. \2 is a valuation sensitivity.",
    ),
    (
        re.compile(
            r"\bthe unresolved questions sit around ([^.]+?)\.",
            re.IGNORECASE,
        ),
        r"valuation sensitivity centers on \1.",
    ),
    (
        re.compile(
            r"\bWe would revisit if ([^.]+?)\.",
            re.IGNORECASE,
        ),
        r"Downside sensitivity centers on \1.",
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
            "Use as a forward round marker; final A2 lead, pre-money, and "
            "closing evidence determine whether the disclosed entry economics "
            "hold."
        ),
    ),
    (
        re.compile(r"\bConfirm before funding:\s*([^.]+)\.?", re.IGNORECASE),
        r"Valuation sensitivity: \1.",
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
            "SAFE lower-of-cap-or-discount mechanics drive the effective entry, "
            "with the 15% discount controlling at a $3.0B A2 pre-money."
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
            "inside the $500M+ figure drive valuation support."
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
        "The current entry assumes disclosed A2 lead, final pre-money, and priced-round closing economics.",
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
        "SAFE lower-of-cap-or-discount mechanics drive whether the 15% discount controls at a $3.0B A2.",
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
            "Signed-vs-MOU mix, Kajima cohort detail, and healthcare deployments "
            "with revenue attribution drive commercial-conversion sensitivity."
        ),
    ),
    (
        re.compile(
            r"\bSigned-vs-MOU split, Kajima cohort detail, and any healthcare "
            r"deployment named with revenue attribution support the base case\.?",
            re.IGNORECASE,
        ),
        (
            "Commercial-conversion support depends on signed-vs-MOU mix, "
            "Kajima cohort detail, and healthcare deployments with revenue attribution."
        ),
    ),
    (
        re.compile(
            r"\bRequire split of signed vs\. MOU; risk-weight MOU using a "
            r"15-35% conversion range for scenario work\.?",
            re.IGNORECASE,
        ),
        (
            "The signed-vs-MOU mix drives scenario value; risk-weight MOUs using "
            "a 15-35% conversion range for scenario work."
        ),
    ),
    (
        re.compile(
            r"\brequire a signed-vs-MOU split as a Valuation Sensitivity\b",
            re.IGNORECASE,
        ),
        "the signed-vs-MOU mix is a valuation sensitivity",
    ),
    (
        re.compile(
            r"\bRequire claim-scope and freedom-to-operate read versus "
            r"([^.]+?) before underwriting as multi-year monopoly\.?",
            re.IGNORECASE,
        ),
        (
            "Claim-scope and freedom-to-operate determine patent durability "
            r"versus \1."
        ),
    ),
    (
        re.compile(
            r"\bWe should confirm claim-scope and freedom-to-operate versus "
            r"([^.]+?) before treating the patent estate as a multi-year monopoly\.?",
            re.IGNORECASE,
        ),
        (
            "Claim-scope and freedom-to-operate determine patent durability "
            r"versus \1."
        ),
    ),
    (
        re.compile(
            r"\bbefore we underwrite the licensing fallback\b",
            re.IGNORECASE,
        ),
        "where the licensing fallback supports valuation",
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
            "We treat this as a credible defensive perimeter. Claim-scope and "
            r"freedom-to-operate drive licensing leverage against \1 under "
            "3GPP standardization."
        ),
    ),
    (
        re.compile(
            r"\bWe still need a claim-scope read that the sponsor implies is "
            r"covered by the IP portfolio\.?",
            re.IGNORECASE,
        ),
        "Claim-scope analysis drives patent-coverage risk.",
    ),
    (
        re.compile(r"\bwe still need\b", re.IGNORECASE),
        "Risk factor:",
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
            "Carrier sales cycles run 18 to 36 months, so this layer is a "
            "credible distribution thesis rather than a near-term revenue thesis."
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
            ". Carrier sales cycles run 18 to 36 months, so this layer is a "
            "credible distribution thesis rather than a near-term revenue thesis."
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
        "the investment case assumes",
    ),
    (
        re.compile(r"\bthe sponsor frames\b", re.IGNORECASE),
        "the investment case treats",
    ),
    (
        re.compile(r"\bthe sponsor itself flags\b", re.IGNORECASE),
        "the investment case identifies",
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
        "we recommend participating in",
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
        "used for the investment case",
    ),
    (
        re.compile(r"\bfor (?:the|this|our) memo\b", re.IGNORECASE),
        "for the investment case",
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
        "The refreshed signed-vs-MOU split supports the base scenario.",
    ),
    (
        re.compile(
            r"\bWe underwrite the displacement TAM as bounded;",
            re.IGNORECASE,
        ),
        "Our case treats the displacement TAM as bounded;",
    ),
    (
        re.compile(
            r"\bwhich is the right way to view the underwriting:\s*",
            re.IGNORECASE,
        ),
        "which supports the investment case: ",
    ),
    (
        re.compile(
            r"\bbefore underwriting derivative-tech monetization\b",
            re.IGNORECASE,
        ),
        "before giving credit to derivative-tech monetization",
    ),
    (
        re.compile(
            r"\bwe confirm the executed document before funding\.?",
            re.IGNORECASE,
        ),
        (
            "the investment case assumes the executed document confirms the "
            "conversion mechanics."
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
        "the investment case treats it as",
    ),
    (
        re.compile(
            r"\bno preference, no voting, and no information rights at the LP level\b",
            re.IGNORECASE,
        ),
        "limited direct governance, reporting, and downside preference at the LP level",
    ),
    (
        re.compile(r"\bno voting(?: rights)?\b", re.IGNORECASE),
        "limited direct governance",
    ),
    (
        re.compile(r"\binformation rights\b", re.IGNORECASE),
        "reporting access",
    ),
    (
        re.compile(r"\bvoting rights\b", re.IGNORECASE),
        "direct governance",
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
        "give credit to",
    ),
)


def _rewrite_memo_package_voice_text(text: str) -> str:
    updated = text
    for pattern, replacement in _MEMO_PACKAGE_VOICE_REWRITES:
        updated = pattern.sub(replacement, updated)
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

    storage.update_report(report_id, memo_chinese_parity=parity_payload)
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
    zh_chaser = None
    if _memo_zh_chasing_enabled():
        zh_chaser = claude_runner.BilingualChaser(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            stream=stream,
        )
    async_artifacts = None
    if claude_runner._memo_artifacts_async_enabled():
        async_artifacts = claude_runner.AsyncArtifacts(
            run_dir=run_dir,
            company_name=company_name,
            stream=stream,
        )
    phase3_cost_before = phase3_progress.cost_usd
    phase3_duration_before = phase3_progress.duration_ms
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        attempt_started_at = _now_iso()
        attempt_started = time.monotonic()
        attempt_cost_before = phase3_progress.cost_usd
        attempt_duration_before = phase3_progress.duration_ms
        if attempt > 1:
            phase3_progress.emit(
                "stage",
                stage="memo_fast_english_package_retry",
                message=(
                    "Retrying English package synthesis after a retryable "
                    f"Claude interruption (attempt {attempt}/{max_attempts})"
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
                # translations (bounded-waste rule).
                on_spine=(
                    zh_chaser.on_spine
                    if zh_chaser is not None
                    and attempt == 1
                    and not validation_feedback
                    else None
                ),
                on_section=(
                    zh_chaser.on_section
                    if zh_chaser is not None
                    and attempt == 1
                    and not validation_feedback
                    else None
                ),
                async_artifacts=async_artifacts,
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
                    validation_errors = [quality_error]
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
                    final_package_path
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
    )
    if parity_result.has_blocking_findings:
        return False
    parity_path = run_dir / "logs" / "memo_chinese_parity.md"
    parity_path.write_text(
        memo_chinese_parity.render_markdown_report(parity_result),
        encoding="utf-8",
    )

    lint_result = memo_quality_lint.lint_memo_docx(memo_paths_abs["en"])
    if lint_result.has_blocking_findings:
        return False
    lint_path = run_dir / "logs" / "memo_quality_lint.md"
    lint_path.write_text(
        memo_quality_lint.render_markdown_report(lint_result),
        encoding="utf-8",
    )

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
    names = {f"memo-analysis-{report_id}", f"memo-resume-{report_id}"}
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
    storage.update_report(
        report_id,
        status="failed_during_analysis",
        stage="Analysis orphaned",
        error=message,
        failure_phase="orphaned",
        failure_detail=message,
    )
    stream = job_progress.ProgressLog(stream_path, truncate=False)
    stream.emit("error", error=message, phase="orphaned", recovered=True)
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
        storage.update_report(report["id"], memo_quality_lint=lint_payload)
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
        storage.update_report(
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
def _fail_active_runs_at_exit() -> None:
    """Write a terminal error for in-flight memo runs on interpreter exit.

    The workers are daemon threads, so a clean shutdown (Ctrl-C, --reload,
    SIGTERM via uvicorn's handler → normal exit) kills them silently. This
    hook makes the interruption visible and resume-eligible immediately
    instead of waiting for the 30-minute orphan sweep. A SIGKILL skips
    atexit entirely — that path is covered by ``_demote_orphaned_report``.
    """
    with _ACTIVE_RUNS_LOCK:
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


def _run_safe(report_id: str) -> None:
    _register_active_run(report_id)
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
    finally:
        _unregister_active_run(report_id)


def _resume_safe(report_id: str) -> None:
    _register_active_run(report_id)
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

    final_status = "complete_with_warnings" if quality_warnings else "complete"
    final_stage = (
        "Memo ready (quality warnings)" if quality_warnings else "Memo ready"
    )
    storage.update_report(
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
