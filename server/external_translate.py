"""High-fidelity PDF translation for external research items.

Wraps claude_runner.run_pdf_translation: loads the source PDF, counts
pages with pypdf, hands off to Claude Code (which Reads the PDF directly,
translates page by page, writes a structured JSON), then persists the
result onto the external_research record so subsequent loads are instant.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import claude_runner, external_store

logger = logging.getLogger(__name__)


def _page_count(pdf_path: Path) -> int | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:  # noqa: BLE001
        return None


def translate_research_pdf(
    item_id: str,
    *,
    app_language: str | None = None,
    progress=None,
) -> dict:
    """Translate the PDF attached to this external_research item via Claude
    Code, persist the result, and return ``{ok: True, translation: ...}``
    on success or ``{ok: False, error: "..."}`` on failure.

    The translation is stored on the item record under ``pdf_translation``
    (separate from the existing ``translation`` field that text_analysis
    populates with summary/key_points). Calling this again with a new
    ``app_language`` overwrites the cached translation.
    """
    item = external_store.get_item("external_research", item_id)
    if item is None:
        return {"ok": False, "error": "Research item not found"}
    stored = item.get("stored_name")
    if not stored:
        return {"ok": False, "error": "Item has no attached file"}
    if (item.get("content_type") or "").lower() != "application/pdf" and not str(
        stored
    ).lower().endswith(".pdf"):
        return {
            "ok": False,
            "error": "Only PDF files are supported for high-fidelity translation",
        }

    pdf_path = (
        external_store._kind_dir("external_research") / "files" / stored
    )
    if not pdf_path.exists():
        return {"ok": False, "error": "Source PDF missing on disk"}

    work_dir = (
        external_store._kind_dir("external_research")
        / "translations"
        / item_id
    )

    pages = _page_count(pdf_path)
    if progress and pages:
        progress.emit(
            "stage",
            stage="counting",
            message=f"PDF has {pages} pages",
            page_count=pages,
        )

    result = claude_runner.run_pdf_translation(
        pdf_path=pdf_path,
        work_dir=work_dir,
        page_count=pages,
        app_language=app_language,
        progress=progress,
    )

    if "error" in result:
        return {"ok": False, "error": result["error"]}

    detected = result.get("detected_language")
    target = result.get("target_language")

    # Persist onto the research record so reloads don't re-translate.
    external_store.update_item(
        "external_research",
        item_id,
        pdf_translation={
            "detected_language": detected,
            "target_language": target,
            "page_count": result.get("page_count"),
            "pages": result.get("pages") or [],
            "claude_cost_usd": result.get("claude_cost_usd"),
            "claude_duration_ms": result.get("claude_duration_ms"),
        },
        # Keep the top-level `language` in sync with what Claude detected.
        language=detected or item.get("language"),
    )

    return {
        "ok": True,
        "translation": external_store.get_item("external_research", item_id).get(
            "pdf_translation"
        ),
        "detected_language": detected,
        "target_language": target,
    }
