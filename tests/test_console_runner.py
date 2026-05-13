"""Direct tests for claude_runner._consume_stream — §11.2 watchdog
scenarios. We swap out subprocess.Popen entirely with a FakeProc and
drive the events queue manually, so these tests run in <2s without
spawning Claude.
"""
from __future__ import annotations

import signal
import subprocess
import threading
import time

import pytest

from server import claude_runner, job_progress


# ---- Fakes --------------------------------------------------------------


class FakeProc:
    """Looks enough like subprocess.Popen for ``_consume_stream`` and
    ``_terminate_console`` to drive it.
    """

    def __init__(self, *, exit_code: int | None = None):
        self._returncode: int | None = exit_code
        self.signals_received: list[int] = []
        self.kill_called: bool = False
        # claude_runner's stderr drainer thread expects this attribute.
        self.stdout = None
        self.stderr = None

    def poll(self):
        return self._returncode

    @property
    def returncode(self):
        return self._returncode

    def send_signal(self, sig):
        self.signals_received.append(sig)
        if self._returncode is None:
            # Simulate a clean SIGINT exit.
            self._returncode = 130 if sig == signal.SIGINT else 1

    def kill(self):
        self.kill_called = True
        if self._returncode is None:
            self._returncode = -9

    def wait(self, timeout=None):
        """Mimic ``Popen.wait``: raise ``TimeoutExpired`` if the process is
        still running (returncode is None) and a timeout was given."""
        if self._returncode is None:
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
            self._returncode = 0
        return self._returncode


def _make_handle(events, *, exit_code=None, keep_reader_alive=False):
    """Build a _ConsoleRunHandle with pre-queued events.

    ``exit_code=None`` means the FakeProc is still "running" (poll() is
    None) — required for tests that exercise SIGINT delivery. Pass an
    integer to simulate a process that already exited.

    ``keep_reader_alive`` controls whether the queue gets a terminal
    ``None`` (False → consumer breaks on EOF) or no terminator (True →
    consumer keeps polling, letting the watchdog fire).
    """
    proc = FakeProc(exit_code=exit_code)
    handle = claude_runner._ConsoleRunHandle(proc)
    for ev in events:
        handle.events.put(ev)
    if keep_reader_alive:
        # Long-lived reader so empty-queue path doesn't short-circuit.
        handle.reader = threading.Thread(
            target=lambda: time.sleep(30), daemon=True
        )
    else:
        handle.events.put(None)  # EOF sentinel
        handle.reader = threading.Thread(target=lambda: None, daemon=True)
    handle.reader.start()
    return handle


def _new_progress(tmp_path):
    return job_progress.ProgressLog(tmp_path / "progress.jsonl")


# ---- Clean-success path -------------------------------------------------


def test_clean_result_event(tmp_path):
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "abc", "model": "claude"},
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": "Ready."}]}},
            {"type": "result", "subtype": "success",
             "total_cost_usd": 0.018, "duration_ms": 1200,
             "usage": {"input_tokens": 10, "output_tokens": 5,
                       "cache_read_input_tokens": 50,
                       "cache_creation_input_tokens": 0}},
        ],
        exit_code=0,
    )
    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=None,
        event_silence_timeout_s=10.0,
        wall_clock_cap_s=10.0,
        grace_kill_s=1.0,
    )
    assert out["ok"] is True
    assert out["subtype"] == "success"
    assert out["cost_usd"] == 0.018
    assert out["usage"]["input_tokens"] == 10
    assert state.get("assistant_text_parts") == ["Ready."]


# ---- Subprocess died with no result event -------------------------------


def test_subprocess_died_without_result(tmp_path):
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
        ],
        exit_code=1,
    )
    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=None,
        event_silence_timeout_s=10.0,
        wall_clock_cap_s=10.0,
        grace_kill_s=1.0,
    )
    assert out["ok"] is False
    assert "exited unexpectedly" in (out.get("error") or "")
    assert out["interrupt_reason"] == "subprocess_died"


# ---- Event-silence watchdog --------------------------------------------


def test_event_silence_watchdog_fires_sigint(tmp_path):
    """No events arrive after init → silence timer fires → SIGINT delivered."""
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
        ],
        keep_reader_alive=True,
    )
    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=None,
        event_silence_timeout_s=0.3,
        wall_clock_cap_s=5.0,
        grace_kill_s=0.5,
    )
    assert out["ok"] is False
    assert out["interrupt_reason"] == "event_silence_timeout"
    assert signal.SIGINT in handle.proc.signals_received


# ---- Wall-clock cap ----------------------------------------------------


def test_wall_clock_cap_fires_sigint(tmp_path):
    """Steady event flow but total elapsed > cap → wall-clock interrupt."""
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
        ],
        keep_reader_alive=True,
    )
    # Slowly emit additional events from a thread to keep the silence
    # watchdog at bay; wall-clock cap should still fire.
    def drip():
        for _ in range(10):
            time.sleep(0.05)
            handle.events.put({"type": "assistant", "message": {"content": []}})
    threading.Thread(target=drip, daemon=True).start()

    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=None,
        event_silence_timeout_s=5.0,
        wall_clock_cap_s=0.25,
        grace_kill_s=0.5,
    )
    assert out["ok"] is False
    assert out["interrupt_reason"] == "wall_clock_cap"


# ---- User-cancellation event -------------------------------------------


def test_user_cancel_event(tmp_path):
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
        ],
        keep_reader_alive=True,
    )
    cancel = threading.Event()
    cancel.set()  # Pre-set so the very first loop iteration sees it.

    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=cancel,
        event_silence_timeout_s=10.0,
        wall_clock_cap_s=10.0,
        grace_kill_s=0.5,
    )
    assert out["ok"] is False
    assert out["interrupt_reason"] == "user_cancelled"
    assert signal.SIGINT in handle.proc.signals_received


def test_cancel_after_some_progress(tmp_path):
    """Cancel arrives after init+thinking events have been processed."""
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": "thinking…"}]}},
        ],
        keep_reader_alive=True,
    )
    cancel = threading.Event()

    def cancel_after(delay):
        time.sleep(delay)
        cancel.set()

    threading.Thread(target=cancel_after, args=(0.2,), daemon=True).start()

    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=cancel,
        event_silence_timeout_s=10.0,
        wall_clock_cap_s=10.0,
        grace_kill_s=0.5,
    )
    assert out["ok"] is False
    assert out["interrupt_reason"] == "user_cancelled"
    assert "thinking" in (state.get("assistant_text_parts") or [""])[0]


# ---- Subprocess refuses SIGINT, requires SIGKILL -----------------------


def test_sigkill_fallback_when_sigint_ignored(tmp_path, monkeypatch):
    handle = _make_handle(
        [
            {"type": "system", "subtype": "init",
             "session_id": "x", "model": "claude"},
        ],
        keep_reader_alive=True,
    )

    # Patch send_signal so SIGINT is logged but the process does not exit.
    def stubborn_signal(sig):
        handle.proc.signals_received.append(sig)
        # Do NOT set returncode — pretend the subprocess ignores SIGINT.

    handle.proc.send_signal = stubborn_signal  # type: ignore[assignment]

    cancel = threading.Event()
    cancel.set()
    progress = _new_progress(tmp_path)
    state: dict = {}
    out = claude_runner._consume_stream(
        handle, progress=progress, state=state,
        cancel_event=cancel,
        event_silence_timeout_s=10.0,
        wall_clock_cap_s=10.0,
        grace_kill_s=0.1,  # short grace → escalates fast
    )
    assert out["ok"] is False
    assert handle.proc.kill_called is True
