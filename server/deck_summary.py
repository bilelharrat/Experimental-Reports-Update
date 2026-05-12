"""Bilingual deck summarization via Claude Code CLI.

For an uploaded PPTX or PDF, spawn `claude -p` with the source deck in a
per-job work directory. Claude reads the deck page-by-page and produces a
structured English + 中文 summary (validated against ``SUMMARY_SCHEMA``).

Stored on the file's index record under `summary` so the modal can render
instantly on subsequent opens. Re-generation overwrites the existing entry.

This module does **not** call the OpenAI SDK. If the `claude` CLI isn't
installed, summarization returns an error and the user is asked to install
Claude Code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Slide:
    slide_no: int  # 1-indexed
    text: str
    notes: str = ""


# ---- slide extraction --------------------------------------------------


def _extract_pptx(path: Path) -> list[Slide]:
    try:
        from pptx import Presentation  # type: ignore
    except ImportError:
        logger.warning("python-pptx not installed; can't extract %s", path)
        return []
    try:
        prs = Presentation(str(path))
    except Exception as exc:
        logger.warning("Failed to open pptx %s: %s", path, exc)
        return []
    slides: list[Slide] = []
    for i, slide in enumerate(prs.slides, start=1):
        text_parts: list[str] = []
        for shape in slide.shapes:
            tf = getattr(shape, "text_frame", None)
            if tf is not None and tf.text:
                text_parts.append(tf.text)
            elif hasattr(shape, "text") and shape.text:
                text_parts.append(shape.text)
            # Tables — extract cell text
            if shape.has_table if hasattr(shape, "has_table") else False:
                for row in shape.table.rows:  # type: ignore
                    for cell in row.cells:
                        if cell.text:
                            text_parts.append(cell.text)
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = (slide.notes_slide.notes_text_frame.text or "").strip()
        text = "\n".join(t.strip() for t in text_parts if t and t.strip())
        slides.append(Slide(slide_no=i, text=text, notes=notes))
    return slides


def _extract_pdf(path: Path) -> list[Slide]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        logger.warning("pypdf not installed; can't extract %s", path)
        return []
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        logger.warning("Failed to open pdf %s: %s", path, exc)
        return []
    slides: list[Slide] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        slides.append(Slide(slide_no=i, text=text.strip()))
    return slides


def extract_slides(
    path: Path,
    kind: str,
    *,
    ppt_preview: Path | None = None,
    progress=None,
) -> list[Slide]:
    """Extract per-slide text. For .ppt (binary, not python-pptx-readable),
    falls back to the cached PDF preview if one was supplied. Emits a
    `slide_extracted` event for each slide via `progress` if provided.
    """
    if progress:
        progress.emit("stage", stage="extracting", message="Reading slides")

    if kind == "pptx":
        slides = _extract_pptx(path)
    elif kind == "pdf":
        slides = _extract_pdf(path)
    elif kind == "ppt" and ppt_preview is not None and ppt_preview.exists():
        slides = _extract_pdf(ppt_preview)
    else:
        slides = []

    if progress:
        for s in slides:
            preview = (s.text or s.notes or "").replace("\n", " ").strip()
            progress.emit(
                "slide_extracted",
                slide_no=s.slide_no,
                preview=preview[:120],
                chars=len(s.text or ""),
                has_notes=bool(s.notes),
            )
        progress.emit(
            "stage",
            stage="extracted",
            message=f"Extracted {len(slides)} slide{'s' if len(slides) != 1 else ''}",
            count=len(slides),
        )
    return slides


# ---- Schema, system prompt, and quality bar (used by Claude runner) ----


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "language": {
            "type": "string",
            "enum": ["en", "zh", "mixed", "other"],
            "description": "Detected source language of the deck.",
        },
        "exec_summary": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "en": {"type": "string"},
                "zh": {"type": "string"},
            },
            "required": ["en", "zh"],
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "en": {"type": "string"},
                            "zh": {"type": "string"},
                        },
                        "required": ["en", "zh"],
                    },
                    "body": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "en": {"type": "string"},
                            "zh": {"type": "string"},
                        },
                        "required": ["en", "zh"],
                    },
                    "slide_refs": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["title", "body", "slide_refs"],
            },
        },
    },
    "required": ["language", "exec_summary", "sections"],
}


SYSTEM_PROMPT = (
    "You are summarizing a presentation deck for an investment-research "
    "dashboard. The reader is a senior analyst — they need signal, not "
    "filler.\n\n"
    "You will receive the deck as numbered slides with text content and any "
    "speaker notes. Produce a BILINGUAL summary in English and 简体中文.\n\n"
    "Output structure:\n"
    "1. `exec_summary` — 3–5 sentences. The TL;DR: what this deck is, who "
    "or what it's about, the central thesis or ask. Read like an executive "
    "briefing. Specific. Concrete.\n"
    "2. `sections` — 4–8 supporting-detail sections. Each has:\n"
    "   - `title`: short noun phrase, no padding (≤6 words).\n"
    "   - `body`: 2–4 dense sentences with specific facts (numbers, names, "
    "dates, claims). Reference slides naturally where it adds precision — "
    "in English use \"(see slide 5)\" or \"(slides 5–7)\"; in Chinese use "
    "\"(参见第5页)\" or \"(参见第5–7页)\".\n"
    "   - `slide_refs`: integer list of 1-indexed slide numbers backing this "
    "section.\n\n"
    "Both languages must convey the SAME information. The Chinese version "
    "is not a word-for-word translation — render naturally in 简体中文 "
    "while preserving every fact and number.\n\n"
    "HARD RULES — every word earns its place:\n"
    "- No marketing adjectives (\"innovative\", \"leading\", \"world-class\", "
    "\"cutting-edge\") unless they appear verbatim in the deck.\n"
    "- No throat-clearing sentences (\"This deck covers various topics…\"). "
    "If you'd write filler, delete it.\n"
    "- Don't invent facts. If a slide is empty or unclear, omit it.\n"
    "- `slide_refs` must be real slide numbers from the input.\n"
    "- For very short decks (<5 slides), 2–3 sections is fine.\n"
    "- Set `language` to the detected source language of the deck content."
)


QUALITY_BAR = (
    "- Executive summary: 3–5 sentences. The TL;DR — what this deck is, "
    "who/what it's about, the central thesis. Specific. Concrete.\n"
    "- 4–8 supporting-detail sections. Each: short noun-phrase title (≤6 "
    "words), 2–4 dense sentences (numbers, names, dates, claims), and "
    "slide_refs as integer 1-indexed slide numbers.\n"
    "- Both languages (`en` and `zh` / 简体中文) must convey the SAME "
    "information. The Chinese version is naturally rendered, not literal.\n"
    "- No marketing adjectives ('innovative', 'leading', 'world-class') "
    "unless the deck uses them as a direct quote.\n"
    "- No throat-clearing sentences. If you'd write 'the deck covers various "
    "topics', delete it.\n"
    "- Don't invent. If a slide is unclear or empty, omit it.\n"
    "- Reference slides naturally where it adds precision: '(see slide 5)' / "
    "'(参见第5页)'.\n"
    "- For very short decks (<5 slides), 2–3 sections is fine."
)


def summarize_slides(
    slides: list[Slide],
    *,
    hint_title: str | None = None,
    file_path: Path | None = None,
    kind: str | None = None,
    progress=None,
    work_dir: Path | None = None,
    speed: str = "auto",
) -> dict:
    """Generate a bilingual deck summary via Claude Code CLI.

    Spawns `claude -p ... --output-format stream-json --json-schema ...`
    with the source deck staged in a per-job work directory. Claude reads
    the deck, writes a per-slide `progress.md`, and returns a structured
    JSON answer validated against ``SUMMARY_SCHEMA``.

    Returns ``{"error": "..."}`` if the `claude` CLI isn't installed or
    if there's no usable source file — no OpenAI fallback.
    """
    if not slides and file_path is None:
        return {"error": "Couldn't extract any slide text from this file."}

    source_for_claude: Path | None = None
    if file_path and file_path.exists() and kind in ("pdf", "pptx", "ppt"):
        source_for_claude = file_path

    from . import claude_runner

    if not claude_runner.is_available():
        return {
            "error": (
                "Claude Code (`claude`) not on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            )
        }
    if source_for_claude is None:
        return {
            "error": (
                "No source file available to Claude. PPTX/PDF files are "
                "summarized directly; .ppt needs a PDF preview first."
            )
        }

    if work_dir is None:
        work_dir = source_for_claude.parent / f"{source_for_claude.stem}__job"
    result = claude_runner.run_summary(
        work_dir=work_dir,
        source_path=source_for_claude,
        hint_title=hint_title,
        schema=SUMMARY_SCHEMA,
        quality_bar=QUALITY_BAR,
        page_count=len(slides) if slides else None,
        speed=speed,
        progress=progress,
    )
    if "error" not in result:
        result.setdefault("slide_count", len(slides) or None)
        result.setdefault("slides_used", len(slides) or None)
    return result
