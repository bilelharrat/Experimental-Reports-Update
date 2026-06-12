from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from server import (
    claude_runner,
    job_progress,
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
    assert "Claude highlight 1" in (
        serena_analysis.session_dir("generalist", session["id"]) / "memo_packet.md"
    ).read_text(encoding="utf-8")

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
        "chart_spec_builder",
        "private_benchmark_dashboard",
        "readiness_check",
    ):
        session = serena_analysis.run_tool("anduril", tool)

    assert session["readiness"]["score"] == session["readiness"]["total"] - 1
    assert session["approved_for_memo"] is False

    approved = serena_analysis.approve("anduril")

    assert approved["approved_for_memo"] is True
    assert approved["readiness"]["ready_for_memo"] is True
    memo_packet = (
        serena_analysis.session_dir("anduril", approved["id"]) / "memo_packet.md"
    )
    assert memo_packet.exists()
    assert "Investment Highlights" in memo_packet.read_text(encoding="utf-8")


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

    approved = client.post("/api/companies/generalist/memo-analysis/approve")
    assert approved.status_code == 200
    assert approved.json()["approved_for_memo"] is True


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


def test_analysis_backed_report_requires_approved_session(tmp_path, monkeypatch):
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

    assert response.status_code == 400
    assert "not approved for memo generation" in response.json()["detail"]
    assert storage.list_reports() == []
    assert not memo_prep.MEMOS_ROOT.exists()


def test_analysis_backed_prep_requires_approved_thesis_spine(
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
    session = serena_analysis.get_current_session("generalist", create=True)
    assert session is not None
    approved_without_thesis = serena_analysis.approve("generalist")
    client = TestClient(app)

    response = client.post(
        "/api/memos/prep",
        json={
            "company_id": "generalist",
            "analysis_session_id": approved_without_thesis["id"],
        },
    )

    assert response.status_code == 400
    assert "approved thesis spine" in response.json()["detail"]
    assert storage.list_reports() == []
    assert not memo_prep.MEMOS_ROOT.exists()


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
    session = serena_analysis.run_tool("generalist", "thesis_spine_builder")
    approved = serena_analysis.approve("generalist")
    client = TestClient(app)

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
