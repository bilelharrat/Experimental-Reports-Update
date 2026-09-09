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
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

CNBC_URL = (
    "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
)
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks"
NASDAQ_CHART_URL = (
    "https://api.nasdaq.com/api/quote/{symbol}/chart?assetclass={asset}"
)
NASDAQ_HIST_URL = (
    "https://api.nasdaq.com/api/quote/{symbol}/historical"
    "?assetclass={asset}&fromdate={start}&todate={end}&limit={limit}"
)
NASDAQ_SEARCH_URL = "https://api.nasdaq.com/api/autocomplete/slookup/10"
NASDAQ_HEADERS = {
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
NASDAQ_ETF_TICKERS = {
    "SPY",
    "QQQ",
    "DIA",
    "IWM",
    "EFA",
    "EEM",
    "GLD",
    "USO",
    "TLT",
}

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
    **extra: Any,
) -> dict | None:
    if last is None and change is None:
        return None
    row = {
        "ticker": ticker,
        "last_price": last,
        "change_pct_1d": change,
        "currency": currency,
        "as_of": as_of,
        "source": source,
    }
    for key, value in extra.items():
        if value is not None:
            row[key] = value
    return row


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
            name=str(row.get("name") or "").strip() or None,
            exchange=str(row.get("exchange") or "").strip() or None,
            open=_as_float(row.get("open")),
            high=_as_float(row.get("high") or row.get("day_high")),
            low=_as_float(row.get("low") or row.get("day_low")),
            previous_close=_as_float(
                row.get("previous_day_closing") or row.get("previousClose"),
            ),
            volume=_as_float(row.get("volume")),
            market_cap=_as_float(row.get("mktcapView") or row.get("market_cap")),
            fifty_two_week_high=_as_float(
                row.get("year_high_price") or row.get("yrhig"),
            ),
            fifty_two_week_low=_as_float(
                row.get("year_low_price") or row.get("yrlow"),
            ),
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
    try:
        return _parse_nasdaq(ticker, _http_get_json(url, NASDAQ_HEADERS))
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
        _CHART_CACHE.clear()
        _SEARCH_CACHE.clear()


def cache_stats() -> dict:
    """Introspection for /diagnostics/quotes: what's cached, what's failing.

    Ages are derived from the monotonic expiry stamps, so ``age_seconds``
    is time since the entry was cached (TTL minus time-to-expiry). The
    negative cache lists symbols whose providers recently failed — the
    usual smoking gun when the desk shows "Waiting" everywhere.
    """
    now = time.monotonic()
    with _CACHE_LOCK:
        quotes = [
            {
                "ticker": ticker,
                "age_seconds": round(max(QUOTE_TTL_SECONDS - (expiry - now), 0), 1),
                "as_of": payload.get("as_of"),
                "source": payload.get("source"),
            }
            for ticker, (expiry, payload) in sorted(_CACHE.items())
            if expiry > now
        ]
        negative = [
            {
                "ticker": ticker,
                "retry_in_seconds": round(max(until - now, 0), 1),
            }
            for ticker, until in sorted(_NEGATIVE.items())
            if until > now
        ]
        charts = sum(1 for expiry, _ in _CHART_CACHE.values() if expiry > now)
        searches = sum(1 for expiry, _ in _SEARCH_CACHE.values() if expiry > now)
    return {
        "generated_at": _iso(),
        "quote_ttl_seconds": QUOTE_TTL_SECONDS,
        "cached_quotes": quotes,
        "failed_tickers": negative,
        "chart_cache_entries": charts,
        "search_cache_entries": searches,
    }


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


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"

CHART_RANGES: dict[str, tuple[str, str]] = {
    "1d": ("1d", "5m"),
    "5d": ("5d", "15m"),
    "1mo": ("1mo", "1d"),
    "6mo": ("6mo", "1d"),
    "ytd": ("ytd", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
    "max": ("max", "1mo"),
}

CHART_TTL_SECONDS = 60
SEARCH_TTL_SECONDS = 60
SEARCH_QUOTE_TYPES = {"EQUITY", "ETF", "INDEX", "MUTUALFUND", "CRYPTOCURRENCY"}
_CHART_CACHE: dict[str, tuple[float, dict]] = {}
_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}


def _chart_cache_key(ticker: str, span: str) -> str:
    return f"{ticker}:{span}"


def _yahoo_chart_url(ticker: str, span: str, interval: str) -> str:
    return (
        f"{YAHOO_CHART_URL.format(symbol=quote(ticker, safe=''))}"
        f"?range={quote(span, safe='')}&interval={quote(interval, safe='')}"
        "&includePrePost=false&events=div%7Csplit"
    )


def _yahoo_quote_url(ticker: str) -> str:
    return f"{YAHOO_QUOTE_URL}?symbols={quote(ticker, safe='')}"


def _parse_yahoo_quote(payload: dict) -> dict:
    wrapper = payload.get("quoteResponse")
    if not isinstance(wrapper, dict):
        return {}
    rows = wrapper.get("result") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    row = rows[0]
    last = _as_float(row.get("regularMarketPrice"))
    previous = _as_float(row.get("regularMarketPreviousClose"))
    change_pct = _as_float(row.get("regularMarketChangePercent"))
    if change_pct is None and last is not None and previous not in (None, 0):
        change_pct = ((last - previous) / previous) * 100
    change = _as_float(row.get("regularMarketChange"))
    if change is None and last is not None and previous is not None:
        change = last - previous
    as_of = None
    market_time = row.get("regularMarketTime")
    if isinstance(market_time, (int, float)) and market_time > 0:
        as_of = _iso(datetime.fromtimestamp(market_time, tz=timezone.utc))
    name = (
        str(row.get("shortName") or row.get("longName") or "").strip() or None
    )
    return {
        "ticker": str(row.get("symbol") or "").strip().upper(),
        "name": name,
        "exchange": str(row.get("fullExchangeName") or row.get("exchange") or "").strip()
        or None,
        "currency": str(row.get("currency") or "USD"),
        "last_price": last,
        "change": change,
        "change_pct_1d": change_pct,
        "previous_close": previous,
        "open": _as_float(row.get("regularMarketOpen")),
        "high": _as_float(row.get("regularMarketDayHigh")),
        "low": _as_float(row.get("regularMarketDayLow")),
        "volume": _as_float(row.get("regularMarketVolume")),
        "avg_volume": _as_float(row.get("averageDailyVolume3Month")),
        "market_cap": _as_float(row.get("marketCap")),
        "pe_ratio": _as_float(row.get("trailingPE")),
        "eps": _as_float(row.get("epsTrailingTwelveMonths")),
        "beta": _as_float(row.get("beta")),
        "dividend_yield": _as_float(row.get("dividendYield") or row.get("trailingAnnualDividendYield")),
        "fifty_two_week_high": _as_float(row.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _as_float(row.get("fiftyTwoWeekLow")),
        "as_of": as_of,
        "source": "yahoo",
    }


def _parse_yahoo_chart(payload: dict) -> dict:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ValueError("yahoo chart payload missing chart")
    error = chart.get("error")
    if error:
        raise ValueError(str(error))
    results = chart.get("result") or []
    if not results or not isinstance(results[0], dict):
        raise ValueError("yahoo chart had no series")
    result = results[0]
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
    quotes = indicators.get("quote") or []
    series = quotes[0] if quotes and isinstance(quotes[0], dict) else {}
    closes = series.get("close") or []
    opens = series.get("open") or []
    highs = series.get("high") or []
    lows = series.get("low") or []
    volumes = series.get("volume") or []
    points: list[dict] = []
    for index, stamp in enumerate(timestamps):
        if not isinstance(stamp, (int, float)):
            continue
        close = _as_float(closes[index] if index < len(closes) else None)
        if close is None:
            continue
        points.append(
            {
                "t": int(stamp),
                "close": close,
                "open": _as_float(opens[index] if index < len(opens) else None),
                "high": _as_float(highs[index] if index < len(highs) else None),
                "low": _as_float(lows[index] if index < len(lows) else None),
                "volume": _as_float(volumes[index] if index < len(volumes) else None),
            }
        )
    last = _as_float(meta.get("regularMarketPrice"))
    previous = _as_float(
        meta.get("chartPreviousClose")
        if meta.get("chartPreviousClose") is not None
        else meta.get("previousClose")
    )
    if last is None and points:
        last = points[-1]["close"]
    change = None
    change_pct = None
    if last is not None and previous not in (None, 0):
        change = last - previous
        change_pct = (change / previous) * 100
    as_of = None
    market_time = meta.get("regularMarketTime")
    if isinstance(market_time, (int, float)) and market_time > 0:
        as_of = _iso(datetime.fromtimestamp(market_time, tz=timezone.utc))
    ticker = str(meta.get("symbol") or "").strip().upper()
    return {
        "ticker": ticker,
        "name": str(meta.get("shortName") or meta.get("longName") or "").strip() or None,
        "exchange": str(meta.get("exchangeName") or meta.get("fullExchangeName") or "").strip()
        or None,
        "currency": str(meta.get("currency") or "USD"),
        "last_price": last,
        "previous_close": previous,
        "change": change,
        "change_pct_1d": change_pct,
        "open": _as_float(meta.get("regularMarketOpen")),
        "high": _as_float(meta.get("regularMarketDayHigh")),
        "low": _as_float(meta.get("regularMarketDayLow")),
        "volume": _as_float(meta.get("regularMarketVolume")),
        "fifty_two_week_high": _as_float(meta.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _as_float(meta.get("fiftyTwoWeekLow")),
        "as_of": as_of,
        "points": points,
        "source": "yahoo",
    }


def _merge_quote_stats(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key, value in extra.items():
        if key in {"points", "source"}:
            continue
        if value is not None and merged.get(key) in (None, "", []):
            merged[key] = value
    return merged


def _nasdaq_asset_classes(ticker: str) -> tuple[str, ...]:
    if ticker in NASDAQ_ETF_TICKERS:
        return ("etf", "stocks", "index")
    return ("stocks", "etf", "index")


def _epoch_seconds(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    if number > 1e12:
        number = number / 1000.0
    return int(number)


def _parse_us_date(value: Any) -> int | None:
    raw = str(value or "").strip()
    try:
        parsed = datetime.strptime(raw, "%m/%d/%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(parsed.timestamp())


def _nasdaq_history_window(span: str) -> tuple[date, date, int]:
    end = datetime.now(timezone.utc).date()
    if span == "ytd":
        return date(end.year, 1, 1), end, 320
    days, limit = {
        "5d": (12, 10),
        "1mo": (40, 40),
        "6mo": (210, 160),
        "1y": (400, 280),
        "5y": (365 * 5 + 30, 1400),
        "max": (365 * 20, 6000),
    }.get(span, (400, 280))
    return end - timedelta(days=days), end, limit


def _chart_payload(
    ticker: str,
    points: list[dict],
    *,
    name: str | None,
    exchange: str | None,
    last: float | None,
    previous: float | None,
    volume: float | None,
    as_of: str | None,
    source: str,
) -> dict:
    if last is None and points:
        last = points[-1]["close"]
    change = None
    change_pct = None
    if last is not None and previous not in (None, 0):
        change = last - previous
        change_pct = (change / previous) * 100
    return {
        "ticker": ticker,
        "name": name,
        "exchange": exchange,
        "currency": "USD",
        "last_price": last,
        "previous_close": previous,
        "change": change,
        "change_pct_1d": change_pct,
        "volume": volume,
        "as_of": as_of,
        "points": points,
        "source": source,
    }


def _parse_nasdaq_intraday(payload: dict) -> dict:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("nasdaq chart payload missing data")
    ticker = str(data.get("symbol") or "").strip().upper()
    points: list[dict] = []
    for row in data.get("chart") or []:
        if not isinstance(row, dict):
            continue
        close = _as_float(row.get("y"))
        extra = row.get("z") if isinstance(row.get("z"), dict) else {}
        if close is None:
            close = _as_float(extra.get("value"))
        stamp = _epoch_seconds(row.get("x"))
        if close is None or stamp is None:
            continue
        points.append(
            {
                "t": stamp,
                "close": close,
                "open": None,
                "high": None,
                "low": None,
                "volume": None,
            }
        )
    if not ticker or not points:
        raise ValueError("nasdaq chart had no series")
    last_stamp = points[-1]["t"]
    return _chart_payload(
        ticker,
        points,
        name=str(data.get("company") or "").strip() or None,
        exchange=str(data.get("exchange") or "").strip() or None,
        last=_as_float(data.get("lastSalePrice")),
        previous=_as_float(data.get("previousClose")),
        volume=_as_float(data.get("volume")),
        as_of=_iso(datetime.fromtimestamp(last_stamp, tz=timezone.utc)),
        source="nasdaq",
    )


def _parse_nasdaq_history(ticker: str, payload: dict) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    table = data.get("tradesTable") if isinstance(data.get("tradesTable"), dict) else {}
    points: list[dict] = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        close = _as_float(row.get("close"))
        stamp = _parse_us_date(row.get("date"))
        if close is None or stamp is None:
            continue
        points.append(
            {
                "t": stamp,
                "close": close,
                "open": _as_float(row.get("open")),
                "high": _as_float(row.get("high")),
                "low": _as_float(row.get("low")),
                "volume": _as_float(row.get("volume")),
            }
        )
    points.sort(key=lambda item: item["t"])
    if not points:
        raise ValueError(f"nasdaq history had no series for {ticker}")
    return points


def _fetch_nasdaq_json(url: str) -> dict:
    return _http_get_json(url, NASDAQ_HEADERS)


def _fetch_nasdaq_chart(symbol: str, span: str) -> dict:
    last_error: Exception | None = None
    for asset in _nasdaq_asset_classes(symbol):
        try:
            if span == "1d":
                url = NASDAQ_CHART_URL.format(
                    symbol=quote(symbol, safe=""),
                    asset=quote(asset, safe=""),
                )
                return _parse_nasdaq_intraday(_fetch_nasdaq_json(url))
            start, end, limit = _nasdaq_history_window(span)
            url = NASDAQ_HIST_URL.format(
                symbol=quote(symbol, safe=""),
                asset=quote(asset, safe=""),
                start=start.isoformat(),
                end=end.isoformat(),
                limit=limit,
            )
            points = _parse_nasdaq_history(symbol, _fetch_nasdaq_json(url))
            last = points[-1]["close"]
            previous = points[-2]["close"] if len(points) > 1 else None
            return _chart_payload(
                symbol,
                points,
                name=None,
                exchange=None,
                last=last,
                previous=previous,
                volume=points[-1].get("volume"),
                as_of=_iso(datetime.fromtimestamp(points[-1]["t"], tz=timezone.utc)),
                source="nasdaq",
            )
        except Exception as exc:
            last_error = exc
            continue
    raise last_error or ValueError(f"nasdaq chart unavailable for {symbol}")


def fetch_chart(ticker: str | None, span: str = "1d") -> dict:
    """OHLC series plus quote statistics for one ticker."""
    wanted = normalize_tickers([ticker or ""])
    if not wanted:
        raise ValueError("ticker is required")
    symbol = wanted[0]
    requested = str(span or "1d").strip().lower()
    if requested not in CHART_RANGES:
        raise ValueError(f"unsupported chart range: {span}")
    yahoo_range, interval = CHART_RANGES[requested]
    cache_key = _chart_cache_key(symbol, requested)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CHART_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    chart: dict | None = None
    try:
        chart = _parse_yahoo_chart(
            _http_get_json(_yahoo_chart_url(symbol, yahoo_range, interval)),
        )
        if not chart.get("ticker"):
            chart["ticker"] = symbol
        try:
            stats = _parse_yahoo_quote(_http_get_json(_yahoo_quote_url(symbol)))
            if stats:
                chart = _merge_quote_stats(chart, stats)
        except Exception as exc:
            logger.warning("Yahoo quote stats fetch failed for %s: %s", symbol, exc)
    except Exception as exc:
        logger.warning("Yahoo chart fetch failed for %s: %s", symbol, exc)
        chart = _fetch_nasdaq_chart(symbol, requested)
        interval = "1m" if requested == "1d" else "1d"

    payload = {
        "generated_at": _iso(),
        "range": requested,
        "interval": interval,
        **(chart or {}),
    }
    with _CACHE_LOCK:
        _CHART_CACHE[cache_key] = (time.monotonic() + CHART_TTL_SECONDS, payload)
    return payload


def _parse_yahoo_search(payload: dict, limit: int = 8) -> list[dict]:
    rows = payload.get("quotes") or []
    matches: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("quoteType") or "").strip().upper()
        if kind and kind not in SEARCH_QUOTE_TYPES:
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen or not TICKER_RE.match(ticker):
            continue
        seen.add(ticker)
        name = str(row.get("shortname") or row.get("longname") or ticker).strip()
        matches.append(
            {
                "ticker": ticker,
                "name": name or ticker,
                "exchange": str(row.get("exchDisp") or row.get("exchange") or "").strip()
                or None,
                "type": (kind or "EQUITY").lower(),
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _parse_nasdaq_search(payload: dict, limit: int = 8) -> list[dict]:
    rows = payload.get("data") or []
    matches: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen or not TICKER_RE.match(ticker):
            continue
        seen.add(ticker)
        asset = str(row.get("asset") or "equity").strip().lower() or "equity"
        matches.append(
            {
                "ticker": ticker,
                "name": str(row.get("name") or ticker).strip() or ticker,
                "exchange": str(row.get("exchange") or "").strip() or None,
                "type": "etf" if asset == "etf" else "equity",
            }
        )
        if len(matches) >= limit:
            break
    return matches


def search_symbols(query: str | None, limit: int = 8) -> dict:
    """Symbol lookup for the Markets search box (Yahoo, Nasdaq fallback)."""
    q = str(query or "").strip()[:80]
    if len(q) < 1:
        return {"query": q, "matches": []}
    cache_key = q.lower()
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
    capped = max(1, min(int(limit), 12))
    matches: list[dict] = []
    try:
        url = (
            f"{YAHOO_SEARCH_URL}?q={quote(q)}"
            "&quotesCount=12&newsCount=0&listsCount=0"
            "&lang=en-US&region=US"
        )
        matches = _parse_yahoo_search(_http_get_json(url), limit=capped)
    except Exception as exc:
        logger.warning("Yahoo symbol search failed: %s", exc)
    if not matches:
        try:
            url = f"{NASDAQ_SEARCH_URL}?search={quote(q)}"
            matches = _parse_nasdaq_search(_fetch_nasdaq_json(url), limit=capped)
        except Exception as exc:
            logger.warning("Nasdaq symbol search failed: %s", exc)
    payload = {"query": q, "matches": matches}
    with _CACHE_LOCK:
        _SEARCH_CACHE[cache_key] = (time.monotonic() + SEARCH_TTL_SECONDS, payload)
    return payload
