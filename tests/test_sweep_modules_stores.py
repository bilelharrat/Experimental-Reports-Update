"""Store safety and validation: deal pipeline, cap model, comps peers, signal ledger, IC room, portfolio inputs, signal score, filings."""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml
from starlette.testclient import TestClient

from server import cap_model, comps, deal_pipeline, decisions_store, desk_store, filings_watch, ic_room, portfolio, signal_score, storage
from server.main import app

client = TestClient(app)


def _seed(*companies: dict) -> None:
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private", "industry": "AI infrastructure"},
        *companies,
    ])


# ---- Deal pipeline ---------------------------------------------------------------------------


def _pipeline_file(company_id: str):
    return storage.DATA_DIR / "deal_pipeline" / f"{company_id}.json"


def test_deal_pipeline_get_never_writes_and_keeps_a_half_written_file():
    _seed()
    assert client.get("/api/companies/acme-ai/deal-pipeline").json()["stage"] == "Sourced"
    assert not _pipeline_file("acme-ai").exists()
    client.put("/api/companies/acme-ai/deal-pipeline", json={"stage": "Term Sheet / IC", "deal_lead": "ana"})
    _pipeline_file("acme-ai").write_text("", encoding="utf-8")
    fallback = client.get("/api/companies/acme-ai/deal-pipeline").json()
    assert fallback["stage"] == "Sourced" and fallback["deal_lead"] is None
    assert _pipeline_file("acme-ai").read_text(encoding="utf-8") == ""
    assert client.get("/api/companies/ghost/deal-pipeline").status_code == 404
    assert not _pipeline_file("ghost").exists()


def test_deal_pipeline_days_in_stage_comes_from_stage_change_time():
    _seed()
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    _pipeline_file("acme-ai").parent.mkdir(parents=True, exist_ok=True)
    _pipeline_file("acme-ai").write_text(json.dumps({"stage": "Partner Intro", "stage_changed_at": ten_days_ago, "updated_at": ten_days_ago}), encoding="utf-8")
    assert client.get("/api/companies/acme-ai/deal-pipeline").json()["days_in_stage"] == 10
    same = client.put("/api/companies/acme-ai/deal-pipeline", json={"stage": "Partner Intro", "days_in_stage": "abc"}).json()
    assert same["days_in_stage"] == 10 and isinstance(same["days_in_stage"], int)
    moved = client.put("/api/companies/acme-ai/deal-pipeline", json={"stage": "Technical Diligence"}).json()
    assert moved["days_in_stage"] == 0
    legacy = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _pipeline_file("acme-ai").write_text(json.dumps({"stage": "Sourced", "updated_at": legacy, "days_in_stage": 0}), encoding="utf-8")
    assert client.get("/api/companies/acme-ai/deal-pipeline").json()["days_in_stage"] == 3


def test_deal_pipeline_validates_every_field_and_the_company():
    _seed()
    for bad in ({"warmth_score": 72.5}, {"warmth_score": True}, {"warmth_score": "hot"}, {"days_in_stage": None, "deal_lead": {"x": 1}}, {"next_step": ["a"]}):
        assert client.put("/api/companies/acme-ai/deal-pipeline", json=bad).status_code == 400, bad
    assert client.put("/api/companies/acme-ai/deal-pipeline", json={"warmth_score": 85.0, "deal_lead": " ana "}).json()["warmth_score"] == 85
    assert client.put("/api/companies/nope/deal-pipeline", json={"stage": "Sourced"}).status_code == 404
    assert not _pipeline_file("nope").exists()
    with pytest.raises(LookupError):
        deal_pipeline.require_company("nope")
    _pipeline_file("acme-ai").write_text(json.dumps({"stage": "Moon", "warmth_score": "hot", "days_in_stage": None, "deal_lead": 5}), encoding="utf-8")
    cleaned = client.get("/api/companies/acme-ai/deal-pipeline").json()
    assert (cleaned["stage"], cleaned["warmth_score"], cleaned["days_in_stage"], cleaned["deal_lead"]) == ("Sourced", None, 0, None)


def test_deal_pipeline_survives_a_get_put_race():
    _seed()
    deal_pipeline.update_deal_pipeline("acme-ai", {"stage": "Term Sheet / IC", "deal_lead": "lead"})
    errors: list[str] = []

    def reader():
        for _ in range(150):
            if deal_pipeline.get_deal_pipeline("acme-ai")["deal_lead"] != "lead":
                errors.append("reset seen")

    def writer():
        for i in range(60):
            deal_pipeline.update_deal_pipeline("acme-ai", {"next_step": f"step {i}"})

    threads = [threading.Thread(target=t) for t in (reader, reader, writer, writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    final = deal_pipeline.get_deal_pipeline("acme-ai")
    assert final["deal_lead"] == "lead" and final["stage"] == "Term Sheet / IC"
    assert not list(_pipeline_file("acme-ai").parent.glob("*.tmp"))


# ---- Cap model -------------------------------------------------------------------------------


def test_cap_model_zero_preference_is_not_defaulted_to_1x():
    r = cap_model.compute({"pre_money_musd": 40, "new_money_musd": 10, "our_check_musd": 5, "liquidation_preference_x": 0, "exit_values_musd": [30]})
    assert r["liquidation_preference_x"] == 0
    row = r["waterfall"][0]
    assert row["our_proceeds_musd"] == 3.0 and row["multiple_on_check"] == 0.6 and row["converted"] is True


def test_cap_model_rejects_bad_inputs_and_refuses_to_overwrite_an_unreadable_file():
    _seed()
    for bad in ({"pre_money_musd": "nan"}, {"pre_money_musd": float("inf")}, {"new_money_musd": -1}, {"option_pool_pct_post": 250}, {"liquidation_preference_x": True}):
        with pytest.raises(ValueError):
            cap_model.save_inputs("acme-ai", bad)
    cap_model.save_inputs("acme-ai", {"pre_money_musd": 123, "new_money_musd": 45})
    path = cap_model._path("acme-ai")
    path.write_text("", encoding="utf-8")
    with pytest.raises(cap_model.CapModelUnreadable):
        cap_model.save_inputs("acme-ai", {"notes": "x"})
    assert path.read_text(encoding="utf-8") == ""
    assert cap_model.load_inputs("acme-ai")["pre_money_musd"] is None


def test_cap_model_concurrent_patches_keep_every_field():
    _seed()
    cap_model.save_inputs("acme-ai", {"pre_money_musd": 123, "new_money_musd": 45, "our_check_musd": 5})
    defaults_seen: list[int] = []

    def reader():
        for _ in range(100):
            if cap_model.load_inputs("acme-ai")["pre_money_musd"] is None:
                defaults_seen.append(1)

    def writer(n: int):
        for i in range(40):
            cap_model.save_inputs("acme-ai", {"notes": f"w{n}-{i}"})

    threads = [threading.Thread(target=reader), threading.Thread(target=reader), threading.Thread(target=writer, args=(1,)), threading.Thread(target=writer, args=(2,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = cap_model.load_inputs("acme-ai")
    assert not defaults_seen and (final["pre_money_musd"], final["new_money_musd"], final["our_check_musd"]) == (123, 45, 5)
    assert not list(cap_model._path("acme-ai").parent.glob("*.tmp"))


# ---- Comps peers -----------------------------------------------------------------------------


def test_comps_peer_saves_are_serialized_and_corrupt_files_are_moved_aside():
    companies = [{"id": f"co-{i}", "name": f"Co {i}", "status": "private"} for i in range(12)]
    _seed(*companies)
    threads = [threading.Thread(target=comps.save_peers, args=(f"co-{i}", [f"T{i}", "MSFT"])) for i in range(12) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    saved = yaml.safe_load(comps._peers_file().read_text(encoding="utf-8"))
    assert all(saved[f"co-{i}"] == [f"T{i}", "MSFT"] for i in range(12))
    assert not list(comps._peers_file().parent.glob("*.tmp"))
    comps._peers_file().write_text("key: [unclosed\n0X16", encoding="utf-8")
    assert comps.get_peers("acme-ai") == comps.default_peers_for(storage.get_company("acme-ai"))
    assert comps.save_peers("acme-ai", ["NVDA"]) == ["NVDA"]
    assert list(comps._peers_file().parent.glob("comps_peers.yaml.corrupt-*"))
    assert comps.get_peers("acme-ai") == ["NVDA"]


# ---- Signal ledger ---------------------------------------------------------------------------


def test_signal_ledger_reports_duplicates_and_keeps_reversals():
    first = desk_store.record_signal({"ticker": "spy", "direction": "bullish", "label": "probe", "price_at_signal": 500})
    assert first["deduplicated"] is False
    dup = desk_store.record_signal({"ticker": "SPY", "direction": "bullish", "label": "probe", "price_at_signal": 999})
    assert dup["deduplicated"] is True and dup["id"] == first["id"] and dup["price_at_signal"] == 500
    reversal = desk_store.record_signal({"ticker": "SPY", "direction": "bearish", "label": "probe", "price_at_signal": 999})
    assert reversal["deduplicated"] is False and reversal["id"] != first["id"]
    assert len(desk_store.list_signals()) == 2
    assert all("deduplicated" not in row for row in desk_store.list_signals())


# ---- IC room ---------------------------------------------------------------------------------


def test_ic_room_inputs_return_400_not_500():
    _seed()
    headers = {"content-type": "application/json"}
    assert client.post("/api/companies/acme-ai/reference-calls", content='{"contact":"A","relation":"customer","rating":1e400}', headers=headers).status_code == 400
    assert client.post("/api/companies/acme-ai/reference-calls", json={"contact": "A", "rating": 4.9}).status_code == 400
    assert client.post("/api/companies/acme-ai/reference-calls", json={"contact": "A", "rating": True}).status_code == 400
    assert client.post("/api/companies/acme-ai/reference-calls", json={"contact": "A", "call_date": "not-a-date"}).status_code == 400
    ok = client.post("/api/companies/acme-ai/reference-calls", json={"contact": "A", "rating": "4", "call_date": "2026-09-01"}).json()
    assert ok["items"][0]["rating"] == 4 and ok["items"][0]["call_date"] == "2026-09-01"
    mid = client.post("/api/companies/acme-ai/ic/meetings", json={}).json()["id"]
    assert client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/votes", content='{"member":"a","vote":"invest","conviction":1e400}', headers=headers).status_code == 400
    assert client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/votes", json={"member": "a", "vote": "invest", "conviction": 4.9}).status_code == 400


def test_ic_close_records_only_a_majority():
    _seed()
    mid = ic_room.open_meeting("acme-ai")["id"]
    for member, vote in (("a", "invest"), ("b", "invest"), ("c", "pass"), ("d", "more_work")):
        ic_room.cast_vote("acme-ai", mid, member=member, vote=vote)
    tally = ic_room.list_meetings("acme-ai")["items"][0]["tally"]
    assert tally["leading"] == "invest" and tally["majority"] is None and tally["tied"] is False
    r = client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/close", json={"record_decision": True})
    assert r.status_code == 400 and "No majority" in r.json()["detail"]
    assert decisions_store.list_decisions("acme-ai")["items"] == []
    ic_room.cast_vote("acme-ai", mid, member="c", vote="invest")
    assert ic_room.list_meetings("acme-ai")["items"][0]["tally"]["majority"] == "invest"
    closed = client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/close", json={"record_decision": True}).json()
    assert closed["decision_id"] and closed["outcome"]["majority"] == "invest"
    assert decisions_store.list_decisions("acme-ai")["items"][0]["verdict"] == "invest"


# ---- Portfolio ---------------------------------------------------------------------------------


def test_portfolio_rejects_non_finite_and_out_of_range_figures():
    _seed()
    headers = {"content-type": "application/json"}
    bad_kpis = ({"headcount": "inf"}, {"arr_usd": "nan"}, {"burn_usd_month": -50000}, {"headcount": 2.5}, {"runway_months": True})
    for row in bad_kpis:
        assert client.post("/api/portfolio/acme-ai/kpis", json={"as_of": "2026-09-01", **row}).status_code == 400, row
    assert client.post("/api/portfolio/acme-ai/kpis", content='{"as_of":"2026-09-01","runway_months":NaN}', headers=headers).status_code == 400
    assert client.post("/api/portfolio/acme-ai/kpis", content='{"as_of":"2026-09-01","cash_usd":Infinity}', headers=headers).status_code == 400
    for patch in ({"invested_usd": "1e309"}, {"ownership_pct": -50}, {"ownership_pct": 250}):
        assert client.put("/api/portfolio/acme-ai/position", json=patch).status_code == 400, patch
    assert client.post("/api/portfolio/acme-ai/marks", json={"value_usd": "Infinity", "basis": "manual"}).status_code == 400
    assert client.put("/api/portfolio/reserves", json={"fund_size_musd": 0}).status_code == 400
    assert client.put("/api/portfolio/reserves", json={"fund_size_musd": "nan"}).status_code == 400
    assert portfolio.get_portfolio("acme-ai")["kpi_count"] == 0
    burn_alert = [a for a in portfolio.alerts_for({"kpis": [{"as_of": "2026-09-01T00:00:00Z", "cash_usd": 1_000_000, "burn_usd_month": -50_000}]}) if a["kind"] == "runway"]
    assert burn_alert == []


def test_runway_alert_comes_from_the_latest_row_that_reports_it():
    _seed()
    portfolio.add_kpi("acme-ai", {"as_of": "2026-08-01", "runway_months": 5})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-09-01", "headcount": 30})
    kinds = {a["kind"]: a for a in portfolio.get_portfolio("acme-ai")["alerts"]}
    assert kinds["runway"]["severity"] == "high" and "2026-08-01" in kinds["runway"]["detail"]
    portfolio.add_kpi("acme-ai", {"as_of": "2026-09-15", "cash_usd": 20_000_000, "burn_usd_month": 1_000_000})
    assert "runway" not in {a["kind"] for a in portfolio.get_portfolio("acme-ai")["alerts"]}
    portfolio.add_kpi("acme-ai", {"as_of": "2026-10-01", "cash_usd": 8_600_000, "burn_usd_month": 1_000_000})
    runway = next(a for a in portfolio.get_portfolio("acme-ai")["alerts"] if a["kind"] == "runway")
    assert runway["severity"] == "high" and "8.6 months" in runway["label"]


def test_blended_moic_only_counts_positions_with_a_cost_basis():
    _seed({"id": "beta", "name": "Beta", "status": "private"})
    portfolio.update_position("acme-ai", {"invested_usd": 1_000_000})
    portfolio.add_mark("acme-ai", value_usd=2_000_000, basis="last_round")
    portfolio.add_mark("beta", value_usd=5_000_000, basis="manual")
    totals = portfolio.dashboard()["totals"]
    assert totals["marked_value_usd"] == 7_000_000 and totals["marked_count"] == 2
    assert totals["marked_moic"] == 2.0 and totals["marked_cost_usd"] == 1_000_000 and totals["marked_uncosted_count"] == 1


# ---- Signal score & filings ------------------------------------------------------------------


def test_signal_score_needs_more_than_one_component(monkeypatch):
    _seed()
    monkeypatch.setattr(signal_score.storage, "list_reports_for", lambda company_id: [{"company_id": "acme-ai", "status": "complete_with_warnings"}])
    out = signal_score.compute("acme-ai")
    assert out["score"] is None and out["provisional_score"] == 100 and out["sufficient_coverage"] is False
    assert out["note"] and out["max_available"] == 15
    assert client.get("/api/signal-watch").json()["flagged"] == []
    ic_room.add_reference_call("acme-ai", {"contact": "A", "relation": "customer", "rating": 5})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-03-31", "arr_usd": 1_000_000})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-06-30", "arr_usd": 2_000_000})
    out = signal_score.compute("acme-ai")
    assert out["sufficient_coverage"] is True and out["score"] == 100 and out["max_available"] == 40


def test_filings_watch_maps_share_class_tickers_to_the_sec_form():
    _seed({"id": "brk.b", "name": "Berkshire Hathaway", "status": "public", "ticker": "BRK.B"})

    def fetch(url, headers=None):
        if "company_tickers.json" in url:
            return {"0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"}}
        if "submissions/CIK0001067983" in url:
            return {"filings": {"recent": {"form": ["10-Q"], "filingDate": ["2026-09-01"], "accessionNumber": ["0001-26-1"], "primaryDocument": ["a.htm"], "primaryDocDescription": ["Q"]}}}
        return {}

    row = filings_watch.build(tickers=["BRK.B"], fetch=fetch, today=date(2026, 9, 13))["tickers"][0]
    assert row["ticker"] == "BRK.B" and row["cik"] == 1067983 and row["error"] is None and row["company_id"] == "brk.b"
    assert [f["form"] for f in row["filings"]] == ["10-Q"]
