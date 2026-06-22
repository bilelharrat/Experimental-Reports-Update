from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import hypothesis_store, research_pages, stock_research
from server.main import app


@pytest.fixture
def tmp_stock_root(monkeypatch, tmp_path):
    root = tmp_path / "stock_research"
    monkeypatch.setattr(stock_research, "STOCK_RESEARCH_ROOT", root)
    return root


@pytest.fixture
def client(tmp_stock_root):
    return TestClient(app)


def _write_aggregate(signals: list[dict], *, period_id: str = "2026-06-08_to_2026-06-14") -> dict:
    aggregate = stock_research.coerce_weekly_aggregate(
        {
            "generated_at": "2026-06-14T12:00:00+00:00",
            "included_tracker_run_ids": ["nvidia:run-1"],
            "modules": {
                "macro": [],
                "industry": [],
                "company": [],
                "cross_tracker": [],
                "watchlist": [],
            },
            "ranked_signals": signals,
            "deduped_claims": [],
            "contradictions": [],
            "missing_source_warnings": [],
            "event_calendar": [],
            "markdown": "# Weekly",
        },
        period_id=period_id,
        period_start=period_id.split("_to_")[0],
        period_end=period_id.split("_to_")[1],
    )
    stock_research._write_weekly_aggregate(aggregate)
    return aggregate


def test_market_pulse_flags_missing_and_weak_source_signals(tmp_stock_root):
    stock_research.seed_tracker_registry()
    weak = stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "Desk note",
            "body": "A weak note-only source.",
            "priority": "unsourced_note",
        }
    )
    weak_source_id = weak["source"]["id"]
    _write_aggregate(
        [
            {
                "id": "sig-missing",
                "source_tracker_id": "nvidia",
                "tracker_run_id": "run-1",
                "ticker": "NVDA",
                "observation": "Missing trace claim.",
                "direction": "bullish",
                "confidence": 0.7,
                "source_traces": [],
            },
            {
                "id": "sig-weak",
                "source_tracker_id": "nvidia",
                "tracker_run_id": "run-1",
                "ticker": "NVDA",
                "observation": "Weak source claim.",
                "direction": "watch",
                "confidence": 0.6,
                "source_traces": [
                    {
                        "source_id": weak_source_id,
                        "source_title": "Desk note",
                        "locator": "note",
                        "excerpt": "A weak note-only source.",
                    }
                ],
            },
        ]
    )

    payload = research_pages.market_pulse_page()
    issue_types = {issue["type"] for issue in payload["doctor_issues"]}

    assert payload["page_id"] == "market_pulse"
    assert payload["summary"]["signal_count"] == 2
    assert "market_pulse_signal_missing_source_trace" in issue_types
    assert "market_pulse_weak_source_only_signal" in issue_types
    assert payload["sections"]["theme_heatmap"]


def test_evidence_matrix_global_uses_signal_claims_and_stable_issues(tmp_stock_root):
    stock_research.seed_tracker_registry()
    _write_aggregate(
        [
            {
                "id": "sig-unsupported",
                "source_tracker_id": "nvidia",
                "tracker_run_id": "run-1",
                "ticker": "NVDA",
                "observation": "Unsupported AI demand claim.",
                "direction": "bullish",
                "source_traces": [],
            }
        ]
    )

    payload = research_pages.evidence_matrix_page()
    issue_types = {issue["type"] for issue in payload["doctor_issues"]}

    assert payload["page_id"] == "evidence_matrix"
    assert payload["summary"]["claim_count"] == 1
    assert payload["sections"]["claim_table"][0]["status"] == "unsupported"
    assert "evidence_claim_missing_source_trace" in issue_types


def test_evidence_matrix_company_scoped_empty_state(monkeypatch, tmp_stock_root):
    monkeypatch.setattr(
        research_pages.evidence_matrix,
        "build_company_evidence_matrix",
        lambda company_id: {
            "company_id": company_id,
            "company_name": "Empty Co",
            "generated_at": "2026-06-14T12:00:00+00:00",
            "claims": [],
            "claim_count": 0,
        },
    )
    monkeypatch.setattr(
        research_pages.storage,
        "get_company",
        lambda company_id: {"id": company_id, "name": "Empty Co"},
    )

    payload = research_pages.evidence_matrix_page(company_id="empty-co")

    assert payload["status"] == "empty"
    assert payload["summary"]["company_id"] == "empty-co"
    assert {issue["type"] for issue in payload["doctor_issues"]} == {"evidence_matrix_empty"}


def test_evidence_matrix_company_scoped_weak_source_only(monkeypatch, tmp_stock_root):
    monkeypatch.setattr(
        research_pages.evidence_matrix,
        "build_company_evidence_matrix",
        lambda company_id: {
            "company_id": company_id,
            "company_name": "Weak Co",
            "generated_at": "2026-06-14T12:00:00+00:00",
            "claims": [
                {
                    "claim": "Weak-source-only product adoption claim.",
                    "status": "supported",
                    "confidence": "medium",
                    "source_coverage": {"source_count": 1},
                    "supporting_evidence": [
                        {
                            "task_id": "task-weak",
                            "task_title": "Analyst desk note",
                            "source_kind": "unsourced_note",
                            "locator": "note",
                            "excerpt": "Desk note only.",
                            "confidence": "medium",
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        research_pages.storage,
        "get_company",
        lambda company_id: {"id": company_id, "name": "Weak Co"},
    )

    payload = research_pages.evidence_matrix_page(company_id="weak-co")
    claim = payload["sections"]["claim_table"][0]

    assert claim["eligible_for_memo"] is False
    assert "primary source" in claim["memo_eligibility_reason"]
    assert "evidence_claim_weak_source_only" in {
        issue["type"] for issue in payload["doctor_issues"]
    }


def test_market_pulse_empty_state_preserves_page_frame(tmp_stock_root):
    payload = research_pages.market_pulse_page()

    assert payload["status"] == "empty"
    assert payload["summary"]["empty_state"] == "Missing latest Stock Research weekly aggregate."
    assert payload["sections"]["market_regime"]["posture"] == "empty"
    assert payload["sections"]["theme_heatmap"] == []
    assert payload["sections"]["changed_since_last_week"]["new_signals"] == []
    assert payload["sections"]["catalyst_calendar"] == []
    assert payload["sections"]["next_steps"][0]["endpoint"] == "/api/stock-research/aggregates/run"


def test_hypothesis_lab_surfaces_no_lookahead_warning(tmp_stock_root):
    hypothesis_store.write_hypothesis_snapshot(
        {
            "hypothesis_id": "hyp-lookahead",
            "vintage_kind": "forward_live",
            "eligible_for_training": False,
            "generated_at": "2026-06-15T01:00:00+00:00",
            "vintage_date": "2026-06-14",
            "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
            "evaluation_window_start": "2026-06-15",
            "evaluation_window_end": "2026-06-21",
            "tracker_id": "nvidia",
            "tracker_type": "company",
            "ticker": "NVDA",
            "claim": "Generated too late.",
            "direction": "bullish",
            "confidence": 0.8,
            "input_manifest": {"sources": []},
        }
    )

    payload = research_pages.hypothesis_lab_page()
    row = payload["sections"]["hypotheses"][0]

    assert row["training_eligible"] is False
    assert "hypothesis_generated_after_window_start" in {
        issue["type"] for issue in payload["doctor_issues"]
    }


def test_hypothesis_lab_keeps_live_and_debug_rows_separate(tmp_stock_root):
    base = {
        "generated_at": "2026-06-14T12:00:00+00:00",
        "vintage_date": "2026-06-14",
        "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
        "evaluation_window_start": "2026-06-15",
        "evaluation_window_end": "2026-06-21",
        "tracker_id": "nvidia",
        "tracker_type": "company",
        "ticker": "NVDA",
        "direction": "bullish",
        "confidence": 0.8,
        "input_manifest": {"sources": []},
    }
    hypothesis_store.write_hypothesis_snapshot(
        {
            **base,
            "hypothesis_id": "hyp-live-mixed",
            "vintage_kind": "forward_live",
            "claim": "Live claim.",
        }
    )
    hypothesis_store.write_hypothesis_snapshot(
        {
            **base,
            "hypothesis_id": "hyp-debug-mixed",
            "vintage_kind": "debug_backfill",
            "claim": "Debug claim.",
        }
    )

    payload = research_pages.hypothesis_lab_page()
    rows = [
        row
        for row in payload["sections"]["vintage_timeline"]
        if row["vintage_date"] == "2026-06-14"
    ]

    assert [row["vintage_kind"] for row in rows] == ["forward_live", "debug_backfill"]
    assert all(row["generated_count"] == 1 for row in rows)
    assert rows[1]["training_eligible_count"] == 0


def test_hypothesis_lab_dedupes_stock_doctor_issue(monkeypatch, tmp_stock_root):
    today = research_pages._today()
    monkeypatch.setattr(
        research_pages.stock_research,
        "stock_research_doctor",
        lambda: {
            "issues": [
                {
                    "severity": "warning",
                    "type": "missing_current_live_hypothesis_vintage",
                    "message": f"No forward_live hypothesis vintage exists for {today}.",
                    "path": "/tmp/hypotheses",
                }
            ]
        },
    )

    payload = research_pages.hypothesis_lab_page()
    matching = [
        issue
        for issue in payload["doctor_issues"]
        if issue["type"] == "missing_current_live_hypothesis_vintage"
    ]

    assert len(matching) == 1
    assert matching[0]["source"] == "stock_research_doctor"
    assert matching[0]["path"] == "/tmp/hypotheses"


def test_research_pages_api_routes(client):
    assert client.get("/api/research-pages/market-pulse").status_code == 200
    assert client.get("/api/research-pages/evidence-matrix").status_code == 200
    assert client.get("/api/research-pages/hypothesis-lab").status_code == 200
