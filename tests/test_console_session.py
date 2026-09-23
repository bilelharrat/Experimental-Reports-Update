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
    assert meta["output_language"] == "en"  # default


def test_output_language_threads_to_hydrate_and_ask(tmp_consoles, monkeypatch):
    """The session's output_language must reach claude_runner on both
    the initial hydration call and every follow-up ask."""
    captured: dict = {"hydrate": [], "ask": []}

    def fake_hydrate(*, output_language=None, **kw):
        captured["hydrate"].append(output_language)
        return _stub_hydrate_ok(**kw)

    def fake_ask(*, output_language=None, **kw):
        captured["ask"].append(output_language)
        return _make_stub_ask(reply_text="ok")(**kw)

    monkeypatch.setattr(claude_runner, "run_console_hydrate", fake_hydrate)
    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        output_language="zh",
    )
    sid = meta["id"]
    # Hydrate ran in a background thread; wait briefly for the kwarg
    # to land.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not captured["hydrate"]:
        time.sleep(0.02)
    assert captured["hydrate"] == ["zh"]

    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="hi", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info["turn_id"])
    assert captured["ask"] == ["zh"]
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


def test_skip_hydrate_first_ask_bootstraps_claude_session(tmp_consoles, monkeypatch):
    """Co-Pilot quick sessions skip hydrate; first ask must use --session-id."""
    captured: list[bool] = []

    def fake_ask(*, bootstrap_session=False, **kwargs):
        captured.append(bool(bootstrap_session))
        return {
            "ok": True, "subtype": "success",
            "text": "bootstrapped",
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0},
            "cost_usd": 0.001,
            "duration_ms": 100,
        }

    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        skip_hydrate=True,
    )
    sid = meta["id"]
    assert console_store.load_meta(COMPANY, sid)["hydration_status"] == "skipped"

    info1 = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="q1", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info1["turn_id"])
    assert captured == [True]
    assert console_store.load_meta(COMPANY, sid).get("claude_session_ready") is True

    info2 = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="q2", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info2["turn_id"])
    assert captured == [True, False]


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
    # Empty Claude text still gets a visible fallback for the UI.
    assert assistant["text"] == assistant["error"]


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


def test_recover_flips_in_progress_hydration(tmp_consoles):
    # skip_hydrate: a live hydration worker's "done" write can land after
    # the forced state below and hide recover()'s flip.
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
        skip_hydrate=True,
    )
    sid = meta["id"]
    # What a restart mid-hydration leaves on disk: in_progress, no worker.
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


def test_auto_rename_after_first_successful_turn(tmp_consoles, monkeypatch):
    """Once the first assistant record lands, run_console_title is called
    in a background thread and the session's meta.title is updated.
    """
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="Burn was $14.2M last Q."))
    monkeypatch.setattr(claude_runner, "run_console_title",
                        lambda **kw: "AMI Burn Rate Q1 2025")
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    assert meta["title"].startswith("Session ·")  # default

    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="What was burn last quarter?", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info["turn_id"])

    # Auto-rename runs in a daemon thread; poll briefly.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        m = console_store.load_meta(COMPANY, sid)
        if m and m.get("title") == "AMI Burn Rate Q1 2025":
            return
        time.sleep(0.05)
    pytest.fail(f"title was not auto-renamed; current={m.get('title')!r}")


def test_auto_rename_skipped_after_second_turn(tmp_consoles, monkeypatch):
    """If the title is already set, _maybe_auto_rename short-circuits."""
    title_calls = []
    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="ok"))

    def fake_title(**kw):
        title_calls.append(kw)
        return "Should not be called"
    monkeypatch.setattr(claude_runner, "run_console_title", fake_title)

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    # Pretend the user already set a manual title.
    console_store.update_meta(COMPANY, sid, title="Manually picked")

    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="hi", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info["turn_id"])
    # Give the daemon a beat to NOT do anything.
    time.sleep(0.1)
    assert title_calls == []
    assert console_store.load_meta(COMPANY, sid)["title"] == "Manually picked"


# ---- Persona swap by company_type --------------------------------------


def test_public_company_uses_trader_persona(tmp_consoles, monkeypatch):
    """When the target company is public, hydrate + ask both receive the
    trader-analyst skill file, not the default analyst persona.
    """
    from server import storage

    # Seed a public company in the same DATA_DIR the storage layer is
    # rooted to. The tmp_consoles fixture redirects only console paths;
    # we need to also redirect storage to a clean companies.yaml for
    # this test.
    storage_dir = tmp_consoles["root"]
    monkeypatch.setattr(storage, "DATA_DIR", storage_dir)
    monkeypatch.setattr(storage, "COMPANIES_FILE", storage_dir / "companies.yaml")
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": COMPANY, "name": "AMD", "ticker": "AMD",
         "status": "public", "company_type": "public"},
    ])

    captured = {"hydrate": [], "ask": []}

    def fake_hydrate(*, skill_path, **kw):
        captured["hydrate"].append(Path(skill_path).name)
        return _stub_hydrate_ok(**kw)

    def fake_ask(*, skill_path, **kw):
        captured["ask"].append(Path(skill_path).name)
        return _make_stub_ask(reply_text="ok")(**kw)

    monkeypatch.setattr(claude_runner, "run_console_hydrate", fake_hydrate)
    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    assert meta["skill_path"].endswith("bsh_company_console_public.md")

    sid = meta["id"]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not captured["hydrate"]:
        time.sleep(0.02)
    assert captured["hydrate"] == ["bsh_company_console_public.md"]

    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="hi", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info["turn_id"])
    assert captured["ask"] == ["bsh_company_console_public.md"]


def test_private_company_uses_default_persona(tmp_consoles, monkeypatch):
    from server import storage
    storage_dir = tmp_consoles["root"]
    monkeypatch.setattr(storage, "DATA_DIR", storage_dir)
    monkeypatch.setattr(storage, "COMPANIES_FILE", storage_dir / "companies.yaml")
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": COMPANY, "name": "Anduril", "status": "private",
         "company_type": "private"},
    ])

    captured = []

    def fake_hydrate(*, skill_path, **kw):
        captured.append(Path(skill_path).name)
        return _stub_hydrate_ok(**kw)

    monkeypatch.setattr(claude_runner, "run_console_hydrate", fake_hydrate)
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="ok"))

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    assert meta["skill_path"].endswith("bsh_company_console.md")

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not captured:
        time.sleep(0.02)
    assert captured == ["bsh_company_console.md"]


def test_skill_path_survives_company_retype(tmp_consoles, monkeypatch):
    """A session created when the company was private must keep using
    the default persona even if the company later flips to public."""
    from server import storage
    storage_dir = tmp_consoles["root"]
    monkeypatch.setattr(storage, "DATA_DIR", storage_dir)
    monkeypatch.setattr(storage, "COMPANIES_FILE", storage_dir / "companies.yaml")
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": COMPANY, "name": "Foo", "status": "private",
         "company_type": "private"},
    ])

    monkeypatch.setattr(claude_runner, "run_console_hydrate", _stub_hydrate_ok)
    monkeypatch.setattr(claude_runner, "run_console_ask",
                        _make_stub_ask(reply_text="ok"))

    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False, include_library_docs=False,
    )
    sid = meta["id"]
    # Now the company gets re-typed to public.
    storage.update_company(COMPANY, company_type="public", ticker="FOO",
                           status="public")

    captured = []

    def fake_ask(*, skill_path, **kw):
        captured.append(Path(skill_path).name)
        return _make_stub_ask(reply_text="ok")(**kw)

    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)
    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="hi", attachments=[],
    )
    _wait_for_assistant(COMPANY, sid, info["turn_id"])
    # Session was created when the company was private, so the
    # private persona should stay locked in even after re-typing.
    assert captured == ["bsh_company_console.md"]


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


# ---- Editing a question you already sent --------------------------------


def _quick_session():
    return console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False,
        include_library_docs=False,
        skip_hydrate=True,
        session_kind="copilot_quick",
    )


def test_an_edited_question_replaces_the_one_it_rewrites(tmp_consoles, monkeypatch):
    """The thread shows the new question; the old one and the answer it
    drew are gone — for everyone, because the thread is shared."""
    monkeypatch.setattr(claude_runner, "run_console_ask", _make_stub_ask(reply_text="ok"))
    sid = _quick_session()["id"]

    first = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="whats the mote here", attachments=[],
    )["turn_id"]
    _wait_for_assistant(COMPANY, sid, first)
    second = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="what is the moat here?", attachments=[], edits=first,
    )["turn_id"]

    thread = console_store.read_turns(COMPANY, sid)
    assert [t["text"] for t in thread if t["role"] == "user"] == [
        "what is the moat here?"
    ]
    assert not [t for t in thread if t["id"] == first]
    assert second != first

    # The log itself keeps every version — nothing is rewritten on disk.
    whole = console_store.read_turns(COMPANY, sid, include_superseded=True)
    assert "whats the mote here" in [t.get("text") for t in whole]


def test_editing_an_edit_leaves_one_question(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_ask", _make_stub_ask(reply_text="ok"))
    sid = _quick_session()["id"]

    first = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="v1", attachments=[],
    )["turn_id"]
    second = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="v2", attachments=[], edits=first,
    )["turn_id"]
    console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="v3", attachments=[], edits=second,
    )

    users = [t for t in console_store.read_turns(COMPANY, sid) if t["role"] == "user"]
    assert [t["text"] for t in users] == ["v3"]


def test_a_question_is_signed_by_whoever_asked(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_ask", _make_stub_ask(reply_text="ok"))
    sid = _quick_session()["id"]

    console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="who owns this?", attachments=[],
        author={"email": "sam@bshventures.com", "name": "Sam Ortiz"},
    )

    user_turn = next(
        t for t in console_store.read_turns(COMPANY, sid) if t["role"] == "user"
    )
    assert user_turn["author"] == {
        "email": "sam@bshventures.com",
        "name": "Sam Ortiz",
    }


def test_an_unsigned_question_carries_no_author(tmp_consoles, monkeypatch):
    monkeypatch.setattr(claude_runner, "run_console_ask", _make_stub_ask(reply_text="ok"))
    sid = _quick_session()["id"]

    console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="anon", attachments=[],
        author={"email": "", "name": ""},
    )

    user_turn = next(
        t for t in console_store.read_turns(COMPANY, sid) if t["role"] == "user"
    )
    assert "author" not in user_turn


def test_an_edited_question_keeps_the_file_it_asked_about(
    tmp_consoles, monkeypatch, real_docx_bytes
):
    """Rewording "what's in this?" must not turn it into a question about
    nothing — which is how it answered before, confidently and wrongly.
    """
    seen: list[list[str]] = []

    def fake_ask(*, attachments=None, **kw):
        seen.append(list(attachments or []))
        return _make_stub_ask(reply_text="ok")(attachments=attachments, **kw)

    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)
    sid = _quick_session()["id"]
    record = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="term-sheet.docx", data=real_docx_bytes,
    )

    first = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="what is in this?", attachments=[record["stored_name"]],
        attachment_names={record["stored_name"]: "term-sheet.docx"},
    )["turn_id"]
    _wait_for_assistant(COMPANY, sid, first)

    second = console_session.submit_ask(
        company_id=COMPANY, session_id=sid,
        prompt="just the liquidation preference, please",
        attachments=[], edits=first,
    )["turn_id"]
    _wait_for_assistant(COMPANY, sid, second)

    assert seen[-1] == [record["stored_name"]]
    edited = next(
        t for t in console_store.read_turns(COMPANY, sid)
        if t["id"] == second and t["role"] == "user"
    )
    # And the chip still names the file the way the analyst picked it.
    assert [a["name"] for a in edited["attachments"]] == ["term-sheet.docx"]


def test_an_edit_that_brings_its_own_file_does_not_inherit(
    tmp_consoles, monkeypatch, real_docx_bytes, png_bytes
):
    seen: list[list[str]] = []

    def fake_ask(*, attachments=None, **kw):
        seen.append(list(attachments or []))
        return _make_stub_ask(reply_text="ok")(attachments=attachments, **kw)

    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)
    sid = _quick_session()["id"]
    doc = console_store.save_attachment(
        company_id=COMPANY, session_id=sid,
        filename="term-sheet.docx", data=real_docx_bytes,
    )
    chart = console_store.save_attachment(
        company_id=COMPANY, session_id=sid, filename="chart.png", data=png_bytes,
    )

    first = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="read this",
        attachments=[doc["stored_name"]],
    )["turn_id"]
    _wait_for_assistant(COMPANY, sid, first)
    second = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt="this one instead",
        attachments=[chart["stored_name"]], edits=first,
    )["turn_id"]
    _wait_for_assistant(COMPANY, sid, second)

    assert seen[-1] == [chart["stored_name"]]
