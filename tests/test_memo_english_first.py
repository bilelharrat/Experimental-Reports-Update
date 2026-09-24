"""English first: the Chinese stage can never cost the reader the English.

The English DOCX is written the moment the English package is accepted; a
Chinese failure (or a cancel during the Chinese) delivers the English alone
as ``complete_with_warnings`` with ``failure_phase = "chinese_package"``;
Resume of such a run is "Retry Chinese", which translates only what is
still blank and never rewrites the English package or its DOCX.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from server import api, claude_runner, job_progress, memo_analysis, memo_prep, storage
from test_memo_analysis import (  # noqa: F401 — memo_env is a fixture
    _events,
    _make_memo_report,
    _memo_package,
    memo_env,
)


def _analysis_pass(**_kwargs):
    return {
        "summary": "A pass summary long enough to look like work.",
        "key_findings": [],
        "supporting_evidence": [],
        "disconfirming_evidence": [],
        "open_questions": [],
        "memo_uses": [],
    }, None


def _english_package(**_kwargs):
    return {"analysis_artifacts": {}, "memo_package": _memo_package(body_zh="")}, None


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fast_env(memo_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", _analysis_pass)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", _english_package)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **_kw: (None, "monolithic Chinese pass failed too"),
    )
    report, run_dir = _make_memo_report(memo_env)
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit(
        "job_init", kind="memo", report_id=report["id"]
    )
    return report, run_dir


def _run_with_failing_chinese(report, run_dir, monkeypatch, *, seen=None):
    def failing_chinese(**kwargs):
        if seen is not None:
            record = storage.get_report(report["id"])
            seen.update(
                stage=record.get("stage"),
                progress=record.get("progress"),
                english_ready_at=record.get("english_ready_at"),
                english_docx=memo_analysis._memo_paths_abs(record)["en"].exists(),
                status=record.get("status"),
            )
        return None, "Chinese translation failed for section executive_summary: token limit"

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package_parallel", failing_chinese
    )
    memo_analysis._run(report["id"])
    return storage.get_report(report["id"])


def test_the_english_docx_lands_before_the_chinese_stage_starts(fast_env, monkeypatch):
    report, run_dir = fast_env
    en_path = memo_analysis._memo_paths_abs(report)["en"]
    en_path.unlink()
    seen: dict = {}
    _run_with_failing_chinese(report, run_dir, monkeypatch, seen=seen)

    assert seen["english_docx"] is True
    assert seen["english_ready_at"]
    assert seen["stage"] == memo_analysis.ENGLISH_READY_STAGE
    # Above the progress ticker's 78% ceiling, so it cannot write back.
    assert seen["progress"] >= 80
    assert seen["status"] == "analyzing"
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_english_ready" for e in events)


def test_a_chinese_failure_delivers_the_english_with_warnings(fast_env, monkeypatch):
    report, run_dir = fast_env
    paths = memo_analysis._memo_paths_abs(report)

    updated = _run_with_failing_chinese(report, run_dir, monkeypatch)

    assert updated["status"] == "complete_with_warnings"
    assert updated["failure_phase"] == "chinese_package"
    assert "token limit" in updated["failure_detail"]
    assert updated["english_only"] is True
    assert updated["stage"] == "Memo ready — English only (Chinese failed)"
    en_text, zh_text = memo_analysis.CHINESE_FAILED_WARNING
    assert en_text in updated["quality_warnings"]
    assert zh_text in updated["quality_warnings_zh"]
    assert len(updated["quality_warnings_zh"]) == len(updated["quality_warnings"])
    items = updated["quality_warning_items"]
    assert any(
        item["gate"] == "chinese_package" and item["language"] == "ZH" for item in items
    )
    # Warning wording must never read as an English quality failure, or
    # Resume would regenerate the English package.
    for warning in updated["quality_warnings"]:
        assert "quality gate" not in warning.lower()
        assert "memo quality" not in warning.lower()
    assert not memo_analysis._english_quality_gate_needs_package_regen(updated)
    # The English is delivered; the Chinese from an earlier attempt is not
    # served against English it was not written for.
    assert paths["en"].exists()
    assert not paths["zh"].exists()
    assert (run_dir / "logs" / "memo_package.en.json").exists()
    partial = json.loads(
        (run_dir / "logs" / "memo_package.zh_partial.json").read_text(encoding="utf-8")
    )
    assert partial["sections"]
    # The English still went through its lint and fact-check payloads.
    assert updated["memo_quality_lint"] is not None
    assert updated["memo_chinese_parity"] is None
    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "done"
    assert events[-1]["english_only"] is True
    assert set(events[-1]["memo_paths"]) == {"en"}

    summary = api._report_summary(updated)
    assert set(summary["download_urls"]) == {"en"}
    assert summary["resume_available"] is True
    assert summary["english_only"] is True


def test_retry_chinese_runs_only_the_chinese_and_keeps_the_english(
    fast_env, monkeypatch
):
    report, run_dir = fast_env
    _run_with_failing_chinese(report, run_dir, monkeypatch)
    paths = memo_analysis._memo_paths_abs(report)
    english_package = run_dir / "logs" / "memo_package.en.json"
    english_hash = _sha(english_package)
    english_docx_hash = _sha(paths["en"])
    english_docx_mtime = paths["en"].stat().st_mtime_ns

    # What the resume endpoint does before starting the worker.
    record = storage.get_report(report["id"])
    storage.update_report(
        report["id"],
        status="analyzing",
        resume_last_status=record["status"],
        resume_last_failure_phase=record["failure_phase"],
        failure_phase=None,
        failure_detail=None,
    )
    forbidden = lambda **_kw: pytest.fail("Retry Chinese must not rerun English work")  # noqa: E731
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package_parallel", forbidden)
    monkeypatch.setattr(claude_runner, "run_resume_memo_package", forbidden)
    calls: list[dict] = []

    def translate(**kwargs):
        calls.append(kwargs)
        return {"memo_package": _memo_package(), "claude_cost_usd": 0.2}, None

    monkeypatch.setattr(claude_runner, "run_memo_fast_bilingual_package_parallel", translate)

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete", updated.get("quality_warnings")
    assert updated["failure_phase"] is None
    assert not updated.get("english_only")
    assert len(calls) == 1
    assert calls[0]["english_package_path"].name == "memo_package.zh_retry_input.json"
    assert paths["zh"].exists()
    # Never touched: the accepted English package and the English DOCX.
    assert _sha(english_package) == english_hash
    assert _sha(paths["en"]) == english_docx_hash
    assert paths["en"].stat().st_mtime_ns == english_docx_mtime
    events = _events(memo_prep.stream_path(run_dir))
    assert events[0]["type"] == "job_init" and events[0]["retry_chinese"] is True
    assert events[-1]["type"] == "done"


def test_a_failed_retry_chinese_keeps_the_english_delivery(fast_env, monkeypatch):
    report, run_dir = fast_env
    _run_with_failing_chinese(report, run_dir, monkeypatch)
    paths = memo_analysis._memo_paths_abs(report)
    english_docx_hash = _sha(paths["en"])
    storage.update_report(
        report["id"],
        status="analyzing",
        resume_last_failure_phase="chinese_package",
        failure_phase=None,
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package_parallel",
        lambda **_kw: (None, "Chinese translation failed again"),
    )

    memo_analysis._resume(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["failure_phase"] == "chinese_package"
    assert _sha(paths["en"]) == english_docx_hash
    assert not paths["zh"].exists()


def test_a_cancel_during_the_chinese_keeps_the_english(fast_env, monkeypatch):
    report, run_dir = fast_env
    paths = memo_analysis._memo_paths_abs(report)
    (run_dir / "logs" / "memo_package.en.json").write_text(
        json.dumps(_memo_package(body_zh=""), ensure_ascii=False), encoding="utf-8"
    )
    paths["zh"].unlink()  # the Chinese never landed
    storage.update_report(
        report["id"],
        status="analyzing",
        stage=memo_analysis.ENGLISH_READY_STAGE,
        english_ready_at="2026-09-22T10:00:00+00:00",
    )
    monkeypatch.setattr(claude_runner, "terminate_claude_procs_under", lambda _d: 0)

    memo_analysis.cancel_run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["failure_phase"] == "chinese_package"
    assert updated["english_only"] is True
    en_text, zh_text = memo_analysis.CHINESE_CANCELLED_WARNING
    assert updated["quality_warnings"] == [en_text]
    assert updated["quality_warnings_zh"] == [zh_text]
    assert paths["en"].exists()
    assert (run_dir / "logs" / "memo_package.zh_partial.json").exists()
    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "done"
    assert events[-1]["cancelled"] is True
    # Resume is "Retry Chinese" from here.
    assert memo_analysis._chinese_retry_requested(
        {"resume_last_failure_phase": updated["failure_phase"]}, run_dir
    )
    memo_analysis._clear_run_halt(report["id"])


def test_a_cancel_before_the_english_still_fails_the_run(fast_env, monkeypatch):
    report, run_dir = fast_env
    storage.update_report(report["id"], status="analyzing")
    monkeypatch.setattr(claude_runner, "terminate_claude_procs_under", lambda _d: 0)

    memo_analysis.cancel_run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "failed_during_analysis"
    assert updated["failure_phase"] == "cancelled"
    memo_analysis._clear_run_halt(report["id"])


def test_retry_chinese_is_offered_to_studio_runs(fast_env, monkeypatch):
    report, run_dir = fast_env
    _run_with_failing_chinese(report, run_dir, monkeypatch)
    record = storage.update_report(report["id"], memo_mode="studio")
    assert api._report_resume_available(record) is True
    # Any other Studio failure still recovers through Generate, not Resume.
    other = storage.update_report(report["id"], failure_phase="studio_generate")
    assert api._report_resume_available(other) is False


def test_the_parallel_pass_keeps_finished_units_when_one_fails(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    package = _memo_package(body_zh="")
    package["sections"].append(
        {
            "id": "late_extra",
            "blocks": [{"type": "paragraph", "text": {"en": "Second section.", "zh": ""}}],
        }
    )
    english_path = run_dir / "logs" / "memo_package.en.json"
    english_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")

    def fake_unit(**kwargs):
        unit = json.loads(kwargs["unit_path"].read_text(encoding="utf-8"))
        if unit.get("id") == "late_extra":
            return None, "unit failed"

        def fill(node):
            if isinstance(node, dict):
                if "en" in node and "zh" in node and not node["zh"]:
                    node["zh"] = "中文"
                for value in node.values():
                    fill(value)
            elif isinstance(node, list):
                for value in node:
                    fill(value)

        fill(unit)
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **_kw: (None, "monolithic failed"),
    )
    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        run_id="r1",
        english_package_path=english_path,
    )
    assert result is None and error
    partial = json.loads(
        (run_dir / "logs" / claude_runner.MEMO_ZH_PARTIAL_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    first = partial["sections"][0]["blocks"][0]["text"]
    second = partial["sections"][-1]["blocks"][0]["text"]
    assert first["zh"] == "中文"
    assert second["zh"] == ""
    assert second["en"] == "Second section."
