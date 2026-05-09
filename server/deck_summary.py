"""Bilingual deck summarization.

For an uploaded PPTX or PDF, extract per-slide text (and PPTX speaker notes)
and send to OpenAI to produce a structured English+中文 summary with an exec
summary and supporting sections that cite specific slide numbers.

Stored on the file's index record under `summary` so the modal can render
instantly on subsequent opens. Re-generation overwrites the existing entry.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("OPENAI_DECK_SUMMARY_MODEL", "gpt-4.1")

# Cap how much text we send. ~50K chars covers a ~80-100-slide deck with
# rich text + notes; longer decks get tail-truncated.
MAX_INPUT_CHARS = 50_000


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


def _format_slides_for_prompt(slides: list[Slide]) -> tuple[str, int]:
    """Format slides as a single prompt-ready string. Returns (text, slides_used)."""
    chunks: list[str] = []
    used = 0
    total = 0
    for s in slides:
        block_lines = [f"=== Slide {s.slide_no} ==="]
        if s.text:
            block_lines.append(s.text)
        if s.notes:
            block_lines.append(f"[Speaker notes]\n{s.notes}")
        block = "\n".join(block_lines)
        if total + len(block) > MAX_INPUT_CHARS:
            chunks.append(
                f"=== ... (truncated; deck has {len(slides)} slides total, "
                f"only first {used} included) ==="
            )
            break
        chunks.append(block)
        total += len(block) + 2
        used += 1
    return "\n\n".join(chunks), used


# ---- OpenAI summarization ---------------------------------------------


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


def _is_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _has_meaningful_text(slides: list[Slide]) -> bool:
    """At least one slide has >= 20 chars of extractable text."""
    return any(len((s.text or "")) >= 20 or (s.notes and len(s.notes) >= 20) for s in slides)


def _call_openai_summarize(
    *,
    content_blocks: list[dict],
    slide_count: int,
    slides_used: int,
    progress=None,
) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package not installed."}
    client = OpenAI()

    if progress:
        progress.emit("stage", stage="generating", message="BSH model is composing")

    chars_seen = 0
    last_emit_chars = 0
    EMIT_EVERY_CHARS = 200
    try:
        with client.responses.stream(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content_blocks},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "deck_summary",
                    "schema": SUMMARY_SCHEMA,
                    "strict": True,
                }
            },
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", "")
                if etype == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    chars_seen += len(delta)
                    if progress and chars_seen - last_emit_chars >= EMIT_EVERY_CHARS:
                        progress.emit(
                            "thinking",
                            chars=chars_seen,
                            tail=delta[-160:],
                        )
                        last_emit_chars = chars_seen
            final = stream.get_final_response()
    except Exception as exc:  # noqa: BLE001
        msg = f"OpenAI summary failed: {type(exc).__name__}: {exc}"
        logger.warning(msg)
        return {"error": msg}

    raw = getattr(final, "output_text", "") or ""
    if not raw:
        return {"error": "OpenAI returned empty output."}
    if progress:
        progress.emit("stage", stage="parsing", message="Parsing structured output", chars=chars_seen)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"OpenAI returned non-JSON: {exc}"}

    data["slide_count"] = slide_count
    data["slides_used"] = slides_used
    return data


def _summarize_text(
    slides: list[Slide], *, hint_title: str | None, progress=None
) -> dict:
    prompt_text, slides_used = _format_slides_for_prompt(slides)
    if slides_used == 0:
        return {"error": "Slide content too sparse to summarize."}
    user_prompt_lines: list[str] = []
    if hint_title:
        user_prompt_lines.append(f"Deck title (hint): {hint_title}")
    user_prompt_lines.append(f"Deck has {len(slides)} slide(s).")
    user_prompt_lines.append("Source slides (extracted text):")
    user_prompt_lines.append("---")
    user_prompt_lines.append(prompt_text)
    user_prompt_lines.append("---")
    return _call_openai_summarize(
        content_blocks=[
            {"type": "input_text", "text": "\n".join(user_prompt_lines)}
        ],
        slide_count=len(slides),
        slides_used=slides_used,
        progress=progress,
    )


def _summarize_pdf_visually(
    pdf_path: Path,
    *,
    slide_count: int,
    hint_title: str | None,
    progress=None,
) -> dict:
    """Upload the PDF to OpenAI and let the model read it visually."""
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package not installed."}
    if not pdf_path.exists():
        return {"error": "PDF not on disk."}

    client = OpenAI()
    uploaded_id: str | None = None
    if progress:
        progress.emit(
            "stage",
            stage="uploading",
            message="Uploading PDF to BSH model",
            size_bytes=pdf_path.stat().st_size,
        )
    try:
        with pdf_path.open("rb") as fh:
            uploaded = client.files.create(file=fh, purpose="user_data")
        uploaded_id = uploaded.id
        if progress:
            progress.emit(
                "stage", stage="uploaded", message="Upload complete", file_id=uploaded.id
            )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"PDF upload failed: {type(exc).__name__}: {exc}"}

    user_text_lines: list[str] = []
    if hint_title:
        user_text_lines.append(f"Deck title (hint): {hint_title}")
    user_text_lines.append(
        f"The attached PDF has {slide_count} pages — treat each PDF page as "
        "one slide, 1-indexed, in order."
    )
    user_text_lines.append(
        "Read the slides and produce the bilingual summary per the schema. "
        "slide_refs must be 1-indexed page numbers."
    )

    try:
        result = _call_openai_summarize(
            content_blocks=[
                {"type": "input_file", "file_id": uploaded_id},
                {"type": "input_text", "text": "\n".join(user_text_lines)},
            ],
            slide_count=slide_count,
            slides_used=slide_count,
            progress=progress,
        )
    finally:
        if uploaded_id:
            try:
                client.files.delete(uploaded_id)
            except Exception:
                pass
    if "error" not in result:
        result["mode"] = "vision"
    return result


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
) -> dict:
    """Generate a bilingual deck summary.

    Primary path: spawn Claude Code (`claude -p ... --output-format stream-json
    --json-schema ...`) with the source deck staged in a per-job work
    directory. Claude reads the deck, writes a per-slide `progress.md`, and
    returns a structured JSON answer validated against SUMMARY_SCHEMA.

    Fallback (only when `claude` isn't on PATH): the previous OpenAI text /
    vision pipeline.
    """
    if not slides and file_path is None:
        return {"error": "Couldn't extract any slide text from this file."}

    # Decide what to feed Claude. We always prefer the original/visual file
    # because Claude can read it directly via the Read tool (handles PDFs +
    # PPTX text natively). Only when we have neither do we lean on the
    # extracted text.
    source_for_claude: Path | None = None
    if file_path and file_path.exists() and kind in ("pdf", "pptx", "ppt"):
        source_for_claude = file_path

    from . import claude_runner

    if claude_runner.is_available() and source_for_claude is not None:
        if work_dir is None:
            work_dir = source_for_claude.parent / f"{source_for_claude.stem}__job"
        result = claude_runner.run_summary(
            work_dir=work_dir,
            source_path=source_for_claude,
            hint_title=hint_title,
            schema=SUMMARY_SCHEMA,
            quality_bar=QUALITY_BAR,
            page_count=len(slides) if slides else None,
            progress=progress,
        )
        if "error" not in result:
            # Stamp slide-count metadata for the UI.
            result.setdefault("slide_count", len(slides) or None)
            result.setdefault("slides_used", len(slides) or None)
        return result

    # Fallback: OpenAI direct (kept so the system still works on machines
    # without Claude Code installed).
    if not _is_available():
        return {
            "error": (
                "Neither Claude Code (`claude`) nor OPENAI_API_KEY are "
                "available. Install Claude Code with "
                "`npm install -g @anthropic-ai/claude-code` and authenticate, "
                "or set OPENAI_API_KEY."
            )
        }
    if _has_meaningful_text(slides):
        result = _summarize_text(slides, hint_title=hint_title, progress=progress)
        if "error" not in result:
            result["mode"] = "openai_text"
        return result
    if file_path and kind in ("pdf", "ppt"):
        result = _summarize_pdf_visually(
            file_path,
            slide_count=len(slides),
            hint_title=hint_title,
            progress=progress,
        )
        if "error" not in result:
            result["mode"] = "openai_vision"
        return result
    return {
        "error": (
            "This deck has no extractable text. PDFs can be summarized "
            "visually; for image-only PPTX the deck would need conversion "
            "to PDF first."
        )
    }
