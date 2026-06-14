from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import stock_research
from server.main import app


def wait_for_terminal(path, timeout=3.0):
    deadline = time.monotonic() + timeout
    state = stock_research.job_progress.scan_progress_state(path)
    while not state.get("terminated") and time.monotonic() < deadline:
        time.sleep(0.02)
        state = stock_research.job_progress.scan_progress_state(path)
    return state


def assert_metric_fields(metadata: dict):
    for key in (
        "duration_ms",
        "token_usage",
        "estimated_cost_usd",
        "source_count",
        "source_priority_mix",
        "source_quality",
        "evidence_coverage",
        "contradiction_count",
        "missing_source_count",
        "reviewer_score",
        "reviewer_scores",
    ):
        assert key in metadata


@pytest.fixture
def tmp_stock_root(monkeypatch, tmp_path):
    root = tmp_path / "stock_research"
    monkeypatch.setattr(stock_research, "STOCK_RESEARCH_ROOT", root)
    return root


@pytest.fixture
def client(tmp_stock_root):
    return TestClient(app)


def test_seed_dashboard_and_path_safety(tmp_stock_root):
    payload = stock_research.dashboard_payload()

    assert payload["summary"]["tracker_count"] == 3
    assert payload["summary"]["tracker_counts_by_type"] == {
        "macro": 1,
        "industry": 1,
        "company": 1,
    }
    assert {tracker["id"] for tracker in payload["trackers"]} == {
        "us-macro",
        "ai-cloud-infrastructure",
        "nvidia",
    }

    us_macro = stock_research.get_tracker("us-macro")
    assert us_macro["schema_version"] == stock_research.SCHEMA_VERSION
    assert (tmp_stock_root / "trackers" / "us-macro" / "knowledge.json").exists()
    assert (tmp_stock_root / "trackers" / "us-macro" / "notes.md").exists()

    with pytest.raises(ValueError):
        stock_research.tracker_config_path("../bad")


def test_tracker_crud_status_defaults_and_work_product_updates(tmp_stock_root):
    tracker = stock_research.create_tracker(
        {
            "type": "company",
            "display_name": "Advanced Micro Devices",
            "tickers": ["amd"],
            "status": "nonsense",
        }
    )
    assert tracker["id"] == "advanced-micro-devices"
    assert tracker["status"] == "active"
    assert tracker["tickers"] == ["AMD"]
    assert tracker["cadence"]["frequency"] == "weekly"

    updated = stock_research.update_tracker(
        tracker["id"],
        {"priority": 1, "owner": "Analyst"},
    )
    assert updated["priority"] == 1
    assert updated["owner"] == "Analyst"

    disabled = stock_research.disable_tracker(tracker["id"])
    assert disabled["status"] == "disabled"

    product = stock_research.register_work_product(
        {
            "artifact_id": "manual:one",
            "artifact_type": "markdown_export",
            "title": "Manual note",
            "status": "bad-status",
        }
    )
    assert product["schema_version"] == stock_research.WORK_PRODUCT_SCHEMA_VERSION
    assert product["status"] == "draft"
    assert product["version_history"][0]["action"] == "created"
    pinned = stock_research.update_work_product("manual:one", {"pinned": True})
    assert pinned["pinned"] is True
    assert pinned["version_history"][-1]["action"] == "updated"
    assert "pinned" in pinned["version_history"][-1]["changed_fields"]
    approved = stock_research.update_work_product(
        "manual:one",
        {"status": "approved", "review_state": "resolved", "reviewer": "Serena"},
    )
    assert approved["status"] == "approved"
    assert approved["review_state"] == "resolved"
    assert approved["reviewer"] == "Serena"
    assert {"status", "review_state", "reviewer"} <= set(
        approved["version_history"][-1]["changed_fields"]
    )
    superseded = stock_research.update_work_product(
        "manual:one",
        {"status": "superseded", "superseded_by": "manual:two"},
    )
    assert superseded["status"] == "superseded"
    assert superseded["superseded_by"] == "manual:two"
    archived = stock_research.update_work_product(
        "manual:one",
        {"status": "archived", "archived": True},
    )
    assert archived["archived"] is True
    assert stock_research.list_work_products() == []
    assert stock_research.list_work_products(include_archived=True)[0]["artifact_id"] == "manual:one"


def test_source_assignment_prompt_and_tracker_output_preserve_traces(tmp_stock_root):
    stock_research.seed_tracker_registry()
    assert stock_research.TRACKER_OUTPUT_SCHEMA["properties"]["tracker_type"][
        "enum"
    ] == ["macro", "industry", "company"]
    assigned = stock_research.create_link_source(
        {
            "tracker_ids": ["us-macro", "nvidia"],
            "title": "FOMC note",
            "url": "https://example.com/fomc",
            "notes": "Rates commentary with source context.",
        }
    )
    assert len(assigned["assigned"]) == 2
    assert assigned["assigned"][0]["id"] == assigned["assigned"][1]["id"]

    us_macro = stock_research.get_tracker("us-macro")
    prompt = stock_research.build_tracker_prompt(
        us_macro,
        period_start="2026-06-08",
        period_end="2026-06-14",
    )
    assert "Unsupported facts must be null, missing, or source_needed" in prompt
    assert "central bank releases" in prompt
    assert "Do not use raw context from other trackers" in prompt
    stock_research.create_note_source(
        {
            "tracker_ids": ["us-macro"],
            "title": "Macro-only context",
            "body": "MACRO_ONLY_DO_NOT_LEAK_TO_COMPANY_TRACKER",
        }
    )
    nvidia_prompt = stock_research.build_tracker_prompt(
        stock_research.get_tracker("nvidia"),
        period_start="2026-06-08",
        period_end="2026-06-14",
    )
    assert "MACRO_ONLY_DO_NOT_LEAK_TO_COMPANY_TRACKER" not in nvidia_prompt

    run = stock_research.run_tracker_now(
        "us-macro",
        period_id="2026-06-08_to_2026-06-14",
    )
    assert_metric_fields(
        stock_research._read_json(
            stock_research.tracker_run_metadata_path("us-macro", run["run_id"]),
            {},
        )
    )
    output = stock_research.get_tracker_run_output("us-macro", run["run_id"])
    assert output["tracker_type"] == "macro"
    assert output["source_traces"]
    assert any(
        trace["source_id"] == assigned["source"]["id"]
        for trace in output["source_traces"]
    )
    assert output["missing_sources"] == []
    assert "major_events" in output["type_sections"]


def test_file_source_extraction_and_missing_file_review_state(tmp_stock_root):
    stock_research.seed_tracker_registry()
    created = stock_research.create_file_source(
        tracker_ids=["us-macro", "nvidia"],
        filename="weekly-note.txt",
        content_type="text/plain",
        data=b"Rates moved after the policy release.\nSemis demand stayed firm.",
        title="Weekly note",
    )

    assert len(created["assigned"]) == 2
    assert created["source"]["extraction_status"] == "ready"
    assert created["source"]["chunks"][0]["locator"] == "document"
    assert "policy release" in created["source"]["chunks"][0]["excerpt"]

    stored_name = created["assigned"][0]["stored_name"]
    (stock_research.tracker_sources_dir("us-macro") / stored_name).unlink()
    sources = stock_research.list_tracker_sources("us-macro")
    missing = next(source for source in sources if source["id"] == created["source"]["id"])

    assert missing["exists"] is False
    assert missing["extraction_status"] == "missing"
    assert "Stored file is missing" in missing["missing_reason"]
    review_items = stock_research.list_review_items()
    assert any(
        item["item_type"] == "missing_source"
        and item["artifact_id"] == f"source:us-macro:{created['source']['id']}"
        for item in review_items
    )


def test_doctor_reports_missing_source_files_and_run_ledger(tmp_stock_root):
    stock_research.seed_tracker_registry()
    created = stock_research.create_file_source(
        tracker_ids=["us-macro"],
        filename="policy-note.txt",
        content_type="text/plain",
        data=b"Official source context.",
        title="Policy note",
        priority="official",
    )
    run = stock_research.run_tracker_now(
        "us-macro",
        period_id="2026-06-08_to_2026-06-14",
    )
    stored_name = created["assigned"][0]["stored_name"]
    (stock_research.tracker_sources_dir("us-macro") / stored_name).unlink()

    doctor = stock_research.stock_research_doctor()
    ledger = stock_research.list_run_ledger()

    assert doctor["status"] == "issues"
    assert doctor["summary"]["error_count"] >= 1
    assert any(issue["type"] == "missing_source_file" for issue in doctor["issues"])
    assert any(
        entry["job_kind"] == "stock_tracker"
        and entry["run_id"] == run["run_id"]
        and entry["source_quality"]["average"] > 0
        for entry in ledger
    )


def test_note_source_and_ocr_handoff_metadata(monkeypatch, tmp_stock_root):
    stock_research.seed_tracker_registry()
    note = stock_research.create_note_source(
        {
            "tracker_ids": ["us-macro", "nvidia"],
            "title": "Channel check",
            "body": "Manual note says hyperscaler demand remains resilient.",
            "priority": "user_provided",
            "relevance": "this_week_input",
        }
    )
    assert len(note["assigned"]) == 2
    assert note["source"]["source_type"] == "note"
    assert note["source"]["chunks"][0]["locator"] == "note"
    assert "hyperscaler demand" in note["source"]["chunks"][0]["excerpt"]

    calls = []

    def fake_ocr(path):
        calls.append(path.name)
        return [
            {
                "label": "OCR text",
                "locator": "ocr",
                "excerpt": "OCR extracted channel-check image text.",
                "char_count": 39,
            }
        ]

    monkeypatch.setattr(stock_research, "_ocr_source_chunks_from_path", fake_ocr)
    image = stock_research.create_file_source(
        tracker_ids=["us-macro"],
        filename="channel-check.png",
        content_type="image/png",
        data=b"not-really-an-image",
        title="Channel check image",
    )
    assert calls == ["channel-check.png"]
    assert image["source"]["extraction_status"] == "ready"
    assert image["source"]["ocr_needed"] is False
    assert image["source"]["chunks"][0]["locator"] == "ocr"


def test_aggregate_and_strategy_map_require_tracker_source_refs(tmp_stock_root):
    stock_research.seed_tracker_registry()
    for tracker in stock_research.list_trackers():
        stock_research.create_note_source(
            {
                "tracker_ids": [tracker["id"]],
                "title": f"{tracker['display_name']} weekly note",
                "body": f"{tracker['display_name']} source-backed weekly context.",
            }
        )
        stock_research.run_tracker_now(
            tracker["id"],
            period_id="2026-06-08_to_2026-06-14",
        )

    aggregate = stock_research.run_aggregate_now("2026-06-08_to_2026-06-14")
    assert (
        stock_research.WEEKLY_AGGREGATE_SCHEMA["properties"]["schema_version"][
            "const"
        ]
        == stock_research.WEEKLY_AGGREGATE_SCHEMA_VERSION
    )
    assert len(aggregate["included_tracker_run_ids"]) == 3
    assert aggregate["ranked_signals"]
    assert all(
        signal.get("source_tracker_id")
        and signal.get("tracker_run_id")
        and signal.get("source_traces")
        for signal in aggregate["ranked_signals"]
    )
    assert aggregate["deduped_claims"]
    assert all(
        claim.get("contributing_tracker_refs")
        and claim.get("source_traces")
        for claim in aggregate["deduped_claims"]
    )
    assert "raw" not in aggregate["markdown"].lower()

    strategy_map = stock_research.run_strategy_map_now("2026-06-08_to_2026-06-14")
    assert (
        stock_research.STRATEGY_MAP_SCHEMA["properties"]["schema_version"][
            "const"
        ]
        == stock_research.STRATEGY_MAP_SCHEMA_VERSION
    )
    assert strategy_map["nodes"]
    assert all(node.get("source_tracker_refs") for node in strategy_map["nodes"])
    assert all(node.get("source_traces") for node in strategy_map["nodes"])
    assert "not automated trading" in strategy_map["markdown"]


def test_aggregate_ranks_equal_signals_by_source_quality(tmp_stock_root):
    stock_research.seed_tracker_registry()
    stock_research.create_note_source(
        {
            "tracker_ids": ["us-macro"],
            "title": "Official macro note",
            "body": "Official source-backed macro signal.",
            "priority": "official",
        }
    )
    stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "Desk note",
            "body": "Lower-priority analyst note.",
            "priority": "note",
        }
    )
    macro = stock_research.run_tracker_now(
        "us-macro",
        period_id="2026-06-08_to_2026-06-14",
    )
    company = stock_research.run_tracker_now(
        "nvidia",
        period_id="2026-06-08_to_2026-06-14",
    )
    for tracker_id, run_id in [
        ("us-macro", macro["run_id"]),
        ("nvidia", company["run_id"]),
    ]:
        output = stock_research.get_tracker_run_output(tracker_id, run_id)
        output["confidence"] = 0.5
        output["key_signals"][0]["importance"] = 3
        output["key_signals"][0]["confidence"] = 0.5
        stock_research._write_json(
            stock_research.tracker_run_output_path(tracker_id, run_id),
            output,
        )

    aggregate = stock_research.run_aggregate_now("2026-06-08_to_2026-06-14")

    assert aggregate["ranked_signals"][0]["source_tracker_id"] == "us-macro"
    assert aggregate["ranked_signals"][0]["source_quality_score"] > aggregate[
        "ranked_signals"
    ][1]["source_quality_score"]
    assert aggregate["ranked_signals"][0]["rank_score"] > aggregate["ranked_signals"][1]["rank_score"]


def test_aggregate_warnings_contradictions_and_raw_context_boundary(tmp_stock_root):
    stock_research.seed_tracker_registry()
    stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "Company-only note",
            "body": "RAW_COMPANY_NOTE_BODY_SHOULD_NOT_BE_COPIED_TO_AGGREGATE_MARKDOWN",
        }
    )
    run = stock_research.run_tracker_now(
        "nvidia",
        period_id="2026-06-08_to_2026-06-14",
    )
    output = stock_research.get_tracker_run_output("nvidia", run["run_id"])
    output["contradictions"] = [
        {
            "id": "contra-demand",
            "description": "Demand signal conflicts with channel checks.",
            "source_traces": output["source_traces"][:1],
        }
    ]
    stock_research._write_json(
        stock_research.tracker_run_output_path("nvidia", run["run_id"]),
        output,
    )

    aggregate = stock_research.run_aggregate_now("2026-06-08_to_2026-06-14")
    warning_ids = {
        warning.get("tracker_id")
        for warning in aggregate["excluded_tracker_warnings"]
    }
    assert {"us-macro", "ai-cloud-infrastructure"} <= warning_ids
    assert aggregate["contradictions"][0]["description"] == (
        "Demand signal conflicts with channel checks."
    )
    assert aggregate["deduped_claims"][0]["source_traces"]
    assert "RAW_COMPANY_NOTE_BODY" not in aggregate["markdown"]
    aggregate["deduped_claims"].append(
        {
            "claim": "Ambiguous AI demand claim",
            "ambiguous": True,
            "contributing_tracker_refs": [
                {"tracker_id": "nvidia", "tracker_run_id": run["run_id"]},
                {"tracker_id": "us-macro", "tracker_run_id": "manual"},
            ],
            "source_traces": output["source_traces"][:1],
        }
    )
    stock_research._write_weekly_aggregate(aggregate)
    assert any(
        item["item_type"] == "ambiguous_claim"
        and item["title"] == "Ambiguous AI demand claim"
        for item in stock_research.list_review_items()
    )


def test_strategy_map_diff_unsupported_signal_and_failure_preservation(monkeypatch, tmp_stock_root):
    stock_research.seed_tracker_registry()
    for tracker in stock_research.list_trackers():
        stock_research.create_note_source(
            {
                "tracker_ids": [tracker["id"]],
                "title": f"{tracker['display_name']} note",
                "body": f"{tracker['display_name']} sourced strategy context.",
            }
        )
        stock_research.run_tracker_now(
            tracker["id"],
            period_id="2026-06-08_to_2026-06-14",
        )
    first = stock_research.run_strategy_map_now("2026-06-08_to_2026-06-14")
    assert first["nodes"]
    assert all(node["source_traces"] for node in first["nodes"])

    empty_aggregate = stock_research.coerce_weekly_aggregate(
        {
            "included_tracker_run_ids": [],
            "modules": {},
            "ranked_signals": [],
            "markdown": "# Empty week",
        },
        period_id="2026-06-15_to_2026-06-21",
        period_start="2026-06-15",
        period_end="2026-06-21",
    )
    stock_research._write_weekly_aggregate(empty_aggregate)
    second = stock_research.run_strategy_map_now("2026-06-15_to_2026-06-21")
    assert second["nodes"] == []
    assert any(item["state"] == "removed" for item in second["diff"])

    unsupported = stock_research.coerce_weekly_aggregate(
        {
            "included_tracker_run_ids": ["manual:unsupported"],
            "modules": {},
            "ranked_signals": [
                {
                    "id": "unsupported-signal",
                    "observation": "Unsupported action claim",
                    "direction": "positive",
                    "affected_themes": ["unsupported"],
                    "source_traces": [],
                }
            ],
            "markdown": "# Unsupported",
        },
        period_id="2026-06-22_to_2026-06-28",
        period_start="2026-06-22",
        period_end="2026-06-28",
    )
    stock_research._write_weekly_aggregate(unsupported)
    unsupported_map = stock_research.run_strategy_map_now("2026-06-22_to_2026-06-28")
    assert unsupported_map["nodes"] == []

    before = stock_research.latest_strategy_map()

    def fail_build(period_id=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(stock_research, "build_strategy_map", fail_build)
    stock_research._run_strategy_job("2026-06-29_to_2026-07-05")
    assert stock_research.latest_strategy_map()["period_id"] == before["period_id"]
    assert any(
        item["item_type"] == "failed_job"
        and item["artifact_id"] == "strategy_map:2026-06-29_to_2026-07-05"
        for item in stock_research.list_review_items()
    )


def test_claude_tracker_job_writes_structured_output(monkeypatch, tmp_stock_root):
    stock_research.seed_tracker_registry()
    assigned = stock_research.create_note_source(
        {
            "tracker_ids": ["us-macro"],
            "title": "Policy note",
            "body": "The Fed signaled a patient stance after mixed inflation data.",
        }
    )
    source_id = assigned["source"]["id"]
    period_id = "2026-06-08_to_2026-06-14"
    run_id = f"{period_id}-claude"

    def fake_structured_prompt(**kwargs):
        assert kwargs["schema"] is stock_research.TRACKER_OUTPUT_SCHEMA
        assert "Tracker-owned source context" in kwargs["user_prompt"]
        trace = {
            "tracker_id": "us-macro",
            "tracker_run_id": run_id,
            "source_id": source_id,
            "source_title": "Policy note",
            "locator": "note",
            "excerpt": "patient stance",
            "confidence": 0.88,
            "checked_at": "2026-06-13T00:00:00+00:00",
        }
        return {
            "schema_version": stock_research.TRACKER_OUTPUT_SCHEMA_VERSION,
            "tracker_id": "us-macro",
            "tracker_type": "macro",
            "tracker_run_id": run_id,
            "period_start": "2026-06-08",
            "period_end": "2026-06-14",
            "generated_at": "2026-06-13T00:00:00+00:00",
            "status": "done",
            "confidence": 0.82,
            "thesis": "Macro conditions warrant a patient policy read.",
            "key_signals": [
                {
                    "id": "sig-policy",
                    "observation": "Policy stance remains patient.",
                    "importance": 4,
                    "direction": "neutral",
                    "affected_themes": ["rates"],
                    "source_traces": [trace],
                }
            ],
            "metrics": [],
            "recommendations": [],
            "open_questions": [],
            "missing_sources": [],
            "contradictions": [],
            "watch_items": [],
            "source_traces": [trace],
            "knowledge_updates": [],
            "type_sections": {},
        }, None

    monkeypatch.setattr(
        stock_research.claude_runner,
        "run_structured_prompt",
        fake_structured_prompt,
    )
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("us-macro", run_id),
        stock_research._run_metadata(
            run_id=run_id,
            tracker_id="us-macro",
            period_id=period_id,
            period_start="2026-06-08",
            period_end="2026-06-14",
            status="running",
        ),
    )

    stock_research._run_tracker_job(
        "us-macro",
        run_id,
        period_id,
        "2026-06-08",
        "2026-06-14",
        use_claude=True,
    )

    output = stock_research.get_tracker_run_output("us-macro", run_id)
    assert output["generated_by"] == "claude_code"
    assert output["thesis"] == "Macro conditions warrant a patient policy read."
    assert output["source_traces"][0]["source_id"] == source_id
    metadata = stock_research._read_json(
        stock_research.tracker_run_metadata_path("us-macro", run_id),
        {},
    )
    assert metadata["status"] == "done"
    assert_metric_fields(metadata)
    assert stock_research.get_tracker("us-macro")["latest_run_id"] == run_id


def test_claude_tracker_failure_preserves_previous_good_output(monkeypatch, tmp_stock_root):
    stock_research.seed_tracker_registry()
    stock_research.create_note_source(
        {
            "tracker_ids": ["nvidia"],
            "title": "Company note",
            "body": "NVIDIA demand remains tied to AI infrastructure capex.",
        }
    )
    period_id = "2026-06-08_to_2026-06-14"
    previous = stock_research.run_tracker_now("nvidia", period_id=period_id)
    previous_output = stock_research.get_tracker_run_output("nvidia", previous["run_id"])

    def failing_structured_prompt(**_kwargs):
        return None, "simulated Claude failure"

    monkeypatch.setattr(
        stock_research.claude_runner,
        "run_structured_prompt",
        failing_structured_prompt,
    )
    run_id = f"{period_id}-failed-claude"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", run_id),
        stock_research._run_metadata(
            run_id=run_id,
            tracker_id="nvidia",
            period_id=period_id,
            period_start="2026-06-08",
            period_end="2026-06-14",
            status="running",
        ),
    )

    stock_research._run_tracker_job(
        "nvidia",
        run_id,
        period_id,
        "2026-06-08",
        "2026-06-14",
        use_claude=True,
    )

    failed_metadata = stock_research._read_json(
        stock_research.tracker_run_metadata_path("nvidia", run_id),
        {},
    )
    assert failed_metadata["status"] == "error"
    assert failed_metadata["preserved_previous_run_id"] == previous["run_id"]
    assert_metric_fields(failed_metadata)
    assert not stock_research.tracker_run_output_path("nvidia", run_id).exists()
    assert stock_research.get_tracker("nvidia")["latest_run_id"] == previous["run_id"]
    assert (
        stock_research.get_tracker_run_output("nvidia", previous["run_id"])
        == previous_output
    )
    assert any(
        item["item_type"] == "failed_job" and item["run_id"] == run_id
        for item in stock_research.list_review_items()
    )


def test_review_queue_and_evaluation_lifecycle(tmp_stock_root):
    stock_research.seed_tracker_registry()
    run = stock_research.run_tracker_now(
        "nvidia",
        period_id="2026-06-08_to_2026-06-14",
    )

    review_items = stock_research.list_review_items()
    assert any(item["item_type"] == "missing_source" for item in review_items)
    item = next(item for item in review_items if item["item_type"] == "missing_source")
    updated = stock_research.update_review_item(
        item["id"],
        {"status": "waived", "rationale": "Accepted for fixture run."},
    )
    assert updated["status"] == "waived"
    assert "fixture" in updated["rationale"]

    reviewed_run = stock_research.update_run_review(
        "nvidia",
        run["run_id"],
        {
            "factual_accuracy": 4,
            "usefulness": 5,
            "source_quality": 3,
            "writing_quality": 4,
            "actionability": 4,
        },
    )
    assert reviewed_run["reviewer_score"] == 4.0
    evaluation = stock_research.list_evaluation()
    assert evaluation["runs"][0]["reviewer_score"] == 4.0

    output = stock_research.get_tracker_run_output("nvidia", run["run_id"])
    update_id = output["knowledge_updates"][0]["id"]
    accepted = stock_research.review_knowledge_update(
        "nvidia",
        run["run_id"],
        update_id,
        status="resolved",
        rationale="Useful ownership lesson.",
    )
    assert accepted["review_status"] == "resolved"
    knowledge = json.loads(stock_research.tracker_knowledge_path("nvidia").read_text())
    assert any(item["id"] == update_id for item in knowledge["accepted_lessons"])
    review = next(
        item
        for item in stock_research.list_review_items(status="resolved")
        if item["item_type"] == "knowledge_update"
    )
    assert "Useful ownership lesson" in review["rationale"]


def test_retry_cancel_and_failed_job_review_lifecycle(tmp_stock_root):
    stock_research.seed_tracker_registry()
    period_id = "2026-06-08_to_2026-06-14"
    active_run_id = f"{period_id}-active"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", active_run_id),
        stock_research._run_metadata(
            run_id=active_run_id,
            tracker_id="nvidia",
            period_id=period_id,
            period_start="2026-06-08",
            period_end="2026-06-14",
            status="running",
        ),
    )
    stock_research._update_tracker_current_run(
        "nvidia",
        {
            "run_id": active_run_id,
            "period_id": period_id,
            "status": "running",
            "started_at": "2026-06-13T12:00:00Z",
        },
    )
    active_progress = stock_research.job_progress.ProgressLog(
        stock_research.tracker_progress_path("nvidia", active_run_id)
    )
    active_progress.emit(
        "job_init",
        kind="stock_tracker",
        tracker_id="nvidia",
        run_id=active_run_id,
    )
    attached = stock_research.start_tracker_run(
        "nvidia",
        period_id=period_id,
        use_claude=False,
    )
    assert attached["status"] == "already_running"
    assert attached["run_id"] == active_run_id
    assert stock_research.recover_stale_runs(max_idle_seconds=0) >= 1
    recovered_meta = stock_research._read_json(
        stock_research.tracker_run_metadata_path("nvidia", active_run_id),
        {},
    )
    assert recovered_meta["status"] == "recovered"
    assert_metric_fields(recovered_meta)

    failed_run_id = f"{period_id}-failed"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", failed_run_id),
        stock_research._run_metadata(
            run_id=failed_run_id,
            tracker_id="nvidia",
            period_id=period_id,
            period_start="2026-06-08",
            period_end="2026-06-14",
            status="error",
        ),
    )
    assert_metric_fields(
        stock_research._read_json(
            stock_research.tracker_run_metadata_path("nvidia", failed_run_id),
            {},
        )
    )
    cancel_run_id = f"{period_id}-cancel"
    stock_research._write_json(
        stock_research.tracker_run_metadata_path("nvidia", cancel_run_id),
        stock_research._run_metadata(
            run_id=cancel_run_id,
            tracker_id="nvidia",
            period_id=period_id,
            period_start="2026-06-08",
            period_end="2026-06-14",
            status="running",
        ),
    )
    stock_research.job_progress.ProgressLog(
        stock_research.tracker_progress_path("nvidia", cancel_run_id)
    ).emit(
        "job_init",
        kind="stock_tracker",
        tracker_id="nvidia",
        run_id=cancel_run_id,
    )
    cancelled = stock_research.cancel_tracker_run("nvidia", cancel_run_id)
    assert cancelled["cancelled"] is True
    cancelled_meta = stock_research._read_json(
        stock_research.tracker_run_metadata_path("nvidia", cancel_run_id),
        {},
    )
    assert cancelled_meta["status"] == "cancelled"
    assert_metric_fields(cancelled_meta)

    retry = stock_research.retry_tracker_run(
        "nvidia",
        failed_run_id,
        use_claude=False,
    )
    assert retry["status"] == "queued"
    assert retry["period_id"] == period_id
    assert retry["run_id"] != failed_run_id
    wait_for_terminal(stock_research.tracker_progress_path("nvidia", retry["run_id"]))

    cancelled_aggregate = stock_research.cancel_aggregate_job(period_id)
    assert cancelled_aggregate["cancelled"] is True
    retry_aggregate = stock_research.retry_aggregate_job(period_id)
    assert retry_aggregate["status"] in {"queued", "already_running"}
    wait_for_terminal(stock_research.aggregate_progress_path(period_id))

    cancelled_strategy = stock_research.cancel_strategy_map_job(period_id)
    assert cancelled_strategy["cancelled"] is True
    retry_strategy = stock_research.retry_strategy_map_job(period_id)
    assert retry_strategy["status"] in {"queued", "already_running"}
    wait_for_terminal(stock_research.strategy_map_progress_path(period_id))

    review_items = stock_research.list_review_items()
    assert any(item["item_type"] == "cancelled_job" for item in review_items)


def test_stock_research_api_dashboard_and_tracker_create(client):
    response = client.get("/api/stock-research")
    assert response.status_code == 200
    assert response.json()["summary"]["tracker_count"] == 3
    assert "doctor" in response.json()

    doctor = client.get("/api/stock-research/doctor")
    assert doctor.status_code == 200
    assert doctor.json()["summary"]["tracker_count"] == 3

    ledger = client.get("/api/stock-research/run-ledger")
    assert ledger.status_code == 200
    assert isinstance(ledger.json(), list)

    response = client.post(
        "/api/stock-research/trackers",
        json={
            "type": "industry",
            "display_name": "Optical Communications",
            "sector": "Technology",
            "industry": "Optical communications",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == "optical-communications"

    bad = client.post(
        "/api/stock-research/trackers",
        json={"type": "company", "display_name": "No Ticker"},
    )
    assert bad.status_code == 400
