from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import (
    claude_runner,
    job_progress,
    memo_analysis,
    memo_prep,
    research_store,
    serena_analysis,
    storage,
)
from server.main import app


def _seed_company(tmp_path, monkeypatch, company: dict) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(serena_analysis, "ANALYSIS_ROOT", tmp_path / "serena_analysis")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    monkeypatch.setattr(memo_prep, "DATA_DIR", tmp_path)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", tmp_path / "memos")
    monkeypatch.setattr(
        memo_prep,
        "SETTINGS_FILE",
        tmp_path / "settings" / "serena_background.md",
    )
    monkeypatch.setattr(memo_prep, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(
        claude_runner,
        "run_serena_strategic_risk_mapper",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_thesis_spine_builder",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_private_benchmark_dashboard",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_infographic_source_brief",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_chart_spec_builder",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_narrative_hooks",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_memo_grader",
        lambda **kwargs: (None, "Claude disabled in test"),
    )
    memo_prep.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    memo_prep.SETTINGS_FILE.write_text("Serena background settings\n", encoding="utf-8")
    storage._write_yaml(storage.COMPANIES_FILE, [company])


def _wait_for_task_status(
    company_id: str,
    task_id: str,
    status: str,
    *,
    timeout: float = 3.0,
) -> dict:
    deadline = time.time() + timeout
    last_session = None
    while time.time() < deadline:
        last_session = serena_analysis.get_current_session(company_id)
        tasks = (
            last_session.get("artifacts", {})
            .get("research_tasks", {})
            .get("tasks", [])
        )
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if task and task.get("status") == status:
            return last_session
        time.sleep(0.02)
    assert last_session is not None
    tasks = (
        last_session.get("artifacts", {})
        .get("research_tasks", {})
        .get("tasks", [])
    )
    task = next((t for t in tasks if t.get("id") == task_id), None)
    assert task and task.get("status") == status
    return last_session


def _wait_for_tool_status(
    company_id: str,
    tool_name: str,
    status: str,
    *,
    timeout: float = 3.0,
) -> dict:
    deadline = time.time() + timeout
    last_session = None
    while time.time() < deadline:
        last_session = serena_analysis.get_current_session(company_id)
        tools = {
            tool.get("name"): tool
            for tool in last_session.get("tools", [])
            if isinstance(tool, dict)
        }
        if tools.get(tool_name, {}).get("status") == status:
            return last_session
        time.sleep(0.02)
    assert last_session is not None
    tools = {
        tool.get("name"): tool
        for tool in last_session.get("tools", [])
        if isinstance(tool, dict)
    }
    assert tools.get(tool_name, {}).get("status") == status
    return last_session


def _post_tool(client: TestClient, company_id: str, tool_name: str) -> dict:
    response = client.post(
        f"/api/companies/{company_id}/memo-analysis/tools/{tool_name}/run"
    )
    if serena_analysis.tool_uses_background_job(tool_name):
        assert response.status_code == 202, response.text
        return _wait_for_tool_status(company_id, tool_name, "done")
    assert response.status_code == 200, response.text
    return response.json()


def _run_approval_required_tools(client: TestClient, company_id: str) -> dict:
    session = None
    for tool in (
        "strategic_risk_mapper",
        "priority_prompt_harness",
        "thesis_spine_builder",
    ):
        current = serena_analysis.get_current_session(company_id)
        tool_statuses = {
            row.get("name"): row.get("status")
            for row in current.get("tools", [])
            if isinstance(row, dict)
        }
        if tool_statuses.get(tool) == "done":
            session = current
            continue
        session = _post_tool(client, company_id, tool)
    assert session is not None
    return session


def _waive_additional_areas(
    company_id: str,
    *,
    rationale: str = "Reviewed by Serena.",
) -> dict:
    session = serena_analysis.get_current_session(company_id)
    items = [
        {
            "id": area["id"],
            "status": "waived",
            "rationale": rationale,
        }
        for area in session.get("additional_areas") or []
        if area.get("id")
    ]
    if not items:
        return session
    return serena_analysis.patch_artifact(
        company_id,
        "readiness_reviews",
        {"items": items},
    )


def _create_completed_memo_report(company_id: str, tmp_path) -> dict:
    run_dir = tmp_path / "memos" / company_id / "run-1"
    memo_dir = run_dir / "memo"
    memo_dir.mkdir(parents=True, exist_ok=True)
    (memo_dir / "memo-en.docx").write_bytes(b"docx")
    (memo_dir / "memo-zh.docx").write_bytes(b"docx")
    report = storage.create_report(
        company_id=company_id,
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
    )
    return storage.update_report(
        report["id"],
        kind="investment_memo_latestage",
        status="complete",
        stage="Memo ready",
        progress=100,
        run_id="run-1",
        run_dir=str(run_dir.relative_to(tmp_path.parent)),
        memo_files=[
            {
                "language": "en",
                "path": str((memo_dir / "memo-en.docx").relative_to(tmp_path.parent)),
            },
            {
                "language": "zh",
                "path": str((memo_dir / "memo-zh.docx").relative_to(tmp_path.parent)),
            },
        ],
    )


def _events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _iso_seconds_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def test_strategic_risk_mapper_generates_humanoid_specific_risks(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots for embodied AI tasks.",
            "products": [{"name": "Humanoid platform"}],
        },
    )

    session = serena_analysis.run_tool("generalist", "strategic_risk_mapper")

    risks = session["artifacts"]["strategic_risks"]["risks"]
    titles = [r["title"] for r in risks]
    assert "Is the humanoid embodiment actually the right market abstraction?" in titles
    assert "Can they achieve economically viable deployment at scale?" in titles
    assert "Can they build a durable intelligence advantage?" in titles
    assert session["tools"][0]["status"] == "done"
    assert session["readiness"]["score"] >= 1


def test_memo_analysis_strategic_risk_job_persists_claude_result(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    claude_risks = [
        {
            "title": f"Claude risk {i}",
            "decision_question": f"Can Generalist prove risk {i}?",
            "why_it_matters": "It can change the investment recommendation.",
            "bull_case_answer": "Independent evidence supports the risk being manageable.",
            "bear_case_answer": "The deal depends on unproven assumptions.",
            "evidence_needed": ["Customer evidence", "Unit economics"],
            "best_sources": ["Serena research folder", "public sources"],
            "research_prompt": f"Research Claude risk {i}.",
            "memo_section": "Investment Risk",
            "status": "unresearched",
        }
        for i in range(1, 6)
    ]
    monkeypatch.setattr(
        claude_runner,
        "run_serena_strategic_risk_mapper",
        lambda **kwargs: (
            {
                "risks": claude_risks,
                "source_basis": {"claude_sources_checked": ["Serena research folder"]},
            },
            None,
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/strategic_risk_mapper/run"
    )
    assert response.status_code == 202, response.text

    session = _wait_for_tool_status("generalist", "strategic_risk_mapper", "done")
    artifact = session["artifacts"]["strategic_risks"]
    assert artifact["generated_by"] == "claude_code"
    assert artifact["risks"][0]["id"] == "risk-1"
    assert artifact["risks"][0]["title"] == "Claude risk 1"
    assert artifact["source_basis"]["claude_sources_checked"] == [
        "Serena research folder"
    ]
    tool = next(t for t in session["tools"] if t["name"] == "strategic_risk_mapper")
    assert tool["error"] is None
    assert "with Claude" in tool["summary"]


def test_memo_analysis_strategic_risk_job_preserves_previous_artifact_on_error(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "strategic_risk_mapper")
    previous = copy.deepcopy(initial["artifacts"]["strategic_risks"])
    monkeypatch.setattr(
        claude_runner,
        "run_serena_strategic_risk_mapper",
        lambda **kwargs: (None, "Claude failed after prior good artifact"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/strategic_risk_mapper/run"
    )
    assert response.status_code == 202, response.text

    session = _wait_for_tool_status("generalist", "strategic_risk_mapper", "error")
    assert session["artifacts"]["strategic_risks"] == previous
    tool = next(t for t in session["tools"] if t["name"] == "strategic_risk_mapper")
    assert tool["error"] == "Claude failed after prior good artifact"
    assert "Claude strategic risk mapper failed" in tool["summary"]


def test_memo_analysis_thesis_spine_job_persists_claude_result_and_context(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "competitors": ["Tesla", "Boston Dynamics"],
        },
    )
    for tool in (
        "strategic_risk_mapper",
        "priority_prompt_harness",
        "chart_spec_builder",
        "private_benchmark_dashboard",
    ):
        serena_analysis.run_tool("generalist", tool)
    serena_analysis.run_research_task("generalist", "task-1")

    captured = {}

    def fake_thesis_runner(**kwargs):
        captured.update(kwargs)
        return (
            {
                "investment_highlights": [
                    {
                        "claim": f"Claude highlight {i}",
                        "detail": "Source-backed upside still needs final validation.",
                        "state": "upside_state",
                        "source_trace": [
                            "strategic_risks",
                            "research_tasks",
                            "benchmark_dashboard",
                        ],
                        "needs_stronger_evidence": i == 3,
                    }
                    for i in range(1, 4)
                ],
                "investment_risks": [
                    {
                        "claim": f"Claude memo risk {i}",
                        "detail": "This can change the BSH recommendation.",
                        "source_trace": ["strategic_risks", "chart_specs"],
                        "needs_stronger_evidence": True,
                    }
                    for i in range(1, 4)
                ],
                "recommendation_logic": (
                    "Proceed only if deployment depth and valuation support "
                    "survive independent checks."
                ),
                "top_gating_questions": [
                    {
                        "question": f"Claude gate {i}?",
                        "why_it_matters": "It controls recommendation quality.",
                        "evidence_needed": ["Independent customer evidence"],
                    }
                    for i in range(1, 4)
                ],
                "bull_case_must_be_true": [
                    "Deployment depth is repeatable.",
                    "Revenue quality supports valuation.",
                    "Public comps are economically relevant.",
                ],
                "pass_triggers": [
                    "No independent deployment support.",
                    "Weak revenue quality.",
                    "Inappropriate comp set.",
                ],
                "source_basis": {"claude_sources_checked": ["memo studio artifacts"]},
            },
            None,
        )

    monkeypatch.setattr(
        claude_runner,
        "run_serena_thesis_spine_builder",
        fake_thesis_runner,
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/thesis_spine_builder/run"
    )
    assert response.status_code == 202, response.text

    session = _wait_for_tool_status("generalist", "thesis_spine_builder", "done")
    artifact = session["artifacts"]["thesis_spine"]
    assert artifact["generated_by"] == "claude_code"
    assert artifact["investment_highlights"][0]["id"] == "highlight-1"
    assert artifact["investment_highlights"][0]["claim"] == "Claude highlight 1"
    assert artifact["investment_risks"][0]["id"] == "memo-risk-1"
    assert artifact["top_gating_questions"][0]["id"] == "gate-1"
    assert artifact["source_basis"]["claude_sources_checked"] == [
        "memo studio artifacts"
    ]
    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Claude highlight 1" in packet
    assert "Use this packet as evidence, not copy" in packet
    assert "Memo Spine For Final Draft" in packet
    assert "partner-level conclusions" in packet
    assert "Use first-person sponsor voice" in packet
    assert "the recommendation is" in packet

    context = captured["artifacts"]
    assert context["strategic_risks"]["risks"]
    assert context["risk_priorities"]["priorities"]
    assert context["research_tasks"]["tasks"][0]["result_summary"]
    assert context["chart_specs"]["specs"]
    assert context["benchmark_dashboard"]["public_comps"]
    assert captured["research_dir"] == research_store.RESEARCH_ROOT / "generalist"
    tool = next(t for t in session["tools"] if t["name"] == "thesis_spine_builder")
    assert tool["error"] is None
    assert "with Claude" in tool["summary"]


def test_memo_analysis_thesis_spine_job_preserves_previous_artifact_on_error(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "thesis_spine_builder")
    previous = copy.deepcopy(initial["artifacts"]["thesis_spine"])
    monkeypatch.setattr(
        claude_runner,
        "run_serena_thesis_spine_builder",
        lambda **kwargs: (None, "Claude failed after prior thesis"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/thesis_spine_builder/run"
    )
    assert response.status_code == 202, response.text

    session = _wait_for_tool_status("generalist", "thesis_spine_builder", "error")
    assert session["artifacts"]["thesis_spine"] == previous
    tool = next(t for t in session["tools"] if t["name"] == "thesis_spine_builder")
    assert tool["error"] == "Claude failed after prior thesis"
    assert "Claude thesis spine builder failed" in tool["summary"]


def test_memo_analysis_thesis_spine_job_falls_back_on_first_run_error(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_thesis_spine_builder",
        lambda **kwargs: (None, "Claude unavailable for thesis"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/thesis_spine_builder/run"
    )
    assert response.status_code == 202, response.text

    session = _wait_for_tool_status("generalist", "thesis_spine_builder", "done")
    artifact = session["artifacts"]["thesis_spine"]
    assert artifact["generated_by"] == "deterministic_fallback"
    assert artifact["claude_error"] == "Claude unavailable for thesis"
    assert artifact["investment_highlights"]
    assert session["artifacts"]["strategic_risks"]["risks"]
    tool = next(t for t in session["tools"] if t["name"] == "thesis_spine_builder")
    assert "Claude thesis spine fallback" in tool["error"]
    assert "Investment Highlights" in (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")


def test_memo_analysis_benchmark_job_persists_claude_result_and_packet(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "competitors": ["Tesla", "Rockwell"],
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_private_benchmark_dashboard",
        lambda **kwargs: (
            {
                "summary": "Public comps show premium robotics valuations need proof.",
                "public_comps": [
                    {
                        "company": "Rockwell Automation",
                        "ticker": "ROK",
                        "why_relevant": "Industrial automation comp.",
                        "revenue_growth_pct": "8.5%",
                        "gross_margin_pct": 41.2,
                        "ev_revenue": 4.3,
                        "ev_ebitda": 18.5,
                        "fcf_margin_pct": 16.1,
                        "rule_of_40": 24.6,
                        "metric_period": "FY2026E",
                        "sell_side_theme": "Automation demand is cyclical.",
                        "source_traces": [
                            {
                                "title": "ROK 10-K",
                                "url": "https://example.com/rok",
                                "locator": "FY2025 10-K",
                                "excerpt": "Industrial automation demand remained mixed.",
                                "confidence": "high",
                            }
                        ],
                        "confidence": "high",
                    },
                    {
                        "company": "Teradyne",
                        "ticker": "TER",
                        "why_relevant": "Automation and robotics exposure.",
                        "revenue_growth_pct": 6.0,
                        "gross_margin_pct": 58.0,
                        "ev_revenue": 5.1,
                        "ev_ebitda": 20.0,
                        "fcf_margin_pct": 18.0,
                        "rule_of_40": 24.0,
                        "metric_period": "FY2026E",
                        "sell_side_theme": "Robotics is still early.",
                        "source_traces": [],
                        "confidence": "medium",
                    },
                    {
                        "company": "Intuitive Surgical",
                        "ticker": "ISRG",
                        "why_relevant": "High-quality robotics model.",
                        "revenue_growth_pct": 14.0,
                        "gross_margin_pct": 67.0,
                        "ev_revenue": 15.0,
                        "ev_ebitda": 38.0,
                        "fcf_margin_pct": 28.0,
                        "rule_of_40": 42.0,
                        "metric_period": "FY2026E",
                        "sell_side_theme": "Procedure volume drives durability.",
                        "source_traces": [],
                        "confidence": "medium",
                    },
                ],
                "benchmark_gaps": ["Need private ARR scale and customer depth."],
                "must_prove": ["Deployment depth deserves public-comp treatment."],
                "source_traces": [
                    {
                        "title": "Robotics comp note",
                        "url": "https://example.com/note",
                        "locator": "summary",
                        "excerpt": "Investors reward durable robotics revenue.",
                        "confidence": "medium",
                    }
                ],
                "confidence": "medium",
            },
            None,
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/private_benchmark_dashboard/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status(
        "generalist",
        "private_benchmark_dashboard",
        "done",
    )
    artifact = session["artifacts"]["benchmark_dashboard"]

    assert artifact["generated_by"] == "claude_code"
    assert artifact["public_comps"][0]["id"] == "comp-1"
    assert artifact["public_comps"][0]["revenue_growth_pct"] == 8.5
    assert artifact["public_comps"][0]["ev_ebitda"] == 18.5
    assert artifact["public_comps"][0]["source_traces"][0]["confidence"] == "high"
    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Private Benchmark Dashboard" in packet
    assert "Rockwell Automation" in packet
    assert "18.5" in packet
    assert "Need private ARR scale" in packet
    assert "Investors reward durable robotics revenue" in packet


def test_memo_analysis_benchmark_job_preserves_previous_artifact_on_error(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "private_benchmark_dashboard")
    previous = copy.deepcopy(initial["artifacts"]["benchmark_dashboard"])
    monkeypatch.setattr(
        claude_runner,
        "run_serena_private_benchmark_dashboard",
        lambda **kwargs: (None, "Claude benchmark failed"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/private_benchmark_dashboard/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status(
        "generalist",
        "private_benchmark_dashboard",
        "error",
    )

    assert session["artifacts"]["benchmark_dashboard"] == previous
    tool = next(
        item for item in session["tools"]
        if item["name"] == "private_benchmark_dashboard"
    )
    assert tool["error"] == "Claude benchmark failed"
    assert "Claude benchmark dashboard failed" in tool["summary"]


def test_memo_analysis_benchmark_job_first_run_uses_deterministic_fallback(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_private_benchmark_dashboard",
        lambda **kwargs: (None, "Claude unavailable"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/private_benchmark_dashboard/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status(
        "generalist",
        "private_benchmark_dashboard",
        "done",
    )
    artifact = session["artifacts"]["benchmark_dashboard"]

    assert artifact["generated_by"] == "deterministic_fallback"
    assert artifact["claude_error"] == "Claude unavailable"
    assert artifact["public_comps"]
    tool = next(
        item for item in session["tools"]
        if item["name"] == "private_benchmark_dashboard"
    )
    assert "Claude benchmark fallback" in tool["error"]


def test_memo_analysis_infographic_source_brief_job_persists_claude_result_and_packet(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_infographic_source_brief",
        lambda **kwargs: (
            {
                "summary": "Use only source-backed deployment claims for visuals.",
                "compact_claims": [
                    {
                        "id": "claim-deployment",
                        "claim": "Deployment evidence is limited to pilots.",
                        "evidence_status": "partial",
                        "source_traces": [
                            {
                                "title": "Customer note",
                                "url": None,
                                "locator": "customer-note.md",
                                "excerpt": "Only pilots were confirmed.",
                                "confidence": "high",
                            }
                        ],
                        "contradictions": [],
                        "warnings": ["Do not imply contracted ARR."],
                        "prohibited_for_visuals": False,
                        "confidence": "high",
                    }
                ],
                "numeric_metrics": [
                    {
                        "id": "metric-pilots",
                        "label": "Confirmed pilots",
                        "value": 3,
                        "unit": "customers",
                        "period": "2026",
                        "calculation": "Count of named pilots.",
                        "denominator_note": "Not production customers.",
                        "source_traces": [],
                        "confidence": "medium",
                    }
                ],
                "source_traces": [],
                "contradictions": ["ARR claim is not sourced."],
                "missing_evidence": ["Contracted ARR by customer."],
                "no_go_claims": ["Do not visualize pilots as production adoption."],
                "visual_opportunities": [
                    {
                        "id": "visual-adoption",
                        "title": "Pilot-to-production ladder",
                        "rationale": "Separates pilots from production.",
                        "paired_claim_ids": ["claim-deployment"],
                        "source_trace_ids": [],
                        "confidence": "medium",
                    }
                ],
                "narrative_opportunities": [],
                "reviewer_prompts": [
                    {
                        "id": "prompt-mode",
                        "prompt": "Should the adoption ladder use generated text?",
                        "required": True,
                        "options": ["no_text_overlay", "text_in_image"],
                        "resolved_choice": None,
                        "rationale": "",
                        "status": "needs_review",
                    }
                ],
                "confidence": "medium",
            },
            None,
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/infographic_source_brief/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status(
        "generalist",
        "infographic_source_brief",
        "done",
    )
    brief = session["artifacts"]["infographic_source_brief"]

    assert brief["generated_by"] == "claude_code"
    assert brief["compact_claims"][0]["source_traces"][0]["confidence"] == "high"
    assert brief["reviewer_prompts"][0]["status"] == "needs_review"
    assert not any(
        area["id"].startswith("source-brief-choice-")
        for area in session["additional_areas"]
    )
    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Infographic Source Brief" in packet
    assert "Only pilots were confirmed" in packet
    assert "Do not visualize pilots as production adoption" in packet


def test_memo_analysis_infographic_source_brief_preserves_previous_on_error(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "infographic_source_brief")
    previous = copy.deepcopy(initial["artifacts"]["infographic_source_brief"])
    monkeypatch.setattr(
        claude_runner,
        "run_serena_infographic_source_brief",
        lambda **kwargs: (None, "Claude source brief failed"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/infographic_source_brief/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status(
        "generalist",
        "infographic_source_brief",
        "error",
    )

    assert session["artifacts"]["infographic_source_brief"] == previous
    tool = next(
        item for item in session["tools"]
        if item["name"] == "infographic_source_brief"
    )
    assert tool["error"] == "Claude source brief failed"


def test_memo_analysis_chart_spec_job_preserves_manual_state_and_prompts(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "chart_spec_builder")
    chart = copy.deepcopy(initial["artifacts"]["chart_specs"])
    chart["specs"][0]["include_in_final_memo"] = False
    chart["specs"][0]["manual_notes"] = "Serena excluded this visual."
    serena_analysis.patch_artifact("generalist", "chart_specs", chart)
    monkeypatch.setattr(
        claude_runner,
        "run_serena_chart_spec_builder",
        lambda **kwargs: (
            {
                "summary": "Infographic plans from source brief.",
                "generated_from_brief_id": "infographic_source_brief",
                "specs": [
                    {
                        "id": chart["specs"][0]["id"],
                        "title": chart["specs"][0]["title"],
                        "purpose": "Show why growth quality needs proof.",
                        "takeaway": "Growth bridge remains incomplete.",
                        "recommended_visual_format": "bridge infographic",
                        "alternate_formats": ["table"],
                        "image_generation_mode": "needs_human_choice",
                        "text_overlay_plan": {
                            "headline": "Growth quality still needs proof",
                            "labels": ["Starting ARR", "Latest ARR"],
                            "callouts": ["Separate pilots from production"],
                            "footnotes": ["Source needed for ARR bridge."],
                            "safe_copy_length": "Headline under 60 characters.",
                        },
                        "required_metrics": [
                            {
                                "id": "metric-arr",
                                "label": "Latest ARR",
                                "value": None,
                                "unit": "USD",
                                "period": None,
                                "calculation": "",
                                "denominator_note": "ARR definition required.",
                                "source_available": False,
                                "source_traces": [],
                                "confidence": "low",
                            }
                        ],
                        "source_availability": "missing",
                        "source_traces": [
                            {
                                "title": "Memo note",
                                "url": None,
                                "locator": "memo",
                                "excerpt": "ARR bridge is not sourced.",
                                "confidence": "medium",
                            }
                        ],
                        "information_gaps": ["ARR bridge."],
                        "data_payload": [],
                        "design_prompt": {
                            "composition": "Use a clean bridge composition.",
                            "visual_metaphor": "bridge",
                            "style_constraints": ["restrained"],
                            "aspect_ratio": "16:9",
                            "prohibited_claims": ["Do not imply sourced ARR."],
                        },
                        "owner": "Serena",
                        "diligence_needed": ["ARR source."],
                        "memo_section_placement": "Investment Highlights",
                        "include_in_final_memo": True,
                        "final_memo_inclusion_state": "needs_review",
                        "reviewer_prompts": [
                            {
                                "id": "prompt-mode",
                                "prompt": "Choose overlay or text-in-image.",
                                "required": True,
                                "options": ["no_text_overlay", "text_in_image"],
                                "resolved_choice": None,
                                "rationale": "",
                                "status": "needs_review",
                            }
                        ],
                        "status": "needs_review",
                        "confidence": "medium",
                    },
                    {
                        "id": "chart-deployment-proof",
                        "title": "Deployment proof ladder",
                        "purpose": "Separate pilots from production adoption.",
                        "takeaway": "Production evidence needs explicit sourcing.",
                        "recommended_visual_format": "ladder infographic",
                        "alternate_formats": [],
                        "image_generation_mode": "no_text_overlay",
                        "text_overlay_plan": {
                            "headline": "Pilots are not production",
                            "labels": ["Pilot", "Production"],
                            "callouts": ["Evidence gap remains"],
                            "footnotes": [],
                            "safe_copy_length": "Short overlay copy.",
                        },
                        "required_metrics": [],
                        "source_availability": "partial",
                        "source_traces": [
                            {
                                "title": "Customer note",
                                "url": None,
                                "locator": "customer-note.md",
                                "excerpt": "Production adoption is not yet sourced.",
                                "confidence": "medium",
                            }
                        ],
                        "information_gaps": [],
                        "data_payload": [],
                        "design_prompt": {
                            "composition": "Use a simple adoption ladder.",
                            "visual_metaphor": "ladder",
                            "style_constraints": ["clean"],
                            "aspect_ratio": "16:9",
                            "prohibited_claims": [],
                        },
                        "owner": "Serena",
                        "diligence_needed": [],
                        "memo_section_placement": "Investment Highlights",
                        "include_in_final_memo": True,
                        "final_memo_inclusion_state": "include",
                        "reviewer_prompts": [],
                        "status": "draft",
                        "confidence": "medium",
                    }
                ],
                "reviewer_prompts": [],
                "confidence": "medium",
            },
            None,
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/chart_spec_builder/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status("generalist", "chart_spec_builder", "done")
    charts = session["artifacts"]["chart_specs"]
    spec = charts["specs"][0]

    assert charts["generated_by"] == "claude_code"
    assert spec["include_in_final_memo"] is False
    assert spec["manual_notes"] == "Serena excluded this visual."
    assert spec["reviewer_prompts"][0]["status"] == "needs_review"
    assert not any(
        area["id"].startswith(f"infographic-choice-{spec['id']}")
        for area in session["additional_areas"]
    )
    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Growth quality still needs proof" not in packet
    assert "Deployment proof ladder" in packet
    assert "Production adoption is not yet sourced" in packet


def test_memo_analysis_narrative_job_preserves_selected_ids_and_packet(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    initial = serena_analysis.run_tool("generalist", "narrative_hooks")
    previous = initial["artifacts"]["narrative_hooks"]
    selected_opening = previous["selected_opening_id"]
    selected_ending = previous["selected_ending_id"]
    monkeypatch.setattr(
        claude_runner,
        "run_serena_narrative_hooks",
        lambda **kwargs: (
            {
                "summary": "Source-backed hooks.",
                "generated_from_brief_id": "infographic_source_brief",
                "openings": [
                    {
                        "id": selected_opening,
                        "text": "Start with deployment proof, not category excitement.",
                        "purpose": "opening",
                        "tone": "direct",
                        "supported_claims": ["Deployment proof is incomplete."],
                        "evidence_references": ["infographic_source_brief"],
                        "source_traces": [],
                        "confidence": "medium",
                        "overclaiming_risk": "Do not imply ARR is verified.",
                        "paired_infographic_ids": ["chart-growth-bridge"],
                        "reviewer_prompts": [],
                        "status": "draft",
                    }
                ],
                "transitions": [
                    {
                        "id": "transition-proof",
                        "text": "The diligence burden shifts from story to source-backed proof.",
                        "purpose": "transition",
                        "tone": "evidence_bridge",
                        "supported_claims": ["Evidence gaps remain."],
                        "evidence_references": ["source brief"],
                        "source_traces": [],
                        "confidence": "medium",
                        "overclaiming_risk": "Keep as framing, not fact.",
                        "paired_infographic_ids": [],
                        "reviewer_prompts": [],
                        "status": "draft",
                    }
                ],
                "endings": [
                    {
                        "id": selected_ending,
                        "text": "We would keep the decision conditional until proof arrives.",
                        "purpose": "closing",
                        "tone": "conditional",
                        "supported_claims": ["Gates remain open."],
                        "evidence_references": ["thesis_spine"],
                        "source_traces": [],
                        "confidence": "medium",
                        "overclaiming_risk": "Avoid implying a final pass.",
                        "paired_infographic_ids": [],
                        "reviewer_prompts": [],
                        "status": "draft",
                    }
                ],
                "selected_opening_id": "different-opening",
                "selected_transition_id": "transition-proof",
                "selected_ending_id": "different-ending",
                "reviewer_prompts": [],
                "status": "draft",
                "confidence": "medium",
            },
            None,
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/narrative_hooks/run"
    )
    assert response.status_code == 202, response.text
    session = _wait_for_tool_status("generalist", "narrative_hooks", "done")
    hooks = session["artifacts"]["narrative_hooks"]

    assert hooks["selected_opening_id"] == selected_opening
    assert hooks["selected_ending_id"] == selected_ending
    assert hooks["selected_transition_id"] == "transition-proof"
    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Start with deployment proof" in packet
    assert "diligence burden shifts" in packet
    assert "Do not imply ARR is verified" in packet


def test_memo_analysis_narrative_fallback_creates_operator_choices(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    for tool in (
        "strategic_risk_mapper",
        "priority_prompt_harness",
        "thesis_spine_builder",
        "narrative_hooks",
    ):
        serena_analysis.run_tool("generalist", tool)

    session = serena_analysis.get_current_session("generalist")
    hooks = session["artifacts"]["narrative_hooks"]
    assert len(hooks["openings"]) >= 3
    assert len(hooks["transitions"]) >= 3
    assert len(hooks["endings"]) >= 3
    assert hooks["openings"][0]["purpose"] == "intro stance"
    assert hooks["transitions"][0]["purpose"] == "risk framing"
    assert hooks["endings"][0]["purpose"] == "conclusion posture"
    assert "The memo should" not in hooks["openings"][0]["text"]
    assert "The right posture is" not in hooks["endings"][0]["text"]
    assert hooks["endings"][0]["text"].startswith("We would")
    assert hooks["reviewer_prompts"][0]["id"] == "operator-final-posture"

    packet = (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Selected Operator Narrative Choices" in packet
    assert "Intro stance:" in packet
    assert "Risk-section posture:" in packet
    assert "Conclusion posture:" in packet
    assert "Rewrite any detached phrasing into first-person sponsor voice" in packet


def test_memo_analysis_completed_memo_runs_are_exposed_for_grader(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    report = _create_completed_memo_report("generalist", tmp_path)

    session = serena_analysis.get_current_session("generalist")

    assert session["completed_memo_runs"][0]["id"] == report["id"]
    assert session["completed_memo_runs"][0]["run_id"] == "run-1"


def test_memo_analysis_memo_grader_persists_lessons(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    report = _create_completed_memo_report("generalist", tmp_path)
    session = serena_analysis.get_current_session("generalist")
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    raw["artifacts"]["memo_packet"] = "# Memo Packet\nEvidence quality matters.\n"
    serena_analysis._write_session(raw)
    monkeypatch.setattr(
        claude_runner,
        "run_serena_memo_grader",
        lambda **kwargs: (
            {
                "completed_report_id": report["id"],
                "completed_run_id": report["run_id"],
                "scores": [
                    {
                        "area": "Evidence quality",
                        "score": 8.0,
                        "rationale": "Source discipline was strong.",
                    }
                ],
                "strongest_sections": ["Risk section"],
                "weakest_sections": ["Valuation bridge"],
                "missing_diligence": ["Need customer-level ARR."],
                "rewrite_guidance": ["Tighten the valuation bridge."],
                "lessons_for_future_memo_runs": [
                    "Lead with customer-level evidence before valuation."
                ],
                "source_files_reviewed": ["memo_packet.md"],
                "confidence": "high",
            },
            None,
        ),
    )
    serena_analysis.patch_artifact(
        "generalist",
        "memo_grader",
        {"selected_report_id": report["id"]},
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/memo_grader/run"
    )
    assert response.status_code == 202, response.text
    graded = _wait_for_tool_status("generalist", "memo_grader", "done")
    artifact = graded["artifacts"]["memo_grader"]

    assert artifact["generated_by"] == "claude_code"
    assert artifact["completed_report_id"] == report["id"]
    assert artifact["scores"][0]["score"] == 8.0
    lessons = serena_analysis.memo_lessons_path("generalist").read_text(
        encoding="utf-8"
    )
    assert "Lead with customer-level evidence" in lessons


def test_memo_analysis_memo_grader_preserves_previous_grading_on_error(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    report = _create_completed_memo_report("generalist", tmp_path)
    previous = {
        "status": "graded",
        "completed_report_id": report["id"],
        "completed_run_id": report["run_id"],
        "lessons_for_future_memo_runs": ["Preserve this lesson."],
    }
    session = serena_analysis.get_current_session("generalist")
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    raw["artifacts"]["memo_grader"] = previous
    serena_analysis._write_session(raw)
    monkeypatch.setattr(
        claude_runner,
        "run_serena_memo_grader",
        lambda **kwargs: (None, "Claude grader failed"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/companies/generalist/memo-analysis/tools/memo_grader/run"
    )
    assert response.status_code == 202, response.text
    errored = _wait_for_tool_status("generalist", "memo_grader", "error")

    assert errored["artifacts"]["memo_grader"] == previous
    tool = next(item for item in errored["tools"] if item["name"] == "memo_grader")
    assert tool["error"] == "Claude grader failed"


def test_analysis_session_tracks_readiness_and_approval(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "anduril",
            "name": "Anduril",
            "status": "private",
            "sector": "Defense AI",
            "description": "Defense technology company building autonomous systems.",
            "competitors": ["Lockheed Martin", "Northrop Grumman"],
            "latest_funding": {"round": "Series G", "post_money_usd": "$30B"},
        },
    )

    for tool in (
        "strategic_risk_mapper",
        "priority_prompt_harness",
        "thesis_spine_builder",
        "readiness_check",
    ):
        session = serena_analysis.run_tool("anduril", tool)

    assert session["readiness"]["score"] == session["readiness"]["total"] - 1
    assert session["readiness"]["ready_for_approval"] is True
    assert session["readiness"]["approval_blockers"] == []
    assert session["approved_for_memo"] is False

    approved = serena_analysis.approve("anduril")

    assert approved["approved_for_memo"] is True
    assert approved["readiness"]["ready_for_memo"] is True
    memo_packet = (
        serena_analysis.session_dir("anduril", approved["id"]) / "memo_packet.md"
    )
    assert memo_packet.exists()
    packet_text = memo_packet.read_text(encoding="utf-8")
    assert "Use this packet as evidence, not copy" in packet_text
    assert "Never copy source labels" in packet_text
    assert "Use first-person sponsor voice" in packet_text
    assert "source-class and model-treatment language" in packet_text
    assert "Memo Spine For Final Draft" in packet_text
    assert "**kill_criteria:**" in packet_text
    assert "Investment Highlights" in packet_text


def test_analysis_approval_fails_when_required_gates_are_missing(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )

    with pytest.raises(ValueError, match="Strategic risks generated"):
        serena_analysis.approve("generalist")

    session = serena_analysis.get_current_session("generalist")
    assert session["approved_for_memo"] is False
    assert session["readiness"]["ready_for_approval"] is False


def test_analysis_approval_succeeds_without_optional_visual_work(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "competitors": ["Tesla", "Boston Dynamics"],
            "latest_funding": {"round": "Series G", "post_money_usd": "$5B"},
        },
    )
    client = TestClient(app)
    session = _run_approval_required_tools(client, "generalist")

    assert session["readiness"]["ready_for_approval"] is True
    assert not any(
        blocker["kind"] == "additional_area"
        for blocker in session["readiness"]["approval_blockers"]
    )

    approved = serena_analysis.approve("generalist")
    assert approved["approved_for_memo"] is True
    assert approved["readiness"]["ready_for_memo"] is True


def test_investment_memo_prompt_can_reference_research_and_analysis_dirs(
    tmp_path,
):
    research_dir = tmp_path / "research" / "generalist"
    research_dir.mkdir(parents=True)
    (research_dir / "pitchbook.pdf").write_bytes(b"%PDF-1.4\n")
    analysis_dir = tmp_path / "serena_analysis" / "generalist" / "abc123"
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "memo_packet.md").write_text("# Memo Packet\n", encoding="utf-8")

    prompt = claude_runner._build_investment_memo_prompt(
        run_dir=tmp_path / "run",
        company_name="Generalist",
        company_slug="generalist",
        run_id="2026-06-02__101010",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={
            "en": str(tmp_path / "run" / "memo" / "en.docx"),
            "zh": str(tmp_path / "run" / "memo" / "zh.docx"),
        },
        research_dir=research_dir,
        analysis_session_path=analysis_dir,
    )

    assert str(research_dir) in prompt
    assert str(analysis_dir) in prompt
    assert "memo_packet.md" in prompt
    assert "selected operator narrative choices" in prompt
    assert "operator HIL guidance" in prompt
    assert "DO NOT read from `data/uploads/`" in prompt


def test_memo_analysis_api_runs_tool_and_approves(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)

    initial = client.get("/api/companies/generalist/memo-analysis")
    assert initial.status_code == 200
    assert initial.json()["company_id"] == "generalist"

    run_payload = _post_tool(client, "generalist", "strategic_risk_mapper")
    assert run_payload["artifacts"]["strategic_risks"]["risks"]

    blocked = client.post("/api/companies/generalist/memo-analysis/approve")
    assert blocked.status_code == 400
    assert "Thesis spine drafted" in blocked.json()["detail"]

    _run_approval_required_tools(client, "generalist")
    session = serena_analysis.get_current_session("generalist")
    assert session["readiness"]["ready_for_approval"] is True

    approved = client.post("/api/companies/generalist/memo-analysis/approve")
    assert approved.status_code == 200
    assert approved.json()["approved_for_memo"] is True
    assert approved.json()["readiness"]["ready_for_memo"] is True


def test_memo_analysis_catalog_metadata_preserves_source_boundaries(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    legacy_upload = tmp_path / "uploads" / "generalist" / "legacy-upload.pdf"
    legacy_upload.parent.mkdir(parents=True)
    legacy_upload.write_bytes(b"%PDF-1.4\nlegacy upload")
    source_record = research_store.upload_file(
        "generalist",
        filename="customer-note.txt",
        content_type="text/plain",
        data=b"Customer note",
    )
    client = TestClient(app)

    session = _post_tool(client, "generalist", "strategic_risk_mapper")
    session = _post_tool(client, "generalist", "priority_prompt_harness")
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    task = raw["artifacts"]["research_tasks"]["tasks"][0]
    task.update({
        "status": "done",
        "answer": "Three customers expanded production deployments.",
        "result_summary": "Customer expansion evidence is now source backed.",
        "supporting_evidence": [
            {
                "file_id": source_record["id"],
                "filename": source_record["filename"],
                "locator": "Document",
                "excerpt": "Three customers expanded production deployments.",
                "confidence": "high",
            }
        ],
        "confidence": "high",
        "result_generated_by": "test",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    serena_analysis._refresh_memo_packet(raw)
    serena_analysis._write_session(raw)
    report = _create_completed_memo_report("generalist", tmp_path)

    response = client.get("/api/companies/generalist/memo-analysis/catalog")

    assert response.status_code == 200, response.text
    catalog = response.json()
    work_products = {
        row["artifact_id"]: row
        for row in catalog["work_products"]
    }
    session_id = catalog["session_id"]
    assert work_products[f"analysis_session:{session_id}"]["location"] == (
        f"data/serena_analysis/generalist/{session_id}/"
    )
    assert work_products["strategic_risks"]["artifact_type"] == "risk_map"
    strategy_row = work_products["strategic_risks"]
    assert strategy_row["version"] == 1
    assert strategy_row["version_count"] == 1
    assert strategy_row["version_id"].startswith("strategic_risks:v1:")
    assert len(strategy_row["generated_files"]) == 1
    first_strategy_snapshot = Path(strategy_row["generated_files"][0]["path"])
    assert first_strategy_snapshot.exists()
    assert "Updated strategic risk title" not in first_strategy_snapshot.read_text(
        encoding="utf-8"
    )
    assert work_products["research_tasks"]["version_count"] == 1
    assert work_products["memo_packet"]["export_paths"] == [
        f"data/serena_analysis/generalist/{session_id}/memo_packet.md"
    ]
    packet_row = work_products["memo_packet"]
    assert packet_row["version"] == 1
    assert packet_row["version_count"] == 1
    assert packet_row["version_id"].startswith("memo_packet:v1:")
    first_packet_snapshot = Path(packet_row["generated_files"][0]["path"])
    assert first_packet_snapshot.exists()
    assert "Customer expansion evidence" in first_packet_snapshot.read_text(
        encoding="utf-8"
    )
    task_row = work_products[f"research_task:{task['id']}"]
    assert task_row["source_trace_count"] == 1
    assert task_row["source_refs"][0]["title"] == "customer-note.txt"
    evidence_row = work_products["evidence_matrix:current"]
    assert evidence_row["artifact_type"] == "evidence_matrix"
    assert evidence_row["version"] == 1
    assert evidence_row["version_count"] == 1
    assert evidence_row["version_id"].startswith("evidence_matrix:current:v1:")
    assert evidence_row["export_paths"] == [
        f"data/serena_analysis/generalist/{session_id}/evidence_matrix.json"
    ]
    first_evidence_snapshot = Path(evidence_row["generated_files"][0]["path"])
    assert first_evidence_snapshot.exists()
    first_evidence_payload = json.loads(first_evidence_snapshot.read_text(encoding="utf-8"))
    assert first_evidence_payload["snapshot_type"] == "memo_evidence_matrix"
    assert "generated_at" not in first_evidence_payload
    assert first_evidence_payload["claim_count"] >= 1
    generated_memo = work_products[f"generated_memo:{report['id']}"]
    assert generated_memo["status"] == "published"
    assert generated_memo["version"] == 1
    assert generated_memo["version_count"] == 1
    assert len(generated_memo["generated_files"]) == 2
    assert all(Path(file["path"]).exists() for file in generated_memo["generated_files"])

    raw["artifacts"]["memo_packet"] += "\nSecond packet version.\n"
    raw["artifacts"]["strategic_risks"]["risks"][0]["title"] = (
        "Updated strategic risk title"
    )
    serena_analysis._write_session(raw)
    second_catalog = client.get("/api/companies/generalist/memo-analysis/catalog").json()
    second_products = {
        row["artifact_id"]: row
        for row in second_catalog["work_products"]
    }
    second_packet = second_products["memo_packet"]
    assert second_packet["version"] == 2
    assert second_packet["version_count"] == 2
    assert second_packet["supersedes_version_id"] == packet_row["version_id"]
    assert "Second packet version." not in first_packet_snapshot.read_text(
        encoding="utf-8"
    )
    assert "Second packet version." in Path(
        second_packet["generated_files"][0]["path"]
    ).read_text(encoding="utf-8")
    second_strategy = second_products["strategic_risks"]
    assert second_strategy["version"] == 2
    assert second_strategy["version_count"] == 2
    assert second_strategy["supersedes_version_id"] == strategy_row["version_id"]
    assert "Updated strategic risk title" not in first_strategy_snapshot.read_text(
        encoding="utf-8"
    )
    assert "Updated strategic risk title" in Path(
        second_strategy["generated_files"][0]["path"]
    ).read_text(encoding="utf-8")
    second_evidence = second_products["evidence_matrix:current"]
    assert second_evidence["version"] == 1
    assert second_evidence["version_id"] == evidence_row["version_id"]

    raw["artifacts"]["research_tasks"]["tasks"][0]["answer"] = (
        "Five enterprise deployments are now verified."
    )
    serena_analysis._write_session(raw)
    third_catalog = client.get("/api/companies/generalist/memo-analysis/catalog").json()
    third_evidence = {
        row["artifact_id"]: row
        for row in third_catalog["work_products"]
    }["evidence_matrix:current"]
    assert third_evidence["version"] == 2
    assert third_evidence["version_count"] == 2
    assert third_evidence["supersedes_version_id"] == evidence_row["version_id"]
    assert "Five enterprise deployments" not in first_evidence_snapshot.read_text(
        encoding="utf-8"
    )
    assert "Five enterprise deployments" in Path(
        third_evidence["generated_files"][0]["path"]
    ).read_text(encoding="utf-8")

    boundaries = {
        row["path"]: row
        for row in catalog["source_boundaries"]
    }
    assert boundaries["data/research/generalist/"]["status"] == "included"
    assert boundaries[f"data/serena_analysis/generalist/{session_id}/"]["status"] == (
        "included"
    )
    assert boundaries["data/uploads/generalist/"]["status"] == "excluded"
    assert boundaries["data/stock_research/"]["status"] == "excluded"

    for row in catalog["work_products"]:
        serialized = json.dumps(row)
        assert "data/uploads/generalist" not in serialized
        assert "legacy-upload.pdf" not in serialized


def test_memo_analysis_run_ledger_normalizes_jobs_and_tasks(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    session = _post_tool(client, "generalist", "strategic_risk_mapper")
    session = _post_tool(client, "generalist", "priority_prompt_harness")
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    session_id = raw["id"]
    now = datetime.now(timezone.utc).isoformat()

    raw["artifacts"]["thesis_spine"] = {
        "generated_by": "claude_code",
        "investment_highlights": [{"id": "h1", "claim": "Prior good artifact"}],
    }
    raw["tool_runs"]["thesis_spine_builder"] = {
        "status": "error",
        "last_run_at": now,
        "summary": "Interrupted.",
        "error": "Recovered interrupted run: progress log is missing.",
        "run_job_id": f"generalist/{session_id}/thesis_spine_builder",
    }

    tasks = raw["artifacts"]["research_tasks"]["tasks"]
    done_task = tasks[0]
    done_task.update({
        "status": "done",
        "started_at": now,
        "completed_at": now,
        "last_run_at": now,
        "error": "Claude research fallback: unavailable",
        "run_job_id": f"generalist/{session_id}/{done_task['id']}",
        "result_summary": "Fallback answer.",
        "answer": "Fallback answer.",
        "supporting_evidence": [
            {"title": "Customer note", "excerpt": "Support", "confidence": "high"}
        ],
        "sources_checked": [{"title": "Customer note"}],
        "result_generated_by": "deterministic_fallback",
        "job_metrics": {"duration_ms": 1234},
    })
    cancelled_task = tasks[1]
    cancelled_task.update({
        "status": "cancelled",
        "completed_at": now,
        "last_run_at": now,
        "cancelled_at": now,
        "error": "Research task cancelled",
        "run_job_id": f"generalist/{session_id}/{cancelled_task['id']}",
    })
    recovered_task = tasks[2]
    recovered_task.update({
        "status": "error",
        "completed_at": now,
        "last_run_at": now,
        "error": "Recovered interrupted run: progress log is missing.",
        "result_summary": "Previous answer preserved.",
        "run_job_id": f"generalist/{session_id}/{recovered_task['id']}",
    })
    serena_analysis._refresh_memo_packet(raw)
    serena_analysis._write_session(raw)
    report = _create_completed_memo_report("generalist", tmp_path)

    response = client.get("/api/companies/generalist/memo-analysis/run-ledger")

    assert response.status_code == 200, response.text
    by_id = {row["ledger_id"]: row for row in response.json()}
    priority = by_id[f"memo_tools:generalist:{session_id}:tool:priority_prompt_harness"]
    assert priority["workspace"] == "memo_tools"
    assert priority["job_kind"] == "priority_prompt_harness"
    assert priority["status"] == "done"
    assert priority["fallback_used"] is False

    risk_mapper = by_id[f"memo_tools:generalist:{session_id}:tool:strategic_risk_mapper"]
    assert risk_mapper["fallback_used"] is True
    assert "fallback" in risk_mapper["failure_reason"].lower()

    thesis = by_id[f"memo_tools:generalist:{session_id}:tool:thesis_spine_builder"]
    assert thesis["status"] == "error"
    assert thesis["preserved_previous_artifact"] == "thesis_spine"

    done_row = by_id[
        f"memo_tools:generalist:{session_id}:research_task:{done_task['id']}"
    ]
    assert done_row["duration_ms"] == 1234
    assert done_row["source_count"] == 1
    assert done_row["evidence_coverage"] == 1.0
    assert done_row["fallback_used"] is True

    cancelled_row = by_id[
        f"memo_tools:generalist:{session_id}:research_task:{cancelled_task['id']}"
    ]
    assert cancelled_row["status"] == "cancelled"
    assert cancelled_row["cancellation_reason"] == "Research task cancelled"

    recovered_row = by_id[
        f"memo_tools:generalist:{session_id}:research_task:{recovered_task['id']}"
    ]
    assert recovered_row["status"] == "error"
    assert recovered_row["preserved_previous_artifact"] == (
        f"research_task:{recovered_task['id']}"
    )

    generated = by_id[f"memo_tools:generalist:{session_id}:generated_memo:{report['id']}"]
    assert generated["job_kind"] == "final_memo_generation"
    assert generated["artifact_id"] == f"generated_memo:{report['id']}"
    assert generated["source_count"] == 2


def test_memo_analysis_flags_meaningful_unapproved_work(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)

    initial = client.get("/api/companies/generalist/memo-analysis")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["has_unapproved_work"] is False
    assert initial_payload["regular_memo_warning"] is None
    assert serena_analysis.has_unapproved_work("generalist") is False

    run_payload = _post_tool(client, "generalist", "strategic_risk_mapper")
    assert run_payload["has_unapproved_work"] is True
    assert run_payload["regular_memo_warning"]["code"] == (
        "memo_studio_unapproved_work"
    )
    assert run_payload["regular_memo_warning"]["analysis_session_id"] == (
        run_payload["id"]
    )
    assert serena_analysis.has_unapproved_work("generalist") is True

    blocked = client.post("/api/companies/generalist/memo-analysis/approve")
    assert blocked.status_code == 400
    assert serena_analysis.has_unapproved_work("generalist") is True

    _run_approval_required_tools(client, "generalist")
    approved = client.post("/api/companies/generalist/memo-analysis/approve")
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["has_unapproved_work"] is False
    assert approved_payload["regular_memo_warning"] is None
    assert serena_analysis.has_unapproved_work("generalist") is False


def test_memo_analysis_api_patches_editable_artifacts(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "competitors": ["Tesla", "Boston Dynamics"],
        },
    )
    client = TestClient(app)

    session = None
    for tool in (
        "strategic_risk_mapper",
        "thesis_spine_builder",
        "chart_spec_builder",
        "narrative_hooks",
    ):
        session = _post_tool(client, "generalist", tool)

    assert session is not None
    thesis = session["artifacts"]["thesis_spine"]
    thesis["investment_highlights"][0]["claim"] = "Edited deployment wedge"
    thesis["top_gating_questions"][0]["question"] = "Edited gate question?"

    thesis_response = client.patch(
        "/api/companies/generalist/memo-analysis/artifacts/thesis_spine",
        json={
            "investment_highlights": thesis["investment_highlights"],
            "top_gating_questions": thesis["top_gating_questions"],
        },
    )
    assert thesis_response.status_code == 200
    thesis_payload = thesis_response.json()["artifacts"]["thesis_spine"]
    assert thesis_payload["investment_highlights"][0]["claim"] == (
        "Edited deployment wedge"
    )
    assert thesis_payload["top_gating_questions"][0]["question"] == (
        "Edited gate question?"
    )

    charts = thesis_response.json()["artifacts"]["chart_specs"]["specs"]
    disabled_chart_title = charts[0]["title"]
    charts[0]["include_in_final_memo"] = False
    chart_response = client.patch(
        "/api/companies/generalist/memo-analysis/artifacts/chart_specs",
        json={"specs": charts},
    )
    assert chart_response.status_code == 200
    assert (
        chart_response.json()["artifacts"]["chart_specs"]["specs"][0][
            "include_in_final_memo"
        ]
        is False
    )

    hooks = chart_response.json()["artifacts"]["narrative_hooks"]
    selected_opening = hooks["openings"][1]
    selected_ending = hooks["endings"][2]
    hooks_response = client.patch(
        "/api/companies/generalist/memo-analysis/artifacts/narrative_hooks",
        json={
            "selected_opening_id": selected_opening["id"],
            "selected_ending_id": selected_ending["id"],
        },
    )
    assert hooks_response.status_code == 200
    hook_payload = hooks_response.json()["artifacts"]["narrative_hooks"]
    assert hook_payload["selected_opening_id"] == selected_opening["id"]
    assert hook_payload["selected_ending_id"] == selected_ending["id"]

    packet_path = (
        serena_analysis.session_dir("generalist", hooks_response.json()["id"])
        / "memo_packet.md"
    )
    packet = packet_path.read_text(encoding="utf-8")
    assert "Edited deployment wedge" in packet
    assert "Edited gate question?" in packet
    assert disabled_chart_title not in packet
    assert selected_opening["text"] in packet
    assert selected_ending["text"] in packet


def test_memo_analysis_api_patches_risk_priorities_and_refreshes_tasks(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "products": [{"name": "Humanoid platform"}],
        },
    )
    client = TestClient(app)

    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)

    risks = session["artifacts"]["strategic_risks"]["risks"]
    initial_priorities = session["artifacts"]["risk_priorities"]["priorities"]
    assert len(risks) >= 5
    assert [task["risk_id"] for task in session["artifacts"]["research_tasks"]["tasks"]] == [
        row["risk_id"] for row in initial_priorities[:3]
    ]

    moved_to_top = initial_priorities[4]
    kept_selected = initial_priorities[1]
    deprioritized = initial_priorities[0]
    omitted_default_selected = initial_priorities[2]
    patch_response = client.patch(
        "/api/companies/generalist/memo-analysis/artifacts/risk_priorities",
        json={
            "priorities": [
                {
                    "risk_id": moved_to_top["risk_id"],
                    "rank": 1,
                    "selected": True,
                    "rationale": "Serena moved this risk to the top.",
                },
                {
                    "risk_id": kept_selected["risk_id"],
                    "rank": 2,
                    "selected": True,
                    "rationale": kept_selected["rationale"],
                },
                {
                    "risk_id": deprioritized["risk_id"],
                    "rank": 3,
                    "selected": False,
                    "rationale": "Lower decision impact after review.",
                },
            ],
        },
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    priorities = payload["artifacts"]["risk_priorities"]["priorities"]
    assert [row["rank"] for row in priorities] == list(range(1, len(risks) + 1))
    assert [row["risk_id"] for row in priorities[:3]] == [
        moved_to_top["risk_id"],
        kept_selected["risk_id"],
        deprioritized["risk_id"],
    ]
    by_id = {row["risk_id"]: row for row in priorities}
    assert by_id[moved_to_top["risk_id"]]["selected"] is True
    assert by_id[kept_selected["risk_id"]]["selected"] is True
    assert by_id[deprioritized["risk_id"]]["selected"] is False
    assert by_id[omitted_default_selected["risk_id"]]["selected"] is False
    assert by_id[moved_to_top["risk_id"]]["rationale"] == (
        "Serena moved this risk to the top."
    )

    tasks = payload["artifacts"]["research_tasks"]["tasks"]
    assert [task["risk_id"] for task in tasks] == [
        moved_to_top["risk_id"],
        kept_selected["risk_id"],
    ]
    assert [task["id"] for task in tasks] == ["task-1", "task-2"]
    assert all(task["priority"] == "high" for task in tasks)
    assert tasks[0]["search_plan"]["steps"]
    assert tasks[0]["search_plan"]["question"]

    persisted = serena_analysis.get_current_session("generalist")
    assert persisted["artifacts"]["risk_priorities"]["priorities"] == priorities
    assert persisted["artifacts"]["research_tasks"]["tasks"] == tasks

    empty_response = client.patch(
        "/api/companies/generalist/memo-analysis/artifacts/risk_priorities",
        json={
            "priorities": [
                {**row, "selected": False}
                for row in priorities
            ],
        },
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["artifacts"]["research_tasks"]["tasks"] == []


def test_memo_analysis_research_task_results_persist_without_reordering_priorities(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "products": [{"name": "Humanoid platform"}],
        },
    )
    client = TestClient(app)
    monkeypatch.setattr(
        claude_runner,
        "run_serena_research_task",
        lambda **kwargs: (None, "Claude disabled in test"),
    )

    session = None
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)

    assert session is not None
    priorities_before = session["artifacts"]["risk_priorities"]["priorities"]
    tasks_before = session["artifacts"]["research_tasks"]["tasks"]
    assert len(tasks_before) >= 2

    patched = client.patch(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1",
        json={
            "status": "skipped",
            "result_summary": "Manual review: deprioritized after source check.",
        },
    )
    assert patched.status_code == 200
    patched_payload = patched.json()
    assert (
        patched_payload["artifacts"]["risk_priorities"]["priorities"]
        == priorities_before
    )

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-2/run"
    )
    assert run.status_code == 202
    running_payload = run.json()
    running_tasks = {
        task["id"]: task
        for task in running_payload["artifacts"]["research_tasks"]["tasks"]
    }
    assert running_tasks["task-2"]["status"] == "running"

    payload = _wait_for_task_status("generalist", "task-2", "done")
    assert payload["artifacts"]["risk_priorities"]["priorities"] == priorities_before

    tasks = {
        task["id"]: task
        for task in payload["artifacts"]["research_tasks"]["tasks"]
    }
    assert tasks["task-1"]["status"] == "skipped"
    assert "Manual review" in tasks["task-1"]["result_summary"]
    assert tasks["task-2"]["status"] == "done"
    assert tasks["task-2"]["result_generated_by"] == "deterministic_fallback"
    assert "Claude research fallback" in tasks["task-2"]["error"]
    assert "First-pass deterministic result for Generalist" in (
        tasks["task-2"]["result_summary"]
    )

    persisted = serena_analysis.get_current_session("generalist")
    assert (
        persisted["artifacts"]["risk_priorities"]["priorities"]
        == priorities_before
    )
    persisted_tasks = {
        task["id"]: task
        for task in persisted["artifacts"]["research_tasks"]["tasks"]
    }
    assert persisted_tasks["task-2"]["result_summary"] == (
        tasks["task-2"]["result_summary"]
    )

    packet_path = (
        serena_analysis.session_dir("generalist", payload["id"]) / "memo_packet.md"
    )
    packet = packet_path.read_text(encoding="utf-8")
    assert "Research Task Results" in packet
    assert "Manual review: deprioritized after source check." in packet
    assert tasks["task-2"]["result_summary"] in packet


def test_memo_analysis_research_task_job_persists_claude_result(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
            "products": [{"name": "Humanoid platform"}],
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_research_task",
        lambda **kwargs: (
            {
                "result_summary": "Claude-backed result: deployment evidence is still thin.",
                "key_findings": ["Pilots need independent validation."],
                "evidence_gaps": ["Customer deployment depth"],
                "sources_checked": ["Serena research folder"],
                "confidence": "medium",
            },
            None,
        ),
    )
    client = TestClient(app)

    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1/run"
    )
    assert run.status_code == 202

    session = _wait_for_task_status("generalist", "task-1", "done")
    tasks = {
        task["id"]: task
        for task in session["artifacts"]["research_tasks"]["tasks"]
    }
    task = tasks["task-1"]
    assert task["result_generated_by"] == "claude_code"
    assert task["result_summary"] == (
        "Claude-backed result: deployment evidence is still thin."
    )
    assert task["result_payload"]["confidence"] == "medium"


def test_memo_analysis_research_task_selected_source_ids_persist(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    source = research_store.upload_file(
        "generalist",
        filename="customer-note.txt",
        content_type="text/plain",
        data=b"Customer deployment note",
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    patched = client.patch(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1",
        json={"selected_source_ids": [source["id"], source["id"], "bad id"]},
    )

    assert patched.status_code == 200, patched.text
    task = next(
        item
        for item in patched.json()["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )
    assert task["selected_source_ids"] == [source["id"]]

    persisted = serena_analysis.get_current_session("generalist")
    persisted_task = next(
        item
        for item in persisted["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )
    assert persisted_task["selected_source_ids"] == [source["id"]]


def test_memo_analysis_research_task_passes_only_selected_sources_to_claude(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    selected = research_store.upload_file(
        "generalist",
        filename="selected-source.txt",
        content_type="text/plain",
        data=b"Selected source evidence",
    )
    unselected = research_store.upload_file(
        "generalist",
        filename="unselected-source.txt",
        content_type="text/plain",
        data=b"Unselected source evidence",
    )
    captured = {}

    def fake_run(**kwargs):
        research_dir = kwargs["research_dir"]
        captured["files"] = sorted(path.name for path in research_dir.iterdir())
        captured["source_manifest"] = kwargs["source_manifest"]
        return (
            {
                "answer": "Selected source supports limited deployment depth.",
                "supporting_evidence": [
                    {
                        "file_id": selected["id"],
                        "filename": selected["filename"],
                        "locator": "Document",
                        "excerpt": "Selected source evidence",
                        "confidence": "high",
                    }
                ],
                "contradicting_evidence": [],
                "open_questions": ["Need customer count."],
                "sources_checked": [
                    {
                        "file_id": selected["id"],
                        "filename": selected["filename"],
                        "source_type": "company_background",
                        "notes": None,
                    }
                ],
                "confidence": "high",
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "run_serena_research_task", fake_run)
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)
    client.patch(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1",
        json={"selected_source_ids": [selected["id"]]},
    )

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1/run"
    )
    assert run.status_code == 202, run.text
    session = _wait_for_task_status("generalist", "task-1", "done")

    assert selected["stored_name"] in captured["files"]
    assert unselected["stored_name"] not in captured["files"]
    assert captured["source_manifest"][0]["file_id"] == selected["id"]
    task = next(
        item
        for item in session["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )
    assert task["answer"] == "Selected source supports limited deployment depth."
    assert task["confidence"] == "high"
    assert task["supporting_evidence"][0]["file_id"] == selected["id"]
    assert task["sources_checked"][0]["file_id"] == selected["id"]


def test_memo_analysis_research_task_no_selection_uses_full_research_folder(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    source = research_store.upload_file(
        "generalist",
        filename="full-folder-source.txt",
        content_type="text/plain",
        data=b"Full folder evidence",
    )
    captured = {}

    def fake_run(**kwargs):
        captured["research_dir"] = kwargs["research_dir"]
        captured["source_manifest"] = kwargs["source_manifest"]
        return (
            {
                "answer": "Full folder fallback still works.",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "open_questions": [],
                "sources_checked": [],
                "confidence": "medium",
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "run_serena_research_task", fake_run)
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1/run"
    )
    assert run.status_code == 202, run.text
    _wait_for_task_status("generalist", "task-1", "done")

    assert captured["research_dir"] == research_store.RESEARCH_ROOT / "generalist"
    assert any(
        item.get("file_id") == source["id"]
        for item in captured["source_manifest"]
    )


def test_memo_analysis_research_task_malformed_claude_output_falls_back(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_research_task",
        lambda **kwargs: ({"key_findings": ["Finding without answer"]}, None),
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1/run"
    )
    assert run.status_code == 202, run.text
    session = _wait_for_task_status("generalist", "task-1", "done")
    task = next(
        item
        for item in session["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )

    assert task["result_generated_by"] == "deterministic_fallback"
    assert task["confidence"] == "low"
    assert "Claude research fallback" in task["error"]
    assert "First-pass deterministic result for Generalist" in task["answer"]


def test_memo_analysis_research_task_error_preserves_previous_result(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_research_task",
        lambda **kwargs: (None, "Claude failed"),
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)
    client.patch(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1",
        json={"result_summary": "Previous sourced answer."},
    )

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/task-1/run"
    )
    assert run.status_code == 202, run.text
    session = _wait_for_task_status("generalist", "task-1", "error")
    task = next(
        item
        for item in session["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )

    assert task["result_summary"] == "Previous sourced answer."
    assert task["answer"] == "Previous sourced answer."
    assert task["error"] == "Claude failed"


def test_memo_analysis_run_selected_launches_all_runnable_tasks(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )

    def fake_run(**kwargs):
        task_id = kwargs["task"]["id"]
        return (
            {
                "answer": f"Answer for {task_id}",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "open_questions": [],
                "sources_checked": [],
                "confidence": "medium",
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "run_serena_research_task", fake_run)
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/run-selected"
    )

    assert run.status_code == 202, run.text
    batch = run.json()["batch"]
    assert batch["launched_task_ids"] == ["task-1", "task-2", "task-3"]
    assert all(
        batch["statuses"][task_id] == "launched"
        for task_id in batch["launched_task_ids"]
    )
    for task_id in batch["launched_task_ids"]:
        session = _wait_for_task_status("generalist", task_id, "done")
    tasks = {
        task["id"]: task
        for task in session["artifacts"]["research_tasks"]["tasks"]
    }
    assert tasks["task-1"]["answer"] == "Answer for task-1"
    assert tasks["task-2"]["answer"] == "Answer for task-2"
    assert tasks["task-3"]["answer"] == "Answer for task-3"


def test_memo_analysis_research_task_worker_uses_concurrency_semaphore(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)
    task = session["artifacts"]["research_tasks"]["tasks"][0]
    enters = []

    class FakeSemaphore:
        def __enter__(self):
            enters.append("enter")

        def __exit__(self, exc_type, exc, tb):
            enters.append("exit")

    monkeypatch.setattr(
        serena_analysis,
        "_RESEARCH_TASK_RUN_SEMAPHORE",
        FakeSemaphore(),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_serena_research_task",
        lambda **kwargs: (
            {
                "answer": "Semaphore-wrapped answer.",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "open_questions": [],
                "sources_checked": [],
                "confidence": "medium",
            },
            None,
        ),
    )

    serena_analysis._run_research_task_job(
        "generalist",
        session["id"],
        task["id"],
        storage.get_company("generalist"),
        task,
        None,
        research_store.RESEARCH_ROOT / "generalist",
        [],
    )

    assert enters == ["enter", "exit"]
    progress_path = serena_analysis.research_task_progress_path(
        "generalist", session["id"], task["id"]
    )
    stages = [
        event.get("stage")
        for event in _events(progress_path)
        if event.get("type") == "stage"
    ]
    assert "queued" in stages
    assert "running" in stages


def test_memo_analysis_run_selected_retries_failed_and_skips_running(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    tasks = raw["artifacts"]["research_tasks"]["tasks"]
    tasks[0]["status"] = "running"
    tasks[0]["started_at"] = datetime.now(timezone.utc).isoformat()
    tasks[0]["last_run_at"] = datetime.now(timezone.utc).isoformat()
    tasks[1]["status"] = "error"
    tasks[2]["status"] = "cancelled"
    serena_analysis._write_session(raw)
    progress = job_progress.ProgressLog(
        serena_analysis.research_task_progress_path(
            "generalist", raw["id"], tasks[0]["id"]
        )
    )
    progress.emit(
        "job_init",
        kind="serena_research_task",
        title=tasks[0]["title"],
        subtitle="Generalist",
        company_id="generalist",
        session_id=raw["id"],
        task_id=tasks[0]["id"],
    )
    progress.emit("stage", stage="running", message="Still running")
    starts = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            starts.append((args, kwargs))

        def start(self):
            starts.append("started")

    monkeypatch.setattr(serena_analysis.threading, "Thread", FakeThread)

    payload = serena_analysis.start_selected_research_task_jobs("generalist")

    assert starts.count("started") == 2
    assert payload["batch"]["statuses"]["task-1"] == "already_running"
    assert payload["batch"]["statuses"]["task-2"] == "launched"
    assert payload["batch"]["statuses"]["task-3"] == "launched"


def test_memo_analysis_run_selected_partial_failures_do_not_block_successes(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )

    def fake_run(**kwargs):
        if kwargs["task"]["id"] == "task-2":
            return None, "Claude failed task-2"
        return (
            {
                "answer": f"Successful {kwargs['task']['id']}",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "open_questions": [],
                "sources_checked": [],
                "confidence": "medium",
            },
            None,
        )

    monkeypatch.setattr(claude_runner, "run_serena_research_task", fake_run)
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        _post_tool(client, "generalist", tool)

    run = client.post(
        "/api/companies/generalist/memo-analysis/research-tasks/run-selected"
    )
    assert run.status_code == 202, run.text
    for task_id in ("task-1", "task-2", "task-3"):
        session = _wait_for_task_status("generalist", task_id, "done")
    tasks = {
        task["id"]: task
        for task in session["artifacts"]["research_tasks"]["tasks"]
    }

    assert tasks["task-1"]["answer"] == "Successful task-1"
    assert tasks["task-3"]["answer"] == "Successful task-3"
    assert tasks["task-2"]["result_generated_by"] == "deterministic_fallback"
    assert "Claude failed task-2" in tasks["task-2"]["error"]


def test_company_evidence_matrix_builds_mixed_buckets_and_dedupes(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    record = research_store.upload_file(
        "generalist",
        filename="customer-note.txt",
        content_type="text/plain",
        data=b"Customer note",
    )
    duplicate_trace = {
        "claim": "Deployment depth is proven.",
        "file_id": record["id"],
        "filename": record["filename"],
        "locator": "Document",
        "excerpt": "Three customers expanded production deployments.",
        "confidence": "high",
    }
    research_store.update_record(
        "generalist",
        record["id"],
        quick_summary={
            "source_traces": [duplicate_trace, duplicate_trace],
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    task = raw["artifacts"]["research_tasks"]["tasks"][0]
    task.update({
        "status": "done",
        "answer": "Deployment depth is proven.",
        "result_summary": "Deployment depth is proven.",
        "supporting_evidence": [
            {
                "file_id": record["id"],
                "filename": record["filename"],
                "locator": "Document",
                "excerpt": "Three customers expanded production deployments.",
                "confidence": "high",
            }
        ],
        "contradicting_evidence": [
            {
                "file_id": None,
                "filename": "Expert call",
                "locator": "Call note",
                "excerpt": "Reference said deployments remain pilots.",
                "confidence": "medium",
            }
        ],
        "open_questions": ["Need contracted ARR by customer."],
        "confidence": "medium",
    })
    serena_analysis._write_session(raw)

    response = client.get("/api/companies/generalist/evidence-matrix")

    assert response.status_code == 200, response.text
    matrix = response.json()
    row = next(
        claim
        for claim in matrix["claims"]
        if claim["claim"] == "Deployment depth is proven."
    )
    assert row["status"] == "mixed"
    assert row["confidence"] == "high"
    assert row["source_coverage"]["supporting_count"] == 1
    assert row["source_coverage"]["contradicting_count"] == 1
    assert row["source_coverage"]["missing_count"] == 1
    assert row["contradicting_evidence"][0]["task_id"] == task["id"]
    assert row["missing_evidence"] == ["Need contracted ARR by customer."]


def test_structured_research_results_feed_readiness_and_memo_packet(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    task = raw["artifacts"]["research_tasks"]["tasks"][0]
    task.update({
        "status": "done",
        "answer": "Deployment depth remains unproven.",
        "result_summary": "Deployment depth remains unproven.",
        "supporting_evidence": [
            {
                "file_id": None,
                "filename": "Customer call",
                "locator": "Call note",
                "excerpt": "Only pilots were confirmed.",
                "confidence": "medium",
            }
        ],
        "contradicting_evidence": [],
        "open_questions": ["Need production deployment count."],
        "confidence": "medium",
    })
    serena_analysis._refresh_memo_packet(raw)
    serena_analysis._write_session(raw)

    decorated = serena_analysis.get_current_session("generalist")

    gates = {gate["id"]: gate for gate in decorated["readiness"]["gates"]}
    assert gates["research_task_results"]["status"] == "done"
    assert gates["research_task_evidence"]["status"] == "done"
    assert any(
        area["id"].startswith("research-open-question-")
        and "Need production deployment count" in area["why_it_matters"]
        for area in decorated["additional_areas"]
    )
    assert any(
        blocker["id"].startswith("research-open-question-")
        for blocker in decorated["readiness"]["approval_blockers"]
    )
    packet = (
        serena_analysis.session_dir("generalist", decorated["id"])
        / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Evidence Matrix Summary" in packet
    assert "Missing evidence / open questions" in packet
    assert "Strongest source-backed support" in packet
    assert "Only pilots were confirmed." in packet
    assert "Need production deployment count." in packet


def test_memo_analysis_research_task_job_is_idempotent_while_running(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        serena_analysis.run_tool("generalist", tool)

    starts = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            starts.append((args, kwargs))

        def start(self):
            starts.append("started")

    monkeypatch.setattr(serena_analysis.threading, "Thread", FakeThread)

    first = serena_analysis.start_research_task_job("generalist", "task-1")
    second = serena_analysis.start_research_task_job("generalist", "task-1")

    assert starts.count("started") == 1
    for payload in (first, second):
        task = next(
            item
            for item in payload["artifacts"]["research_tasks"]["tasks"]
            if item["id"] == "task-1"
        )
        assert task["status"] == "running"


def test_memo_analysis_research_task_cancel_marks_task_and_progress(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        serena_analysis.run_tool("generalist", tool)

    class FakeThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(serena_analysis.threading, "Thread", FakeThread)

    started = serena_analysis.start_research_task_job("generalist", "task-1")
    task = next(
        item
        for item in started["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )
    assert task["status"] == "running"

    cancelled = serena_analysis.cancel_research_task_job("generalist", "task-1")
    task = next(
        item
        for item in cancelled["artifacts"]["research_tasks"]["tasks"]
        if item["id"] == "task-1"
    )
    assert task["status"] == "cancelled"
    assert task["cancelled_at"]
    assert task["error"] == "Research task cancelled"

    session_id = cancelled["id"]
    progress_path = serena_analysis.research_task_progress_path(
        "generalist", session_id, "task-1"
    )
    assert _events(progress_path)[-1]["type"] == "cancelled"


def test_memo_analysis_recovers_stale_running_research_task(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)

    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    task = raw["artifacts"]["research_tasks"]["tasks"][0]
    stale_at = _iso_seconds_ago(120)
    task.update({
        "status": "running",
        "started_at": stale_at,
        "completed_at": None,
        "last_run_at": stale_at,
        "error": None,
        "result_summary": "Previous completed result remains useful.",
        "result_generated_by": "claude_code",
        "run_job_id": f"generalist/{raw['id']}/{task['id']}",
    })
    serena_analysis._write_session(raw)

    progress_path = serena_analysis.research_task_progress_path(
        "generalist", raw["id"], task["id"]
    )
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="serena_research_task",
        title=task["title"],
        subtitle="Generalist",
        company_id="generalist",
        session_id=raw["id"],
        task_id=task["id"],
    )
    progress.emit("stage", stage="researching", message="Researching evidence")
    old_mtime = time.time() - 120
    os.utime(progress_path, (old_mtime, old_mtime))

    assert serena_analysis.recover_stale_runs(max_idle_seconds=60) == 1
    recovered = serena_analysis.get_current_session("generalist")
    recovered_task = recovered["artifacts"]["research_tasks"]["tasks"][0]
    assert recovered_task["status"] == "error"
    assert "progress log has been idle" in recovered_task["error"]
    assert recovered_task["result_summary"] == "Previous completed result remains useful."
    assert recovered_task["recovered_at"]
    assert '"type": "error"' in progress_path.read_text(encoding="utf-8")


def test_memo_analysis_recovers_running_tool_with_terminal_progress(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    session = _post_tool(client, "generalist", "strategic_risk_mapper")
    previous_risks = copy.deepcopy(
        session["artifacts"]["strategic_risks"]["risks"]
    )

    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    raw["tool_runs"]["strategic_risk_mapper"] = {
        "status": "running",
        "last_run_at": _iso_seconds_ago(5),
        "summary": "Running with Claude.",
        "error": None,
        "run_job_id": f"generalist/{raw['id']}/strategic_risk_mapper",
    }
    serena_analysis._write_session(raw)

    progress_path = serena_analysis.analysis_tool_progress_path(
        "generalist", raw["id"], "strategic_risk_mapper"
    )
    progress = job_progress.ProgressLog(progress_path)
    progress.emit(
        "job_init",
        kind="serena_analysis_tool",
        title="Strategic Risk Mapper",
        subtitle="Generalist",
        company_id="generalist",
        session_id=raw["id"],
        tool_name="strategic_risk_mapper",
    )
    progress.emit("error", tool_name="strategic_risk_mapper", error="Claude exited")

    recovered = serena_analysis.get_current_session("generalist")
    tool = next(
        item for item in recovered["tools"]
        if item["name"] == "strategic_risk_mapper"
    )
    assert tool["status"] == "error"
    assert "Claude exited" in tool["error"]
    assert recovered["artifacts"]["strategic_risks"]["risks"] == previous_risks
    assert len(progress_path.read_text(encoding="utf-8").splitlines()) == 2


def test_memo_analysis_recovery_leaves_active_and_terminal_runs_alone(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)

    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    tasks = raw["artifacts"]["research_tasks"]["tasks"]
    active_task = tasks[0]
    active_task.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "run_job_id": f"generalist/{raw['id']}/{active_task['id']}",
    })
    terminal_task = tasks[1]
    terminal_task.update({
        "status": "done",
        "completed_at": _iso_seconds_ago(120),
        "last_run_at": _iso_seconds_ago(120),
        "result_summary": "Already completed.",
        "error": None,
    })
    serena_analysis._write_session(raw)

    progress = job_progress.ProgressLog(
        serena_analysis.research_task_progress_path(
            "generalist", raw["id"], active_task["id"]
        )
    )
    progress.emit(
        "job_init",
        kind="serena_research_task",
        title=active_task["title"],
        subtitle="Generalist",
        company_id="generalist",
        session_id=raw["id"],
        task_id=active_task["id"],
    )
    progress.emit("stage", stage="starting", message="Still active")

    assert serena_analysis.recover_stale_runs(max_idle_seconds=60) == 0
    recovered = serena_analysis.get_current_session("generalist")
    recovered_tasks = {
        task["id"]: task
        for task in recovered["artifacts"]["research_tasks"]["tasks"]
    }
    assert recovered_tasks[active_task["id"]]["status"] == "running"
    assert recovered_tasks[terminal_task["id"]]["status"] == "done"
    assert recovered_tasks[terminal_task["id"]]["result_summary"] == "Already completed."


def test_memo_analysis_research_task_job_appears_in_active_jobs(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    for tool in ("strategic_risk_mapper", "priority_prompt_harness"):
        session = _post_tool(client, "generalist", tool)

    progress = job_progress.ProgressLog(
        serena_analysis.research_task_progress_path(
            "generalist", session["id"], "task-1"
        )
    )
    progress.emit(
        "job_init",
        kind="serena_research_task",
        title="Research: active task",
        subtitle="Generalist",
        company_id="generalist",
        session_id=session["id"],
        task_id="task-1",
        risk_id="risk-1",
    )
    progress.emit("stage", stage="starting", message="Starting selected prompt")

    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    jobs = active.json()
    job = next(j for j in jobs if j.get("task_id") == "task-1")
    assert job["kind"] == "serena_research_task"
    assert job["title"] == "Research: active task"
    assert job["stream_url"].endswith(
        f"/memo-analysis/sessions/{session['id']}/research-tasks/task-1/stream"
    )
    assert job["log_url"] == (
        f"/api/jobs/log?path=serena_research_task:"
        f"generalist/{session['id']}/task-1"
    )

    log = client.get(job["log_url"])
    assert log.status_code == 200, log.text
    assert [event["type"] for event in log.json()] == ["job_init", "stage"]


def test_memo_analysis_tool_job_appears_in_active_jobs(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    session = serena_analysis.get_current_session("generalist")

    progress = job_progress.ProgressLog(
        serena_analysis.analysis_tool_progress_path(
            "generalist", session["id"], "strategic_risk_mapper"
        )
    )
    progress.emit(
        "job_init",
        kind="serena_analysis_tool",
        title="Strategic Risk Mapper",
        subtitle="Generalist",
        company_id="generalist",
        session_id=session["id"],
        tool_name="strategic_risk_mapper",
    )
    progress.emit("stage", stage="starting", message="Starting risk mapper")

    thesis_progress = job_progress.ProgressLog(
        serena_analysis.analysis_tool_progress_path(
            "generalist", session["id"], "thesis_spine_builder"
        )
    )
    thesis_progress.emit(
        "job_init",
        kind="serena_analysis_tool",
        title="Thesis Spine Builder",
        subtitle="Generalist",
        company_id="generalist",
        session_id=session["id"],
        tool_name="thesis_spine_builder",
    )
    thesis_progress.emit("stage", stage="starting", message="Starting thesis builder")

    benchmark_progress = job_progress.ProgressLog(
        serena_analysis.analysis_tool_progress_path(
            "generalist", session["id"], "private_benchmark_dashboard"
        )
    )
    benchmark_progress.emit(
        "job_init",
        kind="serena_analysis_tool",
        title="Private Benchmark Dashboard",
        subtitle="Generalist",
        company_id="generalist",
        session_id=session["id"],
        tool_name="private_benchmark_dashboard",
    )
    benchmark_progress.emit("stage", stage="starting", message="Starting benchmark")

    for tool_name, title in (
        ("infographic_source_brief", "Infographic Source Brief"),
        ("chart_spec_builder", "Infographic Plan Builder"),
        ("narrative_hooks", "Narrative Hook Planner"),
    ):
        tool_progress = job_progress.ProgressLog(
            serena_analysis.analysis_tool_progress_path(
                "generalist", session["id"], tool_name
            )
        )
        tool_progress.emit(
            "job_init",
            kind="serena_analysis_tool",
            title=title,
            subtitle="Generalist",
            company_id="generalist",
            session_id=session["id"],
            tool_name=tool_name,
        )
        tool_progress.emit(
            "stage",
            stage="starting",
            message=f"Starting {title}",
        )

    active = client.get("/api/jobs/active")
    assert active.status_code == 200, active.text
    jobs = active.json()
    job = next(j for j in jobs if j.get("tool_name") == "strategic_risk_mapper")
    assert job["kind"] == "serena_analysis_tool"
    assert job["title"] == "Strategic Risk Mapper"
    assert job["job_id"] == f"generalist/{session['id']}/strategic_risk_mapper"
    assert job["stream_url"].endswith(
        f"/memo-analysis/sessions/{session['id']}/tools/strategic_risk_mapper/stream"
    )
    assert job["log_url"] == (
        f"/api/jobs/log?path=serena_analysis_tool:"
        f"generalist/{session['id']}/strategic_risk_mapper"
    )

    log = client.get(job["log_url"])
    assert log.status_code == 200, log.text
    assert [event["type"] for event in log.json()] == ["job_init", "stage"]

    thesis_job = next(j for j in jobs if j.get("tool_name") == "thesis_spine_builder")
    assert thesis_job["kind"] == "serena_analysis_tool"
    assert thesis_job["title"] == "Thesis Spine Builder"
    assert thesis_job["job_id"] == f"generalist/{session['id']}/thesis_spine_builder"
    assert thesis_job["stream_url"].endswith(
        f"/memo-analysis/sessions/{session['id']}/tools/thesis_spine_builder/stream"
    )
    assert thesis_job["log_url"] == (
        f"/api/jobs/log?path=serena_analysis_tool:"
        f"generalist/{session['id']}/thesis_spine_builder"
    )

    benchmark_job = next(
        j for j in jobs if j.get("tool_name") == "private_benchmark_dashboard"
    )
    assert benchmark_job["kind"] == "serena_analysis_tool"
    assert benchmark_job["title"] == "Private Benchmark Dashboard"
    assert benchmark_job["job_id"] == (
        f"generalist/{session['id']}/private_benchmark_dashboard"
    )
    assert benchmark_job["stream_url"].endswith(
        f"/memo-analysis/sessions/{session['id']}/tools/private_benchmark_dashboard/stream"
    )

    for tool_name, title in (
        ("infographic_source_brief", "Infographic Source Brief"),
        ("chart_spec_builder", "Infographic Plan Builder"),
        ("narrative_hooks", "Narrative Hook Planner"),
    ):
        tool_job = next(j for j in jobs if j.get("tool_name") == tool_name)
        assert tool_job["kind"] == "serena_analysis_tool"
        assert tool_job["title"] == title
        assert tool_job["job_id"] == f"generalist/{session['id']}/{tool_name}"
        assert tool_job["stream_url"].endswith(
            f"/memo-analysis/sessions/{session['id']}/tools/{tool_name}/stream"
        )


def test_analysis_backed_report_accepts_draft_session(tmp_path, monkeypatch):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    session = serena_analysis.run_tool("generalist", "thesis_spine_builder")
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)
    client = TestClient(app)

    response = client.post(
        "/api/reports",
        json={
            "company_id": "generalist",
            "report_type": memo_prep.REPORT_TYPE,
            "audience": "Internal",
            "language": "en",
            "analysis_session_id": session["id"],
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["analysis_session_id"] == session["id"]
    assert report["analysis_session_approved"] is False
    assert report["status"] == "ready_for_analysis"
    assert len(storage.list_reports()) == 1
    assert memo_prep.MEMOS_ROOT.exists()


def test_analysis_backed_prep_skips_current_memo_packet_refresh(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    session = serena_analysis.run_tool("generalist", "thesis_spine_builder")
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)

    def fail_refresh(_session):
        raise AssertionError("current memo packet should not be rebuilt")

    monkeypatch.setattr(serena_analysis, "_refresh_memo_packet", fail_refresh)
    client = TestClient(app)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": session["id"],
        },
    )

    assert response.status_code == 201, response.text
    report = response.json()
    assert report["analysis_session_id"] == session["id"]
    assert report["status"] == "ready_for_analysis"


def test_analysis_backed_prep_refreshes_stale_memo_packet(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    session = serena_analysis.run_tool("generalist", "thesis_spine_builder")
    raw = serena_analysis._strip_decorations(copy.deepcopy(session))
    raw["artifacts"]["thesis_spine"]["investment_highlights"][0]["claim"] = (
        "Launch-time packet refresh keeps the final memo current"
    )
    serena_analysis._write_session(raw)
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)
    client = TestClient(app)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": session["id"],
        },
    )

    assert response.status_code == 201, response.text
    packet = (
        serena_analysis.session_dir("generalist", session["id"])
        / "memo_packet.md"
    ).read_text(encoding="utf-8")
    assert "Launch-time packet refresh keeps the final memo current" in packet


def test_analysis_backed_prep_accepts_unapproved_thesis_spine(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    approved_without_thesis = _run_approval_required_tools(client, "generalist")
    approved_without_thesis = serena_analysis.approve("generalist")
    raw = serena_analysis._strip_decorations(copy.deepcopy(approved_without_thesis))
    raw["artifacts"]["thesis_spine"]["approved"] = False
    serena_analysis._write_session(raw)
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": approved_without_thesis["id"],
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["analysis_session_id"] == approved_without_thesis["id"]
    assert report["analysis_session_approved"] is True
    assert report["status"] == "ready_for_analysis"


def test_analysis_backed_prep_accepts_approved_thesis_spine(
    tmp_path, monkeypatch
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    session = _run_approval_required_tools(client, "generalist")
    approved = serena_analysis.approve("generalist")
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": session["id"],
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["analysis_session_id"] == approved["id"]
    assert report["analysis_session_approved"] is True
    assert report["status"] == "ready_for_analysis"


def test_analysis_backed_prep_accepts_approved_session_with_reopened_blockers(
    tmp_path,
    monkeypatch,
):
    _seed_company(
        tmp_path,
        monkeypatch,
        {
            "id": "generalist",
            "name": "Generalist",
            "status": "private",
            "sector": "AI Robotics",
            "description": "Generalist builds humanoid robots.",
        },
    )
    client = TestClient(app)
    session = _run_approval_required_tools(client, "generalist")
    approved = serena_analysis.approve("generalist")
    raw = serena_analysis._strip_decorations(copy.deepcopy(approved))
    raw["artifacts"]["thesis_spine"]["top_gating_questions"] = []
    serena_analysis._refresh_memo_packet(raw)
    serena_analysis._write_session(raw)
    reopened = serena_analysis.get_current_session("generalist")
    assert any(
        blocker["id"] == "gating_questions"
        for blocker in reopened["readiness"]["approval_blockers"]
    )
    assert reopened["approved_for_memo"] is True
    assert reopened["readiness"]["ready_for_memo"] is False
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: None)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": approved["id"],
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["analysis_session_id"] == approved["id"]
    assert report["analysis_session_approved"] is True
    assert report["status"] == "ready_for_analysis"
