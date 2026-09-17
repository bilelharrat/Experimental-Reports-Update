"""News desk briefings.

Opening a story serves the cached AI briefing, else writes one now
(``BSH_NEWS_BRIEF_ON_OPEN=0`` restores the old basic-briefing behavior).
Briefings come from ONE worker, one call per headline writing English and
Chinese, plus a scheduled sweep and an explicit, warned rewrite.

Note the ``_no_real_claude_cli`` fixture in conftest forces
``claude_runner.is_available()`` False for every test, and no Gemini key is
set, so ``ai_engine.available()`` is False unless a test says otherwise.
Tests about on-open writing must therefore stub availability explicitly —
without that they pass for the wrong reason. The engine is stubbed
everywhere: no network, no spend.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import timedelta

import pytest

from server import claude_runner, news_brief

_ENV = (
    "BSH_NEWS_BRIEF_MODEL",
    "BSH_NEWS_BRIEF_EFFORT",
    "BSH_NEWS_BRIEF_REFRESH_HOURS",
    "BSH_NEWS_BRIEF_REFRESH_LIMIT",
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    news_brief.reset_state_for_tests()
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    yield
    news_brief.reset_state_for_tests()


def _part(lang: str, **overrides):
    data = {
        "headline": f"ZaiNar opens Tokyo hub ({lang})",
        "what_happened": f"A long {lang} body. " * 40,
        "why_it_matters": f"The {lang} investment read. " * 20,
        "context": ["Prior round closed in March", "Competes with NextNav"],
        "watch_next": ["APAC revenue disclosure at Q3"],
        "key_figures": [
            f"Revenue rose 40% year on year in the {lang} period.",
            "  ",
            "Headcount reached 180, up from 120 a year earlier.",
        ],
    }
    data.update(overrides)
    return data


def _payload(**overrides):
    data = {
        "en": _part("en"),
        "zh": _part("zh"),
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
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
                "name": name,
                "timeout_sec": timeout_sec,
                **kwargs,
            }
        )
        return _payload(), {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None}, None

    monkeypatch.setattr(news_brief.ai_engine, "structured", _fake)
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    return calls


ARTICLE = "\n".join(
    [
        "Home",
        "Subscribe to our newsletter",
        "ZaiNar opens Tokyo office",
        "ZaiNar said on Monday it opened a Tokyo office to serve Japanese "
        "carriers, its first site outside the United States.",
        "The company raised $100 million in March and says revenue grew 45% "
        "last year as carrier pilots turned into contracts.",
        "Short caption.",
        "Analysts expect the Asia-Pacific market for network positioning to "
        "reach 2.5 billion dollars by 2030, led by Japan and Korea.",
    ]
)


# ---- AI briefing: one call, both languages, Sonnet medium, tools off ------


def test_one_call_writes_both_languages_with_no_tools(stub_claude):
    written = news_brief.write_brief(
        title="ZaiNar opens Tokyo office",
        summary="Short desk one-liner.",
        source="Nikkei",
        company="ZaiNar",
        ticker="PRIV",
        url="https://example.com/story",
    )

    assert len(stub_claude) == 1
    call = stub_claude[0]
    # ai_engine never enables tools for a structured call, and the
    # BSH_NEWS_BRIEF_* knobs now pin the Claude fallback only — Gemini's
    # model comes from BSH_GEMINI_MODEL.
    assert call["claude_model"] == "sonnet"
    assert call["claude_effort"] == "medium"
    assert "tools" not in call
    assert set(call["schema"]["required"]) == {"en", "zh"}
    assert "do NOT call tools" in call["system_prompt"]
    assert "ZaiNar (PRIV)" in call["user_prompt"]
    assert call["timeout_sec"] == news_brief.BRIEF_TIMEOUT_SEC

    key = news_brief.brief_key("ZaiNar opens Tokyo office", "ZaiNar")
    en = news_brief.load_brief(key, "en")
    zh = news_brief.load_brief(key, "zh")
    assert written == {"en": en, "zh": zh}
    assert en["kind"] == zh["kind"] == "ai"
    assert "long en body" in en["what_happened"]
    assert en["what_happened_en"] == en["what_happened"]
    assert "long zh body" in zh["what_happened"]
    assert zh["what_happened_zh"] == zh["what_happened"]
    assert en["confidence"] == "medium"
    assert [s["url"] for s in en["sources"]] == [
        "https://example.com/story",
        "https://example.com/pr",
    ]


def test_env_can_change_the_fallback_model_and_effort(stub_claude, monkeypatch):
    monkeypatch.setenv("BSH_NEWS_BRIEF_MODEL", "haiku")
    monkeypatch.setenv("BSH_NEWS_BRIEF_EFFORT", "low")
    news_brief.write_brief(title="Headline")
    assert stub_claude[0]["claude_model"] == "haiku"
    assert stub_claude[0]["claude_effort"] == "low"


def test_article_text_is_injected_into_prompt(stub_claude, monkeypatch):
    monkeypatch.setattr(
        news_brief,
        "fetch_article_text",
        lambda url, **kwargs: ("Body of the article with numbers.", url),
    )
    news_brief.write_brief(title="Story", url="https://example.com/a")
    assert "Body of the article with numbers." in stub_claude[0]["user_prompt"]


def test_writes_run_one_at_a_time(monkeypatch):
    """Two callers at once (a refresh and a user rewrite) never overlap."""
    active = 0
    peak = 0
    lock = threading.Lock()

    def _slow(**kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return _payload(), {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None}, None

    monkeypatch.setattr(news_brief.ai_engine, "structured", _slow)
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    threads = [
        threading.Thread(target=news_brief.write_brief, kwargs={"title": f"Story {i}"})
        for i in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert peak == 1


def test_model_failure_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(
        news_brief.ai_engine,
        "structured",
        lambda **kwargs: (None, {"engine": "gemini"}, "the engine exploded"),
    )
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    with pytest.raises(RuntimeError, match="the engine exploded"):
        news_brief.expand(title="Headline", refresh=True)


def test_body_less_response_raises(monkeypatch):
    monkeypatch.setattr(
        news_brief.ai_engine,
        "structured",
        lambda **kwargs: (
            _payload(en=_part("en", what_happened=" "), zh=_part("zh", what_happened="")),
            {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None},
            None,
        ),
    )
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    with pytest.raises(RuntimeError):
        news_brief.write_brief(title="Headline")


# ---- Opening a story: never AI ---------------------------------------------


def test_opening_falls_back_to_basic_when_no_engine_can_run(stub_claude, monkeypatch):
    """conftest leaves no engine available, which is the degraded case: the
    reader still gets the article's lead and figures rather than nothing."""
    fetches: list[str] = []

    def _fetch(url, **kwargs):
        fetches.append(url)
        return ARTICLE, url

    monkeypatch.setattr(news_brief, "fetch_article_text", _fetch)
    first = news_brief.expand(
        title="ZaiNar opens Tokyo office",
        source="Nikkei",
        url="https://example.com/story",
        lang="zh",
    )
    second = news_brief.expand(
        title="ZaiNar opens Tokyo office", url="https://example.com/story", lang="en"
    )

    assert stub_claude == []
    assert first["kind"] == "basic"
    assert first["what_happened"].startswith("ZaiNar said on Monday")
    assert first["what_happened_zh"] == first["what_happened"]
    assert first["sources"] == [{"title": "Nikkei", "url": "https://example.com/story"}]
    assert second["lang"] == "en" and second["what_happened_en"]
    assert fetches == ["https://example.com/story"], "basic briefing is cached"


def test_opening_a_story_writes_the_briefing_when_one_is_missing(
    stub_claude, monkeypatch
):
    """The tape rotates in minutes and the scheduled sweep runs every six
    hours, so the newest story — the one actually opened — would otherwise
    never have a briefing."""
    monkeypatch.setattr(news_brief.ai_engine, "available", lambda: True)
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))

    brief = news_brief.expand(title="Fresh headline", lang="en")
    assert brief["kind"] == "ai"
    assert len(stub_claude) == 1

    # Cached: a second reader pays nothing.
    again = news_brief.expand(title="Fresh headline", lang="en")
    assert again["kind"] == "ai"
    assert len(stub_claude) == 1


def test_on_open_writing_can_be_switched_off(stub_claude, monkeypatch):
    monkeypatch.setattr(news_brief.ai_engine, "available", lambda: True)
    monkeypatch.setenv("BSH_NEWS_BRIEF_ON_OPEN", "0")
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))

    brief = news_brief.expand(title="Fresh headline", lang="en")
    assert brief["kind"] == "basic"
    assert stub_claude == []


def test_a_failed_write_on_open_degrades_instead_of_erroring(monkeypatch):
    """Opening a story must never 500 because a model was unavailable."""
    monkeypatch.setattr(news_brief.ai_engine, "available", lambda: True)
    monkeypatch.setattr(
        news_brief.ai_engine,
        "structured",
        lambda **kw: (None, {"engine": "gemini"}, "engine down"),
    )
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kw: ("Lead paragraph.", url)
    )
    brief = news_brief.expand(title="Fresh headline", lang="en")
    assert brief["kind"] == "basic"


def test_opening_serves_the_cached_ai_briefing(stub_claude):
    news_brief.write_brief(title="Same headline", company="ZaiNar")
    stub_claude.clear()
    brief = news_brief.expand(title="Same headline", company="ZaiNar", lang="zh")
    assert brief["kind"] == "ai"
    assert "long zh body" in brief["what_happened"]
    assert stub_claude == []


def test_refresh_true_is_the_explicit_rewrite(stub_claude):
    brief = news_brief.expand(title="Same headline", lang="zh", refresh=True)
    assert len(stub_claude) == 1
    assert brief["lang"] == "zh"
    assert news_brief.load_brief(news_brief.brief_key("Same headline"), "en")


def test_basic_extract_keeps_the_lead_and_the_figures():
    paragraphs = news_brief.lead_paragraphs(ARTICLE)
    assert paragraphs[0].startswith("ZaiNar said on Monday")
    assert all("Subscribe" not in p and p != "Short caption." for p in paragraphs)
    assert len(paragraphs) == 3

    figures = news_brief.figure_sentences(ARTICLE)
    assert any("$100 million" in s for s in figures)
    assert any("2.5 billion" in s for s in figures)
    assert not any("first site outside" in s for s in figures)
    assert news_brief.figure_sentences("营收同比增长45%，达到12亿元人民币的历史新高。")


def test_failed_fetch_falls_back_to_summary_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(
        news_brief, "fetch_article_text", lambda url, **kwargs: ("", None)
    )
    brief = news_brief.basic_brief(title="Headline", summary="One-liner on file.")
    assert brief["what_happened"] == "One-liner on file."
    key = news_brief.brief_key("Headline")
    assert not (news_brief.BRIEFS_ROOT / f"{key}-basic.json").exists()


def test_empty_title_rejected():
    with pytest.raises(ValueError):
        news_brief.expand(title="   ")


def test_key_ignores_case_and_whitespace():
    assert news_brief.brief_key("  Big   News  ") == news_brief.brief_key("big news")
    assert news_brief.brief_key("Big news", "A") != news_brief.brief_key("Big news", "B")


def test_load_brief_missing_returns_none():
    assert news_brief.load_brief("deadbeefdeadbeef") is None


# ---- Tape and refresh --------------------------------------------------------


def test_prewarm_only_records_the_tape(stub_claude):
    plan = news_brief.prewarm(
        [
            {"title": "Fresh one", "url": "https://example.com/a"},
            {"title": "fresh   ONE", "url": "https://example.com/a"},
            {"title": "Fresh two", "summary": "x", "company": "ZaiNar"},
            {"title": ""},
        ],
        lang="en",
        limit=12,
    )
    assert plan["recorded"] == 2
    assert plan["queued"] == 0 and plan["started"] is False and plan["ai"] is False
    assert stub_claude == []
    assert [row["title"] for row in news_brief.load_tape()] == ["Fresh one", "Fresh two"]


def test_refresh_writes_only_missing_headlines_in_order(stub_claude):
    news_brief.write_brief(title="Already done", company="ZaiNar")
    stub_claude.clear()
    items = [
        {"title": "Already done", "company": "ZaiNar"},
        {"title": "Fresh one"},
        {"title": "Fresh two"},
    ]

    result = news_brief.start_refresh(items=items, background=False)

    assert result["started"] is True and result["planned"] == 2
    assert [c["user_prompt"].splitlines()[0] for c in stub_claude] == [
        "Headline: Fresh one",
        "Headline: Fresh two",
    ]
    status = news_brief.refresh_status()
    assert status["running"] is False
    assert status["done"] == 2 and status["failed"] == 0
    assert status["pending"] == 0
    assert status["last_refresh_at"] is not None
    assert status["model"] == "sonnet" and status["effort"] == "medium"


def test_refresh_counts_a_failed_story_and_keeps_going(stub_claude, monkeypatch):
    def _flaky(*, user_prompt, **kwargs):
        if "Bad story" in user_prompt:
            return None, {"engine": "gemini"}, "the engine exploded"
        return _payload(), {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None}, None

    monkeypatch.setattr(news_brief.ai_engine, "structured", _flaky)
    news_brief.start_refresh(
        items=[{"title": "Bad story"}, {"title": "Good story"}], background=False
    )
    status = news_brief.refresh_status()
    assert status["done"] == 1 and status["failed"] == 1
    assert "the engine exploded" in status["last_error"]
    assert news_brief.load_brief(news_brief.brief_key("Good story"), "zh")


def test_refresh_with_everything_cached_writes_nothing(stub_claude):
    news_brief.write_brief(title="Done")
    stub_claude.clear()
    result = news_brief.start_refresh(items=[{"title": "Done"}], background=False)
    assert result["started"] is False and result["note"] == "nothing_to_write"
    assert stub_claude == []
    assert news_brief.last_refresh_at() is not None


def test_refresh_without_a_tape_does_not_start_the_clock(stub_claude):
    result = news_brief.start_refresh(background=False)
    assert result["note"] == "no_headlines"
    assert news_brief.last_refresh_at() is None


def test_refresh_limit_caps_the_batch(stub_claude, monkeypatch):
    monkeypatch.setenv("BSH_NEWS_BRIEF_REFRESH_LIMIT", "2")
    news_brief.start_refresh(
        items=[{"title": f"Story {i}"} for i in range(5)], limit=16, background=False
    )
    assert len(stub_claude) == 2


def test_schedule_is_due_every_six_hours(monkeypatch):
    assert news_brief.seconds_until_due() <= 0, "a server that never refreshed is due"
    news_brief._mark_refreshed(news_brief._now() - timedelta(hours=1))
    wait = news_brief.seconds_until_due()
    assert 5 * 3600 - 60 < wait <= 5 * 3600
    state = json.loads((news_brief.BRIEFS_ROOT / "_refresh_state.json").read_text())
    assert state["last_refresh_at"]

    monkeypatch.setenv("BSH_NEWS_BRIEF_REFRESH_HOURS", "0")
    assert news_brief.next_refresh_at() is None
    assert news_brief.refresh_status()["next_refresh_at"] is None


def test_refresh_loop_needs_an_interval_and_an_engine(monkeypatch):
    """The gate asks ai_engine, not the Claude CLI: a Gemini key with no CLI
    installed must still start the loop."""
    monkeypatch.setattr(news_brief, "_LOOP_STARTED", False)
    monkeypatch.setattr(news_brief, "_refresh_loop", lambda: None)
    monkeypatch.setattr(news_brief.ai_engine, "available", lambda: False)
    assert news_brief.start_refresh_loop() is False

    monkeypatch.setattr(news_brief.ai_engine, "available", lambda: True)
    monkeypatch.setenv("BSH_NEWS_BRIEF_REFRESH_HOURS", "0")
    assert news_brief.start_refresh_loop() is False

    monkeypatch.delenv("BSH_NEWS_BRIEF_REFRESH_HOURS")
    assert news_brief.start_refresh_loop() is True
    assert news_brief.start_refresh_loop() is False, "idempotent"


def test_brief_statuses_reports_ready(stub_claude):
    news_brief.write_brief(title="Ready story")
    status = news_brief.brief_statuses(
        [{"title": "Ready story"}, {"title": "Missing story"}], lang="zh"
    )
    assert status["ready"] == 1
    by_title = {row["title"]: row for row in status["items"]}
    assert by_title["Ready story"]["ready"] is True
    assert by_title["Missing story"]["ready"] is False


# ---- Shared plumbing ---------------------------------------------------------


def test_structured_prompt_passes_model_effort_and_tools(monkeypatch):
    commands: list[list[str]] = []

    class _Proc:
        returncode = 0
        pid = 4242

        def communicate(self, timeout=None):
            return json.dumps({"result": '{"ok": true}'}), ""

        def poll(self):
            return 0

    def _popen(cmd, **kwargs):
        commands.append(cmd)
        return _Proc()

    # The non-streaming path spawns through the process registry, so fake
    # that: faking subprocess.run here would launch the real claude CLI.
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(claude_runner, "_popen_claude", _popen)

    data, err = claude_runner.run_structured_prompt(
        system_prompt="s",
        user_prompt="u",
        schema={"type": "object"},
        model="sonnet",
        effort="medium",
        tools="",
    )
    assert err is None and data == {"ok": True}
    cmd = commands[0]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--effort") + 1] == "medium"
    assert cmd[cmd.index("--tools") + 1] == ""

    claude_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema={"type": "object"}
    )
    assert not {"--model", "--effort", "--tools"} & set(commands[1])


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


def test_a_refresh_that_wrote_nothing_does_not_buy_a_full_interval(monkeypatch):
    """One bad window (expired key, model outage) must not leave every story
    on the no-AI fallback for the whole refresh interval with nothing
    retrying — that is what marking the clock before the work did."""
    monkeypatch.setattr(
        news_brief.ai_engine,
        "structured",
        lambda **kwargs: (None, {"engine": "gemini"}, "engine down"),
    )
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))
    news_brief.start_refresh(
        items=[{"title": "Story A"}, {"title": "Story B"}], background=False
    )

    status = news_brief.refresh_status()
    assert status["failed"] == 2 and status["done"] == 0
    # Next attempt is the short retry, not a full interval away.
    due = news_brief.seconds_until_due()
    assert due is not None
    assert due <= news_brief.FAILED_RETRY_MINUTES * 60 + 5


def test_a_refresh_that_wrote_something_resets_the_clock(stub_claude, monkeypatch):
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))
    news_brief.start_refresh(
        items=[{"title": "Story A"}, {"title": "Story B"}], background=False
    )
    status = news_brief.refresh_status()
    assert status["done"] == 2 and status["failed"] == 0
    due = news_brief.seconds_until_due()
    # A successful run buys the full interval.
    assert due > news_brief.FAILED_RETRY_MINUTES * 60


def test_key_figures_are_carried_onto_the_ai_briefing(stub_claude, monkeypatch):
    """The news UI has always rendered a Key figures block, but until the
    schema gained the field only the no-AI basic briefing filled it."""
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))
    written = news_brief.write_brief(title="Headline", company="ZaiNar")

    en = written["en"]
    assert en["key_figures"] == [
        "Revenue rose 40% year on year in the en period.",
        "Headcount reached 180, up from 120 a year earlier.",
    ]
    # iOS and older bilingual callers read the language-suffixed key.
    assert en["key_figures_en"] == en["key_figures"]
    assert written["zh"]["key_figures_zh"][0].endswith("zh period.")


def test_the_briefing_call_asks_for_room_and_reasoning(stub_claude, monkeypatch):
    """Length was the ask: on the default ceiling and low reasoning the model
    returned roughly half the requested word count."""
    monkeypatch.setattr(news_brief, "fetch_article_text", lambda url, **kw: ("", None))
    news_brief.write_brief(title="Headline")
    call = stub_claude[0]
    assert call["max_output_tokens"] == news_brief.BRIEF_MAX_OUTPUT_TOKENS
    assert call["thinking_level"] == news_brief.BRIEF_THINKING == "medium"
