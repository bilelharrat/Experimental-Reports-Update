"""Tiny file-based TTL cache.

Keyed by an arbitrary string (we hash it for the filename so weird query
strings can't blow up the filesystem).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import yaml

from .storage import DATA_DIR

CACHE_ROOT = DATA_DIR / "cache"


def _path(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return CACHE_ROOT / namespace / f"{digest}.yaml"


def get(namespace: str, key: str, ttl_seconds: int) -> Any | None:
    p = _path(namespace, key)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            entry = yaml.safe_load(f) or {}
    except Exception:
        return None
    stored_at = float(entry.get("stored_at", 0))
    if time.time() - stored_at > ttl_seconds:
        return None
    return entry.get("value")


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
