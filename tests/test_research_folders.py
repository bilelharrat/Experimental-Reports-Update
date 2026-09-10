"""Folder upload grouping + analysis delete cascades in the research store."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import evidence_store, research_store, storage
from server.main import app


@pytest.fixture()
def company():
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    return storage.list_companies()[0]["id"]


def _upload(company_id, name="doc.md", **kwargs):
    return research_store.upload_file(
        company_id,
        filename=name,
        content_type="text/markdown",
        data=b"# hello",
        **kwargs,
    )


def test_route_mints_and_echoes_folder_id(company):
    client = TestClient(app)
    first = client.post(
        f"/api/companies/{company}/research-files",
        files={"file": ("a.md", b"# a", "text/markdown")},
        data={"folder_name": "notes"},
    )
    assert first.status_code == 201, first.text
    folder_id = first.json()["folder_id"]
    assert research_store.FOLDER_ID_RE.match(folder_id)
    assert first.json()["folder_name"] == "notes"

    second = client.post(
        f"/api/companies/{company}/research-files",
        files={"file": ("b.md", b"# b", "text/markdown")},
        data={"folder_name": "notes", "folder_id": folder_id},
    )
    assert second.status_code == 201
    assert second.json()["folder_id"] == folder_id

    members = research_store.folder_members(company, folder_id)
    assert [m["filename"] for m in members] == ["a.md", "b.md"]

    bad = client.post(
        f"/api/companies/{company}/research-files",
        files={"file": ("c.md", b"# c", "text/markdown")},
        data={"folder_id": "not-a-folder-id"},
    )
    assert bad.status_code == 400

    # Plain uploads carry no folder fields.
    plain = client.post(
        f"/api/companies/{company}/research-files",
        files={"file": ("d.md", b"# d", "text/markdown")},
    )
    assert plain.status_code == 201
    assert plain.json().get("folder_id") is None


def test_delete_analysis_clears_source_backref(company):
    source = _upload(company, "report.md")
    analysis = _upload(company, "report_analysis.md")
    research_store.update_record(company, analysis["id"], analysis_of=source["id"])
    research_store.update_record(company, source["id"], analysis_file_id=analysis["id"])

    assert research_store.delete_file(company, analysis["id"]) is True
    refreshed = next(
        e for e in research_store.list_files(company) if e["id"] == source["id"]
    )
    assert refreshed.get("analysis_file_id") is None


def test_delete_source_cascades_its_analysis_and_sidecar(company, tmp_path):
    source = _upload(company, "deck.md")
    analysis = _upload(company, "deck_analysis.md")
    research_store.update_record(company, analysis["id"], analysis_of=source["id"])
    research_store.update_record(company, source["id"], analysis_file_id=analysis["id"])
    sidecar = research_store.analysis_progress_path(company, source["id"])
    sidecar.write_text("{}\n", encoding="utf-8")

    assert research_store.delete_file(company, source["id"]) is True
    ids = {e["id"] for e in research_store.list_files(company)}
    assert analysis["id"] not in ids
    assert not sidecar.exists()


def test_last_member_delete_cascades_folder_analysis(company):
    folder_id = research_store.mint_folder_id()
    m1 = _upload(company, "n1.md", folder_id=folder_id, folder_name="notes")
    m2 = _upload(company, "n2.md", folder_id=folder_id, folder_name="notes")
    folder_analysis = _upload(company, "notes_analysis.md")
    research_store.update_record(
        company, folder_analysis["id"], analysis_of=folder_id
    )
    folder_sidecar = research_store.analysis_progress_path(company, folder_id)
    folder_sidecar.write_text("{}\n", encoding="utf-8")

    # Non-last member: folder analysis survives (stale until Reanalyze).
    assert research_store.delete_file(company, m1["id"]) is True
    assert research_store.analysis_entry_for(company, folder_id) is not None

    # Last member: folder analysis + sidecar cascade.
    assert research_store.delete_file(company, m2["id"]) is True
    assert research_store.analysis_entry_for(company, folder_id) is None
    assert not folder_sidecar.exists()
    ids = {e["id"] for e in research_store.list_files(company)}
    assert folder_analysis["id"] not in ids


def test_document_rows_expose_grouping_fields(company):
    folder_id = research_store.mint_folder_id()
    member = _upload(company, "m.md", folder_id=folder_id, folder_name="notes")
    analysis = _upload(company, "m_analysis.md")
    research_store.update_record(company, analysis["id"], analysis_of=member["id"])
    research_store.update_record(company, member["id"], analysis_file_id=analysis["id"])

    payload = evidence_store.list_documents(company)
    rows = [row for group in payload["groups"] for row in group["rows"]]
    by_record = {row["record_id"]: row for row in rows}
    assert by_record[member["id"]]["folder_id"] == folder_id
    assert by_record[member["id"]]["folder_name"] == "notes"
    assert by_record[member["id"]]["analysis_file_id"] == analysis["id"]
    assert by_record[analysis["id"]]["analysis_of"] == member["id"]
