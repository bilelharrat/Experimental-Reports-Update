"""FastAPI entrypoint for BSH Research Center.

Serves the Vue SPA from `frontend/dist` and mounts the JSON API under `/api`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root BEFORE importing modules that read env vars
# (text_analysis, companies_ai, etc. check OPENAI_API_KEY at call time, but
# threads spawned by the API inherit the process environment from import
# time, so we want this set as early as possible). This works regardless of
# how uvicorn was launched — IDE, `uv run`, plain shell, etc. — so the user
# isn't dependent on `./run.sh` sourcing .env.
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

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .api import router as api_router  # noqa: E402
from .storage import bootstrap_seed_data  # noqa: E402

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
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        logger.info(
            "OPENAI_API_KEY loaded — analysis enabled (len=%d, prefix=%s…)",
            len(key),
            key[:7],
        )
    else:
        logger.warning(
            "OPENAI_API_KEY not set — analysis paths will fall back to "
            "stubs. Put it in .env at the project root."
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/diagnostics")
def diagnostics() -> dict:
    """Quick health check for env / config — useful when analysis claims
    a missing key and you want to confirm what the running process sees.
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    return {
        "openai_api_key_set": bool(key),
        "openai_api_key_prefix": (key[:7] + "…") if key else None,
        "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        "env_file_exists": (ROOT_DIR / ".env").exists(),
    }


def _serve_index() -> FileResponse:
    index_path = DIST_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build missing. Run `npm install && npm run build` in frontend/.",
        )
    return FileResponse(index_path)


@app.get("/")
def root() -> FileResponse:
    return _serve_index()


@app.get("/research/{company_id}")
def research_page(company_id: str) -> FileResponse:  # noqa: ARG001 — handled client-side
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
