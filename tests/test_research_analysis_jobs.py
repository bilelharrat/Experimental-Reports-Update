"""Document-analysis job: persistent <name>_analysis.md for files/folders."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server import api, claude_runner, research_store, storage
from server.main import app


@pytest.fixture()
def company(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": "generalist", "name": "Generalist", "status": "private"}],
    )
    return "generalist"


def _upload(company_id, name="doc.md", **kwargs):
    return research_store.upload_file(
        company_id,
        filename=name,
        content_type="text/markdown",
        data=b"# content",
        **kwargs,
    )


def _fake_analysis(captured):
    def fake(**kwargs):
        captured.append(kwargs)
        return {
            "analysis_md": "# Analysis\n\nUseful facts.\n\n## 中文摘要\n摘要。",
            "claude_cost_usd": 0.5,
            "generated_at": "2026-09-13T00:00:00+00:00",
        }

    return fake


def test_file_analysis_persists_entry_and_backref(company, monkeypatch):
    entry = _upload(company, "partner-note.md")
    captured: list[dict] = []
    monkeypatch.setattr(
        api.claude_runner, "run_research_analysis", _fake_analysis(captured)
    )

    api._run_research_analysis_job(company, entry["id"])

    assert len(captured) == 1
    assert captured[0]["sources"][0]["filename"] == "partner-note.md"
    analysis = research_store.analysis_entry_for(company, entry["id"])
    assert analysis is not None
    assert analysis["filename"] == "partner-note_analysis.md"
    assert analysis["analysis_of"] == entry["id"]
    source = next(
        e for e in research_store.list_files(company) if e["id"] == entry["id"]
    )
    assert source["analysis_file_id"] == analysis["id"]
    _, blob = research_store.get_file(company, analysis["id"])
    assert "Useful facts" in blob.read_text(encoding="utf-8")

    events = _stream_events(company, entry["id"])
    done = [e for e in events if e["type"] == "done"]
    assert done and done[-1]["analysis_file_id"] == analysis["id"]


def _stream_events(company_id, target_id):
    path = research_store.analysis_progress_path(company_id, target_id)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_folder_analysis_passes_every_member(company, monkeypatch):
    folder_id = research_store.mint_folder_id()
    _upload(company, "n1.md", folder_id=folder_id, folder_name="notes")
    _upload(company, "n2.md", folder_id=folder_id, folder_name="notes")
    captured: list[dict] = []
    monkeypatch.setattr(
        api.claude_runner, "run_research_analysis", _fake_analysis(captured)
    )

    api._run_research_analysis_job(company, folder_id)

    names = [s["filename"] for s in captured[0]["sources"]]
    assert names == ["n1.md", "n2.md"]
    assert captured[0]["hint_title"] == "notes"
    analysis = research_store.analysis_entry_for(company, folder_id)
    assert analysis["filename"] == "notes_analysis.md"
    # Folder targets have no record to back-reference — the analysis_of
    # link alone drives the Reanalyze state.


def test_reanalyze_replaces_prior_analysis(company, monkeypatch):
    entry = _upload(company, "deck.md")
    captured: list[dict] = []
    monkeypatch.setattr(
        api.claude_runner, "run_research_analysis", _fake_analysis(captured)
    )
    api._run_research_analysis_job(company, entry["id"])
    first = research_store.analysis_entry_for(company, entry["id"])
    api._run_research_analysis_job(company, entry["id"])
    second = research_store.analysis_entry_for(company, entry["id"])
    assert first["id"] != second["id"]
    ids = {e["id"] for e in research_store.list_files(company)}
    assert first["id"] not in ids
    source = next(
        e for e in research_store.list_files(company) if e["id"] == entry["id"]
    )
    assert source["analysis_file_id"] == second["id"]


def test_runner_fence_strip():
    fenced = "```markdown\n# Doc\n\nBody.\n```"
    import re

    match = re.match(
        r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", fenced, re.DOTALL
    )
    assert match and match.group(1).strip().startswith("# Doc")
    assert claude_runner.research_analysis_timeout_sec(1) == 240
    assert claude_runner.research_analysis_timeout_sec(4) == 600
    assert claude_runner.research_analysis_timeout_sec(50) == 900


def test_analysis_routes(company, monkeypatch):
    entry = _upload(company, "memo.md")
    started: list[tuple] = []
    monkeypatch.setattr(
        api,
        "_run_research_analysis_job",
        lambda cid, tid, *a, **kw: started.append((cid, tid)),
    )
    client = TestClient(app)

    assert (
        client.post(
            f"/api/companies/{company}/research-files/nope/analysis"
        ).status_code
        == 404
    )
    fake_folder = research_store.mint_folder_id()
    assert (
        client.post(
            f"/api/companies/{company}/research-files/{fake_folder}/analysis"
        ).status_code
        == 404
    )

    response = client.post(
        f"/api/companies/{company}/research-files/{entry['id']}/analysis"
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["kind"] == "research_analysis"
    assert (
        body["log_url"]
        == f"/api/jobs/log?path=research_analysis:{company}/{entry['id']}"
    )
    deadline_ok = False
    for _ in range(50):
        if started:
            deadline_ok = True
            break
        import time

        time.sleep(0.02)
    assert deadline_ok and started[0] == (company, entry["id"])

    # An analysis file cannot itself be analyzed.
    analysis = _upload(company, "memo_analysis.md")
    research_store.update_record(company, analysis["id"], analysis_of=entry["id"])
    assert (
        client.post(
            f"/api/companies/{company}/research-files/{analysis['id']}/analysis"
        ).status_code
        == 400
    )


def test_cancel_route_emits_terminal(company):
    entry = _upload(company, "long.md")
    client = TestClient(app)
    response = client.post(
        f"/api/companies/{company}/research-files/{entry['id']}/analysis/cancel"
    )
    assert response.status_code == 200
    events = _stream_events(company, entry["id"])
    assert events and events[-1]["type"] == "cancelled"


def test_rail_collector_and_recovery(company):
    entry = _upload(company, "live.md")
    progress = api.job_progress.ProgressLog(
        research_store.analysis_progress_path(company, entry["id"])
    )
    progress.emit(
        "job_init",
        kind="research_analysis",
        title="live.md",
        company_id=company,
        file_id=entry["id"],
    )
    rows = list(api._research_analysis_kind_records())
    assert len(rows) == 1
    assert rows[0]["kind"] == "research_analysis"
    assert rows[0]["file_id"] == entry["id"]
    assert "analysis/stream" in rows[0]["stream_url"]

    # The quick-summary collector must not pick the analysis jsonl up.
    assert all(
        row["file_id"] != entry["id"]
        for row in api._research_summary_kind_records()
    )

    # Log-path token resolves.
    resolved = api._resolve_job_log_path(
        f"research_analysis:{company}/{entry['id']}"
    )
    assert resolved == research_store.analysis_progress_path(
        company, entry["id"]
    )
