from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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
    internal_md = memo_dir / f"Generalist, Inc. - Internal Diligence Memo - {run_id}.md"
    internal_docx = memo_dir / f"Generalist, Inc. - Internal Diligence Memo - {run_id}.docx"
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
        internal_memo_files=[
            {
                "kind": "internal_diligence_memo",
                "language": "en",
                "markdown_path": memo_prep._rel(internal_md),
                "path": memo_prep._rel(internal_docx),
            }
        ],
    )
    return report, run_dir


def _write_clean_memo_docx(path):
    document = Document()
    document.add_paragraph("I. Executive Summary")
    document.add_paragraph(
        "Generalist builds automation infrastructure. Investors should proceed only "
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


def _write_internal_memo_markdown(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "# Internal Diligence Memo - Generalist, Inc.",
            "",
            "## Internal Recommendation",
            "Recommendation: Proceed if confirmed.",
            "",
            "| Item | View |",
            "|---|---|",
            "| Suggested allocation | $5-10M pending confirmation |",
            "| Conviction | Medium |",
            "",
            "## Allocation Rationale",
            "The suggested allocation reflects scarce access, stage fit, and "
            "remaining deployment proof that can change commitment sizing.",
            "",
            "## Internal Diligence Priorities",
            "- Confirm deployment depth.",
            "- Confirm valuation support.",
            "- Confirm SPV economics.",
            "",
            "## Risk Controls And Stop/Revisit Conditions",
            "Hold pending confirmation if customer proof is not source-backed.",
            "",
            "Internal use only.",
        ]),
        encoding="utf-8",
    )


def _memo_package(body_en=None, body_zh=None):
    return {
        "schema_version": 1,
        "company": {
            "name": "Generalist, Inc.",
            "descriptor": {
                "en": "Industrial automation systems",
                "zh": "工业自动化系统",
            },
            "stage": "Late-stage / pre-IPO",
            "sector": "AI Robotics",
            "location": "San Francisco, CA",
            "round": "Series D context",
        },
        "run": {"run_id": "2026-05-22__191917", "as_of": "2026-05-22"},
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {
                            "en": body_en
                            or (
                                "Generalist builds automation infrastructure. "
                                "Investors should proceed only after deployment depth "
                                "and valuation support are confirmed."
                            ),
                            "zh": (
                                body_zh
                                or (
                                    "Generalist 构建自动化基础设施。BSH 只有在确认部署深度"
                                    "和估值支撑后才应继续推进。"
                                )
                            ),
                        },
                    },
                    {
                        "type": "table",
                        "title": {
                            "en": "Key Metrics Snapshot",
                            "zh": "关键指标快照",
                        },
                        "headers": [
                            {"en": "Metric", "zh": "指标"},
                            {"en": "Treatment", "zh": "处理方式"},
                        ],
                        "rows": [
                            [
                                {"en": "Revenue", "zh": "收入"},
                                {
                                    "en": (
                                        "Not disclosed; model uses customer-count "
                                        "proxy and diligence threshold."
                                    ),
                                    "zh": "未披露；模型使用客户数量代理和尽调门槛。",
                                },
                            ]
                        ],
                    },
                ],
            },
            {
                "id": "company_overview",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {
                            "en": "The company sells automation systems for repeatable industrial workflows.",
                            "zh": "该公司销售面向可重复工业流程的自动化系统。",
                        },
                    }
                ],
            },
            {
                "id": "investment_highlights",
                "blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            {
                                "en": "Deployment proof creates a concrete diligence path.",
                                "zh": "部署验证提供了具体的尽调路径。",
                            },
                            {
                                "en": "Repeatable production usage can support the expansion case.",
                                "zh": "可重复的生产环境使用可支持扩张判断。",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "investment_risk",
                "blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            {
                                "en": "Hardware integration may slow gross-margin expansion.",
                                "zh": "硬件集成可能拖慢毛利率提升。",
                            },
                            {
                                "en": "Enterprise adoption may remain services-heavy.",
                                "zh": "企业采用可能继续偏服务交付。",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "financial_forecast_valuation",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {
                            "en": "The valuation case should use conservative scenario ranges.",
                            "zh": "估值判断应使用保守情景区间。",
                        },
                    }
                ],
            },
        ],
        "sources": [
            {
                "id": "S1",
                "title": "Company investor materials",
                "class": {"en": "Company material", "zh": "公司材料"},
                "treatment": {
                    "en": "Used for product, customer, and funding context.",
                    "zh": "用于产品、客户和融资背景。",
                },
                "as_of": "2026-05-22",
            }
        ],
    }


def _write_memo_package(run_dir, *, body_en=None, body_zh=None):
    path = run_dir / "logs" / "memo_package.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _memo_package(body_en=body_en, body_zh=body_zh),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


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
        _write_memo_package(run_dir)
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

    def fake_run_internal_diligence_memo(**kwargs):
        _write_internal_memo_markdown(kwargs["internal_markdown_path"])
        return {"ok": True, "cost_usd": 0.25, "duration_ms": 250}

    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        fake_run_internal_diligence_memo,
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
    assert updated["internal_memo_files"][0]["path"].endswith(".docx")
    assert "pdf_path" not in updated["internal_memo_files"][0]
    assert (run_dir / "memo" / f"Generalist, Inc. - Internal Diligence Memo - {report['run_id']}.docx").exists()

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "done"
    assert events[-1]["internal_memo_paths"]["md"].endswith(".md")
    assert any(
        e.get("type") == "claude_action"
        and e.get("tool") == "docx→pdf"
        and e.get("is_error")
        for e in events
    )


def test_memo_run_fails_closed_when_chinese_parity_gate_finds_p0(
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
        package = _memo_package(
            body_zh=(
                "Generalist builds automation infrastructure. Investors should proceed "
                "only after deployment depth and valuation support are confirmed."
            )
        )
        executive_table = package["sections"][0]["blocks"][1]
        executive_table["title"]["zh"] = "Key Metrics Snapshot"
        executive_table["headers"][0]["zh"] = "Metric"
        executive_table["headers"][1]["zh"] = "Treatment"
        executive_table["rows"][0][0]["zh"] = "Revenue"
        executive_table["rows"][0][1]["zh"] = (
            "Not disclosed; model uses customer-count proxy and diligence threshold."
        )
        path = run_dir / "logs" / "memo_package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(package, ensure_ascii=False),
            encoding="utf-8",
        )
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
    def fake_convert_docx_to_pdf(docx_path, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4\n")
        return True, None

    monkeypatch.setattr(docx_pdf, "convert_docx_to_pdf", fake_convert_docx_to_pdf)

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_quality_gate"
    assert updated["stage"] == "Memo failed Chinese parity gate"
    assert updated["artifacts_available"] is True
    assert updated["memo_chinese_parity"]["p0_count"] >= 1
    assert all(f.get("pdf_path") for f in updated["memo_files"])
    assert (run_dir / "logs" / "memo_chinese_parity.md").exists()

    detail = api._report_detail(updated)
    assert detail["download_urls"]["en"].endswith("language=en")
    assert detail["preview_urls"]["en"].endswith("language=en")

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "chinese_parity_gate"
    assert events[-1]["findings"]


def test_report_detail_advertises_internal_memo_urls(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    internal_docx = run_dir / "memo" / (
        f"Generalist, Inc. - Internal Diligence Memo - {report['run_id']}.docx"
    )
    internal_pdf = internal_docx.with_suffix(".pdf")
    _write_clean_memo_docx(internal_docx)
    internal_pdf.write_bytes(b"%PDF-1.4\n")
    storage.update_report(
        report["id"],
        internal_memo_files=[
            {
                "kind": "internal_diligence_memo",
                "language": "en",
                "markdown_path": memo_prep._rel(internal_docx.with_suffix(".md")),
                "path": memo_prep._rel(internal_docx),
                "pdf_path": memo_prep._rel(internal_pdf),
            }
        ],
    )

    detail = api._report_detail(storage.get_report(report["id"]))

    assert detail["download_urls"]["internal"].endswith("artifact=internal")
    assert detail["preview_urls"]["internal"].endswith("artifact=internal")


def test_memo_run_fails_closed_when_docx_quality_gate_finds_p0(
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
        _write_memo_package(
            run_dir,
            body_en=(
                "ZaiNar has no battery cost [WV SPV memo] and a hard IP wall "
                "(present-state)."
            ),
        )
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
    def fake_convert_docx_to_pdf(docx_path, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4\n")
        return True, None

    monkeypatch.setattr(docx_pdf, "convert_docx_to_pdf", fake_convert_docx_to_pdf)

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_quality_gate"
    assert updated["stage"] == "Memo failed quality gate"
    assert updated["artifacts_available"] is True
    assert updated["memo_quality_lint"]["p0_count"] >= 1
    assert all(f.get("pdf_path") for f in updated["memo_files"])
    assert (run_dir / "logs" / "memo_quality_lint.md").exists()

    detail = api._report_detail(updated)
    assert detail["download_urls"]["en"].endswith("language=en")
    assert detail["preview_urls"]["en"].endswith("language=en")

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "quality_gate"
    assert events[-1]["findings"]


def test_memo_run_fails_when_memo_package_missing(memo_env, monkeypatch):
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PDF rendering should not run after package failure")
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["stage"] == "Renderer contract failed"
    assert updated["failure_phase"] == "renderer_contract"
    assert "memo_package.json" in updated["failure_detail"]
    assert updated["renderer_contract"]["errors"]

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "renderer_contract"
    assert "memo_package.json" in events[-1]["error"]
    assert "memo_package missing" in events[-1]["contract_errors"]
    assert any(
        file.get("label") == "memo_package" and file.get("exists") is False
        for file in events[-1]["expected_files"]
    )

    detail = api._report_detail(updated)
    assert detail["failure_detail"] == updated["failure_detail"]
    assert detail["renderer_contract"]["errors"]


def test_memo_run_blocks_generated_renderer_scripts(memo_env, monkeypatch):
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
        (run_dir / "build_memo.py").write_text(
            "# generated renderer should be blocked\n",
            encoding="utf-8",
        )
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
            AssertionError("PDF rendering should not run after renderer violation")
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["stage"] == "Generated renderer script blocked"

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "renderer_contract"
    assert events[-1]["generated_renderer_scripts"]


def test_recover_stale_memo_report_emits_missing_done(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    _write_memo_package(run_dir)
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
    assert any(
        event.get("type") == "thread_finished"
        and event.get("thread") == "Validation log"
        for event in events
    )
    assert events[-1]["type"] == "done"
    assert events[-1]["recovered"] is True

    state = api._scan_progress_state(memo_prep.stream_path(run_dir))
    assert state["terminated"] is True


def test_recover_stale_memo_report_blocks_generated_renderer_scripts(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "build_memo.py").write_text(
        "# generated renderer should be blocked during recovery\n",
        encoding="utf-8",
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo — Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )
    stream.emit(
        "claude_action",
        action="result",
        subtype="success",
        cost_usd=9.02,
        duration_ms=1845017,
    )

    recovered = memo_analysis.recover_stale_reports()

    assert recovered == 0
    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["stage"] == "Generated renderer script blocked"

    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "error"
    assert events[-1]["phase"] == "renderer_contract"
    assert events[-1]["recovered"] is True
    assert events[-1]["generated_renderer_scripts"]


def test_active_memo_job_registers_subtask_completion(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    stream_path = memo_prep.stream_path(run_dir)
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    base_ts = datetime.now(timezone.utc) - timedelta(seconds=10)

    def ts(offset_s: int) -> str:
        return (base_ts + timedelta(seconds=offset_s)).isoformat()

    stream_path.write_text(
        "\n".join(
            json.dumps(event)
            for event in [
                {
                    "type": "job_init",
                    "ts": ts(0),
                    "kind": "memo",
                    "title": "Investment memo — Generalist, Inc.",
                    "report_id": report["id"],
                    "company_id": "generalist-inc",
                    "run_id": report["run_id"],
                },
                {
                    "type": "thread_started",
                    "ts": ts(1),
                    "thread": "Pressure tests",
                },
                {
                    "type": "claude_action",
                    "ts": ts(2),
                    "action": "tool_use",
                    "tool": "Write",
                    "thread": "Pressure tests",
                    "preview": "analysis/pressure_tests.md",
                },
                {
                    "type": "thread_finished",
                    "ts": ts(5),
                    "thread": "Pressure tests",
                },
                {
                    "type": "thread_started",
                    "ts": ts(6),
                    "thread": "Validation log",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state = api._scan_progress_state(stream_path)

    assert state["terminated"] is False
    assert state["thread_count"] == 2
    assert state["thread_done_count"] == 1
    assert state["thread_failed_count"] == 0
    assert state["open_thread_count"] == 1
    assert {
        (thread["name"], thread["status"], thread["event_count"])
        for thread in state["threads"]
    } == {
        ("Pressure tests", "done", 3),
        ("Validation log", "running", 1),
    }
    pressure = next(
        thread for thread in state["threads"]
        if thread["name"] == "Pressure tests"
    )
    assert pressure["elapsed_ms"] == 4000
    assert pressure["last_event_at"] == ts(5)
    assert pressure["latest_action"]["action"] == "tool_use"

    memo_job = next(
        job for job in api._memo_kind_records()
        if job.get("report_id") == report["id"]
    )
    assert memo_job["thread_count"] == 2
    assert memo_job["thread_done_count"] == 1
    assert memo_job["open_thread_count"] == 1
