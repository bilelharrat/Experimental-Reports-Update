"""Compact report mode + the founder-feedback voice/format gates:

- `late_compact` profile: 7 sections, bullet-format risks, same
  scorecard and pin discipline as the full report.
- active_structure(stage, mode) resolves compact profiles with full
  fallback.
- Exec-summary bullets must open with a claim, not a topic label.
- Charts require a `reading` note and support hbar/pie.
"""
from __future__ import annotations

import pytest

import test_memo_subsections_charts as full_fixtures
from server import memo_docx_renderer, memo_structure

COMPACT = memo_structure.load_structure("late_compact", 1)


# ---- profile ----------------------------------------------------------------


def test_compact_profile_shape():
    assert len(COMPACT.section_ids) == 7
    assert COMPACT.risk_format == "bullets"
    assert COMPACT.scorecard_weights() == memo_structure.load_structure(
        "late", 2
    ).scorecard_weights()
    for role in ("exec", "risk", "valuation"):
        assert COMPACT.section_for_role(role).id in COMPACT.section_ids
    for section in COMPACT.sections:
        assert section.subsections, section.id
        for sub in section.subsections:
            assert sub.en.lower() in section.contract_md.lower(), (
                section.id,
                sub.en,
            )


def test_compact_recognizer_canary():
    titles = COMPACT.section_titles()
    patterns = COMPACT.parity_patterns()
    prefix = COMPACT.numbered_prefix_pattern()
    for section_id in COMPACT.section_ids:
        for locale in ("en", "zh"):
            assert patterns[section_id][locale].match(
                titles[section_id][locale]
            ), (section_id, locale)
        assert prefix.match(titles[section_id]["en"].lower())
    assert patterns["sources"]["en"].match(titles["sources"]["en"])


def test_full_profiles_keep_card_risk_format():
    for stage, version in (("late", 1), ("late", 2), ("growth", 1), ("early", 1)):
        assert memo_structure.load_structure(stage, version).risk_format == "cards"


# ---- mode mapping -----------------------------------------------------------


def test_active_structure_compact_mode(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    assert memo_structure.active_structure("late", "compact").meta() == {
        "stage": "late_compact",
        "version": 1,
    }
    # stages without a compact profile fall back to the late compact one
    assert memo_structure.active_structure("growth", "compact").meta() == {
        "stage": "late_compact",
        "version": 1,
    }
    # full mode is untouched
    assert memo_structure.active_structure("late", "full").meta() == {
        "stage": "late",
        "version": 2,
    }


def test_flag_off_compact_still_runs_late_v1(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)
    assert (
        memo_structure.active_structure("late", "compact")
        is memo_structure.LATE
    )


# ---- compact package clears every gate --------------------------------------


def _compact_package() -> dict:
    return full_fixtures._v2_gen_package(COMPACT)


def test_compact_package_passes_generation_gates():
    package = _compact_package()
    errors = memo_docx_renderer.english_package_validation_errors(package)
    # No risk-card demands for a bullets-format profile.
    assert errors == []


def test_compact_package_renders_and_clears_docx_gates(tmp_path):
    from server import memo_chinese_parity, memo_quality_lint

    package = _compact_package()
    out_en = tmp_path / "memo" / "en.docx"
    out_zh = tmp_path / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    lint = memo_quality_lint.lint_memo_docx(out_en, COMPACT)
    assert not lint.p0_findings, [f.to_dict() for f in lint.p0_findings]
    parity = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh, COMPACT)
    assert not parity.p0_findings, [f.to_dict() for f in parity.p0_findings]


def test_compact_risk_contract_is_bullets():
    from server import claude_runner

    contract = claude_runner.memo_risk_register_contract(COMPACT)
    assert "BULLETS" in contract
    assert "six" not in contract.lower()
    v2 = memo_structure.load_structure("late", 2)
    assert "Mitigation" in claude_runner.memo_risk_register_contract(v2)


# ---- exec bullet topic-label gate -------------------------------------------


def test_exec_bullet_topic_label_rejected():
    package = full_fixtures._v2_gen_package()
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"].append(
        {
            "type": "bullets",
            "items": [
                {"en": "Price. 13.8x vs a 21x median.", "zh": ""},
                {
                    "en": (
                        "The price sits below every disclosed peer — 13.8x "
                        "against a 21x median."
                    ),
                    "zh": "",
                },
            ],
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    label_errors = [e for e in errors if "topic label" in e]
    assert len(label_errors) == 1
    assert "'Price'" in label_errors[0]


def test_exec_bullet_colon_lead_accepted():
    package = full_fixtures._v2_gen_package()
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"].append(
        {
            "type": "bullets",
            "items": [
                {
                    "en": (
                        "Market size: the pool is $125B and the company "
                        "already holds half of it."
                    ),
                    "zh": "",
                }
            ],
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert not [e for e in errors if "topic label" in e]


# ---- chart reading + new types ----------------------------------------------


def test_chart_without_reading_is_rejected():
    chart = full_fixtures._chart_block()
    chart.pop("reading", None)
    package = full_fixtures._package_with_chart(chart)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any("`reading` note" in e for e in errors)


def test_chart_with_reading_passes_and_renders_caption(tmp_path):
    chart = full_fixtures._chart_block(
        reading={"en": "Higher is better", "zh": "越高越好"}
    )
    package = full_fixtures._package_with_chart(chart)
    assert memo_docx_renderer.english_package_validation_errors(package) == []
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    for locale, needle in (
        ("en", "Reading: Higher is better"),
        ("zh", "读法：越高越好"),
    ):
        doc = Document(tmp_path / "memo" / f"{locale}.docx")
        text = "\n".join(p.text for p in doc.paragraphs)
        assert needle in text, locale


@pytest.mark.parametrize("chart_type", ["hbar", "pie"])
def test_new_chart_types_validate_and_render(chart_type):
    from server import memo_charts

    chart = full_fixtures._chart_block(
        chart_type=chart_type,
        reading={"en": "Shares of the pool", "zh": ""},
    )
    chart["series"] = chart["series"][:1]
    package = full_fixtures._package_with_chart(chart)
    assert memo_docx_renderer.english_package_validation_errors(package) == []
    png = memo_charts.chart_png(chart)
    assert png.startswith(b"\x89PNG"), chart_type


@pytest.mark.parametrize("chart_type", ["hbar", "pie"])
def test_new_chart_types_take_one_series(chart_type):
    chart = full_fixtures._chart_block(
        chart_type=chart_type,
        reading={"en": "Higher is better", "zh": ""},
    )
    package = full_fixtures._package_with_chart(chart)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any("exactly one series" in e for e in errors)


# ---- pagination -------------------------------------------------------------


def test_each_section_starts_on_a_new_page(tmp_path):
    package = full_fixtures._v2_gen_package()
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    doc = Document(tmp_path / "memo" / "en.docx")
    xml = doc.element.body.xml
    # Cover break + one break before each section after the first (11)
    # + one before the auto-rendered sources section.
    assert xml.count("w:br") >= 12


# ---- run plumbing -----------------------------------------------------------


def test_bootstrap_rejects_unknown_report_mode():
    from server import memo_prep

    with pytest.raises(ValueError, match="report_mode"):
        memo_prep.bootstrap_memo_run("whatever", report_mode="tiny")
