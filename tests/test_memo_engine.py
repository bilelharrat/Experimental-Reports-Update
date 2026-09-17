"""The memo engine toggle.

The contract that matters: a Gemini memo runs the same stage graph, prompts,
schemas, retries, repair passes, validation and renderer as a Claude memo.
Only the model differs, and the mechanism by which research reaches it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server import claude_runner, memo_engine

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ENGINE", raising=False)
    monkeypatch.delenv("BSH_MEMO_GEMINI_THINKING", raising=False)


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
        return {"answer": "ok"}, None

    monkeypatch.setattr(memo_engine.gemini_runner, "is_available", lambda: True)
    monkeypatch.setattr(memo_engine.gemini_runner, "run_structured_prompt", fake)

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
        return {"ok": True}, None

    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(monkeypatch_target, "is_available", lambda: True)
    mp.setattr(monkeypatch_target, "run_structured_prompt", fake)
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
        memo_engine.gemini_runner, "run_structured_prompt",
        lambda **kw: (seen.update(kw) or ({"ok": True}, None)),
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
