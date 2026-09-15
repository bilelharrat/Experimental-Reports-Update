"""Firm layer: comments/@mentions, chat, audit trail, transcripts, firm search and the transparent signal score."""
from __future__ import annotations

import io

from starlette.testclient import TestClient

from server import firm, firm_search, ic_room, portfolio, signal_score, storage, transcripts
from server.main import app

client = TestClient(app)


def _seed() -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private",
          "industry": "AI infrastructure", "description": "Vector database for agent developers, Series A"}],
    )


def test_comments_mentions_resolve_and_inbox():
    _seed()
    r = client.post("/api/companies/acme-ai/comments", json={"text": "@ana can you check the churn claim?", "target": {"kind": "section", "ref": "Risks", "label": "Risks"}})
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["mentions"] == ["ana"]
    assert item["target"]["kind"] == "section"
    reply = client.post("/api/companies/acme-ai/comments", json={"text": "on it", "parent_id": item["id"]}).json()
    assert reply["parent_id"] == item["id"]
    assert client.post("/api/companies/acme-ai/comments", json={"text": "x", "target": {"kind": "bogus"}}).status_code == 400

    inbox = firm.mentions_for("ana@firm.com")
    assert inbox["handle"] == "ana"
    assert inbox["open_count"] == 1
    assert client.post(f"/api/companies/acme-ai/comments/{item['id']}/resolve").json()["resolved_at"]
    assert firm.mentions_for("ana@firm.com")["open_count"] == 0
    listing = client.get("/api/companies/acme-ai/comments?open_only=true").json()
    assert [c["id"] for c in listing["items"]] == [reply["id"]]
    assert client.delete(f"/api/companies/acme-ai/comments/{item['id']}").status_code == 200
    assert client.get("/api/companies/acme-ai/comments").json()["items"] == []  # reply deleted with its parent


def test_chat_channels_since_and_mentions():
    _seed()
    m1 = client.post("/api/chat/general", json={"text": "Morning — @ben the Acme IC is at 3", "company_id": "acme-ai"}).json()
    assert m1["mentions"] == ["ben"]
    client.post("/api/chat/company:acme-ai", json={"text": "Deck v3 uploaded"})
    channels = client.get("/api/chat/channels").json()["items"]
    ids = {c["id"] for c in channels}
    assert {"general", "company:acme-ai"} <= ids
    company_channel = next(c for c in channels if c["id"] == "company:acme-ai")
    assert company_channel["label"] == "Acme AI"
    page = client.get("/api/chat/general").json()
    assert page["items"][-1]["id"] == m1["id"]
    seen = {m["id"] for m in page["items"]}
    assert {m["id"] for m in client.get(f"/api/chat/general?since={page['latest']}").json()["items"]} <= seen
    assert client.post("/api/chat/general", json={"text": "   "}).status_code == 400
    assert firm.mentions_for("ben@firm.com")["items"][0]["kind"] == "chat"


def test_audit_trail_records_mutations_with_company():
    _seed()
    client.put("/api/portfolio/acme-ai/position", json={"round": "Seed"})
    client.get("/api/portfolio/acme-ai")  # reads are not audited
    rows = client.get("/api/audit?company_id=acme-ai").json()["items"]
    assert rows, "expected an audit row"
    assert rows[0]["path"].endswith("/portfolio/acme-ai/position")
    assert rows[0]["status"] == 200
    assert rows[0]["action"].startswith("update portfolio/")
    assert all(r["path"] != "/api/portfolio/acme-ai" for r in rows)


def test_transcripts_normalize_vtt_and_highlights():
    _seed()
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\nHost: Thanks for joining.\n\n2\n00:00:04.000 --> 00:00:09.000\nExpert: Churn at Acme is closer to 4% monthly.\n[00:12] Actually 4 to 5.\n"
    r = client.post("/api/transcripts/upload", files={"file": ("call.vtt", io.BytesIO(vtt.encode()), "text/vtt")},
                    data={"title": "Expert call — ex-VP Sales", "kind": "expert_call", "company_id": "acme-ai", "tags": "churn, sales"})
    assert r.status_code == 200, r.text
    item = r.json()
    assert "-->" not in item["text"]
    assert "00:12" not in item["text"]
    assert "Churn at Acme is closer to 4% monthly" in item["text"]
    assert item["company_name"] == "Acme AI"
    assert item["tags"] == ["churn", "sales"]
    tid = item["id"]
    hl = client.post(f"/api/transcripts/{tid}/highlights", json={"text": "Churn at Acme is closer to 4% monthly", "note": "contradicts deck"}).json()
    assert hl["highlights"][0]["note"] == "contradicts deck"
    listing = client.get("/api/transcripts?q=churn&company_id=acme-ai").json()
    assert listing["count"] == 1 and listing["items"][0]["highlight_count"] == 1
    assert client.get("/api/transcripts?q=nothingmatches").json()["count"] == 0
    assert client.post("/api/transcripts", json={"title": "empty", "text": "   "}).status_code == 400
    assert client.delete(f"/api/transcripts/{tid}").status_code == 200
    assert client.get(f"/api/transcripts/{tid}").status_code == 404


def test_firm_search_spans_sources_with_excerpts():
    _seed()
    from server import decisions_store

    decisions_store.add_decision("acme-ai", verdict="pass", explanation="Passed because churn was far above plan.")
    ic_room.add_reference_call("acme-ai", {"contact": "Lee", "relation": "customer", "concerns": ["Churn risk after the price change"]})
    portfolio.add_update("acme-ai", text="Monthly churn improved to 2%. ARR $1.1M.", as_of="2026-08-01", subject="August")
    transcripts.add_transcript(title="Expert on churn", text="Speaker: The churn problem was structural.", kind="expert_call", company_id="acme-ai")
    firm.post_message("general", text="Did anyone dig into Acme churn?", author="ana@firm.com", company_id="acme-ai")
    firm_search.invalidate()
    out = client.get("/api/firm/search?q=churn").json()
    kinds = {i["kind"] for i in out["items"]}
    assert {"decision", "reference_call", "founder_update", "transcript", "chat"} <= kinds, kinds
    assert all("churn" in i["excerpt"].lower() for i in out["items"])
    only = client.get("/api/firm/search?q=churn&kinds=decision").json()
    assert {i["kind"] for i in only["items"]} == {"decision"}
    assert client.get("/api/firm/search?q=").json()["items"] == []


def test_signal_score_is_transparent_and_skips_missing_components():
    _seed()
    base = signal_score.compute("acme-ai")
    assert base["score"] is None or base["max_available"] <= 30
    names = [c["name"] for c in base["components"]]
    assert names == ["Thesis fit", "Evidence", "Memo", "Reference calls", "KPI momentum", "IC votes"]
    assert all(c["formula"] for c in base["components"])

    ic_room.add_reference_call("acme-ai", {"contact": "A", "relation": "customer", "rating": 4})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-03-31", "arr_usd": 1_000_000})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-06-30", "arr_usd": 1_500_000})
    meeting = ic_room.open_meeting("acme-ai")
    ic_room.cast_vote("acme-ai", meeting["id"], member="ana", vote="invest")
    ic_room.cast_vote("acme-ai", meeting["id"], member="ben", vote="pass")
    out = client.get("/api/companies/acme-ai/signal-score").json()
    comp = {c["name"]: c for c in out["components"]}
    assert comp["Reference calls"]["points"] == 12.0
    assert comp["KPI momentum"]["points"] == 5.0
    assert comp["IC votes"]["points"] == 5.0
    assert comp["Memo"]["available"] is False
    expected_max = sum(c["max"] for c in out["components"] if c["available"])
    assert out["max_available"] == expected_max
    assert out["score"] == round(out["points"] / expected_max * 100)
