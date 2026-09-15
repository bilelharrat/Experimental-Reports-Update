"""Earnings and SEC filings watch for the public names on the desk.

Sources: SEC EDGAR submissions feed (free, needs a User-Agent) for recent filings,
Nasdaq earnings-surprise for the last report and an estimated next date. Cached on disk;
`fetch` is injectable so the logic is testable without the network.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import desk_store, live_quotes, quote_workspace, storage

def _cache_file() -> Path:
    return storage.DATA_DIR / "cache" / "filings_watch.json"


def _ticker_map_file() -> Path:
    return storage.DATA_DIR / "cache" / "sec_tickers.json"
CACHE_TTL_S = 6 * 3600
TICKER_MAP_TTL_S = 7 * 24 * 3600
WATCH_FORMS = {"8-K", "10-K", "10-Q", "S-1", "S-1/A", "424B4", "SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A", "4", "DEF 14A", "6-K", "20-F"}
LOOKBACK_DAYS = 90
SEC_HEADERS = {"User-Agent": "BSH Research Center research@bsh.local", "Accept-Encoding": "gzip, deflate"}

Fetch = Callable[[str, dict | None], dict]


def _default_fetch(url: str, headers: dict | None = None) -> dict:
    return live_quotes._http_get_json(url, headers or {})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def watched_tickers() -> list[str]:
    tickers: list[str] = []
    for t in desk_store.pinned_tickers():
        if t not in tickers:
            tickers.append(t)
    for company in storage.list_companies():
        t = str(company.get("ticker") or "").strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    return tickers


def _ticker_map(fetch: Fetch) -> dict[str, dict]:
    if _ticker_map_file().exists() and time.time() - _ticker_map_file().stat().st_mtime < TICKER_MAP_TTL_S:
        try:
            return json.loads(_ticker_map_file().read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    raw = fetch("https://www.sec.gov/files/company_tickers.json", SEC_HEADERS) or {}
    out: dict[str, dict] = {}
    for entry in raw.values() if isinstance(raw, dict) else []:
        if isinstance(entry, dict) and entry.get("ticker"):
            out[str(entry["ticker"]).upper()] = {"cik": int(entry.get("cik_str") or 0), "name": entry.get("title")}
    if out:
        _ticker_map_file().parent.mkdir(parents=True, exist_ok=True)
        _ticker_map_file().write_text(json.dumps(out), encoding="utf-8")
    return out


def _recent_filings(cik: int, fetch: Fetch, *, today: date) -> list[dict]:
    raw = fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", SEC_HEADERS) or {}
    recent = ((raw.get("filings") or {}).get("recent") or {}) if isinstance(raw, dict) else {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    descs = recent.get("primaryDocDescription") or []
    cutoff = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    out = []
    for i, form in enumerate(forms):
        filed = dates[i] if i < len(dates) else ""
        if form not in WATCH_FORMS or filed < cutoff:
            continue
        acc = (accessions[i] if i < len(accessions) else "").replace("-", "")
        doc = docs[i] if i < len(docs) else ""
        out.append({
            "form": form,
            "filed": filed,
            "description": descs[i] if i < len(descs) else "",
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}" if acc and doc else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}",
            "material": form.startswith("8-K") or form in {"10-K", "10-Q", "S-1", "424B4"},
        })
    out.sort(key=lambda f: f["filed"], reverse=True)
    return out[:12]


def _earnings(ticker: str, fetch: Fetch) -> dict:
    try:
        raw = fetch(f"https://api.nasdaq.com/api/company/{ticker}/earnings-surprise", live_quotes.NASDAQ_HEADERS)
        return quote_workspace._parse_earnings(raw or {})
    except Exception:  # noqa: BLE001
        return {"next_date": None, "next_estimated": False, "past": []}


def build(*, tickers: list[str] | None = None, fetch: Fetch | None = None, today: date | None = None) -> dict:
    fetch = fetch or _default_fetch
    today = today or date.today()
    tickers = tickers if tickers is not None else watched_tickers()
    names = {str(c.get("ticker") or "").upper(): c for c in storage.list_companies() if c.get("ticker")}
    try:
        cik_map = _ticker_map(fetch)
    except Exception:  # noqa: BLE001
        cik_map = {}
    rows = []
    for ticker in tickers:
        entry = cik_map.get(ticker) or (cik_map.get(ticker.replace(".", "-")) if "." in ticker else None) or {}
        filings: list[dict] = []
        error = None
        if entry.get("cik"):
            try:
                filings = _recent_filings(int(entry["cik"]), fetch, today=today)
            except Exception as exc:  # noqa: BLE001
                error = f"EDGAR unavailable: {exc}"
        else:
            error = "No CIK for ticker (not SEC-registered or ticker map unavailable)"
        earnings = _earnings(ticker, fetch)
        next_date = earnings.get("next_date")
        days_to = None
        if next_date:
            try:
                days_to = (date.fromisoformat(next_date) - today).days
            except ValueError:
                days_to = None
        company = names.get(ticker)
        rows.append({
            "ticker": ticker,
            "company_id": (company or {}).get("id"),
            "company_name": (company or {}).get("name") or entry.get("name"),
            "cik": entry.get("cik"),
            "filings": filings,
            "material_count": sum(1 for f in filings if f["material"]),
            "earnings": {
                "next_date": next_date,
                "next_estimated": bool(earnings.get("next_estimated")),
                "days_to_next": days_to,
                "last_reported": (earnings.get("past") or [{}])[0].get("reported") if earnings.get("past") else None,
                "last_surprise_pct": (earnings.get("past") or [{}])[0].get("surprise_pct") if earnings.get("past") else None,
            },
            "error": error,
        })

    def _sort_key(row: dict) -> tuple:
        days = row["earnings"]["days_to_next"]
        return (0 if row["material_count"] else 1, days if isinstance(days, int) and days >= 0 else 999, row["ticker"])

    rows.sort(key=_sort_key)
    upcoming = [r for r in rows if isinstance(r["earnings"]["days_to_next"], int) and 0 <= r["earnings"]["days_to_next"] <= 14]
    return {
        "generated_at": _now(),
        "as_of_date": today.isoformat(),
        "tickers": rows,
        "upcoming_earnings": [{"ticker": r["ticker"], "date": r["earnings"]["next_date"], "days": r["earnings"]["days_to_next"], "estimated": r["earnings"]["next_estimated"]} for r in upcoming],
        "material_filings": [dict(f, ticker=r["ticker"]) for r in rows for f in r["filings"] if f["material"]][:30],
        "note": "Filings: SEC EDGAR, last 90 days. Next earnings date is Nasdaq's last report + 91 days unless confirmed.",
    }


def get(*, refresh: bool = False, fetch: Fetch | None = None) -> dict:
    if not refresh and _cache_file().exists() and time.time() - _cache_file().stat().st_mtime < CACHE_TTL_S:
        try:
            cached = json.loads(_cache_file().read_text(encoding="utf-8"))
            if set(cached.get("watched") or []) == set(watched_tickers()):
                return cached
        except Exception:  # noqa: BLE001
            pass
    result = build(fetch=fetch)
    result["watched"] = watched_tickers()
    _cache_file().parent.mkdir(parents=True, exist_ok=True)
    _cache_file().write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


__all__ = ["build", "get", "watched_tickers", "Any"]
