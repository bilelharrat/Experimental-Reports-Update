"""One cadence registry for every background job that spends tokens.

Owner policy (2026-09-15): nothing that calls Claude on its own may pick
its own schedule. Every such job is a *channel* here, and every channel
offers the same five choices — manual, every 6 hours, every 12 hours,
daily, every 3 days. The UI renders one segmented bar per channel.

Two rules follow from "prevent token spend on the start of the server":

1. ``manual`` means the loop never fires. The user's button still works.
2. A channel that has never run is **not** due at once. Its clock starts
   at first sight, so a fresh server waits a full interval before it
   spends anything.

Every channel is MANUAL by default (owner, 2026-09-15): nothing spends on
a schedule until someone turns that schedule on. A stored choice always
wins; failing that, the channel's legacy env var still supplies a default,
so a deployment that deliberately set one keeps it.

Settings live in ``data/settings/auto_update.json``; each channel keeps
its own last-run clock in its own module and registers it here.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server import storage

logger = logging.getLogger(__name__)

# The bar, in display order. Values are hours; manual never fires.
CADENCE_HOURS: dict[str, float] = {
    "manual": 0.0,
    "6h": 6.0,
    "12h": 12.0,
    "1d": 24.0,
    "3d": 72.0,
}
CADENCES: tuple[str, ...] = tuple(CADENCE_HOURS)
# A legacy env var may name an interval that is not on the bar.
CUSTOM = "custom"

_LOCK = threading.Lock()
_CLOCKS: dict[str, Callable[[], datetime | None]] = {}


@dataclass(frozen=True)
class Channel:
    """One background job that spends tokens on a schedule."""

    id: str
    label_en: str
    label_zh: str
    description_en: str
    description_zh: str
    default_cadence: str
    env_var: str
    env_unit: str  # "hours" or "seconds"


CHANNELS: dict[str, Channel] = {
    "news_brief": Channel(
        id="news_brief",
        label_en="News briefs",
        label_zh="新闻简报",
        description_en="AI briefings for the top headlines on the News page.",
        description_zh="新闻页头条的 AI 简报。",
        default_cadence="manual",
        env_var="BSH_NEWS_BRIEF_REFRESH_HOURS",
        env_unit="hours",
    ),
    "tracked_news": Channel(
        id="tracked_news",
        label_en="Tracked company updates",
        label_zh="追踪公司动态",
        description_en=(
            "News sweep and impact analysis for every tracked company."
        ),
        description_zh="对每家追踪公司做新闻扫描与影响分析。",
        default_cadence="manual",
        env_var="BSH_TRACKING_SYNC_INTERVAL_SECONDS",
        env_unit="seconds",
    ),
}


def _settings_path() -> Path:
    return storage.DATA_DIR / "settings" / "auto_update.json"


def _read_settings() -> dict:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unreadable auto-update settings %s: %s", path.name, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(payload: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def channel(channel_id: str) -> Channel:
    try:
        return CHANNELS[str(channel_id)]
    except KeyError:
        raise KeyError(f"unknown auto-update channel: {channel_id!r}") from None


def normalize_cadence(value: str | None) -> str | None:
    """A value from the bar, or None when it is not one of the five."""
    text = str(value or "").strip().lower()
    return text if text in CADENCE_HOURS else None


def _env_hours(spec: Channel) -> float | None:
    """The legacy env var as hours, or None when it is unset or unusable."""
    raw = str(os.environ.get(spec.env_var) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return value / 3600.0 if spec.env_unit == "seconds" else value


def interval_hours(channel_id: str) -> float:
    """Hours between runs. ``0`` means manual — the loop never fires."""
    spec = channel(channel_id)
    stored = normalize_cadence(_read_settings().get(spec.id, {}).get("cadence"))
    if stored is not None:
        return CADENCE_HOURS[stored]
    env = _env_hours(spec)
    if env is not None:
        return env
    return CADENCE_HOURS[spec.default_cadence]


def cadence(channel_id: str) -> str:
    """Which segment of the bar is lit: a cadence name, or ``custom``."""
    spec = channel(channel_id)
    stored = normalize_cadence(_read_settings().get(spec.id, {}).get("cadence"))
    if stored is not None:
        return stored
    hours = interval_hours(spec.id)
    for name, value in CADENCE_HOURS.items():
        if abs(value - hours) < 1e-9:
            return name
    return CUSTOM


def set_cadence(
    channel_id: str, value: str, *, updated_by: str | None = None
) -> dict:
    """Store a choice from the bar. Takes effect without a restart."""
    spec = channel(channel_id)
    chosen = normalize_cadence(value)
    if chosen is None:
        raise ValueError(
            f"cadence must be one of {', '.join(CADENCES)}; got {value!r}"
        )
    with _LOCK:
        settings = _read_settings()
        settings[spec.id] = {
            "cadence": chosen,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        _write_settings(settings)
    return describe(spec.id)


def register_clock(
    channel_id: str, last_run: Callable[[], datetime | None]
) -> None:
    """A channel's module hands over its persisted last-run clock."""
    _CLOCKS[channel(channel_id).id] = last_run


def last_run_at(channel_id: str) -> datetime | None:
    fn = _CLOCKS.get(channel(channel_id).id)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001 — a broken clock never blocks the API
        logger.exception("auto-update clock failed for %s", channel_id)
        return None


def next_run_at(channel_id: str) -> datetime | None:
    """When the schedule next fires, or None when it is manual.

    A channel that has never run waits a full interval, so restarting the
    server never triggers a round of spending."""
    hours = interval_hours(channel_id)
    if hours <= 0:
        return None
    last = last_run_at(channel_id)
    base = last if last is not None else datetime.now(timezone.utc)
    return base + timedelta(hours=hours)


def seconds_until_due(channel_id: str) -> float | None:
    """Seconds until the next run; None when the channel is manual."""
    due = next_run_at(channel_id)
    if due is None:
        return None
    return (due - datetime.now(timezone.utc)).total_seconds()


def describe(channel_id: str) -> dict:
    """One channel, shaped for the settings bar in the UI."""
    spec = channel(channel_id)
    stored = _read_settings().get(spec.id, {})
    last = last_run_at(spec.id)
    due = next_run_at(spec.id)
    return {
        "id": spec.id,
        "label": {"en": spec.label_en, "zh": spec.label_zh},
        "description": {"en": spec.description_en, "zh": spec.description_zh},
        "cadence": cadence(spec.id),
        "interval_hours": round(interval_hours(spec.id), 4),
        "choices": list(CADENCES),
        "last_run_at": last.isoformat() if last else None,
        "next_run_at": due.isoformat() if due else None,
        "updated_at": stored.get("updated_at"),
        "updated_by": stored.get("updated_by"),
    }


def list_channels() -> list[dict]:
    return [describe(cid) for cid in CHANNELS]


def reset_state_for_tests() -> None:
    """Forget stored choices and registered clocks (tests only)."""
    with _LOCK:
        path = _settings_path()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("auto-update settings reset failed")
