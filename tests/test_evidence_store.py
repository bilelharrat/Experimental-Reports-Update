from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from server import evidence_store, external_store, files_store, research_store, storage
from server.main import app


def _write_companies(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            [
                {
                    "id": "zainar-inc",
                    "name": "ZaiNar, Inc.",
                    "aliases": ["ZaiNar"],
                    "ticker": "",
                    "status": "private",
                    "company_type": "private",
                },
                {
                    "id": "other-co",
                    "name": "Other Co",
                    "aliases": [],
                    "status": "private",
                    "company_type": "private",
                },
            ],
            f,
            sort_keys=False,
        )


def test_evidence_groups_documents_and_persists_metadata(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data_root / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data_root / "research")
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    _write_companies(data_root / "companies.yaml")

    library = files_store.upload_file(
        "zainar-inc",
        filename="ZaiNar ARR model.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4\n%%EOF\n",
    )
    background = research_store.upload_file(
        "zainar-inc",
        filename="PitchBook ZaiNar market report.txt",
        content_type="text/plain",
        data=b"Market report",
    )

    grouped = evidence_store.list_documents(
        "zainar-inc",
        reports=[
            {
                "id": "report-1",
                "company_id": "zainar-inc",
                "report_type": "Investment Memo (Late-Stage)",
                "language": "en",
                "status": "complete",
                "created_at": "2026-07-03T12:00:00Z",
                "kind": "investment_memo_latestage",
                "download_urls": {"en": "/api/reports/report-1/download?language=en"},
            }
        ],
    )

    rows = grouped["rows"]
    assert {row["backend"] for row in rows} == {
        "document_library",
        "background_documents",
        "generated_report",
    }
    assert grouped["groups"][0]["id"] == "memos"
    assert grouped["groups"][0]["rows"][0]["source_class"] == "generated memo"
    assert next(row for row in rows if row["record_id"] == library["id"])["source_class"] == "unknown/pending"
    assert next(row for row in rows if row["record_id"] == background["id"])["category"] == "external_reports"

    updated = evidence_store.update_document_metadata(
        "zainar-inc",
        "document_library",
        library["id"],
        {
            "category": "Financial",
            "source_class": "company",
            "provenance": {"origin": "CFO upload", "published_at": "2026-06-01"},
        },
    )
    assert updated["document_category"] == "financial"
    assert updated["source_class"] == "company material"
    assert updated["provenance"]["origin"] == "CFO upload"

    refreshed = evidence_store.list_documents("zainar-inc")
    library_row = next(row for row in refreshed["rows"] if row["record_id"] == library["id"])
    assert library_row["category_label"] == "Financial"
    assert library_row["source_class"] == "company material"
    assert library_row["provenance"]["published_at"] == "2026-06-01"


def test_assignment_inference_unresolved_queue_and_dedupe(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    _write_companies(data_root / "companies.yaml")

    assignment = evidence_store.assignment_for_intake(
        "external_research",
        {
            "title": "ZaiNar market landscape",
            "filename": "zainar_market_report.pdf",
            "source_company": "PitchBook",
        },
    )
    assert assignment["status"] == "assigned"
    assert assignment["company_id"] == "zainar-inc"
    assert assignment["document_category"] == "external_reports"
    assert assignment["source_class"] == "third-party market data"

    unresolved = evidence_store.assignment_for_intake(
        "news",
        {"title": "Generic market update", "url": "https://example.com/post"},
    )
    assert unresolved["status"] == "unresolved"
    row = evidence_store.add_unresolved_intake(
        kind="news",
        item_id="news-1",
        payload={"title": "Generic market update", "url": "https://example.com/post"},
        assignment=unresolved,
    )
    assert row["status"] == "unresolved"
    assert evidence_store.list_unresolved_intake()[0]["item_id"] == "news-1"

    key = evidence_store.dedupe_key("news", {"url": "https://Example.com/path/"})
    external_store.write_item(
        "news",
        {
            "id": "news-dup",
            "kind": "news",
            "dedupe_key": key,
            "source_url": "https://example.com/path",
        },
    )
    duplicate = evidence_store.find_duplicate_intake(
        "news",
        key,
        url="https://example.com/path/",
    )
    assert duplicate["id"] == "news-dup"


def test_documents_api_returns_grouped_rows(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data_root / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data_root / "research")
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    _write_companies(data_root / "companies.yaml")

    files_store.upload_file(
        "zainar-inc",
        filename="customer deck.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4\n%%EOF\n",
    )

    client = TestClient(app)
    response = client.get("/api/companies/zainar-inc/documents")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["categories"][0]["label"] == "Memos"
    assert body["groups"]
    assert body["rows"][0]["backend"] == "document_library"

    doc = body["rows"][0]
    patch = client.patch(
        f"/api/companies/zainar-inc/documents/{doc['backend']}/{doc['record_id']}",
        json={"category": "Legal and Corporate", "source_class": "public filing"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["document_category"] == "legal_corporate"
    assert patch.json()["source_class"] == "public filing"
