from __future__ import annotations

import copy
import json

from docx import Document
import pytest

from server import (
    internal_memo_renderer,
    memo_chinese_parity,
    memo_docx_renderer,
    memo_quality_lint,
)


def _package() -> dict:
    return {
        "schema_version": 1,
        "company": {
            "name": "Generalist, Inc.",
            "descriptor": {
                "en": "Embodied AI systems for industrial automation",
                "zh": "面向工业自动化的具身智能系统",
            },
            "stage": "Late-stage / pre-IPO",
            "sector": "AI Robotics",
            "location": "San Francisco, CA",
            "round": "Series D context",
        },
        "run": {
            "run_id": "2026-06-22__120000",
            "as_of": "2026-06-22",
        },
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "heading",
                        "level": 2,
                        "text": {
                            "en": "Investment Opportunity",
                            "zh": "投资机会",
                        },
                    },
                    {
                        "type": "paragraph",
                        "text": {
                            "en": (
                                "Generalist should be treated as a conditional "
                                "opportunity because deployment proof is visible "
                                "but revenue depth still needs diligence."
                            ),
                            "zh": (
                                "Generalist 应被视为有条件推进的机会，因为部署证据已经出现，"
                                "但收入深度仍需尽调确认。"
                            ),
                        },
                    },
                    {
                        "type": "table",
                        "title": {
                            "en": "Key Metrics Snapshot",
                            "zh": "关键指标快照",
                        },
                        "headers": [
                            {"en": "Metric", "zh": "指标"},
                            {"en": "Treatment", "zh": "处理方式"},
                        ],
                        "rows": [
                            [
                                {"en": "Revenue", "zh": "收入"},
                                {
                                    "en": "Use a deployment-depth proxy until audited ARR is available.",
                                    "zh": "在审计 ARR 可得前，使用部署深度作为代理指标。",
                                },
                            ],
                            [
                                {"en": "Customer depth", "zh": "客户深度"},
                                {
                                    "en": "Require repeatable production usage before supporting a step-up.",
                                    "zh": "承销估值上调前，需要验证可重复的生产环境使用。",
                                },
                            ],
                        ],
                    },
                    {
                        "type": "callout",
                        "tone": "warning",
                        "title": {
                            "en": "Decision Gate",
                            "zh": "决策关口",
                        },
                        "items": [
                            {
                                "en": "Confirm production deployments and margin path.",
                                "zh": "确认生产部署和利润率路径。",
                            },
                            {
                                "en": "Separate contracted pilots from recognized revenue.",
                                "zh": "区分已签试点与已确认收入。",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "company_overview",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {
                            "en": (
                                "Generalist sells automation systems for "
                                "industrial workflows where repeatability and "
                                "integration depth drive adoption."
                            ),
                            "zh": (
                                "Generalist 销售面向工业流程的自动化系统，"
                                "可重复性和集成深度决定采用速度。"
                            ),
                        },
                    }
                ],
            },
            {
                "id": "investment_highlights",
                "blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            {
                                "en": "Customer proof creates a diligence path for BSH.",
                                "zh": "客户验证为 BSH 提供了尽调路径。",
                            },
                            {
                                "en": "The category can support expansion if deployments repeat.",
                                "zh": "如果部署可重复，该品类具备扩张空间。",
                            },
                        ],
                    }
                ],
            },
            {
                "id": "investment_risk",
                "blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            {
                                "en": "Hardware integration may slow gross-margin expansion.",
                                "zh": "硬件集成可能拖慢毛利率提升。",
                            },
                            {
                                "en": "Enterprise adoption may remain services-heavy.",
                                "zh": "企业采用可能继续偏服务交付。",
                            },
                        ],
                    }
                ],
            },
            {
                "id": "financial_forecast_valuation",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {
                            "en": (
                                "The valuation case should use scenario ranges "
                                "until audited revenue and margin data are available."
                            ),
                            "zh": (
                                "在审计收入和利润率数据可得前，估值判断应使用情景区间。"
                            ),
                        },
                    }
                ],
            },
        ],
        "sources": [
            {
                "id": "S1",
                "title": "Company investor materials",
                "class": {"en": "Company material", "zh": "公司材料"},
                "treatment": {
                    "en": "Used for product, customer, and funding context.",
                    "zh": "用于产品、客户和融资背景。",
                },
                "as_of": "2026-06-22",
            }
        ],
    }


def _all_text(path):
    document = Document(path)
    text = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text.append(cell.text)
    return "\n".join(text)


def test_parameterized_renderer_writes_bilingual_docx_and_logs(tmp_path):
    package_path = tmp_path / "logs" / "memo_package.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text(json.dumps(_package()), encoding="utf-8")
    out_en = tmp_path / "memo" / "Generalist, Inc. - Investment Memo - 2026-06-22__120000.docx"
    out_zh = tmp_path / "memo" / "Generalist, Inc. - 投资备忘录 - 2026-06-22__120000.docx"

    result = memo_docx_renderer.render_memos(
        package_path,
        out_en=out_en,
        out_zh=out_zh,
        manifest_path=tmp_path / "logs" / "run_manifest.md",
        inventory_path=tmp_path / "logs" / "file_inventory.md",
    )

    assert result["ok"] is True
    assert out_en.exists()
    assert out_zh.exists()
    assert "Generalist, Inc." in _all_text(out_en)
    assert "I. EXECUTIVE SUMMARY" in _all_text(out_en)
    assert "BSH target allocation" not in _all_text(out_en)
    assert "target allocation" not in _all_text(out_en)
    assert "BSH ticket size" not in _all_text(out_en)
    assert "关键指标快照" in _all_text(out_zh)
    assert "server.memo_docx_renderer" in (
        tmp_path / "logs" / "run_manifest.md"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "logs" / "validation.txt").exists()
    assert (tmp_path / "logs" / "validation_cn.txt").exists()

    lint_result = memo_quality_lint.lint_memo_docx(out_en)
    assert lint_result.has_blocking_findings is False


def test_internal_memo_markdown_renderer_writes_docx(tmp_path):
    md_path = tmp_path / "internal.md"
    out_path = tmp_path / "internal.docx"
    md_path.write_text(
        "\n".join([
            "# Internal Diligence Memo - Generalist",
            "",
            "## Internal Recommendation",
            "Recommendation: Proceed if confirmed with a staged allocation.",
            "",
            "| Item | View |",
            "|---|---|",
            "| Suggested allocation | $5-10M pending confirmation |",
            "| Conviction | Medium |",
            "",
            "## Internal Diligence Priorities",
            "- Confirm deployment depth.",
            "- Confirm SPV economics.",
            "",
            "Internal use only.",
        ]),
        encoding="utf-8",
    )

    result = internal_memo_renderer.render_internal_memo(md_path, out_path)

    assert result["ok"] is True
    assert out_path.exists()
    text = _all_text(out_path)
    assert "Internal Diligence Memo" in text
    assert "Suggested allocation" in text


def test_generated_renderer_script_detector_flags_old_pattern(tmp_path):
    (tmp_path / "build_memo.py").write_text("# old generated renderer\n", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "build_memos.js").write_text("// old renderer\n", encoding="utf-8")

    matches = memo_docx_renderer.find_generated_renderer_scripts(tmp_path)

    assert {path.name for path in matches} == {"build_memo.py", "build_memos.js"}


def test_renderer_rejects_missing_required_section():
    package = copy.deepcopy(_package())
    package["sections"] = [
        section
        for section in package["sections"]
        if section["id"] != "investment_highlights"
    ]

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="investment_highlights"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_missing_chinese_translation():
    package = copy.deepcopy(_package())
    package["sections"][0]["blocks"][0]["text"].pop("zh")

    with pytest.raises(memo_docx_renderer.MemoRenderError, match=r"\.zh is required"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_unsupported_block_type():
    package = copy.deepcopy(_package())
    package["sections"][0]["blocks"].append({
        "type": "chart",
        "title": {"en": "Unsupported", "zh": "不支持"},
    })

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="unsupported"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_missing_sources():
    package = copy.deepcopy(_package())
    package["sources"] = []

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="sources"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_heading_only_required_section():
    package = copy.deepcopy(_package())
    package["sections"][1]["blocks"] = [
        {
            "type": "heading",
            "level": 2,
            "text": {"en": "Overview", "zh": "概览"},
        }
    ]

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="substantive"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_spacer_only_required_section():
    package = copy.deepcopy(_package())
    package["sections"][1]["blocks"] = [{"type": "spacer"}]

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="substantive"):
        memo_docx_renderer.validate_package(package)


def test_renderer_rejects_table_with_headers_but_no_rows():
    package = copy.deepcopy(_package())
    package["sections"][1]["blocks"] = [
        {
            "type": "table",
            "title": {"en": "Overview Table", "zh": "概览表"},
            "headers": [
                {"en": "Metric", "zh": "指标"},
                {"en": "Treatment", "zh": "处理方式"},
            ],
            "rows": [],
        }
    ]

    with pytest.raises(memo_docx_renderer.MemoRenderError, match="substantive"):
        memo_docx_renderer.validate_package(package)


def test_renderer_accepts_substantive_required_sections():
    memo_docx_renderer.validate_package(_package())


def test_is_numbered_section_heading():
    assert memo_docx_renderer._is_numbered_section_heading(
        "VI. Sources, Source Classes, and Fact Reference Index"
    )
    assert memo_docx_renderer._is_numbered_section_heading("六、资料、来源分类与事实索引")
    assert memo_docx_renderer._is_numbered_section_heading("I. Executive Summary")
    # Legitimate sub-headings are unnumbered and must be preserved.
    assert not memo_docx_renderer._is_numbered_section_heading("Investment Opportunity")
    assert not memo_docx_renderer._is_numbered_section_heading("风险清单")
    assert not memo_docx_renderer._is_numbered_section_heading("")


def test_renderer_drops_numbered_section_heading_restatement(tmp_path):
    # Reproduces the zainar parity failure: the sources section carried a
    # heading block restating its own numbered title. The renderer already
    # emits the section title, so the restatement produced a doubled heading —
    # counted asymmetrically across EN/ZH (en=7, zh=6) and tripping the gate.
    package = copy.deepcopy(_package())
    package["sections"].append(
        {
            "id": "sources",
            "blocks": [
                {
                    "type": "heading",
                    "level": 2,
                    "text": {
                        "en": "VI. Sources, Source Classes, and Fact Reference Index",
                        "zh": "六、资料、来源分类与事实索引",
                    },
                },
                {
                    "type": "paragraph",
                    "text": {
                        "en": "Source index follows.",
                        "zh": "以下为来源索引。",
                    },
                },
            ],
        }
    )
    package_path = tmp_path / "logs" / "memo_package.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    out_en = tmp_path / "memo" / "Generalist, Inc. - Investment Memo.docx"
    out_zh = tmp_path / "memo" / "Generalist, Inc. - 投资备忘录.docx"

    memo_docx_renderer.render_memos(package_path, out_en=out_en, out_zh=out_zh)

    # Count *section headings* (paragraphs), not TOC table entries. Before the
    # fix the restated heading rendered as a second "sources" section heading in
    # English (en=2) while Chinese counted one (zh=1) — an asymmetry that failed
    # the gate. Both must now resolve to exactly one.
    en_shape = memo_chinese_parity._extract_docx_shape(out_en, "en")
    zh_shape = memo_chinese_parity._extract_docx_shape(out_zh, "zh")
    assert en_shape.section_ids.count("sources") == 1, en_shape.section_ids
    assert zh_shape.section_ids.count("sources") == 1, zh_shape.section_ids
    assert en_shape.section_count == zh_shape.section_count

    result = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh)
    assert result.has_blocking_findings is False
    assert not any(
        finding.code == "section_heading_count_mismatch" for finding in result.findings
    )


def test_chinese_parity_passes_for_renderer_output(tmp_path):
    package_path = tmp_path / "logs" / "memo_package.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text(
        json.dumps(_package(), ensure_ascii=False),
        encoding="utf-8",
    )
    out_en = tmp_path / "memo" / "Generalist, Inc. - Investment Memo.docx"
    out_zh = tmp_path / "memo" / "Generalist, Inc. - 投资备忘录.docx"

    memo_docx_renderer.render_memos(package_path, out_en=out_en, out_zh=out_zh)

    result = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh)

    assert result.has_blocking_findings is False


def test_chinese_parity_fails_when_zh_section_missing(tmp_path):
    out_en = tmp_path / "en.docx"
    out_zh = tmp_path / "zh.docx"
    _write_parity_docx(out_en, locale="en")
    _write_parity_docx(out_zh, locale="zh", omit_section="investment_risk")

    result = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh)

    assert result.has_blocking_findings is True
    assert any(finding.code == "zh_core_section_missing" for finding in result.findings)


def test_chinese_parity_fails_when_zh_has_no_cjk_body(tmp_path):
    out_en = tmp_path / "en.docx"
    out_zh = tmp_path / "zh.docx"
    _write_parity_docx(out_en, locale="en")
    _write_parity_docx(
        out_zh,
        locale="zh",
        english_only_section="executive_summary",
    )

    result = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh)

    assert result.has_blocking_findings is True
    assert any(
        finding.code == "zh_core_section_no_cjk_body"
        for finding in result.findings
    )


def test_chinese_parity_fails_when_table_counts_diverge(tmp_path):
    out_en = tmp_path / "en.docx"
    out_zh = tmp_path / "zh.docx"
    _write_parity_docx(out_en, locale="en")
    _write_parity_docx(out_zh, locale="zh", extra_table=True)

    result = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh)

    assert result.has_blocking_findings is True
    assert any(finding.code == "table_count_mismatch" for finding in result.findings)


def _write_parity_docx(
    path,
    *,
    locale: str,
    omit_section: str | None = None,
    english_only_section: str | None = None,
    extra_table: bool = False,
):
    document = Document()
    titles = {
        "en": [
            ("executive_summary", "I. Executive Summary"),
            ("company_overview", "II. Company Overview"),
            ("investment_highlights", "III. Investment Highlights"),
            ("investment_risk", "IV. Investment Risk"),
            (
                "financial_forecast_valuation",
                "V. Financial Forecast & Valuation",
            ),
            (
                "sources",
                "VI. Sources, Source Classes, and Fact Reference Index",
            ),
        ],
        "zh": [
            ("executive_summary", "I. 执行摘要"),
            ("company_overview", "II. 公司概览"),
            ("investment_highlights", "III. 投资亮点"),
            ("investment_risk", "IV. 投资风险"),
            ("financial_forecast_valuation", "V. 财务预测与估值"),
            ("sources", "VI. 来源、来源类别与事实索引"),
        ],
    }
    bodies = {
        "en": "The memo preserves structure, tables, risks, valuation, and diligence gates.",
        "zh": "本备忘录保留相同结构、表格、风险、估值判断和尽调关口。",
    }
    for section_id, title in titles[locale]:
        if section_id == omit_section:
            continue
        document.add_paragraph(title)
        body_locale = "en" if section_id == english_only_section else locale
        document.add_paragraph(bodies[body_locale])
        if section_id == "executive_summary":
            table_locale = "en" if section_id == english_only_section else locale
            headers = {
                "en": ("Metric", "Treatment"),
                "zh": ("指标", "处理方式"),
            }
            values = {
                "en": ("Revenue", "Use scenario ranges for valuation support."),
                "zh": ("收入", "使用情景区间支持估值判断。"),
            }
            table = document.add_table(rows=2, cols=2)
            table.cell(0, 0).text = headers[table_locale][0]
            table.cell(0, 1).text = headers[table_locale][1]
            table.cell(1, 0).text = values[table_locale][0]
            table.cell(1, 1).text = values[table_locale][1]
    if extra_table:
        table = document.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "额外表格"
    document.save(path)
