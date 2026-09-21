"""The Pulse morning brief writes itself each morning.

Left to the buttons the brief is written when someone remembers, so the
analyst reads yesterday's tape or waits ninety seconds for a long note.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from server import market_brief

BRIEF = {"date": "2026-09-17", "indices": [], "movers": {}, "calendar": [], "alerts": []}


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    for name in ("BSH_MORNING_BRIEF", "BSH_MORNING_BRIEF_HOUR", "BSH_MORNING_BRIEF_LENGTH"):
        monkeypatch.delenv(name, raising=False)


def _at(hour: int, day: int = 17, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute).astimezone()


def test_not_due_before_the_hour():
    assert market_brief.morning_due(_at(6)) is False
    assert market_brief.morning_due(_at(7)) is True


def test_a_custom_hour_is_honoured(monkeypatch):
    monkeypatch.setenv("BSH_MORNING_BRIEF_HOUR", "9")
    assert market_brief.morning_due(_at(8)) is False
    assert market_brief.morning_due(_at(9)) is True


def test_an_invalid_hour_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("BSH_MORNING_BRIEF_HOUR", "99")
    assert market_brief.morning_hour() == market_brief.DEFAULT_MORNING_HOUR
    monkeypatch.setenv("BSH_MORNING_BRIEF_HOUR", "nonsense")
    assert market_brief.morning_hour() == market_brief.DEFAULT_MORNING_HOUR


def test_the_schedule_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("BSH_MORNING_BRIEF", "0")
    assert market_brief.morning_due(_at(9)) is False
    assert market_brief.start_morning_loop() is False


def test_a_brief_that_already_has_a_note_is_not_rewritten(monkeypatch):
    """Restarting the server all morning must not spend a call each time."""
    monkeypatch.setattr(
        market_brief, "load_brief", lambda date=None: {**BRIEF, "note": {"length": "long"}}
    )
    assert market_brief.morning_due(_at(9)) is False


def test_a_written_note_stops_the_day_repeating(monkeypatch):
    written: dict = {}
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: dict(written) or None)
    # A rebuild drops the note, exactly as build_brief does.
    monkeypatch.setattr(market_brief, "build_brief", lambda: written.pop("note", None))
    monkeypatch.setattr(
        market_brief,
        "write_note",
        lambda length="long": written.update({**BRIEF, "note": {"length": length}}),
    )

    assert market_brief.morning_due(_at(8)) is True
    market_brief.run_morning_brief(_at(8))
    assert market_brief.morning_due(_at(11)) is False

    # A new day: yesterday's note does not count for today.
    written.clear()
    assert market_brief.morning_due(_at(8, day=18)) is True


def test_a_rebuilt_brief_becomes_due_again_the_same_day(monkeypatch):
    """`build_brief` drops the note on purpose — it described the previous
    tape — so a "Build brief" click after the morning run leaves the desk
    with nothing. Keying off the recorded run date alone made the schedule
    see its own completed run and refuse to write another all day."""
    written: dict = {}
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: dict(written) or None)
    monkeypatch.setattr(market_brief, "build_brief", lambda: None)
    monkeypatch.setattr(
        market_brief,
        "write_note",
        lambda length="long": written.update({**BRIEF, "note": {"length": length}}),
    )

    market_brief.run_morning_brief(_at(8))
    assert market_brief.morning_due(_at(9)) is False

    # Someone clicks Build brief: the snapshot is rebuilt and the note goes.
    written.pop("note")
    assert market_brief.morning_due(_at(9)) is True


def test_it_writes_the_long_note_by_default(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: None)
    monkeypatch.setattr(market_brief, "build_brief", lambda: BRIEF)

    def write_note(length="long"):
        seen["length"] = length
        return {**BRIEF, "note": {"length": length}}

    monkeypatch.setattr(market_brief, "write_note", write_note)
    market_brief.run_morning_brief(_at(8))
    assert seen["length"] == "long"

    monkeypatch.setenv("BSH_MORNING_BRIEF_LENGTH", "short")
    market_brief.run_morning_brief(_at(8, day=18))
    assert seen["length"] == "short"


def test_a_failed_morning_never_takes_the_loop_down(monkeypatch):
    """Market data or the model can be out; the thread must survive it."""
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: None)
    monkeypatch.setattr(market_brief, "build_brief", lambda: BRIEF)

    def boom(length="long"):
        raise RuntimeError("engine down")

    monkeypatch.setattr(market_brief, "write_note", boom)
    assert market_brief.run_morning_brief(_at(8)) is None

    status = market_brief.morning_status(_at(8, minute=5))
    assert status["last_run_ok"] is False
    assert "engine down" in status["last_error"]
    # Recorded, so a failing morning is not retried every five minutes.
    assert market_brief.morning_due(_at(8, minute=5)) is False


def _failing_morning(monkeypatch) -> dict:
    """A note writer that fails until told otherwise; counts its calls."""
    written: dict = {}
    calls = {"n": 0, "fail": True}
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: dict(written) or None)
    monkeypatch.setattr(market_brief, "build_brief", lambda: None)

    def write_note(length="long"):
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("You've hit your weekly limit")
        written.update({**BRIEF, "note": {"length": length}})
        return dict(written)

    monkeypatch.setattr(market_brief, "write_note", write_note)
    return calls


def test_a_failed_morning_is_tried_again_an_hour_later(monkeypatch):
    """One failure used to cost the whole day: a server started before its
    Gemini key was added never wrote the brief, even once the key was in."""
    calls = _failing_morning(monkeypatch)
    market_brief.run_morning_brief(_at(8))

    assert market_brief.morning_due(_at(8, minute=59)) is False
    status = market_brief.morning_status(_at(8, minute=30))
    assert status["attempts"] == 1
    assert status["next_retry_at"] == _at(9).isoformat()

    assert market_brief.morning_due(_at(9)) is True
    calls["fail"] = False
    assert market_brief.run_morning_brief(_at(9)) is not None
    assert market_brief.morning_due(_at(10)) is False
    status = market_brief.morning_status(_at(10))
    assert status["last_run_ok"] is True
    assert status["next_retry_at"] is None


def test_a_morning_that_keeps_failing_waits_for_tomorrow(monkeypatch):
    calls = _failing_morning(monkeypatch)
    for hour in (8, 9, 10):
        assert market_brief.morning_due(_at(hour)) is True
        market_brief.run_morning_brief(_at(hour))

    assert calls["n"] == market_brief.MORNING_MAX_ATTEMPTS
    assert market_brief.morning_due(_at(15)) is False
    status = market_brief.morning_status(_at(15))
    assert status["attempts"] == market_brief.MORNING_MAX_ATTEMPTS
    assert status["next_retry_at"] is None
    # The count is per day: tomorrow starts over.
    assert market_brief.morning_due(_at(7, day=18)) is True


def test_a_failure_recorded_before_retries_existed_is_not_retried(monkeypatch):
    """Without the time of the failure there is no hour to wait out."""
    monkeypatch.setattr(market_brief, "load_brief", lambda date=None: None)
    market_brief._write_morning_state(
        {"last_run_date": "2026-09-17", "length": "long", "ok": False, "error": "x"}
    )
    assert market_brief.morning_due(_at(15)) is False
    assert market_brief.morning_status(_at(15))["next_retry_at"] is None
    assert market_brief.morning_due(_at(7, day=18)) is True


def test_the_loop_does_not_start_without_an_engine(monkeypatch):
    monkeypatch.setattr(market_brief.ai_engine, "available", lambda *_a, **_k: False)
    assert market_brief.start_morning_loop() is False


def test_a_claude_cli_alone_does_not_start_the_loop(monkeypatch):
    """The brief is Gemini's to write, so a desk on Claude with no Gemini key
    has nothing that can write it."""
    # Were the gate wrong, the thread it starts must not reach the network.
    monkeypatch.setattr(market_brief, "_morning_loop", lambda: None)
    monkeypatch.setattr(market_brief, "_MORNING_LOOP_STARTED", False)
    monkeypatch.setattr(market_brief.ai_engine, "policy", lambda: "claude")
    monkeypatch.setattr(market_brief.ai_engine.claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(market_brief.ai_engine.gemini_runner, "is_available", lambda: False)
    assert market_brief.start_morning_loop() is False
