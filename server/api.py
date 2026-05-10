"""HTTP API for the research center."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

import threading
from datetime import datetime, timezone

from . import (
    cache,
    claude_runner,
    companies_ai,
    companies_autocomplete,
    company_translate,
    deck_summary,
    external_store,
    external_translate,
    files_store,
    generator,
    job_progress,
    link_preview as link_preview_mod,
    storage,
    text_analysis,
)

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
    language: str | None = None
    translation: dict | None = None


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


@router.get("/diagnostics/claude")
def diagnose_claude() -> dict:
    """Health-check the local Claude Code CLI.

    Spawns a one-shot prompt and reports back path, version, model,
    response, latency, and cost. Used to verify Claude is installed and
    authenticated before kicking off real summary jobs.
    """
    return claude_runner.health_check()


@router.get("/companies")
def get_companies() -> list[CompanyOut]:
    return [CompanyOut(**_company_view(c)) for c in storage.list_companies()]


@router.get("/companies/autocomplete")
def companies_autocomplete_endpoint(q: str = "", limit: int = 8) -> list[dict]:
    """Fast typeahead — local YAML hits + Yahoo Finance equity suggestions."""
    return companies_autocomplete.autocomplete(q, limit=limit)


@router.get("/companies/search")
def companies_search(q: str = "", refresh: bool = False) -> dict:
    """Deep search — Claude Code (primary) or OpenAI (fallback).

    Synchronous. Cached results return instantly. Pass `refresh=true` to
    re-query and overwrite. For a live progress feed during the
    underlying LLM call, use POST /companies/search/start instead.
    """
    return companies_ai.deep_search(q, force_refresh=refresh)


# ---- Search-job streaming (for live progress UI) ----


def _search_job_id(query: str) -> str:
    """Stable per-query job id — same query → same job id, so concurrent
    searches for the same string share one progress stream."""
    import hashlib

    return hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:16]


def _search_progress_path(job_id: str):
    from pathlib import Path

    base: Path = files_store.UPLOADS_ROOT / "_search"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{job_id}__search.progress.jsonl"


def _run_search_job(job_id: str, query: str, refresh: bool) -> None:
    """Background worker for a deep-search job. Streams progress events
    into the JSONL file and emits a terminal `done` event with the matches
    payload (or `error` on failure)."""
    progress = job_progress.ProgressLog(_search_progress_path(job_id))
    progress.emit("stage", stage="starting", message="Starting search", query=query)
    try:
        result = companies_ai.deep_search(
            query, force_refresh=refresh, progress=progress
        )
        progress.emit(
            "done",
            source=result.get("source"),
            matches=result.get("matches") or [],
            cached_at=result.get("cached_at"),
            reason=result.get("reason"),
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Search crashed: {type(exc).__name__}: {exc}"
        )


@router.post("/companies/search/start")
def post_companies_search_start(q: str = "", refresh: bool = False) -> dict:
    """Kick off a deep search in the background and return a job id + the
    SSE stream URL for live progress.

    If a fresh cache hit exists and refresh isn't set, the matches come
    back inline (no job, no stream needed).
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    if not refresh:
        cached = cache.get("companies_ai", query.lower())
        if cached is not None:
            return {
                "cached": True,
                "source": "cache",
                "matches": cached["value"] or [],
                "cached_at": cached["stored_at_iso"],
            }

    job_id = _search_job_id(query)
    path = _search_progress_path(job_id)

    # Idempotency: attach to an in-flight job for the same query.
    state = _scan_progress_state(path)
    if state.get("exists") and not state.get("terminated"):
        return {
            "cached": False,
            "job_id": job_id,
            "stream_url": f"/api/companies/search/stream/{job_id}",
            "status": "already_running",
        }

    threading.Thread(
        target=_run_search_job,
        args=(job_id, query, refresh),
        name=f"search:{job_id}",
        daemon=True,
    ).start()
    return {
        "cached": False,
        "job_id": job_id,
        "stream_url": f"/api/companies/search/stream/{job_id}",
        "status": "queued",
    }


@router.get("/companies/search/stream/{job_id}")
async def stream_search_progress(job_id: str):
    """SSE stream of progress events for a search job. Same tail/replay
    semantics as the deck-summary stream endpoint."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    progress_path = _search_progress_path(job_id)

    async def event_stream():
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this job\"}\n\n"
            return

        pos = 0
        idle_deadline = time.monotonic() + 600.0
        terminated = False
        while time.monotonic() < idle_deadline and not terminated:
            try:
                with progress_path.open("r", encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
            except Exception:
                await asyncio.sleep(0.2)
                continue
            if chunk:
                idle_deadline = time.monotonic() + 600.0
                for line in chunk.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    yield f"data: {line}\n\n"
                    try:
                        entry = _json.loads(line)
                        if entry.get("type") in ("done", "error"):
                            terminated = True
                            break
                    except Exception:
                        pass
            else:
                await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/companies/select", status_code=201)
def companies_select(payload: SelectMatch) -> dict:
    """Promote an autocomplete suggestion to a tracked company.

    Used when the user clicks a Yahoo-only typeahead hit and we need a stable
    local id before navigating to the research page.
    """
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    company = storage.upsert_company_from_match(payload.model_dump())
    _ensure_company_translation(company.get("id"))
    return storage.get_company(company.get("id")) or company


def _ensure_company_translation(company_id: str | None, *, force: bool = False) -> None:
    """Translate a company synchronously and persist the result.

    No-op if a translation already exists (unless `force=True`) or the
    OPENAI_API_KEY isn't configured.
    """
    if not company_id:
        return
    company = storage.get_company(company_id)
    if company is None:
        return
    if not force and company.get("translation"):
        return
    result = company_translate.translate_company(company)
    storage.update_company(
        company_id,
        language=result.get("language"),
        translation=result.get("translation"),
    )


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
    _ensure_company_translation(company_id, force=True)
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


@router.post("/companies/{company_id}/translate")
def translate_company_endpoint(company_id: str) -> CompanyOut:
    """Force a re-translation of this company (e.g. after editing fields)."""
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _ensure_company_translation(company_id, force=True)
    refreshed = storage.get_company(company_id) or {}
    return CompanyOut(**_company_view(refreshed))


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
    pdf_path, err = files_store.get_or_create_preview(company_id, file_id)
    if pdf_path is None:
        raise HTTPException(
            status_code=415,
            detail=err or "Preview not available.",
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


@router.get("/companies/{company_id}/files/{file_id}/summary")
def get_file_summary(company_id: str, file_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = files_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    record, _ = found
    summary = record.get("summary")
    if not summary:
        raise HTTPException(status_code=404, detail="No summary cached")
    return summary


def _summary_progress_path(company_id: str, file_id: str) -> "Path":
    from pathlib import Path

    return (
        files_store._company_dir(company_id)
        / f"{file_id}__summary.progress.jsonl"
    )


def _scan_progress_state(path: "Path") -> dict:
    """Scan a progress JSONL and summarize where the job stands.

    Used by both the active-jobs listing and the idempotent POST handler so
    we can decide whether to start a new run or attach to one in flight.
    """
    import json as _json

    state: dict = {
        "exists": path.exists(),
        "terminated": False,
        "terminal_type": None,
        "started_at": None,
        "last_event_at": None,
        "latest_stage": None,
        "latest_stage_key": None,
        "slide_no": None,
        "slide_count": None,
        "speed": None,
        "claude_cost_usd": None,
        "error": None,
    }
    if not path.exists():
        return state
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if state["started_at"] is None:
                    state["started_at"] = entry.get("ts")
                state["last_event_at"] = entry.get("ts")
                etype = entry.get("type")
                if etype in ("done", "error"):
                    state["terminated"] = True
                    state["terminal_type"] = etype
                    if etype == "error":
                        state["error"] = entry.get("error")
                elif etype == "stage":
                    state["latest_stage_key"] = entry.get("stage")
                    state["latest_stage"] = (
                        entry.get("message") or entry.get("stage")
                    )
                    if "slide_no" in entry:
                        state["slide_no"] = entry["slide_no"]
                    if "slide_count" in entry:
                        state["slide_count"] = entry["slide_count"]
                    if "speed" in entry:
                        state["speed"] = entry["speed"]
                elif etype == "claude_action" and entry.get("action") == "result":
                    if entry.get("cost_usd") is not None:
                        state["claude_cost_usd"] = entry["cost_usd"]
    except Exception:
        pass
    return state


def _run_summary_job(company_id: str, file_id: str, speed: str = "auto") -> None:
    """Background entry point for a summary generation job. Writes progress
    events to a JSONL file and persists the final summary onto the file
    record.
    """
    progress = job_progress.ProgressLog(
        _summary_progress_path(company_id, file_id)
    )
    try:
        progress.emit("stage", stage="starting", message="Starting summary job")
        found = files_store.get_file(company_id, file_id)
        if found is None:
            progress.emit("error", error="File not found")
            return
        record, src_path = found
        kind = record.get("kind") or ""

        ppt_preview = None
        if kind == "ppt":
            ppt_preview = files_store._preview_path_for(company_id, record)
            if not ppt_preview.exists():
                ppt_preview = None

        # Best-effort slide extraction for metadata + UI hints. The actual
        # reading still happens inside Claude Code.
        slides = deck_summary.extract_slides(
            src_path, kind, ppt_preview=ppt_preview, progress=progress
        )

        # Choose what to hand Claude. Claude reads the original file directly
        # (PDF / PPTX). For .ppt (binary) we use the PowerPoint-converted PDF
        # if available.
        claude_source: "Path | None"
        if kind in ("pdf", "pptx"):
            claude_source = src_path
        elif kind == "ppt":
            claude_source = ppt_preview
        else:
            claude_source = None
        claude_kind = (
            "pdf" if claude_source and claude_source.suffix.lower() == ".pdf"
            else "pptx" if claude_source and claude_source.suffix.lower() == ".pptx"
            else kind
        )

        if claude_source is None and not slides:
            progress.emit(
                "error",
                error=(
                    "Couldn't extract slide text. .ppt files need a PDF "
                    "preview first; .pptx and .pdf should work directly."
                ),
            )
            return

        # Per-job work dir lives under the upload folder so progress.md and
        # summary.json are inspectable on disk.
        work_dir = files_store._company_dir(company_id) / f"{file_id}__job"

        summary = deck_summary.summarize_slides(
            slides,
            hint_title=(record.get("label") or record.get("filename") or ""),
            file_path=claude_source,
            kind=claude_kind,
            progress=progress,
            work_dir=work_dir,
            speed=speed,
        )
        if "error" in summary:
            progress.emit("error", error=summary["error"])
            return

        summary["generated_at"] = datetime.now(timezone.utc).isoformat()
        files_store.update_record(company_id, file_id, summary=summary)
        progress.emit("done", summary=summary)
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Job crashed: {type(exc).__name__}: {exc}"
        )


@router.post("/companies/{company_id}/files/{file_id}/summary")
def post_file_summary(
    company_id: str, file_id: str, speed: str = "auto"
) -> dict:
    """Kick off bilingual deck summary generation in the background.

    `speed` is one of:
      - "auto"     — granular for ≤30 pages, fast otherwise (default)
      - "granular" — one Read per page (best per-slide visibility, slowest)
      - "fast"     — batched 20-page Reads (efficient on large decks)

    Returns immediately with a `job_id` (= file_id) and the path of the SSE
    stream. The frontend opens the SSE stream to consume granular progress
    events and pulls the cached summary once `done` arrives.
    """
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = files_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    if speed not in ("auto", "granular", "fast"):
        raise HTTPException(status_code=400, detail="Invalid speed")

    # Idempotency: if a job is already running for this file, return its
    # info instead of starting a second one. Caller's SSE replay will pick
    # up from the existing JSONL.
    progress_path = _summary_progress_path(company_id, file_id)
    state = _scan_progress_state(progress_path)
    if state.get("exists") and not state.get("terminated"):
        return {
            "job_id": file_id,
            "stream_url": (
                f"/api/companies/{company_id}/files/{file_id}/summary/stream"
            ),
            "speed": state.get("speed") or "unknown",
            "status": "already_running",
        }

    threading.Thread(
        target=_run_summary_job,
        args=(company_id, file_id, speed),
        name=f"summary:{file_id}",
        daemon=True,
    ).start()
    return {
        "job_id": file_id,
        "stream_url": (
            f"/api/companies/{company_id}/files/{file_id}/summary/stream"
        ),
        "speed": speed,
        "status": "queued",
    }


@router.get("/jobs/active")
def get_active_jobs() -> list[dict]:
    """All summary jobs currently in flight across every company.

    Powers the right-side ActiveJobsRail: walks the per-company upload
    directories looking for `<file_id>__summary.progress.jsonl` files, and
    returns those whose progress hasn't yet reached `done` or `error`.
    """
    from . import files_store as _fs

    out: list[dict] = []
    if not _fs.UPLOADS_ROOT.exists():
        return out
    for jsonl_path in _fs.UPLOADS_ROOT.glob("*/*__summary.progress.jsonl"):
        company_id = jsonl_path.parent.name
        name = jsonl_path.name
        suffix = "__summary.progress.jsonl"
        if not name.endswith(suffix):
            continue
        file_id = name[: -len(suffix)]
        state = _scan_progress_state(jsonl_path)
        if state.get("terminated"):
            continue
        found = _fs.get_file(company_id, file_id)
        if found is None:
            continue
        record, _ = found
        out.append(
            {
                "company_id": company_id,
                "file_id": file_id,
                "filename": record.get("filename"),
                "label": record.get("label"),
                "kind": record.get("kind"),
                "started_at": state.get("started_at"),
                "last_event_at": state.get("last_event_at"),
                "latest_stage": state.get("latest_stage"),
                "latest_stage_key": state.get("latest_stage_key"),
                "slide_no": state.get("slide_no"),
                "slide_count": state.get("slide_count"),
                "speed": state.get("speed"),
                "claude_cost_usd": state.get("claude_cost_usd"),
            }
        )
    out.sort(key=lambda j: j.get("started_at") or "", reverse=True)
    return out


@router.get("/companies/{company_id}/files/{file_id}/summary/stream")
async def stream_file_summary_progress(
    company_id: str, file_id: str
) -> "StreamingResponse":
    """SSE stream of progress events for a running (or recently finished)
    summary job. Replays everything in the JSONL file from the start and
    then tails new lines until a `done` or `error` event is seen.
    """
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if files_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")

    progress_path = _summary_progress_path(company_id, file_id)

    async def event_stream():
        # Wait briefly for the file to appear if the job was just kicked off.
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this job\"}\n\n"
            return

        pos = 0
        idle_deadline = time.monotonic() + 600.0  # 10 min ceiling
        terminated = False
        while time.monotonic() < idle_deadline and not terminated:
            try:
                with progress_path.open("r", encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
            except Exception:
                await asyncio.sleep(0.2)
                continue
            if chunk:
                idle_deadline = time.monotonic() + 600.0
                for line in chunk.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    yield f"data: {line}\n\n"
                    try:
                        entry = _json.loads(line)
                        if entry.get("type") in ("done", "error"):
                            terminated = True
                            break
                    except Exception:
                        pass
            else:
                await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/companies/{company_id}/files/{file_id}/summary", status_code=204
)
def delete_file_summary(company_id: str, file_id: str) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = files_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    files_store.update_record(company_id, file_id, summary=None)


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


# ---- External news / external research / Hormuz research ----


class LinkPreviewIn(BaseModel):
    url: str


class NewsCreateIn(BaseModel):
    url: str


@router.post("/external/link-preview")
def post_link_preview(payload: LinkPreviewIn) -> dict:
    """Fetch a URL and return its OpenGraph-style preview without saving.

    Used by the Submit-a-link tool to show the user what they're about to
    accept before kicking off the analysis pipeline.
    """
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    preview = link_preview_mod.fetch(url)
    if preview.error:
        raise HTTPException(status_code=400, detail=preview.error)
    out = preview.to_dict()
    # Hint how much article text we captured so the UI can show it.
    out["text_chars"] = len(preview.text or "")
    return out


def _run_news_analysis(item_id: str, url: str) -> None:
    """Background pipeline: fetch URL, archive HTML, run AI analysis."""
    try:
        external_store.update_item("news", item_id, status="fetching")
        preview = link_preview_mod.fetch(url)
        if preview.error:
            external_store.update_item(
                "news", item_id, status="failed", error=preview.error
            )
            return
        external_store.write_archive("news", item_id, preview.html)
        external_store.update_item(
            "news",
            item_id,
            status="analyzing",
            title=preview.title or url,
            description=preview.description,
            site_name=preview.site_name,
            image=preview.image,
            favicon=preview.favicon,
            domain=preview.domain,
            final_url=preview.final_url,
            archive_path=str(external_store.archive_path("news", item_id).name),
            raw_text_chars=len(preview.text or ""),
        )
        analysis = text_analysis.analyze(
            preview.text, hint_title=preview.title
        )
        if "error" in analysis:
            external_store.update_item(
                "news", item_id, status="ready", analysis_error=analysis["error"]
            )
            return
        external_store.update_item(
            "news",
            item_id,
            status="ready",
            summary=analysis.get("summary"),
            key_points=analysis.get("key_points") or [],
            language=analysis.get("language") or "other",
            translation=analysis.get("translation"),
            title=(analysis.get("title") or preview.title or url),
        )
    except Exception as exc:  # noqa: BLE001
        external_store.update_item(
            "news", item_id, status="failed", error=f"{type(exc).__name__}: {exc}"
        )


@router.post("/external/news", status_code=201)
def post_news(payload: NewsCreateIn) -> dict:
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    item_id = external_store.new_id()
    item = external_store.write_item(
        "news",
        {
            "id": item_id,
            "kind": "news",
            "status": "queued",
            "source_url": url,
            "title": url,
        },
    )
    threading.Thread(
        target=_run_news_analysis, args=(item_id, url), daemon=True
    ).start()
    return item


@router.get("/external/news")
def get_news_list() -> list[dict]:
    return external_store.list_items("news")


@router.get("/external/news/{item_id}")
def get_news(item_id: str) -> dict:
    item = external_store.get_item("news", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return item


@router.get("/external/news/{item_id}/archive", response_class=Response)
def get_news_archive(item_id: str) -> Response:
    """Serve the archived HTML for a news item."""
    from fastapi.responses import HTMLResponse

    item = external_store.get_item("news", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    p = external_store.archive_path("news", item_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Archive not available")
    return HTMLResponse(content=p.read_text(encoding="utf-8"))


@router.delete("/external/news/{item_id}", status_code=204)
def delete_news(item_id: str) -> None:
    if not external_store.delete_item("news", item_id):
        raise HTTPException(status_code=404, detail="News item not found")


@router.post("/external/news/{item_id}/retry")
def retry_news(item_id: str) -> dict:
    """Re-run the analysis pipeline for a news item — useful when the
    initial run hit `analysis_error` (e.g. OPENAI_API_KEY wasn't loaded yet).
    """
    item = external_store.get_item("news", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    url = item.get("source_url") or item.get("final_url")
    if not url:
        raise HTTPException(status_code=400, detail="Item has no source URL")
    external_store.update_item(
        "news",
        item_id,
        status="queued",
        analysis_error=None,
        error=None,
    )
    threading.Thread(
        target=_run_news_analysis, args=(item_id, url), daemon=True
    ).start()
    return external_store.get_item("news", item_id) or {}


# ---- External research ----


def _run_external_research_analysis(
    item_id: str, file_path: str, hint_title: str | None
) -> None:
    try:
        external_store.update_item("external_research", item_id, status="extracting")
        text = _extract_text_from_file(file_path)
        if not text:
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error="Couldn't extract text from this file type.",
            )
            return
        external_store.update_item(
            "external_research",
            item_id,
            status="analyzing",
            raw_text_chars=len(text),
        )
        analysis = text_analysis.analyze(text, hint_title=hint_title)
        if "error" in analysis:
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error=analysis["error"],
            )
            return
        external_store.update_item(
            "external_research",
            item_id,
            status="ready",
            summary=analysis.get("summary"),
            key_points=analysis.get("key_points") or [],
            language=analysis.get("language") or "other",
            translation=analysis.get("translation"),
            title=(analysis.get("title") or hint_title or "Untitled"),
        )
    except Exception as exc:  # noqa: BLE001
        external_store.update_item(
            "external_research",
            item_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )


def _extract_text_from_file(path_str: str) -> str:
    """Best-effort text extraction from PDF/DOCX/TXT. Returns "" if we can't."""
    from pathlib import Path

    p = Path(path_str)
    if not p.exists():
        return ""
    suffix = p.suffix.lower()
    try:
        if suffix == ".txt":
            return p.read_text(encoding="utf-8", errors="ignore")[:60_000]
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                return ""
            reader = PdfReader(str(p))
            chunks = []
            for page in reader.pages[:50]:
                chunks.append(page.extract_text() or "")
            return "\n".join(chunks)[:60_000]
        if suffix in (".docx", ".doc"):
            try:
                from docx import Document  # type: ignore
            except ImportError:
                return ""
            doc = Document(str(p))
            return "\n".join(p_.text for p_ in doc.paragraphs)[:60_000]
    except Exception:
        return ""
    return ""


@router.post("/external/research", status_code=201)
async def post_external_research(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source_company: str | None = Form(None),
    contact_name: str | None = Form(None),
    contact_email: str | None = Form(None),
    notes: str | None = Form(None),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    item_id = external_store.new_id()

    # Stage the file under data/external/external_research/files/<id>__<name>
    from pathlib import Path

    files_dir = external_store._kind_dir("external_research") / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    safe_name = files_store._sanitize_filename(file.filename)
    stored_name = f"{item_id}__{safe_name}"
    stored_path = files_dir / stored_name
    tmp = stored_path.with_suffix(stored_path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(stored_path)

    item = external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "queued",
            "title": (title or "").strip() or safe_name,
            "filename": safe_name,
            "stored_name": stored_name,
            "size_bytes": len(data),
            "content_type": file.content_type or "",
            "source_company": (source_company or "").strip() or None,
            "contact_name": (contact_name or "").strip() or None,
            "contact_email": (contact_email or "").strip() or None,
            "notes": (notes or "").strip() or None,
        },
    )
    threading.Thread(
        target=_run_external_research_analysis,
        args=(item_id, str(stored_path), item.get("title")),
        daemon=True,
    ).start()
    return item


@router.get("/external/research")
def get_external_research_list() -> list[dict]:
    return external_store.list_items("external_research")


@router.get("/external/research/{item_id}")
def get_external_research(item_id: str) -> dict:
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    return item


@router.get("/external/research/{item_id}/file")
def get_external_research_file(item_id: str) -> FileResponse:
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    stored = item.get("stored_name")
    if not stored:
        raise HTTPException(status_code=404, detail="No file attached")
    p = external_store._kind_dir("external_research") / "files" / stored
    if not p.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path=str(p),
        filename=item.get("filename") or stored,
        media_type=item.get("content_type") or "application/octet-stream",
    )


@router.delete("/external/research/{item_id}", status_code=204)
def delete_external_research(item_id: str) -> None:
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    stored = item.get("stored_name")
    if stored:
        p = external_store._kind_dir("external_research") / "files" / stored
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    external_store.delete_item("external_research", item_id)


# ---- High-fidelity PDF translation for external research ----


def _research_translate_progress_path(item_id: str):
    base = external_store._kind_dir("external_research") / "translations"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{item_id}__translate.progress.jsonl"


def _run_research_translate_job(item_id: str, app_language: str | None) -> None:
    progress = job_progress.ProgressLog(_research_translate_progress_path(item_id))
    progress.emit("stage", stage="starting", message="Starting translation")
    try:
        result = external_translate.translate_research_pdf(
            item_id, app_language=app_language, progress=progress
        )
        if result.get("ok"):
            progress.emit(
                "done",
                detected_language=result.get("detected_language"),
                target_language=result.get("target_language"),
            )
        else:
            progress.emit("error", error=result.get("error") or "Unknown error")
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Job crashed: {type(exc).__name__}: {exc}"
        )


@router.post("/external/research/{item_id}/translate")
def post_research_translate(item_id: str, app_language: str | None = None) -> dict:
    """Kick off a high-fidelity PDF translation job for this research item.

    Returns ``{job_id, stream_url}`` for the live progress stream. Cached
    translations come back inline (``cached: true``) when the language
    already matches the request — call with a different ``app_language`` or
    delete and re-upload to force a re-translate.
    """
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")

    cached = item.get("pdf_translation")
    if cached and cached.get("target_language") and (
        not app_language or cached.get("target_language") == app_language
    ):
        return {
            "cached": True,
            "translation": cached,
        }

    progress_path = _research_translate_progress_path(item_id)
    state = _scan_progress_state(progress_path)
    if state.get("exists") and not state.get("terminated"):
        return {
            "cached": False,
            "job_id": item_id,
            "stream_url": f"/api/external/research/{item_id}/translate/stream",
            "status": "already_running",
        }

    threading.Thread(
        target=_run_research_translate_job,
        args=(item_id, app_language),
        name=f"research_translate:{item_id}",
        daemon=True,
    ).start()
    return {
        "cached": False,
        "job_id": item_id,
        "stream_url": f"/api/external/research/{item_id}/translate/stream",
        "status": "queued",
    }


@router.get("/external/research/{item_id}/translation")
def get_research_translation(item_id: str) -> dict:
    """Return the cached structured translation, or 404 if none yet."""
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    cached = item.get("pdf_translation")
    if not cached:
        raise HTTPException(status_code=404, detail="No translation yet")
    return cached


@router.get("/external/research/{item_id}/translate/stream")
async def stream_research_translate_progress(item_id: str):
    """SSE tail of the translation progress JSONL for this item."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if external_store.get_item("external_research", item_id) is None:
        raise HTTPException(status_code=404, detail="Research item not found")

    progress_path = _research_translate_progress_path(item_id)

    async def event_stream():
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this job\"}\n\n"
            return

        pos = 0
        idle_deadline = time.monotonic() + 1800.0
        terminated = False
        while time.monotonic() < idle_deadline and not terminated:
            try:
                with progress_path.open("r", encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
            except Exception:
                await asyncio.sleep(0.2)
                continue
            if chunk:
                idle_deadline = time.monotonic() + 1800.0
                for line in chunk.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    yield f"data: {line}\n\n"
                    try:
                        entry = _json.loads(line)
                        if entry.get("type") in ("done", "error"):
                            terminated = True
                            break
                    except Exception:
                        pass
            else:
                await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/external/research/{item_id}/retry")
def retry_external_research(item_id: str) -> dict:
    """Re-run the analysis pipeline for an external research item."""
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    stored = item.get("stored_name")
    if not stored:
        raise HTTPException(status_code=400, detail="Item has no file")
    p = external_store._kind_dir("external_research") / "files" / stored
    if not p.exists():
        raise HTTPException(status_code=400, detail="File missing on disk")
    external_store.update_item(
        "external_research",
        item_id,
        status="queued",
        analysis_error=None,
        error=None,
    )
    threading.Thread(
        target=_run_external_research_analysis,
        args=(item_id, str(p), item.get("title")),
        daemon=True,
    ).start()
    return external_store.get_item("external_research", item_id) or {}


# ---- Combined news + research feed ----


@router.get("/external/feed")
def get_external_feed() -> list[dict]:
    """Combined news + external_research, sorted newest first."""
    return external_store.list_news_and_research()


# ---- Hormuz research (internal, no AI) ----


@router.post("/external/hormuz", status_code=201)
async def post_hormuz(
    title: str = Form(...),
    body: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict:
    title = (title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    item_id = external_store.new_id()

    record: dict = {
        "id": item_id,
        "kind": "hormuz_research",
        "status": "ready",
        "title": title,
        "body": (body or "").strip(),
    }

    if file is not None and file.filename:
        data = await file.read()
        if data:
            files_dir = external_store._kind_dir("hormuz_research") / "files"
            files_dir.mkdir(parents=True, exist_ok=True)
            safe_name = files_store._sanitize_filename(file.filename)
            stored_name = f"{item_id}__{safe_name}"
            stored_path = files_dir / stored_name
            tmp = stored_path.with_suffix(stored_path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(stored_path)
            record.update(
                filename=safe_name,
                stored_name=stored_name,
                size_bytes=len(data),
                content_type=file.content_type or "",
            )

    return external_store.write_item("hormuz_research", record)


@router.get("/external/hormuz")
def get_hormuz_list() -> list[dict]:
    return external_store.list_items("hormuz_research")


@router.get("/external/hormuz/{item_id}")
def get_hormuz(item_id: str) -> dict:
    item = external_store.get_item("hormuz_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Hormuz item not found")
    return item


@router.get("/external/hormuz/{item_id}/file")
def get_hormuz_file(item_id: str) -> FileResponse:
    item = external_store.get_item("hormuz_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Hormuz item not found")
    stored = item.get("stored_name")
    if not stored:
        raise HTTPException(status_code=404, detail="No file attached")
    p = external_store._kind_dir("hormuz_research") / "files" / stored
    if not p.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path=str(p),
        filename=item.get("filename") or stored,
        media_type=item.get("content_type") or "application/octet-stream",
    )


@router.delete("/external/hormuz/{item_id}", status_code=204)
def delete_hormuz(item_id: str) -> None:
    item = external_store.get_item("hormuz_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Hormuz item not found")
    stored = item.get("stored_name")
    if stored:
        p = external_store._kind_dir("hormuz_research") / "files" / stored
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    external_store.delete_item("hormuz_research", item_id)


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
        "language": c.get("language"),
        "translation": c.get("translation"),
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
