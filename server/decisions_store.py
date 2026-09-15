"""Per-company Decision Record store.

Human investment decisions — invest / pass / watch — recorded AFTER the
humans decide, each with a required explanation. The memo pipeline treats
these as factual history ("BSH made the decision to … on … because …")
while its own analysis stays in recommendation voice; the tracked-news
sync appends `retrospectives` to each decision assessing whether it still
looks right as new information lands.

Storage: ``data/companies/<company_id>/decisions.json`` — beside the
tracking store's ``tracking_updates.json``. Writes are atomic
(tmp + replace); all mutation happens under a module lock.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server import company_paths

VERDICTS = ("invest", "pass", "watch")
RETRO_VERDICTS = ("still_right", "questionable", "looks_wrong")
MAX_RETROSPECTIVES_PER_DECISION = 10

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_dir(company_id: str) -> Path:
    return company_paths.company_dir(company_id)


def _decisions_path(company_id: str) -> Path:
    return _company_dir(company_id) / "decisions.json"


def _clean_text(value: Any, *, limit: int = 1000) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def _stable_id(prefix: str, text: Any) -> str:
    stamp = _now()
    digest = hashlib.sha1(f"{prefix}:{stamp}:{text}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _load(company_id: str) -> dict:
    path = _decisions_path(company_id)
    if not path.exists():
        return {"company_id": company_id, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"company_id": company_id, "items": []}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return {"company_id": company_id, "items": []}
    return data


def _save(company_id: str, payload: dict) -> None:
    path = _decisions_path(company_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _parse_decided_at(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return _now()
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("decided_at must be an ISO date or datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _sorted_items(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda row: str(row.get("decided_at") or row.get("created_at") or ""),
        reverse=True,
    )


def list_decisions(company_id: str) -> dict:
    with _LOCK:
        payload = _load(company_id)
    return {
        "company_id": company_id,
        "items": _sorted_items(list(payload.get("items") or [])),
    }


def add_decision(
    company_id: str,
    *,
    verdict: str,
    explanation: str,
    decided_at: str | None = None,
    report_id: str | None = None,
    created_by: str = "",
) -> dict:
    verdict = _clean_text(verdict, limit=20).lower()
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    explanation = _clean_text(explanation, limit=2000)
    if not explanation:
        raise ValueError("explanation is required")
    row = {
        "id": _stable_id("decision", f"{company_id}:{verdict}:{explanation}"),
        "verdict": verdict,
        "explanation": explanation,
        "decided_at": _parse_decided_at(decided_at),
        "created_at": _now(),
        "created_by": _clean_text(created_by, limit=120) or "shared",
        "report_id": _clean_text(report_id, limit=64) or None,
        "retrospectives": [],
    }
    with _LOCK:
        payload = _load(company_id)
        items = list(payload.get("items") or [])
        items.append(row)
        payload["company_id"] = company_id
        payload["items"] = _sorted_items(items)
        _save(company_id, payload)
    return row


def remove_decision(company_id: str, decision_id: str) -> bool:
    with _LOCK:
        payload = _load(company_id)
        items = list(payload.get("items") or [])
        kept = [row for row in items if row.get("id") != decision_id]
        if len(kept) == len(items):
            return False
        payload["items"] = kept
        _save(company_id, payload)
    return True


def append_retrospectives(
    company_id: str, assessments: list[dict], *, source: str
) -> int:
    """Attach retrospective verdicts to their decisions.

    Each assessment: ``{decision_id, verdict, rationale_en, rationale_zh,
    news_ids?, news_titles?}``. Unknown decision ids and invalid verdicts
    are dropped, never raised — the tracking sync must not fail on model
    output. Returns the number of retrospectives actually appended.
    """
    appended = 0
    with _LOCK:
        payload = _load(company_id)
        items = list(payload.get("items") or [])
        by_id = {str(row.get("id")): row for row in items}
        for assessment in assessments or []:
            if not isinstance(assessment, dict):
                continue
            decision = by_id.get(str(assessment.get("decision_id") or ""))
            if decision is None:
                continue
            verdict = _clean_text(assessment.get("verdict"), limit=20).lower()
            if verdict not in RETRO_VERDICTS:
                continue
            retro = {
                "id": _stable_id("retro", f"{decision.get('id')}:{verdict}"),
                "assessed_at": _now(),
                "verdict": verdict,
                "rationale_en": _clean_text(
                    assessment.get("rationale_en"), limit=600
                ),
                "rationale_zh": _clean_text(
                    assessment.get("rationale_zh"), limit=600
                ),
                "news_ids": [
                    str(item)
                    for item in (assessment.get("news_ids") or [])
                    if str(item).strip()
                ][:10],
                "news_titles": [
                    _clean_text(item, limit=200)
                    for item in (assessment.get("news_titles") or [])
                    if _clean_text(item, limit=200)
                ][:10],
                "source": _clean_text(source, limit=40) or "tracking_sync",
            }
            existing = list(decision.get("retrospectives") or [])
            decision["retrospectives"] = ([retro] + existing)[
                :MAX_RETROSPECTIVES_PER_DECISION
            ]
            appended += 1
        if appended:
            payload["items"] = items
            _save(company_id, payload)
    return appended


def _age_bucket(decided_at: str, now: datetime) -> str:
    try:
        decided = datetime.fromisoformat(str(decided_at).replace("Z", "+00:00"))
    except ValueError:
        return "undated"
    if decided.tzinfo is None:
        decided = decided.replace(tzinfo=timezone.utc)
    days = max(0, (now - decided).days)
    if days < 90:
        return "recent (under 3 months old)"
    if days < 365:
        return "3-12 months old"
    return "over 12 months old"


def render_decision_record_md(company_id: str, *, max_chars: int = 4000) -> str | None:
    """English markdown digest of the decision record for the memo pipeline.

    ``None`` when the company has no decisions, so the caller can skip the
    file entirely and keep prompts byte-identical. Truncation happens on
    decision boundaries, never mid-entry.
    """
    items = list_decisions(company_id).get("items") or []
    if not items:
        return None
    now = datetime.now(timezone.utc)
    lines = ["# BSH decision record", ""]
    for row in items:
        decided_at = str(row.get("decided_at") or "")[:10]
        entry = [
            f"- Decision: {row.get('verdict')} — decided {decided_at} "
            f"({_age_bucket(row.get('decided_at'), now)})",
            f"  Reason: {row.get('explanation')}",
        ]
        retros = row.get("retrospectives") or []
        if retros:
            latest = retros[0]
            rationale = latest.get("rationale_en") or ""
            entry.append(
                f"  Latest retrospective ({str(latest.get('assessed_at') or '')[:10]}): "
                f"{latest.get('verdict')}"
                + (f" — {rationale}" if rationale else "")
            )
        candidate = "\n".join(lines + entry + [""])
        if len(candidate) > max_chars:
            lines.append("(older decisions truncated)")
            break
        lines.extend(entry)
        lines.append("")
    lines.append(
        "Weight these as decision history, not analysis: recent decisions "
        "(under ~12 months) should inform the current view; older ones are "
        "historical context only. The memo's own conclusion must still be "
        "an independent recommendation."
    )
    return "\n".join(lines).rstrip() + "\n"
