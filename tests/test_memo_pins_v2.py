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
            },
            {
                "summary": "Revenue concentration exposes half of ARR to one renewal",
                "rating": "7/10",
                "likelihood": "Medium",
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


def test_card_gate_accepts_six_row_cards_for_v2(tmp_path):
    from server import memo_docx_renderer

    labels_v2 = [label for _p, label in memo_docx_renderer._RISK_CARD_ROW_LABELS_V2]
    package = {
        "structure": V2.meta(),
        "sections": [
            {"id": "investment_risk", "blocks": _risk_card_blocks(labels_v2)}
        ],
    }
    errors = memo_docx_renderer._risk_card_format_errors(package)
    assert errors == [], errors
    # five-row cards (the v1 shape) fail the v2 gate and the error names
    # six rows including Mitigation
    labels_v1 = [label for _p, label in memo_docx_renderer._RISK_CARD_ROW_LABELS]
    package["sections"][0]["blocks"] = _risk_card_blocks(labels_v1)
    errors = memo_docx_renderer._risk_card_format_errors(package)
    assert any("six two-cell rows" in e and "Mitigation" in e for e in errors)


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
