"""Durable market-desk state: prefs blob, alert history, signal ledger.

The market desk historically kept everything in browser localStorage —
watchlists, pin groups, book lots, ticker notes, saved desks, alert rules,
chart prefs. One cache clear (or a second machine) and the desk was empty.
This store gives that state a server-side home:

- **Prefs blob** — an opaque JSON object of desk localStorage keys. The
  frontend owns the shape; the server only stamps ``updated_at`` and
  persists it. Alert rules live inside the blob under ``alertRules`` so
  the alert engine can evaluate them while the browser is closed.
- **Alert events** — fired alerts recorded by the alert engine (or the
  browser) with a de-dupe key, so "what fired while I was away" survives
  reloads and devices.
- **Signal ledger** — point-in-time signal records (ticker, direction,
  price at signal) that later get scored against live prices. This is the
  outcome loop for Pulse/Signals calls.

Everything lives under ``data/market_desk/`` as small JSON documents with
a module lock; write volume is tiny (one analyst).
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DESK_ROOT = Path(__file__).resolve().parent.parent / "data" / "market_desk"

PREFS_FILE = "prefs.json"
ALERTS_FILE = "alert_events.json"
SIGNALS_FILE = "signal_ledger.json"

MAX_ALERT_EVENTS = 500
MAX_SIGNALS = 500
MAX_PREFS_BYTES = 512 * 1024

_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _path(name: str) -> Path:
    return DESK_ROOT / name


def _read_json(name: str, default: Any) -> Any:
    path = _path(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(name: str, payload: Any) -> None:
    DESK_ROOT.mkdir(parents=True, exist_ok=True)
    path = _path(name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# --- Prefs blob -------------------------------------------------------------


def load_prefs() -> dict:
    """The desk prefs blob, or an empty stub when nothing was saved yet."""
    with _LOCK:
        payload = _read_json(PREFS_FILE, None)
    if not isinstance(payload, dict):
        return {"updated_at": None, "data": {}}
    data = payload.get("data")
    return {
        "updated_at": payload.get("updated_at"),
        "data": data if isinstance(data, dict) else {},
    }


def save_prefs(data: dict) -> dict:
    """Persist the desk prefs blob. The frontend owns the key shape."""
    if not isinstance(data, dict):
        raise ValueError("prefs payload must be an object")
    encoded = json.dumps(data, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_PREFS_BYTES:
        raise ValueError("prefs payload too large")
    payload = {"updated_at": _now_iso(), "data": data}
    with _LOCK:
        _write_json(PREFS_FILE, payload)
    return payload


def alert_rules() -> list[dict]:
    """Alert rules from the synced prefs blob.

    The frontend mirrors desk localStorage into the blob keyed by the
    original storage keys, so rules live under ``bsh.marketAlertRules``
    (same shape ``marketWatchlist.js`` writes).
    """
    rules = load_prefs()["data"].get("bsh.marketAlertRules")
    return [row for row in rules if isinstance(row, dict)] if isinstance(rules, list) else []


def pinned_tickers() -> list[str]:
    """Watchlist tickers from the synced prefs blob."""
    raw = load_prefs()["data"].get("bsh.marketPinnedTickers")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        ticker = str(item or "").strip().upper()
        if ticker and ticker not in out:
            out.append(ticker)
    return out


def book_lots() -> list[dict]:
    """Position lots from the synced prefs blob (``bsh.bookLots``)."""
    raw = load_prefs()["data"].get("bsh.bookLots")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


# --- Alert events -----------------------------------------------------------


def list_alert_events(since: str | None = None, limit: int = 100) -> list[dict]:
    """Fired alerts, newest first. ``since`` filters by ``fired_at``."""
    with _LOCK:
        rows = _read_json(ALERTS_FILE, [])
    if not isinstance(rows, list):
        return []
    events = [row for row in rows if isinstance(row, dict)]
    if since:
        events = [row for row in events if str(row.get("fired_at") or "") > since]
    events.sort(key=lambda row: str(row.get("fired_at") or ""), reverse=True)
    return events[: max(1, min(limit, MAX_ALERT_EVENTS))]


def record_alert_events(rows: list[dict]) -> list[dict]:
    """Append fired alerts, de-duped on ``dedupe_key``. Returns new rows."""
    stamped: list[dict] = []
    with _LOCK:
        existing = _read_json(ALERTS_FILE, [])
        if not isinstance(existing, list):
            existing = []
        seen = {
            str(row.get("dedupe_key"))
            for row in existing
            if isinstance(row, dict) and row.get("dedupe_key")
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("dedupe_key") or "") or uuid.uuid4().hex
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "id": uuid.uuid4().hex[:12],
                "fired_at": _now_iso(),
                **row,
                "dedupe_key": key,
            }
            stamped.append(entry)
        if stamped:
            merged = existing + stamped
            merged.sort(key=lambda r: str(r.get("fired_at") or ""))
            _write_json(ALERTS_FILE, merged[-MAX_ALERT_EVENTS:])
    return stamped


# --- Signal ledger ----------------------------------------------------------


def list_signals() -> list[dict]:
    """Ledger entries, newest first."""
    with _LOCK:
        rows = _read_json(SIGNALS_FILE, [])
    if not isinstance(rows, list):
        return []
    entries = [row for row in rows if isinstance(row, dict)]
    entries.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
    return entries


def record_signal(entry: dict) -> dict:
    """Record one signal call (ticker, direction, label, price at signal).

    Duplicate ticker+label pairs recorded on the same UTC day are rejected
    so a re-render doesn't double-book the same call.
    """
    ticker = str(entry.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    direction = str(entry.get("direction") or "watch").strip().lower()
    if direction not in {"bullish", "bearish", "watch"}:
        direction = "watch"
    price = entry.get("price_at_signal")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    recorded_at = _now_iso()
    day = recorded_at[:10]
    label = str(entry.get("label") or "").strip()[:300]
    row = {
        "id": uuid.uuid4().hex[:12],
        "recorded_at": recorded_at,
        "ticker": ticker,
        "direction": direction,
        "label": label,
        "source": str(entry.get("source") or "manual")[:40],
        "price_at_signal": price,
    }
    with _LOCK:
        rows = _read_json(SIGNALS_FILE, [])
        if not isinstance(rows, list):
            rows = []
        for existing in rows:
            if not isinstance(existing, dict):
                continue
            if (
                str(existing.get("ticker")) == ticker
                and str(existing.get("label") or "") == label
                and str(existing.get("recorded_at") or "")[:10] == day
            ):
                return existing
        rows.append(row)
        _write_json(SIGNALS_FILE, rows[-MAX_SIGNALS:])
    return row


def delete_signal(signal_id: str) -> bool:
    with _LOCK:
        rows = _read_json(SIGNALS_FILE, [])
        if not isinstance(rows, list):
            return False
        kept = [row for row in rows if not (isinstance(row, dict) and row.get("id") == signal_id)]
        if len(kept) == len(rows):
            return False
        _write_json(SIGNALS_FILE, kept)
    return True


def score_signals(quotes: dict[str, dict]) -> list[dict]:
    """Attach live-price outcomes to ledger entries.

    ``quotes`` maps ticker -> live quote (``last_price``). Adds
    ``last_price``, ``return_since_pct`` (signed, direction-agnostic) and
    ``score_pct`` (positive when the call was right: bearish calls invert).
    Entries without a recorded price or live quote pass through unscored.
    """
    scored: list[dict] = []
    for row in list_signals():
        entry = dict(row)
        quote = quotes.get(str(row.get("ticker") or "")) or {}
        last = quote.get("last_price")
        base = row.get("price_at_signal")
        try:
            last = float(last) if last is not None else None
            base = float(base) if base is not None else None
        except (TypeError, ValueError):
            last = base = None
        if last is not None and base:
            move = (last - base) / base * 100
            entry["last_price"] = last
            entry["return_since_pct"] = move
            direction = str(row.get("direction") or "watch")
            if direction == "bearish":
                entry["score_pct"] = -move
            elif direction == "bullish":
                entry["score_pct"] = move
        scored.append(entry)
    return scored
