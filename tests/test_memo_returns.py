"""Returns computed in Python from the v2 pins, and the firm's hurdle wired
through the spine (R16, R7 FIX 2-3).

Every check here is a WARNING: the spine gate (check_spine_pins_v2) is
unchanged, and a pin sheet the arithmetic disagrees with still ships.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from memo_v2_fixture import late_v2_package
from server import claude_runner, fund_policy, memo_analysis, memo_pin_check, memo_returns, memo_structure

V2 = memo_structure.active_structure("late", version="v2")

# Anthropic's bull row as shipped: "$60–66B … about $366B", which only
# follows from $56B of revenue at the row's own 6.5x.
ANTHROPIC = {
    "recommendation_sentence": "Recommendation: watch Anthropic until the price clears our bar.",
    "entry": {"valuation": "$61.5B post-money", "basis": "Series E [S1]"},
    "scenarios": {
        "bear": {
            "narrative": "Growth stalls at a services-heavy mix.",
            "exit_year": "2029",
            "exit_revenue": "$12B",
            "exit_multiple": "6x",
            "exit_value": "$72B",
            "moic": "1.1x",
        },
        "base": {
            "narrative": "Enterprise adoption compounds.",
            "exit_year": "2029",
            "exit_revenue": "$34B",
            "exit_multiple": "6.5x",
            "exit_value": "$221B",
            "moic": "3.3x",
        },
        "bull": {
            "narrative": "Agents become the default interface.",
            "exit_year": "2029",
            "exit_revenue": "$60–66B",
            "exit_multiple": "6.5x",
            "exit_value": "$366B",
            "moic": "5.4x",
        },
    },
    "calculations": [
        {"id": "C1", "label": "Base MOIC", "inputs": [], "formula": "$221B / $61.5B ≈ 3.6x less dilution", "result": "3.3x", "meaning": "m"},
        {"id": "C4", "label": "Bull MOIC", "inputs": [], "formula": "$366B / $61.5B", "result": "5.4x", "meaning": "m"},
    ],
}

POLICY = {"target_moic": 2.0, "target_irr_pct": 20.0, "max_hold_years": 5.0, "basis": "gross"}


def _facts(**changes) -> dict:
    facts = copy.deepcopy(ANTHROPIC)
    for key, value in changes.items():
        facts[key] = value
    return facts


# ---- parsing -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$60–66B", (60e9, 66e9)),
        ("~$366B", (366e9, 366e9)),
        ("2029: $2.6T", (2.6e12, 2.6e12)),
        ("$1.9-2.3T", (1.9e12, 2.3e12)),
        ("$60B to $66B", (60e9, 66e9)),
        ("$1,950B", (1.95e12, 1.95e12)),
        ("not disclosed", None),
    ],
)
def test_money_ranges_parse(text, expected):
    assert memo_returns.parse_money_range(text) == expected


def test_commit_price_takes_the_largest_amount_named_as_a_price():
    assert memo_returns.commit_price(
        "Recommendation: BSH commits up to $5M at or below a $1.2T valuation."
    ) == (1.2e12, "$1.2T")
    assert memo_returns.commit_price("Recommendation: pass — the base case sits below our 2.0x hurdle.") is None


def test_money_formatting_keeps_whole_numbers_whole():
    assert memo_returns.format_money(740e9) == "$740B"
    assert memo_returns.format_money(7.36e11) == "$736B"
    assert memo_returns.format_money(1.25e12) == "$1.25T"
    assert memo_returns.format_money(56.3e9) == "$56.3B"


# ---- the checks ------------------------------------------------------------------------------


def test_the_anthropic_bull_row_is_flagged_and_names_the_revenue_it_implies():
    result = memo_returns.compute(ANTHROPIC, as_of_year=2026)
    warnings = memo_returns.check(result)
    assert [(w["code"], w.get("scenario")) for w in warnings] == [("exit_value_mismatch", "bull")]
    detail = warnings[0]["detail"]
    assert "$366B" in detail and "$60B–$66B" in detail and "$56.3B" in detail


def test_a_below_entry_label_on_an_exit_above_the_entry_is_flagged():
    facts = _facts(
        entry={"valuation": "$1.35T", "basis": "secondary strip"},
        scenarios={
            "bear": {"narrative": "Below entry: the multiple compresses.", "exit_year": "2029", "exit_value": "$1.45T", "moic": "1.0x"},
            "base": {"narrative": "b", "exit_year": "2029", "exit_value": "$2.3T", "moic": "1.6x"},
            "bull": {"narrative": "c", "exit_year": "2029", "exit_value": "$3.5T", "moic": "2.4x"},
        },
    )
    warnings = memo_returns.check(memo_returns.compute(facts, as_of_year=2026))
    assert [(w["code"], w["scenario"]) for w in warnings] == [("label_sign_mismatch", "bear")]


def test_moic_irr_and_probabilities_are_rechecked():
    facts = _facts()
    facts["scenarios"]["bear"]["moic"] = "1.5x"  # above $72B / $61.5B undiluted
    # 3.3x over about three years is ~49%; with the entry and exit dates
    # inside their years unknown, anything from 2 to 4 years (35-82%) passes.
    facts["scenarios"]["base"]["irr"] = "15%"
    facts["scenarios"]["bull"]["exit_revenue"] = "$56B"
    for key, weight in (("bear", 30), ("base", 50), ("bull", 30)):
        facts["scenarios"][key]["probability"] = weight
    codes = [w["code"] for w in memo_returns.check(memo_returns.compute(facts, as_of_year=2026))]
    assert codes == ["moic_above_undiluted", "irr_mismatch", "probabilities_do_not_sum"]


def test_a_stated_dilution_is_used_for_the_moic():
    facts = _facts()
    facts["scenarios"]["base"]["dilution_pct"] = 10
    facts["scenarios"]["base"]["moic"] = "2.5x"  # $221B × 0.9 / $61.5B = 3.2x
    warnings = memo_returns.check(memo_returns.compute(facts, as_of_year=2026))
    assert [(w["code"], w["scenario"]) for w in warnings] == [
        ("moic_mismatch", "base"),
        ("exit_value_mismatch", "bull"),
    ]


def test_the_walk_away_price_uses_the_stricter_bar_and_flags_a_higher_commit_price():
    facts = {
        "recommendation_sentence": (
            "Recommendation: BSH commits at or below $1.2T — the base case returns 1.9x."
        ),
        "entry": {"valuation": "$965B", "basis": "Series H"},
        "scenarios": {
            "bear": {"narrative": "a", "exit_year": "2031", "exit_value": "$0.9T", "moic": "0.9x"},
            "base": {"narrative": "b", "exit_year": "2031", "exit_value": "$1.95T", "moic": "1.9x"},
            "bull": {"narrative": "c", "exit_year": "2031", "exit_value": "$3.2T", "moic": "3.1x"},
        },
    }
    result = memo_returns.compute(facts, policy=POLICY, as_of_year=2026)
    # 20% over five years (2.49x) binds, not the 2.0x MOIC.
    assert result["hurdle"]["bar_moic"] == pytest.approx(1.2**5)
    assert result["walk_away_entry"] == pytest.approx(1.9 * 965e9 / 1.2**5)
    warnings = memo_returns.check(result, recommendation_sentence=facts["recommendation_sentence"])
    assert [w["code"] for w in warnings] == ["commit_above_walk_away"]
    assert "$737B" in warnings[0]["detail"]
    fine = "Recommendation: BSH commits at or below $700B."
    assert memo_returns.check(result, recommendation_sentence=fine) == []
    # No saved policy: no hurdle, no walk-away price, no warning.
    assert memo_returns.compute(facts, as_of_year=2026)["walk_away_entry"] is None


def test_preferences_come_from_the_cap_model_when_it_is_set():
    cap = {"pre_money_musd": 50_000, "new_money_musd": 11_500, "our_check_musd": 100, "liquidation_preference_x": 1.0, "participating": False}
    result = memo_returns.compute(ANTHROPIC, as_of_year=2026, cap_inputs=cap)
    # A 1x non-participating preference: the bear case converts above the
    # post-money, so the multiple is the as-converted one.
    assert result["scenarios"]["bear"]["pref_moic"] == pytest.approx(72_000 / 61_500, abs=0.01)


# ---- the pin sheet -------------------------------------------------------------------------


def test_apply_adds_notes_after_the_spines_own_and_is_idempotent():
    facts = _facts()
    for key, weight in (("bear", 30), ("base", 50), ("bull", 20)):
        facts["scenarios"][key]["probability"] = weight
    facts["scenarios"]["bull"]["exit_revenue"] = "$56B"
    outcome = memo_returns.apply(facts, policy=POLICY, as_of_year=2026)
    ids = [note["id"] for note in outcome["notes"]]
    assert ids == ["C5", "C6", "C7", "C8", "C9", "C10"]
    labels = [note["label"] for note in outcome["notes"]]
    assert labels == [
        "Probability-weighted MOIC",
        "Walk-away entry price",
        "Base-case IRR",
        "Breakeven entry price",
        "Required exit at this price",
        "Base-case IRR if the exit slips",
    ]
    weighted = outcome["notes"][0]
    assert weighted["result"] == "3.1x"  # 0.3 × 1.1 + 0.5 × 3.3 + 0.2 × 5.4
    assert {"name": "base case MOIC", "value": "3.3x", "ref": "C1"} in weighted["inputs"]
    assert facts["calculations"][-6:] == outcome["notes"]
    assert facts["returns"]["notes"] == {
        "probability_weighted_moic": "C5",
        "walk_away_entry": "C6",
        "base_irr": "C7",
        "breakeven_entry": "C8",
        "required": "C9",
        "exit_timing": "C10",
    }
    assert facts["returns"]["p_moic_below_1"] == "0%"
    assert len(facts["returns"]["grid"]["moic"]) == 3
    # No pinned revenue and no check on file: no growth note, no position.
    assert "implied_growth" not in facts["returns"] and "position" not in facts["returns"]
    assert outcome["warnings"] == []
    assert memo_returns.apply(facts, policy=POLICY, as_of_year=2026) is None
    assert len(facts["calculations"]) == 8


def test_the_pin_sheet_renders_the_computed_returns_only_when_present():
    facts = _facts()
    before = claude_runner._render_shared_facts_block(copy.deepcopy(facts), V2)
    memo_returns.apply(facts, policy=POLICY, as_of_year=2026)
    after = claude_runner._render_shared_facts_block(facts, V2)
    assert "Returns computed in Python" not in before
    assert "Returns computed in Python from these pins" in after
    assert "walk-away entry price" in after and "[C6]" in after
    assert "base-case MOIC by entry and exit multiple" in after
    # A v1 sheet never carries them: its bytes are unchanged.
    v1 = {"recommendation_sentence": "Recommendation: pass on X.", "scenarios": {"base": "2029: $1T; 1.5x"}}
    assert "Returns computed" not in claude_runner._render_shared_facts_block(v1)


def test_apply_python_returns_is_v2_only(tmp_path):
    run_dir = tmp_path / "2026-09-20__101500__acme__memo-run"
    events = []

    class Progress:
        def emit(self, *args, **kwargs):
            events.append(kwargs)

    v1_facts = _facts()
    assert claude_runner.apply_python_returns(v1_facts, memo_structure.LATE, run_dir=run_dir) == []
    assert "returns" not in v1_facts
    warnings = claude_runner.apply_python_returns(_facts(), V2, run_dir=run_dir, progress=Progress())
    assert [w["code"] for w in warnings] == ["exit_value_mismatch"]
    assert events[0]["stage"] == "memo_returns_computed"


# ---- the firm's hurdle -----------------------------------------------------------------------


def test_the_hurdle_is_pinned_verbatim_only_when_a_policy_is_saved(monkeypatch):
    facts: dict = {"return_hurdle": "the model's paraphrase"}
    assert claude_runner.pin_return_hurdle(facts, "late") is None
    assert facts["return_hurdle"] == "the model's paraphrase"  # unset policy: left alone
    fund_policy.save_policy({"stages": {"late": POLICY}})
    pinned = claude_runner.pin_return_hurdle(facts, "late")
    assert pinned == fund_policy.hurdle_text("late") == facts["return_hurdle"]
    assert pinned == "2x gross MOIC / 20% gross IRR over at most 5 years (late stage)"
    schema = claude_runner.spine_schema_with_return_hurdle(
        claude_runner.memo_fast_english_spine_schema(V2)
    )
    assert claude_runner._schema_errors(
        pinned, schema["properties"]["shared_facts"]["properties"]["return_hurdle"]
    ) == []
    # A hurdle line that would not fit the pinned field is not pinned.
    monkeypatch.setattr(claude_runner, "_memo_hurdle_text", lambda _stage: "x" * 201)
    other: dict = {}
    assert claude_runner.pin_return_hurdle(other, "late") is None and other == {}


def _with_decision_text(package: dict, text: str) -> dict:
    for section in package["sections"]:
        if section["id"] == "investment_decision":
            section["blocks"] = [{"type": "paragraph", "text": {"en": text, "zh": ""}}]
    return package


def test_the_decision_section_must_state_the_hurdle_by_its_figures():
    hurdle = "2x gross MOIC / 20% gross IRR over at most 5 years (late stage)"
    stated = _with_decision_text(
        late_v2_package(), "The base case returns 1.5x against our 2.0x / 20% late-stage hurdle [C2]."
    )
    result = memo_pin_check.check_package_pins(stated, {"return_hurdle": hurdle})
    assert not [f for f in result.findings if f.code == "return_hurdle_not_echoed"]
    missing = _with_decision_text(late_v2_package(), "The base case returns 1.5x.")
    findings = [
        f for f in memo_pin_check.check_package_pins(missing, {"return_hurdle": hurdle}).findings
        if f.code == "return_hurdle_not_echoed"
    ]
    assert len(findings) == 1 and findings[0].location == "investment_decision"
    assert "2x, 20%" in findings[0].detail
    # Unset policy: nothing is pinned and nothing is checked.
    assert not [
        f for f in memo_pin_check.check_package_pins(missing, {}).findings
        if f.code == "return_hurdle_not_echoed"
    ]


def test_spine_warnings_are_v2_only_and_never_part_of_the_gate():
    assert memo_pin_check.spine_warnings_v2(ANTHROPIC, memo_structure.LATE) == []
    assert [w["code"] for w in memo_pin_check.spine_warnings_v2(ANTHROPIC, V2, as_of_year=2026)] == [
        "exit_value_mismatch"
    ]
    # The gate's own verdict on the same sheet is untouched by the returns.
    gate_before = memo_pin_check.check_spine_pins_v2(copy.deepcopy(ANTHROPIC), V2)
    facts = copy.deepcopy(ANTHROPIC)
    memo_returns.apply(facts, as_of_year=2026)
    assert memo_pin_check.check_spine_pins_v2(facts, V2) == gate_before


def test_finalize_records_the_returns_disagreements_as_warnings(tmp_path):
    run_dir = tmp_path / "2026-09-20__101500__acme__memo-run"
    units = run_dir / "logs" / "english_units"
    units.mkdir(parents=True)
    (units / "spine.json").write_text(json.dumps({"shared_facts": ANTHROPIC}), encoding="utf-8")
    (run_dir / "logs" / "memo_package.en.json").write_text(json.dumps(late_v2_package()), encoding="utf-8")
    warnings = memo_analysis._RunWarnings()
    memo_analysis._returns_warning(run_dir, warnings)
    assert warnings.en == ["Returns arithmetic: 1 pinned figure disagrees with the recomputation"]
    assert warnings.zh == ["回报测算：1 处锁定数字与重新计算的结果不一致"]
    item = warnings.items[0]
    assert item["gate"] == "returns" and item["code"] == "exit_value_mismatch"
    assert item["summary_zh"].startswith("乐观情景")
    # A v1 run (no scorecard) records nothing.
    (run_dir / "logs" / "memo_package.en.json").write_text(json.dumps({"sections": []}), encoding="utf-8")
    empty = memo_analysis._RunWarnings()
    memo_analysis._returns_warning(run_dir, empty)
    assert not empty


# ---- the partner's price questions (R17) -----------------------------------------------------


def test_latest_revenue_picks_a_level_never_a_rate():
    metrics = [
        {"name": "Revenue growth", "value": "120%", "as_of": "2026"},
        {"name": "Revenue 2027E", "value": "$9B", "as_of": "2026"},
        {"name": "Gross margin", "value": "60%", "as_of": "2026"},
        {"name": "Run-rate revenue", "value": "$5B", "as_of": "2026-07", "source_ids": ["S2"]},
    ]
    found = memo_returns.latest_revenue(metrics)
    assert found["name"] == "Run-rate revenue"
    assert found["range"] == (5e9, 5e9) and found["ref"] == "S2" and found["as_of"] == "2026-07"
    assert memo_returns.latest_revenue([{"name": "ARR", "value": "Not disclosed"}]) is None
    # A bare number has no scale: ambiguous, so it is not a level.
    assert memo_returns.latest_revenue([{"name": "ARR", "value": "12"}]) is None


def test_what_has_to_be_true_at_this_price():
    facts = _facts()
    facts["key_metrics"] = [
        {"name": "Run-rate revenue", "value": "$5B", "as_of": "2026-07", "source_ids": ["S2"]}
    ]
    result = memo_returns.compute(facts, policy=POLICY, as_of_year=2026)
    # Base: a $221B exit and a 3.3x MOIC against $61.5B → 0.92 kept to exit.
    retention = result["base_retention"]
    assert retention == pytest.approx(3.3 / (221 / 61.5), abs=1e-6)
    assert result["breakeven_entry"] == pytest.approx(221e9 * retention)
    assert [row["target"] for row in result["required"]] == [1.0, 2.0, 3.0]
    one_x = result["required"][0]
    assert one_x["label"] == "return the money"
    assert one_x["exit_value"] == pytest.approx(61.5e9 / retention)
    assert one_x["revenue"] == pytest.approx(one_x["exit_value"] / 6.5)
    assert one_x["growth_pct"] == pytest.approx(((one_x["revenue"] / 5e9) ** (1 / 3) - 1) * 100)
    assert result["required"][1]["label"] == "clear the firm's bar"
    # Without a policy: the money and 3x only — the breakeven needs no bar.
    unset = memo_returns.compute(facts, as_of_year=2026)
    assert [row["target"] for row in unset["required"]] == [1.0, 3.0]
    assert unset["breakeven_entry"] == pytest.approx(result["breakeven_entry"])
    assert result["scenarios"]["base"]["implied_growth_pct"] == pytest.approx(
        ((34 / 5) ** (1 / 3) - 1) * 100
    )
    timing = result["exit_timing"]
    assert [row["exit_year"] for row in timing] == [2029, 2030, 2031]
    assert timing[0]["irr_pct"] > timing[1]["irr_pct"] > timing[2]["irr_pct"]
    # A company with no pinned revenue gets no growth lines — never an estimate.
    bare = memo_returns.compute(_facts(), as_of_year=2026)
    assert bare["latest_revenue"] is None
    assert all(row["implied_growth_pct"] is None for row in bare["scenarios"].values())
    assert all(row["growth_pct"] is None for row in bare["required"])


def test_the_price_question_notes_show_their_arithmetic():
    facts = _facts()
    facts["key_metrics"] = [{"name": "ARR", "value": "$5B", "as_of": "2026-07", "source_ids": ["S2"]}]
    outcome = memo_returns.apply(facts, policy=POLICY, as_of_year=2026)
    by_label = {note["label"]: note for note in outcome["notes"]}
    breakeven = by_label["Breakeven entry price"]
    assert breakeven["formula"] == "$221B × 0.918 = $203B"
    assert {"name": "share kept to exit, implied by the base case MOIC", "value": "0.918", "ref": "derived"} in breakeven["inputs"]
    assert "only the bull case" not in breakeven["meaning"]
    assert breakeven["result"] == "$203B"
    required = by_label["Required exit at this price"]
    assert required["formula"].startswith("$61.5B × 1.0x ÷ 0.918 = $67B; $67B ÷ 6.5x = $10.3B; $61.5B × 2.0x ÷ 0.918 = $134B")
    assert required["result"] == "$10.3B for 1.0x; $20.6B for 2.0x; $30.9B for 3.0x"
    assert "the base case assumes $34B, 6.8x today's $5B (89% a year)" in required["meaning"]
    growth = by_label["Implied revenue growth by case"]
    assert growth["result"] == "bear 34% / base 89% / bull 133% a year"
    assert {"name": "latest ARR", "value": "$5B", "ref": "S2"} in growth["inputs"]
    timing = by_label["Base-case IRR if the exit slips"]
    assert timing["result"] == "2029 49% / 2030 35% / 2031 27%"
    assert timing["meaning"].startswith("Each year the exit slips costs about 11 points")
    # The summary carries the same figures as strings.
    returns = facts["returns"]
    assert returns["breakeven_entry"] == "$203B"
    assert returns["required"][0] == {
        "target": "1.0x", "label": "return the money", "exit_value": "$67B", "revenue": "$10.3B", "growth": "27%"
    }
    assert returns["latest_revenue"] == "$5B (ARR, 2026-07)"
    assert returns["implied_growth"] == {"bear": "34%", "base": "89%", "bull": "133%"}
    assert returns["exit_timing"][2] == {"exit_year": "2031", "irr": "27%"}


def test_bsh_position_from_the_deal_terms_and_the_fund():
    terms = {"proposed_check_usd": 100e6, "post_money_usd": 61.5e9}
    result = memo_returns.compute(ANTHROPIC, as_of_year=2026, deal_terms=terms, fund_size_usd=2e9)
    position = result["position"]
    assert position["ownership_entry_pct"] == pytest.approx(100 / 61_500 * 100)
    base = position["cases"]["base"]
    assert base["proceeds"] == pytest.approx(221e9 * (100e6 / 61.5e9) * result["base_retention"])
    assert base["multiple"] == pytest.approx(3.3, abs=0.01)
    assert position["share_of_fund_pct"] == pytest.approx(5.0)
    bull = position["cases"]["bull"]
    assert bull["fund_pct"] == pytest.approx(bull["proceeds"] / 2e9 * 100)
    note = [n for n in memo_returns.calculation_notes(result, ANTHROPIC) if n["label"] == "BSH proceeds by case"][0]
    assert note["formula"].startswith("$100M ÷ $61.5B = 0.163%; $72B × 0.163% × 0.918 = $108M (1.1x)")
    assert {"name": "BSH check", "value": "$100M", "ref": "deal terms"} in note["inputs"]
    assert note["result"] == "bear $108M / base $330M / bull $547M"
    assert "The check is 5.0% of the $2B fund; the bull case returns 27% of the fund" in note["meaning"]
    # Without a post-money on the record the pinned entry stands in.
    entry_only = memo_returns.compute(ANTHROPIC, as_of_year=2026, deal_terms={"proposed_check_usd": 100e6})
    assert entry_only["position"]["post_money"] == 61.5e9
    assert entry_only["position"]["post_money_basis"] == "the pinned entry valuation"
    assert entry_only["position"]["share_of_fund_pct"] is None
    # No check on file: no position, no note.
    assert memo_returns.compute(ANTHROPIC, as_of_year=2026, deal_terms={"post_money_usd": 61.5e9})["position"] is None
    # The check against the policy's single-position limit is a warning.
    capped = memo_returns.compute(
        ANTHROPIC, as_of_year=2026, deal_terms=terms, fund_size_usd=2e9, policy={**POLICY, "max_position_pct": 4}
    )
    codes = [w["code"] for w in memo_returns.check(capped)]
    assert "position_above_policy" in codes
    detail = [w for w in memo_returns.check(capped) if w["code"] == "position_above_policy"][0]["detail"]
    assert detail == "the proposed $100M check is 5.0% of the $2B fund, above the 4% single-position limit in the fund policy"
    assert "position_above_policy" not in [w["code"] for w in memo_returns.check(result)]


def test_scenario_order_and_missing_dilution_are_flagged():
    facts = _facts()
    facts["scenarios"]["bear"].update({"exit_value": "$300B", "exit_revenue": "$50B", "moic": "4.9x"})
    result = memo_returns.compute(facts, as_of_year=2026)
    found = [w for w in memo_returns.check(result) if w["code"] == "scenario_order"]
    assert [w["scenario"] for w in found] == ["bear", "bear"]  # exit value, then MOIC
    assert found[0]["detail"] == "the bear case's exit value $300B is above the base case's $221B"
    assert found[1]["detail"] == "the bear case's MOIC 4.9x is above the base case's 3.3x"
    # A base MOIC that is exactly exit ÷ entry over a 3-year hold, no dilution pinned.
    naive = _facts()
    naive["scenarios"]["base"]["moic"] = "3.6x"  # $221B ÷ $61.5B
    warnings = memo_returns.check(memo_returns.compute(naive, as_of_year=2026))
    dilution = [w for w in warnings if w["code"] == "dilution_not_pinned"]
    assert len(dilution) == 1 and dilution[0]["scenario"] == "base"
    assert dilution[0]["detail"].startswith("the base case's MOIC 3.6x is its exit value ÷ entry with no dilution over a 3-year hold to 2029")
    # The shipped 3.3x has taken dilution, whatever the sheet says: left alone.
    assert "dilution_not_pinned" not in [
        w["code"] for w in memo_returns.check(memo_returns.compute(_facts(), as_of_year=2026))
    ]


def test_the_pin_sheet_renders_the_price_questions():
    facts = _facts()
    facts["key_metrics"] = [{"name": "ARR", "value": "$5B", "as_of": "2026-07", "source_ids": ["S2"]}]
    memo_returns.apply(
        facts,
        policy=POLICY,
        as_of_year=2026,
        deal_terms={"proposed_check_usd": 100e6, "post_money_usd": 61.5e9},
        fund_size_usd=2e9,
    )
    sheet = claude_runner._render_shared_facts_block(facts, V2)
    notes = facts["returns"]["notes"]
    assert (
        f"- what has to be true at this price [{notes['required']}]: to return the money (1.0x), "
        "$67B at exit — $10.3B of exit-year revenue at the base multiple (27% a year from the "
        "latest revenue); to clear the firm's bar (2.0x), $134B at exit"
    ) in sheet
    assert f"- breakeven entry price $203B [{notes['breakeven_entry']}]: the entry at which the base case returns 1.0x — above it the base case loses money\n" in sheet + "\n"
    assert (
        f"- implied revenue growth from $5B (ARR, 2026-07) [{notes['implied_growth']}]: "
        "bear 34% / base 89% / bull 133% a year"
    ) in sheet
    assert f"- base-case IRR if the exit slips [{notes['exit_timing']}]: 2029 49% / 2030 35% / 2031 27%" in sheet
    assert (
        f"- BSH's position [{notes['position']}]: a $100M check at $61.5B post-money (the post-money "
        "on the deal record) is 0.163% at entry; proceeds by case bear $108M (1.1x) / base $330M (3.3x) / "
        "bull $547M (5.5x); the check is 5.0% of the $2B fund, and the bull case returns 27% of the fund"
    ) in sheet


def test_memo_returns_inputs_read_the_deal_record_and_the_saved_fund_size(monkeypatch):
    from server import memo_inputs, portfolio

    terms = {"proposed_check_usd": 5e6, "post_money_usd": 1e9}
    monkeypatch.setattr(
        memo_inputs, "deal_terms", lambda cid: {"source": "deal_pipeline", "stage": "Term Sheet / IC", "terms": terms}
    )
    monkeypatch.setattr(
        portfolio,
        "get_reserves_settings",
        lambda: {"fund_size_musd": 200, "reserve_pct": 30, "notes": "", "updated_at": "2026-09-01T00:00:00Z"},
    )
    inputs = claude_runner.memo_returns_inputs("acme")
    assert inputs["deal_terms"] == terms and inputs["fund_size_usd"] == 200e6 and inputs["cap_inputs"] is None
    # A reserves file never saved is a placeholder: its fund size stays out.
    monkeypatch.setattr(portfolio, "get_reserves_settings", lambda: {"fund_size_musd": 200, "updated_at": None})
    assert claude_runner.memo_returns_inputs("acme")["fund_size_usd"] is None
    assert claude_runner.memo_returns_inputs(None) == {"cap_inputs": None, "deal_terms": None, "fund_size_usd": None}


@pytest.mark.parametrize(
    "text, year",
    [("2031", 2031), ("2031E", 2031), ("FY2025", 2025), ("exit 2029", 2029), ("2026-07", 2026), ("FY25", None), ("20310", None)],
)
def test_years_parse_next_to_letters(text, year):
    assert memo_returns.parse_year(text) == year


def test_growth_never_starts_from_an_estimate_or_a_backlog_and_counts_from_the_figures_year():
    # ZaiNar C2 pinned "$30M annualized estimate": the spine's own estimate,
    # not a disclosed level — no growth arithmetic may rest on it.
    assert memo_returns.latest_revenue(
        [{"name": "Baseline Contracted Revenue", "value": "$30M annualized estimate", "as_of": "2026-06"}]
    ) is None
    assert memo_returns.latest_revenue([{"name": "Revenue backlog", "value": "$450M", "as_of": "2026"}]) is None
    assert memo_returns.latest_revenue([{"name": "Revenue pipeline", "value": "$1.2B", "as_of": "2026"}]) is None
    # A FY2025 figure has four years to a 2029 exit, not three.
    facts = _facts()
    facts["key_metrics"] = [{"name": "Revenue", "value": "$5B", "as_of": "FY2025", "source_ids": ["S2"]}]
    result = memo_returns.compute(facts, as_of_year=2026)
    base = result["scenarios"]["base"]
    assert base["hold_years"] == 3 and base["growth_years"] == 4
    assert base["implied_growth_pct"] == pytest.approx(((34 / 5) ** (1 / 4) - 1) * 100)
    note = [n for n in memo_returns.calculation_notes(result, facts) if n["label"] == "Implied revenue growth by case"][0]
    assert "($34B ÷ $5B)^(1/4) − 1 = 61%" in note["formula"]
    assert note["meaning"].endswith("the base case needs 6.8x in 4 years.")
    # No year on the figure: the hold stands in.
    facts["key_metrics"][0]["as_of"] = "latest"
    assert memo_returns.compute(facts, as_of_year=2026)["scenarios"]["base"]["growth_years"] == 3


def test_formulas_carry_no_english_prose_for_the_chinese_table():
    facts = _facts()
    facts["key_metrics"] = [{"name": "ARR", "value": "$5B", "as_of": "2026-07", "source_ids": ["S2"]}]
    result = memo_returns.compute(
        facts,
        policy=POLICY,
        as_of_year=2026,
        deal_terms={"proposed_check_usd": 100e6, "post_money_usd": 61.5e9},
        fund_size_usd=2e9,
    )
    notes = memo_returns.calculation_notes(result, facts)
    new = [n for n in notes if n["label"] not in ("Walk-away entry price",)]
    assert len(new) == 6
    for note in new:
        assert not re.search(r"[A-Za-z]{3,}", note["formula"]), (note["label"], note["formula"])


def test_every_irr_formula_reproduces_its_result_from_the_figures_it_shows():
    # ZaiNar C2: a 1.24x base case printed as "1.2x^(1/3) − 1 = 7.4%" — the
    # figures shown give 6.3%.
    facts = _facts()
    facts["scenarios"]["base"]["moic"] = "1.24x"
    facts["scenarios"]["base"]["exit_value"] = "$83B"
    facts["scenarios"]["base"]["exit_revenue"] = "$12.8B"
    notes = memo_returns.calculation_notes(memo_returns.compute(facts, as_of_year=2026), facts)
    checked = 0
    for note in notes:
        for moic, years, pct in re.findall(r"(\d+(?:\.\d+)?)x\^\(1/(\d+(?:\.\d+)?)\) − 1 = (-?\d+(?:\.\d+)?)%", note["formula"]):
            recomputed = (float(moic) ** (1 / float(years)) - 1) * 100
            assert recomputed == pytest.approx(float(pct), abs=0.6), (note["label"], note["formula"])
            checked += 1
    assert checked >= 4  # the base-case IRR note and the three exit years


@pytest.mark.parametrize(
    "text, years",
    [
        ("3.5 years", 3.5),
        ("3.5 years (target exit 2029)", 3.5),
        ("3-4 years", 3.5),
        ("5 yrs", 5.0),
        ("a 4-year hold", 4.0),
        ("exit 2029", None),
        ("", None),
    ],
)
def test_the_pinned_holding_period_parses(text, years):
    assert memo_returns.parse_hold_years(text) == years


def test_the_irr_compounds_over_the_pinned_hold_when_it_agrees_with_the_exit_year():
    # ZaiNar 2026-09-23 (C3): a 3.5-year pin and a 16.5% base IRR, but the
    # IRR-by-exit-year line compounded over 2029 − 2026 = 3 years and read
    # "2029 19% / 2030 14% / 2031 11%" next to it.
    facts = _facts()
    facts["entry"]["holding_period"] = "3.5 years (target exit 2029)"
    result = memo_returns.compute(facts, as_of_year=2026)
    base = result["scenarios"]["base"]
    assert base["hold_years"] == 3.5
    assert base["irr_computed"] == pytest.approx((3.3 ** (1 / 3.5) - 1) * 100)
    assert [row["hold_years"] for row in result["exit_timing"]] == [3.5, 4.5, 5.5]
    note = next(
        n for n in memo_returns.calculation_notes(result, facts)
        if n["label"] == "Base-case IRR if the exit slips"
    )
    assert "3.30x^(1/3.5) − 1 = 41%; 3.30x^(1/4.5) − 1 = 30%" in note["formula"]
    assert {"name": "holding period", "value": "3.5 years (exit 2029)", "ref": "assumption"} in note["inputs"]
    # A pin more than a year away from the exit year is not the same hold:
    # the exit year decides.
    facts["entry"]["holding_period"] = "5 years"
    assert memo_returns.compute(facts, as_of_year=2026)["scenarios"]["base"]["hold_years"] == 3.0
