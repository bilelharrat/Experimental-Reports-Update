"""Tests for the retrieved-source cache and the Claude stream capture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import claude_runner, research_store, source_cache

COMPANY = "generalist-inc"


@pytest.fixture(autouse=True)
def _research_root(tmp_path, monkeypatch):
    root = tmp_path / "research"
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", root)
    return root


def _page(n: int = 1) -> str:
    return (
        f"Zainar announced a contracted book of $500M+ and 95+ patents on 2026-06-13. "
        f"Page variant {n}. " + "Filler sentence about wireless positioning. " * 3
    )


# ---- canonical URLs ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://Example.com/Report/", "https://example.com/Report"),
        ("http://example.com", "http://example.com/"),
        ("https://example.com/a?utm_source=x&b=2&a=1#frag", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a?fbclid=123", "https://example.com/a"),
        ("https://example.com:443/x", "https://example.com/x"),
        ("https://example.com:8443/x", "https://example.com:8443/x"),
        ("https://example.com//double//slash/", "https://example.com/double/slash"),
    ],
)
def test_canonical_url_normalizes(raw, expected):
    assert source_cache.canonical_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", None, "not a url", "ftp://example.com/x", "http://localhost:5181/research", "http://127.0.0.1/", "data:text/plain,hi", "https://box.local/x"],
)
def test_canonical_url_rejects_non_pages(raw):
    assert source_cache.canonical_url(raw) is None


# ---- records ----------------------------------------------------------------


def test_record_fetch_writes_text_and_index(_research_root):
    record = source_cache.record_source(
        COMPANY, kind="web_fetch", text=_page(), url="https://example.com/news/zainar?utm_x=1", title="Zainar news", origin="test"
    )
    assert record is not None
    assert record["kind"] == "web_fetch"
    assert record["canonical_url"] == "https://example.com/news/zainar"
    assert record["url"] == "https://example.com/news/zainar?utm_x=1"
    stored = _research_root / COMPANY / "sources"
    assert (stored / record["file"]).read_text(encoding="utf-8").startswith("Zainar announced")
    index = json.loads((stored / "index.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in index] == [record["id"]]
    assert source_cache.source_text(COMPANY, record["id"]).startswith("Zainar announced")
    assert source_cache.find_by_url(COMPANY, "HTTPS://example.com/news/zainar/")["id"] == record["id"]


def test_record_rejects_junk():
    assert source_cache.record_source(COMPANY, kind="web_fetch", text="short", url="https://example.com/x") is None
    assert source_cache.record_source(COMPANY, kind="web_fetch", text=_page(), url="http://localhost/x") is None
    assert source_cache.record_source(COMPANY, kind="nope", text=_page(), url="https://example.com/x") is None
    assert source_cache.list_sources(COMPANY) == []


def test_refetch_same_url_replaces_text_keeps_first_seen():
    first = source_cache.record_source(
        COMPANY, kind="web_fetch", text=_page(1), url="https://example.com/a", run_id="r1", origin="memo_run:r1:WebFetch", fetched_at="2026-01-01T00:00:00+00:00"
    )
    second = source_cache.record_source(
        COMPANY, kind="web_fetch", text=_page(2), url="https://example.com/a", run_id="r2", origin="memo_run:r2:WebFetch", fetched_at="2026-02-01T00:00:00+00:00"
    )
    rows = source_cache.list_sources(COMPANY)
    assert len(rows) == 1
    assert rows[0]["first_seen_at"] == "2026-01-01T00:00:00+00:00"
    assert rows[0]["fetched_at"] == "2026-02-01T00:00:00+00:00"
    assert rows[0]["run_ids"] == ["r1", "r2"]
    assert rows[0]["origins"] == ["memo_run:r1:WebFetch", "memo_run:r2:WebFetch"]
    assert "Page variant 2" in source_cache.source_text(COMPANY, rows[0])
    stored = source_cache.sources_dir(COMPANY)
    assert not (stored / first["file"]).exists()
    assert (stored / second["file"]).exists()


def test_search_blob_dedupes_on_content_and_keeps_links():
    text = "Web search results for query: zainar\n\nLinks: [{\"title\":\"A\",\"url\":\"https://a.com/x\"}]\n\n" + _page()
    links = source_cache.parse_search_links(text)
    assert links == [{"title": "A", "url": "https://a.com/x"}]
    one = source_cache.record_source(COMPANY, kind="web_search", text=text, query="zainar", links=links)
    two = source_cache.record_source(COMPANY, kind="web_search", text=text, query="zainar again", links=[{"title": "B", "url": "https://b.com/y"}])
    assert one["id"] == two["id"]
    rows = source_cache.list_sources(COMPANY)
    assert len(rows) == 1
    assert rows[0]["query"] == "zainar"
    assert [link["url"] for link in rows[0]["links"]] == ["https://a.com/x", "https://b.com/y"]


def test_list_sources_newest_first_with_filters_and_limit():
    for n, (kind, when) in enumerate(
        [("web_fetch", "2026-01-01"), ("web_search", "2026-03-01"), ("web_fetch", "2026-02-01")]
    ):
        source_cache.record_source(
            COMPANY, kind=kind, text=_page(n), url=f"https://example.com/{n}", query=f"q{n}", fetched_at=f"{when}T00:00:00+00:00"
        )
    rows = source_cache.list_sources(COMPANY)
    assert [row["fetched_at"][:10] for row in rows] == ["2026-03-01", "2026-02-01", "2026-01-01"]
    assert [row["kind"] for row in source_cache.list_sources(COMPANY, kinds=("web_fetch",))] == ["web_fetch", "web_fetch"]
    assert len(source_cache.list_sources(COMPANY, limit=1)) == 1


def test_eviction_past_max_records(monkeypatch):
    monkeypatch.setattr(source_cache, "MAX_RECORDS", 3)
    for n in range(5):
        source_cache.record_source(
            COMPANY, kind="web_fetch", text=_page(n), url=f"https://example.com/{n}", fetched_at=f"2026-01-0{n + 1}T00:00:00+00:00"
        )
    rows = source_cache.list_sources(COMPANY)
    assert [row["url"] for row in rows] == ["https://example.com/4", "https://example.com/3", "https://example.com/2"]
    files = sorted(p.name for p in source_cache.sources_dir(COMPANY).glob("*.txt"))
    assert len(files) == 3


def test_corrupt_index_reads_as_empty_and_recovers(_research_root):
    stored = _research_root / COMPANY / "sources"
    stored.mkdir(parents=True)
    (stored / "index.json").write_text("{not json", encoding="utf-8")
    assert source_cache.list_sources(COMPANY) == []
    record = source_cache.record_source(COMPANY, kind="web_fetch", text=_page(), url="https://example.com/x")
    assert record is not None
    assert len(source_cache.list_sources(COMPANY)) == 1


def test_long_text_is_capped(monkeypatch):
    monkeypatch.setattr(source_cache, "MAX_TEXT_CHARS", 200)
    record = source_cache.record_source(COMPANY, kind="web_fetch", text="x" * 1000, url="https://example.com/long")
    text = source_cache.source_text(COMPANY, record)
    assert text.endswith("[truncated by source cache]")
    assert len(text) < 260


# ---- run manifest -----------------------------------------------------------


def test_record_run_source_freezes_copy_and_manifest(tmp_path):
    run_dir = tmp_path / "memos" / COMPANY / "run-1"
    record = source_cache.record_run_source(
        COMPANY, run_dir, tool="WebFetch", text=_page(), url="https://example.com/a", run_id="run-1"
    )
    assert record is not None
    rows = source_cache.run_manifest(run_dir)
    assert len(rows) == 1
    assert rows[0]["tool"] == "WebFetch"
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["sha256"] == record["sha256"]
    assert (run_dir / "sources" / record["file"]).exists()
    # A later re-fetch changes the company record; the run copy keeps what it saw.
    source_cache.record_source(COMPANY, kind="web_fetch", text=_page(9), url="https://example.com/a")
    assert "Page variant 1" in source_cache.run_source_texts(run_dir)[0][1]
    assert "Page variant 9" in source_cache.source_text(COMPANY, source_cache.list_sources(COMPANY)[0])
    assert record["origins"] == ["memo_run:run-1:WebFetch"]


def test_run_manifest_missing_is_empty(tmp_path):
    assert source_cache.run_manifest(tmp_path / "nope") == []
    assert source_cache.run_source_texts(tmp_path / "nope") == []


# ---- grounding ----------------------------------------------------------------


def test_record_grounding_keeps_prose_and_links():
    meta = {
        "research_text": _page(),
        "sources": [{"title": "Reuters", "url": "https://reuters.com/x"}],
        "queries": ["zainar revenue", "zainar patents"],
    }
    record = source_cache.record_grounding(COMPANY, meta, origin="news_sweep")
    assert record["kind"] == "grounding"
    assert record["query"] == "zainar revenue; zainar patents"
    assert record["links"][0]["url"] == "https://reuters.com/x"
    assert source_cache.record_grounding(COMPANY, {"research_text": "", "sources": []}, origin="x") is None
    assert source_cache.record_grounding(COMPANY, None, origin="x") is None


def test_record_grounding_without_prose_lists_pages():
    record = source_cache.record_grounding(
        COMPANY,
        {"sources": [{"title": "Reuters piece", "url": "https://reuters.com/x"}] * 3},
        origin="news_sweep",
    )
    assert record is not None
    assert "Pages reported by grounding" in source_cache.source_text(COMPANY, record)


# ---- digest and matching --------------------------------------------------------


def test_known_pages_and_digest(tmp_path):
    source_cache.record_source(
        COMPANY, kind="web_fetch", text=_page(), url="https://gartner.com/it-services-databook", title="Gartner IT Services Databook 2026", fetched_at="2026-02-01T00:00:00+00:00"
    )
    source_cache.record_source(
        COMPANY,
        kind="web_search",
        text=_page(2),
        query="zainar",
        links=[{"title": "IDC forecast", "url": "https://idc.com/forecast"}, {"title": "dup", "url": "https://gartner.com/it-services-databook?utm_x=1"}],
        fetched_at="2026-03-01T00:00:00+00:00",
    )
    pages = source_cache.known_pages(COMPANY)
    # Fetched pages first (they have text to reopen), then bare links; the
    # utm-tagged duplicate of the fetched page is dropped.
    assert [p["url"] for p in pages] == ["https://gartner.com/it-services-databook", "https://idc.com/forecast"]
    digest = source_cache.render_known_sources_md(COMPANY)
    assert digest.startswith("# Known sources")
    assert "2026-03-01 — IDC forecast — https://idc.com/forecast" in digest
    assert "text: sources/" in digest
    assert source_cache.render_known_sources_md("other-co") == ""
    research_dir = tmp_path / "research" / COMPANY
    assert source_cache.write_known_sources_file(COMPANY, research_dir, "known_sources.md") is True
    assert (research_dir / "known_sources.md").read_text(encoding="utf-8").startswith("# Known sources")
    assert source_cache.write_known_sources_file("other-co", research_dir, "known_sources.md") is False


def test_digest_truncates_on_a_line_boundary():
    for n in range(30):
        source_cache.record_source(
            COMPANY, kind="web_fetch", text=_page(n), url=f"https://example.com/report-{n}", title=f"Report number {n} about positioning"
        )
    digest = source_cache.render_known_sources_md(COMPANY, max_chars=600)
    assert len(digest) <= 640
    assert digest.endswith("(known sources truncated)")
    assert "\n- " in digest


def test_match_title_needs_a_strong_match():
    source_cache.record_source(
        COMPANY, kind="web_fetch", text=_page(), url="https://gartner.com/it-services-databook", title="Gartner IT Services Databook 2026"
    )
    assert source_cache.match_title(COMPANY, "Gartner IT Services Databook")["url"].startswith("https://gartner.com")
    assert source_cache.match_title(COMPANY, "Databook") is None  # one token: never
    assert source_cache.match_title(COMPANY, "IDC Digital Engineering Forecast") is None


def test_corpus_texts_labels_and_budget():
    source_cache.record_source(COMPANY, kind="web_fetch", text=_page(), url="https://example.com/a")
    source_cache.record_source(COMPANY, kind="web_search", text=_page(2), query="zainar book")
    texts = source_cache.corpus_texts(COMPANY)
    labels = [label for label, _ in texts]
    assert any("https://example.com/a" in label for label in labels)
    assert any("search: zainar book" in label for label in labels)
    assert source_cache.corpus_texts(COMPANY, max_total_chars=10) == []


# ---- Claude stream capture ------------------------------------------------------


def _events(tool: str, inp: dict, result_text: str, *, is_error: bool = False) -> list[dict]:
    return [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu1", "name": tool, "input": inp}]}},
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "is_error": is_error, "content": [{"type": "text", "text": result_text}]}
                ]
            },
        },
    ]


def test_observe_stream_event_records_fetch_and_search(tmp_path):
    run_dir = tmp_path / "memos" / COMPANY / "run-1"
    capture = {"company_id": COMPANY, "run_dir": run_dir, "run_id": "run-1", "pending": {}}
    for event in _events("WebFetch", {"url": "https://example.com/a", "prompt": "facts"}, _page()):
        source_cache.observe_stream_event(event, capture)
    search_text = "Web search results for query: \"zainar\"\n\nLinks: [{\"title\":\"A\",\"url\":\"https://a.com/x\"}]\n\n" + _page(2)
    events = _events("WebSearch", {"query": "zainar"}, search_text)
    events[0]["message"]["content"][0]["id"] = "tu2"
    events[1]["message"]["content"][0]["tool_use_id"] = "tu2"
    for event in events:
        source_cache.observe_stream_event(event, capture)
    rows = source_cache.list_sources(COMPANY)
    assert {row["kind"] for row in rows} == {"web_fetch", "web_search"}
    assert capture["recorded"] == 2
    assert capture["pending"] == {}
    manifest = source_cache.run_manifest(run_dir)
    assert [row["tool"] for row in manifest] == ["WebFetch", "WebSearch"]
    assert manifest[1]["links"] == 1


def test_observe_stream_event_skips_errors_and_other_tools(tmp_path):
    capture = {"company_id": COMPANY, "run_dir": tmp_path / "run", "run_id": "r", "pending": {}}
    for event in _events("WebFetch", {"url": "https://example.com/a"}, "404 not found", is_error=True):
        source_cache.observe_stream_event(event, capture)
    for event in _events("Read", {"file_path": "/x"}, _page()):
        source_cache.observe_stream_event(event, capture)
    assert source_cache.list_sources(COMPANY) == []
    assert capture.get("recorded", 0) == 0
    # A tool_result with no matching tool_use is ignored, and a malformed event never raises.
    assert source_cache.observe_stream_event({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "zzz"}]}}, capture) is None
    assert source_cache.observe_stream_event({"type": "assistant", "message": None}, capture) is None


def test_runner_registry_and_wrapped_handler(tmp_path):
    run_dir = tmp_path / "memos" / COMPANY / "run-7"
    research_dir = tmp_path / "research" / COMPANY
    claude_runner.register_memo_run_source_capture(
        run_dir, company_id=COMPANY, run_id="run-7", research_dir=research_dir
    )
    capture = claude_runner.memo_run_source_capture(run_dir)
    assert capture["company_id"] == COMPANY
    assert claude_runner.memo_run_source_capture(tmp_path / "elsewhere") is None
    seen: list[dict] = []
    handler = claude_runner._with_source_capture(lambda event, progress, state: seen.append(event))
    capture.update({"run_dir": run_dir, "pending": {}, "recorded": 0})
    state = {"source_capture": capture}
    for event in _events("WebFetch", {"url": "https://example.com/a"}, _page()):
        handler(event, None, state)
    assert len(seen) == 2
    assert capture["recorded"] == 1
    assert (research_dir / claude_runner.MEMO_KNOWN_SOURCES_FILENAME).exists()
    # A handler without capture state is a plain pass-through.
    handler({"type": "result"}, None, {})
    assert len(seen) == 3


def test_wrapped_handler_survives_inner_failure(tmp_path):
    def broken(event, progress, state):
        raise RuntimeError("boom")

    handler = claude_runner._with_source_capture(broken)
    with pytest.raises(RuntimeError):
        handler({"type": "assistant"}, None, {})


def test_known_sources_loader_and_block(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_KNOWN_SOURCES", raising=False)
    research = tmp_path / "research" / COMPANY
    assert claude_runner.load_memo_known_sources(None) is None
    assert claude_runner.load_memo_known_sources(research) is None
    research.mkdir(parents=True)
    (research / claude_runner.MEMO_KNOWN_SOURCES_FILENAME).write_text("# Known sources\n- a — https://x", encoding="utf-8")
    assert claude_runner.load_memo_known_sources(research).startswith("# Known sources")
    block = claude_runner._memo_known_sources_block("- a — https://x")
    assert "## Known sources" in block and "https://x" in block
    assert claude_runner._memo_known_sources_block(None) == ""
    monkeypatch.setenv("BSH_MEMO_KNOWN_SOURCES", "0")
    assert claude_runner.load_memo_known_sources(research) is None
    monkeypatch.delenv("BSH_MEMO_KNOWN_SOURCES")
    big = "\n".join(f"- line {n} — https://x/{n}" for n in range(600))
    (research / claude_runner.MEMO_KNOWN_SOURCES_FILENAME).write_text(big, encoding="utf-8")
    text = claude_runner.load_memo_known_sources(research)
    assert text.endswith("(known sources truncated)")
    assert len(text) <= claude_runner.MEMO_KNOWN_SOURCES_MAX_CHARS + 40


def test_known_sources_reach_passes_and_spine_not_sections(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_KNOWN_SOURCES", raising=False)
    research = tmp_path / "research" / COMPANY
    research.mkdir(parents=True)
    (research / claude_runner.MEMO_KNOWN_SOURCES_FILENAME).write_text(
        "# Known sources\n- 2026-01-01 — Gartner Databook — https://gartner.com/db", encoding="utf-8"
    )
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"key_findings": []}, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    claude_runner.run_memo_fast_analysis_pass(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug=COMPANY,
        run_id="r1",
        pass_id="time_base",
        pass_label="Time base",
        artifact_filename="time_base.md",
        focus="Check every time base.",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        research_dir=research,
    )
    assert "## Known sources" in captured["append_system_prompt"]
    assert "https://gartner.com/db" in captured["append_system_prompt"]
    captured.clear()
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
        known_sources="- 2026-01-01 — Gartner Databook — https://gartner.com/db",
    )
    assert "## Known sources" in captured["prompt"]
    context = claude_runner._memo_english_common_context(
        company_name="Generalist, Inc.",
        company_slug=COMPANY,
        run_id="r1",
        run_dir=run_dir,
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
        analysis_session_path=None,
        scope_check=None,
        warnings=None,
    )
    assert "Known sources" not in context


def test_parallel_wrapper_threads_known_sources_to_spine(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_KNOWN_SOURCES", raising=False)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    research = tmp_path / "research" / COMPANY
    research.mkdir(parents=True)
    (research / claude_runner.MEMO_KNOWN_SOURCES_FILENAME).write_text("- x — https://x.com/1", encoding="utf-8")
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return None, "stop here"

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package", lambda **_kw: (None, "monolithic fallback declined")
    )
    claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug=COMPANY,
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        research_dir=research,
    )
    assert spine_calls
    assert "https://x.com/1" in spine_calls[0]["known_sources"]


def test_gemini_research_walk_skips_the_cache_and_inlines_the_digest(tmp_path):
    from server import memo_engine

    research = tmp_path / "research" / COMPANY
    (research / "sources").mkdir(parents=True)
    (research / "sources" / "abc.txt").write_text("cached page text that must not inline", encoding="utf-8")
    (research / "known_sources.md").write_text("# Known sources\n- a — https://x", encoding="utf-8")
    (research / "notes.md").write_text("analyst notes", encoding="utf-8")
    text = memo_engine.inline_research([research])
    assert "cached page text that must not inline" not in text
    assert text.index("known_sources.md") < text.index("notes.md")
