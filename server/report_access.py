"""What leaves the firm: memo downloads, previews and exports.

Every successful memo download or preview is appended to
``data/_api/report_access.jsonl`` (resolved at call time) with who asked,
how they were signed in, which report, run, language and artifact, and
whether it was an explicit export or an in-app view. The web viewer, the
Mac and the iOS apps read documents through the same download URL, so a
fetch is a ``view`` unless the client says ``purpose=export`` — the flag
records intent among signed-in staff; it is not DRM.

Exports are also written to the firm audit trail, where admins already
look. Views are de-duplicated for a couple of minutes per reader so a PDF
viewer's range requests do not flood the log.

Also here: the file names readers get (``BSH – Company – Investment Memo –
2026-09-01 (EN).docx``) and the per-session de-duplication of reader
telemetry events.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

VIEW_DEDUPE_SECONDS = 120.0
PURPOSES = ("view", "export")

_LOCK = threading.RLock()
_recent_views: dict[tuple, float] = {}
_seen_reader_events: dict[tuple, float] = {}
_READER_EVENT_TTL_SECONDS = 12 * 3600.0
_MAX_SEEN = 5000


def _log_path() -> Path:
    return storage.DATA_DIR / "_api" / "report_access.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_purpose(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "export" if text == "export" else "view"


def _prune(table: dict[tuple, float], ttl: float, now: float) -> None:
    if len(table) < _MAX_SEEN:
        return
    for key in [k for k, ts in table.items() if now - ts > ttl]:
        table.pop(key, None)
    if len(table) >= _MAX_SEEN:
        # Still full of fresh keys: drop the oldest half.
        for key, _ts in sorted(table.items(), key=lambda kv: kv[1])[: len(table) // 2]:
            table.pop(key, None)


def record_access(
    *,
    report: dict,
    actor: str | None,
    auth_kind: str | None,
    role: str | None,
    language: str | None,
    artifact: str,
    purpose: str,
    file: str | None = None,
    fmt: str | None = None,
) -> dict | None:
    """Append one access row. Returns the row, or None when a repeat view
    inside the de-duplication window was skipped. Never raises."""
    purpose = normalize_purpose(purpose)
    report_id = str(report.get("id") or "")
    who = actor or {"shared": "service", "anon_dev": "anon-dev"}.get(auth_kind or "", "anonymous")
    now_mono = time.monotonic()
    if purpose == "view":
        key = (who, report_id, language, artifact, file, fmt)
        with _LOCK:
            last = _recent_views.get(key)
            if last is not None and now_mono - last < VIEW_DEDUPE_SECONDS:
                return None
            _recent_views[key] = now_mono
            _prune(_recent_views, VIEW_DEDUPE_SECONDS, now_mono)
    row = {
        "ts": _now(),
        "actor": who,
        "auth_kind": auth_kind or ("session" if actor else None),
        "role": role,
        "report_id": report_id,
        "company_id": report.get("company_id"),
        "run_id": report.get("run_id"),
        "kind": report.get("kind"),
        "language": language,
        "artifact": artifact,
        "format": fmt,
        "file": file,
        "purpose": purpose,
        "review_state": report.get("review_state") or "draft",
        "status": report.get("status"),
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return None
    if purpose == "export":
        try:
            from . import firm

            firm.record_audit(
                actor=actor,
                auth_kind=auth_kind,
                action="export report",
                path=f"/api/reports/{report_id}/download",
                status=200,
                company_id=report.get("company_id"),
                detail=" ".join(
                    str(part)
                    for part in (artifact, fmt or "", language or "", file or "")
                    if part
                ),
            )
        except Exception:  # noqa: BLE001 — logging must never break a download
            pass
    return row


def list_access(
    report_id: str,
    *,
    purpose: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """The newest access rows for one report (optionally one purpose)."""
    path = _log_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with _LOCK:
            lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("report_id") != report_id:
            continue
        if purpose and row.get("purpose") != purpose:
            continue
        rows.append(row)
        if len(rows) >= max(1, int(limit or 1)):
            break
    return rows


def recent_exports(report_id: str, *, limit: int = 5) -> list[dict]:
    """The last few explicit exports, shaped for the report detail."""
    return [
        {
            "ts": row.get("ts"),
            "actor": row.get("actor"),
            "role": row.get("role"),
            "language": row.get("language"),
            "artifact": row.get("artifact"),
            "format": row.get("format"),
        }
        for row in list_access(report_id, purpose="export", limit=limit)
    ]


def should_record_reader_event(session_key: str, report_id: str, event: str, language: str | None) -> bool:
    """True the first time a session sends this event for this report (and
    language); repeats are dropped for ``_READER_EVENT_TTL_SECONDS``."""
    now_mono = time.monotonic()
    key = (session_key, report_id, event, language or "")
    with _LOCK:
        last = _seen_reader_events.get(key)
        if last is not None and now_mono - last < _READER_EVENT_TTL_SECONDS:
            return False
        _seen_reader_events[key] = now_mono
        _prune(_seen_reader_events, _READER_EVENT_TTL_SECONDS, now_mono)
    return True


def reader_hash(identity: str | None) -> str | None:
    """A short stable hash for counting distinct readers without storing who."""
    if not identity:
        return None
    return hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:10]


# ---- file names ----------------------------------------------------------------

# EDGAR appends state and filer tokens to registrant names: "Occidental
# Petroleum Corp /De/", "Foo Inc /MD/", "Bar Holdings /NEW/".
_EDGAR_SUFFIX_RE = re.compile(r"\s*/(?:[A-Za-z]{2}|NEW|ADR|CAN|FI|BERMUDA)/?\s*$", re.I)
_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]+")


def display_company_name(name: str | None) -> str:
    """A company name that is safe as one path component.

    Prefers ``memo_prep.company_display_name`` when it exists; otherwise
    strips EDGAR suffix tokens, path separators and control characters.
    """
    raw = str(name or "").strip()
    try:
        from . import memo_prep

        helper = getattr(memo_prep, "company_display_name", None)
        if callable(helper):
            cleaned = str(helper(raw) or "").strip()
            if cleaned:
                raw = cleaned
    except Exception:  # noqa: BLE001
        pass
    previous = None
    while previous != raw:
        previous = raw
        raw = _EDGAR_SUFFIX_RE.sub("", raw).strip()
    raw = _UNSAFE_RE.sub(" ", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -–")
    return raw[:120] or "Company"


def _memo_date(report: dict) -> str:
    reader = report.get("reader") if isinstance(report.get("reader"), dict) else {}
    for candidate in (reader.get("memo_as_of"), report.get("run_id"), report.get("created_at")):
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(candidate or ""))
        if match:
            return match.group(0)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _type_label(report: dict) -> str:
    from . import memo_prep

    if memo_prep.is_buffett_kind(report.get("kind")):
        return "Buffett-Method Memo"
    return "Investment Memo"


def download_filename(
    report: dict,
    *,
    language: str | None,
    ext: str,
    artifact: str = "memo",
) -> str:
    """``BSH – {display name} – {type} – {YYYY-MM-DD} ({EN|中文}).{ext}``."""
    name = display_company_name(report.get("company_name") or report.get("company_id"))
    label = "Internal Diligence Memo" if artifact == "internal" else _type_label(report)
    date = _memo_date(report)
    if language == "zh":
        lang_tag = " (中文)"
    elif language == "en":
        lang_tag = " (EN)"
    elif language == "both":
        lang_tag = " (EN + 中文)"
    else:
        lang_tag = ""
    return f"BSH – {name} – {label} – {date}{lang_tag}.{ext.lstrip('.')}"
