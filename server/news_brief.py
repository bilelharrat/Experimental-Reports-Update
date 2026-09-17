"""Expanded briefings for headlines shown in the news tape.

The stored news rows are a headline plus a one-liner — enough for a list
row, too thin to read. This module turns one of those into a desk-grade
briefing: what happened, why it matters, context, and what to watch.

Cost policy (owner, 2026-09-14, after a cloud server burned tokens
prewarming 16 briefings eight at a time on every tape change):

1. Opening a story, or the tape changing, never calls Claude. A story
   without an AI briefing gets a *basic* briefing built without AI: the
   article's lead paragraphs and the sentences that carry figures.
2. AI briefings are written by ONE worker, one headline at a time
   (``_WRITE_LOCK``), through ``ai_engine.structured`` — Gemini Flash with
   a Claude fallback, no tools either way, since the article text is fetched
   here and the model only has to write from it. One call writes English AND
   Chinese. The briefing records which engine wrote it.
3. A server loop writes AI briefings for the top of the tape that clients
   last showed, every ``BSH_NEWS_BRIEF_REFRESH_HOURS`` (default 6). A user
   can start that refresh now, or rewrite one story; the UI warns first.

AI briefings are cached under ``data/news_briefs/<key>-<lang>.json``, basic
briefings under ``<key>-basic.json``, and the recorded tape and refresh
clock under ``_tape.json`` and ``_refresh_state.json``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from server import ai_engine
from server.link_preview import HEADERS, extract_text_from_html

logger = logging.getLogger(__name__)

BRIEFS_ROOT = Path(__file__).resolve().parent.parent / "data" / "news_briefs"

LANGUAGES = ("en", "zh")
MAX_BULLETS = 8
MAX_SOURCES = 8
# One call writes both languages — roughly twice the old single-language
# output — so the wall sits well above the old 90s.
BRIEF_TIMEOUT_SEC = 240
FETCH_TIMEOUT_SEC = 5.0
ARTICLE_MAX_CHARS = 12_000
DEFAULT_MODEL = "sonnet"
DEFAULT_EFFORT = "medium"
# Scheduled refresh: how often, and how many top-of-tape headlines.
REFRESH_INTERVAL_HOURS_DEFAULT = 6.0
REFRESH_LIMIT_DEFAULT = 16
REFRESH_LIMIT_MAX = 24
# How often the loop wakes to check whether a refresh is due.
REFRESH_CHECK_SECONDS = 600
# How soon to retry after a refresh that wrote nothing at all.
FAILED_RETRY_MINUTES = 15
# Basic (no-AI) briefing shape.
BASIC_MAX_PARAGRAPHS = 6
BASIC_MAX_WORDS = 450
BASIC_MIN_PARAGRAPH_CHARS = 80
BASIC_MAX_FIGURES = 5

_LOCK = threading.Lock()
# At most one AI briefing call at a time, process-wide: the scheduled
# refresh, a user-started refresh and a single-story rewrite all queue here.
_WRITE_LOCK = threading.Lock()
_INFLIGHT: set[str] = set()
_INFLIGHT_LOCK = threading.Lock()
_REFRESH_LOCK = threading.Lock()
_REFRESH_IDLE: dict = {
    "running": False,
    "reason": None,
    "total": 0,
    "done": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
}
_REFRESH_STATE: dict = dict(_REFRESH_IDLE)
_PLANNED_KEYS: set[str] = set()
_LOOP_LOCK = threading.Lock()
_LOOP_STARTED = False

SYSTEM_PROMPT = (
    "You are a senior markets analyst writing a long-form briefing for an "
    "investment desk that has already seen the headline. The reader should "
    "finish this and not need the original article.\n"
    "You are given the materials directly — do NOT call tools, search, or "
    "fetch. Write immediately from what is provided.\n"
    "Write the briefing twice in this one response: `en` in English and `zh` "
    "in simplified Chinese. Both carry the same facts and judgments. Write "
    "the Chinese as a native markets writer would, not as a literal "
    "translation of the English, and keep tickers and company names in "
    "their usual form.\n"
    "In each language:\n"
    "- 'what_happened': 5-7 substantial paragraphs (550-850 English words, "
    "the same depth in Chinese). Cover the event, the numbers, who said "
    "what, how it compares to prior periods or expectations, and any "
    "second-order facts the materials support. Do not restate the headline.\n"
    "- 'why_it_matters': 3-4 paragraphs on the investment read: who is "
    "affected (company, competitors, customers, lenders), through which "
    "mechanism (revenue, margin, multiple, regulation, cost of capital), "
    "and on what timeline.\n"
    "- 'context': 5-8 bullets of background a reader needs (prior events, "
    "competitive position, relevant financials, ownership, regulation).\n"
    "- 'watch_next': 4-6 specific, checkable upcoming markers with dates "
    "or windows when the materials give them.\n"
    "- Assert only what the materials support. Where they are thin, say so "
    "plainly instead of padding or guessing.\n"
    "Put the article URL (if any) and any other cited URLs in 'sources' once, "
    "for both languages.\n"
    "No hype, no disclaimers, no greetings, no markdown headers."
)

_LANGUAGE_BRIEF_SCHEMA = {
    "type": "object",
    "required": ["what_happened", "why_it_matters"],
    "properties": {
        "headline": {"type": "string"},
        "what_happened": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "context": {"type": "array", "items": {"type": "string"}},
        "watch_next": {"type": "array", "items": {"type": "string"}},
    },
}

BRIEF_SCHEMA = {
    "type": "object",
    "required": ["en", "zh"],
    "properties": {
        "en": _LANGUAGE_BRIEF_SCHEMA,
        "zh": _LANGUAGE_BRIEF_SCHEMA,
        "confidence": {
            "type": "string",
            "description": "high | medium | low — how well sources supported the story",
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        },
    },
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")
_SENTENCE_END_RE = re.compile(r"[.!?。！？]")
_CJK_RE = re.compile(r"[一-鿿]")
# A sentence "carries a figure" when it has a currency amount, a percentage,
# or a number with a scale word — the numbers a desk reader scans for.
_FIGURE_RE = re.compile(
    r"[$€£¥]\s?\d"
    r"|\d(?:[\d,.]*\d)?\s?(?:%|percent\b|per cent\b|million\b|billion\b"
    r"|trillion\b|bn\b|mn\b|亿|万)",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def normalize_language(lang: str | None) -> str:
    value = str(lang or "en").strip().lower()
    return value if value in LANGUAGES else "en"


def brief_model() -> str:
    """Model for AI briefings (``BSH_NEWS_BRIEF_MODEL``, default Sonnet)."""
    return str(os.environ.get("BSH_NEWS_BRIEF_MODEL") or "").strip() or DEFAULT_MODEL


def brief_effort() -> str:
    """Effort for AI briefings (``BSH_NEWS_BRIEF_EFFORT``, default medium)."""
    return str(os.environ.get("BSH_NEWS_BRIEF_EFFORT") or "").strip() or DEFAULT_EFFORT


def write_on_open() -> bool:
    """Whether opening a story without a briefing writes one now.

    On by default: see ``expand``. ``BSH_NEWS_BRIEF_ON_OPEN=0`` restores the
    old behavior, where only the scheduled refresh and the explicit
    Regenerate button ever call a model.
    """
    raw = str(os.environ.get("BSH_NEWS_BRIEF_ON_OPEN") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def refresh_interval_hours() -> float:
    """Hours between scheduled refreshes (``BSH_NEWS_BRIEF_REFRESH_HOURS``).

    ``0`` turns the schedule off; users can still start a refresh."""
    raw = str(os.environ.get("BSH_NEWS_BRIEF_REFRESH_HOURS") or "").strip()
    if not raw:
        return REFRESH_INTERVAL_HOURS_DEFAULT
    try:
        return max(0.0, float(raw))
    except ValueError:
        return REFRESH_INTERVAL_HOURS_DEFAULT


def refresh_limit(requested: int | None = None) -> int:
    """How many top-of-tape headlines one refresh covers.

    The owner's ``BSH_NEWS_BRIEF_REFRESH_LIMIT`` wins over a client request."""
    value: int = REFRESH_LIMIT_DEFAULT
    raw = str(os.environ.get("BSH_NEWS_BRIEF_REFRESH_LIMIT") or "").strip()
    for candidate in (raw or None, requested):
        if candidate is None:
            continue
        try:
            value = int(candidate)
            break
        except (TypeError, ValueError):
            continue
    return max(1, min(value, REFRESH_LIMIT_MAX))


def brief_key(title: str, company: str | None = None) -> str:
    """Stable cache key for a headline (+ company when the tape has one)."""
    normalized = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if not normalized:
        raise ValueError("title is required")
    seed = f"{normalized}|{(company or '').strip().lower()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _opt_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _brief_row(raw: object) -> dict | None:
    """Normalize one headline (API body, client tape row, or stored tape)."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    company = raw.get("company") or raw.get("company_name")
    return {
        "title": title,
        "summary": _opt_text(raw.get("summary")),
        "source": _opt_text(raw.get("source")),
        "published_at": _opt_text(raw.get("published_at") or raw.get("captured_at")),
        "company": _opt_text(company) if isinstance(company, str) else None,
        "ticker": _opt_text(raw.get("ticker")),
        "url": _opt_text(raw.get("url")),
    }


def _row_key(row: dict) -> str:
    return brief_key(row["title"], row["company"])


def _path_for(key: str, lang: str) -> Path:
    return BRIEFS_ROOT / f"{key}-{lang}.json"


def _basic_path(key: str) -> Path:
    return BRIEFS_ROOT / f"{key}-basic.json"


def _tape_path() -> Path:
    return BRIEFS_ROOT / "_tape.json"


def _state_path() -> Path:
    return BRIEFS_ROOT / "_refresh_state.json"


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unreadable news brief file %s: %s", path.name, exc)
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict) -> None:
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        tmp.replace(path)


def load_brief(key: str, lang: str = "en") -> dict | None:
    """Cached AI briefing, or None when this headline has none yet."""
    return _read_json(_path_for(key, normalize_language(lang)))


def _save_brief(key: str, lang: str, payload: dict) -> None:
    _write_json(_path_for(key, lang), payload)


def _missing_languages(key: str) -> bool:
    return any(not _path_for(key, lang).exists() for lang in LANGUAGES)


def _clean_lines(rows: object) -> list[str]:
    out: list[str] = []
    for row in rows or []:
        text = str(row).strip()
        if text:
            out.append(text)
        if len(out) >= MAX_BULLETS:
            break
    return out


def _clean_sources(rows: object) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        out.append({"title": str(row.get("title") or url).strip(), "url": url})
        if len(out) >= MAX_SOURCES:
            break
    return out


def fetch_article_text(
    url: str | None,
    *,
    timeout_sec: float = FETCH_TIMEOUT_SEC,
    max_chars: int = ARTICLE_MAX_CHARS,
) -> tuple[str, str | None]:
    """Pull readable article text. Never raises.

    Returns ``(text, final_url)``. Empty text means the fetch failed or the
    page had nothing extractable — the writer still runs on the headline.
    """
    clean = str(url or "").strip()
    if not clean.startswith("http"):
        return "", None
    try:
        with httpx.Client(
            timeout=timeout_sec,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            response = client.get(clean)
            response.raise_for_status()
            text = extract_text_from_html(response.text or "")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + "…"
            final = str(response.url) if response.url else clean
            return text, final
    except Exception as exc:
        logger.info("News brief article fetch failed for %s: %s", clean, exc)
        return "", None


def _source_url(url: str | None, final_url: str | None) -> str | None:
    return final_url or (url if str(url or "").startswith("http") else None)


# ---- Basic briefing (no AI) ------------------------------------------------


def lead_paragraphs(
    text: str,
    *,
    max_paragraphs: int = BASIC_MAX_PARAGRAPHS,
    max_words: int = BASIC_MAX_WORDS,
) -> list[str]:
    """The article's opening paragraphs, the way a news lead is written.

    Short lines and lines without sentence punctuation are navigation,
    bylines, captions or headings, so they are skipped."""
    out: list[str] = []
    seen: set[str] = set()
    words = 0
    for line in str(text or "").splitlines():
        block = re.sub(r"\s+", " ", line).strip()
        if len(block) < BASIC_MIN_PARAGRAPH_CHARS or not _SENTENCE_END_RE.search(block):
            continue
        marker = block.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(block)
        words += len(block.split())
        if len(out) >= max_paragraphs or words >= max_words:
            break
    return out


def figure_sentences(text: str, *, limit: int = BASIC_MAX_FIGURES) -> list[str]:
    """Sentences that carry a currency amount, a percentage or a scaled number."""
    out: list[str] = []
    seen: set[str] = set()
    for line in str(text or "").splitlines():
        block = re.sub(r"\s+", " ", line).strip()
        for sentence in _SENTENCE_SPLIT_RE.split(block):
            candidate = sentence.strip()
            # Chinese packs a sentence into far fewer characters.
            shortest = 12 if _CJK_RE.search(candidate) else 30
            if not shortest <= len(candidate) <= 320 or not _FIGURE_RE.search(candidate):
                continue
            marker = candidate.lower()
            if marker in seen:
                continue
            seen.add(marker)
            out.append(candidate)
            if len(out) >= limit:
                return out
    return out


def basic_brief(
    *,
    title: str,
    summary: str | None = None,
    source: str | None = None,
    published_at: str | None = None,
    company: str | None = None,
    ticker: str | None = None,
    url: str | None = None,
    lang: str = "en",
) -> dict:
    """A briefing built without AI, in the article's own language.

    Cached per headline once the article text was fetched; a failed fetch
    is not cached, so the next open tries again."""
    row = _brief_row(
        {
            "title": title,
            "summary": summary,
            "source": source,
            "published_at": published_at,
            "company": company,
            "ticker": ticker,
            "url": url,
        }
    )
    if row is None:
        raise ValueError("title is required")
    language = normalize_language(lang)
    key = _row_key(row)
    cached = _read_json(_basic_path(key))
    if cached is None:
        article_text, final_url = fetch_article_text(row["url"])
        source_url = _source_url(row["url"], final_url)
        paragraphs = lead_paragraphs(article_text)
        cached = {
            "key": key,
            "kind": "basic",
            "generated_at": _iso(),
            "title": row["title"],
            "company": row["company"],
            "ticker": row["ticker"],
            "source": row["source"],
            "published_at": row["published_at"],
            "url": source_url or row["url"],
            "headline": "",
            "what_happened": "\n\n".join(paragraphs) or (row["summary"] or ""),
            "why_it_matters": "",
            "context": [],
            "watch_next": [],
            "key_figures": figure_sentences(article_text),
            "confidence": None,
            "sources": (
                [{"title": row["source"] or "Article", "url": source_url}]
                if source_url
                else []
            ),
            "article_chars": len(article_text),
        }
        if paragraphs:
            _write_json(_basic_path(key), cached)
    payload = dict(cached)
    payload["lang"] = language
    for field in ("headline", "what_happened", "why_it_matters", "context", "watch_next"):
        payload[f"{field}_{language}"] = payload.get(field)
    return payload


# ---- AI briefing (one Sonnet call, both languages) -------------------------


def _prompt(*, row: dict, url: str | None, article_text: str) -> str:
    lines = [f"Headline: {row['title']}"]
    if row["summary"]:
        lines.append(f"Desk one-liner already on file: {row['summary']}")
    if row["company"]:
        ticker = f" ({row['ticker']})" if row["ticker"] else ""
        lines.append(f"Company: {row['company']}{ticker}")
    elif row["ticker"]:
        lines.append(f"Ticker: {row['ticker']}")
    if row["source"]:
        lines.append(f"Attributed source: {row['source']}")
    if row["published_at"]:
        lines.append(f"Reported: {row['published_at']}")
    if url and str(url).startswith("http"):
        lines.append(f"Article URL: {url}")
    lines.append("Write both `en` (English) and `zh` (simplified Chinese).")
    if article_text:
        lines.append(
            "Article text (primary source — write from this; do not invent "
            "facts beyond it):\n---\n"
            f"{article_text}\n---"
        )
        lines.append("Write the long briefing in both languages now.")
    else:
        lines.append(
            "No full article body was available. Write the longest, most "
            "useful briefing you can from the headline, one-liner, and any "
            "metadata above. Mark confidence medium or low. Do not invent "
            "specific figures, quotes, or dates that are not implied."
        )
    return "\n".join(lines)


def _ai_payload(
    *,
    key: str,
    language: str,
    part: dict,
    row: dict,
    source_url: str | None,
    sources: list[dict],
    confidence: str,
    article_chars: int,
    generated_at: str,
    meta: dict | None = None,
) -> dict | None:
    what_happened = str(part.get("what_happened") or "").strip()
    if not what_happened:
        return None
    headline = str(part.get("headline") or "").strip()
    why = str(part.get("why_it_matters") or "").strip()
    context = _clean_lines(part.get("context"))
    watch_next = _clean_lines(part.get("watch_next"))
    return {
        "key": key,
        "lang": language,
        "kind": "ai",
        # The engine that actually wrote it, not the configured preference:
        # a Claude fallback has to be visible on the stored briefing.
        "engine": (meta or {}).get("engine"),
        "model": (meta or {}).get("model") or brief_model(),
        "engine_fallback_reason": (meta or {}).get("fallback_reason"),
        "effort": brief_effort(),
        "generated_at": generated_at,
        "title": row["title"],
        "company": row["company"],
        "ticker": row["ticker"],
        "source": row["source"],
        "published_at": row["published_at"],
        "url": source_url or row["url"],
        "headline": headline,
        "what_happened": what_happened,
        "why_it_matters": why,
        "context": context,
        "watch_next": watch_next,
        "confidence": confidence,
        "sources": sources,
        "article_chars": article_chars,
        # iOS (and older bilingual callers) read language-suffixed keys.
        f"headline_{language}": headline,
        f"what_happened_{language}": what_happened,
        f"why_it_matters_{language}": why,
        f"context_{language}": context,
        f"watch_next_{language}": watch_next,
    }


def _notify(title: str, body: str, data: dict) -> None:
    try:
        from server import push_notify

        push_notify.notify("brief", title, body, data=data)
    except Exception:  # noqa: BLE001
        logger.debug("brief push notify skipped", exc_info=True)


def write_brief(
    *,
    title: str,
    summary: str | None = None,
    source: str | None = None,
    published_at: str | None = None,
    company: str | None = None,
    ticker: str | None = None,
    url: str | None = None,
    notify: bool = False,
) -> dict[str, dict]:
    """Write the AI briefing for one headline in BOTH languages.

    One Claude call (Sonnet, medium effort, no tools) writes English and
    Chinese; each language is cached. Calls are serialized process-wide,
    so at most one briefing call runs at a time. Returns ``{lang: payload}``
    and raises ``RuntimeError`` when the call fails or returns no body.
    """
    row = _brief_row(
        {
            "title": title,
            "summary": summary,
            "source": source,
            "published_at": published_at,
            "company": company,
            "ticker": ticker,
            "url": url,
        }
    )
    if row is None:
        raise ValueError("title is required")
    key = _row_key(row)
    with _WRITE_LOCK:
        with _INFLIGHT_LOCK:
            _INFLIGHT.add(key)
        try:
            written = _write_brief_locked(key, row)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(key)
    if notify:
        _notify("Briefing ready", row["title"][:120], {"key": key})
    return written


def _write_brief_locked(key: str, row: dict) -> dict[str, dict]:
    article_text, final_url = fetch_article_text(row["url"])
    source_url = _source_url(row["url"], final_url)
    data, meta, err = ai_engine.structured(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_prompt(row=row, url=source_url, article_text=article_text),
        schema=BRIEF_SCHEMA,
        name="news_brief",
        timeout_sec=BRIEF_TIMEOUT_SEC,
        claude_model=brief_model(),
        claude_effort=brief_effort(),
    )
    if err is not None or not isinstance(data, dict):
        raise RuntimeError(err or "Empty briefing response")

    sources = _clean_sources(data.get("sources"))
    if source_url and not any(item.get("url") == source_url for item in sources):
        sources.insert(0, {"title": row["source"] or "Article", "url": source_url})
        sources = sources[:MAX_SOURCES]
    confidence = str(data.get("confidence") or "").strip().lower()
    if not confidence:
        confidence = "high" if article_text else "medium"

    generated_at = _iso()
    written: dict[str, dict] = {}
    for language in LANGUAGES:
        part = data.get(language)
        if not isinstance(part, dict):
            continue
        payload = _ai_payload(
            key=key,
            language=language,
            part=part,
            row=row,
            source_url=source_url,
            sources=sources,
            confidence=confidence,
            article_chars=len(article_text),
            generated_at=generated_at,
            meta=meta,
        )
        if payload is None:
            continue
        _save_brief(key, language, payload)
        written[language] = payload
    if not written:
        raise RuntimeError("Briefing came back without a body")
    return written


def expand(
    *,
    title: str,
    summary: str | None = None,
    source: str | None = None,
    published_at: str | None = None,
    company: str | None = None,
    ticker: str | None = None,
    url: str | None = None,
    lang: str = "en",
    refresh: bool = False,
) -> dict:
    """The briefing to show for a headline.

    ``refresh=True`` is the explicit, warned user action: one call rewrites
    both languages and the requested one comes back.

    ``refresh=False`` (opening a story) returns the cached AI briefing when
    one exists. When none exists it writes one, unless
    ``BSH_NEWS_BRIEF_ON_OPEN=0``, in which case it returns the no-AI basic
    briefing as before.

    Writing on open is a deliberate reversal of the original cost policy,
    which was written when every briefing was a Claude CLI subprocess. The
    news tape is live and rotates constantly, while the scheduled refresh
    runs every six hours — so the newest story, which is the one the reader
    actually opens, essentially never had a briefing, and the desk showed
    "No AI briefing yet" more or less permanently. A batch on a six-hour
    clock cannot cover a feed that turns over in minutes.

    The guards that made the old policy necessary all stay: one worker at a
    time (``_WRITE_LOCK``), results cached per headline so a second reader
    pays nothing, and a failure falls back to the basic briefing rather than
    erroring. Raises ``ValueError`` for an empty headline; a model failure
    on open degrades instead of raising.
    """
    row = _brief_row(
        {
            "title": title,
            "summary": summary,
            "source": source,
            "published_at": published_at,
            "company": company,
            "ticker": ticker,
            "url": url,
        }
    )
    if row is None:
        raise ValueError("title is required")
    language = normalize_language(lang)
    if refresh:
        written = write_brief(**row, notify=True)
        return written.get(language) or next(iter(written.values()))
    cached = load_brief(_row_key(row), language)
    if cached is not None:
        return cached
    if write_on_open() and ai_engine.available():
        try:
            written = write_brief(**row)
            found = written.get(language) or next(iter(written.values()), None)
            if found is not None:
                return found
        except Exception as exc:  # noqa: BLE001 — a briefing is never worth a 500
            logger.warning("news brief on-open write failed: %s", exc)
    return basic_brief(**row, lang=language)


# ---- Tape and scheduled refresh ---------------------------------------------


def record_tape(items: list[dict]) -> list[dict]:
    """Remember the top headlines a client is showing (never calls Claude)."""
    rows: list[dict] = []
    seen: set[str] = set()
    for raw in items or []:
        row = _brief_row(raw)
        if row is None:
            continue
        key = _row_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= REFRESH_LIMIT_MAX:
            break
    if rows:
        _write_json(_tape_path(), {"updated_at": _iso(), "items": rows})
    return rows


def load_tape() -> list[dict]:
    data = _read_json(_tape_path()) or {}
    return [row for row in (_brief_row(raw) for raw in data.get("items") or []) if row]


def prewarm(
    items: list[dict],
    *,
    lang: str = "en",
    limit: int = REFRESH_LIMIT_DEFAULT,
) -> dict:
    """Record the tape a client is showing. Never calls Claude.

    Web and iOS still call this whenever their headlines change. The server
    only remembers the list, so the scheduled refresh knows what to brief.
    ``limit`` is accepted for older clients and ignored.
    """
    rows = record_tape(items)
    language = normalize_language(lang)
    ready = sum(1 for row in rows if load_brief(_row_key(row), language) is not None)
    due = next_refresh_at()
    return {
        "lang": language,
        "recorded": len(rows),
        "ready": ready,
        "queued": 0,
        "started": False,
        "ai": False,
        "next_refresh_at": _iso(due) if due else None,
    }


def plan_refresh(limit: int | None = None) -> list[dict]:
    """Top-of-tape headlines still missing an AI briefing in either language."""
    return [
        row
        for row in load_tape()[: refresh_limit(limit)]
        if _missing_languages(_row_key(row))
    ]


def _mark_refreshed(at: datetime | None = None) -> None:
    _write_json(_state_path(), {"last_refresh_at": _iso(at)})


def _mark_refresh_failed() -> None:
    """Back the clock off to a short retry instead of a full interval.

    A run that wrote nothing has not refreshed anything, and must not buy
    itself the full ``BSH_NEWS_BRIEF_REFRESH_HOURS`` of silence: that is how
    a single bad window (an expired key, a model outage) leaves every story
    showing "No AI briefing yet" for six hours with nothing retrying. The
    clock is set so the next attempt is ``FAILED_RETRY_MINUTES`` away rather
    than reset — still backed off enough not to hammer a broken model.
    """
    interval = timedelta(hours=refresh_interval_hours())
    retry_in = min(timedelta(minutes=FAILED_RETRY_MINUTES), interval)
    _mark_refreshed(_now() - interval + retry_in)


def last_refresh_at() -> datetime | None:
    raw = str((_read_json(_state_path()) or {}).get("last_refresh_at") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def next_refresh_at() -> datetime | None:
    """When the schedule next writes briefings; None when it is off."""
    hours = refresh_interval_hours()
    if hours <= 0:
        return None
    last = last_refresh_at()
    return _now() if last is None else last + timedelta(hours=hours)


def seconds_until_due() -> float | None:
    due = next_refresh_at()
    return None if due is None else (due - _now()).total_seconds()


def refresh_status() -> dict:
    """Schedule and progress for the News page and the API."""
    with _REFRESH_LOCK:
        state = dict(_REFRESH_STATE)
    last = last_refresh_at()
    due = next_refresh_at()
    return {
        **state,
        "last_refresh_at": _iso(last) if last else None,
        "next_refresh_at": _iso(due) if due else None,
        "interval_hours": refresh_interval_hours(),
        "limit": refresh_limit(),
        "model": brief_model(),
        "effort": brief_effort(),
        "tape_count": len(load_tape()),
        "pending": len(plan_refresh()),
    }


def start_refresh(
    *,
    items: list[dict] | None = None,
    reason: str = "manual",
    limit: int | None = None,
    background: bool = True,
) -> dict:
    """Write AI briefings for top-of-tape headlines that lack one.

    One worker, one headline at a time. ``items`` (what the user is looking
    at) replaces the recorded tape first. A refresh already running is left
    alone. Starting a refresh restarts the schedule clock.
    """
    if items:
        record_tape(items)
    plan = plan_refresh(limit)
    tape_known = bool(load_tape())
    with _REFRESH_LOCK:
        busy = bool(_REFRESH_STATE["running"])
        if not busy and plan:
            _REFRESH_STATE.clear()
            _REFRESH_STATE.update(_REFRESH_IDLE)
            _REFRESH_STATE.update(
                running=True, reason=reason, total=len(plan), started_at=_iso()
            )
            _PLANNED_KEYS.clear()
            _PLANNED_KEYS.update(_row_key(row) for row in plan)
    if busy:
        return {**refresh_status(), "started": False, "note": "already_running"}
    if not plan:
        if tape_known:
            _mark_refreshed()
        return {
            **refresh_status(),
            "started": False,
            "planned": 0,
            "note": "nothing_to_write" if tape_known else "no_headlines",
        }
    if background:
        threading.Thread(
            target=_run_refresh,
            args=(plan,),
            name="news-brief-refresh",
            daemon=True,
        ).start()
    else:
        _run_refresh(plan)
    return {**refresh_status(), "started": True, "planned": len(plan)}


def _run_refresh(plan: list[dict]) -> None:
    written = 0
    try:
        for row in plan:
            key = _row_key(row)
            try:
                # A single-story rewrite may have landed since planning.
                if _missing_languages(key):
                    write_brief(**row)
                    written += 1
                with _REFRESH_LOCK:
                    _REFRESH_STATE["done"] += 1
            except Exception as exc:  # noqa: BLE001 — one story never stops the batch
                logger.warning("news brief refresh item failed: %s", exc)
                with _REFRESH_LOCK:
                    _REFRESH_STATE["failed"] += 1
                    _REFRESH_STATE["last_error"] = str(exc)[:300]
            finally:
                with _REFRESH_LOCK:
                    _PLANNED_KEYS.discard(key)
    finally:
        with _REFRESH_LOCK:
            _REFRESH_STATE["running"] = False
            _REFRESH_STATE["finished_at"] = _iso()
            _PLANNED_KEYS.clear()
        # The schedule clock is set here, from the outcome — a run that wrote
        # nothing gets a short retry instead of the full interval.
        if written:
            _mark_refreshed()
        else:
            _mark_refresh_failed()
    if written:
        _notify("AI briefs ready", f"{written} headline briefs refreshed", {"count": written})


def _refresh_loop() -> None:
    while True:
        wait: float | None = None
        try:
            wait = seconds_until_due()
            if wait is not None and wait <= 0:
                start_refresh(reason="scheduled", background=False)
                wait = seconds_until_due()
        except Exception:  # noqa: BLE001
            logger.exception("news brief scheduled refresh failed")
        if wait is None or wait <= 0:
            # Schedule off, nothing recorded yet, or an error: check again later.
            time.sleep(REFRESH_CHECK_SECONDS)
        else:
            time.sleep(max(30.0, min(float(REFRESH_CHECK_SECONDS), wait)))


def start_refresh_loop() -> bool:
    """Start the scheduled refresh (FastAPI startup hook). Idempotent.

    Off when ``BSH_NEWS_BRIEF_REFRESH_HOURS=0`` or no engine can run. This
    asks ``ai_engine``, not the Claude CLI: with a Gemini key and no CLI
    installed the loop must still start.
    A server that never refreshed is due at once, but writes nothing until
    a client has recorded the tape."""
    global _LOOP_STARTED
    if refresh_interval_hours() <= 0 or not ai_engine.available():
        return False
    with _LOOP_LOCK:
        if _LOOP_STARTED:
            return False
        _LOOP_STARTED = True
    threading.Thread(
        target=_refresh_loop, name="news-brief-refresh-loop", daemon=True
    ).start()
    return True


def brief_statuses(
    items: list[dict],
    *,
    lang: str = "en",
) -> dict:
    """Which headlines already have a cached AI briefing (for client poll/UI)."""
    language = normalize_language(lang)
    with _INFLIGHT_LOCK:
        writing = set(_INFLIGHT)
    with _REFRESH_LOCK:
        planned = set(_PLANNED_KEYS)
    rows: list[dict] = []
    for raw in items or []:
        row = _brief_row(raw)
        if row is None:
            continue
        key = _row_key(row)
        rows.append(
            {
                "key": key,
                "title": row["title"],
                "company": row["company"],
                "ready": load_brief(key, language) is not None,
                "generating": key in writing or key in planned,
            }
        )
    return {
        "lang": language,
        "items": rows,
        "ready": sum(1 for row in rows if row["ready"]),
        "generating": sum(1 for row in rows if row["generating"]),
    }


def reset_state_for_tests() -> None:
    """Clear refresh progress and in-flight markers between unit tests."""
    with _REFRESH_LOCK:
        _REFRESH_STATE.clear()
        _REFRESH_STATE.update(_REFRESH_IDLE)
        _PLANNED_KEYS.clear()
    with _INFLIGHT_LOCK:
        _INFLIGHT.clear()
