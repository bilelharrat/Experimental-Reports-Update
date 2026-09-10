"""Tests for the human decision-record digest feeding the memo pipeline.

``decision_record.md`` mirrors the tracked-news digest exactly: rendered
from the decisions store into the research folder by the memo workers
before Phase 2, it reaches every analysis pass and the spine — but NOT
the shared section context (pins stay the only fact channel into section
workers).
"""
from __future__ import annotations

from pathlib import Path

from server import claude_runner, decisions_store, memo_analysis, storage


def _write_record(root: Path, text: str = "- Decision: pass — decided 2026-01-05") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / claude_runner.MEMO_DECISION_RECORD_FILENAME
    path.write_text(text, encoding="utf-8")
    return path


def _seed_decision(company_id: str = "zainar-inc"):
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    decisions_store.add_decision(
        company_id,
        verdict="pass",
        explanation="Valuation too rich at the 2026 round.",
        decided_at="2026-01-05",
        created_by="Ben",
    )
    return company_id


def test_loader_absent_empty_and_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_DECISION_RECORD", raising=False)
    assert claude_runner.load_memo_decision_record(None) is None
    research = tmp_path / "research" / "generalist-inc"
    assert claude_runner.load_memo_decision_record(research) is None  # no dir
    research.mkdir(parents=True)
    assert claude_runner.load_memo_decision_record(research) is None  # no file
    _write_record(research)
    assert "pass" in (claude_runner.load_memo_decision_record(research) or "")
    monkeypatch.setenv("BSH_MEMO_DECISION_RECORD", "0")
    assert claude_runner.load_memo_decision_record(research) is None  # kill switch


def test_loader_truncates_oversized_digest(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_DECISION_RECORD", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_record(
        research, "x" * (claude_runner.MEMO_DECISION_RECORD_MAX_CHARS + 500)
    )
    text = claude_runner.load_memo_decision_record(research)
    assert text is not None
    assert text.endswith("(decision record truncated)")


def test_block_rendering_empty_is_byte_identical():
    assert claude_runner._memo_decision_record_block(None) == ""
    assert claude_runner._memo_decision_record_block("") == ""
    block = claude_runner._memo_decision_record_block("- Decision: pass")
    assert "## BSH decision record" in block
    assert "factual history" in block
    assert "- Decision: pass" in block


def test_analysis_pass_prompt_carries_decision_record(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_DECISION_RECORD", raising=False)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    research = tmp_path / "research" / "generalist-inc"
    _write_record(research)
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
    assert "## BSH decision record" in captured["prompt"]
    assert "decided 2026-01-05" in captured["prompt"]
    captured.clear()
    kwargs["research_dir"] = tmp_path / "research" / "other-co"
    claude_runner.run_memo_fast_analysis_pass(**kwargs)
    assert "BSH decision record" not in captured["prompt"]


def test_spine_prompt_carries_decision_record_kwarg(tmp_path, monkeypatch):
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
        decision_record="- Decision: pass — decided 2026-01-05",
    )
    assert "## BSH decision record" in captured["prompt"]
    captured.clear()
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
    )
    assert "BSH decision record" not in captured["prompt"]


def test_common_section_context_stays_decision_free(tmp_path, monkeypatch):
    """Sections are fed facts through the pin sheet only — the decision
    record must not leak into the shared context every section reads."""
    monkeypatch.delenv("BSH_MEMO_DECISION_RECORD", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_record(research)
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
    assert "BSH decision record" not in context
    assert "decided 2026-01-05" not in context


def test_wrapper_spine_call_threads_decision_record(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_DECISION_RECORD", raising=False)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    research = tmp_path / "research" / "generalist-inc"
    _write_record(research)
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
    assert "decided 2026-01-05" in spine_calls[0]["decision_record"]


def test_write_decision_record_file_and_best_effort(tmp_path, monkeypatch):
    company_id = _seed_decision()
    research = tmp_path / "research" / company_id
    memo_analysis._write_decision_record_file(company_id, research)
    written = research / claude_runner.MEMO_DECISION_RECORD_FILENAME
    assert written.exists()
    assert "Valuation too rich" in written.read_text(encoding="utf-8")

    # A broken store must never raise into the memo worker.
    def _boom(*_a, **_kw):
        raise RuntimeError("store corrupted")

    monkeypatch.setattr(decisions_store, "render_decision_record_md", _boom)
    memo_analysis._write_decision_record_file(company_id, research)  # no raise

    # Empty store leaves an existing digest alone.
    monkeypatch.setattr(
        decisions_store, "render_decision_record_md", lambda *_a, **_kw: None
    )
    memo_analysis._write_decision_record_file(company_id, research)
    assert written.exists()
