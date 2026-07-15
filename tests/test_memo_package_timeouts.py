"""The memo package passes must run with the long silence budget, not the
180s default — the short default was the dominant memo-generation failure
("memo Chinese package stalled after 180s without output").
"""
from __future__ import annotations

from pathlib import Path

from server import claude_runner


def test_silence_constant_is_long():
    assert claude_runner.MEMO_PACKAGE_SILENCE_TIMEOUT_SEC >= 600


def _capture(monkeypatch):
    captured: dict = {}

    def fake_artifact(**kwargs):
        captured.update(kwargs)
        return ({"memo_package": {}}, None)

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_artifact)
    return captured


def test_bilingual_pass_uses_long_silence_budget(monkeypatch, tmp_path):
    """This is the pass that inherited the 180s default and stalled — it
    must now run with the long budget."""
    captured = _capture(monkeypatch)
    claude_runner.run_memo_fast_bilingual_package(
        run_dir=tmp_path,
        company_name="Test Co",
        run_id="run-1",
        english_package_path=tmp_path / "english.json",
    )
    assert captured["timeout_label"] == "memo Chinese package"
    assert captured["silence_timeout_sec"] == claude_runner.MEMO_PACKAGE_SILENCE_TIMEOUT_SEC


def test_resume_pass_no_longer_hardcodes_180(monkeypatch):
    """The resume path used a hardcoded 180s; guard against it regressing."""
    src = Path(claude_runner.__file__).read_text(encoding="utf-8")
    # The two package-pass call sites and resume must not pass a bare 180.
    assert 'timeout_label="memo package resume"' in src
    resume_idx = src.index('timeout_label="memo package resume"')
    window = src[resume_idx : resume_idx + 300]
    assert "silence_timeout_sec=180" not in window
    assert "MEMO_PACKAGE_SILENCE_TIMEOUT_SEC" in window


def test_memo_artifact_command_streams_partial_messages(monkeypatch, tmp_path):
    """The memo package passes are single tool-free generations; without
    --include-partial-messages the CLI publishes no events for minutes and
    the silence guard fires on a healthy run (Phase 4.3 liveness fix)."""
    captured_cmd: list = []

    class FakeProc:
        stdout = None
        stderr = None
        returncode = 0

        def poll(self):
            return 0

    def fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        raise FileNotFoundError("stop here — we only need the cmd")

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner.subprocess, "Popen", fake_popen)

    result, err = claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema={"type": "object"},
        run_dir=tmp_path,
        progress=None,
        progress_message="m",
        timeout_label="memo test",
        timeout_sec=10,
    )
    assert result is None and err is not None
    assert "--include-partial-messages" in captured_cmd


# ---- Phase 4.4: parallel bilingual pass ----

import json


def _english_package():
    return {
        "company": {"name": "Test Co"},
        "recommendation": {"en": "Participate", "zh": ""},
        "sections": [
            {
                "id": "executive_summary",
                "title": {"en": "Executive Summary", "zh": ""},
                "blocks": [
                    {"type": "paragraph", "text": {"en": "Alpha.", "zh": ""}},
                ],
            },
            {
                "id": "risks",
                "title": {"en": "Risks", "zh": ""},
                "blocks": [
                    {"type": "paragraph", "text": {"en": "Beta.", "zh": ""}},
                ],
            },
        ],
        "sources": [{"label": {"en": "Company materials", "zh": ""}}],
    }


def test_adopt_zh_translations_fills_only_zh():
    source = _english_package()
    translated = json.loads(json.dumps(source))
    translated["recommendation"]["zh"] = "参与"
    translated["recommendation"]["en"] = "TAMPERED"  # en mismatch → rejected
    translated["sources"][0]["label"]["zh"] = "公司材料"
    claude_runner._adopt_zh_translations(source, translated)
    assert source["recommendation"]["en"] == "Participate"
    assert source["recommendation"]["zh"] == ""  # en drifted → not adopted
    assert source["sources"][0]["label"]["zh"] == "公司材料"


def test_adopt_zh_translations_never_overwrites_existing_zh():
    source = {"title": {"en": "Risks", "zh": "风险"}}
    translated = {"title": {"en": "Risks", "zh": "别的"}}
    claude_runner._adopt_zh_translations(source, translated)
    assert source["title"]["zh"] == "风险"


def test_parallel_bilingual_pass_reassembles_sections(monkeypatch, tmp_path):
    package = _english_package()
    package_path = tmp_path / "memo_package.en.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    def fake_unit(*, unit_path, unit_label, **kwargs):
        unit = json.loads(unit_path.read_text(encoding="utf-8"))

        def fill(node):
            if isinstance(node, dict):
                if "en" in node and "zh" in node and not node["zh"]:
                    node["zh"] = f"中文:{node['en']}"
                for v in node.values():
                    fill(v)
            elif isinstance(node, list):
                for v in node:
                    fill(v)

        fill(unit)
        unit["claude_cost_usd"] = 0.5
        unit["claude_duration_ms"] = 1000
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)

    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=tmp_path,
        company_name="Test Co",
        run_id="run-1",
        english_package_path=package_path,
    )
    assert error is None
    merged = result["memo_package"]
    assert merged["recommendation"]["zh"] == "中文:Participate"
    assert merged["sections"][0]["title"]["zh"] == "中文:Executive Summary"
    assert merged["sections"][1]["blocks"][0]["text"]["zh"] == "中文:Beta."
    # English untouched everywhere.
    assert merged["sections"][0]["blocks"][0]["text"]["en"] == "Alpha."
    assert result["claude_cost_usd"] == 1.5  # envelope + 2 sections


def test_parallel_bilingual_pass_falls_back_on_unit_failure(monkeypatch, tmp_path):
    package = _english_package()
    package_path = tmp_path / "memo_package.en.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    monkeypatch.setattr(
        claude_runner,
        "_run_bilingual_unit",
        lambda **kwargs: (None, "boom"),
    )
    fallback_calls = []

    def fake_monolithic(**kwargs):
        fallback_calls.append(kwargs)
        return {"memo_package": {"sections": []}}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package", fake_monolithic
    )

    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=tmp_path,
        company_name="Test Co",
        run_id="run-1",
        english_package_path=package_path,
    )
    assert error is None
    assert len(fallback_calls) == 1


def test_parallel_bilingual_pass_env_kill_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("BSH_MEMO_BILINGUAL_PARALLEL", "0")
    calls = []
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package",
        lambda **kwargs: (calls.append(kwargs) or ({"memo_package": {}}, None)),
    )
    result, error = claude_runner.run_memo_fast_bilingual_package_parallel(
        run_dir=tmp_path,
        company_name="Test Co",
        run_id="run-1",
        english_package_path=tmp_path / "missing.json",
    )
    assert error is None and len(calls) == 1
