"""Tests for the memo run-slot registry and run cancellation.

User-started runs share the Settings cap and queue FIFO; tracking
auto-runs live in a small reserved lane. Cancel kills subprocesses by
spawn cwd, blocks respawns via the run-dir marker, and writes the
terminal failed state.
"""
from __future__ import annotations

import threading
import time

import pytest

from server import claude_runner, memo_analysis, product_store, storage


@pytest.fixture(autouse=True)
def _clean_registry():
    with memo_analysis._SLOT_COND:
        memo_analysis._SLOT_ACTIVE.clear()
        memo_analysis._SLOT_WAITERS.clear()
        memo_analysis._SLOT_CANCELLED.clear()
    yield
    with memo_analysis._SLOT_COND:
        memo_analysis._SLOT_ACTIVE.clear()
        memo_analysis._SLOT_WAITERS.clear()
        memo_analysis._SLOT_CANCELLED.clear()


def _acquire_in_thread(report_id: str, *, reserved: bool = False):
    result: dict = {}

    def _target():
        result["granted"] = memo_analysis.acquire_run_slot(
            report_id, reserved=reserved
        )

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return t, result


def _wait_for_waiter(report_id: str, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with memo_analysis._SLOT_COND:
            if any(rid == report_id for _t, rid, _r in memo_analysis._SLOT_WAITERS):
                return
        time.sleep(0.02)
    raise AssertionError(f"{report_id} never queued")


def test_user_slots_cap_and_release(monkeypatch):
    monkeypatch.setattr(product_store, "memo_parallel_runs", lambda: 1)
    assert memo_analysis.acquire_run_slot("r1", reserved=False) is True

    t, result = _acquire_in_thread("r2")
    _wait_for_waiter("r2")
    t.join(0.3)
    assert t.is_alive(), "second run should be queued at cap 1"

    memo_analysis.release_run_slot("r1")
    t.join(5.0)
    assert result["granted"] is True
    memo_analysis.release_run_slot("r2")


def test_reserved_lane_is_independent(monkeypatch):
    monkeypatch.setattr(product_store, "memo_parallel_runs", lambda: 1)
    assert memo_analysis.acquire_run_slot("user1", reserved=False) is True
    # Tracking runs are not blocked by a saturated user lane.
    assert memo_analysis.acquire_run_slot("track1", reserved=True) is True
    assert memo_analysis.acquire_run_slot("track2", reserved=True) is True

    t, result = _acquire_in_thread("track3", reserved=True)
    _wait_for_waiter("track3")
    t.join(0.3)
    assert t.is_alive(), "reserved lane holds 2"

    memo_analysis.release_run_slot("track1")
    t.join(5.0)
    assert result["granted"] is True
    for rid in ("user1", "track2", "track3"):
        memo_analysis.release_run_slot(rid)


def test_cancel_aborts_queued_run(monkeypatch):
    monkeypatch.setattr(product_store, "memo_parallel_runs", lambda: 1)
    assert memo_analysis.acquire_run_slot("r1", reserved=False) is True
    t, result = _acquire_in_thread("r2")
    _wait_for_waiter("r2")

    memo_analysis.cancel_queued_run_slot("r2")
    t.join(5.0)
    assert result["granted"] is False
    memo_analysis.release_run_slot("r1")


def test_reserved_slots_available(monkeypatch):
    assert memo_analysis.reserved_run_slots_available() is True
    assert memo_analysis.acquire_run_slot("t1", reserved=True) is True
    assert memo_analysis.acquire_run_slot("t2", reserved=True) is True
    assert memo_analysis.reserved_run_slots_available() is False
    memo_analysis.release_run_slot("t1")
    assert memo_analysis.reserved_run_slots_available() is True
    memo_analysis.release_run_slot("t2")


def test_queued_report_status_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    report = storage.create_report(
        company_id="zainar-inc",
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(report["id"], status="ready_for_analysis")
    monkeypatch.setattr(product_store, "memo_parallel_runs", lambda: 1)
    assert memo_analysis.acquire_run_slot("holder", reserved=False) is True

    t, result = _acquire_in_thread(report["id"])
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if storage.get_report(report["id"])["status"] == "queued":
            break
        time.sleep(0.05)
    assert storage.get_report(report["id"])["status"] == "queued"

    memo_analysis.release_run_slot("holder")
    t.join(5.0)
    assert result["granted"] is True
    updated = storage.get_report(report["id"])
    assert updated["status"] == "analyzing"
    assert updated["stage"] == "Run slot acquired"
    memo_analysis.release_run_slot(report["id"])


def test_cancel_run_marks_report_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_DATA_DIR", str(tmp_path / "data"))
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    report = storage.create_report(
        company_id="zainar-inc",
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(report["id"], status="analyzing")

    memo_analysis.cancel_run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == "cancelled"
    assert updated["error"] == "Cancelled by user"

    with pytest.raises(ValueError):
        memo_analysis.cancel_run("nope")


def test_run_dir_marker_blocks_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    run_dir = tmp_path / "memo-run"
    claude_runner.mark_run_dir_cancelled(str(run_dir))
    try:
        result, error = claude_runner._run_memo_local_json_artifact(
            run_dir=run_dir,
            prompt="p",
            schema={"type": "object"},
            progress=None,
            progress_message="test",
            timeout_label="test",
            timeout_sec=5,
        )
        assert result is None
        assert error == claude_runner.MEMO_RUN_CANCELLED_ERROR
        # The cancelled marker must never read as a transient error, or
        # the attempt loop would retry and respawn.
        assert claude_runner.is_transient_claude_error(error) is False
    finally:
        claude_runner.clear_run_dir_cancelled(str(run_dir))


def test_terminate_claude_procs_under_matches_cwd(monkeypatch):
    killed: list[str] = []

    class _FakeProc:
        def __init__(self, cwd):
            self._bsh_spawn_cwd = cwd

        def poll(self):
            return None

    a = _FakeProc("/runs/a")
    b = _FakeProc("/runs/b")
    with claude_runner._LIVE_CLAUDE_PROCS_LOCK:
        claude_runner._LIVE_CLAUDE_PROCS.add(a)
        claude_runner._LIVE_CLAUDE_PROCS.add(b)
    monkeypatch.setattr(
        claude_runner,
        "_terminate_process_group",
        lambda proc, *, grace_s=2.0: killed.append(proc._bsh_spawn_cwd),
    )
    try:
        assert claude_runner.terminate_claude_procs_under("/runs/a") == 1
        assert killed == ["/runs/a"]
    finally:
        with claude_runner._LIVE_CLAUDE_PROCS_LOCK:
            claude_runner._LIVE_CLAUDE_PROCS.discard(a)
            claude_runner._LIVE_CLAUDE_PROCS.discard(b)
