from __future__ import annotations

from fastapi.testclient import TestClient

from server import files_store, storage
from server.main import app


def test_files_store_accepts_markdown(tmp_consoles):
    record = files_store.upload_file(
        "testco",
        filename="notes.md",
        content_type="text/plain",
        data=b"# Notes\n\n- item\n",
    )

    assert record["kind"] == "md"
    assert record["content_type"] == "text/markdown"

    preview_path, err = files_store.get_or_create_preview("testco", record["id"])
    assert err is None
    assert preview_path is not None
    assert preview_path.name == record["stored_name"]
    assert preview_path.read_text(encoding="utf-8").startswith("# Notes")


def test_markdown_upload_and_preview_api(tmp_consoles, monkeypatch):
    monkeypatch.setattr(
        storage,
        "get_company",
        lambda company_id: {"id": company_id, "name": "Test Co"},
    )
    client = TestClient(app)

    upload = client.post(
        "/api/companies/testco/files",
        files={
            "file": (
                "memo.md",
                b"# Memo\n\nA markdown note.",
                "text/markdown",
            )
        },
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["kind"] == "md"
    assert body["filename"] == "memo.md"

    preview = client.get(f"/api/companies/testco/files/{body['id']}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("text/markdown")
    assert preview.headers["content-disposition"] == (
        'inline; filename="memo.md"'
    )
    assert preview.text == "# Memo\n\nA markdown note."
