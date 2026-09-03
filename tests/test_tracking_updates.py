"""Tests for tracked-company news updates."""
from __future__ import annotations

from server import storage, tracking_updates


def test_fingerprint_dedupes_same_url(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    a = tracking_updates.fingerprint({"url": "https://example.com/a", "title": "One"})
    b = tracking_updates.fingerprint({"url": "https://example.com/a", "title": "Different"})
    assert a == b


def test_classify_impact_levels():
    assert tracking_updates.classify_impact({"title": "Company raises Series B"}) == "high"
    assert tracking_updates.classify_impact({"title": "New product launch"}) == "medium"
    assert tracking_updates.classify_impact({"title": "Industry conference appearance"}) == "low"


def test_sync_from_news_feed_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar raises Series B financing",
                "summary": "Funding news",
                "url": "https://example.com/zainar-series-b",
                "published_at": "2026-01-01",
                "tags": ["funding"],
            }
        ],
    )
    first = tracking_updates.sync_from_news_feed(company_id, mark_auto=True)
    second = tracking_updates.sync_from_news_feed(company_id, mark_auto=True)
    assert first["created"] >= 1
    assert second["created"] == 0
    assert first["recommended_auto_run"]["action"] in {
        tracking_updates.ACTION_REPORT,
        tracking_updates.ACTION_INVESTIGATE,
    }
    listed = tracking_updates.list_updates(company_id)
    assert listed["counts"]["total"] >= 1
    assert listed["latest_auto_run"]


def test_remove_from_watchlist(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    company_id = "zainar-inc"
    tracking_updates.sync_watchlist([company_id, "other-co"])
    tracking_updates.remove_from_watchlist(company_id)
    assert company_id not in tracking_updates.get_watchlist()
    assert "other-co" in tracking_updates.get_watchlist()


def test_delete_company_removes_from_index(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    assert storage.get_company(company_id) is not None
    assert storage.delete_company(company_id) is True
    assert storage.get_company(company_id) is None


def test_watchlist_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    payload = tracking_updates.sync_watchlist(["alpha-co", "beta-co", "alpha-co"])
    assert payload["company_ids"] == ["alpha-co", "beta-co"]
    assert tracking_updates.get_watchlist() == ["alpha-co", "beta-co"]


def test_execute_auto_run_skips_when_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar launches new product",
                "summary": "Product news",
                "url": "https://example.com/zainar-product",
                "published_at": "2026-01-02",
                "tags": ["product"],
            }
        ],
    )
    tracking_updates.sync_from_news_feed(company_id, mark_auto=True)
    storage.create_report(
        company_id=company_id,
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(
        storage.list_reports()[-1]["id"],
        status="analyzing",
    )
    result = tracking_updates.execute_auto_run(company_id)
    assert result["executed"] is False
    assert result["reason"] == "company_busy"


def test_execute_auto_run_investigate(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar launches new product",
                "summary": "Product news",
                "url": "https://example.com/zainar-product-2",
                "published_at": "2026-01-03",
                "tags": ["product"],
            }
        ],
    )
    sync = tracking_updates.sync_from_news_feed(company_id, mark_auto=True)
    auto_run_id = sync["recommended_auto_run"]["id"]

    def _fake_start(company, tool_name):
        assert tool_name == "strategic_risk_mapper"
        return {"id": "sess-1", "tools": []}

    monkeypatch.setattr(
        "server.serena_analysis.start_analysis_tool_job",
        _fake_start,
    )
    executed = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert executed["executed"] is True
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "running"
    assert latest["job_ref"]["tool_name"] == "strategic_risk_mapper"


def test_complete_auto_run_for_job(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    tracking_updates.record_auto_run(
        company_id,
        action=tracking_updates.ACTION_INVESTIGATE,
        news_titles=["Launch headline"],
        status="running",
    )
    run_id = tracking_updates.list_updates(company_id)["latest_auto_run"]["id"]
    tracking_updates._patch_auto_run(
        company_id,
        run_id,
        {
            "status": "running",
            "job_ref": {"kind": "serena_tool", "tool_name": "strategic_risk_mapper"},
        },
    )
    finished = tracking_updates.complete_auto_run_for_job(
        company_id,
        job_kind="serena_tool",
        tool_name="strategic_risk_mapper",
        success=True,
    )
    assert finished["status"] == "completed"
    assert "Deep investigate refreshed" in finished["label"]


def test_complete_auto_run_for_memo_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    tracking_updates.record_auto_run(
        company_id,
        action=tracking_updates.ACTION_REPORT,
        news_titles=["Series B"],
        status="running",
    )
    run_id = tracking_updates.list_updates(company_id)["latest_auto_run"]["id"]
    tracking_updates._patch_auto_run(
        company_id,
        run_id,
        {
            "status": "running",
            "job_ref": {"kind": "memo_report", "report_id": "rep-1"},
        },
    )
    finished = tracking_updates.complete_auto_run_for_job(
        company_id,
        job_kind="memo_report",
        report_id="rep-1",
        success=False,
        error="Analysis worker crashed",
    )
    assert finished["status"] == "failed"
    assert finished["error"] == "Analysis worker crashed"


def test_refresh_company_news_soft_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"

    def _boom(*_args, **_kwargs):
        raise RuntimeError("claude unavailable")

    monkeypatch.setattr("server.companies_ai.deep_search", _boom)
    result = tracking_updates.refresh_company_news(company_id)
    assert result["refreshed"] is False
    assert "claude unavailable" in result["error"]


def test_sync_skips_refresh_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    called = {"n": 0}

    def _spy(*_args, **_kwargs):
        called["n"] += 1
        return {"matches": [], "source": "cache"}

    monkeypatch.setattr("server.companies_ai.deep_search", _spy)
    tracking_updates.sync_from_news_feed(company_id, refresh_news=False)
    assert called["n"] == 0
    tracking_updates.sync_from_news_feed(company_id, refresh_news=True)
    assert called["n"] == 1

