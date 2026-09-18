"""Round 2 of the report restructure: the 12-pass Phase 2 and the
per-run subprocess ceiling (owner cap: 10 concurrent Claude processes)."""
from __future__ import annotations

import threading
import time

from server import claude_runner, memo_analysis


def test_phase2_has_eight_passes():
    """Eight, not twelve: passes reading the same evidence were merged so
    Phase 3 gets fewer, better-prioritised findings. Eight also fits under
    the ten-subprocess cap, so nothing queues behind the pin-feeding set."""
    ids = [spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES]
    assert len(ids) == 8
    assert len(set(ids)) == 8
    assert len(ids) <= claude_runner._memo_run_max_procs()
    for new_pass in (
        "market_sizing",
        "team_governance",
        "valuation_exit",
        "numbers_integrity",
    ):
        assert new_pass in ids
    # The adversarial pass stays on its own: it argues against what the
    # others conclude.
    assert "alternative_explanations" in ids
    # every artifact filename is unique and registered in the rail's
    # thread map so job history rows get labels
    filenames = [spec.artifact_filename for spec in memo_analysis._FAST_MEMO_PASSES]
    assert len(set(filenames)) == 8
    for filename in filenames:
        assert filename in claude_runner._MEMO_ANALYSIS_PASSES, filename


def test_pin_feeding_passes_are_real_passes():
    ids = {spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES}
    assert claude_runner.MEMO_SPINE_PIN_FEEDING_PASSES <= ids
    assert "valuation_exit" in claude_runner.MEMO_SPINE_PIN_FEEDING_PASSES
    assert "numbers_integrity" in claude_runner.MEMO_SPINE_PIN_FEEDING_PASSES


def test_run_max_procs_clamp(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_RUN_MAX_PROCS", raising=False)
    assert claude_runner._memo_run_max_procs() == 10
    monkeypatch.setenv("BSH_MEMO_RUN_MAX_PROCS", "4")
    assert claude_runner._memo_run_max_procs() == 4
    # the owner cap can be lowered, never raised
    monkeypatch.setenv("BSH_MEMO_RUN_MAX_PROCS", "50")
    assert claude_runner._memo_run_max_procs() == 10
    monkeypatch.setenv("BSH_MEMO_RUN_MAX_PROCS", "junk")
    assert claude_runner._memo_run_max_procs() == 10


def test_limiter_is_per_run_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_runner, "_MEMO_RUN_LIMITERS", {})
    a = claude_runner._memo_run_limiter(tmp_path / "run-a")
    b = claude_runner._memo_run_limiter(tmp_path / "run-b")
    assert a is not b
    assert claude_runner._memo_run_limiter(tmp_path / "run-a") is a


def test_limiter_caps_concurrent_subprocess_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_RUN_MAX_PROCS", "2")
    monkeypatch.setattr(claude_runner, "_MEMO_RUN_LIMITERS", {})
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "run_dir_cancelled", lambda _rd: False)

    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def fake_inner(**kwargs):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return {"ok": True}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact_inner", fake_inner
    )

    def call():
        claude_runner._run_memo_local_json_artifact(
            prompt="p",
            schema={},
            run_dir=tmp_path,
            progress=None,
            progress_message="m",
            timeout_label="t",
            timeout_sec=10,
        )

    threads = [threading.Thread(target=call) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert state["peak"] <= 2
    assert state["active"] == 0
    # every permit was returned
    limiter = claude_runner._memo_run_limiter(tmp_path)
    acquired = [limiter.acquire(timeout=1) for _ in range(2)]
    assert all(acquired)
    for _ in range(2):
        limiter.release()


def test_limiter_respects_cancellation_while_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_RUN_MAX_PROCS", "1")
    monkeypatch.setattr(claude_runner, "_MEMO_RUN_LIMITERS", {})
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)

    cancelled = {"value": False}
    monkeypatch.setattr(
        claude_runner, "run_dir_cancelled", lambda _rd: cancelled["value"]
    )
    # hold the only permit so the call queues
    limiter = claude_runner._memo_run_limiter(tmp_path)
    assert limiter.acquire(timeout=1)
    try:
        cancelled["value"] = True

        def never_called(**kwargs):  # pragma: no cover
            raise AssertionError("inner must not run after cancellation")

        monkeypatch.setattr(
            claude_runner,
            "_run_memo_local_json_artifact_inner",
            never_called,
        )
        result, error = claude_runner._run_memo_local_json_artifact(
            prompt="p",
            schema={},
            run_dir=tmp_path,
            progress=None,
            progress_message="m",
            timeout_label="t",
            timeout_sec=10,
        )
        assert result is None
        assert error == claude_runner.MEMO_RUN_CANCELLED_ERROR
    finally:
        limiter.release()
