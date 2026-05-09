"""HTTP API for the research center."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import companies_ai, companies_autocomplete, files_store, generator, storage

router = APIRouter(prefix="/api")

REPORT_TYPES = ("Investment Report", "Background", "Financial Analysis", "Market Analysis")
AUDIENCES = ("LP", "Assistant", "Partner", "Internal")
LANGUAGES = ("en", "zh")


class CompanyOut(BaseModel):
    id: str
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    status: str | None = None
    hq: str | None = None
    founded_year: int | None = None
    website: str | None = None
    logo_domain: str | None = None
    employee_band: str | None = None
    parent_company: str | None = None
    key_people: list[dict] = Field(default_factory=list)
    highlight_2026: dict | None = None
    latest_funding: dict | None = None
    latest_earnings: dict | None = None
    total_funding_usd: str | None = None
    products: list[dict] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    recent_news: list[dict] = Field(default_factory=list)
    notable_contracts: list[dict] = Field(default_factory=list)
    notable_acquisitions: list[dict] = Field(default_factory=list)


class ReportSummary(BaseModel):
    id: str
    company_id: str
    company_name: str | None = None
    report_type: str
    audience: str
    language: str = "en"
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
    language: str = "en"


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
    return {
        "report_types": list(REPORT_TYPES),
        "audiences": list(AUDIENCES),
        "languages": [{"code": "en", "label": "English"}, {"code": "zh", "label": "中文"}],
    }


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


@router.post("/companies/{company_id}/refresh")
def refresh_company(company_id: str) -> CompanyOut:
    """Re-run the AI deep search for this company by name and merge the new
    enrichment back into the local record. Also patch any other cached search
    results that contain this company so they show the fresh data on next view.
    """
    from . import cache

    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    name = company.get("name") or ""
    if not name:
        raise HTTPException(status_code=400, detail="Company has no name to query")
    result = companies_ai.deep_search(name, force_refresh=True)
    matches = result.get("matches") or []
    chosen: dict | None = next(
        (m for m in matches if m.get("id") == company_id), None
    )
    if chosen is None and matches:
        chosen = matches[0]
    refreshed = storage.get_company(company_id) or chosen or company
    view = _company_view(refreshed)
    # Patch any cached deep-search result that referenced this company so future
    # cache hits don't show stale data.
    cache.update_in_namespace(
        "companies_ai",
        predicate=lambda item: item.get("id") == company_id,
        transform=lambda _item: dict(view),
    )
    return CompanyOut(**view)


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
    if payload.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Invalid language")
    try:
        report = storage.create_report(
            company_id=payload.company_id,
            report_type=payload.report_type,
            audience=payload.audience,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    generator.start_generation(report["id"])
    return ReportDetail(**_report_detail(report))


@router.get("/companies/{company_id}/reports")
def get_company_reports(company_id: str) -> list[ReportSummary]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return [
        ReportSummary(**_report_summary(r))
        for r in storage.list_reports()
        if r.get("company_id") == company_id
    ]


@router.get("/companies/{company_id}/files")
def get_files(company_id: str) -> list[dict]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return files_store.list_files(company_id)


@router.post("/companies/{company_id}/files", status_code=201)
async def post_file(
    company_id: str,
    file: UploadFile = File(...),
    label: str | None = Form(None),
    language: str = Form("en"),
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    data = await file.read()
    try:
        return files_store.upload_file(
            company_id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
            label=label,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/files/{file_id}/preview")
def get_file_preview(company_id: str, file_id: str) -> FileResponse:
    """Return a PDF preview suitable for an <iframe>.

    PDFs are streamed inline as-is. PPT/PPTX files are converted via Microsoft
    PowerPoint (cached on disk after the first run); the conversion runs
    synchronously here for files that weren't converted on upload yet.
    """
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = files_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    record, _ = found
    pdf_path = files_store.get_or_create_preview(company_id, file_id)
    if pdf_path is None:
        raise HTTPException(
            status_code=415,
            detail=(
                "Preview not available — PowerPoint conversion failed or this "
                "file type isn't supported. The file is still downloadable."
            ),
        )
    base = (record.get("filename") or "preview").rsplit(".", 1)[0]
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{base}.pdf"'},
    )


@router.get("/companies/{company_id}/files/{file_id}")
def get_file(
    company_id: str, file_id: str, inline: bool = False
) -> FileResponse:
    """Stream an uploaded file.

    Default disposition is `attachment` (browser downloads). Pass `inline=1`
    to get `inline` so PDFs render in an <iframe> previewer.
    """
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = files_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    record, path = found
    filename = record.get("filename") or "file"
    media_type = record.get("content_type") or "application/octet-stream"
    if inline:
        # FileResponse's `filename` arg always sets attachment; build the
        # header by hand to keep `inline` disposition.
        return FileResponse(
            path=str(path),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type=media_type,
    )


@router.delete("/companies/{company_id}/files/{file_id}", status_code=204)
def delete_file(company_id: str, file_id: str) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not files_store.delete_file(company_id, file_id):
        raise HTTPException(status_code=404, detail="File not found")


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
        "industry": c.get("industry"),
        "exchange": c.get("exchange"),
        "status": c.get("status"),
        "hq": c.get("hq"),
        "founded_year": c.get("founded_year"),
        "website": c.get("website"),
        "logo_domain": c.get("logo_domain"),
        "employee_band": c.get("employee_band"),
        "parent_company": c.get("parent_company"),
        "key_people": list(c.get("key_people") or []),
        "highlight_2026": c.get("highlight_2026"),
        "latest_funding": c.get("latest_funding"),
        "latest_earnings": c.get("latest_earnings"),
        "total_funding_usd": c.get("total_funding_usd"),
        "products": list(c.get("products") or []),
        "competitors": list(c.get("competitors") or []),
        "recent_news": list(c.get("recent_news") or []),
        "notable_contracts": list(c.get("notable_contracts") or []),
        "notable_acquisitions": list(c.get("notable_acquisitions") or []),
    }


def _report_summary(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "company_id": r.get("company_id"),
        "company_name": r.get("company_name"),
        "report_type": r.get("report_type"),
        "audience": r.get("audience"),
        "language": r.get("language") or "en",
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
