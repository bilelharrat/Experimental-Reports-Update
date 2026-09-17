"""Canonical recommendation-voice forms: contract, lint, and rewriter agree.

The memo's conclusion is a recommendation ("Recommendation: BSH commits
$X to ..."), never a decided action ("BSH is committing ..."). The one
legitimate decided sentence is the pinned decision history ("BSH made the
decision to ... on ... because ..."). These tests pin the three pieces of
machinery to the same fixture strings so they can never oscillate:
the lint must accept the canonical forms and reject decided language,
and the deterministic rewriter must convert decided language while never
touching a decision-history sentence.
"""
from __future__ import annotations

from docx import Document

from server import memo_structure
from server import memo_analysis, memo_quality_lint

CANONICAL_SENTENCES = (
    "Recommendation: BSH commits $3,000,000 to the SPV, leaving $7,000,000 "
    "for co-investors.",
    "Recommendation: pass on Generalist — the entry price assumes proof the "
    "sources do not show.",
    "Recommendation: watch Generalist — revisit once the Series C terms are "
    "disclosed.",
)

HISTORY_SENTENCE = (
    "BSH made the decision to pass on 2026-01-05 because the valuation was "
    "too rich."
)

# A history sentence whose human-entered reason itself contains decided
# phrasing — the sentence-scoped exemption must still cover it.
HISTORY_WITH_DECIDED_REASON = (
    "BSH made the decision to invest on 2026-01-05 because BSH is committing "
    "to the category long-term."
)


def _save_docx(path, paragraphs):
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)


def test_canonical_forms_pass_lint(tmp_path):
    path = tmp_path / "memo.docx"
    _save_docx(
        path,
        [
            "I. Executive Summary",
            *CANONICAL_SENTENCES,
            HISTORY_SENTENCE,
            HISTORY_WITH_DECIDED_REASON,
        ],
    )
    result = memo_quality_lint.lint_memo_docx(path)
    assert result.has_blocking_findings is False, [
        f.to_dict() for f in result.findings
    ]


def test_decided_language_fails_lint(tmp_path):
    for bad in (
        "BSH is committing $3,000,000 to the SPV.",
        "BSH is investing in Generalist at the disclosed terms.",
        "BSH is not committing capital to Generalist.",
    ):
        path = tmp_path / "memo.docx"
        _save_docx(path, ["I. Executive Summary", bad])
        result = memo_quality_lint.lint_memo_docx(path)
        codes = {f.code for f in result.findings}
        assert "decided_voice_violation" in codes, bad


def test_rewriter_converts_decided_language():
    assert (
        memo_analysis._rewrite_memo_package_voice_text(
            "BSH is committing capital to Generalist."
        )
        == "Recommendation: BSH commits capital to Generalist."
    )
    assert memo_analysis._rewrite_memo_package_voice_text(
        "BSH is committing $3,000,000, leaving $7,000,000 for co-investors."
    ).startswith("Recommendation: BSH commits $3,000,000")
    assert (
        memo_analysis._rewrite_memo_package_voice_text(
            "BSH is not committing capital to Generalist."
        )
        == "Recommendation: pass on Generalist."
    )


def test_rewriter_never_touches_history_sentences():
    for sentence in (HISTORY_SENTENCE, HISTORY_WITH_DECIDED_REASON):
        assert (
            memo_analysis._rewrite_memo_package_voice_text(sentence)
            == sentence
        )
    # Mixed text: the decided sentence converts, the history one survives.
    mixed = f"{HISTORY_WITH_DECIDED_REASON} BSH is committing capital to X."
    out = memo_analysis._rewrite_memo_package_voice_text(mixed)
    assert HISTORY_WITH_DECIDED_REASON in out
    assert "Recommendation: BSH commits capital to X." in out


def test_canonical_forms_survive_the_rewriter():
    for sentence in CANONICAL_SENTENCES:
        assert (
            memo_analysis._rewrite_memo_package_voice_text(sentence)
            == sentence
        )


# ---- the six moves ----------------------------------------------------------


def test_the_addendum_names_the_six_moves():
    """The founder's own refinement of a live passage, turned into a shape.

    Her complaint across several rounds was never that a number was wrong
    — it was that the memo assumed the reader already knew whether the
    number was good. The calibrating move ("what counts as normal HERE")
    is the one that answers that, and it is the one most often missing.
    """
    from server import memo_prompts

    text = memo_prompts.load_prompt("structure_addendum.md")
    assert "## The six moves" in text
    for move in (
        "Say the point, in plain words",
        "Show the arithmetic",
        "Say what it costs",
        "say what counts as normal HERE",
        "Say what to check",
        "say why the rating is what it is",
    ):
        assert move in text, move
    # the worked example must carry a calculation reference and a rating
    # with its reason, or it is not modelling the shape it describes
    assert "[C4]" in text
    assert "What to check:" in text
    assert "likelihood high, because the price range is already public" in text


def test_the_chinese_twin_carries_the_founders_own_words():
    """The zh file is what the founder's team edits, so the example there
    is her text verbatim, not a translation of my translation."""
    zh = (
        memo_structure.STRUCTURES_DIR.parent / "zh" / "structure_addendum.md"
    ).read_text(encoding="utf-8")
    assert "## 六个动作" in zh
    assert "要点核查：" in zh
    assert "单项假设偏差即可将投资变为亏损" in zh
