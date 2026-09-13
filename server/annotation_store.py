"""Account-scoped memo ink annotations (PKDrawing + web PNG overlay).

Persists freehand annotations per ``(account_key, report_id)`` under
``data/report_annotations/`` so the same login sees ink on web, iPhone, and
iPad. Apple clients own the PencilKit blob; web clients render the exported
PNG overlay. Conflict policy is last-write-wins stamped with ``updated_at``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

ANNOTATIONS_ROOT = storage.DATA_DIR / "report_annotations"

MAX_DRAWING_BYTES = 8 * 1024 * 1024
MAX_OVERLAY_BYTES = 12 * 1024 * 1024

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def account_key(email: str | None) -> str:
    """Stable folder key for the signed-in account (or shared workspace)."""
    cleaned = (email or "").strip().lower()
    if not cleaned:
        return "shared"
    safe = re.sub(r"[^a-z0-9._@+-]+", "_", cleaned)
    return safe[:180] or "shared"


def _safe_report_id(report_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(report_id or "").strip())
    if not cleaned:
        raise ValueError("Invalid report id")
    return cleaned[:200]


def _dir(account: str, report_id: str) -> Path:
    return ANNOTATIONS_ROOT / account_key(account) / _safe_report_id(report_id)


def _meta_path(account: str, report_id: str) -> Path:
    return _dir(account, report_id) / "meta.json"


def _drawing_path(account: str, report_id: str) -> Path:
    return _dir(account, report_id) / "drawing.pkdrawing"


def _overlay_path(account: str, report_id: str) -> Path:
    return _dir(account, report_id) / "overlay.png"


def _read_meta(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _decode_b64(value: str | None, *, limit: int, label: str) -> bytes | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return b""
    try:
        raw = base64.b64decode(text, validate=False)
    except Exception as exc:
        raise ValueError(f"Invalid {label} base64") from exc
    if len(raw) > limit:
        raise ValueError(f"{label} exceeds {limit} bytes")
    return raw


def _etag_for(drawing: bytes | None, overlay: bytes | None, updated_at: str) -> str:
    digest = hashlib.sha256()
    digest.update(updated_at.encode("utf-8"))
    digest.update(drawing or b"")
    digest.update(overlay or b"")
    return digest.hexdigest()[:24]


def empty_payload(report_id: str) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "updated_at": None,
        "etag": None,
        "has_drawing_pk": False,
        "has_overlay": False,
        "drawing_pk_base64": None,
        "overlay_png_base64": None,
        "canvas_width": None,
        "canvas_height": None,
        "cleared": False,
    }


def get(
    account: str | None,
    report_id: str,
    *,
    include_drawing: bool = True,
    include_overlay_b64: bool = False,
) -> dict[str, Any]:
    """Load annotation metadata (and optionally binary payloads as base64)."""
    rid = _safe_report_id(report_id)
    with _LOCK:
        meta = _read_meta(_meta_path(account or "", rid))
        if not meta:
            return empty_payload(rid)

        drawing_file = _drawing_path(account or "", rid)
        overlay_file = _overlay_path(account or "", rid)
        drawing_bytes = (
            drawing_file.read_bytes() if drawing_file.is_file() else None
        )
        overlay_bytes = (
            overlay_file.read_bytes() if overlay_file.is_file() else None
        )

        payload = {
            "report_id": rid,
            "updated_at": meta.get("updated_at"),
            "etag": meta.get("etag"),
            "has_drawing_pk": bool(drawing_bytes),
            "has_overlay": bool(overlay_bytes),
            "drawing_pk_base64": None,
            "overlay_png_base64": None,
            "canvas_width": meta.get("canvas_width"),
            "canvas_height": meta.get("canvas_height"),
            "cleared": bool(meta.get("cleared")),
        }
        if include_drawing and drawing_bytes:
            payload["drawing_pk_base64"] = base64.b64encode(drawing_bytes).decode(
                "ascii"
            )
        if include_overlay_b64 and overlay_bytes:
            payload["overlay_png_base64"] = base64.b64encode(overlay_bytes).decode(
                "ascii"
            )
        return payload


def overlay_file(account: str | None, report_id: str) -> Path | None:
    path = _overlay_path(account or "", _safe_report_id(report_id))
    return path if path.is_file() and path.stat().st_size > 0 else None


def save(
    account: str | None,
    report_id: str,
    *,
    drawing_pk_base64: str | None = None,
    overlay_png_base64: str | None = None,
    canvas_width: float | None = None,
    canvas_height: float | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    """Create/replace annotations (last-write-wins). Empty drawing clears ink."""
    rid = _safe_report_id(report_id)
    drawing = _decode_b64(
        drawing_pk_base64, limit=MAX_DRAWING_BYTES, label="drawing_pk"
    )
    overlay = _decode_b64(
        overlay_png_base64, limit=MAX_OVERLAY_BYTES, label="overlay_png"
    )

    if clear or (drawing is not None and len(drawing) == 0):
        delete(account, rid)
        payload = empty_payload(rid)
        payload["cleared"] = True
        payload["updated_at"] = _now_iso()
        payload["etag"] = _etag_for(None, None, payload["updated_at"])
        # Keep a tombstone so other devices know ink was intentionally cleared.
        with _LOCK:
            folder = _dir(account or "", rid)
            folder.mkdir(parents=True, exist_ok=True)
            _write_json(
                _meta_path(account or "", rid),
                {
                    "updated_at": payload["updated_at"],
                    "etag": payload["etag"],
                    "cleared": True,
                    "canvas_width": None,
                    "canvas_height": None,
                },
            )
        return payload

    if drawing is None and overlay is None:
        raise ValueError("Provide drawing_pk_base64 and/or overlay_png_base64")

    updated_at = _now_iso()
    with _LOCK:
        folder = _dir(account or "", rid)
        folder.mkdir(parents=True, exist_ok=True)

        existing_drawing = (
            _drawing_path(account or "", rid).read_bytes()
            if _drawing_path(account or "", rid).is_file()
            else None
        )
        existing_overlay = (
            _overlay_path(account or "", rid).read_bytes()
            if _overlay_path(account or "", rid).is_file()
            else None
        )

        final_drawing = existing_drawing if drawing is None else drawing
        final_overlay = existing_overlay if overlay is None else overlay

        if drawing is not None:
            path = _drawing_path(account or "", rid)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(drawing)
            tmp.replace(path)
        if overlay is not None:
            path = _overlay_path(account or "", rid)
            if len(overlay) == 0:
                path.unlink(missing_ok=True)
                final_overlay = None
            else:
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(overlay)
                tmp.replace(path)

        meta = _read_meta(_meta_path(account or "", rid)) or {}
        width = canvas_width if canvas_width is not None else meta.get("canvas_width")
        height = (
            canvas_height if canvas_height is not None else meta.get("canvas_height")
        )
        etag = _etag_for(final_drawing, final_overlay, updated_at)
        meta_out = {
            "updated_at": updated_at,
            "etag": etag,
            "cleared": False,
            "canvas_width": width,
            "canvas_height": height,
        }
        _write_json(_meta_path(account or "", rid), meta_out)

    return get(
        account,
        rid,
        include_drawing=False,
        include_overlay_b64=False,
    )


def delete(account: str | None, report_id: str) -> bool:
    """Remove drawing + overlay files for this account/report."""
    rid = _safe_report_id(report_id)
    with _LOCK:
        folder = _dir(account or "", rid)
        if not folder.exists():
            return False
        for path in (
            _drawing_path(account or "", rid),
            _overlay_path(account or "", rid),
            _meta_path(account or "", rid),
        ):
            path.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        return True
