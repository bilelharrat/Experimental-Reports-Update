"""Per-company research-library uploads (Serena's "company folder").

This is the storage backing the **Background Documents** UI section: a
per-company folder where the analyst drops research material (PitchBook
PDFs, partner notes, CB Insights exports, screenshots, Word notes) that
the investment-memo skill is intended to consume.

It is intentionally **separate** from ``data/uploads/<slug>/`` (the
Document Library). See ``docs/architecture.md`` — the two flows do not
share files or code paths.

Layout::

    data/research/<company_slug>/
        index.yaml                     # list[dict] of file records
        <file_id>__<sanitized_name>    # raw file bytes

Each ``index.yaml`` row records id, original filename, stored name,
content type, kind, size, sha256, uploaded_at, plus a ``quick_summary``
field that the AI-summary endpoint populates.

The file types we accept are broader than the Document Library because
research material is heterogeneous (PitchBook PDFs, Word docs, plain
notes, screenshots).
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import company_paths
from .storage import DATA_DIR

logger = logging.getLogger(__name__)

RESEARCH_ROOT = DATA_DIR / "research"
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100MB per file

# Broader than files_store: this library is for any research artifact.
ALLOWED_KINDS_BY_EXT: dict[str, str] = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".docx": "docx",
    ".doc": "doc",
    ".txt": "text",
    ".md": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
}

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_dir(company_id: str) -> Path:
    return RESEARCH_ROOT / company_paths.storage_key(company_id)


def _index_path(company_id: str) -> Path:
    return _company_dir(company_id) / "index.yaml"


def quick_summary_progress_path(company_id: str, file_id: str) -> Path:
    """JSONL stream path for a quick-summary job. Surfaces in the unified
    AI Tasks rail (kind=research_summary)."""
    return _company_dir(company_id) / f"{file_id}__quick_summary.progress.jsonl"


def analysis_progress_path(company_id: str, target_id: str) -> Path:
    """JSONL stream path for a document-analysis job (kind=research_analysis).

    ``target_id`` is a file id or a folder id (``fld`` prefix)."""
    return _company_dir(company_id) / f"{target_id}__analysis.progress.jsonl"


# Folder ids are server-minted and self-identifying: the ``fld`` prefix means
# a folder id can never be confused with a 12-hex file id in analysis
# targets, progress filenames, or the memo listing.
FOLDER_ID_RE = re.compile(r"^fld[0-9a-f]{9}$")


def mint_folder_id() -> str:
    return "fld" + uuid.uuid4().hex[:9]


def folder_members(company_id: str, folder_id: str) -> list[dict]:
    """Member entries of one uploaded folder, oldest first."""
    with _LOCK:
        entries = _read_index(company_id)
    members = [e for e in entries if e.get("folder_id") == folder_id]
    members.sort(key=lambda e: str(e.get("uploaded_at") or ""))
    return members


def analysis_entry_for(company_id: str, target_id: str) -> dict | None:
    """The analysis file entry for a file or folder id, when one exists."""
    with _LOCK:
        entries = _read_index(company_id)
    for entry in entries:
        if entry.get("analysis_of") == target_id:
            return entry
    return None


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
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
    if ext in ALLOWED_KINDS_BY_EXT:
        return ALLOWED_KINDS_BY_EXT[ext]
    # Map a few common content-types as a fallback for browser-driven uploads.
    if content_type:
        ct = content_type.lower()
        if "pdf" in ct:
            return "pdf"
        if "presentation" in ct or "pptx" in ct:
            return "pptx"
        if "wordprocessing" in ct or "docx" in ct:
            return "docx"
        if ct.startswith("image/"):
            return "image"
        if ct.startswith("text/"):
            return "text"
    return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Public API -----------------------------------------------------------

def list_files(company_id: str) -> list[dict]:
    """Newest first."""
    with _LOCK:
        entries = _read_index(company_id)
        entries.sort(key=lambda e: str(e.get("uploaded_at", "")), reverse=True)
        return entries


def get_file(company_id: str, file_id: str) -> tuple[dict, Path] | None:
    """Return ``(metadata, on_disk_path)`` if the file exists, else None."""
    with _LOCK:
        for entry in _read_index(company_id):
            if entry.get("id") == file_id:
                p = _company_dir(company_id) / entry["stored_name"]
                if not p.exists():
                    return None
                return entry, p
        return None


def upload_file(
    company_id: str,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    label: str | None = None,
    folder_id: str | None = None,
    folder_name: str | None = None,
) -> dict:
    if not filename:
        raise ValueError("Missing filename")
    if not data:
        raise ValueError("Empty file")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            f"File too large: {len(data)} bytes (max {MAX_FILE_BYTES})"
        )
    kind = _kind_from(content_type, filename)
    if kind is None:
        raise ValueError(
            f"Unsupported file type: {filename} (content_type={content_type})"
        )

    safe_name = _sanitize_filename(filename)
    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}__{safe_name}"

    with _LOCK:
        cdir = _company_dir(company_id)
        cdir.mkdir(parents=True, exist_ok=True)
        out_path = cdir / stored_name
        out_path.write_bytes(data)

        entry: dict = {
            "id": file_id,
            "filename": safe_name,
            "stored_name": stored_name,
            "kind": kind,
            "content_type": content_type,
            "size_bytes": len(data),
            "sha256": _sha256(data),
            "label": label or None,
            "uploaded_at": _now(),
            "quick_summary": None,  # Populated by the summarize endpoint.
        }
        if folder_id:
            entry["folder_id"] = folder_id
            entry["folder_name"] = folder_name or None
        entries = _read_index(company_id)
        entries.append(entry)
        _write_index(company_id, entries)
        return entry


def update_record(
    company_id: str, file_id: str, **patch
) -> dict | None:
    """Merge ``patch`` into the index entry for ``file_id``. Returns the
    updated entry or None if not found."""
    with _LOCK:
        entries = _read_index(company_id)
        for i, entry in enumerate(entries):
            if entry.get("id") == file_id:
                entry.update(patch)
                entries[i] = entry
                _write_index(company_id, entries)
                return entry
        return None


def _unlink_quiet(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        logger.warning("Failed to delete %s", path, exc_info=True)


def delete_file(company_id: str, file_id: str) -> bool:
    """Delete one entry + blob, cascading its analysis relationships.

    - The entry's own analysis progress sidecar is removed.
    - Deleting an ANALYSIS file nulls the source's ``analysis_file_id``
      (the Analyze button flips back).
    - Deleting a SOURCE file cascades its analysis file (an analysis of a
      deleted document is orphaned noise).
    - Deleting a folder's LAST member cascades the folder's analysis and
      its sidecar. Deleting a non-last member leaves the folder analysis
      (stale until Reanalyze).
    ``_LOCK`` is reentrant, so cascades re-enter this function; the index
    is re-read on every entry.
    """
    with _LOCK:
        entries = _read_index(company_id)
        removed: dict | None = None
        kept: list[dict] = []
        for entry in entries:
            if entry.get("id") == file_id and removed is None:
                removed = entry
            else:
                kept.append(entry)
        if removed is None:
            return False
        _write_index(company_id, kept)
        _unlink_quiet(_company_dir(company_id) / removed.get("stored_name", ""))
        _unlink_quiet(analysis_progress_path(company_id, file_id))

        source_id = removed.get("analysis_of")
        if source_id:
            update_record(company_id, str(source_id), analysis_file_id=None)

        analysis_id = removed.get("analysis_file_id")
        if analysis_id:
            delete_file(company_id, str(analysis_id))

        folder_id = removed.get("folder_id")
        if folder_id and not folder_members(company_id, str(folder_id)):
            folder_analysis = analysis_entry_for(company_id, str(folder_id))
            if folder_analysis and folder_analysis.get("id"):
                delete_file(company_id, str(folder_analysis["id"]))
            _unlink_quiet(analysis_progress_path(company_id, str(folder_id)))
        return True
