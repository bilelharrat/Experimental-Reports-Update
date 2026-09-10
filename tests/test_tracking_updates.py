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



# ---- Decision retrospectives -----------------------------------------------


def _seed_high_impact_news(company_id: str = "zainar-inc") -> str:
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar raises Series C financing",
                "summary": "Large round at a step-up valuation",
                "url": "https://example.com/zainar-series-c",
                "published_at": "2026-02-01",
                "tags": ["funding"],
            }
        ],
    )
    return company_id


def test_retro_fires_on_new_impactful_news_with_decisions(monkeypatch):
    from server import claude_runner, decisions_store

    company_id = _seed_high_impact_news()
    decision = decisions_store.add_decision(
        company_id,
        verdict="pass",
        explanation="Valuation too rich.",
        created_by="b",
    )
    calls: list[dict] = []

    def fake_structured(**kw):
        # The Claude call must never run under the tracking lock.
        assert tracking_updates._LOCK.acquire(blocking=False)
        tracking_updates._LOCK.release()
        calls.append(kw)
        return (
            {
                "assessments": [
                    {
                        "decision_id": decision["id"],
                        "verdict": "looks_wrong",
                        "rationale_en": "The step-up round contradicts the pass.",
                        "rationale_zh": "新一轮溢价融资与放弃决策相悖。",
                        "news_ids": ["not-a-real-item", ],
                    },
                    {
                        "decision_id": "unknown-id",
                        "verdict": "still_right",
                        "rationale_en": "x",
                        "rationale_zh": "x",
                    },
                ]
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "run_structured_prompt", fake_structured)

    tracking_updates.sync_from_news_feed(company_id)

    assert len(calls) == 1
    assert "Valuation too rich." in calls[0]["user_prompt"]
    assert "Series C" in calls[0]["user_prompt"]
    stored = decisions_store.list_decisions(company_id)["items"][0]
    assert len(stored["retrospectives"]) == 1
    retro = stored["retrospectives"][0]
    assert retro["verdict"] == "looks_wrong"
    assert retro["rationale_zh"].startswith("新一轮")
    assert retro["news_ids"] == []  # unmatched ids dropped

    # Re-sync with no new items: no second call.
    tracking_updates.sync_from_news_feed(company_id)
    assert len(calls) == 1


def test_retro_skips_without_decisions_or_when_disabled(monkeypatch):
    from server import claude_runner, decisions_store

    company_id = _seed_high_impact_news()
    calls: list[dict] = []
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        claude_runner,
        "run_structured_prompt",
        lambda **kw: calls.append(kw) or ({"assessments": []}, None),
    )

    # No decisions recorded: never called.
    tracking_updates.sync_from_news_feed(company_id)
    assert calls == []

    decisions_store.add_decision(
        company_id, verdict="watch", explanation="Wait for Q3.", created_by="b"
    )
    # Kill switch: never called even with decisions + fresh impactful news.
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar announces acquisition",
                "summary": "M&A move",
                "url": "https://example.com/zainar-acquisition",
                "published_at": "2026-03-01",
                "tags": ["m&a"],
            }
        ],
    )
    monkeypatch.setenv("BSH_TRACKING_DECISION_RETRO", "0")
    tracking_updates.sync_from_news_feed(company_id)
    assert calls == []


def test_retro_failure_never_fails_the_sync(monkeypatch):
    from server import claude_runner, decisions_store

    company_id = _seed_high_impact_news()
    decisions_store.add_decision(
        company_id, verdict="invest", explanation="Strong team.", created_by="b"
    )
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)

    def _boom(**_kw):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(claude_runner, "run_structured_prompt", _boom)
    summary = tracking_updates.sync_from_news_feed(company_id)
    assert summary["created"] >= 1  # sync unaffected
    stored = decisions_store.list_decisions(company_id)["items"][0]
    assert stored["retrospectives"] == []
