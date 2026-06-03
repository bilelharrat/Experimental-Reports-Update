"""Persistent pre-memo analysis sessions for Serena's memo workflow.

The memo generator writes the final DOCX deliverables. This module owns the
work that should happen before that point: strategic risks, priorities,
research prompts, thesis spine, chart plans, narrative hooks, private-company
benchmarking, and readiness gates.

The first implementation is deterministic and local. It gives the UI and
storage model a stable contract; individual tools can later be replaced with
Claude-backed jobs without changing the dashboard shape.
"""
from __future__ import annotations

import copy
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import claude_runner, job_progress, research_store, storage

ANALYSIS_ROOT = storage.DATA_DIR / "serena_analysis"
SESSION_VERSION = 1

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()

TOOL_DEFINITIONS: list[dict[str, str]] = [
    {
        "name": "strategic_risk_mapper",
        "label": "Strategic Risk Mapper",
        "description": "Generate sharp decision-grade strategic risks.",
    },
    {
        "name": "priority_prompt_harness",
        "label": "Priority + Prompt Harness",
        "description": "Rank risks and turn them into targeted research prompts.",
    },
    {
        "name": "thesis_spine_builder",
        "label": "Thesis Spine Builder",
        "description": "Draft the 3-5 highlights, 3-5 risks, recommendation logic, and top gates.",
    },
    {
        "name": "chart_spec_builder",
        "label": "Chart Spec Builder",
        "description": "Plan the charts and tables needed before writing.",
    },
    {
        "name": "narrative_hooks",
        "label": "Opening / Ending Punch Tool",
        "description": "Draft punchier opening and ending options from the thesis spine.",
    },
    {
        "name": "private_benchmark_dashboard",
        "label": "Private Benchmark Dashboard",
        "description": "Identify mature public comps and underwriting benchmarks.",
    },
    {
        "name": "memo_grader",
        "label": "Memo Grader",
        "description": "Grade completed memos and record lessons for the next run.",
    },
    {
        "name": "readiness_check",
        "label": "Memo Readiness Gate",
        "description": "Check whether analysis is strong enough for final memo generation.",
    },
]

_TOOL_NAMES = {t["name"] for t in TOOL_DEFINITIONS}
_TASK_STATUSES = {"not_started", "running", "done", "error", "skipped"}
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
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]", "", (value or "").lower())
    if not cleaned:
        raise ValueError("Invalid company id")
    return cleaned


def _company_dir(company_id: str) -> Path:
    return ANALYSIS_ROOT / _safe_id(company_id)


def session_dir(company_id: str, session_id: str) -> Path:
    return _company_dir(company_id) / _safe_id(session_id)


def session_path(company_id: str, session_id: str) -> Path:
    return session_dir(company_id, session_id) / "session.yaml"


def research_task_progress_path(company_id: str, session_id: str, task_id: str) -> Path:
    safe_task_id = str(task_id or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", safe_task_id):
        raise ValueError("Invalid research task id")
    return session_dir(company_id, session_id) / "logs" / f"{safe_task_id}.progress.jsonl"


def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else default


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
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
            return _decorate(session)
        if not create:
            return None
        session = _new_session(company)
        _write_session(session)
        return _decorate(session)


def get_session(company_id: str, session_id: str) -> dict | None:
    with _LOCK:
        session = _load_session(session_path(company_id, session_id))
        return _decorate(session) if session else None


def has_unapproved_work(company_id: str) -> bool:
    """Return whether a company has draft Memo Studio work not approved yet."""
    with _LOCK:
        session = get_current_session(company_id, create=False)
        return _has_unapproved_work(session) if session else False


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
            artifacts["risk_priorities"] = {
                **(current if isinstance(current, dict) else {}),
                **(patch if isinstance(patch, dict) else {}),
                "updated_at": _now(),
                "priorities": _normalize_priorities(risks, priorities),
            }
            _refresh_research_tasks(company, artifacts)
        elif isinstance(current, dict) and isinstance(patch, dict):
            artifacts[artifact_name] = {**current, **patch}
        else:
            artifacts[artifact_name] = patch
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
        task["result_summary"] = _deterministic_research_result(company, task, risk)
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
        risk = _risks_by_id(artifacts).get(str(task.get("risk_id") or ""))
        now = _now()
        session_id = str(session["id"])
        safe_task_id = str(task.get("id") or task_id)
        job_id = f"{company_id}/{session_id}/{safe_task_id}"
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

    threading.Thread(
        target=_run_research_task_job,
        args=(company_id, session_id, safe_task_id, company_snapshot, task_snapshot, risk_snapshot),
        name=f"serena-research-task-{company_id}-{safe_task_id}",
        daemon=True,
    ).start()
    return decorated


def _run_research_task_job(
    company_id: str,
    session_id: str,
    task_id: str,
    company: dict,
    task: dict,
    risk: dict | None,
) -> None:
    progress = job_progress.ProgressLog(
        research_task_progress_path(company_id, session_id, task_id)
    )
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
    )
    progress.emit(
        "stage",
        stage="starting",
        message="Starting selected research prompt",
        task_id=task_id,
    )

    result: dict | None = None
    error: str | None = None
    try:
        result, error = claude_runner.run_serena_research_task(
            company=company,
            task=task,
            risk=risk,
            research_dir=research_store.RESEARCH_ROOT / company_id,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("serena research task crashed")
        error = f"{type(exc).__name__}: {exc}"

    if result and not error:
        summary = str(result.get("result_summary") or "").strip()
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
                "result_summary": summary,
                "result_basis": _research_result_basis(task, risk) + ["claude_code"],
                "result_generated_by": "claude_code",
                "result_updated_at": now,
                "result_payload": result,
            },
        )
        progress.emit("done", task_id=task_id, result_summary=summary)
        return

    message = error or "Claude returned no result"
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
        return

    progress.emit(
        "stage",
        stage="fallback",
        message="Using deterministic fallback result",
        task_id=task_id,
    )
    fallback = _deterministic_research_result(company, task, risk)
    _finish_research_task_job(
        company_id,
        session_id,
        task_id,
        {
            "status": "done",
            "completed_at": now,
            "last_run_at": now,
            "error": f"Claude research fallback: {message}",
            "result_summary": fallback,
            "result_basis": _research_result_basis(task, risk),
            "result_generated_by": "deterministic_fallback",
            "result_updated_at": now,
            "result_payload": {
                "fallback": True,
                "claude_error": message,
            },
        },
    )
    progress.emit(
        "done",
        task_id=task_id,
        fallback=True,
        error=message,
        result_summary=fallback,
    )


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
        _touch_research_tasks(session)
        _refresh_memo_packet(session)
        _write_session(session)


def approve(company_id: str) -> dict:
    with _LOCK:
        session = get_current_session(company_id, create=True)
        if session is None:
            raise ValueError(f"Unknown company: {company_id}")
        session = _strip_decorations(session)
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
        }
        return f"Generated {len(risks)} strategic risks."
    if tool_name == "priority_prompt_harness":
        risks = _ensure_risks(company, artifacts)
        priorities = [
            {
                "risk_id": risk["id"],
                "rank": i + 1,
                "selected": i < 3,
                "rationale": "Default priority based on decision impact and memo centrality.",
            }
            for i, risk in enumerate(risks)
        ]
        artifacts["risk_priorities"] = {
            "updated_at": _now(),
            "priorities": priorities,
        }
        _refresh_research_tasks(company, artifacts)
        tasks = artifacts["research_tasks"]["tasks"]
        return f"Ranked {len(priorities)} risks and created {len(tasks)} research tasks."
    if tool_name == "thesis_spine_builder":
        risks = _ensure_risks(company, artifacts)
        artifacts["thesis_spine"] = _thesis_spine(company, risks)
        return "Drafted investment highlights, risks, recommendation logic, and top gates."
    if tool_name == "chart_spec_builder":
        artifacts["chart_specs"] = _chart_specs(company)
        return "Drafted chart and table plan."
    if tool_name == "narrative_hooks":
        artifacts["narrative_hooks"] = _narrative_hooks(company, artifacts)
        return "Drafted opening and ending options."
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
                "Missing diligence",
            ],
            "next_step": "Run this after a completed memo exists.",
        }
        return "Memo grader is ready; no completed memo selected yet."
    if tool_name == "readiness_check":
        artifacts["readiness_reviewed_at"] = _now()
        return "Updated memo readiness gates."
    raise ValueError(f"Unhandled tool: {tool_name}")


def _ensure_risks(company: dict, artifacts: dict) -> list[dict]:
    risk_artifact = artifacts.get("strategic_risks")
    risks = risk_artifact.get("risks") if isinstance(risk_artifact, dict) else None
    if isinstance(risks, list) and risks:
        return risks
    risks = _strategic_risks(company)
    artifacts["strategic_risks"] = {
        "generated_at": _now(),
        "risks": risks,
        "source_basis": _source_basis(company),
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
    for _, _, row in provided:
        item = {
            "risk_id": str(row.get("risk_id")),
            "rank": len(normalized) + 1,
            "selected": _coerce_selected(row.get("selected")),
        }
        if row.get("rationale") is not None:
            item["rationale"] = str(row.get("rationale") or "")
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


def _apply_research_task_patch(task: dict, patch: dict) -> None:
    if "status" in patch:
        status = str(patch.get("status") or "").strip()
        if status not in _TASK_STATUSES:
            raise ValueError("Invalid research task status")
        task["status"] = status
    if "result_summary" in patch:
        summary = str(patch.get("result_summary") or "").strip()
        task["result_summary"] = summary or None
        task["result_updated_at"] = _now() if summary else None
    if "error" in patch:
        error = str(patch.get("error") or "").strip()
        task["error"] = error or None
    if "completed_at" in patch:
        task["completed_at"] = str(patch.get("completed_at") or "").strip() or None
    if "started_at" in patch:
        task["started_at"] = str(patch.get("started_at") or "").strip() or None


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
        f"{source_type}. Decision question: {decision_question}"
    )


def _company_text(company: dict) -> str:
    parts = [
        company.get("name"),
        company.get("description"),
        company.get("sector"),
        company.get("industry"),
    ]
    parts += [p.get("name") for p in company.get("products") or [] if isinstance(p, dict)]
    parts += list(company.get("competitors") or [])
    return " ".join(str(p or "") for p in parts).lower()


def _source_basis(company: dict) -> dict:
    return {
        "company_record_fields": [
            k for k in (
                "description", "sector", "industry", "products",
                "competitors", "latest_funding", "total_funding_usd",
                "notable_contracts", "recent_news",
            )
            if company.get(k)
        ],
        "research_file_count": len(research_store.list_files(str(company.get("id")))),
    }


def _strategic_risks(company: dict) -> list[dict]:
    name = company.get("name") or company.get("id") or "the company"
    sector = company.get("sector") or company.get("industry") or "the category"
    text = _company_text(company)
    risks: list[dict[str, Any]] = []

    def add(title: str, decision_question: str, why: str, evidence: list[str],
            sources: list[str], section: str = "Investment Risk") -> None:
        risks.append({
            "id": f"risk-{len(risks) + 1}",
            "title": title,
            "decision_question": decision_question,
            "why_it_matters": why,
            "bull_case_answer": (
                f"{name} has evidence that this risk is manageable and can "
                "become an investment advantage."
            ),
            "bear_case_answer": (
                "If the answer is weak, the investment case depends on a "
                "future state that is not yet underwritten."
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
        "Budget-owner ambiguity and weak procurement evidence often break late-stage software underwriting.",
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
            "pre-mortem",
            "reverse IC case",
            "top three gating questions",
            "missingness penalties",
        ],
        ["all analysis artifacts", "partner notes", "independent negative searches"],
    )

    return risks[:8]


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
            "result_summary": None,
        })
    return tasks


def _thesis_spine(company: dict, risks: list[dict]) -> dict:
    name = company.get("name") or "the company"
    sector = company.get("sector") or company.get("industry") or "its category"
    desc = company.get("description") or f"{name} operates in {sector}."
    top = risks[:3]
    highlights = [
        {
            "id": "highlight-1",
            "claim": f"Present-state wedge in {sector}",
            "detail": desc,
            "state": "present_state",
            "source_trace": ["company_record"],
            "needs_stronger_evidence": True,
        },
        {
            "id": "highlight-2",
            "claim": "Upside depends on proving the highest-priority strategic risk is manageable",
            "detail": top[0]["decision_question"] if top else "Strategic risk still needs mapping.",
            "state": "upside_state",
            "source_trace": ["strategic_risks"],
            "needs_stronger_evidence": True,
        },
        {
            "id": "highlight-3",
            "claim": "BSH can underwrite the deal if evidence supports deployment depth and revenue quality",
            "detail": "The current analysis should now focus on independent proof rather than narrative completeness.",
            "state": "upside_state",
            "source_trace": ["strategic_risks", "chart_specs"],
            "needs_stronger_evidence": True,
        },
    ]
    risks_out = [
        {
            "id": f"memo-risk-{i}",
            "claim": r["title"],
            "detail": r["why_it_matters"],
            "source_trace": ["strategic_risks"],
            "needs_stronger_evidence": True,
        }
        for i, r in enumerate(top, start=1)
    ]
    gates = [
        {
            "id": f"gate-{i}",
            "question": r["decision_question"],
            "why_it_matters": r["why_it_matters"],
            "evidence_needed": r.get("evidence_needed") or [],
        }
        for i, r in enumerate(top, start=1)
    ]
    return {
        "updated_at": _now(),
        "approved": False,
        "investment_highlights": highlights[:5],
        "investment_risks": risks_out[:5],
        "recommendation_logic": (
            "Need More Information until the top strategic risks have "
            "independent support and the benchmark dashboard is complete."
        ),
        "top_gating_questions": gates[:3],
        "bull_case_must_be_true": [
            "Deployment depth is repeatable beyond early adopters.",
            "Revenue quality supports the proposed valuation.",
            "Competitive compression is manageable."
        ],
        "pass_triggers": [
            "No independent support for deployment depth.",
            "Valuation depends on stale or inappropriate comps.",
            "Growth is mainly pricing, services, or acquisition-driven without durable expansion."
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


def _narrative_hooks(company: dict, artifacts: dict) -> dict:
    name = company.get("name") or "the company"
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts, dict) else None
    gates = thesis.get("top_gating_questions") if isinstance(thesis, dict) else []
    main_gate = gates[0]["question"] if gates else "whether the current traction is deep enough to underwrite"
    openings = [
        {
            "id": "opening-1",
            "text": f"The memo should not start with what {name} claims to be; it should start with {main_gate.lower()}.",
            "tone": "falsification_first",
        },
        {
            "id": "opening-2",
            "text": f"{name} is interesting only if the strongest version of the bull case survives the deployment and valuation tests.",
            "tone": "direct",
        },
        {
            "id": "opening-3",
            "text": f"BSH's decision on {name} turns less on category excitement than on proof of depth, economics, and durability.",
            "tone": "ic_ready",
        },
    ]
    endings = [
        {
            "id": "ending-1",
            "text": "The recommendation should remain conditional until the top three gating questions are answered with independent evidence.",
            "tone": "conditional",
        },
        {
            "id": "ending-2",
            "text": "If the missing evidence arrives, this can become a focused yes; if it does not, the right answer is to pass without stretching the thesis.",
            "tone": "crisp",
        },
        {
            "id": "ending-3",
            "text": "The next diligence step is not more narrative. It is proof that the investment highlights are already true or realistically attainable.",
            "tone": "discipline",
        },
    ]
    return {
        "updated_at": _now(),
        "openings": openings,
        "endings": endings,
        "selected_opening_id": openings[0]["id"],
        "selected_ending_id": endings[0]["id"],
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
            "sell_side_theme": "To be filled from filings, earnings transcripts, and sell-side notes.",
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
    }


def _refresh_memo_packet(session: dict) -> None:
    artifacts = session.setdefault("artifacts", {})
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts.get("thesis_spine"), dict) else {}
    risks = artifacts.get("strategic_risks") if isinstance(artifacts.get("strategic_risks"), dict) else {}
    research_tasks = artifacts.get("research_tasks") if isinstance(artifacts.get("research_tasks"), dict) else {}
    chart_specs = artifacts.get("chart_specs") if isinstance(artifacts.get("chart_specs"), dict) else {}
    hooks = artifacts.get("narrative_hooks") if isinstance(artifacts.get("narrative_hooks"), dict) else {}

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

    lines = [
        f"# Serena Memo Analysis Packet — {session.get('company_name')}",
        "",
        f"- analysis_session_id: {session.get('id')}",
        f"- status: {session.get('status')}",
        f"- approved_for_memo: {bool(session.get('approved_for_memo'))}",
        "",
        "## Investment Highlights",
    ]
    for item in thesis.get("investment_highlights") or []:
        lines.append(f"- **{item.get('claim')}** — {item.get('detail')}")
    lines += ["", "## Investment Risks"]
    for item in thesis.get("investment_risks") or []:
        lines.append(f"- **{item.get('claim')}** — {item.get('detail')}")
    lines += ["", "## Top Gating Questions"]
    for item in thesis.get("top_gating_questions") or []:
        lines.append(f"- {item.get('question')}")
    lines += ["", "## Strategic Risks"]
    for item in risks.get("risks") or []:
        lines.append(f"- **{item.get('title')}** — {item.get('decision_question')}")
    if research_tasks.get("tasks"):
        lines += ["", "## Research Task Results"]
        for item in research_tasks.get("tasks") or []:
            lines.append(
                f"- **{item.get('title')}** [{item.get('status') or 'not_started'}]"
            )
            if item.get("result_summary"):
                lines.append(f"  - Result: {item.get('result_summary')}")
            elif item.get("prompt"):
                lines.append(f"  - Prompt: {item.get('prompt')}")
    lines += ["", "## Chart Specs"]
    for item in chart_specs.get("specs") or []:
        if item.get("include_in_final_memo"):
            lines.append(f"- {item.get('title')}: {item.get('takeaway')}")
    if selected_opening or selected_ending:
        lines += ["", "## Selected Narrative Hooks"]
        if selected_opening:
            lines.append(f"- Opening: {selected_opening.get('text')}")
        if selected_ending:
            lines.append(f"- Ending: {selected_ending.get('text')}")
    artifacts["memo_packet"] = "\n".join(lines).strip() + "\n"


def _strip_decorations(session: dict) -> dict:
    return {
        k: v for k, v in session.items()
        if k not in {
            "tools",
            "readiness",
            "additional_areas",
            "has_unapproved_work",
            "regular_memo_warning",
        }
    }


def _artifact_has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return value is not None


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


def _decorate(session: dict) -> dict:
    session = dict(session)
    session.setdefault("tool_runs", {})
    session.setdefault("artifacts", {})
    session["tools"] = _decorated_tools(session)
    readiness, additional = _readiness(session)
    session["readiness"] = readiness
    session["additional_areas"] = additional
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
    charts = artifacts.get("chart_specs") if isinstance(artifacts.get("chart_specs"), dict) else {}
    benchmark = artifacts.get("benchmark_dashboard") if isinstance(artifacts.get("benchmark_dashboard"), dict) else {}

    gates = [
        ("strategic_risks", "Strategic risks generated", bool(risks.get("risks"))),
        ("risk_priorities", "Serena prioritized risks", bool(priorities.get("priorities"))),
        ("thesis_spine", "Thesis spine drafted", bool(thesis.get("investment_highlights"))),
        ("highlights", "3-5 Investment Highlights drafted", 3 <= len(thesis.get("investment_highlights") or []) <= 5),
        ("memo_risks", "3-5 Investment Risks drafted", 3 <= len(thesis.get("investment_risks") or []) <= 5),
        ("gating_questions", "Top 3 gating questions selected", len(thesis.get("top_gating_questions") or []) >= 3),
        ("chart_specs", "Chart/table plan reviewed", bool(charts.get("specs"))),
        ("benchmark", "Benchmark dashboard reviewed", bool(benchmark.get("public_comps"))),
        ("approved", "Final memo generation approved", bool(session.get("approved_for_memo"))),
    ]
    completed = sum(1 for _, _, ok in gates if ok)
    readiness = {
        "score": completed,
        "total": len(gates),
        "pct": completed / len(gates) if gates else 0,
        "ready_for_memo": completed == len(gates),
        "gates": [
            {"id": gid, "label": label, "status": "done" if ok else "missing"}
            for gid, label, ok in gates
        ],
    }
    additional = [
        {
            "id": gid,
            "severity": "high" if gid in {"strategic_risks", "thesis_spine", "gating_questions"} else "medium",
            "area": label,
            "why_it_matters": "This must be addressed or explicitly waived before final memo generation.",
            "status": "open",
        }
        for gid, label, ok in gates if not ok
    ]

    for spec in charts.get("specs") or []:
        if spec.get("data_availability") == "missing":
            additional.append({
                "id": f"chart-gap-{spec.get('id')}",
                "severity": "medium",
                "area": f"Chart data incomplete: {spec.get('title')}",
                "why_it_matters": spec.get("takeaway"),
                "status": "open",
            })
    return readiness, additional
