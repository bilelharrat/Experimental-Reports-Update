"""Company ids with dots or non-ASCII letters reach the console store and the
per-company routes without 500s."""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from server import console_store, storage
from server.main import app

CJK_ID = "ceinet-data-co-ltd-中经网数据有限公司"
ACCENT_ID = "centro-de-educação-integrada-ltda"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("company_id", ["brk.b", ACCENT_ID, CJK_ID, "hormuz", "test_company_id"])
def test_console_store_accepts_ids_storage_issues(company_id):
    meta = console_store.create_session(
        company_id=company_id, include_background_docs=False, include_library_docs=False, included_files=[]
    )
    assert meta["company_id"] == company_id
    listed = console_store.list_sessions(company_id)
    assert [m["id"] for m in listed] == [meta["id"]]
    assert console_store.company_dir(company_id).name == company_id


def test_console_store_keeps_dot_and_dotless_ids_separate():
    console_store.create_session(company_id="brk.b", include_background_docs=False, include_library_docs=False, included_files=[])
    assert console_store.list_sessions("brkb") == []
    assert console_store.company_dir("BRK.B") == console_store.company_dir("brk.b")


@pytest.mark.parametrize(
    "bad", ["", "..", ".", "/etc", "a/b", "a\\b", "a\x00b", ".x", "-x", "a..b", "x" * 129, "中" * 90]
)
def test_console_store_rejects_unsafe_ids(bad):
    with pytest.raises(ValueError):
        console_store.company_dir(bad)


def test_console_routes_return_json_400_for_bad_ids(client):
    r = client.get("/api/companies/a..b/console/sessions")
    assert r.status_code == 400
    assert "Invalid company_id" in r.json()["detail"]
    r = client.get("/api/companies/a..b/console/sessions/abcdef123456abcd")
    assert r.status_code == 400
    r = client.get("/api/companies/a..b/console/sessions/abcdef123456abcd/turns")
    assert r.status_code in (400, 404)
    r = client.delete("/api/companies/a..b/console/sessions/abcdef123456abcd")
    assert r.status_code == 400


def test_console_routes_work_for_dot_and_cjk_ids(client):
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {"id": "brk.b", "name": "Berkshire Hathaway", "ticker": "BRK.B", "status": "public", "company_type": "public"},
            {"id": CJK_ID, "name": "中经网数据有限公司", "status": "private", "company_type": "private"},
        ],
    )
    for cid in ("brk.b", CJK_ID):
        r = client.get(f"/api/companies/{cid}/console/sessions")
        assert r.status_code == 200, r.text
        assert r.json() == []


def test_company_routes_map_invalid_id_to_json_404(client, monkeypatch):
    from server import firm, ic_room, portfolio, red_team, signal_score

    def boom(*_a, **_k):
        raise ValueError("Invalid company id")

    monkeypatch.setattr(ic_room, "list_reference_calls", boom)
    monkeypatch.setattr(ic_room, "list_meetings", boom)
    monkeypatch.setattr(red_team, "load_result", boom)
    monkeypatch.setattr(portfolio, "get_portfolio", boom)
    monkeypatch.setattr(firm, "list_comments", boom)
    monkeypatch.setattr(signal_score, "compute", boom)
    for path in (
        "/api/companies/中文公司/reference-calls",
        "/api/companies/中文公司/ic/meetings",
        "/api/companies/中文公司/ic/red-team",
        "/api/portfolio/中文公司",
        "/api/companies/中文公司/comments",
        "/api/companies/中文公司/signal-score",
    ):
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code, r.text)
        assert r.json()["detail"] == "Company not found"


def test_transcript_upload_rejects_corrupt_docx(client):
    r = client.post(
        "/api/transcripts/upload",
        files={"file": ("bad.docx", io.BytesIO(b"not a zip"), "application/octet-stream")},
        data={"title": "Broken", "kind": "expert_call"},
    )
    assert r.status_code == 400, r.text
    assert "docx" in r.json()["detail"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<not xml")
    r = client.post(
        "/api/transcripts/upload",
        files={"file": ("bad2.docx", io.BytesIO(buf.getvalue()), "application/octet-stream")},
        data={"title": "Broken", "kind": "expert_call"},
    )
    assert r.status_code == 400, r.text
