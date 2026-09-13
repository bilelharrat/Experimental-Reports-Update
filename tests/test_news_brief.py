"""Expanded news briefings: caching, cleaning, and the fast write path.

The Claude call is stubbed everywhere — these tests never touch the
network or spend money.
"""
from __future__ import annotations

import pytest

from server import news_brief


@pytest.fixture(autouse=True)
def _reset_prewarm_pool():
    news_brief.reset_prewarm_state_for_tests()
    yield
    news_brief.reset_prewarm_state_for_tests()


def _payload(**overrides):
    data = {
        "headline": "ZaiNar opens Tokyo hub",
        "what_happened": "A long English body. " * 40,
        "why_it_matters": "The investment read. " * 20,
        "context": ["Prior round closed in March", "Competes with NextNav"],
        "watch_next": ["APAC revenue disclosure at Q3"],
        "confidence": "Medium",
        "sources": [
            {"title": "Company release", "url": "https://example.com/pr"},
            {"title": "Bad row", "url": "not-a-url"},
            "junk",
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def stub_claude(monkeypatch):
    """Recorder that stands in for the structured (no-tools) Claude call."""

    calls: list[dict] = []

    def _fake(*, system_prompt, user_prompt, schema, name, timeout_sec, **kwargs):
        calls.append(
            {
                "user_prompt": user_prompt,
                "name": name,
                "timeout_sec": timeout_sec,
                "system_prompt": system_prompt,
            }
        )
        return _payload(), None

    monkeypatch.setattr(news_brief.claude_runner, "run_structured_prompt", _fake)
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    return calls


def test_expand_returns_long_briefing_with_ios_aliases(stub_claude):
    brief = news_brief.expand(
        title="ZaiNar opens Tokyo office",
        summary="Short desk one-liner.",
        source="Nikkei",
        company="ZaiNar",
        ticker="PRIV",
        url="https://example.com/story",
    )

    assert len(brief["what_happened"]) > 400
    assert brief["what_happened_en"] == brief["what_happened"]
    assert brief["why_it_matters_en"]
    assert brief["context_en"] == [
        "Prior round closed in March",
        "Competes with NextNav",
    ]
    assert brief["watch_next_en"] == ["APAC revenue disclosure at Q3"]
    assert brief["confidence"] == "medium"
    assert brief["sources"][0]["url"] == "https://example.com/story"
    assert "ZaiNar (PRIV)" in stub_claude[0]["user_prompt"]
    assert stub_claude[0]["timeout_sec"] == news_brief.BRIEF_TIMEOUT_SEC
    assert stub_claude[0]["timeout_sec"] >= 60
    assert "do NOT call tools" in stub_claude[0]["system_prompt"]


def test_article_text_is_injected_into_prompt(stub_claude, monkeypatch):
    monkeypatch.setattr(
        news_brief,
        "fetch_article_text",
        lambda url, **kwargs: ("Body of the article with numbers.", url),
    )
    news_brief.expand(title="Story", url="https://example.com/a")
    assert "Body of the article with numbers." in stub_claude[0]["user_prompt"]


def test_chinese_call_writes_zh_aliases(stub_claude):
    brief = news_brief.expand(title="ZaiNar opens Tokyo office", lang="zh")
    assert brief["what_happened_zh"] == brief["what_happened"]
    assert "what_happened_en" not in brief


def test_second_open_is_served_from_cache(stub_claude):
    first = news_brief.expand(title="Same headline", company="ZaiNar")
    second = news_brief.expand(title="Same headline", company="ZaiNar")

    assert second["generated_at"] == first["generated_at"]
    assert len(stub_claude) == 1, "cached briefing must not re-run the model"


def test_refresh_regenerates(stub_claude):
    news_brief.expand(title="Same headline")
    news_brief.expand(title="Same headline", refresh=True)

    assert len(stub_claude) == 2


def test_key_ignores_case_and_whitespace():
    assert news_brief.brief_key("  Big   News  ") == news_brief.brief_key("big news")
    assert news_brief.brief_key("Big news", "A") != news_brief.brief_key("Big news", "B")


def test_empty_title_rejected():
    with pytest.raises(ValueError):
        news_brief.expand(title="   ")


def test_model_failure_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(
        news_brief.claude_runner,
        "run_structured_prompt",
        lambda **kwargs: (None, "claude exploded"),
    )
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    with pytest.raises(RuntimeError, match="claude exploded"):
        news_brief.expand(title="Headline")


def test_body_less_response_raises(monkeypatch):
    monkeypatch.setattr(
        news_brief.claude_runner,
        "run_structured_prompt",
        lambda **kwargs: (_payload(what_happened="   "), None),
    )
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    with pytest.raises(RuntimeError):
        news_brief.expand(title="Headline")


def test_load_brief_missing_returns_none():
    assert news_brief.load_brief("deadbeefdeadbeef") is None


def test_prewarm_queues_missing_and_skips_cached(stub_claude):
    news_brief.expand(title="Already done", company="ZaiNar")
    stub_claude.clear()

    plan = news_brief.prewarm(
        [
            {"title": "Already done", "company": "ZaiNar"},
            {"title": "Fresh one", "url": "https://example.com/a"},
            {"title": "Fresh two", "summary": "x"},
            {"title": ""},
        ],
        lang="en",
        limit=12,
        workers=2,
        background=False,
    )

    assert plan["skipped_cached"] == 1
    assert plan["queued"] == 2
    assert plan["started"] is True
    assert plan["parallel"] is True
    assert plan["workers"] == 2
    assert len(stub_claude) == 2
    assert news_brief.load_brief(
        news_brief.brief_key("Fresh one"), "en"
    ) is not None


def test_prewarm_runs_items_in_parallel(stub_claude, monkeypatch):
    """Wall clock for N briefs should track one Claude call, not N serial."""
    import threading
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    def _slow(*, system_prompt, user_prompt, schema, name, timeout_sec, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return _payload(), None

    monkeypatch.setattr(news_brief.claude_runner, "run_structured_prompt", _slow)
    started = time.monotonic()
    plan = news_brief.prewarm(
        [{"title": f"Parallel story {i}"} for i in range(4)],
        lang="en",
        limit=4,
        workers=4,
        background=False,
    )
    elapsed = time.monotonic() - started

    assert plan["queued"] == 4
    assert peak >= 3, f"expected concurrent Claude calls, peak={peak}"
    assert elapsed < 0.5, f"serial would be ~0.6s; got {elapsed:.2f}s"


def test_prewarm_second_call_enqueues_while_pool_busy(monkeypatch):
    """A second prewarm must enqueue, not drop, while the shared pool is busy."""
    import threading
    import time

    news_brief.reset_prewarm_state_for_tests()
    release = threading.Event()
    started = threading.Event()
    calls: list[str] = []

    def _gated(*, system_prompt, user_prompt, schema, name, timeout_sec, **kwargs):
        title_line = user_prompt.splitlines()[0]
        calls.append(title_line)
        started.set()
        release.wait(timeout=5)
        return _payload(), None

    monkeypatch.setattr(news_brief.claude_runner, "run_structured_prompt", _gated)
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )

    first = news_brief.prewarm(
        [{"title": "Busy one"}],
        lang="en",
        limit=4,
        background=True,
    )
    assert first["started"] is True
    assert started.wait(timeout=2)

    second = news_brief.prewarm(
        [{"title": "Busy one"}, {"title": "Late arrival"}],
        lang="en",
        limit=4,
        background=True,
    )
    # "Busy one" is already writing (or still queued); "Late arrival" enqueues.
    assert second["skipped_inflight"] + second["skipped_queued"] >= 1
    assert second["queued"] == 1
    assert second["started"] is True
    # Must enqueue the new headline — not drop the whole round.
    assert "new items skipped" not in str(second.get("note") or "")

    release.set()
    for _ in range(40):
        if news_brief.load_brief(news_brief.brief_key("Late arrival"), "en"):
            break
        time.sleep(0.05)
    assert news_brief.load_brief(news_brief.brief_key("Late arrival"), "en") is not None
    news_brief.reset_prewarm_state_for_tests()


def test_brief_statuses_reports_ready_and_generating(stub_claude):
    news_brief.expand(title="Ready story")
    status = news_brief.brief_statuses(
        [
            {"title": "Ready story"},
            {"title": "Missing story"},
        ],
        lang="en",
    )
    assert status["ready"] == 1
    by_title = {row["title"]: row for row in status["items"]}
    assert by_title["Ready story"]["ready"] is True
    assert by_title["Missing story"]["ready"] is False


def test_fetch_article_text_truncates(monkeypatch):
    class FakeResponse:
        text = "<html><body><article>" + ("word " * 5000) + "</article></body></html>"
        url = "https://example.com/long"
        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(news_brief.httpx, "Client", FakeClient)
    text, final = news_brief.fetch_article_text(
        "https://example.com/long", max_chars=200
    )
    assert final == "https://example.com/long"
    assert len(text) <= 201
    assert text.endswith("…")
