"""Warren's engines: Gemini stands in when Claude cannot answer, and the other
way round when Settings puts Gemini first.

Both engines are stubbed — ``claude_runner.run_console_ask`` and
``gemini_runner.run_chat`` — so nothing spawns a CLI or reaches the network.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import (
    claude_runner,
    console_session,
    console_store,
    gemini_runner,
    product_store,
    warren_engine,
)

COMPANY = "ami_labs"
LIMIT = "You've hit your weekly limit · resets 5pm (America/Los_Angeles)"


@pytest.fixture(autouse=True)
def _fresh_rest():
    warren_engine.reset()
    yield
    warren_engine.reset()


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("BSH_GEMINI_MODEL", raising=False)


def _claude(calls, *, ok=True, text="Claude's answer.", error=None, interrupt=None):
    """A fake ``run_console_ask`` that streams the way the real one does."""

    def fake(**kwargs):
        calls.append(kwargs)
        progress = kwargs["progress"]
        progress.emit("claude_action", action="init", model="claude-sonnet-5")
        if ok:
            progress.emit("claude_action", action="thinking", text=text)
            progress.emit("done", text=text, usage={"input_tokens": 9}, cost_usd=0.001)
            return {"ok": True, "subtype": "success", "text": text,
                    "usage": {"input_tokens": 9}, "cost_usd": 0.001}
        # The CLI echoes a usage limit as text before failing the run.
        progress.emit("claude_action", action="thinking", text=error)
        progress.emit("error", error=error, interrupt_reason=interrupt)
        outcome = {"ok": False, "subtype": "success", "text": error,
                   "usage": {}, "cost_usd": 0, "error": error}
        if interrupt:
            outcome["interrupt_reason"] = interrupt
        return outcome

    return fake


def _gemini(calls, *, text="Gemini's answer.", error=None, sources=None):
    def fake(**kwargs):
        calls.append(kwargs)
        meta = {
            "engine": "gemini",
            "model": "gemini-3.8-flash",
            "usage": {"input_tokens": 40, "output_tokens": 12},
            "cost_usd": None,
            "sources": sources or [],
            "queries": ["chip stocks today"] if sources else [],
            "grounded": bool(sources),
        }
        if error:
            return None, meta, error
        return text, meta, None

    return fake


def _warren_session(kind="copilot_quick"):
    meta = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False,
        include_library_docs=False,
        session_kind=kind,
        skip_hydrate=True,
    )
    return meta["id"]


def _ask(sid, prompt="why did chip stocks soar today"):
    info = console_session.submit_ask(
        company_id=COMPANY, session_id=sid, prompt=prompt, attachments=[],
    )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        for turn in console_store.read_turns(COMPANY, sid):
            if turn.get("id") == info["turn_id"] and turn.get("role") == "assistant":
                return info["turn_id"], turn
        time.sleep(0.02)
    raise AssertionError("no answer landed")


def _events(sid, turn_id):
    path = console_store.ask_progress_path(COMPANY, sid, turn_id)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_gemini_answers_when_claude_is_out_of_tokens(tmp_consoles, monkeypatch, gemini_key):
    claude_calls, gemini_calls = [], []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls, ok=False, error=LIMIT))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(
        gemini_calls, sources=[{"title": "reuters.com", "url": "https://example.com/r"}],
    ))
    sid = _warren_session()

    turn_id, turn = _ask(sid)

    assert turn["engine"] == "gemini"
    assert turn["model"] == "gemini-3.8-flash"
    assert turn["fallback_reason"] == LIMIT
    assert "error" not in turn
    assert turn["text"].startswith("Gemini's answer.")
    # A grounded reply links what it read.
    assert "[reuters.com](https://example.com/r)" in turn["text"]
    events = _events(sid, turn_id)
    types = [event["type"] for event in events]
    # Claude's failure must not end the stream before Gemini answers.
    assert "error" not in types
    assert types[-1] == "done"
    assert events[-1]["text"] == turn["text"]
    assert any(e.get("action") == "fallback" and e.get("engine") == "gemini" for e in events)
    # Gemini is told it has no file tools, in Warren's own persona.
    assert "Tools in this session" in gemini_calls[0]["system_prompt"]
    # The Claude CLI session was never created, so the next Claude ask must
    # still bootstrap it rather than resume nothing.
    assert not console_store.load_meta(COMPANY, sid).get("claude_session_ready")


def test_a_usage_limit_rests_claude_so_the_next_question_skips_it(
    tmp_consoles, monkeypatch, gemini_key,
):
    claude_calls, gemini_calls = [], []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls, ok=False, error=LIMIT))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    sid = _warren_session()

    _ask(sid, "first")
    _turn_id, second = _ask(sid, "second")

    assert len(claude_calls) == 1
    assert len(gemini_calls) == 2
    assert second["engine"] == "gemini"
    assert second["fallback_reason"] == LIMIT
    assert warren_engine.status()["claude_resting"] == LIMIT


def test_claude_answering_leaves_gemini_alone(tmp_consoles, monkeypatch, gemini_key):
    claude_calls, gemini_calls = [], []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    sid = _warren_session()

    _turn_id, turn = _ask(sid)

    assert gemini_calls == []
    assert turn["text"] == "Claude's answer."
    assert turn["engine"] == "claude"
    assert turn["model"] == "claude-sonnet-5"
    assert "fallback_reason" not in turn
    assert console_store.load_meta(COMPANY, sid).get("claude_session_ready") is True


def test_a_stop_is_not_handed_to_gemini(tmp_consoles, monkeypatch, gemini_key):
    claude_calls, gemini_calls = [], []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(
        claude_calls, ok=False, error="Interrupted (user_cancelled)", interrupt="user_cancelled",
    ))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    sid = _warren_session()

    turn_id, turn = _ask(sid)

    assert gemini_calls == []
    assert turn["interrupt_reason"] == "user_cancelled"
    assert [e["type"] for e in _events(sid, turn_id)][-1] == "error"


def test_without_a_gemini_key_claudes_error_is_unchanged(tmp_consoles, monkeypatch):
    claude_calls = []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls, ok=False, error=LIMIT))
    sid = _warren_session()

    turn_id, turn = _ask(sid)

    assert turn["error"] == LIMIT
    assert "fallback_reason" not in turn
    errors = [e for e in _events(sid, turn_id) if e["type"] == "error"]
    assert [e["error"] for e in errors] == [LIMIT]
    # The limit is still worth knowing about (Settings shows it), but with
    # no stand-in the next question goes to Claude regardless.
    assert warren_engine.claude_resting() == LIMIT


def test_both_engines_failing_names_both(tmp_consoles, monkeypatch, gemini_key):
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], ok=False, error=LIMIT))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini([], error="gemini HTTP 429 — quota"))
    sid = _warren_session()

    turn_id, turn = _ask(sid)

    assert turn["error"] == f"Claude: {LIMIT} · Gemini: gemini HTTP 429 — quota"
    errors = [e for e in _events(sid, turn_id) if e["type"] == "error"]
    assert len(errors) == 1


def test_gemini_setting_asks_gemini_first(tmp_consoles, monkeypatch, gemini_key):
    product_store.update_preferences(None, {"warren_engine": "gemini"})
    claude_calls, gemini_calls = [], []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    sid = _warren_session()

    _turn_id, turn = _ask(sid)

    assert claude_calls == []
    assert turn["engine"] == "gemini"
    assert "fallback_reason" not in turn


def test_gemini_setting_falls_back_to_claude(tmp_consoles, monkeypatch, gemini_key):
    product_store.update_preferences(None, {"warren_engine": "gemini"})
    claude_calls = []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini([], error="gemini timed out after 120s"))
    sid = _warren_session()

    _turn_id, turn = _ask(sid)

    assert turn["engine"] == "claude"
    assert turn["fallback_reason"] == "gemini timed out after 120s"
    assert claude_calls[0]["bootstrap_session"] is True


def test_gemini_setting_without_a_key_says_so(tmp_consoles, monkeypatch):
    product_store.update_preferences(None, {"warren_engine": "gemini"})
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([]))
    sid = _warren_session()

    _turn_id, turn = _ask(sid)

    assert turn["engine"] == "claude"
    assert turn["fallback_reason"] == "no Gemini API key configured"


def test_gemini_sees_the_conversation_but_not_failed_turns(tmp_consoles, monkeypatch, gemini_key):
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini([], error="gemini HTTP 503"))
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], text="AMD is up 4%."))
    sid = _warren_session()
    _ask(sid, "how is AMD doing")
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], ok=False, error="claude exited 1"))
    _ask(sid, "and NVDA")  # both engines fail: no answer to carry forward
    gemini_calls = []
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], ok=False, error=LIMIT))

    _ask(sid, "what about Intel")

    call = gemini_calls[-1]
    assert call["history"] == [("how is AMD doing", "AMD is up 4%.")]
    assert call["user_prompt"] == "what about Intel"


def test_claude_hears_what_gemini_said_while_it_was_out(tmp_consoles, monkeypatch, gemini_key):
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], ok=False, error=LIMIT))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini([], text="Chips rose on AI demand."))
    sid = _warren_session()
    _ask(sid, "why did chip stocks soar today")

    warren_engine.reset()  # the limit lifts
    claude_calls = []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude(claude_calls))
    _turn_id, turn = _ask(sid, "which of them do we cover")

    prompt = claude_calls[0]["user_prompt"]
    assert prompt.startswith("## Earlier in this chat")
    assert "Q: why did chip stocks soar today" in prompt
    assert "A: Chips rose on AI demand." in prompt
    assert prompt.endswith("which of them do we cover")
    assert claude_calls[0]["bootstrap_session"] is True
    assert turn["engine"] == "claude"
    assert warren_engine.claude_resting() is None


def test_the_company_console_stays_on_claude(tmp_consoles, monkeypatch, gemini_key):
    gemini_calls = []
    monkeypatch.setattr(claude_runner, "run_console_ask", _claude([], ok=False, error=LIMIT))
    monkeypatch.setattr(gemini_runner, "run_chat", _gemini(gemini_calls))
    sid = _warren_session(kind=None)

    _turn_id, turn = _ask(sid)

    assert gemini_calls == []
    assert turn["error"] == LIMIT
    assert "engine" not in turn


def test_warren_engine_setting_is_validated_and_desk_wide():
    with pytest.raises(ValueError):
        product_store.update_preferences(None, {"warren_engine": "gpt"})
    product_store.update_preferences("analyst@bshfoundation.org", {"warren_engine": "gemini"})
    assert product_store.warren_engine() == "gemini"
    assert warren_engine.chosen() == "gemini"


def test_settings_report_warrens_engines(gemini_key):
    from server.main import app

    client = TestClient(app)
    settings = client.get("/api/workspace/settings")
    assert settings.status_code == 200, settings.text
    warren = settings.json()["warren"]
    assert warren["engine"] == "claude"
    assert warren["gemini_available"] is True
    assert warren["gemini_model"] == "gemini-3.8-flash"

    patched = client.patch("/api/workspace/settings", json={"warren_engine": "gemini"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["warren"]["engine"] == "gemini"
    assert patched.json()["preferences"]["warren_engine"] == "gemini"

    rejected = client.patch("/api/workspace/settings", json={"warren_engine": "gpt"})
    assert rejected.status_code == 400
