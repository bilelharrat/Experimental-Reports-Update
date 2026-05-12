"""FastAPI entrypoint for BSH Research Center.

Serves the Vue SPA from `frontend/dist` and mounts the JSON API under `/api`.
"""
from __future__ import annotations

import logging
import os
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
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import claude_runner  # noqa: E402
from .api import router as api_router, require_api_token, _expected_token  # noqa: E402
from .company_translate import translate_company  # noqa: E402
from .storage import bootstrap_seed_data, list_companies, update_company  # noqa: E402

logger = logging.getLogger("bsh.startup")

DIST_DIR = ROOT_DIR / "frontend" / "dist"
ASSETS_DIR = DIST_DIR / "assets"

app = FastAPI(title="bsh-research-center")
app.add_middleware(GZipMiddleware, minimum_size=1024)

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

app.include_router(api_router)


@app.on_event("startup")
def _startup() -> None:
    bootstrap_seed_data()
    if claude_runner.is_available():
        logger.info("Claude Code CLI available — analysis paths enabled.")
    else:
        logger.warning(
            "Claude Code (`claude`) not on PATH — analysis paths will "
            "return errors. Install with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )
    _start_translation_backfill()


def _start_translation_backfill() -> None:
    """Translate any company record that doesn't yet have a `translation`
    block. Runs in a background thread so startup isn't blocked. No-op if
    the Claude CLI isn't installed.
    """
    if not claude_runner.is_available():
        return

    def _worker() -> None:
        try:
            companies = list_companies()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Translation backfill: list_companies failed: %s", exc)
            return
        pending = [c for c in companies if not c.get("translation")]
        if not pending:
            return
        logger.info(
            "Translation backfill: %d company record(s) to translate.",
            len(pending),
        )
        for c in pending:
            cid = c.get("id")
            if not cid:
                continue
            try:
                result = translate_company(c)
                update_company(
                    cid,
                    language=result.get("language"),
                    translation=result.get("translation"),
                )
                if result.get("error"):
                    logger.warning(
                        "Translation backfill for %s: %s", cid, result["error"]
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Translation backfill for %s failed: %s", cid, exc
                )
        logger.info("Translation backfill: complete.")

    threading.Thread(
        target=_worker,
        name="company-translation-backfill",
        daemon=True,
    ).start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/diagnostics", dependencies=[Depends(require_api_token)])
def diagnostics() -> dict:
    """Quick health check for env / config."""
    return {
        "env_file_exists": (ROOT_DIR / ".env").exists(),
        "api_token_configured": bool(_expected_token()),
    }


def _serve_index() -> HTMLResponse:
    """Serve the SPA shell. When ``BSH_RESEARCH_API_TOKEN`` is configured we
    splice a ``<meta>`` tag into ``<head>`` so the in-browser app can read
    the token and forward it on every API request (header or query). The
    page itself is intentionally NOT gated — clients need to load it
    before they can authenticate, and anyone who can already load the
    HTML can also call the API.
    """
    index_path = DIST_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build missing. Run `npm install && npm run build` in frontend/.",
        )
    html_text = index_path.read_text(encoding="utf-8")
    token = _expected_token()
    if token:
        meta_tag = (
            f'<meta name="bsh-research-api-token" '
            f'content="{_html.escape(token, quote=True)}">'
        )
        # Insert just before </head>; fall back to prepending into <head>
        # if for some reason the close tag isn't present.
        if "</head>" in html_text:
            html_text = html_text.replace(
                "</head>", f"  {meta_tag}\n  </head>", 1
            )
        elif "<head>" in html_text:
            html_text = html_text.replace(
                "<head>", f"<head>\n  {meta_tag}", 1
            )
    return HTMLResponse(content=html_text)


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
