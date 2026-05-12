"""Storage for external news, external research, and Hormuz research items.

Each kind lives under its own subdirectory of `data/external/<kind>/` with one
YAML per item. Archived HTML for news items is stored alongside as
`<id>.html`, with downloaded image assets in `<id>.assets/`. Uploaded research
files reuse `data/uploads/_external/` so the existing FileResponse plumbing
works.

Item shapes (any field may be missing):
- news:           id, kind, status, title, source_url, archive_path,
                  captured_at, summary, key_points, language, translation,
                  raw_text_chars
- external_research: id, kind, status, title, file_id, source_company,
                     contact_name, contact_email, captured_at, summary,
                     key_points, language, translation, raw_text_chars
- hormuz_research:  id, kind, status, title, body, captured_at,
                    file_id (optional), summary
"""
from __future__ import annotations

import threading
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .storage import DATA_DIR

EXTERNAL_ROOT = DATA_DIR / "external"

KINDS = ("news", "external_research", "hormuz_research")

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kind_dir(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"Unknown kind: {kind}")
    return EXTERNAL_ROOT / kind


def _path(kind: str, item_id: str) -> Path:
    return _kind_dir(kind) / f"{item_id}.yaml"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def list_items(kind: str) -> list[dict]:
    d = _kind_dir(kind)
    if not d.exists():
        return []
    out: list[dict] = []
    for p in d.glob("*.yaml"):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue
        if isinstance(data, dict):
            out.append(data)
    out.sort(key=lambda r: str(r.get("captured_at", "")), reverse=True)
    return out


def list_news_and_research() -> list[dict]:
    """Combined feed for the 'External Research and News' sidebar section."""
    items = list_items("news") + list_items("external_research")
    items.sort(key=lambda r: str(r.get("captured_at", "")), reverse=True)
    return items


def get_item(kind: str, item_id: str) -> dict | None:
    p = _path(kind, item_id)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write_item(kind: str, data: dict) -> dict:
    """Atomically write/replace an item record."""
    item_id = data.get("id")
    if not item_id:
        raise ValueError("Item missing id")
    data.setdefault("kind", kind)
    data.setdefault("captured_at", _now())
    data["updated_at"] = _now()
    with _LOCK:
        d = _kind_dir(kind)
        d.mkdir(parents=True, exist_ok=True)
        p = _path(kind, item_id)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        tmp.replace(p)
    return data


def update_item(kind: str, item_id: str, **patch: Any) -> dict | None:
    """Merge `patch` into the existing item. Returns updated record or None."""
    with _LOCK:
        existing = get_item(kind, item_id)
        if existing is None:
            return None
        existing.update(patch)
        return write_item(kind, existing)


def delete_item(kind: str, item_id: str) -> bool:
    p = _path(kind, item_id)
    if not p.exists():
        return False
    archive = _kind_dir(kind) / f"{item_id}.html"
    assets = archive_asset_dir(kind, item_id)
    try:
        p.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        shutil.rmtree(assets, ignore_errors=True)
    except Exception:
        return False
    return True


def archive_path(kind: str, item_id: str) -> Path:
    return _kind_dir(kind) / f"{item_id}.html"


def archive_asset_dir(kind: str, item_id: str) -> Path:
    return _kind_dir(kind) / f"{item_id}.assets"


def archive_asset_path(kind: str, item_id: str, filename: str) -> Path:
    return archive_asset_dir(kind, item_id) / filename


def write_archive(kind: str, item_id: str, html: str) -> Path:
    p = archive_path(kind, item_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(p)
    return p
