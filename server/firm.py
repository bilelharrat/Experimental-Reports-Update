"""Firm layer: comments with @mentions, internal chat, and the audit trail.

All three are append-style records keyed by who wrote them. Mentions are resolved
against known user emails (the local part) so an inbox can be built per person.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from . import auth_store, company_paths, storage

_LOCK = threading.RLock()

def _comments_dir() -> Path:
    return storage.DATA_DIR / "comments"


def _chat_dir() -> Path:
    return storage.DATA_DIR / "chat"


def _audit_file() -> Path:
    return storage.DATA_DIR / "audit" / "audit.jsonl"

MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._-]+)")
COMMENT_TARGET_KINDS = ("company", "report", "decision", "section", "document", "kpi", "transcript")
# Reader flags on a report (G7): a comment may name what is wrong with the
# text it quotes. Plain comments carry no flag.
FLAG_KINDS = ("wrong_number", "unsupported", "unclear", "missing", "tone")
FLAG_LABELS = {
    "wrong_number": "Flagged: wrong number",
    "unsupported": "Flagged: unsupported claim",
    "unclear": "Flagged: unclear",
    "missing": "Flagged: something missing",
    "tone": "Flagged: tone",
}
QUOTE_MAX_CHARS = 300
COMMENT_LANGUAGES = ("en", "zh")
# Target kinds whose ``ref`` is a report id.
REPORT_TARGET_KINDS = ("report", "section")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_KEY_SAFE = "abcdefghijklmnopqrstuvwxyz0123456789_:-."
_KEY_MAX_BYTES = 200


def _key(value: str) -> str:
    """Reversible file-name form of a channel id; safe ASCII ids stay as they are."""
    text = str(value or "").strip().lower()
    if not text or text.strip(".") == "" or "/" in text or "\\" in text:
        raise ValueError("Invalid channel")
    encoded = quote(text, safe=_KEY_SAFE)
    if len(encoded.encode("utf-8")) > _KEY_MAX_BYTES:
        encoded = encoded[:_KEY_MAX_BYTES - 13].rstrip("%") + "~" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return encoded


COMMENT_MAX_CHARS = 4000
CHAT_MESSAGE_MAX_CHARS = 8000


def handle_for(email: str | None, *, auth_kind: str | None = None) -> str:
    """`ana@firm.com` → `ana`; the shared service token → `service`; anonymous dev → `dev`."""
    if email:
        return email.split("@", 1)[0].lower()
    return "service" if auth_kind == "shared" else "dev"


def audit_actor(email: str | None, auth_kind: str | None) -> str:
    """Who an audit row names: the session email, `service` for the shared
    token, `anon-dev` for local anonymous dev, else `anonymous`."""
    if email:
        return email
    return {"shared": "service", "anon_dev": "anon-dev"}.get(auth_kind or "", "anonymous")


def known_handles() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for email in auth_store.list_user_emails():
            out[handle_for(email)] = email
    except Exception:  # noqa: BLE001
        pass
    return out


def parse_mentions(text: str) -> list[str]:
    found = []
    for match in MENTION_RE.finditer(text or ""):
        handle = match.group(1).lower().rstrip(".")
        if handle and handle not in found:
            found.append(handle)
    return found


# ---- Comments ------------------------------------------------------------------------------


def _comments_path(company_id: str) -> Path:
    return _comments_dir() / f"{company_paths.storage_key(company_id)}.json"


def _load_comments(company_id: str) -> list[dict]:
    path = _comments_path(company_id)
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("items") or [])
    except Exception:  # noqa: BLE001
        return []


def _save_comments(company_id: str, items: list[dict]) -> None:
    path = _comments_path(company_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def list_comments(company_id: str, *, target_kind: str | None = None, target_ref: str | None = None, include_resolved: bool = True) -> dict:
    with _LOCK:
        items = _load_comments(company_id)
    items = [c for c in items if not c.get("company_id") or c.get("company_id") == company_id]
    if target_kind:
        items = [c for c in items if (c.get("target") or {}).get("kind") == target_kind]
    if target_ref:
        items = [c for c in items if (c.get("target") or {}).get("ref") == target_ref]
    if not include_resolved:
        items = [c for c in items if not c.get("resolved_at")]
    items.sort(key=lambda c: c.get("created_at") or "")
    return {"company_id": company_id, "items": items, "open_count": sum(1 for c in items if not c.get("resolved_at"))}


def add_comment(
    company_id: str,
    *,
    text: str,
    author: str | None,
    target: dict | None = None,
    parent_id: str | None = None,
    flag: str | None = None,
    quote: str | None = None,
    language: str | None = None,
) -> dict:
    """Append a comment. ``flag`` (one of ``FLAG_KINDS``), ``quote`` (the
    selected text, up to ``QUOTE_MAX_CHARS``) and ``language`` (en | zh) are
    optional and only stored when given, so plain comments keep their shape.
    A flag with no text gets the flag's label as its text."""
    flag_value = str(flag or "").strip().lower() or None
    if flag_value is not None and flag_value not in FLAG_KINDS:
        raise ValueError(f"flag must be one of {', '.join(FLAG_KINDS)}")
    language_value = str(language or "").strip().lower() or None
    if language_value is not None and language_value not in COMMENT_LANGUAGES:
        raise ValueError("language must be 'en' or 'zh'")
    quote_value = " ".join(str(quote or "").split())[:QUOTE_MAX_CHARS] or None
    body = " ".join(str(text or "").split())
    if not body and flag_value:
        body = FLAG_LABELS[flag_value]
    if not body:
        raise ValueError("Comment text is empty")
    if len(body) > COMMENT_MAX_CHARS:
        raise ValueError(f"Comment is too long, max {COMMENT_MAX_CHARS} characters")
    if target is not None and not isinstance(target, dict):
        raise ValueError("target must be an object")
    target = target or {"kind": "company", "ref": company_id}
    kind = str(target.get("kind") or "company")
    if kind not in COMMENT_TARGET_KINDS:
        raise ValueError(f"target.kind must be one of {', '.join(COMMENT_TARGET_KINDS)}")
    item = {
        "id": f"cmt-{uuid.uuid4().hex[:10]}",
        "company_id": company_id,
        "author": author or "",
        "author_handle": handle_for(author),
        "text": body,
        "mentions": parse_mentions(body),
        "target": {"kind": kind, "ref": str(target.get("ref") or company_id)[:200], "label": str(target.get("label") or "")[:200]},
        "parent_id": parent_id,
        "created_at": _now(),
        "resolved_at": None,
        "resolved_by": None,
    }
    if flag_value:
        item["flag"] = flag_value
    if quote_value:
        item["quote"] = quote_value
    if language_value:
        item["language"] = language_value
    with _LOCK:
        items = _load_comments(company_id)
        if parent_id and not any(c.get("id") == parent_id for c in items):
            raise ValueError("parent comment not found")
        items.append(item)
        _save_comments(company_id, items)
    return item


def resolve_comment(company_id: str, comment_id: str, *, by: str | None, resolved: bool = True) -> dict | None:
    with _LOCK:
        items = _load_comments(company_id)
        for item in items:
            if item.get("id") == comment_id:
                item["resolved_at"] = _now() if resolved else None
                item["resolved_by"] = (by or "") if resolved else None
                _save_comments(company_id, items)
                return item
    return None


def delete_comment(company_id: str, comment_id: str) -> bool:
    with _LOCK:
        items = _load_comments(company_id)
        kept = [c for c in items if c.get("id") != comment_id and c.get("parent_id") != comment_id]
        if len(kept) == len(items):
            return False
        _save_comments(company_id, kept)
    return True


def all_comments() -> list[dict]:
    out: list[dict] = []
    if _comments_dir().exists():
        for path in _comments_dir().glob("*.json"):
            try:
                out.extend(json.loads(path.read_text(encoding="utf-8")).get("items") or [])
            except Exception:  # noqa: BLE001
                continue
    return out


def _is_report_comment(item: dict, report_id: str | None = None) -> bool:
    target = item.get("target") or {}
    if target.get("kind") not in REPORT_TARGET_KINDS:
        return False
    return report_id is None or target.get("ref") == report_id


def report_comments(company_id: str, report_id: str, *, include_resolved: bool = True, flags_only: bool = False) -> dict:
    """Comments and reader flags on one report, oldest first, with counts.
    Comments on a report live in its company's comment file (target kind
    ``report`` or ``section``, ``ref`` = the report id)."""
    with _LOCK:
        items = _load_comments(company_id)
    items = [c for c in items if _is_report_comment(c, report_id)]
    open_top = [c for c in items if not c.get("resolved_at") and not c.get("parent_id")]
    counts = {
        "open_comments": sum(1 for c in open_top if not c.get("flag")),
        "open_flags": sum(1 for c in open_top if c.get("flag")),
    }
    if flags_only:
        items = [c for c in items if c.get("flag")]
    if not include_resolved:
        items = [c for c in items if not c.get("resolved_at")]
    items.sort(key=lambda c: c.get("created_at") or "")
    return {
        "company_id": company_id,
        "report_id": report_id,
        "items": items,
        "open_count": counts["open_comments"] + counts["open_flags"],
        **counts,
    }


_COUNTS_CACHE: dict[str, Any] = {"key": None, "counts": {}}


def report_comment_counts() -> dict[str, dict[str, int]]:
    """``{report_id: {"open_comments": n, "open_flags": n}}`` over every
    comment file — open, top-level items only (replies belong to a thread).
    Cached on the comment files' sizes and modification times, so the
    Reports list does not re-read them on every request."""
    folder = _comments_dir()
    stamp: list[tuple[str, int, int]] = []
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                st = path.stat()
            except OSError:
                continue
            stamp.append((str(path), st.st_mtime_ns, st.st_size))
    key = (str(folder), tuple(sorted(stamp)))
    with _LOCK:
        if _COUNTS_CACHE["key"] == key:
            return {rid: dict(v) for rid, v in _COUNTS_CACHE["counts"].items()}
    counts: dict[str, dict[str, int]] = {}
    for item in all_comments():
        if not isinstance(item, dict) or not _is_report_comment(item):
            continue
        if item.get("resolved_at") or item.get("parent_id"):
            continue
        rid = str((item.get("target") or {}).get("ref") or "")
        if not rid:
            continue
        entry = counts.setdefault(rid, {"open_comments": 0, "open_flags": 0})
        entry["open_flags" if item.get("flag") else "open_comments"] += 1
    with _LOCK:
        _COUNTS_CACHE["key"] = key
        _COUNTS_CACHE["counts"] = counts
    return {rid: dict(v) for rid, v in counts.items()}


# ---- Chat ----------------------------------------------------------------------------------


def _channel_path(channel: str) -> Path:
    return _chat_dir() / f"{_key(channel)}.jsonl"


def _channel_id(path: Path) -> str:
    """The channel id a chat file was written for: its last message's ``channel``, else the decoded file name."""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            last = json.loads(lines[-1])
            if isinstance(last, dict) and isinstance(last.get("channel"), str) and last["channel"].strip():
                return last["channel"]
    except Exception:  # noqa: BLE001
        pass
    return unquote(path.stem)


def list_channels() -> list[dict]:
    channels: dict[str, dict] = {"general": {"id": "general", "label": "General", "kind": "firm"}}
    if _chat_dir().exists():
        for path in _chat_dir().glob("*.jsonl"):
            cid = _channel_id(path)
            if cid.startswith("company:"):
                company_id = cid.split(":", 1)[1]
                company = storage.get_company(company_id) or {}
                channels[cid] = {"id": cid, "label": company.get("name") or company_id, "kind": "company", "company_id": company_id}
            elif cid not in channels:
                channels[cid] = {"id": cid, "label": cid.replace("-", " ").title(), "kind": "firm"}
    out = []
    for cid, meta in channels.items():
        last = None
        count = 0
        try:
            path = _channel_path(cid)
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []
            count = len(lines)
            if lines:
                last = json.loads(lines[-1])
        except Exception:  # noqa: BLE001
            pass
        out.append(dict(meta, message_count=count, last_message=last))
    out.sort(key=lambda c: ((c.get("last_message") or {}).get("at") or "", c["id"]), reverse=True)
    return out


def read_messages(channel: str, *, since: str | None = None, limit: int = 200) -> dict:
    path = _channel_path(channel)
    items: list[dict] = []
    if path.exists():
        with _LOCK:
            lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if since and (msg.get("at") or "") < since:
                continue
            items.append(msg)
    items = items[-max(1, min(limit, 1000)):]
    return {"channel": channel, "items": items, "latest": items[-1]["at"] if items else since}


def post_message(channel: str, *, text: str, author: str | None, company_id: str | None = None, report_id: str | None = None) -> dict:
    body = str(text or "").strip()
    if not body:
        raise ValueError("Message is empty")
    if len(body) > CHAT_MESSAGE_MAX_CHARS:
        raise ValueError(f"Message is too long, max {CHAT_MESSAGE_MAX_CHARS} characters")
    path = _channel_path(channel)
    msg = {
        "id": f"msg-{uuid.uuid4().hex[:10]}",
        "channel": str(channel or "").strip().lower(),
        "author": author or "",
        "author_handle": handle_for(author),
        "text": body,
        "mentions": parse_mentions(body),
        "company_id": company_id or None,
        "report_id": report_id or None,
        "at": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        msg["at"] = _now()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def all_messages() -> list[dict]:
    out: list[dict] = []
    if _chat_dir().exists():
        for path in _chat_dir().glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    return out


# ---- Mentions inbox --------------------------------------------------------------------------


def mentions_for(email: str | None, *, days: int = 30, auth_kind: str | None = None) -> dict:
    handle = handle_for(email, auth_kind=auth_kind)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    items: list[dict] = []
    for c in all_comments():
        if handle in (c.get("mentions") or []) and (c.get("created_at") or "") >= cutoff:
            items.append({
                "kind": "comment", "id": c["id"], "at": c.get("created_at"), "from": c.get("author_handle"),
                "text": c.get("text"), "company_id": c.get("company_id"), "target": c.get("target"),
                "resolved": bool(c.get("resolved_at")),
            })
    for m in all_messages():
        if handle in (m.get("mentions") or []) and (m.get("at") or "") >= cutoff:
            items.append({
                "kind": "chat", "id": m["id"], "at": m.get("at"), "from": m.get("author_handle"),
                "text": m.get("text"), "company_id": m.get("company_id"), "channel": m.get("channel"), "resolved": False,
            })
    items.sort(key=lambda i: i.get("at") or "", reverse=True)
    return {"handle": handle, "items": items, "open_count": sum(1 for i in items if not i.get("resolved"))}


# ---- Audit trail ---------------------------------------------------------------------------------


def record_audit(*, actor: str | None, action: str, path: str, status: int, company_id: str | None = None, detail: str = "", auth_kind: str | None = None) -> None:
    entry = {
        "at": _now(),
        "actor": audit_actor(actor, auth_kind),
        "action": action,
        "path": path,
        "status": status,
        "company_id": company_id,
        "detail": str(detail or "")[:500],
    }
    _audit_file().parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with _audit_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


_COMPANY_PATH_RE = re.compile(r"/api/(?:companies|portfolio)/([^/?#]+)")


def company_from_path(path: str) -> str | None:
    match = _COMPANY_PATH_RE.search(path or "")
    if not match:
        return None
    cid = match.group(1)
    return None if cid in {"reserves", "search", "match", "autocomplete"} else cid


def list_audit(*, company_id: str | None = None, actor: str | None = None, limit: int = 200) -> dict:
    items: list[dict] = []
    if _audit_file().exists():
        with _LOCK:
            lines = _audit_file().read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            cid = company_from_path(entry.get("path") or "") or entry.get("company_id")
            entry["company_id"] = cid
            if company_id and cid != company_id:
                continue
            if actor and entry.get("actor") != actor:
                continue
            items.append(entry)
            if len(items) >= max(1, min(limit, 2000)):
                break
    return {"items": items}


def describe_action(method: str, path: str) -> str:
    """Human label for an audit row, derived from the route shape."""
    p = re.sub(r"/api/", "", path)
    p = re.sub(r"/[a-z0-9_-]{6,}(?=/|$)", "/…", p)
    verb = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(method.upper(), method.lower())
    return f"{verb} {p}"


__all__ = [name for name in globals() if not name.startswith("_")] + ["Any"]
