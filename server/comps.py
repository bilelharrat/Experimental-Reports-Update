"""Public ↔ private comps.

Peer fundamentals come from the same Nasdaq feeds Market Radar uses (live quote
for price and market cap, the annual income statement for revenue and growth).
The private side is read from the company's latest memo package text — the
post-money and revenue sentences the memo itself cites — and every number is
returned with where it came from. When a figure isn't on record the field is
``None``; nothing is estimated.
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import live_quotes, quote_workspace, storage

logger = logging.getLogger(__name__)

def _peers_file():
    return storage.DATA_DIR / "settings" / "comps_peers.yaml"

SECTOR_DEFAULT_PEERS: list[tuple[tuple[str, ...], list[str]]] = [
    (("health", "bio", "medical", "pharma"), ["ISRG", "VEEV", "DXCM"]),
    (("fin", "bank", "payment", "lending"), ["SQ", "PYPL", "AFRM"]),
    (("semiconductor", "chip", "hardware", "robot", "physical"), ["NVDA", "AMD", "AVGO"]),
    (("security", "cyber"), ["CRWD", "PANW", "ZS"]),
    (("wireless", "telecom", "network", "positioning"), ["QCOM", "TMUS", "CSCO"]),
    ((), ["PLTR", "DDOG", "SNOW", "MDB", "NET"]),
]

MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(k|m|mm|b|bn|t|million|billion|trillion)?\b"
MULTIPLIERS = {"k": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}

_POST_MONEY = re.compile(r"post[- ]money", re.I)
_POST_MONEY_AFTER = re.compile(
    r"post[- ]money(?:\s+valuation)?(?:\s+(?:of|at|was|is|:))?\s*(?:about|around|roughly|approximately|~)?\s*" + MONEY, re.I
)
_POST_MONEY_BEFORE = re.compile(MONEY + r"[^$.;]{0,25}post[- ]money$", re.I)
_ANNUAL_METRIC = r"(?:arr|annual recurring revenue|(?:revenue\s)?run[- ]rate|annuali[sz]ed revenue|(?:fy|full[- ]year)\s?\d{2,4}\s(?:recognized\s)?revenue)"
_REVENUE_AFTER = re.compile(
    r"\b" + _ANNUAL_METRIC + r"\b(?:\s|of|at|near|was|is|:|reached|exceeded|above|about|roughly|approximately|~)*" + MONEY, re.I
)
_REVENUE_BEFORE = re.compile(MONEY + r"\s(?:in\s)?" + _ANNUAL_METRIC + r"\b", re.I)
_NOT_ANNUAL_AFTER = re.compile(r"^\s*(?:a|per)\s+month|^\s*(?:to|–|-)\s*\$?\d", re.I)
_NOT_ANNUAL_BEFORE = re.compile(r"(?:quarter|\bq[1-4]\b|month(?:ly)?|exit|modeled|projected|forecast)[^.;$]{0,40}$", re.I)

_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_PEERS_LOCK = threading.RLock()
CACHE_TTL_SECONDS = 15 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _localized(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), "") or "")
    return str(value or "")


def default_peers_for(company: dict) -> list[str]:
    sector = " ".join(_localized(company.get(k)) for k in ("sector", "industry", "descriptor", "description")).lower()
    for needles, tickers in SECTOR_DEFAULT_PEERS:
        if not needles or any(n in sector for n in needles):
            return list(tickers)
    return list(SECTOR_DEFAULT_PEERS[-1][1])


def _read_peers_file() -> dict | None:
    """Saved peers by company id; ``None`` when the file is corrupt."""
    try:
        saved = storage._read_yaml(_peers_file(), {})
    except yaml.YAMLError as exc:
        logger.warning("comps peers file %s is unreadable: %s", _peers_file(), exc)
        return None
    return saved if isinstance(saved, dict) else {}


def _write_peers_file(saved: dict) -> None:
    path = _peers_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(saved, f, sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_peers(company_id: str) -> list[str]:
    with _PEERS_LOCK:
        saved = _read_peers_file()
    if isinstance(saved, dict):
        rows = saved.get(company_id)
        if isinstance(rows, list) and rows:
            return [str(t).upper() for t in rows if str(t).strip()][:12]
    company = storage.get_company(company_id) or {}
    return default_peers_for(company)


def save_peers(company_id: str, tickers: list[str]) -> list[str]:
    clean: list[str] = []
    for t in tickers:
        sym = re.sub(r"[^A-Z0-9.\-]", "", str(t).upper().strip())
        if sym and sym not in clean:
            clean.append(sym)
    with _PEERS_LOCK:
        saved = _read_peers_file()
        if saved is None:
            aside = _peers_file().with_name(f"{_peers_file().name}.corrupt-{int(time.time())}")
            _peers_file().replace(aside)
            logger.warning("comps peers file moved aside to %s; starting a fresh file", aside)
            saved = {}
        saved[company_id] = clean[:12]
        _write_peers_file(saved)
    with _LOCK:
        _CACHE.pop(company_id, None)
    return saved[company_id]


def _money(amount: str, unit: str | None) -> float | None:
    try:
        value = float(amount.replace(",", ""))
    except ValueError:
        return None
    return value * MULTIPLIERS.get((unit or "").lower(), 1.0)


def _stated_amount(match: re.Match) -> float | None:
    """Value of the MONEY groups in ``match`` when it carries a unit or a full figure (not a bare range endpoint like ``$55 to``)."""
    amount, unit = match.group(1), match.group(2)
    if not unit and float(amount.replace(",", "")) < 10_000:
        return None
    value = _money(amount, unit)
    return value if value else None


def post_money_from(text: str) -> tuple[float, int, int] | None:
    """(value, start, end) of the post-money amount stated in ``text``: the figure right after the phrase, else the one right before it."""
    for phrase in _POST_MONEY.finditer(text):
        after = _POST_MONEY_AFTER.match(text, phrase.start())
        if after and _stated_amount(after):
            return _stated_amount(after), after.start(), after.end()
        window_start = max(0, phrase.start() - 60)
        before = _POST_MONEY_BEFORE.search(text[window_start:phrase.end()])
        if before and _stated_amount(before):
            return _stated_amount(before), window_start + before.start(), window_start + before.end()
    return None


def revenue_from(text: str) -> tuple[float, int, int] | None:
    """(value, start, end) of an annual revenue/ARR figure stated in ``text``; quarterly, monthly and range figures are skipped."""
    candidates = sorted(
        [(m.start(), m.end(), m) for m in _REVENUE_AFTER.finditer(text)] + [(m.start(), m.end(), m) for m in _REVENUE_BEFORE.finditer(text)]
    )
    for start, end, match in candidates:
        amount_end = match.end(2) if match.group(2) else match.end(1)
        if _NOT_ANNUAL_AFTER.match(text[amount_end:amount_end + 12]):
            continue
        if _NOT_ANNUAL_BEFORE.search(text[max(0, start - 50):start]):
            continue
        value = _stated_amount(match)
        if value:
            return value, start, end
    return None


def _latest_memo_package(company_id: str, reports: list[dict] | None = None) -> tuple[Path | None, dict | None]:
    if reports is None:
        reports = storage.list_reports_for(company_id)
    reports = [r for r in reports if r.get("run_dir")]
    reports.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    for report in reports:
        path = storage.DATA_DIR.parent / str(report["run_dir"]) / "logs" / "memo_package.json"
        if path.exists():
            try:
                return path, json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return None, None


def _memo_text_blocks(package: dict) -> list[tuple[str, str]]:
    """(section title, text) pairs from the package."""
    out: list[tuple[str, str]] = []
    for section in package.get("sections") or []:
        title = _localized(section.get("title")) if isinstance(section, dict) else ""
        for block in (section.get("blocks") or []) if isinstance(section, dict) else []:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, dict):
                text = text.get("en")
            if isinstance(text, str) and text.strip():
                out.append((title, text))
            for item in block.get("items") or []:
                item_text = item.get("text") if isinstance(item, dict) else item
                if isinstance(item_text, dict):
                    item_text = item_text.get("en")
                if isinstance(item_text, str) and item_text.strip():
                    out.append((title, item_text))
    return out


def private_facts(company_id: str) -> dict:
    """Post-money and revenue/ARR sentences the memo itself states, with section refs."""
    path, package = _latest_memo_package(company_id)
    facts: dict[str, Any] = {"post_money_usd": None, "revenue_usd": None, "sources": [], "memo_package": str(path) if path else None}
    if not package:
        company = storage.get_company(company_id) or {}
        round_text = " ".join(_localized(company.get("round")).split())
        found = post_money_from(round_text)
        if found:
            facts["post_money_usd"] = found[0]
            facts["sources"].append({"field": "post_money_usd", "section": "company record", "excerpt": round_text[:200]})
        return facts
    for title, text in _memo_text_blocks(package):
        flat = " ".join(text.split())
        if facts["post_money_usd"] is None:
            found = post_money_from(flat)
            if found:
                value, start, end = found
                facts["post_money_usd"] = value
                facts["sources"].append({"field": "post_money_usd", "section": title or "memo", "excerpt": flat[max(0, start - 80): end + 80]})
        if facts["revenue_usd"] is None:
            found = revenue_from(flat)
            if found:
                value, start, end = found
                facts["revenue_usd"] = value
                facts["sources"].append({"field": "revenue_usd", "section": title or "memo", "excerpt": flat[max(0, start - 80): end + 80]})
        if facts["post_money_usd"] is not None and facts["revenue_usd"] is not None:
            break
    return facts


def _latest_annual_revenue(symbol: str) -> float | None:
    try:
        payload = quote_workspace._get(
            f"https://api.nasdaq.com/api/company/{symbol}/financials?frequency=1"
        )
    except Exception:  # noqa: BLE001
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    income = data.get("incomeStatementTable") if isinstance(data.get("incomeStatementTable"), dict) else {}
    for row in income.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("value1") or "").strip().lower()
        if label in {"total revenue", "revenue"}:
            raw = str(row.get("value2") or "")
            try:
                # Nasdaq's income statement is denominated in thousands of dollars.
                return float(re.sub(r"[^0-9.\-]", "", raw)) * 1000 if raw else None
            except ValueError:
                return None
    return None


def peer_row(symbol: str, quote: dict | None) -> dict:
    fundamentals = quote_workspace._fundamentals(symbol) or {}
    market_cap = live_quotes._as_float((quote or {}).get("market_cap"))
    revenue = _latest_annual_revenue(symbol)
    ps = round(market_cap / revenue, 2) if market_cap and revenue and revenue > 0 else None
    return {
        "ticker": symbol,
        "name": (quote or {}).get("name"),
        "last_price": live_quotes._as_float((quote or {}).get("last_price")),
        "change_pct_1d": live_quotes._as_float((quote or {}).get("change_pct_1d")),
        "market_cap_usd": market_cap,
        "revenue_usd": revenue,
        "price_to_sales": ps,
        "revenue_growth": fundamentals.get("revenue_growth"),
        "gross_margin": fundamentals.get("gross_margin"),
        "source": "nasdaq quote + annual income statement",
    }


def build_comps(company_id: str, *, refresh: bool = False) -> dict:
    with _LOCK:
        cached = _CACHE.get(company_id)
        if cached and not refresh and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    peers = get_peers(company_id)
    quotes: dict[str, dict] = {}
    try:
        quotes = (live_quotes.fetch_quotes(peers) or {}).get("quotes") or {}
    except Exception:  # noqa: BLE001
        quotes = {}
    rows = [peer_row(sym, quotes.get(sym)) for sym in peers]
    multiples = [r["price_to_sales"] for r in rows if r.get("price_to_sales")]
    median = round(statistics.median(multiples), 2) if multiples else None

    facts = private_facts(company_id)
    implied = None
    if facts["post_money_usd"] and facts["revenue_usd"]:
        implied = round(facts["post_money_usd"] / facts["revenue_usd"], 2)
    vs_median_pct = round(100 * (implied - median) / median, 1) if implied and median else None

    payload = {
        "company_id": company_id,
        "generated_at": _now(),
        "peers": rows,
        "peer_median_price_to_sales": median,
        "private": {
            **facts,
            "implied_multiple": implied,
            "vs_peer_median_pct": vs_median_pct,
            "basis": "post-money ÷ revenue as stated in the latest memo" if implied else None,
        },
        "note": "Peer multiple is market cap ÷ latest annual revenue (price-to-sales), not EV/Sales; private figures are only shown when the memo states them.",
    }
    with _LOCK:
        _CACHE[company_id] = (time.time(), payload)
    return payload
