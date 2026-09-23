"""File-based storage for the per-company Console feature.

See ``docs/console-feature.md`` for the full design. This module owns the
on-disk layout and pure data operations — no subprocess management, no
HTTP, no Claude calls. ``console_session`` is the orchestrator that
calls into here.

Layout::

    data/consoles/<company_id>/
      sessions/
        <session_id>/
          meta.json                  (status, tokens, summary, …)
          turns.jsonl                (user + assistant records, append-only)
          attachments/
            <sha256>.<ext>           (uploaded images keyed by content hash)
          workdir/                   (Claude's --add-dir target)
            <staged docs>            (hardlinks of selected library/research files)
            attachments/             (symlink/copy mirror of ../attachments/)
          hydrate.progress.jsonl     (stream-json events from the hydrate run)
          ask/
            <turn_id>.progress.jsonl (one stream per turn — see §3 of the doc)
          summary.progress.jsonl     (stream from the on-archive summary run)
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import attachment_text
from .files_store import DATA_DIR


# ---- Caps (see §10 of docs/console-feature.md) --------------------------

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Canonical extension -> MIME for everything an analyst may attach. The
# stored file keeps the canonical extension, so this table also drives
# ``_EXT_FOR_MIME``. Office documents, HTML and RTF are converted to text
# at save time (see ``attachment_text``) because Claude's Read tool
# reports them as binary; images and PDFs it opens itself.
ATTACHMENT_TYPE_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".html": "text/html",
    ".htm": "text/html",
}
ALLOWED_ATTACHMENT_TYPES: frozenset[str] = frozenset(ATTACHMENT_TYPE_BY_EXT.values())

# Formats the model takes in with its own eyes. Everything else has to
# come back from ``attachment_text`` as text, or it is not worth staging:
# a file nobody can read only produces an apology two minutes later.
NATIVE_READ_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
)

ATTACHMENT_TYPE_MESSAGE = (
    "Attach an image (PNG, JPEG, GIF, WebP), a document (PDF, Word, "
    "PowerPoint, Excel, RTF) or a text file (TXT, Markdown, CSV, TSV, "
    "JSON, YAML, HTML)"
)
MAX_ACTIVE_SESSIONS_PER_COMPANY = 6

# Watchdog thresholds (see §7). Exposed here so console_session and tests
# can import the same numbers.
EVENT_SILENCE_TIMEOUT_S = 90.0
WATCHDOG_KILL_GRACE_S = 30.0
WALL_CLOCK_CAP_S = 600.0  # 10 minutes per ask

# Output-language allowlist (see §7? actually §1 — set on create, immutable).
SUPPORTED_OUTPUT_LANGUAGES = ("en", "zh")
DEFAULT_OUTPUT_LANGUAGE = "en"


# ---- On-disk roots ------------------------------------------------------

CONSOLES_ROOT = DATA_DIR / "consoles"

# Session and turn ids are UUID4 hex (32 chars). Company ids are whatever
# ``storage`` issues: a lowercased ticker (``brk.b``) or a slug that keeps
# any Unicode letter or digit (``ceinet-data-co-ltd-中经网数据有限公司``).
# ``_validate_company_id`` accepts exactly that shape as a single safe path
# segment; the directory key stays identical to the id so existing
# ``data/consoles/<id>`` folders keep working.
_HEX_ID_RE = re.compile(r"^[a-f0-9]{12,64}$")
_COMPANY_ID_MAX_CHARS = 128
_COMPANY_ID_MAX_BYTES = 255
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

# One process-wide lock for index-style mutations. Turn writes use the same
# lock so meta + turns.jsonl never observe a half-written counterpart.
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_id(value: str, *, kind: str = "id") -> str:
    """Validate a session or turn id as UUID-style hex."""
    if not isinstance(value, str) or not _HEX_ID_RE.match(value):
        raise ValueError(f"Invalid {kind}: {value!r}")
    return value


def _validate_company_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid company_id: {value!r}")
    v = value.lower()
    ok = (
        0 < len(v) <= _COMPANY_ID_MAX_CHARS
        and len(v.encode("utf-8")) <= _COMPANY_ID_MAX_BYTES
        and v[0].isalnum()
        and all(ch.isalnum() or ch in "-_." for ch in v)
        and ".." not in v
    )
    if not ok:
        raise ValueError(f"Invalid company_id: {value!r}")
    return v


def _validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        raise ValueError(f"Invalid attachment id: {value!r}")
    return value


# ---- Path helpers -------------------------------------------------------


def company_dir(company_id: str) -> Path:
    return CONSOLES_ROOT / _validate_company_id(company_id)


def sessions_dir(company_id: str) -> Path:
    return company_dir(company_id) / "sessions"


def session_dir(company_id: str, session_id: str) -> Path:
    return sessions_dir(company_id) / _validate_id(session_id, kind="session_id")


def meta_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "meta.json"


def turns_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "turns.jsonl"


def attachments_dir(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "attachments"


def workdir(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "workdir"


def workdir_attachments(company_id: str, session_id: str) -> Path:
    return workdir(company_id, session_id) / "attachments"


def hydrate_progress_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "hydrate.progress.jsonl"


def ask_progress_dir(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "ask"


def ask_progress_path(company_id: str, session_id: str, turn_id: str) -> Path:
    return ask_progress_dir(company_id, session_id) / (
        f"{_validate_id(turn_id, kind='turn_id')}.progress.jsonl"
    )


def summary_progress_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "summary.progress.jsonl"


# ---- Session lifecycle --------------------------------------------------


def new_session_id() -> str:
    """UUID4-hex as our session id (also used for ``--session-id`` to Claude).

    Hex form is convenient because it round-trips as a safe path component.
    """
    return uuid.uuid4().hex


def new_turn_id() -> str:
    return uuid.uuid4().hex


def _default_title() -> str:
    return "Session · " + datetime.now(timezone.utc).strftime("%H:%M")


def create_session(
    *,
    company_id: str,
    include_background_docs: bool,
    include_library_docs: bool,
    included_files: Iterable[dict],
    output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    model: str = "claude-opus-4-7-1m",
    title: str | None = None,
) -> dict:
    """Lay out the on-disk session directory and write the initial meta.json.

    ``included_files`` is a list of ``{"id": "...", "kind": "library"|"research",
    "filename": "..."}`` records. The caller resolves these from the two
    file stores; we just record them.

    Raises ``SessionLimitReached`` if the per-company cap is already met.
    """
    active = active_count(company_id)
    if active >= MAX_ACTIVE_SESSIONS_PER_COMPANY:
        raise SessionLimitReached(
            f"Company {company_id} already has {active} active sessions "
            f"(max {MAX_ACTIVE_SESSIONS_PER_COMPANY})"
        )
    if output_language not in SUPPORTED_OUTPUT_LANGUAGES:
        raise ValueError(
            f"Unsupported output_language: {output_language!r} "
            f"(expected one of {SUPPORTED_OUTPUT_LANGUAGES})"
        )

    sid = new_session_id()
    with _LOCK:
        sdir = session_dir(company_id, sid)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "workdir").mkdir(exist_ok=True)
        (sdir / "ask").mkdir(exist_ok=True)
        (sdir / "attachments").mkdir(exist_ok=True)
        (sdir / "workdir" / "attachments").mkdir(exist_ok=True)
        turns_path(company_id, sid).touch()

        now = _now()
        meta = {
            "id": sid,
            "company_id": company_id,
            "claude_session_id": str(uuid.uuid4()),
            "model": model,
            "status": "active",
            "title": title or _default_title(),
            "created_at": now,
            "last_used_at": now,
            "archived_at": None,
            "include_background_docs": bool(include_background_docs),
            "include_library_docs": bool(include_library_docs),
            "included_files": list(included_files),
            "output_language": output_language,
            "tokens": {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_creation": 0,
                "total_cost_usd": 0.0,
                "last_turn_usage": None,
            },
            "summary": None,
        }
        _write_meta(company_id, sid, meta)
    return meta


def is_copilot_session(meta: dict | None) -> bool:
    """True for Co-Pilot quick/deep sessions (hidden from company Console UI)."""
    if not meta:
        return False
    kind = str(meta.get("session_kind") or "")
    return kind.startswith("copilot_")


def active_count(company_id: str) -> int:
    """Count user Console sessions only — Co-Pilot sessions don't burn the cap."""
    return sum(
        1
        for m in iter_sessions(company_id)
        if m.get("status") == "active" and not is_copilot_session(m)
    )


def list_sessions(company_id: str, *, include_copilot: bool = True) -> list[dict]:
    """Newest first; both active and archived.

    Pass ``include_copilot=False`` for the company Console UI so Inspect
    sessions don't appear as Research AI transcripts.
    """
    metas = list(iter_sessions(company_id))
    if not include_copilot:
        metas = [m for m in metas if not is_copilot_session(m)]
    metas.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
    return metas


def iter_sessions(company_id: str) -> Iterable[dict]:
    sdir = sessions_dir(company_id)
    if not sdir.exists():
        return []
    out: list[dict] = []
    for child in sdir.iterdir():
        if not child.is_dir():
            continue
        meta_file = child / "meta.json"
        if not meta_file.exists():
            continue
        try:
            out.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def load_meta(company_id: str, session_id: str) -> dict | None:
    path = meta_path(company_id, session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_meta(company_id: str, session_id: str, meta: dict) -> None:
    """Atomic tmp+rename meta.json write."""
    target = meta_path(company_id, session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def update_meta(company_id: str, session_id: str, **patch: Any) -> dict | None:
    """Read-modify-write under the session lock."""
    with _LOCK:
        meta = load_meta(company_id, session_id)
        if meta is None:
            return None
        meta.update(patch)
        meta["last_used_at"] = _now()
        _write_meta(company_id, session_id, meta)
        return meta


def update_tokens(
    company_id: str,
    session_id: str,
    *,
    usage: dict,
    cost_usd: float,
) -> dict | None:
    """Apply one turn's accounting to ``meta.tokens``.

    Cumulative fields (input/output/cache_read/cache_creation/total_cost_usd)
    sum across turns; ``last_turn_usage`` stores the raw usage from this
    turn for the token meter (see §5).
    """
    with _LOCK:
        meta = load_meta(company_id, session_id)
        if meta is None:
            return None
        tokens = meta.setdefault(
            "tokens",
            {
                "input": 0, "output": 0,
                "cache_read": 0, "cache_creation": 0,
                "total_cost_usd": 0.0, "last_turn_usage": None,
            },
        )
        tokens["input"] += int(usage.get("input_tokens") or 0)
        tokens["output"] += int(usage.get("output_tokens") or 0)
        tokens["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
        tokens["cache_creation"] += int(usage.get("cache_creation_input_tokens") or 0)
        tokens["total_cost_usd"] = float(tokens.get("total_cost_usd") or 0.0) + float(cost_usd or 0.0)
        tokens["last_turn_usage"] = {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
        }
        meta["last_used_at"] = _now()
        _write_meta(company_id, session_id, meta)
        return meta


def archive_session(company_id: str, session_id: str) -> dict | None:
    return update_meta(
        company_id, session_id,
        status="archived", archived_at=_now(),
    )


def hard_delete_session(company_id: str, session_id: str) -> bool:
    sdir = session_dir(company_id, session_id)
    if not sdir.exists():
        return False
    with _LOCK:
        shutil.rmtree(sdir)
        return True


# ---- Turns --------------------------------------------------------------


def append_turn(company_id: str, session_id: str, record: dict) -> None:
    """Append one JSON line to ``turns.jsonl`` under the lock."""
    path = turns_path(company_id, session_id)
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


def read_turns(
    company_id: str, session_id: str, *, include_superseded: bool = False
) -> list[dict]:
    """The thread as it stands.

    The log itself is append-only — an edited question is never rewritten
    or deleted. A re-asked question carries ``edits: <old turn id>``, and
    the old question (plus the answer it drew) drops out of the thread
    here, so nobody on the team — and no model reading the transcript for
    context — works from the version that was replaced. Pass
    ``include_superseded`` to see the whole log.
    """
    path = turns_path(company_id, session_id)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out if include_superseded else drop_superseded(out)


def drop_superseded(turns: list[dict]) -> list[dict]:
    """Remove every turn an edit replaced, questions and answers alike.

    An assistant turn carries the id of the question it answers, so one
    id covers the pair. Edits chain: edit an edit and both earlier
    versions go.
    """
    replaced = {
        str(turn.get("edits"))
        for turn in turns
        if turn.get("edits")
    }
    if not replaced:
        return turns
    return [turn for turn in turns if str(turn.get("id")) not in replaced]


# ---- Workdir staging ----------------------------------------------------


def stage_docs(
    *,
    company_id: str,
    session_id: str,
    source_paths: Iterable[Path],
) -> list[Path]:
    """Populate the session's workdir/ with hardlinks (or copies) of source
    documents. Returns the staged paths inside workdir/.

    Hardlink first; fall back to ``shutil.copy2`` on ``OSError`` (most often
    ``EXDEV`` for cross-filesystem links).
    """
    wd = workdir(company_id, session_id)
    wd.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for src in source_paths:
        src = Path(src)
        if not src.is_file():
            continue
        dst = wd / src.name
        if dst.exists():
            staged.append(dst)
            continue
        try:
            os.link(src, dst)
        except OSError as exc:
            # EXDEV → fall back to copy. We also fall back on any other OSError
            # because workdir hardlinks are best-effort; a copy always works.
            if exc.errno != errno.EXDEV:
                # Re-raise truly unexpected errors only if they aren't recoverable
                # by copy. The copy below will surface the real problem otherwise.
                pass
            shutil.copy2(src, dst)
        staged.append(dst)
    return staged


# ---- Attachments --------------------------------------------------------


# Magic-byte prefixes for unambiguous formats. For .doc/.docx the magic
# is shared with other OLE2/ZIP-based files, so detection there also
# requires the filename extension (see ``detect_attachment_type``).
_UNAMBIGUOUS_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"{\\rtf", "application/rtf"),
)
_OLE2_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"  # .doc (and .xls/.ppt — extension disambiguates)
_ZIP_MAGIC = b"PK\x03\x04"                          # .docx/.xlsx/.pptx — extension disambiguates
_ZIP_OFFICE_EXTS = frozenset({".docx", ".xlsx", ".pptx"})
# Plain-text formats have no magic; the extension names them and the
# bytes have to back it up (see ``_looks_like_text``).
_TEXT_EXTS = frozenset(
    {".txt", ".log", ".md", ".markdown", ".csv", ".tsv", ".json",
     ".yaml", ".yml", ".html", ".htm"}
)


def _looks_like_text(data: bytes) -> bool:
    """A cheap "is this prose or a binary blob" check, encoding-agnostic:
    no NUL bytes and almost everything printable in the first 8 KB.
    """
    head = data[:8192]
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 BOM
        return True
    if b"\x00" in head:
        return False
    printable = sum(1 for byte in head if byte >= 32 or byte in (9, 10, 13))
    return printable / max(len(head), 1) > 0.9


def detect_attachment_type(
    data: bytes, filename: str | None = None
) -> str | None:
    """Return the MIME type detected from magic bytes, or None if the
    upload isn't one of the allowed types.

    For .doc (OLE2 compound) and .docx (ZIP-based Office Open XML), the
    magic alone is ambiguous (other Office formats share it), so we
    additionally require the filename extension to disambiguate.
    """
    if not data:
        return None
    for prefix, mime in _UNAMBIGUOUS_MAGIC:
        if data.startswith(prefix):
            return mime
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    lower_name = (filename or "").lower()
    ext = "." + lower_name.rsplit(".", 1)[1] if "." in lower_name else ""
    if data.startswith(_OLE2_MAGIC) and ext == ".doc":
        return "application/msword"
    if data.startswith(_ZIP_MAGIC) and ext in _ZIP_OFFICE_EXTS:
        return ATTACHMENT_TYPE_BY_EXT[ext]
    if ext in _TEXT_EXTS and _looks_like_text(data):
        return ATTACHMENT_TYPE_BY_EXT[ext]
    return None


# Backwards-compat aliases for external callers (and existing tests).
detect_image_type = detect_attachment_type
MAX_IMAGE_BYTES = MAX_ATTACHMENT_BYTES
ALLOWED_IMAGE_TYPES = ALLOWED_ATTACHMENT_TYPES


# First extension wins: .jpg over .jpeg, .md over .markdown.
_EXT_FOR_MIME: dict[str, str] = {}
for _ext, _mime in ATTACHMENT_TYPE_BY_EXT.items():
    _EXT_FOR_MIME.setdefault(_mime, _ext)


class AttachmentTooLarge(Exception):
    """Upload exceeded ``MAX_ATTACHMENT_BYTES``."""


class AttachmentTypeNotAllowed(Exception):
    """Upload's sniffed MIME isn't one of ``ALLOWED_ATTACHMENT_TYPES``."""


class AttachmentUnreadable(Exception):
    """An allowed format that yielded no text and that the model cannot
    open itself — better refused at the composer than apologized for two
    minutes into the answer.
    """


class SessionLimitReached(Exception):
    """Per-company active session cap hit."""


def save_attachment(
    *,
    company_id: str,
    session_id: str,
    filename: str,
    data: bytes,
) -> dict:
    """Validate, sniff, and persist an uploaded attachment (image or
    document). Returns a record suitable for embedding in the user turn::

        {"id": "<sha256>", "name": "chart.png", "mime": "image/png",
         "size_bytes": 12345}

    The same bytes are written to both ``attachments/<sha>.<ext>`` (the
    canonical store) AND to ``workdir/attachments/<sha>.<ext>`` (so Claude
    can Read them via ``--add-dir workdir``). Anything that isn't an image
    or a PDF is also converted to text beside it, because Read reports a
    .docx as binary; the ask inlines that text into the prompt.
    """
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLarge(
            f"Attachment too large: {len(data)} bytes (max {MAX_ATTACHMENT_BYTES})"
        )
    mime = detect_attachment_type(data, filename)
    if mime is None or mime not in ALLOWED_ATTACHMENT_TYPES:
        raise AttachmentTypeNotAllowed(ATTACHMENT_TYPE_MESSAGE)
    text = attachment_text.extract(data, mime, filename=filename)
    if not text and mime not in NATIVE_READ_TYPES:
        raise AttachmentUnreadable(
            f"No text could be read out of {filename}. If it is a scan, "
            "attach it as a PDF or an image instead."
        )
    sha = hashlib.sha256(data).hexdigest()
    ext = _EXT_FOR_MIME[mime]

    canonical = attachments_dir(company_id, session_id) / f"{sha}{ext}"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if not canonical.exists():
        tmp = canonical.with_suffix(ext + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(canonical)

    work = workdir_attachments(company_id, session_id) / f"{sha}{ext}"
    work.parent.mkdir(parents=True, exist_ok=True)
    if not work.exists():
        try:
            os.link(canonical, work)
        except OSError:
            shutil.copy2(canonical, work)

    stored_name = f"{sha}{ext}"
    chars = attachment_text.write_text(
        canonical.parent, stored_name, text, display_name=filename
    )
    if chars:
        sidecar = attachment_text.text_path(canonical.parent, stored_name)
        mirror = attachment_text.text_path(work.parent, stored_name)
        if not mirror.exists():
            try:
                os.link(sidecar, mirror)
            except OSError:
                shutil.copy2(sidecar, mirror)

    return {
        "id": sha,
        "name": filename,
        "mime": mime,
        "size_bytes": len(data),
        "stored_name": stored_name,
        "text_chars": chars,
    }


def get_attachment_path(
    company_id: str, session_id: str, attachment_id: str
) -> Path | None:
    _validate_sha256(attachment_id)
    adir = attachments_dir(company_id, session_id)
    if not adir.exists():
        return None
    for child in adir.iterdir():
        if child.is_file() and child.stem == attachment_id:
            return child
    return None


# ---- Token-meter helper -------------------------------------------------


CONTEXT_WINDOW = 1_000_000


def context_used_from_usage(usage: dict | None) -> int:
    """The §5 formula::

        last_result.usage.input_tokens
          + cache_read_input_tokens
          + cache_creation_input_tokens
    """
    if not usage:
        return 0
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )


def context_used(meta: dict) -> int:
    return context_used_from_usage((meta.get("tokens") or {}).get("last_turn_usage"))


# ---- Diagnostics / debug ------------------------------------------------


def session_exists(company_id: str, session_id: str) -> bool:
    try:
        return meta_path(company_id, session_id).exists()
    except ValueError:
        return False


__all__ = [
    "drop_superseded",
    "MAX_ATTACHMENT_BYTES",
    "ALLOWED_ATTACHMENT_TYPES",
    "ATTACHMENT_TYPE_BY_EXT",
    "ATTACHMENT_TYPE_MESSAGE",
    "NATIVE_READ_TYPES",
    "AttachmentUnreadable",
    # Backwards-compat aliases kept for one release; remove once external
    # callers (none in-tree as of 2026-05-13) have migrated.
    "MAX_IMAGE_BYTES",
    "ALLOWED_IMAGE_TYPES",
    "MAX_ACTIVE_SESSIONS_PER_COMPANY",
    "EVENT_SILENCE_TIMEOUT_S",
    "WATCHDOG_KILL_GRACE_S",
    "WALL_CLOCK_CAP_S",
    "SUPPORTED_OUTPUT_LANGUAGES",
    "DEFAULT_OUTPUT_LANGUAGE",
    "CONTEXT_WINDOW",
    "CONSOLES_ROOT",
    "AttachmentTooLarge",
    "AttachmentTypeNotAllowed",
    "SessionLimitReached",
    "create_session",
    "is_copilot_session",
    "list_sessions",
    "load_meta",
    "update_meta",
    "update_tokens",
    "archive_session",
    "hard_delete_session",
    "append_turn",
    "read_turns",
    "stage_docs",
    "save_attachment",
    "get_attachment_path",
    "detect_image_type",
    "context_used",
    "context_used_from_usage",
    "session_exists",
    "active_count",
    "new_session_id",
    "new_turn_id",
    "meta_path",
    "turns_path",
    "workdir",
    "workdir_attachments",
    "attachments_dir",
    "hydrate_progress_path",
    "ask_progress_dir",
    "ask_progress_path",
    "summary_progress_path",
    "session_dir",
]
