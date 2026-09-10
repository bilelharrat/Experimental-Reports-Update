"""Append-only JSONL progress log.

A single small primitive used by long-running jobs (deck summary today,
report generation tomorrow) to emit granular progress that the frontend
can consume via SSE. The disk file doubles as a durable record so the
user can replay events if they reload mid-job.

Each line is one JSON object with at minimum `{type, ts}` plus any
job-specific fields the caller wants to attach.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESEARCH_JOB_STATES = (
    "queued",
    "running",
    "done",
    "error",
    "cancelled",
    "recovered",
)
RESEARCH_JOB_TERMINAL_STATES = ("done", "error", "cancelled", "recovered")


class ProgressLog:
    """Thread-safe writer for a JSONL progress file."""

    TERMINAL_TYPES = RESEARCH_JOB_TERMINAL_STATES

    def __init__(self, path: Path, *, truncate: bool = True):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if truncate:
            # Default: truncate so a re-run doesn't surface the old log.
            self.path.write_text("", encoding="utf-8")
        elif not self.path.exists():
            # Append mode but file missing — create empty so the first
            # emit() doesn't race with mkdir.
            self.path.write_text("", encoding="utf-8")

    def emit(self, type_: str, **fields: Any) -> None:
        if "status" not in fields:
            if type_ == "job_init":
                fields["status"] = "queued"
            elif type_ == "stage":
                fields["status"] = (
                    "queued" if fields.get("stage") == "queued" else "running"
                )
            elif type_ in self.TERMINAL_TYPES:
                fields["status"] = type_
        entry = {
            "type": type_,
            "ts": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        if type_ in self.TERMINAL_TYPES:
            # Every finished job passes through here exactly when it turns
            # terminal — the one hook the Task history ledger needs.
            from server import job_history

            job_history.record_terminal(self.path, type_)

    @property
    def is_terminated(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in reversed(f.readlines()[-10:]):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("type") in self.TERMINAL_TYPES:
                        return True
        except Exception:
            return False
        return False


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class ThreadProgress:
    """Stamp every emitted event with a stable `thread` label.

    Wraps a ProgressLog (or another emitter) so one worker's events group
    into one thread row in the job UI, and accumulates that worker's
    cost/duration from `claude_action result` events. The accumulation is
    lock-guarded because several worker threads may share one instance.
    """

    def __init__(self, base, thread: str):
        self._base = base
        self._thread = thread
        self.cost_usd = 0.0
        self.duration_ms = 0
        self._totals_lock = threading.Lock()

    def emit(self, type_: str, **fields: Any) -> None:
        fields.setdefault("thread", self._thread)
        if type_ == "claude_action" and fields.get("action") == "result":
            with self._totals_lock:
                self.cost_usd += _coerce_float(fields.get("cost_usd"))
                self.duration_ms += _coerce_int(fields.get("duration_ms"))
        self._base.emit(type_, **fields)

    @property
    def is_terminated(self) -> bool:
        try:
            return self._base.is_terminated
        except Exception:  # noqa: BLE001
            return False


def scan_progress_state(path: Path) -> dict:
    """Scan a progress JSONL and summarize where the job stands.

    The active-jobs rail, idempotent POST handlers, and recovery paths all
    consume this shape. Job-specific metadata is intentionally permissive so
    each long-running workflow can add fields without changing the scanner.
    """
    state: dict = {
        "exists": path.exists(),
        "terminated": False,
        "terminal_type": None,
        "started_at": None,
        "last_event_at": None,
        "latest_stage": None,
        "latest_stage_key": None,
        "elapsed_ms": None,
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
        "report_ready": False,
        "job_init": None,
        "kind": None,
        "title": None,
        "subtitle": None,
        "latest_action": None,
        "tool_count": 0,
        "thread_count": 0,
        "thread_done_count": 0,
        "thread_failed_count": 0,
        "open_thread_count": 0,
        "threads": [],
        "phase_timings": [],
        "backoff_until": None,
        "backoff_remaining_seconds": None,
        "recoverable": None,
    }
    if not path.exists():
        return state
    threads: dict[str, dict] = {}

    def note_thread(name: Any, status: str, entry: dict) -> None:
        label = str(name or "").strip()
        if not label:
            return
        is_planned = entry.get("type") == "thread_planned" or status == "not_started"
        row = threads.setdefault(
            label,
            {
                "name": label,
                "status": "not_started" if is_planned else "running",
                "planned_at": entry.get("ts") if is_planned else None,
                "started_at": None if is_planned else entry.get("ts"),
                "last_event_at": entry.get("ts"),
                "finished_at": None,
                "error": None,
                "event_count": 0,
                "latest_action": None,
                "elapsed_ms": None,
                "phase_index": entry.get("phase_index"),
                "description": entry.get("description"),
                "estimate_ms": entry.get("estimate_ms"),
                "group": entry.get("group"),
                "parent_thread": entry.get("parent_thread"),
                "pass_id": entry.get("pass_id"),
                "artifact": entry.get("artifact"),
            },
        )
        if is_planned:
            row["planned_at"] = row.get("planned_at") or entry.get("ts")
            if entry.get("phase_index") is not None:
                row["phase_index"] = entry.get("phase_index")
            if entry.get("description"):
                row["description"] = entry.get("description")
            if entry.get("estimate_ms") is not None:
                row["estimate_ms"] = entry.get("estimate_ms")
            for key in ("group", "parent_thread", "pass_id", "artifact"):
                if entry.get(key) is not None:
                    row[key] = entry.get(key)
        if row.get("started_at") is None and not is_planned:
            row["started_at"] = entry.get("ts")
        if not is_planned and entry.get("description"):
            row["description"] = row.get("description") or entry.get("description")
        if row.get("description") is None and entry.get("description"):
            row["description"] = entry.get("description")
        for key in ("group", "parent_thread", "pass_id", "artifact"):
            if entry.get(key) is not None:
                row[key] = entry.get(key)
        if entry.get("ts"):
            row["last_event_at"] = entry.get("ts")
        if not is_planned:
            row["event_count"] = int(row.get("event_count") or 0) + 1
        if entry.get("type") == "claude_action":
            row["latest_action"] = {
                "action": entry.get("action"),
                "tool": entry.get("tool"),
                "preview": entry.get("preview"),
                "text": entry.get("text"),
                "error": entry.get("error"),
                "api_error_status": entry.get("api_error_status"),
                "is_error": entry.get("is_error"),
                "ts": entry.get("ts"),
            }
        if status == "running" and row.get("status") in {"done", "failed"}:
            return
        if status == "not_started" and row.get("status") != "not_started":
            return
        row["status"] = status
        if status in {"done", "failed"}:
            row["finished_at"] = entry.get("ts")
        if status == "failed":
            row["error"] = entry.get("error")

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
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
                elif etype in ProgressLog.TERMINAL_TYPES:
                    state["terminated"] = True
                    state["terminal_type"] = etype
                    if "error" in entry:
                        state["error"] = entry.get("error")
                elif etype == "stage":
                    state["latest_stage_key"] = entry.get("stage")
                    state["latest_stage"] = (
                        entry.get("message") or entry.get("stage")
                    )
                    if entry.get("report_ready"):
                        state["report_ready"] = True
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
                elif etype == "phase_timing":
                    phase_timings = state.setdefault("phase_timings", [])
                    phase_timings.append(entry)
                    if len(phase_timings) > 200:
                        del phase_timings[:-200]
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
                elif etype == "thread_planned":
                    note_thread(
                        entry.get("thread") or entry.get("title"),
                        "not_started",
                        entry,
                    )
                elif etype == "thread_started":
                    note_thread(
                        entry.get("thread") or entry.get("title"),
                        "running",
                        entry,
                    )
                    state["latest_stage_key"] = "thread_started"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Started {entry.get('title') or entry.get('thread') or 'subtask'}"
                    )
                elif etype == "thread_finished":
                    note_thread(
                        entry.get("thread") or entry.get("title"),
                        "done",
                        entry,
                    )
                    state["latest_stage_key"] = "thread_finished"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Completed {entry.get('title') or entry.get('thread') or 'subtask'}"
                    )
                elif etype == "thread_failed":
                    note_thread(
                        entry.get("thread") or entry.get("title"),
                        "failed",
                        entry,
                    )
                    state["latest_stage_key"] = "thread_failed"
                    state["latest_stage"] = (
                        entry.get("message")
                        or f"Failed {entry.get('title') or entry.get('thread') or 'subtask'}"
                    )
                    state["error"] = entry.get("error") or state.get("error")
                elif etype == "claude_action":
                    if entry.get("thread"):
                        note_thread(entry.get("thread"), "running", entry)
                    action = entry.get("action")
                    if action == "result":
                        if entry.get("cost_usd") is not None:
                            state["claude_cost_usd"] = entry["cost_usd"]
                        if entry.get("duration_ms") is not None:
                            state["claude_duration_ms"] = entry["duration_ms"]
                    if action in (
                        "tool_use",
                        "tool_result",
                        "thinking",
                        "init",
                        "result",
                    ):
                        state["latest_action"] = {
                            "action": action,
                            "tool": entry.get("tool"),
                            "preview": entry.get("preview"),
                            "text": entry.get("text"),
                            "error": entry.get("error"),
                            "api_error_status": entry.get("api_error_status"),
                            "is_error": entry.get("is_error"),
                            "ts": entry.get("ts"),
                        }
                    if action == "tool_use":
                        state["tool_count"] += 1
    except Exception:
        pass
    thread_rows = list(threads.values())
    now = datetime.now(timezone.utc)
    state_started = parse_progress_datetime(state.get("started_at"))
    state_finished = None
    if state.get("terminated"):
        state_finished = parse_progress_datetime(state.get("last_event_at"))
    elif state_started is not None:
        state_finished = now
    if state_started is not None and state_finished is not None:
        state["elapsed_ms"] = max(
            0,
            int((state_finished - state_started).total_seconds() * 1000),
        )
    for row in thread_rows:
        started = parse_progress_datetime(row.get("started_at"))
        if started is None:
            continue
        if row.get("status") == "running" and not state.get("terminated"):
            finished = now
        else:
            finished = (
                parse_progress_datetime(row.get("finished_at"))
                or parse_progress_datetime(row.get("last_event_at"))
                or started
            )
        row["elapsed_ms"] = max(0, int((finished - started).total_seconds() * 1000))
    state["threads"] = thread_rows
    state["thread_count"] = len(thread_rows)
    state["thread_done_count"] = sum(
        1 for row in thread_rows if row.get("status") == "done"
    )
    state["thread_failed_count"] = sum(
        1 for row in thread_rows if row.get("status") == "failed"
    )
    state["open_thread_count"] = sum(
        1 for row in thread_rows if row.get("status") == "running"
    )
    return state


def parse_progress_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def seconds_since(value: Any) -> float | None:
    dt = parse_progress_datetime(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def progress_idle_seconds(state: dict) -> float | None:
    return seconds_since(state.get("last_event_at"))


def progress_path_idle_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


# How long a run may sit on a failed StructuredOutput validation before the
# scanner declares it dead. Observed healthy retries take up to ~3 minutes
# to rewrite a large payload (Mill run 2026-09-10: 188s), so 10 minutes
# separates "still rewriting" from "the CLI exited on that rejection".
SCHEMA_RETRY_GRACE_SECONDS = 600.0


def progress_path_recent(path: Path, *, max_idle_seconds: int) -> bool:
    idle = progress_path_idle_seconds(path)
    return idle is not None and idle <= max_idle_seconds


def progress_state_in_flight(
    state: dict,
    *,
    max_idle_seconds: int,
    schema_retry_grace_seconds: float = SCHEMA_RETRY_GRACE_SECONDS,
) -> bool:
    if not state.get("exists") or state.get("terminated"):
        return False
    latest = state.get("latest_action") or {}
    if (
        latest.get("action") == "tool_result"
        and latest.get("tool") == "StructuredOutput"
        and latest.get("is_error")
    ):
        # A schema rejection is routine mid-run: the CLI feeds the error
        # back and the agent retries, sometimes taking minutes to rewrite
        # a large payload before the next event lands. Only a rejection
        # the stream never moved past means the worker died there —
        # treating every fresh rejection as terminal blanked the jobs
        # rail for healthy runs. Takeover-style callers (weekly refresh)
        # pass schema_retry_grace_seconds=0 to keep superseding such logs
        # immediately.
        idle = progress_idle_seconds(state)
        if idle is None or idle > schema_retry_grace_seconds:
            return False
    idle = progress_idle_seconds(state)
    return idle is None or idle <= max_idle_seconds


def scan_active_progress_state(path: Path, *, max_idle_seconds: int) -> dict | None:
    if not progress_path_recent(path, max_idle_seconds=max_idle_seconds):
        return None
    state = scan_progress_state(path)
    return (
        state
        if progress_state_in_flight(state, max_idle_seconds=max_idle_seconds)
        else None
    )


def supersede_progress_file(path: Path, *, reason: str) -> None:
    """Mark a stale progress log terminal, then remove it for a clean rerun."""
    if not path.exists():
        return
    ProgressLog(path, truncate=False).emit(
        "error",
        error=reason,
        terminal=True,
    )
    path.unlink(missing_ok=True)


def cancel_progress_file(path: Path, *, reason: str, **fields: Any) -> dict:
    """Emit a terminal cancellation event without deleting the progress log."""
    progress = ProgressLog(path, truncate=False)
    state = scan_progress_state(path)
    if not state.get("terminated"):
        progress.emit(
            "cancelled",
            status="cancelled",
            reason=reason,
            **fields,
        )
        state = scan_progress_state(path)
    return state
