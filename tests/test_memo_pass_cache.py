"""The twelve Phase-2 passes must share one cached prompt block.

Before this, every pass repeated the registry entry, the research listing,
the fact ledger, the recent news and the decision record in its own user
message, so the run paid cache-creation for the same context twelve times.
The shared block rides --append-system-prompt, which only collapses into one
cache entry while the bytes are identical.
"""
from __future__ import annotations

from pathlib import Path

from server import claude_runner


def _ctx(tmp_path: Path, **over) -> str:
    kwargs = dict(
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        research_dir=tmp_path / "research",
        scope_check={"ok": True},
        warnings=["one warning"],
    )
    kwargs.update(over)
    return claude_runner.memo_fast_pass_common_context(**kwargs)


def test_the_shared_block_is_byte_identical_for_every_pass(tmp_path):
    first = _ctx(tmp_path)
    for _ in range(3):
        assert _ctx(tmp_path) == first


def test_the_shared_block_carries_the_run_wide_context_and_rules(tmp_path):
    ctx = _ctx(tmp_path)
    assert "Generalist, Inc." in ctx
    assert "Registry entry:" in ctx
    assert "Research folder:" in ctx
    assert "Scope check:" in ctx
    assert "one warning" in ctx
    assert "Hard output budget" in ctx
    assert "Do not write files." in ctx


def test_nothing_pass_specific_leaks_into_the_shared_block(tmp_path):
    """A pass id, label, focus or company-type addendum in here would give
    every pass a different block and cost the run its cache."""
    ctx = _ctx(tmp_path)
    for leak in ("Focus for this pass", "Artifact later written", "Pass: "):
        assert leak not in ctx


def test_each_pass_sends_the_shared_block_and_only_its_own_focus(
    tmp_path, monkeypatch
):
    captured: list[dict] = []

    def fake_runner(**kw):
        captured.append(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    shared = _ctx(tmp_path)
    for pass_id, label, focus in (
        ("time_base", "Time-base integrity", "Date-tag every valuation."),
        ("exit_paths", "Exit paths", "Map the realistic exits."),
    ):
        claude_runner.run_memo_fast_analysis_pass(
            run_dir=tmp_path / "memo-run",
            company_name="Generalist, Inc.",
            company_slug="generalist-inc",
            run_id="r1",
            pass_id=pass_id,
            pass_label=label,
            artifact_filename=f"{pass_id}.md",
            focus=focus,
            settings_path=tmp_path / "settings" / "serena_background.md",
            companies_yaml_path=tmp_path / "companies.yaml",
            research_dir=tmp_path / "research",
            common_context=shared,
        )

    assert [c["append_system_prompt"] for c in captured] == [shared, shared]
    assert "Date-tag every valuation." in captured[0]["prompt"]
    assert "Map the realistic exits." in captured[1]["prompt"]
    # The per-pass message stays small — that is the whole point.
    for call in captured:
        assert "Registry entry:" not in call["prompt"]
        assert len(call["prompt"]) < len(shared)


def test_a_caller_that_omits_the_shared_block_still_works(tmp_path, monkeypatch):
    """Resume paths and tests may call a pass on its own."""
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    claude_runner.run_memo_fast_analysis_pass(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        pass_id="time_base",
        pass_label="Time-base integrity",
        artifact_filename="time_base.md",
        focus="Date-tag every valuation.",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
    )
    assert "Registry entry:" in captured["append_system_prompt"]
