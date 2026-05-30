from __future__ import annotations

import json

import pytest

from server import storage, trader_stats


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    return tmp_path


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_parse_progress_stats_sums_tokens_by_thread(tmp_data):
    progress_path = tmp_data / "_trader" / "amd__snapshot.progress.jsonl"
    _write_jsonl(
        progress_path,
        [
            {"type": "job_init", "ts": "2026-05-29T00:00:00+00:00"},
            {
                "type": "claude_action",
                "ts": "2026-05-29T00:00:01+00:00",
                "action": "result",
                "thread": "Price & returns",
                "cost_usd": 0.25,
                "duration_ms": 1200,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 300,
                    "cache_read_input_tokens": 700,
                    "server_tool_use": {"web_search_requests": 2},
                },
            },
            {
                "type": "claude_action",
                "ts": "2026-05-29T00:00:02+00:00",
                "action": "result",
                "thread": "Momentum",
                "cost_usd": 0.1,
                "duration_ms": 800,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                },
            },
            {
                "type": "thread_failed",
                "ts": "2026-05-29T00:00:03+00:00",
                "thread": "Research overview",
                "error": "timeout",
            },
            {
                "type": "done",
                "ts": "2026-05-29T00:00:04+00:00",
                "duration_ms": 5000,
            },
        ],
    )

    stats = trader_stats.parse_progress_stats(progress_path)

    assert stats["token_usage"]["input_tokens"] == 110
    assert stats["token_usage"]["output_tokens"] == 70
    assert stats["token_usage"]["cache_creation_input_tokens"] == 330
    assert stats["token_usage"]["cache_read_input_tokens"] == 740
    assert stats["token_usage"]["total_tokens"] == 1250
    assert stats["cost_usd"] == 0.35
    assert stats["wall_duration_ms"] == 5000
    assert stats["failed_sections"] == [
        {"thread": "Research overview", "error": "timeout"}
    ]
    assert stats["token_usage"]["by_thread"][0]["thread"] == "Price & returns"


def test_record_trader_refresh_appends_diff_history(tmp_data):
    progress_path = tmp_data / "_trader" / "amd__snapshot.progress.jsonl"
    _write_jsonl(
        progress_path,
        [
            {
                "type": "claude_action",
                "ts": "2026-05-29T00:00:01+00:00",
                "action": "result",
                "thread": "Price & returns",
                "cost_usd": 0.12,
                "duration_ms": 1000,
                "usage": {"input_tokens": 5, "output_tokens": 7},
            }
        ],
    )
    previous = {
        "refreshed_at": "2026-05-28T00:00:00+00:00",
        "price_card": {"last_price": 100, "change_pct_30d": 2.0},
        "momentum_card": {"trend_en": "Neutral", "above_50dma": False},
        "catalysts": [{"date": "2026-06-01", "title_en": "Old event"}],
    }
    new = {
        "refreshed_at": "2026-05-29T00:00:00+00:00",
        "schema_version": 2,
        "generation_duration_ms": 1500,
        "price_card": {"last_price": 112, "change_pct_30d": 8.5},
        "momentum_card": {"trend_en": "Bullish", "above_50dma": True},
        "catalysts": [{"date": "2026-06-10", "title_en": "New event"}],
    }

    record = trader_stats.record_trader_refresh(
        company_id="amd",
        company={"id": "amd", "name": "Advanced Micro Devices", "ticker": "AMD"},
        previous_snapshot=previous,
        new_snapshot=new,
        progress_path=progress_path,
        duration_ms=1500,
    )
    history = trader_stats.read_history("amd", limit=5)

    assert history[0]["refreshed_at"] == "2026-05-29T00:00:00+00:00"
    assert record["token_usage"]["total_tokens"] == 12
    assert record["change_summary"]["has_previous"] is True
    assert "price_card" in record["change_summary"]["changed_sections"]
    assert any(
        item.startswith("Last price: 100 -> 112")
        for item in record["change_summary"]["highlights"]
    )


def test_dashboard_seeds_baseline_from_existing_progress(tmp_data):
    progress_path = tmp_data / "_trader" / "amd__snapshot.progress.jsonl"
    _write_jsonl(
        progress_path,
        [
            {
                "type": "claude_action",
                "ts": "2026-05-29T00:00:01+00:00",
                "action": "result",
                "thread": "Momentum",
                "cost_usd": 0.2,
                "duration_ms": 1000,
                "usage": {
                    "input_tokens": 100,
                    "cache_read_input_tokens": 400,
                    "output_tokens": 50,
                },
            },
            {
                "type": "done",
                "ts": "2026-05-29T00:00:03+00:00",
                "duration_ms": 3000,
                "refreshed_at": "2026-05-29T00:00:00+00:00",
            },
        ],
    )
    companies = [
        {
            "id": "amd",
            "name": "Advanced Micro Devices",
            "ticker": "AMD",
            "company_type": "public",
            "trader_snapshot": {
                "refreshed_at": "2026-05-29T00:00:00+00:00",
                "price_card": {"last_price": 112},
            },
        }
    ]

    dashboard = trader_stats.build_dashboard(companies, limit=5)
    second_dashboard = trader_stats.build_dashboard(companies, limit=5)

    latest = dashboard["items"][0]["latest_record"]
    assert dashboard["totals"]["baseline_records_created"] == 1
    assert second_dashboard["totals"]["baseline_records_created"] == 0
    assert latest["status"] == "baseline"
    assert latest["change_summary"]["baseline"] is True
    assert latest["token_usage"]["total_tokens"] == 550
