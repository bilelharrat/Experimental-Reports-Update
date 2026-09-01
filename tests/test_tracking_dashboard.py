from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server import (
    evidence_matrix,
    serena_analysis,
    storage,
    tracking_dashboard,
)
from server.main import app


COMPANY_ID = "generalist-inc"
OTHER_ID = "quiet-co"


def _iso(offset_days: int = 0) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(days=offset_days)
    return stamp.isoformat().replace("+00:00", "Z")


@pytest.fixture
def seeded():
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": COMPANY_ID,
                "name": "Generalist, Inc.",
                "status": "private",
                "company_type": "private",
                "industry": "Industrial AI",
                "description": "A robotics software company.",
            },
            {
                "id": OTHER_ID,
                "name": "Quiet Co",
                "status": "private",
                "company_type": "private",
                "industry": "Logistics",
                "description": "A logistics company.",
            },
        ],
    )
    return storage.list_companies()


@pytest.fixture
def no_evidence(monkeypatch):
    """Default the evidence matrix to empty so tests opt into claims."""
    monkeypatch.setattr(
        evidence_matrix,
        "build_company_evidence_matrix",
        lambda company_id: {"company_id": company_id, "claims": [], "claim_count": 0},
    )


def _stub_claims(monkeypatch, statuses: dict[str, list[str]]):
    def fake(company_id: str) -> dict:
        claims = [
            {"claim": f"{company_id} claim {index}", "status": status}
            for index, status in enumerate(statuses.get(company_id, []))
        ]
        return {"company_id": company_id, "claims": claims, "claim_count": len(claims)}

    monkeypatch.setattr(evidence_matrix, "build_company_evidence_matrix", fake)


def _rollup(*company_ids: str) -> dict:
    return tracking_dashboard.build_rollup(list(company_ids))


def _row(rollup: dict, company_id: str) -> dict:
    return next(row for row in rollup["companies"] if row["id"] == company_id)


def _kinds(row: dict) -> set[str]:
    return {item["kind"] for item in row["attention"]}


def test_rollup_flags_failed_memo_as_high_severity(seeded, no_evidence):
    storage.create_report_record(
        company_id=COMPANY_ID,
        company_name="Generalist, Inc.",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="failed_quality_gate",
        failure_detail="Chinese parity check failed.",
        created_at=_iso(1),
        updated_at=_iso(1),
    )

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["memo"]["latest_status"] == "failed_quality_gate"
    assert row["memo"]["failed"] == 1
    failure = next(i for i in row["attention"] if i["kind"] == "memo_failed")
    assert failure["severity"] == "high"
    assert failure["detail"] == "Chinese parity check failed."
    assert failure["route"] == {
        "name": "research",
        "params": {"companyId": COMPANY_ID},
        "query": {"tab": "memo"},
    }
    assert row["bucket"] == "needs_action"
    assert row["next_action"]["kind"] == "memo_failed"
    assert row["next_action"]["label"] == "Resume failed memo"


def test_rollup_counts_open_risks_from_the_analysis_session(seeded, no_evidence):
    serena_analysis.run_tool(COMPANY_ID, "strategic_risk_mapper")

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["risks"]["total"] > 0
    assert row["risks"]["unresearched"] == row["risks"]["total"]
    assert row["risks"]["researched"] == 0
    risk_item = next(i for i in row["attention"] if i["kind"] == "risks_open")
    assert str(row["risks"]["unresearched"]) in risk_item["label"]


def test_unrecognized_risk_status_counts_as_open_work(seeded, no_evidence):
    serena_analysis.run_tool(COMPANY_ID, "strategic_risk_mapper")
    session = serena_analysis._strip_decorations(
        serena_analysis.get_current_session(COMPANY_ID, create=True)
    )
    for risk in session["artifacts"]["strategic_risks"]["risks"]:
        risk["status"] = "in_flight"
    serena_analysis._write_session(session)

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["risks"]["researched"] == 0
    assert row["risks"]["unresearched"] == row["risks"]["total"]


def test_high_severity_open_risk_escalates_the_attention_item(seeded, no_evidence):
    serena_analysis.run_tool(COMPANY_ID, "strategic_risk_mapper")
    session = serena_analysis._strip_decorations(
        serena_analysis.get_current_session(COMPANY_ID, create=True)
    )
    risks = session["artifacts"]["strategic_risks"]["risks"]
    for risk in risks:
        risk["status"] = "researched"
        risk["severity"] = "medium"
    risks[0]["status"] = "unresearched"
    risks[0]["severity"] = "high"
    serena_analysis._write_session(session)

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["risks"]["high_severity_open"] == 1
    risk_item = next(i for i in row["attention"] if i["kind"] == "risks_open")
    assert risk_item["severity"] == "high"


def test_contradicted_and_missing_evidence_surface_separately(seeded, monkeypatch):
    _stub_claims(
        monkeypatch,
        {COMPANY_ID: ["contradicted", "missing", "missing", "supported"]},
    )

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["evidence"]["contradicted"] == 1
    assert row["evidence"]["missing"] == 2
    assert row["evidence"]["supported"] == 1
    assert row["evidence"]["total"] == 4
    contradicted = next(
        i for i in row["attention"] if i["kind"] == "evidence_contradicted"
    )
    assert contradicted["severity"] == "high"
    assert contradicted["label"] == "1 contradicted claim"
    # Missing evidence stays in the counts, but the queue only keeps the
    # one next action — contradicted claims outrank a coverage gap.
    assert "evidence_missing" not in _kinds(row)
    assert row["next_action"]["kind"] == "evidence_contradicted"


def test_company_with_no_work_is_not_started_not_an_alert(seeded, no_evidence):
    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["attention"] == []
    assert row["bucket"] == "not_started"
    assert row["next_action"]["kind"] == "start_investigation"
    assert row["session"] is None
    assert row["last_activity_at"] is None


def test_healthy_company_produces_no_attention_items(seeded, monkeypatch):
    _stub_claims(monkeypatch, {COMPANY_ID: ["supported", "supported"]})
    storage.create_report_record(
        company_id=COMPANY_ID,
        company_name="Generalist, Inc.",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="complete",
        created_at=_iso(1),
        updated_at=_iso(1),
    )
    serena_analysis.run_tool(COMPANY_ID, "strategic_risk_mapper")
    session = serena_analysis._strip_decorations(
        serena_analysis.get_current_session(COMPANY_ID, create=True)
    )
    session["approved_for_memo"] = True
    for risk in session["artifacts"]["strategic_risks"]["risks"]:
        risk["status"] = "researched"
    serena_analysis._write_session(session)

    rollup = _rollup(COMPANY_ID)
    row = _row(rollup, COMPANY_ID)

    assert row["attention"] == []
    assert row["bucket"] == "clear"
    assert row["next_action"] is None
    assert rollup["totals"]["clear_company_count"] == 1
    assert rollup["totals"]["attention_count"] == 0


def test_completed_memo_without_a_risk_map_is_not_an_alert(seeded, no_evidence):
    storage.create_report_record(
        company_id=COMPANY_ID,
        company_name="Generalist, Inc.",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="complete",
        created_at=_iso(1),
        updated_at=_iso(1),
    )

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["attention"] == []
    assert row["bucket"] == "clear"
    assert row["next_action"] is None
    assert row["risks"]["total"] == 0


def test_attention_items_are_capped_per_company(seeded, monkeypatch):
    _stub_claims(monkeypatch, {COMPANY_ID: ["contradicted", "missing"]})
    storage.create_report_record(
        company_id=COMPANY_ID,
        company_name="Generalist, Inc.",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="failed_during_analysis",
        created_at=_iso(1),
        updated_at=_iso(1),
    )
    serena_analysis.run_tool(COMPANY_ID, "strategic_risk_mapper")

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert len(row["attention"]) == 1
    assert row["attention"][0]["kind"] == "memo_failed"
    assert row["next_action"]["kind"] == "memo_failed"


def test_companies_sort_worst_first(seeded, monkeypatch):
    _stub_claims(monkeypatch, {})
    storage.create_report_record(
        company_id=OTHER_ID,
        company_name="Quiet Co",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="failed_scope_check",
        created_at=_iso(2),
        updated_at=_iso(2),
    )

    rollup = _rollup(COMPANY_ID, OTHER_ID)

    assert [row["id"] for row in rollup["companies"]] == [OTHER_ID, COMPANY_ID]
    assert rollup["attention"][0]["severity"] == "high"
    assert rollup["totals"]["failed_memo_count"] == 1
    assert rollup["totals"]["needs_action_count"] == 1
    assert rollup["totals"]["not_started_count"] == 1
    assert rollup["totals"]["company_count"] == 2


def test_unknown_ids_are_reported_without_failing_the_request(seeded, no_evidence):
    rollup = _rollup(COMPANY_ID, "ghost-co")

    assert rollup["unknown_company_ids"] == ["ghost-co"]
    assert [row["id"] for row in rollup["companies"]] == [COMPANY_ID]


def test_rollup_does_not_create_analysis_sessions(seeded, no_evidence):
    """Opening the dashboard must stay read-only.

    ``get_current_session(create=True)`` writes a session file, so a
    careless read here would mint an empty draft for every followed
    company just because the page loaded.
    """
    _rollup(COMPANY_ID, OTHER_ID)

    assert not serena_analysis.ANALYSIS_ROOT.exists()


def test_price_block_is_none_without_a_trader_snapshot(seeded, no_evidence):
    row = _row(_rollup(COMPANY_ID), COMPANY_ID)
    assert row["price"] is None


def test_price_block_carries_relative_performance(seeded, no_evidence):
    storage.update_company(
        COMPANY_ID,
        trader_snapshot={
            "price_card": {
                "last_price": 101.5,
                "currency": "USD",
                "change_pct_1d": 1.2,
                "change_pct_30d": -4.0,
                "vs_sp500_30d_pct": -6.5,
                "as_of": _iso(0),
            }
        },
    )

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["price"]["change_pct_1d"] == 1.2
    assert row["price"]["vs_sp500_30d_pct"] == -6.5
    assert row["price"]["currency"] == "USD"


def test_idle_completed_memo_stays_clear(seeded, no_evidence):
    storage.create_report_record(
        company_id=COMPANY_ID,
        company_name="Generalist, Inc.",
        report_type="Investment Memo (Late-Stage)",
        kind="investment_memo_latestage",
        status="complete",
        created_at=_iso(120),
        updated_at=_iso(120),
    )

    row = _row(_rollup(COMPANY_ID), COMPANY_ID)

    assert row["bucket"] == "clear"
    assert row["attention"] == []
    assert "stale" not in _kinds(row)


def test_endpoint_accepts_repeated_and_comma_joined_ids(seeded, no_evidence):
    client = TestClient(app)

    repeated = client.get(
        "/api/tracking/rollup",
        params=[("company_id", COMPANY_ID), ("company_id", OTHER_ID)],
    )
    joined = client.get(
        "/api/tracking/rollup", params={"company_id": f"{COMPANY_ID},{OTHER_ID}"}
    )

    assert repeated.status_code == 200
    assert joined.status_code == 200
    assert {row["id"] for row in repeated.json()["companies"]} == {COMPANY_ID, OTHER_ID}
    assert repeated.json()["companies"] == joined.json()["companies"]


def test_endpoint_returns_an_empty_rollup_without_ids(seeded, no_evidence):
    client = TestClient(app)

    payload = client.get("/api/tracking/rollup").json()

    assert payload["companies"] == []
    assert payload["attention"] == []
    assert payload["totals"]["company_count"] == 0


def test_duplicate_ids_are_collapsed(seeded, no_evidence):
    rollup = _rollup(COMPANY_ID, COMPANY_ID, COMPANY_ID)
    assert len(rollup["companies"]) == 1
