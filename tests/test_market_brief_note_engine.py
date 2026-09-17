"""The daily desk note runs on the engine policy, and says which one wrote it."""
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


def test_a_fallback_is_visible_on_the_stored_note(monkeypatch, archived_brief):
    _stub(
        monkeypatch,
        SHORT_NOTE,
        {"engine": "claude", "model": None, "fallback_reason": "gemini HTTP 429 — quota"},
    )
    market_brief.write_note("2026-09-16")
    stored = market_brief.load_brief("2026-09-16")["note"]
    assert stored["engine"] == "claude"
    assert stored["engine_fallback_reason"] == "gemini HTTP 429 — quota"


def test_the_long_note_buys_more_reasoning_than_the_short_one(monkeypatch, archived_brief):
    long_note = {
        "headline_en": "A long read",
        "headline_zh": "长篇",
        "sections_en": [{"heading": "Tape", "body": "..."}],
        "sections_zh": [{"heading": "行情", "body": "..."}],
    }
    calls = _stub(monkeypatch, long_note, {"engine": "gemini", "model": "m", "fallback_reason": None})
    market_brief.write_note("2026-09-16", length="long")
    assert calls[0]["thinking_level"] == "medium"


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
