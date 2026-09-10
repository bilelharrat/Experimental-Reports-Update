"""Report-ready artifacts detach: scanner grace, handle state, registry.

The detached artifacts agent may still be running when the memo package is
accepted; the run parks the handle and the finalizer collects it after the
DOCX renders. These tests cover the pieces that machinery leans on:

- the jobs-rail scanner must not declare a run dead on a fresh
  StructuredOutput schema rejection (routine mid-retry state — this
  blanked the rail for minutes on healthy runs);
- AsyncArtifacts.done picks between inline harvest and the tail;
- the parked-handle registry, including failure-path abandonment.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from server import claude_runner, job_progress, memo_analysis, storage


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _write_stream(path, events) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def _rejection_stream(tmp_path, *, rejection_age_seconds: float):
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(seconds=rejection_age_seconds))
    path = tmp_path / "logs" / "stream.jsonl"
    _write_stream(
        path,
        [
            {
                "type": "job_init",
                "ts": _iso(now - timedelta(seconds=rejection_age_seconds + 60)),
                "kind": "memo",
                "report_id": "r1",
            },
            {
                "type": "claude_action",
                "ts": ts,
                "action": "tool_result",
                "tool": "StructuredOutput",
                "is_error": True,
                "preview": "Output does not match required schema",
            },
        ],
    )
    return path


def test_fresh_schema_rejection_keeps_run_in_flight(tmp_path):
    path = _rejection_stream(tmp_path, rejection_age_seconds=30)
    state = job_progress.scan_active_progress_state(path, max_idle_seconds=1800)
    assert state is not None
    assert state["terminated"] is False


def test_stale_schema_rejection_drops_run(tmp_path):
    age = job_progress.SCHEMA_RETRY_GRACE_SECONDS + 60
    path = _rejection_stream(tmp_path, rejection_age_seconds=age)
    # The file itself was just written (mtime fresh), so only the new
    # event-age grace separates this from the fresh-rejection case.
    state = job_progress.scan_active_progress_state(path, max_idle_seconds=1800)
    assert state is None


def test_report_ready_stage_sets_state_flag(tmp_path):
    now = datetime.now(timezone.utc)
    path = tmp_path / "logs" / "stream.jsonl"
    _write_stream(
        path,
        [
            {"type": "job_init", "ts": _iso(now), "kind": "memo"},
            {
                "type": "stage",
                "ts": _iso(now),
                "stage": "memo_report_ready",
                "message": "Report is ready to view",
                "report_ready": True,
            },
        ],
    )
    state = job_progress.scan_progress_state(path)
    assert state["report_ready"] is True

    plain = tmp_path / "logs" / "plain.jsonl"
    _write_stream(
        plain,
        [{"type": "stage", "ts": _iso(now), "stage": "rendering_docx"}],
    )
    assert job_progress.scan_progress_state(plain)["report_ready"] is False


def test_async_artifacts_done_property(tmp_path, monkeypatch):
    release = threading.Event()

    def _fake_agent(**kwargs):
        release.wait(5.0)
        return {"analysis_artifacts": {"claim_register_md": "# Claims"}}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts", _fake_agent
    )
    handle = claude_runner.AsyncArtifacts(
        run_dir=tmp_path, company_name="Testco", stream=None
    )
    assert handle.done is False  # never started
    handle.start(common_context="", add_dirs=[], timeout_sec=5)
    assert handle.done is False  # agent blocked on the event
    release.set()
    result, error = handle.join(timeout_sec=5.0)
    assert error is None
    assert handle.done is True
    handle.shutdown()


@pytest.fixture()
def _memo_report(tmp_path, monkeypatch):
    from server import memo_prep

    # conftest isolates storage.DATA_DIR; align memo_prep so
    # _resolve_run_dir resolves rel paths inside the test tmp dir too.
    monkeypatch.setattr(memo_prep, "DATA_DIR", storage.DATA_DIR)
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    report = storage.create_report(
        company_id="zainar-inc",
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    run_dir = tmp_path / "memo-run"
    run_dir.mkdir()
    rel = run_dir.relative_to(memo_prep.DATA_DIR.parent)
    storage.update_report(report["id"], run_dir=str(rel))
    return storage.get_report(report["id"]), run_dir


class _FakeHandle:
    def __init__(self):
        self.shutdowns = 0

    def join(self, timeout_sec=0):
        return None, "abandoned"

    def shutdown(self):
        self.shutdowns += 1


def test_abandon_pending_artifacts_reaps(_memo_report, monkeypatch):
    report, run_dir = _memo_report
    handle = _FakeHandle()
    memo_analysis._park_pending_artifacts(run_dir, handle)
    killed: list[str] = []
    monkeypatch.setattr(
        memo_analysis.claude_runner,
        "terminate_claude_procs_under",
        lambda path: killed.append(path) or 0,
    )

    memo_analysis._abandon_pending_artifacts(report["id"])
    assert killed == [str(run_dir)]
    assert handle.shutdowns == 1

    # Second call no-ops: the registry entry is gone.
    memo_analysis._abandon_pending_artifacts(report["id"])
    assert killed == [str(run_dir)]
    assert handle.shutdowns == 1


def test_with_run_slot_reaps_parked_artifacts_on_failure(
    _memo_report, monkeypatch
):
    from server import product_store

    report, run_dir = _memo_report
    monkeypatch.setattr(product_store, "memo_parallel_runs", lambda: 2)
    handle = _FakeHandle()
    memo_analysis._park_pending_artifacts(run_dir, handle)
    killed: list[str] = []
    monkeypatch.setattr(
        memo_analysis.claude_runner,
        "terminate_claude_procs_under",
        lambda path: killed.append(path) or 0,
    )

    def _worker():
        raise RuntimeError("pipeline blew up")

    with pytest.raises(RuntimeError):
        memo_analysis._with_run_slot(report["id"], _worker)

    assert killed == [str(run_dir)]
    assert handle.shutdowns == 1
    assert memo_analysis._pop_pending_artifacts(run_dir) is None
