"""Per-company file uploads (presentations, PDFs).

Each company gets a directory under `data/uploads/<company_id>/` with an
`index.yaml` recording the metadata for every upload (id, original filename,
size, content type, uploaded_at). The bytes live next to the index in files
named `<file_id>__<sanitized_original>.

Only PPT, PPTX, and PDF are accepted. Filenames are sanitized to prevent
path traversal — even though the filename is never used as a directory
component, we want predictable inspection on disk.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .storage import DATA_DIR

UPLOADS_ROOT = DATA_DIR / "uploads"
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100MB

ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}
ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx"}

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_dir(company_id: str) -> Path:
    safe_id = re.sub(r"[^a-z0-9_-]", "", company_id.lower())
    if not safe_id:
        raise ValueError("Invalid company id")
    return UPLOADS_ROOT / safe_id


def _index_path(company_id: str) -> Path:
    return _company_dir(company_id) / "index.yaml"


def _sanitize_filename(name: str) -> str:
    """Drop path separators, control chars, and weird whitespace."""
    base = Path(name).name  # strips any directory components
    base = re.sub(r"[\x00-\x1f\\/]+", "", base)
    base = base.strip().strip(".")
    return base or "file"


def _read_index(company_id: str) -> list[dict]:
    p = _index_path(company_id)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception:
        return []
    return list(data) if isinstance(data, list) else []


def _write_index(company_id: str, entries: list[dict]) -> None:
    p = _index_path(company_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(entries, f, sort_keys=False, allow_unicode=True)
    tmp.replace(p)


def _kind_from(content_type: str | None, filename: str) -> str | None:
    if content_type and content_type in ALLOWED_TYPES:
        return ALLOWED_TYPES[content_type]
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".pptx":
        return "pptx"
    if ext == ".ppt":
        return "ppt"
    return None


def list_files(company_id: str) -> list[dict]:
    with _LOCK:
        entries = _read_index(company_id)
        # Sort newest first.
        entries.sort(key=lambda e: str(e.get("uploaded_at", "")), reverse=True)
        return entries


def get_file(company_id: str, file_id: str) -> tuple[dict, Path] | None:
    with _LOCK:
        for entry in _read_index(company_id):
            if entry.get("id") == file_id:
                p = _company_dir(company_id) / entry["stored_name"]
                if not p.exists():
                    return None
                return entry, p
        return None


SUPPORTED_LANGUAGES = ("en", "zh")


def upload_file(
    company_id: str,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    label: str | None = None,
    language: str = "en",
) -> dict:
    if not filename:
        raise ValueError("Missing filename")
    if len(data) == 0:
        raise ValueError("Empty file")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds {MAX_FILE_BYTES // (1024*1024)}MB limit")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")

    kind = _kind_from(content_type, filename)
    if kind is None:
        raise ValueError("Unsupported file type — only PDF, PPT, PPTX are accepted")

    safe_name = _sanitize_filename(filename)
    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}__{safe_name}"

    with _LOCK:
        cdir = _company_dir(company_id)
        cdir.mkdir(parents=True, exist_ok=True)
        target = cdir / stored_name
        # Write bytes via tmp + rename for atomicity.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)

        record: dict[str, Any] = {
            "id": file_id,
            "filename": safe_name,
            "stored_name": stored_name,
            "kind": kind,
            "language": language,
            "content_type": content_type or "",
            "size_bytes": len(data),
            "uploaded_at": _now(),
            "label": (label or "").strip() or None,
        }
        entries = _read_index(company_id)
        entries.insert(0, record)
        _write_index(company_id, entries)
        return record


def delete_file(company_id: str, file_id: str) -> bool:
    with _LOCK:
        entries = _read_index(company_id)
        keep: list[dict] = []
        removed: dict | None = None
        for entry in entries:
            if entry.get("id") == file_id:
                removed = entry
            else:
                keep.append(entry)
        if removed is None:
            return False
        # Best-effort delete of the bytes; index update is the source of truth.
        path = _company_dir(company_id) / removed.get("stored_name", "")
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        _write_index(company_id, keep)
        return True
