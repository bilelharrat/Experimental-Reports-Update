"""Lightweight evaluation helpers for research outputs."""
from __future__ import annotations

from typing import Any


def evidence_coverage(output: dict) -> dict:
    supporting = output.get("supporting_evidence") or []
    contradicting = output.get("contradicting_evidence") or []
    traces = output.get("source_traces") or []
    chunks = output.get("source_chunks") or []
    return {
        "supporting_count": len(supporting) if isinstance(supporting, list) else 0,
        "contradicting_count": (
            len(contradicting) if isinstance(contradicting, list) else 0
        ),
        "source_trace_count": len(traces) if isinstance(traces, list) else 0,
        "source_chunk_count": len(chunks) if isinstance(chunks, list) else 0,
    }


def compare_output_shape(
    actual: dict,
    golden: dict,
    *,
    required_fields: list[str],
) -> dict:
    missing_fields = [
        field
        for field in required_fields
        if field not in actual
    ]
    type_mismatches: list[dict[str, str]] = []
    for field in required_fields:
        if field not in actual or field not in golden:
            continue
        expected = golden.get(field)
        observed = actual.get(field)
        if expected is not None and not isinstance(observed, type(expected)):
            type_mismatches.append({
                "field": field,
                "expected_type": type(expected).__name__,
                "actual_type": type(observed).__name__,
            })
    return {
        "ok": not missing_fields and not type_mismatches,
        "missing_fields": missing_fields,
        "type_mismatches": type_mismatches,
    }


def with_observability_defaults(output: dict, *, duration_ms: int | None = None) -> dict:
    observed = dict(output)
    observed.setdefault("analyst_review_score", None)
    metrics = dict(observed.get("job_metrics") or {})
    if duration_ms is not None:
        metrics["duration_ms"] = duration_ms
    metrics.update(evidence_coverage(observed))
    observed["job_metrics"] = metrics
    return observed
