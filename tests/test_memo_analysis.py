from __future__ import annotations

import json

from docx import Document
import pytest

from server import (
    api,
    claude_runner,
    docx_pdf,
    job_progress,
    memo_analysis,
    memo_prep,
    storage,
)


@pytest.fixture
def memo_env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    monkeypatch.setattr(
        memo_prep,
        "SETTINGS_FILE",
        data_root / "settings" / "serena_background.md",
    )
    monkeypatch.setattr(memo_prep, "COMPANIES_FILE", data_root / "companies.yaml")
    return data_root


def _events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _make_memo_report(data_root):
    run_id = "2026-05-22__191917"
    run_dir = (
        data_root
        / "memos"
        / "generalist-inc"
        / f"{run_id}__generalist-inc__memo-run"
    )
    memo_dir = run_dir / "memo"
    memo_dir.mkdir(parents=True)
    en_path = memo_dir / f"Generalist, Inc. - Investment Memo - {run_id}.docx"
    zh_path = memo_dir / f"Generalist, Inc. - 投资备忘录 - {run_id}.docx"
    _write_clean_memo_docx(en_path)
    _write_clean_memo_docx(zh_path)

    report = storage.create_report_record(
        company_id="generalist-inc",
        company_name="Generalist, Inc.",
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status="analyzing",
        progress=95,
        stage="Rendering PDF previews",
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[
            {"language": "en", "path": memo_prep._rel(en_path)},
            {"language": "zh", "path": memo_prep._rel(zh_path)},
        ],
    )
    return report, run_dir


def _write_clean_memo_docx(path):
    document = Document()
    document.add_paragraph("I. Executive Summary")
    document.add_paragraph(
        "Generalist builds automation infrastructure. BSH should proceed only "
        "after deployment depth and valuation support are confirmed."
    )
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Treatment"
    table.cell(1, 0).text = "Revenue"
    table.cell(1, 1).text = (
        "Not disclosed; model uses customer-count proxy and diligence threshold."
    )
    document.add_paragraph("VI. Sources, Source Classes, and Fact Reference Index")
    document.add_paragraph("[S1] Company materials, company-reported.")
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def _write_bad_memo_docx(path):
    document = Document()
    document.add_paragraph("I. Executive Summary")
    document.add_paragraph(
        "ZaiNar has no battery cost [WV SPV memo] and a hard IP wall "
        "(present-state)."
    )
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Last priced valuation"
    table.cell(1, 1).text = "~$1.0B post-money [companies.yaml]"
    document.save(path)


def test_memo_run_completes_when_optional_pdf_render_fails(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )

    def fake_run_investment_memo(**kwargs):
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=1.25,
            duration_ms=1234,
        )
        return {"ok": True, "cost_usd": 1.25, "duration_ms": 1234}

    monkeypatch.setattr(
        claude_runner, "run_investment_memo", fake_run_investment_memo
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda *_args, **_kwargs: (False, "Word conversion timed out"),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["progress"] == 100
    assert updated["stage"] == "Memo ready"
    assert not any("pdf_path" in f for f in updated["memo_files"])

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "done"
    assert any(
        e.get("type") == "claude_action"
        and e.get("tool") == "docx→pdf"
        and e.get("is_error")
        for e in events
    )


def test_memo_run_fails_closed_when_docx_quality_gate_finds_p0(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    en_path = memo_analysis._memo_paths_abs(report)["en"]
    _write_bad_memo_docx(en_path)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )

    def fake_run_investment_memo(**kwargs):
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=1.25,
            duration_ms=1234,
        )
        return {"ok": True, "cost_usd": 1.25, "duration_ms": 1234}

    monkeypatch.setattr(
        claude_runner, "run_investment_memo", fake_run_investment_memo
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PDF rendering should not run after quality failure")
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_quality_gate"
    assert updated["stage"] == "Memo failed quality gate"
    assert updated["memo_quality_lint"]["p0_count"] >= 1
    assert (run_dir / "logs" / "memo_quality_lint.md").exists()

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "quality_gate"
    assert events[-1]["findings"]


def test_recover_stale_memo_report_emits_missing_done(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )
    stream.emit("thread_started", thread="Validation log")
    stream.emit(
        "claude_action",
        action="result",
        subtype="success",
        cost_usd=9.02,
        duration_ms=1845017,
    )

    recovered = memo_analysis.recover_stale_reports()

    assert recovered == 1
    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["progress"] == 100
    assert updated["claude_cost_usd"] == 9.02

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-2]["type"] == "thread_finished"
    assert events[-2]["thread"] == "Validation log"
    assert events[-1]["type"] == "done"
    assert events[-1]["recovered"] is True

    state = api._scan_progress_state(memo_prep.stream_path(run_dir))
    assert state["terminated"] is True


def test_active_memo_job_registers_subtask_completion(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )
    stream.emit("thread_started", thread="Pressure tests")
    stream.emit(
        "claude_action",
        action="tool_use",
        tool="Write",
        thread="Pressure tests",
        preview="analysis/pressure_tests.md",
    )
    stream.emit("thread_finished", thread="Pressure tests")
    stream.emit("thread_started", thread="Validation log")

    state = api._scan_progress_state(memo_prep.stream_path(run_dir))

    assert state["terminated"] is False
    assert state["thread_count"] == 2
    assert state["thread_done_count"] == 1
    assert state["thread_failed_count"] == 0
    assert state["open_thread_count"] == 1
    assert {
        (thread["name"], thread["status"])
        for thread in state["threads"]
    } == {
        ("Pressure tests", "done"),
        ("Validation log", "running"),
    }

    memo_job = next(
        job for job in api._memo_kind_records()
        if job.get("report_id") == report["id"]
    )
    assert memo_job["thread_count"] == 2
    assert memo_job["thread_done_count"] == 1
    assert memo_job["open_thread_count"] == 1
