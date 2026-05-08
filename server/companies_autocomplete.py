"""Fast company autocomplete.

Sources, in order of priority:

1. Local YAML — already-tracked companies always rank first.
2. SEC EDGAR ticker index — single ~1MB JSON of every US-listed company,
   refreshed daily. No rate limits, no auth, fully local matching after the
   first download. https://www.sec.gov/files/company_tickers.json

For private or non-US companies the user can fall back to deep search.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

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
        }
        for _, row in scored[:limit]
    ]


def autocomplete(query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip()
    if not q or len(q) < 2:
        return []

    seen: set[str] = set()
    results: list[dict] = []

    for c in storage.search_companies(q, limit=limit):
        ticker = (c.get("ticker") or "").upper()
        seen.add(f"local:{c.get('id')}")
        if ticker:
            seen.add(f"ticker:{ticker}")
        results.append(
            {
                "source": "local",
                "id": c.get("id"),
                "ticker": c.get("ticker"),
                "name": c.get("name"),
                "sector": c.get("sector"),
                "description": c.get("description"),
            }
        )

    if len(results) >= limit:
        return results[:limit]

    for hit in _edgar_search(q, limit=limit):
        key = f"ticker:{hit['ticker']}"
        if key in seen:
            continue
        seen.add(key)
        results.append(hit)
        if len(results) >= limit:
            break

    return results[:limit]
