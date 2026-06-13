from __future__ import annotations

from server import research_eval


def test_quick_summary_golden_shape_and_evidence_coverage():
    golden = {
        "summary_en": "ARR reached $120M.",
        "source_traces": [],
        "source_chunks": [],
        "job_metrics": {},
        "analyst_review_score": None,
    }
    actual = research_eval.with_observability_defaults({
        "summary_en": "ARR reached $120M.",
        "source_traces": [{"excerpt": "ARR reached $120M"}],
        "source_chunks": [{"text": "ARR reached $120M"}],
    })

    result = research_eval.compare_output_shape(
        actual,
        golden,
        required_fields=[
            "summary_en",
            "source_traces",
            "source_chunks",
            "job_metrics",
            "analyst_review_score",
        ],
    )

    assert result["ok"] is True
    assert actual["job_metrics"]["source_trace_count"] == 1
    assert actual["job_metrics"]["source_chunk_count"] == 1


def test_external_research_golden_shape_and_evidence_coverage():
    golden = {
        "summary": "Customer deployments expanded.",
        "key_points": [],
        "source_traces": [],
        "source_chunks": [],
        "job_metrics": {},
        "analyst_review_score": None,
    }
    actual = research_eval.with_observability_defaults({
        "summary": "Customer deployments expanded.",
        "key_points": ["Deployment depth"],
        "source_traces": [{"excerpt": "expanded deployments"}],
        "source_chunks": [{"text": "expanded deployments"}],
    })

    result = research_eval.compare_output_shape(
        actual,
        golden,
        required_fields=[
            "summary",
            "key_points",
            "source_traces",
            "source_chunks",
            "job_metrics",
            "analyst_review_score",
        ],
    )

    assert result["ok"] is True
    assert actual["job_metrics"]["source_trace_count"] == 1


def test_memo_research_task_golden_shape_and_evidence_coverage():
    golden = {
        "answer": "Deployment depth remains unproven.",
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "open_questions": [],
        "sources_checked": [],
        "confidence": "medium",
        "job_metrics": {},
        "analyst_review_score": None,
    }
    actual = research_eval.with_observability_defaults({
        "answer": "Deployment depth remains unproven.",
        "supporting_evidence": [{"excerpt": "Only pilots confirmed."}],
        "contradicting_evidence": [],
        "open_questions": ["Need production count."],
        "sources_checked": [{"filename": "call.txt"}],
        "confidence": "medium",
    })

    result = research_eval.compare_output_shape(
        actual,
        golden,
        required_fields=[
            "answer",
            "supporting_evidence",
            "contradicting_evidence",
            "open_questions",
            "sources_checked",
            "confidence",
            "job_metrics",
            "analyst_review_score",
        ],
    )

    assert result["ok"] is True
    assert actual["job_metrics"]["supporting_count"] == 1
    assert actual["job_metrics"]["contradicting_count"] == 0
