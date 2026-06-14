from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import hypothesis_cycle, hypothesis_store, stock_research
from server.main import app


@pytest.fixture
def tmp_stock_root(monkeypatch, tmp_path):
    root = tmp_path / "stock_research"
    monkeypatch.setattr(stock_research, "STOCK_RESEARCH_ROOT", root)
    return root


@pytest.fixture
def client(tmp_stock_root):
    return TestClient(app)


def _write_aggregate(
    *,
    period_id: str = "2026-06-08_to_2026-06-14",
    generated_at: str = "2026-06-14T12:00:00+00:00",
) -> dict:
    stock_research.seed_tracker_registry()
    aggregate = stock_research.coerce_weekly_aggregate(
        {
            "generated_at": generated_at,
            "included_tracker_run_ids": ["nvidia:run-1"],
            "modules": {
                "macro": [],
                "industry": [],
                "company": [],
                "cross_tracker": [],
                "watchlist": [],
            },
            "ranked_signals": [
                {
                    "id": "sig-nvda",
                    "source_tracker_id": "nvidia",
                    "tracker_run_id": "run-1",
                    "ticker": "NVDA",
                    "observation": "AI demand remains resilient.",
                    "direction": "bullish",
                    "confidence": 0.8,
                    "source_traces": [
                        {
                            "source_id": "src-1",
                            "source_title": "Transcript",
                            "locator": "p.1",
                            "excerpt": "Demand remains resilient.",
                        }
                    ],
                    "source_quality_score": 0.9,
                    "source_quality_reason": "Primary transcript.",
                    "primary_source_count": 1,
                    "weak_source_count": 0,
                }
            ],
            "deduped_claims": [],
            "contradictions": [],
            "missing_source_warnings": [],
            "markdown": "# Weekly",
        },
        period_id=period_id,
        period_start=period_id.split("_to_")[0],
        period_end=period_id.split("_to_")[1],
    )
    stock_research._write_weekly_aggregate(aggregate)
    return aggregate


def test_create_command_respects_forward_and_debug_dates(monkeypatch, tmp_stock_root):
    _write_aggregate()
    monkeypatch.setattr(
        hypothesis_cycle, "current_date", lambda: __import__("datetime").date(2026, 6, 14)
    )

    live = hypothesis_cycle.create_hypotheses(vintage_date="2026-06-14")
    assert live["vintage_kind"] == "forward_live"
    assert live["hypotheses"][0]["evaluation_window_start"] == "2026-06-15"

    with pytest.raises(ValueError, match="past vintage"):
        hypothesis_cycle.create_hypotheses(vintage_date="2026-06-07")

    _write_aggregate(generated_at="2026-06-07T12:00:00+00:00")
    backfill = hypothesis_cycle.create_hypotheses(
        vintage_date="2026-06-07",
        allow_debug_backfill=True,
    )
    assert backfill["vintage_kind"] == "debug_backfill"
    assert backfill["hypotheses"][0]["eligible_for_training"] is False


def test_debug_backfill_windows_are_stable(monkeypatch, tmp_stock_root):
    _write_aggregate(generated_at="2026-05-31T12:00:00+00:00")
    monkeypatch.setattr(
        hypothesis_cycle, "current_date", lambda: __import__("datetime").date(2026, 6, 14)
    )

    first = hypothesis_cycle.debug_backfill("2026-05-31", horizon_days=7)
    second = hypothesis_cycle.debug_backfill("2026-06-07", horizon_days=7)

    assert first["hypotheses"][0]["evaluation_window_start"] == "2026-06-01"
    assert first["hypotheses"][0]["evaluation_window_end"] == "2026-06-07"
    assert second["hypotheses"][0]["evaluation_window_start"] == "2026-06-08"
    assert second["hypotheses"][0]["evaluation_window_end"] == "2026-06-14"
    assert all(row["vintage_kind"] == "debug_backfill" for row in first["hypotheses"])


def test_fixture_evaluator_scores_direction_and_missing_prices(tmp_stock_root):
    snapshot = hypothesis_store.write_hypothesis_snapshot(
        {
            "hypothesis_id": "hyp-hit",
            "vintage_kind": "forward_live",
            "generated_at": "2026-06-14T12:00:00+00:00",
            "vintage_date": "2026-06-14",
            "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
            "evaluation_window_start": "2026-06-15",
            "evaluation_window_end": "2026-06-21",
            "tracker_id": "nvidia",
            "tracker_type": "company",
            "ticker": "NVDA",
            "claim": "Bullish claim.",
            "direction": "bullish",
            "confidence": 0.8,
            "input_manifest": {"sources": []},
        }
    )
    adapter = hypothesis_cycle.FixtureMarketDataAdapter(
        {
            "NVDA": {
                "2026-06-15": 100,
                "2026-06-16": 98,
                "2026-06-21": 112,
            },
            "SPY": {"2026-06-15": 100, "2026-06-21": 101},
        }
    )
    outcome = hypothesis_cycle.evaluate_hypothesis(snapshot, adapter)
    assert outcome["directional_result"] == "hit"
    assert outcome["relative_return_pct"] == 11
    assert outcome["market_data_snapshot_sha256"]
    assert outcome["eligible_for_training"] is True

    missing = hypothesis_store.write_hypothesis_snapshot(
        {
            "hypothesis_id": "hyp-missing",
            "vintage_kind": "forward_live",
            "generated_at": "2026-06-14T12:00:00+00:00",
            "vintage_date": "2026-06-14",
            "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
            "evaluation_window_start": "2026-06-15",
            "evaluation_window_end": "2026-06-21",
            "tracker_id": "nvidia",
            "tracker_type": "company",
            "ticker": "MSNG",
            "claim": "Missing price claim.",
            "direction": "bullish",
            "confidence": 0.8,
            "input_manifest": {"sources": []},
        }
    )
    unresolved = hypothesis_cycle.evaluate_hypothesis(missing, adapter)
    assert unresolved["directional_result"] == "unresolved"
    assert unresolved["eligible_for_training"] is False


def test_calibration_excludes_debug_backfills(tmp_stock_root):
    live = hypothesis_store.write_hypothesis_snapshot(
        {
            "hypothesis_id": "hyp-live-cal",
            "vintage_kind": "forward_live",
            "generated_at": "2026-06-14T12:00:00+00:00",
            "vintage_date": "2026-06-14",
            "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
            "evaluation_window_start": "2026-06-15",
            "evaluation_window_end": "2026-06-21",
            "tracker_id": "nvidia",
            "tracker_type": "company",
            "ticker": "NVDA",
            "claim": "Live claim.",
            "direction": "bullish",
            "confidence": 0.8,
            "primary_source_count": 1,
            "input_manifest": {"sources": []},
        }
    )
    debug = hypothesis_store.write_hypothesis_snapshot(
        {
            "hypothesis_id": "hyp-debug-cal",
            "vintage_kind": "debug_backfill",
            "generated_at": "2026-06-07T12:00:00+00:00",
            "vintage_date": "2026-06-07",
            "eligible_source_cutoff": "2026-06-07T23:59:59+00:00",
            "evaluation_window_start": "2026-06-08",
            "evaluation_window_end": "2026-06-14",
            "tracker_id": "nvidia",
            "tracker_type": "company",
            "ticker": "NVDA",
            "claim": "Debug claim.",
            "direction": "bullish",
            "confidence": 0.8,
            "input_manifest": {"sources": []},
        }
    )
    hypothesis_store.write_hypothesis_outcome(
        {
            "hypothesis_id": live["hypothesis_id"],
            "evaluated_at": "2026-06-22T00:00:00+00:00",
            "evaluation_window_start": live["evaluation_window_start"],
            "evaluation_window_end": live["evaluation_window_end"],
            "ticker": "NVDA",
            "benchmark_ticker": "SPY",
            "relative_return_pct": 5,
            "directional_result": "hit",
            "confidence_bucket": "high",
            "calibration_bucket": "bullish:hit",
            "market_data_snapshot_sha256": "live",
            "eligible_for_training": True,
        }
    )
    hypothesis_store.write_hypothesis_outcome(
        {
            "hypothesis_id": debug["hypothesis_id"],
            "evaluated_at": "2026-06-15T00:00:00+00:00",
            "evaluation_window_start": debug["evaluation_window_start"],
            "evaluation_window_end": debug["evaluation_window_end"],
            "ticker": "NVDA",
            "benchmark_ticker": "SPY",
            "relative_return_pct": -5,
            "directional_result": "miss",
            "confidence_bucket": "high",
            "calibration_bucket": "bullish:miss",
            "market_data_snapshot_sha256": "debug",
            "eligible_for_training": False,
        }
    )

    summary = hypothesis_cycle.calibrate()
    assert summary["eligible_outcome_count"] == 1
    assert summary["hit_rate_by_confidence_bucket"] == [
        {"bucket": "high", "count": 1, "hit_rate": 1.0}
    ]


def test_hypothesis_api_create_list_evaluate_and_calibrate(client, monkeypatch):
    _write_aggregate()
    monkeypatch.setattr(
        hypothesis_cycle, "current_date", lambda: __import__("datetime").date(2026, 6, 14)
    )

    created = client.post(
        "/api/stock-research/hypotheses/create",
        json={"vintage_date": "2026-06-14"},
    )
    assert created.status_code == 201
    assert created.json()["created_count"] == 1

    listed = client.get("/api/stock-research/hypotheses")
    assert listed.status_code == 200
    assert listed.json()["summary"]["hypothesis_count"] == 1

    detail = client.get("/api/stock-research/hypotheses/2026-06-14")
    assert detail.status_code == 200
    assert detail.json()["hypotheses"][0]["ticker"] == "NVDA"

    evaluated = client.post(
        "/api/stock-research/hypotheses/2026-06-14/evaluate",
        json={
            "prices": {
                "NVDA": {"2026-06-15": 100, "2026-06-21": 112},
                "SPY": {"2026-06-15": 100, "2026-06-21": 101},
            }
        },
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["outcomes"][0]["directional_result"] == "hit"

    calibration = client.post("/api/stock-research/hypotheses/calibrate")
    assert calibration.status_code == 200
    assert calibration.json()["eligible_outcome_count"] == 1
