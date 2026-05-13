"""HTTP API for the research center."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from . import (
    auth_store,
    cache,
    browser_archive,
    claude_runner,
    companies_ai,
    companies_autocomplete,
    company_translate,
    console_session,
    console_store,
    deck_summary,
    external_store,
    external_translate,
    files_store,
    generator,
    job_progress,
    link_preview as link_preview_mod,
    memo_prep,
    news_archive,
    research_store,
    storage,
    text_analysis,
)

logger = logging.getLogger("bsh.api")


# ---- Auth ---------------------------------------------------------------
#
# All /api/* routes go through ``require_api_token``. A request is
# accepted if it presents EITHER:
#
#   (a) the shared ``BSH_RESEARCH_API_TOKEN`` env value — this is the
#       legacy / "meta-tag" flow used by the SPA when the server splices
#       the token into the served HTML; or
#   (b) a per-session bearer token previously issued by
#       ``POST /api/auth/token`` (the email+password login endpoint).
#       These are stored hashed in ``data/sessions.json`` with a 30-day
#       TTL — see ``server/auth_store.py``.
#
# Either kind may be presented as:
#   - ``Authorization: Bearer <token>`` header (preferred — used by the
#     web SPA, mobile clients, and external tooling)
#   - ``Authorization: Bearer sha256:<digest>`` (only the shared token
#     accepts a sha256-prefixed form; session tokens never do)
#   - ``?token=<token>`` query parameter (for EventSource SSE and
#     ``<a href="...">`` download links that can't set headers)
#
# When ``BSH_RESEARCH_API_TOKEN`` is empty/unset AND no users have logged
# in yet, the dependency is a no-op so local development without auth
# still works.


def _expected_token() -> str | None:
    """Read the configured token at call time (so test/runtime changes to
    the environment take effect without restart).
    """
    return _normalize_api_token(os.environ.get("BSH_RESEARCH_API_TOKEN"))


def _normalize_api_token(value: str | None) -> str | None:
    token_value = (value or "").strip()
    if token_value.lower().startswith("bearer "):
        token_value = token_value[7:].strip()
    return token_value or None


def _sha256_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_token_digest(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized.lower().startswith("sha256:"):
        return None
    digest = normalized.split(":", 1)[1].strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return None
    return digest


def _api_token_matches(presented: str | None, expected: str) -> bool:
    if not presented:
        return False
    if secrets.compare_digest(presented, expected):
        return True

    expected_hash = _hash_token_digest(expected) or _sha256_token(expected)
    presented_hash = _hash_token_digest(presented)
    if presented_hash:
        return secrets.compare_digest(presented_hash, expected_hash)

    if _hash_token_digest(expected):
        return secrets.compare_digest(_sha256_token(presented), expected_hash)
    return False


def _describe_api_token(raw_value: str | None, normalized_value: str | None) -> str:
    """Render an auth-token attempt for logs without leaking the raw token.

    Shows length, kind (raw vs sha256), a short sha256 fingerprint, and
    whether the original header carried the ``Bearer `` prefix — enough
    to debug client/server token mismatches without writing the secret
    itself to disk.
    """
    normalized = normalized_value or ""
    raw = (raw_value or "").strip()
    had_bearer_prefix = raw.lower().startswith("bearer ")
    if not normalized:
        return f"present=false raw_len={len(raw)} bearer_prefix={had_bearer_prefix}"

    token_hash = _hash_token_digest(normalized)
    token_kind = "sha256" if token_hash else "raw"
    digest = (token_hash or _sha256_token(normalized))[:12]
    if token_hash:
        display = f"sha256:{token_hash[:12]}..."
    elif len(normalized) <= 8:
        display = f"{normalized[:2]}...{normalized[-2:]}"
    else:
        display = f"{normalized[:4]}...{normalized[-4:]}"
    return (
        f"present=true kind={token_kind} value={display} len={len(normalized)} "
        f"sha256={digest} bearer_prefix={had_bearer_prefix}"
    )


def _extract_presented_token(
    request: Request, query_token: str | None
) -> tuple[str | None, str | None]:
    """Read whatever the client presented (header or ?token=) and return
    ``(presented, raw_for_logging)``. Does not validate."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return _normalize_api_token(auth[7:]), auth
    if query_token:
        return _normalize_api_token(query_token), query_token
    return None, None


def require_api_token(
    request: Request,
    token: str | None = Query(default=None),
) -> None:
    """FastAPI dependency: enforce bearer-token auth on /api/* routes.

    Accepts the shared env-configured token OR any non-expired
    per-session token issued via ``POST /api/auth/token``.
    """
    presented, presented_raw = _extract_presented_token(request, token)
    expected = _expected_token()

    # Dev mode: no env token configured AND no session token presented →
    # let everything through so local-only development still works.
    if not expected and presented is None:
        return

    # Fast path 1: shared env token (legacy / meta-tag flow).
    if expected and _api_token_matches(presented, expected):
        return

    # Fast path 2: a session token issued by the login endpoint.
    session = auth_store.validate_token(presented) if presented else None
    if session:
        # Stash the authenticated email on request.state so future routes
        # (audit logs, "who am I") can pull it without re-validating.
        request.state.session_email = session.get("email")
        return

    logger.warning(
        "API token rejected path=%s presented={%s} expected={%s} session=%s",
        request.url.path,
        _describe_api_token(presented_raw, presented),
        _describe_api_token(os.environ.get("BSH_RESEARCH_API_TOKEN"), expected or ""),
        bool(session),
    )
    raise HTTPException(
        status_code=401,
        detail="Missing or invalid API token",
    )


router = APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])

# Public (unauthenticated) auth routes — registered separately on the
# app in main.py so they aren't gated by ``require_api_token``. Today
# only the login endpoint lives here; logout / "who am I" are on the
# main authenticated router below.
auth_router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    email: str = Field(..., description="Account email address")
    password: str = Field(..., description="Plain-text password — verified against PBKDF2 hash")


class LoginResponse(BaseModel):
    token: str
    email: str
    created_at: str
    expires_at: str


@auth_router.post("/token", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Email + password → freshly minted per-session bearer token.

    On success the caller stores ``token`` and presents it as
    ``Authorization: Bearer <token>`` on every subsequent ``/api/*``
    call. The token is valid for 30 days unless revoked via
    ``POST /api/auth/logout``.
    """
    email = auth_store.verify_credentials(payload.email, payload.password)
    if not email:
        logger.warning(
            "Login rejected for email=%r (no match or bad password)",
            payload.email,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    session = auth_store.issue_session(email)
    logger.info("Login accepted email=%s expires_at=%s", email, session["expires_at"])
    return LoginResponse(**session)


@router.get("/auth/me")
def auth_me(request: Request) -> dict:
    """Identify the caller — useful for the SPA to confirm a stored
    token is still valid and to show the logged-in email in the UI.
    Returns ``{email, auth: 'session' | 'shared'}``.
    """
    email = getattr(request.state, "session_email", None)
    return {
        "email": email,
        "auth": "session" if email else "shared",
    }


@router.post("/auth/logout", status_code=204)
def logout(request: Request, token: str | None = Query(default=None)) -> Response:
    """Revoke the bearer token used on this request. Safe to call even if
    the token was the shared env token (it's a no-op then).
    """
    presented, _ = _extract_presented_token(request, token)
    if presented:
        auth_store.revoke_token(presented)
    return Response(status_code=204)

REPORT_TYPES = (
    "Investment Memo (Late-Stage)",
    "Investment Report",
    "Background",
    "Financial Analysis",
    "Market Analysis",
)
AUDIENCES = ("LP", "Assistant", "Partner", "Internal")
LANGUAGES = ("en", "zh")


@router.get("/health")
def api_health() -> dict:
    return {"status": "ok", "service": "bsh-research-api"}


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
    # Memo-run extensions (only set for kind=investment_memo_latestage).
    kind: str | None = None
    run_id: str | None = None
    run_dir: str | None = None
    skill: str | None = None
    memo_files: list[dict] = Field(default_factory=list)


class ReportDetail(ReportSummary):
    content: str = ""
    stages: list[dict] = Field(default_factory=list)
    # Memo-run extensions.
    content_en: str | None = None
    content_zh: str | None = None
    warnings: list[str] = Field(default_factory=list)
    scope_check: dict | None = None
    stream_url: str | None = None
    log_url: str | None = None
    download_urls: dict | None = None


class GenerateRequest(BaseModel):
    company_id: str
    report_type: str
    audience: str
    language: str = "en"


class MemoPrepRequest(BaseModel):
    """Request body for POST /api/memos/prep — kicks off the synchronous
    memo-run bootstrap (company resolve, scope check, run-folder mint,
    input staging) before the long-running analysis composite job."""
    company_id: str


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
    progress.emit(
        "job_init",
        kind="search",
        title=f'Searching "{query}"',
        subtitle="Company deep search",
        query=query,
        refresh=refresh,
    )
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

    No-op if a translation already exists (unless `force=True`). Note:
    company-record translation is currently disabled — see
    ``server/company_translate.py``.
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

    Progress is streamed into the search-job JSONL so the ActiveJobsRail can
    surface this work alongside other in-flight Claude tasks. The HTTP call
    stays synchronous — the response carries the refreshed company once the
    underlying deep-search returns.
    """
    from . import cache

    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    name = company.get("name") or ""
    if not name:
        raise HTTPException(status_code=400, detail="Company has no name to query")

    progress = job_progress.ProgressLog(
        _search_progress_path(f"refresh_{company_id}")
    )
    progress.emit(
        "job_init",
        kind="search",
        title=f"Refreshing {name}",
        subtitle="Company refresh",
        query=name,
        refresh=True,
        company_id=company_id,
    )
    progress.emit("stage", stage="starting", message="Starting refresh", query=name)
    try:
        result = companies_ai.deep_search(
            name, force_refresh=True, progress=progress
        )
        matches = result.get("matches") or []
        chosen: dict | None = next(
            (m for m in matches if m.get("id") == company_id), None
        )
        if chosen is None and matches:
            chosen = matches[0]
        progress.emit("stage", stage="translating", message="Translating company record")
        _ensure_company_translation(company_id, force=True)
        refreshed = storage.get_company(company_id) or chosen or company
        view = _company_view(refreshed)
        # Patch any cached deep-search result that referenced this company so
        # future cache hits don't show stale data.
        cache.update_in_namespace(
            "companies_ai",
            predicate=lambda item: item.get("id") == company_id,
            transform=lambda _item: dict(view),
        )
        progress.emit(
            "done",
            source=result.get("source"),
            matches=matches,
            cached_at=result.get("cached_at"),
            reason=result.get("reason"),
        )
        return CompanyOut(**view)
    except HTTPException:
        progress.emit("error", error="HTTPException")
        raise
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Refresh crashed: {type(exc).__name__}: {exc}"
        )
        raise


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

    # Investment memos route through the bsh-investment-memo-latestage prep
    # pipeline (run folder, scope check, input staging) instead of the
    # legacy placeholder generator.
    if payload.report_type == memo_prep.REPORT_TYPE:
        try:
            result = memo_prep.bootstrap_memo_run(payload.company_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        report = storage.get_report(result["report_id"])
        if report is None:
            raise HTTPException(status_code=500, detail="Report record vanished after prep")
        return ReportDetail(**_report_detail(report))

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


@router.get("/reports/{report_id}/download")
def download_memo(report_id: str, language: str = "en") -> FileResponse:
    """Download a memo .docx in the requested language.

    Returns 404 if the report doesn't exist, isn't an investment memo, or
    the rendered file isn't on disk (e.g., still running, or the run
    folder was deleted).
    """
    if language not in ("en", "zh"):
        raise HTTPException(status_code=400, detail="language must be 'en' or 'zh'")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("kind") != "investment_memo_latestage":
        raise HTTPException(
            status_code=404, detail="Report is not an investment memo"
        )
    memo_files = report.get("memo_files") or []
    target = next((f for f in memo_files if f.get("language") == language), None)
    if not target or not target.get("path"):
        raise HTTPException(status_code=404, detail=f"No {language} file recorded")
    repo_root = memo_prep.DATA_DIR.parent
    file_path = (repo_root / target["path"]).resolve()
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Memo file not found on disk; the run folder may have been "
                f"deleted: {target['path']}"
            ),
        )
    # Suggest a clean download filename — the on-disk name already includes
    # the company name, type label, and timestamp.
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


@router.post("/memos/prep", status_code=201)
def post_memo_prep(payload: MemoPrepRequest) -> ReportDetail:
    """Bootstrap an investment-memo run.

    Synchronously resolves the company, mints the run folder, runs the
    late-stage / pre-IPO scope check, stages source materials, and writes
    the manifest skeleton. On scope-check failure the run folder is
    preserved (browseable in the sidebar with a failed badge) and the
    response carries `status: failed_scope_check` plus the scope reason.
    """
    try:
        result = memo_prep.bootstrap_memo_run(payload.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    report = storage.get_report(result["report_id"])
    if report is None:
        raise HTTPException(status_code=500, detail="Report record vanished after prep")
    return ReportDetail(**_report_detail(report))


@router.get("/memos/{report_id}/stream")
async def stream_memo_progress(report_id: str) -> "StreamingResponse":
    """SSE stream of progress events for a memo run.

    Replays the run's stream.jsonl from the start and tails it until a
    `done` or `error` terminal event lands. The same stream is shared by
    the prep stage and (later) the analysis composite job.
    """
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Memo report not found")
    run_dir = report.get("run_dir")
    if not run_dir:
        raise HTTPException(status_code=404, detail="Report has no run_dir")
    repo_root = memo_prep.DATA_DIR.parent
    progress_path = memo_prep.stream_path(repo_root / run_dir)

    async def event_stream():
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this memo run\"}\n\n"
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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


# --- Research library (Serena's background-documents folder) -------------
#
# Distinct from /companies/{id}/files (the Document Library). The research
# library is where the analyst drops PitchBook PDFs, partner notes, etc.
# that the investment-memo skill is meant to read. See docs/architecture.md.

@router.get("/companies/{company_id}/research-files")
def get_research_files(company_id: str) -> list[dict]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return research_store.list_files(company_id)


@router.post("/companies/{company_id}/research-files", status_code=201)
async def post_research_file(
    company_id: str,
    file: UploadFile = File(...),
    label: str | None = Form(None),
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    data = await file.read()
    try:
        return research_store.upload_file(
            company_id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
            label=label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/research-files/{file_id}")
def get_research_file(
    company_id: str, file_id: str, inline: bool = False
) -> FileResponse:
    """Stream a research-library file. Pass ``inline=1`` for inline
    Content-Disposition so PDFs / images render inside an iframe."""
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    found = research_store.get_file(company_id, file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    record, path = found
    filename = record.get("filename") or path.name
    media_type = record.get("content_type") or "application/octet-stream"
    if inline:
        return FileResponse(
            path=str(path),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    return FileResponse(path=str(path), filename=filename, media_type=media_type)


@router.delete("/companies/{company_id}/research-files/{file_id}",
               status_code=204)
def delete_research_file(company_id: str, file_id: str) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not research_store.delete_file(company_id, file_id):
        raise HTTPException(status_code=404, detail="File not found")


def _run_research_summary_job(company_id: str, file_id: str) -> None:
    """Background worker for a research-library quick-summary job. Streams
    progress events to a JSONL file (visible in the AI Tasks rail) and
    persists the final summary onto the file record."""
    from pathlib import Path

    progress_path = research_store.quick_summary_progress_path(
        company_id, file_id
    )
    progress = job_progress.ProgressLog(progress_path)
    try:
        found = research_store.get_file(company_id, file_id)
        company_name = (storage.get_company(company_id) or {}).get("name") or company_id
        record_for_init = found[0] if found else {}
        progress.emit(
            "job_init",
            kind="research_summary",
            title=record_for_init.get("filename") or "Research summary",
            subtitle=company_name,
            company_id=company_id,
            file_id=file_id,
            filename=record_for_init.get("filename"),
            file_kind=record_for_init.get("kind"),
        )
        progress.emit("stage", stage="starting", message="Starting quick summary")
        if found is None:
            progress.emit("error", error="File not found")
            return
        record, path = found
        kind = record.get("kind") or "text"
        summary = claude_runner.run_quick_summary(
            source_path=path,
            work_dir=path.parent,
            kind=kind,
            hint_title=record.get("label") or record.get("filename"),
            progress=progress,
        )
        if "error" in summary:
            progress.emit("error", error=summary["error"])
            return
        research_store.update_record(
            company_id, file_id, quick_summary=summary
        )
        progress.emit("done", summary=summary)
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Job crashed: {type(exc).__name__}: {exc}"
        )


@router.post(
    "/companies/{company_id}/research-files/{file_id}/summary",
    status_code=202,
)
def post_research_file_summary(company_id: str, file_id: str) -> dict:
    """Kick off the quick-summary job in the background.

    Returns immediately with the job descriptor (stream_url, log_url) —
    the actual Claude run takes 5–30s and progresses via the AI Tasks
    rail. The summary lands on the file's index record when done; the
    FE polls the file list to detect completion (and the user can click
    the rail entry to watch live).
    """
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Reset any prior summary so the UI shows the new run cleanly.
    research_store.update_record(company_id, file_id, quick_summary=None)

    threading.Thread(
        target=_run_research_summary_job,
        args=(company_id, file_id),
        name=f"research-summary-{company_id}-{file_id}",
        daemon=True,
    ).start()
    return {
        "kind": "research_summary",
        "company_id": company_id,
        "file_id": file_id,
        "stream_url": (
            f"/api/companies/{company_id}/research-files/{file_id}/summary/stream"
        ),
        "log_url": (
            f"/api/jobs/log?path=research_summary:{company_id}/{file_id}"
        ),
    }


@router.delete(
    "/companies/{company_id}/research-files/{file_id}/summary",
    status_code=204,
)
def delete_research_file_summary(company_id: str, file_id: str) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    research_store.update_record(company_id, file_id, quick_summary=None)


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

    Used by the active-jobs listing, idempotent POST handlers, and the
    generic job-log endpoints. Pulls metadata out of the `job_init` event
    so the rail can show kind/title/subtitle for any task.
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
        "page_no": None,
        "page_count": None,
        "speed": None,
        "claude_cost_usd": None,
        "claude_duration_ms": None,
        "error": None,
        # Populated by `job_init` — generic display metadata for the rail.
        "job_init": None,
        "kind": None,
        "title": None,
        "subtitle": None,
        # Most recent claude_action — gives the rail something to tail in
        # real time without making the user open the modal.
        "latest_action": None,
        "tool_count": 0,
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
                if etype == "job_init":
                    state["job_init"] = entry
                    state["kind"] = entry.get("kind")
                    state["title"] = entry.get("title")
                    state["subtitle"] = entry.get("subtitle")
                elif etype in ("done", "error"):
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
                    if "page_no" in entry:
                        state["page_no"] = entry["page_no"]
                    if "page_count" in entry:
                        state["page_count"] = entry["page_count"]
                    if "speed" in entry:
                        state["speed"] = entry["speed"]
                elif etype == "claude_action":
                    action = entry.get("action")
                    if action == "result":
                        if entry.get("cost_usd") is not None:
                            state["claude_cost_usd"] = entry["cost_usd"]
                        if entry.get("duration_ms") is not None:
                            state["claude_duration_ms"] = entry["duration_ms"]
                    # Track the latest user-visible action for the rail.
                    # We surface tool_use, tool_result, thinking, init, and
                    # result — everything except internal book-keeping.
                    if action in ("tool_use", "tool_result", "thinking",
                                  "init", "result"):
                        state["latest_action"] = {
                            "action": action,
                            "tool": entry.get("tool"),
                            "preview": entry.get("preview"),
                            "text": entry.get("text"),
                            "is_error": entry.get("is_error"),
                            "ts": entry.get("ts"),
                        }
                    if action == "tool_use":
                        state["tool_count"] += 1
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
        found = files_store.get_file(company_id, file_id)
        record_for_init = found[0] if found else {}
        company_name = (storage.get_company(company_id) or {}).get("name") or company_id
        progress.emit(
            "job_init",
            kind="summary",
            title=record_for_init.get("label") or record_for_init.get("filename") or "Deck summary",
            subtitle=company_name,
            company_id=company_id,
            file_id=file_id,
            filename=record_for_init.get("filename"),
            file_kind=record_for_init.get("kind"),
            speed=speed,
        )
        progress.emit(
            "stage", stage="starting", message="Starting summary job", speed=speed
        )
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


# ---- Generic AI-task rail / log viewer ----
#
# Each job kind contributes a (glob_root, glob_pattern, adapter) that turns
# matching JSONL paths into the standardized rail record. Add a new tuple
# here when you wire a new Claude task — that's all the rail needs.


def _summary_kind_records():
    from . import files_store as _fs

    if not _fs.UPLOADS_ROOT.exists():
        return
    for jsonl_path in _fs.UPLOADS_ROOT.glob("*/*__summary.progress.jsonl"):
        company_id = jsonl_path.parent.name
        suffix = "__summary.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        file_id = name[: -len(suffix)]
        state = _scan_progress_state(jsonl_path)
        record, _ = _fs.get_file(company_id, file_id) or (None, None)
        title = (
            (state.get("title"))
            or (record and (record.get("label") or record.get("filename")))
            or "Deck summary"
        )
        subtitle = state.get("subtitle") or (
            (storage.get_company(company_id) or {}).get("name") or company_id
        )
        yield {
            "kind": state.get("kind") or "summary",
            "title": title,
            "subtitle": subtitle,
            "stream_url": (
                f"/api/companies/{company_id}/files/{file_id}/summary/stream"
            ),
            "log_url": f"/api/jobs/log?path=summary:{company_id}/{file_id}",
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
                "query": {"file": file_id},
            },
            # Extra summary-specific fields the deck modal still uses.
            "company_id": company_id,
            "file_id": file_id,
            "filename": record and record.get("filename"),
            "speed": state.get("speed"),
            "slide_no": state.get("slide_no"),
            "slide_count": state.get("slide_count"),
            **_common_state_fields(state),
        }


def _search_kind_records():
    base = files_store.UPLOADS_ROOT / "_search"
    if not base.exists():
        return
    for jsonl_path in base.glob("*__search.progress.jsonl"):
        suffix = "__search.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        job_id = name[: -len(suffix)]
        state = _scan_progress_state(jsonl_path)
        yield {
            "kind": state.get("kind") or "search",
            "title": state.get("title") or "Company search",
            "subtitle": state.get("subtitle") or "Web search",
            "stream_url": f"/api/companies/search/stream/{job_id}",
            "log_url": f"/api/jobs/log?path=search:{job_id}",
            "primary_route": {"name": "home"},
            "job_id": job_id,
            **_common_state_fields(state),
        }


def _pdf_translation_kind_records():
    base = external_store._kind_dir("external_research") / "translations"
    if not base.exists():
        return
    for jsonl_path in base.glob("*__translate.progress.jsonl"):
        suffix = "__translate.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        item_id = name[: -len(suffix)]
        state = _scan_progress_state(jsonl_path)
        item = external_store.get_item("external_research", item_id) or {}
        yield {
            "kind": state.get("kind") or "pdf_translation",
            "title": state.get("title") or item.get("title") or item.get("filename") or "PDF translation",
            "subtitle": state.get("subtitle") or "Translation",
            "stream_url": f"/api/external/research/{item_id}/translate/stream",
            "log_url": f"/api/jobs/log?path=pdf_translation:{item_id}",
            "primary_route": {
                "name": "external-research",
                "params": {"id": item_id},
            },
            "item_id": item_id,
            "page_no": state.get("page_no"),
            "page_count": state.get("page_count"),
            **_common_state_fields(state),
        }


def _common_state_fields(state: dict) -> dict:
    return {
        "started_at": state.get("started_at"),
        "last_event_at": state.get("last_event_at"),
        "latest_stage": state.get("latest_stage"),
        "latest_stage_key": state.get("latest_stage_key"),
        "claude_cost_usd": state.get("claude_cost_usd"),
        "claude_duration_ms": state.get("claude_duration_ms"),
        "terminated": state.get("terminated"),
        "terminal_type": state.get("terminal_type"),
        "error": state.get("error"),
        "latest_action": state.get("latest_action"),
        "tool_count": state.get("tool_count"),
    }


def _memo_stream_path_for_report(report_id: str):
    """Resolve a memo-run report id to its on-disk stream JSONL.

    The path lives inside the run folder (data/memos/<slug>/<run>/logs/),
    not under uploads/. Lookup goes through the report record so callers
    can use a stable report_id without knowing the run_dir.
    """
    report = storage.get_report(report_id)
    if report is None:
        raise ValueError(f"Unknown report: {report_id}")
    run_dir = report.get("run_dir")
    if not run_dir:
        raise ValueError(f"Report {report_id} has no run_dir")
    # run_dir is stored relative to the repo root.
    repo_root = memo_prep.DATA_DIR.parent
    return memo_prep.stream_path(repo_root / run_dir)


def _console_hydrate_path(key: str):
    company_id, sid = key.split("/", 1)
    return console_store.hydrate_progress_path(company_id, sid)


def _console_summary_path(key: str):
    company_id, sid = key.split("/", 1)
    return console_store.summary_progress_path(company_id, sid)


def _console_ask_path(key: str):
    company_id, sid, turn_id = key.split("/", 2)
    return console_store.ask_progress_path(company_id, sid, turn_id)


_JOB_KIND_PATHS = {
    "summary": lambda key: (
        files_store._company_dir(key.split("/", 1)[0])
        / f"{key.split('/', 1)[1]}__summary.progress.jsonl"
    ),
    "search": lambda key: files_store.UPLOADS_ROOT
    / "_search"
    / f"{key}__search.progress.jsonl",
    "pdf_translation": lambda key: external_store._kind_dir("external_research")
    / "translations"
    / f"{key}__translate.progress.jsonl",
    "memo": _memo_stream_path_for_report,
    "research_summary": lambda key: research_store.quick_summary_progress_path(
        key.split("/", 1)[0], key.split("/", 1)[1]
    ),
    "console_hydrate": _console_hydrate_path,
    "console_ask": _console_ask_path,
    "console_summary": _console_summary_path,
}


def _research_summary_kind_records():
    """Yield active-jobs rail entries for every quick-summary JSONL on disk."""
    if not research_store.RESEARCH_ROOT.exists():
        return
    for jsonl_path in research_store.RESEARCH_ROOT.glob(
        "*/*__quick_summary.progress.jsonl"
    ):
        company_id = jsonl_path.parent.name
        suffix = "__quick_summary.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        file_id = name[: -len(suffix)]
        state = _scan_progress_state(jsonl_path)
        record_tuple = research_store.get_file(company_id, file_id)
        record = record_tuple[0] if record_tuple else None
        title = (
            state.get("title")
            or (record and (record.get("label") or record.get("filename")))
            or "Quick summary"
        )
        subtitle = state.get("subtitle") or (
            (storage.get_company(company_id) or {}).get("name") or company_id
        )
        yield {
            "kind": state.get("kind") or "research_summary",
            "title": title,
            "subtitle": subtitle,
            "stream_url": (
                f"/api/companies/{company_id}/research-files/{file_id}/summary/stream"
            ),
            "log_url": (
                f"/api/jobs/log?path=research_summary:{company_id}/{file_id}"
            ),
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
            },
            "company_id": company_id,
            "file_id": file_id,
            "filename": record and record.get("filename"),
            **_common_state_fields(state),
        }


def _memo_kind_records():
    """Yield active-jobs rail entries for every memo-run JSONL on disk."""
    if not memo_prep.MEMOS_ROOT.exists():
        return
    for jsonl_path in memo_prep.MEMOS_ROOT.glob("*/*/logs/stream.jsonl"):
        state = _scan_progress_state(jsonl_path)
        init = state.get("job_init") or {}
        report_id = init.get("report_id")
        if not report_id:
            continue
        yield {
            "kind": state.get("kind") or "memo",
            "title": state.get("title") or "Investment memo",
            "subtitle": state.get("subtitle") or "Memo run",
            "stream_url": f"/api/memos/{report_id}/stream",
            "log_url": f"/api/jobs/log?path=memo:{report_id}",
            "primary_route": {
                "name": "report",
                "params": {"reportId": report_id},
            },
            "report_id": report_id,
            "company_id": init.get("company_id"),
            "run_id": init.get("run_id"),
            "run_dir": init.get("run_dir"),
            **_common_state_fields(state),
        }


def _console_kind_records():
    """Yield active-jobs rail entries for Console hydrate/ask/summary jobs.

    Scans ``data/consoles/<company>/sessions/<sid>/`` for the three kinds
    of progress JSONLs the Console writes. Lightweight — re-globs on each
    call, no caching, mirrors the other ``_*_kind_records`` helpers.
    """
    if not console_store.CONSOLES_ROOT.exists():
        return
    for sdir in console_store.CONSOLES_ROOT.glob("*/sessions/*"):
        if not sdir.is_dir():
            continue
        company_id = sdir.parent.parent.name
        sid = sdir.name

        for jsonl_path, kind, log_token, key in (
            (sdir / "hydrate.progress.jsonl", "console_hydrate",
             "console_hydrate", f"{company_id}/{sid}"),
            (sdir / "summary.progress.jsonl", "console_summary",
             "console_summary", f"{company_id}/{sid}"),
        ):
            if not jsonl_path.exists():
                continue
            state = _scan_progress_state(jsonl_path)
            yield {
                "kind": state.get("kind") or kind,
                "title": state.get("title") or "Console",
                "subtitle": state.get("subtitle") or "Console",
                "stream_url": (
                    f"/api/companies/{company_id}/console/sessions/{sid}"
                    + (
                        "/hydrate/stream" if kind == "console_hydrate"
                        else "/summary/stream"
                    )
                ),
                "log_url": f"/api/jobs/log?path={log_token}:{key}",
                "primary_route": {
                    "name": "research",
                    "params": {"companyId": company_id},
                    "query": {"tab": "console"},
                },
                "company_id": company_id,
                "session_id": sid,
                **_common_state_fields(state),
            }

        ask_dir = sdir / "ask"
        if not ask_dir.exists():
            continue
        for jsonl_path in ask_dir.glob("*.progress.jsonl"):
            turn_id = jsonl_path.name.removesuffix(".progress.jsonl")
            state = _scan_progress_state(jsonl_path)
            yield {
                "kind": state.get("kind") or "console_ask",
                "title": state.get("title") or "Console Q&A",
                "subtitle": state.get("subtitle") or "Console",
                "stream_url": (
                    f"/api/companies/{company_id}/console/sessions/{sid}"
                    f"/ask/stream/{turn_id}"
                ),
                "log_url": f"/api/jobs/log?path=console_ask:{company_id}/{sid}/{turn_id}",
                "primary_route": {
                    "name": "research",
                    "params": {"companyId": company_id},
                    "query": {"tab": "console"},
                },
                "company_id": company_id,
                "session_id": sid,
                "turn_id": turn_id,
                **_common_state_fields(state),
            }


def _resolve_job_log_path(combined: str):
    """Resolve a `kind:key` token into its on-disk JSONL path."""
    if ":" not in combined:
        raise HTTPException(status_code=400, detail="Bad path token")
    kind, key = combined.split(":", 1)
    resolver = _JOB_KIND_PATHS.get(kind)
    if resolver is None:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    try:
        return resolver(key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Bad job key: {exc}") from exc


@router.get("/jobs/active")
def get_active_jobs() -> list[dict]:
    """All in-flight Claude tasks across every kind. Powers ActiveJobsRail."""
    out: list[dict] = []
    for source in (
        _summary_kind_records(),
        _search_kind_records(),
        _pdf_translation_kind_records(),
        _memo_kind_records(),
        _research_summary_kind_records(),
        _console_kind_records(),
    ):
        for rec in source:
            if rec.get("terminated"):
                continue
            out.append(rec)
    out.sort(key=lambda j: j.get("started_at") or "", reverse=True)
    return out


@router.get("/jobs/log")
def get_job_log(path: str) -> list[dict]:
    """Return all events from a job's progress JSONL.

    `path` is a `kind:key` token (e.g. `summary:<company_id>/<file_id>`,
    `search:<job_id>`, `pdf_translation:<item_id>`). Used by the generic
    log viewer to replay history before opening an SSE for live tail.
    """
    import json as _json

    p = _resolve_job_log_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="No log for this path")
    events: list[dict] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read log: {exc}") from exc
    return events


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


@router.get(
    "/companies/{company_id}/research-files/{file_id}/summary/stream"
)
async def stream_research_file_summary_progress(
    company_id: str, file_id: str
) -> "StreamingResponse":
    """SSE stream for a research-library quick-summary job."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")

    progress_path = research_store.quick_summary_progress_path(
        company_id, file_id
    )

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

        archive = news_archive.archive_static_html(
            kind="news",
            item_id=item_id,
            html=preview.html,
            page_url=preview.final_url,
            source_url=url,
        )
        browser_status = "not_needed"
        browser_error = None
        analysis_text = preview.text
        reasons = archive.diagnostics.get("browser_fallback_reasons") or []
        if reasons:
            browser_status = "attempted"
            rendered = browser_archive.render_html(preview.final_url or url)
            if rendered.html:
                browser_archive_result = news_archive.archive_static_html(
                    kind="news",
                    item_id=item_id,
                    html=rendered.html,
                    page_url=preview.final_url or url,
                    source_url=url,
                    strategy="browser_rendered_archive",
                )
                archive = browser_archive_result
                if len(rendered.text or "") > len(analysis_text or ""):
                    analysis_text = rendered.text
                browser_status = "used"
            else:
                browser_status = "failed"
                browser_error = rendered.error

        archived_image = archive.public_url(preview.image, item_id) or preview.image
        archived_favicon = archive.public_url(preview.favicon, item_id) or preview.favicon
        archive_diagnostics = {
            **archive.diagnostics,
            "browser_fallback_status": browser_status,
            "browser_fallback_error": browser_error,
        }
        external_store.update_item(
            "news",
            item_id,
            status="analyzing",
            title=preview.title or url,
            description=preview.description,
            site_name=preview.site_name,
            image=archived_image,
            favicon=archived_favicon,
            domain=preview.domain,
            final_url=preview.final_url,
            archive_path=str(external_store.archive_path("news", item_id).name),
            archive_strategy=archive_diagnostics.get("archive_strategy"),
            archive_asset_count=archive_diagnostics.get("downloaded_image_count"),
            archive_failed_asset_count=archive_diagnostics.get("failed_image_count"),
            archive_diagnostics=archive_diagnostics,
            raw_text_chars=len(analysis_text or ""),
        )
        analysis = text_analysis.analyze(analysis_text, hint_title=preview.title)
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
    return HTMLResponse(
        content=p.read_text(encoding="utf-8"),
        headers={
            "Content-Security-Policy": (
                "script-src 'none'; worker-src 'none'; object-src 'none'; "
                "base-uri 'none'; img-src 'self' data: blob: https:; "
                "style-src 'self' 'unsafe-inline' https:; "
                "font-src 'self' data: https:"
            )
        },
    )


@router.get("/external/news/{item_id}/assets/{filename:path}")
def get_news_archive_asset(item_id: str, filename: str) -> FileResponse:
    item = external_store.get_item("news", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    p = external_store.archive_asset_path("news", item_id, filename)
    root = external_store.archive_asset_dir("news", item_id).resolve()
    try:
        resolved = p.resolve()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archive asset not found")
    if root not in resolved.parents or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Archive asset not found")
    return FileResponse(resolved)


@router.delete("/external/news/{item_id}", status_code=204)
def delete_news(item_id: str) -> None:
    if not external_store.delete_item("news", item_id):
        raise HTTPException(status_code=404, detail="News item not found")


@router.post("/external/news/{item_id}/retry")
def retry_news(item_id: str) -> dict:
    """Re-run the analysis pipeline for a news item — useful when the
    initial run hit `analysis_error`.
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
def get_external_research_file(
    item_id: str, inline: bool = False
) -> FileResponse:
    """Stream the uploaded research file.

    Default disposition is `attachment` so direct navigation downloads.
    Pass `inline=1` for `inline` so PDFs render inside an `<iframe>` —
    `FileResponse(filename=...)` always sets attachment, so the inline
    branch builds the header by hand.
    """
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    stored = item.get("stored_name")
    if not stored:
        raise HTTPException(status_code=404, detail="No file attached")
    p = external_store._kind_dir("external_research") / "files" / stored
    if not p.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    filename = item.get("filename") or stored
    media_type = item.get("content_type") or "application/octet-stream"
    if inline:
        return FileResponse(
            path=str(p),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    return FileResponse(
        path=str(p),
        filename=filename,
        media_type=media_type,
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
    item = external_store.get_item("external_research", item_id) or {}
    progress.emit(
        "job_init",
        kind="pdf_translation",
        title=item.get("title") or item.get("filename") or "PDF translation",
        subtitle=f"→ {app_language or 'auto'}",
        item_id=item_id,
        filename=item.get("filename"),
        target_language=app_language,
    )
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
        "kind": r.get("kind"),
        "run_id": r.get("run_id"),
        "run_dir": r.get("run_dir"),
        "skill": r.get("skill"),
        "memo_files": list(r.get("memo_files") or []),
    }


def _report_detail(r: dict) -> dict:
    base = {
        **_report_summary(r),
        "content": r.get("content") or "",
        "stages": list(r.get("stages") or []),
        "content_en": r.get("content_en"),
        "content_zh": r.get("content_zh"),
        "warnings": list(r.get("warnings") or []),
        "scope_check": r.get("scope_check"),
    }
    # Attach unified-rail URLs and download links for memo runs so the
    # frontend can tail the same JSONL the prep wrote and offer
    # ready-to-click .docx downloads.
    if r.get("kind") == "investment_memo_latestage" and r.get("id"):
        rid = r["id"]
        base["stream_url"] = f"/api/memos/{rid}/stream"
        base["log_url"] = f"/api/jobs/log?path=memo:{rid}"
        base["download_urls"] = {
            "en": f"/api/reports/{rid}/download?language=en",
            "zh": f"/api/reports/{rid}/download?language=zh",
        }
    return base


# ---- Console API ---------------------------------------------------------
#
# Per-company Console feature (see docs/console-feature.md). All ten routes
# inherit the api_router auth dependency; the two SSE endpoints accept
# ``?token=`` via the existing extractor since EventSource can't set
# headers.


class _ConsoleCreateBody(BaseModel):
    include_background_docs: bool = True
    include_library_docs: bool = True


def _serialize_console_meta(meta: dict) -> dict:
    """Wire shape — adds derived fields the frontend wants but we don't
    want to keep duplicated on disk.
    """
    tokens = meta.get("tokens") or {}
    context_used = console_store.context_used_from_usage(
        tokens.get("last_turn_usage")
    )
    return {
        **meta,
        "context_used": context_used,
        "context_window": console_store.CONTEXT_WINDOW,
        "pct_used": context_used / console_store.CONTEXT_WINDOW,
    }


@router.get("/companies/{company_id}/console/sessions")
def list_console_sessions(company_id: str) -> list[dict]:
    return [
        _serialize_console_meta(m)
        for m in console_store.list_sessions(company_id)
    ]


# Rough heuristics for the cost-estimate endpoint. Tokens-per-byte for
# document content is highly variable; the goal here is to give the user
# an order-of-magnitude before they spend real money on hydration.
_EST_TOKENS_PER_BYTE = 0.25  # ≈4 bytes/token for text-heavy content
_EST_USD_PER_M_INPUT = 3.0   # rough Opus 4 input price (cache_creation tier)
_EST_TOKENS_PER_SECOND = 8000


@router.get("/companies/{company_id}/console/estimate")
def estimate_console_hydration(
    company_id: str,
    include_background_docs: bool = True,
    include_library_docs: bool = True,
) -> dict:
    """Preview what the create-console modal will hydrate: file list +
    rough cost + rough duration. Used by the frontend before the user
    confirms a Create."""
    files: list[dict] = []
    total_bytes = 0
    if include_background_docs:
        for entry in research_store.list_files(company_id):
            files.append({
                "id": entry["id"],
                "kind": "research",
                "filename": entry.get("filename") or entry.get("stored_name"),
                "size_bytes": int(entry.get("size_bytes") or 0),
            })
            total_bytes += int(entry.get("size_bytes") or 0)
    if include_library_docs:
        for entry in files_store.list_files(company_id):
            files.append({
                "id": entry["id"],
                "kind": "library",
                "filename": entry.get("filename") or entry.get("stored_name"),
                "size_bytes": int(entry.get("size_bytes") or 0),
            })
            total_bytes += int(entry.get("size_bytes") or 0)
    tokens_est = int(total_bytes * _EST_TOKENS_PER_BYTE)
    cost_usd_est = tokens_est * _EST_USD_PER_M_INPUT / 1_000_000
    duration_est_s = max(5, int(tokens_est / _EST_TOKENS_PER_SECOND))
    return {
        "files": files,
        "tokens_est": tokens_est,
        "cost_usd_est": round(cost_usd_est, 3),
        "duration_est_s": duration_est_s,
    }


@router.post("/companies/{company_id}/console/sessions", status_code=201)
def create_console_session(
    company_id: str, body: _ConsoleCreateBody | None = None
) -> dict:
    body = body or _ConsoleCreateBody()
    try:
        meta = console_session.create_session(
            company_id=company_id,
            include_background_docs=body.include_background_docs,
            include_library_docs=body.include_library_docs,
        )
    except console_store.SessionLimitReached as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "session_limit_reached",
                "limit": console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY,
                "message": str(exc),
            },
        ) from exc
    return {
        **_serialize_console_meta(meta),
        "hydrate_stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}"
            "/hydrate/stream"
        ),
    }


@router.get("/companies/{company_id}/console/sessions/{sid}")
def get_console_session(company_id: str, sid: str) -> dict:
    meta = console_store.load_meta(company_id, sid)
    if meta is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_console_meta(meta)


@router.get("/companies/{company_id}/console/sessions/{sid}/turns")
def get_console_turns(company_id: str, sid: str) -> list[dict]:
    if not console_store.session_exists(company_id, sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return console_store.read_turns(company_id, sid)


@router.post("/companies/{company_id}/console/sessions/{sid}/ask")
async def post_console_ask(
    company_id: str,
    sid: str,
    prompt: str = Form(...),
    images: list[UploadFile] = File(default=[]),
) -> dict:
    if not console_store.session_exists(company_id, sid):
        raise HTTPException(status_code=404, detail="Session not found")

    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    saved: list[str] = []
    for upload in images or []:
        data = await upload.read()
        try:
            record = console_store.save_attachment(
                company_id=company_id,
                session_id=sid,
                filename=upload.filename or "image",
                data=data,
            )
        except console_store.AttachmentTooLarge as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "attachment_too_large",
                    "limit_bytes": console_store.MAX_ATTACHMENT_BYTES,
                    "message": str(exc),
                },
            ) from exc
        except console_store.AttachmentTypeNotAllowed as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "attachment_type_not_allowed",
                    "allowed": sorted(console_store.ALLOWED_ATTACHMENT_TYPES),
                    "message": str(exc),
                },
            ) from exc
        saved.append(record["stored_name"])

    try:
        info = console_session.submit_ask(
            company_id=company_id,
            session_id=sid,
            prompt=prompt.strip(),
            attachments=saved,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "session_archived":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "session_archived",
                    "message": "Session is archived; create a new one.",
                },
            ) from exc
        if code == "session_not_found":
            raise HTTPException(status_code=404, detail="Session not found") from exc
        raise HTTPException(status_code=400, detail=code) from exc

    return {
        "turn_id": info["turn_id"],
        "queue_position": info["queue_position"],
        "stream_url": (
            f"/api/companies/{company_id}/console/sessions/{sid}"
            f"/ask/stream/{info['turn_id']}"
        ),
    }


def _console_event_stream(progress_path: "Path"):
    """Shared SSE generator — replays from the start of the progress file
    and tails new lines until a terminal ``done`` or ``error`` event is
    seen. Mirrors the search-stream pattern.
    """
    import asyncio
    import json as _json
    import time

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

    return event_stream


@router.get(
    "/companies/{company_id}/console/sessions/{sid}/ask/stream/{turn_id}"
)
async def stream_console_ask(
    company_id: str, sid: str, turn_id: str
) -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    try:
        path = console_store.ask_progress_path(company_id, sid, turn_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    gen = _console_event_stream(path)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/companies/{company_id}/console/sessions/{sid}/hydrate/stream"
)
async def stream_console_hydrate(
    company_id: str, sid: str
) -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    try:
        path = console_store.hydrate_progress_path(company_id, sid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    gen = _console_event_stream(path)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/companies/{company_id}/console/sessions/{sid}/summary/stream"
)
async def stream_console_summary(
    company_id: str, sid: str
) -> "StreamingResponse":
    """SSE for the archive-summary subprocess. Used by the AI rail to tail
    the summary as it generates."""
    from fastapi.responses import StreamingResponse

    try:
        path = console_store.summary_progress_path(company_id, sid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    gen = _console_event_stream(path)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/companies/{company_id}/console/sessions/{sid}/ask/{turn_id}/cancel",
    status_code=204,
)
def cancel_console_ask(
    company_id: str, sid: str, turn_id: str
) -> Response:
    try:
        ok = console_session.cancel_turn(company_id, sid, turn_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="No in-flight turn with that id (already complete or unknown)",
        )
    return Response(status_code=204)


@router.get(
    "/companies/{company_id}/console/sessions/{sid}/attachments/{img_id}"
)
def get_console_attachment(
    company_id: str, sid: str, img_id: str
) -> FileResponse:
    try:
        path = console_store.get_attachment_path(company_id, sid, img_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(path)


@router.post(
    "/companies/{company_id}/console/sessions/{sid}/archive"
)
def archive_console_session(company_id: str, sid: str) -> dict:
    meta = console_session.archive_session(company_id=company_id, session_id=sid)
    if meta is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_console_meta(meta)


@router.delete(
    "/companies/{company_id}/console/sessions/{sid}", status_code=204
)
def delete_console_session(company_id: str, sid: str) -> Response:
    ok = console_store.hard_delete_session(company_id, sid)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=204)
