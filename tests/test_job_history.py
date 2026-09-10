"""Task-history ledger: recorded on terminal emit, served by /api/jobs/history."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server import job_history, job_progress, storage
from server.main import app


def _stream(rel: str) -> job_progress.ProgressLog:
    return job_progress.ProgressLog(storage.DATA_DIR / rel)


def test_terminal_emit_records_history_row():
    log = _stream("memos/testco/run-1/logs/stream.jsonl")
    log.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Testco",
        subtitle="Stage-calibrated (auto)",
        report_id="r123",
        company_id="testco",
    )
    log.emit("stage", stage="analyzing", message="Working")
    log.emit("done", report_id="r123")

    rows = job_history.list_history()
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "memo"
    assert row["title"] == "Investment memo — Testco"
    assert row["terminal_type"] == "done"
    assert row["report_id"] == "r123"
    assert row["log_path"] == "memos/testco/run-1/logs/stream.jsonl"
    assert row["started_at"] and row["finished_at"]


def test_history_skips_bare_and_superseded_logs():
    bare = _stream("jobs_misc/bare.jsonl")
    bare.emit("stage", stage="working")
    bare.emit("done")
    assert job_history.list_history() == []

    inited = _stream("jobs_misc/superseded.jsonl")
    inited.emit("job_init", kind="weekly_stocks", title="Weekly")
    job_progress.supersede_progress_file(
        inited.path, reason="superseded stale weekly refresh"
    )
    assert job_history.list_history() == []


def test_history_dedupes_terminal_replays():
    log = _stream("memos/testco/run-2/logs/stream.jsonl")
    log.emit("job_init", kind="memo", title="Memo", report_id="r9")
    log.emit("done")
    # Recovery paths can re-emit a terminal event on the same stream.
    log.emit("done", recovered=True)

    rows = job_history.list_history()
    assert len(rows) == 1
    assert rows[0]["terminal_type"] == "done"


def test_history_endpoint_enriches_memo_and_replays_generic_logs():
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    report = storage.create_report(
        company_id="zainar-inc",
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
    )
    storage.update_report(
        report["id"],
        status="complete",
        report_ready_at="2026-09-10T00:32:00+00:00",
        run_finished_at="2026-09-10T00:36:00+00:00",
        claude_cost_usd=12.5,
    )
    memo_log = _stream("memos/zainar-inc/run-3/logs/stream.jsonl")
    memo_log.emit(
        "job_init",
        kind="memo",
        title="Investment memo — ZaiNar",
        report_id=report["id"],
        company_id="zainar-inc",
    )
    memo_log.emit("done", report_id=report["id"])

    generic_log = _stream("_weekly_stocks/refresh.progress.jsonl")
    generic_log.emit("job_init", kind="weekly_stocks", title="Weekly stocks")
    generic_log.emit("error", error="claude exited 1")

    client = TestClient(app)
    rows = client.get("/api/jobs/history").json()
    assert len(rows) == 2

    memo_row = next(r for r in rows if r["kind"] == "memo")
    assert memo_row["log_url"] == f"/api/jobs/log?path=memo:{report['id']}"
    assert memo_row["status"] == "complete"
    assert memo_row["report_ready_at"] == "2026-09-10T00:32:00+00:00"
    assert memo_row["run_finished_at"] == "2026-09-10T00:36:00+00:00"
    assert memo_row["claude_cost_usd"] == 12.5
    assert memo_row["primary_route"]["params"]["reportId"] == report["id"]

    generic_row = next(r for r in rows if r["kind"] == "weekly_stocks")
    assert generic_row["terminal_type"] == "error"
    assert generic_row["error"] == "claude exited 1"
    token_url = generic_row["log_url"]
    assert token_url == f"/api/jobs/log?path=history:{generic_row['id']}"
    events = client.get(token_url).json()
    assert any(e.get("type") == "job_init" for e in events)


def test_history_limit_and_order():
    for i in range(5):
        log = _stream(f"jobs_misc/task-{i}.jsonl")
        log.emit("job_init", kind="search", title=f"Search {i}")
        log.emit("done")
    rows = job_history.list_history(limit=3)
    assert len(rows) == 3
    # Newest first.
    assert rows[0]["title"] == "Search 4"
