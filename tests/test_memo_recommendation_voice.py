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
