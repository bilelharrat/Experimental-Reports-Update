"""HTTP API for the research center."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import companies_ai, companies_autocomplete, generator, storage

router = APIRouter(prefix="/api")

REPORT_TYPES = ("Investment Report", "Background", "Financial Analysis", "Market Analysis")
AUDIENCES = ("LP", "Assistant", "Partner", "Internal")


class CompanyOut(BaseModel):
    id: str
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None


class ReportSummary(BaseModel):
    id: str
    company_id: str
    company_name: str | None = None
    report_type: str
    audience: str
    status: str
    progress: int = 0
    stage: str | None = None
    created_at: str
    updated_at: str


class ReportDetail(ReportSummary):
    content: str = ""
    stages: list[dict] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    company_id: str
    report_type: str
    audience: str


class ThreadIn(BaseModel):
    question: str
    answer: str = ""


class SelectMatch(BaseModel):
    """Payload for promoting an autocomplete or search hit to a local company."""
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None


@router.get("/options")
def get_options() -> dict:
    return {"report_types": list(REPORT_TYPES), "audiences": list(AUDIENCES)}


@router.get("/companies")
def get_companies() -> list[CompanyOut]:
    return [CompanyOut(**_company_view(c)) for c in storage.list_companies()]


@router.get("/companies/autocomplete")
def companies_autocomplete_endpoint(q: str = "", limit: int = 8) -> list[dict]:
    """Fast typeahead — local YAML hits + Yahoo Finance equity suggestions."""
    return companies_autocomplete.autocomplete(q, limit=limit)


@router.get("/companies/search")
def companies_search(q: str = "", refresh: bool = False) -> dict:
    """Deep search — OpenAI Responses + web_search.

    Results are cached indefinitely with a `cached_at` timestamp so the UI
    can show staleness; pass `refresh=true` to re-query and overwrite. Each
    match carries a local `id` so the frontend can route straight to
    /research/<id>.
    """
    return companies_ai.deep_search(q, force_refresh=refresh)


@router.post("/companies/select", status_code=201)
def companies_select(payload: SelectMatch) -> dict:
    """Promote an autocomplete suggestion to a tracked company.

    Used when the user clicks a Yahoo-only typeahead hit and we need a stable
    local id before navigating to the research page.
    """
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    return storage.upsert_company_from_match(payload.model_dump())


@router.get("/companies/{company_id}")
def get_company(company_id: str) -> CompanyOut:
    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyOut(**_company_view(company))


@router.get("/reports")
def get_reports() -> list[ReportSummary]:
    return [ReportSummary(**_report_summary(r)) for r in storage.list_reports()]


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> ReportDetail:
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportDetail(**_report_detail(report))


@router.post("/reports", status_code=201)
def post_report(payload: GenerateRequest) -> ReportDetail:
    if payload.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid report_type")
    if payload.audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="Invalid audience")
    try:
        report = storage.create_report(
            company_id=payload.company_id,
            report_type=payload.report_type,
            audience=payload.audience,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    generator.start_generation(report["id"])
    return ReportDetail(**_report_detail(report))


@router.get("/companies/{company_id}/threads")
def get_threads(company_id: str) -> list[dict]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return storage.list_threads(company_id)


@router.post("/companies/{company_id}/threads", status_code=201)
def post_thread(company_id: str, payload: ThreadIn) -> dict:
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    try:
        return storage.add_thread(company_id, payload.question.strip(), payload.answer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---- view shaping ----

def _company_view(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "ticker": c.get("ticker"),
        "description": c.get("description"),
        "sector": c.get("sector"),
    }


def _report_summary(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "company_id": r.get("company_id"),
        "company_name": r.get("company_name"),
        "report_type": r.get("report_type"),
        "audience": r.get("audience"),
        "status": r.get("status", "queued"),
        "progress": int(r.get("progress") or 0),
        "stage": r.get("stage"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


def _report_detail(r: dict) -> dict:
    return {
        **_report_summary(r),
        "content": r.get("content") or "",
        "stages": list(r.get("stages") or []),
    }
