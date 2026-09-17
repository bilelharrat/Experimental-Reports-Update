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
