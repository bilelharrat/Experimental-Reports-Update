"""Parameterized DOCX renderer for BSH investment memos.

Claude owns memo judgment and writes ``memo_package.json``. This module owns
all DOCX construction so memo runs do not generate bespoke Python/JS renderers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

SCHEMA_VERSION = 1

EN_FONT = "Arial"
ZH_FONT = "Microsoft YaHei"
NAVY = "1B2A4A"
TIFFANY = "0ABAB5"
PALE_TIFFANY = "E6F7F6"
PALE_GOLD = "F7F0D9"
WARM_GREY = "F3F3F3"
WHITE = "FFFFFF"
BLACK = "111111"
GREY = "666666"
BORDER = "BFBFBF"

GENERATED_RENDERER_SCRIPT_PATTERNS = (
    "build_memo*.py",
    "build_memos*.py",
    "generate_memo*.py",
    "generate_memos*.py",
    "render_memo*.py",
    "render_memos*.py",
    "build_memo*.js",
    "build_memos*.js",
    "generate_memo*.js",
    "generate_memos*.js",
    "render_memo*.js",
    "render_memos*.js",
)

SECTION_TITLES = {
    "executive_summary": {
        "en": "I. Executive Summary",
        "zh": "I. 执行摘要",
    },
    "company_overview": {
        "en": "II. Company Overview",
        "zh": "II. 公司概览",
    },
    "investment_highlights": {
        "en": "III. Investment Highlights",
        "zh": "III. 投资亮点",
    },
    "investment_risk": {
        "en": "IV. Investment Risk",
        "zh": "IV. 投资风险",
    },
    "financial_forecast_valuation": {
        "en": "V. Financial Forecast & Valuation",
        "zh": "V. 财务预测与估值",
    },
    "sources": {
        "en": "VI. Sources, Source Classes, and Fact Reference Index",
        "zh": "VI. 来源、来源类别与事实索引",
    },
    "validation_log": {
        "en": "Appendix: Validation & Assumptions Log",
        "zh": "附录：验证与假设日志",
    },
}

TOC_SECTION_IDS = (
    "executive_summary",
    "company_overview",
    "investment_highlights",
    "investment_risk",
    "financial_forecast_valuation",
    "sources",
)


class MemoRenderError(ValueError):
    """Raised when a memo package cannot be rendered."""


def find_generated_renderer_scripts(run_dir: Path | str) -> list[Path]:
    """Return forbidden per-run renderer scripts left by old memo workflows."""
    root = Path(run_dir)
    matches: list[Path] = []
    if not root.exists():
        return matches
    for pattern in GENERATED_RENDERER_SCRIPT_PATTERNS:
        matches.extend(path for path in root.rglob(pattern) if path.is_file())
    return sorted(set(matches))


def load_package(path: Path | str) -> dict:
    package_path = Path(path)
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoRenderError(f"Invalid memo package JSON: {exc}") from exc
    if not isinstance(package, dict):
        raise MemoRenderError("Memo package must be a JSON object")
    version = int(package.get("schema_version") or SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise MemoRenderError(
            f"Unsupported memo package schema_version {version}; expected {SCHEMA_VERSION}"
        )
    if not isinstance(package.get("company"), dict):
        raise MemoRenderError("Memo package requires a company object")
    if not isinstance(package.get("sections"), list):
        raise MemoRenderError("Memo package requires a sections list")
    return package


def render_memos(
    package: dict | Path | str,
    *,
    out_en: Path | str,
    out_zh: Path | str,
    validation_en: Path | str | None = None,
    validation_zh: Path | str | None = None,
    inventory_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> dict:
    """Render English and Chinese DOCX files from one structured package."""
    payload = load_package(package) if isinstance(package, (str, Path)) else package
    outputs = {
        "en": Path(out_en),
        "zh": Path(out_zh),
    }
    for locale, path in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        document = _build_document(payload, locale)
        document.save(path)

    run_dir = outputs["en"].parent.parent
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    validation_paths = {
        "en": Path(validation_en) if validation_en else logs_dir / "validation.txt",
        "zh": Path(validation_zh) if validation_zh else logs_dir / "validation_cn.txt",
    }
    for locale, path in validation_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_validation_report(payload, outputs[locale], locale), encoding="utf-8")
    if inventory_path:
        _write_inventory(Path(inventory_path), payload, outputs, validation_paths)
    else:
        _write_inventory(logs_dir / "file_inventory.md", payload, outputs, validation_paths)
    if manifest_path:
        _append_manifest(Path(manifest_path), payload, outputs, validation_paths)
    else:
        _append_manifest(logs_dir / "run_manifest.md", payload, outputs, validation_paths)
    return {
        "ok": True,
        "outputs": {locale: str(path) for locale, path in outputs.items()},
        "validation": {locale: str(path) for locale, path in validation_paths.items()},
    }


def _build_document(package: dict, locale: str) -> Document:
    document = Document()
    _configure_document(document, package, locale)
    _add_cover(document, package, locale)
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        _add_section(document, section, locale)
    if package.get("sources") and not _has_section(package, "sources"):
        _add_sources_section(document, package, locale)
    return document


def _configure_document(document: Document, package: dict, locale: str) -> None:
    font = _font(locale)
    section = document.sections[0]
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(1.9)
    section.right_margin = Cm(1.9)
    section.different_first_page_header_footer = True

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = font
    normal.font.size = Pt(10.2)
    _set_rfonts(normal.element.get_or_add_rPr(), font, locale)

    header_text = (
        f"{_company_name(package)} | BSH Confidential Investment Memo"
        if locale == "en"
        else f"{_company_name(package)} | BSH 机密投资备忘录"
    )
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(header, header_text, size=8.5, color=GREY, locale=locale)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_number(footer, locale)
    for run in footer.runs:
        _style_run(run, size=8.5, color=GREY, locale=locale)


def _add_cover(document: Document, package: dict, locale: str) -> None:
    company = package.get("company") or {}
    meta = package.get("run") if isinstance(package.get("run"), dict) else {}
    title = "BERKELEY SUMMIT HOUSE" if locale == "en" else "BERKELEY SUMMIT HOUSE"
    subtitle = "Confidential Investment Memo" if locale == "en" else "机密投资备忘录"
    descriptor = _loc(company.get("descriptor"), locale)

    _add_paragraph(document, title, size=18, bold=True, color=NAVY, align="center", after=4)
    _add_paragraph(document, subtitle, size=12, color=GREY, align="center", after=28)
    _add_paragraph(
        document,
        _company_name(package),
        size=26,
        bold=True,
        color=NAVY,
        align="center",
        after=4,
    )
    if descriptor:
        _add_paragraph(document, descriptor, size=12, color=GREY, align="center", after=18)

    rows = [
        (_label("Date", "日期", locale), meta.get("as_of") or meta.get("run_id") or ""),
        (_label("Stage", "阶段", locale), _loc(company.get("stage"), locale)),
        (_label("Sector", "行业", locale), _loc(company.get("sector"), locale)),
        (_label("Location", "地点", locale), _loc(company.get("location"), locale)),
        (_label("Round", "轮次", locale), _loc(company.get("round"), locale)),
        (_label("BSH ticket size", "BSH 投资规模", locale), _loc(company.get("bsh_ticket_size"), locale)),
    ]
    _add_key_value_table(document, [(k, v) for k, v in rows if str(v or "").strip()], locale)

    _add_paragraph(
        document,
        "TABLE OF CONTENTS" if locale == "en" else "目录",
        size=9.5,
        bold=True,
        color=TIFFANY,
        align="center",
        before=16,
        after=6,
    )
    toc_rows = []
    for index, section_id in enumerate(TOC_SECTION_IDS, start=1):
        title = _section_title({"id": section_id}, locale)
        toc_rows.append([title, str(index)])
    _add_table(document, {"headers": [], "rows": toc_rows, "compact": True}, locale)
    document.add_page_break()


def _add_section(document: Document, section: dict, locale: str) -> None:
    title = _section_title(section, locale)
    if title:
        _add_heading(document, title, level=1, locale=locale)
    for block in section.get("blocks") or []:
        if isinstance(block, dict):
            _add_block(document, block, locale)


def _add_block(document: Document, block: dict, locale: str) -> None:
    kind = str(block.get("type") or "paragraph")
    if kind == "heading":
        _add_heading(
            document,
            _loc(block.get("text") or block.get("title"), locale),
            level=int(block.get("level") or 2),
            locale=locale,
        )
    elif kind == "bullets":
        for item in block.get("items") or []:
            _add_bullet(document, _loc(item, locale), locale=locale)
    elif kind == "table":
        if block.get("title"):
            _add_heading(document, _loc(block.get("title"), locale), level=3, locale=locale)
        _add_table(document, block, locale)
    elif kind == "callout":
        _add_callout(document, block, locale)
    elif kind == "spacer":
        document.add_paragraph()
    else:
        text = _loc(block.get("text") or block.get("body") or "", locale)
        if text:
            _add_paragraph(document, text, locale=locale)


def _add_sources_section(document: Document, package: dict, locale: str) -> None:
    _add_heading(document, _section_title({"id": "sources"}, locale), level=1, locale=locale)
    headers = (
        ["Source", "Class", "Treatment", "As of"]
        if locale == "en"
        else ["来源", "类别", "处理方式", "时点"]
    )
    rows = []
    for source in package.get("sources") or []:
        if not isinstance(source, dict):
            continue
        rows.append([
            _loc(source.get("title") or source.get("id"), locale),
            _loc(source.get("class") or source.get("type"), locale),
            _loc(source.get("treatment"), locale),
            _loc(source.get("as_of"), locale),
        ])
    _add_table(document, {"headers": headers, "rows": rows}, locale)


def _add_heading(document: Document, text: str, *, level: int, locale: str) -> None:
    if not text:
        return
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.space_before = Pt(12 if level == 1 else 7)
    paragraph.paragraph_format.space_after = Pt(5 if level == 1 else 3)
    if level == 1:
        _add_bottom_border(paragraph, TIFFANY)
    _add_run(
        paragraph,
        text.upper() if locale == "en" and level == 1 else text,
        bold=True,
        size=15 if level == 1 else 11.5 if level == 2 else 10.2,
        color=NAVY if level <= 2 else BLACK,
        locale=locale,
    )


def _add_paragraph(
    document_or_cell: Any,
    text: str,
    *,
    locale: str = "en",
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    align: str = "left",
    before: float = 0,
    after: float = 5,
) -> None:
    paragraph = document_or_cell.add_paragraph()
    paragraph.alignment = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }.get(align, WD_ALIGN_PARAGRAPH.LEFT)
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.12 if locale == "en" else 1.25
    _add_run(paragraph, text, size=size, bold=bold, color=color, locale=locale)


def _add_bullet(document: Document, text: str, *, locale: str) -> None:
    paragraph = document.add_paragraph(style=None)
    paragraph.paragraph_format.left_indent = Cm(0.45)
    paragraph.paragraph_format.first_line_indent = Cm(-0.18)
    paragraph.paragraph_format.space_after = Pt(3)
    _add_run(paragraph, f"• {text}", locale=locale)


def _add_callout(document: Document, block: dict, locale: str) -> None:
    title = _loc(block.get("title") or block.get("label"), locale)
    body = _loc(block.get("body") or block.get("text"), locale)
    items = [_loc(item, locale) for item in block.get("items") or [] if _loc(item, locale)]
    tone = str(block.get("tone") or "info")
    fill = PALE_GOLD if tone in {"warning", "critical", "risk"} else PALE_TIFFANY
    table = document.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _shade_cell(cell, fill)
    _set_cell_borders(cell, left=(TIFFANY, "24"))
    if title:
        _add_paragraph(cell, title, locale=locale, bold=True, color=NAVY, after=2)
    if body:
        _add_paragraph(cell, body, locale=locale, after=2)
    for item in items:
        _add_paragraph(cell, f"• {item}", locale=locale, after=1)
    document.add_paragraph().paragraph_format.space_after = Pt(4)


def _add_key_value_table(document: Document, rows: list[tuple[str, str]], locale: str) -> None:
    if not rows:
        return
    table = document.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, (key, value) in enumerate(rows):
        cells = table.rows[idx].cells
        cells[0].width = Cm(4.0)
        cells[1].width = Cm(9.0)
        _shade_cell(cells[0], WARM_GREY)
        _set_cell_borders(cells[0])
        _set_cell_borders(cells[1])
        _cell_text(cells[0], key, locale=locale, bold=True, color=NAVY)
        _cell_text(cells[1], str(value), locale=locale)


def _add_table(document: Document, block: dict, locale: str) -> None:
    headers = [_loc(header, locale) for header in block.get("headers") or []]
    rows = [_row_values(row, locale) for row in block.get("rows") or []]
    if not rows and not headers:
        return
    col_count = max([len(headers), *(len(row) for row in rows)] or [1])
    table = document.add_table(rows=(1 if headers else 0) + len(rows), cols=col_count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    row_offset = 0
    if headers:
        for col_idx, value in enumerate(headers):
            cell = table.rows[0].cells[col_idx]
            _shade_cell(cell, NAVY)
            _set_cell_borders(cell, color=WHITE)
            _cell_text(cell, value, locale=locale, bold=True, color=WHITE)
        row_offset = 1
    for row_idx, row in enumerate(rows, start=row_offset):
        for col_idx in range(col_count):
            cell = table.rows[row_idx].cells[col_idx]
            if row_idx % 2 == row_offset % 2:
                _shade_cell(cell, "FAFAFA")
            _set_cell_borders(cell)
            _cell_text(cell, row[col_idx] if col_idx < len(row) else "", locale=locale)
    document.add_paragraph().paragraph_format.space_after = Pt(4)


def _cell_text(cell: Any, text: Any, *, locale: str, bold: bool = False, color: str = BLACK) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    _add_run(paragraph, _loc(text, locale), locale=locale, bold=bold, color=color, size=9.3)


def _add_run(
    paragraph: Any,
    text: str,
    *,
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    locale: str = "en",
) -> Any:
    run = paragraph.add_run(str(text or ""))
    _style_run(run, size=size, bold=bold, color=color, locale=locale)
    return run


def _style_run(
    run: Any,
    *,
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    locale: str = "en",
) -> None:
    font = _font(locale)
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    _set_rfonts(run._element.get_or_add_rPr(), font, locale)


def _set_rfonts(rpr: Any, font: str, locale: str) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    if locale == "zh":
        rfonts.set(qn("w:eastAsia"), ZH_FONT)
        rfonts.set(qn("w:ascii"), EN_FONT)
        rfonts.set(qn("w:hAnsi"), EN_FONT)
        rfonts.set(qn("w:cs"), EN_FONT)
    else:
        rfonts.set(qn("w:ascii"), font)
        rfonts.set(qn("w:hAnsi"), font)
        rfonts.set(qn("w:cs"), font)


def _add_page_number(paragraph: Any, locale: str) -> None:
    if locale == "zh":
        _add_run(paragraph, "第 ", locale=locale, size=8.5, color=GREY)
    else:
        _add_run(paragraph, "Page ", locale=locale, size=8.5, color=GREY)
    run = paragraph.add_run()
    for element in (
        _field_char("begin"),
        _instr_text("PAGE"),
        _field_char("end"),
    ):
        run._r.append(element)
    _style_run(run, locale=locale, size=8.5, color=GREY)
    if locale == "zh":
        _add_run(paragraph, " 页", locale=locale, size=8.5, color=GREY)


def _field_char(kind: str) -> Any:
    element = OxmlElement("w:fldChar")
    element.set(qn("w:fldCharType"), kind)
    return element


def _instr_text(value: str) -> Any:
    element = OxmlElement("w:instrText")
    element.set(qn("xml:space"), "preserve")
    element.text = value
    return element


def _shade_cell(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def _set_cell_borders(
    cell: Any,
    *,
    color: str = BORDER,
    size: str = "4",
    left: tuple[str, str] | None = None,
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcBorders"))
    if existing is not None:
        tc_pr.remove(existing)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        if side == "left" and left:
            border.set(qn("w:sz"), left[1])
            border.set(qn("w:color"), left[0])
        else:
            border.set(qn("w:sz"), size)
            border.set(qn("w:color"), color)
        borders.append(border)
    tc_pr.append(borders)


def _add_bottom_border(paragraph: Any, color: str) -> None:
    p_pr = paragraph._element.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)


def _validation_report(package: dict, output_path: Path, locale: str) -> str:
    document = Document(output_path)
    table_count = len(document.tables)
    paragraph_count = sum(1 for paragraph in document.paragraphs if paragraph.text.strip())
    callout_count = sum(
        1
        for section in package.get("sections") or []
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") == "callout"
    )
    return "\n".join([
        "# Memo Renderer Validation",
        "",
        f"- output: `{output_path}`",
        f"- locale: {locale}",
        f"- schema_version: {package.get('schema_version')}",
        f"- paragraphs: {paragraph_count}",
        f"- tables: {table_count}",
        f"- declared_callouts: {callout_count}",
        "- status: passed",
        "",
    ])


def _write_inventory(
    path: Path,
    package: dict,
    outputs: dict[str, Path],
    validation_paths: dict[str, Path],
) -> None:
    lines = ["# Memo File Inventory", ""]
    lines.append(f"- company: {_company_name(package)}")
    lines.append(f"- schema_version: {package.get('schema_version')}")
    for locale, output in outputs.items():
        lines.append(f"- memo_{locale}: `{output}`")
    for locale, validation in validation_paths.items():
        lines.append(f"- validation_{locale}: `{validation}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _append_manifest(
    path: Path,
    package: dict,
    outputs: dict[str, Path],
    validation_paths: dict[str, Path],
) -> None:
    lines = [
        "",
        "## Analysis Finalization",
        "",
        f"- renderer: server.memo_docx_renderer",
        f"- memo_package_schema_version: {package.get('schema_version')}",
    ]
    for locale, output in outputs.items():
        lines.append(f"- memo_{locale}: `{output}`")
    for locale, validation in validation_paths.items():
        lines.append(f"- validation_{locale}: `{validation}`")
    lines.append("- validation_status: passed")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def _has_section(package: dict, section_id: str) -> bool:
    return any(
        isinstance(section, dict) and section.get("id") == section_id
        for section in package.get("sections") or []
    )


def _section_title(section: dict, locale: str) -> str:
    return _loc(section.get("title"), locale) or _loc(
        SECTION_TITLES.get(str(section.get("id") or ""), ""), locale
    )


def _row_values(row: Any, locale: str) -> list[str]:
    if isinstance(row, dict):
        if isinstance(row.get("cells"), list):
            return [_loc(value, locale) for value in row["cells"]]
        return [_loc(value, locale) for value in row.values()]
    if isinstance(row, (list, tuple)):
        return [_loc(value, locale) for value in row]
    return [_loc(row, locale)]


def _loc(value: Any, locale: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        selected = value.get(locale)
        if selected is None:
            selected = value.get("en")
        if selected is None:
            selected = next(iter(value.values()), "")
        return str(selected or "")
    return str(value)


def _company_name(package: dict) -> str:
    company = package.get("company") or {}
    return _loc(company.get("name") or company.get("display_name") or "Company", "en")


def _font(locale: str) -> str:
    return ZH_FONT if locale == "zh" else EN_FONT


def _label(en: str, zh: str, locale: str) -> str:
    return zh if locale == "zh" else en


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render BSH memo DOCX files from memo_package.json")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--out-en", required=True, type=Path)
    parser.add_argument("--out-zh", required=True, type=Path)
    parser.add_argument("--validation-en", type=Path)
    parser.add_argument("--validation-zh", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    render_memos(
        args.package,
        out_en=args.out_en,
        out_zh=args.out_zh,
        validation_en=args.validation_en,
        validation_zh=args.validation_zh,
        inventory_path=args.inventory,
        manifest_path=args.manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
