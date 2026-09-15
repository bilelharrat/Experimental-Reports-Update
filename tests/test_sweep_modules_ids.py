"""Company-id storage keys: dotted and non-ASCII ids keep separate records and never 500."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from server import company_paths, decisions_store, firm, firm_search, ic_room, portfolio, storage
from server.main import app

client = TestClient(app)

CJK = "中经网数据有限公司"


def _seed(*companies: dict) -> None:
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private", "industry": "AI infrastructure"},
        *companies,
    ])


def test_storage_key_keeps_plain_ids_and_hashes_the_rest():
    assert company_paths.storage_key("acme-ai") == "acme-ai"
    assert company_paths.storage_key("Acme-AI") == "acme-ai"
    dotted = company_paths.storage_key("brk.b")
    assert dotted.startswith("brkb.") and dotted != "brkb"
    assert company_paths.storage_key("x-甲") != company_paths.storage_key("x-乙")
    assert company_paths.storage_key("centro-de-educação-integrada-ltda").startswith("centro-de-educacao-integrada-ltda.")
    cjk = company_paths.storage_key(CJK)
    assert cjk.startswith("id.") and "/" not in cjk
    assert company_paths.storage_key("a" * 300).startswith("a" * 60 + ".")
    for bad in ("", "   ", "###", "..", "/"):
        with pytest.raises(ValueError):
            company_paths.storage_key(bad)
    assert company_paths.company_dir("../../etc").parent == storage.DATA_DIR / "companies"


def test_stores_keep_ids_differing_only_in_non_ascii_apart():
    _seed({"id": "x-甲", "name": "Jia", "status": "private"}, {"id": "x-乙", "name": "Yi", "status": "private"})
    ic_room.add_reference_call("x-甲", {"contact": "probe", "relation": "customer"})
    assert ic_room.list_reference_calls("x-乙")["count"] == 0
    assert ic_room.list_reference_calls("x-甲")["count"] == 1
    decisions_store.add_decision("x-甲", verdict="pass", explanation="not for us")
    assert decisions_store.list_decisions("x-乙")["items"] == []
    portfolio.add_kpi("x-甲", {"as_of": "2026-01-01", "headcount": 3})
    assert portfolio.get_portfolio("x-乙")["kpi_count"] == 0
    firm.add_comment("x-甲", text="only here", author="a@b.c")
    assert firm.list_comments("x-乙")["items"] == []
    assert firm.list_comments("x-甲")["items"][0]["text"] == "only here"


def test_all_cjk_company_id_never_breaks_desk_wide_views():
    _seed({"id": CJK, "name": CJK, "status": "private", "company_type": "private"})
    decisions_store.add_decision("acme-ai", verdict="invest", explanation="Team + wedge")
    decisions_store.add_decision(CJK, verdict="watch", explanation="Waiting on data")
    firm_search.invalidate()
    assert client.get("/api/portfolio").status_code == 200
    assert client.get("/api/firm/search?q=data").status_code == 200
    assert client.get("/api/companies/acme-ai/ic/comparables").status_code == 200
    for route in ("portfolio/{id}", "companies/{id}/reference-calls", "companies/{id}/ic/meetings", "companies/{id}/comments", "portfolio/{id}/tear-sheet.docx"):
        assert client.get("/api/" + route.format(id=CJK)).status_code == 200, route
    assert client.post(f"/api/companies/{CJK}/comments", json={"text": "hello"}).status_code == 200
    assert client.get(f"/api/companies/{CJK}/comments").json()["items"][0]["text"] == "hello"


def test_dotted_id_is_counted_once_in_the_portfolio_dashboard():
    _seed({"id": "brk.b", "name": "Berkshire Hathaway B", "status": "public", "ticker": "BRK.B"})
    decisions_store.add_decision("brk.b", verdict="invest", explanation="Compounding")
    assert client.put("/api/portfolio/brk.b/position", json={"invested_usd": 1_000_000}).status_code == 200
    dash = client.get("/api/portfolio").json()
    assert [r["company_id"] for r in dash["companies"]] == ["brk.b"]
    assert dash["companies"][0]["company_name"] == "Berkshire Hathaway B"
    assert dash["totals"]["invested_usd"] == 1_000_000 and dash["totals"]["company_count"] == 1
    assert portfolio.has_record("brk.b") and not portfolio.has_record("brkb")


def test_dashboard_ignores_portfolio_files_for_ids_that_are_not_companies():
    _seed()
    portfolio.update_position("ghost-co", {"invested_usd": 5})
    assert [r["company_id"] for r in portfolio.dashboard()["companies"]] == []


def test_chat_channels_keep_original_ids_and_labels():
    _seed(
        {"id": "brk.b", "name": "Berkshire Hathaway B", "status": "public"},
        {"id": "x-甲", "name": "Jia", "status": "private"},
        {"id": "x-乙", "name": "Yi", "status": "private"},
    )
    for cid in ("brk.b", "x-甲", "x-乙"):
        r = client.post(f"/api/chat/company:{cid}", json={"text": f"hello {cid}"})
        assert r.status_code == 200, r.text
        assert r.json()["channel"] == f"company:{cid}"
    channels = {c["id"]: c for c in client.get("/api/chat/channels").json()["items"]}
    assert channels["company:brk.b"]["label"] == "Berkshire Hathaway B" and channels["company:brk.b"]["company_id"] == "brk.b"
    assert channels["company:x-甲"]["label"] == "Jia" and channels["company:x-乙"]["label"] == "Yi"
    assert channels["company:x-甲"]["message_count"] == 1
    assert [m["text"] for m in client.get("/api/chat/company:x-乙").json()["items"]] == ["hello x-乙"]
    assert firm._channel_path("company:x-甲") != firm._channel_path("company:x-乙")


def test_chat_polling_does_not_miss_same_second_messages(monkeypatch):
    _seed()
    monkeypatch.setattr(firm, "_now", lambda: "2026-09-14T07:49:15Z")
    first = firm.post_message("general", text="A", author="a@b.c")
    latest = firm.read_messages("general")["latest"]
    second = firm.post_message("general", text="B", author="a@b.c")
    ids = {m["id"] for m in firm.read_messages("general", since=latest)["items"]}
    assert second["id"] in ids and first["id"] in ids


def test_audit_matches_dotted_and_accented_company_ids():
    _seed({"id": "qa-x.b", "name": "Dotted", "status": "private"}, {"id": "qa-educação", "name": "Accented", "status": "private"})
    for cid in ("qa-x.b", "qa-educação"):
        assert client.post(f"/api/companies/{cid}/comments", json={"text": "audit me"}).status_code == 200
        rows = client.get("/api/audit", params={"company_id": cid}).json()["items"]
        assert rows and rows[0]["company_id"] == cid, cid
    assert firm.company_from_path("/api/companies/brk.b/comps/peers") == "brk.b"
    assert firm.company_from_path("/api/portfolio/reserves") is None


def test_comment_target_must_be_an_object():
    _seed()
    assert client.post("/api/companies/acme-ai/comments", json={"text": "qa", "target": "company"}).status_code == 400
