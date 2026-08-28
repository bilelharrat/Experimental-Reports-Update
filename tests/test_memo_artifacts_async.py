"""Tests for the detached (async) analysis-artifacts agent.

Round-2 speedup lever 1: the artifacts agent runs on its own thread from
wrapper entry and is joined after acceptance, so the section wave never
waits on it (in Run B it gated the whole wave at 6.0 m).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from server import claude_runner


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _artifacts_result() -> dict:
    return {
        "analysis_artifacts": {
            "claim_register_md": "# Claim Register",
            "scenario_swim_lanes_md": "# Scenarios",
            "downside_scenario_md": "# Downside",
            "countercase_md": "# Countercase",
            "source_treatment_assumptions_md": "# Sources",
            "risk_sensitivities_md": "# Risks",
        },
        "claude_cost_usd": 0.5,
        "claude_duration_ms": 1500,
    }


def _spine_result() -> dict:
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "Generalist, Inc."},
            "run": {"run_id": "r1", "language": "en"},
            "sources": [
                {
                    "id": "S1",
                    "title": _loc("Data room"),
                    "class": "company-reported",
                    "treatment": _loc("Weighted as company-reported."),
                    "as_of": "2026-05-01",
                }
            ],
        },
        "shared_facts": {
            "recommendation_sentence": "We recommend participating.",
            "key_metrics": [],
            "scenarios": {"bear": "0.8x", "base": "1.5x", "bull": "2.4x"},
            "risks": [
                {
                    "summary": "Concentration",
                    "rating": "7/10",
                    "likelihood": "Medium",
                }
            ],
        },
        "section_notes": {},
        "claude_cost_usd": 1.0,
        "claude_duration_ms": 2000,
    }


def _previous_package() -> dict:
    return {
        "schema_version": 1,
        "company": {"name": "Generalist, Inc."},
        "run": {"run_id": "r1", "language": "en"},
        "sources": _spine_result()["package_skeleton"]["sources"],
        "sections": [
            {
                "id": section_id,
                "blocks": [
                    {"type": "paragraph", "text": _loc(f"prose for {section_id}")}
                ],
            }
            for section_id in claude_runner.MEMO_PACKAGE_SECTION_IDS
        ],
    }


def _parallel_kwargs(tmp_path: Path) -> dict:
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "company_name": "Generalist, Inc.",
        "company_slug": "generalist-inc",
        "run_id": "r1",
        "settings_path": tmp_path / "settings" / "serena_background.md",
        "companies_yaml_path": tmp_path / "companies.yaml",
        "memo_paths": {"en": "memo/en.docx", "zh": "memo/zh.docx"},
    }


def test_flag_helper_requires_both_flags(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    monkeypatch.delenv("BSH_MEMO_ARTIFACTS_ASYNC", raising=False)
    assert claude_runner._memo_artifacts_async_enabled() is False
    monkeypatch.setenv("BSH_MEMO_ARTIFACTS_ASYNC", "1")
    assert claude_runner._memo_artifacts_async_enabled() is False
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    assert claude_runner._memo_artifacts_async_enabled() is True


def test_start_is_idempotent_and_join_persists_cache(tmp_path, monkeypatch):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    calls: list[dict] = []

    def fake_artifacts(**kw):
        calls.append(kw)
        return _artifacts_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts", fake_artifacts
    )
    handle = claude_runner.AsyncArtifacts(run_dir=run_dir, company_name="G")
    assert handle.started is False
    handle.start(common_context="ctx", add_dirs=[run_dir])
    handle.start(common_context="ctx", add_dirs=[run_dir])
    assert handle.started is True
    result, error = handle.join(timeout_sec=10)
    handle.shutdown()
    assert error is None
    assert len(calls) == 1
    assert calls[0]["common_context"] == "ctx"
    assert (
        result["analysis_artifacts"]["claim_register_md"] == "# Claim Register"
    )
    cache = run_dir / "logs" / "english_units" / "analysis_artifacts.json"
    assert json.loads(cache.read_text())["claim_register_md"] == "# Claim Register"


def test_join_reports_agent_failure_without_cache(tmp_path, monkeypatch):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (None, "artifacts exploded"),
    )
    handle = claude_runner.AsyncArtifacts(run_dir=run_dir, company_name="G")
    handle.start(common_context="ctx", add_dirs=[run_dir])
    result, error = handle.join(timeout_sec=10)
    handle.shutdown()
    assert result is None
    assert error == "artifacts exploded"
    cache = run_dir / "logs" / "english_units" / "analysis_artifacts.json"
    assert not cache.exists()


def test_join_without_start_errors(tmp_path):
    handle = claude_runner.AsyncArtifacts(
        run_dir=tmp_path / "memo-run", company_name="G"
    )
    result, error = handle.join(timeout_sec=1)
    handle.shutdown()
    assert result is None
    assert "never started" in error


def test_wrapper_detaches_artifacts_from_wave(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    gate = threading.Event()
    calls: list[dict] = []

    def slow_artifacts(**kw):
        calls.append(kw)
        gate.wait(timeout=30)
        return _artifacts_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts", slow_artifacts
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: (
            {
                "section": {"id": kw["section_id"], "blocks": []},
                "claude_cost_usd": 0.5,
                "claude_duration_ms": 1000,
            },
            None,
        ),
    )
    handle = claude_runner.AsyncArtifacts(
        run_dir=kwargs["run_dir"], company_name="G"
    )
    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, async_artifacts=handle
    )
    # The pass returned while the artifacts agent is still blocked — the
    # wave no longer waits on it.
    assert error is None
    assert result["analysis_artifacts"] is None
    assert result["claude_cost_usd"] == 3.5  # spine 1.0 + five sections
    assert result["claude_duration_ms"] == 3000  # artifacts not in the max
    assert len(calls) == 1
    gate.set()
    join_result, join_error = handle.join(timeout_sec=10)
    handle.shutdown()
    assert join_error is None
    assert (
        join_result["analysis_artifacts"]["risk_sensitivities_md"] == "# Risks"
    )
    cache = kwargs["run_dir"] / "logs" / "english_units" / "analysis_artifacts.json"
    assert cache.exists()


def test_selective_retry_with_pending_detached_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    run_dir = kwargs["run_dir"]
    units_dir = run_dir / "logs" / "english_units"
    units_dir.mkdir(parents=True)
    spine = _spine_result()
    (units_dir / "spine.json").write_text(
        json.dumps(
            {
                "package_skeleton": spine["package_skeleton"],
                "shared_facts": spine["shared_facts"],
                "section_notes": {},
            }
        ),
        encoding="utf-8",
    )
    previous_path = run_dir / "logs" / "memo_package.en.attempt-1.json"
    previous_path.write_text(json.dumps(_previous_package()), encoding="utf-8")

    gate = threading.Event()
    artifact_calls: list[dict] = []

    def slow_artifacts(**kw):
        artifact_calls.append(kw)
        gate.wait(timeout=30)
        return _artifacts_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_artifacts", slow_artifacts
    )
    section_calls: list[str] = []

    def fake_section(**kw):
        section_calls.append(kw["section_id"])
        return {
            "section": {"id": kw["section_id"], "blocks": []},
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    handle = claude_runner.AsyncArtifacts(run_dir=run_dir, company_name="G")

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        async_artifacts=handle,
        previous_validation_errors=[
            "section investment_risk must present risks as per-risk cards"
        ],
        previous_package_path=previous_path,
        attempt=2,
    )

    # The selective retry proceeded without the artifacts cache on disk —
    # the pending detached agent stands in for it — and did not resubmit
    # the artifacts agent into the wave.
    assert error is None
    assert section_calls == ["investment_risk"]
    assert result["analysis_artifacts"] is None
    assert len(artifact_calls) == 1
    gate.set()
    join_result, join_error = handle.join(timeout_sec=10)
    handle.shutdown()
    assert join_error is None
    assert isinstance(join_result["analysis_artifacts"], dict)
