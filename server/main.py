"""FastAPI entrypoint for BSH Research Center.

Serves the Vue SPA from `frontend/dist` and mounts the JSON API under `/api`.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root BEFORE importing modules that read env
# vars. All LLM calls go through the Claude Code CLI (which manages its
# own credentials), so the .env file is currently only used for
# miscellaneous service config — we keep the loader for forward
# compatibility but no key is required for the app to run.
def _bootstrap_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        # Fallback: minimal KEY=VALUE parser so we don't hard-require
        # python-dotenv if the install is partial.
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_bootstrap_env()

import html as _html  # noqa: E402

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
import mimetypes  # noqa: E402

from . import (  # noqa: E402
    claude_runner,
    companies_ai_public,
    company_paths,
    companies_autocomplete,
    console_session,
    local_generation,
    buffett_memo_analysis,
    memo_analysis,
)
from .api import (  # noqa: E402
    auth_router,
    router as api_router,
    require_api_token,
    _anon_dev_enabled,
    _expected_token,
    resume_interrupted_memo_runs,
    resume_regen_all_if_needed,
    start_stale_job_recovery,
)
from .company_translate import translate_company  # noqa: E402
from .storage import (  # noqa: E402
    get_company_ext,
    list_companies,
    migrate_trader_snapshots,
    update_company,
)

logger = logging.getLogger("bsh.startup")

DIST_DIR = ROOT_DIR / "frontend" / "dist"
ASSETS_DIR = DIST_DIR / "assets"

# root_path tells Starlette/FastAPI the prefix nginx mounts us under
# (api.bshventures.com/research/*). With a non-stripping nginx, the
# upstream receives the full `/research/...` path; Starlette strips
# root_path internally before matching, and uses it to generate URLs
# (OpenAPI servers, request.url_for, etc.).
#
# Consequence: any request path that *starts with* `/research` has that
# segment stripped before routing — including a hard reload of the
# client route `/research/<company>`, which becomes `/<company>`. So the
# SPA page routes can't be reliably enumerated with a `/research` prefix;
# the catch-all `spa_fallback` at the bottom of this file is what makes
# deep-link reloads work. See that route's docstring.
app = FastAPI(title="bsh-research-center", root_path="/research")
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def _security_headers(request, call_next):
    """The response headers a sign-in page is naked without.

    Framing is limited to this origin — not denied outright, because the
    file and external-research previews frame their own documents. Auth
    responses carry a token and are marked uncacheable so no shared cache
    keeps one. HSTS is sent only where the request is already secure: on a
    plain-http local run it would be a promise the browser then holds the
    developer to. A full script CSP is deliberately not here — index.html
    ships an inline bootstrap script, and a policy that breaks the app
    gets removed rather than kept.
    """
    response = await call_next(request)
    headers = response.headers
    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "same-origin")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if "/api/auth/" in request.url.path:
        headers["Cache-Control"] = "no-store"
    from server.api import _cookie_secure

    if _cookie_secure(request):
        headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


_READER_EVENT_PATH_RE = re.compile(r"/api/reports/[^/]+/events/?$")


@app.middleware("http")
async def _audit_mutations(request, call_next):
    """Append every mutating /api call (who, what, status) to the firm audit trail.

    Reader telemetry (POST /api/reports/{id}/events) is a read signal, not a
    change, so it stays out of the trail; report downloads and exports are
    recorded by the download routes themselves (server/report_access.py).
    """
    response = await call_next(request)
    try:
        path = request.url.path
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and "/api/" in path
            and "/auth/" not in path
            and "/stream" not in path
            and "/copilot" not in path
            and "/console" not in path
            and not _READER_EVENT_PATH_RE.search(path)
        ):
            from server import firm

            firm.record_audit(
                actor=getattr(request.state, "session_email", None),
                auth_kind=getattr(request.state, "auth_kind", None),
                action=firm.describe_action(request.method, path),
                path=path,
                status=response.status_code,
                company_id=firm.company_from_path(path),
            )
    except Exception:  # noqa: BLE001 — auditing must never break a request
        pass
    return response

# Serve the SPA's built assets via a regular route (not StaticFiles
# mount). The mount path interacts awkwardly with root_path: when nginx
# strips the prefix before forwarding, scope["root_path"] is still set
# but scope["path"] no longer includes it, and StaticFiles ends up
# looking for "assets/foo.js" inside ASSETS_DIR (one level too deep)
# and returns 404. A direct route is independent of where the mount
# point lives in the URL hierarchy, so it serves correctly whether
# the request arrives prefixed (`/research/assets/...`) or stripped
# (`/assets/...`).
ASSETS_DIR_RESOLVED = ASSETS_DIR.resolve() if ASSETS_DIR.exists() else None


@app.get("/assets/{file_path:path}", include_in_schema=False)
async def _serve_spa_asset(file_path: str) -> FileResponse:
    if ASSETS_DIR_RESOLVED is None:
        raise HTTPException(status_code=503, detail="Frontend build missing.")
    candidate = (ASSETS_DIR_RESOLVED / file_path).resolve()
    # Path-traversal guard: candidate must live inside ASSETS_DIR.
    if not str(candidate).startswith(str(ASSETS_DIR_RESOLVED) + "/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(candidate, media_type=media_type)

app.include_router(auth_router)
app.include_router(api_router)


def _run_startup_recovery() -> None:
    """Restart recovery sweeps. They walk every report and job log, so the
    startup hook runs them on a background thread instead of making the
    first requests wait for them."""
    # Synthesize error turns for any Console session that lost an in-flight
    # subprocess across the restart. Cheap, idempotent — see §7 of
    # docs/console-feature.md.
    try:
        console_session.recover()
    except Exception:  # noqa: BLE001
        logger.exception("Console recovery sweep failed")
    try:
        n = memo_analysis.recover_stale_reports()
        if n:
            logger.info("Recovered %d stale memo report(s).", n)
    except Exception:  # noqa: BLE001
        logger.exception("Memo recovery sweep failed")
    try:
        n = buffett_memo_analysis.recover_stale_reports()
        if n:
            logger.info("Recovered %d stale Buffett memo report(s).", n)
    except Exception:  # noqa: BLE001
        logger.exception("Buffett memo recovery sweep failed")
    # A restart interrupts daemon-thread memo workers; the sweep above
    # (plus the shutdown hook) marks them failed_during_analysis with
    # failure_phase shutdown/orphaned. Resume those automatically so a
    # restart resumes rather than orphans runs (BSH_MEMO_AUTO_RESUME=0
    # disables).
    try:
        n = resume_interrupted_memo_runs()
        if n:
            logger.info("Auto-resumed %d restart-interrupted memo run(s).", n)
    except Exception:  # noqa: BLE001
        logger.exception("Memo auto-resume failed")
    try:
        if resume_regen_all_if_needed():
            logger.info("Resumed all-company regeneration from checkpoint.")
    except Exception:  # noqa: BLE001
        logger.exception("All-company regeneration recovery failed")
    # Stale-job recovery used to run inline on every /api/jobs/active poll,
    # overloading the endpoint. Do it once now, then periodically in the
    # background — off the request path.
    try:
        start_stale_job_recovery()
    except Exception:  # noqa: BLE001
        logger.exception("Stale-job recovery startup failed")


@app.on_event("startup")
def _startup() -> None:
    try:
        summary = local_generation.generate_local_runtime_state()
        logger.info(
            "Local runtime state ready: companies=%s materialized=%s stock_trackers=%s.",
            summary.get("company_count"),
            summary.get("company_records_materialized"),
            summary.get("stock_research_tracker_count"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Local runtime state generation failed")
    if claude_runner.is_available():
        logger.info("Claude Code CLI available — analysis paths enabled.")
    else:
        logger.warning(
            "Claude Code (`claude`) not on PATH — analysis paths will "
            "return errors. Install with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )
    threading.Thread(
        target=_run_startup_recovery, name="startup-recovery", daemon=True
    ).start()
    try:
        from . import tracking_updates

        tracking_updates.start_tracking_sync_loop()
    except Exception:  # noqa: BLE001
        logger.exception("Tracking sync startup failed")
    # News desk AI briefings: one Sonnet worker refreshes the recorded top
    # of the tape every BSH_NEWS_BRIEF_REFRESH_HOURS (default 6; 0 turns
    # the schedule off). Opening the News page never calls Claude.
    try:
        from . import news_brief

        if news_brief.start_refresh_loop():
            logger.info("News brief refresh loop started.")
    except Exception:  # noqa: BLE001
        logger.exception("News brief refresh loop startup failed")
    # Morning brief: build the tape snapshot and write its note once each
    # morning (BSH_MORNING_BRIEF_HOUR, default 07:00 local; BSH_MORNING_BRIEF=0
    # turns it off), so the desk opens to a brief instead of a button.
    try:
        from . import market_brief

        if market_brief.start_morning_loop():
            logger.info(
                "Morning brief loop started (%02d:00 local, %s note).",
                market_brief.morning_hour(),
                market_brief.morning_length(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Morning brief loop startup failed")
    # Server-side alert engine — opt-in via BSH_ALERT_ENGINE_INTERVAL so
    # tests and offline runs never poll quote providers.
    try:
        from . import alert_engine

        if alert_engine.start_background_engine():
            logger.info("Market alert engine started.")
    except Exception:  # noqa: BLE001
        logger.exception("Alert engine startup failed")
    # Warm the autocomplete indexes (SEC EDGAR fetch + deep-search cache scan)
    # off the request path so the first keystrokes aren't slow.
    try:
        companies_autocomplete.prewarm_indexes()
    except Exception:  # noqa: BLE001
        logger.exception("Autocomplete prewarm failed")
    # Strip any pre-v2 heat_card blocks so iOS / web don't try to read
    # the legacy shape through the new code. Idempotent on subsequent
    # restarts. See docs/heat-card-v2.md §6.
    try:
        target = companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
        n = migrate_trader_snapshots(target_schema_version=target)
        if n:
            logger.info(
                "Migrated %d trader_snapshot record(s) to schema_version=%d.",
                n, target,
            )
    except Exception:  # noqa: BLE001
        logger.exception("trader_snapshot migration failed")
    # Per-company data used to live under an ASCII-stripped directory name
    # ("brk.b" -> "brkb"); move it under the id's storage key once.
    try:
        moved = company_paths.migrate_legacy_dirs()
        if moved:
            logger.warning(
                "Moved %d legacy per-company director(ies)/file(s) to their storage keys.", len(moved)
            )
    except Exception:  # noqa: BLE001
        logger.exception("Legacy company directory migration failed")
    _start_translation_backfill()


@app.on_event("shutdown")
def _shutdown() -> None:
    _TRANSLATION_STOP.set()
    # Order matters: refuse new claude spawns, record in-flight memo runs
    # as interrupted by the shutdown (resume-eligible) while their workers
    # are still blocked, then reap every live claude CLI subprocess group.
    # They run detached (start_new_session=True) so nothing else kills them
    # when uvicorn exits — without this a dev restart leaves orphaned CLI
    # runs burning tokens with no consumer. Also registered via atexit as a
    # backstop for non-graceful exits.
    claude_runner.begin_shutdown()
    try:
        memo_analysis.halt_active_runs_for_shutdown()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to mark in-flight memo runs interrupted")
    try:
        claude_runner.terminate_live_claude_procs()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to terminate live claude subprocesses")


# Content fields we expect a real translation to populate. A block that
# has none of these filled is a stale skeleton or a persisted failed
# attempt (e.g. NVDA: language="other", every field null) — the old
# `not c.get("translation")` predicate skipped those forever because an
# all-null dict is truthy. Re-translate them.
_TRANSLATION_CONTENT_FIELDS = (
    "description", "sector", "industry", "status", "hq",
    "employee_band", "parent_company", "key_people", "products",
    "competitors", "recent_news", "notable_contracts",
    "notable_acquisitions", "highlight_2026",
)


def _needs_translation(company: dict) -> bool:
    tr = company.get("translation")
    if not tr or not isinstance(tr, dict):
        return True
    for k in _TRANSLATION_CONTENT_FIELDS:
        v = tr.get(k)
        if v not in (None, "", [], {}):
            return False  # at least one field is genuinely populated
    return True  # shaped-but-empty / failed block → retranslate


def _run_translation_backfill_once() -> None:
    try:
        # list_companies() is slim — translation lives in per-company
        # sidecar files — so hydrate that one field before deciding who
        # still needs a translation pass.
        companies = []
        for c in list_companies():
            cid = c.get("id")
            if cid and "translation" not in c:
                ext = get_company_ext(cid)
                if "translation" in ext:
                    c = {**c, "translation": ext["translation"]}
            companies.append(c)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Translation backfill: list_companies failed: %s", exc)
        return
    pending = [c for c in companies if _needs_translation(c)]
    if not pending:
        return
    logger.warning(
        "Translation backfill: %d company record(s) to translate.",
        len(pending),
    )
    paused = False
    for idx, c in enumerate(pending, start=1):
        cid = c.get("id")
        if not cid:
            continue
        if _TRANSLATION_STOP.is_set():
            paused = True
            break
        try:
            result = translate_company(c)
            err = result.get("error")
            limit_reason = claude_runner.provider_limit_reason(
                err, include_bare_claude_exit=True
            )
            if limit_reason:
                remaining = len(pending) - idx + 1
                logger.warning(
                    "Translation backfill paused at %s: %s. "
                    "%d record(s) remain pending.",
                    cid, limit_reason, remaining,
                )
                paused = True
                break
            update_company(
                cid,
                language=result.get("language"),
                translation=result.get("translation"),
            )
            if err:
                logger.warning("Translation backfill for %s: %s", cid, err)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            limit_reason = claude_runner.provider_limit_reason(
                err, include_bare_claude_exit=True
            )
            if limit_reason:
                remaining = len(pending) - idx + 1
                logger.warning(
                    "Translation backfill paused at %s: %s. "
                    "%d record(s) remain pending.",
                    cid, limit_reason, remaining,
                )
                paused = True
                break
            logger.warning("Translation backfill for %s failed: %s", cid, exc)
    if not paused:
        logger.info("Translation backfill: complete.")


_TRANSLATION_STOP = threading.Event()


def _translation_backfill_enabled() -> bool:
    raw = (os.environ.get("BSH_COMPANY_TRANSLATION_BACKFILL") or "1").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


def _start_translation_backfill() -> None:
    """Backfill missing company translations without blocking startup.

    On by default; ``BSH_COMPANY_TRANSLATION_BACKFILL=0`` turns it off
    because every run spawns Claude CLI work (deck intake and AI search do
    not translate inline, so switching it off leaves those companies
    untranslated). If Claude reports a quota / rate-limit failure,
    pause the backfill and leave the remaining records untouched so a later
    restart can retry them.
    """
    if not _translation_backfill_enabled():
        return
    if not claude_runner.is_available():
        return
    _TRANSLATION_STOP.clear()

    threading.Thread(
        target=_run_translation_backfill_once,
        name="company-translation-backfill",
        daemon=True,
    ).start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/diagnostics", dependencies=[Depends(require_api_token)])
def diagnostics() -> dict:
    """Quick health check for env / config."""
    from server import ai_engine, gemini_runner

    return {
        "env_file_exists": (ROOT_DIR / ".env").exists(),
        "api_token_configured": bool(_expected_token()),
        # Whether the Gemini-backed surfaces (Team dossier, desk note,
        # company news sweep) will run on Gemini or fall back to Claude.
        # Reports configuration only — it spends nothing to answer.
        "ai_engine_policy": ai_engine.policy(),
        "gemini_key_configured": gemini_runner.is_available(),
        "gemini_model": gemini_runner.default_model(),
    }


def _serve_index() -> HTMLResponse:
    """Serve the SPA shell.

    Meta tags spliced into ``<head>`` for the in-browser app:

    - ``bsh-research-api-base``: the prefix the app is mounted under
      (``root_path``). The SPA prepends it to every fetched URL so that
      a non-stripping nginx upstream sees the full ``/research/...`` path
      and Starlette's routing matches correctly. Empty when the app is
      served at the root.
    - ``bsh-research-anon-dev``: present only when ``BSH_ALLOW_ANON_DEV=1``.
      Lets the SPA skip the login gate for local development. Not a
      credential.

    The page itself is NOT gated (it must load before the user can log
    in), but it no longer carries any credential — the API token is not
    injected. ``/api/*`` routes enforce auth via ``require_api_token``.
    """
    index_path = DIST_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build missing. Run `npm install && npm run build` in frontend/.",
        )
    html_text = index_path.read_text(encoding="utf-8")
    # NOTE: the API token is deliberately NOT injected here. It used to be
    # served as <meta name="bsh-research-api-token"> so any visitor could
    # read a fully-privileged credential from View Source. Clients now
    # authenticate via the login flow (session token + httponly cookie).
    # Only the mount-path hint is injected.
    metas: list[str] = []
    metas.append(
        f'<meta name="bsh-research-api-base" '
        f'content="{_html.escape(app.root_path or "", quote=True)}">'
    )
    if _anon_dev_enabled():
        metas.append('<meta name="bsh-research-anon-dev" content="1">')
    if metas:
        block = "\n  ".join(metas)
        if "</head>" in html_text:
            html_text = html_text.replace("</head>", f"  {block}\n  </head>", 1)
        elif "<head>" in html_text:
            html_text = html_text.replace("<head>", f"<head>\n  {block}", 1)
    return HTMLResponse(
        content=html_text,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
def root() -> HTMLResponse:
    return _serve_index()


@app.get("/research/{company_id}")
def research_page(company_id: str) -> HTMLResponse:  # noqa: ARG001 — handled client-side
    return _serve_index()


@app.get("/news/{item_id}")
def news_page(item_id: str) -> FileResponse:  # noqa: ARG001
    return _serve_index()


@app.get("/external-research/{item_id}")
def external_research_page(item_id: str) -> FileResponse:  # noqa: ARG001
    return _serve_index()


@app.get("/hormuz/{item_id}")
def hormuz_page(item_id: str) -> FileResponse:  # noqa: ARG001
    return _serve_index()


@app.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    icon = DIST_DIR / "favicon.svg"
    if not icon.exists():
        raise HTTPException(status_code=404)
    return FileResponse(icon)


@app.get("/favicon.png")
def favicon_png() -> FileResponse:
    icon = DIST_DIR / "favicon.png"
    if not icon.exists():
        raise HTTPException(status_code=404)
    return FileResponse(icon)


@app.get("/app-icon.png")
def app_icon() -> FileResponse:
    icon = DIST_DIR / "app-icon.png"
    if not icon.exists():
        raise HTTPException(status_code=404)
    return FileResponse(icon)


# SPA history-mode fallback. MUST be the last route so every explicit
# route above (API, /assets, favicons, /, /news/..., etc.) is matched
# first. Anything that reaches here is a client-side route — serve the
# shell so a hard reload or shared deep link boots the app and lets
# Vue Router resolve the path in-browser.
#
# Why this is needed even though /research/{company_id} is declared
# above: Starlette strips `root_path` ("/research") from the request
# path before route matching. A reload of `/research/<company>` arrives,
# gets stripped to `/<company>`, and matches none of the prefixed page
# routes (they'd only match a double-prefixed `/research/research/...`).
# `/login` has no explicit route at all. A single catch-all fixes both
# without re-deriving the post-strip path for each client route.
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> HTMLResponse:
    # API and built assets have their own routes registered earlier and
    # are matched first; only *unknown* paths under those prefixes fall
    # through to here. Return a real 404 for those instead of HTML so
    # clients don't get an HTML body where they expect JSON / a file.
    if full_path.startswith(("api/", "assets/")):
        raise HTTPException(status_code=404, detail="Not Found")
    return _serve_index()
