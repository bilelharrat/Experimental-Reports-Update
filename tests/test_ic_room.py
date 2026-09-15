"""IC room: reference calls, votes → decision, comparables and the red-team job (runner stubbed)."""
from __future__ import annotations

from starlette.testclient import TestClient

from server import decisions_store, ic_room, red_team, storage
from server.main import app

client = TestClient(app)


def _seed() -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private",
             "industry": "AI infrastructure", "description": "Vector database for agent developers, Series A"},
            {"id": "vecto", "name": "Vecto", "status": "private", "company_type": "private",
             "industry": "AI infrastructure", "description": "Embedding database and retrieval for developers, Series A"},
            {"id": "fintech-co", "name": "Fintech Co", "status": "private", "company_type": "private",
             "industry": "Fintech", "description": "Payments for restaurants, seed"},
        ],
    )


def test_reference_calls_round_trip_and_validation():
    _seed()
    r = client.post("/api/companies/acme-ai/reference-calls", json={
        "contact": "Dana Q.", "relation": "customer", "rating": 4,
        "strengths": ["Fast onboarding", "Great support"], "concerns": "Pricing changed twice\nOccasional latency",
        "quotes": ["We'd renew."], "would_back_again": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["concerns"] == ["Pricing changed twice", "Occasional latency"]
    assert body["average_rating"] == 4
    assert client.post("/api/companies/acme-ai/reference-calls", json={"contact": "X", "relation": "cousin"}).status_code == 400
    assert client.post("/api/companies/acme-ai/reference-calls", json={"contact": "X", "rating": 9}).status_code == 400
    rid = body["items"][0]["id"]
    assert client.delete(f"/api/companies/acme-ai/reference-calls/{rid}").json()["count"] == 0
    assert client.delete(f"/api/companies/acme-ai/reference-calls/{rid}").status_code == 404


def test_ic_meeting_votes_tally_and_record_decision():
    _seed()
    r = client.post("/api/companies/acme-ai/ic/meetings", json={"title": "Acme IC"})
    assert r.status_code == 200, r.text
    meeting = r.json()
    mid = meeting["id"]
    # only one open meeting at a time
    assert client.post("/api/companies/acme-ai/ic/meetings", json={}).status_code == 409
    for member, vote, conv in (("ana", "invest", 4), ("ben", "invest", 3), ("cy", "pass", 5)):
        r = client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/votes", json={"member": member, "vote": vote, "conviction": conv})
        assert r.status_code == 200, r.text
    # re-vote overwrites
    client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/votes", json={"member": "cy", "vote": "more_work"})
    tally = client.get("/api/companies/acme-ai/ic/meetings").json()["items"][0]["tally"]
    assert (tally["invest"], tally["pass"], tally["more_work"], tally["leading"]) == (2, 0, 1, "invest")
    assert client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/votes", json={"member": "d", "vote": "maybe"}).status_code == 400

    r = client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/close", json={"record_decision": True})
    assert r.status_code == 200, r.text
    closed = r.json()
    assert closed["status"] == "closed"
    assert closed["decision_id"]
    latest = decisions_store.list_decisions("acme-ai")["items"][0]
    assert latest["verdict"] == "invest"
    assert "2 invest" in latest["explanation"]
    assert client.post(f"/api/companies/acme-ai/ic/meetings/{mid}/close", json={}).status_code == 400


def test_comparables_score_sector_stage_and_terms():
    _seed()
    decisions_store.add_decision("vecto", verdict="pass", explanation="Too early, no wedge")
    decisions_store.add_decision("fintech-co", verdict="invest", explanation="Great team")
    out = ic_room.comparable_decisions("acme-ai")
    assert out["items"], out
    top = out["items"][0]
    assert top["company_id"] == "vecto"
    assert top["decision"]["verdict"] == "pass"
    assert any(w.startswith("Same sector") for w in top["why"])
    assert any(w.startswith("Same stage") for w in top["why"])
    assert all(item["company_id"] != "fintech-co" for item in out["items"])


def test_red_team_prompt_and_stubbed_run():
    _seed()
    ic_room.add_reference_call("acme-ai", {"contact": "Lee", "relation": "former_employee", "concerns": ["Churn is higher than the deck says"]})
    prompt, provenance = red_team.build_prompt("acme-ai")
    assert "Churn is higher" in prompt
    assert provenance["reference_concerns"] == 1
    assert provenance["memo_package"] is None

    captured = {}

    def fake_runner(system_prompt, user_prompt, progress):
        captured["prompt"] = user_prompt
        return {
            "counter_thesis": "The wedge is a feature.",
            "kill_risks": [{"risk": "Incumbent bundling", "why": "Cloud vendors ship it free", "severity": "high", "evidence_needed": "Win rates vs pgvector", "memo_section": "Market"}],
            "questionable_assumptions": ["ARR growth continues"],
            "what_would_change_my_mind": ["Net retention above 120%"],
            "pre_mortem": "Bought by a hyperscaler for talent.",
            "questions_for_founders": ["Why did churn rise?"],
        }, None

    payload = red_team.run("acme-ai", requested_by="me", runner=fake_runner)
    assert payload["status"] == "done"
    assert "Churn is higher" in captured["prompt"]
    loaded = client.get("/api/companies/acme-ai/ic/red-team").json()
    assert loaded["status"] == "done"
    assert loaded["result"]["kill_risks"][0]["severity"] == "high"
    assert loaded["provenance"]["reference_concerns"] == 1
