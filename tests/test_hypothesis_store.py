from __future__ import annotations

import json

import pytest

from server import hypothesis_store, stock_research


@pytest.fixture
def tmp_stock_root(monkeypatch, tmp_path):
    root = tmp_path / "stock_research"
    monkeypatch.setattr(stock_research, "STOCK_RESEARCH_ROOT", root)
    return root


def _snapshot(**overrides):
    manifest = {"sources": [{"id": "src-1", "created_at": "2026-06-14T12:00:00+00:00"}]}
    frozen = hypothesis_store.freeze_input_manifest(manifest)
    row = {
        "hypothesis_id": "hyp-2026-06-14-nvda",
        "vintage_kind": "forward_live",
        "generated_at": "2026-06-14T12:00:00+00:00",
        "vintage_date": "2026-06-14",
        "eligible_source_cutoff": "2026-06-14T23:59:59+00:00",
        "evaluation_window_start": "2026-06-15",
        "evaluation_window_end": "2026-06-21",
        "tracker_id": "nvidia",
        "tracker_type": "company",
        "ticker": "NVDA",
        "claim": "AI demand remains resilient.",
        "direction": "bullish",
        "expected_horizon_days": 7,
        "confidence": 0.8,
        "source_refs": [{"source_id": "src-1"}],
        "source_quality_score": 0.9,
        "source_quality_reason": "Primary source.",
        "primary_source_count": 1,
        "weak_source_count": 0,
        "input_manifest": frozen["manifest"],
        "input_manifest_sha256": frozen["sha256"],
    }
    row.update(overrides)
    return row


def test_snapshot_immutability_and_manifest_hash(tmp_stock_root):
    frozen_a = hypothesis_store.freeze_input_manifest({"b": 2, "a": [{"z": 1}]})
    frozen_b = hypothesis_store.freeze_input_manifest({"a": [{"z": 1}], "b": 2})
    assert frozen_a["sha256"] == frozen_b["sha256"]

    first = hypothesis_store.write_hypothesis_snapshot(_snapshot())
    again = hypothesis_store.write_hypothesis_snapshot(_snapshot())
    assert again == first

    with pytest.raises(ValueError, match="Frozen hypothesis"):
        hypothesis_store.write_hypothesis_snapshot(_snapshot(claim="Changed claim."))


def test_debug_backfill_is_never_training_eligible(tmp_stock_root):
    with pytest.raises(ValueError, match="debug_backfill"):
        hypothesis_store.write_hypothesis_snapshot(
            _snapshot(vintage_kind="debug_backfill", eligible_for_training=True)
        )

    debug = hypothesis_store.write_hypothesis_snapshot(
        _snapshot(
            hypothesis_id="hyp-debug",
            vintage_kind="debug_backfill",
            eligible_for_training=False,
        )
    )
    assert debug["eligible_for_training"] is False

    with pytest.raises(ValueError, match="Outcome is not eligible"):
        hypothesis_store.write_hypothesis_outcome(
            {
                "hypothesis_id": debug["hypothesis_id"],
                "evaluated_at": "2026-06-22T00:00:00+00:00",
                "evaluation_window_start": "2026-06-15",
                "evaluation_window_end": "2026-06-21",
                "ticker": "NVDA",
                "directional_result": "hit",
                "eligible_for_training": True,
            }
        )


def test_forward_live_outcome_training_eligibility_rules(tmp_stock_root):
    snapshot = hypothesis_store.write_hypothesis_snapshot(_snapshot())

    outcome = hypothesis_store.write_hypothesis_outcome(
        {
            "hypothesis_id": snapshot["hypothesis_id"],
            "evaluated_at": "2026-06-22T00:00:00+00:00",
            "evaluation_window_start": "2026-06-15",
            "evaluation_window_end": "2026-06-21",
            "ticker": "NVDA",
            "benchmark_ticker": "SPY",
            "start_price": 100,
            "end_price": 110,
            "absolute_return_pct": 10,
            "benchmark_return_pct": 2,
            "relative_return_pct": 8,
            "directional_result": "hit",
            "confidence_bucket": "high",
            "calibration_bucket": "bullish:hit",
            "market_data_snapshot_sha256": "abc",
            "eligible_for_training": True,
        }
    )
    assert outcome["eligible_for_training"] is True

    late = hypothesis_store.write_hypothesis_snapshot(
        _snapshot(
            hypothesis_id="hyp-late",
            generated_at="2026-06-15T01:00:00+00:00",
        )
    )
    with pytest.raises(ValueError, match="Outcome is not eligible"):
        hypothesis_store.write_hypothesis_outcome(
            {
                "hypothesis_id": late["hypothesis_id"],
                "evaluated_at": "2026-06-22T00:00:00+00:00",
                "evaluation_window_start": "2026-06-15",
                "evaluation_window_end": "2026-06-21",
                "ticker": "NVDA",
                "directional_result": "hit",
                "eligible_for_training": True,
            }
        )


def test_point_in_time_manifest_filters_future_inputs(tmp_stock_root):
    stock_research.seed_tracker_registry()
    before = stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "Before cutoff",
            "body": "Eligible source.",
        }
    )
    after = stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "After cutoff",
            "body": "Future source.",
        }
    )
    manifest_path = stock_research.tracker_source_manifest_path("nvidia")
    manifest = json.loads(manifest_path.read_text())
    for source in manifest["sources"]:
        if source["id"] == before["source"]["id"]:
            source["created_at"] = "2026-06-14T12:00:00+00:00"
        elif source["id"] == after["source"]["id"]:
            source["created_at"] = "2026-06-15T12:00:00+00:00"
    stock_research._write_json(manifest_path, manifest)

    run_id = "run-before"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", run_id),
        {
            **stock_research._run_metadata(
                run_id=run_id,
                tracker_id="nvidia",
                period_id="2026-06-08_to_2026-06-14",
                period_start="2026-06-08",
                period_end="2026-06-14",
                status="done",
            ),
            "created_at": "2026-06-14T12:00:00+00:00",
        },
    )
    stock_research._write_json(
        stock_research.tracker_run_output_path("nvidia", run_id),
        {
            "thesis": "Eligible thesis.",
            "confidence": 0.7,
            "source_traces": [],
        },
    )
    future_run_id = "run-after"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", future_run_id),
        {
            **stock_research._run_metadata(
                run_id=future_run_id,
                tracker_id="nvidia",
                period_id="2026-06-15_to_2026-06-21",
                period_start="2026-06-15",
                period_end="2026-06-21",
                status="done",
            ),
            "created_at": "2026-06-15T12:00:00+00:00",
        },
    )

    manifest_a = hypothesis_store.build_point_in_time_manifest("2026-06-14T23:59:59+00:00")
    source_ids = {row["id"] for row in manifest_a["manifest"]["sources"]}
    run_ids = {row["run_id"] for row in manifest_a["manifest"]["tracker_runs"]}
    assert before["source"]["id"] in source_ids
    assert after["source"]["id"] not in source_ids
    assert "run-before" in run_ids
    assert "run-after" not in run_ids

    manifest_b = hypothesis_store.build_point_in_time_manifest("2026-06-14T23:59:59+00:00")
    assert manifest_a["input_manifest_sha256"] == manifest_b["input_manifest_sha256"]
