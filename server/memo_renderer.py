"""Render BSH investment-memo .docx files from a structured JSON.

Claude produces the analytical content as ``memo_structured_en.json`` and
``memo_structured_zh.json`` (one per language, same schema). This module
turns each into a styled ``.docx`` per the bsh-investment-memo-latestage
spec — BSH palette, cover page with metadata block, callout boxes,
styled tables, page numbers, CJK-safe fonts for the Chinese version.

The Claude side is responsible for analysis quality. This module is
responsible for *deterministic* styling so two runs of the same content
produce visually identical decks.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import nsmap, qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt, RGBColor

# --- BSH palette -----------------------------------------------------------

NAVY = RGBColor(0x1B, 0x2A, 0x4A)
TIFFANY = RGBColor(0x0A, 0xBA, 0xB5)
PALE_TIFFANY = RGBColor(0xE6, 0xF7, 0xF6)
PALE_GOLD = RGBColor(0xF7, 0xF0, 0xD9)
SOFT_GOLD = RGBColor(0xC9, 0xA2, 0x27)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY = RGBColor(0x66, 0x66, 0x66)
BLACK = RGBColor(0x11, 0x11, 0x11)
WARM_GREY = RGBColor(0xF3, 0xF3, 0xF3)

# Hex strings for OOXML shading (no "#"; uppercase per spec).
HEX_NAVY = "1B2A4A"
HEX_TIFFANY = "0ABAB5"
HEX_PALE_TIFFANY = "E6F7F6"
HEX_PALE_GOLD = "F7F0D9"
HEX_WARM_GREY = "F3F3F3"

# Font priority lists. python-docx exposes single-name set; for CJK we set
# both "ascii" and "eastAsia" via OOXML to get the right runs.
FONT_LATIN = "Arial"
FONT_CJK = "Microsoft YaHei"


def _set_cell_shading(cell, hex_color: str) -> None:
    """Fill a table cell with a solid background color via OOXML."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _set_cell_left_border(cell, hex_color: str, size_pt: int = 18) -> None:
    """Apply a thick colored left border (used for callout boxes)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(size_pt))  # in eighths of a point
    left.set(qn("w:color"), hex_color)
    tc_borders.append(left)


def _set_run_font(run, *, size_pt: float, bold: bool = False, color: RGBColor = BLACK,
                  font_name: str = FONT_LATIN, cjk: bool = False) -> None:
    """Apply font + size + color + (optional) CJK East Asian font binding."""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = color
    if cjk:
        # Also set the East-Asia font slot so CJK runs use the right face.
        r_pr = run._element.get_or_add_rPr()
        r_fonts = r_pr.find(qn("w:rFonts"))
        if r_fonts is None:
            r_fonts = OxmlElement("w:rFonts")
            r_pr.append(r_fonts)
        r_fonts.set(qn("w:ascii"), FONT_LATIN)
        r_fonts.set(qn("w:hAnsi"), FONT_LATIN)
        r_fonts.set(qn("w:eastAsia"), FONT_CJK)


def _add_heading1(doc, text: str, *, cjk: bool = False) -> None:
    """Heading 1: bold uppercase navy with a Tiffany underline rule."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text.upper() if not cjk else text)
    _set_run_font(run, size_pt=15, bold=True, color=NAVY, cjk=cjk)
    # Bottom border (Tiffany rule)
    p_pr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), HEX_TIFFANY)
    pbdr.append(bottom)
    p_pr.append(pbdr)


def _add_heading2(doc, text: str, *, cjk: bool = False) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    _set_run_font(run, size_pt=12, bold=True, color=NAVY, cjk=cjk)


def _add_heading3(doc, text: str, *, cjk: bool = False) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    _set_run_font(run, size_pt=10.5, bold=True, color=BLACK, cjk=cjk)


def _add_body(doc, text: str, *, cjk: bool = False) -> None:
    if not text:
        return
    # Split on blank lines so a "paragraph" of body markdown lays out as
    # multiple <w:p> instead of one blob.
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        p.paragraph_format.line_spacing = 1.15 if cjk else 1.08
        run = p.add_run(chunk.replace("\n", " "))
        _set_run_font(run, size_pt=10.5, color=BLACK, cjk=cjk)


def _add_bullets(doc, items: list[str], *, cjk: bool = False) -> None:
    for item in items or []:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        p.paragraph_format.line_spacing = 1.15 if cjk else 1.08
        run = p.add_run(str(item))
        _set_run_font(run, size_pt=10.5, color=BLACK, cjk=cjk)


def _add_styled_table(
    doc,
    rows: list[list[str]],
    *,
    header: bool = True,
    cjk: bool = False,
    col_widths: list[float] | None = None,
) -> None:
    """Navy header, alternating Pale-Tiffany / white body rows."""
    if not rows:
        return
    cols = len(rows[0])
    tbl = doc.add_table(rows=len(rows), cols=cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.autofit = True

    for r_idx, row in enumerate(rows):
        is_header = header and r_idx == 0
        is_alt = (not is_header) and ((r_idx - (1 if header else 0)) % 2 == 0)
        for c_idx, val in enumerate(row):
            cell = tbl.rows[r_idx].cells[c_idx]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            # Clear default paragraph; set ours.
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(str(val) if val is not None else "")
            if is_header:
                _set_cell_shading(cell, HEX_NAVY)
                _set_run_font(run, size_pt=9.5, bold=True, color=WHITE, cjk=cjk)
            else:
                if is_alt:
                    _set_cell_shading(cell, HEX_PALE_TIFFANY)
                _set_run_font(run, size_pt=9.5, color=BLACK, cjk=cjk)
    # Add spacing after the table.
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def _add_callout(
    doc,
    label: str,
    body_paragraphs: list[str],
    *,
    flavor: str = "warning",
    cjk: bool = False,
) -> None:
    """Single-cell table with a colored left border + pale fill."""
    fill = HEX_PALE_GOLD if flavor == "warning" else HEX_PALE_TIFFANY
    if flavor == "decision":
        fill = HEX_WARM_GREY
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    cell = tbl.rows[0].cells[0]
    _set_cell_shading(cell, fill)
    _set_cell_left_border(cell, HEX_TIFFANY, size_pt=24)
    cell.text = ""
    # Label
    p_label = cell.paragraphs[0]
    p_label.paragraph_format.space_after = Pt(2)
    run = p_label.add_run(label)
    _set_run_font(run, size_pt=10, bold=True, color=NAVY, cjk=cjk)
    # Body paragraphs
    for body in body_paragraphs or []:
        p = cell.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(str(body))
        _set_run_font(run, size_pt=10, color=BLACK, cjk=cjk)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def _add_cover_page(doc, cover: dict, *, language: str) -> None:
    cjk = language == "zh"
    section = doc.sections[0]
    section.page_height = Cm(27.94)
    section.page_width = Cm(21.59)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)

    # Top brand line
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(40)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run("BERKELEY SUMMIT HOUSE")
    _set_run_font(run, size_pt=24, bold=True, color=NAVY)

    # Subtitle (English fixed; Chinese is 机密投资备忘录)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(14)
    sub = "Confidential Investment Memo" if language == "en" else "机密投资备忘录"
    run = p.add_run(sub)
    _set_run_font(run, size_pt=13, color=GREY, cjk=cjk)

    # Thin Tiffany divider
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_pr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), HEX_TIFFANY)
    pbdr.append(bottom)
    p_pr.append(pbdr)
    p.paragraph_format.space_after = Pt(16)

    # Company name (large)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(cover.get("company_display_name", "") or "")
    _set_run_font(run, size_pt=22, bold=True, color=NAVY, cjk=cjk)

    # Optional descriptor
    if cover.get("company_descriptor"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(20)
        run = p.add_run(cover["company_descriptor"])
        _set_run_font(run, size_pt=12, color=GREY, cjk=cjk)
    else:
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(20)

    # Metadata block (centered, label : value)
    labels_en = [
        ("Date", cover.get("date")),
        ("Stage", cover.get("stage")),
        ("Sector", cover.get("sector")),
        ("Location", cover.get("location")),
        ("Round", cover.get("round")),
        ("BSH ticket size", cover.get("bsh_ticket")),
    ]
    labels_zh = [
        ("日期", cover.get("date")),
        ("阶段", cover.get("stage")),
        ("行业", cover.get("sector")),
        ("地点", cover.get("location")),
        ("本轮", cover.get("round")),
        ("BSH 投资规模", cover.get("bsh_ticket")),
    ]
    labels = labels_zh if language == "zh" else labels_en
    for label, value in labels:
        if not value:
            continue
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(f"{label}: ")
        _set_run_font(run, size_pt=11, bold=True, color=NAVY, cjk=cjk)
        run2 = p.add_run(str(value))
        _set_run_font(run2, size_pt=11, color=BLACK, cjk=cjk)

    # Table of Contents
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(28)
    spacer.paragraph_format.space_after = Pt(4)
    spacer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = spacer.add_run("TABLE OF CONTENTS" if language == "en" else "目录")
    _set_run_font(run, size_pt=10, bold=True, color=TIFFANY, cjk=cjk)

    toc_entries_en = [
        "I. Executive Summary",
        "II. Company Overview",
        "III. Investment Highlights",
        "IV. Investment Risk",
        "V. Financial Forecast & Valuation",
        "VI. Sources & References",
    ]
    toc_entries_zh = [
        "一、核心摘要",
        "二、项目简介",
        "三、投资亮点",
        "四、投资风险",
        "五、财务分析",
        "六、资料与参考来源",
    ]
    entries = toc_entries_zh if language == "zh" else toc_entries_en
    for entry in entries:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(entry)
        _set_run_font(run, size_pt=10.5, color=BLACK, cjk=cjk)

    doc.add_page_break()


def _add_page_number_footer(section, *, language: str) -> None:
    """Insert a centered 'Page X' / '第 X 页' footer with a PAGE field."""
    cjk = language == "zh"
    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # "Page " or "第 "
    run = p.add_run("第 " if cjk else "Page ")
    _set_run_font(run, size_pt=9, color=GREY, cjk=cjk)
    # PAGE field
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_begin)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    run._r.append(instr)
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    run._r.append(fld_sep)
    placeholder = OxmlElement("w:t")
    placeholder.text = "1"
    run._r.append(placeholder)
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_end)
    if cjk:
        run2 = p.add_run(" 页")
        _set_run_font(run2, size_pt=9, color=GREY, cjk=True)


def _add_running_header(section, company_name: str, *, language: str) -> None:
    cjk = language == "zh"
    header = section.header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    label = (
        f"{company_name} | BSH 机密投资备忘录"
        if language == "zh"
        else f"{company_name} | BSH Confidential Investment Memo"
    )
    run = p.add_run(label)
    _set_run_font(run, size_pt=9, color=GREY, cjk=cjk)


# --- Section renderers -----------------------------------------------------

def _exec_summary(doc, es: dict, *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc, "I. Executive Summary" if language == "en" else "一、核心摘要", cjk=cjk)

    # Investment Opportunity
    _add_heading2(doc, "Investment Opportunity" if language == "en" else "投资机会", cjk=cjk)
    opp = es.get("investment_opportunity") or {}
    _add_body(doc, opp.get("narrative") or "", cjk=cjk)
    # Key Metrics Snapshot
    km = opp.get("key_metrics") or []
    if km:
        _add_heading3(doc,
                      "Key Metrics Snapshot" if language == "en" else "关键指标速览",
                      cjk=cjk)
        rows = [["Metric" if language == "en" else "指标",
                 "Value" if language == "en" else "数值"]]
        for m in km:
            rows.append([str(m.get("label") or ""), str(m.get("value") or "")])
        _add_styled_table(doc, rows, cjk=cjk)
    # Valuation Timing Warning
    vtw = opp.get("valuation_warning")
    if vtw and (vtw.get("body") or vtw.get("paragraphs")):
        label = vtw.get("label") or (
            "Valuation Timing Warning (for BSH)" if language == "en"
            else "估值时点警示（仅供 BSH）"
        )
        bodies = vtw.get("paragraphs") or [vtw.get("body") or ""]
        _add_callout(doc, label, bodies, flavor="warning", cjk=cjk)

    # Investment Thesis
    _add_heading2(doc, "Investment Thesis" if language == "en" else "投资论点", cjk=cjk)
    _add_bullets(doc, es.get("investment_thesis") or [], cjk=cjk)

    # Investment Risk
    _add_heading2(doc, "Investment Risk" if language == "en" else "投资风险", cjk=cjk)
    risk = es.get("investment_risk") or {}
    _add_bullets(doc, risk.get("bullets") or [], cjk=cjk)
    crc = risk.get("critical_reality_check")
    if crc:
        label = (
            "Critical Reality Check (for BSH)" if language == "en"
            else "关键现实核查（仅供 BSH）"
        )
        bodies = []
        if crc.get("supporting_facts"):
            bodies.append(
                ("Strongest supporting facts: " if language == "en" else "最强支持事实：")
                + "; ".join(crc["supporting_facts"])
            )
        if crc.get("disconfirming_facts"):
            bodies.append(
                ("Strongest disconfirming facts: " if language == "en" else "最强反证事实：")
                + "; ".join(crc["disconfirming_facts"])
            )
        if crc.get("unproven"):
            bodies.append(
                ("What remains unproven: " if language == "en" else "尚未证实的部分：")
                + "; ".join(crc["unproven"])
            )
        if crc.get("must_be_true_for_bull"):
            bodies.append(
                ("Must be true for the bull case: " if language == "en"
                 else "牛市情景必须成立的前提：")
                + "; ".join(crc["must_be_true_for_bull"])
            )
        _add_callout(doc, label, bodies, flavor="evidence", cjk=cjk)

    # Recommendation
    _add_heading2(doc,
                  "Investment Recommendation" if language == "en" else "投资建议",
                  cjk=cjk)
    rec = es.get("investment_recommendation") or {}
    verdict = rec.get("verdict")
    if verdict:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(("Verdict: " if language == "en" else "结论："))
        _set_run_font(run, size_pt=10.5, bold=True, color=NAVY, cjk=cjk)
        run2 = p.add_run(str(verdict))
        _set_run_font(run2, size_pt=10.5, bold=True, color=SOFT_GOLD, cjk=cjk)
    _add_body(doc, rec.get("logic") or "", cjk=cjk)
    conds = rec.get("conditions") or []
    if conds:
        _add_heading3(doc, "Conditions" if language == "en" else "条件", cjk=cjk)
        _add_bullets(doc, conds, cjk=cjk)

    # Open Questions
    _add_heading2(doc, "Open Questions" if language == "en" else "待解决问题", cjk=cjk)
    oq = es.get("open_questions") or {}
    questions = oq.get("top_3_gating_questions") or []
    if questions:
        label = (
            "Top 3 Gating Questions (for BSH)" if language == "en"
            else "三大核心决策问题（仅供 BSH）"
        )
        _add_callout(doc, label, questions, flavor="decision", cjk=cjk)


def _company_overview(doc, co: dict, *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "II. Company Overview" if language == "en" else "二、项目简介",
                  cjk=cjk)
    en_labels = [
        ("product_overview", "Product Overview"),
        ("core_technology", "Core Technology / Differentiation"),
        ("value_proposition", "Value Proposition"),
        ("business_model", "Business Model"),
        ("key_partners", "Key Partners and Relationships"),
    ]
    zh_labels = [
        ("product_overview", "产品概述"),
        ("core_technology", "核心技术与差异化"),
        ("value_proposition", "价值主张"),
        ("business_model", "商业模式"),
        ("key_partners", "主要合作伙伴与关系"),
    ]
    labels = zh_labels if language == "zh" else en_labels
    for key, heading in labels:
        body = co.get(key)
        if not body:
            continue
        _add_heading2(doc, heading, cjk=cjk)
        _add_body(doc, body, cjk=cjk)

    team = co.get("team") or {}
    if team.get("founders") or team.get("board"):
        _add_heading2(doc, "Team" if language == "en" else "团队", cjk=cjk)
    if team.get("founders"):
        _add_heading3(doc,
                      "Founders / Management Team" if language == "en"
                      else "创始人与管理团队", cjk=cjk)
        for person in team["founders"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(f"{person.get('name', '')} — {person.get('title', '')}")
            _set_run_font(run, size_pt=10.5, bold=True, color=BLACK, cjk=cjk)
            if person.get("background"):
                run2 = p.add_run(f"  {person['background']}")
                _set_run_font(run2, size_pt=10.5, color=BLACK, cjk=cjk)
    if team.get("board"):
        _add_heading3(doc,
                      "Board of Directors" if language == "en" else "董事会", cjk=cjk)
        rows = [[
            "Name" if language == "en" else "姓名",
            "Background / Strategic value" if language == "en" else "背景与战略价值",
        ]]
        for m in team["board"]:
            rows.append([str(m.get("name") or ""), str(m.get("background") or "")])
        _add_styled_table(doc, rows, cjk=cjk)

    rev = co.get("revenue") or {}
    if rev:
        _add_heading2(doc, "Revenue" if language == "en" else "收入", cjk=cjk)
        if rev.get("narrative"):
            _add_body(doc, rev["narrative"], cjk=cjk)
        if rev.get("table"):
            rows = [[
                "Component" if language == "en" else "项目",
                "Value" if language == "en" else "数值",
            ]]
            for row in rev["table"]:
                rows.append([str(row.get("metric") or ""), str(row.get("value") or "")])
            _add_styled_table(doc, rows, cjk=cjk)

    km = co.get("key_metrics_table") or []
    if km:
        _add_heading2(doc, "Key Metrics" if language == "en" else "关键指标", cjk=cjk)
        rows = [[
            "Metric" if language == "en" else "指标",
            "Value" if language == "en" else "数值",
            "Notes" if language == "en" else "备注",
        ]]
        for row in km:
            rows.append([
                str(row.get("metric") or ""),
                str(row.get("value") or ""),
                str(row.get("notes") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)


def _highlights(doc, hl: dict, *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "III. Investment Highlights" if language == "en" else "三、投资亮点",
                  cjk=cjk)
    if hl.get("industry_trends"):
        _add_heading2(doc,
                      "Industry Trends & Market Context" if language == "en"
                      else "行业趋势与市场背景", cjk=cjk)
        _add_body(doc, hl["industry_trends"], cjk=cjk)
    ca = hl.get("competitive_analysis") or {}
    if ca:
        _add_heading2(doc,
                      "Competitive Analysis" if language == "en" else "竞争分析",
                      cjk=cjk)
        if ca.get("narrative"):
            _add_body(doc, ca["narrative"], cjk=cjk)
        if ca.get("table"):
            cols_en = ["Competitor", "Focus", "Strengths", "Weaknesses", "Differentiation"]
            cols_zh = ["竞争对手", "聚焦", "优势", "劣势", "差异化"]
            cols = cols_zh if language == "zh" else cols_en
            rows = [cols]
            for r in ca["table"]:
                rows.append([
                    str(r.get("competitor") or ""),
                    str(r.get("focus") or ""),
                    str(r.get("strengths") or ""),
                    str(r.get("weaknesses") or ""),
                    str(r.get("differentiation") or ""),
                ])
            _add_styled_table(doc, rows, cjk=cjk)
    if hl.get("replacement_vs_coexistence"):
        _add_heading2(doc,
                      "Replacement vs. Coexistence" if language == "en"
                      else "替代 vs. 共存", cjk=cjk)
        _add_body(doc, hl["replacement_vs_coexistence"], cjk=cjk)
    moat = hl.get("moat_table") or []
    if moat:
        _add_heading2(doc, "Moat" if language == "en" else "护城河", cjk=cjk)
        cols_en = ["Component", "What's there", "Strength", "Risk"]
        cols_zh = ["组成部分", "现状", "强度", "风险"]
        cols = cols_zh if language == "zh" else cols_en
        rows = [cols]
        for r in moat:
            rows.append([
                str(r.get("component") or ""),
                str(r.get("description") or ""),
                str(r.get("strength") or ""),
                str(r.get("risk") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)
    if hl.get("moat_rights_durability"):
        _add_heading3(doc,
                      "Rights durability" if language == "en" else "权利持续性",
                      cjk=cjk)
        _add_body(doc, hl["moat_rights_durability"], cjk=cjk)
    for key, en, zh in [
        ("quality_of_financials", "Quality of Financials", "财务质量"),
        ("quality_of_business_model", "Quality of Business Model", "商业模式质量"),
        ("quality_of_team", "Quality of Team", "团队质量"),
    ]:
        if hl.get(key):
            _add_heading2(doc, zh if language == "zh" else en, cjk=cjk)
            _add_body(doc, hl[key], cjk=cjk)


def _risk(doc, ir: dict, *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "IV. Investment Risk" if language == "en" else "四、投资风险",
                  cjk=cjk)
    rr = ir.get("risk_register") or []
    if rr:
        _add_heading2(doc, "Risk Register" if language == "en" else "风险清单", cjk=cjk)
        cols_en = ["#", "Risk", "Severity", "Likelihood",
                   "Disconfirming Evidence", "Mitigant"]
        cols_zh = ["#", "风险", "严重度", "可能性", "反证", "缓释/监控"]
        cols = cols_zh if language == "zh" else cols_en
        rows = [cols]
        for r in rr:
            rows.append([
                str(r.get("id") or ""),
                str(r.get("risk") or ""),
                str(r.get("severity") or ""),
                str(r.get("likelihood") or ""),
                str(r.get("evidence") or ""),
                str(r.get("mitigant") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)
    if ir.get("key_disconfirming_evidence"):
        _add_heading2(doc,
                      "Key Disconfirming Evidence" if language == "en"
                      else "关键反证", cjk=cjk)
        _add_body(doc, ir["key_disconfirming_evidence"], cjk=cjk)
    if ir.get("pre_mortem_summary"):
        _add_heading2(doc,
                      "Pre-Mortem Summary" if language == "en" else "预先反思摘要",
                      cjk=cjk)
        _add_body(doc, ir["pre_mortem_summary"], cjk=cjk)


def _financial(doc, ff: dict, *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "V. Financial Forecast & Valuation" if language == "en"
                  else "五、财务分析", cjk=cjk)
    if ff.get("outside_in_checks"):
        _add_heading2(doc,
                      "Outside-In Sanity Checks" if language == "en"
                      else "外部验证测算", cjk=cjk)
        _add_body(doc, ff["outside_in_checks"], cjk=cjk)
    tbt = ff.get("time_base_integrity_table") or []
    if tbt:
        _add_heading2(doc,
                      "Time-Base Integrity Table" if language == "en"
                      else "时点一致性表", cjk=cjk)
        cols_en = ["Marker", "Date", "Value", "Implied Multiple", "Label"]
        cols_zh = ["标记", "日期", "数值", "对应倍数", "标签"]
        cols = cols_zh if language == "zh" else cols_en
        rows = [cols]
        for r in tbt:
            rows.append([
                str(r.get("marker") or ""),
                str(r.get("date") or ""),
                str(r.get("value") or ""),
                str(r.get("multiple") or ""),
                str(r.get("label") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)
    if ff.get("growth_quality_notes"):
        _add_heading2(doc,
                      "Growth Quality Notes" if language == "en"
                      else "增长质量说明", cjk=cjk)
        _add_body(doc, ff["growth_quality_notes"], cjk=cjk)
    gb = ff.get("growth_bridge_table") or []
    if gb:
        _add_heading2(doc,
                      "Growth Bridge Table" if language == "en" else "增长桥接表",
                      cjk=cjk)
        cols_en = ["Bucket", "Contribution", "Notes"]
        cols_zh = ["增长来源", "贡献", "备注"]
        cols = cols_zh if language == "zh" else cols_en
        rows = [cols]
        for r in gb:
            rows.append([
                str(r.get("bucket") or ""),
                str(r.get("contribution") or ""),
                str(r.get("notes") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)
    if ff.get("capital_structure"):
        _add_heading2(doc,
                      "Capital Structure & Dilution Notes" if language == "en"
                      else "资本结构与稀释说明", cjk=cjk)
        _add_body(doc, ff["capital_structure"], cjk=cjk)
    sc = ff.get("scenario_table") or []
    if sc:
        _add_heading2(doc,
                      "Scenario Analysis" if language == "en" else "情景分析",
                      cjk=cjk)
        cols_en = ["Scenario", "Revenue (target year)", "CAGR",
                   "Comparable Multiple", "Implied EV",
                   "Dilution / Preference Assumption",
                   "Implied Value to Common", "BSH IRR"]
        cols_zh = ["情景", "目标年收入", "复合增长", "对标倍数",
                   "对应企业价值", "稀释/优先假设", "对应普通股价值", "BSH IRR"]
        cols = cols_zh if language == "zh" else cols_en
        rows = [cols]
        for r in sc:
            rows.append([
                str(r.get("scenario") or ""),
                str(r.get("revenue") or ""),
                str(r.get("cagr") or ""),
                str(r.get("multiple") or ""),
                str(r.get("ev") or ""),
                str(r.get("dilution_assumption") or ""),
                str(r.get("value_to_common") or ""),
                str(r.get("bsh_irr") or ""),
            ])
        _add_styled_table(doc, rows, cjk=cjk)


def _sources(doc, sources: list[dict], *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "VI. Sources & References" if language == "en"
                  else "六、资料与参考来源", cjk=cjk)
    if not sources:
        return
    for i, src in enumerate(sources, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(f"{i}. ")
        _set_run_font(run, size_pt=10, bold=True, color=NAVY, cjk=cjk)
        if src.get("category"):
            cat = doc.paragraphs[-1].add_run(f"[{src['category']}] ")
            _set_run_font(cat, size_pt=10, color=GREY, cjk=cjk)
        run2 = p.add_run(str(src.get("citation") or ""))
        _set_run_font(run2, size_pt=10, color=BLACK, cjk=cjk)


def _validation_log(doc, items: list[dict], *, language: str) -> None:
    cjk = language == "zh"
    _add_heading1(doc,
                  "Appendix: Validation & Assumptions Log" if language == "en"
                  else "附录：验证与假设日志", cjk=cjk)
    if not items:
        return
    cols_en = ["#", "Claim", "Provenance", "Independent Support",
               "Disconfirming Evidence", "Status", "Confidence", "Next Step"]
    cols_zh = ["#", "主张", "来源", "独立佐证", "反证", "状态", "信心", "下一步"]
    cols = cols_zh if language == "zh" else cols_en
    rows = [cols]
    for r in items:
        rows.append([
            str(r.get("id") or ""),
            str(r.get("claim") or ""),
            str(r.get("provenance") or ""),
            str(r.get("independent_support") or ""),
            str(r.get("disconfirming_evidence") or ""),
            str(r.get("status") or ""),
            str(r.get("confidence") or ""),
            str(r.get("next_step") or ""),
        ])
    _add_styled_table(doc, rows, cjk=cjk)


# --- Public entry ----------------------------------------------------------

def render(structured: dict, output_path: Path | str, *, language: str = "en") -> Path:
    """Render a structured memo dict to a styled .docx and return its path."""
    if language not in ("en", "zh"):
        raise ValueError(f"Unsupported language: {language}")
    doc = Document()

    cover = structured.get("cover") or {}
    company_name = cover.get("company_display_name") or "Company"

    # Header + footer on all sections (cover included; we don't fight Word's
    # different-first-page setting for v1 — the page-number field starts at 1
    # which is fine).
    section = doc.sections[0]
    _add_running_header(section, company_name, language=language)
    _add_page_number_footer(section, language=language)

    _add_cover_page(doc, cover, language=language)
    _exec_summary(doc, structured.get("executive_summary") or {}, language=language)
    _company_overview(doc, structured.get("company_overview") or {}, language=language)
    _highlights(doc, structured.get("investment_highlights") or {}, language=language)
    _risk(doc, structured.get("investment_risk") or {}, language=language)
    _financial(doc, structured.get("financial_forecast") or {}, language=language)
    _sources(doc, structured.get("sources") or [], language=language)
    _validation_log(doc, structured.get("validation_log") or [], language=language)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def render_pair(structured_en: dict, structured_zh: dict, *,
                en_path: Path | str, zh_path: Path | str) -> dict[str, Path]:
    """Render both English and Chinese .docx files from their structured JSONs."""
    paths = {
        "en": render(structured_en, en_path, language="en"),
        "zh": render(structured_zh, zh_path, language="zh"),
    }
    return paths


# --- Validation helpers ----------------------------------------------------

def validate_rendered(path: Path) -> dict:
    """Quick structural validation of a rendered .docx.

    Counts tables and rough callout boxes, looks for cover-page tokens,
    confirms page-number field is present. Returns ``{ok, checks, errors}``
    suitable for writing into logs/validation.txt.
    """
    if not path.exists():
        return {"ok": False, "errors": [f"file does not exist: {path}"]}
    try:
        doc = Document(str(path))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"failed to open docx: {exc}"]}

    n_tables = len(doc.tables)
    # Callout boxes are 1x1 tables; everything else is a content table.
    n_callouts = sum(1 for t in doc.tables if len(t.rows) == 1 and len(t.columns) == 1)
    n_content_tables = n_tables - n_callouts

    has_bsh = any("BERKELEY SUMMIT HOUSE" in (p.text or "") for p in doc.paragraphs)
    # PAGE field shows up in footers; look in section footers.
    has_page_field = False
    for section in doc.sections:
        for p in section.footer.paragraphs:
            for run in p.runs:
                if any(
                    el.tag.endswith("instrText") and "PAGE" in (el.text or "")
                    for el in run._r.iter()
                ):
                    has_page_field = True

    checks = {
        "tables": n_content_tables,
        "callout_boxes": n_callouts,
        "has_cover_title": has_bsh,
        "has_page_field": has_page_field,
    }
    errors: list[str] = []
    if n_content_tables < 8:
        errors.append(f"only {n_content_tables} content tables (>= 8 required)")
    if n_callouts < 3:
        errors.append(f"only {n_callouts} callout boxes (>= 3 required)")
    if not has_bsh:
        errors.append("cover title 'BERKELEY SUMMIT HOUSE' missing")
    if not has_page_field:
        errors.append("footer page-number field missing")
    return {"ok": not errors, "checks": checks, "errors": errors}
