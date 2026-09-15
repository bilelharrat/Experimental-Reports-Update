"""Round-3 job sweep (memo runs): a cancel survives the worker unwinding after it,
server shutdown refuses new Claude spawns and records in-flight runs as
interrupted before reaping, cancel reaps processes an earlier server left
behind (pid file), and a provider usage limit is named in the failure and
stops further spawns within the run. No real CLI is ever started."""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from server import claude_runner, job_history, memo_analysis, memo_prep, storage
from server import main as server_main

LIMIT = "claude exited 1: You've hit your weekly limit · resets Sep 18 at 3pm (America/New_York)"


@pytest.fixture
def memo_env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    return data_root


@pytest.fixture(autouse=True)
def _clean_run_state():
    with memo_analysis._SLOT_COND:
        memo_analysis._SLOT_ACTIVE.clear()
        memo_analysis._SLOT_WAITERS.clear()
        memo_analysis._SLOT_CANCELLED.clear()
    yield
    claude_runner._SHUTTING_DOWN.clear()
    with memo_analysis._HALTED_RUNS_LOCK:
        memo_analysis._HALTED_RUNS.clear()
    with memo_analysis._SLOT_COND:
        memo_analysis._SLOT_ACTIVE.clear()
        memo_analysis._SLOT_WAITERS.clear()
        memo_analysis._SLOT_CANCELLED.clear()


def _memo_report(data_root):
    run_id = "2026-09-14__120000"
    run_dir = data_root / "memos" / "acme-ai" / f"{run_id}__acme-ai__memo-run"
    (run_dir / "logs").mkdir(parents=True)
    report = storage.create_report_record(
        company_id="acme-ai",
        company_name="Acme AI",
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status="analyzing",
        progress=20,
        stage="Running parallel analysis passes",
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
    )
    return report, run_dir


def _events(run_dir):
    path = memo_prep.stream_path(run_dir)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _history_rows():
    path = job_history._history_file()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _phase2(report_id, run_dir, stream, data_root):
    return memo_analysis._run_fast_phase2(
        report_id=report_id,
        run_dir=run_dir,
        stream=stream,
        company_name="Acme AI",
        company_slug="acme-ai",
        run_id="2026-09-14__120000",
        research_dir=data_root / "research" / "acme-ai",
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )


# ---- F1: cancel is terminal ------------------------------------------------------------------


def test_cancel_is_not_overwritten_by_the_worker_unwinding_after_it(memo_env, monkeypatch):
    report, run_dir = _memo_report(memo_env)
    rid = report["id"]
    entered = threading.Event()
    release = threading.Event()

    def hung_pass(**_kw):
        entered.set()
        release.wait(10)
        return None, claude_runner.MEMO_RUN_CANCELLED_ERROR

    def reap(_run_dir):
        release.set()
        return 10

    finalized: list[str | None] = []
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", hung_pass)
    monkeypatch.setattr(claude_runner, "terminate_claude_procs_under", reap)
    monkeypatch.setattr(
        memo_analysis,
        "_complete_tracking_auto_run",
        lambda _report, *, success, error=None: finalized.append(error),
    )

    def worker():
        stream = memo_analysis._RunStream(rid, memo_prep.stream_path(run_dir), truncate=False)
        stream.emit("job_init", kind="memo", title="Investment memo — Acme AI")
        pass_results, _cost, _ms = _phase2(rid, run_dir, stream, memo_env)
        assert pass_results is None
        # What _run does next with the pipeline's failure.
        message = memo_analysis._recorded_fast_phase2_failure(rid)
        memo_analysis._update_report(
            rid,
            status="failed_during_analysis",
            stage="Claude skill run failed",
            error=message,
            failure_phase="analysis",
            failure_detail=message,
        )
        stream.emit("error", error=message, phase="analysis")
        memo_analysis._sync_tracking_auto_run(report, success=False, error=message)

    thread = threading.Thread(target=memo_analysis._with_run_slot, args=(rid, worker))
    thread.start()
    assert entered.wait(5)
    memo_analysis.cancel_run(rid)
    thread.join(30)
    assert not thread.is_alive()

    after = storage.get_report(rid)
    assert after["failure_phase"] == "cancelled"
    assert after["error"] == after["failure_detail"] == "Cancelled by user"
    assert after["stage"] == "Cancelled"
    errors = [e for e in _events(run_dir) if e["type"] == "error"]
    assert [e.get("phase") for e in errors] == ["cancelled"]
    assert finalized == ["Cancelled by user"]
    assert [row["error"] for row in _history_rows()] == ["Cancelled by user"]


def test_restarting_a_cancelled_report_writes_again(memo_env, monkeypatch):
    report, _run_dir = _memo_report(memo_env)
    rid = report["id"]
    monkeypatch.setattr(claude_runner, "terminate_claude_procs_under", lambda _run_dir: 0)
    memo_analysis.cancel_run(rid)
    memo_analysis._update_report(rid, stage="late worker write")
    assert storage.get_report(rid)["stage"] == "Cancelled"

    memo_analysis._with_run_slot(rid, lambda: memo_analysis._update_report(rid, stage="Resuming"))

    assert storage.get_report(rid)["stage"] == "Resuming"


# ---- F2: shutdown ----------------------------------------------------------------------------


def test_shutdown_records_interrupted_runs_before_reaping_and_refuses_spawns(memo_env, monkeypatch):
    report, run_dir = _memo_report(memo_env)
    rid = report["id"]
    seen: dict = {}

    def reap_all():
        seen["phase_at_reap"] = storage.get_report(rid)["failure_phase"]
        seen["shutting_down_at_reap"] = claude_runner.shutting_down()
        return 0

    monkeypatch.setattr(server_main.claude_runner, "terminate_live_claude_procs", reap_all)
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        claude_runner.subprocess, "Popen", lambda *a, **k: pytest.fail("no claude spawn after shutdown began")
    )
    memo_analysis._register_active_run(rid)
    try:
        server_main._shutdown()
    finally:
        memo_analysis._unregister_active_run(rid)
        server_main._TRANSLATION_STOP.clear()

    assert seen == {"phase_at_reap": "shutdown", "shutting_down_at_reap": True}
    # The worker unwinding after the reap cannot replace the resumable state.
    memo_analysis._update_report(rid, failure_phase="fast_parallel_analysis", error="All fast memo analysis passes failed.")
    memo_analysis._RunStream(rid, memo_prep.stream_path(run_dir), truncate=False).emit(
        "error", error="All fast memo analysis passes failed.", phase="fast_parallel_analysis"
    )
    after = storage.get_report(rid)
    assert after["failure_phase"] == "shutdown"
    assert after["error"] == "interrupted by server shutdown"
    assert [e.get("phase") for e in _events(run_dir) if e["type"] == "error"] == ["shutdown"]

    with pytest.raises(claude_runner.ClaudeShutdownError):
        claude_runner._popen_claude(["claude", "-p", "x"], cwd=str(run_dir))
    data, error = claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="pass",
        timeout_label="pass",
        timeout_sec=5,
    )
    assert (data, error) == (None, claude_runner.SERVER_SHUTTING_DOWN_ERROR)
    assert memo_analysis.acquire_run_slot("queued-report", reserved=False) is False


def test_spawn_racing_the_shutdown_flag_is_terminated(monkeypatch, tmp_path):
    terminated: list[int] = []

    class Proc:
        pid = 4242

        def poll(self):
            return None

    def popen(*_a, **_k):
        claude_runner.begin_shutdown()
        return Proc()

    monkeypatch.setattr(claude_runner.subprocess, "Popen", popen)
    monkeypatch.setattr(
        claude_runner, "_terminate_process_group", lambda proc, *, grace_s=2.0: terminated.append(proc.pid)
    )
    with pytest.raises(claude_runner.ClaudeShutdownError):
        claude_runner._popen_claude(["claude"], cwd=str(tmp_path))
    assert terminated == [4242]


def test_memo_spawns_record_their_pid_next_to_the_stream(monkeypatch, tmp_path):
    class Proc:
        def __init__(self):
            self.pid = 51234

        def poll(self):
            return 0

    monkeypatch.setattr(claude_runner.subprocess, "Popen", lambda *a, **k: Proc())
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "stream.jsonl").write_text("", encoding="utf-8")
    other = tmp_path / "work"
    other.mkdir()

    claude_runner._popen_claude(["claude"], cwd=str(run_dir))
    claude_runner._popen_claude(["claude"], cwd=str(other))

    rows = [json.loads(line) for line in (run_dir / "logs" / "claude_pids.jsonl").read_text().splitlines()]
    assert [row["pid"] for row in rows] == [51234]
    assert not list(other.rglob("claude_pids.jsonl"))


def _fake_claude(tmp_path):
    script = tmp_path / "bin" / "claude"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    script.chmod(0o755)
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "stream.jsonl").write_text("", encoding="utf-8")
    proc = subprocess.Popen([str(script)], cwd=str(run_dir), start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc, run_dir


def test_cancel_reaps_claude_processes_an_earlier_server_left_behind(tmp_path):
    proc, run_dir = _fake_claude(tmp_path)
    try:
        claude_runner._record_run_pid(str(run_dir), proc.pid)
        assert claude_runner.terminate_claude_procs_under(str(run_dir)) == 1
        deadline = time.monotonic() + 10
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_recorded_pid_with_a_different_start_time_is_left_alone(tmp_path):
    proc, run_dir = _fake_claude(tmp_path)
    try:
        with (run_dir / "logs" / "claude_pids.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": proc.pid, "started_at": time.time() - 3600}) + "\n")
        assert claude_runner.terminate_claude_procs_under(str(run_dir)) == 0
        assert proc.poll() is None
    finally:
        proc.kill()


# ---- F3: provider limit ----------------------------------------------------------------------


def test_all_passes_failed_names_the_first_pass_error(memo_env, monkeypatch):
    report, run_dir = _memo_report(memo_env)
    rid = report["id"]
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", lambda **_kw: (None, LIMIT))
    stream = memo_analysis._RunStream(rid, memo_prep.stream_path(run_dir), truncate=False)

    pass_results, _cost, _ms = _phase2(rid, run_dir, stream, memo_env)

    assert pass_results is None
    after = storage.get_report(rid)
    assert after["error"] == after["failure_detail"] == f"All fast memo analysis passes failed: {LIMIT}"
    assert memo_analysis._recorded_fast_phase2_failure(rid) == after["failure_detail"]
    assert _events(run_dir)[-1]["error"] == after["error"]


def _funnel(run_dir, label):
    return claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message=label,
        timeout_label=label,
        timeout_sec=5,
    )


def test_provider_limit_stops_further_spawns_in_the_same_run(monkeypatch, tmp_path):
    calls: list[str] = []
    replies = {"pass-1": (None, LIMIT)}

    def inner(**kw):
        calls.append(kw["timeout_label"])
        return replies.get(kw["timeout_label"], ({"ok": True}, None))

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact_inner", inner)
    run_dir = tmp_path / "run"
    try:
        assert _funnel(run_dir, "pass-1") == (None, LIMIT)
        assert _funnel(run_dir, "pass-2") == (None, LIMIT)
        assert _funnel(run_dir, "pass-3") == (None, LIMIT)
        assert calls == ["pass-1"]
        claude_runner.reset_run_dir_state(str(run_dir))
        assert _funnel(run_dir, "pass-4") == ({"ok": True}, None)
        assert calls == ["pass-1", "pass-4"]
    finally:
        claude_runner.reset_run_dir_state(str(run_dir))


def test_ordinary_failures_do_not_stop_the_run(monkeypatch, tmp_path):
    calls: list[str] = []

    def inner(**kw):
        calls.append(kw["timeout_label"])
        return None, "claude exited 1: malformed output"

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact_inner", inner)
    run_dir = tmp_path / "run"
    try:
        _funnel(run_dir, "pass-1")
        _funnel(run_dir, "pass-2")
        assert calls == ["pass-1", "pass-2"]
    finally:
        claude_runner.reset_run_dir_state(str(run_dir))
