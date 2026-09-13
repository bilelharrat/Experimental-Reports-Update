"""Server-side alert evaluation for the market desk.

Browser alerts only fire while the tab is open. This engine evaluates the
same rules (synced into the desk prefs blob as ``alertRules``) against
``live_quotes`` on the server, so alerts fire and are recorded in the desk
store even when no browser is polling.

Rule shape (written by ``frontend/src/marketWatchlist.js``):

    {"id": "...", "ticker": "NVDA", "kind": "pct"|"price"|...,
     "threshold": 5, "direction": "above"|"below", "enabled": true}

The server evaluates the kinds a bare live quote can answer: ``price``
(last print above/below the threshold) and ``pct`` (absolute 1-day move
at least the threshold). Volume/SMA/earnings rules need history the
browser already has, so those stay client-side. Each rule fires at most
once per UTC day (de-dupe key = rule id + day).

Evaluation runs on demand via ``POST /api/alerts/check`` and, when
``BSH_ALERT_ENGINE_INTERVAL`` (seconds) is set, from a daemon thread
started at app startup. The thread is opt-in so tests and offline runs
never touch the network.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

from server import desk_store, live_quotes

logger = logging.getLogger(__name__)

_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


SERVER_KINDS = {"price", "pct"}


def evaluate_rules(rules: list[dict], quotes: dict[str, dict]) -> list[dict]:
    """Pure evaluation: which rules fire against these quotes."""
    fired: list[dict] = []
    day = _today()
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("enabled") is False:
            continue
        kind = str(rule.get("kind") or "").strip().lower()
        if kind not in SERVER_KINDS:
            continue
        ticker = str(rule.get("ticker") or "").strip().upper()
        quote = quotes.get(ticker) or {}
        last = quote.get("last_price")
        change = quote.get("change_pct_1d")
        try:
            threshold = float(rule.get("threshold"))
        except (TypeError, ValueError):
            continue
        rule_id = str(rule.get("id") or f"{ticker}-{kind}-{threshold:g}")
        hit = None
        if kind == "price" and isinstance(last, (int, float)):
            direction = str(rule.get("direction") or "above").lower()
            if direction == "below":
                if last <= threshold:
                    hit = f"{ticker} ≤ {threshold:g} (last {last:g})"
            elif last >= threshold:
                hit = f"{ticker} ≥ {threshold:g} (last {last:g})"
        elif kind == "pct" and isinstance(change, (int, float)):
            if abs(change) >= threshold:
                hit = f"{ticker} moved {change:+.2f}% (≥ {threshold:g}%)"
        if hit is None:
            continue
        fired.append(
            {
                "rule_id": rule_id,
                "ticker": ticker,
                "kind": kind,
                "threshold": threshold,
                "message": hit,
                "last_price": last,
                "change_pct_1d": change,
                "dedupe_key": f"{rule_id}:{day}",
                "source": "server",
            }
        )
    return fired


def run_check() -> dict:
    """Evaluate stored rules against live quotes; record fresh fires."""
    rules = desk_store.alert_rules()
    tickers = sorted(
        {str(rule.get("ticker") or "").strip().upper() for rule in rules if rule.get("ticker")}
    )
    if not tickers:
        return {"checked": 0, "fired": [], "generated_at": None}
    payload = live_quotes.fetch_quotes(tickers)
    quotes = payload.get("quotes") or {}
    fired = evaluate_rules(rules, quotes)
    recorded = desk_store.record_alert_events(fired)
    if recorded:
        try:
            from . import push_notify

            for event in recorded[:5]:
                ticker = str(event.get("ticker") or "").upper()
                message = str(event.get("message") or "Alert fired")
                push_notify.notify(
                    "alert",
                    f"Alert · {ticker}" if ticker else "Desk alert",
                    message,
                    data={
                        "ticker": ticker or None,
                        "deep_link": f"bshresearch://ticker/{ticker}" if ticker else None,
                    },
                )
        except Exception:  # noqa: BLE001
            logger.exception("alert push notify failed")
    return {
        "checked": len(rules),
        "fired": recorded,
        "generated_at": payload.get("generated_at"),
    }


def _loop(interval: float) -> None:
    while not _STOP.wait(interval):
        try:
            run_check()
        except Exception:
            logger.exception("Alert engine check failed")


def start_background_engine() -> bool:
    """Start the polling thread when BSH_ALERT_ENGINE_INTERVAL is set."""
    global _THREAD
    raw = os.environ.get("BSH_ALERT_ENGINE_INTERVAL", "").strip()
    try:
        interval = float(raw) if raw else 0.0
    except ValueError:
        interval = 0.0
    if interval <= 0 or (_THREAD is not None and _THREAD.is_alive()):
        return False
    _STOP.clear()
    _THREAD = threading.Thread(
        target=_loop, args=(max(interval, 30.0),), name="bsh-alert-engine", daemon=True
    )
    _THREAD.start()
    logger.info("Alert engine polling every %.0fs", max(interval, 30.0))
    return True
