"""Tests for the Memo Studio lifecycle: investigate → park → generate.

The investigation worker runs Phase 1-2 plus the standalone spine, seeds
the cards, and parks the report at ``awaiting_studio`` with a terminal
``done`` on the stream — the event that keeps SSE, the jobs rail, and
every watchdog well-behaved. The generate worker re-enters the pipeline
at Phase 3 with the composed spine pinned.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest
import yaml

from server import (
    api,
    claude_runner,
    memo_analysis,
    memo_editor_store,
    memo_prep,
    memo_studio_bridge,
    serena_analysis,
    storage,
)
from server.main import app


@pytest.fixture
def studio_env(monkeypatch, tmp_path):
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
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data_root / "memo_editor")
    monkeypatch.setattr(serena_analysis, "ANALYSIS_ROOT", data_root / "serena_analysis")
    monkeypatch.setattr(serena_analysis, "TRAINING_ROOT", data_root / "serena_training")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    data_root.mkdir(parents=True)
    companies = [{"id": "generalist-inc", "name": "Generalist, Inc.", "status": "private"}]
    with (data_root / "companies.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(companies, f, sort_keys=False)
    return data_root


_RUN_COUNTER = iter(range(1000))


def _make_studio_report(data_root, *, status="ready_for_analysis", **extra):
    run_id = f"2026-09-01__12{next(_RUN_COUNTER):04d}"
    run_dir = (
        data_root / "memos" / "generalist-inc" / f"{run_id}__generalist-inc__memo-run"
    )
    (run_dir / "logs").mkdir(parents=True)
    report = storage.create_report_record(
        company_id="generalist-inc",
        company_name="Generalist, Inc.",
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status=status,
        progress=10,
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[
            {"language": "en", "path": memo_prep._rel(run_dir / "memo" / "en.docx")},
            {"language": "zh", "path": memo_prep._rel(run_dir / "memo" / "zh.docx")},
        ],
        memo_mode="studio",
        warnings=[],
        **extra,
    )
    return report, run_dir


def _events(run_dir):
    path = run_dir / "logs" / "stream.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fake_pass_results(failed: set[str] | None = None):
    failed = failed or set()
    results = []
    for spec in memo_analysis._FAST_MEMO_PASSES:
        if spec.pass_id in failed:
            results.append(
                memo_analysis._FastMemoPassResult(
                    spec=spec, data=None, error="boom", duration_ms=5, cost_usd=0.0
                )
            )
        else:
            results.append(
                memo_analysis._FastMemoPassResult(
                    spec=spec, data={"summary": "ok"}, error=None,
                    duration_ms=10, cost_usd=0.1,
                )
            )
    return results


def _spine_payload() -> dict:
    return {
        "package_skeleton": {
            "company": {"name": "Generalist, Inc."},
            "sources": [{"id": "S1", "title": {"en": "Data room", "zh": ""}}],
        },
        "shared_facts": {
            "recommendation_sentence": "We recommend participating.",
            "key_metrics": [],
            "scenarios": {"bear": "1x", "base": "2x", "bull": "3x"},
            "risks": [
                {"summary": "Concentration", "rating": "7/10"},
                {"summary": "Execution", "rating": "6/10"},
                {"summary": "Competition", "rating": "5/10"},
                {"summary": "Regulatory", "rating": "3/10"},
            ],
        },
        "section_notes": {},
    }


# ---- investigate ----------------------------------------------------------


def test_investigate_parks_at_awaiting_studio(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env)
    monkeypatch.setattr(
        memo_analysis,
        "_run_fast_phase2",
        lambda **kw: (_fake_pass_results({"competitive_rights"}), 0.8, 900),
    )
    spine_calls: list[dict] = []

    def fake_standalone(**kw):
        spine_calls.append(kw)
        units_dir = kw["run_dir"] / "logs" / "english_units"
        units_dir.mkdir(parents=True, exist_ok=True)
        payload = _spine_payload()
        (units_dir / "spine.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload, None

    monkeypatch.setattr(
        claude_runner, "run_memo_english_spine_standalone", fake_standalone
    )
    seeded: list[tuple] = []
    monkeypatch.setattr(
        memo_editor_store,
        "apply_agent_spine",
        lambda company_id, spine, provenance=None: (
            seeded.append((company_id, spine, provenance))
            or {"revision_id": "rev-0002"}
        ),
    )

    memo_analysis._investigate(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "awaiting_studio"
    investigation = updated["studio_investigation"]
    assert investigation["pass_failed"] == ["competitive_rights"]
    assert len(investigation["pass_ok"]) == len(memo_analysis._FAST_MEMO_PASSES) - 1
    assert investigation["seeded_revision_id"] == "rev-0002"
    # Failed passes reach the spine prompt as missing artifacts.
    assert spine_calls[0]["missing_pass_ids"] == ["competitive_rights"]
    assert seeded and seeded[0][0] == "generalist-inc"
    assert seeded[0][2]["mode"] == "studio"
    events = _events(run_dir)
    terminal = [e for e in events if e["type"] == "done"]
    assert terminal and terminal[-1]["awaiting_studio"] is True
    assert terminal[-1]["pass_failed"] == ["competitive_rights"]


def test_investigate_spine_retry_then_failure(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env)
    monkeypatch.setattr(
        memo_analysis,
        "_run_fast_phase2",
        lambda **kw: (_fake_pass_results(), 0.8, 900),
    )
    attempts: list[int] = []

    def failing_standalone(**kw):
        attempts.append(1)
        return None, "spine exploded"

    monkeypatch.setattr(
        claude_runner, "run_memo_english_spine_standalone", failing_standalone
    )

    memo_analysis._investigate(report["id"])

    assert len(attempts) == 2
    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == "studio_spine"
    events = _events(run_dir)
    assert any(e["type"] == "error" for e in events)
    assert any(
        e.get("stage") == "memo_studio_spine_retry"
        for e in events
        if e["type"] == "stage"
    )


def test_investigate_all_passes_failed(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env)

    def fake_phase2(**kw):
        # The real function records the failure itself before returning
        # None; mirror that contract.
        storage.update_report(
            report["id"],
            status="failed_during_analysis",
            failure_phase="fast_parallel_analysis",
        )
        return None, 0.5, 100

    monkeypatch.setattr(memo_analysis, "_run_fast_phase2", fake_phase2)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_english_spine_standalone",
        lambda **kw: (_ for _ in ()).throw(
            AssertionError("spine must not run when all passes failed")
        ),
    )

    memo_analysis._investigate(report["id"])

    assert storage.get_report(report["id"])["status"] == "failed_during_analysis"


# ---- the parked state vs the watchdogs ------------------------------------


def _park_report(studio_env):
    report, run_dir = _make_studio_report(studio_env, status="awaiting_studio")
    stream = memo_analysis.job_progress.ProgressLog(
        memo_prep.stream_path(run_dir)
    )
    stream.emit("job_init", kind="memo", report_id=report["id"])
    stream.emit("done", phase="investigation", awaiting_studio=True)
    return storage.get_report(report["id"]), run_dir


def test_recover_stale_reports_leaves_parked_run_alone(studio_env):
    report, _run_dir = _park_report(studio_env)
    assert memo_analysis.recover_stale_reports() == 0
    assert storage.get_report(report["id"])["status"] == "awaiting_studio"


def test_parked_report_never_offers_resume(studio_env):
    report, _run_dir = _park_report(studio_env)
    assert api._report_resume_available(report) is False
    # Even a failed STUDIO generation must not offer the monolithic resume.
    storage.update_report(
        report["id"], status="failed_during_analysis", failure_phase="shutdown"
    )
    assert api._report_resume_available(storage.get_report(report["id"])) is False


def test_auto_resume_skips_studio_runs(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(
        studio_env, status="failed_during_analysis"
    )
    storage.update_report(report["id"], failure_phase="shutdown")
    (run_dir / "logs" / "memo_package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        memo_analysis,
        "start_resume",
        lambda report_id: (_ for _ in ()).throw(
            AssertionError("studio run must not auto-resume")
        ),
    )
    assert api.resume_interrupted_memo_runs() == 0


def test_new_investigation_supersedes_parked_run(studio_env):
    parked, _run_dir = _park_report(studio_env)
    api._supersede_stale_memo_failures("generalist-inc", "newreport1234")
    assert storage.get_report(parked["id"])["superseded_by"] == "newreport1234"


# ---- generate -------------------------------------------------------------


def _prepare_generate(studio_env, *, status="awaiting_studio"):
    report, run_dir = _make_studio_report(studio_env, status=status)
    units_dir = run_dir / "logs" / "english_units"
    units_dir.mkdir(parents=True)
    (units_dir / "spine.json").write_text(
        json.dumps(_spine_payload()), encoding="utf-8"
    )
    (run_dir / "analysis" / "fast").mkdir(parents=True)
    stream = memo_analysis.job_progress.ProgressLog(
        memo_prep.stream_path(run_dir)
    )
    stream.emit("job_init", kind="memo", report_id=report["id"])
    stream.emit("done", phase="investigation", awaiting_studio=True)
    return storage.get_report(report["id"]), run_dir


def test_generate_worker_pins_spine_and_finalizes(studio_env, monkeypatch):
    report, run_dir = _prepare_generate(studio_env)
    (run_dir / "logs" / "memo_package.json").write_text("{}", encoding="utf-8")
    (run_dir / "logs" / "memo_package.en.json").write_text("{}", encoding="utf-8")
    synth_calls: list[dict] = []
    monkeypatch.setattr(
        memo_analysis,
        "_run_fast_synthesis",
        lambda **kw: synth_calls.append(kw) or {"ok": True, "cost_usd": 1.0},
    )
    finalize_calls: list[dict] = []
    monkeypatch.setattr(
        memo_analysis,
        "_finalize_memo_from_package",
        lambda **kw: finalize_calls.append(kw) or True,
    )

    memo_analysis._generate_from_studio(report["id"])

    assert synth_calls and synth_calls[0]["pinned_spine_path"] == (
        run_dir / "logs" / "english_units" / "spine.json"
    )
    assert synth_calls[0]["speculator"] is None
    assert finalize_calls
    # Old stream and packages were archived; a fresh stream carries the
    # studio-generate job_init.
    logs = run_dir / "logs"
    assert list(logs.glob("stream.before_generate.*.jsonl"))
    assert list(logs.glob("memo_package.studio_regenerate.*.json"))
    assert list(logs.glob("memo_package.en.studio_regenerate.*.json"))
    events = _events(run_dir)
    assert events[0]["type"] == "job_init"
    assert events[0]["studio_generate"] is True


def test_generate_worker_failure_marks_report(studio_env, monkeypatch):
    report, run_dir = _prepare_generate(studio_env)
    monkeypatch.setattr(
        memo_analysis,
        "_run_fast_synthesis",
        lambda **kw: {"ok": False, "error": "sections exploded"},
    )

    memo_analysis._generate_from_studio(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == "studio_generate"
    events = _events(run_dir)
    assert any(e["type"] == "error" for e in events)


# ---- API endpoints --------------------------------------------------------


def test_investigate_endpoint_requires_parallel_flag(studio_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    client = TestClient(app)
    response = client.post(
        "/api/memos/studio/investigate", json={"company_id": "generalist-inc"}
    )
    assert response.status_code == 409
    assert "BSH_MEMO_ENGLISH_PARALLEL" in response.json()["detail"]


def test_investigate_endpoint_refuses_second_live_run(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env, status="analyzing")
    stream = memo_analysis.job_progress.ProgressLog(
        memo_prep.stream_path(run_dir)
    )
    stream.emit("job_init", kind="memo", report_id=report["id"])  # no terminal
    client = TestClient(app)
    response = client.post(
        "/api/memos/studio/investigate", json={"company_id": "generalist-inc"}
    )
    assert response.status_code == 409
    assert "already in flight" in response.json()["detail"]


def test_investigate_endpoint_bootstraps_studio_mode(studio_env, monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_investigation", started.append)
    client = TestClient(app)
    response = client.post(
        "/api/memos/studio/investigate", json={"company_id": "generalist-inc"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["memo_mode"] == "studio"
    assert started == [body["id"]]
    record = storage.get_report(body["id"])
    assert record["memo_mode"] == "studio"


def test_generate_endpoint_validation_matrix(studio_env, monkeypatch):
    client = TestClient(app)
    # Unknown report.
    assert client.post("/api/memos/studio/nope/generate").status_code == 404
    # Not a studio report.
    auto_report, _ = _make_studio_report(studio_env, status="complete")
    storage.update_report(auto_report["id"], memo_mode="auto")
    response = client.post(f"/api/memos/studio/{auto_report['id']}/generate")
    assert response.status_code == 400

    # Wrong status.
    parked, run_dir = _prepare_generate(studio_env, status="analyzing")
    response = client.post(f"/api/memos/studio/{parked['id']}/generate")
    assert response.status_code == 409

    # Dismissed.
    storage.update_report(
        parked["id"], status="awaiting_studio", dismissed_at="2026-09-01"
    )
    response = client.post(f"/api/memos/studio/{parked['id']}/generate")
    assert response.status_code == 409

    # Missing investigation artifacts.
    storage.update_report(parked["id"], dismissed_at=None)
    spine_path = run_dir / "logs" / "english_units" / "spine.json"
    spine_path.unlink()
    response = client.post(f"/api/memos/studio/{parked['id']}/generate")
    assert response.status_code == 400
    assert "Deep Investigate" in response.json()["detail"]


def test_generate_endpoint_composes_and_spawns_worker(studio_env, monkeypatch):
    report, run_dir = _prepare_generate(studio_env)
    # Seed the card store from the investigation spine so compose has a
    # real editor state.
    memo_editor_store.apply_agent_spine(
        "generalist-inc",
        {**_spine_payload(), "studio_extras": {
            "conclusion_options": [
                {"label": "Invest", "recommendation_sentence": "We recommend participating."},
                {"label": "Decline", "recommendation_sentence": "We recommend passing."},
            ],
        }},
        {"report_id": report["id"], "mode": "studio"},
    )
    started: list[str] = []
    monkeypatch.setattr(
        memo_analysis, "start_generate_from_studio", started.append
    )
    client = TestClient(app)
    response = client.post(f"/api/memos/studio/{report['id']}/generate")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "analyzing"
    assert started == [report["id"]]
    generation = storage.get_report(report["id"])["studio_generate"]
    assert generation["generation_count"] == 1
    assert generation["revision_id"]
    assert generation["spine_sha256"]
    # The composed spine replaced the investigation spine (archived), and
    # the pin sheet landed next to it.
    units_dir = run_dir / "logs" / "english_units"
    composed = json.loads((units_dir / "spine.json").read_text(encoding="utf-8"))
    assert composed["studio_provenance"]["report_id"] == report["id"]
    assert list(units_dir.glob("spine.before_generate.*.json"))
    assert (units_dir / "studio_pin_sheet.md").exists()

    # A second generate (regeneration) from complete bumps the counter.
    storage.update_report(report["id"], status="complete")
    response = client.post(f"/api/memos/studio/{report['id']}/generate")
    assert response.status_code == 202
    assert (
        storage.get_report(report["id"])["studio_generate"]["generation_count"]
        == 2
    )


def test_generate_endpoint_maps_compose_errors(studio_env, monkeypatch):
    report, run_dir = _prepare_generate(studio_env)
    memo_editor_store.apply_agent_spine(
        "generalist-inc", _spine_payload(), {"mode": "studio"}
    )
    # Exclude every risk card → user-fixable 409.
    state = memo_editor_store.get_state("generalist-inc")
    for card in state["sections"]["risks_mitigations"]["cards"]:
        memo_editor_store.patch_card(
            "generalist-inc", "risks_mitigations", card["id"], {"included": False}
        )
    monkeypatch.setattr(
        memo_analysis,
        "start_generate_from_studio",
        lambda report_id: (_ for _ in ()).throw(
            AssertionError("worker must not start on compose errors")
        ),
    )
    client = TestClient(app)
    response = client.post(f"/api/memos/studio/{report['id']}/generate")
    assert response.status_code == 409
    assert "risk cards" in response.json()["detail"]


def test_dismiss_allows_awaiting_studio(studio_env):
    report, _run_dir = _park_report(studio_env)
    client = TestClient(app)
    response = client.post(f"/api/reports/{report['id']}/dismiss")
    assert response.status_code == 200
    assert storage.get_report(report["id"])["dismissed_at"]


# ---- One-Click publish hook -----------------------------------------------


def test_publish_studio_cards_after_auto_run(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env, status="complete")
    storage.update_report(report["id"], memo_mode="auto")
    report = storage.get_report(report["id"])
    units_dir = run_dir / "logs" / "english_units"
    units_dir.mkdir(parents=True)
    (units_dir / "spine.json").write_text(
        json.dumps(_spine_payload()), encoding="utf-8"
    )
    stream = memo_analysis.job_progress.ProgressLog(
        memo_prep.stream_path(run_dir)
    )
    applied: list[tuple] = []
    monkeypatch.setattr(
        memo_editor_store,
        "apply_agent_spine",
        lambda company_id, spine, provenance=None: (
            applied.append((company_id, provenance)) or {"revision_id": "rev-9"}
        ),
    )

    memo_analysis._publish_studio_cards(
        report_id=report["id"], report=report, run_dir=run_dir, stream=stream
    )
    assert applied and applied[0][1]["mode"] == "auto"
    events = _events(run_dir)
    assert any(
        e.get("stage") == "memo_studio_cards_published"
        for e in events
        if e["type"] == "stage"
    )

    # Studio-mode runs never republish (would clobber user edits).
    applied.clear()
    storage.update_report(report["id"], memo_mode="studio")
    memo_analysis._publish_studio_cards(
        report_id=report["id"],
        report=storage.get_report(report["id"]),
        run_dir=run_dir,
        stream=stream,
    )
    assert applied == []


def test_publish_failure_never_raises(studio_env, monkeypatch):
    report, run_dir = _make_studio_report(studio_env, status="complete")
    storage.update_report(report["id"], memo_mode="auto")
    report = storage.get_report(report["id"])
    units_dir = run_dir / "logs" / "english_units"
    units_dir.mkdir(parents=True)
    (units_dir / "spine.json").write_text(
        json.dumps(_spine_payload()), encoding="utf-8"
    )
    stream = memo_analysis.job_progress.ProgressLog(
        memo_prep.stream_path(run_dir)
    )
    monkeypatch.setattr(
        memo_editor_store,
        "apply_agent_spine",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("store exploded")),
    )
    memo_analysis._publish_studio_cards(
        report_id=report["id"], report=report, run_dir=run_dir, stream=stream
    )
    events = _events(run_dir)
    assert any(
        e.get("stage") == "memo_studio_cards_publish_failed"
        for e in events
        if e["type"] == "stage"
    )


def test_bootstrap_dispatches_studio_worker(studio_env, monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_investigation", started.append)
    monkeypatch.setattr(
        memo_analysis,
        "start_analysis",
        lambda report_id: (_ for _ in ()).throw(
            AssertionError("auto worker must not start in studio mode")
        ),
    )
    result = memo_prep.bootstrap_memo_run("generalist-inc", memo_mode="studio")
    assert not result["failed"]
    assert started == [result["report_id"]]
    record = storage.get_report(result["report_id"])
    assert record["memo_mode"] == "studio"
    with pytest.raises(ValueError):
        memo_prep.bootstrap_memo_run(
            "generalist-inc",
            report_type=memo_prep.BUFFETT_REPORT_TYPE,
            memo_mode="studio",
        )
    with pytest.raises(ValueError):
        memo_prep.bootstrap_memo_run("generalist-inc", memo_mode="banana")


# ---- "Investment Report (Auto)" plumbing ----------------------------------


def test_auto_stage_bootstrap_keeps_latestage_kind(studio_env, monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_analysis", started.append)
    result = memo_prep.bootstrap_memo_run(
        "generalist-inc", report_type=memo_prep.AUTO_STAGE_REPORT_TYPE
    )
    assert not result["failed"]
    record = storage.get_report(result["report_id"])
    assert record["report_type"] == memo_prep.AUTO_STAGE_REPORT_TYPE
    assert record["kind"] == memo_prep.LATESTAGE_KIND
    assert record["report_flavor"] == "auto_stage"
    # generalist-inc has no stage signal → calibration guidance, not a gate.
    assert record["scope_check"]["calibrate_only"] is True
    assert "no stage gate" in record["scope_check"]["reason"]
    assert started == [result["report_id"]]


def test_post_report_maps_legacy_investment_report(studio_env, monkeypatch):
    captured: dict = {}

    def fake_bootstrap(company_id, **kw):
        captured.update(kw, company_id=company_id)
        report = storage.create_report_record(
            company_id=company_id,
            report_type=kw["report_type"],
            audience="Internal",
            language="en",
            kind=memo_prep.LATESTAGE_KIND,
            status="ready_for_analysis",
        )
        return {"failed": False, "report_id": report["id"]}

    monkeypatch.setattr(memo_prep, "bootstrap_memo_run", fake_bootstrap)
    client = TestClient(app)
    response = client.post(
        "/api/reports",
        json={
            "company_id": "generalist-inc",
            "report_type": "Investment Report",
            "audience": "Internal",
            "language": "en",
        },
    )
    assert response.status_code == 201, response.text
    # The legacy stub type now routes into the real memo pipeline as Auto.
    assert captured["report_type"] == memo_prep.AUTO_STAGE_REPORT_TYPE


def test_studio_investigate_carries_report_type(studio_env, monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_investigation", started.append)
    client = TestClient(app)
    response = client.post(
        "/api/memos/studio/investigate",
        json={
            "company_id": "generalist-inc",
            "report_type": memo_prep.AUTO_STAGE_REPORT_TYPE,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["report_type"] == memo_prep.AUTO_STAGE_REPORT_TYPE
    assert body["memo_mode"] == "studio"
    assert started == [body["id"]]
    # Buffett is One-Click only.
    response = client.post(
        "/api/memos/studio/investigate",
        json={
            "company_id": "generalist-inc",
            "report_type": memo_prep.BUFFETT_REPORT_TYPE,
        },
    )
    assert response.status_code == 400
