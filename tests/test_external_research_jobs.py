from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server import (
    api,
    console_store,
    external_store,
    files_store,
    hormuz_store,
    job_progress,
    memo_prep,
    research_store,
    storage,
    text_analysis,
)
from server.main import app


@pytest.fixture
def isolated_job_roots(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data_root / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data_root / "research")
    monkeypatch.setattr(console_store, "CONSOLES_ROOT", data_root / "consoles")
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    monkeypatch.setattr(hormuz_store, "APPENDIX_ROOT", data_root / "hormuz")
    return data_root


def _events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _old_ts(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _seed_company(tmp_path, company_id: str = "generalist") -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": company_id, "name": "Generalist", "status": "private"}],
    )


def test_external_research_analysis_writes_job_progress(
    isolated_job_roots, tmp_path, monkeypatch
):
    item_id = "research123"
    source = tmp_path / "source.txt"
    source.write_text(
        "Agentic workflow analysis with specific facts.", encoding="utf-8"
    )
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "queued",
            "title": "Agentic Gap",
            "filename": "source.txt",
            "source_company": "Fusion Fund",
        },
    )

    def fake_analyze(text, *, hint_title=None, progress=None, cancel_event=None):
        assert "Agentic workflow" in text
        assert hint_title == "Agentic Gap"
        assert progress is not None
        assert cancel_event is None
        progress.emit("claude_action", action="thinking", text="Reading the document")
        return {
            "title": "Agentic Gap",
            "summary": "Google closed part of the agentic gap.",
            "key_points": ["Gemini improved.", "Distribution matters."],
            "language": "en",
            "translation": {
                "language": "zh",
                "title": "Agentic Gap",
                "summary": "谷歌缩小了部分智能体差距。",
                "key_points": ["Gemini 有提升。", "分发很重要。"],
                "full_text": "译文",
            },
        }

    monkeypatch.setattr(text_analysis, "analyze", fake_analyze)

    api._run_external_research_analysis(item_id, str(source), "Agentic Gap")

    log_path = api._external_research_analysis_progress_path(item_id)
    events = _events(log_path)
    assert [event["type"] for event in events] == [
        "job_init",
        "stage",
        "stage",
        "claude_action",
        "stage",
        "done",
    ]
    assert events[0]["kind"] == "external_research"
    assert events[2]["stage"] == "analyzing"
    assert events[-1]["key_point_count"] == 2

    item = external_store.get_item("external_research", item_id)
    assert item["status"] == "ready"
    assert item["summary"] == "Google closed part of the agentic gap."


def test_external_research_analysis_appears_in_active_jobs(isolated_job_roots):
    item_id = "active123"
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "analyzing",
            "title": "Live analysis",
            "filename": "live.pdf",
            "source_company": "Fusion Fund",
        },
    )
    progress = job_progress.ProgressLog(
        api._external_research_analysis_progress_path(item_id)
    )
    progress.emit(
        "job_init",
        kind="external_research",
        title="Live analysis",
        subtitle="Fusion Fund",
        item_id=item_id,
    )
    progress.emit("stage", stage="analyzing", message="Analyzing extracted text")

    client = TestClient(app)
    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    jobs = active.json()
    job = next(j for j in jobs if j.get("item_id") == item_id)
    assert job["kind"] == "external_research"
    assert job["title"] == "Live analysis"
    assert job["stream_url"].endswith(
        f"/external/research/{item_id}/analysis/stream"
    )
    assert job["log_url"] == f"/api/jobs/log?path=external_research:{item_id}"

    log = client.get(f"/api/jobs/log?path=external_research:{item_id}")
    assert log.status_code == 200, log.text
    assert [event["type"] for event in log.json()] == ["job_init", "stage"]


def test_external_research_upload_rejects_unsupported_and_oversized_files(
    isolated_job_roots, monkeypatch
):
    client = TestClient(app)

    unsupported = client.post(
        "/api/external/research",
        files={"file": ("payload.exe", b"abc", "application/octet-stream")},
    )
    assert unsupported.status_code == 400, unsupported.text
    assert "Unsupported external research file type" in unsupported.text

    monkeypatch.setattr(api, "EXTERNAL_RESEARCH_MAX_FILE_BYTES", 4)
    oversized = client.post(
        "/api/external/research",
        files={"file": ("note.txt", b"12345", "text/plain")},
    )
    assert oversized.status_code == 400, oversized.text
    assert "File too large" in oversized.text


def test_external_research_upload_allows_pptx():
    assert api._external_research_upload_kind("board-update.pptx") == "pptx"


def test_external_research_extracts_pptx_slide_text(tmp_path, monkeypatch):
    path = tmp_path / "board-update.pptx"
    path.write_bytes(b"pptx placeholder")

    monkeypatch.setattr(
        api.deck_summary,
        "extract_slides",
        lambda path, kind: [
            api.deck_summary.Slide(
                slide_no=1,
                text="Net revenue retention reached 122% in enterprise cohorts.",
                notes="Speaker note: source is the customer cohort appendix.",
            )
        ],
    )

    text = api._extract_text_from_file(str(path))

    assert "[Slide 1]" in text
    assert "Net revenue retention reached 122%" in text
    assert "[Slide 1 notes]" in text
    assert "customer cohort appendix" in text


def test_research_file_summary_launch_is_idempotent_for_active_job(
    isolated_job_roots, tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    _seed_company(tmp_path)
    entry = research_store.upload_file(
        "generalist",
        filename="note.txt",
        content_type="text/plain",
        data=b"research note",
    )
    research_store.update_record(
        "generalist",
        entry["id"],
        quick_summary={"summary": "Existing summary"},
    )
    progress = job_progress.ProgressLog(
        research_store.quick_summary_progress_path("generalist", entry["id"])
    )
    progress.emit(
        "job_init",
        kind="research_summary",
        title="note.txt",
        company_id="generalist",
        file_id=entry["id"],
    )
    progress.emit("stage", stage="starting", message="Still summarizing")

    client = TestClient(app)
    response = client.post(
        f"/api/companies/generalist/research-files/{entry['id']}/summary"
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "already_running"
    persisted, _ = research_store.get_file("generalist", entry["id"])
    assert persisted["quick_summary"]["summary"] == "Existing summary"


def test_research_translation_supersedes_stale_progress_before_requeue(
    isolated_job_roots, monkeypatch
):
    item_id = "translate123"
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "ready",
            "title": "Deck",
            "filename": "deck.pdf",
            "stored_name": f"{item_id}__deck.pdf",
            "content_type": "application/pdf",
        },
    )
    progress_path = api._research_translate_progress_path(item_id)
    progress_path.write_text(
        "\n".join([
            json.dumps({
                "type": "job_init",
                "ts": _old_ts(),
                "kind": "pdf_translation",
                "item_id": item_id,
            }),
            json.dumps({
                "type": "stage",
                "ts": _old_ts(),
                "stage": "translating",
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    os.utime(progress_path, (0, 0))

    starts = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            starts.append((args, kwargs))

        def start(self):
            starts.append("started")

    monkeypatch.setattr(api.threading, "Thread", FakeThread)

    response = api.post_research_translate(item_id)
    assert response["status"] == "queued"
    assert "started" in starts
    assert not progress_path.exists()


def test_external_research_delete_cleans_progress_artifacts(isolated_job_roots):
    item_id = "delete123"
    files_dir = external_store._kind_dir("external_research") / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{item_id}__source.txt"
    (files_dir / stored_name).write_text("source", encoding="utf-8")
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "ready",
            "title": "Delete me",
            "filename": "source.txt",
            "stored_name": stored_name,
        },
    )
    analysis_path = api._external_research_analysis_progress_path(item_id)
    translation_path = api._research_translate_progress_path(item_id)
    analysis_path.write_text("{}\n", encoding="utf-8")
    translation_path.write_text("{}\n", encoding="utf-8")
    translation_dir = (
        external_store._kind_dir("external_research")
        / "translations"
        / item_id
    )
    translation_dir.mkdir(parents=True)
    (translation_dir / "result.json").write_text("{}", encoding="utf-8")

    client = TestClient(app)
    response = client.delete(f"/api/external/research/{item_id}")
    assert response.status_code == 204, response.text
    assert external_store.get_item("external_research", item_id) is None
    assert not (files_dir / stored_name).exists()
    assert not analysis_path.exists()
    assert not translation_path.exists()
    assert not translation_dir.exists()


def test_research_file_summary_cancel_emits_terminal_event(
    isolated_job_roots, tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    _seed_company(tmp_path)
    entry = research_store.upload_file(
        "generalist",
        filename="note.txt",
        content_type="text/plain",
        data=b"research note",
    )
    progress_path = research_store.quick_summary_progress_path(
        "generalist", entry["id"]
    )
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="research_summary",
        title="note.txt",
        company_id="generalist",
        file_id=entry["id"],
    )
    progress.emit("stage", stage="starting", message="Still summarizing")

    client = TestClient(app)
    response = client.post(
        f"/api/companies/generalist/research-files/{entry['id']}/summary/cancel"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert _events(progress_path)[-1]["type"] == "cancelled"

    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    assert not any(
        job.get("kind") == "research_summary"
        and job.get("file_id") == entry["id"]
        for job in active.json()
    )


def test_external_research_analysis_cancel_clears_active_state(
    isolated_job_roots,
):
    item_id = "cancel-analysis"
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "analyzing",
            "title": "Cancel me",
            "filename": "cancel.pdf",
        },
    )
    progress_path = api._external_research_analysis_progress_path(item_id)
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="external_research",
        title="Cancel me",
        item_id=item_id,
    )
    progress.emit("stage", stage="analyzing", message="Analyzing")

    client = TestClient(app)
    response = client.post(f"/api/external/research/{item_id}/analysis/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert _events(progress_path)[-1]["type"] == "cancelled"
    item = external_store.get_item("external_research", item_id)
    assert item["status"] == "ready"
    assert item["analysis_error"] == "Analysis cancelled"

    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    assert not any(job.get("item_id") == item_id for job in active.json())


def test_research_translation_cancel_emits_terminal_event(isolated_job_roots):
    item_id = "cancel-translation"
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "ready",
            "title": "Translate me",
            "filename": "deck.pdf",
            "stored_name": f"{item_id}__deck.pdf",
            "content_type": "application/pdf",
        },
    )
    progress_path = api._research_translate_progress_path(item_id)
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="pdf_translation",
        title="Translate me",
        item_id=item_id,
    )
    progress.emit("stage", stage="translating", message="Translating")

    client = TestClient(app)
    response = client.post(f"/api/external/research/{item_id}/translate/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert _events(progress_path)[-1]["type"] == "cancelled"

    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    assert not any(job.get("item_id") == item_id for job in active.json())


def test_stale_research_summary_and_analysis_are_recovered(
    isolated_job_roots, tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    _seed_company(tmp_path)
    entry = research_store.upload_file(
        "generalist",
        filename="note.txt",
        content_type="text/plain",
        data=b"research note",
    )
    summary_path = research_store.quick_summary_progress_path(
        "generalist", entry["id"]
    )
    summary_path.write_text(
        "\n".join([
            json.dumps({
                "type": "job_init",
                "ts": _old_ts(),
                "kind": "research_summary",
                "company_id": "generalist",
                "file_id": entry["id"],
            }),
            json.dumps({
                "type": "stage",
                "ts": _old_ts(),
                "stage": "summarizing",
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    os.utime(summary_path, (0, 0))

    item_id = "stale-analysis"
    external_store.write_item(
        "external_research",
        {
            "id": item_id,
            "kind": "external_research",
            "status": "analyzing",
            "title": "Stale analysis",
            "filename": "stale.pdf",
        },
    )
    analysis_path = api._external_research_analysis_progress_path(item_id)
    analysis_path.write_text(
        "\n".join([
            json.dumps({
                "type": "job_init",
                "ts": _old_ts(),
                "kind": "external_research",
                "item_id": item_id,
            }),
            json.dumps({
                "type": "stage",
                "ts": _old_ts(),
                "stage": "analyzing",
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    os.utime(analysis_path, (0, 0))

    client = TestClient(app)
    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    assert not any(job.get("file_id") == entry["id"] for job in active.json())
    assert not any(job.get("item_id") == item_id for job in active.json())
    assert _events(summary_path)[-1]["type"] == "recovered"
    assert _events(analysis_path)[-1]["type"] == "recovered"
    item = external_store.get_item("external_research", item_id)
    assert item["status"] == "ready"
    assert "Recovered interrupted run" in item["analysis_error"]
