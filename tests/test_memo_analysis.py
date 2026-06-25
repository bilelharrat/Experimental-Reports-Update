from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from docx import Document
from fastapi import HTTPException
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
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "1")
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "0")
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
            "Recommendation: Proceed.",
            "",
            "| Item | View |",
            "|---|---|",
            "| Suggested allocation | $5-10M with deployment-depth sensitivity |",
            "| Conviction | Medium |",
            "",
            "## Allocation Rationale",
            "The suggested allocation reflects scarce access, stage fit, and "
            "remaining deployment proof that can change commitment sizing.",
            "",
            "## Internal Diligence Priorities",
            "- Deployment depth shapes allocation size.",
            "- Valuation support shapes conviction.",
            "- SPV economics shape effective entry.",
            "",
            "## Risk Controls And Stop/Revisit Conditions",
            "Customer proof below the support threshold weakens commitment sizing.",
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
    monkeypatch.setenv("BSH_MEMO_RENDER_PDF_PREVIEWS", "1")
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo - Generalist, Inc.",
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


def test_memo_run_skips_pdf_and_internal_memo_by_default(memo_env, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
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
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("internal memo should be opt-in")
        ),
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PDF previews should be opt-in")
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["stage"] == "Memo ready"
    assert not any("pdf_path" in f for f in updated["memo_files"])
    internal_docx = run_dir / "memo" / (
        f"Generalist, Inc. - Internal Diligence Memo - {report['run_id']}.docx"
    )
    assert not internal_docx.exists()

    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "pdf_previews_skipped" for e in events)
    assert any(e.get("stage") == "internal_memo_skipped" for e in events)
    assert events[-1]["type"] == "done"
    assert "internal_memo_paths" not in events[-1]


def test_memo_fast_pipeline_runs_parallel_passes_and_finalizes(
    memo_env, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
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
    called_passes = []

    def fake_analysis_pass(**kwargs):
        called_passes.append(kwargs["pass_id"])
        return {
            "summary": f"{kwargs['pass_label']} summary.",
            "key_findings": [
                {
                    "claim": "Commercial proof",
                    "finding": "Evidence supports a scoped diligence path.",
                    "evidence_class": "company-reported",
                    "implication": "Use as conditional support.",
                    "confidence": "medium",
                }
            ],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": ["Use in the investment case."],
            "claude_cost_usd": 0.01,
            "claude_duration_ms": 100,
        }, None

    def fake_english_package(**kwargs):
        assert (run_dir / "analysis" / "fast").exists()
        return {
            "analysis_artifacts": {
                "claim_register_md": "# Claim Register\n\n- Commercial proof: supported.",
                "scenario_swim_lanes_md": "# Scenario Swim Lanes\n\n- Base: participate with contract-conversion sensitivity.",
                "pre_mortem_md": "# Pre-Mortem\n\n- Deployment stalls.",
                "reverse_ic_md": "# Reverse IC\n\n- Pass if valuation support fails.",
                "validation_log_md": "# Validation Log\n\n- Revenue: not disclosed.",
                "risk_sensitivities_md": (
                    "# Risk Sensitivities\n\n"
                    "1. Binding contract conversion supports valuation."
                ),
            },
            "memo_package": _memo_package(body_zh=""),
            "claude_cost_usd": 0.10,
            "claude_duration_ms": 500,
        }, None

    def fake_bilingual_package(**kwargs):
        assert kwargs["english_package_path"].name == "memo_package.en.json"
        return {
            "memo_package": _memo_package(),
            "claude_cost_usd": 0.05,
            "claude_duration_ms": 400,
        }, None

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_analysis_pass",
        fake_analysis_pass,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        fake_english_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        fake_bilingual_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_investment_memo",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("fast path should not call legacy memo runner")
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["stage"] == "Memo ready"
    assert len(called_passes) == len(memo_analysis._FAST_MEMO_PASSES)
    assert (run_dir / "logs" / "memo_package.en.json").exists()
    assert (run_dir / "logs" / "memo_package.json").exists()
    assert (run_dir / "analysis" / "claim_register.md").exists()

    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_fast_parallel_dispatch" for e in events)
    phase_events = [e for e in events if e.get("type") == "phase_timing"]
    phases = {(e.get("phase"), e.get("status")) for e in phase_events}
    assert ("memo_background_run", "started") in phases
    assert ("memo_background_run", "finished") in phases
    assert ("memo_fast_parallel_analysis", "finished") in phases
    assert ("memo_fast_english_package", "finished") in phases
    assert ("memo_fast_chinese_package", "finished") in phases
    assert ("memo_docx_render", "finished") in phases
    assert ("memo_chinese_parity_gate", "finished") in phases
    assert ("memo_quality_gate", "finished") in phases
    assert ("memo_pdf_previews", "skipped") in phases
    assert ("memo_internal_diligence", "skipped") in phases
    assert any(
        e.get("phase") == "memo_fast_parallel_analysis"
        and e.get("worker_count") == memo_analysis._memo_fast_max_workers()
        for e in phase_events
    )
    scanned = job_progress.scan_progress_state(memo_prep.stream_path(run_dir))
    assert any(
        e.get("phase") == "memo_docx_render"
        for e in scanned.get("phase_timings") or []
    )
    assert any(e.get("stage") == "pdf_previews_skipped" for e in events)
    assert events[-1]["type"] == "done"


def test_memo_fast_pipeline_retries_transient_english_package_failure(
    memo_env, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.setenv("BSH_MEMO_FAST_ENGLISH_PACKAGE_RETRIES", "1")
    monkeypatch.setenv("BSH_MEMO_FAST_RETRY_BACKOFF_SEC", "0")
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
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
    called_passes = []
    english_calls = []

    def fake_analysis_pass(**kwargs):
        called_passes.append(kwargs["pass_id"])
        return {
            "summary": f"{kwargs['pass_label']} summary.",
            "key_findings": [],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": [],
            "claude_cost_usd": 0.01,
            "claude_duration_ms": 100,
        }, None

    def fake_english_package(**kwargs):
        english_calls.append(kwargs["run_id"])
        progress = kwargs["progress"]
        if len(english_calls) == 1:
            progress.emit(
                "claude_action",
                action="thinking",
                text=(
                    "API Error: The socket connection was closed unexpectedly. "
                    "For more information, pass verbose: true in the second "
                    "argument to fetch()"
                ),
            )
            progress.emit(
                "claude_action",
                action="result",
                subtype="success",
                cost_usd=0.71,
                duration_ms=254522,
            )
            return None, (
                "claude exited 1: API Error: The socket connection was closed "
                "unexpectedly"
            )
        progress.emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=0.10,
            duration_ms=500,
        )
        return {
            "analysis_artifacts": {
                "claim_register_md": "# Claim Register\n",
                "scenario_swim_lanes_md": "# Scenario Swim Lanes\n",
                "pre_mortem_md": "# Pre-Mortem\n",
                "reverse_ic_md": "# Reverse IC\n",
                "validation_log_md": "# Validation Log\n",
                "risk_sensitivities_md": "# Risk Sensitivities\n",
            },
            "memo_package": _memo_package(body_zh=""),
            "claude_cost_usd": 0.10,
            "claude_duration_ms": 500,
        }, None

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_analysis_pass",
        fake_analysis_pass,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        fake_english_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **_kwargs: (
            {
                "memo_package": _memo_package(),
                "claude_cost_usd": 0.05,
                "claude_duration_ms": 400,
            },
            None,
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert len(called_passes) == len(memo_analysis._FAST_MEMO_PASSES)
    assert len(english_calls) == 2
    assert updated["claude_cost_usd"] >= 0.94

    events = _events(memo_prep.stream_path(run_dir))
    assert any(
        e.get("stage") == "memo_fast_english_package_retry_scheduled"
        for e in events
    )
    attempt_events = [
        e
        for e in events
        if e.get("type") == "phase_timing"
        and e.get("phase") == "memo_fast_english_package_attempt"
    ]
    assert any(e.get("status") == "failed" and e.get("transient") for e in attempt_events)
    assert any(e.get("status") == "finished" and e.get("attempt") == 2 for e in attempt_events)
    phase3_finished = [
        e
        for e in events
        if e.get("type") == "phase_timing"
        and e.get("phase") == "memo_fast_english_package"
        and e.get("status") == "finished"
    ]
    assert phase3_finished[-1]["attempts"] == 2
    assert phase3_finished[-1]["cost_usd"] >= 0.81
    assert not any(
        e.get("type") == "thread_failed"
        and e.get("thread") == claude_runner._MEMO_PHASE3_THREAD
        for e in events
    )


def test_memo_package_voice_cleanup_removes_quality_gate_terms(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    bad_text = (
        "The relevant competitive surface is broader than legacy positioning "
        "vendors. We frame it as technology paradigms rather than a logo list, "
        "because the durable pricing-power question is whether incumbent "
        "paradigms absorb the function ZaiNar performs. We still need a "
        "claim-scope and freedom-to-operate read before we underwrite the "
        "licensing fallback. The instrument has no preference, no voting, "
        "and no information rights at the LP level. This is the right way "
        "to view the underwriting: a pipeline-conversion case. Confirm before "
        "funding: final terms match the disclosed A2 economics. We still need "
        "a claim-scope read that the sponsor implies is covered by the IP "
        "portfolio. Memo language was closing imminent. Diligence Thresholds. "
        "Next Diligence Actions. The sponsor itself acknowledges that a "
        "meaningful portion is in MOU form and that pipeline figures are "
        "company-provided and unaudited. Sponsor explicitly discloses 18 to "
        "36 month carrier sales cycles. The competitor list embedded in the "
        "registry understates the threat surface. Revenue is not documented "
        "in source material. Closing Confirmations. We recommend proceeding "
        "with a participation in the Wisdom Ventures ZaiNar SPV subject to "
        "the closing confirmations below. Valuation Sensitivity Bars. Stop "
        "or Revisit Conditions. What Would Make Us Revisit or Decline. "
        "Immediate Confirmation Work. Closing bar: signed mix supports the case. "
        "Cross-check DoD signings on SAM.gov and USAspending.gov. Patent counsel "
        "claim-scope and freedom-to-operate read supports durable patent leverage. "
        "Source two non-investor technical references through the BSH and partner networks."
    )
    package_path = _write_memo_package(run_dir, body_en=bad_text)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=True)

    rewrite_count = memo_analysis._clean_memo_package_voice(package_path, stream)

    assert rewrite_count >= 1
    package_text = package_path.read_text(encoding="utf-8")
    assert "underwrite" not in package_text.lower()
    assert "underwriting" not in package_text.lower()
    assert "We frame" not in package_text
    assert "information rights" not in package_text
    assert "We should confirm" not in package_text
    assert "Confirm before funding" not in package_text
    assert "We still need" not in package_text
    assert "sponsor implies" not in package_text
    assert "Memo language was" not in package_text
    assert "Diligence Thresholds" not in package_text
    assert "Next Diligence Actions" not in package_text
    assert "Closing Confirmations" not in package_text
    assert "Expected bar" not in package_text
    assert "subject to" not in package_text
    assert "Valuation Sensitivity Bars" not in package_text
    assert "Stop or Revisit Conditions" not in package_text
    assert "What Would Make Us Revisit" not in package_text
    assert "Immediate Confirmation Work" not in package_text
    assert "Closing bar" not in package_text
    assert "Cross-check" not in package_text
    assert "Source two" not in package_text
    assert "sponsor itself acknowledges" not in package_text
    assert "Sponsor explicitly discloses" not in package_text
    assert "embedded in the registry" not in package_text
    assert "source material" not in package_text
    memo_paths_abs = memo_analysis._memo_paths_abs(report)
    memo_analysis.memo_docx_renderer.render_memos(
        package_path,
        out_en=memo_paths_abs["en"],
        out_zh=memo_paths_abs["zh"],
        manifest_path=run_dir / "logs" / "run_manifest.md",
        inventory_path=run_dir / "logs" / "file_inventory.md",
    )

    lint_result = memo_analysis.memo_quality_lint.lint_memo_docx(
        memo_paths_abs["en"]
    )
    assert not any(
        finding.code in {"sell_side_voice_violation", "meta_process_language"}
        for finding in lint_result.findings
    )
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_package_voice_cleanup" for e in events)


def test_memo_fast_pipeline_packet_mode_skips_parallel_passes(
    memo_env, monkeypatch, tmp_path
):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    report, run_dir = _make_memo_report(memo_env)
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    (packet_dir / "memo_packet.md").write_text("# Packet\n", encoding="utf-8")
    storage.update_report(
        report["id"],
        analysis_session_id="session-1",
        analysis_session_approved=True,
    )
    monkeypatch.setattr(
        memo_analysis.serena_analysis,
        "session_dir",
        lambda company_id, session_id: packet_dir,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_analysis_pass",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("approved packet mode should skip analysis fan-out")
        ),
    )

    def fake_english_package(**kwargs):
        assert kwargs["analysis_session_path"] == packet_dir
        return {
            "analysis_artifacts": {
                "claim_register_md": "# Claim Register\n",
                "scenario_swim_lanes_md": "# Scenario Swim Lanes\n",
                "pre_mortem_md": "# Pre-Mortem\n",
                "reverse_ic_md": "# Reverse IC\n",
                "validation_log_md": "# Validation Log\n",
                "risk_sensitivities_md": "# Risk Sensitivities\n",
            },
            "memo_package": _memo_package(body_zh=""),
            "claude_cost_usd": 0.10,
            "claude_duration_ms": 500,
        }, None

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        fake_english_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **_kwargs: (
            {
                "memo_package": _memo_package(),
                "claude_cost_usd": 0.05,
                "claude_duration_ms": 400,
            },
            None,
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_fast_packet_mode" for e in events)
    assert not (run_dir / "analysis" / "fast").exists()


def test_memo_fast_pipeline_draft_packet_still_runs_parallel_passes(
    memo_env, monkeypatch, tmp_path
):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    report, run_dir = _make_memo_report(memo_env)
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    (packet_dir / "memo_packet.md").write_text("# Draft Packet\n", encoding="utf-8")
    storage.update_report(
        report["id"],
        analysis_session_id="session-1",
        analysis_session_approved=False,
    )
    monkeypatch.setattr(
        memo_analysis.serena_analysis,
        "session_dir",
        lambda company_id, session_id: packet_dir,
    )
    called_passes = []

    def fake_analysis_pass(**kwargs):
        called_passes.append(kwargs["pass_id"])
        return {
            "summary": f"{kwargs['pass_label']} summary.",
            "key_findings": [],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": [],
            "claude_cost_usd": 0.01,
            "claude_duration_ms": 100,
        }, None

    def fake_english_package(**kwargs):
        assert kwargs["analysis_session_path"] is None
        return {
            "analysis_artifacts": {
                "claim_register_md": "# Claim Register\n",
                "scenario_swim_lanes_md": "# Scenario Swim Lanes\n",
                "pre_mortem_md": "# Pre-Mortem\n",
                "reverse_ic_md": "# Reverse IC\n",
                "validation_log_md": "# Validation Log\n",
                "risk_sensitivities_md": "# Risk Sensitivities\n",
            },
            "memo_package": _memo_package(body_zh=""),
            "claude_cost_usd": 0.10,
            "claude_duration_ms": 500,
        }, None

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_analysis_pass",
        fake_analysis_pass,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        fake_english_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **_kwargs: (
            {
                "memo_package": _memo_package(),
                "claude_cost_usd": 0.05,
                "claude_duration_ms": 400,
            },
            None,
        ),
    )

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert len(called_passes) == len(memo_analysis._FAST_MEMO_PASSES)
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_fast_parallel_dispatch" for e in events)
    assert not any(e.get("stage") == "memo_fast_packet_mode" for e in events)
    assert (run_dir / "analysis" / "fast").exists()


def test_memo_run_fails_closed_when_chinese_parity_gate_finds_p0(
    memo_env, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_RENDER_PDF_PREVIEWS", "1")
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
    assert detail["artifacts_available"] is True
    assert detail["memo_chinese_parity"]["p0_count"] >= 1
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


def test_report_detail_advertises_partial_analysis_artifacts(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nGenerated before auth failure.\n",
        encoding="utf-8",
    )
    (analysis_dir / "custom_notes.md").write_text(
        "# Custom notes\n",
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Claude skill run failed",
        error="Failed to authenticate. API Error: 403 Request not allowed",
        failure_phase="analysis",
        failure_detail="Failed to authenticate. API Error: 403 Request not allowed",
        artifacts_available=False,
        memo_files=[],
        internal_memo_files=[],
    )

    detail = api._report_detail(storage.get_report(report["id"]))

    assert "download_urls" not in detail
    assert [a["filename"] for a in detail["analysis_artifacts"]] == [
        "pressure_tests.md",
        "custom_notes.md",
    ]
    assert detail["analysis_artifacts"][0]["label"] == "Arithmetic / pressure tests"
    assert detail["analysis_artifacts"][0]["download_url"].endswith(
        "artifact=analysis&file=pressure_tests.md"
    )
    assert detail["analysis_artifacts"][1]["label"] == "Custom Notes"
    assert api.ReportDetail(**detail).analysis_artifacts == detail["analysis_artifacts"]

    response = api.download_memo(
        report["id"],
        artifact="analysis",
        analysis_file="pressure_tests.md",
    )
    assert response.path.endswith("pressure_tests.md")
    with pytest.raises(HTTPException):
        api.download_memo(
            report["id"],
            artifact="analysis",
            analysis_file="../pressure_tests.md",
        )


def test_claude_transient_error_classifier_excludes_provider_limits():
    assert claude_runner.is_transient_claude_error(
        "claude exited 1: API Error: The socket connection was closed unexpectedly"
    )
    assert claude_runner.is_transient_claude_error("fetch failed")
    assert not claude_runner.is_transient_claude_error(
        "Failed to authenticate. API Error: 403 Request not allowed"
    )
    assert not claude_runner.is_transient_claude_error(
        "usage limit reached; try again later"
    )


def test_failed_memo_report_can_resume_from_analysis_artifacts(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nCompleted before provider failure.\n",
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
    stream.emit("error", error="Failed to authenticate. API Error: 403 Request not allowed")
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Claude skill run failed",
        error="Failed to authenticate. API Error: 403 Request not allowed",
        failure_phase="analysis",
        failure_detail="Failed to authenticate. API Error: 403 Request not allowed",
        artifacts_available=False,
    )

    monkeypatch.setattr(
        claude_runner,
        "run_investment_memo",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume must not rerun the full memo analysis")
        ),
    )

    def fake_resume_package(**kwargs):
        _write_memo_package(run_dir)
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=0.5,
            duration_ms=500,
        )
        return {"ok": True, "cost_usd": 0.5, "duration_ms": 500, "resumed": True}

    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        fake_resume_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **kwargs: (
            _write_internal_memo_markdown(kwargs["internal_markdown_path"])
            or {"ok": True, "cost_usd": 0.25, "duration_ms": 250}
        ),
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda docx_path, pdf_path: (pdf_path.write_bytes(b"%PDF-1.4\n") or True, None),
    )

    assert api._report_detail(storage.get_report(report["id"]))["resume_available"] is True

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["stage"] == "Memo ready"
    assert updated["artifacts_available"] is True
    assert updated["failure_phase"] is None
    assert (run_dir / "logs" / "memo_package.json").exists()
    assert list((run_dir / "logs").glob("stream.before_resume.*.jsonl"))

    events = _events(memo_prep.stream_path(run_dir))
    assert events[0]["type"] == "job_init"
    assert events[0]["resumed"] is True
    assert not any(
        event.get("error") == "Failed to authenticate. API Error: 403 Request not allowed"
        for event in events
    )
    assert events[-1]["type"] == "done"
    assert events[-1]["recovered"] is True


def test_resume_retries_transient_resume_package_failure(
    memo_env, monkeypatch
):
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    monkeypatch.setenv("BSH_MEMO_RESUME_PACKAGE_RETRIES", "1")
    monkeypatch.setenv("BSH_MEMO_FAST_RETRY_BACKOFF_SEC", "0")
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nCompleted before provider failure.\n",
        encoding="utf-8",
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit(
        "job_init",
        kind="memo",
        title="Investment memo - Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Claude skill run failed",
        error="claude exited 1",
        failure_phase="analysis",
        failure_detail="claude exited 1",
        artifacts_available=False,
    )
    calls = []

    def fake_resume_package(**kwargs):
        calls.append(kwargs["run_id"])
        if len(calls) == 1:
            return {
                "ok": False,
                "error": (
                    "claude exited 1: API Error: The socket connection was "
                    "closed unexpectedly"
                ),
                "cost_usd": 0.71,
                "duration_ms": 254522,
            }
        _write_memo_package(run_dir)
        return {"ok": True, "cost_usd": 0.5, "duration_ms": 500, "resumed": True}

    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        fake_resume_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("internal memo should be opt-in")
        ),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert len(calls) == 2
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "resume_package_retry_scheduled" for e in events)
    attempts = [
        e
        for e in events
        if e.get("type") == "phase_timing"
        and e.get("phase") == "memo_resume_package_attempt"
    ]
    assert any(e.get("status") == "failed" and e.get("transient") for e in attempts)
    assert any(e.get("status") == "finished" and e.get("attempt") == 2 for e in attempts)


def test_resume_regenerates_existing_invalid_memo_package(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nCompleted before renderer failure.\n",
        encoding="utf-8",
    )
    invalid_package = _memo_package()
    invalid_package["sections"][0]["blocks"].append(
        {
            "type": "table",
            "title": {"en": "Invalid summary", "zh": "无效摘要"},
            "headers": [
                {"en": "Metric", "zh": "指标"},
                {"en": "Value", "zh": "数值"},
            ],
            "rows": [
                [
                    {"en": "Total", "zh": "合计"},
                    {"en": "", "zh": ""},
                ]
            ],
        }
    )
    package_path = run_dir / "logs" / "memo_package.json"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(
        json.dumps(invalid_package, ensure_ascii=False),
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Renderer contract failed",
        failure_phase="renderer_contract",
        failure_detail="Invalid memo package",
    )

    def fake_resume_package(**kwargs):
        assert not package_path.exists()
        assert list((run_dir / "logs").glob("memo_package.invalid.*.json"))
        _write_memo_package(run_dir)
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=0.5,
            duration_ms=500,
        )
        return {"ok": True, "cost_usd": 0.5, "duration_ms": 500, "resumed": True}

    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        fake_resume_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **kwargs: (
            _write_internal_memo_markdown(kwargs["internal_markdown_path"])
            or {"ok": True, "cost_usd": 0.25, "duration_ms": 250}
        ),
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda docx_path, pdf_path: (pdf_path.write_bytes(b"%PDF-1.4\n") or True, None),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    events = _events(memo_prep.stream_path(run_dir))
    assert any(event.get("stage") == "resume_package_invalid" for event in events)
    assert events[-1]["type"] == "done"


def test_resume_regenerates_quality_failed_memo_package(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nCompleted before quality gate failure.\n",
        encoding="utf-8",
    )
    package_path = _write_memo_package(
        run_dir,
        body_en=(
            "Confirm before funding: Series A2 closes at or above $3.0B "
            "pre-money with a named institutional lead."
        ),
    )
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    quality_lint_path.write_text(
        "\n".join([
            "# Memo Quality Lint",
            "",
            "- status: failed",
            "- p0_count: 1",
            "",
            "| Severity | Code | Location | Snippet | Suggestion |",
            "|---|---|---|---|---|",
            "| P0 | sell_side_voice_violation | paragraph 1 | Confirm before funding | Rewrite buyer-side diligence wording. |",
        ]),
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_quality_gate",
        stage="Memo failed quality gate",
        failure_phase="quality_gate",
        failure_detail="Generated memo failed the DOCX quality gate",
        artifacts_available=True,
        memo_quality_lint={"p0_count": 1, "finding_count": 1},
    )

    stored = storage.get_report(report["id"])
    summary = api._report_summary(stored)
    detail = api._report_detail(stored)
    assert summary["resume_available"] is True
    assert detail["resume_available"] is True
    storage.update_report(
        report["id"],
        status="analyzing",
        stage="Resume queued",
        progress=98,
        resume_from_status="failed_quality_gate",
        resume_from_failure_phase="quality_gate",
        resume_from_failure_detail="Generated memo failed the DOCX quality gate",
        failure_phase=None,
        failure_detail=None,
    )

    def fake_resume_package(**kwargs):
        assert not package_path.exists()
        archives = list((run_dir / "logs").glob("memo_package.quality_failed.*.json"))
        assert archives
        assert kwargs["quality_lint_path"] == quality_lint_path
        assert kwargs["prior_package_path"] == archives[0]
        _write_memo_package(run_dir)
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=0.5,
            duration_ms=500,
        )
        return {"ok": True, "cost_usd": 0.5, "duration_ms": 500, "resumed": True}

    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        fake_resume_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **kwargs: (
            _write_internal_memo_markdown(kwargs["internal_markdown_path"])
            or {"ok": True, "cost_usd": 0.25, "duration_ms": 250}
        ),
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda docx_path, pdf_path: (pdf_path.write_bytes(b"%PDF-1.4\n") or True, None),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["stage"] == "Memo ready"
    assert updated["failure_phase"] is None
    events = _events(memo_prep.stream_path(run_dir))
    assert any(
        event.get("stage") == "resume_package_quality_failed"
        for event in events
    )
    assert not any(
        event.get("stage") == "resume_package_reuse"
        for event in events
    )
    assert events[-1]["type"] == "done"


def test_resume_memo_endpoint_queues_failed_report(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n",
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Claude skill run failed",
        failure_phase="analysis",
        failure_detail="Failed to authenticate. API Error: 403 Request not allowed",
    )
    called = []
    monkeypatch.setattr(
        memo_analysis,
        "start_resume",
        lambda report_id: called.append(report_id),
    )

    response = api.resume_memo_report(report["id"])

    assert called == [report["id"]]
    assert response.status == "analyzing"
    assert response.stage == "Resume queued"
    queued = storage.get_report(report["id"])
    assert queued["resume_from_status"] == "failed_during_analysis"
    assert queued["resume_from_failure_phase"] == "analysis"
    assert (
        queued["resume_from_failure_detail"]
        == "Failed to authenticate. API Error: 403 Request not allowed"
    )


def test_resume_memo_endpoint_preserves_original_resume_source(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n",
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Memo resume failed",
        failure_phase="resume",
        failure_detail="API Error: socket closed",
        resume_from_status="failed_quality_gate",
        resume_from_failure_phase="quality_gate",
        resume_from_failure_detail="Generated memo failed quality gate",
    )
    called = []
    monkeypatch.setattr(
        memo_analysis,
        "start_resume",
        lambda report_id: called.append(report_id),
    )

    response = api.resume_memo_report(report["id"])

    assert called == [report["id"]]
    assert response.status == "analyzing"
    queued = storage.get_report(report["id"])
    assert queued["resume_from_status"] == "failed_quality_gate"
    assert queued["resume_from_failure_phase"] == "quality_gate"
    assert queued["resume_from_failure_detail"] == "Generated memo failed quality gate"


def test_resume_continues_from_quality_failed_archive_after_transport_error(
    memo_env, monkeypatch
):
    report, run_dir = _make_memo_report(memo_env)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "pressure_tests.md").write_text(
        "# Pressure tests\n\nCompleted before transport failure.\n",
        encoding="utf-8",
    )
    original_package = _write_memo_package(
        run_dir,
        body_en="Confirm before funding: buyer-side checkpoint language.",
    )
    archived_package = original_package.with_name(
        "memo_package.quality_failed.20260623T114731Z.json"
    )
    original_package.replace(archived_package)
    quality_lint_path = run_dir / "logs" / "memo_quality_lint.md"
    quality_lint_path.write_text(
        "# Memo Quality Lint\n\nP0 sell_side_voice_violation\n",
        encoding="utf-8",
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Memo resume failed",
        failure_phase="resume",
        failure_detail="API Error: socket closed",
        artifacts_available=True,
    )

    def fake_resume_package(**kwargs):
        assert kwargs["quality_lint_path"] == quality_lint_path
        assert kwargs["prior_package_path"] == archived_package
        _write_memo_package(run_dir)
        kwargs["progress"].emit(
            "claude_action",
            action="result",
            subtype="success",
            cost_usd=0.5,
            duration_ms=500,
        )
        return {"ok": True, "cost_usd": 0.5, "duration_ms": 500, "resumed": True}

    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        fake_resume_package,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_internal_diligence_memo",
        lambda **kwargs: (
            _write_internal_memo_markdown(kwargs["internal_markdown_path"])
            or {"ok": True, "cost_usd": 0.25, "duration_ms": 250}
        ),
    )
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda docx_path, pdf_path: (pdf_path.write_bytes(b"%PDF-1.4\n") or True, None),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    events = _events(memo_prep.stream_path(run_dir))
    assert any(
        event.get("stage") == "resume_package_quality_failed_continue"
        for event in events
    )
    assert not any(
        event.get("stage") == "resume_package_reuse"
        for event in events
    )


def test_memo_run_fails_closed_when_docx_quality_gate_finds_p0(
    memo_env, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_RENDER_PDF_PREVIEWS", "1")
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
    assert updated["renderer_contract"]["errors"] == []

    summary = api._report_summary(updated)
    assert summary["artifacts_available"] is True
    assert summary["memo_quality_lint"]["p0_count"] >= 1
    assert summary["download_urls"]["en"].endswith("language=en")
    detail = api._report_detail(updated)
    assert detail["artifacts_available"] is True
    assert detail["memo_quality_lint"]["p0_count"] >= 1
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


def test_recover_stale_memo_report_repairs_failed_record_when_stream_done(
    memo_env,
):
    report, run_dir = _make_memo_report(memo_env)
    package_path = _write_memo_package(run_dir)
    memo_paths_abs = memo_analysis._memo_paths_abs(report)
    memo_analysis.memo_docx_renderer.render_memos(
        package_path,
        out_en=memo_paths_abs["en"],
        out_zh=memo_paths_abs["zh"],
        manifest_path=run_dir / "logs" / "run_manifest.md",
        inventory_path=run_dir / "logs" / "file_inventory.md",
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=True)
    stream.emit(
        "job_init",
        kind="memo",
        title="Resume investment memo - Generalist, Inc.",
        report_id=report["id"],
        company_id="generalist-inc",
        run_id=report["run_id"],
        resumed=True,
    )
    stream.emit(
        "done",
        report_id=report["id"],
        memo_paths={k: str(v) for k, v in memo_paths_abs.items()},
        cost_usd=2.25,
        duration_ms=111000,
        recovered=True,
    )
    storage.update_report(
        report["id"],
        status="failed_during_analysis",
        stage="Memo resume failed",
        error="API Error: The socket connection was closed unexpectedly.",
        failure_phase="resume",
        failure_detail="API Error: The socket connection was closed unexpectedly.",
        artifacts_available=False,
    )

    recovered = memo_analysis.recover_stale_reports()

    assert recovered == 1
    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["stage"] == "Memo ready"
    assert updated["error"] is None
    assert updated["failure_phase"] is None
    assert updated["artifacts_available"] is True
    assert updated["claude_cost_usd"] == 2.25
    assert updated["claude_duration_ms"] == 111000
    assert updated["memo_quality_lint"]["p0_count"] == 0
    assert updated["memo_chinese_parity"]["p0_count"] == 0
    assert all(
        item["exists"]
        for item in updated["renderer_contract"]["expected_files"]
    )

    events = _events(memo_prep.stream_path(run_dir))
    assert sum(1 for event in events if event.get("type") == "done") == 1


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


def test_active_memo_job_includes_not_started_phase_rows(memo_env):
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
                    "type": "thread_planned",
                    "ts": ts(1),
                    "thread": "Phase 1 - Intake and setup",
                    "title": "Phase 1 - Intake and setup",
                    "phase_index": 1,
                    "estimate_ms": 150000,
                    "description": "Setup usually takes about 2m 30s.",
                },
                {
                    "type": "thread_planned",
                    "ts": ts(2),
                    "thread": "Phase 2 - Parallel analysis passes",
                    "title": "Phase 2 - Parallel analysis passes",
                    "phase_index": 2,
                },
                {
                    "type": "thread_started",
                    "ts": ts(3),
                    "thread": "Phase 1 - Intake and setup",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state = api._scan_progress_state(stream_path)

    assert state["thread_count"] == 2
    assert state["open_thread_count"] == 1
    phase1 = next(
        thread for thread in state["threads"]
        if thread["name"] == "Phase 1 - Intake and setup"
    )
    phase2 = next(
        thread for thread in state["threads"]
        if thread["name"] == "Phase 2 - Parallel analysis passes"
    )
    assert phase1["status"] == "running"
    assert phase1["estimate_ms"] == 150000
    assert phase1["event_count"] == 1
    assert phase2["status"] == "not_started"
    assert phase2["event_count"] == 0
    assert phase2["started_at"] is None
