"""IC room: reference calls, meeting votes and comparable past decisions.

Reference calls and votes are records people enter. Comparables are a deterministic
overlap score over company records and the decision ledger, with the reasons listed —
no model, no inference beyond the rules written here.
"""
from __future__ import annotations

import json
import math
import re
import threading
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from . import company_paths, decisions_store, storage, thesis_store

_LOCK = threading.RLock()

RELATIONS = ("customer", "former_employee", "investor", "partner", "founder_peer", "other")
VOTES = ("invest", "pass", "more_work")
VOTE_TO_VERDICT = {"invest": "invest", "pass": "pass", "more_work": "watch"}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "its", "our", "their",
    "into", "over", "about", "than", "then", "they", "them", "who", "how", "what", "when", "where", "which", "while",
    "company", "companies", "platform", "based", "using", "help", "helps", "provides", "provider", "solution", "solutions",
    "inc", "ltd", "llc", "corp", "startup", "business", "businesses", "customers", "customer", "software", "service", "services",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _company_dir(company_id: str):
    return company_paths.company_dir(company_id)


def _read(company_id: str, name: str, default: Any) -> Any:
    path = _company_dir(company_id) / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(company_id: str, name: str, payload: Any) -> None:
    path = _company_dir(company_id) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _clean(value: Any, limit: int = 2000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _score_1_to_5(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be 1–5")
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be 1–5") from exc
    if not math.isfinite(number) or not number.is_integer() or not 1 <= number <= 5:
        raise ValueError(f"{label} must be a whole number from 1 to 5")
    return int(number)


def _call_date(value: Any) -> str:
    text = _clean(value, 10)
    if not text:
        return _now()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("call_date must be YYYY-MM-DD") from exc


def _clean_list(value: Any, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"\n|;", value)]
    if not isinstance(value, list):
        return []
    out = [_clean(v, 500) for v in value]
    return [v for v in out if v][:limit]


# ---- Reference calls ---------------------------------------------------------------------


def list_reference_calls(company_id: str) -> dict:
    with _LOCK:
        items = _read(company_id, "reference_calls.json", {}).get("items") or []
    items.sort(key=lambda item: item.get("call_date") or "", reverse=True)
    ratings = [item["rating"] for item in items if isinstance(item.get("rating"), (int, float))]
    return {
        "company_id": company_id,
        "items": items,
        "count": len(items),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "concern_count": sum(len(item.get("concerns") or []) for item in items),
    }


def add_reference_call(company_id: str, payload: dict, *, created_by: str | None = None) -> dict:
    contact = _clean(payload.get("contact"), 200)
    if not contact:
        raise ValueError("contact is required")
    relation = _clean(payload.get("relation"), 40).lower() or "other"
    if relation not in RELATIONS:
        raise ValueError(f"relation must be one of {', '.join(RELATIONS)}")
    rating = _score_1_to_5(payload.get("rating"), "rating")
    call_date = _call_date(payload.get("call_date"))
    item = {
        "id": f"ref-{uuid.uuid4().hex[:10]}",
        "contact": contact,
        "role": _clean(payload.get("role"), 200),
        "relation": relation,
        "call_date": call_date,
        "strengths": _clean_list(payload.get("strengths")),
        "concerns": _clean_list(payload.get("concerns")),
        "quotes": _clean_list(payload.get("quotes"), 8),
        "rating": rating,
        "would_back_again": payload.get("would_back_again") if isinstance(payload.get("would_back_again"), bool) else None,
        "notes": _clean(payload.get("notes"), 4000),
        "created_at": _now(),
        "created_by": created_by or "",
    }
    with _LOCK:
        data = _read(company_id, "reference_calls.json", {})
        items = list(data.get("items") or [])
        items.append(item)
        _write(company_id, "reference_calls.json", {"items": items})
    return list_reference_calls(company_id)


def remove_reference_call(company_id: str, item_id: str) -> bool:
    with _LOCK:
        data = _read(company_id, "reference_calls.json", {})
        items = list(data.get("items") or [])
        kept = [item for item in items if item.get("id") != item_id]
        if len(kept) == len(items):
            return False
        _write(company_id, "reference_calls.json", {"items": kept})
    return True


# ---- IC meetings & votes -----------------------------------------------------------------


def _tally(meeting: dict) -> dict:
    votes = meeting.get("votes") or {}
    counts = Counter(v.get("vote") for v in votes.values())
    convictions = [v.get("conviction") for v in votes.values() if isinstance(v.get("conviction"), (int, float))]
    leading = None
    majority = None
    total = sum(counts.values())
    if counts:
        top = counts.most_common()
        if len(top) == 1 or top[0][1] > top[1][1]:
            leading = top[0][0]
        if top[0][1] * 2 > total:
            majority = top[0][0]
    return {
        "invest": counts.get("invest", 0),
        "pass": counts.get("pass", 0),
        "more_work": counts.get("more_work", 0),
        "total": total,
        "leading": leading,
        "majority": majority,
        "tied": bool(counts) and leading is None,
        "average_conviction": round(sum(convictions) / len(convictions), 2) if convictions else None,
    }


def _with_tally(meeting: dict) -> dict:
    out = dict(meeting)
    out["tally"] = _tally(meeting)
    out["votes"] = [
        dict(v, member=member, member_name=v.get("member_name") or member, recorded_by=v.get("recorded_by") or member)
        for member, v in (meeting.get("votes") or {}).items()
    ]
    out["votes"].sort(key=lambda v: v.get("at") or "")
    return out


def list_meetings(company_id: str) -> dict:
    with _LOCK:
        items = _read(company_id, "ic_meetings.json", {}).get("items") or []
    items = sorted(items, key=lambda m: m.get("created_at") or "", reverse=True)
    return {"company_id": company_id, "items": [_with_tally(m) for m in items]}


def open_meeting(company_id: str, *, title: str = "", scheduled_at: str | None = None, report_id: str | None = None, created_by: str | None = None) -> dict:
    meeting = {
        "id": f"icm-{uuid.uuid4().hex[:10]}",
        "title": _clean(title, 200) or f"IC — {storage.get_company(company_id) and storage.get_company(company_id).get('name') or company_id}",
        "scheduled_at": _clean(scheduled_at, 40) or _now(),
        "report_id": _clean(report_id, 120) or None,
        "status": "open",
        "created_at": _now(),
        "created_by": created_by or "",
        "votes": {},
        "outcome": None,
        "decision_id": None,
    }
    with _LOCK:
        data = _read(company_id, "ic_meetings.json", {})
        items = list(data.get("items") or [])
        for other in items:
            if other.get("status") == "open":
                raise ValueError("A meeting is already open for this company — close it first")
        items.append(meeting)
        _write(company_id, "ic_meetings.json", {"items": items})
    return _with_tally(meeting)


def cast_vote(
    company_id: str,
    meeting_id: str,
    *,
    member: str,
    vote: str,
    conviction: Any = None,
    note: str = "",
    member_name: str | None = None,
    recorded_by: str | None = None,
) -> dict:
    member = _clean(member, 120)
    member_name = _clean(member_name or "", 120) or None
    recorded_by = _clean(recorded_by or "", 200) or None
    if not member:
        raise ValueError("member is required")
    vote = _clean(vote, 20).lower()
    if vote not in VOTES:
        raise ValueError(f"vote must be one of {', '.join(VOTES)}")
    conviction = _score_1_to_5(conviction, "conviction")
    with _LOCK:
        data = _read(company_id, "ic_meetings.json", {})
        items = list(data.get("items") or [])
        meeting = next((m for m in items if m.get("id") == meeting_id), None)
        if meeting is None:
            raise LookupError("Meeting not found")
        if meeting.get("status") != "open":
            raise ValueError("Meeting is closed")
        votes = meeting.setdefault("votes", {})
        if member_name:
            for key in [k for k in votes if k.lower() == member_name.lower() and k != member]:
                votes.pop(key)
        votes[member] = {
            "vote": vote,
            "conviction": conviction,
            "note": _clean(note, 1000),
            "at": _now(),
            "member_name": member_name or member,
            "recorded_by": recorded_by or member,
        }
        _write(company_id, "ic_meetings.json", {"items": items})
    return _with_tally(meeting)


def close_meeting(company_id: str, meeting_id: str, *, record_decision: bool = False, explanation: str = "", closed_by: str | None = None) -> dict:
    with _LOCK:
        data = _read(company_id, "ic_meetings.json", {})
        items = list(data.get("items") or [])
        meeting = next((m for m in items if m.get("id") == meeting_id), None)
        if meeting is None:
            raise LookupError("Meeting not found")
        if meeting.get("status") != "open":
            raise ValueError("Meeting is already closed")
        tally = _tally(meeting)
        meeting["status"] = "closed"
        meeting["closed_at"] = _now()
        meeting["closed_by"] = closed_by or ""
        meeting["outcome"] = {"leading": tally["leading"], "majority": tally["majority"], "tied": tally["tied"], "tally": tally}
        if record_decision:
            if tally["tied"]:
                raise ValueError("Votes are tied — break the tie first")
            if not tally["majority"]:
                raise ValueError(
                    f"No majority — {tally.get(tally['leading'] or '', 0)} of {tally['total']} voted {tally['leading'] or 'nothing'}; "
                    "record a decision manually or re-vote"
                )
            verdict = VOTE_TO_VERDICT[tally["majority"]]
            summary = _clean(explanation, 1800) or (
                f"IC vote: {tally['invest']} invest / {tally['pass']} pass / {tally['more_work']} more work"
                + (f" · avg conviction {tally['average_conviction']}" if tally["average_conviction"] else "")
            )
            decision = decisions_store.add_decision(
                company_id,
                verdict=verdict,
                explanation=summary,
                report_id=meeting.get("report_id"),
                created_by=closed_by or "",
            )
            meeting["decision_id"] = decision.get("id") if isinstance(decision, dict) else None
        _write(company_id, "ic_meetings.json", {"items": items})
    return _with_tally(meeting)


# ---- Comparable past decisions -----------------------------------------------------------


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _sector_of(company: dict) -> str:
    for key in ("sector", "industry", "category"):
        value = thesis_store._localized(company.get(key)).strip().lower()
        if value:
            return value
    return ""


def comparable_decisions(company_id: str, *, limit: int = 6) -> dict:
    target = storage.get_company(company_id)
    if target is None:
        return {"company_id": company_id, "items": [], "basis": "Company not found"}
    target_text = thesis_store._company_text(target)
    target_tokens = _tokens(target_text)
    target_sector = _sector_of(target)
    target_stage = thesis_store._stage_of(target, target_text)

    scored: list[dict] = []
    for other in storage.list_companies():
        oid = other.get("id")
        if not oid or oid == company_id:
            continue
        try:
            decisions = decisions_store.list_decisions(oid).get("items") or []
        except ValueError:
            continue
        if not decisions:
            continue
        other_text = thesis_store._company_text(other)
        score = 0
        why: list[str] = []
        other_sector = _sector_of(other)
        if target_sector and other_sector and (target_sector == other_sector or target_sector in other_sector or other_sector in target_sector):
            score += 40
            why.append(f"Same sector ({other_sector})")
        other_stage = thesis_store._stage_of(other, other_text)
        if target_stage and other_stage == target_stage:
            score += 20
            why.append(f"Same stage ({other_stage})")
        overlap = target_tokens & _tokens(other_text)
        if overlap:
            share = len(overlap) / max(1, min(len(target_tokens), 25))
            pts = int(min(40, round(share * 40)))
            if pts:
                score += pts
                why.append("Shared terms: " + ", ".join(sorted(overlap)[:6]))
        if score < 20:
            continue
        latest = decisions[0]
        retro = (latest.get("retrospectives") or [])
        latest_retro = retro[-1] if retro else None
        scored.append({
            "company_id": oid,
            "company_name": other.get("name") or oid,
            "score": min(100, score),
            "why": why,
            "decision": {
                "id": latest.get("id"),
                "verdict": latest.get("verdict"),
                "decided_at": latest.get("decided_at"),
                "explanation": latest.get("explanation"),
            },
            "retrospective": {"verdict": latest_retro.get("verdict"), "note": latest_retro.get("note")} if isinstance(latest_retro, dict) else None,
            "decision_count": len(decisions),
        })
    scored.sort(key=lambda item: (-item["score"], item["company_name"]))
    return {
        "company_id": company_id,
        "items": scored[:limit],
        "basis": "Sector match 40 · stage match 20 · shared description terms up to 40. Only companies with a recorded decision appear.",
    }
