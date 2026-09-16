"""The word-budget retry loop, after the 2026-09-16 analysis.

Three Anthropic runs in a row spent two full regeneration rounds on
word-budget errors and still failed the gate; on the last of them
company_team went 1358 -> 1187 -> 1018 against a 750-word ceiling, and the
surgical repair pass then fixed it in one call. Regenerating from the same
inputs lands at the same natural length. Only editing converges.
"""
from __future__ import annotations

from server import memo_analysis, memo_docx_renderer, memo_structure

COMPACT = memo_structure.load_structure("late_compact", 1)

_BUDGET_ERR = (
    "section company_team runs 1018 English words against its 1100-word "
    "ceiling — this is the COMPACT memo: cut commentary"
)
_OTHER_ERR = "sections[1].blocks[9].text.zh is required"


def test_a_pure_budget_failure_skips_the_regeneration_rounds():
    assert memo_analysis._only_word_budget_errors([_BUDGET_ERR])
    assert memo_analysis._only_word_budget_errors([_BUDGET_ERR, _BUDGET_ERR])


def test_any_other_error_still_earns_a_regeneration():
    """Structural defects DO get fixed by rewriting, so they keep the
    retries; only the ceiling has proven immune to them."""
    assert not memo_analysis._only_word_budget_errors([_OTHER_ERR])
    assert not memo_analysis._only_word_budget_errors([_BUDGET_ERR, _OTHER_ERR])
    assert not memo_analysis._only_word_budget_errors([])


def test_the_ceilings_clear_the_drafts_the_memo_really_produces():
    """Observed first-attempt English lengths across the 2026-09-14 and
    2026-09-16 Anthropic runs. Every ceiling now clears its typical draft,
    so the ordinary run stops paying for retry rounds.

    company_team's worst draft (1358) still exceeds its ceiling, and that
    is deliberate: 1358 words in a compact memo IS the blowout the gate is
    for. It now costs one trim repair instead of three regeneration rounds.
    """
    typical = {
        "executive_summary": 729,
        "company_team": 1018,
        "thesis_market": 856,
        "business_financials": 751,
        "valuation_returns": 878,
        "risks": 741,
        "investment_decision": 850,
    }
    grace = memo_docx_renderer._BUDGET_GRACE
    for section in COMPACT.sections:
        seen = typical.get(section.id)
        if seen is None:
            continue
        assert section.budget_words * grace >= seen, (
            f"{section.id}: ceiling {section.budget_words} would have "
            f"rejected the {seen}-word draft this memo really produced"
        )


def test_every_compact_ceiling_grew():
    """The old ceilings sat below the natural draft length, which is what
    made the retry loop unavoidable rather than exceptional."""
    old_ceilings = {
        "executive_summary": 1200,
        "company_team": 750,
        "thesis_market": 650,
        "business_financials": 600,
        "valuation_returns": 750,
        "risks": 500,
        "investment_decision": 700,
    }
    for section in COMPACT.sections:
        previous = old_ceilings.get(section.id)
        if previous is None:
            continue
        assert section.budget_words >= previous, section.id


def test_every_compact_section_sets_its_own_hard_multiple():
    """Owner-set 2026-09-16. The multiples differ because a complete answer
    costs different amounts per section: the risk register's honest length
    depends on how many risks there are, a valuation summary's does not."""
    expected = {
        "executive_summary": 1.3,
        "company_team": 1.3,
        "thesis_market": 1.5,
        "business_financials": 1.5,
        "valuation_returns": 1.3,
        "risks": 2.0,
        "investment_decision": 1.5,
    }
    got = {
        s.id: s.budget_hard_multiple
        for s in COMPACT.sections
        if s.budget_words
    }
    assert got == expected


def test_the_gate_fires_at_the_cap_not_the_target():
    """A section between its target and its cap is finishing its argument,
    which is the behaviour the soft budget exists to allow."""
    risks = next(s for s in COMPACT.sections if s.id == "risks")
    assert risks.budget_words == 800 and risks.budget_hard_multiple == 2.0
    package = {
        "structure": {"stage": "late_compact", "version": 1},
        "sections": [
            {
                "id": "risks",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {"en": "word " * 1200, "zh": "x"},
                    }
                ],
            }
        ],
    }
    # 1200 words: half again over target, still well under the 1600 cap.
    assert not [
        e
        for e in memo_docx_renderer._word_budget_errors(package)
        if "hard cap" in e
    ]
    package["sections"][0]["blocks"][0]["text"]["en"] = "word " * 1700
    assert [
        e
        for e in memo_docx_renderer._word_budget_errors(package)
        if "hard cap" in e
    ]


def test_the_profile_prose_agrees_with_its_own_ceilings():
    """The prose said 3,200-3,800 words while the ceilings summed to 5,150,
    and the writer followed the ceilings. Two targets is no target."""
    from server import memo_prompts

    text = memo_prompts.load_prompt("structures/late_compact.md")
    total = sum(s.budget_words or 0 for s in COMPACT.sections)
    assert "5,000-6,000 words total" in text
    assert 5000 <= total <= 6700, total
