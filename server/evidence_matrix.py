"""Build per-company evidence matrices from research outputs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import research_store, serena_analysis, storage

_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip() if limit else text


def _confidence(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in _CONFIDENCE_RANK else "medium"


def _max_confidence(*values: str | None) -> str:
    best = "low"
    for value in values:
        confidence = _confidence(value)
        if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[best]:
            best = confidence
    return best


def _new_row(claim: str) -> dict:
    return {
        "claim": claim,
        "status": "missing",
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "missing_evidence": [],
        "confidence": "low",
        "source_coverage": {
            "source_count": 0,
            "supporting_count": 0,
            "contradicting_count": 0,
            "missing_count": 0,
        },
    }


def _evidence_key(evidence: dict) -> tuple:
    return (
        evidence.get("file_id"),
        evidence.get("filename"),
        evidence.get("locator"),
        evidence.get("excerpt"),
    )


def _add_evidence(
    rows: dict[str, dict],
    seen: set[tuple],
    *,
    claim: str,
    bucket: str,
    evidence: dict,
) -> None:
    claim = _clean(claim, limit=600)
    if not claim:
        return
    row = rows.setdefault(claim, _new_row(claim))
    if bucket == "missing_evidence":
        text = _clean(evidence.get("question") or evidence.get("excerpt"), limit=600)
        if text and text not in row[bucket]:
            row[bucket].append(text)
        return
    excerpt = _clean(evidence.get("excerpt"), limit=900)
    if not excerpt:
        return
    normalized = {
        "source_kind": evidence.get("source_kind"),
        "file_id": evidence.get("file_id"),
        "filename": evidence.get("filename"),
        "task_id": evidence.get("task_id"),
        "task_title": evidence.get("task_title"),
        "locator": evidence.get("locator"),
        "excerpt": excerpt,
        "confidence": _confidence(evidence.get("confidence")),
    }
    key = (bucket, *_evidence_key(normalized))
    if key in seen:
        return
    seen.add(key)
    row[bucket].append(normalized)


def _finalize_row(row: dict) -> None:
    supporting = row.get("supporting_evidence") or []
    contradicting = row.get("contradicting_evidence") or []
    missing = row.get("missing_evidence") or []
    if supporting and contradicting:
        row["status"] = "mixed"
    elif supporting:
        row["status"] = "supported" if not missing else "partial"
    elif contradicting:
        row["status"] = "contradicted"
    else:
        row["status"] = "missing"
    row["confidence"] = _max_confidence(
        *[item.get("confidence") for item in supporting],
        *[item.get("confidence") for item in contradicting],
        "low" if missing else None,
    )
    source_keys = {
        (item.get("source_kind"), item.get("file_id"), item.get("filename"))
        for item in [*supporting, *contradicting]
    }
    row["source_coverage"] = {
        "source_count": len(source_keys),
        "supporting_count": len(supporting),
        "contradicting_count": len(contradicting),
        "missing_count": len(missing),
    }


def build_company_evidence_matrix(company_id: str) -> dict:
    """Return the current evidence matrix for a company.

    The matrix is rebuilt from durable outputs on each read, so replaced
    summaries or rerun task results do not leave stale duplicate evidence.
    """
    company = storage.get_company(company_id) or {"id": company_id}
    rows: dict[str, dict] = {}
    seen: set[tuple] = set()

    for record in research_store.list_files(company_id):
        summary = record.get("quick_summary")
        traces = (
            summary.get("source_traces")
            if isinstance(summary, dict)
            else record.get("source_traces")
        )
        for trace in traces or []:
            if not isinstance(trace, dict):
                continue
            claim = trace.get("claim") or trace.get("excerpt")
            _add_evidence(
                rows,
                seen,
                claim=claim,
                bucket="supporting_evidence",
                evidence={
                    **trace,
                    "source_kind": "company_quick_summary",
                    "file_id": trace.get("file_id") or record.get("id"),
                    "filename": trace.get("filename") or record.get("filename"),
                },
            )

    try:
        session = serena_analysis.get_current_session(company_id, create=False)
    except Exception:
        session = None
    tasks = (
        session.get("artifacts", {})
        .get("research_tasks", {})
        .get("tasks", [])
        if isinstance(session, dict)
        else []
    )
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        claim = task.get("answer") or task.get("result_summary") or task.get("title")
        for evidence in task.get("supporting_evidence") or []:
            if isinstance(evidence, dict):
                _add_evidence(
                    rows,
                    seen,
                    claim=claim,
                    bucket="supporting_evidence",
                    evidence={
                        **evidence,
                        "source_kind": "memo_research_task",
                        "task_id": task.get("id"),
                        "task_title": task.get("title"),
                    },
                )
        for evidence in task.get("contradicting_evidence") or []:
            if isinstance(evidence, dict):
                _add_evidence(
                    rows,
                    seen,
                    claim=claim,
                    bucket="contradicting_evidence",
                    evidence={
                        **evidence,
                        "source_kind": "memo_research_task",
                        "task_id": task.get("id"),
                        "task_title": task.get("title"),
                    },
                )
        for question in task.get("open_questions") or []:
            _add_evidence(
                rows,
                seen,
                claim=claim,
                bucket="missing_evidence",
                evidence={"question": question},
            )

    matrix = list(rows.values())
    for row in matrix:
        _finalize_row(row)
    matrix.sort(
        key=lambda row: (
            {"mixed": 0, "contradicted": 1, "partial": 2, "missing": 3, "supported": 4}.get(
                row.get("status"),
                9,
            ),
            row.get("claim") or "",
        )
    )
    return {
        "company_id": company_id,
        "company_name": company.get("name") or company_id,
        "generated_at": _now(),
        "claims": matrix,
        "claim_count": len(matrix),
    }
