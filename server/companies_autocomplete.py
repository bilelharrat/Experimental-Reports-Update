"""Fast company autocomplete.

Sources, in order of priority:

1. Local YAML — already-tracked companies always rank first.
2. Past AI-search results — every company that has ever appeared in a
   cached deep-search result (e.g. Anduril after the user searched for it)
   is surfaced even if it was missing from the local YAML.
3. SEC EDGAR ticker index — single ~1MB JSON of every US-listed company,
   refreshed daily. No rate limits, no auth, fully local matching after the
   first download. https://www.sec.gov/files/company_tickers.json

For private or non-US companies the user can fall back to deep search.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

import httpx
import yaml

from . import storage

logger = logging.getLogger(__name__)

EDGAR_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_HEADERS = {
    # SEC requires a descriptive User-Agent identifying the requester.
    "User-Agent": "BSH Research Center research@bsh.example",
    "Accept": "application/json",
}
EDGAR_TTL = 24 * 60 * 60

_INDEX_LOCK = threading.RLock()
_INDEX: list[dict] | None = None
_INDEX_LOADED_AT: float = 0.0


def _load_edgar_index() -> list[dict]:
    """Fetch the SEC ticker index and normalize to a flat list of dicts."""
    global _INDEX, _INDEX_LOADED_AT
    with _INDEX_LOCK:
        if _INDEX is not None and (time.time() - _INDEX_LOADED_AT) < EDGAR_TTL:
            return _INDEX
        try:
            with httpx.Client(timeout=8.0, headers=EDGAR_HEADERS) as client:
                r = client.get(EDGAR_URL)
                r.raise_for_status()
                data = r.json()
        except Exception as exc:
            logger.warning("SEC EDGAR ticker fetch failed: %s", exc)
            if _INDEX is not None:
                return _INDEX  # serve stale rather than fail
            _INDEX = []
            _INDEX_LOADED_AT = time.time()
            return _INDEX

        rows: list[dict] = []
        # File shape: { "0": {cik_str, ticker, title}, "1": {...}, ... }
        for v in data.values():
            ticker = (v.get("ticker") or "").strip()
            title = (v.get("title") or "").strip()
            if not ticker or not title:
                continue
            rows.append(
                {
                    "ticker": ticker.upper(),
                    "name": title,
                    "name_lower": title.lower(),
                    "ticker_lower": ticker.lower(),
                    "cik": v.get("cik_str"),
                }
            )
        _INDEX = rows
        _INDEX_LOADED_AT = time.time()
        logger.info("Loaded SEC EDGAR ticker index: %d entries", len(rows))
        return _INDEX


def _edgar_search(q: str, limit: int) -> list[dict]:
    index = _load_edgar_index()
    if not index:
        return []
    ql = q.lower()
    scored: list[tuple[int, dict]] = []
    for row in index:
        ticker_l = row["ticker_lower"]
        name_l = row["name_lower"]
        score = 0
        if ticker_l == ql:
            score = 100
        elif name_l == ql:
            score = 95
        elif ticker_l.startswith(ql):
            score = 80
        elif name_l.startswith(ql):
            score = 70
        elif ql in name_l:
            score = 40
        if score:
            scored.append((score, row))
    scored.sort(key=lambda t: (-t[0], len(t[1]["name"]), t[1]["name_lower"]))
    return [
        {
            "source": "edgar",
            "ticker": row["ticker"],
            "name": row["name"].title() if row["name"].isupper() else row["name"],
            "exchange": None,
            "status": "public",
            "company_type": "public",
        }
        for _, row in scored[:limit]
    ]


_RESEARCHED_LOCK = threading.RLock()
_RESEARCHED_CACHE: list[dict] | None = None
_RESEARCHED_AT: float = 0.0
RESEARCHED_TTL = 30


def _researched_dir() -> Path:
    return storage.DATA_DIR / "cache" / "companies_ai"


def _load_researched() -> list[dict]:
    """Walk the deep-search cache and collect every company we've ever seen.

    Cache files were written by `cache.put('companies_ai', q, value)` where
    `value` is the list of upserted matches. We iterate them, dedupe by
    company id (or by name+ticker if id is missing), and produce a flat list
    suitable for prefix-match scoring.
    """
    global _RESEARCHED_CACHE, _RESEARCHED_AT
    with _RESEARCHED_LOCK:
        now = time.time()
        if _RESEARCHED_CACHE is not None and (now - _RESEARCHED_AT) < RESEARCHED_TTL:
            return _RESEARCHED_CACHE
        seen: dict[str, dict] = {}
        cache_dir = _researched_dir()
        if cache_dir.exists():
            for path in cache_dir.glob("*.yaml"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        entry = yaml.safe_load(f) or {}
                except Exception:
                    continue
                value = entry.get("value")
                if not isinstance(value, list):
                    continue
                for c in value:
                    if not isinstance(c, dict):
                        continue
                    key = (
                        c.get("id")
                        or f"{(c.get('ticker') or '').upper()}::{(c.get('name') or '').lower()}"
                    )
                    if not key or key in seen:
                        continue
                    seen[key] = {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "ticker": c.get("ticker"),
                        "description": c.get("description"),
                        "sector": c.get("sector"),
                        "industry": c.get("industry"),
                        "exchange": c.get("exchange"),
                        "status": c.get("status"),
                        "company_type": c.get("company_type"),
                    }
        _RESEARCHED_CACHE = list(seen.values())
        _RESEARCHED_AT = now
        return _RESEARCHED_CACHE


def invalidate_researched_cache() -> None:
    """Force the next autocomplete call to re-scan the cache directory."""
    global _RESEARCHED_CACHE, _RESEARCHED_AT
    with _RESEARCHED_LOCK:
        _RESEARCHED_CACHE = None
        _RESEARCHED_AT = 0.0


def _researched_search(q: str, limit: int) -> list[dict]:
    ql = q.lower()
    scored: list[tuple[int, dict]] = []
    for c in _load_researched():
        name_l = (c.get("name") or "").lower()
        ticker_l = (c.get("ticker") or "").lower()
        if not name_l and not ticker_l:
            continue
        score = 0
        if ticker_l == ql or name_l == ql:
            score = 100
        elif ticker_l and ticker_l.startswith(ql):
            score = 85
        elif name_l.startswith(ql):
            score = 75
        elif ql in name_l:
            score = 45
        if score:
            scored.append((score, c))
    scored.sort(key=lambda t: (-t[0], len(t[1].get("name") or ""), (t[1].get("name") or "").lower()))
    out: list[dict] = []
    for _, c in scored[:limit]:
        out.append(
            {
                "source": "researched",
                "id": c.get("id"),
                "name": c.get("name"),
                "ticker": c.get("ticker"),
                "sector": c.get("sector"),
                "industry": c.get("industry"),
                "exchange": c.get("exchange"),
                "description": c.get("description"),
                "status": c.get("status"),
                "company_type": c.get("company_type"),
            }
        )
    return out


_SUFFIX_RE = re.compile(
    r"[,\.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|"
    r"plc|holdings|holding|sa|nv|ag|gmbh|kk)\.?$",
    re.IGNORECASE,
)


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    n = name.strip().lower()
    # Strip punctuation that the model adds inconsistently.
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Strip a single trailing legal suffix (we re-run on the stripped name in
    # case the original had multiple — "Foo Inc Holdings").
    while True:
        stripped = _SUFFIX_RE.sub("", n).strip()
        if stripped == n:
            break
        n = stripped
    return n


def _seen_keys(*, id_: str | None, ticker: str | None, name: str | None) -> list[str]:
    keys: list[str] = []
    if id_:
        keys.append(f"id:{id_}")
    t = (ticker or "").strip().upper()
    if t:
        keys.append(f"ticker:{t}")
    norm = _normalize_name(name)
    if norm:
        keys.append(f"name:{norm}")
    return keys


def autocomplete(query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip()
    if not q or len(q) < 2:
        return []

    seen: set[str] = set()
    results: list[dict] = []

    def add(hit: dict) -> bool:
        keys = _seen_keys(
            id_=hit.get("id"), ticker=hit.get("ticker"), name=hit.get("name")
        )
        if any(k in seen for k in keys):
            return False
        for k in keys:
            seen.add(k)
        results.append(hit)
        return True

    for c in storage.search_companies(q, limit=limit):
        add(
            {
                "source": "local",
                "id": c.get("id"),
                "ticker": c.get("ticker"),
                "name": c.get("name"),
                "sector": c.get("sector"),
                "description": c.get("description"),
                "status": c.get("status"),
                "company_type": c.get("company_type"),
            }
        )

    if len(results) >= limit:
        return results[:limit]

    for hit in _researched_search(q, limit=limit):
        if add(hit) and len(results) >= limit:
            break

    if len(results) >= limit:
        return results[:limit]

    for hit in _edgar_search(q, limit=limit):
        if add(hit) and len(results) >= limit:
            break

    return results[:limit]
