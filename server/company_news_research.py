"""Company news sweep — pull recent news for one company off the live web.

The company news feed (``context_store.company_news``) is an assembler: it
merges ``company_news`` and ``recent_news`` off the company record with the
external news archive. Nothing in that path fetches anything, so the feed
was only ever as fresh as the last full company deep search.

This module is the refresh for it. One web-grounded Gemini Flash pass
(Claude fallback via ``ai_engine``) looks for what has happened to the
company recently and merges the results into ``recent_news``, which the
feed already reads.

Merge rules, in order of what they protect:

- **Existing rows are never edited or dropped.** Whatever is on the record
  was either curated by the desk or written by an earlier pass; a sweep only
  appends what is genuinely new, matched on URL first and normalized
  headline second.
- **Rows without a date or headline are dropped**, and a date that is not
  ``YYYY-MM-DD`` is discarded rather than stored — the feed sorts on that
  field, so a malformed one silently reorders the desk's news.
- **A changed list invalidates ``translation.recent_news``.** That cache is
  aligned to ``recent_news`` *by index* (see
  ``context_store._translated_recent_news``), so appending rows without
  clearing it would caption new English headlines with unrelated Chinese.
  Dropping it degrades the zh view to English until the next translation
  pass, which is the honest failure.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import ai_engine, context_store, storage

logger = logging.getLogger(__name__)

SWEEP_TIMEOUT_SEC = 240
# Same reasoning as the founder dossier: this runs from a button, so the
# Claude fallback gets a UI-shaped cap rather than ai_engine's 15-minute
# batch default.
FALLBACK_TIMEOUT_SEC = 300
MAX_NEW_ROWS = 20
MAX_STORED_ROWS = 60
CATEGORIES = ("fundraising", "product", "filing", "partnership", "leadership", "risk", "press")

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRACKING_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid")

NEWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "Recent developments, newest first. Omit anything you cannot source.",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {
                        "type": "string",
                        "description": "What happened, as a headline. Not a topic label.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Two or three sentences: what happened and why the desk should care.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Publication date as YYYY-MM-DD. Omit the item if you cannot date it.",
                    },
                    "url": {"type": "string", "description": "Direct link to the article."},
                    "source": {
                        "type": "string",
                        "description": "Publication name, e.g. 'Reuters', 'TechCrunch'.",
                    },
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                },
                "required": ["headline", "date"],
            },
        },
        "notes": {
            "type": "string",
            "description": "Anything notable about coverage — a quiet period, conflicting reports, a name collision.",
        },
    },
    "required": ["items"],
}

SWEEP_SYSTEM_PROMPT = """You are a research analyst sweeping recent news about
one company for an investment desk.

Rules you do not break:
- Search the web and report only developments you can point to a published
  article for. Every item needs a real URL and a real publication date.
- Never invent a headline, a date, a funding number or a customer name. An
  item you cannot date or link is left out — a short list is correct, a
  padded one is a defect.
- Watch for name collisions: companies share names. If the sources you find
  are about a different company with the same name, return no items for it
  and say so in `notes`.
- Report the development, not the coverage of it. Three articles about one
  funding round are one item.
- Order newest first. Prefer the original report over an aggregator.
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _canonical_url(value: Any) -> str:
    """Normalize a URL for dedupe: scheme/host lowercased, tracking params cut."""
    raw = _text(value, limit=600)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower()
    if not parts.netloc:
        return raw.lower()
    query = "&".join(
        piece
        for piece in parts.query.split("&")
        if piece and piece.split("=", 1)[0].lower() not in _TRACKING_PARAMS
    )
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def _headline_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _row_keys(row: dict) -> tuple[str, str]:
    url = _canonical_url(row.get("url") or row.get("source_url"))
    headline = _headline_key(row.get("headline") or row.get("title"))
    return url, headline


def _clean_item(item: Any) -> dict | None:
    """One researched item as a ``recent_news`` row, or None if unusable."""
    if not isinstance(item, dict):
        return None
    headline = _text(item.get("headline") or item.get("title"), limit=240)
    date = _text(item.get("date") or item.get("published_at"), limit=10)
    if not headline or not _ISO_DATE_RE.match(date):
        return None
    row: dict[str, Any] = {"headline": headline, "date": date}
    summary = _text(item.get("summary"), limit=900)
    if summary:
        row["summary"] = summary
    url = _text(item.get("url"), limit=600)
    if url.startswith(("http://", "https://")):
        row["url"] = url
    source = _text(item.get("source"), limit=160)
    if source:
        row["source"] = source
    category = _text(item.get("category"), limit=40).lower()
    if category in CATEGORIES:
        row["category"] = category
    row["origin"] = "news_sweep"
    return row


def _merge_rows(existing: list, researched: list[dict]) -> tuple[list, list[dict]]:
    """Append genuinely new rows to ``existing``. Returns ``(merged, added)``."""
    seen_urls: set[str] = set()
    seen_headlines: set[str] = set()
    for row in existing:
        if not isinstance(row, dict):
            continue
        url, headline = _row_keys(row)
        if url:
            seen_urls.add(url)
        if headline:
            seen_headlines.add(headline)

    added: list[dict] = []
    for row in researched:
        url, headline = _row_keys(row)
        if (url and url in seen_urls) or (headline and headline in seen_headlines):
            continue
        if url:
            seen_urls.add(url)
        if headline:
            seen_headlines.add(headline)
        added.append(row)
        if len(added) >= MAX_NEW_ROWS:
            break

    merged = list(existing) + added
    # Newest first, undated rows last. The feed sorts again on its own, but
    # the stored list is read directly elsewhere (memo prep, translation).
    merged.sort(key=lambda row: str((row or {}).get("date") or ""), reverse=True)
    return merged[:MAX_STORED_ROWS], added


def _sweep_prompt(company: dict, *, existing: list) -> str:
    name = company.get("name") or company.get("id")
    lines = [f"Company: {name}"]
    for label, key in (
        ("Website", "website"),
        ("Headquarters", "hq"),
        ("Sector", "sector"),
        ("Stage", "stage"),
    ):
        value = _text(company.get(key), limit=200)
        if value:
            lines.append(f"{label}: {value}")
    description = _text(
        company.get("description") or company.get("one_liner") or company.get("positioning"),
        limit=600,
    )
    if description:
        lines.append(f"What the desk has on file: {description}")
        lines.append(
            "Use that description to confirm you are reading about this "
            "company and not another one with the same name."
        )

    known = [
        f"- {_text(row.get('headline') or row.get('title'), limit=180)} ({_text(row.get('date'), limit=10)})"
        for row in existing[:15]
        if isinstance(row, dict) and (row.get("headline") or row.get("title"))
    ]
    if known:
        lines.append("")
        lines.append("Already on the desk's feed — do not return these again:")
        lines.extend(known)
        lines.append("")
        lines.append("Return only developments the list above is missing.")
    else:
        lines.append("")
        lines.append(
            "The desk has no news on file. Return the most significant recent "
            "developments, newest first."
        )
    return "\n".join(lines)


def sweep_company_news(company_id: str, *, lang: str | None = None) -> dict:
    """Refresh one company's news feed from the live web.

    Returns the feed payload ``context_store.company_news`` would return,
    plus a ``sweep`` block recording what the pass did — the engine that ran
    it, the sources it read, how many items were added, and any error.

    Never raises for a model failure: a failed sweep returns the current feed
    with ``sweep.error`` set, so the feed degrades to what it had.
    """
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")

    existing = [row for row in (company.get("recent_news") or []) if isinstance(row, dict)]
    data, meta, error = ai_engine.grounded(
        system_prompt=SWEEP_SYSTEM_PROMPT,
        user_prompt=_sweep_prompt(company, existing=existing),
        schema=NEWS_SCHEMA,
        name="company_news_sweep",
        gemini_timeout_sec=SWEEP_TIMEOUT_SEC,
        claude_timeout_sec=FALLBACK_TIMEOUT_SEC,
    )

    sweep: dict[str, Any] = {
        "searched_at": _now_iso(),
        "engine": meta.get("engine"),
        "model": meta.get("model"),
        "sources": meta.get("sources") or [],
        "added": 0,
        "error": None,
        "notes": None,
    }

    if error is not None or not isinstance(data, dict):
        logger.warning("company_news_research: sweep failed for %s — %s", company_id, error)
        sweep["error"] = error or "News sweep returned nothing"
        feed = context_store.company_news(company_id, lang=lang)
        feed["sweep"] = sweep
        return feed

    researched = [row for row in (_clean_item(item) for item in data.get("items") or []) if row]
    merged, added = _merge_rows(existing, researched)
    sweep["added"] = len(added)
    sweep["notes"] = _text(data.get("notes"), limit=1200) or None

    if added:
        patch: dict[str, Any] = {"recent_news": merged, "news_sweep": sweep}
        # The zh cache is index-aligned to recent_news; a changed list makes
        # it wrong, so it goes rather than mis-captioning the new rows.
        translation = company.get("translation")
        if isinstance(translation, dict) and translation.get("recent_news"):
            trimmed = dict(translation)
            trimmed.pop("recent_news", None)
            patch["translation"] = trimmed
        storage.update_company(company_id, **patch)
    else:
        storage.update_company(company_id, news_sweep=sweep)

    feed = context_store.company_news(company_id, lang=lang)
    feed["sweep"] = sweep
    return feed
