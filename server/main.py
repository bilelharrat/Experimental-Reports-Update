"""FastAPI entrypoint for BSH Research Center.

Serves the Vue SPA from `frontend/dist` and mounts the JSON API under `/api`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .storage import bootstrap_seed_data

ROOT_DIR = Path(__file__).resolve().parent.parent
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    icon = DIST_DIR / "favicon.svg"
    if not icon.exists():
        raise HTTPException(status_code=404)
    return FileResponse(icon)
