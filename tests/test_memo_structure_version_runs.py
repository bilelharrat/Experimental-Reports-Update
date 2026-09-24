"""The memo template a run was started with decides its structure.

POST /api/reports records ``structure_version`` ("v1" | "v2") from the
per-run override, the user's Settings choice, or the env default — before
the worker starts. The pipeline resolves the structure from it; a v2 run
takes the parallel English wave even where BSH_MEMO_ENGLISH_PARALLEL is off
(v2 has no monolithic twin); records without the field follow the env.
"""
from __future__ import annotations

import pytest

from server import claude_runner, job_progress, memo_analysis, memo_prep, memo_structure, storage
from test_memo_analysis import _make_memo_report, memo_env  # noqa: F401


def _pass(**_kwargs):
    return {
        "summary": "A pass summary long enough to look like work.",
        "key_findings": [],
        "supporting_evidence": [],
        "disconfirming_evidence": [],
        "open_questions": [],
        "memo_uses": [],
    }, None


def _run_until_english(report, run_dir, monkeypatch):
    seen: dict = {}

    def capture_english(**kwargs):
        seen["structure"] = kwargs["structure"]
        seen["parallel"] = claude_runner._memo_english_parallel_enabled(kwargs["run_dir"])
        return None, "stop after the structure is resolved"

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", _pass)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package_parallel", capture_english
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_company_type_classifier",
        lambda **_kw: {"type": "other", "source": "test"},
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    memo_analysis._run_fast_memo_pipeline(
        report_id=report["id"],
        report=storage.get_report(report["id"]),
        run_dir=run_dir,
        stream=stream,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id=str(report["run_id"]),
        memo_paths_abs=memo_analysis._memo_paths_abs(report),
        analysis_session_path=None,
        lessons_path=None,
    )
    return seen


def _is_v1(structure) -> bool:
    return structure.meta() == memo_structure.LATE.meta()


@pytest.fixture
def run(memo_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    report, run_dir = _make_memo_report(memo_env)
    return report, run_dir


def test_a_v2_run_gets_v2_and_the_wave_with_both_flags_off(run, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    report, run_dir = run
    storage.update_report(report["id"], structure_version="v2")

    seen = _run_until_english(report, run_dir, monkeypatch)

    assert not _is_v1(seen["structure"])
    assert seen["structure"].scorecard_weights()
    assert seen["parallel"] is True
    assert claude_runner.memo_run_structure_version(run_dir) == "v2"


def test_a_v1_run_gets_the_standard_memo_with_the_flag_on(run, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    report, run_dir = run
    storage.update_report(report["id"], structure_version="v1")

    seen = _run_until_english(report, run_dir, monkeypatch)

    assert _is_v1(seen["structure"])
    # A v1 run keeps the operator's parallel flag.
    assert seen["parallel"] is False


@pytest.mark.parametrize("flag, expect_v1", [("0", True), ("1", False)])
def test_a_legacy_record_follows_the_env(run, monkeypatch, flag, expect_v1):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", flag)
    report, run_dir = run
    assert "structure_version" not in storage.get_report(report["id"])

    seen = _run_until_english(report, run_dir, monkeypatch)

    assert _is_v1(seen["structure"]) is expect_v1


def test_resume_resolves_the_runs_own_template(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    record = {"structure_stage": {"stage": "late"}, "structure_version": "v1"}
    assert _is_v1(memo_analysis._report_structure(record))
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    record["structure_version"] = "v2"
    assert not _is_v1(memo_analysis._report_structure(record))
    record.pop("structure_version")
    assert _is_v1(memo_analysis._report_structure(record))


def test_compact_mode_still_applies_to_a_v2_run(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    record = {
        "structure_stage": {"stage": "late"},
        "structure_mode": "compact",
        "structure_version": "v2",
    }
    assert memo_analysis._report_structure(record).stage == "late_compact"


def test_bootstrap_writes_the_template_before_the_worker(memo_env, monkeypatch):
    import yaml

    memo_env.mkdir(parents=True, exist_ok=True)
    (memo_env / "companies.yaml").write_text(
        yaml.safe_dump([{"id": "acme-ai", "name": "Acme AI", "status": "private"}]),
        encoding="utf-8",
    )
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    seen: dict = {}

    def start(report_id):
        seen.update(storage.get_report(report_id) or {})

    monkeypatch.setattr(memo_analysis, "start_analysis", start)
    result = memo_prep.bootstrap_memo_run(
        "acme-ai",
        report_type=memo_prep.AUTO_STAGE_REPORT_TYPE,
        audience="LP",
        structure_version="v2",
        structure_version_source="preference",
    )
    assert seen["id"] == result["report_id"]
    assert seen["structure_version"] == "v2"
    assert seen["structure_version_source"] == "preference"
    assert seen["audience"] == "LP"
    assert seen["internal_memo_files"] == []
    # What an outside investor could buy, recorded next to the scope check.
    assert seen["actionability"]["kind"] == "private_round"
    with pytest.raises(ValueError):
        memo_prep.bootstrap_memo_run("acme-ai", structure_version="v9")
