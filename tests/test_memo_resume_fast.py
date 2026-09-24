"""Resume continues a run from disk instead of rewriting it.

The analysis passes that succeeded are kept (only failed or missing ones
run again); an accepted English package that still validates is reused and
the run continues at the Chinese step; otherwise the English is synthesized
again with the run's OWN structure (a v2 run is never refused or downgraded)
and finalized. A pass failing again on a provider limit stops the resume
and names the cause. Failed-pass stubs never make a run resumable.
"""
from __future__ import annotations

import json

import pytest

from server import api, claude_runner, job_progress, memo_analysis, memo_prep, memo_structure, storage
from test_memo_analysis import (  # noqa: F401 — memo_env is a fixture
    _events,
    _make_memo_report,
    _memo_package,
    memo_env,
)


def _write_pass(run_dir, spec, *, ok: bool, error: str | None = None):
    result = memo_analysis._FastMemoPassResult(
        spec=spec,
        data=(
            {
                "summary": f"{spec.label} summary long enough to be work.",
                "key_findings": [],
                "supporting_evidence": [],
                "disconfirming_evidence": [],
                "open_questions": [],
                "memo_uses": [],
            }
            if ok
            else None
        ),
        error=None if ok else (error or "claude exited 1"),
        duration_ms=10,
        cost_usd=0.1,
    )
    memo_analysis._write_fast_pass_outputs(run_dir=run_dir, result=result)


@pytest.fixture
def resumable(memo_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    report, run_dir = _make_memo_report(memo_env)
    specs = memo_analysis._FAST_MEMO_PASSES
    for index, spec in enumerate(specs):
        _write_pass(run_dir, spec, ok=index >= 2)
    storage.update_report(
        report["id"],
        status="analyzing",
        resume_last_status="failed_during_analysis",
        resume_last_failure_phase="shutdown",
        claude_cost_usd=2.0,
    )
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit("job_init", kind="memo")
    return report, run_dir, [spec.pass_id for spec in specs[:2]]


def _translate(**_kwargs):
    return {"memo_package": _memo_package(), "claude_cost_usd": 0.3}, None


def test_resume_reruns_only_the_failed_passes(resumable, monkeypatch):
    report, run_dir, failed_ids = resumable
    rerun: list[str] = []

    def fake_pass(**kwargs):
        rerun.append(kwargs["pass_id"])
        return {
            "summary": "A rerun pass summary long enough to be work.",
            "key_findings": [],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": [],
        }, None

    english_calls: list[dict] = []

    def fake_english(**kwargs):
        english_calls.append(kwargs)
        return {"analysis_artifacts": {}, "memo_package": _memo_package(body_zh="")}, None

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", fake_pass)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", fake_english)
    monkeypatch.setattr(claude_runner, "run_memo_fast_bilingual_package_parallel", _translate)
    monkeypatch.setattr(
        claude_runner,
        "run_resume_memo_package",
        lambda **_kw: pytest.fail("the legacy one-shot agent must not run"),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert sorted(rerun) == sorted(failed_ids)
    assert len(english_calls) == 1
    assert updated["status"] == "complete", (
        updated.get("failure_detail"),
        updated.get("quality_warnings"),
    )
    assert updated["claude_cost_usd"] >= 2.0
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "resume_passes" for e in events)
    assert events[-1]["type"] == "done"


def test_resume_reuses_a_valid_english_package(resumable, monkeypatch):
    report, run_dir, _failed = resumable
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.en.json").write_text(
        json.dumps(_memo_package(body_zh=""), ensure_ascii=False), encoding="utf-8"
    )
    forbidden = lambda **_kw: pytest.fail("the English is reused")  # noqa: E731
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package_parallel", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_fast_bilingual_package_parallel", _translate)

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    # Delivered; the English was written from 6 of 8 passes and says so.
    assert updated["status"] == "complete_with_warnings", updated.get("quality_warnings")
    assert [item["gate"] for item in updated["quality_warning_items"]] == ["analysis_coverage"]
    assert updated["english_ready_at"]
    assert (run_dir / "logs" / "memo_package.json").exists()
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "resume_english_reuse" for e in events)


def test_resume_stops_on_a_provider_limit(resumable, monkeypatch):
    from server import provider_limits

    report, run_dir, _failed = resumable
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_analysis_pass",
        lambda **_kw: (None, "Claude AI usage limit reached|resets 3pm"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: pytest.fail("no synthesis after a provider limit"),
    )

    try:
        memo_analysis._resume(report["id"])
        updated = storage.get_report(report["id"])
        assert updated["status"] == "failed_during_analysis"
        assert updated["failure_phase"] == "resume"
        assert updated["failure_detail"].startswith("Resume stopped: Claude usage limit")
        # The passes that succeeded are still on disk for the next resume.
        records = memo_analysis._fast_pass_records(run_dir)
        assert sum(1 for r in records.values() if r.get("status") == "ok") >= 6
    finally:
        provider_limits.clear_provider_limit()


def test_a_v2_run_resumes_with_its_own_structure(resumable, monkeypatch):
    report, run_dir, _failed = resumable
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    storage.update_report(report["id"], structure_version="v2")
    seen: dict = {}

    def fake_pass(**kwargs):
        return {
            "summary": "A rerun pass summary long enough to be work.",
            "key_findings": [],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": [],
        }, None

    def capture(**kwargs):
        seen["structure"] = kwargs["structure"]
        return None, "stop after the structure is chosen"

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", fake_pass)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package_parallel", capture)

    memo_analysis._resume(report["id"])

    assert seen["structure"].meta() != memo_structure.LATE.meta()
    updated = storage.get_report(report["id"])
    # The synthesis stub failed on purpose: a named resume failure, not the
    # old "the resume agent only writes the legacy structure" refusal.
    assert "legacy structure" not in (updated.get("failure_detail") or "")


def test_failed_pass_stubs_never_make_a_run_resumable(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    for spec in memo_analysis._FAST_MEMO_PASSES:
        _write_pass(run_dir, spec, ok=False)
    record = storage.update_report(report["id"], status="failed_during_analysis")
    assert memo_analysis._analysis_artifact_paths(run_dir) == []
    assert api._report_resume_available(record) is False
    # One real pass makes it resumable.
    _write_pass(run_dir, memo_analysis._FAST_MEMO_PASSES[0], ok=True)
    assert api._report_resume_available(record) is True


def test_a_transient_pass_failure_is_retried_once(tmp_path, monkeypatch):
    calls: list[int] = []

    def flaky(**_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return None, "API Error: socket connection was closed unexpectedly"
        return {
            "summary": "A pass summary long enough to look like work.",
            "key_findings": [],
            "supporting_evidence": [],
            "disconfirming_evidence": [],
            "open_questions": [],
            "memo_uses": [],
        }, None

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", flaky)
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    stream = job_progress.ProgressLog(run_dir / "logs" / "stream.jsonl")
    result = memo_analysis._run_fast_memo_pass(
        spec=memo_analysis._FAST_MEMO_PASSES[0],
        run_dir=run_dir,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        stream=stream,
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )
    assert result.ok and len(calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        "Claude AI usage limit reached|resets 3pm",
        claude_runner.MEMO_RUN_CANCELLED_ERROR,
        claude_runner.CLAUDE_NOT_SIGNED_IN_ERROR,
    ],
)
def test_limits_logins_and_cancels_are_never_retried(tmp_path, monkeypatch, error):
    calls: list[int] = []

    def failing(**_kwargs):
        calls.append(1)
        return None, error

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", failing)
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    result = memo_analysis._run_fast_memo_pass(
        spec=memo_analysis._FAST_MEMO_PASSES[0],
        run_dir=run_dir,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        stream=job_progress.ProgressLog(run_dir / "logs" / "stream.jsonl"),
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )
    assert not result.ok and len(calls) == 1


def test_a_memo_short_of_passes_is_delivered_with_a_coverage_warning(tmp_path):
    run_dir = tmp_path / "run"
    specs = memo_analysis._FAST_MEMO_PASSES
    for spec in specs:
        _write_pass(run_dir, spec, ok=spec.pass_id not in ("numbers_integrity", "market_sizing"))
    coverage = memo_analysis._analysis_coverage(run_dir)
    assert coverage["passes_ok"] == len(specs) - 2
    assert set(coverage["missing"]) == {"numbers_integrity", "market_sizing"}
    warnings = memo_analysis._RunWarnings()
    memo_analysis._coverage_warning(run_dir, warnings)
    assert f"{len(specs) - 2} of {len(specs)}" in warnings.en[0]
    assert "treat the numbers with extra care" in warnings.en[0]
    assert warnings.items[0]["gate"] == "analysis_coverage"
    # All passes in: nothing to say.
    for spec in specs:
        _write_pass(run_dir, spec, ok=True)
    quiet = memo_analysis._RunWarnings()
    memo_analysis._coverage_warning(run_dir, quiet)
    assert not quiet
