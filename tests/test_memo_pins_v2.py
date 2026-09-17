"""Round 4 of the report restructure: the v2 pin sheet (verdict,
scorecard, fair value, entry, object scenarios), its deterministic spine
gate, the package pin-check extensions, and Risk Card v2."""
from __future__ import annotations

import copy

from server import claude_runner, memo_pin_check, memo_structure

V2 = memo_structure.load_structure("late", 2)
GROWTH = memo_structure.load_structure("growth", 1)
EARLY = memo_structure.load_structure("early", 1)


def _good_shared_facts() -> dict:
    weights = V2.scorecard_weights()
    # Watch band: total 70-79. Distribute scores deterministically.
    scores = {
        "market_size_growth": 12,
        "industry_position": 11,
        "moat": 10,
        "revenue_growth_quality": 11,
        "business_model_ue": 8,
        "team_governance": 7,
        "valuation": 6,
        "exit_certainty": 4,
        "risk_reward": 3,
    }
    assert sum(scores.values()) == 72
    assert all(scores[k] <= weights[k] for k in scores)
    return {
        "recommendation_sentence": (
            "Recommendation: watch Acme — the price already assumes the "
            "2027 plan."
        ),
        "key_metrics": [
            {"name": "ARR", "value": "$24M", "as_of": "2026-06"},
        ],
        "scenarios": {
            "bear": {
                "narrative": "Enterprise conversion stalls",
                "exit_year": "2029",
                "exit_revenue": "$40M",
                "exit_multiple": "6x",
                "exit_value": "$240M",
                "moic": "0.2x",
                "irr": "-35%",
            },
            "base": {
                "narrative": "Plan lands late but lands",
                "exit_year": "2030",
                "exit_revenue": "$120M",
                "exit_multiple": "10x",
                "exit_value": "$1.2B",
                "moic": "1.1x",
                "irr": "2%",
            },
            "bull": {
                "narrative": "Category leadership",
                "exit_year": "2030",
                "exit_revenue": "$250M",
                "exit_multiple": "14x",
                "exit_value": "$3.5B",
                "moic": "3.2x",
                "irr": "34%",
            },
        },
        "risks": [
            {
                "summary": (
                    "The entry price already assumes success — ordinary "
                    "execution earns nothing"
                ),
                "rating": "9/10",
                "likelihood": "High",
                "area": "valuation_exit",
                "impact": "the base case returns 1.1x, barely our money back",
            },
            {
                "summary": "Revenue concentration exposes half of ARR to one renewal",
                "rating": "7/10",
                "likelihood": "Medium",
                "area": "concentration",
                "impact": "one lost renewal removes $12M of the $24M ARR",
            },
        ],
        "highlights": [
            {
                "dimension": "market_size_growth",
                "headline": "The market is large enough to carry the price.",
                "evidence": [
                    "Gartner sizes 2026 spend at $8B, growing 30% a year.",
                    "The memo's own estimate reaches $25B by 2030.",
                ],
            },
            {
                "dimension": "industry_position",
                "headline": "Acme leads its category rather than chasing it.",
                "evidence": [
                    "It holds 40% of enterprise spend per the 2025 survey.",
                    "It is the only vendor on all three clouds.",
                ],
            },
            {
                "dimension": "revenue_growth_quality",
                "headline": "Growth is real and mostly recurring.",
                "evidence": [
                    "ARR tripled in twelve months to $24M.",
                    "Net revenue retention is 118%.",
                ],
            },
        ],
        "stage": "late",
        "verdict": "Watch",
        "scorecard": {
            "total": 72,
            "dimensions": {
                key: {"score": scores[key], "why": f"why {key}"}
                for key in scores
            },
        },
        "fair_value_range": {
            "low": "$600M",
            "high": "$900M",
            "basis": "growth-adjusted comps",
        },
        "entry": {
            "valuation": "$1.0B",
            "basis": "current round pre-money",
            "holding_period": "4-5 years",
        },
        "calculations": [
            {
                "id": "C1",
                "label": "Scenario exit values and multiples",
                "inputs": [
                    {"name": "entry valuation", "value": "$1.0B", "ref": "S1"},
                    {"name": "exit multiples", "value": "6x/10x/14x", "ref": "assumption"},
                ],
                "formula": (
                    "bear 6x × $40M = $240M → 0.2x; base 10x × $120M = $1.2B → "
                    "1.1x; bull 14x × $250M = $3.5B → 3.2x"
                ),
                "result": "0.2x / 1.1x / 3.2x",
                "meaning": "Only the bull case clears a venture return.",
            },
            {
                "id": "C2",
                "label": "Fair value range",
                "inputs": [
                    {"name": "ARR", "value": "$24M", "ref": "S1"},
                    {"name": "comp multiples", "value": "25-37x", "ref": "S2"},
                ],
                "formula": "25x × $24M = $600M; 37x × $24M = $900M",
                "result": "$600M - $900M",
                "meaning": "The round price sits above the range.",
            },
        ],
    }


# ---- spine schema ----------------------------------------------------------


def test_v2_spine_schema_extends_shared_facts():
    schema = claude_runner.memo_fast_english_spine_schema(V2)
    facts = schema["properties"]["shared_facts"]
    for key in ("stage", "verdict", "scorecard", "fair_value_range", "entry"):
        assert key in facts["properties"], key
        assert key in facts["required"], key
    dims = facts["properties"]["scorecard"]["properties"]["dimensions"]
    assert tuple(dims["properties"]) == memo_structure.SCORECARD_DIMENSION_KEYS
    score_schema = dims["properties"]["market_size_growth"]["properties"]["score"]
    assert score_schema["maximum"] == max(V2.scorecard_weights().values())
    # scenarios became objects
    bear = facts["properties"]["scenarios"]["properties"]["bear"]
    assert bear["type"] == "object"
    assert "moic" in bear["properties"]


def test_v1_spine_schema_untouched():
    schema = claude_runner.memo_fast_english_spine_schema(memo_structure.LATE)
    assert schema is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    facts = schema["properties"]["shared_facts"]
    assert "verdict" not in facts["properties"]
    assert facts["properties"]["scenarios"]["properties"]["bear"]["type"] == "string"


# ---- deterministic spine gate ----------------------------------------------


def test_gate_passes_good_sheet():
    assert memo_pin_check.check_spine_pins_v2(_good_shared_facts(), V2) == []


def test_gate_is_noop_for_v1():
    assert memo_pin_check.check_spine_pins_v2({}, memo_structure.LATE) == []


def test_gate_catches_total_mismatch():
    facts = _good_shared_facts()
    facts["scorecard"]["total"] = 80
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("does not equal the sum" in p for p in problems)


def test_gate_catches_verdict_band_mismatch():
    facts = _good_shared_facts()
    facts["verdict"] = "Strong Buy"  # total is 72
    facts["recommendation_sentence"] = (
        "Recommendation: BSH commits $5M to Acme at the current round."
    )
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("requires a scorecard total between" in p for p in problems)


def test_gate_catches_stance_conflict():
    facts = _good_shared_facts()
    # verdict Watch but the sentence commits
    facts["recommendation_sentence"] = (
        "Recommendation: BSH commits $5M to Acme at the current round."
    )
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("conflicts with the recommendation" in p for p in problems)


def test_gate_catches_score_over_weight():
    facts = _good_shared_facts()
    facts["scorecard"]["dimensions"]["exit_certainty"]["score"] = 9  # max 5
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("exit_certainty" in p and "between 0 and 5" in p for p in problems)


def test_gate_catches_topic_label_risk_summary():
    facts = _good_shared_facts()
    facts["risks"].append({"summary": "Entry price", "rating": "8/10"})
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("topic label" in p for p in problems)


def test_gate_accepts_long_summary_with_unlisted_verb():
    """Live run 2026-09-11: 'commitments behave like senior obligations'
    was flagged because 'behave' was not in the curated verb list. A
    summary long enough to be a sentence must never fail the gate."""
    facts = _good_shared_facts()
    facts["risks"].append(
        {
            "summary": (
                "More than $275B of multi-year compute commitments behave "
                "like senior obligations and become stranded cost if "
                "growth decelerates"
            ),
            "rating": "8/10",
        }
    )
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert not any("topic label" in p for p in problems), problems


def test_gate_handles_trillion_scale_values():
    """Live run 2026-09-11: '$1.05T' parsed as 1.05 dollars, breaking
    the fair-value ordering and MOIC ratio checks for Anthropic-scale
    companies."""
    assert memo_pin_check._parse_money("$1.05T") == 1.05e12
    assert memo_pin_check._parse_money("1.2 trillion") == 1.2e12
    facts = _good_shared_facts()
    facts["fair_value_range"] = {
        "low": "$300B",
        "high": "$1.05T",
        "basis": "growth-adjusted comps",
    }
    facts["entry"]["valuation"] = "$350B"
    facts["scenarios"]["base"].update(
        {"exit_value": "$1.2T", "moic": "1.4x"}
    )
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert not any("low exceeds high" in p for p in problems), problems
    assert not any("inconsistent with" in p for p in problems), problems


def test_gate_catches_fictional_moic():
    facts = _good_shared_facts()
    facts["scenarios"]["base"]["moic"] = "9.0x"  # exit 1.2B / entry 1.0B
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("inconsistent with" in p for p in problems)


def test_gate_catches_wrong_stage():
    facts = _good_shared_facts()
    facts["stage"] = "early"
    problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("does not match the run's classified stage" in p for p in problems)


def test_gate_weights_respect_stage_profile():
    facts = _good_shared_facts()
    facts["stage"] = "early"
    # team_governance max is 25 for early; 20 is legal there, illegal for late
    facts["scorecard"]["dimensions"]["team_governance"]["score"] = 20
    facts["scorecard"]["total"] = 85
    facts["verdict"] = "Strong Buy"
    facts["recommendation_sentence"] = (
        "Recommendation: BSH commits $1M to Acme's seed round."
    )
    late_problems = memo_pin_check.check_spine_pins_v2(facts, V2)
    assert any("between 0 and 10" in p for p in late_problems)
    early_problems = memo_pin_check.check_spine_pins_v2(facts, EARLY)
    assert not any("team_governance" in p for p in early_problems)


# ---- shared-facts block rendering ------------------------------------------


def test_facts_block_renders_v2_pins():
    block = claude_runner._render_shared_facts_block(_good_shared_facts(), V2)
    assert "Verdict: Watch (观察名单) — 72/100" in block
    assert "market_size_growth (owner: market_industry): 12 of 15" in block
    assert "Fair value range: $600M - $900M" in block
    assert "Entry: $1.0B" in block
    assert "gross MOIC 1.1x" in block
    assert "This dimension scores {score} of {max}" in block


def test_facts_block_renders_case_summary_highlights_and_risk_areas():
    block = claude_runner._render_shared_facts_block(_good_shared_facts(), V2)
    # The opening sentence: strong dimensions = the pinned highlights in
    # pinned order, the thinnest two = the lowest score-to-weight ratios.
    assert (
        '"The case rests on market size and growth (12/15), industry '
        "position (11/15) and revenue growth and quality (11/15); it is "
        'thinnest on valuation (6/10) and risk-reward balance (3/5)."'
    ) in block
    assert "Investment highlights (exactly these three" in block
    assert (
        "1. [market size and growth (12/15)] The market is large enough to "
        "carry the price."
    ) in block
    assert "   - Gartner sizes 2026 spend at $8B" in block
    assert (
        "1. [Valuation & exit] The entry price already assumes success — "
        "ordinary execution earns nothing — Impact: the base case returns "
        "1.1x, barely our money back — 9/10 (High)"
    ) in block


def test_spine_schema_requires_highlights_area_and_impact():
    schema = claude_runner.memo_fast_english_spine_schema(V2)
    facts = schema["properties"]["shared_facts"]
    assert "highlights" in facts["required"]
    highlights = facts["properties"]["highlights"]
    assert highlights["minItems"] == 3 and highlights["maxItems"] == 3
    assert highlights["items"]["properties"]["dimension"]["enum"] == list(
        memo_structure.SCORECARD_DIMENSION_KEYS
    )
    risk_item = facts["properties"]["risks"]["items"]
    assert risk_item["properties"]["area"]["enum"] == list(
        memo_structure.RISK_AREA_KEYS
    )
    assert set(risk_item["required"]) >= {"area", "impact", "likelihood"}
    # v1 risks stay as they were (no area/impact).
    v1_item = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA["properties"][
        "shared_facts"
    ]["properties"]["risks"]["items"]
    assert "area" not in v1_item["properties"]


def test_gate_checks_highlights():
    facts = _good_shared_facts()
    assert memo_pin_check.check_spine_pins_v2(facts, V2) == []
    two = copy.deepcopy(facts)
    two["highlights"] = two["highlights"][:2]
    assert any(
        "exactly three" in p for p in memo_pin_check.check_spine_pins_v2(two, V2)
    )
    dup = copy.deepcopy(facts)
    dup["highlights"][1]["dimension"] = "market_size_growth"
    assert any(
        "used twice" in p for p in memo_pin_check.check_spine_pins_v2(dup, V2)
    )
    weak = copy.deepcopy(facts)
    weak["highlights"][2]["dimension"] = "risk_reward"  # 3 of 5 = 60% passes
    assert memo_pin_check.check_spine_pins_v2(weak, V2) == []
    weak["highlights"][2]["dimension"] = "valuation"  # 6 of 10 = 60% passes
    assert memo_pin_check.check_spine_pins_v2(weak, V2) == []
    weak["scorecard"]["dimensions"]["valuation"]["score"] = 5
    weak["scorecard"]["total"] = 71
    problems = memo_pin_check.check_spine_pins_v2(weak, V2)
    assert any("below 60%" in p and "valuation" in p for p in problems)
    label = copy.deepcopy(facts)
    label["highlights"][0]["headline"] = "Market size"
    assert any(
        "topic label" in p for p in memo_pin_check.check_spine_pins_v2(label, V2)
    )


def test_package_pin_check_flags_missing_highlight_and_impact_echo():
    facts = _good_shared_facts()
    package = _echoing_package(facts)
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"] = [
        b
        for b in exec_section["blocks"]
        if "Acme leads its category" not in b["text"]["en"]
        and "one lost renewal" not in b["text"]["en"]
    ]
    result = memo_pin_check.check_package_pins(package, facts)
    codes = {(f.code, f.location) for f in result.findings}
    assert ("highlight_not_echoed", "executive_summary") in codes
    assert ("risk_impact_not_echoed", "executive_summary") in codes
    # The risk section still carries every impact, so no risk-section finding.
    assert ("risk_impact_not_echoed", "investment_risk") not in codes


def test_facts_block_v1_output_unchanged():
    sheet = {
        "recommendation_sentence": "Recommendation: watch Acme.",
        "key_metrics": [
            {"name": "ARR", "value": "$24M", "as_of": "2026-06"}
        ],
        "scenarios": {"bear": "b", "base": "m", "bull": "t"},
        "risks": [{"summary": "risk one", "rating": "8/10"}],
    }
    block = claude_runner._render_shared_facts_block(sheet)
    assert block == (
        "## Shared fact sheet (pinned — repeat these exactly)\n"
        "Recommendation sentence: Recommendation: watch Acme.\n"
        "Key metrics:\n"
        "- ARR: $24M (as of 2026-06)\n"
        "Scenarios:\n"
        "- bear: b\n"
        "- base: m\n"
        "- bull: t\n"
        "Risk list (ordered by rating, highest first):\n"
        "1. risk one — 8/10"
    )


# ---- package pin-check extensions ------------------------------------------


def _echoing_package(facts: dict) -> dict:
    weights = V2.scorecard_weights()
    dimensions = facts["scorecard"]["dimensions"]
    sections = []
    for section_id in V2.section_ids:
        texts = ["Body prose for the section."]
        section = V2.section(section_id)
        for dimension in section.scorecard_dimensions:
            entry = dimensions[dimension]
            texts.append(
                f"This dimension scores {entry['score']} of "
                f"{weights[dimension]}."
            )
        if section_id == "executive_summary":
            texts.append(facts["recommendation_sentence"])
            texts.append("Watch — 72/100.")
            texts.append("ARR stands at $24M as of June 2026.")
            for item in facts.get("highlights") or []:
                texts.append(f"{item['headline']} {' '.join(item['evidence'])}")
            for risk in facts["risks"][:3]:
                texts.append(
                    f"Valuation & exit — {risk['summary']}. Impact: "
                    f"{risk['impact']}. ({risk['rating']}, High likelihood)"
                )
        if section_id == "investment_decision":
            texts.append("Watch — 72/100.")
            for dimension in memo_structure.SCORECARD_DIMENSION_KEYS:
                texts.append(dimensions[dimension]["why"])
            texts.append("Fair value range $600M to $900M.")
        if section_id == "valuation":
            texts.append("Fair value range: $600M to $900M.")
        if section_id == "returns_exit":
            for key in ("bear", "base", "bull"):
                scenario = facts["scenarios"][key]
                texts.append(
                    " ".join(
                        str(scenario[f])
                        for f in (
                            "exit_year",
                            "exit_revenue",
                            "exit_multiple",
                            "exit_value",
                            "moic",
                            "irr",
                        )
                    )
                )
        if section_id == "investment_risk":
            for risk in facts["risks"]:
                texts.append(f"{risk['summary']} — {risk['rating']}")
                if risk.get("impact"):
                    texts.append(f"Impact: {risk['impact']}.")
        sections.append(
            {
                "id": section_id,
                "blocks": [
                    {"type": "paragraph", "text": {"en": text}}
                    for text in texts
                ],
            }
        )
    return {
        "structure": V2.meta(),
        "company": {"name": {"en": "Acme"}},
        "sources": [{"id": "s1"}],
        "sections": sections,
    }


def test_package_pin_check_passes_full_v2_echo():
    facts = _good_shared_facts()
    package = _echoing_package(facts)
    result = memo_pin_check.check_package_pins(package, facts)
    assert result.ok, [finding.to_dict() for finding in result.findings]


def test_package_pin_check_flags_missing_dimension_echo():
    facts = _good_shared_facts()
    package = _echoing_package(facts)
    moat_section = next(s for s in package["sections"] if s["id"] == "moat")
    moat_section["blocks"] = [
        {"type": "paragraph", "text": {"en": "No score sentence here."}}
    ]
    result = memo_pin_check.check_package_pins(package, facts)
    codes = {finding.code for finding in result.findings}
    assert "scorecard_dimension_not_echoed" in codes


def test_package_pin_check_flags_missing_verdict_and_why():
    facts = _good_shared_facts()
    package = _echoing_package(facts)
    decision = next(
        s for s in package["sections"] if s["id"] == "investment_decision"
    )
    decision["blocks"] = [
        {"type": "paragraph", "text": {"en": "A decision without echoes."}}
    ]
    result = memo_pin_check.check_package_pins(package, facts)
    codes = {finding.code for finding in result.findings}
    assert "verdict_not_echoed" in codes
    assert "scorecard_why_not_echoed" in codes


def test_package_pin_check_v1_untouched_by_v2_checks():
    facts = {
        "recommendation_sentence": "Recommendation: watch Acme.",
        "key_metrics": [],
        "scenarios": {"bear": "", "base": "", "bull": ""},
        "risks": [],
    }
    package = {
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {"en": "Recommendation: watch Acme."},
                    }
                ],
            }
        ]
    }
    result = memo_pin_check.check_package_pins(package, facts)
    assert result.ok


# ---- Risk Card v2 ----------------------------------------------------------


def test_risk_contract_selection():
    assert (
        claude_runner.memo_risk_register_contract(memo_structure.LATE)
        is claude_runner.MEMO_RISK_REGISTER_CONTRACT
    )
    assert claude_runner.memo_risk_register_contract(None) is (
        claude_runner.MEMO_RISK_REGISTER_CONTRACT
    )
    for structure in (V2, GROWTH, EARLY):
        contract = claude_runner.memo_risk_register_contract(structure)
        assert "Mitigation" in contract
        assert "缓释措施" in contract
        assert "No structural mitigation exists" in contract


def _risk_card_blocks(labels: list[str]) -> list[dict]:
    blocks: list[dict] = [
        {"type": "paragraph", "text": {"en": "Where the risk concentrates."}}
    ]
    for index in range(1, 5):
        blocks.append(
            {
                "type": "heading",
                "level": 3,
                "text": {
                    "en": (
                        f"Risk {index}: The concentration risk number "
                        f"{index} erodes the return case"
                    )
                },
            }
        )
        rows = []
        for label in labels:
            value = {
                "Risk Type": "Commercial",
                "Verdict": (
                    f"The concentration risk number {index} erodes the "
                    "return case."
                ),
                "Impact": "one lost renewal removes half of ARR.",
                "Why it matters": (
                    "Half of ARR renews in one quarter; a single loss cuts "
                    "revenue growth to zero and burns cash reserves."
                ),
                "What we watch": "Q3 renewal notices from the top account",
                "Mitigation": (
                    "No structural mitigation exists. Position sizing must "
                    "carry the risk."
                ),
                "Likelihood": "Medium: renewal history is short",
                "Risk Rating": f"{10 - index}/10: could break the case",
            }[label]
            rows.append([{"en": label}, {"en": value}])
        blocks.append(
            {
                "type": "table",
                "component": "risk_register",
                "layout": "key_value",
                "headers": [],
                "rows": rows,
            }
        )
    return blocks


def test_card_gate_accepts_eight_row_cards_for_v2(tmp_path):
    from server import memo_docx_renderer

    labels_v2 = [label for _p, label in memo_docx_renderer._RISK_CARD_ROW_LABELS_V2]
    assert labels_v2 == [
        "Risk Type",
        "Verdict",
        "Impact",
        "Why it matters",
        "What we watch",
        "Mitigation",
        "Likelihood",
        "Risk Rating",
    ]
    package = {
        "structure": V2.meta(),
        "sections": [
            {"id": "investment_risk", "blocks": _risk_card_blocks(labels_v2)}
        ],
    }
    errors = memo_docx_renderer._risk_card_format_errors(package)
    assert errors == [], errors
    # five-row cards (the v1 shape) fail the v2 gate and the error names
    # eight rows including Verdict, Impact and Mitigation
    labels_v1 = [label for _p, label in memo_docx_renderer._RISK_CARD_ROW_LABELS]
    package["sections"][0]["blocks"] = _risk_card_blocks(labels_v1)
    errors = memo_docx_renderer._risk_card_format_errors(package)
    assert any(
        "eight two-cell rows" in e and "Impact" in e and "Mitigation" in e
        for e in errors
    )


def test_card_gate_keeps_five_rows_for_v1():
    from server import memo_docx_renderer

    labels_v1 = [label for _p, label in memo_docx_renderer._RISK_CARD_ROW_LABELS]
    package = {
        "sections": [
            {"id": "investment_risk", "blocks": _risk_card_blocks(labels_v1)}
        ]
    }
    errors = memo_docx_renderer._risk_card_format_errors(package)
    assert errors == [], errors


# ---- gate wiring -----------------------------------------------------------


def test_parallel_wrapper_respins_spine_on_gate_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    good = _good_shared_facts()
    bad = copy.deepcopy(good)
    bad["scorecard"]["total"] = 99  # fails the sum check

    skeleton = {
        "company": {"name": {"en": "Acme"}},
        "sources": [{"id": "s1"}],
    }
    calls = {"count": 0}

    def fake_spine(**kwargs):
        calls["count"] += 1
        facts = bad if calls["count"] == 1 else good
        if calls["count"] > 1:
            assert "does not equal the sum" in (
                kwargs.get("validation_feedback") or ""
            )
        return (
            {"package_skeleton": skeleton, "shared_facts": facts},
            None,
        )

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", fake_spine
    )

    captured_jobs = {}

    def fake_section(**kwargs):
        captured_jobs[kwargs["section_id"]] = kwargs
        return (
            {
                "section": {"id": kwargs["section_id"], "blocks": []},
                "claude_cost_usd": 0,
                "claude_duration_ms": 1,
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    def fake_artifacts(**kwargs):
        return {"analysis_artifacts": {}}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts", fake_artifacts
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=tmp_path / "settings.json",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "a.docx", "zh": "b.docx"},
        structure=V2,
    )
    assert error is None, error
    assert calls["count"] == 2  # one gate-failing spine + one respin
    package = result["memo_package"]
    assert package["structure"] == V2.meta()
    assert len(package["sections"]) == len(V2.section_ids)


def _tied_dimensions() -> tuple[dict, dict]:
    """Three dimensions tied at exactly 0.500 on different weights.

    Taken from the 2026-09-17 compact run: business model 6/12,
    valuation 4/8 and risk-reward 2/4 all scored 0.500 at once.
    """
    weights = {
        "market_size_growth": 12,
        "industry_position": 18,
        "moat": 18,
        "revenue_growth_quality": 12,
        "business_model_ue": 12,
        "team_governance": 12,
        "valuation": 8,
        "exit_certainty": 4,
        "risk_reward": 4,
    }
    scores = {
        "market_size_growth": 11,
        "industry_position": 15,
        "moat": 12,
        "revenue_growth_quality": 10,
        "business_model_ue": 6,
        "team_governance": 8,
        "valuation": 4,
        "exit_certainty": 3,
        "risk_reward": 2,
    }
    dimensions = {
        key: {"score": score, "why": "why.", "evidence": ["e."]}
        for key, score in scores.items()
    }
    return dimensions, weights


def test_case_summary_says_thinnest_not_weak():
    """The scan bands by an absolute threshold and calls 0.500 `adequate`.
    This sentence ranks, so it must not use a threshold word: the
    2026-09-17 memo called business model a weak point in its opening
    line and adequate four lines later, off the same 6/12."""
    dimensions, weights = _tied_dimensions()
    lines = claude_runner._render_case_summary_lines({}, dimensions, weights)
    summary = lines[0]
    assert "it is thinnest on" in summary
    assert "weak point" not in summary
    # Same numbers, banded: nothing here is actually weak.
    scan = "\n".join(lines)
    assert "business model and unit economics — 6/12, adequate" in scan


def test_tied_thinnest_dimensions_break_by_weight_not_key_order():
    """business model (6/12), valuation (4/8) and risk-reward (2/4) all
    sit at 0.500. Key order alone picked two of the three arbitrarily;
    the heavier weight is the one that costs the reader more, so it is
    named first."""
    dimensions, weights = _tied_dimensions()
    summary = claude_runner._render_case_summary_lines(
        {}, dimensions, weights
    )[0]
    thinnest = summary.split("it is thinnest on", 1)[1]
    assert thinnest.index("business model and unit economics (6/12)") < (
        thinnest.index("valuation (4/8)")
    )
    assert "risk-reward" not in thinnest

    # Give risk-reward the heaviest weight and it leads instead.
    heavy = dict(weights, risk_reward=20)
    dimensions["risk_reward"]["score"] = 10
    summary = claude_runner._render_case_summary_lines({}, dimensions, heavy)[0]
    thinnest = summary.split("it is thinnest on", 1)[1]
    assert thinnest.index("risk-reward balance (10/20)") < (
        thinnest.index("business model and unit economics (6/12)")
    )
