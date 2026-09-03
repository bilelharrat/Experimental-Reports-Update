"""Tests for the Co-Pilot context adapter."""
from __future__ import annotations

from server import copilot, console_store, storage


def test_assemble_context_includes_workspace_and_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    ctx = copilot.assemble_context(
        company_id,
        {
            "surface": "memo_studio",
            "tab": "memo",
            "selection": {
                "section_title": "Market",
                "bullet_text": "Revenue is recurring.",
            },
        },
    )
    assert ctx["company_id"] == company_id
    assert "ZaiNar" in ctx["label"]
    assert ctx["surface"] == "memo_studio"
    assert isinstance(ctx["actions"], list)
    assert len(ctx["actions"]) >= 1
    assert "workspace" in ctx
    assert "packet" in ctx


def test_situational_actions_prioritize_failed_memo(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    row = copilot._company_row("zainar-inc")
    actions = copilot.situational_actions(
        row,
        {"surface": "research", "tab": "memo"},
    )
    ids = [a["id"] for a in actions]
    assert "evidence_gaps" in ids


def test_build_context_preamble_is_json_block():
    packet = {"company": {"name": "Acme"}, "selection": {"bullet_text": "x"}}
    text = copilot.build_context_preamble(packet)
    assert "Workspace context" in text
    assert "Acme" in text


def test_parse_research_task_from_response():
    text = (
        "Looks worth a follow-up.\n\n"
        '```json\n{"research_task":{"title":"Verify ARR","description":"Check deck"}}\n```'
    )
    task = copilot.parse_research_task(text)
    assert task["title"] == "Verify ARR"
    cleaned = copilot.strip_research_task_block(text)
    assert "```json" not in cleaned


def test_ensure_quick_session_reuses_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    first = copilot.ensure_quick_session(company_id)
    second = copilot.ensure_quick_session(company_id)
    assert first["id"] == second["id"]
    meta = console_store.load_meta(company_id, first["id"])
    assert meta.get("session_kind") == copilot.COPILOT_SESSION_KIND
    assert meta.get("hydration_status") == "skipped"


def test_needs_hydration_skips_workspace_only_questions():
    client = {"surface": "tracking", "attention": {"kind": "memo_failed"}}
    assert copilot.needs_hydration("Diagnose the failed memo run", client) is False
    assert copilot.needs_hydration("Read the deck and cite revenue", client) is True


def test_parse_structured_outputs():
    text = (
        '```json\n{"suggested_edit":{"section_id":"s1","card_id":"c1",'
        '"bullet_id":"b1","text":"Tighter wording"}}\n```\n'
        '```json\n{"next_route":{"surface":"memo_studio","tab":"memo"}}\n```'
    )
    outputs = copilot.parse_structured_outputs(text)
    assert outputs["suggested_edit"]["text"] == "Tighter wording"
    assert outputs["next_route"]["surface"] == "memo_studio"
    cleaned = copilot.strip_structured_blocks(text)
    assert "```json" not in cleaned


def test_ensure_deep_session_reuses_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company_id = "zainar-inc"
    first = copilot.ensure_deep_session(company_id)
    second = copilot.ensure_deep_session(company_id)
    assert first["id"] == second["id"]
    meta = console_store.load_meta(company_id, first["id"])
    assert meta.get("session_kind") == copilot.COPILOT_DEEP_SESSION_KIND


def test_assemble_context_includes_proactive_and_auto_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    ctx = copilot.assemble_context(
        "zainar-inc",
        {
            "surface": "jobs",
            "job": {"status": "failed", "title": "Memo run"},
        },
    )
    assert isinstance(ctx.get("proactive"), list)
    assert ctx.get("auto_prompt")
    assert isinstance(ctx.get("files"), list)


def test_build_provenance_for_metric_target():
    provenance = copilot.build_provenance(
        "zainar-inc",
        {
            "selection": {
                "target_kind": "metric",
                "metric_label": "ARR",
                "metric_value": "$12M",
                "source_refs": [{"filename": "deck.pdf", "locator": "p.4"}],
            },
        },
    )
    assert provenance is not None
    assert provenance["target_kind"] == "metric"
    assert provenance["label"] == "ARR"
    assert len(provenance["sources"]) == 1


def test_auto_prompt_skips_when_drag_tell_target(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    prompt = copilot.auto_prompt(
        {
            "surface": "jobs",
            "job": {"status": "failed"},
            "selection": {"target_kind": "metric", "metric_label": "ARR"},
        },
        None,
    )
    assert prompt is None


def test_assemble_context_includes_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    ctx = copilot.assemble_context(
        "zainar-inc",
        {
            "surface": "overview",
            "selection": {
                "target_kind": "metric",
                "metric_label": "Revenue",
                "metric_value": "high",
            },
        },
    )
    assert ctx.get("provenance")
    assert ctx["provenance"]["target_kind"] == "metric"
    assert ctx.get("auto_prompt") is None
