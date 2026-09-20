"""The fact-ledger, source-cache and per-report fact-check endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server import claude_runner, memo_prep, research_store, source_cache, storage
from server.main import app

COMPANY = "acme-ai"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed(monkeypatch, tmp_path):
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": COMPANY, "name": "Acme AI", "status": "private", "company_type": "private"}],
    )
    monkeypatch.setattr(memo_prep, "DATA_DIR", tmp_path / "data")
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)


def _ledger_path():
    return research_store.RESEARCH_ROOT / COMPANY / claude_runner.MEMO_FACT_LEDGER_FILENAME


def test_ledger_round_trip(client):
    r = client.get(f"/api/companies/{COMPANY}/fact-ledger")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exists"] is False and body["text"] == "" and body["updated_at"] is None
    assert body["max_chars"] == claude_runner.MEMO_FACT_LEDGER_MAX_CHARS
    assert body["enabled"] is True

    text = "- 2026-06-13: Contracted book revised to $500M+; 95+ patents (company announcement).\r\n"
    r = client.put(f"/api/companies/{COMPANY}/fact-ledger", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exists"] is True
    assert body["text"] == "- 2026-06-13: Contracted book revised to $500M+; 95+ patents (company announcement).\n"
    assert body["updated_at"]
    assert _ledger_path().read_text(encoding="utf-8") == body["text"]
    # The loader the pipeline uses reads exactly what was saved.
    assert claude_runner.load_memo_fact_ledger(_ledger_path().parent) == body["text"].strip()

    r = client.get(f"/api/companies/{COMPANY}/fact-ledger")
    assert r.json()["text"] == body["text"]

    # Emptying the ledger removes the file rather than leaving a blank one.
    r = client.put(f"/api/companies/{COMPANY}/fact-ledger", json={"text": "  \n "})
    assert r.status_code == 200
    assert r.json()["exists"] is False
    assert not _ledger_path().exists()


def test_ledger_rejects_bad_input(client):
    assert client.put(f"/api/companies/{COMPANY}/fact-ledger", json={"text": 5}).status_code == 400
    assert client.put(f"/api/companies/{COMPANY}/fact-ledger", json={}).status_code == 400
    too_long = "x" * (claude_runner.MEMO_FACT_LEDGER_MAX_CHARS + 1)
    r = client.put(f"/api/companies/{COMPANY}/fact-ledger", json={"text": too_long})
    assert r.status_code == 400
    assert "limited to" in r.json()["detail"]
    assert not _ledger_path().exists()
    assert client.get("/api/companies/nope/fact-ledger").status_code == 404
    assert client.put("/api/companies/nope/fact-ledger", json={"text": "x"}).status_code == 404


def test_ledger_edit_needs_the_sources_permission(client, monkeypatch):
    from server import api as api_mod

    def deny(request, permission):
        assert permission == "sources:edit"
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="no")

    monkeypatch.setattr(api_mod, "_require_permission", deny)
    assert client.put(f"/api/companies/{COMPANY}/fact-ledger", json={"text": "x"}).status_code == 403
    assert client.get(f"/api/companies/{COMPANY}/fact-ledger").status_code == 200


def test_source_cache_listing(client):
    assert client.get("/api/companies/nope/source-cache").status_code == 404
    r = client.get(f"/api/companies/{COMPANY}/source-cache")
    assert r.status_code == 200 and r.json() == {"company_id": COMPANY, "count": 0, "sources": []}
    source_cache.record_source(
        COMPANY,
        kind="web_search",
        text="Web search results " * 5,
        query="acme ai revenue",
        links=[{"title": "A", "url": "https://a.com/x"}, {"title": "B", "url": "https://b.com/y"}],
        origin="memo_run:r1:WebSearch",
        run_id="r1",
    )
    source_cache.record_source(COMPANY, kind="web_fetch", text="Page text " * 10, url="https://a.com/x", title="Page A")
    r = client.get(f"/api/companies/{COMPANY}/source-cache?limit=1")
    body = r.json()
    assert body["count"] == 2 and len(body["sources"]) == 1
    row = body["sources"][0]
    assert row["kind"] == "web_fetch" and row["url"] == "https://a.com/x"
    assert set(row) == {"id", "kind", "url", "title", "query", "chars", "fetched_at", "first_seen_at", "origins", "run_ids", "links"}
    r = client.get(f"/api/companies/{COMPANY}/source-cache")
    search_row = next(s for s in r.json()["sources"] if s["kind"] == "web_search")
    assert search_row["links"] == 2 and search_row["query"] == "acme ai revenue"


def test_report_fact_check_endpoint(client, tmp_path):
    run_dir = memo_prep.DATA_DIR / "memos" / COMPANY / "2026-09-20__100000__acme-ai__memo-run"
    (run_dir / "logs").mkdir(parents=True)
    report = storage.create_report_record(
        company_id=COMPANY,
        company_name="Acme AI",
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status="complete",
        progress=100,
        stage="Memo ready",
        run_id="2026-09-20__100000",
        run_dir=memo_prep._rel(run_dir),
    )
    r = client.get(f"/api/reports/{report['id']}/fact-check")
    assert r.status_code == 404
    payload = {"status": "warn", "checked": 12, "unsupported": 2, "findings": [{"code": "unsupported_figure"}]}
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps(payload), encoding="utf-8")
    r = client.get(f"/api/reports/{report['id']}/fact-check")
    assert r.status_code == 200, r.text
    assert r.json()["checked"] == 12 and r.json()["report_id"] == report["id"]
    (run_dir / "logs" / "fact_check.json").write_text("{broken", encoding="utf-8")
    assert client.get(f"/api/reports/{report['id']}/fact-check").status_code == 500
    assert client.get("/api/reports/nope/fact-check").status_code == 404
