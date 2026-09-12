"""Founder-feedback round on the v2 report structure:

1. The executive summary carries no tables — it says the point.
2. Every section is organized under fixed numbered subsections declared
   by the profile and enforced at generation time.
3. Chart slots render real server-drawn charts (``chart`` blocks)
   instead of bridge tables.
"""
from __future__ import annotations

import pytest

from server import memo_docx_renderer, memo_structure

V2 = memo_structure.load_structure("late", 2)
GROWTH = memo_structure.load_structure("growth", 1)
EARLY = memo_structure.load_structure("early", 1)


# ---- structure declarations -------------------------------------------------


@pytest.mark.parametrize(
    "structure", [V2, GROWTH, EARLY], ids=["late_v2", "growth", "early"]
)
def test_v2_family_declares_subsections_everywhere(structure):
    for section in structure.sections:
        assert section.subsections, (structure.stage, section.id)
        # the contract narrates the same subsections it declares
        for sub in section.subsections:
            assert sub.en.lower() in section.contract_md.lower(), (
                structure.stage,
                section.id,
                sub.en,
            )


def test_late_v1_declares_no_subsections():
    for section in memo_structure.LATE.sections:
        assert section.subsections == ()


@pytest.mark.parametrize(
    "structure", [V2, GROWTH, EARLY], ids=["late_v2", "growth", "early"]
)
def test_exec_summary_owns_no_snapshot_components(structure):
    """The Deal Snapshot / Key Metrics Snapshot tables moved out of the
    executive summary into an overview-family section."""
    exec_id = structure.section_for_role("exec").id
    routing = structure.component_section()
    assert structure.section_for_role("exec").components == ()
    for slug in ("deal_terms", "key_metrics_snapshot"):
        if slug in routing:
            assert routing[slug] != exec_id, slug


# ---- generation-time package fixture ----------------------------------------


def _subsection_heading(number: int, sub: memo_structure.SubsectionDef) -> dict:
    return {
        "type": "heading",
        "level": 2,
        "text": {"en": f"{number}. {sub.en}", "zh": f"{number}. {sub.zh}"},
    }


def _risk_card(number: int, rating: int) -> list[dict]:
    def row(label: str, value: str) -> list[dict]:
        return [{"en": label, "zh": label}, {"en": value, "zh": value}]

    return [
        {
            "type": "heading",
            "level": 3,
            "text": {
                "en": (
                    f"Risk {number}: The concentration case number {number} "
                    "erodes revenue durability under stress"
                ),
                "zh": f"风险 {number}：集中度问题削弱收入持续性",
            },
        },
        {
            "type": "table",
            "component": "risk_register",
            "layout": "key_value",
            "headers": [],
            "rows": [
                row("Risk Type", "Concentration"),
                row(
                    "Why it matters",
                    "Top customer is 40% of revenue; churn there cuts "
                    "revenue by $10M and breaks the growth case.",
                ),
                row("What we watch", "Quarterly top-10 revenue share."),
                row("Mitigation", "Contract staggering already underway."),
                row("Likelihood", "Medium: concentration is disclosed."),
                row("Risk Rating", f"{rating}/10: quantified above."),
            ],
        },
    ]


def _v2_gen_section(
    structure: memo_structure.MemoStructure, section_id: str
) -> dict:
    """A section that satisfies the generation-time gates: subsection
    headings in order, component tables, exec without tables, risk cards
    in the risk section."""
    sdef = structure.section(section_id)
    exec_id = structure.section_for_role("exec").id
    risk_id = structure.section_for_role("risk").id
    components = [
        slug
        for slug, owner in structure.component_section().items()
        if owner == section_id
    ]
    blocks: list[dict] = []
    for number, sub in enumerate(sdef.subsections, start=1):
        blocks.append(_subsection_heading(number, sub))
        blocks.append(
            {
                "type": "paragraph",
                "text": {
                    "en": (
                        "This passage interprets the valuation and scenario "
                        "evidence in complete sentences and states what "
                        "moves the number."
                    ),
                    "zh": "本段解释估值与情景证据。",
                },
            }
        )
        if section_id == risk_id and sub.en == "Risk cards":
            for card_number, rating in enumerate((9, 8, 7, 6), start=1):
                blocks.extend(_risk_card(card_number, rating))
    if section_id == exec_id:
        blocks.append(
            {
                "type": "bullets",
                "items": [
                    {"en": "First substantive bullet with a number: 42%.", "zh": "一"},
                    {"en": "Second substantive bullet with a verdict.", "zh": "二"},
                ],
            }
        )
        blocks.append(
            {
                "type": "callout",
                "title": {"en": "Recommendation", "zh": "建议"},
                "body": {
                    "en": "Watch — 70/100. Entry only below the fair range.",
                    "zh": "观察名单。",
                },
            }
        )
    else:
        for slug in components:
            blocks.append(
                {
                    "type": "table",
                    "component": slug,
                    "title": {"en": slug.replace("_", " "), "zh": slug},
                    "headers": [{"en": "K", "zh": "K"}, {"en": "V", "zh": "V"}],
                    "rows": [
                        [{"en": "row", "zh": "行"}, {"en": "value", "zh": "值"}]
                    ],
                }
            )
    return {"id": section_id, "blocks": blocks}


def _v2_gen_package(structure: memo_structure.MemoStructure = V2) -> dict:
    return {
        "schema_version": 1,
        "structure": structure.meta(),
        "company": {"name": {"en": "Acme", "zh": "Acme"}},
        "run": {"run_id": "r1", "as_of": "2026-09-11"},
        "sources": [
            {
                "id": "s1",
                "title": {"en": "Company filing", "zh": "公司文件"},
                "class": {"en": "company-reported", "zh": "公司披露"},
                "treatment": {"en": "verified", "zh": "已核对"},
                "as_of": "2026-09-01",
            }
        ],
        "sections": [
            _v2_gen_section(structure, section_id)
            for section_id in structure.section_ids
        ],
    }


# ---- subsection gate ---------------------------------------------------------


@pytest.mark.parametrize(
    "structure", [V2, GROWTH, EARLY], ids=["late_v2", "growth", "early"]
)
def test_generation_gate_accepts_scaffolded_package(structure):
    package = _v2_gen_package(structure)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert errors == []


def test_missing_subsection_heading_is_named():
    package = _v2_gen_package()
    market = next(
        s for s in package["sections"] if s["id"] == "market_industry"
    )
    market["blocks"] = [
        b
        for b in market["blocks"]
        if "The ceiling question" not in str(b.get("text", {}).get("en", ""))
        or b.get("type") != "heading"
    ]
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any(
        "section market_industry" in e and "4. The ceiling question" in e
        for e in errors
    ), errors


def test_wrong_subsection_number_is_rejected():
    package = _v2_gen_package()
    moat = next(s for s in package["sections"] if s["id"] == "moat")
    for block in moat["blocks"]:
        if block.get("type") == "heading" and block["text"]["en"].startswith(
            "2. "
        ):
            block["text"]["en"] = "5. The $5B question"
            block["text"]["zh"] = "5. 50亿美元问题"
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any(
        "section moat" in e and "'2. The $5B question'" in e for e in errors
    ), errors


def test_exec_summary_table_is_rejected_with_routing_hint():
    package = _v2_gen_package()
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"].append(
        {
            "type": "table",
            "title": {"en": "Deal Snapshot", "zh": "交易概览"},
            "headers": [{"en": "K", "zh": "K"}],
            "rows": [[{"en": "Round", "zh": "轮次"}, {"en": "Series F", "zh": "F轮"}]],
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    matching = [e for e in errors if "must contain NO table blocks" in e]
    assert matching and "section executive_summary" in matching[0]
    assert "company_overview" in matching[0]


def test_v1_package_skips_the_new_gates():
    """Late v1 declares no subsections and no scorecard — neither new
    gate may fire on an unstamped (v1) package."""
    package = _v2_gen_package()
    del package["structure"]
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert not any("subsection" in e or "NO table blocks" in e for e in errors)


# ---- chart blocks ------------------------------------------------------------


def _chart_block(**overrides) -> dict:
    block = {
        "type": "chart",
        "chart_type": "grouped_bar",
        "title": {"en": "Market size", "zh": "市场空间"},
        "unit": {"en": "US$B", "zh": "十亿美元"},
        "reading": {"en": "Higher is better", "zh": "越高越好"},
        "caption": {
            "en": "SAM triples by 2030, so the ceiling is not the cap.",
            "zh": "SAM 到 2030 年增至三倍。",
        },
        "series": [
            {
                "label": "2026",
                "points": [
                    {"x": "TAM", "y": 60},
                    {"x": "SAM", "y": 22},
                    {"x": "SOM", "y": 4},
                ],
            },
            {
                "label": "2030",
                "points": [
                    {"x": "TAM", "y": 260},
                    {"x": "SAM", "y": 75},
                    {"x": "SOM", "y": 18},
                ],
            },
        ],
        "source_ids": ["s1"],
    }
    block.update(overrides)
    return block


def _package_with_chart(chart: dict) -> dict:
    package = _v2_gen_package()
    market = next(
        s for s in package["sections"] if s["id"] == "market_industry"
    )
    market["blocks"].insert(4, chart)
    return package


def test_valid_chart_block_passes_both_gates():
    package = _package_with_chart(_chart_block())
    assert memo_docx_renderer.english_package_validation_errors(package) == []
    memo_docx_renderer.validate_package(
        memo_docx_renderer.fill_blank_zh_placeholders(package)
    )


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"chart_type": "pie"}, "chart_type"),
        ({"title": None}, ".title"),
        ({"series": []}, "series"),
        (
            {
                "chart_type": "bar",
            },
            "exactly one series",
        ),
        (
            {
                "series": [
                    {"label": "A", "points": [{"x": "1", "y": 1}, {"x": "2", "y": 2}]},
                    {"label": "B", "points": [{"x": "1", "y": 1}, {"x": "3", "y": 2}]},
                ]
            },
            "same x categories",
        ),
        (
            {
                "series": [
                    {"label": "A", "points": [{"x": "1", "y": True}, {"x": "2", "y": 2}]}
                ]
            },
            "plain number",
        ),
        (
            {"series": [{"label": "A", "points": [{"x": "only", "y": 5}]}]},
            "at least two data points",
        ),
    ],
    ids=[
        "bad_type",
        "missing_title",
        "empty_series",
        "bar_with_two_series",
        "mismatched_x",
        "bool_y",
        "single_point",
    ],
)
def test_invalid_chart_blocks_are_rejected(overrides, needle):
    package = _package_with_chart(_chart_block(**overrides))
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any(needle in e for e in errors), (needle, errors)


@pytest.mark.parametrize("chart_type", ["bar", "grouped_bar", "line"])
def test_chart_png_renders(chart_type):
    from server import memo_charts

    block = _chart_block()
    if chart_type == "bar":
        block["series"] = block["series"][:1]
    block["chart_type"] = chart_type
    png = memo_charts.chart_png(block)
    assert png.startswith(b"\x89PNG"), chart_type
    # deterministic: the cache returns the identical render
    assert memo_charts.chart_png(dict(block)) == png


def test_chart_renders_as_image_with_localized_caption(tmp_path):
    package = _package_with_chart(_chart_block())
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    for locale, needle in (("en", "ceiling is not the cap"), ("zh", "SAM 到 2030")):
        doc = Document(tmp_path / "memo" / f"{locale}.docx")
        assert len(doc.inline_shapes) == 1, locale
        text = "\n".join(p.text for p in doc.paragraphs)
        assert needle in text, locale


def test_chart_falls_back_to_table_when_render_fails(tmp_path, monkeypatch):
    from server import memo_charts

    def _boom(_block):
        raise RuntimeError("no backend")

    monkeypatch.setattr(memo_charts, "chart_png", _boom)
    package = _package_with_chart(_chart_block())
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    doc = Document(tmp_path / "memo" / "en.docx")
    assert len(doc.inline_shapes) == 0
    cells = [
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    ]
    assert "260" in " ".join(cells)


def test_repair_wraps_plain_chart_strings():
    package = _package_with_chart(
        _chart_block(
            title="Market size over time",
            caption="The market triples by 2030.",
        )
    )
    repaired, repairs = memo_docx_renderer.repair_package_structure(package)
    market = next(
        s for s in repaired["sections"] if s["id"] == "market_industry"
    )
    chart = market["blocks"][4]
    assert chart["title"] == {"en": "Market size over time", "zh": ""}
    assert chart["caption"] == {"en": "The market triples by 2030.", "zh": ""}
    assert any(".title" in r or ".caption" in r for r in repairs)


# ---- full render + docx gate chain with the scaffold -------------------------


@pytest.mark.parametrize(
    "structure", [V2, GROWTH, EARLY], ids=["late_v2", "growth", "early"]
)
def test_scaffolded_package_clears_docx_gates(structure, tmp_path):
    from server import memo_chinese_parity, memo_quality_lint

    package = _v2_gen_package(structure)
    out_en = tmp_path / "memo" / "en.docx"
    out_zh = tmp_path / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    lint = memo_quality_lint.lint_memo_docx(out_en, structure)
    assert not lint.p0_findings, [f.to_dict() for f in lint.p0_findings]
    parity = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh, structure)
    assert not parity.p0_findings, [f.to_dict() for f in parity.p0_findings]


def test_subsection_headings_render_in_both_locales(tmp_path):
    package = _v2_gen_package()
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    for locale, needle in (
        ("en", "4. The ceiling question"),
        ("zh", "4. 天花板问题"),
    ):
        doc = Document(tmp_path / "memo" / f"{locale}.docx")
        text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        assert needle in text, (locale, [t for t in text if t.startswith("4.")])


# ---- section-worker prompt scaffold ------------------------------------------


def test_section_prompt_carries_subsection_scaffold(monkeypatch, tmp_path):
    from server import claude_runner

    captured = {}

    def fake_artifact(**kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return {"section": {"id": "market_industry", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    claude_runner._run_english_section(
        run_dir=tmp_path,
        section_id="market_industry",
        common_context="",
        shared_facts_block="",
        spine_path=tmp_path / "spine.json",
        add_dirs=[],
        progress=None,
        timeout_sec=10,
        structure=V2,
    )
    prompt = captured["prompt"]
    assert "## Subsection scaffold" in prompt
    assert '"en": "4. The ceiling question", "zh": "4. 天花板问题"' in prompt

    claude_runner._run_english_section(
        run_dir=tmp_path,
        section_id="company_overview",
        common_context="",
        shared_facts_block="",
        spine_path=tmp_path / "spine.json",
        add_dirs=[],
        progress=None,
        timeout_sec=10,
        structure=memo_structure.LATE,
    )
    assert "## Subsection scaffold" not in captured["prompt"]
