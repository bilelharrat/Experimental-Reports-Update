"""Firm memory search: one query across companies, memos, decisions, reference calls,
founder updates, comments, chat and transcripts. Deterministic tf-idf, excerpts show the match."""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import Counter
from typing import Any

from . import comps, decisions_store, firm, ic_room, portfolio, storage, transcripts

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']{1,}")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "its", "our", "their", "into", "not", "but", "you", "they", "them", "than", "then"}

_LOCK = threading.Condition()
_INDEXES: dict[str, dict[str, Any]] = {}
CACHE_TTL_S = 45.0


class _DataDirChanged(Exception):
    pass


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def _doc(kind: str, *, title: str, text: str, company_id: str | None, ref: str, at: str | None = None, extra: dict | None = None) -> dict:
    return {"kind": kind, "title": title, "text": text, "company_id": company_id, "ref": ref, "at": at, **(extra or {})}


def _build(data_dir: str) -> list[dict]:
    docs: list[dict] = []
    companies = storage.list_companies()
    names = {c.get("id"): c.get("name") or c.get("id") for c in companies}
    reports = storage.reports_by_company()
    for c in companies:
        if str(storage.DATA_DIR) != data_dir:
            raise _DataDirChanged(data_dir)
        cid = c.get("id")
        if not cid:
            continue
        try:
            _build_company(docs, c, cid, names, reports.get(cid, []))
        except ValueError:
            logger.warning("firm search skipped company with an invalid id: %r", cid)
    for c in firm.all_comments():
        docs.append(_doc("comment", title=f"{names.get(c.get('company_id'), c.get('company_id'))} — comment by {c.get('author_handle')}", text=c.get("text") or "", company_id=c.get("company_id"), ref=c.get("id") or "", at=c.get("created_at"),
                         extra={"target": c.get("target"), "resolved": bool(c.get("resolved_at"))}))
    for m in firm.all_messages():
        docs.append(_doc("chat", title=f"#{m.get('channel')} — {m.get('author_handle')}", text=m.get("text") or "", company_id=m.get("company_id"), ref=m.get("id") or "", at=m.get("at"), extra={"channel": m.get("channel")}))
    for t in transcripts.all_transcripts():
        paragraphs = [p for p in (t.get("text") or "").split("\n") if p.strip()]
        # index in ~1200-char chunks so excerpts stay local
        chunk, size, idx = [], 0, 0
        for p in paragraphs + [""]:
            if (size + len(p) > 1200 and chunk) or p == "":
                if chunk:
                    docs.append(_doc("transcript", title=f"{t.get('title')} ({t.get('kind')})", text="\n".join(chunk), company_id=t.get("company_id"), ref=t.get("id") or "", at=t.get("call_date"), extra={"chunk": idx}))
                    idx += 1
                chunk, size = [], 0
            if p:
                chunk.append(p)
                size += len(p)
        for h in t.get("highlights") or []:
            docs.append(_doc("highlight", title=f"{t.get('title')} — highlight", text=f"{h.get('text')} {h.get('note') or ''}", company_id=t.get("company_id"), ref=t.get("id") or "", at=h.get("at")))
    for d in docs:
        d["_tf"] = Counter(_tokens(f"{d['title']} {d['text']}"))
    return docs


def _build_company(docs: list[dict], c: dict, cid: str, names: dict, reports: list[dict]) -> None:
    desc = c.get("description")
    if isinstance(desc, dict):
        desc = desc.get("en") or ""
    docs.append(_doc("company", title=names[cid], text=f"{names[cid]} {desc or ''} {c.get('industry') or ''} {c.get('sector') or ''}", company_id=cid, ref=cid))
    for d in decisions_store.list_decisions(cid).get("items") or []:
        docs.append(_doc("decision", title=f"{names[cid]} — {d.get('verdict', '').title()}", text=d.get("explanation") or "", company_id=cid, ref=d.get("id") or "", at=d.get("decided_at"),
                         extra={"verdict": d.get("verdict")}))
        for r in d.get("retrospectives") or []:
            if isinstance(r, dict) and r.get("note"):
                docs.append(_doc("retrospective", title=f"{names[cid]} — retrospective", text=r["note"], company_id=cid, ref=d.get("id") or "", at=r.get("at")))
    for ref in ic_room.list_reference_calls(cid).get("items") or []:
        text = " ".join([ref.get("notes") or ""] + list(ref.get("strengths") or []) + list(ref.get("concerns") or []) + list(ref.get("quotes") or []))
        docs.append(_doc("reference_call", title=f"{names[cid]} — {ref.get('contact')} ({ref.get('relation')})", text=text, company_id=cid, ref=ref.get("id") or "", at=ref.get("call_date")))
    record = portfolio.get_portfolio(cid) if portfolio.has_record(cid) else None
    for u in (record or {}).get("updates") or []:
        docs.append(_doc("founder_update", title=f"{names[cid]} — {u.get('subject') or 'founder update'}", text=u.get("text") or "", company_id=cid, ref=u.get("id") or "", at=u.get("as_of")))
    _path, package = comps._latest_memo_package(cid, reports)
    if package:
        for section, text in comps._memo_text_blocks(package)[:400]:
            docs.append(_doc("memo", title=f"{names[cid]} — memo · {section}", text=text, company_id=cid, ref=section))


def _refresh(data_dir: str, entry: dict[str, Any], generation: int, version: int) -> None:
    try:
        docs = _build(data_dir)
    except BaseException:
        with _LOCK:
            entry["building"] = False
            _LOCK.notify_all()
        raise
    with _LOCK:
        entry.update(docs=docs, built_at=time.monotonic(), built_generation=generation, reports_version=version, building=False)
        _LOCK.notify_all()


def _refresh_in_background(data_dir: str, entry: dict[str, Any], generation: int, version: int) -> None:
    try:
        _refresh(data_dir, entry, generation, version)
    except _DataDirChanged:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("firm search index rebuild failed")


def _docs() -> list[dict]:
    data_dir = str(storage.DATA_DIR)
    version = storage.reports_version()
    with _LOCK:
        for other in [k for k in _INDEXES if k != data_dir]:
            del _INDEXES[other]
        entry = _INDEXES.setdefault(data_dir, {"docs": None, "built_at": 0.0, "generation": 0, "built_generation": 0, "reports_version": None, "building": False})
        while entry["docs"] is None and entry["building"]:
            _LOCK.wait()
        docs = entry["docs"]
        if docs is not None:
            stale = (
                entry["built_generation"] != entry["generation"]
                or entry["reports_version"] != version
                or time.monotonic() - entry["built_at"] > CACHE_TTL_S
            )
            if stale and not entry["building"]:
                entry["building"] = True
                threading.Thread(
                    target=_refresh_in_background, args=(data_dir, entry, entry["generation"], version), name="firm-search-index", daemon=True
                ).start()
            return docs
        entry["building"] = True
        generation = entry["generation"]
    _refresh(data_dir, entry, generation, version)
    return entry["docs"]


def invalidate() -> None:
    with _LOCK:
        for entry in _INDEXES.values():
            entry["generation"] += 1


def _excerpt(text: str, terms: list[str], width: int = 110) -> str:
    flat = " ".join((text or "").split())
    low = flat.lower()
    pos = -1
    for term in terms:
        pos = low.find(term)
        if pos >= 0:
            break
    if pos < 0:
        return flat[: width * 2] + ("…" if len(flat) > width * 2 else "")
    lo = max(0, pos - width)
    hi = min(len(flat), pos + width)
    return ("…" if lo > 0 else "") + flat[lo:hi] + ("…" if hi < len(flat) else "")


def search(query: str, *, kinds: list[str] | None = None, company_id: str | None = None, limit: int = 30) -> dict:
    terms = _tokens(query)
    if not terms:
        return {"query": query, "items": [], "total": 0}
    docs = _docs()
    if kinds:
        docs = [d for d in docs if d["kind"] in kinds]
    if company_id:
        docs = [d for d in docs if d.get("company_id") == company_id]
    n = max(1, len(docs))
    df = Counter()
    for d in docs:
        for term in set(terms):
            if d["_tf"].get(term):
                df[term] += 1
    phrase = " ".join(terms)
    scored = []
    for d in docs:
        score = 0.0
        matched = 0
        for term in terms:
            tf = d["_tf"].get(term, 0)
            if tf:
                matched += 1
                score += (1 + math.log(tf)) * math.log(1 + n / (1 + df[term]))
        if not matched:
            continue
        if matched == len(terms):
            score *= 1.5
        if len(terms) > 1 and phrase in f"{d['title']} {d['text']}".lower():
            score *= 1.5
        if d["kind"] in {"decision", "memo"}:
            score *= 1.1
        scored.append((score, d))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("at") or ""))
    items = []
    for score, d in scored[:limit]:
        items.append({
            "kind": d["kind"], "title": d["title"], "company_id": d.get("company_id"), "ref": d["ref"], "at": d.get("at"),
            "score": round(score, 3), "excerpt": _excerpt(d["text"], terms),
            **{k: v for k, v in d.items() if k in {"verdict", "channel", "target", "resolved", "chunk"}},
        })
    return {"query": query, "items": items, "total": len(scored), "kinds": sorted({d["kind"] for _s, d in scored})}
