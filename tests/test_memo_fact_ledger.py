"""Tests for the per-company fact ledger (the fact-lottery fix).

The ledger is a hand-curated `fact_ledger.md` in the company's research
folder. When present, its text is injected verbatim into every analysis
pass, the spine (normal and speculative), and the monolithic English
fallback — but NOT the shared section context: pins stay the only channel
into section workers.
"""
from __future__ import annotations

from pathlib import Path

from server import claude_runner


def _write_ledger(root: Path, text: str = "- 2026-04-20: $500M+ contracted book; 95+ patents.") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / claude_runner.MEMO_FACT_LEDGER_FILENAME
    path.write_text(text, encoding="utf-8")
    return path


def test_loader_absent_empty_and_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    assert claude_runner.load_memo_fact_ledger(None) is None
    research = tmp_path / "research" / "generalist-inc"
    assert claude_runner.load_memo_fact_ledger(research) is None  # no dir
    research.mkdir(parents=True)
    assert claude_runner.load_memo_fact_ledger(research) is None  # no file
    (research / claude_runner.MEMO_FACT_LEDGER_FILENAME).write_text(
        "  \n\n", encoding="utf-8"
    )
    assert claude_runner.load_memo_fact_ledger(research) is None  # blank file
    _write_ledger(research, "  - a dated fact\n")
    assert claude_runner.load_memo_fact_ledger(research) == "- a dated fact"
    monkeypatch.setenv("BSH_MEMO_FACT_LEDGER", "0")
    assert claude_runner.load_memo_fact_ledger(research) is None  # kill switch


def test_loader_truncates_oversized_ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research, "x" * (claude_runner.MEMO_FACT_LEDGER_MAX_CHARS + 500))
    text = claude_runner.load_memo_fact_ledger(research)
    assert text is not None
    assert text.endswith("(fact ledger truncated)")
    assert len(text) <= claude_runner.MEMO_FACT_LEDGER_MAX_CHARS + 40


def test_block_rendering():
    assert claude_runner._memo_fact_ledger_block(None) == ""
    assert claude_runner._memo_fact_ledger_block("") == ""
    block = claude_runner._memo_fact_ledger_block("- fact one")
    assert "## Curated fact ledger" in block
    assert "- fact one" in block


def test_analysis_pass_prompt_carries_ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research)
    kwargs = dict(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        pass_id="time_base",
        pass_label="Time base",
        artifact_filename="time_base.md",
        focus="Check every time base.",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        research_dir=research,
    )
    claude_runner.run_memo_fast_analysis_pass(**kwargs)
    assert "## Curated fact ledger" in captured["prompt"]
    assert "$500M+ contracted book" in captured["prompt"]
    # Without a ledger the block must be absent.
    captured.clear()
    kwargs["research_dir"] = tmp_path / "research" / "other-co"
    claude_runner.run_memo_fast_analysis_pass(**kwargs)
    assert "Curated fact ledger" not in captured["prompt"]


def test_spine_prompt_carries_ledger_kwarg(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
        fact_ledger="- 2026-04-20: $500M+ contracted book.",
    )
    assert "## Curated fact ledger" in captured["prompt"]
    assert "$500M+ contracted book" in captured["prompt"]
    captured.clear()
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
    )
    assert "Curated fact ledger" not in captured["prompt"]


def test_monolithic_english_prompt_carries_ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research)
    claude_runner.run_memo_fast_english_package(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
    )
    assert "## Curated fact ledger" in captured["prompt"]


def test_common_section_context_stays_ledger_free(tmp_path, monkeypatch):
    """Sections are fed facts through the pin sheet only — the ledger must
    not leak into the shared context every section worker reads."""
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research)
    context = claude_runner._memo_english_common_context(
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        run_dir=tmp_path / "memo-run",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
        analysis_session_path=None,
        scope_check=None,
        warnings=None,
    )
    assert "Curated fact ledger" not in context
    assert "95+ patents" not in context


def test_wrapper_spine_call_threads_ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research)
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return None, "stop here"

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (None, "monolithic fallback declined"),
    )
    claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
    )
    assert spine_calls
    assert "$500M+ contracted book" in spine_calls[0]["fact_ledger"]


def test_speculative_spine_call_threads_ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_FACT_LEDGER", raising=False)
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_ledger(research)
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return None, "stop here"

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    spec = claude_runner.SpeculativeEnglish(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
        all_pass_ids=["a", "b", "c", "d", "e"],
        threshold=4,
    )
    for pass_id in ["a", "b", "c", "d"]:
        spec.note_pass_result(pass_id, True)
    spec.consume()
    spec.shutdown()
    assert spine_calls
    assert "$500M+ contracted book" in spine_calls[0]["fact_ledger"]
