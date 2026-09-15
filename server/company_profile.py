"""Unified company object: the public and private sides of one company in a single record.

Public: ticker quote (when a ticker exists). Private: position, latest KPI, latest mark.
Plus thesis fit, pipeline stage, latest decision, IC state and counts of everything on file.
Every field is either on record or absent — nothing is filled in.
"""
from __future__ import annotations

from typing import Any

from . import deal_pipeline, decisions_store, files_store, firm, ic_room, live_quotes, portfolio, storage, thesis_store, transcripts


def _quote(ticker: str | None) -> dict | None:
    if not ticker:
        return None
    try:
        quotes = (live_quotes.fetch_quotes([ticker]) or {}).get("quotes") or {}
    except Exception:  # noqa: BLE001
        return None
    raw = quotes.get(ticker.upper()) or quotes.get(ticker)
    if not isinstance(raw, dict):
        return None
    return {
        "ticker": ticker.upper(),
        "last_price": live_quotes._as_float(raw.get("last_price")),
        "change_pct_1d": live_quotes._as_float(raw.get("change_pct_1d")),
        "market_cap": live_quotes._as_float(raw.get("market_cap")),
        "name": raw.get("name"),
        "as_of": raw.get("as_of"),
    }


def build_profile(company_id: str, *, include_quote: bool = True) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        return {"company_id": company_id, "found": False}
    ticker = (company.get("ticker") or "").strip() or None
    is_public = bool(ticker) or str(company.get("status") or "").lower() == "public"
    record = portfolio.get_portfolio(company_id) if portfolio.has_record(company_id) else None
    decisions = decisions_store.list_decisions(company_id).get("items") or []
    meetings = ic_room.list_meetings(company_id).get("items") or []
    refs = ic_room.list_reference_calls(company_id)
    comments = firm.list_comments(company_id)
    fit = thesis_store.score_company(company)
    try:
        pipeline = deal_pipeline.get_deal_pipeline(company_id)
    except Exception:  # noqa: BLE001
        pipeline = {}
    description = company.get("description")
    if isinstance(description, dict):
        description = description.get("en") or next(iter(description.values()), "")
    profile: dict[str, Any] = {
        "company_id": company_id,
        "found": True,
        "name": company.get("name") or company_id,
        "description": description or "",
        "sector": thesis_store._localized(company.get("sector") or company.get("industry") or company.get("category")),
        "hq": thesis_store._localized(company.get("hq") or company.get("location")),
        "is_public": is_public,
        "ticker": ticker,
        "public": _quote(ticker) if include_quote else None,
        "private": {
            "position": (record or {}).get("position") or {},
            "latest_kpi": (record or {}).get("latest_kpi"),
            "latest_mark": (record or {}).get("latest_mark"),
            "moic": (record or {}).get("moic"),
            "alerts": (record or {}).get("alerts") or [],
        } if record else None,
        "thesis_fit": {"score": fit.get("score"), "fit": fit.get("fit"), "reasons": fit.get("reasons") or []},
        "pipeline": {"stage": pipeline.get("stage"), "owner": pipeline.get("owner"), "next_step": pipeline.get("next_step")} if pipeline else None,
        "latest_decision": {"verdict": decisions[0].get("verdict"), "decided_at": decisions[0].get("decided_at"), "explanation": decisions[0].get("explanation")} if decisions else None,
        "ic": {
            "open_meeting": next((m.get("id") for m in meetings if m.get("status") == "open"), None),
            "meeting_count": len(meetings),
            "reference_calls": refs.get("count", 0),
            "reference_rating": refs.get("average_rating"),
        },
        "counts": {
            "files": len(files_store.list_files(company_id)),
            "transcripts": transcripts.list_transcripts(company_id=company_id, limit=1000).get("count", 0),
            "open_comments": comments.get("open_count", 0),
            "decisions": len(decisions),
            "kpi_rows": (record or {}).get("kpi_count", 0),
        },
    }
    return profile
