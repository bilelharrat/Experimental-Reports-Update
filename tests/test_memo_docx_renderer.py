from __future__ import annotations

import json

from docx import Document

from server import memo_docx_renderer, memo_quality_lint


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
            "bsh_ticket_size": "$5-10M",
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
                                    "en": "Require repeatable production usage before underwriting a step-up.",
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
        ],
        "sources": [
            {
                "id": "S1",
                "title": "Company investor materials",
                "class": "Company material",
                "treatment": "Used for product, customer, and funding context.",
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
    assert "关键指标快照" in _all_text(out_zh)
    assert "server.memo_docx_renderer" in (
        tmp_path / "logs" / "run_manifest.md"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "logs" / "validation.txt").exists()
    assert (tmp_path / "logs" / "validation_cn.txt").exists()

    lint_result = memo_quality_lint.lint_memo_docx(out_en)
    assert lint_result.has_blocking_findings is False


def test_generated_renderer_script_detector_flags_old_pattern(tmp_path):
    (tmp_path / "build_memo.py").write_text("# old generated renderer\n", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "build_memos.js").write_text("// old renderer\n", encoding="utf-8")

    matches = memo_docx_renderer.find_generated_renderer_scripts(tmp_path)

    assert {path.name for path in matches} == {"build_memo.py", "build_memos.js"}
