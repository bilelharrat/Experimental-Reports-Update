"""The memo engine toggle.

The contract that matters: a Gemini memo runs the same stage graph, prompts,
schemas, retries, repair passes, validation and renderer as a Claude memo.
Only the model differs, and the mechanism by which research reaches it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from server import claude_runner, memo_engine, memo_structure

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ENGINE", raising=False)
    monkeypatch.delenv("BSH_MEMO_GEMINI_THINKING", raising=False)
    monkeypatch.delenv("BSH_MEMO_GEMINI_WORDS", raising=False)


# ---- selection ------------------------------------------------------------


def test_claude_is_the_default(tmp_path):
    assert memo_engine.default_engine() == "claude"
    assert memo_engine.run_engine(tmp_path) == "claude"


def test_a_run_pins_its_engine(tmp_path):
    assert memo_engine.register_run_engine(tmp_path, "gemini") == "gemini"
    assert memo_engine.run_engine(tmp_path) == "gemini"
    memo_engine.clear_run_engine(tmp_path)
    assert memo_engine.run_engine(tmp_path) == "claude"


def test_an_unknown_engine_falls_back_rather_than_failing_the_run(tmp_path):
    assert memo_engine.register_run_engine(tmp_path, "gpt-9") == "claude"
    assert memo_engine.register_run_engine(tmp_path, None) == "claude"


def test_the_env_default_can_be_moved(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGINE", "gemini")
    assert memo_engine.run_engine(tmp_path) == "gemini"


# ---- research inlining ----------------------------------------------------


def test_digests_and_analyses_come_before_raw_files(tmp_path):
    (tmp_path / "zz_raw_notes.md").write_text("raw notes", encoding="utf-8")
    (tmp_path / "deck_analysis.md").write_text("distilled brief", encoding="utf-8")
    (tmp_path / "fact_ledger.md").write_text("the ledger", encoding="utf-8")

    text = memo_engine.inline_research([tmp_path])
    assert text.index("the ledger") < text.index("distilled brief") < text.index("raw notes")


def test_index_and_progress_sidecars_are_skipped(tmp_path):
    (tmp_path / "index.yaml").write_text("rows: []", encoding="utf-8")
    (tmp_path / "deck.progress.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.md").write_text("real content", encoding="utf-8")
    text = memo_engine.inline_research([tmp_path])
    assert "real content" in text
    assert "index.yaml" not in text and "progress.jsonl" not in text


def test_truncation_is_announced_not_silent(tmp_path):
    (tmp_path / "long.md").write_text("x" * 5000, encoding="utf-8")
    text = memo_engine.inline_research([tmp_path], per_file=1000)
    assert "truncated at 1000 characters" in text
    assert len(text) < 3000


def test_a_file_dropped_for_budget_is_named(tmp_path):
    (tmp_path / "a_fact_ledger.md").write_text("y" * 900, encoding="utf-8")
    (tmp_path / "zzz_big.md").write_text("z" * 900, encoding="utf-8")
    text = memo_engine.inline_research([tmp_path], budget=1000, per_file=900)
    assert "NOT INCLUDED" in text
    assert "zzz_big.md (context budget reached)" in text
    # And the memo is told not to reason from what it cannot see.
    assert "do not assume their contents" in text


def test_an_unreadable_file_is_reported_rather_than_dropped_silently(tmp_path):
    """A scanned PDF has no text layer. A Claude agent could still describe
    the pages; here the memo must at least know the file existed."""
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    text = memo_engine.inline_research([tmp_path])
    assert "scan.pdf (no extractable text)" in text


def test_an_empty_research_folder_reads_like_the_claude_listing(tmp_path):
    assert "No research files found." in memo_engine.inline_research([tmp_path])
    assert "No research directory" in memo_engine.inline_research(None)


# ---- the artifact call ----------------------------------------------------


def test_the_prompt_and_schema_reach_gemini_unchanged(tmp_path, monkeypatch):
    """The whole point of the toggle: same prompt, same schema, other model."""
    (tmp_path / "fact_ledger.md").write_text("Revenue was $40M.", encoding="utf-8")
    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"answer": "ok"}, {}, None

    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        memo_engine.gemini_runner, "run_structured_prompt_with_meta", fake
    )

    data, error = memo_engine.run_artifact(
        prompt="THE MEMO PROMPT",
        schema=SCHEMA,
        add_dirs=[tmp_path],
        timeout_label="memo_stage",
        timeout_sec=600,
    )
    assert error is None and data == {"answer": "ok"}
    assert seen["schema"] is SCHEMA
    assert seen["user_prompt"].startswith("THE MEMO PROMPT")
    # The research is inlined, and the prompt says so — the memo prompts tell
    # the agent to open files, and there is no filesystem here.
    assert "Revenue was $40M." in seen["user_prompt"]
    assert "no file access" in seen["user_prompt"]
    assert seen["thinking_level"] == "high"


def test_a_missing_key_says_to_run_it_on_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: False)
    data, error = memo_engine.run_artifact(
        prompt="p", schema=SCHEMA, add_dirs=None,
        timeout_label="t", timeout_sec=60,
    )
    assert data is None
    assert "run this memo on Claude" in error


# ---- the funnel -----------------------------------------------------------


def test_the_funnel_routes_a_gemini_run_without_spawning_claude(tmp_path, monkeypatch):
    """Every memo stage, retry and repair pass goes through this one call."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact_inner",
        lambda **kw: pytest.fail("a gemini run must not spawn the Claude CLI"),
    )
    monkeypatch.setattr(
        memo_engine,
        "run_artifact",
        lambda **kw: ({"answer": "from gemini"}, None),
    )
    data, error = claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema=SCHEMA,
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=60,
    )
    assert error is None and data == {"answer": "from gemini"}


def test_a_gemini_run_is_not_blocked_by_a_missing_claude_cli(tmp_path, monkeypatch):
    """conftest forces the CLI unavailable, which is also the real case on a
    machine with no Claude login. That must not stop a Gemini memo."""
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    monkeypatch.setattr(claude_runner, "is_available", lambda: False)
    monkeypatch.setattr(memo_engine, "run_artifact", lambda **kw: ({"ok": True}, None))
    data, error = claude_runner._run_memo_local_json_artifact(
        prompt="p", schema=SCHEMA, run_dir=run_dir, progress=None,
        progress_message="m", timeout_label="t", timeout_sec=60,
    )
    assert error is None and data == {"ok": True}


def test_a_claude_run_still_refuses_without_the_cli(tmp_path, monkeypatch):
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "claude")
    monkeypatch.setattr(claude_runner, "is_available", lambda: False)
    data, error = claude_runner._run_memo_local_json_artifact(
        prompt="p", schema=SCHEMA, run_dir=run_dir, progress=None,
        progress_message="m", timeout_label="t", timeout_sec=60,
    )
    assert data is None and "not on PATH" in error


# ---- the run directory ----------------------------------------------------


def test_run_analysis_artifacts_are_found_in_their_subdirectory(tmp_path):
    """Most memo stages pass the RUN directory, and the artifacts the package
    stage is told to build on are written to `<run_dir>/analysis/*.md`. A flat
    listing finds none of them — which returned an 85-byte empty package on
    the first live run."""
    run = tmp_path / "run"
    (run / "analysis").mkdir(parents=True)
    (run / "analysis" / "market_sizing.md").write_text("TAM is $4B.", encoding="utf-8")
    (run / "analysis" / "exit_paths.md").write_text("Strategic buyers.", encoding="utf-8")
    (run / "manifest.md").write_text("run manifest", encoding="utf-8")

    text = memo_engine.inline_research([run])
    assert "TAM is $4B." in text
    assert "Strategic buyers." in text
    # Labelled by folder so an analysis artifact is distinguishable.
    assert "analysis/market_sizing.md" in text
    # And they outrank the run's own loose files.
    assert text.index("TAM is $4B.") < text.index("run manifest")


def test_run_plumbing_and_output_are_not_fed_back_in(tmp_path):
    """The event stream is enormous and the rendered DOCX is what the run is
    producing, not source material for it."""
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    (run / "memo").mkdir()
    (run / "previews").mkdir()
    (run / "logs" / "stream.jsonl").write_text('{"huge": "stream"}', encoding="utf-8")
    (run / "logs" / "memo_package.json").write_text('{"prior": "package"}', encoding="utf-8")
    (run / "memo" / "out.docx").write_bytes(b"docx bytes")
    (run / "previews" / "p.png").write_bytes(b"png")
    (run / "analysis").mkdir()
    (run / "analysis" / "keep.md").write_text("real analysis", encoding="utf-8")

    text = memo_engine.inline_research([run])
    assert "real analysis" in text
    for leaked in ("huge", "prior", "docx bytes"):
        assert leaked not in text


# ---- files the prompt names by path ---------------------------------------


def test_a_file_the_prompt_names_by_path_is_inlined_even_under_logs(tmp_path):
    """The repair passes hand the agent a path — `<run>/logs/memo_package.en.invalid.json`
    — and expect it opened. `logs/` is exactly what the folder walk skips, so
    on Gemini every repair pass ran blind: three attempts and a surgical
    repair "did not clear renderer validation" on a package it never saw."""
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    pkg = run / "logs" / "memo_package.en.invalid.json"
    pkg.write_text('{"sections": [{"id": "investment_risk"}]}', encoding="utf-8")
    (run / "logs" / "stream.jsonl").write_text('{"noise": true}', encoding="utf-8")

    prompt = f"Input package (fails renderer validation):\n`{pkg}`\n\nFix `investment_risk`."
    seen: dict = {}
    monkeypatch_target = memo_engine.gemini_runner

    def fake(**kw):
        seen.update(kw)
        return {"ok": True}, {}, None

    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(monkeypatch_target, "is_available", lambda: True)
    mp.setattr(monkeypatch_target, "run_structured_prompt_with_meta", fake)
    try:
        memo_engine.run_artifact(
            prompt=prompt, schema=SCHEMA, add_dirs=[run],
            timeout_label="repair", timeout_sec=60,
        )
    finally:
        mp.undo()

    sent = seen["user_prompt"]
    # Inlined under the path exactly as the prompt wrote it, so the
    # reference resolves; the event stream next to it stays excluded.
    assert f"=== FILE: {pkg} ===" in sent
    assert '"investment_risk"' in sent
    assert "noise" not in sent
    # A backticked identifier is not mistaken for a path.
    assert "=== FILE: investment_risk ===" not in sent


def test_a_referenced_file_is_not_inlined_twice_by_the_folder_walk(tmp_path):
    run = tmp_path / "run"
    (run / "analysis").mkdir(parents=True)
    art = run / "analysis" / "market_sizing.md"
    art.write_text("TAM is $4B.", encoding="utf-8")
    referenced, already = memo_engine.inline_referenced(f"Read `{art}` first.", [run])
    assert "TAM is $4B." in referenced
    walked = memo_engine.inline_research([run], already=already)
    assert "TAM is $4B." not in walked


def test_a_relative_path_resolves_against_the_run_dir(tmp_path):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    (run / "logs" / "quality_lint.json").write_text('{"p0": []}', encoding="utf-8")
    found = memo_engine.referenced_files("Read `logs/quality_lint.json` before writing.", [run])
    assert [as_written for as_written, _ in found] == ["logs/quality_lint.json"]


# ---- a dead Claude login --------------------------------------------------


def test_a_dead_login_halts_the_run_with_one_actionable_message(tmp_path, monkeypatch):
    """The CLI reports an expired OAuth session as an ordinary exit-1. Without
    this, all eight parallel passes spawn, fail identically and retry — a
    five-second diagnosis stretched into a five-minute doomed run."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    claude_runner.reset_run_dir_state(str(run_dir))
    memo_engine.register_run_engine(run_dir, "claude")
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    spawns: list[str] = []

    def dead_login(**kw):
        spawns.append(kw["timeout_label"])
        return None, "claude exited 1: Failed to authenticate: OAuth session expired and could not be refreshed"

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact_inner", dead_login)

    common = dict(schema=SCHEMA, run_dir=run_dir, progress=None, progress_message="m", timeout_sec=60)
    data, error = claude_runner._run_memo_local_json_artifact(prompt="p", timeout_label="pass_1", **common)
    assert data is None
    assert error == claude_runner.CLAUDE_NOT_SIGNED_IN_ERROR
    assert "log in" in error and "Gemini" in error

    # A sibling pass halts before spawning, with the same message.
    data2, error2 = claude_runner._run_memo_local_json_artifact(prompt="p", timeout_label="pass_2", **common)
    assert data2 is None and error2 == claude_runner.CLAUDE_NOT_SIGNED_IN_ERROR
    assert spawns == ["pass_1"]
    claude_runner.reset_run_dir_state(str(run_dir))


def test_auth_failure_reason_matches_the_cli_wordings():
    for text in (
        "Failed to authenticate: OAuth session expired and could not be refreshed",
        "Failed to authenticate. API Error: 401 Invalid authentication credentials",
        "Not logged in · please run /login",
    ):
        assert claude_runner.auth_failure_reason(text)
    assert claude_runner.auth_failure_reason("claude timed out after 900s") is None
    assert claude_runner.auth_failure_reason("") is None


# ---- model and path ---------------------------------------------------------


def test_the_claude_tier_model_never_reaches_gemini(tmp_path, monkeypatch):
    """The funnel's `model` is the Claude quality tier's role override
    ("sonnet" at the customizer's default tier). Passed through, Google
    would be asked for a model called "sonnet"."""
    monkeypatch.delenv("BSH_MEMO_GEMINI_MODEL", raising=False)
    monkeypatch.delenv("BSH_GEMINI_MODEL", raising=False)
    seen: dict = {}
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        memo_engine.gemini_runner, "run_structured_prompt_with_meta",
        lambda **kw: (seen.update(kw) or ({"ok": True}, {}, None)),
    )
    run_dir = tmp_path / "r"; run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact_inner",
        lambda **kw: pytest.fail("gemini run must not spawn the CLI"),
    )
    claude_runner._run_memo_local_json_artifact(
        prompt="p", schema=SCHEMA, run_dir=run_dir, progress=None,
        progress_message="m", timeout_label="t", timeout_sec=60,
        model="sonnet", effort="medium",
    )
    assert seen["model"] == "gemini-3.8-flash"


def test_memos_can_pin_their_own_gemini_model(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL", "gemini-3.8-pro")
    assert memo_engine.memo_gemini_model() == "gemini-3.8-pro"
    monkeypatch.delenv("BSH_MEMO_GEMINI_MODEL")
    monkeypatch.delenv("BSH_GEMINI_MODEL", raising=False)
    assert memo_engine.memo_gemini_model() == "gemini-3.8-flash"


def test_a_gemini_run_always_takes_the_per_section_wave(tmp_path, monkeypatch):
    """One monolithic call is where a Gemini memo's depth went (~2,700
    words against the ~12,200 of the benchmarked wave memos). Claude keeps
    the operator's flag."""
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    gem = tmp_path / "g"; gem.mkdir()
    cla = tmp_path / "c"; cla.mkdir()
    memo_engine.register_run_engine(gem, "gemini")
    memo_engine.register_run_engine(cla, "claude")
    assert claude_runner._memo_english_parallel_enabled(gem) is True
    assert claude_runner._memo_english_parallel_enabled(cla) is False
    assert claude_runner._memo_english_parallel_enabled(None) is False
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    assert claude_runner._memo_english_parallel_enabled(cla) is True


def test_a_gemini_run_always_takes_the_compact_chinese_method(tmp_path, monkeypatch):
    """The legacy method re-emits the whole unit, English included. Once the
    length contract brought the English up to the Claude reference, that
    doubled output hit Gemini's 64k response ceiling and the risk unit's
    translation failed outright. Claude keeps the operator's flag."""
    monkeypatch.delenv("BSH_MEMO_ZH_COMPACT", raising=False)
    gem = tmp_path / "g"; gem.mkdir()
    cla = tmp_path / "c"; cla.mkdir()
    memo_engine.register_run_engine(gem, "gemini")
    memo_engine.register_run_engine(cla, "claude")
    assert claude_runner._memo_zh_compact_enabled(gem) is True
    assert claude_runner._memo_zh_compact_enabled(cla) is False
    assert claude_runner._memo_zh_compact_enabled(None) is False
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    assert claude_runner._memo_zh_compact_enabled(cla) is True


def test_a_gemini_run_keeps_the_inline_spine_and_section_contracts(tmp_path, monkeypatch):
    """The spine and section handoffs deliver their parts as files on disk.
    Gemini has no filesystem: on the merge that made handoff the default,
    a live run failed at its first step with every spine part "never
    written". Claude keeps the operator's flags."""
    monkeypatch.delenv("BSH_MEMO_SPINE_HANDOFF", raising=False)
    monkeypatch.delenv("BSH_MEMO_SECTION_HANDOFF", raising=False)
    gem = tmp_path / "g"; gem.mkdir()
    cla = tmp_path / "c"; cla.mkdir()
    memo_engine.register_run_engine(gem, "gemini")
    memo_engine.register_run_engine(cla, "claude")
    section = memo_structure.load_structure("late", 2).section("executive_summary")
    assert len(section.subsections) > 1
    assert claude_runner._memo_spine_handoff_enabled(gem) is False
    assert claude_runner._section_handoff_enabled("executive_summary", section, gem) is False
    assert claude_runner._memo_spine_handoff_enabled(cla) is True
    assert claude_runner._section_handoff_enabled("executive_summary", section, cla) is True
    assert claude_runner._memo_spine_handoff_enabled(None) is True


# ---- Chinese translation on Gemini -----------------------------------------


def _bilingual_package():
    def loc(en):
        return {"en": en, "zh": ""}
    return {
        "schema_version": 1,
        "company": {"id": "acme", "name": "Acme"},
        "run": {"run_id": "r1", "date": "2026-09-17"},
        "sources": [{"id": "S1", "title": loc("Filing"), "url": "https://x"}],
        "sections": [
            {"id": "executive_summary", "title": loc("Executive Summary"),
             "blocks": [{"type": "paragraph", "text": loc("Acme sells widgets.")}]},
            {"id": "investment_risk", "title": loc("Investment Risk"),
             "blocks": [{"type": "paragraph", "text": loc("Concentration is high.")}]},
        ],
    }


def _translated(obj):
    """A zh-filled copy in the same shape, as a unit call returns it."""
    import copy
    out = copy.deepcopy(obj)
    def fill(x):
        if isinstance(x, dict):
            if "en" in x and "zh" in x and isinstance(x["en"], str) and x["en"]:
                x["zh"] = "中文：" + x["en"]
            for v in x.values(): fill(v)
        elif isinstance(x, list):
            for v in x: fill(v)
    fill(out)
    return out


def test_a_failed_chinese_unit_is_retried_not_replaced_by_the_whole_package_pass(tmp_path, monkeypatch):
    """Live: one section unit came back unparseable, and the wave fell back to
    the monolithic pass, which cannot fit a full memo in one Gemini response
    and failed on the output ceiling — reporting the wrong cause."""
    run_dir = tmp_path / "run"; (run_dir / "logs").mkdir(parents=True)
    memo_engine.register_run_engine(run_dir, "gemini")
    pkg_path = run_dir / "logs" / "memo_package.en.json"
    import json
    pkg_path.write_text(json.dumps(_bilingual_package()), encoding="utf-8")

    calls: dict = {}

    def fake_unit(*, unit_path, **kw):
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
        uid = unit.get("id") or "envelope"
        calls[uid] = calls.get(uid, 0) + 1
        if uid == "investment_risk" and calls[uid] == 1:
            return None, "gemini output didn't parse as JSON (name=memo Chinese package (section investment_risk))"
        return _translated(unit), None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package",
        lambda **kw: pytest.fail("must not fall back to the whole-package pass on Gemini"),
    )

    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=run_dir, company_name="Acme", run_id="r1",
        english_package_path=pkg_path, timeout_sec=10, max_workers=2,
    )
    assert error is None, error
    assert calls["investment_risk"] == 2, "the failed unit is retried once"
    assert calls["executive_summary"] == 1


def test_a_unit_that_fails_twice_reports_the_real_cause_on_gemini(tmp_path, monkeypatch):
    run_dir = tmp_path / "run2"; (run_dir / "logs").mkdir(parents=True)
    memo_engine.register_run_engine(run_dir, "gemini")
    pkg_path = run_dir / "logs" / "memo_package.en.json"
    import json
    pkg_path.write_text(json.dumps(_bilingual_package()), encoding="utf-8")
    monkeypatch.setattr(
        claude_runner, "_run_bilingual_unit",
        lambda *, unit_path, **kw: (None, "Invalid control character at line 3 column 9"),
    )
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package",
        lambda **kw: pytest.fail("no monolithic fallback on Gemini"),
    )
    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=run_dir, company_name="Acme", run_id="r1",
        english_package_path=pkg_path, timeout_sec=10, max_workers=2,
    )
    assert result is None
    assert "Invalid control character" in error
    assert "not attempted" in error


def test_claude_only_memo_stages_refuse_a_gemini_run_instead_of_spawning_the_cli(tmp_path, monkeypatch):
    """Four memo entry points drive the CLI as an agent and have no Gemini
    twin, so they never pass through the funnel where the toggle lives. A
    live Gemini run reached the resume agent and failed as "OAuth session
    expired" — the CLI's problem, reported on a run that never wanted it."""
    run_dir = tmp_path / "run"; run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    monkeypatch.setattr(
        claude_runner, "_popen_claude",
        lambda *a, **kw: pytest.fail("a gemini run must not spawn the Claude CLI"),
    )
    # Available on PATH, so only the engine guard can stop these.
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)

    common = dict(
        run_dir=run_dir, company_name="Acme", company_slug="acme", run_id="r1",
        settings_path=tmp_path / "s.md", companies_yaml_path=tmp_path / "c.yaml",
        memo_paths={}, research_dir=tmp_path,
    )
    for fn, extra in (
        (claude_runner.run_resume_memo_package, {}),
        (
            claude_runner.run_internal_diligence_memo,
            {"internal_markdown_path": tmp_path / "internal.md"},
        ),
    ):
        result = fn(**common, **extra)
        assert result["ok"] is False, fn.__name__
        assert "no Gemini equivalent" in result["error"]
        assert "Re-run it on Claude" in result["error"]


def test_a_claude_run_is_not_affected_by_the_guard(tmp_path, monkeypatch):
    run_dir = tmp_path / "run2"; run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "claude")
    assert claude_runner.claude_only_stage_error("Memo resume", run_dir) is None
    assert claude_runner.claude_only_stage_error("Memo resume", None) is None


# ---- permission roots ------------------------------------------------------


def test_a_granted_ancestor_of_the_run_contributes_only_this_companys_registry_entry(tmp_path):
    """`--add-dir data/` lets a Claude agent open companies.yaml; walking it
    inlined every file under data/. A live ZaiNar memo lost its founders,
    board and Tokyo office to other runs' artifacts that way."""
    data = tmp_path / "data"
    run = data / "memos" / "zainar-inc" / "run1"
    (run / "analysis").mkdir(parents=True)
    (run / "analysis" / "team_governance.md").write_text("CEO Daniel Jacker; board Steve Jurvetson.", encoding="utf-8")
    other = data / "memos" / "acme" / "run9" / "analysis"
    other.mkdir(parents=True)
    (other / "team_governance.md").write_text("Acme CEO Pat Smith.", encoding="utf-8")
    (data / "news_briefs").mkdir()
    (data / "news_briefs" / "x.json").write_text('{"headline": "Unrelated brief"}', encoding="utf-8")
    (data / "companies.yaml").write_text(
        "- id: acme\n  name: Acme\n  key_people:\n  - name: Pat Smith\n"
        "- id: zainar-inc\n  name: ZaiNar, Inc.\n  key_people:\n  - name: Daniel Jacker\n    role: CEO\n",
        encoding="utf-8",
    )
    settings = data / "settings"; settings.mkdir()
    (settings / "serena_background.md").write_text("Analyst background.", encoding="utf-8")

    text = memo_engine.inline_research([settings, data, run], run_dir=run)

    assert "Daniel Jacker" in text and "Jurvetson" in text
    assert "Analyst background." in text
    assert "entry `zainar-inc` only" in text
    # Nothing from the permission root but the registry entry.
    assert "Pat Smith" not in text
    assert "Unrelated brief" not in text
    # Only this run's analysis folder counts as "analysis".
    assert text.count("=== FILE: analysis/team_governance.md") == 1


def test_the_run_dir_itself_is_walked_not_treated_as_a_root(tmp_path):
    run = tmp_path / "run"; (run / "analysis").mkdir(parents=True)
    (run / "analysis" / "a.md").write_text("artifact", encoding="utf-8")
    assert memo_engine._is_permission_root(run, run) is False
    assert memo_engine._is_permission_root(tmp_path, run) is True
    assert memo_engine._is_permission_root(tmp_path / "elsewhere", run) is False
    assert "artifact" in memo_engine.inline_research([run], run_dir=run)


# ---- length parity with Claude ---------------------------------------------


def test_a_gemini_section_is_held_to_its_claude_twins_length(tmp_path):
    """The benchmarked Claude late-stage memos carry ~12,200 English words
    (docs/memo-benchmarks.md, Round 2); a Gemini run splits that total
    across the five sections, weighted by what each has to carry."""
    run = tmp_path / "g"
    run.mkdir()
    memo_engine.register_run_engine(run, "gemini")
    targets = memo_engine.section_word_targets(run, memo_structure.LATE)
    assert set(targets) == set(memo_structure.LATE.section_ids)
    assert sum(t.target for t in targets.values()) == memo_engine.CLAUDE_REFERENCE_WORDS
    for target in targets.values():
        assert target.low < target.target < target.high
    assert (
        targets["financial_forecast_valuation"].target
        > targets["executive_summary"].target
    )


def test_a_claude_run_gets_no_length_contract(tmp_path):
    run = tmp_path / "c"
    run.mkdir()
    memo_engine.register_run_engine(run, "claude")
    assert memo_engine.section_word_targets(run, memo_structure.LATE) == {}
    assert memo_engine.section_word_targets(None, memo_structure.LATE) == {}


def test_the_reference_length_can_be_moved_or_switched_off(tmp_path, monkeypatch):
    run = tmp_path / "g"
    run.mkdir()
    memo_engine.register_run_engine(run, "gemini")
    monkeypatch.setenv("BSH_MEMO_GEMINI_WORDS", "6,100")
    halved = memo_engine.section_word_targets(run, memo_structure.LATE)
    assert sum(t.target for t in halved.values()) == 6_100
    monkeypatch.setenv("BSH_MEMO_GEMINI_WORDS", "0")
    assert memo_engine.section_word_targets(run, memo_structure.LATE) == {}
    monkeypatch.setenv("BSH_MEMO_GEMINI_WORDS", "lots")
    unparsed = memo_engine.section_word_targets(run, memo_structure.LATE)
    assert sum(t.target for t in unparsed.values()) == memo_engine.CLAUDE_REFERENCE_WORDS


def test_a_profile_with_its_own_word_ranges_is_read_as_written(tmp_path):
    """growth.md says '600-800 words' for its summary; the contract repeats
    the profile's own range rather than imposing the late-stage split."""
    run = tmp_path / "g"
    run.mkdir()
    memo_engine.register_run_engine(run, "gemini")
    growth = memo_structure.load_structure("growth")
    targets = memo_engine.section_word_targets(run, growth)
    assert targets["executive_summary"] == memo_engine.WordTarget(
        target=700, low=600, high=800
    )
    assert set(targets) == set(growth.section_ids)


def test_a_profile_with_ceilings_gets_a_floor_under_them(tmp_path):
    """The compact profile states a target and a hard cap per section, and
    the renderer already rejects anything above the cap. What it never had
    is a FLOOR: Claude overshoots, so nobody needed one, and the gate
    skipped the profile the fund actually ships. Gemini fails the other
    way — a monolithic call came back at ~2,700 words — so a short section
    stood as written.

    The band is the profile's own numbers, so it cannot drift from what the
    Claude twin is asked for.
    """
    run = tmp_path / "g"
    run.mkdir()
    memo_engine.register_run_engine(run, "gemini")
    compact = memo_structure.load_structure("late_compact")
    targets = memo_engine.section_word_targets(run, compact)
    assert set(targets) == set(compact.section_ids)

    for section in compact.sections:
        band = targets[section.id]
        cap = int(
            section.budget_words
            * (section.budget_hard_multiple or memo_engine._BUDGET_GRACE)
        )
        # the target IS the Claude twin's budget, and the ceiling IS the
        # renderer's cap — no second opinion about either
        assert band.target == section.budget_words
        assert band.high == cap
        assert band.low == int(round(section.budget_words * 0.90))
        # a draft at the budget sits inside the band; a thin one does not
        assert band.distance(section.budget_words) == 0
        assert band.distance(int(section.budget_words * 0.5)) > 0


def test_the_floor_is_off_on_claude(tmp_path):
    """Claude overshoots and has the renderer's cap; it never sees this."""
    run = tmp_path / "c"
    run.mkdir()
    memo_engine.register_run_engine(run, "claude")
    compact = memo_structure.load_structure("late_compact")
    assert memo_engine.section_word_targets(run, compact) == {}


def test_en_word_count_counts_prose_bullets_and_table_cells():
    section = {
        "blocks": [
            {"type": "paragraph", "text": {"en": "one two three", "zh": "一二三"}},
            {"type": "bullets", "items": [{"en": "four five", "zh": ""}]},
            {
                "type": "table",
                "headers": [{"en": "six", "zh": ""}],
                "rows": [[{"en": "seven eight", "zh": ""}]],
            },
        ]
    }
    assert memo_engine.en_word_count(section) == 8
    assert memo_engine.en_word_count(None) == 0


def test_en_word_count_reads_a_raw_worker_draft_too():
    """Gemini's raw drafts carry plain strings under whatever keys the model
    chose; the repair step localizes them only later. The gate must count
    the draft as returned — a live run measured five full sections as 0."""
    raw = {
        "blocks": [
            {"type": "header", "level": 2, "text": "Executive framing"},
            {"id": "block_exec_thesis", "type": "paragraph", "content": "one two three four"},
            {"slug": "time_base_integrity", "title": "Timing", "content": "five six"},
            {
                "type": "table",
                "title": "Board",
                "headers": ["Name", "Role"],
                "rows": [["Ada", "Chair"]],
            },
            {"type": "bullet_list", "items": ["seven eight nine"]},
            {"type": "chart", "series": [{"name": "ARR", "values": [1, 2]}]},
        ]
    }
    assert memo_engine.en_word_count(raw) == 17


def test_renderable_count_ignores_words_the_renderer_cannot_use():
    """The depth gate must measure what the reader gets, not what the worker
    returned. Live on 2026-09-19 a Gemini `thesis_market` counted 3,753
    words against a 2,610 floor while the renderer could use 1,625. The
    other 2,128 sat in shapes Gemini invented — a bullet item given as
    `{"title": ..., "text": ...}` rather than a localized string, which the
    repair step does not wrap — so the section shipped ~1,000 words short
    and no depth round ever fired.
    """
    section = {
        "blocks": [
            {"type": "paragraph", "text": {"en": "one two three", "zh": ""}},
            {
                "type": "bullet_list",
                "items": [
                    {"title": "four five", "text": "six seven eight nine"},
                    {"title": "ten eleven", "text": "twelve thirteen"},
                ],
            },
        ]
    }
    # Counting the draft as returned sees all of it.
    assert memo_engine.en_word_count(section) == 13
    # The renderer can only use the one properly localized paragraph.
    assert memo_engine.renderable_en_word_count(section) == 3
    assert memo_engine.renderable_en_word_count(None) == 0


def test_renderable_count_still_reads_a_raw_worker_draft():
    """The reason en_word_count counts plain strings must survive: a raw
    draft is repaired before counting, so it does not read as 0."""
    raw = {
        "blocks": [
            {"type": "paragraph", "text": "one two three four five"},
            {"type": "bullet_list", "items": ["six seven eight"]},
        ]
    }
    from server import memo_docx_renderer

    assert memo_docx_renderer.section_en_word_count(raw) == 0
    assert memo_engine.renderable_en_word_count(raw) == 8


def test_a_gemini_section_worker_drafts_under_the_length_contract(tmp_path, monkeypatch):
    prompts: list[str] = []

    def fake_artifact(**kw):
        prompts.append(kw["prompt"])
        return {"section": {"id": "investment_risk", "blocks": []}}, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_artifact)

    def draft(run: Path, **extra):
        (run / "logs").mkdir(parents=True, exist_ok=True)
        spine = run / "logs" / "spine.json"
        spine.write_text("{}")
        return claude_runner._run_english_section(
            run_dir=run,
            section_id="investment_risk",
            common_context="",
            shared_facts_block="## Shared fact sheet",
            spine_path=spine,
            add_dirs=[run],
            progress=None,
            timeout_sec=10,
            **extra,
        )

    gem = tmp_path / "g"
    memo_engine.register_run_engine(gem, "gemini")
    _result, error = draft(gem)
    assert error is None
    target = memo_engine.section_word_targets(gem, memo_structure.LATE)["investment_risk"]
    assert "## Length contract" in prompts[-1]
    assert f"{target.low:,}–{target.high:,} English words" in prompts[-1]

    # Short draft -> deepen. Long draft -> tighten. The worker reads the
    # direction off the same band the gate used, so they cannot disagree.
    draft_path = gem / "logs" / "investment_risk.length-1.json"
    draft_path.write_text('{"id": "investment_risk", "blocks": []}')

    draft(gem, depth_revision=(draft_path, target.low - 400))
    assert "## Length extension" in prompts[-1]
    assert f"{target.low - 400:,} English" in prompts[-1]
    assert str(draft_path) in prompts[-1]
    assert "## Length contract" not in prompts[-1]

    draft(gem, depth_revision=(draft_path, target.high + 900))
    assert "## Length trim" in prompts[-1]
    assert f"{target.high + 900:,} English" in prompts[-1]
    assert "## Length extension" not in prompts[-1]

    cla = tmp_path / "c"
    memo_engine.register_run_engine(cla, "claude")
    draft(cla)
    assert "## Length contract" not in prompts[-1]
    assert "## Length extension" not in prompts[-1]
    assert "## Length trim" not in prompts[-1]


def test_the_band_distance_scores_both_directions():
    target = memo_engine.WordTarget(target=2_400, low=2_160, high=2_760)
    assert target.distance(2_400) == 0
    assert target.distance(2_160) == 0 and target.distance(2_760) == 0
    assert target.distance(1_900) == 260
    assert target.distance(3_000) == 240
    # Closer to the band scores lower: what the gate keeps a revision on.
    assert target.distance(2_900) < target.distance(4_500)


def test_the_trim_pass_forbids_cutting_content_rather_than_words():
    """Gemini overran the reference by a quarter on the first live run under
    the contract (13,958 English words against 12,200), so the trim exists —
    but a shorter memo that dropped a table or softened a risk is a worse
    memo, not a compliant one."""
    target = memo_engine.WordTarget(target=3_200, low=2_880, high=3_680)
    block = memo_engine.length_condense(target, Path("/tmp/draft.json"), 5_087)
    assert "5,087 English" in block and "2,880–3,680" in block
    for promise in ("every table and every row", "same order", "Cut only words, never content"):
        assert promise in block
    for forbidden in ("drop a subsection heading", "summarize a table", "soften a risk"):
        assert forbidden in block


def _split_draft(run: Path, section_id: str, structure, **extra):
    (run / "logs").mkdir(parents=True, exist_ok=True)
    spine = run / "logs" / "spine.json"
    spine.write_text("{}")
    return claude_runner._run_english_section(
        run_dir=run,
        section_id=section_id,
        common_context="",
        shared_facts_block="## Shared fact sheet",
        spine_path=spine,
        add_dirs=[run],
        progress=None,
        timeout_sec=10,
        structure=structure,
        **extra,
    )


def test_gemini_drafts_a_section_one_call_per_subsection(tmp_path, monkeypatch):
    """A whole section in one Gemini response is all-or-nothing: on
    2026-09-19 a valuation_returns ran past the 64k output ceiling and lost
    every word, and a malformed thesis_market cost the entire wave a respin.
    Claude splits a section into files for the same reason; Gemini has no
    filesystem, so it splits into calls."""
    structure = memo_structure.load_structure("late_compact", 1)
    section_def = structure.section("thesis_market")
    headings = [f"{n}. {s.en}" for n, s in enumerate(section_def.subsections, 1)]
    assert len(headings) > 1

    prompts: list[str] = []

    def fake_artifact(**kw):
        prompts.append(kw["prompt"])
        number = len(prompts)
        return (
            {
                "piece": number,
                "blocks": [
                    {
                        "type": "heading",
                        "level": 2,
                        "text": {"en": headings[number - 1], "zh": "标题"},
                    },
                    {"type": "paragraph", "text": {"en": "body", "zh": "正文"}},
                ],
            },
            None,
        )

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )

    gem = tmp_path / "g"
    memo_engine.register_run_engine(gem, "gemini")
    result, error = _split_draft(gem, "thesis_market", structure)

    assert error is None
    # One call per subsection, not one for the section.
    assert len(prompts) == len(headings)
    # Every piece assembled, in plan order.
    blocks = result["section"]["blocks"]
    assert [
        b["text"]["en"] for b in blocks if b.get("type") == "heading"
    ] == headings
    assert len(blocks) == 2 * len(headings)

    # Each call is told to write exactly one subsection...
    for index, heading in enumerate(headings):
        assert f'Write subsection {index + 1} ("{heading}"' in prompts[index]
    # ...under its own share of the band, never the whole section's.
    section_target = memo_engine.section_word_targets(gem, structure)[
        "thesis_market"
    ]
    piece_target = memo_engine.split_target(section_target, len(headings))
    assert f"{piece_target.low:,}–{piece_target.high:,} English words" in prompts[0]
    assert (
        f"{section_target.low:,}–{section_target.high:,} English words"
        not in prompts[0]
    )
    # A later call can see what the earlier ones wrote, the way one Claude
    # agent writing all the files can.
    assert "already written" not in prompts[0]
    assert "already written" in prompts[1]

    # The OTHER length instruction has to be divided too. Live on
    # 2026-09-19 it was not: every piece was told the section is N words
    # and that this figure overrides the range it had just been given, and
    # six of seven sections came back about a third of their length.
    section_words = structure.section("thesis_market").budget_words
    piece_words = int(round(section_words / len(headings)))
    assert f"Target: {piece_words} words of English for this ONE subsection" in prompts[0]
    assert f"Target: {section_words} words" not in prompts[0]


def test_a_bad_subsection_reply_costs_only_that_subsection(tmp_path, monkeypatch):
    """The point of the split: a failure costs one subsection, not the
    section. A whole-section call had to be thrown away entire."""
    structure = memo_structure.load_structure("late_compact", 1)
    section_def = structure.section("thesis_market")
    headings = [f"{n}. {s.en}" for n, s in enumerate(section_def.subsections, 1)]

    asked: list[int] = []

    def fake_artifact(**kw):
        number = int(
            re.search(r"Write subsection (\d+)", kw["prompt"]).group(1)
        )
        first_try = number not in asked
        asked.append(number)
        if number == 2 and first_try:
            # Headless: the one defect that costs a retry.
            return {"piece": 2, "blocks": [{"type": "paragraph"}]}, None
        return (
            {
                "piece": number,
                "blocks": [
                    {
                        "type": "heading",
                        "level": 2,
                        "text": {"en": headings[number - 1], "zh": "标题"},
                    }
                ],
            },
            None,
        )

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    gem = tmp_path / "g2"
    memo_engine.register_run_engine(gem, "gemini")
    result, error = _split_draft(gem, "thesis_market", structure)

    assert error is None
    # One extra call — the retry — not a whole section redrafted.
    assert asked == [1, 2, 2, 3]
    assert len(result["section"]["blocks"]) == len(headings)


def test_claude_never_takes_the_per_call_split(tmp_path, monkeypatch):
    structure = memo_structure.load_structure("late_compact", 1)
    prompts: list[str] = []

    def fake_artifact(**kw):
        prompts.append(kw["prompt"])
        return {"section": {"id": "thesis_market", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    monkeypatch.setattr(claude_runner, "_section_handoff_enabled", lambda *a, **k: False)
    cla = tmp_path / "c2"
    memo_engine.register_run_engine(cla, "claude")
    _result, error = _split_draft(cla, "thesis_market", structure)
    assert error is None
    assert len(prompts) == 1
    assert "Write ONE subsection" not in prompts[0]
    # A single-call section still states its own whole budget.
    section_words = structure.section("thesis_market").budget_words
    assert f"Target: {section_words} words of English for this whole" in prompts[0]


def _headed(headings, words_each=3):
    """An assembled section: one heading block per subsection, each followed
    by a paragraph."""
    blocks = []
    for index, heading in enumerate(headings):
        blocks.append(
            {"type": "heading", "level": 2, "text": {"en": heading, "zh": "标题"}}
        )
        blocks.append(
            {
                "type": "paragraph",
                "text": {"en": " ".join(["w"] * words_each), "zh": "正文"},
            }
        )
    return {"id": "thesis_market", "blocks": blocks}


def test_a_length_revision_is_split_too(tmp_path, monkeypatch):
    """A lengthening revision is the biggest call in a Gemini run — it
    restates the whole section and then some. Left whole it was the one call
    with no partial credit, and on 2026-09-19 a company_team revision died on
    one bad token at 38,544 characters and lost the round."""
    structure = memo_structure.load_structure("late_compact", 1)
    section_def = structure.section("thesis_market")
    headings = [f"{n}. {s.en}" for n, s in enumerate(section_def.subsections, 1)]

    prompts: list[str] = []

    def fake_artifact(**kw):
        prompts.append(kw["prompt"])
        number = int(re.search(r"Write subsection (\d+)", kw["prompt"]).group(1))
        return (
            {
                "piece": number,
                "blocks": [
                    {
                        "type": "heading",
                        "level": 2,
                        "text": {"en": headings[number - 1], "zh": "标题"},
                    }
                ],
            },
            None,
        )

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    gem = tmp_path / "g3"
    memo_engine.register_run_engine(gem, "gemini")
    (gem / "logs").mkdir(parents=True, exist_ok=True)
    draft_path = gem / "logs" / "thesis_market.length-1.json"
    draft_path.write_text(
        json.dumps(_headed(headings)), encoding="utf-8"
    )

    _result, error = _split_draft(
        gem, "thesis_market", structure, depth_revision=(draft_path, 9)
    )
    assert error is None
    # Still one call per subsection, not one call carrying the whole draft.
    assert len(prompts) == len(headings)
    # Each call revises its OWN slice, written beside the draft.
    for index in range(len(headings)):
        slice_path = draft_path.with_name(
            f"{draft_path.stem}.piece-{index + 1:02d}.json"
        )
        assert slice_path.exists()
        assert str(slice_path) in prompts[index]
        assert "## Length extension" in prompts[index]
    # And no call is handed the whole draft.
    assert all(str(draft_path) not in prompt for prompt in prompts)


def test_an_uncuttable_draft_is_revised_whole(tmp_path, monkeypatch):
    """A draft whose headings do not line up with the plan is revised as one
    call rather than sliced wrongly."""
    structure = memo_structure.load_structure("late_compact", 1)
    prompts: list[str] = []

    def fake_artifact(**kw):
        prompts.append(kw["prompt"])
        return {"section": {"id": "thesis_market", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    gem = tmp_path / "g4"
    memo_engine.register_run_engine(gem, "gemini")
    (gem / "logs").mkdir(parents=True, exist_ok=True)
    draft_path = gem / "logs" / "thesis_market.length-1.json"
    draft_path.write_text(
        json.dumps(_headed(["Something Else Entirely"])), encoding="utf-8"
    )

    _result, error = _split_draft(
        gem, "thesis_market", structure, depth_revision=(draft_path, 9)
    )
    assert error is None
    assert len(prompts) == 1
    assert "Write ONE subsection" not in prompts[0]
    assert str(draft_path) in prompts[0]


# ---- web research on Gemini --------------------------------------------------
# Until 2026-09-21 no Gemini memo call was grounded: every research pass
# answered from the inlined registry and the model's memory, so its URLs
# were remembered rather than found, and the source cache and fact check
# saw nothing. A research pass now searches, and the pages it found are
# fetched at their real addresses and stored like a Claude WebFetch.


def _grounded_fake(seen: dict, meta: dict | None = None):
    def fake(**kwargs):
        seen.update(kwargs)
        found = meta or {
            "sources": [{"title": "acme.example", "url": "https://acme.example/about"}],
            "queries": ["acme"],
            "grounded": True,
        }
        seen["addendum"] = kwargs["notes_addendum"](found)
        return {"answer": "ok"}, found, None

    return fake


def test_a_research_pass_searches_and_hands_over_real_pages(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_GEMINI_WEB_RESEARCH", raising=False)
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    seen: dict = {}
    monkeypatch.setattr(memo_engine.gemini_runner, "run_grounded_json", _grounded_fake(seen))
    monkeypatch.setattr(
        memo_engine,
        "fetch_grounded_pages",
        lambda meta, run_dir: [{"title": "About Acme", "url": "https://acme.example/about"}],
    )

    data, error = memo_engine.run_artifact(
        prompt="THE PASS PROMPT",
        schema=SCHEMA,
        add_dirs=[tmp_path],
        timeout_label="memo pass market_sizing",
        timeout_sec=600,
        web_research=True,
    )
    assert error is None and data == {"answer": "ok"}
    # The structuring step is told the pass's own instructions...
    assert seen["task_context"] == "THE PASS PROMPT"
    # ...and gets the pages at their real addresses to cite.
    assert "About Acme — https://acme.example/about" in seen["addendum"]


def test_a_writing_stage_does_not_search(tmp_path, monkeypatch):
    """Sections, the spine and repairs write from the research; only the
    research passes go to the web."""
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        memo_engine.gemini_runner,
        "run_grounded_json",
        lambda **_k: pytest.fail("a writing stage must not search"),
    )
    monkeypatch.setattr(
        memo_engine.gemini_runner,
        "run_structured_prompt_with_meta",
        lambda **_k: ({"answer": "ok"}, {}, None),
    )
    data, error = memo_engine.run_artifact(
        prompt="p", schema=SCHEMA, add_dirs=[tmp_path], timeout_label="spine", timeout_sec=60
    )
    assert error is None and data == {"answer": "ok"}


def test_web_research_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GEMINI_WEB_RESEARCH", "0")
    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        memo_engine.gemini_runner,
        "run_grounded_json",
        lambda **_k: pytest.fail("switched off"),
    )
    monkeypatch.setattr(
        memo_engine.gemini_runner,
        "run_structured_prompt_with_meta",
        lambda **_k: ({"answer": "ok"}, {}, None),
    )
    _data, error = memo_engine.run_artifact(
        prompt="p", schema=SCHEMA, add_dirs=[tmp_path], timeout_label="pass",
        timeout_sec=60, web_research=True,
    )
    assert error is None


def test_grounded_pages_are_fetched_at_their_real_address_and_stored(tmp_path, monkeypatch):
    """Gemini reports pages as links through Google's redirector. Each is
    followed to where it lands, and a page with text is stored in the
    company cache and the run's manifest, like a Claude WebFetch."""
    from server import claude_runner, link_preview, source_cache

    redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbC"
    monkeypatch.setattr(
        link_preview,
        "fetch",
        lambda url: link_preview.LinkPreview(
            url=url,
            final_url="https://acme.example/news/seed",
            title="Acme raises a seed round",
            text="Acme raised $100M in its seed round, led by Example Ventures. " * 3,
        ),
    )
    recorded: list[dict] = []
    monkeypatch.setattr(
        source_cache, "record_run_source", lambda *a, **k: recorded.append(k) or {}
    )
    monkeypatch.setattr(source_cache, "write_known_sources_file", lambda *a, **k: True)
    monkeypatch.setattr(
        claude_runner,
        "memo_run_source_capture",
        lambda _rd: {"company_id": "acme", "run_id": "r1", "research_dir": tmp_path},
    )

    pages = memo_engine.fetch_grounded_pages(
        {"sources": [{"title": "acme.example", "url": redirect}]}, tmp_path
    )
    assert pages == [{"title": "Acme raises a seed round", "url": "https://acme.example/news/seed"}]
    assert len(recorded) == 1
    assert recorded[0]["tool"] == "GroundedFetch"
    assert recorded[0]["url"] == "https://acme.example/news/seed"


def test_a_page_that_never_left_the_redirector_is_dropped(tmp_path, monkeypatch):
    from server import link_preview

    redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/XyZ"
    monkeypatch.setattr(
        link_preview,
        "fetch",
        lambda url: link_preview.LinkPreview(url=url, final_url=url, error="Fetch failed"),
    )
    monkeypatch.setattr(memo_engine, "_resolve_only", lambda _url: None)
    assert memo_engine.fetch_grounded_pages({"sources": [{"url": redirect}]}, None) == []


def test_the_research_passes_ask_for_web_research(tmp_path, monkeypatch):
    """The flag has to be set where the passes are launched, or the Gemini
    branch never sees it and every pass answers from memory again."""
    seen: dict = {}
    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact",
        lambda **kwargs: seen.update(kwargs) or ({}, None),
    )
    (tmp_path / "companies.yaml").write_text("companies: []\n", encoding="utf-8")
    (tmp_path / "background.md").write_text("bg", encoding="utf-8")
    claude_runner.run_memo_fast_analysis_pass(
        run_dir=tmp_path,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        pass_id="market_sizing",
        pass_label="Market sizing",
        artifact_filename="market_sizing.md",
        focus="size the market",
        settings_path=tmp_path / "background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        common_context="shared",
    )
    assert seen["web_research"] is True
