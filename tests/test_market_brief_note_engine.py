"""The morning brief note is Gemini's to write, and says which model wrote it."""
from __future__ import annotations

import json

import pytest

from server import market_brief

BRIEF = {
    "date": "2026-09-16",
    "generated_at": "2026-09-16T12:00:00Z",
    "indices": [{"ticker": "SPY", "change_pct": 0.8}],
    "movers": {"up": [], "down": []},
    "calendar": [],
    "alerts": [],
}

SHORT_NOTE = {
    "headline_en": "Risk on",
    "headline_zh": "风险偏好回升",
    "bullets_en": ["SPY up 0.8%", "  ", "Breadth improving"],
    "bullets_zh": ["标普上涨0.8%"],
}


@pytest.fixture
def archived_brief():
    market_brief.BRIEFS_ROOT.mkdir(parents=True, exist_ok=True)
    path = market_brief.BRIEFS_ROOT / f"{BRIEF['date']}.json"
    path.write_text(json.dumps(BRIEF), encoding="utf-8")
    return dict(BRIEF)


def _stub(monkeypatch, data, meta, error=None):
    calls: list[dict] = []

    def structured(**kwargs):
        calls.append(kwargs)
        return data, meta, error

    monkeypatch.setattr(market_brief.ai_engine, "structured", structured)
    return calls


def test_the_note_records_the_engine_that_wrote_it(monkeypatch, archived_brief):
    _stub(monkeypatch, SHORT_NOTE, {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None})
    note = market_brief.write_note("2026-09-16")["note"]
    assert note["engine"] == "gemini"
    assert note["model"] == "gemini-3.8-flash"
    assert note["engine_fallback_reason"] is None
    assert note["headline_en"] == "Risk on"
    # Blank bullets are dropped, as before.
    assert note["bullets_en"] == ["SPY up 0.8%", "Breadth improving"]


LONG_NOTE = {
    "headline_en": "A long read",
    "headline_zh": "长篇",
    "sections_en": [{"title": "Tape", "body": "..."}],
    "sections_zh": [{"title": "行情", "body": "..."}],
}


@pytest.fixture(params=["claude", "gemini"])
def claude_calls(request, monkeypatch):
    """The research desk is set to Claude, or to Gemini-then-Claude; the brief
    must reach Claude under neither. Returns the Claude calls made."""
    monkeypatch.setattr(market_brief.ai_engine, "policy", lambda: request.param)
    calls: list[str] = []
    monkeypatch.setattr(
        market_brief.ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **kw: calls.append(kw["name"]) or (SHORT_NOTE, None),
    )
    monkeypatch.setattr(
        market_brief.ai_engine.claude_runner,
        "run_web_research_json",
        lambda **kw: calls.append(kw["name"]) or (LONG_NOTE, None),
    )
    return calls


def test_gemini_flash_writes_the_brief_whatever_the_desk_engine_is(
    monkeypatch, archived_brief, claude_calls
):
    gemini = market_brief.ai_engine.gemini_runner
    monkeypatch.delenv("BSH_GEMINI_MODEL", raising=False)
    monkeypatch.setattr(gemini, "is_available", lambda: True)
    monkeypatch.setattr(gemini, "run_structured_prompt", lambda **kw: (SHORT_NOTE, None))
    monkeypatch.setattr(
        gemini,
        "run_grounded_json",
        lambda **kw: (
            LONG_NOTE,
            {"model": gemini.default_model(), "grounded": True, "sources": []},
            None,
        ),
    )

    short = market_brief.write_note("2026-09-16")["note"]
    long = market_brief.write_note("2026-09-16", length="long")["note"]
    for note in (short, long):
        assert (note["engine"], note["model"]) == ("gemini", "gemini-3.8-flash")
    assert claude_calls == []


def test_a_gemini_failure_is_not_handed_to_claude(monkeypatch, archived_brief, claude_calls):
    """The morning schedule tries a failed brief again an hour later; a
    Claude-written brief in the meantime is not the brief."""
    gemini = market_brief.ai_engine.gemini_runner
    monkeypatch.setattr(gemini, "is_available", lambda: True)
    monkeypatch.setattr(
        gemini, "run_structured_prompt", lambda **kw: (None, "gemini HTTP 503 — unavailable")
    )
    with pytest.raises(RuntimeError, match="503"):
        market_brief.write_note("2026-09-16")
    assert claude_calls == []
    assert "note" not in market_brief.load_brief("2026-09-16")


def test_without_a_gemini_key_the_brief_is_not_written(monkeypatch, archived_brief, claude_calls):
    monkeypatch.setattr(market_brief.ai_engine.gemini_runner, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="no Gemini API key"):
        market_brief.write_note("2026-09-16", length="long")
    assert claude_calls == []


def test_the_long_note_researches_and_the_short_one_does_not(monkeypatch, archived_brief):
    """The long note covers geoeconomics and geopolitics, which are not in
    the frozen snapshot and cannot be inferred from index moves — so it has
    to read the news. The short note is a read of the numbers it was given."""
    long_note = {
        "headline_en": "A long read",
        "headline_zh": "长篇",
        "sections_en": [{"title": "Tape", "body": "..."}],
        "sections_zh": [{"title": "行情", "body": "..."}],
    }
    grounded_calls: list[dict] = []
    structured_calls: list[dict] = []

    def grounded(**kwargs):
        grounded_calls.append(kwargs)
        return (
            long_note,
            {
                "engine": "gemini",
                "model": "m",
                "grounded": True,
                "sources": [{"title": "Reuters", "url": "https://r.example/x"}],
                "fallback_reason": None,
            },
            None,
        )

    def structured(**kwargs):
        structured_calls.append(kwargs)
        return SHORT_NOTE, {"engine": "gemini", "model": "m", "fallback_reason": None}, None

    monkeypatch.setattr(market_brief.ai_engine, "grounded", grounded)
    monkeypatch.setattr(market_brief.ai_engine, "structured", structured)

    note = market_brief.write_note("2026-09-16", length="long")["note"]
    assert len(grounded_calls) == 1 and structured_calls == []
    assert note["researched"] is True
    assert note["sources"] == [{"title": "Reuters", "url": "https://r.example/x"}]

    market_brief.write_note("2026-09-16", length="short")
    assert len(structured_calls) == 1 and len(grounded_calls) == 1


def test_an_unsourced_long_note_says_it_was_not_researched(monkeypatch, archived_brief):
    """A long note with no sources asserted geopolitics from memory. The flag
    is how a reader can tell."""
    long_note = {
        "headline_en": "A long read",
        "headline_zh": "长篇",
        "sections_en": [{"title": "Tape", "body": "..."}],
        "sections_zh": [{"title": "行情", "body": "..."}],
    }
    monkeypatch.setattr(
        market_brief.ai_engine,
        "grounded",
        lambda **kw: (long_note, {"engine": "gemini", "grounded": False, "sources": []}, None),
    )
    note = market_brief.write_note("2026-09-16", length="long")["note"]
    assert note["researched"] is False
    assert note["sources"] == []


def test_the_short_note_stays_on_low_reasoning(monkeypatch, archived_brief):
    calls = _stub(monkeypatch, SHORT_NOTE, {"engine": "gemini", "model": "m", "fallback_reason": None})
    market_brief.write_note("2026-09-16")
    assert calls[0]["thinking_level"] == "low"


def test_a_model_failure_leaves_the_frozen_numbers_alone(monkeypatch, archived_brief):
    _stub(monkeypatch, None, {"engine": "gemini", "fallback_reason": None}, "gemini HTTP 503")
    with pytest.raises(RuntimeError, match="503"):
        market_brief.write_note("2026-09-16")
    stored = market_brief.load_brief("2026-09-16")
    assert "note" not in stored
    assert stored["indices"] == BRIEF["indices"]


def test_a_missing_brief_is_a_value_error_not_a_model_call(monkeypatch):
    monkeypatch.setattr(
        market_brief.ai_engine,
        "structured",
        lambda **_kw: pytest.fail("no brief means no model spend"),
    )
    with pytest.raises(ValueError):
        market_brief.write_note("2026-09-16")


def test_the_headline_is_stored_as_a_front_page_line(monkeypatch, archived_brief):
    """Wrapping quotes, doubled spaces and a trailing full stop are the
    model's habits, not the headline's."""
    _stub(
        monkeypatch,
        {
            **SHORT_NOTE,
            "headline_en": '  "Nasdaq jumps 2.5% as chip   talks revive the AI trade." ',
            "headline_zh": "「纳指大涨2.5%，芯片谈判重燃AI交易。」",
            "dek_en": " Crude gives back its war premium as Hormuz traffic resumes. ",
            "dek_zh": "霍尔木兹航运恢复，原油回吐地缘溢价。",
        },
        {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None},
    )
    note = market_brief.write_note("2026-09-16")["note"]
    assert note["headline_en"] == "Nasdaq jumps 2.5% as chip talks revive the AI trade"
    assert note["headline_zh"] == "纳指大涨2.5%，芯片谈判重燃AI交易"
    # The dek is a sentence, so it keeps its full stop.
    assert note["dek_en"] == "Crude gives back its war premium as Hormuz traffic resumes."
    assert note["dek_zh"] == "霍尔木兹航运恢复，原油回吐地缘溢价。"


def test_both_notes_ask_for_a_front_page_headline_and_a_dek():
    for schema in (market_brief.NOTE_SCHEMA, market_brief.LONG_NOTE_SCHEMA):
        assert {"headline_en", "headline_zh", "dek_en", "dek_zh"} <= set(schema["required"])
        assert "sentence case" in schema["properties"]["headline_en"]["description"]
    for prompt in (market_brief.NOTE_SYSTEM_PROMPT, market_brief.LONG_NOTE_SYSTEM_PROMPT):
        assert "The headline and dek" in prompt


def test_a_note_written_before_the_dek_existed_still_loads(archived_brief):
    stored = {**BRIEF, "note": {"length": "long", "headline_en": "Old headline"}}
    (market_brief.BRIEFS_ROOT / f"{BRIEF['date']}.json").write_text(
        json.dumps(stored), encoding="utf-8"
    )
    assert "dek_en" not in market_brief.load_brief("2026-09-16")["note"]
