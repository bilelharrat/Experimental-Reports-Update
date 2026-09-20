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

# Late v1 defaults; check_package_pins resolves the package's own
# structure from its meta stamp and uses role-based lookups.
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


# Inline provenance tokens ("[S3]", "[C2, S4]") may sit anywhere in a v2
# package, including inside a pinned sentence's final period ("...buyer
# is feasible [S15]."). A cited echo is still an echo: strip the tokens
# (and the space before them) from both the section text and the pin
# before matching. A live compact run lost a repair round when all nine
# cited scorecard why-lines "failed" exact matching (2026-09-14).
_CITATION_TOKEN_RE = re.compile(r"\s*\[[SC]\d+(?:\s*,\s*[SC]\d+)*\]")


def _norm(text: str) -> str:
    text = _CITATION_TOKEN_RE.sub("", str(text))
    return re.sub(r"\s+", " ", text).strip().casefold()


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
    structure = memo_structure.for_package(package)
    section_exec = structure.section_for_role("exec").id
    section_risk = structure.section_for_role("risk").id
    section_finance = structure.section_for_role("valuation").id
    findings: list[PinFinding] = []
    pins_checked = 0
    pins_skipped = 0

    package_norm = _norm(_package_text(package))
    package_squashed = _squash(_package_text(package))
    exec_text = _section_text(package, section_exec)
    exec_norm, exec_squashed = _norm(exec_text), _squash(exec_text)
    risk_text = _section_text(package, section_risk)
    risk_norm, risk_squashed = _norm(risk_text), _squash(risk_text)
    finance_text = _section_text(package, section_finance)
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
                    location=section_exec,
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
                    location=section_exec,
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
                    location=section_risk,
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
                        location=section_risk,
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
    #    v2 pins scenarios as objects; their numeric fields join into one
    #    checkable line.
    scenarios = shared_facts.get("scenarios")
    if isinstance(scenarios, dict):
        for key in ("bear", "base", "bull"):
            scenario = scenarios.get(key)
            if isinstance(scenario, dict):
                line = " ".join(
                    str(scenario.get(field) or "")
                    for field in (
                        "exit_year",
                        "exit_revenue",
                        "exit_multiple",
                        "exit_value",
                        "moic",
                        "irr",
                    )
                ).strip()
            else:
                line = str(scenario or "").strip()
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
                        location=section_finance,
                        pin=f"{key}: {line}",
                        detail=(
                            f"the pinned {key} scenario numbers "
                            f"({', '.join(missing)}) do not appear in the "
                            "financial section — repeat the pinned scenario "
                            "numbers exactly"
                        ),
                    )
                )

    # 5. v2 pins (verdict, scorecard, fair value): the owning sections and
    #    the decision section must echo them. Absent pins mean no checks,
    #    so v1 packages are untouched.
    weights = structure.scorecard_weights()
    scorecard = shared_facts.get("scorecard")
    verdict = str(shared_facts.get("verdict") or "").strip()
    decision_section = structure.section("investment_decision")
    decision_id = (
        decision_section.id
        if decision_section is not None
        else structure.section_ids[-1]
    )
    decision_text = _section_text(package, decision_id)
    decision_norm = _norm(decision_text)
    decision_squashed = _squash(decision_text)
    if weights and isinstance(scorecard, dict) and verdict:
        total = scorecard.get("total")
        verdict_token = f"{verdict} — {total}/100"
        pins_checked += 1
        for location, norm_text, squashed in (
            (section_exec, exec_norm, exec_squashed),
            (decision_id, decision_norm, decision_squashed),
        ):
            if not _contains(norm_text, squashed, verdict_token):
                findings.append(
                    PinFinding(
                        code="verdict_not_echoed",
                        location=location,
                        pin=verdict_token,
                        detail=(
                            f'the pinned verdict line "{verdict_token}" does '
                            f"not appear in {location} — open the verdict "
                            "block with it exactly as pinned"
                        ),
                    )
                )
        dimensions = (
            scorecard.get("dimensions")
            if isinstance(scorecard.get("dimensions"), dict)
            else {}
        )
        for dimension, weight in weights.items():
            entry = dimensions.get(dimension)
            if not isinstance(entry, dict):
                continue
            score = entry.get("score")
            owner = structure.scorecard_owner(dimension)
            if owner is not None and isinstance(score, int):
                pins_checked += 1
                owner_text = _section_text(package, owner.id)
                sentence = f"scores {score} of {weight}"
                if not _contains(
                    _norm(owner_text), _squash(owner_text), sentence
                ):
                    findings.append(
                        PinFinding(
                            code="scorecard_dimension_not_echoed",
                            location=owner.id,
                            pin=f"{dimension}: {sentence}",
                            detail=(
                                f"section {owner.id} owns the scorecard "
                                f"dimension {dimension} and must close with "
                                f'"This dimension scores {score} of '
                                f'{weight}." — the pinned score sentence is '
                                "missing"
                            ),
                        )
                    )
            why = str(entry.get("why") or "").strip()
            if why:
                pins_checked += 1
                if not _contains(decision_norm, decision_squashed, why):
                    findings.append(
                        PinFinding(
                            code="scorecard_why_not_echoed",
                            location=decision_id,
                            pin=f"{dimension}: {why}",
                            detail=(
                                f"the decision section's scorecard table "
                                f"must repeat the pinned why-line for "
                                f'{dimension} ("{why}") exactly'
                            ),
                        )
                    )
    fair_value = shared_facts.get("fair_value_range")
    if weights and isinstance(fair_value, dict):
        valuation_owner = structure.scorecard_owner("valuation")
        if valuation_owner is not None:
            owner_text = _section_text(package, valuation_owner.id)
            owner_norm, owner_squashed = _norm(owner_text), _squash(owner_text)
            for bound in ("low", "high"):
                value = str(fair_value.get(bound) or "").strip()
                if not value:
                    continue
                pins_checked += 1
                if not _contains(owner_norm, owner_squashed, value):
                    findings.append(
                        PinFinding(
                            code="fair_value_not_echoed",
                            location=valuation_owner.id,
                            pin=f"fair value {bound}: {value}",
                            detail=(
                                f"the pinned fair-value {bound} bound "
                                f'"{value}" does not appear in '
                                f"{valuation_owner.id} — state the pinned "
                                "range verbatim"
                            ),
                        )
                    )

    # 6. Highlights (headline verbatim in the executive summary) and risk
    #    impacts (verbatim in the risk section; the top three also in the
    #    executive summary's Key risks). Absent pins mean no checks.
    highlights = shared_facts.get("highlights")
    if weights and isinstance(highlights, list):
        for index, item in enumerate(highlights, start=1):
            if not isinstance(item, dict):
                continue
            headline = _pin_sentence(item.get("headline"))
            if not headline:
                continue
            pins_checked += 1
            if not _contains(exec_norm, exec_squashed, headline):
                findings.append(
                    PinFinding(
                        code="highlight_not_echoed",
                        location=section_exec,
                        pin=f"highlight {index}: {headline}",
                        detail=(
                            f'pinned highlight headline "{headline}" does '
                            f"not appear in {section_exec} — open highlight "
                            f"bullet {index} with it verbatim"
                        ),
                    )
                )
    pinned_risks = shared_facts.get("risks")
    if weights and isinstance(pinned_risks, list):
        for index, risk in enumerate(pinned_risks, start=1):
            if not isinstance(risk, dict):
                continue
            impact = _pin_sentence(risk.get("impact"))
            if not impact:
                continue
            targets = [(section_risk, risk_norm, risk_squashed)]
            if index <= 3:
                targets.append((section_exec, exec_norm, exec_squashed))
            for location, norm_text, squashed in targets:
                pins_checked += 1
                if not _contains(norm_text, squashed, impact):
                    findings.append(
                        PinFinding(
                            code="risk_impact_not_echoed",
                            location=location,
                            pin=f"risk {index} impact: {impact}",
                            detail=(
                                f'the pinned impact "{impact}" for risk '
                                f"{index} does not appear in {location} — "
                                'state it verbatim after "Impact:"'
                            ),
                        )
                    )

    return PinCheckResult(
        findings=findings,
        pins_checked=pins_checked,
        pins_skipped=pins_skipped,
    )


_MONEY_RE = re.compile(
    # Digit grouping first, so "$1,950B" reads 1950, not 1 (a live spine
    # respin traced to exactly that: base MOIC vs "~0.0x", 2026-09-12).
    r"\$?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(t(?:n|rillion)?|b(?:n|illion)?|m(?:m|illion)?|k)?\b",
    re.IGNORECASE,
)
_MOIC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*x", re.IGNORECASE)
# A pinned risk summary must be a predication, not a topic label. The
# verb list is deliberately broad; only a summary with NO recognizable
# finite verb is flagged (false positives cost a spine respin).
_FINITE_VERB_RE = re.compile(
    r"\b(is|are|was|were|has|have|had|does|do|did|remains?|requires?|"
    r"assumes?|depends?|lacks?|exceeds?|needs?|fails?|cannot|can't|"
    r"will|would|could|must|earns?|leaves?|makes?|takes?|"
    r"drives?|carries?|threatens?|erodes?|blocks?|stalls?|"
    r"dilutes?|concentrates?|rests?|hinges?|outpaces?|trails?|"
    r"exposes?|limits?|constrains?|undermines?|overstates?|"
    r"understates?|breaks?|kills?|holds?|comes?|goes?|puts?|"
    r"gets?|means?|implies?|says?|shows?|masks?|hides?|behaves?|"
    r"becomes?|sits?|faces?|relies?|works?|stands?|acts?|looks?|"
    r"turns?|falls?|rises?|grows?|shrinks?|competes?|loses?|wins?)\b",
    re.IGNORECASE,
)


def _parse_money(text: str) -> float | None:
    """Parse the money value a pin string carries.

    Prefer the first match that carries a scale suffix: pins like
    "2029: $2.6T" or "$1.9-2.3T" lead with a bare number (a year, a
    range's low end) that a first-match parse mistakes for the value —
    the "~0.0x" MOIC false positive that cost a spine respin in two
    consecutive live runs. A string with no suffixed match still parses
    its first number."""
    matches = list(_MONEY_RE.finditer(str(text or "")))
    match = next((m for m in matches if m.group(2)), None) or (
        matches[0] if matches else None
    )
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    if suffix.startswith("t"):
        return value * 1_000_000_000_000
    if suffix.startswith("b"):
        return value * 1_000_000_000
    if suffix.startswith("m"):
        return value * 1_000_000
    if suffix.startswith("k"):
        return value * 1_000
    return value


def _pin_sentence(value: object) -> str:
    """A pinned sentence for echo matching: trailing full stops are
    dropped so a section that ends the sentence differently ("...it." vs
    "...it, because") still matches the words."""
    return str(value or "").strip().rstrip(".。 ")


def check_spine_pins_v2(
    shared_facts: dict,
    structure,
) -> list[str]:
    """Deterministic arithmetic/consistency gate on the v2 pin sheet.

    Runs after spine validation and BEFORE any section launches, so bad
    pins cost one cheap spine retry instead of a full section wave.
    Returns a list of failure strings (empty = pass). A structure
    without a scorecard (late v1) always passes — these pins do not
    exist there.
    """
    weights = structure.scorecard_weights()
    if not weights:
        return []
    problems: list[str] = []

    stage = str(shared_facts.get("stage") or "").strip()
    if stage and stage != structure.declared_stage:
        problems.append(
            f"pinned stage {stage!r} does not match the run's classified "
            f"stage {structure.declared_stage!r}"
        )

    scorecard = shared_facts.get("scorecard")
    total_score: int | None = None
    if not isinstance(scorecard, dict):
        problems.append("shared_facts.scorecard is missing")
    else:
        dimensions = scorecard.get("dimensions")
        if not isinstance(dimensions, dict):
            problems.append("scorecard.dimensions is missing")
        else:
            computed = 0
            for dimension, weight in weights.items():
                entry = dimensions.get(dimension)
                if not isinstance(entry, dict):
                    problems.append(
                        f"scorecard dimension {dimension} is missing"
                    )
                    continue
                score = entry.get("score")
                if not isinstance(score, int) or not 0 <= score <= weight:
                    problems.append(
                        f"scorecard {dimension} score {score!r} must be an "
                        f"integer between 0 and {weight} (this stage's "
                        "weight)"
                    )
                    continue
                computed += score
                if not str(entry.get("why") or "").strip():
                    problems.append(
                        f"scorecard {dimension} needs a one-line why"
                    )
            stated_total = scorecard.get("total")
            if isinstance(stated_total, int) and stated_total != computed:
                problems.append(
                    f"scorecard total {stated_total} does not equal the sum "
                    f"of the dimension scores ({computed}) — recompute it"
                )
            total_score = computed

    from server import memo_structure as _ms

    verdict = str(shared_facts.get("verdict") or "").strip()
    bands = {name: (low, high) for name, low, high in _ms.VERDICT_BANDS}
    if verdict not in bands:
        problems.append(
            f"verdict {verdict!r} must be one of {', '.join(bands)}"
        )
    elif total_score is not None:
        low, high = bands[verdict]
        if not low <= total_score <= high:
            problems.append(
                f"verdict {verdict} requires a scorecard total between "
                f"{low} and {high}; the dimensions sum to {total_score}"
            )

    recommendation = str(
        shared_facts.get("recommendation_sentence") or ""
    ).strip().lower()
    if verdict in bands and recommendation.startswith("recommendation:"):
        stance = recommendation[len("recommendation:"):].strip()
        invests = stance.startswith(("bsh commits", "bsh invests"))
        watches = stance.startswith("watch")
        passes = stance.startswith("pass")
        if verdict in ("Strong Buy", "Buy") and (watches or passes):
            problems.append(
                f"verdict {verdict} conflicts with the recommendation "
                "sentence's watch/pass stance"
            )
        if verdict == "Watch" and (invests or passes):
            problems.append(
                "verdict Watch conflicts with the recommendation sentence's "
                "stance"
            )
        if verdict == "Pass" and (invests or watches):
            problems.append(
                "verdict Pass conflicts with the recommendation sentence's "
                "stance"
            )

    fair_value = shared_facts.get("fair_value_range")
    if isinstance(fair_value, dict):
        low_value = _parse_money(fair_value.get("low"))
        high_value = _parse_money(fair_value.get("high"))
        if low_value is not None and high_value is not None:
            if low_value > high_value:
                problems.append(
                    "fair_value_range low exceeds high — swap or fix them"
                )

    scenarios = shared_facts.get("scenarios")
    entry_pin = shared_facts.get("entry")
    if isinstance(scenarios, dict) and isinstance(entry_pin, dict):
        base = scenarios.get("base")
        entry_valuation = _parse_money(entry_pin.get("valuation"))
        if isinstance(base, dict) and entry_valuation:
            exit_value = _parse_money(base.get("exit_value"))
            moic_match = _MOIC_RE.search(str(base.get("moic") or ""))
            if exit_value and moic_match:
                stated = float(moic_match.group(1))
                undiluted = exit_value / entry_valuation
                # Dilution only lowers the multiple; a stated MOIC above
                # the undiluted ratio (with slack) is arithmetic fiction.
                if stated > undiluted * 1.2 or stated < undiluted * 0.3:
                    problems.append(
                        f"base scenario MOIC {stated}x is inconsistent with "
                        f"exit value / entry valuation (~{undiluted:.1f}x "
                        "before dilution) — fix the numbers or the MOIC"
                    )

    calculations = shared_facts.get("calculations")
    if isinstance(calculations, list):
        seen_calc_ids: set[str] = set()
        blob_parts: list[str] = []
        for note in calculations:
            if not isinstance(note, dict):
                continue
            calc_id = str(note.get("id") or "").strip()
            if calc_id in seen_calc_ids:
                problems.append(f"calculation id {calc_id} is duplicated")
            seen_calc_ids.add(calc_id)
            blob_parts.append(
                f"{note.get('formula') or ''} {note.get('result') or ''}"
            )
        blob = " ".join(blob_parts).lower().replace(" ", "")
        needed: list[tuple[str, object]] = []
        if isinstance(scenarios, dict):
            for key in ("bear", "base", "bull"):
                scenario = scenarios.get(key)
                if isinstance(scenario, dict) and scenario.get("moic"):
                    needed.append((f"{key} scenario MOIC", scenario["moic"]))
        if isinstance(fair_value, dict):
            for bound in ("low", "high"):
                if fair_value.get(bound):
                    needed.append((f"fair value {bound}", fair_value[bound]))
        for label, value in needed:
            token = str(value or "").strip().lower().replace(" ", "")
            if token and token not in blob:
                problems.append(
                    f"calculations must include a note whose formula or "
                    f"result shows the {label} {value} — add the arithmetic "
                    "behind it"
                )

    highlights = shared_facts.get("highlights")
    dimensions_pinned = (
        scorecard.get("dimensions")
        if isinstance(scorecard, dict)
        and isinstance(scorecard.get("dimensions"), dict)
        else {}
    )
    if isinstance(highlights, list):
        if len(highlights) != 3:
            problems.append(
                f"highlights must contain exactly three items, found "
                f"{len(highlights)}"
            )
        seen_dimensions: set[str] = set()
        for item in highlights:
            if not isinstance(item, dict):
                continue
            dimension = str(item.get("dimension") or "").strip()
            if dimension in seen_dimensions:
                problems.append(
                    f"highlight dimension {dimension} is used twice — each "
                    "highlight files under a different scorecard dimension"
                )
            seen_dimensions.add(dimension)
            weight = weights.get(dimension)
            entry = dimensions_pinned.get(dimension)
            score = entry.get("score") if isinstance(entry, dict) else None
            if (
                isinstance(score, int)
                and isinstance(weight, int)
                and weight > 0
                and score * 10 < weight * 6
            ):
                problems.append(
                    f"highlight dimension {dimension} scores {score} of "
                    f"{weight} (below 60%) — a highlight must be one of the "
                    "strongest dimensions; pick a stronger dimension"
                )
            headline = str(item.get("headline") or "").strip()
            if (
                headline
                and len(headline.split()) <= 5
                and not _FINITE_VERB_RE.search(headline)
            ):
                problems.append(
                    f'highlight headline "{headline}" is a topic label — '
                    "write one plain verdict sentence with a finite verb"
                )

    for risk in shared_facts.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        summary = str(risk.get("summary") or "").strip()
        # Topic labels are short noun phrases ("Entry price"). A summary
        # long enough to be a sentence passes even when the curated verb
        # list misses its verb — false positives cost a spine respin
        # (live run 2026-09-11: "commitments behave like senior
        # obligations" was flagged because "behave" was unlisted).
        if (
            summary
            and len(summary.split()) <= 5
            and not _FINITE_VERB_RE.search(summary)
        ):
            problems.append(
                f'risk summary "{summary}" is a topic label — rewrite it as '
                "a complete verdict sentence with a finite verb"
            )
    return problems


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
