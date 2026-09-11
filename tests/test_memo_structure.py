"""Golden tests for the memo structure registry (Round 0).

The registry replaced ~16 scattered literals (section ids, numbered
titles, Chinese-parity regexes, section prompt contracts, component
routing, content floors, lint heading recognizers). Round 0 promised
ZERO behavior change, so this file pins every derivation byte-equal to
the literal it replaced. If a later round edits the late profile on
purpose, update the goldens alongside — a surprise diff here means the
profile drifted from what the gates enforce.
"""
from __future__ import annotations

import re

from server import memo_structure

LATE = memo_structure.LATE


# --- the old literals, verbatim -------------------------------------------

GOLDEN_SECTION_IDS = (
    "executive_summary",
    "company_overview",
    "investment_highlights",
    "investment_risk",
    "financial_forecast_valuation",
)

GOLDEN_SECTION_TITLES = {
    "executive_summary": {"en": "I. Executive Summary", "zh": "I. 执行摘要"},
    "company_overview": {"en": "II. Company Overview", "zh": "II. 公司概览"},
    "investment_highlights": {
        "en": "III. Investment Highlights",
        "zh": "III. 投资亮点",
    },
    "investment_risk": {"en": "IV. Investment Risk", "zh": "IV. 投资风险"},
    "financial_forecast_valuation": {
        "en": "V. Financial Forecast & Valuation",
        "zh": "V. 财务预测与估值",
    },
    "sources": {
        "en": "VI. Sources, Source Classes, and Fact Reference Index",
        "zh": "VI. 来源、来源类别与事实索引",
    },
    "validation_log": {
        "en": "Appendix: Source Treatment And Assumptions",
        "zh": "附录：来源处理与假设",
    },
}

GOLDEN_PARITY_PATTERNS = {
    "executive_summary": {
        "en": r"^\s*(?:(?:i|1)[\.\、]\s*)?executive\s+summary\s*[:：]?\s*$",
        "zh": r"^\s*(?:(?:i|1|一)[\.\、]\s*)?(?:执行摘要|核心摘要)\s*[:：]?\s*$",
    },
    "company_overview": {
        "en": r"^\s*(?:(?:ii|2)[\.\、]\s*)?company\s+overview\s*[:：]?\s*$",
        "zh": r"^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司概览|公司概况|项目简介)\s*[:：]?\s*$",
    },
    "investment_highlights": {
        "en": r"^\s*(?:(?:iii|3)[\.\、]\s*)?investment\s+highlights\s*[:：]?\s*$",
        "zh": r"^\s*(?:(?:iii|3|三)[\.\、]\s*)?投资亮点\s*[:：]?\s*$",
    },
    "investment_risk": {
        "en": r"^\s*(?:(?:iv|4)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$",
        "zh": r"^\s*(?:(?:iv|4|四)[\.\、]\s*)?投资风险\s*[:：]?\s*$",
    },
    "financial_forecast_valuation": {
        "en": (
            r"^\s*(?:(?:v|5)[\.\、]\s*)?financial\s+forecast\s+(?:&|and)\s+valuation"
            r"\s*[:：]?\s*$"
        ),
        "zh": r"^\s*(?:(?:v|5|五)[\.\、]\s*)?财务预测与估值\s*[:：]?\s*$",
    },
    "sources": {
        "en": (
            r"^\s*(?:(?:vi|6)[\.\、]\s*)?sources?"
            r"(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?"
            r"\s*[:：]?\s*$"
        ),
        "zh": (
            r"^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)"
            r"\s*[:：]?\s*$"
        ),
    },
}

GOLDEN_COMPONENT_SECTION = {
    "key_metrics_snapshot": "executive_summary",
    "board": "company_overview",
    "revenue": "company_overview",
    "key_operating_metrics": "company_overview",
    "competitive_analysis": "investment_highlights",
    "replacement_coexistence": "investment_highlights",
    "moat": "investment_highlights",
    "risk_register": "investment_risk",
    "disconfirming_evidence": "investment_risk",
    "time_base_integrity": "financial_forecast_valuation",
    "growth_bridge": "financial_forecast_valuation",
    "scenario_analysis": "financial_forecast_valuation",
    "deal_terms": "financial_forecast_valuation",
    "evidence_thresholds": "financial_forecast_valuation",
    "investment_decision": "financial_forecast_valuation",
    "disclosures": "financial_forecast_valuation",
}

# source_index is envelope-rendered (the Sources section), so it has a
# component definition but no owning body section.
GOLDEN_COMPONENT_IDS = set(GOLDEN_COMPONENT_SECTION) | {"source_index"}

GOLDEN_TITLE_WORDS = {
    "executive summary": "executive_summary",
    "company overview": "company_overview",
    "investment highlights": "investment_highlights",
    "investment risk": "investment_risk",
    "financial forecast & valuation": "financial_forecast_valuation",
    "financial forecast and valuation": "financial_forecast_valuation",
}

GOLDEN_PASS_AFFINITY = {
    "company_overview": frozenset(
        {"deployment_behavior", "gtm_operating_burden"}
    ),
    "investment_highlights": frozenset(
        {"replacement_coexistence", "competitive_rights"}
    ),
    "investment_risk": frozenset(
        {"alternative_explanations", "competitive_rights"}
    ),
    "financial_forecast_valuation": frozenset(
        {"arithmetic_denominators", "time_base", "growth_bridge"}
    ),
}

GOLDEN_LINT_TITLE_SET = frozenset(
    {
        "executive summary",
        "company overview",
        "investment highlights",
        "investment risk",
        "financial forecast & valuation",
        "financial forecast and valuation",
        "investment decision / closing view",
        "closing view",
        "investment decision",
        "key metrics snapshot",
        "sources",
        "references",
    }
)


# --- derivation goldens ----------------------------------------------------


def test_section_ids_match_old_literal():
    assert LATE.section_ids == GOLDEN_SECTION_IDS


def test_section_titles_match_old_literal():
    assert LATE.section_titles() == GOLDEN_SECTION_TITLES


def test_parity_patterns_match_old_literals():
    patterns = LATE.parity_patterns()
    assert set(patterns) == set(GOLDEN_PARITY_PATTERNS)
    for section_id, locales in GOLDEN_PARITY_PATTERNS.items():
        for locale, source in locales.items():
            compiled = patterns[section_id][locale]
            assert compiled.pattern == source, (section_id, locale)
            assert compiled.flags & re.IGNORECASE


def test_component_section_matches_old_literal():
    assert LATE.component_section() == GOLDEN_COMPONENT_SECTION


def test_components_cover_all_seventeen():
    ids = [component["id"] for component in LATE.components]
    assert len(ids) == 17
    assert set(ids) == GOLDEN_COMPONENT_IDS
    for component in LATE.components:
        assert component["label"]
        assert component["block_types"]
        assert component["patterns"]


def test_title_words_match_old_literal():
    assert LATE.title_words() == GOLDEN_TITLE_WORDS


def test_pass_affinity_matches_old_literal():
    assert LATE.pass_affinity() == GOLDEN_PASS_AFFINITY


def test_content_floors_match_old_behavior():
    floors = LATE.content_floors()
    assert set(floors) == set(GOLDEN_SECTION_IDS)
    assert floors["executive_summary"].min_real_blocks == 2
    assert not floors["executive_summary"].bullets_or_prose
    assert floors["investment_highlights"].bullets_or_prose
    assert floors["investment_risk"].bullets_or_prose
    assert floors["financial_forecast_valuation"].require_valuation_refs
    assert floors["company_overview"] == memo_structure.ContentFloor()


def test_numbered_prefix_pattern_matches_old_regex():
    pattern = LATE.numbered_prefix_pattern()
    assert pattern.pattern == r"^(i|ii|iii|iv|v|vi)\.\s+"
    assert pattern.match("iv. investment risk")
    assert not pattern.match("vii. anything")


def test_lint_section_titles_match_old_literal_set():
    assert LATE.lint_section_titles() == GOLDEN_LINT_TITLE_SET


def test_numbered_lint_key_for_risk():
    assert LATE.numbered_lint_key("risk") == "iv. investment risk"


def test_roles_resolve_to_pin_check_sections():
    assert LATE.section_for_role("exec").id == "executive_summary"
    assert LATE.section_for_role("risk").id == "investment_risk"
    assert (
        LATE.section_for_role("valuation").id == "financial_forecast_valuation"
    )


def test_section_specs_present_and_nonempty():
    specs = LATE.section_specs()
    assert set(specs) == set(GOLDEN_SECTION_IDS)
    for section_id, spec in specs.items():
        assert spec.strip(), section_id
        # every contract names its own section id's title words
        assert len(spec) > 200, section_id


# --- profile invariants (hold for every stage profile) ---------------------


def test_profile_invariants():
    structure = LATE
    assert structure.stage == "late"
    assert structure.version == 1
    ids = structure.section_ids
    assert len(set(ids)) == len(ids)
    routed = set(structure.component_section().values())
    assert routed <= set(ids)
    for section in structure.sections:
        assert section.en_title == section.en_title.strip()
        assert not section.en_title[:1].isdigit()
        assert not re.match(r"^[ivxIVX]+\.", section.en_title)


def test_load_structure_is_cached_and_clearable():
    first = memo_structure.load_structure("late")
    assert first is memo_structure.load_structure("late")
    memo_structure.clear_cache()
    reloaded = memo_structure.load_structure("late")
    assert reloaded is not first
    assert reloaded.section_ids == first.section_ids


def test_unknown_role_raises():
    import pytest

    with pytest.raises(KeyError):
        LATE.section_for_role("nonexistent")
