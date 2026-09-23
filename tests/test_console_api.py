"""API-level tests for the Console routes via FastAPI TestClient.

Subprocess helpers in ``claude_runner`` are stubbed so these tests run
fast and never spawn Claude.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server import attachment_text, claude_runner, console_store
from server.main import app


COMPANY = "ami_labs"


@pytest.fixture
def stubbed_claude(monkeypatch):
    """Replace the three Console claude_runner helpers with stubs."""
    def fake_hydrate(**kwargs):
        progress = kwargs["progress"]
        progress.emit("done", text="Ready.",
                      usage={"input_tokens": 0, "output_tokens": 0,
                             "cache_read_input_tokens": 0,
                             "cache_creation_input_tokens": 0},
                      cost_usd=0.0)
        return {"ok": True, "subtype": "success", "text": "Ready.",
                "usage": {"input_tokens": 0, "output_tokens": 0,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
                "cost_usd": 0.0, "duration_ms": 1}

    def fake_ask(**kwargs):
        return {"ok": True, "subtype": "success", "text": "ok",
                "usage": {"input_tokens": 10, "output_tokens": 5,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
                "cost_usd": 0.001, "duration_ms": 1}

    def fake_summary(*, turns, progress, **kwargs):
        progress.emit("done", headline="Test session",
                      bullets=["Did a thing"])
        return {"headline": "Test session", "bullets": ["Did a thing"],
                "cost_usd": 0.0, "usage": {}}

    monkeypatch.setattr(claude_runner, "run_console_hydrate", fake_hydrate)
    monkeypatch.setattr(claude_runner, "run_console_ask", fake_ask)
    monkeypatch.setattr(claude_runner, "run_console_summary", fake_summary)


@pytest.fixture
def client():
    return TestClient(app)


def _create(client, company=COMPANY):
    resp = client.post(
        f"/api/companies/{company}/console/sessions",
        json={"include_background_docs": False,
              "include_library_docs": False},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_for_assistant(company, sid, turn_id, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for t in console_store.read_turns(company, sid):
            if t.get("id") == turn_id and t.get("role") == "assistant":
                return t
        time.sleep(0.05)
    raise AssertionError("assistant turn not written in time")


# ---- Happy path --------------------------------------------------------


def test_create_session(tmp_consoles, stubbed_claude, client):
    body = _create(client)
    assert body["status"] == "active"
    assert body["hydrate_stream_url"].endswith("/hydrate/stream")
    assert body["context_window"] == console_store.CONTEXT_WINDOW
    assert body["pct_used"] == 0.0


def test_list_sessions(tmp_consoles, stubbed_claude, client):
    a = _create(client)
    b = _create(client)
    resp = client.get(f"/api/companies/{COMPANY}/console/sessions")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert {a["id"], b["id"]}.issubset(ids)


def test_list_sessions_hides_copilot(tmp_consoles, stubbed_claude, client):
    user = _create(client)
    from server import attachment_text, console_session, console_store

    copilot = console_session.create_session(
        company_id=COMPANY,
        include_background_docs=False,
        include_library_docs=False,
        skip_hydrate=True,
        title="Co-Pilot Inspector",
        session_kind="copilot_quick",
    )
    resp = client.get(f"/api/companies/{COMPANY}/console/sessions")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert user["id"] in ids
    assert copilot["id"] not in ids
    # Still on disk for Co-Pilot itself.
    assert console_store.load_meta(COMPANY, copilot["id"]) is not None


def test_get_session(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    resp = client.get(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == meta["id"]
    assert "context_used" in body


def test_get_session_404(tmp_consoles, stubbed_claude, client):
    resp = client.get(
        f"/api/companies/{COMPANY}/console/sessions/" + ("0" * 32)
    )
    assert resp.status_code == 404


def test_post_ask_and_stream_url(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "hello"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queue_position"] == 0
    assert "/ask/stream/" in body["stream_url"]
    _wait_for_assistant(COMPANY, meta["id"], body["turn_id"])


def test_post_ask_requires_prompt(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "   "},
    )
    assert resp.status_code == 400


def test_post_ask_to_archived_returns_409(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/archive"
    )
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "after archive"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "session_archived"


def test_get_turns_returns_history(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    ask = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "hello"},
    ).json()
    _wait_for_assistant(COMPANY, meta["id"], ask["turn_id"])
    resp = client.get(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/turns"
    )
    assert resp.status_code == 200
    turns = resp.json()
    assert any(t["role"] == "user" and t["text"] == "hello" for t in turns)
    assert any(t["role"] == "assistant" for t in turns)


def test_archive_writes_summary(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "for the record"},
    )
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/archive"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    # Wait for the summary worker to land.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        m = console_store.load_meta(COMPANY, meta["id"])
        if m and m.get("summary"):
            assert m["summary"]["headline"] == "Test session"
            return
        time.sleep(0.05)
    pytest.fail("summary did not land")


def test_delete_session(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    resp = client.delete(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}"
    )
    assert resp.status_code == 204
    # Subsequent gets are 404.
    assert client.get(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}"
    ).status_code == 404


# ---- Resource limits ---------------------------------------------------


def test_session_limit_returns_409(tmp_consoles, stubbed_claude, client):
    for _ in range(console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY):
        _create(client)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions",
        json={"include_background_docs": False, "include_library_docs": False},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "session_limit_reached"
    assert resp.json()["detail"]["limit"] == (
        console_store.MAX_ACTIVE_SESSIONS_PER_COMPANY
    )


def test_attachment_too_large_400(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (console_store.MAX_ATTACHMENT_BYTES + 1)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "look"},
        files=[("images", ("big.png", huge, "image/png"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "attachment_too_large"


def test_attachment_wrong_type_400(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "look"},
        files=[("images", ("bad.png", b"MZ\x90\x00" + b"\x00" * 12, "image/png"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "attachment_type_not_allowed"


# ---- Warren's own attachments (POST /copilot/attachments) --------------


@pytest.fixture
def warren_company():
    """A company record, which the copilot routes check for (the console
    routes key off the session instead)."""
    from server import storage

    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    return "zainar-inc"


def test_warren_attachment_is_staged_for_the_next_question(
    tmp_consoles, stubbed_claude, client, warren_company, pdf_bytes
):
    resp = client.post(
        f"/api/companies/{warren_company}/copilot/attachments",
        files=[("file", ("term-sheet.pdf", pdf_bytes, "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert record["name"] == "term-sheet.pdf"
    assert record["stored_name"].endswith(".pdf")

    # The ask carries it, and it reaches the turn Warren answers.
    ask = client.post(
        f"/api/companies/{warren_company}/copilot/ask",
        json={
            "prompt": "What is unusual in this term sheet?",
            "attachments": [record["stored_name"]],
            "attachment_names": {record["stored_name"]: record["name"]},
        },
    )
    assert ask.status_code == 200, ask.text
    sid = ask.json()["session_id"]
    assert sid == record["session_id"]
    user_turn = next(
        t
        for t in console_store.read_turns(warren_company, sid)
        if t["role"] == "user" and t["id"] == ask.json()["turn_id"]
    )
    assert [a["name"] for a in user_turn["attachments"]] == ["term-sheet.pdf"]


def test_warren_edit_replaces_the_question_for_everyone(
    tmp_consoles, stubbed_claude, client, warren_company
):
    """An edited question is re-asked and the old pair leaves the thread,
    which is the copy the rest of the team loads."""
    first = client.post(
        f"/api/companies/{warren_company}/copilot/ask",
        json={"prompt": "whats the mote"},
    )
    assert first.status_code == 200, first.text
    sid = first.json()["session_id"]

    second = client.post(
        f"/api/companies/{warren_company}/copilot/ask",
        json={"prompt": "what is the moat?", "edits": first.json()["turn_id"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == sid

    thread = console_store.read_turns(warren_company, sid)
    assert [t["text"] for t in thread if t["role"] == "user"] == [
        "what is the moat?"
    ]


def test_warren_threads_are_the_companys_not_the_browsers(
    tmp_consoles, stubbed_claude, client, warren_company
):
    """Starting a new thread files the old one in the history everyone
    reads, instead of hiding it for one browser."""
    first = client.post(
        f"/api/companies/{warren_company}/copilot/ask",
        json={"prompt": "how do they make money?"},
    )
    assert first.status_code == 200, first.text
    old_sid = first.json()["session_id"]

    started = client.post(f"/api/companies/{warren_company}/copilot/threads", json={})
    assert started.status_code == 201, started.text
    new_sid = started.json()["session_id"]
    assert new_sid != old_sid
    assert started.json()["previous_session_id"] == old_sid

    threads = client.get(f"/api/companies/{warren_company}/copilot/threads").json()
    by_id = {t["id"]: t for t in threads}
    assert by_id[new_sid]["active"] is True
    assert by_id[old_sid]["active"] is False
    assert by_id[old_sid]["opening_question"] == "how do they make money?"
    assert by_id[old_sid]["question_count"] == 1

    # And the old thread still reads back in full.
    turns = client.get(
        f"/api/companies/{warren_company}/console/sessions/{old_sid}/turns"
    ).json()
    assert [t["text"] for t in turns if t["role"] == "user"] == [
        "how do they make money?"
    ]


def test_an_empty_thread_is_not_history(
    tmp_consoles, stubbed_claude, client, warren_company
):
    client.post(f"/api/companies/{warren_company}/copilot/ask", json={"prompt": "hi"})
    client.post(f"/api/companies/{warren_company}/copilot/threads", json={})
    # The fresh thread has no questions yet, so only it and the one with
    # the question are listed — not a trail of empty ones.
    client.post(f"/api/companies/{warren_company}/copilot/threads", json={})

    threads = client.get(f"/api/companies/{warren_company}/copilot/threads").json()
    assert sum(1 for t in threads if not t["question_count"] and not t["active"]) == 0


def test_warren_attachment_too_large_400(
    tmp_consoles, stubbed_claude, client, warren_company
):
    huge = b"%PDF-1.4\n" + b"\x00" * (console_store.MAX_ATTACHMENT_BYTES + 1)
    resp = client.post(
        f"/api/companies/{warren_company}/copilot/attachments",
        files=[("file", ("big.pdf", huge, "application/pdf"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "attachment_too_large"


def test_warren_attachment_wrong_type_400(
    tmp_consoles, stubbed_claude, client, warren_company
):
    resp = client.post(
        f"/api/companies/{warren_company}/copilot/attachments",
        files=[("file", ("models.zip", b"PK\x03\x04nope", "application/zip"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "attachment_type_not_allowed"


def test_warren_attachment_unreadable_400(
    tmp_consoles, stubbed_claude, client, warren_company
):
    """An allowed extension whose bytes hold no text is refused here,
    rather than answered with an apology two minutes later."""
    resp = client.post(
        f"/api/companies/{warren_company}/copilot/attachments",
        files=[("file", ("sheet.xlsx", b"PK\x03\x04nope", "application/vnd.ms-excel"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "attachment_unreadable"


def test_warren_reads_a_word_file(
    tmp_consoles, stubbed_claude, client, warren_company, real_docx_bytes
):
    """The .docx that used to come back as "I wasn't able to open that"."""
    resp = client.post(
        f"/api/companies/{warren_company}/copilot/attachments",
        files=[(
            "file",
            ("term-sheet.docx", real_docx_bytes, "application/octet-stream"),
        )],
    )
    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert record["text_chars"] > 0
    _, text = attachment_text.read_text(
        console_store.workdir_attachments(warren_company, record["session_id"]),
        record["stored_name"],
    )
    assert "Pre-money valuation of $42M." in text


def test_attachment_round_trip(tmp_consoles, stubbed_claude, client, png_bytes):
    meta = _create(client)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/ask",
        data={"prompt": "look at this"},
        files=[("images", ("chart.png", png_bytes, "image/png"))],
    )
    assert resp.status_code == 200
    info = resp.json()
    _wait_for_assistant(COMPANY, meta["id"], info["turn_id"])
    turns = console_store.read_turns(COMPANY, meta["id"])
    user_turn = next(t for t in turns if t["role"] == "user"
                     and t["id"] == info["turn_id"])
    assert user_turn["attachments"]
    img_id = user_turn["attachments"][0]["id"]
    # Attachment endpoint serves the bytes back.
    resp = client.get(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}/attachments/{img_id}"
    )
    assert resp.status_code == 200
    assert resp.content == png_bytes


# ---- Cancel ------------------------------------------------------------


def test_cancel_returns_404_when_no_turn(tmp_consoles, stubbed_claude, client):
    meta = _create(client)
    fake_turn = "f" * 32
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{meta['id']}"
        f"/ask/{fake_turn}/cancel"
    )
    assert resp.status_code == 404


# ---- Estimate endpoint -------------------------------------------------


def test_estimate_zero_for_empty_company(tmp_consoles, stubbed_claude, client):
    resp = client.get(
        f"/api/companies/{COMPANY}/console/estimate"
        "?include_background_docs=true&include_library_docs=true"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"] == []
    assert body["tokens_est"] == 0
    assert body["cost_usd_est"] == 0
    assert body["duration_est_s"] >= 5  # floor


def test_estimate_picks_up_research_files(tmp_consoles, stubbed_claude, client):
    # Drop a fake research file directly onto disk so the estimate sees it.
    from server import research_store
    cdir = research_store._company_dir(COMPANY)
    cdir.mkdir(parents=True, exist_ok=True)
    payload = b"# Notes\n\n" + b"x" * 4000
    fid = "abc123def456"
    (cdir / f"{fid}__notes.md").write_bytes(payload)
    (cdir / "index.yaml").write_text(
        '- {"id": "abc123def456", "filename": "notes.md", '
        f'"stored_name": "{fid}__notes.md", "kind": "text", '
        f'"size_bytes": {len(payload)}, "uploaded_at": "2026-01-01T00:00:00Z"}}\n',
        encoding="utf-8",
    )
    resp = client.get(
        f"/api/companies/{COMPANY}/console/estimate"
        "?include_background_docs=true&include_library_docs=false"
    )
    body = resp.json()
    assert len(body["files"]) == 1
    assert body["files"][0]["filename"] == "notes.md"
    # ~0.25 tokens/byte: 4007 bytes → ~1000 tokens, ~$0.003.
    assert body["tokens_est"] > 0
    assert body["cost_usd_est"] >= 0


# ---- AI rail (/api/jobs/active) ----------------------------------------


def test_console_jobs_appear_in_active_jobs(
    tmp_consoles, stubbed_claude, client,
):
    """After creating a session, the hydrate progress file is on disk and
    /api/jobs/active should surface it until it terminates."""
    meta = _create(client)
    # The hydrate worker fires `done` quickly with the stub, so wait a
    # tiny moment and then check whether a Console entry shows up
    # either as in-flight or terminated — the aggregator filters
    # terminated entries out in /jobs/active, so we look at /jobs/log
    # directly to confirm a Console job log exists.
    log_resp = client.get(
        f"/api/jobs/log?path=console_hydrate:{COMPANY}/{meta['id']}"
    )
    assert log_resp.status_code == 200
    events = log_resp.json()
    assert any(ev.get("type") == "job_init" for ev in events)
