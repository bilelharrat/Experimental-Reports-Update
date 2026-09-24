"""Deal Pipeline & Affinity-grade Relationship Warmth Engine.

Tracks institutional VC deal progression (Sourced -> Intro -> Tech DD ->
Term Sheet -> Portfolio), warm intro paths, and relationship scores.

Reads never write: a missing or unreadable file yields the default record in
the response only. ``days_in_stage`` is derived from ``stage_changed_at`` on
every read, so clients cannot set it.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()

STAGES = [
    "Sourced",
    "Partner Intro",
    "Technical Diligence",
    "Term Sheet / IC",
    "Portfolio",
]

TEXT_FIELDS = {"deal_lead": 200, "intro_path": 1000, "last_touchpoint": 1000, "next_step": 1000}

# Proposed deal terms (optional): what the memo may say about the vehicle,
# price and check. Absent terms mean "no terms on file", and the memo must
# not assert any (memo_inputs stages them as deal_terms.md).
TERM_TEXT_FIELDS = {"round": 120, "instrument": 120, "terms_note": 1000}
TERM_MONEY_FIELDS = ("pre_money_usd", "post_money_usd", "proposed_check_usd")
TERM_FIELDS = tuple(TERM_TEXT_FIELDS) + TERM_MONEY_FIELDS

ALLOWED_UPDATE_KEYS = {
    "stage",
    "deal_lead",
    "warmth_score",
    "intro_path",
    "last_touchpoint",
    "next_step",
    "next_step_due",
    *TERM_FIELDS,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pipeline_path(company_id: str) -> Path:
    return storage.DATA_DIR / "deal_pipeline" / f"{company_id}.json"


def company_exists(company_id: str) -> bool:
    return storage.get_company(company_id) is not None


def require_company(company_id: str) -> None:
    if not company_exists(company_id):
        raise LookupError("Company not found")


def _default(company_id: str) -> dict:
    company = storage.get_company(company_id) or {}
    status = str(company.get("status") or "").lower()
    now = _now()
    return {
        "company_id": company_id,
        "stage": "Portfolio" if status == "portfolio" else STAGES[0],
        "stages": STAGES,
        "deal_lead": None,
        "warmth_score": None,
        "intro_path": None,
        "days_in_stage": 0,
        "last_touchpoint": None,
        "next_step": None,
        # A calendar date (YYYY-MM-DD) the next step is due by, or None.
        "next_step_due": None,
        # Proposed terms (all optional): round, instrument, pre/post-money
        # and the proposed check in USD, plus a free-text note.
        **{key: None for key in TERM_FIELDS},
        "stage_changed_at": now,
        "updated_at": now,
    }


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_ts(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _warmth(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("warmth_score must be a whole number from 0 to 100 or null")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("warmth_score must be a whole number from 0 to 100 or null") from None
    if not math.isfinite(number) or not number.is_integer() or not 0 <= number <= 100:
        raise ValueError("warmth_score must be a whole number from 0 to 100 or null")
    return int(number)


def _text(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value.strip()[: TEXT_FIELDS[key]] or None


def _money(key: str, value: Any) -> float | None:
    """A USD amount (>= 0) or null; "$24M"-style text is not accepted —
    the UI sends numbers."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number of US dollars or null")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number of US dollars or null") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{key} must be a number of US dollars or null")
    return int(number) if number.is_integer() else number


def _term_text(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value.strip()[: TERM_TEXT_FIELDS[key]] or None


def _due(value: Any) -> str | None:
    """A next-step due date: ``YYYY-MM-DD`` or null."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError:
        raise ValueError("next_step_due must be a date (YYYY-MM-DD) or null") from None


def _validate(updates: dict) -> dict:
    clean: dict[str, Any] = {}
    for key, value in (updates or {}).items():
        if key not in ALLOWED_UPDATE_KEYS:
            continue
        if key == "stage":
            if value not in STAGES:
                raise ValueError(f"stage must be one of {', '.join(STAGES)}")
            clean[key] = value
        elif key == "warmth_score":
            clean[key] = _warmth(value)
        elif key == "next_step_due":
            clean[key] = _due(value)
        elif key in TERM_MONEY_FIELDS:
            clean[key] = _money(key, value)
        elif key in TERM_TEXT_FIELDS:
            clean[key] = _term_text(key, value)
        else:
            clean[key] = _text(key, value)
    return clean


def _sanitize(record: dict, company_id: str) -> dict:
    """A stored record with any invalid field replaced by its default."""
    base = _default(company_id)
    if not isinstance(record, dict):
        return base
    out = dict(base)
    if record.get("stage") in STAGES:
        out["stage"] = record["stage"]
    try:
        out["warmth_score"] = _warmth(record.get("warmth_score"))
    except ValueError:
        out["warmth_score"] = None
    for key in TEXT_FIELDS:
        value = record.get(key)
        out[key] = (value.strip()[: TEXT_FIELDS[key]] or None) if isinstance(value, str) else None
    try:
        out["next_step_due"] = _due(record.get("next_step_due"))
    except ValueError:
        out["next_step_due"] = None
    for key in TERM_MONEY_FIELDS:
        try:
            out[key] = _money(key, record.get(key))
        except ValueError:
            out[key] = None
    for key in TERM_TEXT_FIELDS:
        try:
            out[key] = _term_text(key, record.get(key))
        except ValueError:
            out[key] = None
    updated = _parse_ts(record.get("updated_at"))
    out["updated_at"] = updated.isoformat() if updated else base["updated_at"]
    changed = _parse_ts(record.get("stage_changed_at")) or updated
    out["stage_changed_at"] = changed.isoformat() if changed else base["stage_changed_at"]
    return out


def _with_days_in_stage(record: dict) -> dict:
    now = datetime.now(timezone.utc)
    changed = _parse_ts(record.get("stage_changed_at"))
    days = (now - changed).days if changed else 0
    record["days_in_stage"] = max(0, days)
    # A next step past its due date is the pipeline's one actionable alarm.
    due = record.get("next_step_due")
    record["next_step_overdue"] = bool(
        record.get("next_step") and due and date.fromisoformat(due) < now.date()
    )
    return record


def _read(company_id: str) -> dict | None:
    """The stored record, ``None`` when there is none; raises on an unreadable file."""
    path = _pipeline_path(company_id)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return json.loads(raw)


def get_deal_pipeline(company_id: str) -> dict:
    try:
        stored = _read(company_id)
    except (OSError, ValueError) as exc:
        logger.warning("Failed to read deal pipeline for %s: %s", company_id, exc)
        stored = None
    return _with_days_in_stage(_sanitize(stored, company_id) if stored is not None else _default(company_id))


def update_deal_pipeline(company_id: str, updates: dict) -> dict:
    clean = _validate(updates)
    if not company_exists(company_id):
        raise ValueError("Company not found")
    path = _pipeline_path(company_id)
    with _LOCK:
        try:
            stored = _read(company_id)
        except (OSError, ValueError) as exc:
            aside = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            logger.warning("Deal pipeline for %s unreadable (%s); moving it aside to %s", company_id, exc, aside)
            path.replace(aside)
            stored = None
        current = _sanitize(stored, company_id) if stored is not None else _default(company_id)
        now = _now()
        if "stage" in clean and clean["stage"] != current["stage"]:
            current["stage_changed_at"] = now
        current.update(clean)
        # A due date belongs to a next step; clearing the step clears it.
        if "next_step" in clean and clean["next_step"] is None:
            current["next_step_due"] = None
        current["updated_at"] = now
        _write_atomic(path, current)
    return _with_days_in_stage(current)
