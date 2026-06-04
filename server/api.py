"""HTTP API for the research center."""
from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

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
    companies_ai_public,
    companies_autocomplete,
    company_translate,
    console_session,
    console_store,
    deck_summary,
    external_store,
    external_translate,
    files_store,
    trader_bilingual_fill,
    generator,
    hormuz_console,
    hormuz_prep,
    hormuz_store,
    job_progress,
    link_preview as link_preview_mod,
    memo_prep,
    news_archive,
    research_store,
    serena_analysis,
    storage,
    text_analysis,
    trader_stats,
    weekly_stocks,
)

logger = logging.getLogger("bsh.api")

ACTIVE_JOB_MAX_IDLE_SECONDS = int(
    os.environ.get("BSH_ACTIVE_JOB_MAX_IDLE_SECONDS", "1800")
)
SEARCH_JOB_MAX_IDLE_SECONDS = int(
    os.environ.get("BSH_SEARCH_JOB_MAX_IDLE_SECONDS", "180")
)


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
    company_type: str | None = None  # "public" | "private" (see storage.infer_company_type)
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
    trader_snapshot: dict | None = None  # populated for public companies via /trader/refresh


class ReportSummary(BaseModel):
    id: str
    # Optional: not every report kind is company-scoped (e.g. the Hormuz
    # V3 appendix has no company or audience).
    company_id: str | None = None
    company_name: str | None = None
    report_type: str
    audience: str | None = None
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
    analysis_session_id: str | None = None
    analysis_session_approved: bool = False


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
    preview_urls: dict | None = None


class GenerateRequest(BaseModel):
    company_id: str
    report_type: str
    audience: str
    language: str = "en"
    analysis_session_id: str | None = None


class MemoPrepRequest(BaseModel):
    """Request body for POST /api/memos/prep — kicks off the synchronous
    memo-run bootstrap (company resolve, scope check, run-folder mint,
    input staging) before the long-running analysis composite job."""
    company_id: str
    analysis_session_id: str | None = None


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
    in_flight = _progress_state_in_flight(
        state, max_idle_seconds=SEARCH_JOB_MAX_IDLE_SECONDS
    )
    if in_flight:
        return {
            "cached": False,
            "job_id": job_id,
            "stream_url": f"/api/companies/search/stream/{job_id}",
            "status": "already_running",
        }
    if state.get("exists") and not state.get("terminated"):
        try:
            job_progress.ProgressLog(path).emit(
                "error",
                error="superseded stale company search",
                terminal=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("company search: failed to terminate stale log")
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("company search: failed to unlink stale log")

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


# ---- Weekly hot-stock dashboard -----------------------------------------


def _run_weekly_stocks_job() -> None:
    """Background worker for the weekly hot-stock dashboard refresh."""
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())
    progress.emit(
        "job_init",
        kind="weekly_stocks",
        title="Weekly stock summary",
        subtitle="Hot stocks research",
    )
    progress.emit(
        "stage",
        stage="starting",
        message="Starting weekly hot-stock research",
    )
    try:
        summary, err = weekly_stocks.generate_summary(progress=progress)
    except Exception as exc:  # noqa: BLE001
        logger.exception("weekly stocks job crashed")
        progress.emit(
            "error",
            error=f"Weekly stock research crashed: {type(exc).__name__}: {exc}",
        )
        return
    if err:
        progress.emit("error", error=err)
        return
    progress.emit(
        "done",
        generated_at=summary.get("generated_at") if summary else None,
        summary=summary,
    )


@router.get("/weekly-stocks")
def get_weekly_stocks() -> dict:
    """Return the cached weekly hot-stock dashboard payload, if any."""
    summary = weekly_stocks.load_summary()
    prompt_en = (
        summary.get("research_prompt_en")
        if isinstance(summary, dict) and summary.get("research_prompt_en")
        else weekly_stocks.build_research_prompt()
    )
    prompt_zh = (
        summary.get("research_prompt_zh")
        if isinstance(summary, dict) and summary.get("research_prompt_zh")
        else weekly_stocks.build_research_prompt_zh()
    )
    return {
        "summary": summary,
        "draft": weekly_stocks.load_draft(),
        "prompt": prompt_en,
        "prompt_en": prompt_en,
        "prompt_zh": prompt_zh,
        "refresh_state": _weekly_refresh_state_payload(),
        "schema_version": weekly_stocks.SCHEMA_VERSION,
    }


def _weekly_refresh_state_payload() -> dict | None:
    path = weekly_stocks.progress_path()
    state = _scan_progress_state(path)
    if not state.get("exists"):
        return None
    return {
        "kind": state.get("kind") or "weekly_stocks",
        "title": state.get("title") or "Weekly stock summary",
        "subtitle": state.get("subtitle") or "Hot stocks research",
        **_common_state_fields(state),
    }


@router.post("/weekly-stocks/refresh")
def post_weekly_stocks_refresh(force: bool = False) -> dict:
    """Kick off or attach to the weekly hot-stock dashboard refresh."""
    path = weekly_stocks.progress_path()
    state = _scan_progress_state(path)
    in_flight = _progress_state_in_flight(state)
    stream_url = "/api/weekly-stocks/refresh/stream"
    if in_flight and not force:
        return {
            "job_id": "weekly",
            "stream_url": stream_url,
            "status": "already_running",
        }
    if state.get("exists") and not state.get("terminated"):
        try:
            tail_progress = job_progress.ProgressLog(path)
            tail_progress.emit(
                "error",
                error=(
                    "superseded by force-refresh"
                    if force
                    else "superseded stale weekly refresh"
                ),
                terminal=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("weekly refresh: failed to terminate stale log")
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("weekly refresh: failed to unlink stale log")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        weekly_stocks.clear_draft()
    except Exception:  # noqa: BLE001
        logger.exception("weekly refresh: failed to clear previous progress log")

    threading.Thread(
        target=_run_weekly_stocks_job,
        name="weekly-stocks",
        daemon=True,
    ).start()
    return {
        "job_id": "weekly",
        "stream_url": stream_url,
        "status": "force_queued" if force else "queued",
    }


@router.get("/weekly-stocks/refresh/stream")
async def stream_weekly_stocks_refresh() -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    gen = _console_event_stream(weekly_stocks.progress_path())
    return StreamingResponse(
        gen(),
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


def _refresh_company_summary(company_id: str, *, progress=None) -> dict:
    """Re-run company deep-search enrichment and force its translation.

    Shared by the per-company refresh endpoint and the bulk regen-all job.
    Returns the refreshed ``CompanyOut``-shaped view plus the upstream search
    metadata the caller may want to expose in progress logs.
    """
    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    name = company.get("name") or ""
    if not name:
        raise HTTPException(status_code=400, detail="Company has no name to query")

    result = companies_ai.deep_search(name, force_refresh=True, progress=progress)
    matches = result.get("matches") or []
    chosen: dict | None = next(
        (m for m in matches if m.get("id") == company_id), None
    )
    if chosen is None and matches:
        chosen = matches[0]
    if progress is not None:
        progress.emit(
            "stage",
            stage="translating",
            message="Translating company record",
        )
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
    return {
        "view": view,
        "source": result.get("source"),
        "matches": matches,
        "cached_at": result.get("cached_at"),
        "reason": result.get("reason"),
    }


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
        result = _refresh_company_summary(company_id, progress=progress)
        progress.emit(
            "done",
            source=result.get("source"),
            matches=result.get("matches") or [],
            cached_at=result.get("cached_at"),
            reason=result.get("reason"),
        )
        return CompanyOut(**result["view"])
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
            result = memo_prep.bootstrap_memo_run(
                payload.company_id,
                analysis_session_id=payload.analysis_session_id,
            )
        except memo_prep.AnalysisSessionNotReadyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.get("/reports/{report_id}/preview")
def preview_memo(report_id: str, language: str = "en") -> FileResponse:
    """Serve the rendered PDF of a memo for inline preview.

    Mirrors `download_memo` but targets the `pdf_path` recorded on the
    memo_files entry (rendered post-run from the .docx) and serves it
    with an inline disposition so it renders in an <iframe>/embed rather
    than downloading. Returns 404 if no PDF was produced (e.g. Word
    automation unavailable) — the .docx download is still offered.
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
    if not target or not target.get("pdf_path"):
        raise HTTPException(
            status_code=404,
            detail=f"No {language} PDF preview was rendered for this run",
        )
    repo_root = memo_prep.DATA_DIR.parent
    file_path = (repo_root / target["pdf_path"]).resolve()
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"PDF preview not found on disk; the run folder may have "
                f"been deleted: {target['pdf_path']}"
            ),
        )
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        content_disposition_type="inline",
    )


@router.post("/memos/prep", status_code=201)
def post_memo_prep(payload: MemoPrepRequest) -> ReportDetail:
    """Bootstrap an investment-memo run.

    Synchronously resolves the company, mints the run folder, runs the
    late-stage / pre-IPO scope check, stages source materials, and writes
    the manifest skeleton. Early-stage signals are non-fatal warnings and
    continue into analysis; hard out-of-scope failures preserve the run
    folder and return `status: failed_scope_check` plus the scope reason.
    """
    try:
        result = memo_prep.bootstrap_memo_run(
            payload.company_id,
            analysis_session_id=payload.analysis_session_id,
        )
    except memo_prep.AnalysisSessionNotReadyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.get("/companies/{company_id}/memo-analysis")
def get_memo_analysis(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        session = serena_analysis.get_current_session(company_id, create=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="Memo analysis not found")
    return session


@router.post("/companies/{company_id}/memo-analysis/tools/{tool_name}/run")
def run_memo_analysis_tool(
    company_id: str,
    tool_name: str,
    response: Response,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        if serena_analysis.tool_uses_background_job(tool_name):
            response.status_code = 202
            return serena_analysis.start_analysis_tool_job(company_id, tool_name)
        return serena_analysis.run_tool(company_id, tool_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/companies/{company_id}/memo-analysis/artifacts/{artifact_name}")
def patch_memo_analysis_artifact(
    company_id: str,
    artifact_name: str,
    patch: dict,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.patch_artifact(company_id, artifact_name, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/companies/{company_id}/memo-analysis/research-tasks/{task_id}")
def patch_memo_analysis_research_task(
    company_id: str,
    task_id: str,
    patch: dict,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.patch_research_task(company_id, task_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/memo-analysis/research-tasks/{task_id}/run",
    status_code=202,
)
def run_memo_analysis_research_task(company_id: str, task_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.start_research_task_job(company_id, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/companies/{company_id}/memo-analysis/sessions/{session_id}/research-tasks/{task_id}/stream"
)
async def stream_memo_analysis_research_task(
    company_id: str,
    session_id: str,
    task_id: str,
) -> "StreamingResponse":
    """SSE stream for one Memo Studio research-task job."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if serena_analysis.get_session(company_id, session_id) is None:
        raise HTTPException(status_code=404, detail="Memo analysis session not found")

    progress_path = serena_analysis.research_task_progress_path(
        company_id, session_id, task_id
    )

    async def event_stream():
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this task\"}\n\n"
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


@router.get(
    "/companies/{company_id}/memo-analysis/sessions/{session_id}/tools/{tool_name}/stream"
)
async def stream_memo_analysis_tool(
    company_id: str,
    session_id: str,
    tool_name: str,
) -> "StreamingResponse":
    """SSE stream for one Memo Studio analysis-tool job."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if serena_analysis.get_session(company_id, session_id) is None:
        raise HTTPException(status_code=404, detail="Memo analysis session not found")

    try:
        progress_path = serena_analysis.analysis_tool_progress_path(
            company_id, session_id, tool_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream():
        deadline = time.monotonic() + 5.0
        while not progress_path.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if not progress_path.exists():
            yield "event: error\ndata: {\"error\":\"No progress for this tool\"}\n\n"
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


@router.post("/companies/{company_id}/memo-analysis/approve")
def approve_memo_analysis(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.approve(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    """Return an inline preview suitable for the frontend preview modal.

    PDFs and Markdown are streamed inline as-is. PPT/PPTX files are converted
    via Microsoft PowerPoint (cached on disk after the first run); the
    conversion runs synchronously here for files that weren't converted on
    upload yet.
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
    kind = record.get("kind")
    filename = record.get("filename") or "preview"
    if kind == "md":
        media_type = "text/markdown; charset=utf-8"
        inline_name = filename
    else:
        media_type = "application/pdf"
        base = filename.rsplit(".", 1)[0]
        inline_name = f"{base}.pdf"
    return FileResponse(
        path=str(pdf_path),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{inline_name}"'},
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
    if record.get("kind") == "md":
        media_type = "text/markdown; charset=utf-8"
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
        "index": None,
        "total_count": None,
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
        "backoff_until": None,
        "backoff_remaining_seconds": None,
        "recoverable": None,
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
                    if "total_count" in entry:
                        state["total_count"] = entry["total_count"]
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
                    if "index" in entry:
                        state["index"] = entry["index"]
                    if "total_count" in entry:
                        state["total_count"] = entry["total_count"]
                    if "speed" in entry:
                        state["speed"] = entry["speed"]
                    if "backoff_until" in entry:
                        state["backoff_until"] = entry["backoff_until"]
                    if "backoff_remaining_seconds" in entry:
                        state["backoff_remaining_seconds"] = entry[
                            "backoff_remaining_seconds"
                        ]
                    if "recoverable" in entry:
                        state["recoverable"] = entry["recoverable"]
                elif etype == "candidates":
                    state["latest_stage_key"] = "candidates"
                    state["latest_stage"] = entry.get("message") or "Found candidates"
                    state["total_count"] = entry.get("total_count")
                    state["index"] = 0
                elif etype == "stock_started":
                    state["latest_stage_key"] = "stock_started"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Researching {entry.get('ticker') or 'stock'}"
                    )
                    state["index"] = entry.get("index")
                    state["total_count"] = entry.get("total_count")
                elif etype == "stock_done":
                    state["latest_stage_key"] = "stock_done"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Completed {entry.get('ticker') or 'stock'}"
                    )
                    state["index"] = entry.get("index")
                    state["total_count"] = entry.get("total_count")
                elif etype == "stock_error":
                    state["latest_stage_key"] = "stock_error"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Skipped {entry.get('ticker') or 'stock'}"
                    )
                    state["index"] = entry.get("index")
                    state["total_count"] = entry.get("total_count")
                    state["error"] = entry.get("error") or state.get("error")
                elif etype == "publish_done":
                    state["latest_stage_key"] = "publish_done"
                    state["latest_stage"] = (
                        entry.get("message") or "Published weekly dashboard"
                    )
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


def _progress_idle_seconds(state: dict) -> float | None:
    ts = state.get("last_event_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _progress_path_recent(path: "Path", *, max_idle_seconds: int) -> bool:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return (time.time() - mtime) <= max_idle_seconds


def _progress_state_in_flight(
    state: dict, *, max_idle_seconds: int = ACTIVE_JOB_MAX_IDLE_SECONDS
) -> bool:
    if not state.get("exists") or state.get("terminated"):
        return False
    latest = state.get("latest_action") or {}
    if (
        latest.get("action") == "tool_result"
        and latest.get("tool") == "StructuredOutput"
        and latest.get("is_error")
    ):
        return False
    idle = _progress_idle_seconds(state)
    return idle is None or idle <= max_idle_seconds


def _scan_active_progress_state(path: "Path") -> dict | None:
    if not _progress_path_recent(
        path, max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
    ):
        return None
    state = _scan_progress_state(path)
    return state if _progress_state_in_flight(state) else None


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
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
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
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
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
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
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


def _external_research_analysis_progress_path(item_id: str):
    base = external_store._kind_dir("external_research") / "analysis"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{item_id}__analysis.progress.jsonl"


def _external_research_analysis_kind_records():
    base = external_store._kind_dir("external_research") / "analysis"
    if not base.exists():
        return
    for jsonl_path in base.glob("*__analysis.progress.jsonl"):
        suffix = "__analysis.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        item_id = name[: -len(suffix)]
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        item = external_store.get_item("external_research", item_id) or {}
        yield {
            "kind": state.get("kind") or "external_research",
            "title": (
                state.get("title")
                or item.get("title")
                or item.get("filename")
                or "External research"
            ),
            "subtitle": (
                state.get("subtitle")
                or item.get("source_company")
                or "Document analysis"
            ),
            "stream_url": f"/api/external/research/{item_id}/analysis/stream",
            "log_url": f"/api/jobs/log?path=external_research:{item_id}",
            "primary_route": {
                "name": "external-research",
                "params": {"id": item_id},
            },
            "item_id": item_id,
            "filename": item.get("filename"),
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
        "index": state.get("index"),
        "total_count": state.get("total_count"),
        "tool_count": state.get("tool_count"),
        "backoff_until": state.get("backoff_until"),
        "backoff_remaining_seconds": state.get("backoff_remaining_seconds"),
        "recoverable": state.get("recoverable"),
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


def _serena_research_task_path(key: str):
    company_id, session_id, task_id = key.split("/", 2)
    return serena_analysis.research_task_progress_path(company_id, session_id, task_id)


def _serena_analysis_tool_path(key: str):
    company_id, session_id, tool_name = key.split("/", 2)
    return serena_analysis.analysis_tool_progress_path(company_id, session_id, tool_name)


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
    "external_research": _external_research_analysis_progress_path,
    "memo": _memo_stream_path_for_report,
    # Hormuz appendix reuses the report→run_dir→logs/stream.jsonl resolver.
    "hormuz": _memo_stream_path_for_report,
    "research_summary": lambda key: research_store.quick_summary_progress_path(
        key.split("/", 1)[0], key.split("/", 1)[1]
    ),
    "console_hydrate": _console_hydrate_path,
    "console_ask": _console_ask_path,
    "console_summary": _console_summary_path,
    "serena_research_task": _serena_research_task_path,
    "serena_analysis_tool": _serena_analysis_tool_path,
    "public_snapshot": lambda key: (
        storage.DATA_DIR / "_trader" / f"{key}__snapshot.progress.jsonl"
    ),
    "public_snapshot_bulk": lambda key: _trader_refresh_all_progress_path(),
    "company_regen_all": lambda key: _company_regen_all_progress_path(),
    "weekly_stocks": lambda key: weekly_stocks.progress_path(),
}


def _weekly_stocks_kind_records():
    """Yield the weekly stock refresh job for the active-jobs rail."""
    jsonl_path = weekly_stocks.progress_path()
    if not jsonl_path.exists():
        return
    state = _scan_active_progress_state(jsonl_path)
    if state is None:
        return
    yield {
        "kind": state.get("kind") or "weekly_stocks",
        "title": state.get("title") or "Weekly stock summary",
        "subtitle": state.get("subtitle") or "Hot stocks research",
        "stream_url": "/api/weekly-stocks/refresh/stream",
        "log_url": "/api/jobs/log?path=weekly_stocks:weekly",
        "primary_route": {"name": "weekly-summary"},
        **_common_state_fields(state),
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
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
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
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
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


def _hormuz_appendix_kind_records():
    """Active-jobs rail entries for Hormuz V3 appendix runs.

    One idempotent run folder per date under data/hormuz_appendix/<date>/
    with logs/stream.jsonl (same layout as memo runs)."""
    if not hormuz_store.APPENDIX_ROOT.exists():
        return
    for jsonl_path in hormuz_store.APPENDIX_ROOT.glob("*/logs/stream.jsonl"):
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        init = state.get("job_init") or {}
        report_id = init.get("report_id")
        if not report_id:
            continue
        yield {
            "kind": state.get("kind") or "hormuz",
            "title": state.get("title") or "Hormuz V3 appendix",
            "subtitle": state.get("subtitle") or "Bilingual appendix",
            "stream_url": f"/api/memos/{report_id}/stream",
            "log_url": f"/api/jobs/log?path=hormuz:{report_id}",
            "primary_route": {"name": "hormuz-library"},
            "report_id": report_id,
            "run_dir": init.get("run_dir"),
            **_common_state_fields(state),
        }


def _public_snapshot_kind_records():
    """Yield active-jobs rail entries for in-flight trader-snapshot jobs.
    One progress file per company (idempotent refresh)."""
    base = storage.DATA_DIR / "_trader"
    if not base.exists():
        return
    for jsonl_path in base.glob("*__snapshot.progress.jsonl"):
        suffix = "__snapshot.progress.jsonl"
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        company_id = name[: -len(suffix)]
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        company = storage.get_company(company_id) or {}
        yield {
            "kind": state.get("kind") or "public_snapshot",
            "title": state.get("title") or (
                f"Trader snapshot: {company.get('name') or company_id}"
            ),
            "subtitle": state.get("subtitle") or company.get("ticker") or "",
            "stream_url": (
                f"/api/companies/{company_id}/trader/refresh/stream"
            ),
            "log_url": f"/api/jobs/log?path=public_snapshot:{company_id}",
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
            },
            "company_id": company_id,
            **_common_state_fields(state),
        }


def _public_snapshot_bulk_kind_records():
    """Yield the active-jobs rail entry for the bulk public-stock refresh."""
    jsonl_path = _trader_refresh_all_progress_path()
    if not jsonl_path.exists():
        return
    state = _scan_active_progress_state(jsonl_path)
    if state is None:
        return
    yield {
        "kind": state.get("kind") or "public_snapshot_bulk",
        "title": state.get("title") or "Refresh all stock views",
        "subtitle": state.get("subtitle") or "Public companies",
        "stream_url": "/api/companies/trader/refresh-all/stream",
        "log_url": "/api/jobs/log?path=public_snapshot_bulk:all",
        "primary_route": {"name": "home"},
        **_common_state_fields(state),
    }


def _company_regen_all_kind_records():
    """Yield the active-jobs rail entry for the all-company regeneration."""
    jsonl_path = _company_regen_all_progress_path()
    if not jsonl_path.exists():
        return
    state = _scan_active_progress_state(jsonl_path)
    if state is None:
        return
    yield {
        "kind": state.get("kind") or "company_regen_all",
        "title": state.get("title") or "Regenerate all company views",
        "subtitle": state.get("subtitle") or "Tracked companies",
        "stream_url": "/api/companies/regen-all/stream",
        "log_url": "/api/jobs/log?path=company_regen_all:all",
        "primary_route": {"name": "home"},
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
            state = _scan_active_progress_state(jsonl_path)
            if state is None:
                continue
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
            state = _scan_active_progress_state(jsonl_path)
            if state is None:
                continue
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


def _serena_research_task_kind_records():
    """Yield active-jobs rail entries for Memo Studio research-task jobs."""
    if not serena_analysis.ANALYSIS_ROOT.exists():
        return
    suffix = ".progress.jsonl"
    for jsonl_path in serena_analysis.ANALYSIS_ROOT.glob("*/*/logs/*.progress.jsonl"):
        if not jsonl_path.name.endswith(suffix):
            continue
        task_id = jsonl_path.name[: -len(suffix)]
        session_dir = jsonl_path.parent.parent
        company_dir = session_dir.parent
        session_id = session_dir.name
        company_id = company_dir.name
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        init = state.get("job_init") or {}
        yield {
            "kind": state.get("kind") or "serena_research_task",
            "title": state.get("title") or "Memo Studio research task",
            "subtitle": state.get("subtitle") or (
                (storage.get_company(company_id) or {}).get("name") or company_id
            ),
            "stream_url": (
                f"/api/companies/{company_id}/memo-analysis/sessions/{session_id}"
                f"/research-tasks/{task_id}/stream"
            ),
            "log_url": (
                f"/api/jobs/log?path=serena_research_task:"
                f"{company_id}/{session_id}/{task_id}"
            ),
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
                "query": {"tab": "analysis"},
            },
            "company_id": company_id,
            "session_id": session_id,
            "task_id": task_id,
            "risk_id": init.get("risk_id"),
            **_common_state_fields(state),
        }


def _serena_analysis_tool_kind_records():
    """Yield active-jobs rail entries for Memo Studio analysis-tool jobs."""
    if not serena_analysis.ANALYSIS_ROOT.exists():
        return
    suffix = ".progress.jsonl"
    for jsonl_path in serena_analysis.ANALYSIS_ROOT.glob(
        "*/*/logs/tools/*.progress.jsonl"
    ):
        if not jsonl_path.name.endswith(suffix):
            continue
        tool_name = jsonl_path.name[: -len(suffix)]
        session_dir = jsonl_path.parent.parent.parent
        company_dir = session_dir.parent
        session_id = session_dir.name
        company_id = company_dir.name
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        init = state.get("job_init") or {}
        yield {
            "kind": state.get("kind") or "serena_analysis_tool",
            "title": state.get("title") or "Memo Studio analysis tool",
            "subtitle": state.get("subtitle") or (
                (storage.get_company(company_id) or {}).get("name") or company_id
            ),
            "stream_url": (
                f"/api/companies/{company_id}/memo-analysis/sessions/{session_id}"
                f"/tools/{tool_name}/stream"
            ),
            "log_url": (
                f"/api/jobs/log?path=serena_analysis_tool:"
                f"{company_id}/{session_id}/{tool_name}"
            ),
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
                "query": {"tab": "analysis"},
            },
            "company_id": company_id,
            "session_id": session_id,
            "job_id": f"{company_id}/{session_id}/{tool_name}",
            "tool_name": init.get("tool_name") or tool_name,
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
    try:
        serena_analysis.recover_stale_runs(
            max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
        )
    except Exception:
        logger.exception("failed to recover stale serena jobs")
    out: list[dict] = []
    for source in (
        _summary_kind_records(),
        _search_kind_records(),
        _pdf_translation_kind_records(),
        _external_research_analysis_kind_records(),
        _memo_kind_records(),
        _hormuz_appendix_kind_records(),
        _research_summary_kind_records(),
        _console_kind_records(),
        _serena_research_task_kind_records(),
        _serena_analysis_tool_kind_records(),
        _company_regen_all_kind_records(),
        _public_snapshot_bulk_kind_records(),
        _public_snapshot_kind_records(),
        _weekly_stocks_kind_records(),
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
        archived_favicon = archive.public_url(preview.favicon, item_id)
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


def _news_asset_filename_from_api_url(item_id: str, url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(url).path if "://" in url else url
    marker = f"/api/external/news/{item_id}/assets/"
    if marker not in path:
        return None
    return unquote(path.split(marker, 1)[1])


def _news_asset_exists(item_id: str, filename: str | None) -> bool:
    if not filename:
        return False
    root = external_store.archive_asset_dir("news", item_id).resolve()
    try:
        resolved = external_store.archive_asset_path(
            "news", item_id, filename
        ).resolve()
    except OSError:
        return False
    return root in resolved.parents and resolved.is_file()


def _external_item_response(item: dict) -> dict:
    """Return a UI-safe external item without broken decorative favicon URLs."""
    out = dict(item)
    if out.get("kind") != "news":
        return out
    item_id = str(out.get("id") or "")
    filename = _news_asset_filename_from_api_url(item_id, out.get("favicon"))
    if not _news_asset_exists(item_id, filename):
        out["favicon"] = None
    return out


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
    return [_external_item_response(item) for item in external_store.list_items("news")]


@router.get("/external/news/{item_id}")
def get_news(item_id: str) -> dict:
    item = external_store.get_item("news", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return _external_item_response(item)


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
    progress = job_progress.ProgressLog(
        _external_research_analysis_progress_path(item_id)
    )
    item = external_store.get_item("external_research", item_id) or {}
    progress.emit(
        "job_init",
        kind="external_research",
        title=(
            hint_title
            or item.get("title")
            or item.get("filename")
            or "External research"
        ),
        subtitle=item.get("source_company") or "Document analysis",
        item_id=item_id,
        filename=item.get("filename"),
        source_company=item.get("source_company"),
    )
    try:
        progress.emit("stage", stage="extracting", message="Extracting text")
        external_store.update_item("external_research", item_id, status="extracting")
        text = _extract_text_from_file(file_path)
        if not text:
            message = "Couldn't extract text from this file type."
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error=message,
            )
            progress.emit("error", error=message)
            return
        progress.emit(
            "stage",
            stage="analyzing",
            message="Analyzing extracted text",
            raw_text_chars=len(text),
        )
        external_store.update_item(
            "external_research",
            item_id,
            status="analyzing",
            raw_text_chars=len(text),
        )
        analysis = text_analysis.analyze(
            text, hint_title=hint_title, progress=progress
        )
        if "error" in analysis:
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error=analysis["error"],
            )
            progress.emit("error", error=analysis["error"])
            return
        progress.emit("stage", stage="saving", message="Saving analysis")
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
        progress.emit(
            "done",
            item_id=item_id,
            title=(analysis.get("title") or hint_title or "Untitled"),
            summary=analysis.get("summary"),
            key_point_count=len(analysis.get("key_points") or []),
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit("error", error=f"{type(exc).__name__}: {exc}")
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


@router.get("/external/research/{item_id}/analysis/stream")
async def stream_external_research_analysis_progress(item_id: str):
    """SSE tail of the upload-analysis progress JSONL for this item."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

    if external_store.get_item("external_research", item_id) is None:
        raise HTTPException(status_code=404, detail="Research item not found")

    progress_path = _external_research_analysis_progress_path(item_id)

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
    return [
        _external_item_response(item)
        for item in external_store.list_news_and_research()
    ]


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


# ---- Hormuz date-organized source library + V3 appendix ----

def _latest_hormuz_report_for_date(date: str) -> dict | None:
    """Newest hormuz_appendix report record for a target date, if any."""
    best = None
    for r in storage.list_reports():
        if r.get("kind") != "hormuz_appendix":
            continue
        if str(r.get("target_date")) != date:
            continue
        if best is None or str(r.get("created_at", "")) > str(
            best.get("created_at", "")
        ):
            best = r
    return best


def _hormuz_library_entry(date: str) -> dict:
    src = hormuz_store.source_files(date)
    status = hormuz_store.appendix_status(date)
    report = _latest_hormuz_report_for_date(date)
    appendix: dict = {
        "complete": status["complete"],
        "files": status["files"],
    }
    if report:
        rid = report["id"]
        appendix.update(
            report_id=rid,
            status=report.get("status"),
            stage=report.get("stage"),
            progress=report.get("progress"),
            stream_url=f"/api/memos/{rid}/stream",
            log_url=f"/api/jobs/log?path=hormuz:{rid}",
        )
    return {
        "date": date,
        "sources": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "url": f"/api/external/hormuz/sources/{date}/{p.name}",
            }
            for p in src
        ],
        "previous_date": hormuz_store.previous_date(date),
        "appendix": appendix,
    }


@router.get("/external/hormuz/library")
def get_hormuz_library() -> list[dict]:
    """Date-organized Hormuz source library, newest date first, each with
    its source files and the latest appendix status for that date.

    Folds any files attached to the legacy Hormuz Research items into the
    date library first (idempotent, best-effort)."""
    try:
        hormuz_store.import_legacy_hormuz_files()
    except Exception:  # noqa: BLE001 — never let backfill break listing
        logger.exception("legacy Hormuz fold-in failed")
    return [
        _hormuz_library_entry(d) for d in hormuz_store.list_source_dates()
    ]


@router.post("/external/hormuz/sources", status_code=201)
async def post_hormuz_sources(
    files: list[UploadFile] = File(...),
) -> dict:
    """Upload one or more daily source reports (max 10). The date is
    parsed from each filename (e.g. 中东局势每日研判2026-05-13.pdf →
    2026-05-13)."""
    if len(files) > 10:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(files)}). Upload at most 10 at a time.",
        )
    saved: list[dict] = []
    errors: list[dict] = []
    for f in files:
        if not f or not f.filename:
            continue
        data = await f.read()
        if not data:
            errors.append({"filename": f.filename, "error": "Empty file"})
            continue
        try:
            saved.append(hormuz_store.save_source(f.filename, data))
        except ValueError as exc:
            errors.append({"filename": f.filename, "error": str(exc)})
    if not saved and errors:
        raise HTTPException(status_code=400, detail=errors)
    return {"saved": saved, "errors": errors}


@router.get("/external/hormuz/sources/{date}/{filename}")
def get_hormuz_source_file(date: str, filename: str) -> FileResponse:
    if not hormuz_store.is_valid_date(date):
        raise HTTPException(status_code=400, detail="Bad date")
    p = hormuz_store.resolve_source_file(date, filename)
    if p is None:
        raise HTTPException(status_code=404, detail="Source file not found")
    media = "application/pdf" if p.suffix.lower() == ".pdf" else None
    return FileResponse(
        path=str(p),
        media_type=media,
        content_disposition_type="inline",
    )


@router.post("/external/hormuz/appendix/{date}/generate", status_code=201)
def post_hormuz_appendix(date: str) -> dict:
    """Kick off (or re-run) the bilingual V3 appendix for a date."""
    try:
        return hormuz_prep.bootstrap_appendix_run(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/external/hormuz/appendix/{date}")
def get_hormuz_appendix(date: str) -> dict:
    if not hormuz_store.is_valid_date(date):
        raise HTTPException(status_code=400, detail="Bad date")
    return _hormuz_library_entry(date)


_HORMUZ_SLOTS = {
    "cn_md": ("text/markdown; charset=utf-8", "inline"),
    "cn_pdf": ("application/pdf", "inline"),
    "en_md": ("text/markdown; charset=utf-8", "inline"),
    "en_pdf": ("application/pdf", "inline"),
}


@router.get("/external/hormuz/appendix/{date}/file")
def get_hormuz_appendix_file(date: str, slot: str = "cn_pdf") -> FileResponse:
    if not hormuz_store.is_valid_date(date):
        raise HTTPException(status_code=400, detail="Bad date")
    if slot not in _HORMUZ_SLOTS:
        raise HTTPException(
            status_code=400,
            detail="slot must be one of cn_md, cn_pdf, en_md, en_pdf",
        )
    paths = hormuz_store.appendix_output_paths(date)
    p = paths[slot]
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No {slot} appendix file for {date} (run not complete?)",
        )
    media, disp = _HORMUZ_SLOTS[slot]
    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type=media,
        content_disposition_type=disp,
    )


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
        "company_type": c.get("company_type") or storage.infer_company_type(c),
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
        "trader_snapshot": c.get("trader_snapshot"),
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
        "analysis_session_id": r.get("analysis_session_id"),
        "analysis_session_approved": bool(r.get("analysis_session_approved")),
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
        # Only advertise a preview URL for a language whose PDF was
        # actually rendered (Word automation can be unavailable, or an
        # older run may predate PDF rendering).
        memo_files = r.get("memo_files") or []
        have_pdf = {
            f.get("language")
            for f in memo_files
            if f.get("pdf_path")
        }
        preview_urls = {
            lang: f"/api/reports/{rid}/preview?language={lang}"
            for lang in ("en", "zh")
            if lang in have_pdf
        }
        if preview_urls:
            base["preview_urls"] = preview_urls
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
    output_language: str = "en"  # "en" or "zh" — validated server-side


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
            output_language=body.output_language,
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
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(exc)},
        ) from exc
    return {
        **_serialize_console_meta(meta),
        "hydrate_stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}"
            "/hydrate/stream"
        ),
    }


# ---- Hormuz Console ----
# Scoped to the Strait-of-Hormuz daily reports rather than a company.
# Only the *create* endpoint is Hormuz-specific (it stages the last two
# days of source material + the Hormuz persona). Everything else —
# list/get/turns/ask/stream/archive/delete — reuses the generic
# /companies/{id}/console/* routes with the fixed id "hormuz", since
# those handlers are company-agnostic (they never call get_company).


@router.get("/external/hormuz/console/context")
def get_hormuz_console_context() -> dict:
    """What a new Hormuz console session would load into context."""
    return hormuz_console.context_preview()


@router.post("/external/hormuz/console/sessions", status_code=201)
def create_hormuz_console_session(body: _ConsoleCreateBody | None = None) -> dict:
    body = body or _ConsoleCreateBody()
    try:
        meta = hormuz_console.create_session(output_language=body.output_language)
    except console_store.SessionLimitReached as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "session_limit_reached",
                "limit": console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY,
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(exc)},
        ) from exc
    return {
        **_serialize_console_meta(meta),
        # Reuse the generic, company-agnostic hydrate stream route.
        "hydrate_stream_url": (
            f"/api/companies/{hormuz_console.HORMUZ_ID}/console/sessions"
            f"/{meta['id']}/hydrate/stream"
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


# ---- Public-company trader snapshot --------------------------------------
#
# POST /trader/refresh kicks off a Claude run that populates
# ``company.trader_snapshot``. Idempotent — concurrent refreshes for the
# same company share one job. See docs/public-company-trader-view.md §4.


def _trader_snapshot_progress_path(company_id: str) -> "Path":
    from pathlib import Path

    base: Path = storage.DATA_DIR / "_trader"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{company_id}__snapshot.progress.jsonl"


def _trader_refresh_all_progress_path() -> "Path":
    from pathlib import Path

    base: Path = storage.DATA_DIR / "_trader"
    base.mkdir(parents=True, exist_ok=True)
    return base / "__all_public_refresh.progress.jsonl"


def _company_regen_all_progress_path() -> "Path":
    from pathlib import Path

    base: Path = storage.DATA_DIR / "_regen"
    base.mkdir(parents=True, exist_ok=True)
    return base / "__all_companies_regen.progress.jsonl"


def _company_regen_all_state_path() -> "Path":
    from pathlib import Path

    base: Path = storage.DATA_DIR / "_regen"
    base.mkdir(parents=True, exist_ok=True)
    return base / "__all_companies_regen.state.json"


def _parse_trader_languages(raw: str | None) -> list[str]:
    """Normalize the `languages` query parameter into a list of
    canonical language codes. Anything we don't recognize is dropped.
    Empty / missing input falls back to the full bilingual contract.
    """
    if not raw:
        return ["en", "zh"]
    parsed = [
        part.strip().lower()
        for part in raw.split(",")
        if part.strip()
    ]
    valid = [code for code in parsed if code in {"en", "zh"}]
    return valid or ["en", "zh"]


def _run_trader_snapshot_job(
    company_id: str,
    *,
    languages_requested: list[str] | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
) -> None:
    """Background worker for a single trader-snapshot refresh. Writes
    progress events to JSONL and persists the snapshot on success.

    ``languages_requested`` / ``include_translations`` / ``translation_mode``
    are recorded on ``job_init`` for client-side observability. Today
    the schema + system prompt always produces bilingual output, so
    these inputs don't affect generation; they're a placeholder for a
    future single-language mode (Phase 2 of the bilingual rollout).
    """
    progress = job_progress.ProgressLog(_trader_snapshot_progress_path(company_id))
    company = storage.get_company(company_id) or {}
    previous_snapshot = copy.deepcopy(
        company.get("trader_snapshot")
        if isinstance(company.get("trader_snapshot"), dict)
        else {}
    )
    company_name = company.get("name") or company_id
    ticker = company.get("ticker") or ""
    progress.emit(
        "job_init",
        kind="public_snapshot",
        title=f"Trader snapshot: {company_name}",
        subtitle=ticker or "",
        company_id=company_id,
        languages_requested=languages_requested or ["en", "zh"],
        include_translations=include_translations,
        translation_mode=translation_mode,
    )
    progress.emit(
        "stage", stage="starting",
        message=f"Refreshing trader snapshot for {company_name}",
    )

    started_at = datetime.now(timezone.utc)
    try:
        snapshot, err = companies_ai_public.generate_snapshot(
            company=company, progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("trader snapshot crashed for %s", company_id)
        progress.emit(
            "error",
            error=f"{type(exc).__name__}: {exc}",
        )
        return

    if snapshot is None:
        progress.emit("error", error=err or "Trader snapshot failed")
        return

    duration_ms = int(
        (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
    )
    snapshot["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["generation_duration_ms"] = duration_ms

    # Belt-and-suspenders bilingual fill. The system prompt asks the
    # LLM to populate every `_en` / `_zh` pair, but "best effort" isn't
    # the contract — every prose field MUST be readable in both
    # languages or the UI's language toggle reads as broken. This pass
    # walks the snapshot, finds any pair where exactly one side is
    # populated, and translates to fill the other side via a single
    # batched claude call. Errors fall back to the original snapshot
    # (a logged warning, not a fatal) so the worker never blocks on a
    # translation hiccup.
    progress.emit(
        "stage", stage="bilingual_fill",
        message="Filling missing translations",
    )
    try:
        trader_bilingual_fill.ensure_bilingual_completeness(snapshot)
    except Exception:  # noqa: BLE001
        logger.exception(
            "trader_bilingual_fill: completeness pass crashed; "
            "persisting snapshot as-is",
        )

    # The schema + prompt + bilingual fill above guarantee both
    # languages are present on every prose field, so the client can
    # render either without falling back to nulls.
    snapshot["available_languages"] = ["en", "zh"]
    # Stamp the trader-snapshot schema version on every write. The
    # startup migration uses this to detect snapshots produced by an
    # older code path (e.g. v1 heat_card) and strip the
    # now-incompatible fields. See docs/heat-card-v2.md §6.
    snapshot["schema_version"] = (
        companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
    )

    storage.update_company_snapshot(company_id, snapshot)
    try:
        stats_record = trader_stats.record_trader_refresh(
            company_id=company_id,
            company=company,
            previous_snapshot=previous_snapshot,
            new_snapshot=snapshot,
            progress_path=_trader_snapshot_progress_path(company_id),
            duration_ms=duration_ms,
        )
        progress.emit(
            "stage",
            stage="stats_recorded",
            message="Recorded refresh stats",
            total_tokens=stats_record.get("token_usage", {}).get("total_tokens"),
            change_pct=stats_record.get("change_summary", {}).get("change_pct"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("trader stats recording failed for %s", company_id)
    progress.emit(
        "done",
        refreshed_at=snapshot["refreshed_at"],
        duration_ms=duration_ms,
        # `available_languages` reflects what landed on the saved
        # snapshot. `generated_languages` is the provider-neutral name
        # the agent-orchestrator doc (CODEX_REQUEST_ARCHITECTURE.md)
        # uses for the same idea — emit both so either adapter's
        # downstream consumers can read whichever they were coded
        # against.
        available_languages=snapshot["available_languages"],
        generated_languages=snapshot["available_languages"],
        schema_version=snapshot["schema_version"],
    )


def _public_companies_for_trader_refresh() -> list[dict]:
    """Return tracked public companies in a stable ticker/name order."""
    companies: list[dict] = []
    for company in storage.list_companies():
        if not isinstance(company, dict):
            continue
        company_type = company.get("company_type") or storage.infer_company_type(
            company
        )
        if company_type == "public":
            companies.append(company)
    companies.sort(
        key=lambda c: str(
            c.get("ticker") or c.get("name") or c.get("id") or ""
        ).lower()
    )
    return companies


def _summarize_trader_refresh_queue(
    companies: list[dict], *, force: bool = False
) -> dict:
    queued = 0
    already_running = 0
    skipped = 0
    company_ids: list[str] = []
    for company in companies:
        company_id = (company.get("id") or "").strip()
        ticker = (company.get("ticker") or "").strip()
        if not company_id or not ticker:
            skipped += 1
            continue
        state = _scan_progress_state(_trader_snapshot_progress_path(company_id))
        if _progress_state_in_flight(state) and not force:
            already_running += 1
            continue
        queued += 1
        company_ids.append(company_id)
    return {
        "total_count": len(companies),
        "queued_count": queued,
        "already_running_count": already_running,
        "skipped_count": skipped,
        "company_ids": company_ids,
    }


def _supersede_progress_file(path: "Path", *, reason: str) -> None:
    if not path.exists():
        return
    try:
        job_progress.ProgressLog(path, truncate=False).emit(
            "error",
            error=reason,
            terminal=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to mark stale progress terminated")
    try:
        path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        logger.exception("failed to unlink stale progress")


class _ProgressContext:
    """Attach per-company metadata to nested progress events."""

    def __init__(self, progress: job_progress.ProgressLog, **context):
        self.progress = progress
        self.context = context
        self.backoff_reason: str | None = None

    def emit(self, type_: str, **fields) -> None:
        if type_ == "claude_action":
            reason = _regen_backoff_reason(
                fields.get("text") or fields.get("preview") or fields.get("error")
            )
            if reason:
                self.backoff_reason = reason
        self.progress.emit(type_, **{**self.context, **fields})


def _tracked_companies_for_regen() -> list[dict]:
    """Return every tracked company in a stable public/private/name order."""
    companies = [
        company
        for company in storage.list_companies()
        if isinstance(company, dict)
    ]
    companies.sort(
        key=lambda c: (
            0
            if (c.get("company_type") or storage.infer_company_type(c)) == "public"
            else 1,
            str(c.get("ticker") or c.get("name") or c.get("id") or "").lower(),
        )
    )
    return companies


def _summarize_company_regen_queue(companies: list[dict]) -> dict:
    checkpoint = _load_regen_checkpoint()
    if _regen_checkpoint_complete(checkpoint, companies):
        checkpoint = None
    return _summarize_regen_checkpoint(companies, checkpoint)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_regen_checkpoint() -> dict | None:
    import json as _json

    path = _company_regen_all_state_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:  # noqa: BLE001
        logger.exception("regen-all: failed to read checkpoint")
        return None
    return data if isinstance(data, dict) else None


def _write_regen_checkpoint(state: dict) -> None:
    import json as _json

    path = _company_regen_all_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _iso_now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        _json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def _regen_item_for_company(company: dict, existing: dict | None = None) -> dict:
    company_id = (company.get("id") or "").strip()
    company_type = company.get("company_type") or storage.infer_company_type(company)
    item = dict(existing or {})
    item.update({
        "company_id": company_id or None,
        "company_name": company.get("name") or company_id or "Unknown company",
        "ticker": (company.get("ticker") or "").strip(),
        "company_type": company_type,
    })
    item.setdefault("summary_status", "pending")
    item.setdefault(
        "trader_status",
        "pending" if company_type == "public" else "not_applicable",
    )
    if company_type != "public" and item.get("trader_status") != "done":
        item["trader_status"] = "not_applicable"
    if company_type == "public" and item.get("trader_status") == "not_applicable":
        item["trader_status"] = "pending"
    return item


def _new_regen_checkpoint(companies: list[dict], *, force: bool = False) -> dict:
    started = _iso_now()
    usage_window_seconds = _regen_usage_window_seconds()
    usage_window_pause_fraction = _regen_usage_window_pause_fraction()
    order: list[str] = []
    items: dict[str, dict] = {}
    for company in companies:
        company_id = (company.get("id") or "").strip()
        if not company_id:
            continue
        order.append(company_id)
        items[company_id] = _regen_item_for_company(company)
    return {
        "schema_version": 1,
        "status": "running",
        "started_at": started,
        "updated_at": started,
        "completed_at": None,
        "force": force,
        "languages_requested": ["en", "zh"],
        "include_translations": True,
        "translation_mode": "all",
        "usage_window_started_at": started,
        "usage_window_seconds": usage_window_seconds,
        "usage_window_pause_fraction": usage_window_pause_fraction,
        "order": order,
        "items": items,
    }


_REGEN_SUMMARY_TERMINAL_STATUSES = {
    "done",
    "error",
    "skipped_missing_id",
    "skipped_missing_name",
}
_REGEN_TRADER_TERMINAL_STATUSES = {
    "done",
    "not_applicable",
    "skipped_missing_ticker",
    "error",
}


def _regen_item_done(item: dict) -> bool:
    summary_done = _regen_summary_done(item)
    trader_status = item.get("trader_status")
    trader_done = trader_status in (
        "done",
        "not_applicable",
        "skipped_missing_ticker",
    )
    return summary_done and trader_done


def _regen_item_terminal(item: dict) -> bool:
    summary_status = item.get("summary_status")
    summary_terminal = summary_status in _REGEN_SUMMARY_TERMINAL_STATUSES
    if summary_status == "done" and not _regen_summary_done(item):
        summary_terminal = False
    return (
        summary_terminal
        and item.get("trader_status") in _REGEN_TRADER_TERMINAL_STATUSES
    )


def _regen_summary_done(item: dict) -> bool:
    if item.get("summary_status") != "done":
        return False
    return not (
        item.get("summary_source") == "fallback"
        and _regen_retryable_error_text(item.get("summary_reason"))
    )


def _summarize_regen_checkpoint(
    companies: list[dict], state: dict | None = None
) -> dict:
    items = state.get("items") if isinstance(state, dict) else {}
    if not isinstance(items, dict):
        items = {}
    company_ids: list[str] = []
    public_trader_count = 0
    private_count = 0
    pending_count = 0
    completed_count = 0
    failed_count = 0
    summary_done_count = 0
    summary_failed_count = 0
    trader_done_count = 0
    trader_skipped_count = 0
    trader_failed_count = 0
    detail_items: list[dict] = []

    for company in companies:
        company_id = (company.get("id") or "").strip()
        if company_id:
            company_ids.append(company_id)
        company_type = company.get("company_type") or storage.infer_company_type(
            company
        )
        requires_trader = company_type == "public" and bool(
            (company.get("ticker") or "").strip()
        )
        if requires_trader:
            public_trader_count += 1
        else:
            private_count += 1

        item = _regen_item_for_company(company, items.get(company_id))
        summary_status = item.get("summary_status") or "pending"
        trader_status = item.get("trader_status") or (
            "pending" if requires_trader else "not_applicable"
        )
        if _regen_summary_done(item):
            summary_done_count += 1
        if trader_status == "done":
            trader_done_count += 1
        if summary_status in {
            "error",
            "skipped_missing_id",
            "skipped_missing_name",
        }:
            summary_failed_count += 1
        if trader_status == "skipped_missing_ticker":
            trader_skipped_count += 1
        if trader_status == "error":
            trader_failed_count += 1
        if summary_status in {
            "error",
            "skipped_missing_id",
            "skipped_missing_name",
        } or trader_status == "error":
            failed_count += 1
        if _regen_item_done(item):
            completed_count += 1
        if not _regen_item_terminal(item):
            pending_count += 1
        detail_items.append(item)

    return {
        "total_count": len(companies),
        "queued_count": pending_count,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "summary_done_count": summary_done_count,
        "summary_refreshed_count": summary_done_count,
        "summary_failed_count": summary_failed_count,
        "trader_done_count": trader_done_count,
        "trader_refreshed_count": trader_done_count,
        "trader_skipped_count": trader_skipped_count,
        "trader_failed_count": trader_failed_count,
        "public_trader_count": public_trader_count,
        "private_count": private_count,
        "company_ids": company_ids,
        "checkpoint_status": state.get("status") if isinstance(state, dict) else None,
        "checkpoint_updated_at": (
            state.get("updated_at") if isinstance(state, dict) else None
        ),
        "backoff_until": state.get("backoff_until") if isinstance(state, dict) else None,
        "backoff_reason": state.get("backoff_reason") if isinstance(state, dict) else None,
        "backoff_phase": state.get("backoff_phase") if isinstance(state, dict) else None,
        "backoff_company_id": (
            state.get("backoff_company_id") if isinstance(state, dict) else None
        ),
        "backoff_kind": state.get("backoff_kind") if isinstance(state, dict) else None,
        "usage_window_started_at": (
            state.get("usage_window_started_at") if isinstance(state, dict) else None
        ),
        "usage_window_seconds": (
            state.get("usage_window_seconds") if isinstance(state, dict) else None
        ),
        "usage_window_pause_fraction": (
            state.get("usage_window_pause_fraction")
            if isinstance(state, dict)
            else None
        ),
        "items": detail_items,
    }


def _regen_checkpoint_complete(
    state: dict | None, companies: list[dict]
) -> bool:
    if not state:
        return False
    if state.get("schema_version") != 1:
        return False
    summary = _summarize_regen_checkpoint(companies, state)
    return summary.get("pending_count") == 0 and summary.get("failed_count") == 0


def _regen_usage_window_seconds() -> float:
    raw = os.environ.get("BSH_REGEN_USAGE_WINDOW_SECONDS", str(5 * 60 * 60))
    try:
        return max(1.0, float(raw))
    except ValueError:
        return float(5 * 60 * 60)


def _regen_usage_window_pause_fraction() -> float:
    raw = os.environ.get("BSH_REGEN_USAGE_WINDOW_PAUSE_FRACTION", "0.8")
    try:
        value = float(raw)
    except ValueError:
        return 0.8
    return min(0.99, max(0.01, value))


def _ensure_regen_usage_window(state: dict) -> None:
    state["usage_window_seconds"] = _regen_usage_window_seconds()
    state["usage_window_pause_fraction"] = _regen_usage_window_pause_fraction()
    if not state.get("usage_window_started_at"):
        state["usage_window_started_at"] = state.get("started_at") or _iso_now()


def _regen_usage_window_bounds(state: dict) -> tuple[datetime, datetime, datetime]:
    _ensure_regen_usage_window(state)
    started = _parse_iso_datetime(state.get("usage_window_started_at"))
    if started is None:
        started = datetime.now(timezone.utc)
        state["usage_window_started_at"] = started.isoformat()
    window_seconds = float(state.get("usage_window_seconds") or 5 * 60 * 60)
    pause_fraction = float(state.get("usage_window_pause_fraction") or 0.8)
    threshold = started + timedelta(seconds=window_seconds * pause_fraction)
    reset_at = started + timedelta(seconds=window_seconds)
    return started, threshold, reset_at


def _usage_window_label(state: dict) -> str:
    seconds = float(state.get("usage_window_seconds") or 5 * 60 * 60)
    fraction = float(state.get("usage_window_pause_fraction") or 0.8)
    hours = seconds / 3600
    hour_label = f"{hours:g} hour" if hours == 1 else f"{hours:g} hours"
    return f"{int(round(fraction * 100))}% of {hour_label}"


def _reset_recoverable_regen_statuses(item: dict, *, keep_backoff: bool) -> dict:
    """Turn statuses that could only have existed mid-worker back to pending."""
    for status_key, error_key in (
        ("summary_status", "summary_error"),
        ("trader_status", "trader_error"),
    ):
        status = item.get(status_key)
        if status == "running" or (status == "blocked_backoff" and not keep_backoff):
            item[status_key] = "pending"
            item.pop(error_key, None)
        elif status == "error" and _regen_retryable_error_text(item.get(error_key)):
            item[status_key] = "pending"
            item.pop(error_key, None)

    if (
        item.get("summary_status") == "done"
        and item.get("summary_source") == "fallback"
        and _regen_retryable_error_text(item.get("summary_reason"))
    ):
        item["summary_status"] = "pending"
        for key in ("summary_source", "summary_reason", "summary_refreshed_at"):
            item.pop(key, None)
    return item


def _prepare_regen_checkpoint(
    companies: list[dict], *, force: bool = False
) -> tuple[dict, bool]:
    """Return ``(checkpoint, resumed)`` for the next regen-all run."""
    existing = None if force else _load_regen_checkpoint()
    _repair_provider_limit_backoff(existing)
    if (
        existing is None
        or existing.get("schema_version") != 1
        or _regen_checkpoint_complete(existing, companies)
    ):
        state = _new_regen_checkpoint(companies, force=force)
        _write_regen_checkpoint(state)
        return state, False

    old_items = existing.get("items") if isinstance(existing.get("items"), dict) else {}
    keep_backoff = bool(
        existing.get("status") in {"backing_off", "paused_backoff"}
        and existing.get("backoff_until")
    )
    order: list[str] = []
    items: dict[str, dict] = {}
    for company in companies:
        company_id = (company.get("id") or "").strip()
        if not company_id:
            continue
        order.append(company_id)
        items[company_id] = _reset_recoverable_regen_statuses(
            _regen_item_for_company(company, old_items.get(company_id)),
            keep_backoff=keep_backoff,
        )
    existing.update({
        "status": "backing_off" if keep_backoff else "running",
        "completed_at": None,
        "force": False,
        "order": order,
        "items": items,
    })
    _ensure_regen_usage_window(existing)
    _write_regen_checkpoint(existing)
    return existing, True


def _checkpoint_item(state: dict, item: dict) -> None:
    company_id = item.get("company_id")
    if not company_id:
        return
    items = state.setdefault("items", {})
    items[company_id] = item
    _write_regen_checkpoint(state)


def _regen_backoff_reason(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    markers = (
        "usage limit",
        "rate limit",
        "quota",
        "too many requests",
        "429",
        "limit reached",
        "daily limit",
        "weekly limit",
        "try again later",
        "overloaded",
        "session limit",
        "resets ",
    )
    return text if any(marker in lowered for marker in markers) else None


def _regen_retryable_error_text(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    lowered = text.lower()
    return bool(
        _regen_backoff_reason(text)
        or "claude exited 1" in lowered
        or "all snapshot sections failed" in lowered
    )


def _parse_regen_reset_delay_seconds(
    text: str, *, now: datetime | None = None
) -> int | None:
    """Parse provider messages like ``Resets in 2 hr 44 min``."""
    if not text:
        return None
    lowered = text.lower()
    retry_after = re.search(r"retry[-\s]?after[:=\s]+(\d+)", lowered)
    if retry_after:
        return int(retry_after.group(1))

    window = lowered
    marker = re.search(
        r"(?:resets?|reset|retry|try again|available again)\s+in\s+",
        lowered,
    )
    if marker:
        window = lowered[marker.end(): marker.end() + 80]

    total = 0.0
    for raw, unit in re.findall(
        r"(\d+(?:\.\d+)?)\s*"
        r"(days?|d|hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)",
        window,
    ):
        amount = float(raw)
        unit = unit.lower()
        if unit.startswith("d"):
            total += amount * 86400
        elif unit.startswith("h"):
            total += amount * 3600
        elif unit.startswith("m"):
            total += amount * 60
        elif unit.startswith("s"):
            total += amount
    if total >= 0 and re.search(r"\d", window) and total:
        return int(total)
    if re.search(r"\b0\s*(?:min|m|sec|s|hr|h)", window):
        return 0

    reset_at = re.search(
        r"(?:resets?|reset)\s+(?:at\s+)?"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)"
        r"(?:\s*\(([^)]+)\))?",
        text,
        re.IGNORECASE,
    )
    if reset_at:
        hour = int(reset_at.group(1))
        minute = int(reset_at.group(2) or "0")
        meridiem = reset_at.group(3).lower()
        tz_name = reset_at.group(4) or "UTC"
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        try:
            from zoneinfo import ZoneInfo

            zone = ZoneInfo(tz_name)
        except Exception:
            zone = timezone.utc
        now_utc = now or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        now_local = now_utc.astimezone(zone)
        candidate = now_local.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate <= now_local:
            # Claude can report an exact wall-clock reset just after the
            # boundary. Treat that as a short retry, not "same time tomorrow".
            if (now_local - candidate).total_seconds() <= 30 * 60:
                return 5 * 60
            candidate += timedelta(days=1)
        return max(
            0,
            int(
                (candidate.astimezone(timezone.utc) - now_utc).total_seconds()
            ),
        )
    return None


def _format_regen_backoff(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "now"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if not parts and secs:
        parts.append(f"{secs} sec")
    return " ".join(parts[:2]) if parts else "now"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _seconds_until_iso(value: str | None) -> int:
    dt = _parse_iso_datetime(value)
    if dt is None:
        return 0
    return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))


def _repair_provider_limit_backoff(state: dict | None) -> bool:
    """Correct persisted provider-limit backoffs computed by older parsers."""
    if not isinstance(state, dict):
        return False
    if (
        state.get("backoff_kind") != "provider_limit"
        or not state.get("backoff_until")
        or not state.get("backoff_reason")
    ):
        return False
    started = (
        _parse_iso_datetime(state.get("backoff_started_at"))
        or _parse_iso_datetime(state.get("usage_window_started_at"))
        or datetime.now(timezone.utc)
    )
    delay = _parse_regen_reset_delay_seconds(
        str(state.get("backoff_reason") or ""),
        now=started,
    )
    if delay is None:
        return False
    repaired_until = started + timedelta(seconds=delay)
    current_until = _parse_iso_datetime(state.get("backoff_until"))
    if (
        current_until is not None
        and repaired_until >= current_until - timedelta(seconds=60)
    ):
        return False

    state["backoff_until"] = repaired_until.isoformat()
    state["backoff_seconds"] = delay
    state["backoff_remaining_seconds"] = _seconds_until_iso(
        state["backoff_until"]
    )
    _write_regen_checkpoint(state)
    return True


def _regen_default_backoff_seconds() -> int:
    raw = os.environ.get("BSH_REGEN_DEFAULT_BACKOFF_SECONDS", "900")
    try:
        return max(0, int(raw))
    except ValueError:
        return 900


def _regen_sleep_seconds(seconds: int) -> int:
    raw = os.environ.get("BSH_REGEN_BACKOFF_MAX_SLEEP_SECONDS")
    if raw is None:
        return max(0, int(seconds))
    try:
        cap = max(0, int(float(raw)))
    except ValueError:
        return max(0, int(seconds))
    return min(max(0, int(seconds)), cap)


def _clear_regen_backoff(
    state: dict,
    item: dict | None = None,
    phase: str | None = None,
) -> None:
    if item is not None and phase in {"summary", "trader"}:
        status_key = "summary_status" if phase == "summary" else "trader_status"
        error_key = "summary_error" if phase == "summary" else "trader_error"
        if item.get(status_key) == "blocked_backoff":
            item[status_key] = "pending"
        item.pop(error_key, None)
        _checkpoint_item(state, item)

    state["usage_window_started_at"] = _iso_now()
    _ensure_regen_usage_window(state)
    for key in (
        "backoff_kind",
        "backoff_reason",
        "backoff_phase",
        "backoff_company_id",
        "backoff_until",
        "backoff_seconds",
        "backoff_started_at",
        "backoff_remaining_seconds",
    ):
        state.pop(key, None)
    state["status"] = "running"
    _write_regen_checkpoint(state)


def _sleep_regen_backoff(
    state: dict,
    progress: job_progress.ProgressLog,
    *,
    item: dict | None = None,
    phase: str | None = None,
    context: dict | None = None,
    resumed: bool = False,
) -> None:
    sleep_for = _regen_sleep_seconds(_seconds_until_iso(state.get("backoff_until")))
    backoff_kind = state.get("backoff_kind") or "provider_limit"
    if backoff_kind == "proactive_usage_window":
        prefix = (
            "Resuming usage-window guard"
            if resumed
            else f"Usage window guard reached {_usage_window_label(state)}"
        )
        heartbeat_prefix = "Usage window reset pending"
    else:
        prefix = "Resuming usage-limit backoff" if resumed else "Usage limit hit"
        heartbeat_prefix = "Usage limit reset pending"
    fields = dict(context or {})
    fields.update({
        "recoverable": True,
        "backoff": True,
        "backoff_kind": backoff_kind,
        "phase": phase or state.get("backoff_phase"),
        "backoff_until": state.get("backoff_until"),
        "backoff_seconds": state.get("backoff_seconds"),
        "backoff_remaining_seconds": _seconds_until_iso(state.get("backoff_until")),
    })
    progress.emit(
        "stage",
        stage="backing_off",
        message=(
            f"{prefix}; retrying at next window in "
            f"{_format_regen_backoff(fields['backoff_remaining_seconds'])}"
        ),
        **fields,
    )
    deadline = time.monotonic() + sleep_for
    next_heartbeat = time.monotonic() + 300
    while True:
        remaining_sleep = max(0.0, deadline - time.monotonic())
        if remaining_sleep <= 0:
            break
        time.sleep(min(60.0, remaining_sleep))
        now = time.monotonic()
        if now >= next_heartbeat:
            remaining = _seconds_until_iso(state.get("backoff_until"))
            state["backoff_remaining_seconds"] = remaining
            _write_regen_checkpoint(state)
            progress.emit(
                "stage",
                stage="backing_off",
                message=(
                    f"{heartbeat_prefix}; retrying in "
                    f"{_format_regen_backoff(remaining)}"
                ),
                **{
                    **fields,
                    "backoff_remaining_seconds": remaining,
                },
            )
            next_heartbeat = now + 300

    _clear_regen_backoff(state, item=item, phase=phase)


def _backoff_regen_until_reset(
    state: dict,
    progress: job_progress.ProgressLog,
    *,
    reason: str,
    item: dict | None = None,
    phase: str,
    context: dict | None = None,
) -> None:
    delay = _parse_regen_reset_delay_seconds(reason)
    if delay is None:
        delay = _regen_default_backoff_seconds()
    until = datetime.now(timezone.utc) + timedelta(seconds=delay)
    if item is not None:
        status_key = "summary_status" if phase == "summary" else "trader_status"
        error_key = "summary_error" if phase == "summary" else "trader_error"
        item[status_key] = "blocked_backoff"
        item[error_key] = reason
        _checkpoint_item(state, item)
    state.update({
        "status": "backing_off",
        "backoff_kind": "provider_limit",
        "backoff_reason": reason,
        "backoff_phase": phase,
        "backoff_company_id": item.get("company_id") if item else None,
        "backoff_until": until.isoformat(),
        "backoff_seconds": delay,
        "backoff_started_at": _iso_now(),
        "completed_at": None,
    })
    _write_regen_checkpoint(state)
    _sleep_regen_backoff(
        state,
        progress,
        item=item,
        phase=phase,
        context=context,
    )


def _progress_log_backoff_reason(path: "Path") -> str | None:
    import json as _json

    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines[-200:]):
        if not line.strip():
            continue
        try:
            entry = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        reason = _regen_backoff_reason(
            entry.get("text")
            or entry.get("preview")
            or entry.get("error")
            or entry.get("message")
        )
        if reason:
            return reason
    return None


def _maybe_proactive_regen_window_backoff(
    state: dict,
    progress: job_progress.ProgressLog,
    *,
    phase: str,
    context: dict | None = None,
) -> bool:
    """Pause before starting another LLM call once 80% of the window is used."""
    _ensure_regen_usage_window(state)
    _, threshold, reset_at = _regen_usage_window_bounds(state)
    now = datetime.now(timezone.utc)
    if now >= reset_at:
        state["usage_window_started_at"] = now.isoformat()
        _write_regen_checkpoint(state)
        return False
    if now < threshold:
        return False

    delay = max(0.0, (reset_at - now).total_seconds())
    state.update({
        "status": "backing_off",
        "backoff_kind": "proactive_usage_window",
        "backoff_reason": (
            f"Reached {_usage_window_label(state)} usage-window guard"
        ),
        "backoff_phase": phase,
        "backoff_company_id": (
            (context or {}).get("company_id") if isinstance(context, dict) else None
        ),
        "backoff_until": reset_at.isoformat(),
        "backoff_seconds": delay,
        "backoff_started_at": _iso_now(),
        "completed_at": None,
    })
    _write_regen_checkpoint(state)
    _sleep_regen_backoff(
        state,
        progress,
        phase=phase,
        context=context,
    )
    return True


def _honor_existing_regen_backoff(
    state: dict,
    progress: job_progress.ProgressLog,
) -> None:
    if not state.get("backoff_until"):
        return
    _repair_provider_limit_backoff(state)
    phase = state.get("backoff_phase") or "summary"
    company_id = state.get("backoff_company_id")
    item = None
    if company_id:
        raw_item = (state.get("items") or {}).get(company_id)
        if isinstance(raw_item, dict):
            item = raw_item
    context = {
        "company_id": company_id,
        "company_name": item.get("company_name") if item else None,
        "ticker": item.get("ticker") if item else None,
        "company_type": item.get("company_type") if item else None,
    }
    _sleep_regen_backoff(
        state,
        progress,
        item=item,
        phase=phase,
        context={k: v for k, v in context.items() if v is not None},
        resumed=True,
    )


def _regen_all_thread_running() -> bool:
    return any(
        t.name == "company-regen-all" and t.is_alive()
        for t in threading.enumerate()
    )


def _regen_resume_candidate(state: dict | None, companies: list[dict]) -> bool:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        return False
    if state.get("status") not in {"running", "backing_off", "paused_backoff"}:
        return False
    return not _regen_checkpoint_complete(state, companies)


def _regen_status_payload(companies: list[dict] | None = None) -> dict:
    companies = companies if companies is not None else _tracked_companies_for_regen()
    checkpoint = _load_regen_checkpoint()
    _repair_provider_limit_backoff(checkpoint)
    summary = _summarize_regen_checkpoint(companies, checkpoint)
    progress_state = _scan_progress_state(_company_regen_all_progress_path())
    in_flight = _regen_all_thread_running() or _progress_state_in_flight(
        progress_state
    )
    backoff_until = summary.get("backoff_until")
    return {
        "job_id": "all",
        "stream_url": "/api/companies/regen-all/stream",
        "status": (
            checkpoint.get("status")
            if isinstance(checkpoint, dict) and checkpoint.get("status")
            else "idle"
        ),
        "in_flight": in_flight,
        "languages_requested": ["en", "zh"],
        "backoff_until": backoff_until,
        "backoff_remaining_seconds": _seconds_until_iso(backoff_until),
        **summary,
    }


def resume_regen_all_if_needed() -> bool:
    """Resume a durable regen-all checkpoint after a server restart."""
    companies = _tracked_companies_for_regen()
    checkpoint = _load_regen_checkpoint()
    if not _regen_resume_candidate(checkpoint, companies):
        return False
    if _regen_all_thread_running():
        return False
    path = _company_regen_all_progress_path()
    if path.exists():
        _supersede_progress_file(
            path,
            reason="superseded by regen-all server-restart resume",
        )
    threading.Thread(
        target=_run_regen_all_companies_job,
        kwargs={"force": False},
        name="company-regen-all",
        daemon=True,
    ).start()
    return True


def _exception_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    return f"{type(exc).__name__}: {exc}"


def _wait_for_existing_trader_refresh(
    path: "Path",
    progress: job_progress.ProgressLog,
    *,
    context: dict,
) -> dict:
    state = _scan_progress_state(path)
    if not _progress_state_in_flight(state):
        return state
    next_heartbeat = time.monotonic()
    while _progress_state_in_flight(state):
        if time.monotonic() >= next_heartbeat:
            progress.emit(
                "stage",
                stage="waiting_trader",
                message=(
                    "Waiting for existing trader-view refresh to finish"
                ),
                **context,
            )
            next_heartbeat = time.monotonic() + 60
        time.sleep(2)
        state = _scan_progress_state(path)
    return state


def _run_regen_all_companies_job(*, force: bool = False) -> None:
    """Refresh every tracked company's dossier and public trader snapshot."""
    progress = job_progress.ProgressLog(_company_regen_all_progress_path())
    companies = _tracked_companies_for_regen()
    state, resumed = _prepare_regen_checkpoint(companies, force=force)
    _ensure_regen_usage_window(state)
    _write_regen_checkpoint(state)
    queue = _summarize_regen_checkpoint(companies, state)
    total_count = queue["total_count"]
    progress.emit(
        "job_init",
        kind="company_regen_all",
        title="Regenerate all company views",
        subtitle=f"{total_count} tracked companies",
        total_count=total_count,
        force=force,
        resumed=resumed,
        checkpoint_status=state.get("status"),
        pending_count=queue["pending_count"],
        completed_count=queue["completed_count"],
        failed_count=queue["failed_count"],
        languages_requested=["en", "zh"],
        include_translations=True,
        translation_mode="all",
        public_trader_count=queue["public_trader_count"],
        private_count=queue["private_count"],
        backoff_until=state.get("backoff_until"),
        usage_window_started_at=state.get("usage_window_started_at"),
        usage_window_seconds=state.get("usage_window_seconds"),
        usage_window_pause_fraction=state.get("usage_window_pause_fraction"),
    )

    if state.get("backoff_until"):
        _honor_existing_regen_backoff(state, progress)

    if not companies:
        state["status"] = "done"
        state["completed_at"] = _iso_now()
        _write_regen_checkpoint(state)
        progress.emit(
            "done",
            total_count=0,
            summary_refreshed_count=0,
            summary_failed_count=0,
            trader_refreshed_count=0,
            trader_skipped_count=0,
            trader_failed_count=0,
            results=[],
        )
        return

    items = state.setdefault("items", {})
    for idx, company in enumerate(companies, start=1):
        company_id = (company.get("id") or "").strip()
        raw_company_name = (company.get("name") or "").strip()
        company_name = raw_company_name or company_id or "Unknown company"
        ticker = (company.get("ticker") or "").strip()
        company_type = company.get("company_type") or storage.infer_company_type(
            company
        )
        context = {
            "company_id": company_id,
            "company_name": company_name,
            "ticker": ticker,
            "company_type": company_type,
            "index": idx,
            "total_count": total_count,
        }

        if not company_id:
            progress.emit(
                "stage",
                stage="skipped",
                message=f"Skipped {company_name}: missing company id",
                **context,
            )
            continue

        item = _regen_item_for_company(company, items.get(company_id))
        items[company_id] = item

        if not raw_company_name:
            item["summary_status"] = "skipped_missing_name"
            item["summary_error"] = "Company has no name to query"
            _checkpoint_item(state, item)
            progress.emit(
                "stage",
                stage="skipped",
                message=f"Skipped {company_id}: missing company name",
                **context,
            )
        elif item.get("summary_status") == "done":
            progress.emit(
                "stage",
                stage="summary_already_done",
                message=f"Summary already refreshed for {company_name}",
                **context,
            )
        elif item.get("summary_status") in _REGEN_SUMMARY_TERMINAL_STATUSES:
            progress.emit(
                "stage",
                stage="summary_skipped_terminal",
                message=f"Summary previously ended for {company_name}",
                **context,
            )
        else:
            scoped_progress = _ProgressContext(progress, **context)
            while item.get("summary_status") != "done":
                if _maybe_proactive_regen_window_backoff(
                    state,
                    progress,
                    phase="summary",
                    context=context,
                ):
                    continue
                item["summary_status"] = "running"
                item["summary_started_at"] = _iso_now()
                item.pop("summary_error", None)
                _checkpoint_item(state, item)
                progress.emit(
                    "stage",
                    stage="refreshing_summary",
                    message=(
                        f"Refreshing {company_name} summary "
                        f"({idx}/{total_count})"
                    ),
                    **context,
                )
                try:
                    summary = _refresh_company_summary(
                        company_id, progress=scoped_progress
                    )
                except Exception as exc:  # noqa: BLE001
                    error_text = _exception_text(exc)
                    reason = (
                        scoped_progress.backoff_reason
                        or _regen_backoff_reason(error_text)
                    )
                    if reason:
                        _backoff_regen_until_reset(
                            state,
                            progress,
                            reason=reason,
                            item=item,
                            phase="summary",
                            context=context,
                        )
                        continue
                    logger.exception(
                        "regen-all summary refresh crashed for %s", company_id
                    )
                    item["summary_status"] = "error"
                    item["summary_error"] = error_text
                    _checkpoint_item(state, item)
                    progress.emit(
                        "stage",
                        stage="summary_failed",
                        message=f"Summary failed for {company_name}",
                        error=error_text,
                        **context,
                    )
                    break

                reason = scoped_progress.backoff_reason or _regen_backoff_reason(
                    summary.get("reason")
                )
                if reason is None and _regen_retryable_error_text(summary.get("reason")):
                    reason = summary.get("reason")
                if summary.get("source") == "fallback" and reason:
                    _backoff_regen_until_reset(
                        state,
                        progress,
                        reason=reason,
                        item=item,
                        phase="summary",
                        context=context,
                    )
                    continue

                item["summary_status"] = "done"
                item["summary_source"] = summary.get("source")
                item["summary_refreshed_at"] = _iso_now()
                item.pop("summary_error", None)
                if summary.get("reason"):
                    item["summary_reason"] = summary.get("reason")
                else:
                    item.pop("summary_reason", None)
                _checkpoint_item(state, item)
                break

        refreshed = storage.get_company(company_id) or company
        ticker = (refreshed.get("ticker") or "").strip()
        company_type = refreshed.get("company_type") or storage.infer_company_type(
            refreshed
        )
        item["ticker"] = ticker
        item["company_type"] = company_type
        if company_type != "public" and item.get("trader_status") != "done":
            item["trader_status"] = "not_applicable"
        if company_type == "public" and item.get("trader_status") == "not_applicable":
            item["trader_status"] = "pending"
        context.update({"ticker": ticker, "company_type": company_type})
        _checkpoint_item(state, item)

        if company_type != "public":
            progress.emit(
                "stage",
                stage="trader_not_applicable",
                message=f"No trader view needed for {company_name}",
                **context,
            )
            continue
        if not ticker:
            item["trader_status"] = "skipped_missing_ticker"
            item["trader_error"] = "Public company is missing a ticker"
            _checkpoint_item(state, item)
            progress.emit(
                "stage",
                stage="skipped_trader",
                message=f"Skipped {company_name} trader view: missing ticker",
                **context,
            )
            continue
        if item.get("trader_status") == "done":
            progress.emit(
                "stage",
                stage="trader_already_done",
                message=f"Trader view already refreshed for {ticker}",
                **context,
            )
            continue
        if item.get("trader_status") in _REGEN_TRADER_TERMINAL_STATUSES:
            progress.emit(
                "stage",
                stage="trader_skipped_terminal",
                message=f"Trader view previously ended for {ticker}",
                **context,
            )
            continue

        snapshot_path = _trader_snapshot_progress_path(company_id)
        while item.get("trader_status") != "done":
            if _maybe_proactive_regen_window_backoff(
                state,
                progress,
                phase="trader",
                context=context,
            ):
                continue
            existing_state = _scan_progress_state(snapshot_path)
            if _progress_state_in_flight(existing_state) and force:
                _supersede_progress_file(
                    snapshot_path,
                    reason="superseded by regen-all force-refresh",
                )
            elif _progress_state_in_flight(existing_state):
                final_state = _wait_for_existing_trader_refresh(
                    snapshot_path,
                    progress,
                    context=context,
                )
                if final_state.get("terminal_type") == "done":
                    item["trader_status"] = "done"
                    item["trader_refreshed_at"] = _iso_now()
                    item.pop("trader_error", None)
                    _checkpoint_item(state, item)
                    break
                reason = (
                    _progress_log_backoff_reason(snapshot_path)
                    or _regen_backoff_reason(final_state.get("error"))
                )
                if reason is None and _regen_retryable_error_text(
                    final_state.get("error")
                ):
                    reason = final_state.get("error")
                if reason:
                    _backoff_regen_until_reset(
                        state,
                        progress,
                        reason=reason,
                        item=item,
                        phase="trader",
                        context=context,
                    )
                    continue
            elif existing_state.get("exists") and not existing_state.get("terminated"):
                _supersede_progress_file(
                    snapshot_path,
                    reason="superseded stale trader refresh during regen-all",
                )

            item["trader_status"] = "running"
            item["trader_started_at"] = _iso_now()
            item.pop("trader_error", None)
            _checkpoint_item(state, item)
            progress.emit(
                "stage",
                stage="refreshing_trader",
                message=f"Refreshing {ticker} trader view ({idx}/{total_count})",
                **context,
            )
            try:
                _run_trader_snapshot_job(
                    company_id,
                    languages_requested=["en", "zh"],
                    include_translations=True,
                    translation_mode="all",
                )
            except Exception as exc:  # noqa: BLE001
                error_text = _exception_text(exc)
                reason = (
                    _progress_log_backoff_reason(snapshot_path)
                    or _regen_backoff_reason(error_text)
                )
                if reason is None and _regen_retryable_error_text(error_text):
                    reason = error_text
                if reason:
                    _backoff_regen_until_reset(
                        state,
                        progress,
                        reason=reason,
                        item=item,
                        phase="trader",
                        context=context,
                    )
                    continue
                logger.exception("regen-all trader refresh crashed for %s", company_id)
                item["trader_status"] = "error"
                item["trader_error"] = error_text
                _checkpoint_item(state, item)
                progress.emit(
                    "stage",
                    stage="trader_failed",
                    message=f"Trader view failed for {ticker}",
                    error=error_text,
                    **context,
                )
                break

            final_state = _scan_progress_state(snapshot_path)
            if final_state.get("terminal_type") == "done":
                item["trader_status"] = "done"
                item["trader_refreshed_at"] = _iso_now()
                item.pop("trader_error", None)
                _checkpoint_item(state, item)
                break
            error_text = final_state.get("error") or "Trader snapshot failed"
            reason = (
                _progress_log_backoff_reason(snapshot_path)
                or _regen_backoff_reason(error_text)
            )
            if reason is None and _regen_retryable_error_text(error_text):
                reason = error_text
            if reason:
                _backoff_regen_until_reset(
                    state,
                    progress,
                    reason=reason,
                    item=item,
                    phase="trader",
                    context=context,
                )
                continue
            item["trader_status"] = "error"
            item["trader_error"] = error_text
            _checkpoint_item(state, item)
            progress.emit(
                "stage",
                stage="trader_failed",
                message=f"Trader view failed for {ticker}",
                error=error_text,
                **context,
            )
            break

        progress.emit(
            "stage",
            stage="company_done",
            message=f"Finished {company_name}",
            summary_status=item.get("summary_status"),
            trader_status=item.get("trader_status"),
            **context,
        )

    final_summary = _summarize_regen_checkpoint(companies, state)
    state["status"] = (
        "done_with_errors" if final_summary["failed_count"] else "done"
    )
    state["completed_at"] = _iso_now()
    _write_regen_checkpoint(state)
    progress.emit(
        "done",
        total_count=total_count,
        pending_count=final_summary["pending_count"],
        completed_count=final_summary["completed_count"],
        failed_count=final_summary["failed_count"],
        summary_refreshed_count=final_summary["summary_refreshed_count"],
        summary_failed_count=final_summary["summary_failed_count"],
        trader_refreshed_count=final_summary["trader_refreshed_count"],
        trader_skipped_count=final_summary["trader_skipped_count"],
        trader_failed_count=final_summary["trader_failed_count"],
        checkpoint_status=state["status"],
        results=final_summary["items"],
    )


def _run_refresh_all_trader_snapshots_job(
    *,
    force: bool = False,
    languages_requested: list[str] | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
) -> None:
    """Sequentially refresh every tracked public-company trader snapshot."""
    progress = job_progress.ProgressLog(_trader_refresh_all_progress_path())
    companies = _public_companies_for_trader_refresh()
    total_count = len(companies)
    progress.emit(
        "job_init",
        kind="public_snapshot_bulk",
        title="Refresh all stock views",
        subtitle=f"{total_count} public companies",
        total_count=total_count,
        force=force,
        languages_requested=languages_requested or ["en", "zh"],
        include_translations=include_translations,
        translation_mode=translation_mode,
    )

    if not companies:
        progress.emit(
            "done",
            total_count=0,
            refreshed_count=0,
            skipped_count=0,
            failed_count=0,
            results=[],
        )
        return

    refreshed_count = 0
    skipped_count = 0
    failed_count = 0
    results: list[dict] = []

    for idx, company in enumerate(companies, start=1):
        company_id = (company.get("id") or "").strip()
        company_name = company.get("name") or company_id or "Unknown company"
        ticker = (company.get("ticker") or "").strip()

        if not company_id:
            skipped_count += 1
            results.append({
                "company_id": None,
                "company_name": company_name,
                "ticker": ticker,
                "status": "skipped_missing_id",
            })
            continue
        if not ticker:
            skipped_count += 1
            progress.emit(
                "stage",
                stage="skipped",
                message=f"Skipped {company_name}: missing ticker",
                company_id=company_id,
                company_name=company_name,
                ticker=ticker,
                index=idx,
                total_count=total_count,
            )
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "skipped_missing_ticker",
            })
            continue

        snapshot_path = _trader_snapshot_progress_path(company_id)
        state = _scan_progress_state(snapshot_path)
        if _progress_state_in_flight(state) and not force:
            skipped_count += 1
            progress.emit(
                "stage",
                stage="already_running",
                message=f"Skipped {company_name}: refresh already running",
                company_id=company_id,
                company_name=company_name,
                ticker=ticker,
                index=idx,
                total_count=total_count,
            )
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "already_running",
            })
            continue
        if _progress_state_in_flight(state) and force:
            _supersede_progress_file(
                snapshot_path, reason="superseded by bulk force-refresh"
            )

        progress.emit(
            "stage",
            stage="refreshing_company",
            message=f"Refreshing {ticker} ({idx}/{total_count})",
            company_id=company_id,
            company_name=company_name,
            ticker=ticker,
            index=idx,
            total_count=total_count,
        )
        try:
            _run_trader_snapshot_job(
                company_id,
                languages_requested=languages_requested,
                include_translations=include_translations,
                translation_mode=translation_mode,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("bulk trader refresh crashed for %s", company_id)
            failed_count += 1
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        final_state = _scan_progress_state(snapshot_path)
        if final_state.get("terminal_type") == "done":
            refreshed_count += 1
            status = "done"
        else:
            failed_count += 1
            status = "error"
        result = {
            "company_id": company_id,
            "company_name": company_name,
            "ticker": ticker,
            "status": status,
        }
        if final_state.get("error"):
            result["error"] = final_state["error"]
        results.append(result)

    progress.emit(
        "done",
        total_count=total_count,
        refreshed_count=refreshed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        results=results,
    )


@router.get("/trader/stats")
def get_trader_stats(limit: int = Query(default=30, ge=1, le=250)) -> dict:
    """Return per-symbol trader refresh token/change history."""
    return trader_stats.build_dashboard(storage.list_companies(), limit=limit)


@router.get("/trader/stats/{company_id}")
def get_trader_stats_for_company(
    company_id: str,
    limit: int = Query(default=80, ge=1, le=500),
) -> dict:
    """Return longitudinal trader refresh stats for one company."""
    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return trader_stats.build_company_stats(company_id, company, limit=limit)


@router.post("/companies/{company_id}/trader/refresh")
def post_trader_refresh(
    company_id: str,
    languages: str | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
    force: bool = False,
) -> dict:
    """Kick off (or attach to) a trader-snapshot refresh for a company.

    Returns ``{job_id, stream_url, status, languages_requested}``.
    ``status`` is ``"queued"`` when a fresh job spawned,
    ``"already_running"`` when we attached to an existing in-flight
    refresh, and ``"force_queued"`` when ``?force=true`` superseded an
    in-flight run.

    The bilingual contract: ``languages`` is a comma-separated list of
    codes (today: ``en``, ``zh``); ``include_translations`` and
    ``translation_mode`` mirror the iOS request shape. Phase 1 just
    records these inputs on the job log so clients can observe what was
    asked for; the generator always produces both languages.

    ``force=true`` is the breaking-schema-change escape hatch (see
    docs/heat-card-v2.md §6): mark any stale in-flight progress file
    as terminated, unlink it, and spawn a fresh worker even if the
    short-circuit would otherwise return ``already_running``.

    Public-only: returns 400 if the company's bucket is private.
    """
    company = storage.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    company_type = company.get("company_type") or storage.infer_company_type(company)
    if company_type != "public":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "company_type_not_public",
                "message": (
                    f"Company {company_id} is bucketed as "
                    f"{company_type!r}; the trader snapshot only runs "
                    "for public companies."
                ),
            },
        )

    languages_requested = _parse_trader_languages(languages)
    stream_url = f"/api/companies/{company_id}/trader/refresh/stream"

    path = _trader_snapshot_progress_path(company_id)
    state = _scan_progress_state(path)
    in_flight = state.get("exists") and not state.get("terminated")
    if in_flight and not force:
        return {
            "job_id": company_id,
            "stream_url": stream_url,
            "status": "already_running",
            "languages_requested": languages_requested,
        }
    if in_flight and force:
        # Supersede the stale in-flight worker. We emit a terminal
        # `error` event so any SSE consumer tailing the old progress
        # file sees an explicit superseded marker rather than a silent
        # cut. The old background thread, if still alive, will keep
        # running but its writes go to a deleted file — harmless.
        try:
            tail_progress = job_progress.ProgressLog(path)
            tail_progress.emit(
                "error",
                error="superseded by force-refresh",
                terminal=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "force-refresh: failed to mark stale progress terminated"
            )
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("force-refresh: failed to unlink stale progress")

    threading.Thread(
        target=_run_trader_snapshot_job,
        args=(company_id,),
        kwargs={
            "languages_requested": languages_requested,
            "include_translations": include_translations,
            "translation_mode": translation_mode,
        },
        name=f"trader-snapshot:{company_id}",
        daemon=True,
    ).start()
    return {
        "job_id": company_id,
        "stream_url": stream_url,
        "status": "force_queued" if force else "queued",
        "languages_requested": languages_requested,
    }


@router.post("/companies/trader/refresh-all")
def post_trader_refresh_all(
    languages: str | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
    force: bool = False,
) -> dict:
    """Refresh trader snapshots for every tracked public company."""
    languages_requested = _parse_trader_languages(languages)
    stream_url = "/api/companies/trader/refresh-all/stream"
    companies = _public_companies_for_trader_refresh()
    queue = _summarize_trader_refresh_queue(companies, force=force)

    path = _trader_refresh_all_progress_path()
    state = _scan_progress_state(path)
    in_flight = _progress_state_in_flight(state)
    if in_flight and not force:
        return {
            "job_id": "all",
            "stream_url": stream_url,
            "status": "already_running",
            "languages_requested": languages_requested,
            **queue,
        }
    if in_flight and force:
        _supersede_progress_file(
            path, reason="superseded by bulk force-refresh"
        )

    threading.Thread(
        target=_run_refresh_all_trader_snapshots_job,
        kwargs={
            "force": force,
            "languages_requested": languages_requested,
            "include_translations": include_translations,
            "translation_mode": translation_mode,
        },
        name="trader-snapshot:all",
        daemon=True,
    ).start()
    return {
        "job_id": "all",
        "stream_url": stream_url,
        "status": "force_queued" if force else "queued",
        "languages_requested": languages_requested,
        **queue,
    }


@router.post("/companies/regen-all")
def post_companies_regen_all(force: bool = False) -> dict:
    """Regenerate every tracked company's summary and public trader view.

    This is the broad admin refresh: every tracked company gets a fresh
    deep-search dossier plus forced company translation; companies that are
    public after that refresh also get a bilingual trader snapshot.
    """
    stream_url = "/api/companies/regen-all/stream"
    companies = _tracked_companies_for_regen()
    checkpoint = None if force else _load_regen_checkpoint()
    if _regen_checkpoint_complete(checkpoint, companies):
        checkpoint = None
    queue = _summarize_regen_checkpoint(companies, checkpoint)
    will_resume = bool(
        not force
        and isinstance(checkpoint, dict)
        and checkpoint.get("schema_version") == 1
    )

    path = _company_regen_all_progress_path()
    progress_state = _scan_progress_state(path)
    in_flight = _regen_all_thread_running() or _progress_state_in_flight(
        progress_state
    )
    if in_flight and not force:
        return {
            "job_id": "all",
            "stream_url": stream_url,
            "status": "already_running",
            "resumed": will_resume,
            "languages_requested": ["en", "zh"],
            **queue,
        }
    if in_flight and force:
        _supersede_progress_file(
            path, reason="superseded by regen-all force-refresh"
        )
    elif progress_state.get("exists") and not progress_state.get("terminated"):
        _supersede_progress_file(
            path, reason="superseded stale regen-all progress"
        )

    threading.Thread(
        target=_run_regen_all_companies_job,
        kwargs={"force": force},
        name="company-regen-all",
        daemon=True,
    ).start()
    return {
        "job_id": "all",
        "stream_url": stream_url,
        "status": "force_queued" if force else "resumed" if will_resume else "queued",
        "resumed": will_resume,
        "languages_requested": ["en", "zh"],
        **queue,
    }


@router.get("/companies/regen-all/status")
def get_companies_regen_all_status() -> dict:
    """Return durable checkpoint state for the all-company regeneration."""
    return _regen_status_payload()


@router.get("/companies/{company_id}/trader/refresh/stream")
async def stream_trader_refresh(company_id: str) -> "StreamingResponse":
    """SSE stream of progress events for the in-flight trader-snapshot
    job for a company. Replays from disk so reconnects don't drop
    events.
    """
    from fastapi.responses import StreamingResponse

    path = _trader_snapshot_progress_path(company_id)
    gen = _console_event_stream(path)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/companies/regen-all/stream")
async def stream_companies_regen_all() -> "StreamingResponse":
    """SSE stream for all-company summary + trader-view regeneration."""
    from fastapi.responses import StreamingResponse

    gen = _console_event_stream(_company_regen_all_progress_path())
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/companies/trader/refresh-all/stream")
async def stream_trader_refresh_all() -> "StreamingResponse":
    """SSE stream for the bulk public-company trader refresh."""
    from fastapi.responses import StreamingResponse

    gen = _console_event_stream(_trader_refresh_all_progress_path())
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
