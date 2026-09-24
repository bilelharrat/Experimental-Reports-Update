"""Render internal diligence memo Markdown to DOCX.

The internal memo is deliberately separate from the LP-facing investment memo:
Claude writes Markdown, and this renderer turns that Markdown into a Word file
without allowing per-run rendering scripts.

Callers that want the BSH document frame (the Buffett-method memo) opt in
with keyword arguments: ``locale`` switches on the house style (Arial /
Microsoft YaHei, navy headings, bold and italic runs, a zh-CN language tag for
Chinese), and ``header_text`` / ``stamp_text`` / ``footer_label`` /
``footer_note`` / ``doc_title`` / ``author`` / ``created`` /
``decision_rows`` add the header, review stamp, "Page X of Y" footer,
document properties and a decision box under the title. A call with none of
them — the internal diligence memo's — renders exactly as it always has.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
import re
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


class InternalMemoRenderError(RuntimeError):
    """Raised when internal diligence memo rendering cannot proceed."""


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


# The IC prompt's two tables, by their English header rows. Matched as a
# whole row, so a data cell that happens to read "Value" is never touched;
# live 2026-09-23 one Chinese IC memo kept both header rows in English.
_ZH_TABLE_HEADERS = {
    ("item", "why it matters", "owner", "due"): ("事项", "为什么重要", "负责人", "截止时间"),
    ("figure", "value", "source"): ("数字", "取值", "来源"),
}


def localize_zh_placeholders(text: str, *, money_form: bool = False) -> str:
    """The Chinese IC memo's fixed renderings of the prompts' placeholders
    ("[TO BE DETERMINED BY IC]", "[date to set]", "[owner to assign]") and
    of owner-role table cells ("deal lead", "legal", "finance") and of the
    two tables' English header rows — the placeholder and role maps are the
    maps the LP memo renderer uses, so the two Chinese documents agree. The
    agent writes these verbatim in both languages; left alone they print
    as English inside the Chinese memo. ``money_form`` also rewrites 万/亿美元
    amounts in the LP memo's $ form (the IC decision memo); the Buffett memo
    keeps its own Chinese money convention and leaves it off."""
    from . import memo_docx_renderer

    out: list[str] = []
    for line in text.splitlines():
        if money_form:
            line = memo_docx_renderer.normalize_zh_money(line)
        line = memo_docx_renderer.apply_zh_placeholders(line)
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and not _TABLE_SEPARATOR_RE.match(stripped):
            cells = stripped[1:-1].split("|")
            header = _ZH_TABLE_HEADERS.get(tuple(cell.strip().lower() for cell in cells))
            cells = [
                f" {memo_docx_renderer.owner_role_zh(cell) or cell.strip()} " for cell in (header or cells)
            ]
            line = "|" + "|".join(cells) + "|"
        out.append(line)
    return "\n".join(out)


def render_internal_memo(
    markdown_path: Path | str,
    docx_path: Path | str,
    *,
    markdown_text: str | None = None,
    locale: str | None = None,
    header_text: str | None = None,
    stamp_text: str | None = None,
    stamp_color: str | None = None,
    footer_label: str | None = None,
    footer_note: str | None = None,
    doc_title: str | None = None,
    doc_subject: str | None = None,
    author: str | None = None,
    created: date | datetime | str | None = None,
    decision_rows: list[tuple[str, str]] | None = None,
    zh_money_form: bool = False,
) -> dict:
    """Render an internal diligence memo Markdown file to DOCX.

    ``markdown_text`` renders that text instead of the file's (the file
    path is still reported); every other keyword is the opt-in document
    frame described in the module docstring.
    """
    md_path = Path(markdown_path)
    out_path = Path(docx_path)
    if markdown_text is None:
        if not md_path.exists():
            raise InternalMemoRenderError(f"Internal memo markdown missing: {md_path}")
        text = md_path.read_text(encoding="utf-8").strip()
    else:
        text = str(markdown_text).strip()
    if locale == "zh":
        text = localize_zh_placeholders(text, money_form=zh_money_form)
    if len(text) < 200:
        raise InternalMemoRenderError(
            "Internal memo markdown is too short to render as a diligence memo."
        )

    frame = _frame_from_options(
        locale=locale,
        header_text=header_text,
        stamp_text=stamp_text,
        stamp_color=stamp_color,
        footer_label=footer_label,
        footer_note=footer_note,
        doc_title=doc_title,
        doc_subject=doc_subject,
        author=author,
        created=created,
        decision_rows=decision_rows,
    )
    document = Document()
    if frame is None:
        _configure_document(document)
        _render_markdown(document, text)
    else:
        _configure_framed_document(document, frame)
        _render_markdown(document, text, frame=frame)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return {"ok": True, "markdown_path": str(md_path), "docx_path": str(out_path)}


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    normal = document.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)

    for style_name, size in (
        ("Title", 18),
        ("Heading 1", 15),
        ("Heading 2", 13),
        ("Heading 3", 11.5),
    ):
        style = document.styles[style_name]
        style.font.name = "Aptos Display" if style_name == "Title" else "Aptos"
        style.font.size = Pt(size)
        style.font.bold = True


def _render_markdown(document: Document, text: str, frame: "_Frame | None" = None) -> None:
    lines = text.splitlines()
    i = 0
    paragraph_buffer: list[str] = []
    # The decision box sits under the title block: before the first section
    # heading (or at the end when the text has none).
    box_pending = bool(frame is not None and frame.decision_rows)

    def emit_decision_box() -> None:
        nonlocal box_pending
        if box_pending and frame is not None:
            _add_decision_box(document, frame)
        box_pending = False

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        value = " ".join(line.strip() for line in paragraph_buffer).strip()
        if value:
            if frame is None:
                document.add_paragraph(_clean_inline_markdown(value))
            else:
                paragraph = document.add_paragraph()
                _add_inline_runs(paragraph, value, frame)
        paragraph_buffer = []

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if frame is not None and _is_rule(stripped):
            flush_paragraph()
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            flush_paragraph()
            table_lines = [stripped, lines[i + 1].strip()]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            if frame is None:
                _add_markdown_table(document, table_lines)
            else:
                _add_framed_table(document, table_lines, frame)
            continue

        heading = _heading(stripped)
        if heading:
            flush_paragraph()
            level, body = heading
            if frame is None:
                if level == 1:
                    document.add_paragraph(_clean_inline_markdown(body), style="Title")
                else:
                    document.add_heading(_clean_inline_markdown(body), level=min(level - 1, 3))
            else:
                if level >= 2:
                    emit_decision_box()
                _add_framed_heading(document, body, level)
            i += 1
            continue

        bullet = _bullet(stripped)
        if bullet:
            flush_paragraph()
            if frame is None:
                document.add_paragraph(_clean_inline_markdown(bullet), style="List Bullet")
            else:
                paragraph = document.add_paragraph(style="List Bullet")
                _add_inline_runs(paragraph, bullet, frame)
            i += 1
            continue

        paragraph_buffer.append(stripped)
        i += 1

    flush_paragraph()
    emit_decision_box()


def _heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,4})\s+(.+)$", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _bullet(line: str) -> str | None:
    match = re.match(r"^[-*]\s+(.+)$", line)
    return match.group(1).strip() if match else None


def _is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line))


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [_clean_inline_markdown(cell.strip()) for cell in stripped.split("|")]


def _add_markdown_table(document: Document, table_lines: list[str]) -> None:
    headers = _split_table_row(table_lines[0])
    rows = [_split_table_row(line) for line in table_lines[2:]]
    if not headers or not rows:
        return
    width = len(headers)
    table = document.add_table(rows=1, cols=width)
    table.style = "Table Grid"
    for idx, header in enumerate(headers):
        cell = table.cell(0, idx)
        cell.text = header
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for idx in range(width):
            cells[idx].text = row[idx] if idx < len(row) else ""


def _clean_inline_markdown(value: str) -> str:
    out = value.strip()
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"\*([^*]+)\*", r"\1", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", out)
    return out


# ---- opt-in document frame ---------------------------------------------------
#
# House style shared with the late-stage memo (memo_docx_renderer): Arial for
# Latin text, Microsoft YaHei for East Asian text (it ships with Word for Mac
# and Windows; browsers fall back to PingFang SC), navy headings. The two
# helpers below mirror memo_docx_renderer._set_rfonts / _add_page_number,
# copied rather than imported so this renderer keeps no dependency on the
# late-stage module, and extended with NUMPAGES for "Page X of Y".

EN_FONT = "Arial"
ZH_FONT = "Microsoft YaHei"
NAVY = "1B2A4A"
GREY = "666666"
BORDER = "BFBFBF"
LABEL_FILL = "E6F7F6"
HEADER_FILL = "EEF2F7"
DEFAULT_STAMP_COLOR = "9A6700"

_THEME_FONT_ATTRS = ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme")


@dataclass(frozen=True)
class _Frame:
    locale: str
    header_text: str | None
    stamp_text: str | None
    stamp_color: str
    footer_label: str | None
    footer_note: str | None
    doc_title: str | None
    doc_subject: str | None
    author: str | None
    created: datetime | None
    decision_rows: tuple[tuple[str, str], ...]


def _frame_from_options(**options: Any) -> _Frame | None:
    if all(value is None for value in options.values()):
        return None
    locale = "zh" if str(options.get("locale") or "en").lower().startswith("zh") else "en"
    rows = tuple(
        (str(label), str(value))
        for label, value in (options.get("decision_rows") or [])
        if str(label or "").strip() and str(value or "").strip()
    )
    return _Frame(
        locale=locale,
        header_text=_clean_text(options.get("header_text")),
        stamp_text=_clean_text(options.get("stamp_text")),
        stamp_color=_hex_color(options.get("stamp_color")) or DEFAULT_STAMP_COLOR,
        footer_label=_clean_text(options.get("footer_label")),
        footer_note=_clean_text(options.get("footer_note")),
        doc_title=_clean_text(options.get("doc_title")),
        doc_subject=_clean_text(options.get("doc_subject")),
        author=_clean_text(options.get("author")),
        created=_as_datetime(options.get("created")),
        decision_rows=rows,
    )


def _clean_text(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _hex_color(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("#").upper()
    return text if re.fullmatch(r"[0-9A-F]{6}", text) else None


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=timezone.utc)
    text = str(value).strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _set_rfonts(rpr: Any) -> None:
    """Explicit Arial + Microsoft YaHei, with the theme-font attributes
    removed: a theme attribute outranks an explicit font name in Word, so
    the default template's headings would otherwise stay in the theme's
    font."""
    rfonts = rpr.get_or_add_rFonts()
    for attr in _THEME_FONT_ATTRS:
        key = qn(attr)
        if key in rfonts.attrib:
            del rfonts.attrib[key]
    rfonts.set(qn("w:ascii"), EN_FONT)
    rfonts.set(qn("w:hAnsi"), EN_FONT)
    rfonts.set(qn("w:cs"), EN_FONT)
    rfonts.set(qn("w:eastAsia"), ZH_FONT)


def _style_run(
    run: Any,
    *,
    size: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    color: str | None = None,
) -> None:
    _set_rfonts(run._element.get_or_add_rPr())
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _configure_framed_document(document: Document, frame: _Frame) -> None:
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    styles = document.styles
    _configure_doc_defaults(document, frame.locale)

    normal = styles["Normal"]
    normal.font.name = EN_FONT
    normal.font.size = Pt(10.5)
    _set_rfonts(normal.element.get_or_add_rPr())
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25 if frame.locale == "zh" else 1.15

    for style_name, size, before, after in (
        ("Title", 18, 0, 6),
        ("Heading 1", 14, 14, 4),
        ("Heading 2", 12, 10, 3),
        ("Heading 3", 11, 8, 2),
    ):
        style = styles[style_name]
        style.font.name = EN_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(NAVY)
        _set_rfonts(style.element.get_or_add_rPr())
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        _restyle_linked_character_style(document, style, size)
    _navy_title_rule(styles["Title"])

    if frame.locale == "zh":
        _set_theme_font_lang(document, "zh-CN")

    props = document.core_properties
    if frame.doc_title:
        props.title = frame.doc_title
    if frame.doc_subject:
        props.subject = frame.doc_subject
    if frame.author:
        props.author = frame.author
        props.last_modified_by = frame.author
    props.comments = frame.footer_note or ""
    props.language = "zh-CN" if frame.locale == "zh" else "en-US"
    props.revision = 1
    if frame.created is not None:
        props.created = frame.created
        props.modified = frame.created

    if frame.header_text or frame.stamp_text:
        header = section.header
        first = header.paragraphs[0]
        first.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        target = first
        if frame.header_text:
            _style_run(first.add_run(frame.header_text), size=8.5, color=GREY)
            target = header.add_paragraph() if frame.stamp_text else first
            target.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if frame.stamp_text:
            _style_run(
                target.add_run(frame.stamp_text), size=8.5, bold=True, color=frame.stamp_color
            )

    # Every framed document is paginated: "Page X of Y" in the footer.
    footer = section.footer
    line = footer.paragraphs[0]
    line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if frame.footer_label:
        _style_run(line.add_run(frame.footer_label), size=8, color=GREY)
    _append_page_fields(line, frame.locale, separator=bool(frame.footer_label))
    if frame.footer_note:
        note = footer.add_paragraph()
        note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _style_run(note.add_run(frame.footer_note), size=7.5, italic=True, color=GREY)


def _configure_doc_defaults(document: Document, locale: str) -> None:
    defaults = document.styles.element.find(qn("w:docDefaults"))
    if defaults is None:
        return
    rpr_default = defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        return
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        return
    _set_rfonts(rpr)
    if locale == "zh":
        lang = rpr.find(qn("w:lang"))
        if lang is None:
            lang = OxmlElement("w:lang")
            rpr.append(lang)
        lang.set(qn("w:val"), "en-US")
        lang.set(qn("w:eastAsia"), "zh-CN")


def _set_theme_font_lang(document: Document, east_asia: str) -> None:
    settings = document.settings.element
    element = settings.find(qn("w:themeFontLang"))
    if element is None:
        element = OxmlElement("w:themeFontLang")
        element.set(qn("w:val"), "en-US")
        settings.append(element)
    element.set(qn("w:eastAsia"), east_asia)


def _restyle_linked_character_style(document: Document, style: Any, size: float) -> None:
    """Give a heading's linked character style ("Heading 1 Char") the same
    font and colour. Word ignores it for a whole-paragraph heading, but
    viewers such as docx-preview merge it into the heading's runs, where
    the template's theme font and blue would otherwise win."""
    link = style.element.find(qn("w:link"))
    if link is None:
        return
    linked_id = link.get(qn("w:val"))
    for candidate in document.styles:
        if getattr(candidate, "style_id", None) != linked_id:
            continue
        candidate.font.name = EN_FONT
        candidate.font.size = Pt(size)
        candidate.font.bold = True
        candidate.font.color.rgb = RGBColor.from_string(NAVY)
        _set_rfonts(candidate.element.get_or_add_rPr())
        return


def _navy_title_rule(style: Any) -> None:
    ppr = style.element.find(qn("w:pPr"))
    if ppr is None:
        return
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        return
    for edge in borders:
        for attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
            key = qn(attr)
            if key in edge.attrib:
                del edge.attrib[key]
        edge.set(qn("w:color"), NAVY)


def _append_page_fields(paragraph: Any, locale: str, *, separator: bool) -> None:
    """"Page X of Y" / "第 X 页，共 Y 页" as PAGE and NUMPAGES fields.

    The static words share runs with the field characters, so a viewer
    that skips field runs (the web viewer's docx-preview, which cannot
    paginate) shows nothing rather than a bare "Page of"; Word and the PDF
    export show the full line."""
    if locale == "zh":
        before, middle, after = "第 ", " 页，共 ", " 页"
    else:
        before, middle, after = "Page ", " of ", ""
    lead = (" · " if separator else "") + before
    run = paragraph.add_run()
    run._r.append(_text_element(lead))
    run._r.append(_field_char("begin"))
    _style_run(run, size=8, color=GREY)
    run = paragraph.add_run()
    run._r.append(_instr_text(" PAGE "))
    _style_run(run, size=8, color=GREY)
    run = paragraph.add_run()
    run._r.append(_field_char("end"))
    run._r.append(_text_element(middle))
    run._r.append(_field_char("begin"))
    _style_run(run, size=8, color=GREY)
    run = paragraph.add_run()
    run._r.append(_instr_text(" NUMPAGES "))
    _style_run(run, size=8, color=GREY)
    run = paragraph.add_run()
    run._r.append(_field_char("end"))
    if after:
        run._r.append(_text_element(after))
    _style_run(run, size=8, color=GREY)


def _field_char(kind: str) -> Any:
    element = OxmlElement("w:fldChar")
    element.set(qn("w:fldCharType"), kind)
    return element


def _instr_text(value: str) -> Any:
    element = OxmlElement("w:instrText")
    element.set(qn("xml:space"), "preserve")
    element.text = value
    return element


def _text_element(value: str) -> Any:
    element = OxmlElement("w:t")
    element.set(qn("xml:space"), "preserve")
    element.text = value
    return element


_RULE_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|[^)\s]+)\)")
_INLINE_RE = re.compile(
    r"\*\*\*(?P<bi>[^*\n]+?)\*\*\*"
    r"|\*\*(?P<b>[^*\n]+?)\*\*"
    r"|(?<![\w*])\*(?P<i>[^*\s][^*\n]*?)(?<!\s)\*(?![\w*])"
)


def _is_rule(line: str) -> bool:
    return bool(_RULE_RE.match(line))


def _add_inline_runs(
    paragraph: Any,
    value: str,
    frame: _Frame,
    *,
    bold: bool | None = None,
    size: float | None = None,
    color: str | None = None,
) -> None:
    """``**bold**`` and ``*italic*`` as real runs; code spans and links
    keep their text."""
    text = _LINK_RE.sub(r"\1", _CODE_RE.sub(r"\1", value.strip()))
    position = 0

    def plain(piece: str) -> None:
        if piece:
            run = paragraph.add_run(piece)
            _format_body_run(run, bold=bold, size=size, color=color)

    for match in _INLINE_RE.finditer(text):
        plain(text[position:match.start()])
        if match.group("bi") is not None:
            run = paragraph.add_run(match.group("bi"))
            _format_body_run(run, bold=True, italic=True, size=size, color=color)
        elif match.group("b") is not None:
            run = paragraph.add_run(match.group("b"))
            _format_body_run(run, bold=True, size=size, color=color)
        else:
            run = paragraph.add_run(match.group("i"))
            _format_body_run(run, bold=bold, italic=True, size=size, color=color)
        position = match.end()
    plain(text[position:])


def _format_body_run(
    run: Any,
    *,
    bold: bool | None = None,
    italic: bool | None = None,
    size: float | None = None,
    color: str | None = None,
) -> None:
    # Body runs inherit Arial/YaHei from the Normal style; only set what
    # differs, so the XML stays small.
    if bold:
        run.font.bold = True
    if italic:
        run.font.italic = True
    if size is not None:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _add_framed_heading(document: Document, body: str, level: int) -> None:
    text = _strip_emphasis(body)
    if level == 1:
        document.add_paragraph(text, style="Title")
    else:
        document.add_heading(text, level=min(level - 1, 3))


def _strip_emphasis(value: str) -> str:
    out = _LINK_RE.sub(r"\1", _CODE_RE.sub(r"\1", value.strip()))
    out = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"\1", out)
    return out


def _add_framed_table(document: Document, table_lines: list[str], frame: _Frame) -> None:
    headers = _raw_table_row(table_lines[0])
    rows = [_raw_table_row(line) for line in table_lines[2:]]
    if not headers or not rows:
        return
    width = len(headers)
    table = document.add_table(rows=1, cols=width)
    table.style = "Table Grid"
    _set_table_borders(table, BORDER)
    for idx, header in enumerate(headers):
        cell = table.cell(0, idx)
        _shade_cell(cell, HEADER_FILL)
        _add_inline_runs(cell.paragraphs[0], header, frame, bold=True, size=9.5, color=NAVY)
    for row in rows:
        cells = table.add_row().cells
        for idx in range(width):
            value = row[idx] if idx < len(row) else ""
            if value:
                _add_inline_runs(cells[idx].paragraphs[0], value, frame, size=9.5)


def _raw_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _add_decision_box(document: Document, frame: _Frame) -> None:
    rows = frame.decision_rows
    if not rows:
        return
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.autofit = False
    _set_table_borders(table, BORDER)
    widths = (Inches(1.7), Inches(5.3))
    for label, value in rows:
        cells = table.add_row().cells
        _shade_cell(cells[0], LABEL_FILL)
        label_run = cells[0].paragraphs[0].add_run(label)
        _style_run(label_run, size=9.5, bold=True, color=NAVY)
        _add_inline_runs(cells[1].paragraphs[0], value, frame, size=9.5)
        for cell, cell_width in zip(cells, widths):
            cell.width = cell_width
    for column, column_width in zip(table.columns, widths):
        column.width = column_width


def _shade_cell(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


# tblPr children that must come after tblBorders (ECMA-376 sequence).
_TBL_BORDERS_SUCCESSORS = (
    "w:shd",
    "w:tblLayout",
    "w:tblCellMar",
    "w:tblLook",
    "w:tblCaption",
    "w:tblDescription",
    "w:tblPrChange",
)


def _set_table_borders(table: Any, color: str) -> None:
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)
        borders.append(element)
    successor = next(
        (
            child
            for child in tbl_pr
            if child.tag in {qn(tag) for tag in _TBL_BORDERS_SUCCESSORS}
        ),
        None,
    )
    if successor is None:
        tbl_pr.append(borders)
    else:
        successor.addprevious(borders)
