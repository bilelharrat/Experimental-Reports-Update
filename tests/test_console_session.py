"""Tests for server/console_session.py — dispatcher serialization,
recovery sweep, and create→ask→archive happy path with the Claude
helpers stubbed out.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from server import (
    claude_runner,
    console_session,
    console_store,
    files_store,
    research_store,
)


COMPANY = "ami_labs"


# ---- Stub helpers -------------------------------------------------------


def _stub_hydrate_ok(**kwargs):
    """Fake hydrate that emits a job_init + done and returns success."""
    progress = kwargs["progress"]
    progress.emit("done", text="Ready. 0 documents loaded.",
                  usage={"input_tokens": 100, "output_tokens": 10,
                         "cache_read_input_tokens": 0,
                         "cache_creation_input_tokens": 0},
                  cost_usd=0.001)
    return {
        "ok": True, "subtype": "success",
        "text": "Ready. 0 documents loaded.",
        "usage": {"input_tokens": 100, "output_tokens": 10,
                  "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0},
        "cost_usd": 0.001,
        "duration_ms": 500,
    }


def _make_stub_ask(*, reply_text="OK", delay_s: float = 0.0):
    def stub(**kwargs):
        if delay_s:
            time.sleep(delay_s)
        return {
            "ok": True, "subtype": "success",
            "text": reply_text,
            "usage": {"input_tokens": 200, "output_tokens": 30,
                      "cache_read_input_tokens": 100,
                      "cache_creation_input_tokens": 0},
            "cost_usd": 0.005,
            "duration_ms": 600,
        }
    return stub


def _stub_ask_error(**kwargs):
    return {
        "ok": False, "subtype": "error", "text": "",
        "usage": {},
        "cost_usd": None, "duration_ms": None,
        "error": "claude exited 1",
        "interrupt_reason": "subprocess_died",
    }


def _wait_for_assistant(company, sid, turn_id, timeout=3.0):
    """Poll turns.jsonl until the matching assistant record appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for t in console_store.read_turns(company, sid):
            if t.get("id") == turn_id and t.get("role") == "assistant":
                return t
        time.sleep(0.05)
    raise AssertionError(f"assistant turn for {turn_id} did not arrive within {timeout}s")


# ---- Happy path --------------------------------------------------------


def test_create_session_no_files(tmp_consoles, monkeypatch):
    """create_session works even with both flags off and no source files."""
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False,
        include_library_docs=False,
    )
    assert meta["status"] == "active"
    assert meta["included_files"] == []
    # Hydration worker writes hydration_status; wait briefly for it.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        m = console_store.load_meta(COMPANY, meta["id"])
        if m and m.get("hydration_status") == "done":
            return
        time.sleep(0.05)
    pytest.fail("hydration_status did not become done")


def test_ask_writes_assistant_turn(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="Hello there."))
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="what's up?", attachments=[],
    )
    assistant = _wait_for_assistant(COMPANY, sid, info["turn_id"])
    assert assistant["subtype"] == "success"
    assert assistant["text"] == "Hello there."

    refreshed = console_store.load_meta(COMPANY, sid)
    # Tokens accumulated.
    assert refreshed["tokens"]["input"] >= 200
    assert refreshed["tokens"]["total_cost_usd"] > 0


def test_queue_serializes_within_session(tmp_consoles, monkeypatch):
    """Two asks back-to-back run one at a time and complete in order."""
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    # Slow ask: 200ms each. If they ran in parallel, both would
    # complete in ~200ms; serial → ~400ms.
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="OK", delay_s=0.2))
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    started = time.monotonic()
    info1 = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="q1", attachments=[],
    )
    info2 = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="q2", attachments=[],
    )
    assert info1["queue_position"] == 0
    assert info2["queue_position"] == 1
    _wait_for_assistant(COMPANY, sid, info1["turn_id"], timeout=5.0)
    _wait_for_assistant(COMPANY, sid, info2["turn_id"], timeout=5.0)
    elapsed = time.monotonic() - started
    # Serial baseline ~0.4s + overhead. Allow generous bound but assert
    # it didn't finish in <300ms (which would indicate parallelism).
    assert elapsed >= 0.3, f"asks ran in parallel (elapsed={elapsed:.2f}s)"


def test_archived_session_rejects_ask(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    console_session.archive_session(company_id=COMPANY, session_id=sid)
    with pytest.raises(ValueError, match="session_archived"):
        console_session.submit_ask(
            company_id=COMPANY, session_id=sid,
            prompt="too late", attachments=[],
        )


def test_ask_error_path_writes_error_turn(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    monkeypatch.setattr(claude_runner, "run_console_ask", _stub_ask_error)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="will fail", attachments=[],
    )
    assistant = _wait_for_assistant(COMPANY, sid, info["turn_id"])
    assert assistant["subtype"] == "error"
    assert "claude exited" in assistant["error"]
    assert assistant["interrupt_reason"] == "subprocess_died"


# ---- Recovery sweep -----------------------------------------------------


def test_recover_synthesizes_assistant_for_orphan_user_turn(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    # Hand-write an orphan user turn.
    orphan_id = console_store.new_turn_id()
    console_store.append_turn(
        COMPANY, sid,
        {"ts": "2026-01-01T00:00:00Z", "id": orphan_id, "role": "user",
         "text": "I never got an answer."},
    )

    console_session.recover()

    turns = console_store.read_turns(COMPANY, sid)
    matching = [t for t in turns if t.get("id") == orphan_id]
    roles = [t["role"] for t in matching]
    assert roles == ["user", "assistant"]
    assert matching[1]["subtype"] == "error"
    assert "Interrupted by server restart" in matching[1]["error"]


def test_recover_flips_in_progress_hydration(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    # Force the state we care about, regardless of whether the stub's
    # background hydration has finished already.
    console_store.update_meta(COMPANY, sid, hydration_status="in_progress")

    console_session.recover()

    refreshed = console_store.load_meta(COMPANY, sid)
    assert refreshed["hydration_status"] == "error"
    assert refreshed["hydration_error"] == "Interrupted by server restart"


def test_recover_is_idempotent(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    orphan_id = console_store.new_turn_id()
    console_store.append_turn(
        COMPANY, sid,
        {"ts": "2026-01-01T00:00:00Z", "id": orphan_id, "role": "user", "text": "x"},
    )
    console_session.recover()
    console_session.recover()  # second pass should be a no-op
    turns = [t for t in console_store.read_turns(COMPANY, sid) if t.get("id") == orphan_id]
    assert len(turns) == 2  # one user + one synthesized assistant, not three


# ---- Cancel -------------------------------------------------------------


def test_cancel_in_flight_turn(tmp_consoles, monkeypatch):
    """When ask is in flight, cancel_turn returns True and sets the
    registered event; after it completes, cancel returns False."""
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)

    # An ask that blocks until we tell it to finish.
    release = threading.Event()
    cancel_observed = threading.Event()

    def slow_ask(*, cancel_event, **kwargs):
        # Wait for either the test releasing us OR the cancel event.
        while not release.is_set():
            if cancel_event is not None and cancel_event.is_set():
                cancel_observed.set()
                return {
                    "ok": False, "subtype": "error", "text": "",
                    "usage": {}, "cost_usd": None, "duration_ms": None,
                    "error": "cancelled", "interrupt_reason": "user_cancelled",
                }
            time.sleep(0.01)
        return {
            "ok": True, "subtype": "success", "text": "done",
            "usage": {"input_tokens": 0, "output_tokens": 0,
                      "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0},
            "cost_usd": 0.0, "duration_ms": 10,
        }

    monkeypatch.setattr(claude_runner, "run_console_ask", slow_ask)

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="cancel me", attachments=[],
    )
    # Give the worker time to pick up the turn and register a cancel
    # event.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if console_session.cancel_turn(COMPANY, sid, info["turn_id"]):
            break
        time.sleep(0.02)
    else:
        pytest.fail("cancel_turn never found a cancellable turn")

    assert cancel_observed.wait(timeout=1.0)
    assistant = _wait_for_assistant(COMPANY, sid, info["turn_id"])
    assert assistant["subtype"] == "error"
    assert assistant["interrupt_reason"] == "user_cancelled"

    # After completion, cancel is a no-op.
    assert console_session.cancel_turn(COMPANY, sid, info["turn_id"]) is False
