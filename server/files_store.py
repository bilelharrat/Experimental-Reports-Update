"""Per-company file uploads (presentations, PDFs).

Each company gets a directory under `data/uploads/<company_id>/` with an
`index.yaml` recording the metadata for every upload (id, original filename,
size, content type, uploaded_at). The bytes live next to the index in files
named `<file_id>__<sanitized_original>.

Only PPT, PPTX, and PDF are accepted. Filenames are sanitized to prevent
path traversal — even though the filename is never used as a directory
component, we want predictable inspection on disk.

PPT/PPTX uploads are auto-converted to PDF (cached as `<id>__preview.pdf`
next to the original) using Microsoft PowerPoint via AppleScript. This runs
in a background thread on upload and synchronously on demand for files that
were uploaded before this code shipped or had a previous conversion fail.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .storage import DATA_DIR

logger = logging.getLogger(__name__)

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
        # PPT/PPTX uploads kick off PowerPoint conversion in the background so
        # the upload response stays fast. PDFs need no conversion.
        kick_off_background_conversion(company_id, record)
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
        # Drop the cached preview if we made one.
        preview = _preview_path_for(company_id, removed)
        try:
            preview.unlink(missing_ok=True)
        except Exception:
            pass
        _write_index(company_id, keep)
        return True


# ---------- PowerPoint → PDF conversion ----------

# Embedded AppleScript: open the input, save as PDF, close. `launch` (vs
# `activate`) keeps PowerPoint in the background so it doesn't steal focus.
_POWERPOINT_APPLESCRIPT = """on run argv
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv
    tell application "Microsoft PowerPoint"
        launch
        set thePresentation to open POSIX file inputPath
        save thePresentation in (POSIX file outputPath as text) as save as PDF
        close thePresentation saving no
    end tell
end run
"""

CONVERSION_TIMEOUT = float(os.environ.get("PPT_CONVERSION_TIMEOUT", "180"))


def _preview_path_for(company_id: str, record: dict) -> Path:
    """Where the cached PDF preview for a single uploaded file lives."""
    fid = record.get("id") or "unknown"
    return _company_dir(company_id) / f"{fid}__preview.pdf"


def _convert_with_powerpoint(src: Path, dst: Path) -> bool:
    """Run Microsoft PowerPoint via osascript to save src as a PDF at dst.

    Returns True on success. Idempotent — fast no-op if dst already exists.
    macOS only.
    """
    if dst.exists():
        return True
    if not src.exists():
        return False
    if sys.platform != "darwin":
        logger.warning(
            "PowerPoint conversion is macOS-only (sys.platform=%s); skipping %s",
            sys.platform,
            src,
        )
        return False

    script_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".applescript", delete=False
        ) as f:
            f.write(_POWERPOINT_APPLESCRIPT)
            script_file = Path(f.name)

        # Convert into a temp output then move atomically into place so a
        # half-written file never wins a race against a concurrent reader.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_out = Path(tmp) / "out.pdf"
            try:
                subprocess.run(
                    ["osascript", str(script_file), str(src), str(tmp_out)],
                    check=True,
                    timeout=CONVERSION_TIMEOUT,
                    capture_output=True,
                )
            except FileNotFoundError as exc:
                logger.warning("osascript missing, can't convert %s: %s", src, exc)
                return False
            except subprocess.TimeoutExpired:
                logger.warning(
                    "PowerPoint conversion timed out after %ss for %s",
                    CONVERSION_TIMEOUT,
                    src,
                )
                return False
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"").decode("utf-8", "ignore")[:500]
                logger.warning(
                    "PowerPoint conversion failed for %s: %s", src, stderr
                )
                return False
            if not tmp_out.exists():
                logger.warning("PowerPoint produced no output for %s", src)
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_out), str(dst))
            return True
    finally:
        if script_file is not None:
            try:
                script_file.unlink(missing_ok=True)
            except Exception:
                pass


def get_or_create_preview(company_id: str, file_id: str) -> Path | None:
    """Return a previewable PDF path for the given file.

    PDFs return their original path. PPT/PPTX return a cached preview, running
    PowerPoint conversion synchronously if the cache is empty. None on failure
    or unsupported kind.
    """
    found = get_file(company_id, file_id)
    if found is None:
        return None
    record, src_path = found
    kind = record.get("kind")
    if kind == "pdf":
        return src_path
    if kind not in ("ppt", "pptx"):
        return None
    preview = _preview_path_for(company_id, record)
    if preview.exists():
        return preview
    if _convert_with_powerpoint(src_path, preview):
        return preview
    return None


def kick_off_background_conversion(company_id: str, record: dict) -> None:
    """Spawn a daemon thread to convert a freshly-uploaded PPT to PDF."""
    if record.get("kind") not in ("ppt", "pptx"):
        return
    src = _company_dir(company_id) / record.get("stored_name", "")
    dst = _preview_path_for(company_id, record)

    def _run() -> None:
        try:
            _convert_with_powerpoint(src, dst)
        except Exception:
            logger.exception("Background conversion failed for %s", src)

    threading.Thread(
        target=_run, name=f"ppt-convert:{record.get('id')}", daemon=True
    ).start()
