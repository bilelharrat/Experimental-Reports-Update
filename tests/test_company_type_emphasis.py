"""Company type decides where the report spends its words.

Owner, 2026-09-16: "Different types of companies may have different
things to write more about, and we should adjust accordingly... we should
also use [skills/memo/types] to decide which parts of the report are more
important and should spend more budget to explain."

Emphasis is a claim about PROPORTION, so it is renormalized back onto the
profile's own total: a type can move words between sections, never add
them. Only the owner editing `budget_words` changes how long the memo is.
"""
from __future__ import annotations

import pytest

from server import memo_structure

COMPACT = memo_structure.load_structure("late_compact", 1)
TYPES_WITH_EMPHASIS = [
    key
    for key in memo_structure.COMPANY_TYPE_KEYS
    if (profile := memo_structure.load_company_type(key))
    and profile.section_emphasis
]


def _total(structure):
    return sum(s.budget_words or 0 for s in structure.sections)


def test_at_least_the_five_focus_verticals_declare_emphasis():
    assert len(TYPES_WITH_EMPHASIS) >= 5
    assert "other" not in TYPES_WITH_EMPHASIS  # the fallback stays neutral


@pytest.mark.parametrize("company_type", TYPES_WITH_EMPHASIS)
def test_emphasis_moves_words_without_adding_any(company_type):
    typed = memo_structure.load_structure("late_compact", 1, company_type)
    base_total = _total(COMPACT)
    # rounding lands each section on a 50-word step, so allow one step per
    # budgeted section
    steps = sum(1 for s in COMPACT.sections if s.budget_words)
    assert abs(_total(typed) - base_total) <= 50 * steps // 2
    assert _total(typed) > 0


@pytest.mark.parametrize("company_type", TYPES_WITH_EMPHASIS)
def test_emphasis_only_names_sections_that_exist(company_type):
    """A typo'd section id would silently do nothing at all."""
    profile = memo_structure.load_company_type(company_type)
    for section_id in profile.section_emphasis:
        assert section_id in COMPACT.section_ids, (company_type, section_id)


@pytest.mark.parametrize("company_type", TYPES_WITH_EMPHASIS)
def test_emphasis_points_the_way_it_says(company_type):
    profile = memo_structure.load_company_type(company_type)
    typed = memo_structure.load_structure("late_compact", 1, company_type)
    for section_id, multiplier in profile.section_emphasis.items():
        base = COMPACT.section(section_id).budget_words
        after = typed.section(section_id).budget_words
        if multiplier > 1.05:
            assert after > base, (company_type, section_id, base, after)
        elif multiplier < 0.95:
            assert after < base, (company_type, section_id, base, after)


def test_a_foundation_model_spends_more_on_position_and_moat():
    """Its scorecard puts 36 of 100 on industry position and moat, which
    is the argument thesis_market carries."""
    typed = memo_structure.load_structure(
        "late_compact", 1, "ai_foundation_model"
    )
    assert typed.section("thesis_market").budget_words > COMPACT.section(
        "thesis_market"
    ).budget_words


def test_robotics_spends_more_on_the_team_than_a_video_company():
    robotics = memo_structure.load_structure("late_compact", 1, "robotics")
    video = memo_structure.load_structure(
        "late_compact", 1, "ai_video_short_drama"
    )
    assert (
        robotics.section("company_team").budget_words
        > video.section("company_team").budget_words
    )


def test_an_unknown_or_neutral_type_changes_nothing():
    for company_type in (None, "other"):
        typed = memo_structure.load_structure(
            "late_compact", 1, company_type
        )
        for section in COMPACT.sections:
            assert (
                typed.section(section.id).budget_words
                == section.budget_words
            ), (company_type, section.id)


def test_an_extreme_multiplier_is_clamped():
    sections = COMPACT.sections
    wild = memo_structure._emphasized_sections(
        sections, {"risks": 99.0, "executive_summary": 0.001}
    )
    base = {s.id: s.budget_words for s in sections}
    got = {s.id: s.budget_words for s in wild}
    # risks cannot swallow the report, and the summary cannot vanish
    assert got["risks"] < base["risks"] * memo_structure._EMPHASIS_MAX
    assert got["executive_summary"] > 0
    assert abs(sum(got.values()) - sum(base.values())) <= 400


def test_a_profile_without_budgets_is_left_alone():
    """late v2 declares no word budgets; emphasis has nothing to re-cut."""
    v2 = memo_structure.load_structure("late", 2)
    assert all(s.budget_words is None for s in v2.sections)
    same = memo_structure._emphasized_sections(v2.sections, {"risks": 2.0})
    assert same == v2.sections
