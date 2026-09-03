"""Tests for the tracked-news digest feeding the memo pipeline.

``recent_news.md`` is rendered from the tracking-updates store into the
company's research folder by the memo workers before Phase 2. Like the
fact ledger, it reaches every analysis pass and the spine — but NOT the
shared section context: pins stay the only fact channel into section
workers.
"""
from __future__ import annotations

from pathlib import Path

from server import claude_runner, memo_analysis, storage, tracking_updates


def _write_news(root: Path, text: str = "- [2026-01-05] (high) ZaiNar raises Series C") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / claude_runner.MEMO_RECENT_NEWS_FILENAME
    path.write_text(text, encoding="utf-8")
    return path


def _seed_tracking_items(tmp_path, monkeypatch, company_id: str = "zainar-inc"):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    storage.update_company(
        company_id,
        company_news=[
            {
                "title": "ZaiNar raises Series C financing",
                "summary": "New capital for expansion",
                "url": "https://example.com/zainar-series-c",
                "published_at": "2026-01-05",
            },
            {
                "title": "Quiet industry appearance",
                "summary": "Low-impact item",
                "url": "https://example.com/zainar-quiet",
                "published_at": "2026-01-04",
            },
        ],
    )
    tracking_updates.sync_from_news_feed(company_id)
    return company_id


def test_renderer_empty_store_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    assert tracking_updates.render_research_news_md("zainar-inc") is None


def test_renderer_formats_items_with_impact(tmp_path, monkeypatch):
    company_id = _seed_tracking_items(tmp_path, monkeypatch)
    text = tracking_updates.render_research_news_md(company_id)
    assert text is not None
    assert text.startswith("# Recent tracked news")
    assert "(high) ZaiNar raises Series C financing" in text
    assert "New capital for expansion" in text
    assert "https://example.com/zainar-series-c" in text


def test_renderer_enforces_char_cap(tmp_path, monkeypatch):
    company_id = _seed_tracking_items(tmp_path, monkeypatch)
    text = tracking_updates.render_research_news_md(company_id, max_chars=80)
    assert text is not None
    assert text.endswith("(recent news truncated)")
    assert len(text) <= 80 + 40


def test_loader_absent_empty_and_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_TRACKED_NEWS", raising=False)
    assert claude_runner.load_memo_recent_news(None) is None
    research = tmp_path / "research" / "generalist-inc"
    assert claude_runner.load_memo_recent_news(research) is None  # no dir
    research.mkdir(parents=True)
    assert claude_runner.load_memo_recent_news(research) is None  # no file
    _write_news(research)
    assert "Series C" in (claude_runner.load_memo_recent_news(research) or "")
    monkeypatch.setenv("BSH_MEMO_TRACKED_NEWS", "0")
    assert claude_runner.load_memo_recent_news(research) is None  # kill switch


def test_loader_truncates_oversized_digest(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_TRACKED_NEWS", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_news(research, "x" * (claude_runner.MEMO_RECENT_NEWS_MAX_CHARS + 500))
    text = claude_runner.load_memo_recent_news(research)
    assert text is not None
    assert text.endswith("(recent news truncated)")


def test_block_rendering_empty_is_byte_identical():
    assert claude_runner._memo_recent_news_block(None) == ""
    assert claude_runner._memo_recent_news_block("") == ""
    block = claude_runner._memo_recent_news_block("- one item")
    assert "## Recent tracked news" in block
    assert "- one item" in block


def test_analysis_pass_prompt_carries_recent_news(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_TRACKED_NEWS", raising=False)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    research = tmp_path / "research" / "generalist-inc"
    _write_news(research)
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
    assert "## Recent tracked news" in captured["prompt"]
    assert "Series C" in captured["prompt"]
    captured.clear()
    kwargs["research_dir"] = tmp_path / "research" / "other-co"
    claude_runner.run_memo_fast_analysis_pass(**kwargs)
    assert "Recent tracked news" not in captured["prompt"]


def test_spine_prompt_carries_recent_news_kwarg(tmp_path, monkeypatch):
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
        recent_news="- [2026-01-05] (high) Series C",
    )
    assert "## Recent tracked news" in captured["prompt"]
    captured.clear()
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
    )
    assert "Recent tracked news" not in captured["prompt"]


def test_common_section_context_stays_news_free(tmp_path, monkeypatch):
    """Sections are fed facts through the pin sheet only — tracked news
    must not leak into the shared context every section worker reads."""
    monkeypatch.delenv("BSH_MEMO_TRACKED_NEWS", raising=False)
    research = tmp_path / "research" / "generalist-inc"
    _write_news(research)
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
    assert "Recent tracked news" not in context
    assert "Series C" not in context


def test_wrapper_spine_call_threads_recent_news(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_TRACKED_NEWS", raising=False)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    research = tmp_path / "research" / "generalist-inc"
    _write_news(research)
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
    assert "Series C" in spine_calls[0]["recent_news"]


def test_write_recent_news_file_and_best_effort(tmp_path, monkeypatch):
    company_id = _seed_tracking_items(tmp_path, monkeypatch)
    research = tmp_path / "research" / company_id
    memo_analysis._write_recent_news_file(company_id, research)
    written = research / claude_runner.MEMO_RECENT_NEWS_FILENAME
    assert written.exists()
    assert "Series C" in written.read_text(encoding="utf-8")

    # A broken tracking store must never raise into the memo worker.
    def _boom(*_a, **_kw):
        raise RuntimeError("store corrupted")

    monkeypatch.setattr(tracking_updates, "render_research_news_md", _boom)
    memo_analysis._write_recent_news_file(company_id, research)  # no raise

    # Empty store leaves an existing digest alone.
    monkeypatch.setattr(
        tracking_updates, "render_research_news_md", lambda *_a, **_kw: None
    )
    memo_analysis._write_recent_news_file(company_id, research)
    assert written.exists()
