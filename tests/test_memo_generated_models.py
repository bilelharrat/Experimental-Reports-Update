"""Which models actually generated a memo (``generated_with``).

The quality tier often leaves a role's model to the CLI default, so the
tier cannot say what ran. Each subprocess's stream does — the system/init
event names the session model, each assistant message the model that
answered — and the first model seen per role is recorded for the run,
stamped on the package the documents are rendered from
(``package["run"]["generated_with"]``) and on the report record.
"""
from __future__ import annotations

import io
import json

from server import claude_runner, memo_analysis, memo_engine, memo_structure, storage
from test_memo_analysis import memo_env  # noqa: F401 — a fixture


def _stream_lines(*, init_model=None, assistant_model=None, result=None) -> str:
    events = []
    if init_model:
        events.append({"type": "system", "subtype": "init", "session_id": "s", "model": init_model, "tools": []})
    if assistant_model:
        events.append(
            {
                "type": "assistant",
                "message": {"model": assistant_model, "content": [{"type": "text", "text": "working"}]},
            }
        )
    events.append(
        result
        or {
            "type": "result",
            "subtype": "success",
            "result": json.dumps({"answer": 1}),
            "total_cost_usd": 0.01,
            "duration_ms": 5,
            "usage": {},
        }
    )
    return "".join(json.dumps(event) + "\n" for event in events)


class _FakeProc:
    def __init__(self, cmd, cwd, lines: str):
        self.cmd = cmd
        self.pid = 4242
        self._bsh_spawn_cwd = cwd
        self.returncode = 0
        self.stdout = io.StringIO(lines)
        self.stderr = io.StringIO("")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


def _run_funnel(monkeypatch, run_dir, role, lines):
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        claude_runner, "_popen_claude", lambda cmd, **kwargs: _FakeProc(cmd, kwargs.get("cwd"), lines)
    )
    return claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=60,
        role=role,
    )


def test_the_model_comes_from_the_stream_not_the_tier(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    data, error = _run_funnel(
        monkeypatch,
        run_dir,
        "SECTION",
        _stream_lines(init_model="claude-sonnet-4-6", assistant_model="claude-sonnet-4-6-20260801"),
    )
    assert error is None and data["answer"] == 1
    # The model that answered wins over the session's.
    assert claude_runner.memo_run_models(run_dir) == {"SECTION": "claude-sonnet-4-6-20260801"}
    # First seen per role; persisted for a resume after a restart.
    _run_funnel(monkeypatch, run_dir, "SECTION", _stream_lines(init_model="claude-haiku-4-5"))
    _run_funnel(monkeypatch, run_dir, "SPINE", _stream_lines(init_model="claude-opus-4-7"))
    expected = {"SECTION": "claude-sonnet-4-6-20260801", "SPINE": "claude-opus-4-7"}
    assert claude_runner.memo_run_models(run_dir) == expected
    on_disk = json.loads((run_dir / "logs" / claude_runner.MEMO_MODELS_FILENAME).read_text(encoding="utf-8"))
    assert on_disk == expected
    monkeypatch.setattr(claude_runner, "_MEMO_RUN_MODELS", {})
    assert claude_runner.memo_run_models(run_dir) == expected


def test_synthetic_messages_failed_calls_and_unnamed_stages_record_nothing(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _run_funnel(
        monkeypatch,
        run_dir,
        "ENGLISH",
        _stream_lines(init_model="claude-opus-4-7", assistant_model="<synthetic>"),
    )
    assert claude_runner.memo_run_models(run_dir) == {"ENGLISH": "claude-opus-4-7"}
    bad = {"type": "result", "subtype": "success", "result": "not json at all"}
    _run_funnel(monkeypatch, run_dir, "REPAIR", _stream_lines(init_model="claude-opus-4-7", result=bad))
    _run_funnel(monkeypatch, run_dir, None, _stream_lines(init_model="claude-opus-4-7"))
    assert claude_runner.memo_run_models(run_dir) == {"ENGLISH": "claude-opus-4-7"}


def test_a_gemini_stage_records_the_memo_gemini_model(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    monkeypatch.setenv("BSH_MEMO_GEMINI_MODEL", "gemini-3.8-pro")
    monkeypatch.setattr(memo_engine, "run_artifact", lambda **_kw: ({"answer": 1}, None))
    try:
        claude_runner._run_memo_local_json_artifact(
            prompt="p",
            schema={"type": "object"},
            run_dir=run_dir,
            progress=None,
            progress_message="m",
            timeout_label="t",
            timeout_sec=60,
            role="TRANSLATION",
        )
    finally:
        memo_engine.clear_run_engine(run_dir)
    assert claude_runner.memo_run_models(run_dir) == {"TRANSLATION": "gemini-3.8-pro"}


def test_the_generated_with_shape(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(claude_runner, "SERVER_CODE_VERSION", "abc1234-dirty")
    for role, model in (
        ("ANALYSIS_PASS", "claude-sonnet-4-6"),
        ("SPINE", "claude-opus-4-7"),
        ("SECTION", "claude-opus-4-7"),
        ("TRANSLATION", "claude-sonnet-4-6"),
    ):
        claude_runner.record_memo_run_model(run_dir, role, model)
    report = {"model_quality": "balanced", "structure_version": "v2", "structure_mode": "compact"}
    structure = memo_structure.active_structure("late", mode="compact", version="v2")
    assert memo_analysis._generated_with(report, run_dir, structure=structure) == {
        "engine": "claude",
        "quality": "balanced",
        "template": "ic_v2",
        "structure": {"stage": structure.stage, "version": structure.version, "mode": "compact"},
        "models": {
            "ANALYSIS_PASS": "claude-sonnet-4-6",
            "SPINE": "claude-opus-4-7",
            "SECTION": "claude-opus-4-7",
            "TRANSLATION": "claude-sonnet-4-6",
        },
        "writer_model": "claude-opus-4-7",
        "translation_model": "claude-sonnet-4-6",
        "code_version": "abc1234-dirty",
    }
    # The monolithic English call (alone, or as the wave's fallback) is the
    # writer when it ran; a record without a template reads its structure.
    claude_runner.record_memo_run_model(run_dir, "ENGLISH", "claude-opus-4-6")
    legacy = memo_analysis._generated_with({}, run_dir, structure=memo_structure.LATE)
    assert legacy["writer_model"] == "claude-opus-4-6"
    assert legacy["template"] == "standard" and legacy["quality"] == "best"
    assert legacy["structure"] == {"stage": "late", "version": 1, "mode": "full"}


def test_the_code_version_never_fails(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("no git here")

    monkeypatch.setattr(claude_runner.subprocess, "run", boom)
    assert claude_runner._git_code_version() is None


# ---- stamped on the package and the record --------------------------------------------------


def test_finalize_stamps_the_package_and_the_record(memo_env, monkeypatch):
    from fastapi.testclient import TestClient

    from server.main import app
    from test_memo_analysis import _make_memo_report, _write_memo_package

    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    monkeypatch.setattr(claude_runner, "SERVER_CODE_VERSION", "abc1234")
    report, run_dir = _make_memo_report(memo_env)

    def fake_run_investment_memo(**_kwargs):
        _write_memo_package(run_dir)
        claude_runner.record_memo_run_model(run_dir, "SKILL", "claude-opus-4-7")
        return {"ok": True, "cost_usd": 1.0, "duration_ms": 1000}

    monkeypatch.setattr(claude_runner, "run_investment_memo", fake_run_investment_memo)
    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] in ("complete", "complete_with_warnings")
    facts = updated["generated_with"]
    assert facts["engine"] == "claude"
    assert facts["models"] == {"SKILL": "claude-opus-4-7"}
    assert facts["writer_model"] == facts["translation_model"] == "claude-opus-4-7"
    assert facts["code_version"] == "abc1234"
    package = json.loads((run_dir / "logs" / "memo_package.json").read_text(encoding="utf-8"))
    assert package["run"]["generated_with"] == facts
    body = TestClient(app).get(f"/api/reports/{report['id']}").json()
    assert body["generated_with"] == facts


def test_the_english_package_carries_the_stamp_at_acceptance(memo_env, monkeypatch):
    from test_memo_analysis import _memo_package
    from test_memo_risk_card_triage import _run_pipeline

    monkeypatch.setattr(claude_runner, "SERVER_CODE_VERSION", "abc1234")
    result, run_dir, _english, _repairs = _run_pipeline(
        memo_env,
        monkeypatch,
        english=lambda: _memo_package(body_zh=""),
        repair=lambda: (None, "unused"),
    )
    assert result.get("ok") is True
    english = json.loads((run_dir / "logs" / "memo_package.en.json").read_text(encoding="utf-8"))
    stamp = english["run"]["generated_with"]
    assert stamp["engine"] == "claude" and stamp["code_version"] == "abc1234"
    assert stamp["template"] in ("standard", "ic_v2")
    bilingual = json.loads((run_dir / "logs" / "memo_package.json").read_text(encoding="utf-8"))
    assert bilingual["run"]["generated_with"]["code_version"] == "abc1234"


def test_a_buffett_run_records_its_model(tmp_path, monkeypatch):
    from server import buffett_memo_analysis
    from test_buffett_memo import _english_memo, _finalize_env, _package, _Stream, _valuation_fields

    package = _package(**_valuation_fields(), markdown_en=_english_memo())
    report, run_dir = _finalize_env(tmp_path, monkeypatch, package)
    claude_runner.record_memo_run_model(run_dir, "BUFFETT", "claude-opus-4-7")
    assert buffett_memo_analysis._finalize_from_package(
        report_id=report["id"],
        report=report,
        run_dir=run_dir,
        stream=_Stream(),
        result={"cost_usd": 1.0, "duration_ms": 10, "web_lookups": 3},
    )
    facts = storage.get_report(report["id"])["generated_with"]
    assert facts["engine"] == "claude" and facts["template"] == "buffett"
    assert facts["models"] == {"BUFFETT": "claude-opus-4-7"}
    assert facts["writer_model"] == facts["translation_model"] == "claude-opus-4-7"
    assert "structure" not in facts
    stored = json.loads((run_dir / "logs" / "memo_package.json").read_text(encoding="utf-8"))
    assert stored["run"]["generated_with"] == facts
