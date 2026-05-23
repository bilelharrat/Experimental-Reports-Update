from __future__ import annotations

import json

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

    def fake_analyze(text, *, hint_title=None, progress=None):
        assert "Agentic workflow" in text
        assert hint_title == "Agentic Gap"
        assert progress is not None
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
