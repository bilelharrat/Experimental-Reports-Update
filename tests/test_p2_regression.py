"""Regression set for the memo gates: the four ZaiNar packages of
2026-09-23 (Claude standard v1, Gemini standard v1, Gemini IC-template v2,
and the Claude IC-template v2 English draft that failed its final check).

Every renderer / lint / parity / fact-check change must keep these
validating, rendering and linting — without a model call and without
touching the real data/ directory (everything renders into tmp_path).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import (
    memo_chinese_parity,
    memo_docx_renderer,
    memo_fact_check,
    memo_quality_lint,
    memo_quality_metrics,
    memo_structure,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BILINGUAL = ("zainar_claude_v1", "zainar_gemini_v1", "zainar_gemini_v2")
ENGLISH_DRAFT = "zainar_v2_draft.en"

# Codes added in round 2 — none may ever be P0.
P2_LINT_CODES = {"figure_without_anchor", "claim_restated", "figure_restated_across_sections"}
P2_PARITY_CODES = {"zh_line_untranslated", "citation_glued", "term_drift"}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def render_pair(tmp_path: Path, name: str, package: dict) -> tuple[Path, Path]:
    out_en = tmp_path / name / "memo" / "en.docx"
    out_zh = tmp_path / name / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(
        package, out_en=out_en, out_zh=out_zh, strict_sources=False
    )
    return out_en, out_zh


@pytest.mark.parametrize("name", BILINGUAL)
def test_finished_packages_validate_render_and_lint(tmp_path, name):
    package = load_fixture(name)
    assert memo_docx_renderer.validate_package(package, strict_sources=False) == []
    out_en, out_zh = render_pair(tmp_path, name, package)
    assert out_en.stat().st_size > 10_000 and out_zh.stat().st_size > 10_000
    structure = memo_structure.for_package(package)

    lint = memo_quality_lint.lint_memo_docx(out_en, structure)
    assert not lint.has_blocking_findings, [f.to_dict() for f in lint.p0_findings]
    assert {f.severity for f in lint.findings if f.code in P2_LINT_CODES} <= {"P1", "P2"}

    parity = memo_chinese_parity.lint_chinese_memo_pair(
        out_en, out_zh, structure, package=package
    )
    assert not parity.has_blocking_findings, [f.to_dict() for f in parity.p0_findings]
    assert {f.severity for f in parity.findings if f.code in P2_PARITY_CODES} <= {"P1", "P2"}


def test_english_draft_validates_renders_and_lints(tmp_path):
    """The draft failed live on word caps and one URL-less source; with the
    legacy source rule it validates, renders and lints — the caps are the
    English gate's, not the renderer's."""
    package = load_fixture(ENGLISH_DRAFT)
    filled = memo_docx_renderer.fill_blank_zh_placeholders(package)
    warnings = memo_docx_renderer.validate_package(filled, strict_sources=False)
    assert len(warnings) == 1 and "sources[17].url" in warnings[0]
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert errors, "the draft failed live; it must still fail the English gate"
    assert all("-word hard cap" in e or "sources[17].url" in e for e in errors), errors
    assert sum("-word hard cap" in e for e in errors) == 2

    out_en = tmp_path / ENGLISH_DRAFT / "memo" / "en.docx"
    result = memo_docx_renderer.render_memo_locale(
        package, "en", out_en, strict_sources=False
    )
    assert result["ok"] and out_en.exists()
    structure = memo_structure.for_package(package)
    lint = memo_quality_lint.lint_memo_docx(out_en, structure)
    codes = {f.code for f in lint.findings}
    # The draft restates its figures and claims across sections (A3).
    assert "claim_restated" in codes and "figure_restated_across_sections" in codes
    restated = [f for f in lint.findings if f.code == "figure_restated_across_sections"]
    assert any("2.2x" in f.snippet or "1.73x" in f.snippet for f in restated)
    # ...and none of the round-2 codes block.
    assert all(f.severity != "P0" for f in lint.findings if f.code in P2_LINT_CODES)
    only_new = memo_quality_lint.MemoLintResult(
        path=str(out_en), findings=[f for f in lint.findings if f.code in P2_LINT_CODES]
    )
    assert only_new.has_blocking_findings is False


@pytest.mark.parametrize("name", BILINGUAL + (ENGLISH_DRAFT,))
def test_report_only_checks_run_on_every_package(name):
    package = load_fixture(name)
    conflicts = memo_fact_check.metric_conflicts(package)
    assert isinstance(conflicts, list) and len(conflicts) <= memo_fact_check.MAX_METRIC_CONFLICTS
    for conflict in conflicts:
        assert set(conflict) >= {"metric", "values", "locations"}
        assert 2 <= len(conflict["values"]) <= 3
    metrics = memo_quality_metrics.compute(None, package, None, write=False)
    assert metrics["words_total"] and metrics["words_total"] > 5_000
    assert set(metrics["words_by_section"]) >= {s["id"] for s in package["sections"]}
    assert metrics["repetition_index"] is not None and 0 <= metrics["repetition_index"] <= 1
    assert metrics["metric_conflicts"] == len(conflicts)


def test_v2_draft_is_over_two_caps():
    metrics = memo_quality_metrics.compute(None, load_fixture(ENGLISH_DRAFT), None, write=False)
    assert {row["section"] for row in metrics["over_cap_sections"]} == {"company_team", "risks"}
    assert all(row["words"] > row["cap"] for row in metrics["over_cap_sections"])
