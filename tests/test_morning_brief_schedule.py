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


def _at(hour: int, day: int = 17) -> datetime:
    return datetime(2026, 9, day, hour, 0).astimezone()


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

    status = market_brief.morning_status()
    assert status["last_run_ok"] is False
    assert "engine down" in status["last_error"]
    # Recorded, so a failing morning is not retried every five minutes.
    assert market_brief.morning_due(_at(9)) is False


def test_the_loop_does_not_start_without_an_engine(monkeypatch):
    monkeypatch.setattr(market_brief.ai_engine, "available", lambda: False)
    assert market_brief.start_morning_loop() is False
