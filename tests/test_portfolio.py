"""Private portfolio: founder-update KPIs, alerts, marks, reserves and LP tear sheets — record-backed only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from starlette.testclient import TestClient

from server import portfolio, storage
from server.main import app

client = TestClient(app)


def _seed() -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private"}],
    )


def test_founder_update_extracts_kpis_with_excerpts_and_flags_runway():
    _seed()
    text = (
        "Hi all — quick August update. ARR hit $1.2M this month, up from July. "
        "Net burn is $180k per month and we have about 7 months of runway. Cash balance $1.3M. "
        "Team is now 14 employees and we signed 3 new logos, 41 customers total."
    )
    out = portfolio.add_update("acme-ai", text=text, as_of="2026-08-31", subject="August update")
    assert out["update_count"] == 1
    kpi = out["latest_kpi"]
    assert kpi["arr_usd"] == 1_200_000
    assert kpi["burn_usd_month"] == 180_000
    assert kpi["runway_months"] == 7
    assert kpi["cash_usd"] == 1_300_000
    assert kpi["headcount"] == 14
    assert kpi["customers"] == 41
    assert kpi["source"].startswith("founder_update:")
    assert "runway" in kpi["excerpts"]["runway_months"].lower()
    kinds = {a["kind"]: a["severity"] for a in out["alerts"]}
    assert kinds["runway"] == "high"


def test_manual_kpis_burn_jump_and_stale_alerts():
    _seed()
    portfolio.add_kpi("acme-ai", {"as_of": "2026-03-31", "burn_usd_month": 100_000, "runway_months": 20})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-06-30", "burn_usd_month": 140_000, "runway_months": 14})
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    data = portfolio.dashboard(now=now)
    row = next(r for r in data["companies"] if r["company_id"] == "acme-ai")
    kinds = {a["kind"]: a for a in row["alerts"]}
    assert kinds["burn"]["label"] == "Burn up 40%"
    assert kinds["stale"]["severity"] == "low"
    assert "runway" not in kinds
    # a fresh data point clears staleness
    portfolio.add_kpi("acme-ai", {"as_of": (now - timedelta(days=3)).date().isoformat(), "headcount": 12})
    row = next(r for r in portfolio.dashboard(now=now)["companies"] if r["company_id"] == "acme-ai")
    assert "stale" not in {a["kind"] for a in row["alerts"]}


def test_position_marks_moic_reserves_and_tear_sheet():
    _seed()
    r = client.put("/api/portfolio/acme-ai/position", json={"round": "Seed", "invested_usd": 1_000_000, "ownership_pct": 8.5, "planned_follow_on_usd": 1_500_000})
    assert r.status_code == 200, r.text
    assert r.json()["position"]["ownership_pct"] == 8.5
    assert client.put("/api/portfolio/acme-ai/position", json={"bogus": 1}).status_code == 400

    r = client.post("/api/portfolio/acme-ai/marks", json={"value_usd": 2_500_000, "basis": "last_round", "as_of": "2026-07-01"})
    assert r.status_code == 200
    assert r.json()["moic"] == 2.5
    assert client.post("/api/portfolio/acme-ai/marks", json={"value_usd": 1, "basis": "vibes"}).status_code == 400

    r = client.put("/api/portfolio/reserves", json={"fund_size_musd": 50, "reserve_pct": 40})
    assert r.status_code == 200
    plan = r.json()
    assert plan["reserve_pool_usd"] == 20_000_000
    assert plan["planned_follow_on_usd"] == 1_500_000
    assert plan["remaining_usd"] == 18_500_000

    dash = client.get("/api/portfolio").json()
    assert dash["totals"]["invested_usd"] == 1_000_000
    assert dash["totals"]["marked_moic"] == 2.5

    r = client.get("/api/portfolio/acme-ai/tear-sheet.docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.content[:2] == b"PK"

    # deleting the update removes its derived KPI row too
    out = client.post("/api/portfolio/acme-ai/updates", json={"text": "Revenue was $400k this quarter.", "as_of": "2026-08-01"}).json()
    upd = out["updates"][0]
    assert upd["kpi_id"]
    r = client.delete(f"/api/portfolio/acme-ai/updates/{upd['id']}")
    assert r.status_code == 200
    assert all(k["id"] != upd["kpi_id"] for k in r.json()["kpis"])
    assert client.delete("/api/portfolio/acme-ai/updates/nope").status_code == 404
