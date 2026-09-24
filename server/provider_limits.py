"""A process-wide "Claude is limited until <reset>" record.

Memo runs, Warren and the translation backfill all learn about a provider
usage limit the expensive way: a spawned CLI fails with "usage limit
reached … resets 3pm". This module keeps that knowledge after the failing
call returns, so the report pre-flight (GET /api/reports/readiness) can say
"Claude is limited until 15:00" without spending anything to find out.

The record lives in ``data/_api/provider_limits.json`` (resolved at call
time) so a restart during a limit still knows about it. Every entry
expires: at the parsed reset time, or ``DEFAULT_LIMIT_MINUTES`` after it was
recorded when the message carried no reset time. It is advisory only —
nothing refuses a run because of it; a stale record can therefore cost a
warning, never a blocked memo.

Writers (the pipeline, Warren) call ``record_provider_limit``; a later
successful call may call ``clear_provider_limit``.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import storage

DEFAULT_LIMIT_MINUTES = 30
# A parsed reset further out than this is not trusted (a weekly limit is
# the longest window the CLI reports).
MAX_LIMIT_HOURS = 7 * 24

_LOCK = threading.RLock()


def _path() -> Path:
    return storage.DATA_DIR / "_api" / "provider_limits.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read() -> dict[str, dict]:
    path = _path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(payload: dict[str, dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _coerce_reset(value: Any, now: datetime) -> datetime | None:
    """A reset given as a datetime, an epoch (seconds or milliseconds, as the
    CLI's rate_limit_event ``resetsAt`` carries) or an ISO string."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 1e12:  # milliseconds
            seconds /= 1000.0
        if seconds <= 0:
            return None
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if re.fullmatch(r"\d{9,13}(?:\.\d+)?", text):
        return _coerce_reset(float(text), now)
    return _parse_iso(text)


_UNIT_SECONDS = (
    ("d", 86400),
    ("h", 3600),
    ("m", 60),
    ("s", 1),
)


def parse_reset_text(text: str, *, now: datetime | None = None) -> datetime | None:
    """Parse provider wording such as "resets in 2 hr 44 min", "retry after
    120" or "resets 3pm (America/Los_Angeles)" into an absolute time."""
    if not text:
        return None
    now = now or _now()
    lowered = text.lower()
    retry_after = re.search(r"retry[-\s]?after[:=\s]+(\d+)", lowered)
    if retry_after:
        return now + timedelta(seconds=int(retry_after.group(1)))
    marker = re.search(r"(?:resets?|retry|try again|available again)\s+in\s+", lowered)
    if marker:
        window = lowered[marker.end(): marker.end() + 80]
        total = 0.0
        for raw, unit in re.findall(
            r"(\d+(?:\.\d+)?)\s*"
            r"(days?|d|hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)\b",
            window,
        ):
            for prefix, seconds in _UNIT_SECONDS:
                if unit.startswith(prefix):
                    total += float(raw) * seconds
                    break
        if total > 0:
            return now + timedelta(seconds=total)
    reset_at = re.search(
        r"(?:resets?|reset)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)(?:\s*\(([^)]+)\))?",
        text,
        re.IGNORECASE,
    )
    if reset_at:
        hour = int(reset_at.group(1))
        minute = int(reset_at.group(2) or "0")
        meridiem = reset_at.group(3).lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        zone = timezone.utc
        tz_name = reset_at.group(4)
        if tz_name:
            try:
                from zoneinfo import ZoneInfo

                zone = ZoneInfo(tz_name.strip())
            except Exception:  # noqa: BLE001 — unknown zone: read it as UTC
                zone = timezone.utc
        local_now = now.astimezone(zone)
        candidate = local_now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    return None


def record_provider_limit(
    reason: str | None,
    reset_at: Any = None,
    *,
    provider: str = "claude",
    source: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Remember that ``provider`` hit a usage limit.

    ``reset_at`` may be a datetime, an epoch or an ISO string; when absent
    the reset is parsed from ``reason``, and when that fails the record
    expires ``DEFAULT_LIMIT_MINUTES`` from now. Returns the stored entry.
    Never raises on bad input — a limit record must not sink its caller.
    """
    now = now or _now()
    reset = _coerce_reset(reset_at, now) or parse_reset_text(str(reason or ""), now=now)
    parsed = reset is not None and reset > now
    if not parsed:
        reset = now + timedelta(minutes=DEFAULT_LIMIT_MINUTES)
    reset = min(reset, now + timedelta(hours=MAX_LIMIT_HOURS))
    entry = {
        "provider": str(provider or "claude"),
        "reason": str(reason or "").strip()[:500],
        "reset_at": _iso(reset),
        "reset_parsed": parsed,
        "recorded_at": _iso(now),
        "source": source,
    }
    try:
        with _LOCK:
            payload = _read()
            payload[entry["provider"]] = entry
            _write(payload)
    except OSError:
        pass
    return entry


def clear_provider_limit(provider: str = "claude") -> bool:
    """Forget a recorded limit (a later call succeeded, or an operator
    override). Returns True when there was one."""
    try:
        with _LOCK:
            payload = _read()
            if provider not in payload:
                return False
            payload.pop(provider, None)
            _write(payload)
            return True
    except OSError:
        return False


def current_limit(provider: str = "claude", *, now: datetime | None = None) -> dict | None:
    """The live limit for ``provider``, or None when none is recorded or the
    recorded one has expired."""
    now = now or _now()
    with _LOCK:
        entry = _read().get(provider)
    if not isinstance(entry, dict):
        return None
    reset = _parse_iso(entry.get("reset_at"))
    if reset is None or reset <= now:
        return None
    return {**entry, "seconds_remaining": int((reset - now).total_seconds())}


def all_limits(*, now: datetime | None = None) -> dict[str, dict]:
    now = now or _now()
    with _LOCK:
        providers = list(_read())
    out: dict[str, dict] = {}
    for provider in providers:
        entry = current_limit(provider, now=now)
        if entry:
            out[provider] = entry
    return out
