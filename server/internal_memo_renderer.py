"""Render internal diligence memo Markdown to DOCX.

The internal memo is deliberately separate from the LP-facing investment memo:
Claude writes Markdown, and this renderer turns that Markdown into a Word file
without allowing per-run rendering scripts.
"""
from __future__ import annotations

from pathlib import Path
import re

from docx import Document
from docx.shared import Inches, Pt


class InternalMemoRenderError(RuntimeError):
    """Raised when internal diligence memo rendering cannot proceed."""


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def render_internal_memo(markdown_path: Path | str, docx_path: Path | str) -> dict:
    """Render an internal diligence memo Markdown file to DOCX."""
    md_path = Path(markdown_path)
    out_path = Path(docx_path)
    if not md_path.exists():
        raise InternalMemoRenderError(f"Internal memo markdown missing: {md_path}")
    text = md_path.read_text(encoding="utf-8").strip()
    if len(text) < 200:
        raise InternalMemoRenderError(
            "Internal memo markdown is too short to render as a diligence memo."
        )

    document = Document()
    _configure_document(document)
    _render_markdown(document, text)
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


def _render_markdown(document: Document, text: str) -> None:
    lines = text.splitlines()
    i = 0
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        value = " ".join(line.strip() for line in paragraph_buffer).strip()
        if value:
            document.add_paragraph(_clean_inline_markdown(value))
        paragraph_buffer = []

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
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
            _add_markdown_table(document, table_lines)
            continue

        heading = _heading(stripped)
        if heading:
            flush_paragraph()
            level, body = heading
            if level == 1:
                document.add_paragraph(_clean_inline_markdown(body), style="Title")
            else:
                document.add_heading(_clean_inline_markdown(body), level=min(level - 1, 3))
            i += 1
            continue

        bullet = _bullet(stripped)
        if bullet:
            flush_paragraph()
            document.add_paragraph(_clean_inline_markdown(bullet), style="List Bullet")
            i += 1
            continue

        paragraph_buffer.append(stripped)
        i += 1

    flush_paragraph()


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
