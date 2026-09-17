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

def _real_budget_error(section_id="company_team"):
    """The error the RENDERER actually writes for an over-long section.

    Built, never typed. A hand-written fixture let the shortcut die
    unnoticed: the marker still said "-word ceiling" after the message
    became "...-word target and its ...-word hard cap", so the live
    2026-09-16 re-run paid a full regeneration for a 42-word overrun.
    """
    sdef = COMPACT.section(section_id)
    cap = int(
        sdef.budget_words
        * (sdef.budget_hard_multiple or memo_docx_renderer._BUDGET_GRACE)
    )
    package = {
        "structure": COMPACT.meta(),
        "sections": [
            {
                "id": section_id,
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {"en": "word " * (cap + 50), "zh": ""},
                    }
                ],
            }
        ],
    }
    errors = memo_docx_renderer._word_budget_errors(package)
    assert errors, "the renderer must flag a section past its hard cap"
    return errors[0]


_BUDGET_ERR = _real_budget_error()
_OTHER_ERR = "sections[1].blocks[9].text.zh is required"


def test_the_shortcut_recognises_the_renderers_own_wording():
    """The guard against the two drifting apart."""
    assert memo_analysis._WORD_BUDGET_ERROR_MARKER in _BUDGET_ERR
    assert memo_analysis._only_word_budget_errors([_BUDGET_ERR])


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
    assert risks.budget_hard_multiple and risks.budget_hard_multiple > 1
    # Derived, never typed: the budgets move whenever the founder asks for
    # a longer report, and a hand-written number here would quietly stop
    # testing what it claims to.
    target = risks.budget_words
    cap = int(target * risks.budget_hard_multiple)
    between = (target + cap) // 2
    package = {
        "structure": {"stage": "late_compact", "version": 1},
        "sections": [
            {
                "id": "risks",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {"en": "word " * between, "zh": "x"},
                    }
                ],
            }
        ],
    }
    # over target, still under the cap
    assert not [
        e
        for e in memo_docx_renderer._word_budget_errors(package)
        if "hard cap" in e
    ]
    package["sections"][0]["blocks"][0]["text"]["en"] = "word " * (cap + 100)
    assert [
        e
        for e in memo_docx_renderer._word_budget_errors(package)
        if "hard cap" in e
    ]


def test_the_profile_prose_agrees_with_its_own_ceilings():
    """The prose said 3,200-3,800 words while the ceilings summed to 5,150,
    and the writer followed the ceilings. Two targets is no target.

    Read the range OUT of the prose rather than restating it, so raising
    the budgets can never leave the profile telling the writer one number
    and the gate enforcing another.
    """
    import re

    from server import memo_prompts

    text = memo_prompts.load_prompt("structures/late_compact.md")
    match = re.search(r"roughly ([\d,]+)-([\d,]+) words", text)
    assert match, "the profile must state its own word range in prose"
    low, high = (int(g.replace(",", "")) for g in match.groups())
    total = sum(s.budget_words or 0 for s in COMPACT.sections)
    assert low <= total <= high, (low, total, high)


def test_every_section_prose_agrees_with_its_own_budget():
    """The failure this test exists for, live 2026-09-16.

    The budgets went from 6,700 words to 16,000 in the yaml, but five of
    the seven section contracts still opened "400-550 words." The writers
    split the difference and came in at 39-88% of target — the whole run
    landed at ~9,000 words when 16,000 was asked for, and it had to be
    cancelled. The profile's own intro warns about exactly this: "Two
    targets is no target." Nothing checked it per section.
    """
    import re

    from server import memo_prompts

    text = memo_prompts.load_prompt("structures/late_compact.md")
    for section in COMPACT.sections:
        if not section.budget_words:
            continue
        body = text.split(f"## section: {section.id}\n", 1)
        assert len(body) == 2, section.id
        after_yaml = body[1].split("```", 2)[-1].strip()
        match = re.match(r"([\d,]+)-([\d,]+) words", after_yaml)
        assert match, (
            f"{section.id}: the contract must open by stating its own word "
            f"range, so the writer is never told two different numbers"
        )
        low, high = (int(g.replace(",", "")) for g in match.groups())
        assert low <= section.budget_words <= high, (
            f"{section.id}: prose says {low}-{high} words but budget_words "
            f"is {section.budget_words}"
        )


def test_the_spine_and_the_renderer_agree_on_how_many_risks():
    """Live 2026-09-17: they did not, and the run could not be saved.

    The spine's cap was raised to ten for the 16,000-word memo while the
    renderer's card gate still demanded four to six. A run that pinned ten
    risks wrote ten cards, the gate rejected the package, and no retry
    could fix it — the contract said one card per pinned risk.
    """
    from server import claude_runner, memo_structure

    for structure, expected in (
        (memo_structure.LATE, memo_structure.RISK_COUNT_V1),
        (COMPACT, memo_structure.RISK_COUNT_V2),
        (memo_structure.load_structure("late", 2), memo_structure.RISK_COUNT_V2),
    ):
        low, high = memo_structure.risk_count_bounds(structure)
        assert (low, high) == expected, structure.stage
        risks = claude_runner.memo_fast_english_spine_schema(structure)[
            "properties"
        ]["shared_facts"]["properties"]["risks"]
        assert risks["minItems"] == low, structure.stage
        assert risks["maxItems"] == high, structure.stage


def test_the_risk_gate_accepts_the_most_risks_the_spine_can_pin():
    """The exact package the last run produced must now validate."""
    from server import memo_structure
    from tests import test_memo_subsections_charts as fixtures

    package = fixtures._v2_gen_package(COMPACT)
    risk_id = COMPACT.section_for_role("risk").id
    section = next(s for s in package["sections"] if s["id"] == risk_id)
    card_blocks = [
        b for b in section["blocks"] if str(b.get("type")) == "heading"
        and str(fixtures.memo_docx_renderer._content_text(b.get("text"))).startswith("Risk ")
    ]
    assert card_blocks, "the fixture must carry risk cards"
    # grow the register to the maximum the spine may pin
    _low, high = memo_structure.risk_count_bounds(COMPACT)
    existing = len(card_blocks)
    for n in range(existing + 1, high + 1):
        section["blocks"].extend(fixtures._risk_card(n, max(1, 10 - n)))
    errors = [
        e
        for e in memo_docx_renderer.english_package_validation_errors(package)
        if "risk cards" in e or "per-risk cards" in e
    ]
    assert errors == [], errors
