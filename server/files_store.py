"""Per-company file uploads (presentations, PDFs, Markdown notes).

Each company gets a directory under `data/uploads/<company_id>/` with an
`index.yaml` recording the metadata for every upload (id, original filename,
size, content type, uploaded_at). The bytes live next to the index in files
named `<file_id>__<sanitized_original>.

Only PPT, PPTX, PDF, and MD are accepted. Filenames are sanitized to
prevent path traversal — even though the filename is never used as a
directory component, we want predictable inspection on disk.

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

from . import company_paths
from .storage import DATA_DIR

logger = logging.getLogger(__name__)

UPLOADS_ROOT = DATA_DIR / "uploads"
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100MB

ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/markdown": "md",
    "text/x-markdown": "md",
}
ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".md"}

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_dir(company_id: str) -> Path:
    return UPLOADS_ROOT / company_paths.storage_key(company_id)


def _index_path(company_id: str) -> Path:
    return _company_dir(company_id) / "index.yaml"


def _sanitize_filename(name: str) -> str:
    """Drop path separators, control chars, and weird whitespace."""
    base = Path(name).name  # strips any directory components
    base = re.sub(r"[\x00-\x1f\\/]+", "", base)
    base = base.strip().strip(".")
    return base or "file"


def _quarantine_corrupt_index(path: Path, error: Exception) -> None:
    """Move an unparseable index aside and fail loudly.

    Silently treating a corrupt index as empty meant the next write
    rebuilt it containing only the new entry, orphaning every previously
    uploaded file's record. Quarantining preserves the bytes for manual
    recovery; the caller's operation fails with a clear error instead.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantined = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        path.replace(quarantined)
        logger.error("Quarantined corrupt index %s -> %s", path, quarantined)
    except OSError:
        logger.exception("Failed to quarantine corrupt index %s", path)
        raise RuntimeError(f"Unreadable index {path}: {error}") from error
    raise RuntimeError(
        f"Corrupt index quarantined to {quarantined.name}: {error}"
    ) from error


def _read_index(company_id: str) -> list[dict]:
    p = _index_path(company_id)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception as exc:  # noqa: BLE001
        _quarantine_corrupt_index(p, exc)
    if not isinstance(data, list):
        _quarantine_corrupt_index(p, ValueError("index is not a list"))
    return list(data)


def _write_index(company_id: str, entries: list[dict]) -> None:
    p = _index_path(company_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(entries, f, sort_keys=False, allow_unicode=True)
    tmp.replace(p)


def _kind_from(content_type: str | None, filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".pptx":
        return "pptx"
    if ext == ".ppt":
        return "ppt"
    if ext == ".md":
        return "md"
    if content_type and content_type in ALLOWED_TYPES:
        return ALLOWED_TYPES[content_type]
    return None


def _content_type_for(kind: str, content_type: str | None) -> str:
    """Normalize stored content types for kinds browsers report loosely."""
    if kind == "md":
        return "text/markdown"
    return content_type or ""


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
        raise ValueError(
            "Unsupported file type — only PDF, PPT, PPTX, and MD are accepted"
        )

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
            "content_type": _content_type_for(kind, content_type),
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
# We pass POSIX paths directly — modern PowerPoint accepts them on `save in`.
_POWERPOINT_APPLESCRIPT = """on run argv
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv
    tell application "Microsoft PowerPoint"
        launch
        set thePresentation to open POSIX file inputPath
        save thePresentation in outputPath as save as PDF
        close thePresentation saving no
    end tell
end run
"""

CONVERSION_TIMEOUT = float(os.environ.get("PPT_CONVERSION_TIMEOUT", "180"))

# PowerPoint runs in macOS's App Sandbox and can't read project paths
# (data/uploads/...) or per-process tempdirs (/var/folders/...) — both fail
# with error -9074. /tmp is world-writable and Office's sandbox allows it,
# so we stage input + output there. Override via PPT_STAGE_DIR if needed.
_DEFAULT_STAGE_ROOT = Path("/tmp/bsh-research-center")
_STAGE_ROOT = Path(os.environ.get("PPT_STAGE_DIR") or _DEFAULT_STAGE_ROOT)


def _preview_path_for(company_id: str, record: dict) -> Path:
    """Where the cached PDF preview for a single uploaded file lives."""
    fid = record.get("id") or "unknown"
    return _company_dir(company_id) / f"{fid}__preview.pdf"


def _interpret_applescript_error(detail: str) -> str:
    """Map the most common AppleScript / PowerPoint error codes to a useful
    plain-English explanation. Falls back to the raw stderr otherwise.
    """
    if "-1743" in detail or "Not authorized" in detail:
        return (
            "macOS Automation permission denied. Open System Settings → "
            "Privacy & Security → Automation, find the terminal / IDE "
            "running uvicorn, and enable the checkbox next to "
            "Microsoft PowerPoint."
        )
    if "-9074" in detail or "-1728" in detail or "-43" in detail:
        return (
            "PowerPoint can't read or write the file at the chosen path. "
            "This usually means macOS App Sandbox is blocking access. "
            "Grant Full Disk Access to Microsoft PowerPoint in System "
            "Settings → Privacy & Security → Full Disk Access."
        )
    return detail[:600]


def _convert_with_powerpoint(src: Path, dst: Path) -> tuple[bool, str | None]:
    """Run Microsoft PowerPoint via osascript to save src as a PDF at dst.

    Returns `(success, error_message)`. Idempotent — fast no-op if dst
    already exists. macOS only.

    Files are staged under the user's home directory before being handed to
    PowerPoint because Office's App Sandbox can't reach `data/uploads/...`
    (under the project) or the system tempdir.
    """
    if dst.exists():
        return True, None
    if not src.exists():
        return False, f"Source file missing: {src.name}"
    if sys.platform != "darwin":
        msg = (
            f"PowerPoint conversion is macOS-only (running on {sys.platform})."
        )
        logger.warning("%s Skipping %s", msg, src)
        return False, msg

    script_file: Path | None = None
    stage_dir: Path | None = None
    try:
        # 1. Write the AppleScript to a temp file (path doesn't matter — the
        #    script is interpreted by osascript, not PowerPoint).
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".applescript", delete=False
        ) as f:
            f.write(_POWERPOINT_APPLESCRIPT)
            script_file = Path(f.name)

        # 2. Stage the input + output in ~/.bsh-research-center/ppt-convert.
        #    PowerPoint's sandbox extension covers the user's home so this
        #    path is reachable; /var/folders/... is not.
        _STAGE_ROOT.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix="conv-", dir=str(_STAGE_ROOT)))
        # Preserve the extension so PowerPoint identifies the format.
        staged_in = stage_dir / src.name
        shutil.copy2(src, staged_in)
        staged_out = stage_dir / "out.pdf"

        try:
            subprocess.run(
                [
                    "osascript",
                    str(script_file),
                    str(staged_in),
                    str(staged_out),
                ],
                check=True,
                timeout=CONVERSION_TIMEOUT,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            msg = f"osascript not found: {exc}"
            logger.warning("Can't convert %s: %s", src, msg)
            return False, msg
        except subprocess.TimeoutExpired:
            msg = (
                f"PowerPoint conversion timed out after "
                f"{CONVERSION_TIMEOUT:.0f}s. Set PPT_CONVERSION_TIMEOUT to "
                "raise the cap."
            )
            logger.warning("%s (%s)", msg, src)
            return False, msg
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", "ignore").strip()
            stdout = (exc.stdout or b"").decode("utf-8", "ignore").strip()
            detail = stderr or stdout or "(no output)"
            msg = f"PowerPoint conversion failed: {_interpret_applescript_error(detail)}"
            logger.warning("%s (raw: %s) (%s)", msg, detail[:300], src)
            return False, msg

        if not staged_out.exists():
            msg = "PowerPoint produced no output (no PDF written)."
            logger.warning("%s (%s)", msg, src)
            return False, msg

        # 3. Move the produced PDF into the cache location.
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_out), str(dst))
        return True, None
    finally:
        if script_file is not None:
            try:
                script_file.unlink(missing_ok=True)
            except Exception:
                pass
        if stage_dir is not None:
            try:
                shutil.rmtree(stage_dir, ignore_errors=True)
            except Exception:
                pass


def get_or_create_preview(
    company_id: str, file_id: str
) -> tuple[Path | None, str | None]:
    """Return `(pdf_path, error)` for the given file.

    PDFs and Markdown return their original path. PPT/PPTX return a cached
    preview, running PowerPoint conversion synchronously if the cache is empty.
    On failure the error string explains why so the API can surface it to the
    UI.
    """
    found = get_file(company_id, file_id)
    if found is None:
        return None, "File not found."
    record, src_path = found
    kind = record.get("kind")
    if kind in ("pdf", "md"):
        return src_path, None
    if kind not in ("ppt", "pptx"):
        return None, f"Unsupported file kind: {kind}"
    preview = _preview_path_for(company_id, record)
    if preview.exists():
        return preview, None
    ok, err = _convert_with_powerpoint(src_path, preview)
    if ok:
        return preview, None
    return None, err or "PowerPoint conversion failed."


def update_record(company_id: str, file_id: str, **patch: Any) -> dict | None:
    """Merge patch into the file's index entry. Returns updated record or None."""
    with _LOCK:
        entries = _read_index(company_id)
        for i, entry in enumerate(entries):
            if entry.get("id") == file_id:
                entry.update(patch)
                entries[i] = entry
                _write_index(company_id, entries)
                return entry
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
