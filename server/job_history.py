"""Durable ledger of finished AI tasks — powers the Task history panel.

The jobs rail only shows in-flight work: the moment a stream turns
terminal its row disappears, taking the timings with it. Every terminal
event already funnels through ``ProgressLog.emit``, so that is the one
hook: it calls :func:`record_terminal`, which summarizes the finished
stream and appends one JSON line to ``data/jobs/history.jsonl``.

Rows are append-only and deduped on read by (log path, started_at) —
recovery and cancel paths may emit more than one terminal event for the
same run, and fixed-path kinds (weekly refresh) reuse one file across
runs. Supersede events ("stale log cleaned before a rerun") are noise,
not finished work, and are skipped. The ledger also serves transcript
replay: ``/api/jobs/log?path=history:<row id>`` resolves a row's
recorded stream path, so history rows open in the same log modal as
live ones without per-kind token mapping.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from server import storage

logger = logging.getLogger(__name__)

# Rewrite the file down to _TRIM_KEEP rows once it exceeds _TRIM_AT.
_TRIM_AT = 400
_TRIM_KEEP = 200

_LOCK = threading.Lock()


def _history_file() -> Path:
    # storage.DATA_DIR is monkeypatched in tests; resolve at call time.
    return storage.DATA_DIR / "jobs" / "history.jsonl"


def record_terminal(stream_path: Path, terminal_type: str) -> None:
    """Append one history row for a stream that just turned terminal.

    Best-effort: a history failure must never break the job that is
    finishing. Streams without a ``job_init`` (bare progress files that
    never appeared in the rail) and supersede terminations are skipped.
    """
    try:
        _record_terminal(stream_path, terminal_type)
    except Exception:  # noqa: BLE001
        logger.warning("failed to record job history", exc_info=True)


def _record_terminal(stream_path: Path, terminal_type: str) -> None:
    from server import job_progress

    state = job_progress.scan_progress_state(stream_path)
    init = state.get("job_init") or {}
    if not init:
        return
    error = str(state.get("error") or "")
    if "superseded" in error.lower():
        return
    try:
        log_path = str(stream_path.resolve().relative_to(storage.DATA_DIR.resolve()))
    except ValueError:
        # Outside the data dir (shouldn't happen) — keep the row, lose replay.
        log_path = None
    row = {
        "id": uuid.uuid4().hex[:12],
        "kind": state.get("kind") or init.get("kind"),
        "title": state.get("title") or init.get("title"),
        "subtitle": state.get("subtitle") or init.get("subtitle"),
        "terminal_type": terminal_type,
        "error": error or None,
        "started_at": state.get("started_at"),
        "finished_at": state.get("last_event_at"),
        "elapsed_ms": state.get("elapsed_ms"),
        "claude_cost_usd": state.get("claude_cost_usd"),
        "report_ready": bool(state.get("report_ready")),
        "log_path": log_path,
        "report_id": init.get("report_id"),
        "company_id": init.get("company_id"),
    }
    path = _history_file()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        _maybe_trim(path)


def _maybe_trim(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _TRIM_AT:
        return
    path.write_text(
        "\n".join(lines[-_TRIM_KEEP:]) + "\n", encoding="utf-8"
    )


def _rows() -> list[dict]:
    path = _history_file()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def list_history(limit: int = 30) -> list[dict]:
    """Newest-first finished tasks, deduped to the last row per run."""
    deduped: dict[Any, dict] = {}
    for row in _rows():  # file order == chronological; later rows win
        key = (row.get("log_path"), row.get("started_at")) if row.get(
            "log_path"
        ) else row.get("id")
        deduped[key] = row
    ordered = sorted(
        deduped.values(),
        key=lambda r: str(r.get("finished_at") or ""),
        reverse=True,
    )
    return ordered[: max(1, min(int(limit or 30), 100))]


def resolve_log_path(row_id: str) -> Path:
    """Resolve a ``history:<row id>`` log token to the recorded stream path."""
    for row in _rows():
        if row.get("id") == row_id and row.get("log_path"):
            return storage.DATA_DIR / str(row["log_path"])
    raise ValueError(f"unknown history row: {row_id}")
