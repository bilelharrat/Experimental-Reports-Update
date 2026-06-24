from __future__ import annotations

from docx import Document

from server import memo_quality_lint


def _save_docx(path, paragraphs=(), tables=()):
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    for rows in tables:
        table = document.add_table(rows=len(rows), cols=len(rows[0]))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                table.cell(row_index, col_index).text = value
    document.save(path)


def test_linter_catches_source_scaffold_fuzzy_em_dash_and_disclosure_gaps(tmp_path):
    path = tmp_path / "bad-memo.docx"
    _save_docx(
        path,
        paragraphs=[
            "I. Executive Summary",
            "ZaiNar has no battery cost [WV SPV memo].",
            "CRITICAL REALITY CHECK (for BSH)",
            "A real technical asset behind a hard IP wall (present-state).",
            "A soft instrument into an unclosed round.",
            "Revenue not disclosed. ARR not disclosed.",
            "Series A2, ~$3.0B pre-money — closing imminent.",
            "What Is Not Yet Underwritten",
            "Conditional Yes at the minimum ticket.",
        ],
        tables=[
            [
                ["Metric", "Value"],
                ["Last priced valuation", "~$1.0B post-money [companies.yaml]"],
            ],
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)
    codes = {finding.code for finding in result.findings}

    assert result.has_blocking_findings is True
    assert {
        "source_token_leak",
        "operating_table_source_token",
        "internal_artifact_leak",
        "scaffold_label",
        "banned_fuzzy_phrase",
        "em_dash_bridge",
        "disclosure_gap_without_treatment",
        "sell_side_voice_violation",
    }.issubset(codes)


def test_linter_allows_source_ids_in_fact_index_and_source_class_in_tables(tmp_path):
    path = tmp_path / "clean-memo.docx"
    document = Document()
    document.add_paragraph("I. Executive Summary")
    document.add_paragraph(
        "ZaiNar is company-reported to have named commercial momentum. "
        "Revenue is not disclosed; model treatment uses a customer-count "
        "proxy and funding diligence threshold."
    )
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Treatment"
    table.cell(1, 0).text = "Commercial signals"
    table.cell(1, 1).text = "company-reported; no source token here"
    table.cell(2, 0).text = "Recognized revenue"
    table.cell(2, 1).text = (
        "Not disclosed; model does not infer ARR from MOU headlines."
    )
    document.add_paragraph("VI. Sources, Source Classes, and Fact Reference Index")
    document.add_paragraph(
        "[S1] WV SPV memo, company-originated, used for transaction terms."
    )
    document.add_paragraph(
        "[S2] companies.yaml, internal registry, used only for fact index."
    )
    document.save(path)

    result = memo_quality_lint.lint_memo_docx(path)

    assert result.p0_findings == []


def test_linter_does_not_flag_wv_deal_party_as_artifact(tmp_path):
    # "WV" is Wisdom Ventures, a real deal counterparty (WV-ZaiNar SPV) — not an
    # internal file artifact. It must not trip internal_artifact_leak.
    path = tmp_path / "wv-memo.docx"
    _save_docx(
        path,
        paragraphs=[
            "I. Executive Summary",
            "BSH co-invests through the WV-ZaiNar SPV on a SAFE, bearing "
            "20% non-WV carry.",
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)

    assert not any(f.code == "internal_artifact_leak" for f in result.findings)


def test_linter_treats_disclosure_gap_via_sibling_note_cell(tmp_path):
    # A "Not disclosed" value paired with treatment / characterization in the
    # row's Note column is adequately treated and must not be flagged.
    path = tmp_path / "row-treated.docx"
    _save_docx(
        path,
        paragraphs=["II. Company Overview"],
        tables=[
            [
                ["Metric", "Value", "Note"],
                ["Gross margin / burn / NRR", "Not disclosed", "Confirmation items"],
                ["Revenue at date", "Not disclosed", "Undefined (no denominator)"],
            ],
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)

    assert not any(
        f.code == "disclosure_gap_without_treatment" for f in result.findings
    )


def test_linter_still_flags_untreated_disclosure_gap(tmp_path):
    # A bare "Not disclosed" cell with no treatment anywhere in its row must
    # still be flagged — the row-aware fix must not neuter the gate.
    path = tmp_path / "row-untreated.docx"
    _save_docx(
        path,
        paragraphs=["II. Company Overview"],
        tables=[
            [
                ["Metric", "Value"],
                ["Active users", "Not disclosed"],
            ],
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)

    assert any(
        f.code == "disclosure_gap_without_treatment" for f in result.findings
    )


def test_linter_blocks_buyer_side_language_in_final_body(tmp_path):
    path = tmp_path / "buyer-side-language.docx"
    _save_docx(
        path,
        paragraphs=[
            "I. Executive Summary",
            "Recommendation: Conditional Yes at the minimum ticket.",
            "Top 3 Gating Questions (for BSH)",
            "What Is Not Yet Underwritten",
            "BSH target allocation: $5-10M.",
            "The final section says what BSH should do and the position size.",
            "Require data room access, a named institutional lead, MFN, "
            "down-round protection, information rights, and voting rights.",
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)

    assert result.has_blocking_findings is True
    assert any(f.code == "sell_side_voice_violation" for f in result.findings)


def test_linter_blocks_third_person_recommendation_voice(tmp_path):
    path = tmp_path / "third-person-recommendation.docx"
    _save_docx(
        path,
        paragraphs=[
            "I. Executive Summary",
            "The opportunity offered to investors is a sponsor-backed SPV interest.",
            "The base case credits commercial pull before revenue is disclosed.",
            "The recommendation is Proceed if confirmed: participate in the SPV.",
            "The right posture is proceed if confirmed only if contracts bind.",
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)
    snippets = " ".join(f.snippet for f in result.findings)

    assert result.has_blocking_findings is True
    assert any(f.code == "sell_side_voice_violation" for f in result.findings)
    assert "The recommendation is" in snippets
    assert "The opportunity offered to investors is" in snippets


def test_linter_allows_gating_questions_as_investment_memo_language(tmp_path):
    path = tmp_path / "gating-questions.docx"
    _save_docx(
        path,
        paragraphs=[
            "I. Executive Summary",
            "Top 3 Gating Questions",
            "Does binding deployment evidence support the current allocation?",
            "Can carrier conversion produce upside without assuming all MOUs become revenue?",
        ],
    )

    result = memo_quality_lint.lint_memo_docx(path)

    assert not any(f.code == "sell_side_voice_violation" for f in result.findings)
