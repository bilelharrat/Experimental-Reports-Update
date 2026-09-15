"""Transcript library: expert, founder and customer calls as searchable text with highlights."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

_LOCK = threading.RLock()
def _dir() -> Path:
    return storage.DATA_DIR / "transcripts"
KINDS = ("expert_call", "founder_call", "customer_call", "reference_call", "earnings_call", "internal", "other")
TRANSCRIPT_MAX_CHARS = 400_000

_VTT_TS = re.compile(r"^\s*(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}\s*-->.*$")
_SRT_INDEX = re.compile(r"^\d+$")
_TS = r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"
_SPEAKER = r"[A-Z][A-Za-z0-9 .'-]{0,40}"
_BRACKETED_TS = re.compile(r"[\[(]\s*" + _TS + r"\s*[\])]")
_ONLY_TS = re.compile(r"^" + _TS + r"$")
_LEADING_TS_BEFORE_SPEAKER = re.compile(r"^" + _TS + r"\s+(?=" + _SPEAKER + r":)")
_LEADING_HMS = re.compile(r"^\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?\s+")
_SPEAKER_HEADER_TS = re.compile(r"^(" + _SPEAKER.replace("{0,40}", "{0,40}?") + r")(?:\s{2,}|\t)" + _TS + r"$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path(transcript_id: str) -> Path:
    safe = re.sub(r"[^a-z0-9_-]", "", str(transcript_id or "").lower())
    if not safe:
        raise ValueError("Invalid transcript id")
    return _dir() / f"{safe}.json"


def normalize_text(raw: str, *, filename: str = "") -> str:
    """Strip VTT/SRT cue lines and inline timestamps; keep speaker labels."""
    lines = []
    src = [line.strip() for line in str(raw or "").replace("\r\n", "\n").split("\n")]
    for i, stripped in enumerate(src):
        if not stripped or stripped == "WEBVTT" or stripped.startswith(("NOTE ", "STYLE", "Kind:", "Language:")):
            continue
        if _VTT_TS.match(stripped):
            continue
        if _SRT_INDEX.match(stripped):
            nxt = next((x for x in src[i + 1:] if x), "")
            if _VTT_TS.match(nxt):
                continue
        if _ONLY_TS.match(stripped):
            continue
        stripped = _BRACKETED_TS.sub("", stripped).strip()
        stripped = _LEADING_TS_BEFORE_SPEAKER.sub("", stripped)
        stripped = _LEADING_HMS.sub("", stripped)
        stripped = _SPEAKER_HEADER_TS.sub(r"\1", stripped).strip()
        stripped = re.sub(r"<[^>]+>", "", stripped)
        if stripped:
            lines.append(stripped)
    # merge consecutive fragments from the same cue into paragraphs
    out: list[str] = []
    for line in lines:
        if out and not re.match(r"^[A-Z][A-Za-z .'-]{0,40}:", line) and len(out[-1]) < 400 and not out[-1].endswith((".", "?", "!")):
            out[-1] = out[-1] + " " + line
        else:
            out.append(line)
    return "\n".join(out)


def _load(transcript_id: str) -> dict | None:
    path = _path(transcript_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save(item: dict) -> None:
    path = _path(item["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _summary(item: dict) -> dict:
    text = item.get("text") or ""
    return {
        key: item.get(key)
        for key in ("id", "title", "kind", "company_id", "company_name", "call_date", "participants", "tags", "created_by", "created_at", "source_filename")
    } | {
        "word_count": len(text.split()),
        "highlight_count": len(item.get("highlights") or []),
        "preview": " ".join(text.split()[:40]),
    }


def add_transcript(
    *,
    title: str,
    text: str,
    kind: str = "expert_call",
    company_id: str | None = None,
    call_date: str | None = None,
    participants: list[str] | str | None = None,
    tags: list[str] | str | None = None,
    created_by: str | None = None,
    source_filename: str = "",
) -> dict:
    body = normalize_text(text, filename=source_filename)
    if not body.strip():
        raise ValueError("Transcript text is empty")
    if len(body) > TRANSCRIPT_MAX_CHARS:
        raise ValueError(f"Transcript text is too long, max {TRANSCRIPT_MAX_CHARS} characters")
    kind = str(kind or "other").lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")

    def _list(value: Any) -> list[str]:
        if isinstance(value, str):
            value = re.split(r"[,\n;]", value)
        elif value is not None and not isinstance(value, (list, tuple)):
            raise ValueError("participants and tags must be a string or list")
        return [str(v).strip() for v in (value or []) if str(v).strip()][:20]

    if company_id is not None and not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    company = storage.get_company(company_id) if company_id else None
    item = {
        "id": f"tr-{uuid.uuid4().hex[:10]}",
        "title": " ".join(str(title or "").split())[:200] or (source_filename or "Transcript"),
        "kind": kind,
        "company_id": company_id or None,
        "company_name": (company or {}).get("name") if company else None,
        "call_date": str(call_date or "")[:10] or _now()[:10],
        "participants": _list(participants),
        "tags": _list(tags),
        "text": body,
        "highlights": [],
        "source_filename": source_filename[:200],
        "created_by": created_by or "",
        "created_at": _now(),
    }
    with _LOCK:
        _save(item)
    return item


def get_transcript(transcript_id: str) -> dict | None:
    with _LOCK:
        return _load(transcript_id)


def delete_transcript(transcript_id: str) -> bool:
    with _LOCK:
        path = _path(transcript_id)
        if not path.exists():
            return False
        path.unlink()
    return True


def add_highlight(transcript_id: str, *, text: str, note: str = "", created_by: str | None = None) -> dict:
    quote = " ".join(str(text or "").split())[:1000]
    if not quote:
        raise ValueError("Highlight text is empty")
    with _LOCK:
        item = _load(transcript_id)
        if item is None:
            raise LookupError("Transcript not found")
        highlight = {"id": f"hl-{uuid.uuid4().hex[:8]}", "text": quote, "note": str(note or "")[:1000], "created_by": created_by or "", "at": _now()}
        item.setdefault("highlights", []).append(highlight)
        _save(item)
    return item


def remove_highlight(transcript_id: str, highlight_id: str) -> dict | None:
    with _LOCK:
        item = _load(transcript_id)
        if item is None:
            return None
        item["highlights"] = [h for h in item.get("highlights") or [] if h.get("id") != highlight_id]
        _save(item)
    return item


def all_transcripts() -> list[dict]:
    out: list[dict] = []
    if _dir().exists():
        for path in _dir().glob("*.json"):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
    return out


def list_transcripts(*, company_id: str | None = None, kind: str | None = None, q: str = "", limit: int = 100) -> dict:
    items = all_transcripts()
    if company_id:
        items = [t for t in items if t.get("company_id") == company_id]
    if kind:
        items = [t for t in items if t.get("kind") == kind]
    terms = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    if terms:
        def hit(t: dict) -> bool:
            hay = " ".join([t.get("title") or "", t.get("text") or "", " ".join(t.get("tags") or []), " ".join(t.get("participants") or [])]).lower()
            return all(term in hay for term in terms)
        items = [t for t in items if hit(t)]
    items.sort(key=lambda t: (t.get("call_date") or "", t.get("created_at") or ""), reverse=True)
    return {"items": [_summary(t) for t in items[:limit]], "count": len(items)}
