"""HTTP API for the research center."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

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
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import (
    alert_engine,
    analytics_store,
    auth_store,
    cache,
    browser_archive,
    buffett_memo_analysis,
    claude_runner,
    companies_ai,
    companies_ai_public,
    companies_autocomplete,
    company_translate,
    copilot,
    console_session,
    console_store,
    context_store,
    decisions_store,
    deck_summary,
    desk_store,
    evidence_store,
    evidence_matrix,
    external_store,
    external_translate,
    files_store,
    trader_bilingual_fill,
    generator,
    hormuz_console,
    hormuz_prep,
    hormuz_store,
    hypothesis_cycle,
    hypothesis_store,
    job_history,
    job_progress,
    link_preview as link_preview_mod,
    live_quotes,
    market_brief,
    memo_analysis,
    memo_editor_store,
    memo_studio_bridge,
    memo_prep,
    news_archive,
    product_store,
    research_eval,
    research_pages,
    research_store,
    serena_analysis,
    storage,
    stock_research,
    text_analysis,
    trader_stats,
    tracking_dashboard,
    tracking_updates,
    weekly_stocks,
)

logger = logging.getLogger("bsh.api")

ACTIVE_JOB_MAX_IDLE_SECONDS = int(
    os.environ.get("BSH_ACTIVE_JOB_MAX_IDLE_SECONDS", "1800")
)
SEARCH_JOB_MAX_IDLE_SECONDS = int(
    os.environ.get("BSH_SEARCH_JOB_MAX_IDLE_SECONDS", "180")
)


def _record_report_generation_event(event: str, **payload: Any) -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    try:
        path = storage.DATA_DIR / "_api" / "report_generation_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001
        logger.debug("Failed to record report generation event", exc_info=True)


UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
EXTERNAL_RESEARCH_MAX_FILE_BYTES = research_store.MAX_FILE_BYTES
EXTERNAL_RESEARCH_ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
}
EXTERNAL_RESEARCH_ANALYSIS_TEXT_LIMIT = 60_000
EXTERNAL_RESEARCH_SOURCE_TRACE_LIMIT = 5
PDF_OCR_NEEDED_MIN_TEXT_CHARS = 40
_RESEARCH_JOB_CANCEL_EVENTS: dict[str, threading.Event] = {}
_RESEARCH_JOB_CANCEL_LOCK = threading.RLock()


async def _read_upload_bounded(
    file: UploadFile,
    *,
    max_bytes: int,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {total} bytes (max {max_bytes})",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _external_research_upload_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    kind = EXTERNAL_RESEARCH_ALLOWED_EXTENSIONS.get(ext)
    if kind:
        return kind
    allowed = ", ".join(sorted(EXTERNAL_RESEARCH_ALLOWED_EXTENSIONS))
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported external research file type: {filename}. Supported: {allowed}",
    )


def _research_cancel_key(kind: str, *parts: str) -> str:
    return f"{kind}:" + "/".join(str(part) for part in parts)


def _start_research_cancel_event(key: str) -> threading.Event:
    event = threading.Event()
    with _RESEARCH_JOB_CANCEL_LOCK:
        _RESEARCH_JOB_CANCEL_EVENTS[key] = event
    return event


def _request_research_cancel(key: str) -> bool:
    with _RESEARCH_JOB_CANCEL_LOCK:
        event = _RESEARCH_JOB_CANCEL_EVENTS.get(key)
    if event is None:
        return False
    event.set()
    return True


def _clear_research_cancel_event(
    key: str, event: threading.Event | None
) -> None:
    if event is None:
        return
    with _RESEARCH_JOB_CANCEL_LOCK:
        if _RESEARCH_JOB_CANCEL_EVENTS.get(key) is event:
            _RESEARCH_JOB_CANCEL_EVENTS.pop(key, None)


def _progress_cancelled(path: Path) -> bool:
    return _scan_progress_state(path).get("terminal_type") == "cancelled"


def _emit_cancelled_progress(
    path: Path,
    *,
    reason: str,
    **fields,
) -> dict:
    try:
        return job_progress.cancel_progress_file(path, reason=reason, **fields)
    except Exception:  # noqa: BLE001
        logger.exception("failed to mark progress cancelled: %s", path)
        return _scan_progress_state(path)


def _honor_research_cancel(
    path: Path,
    event: threading.Event | None,
    *,
    reason: str,
    **fields,
) -> bool:
    if not ((event is not None and event.is_set()) or _progress_cancelled(path)):
        return False
    if not _progress_cancelled(path):
        _emit_cancelled_progress(path, reason=reason, **fields)
    return True


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
#   - the httponly ``bsh_session`` cookie (EventSource SSE and
#     ``<a href="...">`` downloads, which can't set headers). There is NO
#     ``?token=`` query-parameter channel — it leaked credentials into
#     access logs/history and was removed; see ``_extract_presented_token``.
#
# Requests with no credentials fail closed (401). The only escape hatch is
# the explicit ``BSH_ALLOW_ANON_DEV=1`` local-development opt-in — see
# ``_anon_dev_enabled`` below.


def _expected_token() -> str | None:
    """Read the configured token at call time (so test/runtime changes to
    the environment take effect without restart).
    """
    return _normalize_api_token(os.environ.get("BSH_RESEARCH_API_TOKEN"))


def _anon_dev_enabled() -> bool:
    """True only when the operator has explicitly opted into unauthenticated
    access via ``BSH_ALLOW_ANON_DEV=1``. This is the ONLY thing that lets a
    request through with no credentials when no shared token is configured —
    without it, missing/empty ``BSH_RESEARCH_API_TOKEN`` fails closed. Must
    never be set in production.
    """
    return os.environ.get("BSH_ALLOW_ANON_DEV") == "1"


# Name of the httponly session cookie set on login. Lets browser downloads
# (`<a href>`) and EventSource SSE authenticate without a `?token=` query
# param, since those can't set an Authorization header.
SESSION_COOKIE_NAME = "bsh_session"

# Methods that can't mutate state — cookie-authenticated requests skip the
# CSRF header check for these.
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


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


def _extract_presented_token(request: Request) -> tuple[str | None, str | None]:
    """Read the token from the Authorization header and return
    ``(presented, raw_for_logging)``. Does not validate.

    The legacy ``?token=`` query-parameter channel was removed — it leaked
    credentials into access logs, browser history, and Referer headers.
    Browser downloads and SSE now authenticate via the httponly session
    cookie instead (see ``SESSION_COOKIE_NAME``).
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return _normalize_api_token(auth[7:]), auth
    return None, None


def _enforce_cookie_csrf(request: Request) -> None:
    """For cookie-authenticated *mutations*, require a custom header a
    cross-site attacker cannot set. SameSite=Lax already blocks cross-site
    cookie POSTs; this is defense in depth. Bearer-header auth (iOS,
    tooling) is CSRF-immune and never reaches this check.
    """
    if request.method in _CSRF_SAFE_METHODS:
        return
    if request.headers.get("x-bsh-client"):
        return
    raise HTTPException(
        status_code=403,
        detail="Missing CSRF header (X-BSH-Client) on cookie-authenticated request",
    )


def require_api_token(request: Request) -> None:
    """FastAPI dependency: enforce auth on /api/* routes.

    Accepts, in order: the shared env-configured token (Authorization
    header only), a per-session token issued via ``POST /api/auth/token``
    (Authorization header), or the httponly session cookie set on login.

    Fails CLOSED: with no shared token configured and no credentials
    presented, the request is rejected 401 unless ``BSH_ALLOW_ANON_DEV=1``
    is explicitly set (local development only).
    """
    presented, presented_raw = _extract_presented_token(request)
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    expected = _expected_token()

    # Fail closed: no shared token, nothing presented → reject unless the
    # operator explicitly opted into anonymous dev access. Anon dev is a
    # local, full-access escape hatch (see _caller_role); the shared token
    # below is a limited machine credential — the two are distinct.
    if not expected and presented is None and not cookie_token:
        if _anon_dev_enabled():
            request.state.auth_kind = "anon_dev"
            return
        raise HTTPException(status_code=401, detail="Authentication required")

    # Path 1: shared env token (service/tooling, Authorization header).
    if expected and _api_token_matches(presented, expected):
        request.state.auth_kind = "shared"
        return

    # Path 2: session token in the Authorization header (web fetch, iOS).
    session = auth_store.validate_token(presented) if presented else None
    if session:
        request.state.session_email = session.get("email")
        return

    # Path 3: session cookie (browser downloads / SSE). Guard mutations.
    if cookie_token:
        session = auth_store.validate_token(cookie_token)
        if session:
            request.state.session_email = session.get("email")
            _enforce_cookie_csrf(request)
            return

    # Stale bearer/cookie from another checkout must not trap a local
    # operator who opted into anonymous access.
    if _anon_dev_enabled():
        request.state.auth_kind = "anon_dev"
        return

    logger.warning(
        "API token rejected path=%s presented={%s} expected={%s} cookie=%s",
        request.url.path,
        _describe_api_token(presented_raw, presented),
        _describe_api_token(os.environ.get("BSH_RESEARCH_API_TOKEN"), expected or ""),
        bool(cookie_token),
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
    must_reset: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars)")


# --- Login rate limiting -------------------------------------------------
# In-memory sliding window keyed on normalized email. Blunts credential
# stuffing / brute force without a datastore. Per-process (fine for the
# single-worker deployment); swap for a shared store if scaled out.
_LOGIN_MAX_FAILURES = 5
_LOGIN_WINDOW_SECONDS = 15 * 60
_login_failures: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _login_key(email: str) -> str:
    return (email or "").strip().lower()


def _rate_limit_login(email: str) -> None:
    """Raise 429 if this email has too many recent failures."""
    key = _login_key(email)
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_failures.get(key, []) if now - t < _LOGIN_WINDOW_SECONDS]
        _login_failures[key] = hits
        if len(hits) >= _LOGIN_MAX_FAILURES:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


def _record_login_failure(email: str) -> None:
    key = _login_key(email)
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_failures.get(key, []) if now - t < _LOGIN_WINDOW_SECONDS]
        hits.append(now)
        _login_failures[key] = hits


def _reset_login_failures(email: str) -> None:
    with _login_lock:
        _login_failures.pop(_login_key(email), None)


def _cookie_secure(request: Request) -> bool:
    """Whether to mark the session cookie ``Secure``. Honors an explicit
    ``BSH_COOKIE_SECURE`` override, else infers from the forwarded proto
    (prod behind TLS-terminating nginx) or the request scheme. Off for
    plain-http local dev so the cookie is still accepted there.
    """
    override = os.environ.get("BSH_COOKIE_SECURE")
    if override in ("0", "1"):
        return override == "1"
    proto = request.headers.get("x-forwarded-proto")
    if proto:
        return proto.split(",")[0].strip() == "https"
    return request.url.scheme == "https"


# Cookie path is "/" rather than the mount prefix: nginx strips the
# ``/research`` prefix before the app sees the request, so the app-internal
# path is always ``/api/...``. A "/"-scoped cookie is sent for both the
# browser-visible ``/research/...`` URLs and the stripped internal paths,
# which a prefix-scoped cookie would not reliably cover.
_SESSION_COOKIE_PATH = "/"


def _set_session_cookie(request: Request, response: Response, raw_token: str) -> None:
    """Attach the httponly session cookie so browser downloads (`<a href>`)
    and EventSource SSE authenticate without a `?token=` query param."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=int(auth_store.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path=_SESSION_COOKIE_PATH,
    )


def _clear_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path=_SESSION_COOKIE_PATH)


@auth_router.post("/token", response_model=LoginResponse)
def login(request: Request, response: Response, payload: LoginRequest) -> LoginResponse:
    """Email + password → freshly minted per-session token.

    On success the caller receives ``token`` (stored client-side and sent
    as ``Authorization: Bearer <token>`` on API fetches) AND an httponly
    session cookie (used by browser downloads/SSE that can't set headers).
    Rate-limited per email to blunt credential stuffing. Valid for 30 days
    unless revoked via ``POST /api/auth/logout``.
    """
    _rate_limit_login(payload.email)
    email = auth_store.verify_credentials(payload.email, payload.password)
    if not email:
        _record_login_failure(payload.email)
        logger.warning(
            "Login rejected for email=%r (no match or bad password)",
            payload.email,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _reset_login_failures(payload.email)
    session = auth_store.issue_session(email)
    _set_session_cookie(request, response, session["token"])
    logger.info("Login accepted email=%s expires_at=%s", email, session["expires_at"])
    return LoginResponse(
        **session,
        must_reset=auth_store.must_reset(email),
    )


@router.get("/auth/me")
def auth_me(request: Request, response: Response) -> dict:
    """Identify the caller — useful for the SPA to confirm a stored
    token is still valid and to show the logged-in email in the UI.
    Returns ``{email, name, auth: 'session' | 'shared' | 'anon_dev', role, permissions}``.

    Also (re)issues the session cookie for header-authenticated callers so
    users who logged in before cookie support gain one without re-login —
    the SPA calls this on every boot.
    """
    email = getattr(request.state, "session_email", None)
    presented, _ = _extract_presented_token(request)
    if email and presented and auth_store.validate_token(presented):
        _set_session_cookie(request, response, presented)
    role = _caller_role(request)
    auth_kind = getattr(request.state, "auth_kind", None)
    if email:
        auth = "session"
    elif auth_kind == "anon_dev":
        auth = "anon_dev"
    else:
        auth = "shared"
    name = product_store.display_name(email) if email else None
    if not name and auth == "anon_dev":
        name = (os.environ.get("BSH_ANON_DEV_NAME") or "").strip() or None
    return {
        "email": email,
        "name": name,
        "auth": auth,
        "role": role,
        "permissions": product_store.permissions_for_role(role),
        "must_reset": auth_store.must_reset(email) if email else False,
    }


def _caller_email(request: Request) -> str | None:
    return getattr(request.state, "session_email", None)


def _caller_role(request: Request) -> str:
    """Resolve the effective RBAC role for the request.

    - A logged-in user → their email-mapped role.
    - Anonymous dev mode (``BSH_ALLOW_ANON_DEV=1``) → ``admin``: it's an
      explicit, local-only, full-access escape hatch.
    - The shared env token (a machine credential) → the read-only
      ``service`` role.
    """
    email = _caller_email(request)
    if email:
        return product_store.role_for_email(email)
    if getattr(request.state, "auth_kind", None) == "anon_dev":
        return "admin"
    return product_store.role_for_email(None, shared_auth=True)


def _require_permission(request: Request, permission: str) -> None:
    role = _caller_role(request)
    if not product_store.has_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {permission}",
        )


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    """Revoke the session token used on this request (header or cookie) and
    clear the session cookie. No-op for the shared env token.
    """
    presented, _ = _extract_presented_token(request)
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    for candidate in (presented, cookie_token):
        if candidate:
            auth_store.revoke_token(candidate)
    _clear_session_cookie(request, response)
    response.status_code = 204
    return response


@router.post("/auth/change-password", response_model=LoginResponse)
def change_password(
    request: Request, response: Response, payload: ChangePasswordRequest
) -> LoginResponse:
    """Change the authenticated user's password. Requires the current
    password, revokes every existing session for the user, and issues a
    fresh one (returned + set as cookie) so the caller stays logged in.
    Not available to shared-token callers (no user identity).
    """
    email = getattr(request.state, "session_email", None)
    if not email:
        raise HTTPException(status_code=403, detail="Session login required")
    if not auth_store.verify_credentials(email, payload.current_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    auth_store.set_password(email, payload.new_password)
    auth_store.revoke_email(email)
    session = auth_store.issue_session(email)
    _set_session_cookie(request, response, session["token"])
    return LoginResponse(**session, must_reset=False)

REPORT_TYPES = (
    "Investment Report (Auto)",
    "Investment Memo (Late-Stage)",
    "Buffett Investment Memo",
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
    legal_name: str | None = None
    disambiguator: str | None = None
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    # Canonical display category: industry, falling back to sector. All UI
    # surfaces render this one field (QA R5e: search/card showed sector while
    # detail/sidebar showed industry for the same company).
    category: str | None = None
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
    positioning: dict | None = None
    metrics: list[dict] = Field(default_factory=list)
    team_profiles: list[dict] = Field(default_factory=list)
    products: list[dict] = Field(default_factory=list)
    competitors: list[dict | str] = Field(default_factory=list)
    competitor_cards: list[dict] = Field(default_factory=list)
    recent_news: list[dict] = Field(default_factory=list)
    company_news: list[dict] = Field(default_factory=list)
    notable_contracts: list[dict] = Field(default_factory=list)
    notable_acquisitions: list[dict] = Field(default_factory=list)
    board_investors: list[dict] = Field(default_factory=list)
    cap_table_lineage: list[dict] = Field(default_factory=list)
    industry_view: dict | None = None
    expert_opinions: list[dict] = Field(default_factory=list)
    disclosures: list[dict] = Field(default_factory=list)
    memo_state: dict | None = None
    audit_records: list[dict] = Field(default_factory=list)
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
    error: str | None = None
    failure_phase: str | None = None
    failure_detail: str | None = None
    renderer_contract: dict | None = None
    created_at: str
    updated_at: str
    # Memo-run extensions (set for late-stage and Buffett investment memos).
    kind: str | None = None
    run_id: str | None = None
    run_dir: str | None = None
    skill: str | None = None
    memo_files: list[dict] = Field(default_factory=list)
    internal_memo_files: list[dict] = Field(default_factory=list)
    artifacts_available: bool = False
    memo_quality_lint: dict | None = None
    memo_chinese_parity: dict | None = None
    quality_warnings: list[str] | None = None
    analysis_session_id: str | None = None
    analysis_session_approved: bool = False
    download_urls: dict | None = None
    preview_urls: dict | None = None
    # Memo Studio extensions.
    memo_mode: str | None = None
    studio_investigation: dict | None = None
    studio_generate: dict | None = None
    resume_available: bool = False
    # Tracked-news provenance: set when a tracking auto-run launched this
    # report ("tracking_auto_run" + the auto-run record id).
    trigger: str | None = None
    auto_run_id: str | None = None
    # Two completion timestamps (report-ready detach): the DOCX became
    # viewable at report_ready_at; the run fully ended (private artifacts
    # collected) at run_finished_at. Equal-ish when nothing was deferred.
    report_ready_at: str | None = None
    run_finished_at: str | None = None
    # Set when a newer memo run for the same company replaced this failed
    # run; superseded failures are no longer resumable or auto-surfaced.
    superseded_by: str | None = None
    # Set when the user cleared this failure record without reprocessing.
    dismissed_at: str | None = None


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
    analysis_artifacts: list[dict] = Field(default_factory=list)
    resume_available: bool = False


class GenerateRequest(BaseModel):
    company_id: str
    report_type: str
    audience: str
    language: str = "en"
    analysis_session_id: str | None = None
    # "full" = the complete IC report; "compact" = the short partner-memo
    # profile (falls back to full for stages without a compact profile).
    report_mode: str = "full"


class MemoPrepRequest(BaseModel):
    """Request body for POST /api/memos/prep — kicks off the synchronous
    memo-run bootstrap (company resolve, scope check, run-folder mint,
    input staging) before the long-running analysis composite job."""
    company_id: str
    analysis_session_id: str | None = None


class MemoStudioInvestigateRequest(BaseModel):
    """Request body for POST /api/memos/studio/investigate — starts a Memo
    Studio deep investigation (Phases 1-2 plus the studio spine); the run
    parks at ``awaiting_studio`` for card review."""
    company_id: str
    report_type: str | None = None
    analysis_session_id: str | None = None


class MemoRiskRefineRequest(BaseModel):
    framing: str = "other"
    analyst_note: str = ""


class MemoEditorCardPatch(BaseModel):
    included: bool | None = None
    expanded: bool | None = None
    title: str | None = None
    category: str | None = None
    severity: str | None = None
    confidence: str | None = None
    source_class: str | None = None
    source_refs: list[dict[str, Any]] | None = None
    agent_rating: str | None = None
    likelihood: str | None = None


class MemoEditorCardCreate(BaseModel):
    title: str
    category: str | None = None
    severity: str | None = None
    rating: str | None = None
    likelihood: str | None = None
    source_class: str | None = None
    bullets: list[str] | None = None
    source_refs: list[dict[str, Any]] | None = None


class MemoEditorMoveRequest(BaseModel):
    direction: str


class MemoEditorReorderRequest(BaseModel):
    ordered_ids: list[str]


class MemoEditorBulletPatch(BaseModel):
    text: str | None = None
    source_class: str | None = None
    source_refs: list[dict[str, Any]] | None = None


class MemoEditorDiveRequest(BaseModel):
    text: str | None = None


class MemoEditorConclusionRequest(BaseModel):
    conclusion_id: str


class MemoEditorAppendixPatch(BaseModel):
    expanded: bool | None = None
    source_class: str | None = None
    source_refs: list[dict[str, Any]] | None = None


class MemoEditorTaskCreate(BaseModel):
    action_type: str = "discuss"
    title: str
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "proposed"
    created_by: str = "co-pilot"


class MemoEditorTaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    context: dict[str, Any] | None = None
    status: str | None = None


class CopilotContextBody(BaseModel):
    surface: str | None = None
    tab: str | None = None
    selection: dict[str, Any] = Field(default_factory=dict)
    attention: dict[str, Any] = Field(default_factory=dict)
    job: dict[str, Any] = Field(default_factory=dict)
    document_ids: list[str] = Field(default_factory=list)


class CopilotAskBody(BaseModel):
    prompt: str
    context: CopilotContextBody = Field(default_factory=CopilotContextBody)
    output_language: str = "en"
    mode: str = "quick"


class CopilotTaskBody(BaseModel):
    title: str
    description: str = ""
    action_type: str = "discuss"
    context: dict[str, Any] = Field(default_factory=dict)


class CopilotApplyEditBody(BaseModel):
    section_id: str
    card_id: str
    bullet_id: str
    text: str


class CopilotEventBody(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DocumentMetadataPatch(BaseModel):
    category: str | None = None
    source_class: str | None = None
    status: str | None = None
    confidence: str | None = None
    provenance: dict[str, Any] | None = None


class UseInReportPatch(BaseModel):
    use_in_report: bool


class WorkspacePreferencePatch(BaseModel):
    memo_parallel_runs: int | None = None
    weekly_summary: bool | None = None
    stock_auto_refresh: bool | None = None
    agent_alerts: bool | None = None
    compact_density: bool | None = None
    language: str | None = None


class ThreadIn(BaseModel):
    question: str
    answer: str = ""


class StockResearchRunLedgerRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int | None = None
    ledger_id: str | None = None
    workspace: str | None = None
    job_kind: str | None = None
    artifact_id: str | None = None
    run_id: str | None = None
    tracker_id: str | None = None
    company_id: str | None = None
    session_id: str | None = None
    period_id: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    duration_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    estimated_cost_usd: float | None = None
    failure_reason: str | None = None
    fallback_used: bool | None = None
    preserved_previous_artifact: bool | None = None
    cancellation_reason: str | None = None
    source_count: int | None = None
    evidence_coverage: float | dict[str, Any] | None = None


class StockResearchDoctorIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    severity: str
    message: str


class StockResearchDoctorPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    generated_at: str
    summary: dict[str, Any] = Field(default_factory=dict)
    issues: list[StockResearchDoctorIssue] = Field(default_factory=list)


class StockResearchWorkProductVersion(BaseModel):
    model_config = ConfigDict(extra="allow")

    version_id: str | None = None
    artifact_id: str | None = None
    version: int | None = None
    supersedes_version_id: str | None = None
    generated_files: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    review_log: list[dict[str, Any]] = Field(default_factory=list)
    action_log: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None


class StockResearchWorkProductRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int | None = None
    artifact_id: str
    artifact_type: str | None = None
    title: str | None = None
    status: str | None = None
    review_state: str | None = None
    version: int | None = None
    version_id: str | None = None
    version_count: int | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    generated_files: list[dict[str, Any]] = Field(default_factory=list)
    version_history: list[dict[str, Any]] = Field(default_factory=list)
    immutable_versions: list[StockResearchWorkProductVersion] = Field(default_factory=list)
    latest_review_action: dict[str, Any] | None = None


class HypothesisDashboardSummary(BaseModel):
    vintage_count: int = 0
    hypothesis_count: int = 0
    pending_count: int = 0
    training_eligible_count: int = 0


class HypothesisVintageSummary(BaseModel):
    vintage_date: str
    vintage_kind: hypothesis_store.VintageKind = "forward_live"
    hypothesis_count: int = 0
    outcome_count: int = 0
    pending_count: int = 0
    training_eligible_count: int = 0
    kind_counts: dict[str, int] = Field(default_factory=dict)


class HypothesisDashboardRow(hypothesis_store.HypothesisSnapshot):
    outcome: hypothesis_store.HypothesisOutcome | None = None


class HypothesisTrainingSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = hypothesis_store.TRAINING_SUMMARY_SCHEMA_VERSION
    summary_id: str | None = None
    created_at: str | None = None
    eligible_outcome_count: int = 0
    hit_rate_by_confidence_bucket: list[dict[str, Any]] = Field(default_factory=list)
    hit_rate_by_source_category: list[dict[str, Any]] = Field(default_factory=list)
    hit_rate_by_tracker_type: list[dict[str, Any]] = Field(default_factory=list)
    average_relative_return_by_direction: list[dict[str, Any]] = Field(default_factory=list)
    high_confidence_wrong_examples: list[dict[str, Any]] = Field(default_factory=list)
    weak_source_false_positives: list[dict[str, Any]] = Field(default_factory=list)


class HypothesisVintagePayload(BaseModel):
    schema_version: int = hypothesis_store.HYPOTHESIS_SCHEMA_VERSION
    vintage_date: str
    hypotheses: list[hypothesis_store.HypothesisSnapshot] = Field(default_factory=list)
    outcomes: list[hypothesis_store.HypothesisOutcome] = Field(default_factory=list)
    rows: list[HypothesisDashboardRow] = Field(default_factory=list)


class HypothesisDashboardPayload(BaseModel):
    schema_version: int = hypothesis_store.HYPOTHESIS_SCHEMA_VERSION
    generated_at: str
    summary: HypothesisDashboardSummary
    vintages: list[HypothesisVintageSummary] = Field(default_factory=list)
    rows: list[HypothesisDashboardRow] = Field(default_factory=list)
    latest: HypothesisVintagePayload | None = None
    calibration: list[HypothesisTrainingSummary] = Field(default_factory=list)


class HypothesisCreateRequest(BaseModel):
    vintage_date: str
    vintage_kind: hypothesis_store.VintageKind = "forward_live"
    allow_debug_backfill: bool = False
    horizon_days: int = Field(default=7, ge=1)


class HypothesisCreateResponse(BaseModel):
    vintage_date: str
    vintage_kind: hypothesis_store.VintageKind
    created_count: int
    hypotheses: list[hypothesis_store.HypothesisSnapshot] = Field(default_factory=list)
    input_manifest_sha256: str
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class HypothesisEvaluateRequest(BaseModel):
    prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    market_data_source: str = "fixture"
    benchmark_ticker: str = "SPY"


class HypothesisEvaluateResponse(BaseModel):
    vintage_date: str
    evaluated_count: int
    outcomes: list[hypothesis_store.HypothesisOutcome] = Field(default_factory=list)


class StockResearchDashboardPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int | None = None
    generated_at: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    trackers: list[dict[str, Any]] = Field(default_factory=list)
    work_products: list[StockResearchWorkProductRow] = Field(default_factory=list)
    run_ledger: list[StockResearchRunLedgerRow] = Field(default_factory=list)
    doctor: StockResearchDoctorPayload | None = None
    hypotheses: HypothesisDashboardPayload | None = None


class SelectMatch(BaseModel):
    """Payload for promoting an autocomplete or search hit to a local company."""
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    status: str | None = None
    company_type: str | None = None


@router.get("/options")
def get_options() -> dict:
    return {
        "report_types": list(REPORT_TYPES),
        "audiences": list(AUDIENCES),
        "languages": [{"code": "en", "label": "English"}, {"code": "zh", "label": "中文"}],
    }


@router.get("/workspace/settings")
def get_workspace_settings(request: Request) -> dict:
    return {
        "account": product_store.workspace_profile(
            _caller_email(request),
            role_override=_caller_role(request),
        )["account"],
        **product_store.get_preferences(_caller_email(request)),
    }


@router.patch("/workspace/settings")
def patch_workspace_settings(
    patch: WorkspacePreferencePatch,
    request: Request,
) -> dict:
    _require_permission(request, "settings:update")
    try:
        return {
            "account": product_store.workspace_profile(
                _caller_email(request),
                role_override=_caller_role(request),
            )["account"],
            **product_store.update_preferences(
                _caller_email(request),
                patch.model_dump(exclude_none=True),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspace/user-center")
def get_workspace_user_center(request: Request) -> dict:
    email = _caller_email(request)
    profile = product_store.workspace_profile(
        email,
        role_override=_caller_role(request),
    )
    if not email and getattr(request.state, "auth_kind", None) == "anon_dev":
        anon_name = (os.environ.get("BSH_ANON_DEV_NAME") or "").strip()
        if anon_name:
            profile["account"]["name"] = anon_name
    return profile


@router.get("/analytics/summary")
def get_analytics_summary(request: Request) -> dict:
    _require_permission(request, "admin:read")
    return analytics_store.summary()


@router.get("/analytics/events")
def get_analytics_events(
    request: Request,
    limit: int = 100,
    event: str | None = None,
) -> list[dict]:
    _require_permission(request, "admin:read")
    return analytics_store.list_events(limit=limit, event=event)


@router.get("/diagnostics/claude")
def diagnose_claude() -> dict:
    """Health-check the local Claude Code CLI.

    Spawns a one-shot prompt and reports back path, version, model,
    response, latency, and cost. Used to verify Claude is installed and
    authenticated before kicking off real summary jobs.
    """
    return claude_runner.health_check()


@router.get("/quotes")
def get_live_quotes(
    ticker: list[str] = Query(default=[]),
) -> dict:
    """Last print + 1-day move for public tickers.

    Tracking polls this so every listed name can show a live quote
    without waiting on a trader-snapshot Claude pass.
    """
    return live_quotes.fetch_quotes(ticker)


@router.get("/quotes/search")
def search_live_quotes(
    q: str = Query(default=""),
) -> dict:
    """Symbol lookup so Radar can pick any listed name."""
    try:
        return live_quotes.search_symbols(q)
    except Exception:
        return {"query": q, "matches": []}


@router.get("/quotes/screeners")
def get_quote_screeners() -> dict:
    """Nasdaq universe slices: gainers, losers, and large-cap actives."""
    try:
        from server import quote_workspace

        return quote_workspace.fetch_screeners()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Screener unavailable: {exc}") from exc


@router.get("/quotes/calendar")
def get_quote_calendar(
    ticker: list[str] | None = Query(default=None),
) -> dict:
    """Earnings, dividends, and macro calendar for the next few weeks."""
    try:
        from server import quote_workspace

        return quote_workspace.fetch_calendar(ticker or [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar unavailable: {exc}") from exc


@router.get("/quotes/{ticker}/peers")
def get_quote_peers(
    ticker: str,
    peer: list[str] | None = Query(default=None),
) -> dict:
    """Relative performance vs SPY and sector/book peers."""
    try:
        from server import quote_workspace

        return quote_workspace.fetch_peers(ticker, peer or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Peers unavailable for {ticker}: {exc}",
        ) from exc


@router.get("/quotes/{ticker}/workspace")
def get_quote_workspace(ticker: str) -> dict:
    """Gold-style quote workspace: profile, financials, analysis, holders, options."""
    try:
        from server import quote_workspace

        return quote_workspace.fetch_workspace(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Workspace unavailable for {ticker}: {exc}",
        ) from exc


@router.get("/quotes/{ticker}/chart")
def get_quote_chart(
    ticker: str,
    range: str = Query(default="1d"),
) -> dict:
    """Yahoo Finance OHLC chart plus key statistics for one ticker."""
    try:
        return live_quotes.fetch_chart(ticker, range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Chart unavailable for {ticker}: {exc}",
        ) from exc


# --- Market desk durable state ----------------------------------------------


class DeskPrefsBody(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class AlertEventsBody(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


class SignalLedgerBody(BaseModel):
    ticker: str
    direction: str = "watch"
    label: str = ""
    source: str = "manual"
    price_at_signal: float | None = None


@router.get("/desk/prefs")
def get_desk_prefs() -> dict:
    """Server copy of the market-desk localStorage blob."""
    return desk_store.load_prefs()


@router.put("/desk/prefs")
def put_desk_prefs(body: DeskPrefsBody) -> dict:
    """Replace the desk prefs blob (frontend owns the key shape)."""
    try:
        return desk_store.save_prefs(body.data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/alerts/events")
def get_alert_events(
    since: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Fired-alert history (server + browser fires), newest first."""
    return {"events": desk_store.list_alert_events(since=since, limit=limit)}


@router.post("/alerts/events")
def post_alert_events(body: AlertEventsBody) -> dict:
    """Record browser-fired alerts so history survives reloads/devices."""
    recorded = desk_store.record_alert_events(body.events)
    return {"recorded": recorded}


@router.post("/alerts/check")
def post_alerts_check() -> dict:
    """Evaluate stored alert rules against live quotes right now."""
    try:
        return alert_engine.run_check()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Alert check failed: {exc}") from exc


@router.get("/signals/ledger")
def get_signal_ledger(score: bool = Query(default=True)) -> dict:
    """Signal ledger entries, scored against live quotes when possible."""
    entries = desk_store.list_signals()
    if score and entries:
        tickers = sorted({str(row.get("ticker") or "") for row in entries if row.get("ticker")})
        try:
            quotes = live_quotes.fetch_quotes(tickers).get("quotes") or {}
        except Exception:
            quotes = {}
        entries = desk_store.score_signals(quotes)
    return {"entries": entries}


@router.post("/signals/ledger")
def post_signal_ledger(body: SignalLedgerBody) -> dict:
    """Record one signal call; price defaults to the live last print."""
    price = body.price_at_signal
    if price is None:
        try:
            quotes = live_quotes.fetch_quotes([body.ticker]).get("quotes") or {}
            price = (quotes.get(body.ticker.strip().upper()) or {}).get("last_price")
        except Exception:
            price = None
    try:
        entry = desk_store.record_signal(
            {
                "ticker": body.ticker,
                "direction": body.direction,
                "label": body.label,
                "source": body.source,
                "price_at_signal": price,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry": entry}


@router.delete("/signals/ledger/{signal_id}")
def delete_signal_ledger(signal_id: str) -> dict:
    if not desk_store.delete_signal(signal_id):
        raise HTTPException(status_code=404, detail="Unknown signal id")
    return {"ok": True}


@router.post("/market-brief/run")
def post_market_brief_run() -> dict:
    """Build and archive today's Morning Brief."""
    try:
        return market_brief.build_brief()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Brief build failed: {exc}") from exc


@router.get("/market-brief")
def get_market_brief(date: str | None = Query(default=None)) -> dict:
    """Latest archived brief, or one by date (YYYY-MM-DD)."""
    try:
        brief = market_brief.load_brief(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if brief is None:
        raise HTTPException(status_code=404, detail="No archived brief")
    return brief


@router.get("/market-brief/archive")
def get_market_brief_archive() -> dict:
    return {"dates": market_brief.list_briefs()}


class BriefNoteBody(BaseModel):
    date: str | None = None
    length: str = "short"


@router.post("/market-brief/note")
def post_market_brief_note(body: BriefNoteBody) -> dict:
    """Write the model-assisted note for an archived brief (latest by default)."""
    try:
        return market_brief.write_note(body.date, body.length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Note generation failed: {exc}") from exc


@router.get("/diagnostics/quotes")
def get_quotes_diagnostics() -> dict:
    """Quote source health: cache ages and recently failing symbols."""
    return live_quotes.cache_stats()


@router.get("/tracking/rollup")
def get_tracking_rollup(
    company_id: list[str] = Query(default=[]),
) -> dict:
    """Research-state rollup for the companies the caller follows.

    The follow list is browser-local, so ids arrive as query params
    (repeated or comma-joined) rather than being read from a stored
    watchlist.
    """
    return tracking_dashboard.build_rollup(company_id)


@router.post("/companies/{company_id}/copilot/context")
def post_copilot_context(company_id: str, body: CopilotContextBody) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return copilot.assemble_context(company_id, body.model_dump())
    except ValueError as exc:
        if str(exc) == "company_not_found":
            raise HTTPException(status_code=404, detail="Company not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/copilot/ask")
def post_copilot_ask(
    request: Request,
    company_id: str,
    body: CopilotAskBody,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    if body.mode not in {"quick", "deep"}:
        raise HTTPException(status_code=400, detail="Invalid copilot mode")
    try:
        if body.mode == "deep":
            return {
                "mode": "deep",
                **copilot.submit_deep_ask(
                    company_id=company_id,
                    prompt=body.prompt,
                    client_context=body.context.model_dump(),
                    output_language=body.output_language,
                ),
            }
        return {
            "mode": "quick",
            **copilot.submit_quick_ask(
                company_id=company_id,
                prompt=body.prompt,
                client_context=body.context.model_dump(),
                output_language=body.output_language,
            ),
        }
    except ValueError as exc:
        code = str(exc)
        if code == "prompt_required":
            raise HTTPException(status_code=400, detail="prompt is required") from exc
        if code == "company_not_found":
            raise HTTPException(status_code=404, detail="Company not found") from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/companies/{company_id}/copilot/apply-edit")
def post_copilot_apply_edit(
    company_id: str,
    body: CopilotApplyEditBody,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    try:
        state = memo_editor_store.patch_bullet(
            company_id,
            body.section_id,
            body.card_id,
            body.bullet_id,
            {"text": body.text},
        )
        analytics_store.record_event(
            "copilot_edit_applied",
            company_id=company_id,
            section_id=body.section_id,
            card_id=body.card_id,
            bullet_id=body.bullet_id,
        )
        return {"ok": True, "state": state}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/copilot/events", status_code=201)
def post_copilot_event(
    company_id: str,
    body: CopilotEventBody,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    event = str(body.event or "").strip()
    if not event:
        raise HTTPException(status_code=400, detail="event is required")
    return analytics_store.record_event(
        event,
        company_id=company_id,
        **(body.payload or {}),
    )


@router.post("/companies/{company_id}/copilot/tasks", status_code=201)
def create_copilot_task(
    company_id: str,
    body: CopilotTaskBody,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    try:
        return memo_editor_store.create_task(
            company_id,
            {
                "action_type": body.action_type,
                "title": body.title,
                "description": body.description,
                "context": {**body.context, "company_id": company_id},
                "status": "proposed",
                "created_by": "co-pilot",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    analytics_store.record_event("search_started", query=(q or "").strip(), refresh=refresh)
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
def post_companies_search_start(request: Request, q: str = "", refresh: bool = False) -> dict:
    """Kick off a deep search in the background and return a job id + the
    SSE stream URL for live progress.

    If a fresh cache hit exists and refresh isn't set, the matches come
    back inline (no job, no stream needed).
    """
    _require_permission(request, "tasks:action")
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    analytics_store.record_event("search_started", query=query, refresh=refresh)

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

    # Idempotency: attach to an in-flight job for the same query. The lock
    # serializes check-then-spawn so concurrent POSTs can't both start one.
    with _job_start_lock(f"search:{job_id}"):
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
def post_weekly_stocks_refresh(request: Request, force: bool = False) -> dict:
    """Kick off or attach to the weekly hot-stock dashboard refresh."""
    _require_permission(request, "tasks:action")
    path = weekly_stocks.progress_path()
    stream_url = "/api/weekly-stocks/refresh/stream"
    with _job_start_lock("weekly"):
        state = _scan_progress_state(path)
        # Grace 0: a log whose last event is a failed StructuredOutput is
        # superseded immediately (the historical refresh contract), rather
        # than blocking refresh for the schema-retry grace window.
        in_flight = _progress_state_in_flight(
            state, schema_retry_grace_seconds=0.0
        )
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


# ---- Stock Research tracker system --------------------------------------


@router.get("/stock-research", response_model=StockResearchDashboardPayload)
def get_stock_research_dashboard() -> dict:
    """Return the Stock Research toolbox payload."""
    try:
        return stock_research.dashboard_payload()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research-pages/market-pulse")
def get_research_page_market_pulse() -> dict:
    return research_pages.market_pulse_page()


@router.get("/research-pages/evidence-matrix")
def get_research_page_evidence_matrix(company_id: str | None = None) -> dict:
    return research_pages.evidence_matrix_page(company_id=company_id)


@router.get("/research-pages/hypothesis-lab")
def get_research_page_hypothesis_lab() -> dict:
    return research_pages.hypothesis_lab_page()


@router.get("/stock-research/trackers")
def list_stock_research_trackers(include_archived: bool = False) -> list[dict]:
    return stock_research.list_trackers(include_archived=include_archived)


@router.post("/stock-research/trackers", status_code=201)
def create_stock_research_tracker(request: Request, payload: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.create_tracker(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/trackers/{tracker_id}")
def get_stock_research_tracker(tracker_id: str) -> dict:
    tracker = stock_research.get_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
    return tracker


@router.patch("/stock-research/trackers/{tracker_id}")
def update_stock_research_tracker(request: Request, tracker_id: str, patch: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.update_tracker(tracker_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/trackers/{tracker_id}/disable")
def disable_stock_research_tracker(
    request: Request,
    tracker_id: str,
    archive: bool = False,
) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.disable_tracker(tracker_id, archive=archive)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/trackers/import-companies")
def import_stock_research_company_trackers(request: Request, limit: int = 20) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.import_company_trackers(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/sources/link", status_code=201)
def create_stock_research_link_source(request: Request, payload: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.create_link_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/sources/note", status_code=201)
def create_stock_research_note_source(request: Request, payload: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.create_note_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/sources/upload", status_code=201)
async def upload_stock_research_source(
    request: Request,
    file: UploadFile = File(...),
    tracker_ids: list[str] = Form(...),
    title: str | None = Form(default=None),
    priority: str = Form(default="user_provided"),
    relevance: str = Form(default="this_week_input"),
) -> dict:
    _require_permission(request, "sources:edit")
    try:
        data = await _read_upload_bounded(
            file,
            max_bytes=EXTERNAL_RESEARCH_MAX_FILE_BYTES,
        )
        ids: list[str] = []
        for item in tracker_ids:
            ids.extend(part.strip() for part in str(item).split(",") if part.strip())
        return stock_research.create_file_source(
            tracker_ids=ids,
            filename=file.filename or "source",
            content_type=file.content_type,
            data=data,
            title=title,
            priority=priority,
            relevance=relevance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/stock-research/trackers/{tracker_id}/sources/{source_id}")
def remove_stock_research_source_assignment(
    request: Request,
    tracker_id: str,
    source_id: str,
) -> dict:
    _require_permission(request, "documents:delete")
    try:
        return stock_research.remove_source_assignment(tracker_id, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/trackers/{tracker_id}/run", status_code=202)
def run_stock_research_tracker(
    request: Request,
    tracker_id: str,
    period_id: str | None = None,
    force: bool = False,
) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.start_tracker_run(
            tracker_id,
            period_id=period_id,
            force=force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/trackers/run-selected", status_code=202)
def run_selected_stock_research_trackers(request: Request, payload: dict) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.start_selected_tracker_runs(
            [str(item) for item in (payload.get("tracker_ids") or [])],
            retry_failed=bool(payload.get("retry_failed", True)),
            period_id=payload.get("period_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/trackers/run-due", status_code=202)
def run_due_stock_research_trackers(request: Request, period_id: str | None = None) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.start_due_tracker_runs(period_id=period_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stock-research/trackers/{tracker_id}/runs/{run_id}/cancel"
)
def cancel_stock_research_tracker_run(request: Request, tracker_id: str, run_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.cancel_tracker_run(tracker_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stock-research/trackers/{tracker_id}/runs/{run_id}/retry",
    status_code=202,
)
def retry_stock_research_tracker_run(request: Request, tracker_id: str, run_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.retry_tracker_run(tracker_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/stock-research/trackers/{tracker_id}/runs/{run_id}/stream"
)
async def stream_stock_research_tracker_run(
    tracker_id: str,
    run_id: str,
) -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    progress_path = stock_research.tracker_progress_path(tracker_id, run_id)
    gen = _console_event_stream(progress_path)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/stock-research/aggregates/run", status_code=202)
def run_stock_research_aggregate(
    request: Request,
    period_id: str | None = None,
    force: bool = False,
) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.start_aggregate_job(period_id=period_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/aggregates/latest")
def get_latest_stock_research_aggregate() -> dict:
    aggregate = stock_research.latest_aggregate()
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Weekly aggregate not found")
    return aggregate


@router.get("/stock-research/aggregates/{period_id}")
def get_stock_research_aggregate(period_id: str) -> dict:
    aggregate = stock_research.load_aggregate(period_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Weekly aggregate not found")
    return aggregate


@router.post("/stock-research/aggregates/{period_id}/cancel")
def cancel_stock_research_aggregate(request: Request, period_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.cancel_aggregate_job(period_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/aggregates/{period_id}/retry", status_code=202)
def retry_stock_research_aggregate(request: Request, period_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.retry_aggregate_job(period_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/aggregates/{period_id}/stream")
async def stream_stock_research_aggregate(period_id: str) -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    gen = _console_event_stream(stock_research.aggregate_progress_path(period_id))
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/stock-research/strategy-maps/run", status_code=202)
def run_stock_research_strategy_map(
    request: Request,
    period_id: str | None = None,
    force: bool = False,
) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.start_strategy_map_job(
            period_id=period_id,
            force=force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/strategy-maps/latest")
def get_latest_stock_research_strategy_map() -> dict:
    strategy_map = stock_research.latest_strategy_map()
    if strategy_map is None:
        raise HTTPException(status_code=404, detail="Strategy map not found")
    return strategy_map


@router.get("/stock-research/strategy-maps/{period_id}")
def get_stock_research_strategy_map(period_id: str) -> dict:
    strategy_map = stock_research.load_strategy_map(period_id)
    if strategy_map is None:
        raise HTTPException(status_code=404, detail="Strategy map not found")
    return strategy_map


@router.post("/stock-research/strategy-maps/{period_id}/cancel")
def cancel_stock_research_strategy_map(request: Request, period_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.cancel_strategy_map_job(period_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stock-research/strategy-maps/{period_id}/retry", status_code=202)
def retry_stock_research_strategy_map(request: Request, period_id: str) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return stock_research.retry_strategy_map_job(period_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/strategy-maps/{period_id}/stream")
async def stream_stock_research_strategy_map(period_id: str) -> "StreamingResponse":
    from fastapi.responses import StreamingResponse

    gen = _console_event_stream(stock_research.strategy_map_progress_path(period_id))
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/stock-research/work-products",
    response_model=list[StockResearchWorkProductRow],
)
def list_stock_research_work_products(
    artifact_type: str | None = None,
    status: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    return stock_research.list_work_products(
        include_archived=include_archived,
        artifact_type=artifact_type,
        status=status,
    )


@router.patch("/stock-research/work-products/{artifact_id:path}")
def update_stock_research_work_product(request: Request, artifact_id: str, patch: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.update_work_product(artifact_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/review-queue")
def list_stock_research_review_queue(status: str | None = None) -> list[dict]:
    return stock_research.list_review_items(status=status)


@router.patch("/stock-research/review-queue/{item_id:path}")
def update_stock_research_review_item(request: Request, item_id: str, patch: dict) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.update_review_item(item_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stock-research/evaluation")
def get_stock_research_evaluation() -> dict:
    return stock_research.list_evaluation()


@router.get("/stock-research/run-ledger", response_model=list[StockResearchRunLedgerRow])
def get_stock_research_run_ledger() -> list[dict]:
    return stock_research.list_run_ledger()


@router.get("/stock-research/doctor", response_model=StockResearchDoctorPayload)
def get_stock_research_doctor() -> dict:
    return stock_research.stock_research_doctor()


@router.get("/stock-research/hypotheses", response_model=HypothesisDashboardPayload)
def list_stock_research_hypotheses(
    vintage_kind: hypothesis_store.VintageKind | None = None,
) -> dict:
    payload = hypothesis_store.hypothesis_dashboard_payload()
    if vintage_kind:
        rows = [
            row for row in payload.get("rows") or []
            if row.get("vintage_kind") == vintage_kind
        ]
        payload = {**payload, "rows": rows}
    return payload


@router.get(
    "/stock-research/hypotheses/calibration",
    response_model=list[HypothesisTrainingSummary],
)
def list_stock_research_hypothesis_calibration() -> list[dict]:
    return hypothesis_store.list_training_summaries()


@router.get(
    "/stock-research/hypotheses/{vintage_date}",
    response_model=HypothesisVintagePayload,
)
def get_stock_research_hypothesis_vintage(vintage_date: str) -> dict:
    try:
        return hypothesis_store.get_vintage(vintage_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stock-research/hypotheses/create",
    status_code=201,
    response_model=HypothesisCreateResponse,
)
def create_stock_research_hypotheses(request: Request, payload: HypothesisCreateRequest) -> dict:
    _require_permission(request, "tasks:action")
    try:
        return hypothesis_cycle.create_hypotheses(
            vintage_date=payload.vintage_date,
            vintage_kind=payload.vintage_kind,
            allow_debug_backfill=payload.allow_debug_backfill,
            horizon_days=payload.horizon_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stock-research/hypotheses/{vintage_date}/evaluate",
    response_model=HypothesisEvaluateResponse,
)
def evaluate_stock_research_hypotheses(
    request: Request,
    vintage_date: str,
    payload: HypothesisEvaluateRequest | None = None,
) -> dict:
    _require_permission(request, "tasks:action")
    payload = payload or HypothesisEvaluateRequest()
    try:
        adapter = hypothesis_cycle.FixtureMarketDataAdapter(
            payload.prices,
            source_name=payload.market_data_source or "fixture",
        )
        return hypothesis_cycle.evaluate_vintage(
            vintage_date,
            adapter=adapter,
            benchmark_ticker=payload.benchmark_ticker or "SPY",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stock-research/hypotheses/calibrate",
    response_model=HypothesisTrainingSummary,
)
def calibrate_stock_research_hypotheses(request: Request) -> dict:
    _require_permission(request, "tasks:action")
    return hypothesis_cycle.calibrate()


@router.patch("/stock-research/trackers/{tracker_id}/runs/{run_id}/review")
def update_stock_research_run_review(
    request: Request,
    tracker_id: str,
    run_id: str,
    patch: dict,
) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.update_run_review(tracker_id, run_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/stock-research/trackers/{tracker_id}/runs/{run_id}/knowledge/{update_id}"
)
def review_stock_research_knowledge_update(
    request: Request,
    tracker_id: str,
    run_id: str,
    update_id: str,
    patch: dict,
) -> dict:
    _require_permission(request, "sources:edit")
    try:
        return stock_research.review_knowledge_update(
            tracker_id,
            run_id,
            update_id,
            status=str(patch.get("status") or "open"),
            rationale=patch.get("rationale"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/select", status_code=201)
def companies_select(request: Request, payload: SelectMatch) -> dict:
    """Promote an autocomplete suggestion to a tracked company.

    Used when the user clicks a Yahoo-only typeahead hit and we need a stable
    local id before navigating to the research page.
    """
    _require_permission(request, "sources:edit")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    company = storage.upsert_company_from_match(payload.model_dump())
    _ensure_company_translation(company.get("id"))
    analytics_store.record_event(
        "workspace_opened",
        company_id=company.get("id"),
        company_name=company.get("name"),
        source="company_select",
    )
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

    # Query by the most stable key available — ticker, then website host —
    # never the mutable AI-generated name alone: replaying the model's own
    # `name` output as the next query is what minted sibling records (R5c).
    # The name still rides along so a bare host query stays disambiguated.
    ticker = (company.get("ticker") or "").strip()
    host = storage._normalize_host(
        company.get("website")
    ) or storage._normalize_host(company.get("logo_domain"))
    if ticker:
        query = ticker
    elif host:
        query = f"{name} ({host})"
    else:
        query = name

    result = companies_ai.deep_search(
        query,
        force_refresh=True,
        progress=progress,
        only_company_id=company_id,
    )
    matches = result.get("matches") or []
    chosen: dict | None = next(
        (m for m in matches if m.get("id") == company_id), None
    )
    if chosen is None and result.get("source") == "claude_code":
        # deep_search persisted nothing (no returned match resolved to this
        # record). Abort rather than merge or mint a sibling — the old
        # `matches[0]` fallback silently accepted a different company.
        logger.warning(
            "refresh for %s returned no match resolving to it (query=%r); "
            "record left unchanged",
            company_id,
            query,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "Refresh returned a different company; "
                "record left unchanged"
            ),
        )
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
    analytics_store.record_event(
        "workspace_opened",
        company_id=company_id,
        company_name=company.get("name"),
        source="company_get",
    )
    return CompanyOut(**_company_view(company))


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(request: Request, company_id: str) -> Response:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not storage.delete_company(company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    tracking_updates.remove_from_watchlist(company_id)
    analytics_store.record_event("company_removed", company_id=company_id)
    return Response(status_code=204)


@router.get("/tracking/watchlist")
def get_tracking_watchlist() -> dict:
    path = tracking_updates.WATCHLIST_PATH
    updated_at = None
    if path.exists():
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return {"company_ids": tracking_updates.get_watchlist(), "updated_at": updated_at}


class TrackingWatchlistBody(BaseModel):
    company_ids: list[str] = Field(default_factory=list)


@router.put("/tracking/watchlist")
def put_tracking_watchlist(
    request: Request,
    body: TrackingWatchlistBody,
) -> dict:
    _require_permission(request, "tasks:action")
    return tracking_updates.sync_watchlist(body.company_ids)


class TrackingSyncAllBody(BaseModel):
    company_ids: list[str] | None = None
    mark_auto: bool = True
    execute: bool = False
    refresh_news: bool | None = None
    lang: str | None = None


@router.post("/tracking/sync-all")
def sync_all_tracking_updates(
    request: Request,
    body: TrackingSyncAllBody | None = None,
) -> dict:
    _require_permission(request, "tasks:action")
    payload = body or TrackingSyncAllBody()
    return tracking_updates.sync_all_tracked(
        company_ids=payload.company_ids,
        lang=payload.lang,
        mark_auto=payload.mark_auto,
        execute=payload.execute,
        refresh_news=payload.refresh_news,
    )


@router.get("/companies/{company_id}/tracking-updates")
def get_company_tracking_updates(company_id: str, limit: int = 50) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return tracking_updates.list_updates(company_id, limit=limit)


class DecisionCreate(BaseModel):
    verdict: str
    explanation: str
    decided_at: str | None = None
    report_id: str | None = None


@router.get("/companies/{company_id}/decisions")
def get_company_decisions(company_id: str) -> dict:
    """The company's Decision Record — human decisions plus their
    retrospectives (appended over time by the tracking sync)."""
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return decisions_store.list_decisions(company_id)


@router.post("/companies/{company_id}/decisions", status_code=201)
def create_company_decision(
    request: Request, company_id: str, body: DecisionCreate
) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    caller = _caller_email(request)
    created_by = product_store.display_name(caller) or caller or "shared"
    try:
        return decisions_store.add_decision(
            company_id,
            verdict=body.verdict,
            explanation=body.explanation,
            decided_at=body.decided_at,
            report_id=body.report_id,
            created_by=created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/companies/{company_id}/decisions/{decision_id}", status_code=204
)
def delete_company_decision(
    request: Request, company_id: str, decision_id: str
) -> Response:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not decisions_store.remove_decision(company_id, decision_id):
        raise HTTPException(status_code=404, detail="Decision not found")
    return Response(status_code=204)


class TrackingSyncBody(BaseModel):
    mark_auto: bool = True
    execute: bool = False
    refresh_news: bool = True
    lang: str | None = None


@router.post("/companies/{company_id}/tracking-updates/sync")
def sync_company_tracking_updates(
    request: Request,
    company_id: str,
    body: TrackingSyncBody | None = None,
) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    payload = body or TrackingSyncBody()
    try:
        return tracking_updates.sync_from_news_feed(
            company_id,
            lang=payload.lang,
            mark_auto=payload.mark_auto,
            execute=payload.execute,
            refresh_news=payload.refresh_news,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class TrackingAutoRunExecuteBody(BaseModel):
    # The human's "I reviewed the cards" confirmation: bypasses the
    # awaiting-studio guard for this one manual launch.
    acknowledge_review: bool = False


@router.post("/companies/{company_id}/tracking-updates/auto-runs/{auto_run_id}/execute")
def execute_company_tracking_auto_run(
    request: Request,
    company_id: str,
    auto_run_id: str,
    body: TrackingAutoRunExecuteBody | None = None,
) -> dict:
    """Launch one recommended tracking auto-run.

    Domain outcomes come back as HTTP 200 with ``executed: false`` and a
    ``reason`` (``company_busy``, ``awaiting_studio_review``,
    ``auto_run_not_recommended``, ``no_recommended_auto_run`` — also what
    an unknown ``auto_run_id`` yields — ``action_none``,
    ``scope_check_failed``); the frontend renders them as notices, not
    errors.
    """
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    payload = body or TrackingAutoRunExecuteBody()
    try:
        return tracking_updates.execute_auto_run(
            company_id,
            auto_run_id,
            allow_parked_review=payload.acknowledge_review,
        )
    except ValueError as exc:
        if str(exc) == "company_not_found":
            raise HTTPException(status_code=404, detail="Company not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/refresh")
def refresh_company(request: Request, company_id: str) -> CompanyOut:
    """Re-run the AI deep search for this company by name and merge the new
    enrichment back into the local record. Also patch any other cached search
    results that contain this company so they show the fresh data on next view.

    Progress is streamed into the search-job JSONL so the ActiveJobsRail can
    surface this work alongside other in-flight Claude tasks. The HTTP call
    stays synchronous — the response carries the refreshed company once the
    underlying deep-search returns.
    """
    _require_permission(request, "tasks:action")
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
def translate_company_endpoint(request: Request, company_id: str) -> CompanyOut:
    """Force a re-translation of this company (e.g. after editing fields)."""
    _require_permission(request, "tasks:action")
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


def _supersede_stale_memo_failures(company_id: str, new_report_id: str | None) -> None:
    """Mark older failed memo runs for this company as replaced by a new run.

    A failed report's error banner describes progress-to-date of THAT run;
    once the user starts a fresh run it stops being the current state and
    only confuses. Superseded records (and their run folders) stay on disk
    for forensics, but `resume_available` turns false so the UI no longer
    auto-surfaces or offers to resume them.
    """
    if not new_report_id or not company_id:
        return
    for old in storage.list_reports():
        if (
            old.get("id") == new_report_id
            or old.get("company_id") != company_id
            or not memo_prep.is_memo_kind(old.get("kind"))
            or old.get("superseded_by")
            or not (
                str(old.get("status") or "").startswith("failed")
                # A parked studio investigation for the same company is
                # retired too — only one run can claim the card store.
                or str(old.get("status") or "") == "awaiting_studio"
            )
        ):
            continue
        storage.update_report(old["id"], superseded_by=new_report_id)


@router.post("/reports", status_code=201)
def post_report(request: Request, payload: GenerateRequest) -> ReportDetail:
    _require_permission(request, "tasks:action")
    # The stub "Investment Report" type became the real, stage-calibrated
    # memo pipeline; map the legacy string so stale UI builds keep working.
    if payload.report_type == "Investment Report":
        payload.report_type = memo_prep.AUTO_STAGE_REPORT_TYPE
    base_event = {
        "company_id": payload.company_id,
        "report_type": payload.report_type,
        "audience": payload.audience,
        "language": payload.language,
        "analysis_session_id": payload.analysis_session_id,
    }
    _record_report_generation_event("request_received", **base_event)
    analytics_store.record_event("memo_generate_started", **base_event)
    if payload.report_type not in REPORT_TYPES:
        _record_report_generation_event(
            "request_rejected",
            **base_event,
            status_code=400,
            detail="Invalid report_type",
        )
        raise HTTPException(status_code=400, detail="Invalid report_type")
    if payload.audience not in AUDIENCES:
        _record_report_generation_event(
            "request_rejected",
            **base_event,
            status_code=400,
            detail="Invalid audience",
        )
        raise HTTPException(status_code=400, detail="Invalid audience")
    if payload.language not in LANGUAGES:
        _record_report_generation_event(
            "request_rejected",
            **base_event,
            status_code=400,
            detail="Invalid language",
        )
        raise HTTPException(status_code=400, detail="Invalid language")
    if payload.report_mode not in ("full", "compact"):
        _record_report_generation_event(
            "request_rejected",
            **base_event,
            status_code=400,
            detail="Invalid report_mode",
        )
        raise HTTPException(status_code=400, detail="Invalid report_mode")

    # Investment memos (late-stage and Buffett) route through the prep
    # pipeline (run folder, scope check) instead of the placeholder generator.
    if memo_prep.is_memo_report_type(payload.report_type):
        try:
            result = memo_prep.bootstrap_memo_run(
                payload.company_id,
                analysis_session_id=payload.analysis_session_id,
                report_type=payload.report_type,
                report_mode=payload.report_mode,
            )
        except memo_prep.AnalysisSessionNotReadyError as exc:
            _record_report_generation_event(
                "request_rejected",
                **base_event,
                status_code=400,
                detail=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            _record_report_generation_event(
                "request_rejected",
                **base_event,
                status_code=404,
                detail=str(exc),
            )
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            _record_report_generation_event(
                "request_failed",
                **base_event,
                status_code=500,
                detail=str(exc),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        report = result.get("report") or storage.get_report(result["report_id"])
        if report is None:
            _record_report_generation_event(
                "request_failed",
                **base_event,
                status_code=500,
                detail="Report record vanished after prep",
            )
            raise HTTPException(status_code=500, detail="Report record vanished after prep")
        _supersede_stale_memo_failures(
            report.get("company_id") or payload.company_id, report.get("id")
        )
        _record_report_generation_event(
            "report_created",
            **base_event,
            report_id=report.get("id"),
            status=report.get("status"),
            run_dir=report.get("run_dir"),
        )
        return ReportDetail(**_report_detail(report))

    try:
        report = storage.create_report(
            company_id=payload.company_id,
            report_type=payload.report_type,
            audience=payload.audience,
            language=payload.language,
        )
    except ValueError as exc:
        _record_report_generation_event(
            "request_rejected",
            **base_event,
            status_code=404,
            detail=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    generator.start_generation(report["id"])
    _record_report_generation_event(
        "report_created",
        **base_event,
        report_id=report.get("id"),
        status=report.get("status"),
        run_dir=report.get("run_dir"),
    )
    return ReportDetail(**_report_detail(report))


def _report_artifact_entry(
    report: dict,
    *,
    artifact: str,
    language: str,
    preview: bool = False,
) -> dict | None:
    if artifact == "internal":
        entries = report.get("internal_memo_files") or []
        return next(
            (
                f
                for f in entries
                if f.get("kind") == "internal_diligence_memo"
                and (not preview or f.get("pdf_path"))
            ),
            None,
        )
    entries = report.get("memo_files") or []
    key = "pdf_path" if preview else "path"
    return next(
        (
            f
            for f in entries
            if f.get("language") == language and f.get(key)
        ),
        None,
    )


def _memo_run_dir(report: dict) -> Path | None:
    run_dir = report.get("run_dir")
    if not run_dir:
        return None
    return (memo_prep.DATA_DIR.parent / str(run_dir)).resolve()


def _analysis_artifact_label(filename: str) -> str:
    label = claude_runner._MEMO_ANALYSIS_PASSES.get(filename)
    if label:
        return label
    label = claude_runner._BUFFETT_ANALYSIS_PASSES.get(filename)
    if label:
        return label
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


def _report_analysis_artifacts(report: dict) -> list[dict]:
    run_dir = _memo_run_dir(report)
    if not run_dir:
        return []
    analysis_dir = run_dir / "analysis"
    if not analysis_dir.is_dir():
        return []

    known_order = {
        filename: idx
        for idx, filename in enumerate(claude_runner._MEMO_ANALYSIS_PASSES)
    }
    files = sorted(
        (p for p in analysis_dir.iterdir() if p.is_file() and p.suffix == ".md"),
        key=lambda p: (known_order.get(p.name, len(known_order)), p.name),
    )
    rid = report.get("id")
    artifacts: list[dict] = []
    for path in files:
        entry = {
            "label": _analysis_artifact_label(path.name),
            "filename": path.name,
            "path": memo_prep._rel(path),
        }
        if rid:
            entry["download_url"] = (
                f"/api/reports/{rid}/download?artifact=analysis"
                f"&file={quote(path.name)}"
            )
        artifacts.append(entry)
    return artifacts


def _report_resume_available(report: dict) -> bool:
    if not memo_prep.is_memo_kind(report.get("kind")):
        return False
    # A newer run replaced this failure, or the user dismissed it; the
    # record stays for forensics but it must not be auto-surfaced or
    # resumed.
    if report.get("superseded_by") or report.get("dismissed_at"):
        return False
    if str(report.get("memo_mode") or "auto") == "studio":
        # Studio recovery is "press Generate again": the monolithic resume
        # path would regenerate the package ignoring the user's pins.
        return False
    status = str(report.get("status") or "")
    resumable = (
        status.startswith("failed") and status not in {"failed_scope_check"}
    ) or status == "complete_with_warnings"
    if not resumable:
        return False
    run_dir = _memo_run_dir(report)
    if not run_dir or not run_dir.exists():
        return False
    if memo_prep.is_buffett_kind(report.get("kind")):
        if (run_dir / "logs" / "memo_package.json").exists():
            return True
        return status.startswith("failed") and status not in {"failed_scope_check"}
    if status in ("failed_quality_gate", "complete_with_warnings"):
        # Quality regeneration needs the analysis artifacts to rewrite from.
        return bool(_report_analysis_artifacts(report))
    if (run_dir / "logs" / "memo_package.json").exists():
        return True
    return bool(_report_analysis_artifacts(report))


def _report_analysis_artifact_path(report: dict, filename: str | None) -> Path:
    if not filename:
        raise HTTPException(status_code=400, detail="file is required for analysis artifacts")
    name_path = Path(filename)
    if name_path.name != filename or name_path.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="file must be an analysis markdown filename")

    run_dir = _memo_run_dir(report)
    if not run_dir:
        raise HTTPException(status_code=404, detail="Report has no run folder")
    analysis_dir = (run_dir / "analysis").resolve()
    file_path = (analysis_dir / filename).resolve()
    try:
        file_path.relative_to(analysis_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid analysis artifact path") from exc
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis artifact not found")
    return file_path


@router.get("/reports/{report_id}/download")
def download_memo(
    report_id: str,
    language: str = "en",
    artifact: str = "memo",
    analysis_file: str | None = Query(default=None, alias="file"),
) -> FileResponse:
    """Download a memo .docx in the requested language.

    Returns 404 if the report doesn't exist, isn't an investment memo, or
    the rendered file isn't on disk (e.g., still running, or the run
    folder was deleted).
    """
    if artifact not in ("memo", "internal", "analysis"):
        raise HTTPException(
            status_code=400,
            detail="artifact must be 'memo', 'internal', or 'analysis'",
        )
    if artifact == "memo" and language not in ("en", "zh"):
        raise HTTPException(status_code=400, detail="language must be 'en' or 'zh'")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not memo_prep.is_memo_kind(report.get("kind")):
        raise HTTPException(
            status_code=404, detail="Report is not an investment memo"
        )
    if artifact == "analysis":
        file_path = _report_analysis_artifact_path(report, analysis_file)
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="text/markdown; charset=utf-8",
        )
    target = _report_artifact_entry(report, artifact=artifact, language=language)
    if not target or not target.get("path"):
        label = "internal diligence memo" if artifact == "internal" else f"{language} file"
        raise HTTPException(status_code=404, detail=f"No {label} recorded")
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
def preview_memo(
    report_id: str,
    language: str = "en",
    artifact: str = "memo",
) -> FileResponse:
    """Serve the rendered PDF of a memo for inline preview.

    Mirrors `download_memo` but targets the `pdf_path` recorded on the
    memo_files entry (rendered post-run from the .docx) and serves it
    with an inline disposition so it renders in an <iframe>/embed rather
    than downloading. Returns 404 if no PDF was produced (e.g. Word
    automation unavailable) — the .docx download is still offered.
    """
    if artifact not in ("memo", "internal"):
        raise HTTPException(status_code=400, detail="artifact must be 'memo' or 'internal'")
    if artifact == "memo" and language not in ("en", "zh"):
        raise HTTPException(status_code=400, detail="language must be 'en' or 'zh'")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not memo_prep.is_memo_kind(report.get("kind")):
        raise HTTPException(
            status_code=404, detail="Report is not an investment memo"
        )
    target = _report_artifact_entry(
        report,
        artifact=artifact,
        language=language,
        preview=True,
    )
    if not target or not target.get("pdf_path"):
        label = "internal diligence memo" if artifact == "internal" else f"{language} PDF"
        raise HTTPException(
            status_code=404,
            detail=f"No {label} preview was rendered for this run",
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


@router.post("/reports/{report_id}/cancel", status_code=200)
def cancel_memo_report(request: Request, report_id: str) -> ReportDetail:
    """Cancel a queued or in-flight memo run from the jobs rail.

    Kills the run's claude subprocesses, blocks respawns, and writes the
    terminal failed state (failure_phase=cancelled — never auto-resumed).
    The run stays resumable/regeneratable exactly like any other failure.
    """
    _require_permission(request, "tasks:action")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not memo_prep.is_memo_kind(report.get("kind")):
        raise HTTPException(
            status_code=400,
            detail="Only investment memo runs can be cancelled",
        )
    if str(report.get("status") or "").startswith("complete"):
        # The report is already rendered and viewable — the run is only
        # finalizing private artifacts (report-ready detach). Cancelling
        # now would mark a delivered report as failed.
        raise HTTPException(
            status_code=409,
            detail="Report is already complete; only artifacts are finalizing",
        )
    state = _scan_progress_state(_memo_stream_path_for_report(report_id))
    if state.get("exists") and state.get("terminated"):
        raise HTTPException(
            status_code=409, detail="This run has already finished"
        )
    memo_analysis.cancel_run(report_id)
    # Drop the /jobs/active TTL cache so the rail row disappears on the
    # client's immediate refresh instead of up to 3 seconds later.
    global _active_jobs_cache
    _active_jobs_cache = None
    updated = storage.get_report(report_id) or report
    return ReportDetail(**_report_detail(updated))


@router.post("/reports/{report_id}/dismiss", status_code=200)
def dismiss_memo_report(request: Request, report_id: str) -> ReportDetail:
    """Clear a failed memo run's error record without any reprocessing.

    Resume regenerates the memo with real Claude passes — the right call
    when the user still wants the memo. For a stale failure they just want
    out of the way, this marks the record dismissed: no worker, no cost.
    The run folder and report record stay on disk for forensics, but the
    failure stops being auto-surfaced and stops offering resume.
    """
    _require_permission(request, "tasks:action")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not memo_prep.is_memo_kind(report.get("kind")):
        raise HTTPException(
            status_code=400,
            detail="Only investment memo reports can be dismissed",
        )
    status = str(report.get("status") or "")
    if not (status.startswith("failed") or status == "awaiting_studio"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Only failed or awaiting-studio memo reports can be "
                "dismissed"
            ),
        )
    state = _scan_progress_state(_memo_stream_path_for_report(report_id))
    if state.get("exists") and not state.get("terminated"):
        raise HTTPException(
            status_code=409,
            detail="Memo report still has an active worker",
        )
    updated = storage.update_report(
        report_id,
        dismissed_at=datetime.now(timezone.utc).isoformat(),
    ) or report
    return ReportDetail(**_report_detail(updated))


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(request: Request, report_id: str) -> None:
    """Delete a generated report record so it leaves the Library.

    Removes only the record: a memo run's folder under ``data/memos/``
    stays on disk, like dismissed failures. Refuses while a memo worker
    is still writing (same guard as dismiss).
    """
    _require_permission(request, "documents:delete")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if memo_prep.is_memo_kind(report.get("kind")):
        state = _scan_progress_state(_memo_stream_path_for_report(report_id))
        if state.get("exists") and not state.get("terminated"):
            raise HTTPException(
                status_code=409,
                detail="Memo report still has an active worker",
            )
    if not storage.delete_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found")


@router.post("/reports/{report_id}/resume", status_code=202)
def resume_memo_report(request: Request, report_id: str) -> ReportDetail:
    _require_permission(request, "tasks:action")
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not memo_prep.is_memo_kind(report.get("kind")):
        raise HTTPException(
            status_code=400,
            detail="Only investment memo reports can be resumed",
        )
    status = str(report.get("status") or "")
    if status == "failed_scope_check":
        raise HTTPException(
            status_code=400,
            detail="Scope-check failures cannot be resumed",
        )
    if not status.startswith("failed") and status != "complete_with_warnings":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only failed or complete-with-warnings memo reports can be "
                "resumed"
            ),
        )
    if not _report_resume_available(report):
        raise HTTPException(
            status_code=400,
            detail="No reusable memo package or analysis artifacts are available",
        )
    progress_path = _memo_stream_path_for_report(report_id)
    state = _scan_progress_state(progress_path)
    if state.get("exists") and not state.get("terminated"):
        raise HTTPException(
            status_code=409,
            detail="Memo report already has an active worker",
        )

    updated = storage.update_report(
        report_id,
        status="analyzing",
        stage="Resume queued",
        progress=max(int(report.get("progress") or 0), 60),
        error=None,
        # resume_from_* preserve the ORIGINAL failure across chained
        # resumes (provenance — or-chained on purpose)...
        resume_from_status=report.get("resume_from_status") or status,
        resume_from_failure_phase=(
            report.get("resume_from_failure_phase")
            or report.get("failure_phase")
        ),
        resume_from_failure_detail=(
            report.get("resume_from_failure_detail")
            or report.get("failure_detail")
            or report.get("error")
        ),
        # ...while resume_last_* always carry the failure THIS resume is
        # recovering from. The worker's quality_failed check needs it: on a
        # second resume the stale resume_from_* said "renderer_contract",
        # so a quality-gate failure took the package-reuse shortcut and
        # re-failed on the identical DOCX in one second.
        resume_last_status=status,
        resume_last_failure_phase=report.get("failure_phase"),
        failure_phase=None,
        failure_detail=None,
        # Per-run diagnostics describe the FAILED attempt's progress-to-date;
        # clear them so the UI reflects the resumed attempt, not stale gates.
        analysis_error=None,
        renderer_contract=None,
        memo_quality_lint=None,
        memo_chinese_parity=None,
        quality_warnings=None,
    ) or report
    if memo_prep.is_buffett_kind(report.get("kind")):
        buffett_memo_analysis.start_resume(report_id)
    else:
        memo_analysis.start_resume(report_id)
    return ReportDetail(**_report_detail(updated))


def resume_interrupted_memo_runs(max_resumes: int = 2) -> int:
    """Auto-resume memo runs a restart interrupted (Phase 4.6).

    The memo worker is a daemon thread, so a restart kills it; the shutdown
    hook marks in-flight runs ``failed_during_analysis`` with
    ``failure_phase="shutdown"`` — those were provably healthy when the
    process exited, so resume them at startup. Runs the *orphan sweep*
    demoted (``failure_phase="orphaned"``) may be arbitrarily old and are
    deliberately NOT auto-resumed — they get a working Resume button for a
    human instead. Genuine analysis failures also stay parked. Set
    ``BSH_MEMO_AUTO_RESUME=0`` to keep restarts from spawning Claude work.
    """
    if os.environ.get("BSH_MEMO_AUTO_RESUME", "1") != "1":
        return 0
    resumed = 0
    for report in storage.list_reports():
        if resumed >= max_resumes:
            break
        if not memo_prep.is_memo_kind(report.get("kind")):
            continue
        if str(report.get("memo_mode") or "auto") == "studio":
            # Studio runs recover through Investigate / Generate, never
            # through the monolithic resume path.
            continue
        if str(report.get("status") or "") != "failed_during_analysis":
            continue
        if report.get("failure_phase") != "shutdown":
            continue
        if not _report_resume_available(report):
            continue
        report_id = str(report.get("id") or "")
        if not report_id:
            continue
        state = _scan_progress_state(_memo_stream_path_for_report(report_id))
        if state.get("exists") and not state.get("terminated"):
            continue
        storage.update_report(
            report_id,
            status="analyzing",
            stage="Resume queued (auto, after restart)",
            progress=max(int(report.get("progress") or 0), 60),
            error=None,
            resume_from_status=report.get("resume_from_status")
            or "failed_during_analysis",
            resume_from_failure_phase=(
                report.get("resume_from_failure_phase")
                or report.get("failure_phase")
            ),
            resume_from_failure_detail=(
                report.get("resume_from_failure_detail")
                or report.get("failure_detail")
                or report.get("error")
            ),
            failure_phase=None,
            failure_detail=None,
            analysis_error=None,
            renderer_contract=None,
            memo_quality_lint=None,
            memo_chinese_parity=None,
            quality_warnings=None,
        )
        if memo_prep.is_buffett_kind(report.get("kind")):
            buffett_memo_analysis.start_resume(report_id)
        else:
            memo_analysis.start_resume(report_id)
        logger.info("Auto-resumed restart-interrupted memo run %s", report_id)
        resumed += 1
    return resumed


@router.post("/memos/prep", status_code=201)
def post_memo_prep(request: Request, payload: MemoPrepRequest) -> ReportDetail:
    """Bootstrap an investment-memo run.

    Synchronously resolves the company, mints the run folder, runs the
    late-stage / pre-IPO scope check, stages source materials, and writes
    the manifest skeleton. Early-stage signals are non-fatal warnings and
    continue into analysis; hard out-of-scope failures preserve the run
    folder and return `status: failed_scope_check` plus the scope reason.
    """
    _require_permission(request, "tasks:action")
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

    report = result.get("report") or storage.get_report(result["report_id"])
    if report is None:
        raise HTTPException(status_code=500, detail="Report record vanished after prep")
    _supersede_stale_memo_failures(
        report.get("company_id") or payload.company_id, report.get("id")
    )
    return ReportDetail(**_report_detail(report))


_STUDIO_NEEDS_PARALLEL_DETAIL = (
    "Memo Studio requires BSH_MEMO_ENGLISH_PARALLEL=1; the monolithic "
    "English path has no spine input and cannot honor studio cards"
)


def _company_has_active_memo_run(company_slug: str) -> bool:
    for report in storage.list_reports():
        if report.get("company_id") != company_slug:
            continue
        if not memo_prep.is_memo_kind(report.get("kind")):
            continue
        report_id = str(report.get("id") or "")
        if not report_id:
            continue
        state = _scan_progress_state(_memo_stream_path_for_report(report_id))
        if state.get("exists") and not state.get("terminated"):
            return True
    return False


@router.post("/memos/studio/investigate", status_code=201)
def post_memo_studio_investigate(
    request: Request, payload: MemoStudioInvestigateRequest
) -> ReportDetail:
    """Start a Memo Studio deep investigation.

    Runs Phase 1-2 plus the standalone studio spine in a background
    worker, seeds the company's studio cards from the spine, and parks
    the report at ``awaiting_studio`` for the user to review and edit
    before ``POST /api/memos/studio/{report_id}/generate``.
    """
    _require_permission(request, "tasks:action")
    if os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") != "1":
        raise HTTPException(status_code=409, detail=_STUDIO_NEEDS_PARALLEL_DETAIL)
    report_type = payload.report_type or memo_prep.AUTO_STAGE_REPORT_TYPE
    if report_type == "Investment Report":
        report_type = memo_prep.AUTO_STAGE_REPORT_TYPE
    if not memo_prep.is_memo_report_type(
        report_type
    ) or memo_prep.is_buffett_report_type(report_type):
        raise HTTPException(
            status_code=400,
            detail="report_type is not available for Memo Studio",
        )
    company = storage.get_company(payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    company_slug = memo_prep._company_slug(company)
    if _company_has_active_memo_run(company_slug):
        raise HTTPException(
            status_code=409,
            detail="A memo run is already in flight for this company",
        )
    try:
        result = memo_prep.bootstrap_memo_run(
            payload.company_id,
            analysis_session_id=payload.analysis_session_id,
            report_type=report_type,
            memo_mode="studio",
        )
    except memo_prep.AnalysisSessionNotReadyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    report = storage.get_report(result["report_id"])
    if report is None:
        raise HTTPException(
            status_code=500, detail="Report record vanished after prep"
        )
    _supersede_stale_memo_failures(
        report.get("company_id") or payload.company_id, report.get("id")
    )
    return ReportDetail(**_report_detail(report))


@router.post("/memos/studio/{report_id}/generate", status_code=202)
def post_memo_studio_generate(request: Request, report_id: str) -> ReportDetail:
    """Generate (or regenerate) the memo from the studio cards.

    Synchronously composes the user's edited cards into the run's
    ``spine.json`` (freeze semantics: the worker reads only that file, so
    edits made after this call affect the next generate), then spawns the
    Phase 3+ worker with the spine pinned.
    """
    _require_permission(request, "tasks:action")
    if os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") != "1":
        raise HTTPException(status_code=409, detail=_STUDIO_NEEDS_PARALLEL_DETAIL)
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if (
        not memo_prep.is_memo_kind(report.get("kind"))
        or str(report.get("memo_mode") or "auto") != "studio"
    ):
        raise HTTPException(
            status_code=400, detail="Not a Memo Studio report"
        )
    if report.get("dismissed_at") or report.get("superseded_by"):
        raise HTTPException(
            status_code=409,
            detail="This studio report was dismissed or superseded",
        )
    status = str(report.get("status") or "")
    if status not in {
        "awaiting_studio",
        "complete",
        "complete_with_warnings",
        # Recovery path: a failed or restart-interrupted generation is
        # retried by pressing Generate again (the spine file is on disk).
        "failed_during_analysis",
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot generate from status {status!r}",
        )
    state = _scan_progress_state(_memo_stream_path_for_report(report_id))
    if state.get("exists") and not state.get("terminated"):
        raise HTTPException(
            status_code=409,
            detail="Memo report still has an active worker",
        )
    run_dir = _memo_run_dir(report)
    if not run_dir or not run_dir.exists():
        raise HTTPException(status_code=400, detail="Run folder missing")
    spine_path = run_dir / "logs" / "english_units" / "spine.json"
    if not spine_path.exists() or not (run_dir / "analysis" / "fast").is_dir():
        raise HTTPException(
            status_code=400,
            detail=(
                "Investigation artifacts are missing — run Deep "
                "Investigate again"
            ),
        )
    company_id = str(report.get("company_id") or "")
    try:
        editor_state = memo_editor_store.get_state(company_id, create=True)
        base_spine = json.loads(spine_path.read_text(encoding="utf-8"))
        spine, pin_sheet, compose_warnings = memo_studio_bridge.compose_spine(
            editor_state,
            base_spine,
            provenance={
                "report_id": report_id,
                "run_id": str(report.get("run_id") or ""),
            },
        )
    except memo_studio_bridge.StudioComposeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Archive the current spine, then freeze the composed one.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    spine_path.replace(
        spine_path.with_name(f"spine.before_generate.{stamp}.json")
    )
    spine_text = json.dumps(spine, ensure_ascii=False, indent=2)
    spine_path.write_text(spine_text, encoding="utf-8")
    (spine_path.parent / memo_studio_bridge.STUDIO_PIN_SHEET_FILENAME).write_text(
        pin_sheet, encoding="utf-8"
    )
    generation_count = (
        int((report.get("studio_generate") or {}).get("generation_count") or 0)
        + 1
    )
    updated = storage.update_report(
        report_id,
        status="analyzing",
        stage="Studio generation queued",
        progress=60,
        error=None,
        failure_phase=None,
        failure_detail=None,
        analysis_error=None,
        renderer_contract=None,
        memo_quality_lint=None,
        memo_chinese_parity=None,
        quality_warnings=None,
        studio_generate={
            "revision_id": editor_state.get("revision_id"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "spine_sha256": hashlib.sha256(
                spine_text.encode("utf-8")
            ).hexdigest(),
            "generation_count": generation_count,
            "warnings": compose_warnings,
        },
    ) or report
    memo_analysis.start_generate_from_studio(report_id)
    return ReportDetail(**_report_detail(updated))


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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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


@router.get("/companies/{company_id}/memo-analysis/catalog")
def get_memo_analysis_catalog(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.memo_work_product_catalog(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/companies/{company_id}/memo-analysis/run-ledger")
def get_memo_analysis_run_ledger(company_id: str) -> list[dict]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.list_run_ledger(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-analysis/tools/{tool_name}/run")
def run_memo_analysis_tool(
    request: Request,
    company_id: str,
    tool_name: str,
    response: Response,
) -> dict:
    _require_permission(request, "tasks:action")
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
    request: Request,
    company_id: str,
    artifact_name: str,
    patch: dict,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.patch_artifact(company_id, artifact_name, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-analysis/risks/{risk_id}/refine")
def refine_memo_analysis_risk(
    request: Request,
    company_id: str,
    risk_id: str,
    body: MemoRiskRefineRequest | None = None,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    payload = body or MemoRiskRefineRequest()
    try:
        return serena_analysis.refine_risk(
            company_id,
            risk_id,
            framing=payload.framing,
            analyst_note=payload.analyst_note or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/companies/{company_id}/memo-analysis/research-tasks/{task_id}")
def patch_memo_analysis_research_task(
    request: Request,
    company_id: str,
    task_id: str,
    patch: dict,
) -> dict:
    _require_permission(request, "memo:edit")
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
def run_memo_analysis_research_task(request: Request, company_id: str, task_id: str) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.start_research_task_job(company_id, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/memo-analysis/research-tasks/run-selected",
    status_code=202,
)
def run_selected_memo_analysis_research_tasks(
    request: Request,
    company_id: str,
    retry_failed: bool = True,
) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.start_selected_research_task_jobs(
            company_id,
            retry_failed=retry_failed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/memo-analysis/research-tasks/{task_id}/cancel"
)
def cancel_memo_analysis_research_task(request: Request, company_id: str, task_id: str) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.cancel_research_task_job(company_id, task_id)
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
def approve_memo_analysis(request: Request, company_id: str) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return serena_analysis.approve(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/memo-editor")
def get_memo_editor(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        state = memo_editor_store.get_state(company_id, create=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if state is None:
        raise HTTPException(status_code=404, detail="Memo editor not found")
    return state


@router.patch("/companies/{company_id}/memo-editor/sections/{section_id}/cards/{card_id}")
def patch_memo_editor_card(
    request: Request,
    company_id: str,
    section_id: str,
    card_id: str,
    patch: MemoEditorCardPatch,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.patch_card(
            company_id,
            section_id,
            card_id,
            patch.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/sections/{section_id}/cards")
def add_memo_editor_card(
    request: Request,
    company_id: str,
    section_id: str,
    payload: MemoEditorCardCreate,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.add_card(
            company_id,
            section_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/companies/{company_id}/memo-editor/sections/{section_id}/cards/{card_id}"
)
def delete_memo_editor_card(
    request: Request,
    company_id: str,
    section_id: str,
    card_id: str,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.delete_card(company_id, section_id, card_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/sections/{section_id}/cards/reorder")
def reorder_memo_editor_cards(
    request: Request,
    company_id: str,
    section_id: str,
    payload: MemoEditorReorderRequest,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.reorder_cards(
            company_id, section_id, payload.ordered_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/sections/{section_id}/cards/{card_id}/move")
def move_memo_editor_card(
    request: Request,
    company_id: str,
    section_id: str,
    card_id: str,
    payload: MemoEditorMoveRequest,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.move_card(
            company_id,
            section_id,
            card_id,
            payload.direction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/companies/{company_id}/memo-editor/sections/{section_id}/cards/{card_id}/bullets/{bullet_id}"
)
def patch_memo_editor_bullet(
    request: Request,
    company_id: str,
    section_id: str,
    card_id: str,
    bullet_id: str,
    patch: MemoEditorBulletPatch,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.patch_bullet(
            company_id,
            section_id,
            card_id,
            bullet_id,
            patch.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/memo-editor/sections/{section_id}/cards/{card_id}/bullets/{bullet_id}/dive-deeper"
)
def add_memo_editor_dive_deeper(
    request: Request,
    company_id: str,
    section_id: str,
    card_id: str,
    bullet_id: str,
    payload: MemoEditorDiveRequest,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.add_dive_deeper(
            company_id,
            section_id,
            card_id,
            bullet_id,
            text=payload.text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/conclusion/select")
def select_memo_editor_conclusion(
    request: Request,
    company_id: str,
    payload: MemoEditorConclusionRequest,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.select_conclusion(company_id, payload.conclusion_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/sections/{section_id}/rerun")
def request_memo_editor_section_rerun(request: Request, company_id: str, section_id: str) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.request_section_rerun(company_id, section_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/companies/{company_id}/memo-editor/appendix/{block_id}")
def patch_memo_editor_appendix_block(
    request: Request,
    company_id: str,
    block_id: str,
    patch: MemoEditorAppendixPatch,
) -> dict:
    _require_permission(request, "memo:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.patch_appendix_block(
            company_id,
            block_id,
            patch.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/memo-editor/export-projection")
def get_memo_editor_export_projection(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.export_projection(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/export-projection")
def post_memo_editor_export_projection(request: Request, company_id: str) -> dict:
    _require_permission(request, "memo:export")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.export_projection(company_id, record_attempt=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/memo-editor/history")
def get_memo_editor_history(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.history(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/memo-editor/history/{revision_id}")
def get_memo_editor_revision(company_id: str, revision_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return memo_editor_store.get_revision(company_id, revision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/companies/{company_id}/memo-editor/tasks", status_code=201)
def create_memo_editor_task(
    company_id: str,
    payload: MemoEditorTaskCreate,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    try:
        return memo_editor_store.create_task(
            company_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/companies/{company_id}/memo-editor/tasks/{task_id}")
def patch_memo_editor_task(
    company_id: str,
    task_id: str,
    patch: MemoEditorTaskPatch,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "tasks:action")
    try:
        return memo_editor_store.update_task(
            company_id,
            task_id,
            patch.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "unknown memo task" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/companies/{company_id}/news-feed")
def get_company_news_feed(
    company_id: str,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    lang: str | None = None,
) -> dict:
    try:
        return context_store.company_news(
            company_id,
            category=category,
            tag=tag,
            search=search,
            lang=lang,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/companies/{company_id}/industry-view")
def get_company_industry_view(company_id: str) -> dict:
    try:
        return context_store.industry_view(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/companies/{company_id}/competitors/{competitor_id}")
def get_company_competitor_detail(company_id: str, competitor_id: str) -> dict:
    try:
        return context_store.competitor_detail(company_id, competitor_id)
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "unknown" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/companies/{company_id}/documents")
def get_company_documents(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    reports = [_report_summary(r) for r in storage.list_reports()]
    return evidence_store.list_documents(company_id, reports=reports)


@router.patch("/companies/{company_id}/documents/{backend}/{document_id}")
def patch_company_document_metadata(
    company_id: str,
    backend: str,
    document_id: str,
    patch: DocumentMetadataPatch,
    request: Request,
) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "sources:edit")
    try:
        return evidence_store.update_document_metadata(
            company_id,
            backend,
            document_id,
            patch.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post("/companies/{company_id}/documents/{backend}/{document_id}/use-in-report")
def post_company_document_use_in_report(
    company_id: str,
    backend: str,
    document_id: str,
    patch: UseInReportPatch,
    request: Request,
) -> dict:
    _require_permission(request, "sources:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return evidence_store.set_use_in_report(
            company_id,
            backend,
            document_id,
            patch.use_in_report,
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/intake/unresolved")
def get_unresolved_intake(company_id: str | None = None) -> list[dict]:
    return evidence_store.list_unresolved_intake(company_id=company_id)


@router.get("/companies/{company_id}/files")
def get_files(company_id: str) -> list[dict]:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return files_store.list_files(company_id)


@router.post("/companies/{company_id}/files", status_code=201)
async def post_file(
    request: Request,
    company_id: str,
    file: UploadFile = File(...),
    label: str | None = Form(None),
    language: str = Form("en"),
) -> dict:
    _require_permission(request, "sources:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    data = await _read_upload_bounded(
        file, max_bytes=files_store.MAX_FILE_BYTES
    )
    try:
        record = files_store.upload_file(
            company_id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
            label=label,
            language=language,
        )
        category = evidence_store.normalize_document_category(
            None,
            filename=record.get("filename"),
            kind=record.get("kind"),
            backend="document_library",
        )
        updated = files_store.update_record(
            company_id,
            record["id"],
            document_category=category,
            source_class="unknown/pending",
            assignment_status="assigned",
            assignment_confidence="high",
            provenance={
                "title": label or record.get("filename"),
                "file": record.get("stored_name"),
                "uploaded_at": record.get("uploaded_at"),
                "language": language,
                "source_class": "unknown/pending",
                "confidence": "pending",
                "status": "pending",
            },
        )
        return updated or record
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
def delete_file(company_id: str, file_id: str, request: Request) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "documents:delete")
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


@router.get("/companies/{company_id}/evidence-matrix")
def get_company_evidence_matrix(company_id: str) -> dict:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return evidence_matrix.build_company_evidence_matrix(company_id)


@router.post("/companies/{company_id}/research-files", status_code=201)
async def post_research_file(
    request: Request,
    company_id: str,
    file: UploadFile = File(...),
    label: str | None = Form(None),
    folder_name: str | None = Form(None),
    folder_id: str | None = Form(None),
) -> dict:
    _require_permission(request, "sources:edit")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    # Folder handshake: the first member sends folder_name only and the
    # server mints the id; later members echo it back so the whole batch
    # groups under one folder.
    if folder_id and not research_store.FOLDER_ID_RE.match(folder_id):
        raise HTTPException(status_code=400, detail="Invalid folder id")
    if folder_name and not folder_id:
        folder_id = research_store.mint_folder_id()
    data = await _read_upload_bounded(
        file,
        max_bytes=research_store.MAX_FILE_BYTES,
    )
    try:
        record = research_store.upload_file(
            company_id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
            label=label,
            folder_id=folder_id,
            folder_name=folder_name,
        )
        category = evidence_store.normalize_document_category(
            None,
            filename=record.get("filename"),
            kind=record.get("kind"),
            backend="background_documents",
        )
        updated = research_store.update_record(
            company_id,
            record["id"],
            document_category=category,
            source_class="unknown/pending",
            assignment_status="assigned",
            assignment_confidence="high",
            provenance={
                "title": label or record.get("filename"),
                "file": record.get("stored_name"),
                "uploaded_at": record.get("uploaded_at"),
                "source_class": "unknown/pending",
                "confidence": "pending",
                "status": "pending",
            },
        )
        return updated or record
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
def delete_research_file(company_id: str, file_id: str, request: Request) -> None:
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    _require_permission(request, "documents:delete")
    if not research_store.delete_file(company_id, file_id):
        raise HTTPException(status_code=404, detail="File not found")


def _run_research_summary_job(
    company_id: str,
    file_id: str,
    cancel_key: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Background worker for a research-library quick-summary job. Streams
    progress events to a JSONL file (visible in the AI Tasks rail) and
    persists the final summary onto the file record."""
    from pathlib import Path

    started = time.monotonic()
    progress_path = research_store.quick_summary_progress_path(
        company_id, file_id
    )
    cancel_fields = {
        "kind": "research_summary",
        "company_id": company_id,
        "file_id": file_id,
    }
    if _honor_research_cancel(
        progress_path,
        cancel_event,
        reason="Research summary cancelled",
        **cancel_fields,
    ):
        _clear_research_cancel_event(cancel_key or "", cancel_event)
        return
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
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="Research summary cancelled",
            **cancel_fields,
        ):
            return
        record, path = found
        kind = record.get("kind") or "text"
        filename = record.get("filename") or Path(path).name
        source_chunks = _extract_text_chunks_from_file(str(path))
        if _pdf_needs_ocr(str(path), source_chunks):
            ocr_chunks = _ocr_extract_text_chunks_from_file(str(path))
            if ocr_chunks:
                source_chunks = ocr_chunks
        summary = claude_runner.run_quick_summary(
            source_path=path,
            work_dir=path.parent,
            kind=kind,
            hint_title=record.get("label") or record.get("filename"),
            progress=progress,
            cancel_event=cancel_event,
        )
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="Research summary cancelled",
            **cancel_fields,
        ):
            return
        if "error" in summary:
            progress.emit("error", error=summary["error"])
            return
        stored_source_chunks = _source_chunks_for_storage(
            source_chunks,
            item_id=file_id,
            filename=filename,
        )
        source_traces = _normalize_source_traces(
            summary.get("source_traces"),
            stored_source_chunks,
            item_id=file_id,
            filename=filename,
        )
        summary = {
            **summary,
            "source_chunks": stored_source_chunks,
            "source_chunk_count": len(stored_source_chunks),
            "source_traces": source_traces,
            "source_trace_count": len(source_traces),
        }
        summary = research_eval.with_observability_defaults(
            summary,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        research_store.update_record(
            company_id, file_id, quick_summary=summary
        )
        progress.emit(
            "done",
            summary=summary,
            source_trace_count=len(source_traces),
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Job crashed: {type(exc).__name__}: {exc}"
        )
    finally:
        _clear_research_cancel_event(cancel_key or "", cancel_event)


@router.post(
    "/companies/{company_id}/research-files/{file_id}/summary",
    status_code=202,
)
def post_research_file_summary(request: Request, company_id: str, file_id: str) -> dict:
    """Kick off the quick-summary job in the background.

    Returns immediately with the job descriptor (stream_url, log_url) —
    the actual Claude run takes 5–30s and progresses via the AI Tasks
    rail. The summary lands on the file's index record when done; the
    FE polls the file list to detect completion (and the user can click
    the rail entry to watch live).
    """
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")

    progress_path = research_store.quick_summary_progress_path(
        company_id, file_id
    )
    with _job_start_lock(f"research_summary:{company_id}/{file_id}"):
        state = _scan_progress_state(progress_path)
        if _progress_state_in_flight(state):
            return {
                "kind": "research_summary",
                "company_id": company_id,
                "file_id": file_id,
                "status": "already_running",
                "stream_url": (
                    f"/api/companies/{company_id}/research-files/{file_id}/summary/stream"
                ),
                "log_url": (
                    f"/api/jobs/log?path=research_summary:{company_id}/{file_id}"
                ),
            }
        if state.get("exists") and not state.get("terminated"):
            _supersede_progress_file(
                progress_path,
                reason="superseded stale research summary progress",
            )

        # Reset any prior summary so the UI shows the new run cleanly.
        research_store.update_record(company_id, file_id, quick_summary=None)

        cancel_key = _research_cancel_key(
            "research_summary", company_id, file_id
        )
        cancel_event = _start_research_cancel_event(cancel_key)
        threading.Thread(
            target=_run_research_summary_job,
            args=(company_id, file_id, cancel_key, cancel_event),
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


@router.post(
    "/companies/{company_id}/research-files/{file_id}/summary/cancel",
)
def cancel_research_file_summary(request: Request, company_id: str, file_id: str) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    cancel_key = _research_cancel_key(
        "research_summary", company_id, file_id
    )
    signal_sent = _request_research_cancel(cancel_key)
    progress_path = research_store.quick_summary_progress_path(
        company_id, file_id
    )
    state = _emit_cancelled_progress(
        progress_path,
        reason="Research summary cancelled",
        kind="research_summary",
        company_id=company_id,
        file_id=file_id,
    )
    return {
        "kind": "research_summary",
        "company_id": company_id,
        "file_id": file_id,
        "status": "cancelled",
        "signal_sent": signal_sent,
        "terminal_type": state.get("terminal_type"),
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
def delete_research_file_summary(request: Request, company_id: str, file_id: str) -> None:
    _require_permission(request, "documents:delete")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    research_store.update_record(company_id, file_id, quick_summary=None)


def _resolve_analysis_target(
    company_id: str, target_id: str
) -> tuple[list[dict], str] | None:
    """Resolve an analysis target into ``(sources, display_name)``.

    A ``fld``-prefixed id resolves to the folder's member files (analyzed
    as one correlated unit); anything else resolves to a single file.
    Returns ``None`` when the target does not exist / has no members.
    """
    if research_store.FOLDER_ID_RE.match(target_id):
        members = research_store.folder_members(company_id, target_id)
        if not members:
            return None
        sources = []
        folder_name = ""
        for member in members:
            found = research_store.get_file(company_id, member["id"])
            if found is None:
                continue
            record, path = found
            folder_name = record.get("folder_name") or folder_name
            sources.append(
                {
                    "path": path,
                    "filename": record.get("filename"),
                    "kind": record.get("kind") or "text",
                    "uploaded_at": record.get("uploaded_at"),
                    "label": record.get("label"),
                }
            )
        if not sources:
            return None
        return sources, (folder_name or "folder")
    found = research_store.get_file(company_id, target_id)
    if found is None:
        return None
    record, path = found
    source = {
        "path": path,
        "filename": record.get("filename"),
        "kind": record.get("kind") or "text",
        "uploaded_at": record.get("uploaded_at"),
        "label": record.get("label"),
    }
    from pathlib import Path as _Path

    return [source], _Path(record.get("filename") or "document").stem


def _run_research_analysis_job(
    company_id: str,
    target_id: str,
    cancel_key: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Background worker: analyze one research file or uploaded folder and
    persist the result as an indexed `<name>_analysis.md` research file
    (which the memo pipeline then reads instead of the raw documents)."""
    progress_path = research_store.analysis_progress_path(company_id, target_id)
    cancel_fields = {
        "kind": "research_analysis",
        "company_id": company_id,
        "file_id": target_id,
    }
    if _honor_research_cancel(
        progress_path,
        cancel_event,
        reason="Document analysis cancelled",
        **cancel_fields,
    ):
        _clear_research_cancel_event(cancel_key or "", cancel_event)
        return
    progress = job_progress.ProgressLog(progress_path)
    try:
        resolved = _resolve_analysis_target(company_id, target_id)
        company_name = (storage.get_company(company_id) or {}).get(
            "name"
        ) or company_id
        display_name = resolved[1] if resolved else target_id
        progress.emit(
            "job_init",
            kind="research_analysis",
            title=display_name,
            subtitle=company_name,
            company_id=company_id,
            file_id=target_id,
        )
        progress.emit(
            "stage", stage="starting", message="Starting document analysis"
        )
        if resolved is None:
            progress.emit("error", error="Analysis target not found")
            return
        sources, display_name = resolved
        result = claude_runner.run_research_analysis(
            sources=sources,
            work_dir=sources[0]["path"].parent,
            hint_title=display_name,
            progress=progress,
            timeout_sec=claude_runner.research_analysis_timeout_sec(
                len(sources)
            ),
            cancel_event=cancel_event,
        )
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="Document analysis cancelled",
            **cancel_fields,
        ):
            return
        if "error" in result:
            progress.emit("error", error=result["error"])
            return
        # Reanalyze semantics: the previous analysis is replaced wholesale.
        prior = research_store.analysis_entry_for(company_id, target_id)
        if prior and prior.get("id"):
            research_store.delete_file(company_id, str(prior["id"]))
        analysis_record = research_store.upload_file(
            company_id,
            filename=f"{display_name}_analysis.md",
            content_type="text/markdown",
            data=str(result.get("analysis_md") or "").encode("utf-8"),
        )
        research_store.update_record(
            company_id,
            analysis_record["id"],
            analysis_of=target_id,
            source_class="internal note",
            document_category=evidence_store.normalize_document_category(
                None,
                filename=analysis_record.get("filename"),
                kind="text",
                backend="background_documents",
            ),
            provenance={
                "title": f"Distilled analysis of {display_name}",
                "file": analysis_record.get("stored_name"),
                "uploaded_at": analysis_record.get("uploaded_at"),
                "source_class": "internal note",
                "confidence": "high",
                "status": "generated",
            },
        )
        if not research_store.FOLDER_ID_RE.match(target_id):
            research_store.update_record(
                company_id, target_id, analysis_file_id=analysis_record["id"]
            )
        progress.emit(
            "done",
            analysis_file_id=analysis_record["id"],
            claude_cost_usd=result.get("claude_cost_usd"),
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit(
            "error", error=f"Job crashed: {type(exc).__name__}: {exc}"
        )
    finally:
        _clear_research_cancel_event(cancel_key or "", cancel_event)


@router.post(
    "/companies/{company_id}/research-files/{file_id}/analysis",
    status_code=202,
)
def post_research_file_analysis(
    request: Request, company_id: str, file_id: str
) -> dict:
    """Analyze one research file — or one uploaded folder (fld-prefixed
    id) as a single correlated unit. Writes a persistent
    `<name>_analysis.md` next to the documents; future memo runs read the
    distilled analysis instead of reprocessing the raw files."""
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.FOLDER_ID_RE.match(file_id):
        if not research_store.folder_members(company_id, file_id):
            raise HTTPException(status_code=404, detail="Folder not found")
    else:
        found = research_store.get_file(company_id, file_id)
        if found is None:
            raise HTTPException(status_code=404, detail="File not found")
        if found[0].get("analysis_of"):
            raise HTTPException(
                status_code=400,
                detail="This file is itself an analysis — analyze the source instead",
            )

    progress_path = research_store.analysis_progress_path(company_id, file_id)
    stream_url = (
        f"/api/companies/{company_id}/research-files/{file_id}/analysis/stream"
    )
    log_url = f"/api/jobs/log?path=research_analysis:{company_id}/{file_id}"
    with _job_start_lock(f"research_analysis:{company_id}/{file_id}"):
        state = _scan_progress_state(progress_path)
        if _progress_state_in_flight(state):
            return {
                "kind": "research_analysis",
                "company_id": company_id,
                "file_id": file_id,
                "status": "already_running",
                "stream_url": stream_url,
                "log_url": log_url,
            }
        if state.get("exists") and not state.get("terminated"):
            _supersede_progress_file(
                progress_path,
                reason="superseded stale research analysis progress",
            )
        cancel_key = _research_cancel_key(
            "research_analysis", company_id, file_id
        )
        cancel_event = _start_research_cancel_event(cancel_key)
        threading.Thread(
            target=_run_research_analysis_job,
            args=(company_id, file_id, cancel_key, cancel_event),
            name=f"research-analysis-{company_id}-{file_id}",
            daemon=True,
        ).start()
    return {
        "kind": "research_analysis",
        "company_id": company_id,
        "file_id": file_id,
        "stream_url": stream_url,
        "log_url": log_url,
    }


@router.post(
    "/companies/{company_id}/research-files/{file_id}/analysis/cancel",
)
def cancel_research_file_analysis(
    request: Request, company_id: str, file_id: str
) -> dict:
    _require_permission(request, "tasks:action")
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    cancel_key = _research_cancel_key(
        "research_analysis", company_id, file_id
    )
    signal_sent = _request_research_cancel(cancel_key)
    progress_path = research_store.analysis_progress_path(company_id, file_id)
    state = _emit_cancelled_progress(
        progress_path,
        reason="Document analysis cancelled",
        kind="research_analysis",
        company_id=company_id,
        file_id=file_id,
    )
    return {
        "kind": "research_analysis",
        "company_id": company_id,
        "file_id": file_id,
        "status": "cancelled",
        "signal_sent": signal_sent,
        "terminal_type": state.get("terminal_type"),
    }


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


# Striped locks serializing the check-then-spawn section of every job-start
# endpoint. Without this, two concurrent POSTs can both observe "not in
# flight" and spawn duplicate background workers truncating/writing the same
# progress JSONL. Striping (hash of the job key onto a fixed pool) keeps the
# lock table bounded regardless of how many distinct job keys exist; a hash
# collision just briefly serializes two unrelated job starts, which is
# harmless because the critical section is a quick file scan + Thread.start().
_JOB_START_LOCKS = [threading.Lock() for _ in range(64)]


def _job_start_lock(key: str) -> threading.Lock:
    return _JOB_START_LOCKS[hash(key) % len(_JOB_START_LOCKS)]


def _scan_progress_state(path: "Path") -> dict:
    return job_progress.scan_progress_state(path)


def _progress_idle_seconds(state: dict) -> float | None:
    return job_progress.progress_idle_seconds(state)


def _progress_path_recent(path: "Path", *, max_idle_seconds: int) -> bool:
    return job_progress.progress_path_recent(
        path, max_idle_seconds=max_idle_seconds
    )


def _progress_state_in_flight(
    state: dict,
    *,
    max_idle_seconds: int = ACTIVE_JOB_MAX_IDLE_SECONDS,
    schema_retry_grace_seconds: float | None = None,
) -> bool:
    kwargs: dict = {"max_idle_seconds": max_idle_seconds}
    if schema_retry_grace_seconds is not None:
        kwargs["schema_retry_grace_seconds"] = schema_retry_grace_seconds
    return job_progress.progress_state_in_flight(state, **kwargs)


def _scan_active_progress_state(path: "Path") -> dict | None:
    return job_progress.scan_active_progress_state(
        path, max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
    )


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
    request: Request,
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
    _require_permission(request, "tasks:action")
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
    with _job_start_lock(f"summary:{company_id}/{file_id}"):
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
    company_names = storage.company_names()
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
        subtitle = state.get("subtitle") or company_names.get(company_id, company_id)
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
        "elapsed_ms": state.get("elapsed_ms"),
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
        "thread_count": state.get("thread_count"),
        "thread_done_count": state.get("thread_done_count"),
        "thread_failed_count": state.get("thread_failed_count"),
        "open_thread_count": state.get("open_thread_count"),
        "threads": state.get("threads"),
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


def _stock_tracker_progress_path(key: str):
    tracker_id, run_id = key.split("/", 1)
    return stock_research.tracker_progress_path(tracker_id, run_id)


def _stock_aggregate_progress_path(key: str):
    return stock_research.aggregate_progress_path(key)


def _stock_strategy_progress_path(key: str):
    return stock_research.strategy_map_progress_path(key)


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
    "research_analysis": lambda key: research_store.analysis_progress_path(
        key.split("/", 1)[0], key.split("/", 1)[1]
    ),
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
    # Task-history replay: the key is a ledger row id; the ledger recorded
    # the stream path when the job finished, so no per-kind mapping needed.
    "history": lambda key: job_history.resolve_log_path(key),
    "stock_tracker": _stock_tracker_progress_path,
    "stock_aggregate": _stock_aggregate_progress_path,
    "stock_strategy": _stock_strategy_progress_path,
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


def _stock_tracker_kind_records():
    """Yield active Stock Research tracker jobs for the active-jobs rail."""
    for tracker_id, run_id, jsonl_path in stock_research.iter_tracker_progress_paths():
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        tracker = stock_research.get_tracker(tracker_id) or {}
        yield {
            "kind": state.get("kind") or "stock_tracker",
            "title": state.get("title") or "Stock tracker run",
            "subtitle": state.get("subtitle")
            or tracker.get("display_name")
            or tracker_id,
            "stream_url": (
                f"/api/stock-research/trackers/{tracker_id}/runs/{run_id}/stream"
            ),
            "log_url": f"/api/jobs/log?path=stock_tracker:{tracker_id}/{run_id}",
            "primary_route": {"name": "stock-research", "query": {"tab": "runs"}},
            "tracker_id": tracker_id,
            "run_id": run_id,
            **_common_state_fields(state),
        }


def _stock_aggregate_kind_records():
    """Yield active Stock Research weekly aggregate jobs."""
    for period_id, jsonl_path in stock_research.iter_aggregate_progress_paths():
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        yield {
            "kind": state.get("kind") or "stock_aggregate",
            "title": state.get("title") or "Stock Research weekly aggregate",
            "subtitle": state.get("subtitle") or period_id,
            "stream_url": f"/api/stock-research/aggregates/{period_id}/stream",
            "log_url": f"/api/jobs/log?path=stock_aggregate:{period_id}",
            "primary_route": {"name": "stock-research", "query": {"tab": "aggregate"}},
            "period_id": period_id,
            **_common_state_fields(state),
        }


def _stock_strategy_kind_records():
    """Yield active Stock Research strategy-map jobs."""
    for period_id, jsonl_path in stock_research.iter_strategy_progress_paths():
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        yield {
            "kind": state.get("kind") or "stock_strategy",
            "title": state.get("title") or "Stock Research strategy map",
            "subtitle": state.get("subtitle") or period_id,
            "stream_url": f"/api/stock-research/strategy-maps/{period_id}/stream",
            "log_url": f"/api/jobs/log?path=stock_strategy:{period_id}",
            "primary_route": {"name": "stock-research", "query": {"tab": "strategy"}},
            "period_id": period_id,
            **_common_state_fields(state),
        }


def _research_summary_kind_records():
    """Yield active-jobs rail entries for every quick-summary JSONL on disk."""
    if not research_store.RESEARCH_ROOT.exists():
        return
    company_names = storage.company_names()
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
        subtitle = state.get("subtitle") or company_names.get(company_id, company_id)
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


def _research_analysis_kind_records():
    """Yield active-jobs rail entries for document-analysis JSONLs.

    The target id is a file id or a ``fld``-prefixed folder id; folder
    titles fall back to the members' folder_name."""
    if not research_store.RESEARCH_ROOT.exists():
        return
    company_names = storage.company_names()
    suffix = "__analysis.progress.jsonl"
    for jsonl_path in research_store.RESEARCH_ROOT.glob(f"*/*{suffix}"):
        company_id = jsonl_path.parent.name
        name = jsonl_path.name
        if not name.endswith(suffix):
            continue
        target_id = name[: -len(suffix)]
        state = _scan_active_progress_state(jsonl_path)
        if state is None:
            continue
        title = state.get("title")
        if not title:
            if research_store.FOLDER_ID_RE.match(target_id):
                members = research_store.folder_members(company_id, target_id)
                title = (
                    members[0].get("folder_name") if members else None
                ) or "Document analysis"
            else:
                record_tuple = research_store.get_file(company_id, target_id)
                record = record_tuple[0] if record_tuple else None
                title = (
                    record and (record.get("label") or record.get("filename"))
                ) or "Document analysis"
        yield {
            "kind": state.get("kind") or "research_analysis",
            "title": title,
            "subtitle": state.get("subtitle")
            or company_names.get(company_id, company_id),
            "stream_url": (
                f"/api/companies/{company_id}/research-files/{target_id}/analysis/stream"
            ),
            "log_url": (
                f"/api/jobs/log?path=research_analysis:{company_id}/{target_id}"
            ),
            "primary_route": {
                "name": "research",
                "params": {"companyId": company_id},
            },
            "company_id": company_id,
            "file_id": target_id,
            **_common_state_fields(state),
        }


def _stale_research_progress_reason(path: Path) -> str:
    idle = job_progress.progress_path_idle_seconds(path)
    if idle is None:
        idle = job_progress.progress_idle_seconds(_scan_progress_state(path))
    if idle is None:
        return "Recovered interrupted run: progress log is stale"
    return (
        "Recovered interrupted run: progress log has been idle for "
        f"{int(idle)} seconds"
    )


def _recover_stale_research_jobs() -> int:
    recovered = 0
    if research_store.RESEARCH_ROOT.exists():
        for jsonl_path in research_store.RESEARCH_ROOT.glob(
            "*/*__quick_summary.progress.jsonl"
        ):
            state = _scan_progress_state(jsonl_path)
            if state.get("terminated"):
                continue
            if _progress_state_in_flight(state) and _progress_path_recent(
                jsonl_path, max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
            ):
                continue
            company_id = jsonl_path.parent.name
            file_id = jsonl_path.name.removesuffix(
                "__quick_summary.progress.jsonl"
            )
            job_progress.ProgressLog(jsonl_path, truncate=False).emit(
                "recovered",
                recovered=True,
                error=_stale_research_progress_reason(jsonl_path),
                kind="research_summary",
                company_id=company_id,
                file_id=file_id,
            )
            recovered += 1
        for jsonl_path in research_store.RESEARCH_ROOT.glob(
            "*/*__analysis.progress.jsonl"
        ):
            state = _scan_progress_state(jsonl_path)
            if state.get("terminated"):
                continue
            if _progress_state_in_flight(state) and _progress_path_recent(
                jsonl_path, max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
            ):
                continue
            job_progress.ProgressLog(jsonl_path, truncate=False).emit(
                "recovered",
                recovered=True,
                error=_stale_research_progress_reason(jsonl_path),
                kind="research_analysis",
                company_id=jsonl_path.parent.name,
                file_id=jsonl_path.name.removesuffix(
                    "__analysis.progress.jsonl"
                ),
            )
            recovered += 1

    analysis_dir = external_store._kind_dir("external_research") / "analysis"
    if analysis_dir.exists():
        for jsonl_path in analysis_dir.glob("*__analysis.progress.jsonl"):
            state = _scan_progress_state(jsonl_path)
            if state.get("terminated"):
                continue
            if _progress_state_in_flight(state) and _progress_path_recent(
                jsonl_path, max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS
            ):
                continue
            item_id = jsonl_path.name.removesuffix("__analysis.progress.jsonl")
            message = _stale_research_progress_reason(jsonl_path)
            item = external_store.get_item("external_research", item_id)
            if item is not None and item.get("status") in {
                "queued",
                "extracting",
                "analyzing",
            }:
                external_store.update_item(
                    "external_research",
                    item_id,
                    status="ready",
                    analysis_error=message,
                )
            job_progress.ProgressLog(jsonl_path, truncate=False).emit(
                "recovered",
                recovered=True,
                error=message,
                kind="external_research",
                item_id=item_id,
            )
            recovered += 1
    return recovered


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
            "report_ready": bool(state.get("report_ready")),
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
    company_names = storage.company_names()
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
            "subtitle": state.get("subtitle")
            or company_names.get(company_id, company_id),
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


def recover_stale_jobs() -> None:
    """Mark orphaned/stale Claude jobs terminal. Formerly run inline on every
    /api/jobs/active poll — where it walked large trees under a global lock and
    was the main cause of the endpoint's overload (and the 503s). Now driven off
    the request path: once at startup and periodically by a background thread.
    """
    try:
        serena_analysis.recover_stale_runs(max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS)
    except Exception:
        logger.exception("failed to recover stale serena jobs")
    try:
        _recover_stale_research_jobs()
    except Exception:
        logger.exception("failed to recover stale research jobs")
    try:
        stock_research.recover_stale_runs(max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS)
    except Exception:
        logger.exception("failed to recover stale stock research jobs")


_RECOVERY_INTERVAL_SECONDS = 60.0
_recovery_thread_started = False
_recovery_thread_lock = threading.Lock()


def start_stale_job_recovery() -> None:
    """Run one recovery sweep now, then keep sweeping in a daemon thread.
    Idempotent — safe to call from the FastAPI startup hook."""
    global _recovery_thread_started
    with _recovery_thread_lock:
        if _recovery_thread_started:
            return
        _recovery_thread_started = True

    recover_stale_jobs()

    def _loop() -> None:
        while True:
            time.sleep(_RECOVERY_INTERVAL_SECONDS)
            try:
                recover_stale_jobs()
            except Exception:
                logger.exception("background stale-job recovery failed")

    threading.Thread(
        target=_loop, name="stale-job-recovery", daemon=True
    ).start()


# Short TTL cache so concurrent ActiveJobsRail pollers share one filesystem
# scan instead of each re-walking the (large) data tree.
_ACTIVE_JOBS_TTL_SECONDS = 3.0
_active_jobs_cache: tuple[float, list[dict]] | None = None
_active_jobs_lock = threading.Lock()


def _collect_active_jobs() -> list[dict]:
    out: list[dict] = []
    for source in (
        _summary_kind_records(),
        _search_kind_records(),
        _pdf_translation_kind_records(),
        _external_research_analysis_kind_records(),
        _memo_kind_records(),
        _hormuz_appendix_kind_records(),
        _research_summary_kind_records(),
        _research_analysis_kind_records(),
        _console_kind_records(),
        _serena_research_task_kind_records(),
        _serena_analysis_tool_kind_records(),
        _company_regen_all_kind_records(),
        _public_snapshot_bulk_kind_records(),
        _public_snapshot_kind_records(),
        _weekly_stocks_kind_records(),
        _stock_tracker_kind_records(),
        _stock_aggregate_kind_records(),
        _stock_strategy_kind_records(),
    ):
        for rec in source:
            if rec.get("terminated"):
                continue
            out.append(rec)
    out.sort(key=lambda j: j.get("started_at") or "", reverse=True)
    return out


@router.get("/jobs/active")
def get_active_jobs() -> list[dict]:
    """All in-flight Claude tasks across every kind. Powers ActiveJobsRail.

    Recovery of stale runs is NOT done here anymore (see
    ``start_stale_job_recovery``); this endpoint only reads current state,
    behind a short TTL cache so bursts of pollers coalesce.
    """
    global _active_jobs_cache
    now = time.time()
    with _active_jobs_lock:
        if _active_jobs_cache is not None and (
            now - _active_jobs_cache[0] < _ACTIVE_JOBS_TTL_SECONDS
        ):
            return _active_jobs_cache[1]
    data = _collect_active_jobs()
    with _active_jobs_lock:
        _active_jobs_cache = (now, data)
    return data


@router.get("/jobs/history")
def get_job_history(limit: int = 30) -> list[dict]:
    """Recently finished AI tasks, newest first — the Task history panel.

    Rows come from the terminal-event ledger (``job_history``). Memo rows
    are enriched from the report record (status, the two completion
    timestamps, final cost) and deep-link to the report; every row with a
    surviving stream file carries a ``log_url`` for transcript replay.
    """
    out: list[dict] = []
    for row in job_history.list_history(limit=limit):
        entry = dict(row)
        kind = str(row.get("kind") or "")
        report_id = row.get("report_id")
        if kind in ("memo", "hormuz") and report_id:
            entry["log_url"] = f"/api/jobs/log?path=memo:{report_id}"
            report = storage.get_report(str(report_id)) or {}
            if report:
                entry["status"] = report.get("status")
                entry["report_ready_at"] = report.get("report_ready_at")
                entry["run_finished_at"] = report.get("run_finished_at")
                if report.get("claude_cost_usd") is not None:
                    entry["claude_cost_usd"] = report.get("claude_cost_usd")
            entry["primary_route"] = {
                "name": "report",
                "params": {"reportId": report_id},
            }
        elif row.get("log_path"):
            entry["log_url"] = f"/api/jobs/log?path=history:{row.get('id')}"
        out.append(entry)
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
    "/companies/{company_id}/research-files/{file_id}/analysis/stream"
)
async def stream_research_file_analysis_progress(
    company_id: str, file_id: str
) -> "StreamingResponse":
    """SSE stream for a document-analysis job (file or folder target)."""
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if research_store.FOLDER_ID_RE.match(file_id):
        if not research_store.folder_members(company_id, file_id):
            raise HTTPException(status_code=404, detail="Folder not found")
    elif research_store.get_file(company_id, file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    return _research_progress_sse(
        research_store.analysis_progress_path(company_id, file_id)
    )


def _research_progress_sse(progress_path) -> "StreamingResponse":
    """SSE replay-and-tail of one research progress JSONL (shared by the
    summary and analysis streams)."""
    import asyncio
    import json as _json
    import time

    from fastapi.responses import StreamingResponse

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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
def delete_file_summary(request: Request, company_id: str, file_id: str) -> None:
    _require_permission(request, "documents:delete")
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
def post_thread(request: Request, company_id: str, payload: ThreadIn) -> dict:
    _require_permission(request, "sources:edit")
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


class ExternalResearchPromoteIn(BaseModel):
    company_id: str


@router.post("/external/link-preview")
def post_link_preview(request: Request, payload: LinkPreviewIn) -> dict:
    """Fetch a URL and return its OpenGraph-style preview without saving.

    Used by the Submit-a-link tool to show the user what they're about to
    accept before kicking off the analysis pipeline.
    """
    _require_permission(request, "sources:edit")
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
def post_news(request: Request, payload: NewsCreateIn) -> dict:
    _require_permission(request, "sources:edit")
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    dedupe_key = evidence_store.dedupe_key("news", {"url": url})
    duplicate = evidence_store.find_duplicate_intake(
        "news",
        dedupe_key,
        url=url,
    )
    if duplicate is not None:
        return {
            **_external_item_response(duplicate),
            "dedupe_status": "duplicate",
            "idempotent": True,
        }
    item_id = external_store.new_id()
    annotation = evidence_store.annotate_intake_record(
        kind="news",
        item_id=item_id,
        payload={"url": url, "title": url},
    )
    item = external_store.write_item(
        "news",
        {
            "id": item_id,
            "kind": "news",
            "status": "queued",
            "source_url": url,
            "title": url,
            **annotation,
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
def delete_news(item_id: str, request: Request) -> None:
    _require_permission(request, "documents:delete")
    if not external_store.delete_item("news", item_id):
        raise HTTPException(status_code=404, detail="News item not found")


@router.post("/external/news/{item_id}/retry")
def retry_news(request: Request, item_id: str) -> dict:
    """Re-run the analysis pipeline for a news item — useful when the
    initial run hit `analysis_error`.
    """
    _require_permission(request, "tasks:action")
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
        ocr_needed=False,
    )
    threading.Thread(
        target=_run_news_analysis, args=(item_id, url), daemon=True
    ).start()
    return external_store.get_item("news", item_id) or {}


# ---- External research ----


def _run_external_research_analysis(
    item_id: str,
    file_path: str,
    hint_title: str | None,
    cancel_key: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    started = time.monotonic()
    progress_path = _external_research_analysis_progress_path(item_id)
    cancel_fields = {
        "kind": "external_research",
        "item_id": item_id,
    }
    if _honor_research_cancel(
        progress_path,
        cancel_event,
        reason="External research analysis cancelled",
        **cancel_fields,
    ):
        _clear_research_cancel_event(cancel_key or "", cancel_event)
        return
    progress = job_progress.ProgressLog(
        progress_path
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
        source_chunks = _extract_text_chunks_from_file(file_path)
        if _pdf_needs_ocr(file_path, source_chunks):
            ocr_chunks = _ocr_extract_text_chunks_from_file(file_path)
            if ocr_chunks:
                source_chunks = ocr_chunks
            else:
                message = (
                    "OCR needed: this PDF appears to contain little or no "
                    "extractable text."
                )
                external_store.update_item(
                    "external_research",
                    item_id,
                    status="ocr_needed",
                    analysis_error=message,
                    ocr_needed=True,
                    source_chunk_count=len(source_chunks),
                )
                progress.emit(
                    "error",
                    error=message,
                    status="ocr_needed",
                    ocr_needed=True,
                )
                return
        text = _format_source_chunks_for_analysis(source_chunks)
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="External research analysis cancelled",
            **cancel_fields,
        ):
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error="Analysis cancelled",
            )
            return
        if not text:
            message = "Couldn't extract text from this file type."
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error=message,
                ocr_needed=False,
            )
            progress.emit("error", error=message)
            return
        progress.emit(
            "stage",
            stage="analyzing",
            message="Analyzing extracted text",
            raw_text_chars=len(text),
            source_chunk_count=len(source_chunks),
        )
        external_store.update_item(
            "external_research",
            item_id,
            status="analyzing",
            raw_text_chars=len(text),
            source_chunk_count=len(source_chunks),
            ocr_needed=False,
        )
        analysis = text_analysis.analyze(
            text,
            hint_title=hint_title,
            progress=progress,
            cancel_event=cancel_event,
        )
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="External research analysis cancelled",
            **cancel_fields,
        ):
            external_store.update_item(
                "external_research",
                item_id,
                status="ready",
                analysis_error="Analysis cancelled",
            )
            return
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
        filename = item.get("filename") or Path(file_path).name
        stored_source_chunks = _source_chunks_for_storage(
            source_chunks,
            item_id=item_id,
            filename=filename,
        )
        source_traces = _normalize_external_source_traces(
            analysis.get("source_traces"),
            stored_source_chunks,
            item_id=item_id,
            filename=filename,
        )
        observed_analysis = research_eval.with_observability_defaults(
            {
                **analysis,
                "source_chunks": stored_source_chunks,
                "source_traces": source_traces,
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        external_store.update_item(
            "external_research",
            item_id,
            status="ready",
            summary=observed_analysis.get("summary"),
            key_points=observed_analysis.get("key_points") or [],
            language=observed_analysis.get("language") or "other",
            translation=observed_analysis.get("translation"),
            title=(observed_analysis.get("title") or hint_title or "Untitled"),
            source_chunks=stored_source_chunks,
            source_chunk_count=len(stored_source_chunks),
            source_traces=source_traces,
            source_trace_count=len(source_traces),
            job_metrics=observed_analysis.get("job_metrics"),
            analyst_review_score=observed_analysis.get("analyst_review_score"),
            ocr_needed=False,
        )
        progress.emit(
            "done",
            item_id=item_id,
            title=(analysis.get("title") or hint_title or "Untitled"),
            summary=analysis.get("summary"),
            key_point_count=len(analysis.get("key_points") or []),
            source_trace_count=len(source_traces),
        )
    except Exception as exc:  # noqa: BLE001
        progress.emit("error", error=f"{type(exc).__name__}: {exc}")
        external_store.update_item(
            "external_research",
            item_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        _clear_research_cancel_event(cancel_key or "", cancel_event)


def _append_source_chunk(
    chunks: list[dict],
    *,
    label: str,
    locator: str,
    text: str,
    remaining: list[int],
    page_no: int | None = None,
    slide_no: int | None = None,
) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or remaining[0] <= 0:
        return remaining[0] > 0
    if len(cleaned) > remaining[0]:
        cleaned = cleaned[: remaining[0]].rstrip()
    entry = {
        "id": f"chunk-{len(chunks) + 1}",
        "label": label,
        "locator": locator,
        "text": cleaned,
        "char_count": len(cleaned),
    }
    if page_no is not None:
        entry["page_no"] = page_no
    if slide_no is not None:
        entry["slide_no"] = slide_no
    chunks.append(entry)
    remaining[0] -= len(cleaned)
    return remaining[0] > 0


def _extract_text_chunks_from_file(path_str: str) -> list[dict]:
    """Best-effort, bounded source chunks from uploaded research files."""
    from pathlib import Path

    p = Path(path_str)
    if not p.exists():
        return []
    suffix = p.suffix.lower()
    chunks: list[dict] = []
    remaining = [EXTERNAL_RESEARCH_ANALYSIS_TEXT_LIMIT]
    try:
        if suffix in (".txt", ".md"):
            _append_source_chunk(
                chunks,
                label="Document",
                locator="document",
                text=p.read_text(encoding="utf-8", errors="ignore"),
                remaining=remaining,
            )
            return chunks
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                return []
            reader = PdfReader(str(p))
            for index, page in enumerate(reader.pages[:50], start=1):
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                keep_going = _append_source_chunk(
                    chunks,
                    label=f"Page {index}",
                    locator=f"page {index}",
                    text=page_text,
                    remaining=remaining,
                    page_no=index,
                )
                if not keep_going:
                    break
            return chunks
        if suffix in (".docx", ".doc"):
            try:
                from docx import Document  # type: ignore
            except ImportError:
                return []
            doc = Document(str(p))
            _append_source_chunk(
                chunks,
                label="Document",
                locator="document",
                text="\n".join(p_.text for p_ in doc.paragraphs),
                remaining=remaining,
            )
            return chunks
        if suffix == ".pptx":
            slides = deck_summary.extract_slides(p, "pptx")
            for slide in slides:
                if slide.text:
                    keep_going = _append_source_chunk(
                        chunks,
                        label=f"Slide {slide.slide_no}",
                        locator=f"slide {slide.slide_no}",
                        text=slide.text,
                        remaining=remaining,
                        slide_no=slide.slide_no,
                    )
                    if not keep_going:
                        break
                if slide.notes:
                    keep_going = _append_source_chunk(
                        chunks,
                        label=f"Slide {slide.slide_no} notes",
                        locator=f"slide {slide.slide_no} notes",
                        text=slide.notes,
                        remaining=remaining,
                        slide_no=slide.slide_no,
                    )
                    if not keep_going:
                        break
            return chunks
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return _ocr_extract_text_chunks_from_file(path_str)
    except Exception:
        return []
    return []


def _format_source_chunks_for_analysis(chunks: list[dict]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        label = chunk.get("label") or chunk.get("locator") or "Source"
        parts.append(f"[{label}]\n{text}")
    return "\n\n".join(parts)[:EXTERNAL_RESEARCH_ANALYSIS_TEXT_LIMIT]


def _ocr_extract_text_chunks_from_file(path_str: str) -> list[dict]:
    """Best-effort OCR hook for image-only PDFs and screenshots."""
    path = Path(path_str)
    if not path.exists() or shutil.which("tesseract") is None:
        return []
    suffix = path.suffix.lower()
    chunks: list[dict] = []
    remaining = [EXTERNAL_RESEARCH_ANALYSIS_TEXT_LIMIT]

    def run_tesseract(image_path: Path) -> str:
        try:
            proc = subprocess.run(
                ["tesseract", str(image_path), "stdout"],
                capture_output=True,
                text=True,
                timeout=90,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout or ""

    if suffix == ".pdf":
        if shutil.which("pdftoppm") is None:
            return []
        with tempfile.TemporaryDirectory(prefix="bsh-ocr-") as tmp:
            prefix = Path(tmp) / "page"
            try:
                proc = subprocess.run(
                    [
                        "pdftoppm",
                        "-png",
                        "-r",
                        "200",
                        "-f",
                        "1",
                        "-l",
                        "10",
                        str(path),
                        str(prefix),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except Exception:
                return []
            if proc.returncode != 0:
                return []
            images = sorted(Path(tmp).glob("page-*.png"))
            for index, image_path in enumerate(images, start=1):
                text = run_tesseract(image_path)
                keep_going = _append_source_chunk(
                    chunks,
                    label=f"Page {index} OCR",
                    locator=f"page {index} ocr",
                    text=text,
                    remaining=remaining,
                    page_no=index,
                )
                if not keep_going:
                    break
        return chunks

    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        _append_source_chunk(
            chunks,
            label="Image OCR",
            locator="image ocr",
            text=run_tesseract(path),
            remaining=remaining,
        )
        return chunks

    return []


def _pdf_needs_ocr(path_str: str, chunks: list[dict]) -> bool:
    if Path(path_str).suffix.lower() != ".pdf":
        return False
    total_text = sum(len(str(chunk.get("text") or "").strip()) for chunk in chunks)
    return total_text < PDF_OCR_NEEDED_MIN_TEXT_CHARS


def _source_chunks_for_storage(
    chunks: list[dict],
    *,
    item_id: str,
    filename: str,
) -> list[dict]:
    out: list[dict] = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        stored = {
            "id": chunk.get("id"),
            "file_id": item_id,
            "filename": filename,
            "label": chunk.get("label"),
            "locator": chunk.get("locator"),
            "text": text,
            "char_count": len(text),
        }
        if chunk.get("page_no") is not None:
            stored["page_no"] = chunk.get("page_no")
        if chunk.get("slide_no") is not None:
            stored["slide_no"] = chunk.get("slide_no")
        out.append(stored)
    return out


def _excerpt(text: str, *, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit].rstrip()


def _confidence(value: str | None) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in {"low", "medium", "high"} else "medium"


def _find_chunk_for_trace(trace: dict, chunks: list[dict]) -> dict | None:
    locator = str(trace.get("locator") or "").strip().lower()
    if locator:
        for chunk in chunks:
            if locator == str(chunk.get("locator") or "").strip().lower():
                return chunk
            if locator == str(chunk.get("label") or "").strip().lower():
                return chunk
    excerpt = _excerpt(str(trace.get("excerpt") or ""), limit=120).lower()
    if excerpt:
        for chunk in chunks:
            if excerpt in _excerpt(str(chunk.get("text") or ""), limit=10_000).lower():
                return chunk
    return None


def _normalize_source_traces(
    raw_traces,
    chunks: list[dict],
    *,
    item_id: str,
    filename: str,
) -> list[dict]:
    traces: list[dict] = []
    if isinstance(raw_traces, list):
        for raw in raw_traces:
            if not isinstance(raw, dict):
                continue
            excerpt = _excerpt(str(raw.get("excerpt") or ""))
            if not excerpt:
                continue
            chunk = _find_chunk_for_trace(raw, chunks) or {}
            locator = (
                raw.get("locator")
                or chunk.get("locator")
                or chunk.get("label")
                or "document"
            )
            trace = {
                "file_id": raw.get("file_id") or item_id,
                "filename": raw.get("filename") or filename,
                "locator": str(locator),
                "excerpt": excerpt,
                "confidence": _confidence(raw.get("confidence")),
            }
            if raw.get("claim"):
                trace["claim"] = str(raw.get("claim"))
            if chunk.get("page_no") is not None:
                trace["page_no"] = chunk.get("page_no")
            if chunk.get("slide_no") is not None:
                trace["slide_no"] = chunk.get("slide_no")
            traces.append(trace)
            if len(traces) >= EXTERNAL_RESEARCH_SOURCE_TRACE_LIMIT:
                return traces
        if traces:
            return traces

    for chunk in chunks:
        excerpt = _excerpt(str(chunk.get("text") or ""))
        if not excerpt:
            continue
        trace = {
            "file_id": item_id,
            "filename": filename,
            "locator": str(chunk.get("locator") or chunk.get("label") or "document"),
            "excerpt": excerpt,
            "confidence": "medium",
        }
        if chunk.get("page_no") is not None:
            trace["page_no"] = chunk.get("page_no")
        if chunk.get("slide_no") is not None:
            trace["slide_no"] = chunk.get("slide_no")
        traces.append(trace)
        if len(traces) >= min(EXTERNAL_RESEARCH_SOURCE_TRACE_LIMIT, 3):
            break
    return traces


def _normalize_external_source_traces(
    raw_traces,
    chunks: list[dict],
    *,
    item_id: str,
    filename: str,
) -> list[dict]:
    return _normalize_source_traces(
        raw_traces,
        chunks,
        item_id=item_id,
        filename=filename,
    )


def _extract_text_from_file(path_str: str) -> str:
    """Compatibility wrapper returning labeled text for uploaded files."""
    return _format_source_chunks_for_analysis(
        _extract_text_chunks_from_file(path_str)
    )


@router.post("/external/research", status_code=201)
async def post_external_research(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source_company: str | None = Form(None),
    contact_name: str | None = Form(None),
    contact_email: str | None = Form(None),
    notes: str | None = Form(None),
) -> dict:
    _require_permission(request, "sources:edit")
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    _external_research_upload_kind(file.filename)
    data = await _read_upload_bounded(
        file,
        max_bytes=EXTERNAL_RESEARCH_MAX_FILE_BYTES,
    )
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    safe_name = files_store._sanitize_filename(file.filename)
    content_hash = evidence_store.sha256_bytes(data)
    intake_payload = {
        "title": (title or "").strip() or safe_name,
        "filename": safe_name,
        "source_company": (source_company or "").strip(),
        "notes": (notes or "").strip(),
    }
    dedupe_key = evidence_store.dedupe_key(
        "external_research",
        intake_payload,
        content_hash=content_hash,
    )
    duplicate = evidence_store.find_duplicate_intake(
        "external_research",
        dedupe_key,
    )
    if duplicate is not None:
        return {**duplicate, "dedupe_status": "duplicate", "idempotent": True}
    item_id = external_store.new_id()
    annotation = evidence_store.annotate_intake_record(
        kind="external_research",
        item_id=item_id,
        payload=intake_payload,
        content_hash=content_hash,
    )

    # Stage the file under data/external/external_research/files/<id>__<name>
    files_dir = external_store._kind_dir("external_research") / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
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
            "sha256": content_hash,
            "content_type": file.content_type or "",
            "source_company": (source_company or "").strip() or None,
            "contact_name": (contact_name or "").strip() or None,
            "contact_email": (contact_email or "").strip() or None,
            "notes": (notes or "").strip() or None,
            **annotation,
        },
    )
    cancel_key = _research_cancel_key("external_research", item_id)
    cancel_event = _start_research_cancel_event(cancel_key)
    threading.Thread(
        target=_run_external_research_analysis,
        args=(
            item_id,
            str(stored_path),
            item.get("title"),
            cancel_key,
            cancel_event,
        ),
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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


@router.post("/external/research/{item_id}/analysis/cancel")
def cancel_external_research_analysis(request: Request, item_id: str) -> dict:
    _require_permission(request, "tasks:action")
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    cancel_key = _research_cancel_key("external_research", item_id)
    signal_sent = _request_research_cancel(cancel_key)
    external_store.update_item(
        "external_research",
        item_id,
        status="ready",
        analysis_error="Analysis cancelled",
    )
    progress_path = _external_research_analysis_progress_path(item_id)
    state = _emit_cancelled_progress(
        progress_path,
        reason="External research analysis cancelled",
        kind="external_research",
        item_id=item_id,
    )
    return {
        "kind": "external_research",
        "item_id": item_id,
        "status": "cancelled",
        "signal_sent": signal_sent,
        "terminal_type": state.get("terminal_type"),
        "stream_url": f"/api/external/research/{item_id}/analysis/stream",
        "log_url": f"/api/jobs/log?path=external_research:{item_id}",
    }


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


def _promoted_research_record(company_id: str, item_id: str) -> dict | None:
    for entry in research_store.list_files(company_id):
        if entry.get("promoted_from_external_item_id") == item_id:
            return entry
    return None


@router.post("/external/research/{item_id}/promote", status_code=201)
def promote_external_research(
    request: Request,
    item_id: str,
    payload: ExternalResearchPromoteIn,
) -> dict:
    _require_permission(request, "sources:edit")
    company_id = payload.company_id
    if storage.get_company(company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    item = external_store.get_item("external_research", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    existing = _promoted_research_record(company_id, item_id)
    if existing is not None:
        return {**existing, "status": "already_promoted"}
    stored = item.get("stored_name")
    if not stored:
        raise HTTPException(status_code=400, detail="Item has no file")
    source_path = external_store._kind_dir("external_research") / "files" / stored
    if not source_path.exists():
        raise HTTPException(status_code=400, detail="Source file missing on disk")

    try:
        record = research_store.upload_file(
            company_id,
            filename=item.get("filename") or source_path.name,
            content_type=item.get("content_type") or "application/octet-stream",
            data=source_path.read_bytes(),
            label=item.get("title") or item.get("filename"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metadata = {
        "title": item.get("title"),
        "source_company": item.get("source_company"),
        "contact_name": item.get("contact_name"),
        "contact_email": item.get("contact_email"),
        "notes": item.get("notes"),
        "summary": item.get("summary"),
        "key_points": item.get("key_points") or [],
        "language": item.get("language"),
        "translation": item.get("translation"),
        "source_chunks": item.get("source_chunks") or [],
        "source_traces": item.get("source_traces") or [],
    }
    assignment = item.get("intake_assignment") if isinstance(item.get("intake_assignment"), dict) else {}
    updated = research_store.update_record(
        company_id,
        record["id"],
        promoted_from_external_item_id=item_id,
        external_research_metadata=metadata,
        original_external_item_id=item_id,
        source_company=item.get("source_company"),
        external_title=item.get("title"),
        external_summary=item.get("summary"),
        external_key_points=item.get("key_points") or [],
        source_chunks=item.get("source_chunks") or [],
        source_chunk_count=len(item.get("source_chunks") or []),
        source_traces=item.get("source_traces") or [],
        source_trace_count=len(item.get("source_traces") or []),
        document_category=assignment.get("document_category") or item.get("document_category"),
        source_class=assignment.get("source_class") or item.get("source_class"),
        assignment_status=assignment.get("status"),
        assignment_confidence=assignment.get("company_confidence"),
        provenance={
            "title": item.get("title") or item.get("filename"),
            "origin": item.get("source_company") or item.get("contact_name"),
            "file": record.get("stored_name"),
            "uploaded_at": record.get("uploaded_at"),
            "language": item.get("language"),
            "source_class": assignment.get("source_class") or item.get("source_class"),
            "confidence": str(assignment.get("company_confidence") or "pending"),
            "status": item.get("status") or "pending",
        },
    )
    return updated or record


@router.delete("/external/research/{item_id}", status_code=204)
def delete_external_research(item_id: str, request: Request) -> None:
    _require_permission(request, "documents:delete")
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
    for path in (
        _external_research_analysis_progress_path(item_id),
        _research_translate_progress_path(item_id),
    ):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to delete %s", path, exc_info=True)
    translation_dir = (
        external_store._kind_dir("external_research")
        / "translations"
        / item_id
    )
    shutil.rmtree(translation_dir, ignore_errors=True)


# ---- High-fidelity PDF translation for external research ----


def _research_translate_progress_path(item_id: str):
    base = external_store._kind_dir("external_research") / "translations"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{item_id}__translate.progress.jsonl"


def _run_research_translate_job(
    item_id: str,
    app_language: str | None,
    cancel_key: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    progress_path = _research_translate_progress_path(item_id)
    cancel_fields = {
        "kind": "pdf_translation",
        "item_id": item_id,
        "target_language": app_language,
    }
    if _honor_research_cancel(
        progress_path,
        cancel_event,
        reason="PDF translation cancelled",
        **cancel_fields,
    ):
        _clear_research_cancel_event(cancel_key or "", cancel_event)
        return
    progress = job_progress.ProgressLog(progress_path)
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
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="PDF translation cancelled",
            **cancel_fields,
        ):
            return
        result = external_translate.translate_research_pdf(
            item_id,
            app_language=app_language,
            progress=progress,
            cancel_event=cancel_event,
        )
        if _honor_research_cancel(
            progress_path,
            cancel_event,
            reason="PDF translation cancelled",
            **cancel_fields,
        ):
            return
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
    finally:
        _clear_research_cancel_event(cancel_key or "", cancel_event)


@router.post("/external/research/{item_id}/translate")
def post_research_translate(request: Request, item_id: str, app_language: str | None = None) -> dict:
    """Kick off a high-fidelity PDF translation job for this research item.

    Returns ``{job_id, stream_url}`` for the live progress stream. Cached
    translations come back inline (``cached: true``) when the language
    already matches the request — call with a different ``app_language`` or
    delete and re-upload to force a re-translate.
    """
    _require_permission(request, "tasks:action")
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
    with _job_start_lock(f"pdf_translation:{item_id}"):
        state = _scan_progress_state(progress_path)
        if _progress_state_in_flight(state):
            return {
                "cached": False,
                "job_id": item_id,
                "stream_url": f"/api/external/research/{item_id}/translate/stream",
                "status": "already_running",
            }
        if state.get("exists") and not state.get("terminated"):
            _supersede_progress_file(
                progress_path,
                reason="superseded stale research translation progress",
            )

        cancel_key = _research_cancel_key("pdf_translation", item_id)
        cancel_event = _start_research_cancel_event(cancel_key)
        threading.Thread(
            target=_run_research_translate_job,
            args=(item_id, app_language, cancel_key, cancel_event),
            name=f"research_translate:{item_id}",
            daemon=True,
        ).start()
    return {
        "cached": False,
        "job_id": item_id,
        "stream_url": f"/api/external/research/{item_id}/translate/stream",
        "status": "queued",
    }


@router.post("/external/research/{item_id}/translate/cancel")
def cancel_research_translate(request: Request, item_id: str) -> dict:
    _require_permission(request, "tasks:action")
    if external_store.get_item("external_research", item_id) is None:
        raise HTTPException(status_code=404, detail="Research item not found")
    cancel_key = _research_cancel_key("pdf_translation", item_id)
    signal_sent = _request_research_cancel(cancel_key)
    progress_path = _research_translate_progress_path(item_id)
    state = _emit_cancelled_progress(
        progress_path,
        reason="PDF translation cancelled",
        kind="pdf_translation",
        item_id=item_id,
    )
    return {
        "kind": "pdf_translation",
        "item_id": item_id,
        "status": "cancelled",
        "signal_sent": signal_sent,
        "terminal_type": state.get("terminal_type"),
        "stream_url": f"/api/external/research/{item_id}/translate/stream",
        "log_url": f"/api/jobs/log?path=pdf_translation:{item_id}",
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
def retry_external_research(request: Request, item_id: str) -> dict:
    """Re-run the analysis pipeline for an external research item."""
    _require_permission(request, "tasks:action")
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
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict:
    _require_permission(request, "sources:edit")
    title = (title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    file_data: bytes | None = None
    safe_name: str | None = None
    content_type = ""
    if file is not None and file.filename:
        data = await _read_upload_bounded(
            file, max_bytes=files_store.MAX_FILE_BYTES
        )
        if data:
            file_data = data
            safe_name = files_store._sanitize_filename(file.filename)
            content_type = file.content_type or ""
    hash_source = (title + "\n" + (body or "")).encode("utf-8") + (file_data or b"")
    content_hash = evidence_store.sha256_bytes(hash_source)
    intake_payload = {
        "title": title,
        "body": body or "",
        "filename": safe_name or "",
    }
    dedupe_key = evidence_store.dedupe_key(
        "hormuz_research",
        intake_payload,
        content_hash=content_hash,
    )
    duplicate = evidence_store.find_duplicate_intake(
        "hormuz_research",
        dedupe_key,
    )
    if duplicate is not None:
        return {**duplicate, "dedupe_status": "duplicate", "idempotent": True}

    item_id = external_store.new_id()
    annotation = evidence_store.annotate_intake_record(
        kind="hormuz_research",
        item_id=item_id,
        payload=intake_payload,
        content_hash=content_hash,
    )
    record: dict = {
        "id": item_id,
        "kind": "hormuz_research",
        "status": "ready",
        "title": title,
        "body": (body or "").strip(),
        "sha256": content_hash,
        **annotation,
    }

    if file_data and safe_name:
        files_dir = external_store._kind_dir("hormuz_research") / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{item_id}__{safe_name}"
        stored_path = files_dir / stored_name
        tmp = stored_path.with_suffix(stored_path.suffix + ".tmp")
        tmp.write_bytes(file_data)
        tmp.replace(stored_path)
        record.update(
            filename=safe_name,
            stored_name=stored_name,
            size_bytes=len(file_data),
            content_type=content_type,
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
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict:
    """Upload one or more daily source reports (max 10). The date is
    parsed from each filename (e.g. 中东局势每日研判2026-05-13.pdf →
    2026-05-13)."""
    _require_permission(request, "sources:edit")
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
def post_hormuz_appendix(request: Request, date: str) -> dict:
    """Kick off (or re-run) the bilingual V3 appendix for a date."""
    _require_permission(request, "tasks:action")
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
def delete_hormuz(item_id: str, request: Request) -> None:
    _require_permission(request, "documents:delete")
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
        "legal_name": c.get("legal_name"),
        "disambiguator": c.get("disambiguator"),
        "ticker": c.get("ticker"),
        "description": c.get("description"),
        "sector": c.get("sector"),
        "industry": c.get("industry"),
        "category": c.get("industry") or c.get("sector"),
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
        "positioning": c.get("positioning"),
        "metrics": list(c.get("metrics") or []),
        "team_profiles": list(c.get("team_profiles") or c.get("team") or []),
        "products": list(c.get("products") or []),
        "competitors": list(c.get("competitors") or []),
        "competitor_cards": list(c.get("competitor_cards") or []),
        "recent_news": list(c.get("recent_news") or []),
        "company_news": list(c.get("company_news") or []),
        "notable_contracts": list(c.get("notable_contracts") or []),
        "notable_acquisitions": list(c.get("notable_acquisitions") or []),
        "board_investors": list(c.get("board_investors") or []),
        "cap_table_lineage": list(c.get("cap_table_lineage") or []),
        "industry_view": c.get("industry_view"),
        "expert_opinions": list(c.get("expert_opinions") or []),
        "disclosures": list(c.get("disclosures") or []),
        "memo_state": c.get("memo_state"),
        "audit_records": list(c.get("audit_records") or []),
        "language": c.get("language"),
        "translation": c.get("translation"),
        "trader_snapshot": c.get("trader_snapshot"),
    }


def _memo_report_artifact_urls(r: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Return download/preview URLs for memo artifacts that exist on disk."""
    if not memo_prep.is_memo_kind(r.get("kind")) or not r.get("id"):
        return {}, {}
    rid = r["id"]
    repo_root = memo_prep.DATA_DIR.parent

    def rel_exists(value: Any) -> bool:
        return bool(value and (repo_root / str(value)).exists())

    memo_files = r.get("memo_files") or []
    have_docx = {
        f.get("language")
        for f in memo_files
        if rel_exists(f.get("path"))
    }
    download_urls = {
        lang: f"/api/reports/{rid}/download?language={lang}"
        for lang in ("en", "zh")
        if lang in have_docx
    }
    if any(rel_exists(f.get("path")) for f in r.get("internal_memo_files") or []):
        download_urls["internal"] = (
            f"/api/reports/{rid}/download?artifact=internal"
        )

    have_pdf = {
        f.get("language")
        for f in memo_files
        if rel_exists(f.get("pdf_path"))
    }
    preview_urls = {
        lang: f"/api/reports/{rid}/preview?language={lang}"
        for lang in ("en", "zh")
        if lang in have_pdf
    }
    if any(rel_exists(f.get("pdf_path")) for f in r.get("internal_memo_files") or []):
        preview_urls["internal"] = f"/api/reports/{rid}/preview?artifact=internal"
    return download_urls, preview_urls


def _report_summary(r: dict) -> dict:
    base = {
        "id": r.get("id"),
        "company_id": r.get("company_id"),
        "company_name": r.get("company_name"),
        "report_type": r.get("report_type"),
        "audience": r.get("audience"),
        "language": r.get("language") or "en",
        "status": r.get("status", "queued"),
        "progress": int(r.get("progress") or 0),
        "stage": r.get("stage"),
        "error": r.get("error"),
        "failure_phase": r.get("failure_phase"),
        "failure_detail": r.get("failure_detail"),
        "renderer_contract": r.get("renderer_contract"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
        "kind": r.get("kind"),
        "run_id": r.get("run_id"),
        "run_dir": r.get("run_dir"),
        "skill": r.get("skill"),
        "memo_files": list(r.get("memo_files") or []),
        "internal_memo_files": list(r.get("internal_memo_files") or []),
        "artifacts_available": bool(r.get("artifacts_available")),
        "memo_quality_lint": r.get("memo_quality_lint"),
        "memo_chinese_parity": r.get("memo_chinese_parity"),
        "quality_warnings": r.get("quality_warnings") or None,
        "analysis_session_id": r.get("analysis_session_id"),
        "analysis_session_approved": bool(r.get("analysis_session_approved")),
        "resume_available": (
            _report_resume_available(r)
            if memo_prep.is_memo_kind(r.get("kind"))
            else False
        ),
        "superseded_by": r.get("superseded_by"),
        "dismissed_at": r.get("dismissed_at"),
        "memo_mode": r.get("memo_mode"),
        "studio_investigation": r.get("studio_investigation"),
        "studio_generate": r.get("studio_generate"),
        "trigger": r.get("trigger"),
        "auto_run_id": r.get("auto_run_id"),
        "report_ready_at": r.get("report_ready_at"),
        "run_finished_at": r.get("run_finished_at"),
    }
    download_urls, preview_urls = _memo_report_artifact_urls(r)
    if download_urls:
        base["download_urls"] = download_urls
    if preview_urls:
        base["preview_urls"] = preview_urls
    return base


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
    if memo_prep.is_memo_kind(r.get("kind")) and r.get("id"):
        rid = r["id"]
        base["stream_url"] = f"/api/memos/{rid}/stream"
        base["log_url"] = f"/api/jobs/log?path=memo:{rid}"
        base["analysis_artifacts"] = _report_analysis_artifacts(r)
        base["resume_available"] = _report_resume_available(r)
        download_urls, preview_urls = _memo_report_artifact_urls(r)
        if download_urls:
            base["download_urls"] = download_urls
        # Only advertise a preview URL for a language whose PDF was
        # actually rendered (Word automation can be unavailable, or an
        # older run may predate PDF rendering).
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
        for m in console_store.list_sessions(company_id, include_copilot=False)
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
    request: Request,
    company_id: str, body: _ConsoleCreateBody | None = None
) -> dict:
    _require_permission(request, "tasks:action")
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
def create_hormuz_console_session(request: Request, body: _ConsoleCreateBody | None = None) -> dict:
    _require_permission(request, "tasks:action")
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
    request: Request,
    company_id: str,
    sid: str,
    prompt: str = Form(...),
    images: list[UploadFile] = File(default=[]),
) -> dict:
    _require_permission(request, "tasks:action")
    if not console_store.session_exists(company_id, sid):
        raise HTTPException(status_code=404, detail="Session not found")

    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    saved: list[str] = []
    for upload in images or []:
        try:
            data = await _read_upload_bounded(
                upload, max_bytes=console_store.MAX_ATTACHMENT_BYTES
            )
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
            # Keep the structured error shape the frontend matches on.
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "attachment_too_large",
                    "limit_bytes": console_store.MAX_ATTACHMENT_BYTES,
                    "message": (
                        "Attachment too large: exceeds "
                        f"{console_store.MAX_ATTACHMENT_BYTES} bytes"
                    ),
                },
            ) from exc
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
                        if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
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
    request: Request,
    company_id: str, sid: str, turn_id: str
) -> Response:
    _require_permission(request, "tasks:action")
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
def delete_console_session(company_id: str, sid: str, request: Request) -> Response:
    _require_permission(request, "documents:delete")
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


class TraderSectionRefreshRequest(BaseModel):
    sections: list[str] = Field(default_factory=list)
    force: bool = False
    preserve_existing_sections: bool = True


class _TraderProgressMirror:
    """Mirror section-level events from a company refresh into bulk logs."""

    def __init__(self, primary, mirror, *, company: dict):
        self._primary = primary
        self._mirror = mirror
        self._company = company

    def emit(self, type_: str, **fields: Any) -> None:
        self._primary.emit(type_, **fields)
        if self._mirror is None:
            return
        mapped = {
            "thread_started": "section_started",
            "thread_finished": "section_finished",
            "thread_failed": "section_failed",
        }.get(type_)
        if not mapped:
            return
        payload = {
            key: value
            for key, value in fields.items()
            if key
            in {
                "thread",
                "title",
                "section_id",
                "pass_id",
                "error",
                "duration_ms",
                "cached",
            }
        }
        self._mirror.emit(
            mapped,
            company_id=self._company.get("id"),
            company_name=self._company.get("name") or self._company.get("id"),
            ticker=(self._company.get("ticker") or "").strip(),
            **payload,
        )

    @property
    def is_terminated(self) -> bool:
        return self._primary.is_terminated


def _generate_trader_snapshot(
    *,
    company: dict,
    progress,
    previous_snapshot: dict | None,
    section_ids: list[str] | None = None,
    force: bool = False,
    preserve_existing_sections: bool = True,
    section_workers: int | None = None,
    global_llm_semaphore=None,
) -> tuple[dict | None, str | None]:
    try:
        return companies_ai_public.generate_snapshot(
            company=company,
            progress=progress,
            previous_snapshot=previous_snapshot,
            section_ids=section_ids,
            force=force,
            preserve_existing_sections=preserve_existing_sections,
            max_workers=section_workers,
            global_semaphore=global_llm_semaphore,
        )
    except TypeError as exc:
        # Several fast tests monkeypatch the old two-kwarg signature.
        # Keep that shape working while production uses the richer
        # section-aware generator.
        if "unexpected keyword argument" not in str(exc):
            raise
        return companies_ai_public.generate_snapshot(
            company=company,
            progress=progress,
        )


def _run_trader_snapshot_job(
    company_id: str,
    *,
    languages_requested: list[str] | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
    force: bool = False,
    section_ids: list[str] | None = None,
    preserve_existing_sections: bool = True,
    retry_scope: str = "snapshot",
    section_workers: int | None = None,
    global_llm_semaphore=None,
    mirror_progress=None,
) -> None:
    """Background worker for a single trader-snapshot refresh. Writes
    progress events to JSONL and persists the snapshot on success.

    ``languages_requested`` / ``include_translations`` / ``translation_mode``
    are recorded on ``job_init`` for client-side observability. Today
    the schema + system prompt always produces bilingual output, so
    these inputs don't affect generation; they're a placeholder for a
    future single-language mode (Phase 2 of the bilingual rollout).
    """
    base_progress = job_progress.ProgressLog(_trader_snapshot_progress_path(company_id))
    company = storage.get_company(company_id) or {}
    progress = (
        _TraderProgressMirror(base_progress, mirror_progress, company=company)
        if mirror_progress is not None
        else base_progress
    )
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
        retry_scope=retry_scope,
        retried_sections=section_ids or [],
    )
    progress.emit(
        "stage", stage="starting",
        message=f"Refreshing trader snapshot for {company_name}",
    )

    started_at = datetime.now(timezone.utc)
    try:
        snapshot, err = _generate_trader_snapshot(
            company=company,
            progress=progress,
            previous_snapshot=previous_snapshot,
            section_ids=section_ids,
            force=force,
            preserve_existing_sections=preserve_existing_sections,
            section_workers=section_workers,
            global_llm_semaphore=global_llm_semaphore,
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
    section_status = snapshot.pop(companies_ai_public.SECTION_STATUS_KEY, None)
    try:
        if section_ids:
            section_payload = {
                section_id: snapshot.get(section_id)
                for section_id in section_ids
            }
            trader_bilingual_fill.ensure_bilingual_completeness(section_payload)
            for section_id in section_ids:
                snapshot[section_id] = section_payload.get(section_id)
        else:
            trader_bilingual_fill.ensure_bilingual_completeness(snapshot)
    except Exception:  # noqa: BLE001
        logger.exception(
            "trader_bilingual_fill: completeness pass crashed; "
            "persisting snapshot as-is",
        )
    finally:
        if section_status is not None:
            snapshot[companies_ai_public.SECTION_STATUS_KEY] = section_status

    companies_ai_public.ensure_section_status(
        snapshot,
        previous_snapshot=previous_snapshot,
        source_run_id=f"{company_id}:{snapshot['refreshed_at']}",
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
            retry_scope=retry_scope,
            retried_sections=section_ids or [],
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
        retry_scope=retry_scope,
        retried_sections=section_ids or [],
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
        job_progress.supersede_progress_file(path, reason=reason)
    except Exception:  # noqa: BLE001
        logger.exception("failed to supersede stale progress")


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
    """Refresh every tracked public-company trader snapshot with bounds."""
    progress = job_progress.ProgressLog(_trader_refresh_all_progress_path())
    companies = _public_companies_for_trader_refresh()
    total_count = len(companies)
    company_workers = max(
        1, int(os.environ.get("BSH_TRADER_BULK_COMPANY_WORKERS", "3"))
    )
    section_workers = max(
        1, int(os.environ.get("BSH_TRADER_SECTION_WORKERS_PER_COMPANY", "3"))
    )
    global_llm_workers = max(
        1, int(os.environ.get("BSH_TRADER_GLOBAL_LLM_WORKERS", "6"))
    )
    global_llm_semaphore = threading.Semaphore(global_llm_workers)
    progress.emit(
        "job_init",
        kind="public_snapshot_bulk",
        title="Refresh all stock views",
        subtitle=f"{total_count} public companies",
        total_count=total_count,
        force=force,
        company_workers=company_workers,
        section_workers_per_company=section_workers,
        global_llm_workers=global_llm_workers,
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

    def _refresh_one(idx: int, company: dict) -> dict:
        company_id = (company.get("id") or "").strip()
        company_name = company.get("name") or company_id or "Unknown company"
        ticker = (company.get("ticker") or "").strip()

        if not company_id:
            return {
                "company_id": None,
                "company_name": company_name,
                "ticker": ticker,
                "status": "skipped_missing_id",
            }
        if not ticker:
            progress.emit(
                "company_done",
                message=f"Skipped {company_name}: missing ticker",
                company_id=company_id,
                company_name=company_name,
                ticker=ticker,
                index=idx,
                total_count=total_count,
                status="skipped_missing_ticker",
            )
            return {
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "skipped_missing_ticker",
            }

        snapshot_path = _trader_snapshot_progress_path(company_id)
        state = _scan_progress_state(snapshot_path)
        if _progress_state_in_flight(state) and not force:
            progress.emit(
                "company_done",
                message=f"Skipped {company_name}: refresh already running",
                company_id=company_id,
                company_name=company_name,
                ticker=ticker,
                index=idx,
                total_count=total_count,
                status="already_running",
            )
            return {
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "already_running",
            }
        if _progress_state_in_flight(state) and force:
            _supersede_progress_file(
                snapshot_path, reason="superseded by bulk force-refresh"
            )

        progress.emit(
            "company_started",
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
                force=force,
                section_workers=section_workers,
                global_llm_semaphore=global_llm_semaphore,
                mirror_progress=progress,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("bulk trader refresh crashed for %s", company_id)
            progress.emit(
                "company_done",
                message=f"Trader view failed for {ticker}",
                company_id=company_id,
                company_name=company_name,
                ticker=ticker,
                index=idx,
                total_count=total_count,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            return {
                "company_id": company_id,
                "company_name": company_name,
                "ticker": ticker,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        final_state = _scan_progress_state(snapshot_path)
        if final_state.get("terminal_type") == "done":
            status = "done"
        else:
            status = "error"
        if status == "done":
            fresh_company = storage.get_company(company_id) or {}
            fresh_snapshot = fresh_company.get("trader_snapshot")
            section_status = (
                fresh_snapshot.get(companies_ai_public.SECTION_STATUS_KEY)
                if isinstance(fresh_snapshot, dict)
                else None
            )
            if isinstance(section_status, dict) and any(
                isinstance(row, dict)
                and row.get("status") in {"failed", "stale"}
                and row.get("last_error")
                for row in section_status.values()
            ):
                status = "partial"
        result = {
            "company_id": company_id,
            "company_name": company_name,
            "ticker": ticker,
            "status": status,
        }
        if final_state.get("error"):
            result["error"] = final_state["error"]
        progress.emit(
            "company_done" if status == "done" else "company_partial",
            message=(
                f"Completed {ticker}"
                if status == "done"
                else f"Trader view ended {status} for {ticker}"
            ),
            company_id=company_id,
            company_name=company_name,
            ticker=ticker,
            index=idx,
            total_count=total_count,
            status=status,
            error=result.get("error"),
        )
        return result

    queued: list[tuple[int, dict]] = []
    for idx, company in enumerate(companies, start=1):
        progress.emit(
            "company_queued",
            company_id=company.get("id"),
            company_name=company.get("name") or company.get("id"),
            ticker=(company.get("ticker") or "").strip(),
            index=idx,
            total_count=total_count,
        )
        queued.append((idx, company))

    with ThreadPoolExecutor(max_workers=min(company_workers, len(queued))) as pool:
        futures = [
            pool.submit(_refresh_one, idx, company)
            for idx, company in queued
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = result.get("status")
            if status in {"done", "partial"}:
                refreshed_count += 1
            elif status in {"skipped_missing_id", "skipped_missing_ticker", "already_running"}:
                skipped_count += 1
            else:
                failed_count += 1

    progress.emit(
        "bulk_done",
        total_count=total_count,
        refreshed_count=refreshed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        results=results,
    )
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
    # list_companies() is slim (no trader_snapshot — it lives in sidecars);
    # the dashboard summarizes snapshots, so hydrate via get_company.
    companies = [
        storage.get_company(c["id"]) or c
        for c in storage.list_companies()
        if c.get("id")
    ]
    return trader_stats.build_dashboard(companies, limit=limit)


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
    request: Request,
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
    _require_permission(request, "tasks:action")
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
    with _job_start_lock(f"trader:{company_id}"):
        state = _scan_progress_state(path)
        # `_progress_state_in_flight` (not a bare exists-and-not-terminated
        # check) so a worker that died without a terminal event stops
        # blocking new refreshes once the log goes idle.
        in_flight = _progress_state_in_flight(state)
        if in_flight and not force:
            return {
                "job_id": company_id,
                "stream_url": stream_url,
                "status": "already_running",
                "languages_requested": languages_requested,
            }
        if state.get("exists") and not state.get("terminated"):
            # Supersede the stale in-flight worker. We emit a terminal
            # `error` event so any SSE consumer tailing the old progress
            # file sees an explicit superseded marker rather than a silent
            # cut. The old background thread, if still alive, will keep
            # running but its writes go to a deleted file — harmless.
            try:
                tail_progress = job_progress.ProgressLog(path)
                tail_progress.emit(
                    "error",
                    error=(
                        "superseded by force-refresh"
                        if force
                        else "superseded stale trader refresh"
                    ),
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
                "force": force,
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


@router.post("/companies/{company_id}/trader/refresh-sections")
def post_trader_refresh_sections(
    request: Request,
    company_id: str,
    body: TraderSectionRefreshRequest,
    languages: str | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
) -> dict:
    """Retry selected trader snapshot sections without rerunning the whole view."""
    _require_permission(request, "tasks:action")
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
    sections = companies_ai_public.normalize_section_ids(body.sections)
    if not sections:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_sections",
                "message": "Supply at least one valid trader section id.",
                "valid_sections": list(companies_ai_public.SECTION_KEYS),
            },
        )

    languages_requested = _parse_trader_languages(languages)
    stream_url = f"/api/companies/{company_id}/trader/refresh/stream"
    path = _trader_snapshot_progress_path(company_id)
    with _job_start_lock(f"trader:{company_id}"):
        state = _scan_progress_state(path)
        in_flight = _progress_state_in_flight(state)
        if in_flight and not body.force:
            return {
                "job_id": company_id,
                "stream_url": stream_url,
                "status": "already_running",
                "languages_requested": languages_requested,
                "retry_scope": "sections",
                "retried_sections": sections,
            }
        if state.get("exists") and not state.get("terminated"):
            _supersede_progress_file(
                path,
                reason=(
                    "superseded by section force-refresh"
                    if body.force
                    else "superseded stale trader refresh"
                ),
            )

        threading.Thread(
            target=_run_trader_snapshot_job,
            args=(company_id,),
            kwargs={
                "languages_requested": languages_requested,
                "include_translations": include_translations,
                "translation_mode": translation_mode,
                "force": body.force,
                "section_ids": sections,
                "preserve_existing_sections": body.preserve_existing_sections,
                "retry_scope": "sections",
            },
            name=f"trader-snapshot:{company_id}:sections",
            daemon=True,
        ).start()
    return {
        "job_id": company_id,
        "stream_url": stream_url,
        "status": "force_queued" if body.force else "queued",
        "languages_requested": languages_requested,
        "retry_scope": "sections",
        "retried_sections": sections,
    }


@router.post("/companies/trader/refresh-all")
def post_trader_refresh_all(
    request: Request,
    languages: str | None = None,
    include_translations: bool = True,
    translation_mode: str = "all",
    force: bool = False,
) -> dict:
    """Refresh trader snapshots for every tracked public company."""
    _require_permission(request, "tasks:action")
    languages_requested = _parse_trader_languages(languages)
    stream_url = "/api/companies/trader/refresh-all/stream"
    companies = _public_companies_for_trader_refresh()
    queue = _summarize_trader_refresh_queue(companies, force=force)

    path = _trader_refresh_all_progress_path()
    with _job_start_lock("trader:all"):
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
def post_companies_regen_all(request: Request, force: bool = False) -> dict:
    """Regenerate every tracked company's summary and public trader view.

    This is the broad admin refresh: every tracked company gets a fresh
    deep-search dossier plus forced company translation; companies that are
    public after that refresh also get a bilingual trader snapshot.
    """
    _require_permission(request, "tasks:action")
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
    with _job_start_lock("regen:all"):
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
