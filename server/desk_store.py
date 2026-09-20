"""Durable market-desk state: prefs blob, alert history, signal ledger.

The market desk historically kept everything in browser localStorage —
watchlists, pin groups, book lots, ticker notes, saved desks, alert rules,
chart prefs. One cache clear (or a second machine) and the desk was empty.
This store gives that state a server-side home:

- **Prefs blob** — an opaque JSON object of desk localStorage keys. The
  frontend owns the shape; the server only stamps ``updated_at`` and
  persists it. Alert rules live inside the blob under ``alertRules`` so
  the alert engine can evaluate them while the browser is closed.
  ``updated_at`` is a strictly increasing microsecond stamp that doubles as
  an optional save precondition (``expected_updated_at``), so the web, Mac
  and iPad clients can detect an edit made on another device instead of
  silently overwriting it.
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

import hashlib
import json
import math
import threading
import uuid
from datetime import datetime, timedelta, timezone
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

# Sentinel for "the caller sent no precondition" (distinct from ``None``,
# which means "I last saw an empty store").
_UNSET: Any = object()


class PrefsConflict(Exception):
    """The stored prefs changed since the caller's ``expected_updated_at``."""

    def __init__(self, current_updated_at: str | None):
        super().__init__("desk prefs changed")
        self.current_updated_at = current_updated_at


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utcnow() -> datetime:
    """Wall clock for prefs stamps (a seam tests freeze)."""
    return datetime.now(timezone.utc)


def _parse_stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _next_stamp(current: Any) -> str:
    """A prefs ``updated_at`` strictly later than ``current``.

    Always carries six fractional digits (``isoformat()`` drops the fraction
    when the microsecond is 0, which breaks string comparison), and moves
    forward by one microsecond on a clock tie or a clock that went backwards.
    Legacy stamps without a fraction still parse.
    """
    now = _utcnow()
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    previous = _parse_stamp(current)
    if previous is not None and now <= previous:
        now = previous + timedelta(microseconds=1)
    return now.isoformat(timespec="microseconds").replace("+00:00", "Z")


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
#
# One blob per account, plus the firm's. The blob was a single file for
# everyone, and it holds personal things — recently pinned tickers, alert
# rules, a book of positions — so a second account saw the first one's
# desk. A signed-in caller now reads and writes their own file; the firm
# blob (``prefs.json``) is what the shared-token and anon-dev callers use
# and what the morning brief reads as the firm watchlist. The server-side
# readers that drive alerts, digests and filings watch span every desk,
# which is exactly what they saw when there was only one.


def _owner_key(owner: str | None) -> str | None:
    key = str(owner or "").strip().lower()
    return key or None


def _prefs_file(owner: str | None) -> str:
    key = _owner_key(owner)
    if key is None:
        return PREFS_FILE
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"prefs.{digest}.json"


def _as_prefs(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"updated_at": None, "data": {}}
    data = payload.get("data")
    return {
        "updated_at": payload.get("updated_at"),
        "data": data if isinstance(data, dict) else {},
    }


def load_prefs(owner: str | None = None) -> dict:
    """The desk prefs blob for ``owner`` (the firm's when None), or an empty
    stub when nothing was saved yet."""
    with _LOCK:
        payload = _read_json(_prefs_file(owner), None)
    return _as_prefs(payload)


def _every_desk_data() -> list[dict]:
    """The ``data`` of every desk on disk, the firm's first. Read inline:
    the lock is not reentrant."""
    with _LOCK:
        payloads = [_read_json(PREFS_FILE, None)]
        if DESK_ROOT.exists():
            for path in sorted(DESK_ROOT.glob("prefs.*.json")):
                payloads.append(_read_json(path.name, None))
    return [_as_prefs(p)["data"] for p in payloads]


def adopt_firm_prefs(owner: str) -> bool:
    """Copy the firm blob into ``owner``'s desk if they have none yet — the
    one-off migration for the operator whose desk the firm blob was, under
    anon-dev, before desks were per account. Returns whether it copied."""
    key = _owner_key(owner)
    if key is None:
        return False
    with _LOCK:
        if _read_json(_prefs_file(key), None) is not None:
            return False
        firm = _read_json(PREFS_FILE, None)
        if not isinstance(firm, dict):
            return False
        _write_json(_prefs_file(key), firm)
    return True


ALERT_RULE_KINDS = ("pct", "earnings", "volume", "price", "sma_cross")
ALERT_RULE_DIRECTIONS = ("above", "below")


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_book_lots(lots: Any) -> None:
    if not isinstance(lots, list):
        raise ValueError("bsh.bookLots must be a list")
    for index, lot in enumerate(lots):
        where = f"bsh.bookLots[{index}]"
        if not isinstance(lot, dict):
            raise ValueError(f"{where} must be an object")
        if "shares" not in lot and "qty" not in lot:
            raise ValueError(f"{where} needs shares")
        if "cost" not in lot and "costBasis" not in lot:
            raise ValueError(f"{where} needs cost")
        for field in ("shares", "qty", "cost", "costBasis"):
            if field in lot and not (_is_finite_number(lot[field]) and lot[field] >= 0):
                raise ValueError(f"{where}.{field} must be a finite number >= 0")


def _validate_alert_rules(rules: Any) -> None:
    if not isinstance(rules, list):
        raise ValueError("bsh.marketAlertRules must be a list")
    for index, rule in enumerate(rules):
        where = f"bsh.marketAlertRules[{index}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{where} must be an object")
        kind = rule.get("kind")
        if not isinstance(kind, str) or kind.strip().lower() not in ALERT_RULE_KINDS:
            raise ValueError(f"{where}.kind must be one of {', '.join(ALERT_RULE_KINDS)}")
        if not _is_finite_number(rule.get("threshold")):
            raise ValueError(f"{where}.threshold must be a finite number")
        direction = rule.get("direction")
        if direction is not None and (
            not isinstance(direction, str)
            or direction.strip().lower() not in ALERT_RULE_DIRECTIONS
        ):
            raise ValueError(f"{where}.direction must be one of {', '.join(ALERT_RULE_DIRECTIONS)}")


def _validate_pinned_tickers(tickers: Any) -> None:
    from .live_quotes import TICKER_RE

    if not isinstance(tickers, list):
        raise ValueError("bsh.marketPinnedTickers must be a list")
    for index, ticker in enumerate(tickers):
        if not isinstance(ticker, str) or not TICKER_RE.match(ticker):
            raise ValueError(
                f"bsh.marketPinnedTickers[{index}] must be an upper-case ticker symbol "
                "(letters, digits, '.' or '-')"
            )


_VALIDATED_PREF_KEYS = {
    "bsh.bookLots": _validate_book_lots,
    "bsh.marketAlertRules": _validate_alert_rules,
    "bsh.marketPinnedTickers": _validate_pinned_tickers,
}


def save_prefs(
    data: dict, *, expected_updated_at: Any = _UNSET, owner: str | None = None
) -> dict:
    """Persist the desk prefs blob.

    The frontend owns the key shape; the keys the server itself reads
    (book lots, alert rules, pinned tickers) are validated, every other key
    is stored untouched. Raises ``ValueError`` naming the offending entry.

    ``expected_updated_at`` is an optional precondition: when given (``None``
    meaning "the store was empty when I read it") and it differs from the
    stored ``updated_at``, nothing is written and ``PrefsConflict`` carries
    the current stamp. Validation runs first, so a bad payload is always a
    ``ValueError`` even when the precondition is stale too. Omitting it keeps
    the unconditional save.
    """
    if not isinstance(data, dict):
        raise ValueError("prefs payload must be an object")
    for key, validate in _VALIDATED_PREF_KEYS.items():
        if key in data:
            validate(data[key])
    encoded = json.dumps(data, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_PREFS_BYTES:
        raise ValueError("prefs payload too large")
    name = _prefs_file(owner)
    with _LOCK:
        # Compare-and-write under one lock hold. Read inline: _LOCK is not
        # reentrant, so load_prefs() here would deadlock.
        stored = _read_json(name, None)
        current = stored.get("updated_at") if isinstance(stored, dict) else None
        if expected_updated_at is not _UNSET and expected_updated_at != current:
            raise PrefsConflict(current)
        payload = {"updated_at": _next_stamp(current), "data": data}
        _write_json(name, payload)
    return payload


def alert_rules() -> list[dict]:
    """Alert rules from the synced prefs blob.

    The frontend mirrors desk localStorage into the blob keyed by the
    original storage keys, so rules live under ``bsh.marketAlertRules``
    (same shape ``marketWatchlist.js`` writes).
    """
    # Deduped by id: the operator's desk was adopted from the firm blob, so
    # the same rule can sit in both, and one rule must fire once.
    out: list[dict] = []
    seen: set[str] = set()
    for data in _every_desk_data():
        rules = data.get("bsh.marketAlertRules")
        if not isinstance(rules, list):
            continue
        for row in rules:
            if not isinstance(row, dict):
                continue
            rule_id = str(row.get("id") or "")
            if rule_id and rule_id in seen:
                continue
            if rule_id:
                seen.add(rule_id)
            out.append(row)
    return out


def pinned_tickers() -> list[str]:
    """Watchlist tickers from the synced prefs blob."""
    out: list[str] = []
    for data in _every_desk_data():
        raw = data.get("bsh.marketPinnedTickers")
        if not isinstance(raw, list):
            continue
        for item in raw:
            ticker = str(item or "").strip().upper()
            if ticker and ticker not in out:
                out.append(ticker)
    return out


def book_lots() -> list[dict]:
    """Position lots from the synced prefs blob (``bsh.bookLots``)."""
    out: list[dict] = []
    for data in _every_desk_data():
        raw = data.get("bsh.bookLots")
        if isinstance(raw, list):
            out.extend(row for row in raw if isinstance(row, dict))
    return out


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

    A duplicate (same ticker, direction and label on the same UTC day) is not
    re-recorded; the existing row comes back with ``deduplicated`` True so the
    caller can say so instead of reporting a fresh entry.
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
                and str(existing.get("direction") or "watch") == direction
                and str(existing.get("recorded_at") or "")[:10] == day
            ):
                return dict(existing, deduplicated=True)
        rows.append(row)
        _write_json(SIGNALS_FILE, rows[-MAX_SIGNALS:])
    return dict(row, deduplicated=False)


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
