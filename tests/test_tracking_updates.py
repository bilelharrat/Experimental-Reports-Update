"""Tests for tracked-company news updates."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server import storage, tracking_updates
from server.main import app


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


def _seed_recommended_run(company_id: str, *, title: str, url: str) -> str:
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": title,
                "summary": "News summary",
                "url": url,
                "published_at": "2026-01-05",
            }
        ],
    )
    sync = tracking_updates.sync_from_news_feed(company_id, mark_auto=True)
    return sync["recommended_auto_run"]["id"]


def test_list_updates_exposes_last_synced_at(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    assert tracking_updates.list_updates(company_id)["last_synced_at"] is None
    tracking_updates.sync_from_news_feed(company_id)
    assert tracking_updates.list_updates(company_id)["last_synced_at"]


def test_execute_report_action_passes_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar raises Series C financing",
        url="https://example.com/zainar-series-c",
    )
    captured: dict = {}

    def _fake_bootstrap(cid, **kwargs):
        captured["company_id"] = cid
        captured.update(kwargs)
        return {"report_id": "rep-42"}

    monkeypatch.setattr("server.memo_prep.bootstrap_memo_run", _fake_bootstrap)
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is True
    assert result["report_id"] == "rep-42"
    assert captured["trigger"] == "tracking_auto_run"
    assert captured["auto_run_id"] == auto_run_id


def test_execute_investigate_requires_parallel(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches new product",
        url="https://example.com/zainar-launch-parallel",
    )
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is False
    assert result["reason"] == "studio_requires_parallel"
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "recommended"


def test_execute_investigate_dispatches_studio(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches new product",
        url="https://example.com/zainar-launch-studio",
    )
    captured: dict = {}

    def _fake_bootstrap(cid, **kwargs):
        captured["company_id"] = cid
        captured.update(kwargs)
        return {"report_id": "rep-7"}

    monkeypatch.setattr("server.memo_prep.bootstrap_memo_run", _fake_bootstrap)
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is True
    assert result["report_id"] == "rep-7"
    assert captured["memo_mode"] == "studio"
    assert captured["trigger"] == "tracking_auto_run"
    assert captured["auto_run_id"] == auto_run_id
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "running"
    assert latest["job_ref"] == {"kind": "memo_report", "report_id": "rep-7"}


def test_execute_skips_while_studio_review_is_parked(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar raises Series D financing",
        url="https://example.com/zainar-series-d",
    )
    parked = storage.create_report(
        company_id=company_id,
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(
        parked["id"], status="awaiting_studio", kind="investment_memo_latestage"
    )

    # Both actions must skip while cards await review — an auto-run may
    # never snapshot-replace a human's in-progress edits.
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is False
    assert result["reason"] == "awaiting_studio_review"
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "recommended"

    # The human's acknowledgment bypasses the guard, and the new run
    # retires the parked record.
    monkeypatch.setattr(
        "server.memo_prep.bootstrap_memo_run",
        lambda cid, **kwargs: {"report_id": "rep-8"},
    )
    result = tracking_updates.execute_auto_run(
        company_id, auto_run_id, allow_parked_review=True
    )
    assert result["executed"] is True
    assert storage.get_report(parked["id"])["superseded_by"] == "rep-8"


def test_execute_skips_when_reserved_lane_full(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches partner network",
        url="https://example.com/zainar-partner",
    )
    monkeypatch.setattr(
        "server.memo_analysis.reserved_run_slots_available", lambda: False
    )
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is False
    assert result["reason"] == "run_slots_full"
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "recommended"


def test_dismissed_parked_run_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar raises Series E financing",
        url="https://example.com/zainar-series-e",
    )
    parked = storage.create_report(
        company_id=company_id,
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(
        parked["id"],
        status="awaiting_studio",
        kind="investment_memo_latestage",
        dismissed_at="2026-09-03T00:00:00Z",
    )
    monkeypatch.setattr(
        "server.memo_prep.bootstrap_memo_run",
        lambda cid, **kwargs: {"report_id": "rep-8"},
    )
    result = tracking_updates.execute_auto_run(company_id, auto_run_id)
    assert result["executed"] is True


# ---- Execute route --------------------------------------------------------


def test_execute_route_unknown_company_404(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    client = TestClient(app)
    response = client.post(
        "/api/companies/nope/tracking-updates/auto-runs/r1/execute"
    )
    assert response.status_code == 404


def test_execute_route_passes_through_domain_outcomes(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    client = TestClient(app)

    # Empty store / unknown auto_run_id → 200 with executed False.
    response = client.post(
        f"/api/companies/{company_id}/tracking-updates/auto-runs/r1/execute"
    )
    assert response.status_code == 200
    assert response.json() == {
        "executed": False,
        "reason": "no_recommended_auto_run",
    }

    # A live memo run makes the company busy.
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches new platform",
        url="https://example.com/zainar-platform",
    )
    report = storage.create_report(
        company_id=company_id,
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(report["id"], status="analyzing")
    response = client.post(
        f"/api/companies/{company_id}/tracking-updates/auto-runs/{auto_run_id}/execute"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is False
    assert body["reason"] == "company_busy"


def test_execute_route_launches_recommended_run(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches new product line",
        url="https://example.com/zainar-launch",
    )
    monkeypatch.setattr(
        "server.memo_prep.bootstrap_memo_run",
        lambda cid, **kwargs: {"report_id": "rep-99"},
    )
    client = TestClient(app)
    response = client.post(
        f"/api/companies/{company_id}/tracking-updates/auto-runs/{auto_run_id}/execute"
    )
    assert response.status_code == 200
    assert response.json()["executed"] is True
    latest = tracking_updates.list_updates(company_id)["latest_auto_run"]
    assert latest["status"] == "running"


def test_execute_route_accepts_review_acknowledgment(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    auto_run_id = _seed_recommended_run(
        company_id,
        title="ZaiNar launches new sensor",
        url="https://example.com/zainar-sensor",
    )
    parked = storage.create_report(
        company_id=company_id,
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(
        parked["id"], status="awaiting_studio", kind="investment_memo_latestage"
    )
    monkeypatch.setattr(
        "server.memo_prep.bootstrap_memo_run",
        lambda cid, **kwargs: {"report_id": "rep-10"},
    )
    client = TestClient(app)
    url = (
        f"/api/companies/{company_id}/tracking-updates"
        f"/auto-runs/{auto_run_id}/execute"
    )

    blocked = client.post(url)
    assert blocked.status_code == 200
    assert blocked.json()["reason"] == "awaiting_studio_review"

    acknowledged = client.post(url, json={"acknowledge_review": True})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["executed"] is True


def test_report_summary_exposes_tracking_provenance():
    from server import api

    plain = api._report_summary({"id": "r1", "report_type": "X"})
    assert plain["trigger"] is None
    assert plain["auto_run_id"] is None
    tagged = api._report_summary(
        {
            "id": "r2",
            "report_type": "X",
            "trigger": "tracking_auto_run",
            "auto_run_id": "ar-9",
        }
    )
    assert tagged["trigger"] == "tracking_auto_run"
    assert tagged["auto_run_id"] == "ar-9"

