"""File-based persistent cache with timestamps.

Entries are kept indefinitely (so deep-search results survive restarts and
TTL changes). Each entry records `stored_at` so callers can decide whether
they consider the value stale; nothing is auto-evicted.

Keys are hashed for the filename so weird query strings can't blow up the
filesystem.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .storage import DATA_DIR

CACHE_ROOT = DATA_DIR / "cache"


def _path(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return CACHE_ROOT / namespace / f"{digest}.yaml"


def _read_entry(namespace: str, key: str) -> dict | None:
    p = _path(namespace, key)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            entry = yaml.safe_load(f) or {}
    except Exception:
        return None
    return entry if isinstance(entry, dict) else None


def get(namespace: str, key: str) -> dict | None:
    """Return the cached entry as `{value, stored_at, stored_at_iso}` or None.

    No TTL — this returns whatever was last written. Callers decide what to
    do with the age.
    """
    entry = _read_entry(namespace, key)
    if entry is None:
        return None
    stored_at = float(entry.get("stored_at", 0))
    return {
        "value": entry.get("value"),
        "stored_at": stored_at,
        "stored_at_iso": datetime.fromtimestamp(stored_at, tz=timezone.utc).isoformat()
        if stored_at
        else None,
    }


def put(namespace: str, key: str, value: Any) -> None:
    p = _path(namespace, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"key": key, "stored_at": time.time(), "value": value},
            f,
            sort_keys=False,
            allow_unicode=True,
        )
    tmp.replace(p)


def invalidate(namespace: str, key: str) -> None:
    p = _path(namespace, key)
    p.unlink(missing_ok=True)
