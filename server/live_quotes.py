"""Live last-print quotes for public tickers.

Trader snapshots are Claude-scraped and often missing. Tracking needs a
cheap, refreshable last price + 1-day move for every listed name. CNBC's
public quote service is the primary batch source; Yahoo spark and Nasdaq
fill leftovers. Failed or invented symbols are omitted and briefly
remembered so demo tickers do not hammer the providers.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

CNBC_URL = (
    "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
)
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

QUOTE_TTL_SECONDS = 45
NEGATIVE_TTL_SECONDS = 120
MAX_TICKERS = 40
HTTP_TIMEOUT = 8.0
NASDAQ_WORKERS = 4

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
OFFSET_RE = re.compile(r"([+-])(\d{2})(\d{2})$")

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict]] = {}
_NEGATIVE: dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    stamp = value or _now()
    return stamp.isoformat().replace("+00:00", "Z")


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    raw = raw.replace("+", "")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_as_of(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    match = OFFSET_RE.search(raw)
    if match and ":" not in raw[-5:]:
        raw = OFFSET_RE.sub(r"\1\2:\3", raw)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _iso(parsed.astimezone(timezone.utc))


def normalize_tickers(values: list[str] | None) -> list[str]:
    """Uppercase, de-dupe, drop junk. Caps at ``MAX_TICKERS``."""
    seen: list[str] = []
    for value in values or []:
        for part in str(value or "").split(","):
            ticker = part.strip().upper()
            if not ticker or ticker in seen or not TICKER_RE.match(ticker):
                continue
            seen.append(ticker)
            if len(seen) >= MAX_TICKERS:
                return seen
    return seen


def _http_get(url: str, extra_headers: dict | None = None) -> str:
    headers = {**HTTP_HEADERS, **(extra_headers or {})}
    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _http_get_json(url: str, extra_headers: dict | None = None) -> dict:
    payload = json.loads(_http_get(url, extra_headers))
    if not isinstance(payload, dict):
        raise ValueError("quote payload was not an object")
    return payload


def _quote(
    ticker: str,
    last: float | None,
    change: float | None,
    *,
    currency: str,
    as_of: str | None,
    source: str,
) -> dict | None:
    if last is None and change is None:
        return None
    return {
        "ticker": ticker,
        "last_price": last,
        "change_pct_1d": change,
        "currency": currency,
        "as_of": as_of,
        "source": source,
    }


def _cnbc_url(tickers: list[str]) -> str:
    symbols = "|".join(tickers)
    return (
        f"{CNBC_URL}?symbols={quote(symbols, safe='|')}"
        "&requestMethod=itv&noform=1&partnerId=2&fund=1"
    )


def _parse_cnbc(payload: dict) -> dict[str, dict]:
    wrapper = payload.get("FormattedQuoteResult")
    if not isinstance(wrapper, dict):
        return {}
    rows = wrapper.get("FormattedQuote") or []
    if isinstance(rows, dict):
        rows = [rows]
    found: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            code_raw = row.get("code")
            code = int(code_raw) if code_raw is not None else 1
        except (TypeError, ValueError):
            code = 1
        if code != 0:
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        parsed = _quote(
            ticker,
            _as_float(row.get("last")),
            _as_float(row.get("change_pct")),
            currency=str(row.get("currencyCode") or row.get("currency") or "USD"),
            as_of=_parse_as_of(row.get("last_time") or row.get("last_timedate")),
            source="cnbc",
        )
        if ticker and parsed:
            found[ticker] = parsed
    return found


def _spark_url(tickers: list[str]) -> str:
    symbols = ",".join(tickers)
    return (
        f"{YAHOO_SPARK_URL}?symbols={quote(symbols, safe=',')}"
        "&range=1d&interval=1d"
    )


def _quote_from_meta(ticker: str, meta: dict | None) -> dict | None:
    if not isinstance(meta, dict):
        return None
    last = _as_float(
        meta.get("regularMarketPrice")
        if meta.get("regularMarketPrice") is not None
        else meta.get("regularMarketPreviousClose")
    )
    previous = _as_float(
        meta.get("chartPreviousClose")
        if meta.get("chartPreviousClose") is not None
        else meta.get("previousClose")
    )
    change = None
    if last is not None and previous not in (None, 0):
        change = ((last - previous) / previous) * 100
    as_of = None
    market_time = meta.get("regularMarketTime")
    if isinstance(market_time, (int, float)) and market_time > 0:
        as_of = _iso(datetime.fromtimestamp(market_time, tz=timezone.utc))
    return _quote(
        ticker,
        last,
        change,
        currency=str(meta.get("currency") or "USD"),
        as_of=as_of,
        source="yahoo",
    )


def _parse_spark(payload: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    spark = payload.get("spark")
    if not isinstance(spark, dict):
        return rows
    for item in spark.get("result") or []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("symbol") or "").strip().upper()
        responses = item.get("response") or []
        meta = (
            responses[0].get("meta")
            if responses and isinstance(responses[0], dict)
            else None
        )
        parsed = _quote_from_meta(ticker, meta)
        if ticker and parsed:
            rows[ticker] = parsed
    return rows


def _parse_nasdaq(ticker: str, payload: dict) -> dict | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    primary = data.get("primaryData")
    if not isinstance(primary, dict):
        return None
    return _quote(
        ticker,
        _as_float(primary.get("lastSalePrice")),
        _as_float(primary.get("percentageChange")),
        currency="USD",
        as_of=_parse_as_of(primary.get("lastTradeTimestamp")),
        source="nasdaq",
    )


def _fetch_nasdaq_one(ticker: str) -> dict | None:
    url = NASDAQ_URL.format(symbol=quote(ticker, safe=""))
    headers = {
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    try:
        return _parse_nasdaq(ticker, _http_get_json(url, headers))
    except Exception as exc:
        logger.warning("Nasdaq quote fetch failed for %s: %s", ticker, exc)
        return None


def _fetch_nasdaq(tickers: list[str]) -> dict[str, dict]:
    if not tickers:
        return {}
    found: dict[str, dict] = {}
    workers = min(NASDAQ_WORKERS, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_nasdaq_one, ticker): ticker for ticker in tickers
        }
        for future in as_completed(futures):
            parsed = future.result()
            if parsed:
                found[str(parsed["ticker"])] = parsed
    return found


def _fetch_missing(tickers: list[str]) -> dict[str, dict]:
    if not tickers:
        return {}
    found: dict[str, dict] = {}
    cnbc_ok = False

    try:
        found.update(_parse_cnbc(_http_get_json(_cnbc_url(tickers))))
        cnbc_ok = True
    except Exception as exc:
        logger.warning("CNBC quote fetch failed: %s", exc)

    leftover = [ticker for ticker in tickers if ticker not in found]
    # A successful CNBC batch already told us the leftovers are unknown
    # symbols. Do not fan those out to Yahoo/Nasdaq — that is how we
    # earned a 429 on invented demo tickers.
    if leftover and not cnbc_ok:
        try:
            found.update(_parse_spark(_http_get_json(_spark_url(leftover))))
        except Exception as exc:
            logger.warning("Yahoo spark quote fetch failed: %s", exc)
        leftover = [ticker for ticker in tickers if ticker not in found]
        if leftover:
            found.update(_fetch_nasdaq(leftover))
    return found


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
        _NEGATIVE.clear()


def fetch_quotes(tickers: list[str] | None) -> dict:
    """Return last price + 1-day move for the requested tickers.

    Unknown or failed symbols are omitted rather than raising — one bad
    ticker must not blank the tape.
    """
    wanted = normalize_tickers(tickers)
    now = time.monotonic()
    quotes: dict[str, dict] = {}
    missing: list[str] = []

    with _CACHE_LOCK:
        for ticker in wanted:
            cached = _CACHE.get(ticker)
            if cached and cached[0] > now:
                quotes[ticker] = cached[1]
                continue
            negative = _NEGATIVE.get(ticker)
            if negative and negative > now:
                continue
            missing.append(ticker)

    fresh = _fetch_missing(missing)
    expires = time.monotonic() + QUOTE_TTL_SECONDS
    negative_until = time.monotonic() + NEGATIVE_TTL_SECONDS
    with _CACHE_LOCK:
        for ticker, parsed in fresh.items():
            _CACHE[ticker] = (expires, parsed)
            _NEGATIVE.pop(ticker, None)
            quotes[ticker] = parsed
        for ticker in missing:
            if ticker not in fresh:
                _NEGATIVE[ticker] = negative_until

    return {
        "generated_at": _iso(),
        "quotes": quotes,
        "missing": [ticker for ticker in wanted if ticker not in quotes],
    }
