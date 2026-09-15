"""Hormuz Console — a per-topic Console session scoped to the Strait of
Hormuz daily reports instead of a company dossier.

It reuses the generic Console machinery wholesale: ``console_store`` for
the on-disk session + transcript, ``console_session`` for the per-session
FIFO queue / ask path / archive / recovery, and
``claude_runner.run_console_hydrate`` for the hydration turn. The only
Hormuz-specific piece is *what gets staged into the session* — the two
most recent days of source reports (and their V3 appendix Markdown when
present) — and *which persona skill* is appended.

The Console id slot (``company_id`` in the generic layer) is the fixed
sentinel ``"hormuz"``; it's only ever a path segment under
``data/consoles/hormuz/sessions/...`` and validates as a slug.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from . import (
    claude_runner,
    console_store,
    hormuz_store,
    job_progress,
)

logger = logging.getLogger(__name__)

# Console id slot (path segment only). Must be a single safe path segment
# that console_store accepts (any lowercased id storage issues) — "hormuz" is.
HORMUZ_ID = "hormuz"

SKILL_PATH = Path(__file__).parent / "skills" / "bsh_hormuz_console.md"

# How many recent source dates to load into a session's context.
RECENT_DAYS = 2


def _resolve_context_docs() -> tuple[list[Path], list[dict]]:
    """The two most recent days of Hormuz material: each date's source
    report file(s) plus that date's V3 appendix Markdown when it exists.

    Returns ``(paths, included_meta)`` where ``included_meta`` is the
    ``{id, kind, filename}`` list console_store records on the session.
    """
    dates = hormuz_store.list_source_dates()[:RECENT_DAYS]
    paths: list[Path] = []
    included: list[dict] = []
    for date in dates:
        for p in hormuz_store.source_files(date):
            paths.append(p)
            included.append(
                {"id": f"{date}/{p.name}", "kind": "hormuz_source", "filename": p.name}
            )
        out = hormuz_store.appendix_output_paths(date)
        for slot in ("cn_md", "en_md"):
            ap = out[slot]
            if ap.exists():
                paths.append(ap)
                included.append(
                    {"id": f"{date}/{slot}", "kind": "hormuz_appendix", "filename": ap.name}
                )
    return paths, included


def context_preview() -> dict:
    """What a new session *would* load — for the UI to show before create."""
    dates = hormuz_store.list_source_dates()[:RECENT_DAYS]
    _, included = _resolve_context_docs()
    return {
        "dates": dates,
        "file_count": len(included),
        "files": [i["filename"] for i in included],
    }


def create_session(*, output_language: str = console_store.DEFAULT_OUTPUT_LANGUAGE) -> dict:
    """Lay out a Hormuz console session, stage the last two days of
    material, and kick off hydration in a background thread. Mirrors
    ``console_session.create_session`` but with Hormuz context + skill.
    """
    sources, included = _resolve_context_docs()
    if not sources:
        raise ValueError(
            "No Hormuz source reports available yet. Upload at least one "
            "daily report in the Source library first."
        )

    meta = console_store.create_session(
        company_id=HORMUZ_ID,
        include_background_docs=False,
        include_library_docs=False,
        included_files=included,
        output_language=output_language,
        title=f"Hormuz · {included[0]['filename'] if included else 'session'}",
    )
    meta = console_store.update_meta(
        HORMUZ_ID, meta["id"],
        hydration_status="in_progress",
        skill_path=str(SKILL_PATH),
    ) or meta

    console_store.stage_docs(
        company_id=HORMUZ_ID, session_id=meta["id"], source_paths=sources,
    )

    progress_path = console_store.hydrate_progress_path(HORMUZ_ID, meta["id"])
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init", kind="console_hydrate",
        title="Hydrating Hormuz console",
        session_id=meta["id"],
        file_count=len(included),
    )

    def _worker() -> None:
        try:
            outcome = claude_runner.run_console_hydrate(
                claude_session_id=meta["claude_session_id"],
                work_dir=console_store.workdir(HORMUZ_ID, meta["id"]),
                file_list=sources,
                skill_path=SKILL_PATH,
                progress=progress,
                output_language=output_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("hormuz hydrate crashed for sid=%s", meta["id"])
            console_store.update_meta(
                HORMUZ_ID, meta["id"],
                hydration_status="error",
                hydration_error=f"{type(exc).__name__}: {exc}",
            )
            return
        new_status = "done" if outcome.get("ok") else "error"
        patch = {"hydration_status": new_status}
        if not outcome.get("ok"):
            patch["hydration_error"] = outcome.get("error")
        console_store.update_meta(HORMUZ_ID, meta["id"], **patch)
        if outcome.get("usage") and outcome.get("cost_usd") is not None:
            console_store.update_tokens(
                HORMUZ_ID, meta["id"],
                usage=outcome["usage"],
                cost_usd=outcome.get("cost_usd") or 0.0,
            )

    threading.Thread(
        target=_worker,
        name=f"hormuz-console-hydrate-{meta['id'][:8]}",
        daemon=True,
    ).start()

    return meta
