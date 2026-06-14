"""Shared run-ledger normalization for workspace job history."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

RUN_LEDGER_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_run_ledger_entry(item: dict) -> dict:
    """Return the stable cross-workspace run-ledger row shape."""
    now = _now()
    workspace = _as_str(item.get("workspace"), "stock_research")
    job_kind = _as_str(item.get("job_kind"), "stock_tracker")
    run_id = _as_str(item.get("run_id") or item.get("job_id"), "")
    tracker_id = item.get("tracker_id")
    company_id = item.get("company_id")
    session_id = item.get("session_id")
    period_id = item.get("period_id")
    ledger_id = _as_str(
        item.get("ledger_id"),
        ":".join(
            part
            for part in [
                workspace,
                job_kind,
                _as_str(tracker_id),
                _as_str(company_id),
                _as_str(session_id),
                _as_str(period_id),
                run_id,
            ]
            if part
        ),
    )
    if not ledger_id:
        raise ValueError("Run ledger entry missing id")
    return {
        "schema_version": RUN_LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "workspace": workspace,
        "job_kind": job_kind,
        "artifact_id": item.get("artifact_id"),
        "tracker_id": tracker_id,
        "company_id": company_id,
        "session_id": session_id,
        "run_id": run_id,
        "period_id": period_id,
        "period_start": item.get("period_start"),
        "period_end": item.get("period_end"),
        "status": _as_str(item.get("status"), "unknown"),
        "created_at": item.get("created_at") or now,
        "updated_at": item.get("updated_at") or now,
        "duration_ms": item.get("duration_ms"),
        "token_usage": (
            item.get("token_usage") if isinstance(item.get("token_usage"), dict) else {}
        ),
        "estimated_cost_usd": _as_float(item.get("estimated_cost_usd"), 0.0) or 0.0,
        "source_count": max(0, _as_int(item.get("source_count"), 0)),
        "source_priority_mix": (
            item.get("source_priority_mix")
            if isinstance(item.get("source_priority_mix"), dict)
            else {}
        ),
        "source_quality": (
            item.get("source_quality") if isinstance(item.get("source_quality"), dict) else {}
        ),
        "evidence_coverage": _as_float(item.get("evidence_coverage"), 0.0) or 0.0,
        "contradiction_count": max(0, _as_int(item.get("contradiction_count"), 0)),
        "missing_source_count": max(0, _as_int(item.get("missing_source_count"), 0)),
        "reviewer_score": _as_float(item.get("reviewer_score"), None),
        "reviewer_scores": (
            item.get("reviewer_scores")
            if isinstance(item.get("reviewer_scores"), dict)
            else {}
        ),
        "failure_reason": _as_str(item.get("failure_reason") or item.get("error")),
        "fallback_used": bool(item.get("fallback_used")),
        "preserved_previous_artifact": item.get("preserved_previous_artifact")
        or item.get("preserved_previous_run_id"),
        "cancellation_reason": _as_str(item.get("cancellation_reason")),
    }
