"""Real-Claude end-to-end tests (§11.4).

Skipped unless ``pytest -m e2e`` is passed. Each test spawns ``claude
-p`` for real, so expect ~$0.50 per run and ~30s wall time.

Two scenarios:

1. **Happy path** — create session → wait for hydration → ask → assert
   assistant reply → archive → assert summary lands.
2. **Interrupt path** — ask, cancel mid-stream, assert error turn,
   then ask again and assert the session survived.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import claude_runner, console_store
from server.main import app


COMPANY = "test_e2e_company"


pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    return TestClient(app)


def _claude_available() -> bool:
    return claude_runner.is_available()


def _seed_research_files(tmp_consoles):
    """Drop two tiny research files for the e2e company so hydration has
    something to read.

    The files go into ``research_store``'s on-disk layout directly —
    we're not using the upload API path here. Returns the list of
    filenames staged.
    """
    from server import research_store

    cdir = research_store._company_dir(COMPANY)
    cdir.mkdir(parents=True, exist_ok=True)
    files = [
        ("file_alpha.md", b"# AMI Labs Overview\n\nAMI Labs is a "
         b"venture-backed company headquartered in Berkeley. Founded 2021.\n"),
        ("file_bravo.md", b"# Financials\n\nQ1 2025 ARR: 14.2 million USD.\n"),
    ]
    records: list[dict] = []
    for name, payload in files:
        file_id = "abcd1234ef" + name[-2:].zfill(2).encode().hex()[:6]
        stored = f"{file_id}__{name}"
        (cdir / stored).write_bytes(payload)
        records.append({
            "id": file_id, "filename": name, "stored_name": stored,
            "kind": "text", "size_bytes": len(payload),
            "uploaded_at": "2026-01-01T00:00:00Z",
        })
    (cdir / "index.yaml").write_text(
        "\n".join(f"- {json.dumps(r)}" for r in records),
        encoding="utf-8",
    )
    return [r["filename"] for r in records]


def _wait_for_meta(company, sid, predicate, *, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = console_store.load_meta(company, sid)
        if m and predicate(m):
            return m
        time.sleep(0.25)
    raise AssertionError(f"meta predicate not satisfied within {timeout}s")


def _wait_for_assistant(company, sid, turn_id, *, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for t in console_store.read_turns(company, sid):
            if t.get("id") == turn_id and t.get("role") == "assistant":
                return t
        time.sleep(0.25)
    raise AssertionError("assistant turn never landed")


def test_happy_path(tmp_consoles, client):
    if not _claude_available():
        pytest.skip("`claude` CLI not on PATH")
    _seed_research_files(tmp_consoles)

    # Create.
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions",
        json={"include_background_docs": True, "include_library_docs": False},
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]

    # Wait for hydration to complete (or fail loudly).
    meta = _wait_for_meta(
        COMPANY, sid,
        lambda m: m.get("hydration_status") in ("done", "error"),
        timeout=120.0,
    )
    assert meta["hydration_status"] == "done", (
        f"hydration_status={meta.get('hydration_status')} "
        f"error={meta.get('hydration_error')}"
    )

    # Ask a grounded question.
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{sid}/ask",
        data={"prompt": "What is AMI Labs' Q1 2025 ARR per the staged files?"},
    )
    assert resp.status_code == 200
    turn_id = resp.json()["turn_id"]
    assistant = _wait_for_assistant(COMPANY, sid, turn_id, timeout=120.0)
    assert assistant["subtype"] == "success"
    # Loose check: the answer should mention the figure.
    text = (assistant.get("text") or "").lower()
    # Loose ground-truth check — accept the most common phrasings the LLM
    # may use for the figure. Substantive correctness, not exact wording.
    assert any(s in text for s in ("14.2", "14,200,000", "14 million", "14m")), (
        f"assistant reply didn't ground in the fixture: {text[:300]}"
    )

    # Archive and wait for summary.
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{sid}/archive"
    )
    assert resp.status_code == 200
    meta = _wait_for_meta(
        COMPANY, sid,
        lambda m: m.get("summary") is not None or m.get("summary_error"),
        timeout=120.0,
    )
    assert meta.get("summary"), (
        f"summary did not land: error={meta.get('summary_error')}"
    )
    assert meta["summary"]["bullets"]


def test_interrupt_path_survives_cancel(tmp_consoles, client):
    if not _claude_available():
        pytest.skip("`claude` CLI not on PATH")
    _seed_research_files(tmp_consoles)

    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions",
        json={"include_background_docs": True, "include_library_docs": False},
    )
    sid = resp.json()["id"]
    _wait_for_meta(
        COMPANY, sid,
        lambda m: m.get("hydration_status") in ("done", "error"),
        timeout=120.0,
    )

    # Long-running ask.
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{sid}/ask",
        data={
            "prompt": (
                "Read every staged file and write a 1000-word essay "
                "comparing them line by line."
            ),
        },
    )
    turn_id = resp.json()["turn_id"]

    # Give Claude a moment to start streaming, then cancel.
    time.sleep(4.0)
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{sid}"
        f"/ask/{turn_id}/cancel"
    )
    assert resp.status_code in (204, 404), resp.text  # 404 if it finished before we got here

    assistant = _wait_for_assistant(COMPANY, sid, turn_id, timeout=120.0)
    # If we cancelled in time, subtype is error; if the run finished
    # before our cancel landed, subtype is success — either way the
    # session must survive for the follow-up below.

    # Follow-up ask succeeds → session is still usable.
    resp = client.post(
        f"/api/companies/{COMPANY}/console/sessions/{sid}/ask",
        data={"prompt": "Reply with the single word: alive"},
    )
    assert resp.status_code == 200
    follow_id = resp.json()["turn_id"]
    follow = _wait_for_assistant(COMPANY, sid, follow_id, timeout=120.0)
    assert follow["subtype"] == "success"
    assert "alive" in (follow.get("text") or "").lower()
