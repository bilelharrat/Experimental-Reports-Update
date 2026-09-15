"""Round-2 regression sweep (backend): per-company routes 404 for ids that are not
companies and write nothing, ids that cannot be file names give 404 not 500,
legacy stripped directories migrate to storage keys, the translation backfill
is on by default with an opt-out, corrupt settings YAML is logged and kept,
and the non-progress structured prompt runs through the reapable registry."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from server import (
    claude_runner,
    company_paths,
    files_store,
    memo_editor_store,
    portfolio,
    research_store,
    serena_analysis,
    storage,
    thesis_store,
)
from server import main as server_main
from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed(*companies: dict) -> None:
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private"},
        *companies,
    ])


def _paths_mentioning(needle: str) -> list[str]:
    root = storage.DATA_DIR
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*") if needle in p.name]


GHOST = "qa2-r2-ghost"
GHOST_GETS = [
    f"/api/portfolio/{GHOST}",
    f"/api/portfolio/{GHOST}/tear-sheet.docx",
    f"/api/companies/{GHOST}/reference-calls",
    f"/api/companies/{GHOST}/ic/meetings",
    f"/api/companies/{GHOST}/ic/comparables",
    f"/api/companies/{GHOST}/ic/red-team",
    f"/api/companies/{GHOST}/comments",
    f"/api/companies/{GHOST}/signal-score",
    f"/api/companies/{GHOST}/deal-pipeline",
    f"/api/companies/{GHOST}/founder-dossier",
]
GHOST_WRITES = [
    ("PUT", f"/api/portfolio/{GHOST}/position", {"invested_usd": 7}),
    ("POST", f"/api/portfolio/{GHOST}/kpis", {"as_of": "2026-09-01", "headcount": 3}),
    ("POST", f"/api/portfolio/{GHOST}/updates", {"text": "ARR of $1M"}),
    ("POST", f"/api/portfolio/{GHOST}/marks", {"value_usd": 5, "basis": "manual"}),
    ("DELETE", f"/api/portfolio/{GHOST}/kpis/nope", None),
    ("POST", f"/api/companies/{GHOST}/reference-calls", {"contact": "x", "relation": "customer", "rating": 4}),
    ("DELETE", f"/api/companies/{GHOST}/reference-calls/nope", None),
    ("POST", f"/api/companies/{GHOST}/ic/meetings", {"title": "IC"}),
    ("POST", f"/api/companies/{GHOST}/comments", {"text": "hi"}),
    ("PUT", f"/api/companies/{GHOST}/deal-pipeline", {"next_step": "x"}),
]


def test_per_company_routes_404_for_unknown_ids_and_write_nothing(client):
    _seed()
    for path in GHOST_GETS:
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code, r.text[:200])
        assert r.json()["detail"] == "Company not found"
    for method, path, body in GHOST_WRITES:
        r = client.request(method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text[:200])
    assert _paths_mentioning(GHOST) == []
    assert _paths_mentioning(company_paths.storage_key(GHOST)) == []


def test_per_company_routes_still_serve_real_companies(client):
    _seed()
    assert client.get("/api/portfolio/acme-ai").status_code == 200
    assert client.get("/api/companies/acme-ai/reference-calls").status_code == 200
    assert client.get("/api/companies/acme-ai/comments").status_code == 200
    assert client.get("/api/companies/acme-ai/signal-score").status_code == 200
    assert client.get("/api/companies/acme-ai/founder-dossier").status_code == 200
    r = client.put("/api/portfolio/acme-ai/position", json={"invested_usd": 7})
    assert r.status_code == 200, r.text


def test_founder_dossier_get_does_not_write(client):
    _seed()
    assert client.get("/api/companies/acme-ai/founder-dossier").status_code == 200
    assert not (storage.DATA_DIR / "founder_dossiers").exists()


def test_ids_that_cannot_be_file_names_return_404_not_500(client):
    _seed()
    long_id = "a" * 300
    for path in (
        "/api/transcripts/%21%21%21",
        f"/api/transcripts/{long_id}",
        f"/api/reports/{long_id}",
        f"/api/portfolio/{long_id}",
        f"/api/companies/{long_id}/reference-calls",
    ):
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code, r.text[:200])
        assert r.headers["content-type"].startswith("application/json")
    for path in ("/api/transcripts/%21%21%21", f"/api/transcripts/{long_id}"):
        r = client.delete(path)
        assert r.status_code == 404, (path, r.status_code, r.text[:200])


def test_storage_key_is_safe_bounded_and_collision_free():
    key = company_paths.storage_key
    assert key("acme-ai") == "acme-ai"
    assert key("BRK.B") == key("brk.b") != "brkb"
    assert key("x-甲") != key("x-乙")
    assert key("中文公司") != key("中文公司2")
    assert key("brk.b") != key("brk-b")
    long_plain = "a" * 300
    assert len(key(long_plain)) < 100 and key(long_plain) != long_plain
    for raw in ("brk.b", "x-甲", "中文公司", "../../etc", ".a", "a..b", long_plain):
        k = key(raw)
        assert "/" not in k and "\\" not in k and not k.startswith(".") and k not in {".", ".."}
    for raw in ("", "   ", "###", "..", "/"):
        with pytest.raises(ValueError):
            key(raw)


def test_migrate_legacy_dirs_moves_only_unambiguous_data(monkeypatch, tmp_path, caplog):
    data = storage.DATA_DIR
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data / "research")
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data / "memo_editor")
    monkeypatch.setattr(serena_analysis, "ANALYSIS_ROOT", data / "serena_analysis")
    _seed(
        {"id": "brk.b", "name": "Berkshire", "status": "public"},
        {"id": "x-甲", "name": "甲"},
        {"id": "x-乙", "name": "乙"},
        {"id": "abcd", "name": "ABCD plain"},
        {"id": "abc.d", "name": "ABC dotted (strips to the plain id)"},
    )
    companies = data / "companies"
    (companies / "brkb").mkdir(parents=True)
    (companies / "brkb" / "portfolio.json").write_text(
        json.dumps({"position": {"invested_usd": 1000000.0}, "kpis": [], "updates": [], "marks": []}), encoding="utf-8"
    )
    (data / "comments").mkdir()
    (data / "comments" / "brkb.json").write_text(json.dumps({"items": [{"id": "c1", "text": "hi"}]}), encoding="utf-8")
    (data / "memo_editor" / "brkb").mkdir(parents=True)
    (companies / "x-").mkdir()
    (companies / "x-" / "decisions.json").write_text("{}", encoding="utf-8")
    (companies / "abcd").mkdir()
    (companies / "abcd" / "portfolio.json").write_text("{}", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="server.company_paths"):
        moved = company_paths.migrate_legacy_dirs()

    new_key = company_paths.storage_key("brk.b")
    assert sorted(str(dst.relative_to(data)) for _src, dst in moved) == sorted([
        f"companies/{new_key}", f"comments/{new_key}.json", f"memo_editor/{new_key}",
    ])
    assert not (companies / "brkb").exists()
    assert (companies / new_key / "portfolio.json").exists()
    assert portfolio.get_portfolio("brk.b")["position"]["invested_usd"] == 1000000.0
    # Shared legacy name (甲/乙) and a name owned by a plain id (abcd) stay put.
    assert (companies / "x-" / "decisions.json").exists()
    assert (companies / "abcd" / "portfolio.json").exists()
    assert "'x-' is claimed by x-乙, x-甲" in caplog.text
    assert "'abcd' is claimed by abc.d, abcd" in caplog.text
    # Idempotent.
    assert company_paths.migrate_legacy_dirs() == []


def test_lenient_yaml_read_and_quarantine_are_logged_and_keep_the_data(caplog):
    settings = storage.DATA_DIR / "settings"
    settings.mkdir(parents=True)
    broken = "name: my thesis\nsectors: [AI\n  - oops: : :\n"
    (settings / "thesis.yaml").write_text(broken, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="server.storage"):
        thesis = thesis_store.get_thesis()
        assert thesis["name"] != "my thesis"
        assert "not valid YAML" in caplog.text
        caplog.clear()
        thesis_store.save_thesis({"name": "fresh"})
    assert "moved aside" in caplog.text
    aside = [p for p in settings.iterdir() if p.name.startswith("thesis.yaml.corrupt-")]
    assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == broken
    assert thesis_store.get_thesis()["name"] == "fresh"
    assert not list(settings.glob("*.tmp"))


def test_structured_prompt_without_progress_runs_through_the_process_registry(monkeypatch):
    calls: list[dict] = []

    class Proc:
        returncode = 0
        pid = 4242

        def communicate(self, timeout=None):
            return json.dumps({"result": json.dumps({"ok": True})}), ""

        def poll(self):
            return 0

    def fake_popen(*args, **kwargs):
        calls.append(kwargs)
        return Proc()

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(claude_runner, "_popen_claude", fake_popen)
    monkeypatch.setattr(claude_runner.subprocess, "run", lambda *a, **k: pytest.fail("subprocess.run bypasses the registry"))

    data, err = claude_runner.run_structured_prompt(
        system_prompt="Return JSON.", user_prompt="x", schema={"type": "object"}, name="t"
    )
    assert (data, err) == ({"ok": True}, None)
    assert calls and calls[0].get("start_new_session") is True


def test_shutdown_stops_the_translation_backfill_loop(monkeypatch):
    monkeypatch.setattr(server_main.claude_runner, "begin_shutdown", lambda: None)
    monkeypatch.setattr(server_main.memo_analysis, "halt_active_runs_for_shutdown", lambda: None)
    monkeypatch.setattr(server_main.claude_runner, "terminate_live_claude_procs", lambda: 0)
    server_main._TRANSLATION_STOP.clear()
    server_main._shutdown()
    assert server_main._TRANSLATION_STOP.is_set()
