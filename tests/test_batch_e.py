"""Unified profile, filings/earnings watch (stubbed fetch), signal watch, numbers lint and the MCP server."""
from __future__ import annotations

import json
from datetime import date

from starlette.testclient import TestClient

from server import decisions_store, filings_watch, mcp_server, numbers_lint, portfolio, signal_watch, storage
from server.main import app

client = TestClient(app)


def _seed() -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private",
             "industry": "AI infrastructure", "description": "Vector database for agent developers, Series A"},
            {"id": "snow", "name": "Snowflake", "status": "public", "company_type": "public", "ticker": "SNOW"},
        ],
    )


def test_unified_profile_merges_private_side_and_counts():
    _seed()
    portfolio.update_position("acme-ai", {"round": "Seed", "invested_usd": 500_000, "ownership_pct": 5})
    decisions_store.add_decision("acme-ai", verdict="invest", explanation="Team + wedge")
    r = client.get("/api/companies/acme-ai/profile?quote=false")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["is_public"] is False and p["public"] is None
    assert p["private"]["position"]["round"] == "Seed"
    assert p["latest_decision"]["verdict"] == "invest"
    assert p["counts"]["decisions"] == 1
    assert p["thesis_fit"]["fit"]
    assert client.get("/api/companies/nope/profile").status_code == 404


def test_filings_watch_with_stubbed_sources():
    _seed()
    today = date(2026, 9, 13)

    def fetch(url, headers=None):
        if "company_tickers.json" in url:
            return {"0": {"cik_str": 1640147, "ticker": "SNOW", "title": "Snowflake Inc."}}
        if "submissions/CIK0001640147" in url:
            return {"filings": {"recent": {
                "form": ["8-K", "10-Q", "4", "S-8"],
                "filingDate": ["2026-09-01", "2026-08-28", "2026-05-01", "2026-09-02"],
                "accessionNumber": ["0001-26-1", "0001-26-2", "0001-26-3", "0001-26-4"],
                "primaryDocument": ["a.htm", "b.htm", "c.xml", "d.htm"],
                "primaryDocDescription": ["Results", "Quarterly report", "Insider", "Plan"],
            }}}
        if "earnings-surprise" in url:
            return {"data": {"earningsSurpriseTable": {"rows": [{"fiscalQtrEnd": "Jul 2026", "dateReported": "08/27/2026", "eps": "0.3", "consensusForecast": "0.25", "percentageSurprise": "20"}]}}}
        return {}

    out = filings_watch.build(tickers=["SNOW", "ZZZZ"], fetch=fetch, today=today)
    snow = next(r for r in out["tickers"] if r["ticker"] == "SNOW")
    assert [f["form"] for f in snow["filings"]] == ["8-K", "10-Q"]  # S-8 not watched; Form 4 older than 90 days
    assert snow["filings"][0]["url"].endswith("/1640147/000126-1/a.htm".replace("000126-1", "0001261"))
    assert snow["material_count"] == 2
    assert snow["earnings"]["last_surprise_pct"] == 20.0
    assert snow["earnings"]["next_estimated"] is True
    zzz = next(r for r in out["tickers"] if r["ticker"] == "ZZZZ")
    assert "No CIK" in zzz["error"]
    assert out["material_filings"][0]["ticker"] == "SNOW"


def test_signal_watch_snapshots_and_flags_moves():
    _seed()
    from server import ic_room

    assert signal_watch.moves()["previous_snapshot_at"] is None
    # KPI momentum (flat ARR, 0/10) and IC votes (pass, 0/10) give 20 max points with no score contribution
    portfolio.add_kpi("acme-ai", {"as_of": "2026-03-31", "arr_usd": 1_000_000})
    portfolio.add_kpi("acme-ai", {"as_of": "2026-06-30", "arr_usd": 1_000_000})
    meeting = ic_room.open_meeting("acme-ai")
    ic_room.cast_vote("acme-ai", meeting["id"], member="ana", vote="pass")
    ic_room.add_reference_call("acme-ai", {"contact": "A", "relation": "customer", "rating": 3})  # 9/35 → 26
    snap = client.post("/api/signal-watch/snapshot").json()
    assert snap["company_count"] == 2
    ic_room.add_reference_call("acme-ai", {"contact": "B", "relation": "customer", "rating": 5})  # avg 4 → 12/35 → 34
    client.put("/api/signal-watch/settings", json={"up_threshold": 30, "down_threshold": 20, "min_delta": 5})
    out = client.get("/api/signal-watch").json()
    acme = next(i for i in out["items"] if i["company_id"] == "acme-ai")
    assert (acme["previous"], acme["score"], acme["delta"]) == (26, 34, 8)
    assert {"big_move", "crossed_up"} <= set(acme["flags"])
    assert out["flagged"][0]["company_id"] == "acme-ai"
    assert client.put("/api/signal-watch/settings", json={"up_threshold": 30, "down_threshold": 50}).status_code == 400
    assert client.put("/api/signal-watch/settings", json={"min_delta": 1}).json()["min_delta"] == 1.0


def test_numbers_lint_flags_unsupported_figures():
    blocks = [("Traction", "ARR reached $1.2M in Q2 with 41 customers and 130% net retention."), ("Round", "Raising $8M at a $40M post-money, 3.5x the last round.")]
    corpus = ["August update: ARR hit $1,200,000; we now serve 41 customers.", "Deck: raising eight million at a $40M post."]
    out = numbers_lint.lint_blocks(blocks, corpus)
    unsupported = {f["number"] for f in out["findings"]}
    assert "$1.2M" not in unsupported and "$40M" not in unsupported
    assert "130%" in unsupported and "$8M" in unsupported and "3.5x" in unsupported
    assert out["checked"] == 5 and out["supported"] == 2  # small integers (41) are not policed
    _seed()
    assert client.get("/api/companies/acme-ai/memo-number-lint").json()["memo_package"] is None


def test_mcp_server_handshake_and_tool_call():
    _seed()
    init = mcp_server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "bsh-research-center"
    assert mcp_server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = mcp_server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {"firm_search", "company_profile", "portfolio_dashboard"} <= {t["name"] for t in tools}
    call = mcp_server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_companies", "arguments": {"query": "acme"}}})
    payload = json.loads(call["result"]["content"][0]["text"])
    assert payload == [{"id": "acme-ai", "name": "Acme AI", "ticker": None, "status": "private"}]
    bad = mcp_server.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})
    assert bad["error"]["code"] == -32602
    assert mcp_server.handle_message({"jsonrpc": "2.0", "id": 5, "method": "wat"})["error"]["code"] == -32601
