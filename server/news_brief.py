"""Expanded briefings for headlines shown in the news tape.

The stored news rows are a headline plus a one-liner — enough for a list
row, too thin to read. This module turns one of those into a desk-grade
briefing: what happened, why it matters, context, and what to watch.

Speed path (same quality, lower wall clock):
1. Prefetch the article URL ourselves with a hard 5s HTTP budget
   (``link_preview`` text extract) — no Claude tool loop.
2. Write the briefing with ``run_structured_prompt`` (no WebSearch /
   WebFetch). Tool-using research was the multi-minute bottleneck.
3. Prewarm the top of the tape on a shared ThreadPoolExecutor so many
   headlines expand concurrently (default 8 workers) instead of one-by-one.

One language per call, cached under ``data/news_briefs/<key>-<lang>.json``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from server import claude_runner
from server.link_preview import HEADERS, extract_text_from_html

logger = logging.getLogger(__name__)

BRIEFS_ROOT = Path(__file__).resolve().parent.parent / "data" / "news_briefs"

LANGUAGES = ("en", "zh")
MAX_BULLETS = 8
MAX_SOURCES = 8
# Long desk briefings (multi-paragraph what_happened) routinely need
# 40–80s on Claude Code. The old 25s wall returned
# "claude timed out after 25s (news_brief)" on almost every first write.
BRIEF_TIMEOUT_SEC = 90
FETCH_TIMEOUT_SEC = 5.0
ARTICLE_MAX_CHARS = 12_000
# Prefetch the top of the tape so opening a story is usually a cache hit.
PREWARM_DEFAULT_LIMIT = 16
PREWARM_MAX_LIMIT = 24
# Concurrent Claude writes for prewarm. Override with BSH_NEWS_BRIEF_WORKERS.
PREWARM_WORKERS = 8
PREWARM_MAX_WORKERS = 8

_LOCK = threading.Lock()
_INFLIGHT: set[str] = set()
_INFLIGHT_LOCK = threading.Lock()
_PREWARM_LOCK = threading.Lock()
_PREWARM_POOL: ThreadPoolExecutor | None = None
# Keys (key:lang) submitted to the shared pool and not yet finished.
_PREWARM_SUBMITTED: set[str] = set()

_LANGUAGE_RULE = {
    "en": "Write every field in English.",
    "zh": (
        "Write every field in simplified Chinese, as a native markets "
        "writer would — not a literal translation of English phrasing. "
        "Keep tickers and company names in their usual form."
    ),
}

SYSTEM_PROMPT = (
    "You are a senior markets analyst writing a long-form briefing for an "
    "investment desk that has already seen the headline. The reader should "
    "finish this and not need the original article.\n"
    "You are given the materials directly — do NOT call tools, search, or "
    "fetch. Write immediately from what is provided.\n"
    "- 'what_happened': 5-7 substantial paragraphs (550-850 words). Cover "
    "the event, the numbers, who said what, how it compares to prior "
    "periods or expectations, and any second-order facts the materials "
    "support. Do not restate the headline.\n"
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
    "- Put the article URL (if any) and any other cited URLs in 'sources'.\n"
    "- No hype, no disclaimers, no greetings, no markdown headers."
)

BRIEF_SCHEMA = {
    "type": "object",
    "required": ["what_happened", "why_it_matters"],
    "properties": {
        "headline": {"type": "string"},
        "what_happened": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "context": {"type": "array", "items": {"type": "string"}},
        "watch_next": {"type": "array", "items": {"type": "string"}},
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def normalize_language(lang: str | None) -> str:
    value = str(lang or "en").strip().lower()
    return value if value in LANGUAGES else "en"


def brief_key(title: str, company: str | None = None) -> str:
    """Stable cache key for a headline (+ company when the tape has one)."""
    normalized = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if not normalized:
        raise ValueError("title is required")
    seed = f"{normalized}|{(company or '').strip().lower()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _path_for(key: str, lang: str) -> Path:
    return BRIEFS_ROOT / f"{key}-{lang}.json"


def load_brief(key: str, lang: str = "en") -> dict | None:
    """Cached briefing, or None when this headline was never expanded."""
    path = _path_for(key, normalize_language(lang))
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Unreadable news brief %s: %s", path.name, exc)
        return None


def _save_brief(key: str, lang: str, payload: dict) -> None:
    with _LOCK:
        BRIEFS_ROOT.mkdir(parents=True, exist_ok=True)
        target = _path_for(key, lang)
        tmp = target.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        tmp.replace(target)


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
    """Pull readable article text for the model. Never raises.

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


def _prompt(
    *,
    title: str,
    summary: str | None,
    source: str | None,
    published_at: str | None,
    company: str | None,
    ticker: str | None,
    url: str | None,
    article_text: str,
    lang: str,
) -> str:
    lines = [f"Headline: {title}"]
    if summary:
        lines.append(f"Desk one-liner already on file: {summary}")
    if company:
        lines.append(f"Company: {company}" + (f" ({ticker})" if ticker else ""))
    elif ticker:
        lines.append(f"Ticker: {ticker}")
    if source:
        lines.append(f"Attributed source: {source}")
    if published_at:
        lines.append(f"Reported: {published_at}")
    if url and str(url).startswith("http"):
        lines.append(f"Article URL: {url}")
    lines.append(_LANGUAGE_RULE[lang])
    if article_text:
        lines.append(
            "Article text (primary source — write from this; do not invent "
            "facts beyond it):\n---\n"
            f"{article_text}\n---"
        )
        lines.append("Write the long briefing now.")
    else:
        lines.append(
            "No full article body was available. Write the longest, most "
            "useful briefing you can from the headline, one-liner, and any "
            "metadata above. Mark confidence medium or low. Do not invent "
            "specific figures, quotes, or dates that are not implied."
        )
    return "\n".join(lines)


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
    """Return the long briefing for a headline, generating it when needed.

    Cached briefings come back immediately unless ``refresh`` is set.
    Raises ``ValueError`` for an empty headline and ``RuntimeError`` when
    the model call fails, so the API layer can pick status codes.
    """
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    language = normalize_language(lang)

    key = brief_key(clean_title, company)
    if not refresh:
        cached = load_brief(key, language)
        if cached is not None:
            return cached

    inflight_key = f"{key}:{language}"
    with _INFLIGHT_LOCK:
        already = inflight_key in _INFLIGHT
        if not already:
            _INFLIGHT.add(inflight_key)
    if already:
        # Another worker is writing this brief — wait briefly for the cache.
        for _ in range(40):
            time.sleep(1.5)
            cached = load_brief(key, language)
            if cached is not None:
                return cached
        raise RuntimeError("Briefing still generating; try again in a moment")

    try:
        return _expand_uncached(
            key=key,
            clean_title=clean_title,
            summary=summary,
            source=source,
            published_at=published_at,
            company=company,
            ticker=ticker,
            url=url,
            language=language,
        )
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.discard(inflight_key)


def _expand_uncached(
    *,
    key: str,
    clean_title: str,
    summary: str | None,
    source: str | None,
    published_at: str | None,
    company: str | None,
    ticker: str | None,
    url: str | None,
    language: str,
) -> dict:
    article_text, final_url = fetch_article_text(url)
    source_url = final_url or (url if str(url or "").startswith("http") else None)

    data, err = claude_runner.run_structured_prompt(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_prompt(
            title=clean_title,
            summary=summary,
            source=source,
            published_at=published_at,
            company=company,
            ticker=ticker,
            url=source_url,
            article_text=article_text,
            lang=language,
        ),
        schema=BRIEF_SCHEMA,
        name="news_brief",
        timeout_sec=BRIEF_TIMEOUT_SEC,
    )
    if err is not None or not isinstance(data, dict):
        raise RuntimeError(err or "Empty briefing response")

    what_happened = str(data.get("what_happened") or "").strip()
    if not what_happened:
        raise RuntimeError("Briefing came back without a body")

    headline = str(data.get("headline") or "").strip()
    why = str(data.get("why_it_matters") or "").strip()
    context = _clean_lines(data.get("context"))
    watch_next = _clean_lines(data.get("watch_next"))
    sources = _clean_sources(data.get("sources"))
    if source_url and not any(row.get("url") == source_url for row in sources):
        sources.insert(
            0,
            {
                "title": source or "Article",
                "url": source_url,
            },
        )
        sources = sources[:MAX_SOURCES]

    confidence = str(data.get("confidence") or "").strip().lower() or None
    if not confidence:
        confidence = "high" if article_text else "medium"

    payload = {
        "key": key,
        "lang": language,
        "generated_at": _iso(),
        "title": clean_title,
        "company": company,
        "ticker": ticker,
        "source": source,
        "published_at": published_at,
        "url": source_url or url,
        "headline": headline,
        "what_happened": what_happened,
        "why_it_matters": why,
        "context": context,
        "watch_next": watch_next,
        "confidence": confidence,
        "sources": sources,
        "article_chars": len(article_text),
        # iOS (and older bilingual callers) read language-suffixed keys.
        f"headline_{language}": headline,
        f"what_happened_{language}": what_happened,
        f"why_it_matters_{language}": why,
        f"context_{language}": context,
        f"watch_next_{language}": watch_next,
    }
    _save_brief(key, language, payload)
    try:
        from server import push_notify

        push_notify.notify(
            "brief",
            "Briefing ready",
            clean_title[:120],
            data={"key": key, "lang": language},
        )
    except Exception:
        logger.debug("brief push notify skipped", exc_info=True)
    return payload


def _configured_workers(requested: int | None = None) -> int:
    """Resolve prewarm concurrency (env override, then arg, then default)."""
    env_raw = str(os.environ.get("BSH_NEWS_BRIEF_WORKERS") or "").strip()
    if env_raw:
        try:
            return max(1, min(int(env_raw), PREWARM_MAX_WORKERS))
        except ValueError:
            pass
    if requested is not None:
        try:
            return max(1, min(int(requested), PREWARM_MAX_WORKERS))
        except (TypeError, ValueError):
            pass
    return max(1, min(PREWARM_WORKERS, PREWARM_MAX_WORKERS))


def _prewarm_pool() -> ThreadPoolExecutor:
    """Lazy shared pool so successive prewarm calls enqueue onto one runner."""
    global _PREWARM_POOL
    with _PREWARM_LOCK:
        if _PREWARM_POOL is None:
            _PREWARM_POOL = ThreadPoolExecutor(
                max_workers=_configured_workers(),
                thread_name_prefix="news-brief",
            )
        return _PREWARM_POOL


def reset_prewarm_state_for_tests() -> None:
    """Drop the shared pool / queue markers between unit tests."""
    global _PREWARM_POOL
    with _PREWARM_LOCK:
        pool, _PREWARM_POOL = _PREWARM_POOL, None
        _PREWARM_SUBMITTED.clear()
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _plan_prewarm_items(
    items: list[dict],
    *,
    language: str,
    limit: int,
) -> tuple[list[dict], dict]:
    """Pick uncached headlines to expand; skip duplicates / in-flight / junk."""
    capped = max(1, min(int(limit or PREWARM_DEFAULT_LIMIT), PREWARM_MAX_LIMIT))
    planned: list[dict] = []
    seen_keys: set[str] = set()
    skipped_cached = 0
    skipped_inflight = 0
    skipped_queued = 0
    skipped_invalid = 0
    for raw in items or []:
        if len(planned) >= capped:
            break
        if not isinstance(raw, dict):
            skipped_invalid += 1
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            skipped_invalid += 1
            continue
        company = raw.get("company") or raw.get("company_name")
        try:
            key = brief_key(title, company if isinstance(company, str) else None)
        except ValueError:
            skipped_invalid += 1
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if load_brief(key, language) is not None:
            skipped_cached += 1
            continue
        inflight_key = f"{key}:{language}"
        with _INFLIGHT_LOCK:
            writing = inflight_key in _INFLIGHT
        with _PREWARM_LOCK:
            queued = inflight_key in _PREWARM_SUBMITTED
        if writing:
            skipped_inflight += 1
            continue
        if queued:
            skipped_queued += 1
            continue
        planned.append(
            {
                "title": title,
                "summary": raw.get("summary"),
                "source": raw.get("source"),
                "published_at": raw.get("published_at") or raw.get("captured_at"),
                "company": company if isinstance(company, str) else None,
                "ticker": raw.get("ticker"),
                "url": raw.get("url"),
                "lang": language,
                "_inflight_key": inflight_key,
            }
        )
    counts = {
        "skipped_cached": skipped_cached,
        "skipped_inflight": skipped_inflight,
        "skipped_queued": skipped_queued,
        "skipped_invalid": skipped_invalid,
    }
    return planned, counts


def _submit_prewarm_row(row: dict, pool: ThreadPoolExecutor) -> bool:
    """Enqueue one expand on the shared pool. Returns False if already queued."""
    inflight_key = str(row.pop("_inflight_key", "") or "")
    if not inflight_key:
        title = str(row.get("title") or "")
        company = row.get("company")
        try:
            inflight_key = (
                f"{brief_key(title, company if isinstance(company, str) else None)}"
                f":{normalize_language(row.get('lang'))}"
            )
        except ValueError:
            return False

    with _PREWARM_LOCK:
        if inflight_key in _PREWARM_SUBMITTED:
            return False
        _PREWARM_SUBMITTED.add(inflight_key)

    def _done(fut: Future) -> None:
        with _PREWARM_LOCK:
            _PREWARM_SUBMITTED.discard(inflight_key)
        try:
            fut.result()
        except Exception as exc:  # noqa: BLE001
            logger.warning("news brief prewarm item failed: %s", exc)

    pool.submit(expand, **row, refresh=False).add_done_callback(_done)
    return True


def brief_statuses(
    items: list[dict],
    *,
    lang: str = "en",
) -> dict:
    """Which headlines already have a cached briefing (for client poll/UI)."""
    language = normalize_language(lang)
    rows: list[dict] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        company = raw.get("company") or raw.get("company_name")
        company_s = company if isinstance(company, str) else None
        try:
            key = brief_key(title, company_s)
        except ValueError:
            continue
        inflight_key = f"{key}:{language}"
        cached = load_brief(key, language) is not None
        with _INFLIGHT_LOCK:
            writing = inflight_key in _INFLIGHT
        with _PREWARM_LOCK:
            queued = inflight_key in _PREWARM_SUBMITTED
        rows.append(
            {
                "key": key,
                "title": title,
                "company": company_s,
                "ready": cached,
                "generating": writing or queued,
            }
        )
    return {
        "lang": language,
        "items": rows,
        "ready": sum(1 for row in rows if row["ready"]),
        "generating": sum(1 for row in rows if row["generating"]),
    }


def prewarm(
    items: list[dict],
    *,
    lang: str = "en",
    limit: int = PREWARM_DEFAULT_LIMIT,
    workers: int | None = None,
    background: bool = True,
) -> dict:
    """Generate missing briefings for the top of the tape in parallel.

    Skips headlines that are already cached, writing, or already queued on
    the shared pool. Successive calls **enqueue** onto the same pool (they
    do not drop work because a prior batch is still running).

    By default returns immediately after submitting to the background pool
    so the News tab can keep scrolling while Claude works. Pass
    ``background=False`` to run inline (tests).
    """
    language = normalize_language(lang)
    worker_n = _configured_workers(workers)
    planned, counts = _plan_prewarm_items(
        items, language=language, limit=limit
    )

    summary = {
        "lang": language,
        "queued": 0,
        "skipped_cached": counts["skipped_cached"],
        "skipped_inflight": counts["skipped_inflight"],
        "skipped_queued": counts["skipped_queued"],
        "skipped_invalid": counts["skipped_invalid"],
        "workers": worker_n,
        "started": False,
        "parallel": True,
    }
    if not planned:
        return summary

    if not background:
        # Inline path for tests: still parallel across planned rows.
        with ThreadPoolExecutor(
            max_workers=min(worker_n, len(planned)),
            thread_name_prefix="news-brief-test",
        ) as pool:
            futures = [pool.submit(expand, **{
                k: v for k, v in row.items() if k != "_inflight_key"
            }, refresh=False) for row in planned]
            for fut in futures:
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("news brief prewarm item failed: %s", exc)
        summary["queued"] = len(planned)
        summary["started"] = True
        return summary

    pool = _prewarm_pool()
    submitted = 0
    for row in planned:
        if _submit_prewarm_row(row, pool):
            submitted += 1
    summary["queued"] = submitted
    summary["started"] = submitted > 0
    if submitted and submitted < len(planned):
        summary["note"] = "some items were already queued on the shared pool"
    return summary
