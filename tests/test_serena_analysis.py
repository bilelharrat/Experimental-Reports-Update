from __future__ import annotations

import time

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

    run = client.post(
        "/api/companies/generalist/memo-analysis/tools/strategic_risk_mapper/run"
    )
    assert run.status_code == 200
    assert run.json()["artifacts"]["strategic_risks"]["risks"]

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

    run = client.post(
        "/api/companies/generalist/memo-analysis/tools/strategic_risk_mapper/run"
    )
    assert run.status_code == 200
    run_payload = run.json()
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
        response = client.post(
            f"/api/companies/generalist/memo-analysis/tools/{tool}/run"
        )
        assert response.status_code == 200
        session = response.json()

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
        response = client.post(
            f"/api/companies/generalist/memo-analysis/tools/{tool}/run"
        )
        assert response.status_code == 200
        session = response.json()

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
        response = client.post(
            f"/api/companies/generalist/memo-analysis/tools/{tool}/run"
        )
        assert response.status_code == 200
        session = response.json()

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
        response = client.post(
            f"/api/companies/generalist/memo-analysis/tools/{tool}/run"
        )
        assert response.status_code == 200

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
        response = client.post(
            f"/api/companies/generalist/memo-analysis/tools/{tool}/run"
        )
        assert response.status_code == 200
    session = response.json()

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
