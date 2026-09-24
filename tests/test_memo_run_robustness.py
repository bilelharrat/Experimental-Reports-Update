"""Runs explain their failures and survive hard kills honestly.

- A worker crash records the cause ("ValueError: …"), never "see server
  log", with the traceback in the run's logs/crash.txt (late-stage and
  Buffett).
- Startup recovery renders only a package that exists and validates; one
  successful Claude call is not a finished run — the run is demoted
  "interrupted" (or, when the English was already delivered, it ends on
  the English and Resume retries the Chinese).
- Recent "interrupted" runs auto-resume; old ones stay parked.
- A finished run persists its reader block and schedules its PDF.
- A tracking auto-run's report keeps its company identity.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from server import (
    api,
    buffett_memo_analysis,
    claude_runner,
    job_progress,
    memo_analysis,
    memo_prep,
    report_reader,
    storage,
)
from test_memo_analysis import (  # noqa: F401 — memo_env is a fixture
    _events,
    _make_memo_report,
    _memo_package,
    _write_memo_package,
    memo_env,
)


# ---- crashes explain themselves -------------------------------------------------------


@pytest.mark.parametrize(
    "wrapper, target, phase",
    [
        ("_run_safe", "_run", "analysis"),
        ("_resume_safe", "_resume", "resume"),
        ("_investigate_safe", "_investigate", "investigation"),
        ("_generate_safe", "_generate_from_studio", "studio_generate"),
    ],
)
def test_a_worker_crash_records_its_cause(memo_env, monkeypatch, wrapper, target, phase):
    report, run_dir = _make_memo_report(memo_env)
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit("job_init", kind="memo")

    def boom(_report_id):
        raise ValueError("Invalid company id")

    monkeypatch.setattr(memo_analysis, target, boom)
    getattr(memo_analysis, wrapper)(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == phase
    assert updated["failure_detail"] == "ValueError: Invalid company id"
    assert "see server log" not in (updated.get("error") or "")
    crash = (run_dir / "logs" / "crash.txt").read_text(encoding="utf-8")
    assert "ValueError: Invalid company id" in crash
    assert "Traceback" in crash
    assert updated["crash_log"].endswith("logs/crash.txt")
    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert "ValueError: Invalid company id" in events[-1]["error"]
    kind = report_reader.classify_failure(updated)
    assert kind["failure_kind"] == "internal_error"


def test_a_buffett_worker_crash_records_its_cause(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    storage.update_report(report["id"], kind=memo_prep.BUFFETT_KIND)

    def boom(_report_id):
        raise KeyError("price")

    monkeypatch.setattr(buffett_memo_analysis, "_run", boom)
    buffett_memo_analysis._run_safe(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["failure_phase"] == "analysis"
    assert updated["failure_detail"] == "KeyError: 'price'"
    assert (run_dir / "logs" / "crash.txt").exists()


def test_a_crash_on_a_provider_limit_is_remembered(memo_env, monkeypatch):
    from server import provider_limits

    report, _run_dir = _make_memo_report(memo_env)

    def boom(_report_id):
        raise RuntimeError("Claude AI usage limit reached|resets 3pm")

    monkeypatch.setattr(memo_analysis, "_run", boom)
    memo_analysis._run_safe(report["id"])
    try:
        assert provider_limits.current_limit("claude") is not None
    finally:
        provider_limits.clear_provider_limit()


# ---- honest recovery --------------------------------------------------------------------


def _stream_with_one_pass_success(run_dir):
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit("job_init", kind="memo")
    stream.emit("thread_started", thread="Market sizing")
    stream.emit("claude_action", action="result", subtype="success", cost_usd=0.4)
    return stream


def test_one_pass_success_without_a_package_is_interrupted_not_rendered(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    _stream_with_one_pass_success(run_dir)
    monkeypatch.setattr(
        memo_analysis,
        "_render_memo_outputs",
        lambda **_kw: pytest.fail("no package: nothing may be rendered"),
    )

    recovered = memo_analysis.recover_stale_reports()

    assert recovered == 1
    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == "interrupted"
    assert updated["failure_detail"] == "interrupted before the memo package was written"
    assert updated["last_activity_at"]
    assert report_reader.classify_failure(updated)["failure_kind"] == "interrupted"
    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error" and events[-1]["phase"] == "interrupted"


def test_an_invalid_package_is_interrupted_not_rendered(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.json").write_text('{"schema_version": 1}', encoding="utf-8")
    _stream_with_one_pass_success(run_dir)

    memo_analysis.recover_stale_reports()

    assert storage.get_report(report["id"])["failure_phase"] == "interrupted"


def test_a_valid_package_is_still_rendered_at_recovery(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    _write_memo_package(run_dir)
    _stream_with_one_pass_success(run_dir)

    memo_analysis.recover_stale_reports()

    assert storage.get_report(report["id"])["status"] == "complete"


def test_a_kill_after_the_english_keeps_the_english(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    paths = memo_analysis._memo_paths_abs(report)
    paths["zh"].unlink()
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.en.json").write_text(
        json.dumps(_memo_package(body_zh=""), ensure_ascii=False), encoding="utf-8"
    )
    storage.update_report(report["id"], english_ready_at="2026-09-22T10:00:00+00:00")
    _stream_with_one_pass_success(run_dir)

    memo_analysis.recover_stale_reports()

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["failure_phase"] == "chinese_package"
    assert updated["quality_warnings"] == [memo_analysis.CHINESE_INTERRUPTED_WARNING[0]]
    assert paths["en"].exists()


def test_a_run_with_a_live_worker_is_left_alone(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    _stream_with_one_pass_success(run_dir)
    monkeypatch.setattr(memo_analysis, "_memo_worker_alive", lambda _rid: True)

    memo_analysis.recover_stale_reports()

    assert storage.get_report(report["id"])["status"] == "analyzing"


# ---- auto-resume of interrupted runs --------------------------------------------------


def _interrupted(memo_env, *, hours_ago: float):
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "analysis").mkdir(exist_ok=True)
    (run_dir / "analysis" / "pressure_tests.md").write_text("# Notes\n", encoding="utf-8")
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        failure_phase="interrupted",
        failure_detail="interrupted before the memo package was written",
        last_activity_at=when.isoformat(),
    )
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit("error", error="x")
    return report


def test_a_recent_interrupted_run_is_auto_resumed(memo_env, monkeypatch):
    report = _interrupted(memo_env, hours_ago=0.5)
    called: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_resume", called.append)

    assert api.resume_interrupted_memo_runs() == 1
    assert called == [report["id"]]


def test_an_old_interrupted_run_stays_parked(memo_env, monkeypatch):
    _interrupted(memo_env, hours_ago=5)
    called: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_resume", called.append)

    assert api.resume_interrupted_memo_runs() == 0
    assert called == []


# ---- completion hooks ---------------------------------------------------------------------


def test_a_finished_run_persists_its_reader_block_and_schedules_its_pdf(memo_env, monkeypatch):
    from server import memo_pdf

    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    report, run_dir = _make_memo_report(memo_env)
    scheduled: list[str] = []
    persisted: list[str] = []
    monkeypatch.setattr(memo_pdf, "schedule_pdf", lambda rid: scheduled.append(rid))
    monkeypatch.setattr(report_reader, "persist_reader_block", lambda rid: persisted.append(rid))

    def fake_run_investment_memo(**_kwargs):
        _write_memo_package(run_dir)
        return {"ok": True, "cost_usd": 1.0, "duration_ms": 10}

    monkeypatch.setattr(claude_runner, "run_investment_memo", fake_run_investment_memo)
    memo_analysis._run(report["id"])

    assert storage.get_report(report["id"])["status"] == "complete"
    assert scheduled == [report["id"]]
    assert persisted == [report["id"]]


# ---- tracking auto-runs keep the company identity -----------------------------------------


def test_a_tracking_auto_run_report_snapshots_the_company_identity(monkeypatch):
    from server import tracking_updates

    seen: list[str] = []
    monkeypatch.setattr(
        report_reader, "snapshot_company_identity", lambda rid, company=None: seen.append(rid)
    )
    tracking_updates._snapshot_report_identity("rep-1")
    tracking_updates._snapshot_report_identity("")
    assert seen == ["rep-1"]


def test_the_report_reader_reads_an_english_only_package(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.en.json").write_text(
        json.dumps(_memo_package(body_zh=""), ensure_ascii=False), encoding="utf-8"
    )
    package = report_reader.load_package(storage.get_report(report["id"]))
    assert package is not None and package["sections"]


def test_buffett_warnings_get_structured_items():
    items = buffett_memo_analysis._warning_items(
        ["Chinese parity: 2 numbers differ", "Fact check: 3 unsupported figures", "Voice: first person"],
        ["中文对照：2 个数字不一致", "事实核查：3 个数字无来源", "语气：第一人称"],
        detail_path="data/memos/x/run/logs/buffett_checks.md",
    )
    assert [item["gate"] for item in items] == ["chinese_parity", "fact_check", "quality"]
    assert [item["language"] for item in items] == ["ZH", "EN", "EN"]
    assert items[0]["summary_zh"] == "中文对照：2 个数字不一致"
    assert all(item["detail_path"].endswith("buffett_checks.md") for item in items)
    assert buffett_memo_analysis._warning_items([], []) is None
