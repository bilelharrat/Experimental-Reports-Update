"""Persistent pre-memo analysis sessions for Serena's memo workflow.

The memo generator writes the final DOCX deliverables. This module owns the
work that happens before that point: strategic risks, priorities,
research prompts, thesis spine, chart plans, narrative hooks, private-company
benchmarking, and readiness gates.

The first implementation is deterministic and local. It gives the UI and
storage model a stable contract; individual tools can later be replaced with
Claude-backed jobs without changing the dashboard shape.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import claude_runner, company_paths, job_progress, research_eval, research_store, run_ledger, storage
from .risk_workbench import (
    DISPOSITIONS,
    FRAMINGS,
    apply_framing,
    complete_risk,
    company_evidence_rows,
    default_priorities,
    merge_task_evidence_into_risk,
    ordered_active_risks,
    packet_strategic_risk_lines,
    suggested_disposition,
)

ANALYSIS_ROOT = storage.DATA_DIR / "serena_analysis"
TRAINING_ROOT = storage.DATA_DIR / "serena_training"
SESSION_VERSION = 1
MEMO_WORK_PRODUCT_VERSION_SCHEMA_VERSION = 1
ACTIVE_JOB_MAX_IDLE_SECONDS = int(
    os.environ.get("BSH_ACTIVE_JOB_MAX_IDLE_SECONDS", "1800")
)
RESEARCH_TASK_CONCURRENCY = max(
    1,
    int(os.environ.get("BSH_RESEARCH_TASK_CONCURRENCY", "2")),
)

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "strategic_risk_mapper",
        "label": "Strategic Risk Mapper",
        "description": (
            "Generate risk and valuation sensitivities and failure modes that "
            "shape the memo."
        ),
        "stage": "core",
        "critical": True,
        "run_label": "Map risks",
        "ready_label": "Risk map ready for prioritization",
        "input_label": "Pick the sensitivities that deserve diligence.",
        "produces": "strategic_risks",
    },
    {
        "name": "priority_prompt_harness",
        "label": "Risk Prioritizer",
        "description": (
            "Rank the risks and convert selected ones into risk and valuation "
            "sensitivity review."
        ),
        "stage": "core",
        "critical": True,
        "run_label": "Build source review queue",
        "ready_label": "Source review queue ready for selection",
        "input_label": "Select sources and run only the sensitivity reviews that matter.",
        "depends_on": ["strategic_risk_mapper"],
        "produces": "research_tasks",
    },
    {
        "name": "thesis_spine_builder",
        "label": "Thesis Spine",
        "description": (
            "Draft memo-grade highlights, risks, recommendation logic, and "
            "risk or valuation sensitivities."
        ),
        "stage": "core",
        "critical": True,
        "run_label": "Draft thesis",
        "ready_label": "Thesis ready for review",
        "input_label": "Edit the claims and sensitivities before approval.",
        "depends_on": ["strategic_risk_mapper", "priority_prompt_harness"],
        "produces": "thesis_spine",
    },
    {
        "name": "infographic_source_brief",
        "label": "Visual Source Brief",
        "description": "Optional: find claims and metrics safe enough for visuals.",
        "stage": "optional",
        "run_label": "Prepare visual sources",
        "ready_label": "Visual source brief ready for choices",
        "input_label": "Resolve any claim, metric, or visual-use questions.",
        "produces": "infographic_source_brief",
    },
    {
        "name": "chart_spec_builder",
        "label": "Chart Plan Builder",
        "description": "Optional: plan charts or infographics for the memo.",
        "stage": "optional",
        "run_label": "Plan visuals",
        "ready_label": "Chart plans ready for inclusion choices",
        "input_label": "Choose which visuals belong in the memo.",
        "depends_on": ["infographic_source_brief"],
        "produces": "chart_specs",
    },
    {
        "name": "narrative_hooks",
        "label": "Narrative Hook Planner",
        "description": "Optional: propose source-backed opening and closing angles.",
        "stage": "optional",
        "run_label": "Draft hooks",
        "ready_label": "Narrative hooks ready for selection",
        "input_label": "Choose the memo tone and selected hooks.",
        "depends_on": ["infographic_source_brief"],
        "produces": "narrative_hooks",
    },
    {
        "name": "private_benchmark_dashboard",
        "label": "Benchmark Context",
        "description": "Optional: pressure-test the company against public comps.",
        "stage": "optional",
        "run_label": "Build comps",
        "ready_label": "Benchmark context ready for review",
        "input_label": "Decide which comps are relevant enough to cite.",
        "produces": "benchmark_dashboard",
    },
    {
        "name": "memo_grader",
        "label": "Memo Grader",
        "description": "After memo: grade a completed memo and save lessons.",
        "stage": "after_memo",
        "run_label": "Grade memo",
        "ready_label": "Memo grade ready for review",
        "input_label": "Select a completed memo run before grading.",
        "produces": "memo_grader",
    },
    {
        "name": "readiness_check",
        "label": "Memo Readiness Gate",
        "description": "System readiness refresh.",
        "stage": "hidden",
        "visibility": "hidden",
        "run_label": "Refresh readiness",
        "produces": "readiness",
    },
]

_TOOL_NAMES = {t["name"] for t in TOOL_DEFINITIONS}
_CLAUDE_BACKED_TOOLS = {
    "strategic_risk_mapper",
    "thesis_spine_builder",
    "infographic_source_brief",
    "chart_spec_builder",
    "narrative_hooks",
    "private_benchmark_dashboard",
    "memo_grader",
}
_TASK_STATUSES = {"not_started", "running", "done", "error", "skipped"}
_TASK_STATUSES.add("cancelled")
_READINESS_REVIEW_STATUSES = {"open", "reviewed", "waived"}
_PRESERVED_TASK_FIELDS = {
    "status",
    "result_summary",
    "result_basis",
    "result_generated_by",
    "result_updated_at",
    "started_at",
    "completed_at",
    "last_run_at",
    "error",
    "run_job_id",
    "result_payload",
    "answer",
    "supporting_evidence",
    "contradicting_evidence",
    "remaining_evidence_limits",
    "open_questions",
    "sources_checked",
    "confidence",
    "analyst_review_score",
    "job_metrics",
    "selected_source_ids",
    "search_plan",
    "recovered_at",
    "cancelled_at",
}
_RESEARCH_TASK_CANCEL_EVENTS: dict[str, threading.Event] = {}
_RESEARCH_TASK_CANCEL_LOCK = threading.RLock()
_RESEARCH_TASK_RUN_SEMAPHORE = threading.BoundedSemaphore(
    RESEARCH_TASK_CONCURRENCY
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]", "", (value or "").lower())
    if not cleaned:
        raise ValueError("Invalid company id")
    return cleaned


def _company_dir(company_id: str) -> Path:
    return ANALYSIS_ROOT / company_paths.storage_key(company_id)


def session_dir(company_id: str, session_id: str) -> Path:
    return _company_dir(company_id) / _safe_id(session_id)


def session_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "session.yaml"


def memo_work_product_versions_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "memo_work_product_versions.json"


def memo_work_product_version_files_root(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "memo_work_product_version_files"


def training_dir(company_id: str) -> Path:
    return TRAINING_ROOT / _safe_id(company_id)


def memo_lessons_path(company_id: str) -> Path:
    return training_dir(company_id) / "serena_memo_lessons.md"


def completed_memo_runs(company_id: str) -> list[dict]:
    safe_company = _safe_id(company_id)
    rows: list[dict] = []
    for report in storage.list_reports():
        if report.get("company_id") != safe_company:
            continue
        if report.get("status") != "complete":
            continue
        if report.get("kind") not in {
            "investment_memo_latestage",
            "buffett_investment_memo",
        }:
            continue
        rows.append({
            "id": report.get("id"),
            "run_id": report.get("run_id"),
            "run_dir": report.get("run_dir"),
            "created_at": report.get("created_at"),
            "updated_at": report.get("updated_at"),
            "stage": report.get("stage"),
            "analysis_session_id": report.get("analysis_session_id"),
            "memo_files": report.get("memo_files") or [],
        })
    return rows


def research_task_progress_path(company_id: str, session_id: str, task_id: str) -> Path:
    safe_task_id = str(task_id or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", safe_task_id):
        raise ValueError("Invalid research task id")
    return session_dir(company_id, session_id) / "logs" / f"{safe_task_id}.progress.jsonl"


def analysis_tool_progress_path(company_id: str, session_id: str, tool_name: str) -> Path:
    safe_tool_name = str(tool_name or "").strip()
    if safe_tool_name not in _TOOL_NAMES:
        raise ValueError(f"Unknown memo-analysis tool: {tool_name}")
    return (
        session_dir(company_id, session_id)
        / "logs"
        / "tools"
        / f"{safe_tool_name}.progress.jsonl"
    )


def _research_task_cancel_key(
    company_id: str, session_id: str, task_id: str
) -> str:
    return f"{company_id}/{session_id}/{task_id}"


def _start_research_task_cancel_event(key: str) -> threading.Event:
    event = threading.Event()
    with _RESEARCH_TASK_CANCEL_LOCK:
        _RESEARCH_TASK_CANCEL_EVENTS[key] = event
    return event


def _request_research_task_cancel(key: str) -> bool:
    with _RESEARCH_TASK_CANCEL_LOCK:
        event = _RESEARCH_TASK_CANCEL_EVENTS.get(key)
    if event is None:
        return False
    event.set()
    return True


def _clear_research_task_cancel_event(
    key: str, event: threading.Event | None
) -> None:
    if event is None:
        return
    with _RESEARCH_TASK_CANCEL_LOCK:
        if _RESEARCH_TASK_CANCEL_EVENTS.get(key) is event:
            _RESEARCH_TASK_CANCEL_EVENTS.pop(key, None)


def _progress_cancelled(path: Path) -> bool:
    return job_progress.scan_progress_state(path).get("terminal_type") == "cancelled"


def _emit_cancelled_progress(path: Path, *, reason: str, **fields: Any) -> dict:
    try:
        return job_progress.cancel_progress_file(path, reason=reason, **fields)
    except Exception:
        logger.exception("failed to emit research-task cancellation: %s", path)
        return job_progress.scan_progress_state(path)


def tool_uses_background_job(tool_name: str) -> bool:
    return tool_name in _CLAUDE_BACKED_TOOLS


def _parse_progress_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _seconds_since(value: Any) -> float | None:
    dt = _parse_progress_datetime(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _progress_path_idle_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _scan_progress_log(path: Path) -> dict:
    state = {
        "exists": path.exists(),
        "terminated": False,
        "terminal_type": None,
        "terminal_error": None,
        "started_at": None,
        "last_event_at": None,
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
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("ts")
                if state["started_at"] is None and ts:
                    state["started_at"] = ts
                if ts:
                    state["last_event_at"] = ts
                if entry.get("type") in job_progress.ProgressLog.TERMINAL_TYPES:
                    state["terminated"] = True
                    state["terminal_type"] = entry.get("type")
                    state["terminal_error"] = entry.get("error")
    except Exception:
        logger.exception("failed to scan serena progress log: %s", path)
    return state


def _reference_run_idle_seconds(*values: Any) -> float | None:
    for value in values:
        idle = _seconds_since(value)
        if idle is not None:
            return idle
    return None


def _stale_run_reason(
    progress_path: Path,
    *,
    max_idle_seconds: int,
    started_at: Any = None,
    last_run_at: Any = None,
) -> str | None:
    """Return why a running session job is stale, or None if it may be active."""
    if not progress_path.exists():
        run_idle = _reference_run_idle_seconds(last_run_at, started_at)
        if run_idle is not None and run_idle <= max_idle_seconds:
            return None
        return "progress log is missing"

    state = _scan_progress_log(progress_path)
    if state.get("terminated"):
        terminal = state.get("terminal_type") or "terminal event"
        if state.get("terminal_error"):
            return f"progress log ended with {terminal}: {state['terminal_error']}"
        return f"progress log already ended with {terminal}"

    path_idle = _progress_path_idle_seconds(progress_path)
    if path_idle is not None and path_idle > max_idle_seconds:
        return f"progress log has been idle for {int(path_idle)} seconds"

    event_idle = _seconds_since(state.get("last_event_at"))
    if event_idle is not None and event_idle > max_idle_seconds:
        return f"progress log has had no events for {int(event_idle)} seconds"

    return None


def _recovered_run_error(reason: str) -> str:
    return f"Recovered interrupted run: {reason}. Start it again to rerun."


def _emit_recovery_error(progress_path: Path | None, message: str, **fields: Any) -> None:
    if progress_path is None:
        return
    try:
        progress = job_progress.ProgressLog(progress_path, truncate=False)
        if not progress.is_terminated:
            progress.emit("error", recovered=True, error=message, **fields)
    except Exception:
        logger.exception("failed to emit serena recovery event: %s", progress_path)


def _recover_stale_runs_in_session(
    session: dict,
    *,
    max_idle_seconds: int | None = None,
) -> int:
    max_idle = (
        ACTIVE_JOB_MAX_IDLE_SECONDS
        if max_idle_seconds is None
        else int(max_idle_seconds)
    )
    company_id = str(session.get("company_id") or "")
    session_id = str(session.get("id") or "")
    if not company_id or not session_id:
        return 0

    now = _now()
    recovered = 0
    touched_tasks = False
    artifacts = session.setdefault("artifacts", {})
    task_artifact = artifacts.get("research_tasks")
    tasks = task_artifact.get("tasks") if isinstance(task_artifact, dict) else []
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict) or task.get("status") != "running":
                continue
            task_id = str(task.get("id") or "")
            progress_path: Path | None
            try:
                progress_path = research_task_progress_path(company_id, session_id, task_id)
                reason = _stale_run_reason(
                    progress_path,
                    max_idle_seconds=max_idle,
                    started_at=task.get("started_at"),
                    last_run_at=task.get("last_run_at"),
                )
            except ValueError as exc:
                progress_path = None
                reason = str(exc)
            if not reason:
                continue
            message = _recovered_run_error(reason)
            task["status"] = "error"
            task["completed_at"] = now
            task["last_run_at"] = now
            task["error"] = message
            task["recovered_at"] = now
            task.setdefault("run_job_id", f"{company_id}/{session_id}/{task_id}")
            _emit_recovery_error(
                progress_path,
                message,
                kind="serena_research_task",
                company_id=company_id,
                session_id=session_id,
                task_id=task_id,
            )
            recovered += 1
            touched_tasks = True

    tool_runs = session.setdefault("tool_runs", {})
    if isinstance(tool_runs, dict):
        for tool_name, run in list(tool_runs.items()):
            if not isinstance(run, dict) or run.get("status") != "running":
                continue
            progress_path = None
            try:
                progress_path = analysis_tool_progress_path(
                    company_id, session_id, str(tool_name)
                )
                reason = _stale_run_reason(
                    progress_path,
                    max_idle_seconds=max_idle,
                    last_run_at=run.get("last_run_at"),
                )
            except ValueError as exc:
                reason = str(exc)
            if not reason:
                continue
            message = _recovered_run_error(reason)
            run["status"] = "error"
            run["last_run_at"] = now
            run["summary"] = f"{_tool_label(str(tool_name))} was interrupted before completion."
            run["error"] = message
            run["recovered_at"] = now
            run.setdefault("run_job_id", f"{company_id}/{session_id}/{tool_name}")
            _emit_recovery_error(
                progress_path,
                message,
                kind="serena_analysis_tool",
                company_id=company_id,
                session_id=session_id,
                tool_name=str(tool_name),
            )
            recovered += 1

    if recovered:
        if touched_tasks:
            _touch_research_tasks(session)
        _refresh_memo_packet(session)
    return recovered


def recover_stale_runs(*, max_idle_seconds: int | None = None) -> int:
    """Sweep all Serena sessions and mark interrupted running jobs as errors."""
    if not ANALYSIS_ROOT.exists():
        return 0
    recovered = 0
    with _LOCK:
        for path in sorted(ANALYSIS_ROOT.glob("*/*/session.yaml")):
            session = _load_session(path)
            if not isinstance(session, dict):
                continue
            count = _recover_stale_runs_in_session(
                session,
                max_idle_seconds=max_idle_seconds,
            )
            if count:
                recovered += count
                _write_session(session)
    return recovered


def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else default


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return copy.deepcopy(default)
    return data if data is not None else copy.deepcopy(default)


def _write_yaml(path: Path, data: Any) -> None:
    storage._write_yaml(path, data)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    tmp.replace(path)


def _session_files(company_id: str) -> list[Path]:
    cdir = _company_dir(company_id)
    if not cdir.exists():
        return []
    return sorted(cdir.glob("*/session.yaml"))


def _load_session(path: Path) -> dict | None:
    data = _read_yaml(path, None)
    return data if isinstance(data, dict) else None


def _write_session(session: dict) -> dict:
    session["updated_at"] = _now()
    _write_yaml(session_path(session["company_id"], session["id"]), session)
    _write_artifacts(session)
    return session


def _write_artifacts(session: dict) -> None:
    base = session_dir(session["company_id"], session["id"])
    artifacts = session.get("artifacts") or {}
    for name, value in artifacts.items():
        if not isinstance(name, str):
            continue
        if name == "memo_packet":
            (base / "memo_packet.md").write_text(str(value or ""), encoding="utf-8")
        else:
            _write_yaml(base / f"{name}.yaml", value)


def _new_session(company: dict) -> dict:
    company_id = str(company.get("id") or "")
    if not company_id:
        raise ValueError("Company record has no id")
    now = _now()
    return {
        "id": uuid.uuid4().hex[:12],
        "version": SESSION_VERSION,
        "company_id": company_id,
        "company_name": company.get("name") or company_id,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_for_memo": False,
        "tool_runs": {},
        "artifacts": {
            "input_manifest": _input_manifest(company_id),
        },
    }


def _input_manifest(company_id: str) -> dict:
    files = []
    for entry in research_store.list_files(company_id):
        files.append({
            "id": entry.get("id"),
            "filename": entry.get("filename") or entry.get("stored_name"),
            "kind": entry.get("kind"),
            "size_bytes": entry.get("size_bytes"),
            "uploaded_at": entry.get("uploaded_at"),
            "has_quick_summary": bool(entry.get("quick_summary")),
        })
    return {
        "research_files": files,
        "research_file_count": len(files),
        "document_library_excluded": True,
        "notes": (
            "Serena analysis sessions use data/research/<slug>/ only. "
            "data/uploads/<slug>/ remains excluded from memo analysis."
        ),
    }


def get_current_session(company_id: str, *, create: bool = True) -> dict | None:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        sessions = [
            s for p in _session_files(company_id)
            if (s := _load_session(p)) is not None
        ]
        sessions.sort(key=lambda s: str(s.get("updated_at", "")), reverse=True)
        if sessions:
            session = sessions[0]
            session.setdefault("artifacts", {})
            session["artifacts"]["input_manifest"] = _input_manifest(company_id)
            if _recover_stale_runs_in_session(session):
                _write_session(session)
            return _decorate(session)
        if not create:
            return None
        session = _new_session(company)
        _write_session(session)
        return _decorate(session)


def get_session(company_id: str, session_id: str) -> dict | None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        if session and _recover_stale_runs_in_session(session):
            _write_session(session)
        return _decorate(session) if session else None


def ensure_memo_packet_current(session: dict) -> dict:
    """Persist a fresh memo packet only when its source artifacts changed."""
    with _LOCK:
        raw = _strip_decorations(session)
        if _memo_packet_is_current(raw):
            return _decorate(raw)
        _refresh_memo_packet(raw)
        return _decorate(_write_session(raw))


def has_unapproved_work(company_id: str) -> bool:
    """Return whether a company has draft Memo Studio work not approved yet."""
    with _LOCK:
        session = get_current_session(company_id, create=False)
        return _has_unapproved_work(session) if session else False


def memo_work_product_catalog(company_id: str) -> dict:
    """Return a read-only catalog of Memo Studio work products and boundaries."""
    session = get_current_session(company_id, create=True)
    if session is None:
        raise ValueError(f"Unknown company: {company_id}")
    return _memo_work_product_catalog(session)


def list_run_ledger(company_id: str) -> list[dict]:
    """Return normalized Memo Studio run rows for the current analysis session."""
    session = get_current_session(company_id, create=True)
    if session is None:
        raise ValueError(f"Unknown company: {company_id}")
    rows = _memo_run_ledger(session)
    rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
    return rows


def run_tool(company_id: str, tool_name: str) -> dict:
    if tool_name not in _TOOL_NAMES:
        raise ValueError(f"Unknown memo-analysis tool: {tool_name}")
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            session = _new_session(company)
        # Remove derived presentation fields before persistence.
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        artifacts["input_manifest"] = _input_manifest(company_id)

        try:
            summary = _run_tool_impl(company, artifacts, tool_name)
            status = "done"
            error = None
        except Exception as exc:  # noqa: BLE001 - persisted for UI visibility
            summary = f"{type(exc).__name__}: {exc}"
            status = "error"
            error = summary
        session.setdefault("tool_runs", {})[tool_name] = {
            "status": status,
            "last_run_at": _now(),
            "summary": summary,
            "error": error,
        }
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def start_analysis_tool_job(company_id: str, tool_name: str) -> dict:
    """Mark a Claude-backed analysis tool running and launch its job."""
    if not tool_uses_background_job(tool_name):
        return run_tool(company_id, tool_name)
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        tool_runs = session.setdefault("tool_runs", {})
        current_run = tool_runs.get(tool_name) or {}
        if current_run.get("status") == "running":
            return _decorate(session)
        session_id = str(session["id"])
        now = _now()
        job_id = f"{company_id}/{session_id}/{tool_name}"
        tool_runs[tool_name] = {
            "status": "running",
            "last_run_at": now,
            "summary": "Running with Claude.",
            "error": None,
            "run_job_id": job_id,
        }
        _write_session(session)
        company_snapshot = copy.deepcopy(company)
        decorated = _decorate(session)

    threading.Thread(
        target=_run_analysis_tool_job,
        args=(company_id, session_id, tool_name, company_snapshot),
        name=f"serena-analysis-tool-{company_id}-{tool_name}",
        daemon=True,
    ).start()
    return decorated


def patch_artifact(company_id: str, artifact_name: str, patch: dict) -> dict:
    if not re.match(r"^[a-z0-9_]+$", artifact_name):
        raise ValueError("Invalid artifact name")
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        current = artifacts.get(artifact_name)
        if artifact_name == "risk_priorities":
            risks = _ensure_risks(company, artifacts)
            priorities = patch.get("priorities") if isinstance(patch, dict) else []
            normalized = _normalize_priorities(risks, priorities)
            for row in normalized:
                row["human_ranked"] = True
            artifacts["risk_priorities"] = {
                **(current if isinstance(current, dict) else {}),
                **(patch if isinstance(patch, dict) else {}),
                "updated_at": _now(),
                "priorities": normalized,
            }
            _refresh_research_tasks(company, artifacts)
        elif artifact_name == "strategic_risks":
            risks = _ensure_risks(company, artifacts)
            merged = _merge_strategic_risk_patch(company, risks, patch)
            artifacts["strategic_risks"] = {
                **(current if isinstance(current, dict) else {}),
                "generated_at": (
                    current.get("generated_at") if isinstance(current, dict) else None
                ) or _now(),
                "updated_at": _now(),
                "source_basis": (
                    current.get("source_basis") if isinstance(current, dict) else None
                ) or _source_basis(company),
                "risks": merged,
            }
        elif artifact_name == "readiness_reviews":
            artifacts["readiness_reviews"] = _merge_readiness_reviews(
                current,
                patch,
            )
        elif isinstance(current, dict) and isinstance(patch, dict):
            artifacts[artifact_name] = {**current, **patch}
        else:
            artifacts[artifact_name] = patch
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def refine_risk(
    company_id: str,
    risk_id: str,
    *,
    framing: str = "other",
    analyst_note: str = "",
) -> dict:
    """Apply an analyst framing to one risk and optionally regenerate it."""
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        risks = _ensure_risks(company, artifacts)
        target = next(
            (
                copy.deepcopy(risk)
                for risk in risks
                if isinstance(risk, dict) and str(risk.get("id") or "") == str(risk_id)
            ),
            None,
        )
        if target is None:
            raise ValueError(f"Unknown risk: {risk_id}")

    framed = apply_framing(target, framing, analyst_note)
    refined: dict | None = None
    claude_error: str | None = None
    try:
        refined, claude_error = claude_runner.run_serena_risk_refine(
            company=company,
            risk=framed,
            framing=framed.get("framing") or framing,
            analyst_note=analyst_note,
            research_dir=research_store.RESEARCH_ROOT / company_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena risk refine crashed")
        claude_error = f"{type(exc).__name__}: {exc}"

    merged_source = {
        **framed,
        **(refined if isinstance(refined, dict) else {}),
        "id": target.get("id"),
        "framing": framed.get("framing"),
        "edited_by_human": True,
        "analyst_note": analyst_note or framed.get("analyst_note") or "",
        "generated_by": (
            "claude_code" if isinstance(refined, dict) else "deterministic_fallback"
        ),
    }
    if claude_error and not isinstance(refined, dict):
        merged_source["claude_error"] = claude_error
    final = complete_risk(merged_source, company, index=1)

    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        risks = _ensure_risks(company, artifacts)
        updated = []
        found = False
        for risk in risks:
            if str(risk.get("id") or "") == str(risk_id):
                updated.append(final)
                found = True
            else:
                updated.append(risk)
        if not found:
            raise ValueError(f"Unknown risk: {risk_id}")
        risk_artifact = artifacts.get("strategic_risks")
        artifacts["strategic_risks"] = {
            **(risk_artifact if isinstance(risk_artifact, dict) else {}),
            "risks": updated,
            "updated_at": _now(),
        }
        priority_artifact = artifacts.get("risk_priorities")
        if isinstance(priority_artifact, dict):
            rows = priority_artifact.get("priorities")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and str(row.get("risk_id") or "") == str(risk_id):
                        row["framing"] = final.get("framing")
                        if analyst_note:
                            row["analyst_note"] = analyst_note
                        row["human_ranked"] = True
                artifacts["risk_priorities"] = {
                    **priority_artifact,
                    "priorities": _normalize_priorities(updated, rows),
                    "updated_at": _now(),
                }
        task_artifact = artifacts.get("research_tasks")
        if isinstance(task_artifact, dict):
            for task in task_artifact.get("tasks") or []:
                if isinstance(task, dict) and str(task.get("risk_id") or "") == str(risk_id):
                    task["prompt"] = final.get("research_prompt")
                    task["search_plan"] = _research_task_search_plan(final)
                    task["title"] = f"Research: {final.get('title')}"
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def patch_research_task(company_id: str, task_id: str, patch: dict) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    if not isinstance(patch, dict):
        raise ValueError("Research task patch must be an object")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        task = _find_research_task(session.setdefault("artifacts", {}), task_id)
        if task is None:
            raise ValueError(f"Unknown research task: {task_id}")
        _apply_research_task_patch(task, patch)
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def run_research_task(company_id: str, task_id: str) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        task = _find_research_task(artifacts, task_id)
        if task is None:
            raise ValueError(f"Unknown research task: {task_id}")
        risks = _risks_by_id(artifacts)
        risk = risks.get(str(task.get("risk_id") or ""))
        now = _now()
        task["status"] = "done"
        task.setdefault("started_at", now)
        task["completed_at"] = now
        task["last_run_at"] = now
        task["error"] = None
        structured = _fallback_research_task_result(
            company,
            task,
            risk,
            source_manifest=_selected_sources_for_task(company_id, task),
        )
        task.update(_research_task_result_fields(structured))
        task["result_basis"] = _research_result_basis(task, risk)
        task["result_generated_by"] = "deterministic_local"
        task["result_updated_at"] = now
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def start_research_task_job(company_id: str, task_id: str) -> dict:
    """Mark a selected research task running and launch its background job."""
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        task = _find_research_task(artifacts, task_id)
        if task is None:
            raise ValueError(f"Unknown research task: {task_id}")
        if task.get("status") == "running":
            return _decorate(session)
        risk = _risks_by_id(artifacts).get(str(task.get("risk_id") or ""))
        now = _now()
        session_id = str(session["id"])
        safe_task_id = str(task.get("id") or task_id)
        job_id = f"{company_id}/{session_id}/{safe_task_id}"
        cancel_key = _research_task_cancel_key(
            company_id, session_id, safe_task_id
        )
        cancel_event = _start_research_task_cancel_event(cancel_key)
        task["status"] = "running"
        task["started_at"] = now
        task["completed_at"] = None
        task["last_run_at"] = now
        task["error"] = None
        task["run_job_id"] = job_id
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)
        task_snapshot = copy.deepcopy(task)
        risk_snapshot = copy.deepcopy(risk)
        company_snapshot = copy.deepcopy(company)
        decorated = _decorate(session)

    research_dir, source_manifest = _research_task_source_context(
        company_id,
        session_id,
        safe_task_id,
        task_snapshot,
    )
    threading.Thread(
        target=_run_research_task_job,
        args=(
            company_id,
            session_id,
            safe_task_id,
            company_snapshot,
            task_snapshot,
            risk_snapshot,
            research_dir,
            source_manifest,
            cancel_key,
            cancel_event,
        ),
        name=f"serena-research-task-{company_id}-{safe_task_id}",
        daemon=True,
    ).start()
    return decorated


def start_selected_research_task_jobs(
    company_id: str,
    *,
    retry_failed: bool = True,
) -> dict:
    """Launch all runnable Memo Studio research tasks for the current session."""
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        tasks = (
            session.get("artifacts", {})
            .get("research_tasks", {})
            .get("tasks", [])
        )
        if not isinstance(tasks, list):
            tasks = []
        task_ids: list[str] = []
        statuses: dict[str, str] = {}
        for task in tasks:
            if not isinstance(task, dict) or not task.get("id"):
                continue
            task_id = str(task["id"])
            status = str(task.get("status") or "not_started")
            if status == "running":
                statuses[task_id] = "already_running"
                continue
            if status == "done":
                statuses[task_id] = "already_done"
                continue
            if status == "skipped":
                statuses[task_id] = "skipped"
                continue
            if status in {"error", "cancelled"} and not retry_failed:
                statuses[task_id] = f"retry_disabled_{status}"
                continue
            task_ids.append(task_id)

    latest = None
    for task_id in task_ids:
        latest = start_research_task_job(company_id, task_id)
        statuses[task_id] = "launched"

    if latest is None:
        latest = get_current_session(company_id, create=True)
    payload = copy.deepcopy(latest)
    payload["batch"] = {
        "kind": "serena_research_task_batch",
        "concurrency": RESEARCH_TASK_CONCURRENCY,
        "retry_failed": retry_failed,
        "launched_task_ids": task_ids,
        "statuses": statuses,
    }
    return payload


def cancel_research_task_job(company_id: str, task_id: str) -> dict:
    """Cancel a running Memo Studio research task."""
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    progress_path: Path | None = None
    cancel_key: str | None = None
    with _LOCK:
        session = get_current_session(company_id, create=False)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        artifacts = session.setdefault("artifacts", {})
        task = _find_research_task(artifacts, task_id)
        if task is None:
            raise ValueError(f"Unknown research task: {task_id}")
        now = _now()
        session_id = str(session["id"])
        safe_task_id = str(task.get("id") or task_id)
        cancel_key = _research_task_cancel_key(
            company_id, session_id, safe_task_id
        )
        progress_path = research_task_progress_path(
            company_id, session_id, safe_task_id
        )
        _request_research_task_cancel(cancel_key)
        task["status"] = "cancelled"
        task["completed_at"] = now
        task["last_run_at"] = now
        task["cancelled_at"] = now
        task["error"] = "Research task cancelled"
        task.setdefault("run_job_id", cancel_key)
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)
        decorated = _decorate(session)

    _emit_cancelled_progress(
        progress_path,
        reason="Memo Studio research task cancelled",
        kind="serena_research_task",
        company_id=company_id,
        session_id=session_id,
        task_id=safe_task_id,
    )
    return decorated


def _tool_label(tool_name: str) -> str:
    definition = next(
        (item for item in TOOL_DEFINITIONS if item.get("name") == tool_name),
        None,
    )
    return str((definition or {}).get("label") or tool_name)


def _run_analysis_tool_job(
    company_id: str,
    session_id: str,
    tool_name: str,
    company: dict,
) -> None:
    progress = job_progress.ProgressLog(
        analysis_tool_progress_path(company_id, session_id, tool_name)
    )
    company_name = company.get("name") or company_id
    label = _tool_label(tool_name)
    progress.emit(
        "job_init",
        kind="serena_analysis_tool",
        title=label,
        subtitle=company_name,
        company_id=company_id,
        session_id=session_id,
        tool_name=tool_name,
    )
    progress.emit(
        "stage",
        stage="starting",
        message=f"Starting {label}",
        tool_name=tool_name,
    )

    if tool_name == "thesis_spine_builder":
        _run_thesis_spine_builder_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name == "private_benchmark_dashboard":
        _run_private_benchmark_dashboard_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name == "infographic_source_brief":
        _run_infographic_source_brief_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name == "chart_spec_builder":
        _run_chart_spec_builder_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name == "narrative_hooks":
        _run_narrative_hooks_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name == "memo_grader":
        _run_memo_grader_job(
            company_id,
            session_id,
            company,
            progress,
        )
        return

    if tool_name != "strategic_risk_mapper":
        error = f"Unsupported background analysis tool: {tool_name}"
        _finish_analysis_tool_job(
            company_id,
            session_id,
            tool_name,
            status="error",
            summary=error,
            error=error,
        )
        progress.emit("error", tool_name=tool_name, error=error)
        return

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_strategic_risk_mapper(
            company=company,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            lessons_path=(
                memo_lessons_path(company_id)
                if memo_lessons_path(company_id).exists()
                else None
            ),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena analysis tool crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        with _LOCK:
            session = _load_session(session_path(company_id, session_id))
            previous_artifact = (
                session.get("artifacts", {}).get("strategic_risks")
                if isinstance(session, dict)
                else None
            )
            previous_priority_artifact = (
                session.get("artifacts", {}).get("risk_priorities")
                if isinstance(session, dict)
                else None
            )
        previous_risks = (
            previous_artifact.get("risks")
            if isinstance(previous_artifact, dict)
            else []
        )
        previous_priorities = (
            previous_priority_artifact.get("priorities")
            if isinstance(previous_priority_artifact, dict)
            else []
        )
        risks = _carry_human_risk_edits(
            previous_risks,
            _coerce_strategic_risks(result.get("risks"), company),
        )
        artifact = {
            "generated_at": _now(),
            "risks": risks,
            "source_basis": {
                **_source_basis(company),
                **(
                    result.get("source_basis")
                    if isinstance(result.get("source_basis"), dict)
                    else {}
                ),
            },
            "generated_by": "claude_code",
            "result_payload": result,
        }
        artifacts_patch: dict[str, Any] = {"strategic_risks": artifact}
        carried = _carry_human_priorities(previous_risks, previous_priorities, risks)
        if carried is not None:
            temp_artifacts = {
                "strategic_risks": artifact,
                "risk_priorities": {
                    **(previous_priority_artifact if isinstance(previous_priority_artifact, dict) else {}),
                    "updated_at": _now(),
                    "priorities": carried,
                },
                "research_tasks": (
                    session.get("artifacts", {}).get("research_tasks")
                    if isinstance(session, dict)
                    else None
                ) or {},
            }
            _refresh_research_tasks(company, temp_artifacts)
            artifacts_patch["risk_priorities"] = temp_artifacts["risk_priorities"]
            artifacts_patch["research_tasks"] = temp_artifacts["research_tasks"]
        summary = f"Generated {len(risks)} strategic risks with Claude."
        _finish_analysis_tool_job(
            company_id,
            session_id,
            tool_name,
            status="done",
            summary=summary,
            error=None,
            artifacts_patch=artifacts_patch,
        )
        progress.emit("done", tool_name=tool_name, summary=summary)
        return

    message = error or "Claude returned no strategic risk result"
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        previous = (
            session.get("artifacts", {}).get("strategic_risks")
            if isinstance(session, dict)
            else None
        )
    previous_risks = (
        previous.get("risks")
        if isinstance(previous, dict)
        else None
    )
    if isinstance(previous_risks, list) and previous_risks:
        _finish_analysis_tool_job(
            company_id,
            session_id,
            tool_name,
            status="error",
            summary=f"Claude strategic risk mapper failed: {message}",
            error=message,
        )
        progress.emit("error", tool_name=tool_name, error=message)
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback risks",
        tool_name=tool_name,
    )
    risks = _strategic_risks(company)
    fallback_artifact = {
        "generated_at": _now(),
        "risks": risks,
        "source_basis": _source_basis(company),
        "generated_by": "deterministic_fallback",
        "claude_error": message,
    }
    summary = f"Generated {len(risks)} deterministic fallback strategic risks."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        tool_name,
        status="done",
        summary=summary,
        error=f"Claude strategic risk fallback: {message}",
        artifacts_patch={"strategic_risks": fallback_artifact},
    )
    progress.emit(
        "done",
        tool_name=tool_name,
        fallback=True,
        error=message,
        summary=summary,
    )


def _run_thesis_spine_builder_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )
    had_risks = bool(
        artifacts.get("strategic_risks", {}).get("risks")
        if isinstance(artifacts.get("strategic_risks"), dict)
        else False
    )
    risks = _ensure_risks(company, artifacts)
    priority_rows = _priority_rows(artifacts)
    artifacts["ordered_strategic_risks"] = ordered_active_risks(risks, priority_rows)
    ensured_patch: dict[str, Any] = {}
    if not had_risks and isinstance(artifacts.get("strategic_risks"), dict):
        ensured_patch["strategic_risks"] = artifacts["strategic_risks"]

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_thesis_spine_builder(
            company=company,
            artifacts=artifacts,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            lessons_path=(
                memo_lessons_path(company_id)
                if memo_lessons_path(company_id).exists()
                else None
            ),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena thesis spine builder crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        thesis = _coerce_thesis_spine(result, company, artifacts)
        thesis["generated_by"] = "claude_code"
        thesis["result_payload"] = result
        if isinstance(result.get("source_basis"), dict):
            thesis["source_basis"] = {
                **_source_basis(company),
                **result["source_basis"],
            }
        else:
            thesis["source_basis"] = _source_basis(company)
        summary = (
            f"Drafted {len(thesis.get('investment_highlights') or [])} "
            "investment highlights and "
            f"{len(thesis.get('investment_risks') or [])} risks with Claude."
        )
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "thesis_spine_builder",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={**ensured_patch, "thesis_spine": thesis},
        )
        progress.emit(
            "done",
            tool_name="thesis_spine_builder",
            summary=summary,
        )
        return

    message = error or "Claude returned no thesis spine result"
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        previous = (
            session.get("artifacts", {}).get("thesis_spine")
            if isinstance(session, dict)
            else None
        )
    previous_highlights = (
        previous.get("investment_highlights")
        if isinstance(previous, dict)
        else None
    )
    if isinstance(previous_highlights, list) and previous_highlights:
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "thesis_spine_builder",
            status="error",
            summary=f"Claude thesis spine builder failed: {message}",
            error=message,
        )
        progress.emit("error", tool_name="thesis_spine_builder", error=message)
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback thesis spine",
        tool_name="thesis_spine_builder",
    )
    fallback = _thesis_spine(company, risks, priority_rows)
    fallback["generated_by"] = "deterministic_fallback"
    fallback["claude_error"] = message
    summary = "Drafted deterministic fallback thesis spine."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "thesis_spine_builder",
        status="done",
        summary=summary,
        error=f"Claude thesis spine fallback: {message}",
        artifacts_patch={**ensured_patch, "thesis_spine": fallback},
    )
    progress.emit(
        "done",
        tool_name="thesis_spine_builder",
        fallback=True,
        error=message,
        summary=summary,
    )


def _run_private_benchmark_dashboard_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_private_benchmark_dashboard(
            company=company,
            artifacts=artifacts,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena benchmark dashboard crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        dashboard = _coerce_benchmark_dashboard(result, company)
        dashboard["generated_by"] = "claude_code"
        dashboard["result_payload"] = result
        summary = (
            f"Built benchmark dashboard with "
            f"{len(dashboard.get('public_comps') or [])} public comps."
        )
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "private_benchmark_dashboard",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={"benchmark_dashboard": dashboard},
        )
        progress.emit(
            "done",
            tool_name="private_benchmark_dashboard",
            summary=summary,
        )
        return

    message = error or "Claude returned no benchmark dashboard result"
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        previous = (
            session.get("artifacts", {}).get("benchmark_dashboard")
            if isinstance(session, dict)
            else None
        )
    previous_comps = (
        previous.get("public_comps")
        if isinstance(previous, dict)
        else None
    )
    if isinstance(previous_comps, list) and previous_comps:
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "private_benchmark_dashboard",
            status="error",
            summary=f"Claude benchmark dashboard failed: {message}",
            error=message,
        )
        progress.emit(
            "error",
            tool_name="private_benchmark_dashboard",
            error=message,
        )
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback benchmark dashboard",
        tool_name="private_benchmark_dashboard",
    )
    fallback = _benchmark_dashboard(company)
    fallback["generated_by"] = "deterministic_fallback"
    fallback["claude_error"] = message
    summary = "Built deterministic fallback benchmark dashboard."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "private_benchmark_dashboard",
        status="done",
        summary=summary,
        error=f"Claude benchmark fallback: {message}",
        artifacts_patch={"benchmark_dashboard": fallback},
    )
    progress.emit(
        "done",
        tool_name="private_benchmark_dashboard",
        fallback=True,
        error=message,
        summary=summary,
    )


def _run_infographic_source_brief_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_infographic_source_brief(
            company=company,
            artifacts=artifacts,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            lessons_path=(
                memo_lessons_path(company_id)
                if memo_lessons_path(company_id).exists()
                else None
            ),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena infographic source brief crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        brief = _coerce_infographic_source_brief(result, company, artifacts)
        brief["generated_by"] = "claude_code"
        brief["result_payload"] = result
        summary = (
            f"Built infographic source brief with "
            f"{len(brief.get('compact_claims') or [])} claims and "
            f"{len(brief.get('numeric_metrics') or [])} metrics."
        )
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "infographic_source_brief",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={"infographic_source_brief": brief},
        )
        progress.emit(
            "done",
            tool_name="infographic_source_brief",
            summary=summary,
        )
        return

    message = error or "Claude returned no infographic source brief result"
    previous = artifacts.get("infographic_source_brief")
    if _infographic_source_brief_has_content(previous):
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "infographic_source_brief",
            status="error",
            summary=f"Claude infographic source brief failed: {message}",
            error=message,
        )
        progress.emit(
            "error",
            tool_name="infographic_source_brief",
            error=message,
        )
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback infographic source brief",
        tool_name="infographic_source_brief",
    )
    fallback = _infographic_source_brief(company, artifacts)
    fallback["generated_by"] = "deterministic_fallback"
    fallback["claude_error"] = message
    summary = "Built deterministic fallback infographic source brief."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "infographic_source_brief",
        status="done",
        summary=summary,
        error=f"Claude infographic source brief fallback: {message}",
        artifacts_patch={"infographic_source_brief": fallback},
    )
    progress.emit(
        "done",
        tool_name="infographic_source_brief",
        fallback=True,
        error=message,
        summary=summary,
    )


def _ensure_infographic_source_brief_for_job(
    company: dict,
    artifacts: dict,
) -> tuple[dict, dict]:
    current = artifacts.get("infographic_source_brief")
    if _infographic_source_brief_has_content(current):
        return artifacts, {}
    ensured = _infographic_source_brief(company, artifacts)
    ensured["generated_by"] = "deterministic_dependency"
    artifacts = copy.deepcopy(artifacts)
    artifacts["infographic_source_brief"] = ensured
    return artifacts, {"infographic_source_brief": ensured}


def _run_chart_spec_builder_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )
    artifacts, ensured_patch = _ensure_infographic_source_brief_for_job(
        company,
        artifacts,
    )

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_chart_spec_builder(
            company=company,
            artifacts=artifacts,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena chart spec builder crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        charts = _coerce_chart_specs(
            result,
            company,
            artifacts,
            previous=artifacts.get("chart_specs"),
        )
        charts["generated_by"] = "claude_code"
        charts["result_payload"] = result
        summary = (
            f"Built {len(charts.get('specs') or [])} infographic plans with Claude."
        )
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "chart_spec_builder",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={**ensured_patch, "chart_specs": charts},
        )
        progress.emit("done", tool_name="chart_spec_builder", summary=summary)
        return

    message = error or "Claude returned no chart spec result"
    previous = artifacts.get("chart_specs")
    previous_specs = (
        previous.get("specs") if isinstance(previous, dict) else None
    )
    if isinstance(previous_specs, list) and previous_specs:
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "chart_spec_builder",
            status="error",
            summary=f"Claude chart spec builder failed: {message}",
            error=message,
            artifacts_patch=ensured_patch,
        )
        progress.emit("error", tool_name="chart_spec_builder", error=message)
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback infographic plans",
        tool_name="chart_spec_builder",
    )
    fallback = _coerce_chart_specs(
        _chart_specs(company),
        company,
        artifacts,
        previous=previous,
    )
    fallback["generated_by"] = "deterministic_fallback"
    fallback["claude_error"] = message
    summary = "Built deterministic fallback infographic plans."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "chart_spec_builder",
        status="done",
        summary=summary,
        error=f"Claude chart spec fallback: {message}",
        artifacts_patch={**ensured_patch, "chart_specs": fallback},
    )
    progress.emit(
        "done",
        tool_name="chart_spec_builder",
        fallback=True,
        error=message,
        summary=summary,
    )


def _run_narrative_hooks_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )
    artifacts, ensured_patch = _ensure_infographic_source_brief_for_job(
        company,
        artifacts,
    )

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_narrative_hooks(
            company=company,
            artifacts=artifacts,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena narrative hook planner crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        hooks = _coerce_narrative_hooks(
            result,
            company,
            artifacts,
            previous=artifacts.get("narrative_hooks"),
        )
        hooks["generated_by"] = "claude_code"
        hooks["result_payload"] = result
        summary = (
            f"Built {len(hooks.get('openings') or [])} openings, "
            f"{len(hooks.get('transitions') or [])} transitions, and "
            f"{len(hooks.get('endings') or [])} closings."
        )
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "narrative_hooks",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={**ensured_patch, "narrative_hooks": hooks},
        )
        progress.emit("done", tool_name="narrative_hooks", summary=summary)
        return

    message = error or "Claude returned no narrative hook result"
    previous = artifacts.get("narrative_hooks")
    previous_openings = (
        previous.get("openings") if isinstance(previous, dict) else None
    )
    if isinstance(previous_openings, list) and previous_openings:
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "narrative_hooks",
            status="error",
            summary=f"Claude narrative hook planner failed: {message}",
            error=message,
            artifacts_patch=ensured_patch,
        )
        progress.emit("error", tool_name="narrative_hooks", error=message)
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback narrative hooks",
        tool_name="narrative_hooks",
    )
    fallback = _coerce_narrative_hooks(
        _narrative_hooks(company, artifacts),
        company,
        artifacts,
        previous=previous,
    )
    fallback["generated_by"] = "deterministic_fallback"
    fallback["claude_error"] = message
    summary = "Built deterministic fallback narrative hooks."
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "narrative_hooks",
        status="done",
        summary=summary,
        error=f"Claude narrative hook fallback: {message}",
        artifacts_patch={**ensured_patch, "narrative_hooks": fallback},
    )
    progress.emit(
        "done",
        tool_name="narrative_hooks",
        fallback=True,
        error=message,
        summary=summary,
    )


def _coerce_memo_grader(value: Any, *, report: dict) -> dict:
    payload = value if isinstance(value, dict) else {}
    report_id = str(payload.get("completed_report_id") or report.get("id") or "")
    run_id = payload.get("completed_run_id") or report.get("run_id")
    scores: list[dict] = []
    for row in payload.get("scores") if isinstance(payload.get("scores"), list) else []:
        if not isinstance(row, dict):
            continue
        area = _clean_text(row.get("area"), limit=120)
        if not area:
            continue
        score = _number_or_none(row.get("score"))
        scores.append({
            "area": area,
            "score": score if score is not None else 0.0,
            "rationale": _clean_text(row.get("rationale"), limit=700),
        })
        if len(scores) >= 12:
            break
    if not scores:
        scores = [
            {
                "area": "Evidence quality",
                "score": 0.0,
                "rationale": "Could not grade this area from available artifacts.",
            }
        ]
    return {
        "updated_at": _now(),
        "status": "graded",
        "completed_report_id": report_id,
        "completed_run_id": run_id,
        "scores": scores,
        "strongest_sections": _string_list(payload.get("strongest_sections"))[:10],
        "weakest_sections": _string_list(payload.get("weakest_sections"))[:10],
        "evidence_limits": _string_list(
            payload.get("evidence_limits") or payload.get("missing_diligence")
        )[:12],
        "rewrite_guidance": _string_list(payload.get("rewrite_guidance"))[:12],
        "lessons_for_future_memo_runs": _string_list(
            payload.get("lessons_for_future_memo_runs")
        )[:12],
        "source_files_reviewed": _string_list(payload.get("source_files_reviewed"))[:20],
        "confidence": _confidence(payload.get("confidence")),
    }


def _fallback_memo_grader(report: dict, *, error: str | None = None) -> dict:
    return {
        "updated_at": _now(),
        "status": "graded",
        "completed_report_id": report.get("id"),
        "completed_run_id": report.get("run_id"),
        "scores": [
            {
                "area": "Evidence quality",
                "score": 0.0,
                "rationale": "Claude grading was unavailable; Serena must review the memo manually.",
            }
        ],
        "strongest_sections": [],
        "weakest_sections": ["Manual grading required."],
        "evidence_limits": ["Run Claude-backed memo grading when available."],
        "rewrite_guidance": ["Use the completed memo and memo packet for manual review."],
        "lessons_for_future_memo_runs": [
            "Do not reuse this fallback as a quality signal; rerun memo grading with Claude."
        ],
        "source_files_reviewed": [],
        "confidence": "low",
        "generated_by": "deterministic_fallback",
        "claude_error": error,
    }


_LESSON_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bClosing Confirmations?\b", re.IGNORECASE), "Risk and valuation sensitivities"),
    (re.compile(r"\bWe back\b", re.IGNORECASE), "Use firm-as-subject deal English for"),
    (re.compile(r"\bWe invest behind\b", re.IGNORECASE), "BSH invests in"),
    (re.compile(r"\bmatters? at IC\b", re.IGNORECASE), "changes valuation support"),
    (re.compile(r"\bmissing diligence\b", re.IGNORECASE), "evidence limits"),
    (re.compile(r"\breviewer prompts?\b", re.IGNORECASE), "operator review notes"),
    (re.compile(r"\bsource traces?\b", re.IGNORECASE), "source-class evidence"),
    (re.compile(r"\bmemo packet\b", re.IGNORECASE), "source brief"),
    (re.compile(r"\bBSH should\b", re.IGNORECASE), "the recommendation is that BSH commit"),
    (re.compile(r"\(for BSH\)", re.IGNORECASE), ""),
)


def _sanitize_memo_lesson(value: Any) -> str:
    text = _clean_text(value, limit=900)
    for pattern, replacement in _LESSON_REWRITES:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -")
    return text


def _write_memo_lessons(company_id: str, grader: dict) -> Path:
    path = memo_lessons_path(company_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lessons = [
        lesson
        for lesson in (
            _sanitize_memo_lesson(item)
            for item in grader.get("lessons_for_future_memo_runs") or []
        )
        if lesson
    ]
    lines = [
        f"# Serena Memo Lessons — {company_id}",
        "",
        f"Last updated: {_now()}",
        "",
        f"## Report {grader.get('completed_report_id') or 'unknown'}",
        "",
    ]
    if lessons:
        for lesson in lessons:
            lines.append(f"- {lesson}")
    else:
        lines.append("- No reusable lessons captured yet.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run_memo_grader_job(
    company_id: str,
    session_id: str,
    company: dict,
    progress: job_progress.ProgressLog,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        artifacts = copy.deepcopy(
            session.get("artifacts", {}) if isinstance(session, dict) else {}
        )
    grader_config = artifacts.get("memo_grader") if isinstance(artifacts.get("memo_grader"), dict) else {}
    selected_report_id = str(grader_config.get("selected_report_id") or "").strip()
    completed = completed_memo_runs(company_id)
    if not selected_report_id and completed:
        selected_report_id = str(completed[0].get("id") or "")
    report = storage.get_report(selected_report_id) if selected_report_id else None
    if report is None:
        artifact = {
            "updated_at": _now(),
            "status": "waiting_for_completed_memo",
            "selected_report_id": selected_report_id or None,
            "completed_memo_runs": completed,
            "next_step": "Select a completed memo run before grading.",
        }
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "memo_grader",
            status="done",
            summary="Memo grader is waiting for a completed memo.",
            error=None,
            artifacts_patch={"memo_grader": artifact},
        )
        progress.emit("done", tool_name="memo_grader", summary=artifact["next_step"])
        return

    run_dir = None
    if report.get("run_dir"):
        run_dir = (storage.DATA_DIR.parent / str(report["run_dir"])).resolve()
    memo_packet = session_dir(company_id, session_id) / "memo_packet.md"
    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_memo_grader(
            company=company,
            report=report,
            memo_packet_path=memo_packet,
            run_dir=run_dir,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena memo grader crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        grader = _coerce_memo_grader(result, report=report)
        grader["generated_by"] = "claude_code"
        grader["result_payload"] = result
        lessons_path = _write_memo_lessons(company_id, grader)
        grader["lessons_path"] = str(lessons_path)
        summary = f"Graded completed memo {grader['completed_report_id']}."
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "memo_grader",
            status="done",
            summary=summary,
            error=None,
            artifacts_patch={"memo_grader": grader},
        )
        progress.emit("done", tool_name="memo_grader", summary=summary)
        return

    message = error or "Claude returned no memo grader result"
    previous_status = str(grader_config.get("status") or "")
    if previous_status == "graded" and grader_config.get("completed_report_id"):
        _finish_analysis_tool_job(
            company_id,
            session_id,
            "memo_grader",
            status="error",
            summary=f"Claude memo grader failed: {message}",
            error=message,
        )
        progress.emit("error", tool_name="memo_grader", error=message)
        return

    fallback = _fallback_memo_grader(report, error=message)
    lessons_path = _write_memo_lessons(company_id, fallback)
    fallback["lessons_path"] = str(lessons_path)
    _finish_analysis_tool_job(
        company_id,
        session_id,
        "memo_grader",
        status="done",
        summary="Built deterministic fallback memo grading artifact.",
        error=f"Claude memo grader fallback: {message}",
        artifacts_patch={"memo_grader": fallback},
    )
    progress.emit(
        "done",
        tool_name="memo_grader",
        fallback=True,
        error=message,
        summary="Built deterministic fallback memo grading artifact.",
    )


def _finish_analysis_tool_job(
    company_id: str,
    session_id: str,
    tool_name: str,
    *,
    status: str,
    summary: str,
    error: str | None,
    artifacts_patch: dict | None = None,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        if session is None:
            logger.warning(
                "serena analysis tool finished for missing session company=%s session=%s tool=%s",
                company_id,
                session_id,
                tool_name,
            )
            return
        if artifacts_patch:
            session.setdefault("artifacts", {}).update(artifacts_patch)
        session.setdefault("tool_runs", {})[tool_name] = {
            "status": status,
            "last_run_at": _now(),
            "summary": summary,
            "error": error,
            "run_job_id": f"{company_id}/{session_id}/{tool_name}",
        }
        _refresh_memo_packet(session)
        _write_session(session)
    if tool_name == "strategic_risk_mapper":
        try:
            from . import tracking_updates

            tracking_updates.complete_auto_run_for_job(
                company_id,
                job_kind="serena_tool",
                tool_name=tool_name,
                success=str(status).lower() == "done",
            )
        except Exception:  # noqa: BLE001
            logger.exception("tracking auto-run finalize failed for %s", company_id)


def _run_research_task_job(
    company_id: str,
    session_id: str,
    task_id: str,
    company: dict,
    task: dict,
    risk: dict | None,
    research_dir: Path | None = None,
    source_manifest: list[dict] | None = None,
    cancel_key: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    started = time.monotonic()
    progress_path = research_task_progress_path(company_id, session_id, task_id)
    source_manifest = source_manifest or []
    cancel_fields = {
        "kind": "serena_research_task",
        "company_id": company_id,
        "session_id": session_id,
        "task_id": task_id,
    }
    if (
        (cancel_event is not None and cancel_event.is_set())
        or _progress_cancelled(progress_path)
    ):
        if not _progress_cancelled(progress_path):
            _emit_cancelled_progress(
                progress_path,
                reason="Memo Studio research task cancelled",
                **cancel_fields,
            )
        _clear_research_task_cancel_event(cancel_key or "", cancel_event)
        return
    progress = job_progress.ProgressLog(progress_path)
    company_name = company.get("name") or company_id
    progress.emit(
        "job_init",
        kind="serena_research_task",
        title=task.get("title") or "Memo Studio research task",
        subtitle=company_name,
        company_id=company_id,
        session_id=session_id,
        task_id=task_id,
        risk_id=task.get("risk_id"),
        selected_source_ids=task.get("selected_source_ids") or [],
        source_count=len(source_manifest),
    )
    progress.emit(
        "stage",
        stage="starting",
        message="Starting selected research prompt",
        task_id=task_id,
    )
    if cancel_event is not None and cancel_event.is_set():
        _emit_cancelled_progress(
            progress_path,
            reason="Memo Studio research task cancelled",
            **cancel_fields,
        )
        _clear_research_task_cancel_event(cancel_key or "", cancel_event)
        return

    result: dict | None = None
    error: str | None = None
    progress.emit(
        "stage",
        stage="queued",
        message="Waiting for research task slot",
        task_id=task_id,
        concurrency=RESEARCH_TASK_CONCURRENCY,
    )
    with _RESEARCH_TASK_RUN_SEMAPHORE:
        if (
            (cancel_event is not None and cancel_event.is_set())
            or _progress_cancelled(progress_path)
        ):
            if not _progress_cancelled(progress_path):
                _emit_cancelled_progress(
                    progress_path,
                    reason="Memo Studio research task cancelled",
                    **cancel_fields,
                )
            _clear_research_task_cancel_event(cancel_key or "", cancel_event)
            return
        progress.emit(
            "stage",
            stage="running",
            message="Running selected research prompt",
            task_id=task_id,
        )
        try:
            result, error = claude_runner.run_serena_research_task(
                company=company,
                task=task,
                risk=risk,
                research_dir=research_dir or research_store.RESEARCH_ROOT / company_id,
                source_manifest=source_manifest,
                progress=progress,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("serena research task crashed")
            error = f"{type(exc).__name__}: {exc}"

    if (
        (cancel_event is not None and cancel_event.is_set())
        or _progress_cancelled(progress_path)
    ):
        if not _progress_cancelled(progress_path):
            _emit_cancelled_progress(
                progress_path,
                reason="Memo Studio research task cancelled",
                **cancel_fields,
            )
        _clear_research_task_cancel_event(cancel_key or "", cancel_event)
        return

    structured_result = (
        _normalize_research_task_result(
            result,
            source_manifest=source_manifest,
        )
        if result and not error
        else None
    )
    if structured_result is not None and not error:
        summary = structured_result["answer"]
        structured_result.setdefault("job_metrics", {})["duration_ms"] = int(
            (time.monotonic() - started) * 1000
        )
        now = _now()
        _finish_research_task_job(
            company_id,
            session_id,
            task_id,
            {
                "status": "done",
                "completed_at": now,
                "last_run_at": now,
                "error": None,
                **_research_task_result_fields(structured_result),
                "result_basis": _research_result_basis(task, risk) + ["claude_code"],
                "result_generated_by": "claude_code",
                "result_updated_at": now,
            },
        )
        progress.emit(
            "done",
            task_id=task_id,
            result_summary=summary,
            confidence=structured_result["confidence"],
            source_count=len(structured_result.get("sources_checked") or []),
        )
        _clear_research_task_cancel_event(cancel_key or "", cancel_event)
        return

    message = error or "Claude returned no structured answer"
    previous_summary = str(task.get("result_summary") or "").strip()
    now = _now()
    if previous_summary:
        _finish_research_task_job(
            company_id,
            session_id,
            task_id,
            {
                "status": "error",
                "completed_at": now,
                "last_run_at": now,
                "error": message,
            },
        )
        progress.emit("error", task_id=task_id, error=message)
        _clear_research_task_cancel_event(cancel_key or "", cancel_event)
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback result",
        task_id=task_id,
    )
    fallback = _fallback_research_task_result(
        company,
        task,
        risk,
        source_manifest=source_manifest,
    )
    fallback["fallback"] = True
    fallback["claude_error"] = message
    fallback.setdefault("job_metrics", {})["duration_ms"] = int(
        (time.monotonic() - started) * 1000
    )
    _finish_research_task_job(
        company_id,
        session_id,
        task_id,
        {
            "status": "done",
            "completed_at": now,
            "last_run_at": now,
            "error": f"Claude research fallback: {message}",
            **_research_task_result_fields(fallback),
            "result_basis": _research_result_basis(task, risk),
            "result_generated_by": "deterministic_fallback",
            "result_updated_at": now,
        },
    )
    progress.emit(
        "done",
        task_id=task_id,
        fallback=True,
        error=message,
        result_summary=fallback["answer"],
        confidence=fallback["confidence"],
    )
    _clear_research_task_cancel_event(cancel_key or "", cancel_event)


def _finish_research_task_job(
    company_id: str,
    session_id: str,
    task_id: str,
    patch: dict,
) -> None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        if session is None:
            logger.warning(
                "serena research task finished for missing session company=%s session=%s task=%s",
                company_id,
                session_id,
                task_id,
            )
            return
        artifacts = session.setdefault("artifacts", {})
        task = _find_research_task(artifacts, task_id)
        if task is None:
            logger.warning(
                "serena research task finished for missing task company=%s session=%s task=%s",
                company_id,
                session_id,
                task_id,
            )
            return
        for key, value in patch.items():
            task[key] = value
        _merge_completed_task_into_parent_risk(
            storage.get_company(company_id) or {},
            artifacts,
            task,
        )
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)


def approve(company_id: str) -> dict:
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
        readiness, _ = _readiness(session)
        blockers = readiness.get("approval_blockers") or []
        if blockers:
            labels = [
                str(item.get("label") or item.get("id") or "readiness blocker")
                for item in blockers[:5]
                if isinstance(item, dict)
            ]
            suffix = "; ".join(labels)
            more = len(blockers) - len(labels)
            if more > 0:
                suffix = f"{suffix}; plus {more} more" if suffix else f"{more} blockers"
            raise ValueError(
                "Memo analysis is not ready for approval"
                + (f": {suffix}" if suffix else ".")
            )
        session["status"] = "approved"
        session["approved_at"] = _now()
        session["approved_for_memo"] = True
        artifacts = session.setdefault("artifacts", {})
        thesis = artifacts.get("thesis_spine")
        if isinstance(thesis, dict):
            thesis["approved"] = True
            thesis["approved_at"] = session["approved_at"]
        _refresh_memo_packet(session)
        _write_session(session)
        return _decorate(session)


def _run_tool_impl(company: dict, artifacts: dict, tool_name: str) -> str:
    if tool_name == "strategic_risk_mapper":
        risks = _strategic_risks(company)
        artifacts["strategic_risks"] = {
            "generated_at": _now(),
            "risks": risks,
            "source_basis": _source_basis(company),
            "generated_by": "deterministic_fallback",
        }
        return f"Generated {len(risks)} strategic risks."
    if tool_name == "priority_prompt_harness":
        risks = _ensure_risks(company, artifacts)
        previous = artifacts.get("risk_priorities")
        previous_rows = previous.get("priorities") if isinstance(previous, dict) else None
        priorities = default_priorities(risks, previous_rows)
        artifacts["risk_priorities"] = {
            "updated_at": _now(),
            "priorities": priorities,
        }
        _refresh_research_tasks(company, artifacts)
        tasks = artifacts["research_tasks"]["tasks"]
        return f"Ranked {len(priorities)} risks and created {len(tasks)} research tasks."
    if tool_name == "thesis_spine_builder":
        risks = _ensure_risks(company, artifacts)
        artifacts["thesis_spine"] = _thesis_spine(
            company,
            risks,
            _priority_rows(artifacts),
        )
        return "Drafted investment highlights, risks, recommendation logic, and top gates."
    if tool_name == "infographic_source_brief":
        artifacts["infographic_source_brief"] = _infographic_source_brief(
            company,
            artifacts,
        )
        return "Distilled source brief for infographic and narrative planning."
    if tool_name == "chart_spec_builder":
        if not _infographic_source_brief_has_content(
            artifacts.get("infographic_source_brief")
        ):
            artifacts["infographic_source_brief"] = _infographic_source_brief(
                company,
                artifacts,
            )
        artifacts["chart_specs"] = _coerce_chart_specs(
            _chart_specs(company),
            company,
            artifacts,
            previous=artifacts.get("chart_specs"),
        )
        return "Drafted image-generation-ready infographic plan."
    if tool_name == "narrative_hooks":
        if not _infographic_source_brief_has_content(
            artifacts.get("infographic_source_brief")
        ):
            artifacts["infographic_source_brief"] = _infographic_source_brief(
                company,
                artifacts,
            )
        artifacts["narrative_hooks"] = _coerce_narrative_hooks(
            _narrative_hooks(company, artifacts),
            company,
            artifacts,
            previous=artifacts.get("narrative_hooks"),
        )
        return "Drafted source-backed narrative hooks."
    if tool_name == "private_benchmark_dashboard":
        artifacts["benchmark_dashboard"] = _benchmark_dashboard(company)
        return "Drafted private-company benchmark dashboard."
    if tool_name == "memo_grader":
        artifacts["memo_grader"] = {
            "updated_at": _now(),
            "status": "waiting_for_completed_memo",
            "rubric": [
                "Investment highlights sharpness",
                "Risk sharpness",
                "Evidence quality",
                "Chart clarity",
                "Intro strength",
                "Ending / recommendation strength",
                "Evidence gaps and named risks",
            ],
            "next_step": "Run this after a completed memo exists.",
        }
        return "Memo grader is ready; no completed memo selected yet."
    if tool_name == "readiness_check":
        artifacts["readiness_reviewed_at"] = _now()
        return "Updated memo readiness gates."
    raise ValueError(f"Unhandled tool: {tool_name}")


def _risk_title_key(risk: dict | None) -> str:
    if not isinstance(risk, dict):
        return ""
    return str(risk.get("title") or risk.get("decision_question") or "").strip().lower()


def _priority_rows(artifacts: dict) -> list[dict]:
    artifact = artifacts.get("risk_priorities")
    rows = artifact.get("priorities") if isinstance(artifact, dict) else []
    return rows if isinstance(rows, list) else []


def _complete_risk_list(company: dict, risks: list[dict]) -> list[dict]:
    completed: list[dict] = []
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            continue
        completed.append(complete_risk(risk, company, index=index + 1))
    return completed


def _carry_human_risk_edits(previous: Any, new_risks: list[dict]) -> list[dict]:
    prev_rows = previous if isinstance(previous, list) else []
    by_title = {
        _risk_title_key(risk): risk
        for risk in prev_rows
        if isinstance(risk, dict) and _risk_title_key(risk)
    }
    out: list[dict] = []
    for risk in new_risks:
        prev = by_title.get(_risk_title_key(risk))
        if not isinstance(prev, dict) or not prev.get("edited_by_human"):
            out.append(risk)
            continue
        merged = dict(risk)
        for field in ("framing", "analyst_note", "edited_by_human", "status"):
            if prev.get(field) not in (None, ""):
                merged[field] = prev[field]
        if prev.get("research_prompt") and prev.get("framing") not in (None, "", "other"):
            merged["research_prompt"] = prev["research_prompt"]
        out.append(merged)
    return out


def _carry_human_priorities(
    previous_risks: Any,
    previous_priorities: Any,
    new_risks: list[dict],
) -> list[dict] | None:
    prev_rows = previous_priorities if isinstance(previous_priorities, list) else []
    if not any(isinstance(row, dict) and row.get("human_ranked") for row in prev_rows):
        return None
    old_by_id = {
        str(risk["id"]): risk
        for risk in (previous_risks if isinstance(previous_risks, list) else [])
        if isinstance(risk, dict) and risk.get("id")
    }
    new_by_title = {
        _risk_title_key(risk): risk
        for risk in new_risks
        if isinstance(risk, dict) and _risk_title_key(risk)
    }
    remapped: list[dict] = []
    for row in prev_rows:
        if not isinstance(row, dict):
            continue
        old_risk = old_by_id.get(str(row.get("risk_id") or ""))
        if old_risk is None:
            continue
        new_risk = new_by_title.get(_risk_title_key(old_risk))
        if new_risk is None:
            continue
        remapped.append({**row, "risk_id": new_risk["id"], "human_ranked": True})
    if not remapped:
        return None
    return _normalize_priorities(new_risks, remapped)


def _merge_strategic_risk_patch(
    company: dict,
    risks: list[dict],
    patch: Any,
) -> list[dict]:
    if not isinstance(patch, dict):
        return _complete_risk_list(company, risks)
    incoming = patch.get("risks")
    if isinstance(incoming, list):
        by_id = {
            str(row.get("id")): row
            for row in incoming
            if isinstance(row, dict) and row.get("id")
        }
        merged: list[dict] = []
        for index, existing in enumerate(risks):
            if not isinstance(existing, dict):
                continue
            update = by_id.get(str(existing.get("id")))
            if isinstance(update, dict):
                merged.append(
                    complete_risk(
                        {**existing, **update, "id": existing.get("id")},
                        company,
                        index=index + 1,
                    )
                )
            else:
                merged.append(complete_risk(existing, company, index=index + 1))
        return merged
    risk_patch = patch.get("risk") if isinstance(patch.get("risk"), dict) else None
    risk_id = str(
        patch.get("risk_id")
        or (risk_patch or {}).get("id")
        or ""
    )
    if not risk_id or not isinstance(risk_patch, dict):
        if risk_id:
            risk_patch = {
                key: value
                for key, value in patch.items()
                if key not in {"risk_id", "risks", "risk"}
            }
        else:
            return _complete_risk_list(company, risks)
    merged = []
    for index, existing in enumerate(risks):
        if str(existing.get("id") or "") == risk_id:
            merged.append(
                complete_risk(
                    {**existing, **risk_patch, "id": existing.get("id"), "edited_by_human": True},
                    company,
                    index=index + 1,
                )
            )
        else:
            merged.append(complete_risk(existing, company, index=index + 1))
    return merged


def _merge_completed_task_into_parent_risk(
    company: dict,
    artifacts: dict,
    task: dict,
) -> None:
    risk_id = str(task.get("risk_id") or "")
    if not risk_id:
        return
    risk_artifact = artifacts.get("strategic_risks")
    risks = risk_artifact.get("risks") if isinstance(risk_artifact, dict) else []
    if not isinstance(risks, list):
        return
    updated: list[dict] = []
    changed = False
    for index, risk in enumerate(risks):
        if isinstance(risk, dict) and str(risk.get("id") or "") == risk_id:
            updated.append(
                merge_task_evidence_into_risk(
                    complete_risk(risk, company, index=index + 1),
                    task,
                )
            )
            changed = True
        else:
            updated.append(risk)
    if not changed:
        return
    artifacts["strategic_risks"] = {
        **(risk_artifact if isinstance(risk_artifact, dict) else {}),
        "risks": updated,
        "updated_at": _now(),
    }


def _ensure_risks(company: dict, artifacts: dict) -> list[dict]:
    risk_artifact = artifacts.get("strategic_risks")
    risks = risk_artifact.get("risks") if isinstance(risk_artifact, dict) else None
    if isinstance(risks, list) and risks:
        completed = _complete_risk_list(company, risks)
        artifacts["strategic_risks"] = {
            **risk_artifact,
            "risks": completed,
        }
        return completed
    risks = _strategic_risks(company)
    artifacts["strategic_risks"] = {
        "generated_at": _now(),
        "risks": risks,
        "source_basis": _source_basis(company),
        "generated_by": "deterministic_fallback",
    }
    return risks


def _risks_by_id(artifacts: dict) -> dict[str, dict]:
    risk_artifact = artifacts.get("strategic_risks")
    risks = risk_artifact.get("risks") if isinstance(risk_artifact, dict) else []
    if not isinstance(risks, list):
        return {}
    return {
        str(risk["id"]): risk
        for risk in risks
        if isinstance(risk, dict) and risk.get("id")
    }


def _coerce_rank(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return fallback
    return rank if rank > 0 else fallback


def _coerce_selected(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_priorities(risks: list[dict], priorities: Any) -> list[dict]:
    risk_by_id = {
        str(risk["id"]): risk
        for risk in risks
        if isinstance(risk, dict) and risk.get("id")
    }
    rows = priorities if isinstance(priorities, list) else []
    provided = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        risk_id = str(row.get("risk_id") or "")
        if risk_id not in risk_by_id or risk_id in seen:
            continue
        seen.add(risk_id)
        provided.append((
            _coerce_rank(row.get("rank"), index + 1),
            index,
            row,
        ))
    provided.sort(key=lambda item: (item[0], item[1]))

    normalized: list[dict[str, Any]] = []
    human_ranked = any(
        bool(row.get("human_ranked")) for _, _, row in provided
    )
    for _, _, row in provided:
        risk = risk_by_id[str(row.get("risk_id"))]
        disposition = str(row.get("disposition") or "").strip() or suggested_disposition(risk)
        if disposition not in DISPOSITIONS:
            disposition = suggested_disposition(risk)
        framing = str(row.get("framing") or risk.get("framing") or "other").strip()
        if framing not in FRAMINGS:
            framing = "other"
        selected = _coerce_selected(row.get("selected")) and disposition != "dismissed"
        item = {
            "risk_id": str(row.get("risk_id")),
            "rank": len(normalized) + 1,
            "selected": selected,
            "disposition": disposition,
            "framing": framing,
            "human_ranked": bool(row.get("human_ranked")) or human_ranked,
        }
        if row.get("rationale") is not None:
            item["rationale"] = str(row.get("rationale") or "")
        if row.get("analyst_note") is not None:
            item["analyst_note"] = str(row.get("analyst_note") or "")
        normalized.append(item)

    for risk in risks:
        if not isinstance(risk, dict) or not risk.get("id"):
            continue
        risk_id = str(risk["id"])
        if risk_id in seen:
            continue
        normalized.append({
            "risk_id": risk_id,
            "rank": len(normalized) + 1,
            "selected": False,
            "disposition": suggested_disposition(risk),
            "framing": risk.get("framing") if risk.get("framing") in FRAMINGS else "other",
            "human_ranked": human_ranked,
        })

    return normalized


def _selected_risks_for_tasks(risks: list[dict], priorities: Any) -> list[dict]:
    artifacts = {"strategic_risks": {"risks": risks}}
    risk_by_id = _risks_by_id(artifacts)
    normalized = _normalize_priorities(risks, priorities)
    return [
        risk_by_id[row["risk_id"]]
        for row in normalized
        if row.get("selected") and row.get("risk_id") in risk_by_id
    ]


def _refresh_research_tasks(company: dict, artifacts: dict) -> None:
    risks = _ensure_risks(company, artifacts)
    priority_artifact = artifacts.get("risk_priorities")
    if not isinstance(priority_artifact, dict):
        priority_artifact = {}
    priorities = _normalize_priorities(
        risks,
        priority_artifact.get("priorities"),
    )
    artifacts["risk_priorities"] = {
        **priority_artifact,
        "priorities": priorities,
    }
    selected_risks = _selected_risks_for_tasks(risks, priorities)
    previous_by_risk_id = _existing_tasks_by_risk_id(artifacts)
    tasks = _research_tasks(company, selected_risks)
    for task in tasks:
        previous = previous_by_risk_id.get(str(task.get("risk_id") or ""))
        if not previous:
            continue
        for field in _PRESERVED_TASK_FIELDS:
            if field in previous:
                task[field] = previous[field]
    artifacts["research_tasks"] = {
        "updated_at": _now(),
        "tasks": tasks,
    }


def _existing_tasks_by_risk_id(artifacts: dict) -> dict[str, dict]:
    task_artifact = artifacts.get("research_tasks")
    tasks = task_artifact.get("tasks") if isinstance(task_artifact, dict) else []
    if not isinstance(tasks, list):
        return {}
    return {
        str(task["risk_id"]): task
        for task in tasks
        if isinstance(task, dict) and task.get("risk_id")
    }


def _find_research_task(artifacts: dict, task_id: str) -> dict | None:
    safe_task_id = str(task_id or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", safe_task_id):
        raise ValueError("Invalid research task id")
    task_artifact = artifacts.get("research_tasks")
    tasks = task_artifact.get("tasks") if isinstance(task_artifact, dict) else []
    if not isinstance(tasks, list):
        return None
    return next(
        (
            task for task in tasks
            if isinstance(task, dict) and str(task.get("id") or "") == safe_task_id
        ),
        None,
    )


def _normalize_source_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    rows = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for row in rows:
        source_id = str(row or "").strip()
        if not re.match(r"^[A-Za-z0-9_-]+$", source_id):
            continue
        if source_id in seen:
            continue
        seen.add(source_id)
        normalized.append(source_id)
    return normalized


def _manifest_entry_for_research_file(entry: dict, path: Path | None = None) -> dict:
    return {
        "file_id": entry.get("id"),
        "filename": entry.get("filename"),
        "local_filename": entry.get("stored_name") or entry.get("filename"),
        "kind": entry.get("kind"),
        "label": entry.get("label"),
        "source_type": "company_background",
        "notes": entry.get("label"),
        "path": str(path) if path is not None else None,
    }


def _selected_sources_for_task(company_id: str, task: dict) -> list[dict]:
    selected_ids = _normalize_source_id_list(task.get("selected_source_ids"))
    if not selected_ids:
        return [
            _manifest_entry_for_research_file(entry)
            for entry in research_store.list_files(company_id)
        ]
    out: list[dict] = []
    for source_id in selected_ids:
        found = research_store.get_file(company_id, source_id)
        if found is None:
            continue
        entry, path = found
        out.append(_manifest_entry_for_research_file(entry, path))
    return out


def _research_task_source_context(
    company_id: str,
    session_id: str,
    task_id: str,
    task: dict,
) -> tuple[Path, list[dict]]:
    selected_ids = _normalize_source_id_list(task.get("selected_source_ids"))
    if not selected_ids:
        return research_store.RESEARCH_ROOT / company_id, _selected_sources_for_task(
            company_id,
            task,
        )

    source_dir = session_dir(company_id, session_id) / "research_task_sources" / task_id
    shutil.rmtree(source_dir, ignore_errors=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for source_id in selected_ids:
        found = research_store.get_file(company_id, source_id)
        if found is None:
            continue
        entry, path = found
        local_name = entry.get("stored_name") or f"{source_id}__{entry.get('filename') or 'source'}"
        shutil.copy2(path, source_dir / local_name)
        copied = {
            **_manifest_entry_for_research_file(entry, source_dir / local_name),
            "local_filename": local_name,
        }
        manifest.append(copied)
    (source_dir / "selected_sources.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return source_dir, manifest


def _apply_research_task_patch(task: dict, patch: dict) -> None:
    if "status" in patch:
        status = str(patch.get("status") or "").strip()
        if status not in _TASK_STATUSES:
            raise ValueError("Invalid research task status")
        task["status"] = status
    if "result_summary" in patch:
        summary = str(patch.get("result_summary") or "").strip()
        task["result_summary"] = summary or None
        task["answer"] = summary or None
        task["result_updated_at"] = _now() if summary else None
    if "error" in patch:
        error = str(patch.get("error") or "").strip()
        task["error"] = error or None
    if "completed_at" in patch:
        task["completed_at"] = str(patch.get("completed_at") or "").strip() or None
    if "started_at" in patch:
        task["started_at"] = str(patch.get("started_at") or "").strip() or None
    if "selected_source_ids" in patch:
        task["selected_source_ids"] = _normalize_source_id_list(
            patch.get("selected_source_ids")
        )


def _touch_research_tasks(session: dict) -> None:
    research_tasks = session.setdefault("artifacts", {}).setdefault(
        "research_tasks",
        {"tasks": []},
    )
    if isinstance(research_tasks, dict):
        research_tasks["updated_at"] = _now()


def _research_result_basis(task: dict, risk: dict | None) -> list[str]:
    basis = ["strategic_risk", "research_prompt"]
    if task.get("source_type"):
        basis.append("source_type")
    if risk and risk.get("evidence_needed"):
        basis.append("evidence_needed")
    return basis


def _deterministic_research_result(
    company: dict,
    task: dict,
    risk: dict | None,
) -> str:
    name = company.get("name") or company.get("id") or "the company"
    risk_title = (
        risk.get("title")
        if isinstance(risk, dict)
        else task.get("title") or "selected risk"
    ) or task.get("title") or "selected risk"
    decision_question = (
        risk.get("decision_question")
        if isinstance(risk, dict)
        else task.get("prompt") or "the selected research question"
    ) or task.get("prompt") or "the selected research question"
    evidence_needed = []
    if isinstance(risk, dict) and isinstance(risk.get("evidence_needed"), list):
        evidence_needed = [
            str(item)
            for item in risk.get("evidence_needed") or []
            if str(item or "").strip()
        ][:3]
    source_type = str(task.get("source_type") or "targeted source review").strip()
    evidence_text = (
        "; ".join(evidence_needed)
        if evidence_needed
        else "independent support, disconfirming facts, and memo-grade source trace"
    )
    return (
        f"First-pass deterministic result for {name}: '{risk_title}' remains "
        f"open until Serena validates {evidence_text}. Recommended source path: "
        f"{source_type}. Sensitivity: {decision_question}"
    )


def _confidence(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in {"low", "medium", "high"} else "medium"


def _clean_text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip() if limit else text


def _normalize_evidence_entries(value: Any, *, fallback_confidence: str) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out: list[dict] = []
    for row in rows:
        if isinstance(row, dict):
            excerpt = _clean_text(
                row.get("excerpt")
                or row.get("claim")
                or row.get("finding")
                or row.get("text"),
                limit=700,
            )
            if not excerpt:
                continue
            out.append({
                "file_id": row.get("file_id"),
                "filename": row.get("filename"),
                "locator": row.get("locator"),
                "excerpt": excerpt,
                "confidence": _confidence(row.get("confidence") or fallback_confidence),
            })
            continue
        excerpt = _clean_text(row, limit=700)
        if excerpt:
            out.append({
                "file_id": None,
                "filename": None,
                "locator": None,
                "excerpt": excerpt,
                "confidence": fallback_confidence,
            })
    return out


def _normalize_question_list(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else []
    return [_clean_text(row, limit=500) for row in rows if _clean_text(row)]


def _source_checked_entry(value: Any) -> dict | None:
    if isinstance(value, dict):
        filename = value.get("filename") or value.get("local_filename")
        notes = value.get("notes") or value.get("label")
        return {
            "file_id": value.get("file_id") or value.get("id"),
            "filename": filename,
            "source_type": value.get("source_type") or value.get("kind"),
            "notes": notes,
        }
    text = _clean_text(value, limit=500)
    if not text:
        return None
    return {
        "file_id": None,
        "filename": text,
        "source_type": "source",
        "notes": None,
    }


def _normalize_sources_checked(value: Any, fallback_manifest: list[dict]) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out: list[dict] = []
    seen: set[tuple[str | None, str | None]] = set()
    for row in rows or fallback_manifest:
        entry = _source_checked_entry(row)
        if entry is None:
            continue
        key = (entry.get("file_id"), entry.get("filename"))
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _normalize_research_task_result(
    result: dict,
    *,
    source_manifest: list[dict],
) -> dict | None:
    answer = _clean_text(
        result.get("answer") or result.get("result_summary"),
        limit=4000,
    )
    if not answer:
        return None
    confidence = _confidence(result.get("confidence"))
    supporting = _normalize_evidence_entries(
        result.get("supporting_evidence") or result.get("key_findings"),
        fallback_confidence=confidence,
    )
    contradicting = _normalize_evidence_entries(
        result.get("contradicting_evidence"),
        fallback_confidence=confidence,
    )
    remaining_limits = _normalize_question_list(
        result.get("remaining_evidence_limits")
        or result.get("open_questions")
        or result.get("evidence_gaps")
    )
    sources_checked = _normalize_sources_checked(
        result.get("sources_checked"),
        source_manifest,
    )
    structured = {
        "answer": answer,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "remaining_evidence_limits": remaining_limits,
        # Legacy UI alias; new Claude-facing schema writes the neutral field.
        "open_questions": remaining_limits,
        "sources_checked": sources_checked,
        "confidence": confidence,
    }
    if result != structured:
        structured["raw_payload"] = result
    return structured


def _fallback_research_task_result(
    company: dict,
    task: dict,
    risk: dict | None,
    *,
    source_manifest: list[dict],
) -> dict:
    answer = _deterministic_research_result(company, task, risk)
    remaining_limits: list[str] = []
    if isinstance(risk, dict) and isinstance(risk.get("evidence_needed"), list):
        remaining_limits = [
            _clean_text(item, limit=500)
            for item in risk.get("evidence_needed") or []
            if _clean_text(item)
        ][:5]
    if not remaining_limits:
        remaining_limits = [
            "Independent support and disconfirming evidence remain material source-treatment limits."
        ]
    company_rows = company_evidence_rows(company)
    supporting = []
    if isinstance(risk, dict):
        supporting = list(risk.get("supporting_evidence") or [])
    if not supporting:
        supporting = company_rows[:3]
    return {
        "answer": answer,
        "supporting_evidence": supporting,
        "contradicting_evidence": (
            list(risk.get("contradicting_evidence") or [])
            if isinstance(risk, dict)
            else []
        ),
        "remaining_evidence_limits": remaining_limits,
        "open_questions": remaining_limits,
        "sources_checked": _normalize_sources_checked(None, source_manifest),
        "confidence": "low",
    }


def _research_task_result_fields(structured: dict) -> dict:
    observed = research_eval.with_observability_defaults(structured)
    return {
        "result_summary": observed.get("answer"),
        "answer": observed.get("answer"),
        "supporting_evidence": observed.get("supporting_evidence") or [],
        "contradicting_evidence": observed.get("contradicting_evidence") or [],
        "remaining_evidence_limits": observed.get("remaining_evidence_limits") or observed.get("open_questions") or [],
        "open_questions": observed.get("remaining_evidence_limits") or observed.get("open_questions") or [],
        "sources_checked": observed.get("sources_checked") or [],
        "confidence": _confidence(observed.get("confidence")),
        "analyst_review_score": observed.get("analyst_review_score"),
        "job_metrics": observed.get("job_metrics"),
        "result_payload": observed,
    }


def _company_text(company: dict) -> str:
    parts = [
        company.get("name"),
        company.get("description"),
        company.get("sector"),
        company.get("industry"),
        company.get("positioning"),
    ]
    parts += [p.get("name") for p in company.get("products") or [] if isinstance(p, dict)]
    parts += [
        item.get("name") if isinstance(item, dict) else item
        for item in (company.get("competitors") or [])
    ]
    for item in list(company.get("recent_news") or company.get("company_news") or [])[:6]:
        if isinstance(item, dict):
            parts.append(item.get("headline") or item.get("title"))
            parts.append(item.get("summary"))
        else:
            parts.append(item)
    funding = company.get("latest_funding") if isinstance(company.get("latest_funding"), dict) else None
    if funding:
        parts.extend(funding.values())
    return " ".join(str(p or "") for p in parts).lower()


def _source_basis(company: dict) -> dict:
    return {
        "company_record_fields": [
            k for k in (
                "description", "sector", "industry", "products",
                "competitors", "latest_funding", "total_funding_usd",
                "latest_earnings", "notable_contracts", "recent_news",
                "company_news", "disclosures", "industry_view",
            )
            if company.get(k)
        ],
        "research_file_count": len(research_store.list_files(str(company.get("id")))),
        "source_classes_available": [
            "first_party", "research_file", "news", "filing", "market_data", "third_party",
        ],
    }


def _string_list(value: Any, *, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        out = [
            str(item).strip()
            for item in value
            if str(item or "").strip()
        ]
        if out:
            return out
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(fallback or [])


def _bool_value(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_strategic_risks(value: Any, company: dict) -> list[dict]:
    rows = value if isinstance(value, list) else []
    risks: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("decision_question") or "").strip()
        decision_question = str(row.get("decision_question") or title).strip()
        if not title or not decision_question:
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        risks.append(
            complete_risk(
                {
                    **row,
                    "id": f"risk-{len(risks) + 1}",
                    "title": title,
                    "decision_question": decision_question,
                },
                company,
                index=len(risks) + 1,
            )
        )
        if len(risks) >= 8:
            break

    if len(risks) < 5:
        for fallback in _strategic_risks(company):
            title = str(fallback.get("title") or "").strip()
            if not title or title.lower() in seen_titles:
                continue
            item = copy.deepcopy(fallback)
            item["id"] = f"risk-{len(risks) + 1}"
            risks.append(complete_risk(item, company, index=len(risks)))
            seen_titles.add(title.lower())
            if len(risks) >= 5:
                break
    return _complete_risk_list(company, risks[:8])


def _coerce_thesis_spine(value: Any, company: dict, artifacts: dict) -> dict:
    risks = _ensure_risks(company, artifacts)
    fallback = _thesis_spine(company, risks, _priority_rows(artifacts))
    payload = value if isinstance(value, dict) else {}

    def sensitivity_rows(source: dict) -> list:
        rows = source.get("risk_valuation_sensitivities")
        if isinstance(rows, list):
            return rows
        # Legacy read alias for sessions created before the prompt-language audit.
        rows = source.get("top_gating_questions")
        return rows if isinstance(rows, list) else []

    def fill_minimum(
        items: list[dict[str, Any]],
        fallback_items: list[dict],
        *,
        prefix: str,
        minimum: int,
        maximum: int,
    ) -> list[dict]:
        seen = {
            str(
                item.get("claim")
                or item.get("sensitivity")
                or item.get("question")
                or ""
            ).strip().lower()
            for item in items
        }
        for fallback_item in fallback_items:
            if len(items) >= minimum:
                break
            key = str(
                fallback_item.get("claim")
                or fallback_item.get("sensitivity")
                or fallback_item.get("question")
                or ""
            ).strip().lower()
            if key and key in seen:
                continue
            item = copy.deepcopy(fallback_item)
            item["id"] = f"{prefix}-{len(items) + 1}"
            items.append(item)
            if key:
                seen.add(key)
        return items[:maximum]

    highlights: list[dict[str, Any]] = []
    highlight_rows = payload.get("investment_highlights")
    if isinstance(highlight_rows, list):
        for row in highlight_rows:
            if not isinstance(row, dict):
                continue
            claim = str(row.get("claim") or row.get("title") or "").strip()
            detail = str(row.get("detail") or row.get("description") or "").strip()
            if not claim and not detail:
                continue
            highlights.append({
                "id": f"highlight-{len(highlights) + 1}",
                "claim": claim or detail[:140],
                "detail": detail or claim,
                "state": str(row.get("state") or "source_limited").strip(),
                "source_trace": _string_list(
                    row.get("source_trace"),
                    fallback=["claude_code"],
                )[:8],
                "needs_stronger_evidence": _bool_value(
                    row.get("needs_stronger_evidence"),
                    default=True,
                ),
            })
            if len(highlights) >= 5:
                break
    highlights = fill_minimum(
        highlights,
        fallback.get("investment_highlights") or [],
        prefix="highlight",
        minimum=3,
        maximum=5,
    )

    memo_risks: list[dict[str, Any]] = []
    risk_rows = payload.get("investment_risks")
    if isinstance(risk_rows, list):
        for row in risk_rows:
            if not isinstance(row, dict):
                continue
            claim = str(row.get("claim") or row.get("title") or "").strip()
            detail = str(row.get("detail") or row.get("description") or "").strip()
            if not claim and not detail:
                continue
            memo_risks.append({
                "id": f"memo-risk-{len(memo_risks) + 1}",
                "claim": claim or detail[:140],
                "detail": detail or claim,
                "source_trace": _string_list(
                    row.get("source_trace"),
                    fallback=["claude_code"],
                )[:8],
                "needs_stronger_evidence": _bool_value(
                    row.get("needs_stronger_evidence"),
                    default=True,
                ),
            })
            if len(memo_risks) >= 5:
                break
    memo_risks = fill_minimum(
        memo_risks,
        fallback.get("investment_risks") or [],
        prefix="memo-risk",
        minimum=3,
        maximum=5,
    )

    sensitivities: list[dict[str, Any]] = []
    for row in sensitivity_rows(payload):
            if not isinstance(row, dict):
                continue
            sensitivity = str(
                row.get("sensitivity")
                or row.get("expected_bar")
                or row.get("support_threshold")
                or row.get("question")
                or row.get("decision_question")
                or ""
            ).strip()
            support_evidence = str(
                row.get("support_evidence")
                or row.get("support_threshold")
                or row.get("why_it_matters")
                or row.get("rationale")
                or ""
            ).strip()
            downside_impact = str(
                row.get("downside_impact")
                or row.get("stop_or_revisit_if_missing")
                or row.get("stop_or_revisit")
                or ""
            ).strip()
            recommendation_sensitivity = str(
                row.get("recommendation_sensitivity")
                or row.get("recommendation_impact")
                or ""
            ).strip()
            if not sensitivity:
                continue
            evidence_context = _string_list(
                row.get("evidence_context")
                or row.get("confirmation_evidence")
                or row.get("evidence_needed"),
                fallback=["specific source support", "disconfirming evidence review"],
            )[:8]
            sensitivities.append({
                "id": f"sensitivity-{len(sensitivities) + 1}",
                "sensitivity": _question_to_sensitivity_statement(sensitivity),
                "support_evidence": support_evidence or sensitivity,
                "evidence_context": evidence_context,
                "downside_impact": downside_impact or (
                    "Downside value increases if this sensitivity weakens valuation support."
                ),
                "recommendation_sensitivity": recommendation_sensitivity or (
                    "Recommendation strength depends on source-backed support for this sensitivity."
                ),
            })
            if len(sensitivities) >= 5:
                break
    sensitivities = fill_minimum(
        sensitivities,
        sensitivity_rows(fallback),
        prefix="sensitivity",
        minimum=3,
        maximum=5,
    )

    recommendation = str(payload.get("recommendation_logic") or "").strip()
    if not recommendation:
        recommendation = fallback["recommendation_logic"]

    return {
        "updated_at": _now(),
        "approved": False,
        "investment_highlights": highlights,
        "investment_risks": memo_risks,
        "recommendation_logic": recommendation,
        "risk_valuation_sensitivities": sensitivities[:3],
        "bull_case_must_be_true": _string_list(
            payload.get("bull_case_must_be_true"),
            fallback=fallback.get("bull_case_must_be_true") or [],
        )[:6],
        "downside_sensitivities": _string_list(
            payload.get("downside_sensitivities") or payload.get("pass_triggers"),
            fallback=(
                fallback.get("downside_sensitivities")
                or fallback.get("pass_triggers")
                or []
            ),
        )[:6],
    }


def _strategic_risks(company: dict) -> list[dict]:
    name = company.get("name") or company.get("id") or "the company"
    text = _company_text(company)
    risks: list[dict[str, Any]] = []

    def add(
        title: str,
        decision_question: str,
        why: str,
        evidence: list[str],
        sources: list[str],
        section: str = "Investment Risk",
        *,
        severity: str = "medium",
        likelihood: str = "medium",
        bull: str | None = None,
        bear: str | None = None,
        description: str | None = None,
    ) -> None:
        risks.append({
            "id": f"risk-{len(risks) + 1}",
            "title": title,
            "description": description or why,
            "decision_question": decision_question,
            "why_it_matters": why,
            "bull_case_answer": bull or (
                f"The bull case is that {name} already has source-backed proof "
                "this is contained and does not change the entry decision."
            ),
            "bear_case_answer": bear or (
                "The bear case is that this is still an unproven future state, "
                "and a weak answer should cut conviction or valuation support."
            ),
            "evidence_needed": evidence,
            "best_sources": sources,
            "research_prompt": (
                f"Research whether {decision_question.lower()} For each "
                "claim, separate company-originated evidence from independent "
                "support and identify the strongest disconfirming facts."
            ),
            "memo_section": section,
            "status": "unresearched",
            "severity": severity,
            "likelihood": likelihood,
            "generated_by": "deterministic_fallback",
        })

    if any(k in text for k in ("humanoid", "robot", "embodiment", "embodied")):
        add(
            "Is the humanoid embodiment actually the right market abstraction?",
            "Is humanoid embodiment the right abstraction for the highest-value customer problem?",
            "A wrong abstraction can create demo appeal while degrading deployment economics and use-case focus.",
            [
                "customer workflow evidence by task type",
                "deployment cost per useful labor hour",
                "evidence of repeat usage outside pilots",
            ],
            ["customer case studies", "procurement data", "deployment logs", "competitor docs"],
            severity="high",
            likelihood="medium",
        )
        add(
            "Can they achieve economically viable deployment at scale?",
            "Can the company deploy at gross margins, uptime, and support intensity that work at scale?",
            "The investment fails if revenue growth requires custom deployment labor or hardware economics that do not compound.",
            [
                "gross margin or bill-of-material proxy",
                "field support burden",
                "uptime / failure rate evidence",
                "repeatable deployment playbook",
            ],
            ["customer contracts", "job postings", "support docs", "unit economics notes"],
            severity="high",
            likelihood="high",
        )
        add(
            "Can they build a durable intelligence advantage?",
            "Can the company collect proprietary task data that compounds faster than general robotics or foundation-model progress?",
            "If intelligence advantage is not durable, hardware and integration burden may outlive the moat.",
            [
                "exclusive data rights",
                "closed-loop learning evidence",
                "model performance deltas",
                "customer-specific adaptation evidence",
            ],
            ["technical docs", "research papers", "customer deployment evidence", "competitor benchmarks"],
            severity="high",
            likelihood="medium",
        )

    if any(k in text for k in ("ai", "llm", "agent", "model", "automation")):
        add(
            "Can they sustain an intelligence or workflow advantage as models commoditize?",
            "Does the company own a durable workflow/data advantage, or is it a thin layer on improving foundation models?",
            "AI application value can compress quickly when incumbents bundle similar features or model vendors move up-stack.",
            [
                "owned or exclusive data",
                "workflow lock-in evidence",
                "retention by feature cohort",
                "incumbent bundling comparison",
            ],
            ["product docs", "customer references", "competitor release notes", "usage proxies"],
        )

    add(
        "Is deployment depth real or only logo-level traction?",
        "Are customers broadly deployed, expanding, and renewing, or are they shallow logos and pilots?",
        "Late-stage memo quality depends on proving depth of adoption, not merely customer count.",
        [
            "ARR/customer",
            "seat or usage distribution",
            "renewal / expansion evidence",
            "named production deployments",
        ],
        ["PitchBook / CB Insights", "customer evidence", "G2 motifs", "sales notes"],
    )
    add(
        "Does revenue quality support the valuation?",
        "Is growth organic, recurring, and efficient enough to justify the current or proposed entry multiple?",
        "Headline revenue can hide pricing pull-forward, acquisition boost, services burden, or weak retention.",
        [
            "growth bridge",
            "NRR / GRR or proxies",
            "ARR per employee",
            "gross margin / burn / runway",
            "contemporaneous multiple",
        ],
        ["financial model", "PitchBook / CB Insights", "public comps", "management notes"],
        "Financial Forecast & Valuation",
    )
    add(
        "Can the company defend pricing and budget ownership?",
        "Does the product own a resilient budget line, or will it face consolidation and finance pushback?",
        "Budget-owner ambiguity and weak procurement evidence often break late-stage software investment cases.",
        [
            "budget owner",
            "contract size by segment",
            "pricing pushback evidence",
            "mission-critical workflow proof",
        ],
        ["procurement notes", "pricing pages", "customer calls", "review-site complaints"],
    )
    add(
        "Will public-company comps support the private mark?",
        "Do mature public comps justify the valuation after adjusting for growth, margins, durability, and liquidity?",
        "The memo needs a benchmark that behaves like the business, not a flattering category label.",
        [
            "closest mature public comps",
            "growth and margin spread",
            "EV/revenue and EV/EBITDA",
            "sell-side thesis themes",
        ],
        ["10-K / 10-Q filings", "earnings transcripts", "sell-side summaries", "market data"],
        "Financial Forecast & Valuation",
    )
    add(
        "What evidence would make BSH pass?",
        "What are the strongest disconfirming facts, and are they severe enough to change the recommendation?",
        "A good memo must lead with the risk that can actually kill the deal.",
        [
            "downside scenario",
            "countercase",
            "top three risk or valuation sensitivities",
            "missingness penalties",
        ],
        ["all analysis artifacts", "partner notes", "independent negative searches"],
    )

    evidence_rows = company_evidence_rows(company)
    completed: list[dict] = []
    for index, risk in enumerate(risks[:8], start=1):
        if evidence_rows and not risk.get("supporting_evidence"):
            title_l = str(risk.get("title") or "").lower()
            matched = []
            for row in evidence_rows:
                hay = f"{row.get('locator') or ''} {row.get('excerpt') or ''}".lower()
                if any(token in title_l for token in ("revenue", "valuation", "funding", "mark")):
                    if row.get("source_class") in {"market_data", "filing"}:
                        matched.append(row)
                elif any(token in title_l for token in ("deploy", "customer", "logo", "contract")):
                    if row.get("source_class") in {"news", "third_party"}:
                        matched.append(row)
                elif hay:
                    matched.append(row)
            risk["supporting_evidence"] = matched[:3] or evidence_rows[:2]
            risk["missing_evidence"] = list(risk.get("evidence_needed") or [])[:3]
        completed.append(complete_risk(risk, company, index=index))
    return completed


def _research_task_search_plan(risk: dict) -> dict:
    evidence_needed = [
        str(item)
        for item in risk.get("evidence_needed") or []
        if str(item or "").strip()
    ][:5]
    best_sources = [
        str(item)
        for item in risk.get("best_sources") or []
        if str(item or "").strip()
    ][:5]
    return {
        "question": risk.get("decision_question") or risk.get("research_prompt"),
        "evidence_needed": evidence_needed,
        "preferred_sources": best_sources,
        "steps": [
            "Check selected company background documents first.",
            "Extract supporting and contradicting evidence with source locators.",
            "Use public web/filing sources only where local evidence is insufficient.",
            "Return unresolved risk or valuation sensitivities when evidence remains missing or weak.",
        ],
    }


def _research_tasks(company: dict, risks: list[dict]) -> list[dict]:
    tasks = []
    for i, risk in enumerate(risks, start=1):
        tasks.append({
            "id": f"task-{i}",
            "risk_id": risk["id"],
            "title": f"Research: {risk['title']}",
            "priority": "high" if i <= 3 else "medium",
            "status": "not_started",
            "source_type": ", ".join(risk.get("best_sources") or [])[:160],
            "prompt": risk.get("research_prompt"),
            "search_plan": _research_task_search_plan(risk),
            "result_summary": None,
            "selected_source_ids": [],
        })
    return tasks


def _thesis_spine(company: dict, risks: list[dict], priorities: Any = None) -> dict:
    name = company.get("name") or "the company"
    sector = company.get("sector") or company.get("industry") or "its category"
    desc = company.get("description") or f"{name} operates in {sector}."
    top = ordered_active_risks(risks, priorities)[:3]
    if not top:
        top = [risk for risk in risks if isinstance(risk, dict)][:3]
    lead_risk = top[0] if top else None
    highlights = [
        {
            "id": "highlight-1",
            "claim": f"{name} gives BSH a focused way to invest in {sector}",
            "detail": (
                f"{desc} Valuation support depends on visible operating "
                "proof, source quality, and fit with a late-stage BSH entry."
            ),
            "state": "present_state",
            "source_trace": ["company_record"],
            "needs_stronger_evidence": True,
        },
        {
            "id": "highlight-2",
            "claim": "The bull case depends on proving the lead risk is manageable",
            "detail": (
                lead_risk["decision_question"]
                if lead_risk
                else "Strategic risk still needs mapping."
            ),
            "state": "upside_state",
            "source_trace": ["strategic_risks", "risk_priorities"],
            "needs_stronger_evidence": True,
        },
        {
            "id": "highlight-3",
            "claim": "Final view depends on deployment depth, revenue quality, and valuation support",
            "detail": (
                "These are the proof points most likely to determine whether "
                "BSH commits capital or treats the opportunity as "
                "valuation-sensitive."
            ),
            "state": "upside_state",
            "source_trace": ["strategic_risks", "risk_priorities", "chart_specs"],
            "needs_stronger_evidence": True,
        },
    ]
    risks_out = [
        {
            "id": f"memo-risk-{i}",
            "claim": r.get("title"),
            "detail": (
                f"{r.get('why_it_matters') or r.get('description') or r.get('title')} "
                f"Bull: {r.get('bull_case_answer') or 'Source-backed proof would contain this.'} "
                f"Bear: {r.get('bear_case_answer') or 'A weak answer should cut conviction.'}"
            ),
            "source_trace": ["strategic_risks", "risk_priorities"],
            "needs_stronger_evidence": True,
        }
        for i, r in enumerate(top, start=1)
    ]
    sensitivities = [
        {
            "id": f"sensitivity-{i}",
            "sensitivity": _question_to_sensitivity_statement(
                r.get("decision_question") or r.get("title")
            ),
            "support_evidence": r.get("why_it_matters") or r.get("description") or r.get("title"),
            "evidence_context": r.get("evidence_needed") or [],
            "downside_impact": (
                "Downside value increases if this sensitivity weakens valuation support."
            ),
            "recommendation_sensitivity": (
                "Recommendation strength depends on source-backed support "
                "for this sensitivity."
            ),
        }
        for i, r in enumerate(top, start=1)
    ]
    return {
        "updated_at": _now(),
        "approved": False,
        "investment_highlights": highlights[:5],
        "investment_risks": risks_out[:5],
        "recommendation_logic": (
            "State the recommendation directly. Support participation when the "
            "lead sensitivities have independent evidence and benchmark work "
            "supports valuation; avoid participation where selected sensitivities "
            "do not support valuation."
        ),
        "risk_valuation_sensitivities": sensitivities[:3],
        "bull_case_must_be_true": [
            "Deployment depth is repeatable beyond early adopters.",
            "Revenue quality supports the proposed valuation.",
            "Competitive compression is manageable."
        ],
        "downside_sensitivities": [
            "Deployment depth is not independently supported. Revenue and the entry multiple are at risk.",
            "Comparable-company evidence is stale or economically mismatched. The disclosed valuation may not hold.",
            "Growth is mainly pricing, services, or acquisition-driven without durable expansion. Revenue quality and the exit multiple are at risk.",
        ],
    }


def _chart_specs(company: dict) -> dict:
    has_funding = bool(company.get("latest_funding") or company.get("total_funding_usd"))
    has_comps = bool(company.get("competitors"))
    specs = [
        {
            "id": "chart-growth-bridge",
            "title": "Growth Bridge",
            "takeaway": "Separate organic growth from pricing, acquisitions, cross-sell, and unknown remainder.",
            "required_data": ["starting revenue/ARR", "latest revenue/ARR", "acquisition contribution", "price uplift"],
            "data_availability": "partial" if has_funding else "missing",
            "include_in_final_memo": True,
        },
        {
            "id": "chart-public-comps",
            "title": "Mature Public Comps Benchmark",
            "takeaway": "Compare the private mark against companies with similar economics, not just similar labels.",
            "required_data": ["public comps", "EV/revenue", "growth", "gross margin", "FCF margin"],
            "data_availability": "partial" if has_comps else "missing",
            "include_in_final_memo": True,
        },
        {
            "id": "chart-valuation-timing",
            "title": "Valuation Timing Table",
            "takeaway": "Distinguish contemporaneous entry multiple from stale-mark shorthand.",
            "required_data": ["last priced valuation date", "ARR/revenue at valuation date", "latest ARR/revenue"],
            "data_availability": "partial" if has_funding else "missing",
            "include_in_final_memo": True,
        },
        {
            "id": "chart-risk-register",
            "title": "Strategic Risk Register",
            "takeaway": "Rank the risks most likely to change the BSH recommendation.",
            "required_data": ["risk severity", "likelihood", "disconfirming evidence", "monitoring approach"],
            "data_availability": "available",
            "include_in_final_memo": True,
        },
        {
            "id": "chart-adoption-ladder",
            "title": "Deployment / Adoption Ladder",
            "takeaway": "Separate announced features from repeatable production adoption.",
            "required_data": ["capabilities", "customer production evidence", "renewal/upsell evidence"],
            "data_availability": "missing",
            "include_in_final_memo": True,
        },
    ]
    return {"updated_at": _now(), "specs": specs}


def _thesis_sensitivity_rows(thesis: Any) -> list[dict]:
    if not isinstance(thesis, dict):
        return []
    rows = thesis.get("risk_valuation_sensitivities")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    # Legacy read alias for sessions created before the prompt-language audit.
    rows = thesis.get("top_gating_questions")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _sensitivity_statement(item: dict) -> str:
    raw = (
        item.get("sensitivity")
        or item.get("expected_bar")
        or item.get("question")
        or item.get("support_evidence")
        or item.get("why_it_matters")
    )
    return _question_to_sensitivity_statement(raw)


def _sensitivity_support(item: dict) -> str:
    return _clean_text(
        item.get("support_evidence")
        or item.get("why_it_matters")
        or item.get("support_threshold"),
        limit=320,
    )


def _sensitivity_downside(item: dict) -> str:
    return _clean_text(
        item.get("downside_impact")
        or item.get("recommendation_sensitivity")
        or item.get("stop_or_revisit_if_missing"),
        limit=320,
    )


def _narrative_hooks(company: dict, artifacts: dict) -> dict:
    name = company.get("name") or "the company"
    sector = company.get("sector") or company.get("industry") or "its category"
    desc = _clean_text(company.get("description"), limit=260)
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts, dict) else None
    sensitivities = _thesis_sensitivity_rows(thesis)
    highlights = thesis.get("investment_highlights") if isinstance(thesis, dict) else []
    memo_risks = thesis.get("investment_risks") if isinstance(thesis, dict) else []
    recommendation_logic = (
        _clean_text(thesis.get("recommendation_logic"), limit=420)
        if isinstance(thesis, dict)
        else ""
    )
    main_sensitivity = (
        _sensitivity_statement(sensitivities[0])
        if sensitivities
        else "current traction supports the entry valuation"
    )
    lead_highlight = (
        _clean_text(highlights[0].get("claim"), limit=180)
        if highlights and isinstance(highlights[0], dict)
        else f"{name}'s operating proof can support a BSH entry"
    )
    lead_risk = (
        _clean_text(memo_risks[0].get("claim"), limit=180)
        if memo_risks and isinstance(memo_risks[0], dict)
        else "deployment depth and revenue quality remain unproven"
    )
    downside_sensitivity = ""
    if isinstance(thesis, dict):
        downside_sensitivity = _clean_text(
            (
                thesis.get("downside_sensitivities")
                or thesis.get("pass_triggers")
                or [None]
            )[0],
            limit=220,
        )
    intro_fact = desc or f"{name} operates in {sector}."
    sensitivity_text = (
        str(main_sensitivity or "")
        .removeprefix("Expected bar:")
        .removeprefix("Sensitivity:")
        .strip()
    )
    sensitivity_lc = (
        sensitivity_text[:1].lower() + sensitivity_text[1:]
        if sensitivity_text
        else sensitivity_text
    )
    openings = [
        {
            "id": "intro-operating-proof",
            "text": (
                f"Recommendation: BSH commits capital to {name} where {sensitivity_lc.rstrip('.')}."
            ),
            "purpose": "intro stance",
            "tone": "proof_first",
            "supported_claims": [lead_highlight, main_sensitivity],
            "evidence_references": ["thesis_spine", "risk_valuation_sensitivities"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Use only if the memo can show the proof burden immediately.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "intro-company-reality",
            "text": (
                f"{intro_fact} The question is whether that "
                "operating reality is already visible in deployments, revenue "
                "quality, and the disclosed terms."
            ),
            "purpose": "intro stance",
            "tone": "operator_grounded",
            "supported_claims": [intro_fact, lead_highlight],
            "evidence_references": ["company_record", "thesis_spine"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Keep the company description factual if independent evidence is thin.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "intro-bsh-decision",
            "text": (
                f"We will judge {name} less on category excitement than on "
                "proof of depth, economics, and durability."
            ),
            "purpose": "intro stance",
            "tone": "ic_ready",
            "supported_claims": [lead_highlight, lead_risk],
            "evidence_references": ["thesis_spine", "strategic_risks"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Avoid if the operator wants a more constructive first paragraph.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
    ]
    transitions = [
        {
            "id": "risk-lead-risk",
            "text": f"Lead risk: {lead_risk.rstrip('.')}.",
            "purpose": "risk framing",
            "tone": "lead_risk",
            "supported_claims": [lead_risk],
            "evidence_references": ["investment_risks", "risk_priorities"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Make sure this is the selected lead risk, not merely the first generated risk.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "risk-proof-burden",
            "text": (
                f"{lead_risk.rstrip('.')}. That failure would move the "
                "recommendation."
            ),
            "purpose": "risk framing",
            "tone": "recommendation_moving",
            "supported_claims": [lead_risk, main_sensitivity],
            "evidence_references": ["strategic_risks", "risk_valuation_sensitivities"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Use only if the selected evidence gap is specific in the risk table.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "risk-downside-sensitivity",
            "text": (
                "Downside begins with "
                f"{downside_sensitivity[:1].lower() + downside_sensitivity[1:] if downside_sensitivity else 'the lead evidence remaining missing'}."
            ),
            "purpose": "risk framing",
            "tone": "downside_sensitivity",
            "supported_claims": [downside_sensitivity or lead_risk],
            "evidence_references": ["downside_sensitivities", "investment_risks"],
            "source_traces": [],
            "confidence": "medium" if downside_sensitivity else "low",
            "overclaiming_risk": "Use only if the downside sensitivity is supported by current evidence.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
    ]
    endings = [
        {
            "id": "conclusion-recommend-participating",
            "text": (
                "Recommendation: BSH commits when independent evidence supports "
                "the lead sensitivities and the disclosed terms."
            ),
            "purpose": "conclusion posture",
            "tone": "recommend_participating",
            "supported_claims": [main_sensitivity, recommendation_logic],
            "evidence_references": ["risk_valuation_sensitivities", "recommendation_logic"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Do not use if the evidence base does not support participation.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "conclusion-risk-sensitive",
            "text": (
                f"The recommendation weakens if {sensitivity_lc.rstrip('.')} fails."
            ),
            "purpose": "conclusion posture",
            "tone": "risk_sensitive",
            "supported_claims": [main_sensitivity, lead_risk],
            "evidence_references": ["risk_valuation_sensitivities", "investment_risks"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Use if unresolved evidence is material enough to weaken the recommendation.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
        {
            "id": "conclusion-evidence-discipline",
            "text": (
                "We keep recommendation strength tied to named proof "
                "rather than stretching the case around weak evidence."
            ),
            "purpose": "conclusion posture",
            "tone": "evidence_discipline",
            "supported_claims": [downside_sensitivity or lead_risk],
            "evidence_references": ["downside_sensitivities", "investment_risks"],
            "source_traces": [],
            "confidence": "medium",
            "overclaiming_risk": "Use only when the evidence base materially weakens the recommendation.",
            "paired_infographic_ids": [],
            "reviewer_prompts": [],
            "status": "draft",
        },
    ]
    return {
        "updated_at": _now(),
        "openings": openings,
        "transitions": transitions,
        "endings": endings,
        "selected_opening_id": openings[0]["id"],
        "selected_transition_id": transitions[0]["id"],
        "selected_ending_id": endings[0]["id"],
        "reviewer_prompts": [
            {
                "id": "operator-final-posture",
                "prompt": (
                    "Choose the final recommendation verdict once the selected "
                    "intro and risk framing are reviewed."
                ),
                "required": False,
                "options": [
                    "Recommendation: BSH commits",
                    "Recommendation: pass",
                    "Risk-sensitive recommendation",
                ],
                "resolved_choice": None,
                "rationale": "Operator HIL guidance can make the conclusion sharper than a default balanced ending.",
                "status": "optional",
            }
        ],
    }


_IMAGE_GENERATION_MODES = {
    "no_text_overlay",
    "text_in_image",
    "needs_human_choice",
    "operator_choice_required",
}
_SOURCE_AVAILABILITY_VALUES = {"available", "partial", "missing"}


def _slug_part(value: Any, *, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return text[:64] or fallback


def _stable_item_id(prefix: str, value: Any, index: int) -> str:
    return f"{prefix}-{_slug_part(value, fallback=str(index))}"


def _source_trace_from_evidence(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    excerpt = _clean_text(value.get("excerpt"), limit=700)
    if not excerpt:
        return None
    return {
        "title": _clean_text(
            value.get("title") or value.get("filename") or value.get("file_id"),
            limit=160,
        ) or None,
        "url": _clean_text(value.get("url"), limit=500) or None,
        "locator": _clean_text(
            value.get("locator") or value.get("filename"),
            limit=160,
        ) or None,
        "excerpt": excerpt,
        "confidence": _confidence(value.get("confidence")),
    }


def _source_traces_from_research_tasks(tasks: list[dict], *, limit: int = 8) -> list[dict]:
    traces: list[dict] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for row in list(task.get("supporting_evidence") or []) + list(
            task.get("contradicting_evidence") or []
        ):
            trace = _source_trace_from_evidence(row)
            if trace:
                traces.append(trace)
            if len(traces) >= limit:
                return traces
    return traces


def _coerce_source_availability(value: Any) -> str:
    lowered = str(value or "").strip().lower().replace(" ", "_")
    if lowered in _SOURCE_AVAILABILITY_VALUES:
        return lowered
    if lowered in {"source_needed", "unknown", "unavailable"}:
        return "missing"
    return "partial"


def _coerce_image_generation_mode(value: Any) -> str:
    lowered = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "overlay": "no_text_overlay",
        "no_text": "no_text_overlay",
        "no_text_with_overlay": "no_text_overlay",
        "application_overlay": "no_text_overlay",
        "text": "text_in_image",
        "text_in_image_generation": "text_in_image",
        "human_choice": "needs_human_choice",
        "needs_choice": "needs_human_choice",
        "reviewer_choice": "needs_human_choice",
        "operator_choice_required": "needs_human_choice",
        "operator_review": "needs_human_choice",
    }
    lowered = aliases.get(lowered, lowered)
    return lowered if lowered in _IMAGE_GENERATION_MODES else "no_text_overlay"


def _coerce_reviewer_prompts(value: Any, *, prefix: str) -> list[dict]:
    rows = value if isinstance(value, list) else []
    prompts: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            prompt = _clean_text(
                row.get("prompt") or row.get("question") or row.get("label"),
                limit=500,
            )
            if not prompt:
                continue
            options = _string_list(row.get("options"))[:8]
            resolved_choice = _clean_text(
                row.get("resolved_choice") or row.get("choice"),
                limit=300,
            )
            required = _bool_value(row.get("required"), default=True)
            status = _clean_text(row.get("status"), limit=40).lower()
            if not status:
                status = "resolved" if resolved_choice else (
                    "needs_review" if required else "optional"
                )
            prompts.append({
                "id": _clean_text(row.get("id"), limit=80)
                or _stable_item_id(prefix, prompt, index),
                "prompt": prompt,
                "required": required,
                "options": options,
                "resolved_choice": resolved_choice or None,
                "rationale": _clean_text(row.get("rationale"), limit=700),
                "status": status,
            })
            continue
        prompt = _clean_text(row, limit=500)
        if prompt:
            prompts.append({
                "id": _stable_item_id(prefix, prompt, index),
                "prompt": prompt,
                "required": True,
                "options": [],
                "resolved_choice": None,
                "rationale": "",
                "status": "needs_review",
            })
    return prompts[:12]


def _has_unresolved_required_prompt(prompts: list[dict]) -> bool:
    return any(
        prompt.get("required") and not prompt.get("resolved_choice")
        for prompt in prompts
    )


def _coerce_infographic_claims(value: Any, fallback: list[dict]) -> list[dict]:
    rows = value if isinstance(value, list) else []
    claims: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            claim = _clean_text(
                row.get("claim") or row.get("text") or row.get("finding"),
                limit=600,
            )
            if not claim:
                continue
            status = _clean_text(
                row.get("evidence_status") or row.get("status"),
                limit=40,
            ).lower() or "needs_review"
            claims.append({
                "id": _clean_text(row.get("id"), limit=80)
                or _stable_item_id("claim", claim, index),
                "claim": claim,
                "evidence_status": status,
                "source_traces": _normalize_source_traces(row.get("source_traces")),
                "contradictions": _string_list(row.get("contradictions"))[:5],
                "warnings": _string_list(row.get("warnings"))[:5],
                "prohibited_for_visuals": _bool_value(
                    row.get("prohibited_for_visuals"),
                    default=status in {"missing", "contradicted", "source_needed"},
                ),
                "confidence": _confidence(row.get("confidence")),
            })
            continue
        claim = _clean_text(row, limit=600)
        if claim:
            claims.append({
                "id": _stable_item_id("claim", claim, index),
                "claim": claim,
                "evidence_status": "needs_review",
                "source_traces": [],
                "contradictions": [],
                "warnings": [],
                "prohibited_for_visuals": False,
                "confidence": "low",
            })
        if len(claims) >= 16:
            break
    return claims[:16] or fallback[:16]


def _coerce_numeric_metrics(value: Any, fallback: list[dict]) -> list[dict]:
    rows = value if isinstance(value, list) else []
    metrics: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        label = _clean_text(row.get("label") or row.get("metric"), limit=160)
        if not label:
            continue
        metrics.append({
            "id": _clean_text(row.get("id"), limit=80)
            or _stable_item_id("metric", label, index),
            "label": label,
            "value": row.get("value"),
            "unit": _clean_text(row.get("unit"), limit=80) or None,
            "period": _clean_text(row.get("period"), limit=100) or None,
            "calculation": _clean_text(row.get("calculation"), limit=500),
            "denominator_note": _clean_text(
                row.get("denominator_note"),
                limit=500,
            ),
            "source_traces": _normalize_source_traces(row.get("source_traces")),
            "confidence": _confidence(row.get("confidence")),
        })
        if len(metrics) >= 20:
            break
    return metrics[:20] or fallback[:20]


def _coerce_opportunity_rows(
    value: Any,
    *,
    fallback: list[dict],
    prefix: str,
) -> list[dict]:
    rows = value if isinstance(value, list) else []
    opportunities: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            title = _clean_text(
                row.get("title") or row.get("name") or row.get("hook_angle"),
                limit=160,
            )
            if not title:
                continue
            opportunities.append({
                "id": _clean_text(row.get("id"), limit=80)
                or _stable_item_id(prefix, title, index),
                "title": title,
                "rationale": _clean_text(
                    row.get("rationale") or row.get("why_it_matters"),
                    limit=700,
                ),
                "paired_claim_ids": _string_list(row.get("paired_claim_ids"))[:8],
                "source_trace_ids": _string_list(row.get("source_trace_ids"))[:8],
                "confidence": _confidence(row.get("confidence")),
            })
            continue
        title = _clean_text(row, limit=160)
        if title:
            opportunities.append({
                "id": _stable_item_id(prefix, title, index),
                "title": title,
                "rationale": "",
                "paired_claim_ids": [],
                "source_trace_ids": [],
                "confidence": "low",
            })
    return opportunities[:12] or fallback[:12]


def _fallback_infographic_claims(artifacts: dict) -> list[dict]:
    thesis = (
        artifacts.get("thesis_spine")
        if isinstance(artifacts, dict)
        and isinstance(artifacts.get("thesis_spine"), dict)
        else {}
    )
    tasks = artifacts.get("research_tasks", {}).get("tasks", [])
    tasks = tasks if isinstance(tasks, list) else []
    traces = _source_traces_from_research_tasks(tasks)
    claims: list[dict] = []
    for index, row in enumerate(thesis.get("investment_highlights") or [], start=1):
        if not isinstance(row, dict):
            continue
        claim = _clean_text(row.get("claim"), limit=600)
        if not claim:
            continue
        claims.append({
            "id": row.get("id") or _stable_item_id("claim", claim, index),
            "claim": claim,
            "evidence_status": (
                "partial" if row.get("source_trace") or traces else "needs_review"
            ),
            "source_traces": traces[:3],
            "contradictions": [],
            "warnings": (
                ["Needs stronger evidence before visual use."]
                if row.get("needs_stronger_evidence")
                else []
            ),
            "prohibited_for_visuals": bool(row.get("needs_stronger_evidence")),
            "confidence": "medium" if traces else "low",
        })
    for index, row in enumerate(thesis.get("investment_risks") or [], start=1):
        if not isinstance(row, dict):
            continue
        claim = _clean_text(row.get("claim"), limit=600)
        if claim:
            claims.append({
                "id": row.get("id") or _stable_item_id("risk-claim", claim, index),
                "claim": claim,
                "evidence_status": "needs_review",
                "source_traces": traces[:2],
                "contradictions": [],
                "warnings": ["Risk framing must not be illustrated as proven fact."],
                "prohibited_for_visuals": False,
                "confidence": "low",
            })
    return claims


def _fallback_numeric_metrics(company: dict, artifacts: dict) -> list[dict]:
    metrics: list[dict] = []
    latest_funding = company.get("latest_funding")
    if isinstance(latest_funding, dict) and latest_funding.get("post_money_usd"):
        metrics.append({
            "id": "metric-latest-post-money",
            "label": "Latest post-money valuation",
            "value": latest_funding.get("post_money_usd"),
            "unit": "USD",
            "period": _clean_text(latest_funding.get("date"), limit=100) or None,
            "calculation": "",
            "denominator_note": "",
            "source_traces": [],
            "confidence": "low",
        })
    benchmark = artifacts.get("benchmark_dashboard")
    comps = benchmark.get("public_comps") if isinstance(benchmark, dict) else []
    for comp in comps if isinstance(comps, list) else []:
        if not isinstance(comp, dict):
            continue
        company_name = comp.get("company") or "Comp"
        for key, label, unit in (
            ("revenue_growth_pct", "Revenue growth", "%"),
            ("gross_margin_pct", "Gross margin", "%"),
            ("ev_revenue", "EV/revenue", "x"),
            ("fcf_margin_pct", "FCF margin", "%"),
        ):
            value = comp.get(key)
            if value is None:
                continue
            metrics.append({
                "id": _stable_item_id("metric", f"{company_name}-{key}", len(metrics) + 1),
                "label": f"{company_name} {label}",
                "value": value,
                "unit": unit,
                "period": comp.get("metric_period"),
                "calculation": "",
                "denominator_note": "",
                "source_traces": comp.get("source_traces") or [],
                "confidence": _confidence(comp.get("confidence")),
            })
            if len(metrics) >= 12:
                return metrics
    return metrics


def _infographic_source_brief(company: dict, artifacts: dict) -> dict:
    tasks = artifacts.get("research_tasks", {}).get("tasks", [])
    tasks = tasks if isinstance(tasks, list) else []
    evidence_summary = _memo_packet_evidence_summary(tasks)
    charts = _chart_specs(company).get("specs") or []
    hooks = _narrative_hooks(company, artifacts)
    visual_opportunities = [
        {
            "id": row.get("id"),
            "title": row.get("title"),
            "rationale": row.get("takeaway") or "",
            "paired_claim_ids": [],
            "source_trace_ids": [],
            "confidence": "low",
        }
        for row in charts[:8]
    ]
    narrative_opportunities = [
        {
            "id": row.get("id"),
            "title": row.get("tone") or row.get("id"),
            "rationale": row.get("text") or "",
            "paired_claim_ids": [],
            "source_trace_ids": [],
            "confidence": "low",
        }
        for row in (hooks.get("openings") or [])[:4]
    ]
    benchmark = artifacts.get("benchmark_dashboard")
    benchmark_gaps = (
        benchmark.get("benchmark_gaps") if isinstance(benchmark, dict) else []
    )
    thesis = (
        artifacts.get("thesis_spine")
        if isinstance(artifacts, dict)
        and isinstance(artifacts.get("thesis_spine"), dict)
        else {}
    )
    return {
        "updated_at": _now(),
        "summary": (
            "First-pass source brief for infographic and narrative planning. "
            "Claims marked missing or needs_review require human review before visual use."
        ),
        "compact_claims": _fallback_infographic_claims(artifacts),
        "numeric_metrics": _fallback_numeric_metrics(company, artifacts),
        "source_traces": _source_traces_from_research_tasks(tasks, limit=10),
        "contradictions": [
            f"{item.get('claim')} [{item.get('status')}]"
            for item in evidence_summary.get("mixed_or_contradicted") or []
        ],
        "missing_evidence": [
            item.get("claim")
            for item in evidence_summary.get("missing") or []
            if item.get("claim")
        ][:10] + _string_list(benchmark_gaps)[:6],
        "no_go_claims": _string_list(
            (
                thesis.get("downside_sensitivities")
                or thesis.get("pass_triggers")
            ) if isinstance(thesis, dict) else []
        )[:8],
        "visual_opportunities": visual_opportunities,
        "narrative_opportunities": narrative_opportunities,
        "reviewer_prompts": [
            {
                "id": "prompt-visual-mode-default",
                "prompt": (
                    "Choose no-text overlay or text-in-image generation for "
                    "any infographic whose typography is central to the design."
                ),
                "required": False,
                "options": ["no_text_overlay", "text_in_image"],
                "resolved_choice": None,
                "rationale": "",
                "status": "optional",
            }
        ],
        "confidence": "low",
    }


def _infographic_source_brief_has_content(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        value.get("compact_claims")
        or value.get("numeric_metrics")
        or value.get("source_traces")
        or value.get("visual_opportunities")
        or value.get("narrative_opportunities")
    )


def _coerce_infographic_source_brief(
    value: Any,
    company: dict,
    artifacts: dict,
) -> dict:
    payload = value if isinstance(value, dict) else {}
    fallback = _infographic_source_brief(company, artifacts)
    return {
        "updated_at": _now(),
        "summary": _clean_text(payload.get("summary"), limit=1200)
        or fallback["summary"],
        "compact_claims": _coerce_infographic_claims(
            payload.get("compact_claims")
            or payload.get("claims")
            or payload.get("key_claims"),
            fallback.get("compact_claims") or [],
        ),
        "numeric_metrics": _coerce_numeric_metrics(
            payload.get("numeric_metrics") or payload.get("metrics"),
            fallback.get("numeric_metrics") or [],
        ),
        "source_traces": _normalize_source_traces(payload.get("source_traces"))
        or fallback.get("source_traces")
        or [],
        "contradictions": _string_list(
            payload.get("contradictions"),
            fallback=fallback.get("contradictions") or [],
        )[:12],
        "missing_evidence": _string_list(
            payload.get("missing_evidence"),
            fallback=fallback.get("missing_evidence") or [],
        )[:16],
        "no_go_claims": _string_list(
            payload.get("no_go_claims") or payload.get("prohibited_claims"),
            fallback=fallback.get("no_go_claims") or [],
        )[:12],
        "visual_opportunities": _coerce_opportunity_rows(
            payload.get("visual_opportunities"),
            fallback=fallback.get("visual_opportunities") or [],
            prefix="visual",
        ),
        "narrative_opportunities": _coerce_opportunity_rows(
            payload.get("narrative_opportunities"),
            fallback=fallback.get("narrative_opportunities") or [],
            prefix="narrative",
        ),
        "reviewer_prompts": _coerce_reviewer_prompts(
            payload.get("reviewer_prompts"),
            prefix="brief-prompt",
        ) or fallback.get("reviewer_prompts") or [],
        "confidence": _confidence(payload.get("confidence")),
    }


def _previous_items_by_key(previous: Any, key: str) -> tuple[dict[str, dict], dict[str, dict]]:
    if not isinstance(previous, dict):
        return {}, {}
    rows = previous.get(key)
    if not isinstance(rows, list):
        return {}, {}
    by_id: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        if row_id:
            by_id[row_id] = row
        title = _slug_part(row.get("title") or row.get("text"), fallback="")
        if title:
            by_title[title] = row
    return by_id, by_title


def _matching_previous_item(
    previous_by_id: dict[str, dict],
    previous_by_title: dict[str, dict],
    row_id: str,
    title: str,
) -> dict | None:
    if row_id in previous_by_id:
        return previous_by_id[row_id]
    key = _slug_part(title, fallback="")
    return previous_by_title.get(key)


def _coerce_text_overlay_plan(value: Any, *, title: str) -> dict:
    payload = value if isinstance(value, dict) else {}
    labels = _string_list(payload.get("labels"))[:12]
    callouts = _string_list(payload.get("callouts"))[:8]
    footnotes = _string_list(payload.get("footnotes"))[:6]
    return {
        "headline": _clean_text(payload.get("headline"), limit=120) or title,
        "labels": labels,
        "callouts": callouts,
        "footnotes": footnotes,
        "safe_copy_length": _clean_text(
            payload.get("safe_copy_length"),
            limit=160,
        )
        or "Keep overlay copy short enough for application-rendered text.",
    }


def _coerce_required_metrics(value: Any) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            label = _clean_text(row.get("label") or row.get("metric"), limit=160)
            if not label:
                continue
            out.append({
                "id": _clean_text(row.get("id"), limit=80)
                or _stable_item_id("metric", label, index),
                "label": label,
                "value": row.get("value"),
                "unit": _clean_text(row.get("unit"), limit=80) or None,
                "period": _clean_text(row.get("period"), limit=100) or None,
                "calculation": _clean_text(row.get("calculation"), limit=500),
                "denominator_note": _clean_text(
                    row.get("denominator_note"),
                    limit=500,
                ),
                "source_available": _bool_value(
                    row.get("source_available"),
                    default=bool(row.get("source_traces")),
                ),
                "source_traces": _normalize_source_traces(row.get("source_traces")),
                "confidence": _confidence(row.get("confidence")),
            })
            continue
        label = _clean_text(row, limit=160)
        if label:
            out.append({
                "id": _stable_item_id("metric", label, index),
                "label": label,
                "value": None,
                "unit": None,
                "period": None,
                "calculation": "",
                "denominator_note": "",
                "source_available": False,
                "source_traces": [],
                "confidence": "low",
            })
        if len(out) >= 12:
            break
    return out[:12]


def _coerce_data_payload(value: Any) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        label = _clean_text(row.get("label") or row.get("name"), limit=160)
        if not label:
            continue
        out.append({
            "id": _clean_text(row.get("id"), limit=80)
            or _stable_item_id("data", label, index),
            "label": label,
            "value": row.get("value"),
            "unit": _clean_text(row.get("unit"), limit=80) or None,
            "period": _clean_text(row.get("period"), limit=100) or None,
            "notes": _clean_text(row.get("notes"), limit=500),
        })
        if len(out) >= 20:
            break
    return out


def _coerce_design_prompt(value: Any, *, title: str) -> dict:
    if isinstance(value, str):
        return {
            "composition": _clean_text(value, limit=1200),
            "visual_metaphor": "",
            "style_constraints": [],
            "aspect_ratio": "16:9",
            "prohibited_claims": [],
        }
    payload = value if isinstance(value, dict) else {}
    return {
        "composition": _clean_text(payload.get("composition"), limit=1200)
        or f"Create a crisp memo infographic for {title}.",
        "visual_metaphor": _clean_text(payload.get("visual_metaphor"), limit=500),
        "style_constraints": _string_list(payload.get("style_constraints"))[:8],
        "aspect_ratio": _clean_text(payload.get("aspect_ratio"), limit=40) or "16:9",
        "prohibited_claims": _string_list(payload.get("prohibited_claims"))[:8],
    }


def _manual_chart_fields(previous: dict | None, mode: str) -> dict:
    if not isinstance(previous, dict):
        return {}
    fields: dict[str, Any] = {}
    for key in (
        "include_in_final_memo",
        "memo_inclusion_decision",
        "final_memo_inclusion_state",
        "owner",
        "memo_section_placement",
        "source_limitations",
        "diligence_needed",
        "manual_notes",
        "reviewer_notes",
        "reviewer_prompt_responses",
    ):
        if key in previous:
            fields[key] = previous[key]
    previous_mode = _coerce_image_generation_mode(previous.get("image_generation_mode"))
    if previous_mode != "needs_human_choice" and mode == "needs_human_choice":
        fields["image_generation_mode"] = previous_mode
    return fields


def _coerce_chart_specs(
    value: Any,
    company: dict,
    artifacts: dict,
    *,
    previous: Any = None,
) -> dict:
    payload = value if isinstance(value, dict) else {}
    fallback = _chart_specs(company)
    previous_by_id, previous_by_title = _previous_items_by_key(previous, "specs")
    rows = (
        payload.get("specs")
        or payload.get("charts")
        or payload.get("infographic_plans")
    )
    rows = rows if isinstance(rows, list) else []
    specs: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        title = _clean_text(row.get("title"), limit=160)
        if not title:
            continue
        row_id = _clean_text(row.get("id"), limit=80) or _stable_item_id(
            "chart",
            title,
            index,
        )
        previous_item = _matching_previous_item(
            previous_by_id,
            previous_by_title,
            row_id,
            title,
        )
        mode = _coerce_image_generation_mode(row.get("image_generation_mode"))
        reviewer_prompts = _coerce_reviewer_prompts(
            row.get("reviewer_prompts"),
            prefix=f"{row_id}-prompt",
        )
        status = _clean_text(row.get("status"), limit=60).lower()
        if not status:
            status = (
                "needs_review"
                if mode == "needs_human_choice"
                or _has_unresolved_required_prompt(reviewer_prompts)
                else "draft"
            )
        required_metrics = _coerce_required_metrics(
            row.get("required_metrics") or row.get("required_data")
        )
        information_gaps = _string_list(
            row.get("information_gaps") or row.get("gaps")
        )
        data_availability = _coerce_source_availability(
            row.get("source_availability") or row.get("data_availability")
        )
        if data_availability == "missing" and not information_gaps:
            information_gaps = _string_list(row.get("required_data"))[:8]
        source_limitations = _string_list(
            row.get("source_limitations") or row.get("diligence_needed")
        )[:8]
        inclusion_decision = _clean_text(
            row.get("memo_inclusion_decision")
            or row.get("final_memo_inclusion_state"),
            limit=40,
        ) or ("needs_review" if status == "needs_review" else "include")
        spec = {
            "id": row_id,
            "title": title,
            "purpose": _clean_text(row.get("purpose"), limit=600)
            or _clean_text(row.get("takeaway"), limit=600),
            "takeaway": _clean_text(row.get("takeaway"), limit=700),
            "recommended_visual_format": _clean_text(
                row.get("recommended_visual_format") or row.get("visual_format"),
                limit=120,
            )
            or "infographic",
            "alternate_formats": _string_list(row.get("alternate_formats"))[:6],
            "image_generation_mode": mode,
            "text_overlay_plan": _coerce_text_overlay_plan(
                row.get("text_overlay_plan"),
                title=title,
            ),
            "required_metrics": required_metrics,
            "source_availability": data_availability,
            "data_availability": data_availability,
            "source_traces": _normalize_source_traces(row.get("source_traces")),
            "information_gaps": information_gaps[:10],
            "data_payload": _coerce_data_payload(row.get("data_payload")),
            "design_prompt": _coerce_design_prompt(
                row.get("design_prompt"),
                title=title,
            ),
            "owner": _clean_text(row.get("owner"), limit=120) or "Serena",
            "source_limitations": source_limitations,
            # Legacy UI alias; new Claude-facing schema writes source_limitations.
            "diligence_needed": source_limitations,
            "memo_section_placement": _clean_text(
                row.get("memo_section_placement") or row.get("memo_section"),
                limit=120,
            )
            or "Investment Highlights",
            "include_in_final_memo": _bool_value(
                row.get("include_in_final_memo"),
                default=True,
            ),
            "memo_inclusion_decision": inclusion_decision,
            # Legacy UI alias; new Claude-facing schema writes memo_inclusion_decision.
            "final_memo_inclusion_state": inclusion_decision,
            "reviewer_prompts": reviewer_prompts,
            "status": status,
            "confidence": _confidence(row.get("confidence")),
        }
        spec.update(_manual_chart_fields(previous_item, mode))
        specs.append(spec)
        if len(specs) >= 10:
            break
    if not specs:
        for row in fallback.get("specs") or []:
            enriched = dict(row)
            enriched.setdefault("purpose", row.get("takeaway"))
            enriched.setdefault("recommended_visual_format", "infographic")
            enriched.setdefault("image_generation_mode", "no_text_overlay")
            enriched.setdefault("source_availability", row.get("data_availability"))
            enriched.setdefault("reviewer_prompts", [])
            enriched.setdefault("confidence", "low")
            specs.append(
                _coerce_chart_specs(
                    {"specs": [enriched]},
                    company,
                    artifacts,
                    previous=previous,
                )["specs"][0]
            )
    return {
        "updated_at": _now(),
        "summary": _clean_text(payload.get("summary"), limit=1200)
        or "Infographic and chart plan for memo review.",
        "generated_from_brief_id": _clean_text(
            payload.get("generated_from_brief_id"),
            limit=120,
        )
        or (
            "infographic_source_brief"
            if _infographic_source_brief_has_content(
                artifacts.get("infographic_source_brief")
            )
            else None
        ),
        "specs": specs,
        "reviewer_prompts": _coerce_reviewer_prompts(
            payload.get("reviewer_prompts"),
            prefix="chart-prompt",
        ),
        "confidence": _confidence(payload.get("confidence")),
    }


def _manual_narrative_fields(previous: dict | None) -> dict:
    if not isinstance(previous, dict):
        return {}
    fields: dict[str, Any] = {}
    for key in (
        "manual_notes",
        "reviewer_notes",
        "reviewer_prompt_responses",
    ):
        if key in previous:
            fields[key] = previous[key]
    return fields


def _coerce_hook_candidates(
    rows: Any,
    *,
    fallback_rows: list[dict],
    previous: Any,
    key: str,
    prefix: str,
    purpose: str,
) -> list[dict]:
    source_rows = rows if isinstance(rows, list) else fallback_rows
    previous_by_id, previous_by_title = _previous_items_by_key(previous, key)
    out: list[dict] = []
    for index, row in enumerate(source_rows, start=1):
        if not isinstance(row, dict):
            continue
        text = _clean_text(
            row.get("text") or row.get("hook") or row.get("candidate"),
            limit=1200,
        )
        if not text:
            continue
        row_id = _clean_text(row.get("id"), limit=80) or _stable_item_id(
            prefix,
            text,
            index,
        )
        previous_item = _matching_previous_item(
            previous_by_id,
            previous_by_title,
            row_id,
            text,
        )
        reviewer_prompts = _coerce_reviewer_prompts(
            row.get("reviewer_prompts"),
            prefix=f"{row_id}-prompt",
        )
        status = _clean_text(row.get("status"), limit=60).lower()
        if not status:
            status = (
                "needs_review"
                if _has_unresolved_required_prompt(reviewer_prompts)
                else "draft"
            )
        item = {
            "id": row_id,
            "text": text,
            "purpose": _clean_text(row.get("purpose"), limit=200) or purpose,
            "tone": _clean_text(row.get("tone"), limit=120) or "direct",
            "supported_claims": _string_list(
                row.get("supported_claims") or row.get("claims_supported")
            )[:8],
            "evidence_references": _string_list(
                row.get("evidence_references") or row.get("source_references")
            )[:10],
            "source_traces": _normalize_source_traces(row.get("source_traces")),
            "confidence": _confidence(row.get("confidence")),
            "overclaiming_risk": _clean_text(
                row.get("overclaiming_risk"),
                limit=500,
            )
            or "Review for overclaiming before memo use.",
            "paired_infographic_ids": _string_list(
                row.get("paired_infographic_ids")
                or row.get("paired_chart_ids")
                or row.get("paired_visual_ids")
            )[:8],
            "reviewer_prompts": reviewer_prompts,
            "status": status,
        }
        item.update(_manual_narrative_fields(previous_item))
        out.append(item)
        if len(out) >= 8:
            break
    return out


def _selected_candidate_id(
    previous: Any,
    payload: dict,
    key: str,
    rows: list[dict],
) -> str | None:
    requested = _clean_text(payload.get(key), limit=80)
    row_ids = {str(row.get("id")) for row in rows if row.get("id")}
    if requested in row_ids:
        return requested
    if isinstance(previous, dict):
        previous_id = _clean_text(previous.get(key), limit=80)
        if previous_id in row_ids:
            return previous_id
    return rows[0].get("id") if rows else None


def _coerce_narrative_hooks(
    value: Any,
    company: dict,
    artifacts: dict,
    *,
    previous: Any = None,
) -> dict:
    payload = value if isinstance(value, dict) else {}
    fallback = _narrative_hooks(company, artifacts)
    openings = _coerce_hook_candidates(
        payload.get("openings"),
        fallback_rows=fallback.get("openings") or [],
        previous=previous,
        key="openings",
        prefix="opening",
        purpose="opening",
    )
    transitions = _coerce_hook_candidates(
        payload.get("transitions"),
        fallback_rows=fallback.get("transitions") or [],
        previous=previous,
        key="transitions",
        prefix="transition",
        purpose="transition",
    )
    endings = _coerce_hook_candidates(
        payload.get("endings") or payload.get("closings"),
        fallback_rows=fallback.get("endings") or [],
        previous=previous,
        key="endings",
        prefix="ending",
        purpose="closing",
    )
    reviewer_prompts = _coerce_reviewer_prompts(
        payload.get("reviewer_prompts"),
        prefix="narrative-prompt",
    )
    status = _clean_text(payload.get("status"), limit=60).lower()
    if not status:
        status = (
            "needs_review"
            if _has_unresolved_required_prompt(reviewer_prompts)
            else "draft"
        )
    return {
        "updated_at": _now(),
        "summary": _clean_text(payload.get("summary"), limit=1200)
        or "Opening, transition, and closing hooks for memo review.",
        "generated_from_brief_id": _clean_text(
            payload.get("generated_from_brief_id"),
            limit=120,
        )
        or (
            "infographic_source_brief"
            if _infographic_source_brief_has_content(
                artifacts.get("infographic_source_brief")
            )
            else None
        ),
        "openings": openings,
        "transitions": transitions,
        "endings": endings,
        "selected_opening_id": _selected_candidate_id(
            previous,
            payload,
            "selected_opening_id",
            openings,
        ),
        "selected_transition_id": _selected_candidate_id(
            previous,
            payload,
            "selected_transition_id",
            transitions,
        ),
        "selected_ending_id": _selected_candidate_id(
            previous,
            payload,
            "selected_ending_id",
            endings,
        ),
        "reviewer_prompts": reviewer_prompts,
        "status": status,
        "confidence": _confidence(payload.get("confidence")),
    }


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("%", "").replace("x", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_source_traces(value: Any) -> list[dict]:
    rows = value if isinstance(value, list) else []
    traces: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        excerpt = _clean_text(row.get("excerpt"), limit=700)
        if not excerpt:
            continue
        traces.append({
            "title": _clean_text(row.get("title"), limit=160) or None,
            "url": _clean_text(row.get("url"), limit=500) or None,
            "locator": _clean_text(row.get("locator"), limit=160) or None,
            "excerpt": excerpt,
            "confidence": _confidence(row.get("confidence")),
        })
        if len(traces) >= 10:
            break
    return traces


def _coerce_benchmark_dashboard(value: Any, company: dict) -> dict:
    payload = value if isinstance(value, dict) else {}
    fallback = _benchmark_dashboard(company)
    comps: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows = payload.get("public_comps")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _clean_text(row.get("company") or row.get("name"), limit=120)
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            comps.append({
                "id": f"comp-{len(comps) + 1}",
                "company": name,
                "ticker": _clean_text(row.get("ticker"), limit=20) or None,
                "why_relevant": _clean_text(
                    row.get("why_relevant") or row.get("rationale"),
                    limit=500,
                ) or "Relevant public benchmark; verify comparability.",
                "revenue_growth_pct": _number_or_none(row.get("revenue_growth_pct")),
                "gross_margin_pct": _number_or_none(row.get("gross_margin_pct")),
                "ev_revenue": _number_or_none(row.get("ev_revenue")),
                "ev_ebitda": _number_or_none(row.get("ev_ebitda")),
                "fcf_margin_pct": _number_or_none(row.get("fcf_margin_pct")),
                "rule_of_40": _number_or_none(row.get("rule_of_40")),
                "metric_period": _clean_text(row.get("metric_period"), limit=80) or None,
                "sell_side_theme": _clean_text(row.get("sell_side_theme"), limit=500) or (
                    "Theme requires filing, transcript, or sell-side verification."
                ),
                "source_traces": _normalize_source_traces(row.get("source_traces")),
                "confidence": _confidence(row.get("confidence")),
            })
            if len(comps) >= 8:
                break
    if len(comps) < 3:
        for row in fallback.get("public_comps") or []:
            if len(comps) >= 3:
                break
            key = str(row.get("company") or "").strip().lower()
            if not key or key in seen:
                continue
            item = copy.deepcopy(row)
            item["id"] = f"comp-{len(comps) + 1}"
            comps.append(item)
            seen.add(key)
    return {
        "updated_at": _now(),
        "summary": _clean_text(payload.get("summary"), limit=1000) or fallback["summary"],
        "public_comps": comps,
        "benchmark_gaps": _string_list(
            payload.get("benchmark_gaps"),
            fallback=fallback.get("benchmark_gaps") or [],
        )[:10],
        "must_prove": _string_list(
            payload.get("must_prove"),
            fallback=fallback.get("must_prove") or [],
        )[:10],
        "source_traces": _normalize_source_traces(payload.get("source_traces")),
        "confidence": _confidence(payload.get("confidence")),
    }


def _benchmark_dashboard(company: dict) -> dict:
    competitors = list(company.get("competitors") or [])
    sector = company.get("sector") or company.get("industry") or "sector"
    fallback = {
        "AI": ["MSFT", "GOOGL", "NOW", "PLTR", "ADBE"],
        "Software": ["NOW", "ADBE", "CRM", "SNOW", "DDOG"],
        "Defense": ["LMT", "NOC", "RTX", "GD", "BA"],
        "Robotics": ["TER", "ISRG", "ROK", "ABB", "FANUY"],
    }
    sector_key = next((k for k in fallback if k.lower() in sector.lower()), None)
    names = competitors[:5] or fallback.get(sector_key or "", ["NOW", "ADBE", "CRM", "SNOW", "PLTR"])
    comps = []
    for i, name in enumerate(names[:6], start=1):
        comps.append({
            "id": f"comp-{i}",
            "company": name,
            "ticker": name if name.isupper() and len(name) <= 6 else None,
            "why_relevant": "Closest available business-model or category benchmark; requires verification.",
            "revenue_growth_pct": None,
            "gross_margin_pct": None,
            "ev_revenue": None,
            "ev_ebitda": None,
            "fcf_margin_pct": None,
            "rule_of_40": None,
            "metric_period": None,
            "sell_side_theme": "To be filled from filings, earnings transcripts, and sell-side notes.",
            "source_traces": [],
            "confidence": "low",
        })
    return {
        "updated_at": _now(),
        "summary": "Initial benchmark scaffold. Metrics need sell-side / filing research before memo use.",
        "public_comps": comps,
        "benchmark_gaps": [
            "Verify which comps are mature and economically comparable.",
            "Fill growth, margin, and valuation metrics.",
            "Extract sell-side themes and map them to private-company proof points.",
        ],
        "must_prove": [
            "Growth durability deserves the comp set.",
            "Margins and implementation burden do not require a lower multiple.",
            "Deployment depth supports public-comp treatment.",
        ],
        "source_traces": [],
        "confidence": "low",
    }


def _memo_packet_evidence_summary(tasks: list[dict]) -> dict:
    summary = {
        "mixed_or_contradicted": [],
        "missing": [],
        "supported": [],
    }
    for task in tasks:
        if not isinstance(task, dict) or task.get("status") != "done":
            continue
        claim = (
            task.get("answer")
            or task.get("result_summary")
            or task.get("title")
            or task.get("id")
        )
        claim = str(claim or "").strip()
        if not claim:
            continue
        supporting = [
            item for item in task.get("supporting_evidence") or []
            if isinstance(item, dict) and item.get("excerpt")
        ]
        contradicting = [
            item for item in task.get("contradicting_evidence") or []
            if isinstance(item, dict) and item.get("excerpt")
        ]
        questions = [
            str(item).strip()
            for item in (
                task.get("remaining_evidence_limits")
                or task.get("open_questions")
                or []
            )
            if str(item or "").strip()
        ]
        if supporting and contradicting:
            status = "mixed"
        elif contradicting:
            status = "contradicted"
        elif supporting:
            status = "supported"
        else:
            status = "missing"
        if status in {"mixed", "contradicted"}:
            summary["mixed_or_contradicted"].append({
                "claim": claim,
                "status": status,
                "supporting_count": len(supporting),
                "contradicting_count": len(contradicting),
            })
        if questions or status == "missing":
            summary["missing"].append({
                "claim": claim,
                "questions": questions,
            })
        if status == "supported":
            evidence = supporting[0]
            summary["supported"].append({
                "claim": claim,
                "locator": evidence.get("locator") or evidence.get("filename"),
                "excerpt": evidence.get("excerpt"),
                "confidence": evidence.get("confidence") or task.get("confidence"),
            })
    return summary


def _memo_packet_source_fingerprint(session: dict) -> str:
    artifacts = (
        session.get("artifacts")
        if isinstance(session.get("artifacts"), dict)
        else {}
    )
    source_artifacts = {
        key: value
        for key, value in artifacts.items()
        if key != "memo_packet"
    }
    payload = {
        "id": session.get("id"),
        "company_id": session.get("company_id"),
        "company_name": session.get("company_name"),
        "status": session.get("status"),
        "approved_for_memo": bool(session.get("approved_for_memo")),
        "artifacts": source_artifacts,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _question_to_sensitivity_statement(value: str | None) -> str:
    """Convert internal question-shaped prompts into sensitivity prose."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    text = raw.rstrip(" ?")
    lowered = text.lower()
    is_question_shaped = raw.endswith("?") or lowered.startswith(
        ("is ", "are ", "can ", "does ", "do ", "what is ", "what are ", "how ")
    )
    if not is_question_shaped:
        return raw if raw.endswith((".", "!", ";")) else f"{raw}."

    def decap(fragment: str) -> str:
        fragment = fragment.strip()
        if not fragment:
            return ""
        return fragment[0].lower() + fragment[1:]
    if lowered.startswith("is "):
        return f"Sensitivity: {text[3:]}."
    if lowered.startswith("are "):
        return f"Sensitivity: {text[4:]}."
    if lowered.startswith("can "):
        return f"Sensitivity: {text[4:]}."
    if lowered.startswith("does "):
        return f"Sensitivity: {text[5:]}."
    if lowered.startswith("do "):
        return f"Sensitivity: {text[3:]}."
    if lowered.startswith("what is "):
        return f"Sensitivity: specified {text[8:]}."
    if lowered.startswith("what are "):
        return f"Sensitivity: specified {text[9:]}."
    if lowered.startswith("how "):
        return f"Sensitivity: {text}."
    return f"Sensitivity: {decap(text)}."


def _memo_packet_is_current(session: dict) -> bool:
    artifacts = (
        session.get("artifacts")
        if isinstance(session.get("artifacts"), dict)
        else {}
    )
    packet = artifacts.get("memo_packet")
    if not isinstance(packet, str) or not packet.strip():
        return False
    return (
        session.get("memo_packet_source_fingerprint")
        == _memo_packet_source_fingerprint(session)
    )


def _refresh_memo_packet(session: dict) -> None:
    artifacts = session.setdefault("artifacts", {})
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts.get("thesis_spine"), dict) else {}
    risks = artifacts.get("strategic_risks") if isinstance(artifacts.get("strategic_risks"), dict) else {}
    research_tasks = artifacts.get("research_tasks") if isinstance(artifacts.get("research_tasks"), dict) else {}
    source_brief = artifacts.get("infographic_source_brief") if isinstance(artifacts.get("infographic_source_brief"), dict) else {}
    chart_specs = artifacts.get("chart_specs") if isinstance(artifacts.get("chart_specs"), dict) else {}
    hooks = artifacts.get("narrative_hooks") if isinstance(artifacts.get("narrative_hooks"), dict) else {}
    benchmark = artifacts.get("benchmark_dashboard") if isinstance(artifacts.get("benchmark_dashboard"), dict) else {}
    readiness_reviews = _normalize_readiness_reviews(artifacts.get("readiness_reviews"))
    excluded_chart_ids = {
        str(item.get("id"))
        for item in chart_specs.get("specs") or []
        if isinstance(item, dict) and item.get("include_in_final_memo") is False
    }
    excluded_chart_titles = {
        _slug_part(item.get("title"), fallback="")
        for item in chart_specs.get("specs") or []
        if isinstance(item, dict) and item.get("include_in_final_memo") is False
    }

    def selected(items: list[dict], selected_id: str | None) -> dict | None:
        return next((item for item in items if item.get("id") == selected_id), None)

    selected_opening = selected(
        hooks.get("openings") or [],
        hooks.get("selected_opening_id"),
    )
    selected_ending = selected(
        hooks.get("endings") or [],
        hooks.get("selected_ending_id"),
    )
    selected_transition = selected(
        hooks.get("transitions") or [],
        hooks.get("selected_transition_id"),
    )

    lines = [
        f"# Serena Memo Analysis Packet — {session.get('company_name')}",
        "",
        f"- analysis_session_id: {session.get('id')}",
        f"- status: {session.get('status')}",
        f"- approved_for_memo: {bool(session.get('approved_for_memo'))}",
        "",
        "## Final Memo Handoff Guidance",
        "",
        (
            "Use this packet as evidence, not copy. The final memo must translate "
            "evidence matrices, research tasks, risks, and sensitivities into "
            "partner-level conclusions."
        ),
        "",
        (
            "Write in the LP co-invest register: firm as subject, deal "
            "English, named proof, plain risks. Do not write stock "
            "participation slogans, detached IC jargon, or passive "
            "sponsor-capability speculation."
        ),
        "",
        (
            "Never copy internal source labels, operator prompts, artifact names, "
            "bracketed source tokens, visual-design notes, methodology notes, "
            "artifact metadata, or validation language into "
            "final body prose or operating tables."
        ),
        "",
        (
            "Convert source evidence details into source-class and model-treatment "
            "language in Sections I-V. Use detailed source references only for "
            "the fact reference index or a clearly separated source-treatment appendix."
        ),
        "",
        "## Memo Spine For Final Draft",
    ]
    highlights = [
        item for item in thesis.get("investment_highlights") or []
        if isinstance(item, dict)
    ]
    sensitivities = _thesis_sensitivity_rows(thesis)
    core_bet = "Final draft must state the core investment bet in the opening."
    if highlights:
        first = highlights[0]
        detail = first.get("detail")
        core_bet = str(first.get("claim") or core_bet)
        if detail:
            core_bet = f"{core_bet}: {detail}"
    current_proof = [
        str(item.get("claim") or "").strip()
        for item in highlights[:3]
        if str(item.get("claim") or "").strip()
    ]
    unproven = [
        _sensitivity_statement(item)
        for item in sensitivities[:3]
        if _sensitivity_statement(item)
    ]
    downside_sensitivities = [
        str(item).strip()
        for item in (
            thesis.get("downside_sensitivities")
            or thesis.get("pass_triggers")
            or []
        )
        if str(item or "").strip()
    ][:3]
    recommendation_logic = str(
        thesis.get("recommendation_logic")
        or "State the recommendation, valuation sensitivities, failure modes, and deal mechanics."
    ).strip()
    lines += [
        "",
        f"- **core_bet:** {core_bet}",
        (
            "- **entry_tension:** State what the valuation, instrument, or "
            "entry terms already assume, especially where proof is incomplete."
        ),
        (
            "- **current_proof:** "
            + (
                "; ".join(current_proof)
                if current_proof
                else "Summarize only source-classed evidence proven today."
            )
        ),
        (
            "- **unproven_but_modelable:** "
            + (
                "; ".join(unproven)
                if unproven
                else "List missing proof that can be modeled with conservative ranges."
            )
        ),
        (
            "- **risk_sensitivity:** "
            + (
                "; ".join(downside_sensitivities)
                if downside_sensitivities
                else "Name the evidence that strengthens or weakens valuation support."
            )
        ),
        f"- **action:** {recommendation_logic}",
        "",
        "## Investment Highlights",
    ]
    for item in thesis.get("investment_highlights") or []:
        lines.append(f"- **{item.get('claim')}** — {item.get('detail')}")
    lines += ["", "## Investment Risks"]
    for item in thesis.get("investment_risks") or []:
        lines.append(f"- **{item.get('claim')}** — {item.get('detail')}")
    lines += ["", "## Risk And Valuation Sensitivities"]
    for item in sensitivities:
        action = _sensitivity_statement(item)
        if action:
            support = _sensitivity_support(item)
            downside = _sensitivity_downside(item)
            line = f"- **{action}**"
            details = [text for text in (support, downside) if text]
            if details:
                line += " — " + " ".join(details)
            lines.append(line)
    lines += packet_strategic_risk_lines(
        risks.get("risks") or [],
        (artifacts.get("risk_priorities") or {}).get("priorities")
        if isinstance(artifacts.get("risk_priorities"), dict)
        else [],
    )
    if research_tasks.get("tasks"):
        lines += ["", "## Evidence Review Results"]
        for item in research_tasks.get("tasks") or []:
            lines.append(f"- **{item.get('title')}**")
            if item.get("result_summary"):
                lines.append(f"  - Result: {item.get('result_summary')}")
                supporting = item.get("supporting_evidence") or []
                if supporting:
                    lines.append("  - Source support:")
                    for evidence in supporting[:3]:
                        locator = evidence.get("locator") or evidence.get("filename")
                        prefix = f"{locator}: " if locator else ""
                        lines.append(f"    - {prefix}{evidence.get('excerpt')}")
                contradicting = item.get("contradicting_evidence") or []
                if contradicting:
                    lines.append("  - Contradicting evidence:")
                    for evidence in contradicting[:3]:
                        locator = evidence.get("locator") or evidence.get("filename")
                        prefix = f"{locator}: " if locator else ""
                        lines.append(f"    - {prefix}{evidence.get('excerpt')}")
                open_questions = (
                    item.get("remaining_evidence_limits")
                    or item.get("open_questions")
                    or []
                )
                if open_questions:
                    lines.append("  - Risk and valuation sensitivities:")
                    for question in open_questions[:3]:
                        action = _question_to_sensitivity_statement(question)
                        if action:
                            lines.append(f"    - {action}")
        evidence_summary = _memo_packet_evidence_summary(research_tasks.get("tasks") or [])
        if any(evidence_summary.values()):
            lines += ["", "## Evidence Matrix Summary"]
            if evidence_summary["mixed_or_contradicted"]:
                lines.append("- Mixed / contradicted claims:")
                for item in evidence_summary["mixed_or_contradicted"][:5]:
                    lines.append(
                        "  - "
                        f"**{item['claim']}** [{item['status']}] — "
                        f"{item['supporting_count']} supporting / "
                        f"{item['contradicting_count']} contradicting."
                    )
            if evidence_summary["missing"]:
                lines.append("- Missing evidence / sensitivities:")
                for item in evidence_summary["missing"][:5]:
                    questions = item.get("questions") or []
                    suffix = "; ".join(questions[:3]) if questions else "No source-backed evidence yet."
                    lines.append(f"  - **{item['claim']}** — {suffix}")
            if evidence_summary["supported"]:
                lines.append("- Strongest source-backed support:")
                for item in evidence_summary["supported"][:5]:
                    locator = f"{item.get('locator')}: " if item.get("locator") else ""
                    confidence = f" ({item.get('confidence')})" if item.get("confidence") else ""
                    lines.append(
                        f"  - **{item['claim']}** — {locator}{item.get('excerpt')}{confidence}"
                    )
    if _infographic_source_brief_has_content(source_brief):
        lines += ["", "## Visual Evidence Decisions"]
        if source_brief.get("summary"):
            lines.append(f"- Summary: {source_brief.get('summary')}")
        if source_brief.get("compact_claims"):
            lines.append("- Compact claims:")
            for claim in (source_brief.get("compact_claims") or [])[:8]:
                lines.append(
                    "  - "
                    f"**{claim.get('claim')}** — "
                    f"{claim.get('evidence_status') or 'source support needs review'}"
                )
        if source_brief.get("numeric_metrics"):
            lines.append("- Numeric metrics:")
            for metric in (source_brief.get("numeric_metrics") or [])[:10]:
                unit = metric.get("unit") or ""
                period = f" ({metric.get('period')})" if metric.get("period") else ""
                lines.append(
                    "  - "
                    f"{metric.get('label')}: {metric.get('value')}{unit}{period}"
                )
        if source_brief.get("contradictions"):
            lines.append("- Contradictions / mixed evidence:")
            for item in (source_brief.get("contradictions") or [])[:8]:
                lines.append(f"  - {item}")
        if source_brief.get("missing_evidence"):
            lines.append("- Evidence limits:")
            for item in (source_brief.get("missing_evidence") or [])[:8]:
                lines.append(f"  - {item}")
        if source_brief.get("no_go_claims"):
            lines.append("- Claims to treat as unsupported in visuals:")
            for item in (source_brief.get("no_go_claims") or [])[:8]:
                lines.append(f"  - {item}")
        if source_brief.get("visual_opportunities"):
            lines.append("- Visual opportunities:")
            for item in (source_brief.get("visual_opportunities") or [])[:6]:
                item_id = str(item.get("id") or "")
                title_key = _slug_part(item.get("title"), fallback="")
                if item_id in excluded_chart_ids or title_key in excluded_chart_titles:
                    continue
                lines.append(
                    f"  - **{item.get('title')}** — {item.get('rationale')}"
                )
    if benchmark.get("public_comps"):
        lines += ["", "## Benchmark Valuation Context"]
        if benchmark.get("summary"):
            lines.append(f"- Summary: {benchmark.get('summary')}")
        lines += [
            "",
            "| Company | Ticker | Growth % | Gross Margin % | EV/Revenue | EV/EBITDA | FCF Margin % | Rule of 40 | Period |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for comp in benchmark.get("public_comps") or []:
            lines.append(
                "| "
                f"{comp.get('company') or ''} | "
                f"{comp.get('ticker') or ''} | "
                f"{comp.get('revenue_growth_pct') if comp.get('revenue_growth_pct') is not None else ''} | "
                f"{comp.get('gross_margin_pct') if comp.get('gross_margin_pct') is not None else ''} | "
                f"{comp.get('ev_revenue') if comp.get('ev_revenue') is not None else ''} | "
                f"{comp.get('ev_ebitda') if comp.get('ev_ebitda') is not None else ''} | "
                f"{comp.get('fcf_margin_pct') if comp.get('fcf_margin_pct') is not None else ''} | "
                f"{comp.get('rule_of_40') if comp.get('rule_of_40') is not None else ''} | "
                f"{comp.get('metric_period') or ''} |"
            )
        if benchmark.get("benchmark_gaps"):
            lines += ["", "- Benchmark evidence limits:"]
            for gap in benchmark.get("benchmark_gaps") or []:
                lines.append(f"  - {gap}")
        if benchmark.get("must_prove"):
            lines += ["", "- Private-company proof points:"]
            for claim in benchmark.get("must_prove") or []:
                lines.append(f"  - {claim}")
    lines += ["", "## Selected Visual Decisions"]
    for item in chart_specs.get("specs") or []:
        if item.get("include_in_final_memo"):
            visual_format = item.get("recommended_visual_format") or "infographic"
            lines.append(f"- **{item.get('title')}** — {visual_format}")
            if item.get("purpose") or item.get("takeaway"):
                lines.append(
                    f"  - Supported takeaway: {item.get('purpose') or item.get('takeaway')}"
                )
            overlay = item.get("text_overlay_plan") or {}
            if overlay:
                lines.append(f"  - Visual headline: {overlay.get('headline') or item.get('title')}")
                for callout in (overlay.get("callouts") or [])[:4]:
                    lines.append(f"    - Callout: {callout}")
                for footnote in (overlay.get("footnotes") or [])[:3]:
                    lines.append(f"    - Footnote: {footnote}")
            if item.get("required_metrics"):
                lines.append("  - Required metrics:")
                for metric in (item.get("required_metrics") or [])[:6]:
                    available = "sourced" if metric.get("source_available") else "not sourced"
                    value = metric.get("value")
                    value_text = f" = {value}" if value not in (None, "") else ""
                    unit = metric.get("unit") or ""
                    lines.append(
                        f"    - {metric.get('label')}{value_text}{unit} [{available}]"
                    )
            if item.get("information_gaps"):
                lines.append("  - Evidence limits:")
                for gap in (item.get("information_gaps") or [])[:5]:
                    lines.append(f"    - {gap}")
    if selected_opening or selected_transition or selected_ending:
        lines += [
            "",
            "## Selected Narrative Direction",
            "",
            (
                "Use these operator-selected choices as final memo guidance "
                "for intro stance, risk-section posture, and conclusion posture. "
                "They are source-backed direction, not text that must be copied verbatim. "
                "Rewrite any detached phrasing into firm-as-subject deal English."
            ),
        ]
        if selected_opening:
            lines.append(f"- Intro stance: {selected_opening.get('text')}")
            if selected_opening.get("overclaiming_risk"):
                lines.append(
                    f"  - Overclaiming risk: {selected_opening.get('overclaiming_risk')}"
                )
        if selected_transition:
            lines.append(f"- Risk-section posture: {selected_transition.get('text')}")
            if selected_transition.get("overclaiming_risk"):
                lines.append(
                    f"  - Overclaiming risk: {selected_transition.get('overclaiming_risk')}"
                )
        if selected_ending:
            lines.append(f"- Conclusion posture: {selected_ending.get('text')}")
            if selected_ending.get("overclaiming_risk"):
                lines.append(
                    f"  - Overclaiming risk: {selected_ending.get('overclaiming_risk')}"
                )
    artifacts["memo_packet"] = "\n".join(lines).strip() + "\n"
    session["memo_packet_source_fingerprint"] = _memo_packet_source_fingerprint(session)


def _strip_decorations(session: dict) -> dict:
    return {
        k: v for k, v in session.items()
        if k not in {
            "tools",
            "readiness",
            "additional_areas",
            "completed_memo_runs",
            "has_unapproved_work",
            "regular_memo_warning",
        }
    }


def _catalog_slug(value: str, *, fallback: str = "artifact") -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_.-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip(".-")
    return (raw or fallback)[:96]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _memo_generated_file_record(kind: str, path_value: Any, *, created_at: Any) -> dict:
    path = Path(str(path_value or ""))
    record = {
        "kind": str(kind or "artifact"),
        "path": str(path),
        "sha256": "",
        "bytes": 0,
        "created_at": created_at or _now(),
    }
    try:
        data = path.read_bytes()
    except Exception:
        return record
    record["sha256"] = hashlib.sha256(data).hexdigest()
    record["bytes"] = len(data)
    return record


def _memo_generated_files(paths: list[Any] | None, *, created_at: Any) -> list[dict]:
    files = []
    for index, path in enumerate(paths or [], start=1):
        if isinstance(path, dict):
            kind = path.get("kind") or path.get("language") or f"file_{index}"
            path_value = path.get("path")
        else:
            kind = f"file_{index}"
            path_value = path
        if path_value:
            files.append(_memo_generated_file_record(str(kind), path_value, created_at=created_at))
    return files


def _memo_work_product_fingerprint(row: dict) -> str:
    payload = {
        "generated_files": [
            {
                "kind": file.get("kind"),
                "path": file.get("path"),
                "sha256": file.get("sha256"),
                "bytes": file.get("bytes"),
            }
            for file in row.get("generated_files") or []
            if isinstance(file, dict)
        ],
        "source_refs": row.get("source_refs") or [],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _memo_version_id(artifact_id: str, version: int, fingerprint: str) -> str:
    digest = (fingerprint or hashlib.sha256(artifact_id.encode("utf-8")).hexdigest())[:12]
    return f"{artifact_id}:v{version}:{digest}"


def _memo_version_records(company_id: str, session_id: str) -> list[dict]:
    data = _read_json(
        memo_work_product_versions_path(company_id, session_id),
        {"versions": []},
    )
    rows = data.get("versions") if isinstance(data, dict) else []
    out = [row for row in rows if isinstance(row, dict)]
    out.sort(key=lambda row: (str(row.get("artifact_id", "")), int(row.get("version") or 0)))
    return out


def _write_memo_version_records(company_id: str, session_id: str, rows: list[dict]) -> None:
    rows.sort(key=lambda row: (str(row.get("artifact_id", "")), int(row.get("version") or 0)))
    _write_json(
        memo_work_product_versions_path(company_id, session_id),
        {
            "schema_version": MEMO_WORK_PRODUCT_VERSION_SCHEMA_VERSION,
            "versions": rows,
        },
    )


def _snapshot_memo_generated_files(
    company_id: str,
    session_id: str,
    row: dict,
) -> list[dict]:
    version_id = str(row.get("version_id") or "")
    artifact_id = str(row.get("artifact_id") or "")
    if not version_id or not artifact_id:
        return row.get("generated_files") or []
    target_dir = (
        memo_work_product_version_files_root(company_id, session_id)
        / _catalog_slug(artifact_id)
        / _catalog_slug(version_id, fallback="version")
    )
    snapshots = []
    for file in row.get("generated_files") or []:
        if not isinstance(file, dict):
            continue
        source = Path(str(file.get("path") or ""))
        if not source.exists():
            snapshots.append(file)
            continue
        kind = str(file.get("kind") or "artifact")
        suffix = source.suffix or ".artifact"
        target = target_dir / f"{_catalog_slug(kind)}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        snapshots.append(
            _memo_generated_file_record(
                kind,
                target,
                created_at=file.get("created_at") or row.get("updated_at") or _now(),
            )
        )
    return snapshots


def _memo_versionable_row(row: dict) -> bool:
    if row.get("status") == "missing":
        return False
    return bool(row.get("generated_files"))


def _sync_memo_catalog_versions(session: dict, rows: list[dict]) -> None:
    company_id = _safe_id(str(session.get("company_id") or ""))
    session_id = _safe_id(str(session.get("id") or ""))
    records = _memo_version_records(company_id, session_id)
    records_by_artifact: dict[str, list[dict]] = {}
    for record in records:
        records_by_artifact.setdefault(str(record.get("artifact_id") or ""), []).append(record)

    changed = False
    for row in rows:
        row.setdefault("version_id", None)
        row.setdefault("supersedes_version_id", None)
        row.setdefault("generated_files", [])
        row.setdefault("version_count", 0)
        row.setdefault("review_log", [])
        row.setdefault("action_log", [])
        row.setdefault("latest_review_action", None)
        if not _memo_versionable_row(row):
            continue

        artifact_id = str(row.get("artifact_id") or "")
        fingerprint = _memo_work_product_fingerprint(row)
        artifact_records = records_by_artifact.setdefault(artifact_id, [])
        latest = artifact_records[-1] if artifact_records else None
        if latest and latest.get("fingerprint") == fingerprint:
            row["version"] = latest.get("version") or row.get("version") or 1
            row["version_id"] = latest.get("version_id")
            row["supersedes_version_id"] = latest.get("supersedes_version_id")
            row["generated_files"] = latest.get("generated_files") or row.get("generated_files") or []
            row["version_count"] = len(artifact_records)
            row["action_log"] = latest.get("action_log") or []
            continue

        version = int((latest or {}).get("version") or 0) + 1
        version_id = _memo_version_id(artifact_id, version, fingerprint)
        row["version"] = version
        row["version_id"] = version_id
        row["supersedes_version_id"] = (latest or {}).get("version_id")
        row["version_count"] = len(artifact_records) + 1
        action_event = {
            "event_id": f"memov-{uuid.uuid4().hex[:10]}",
            "action": "created" if version == 1 else "versioned",
            "version_id": version_id,
            "version": version,
            "updated_at": row.get("updated_at") or _now(),
            "changed_fields": ["generated_files", "source_refs"],
        }
        row["action_log"] = [*row.get("action_log", []), action_event]
        snapshot_files = _snapshot_memo_generated_files(company_id, session_id, row)
        row["generated_files"] = snapshot_files
        record = {
            "schema_version": MEMO_WORK_PRODUCT_VERSION_SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "artifact_type": row.get("artifact_type"),
            "title": row.get("title"),
            "version": version,
            "version_id": version_id,
            "supersedes_version_id": row.get("supersedes_version_id"),
            "created_at": row.get("updated_at") or row.get("created_at") or _now(),
            "updated_at": row.get("updated_at") or _now(),
            "generated_by": row.get("generated_by"),
            "source_refs": row.get("source_refs") or [],
            "source_trace_count": row.get("source_trace_count") or 0,
            "confidence": row.get("confidence"),
            "export_paths": row.get("export_paths") or [],
            "generated_files": snapshot_files,
            "fingerprint": fingerprint,
            "review_log": [],
            "action_log": [action_event],
        }
        records.append(record)
        artifact_records.append(record)
        changed = True

    if changed:
        _write_memo_version_records(company_id, session_id, records)


def _artifact_has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return value is not None


_MEMO_CATALOG_SOURCE_KEYS = {
    "source_traces",
    "source_refs",
    "supporting_evidence",
    "contradicting_evidence",
}


def _memo_catalog_source_trace_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key in _MEMO_CATALOG_SOURCE_KEYS:
            raw = value.get(key)
            if isinstance(raw, list):
                count += sum(1 for item in raw if isinstance(item, dict))
        for child in value.values():
            count += _memo_catalog_source_trace_count(child)
    elif isinstance(value, list):
        for item in value:
            count += _memo_catalog_source_trace_count(item)
    return count


def _memo_catalog_source_refs(value: Any, *, limit: int = 12) -> list[dict]:
    refs: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add_ref(row: dict) -> None:
        if len(refs) >= limit:
            return
        title = str(
            row.get("title")
            or row.get("filename")
            or row.get("source_title")
            or row.get("source")
            or row.get("file_id")
            or row.get("url")
            or ""
        ).strip()
        locator = str(row.get("locator") or row.get("page") or "").strip()
        excerpt = str(row.get("excerpt") or row.get("quote") or "").strip()
        if not title and not locator and not excerpt:
            return
        key = (title, locator, excerpt[:120])
        if key in seen:
            return
        seen.add(key)
        ref = {
            "title": title or "Source evidence",
            "locator": locator,
            "excerpt": excerpt,
            "confidence": row.get("confidence"),
        }
        if row.get("file_id"):
            ref["file_id"] = row.get("file_id")
        if row.get("url"):
            ref["url"] = row.get("url")
        refs.append(ref)

    def walk(node: Any) -> None:
        if len(refs) >= limit:
            return
        if isinstance(node, dict):
            for key in _MEMO_CATALOG_SOURCE_KEYS:
                raw = node.get(key)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            add_ref(item)
                        if len(refs) >= limit:
                            return
            for child in node.values():
                walk(child)
                if len(refs) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                walk(item)
                if len(refs) >= limit:
                    return

    walk(value)
    return refs


def _memo_catalog_updated_at(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, dict):
        for key in (
            "updated_at",
            "completed_at",
            "last_run_at",
            "generated_at",
            "created_at",
        ):
            if value.get(key):
                return value.get(key)
    return fallback


def _memo_catalog_generated_by(value: Any) -> str | None:
    if isinstance(value, dict):
        generated_by = value.get("generated_by") or value.get("result_generated_by")
        if generated_by:
            return str(generated_by)
    return None


def _memo_catalog_confidence(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("confidence"):
        return str(value.get("confidence"))
    return None


def _memo_catalog_review_state(session: dict, value: Any = None) -> str:
    if session.get("approved_for_memo"):
        return "approved"
    if isinstance(value, dict):
        state = str(
            value.get("review_state")
            or value.get("memo_inclusion_decision")
            or value.get("final_memo_inclusion_state")
            or ""
        ).strip()
        if state:
            return state
    return "needs_review" if _artifact_has_content(value) else "missing"


def _memo_catalog_status(session: dict, value: Any = None) -> str:
    if not _artifact_has_content(value):
        return "missing"
    if isinstance(value, dict):
        raw_status = str(value.get("status") or "").strip().lower()
        if raw_status in {"running"}:
            return "running"
        if raw_status in {"error", "failed"}:
            return "failed"
        if raw_status in {"complete", "completed", "published"}:
            return "published"
    if session.get("approved_for_memo"):
        return "approved"
    return "needs_review"


def _memo_catalog_row(
    session: dict,
    *,
    artifact_id: str,
    artifact_type: str,
    title: str,
    value: Any = None,
    location: str | None = None,
    export_paths: list[str] | None = None,
    notes: str = "",
    status: str | None = None,
    updated_at: Any = None,
    created_at: Any = None,
    generated_file_paths: list[Any] | None = None,
) -> dict:
    source_refs = _memo_catalog_source_refs(value)
    row_updated_at = updated_at or _memo_catalog_updated_at(
        value,
        session.get("updated_at"),
    )
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "title": title,
        "status": status or _memo_catalog_status(session, value),
        "version": 1,
        "version_id": None,
        "supersedes_version_id": None,
        "created_at": created_at or session.get("created_at"),
        "updated_at": row_updated_at,
        "generated_by": _memo_catalog_generated_by(value),
        "reviewer": None,
        "source_refs": source_refs,
        "source_trace_count": _memo_catalog_source_trace_count(value),
        "confidence": _memo_catalog_confidence(value),
        "review_state": _memo_catalog_review_state(session, value),
        "supersedes": None,
        "superseded_by": None,
        "pinned": False,
        "archived": False,
        "export_paths": export_paths or [],
        "generated_files": _memo_generated_files(
            generated_file_paths,
            created_at=row_updated_at,
        ),
        "version_count": 0,
        "latest_review_action": None,
        "review_log": [],
        "action_log": [],
        "location": location,
        "notes": notes,
    }


def _memo_artifact_generated_file_paths(
    company_id: str,
    session_id: str,
    filename: str,
    value: Any,
    *,
    kind: str | None = None,
) -> list[dict]:
    if not _artifact_has_content(value):
        return []
    path = session_dir(company_id, session_id) / filename
    if not path.exists():
        return []
    file_kind = kind or path.suffix.lstrip(".") or "artifact"
    return [{"kind": file_kind, "path": path}]


def _memo_evidence_matrix_snapshot(
    company_id: str,
    session_id: str,
) -> tuple[dict | None, list[dict]]:
    """Persist a deterministic evidence-matrix snapshot for catalog versioning."""
    try:
        from . import evidence_matrix

        matrix = evidence_matrix.build_company_evidence_matrix(company_id)
    except Exception:
        logger.exception("Failed to build evidence matrix snapshot for %s", company_id)
        return None, []
    if not isinstance(matrix, dict):
        return None, []
    snapshot = copy.deepcopy(matrix)
    snapshot.pop("generated_at", None)
    snapshot["snapshot_type"] = "memo_evidence_matrix"
    path = session_dir(company_id, session_id) / "evidence_matrix.json"
    current = _read_json(path, None)
    if _canonical_json(current) != _canonical_json(snapshot):
        _write_json(path, snapshot)
    return snapshot, [{"kind": "json", "path": path}]


def _memo_work_product_catalog(session: dict) -> dict:
    company_id = _safe_id(str(session.get("company_id") or ""))
    session_id = _safe_id(str(session.get("id") or ""))
    analysis_prefix = f"data/serena_analysis/{company_id}/{session_id}/"
    artifacts = session.get("artifacts") if isinstance(session.get("artifacts"), dict) else {}
    work_products: list[dict] = [
        _memo_catalog_row(
            session,
            artifact_id=f"analysis_session:{session_id}",
            artifact_type="analysis_session",
            title=f"Memo Analysis Session {session_id}",
            value=session,
            location=analysis_prefix,
            notes="Current Memo Studio session metadata and readiness state.",
        )
    ]

    artifact_specs = [
        ("strategic_risks", "risk_map", "Strategic Risk Map", "strategic_risks.yaml"),
        ("risk_priorities", "risk_priorities", "Risk Priority Harness", "risk_priorities.yaml"),
        ("thesis_spine", "thesis_spine", "Thesis Spine", "thesis_spine.yaml"),
        (
            "benchmark_dashboard",
            "benchmark_dashboard",
            "Private Benchmark Dashboard",
            "benchmark_dashboard.yaml",
        ),
        (
            "infographic_source_brief",
            "infographic_source_brief",
            "Infographic Source Brief",
            "infographic_source_brief.yaml",
        ),
        ("chart_specs", "chart_specs", "Chart And Infographic Plans", "chart_specs.yaml"),
        ("narrative_hooks", "narrative_hooks", "Narrative Hooks", "narrative_hooks.yaml"),
        ("memo_grader", "memo_grader", "Memo Grader Output", "memo_grader.yaml"),
        (
            "readiness_reviews",
            "readiness_reviews",
            "Evidence Readiness Review",
            "readiness_reviews.yaml",
        ),
    ]
    for key, artifact_type, title, filename in artifact_specs:
        value = artifacts.get(key)
        work_products.append(
            _memo_catalog_row(
                session,
                artifact_id=key,
                artifact_type=artifact_type,
                title=title,
                value=value,
                location=f"{analysis_prefix}{filename}",
                generated_file_paths=_memo_artifact_generated_file_paths(
                    company_id,
                    session_id,
                    filename,
                    value,
                    kind="yaml",
                ),
            )
        )

    tasks_value = artifacts.get("research_tasks")
    work_products.append(
        _memo_catalog_row(
            session,
            artifact_id="research_tasks",
            artifact_type="research_task_catalog",
            title="Research Task Catalog",
            value=tasks_value,
            location=f"{analysis_prefix}research_tasks.yaml",
            generated_file_paths=_memo_artifact_generated_file_paths(
                company_id,
                session_id,
                "research_tasks.yaml",
                tasks_value,
                kind="yaml",
            ),
        )
    )
    task_rows = (
        tasks_value.get("tasks")
        if isinstance(tasks_value, dict) and isinstance(tasks_value.get("tasks"), list)
        else []
    )
    for task in task_rows:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            continue
        work_products.append(
            _memo_catalog_row(
                session,
                artifact_id=f"research_task:{task_id}",
                artifact_type="research_task_result",
                title=str(task.get("title") or task_id),
                value=task,
                location=f"{analysis_prefix}research_tasks.yaml#{task_id}",
                notes=str(task.get("result_summary") or task.get("answer") or ""),
            )
        )

    memo_packet = artifacts.get("memo_packet")
    memo_packet_path = session_dir(company_id, session_id) / "memo_packet.md"
    work_products.append(
        _memo_catalog_row(
            session,
            artifact_id="memo_packet",
            artifact_type="memo_packet",
            title="Memo Packet",
            value=memo_packet,
            location=f"{analysis_prefix}memo_packet.md",
            export_paths=[f"{analysis_prefix}memo_packet.md"] if memo_packet else [],
            generated_file_paths=(
                [{"kind": "markdown", "path": memo_packet_path}]
                if memo_packet
                else []
            ),
        )
    )

    evidence_matrix_value, evidence_matrix_files = _memo_evidence_matrix_snapshot(
        company_id,
        session_id,
    )
    work_products.append(
        _memo_catalog_row(
            session,
            artifact_id="evidence_matrix:current",
            artifact_type="evidence_matrix",
            title="Evidence Matrix",
            value=evidence_matrix_value or tasks_value,
            location=f"{analysis_prefix}evidence_matrix.json",
            export_paths=(
                [f"{analysis_prefix}evidence_matrix.json"]
                if evidence_matrix_files
                else []
            ),
            generated_file_paths=evidence_matrix_files,
            notes="Derived from research-file summaries and Memo Studio research-task evidence.",
        )
    )

    lessons_path = memo_lessons_path(company_id)
    lessons_value = ""
    if lessons_path.exists():
        try:
            lessons_value = lessons_path.read_text(encoding="utf-8")
        except OSError:
            lessons_value = ""
    work_products.append(
        _memo_catalog_row(
            session,
            artifact_id="memo_lessons",
            artifact_type="memo_lessons",
            title="Memo Lessons File",
            value=lessons_value,
            location=f"data/serena_training/{company_id}/serena_memo_lessons.md",
            export_paths=(
                [f"data/serena_training/{company_id}/serena_memo_lessons.md"]
                if lessons_value
                else []
            ),
            generated_file_paths=(
                [{"kind": "markdown", "path": lessons_path}] if lessons_value else []
            ),
            notes="Derived learning loop for future Memo Studio runs.",
        )
    )

    for report in session.get("completed_memo_runs") or []:
        if not isinstance(report, dict):
            continue
        report_id = str(report.get("id") or report.get("run_id") or "").strip()
        if not report_id:
            continue
        memo_files = [
            str(row.get("path"))
            for row in report.get("memo_files") or []
            if isinstance(row, dict) and row.get("path")
        ]
        memo_file_paths = []
        for index, row in enumerate(report.get("memo_files") or [], start=1):
            if not isinstance(row, dict) or not row.get("path"):
                continue
            path = Path(str(row.get("path")))
            if not path.is_absolute():
                path = storage.DATA_DIR.parent / path
            memo_file_paths.append(
                {
                    "kind": row.get("language") or f"memo_{index}",
                    "path": path,
                }
            )
        work_products.append(
            _memo_catalog_row(
                session,
                artifact_id=f"generated_memo:{report_id}",
                artifact_type="generated_memo",
                title=f"Generated Memo {report.get('run_id') or report_id}",
                value=report,
                location=str(report.get("run_dir") or ""),
                export_paths=memo_files,
                status="published",
                created_at=report.get("created_at") or session.get("created_at"),
                updated_at=report.get("updated_at") or report.get("created_at"),
                generated_file_paths=memo_file_paths,
                notes="Completed final memo output linked back to Memo Studio.",
            )
        )

    source_boundaries = [
        {
            "id": "research_library",
            "label": "Research Library",
            "path": f"data/research/{company_id}/",
            "status": "included",
            "scope": "source_input",
            "notes": "Analyst-curated research files are available to Memo Studio.",
        },
        {
            "id": "memo_analysis_session",
            "label": "Memo Studio Session",
            "path": analysis_prefix,
            "status": "included",
            "scope": "derived_work",
            "notes": "Memo Studio artifacts, packet, and progress logs live here.",
        },
        {
            "id": "document_library_uploads",
            "label": "Document Library Uploads",
            "path": f"data/uploads/{company_id}/",
            "status": "excluded",
            "scope": "out_of_scope",
            "notes": "Legacy document-library uploads are not memo-analysis inputs.",
        },
        {
            "id": "stock_research",
            "label": "Stock Research Workspace",
            "path": "data/stock_research/",
            "status": "excluded",
            "scope": "separate_workflow",
            "notes": "Public-equity tracker artifacts are not imported implicitly.",
        },
    ]

    _sync_memo_catalog_versions(session, work_products)

    return {
        "company_id": company_id,
        "session_id": session_id,
        "generated_at": _now(),
        "work_products": work_products,
        "source_boundaries": source_boundaries,
    }


_MEMO_TOOL_ARTIFACT_IDS = {
    "strategic_risk_mapper": "strategic_risks",
    "priority_prompt_harness": "risk_priorities",
    "thesis_spine_builder": "thesis_spine",
    "private_benchmark_dashboard": "benchmark_dashboard",
    "infographic_source_brief": "infographic_source_brief",
    "chart_spec_builder": "chart_specs",
    "narrative_hooks": "narrative_hooks",
    "memo_grader": "memo_grader",
    "readiness_check": "readiness_reviews",
}


def _memo_job_metrics(value: Any) -> dict:
    if isinstance(value, dict) and isinstance(value.get("job_metrics"), dict):
        return value["job_metrics"]
    return {}


def _memo_duration_ms(value: Any) -> int | None:
    metrics = _memo_job_metrics(value)
    duration = metrics.get("duration_ms")
    try:
        return int(duration) if duration is not None else None
    except (TypeError, ValueError):
        return None


def _memo_tool_fallback_used(run: dict, artifact: Any) -> bool:
    if isinstance(artifact, dict) and artifact.get("generated_by") == "deterministic_fallback":
        return True
    return "fallback" in str(run.get("error") or "").lower()


def _memo_tool_preserved_artifact(artifact_id: str, run: dict, artifact: Any) -> str | None:
    if run.get("status") == "error" and _artifact_has_content(artifact):
        return artifact_id
    return None


def _memo_task_source_count(task: dict) -> int:
    sources_checked = task.get("sources_checked")
    if isinstance(sources_checked, list) and sources_checked:
        return len(sources_checked)
    selected_sources = task.get("selected_source_ids")
    if isinstance(selected_sources, list) and selected_sources:
        return len(selected_sources)
    return _memo_catalog_source_trace_count(task)


def _memo_task_evidence_coverage(task: dict) -> float:
    if task.get("status") != "done":
        return 0.0
    evidence_count = len(task.get("supporting_evidence") or []) + len(
        task.get("contradicting_evidence") or []
    )
    return 1.0 if evidence_count else 0.0


def _memo_run_ledger(session: dict) -> list[dict]:
    company_id = _safe_id(str(session.get("company_id") or ""))
    session_id = _safe_id(str(session.get("id") or ""))
    artifacts = session.get("artifacts") if isinstance(session.get("artifacts"), dict) else {}
    rows: list[dict] = []

    tool_runs = session.get("tool_runs") if isinstance(session.get("tool_runs"), dict) else {}
    for tool_name, run in sorted(tool_runs.items()):
        if not isinstance(run, dict):
            continue
        artifact_id = _MEMO_TOOL_ARTIFACT_IDS.get(str(tool_name), str(tool_name))
        artifact = artifacts.get(artifact_id)
        updated_at = run.get("last_run_at") or session.get("updated_at")
        rows.append(
            run_ledger.normalize_run_ledger_entry(
                {
                    "workspace": "memo_tools",
                    "ledger_id": f"memo_tools:{company_id}:{session_id}:tool:{tool_name}",
                    "job_kind": str(tool_name),
                    "artifact_id": artifact_id,
                    "company_id": company_id,
                    "session_id": session_id,
                    "run_id": run.get("run_job_id") or f"{session_id}/{tool_name}",
                    "status": run.get("status") or "unknown",
                    "created_at": updated_at,
                    "updated_at": updated_at,
                    "failure_reason": run.get("error") or "",
                    "fallback_used": _memo_tool_fallback_used(run, artifact),
                    "preserved_previous_artifact": _memo_tool_preserved_artifact(
                        artifact_id,
                        run,
                        artifact,
                    ),
                    "source_count": _memo_catalog_source_trace_count(artifact),
                    "evidence_coverage": 1.0 if _artifact_has_content(artifact) else 0.0,
                }
            )
        )

    research_tasks = artifacts.get("research_tasks")
    task_rows = (
        research_tasks.get("tasks")
        if isinstance(research_tasks, dict) and isinstance(research_tasks.get("tasks"), list)
        else []
    )
    for task in task_rows:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            continue
        status = str(task.get("status") or "not_started")
        fallback_used = (
            task.get("result_generated_by") == "deterministic_fallback"
            or bool(task.get("fallback"))
            or "fallback" in str(task.get("error") or "").lower()
        )
        preserved = (
            f"research_task:{task_id}"
            if status == "error" and bool(task.get("result_summary") or task.get("answer"))
            else None
        )
        rows.append(
            run_ledger.normalize_run_ledger_entry(
                {
                    "workspace": "memo_tools",
                    "ledger_id": f"memo_tools:{company_id}:{session_id}:research_task:{task_id}",
                    "job_kind": "research_task",
                    "artifact_id": f"research_task:{task_id}",
                    "company_id": company_id,
                    "session_id": session_id,
                    "run_id": task.get("run_job_id") or f"{session_id}/{task_id}",
                    "status": status,
                    "created_at": task.get("started_at") or task.get("last_run_at") or session.get("created_at"),
                    "updated_at": task.get("completed_at") or task.get("last_run_at") or session.get("updated_at"),
                    "duration_ms": _memo_duration_ms(task),
                    "source_count": _memo_task_source_count(task),
                    "evidence_coverage": _memo_task_evidence_coverage(task),
                    "failure_reason": task.get("error") or "",
                    "fallback_used": fallback_used,
                    "preserved_previous_artifact": preserved,
                    "cancellation_reason": (
                        task.get("error") if status == "cancelled" else ""
                    ),
                }
            )
        )

    for report in session.get("completed_memo_runs") or []:
        if not isinstance(report, dict):
            continue
        report_id = str(report.get("id") or report.get("run_id") or "").strip()
        if not report_id:
            continue
        rows.append(
            run_ledger.normalize_run_ledger_entry(
                {
                    "workspace": "memo_tools",
                    "ledger_id": f"memo_tools:{company_id}:{session_id}:generated_memo:{report_id}",
                    "job_kind": "final_memo_generation",
                    "artifact_id": f"generated_memo:{report_id}",
                    "company_id": company_id,
                    "session_id": session_id,
                    "run_id": report.get("run_id") or report_id,
                    "status": report.get("status") or "complete",
                    "created_at": report.get("created_at") or session.get("created_at"),
                    "updated_at": report.get("updated_at") or report.get("created_at") or session.get("updated_at"),
                    "source_count": len(report.get("memo_files") or []),
                    "evidence_coverage": 1.0,
                }
            )
        )

    return rows


def _has_unapproved_work(session: dict | None) -> bool:
    if not session or session.get("approved_for_memo"):
        return False
    artifacts = session.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    return any(
        name != "input_manifest" and _artifact_has_content(value)
        for name, value in artifacts.items()
    )


def _normalize_readiness_review_row(row: Any) -> dict | None:
    if not isinstance(row, dict):
        return None
    item_id = str(row.get("id") or "").strip()
    if not item_id:
        return None
    status = str(row.get("status") or "open").strip().lower()
    if status not in _READINESS_REVIEW_STATUSES:
        status = "open"
    return {
        "id": item_id,
        "status": status,
        "rationale": str(row.get("rationale") or "").strip(),
        "reviewed_at": row.get("reviewed_at"),
    }


def _normalize_readiness_reviews(value: Any) -> dict:
    if isinstance(value, dict):
        raw_items = value.get("items")
        updated_at = value.get("updated_at")
    elif isinstance(value, list):
        raw_items = value
        updated_at = None
    else:
        raw_items = []
        updated_at = None
    items_by_id: dict[str, dict] = {}
    for row in raw_items if isinstance(raw_items, list) else []:
        normalized = _normalize_readiness_review_row(row)
        if normalized is None:
            continue
        items_by_id[normalized["id"]] = normalized
    return {
        "updated_at": updated_at,
        "items": list(items_by_id.values()),
    }


def _readiness_review_map(session: dict) -> dict[str, dict]:
    artifacts = session.get("artifacts") or {}
    reviews = _normalize_readiness_reviews(artifacts.get("readiness_reviews"))
    return {
        str(row.get("id")): row
        for row in reviews.get("items") or []
        if isinstance(row, dict) and row.get("id")
    }


def _merge_readiness_reviews(current: Any, patch: Any) -> dict:
    current_rows = {
        row["id"]: row
        for row in _normalize_readiness_reviews(current).get("items", [])
    }
    incoming = _normalize_readiness_reviews(patch)
    now = _now()
    for row in incoming.get("items", []):
        existing = current_rows.get(row["id"], {})
        merged = {**existing, **row}
        if row.get("status") in {"reviewed", "waived"} and not row.get("reviewed_at"):
            merged["reviewed_at"] = now
        if row.get("status") == "open" and not row.get("reviewed_at"):
            merged["reviewed_at"] = now
        current_rows[row["id"]] = merged
    return {
        "updated_at": now,
        "items": sorted(current_rows.values(), key=lambda item: item.get("id") or ""),
    }


def _apply_readiness_reviews(
    additional: list[dict],
    reviews_by_id: dict[str, dict],
) -> list[dict]:
    decorated: list[dict] = []
    for area in additional:
        item = dict(area)
        review = reviews_by_id.get(str(item.get("id") or ""))
        if review:
            item["status"] = review.get("status") or "open"
            item["rationale"] = review.get("rationale") or ""
            item["reviewed_at"] = review.get("reviewed_at")
        else:
            item.setdefault("status", "open")
        decorated.append(item)
    return decorated


def _readiness_area_blocks_approval(area: dict) -> bool:
    status = str(area.get("status") or "open").strip().lower()
    if status == "open":
        return True
    if status in {"reviewed", "waived"}:
        return not bool(str(area.get("rationale") or "").strip())
    return True


def _decorate(session: dict) -> dict:
    session = dict(session)
    session.setdefault("tool_runs", {})
    session.setdefault("artifacts", {})
    session["tools"] = _decorated_tools(session)
    readiness, additional = _readiness(session)
    session["readiness"] = readiness
    session["additional_areas"] = additional
    session["completed_memo_runs"] = completed_memo_runs(str(session.get("company_id") or ""))
    session["has_unapproved_work"] = _has_unapproved_work(session)
    session["regular_memo_warning"] = (
        {
            "code": "memo_studio_unapproved_work",
            "analysis_session_id": session.get("id"),
            "message": (
                "Memo Studio has unapproved analysis work. Approve the "
                "analysis before generating a regular investment memo."
            ),
        }
        if session["has_unapproved_work"]
        else None
    )
    return session


def _decorated_tools(session: dict) -> list[dict]:
    runs = session.get("tool_runs") or {}
    tools = []
    for definition in TOOL_DEFINITIONS:
        run = runs.get(definition["name"]) or {}
        tools.append({
            **definition,
            "status": run.get("status") or "not_started",
            "last_run_at": run.get("last_run_at"),
            "summary": run.get("summary"),
            "error": run.get("error"),
        })
    return tools


def _readiness(session: dict) -> tuple[dict, list[dict]]:
    artifacts = session.get("artifacts") or {}
    risks = artifacts.get("strategic_risks") if isinstance(artifacts.get("strategic_risks"), dict) else {}
    priorities = artifacts.get("risk_priorities") if isinstance(artifacts.get("risk_priorities"), dict) else {}
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts.get("thesis_spine"), dict) else {}
    research_tasks = artifacts.get("research_tasks") if isinstance(artifacts.get("research_tasks"), dict) else {}
    task_rows = research_tasks.get("tasks") if isinstance(research_tasks, dict) else []
    task_rows = task_rows if isinstance(task_rows, list) else []
    completed_task_results = [
        task for task in task_rows
        if isinstance(task, dict)
        and task.get("status") == "done"
        and (task.get("answer") or task.get("result_summary"))
    ]
    task_evidence_count = sum(
        len(task.get("supporting_evidence") or [])
        + len(task.get("contradicting_evidence") or [])
        for task in completed_task_results
    )
    reviews_by_id = _readiness_review_map(session)
    sensitivity_rows = _thesis_sensitivity_rows(thesis)

    gates = [
        ("strategic_risks", "Strategic risks generated", bool(risks.get("risks"))),
        ("risk_priorities", "Serena prioritized risks", bool(priorities.get("priorities"))),
        ("thesis_spine", "Thesis spine drafted", bool(thesis.get("investment_highlights"))),
        ("highlights", "3-5 Investment Highlights drafted", 3 <= len(thesis.get("investment_highlights") or []) <= 5),
        ("memo_risks", "3-5 Investment Risks drafted", 3 <= len(thesis.get("investment_risks") or []) <= 5),
        ("risk_sensitivities", "Top 3 risk sensitivities selected", len(sensitivity_rows) >= 3),
        ("approved", "Final memo generation approved", bool(session.get("approved_for_memo"))),
    ]
    # Each open gate must name its concrete fix — "must be addressed" alone
    # is not actionable when the session is an empty draft and nothing has
    # been generated yet.
    gate_actions = {
        "strategic_risks": (
            "strategic_risk_mapper",
            'No risks exist yet. Run the Strategic Risk Mapper tool '
            '("Map risks") to generate them.',
        ),
        "risk_priorities": (
            "priority_prompt_harness",
            'Risks have not been prioritized. Run the Risk Prioritizer tool '
            '("Build source review queue") after the risk map.',
        ),
        "thesis_spine": (
            "thesis_spine_builder",
            'No thesis draft exists yet. Run the Thesis Spine tool '
            '("Draft thesis") to draft highlights, risks, and '
            "recommendation logic.",
        ),
        "highlights": (
            "thesis_spine_builder",
            "Edit the Thesis Spine until it carries 3-5 Investment "
            "Highlights.",
        ),
        "memo_risks": (
            "thesis_spine_builder",
            "Edit the Thesis Spine until it carries 3-5 Investment Risks.",
        ),
        "risk_sensitivities": (
            "thesis_spine_builder",
            "Select the top 3 risk / valuation sensitivities in the Thesis "
            "Spine.",
        ),
    }
    if completed_task_results:
        gates.extend([
            (
                "research_task_results",
                "Completed research-task results reviewed",
                all(task.get("status") == "done" for task in completed_task_results),
            ),
            (
                "research_task_evidence",
                "Research-task evidence captured",
                task_evidence_count > 0,
            ),
        ])
    completed = sum(1 for _, _, ok in gates if ok)
    gate_rows = [
        {"id": gid, "label": label, "status": "done" if ok else "missing"}
        for gid, label, ok in gates
    ]
    required_gate_blockers = [
        {
            "id": gid,
            "kind": "required_gate",
            "label": label,
            "severity": (
                "high"
                if gid in {"strategic_risks", "thesis_spine", "risk_sensitivities"}
                else "medium"
            ),
            "reason": (
                gate_actions.get(gid, (None, None))[1]
                or "Complete this required readiness gate before approval."
            ),
            "tool": gate_actions.get(gid, (None, None))[0],
        }
        for gid, label, ok in gates
        if gid != "approved" and not ok
    ]
    missing_required_gate_ids = {
        str(item.get("id"))
        for item in required_gate_blockers
        if item.get("id")
    }

    additional = [
        {
            "id": gid,
            "severity": "high" if gid in {"strategic_risks", "thesis_spine", "risk_sensitivities"} else "medium",
            "area": label,
            "why_it_matters": (
                (
                    gate_actions.get(gid, (None, ""))[1] + " "
                    if gate_actions.get(gid, (None, ""))[1]
                    else ""
                )
                + "This must be addressed or explicitly waived before final "
                "memo generation."
            ),
            "tool": gate_actions.get(gid, (None, None))[0],
            "status": "open",
        }
        for gid, label, ok in gates if gid != "approved" and not ok
    ]

    for task in completed_task_results:
        task_id = task.get("id") or "research-task"
        title = task.get("title") or task_id
        if not (task.get("supporting_evidence") or task.get("contradicting_evidence")):
            additional.append({
                "id": f"research-evidence-gap-{task_id}",
                "severity": "medium",
                "area": f"Research evidence incomplete: {title}",
                "why_it_matters": (
                    "Completed research-task results need source-backed "
                    "supporting or contradicting evidence before final memo generation."
                ),
                "status": "open",
            })
        evidence_limits = (
            task.get("remaining_evidence_limits")
            or task.get("open_questions")
            or []
        )
        for index, question in enumerate(evidence_limits, start=1):
            additional.append({
                "id": f"research-evidence-limit-{task_id}-{index}",
                "severity": "high",
                "area": f"Research evidence limit: {title}",
                "why_it_matters": str(question),
                "status": "open",
            })
    additional = _apply_readiness_reviews(additional, reviews_by_id)
    additional_blockers = [
        {
            "id": area.get("id"),
            "kind": "additional_area",
            "label": area.get("area") or area.get("id"),
            "severity": area.get("severity") or "medium",
            "reason": area.get("why_it_matters") or "Resolve or waive this area.",
        }
        for area in additional
        if area.get("id") not in missing_required_gate_ids
        and _readiness_area_blocks_approval(area)
    ]
    approval_blockers = [*required_gate_blockers, *additional_blockers]
    ready_for_approval = not approval_blockers
    readiness = {
        "score": completed,
        "total": len(gates),
        "pct": completed / len(gates) if gates else 0,
        "ready_for_approval": ready_for_approval,
        "approval_blockers": approval_blockers,
        "ready_for_memo": bool(session.get("approved_for_memo")) and ready_for_approval,
        "gates": gate_rows,
    }
    return readiness, additional
