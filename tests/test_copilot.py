"""Tests for the Co-Pilot context adapter."""
from __future__ import annotations

from server import claude_runner, copilot, console_store, storage


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


def test_needs_hydration_skips_ios_surface():
    client = {"surface": "ios_market"}
    assert copilot.needs_hydration("Read the 10-K filing", client) is False
    assert copilot.needs_hydration(
        "Read the 10-K filing",
        {"surface": "ios_company", "document_ids": ["abc"]},
    ) is True


def test_ios_runtime_prompt_is_lean(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    prompt = copilot._prepare_runtime_prompt(
        "zainar-inc",
        "Why is this moving?",
        {"surface": "ios_market"},
    )
    assert "Mobile Ask style" in prompt
    assert "Why is this moving?" in prompt
    assert "```json" not in prompt
    assert "WebSearch" not in prompt


def test_ios_market_runtime_prompt_includes_options_premiums(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company = storage.upsert_company_from_match(
        {"name": "Invesco QQQ Trust", "ticker": "QQQ", "company_type": "public"}
    )

    def fake_snap(ticker, *, max_rows=12, cache_only=False):
        assert str(ticker).upper() == "QQQ"
        assert cache_only is False
        return {
            "ticker": "QQQ",
            "last_trade": "$500.00",
            "underlying_last": 500.0,
            "source": "nasdaq",
            "implied_vol_available": False,
            "rows": [
                {
                    "expiry": "2026-09-18",
                    "strike": 500.0,
                    "call_bid": "4.1",
                    "call_ask": "4.3",
                    "call_last": "4.2",
                    "put_bid": "3.8",
                    "put_ask": "4.0",
                    "put_last": "3.9",
                    "call_volume": "100",
                    "call_oi": "200",
                    "put_volume": "90",
                    "put_oi": "150",
                }
            ],
        }

    monkeypatch.setattr(copilot.quote_workspace, "compact_options_snapshot", fake_snap)
    prompt = copilot._prepare_runtime_prompt(
        company["id"],
        "What are the ATM call premiums?",
        {"surface": "ios_market"},
    )
    assert "Options premiums (QQQ" in prompt
    assert "4.1/4.3/4.2" in prompt
    assert "IV is not in this Nasdaq snapshot" in prompt
    assert "ATM call premiums" in prompt


def test_options_keywords_inject_outside_market_surface(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company = storage.upsert_company_from_match(
        {"name": "Advanced Micro Devices", "ticker": "AMD", "company_type": "public"}
    )
    monkeypatch.setattr(
        copilot.quote_workspace,
        "compact_options_snapshot",
        lambda ticker, *, max_rows=12, cache_only=False: {
            "ticker": "AMD",
            "last_trade": "$100",
            "underlying_last": 100.0,
            "rows": [
                {
                    "expiry": "2026-09-18",
                    "strike": 100.0,
                    "call_bid": "1",
                    "call_ask": "1.1",
                    "call_last": "1.05",
                    "put_bid": "1",
                    "put_ask": "1.1",
                    "put_last": "1.05",
                    "call_volume": "10",
                    "call_oi": "20",
                    "put_volume": "10",
                    "put_oi": "20",
                }
            ],
        },
    )
    prompt = copilot._prepare_runtime_prompt(
        company["id"],
        "Show me put premiums near the money",
        {"surface": "ios_company"},
    )
    assert "Options premiums (AMD" in prompt


def test_non_options_company_ask_skips_options_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    company = storage.upsert_company_from_match(
        {"name": "Advanced Micro Devices", "ticker": "AMD", "company_type": "public"}
    )

    def boom(*_a, **_k):
        raise AssertionError("should not fetch options")

    monkeypatch.setattr(copilot.quote_workspace, "compact_options_snapshot", boom)
    prompt = copilot._prepare_runtime_prompt(
        company["id"],
        "Summarize the business in one sentence",
        {"surface": "ios_company"},
    )
    assert "Options premiums" not in prompt
    assert "Summarize the business" in prompt


def test_ensure_ios_quick_session_uses_lean_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    meta = copilot.ensure_quick_session(
        "zainar-inc",
        session_kind=copilot.COPILOT_IOS_SESSION_KIND,
        title=copilot.COPILOT_IOS_SESSION_TITLE,
        include_background_docs=False,
    )
    stored = console_store.load_meta("zainar-inc", meta["id"])
    assert stored.get("session_kind") == copilot.COPILOT_IOS_SESSION_KIND
    assert stored.get("skill_path", "").endswith("bsh_copilot_ask_ios.md")


def test_quick_ask_cli_options_ios_disables_tools(monkeypatch):
    from server import console_session

    monkeypatch.delenv("BSH_COPILOT_QUICK_MODEL", raising=False)
    monkeypatch.delenv("BSH_COPILOT_QUICK_EFFORT", raising=False)
    monkeypatch.delenv("BSH_COPILOT_IOS_TOOLS", raising=False)
    opts = console_session.quick_ask_cli_options("copilot_quick_ios")
    assert opts["model"] == "sonnet"
    assert opts["effort"] == "low"
    assert opts["tools"] == ""
    assert opts["lean_language_directive"] is True
    assert opts["exclude_dynamic_system_prompt"] is True
    assert opts["skill_path"].name == "bsh_copilot_ask_ios.md"


def test_quick_ask_cli_options_haiku_override(monkeypatch):
    from server import console_session

    monkeypatch.setenv("BSH_COPILOT_QUICK_MODEL", "haiku")
    monkeypatch.setenv("BSH_COPILOT_QUICK_EFFORT", "low")
    opts = console_session.quick_ask_cli_options("copilot_quick_ios")
    assert opts["model"] == "haiku"
    assert opts["effort"] == "low"
    assert opts["tools"] == ""


def test_quick_ask_cli_options_web_keeps_read(monkeypatch):
    from server import console_session

    monkeypatch.delenv("BSH_COPILOT_QUICK_TOOLS", raising=False)
    opts = console_session.quick_ask_cli_options("copilot_quick")
    assert opts["tools"] == "Read"
    assert "lean_language_directive" not in opts


def test_quick_ask_cli_options_deep_unchanged():
    from server import console_session

    assert console_session.quick_ask_cli_options("copilot_deep") == {}
    assert console_session.quick_ask_cli_options(None) == {}


def test_run_console_ask_fast_profile_argv(tmp_path, monkeypatch):
    """Quick Ask passes model/effort and disables tools via --tools \"\"."""
    captured: dict = {}

    class _FakeHandle:
        proc = type("P", (), {"pid": 1})()

    def fake_spawn(cmd, cwd=None):
        captured["cmd"] = list(cmd)
        return _FakeHandle()

    def fake_consume(handle, **kwargs):
        return {"ok": True, "usage": {}, "cost_usd": 0.0}

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(claude_runner, "_spawn_console", fake_spawn)
    monkeypatch.setattr(claude_runner, "_consume_stream", fake_consume)

    skill = tmp_path / "skill.md"
    skill.write_text("persona", encoding="utf-8")
    progress = type("P", (), {"emit": lambda *a, **k: None})()

    outcome = claude_runner.run_console_ask(
        claude_session_id="sid-1",
        work_dir=tmp_path / "work",
        user_prompt="What matters?",
        skill_path=skill,
        progress=progress,
        bootstrap_session=True,
        model="haiku",
        effort="low",
        tools="",
        exclude_dynamic_system_prompt=True,
        lean_language_directive=True,
    )
    assert outcome["ok"] is True
    cmd = captured["cmd"]
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "haiku"
    assert "--effort" in cmd and cmd[cmd.index("--effort") + 1] == "low"
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--allowedTools" not in cmd
    assert "--exclude-dynamic-system-prompt-sections" in cmd
    assert "--session-id" in cmd


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
