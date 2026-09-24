"""Returns computed in Python from the v2 pin sheet (R16).

The v2 spine pins an entry valuation and three scenario objects (bear, base,
bull: exit year, exit revenue, exit multiple, exit value, MOIC and optional
IRR, dilution and probability). Those numbers are written by a model, and a
partner catches the slips at once: an exit value that does not follow from
its own revenue and multiple (Anthropic's bull row, "$60–66B … about $366B",
which only follows from $56B), a bear case labelled "below entry" whose exit
is above the entry, weights that do not add to 100.

``compute(shared_facts, ...)`` is a pure function over the pins (plus the
firm's saved return policy, the cap-table inputs, the deal terms on file
and the saved fund size, when the caller has them): exit values, gross
MOIC and IRR recomputed, the probability-weighted MOIC and P(MOIC < 1) when
weights exist, the entry price at which the base case clears the firm's
hurdle (the walk-away price), the preference-adjusted multiple when the cap
table is set, and a small entry × exit-multiple grid.

The partner's questions the pins do not answer are computed too (R17):
what has to be true at this price — the exit value and, at the base case's
multiple, the exit-year revenue that return the money, clear the bar and
return 3x after the base case's dilution; the breakeven entry (the price at
which the base case merely returns 1x, so it exists without a policy); the
growth each case implies from the latest pinned revenue; the base-case IRR
if the exit slips a year or two; and, when the deal record names a
proposed check, BSH's ownership, proceeds by case and share of the fund.
``check(result)`` lists where the pinned numbers disagree with the
arithmetic — WARNINGS only, never a respin or a failed run.
``calculation_notes(...)`` turns the new figures into [C#] notes the memo
can cite, so the fact check counts them as derived.

Nothing here reads a file, the clock or a model.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

SCENARIO_KEYS = ("bear", "base", "bull")

# Tolerances: the pins are rounded by the model, so a recompute counts as a
# disagreement only beyond one rounding step.
_MONEY_REL_TOL = 0.05
_MOIC_ABS_TOL = 0.05
_IRR_PP_TOL = 1.5
_PROBABILITY_SUM_TOL = 1

_SCALES = {"t": 1e12, "b": 1e9, "m": 1e6, "k": 1e3}
_MONEY_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(t(?:n|rillion)?|b(?:n|illion)?|m(?:m|illion)?|k)?\b",
    re.IGNORECASE,
)
_RANGE_JOIN_RE = re.compile(r"\s*(?:[-–—~]|to)\s*\$?\s*", re.IGNORECASE)
_MULTIPLE_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*x?\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*x", re.IGNORECASE
)
_MULTIPLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*x", re.IGNORECASE)
_PERCENT_RANGE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*%?\s*(?:[-–—]|to)\s*(-?\d+(?:\.\d+)?)\s*%"
)
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
# Digits, not word boundaries, delimit the year: "2031E" and "FY2025" are
# years too (a \b between "1" and "E" never matches).
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
# The pinned holding period: "3.5 years", "3-4 years (exit 2029)", "5 yrs".
_HOLD_YEARS_RE = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)(?:\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?))?\s*-?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)

# "below entry"-style labels and the sign they claim.
_BELOW_ENTRY_RE = re.compile(
    r"\b(?:below|under|beneath|short of)\s+(?:the\s+|our\s+)?entry\b", re.IGNORECASE
)
_ABOVE_ENTRY_RE = re.compile(r"\babove\s+(?:the\s+|our\s+)?entry\b", re.IGNORECASE)
_LOSS_RE = re.compile(
    r"\b(?:loses?\s+money|lose\s+capital|capital\s+loss|loss\s+of\s+capital|"
    r"below\s+cost|below\s+1(?:\.0)?x|less\s+than\s+1(?:\.0)?x|under\s*water|underwater)\b",
    re.IGNORECASE,
)
# The price a recommendation sentence commits at: "at or below $1.2T",
# "commits … at $1.2T". The largest amount named that way is the price (a
# check size named the same way, "up to $5M", is far smaller).
_COMMIT_PRICE_RE = re.compile(
    r"\b(?:at\s+or\s+below|at\s+or\s+under|no\s+(?:more|higher)\s+than|up\s+to|"
    r"not\s+above|(?:commit|invest|participate|enter|buy)\w*\s+(?:[\w$.,~]+\s+){0,6}?"
    r"(?:at|below|under))\s+(?:an?\s+|the\s+)?(?:entry\s+|price\s+|valuation\s+)?"
    r"(?:of\s+)?(~?\$\s?\d[\d,.]*\s*(?:t(?:n|rillion)?|b(?:n|illion)?|m(?:m|illion)?|k)?\b)",
    re.IGNORECASE,
)


# ---- parsing -------------------------------------------------------------------------------


def _number(match: re.Match) -> float:
    return float(match.group(1).replace(",", ""))


def _scale(match: re.Match) -> float:
    suffix = (match.group(2) or "").lower()
    return _SCALES.get(suffix[:1], 1.0) if suffix else 1.0


def parse_money_range(text: Any) -> tuple[float, float] | None:
    """``"$60–66B"`` → (60e9, 66e9); ``"~$366B"`` → (366e9, 366e9);
    ``"2029: $2.6T"`` → (2.6e12, 2.6e12) — a number with a scale suffix wins
    over a bare one (a year, a range's low end). None when nothing parses."""
    source = str(text or "")
    matches = list(_MONEY_RE.finditer(source))
    if not matches:
        return None
    suffixed = [match for match in matches if match.group(2)]
    if not suffixed:
        value = _number(matches[0])
        return value, value
    first = suffixed[0]
    high = _number(first) * _scale(first)
    before = [match for match in matches if match.end() <= first.start()]
    if before and not before[-1].group(2):
        joined = source[before[-1].end() : first.start()]
        if _RANGE_JOIN_RE.fullmatch(joined):
            low = _number(before[-1]) * _scale(first)
            return min(low, high), max(low, high)
    if len(suffixed) > 1:
        second = suffixed[1]
        joined = source[first.end() : second.start()]
        if _RANGE_JOIN_RE.fullmatch(joined):
            other = _number(second) * _scale(second)
            return min(high, other), max(high, other)
    return high, high


def parse_multiple_range(text: Any) -> tuple[float, float] | None:
    """``"12-15x"`` → (12, 15); ``"1.9x"`` → (1.9, 1.9)."""
    source = str(text or "")
    match = _MULTIPLE_RANGE_RE.search(source)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return min(low, high), max(low, high)
    match = _MULTIPLE_RE.search(source)
    if match:
        value = float(match.group(1))
        return value, value
    return None


def parse_percent_range(text: Any) -> tuple[float, float] | None:
    """``"15-20%"`` → (15, 20); ``"19% IRR"`` → (19, 19)."""
    source = str(text or "")
    match = _PERCENT_RANGE_RE.search(source)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return min(low, high), max(low, high)
    match = _PERCENT_RE.search(source)
    if match:
        value = float(match.group(1))
        return value, value
    return None


def parse_year(text: Any) -> int | None:
    match = _YEAR_RE.search(str(text or ""))
    return int(match.group(1)) if match else None


def parse_hold_years(text: Any) -> float | None:
    """``"3.5 years (target exit 2029)"`` → 3.5; ``"3-4 years"`` → 3.5."""
    match = _HOLD_YEARS_RE.search(str(text or ""))
    if not match:
        return None
    low = float(match.group(1))
    high = float(match.group(2)) if match.group(2) else low
    hold = (low + high) / 2
    return hold if 0 < hold <= 30 else None


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    parsed = parse_percent_range(value) or (
        (float(value), float(value)) if re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", str(value)) else None
    )
    return (parsed[0] + parsed[1]) / 2 if parsed else None


def _mid(pair: tuple[float, float] | None) -> float | None:
    return (pair[0] + pair[1]) / 2 if pair else None


# ---- formatting ----------------------------------------------------------------------------


def format_money(value: float | None) -> str:
    """``7.36e11`` → ``"$736B"``; three significant figures."""
    if value is None or not math.isfinite(value):
        return ""
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            scaled = value / threshold
            digits = 0 if abs(scaled) >= 100 else 1 if abs(scaled) >= 10 else 2
            text = f"{scaled:.{digits}f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"${text}{suffix}"
    return f"${value:,.0f}"


def format_multiple(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.2f}x" if abs(value) < 1 else f"{value:.1f}x"


def _formula_multiple(value: float | None) -> str:
    """A multiple inside a formula, to two decimals below 10x ("1.24x"), so
    the arithmetic reproduces its own result — "1.2x^(1/3) − 1" is 6.3%,
    not the 7.4% a 1.24x base case compounds at."""
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.2f}x" if abs(value) < 10 else f"{value:.1f}x"


def format_percent(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.0f}%" if abs(value) >= 10 else f"{value:.1f}%"


# ---- the computation -----------------------------------------------------------------------


def _irr_pct(moic: float | None, hold_years: float | None) -> float | None:
    if moic is None or hold_years is None or hold_years <= 0 or moic <= 0:
        return None
    return (moic ** (1.0 / hold_years) - 1.0) * 100.0


def _hurdle(policy: dict | None, hold_years: float | None) -> dict | None:
    """The bar in multiple terms: the stricter of the target MOIC and the
    target IRR compounded over the hold (at 20% over 5 years the IRR bar,
    2.49x, binds — not a 2.0x MOIC)."""
    if not isinstance(policy, dict):
        return None
    moic = _optional_number(policy.get("target_moic"))
    irr = _optional_number(policy.get("target_irr_pct"))
    policy_hold = _optional_number(policy.get("max_hold_years"))
    hold = hold_years if hold_years and hold_years > 0 else policy_hold
    irr_bar = (1.0 + irr / 100.0) ** hold if irr is not None and hold else None
    candidates = [value for value in (moic, irr_bar) if value]
    if not candidates:
        return None
    return {
        "moic": moic,
        "irr_pct": irr,
        "hold_years": hold,
        "irr_bar_moic": irr_bar,
        "bar_moic": max(candidates),
    }


def _cagr_pct(start: float | None, end: float | None, years: float | None) -> float | None:
    """Compound annual growth from ``start`` to ``end`` over ``years``
    (None below a one-year hold or without both levels)."""
    if not start or not end or start <= 0 or end <= 0 or not years or years < 1:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


_REVENUE_METRIC_RE = re.compile(
    r"\b(?:revenues?|arr|annual(?:i[sz]ed)?\s+recurring\s+revenue|run[- ]rate|"
    r"net\s+sales|sales)\b",
    re.IGNORECASE,
)
# A revenue-type name that is a rate, a ratio, a count or a forecast — not
# the level the growth arithmetic starts from.
_REVENUE_NOT_LEVEL_RE = re.compile(
    r"growth|multiple|margin|\bper\b|ratio|retention|share|%|/|payback|"
    r"concentration|yoy|cagr|burn|cycle|headcount|customers?|target|forecast|"
    r"guidance|plan|projected|expected|backlog|pipeline|bookings|"
    r"\b20\d\d\s?[eE]\b",
    re.IGNORECASE,
)
# A value that is the spine's own estimate, not a disclosed figure: the
# growth arithmetic never starts from one.
_ESTIMATE_VALUE_RE = re.compile(
    r"estimat|implied|assum|proxy|\bour\b|modell?ed", re.IGNORECASE
)
_MONEY_SUFFIX_RE = re.compile(
    r"\d[\d,.]*\s*(?:t(?:n|rillion)?|b(?:n|illion)?|m(?:m|illion)?|k)\b",
    re.IGNORECASE,
)
_UNDISCLOSED_RE = re.compile(r"not\s+disclosed|undisclosed|\bn/?a\b", re.IGNORECASE)


def latest_revenue(key_metrics: Any) -> dict | None:
    """The pinned revenue level the growth arithmetic starts from: the first
    key metric whose name is a revenue level (revenue, ARR, run-rate,
    sales — never a growth rate, a multiple, a margin, a forecast, a
    backlog or a pipeline) and whose value parses as money with a scale
    suffix and is not itself an estimate. None when no such metric is
    pinned: a company that discloses no revenue gets no growth lines."""
    for metric in key_metrics if isinstance(key_metrics, list) else []:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name") or "").strip()
        if not _REVENUE_METRIC_RE.search(name) or _REVENUE_NOT_LEVEL_RE.search(name):
            continue
        value = str(metric.get("value") or "").strip()
        if (
            not value
            or _UNDISCLOSED_RE.search(value)
            or _ESTIMATE_VALUE_RE.search(value)
            or not _MONEY_SUFFIX_RE.search(value)
        ):
            continue
        parsed = parse_money_range(value)
        if not parsed or parsed[0] <= 0:
            continue
        source_ids = metric.get("source_ids")
        return {
            "name": name,
            "text": value,
            "range": parsed,
            "as_of": str(metric.get("as_of") or "").strip(),
            "ref": (
                str(source_ids[0]).strip()
                if isinstance(source_ids, list) and source_ids
                else ""
            ),
        }
    return None


def _retention_for(row: dict, entry_mid: float | None) -> float | None:
    """The share of the position kept to exit: the pinned dilution's
    retention, else the retention the pinned MOIC implies against exit ÷
    entry (at most 1 — dilution only lowers the multiple)."""
    if row.get("retention") is not None:
        return row["retention"]
    exit_mid = _mid(row.get("exit_value_stated") or row.get("exit_value_computed"))
    moic = _mid(row.get("moic_stated"))
    if moic and exit_mid and entry_mid and exit_mid > 0:
        return min(1.0, moic / (exit_mid / entry_mid))
    return None


def _usd(value: Any) -> float | None:
    """A positive dollar amount from a number or money text; else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value > 0 else None
    parsed = parse_money_range(value)
    mid = _mid(parsed) if parsed else None
    return mid if mid and mid > 0 else None


def _position(
    entry_mid: float | None,
    scenarios: dict,
    base_retention: float | None,
    deal_terms: dict | None,
    fund_size_usd: Any,
    policy: dict | None,
) -> dict | None:
    """BSH's own dollars, when the deal terms on file name a proposed check:
    ownership at entry (check ÷ post-money — the deal record's, else the
    pinned entry), the share kept to each exit, the proceeds and their
    multiple on the check, and — when the fund size is saved — the check
    and each case's proceeds as a share of the fund."""
    terms = deal_terms if isinstance(deal_terms, dict) else {}
    check = _usd(terms.get("proposed_check_usd"))
    if not check:
        return None
    post = _usd(terms.get("post_money_usd"))
    basis = "the post-money on the deal record"
    if not post:
        post, basis = entry_mid, "the pinned entry valuation"
    if not post:
        return None
    ownership = check / post
    fund = _usd(fund_size_usd)
    cases: dict[str, dict] = {}
    for key, row in scenarios.items():
        exit_mid = _mid(row["exit_value_stated"] or row["exit_value_computed"])
        if not exit_mid:
            continue
        retention = row["retention"] if row["retention"] is not None else base_retention
        if retention is None:
            retention = 1.0
        proceeds = exit_mid * ownership * retention
        cases[key] = {
            "ownership_exit_pct": ownership * retention * 100.0,
            "proceeds": proceeds,
            "multiple": proceeds / check,
            "fund_pct": proceeds / fund * 100.0 if fund else None,
        }
    max_position = (
        _optional_number(policy.get("max_position_pct")) if isinstance(policy, dict) else None
    )
    return {
        "check": check,
        "post_money": post,
        "post_money_basis": basis,
        "ownership_entry_pct": ownership * 100.0,
        "cases": cases,
        "fund_size": fund,
        "share_of_fund_pct": check / fund * 100.0 if fund else None,
        "max_position_pct": max_position,
    }


def compute(
    shared_facts: dict,
    *,
    policy: dict | None = None,
    as_of_year: int | None = None,
    cap_inputs: dict | None = None,
    deal_terms: dict | None = None,
    fund_size_usd: Any = None,
) -> dict:
    """What the pinned numbers imply (see the module docstring).

    ``policy`` is ``fund_policy.stage_policy(stage)`` (None when unset),
    ``as_of_year`` the year the memo is written (the hold starts there),
    ``cap_inputs`` the company's cap-model inputs (preference terms),
    ``deal_terms`` the proposed terms on the deal record (a proposed check
    and post-money, in USD) and ``fund_size_usd`` the saved fund size.
    Every output is None when its inputs do not parse."""
    facts = shared_facts if isinstance(shared_facts, dict) else {}
    entry_pin = facts.get("entry") if isinstance(facts.get("entry"), dict) else {}
    entry = parse_money_range(entry_pin.get("valuation"))
    entry_mid = _mid(entry)
    scenarios_pin = facts.get("scenarios") if isinstance(facts.get("scenarios"), dict) else {}
    # Exit year − run year counts whole years; the pinned holding period
    # ("3.5 years") places the entry and exit inside them. The IRR the memo
    # prints compounds over the pinned hold, so the arithmetic does too —
    # when the pin agrees with the base case's exit year to within a year
    # (ZaiNar 2026-09-23: a 3.5-year pin, 16.5% base IRR, and an
    # IRR-by-exit-year line computed over 3 years that read 19%).
    hold_offset = 0.0
    base_pin = scenarios_pin.get("base")
    pinned_hold = parse_hold_years(entry_pin.get("holding_period"))
    base_exit_year = parse_year(base_pin.get("exit_year")) if isinstance(base_pin, dict) else None
    if pinned_hold and base_exit_year is not None and as_of_year is not None:
        offset = pinned_hold - (base_exit_year - as_of_year)
        if abs(offset) <= 1.0:
            hold_offset = offset
    scenarios: dict[str, dict] = {}
    for key in SCENARIO_KEYS:
        pin = scenarios_pin.get(key)
        if not isinstance(pin, dict):
            continue
        exit_year = parse_year(pin.get("exit_year"))
        hold = (
            float(exit_year - as_of_year) + hold_offset
            if exit_year is not None and as_of_year is not None and exit_year > as_of_year
            else None
        )
        if hold is not None and hold <= 0:
            hold = None
        revenue = parse_money_range(pin.get("exit_revenue"))
        multiple = parse_multiple_range(pin.get("exit_multiple"))
        exit_stated = parse_money_range(pin.get("exit_value"))
        exit_computed = (
            (revenue[0] * multiple[0], revenue[1] * multiple[1])
            if revenue and multiple
            else None
        )
        moic_stated = parse_multiple_range(pin.get("moic"))
        dilution = _optional_number(pin.get("dilution_pct"))
        retention = (
            max(0.0, 1.0 - dilution / 100.0)
            if dilution is not None and 0 <= dilution < 100
            else None
        )
        exit_basis = exit_stated or exit_computed
        moic_undiluted = (
            (exit_basis[0] / entry[1], exit_basis[1] / entry[0])
            if exit_basis and entry and entry[0] > 0
            else None
        )
        moic_computed = (
            (moic_undiluted[0] * retention, moic_undiluted[1] * retention)
            if moic_undiluted and retention is not None
            else None
        )
        moic_mid = _mid(moic_stated) or _mid(moic_computed)
        probability = _optional_number(pin.get("probability"))
        scenarios[key] = {
            "narrative": str(pin.get("narrative") or ""),
            "labels_text": " ".join(
                str(pin.get(field) or "") for field in ("narrative", "moic", "exit_value")
            ),
            "exit_year": exit_year,
            "hold_years": hold,
            "exit_revenue": revenue,
            "exit_multiple": multiple,
            "exit_value_stated": exit_stated,
            "exit_value_computed": exit_computed,
            "dilution_pct": dilution,
            "retention": retention,
            "moic_stated": moic_stated,
            "moic_undiluted": moic_undiluted,
            "moic_computed": moic_computed,
            "moic_mid": moic_mid,
            "irr_stated": parse_percent_range(pin.get("irr")),
            "irr_computed": _irr_pct(moic_mid, hold),
            "probability": probability,
            "pref_moic": None,
        }

    # Preference terms: the cap model's waterfall at each scenario's exit.
    if isinstance(cap_inputs, dict) and scenarios:
        try:
            from . import cap_model

            exits = {
                key: _mid(row["exit_value_stated"] or row["exit_value_computed"])
                for key, row in scenarios.items()
            }
            values = [value / 1e6 for value in exits.values() if value]
            model = cap_model.compute({**cap_inputs, "exit_values_musd": values}) if values else {}
            if model.get("ready"):
                by_exit = {
                    round(float(row["exit_musd"]), 6): row.get("multiple_on_check")
                    for row in model.get("waterfall") or []
                }
                for key, value in exits.items():
                    if value:
                        scenarios[key]["pref_moic"] = by_exit.get(round(value / 1e6, 6))
        except Exception:  # noqa: BLE001 — optional input, never fails the run
            pass

    weights = {
        key: row["probability"]
        for key, row in scenarios.items()
        if row["probability"] is not None
    }
    probability_sum = sum(weights.values()) if weights else None
    weighted_moic = None
    p_below_one = None
    if (
        len(weights) == len(SCENARIO_KEYS)
        and probability_sum is not None
        and abs(probability_sum - 100) <= _PROBABILITY_SUM_TOL
        and all(scenarios[key]["moic_mid"] is not None for key in weights)
    ):
        weighted_moic = sum(weights[key] * scenarios[key]["moic_mid"] for key in weights) / probability_sum
        p_below_one = sum(weights[key] for key in weights if scenarios[key]["moic_mid"] < 1.0)

    base = scenarios.get("base") or {}
    hurdle = _hurdle(policy, base.get("hold_years"))
    # The base case's share kept to exit (pinned dilution, else what its
    # MOIC implies) and its exit value: the two inputs every price question
    # below is asked against.
    base_retention = _retention_for(base, entry_mid) if base else None
    base_exit = (
        _mid(base.get("exit_value_stated") or base.get("exit_value_computed"))
        if base
        else None
    )
    walk_away = None
    if hurdle and entry_mid and base_exit and base_retention:
        # max_entry = exit value × dilution retention ÷ bar
        walk_away = base_exit * base_retention / hurdle["bar_moic"]

    grid = None
    revenue_mid = _mid(base.get("exit_revenue"))
    multiple_mid = _mid(base.get("exit_multiple"))
    if entry_mid and revenue_mid and multiple_mid:
        retention = base_retention if base_retention is not None else 1.0
        entries = [entry_mid * factor for factor in (0.8, 1.0, 1.2)]
        multiples = [multiple_mid * factor for factor in (0.75, 1.0, 1.25)]
        grid = {
            "entries": entries,
            "multiples": multiples,
            "retention": retention,
            "moic": [
                [revenue_mid * multiple * retention / price for multiple in multiples]
                for price in entries
            ],
        }

    # The growth each case implies from the latest pinned revenue level —
    # the number a partner reads first ("$120M by 2031 is 4x today's $30M").
    # The years run from the figure's own date ("FY2025 revenue") to the
    # exit, not from the run date: a year-old figure has a year more to grow.
    latest = latest_revenue(facts.get("key_metrics"))
    latest_mid = _mid(latest["range"]) if latest else None
    latest_year = parse_year(latest["as_of"]) if latest else None
    for row in scenarios.values():
        row["growth_years"] = (
            float(row["exit_year"] - latest_year)
            if latest_year and row["exit_year"] and row["exit_year"] > latest_year
            else row["hold_years"]
        )
        row["implied_growth_pct"] = _cagr_pct(
            latest_mid, _mid(row["exit_revenue"]), row["growth_years"]
        )

    # What has to be true at this price: the exit value — and, at the base
    # case's multiple, the exit-year revenue — that returns the money,
    # clears the firm's bar and returns 3x after the base case's dilution;
    # and the entry at which the base case merely returns 1x, which needs
    # no policy to exist.
    breakeven_entry = base_exit * base_retention if base_exit and base_retention else None
    required: list[dict] = []
    if entry_mid and base_retention:
        targets = [(1.0, "return the money")]
        if hurdle:
            targets.append((hurdle["bar_moic"], "clear the firm's bar"))
        targets.append((3.0, "return 3x"))
        seen: set[float] = set()
        for target, label in sorted(targets):
            if round(target, 2) in seen:
                continue
            seen.add(round(target, 2))
            exit_value = entry_mid * target / base_retention
            revenue = exit_value / multiple_mid if multiple_mid else None
            required.append(
                {
                    "target": target,
                    "label": label,
                    "exit_value": exit_value,
                    "revenue": revenue,
                    "growth_pct": _cagr_pct(latest_mid, revenue, base.get("growth_years")),
                }
            )

    # The base-case IRR if the exit slips a year or two: late-stage holds
    # slip routinely, and a 3x in five years is not a 3x in seven.
    exit_timing = None
    if base.get("moic_mid") and base.get("hold_years") and base.get("exit_year"):
        exit_timing = [
            {
                "exit_year": base["exit_year"] + slip,
                "hold_years": base["hold_years"] + slip,
                "irr_pct": _irr_pct(base["moic_mid"], base["hold_years"] + slip),
            }
            for slip in (0, 1, 2)
        ]

    position = _position(
        entry_mid, scenarios, base_retention, deal_terms, fund_size_usd, policy
    )

    return {
        "entry": entry,
        "entry_text": str(entry_pin.get("valuation") or ""),
        "as_of_year": as_of_year,
        "scenarios": scenarios,
        "probability_sum": probability_sum,
        "probability_weighted_moic": weighted_moic,
        "p_moic_below_1": p_below_one,
        "hurdle": hurdle,
        "walk_away_entry": walk_away,
        "grid": grid,
        "latest_revenue": latest,
        "base_retention": base_retention,
        "breakeven_entry": breakeven_entry,
        "required": required,
        "exit_timing": exit_timing,
        "position": position,
    }


# ---- the checks (warnings only) --------------------------------------------------------------


def _outside(stated: tuple[float, float], computed: tuple[float, float], *, rel: float = 0.0, abs_tol: float = 0.0) -> bool:
    """True when two ranges do not overlap even with the tolerance."""
    low = computed[0] * (1 - rel) - abs_tol
    high = computed[1] * (1 + rel) + abs_tol
    return stated[1] < low or stated[0] > high


def _range_text(pair: tuple[float, float], fmt) -> str:
    if abs(pair[1] - pair[0]) <= 1e-9 * max(1.0, abs(pair[1])):
        return fmt(pair[0])
    return f"{fmt(pair[0])}–{fmt(pair[1])}"


def check(result: dict, *, recommendation_sentence: str = "") -> list[dict]:
    """Where the pinned numbers disagree with the arithmetic:
    ``[{"code", "scenario"?, "detail"}]``. Every entry is a warning."""
    warnings: list[dict] = []
    scenarios = result.get("scenarios") or {}
    entry = result.get("entry")
    for key in SCENARIO_KEYS:
        row = scenarios.get(key)
        if not row:
            continue
        stated, computed = row["exit_value_stated"], row["exit_value_computed"]
        if stated and computed and _outside(stated, computed, rel=_MONEY_REL_TOL):
            implied = (
                format_money(_mid(stated) / _mid(row["exit_multiple"]))
                if row["exit_multiple"] and _mid(row["exit_multiple"])
                else ""
            )
            warnings.append(
                {
                    "code": "exit_value_mismatch",
                    "scenario": key,
                    "detail": (
                        f"the {key} case's exit value {_range_text(stated, format_money)} "
                        f"does not follow from its exit revenue "
                        f"{_range_text(row['exit_revenue'], format_money)} × "
                        f"{_range_text(row['exit_multiple'], format_multiple)} "
                        f"({_range_text(computed, format_money)})"
                        + (f"; it implies {implied} of revenue" if implied else "")
                    ),
                }
            )
        moic = row["moic_stated"]
        if moic and row["moic_computed"] and _outside(moic, row["moic_computed"], rel=_MONEY_REL_TOL, abs_tol=_MOIC_ABS_TOL):
            warnings.append(
                {
                    "code": "moic_mismatch",
                    "scenario": key,
                    "detail": (
                        f"the {key} case's MOIC {_range_text(moic, format_multiple)} does not "
                        f"follow from its exit value, the entry and {row['dilution_pct']:g}% "
                        f"dilution ({_range_text(row['moic_computed'], format_multiple)})"
                    ),
                }
            )
        elif moic and row["moic_undiluted"] and moic[0] > row["moic_undiluted"][1] * (1 + _MONEY_REL_TOL) + _MOIC_ABS_TOL:
            warnings.append(
                {
                    "code": "moic_above_undiluted",
                    "scenario": key,
                    "detail": (
                        f"the {key} case's MOIC {_range_text(moic, format_multiple)} is above "
                        f"its exit value ÷ entry ({_range_text(row['moic_undiluted'], format_multiple)} "
                        "before any dilution) — dilution only lowers the multiple"
                    ),
                }
            )
        irr, hold = row["irr_stated"], row["hold_years"]
        moic_mid = row["moic_mid"]
        if irr and hold and moic_mid and moic_mid > 0:
            # The entry and exit dates inside their years are unknown: any
            # hold within a year of exit year − run year is accepted.
            bounds = [
                _irr_pct(moic_mid, h) for h in (max(0.5, hold - 1.0), hold + 1.0)
            ]
            low, high = min(bounds), max(bounds)
            if irr[1] < low - _IRR_PP_TOL or irr[0] > high + _IRR_PP_TOL:
                warnings.append(
                    {
                        "code": "irr_mismatch",
                        "scenario": key,
                        "detail": (
                            f"the {key} case's IRR {_range_text(irr, format_percent)} does not "
                            f"follow from {format_multiple(moic_mid)} over about "
                            f"{hold:g} years (exit {row['exit_year']}): "
                            f"{format_percent(_irr_pct(moic_mid, hold))}"
                        ),
                    }
                )
        text = row["labels_text"]
        exit_mid = _mid(row["exit_value_stated"] or row["exit_value_computed"])
        entry_mid = _mid(entry)
        if exit_mid and entry_mid:
            if _BELOW_ENTRY_RE.search(text) and exit_mid >= entry_mid:
                warnings.append(
                    {
                        "code": "label_sign_mismatch",
                        "scenario": key,
                        "detail": (
                            f'the {key} case says "below entry" but its exit value '
                            f"{format_money(exit_mid)} is above the {format_money(entry_mid)} entry"
                        ),
                    }
                )
            elif _ABOVE_ENTRY_RE.search(text) and exit_mid < entry_mid:
                warnings.append(
                    {
                        "code": "label_sign_mismatch",
                        "scenario": key,
                        "detail": (
                            f'the {key} case says "above entry" but its exit value '
                            f"{format_money(exit_mid)} is below the {format_money(entry_mid)} entry"
                        ),
                    }
                )
        if moic_mid is not None and _LOSS_RE.search(text) and moic_mid >= 1.0:
            warnings.append(
                {
                    "code": "label_sign_mismatch",
                    "scenario": key,
                    "detail": (
                        f"the {key} case describes a loss but its MOIC is "
                        f"{format_multiple(moic_mid)} (at or above 1x)"
                    ),
                }
            )
    # The cases are ordered by construction: a bear that exits above the
    # base, or a base above the bull, is a mislabelled table.
    for low_key, high_key in (("bear", "base"), ("base", "bull")):
        low, high = scenarios.get(low_key), scenarios.get(high_key)
        if not low or not high:
            continue
        pairs = (
            (
                "exit value",
                _mid(low["exit_value_stated"] or low["exit_value_computed"]),
                _mid(high["exit_value_stated"] or high["exit_value_computed"]),
                format_money,
            ),
            ("MOIC", low["moic_mid"], high["moic_mid"], format_multiple),
        )
        for what, low_value, high_value, fmt in pairs:
            if low_value and high_value and low_value > high_value * (1 + _MONEY_REL_TOL):
                warnings.append(
                    {
                        "code": "scenario_order",
                        "scenario": low_key,
                        "detail": (
                            f"the {low_key} case's {what} {fmt(low_value)} is above "
                            f"the {high_key} case's {fmt(high_value)}"
                        ),
                    }
                )
    # A multi-year hold whose MOIC is exactly exit ÷ entry, with no
    # dilution pinned, states a multiple before any further round — a
    # partner would ask. A pinned MOIC below exit ÷ entry has taken some
    # dilution, whatever the sheet says, and is left alone.
    base = scenarios.get("base")
    if (
        base
        and base.get("hold_years")
        and base["hold_years"] >= 3
        and base.get("dilution_pct") is None
        and base.get("moic_undiluted")
        and base.get("moic_mid")
        and base["moic_mid"] >= _mid(base["moic_undiluted"]) * 0.98
    ):
        warnings.append(
            {
                "code": "dilution_not_pinned",
                "scenario": "base",
                "detail": (
                    f"the base case's MOIC {format_multiple(base['moic_mid'])} is its exit "
                    f"value ÷ entry with no dilution over a {base['hold_years']:g}-year hold "
                    f"to {base['exit_year']}; a further round before exit lowers it"
                ),
            }
        )
    position = result.get("position") or {}
    share, cap = position.get("share_of_fund_pct"), position.get("max_position_pct")
    if share and cap and share > cap + 0.01:
        warnings.append(
            {
                "code": "position_above_policy",
                "detail": (
                    f"the proposed {format_money(position['check'])} check is "
                    f"{format_percent(share)} of the {format_money(position['fund_size'])} "
                    f"fund, above the {cap:g}% single-position limit in the fund policy"
                ),
            }
        )
    total = result.get("probability_sum")
    if total is not None and abs(total - 100) > _PROBABILITY_SUM_TOL:
        warnings.append(
            {
                "code": "probabilities_do_not_sum",
                "detail": f"the scenario probabilities sum to {total:g}, not 100",
            }
        )
    walk_away = result.get("walk_away_entry")
    named = commit_price(recommendation_sentence) if walk_away else None
    if walk_away and named and named[0] > walk_away * (1 + _MONEY_REL_TOL):
        hurdle = result.get("hurdle") or {}
        warnings.append(
            {
                "code": "commit_above_walk_away",
                "detail": (
                    f"the recommendation commits at {named[1]}, but the base case clears "
                    f"the firm's {format_multiple(hurdle.get('bar_moic'))} bar only at or "
                    f"below {format_money(walk_away)}"
                ),
            }
        )
    return warnings


def commit_price(sentence: str) -> tuple[float, str] | None:
    """The price a recommendation sentence commits at, as (value, text):
    the largest amount it names after "at or below", "up to", "commits …
    at" and the like. None when it names none."""
    best: tuple[float, str] | None = None
    for match in _COMMIT_PRICE_RE.finditer(str(sentence or "")):
        parsed = parse_money_range(match.group(1))
        if parsed and (best is None or parsed[1] > best[0]):
            best = (parsed[1], match.group(1).strip())
    return best


# ---- what reaches the pin sheet and the memo -------------------------------------------------


def _next_calc_number(calculations: list) -> int:
    numbers = [
        int(match.group(1))
        for note in calculations
        if isinstance(note, dict)
        for match in [re.fullmatch(r"C(\d+)", str(note.get("id") or "").strip())]
        if match
    ]
    return max(numbers, default=0) + 1


def _moic_note_ref(calculations: list, moic_text: str) -> str:
    """The pinned note whose arithmetic shows ``moic_text`` (the spine gate
    requires one for each scenario MOIC), else "derived"."""
    token = str(moic_text or "").strip().lower().replace(" ", "")
    for note in calculations:
        if not isinstance(note, dict) or not token:
            continue
        blob = f"{note.get('formula') or ''} {note.get('result') or ''}".lower().replace(" ", "")
        if token in blob and str(note.get("id") or "").strip():
            return str(note["id"]).strip()
    return "derived"


def calculation_notes(result: dict, shared_facts: dict) -> list[dict]:
    """[C#] notes for the figures only Python computes, numbered after the
    spine's own: the probability-weighted MOIC (when all three scenarios
    carry weights that sum to 100), the walk-away entry price (when the firm
    has saved a hurdle) and the base-case IRR (when the spine pinned none).
    Each note's shape is the spine's calculation-note shape."""
    calculations = [
        note for note in (shared_facts.get("calculations") or []) if isinstance(note, dict)
    ]
    number = _next_calc_number(calculations)
    scenarios_pin = shared_facts.get("scenarios") if isinstance(shared_facts.get("scenarios"), dict) else {}
    scenarios = result.get("scenarios") or {}
    notes: list[dict] = []

    def add(label: str, inputs: list[dict], formula: str, value: str, meaning: str) -> None:
        nonlocal number
        notes.append(
            {
                "id": f"C{number}",
                "label": label,
                "inputs": inputs,
                "formula": formula,
                "result": value,
                "meaning": meaning,
            }
        )
        number += 1

    weighted = result.get("probability_weighted_moic")
    if weighted is not None:
        inputs = []
        terms = []
        for key in SCENARIO_KEYS:
            row = scenarios[key]
            moic_text = str((scenarios_pin.get(key) or {}).get("moic") or format_multiple(row["moic_mid"]))
            inputs.append({"name": f"{key} case probability", "value": f"{row['probability']:g}%", "ref": "assumption"})
            inputs.append({"name": f"{key} case MOIC", "value": moic_text, "ref": _moic_note_ref(calculations, moic_text)})
            terms.append(f"{row['probability'] / 100:.2f} × {_formula_multiple(row['moic_mid'])}")
        below = result.get("p_moic_below_1") or 0
        add(
            "Probability-weighted MOIC",
            inputs,
            " + ".join(terms) + f" = {format_multiple(weighted)}",
            format_multiple(weighted),
            (
                f"Weighting the three cases by their stated probabilities returns "
                f"{format_multiple(weighted)}; the cases below 1x carry {below:g}% of the weight."
            ),
        )

    walk_away = result.get("walk_away_entry")
    hurdle = result.get("hurdle")
    base = scenarios.get("base")
    if walk_away and hurdle and base:
        base_pin = scenarios_pin.get("base") or {}
        moic_text = str(base_pin.get("moic") or "")
        parts = []
        if hurdle.get("moic"):
            parts.append(f"{format_multiple(hurdle['moic'])} MOIC")
        if hurdle.get("irr_bar_moic"):
            parts.append(
                f"{hurdle['irr_pct']:g}% IRR over {hurdle['hold_years']:g} years = "
                f"{format_multiple(hurdle['irr_bar_moic'])}"
            )
        bar_text = format_multiple(hurdle["bar_moic"])
        inputs = [
            {"name": "entry valuation", "value": result.get("entry_text") or format_money(_mid(result.get("entry"))), "ref": "derived"},
            {"name": "base case exit value", "value": str(base_pin.get("exit_value") or ""), "ref": "derived"},
            {"name": "BSH return hurdle (fund policy)", "value": bar_text, "ref": ""},
        ]
        if base.get("retention") is not None:
            formula = (
                f"{format_money(_mid(base['exit_value_stated'] or base['exit_value_computed']))} × "
                f"{base['retention']:.2f} retained after {base['dilution_pct']:g}% dilution ÷ {bar_text} = "
                f"{format_money(walk_away)}"
            )
        else:
            inputs.insert(1, {"name": "base case MOIC", "value": moic_text, "ref": _moic_note_ref(calculations, moic_text)})
            formula = (
                f"{moic_text or format_multiple(_mid(base['moic_stated']))} × "
                f"{result.get('entry_text') or format_money(_mid(result.get('entry')))} ÷ {bar_text} = "
                f"{format_money(walk_away)}"
            )
        add(
            "Walk-away entry price",
            inputs[:8],
            formula + (f" (the bar is the stricter of {' and '.join(parts)})" if len(parts) > 1 else ""),
            format_money(walk_away),
            (
                f"The highest entry at which the base case still clears the firm's "
                f"{bar_text} bar; above {format_money(walk_away)} the base case falls short of it."
            ),
        )

    if base and not str((scenarios_pin.get("base") or {}).get("irr") or "").strip():
        irr = base.get("irr_computed")
        if irr is not None and base.get("hold_years"):
            moic_text = str((scenarios_pin.get("base") or {}).get("moic") or format_multiple(base["moic_mid"]))
            add(
                "Base-case IRR",
                [
                    {"name": "base case MOIC", "value": moic_text, "ref": _moic_note_ref(calculations, moic_text)},
                    {"name": "holding period", "value": f"{base['hold_years']:g} years (exit {base['exit_year']})", "ref": "assumption"},
                ],
                f"{_formula_multiple(base['moic_mid'])}^(1/{base['hold_years']:g}) − 1 = {format_percent(irr)}",
                format_percent(irr),
                f"The base case compounds at about {format_percent(irr)} a year over the hold.",
            )

    notes.extend(_price_question_notes(result, shared_facts, calculations, number))
    return notes


def _ratio_text(value: float) -> str:
    """A share kept to exit, precise enough that the formula it sits in
    reproduces its own result: two decimals when they are exact ("0.75"),
    else three ("0.918")."""
    two = f"{value:.2f}"
    return two if abs(value - float(two)) < 5e-4 else f"{value:.3f}"


def _retention_input(base: dict, retention: float) -> dict:
    """The calculation input for the base case's share kept to exit, named
    for how it was set — the pinned dilution (an assumption of the case)
    or the pinned MOIC (derived from it)."""
    if base.get("dilution_pct") is not None:
        return {
            "name": f"share kept to exit after {base['dilution_pct']:g}% dilution",
            "value": _ratio_text(retention),
            "ref": "assumption",
        }
    return {
        "name": "share kept to exit, implied by the base case MOIC",
        "value": _ratio_text(retention),
        "ref": "derived",
    }


def _price_question_notes(
    result: dict, shared_facts: dict, calculations: list, number: int
) -> list[dict]:
    """The R17 notes: breakeven entry, what has to be true at this price,
    the growth each case implies, the IRR if the exit slips, and BSH's
    proceeds by case — each only when its inputs exist."""
    scenarios_pin = shared_facts.get("scenarios") if isinstance(shared_facts.get("scenarios"), dict) else {}
    scenarios = result.get("scenarios") or {}
    base = scenarios.get("base")
    base_pin = scenarios_pin.get("base") if isinstance(scenarios_pin.get("base"), dict) else {}
    entry_text = result.get("entry_text") or format_money(_mid(result.get("entry")))
    # The formula names the entry as a figure ("$1B"); the pinned text
    # ("$1B+ post-money, 2026-02-19") stays on the input row.
    entry_figure = format_money(_mid(result.get("entry"))) or entry_text
    retention = result.get("base_retention")
    notes: list[dict] = []

    def add(label: str, inputs: list[dict], formula: str, value: str, meaning: str) -> None:
        nonlocal number
        notes.append(
            {
                "id": f"C{number}",
                "label": label,
                "inputs": inputs[:8],
                "formula": formula,
                "result": value,
                "meaning": meaning,
            }
        )
        number += 1

    if not base or retention is None:
        return notes
    base_exit = _mid(base.get("exit_value_stated") or base.get("exit_value_computed"))
    exit_year = base.get("exit_year") or "exit"
    multiple = _mid(base.get("exit_multiple"))
    latest = result.get("latest_revenue")

    # Formulas are arithmetic only: the Chinese 计算说明 table prints them
    # as written, so every word lives in the (translated) inputs, result
    # and meaning instead.
    ratio = _ratio_text(retention)
    breakeven = result.get("breakeven_entry")
    if breakeven and base_exit:
        add(
            "Breakeven entry price",
            [
                {"name": "base case exit value", "value": str(base_pin.get("exit_value") or format_money(base_exit)), "ref": "derived"},
                _retention_input(base, retention),
            ],
            f"{format_money(base_exit)} × {ratio} = {format_money(breakeven)}",
            format_money(breakeven),
            (
                f"The entry at which the base case returns the money and nothing more; "
                f"above {format_money(breakeven)} the base case loses money."
            ),
        )

    required = result.get("required") or []
    if required:
        pieces = []
        results = []
        for row in required:
            piece = (
                f"{entry_figure} × {format_multiple(row['target'])} ÷ {ratio} = "
                f"{format_money(row['exit_value'])}"
            )
            if row.get("revenue"):
                piece += (
                    f"; {format_money(row['exit_value'])} ÷ {format_multiple(multiple)} = "
                    f"{format_money(row['revenue'])}"
                )
            pieces.append(piece)
            results.append(
                f"{format_money(row.get('revenue') or row['exit_value'])} for "
                f"{format_multiple(row['target'])}"
            )
        one_x = required[0]
        base_revenue = _mid(base.get("exit_revenue"))
        meaning = (
            f"To return the money at this price the company needs "
            f"{format_money(one_x.get('revenue') or one_x['exit_value'])} of "
            f"{exit_year} {'revenue' if one_x.get('revenue') else 'exit value'}"
            + (f" at the base case's {format_multiple(multiple)}" if one_x.get("revenue") else "")
        )
        if base_revenue and one_x.get("revenue"):
            meaning += f"; the base case assumes {format_money(base_revenue)}"
            growth = base.get("implied_growth_pct")
            if latest and growth is not None:
                meaning += (
                    f", {base_revenue / _mid(latest['range']):.1f}x today's "
                    f"{latest['text']} ({format_percent(growth)} a year)"
                )
        add(
            "Required exit at this price",
            [
                {"name": "entry valuation", "value": entry_text, "ref": "derived"},
                {"name": "base case exit multiple", "value": str(base_pin.get("exit_multiple") or format_multiple(multiple)), "ref": "derived"},
                _retention_input(base, retention),
            ],
            "; ".join(pieces),
            "; ".join(results),
            meaning + ".",
        )

    growth_rows = [
        (key, scenarios[key])
        for key in SCENARIO_KEYS
        if key in scenarios and scenarios[key].get("implied_growth_pct") is not None
    ]
    if latest and growth_rows:
        latest_mid = _mid(latest["range"])
        inputs = [
            {
                "name": f"latest {latest['name']}",
                "value": latest["text"],
                "ref": latest["ref"] or "derived",
            }
        ]
        pieces = []
        results = []
        for key, row in growth_rows:
            revenue_text = str((scenarios_pin.get(key) or {}).get("exit_revenue") or format_money(_mid(row["exit_revenue"])))
            inputs.append({"name": f"{key} case exit revenue", "value": revenue_text, "ref": "derived"})
            pieces.append(
                f"({format_money(_mid(row['exit_revenue']))} ÷ {format_money(latest_mid)})"
                f"^(1/{row['growth_years']:g}) − 1 = {format_percent(row['implied_growth_pct'])}"
            )
            results.append(f"{key} {format_percent(row['implied_growth_pct'])}")
        base_row = scenarios.get("base") or {}
        meaning = (
            f"From {latest['text']} of {latest['name']}"
            + (f" ({latest['as_of']})" if latest.get("as_of") else "")
            + ", each case's exit revenue implies this compound growth a year over its hold"
        )
        if base_row.get("implied_growth_pct") is not None and _mid(base_row.get("exit_revenue")):
            meaning += (
                f"; the base case needs {_mid(base_row['exit_revenue']) / latest_mid:.1f}x "
                f"in {base_row['growth_years']:g} years"
            )
        add(
            "Implied revenue growth by case",
            inputs,
            "; ".join(pieces),
            " / ".join(results) + " a year",
            meaning + ".",
        )

    timing = result.get("exit_timing") or []
    if len(timing) == 3 and all(row.get("irr_pct") is not None for row in timing):
        moic_text = str(base_pin.get("moic") or format_multiple(base["moic_mid"]))
        first, last = timing[0], timing[-1]
        pieces = [
            f"{_formula_multiple(base['moic_mid'])}^(1/{row['hold_years']:g}) − 1 = "
            f"{format_percent(row['irr_pct'])}"
            for row in timing
        ]
        if base["moic_mid"] >= 1.0:
            cost = (first["irr_pct"] - last["irr_pct"]) / 2.0
            meaning = (
                f"Each year the exit slips costs about {cost:.0f} points of annual return; "
                f"a {last['exit_year']} exit still returns {format_percent(last['irr_pct'])} a year."
            )
        else:
            meaning = (
                "The base case loses money whatever the exit year; a later exit only "
                "spreads the same loss over more years."
            )
        add(
            "Base-case IRR if the exit slips",
            [
                {"name": "base case MOIC", "value": moic_text, "ref": _moic_note_ref(calculations, moic_text)},
                {"name": "holding period", "value": f"{first['hold_years']:g} years (exit {first['exit_year']})", "ref": "assumption"},
            ],
            "; ".join(pieces),
            " / ".join(f"{row['exit_year']} {format_percent(row['irr_pct'])}" for row in timing),
            meaning,
        )

    position = result.get("position")
    if position and position.get("cases"):
        check_text = format_money(position["check"])
        post_text = format_money(position["post_money"])
        own = position["ownership_entry_pct"]
        pieces = [f"{check_text} ÷ {post_text} = {_format_share(own)}"]
        results = []
        for key in SCENARIO_KEYS:
            case = position["cases"].get(key)
            row = scenarios.get(key)
            if not case or not row:
                continue
            exit_mid = _mid(row["exit_value_stated"] or row["exit_value_computed"])
            kept = case["ownership_exit_pct"] / own if own else 1.0
            pieces.append(
                f"{format_money(exit_mid)} × {_format_share(own)} × {_ratio_text(kept)} = "
                f"{format_money(case['proceeds'])} ({format_multiple(case['multiple'])})"
            )
            results.append(f"{key} {format_money(case['proceeds'])}")
        meaning = (
            f"A {check_text} check buys {_format_share(own)} at {post_text} "
            f"({position['post_money_basis']})"
        )
        base_case = position["cases"].get("base")
        if base_case:
            meaning += f"; the base case returns {format_money(base_case['proceeds'])} on it"
        if position.get("share_of_fund_pct"):
            meaning += (
                f". The check is {format_percent(position['share_of_fund_pct'])} of the "
                f"{format_money(position['fund_size'])} fund"
            )
            bull = position["cases"].get("bull")
            if bull and bull.get("fund_pct") is not None:
                meaning += f"; the bull case returns {format_percent(bull['fund_pct'])} of the fund"
        add(
            "BSH proceeds by case",
            [
                {"name": "BSH check", "value": check_text, "ref": "deal terms"},
                {
                    "name": "post-money",
                    "value": post_text,
                    "ref": "deal terms" if "deal record" in position["post_money_basis"] else "derived",
                },
                {"name": "ownership at entry", "value": _format_share(own), "ref": "derived"},
            ],
            "; ".join(pieces),
            " / ".join(results),
            meaning + ".",
        )
    return notes


def _format_share(value: float | None) -> str:
    """An ownership share to three significant figures ("0.163%", "2.34%",
    "12.5%") — enough that a proceeds formula built on it reproduces its
    own result to within rounding — never in exponent form."""
    if value is None or not math.isfinite(value):
        return ""
    text = format(Decimal(f"{value:.3g}"), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%"


def summary(result: dict, note_ids: dict[str, str] | None = None) -> dict:
    """The compact, JSON-safe record written to ``shared_facts["returns"]``
    and rendered on the pin sheet: formatted strings only."""
    note_ids = note_ids or {}
    out: dict[str, Any] = {"computed_by": "python"}
    scenarios = {}
    for key, row in (result.get("scenarios") or {}).items():
        entry: dict[str, Any] = {}
        # Only where the spine pinned no IRR: two IRRs for one case would
        # read as a contradiction (check() reports a pinned one that is off).
        if row.get("irr_computed") is not None and row.get("irr_stated") is None:
            entry["irr"] = format_percent(row["irr_computed"])
        if row.get("pref_moic") is not None:
            entry["moic_after_preferences"] = format_multiple(row["pref_moic"])
        if entry:
            scenarios[key] = entry
    if scenarios:
        out["scenarios"] = scenarios
    if result.get("probability_weighted_moic") is not None:
        out["probability_weighted_moic"] = format_multiple(result["probability_weighted_moic"])
        out["p_moic_below_1"] = f"{result.get('p_moic_below_1') or 0:g}%"
    if result.get("walk_away_entry"):
        out["walk_away_entry"] = format_money(result["walk_away_entry"])
        out["hurdle_bar_moic"] = format_multiple((result.get("hurdle") or {}).get("bar_moic"))
    grid = result.get("grid")
    if grid:
        out["grid"] = {
            "entries": [format_money(value) for value in grid["entries"]],
            "multiples": [format_multiple(value) for value in grid["multiples"]],
            "moic": [[format_multiple(value) for value in row] for row in grid["moic"]],
        }
    if result.get("breakeven_entry"):
        out["breakeven_entry"] = format_money(result["breakeven_entry"])
    required = result.get("required") or []
    if required:
        out["required"] = [
            {
                "target": format_multiple(row["target"]),
                "label": row["label"],
                "exit_value": format_money(row["exit_value"]),
                "revenue": format_money(row["revenue"]) if row.get("revenue") else "",
                "growth": format_percent(row["growth_pct"]) if row.get("growth_pct") is not None else "",
            }
            for row in required
        ]
    latest = result.get("latest_revenue")
    if latest:
        out["latest_revenue"] = f"{latest['text']} ({latest['name']}" + (
            f", {latest['as_of']})" if latest.get("as_of") else ")"
        )
    growth = {
        key: format_percent(row["implied_growth_pct"])
        for key, row in (result.get("scenarios") or {}).items()
        if row.get("implied_growth_pct") is not None
    }
    if growth:
        out["implied_growth"] = growth
    timing = result.get("exit_timing") or []
    if timing and all(row.get("irr_pct") is not None for row in timing):
        out["exit_timing"] = [
            {"exit_year": str(row["exit_year"]), "irr": format_percent(row["irr_pct"])}
            for row in timing
        ]
    position = result.get("position")
    if position and position.get("cases"):
        cases = {}
        for key, case in position["cases"].items():
            entry: dict[str, str] = {
                "proceeds": format_money(case["proceeds"]),
                "multiple": format_multiple(case["multiple"]),
                "ownership_exit": _format_share(case["ownership_exit_pct"]),
            }
            if case.get("fund_pct") is not None:
                entry["fund"] = format_percent(case["fund_pct"])
            cases[key] = entry
        out["position"] = {
            "check": format_money(position["check"]),
            "post_money": format_money(position["post_money"]),
            "post_money_basis": position["post_money_basis"],
            "ownership_entry": _format_share(position["ownership_entry_pct"]),
            "cases": cases,
        }
        if position.get("share_of_fund_pct"):
            out["position"]["share_of_fund"] = format_percent(position["share_of_fund_pct"])
            out["position"]["fund_size"] = format_money(position["fund_size"])
    if note_ids:
        out["notes"] = dict(note_ids)
    return out


# The notes calculation_notes() may add, by the summary key that names them.
NOTE_KINDS = {
    "Probability-weighted MOIC": "probability_weighted_moic",
    "Walk-away entry price": "walk_away_entry",
    "Base-case IRR": "base_irr",
    "Breakeven entry price": "breakeven_entry",
    "Required exit at this price": "required",
    "Implied revenue growth by case": "implied_growth",
    "Base-case IRR if the exit slips": "exit_timing",
    "BSH proceeds by case": "position",
}


def apply(
    shared_facts: dict,
    *,
    policy: dict | None = None,
    as_of_year: int | None = None,
    cap_inputs: dict | None = None,
    deal_terms: dict | None = None,
    fund_size_usd: Any = None,
) -> dict | None:
    """Compute the returns for a v2 pin sheet and write them into it: the
    new [C#] notes appended to ``shared_facts["calculations"]`` and the
    summary under ``shared_facts["returns"]``. Idempotent (a sheet that
    already carries Python's returns is left alone) and a no-op without an
    entry and scenario objects. Returns ``{"result", "notes", "warnings"}``
    or None."""
    if not isinstance(shared_facts, dict):
        return None
    existing = shared_facts.get("returns")
    if isinstance(existing, dict) and existing.get("computed_by") == "python":
        return None
    scenarios = shared_facts.get("scenarios")
    if not isinstance(scenarios, dict) or not any(
        isinstance(scenarios.get(key), dict) for key in SCENARIO_KEYS
    ):
        return None
    result = compute(
        shared_facts,
        policy=policy,
        as_of_year=as_of_year,
        cap_inputs=cap_inputs,
        deal_terms=deal_terms,
        fund_size_usd=fund_size_usd,
    )
    notes = calculation_notes(result, shared_facts)
    if notes:
        calculations = shared_facts.get("calculations")
        shared_facts["calculations"] = (
            list(calculations) if isinstance(calculations, list) else []
        ) + notes
    shared_facts["returns"] = summary(
        result, {NOTE_KINDS[note["label"]]: note["id"] for note in notes if note["label"] in NOTE_KINDS}
    )
    warnings = check(
        result,
        recommendation_sentence=str(shared_facts.get("recommendation_sentence") or ""),
    )
    return {"result": result, "notes": notes, "warnings": warnings}
