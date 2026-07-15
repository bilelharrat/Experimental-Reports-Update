"""High-fidelity PDF translation for external research items.

Wraps claude_runner.run_pdf_translation: loads the source PDF, counts
pages with pypdf, hands off to Claude Code (which Reads the PDF directly,
translates page by page, writes a structured JSON), then persists the
result onto the external_research record so subsequent loads are instant.
"""
from __future__ import annotations

import json
import logging
import threading
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
    cancel_event: threading.Event | None = None,
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
        cancel_event=cancel_event,
    )

    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "error": "user_cancelled"}

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


# ---------------------------------------------------------------------------
# External-archive news translation (Phase 4.7)
# ---------------------------------------------------------------------------
#
# ``recent_news`` on company records carries translations (company_translate),
# but external-archive news items had no zh source at all. Translate their
# title/summary once per item, cache in the ``news_translate`` cache
# namespace, and let context_store.company_news overlay it when lang=zh.
# Translation runs on a background thread so the feed request never blocks
# on a Claude call — the first zh view shows English, the next shows Chinese.

NEWS_TRANSLATION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
    },
    "required": ["title", "summary"],
}

_NEWS_SYSTEM_PROMPT = (
    "You translate investment-research news snippets into Simplified Chinese "
    "for institutional readers. Formal written Chinese, Chinese punctuation, "
    "keep company names, tickers, currency amounts, and standard acronyms in "
    "Latin form. Return null for any field that is empty in the source. Do "
    "not add commentary."
)

# Item ids already attempted this process lifetime — prevents a failing
# item from spawning a translation attempt on every poll.
_news_attempted: set[str] = set()
_news_attempted_lock = threading.Lock()


def cached_news_translation(item_id: str) -> dict | None:
    """Return ``{title, summary}`` (zh) for this news item if cached."""
    from . import cache

    entry = cache.get("news_translate", item_id)
    if entry and isinstance(entry.get("value"), dict):
        return entry["value"]
    return None


def _translate_news_item_now(item_id: str) -> None:
    from . import cache

    item = external_store.get_item("news", item_id)
    if item is None:
        return
    source = {
        "title": item.get("title") or None,
        "summary": item.get("summary") or None,
    }
    if not source["title"] and not source["summary"]:
        return
    data, err = claude_runner.run_structured_prompt(
        system_prompt=_NEWS_SYSTEM_PROMPT,
        user_prompt=(
            "Translate the following news snippet fields to Simplified "
            "Chinese (JSON):\n"
            + json.dumps(source, ensure_ascii=False, indent=2)
        ),
        schema=NEWS_TRANSLATION_SCHEMA,
        name="news_translation",
        timeout_sec=120,
    )
    if err is not None or not isinstance(data, dict):
        logger.debug("news translation for %s failed: %s", item_id, err)
        return
    cache.put("news_translate", item_id, data)


def ensure_news_translation(item_id: str) -> dict | None:
    """Return the cached zh translation, kicking off a background
    translation on the first miss. Never blocks the request path."""
    cached = cached_news_translation(item_id)
    if cached is not None:
        return cached
    if not claude_runner.is_available():
        return None
    with _news_attempted_lock:
        if item_id in _news_attempted:
            return None
        _news_attempted.add(item_id)
    threading.Thread(
        target=_translate_news_item_now,
        args=(item_id,),
        name=f"news-translate-{item_id}",
        daemon=True,
    ).start()
    return None
