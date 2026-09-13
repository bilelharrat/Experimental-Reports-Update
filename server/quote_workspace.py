"""Yahoo Gold-parity quote workspace: stats, financials, analysis, holders, options.

Public Nasdaq endpoints are the primary source because Yahoo quoteSummary is
often rate-limited. Licensed third-party research (Morningstar write-ups,
Argus PDFs, FT) is not included.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from server import live_quotes

logger = logging.getLogger(__name__)

WORKSPACE_TTL_SECONDS = 120
SCREENER_TTL_SECONDS = 180
PEERS_TTL_SECONDS = 120
OPTIONS_SNAP_TTL_SECONDS = 60
_WORKSPACE_CACHE: dict[str, tuple[float, dict]] = {}
_SCREENER_CACHE: dict[str, tuple[float, dict]] = {}
_PEERS_CACHE: dict[str, tuple[float, dict]] = {}
_CALENDAR_CACHE: dict[str, tuple[float, dict]] = {}
_OPTIONS_SNAP_CACHE: dict[str, tuple[float, dict]] = {}
CALENDAR_TTL_SECONDS = 1800

DEFAULT_PEER_FALLBACKS = ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "TSM", "AMD")


def clear_cache() -> None:
    with live_quotes._CACHE_LOCK:
        _WORKSPACE_CACHE.clear()
        _SCREENER_CACHE.clear()
        _PEERS_CACHE.clear()
        _CALENDAR_CACHE.clear()
        _OPTIONS_SNAP_CACHE.clear()


def _get(url: str) -> dict:
    return live_quotes._http_get_json(url, live_quotes.NASDAQ_HEADERS)


def _label_map(node: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(node, dict):
        return out
    for key, row in node.items():
        if isinstance(row, dict) and "value" in row:
            out[str(key)] = str(row.get("value") or "").strip()
        elif row is not None and not isinstance(row, dict):
            out[str(key)] = str(row).strip()
    return out


def _period_table(node: dict | None) -> dict:
    if not isinstance(node, dict):
        return {"headers": [], "rows": []}
    headers_raw = node.get("headers") if isinstance(node.get("headers"), dict) else {}
    headers = [
        str(headers_raw.get(key) or "").strip()
        for key in ("value2", "value3", "value4", "value5")
        if headers_raw.get(key)
    ]
    rows = []
    for row in node.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("value1") or "").strip()
        values = [str(row.get(key) or "").strip() for key in ("value2", "value3", "value4", "value5")]
        if not label:
            continue
        if not any(values):
            rows.append({"label": label, "section": True, "values": []})
            continue
        rows.append({"label": label, "section": False, "values": values[: len(headers) or 4]})
    return {"headers": headers, "rows": rows}


def _try_assets(symbol: str, builder) -> dict | None:
    last_error: Exception | None = None
    for asset in live_quotes._nasdaq_asset_classes(symbol):
        try:
            payload = builder(asset)
            if payload:
                return payload
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        logger.warning("Nasdaq workspace fetch failed for %s: %s", symbol, last_error)
    return None


def _field_value(node) -> str | None:
    if isinstance(node, dict):
        raw = node.get("value")
    else:
        raw = node
    text = str(raw or "").strip()
    return text or None


def _parse_profile(payload: dict, symbol: str) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "ticker": (_field_value(data.get("Symbol")) or symbol).upper(),
        "name": _field_value(data.get("CompanyName")),
        "sector": _field_value(data.get("Sector")),
        "industry": _field_value(data.get("Industry")),
        "region": _field_value(data.get("Region")),
        "website": _field_value(data.get("CompanyUrl")),
        "address": _field_value(data.get("Address")),
        "phone": _field_value(data.get("Phone")),
        "description": _field_value(data.get("CompanyDescription")),
    }


def _parse_summary(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    mapped = _label_map(data.get("summaryData"))
    bid_ask = data.get("bidAsk") if isinstance(data.get("bidAsk"), dict) else {}
    return {
        "exchange": mapped.get("Exchange"),
        "sector": mapped.get("Sector"),
        "industry": mapped.get("Industry"),
        "one_year_target": mapped.get("OneYrTarget"),
        "day_range": mapped.get("TodayHighLow"),
        "volume": mapped.get("ShareVolume"),
        "avg_volume": mapped.get("AverageVolume") or mapped.get("AvgDailyVol20Days"),
        "previous_close": mapped.get("PreviousClose"),
        "fifty_two_week": mapped.get("FiftTwoWeekHighLow"),
        "market_cap": mapped.get("MarketCap"),
        "dividend": mapped.get("AnnualizedDividend"),
        "ex_dividend": mapped.get("ExDividendDate"),
        "dividend_pay": mapped.get("DividendPaymentDate"),
        "yield": mapped.get("Yield"),
        "beta": mapped.get("Beta"),
        "alpha": mapped.get("Alpha"),
        "aum": mapped.get("AUM"),
        "expense_ratio": mapped.get("ExpenseRatio"),
        "bid": bid_ask.get("bidPrice") or mapped.get("Bid"),
        "ask": bid_ask.get("askPrice") or mapped.get("Ask"),
    }


def _parse_financials(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "income": _period_table(data.get("incomeStatementTable")),
        "balance": _period_table(data.get("balanceSheetTable")),
        "cashflow": _period_table(data.get("cashFlowTable")),
        "ratios": _period_table(data.get("financialRatiosTable")),
    }


def _parse_forecast_table(node: dict | None) -> list[dict]:
    if not isinstance(node, dict):
        return []
    rows = []
    for row in node.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "period": row.get("fiscalEnd"),
                "consensus": live_quotes._as_float(row.get("consensusEPSForecast")),
                "high": live_quotes._as_float(row.get("highEPSForecast")),
                "low": live_quotes._as_float(row.get("lowEPSForecast")),
                "estimates": live_quotes._as_float(row.get("noOfEstimates")),
                "revisions_up": live_quotes._as_float(row.get("up")),
                "revisions_down": live_quotes._as_float(row.get("down")),
            }
        )
    return rows


def _parse_analysis(target_payload: dict, forecast_payload: dict) -> dict:
    target = target_payload.get("data") if isinstance(target_payload.get("data"), dict) else {}
    overview = target.get("consensusOverview") if isinstance(target.get("consensusOverview"), dict) else {}
    forecast = forecast_payload.get("data") if isinstance(forecast_payload.get("data"), dict) else {}
    return {
        "target": live_quotes._as_float(overview.get("priceTarget")),
        "target_low": live_quotes._as_float(overview.get("lowPriceTarget")),
        "target_high": live_quotes._as_float(overview.get("highPriceTarget")),
        "buy": int(overview.get("buy") or 0),
        "hold": int(overview.get("hold") or 0),
        "sell": int(overview.get("sell") or 0),
        "quarterly": _parse_forecast_table(forecast.get("quarterlyForecast")),
        "yearly": _parse_forecast_table(forecast.get("yearlyForecast")),
    }


def _parse_holders(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    summary = _label_map(data.get("ownershipSummary"))
    holdings = data.get("holdingsTransactions") if isinstance(data.get("holdingsTransactions"), dict) else {}
    table = holdings.get("table") if isinstance(holdings.get("table"), dict) else {}
    rows = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "owner": row.get("ownerName"),
                "date": row.get("date"),
                "shares": row.get("sharesHeld"),
                "change": row.get("sharesChange"),
                "change_pct": row.get("sharesChangePCT"),
                "value": row.get("marketValue"),
            }
        )
        if len(rows) >= 12:
            break
    return {
        "ownership_pct": summary.get("SharesOutstandingPCT"),
        "shares_out": summary.get("ShareoutstandingTotal"),
        "holdings_value": summary.get("TotalHoldingsValue"),
        "holders": rows,
    }


def _parse_insiders(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    trades = data.get("numberOfTrades") if isinstance(data.get("numberOfTrades"), dict) else {}
    summary = []
    for row in trades.get("rows") or []:
        if not isinstance(row, dict):
            continue
        summary.append(
            {
                "label": row.get("insiderTrade"),
                "months3": row.get("months3"),
                "months12": row.get("months12"),
            }
        )
    tx = data.get("transactionTable") if isinstance(data.get("transactionTable"), dict) else {}
    table = tx.get("table") if isinstance(tx.get("table"), dict) else tx
    recent = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        recent.append(row)
        if len(recent) >= 12:
            break
    return {"summary": summary, "recent": recent}


def _parse_us_date(value) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_earnings(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    table = (
        data.get("earningsSurpriseTable")
        if isinstance(data.get("earningsSurpriseTable"), dict)
        else {}
    )
    past = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        reported = _parse_us_date(row.get("dateReported"))
        past.append(
            {
                "period": row.get("fiscalQtrEnd"),
                "reported": reported.isoformat() if reported else None,
                "eps": live_quotes._as_float(row.get("eps")),
                "estimate": live_quotes._as_float(row.get("consensusForecast")),
                "surprise_pct": live_quotes._as_float(row.get("percentageSurprise")),
            }
        )
        if len(past) >= 8:
            break
    next_date = None
    if past and past[0].get("reported"):
        last = date.fromisoformat(past[0]["reported"])
        # Nasdaq rarely publishes a confirmed next date; estimate ~one quarter out.
        next_date = (last + timedelta(days=91)).isoformat()
    return {
        "next_date": next_date,
        "next_estimated": bool(next_date),
        "past": past,
    }


def _parse_options(payload: dict, last: float | None) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    table = data.get("table") if isinstance(data.get("table"), dict) else {}
    rows = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        strike = live_quotes._as_float(row.get("strike"))
        if strike is None:
            continue
        rows.append(
            {
                "expiry": row.get("expiryDate"),
                "strike": strike,
                "call_last": row.get("c_Last"),
                "call_change": row.get("c_Change"),
                "call_bid": row.get("c_Bid"),
                "call_ask": row.get("c_Ask"),
                "call_volume": row.get("c_Volume"),
                "call_oi": row.get("c_Openinterest"),
                "put_last": row.get("p_Last"),
                "put_change": row.get("p_Change"),
                "put_bid": row.get("p_Bid"),
                "put_ask": row.get("p_Ask"),
                "put_volume": row.get("p_Volume"),
                "put_oi": row.get("p_Openinterest"),
            }
        )
    if last is not None and rows:
        rows.sort(key=lambda row: abs(row["strike"] - last))
        rows = sorted(rows[:40], key=lambda row: (str(row.get("expiry") or ""), row["strike"]))
    else:
        rows = rows[:40]
    return {"last_trade": data.get("lastTrade"), "rows": rows}


def _trim_options_rows(rows: list[dict], last: float | None, *, max_rows: int) -> list[dict]:
    if not rows:
        return []
    if last is not None:
        ranked = sorted(rows, key=lambda row: abs(float(row.get("strike") or 0) - last))
        keep = ranked[:max_rows]
        return sorted(keep, key=lambda row: (str(row.get("expiry") or ""), float(row.get("strike") or 0)))
    return rows[:max_rows]


def _options_from_workspace_payload(payload: dict | None, *, max_rows: int) -> dict | None:
    if not isinstance(payload, dict):
        return None
    options = payload.get("options") if isinstance(payload.get("options"), dict) else None
    if not options:
        return None
    rows = list(options.get("rows") or [])
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    last = live_quotes._as_float(summary.get("previous_close"))
    if last is None:
        last = live_quotes._as_float(str(options.get("last_trade") or "").replace("$", "").replace(",", ""))
    trimmed = _trim_options_rows(rows, last, max_rows=max_rows)
    return {
        "ticker": payload.get("ticker"),
        "last_trade": options.get("last_trade"),
        "underlying_last": last,
        "source": "nasdaq",
        "implied_vol_available": False,
        "rows": trimmed,
    }


def fetch_options_chain(symbol: str, last: float | None = None) -> dict:
    """Fetch Nasdaq option-chain only (no full workspace)."""
    raw = _try_assets(
        symbol,
        lambda asset: _get(
            f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/option-chain?assetclass={asset}"
        ),
    )
    return _parse_options(raw, last) if raw else {"last_trade": None, "rows": []}


def compact_options_snapshot(
    ticker: str | None,
    *,
    max_rows: int = 12,
    cache_only: bool = False,
) -> dict | None:
    """Near-ATM call/put premiums for Ask — prefer warm workspace cache."""
    wanted = live_quotes.normalize_tickers([ticker or ""])
    if not wanted:
        return None
    symbol = wanted[0]
    now = time.monotonic()
    with live_quotes._CACHE_LOCK:
        snap_cached = _OPTIONS_SNAP_CACHE.get(symbol)
        if snap_cached and snap_cached[0] > now:
            return snap_cached[1]
        workspace_cached = _WORKSPACE_CACHE.get(symbol)
        if workspace_cached and workspace_cached[0] > now:
            from_ws = _options_from_workspace_payload(workspace_cached[1], max_rows=max_rows)
            if from_ws is not None:
                _OPTIONS_SNAP_CACHE[symbol] = (
                    time.monotonic() + OPTIONS_SNAP_TTL_SECONDS,
                    from_ws,
                )
                return from_ws

    if cache_only:
        return None

    last: float | None = None
    try:
        live = live_quotes.fetch_quotes([symbol]).get("quotes", {}).get(symbol) or {}
        last = live_quotes._as_float(live.get("last_price"))
    except Exception:
        last = None

    try:
        parsed = fetch_options_chain(symbol, last)
    except Exception as exc:
        logger.warning("options snapshot failed for %s: %s", symbol, exc)
        return None

    rows = _trim_options_rows(list(parsed.get("rows") or []), last, max_rows=max_rows)
    snap = {
        "ticker": symbol,
        "last_trade": parsed.get("last_trade"),
        "underlying_last": last,
        "source": "nasdaq",
        "implied_vol_available": False,
        "rows": rows,
    }
    with live_quotes._CACHE_LOCK:
        _OPTIONS_SNAP_CACHE[symbol] = (time.monotonic() + OPTIONS_SNAP_TTL_SECONDS, snap)
    return snap


def format_options_snapshot_for_prompt(snap: dict | None) -> str:
    """Compact markdown block for Copilot/Ask runtime prompts."""
    if not snap:
        return ""
    ticker = snap.get("ticker") or "?"
    lines = [
        f"## Options premiums ({ticker}, Nasdaq near-ATM)",
        f"Underlying last: {snap.get('underlying_last') if snap.get('underlying_last') is not None else '—'}"
        f" · chain last trade: {snap.get('last_trade') or '—'}",
        "IV is not in this Nasdaq snapshot — use bid/ask/last premiums below.",
        "expiry | strike | call bid/ask/last | put bid/ask/last | call vol/oi | put vol/oi",
    ]
    rows = snap.get("rows") or []
    if not rows:
        lines.append("(no option chain rows for this symbol)")
        return "\n".join(lines)

    def _ba_last(bid, ask, last) -> str:
        return f"{bid or '—'}/{ask or '—'}/{last or '—'}"

    for row in rows:
        lines.append(
            f"{row.get('expiry') or '—'} | {row.get('strike')} | "
            f"{_ba_last(row.get('call_bid'), row.get('call_ask'), row.get('call_last'))} | "
            f"{_ba_last(row.get('put_bid'), row.get('put_ask'), row.get('put_last'))} | "
            f"{row.get('call_volume') or '—'}/{row.get('call_oi') or '—'} | "
            f"{row.get('put_volume') or '—'}/{row.get('put_oi') or '—'}"
        )
    return "\n".join(lines)


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        logger.warning("workspace part failed: %s", exc)
        return default


def fetch_workspace(ticker: str | None) -> dict:
    wanted = live_quotes.normalize_tickers([ticker or ""])
    if not wanted:
        raise ValueError("ticker is required")
    symbol = wanted[0]
    now = time.monotonic()
    with live_quotes._CACHE_LOCK:
        cached = _WORKSPACE_CACHE.get(symbol)
        if cached and cached[0] > now:
            return cached[1]

    def profile():
        try:
            return _parse_profile(
                _get(f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/company-profile"),
                symbol,
            )
        except Exception as exc:
            logger.warning("profile unavailable for %s: %s", symbol, exc)
            return {}

    def summary():
        raw = _try_assets(
            symbol,
            lambda asset: _get(
                f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/summary?assetclass={asset}"
            ),
        )
        return _parse_summary(raw) if raw else {}

    def financials():
        try:
            return _parse_financials(
                _get(
                    f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/financials?frequency=1"
                )
            )
        except Exception as exc:
            logger.warning("financials unavailable for %s: %s", symbol, exc)
            return {
                "income": {"headers": [], "rows": []},
                "balance": {"headers": [], "rows": []},
                "cashflow": {"headers": [], "rows": []},
                "ratios": {"headers": [], "rows": []},
            }

    def analysis():
        target = _safe(
            lambda: _get(f"https://api.nasdaq.com/api/analyst/{quote(symbol, safe='')}/targetprice"),
            {},
        )
        forecast = _safe(
            lambda: _get(
                f"https://api.nasdaq.com/api/analyst/{quote(symbol, safe='')}/earnings-forecast"
            ),
            {},
        )
        return _parse_analysis(target, forecast)

    def holders():
        try:
            return _parse_holders(
                _get(
                    f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/institutional-holdings"
                )
            )
        except Exception as exc:
            logger.warning("holders unavailable for %s: %s", symbol, exc)
            return {"ownership_pct": None, "shares_out": None, "holdings_value": None, "holders": []}

    def insiders():
        try:
            return _parse_insiders(
                _get(f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/insider-trades")
            )
        except Exception as exc:
            logger.warning("insiders unavailable for %s: %s", symbol, exc)
            return {"summary": [], "recent": []}

    def options(last: float | None):
        raw = _try_assets(
            symbol,
            lambda asset: _get(
                f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/option-chain?assetclass={asset}"
            ),
        )
        return _parse_options(raw, last) if raw else {"last_trade": None, "rows": []}

    def earnings():
        try:
            return _parse_earnings(
                _get(f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/earnings-surprise")
            )
        except Exception as exc:
            logger.warning("earnings unavailable for %s: %s", symbol, exc)
            return {"next_date": None, "next_estimated": False, "past": []}

    parts: dict = {}
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = {
            pool.submit(profile): "profile",
            pool.submit(summary): "summary",
            pool.submit(financials): "financials",
            pool.submit(analysis): "analysis",
            pool.submit(holders): "holders",
            pool.submit(insiders): "insiders",
            pool.submit(earnings): "earnings",
        }
        for future in as_completed(futures):
            parts[futures[future]] = future.result()

    last = live_quotes._as_float((parts.get("summary") or {}).get("previous_close"))
    parts["options"] = _safe(lambda: options(last), {"last_trade": None, "rows": []})

    # Nasdaq summary often omits AnnualizedDividend/Yield now. Fill from the
    # live quote cache (CNBC already carries both) so desk stats aren't blank.
    summary = dict(parts.get("summary") or {})
    try:
        live = live_quotes.fetch_quotes([symbol]).get("quotes", {}).get(symbol) or {}
    except Exception:
        live = {}
    if live:
        if not summary.get("dividend") and live.get("dividend"):
            summary["dividend"] = str(live["dividend"])
        if not summary.get("yield") and live.get("dividend_yield") is not None:
            dy = live_quotes._as_float(live.get("dividend_yield"))
            if dy is not None:
                pct = dy * 100 if dy <= 1 else dy
                summary["yield"] = f"{pct:.2f}%"
        if not summary.get("beta") and live.get("beta") is not None:
            summary["beta"] = f"{live_quotes._as_float(live.get('beta')):.2f}"
        parts["summary"] = summary

    payload = {
        "generated_at": live_quotes._iso(),
        "ticker": symbol,
        "source": "nasdaq",
        **parts,
    }
    with live_quotes._CACHE_LOCK:
        _WORKSPACE_CACHE[symbol] = (time.monotonic() + WORKSPACE_TTL_SECONDS, payload)
    return payload


def _parse_screener(payload: dict) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    # download=true puts rows on data.rows; tableonly puts them under data.table.rows
    table = data.get("table") if isinstance(data.get("table"), dict) else data
    raw_rows = table.get("rows") if isinstance(table, dict) else None
    if not isinstance(raw_rows, list):
        raw_rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    rows = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or not live_quotes.TICKER_RE.match(ticker):
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": row.get("name"),
                "last": live_quotes._as_float(row.get("lastsale")),
                "change": live_quotes._as_float(row.get("netchange")),
                "change_pct": live_quotes._as_float(row.get("pctchange")),
                "market_cap": live_quotes._as_float(str(row.get("marketCap") or "").replace(",", "")),
                "volume": live_quotes._as_float(row.get("volume")),
                "sector": str(row.get("sector") or "").strip() or None,
                "industry": str(row.get("industry") or "").strip() or None,
                "country": str(row.get("country") or "").strip() or None,
            }
        )
    return rows


def fetch_screeners() -> dict:
    now = time.monotonic()
    with live_quotes._CACHE_LOCK:
        cached = _SCREENER_CACHE.get("universe")
        if cached and cached[0] > now:
            return cached[1]
    rows = _parse_screener(
        _get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=100&download=true")
    )
    gainers = sorted(
        [row for row in rows if row["change_pct"] is not None],
        key=lambda row: row["change_pct"],
        reverse=True,
    )[:25]
    losers = sorted(
        [row for row in rows if row["change_pct"] is not None],
        key=lambda row: row["change_pct"],
    )[:25]
    active = sorted(
        [row for row in rows if row.get("volume")],
        key=lambda row: row["volume"] or 0,
        reverse=True,
    )[:25]
    sectors = sorted({row["sector"] for row in rows if row.get("sector")})
    payload = {
        "generated_at": live_quotes._iso(),
        "gainers": gainers,
        "losers": losers,
        "active": active,
        "universe": rows,
        "sectors": sectors,
        "source": "nasdaq",
    }
    with live_quotes._CACHE_LOCK:
        _SCREENER_CACHE["universe"] = (time.monotonic() + SCREENER_TTL_SECONDS, payload)
    return payload


def _returns_from_points(points: list[dict]) -> dict:
    closes = []
    for point in points or []:
        stamp = live_quotes._as_float(point.get("t"))
        close = live_quotes._as_float(point.get("close"))
        if stamp is None or close is None:
            continue
        closes.append((int(stamp), float(close)))
    if len(closes) < 2:
        return {
            "1d": None,
            "1m": None,
            "ytd": None,
            "1y": None,
            "last": None,
            "drawdown_1y": None,
            "high_1y": None,
            "low_1y": None,
        }
    last_t, last = closes[-1]
    values = [row[1] for row in closes]
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, ((value - peak) / peak) * 100.0)

    def ret_since(seconds: int | None = None, *, since: date | None = None) -> float | None:
        target = last_t - seconds if seconds is not None else None
        if since is not None:
            target = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp())
        if target is None:
            return None
        base = min(closes, key=lambda row: abs(row[0] - target))
        if seconds and seconds > 86400 * 20 and abs(base[0] - target) > seconds * 0.35:
            return None
        if base[1] == 0:
            return None
        return ((last - base[1]) / base[1]) * 100.0

    today = datetime.fromtimestamp(last_t, tz=timezone.utc).date()
    ytd_start = date(today.year, 1, 1)
    return {
        "1d": ret_since(86400 * 2),
        "1m": ret_since(86400 * 30),
        "ytd": ret_since(since=ytd_start),
        "1y": ret_since(86400 * 365),
        "last": last,
        "drawdown_1y": max_dd,
        "high_1y": max(values),
        "low_1y": min(values),
    }


def _parse_pct(value) -> float | None:
    number = live_quotes._as_float(value)
    if number is None:
        return None
    # Nasdaq ratios often arrive as "71.06%" already stripped by _as_float.
    # Some rows are stored as 71.06 already in percent units.
    return number


def _money_growth(current, prior) -> float | None:
    cur = live_quotes._as_float(str(current or "").replace("$", "").replace(",", ""))
    old = live_quotes._as_float(str(prior or "").replace("$", "").replace(",", ""))
    if cur is None or old is None or old == 0:
        return None
    return ((cur - old) / abs(old)) * 100.0


def _fundamentals(symbol: str) -> dict:
    try:
        payload = _get(
            f"https://api.nasdaq.com/api/company/{quote(symbol, safe='')}/financials?frequency=1"
        )
    except Exception as exc:
        logger.warning("fundamentals unavailable for %s: %s", symbol, exc)
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    income = data.get("incomeStatementTable") if isinstance(data.get("incomeStatementTable"), dict) else {}
    ratios = data.get("financialRatiosTable") if isinstance(data.get("financialRatiosTable"), dict) else {}
    revenue_growth = None
    for row in income.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("value1") or "").strip().lower()
        if label in {"total revenue", "revenue"}:
            revenue_growth = _money_growth(row.get("value2"), row.get("value3"))
            break
    margins: dict[str, float | None] = {
        "gross_margin": None,
        "operating_margin": None,
        "profit_margin": None,
    }
    for row in ratios.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("value1") or "").strip().lower()
        latest = _parse_pct(row.get("value2"))
        if label == "gross margin":
            margins["gross_margin"] = latest
        elif label == "operating margin":
            margins["operating_margin"] = latest
        elif label in {"profit margin", "net margin"}:
            margins["profit_margin"] = latest
    return {"revenue_growth": revenue_growth, **margins}


def _peer_row(
    symbol: str,
    chart: dict | None,
    name: str | None = None,
    meta: dict | None = None,
    fundamentals: dict | None = None,
) -> dict:
    points = (chart or {}).get("points") or []
    returns = _returns_from_points(points)
    change_1d = live_quotes._as_float((chart or {}).get("change_pct_1d"))
    if change_1d is None:
        change_1d = returns.get("1d")
    meta = meta or {}
    fundamentals = fundamentals or {}
    spark = [
        live_quotes._as_float(point.get("close"))
        for point in points[-42:]
        if live_quotes._as_float(point.get("close")) is not None
    ]
    return {
        "ticker": symbol,
        "name": name or (chart or {}).get("name") or symbol,
        "last": returns.get("last") or live_quotes._as_float((chart or {}).get("last_price")),
        "change_1d": change_1d,
        "ret_1m": returns.get("1m"),
        "ret_ytd": returns.get("ytd"),
        "ret_1y": returns.get("1y"),
        "drawdown_1y": returns.get("drawdown_1y"),
        "high_1y": returns.get("high_1y"),
        "low_1y": returns.get("low_1y"),
        "market_cap": live_quotes._as_float((chart or {}).get("market_cap"))
        or meta.get("market_cap"),
        "pe_ratio": live_quotes._as_float((chart or {}).get("pe_ratio")),
        "revenue_growth": fundamentals.get("revenue_growth"),
        "gross_margin": fundamentals.get("gross_margin"),
        "operating_margin": fundamentals.get("operating_margin"),
        "profit_margin": fundamentals.get("profit_margin"),
        "sector": meta.get("sector"),
        "spark": spark,
        "points": [
            {"t": point.get("t"), "close": point.get("close")}
            for point in points
            if live_quotes._as_float(point.get("close")) is not None
        ][-260:],
    }


def _relative(value: float | None, bench: float | None) -> float | None:
    if value is None or bench is None:
        return None
    return value - bench


def _screener_meta(symbol: str) -> dict:
    try:
        universe = fetch_screeners().get("universe") or []
    except Exception:
        return {}
    for row in universe:
        if row.get("ticker") == symbol:
            return {
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "market_cap": row.get("market_cap"),
            }
    return {}


def _sector_peers(symbol: str, sector: str | None, limit: int = 5) -> list[str]:
    if not sector:
        return []
    try:
        universe = fetch_screeners().get("universe") or []
    except Exception:
        return []
    same = [
        row["ticker"]
        for row in sorted(
            [
                row
                for row in universe
                if row.get("sector") == sector and row["ticker"] != symbol and row.get("market_cap")
            ],
            key=lambda row: row["market_cap"] or 0,
            reverse=True,
        )[:limit]
    ]
    return same


def fetch_peers(ticker: str | None, peer_tickers: list[str] | None = None) -> dict:
    wanted = live_quotes.normalize_tickers([ticker or ""])
    if not wanted:
        raise ValueError("ticker is required")
    symbol = wanted[0]
    extras = live_quotes.normalize_tickers(peer_tickers or [])
    extras = [row for row in extras if row != symbol][:8]
    cache_key = f"{symbol}|{','.join(extras)}"
    now = time.monotonic()
    with live_quotes._CACHE_LOCK:
        cached = _PEERS_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    sector = None
    try:
        workspace = fetch_workspace(symbol)
        sector = (workspace.get("profile") or {}).get("sector") or (
            workspace.get("summary") or {}
        ).get("sector")
    except Exception:
        workspace = {}

    peers = list(extras)
    for candidate in _sector_peers(symbol, sector, limit=5):
        if candidate not in peers and candidate != symbol:
            peers.append(candidate)
    for candidate in DEFAULT_PEER_FALLBACKS:
        if len(peers) >= 5:
            break
        if candidate != symbol and candidate not in peers:
            peers.append(candidate)
    peers = peers[:5]
    symbols = [symbol, "SPY", *peers]

    charts: dict[str, dict] = {}
    fundamentals: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures: dict = {}
        for row in symbols:
            futures[pool.submit(live_quotes.fetch_chart, row, "1y")] = ("chart", row)
            if row != "SPY":
                futures[pool.submit(_fundamentals, row)] = ("fund", row)
        for future in as_completed(futures):
            kind, ticker_key = futures[future]
            try:
                result = future.result() or {}
            except Exception as exc:
                logger.warning("peer %s failed for %s: %s", kind, ticker_key, exc)
                result = {}
            if kind == "chart":
                charts[ticker_key] = result
            else:
                fundamentals[ticker_key] = result

    def decorate(symbol: str, chart: dict | None, name: str | None = None) -> dict:
        row = _peer_row(
            symbol,
            chart,
            name,
            _screener_meta(symbol),
            fundamentals.get(symbol) or {},
        )
        bench = charts.get("SPY")
        if symbol != "SPY" and bench:
            spy = _peer_row("SPY", bench, "S&P 500")
            row["vs_spy_1m"] = _relative(row.get("ret_1m"), spy.get("ret_1m"))
            row["vs_spy_ytd"] = _relative(row.get("ret_ytd"), spy.get("ret_ytd"))
            row["vs_spy_1y"] = _relative(row.get("ret_1y"), spy.get("ret_1y"))
        else:
            row["vs_spy_1m"] = None
            row["vs_spy_ytd"] = None
            row["vs_spy_1y"] = None
        return row

    payload = {
        "generated_at": live_quotes._iso(),
        "ticker": symbol,
        "sector": sector,
        "primary": decorate(symbol, charts.get(symbol), (workspace.get("profile") or {}).get("name")),
        "benchmark": decorate("SPY", charts.get("SPY"), "S&P 500"),
        "peers": [decorate(row, charts.get(row)) for row in peers],
        "source": "nasdaq+charts",
    }
    with live_quotes._CACHE_LOCK:
        _PEERS_CACHE[cache_key] = (time.monotonic() + PEERS_TTL_SECONDS, payload)
    return payload


def _parse_calendar_day(payload: dict, day: date) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = []
    for row in data.get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or not live_quotes.TICKER_RE.match(ticker):
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": row.get("name"),
                "date": day.isoformat(),
                "time": str(row.get("time") or "").replace("time-", "").replace("-", " ") or None,
                "eps_forecast": live_quotes._as_float(row.get("epsForecast")),
                "market_cap": live_quotes._as_float(str(row.get("marketCap") or "").replace(",", "")),
                "kind": "earnings",
                "title": "Earnings",
                "confirmed": True,
            }
        )
    return rows


def _parse_dividend_day(payload: dict, day: date) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    calendar = data.get("calendar") if isinstance(data.get("calendar"), dict) else data
    rows = []
    for row in calendar.get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or not live_quotes.TICKER_RE.match(ticker):
            continue
        ex_date = _parse_us_date(row.get("dividend_Ex_Date")) or day
        rows.append(
            {
                "ticker": ticker,
                "name": row.get("companyName") or ticker,
                "date": ex_date.isoformat(),
                "time": None,
                "dividend_rate": live_quotes._as_float(row.get("dividend_Rate")),
                "kind": "dividend",
                "title": "Ex-dividend",
                "confirmed": True,
            }
        )
    return rows


def _parse_econ_day(payload: dict, day: date) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = []
    for row in data.get("rows") or []:
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "").strip()
        name = str(row.get("eventName") or "").strip()
        if not name:
            continue
        # Keep the desk rhythm focused on US prints by default.
        if country and country.lower() not in {"united states", "us", "usa"}:
            continue
        rows.append(
            {
                "ticker": None,
                "name": country or "Macro",
                "date": day.isoformat(),
                "time": str(row.get("gmt") or "").strip() or None,
                "kind": "macro",
                "title": name,
                "actual": str(row.get("actual") or "").strip() or None,
                "consensus": str(row.get("consensus") or "").strip() or None,
                "previous": str(row.get("previous") or "").strip() or None,
                "confirmed": True,
            }
        )
    return rows


def _scan_calendar_window(kind: str, days: int = 21) -> list[dict]:
    cache_key = f"{kind}-window:{days}"
    now = time.monotonic()
    with live_quotes._CACHE_LOCK:
        cached = _CALENDAR_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
    start = datetime.now(timezone.utc).date()
    events: list[dict] = []
    path = {
        "earnings": "earnings",
        "dividend": "dividends",
        "macro": "economicevents",
    }[kind]
    parser = {
        "earnings": _parse_calendar_day,
        "dividend": _parse_dividend_day,
        "macro": _parse_econ_day,
    }[kind]
    # Macro only needs the next ~10 trading days for desk rhythm.
    span = 10 if kind == "macro" else days
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(
                _get,
                f"https://api.nasdaq.com/api/calendar/{path}?date={(start + timedelta(days=offset)).isoformat()}",
            ): start + timedelta(days=offset)
            for offset in range(0, span)
        }
        for future in as_completed(futures):
            day = futures[future]
            try:
                events.extend(parser(future.result(), day))
            except Exception as exc:
                logger.warning("%s calendar day %s failed: %s", kind, day, exc)
    events.sort(key=lambda row: (row["date"], row.get("ticker") or "", row.get("title") or ""))
    with live_quotes._CACHE_LOCK:
        _CALENDAR_CACHE[cache_key] = (time.monotonic() + CALENDAR_TTL_SECONDS, events)
    return events


def fetch_calendar(tickers: list[str] | None = None) -> dict:
    wanted = live_quotes.normalize_tickers(tickers or [])
    wanted_set = set(wanted)
    earnings = _scan_calendar_window("earnings", 21)
    dividends = _scan_calendar_window("dividend", 21)
    macro = _scan_calendar_window("macro", 10)

    confirmed = [row for row in earnings if not wanted_set or row["ticker"] in wanted_set]
    div_rows = [row for row in dividends if not wanted_set or row["ticker"] in wanted_set]

    missing = [ticker for ticker in wanted if ticker not in {row["ticker"] for row in confirmed}]
    estimated: list[dict] = []
    if missing:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                pool.submit(
                    lambda sym=symbol: _safe(
                        lambda: _parse_earnings(
                            _get(
                                f"https://api.nasdaq.com/api/company/{quote(sym, safe='')}/earnings-surprise"
                            )
                        ),
                        {"next_date": None, "next_estimated": False, "past": []},
                    )
                ): symbol
                for symbol in missing[:16]
            }
            for future in as_completed(futures):
                symbol = futures[future]
                payload = future.result()
                if not payload.get("next_date"):
                    continue
                estimated.append(
                    {
                        "ticker": symbol,
                        "name": symbol,
                        "date": payload["next_date"],
                        "time": None,
                        "eps_forecast": None,
                        "market_cap": None,
                        "kind": "earnings",
                        "title": "Earnings",
                        "confirmed": False,
                    }
                )

    events = sorted(
        [*confirmed, *estimated, *div_rows, *macro],
        key=lambda row: (row["date"], row.get("kind") or "", row.get("ticker") or row.get("title") or ""),
    )
    return {
        "generated_at": live_quotes._iso(),
        "events": events[:120],
        "counts": {
            "earnings": len(confirmed) + len(estimated),
            "dividends": len(div_rows),
            "macro": len(macro),
        },
        "source": "nasdaq",
    }
