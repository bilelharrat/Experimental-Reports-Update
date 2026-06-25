from __future__ import annotations

import json

from server import claude_runner, memo_prep


class _CaptureProgress:
    def __init__(self):
        self.events = []

    def emit(self, type_, **fields):
        self.events.append({"type": type_, **fields})


def test_early_stage_round_is_scope_warning_not_failure():
    assessment = memo_prep._assess_stage(
        {"latest_funding": {"round": "Series A"}}
    )

    assert assessment["outcome"] == "warn"
    assert assessment["classification"] == "early-stage"
    assert "series a" in assessment["reason"]


def test_low_total_funding_is_scope_warning_not_failure():
    assessment = memo_prep._assess_stage({"total_funding_usd": "$3M"})

    assert assessment["outcome"] == "warn"
    assert assessment["classification"] == "early-stage"


def test_nonprofit_scope_check_remains_hard_failure():
    assessment = memo_prep._assess_stage({"status": "nonprofit"})

    assert assessment["outcome"] == "fail"
    assert assessment["classification"] == "out-of-scope"


def test_investment_memo_prompt_carries_scope_warning_override(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        scope_check={
            "outcome": "warn",
            "classification": "early-stage",
            "reason": "Latest funding round 'series a' is early-stage.",
        },
        warnings=["Latest funding round 'series a' is early-stage."],
    )

    assert "Scope-warning override from prep" in prompt
    assert "Proceed with the memo anyway" in prompt
    assert "Do **not** stop or decline solely because" in prompt


def test_memo_progress_detects_analysis_pass_written_by_bash():
    progress = _CaptureProgress()
    state = {"thread_map": claude_runner._MEMO_ANALYSIS_PASSES}

    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {
                            "description": "Write pressure-test analysis",
                            "command": "cat > analysis/pressure_tests.md <<'EOF'\n...",
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )
    claude_runner._process_event(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "is_error": False,
                        "content": "ok",
                    }
                ]
            },
        },
        progress,
        state,
    )

    assert {
        (event.get("type"), event.get("thread"))
        for event in progress.events
        if event.get("thread")
    } == {
        ("thread_started", "Arithmetic / pressure tests"),
        ("claude_action", "Arithmetic / pressure tests"),
    }
    assert any(
        event.get("action") == "tool_result"
        and event.get("thread") == "Arithmetic / pressure tests"
        for event in progress.events
    )


def test_memo_progress_groups_initial_intake_as_phase_one():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE1_THREAD,
        "memo_phase_tracking": True,
    }

    claude_runner._process_event(
        {
            "type": "system",
            "subtype": "init",
            "session_id": "session-1",
            "model": "claude-opus-4-7",
            "cwd": "/tmp/run",
            "tools": ["Read", "Write"],
        },
        progress,
        state,
    )
    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Read",
                        "input": {"file_path": "/tmp/Serena_Background.md"},
                    }
                ]
            },
        },
        progress,
        state,
    )
    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "Write",
                        "input": {
                            "file_path": "analysis/pressure_tests.md",
                            "content": "pressure test",
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )

    assert progress.events[0]["type"] == "thread_started"
    assert progress.events[0]["thread"] == claude_runner._MEMO_PHASE1_THREAD
    assert any(
        event.get("type") == "claude_action"
        and event.get("thread") == claude_runner._MEMO_PHASE1_THREAD
        and event.get("action") == "tool_use"
        and event.get("tool") == "Read"
        for event in progress.events
    )
    assert any(
        event.get("type") == "thread_finished"
        and event.get("thread") == claude_runner._MEMO_PHASE1_THREAD
        for event in progress.events
    )
    assert any(
        event.get("type") == "thread_started"
        and event.get("thread") == claude_runner._MEMO_PHASE2_THREAD
        for event in progress.events
    )
    assert any(
        event.get("type") == "thread_started"
        and event.get("thread") == "Arithmetic / pressure tests"
        for event in progress.events
    )


def test_memo_phase_transitions_do_not_skip_phase_two():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE1_THREAD,
        "memo_phase_tracking": True,
    }

    claude_runner._process_event(
        {
            "type": "system",
            "subtype": "init",
            "session_id": "session-1",
            "model": "claude-opus-4-7",
            "cwd": "/tmp/run",
            "tools": ["Read", "Write"],
        },
        progress,
        state,
    )
    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Write",
                        "input": {
                            "file_path": "analysis/risk_sensitivities.md",
                            "content": "sensitivities",
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )

    phase_events = [
        (event.get("type"), event.get("thread"))
        for event in progress.events
        if str(event.get("thread") or "").startswith("Phase ")
    ]

    assert (
        "thread_started",
        claude_runner._MEMO_PHASE2_THREAD,
    ) in phase_events
    assert (
        "thread_finished",
        claude_runner._MEMO_PHASE2_THREAD,
    ) in phase_events
    assert phase_events.index(
        ("thread_finished", claude_runner._MEMO_PHASE2_THREAD)
    ) < phase_events.index(
        ("thread_started", claude_runner._MEMO_PHASE3_THREAD)
    )


def test_memo_progress_emits_output_piece_with_phase_and_started_at():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE1_THREAD,
        "memo_phase_tracking": True,
    }

    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_claim",
                        "name": "Write",
                        "input": {
                            "file_path": "analysis/claim_register.md",
                            "content": "# Claim Register\n\n- Claim A: source-backed.",
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )

    output_events = [
        event for event in progress.events
        if event.get("type") == "output_piece"
    ]

    assert len(output_events) == 1
    output = output_events[0]
    assert output["thread"] == "Claim register"
    assert output["phase"] == claude_runner._MEMO_PHASE3_THREAD
    assert output["filename"] == "claim_register.md"
    assert output["operation"] == "write"
    assert output["started_at"]
    assert "# Claim Register" in output["content"]
    assert output["content_chars"] == len("# Claim Register\n\n- Claim A: source-backed.")
    assert output["truncated"] is False


def test_memo_progress_records_rate_limit_event():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE2_THREAD,
        "memo_phase_tracking": True,
    }

    claude_runner._process_event(
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "rateLimitType": "five_hour",
                "overageStatus": "rejected",
                "overageDisabledReason": "org_level_disabled",
                "isUsingOverage": False,
                "resetsAt": 1782211800,
            },
        },
        progress,
        state,
    )

    event = progress.events[-1]
    assert event["type"] == "claude_action"
    assert event["thread"] == claude_runner._MEMO_PHASE2_THREAD
    assert event["action"] == "rate_limit"
    assert event["resets_at"] == 1782211800
    assert "rate_limit_status" not in event
    assert "rate_limit_type" not in event
    assert "overage_status" not in event
    assert "overage_disabled_reason" not in event
    assert "is_using_overage" not in event


def test_investment_memo_runner_emits_planned_phase_rows(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    settings_path = tmp_path / "serena_background.md"
    companies_path = tmp_path / "companies.yaml"
    settings_path.write_text("background", encoding="utf-8")
    companies_path.write_text(
        "- id: zainar-inc\n  name: ZaiNar, Inc.\n",
        encoding="utf-8",
    )

    result_event = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 1000,
        "total_cost_usd": 0,
    }

    class FakeProc:
        stdout = iter([json.dumps(result_event)])
        stderr = iter(())
        returncode = 0
        pid = 12345

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    progress = _CaptureProgress()

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(
        claude_runner.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProc(),
    )

    result = claude_runner.run_investment_memo(
        run_dir=run_dir,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-23__082720",
        settings_path=settings_path,
        companies_yaml_path=companies_path,
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
        progress=progress,
    )

    assert result["ok"] is True
    planned = [
        event for event in progress.events
        if event.get("type") == "thread_planned"
    ]
    assert [event["thread"] for event in planned[:2]] == [
        claude_runner._MEMO_PHASE1_THREAD,
        claude_runner._MEMO_PHASE2_THREAD,
    ]
    assert planned[0]["estimate_ms"] == 150_000
    assert "2m 30s" in planned[0]["description"]


def test_investment_memo_runner_treats_stream_is_error_as_failure(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    settings_path = tmp_path / "serena_background.md"
    companies_path = tmp_path / "companies.yaml"
    settings_path.write_text("background", encoding="utf-8")
    companies_path.write_text("companies: []", encoding="utf-8")

    result_event = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": 401,
        "duration_ms": 4765,
        "total_cost_usd": 0,
        "result": "Failed to authenticate. API Error: 401 Invalid authentication credentials",
    }

    class FakeProc:
        stdout = iter([json.dumps(result_event)])
        stderr = iter(())
        returncode = 1
        pid = 12345

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")

    captured = {}

    def fake_popen(args, **kwargs):
        captured["cmd"] = args
        return FakeProc()

    monkeypatch.setattr(
        claude_runner.subprocess,
        "Popen",
        fake_popen,
    )

    result = claude_runner.run_investment_memo(
        run_dir=run_dir,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-23__072519",
        settings_path=settings_path,
        companies_yaml_path=companies_path,
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
    )

    assert result["ok"] is False
    assert result["api_error_status"] == 401
    assert "Invalid authentication credentials" in result["error"]
    assert "--disallowedTools" in captured["cmd"]
    denied = captured["cmd"][captured["cmd"].index("--disallowedTools") + 1]
    assert "TaskCreate" in denied
    assert "ToolSearch" in denied
    assert "TodoWrite" in denied


def test_investment_memo_provider_error_preserves_completed_artifact_threads(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    settings_path = tmp_path / "serena_background.md"
    companies_path = tmp_path / "companies.yaml"
    settings_path.write_text("background", encoding="utf-8")
    companies_path.write_text("companies: []", encoding="utf-8")

    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_pressure",
                        "name": "Write",
                        "input": {
                            "file_path": str(run_dir / "analysis" / "pressure_tests.md"),
                            "content": "# Pressure tests\n\nCompleted artifact.",
                        },
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_pressure",
                        "is_error": False,
                        "content": "File created successfully.",
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "api_error_status": 403,
            "duration_ms": 698250,
            "total_cost_usd": 2.75,
            "result": "Failed to authenticate. API Error: 403 Request not allowed",
        },
    ]

    class FakeProc:
        stdout = iter(json.dumps(event) for event in events)
        stderr = iter(())
        returncode = 1
        pid = 12345

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    progress = _CaptureProgress()

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(
        claude_runner.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProc(),
    )

    result = claude_runner.run_investment_memo(
        run_dir=run_dir,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-23__090406",
        settings_path=settings_path,
        companies_yaml_path=companies_path,
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
        progress=progress,
    )

    assert result["ok"] is False
    assert result["api_error_status"] == 403
    assert any(
        event.get("type") == "thread_finished"
        and event.get("thread") == "Arithmetic / pressure tests"
        for event in progress.events
    )
    assert not any(
        event.get("type") == "thread_failed"
        and event.get("thread") == "Arithmetic / pressure tests"
        for event in progress.events
    )
    assert any(
        event.get("type") == "thread_failed"
        and event.get("thread") == claude_runner._MEMO_PHASE2_THREAD
        and "403 Request not allowed" in event.get("error", "")
        for event in progress.events
    )


def test_investment_memo_prompt_includes_phase_one_intake_discipline(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-23__082720",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "Phase 1 - intake and setup" in prompt
    assert "Do not use ToolSearch, TaskCreate" in prompt
    assert "first assistant turn after initialization" in prompt
    assert "`- id: zainar-inc`" in prompt
    assert "Do not waste a\npass searching for `slug:`." in prompt
    assert "read all relevant raw source files together" in " ".join(prompt.split())
    assert "Parallel execution of the eight orthogonal passes" in prompt


def test_investment_memo_prompt_can_embed_resolved_registry_entry(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-23__082720",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        company_registry_entry_yaml=(
            "id: zainar-inc\n"
            "name: ZaiNar, Inc.\n"
            "latest_funding:\n"
            "  round: Series A2\n"
        ),
    )

    assert "Resolved company registry entry" in prompt
    assert "Use this embedded YAML as the registry source for Phase 1" in prompt
    assert "id: zainar-inc" in prompt
    assert "round: Series A2" in prompt
    assert "Only locate the exact `- id: zainar-inc`" in prompt


def test_extract_company_registry_entry_yaml_supports_top_level_list(tmp_path):
    companies_path = tmp_path / "companies.yaml"
    companies_path.write_text(
        "- id: other\n"
        "  name: Other\n"
        "- id: zainar-inc\n"
        "  name: ZaiNar, Inc.\n"
        "  latest_funding:\n"
        "    round: Series A2\n",
        encoding="utf-8",
    )

    entry = claude_runner._extract_company_registry_entry_yaml(
        companies_path,
        "zainar-inc",
    )

    assert entry is not None
    assert "id: zainar-inc" in entry
    assert "round: Series A2" in entry
    assert "id: other" not in entry


def test_investment_memo_prompt_includes_human_exec_voice_contract(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "Human Executive Memo Voice Contract" in prompt
    assert "exec-ready LP-facing sell-side investment memo" in prompt
    assert "investment case under uncertainty" in prompt
    assert "first-person sponsor voice" in prompt
    assert "Open from the sponsor thesis" in prompt
    assert "Concrete positive writing patterns" in prompt
    assert "Rejected language categories" in prompt
    assert "We are being offered SPV exposure" in prompt
    assert "We recommend participating in the SPV because" in prompt
    assert "Revenue is not disclosed; our base case uses" in prompt
    assert "Make statements directly" in prompt
    assert "passive sponsor/counterparty capability speculation" in prompt
    assert "detached third-person recommendation or opportunity framing" in prompt
    assert "risk and valuation sensitivities" in prompt
    assert "Closing Confirmation Bars" in prompt
    assert "bsh_allocation" not in prompt
    assert "BSH target allocation" not in prompt
    assert "We would proceed if" not in prompt
    assert "Proceed if confirmed" in prompt
    assert "not revenue-recognized" in prompt
    assert "Final Prose QA Requirements" in prompt
    assert "Concrete negative examples to reject" not in prompt
    assert "The recommendation is" not in prompt
    assert "The opportunity offered to investors is" not in prompt
    assert "Our memo recommends" not in prompt
    assert "We outline the investment case below" not in prompt
    assert "Top 3 Decision Questions" not in prompt


def test_fast_english_package_prompt_includes_concrete_voice_guidance(
    tmp_path, monkeypatch
):
    captured = {}
    companies_path = tmp_path / "companies.yaml"
    companies_path.write_text(
        "- id: generalist-inc\n  name: Generalist, Inc.\n",
        encoding="utf-8",
    )

    def fake_run_json_artifact(**kwargs):
        captured.update(kwargs)
        return {"analysis_artifacts": {}, "memo_package": {}}, None

    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact",
        fake_run_json_artifact,
    )

    result, error = claude_runner.run_memo_fast_english_package(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=companies_path,
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    prompt = captured["prompt"]
    assert error is None
    assert result is not None
    assert "Human Executive Memo Voice Contract" in prompt
    assert "Concrete positive writing patterns" in prompt
    assert "Rejected language categories" in prompt
    assert "We are being offered SPV exposure" in prompt
    assert "We recommend participating in the SPV because" in prompt
    assert "passive sponsor/counterparty capability speculation" in prompt
    assert "Never use detached recommendation, opportunity" in prompt
    assert "Concrete negative examples to reject" not in prompt
    assert "The recommendation is" not in prompt
    assert "The memo frames this as a scarce technical asset" not in prompt
    assert "Our memo recommends" not in prompt
    assert "We outline the investment case below" not in prompt


def test_investment_memo_prompt_uses_fixed_docx_renderer(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "Fixed DOCX renderer contract" in prompt
    assert "logs/memo_package.json" in prompt
    assert "worker will invoke `server.memo_docx_renderer` directly" in prompt
    assert "Do not run `python -m" in prompt
    assert "Do **not** write or edit a per-run renderer script" in prompt
    assert "build_memo.py" in prompt
    assert "job is to author a complete `memo_package.json`" in prompt
    assert "not rendering code" in prompt


def test_investment_memo_prompt_bans_source_tokens_and_scaffold_labels(tmp_path):
    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="ZaiNar, Inc.",
        company_slug="zainar-inc",
        run_id="2026-06-22__093627",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
    )

    assert "supersedes any older skill instruction" in prompt
    assert "inline source markers" in prompt
    assert "Sources, Source Classes, and Fact Reference Index" in prompt
    assert "Memo spine requirement" in prompt
    assert "Critical Reality Check" in prompt
    assert "present-state" in prompt
    assert "upside-state" in prompt
    assert "soft instrument" in prompt
    assert "hard IP wall" in prompt
    assert "em dash bridging" in prompt
    assert "must include at least one inline citation marker" not in prompt
    assert "Render a **Critical Reality Check" not in prompt
    assert "Critical Reality Check (for BSH)** evidence-summary callout" not in prompt


def test_investment_memo_prompt_includes_serena_lessons(tmp_path):
    lessons_path = tmp_path / "serena_training" / "generalist" / "serena_memo_lessons.md"
    lessons_path.parent.mkdir(parents=True)
    lessons_path.write_text("# Lessons\n- Lead with evidence.\n", encoding="utf-8")

    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        lessons_path=lessons_path,
    )

    assert str(lessons_path) in prompt
    assert "Current company evidence" in prompt
    assert "override stale or contradictory lessons" in prompt


def test_internal_diligence_prompt_is_separate_internal_artifact(tmp_path):
    prompt = claude_runner._build_internal_diligence_memo_prompt(
        run_dir=tmp_path,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=tmp_path / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "memo" / "memo-en.docx"),
            "zh": str(tmp_path / "memo" / "memo-zh.docx"),
        },
        internal_markdown_path=tmp_path / "memo" / "internal.md",
    )

    assert "separate internal BSH diligence memo" in prompt
    assert "Output Markdown path" in prompt
    assert "Suggested allocation" in prompt
    assert "Do not edit `logs/memo_package.json`" in prompt
    assert "Write only the Markdown file" in prompt


def test_resume_memo_package_prompt_is_package_only(tmp_path):
    run_dir = tmp_path / "run"
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True)
    settings_path = tmp_path / "serena_background.md"
    settings_path.write_text("background", encoding="utf-8")
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nExisting analysis.",
        encoding="utf-8",
    )

    prompt = claude_runner._build_resume_memo_package_prompt(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=settings_path,
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
    )

    assert "resuming a previously interrupted" in prompt
    assert "write the missing structured" in prompt
    assert "memo package" in prompt
    assert "Do not rerun the analysis passes" in prompt
    assert "`analysis/pressure_tests.md`" in prompt
    assert "Use the existing run artifacts first" in prompt
    assert "narrow local validation step" in prompt
    assert "Do not inspect `server/`" in prompt
    assert "You may read only these exact supporting files" in prompt
    assert str(settings_path) in prompt
    assert "Write only" in prompt
    assert "logs/memo_package.json" in prompt
    assert "Do not write DOCX files" in prompt


def test_resume_memo_package_prompt_includes_quality_gate_feedback(tmp_path):
    run_dir = tmp_path / "run"
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True)
    settings_path = tmp_path / "serena_background.md"
    settings_path.write_text("background", encoding="utf-8")
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nExisting analysis.",
        encoding="utf-8",
    )
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    quality_lint_path.parent.mkdir(parents=True)
    quality_lint_path.write_text(
        "# Memo Quality Lint\n\nP0 sell_side_voice_violation\n",
        encoding="utf-8",
    )

    prompt = claude_runner._build_resume_memo_package_prompt(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=settings_path,
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
        quality_lint_path=quality_lint_path,
    )

    assert str(quality_lint_path) in prompt
    assert "failed the DOCX quality gate" in prompt
    assert "fix every P0 finding" in prompt
    assert "do not rerun analysis" in prompt
    assert "do not write DOCX files" in prompt


def test_resume_memo_package_prompt_uses_prior_package_as_draft(tmp_path):
    run_dir = tmp_path / "run"
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True)
    settings_path = tmp_path / "serena_background.md"
    settings_path.write_text("background", encoding="utf-8")
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nExisting analysis.",
        encoding="utf-8",
    )
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    prior_package_path = run_dir / "logs" / "memo_package.quality_failed.20260623T114731Z.json"
    quality_lint_path.parent.mkdir(parents=True)
    quality_lint_path.write_text(
        "# Memo Quality Lint\n\nP0 sell_side_voice_violation\n",
        encoding="utf-8",
    )
    prior_package_path.write_text(
        '{"schema_version": 1, "sections": [], "sources": []}',
        encoding="utf-8",
    )

    prompt = claude_runner._build_resume_memo_package_prompt(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=settings_path,
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
        quality_lint_path=quality_lint_path,
        prior_package_path=prior_package_path,
    )

    assert str(prior_package_path) in prompt
    assert "Use `" in prompt
    assert "as the working draft" in prompt
    assert "do not reread every analysis artifact by default" in prompt
    assert "After reading the quality report and prior draft" in prompt
    assert "corrections are clear" in prompt


def test_resume_progress_keeps_analysis_reads_in_phase_four():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE4_THREAD,
        "memo_phase_tracking": True,
        "resume_packaging": True,
    }

    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_read",
                        "name": "Read",
                        "input": {
                            "file_path": "/tmp/run/analysis/pressure_tests.md",
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )
    claude_runner._process_event(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_read",
                        "is_error": False,
                        "content": "# Pressure tests\n\nExisting analysis.",
                    }
                ]
            },
        },
        progress,
        state,
    )

    started_threads = {
        event.get("thread")
        for event in progress.events
        if event.get("type") == "thread_started"
    }
    assert claude_runner._MEMO_PHASE4_THREAD in started_threads
    assert claude_runner._MEMO_PHASE2_THREAD not in started_threads
    assert "Arithmetic / pressure tests" not in started_threads
    action_threads = {
        event.get("thread")
        for event in progress.events
        if event.get("type") == "claude_action"
    }
    assert action_threads == {claude_runner._MEMO_PHASE4_THREAD}


def test_resume_progress_emits_memo_package_writing_stage():
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE4_THREAD,
        "memo_phase_tracking": True,
        "resume_packaging": True,
    }

    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "I have all analysis artifacts and source materials. "
                            "Writing the memo package now."
                        ),
                    }
                ]
            },
        },
        progress,
        state,
    )

    stages = [event for event in progress.events if event.get("type") == "stage"]
    assert stages[-1]["stage"] == "memo_package_writing"
    assert stages[-1]["thread"] == claude_runner._MEMO_PHASE4_THREAD
    assert stages[-1]["message"] == (
        "Writing memo package from existing analysis artifacts"
    )


def test_resume_progress_emits_structured_package_write_stage(tmp_path):
    progress = _CaptureProgress()
    state = {
        "thread_map": claude_runner._MEMO_ANALYSIS_PASSES,
        "phase_thread": claude_runner._MEMO_PHASE4_THREAD,
        "memo_phase_tracking": True,
        "resume_packaging": True,
    }
    package_path = tmp_path / "run" / "logs" / "memo_package.json"

    claude_runner._process_event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_package",
                        "name": "Write",
                        "input": {
                            "file_path": str(package_path),
                            "content": '{"schema_version": 1, "sections": []}',
                        },
                    }
                ]
            },
        },
        progress,
        state,
    )

    stage = next(
        event
        for event in progress.events
        if event.get("stage") == "memo_package_write_started"
    )
    assert stage["thread"] == claude_runner._MEMO_PHASE4_THREAD
    assert stage["message"] == "Writing structured memo package"
    assert stage["content_chars"] == len('{"schema_version": 1, "sections": []}')


def test_resume_memo_package_runner_keeps_standard_memo_tooling(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "analysis").mkdir()
    (run_dir / "analysis" / "pressure_tests.md").write_text(
        "# Pressure tests\n\nExisting analysis.",
        encoding="utf-8",
    )
    (run_dir / "logs" / "memo_package.json").write_text(
        '{"schema_version": 1, "sections": [], "sources": []}',
        encoding="utf-8",
    )
    settings_path = tmp_path / "serena_background.md"
    companies_path = tmp_path / "companies.yaml"
    settings_path.write_text("background", encoding="utf-8")
    companies_path.write_text("companies: []", encoding="utf-8")

    result_event = {
        "type": "result",
        "subtype": "success",
        "total_cost_usd": 0.01,
        "duration_ms": 42,
    }

    class FakeProc:
        stdout = iter([json.dumps(result_event)])
        stderr = iter(())
        returncode = 0
        pid = 12345

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")

    captured = {}

    def fake_popen(args, **kwargs):
        captured["cmd"] = args
        return FakeProc()

    monkeypatch.setattr(claude_runner.subprocess, "Popen", fake_popen)
    progress = _CaptureProgress()

    result = claude_runner.run_resume_memo_package(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="2026-05-21__211535",
        settings_path=settings_path,
        companies_yaml_path=companies_path,
        memo_paths={
            "en": str(run_dir / "memo" / "memo-en.docx"),
            "zh": str(run_dir / "memo" / "memo-zh.docx"),
        },
        progress=progress,
    )

    assert result["ok"] is True
    planned_threads = [
        event["thread"]
        for event in progress.events
        if event.get("type") == "thread_planned"
    ]
    assert claude_runner._MEMO_PHASE1_THREAD not in planned_threads
    assert claude_runner._MEMO_PHASE2_THREAD not in planned_threads
    assert claude_runner._MEMO_PHASE4_THREAD in planned_threads
    assert claude_runner.MEMO_PHASE5_THREAD in planned_threads
    assert claude_runner.MEMO_PHASE6_THREAD in planned_threads
    assert "--allowedTools" in captured["cmd"]
    allowed = captured["cmd"][captured["cmd"].index("--allowedTools") + 1]
    assert allowed == "Read,Write,Edit,Bash,Grep,Glob"
    denied = captured["cmd"][captured["cmd"].index("--disallowedTools") + 1]
    assert "ToolSearch" in denied
    assert "TaskCreate" in denied
    assert "TodoWrite" in denied
