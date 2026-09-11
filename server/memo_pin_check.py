"""Deterministic pin-echo checker for the parallel English memo path.

The spine-lite design keeps five concurrently-written sections consistent by
pinning the facts they must agree on (recommendation sentence, key metrics,
scenarios, rated risk list) and ordering every section worker to repeat them
exactly. This module verifies that contract *mechanically* after assembly:
because the facts were agreed before writing, consistency checking needs no
judgment — just string presence — so it costs milliseconds, not an agent.

It is also the safety net the speculative-execution levers stand on
(speculative spine, early section starts): any speculation that quietly
drifted from the pins surfaces here instead of in the finished memo.

Checks are deliberately conservative: they flag only a pin that cannot be
found under generous normalization, never style. False negatives are
acceptable; false positives cost an 8-minute repair round and are not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from server import memo_structure

_SECTION_EXEC = memo_structure.LATE.section_for_role("exec").id
_SECTION_RISK = memo_structure.LATE.section_for_role("risk").id
_SECTION_FINANCE = memo_structure.LATE.section_for_role("valuation").id

_SKIPPABLE_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "not disclosed",
    "not computable",
    "-",
    "—",
    "tbd",
}

_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "or",
    "for",
    "on",
    "with",
    "is",
    "are",
    "at",
    "by",
    "from",
    "risk",
}

_NUMBER_TOKEN_RE = re.compile(r"\$?\d[\d,.]*[a-z%]*", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class PinFinding:
    code: str
    location: str
    pin: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "location": self.location,
            "pin": self.pin,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PinCheckResult:
    findings: list[PinFinding] = field(default_factory=list)
    pins_checked: int = 0
    pins_skipped: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "pins_checked": self.pins_checked,
            "pins_skipped": self.pins_skipped,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def summary_lines(self) -> list[str]:
        """Findings as feedback strings.

        Shaped like the quality-gate findings so they can flow into the
        surgical-repair path: each names the owning section with a
        ``section <id>`` token where one exists, which the error→section
        mapper resolves.
        """
        return [
            f"pin check {finding.code} in section {finding.location}: "
            f"{finding.detail}"
            if finding.location != "package"
            else f"pin check {finding.code}: {finding.detail}"
            for finding in self.findings
        ]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def _squash(text: str) -> str:
    """Aggressive variant for number matching: drop commas and spaces so
    "70,000" matches "70000" and "1.9 T" matches "1.9T"."""
    return _norm(text).replace(",", "").replace(" ", "")


def _iter_en_strings(value):
    if isinstance(value, dict):
        en = value.get("en")
        if isinstance(en, str):
            yield en
            return
        for item in value.values():
            yield from _iter_en_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_en_strings(item)
    elif isinstance(value, str):
        yield value


def _section_text(package: dict, section_id: str) -> str:
    for section in package.get("sections") or []:
        if isinstance(section, dict) and section.get("id") == section_id:
            return " \n ".join(_iter_en_strings(section))
    return ""


def _package_text(package: dict) -> str:
    return " \n ".join(_iter_en_strings(package))


def _contains(haystack_norm: str, haystack_squashed: str, needle: str) -> bool:
    needle_norm = _norm(needle)
    if not needle_norm:
        return True
    if needle_norm in haystack_norm:
        return True
    return _squash(needle) in haystack_squashed


def _significant_tokens(text: str) -> list[str]:
    return [
        token
        for token in _WORD_RE.findall(_norm(text))
        if len(token) > 2 and token not in _STOPWORDS
    ]


def check_package_pins(package: dict, shared_facts: dict) -> PinCheckResult:
    """Verify the assembled package echoes every pinned shared fact."""
    findings: list[PinFinding] = []
    pins_checked = 0
    pins_skipped = 0

    package_norm = _norm(_package_text(package))
    package_squashed = _squash(_package_text(package))
    exec_text = _section_text(package, _SECTION_EXEC)
    exec_norm, exec_squashed = _norm(exec_text), _squash(exec_text)
    risk_text = _section_text(package, _SECTION_RISK)
    risk_norm, risk_squashed = _norm(risk_text), _squash(risk_text)
    finance_text = _section_text(package, _SECTION_FINANCE)
    finance_norm = _norm(finance_text)
    finance_squashed = _squash(finance_text)

    # 1. The recommendation sentence must appear verbatim in the executive
    #    summary (the section spec says "exactly as the spine brief fixes
    #    it"). Tolerate only a trailing-period difference.
    recommendation = str(
        shared_facts.get("recommendation_sentence") or ""
    ).strip()
    if recommendation:
        pins_checked += 1
        candidate = recommendation.rstrip(".")
        if not _contains(exec_norm, exec_squashed, candidate):
            findings.append(
                PinFinding(
                    code="recommendation_not_echoed",
                    location=_SECTION_EXEC,
                    pin=recommendation,
                    detail=(
                        "the pinned recommendation sentence "
                        f'"{recommendation}" does not appear verbatim in the '
                        "executive summary — repeat it exactly as pinned"
                    ),
                )
            )

    # 1b. The decision-history pin (what BSH previously decided, factual
    #     history) gets the same verbatim-echo treatment, but only when the
    #     spine set it — absent pin means no check, so legacy runs and
    #     companies without a decision record are untouched.
    decision_history = str(
        shared_facts.get("decision_history_sentence") or ""
    ).strip()
    if decision_history:
        pins_checked += 1
        candidate = decision_history.rstrip(".")
        if not _contains(exec_norm, exec_squashed, candidate):
            findings.append(
                PinFinding(
                    code="decision_history_not_echoed",
                    location=_SECTION_EXEC,
                    pin=decision_history,
                    detail=(
                        "the pinned decision-history sentence "
                        f'"{decision_history}" does not appear verbatim in '
                        "the executive summary — repeat it exactly as pinned"
                    ),
                )
            )

    # 2. Every checkable pinned metric value must appear somewhere in the
    #    package. Short values match verbatim; spines also legally pack
    #    treatment prose into `value` ("~$24M; treated as a revenue
    #    proxy…"), which sections echo by number rather than verbatim
    #    (observed live 2026-08-28: nine such false positives, every number
    #    present) — so the fallback matches the value's numeric tokens and
    #    flags only when most are missing. A prose value with no numbers is
    #    uncheckable and skipped.
    for metric in shared_facts.get("key_metrics") or []:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name") or "").strip()
        value = str(metric.get("value") or "").strip()
        if len(value) < 2 or _norm(value) in _SKIPPABLE_VALUES:
            pins_skipped += 1
            continue
        if _contains(package_norm, package_squashed, value):
            pins_checked += 1
            continue
        numbers = _NUMBER_TOKEN_RE.findall(value)
        if not numbers:
            pins_skipped += 1
            continue
        pins_checked += 1
        missing = [
            number
            for number in numbers
            if _squash(number) not in package_squashed
            and _norm(number) not in package_norm
        ]
        if len(missing) * 2 > len(numbers):
            findings.append(
                PinFinding(
                    code="metric_value_missing",
                    location="package",
                    pin=f"{name}: {value}",
                    detail=(
                        f'pinned metric "{name}" numbers '
                        f"({', '.join(missing)}) do not appear anywhere in "
                        "the package — repeat the pinned values exactly"
                    ),
                )
            )

    # 3. Every pinned risk rating must appear in the risk section; when the
    #    rating is present, the risk's summary should be recognizably there
    #    too (majority of its significant words).
    for risk in shared_facts.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        summary = str(risk.get("summary") or "").strip()
        rating = str(risk.get("rating") or "").strip()
        if not rating:
            pins_skipped += 1
            continue
        pins_checked += 1
        if not _contains(risk_norm, risk_squashed, rating):
            findings.append(
                PinFinding(
                    code="risk_rating_missing",
                    location=_SECTION_RISK,
                    pin=f"{summary} — {rating}",
                    detail=(
                        f'pinned risk "{summary}" with rating {rating} has '
                        "no matching rating in the risk section — use "
                        "exactly the pinned risk list and ratings"
                    ),
                )
            )
            continue
        tokens = _significant_tokens(summary)
        if tokens:
            present = sum(1 for token in tokens if token in risk_norm)
            if present * 2 < len(tokens):
                findings.append(
                    PinFinding(
                        code="risk_summary_weak",
                        location=_SECTION_RISK,
                        pin=f"{summary} — {rating}",
                        detail=(
                            f'pinned risk "{summary}" ({rating}) is not '
                            "recognizable in the risk section — keep the "
                            "pinned risk summaries"
                        ),
                    )
                )

    # 4. Each pinned scenario line's numbers should appear in the financial
    #    section (majority of its numeric tokens, since prose may reflow).
    scenarios = shared_facts.get("scenarios")
    if isinstance(scenarios, dict):
        for key in ("bear", "base", "bull"):
            line = str(scenarios.get(key) or "").strip()
            if not line:
                continue
            numbers = _NUMBER_TOKEN_RE.findall(line)
            if not numbers:
                pins_skipped += 1
                continue
            pins_checked += 1
            missing = [
                number
                for number in numbers
                if _squash(number) not in finance_squashed
                and _norm(number) not in finance_norm
            ]
            if len(missing) * 2 > len(numbers):
                findings.append(
                    PinFinding(
                        code="scenario_numbers_missing",
                        location=_SECTION_FINANCE,
                        pin=f"{key}: {line}",
                        detail=(
                            f"the pinned {key} scenario numbers "
                            f"({', '.join(missing)}) do not appear in the "
                            "financial section — repeat the pinned scenario "
                            "numbers exactly"
                        ),
                    )
                )

    return PinCheckResult(
        findings=findings,
        pins_checked=pins_checked,
        pins_skipped=pins_skipped,
    )


def render_markdown_report(result: PinCheckResult, *, attempt: int | None = None) -> str:
    lines = ["# Memo pin-echo check", ""]
    if attempt:
        lines.append(f"Attempt: {attempt}")
    lines.append(f"Pins checked: {result.pins_checked}")
    lines.append(f"Pins skipped (uncheckable values): {result.pins_skipped}")
    lines.append(f"Findings: {len(result.findings)}")
    lines.append("")
    if result.ok:
        lines.append("All pinned facts are echoed by the package.")
    else:
        for finding in result.findings:
            lines.append(
                f"- **{finding.code}** ({finding.location}): {finding.detail}"
            )
    return "\n".join(lines) + "\n"
