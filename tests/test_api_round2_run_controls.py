"""POST /reports passes the run controls (pause after English, spend
ceiling) to the bootstrap, rejects a nonsense ceiling, and a run paused
after its English can be resumed."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import api, memo_analysis, memo_prep, storage
from server.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_caller_role", lambda request: "admin")
    monkeypatch.setattr(api, "_caller_email", lambda request: None)
    return TestClient(app)


def _fake_detail(r):
    return {
        "id": r["id"], "status": r["status"], "company_id": "zainar-inc", "company_name": "ZaiNar, Inc.",
        "report_type": "Investment Memo (Late-Stage)", "audience": "Internal", "language": "en",
        "created_at": "2026-09-23T00:00:00+00:00", "updated_at": "2026-09-23T00:00:00+00:00",
    }


BODY = {
    "company_id": "zainar-inc",
    "report_type": "Investment Memo (Late-Stage)",
    "audience": "Internal",
    "quality": "balanced",
}


def test_run_controls_reach_the_bootstrap(client, monkeypatch):
    seen: dict = {}

    def fake_bootstrap(company_id, **kwargs):
        seen.update(kwargs)
        return {"report_id": "r1", "report": {"id": "r1", "company_id": company_id, "status": "ready_for_analysis"}}

    monkeypatch.setattr(memo_prep, "bootstrap_memo_run", fake_bootstrap)
    monkeypatch.setattr(api, "_stamp_new_report", lambda report, request, **kw: report)
    monkeypatch.setattr(api, "_supersede_stale_memo_failures", lambda *a, **kw: None)
    monkeypatch.setattr(api, "_report_detail", _fake_detail)
    res = client.post("/api/reports", json={**BODY, "pause_after_english": True, "cost_ceiling_usd": 25})
    assert res.status_code == 201, res.text
    assert seen["pause_after_english"] is True
    assert seen["cost_ceiling_usd"] == 25


@pytest.mark.parametrize("ceiling", [0, -5, 5000])
def test_a_nonsense_ceiling_is_rejected(client, monkeypatch, ceiling):
    monkeypatch.setattr(memo_prep, "bootstrap_memo_run", lambda *a, **kw: pytest.fail("must not start"))
    res = client.post("/api/reports", json={**BODY, "cost_ceiling_usd": ceiling})
    assert res.status_code == 400
    assert "cost_ceiling_usd" in res.text


def test_a_paused_run_can_be_resumed(client, monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "memo_package.en.json").write_text("{}")
    report = {
        "id": "p1",
        "kind": "investment_memo_latestage",
        "status": "english_ready_paused",
        "run_dir": str(run_dir),
        "company_id": "zainar-inc",
    }
    updates: dict = {}
    monkeypatch.setattr(storage, "get_report", lambda rid: dict(report) if rid == "p1" else None)
    monkeypatch.setattr(api, "_memo_run_dir", lambda r: run_dir)
    monkeypatch.setattr(api, "_memo_stream_path_for_report", lambda rid: tmp_path / "none.jsonl")
    monkeypatch.setattr(api, "_scan_progress_state", lambda path: {"exists": False})

    def fake_update(rid, **fields):
        updates.update(fields)
        return {**report, **fields}

    monkeypatch.setattr(storage, "update_report", fake_update)
    started: list = []
    monkeypatch.setattr(memo_analysis, "start_resume", lambda rid: started.append(rid))
    monkeypatch.setattr(api, "_report_detail", _fake_detail)
    res = client.post("/api/reports/p1/resume")
    assert res.status_code == 202, res.text
    assert started == ["p1"]
    assert updates["resume_from_status"] == "english_ready_paused"
