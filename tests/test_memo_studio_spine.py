"""Tests for the Memo Studio standalone spine (investigation seam).

The standalone spine runs once after the Phase-2 passes land: it rebuilds
the shared context, calls the spine agent with the studio-extended schema
(thesis seeds + conclusion stances), and persists
``logs/english_units/spine.json``. The pipeline's own spine keeps the base
schema so One-Click prompts stay byte-identical.
"""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner


def _standalone_kwargs(tmp_path: Path) -> dict:
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


def _spine_agent_result() -> dict:
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "Generalist, Inc."},
            "run": {"run_id": "r1", "language": "en"},
            "sources": [{"id": "S1", "title": {"en": "Data room", "zh": ""}}],
        },
        "shared_facts": {
            "recommendation_sentence": "We recommend participating.",
            "key_metrics": [],
            "scenarios": {"bear": "0.8x", "base": "1.5x", "bull": "2.4x"},
            "risks": [
                {"summary": "Concentration", "rating": "7/10"},
                {"summary": "Execution", "rating": "6/10"},
                {"summary": "Competition", "rating": "5/10"},
                {"summary": "Regulatory", "rating": "3/10"},
            ],
        },
        "section_notes": {"investment_risk": "Lead with concentration."},
        "studio_extras": {
            "thesis_points": [
                {"title": "Contracted demand", "support": "Backlog covers it."}
            ],
            "conclusion_options": [
                {
                    "label": "Invest",
                    "recommendation_sentence": "We recommend participating.",
                },
                {
                    "label": "Decline",
                    "recommendation_sentence": "We recommend passing.",
                },
            ],
        },
    }


def test_studio_schema_extends_base_with_extras():
    base = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    studio = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA_STUDIO
    assert "studio_extras" not in base["properties"]
    extras = studio["properties"]["studio_extras"]
    assert "thesis_points" in extras["properties"]
    assert "conclusion_options" in extras["properties"]
    # The enforced pin sheet is the SAME contract in both schemas.
    assert studio["properties"]["shared_facts"] is base["properties"]["shared_facts"]
    assert studio["required"] == base["required"]


def test_standalone_spine_writes_payload_with_extras(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return _spine_agent_result(), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    kwargs = _standalone_kwargs(tmp_path)

    payload, error = claude_runner.run_memo_english_spine_standalone(
        **kwargs, missing_pass_ids=["competitive_position"]
    )

    assert error is None
    assert captured["schema"] is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA_STUDIO
    assert "studio_extras" in captured["prompt"]
    assert "conclusion_options" in captured["prompt"]
    # Failed passes reuse the speculative-missing prompt block.
    assert "`competitive_position`" in captured["prompt"]
    spine_path = kwargs["run_dir"] / "logs" / "english_units" / "spine.json"
    on_disk = json.loads(spine_path.read_text(encoding="utf-8"))
    assert set(on_disk) == {
        "package_skeleton",
        "shared_facts",
        "section_notes",
        "studio_extras",
    }
    assert payload["studio_extras"]["conclusion_options"][0]["label"] == "Invest"


def test_standalone_spine_without_extras_keeps_base_contract(
    tmp_path, monkeypatch
):
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        result = _spine_agent_result()
        result.pop("studio_extras")
        return result, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    kwargs = _standalone_kwargs(tmp_path)

    payload, error = claude_runner.run_memo_english_spine_standalone(
        **kwargs, studio_extras=False
    )

    assert error is None
    assert captured["schema"] is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    assert "studio_extras" not in captured["prompt"]
    assert "studio_extras" not in payload


def test_standalone_spine_shape_guard(tmp_path, monkeypatch):
    def fake_runner(**kw):
        result = _spine_agent_result()
        result["package_skeleton"]["sources"] = []
        return result, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    kwargs = _standalone_kwargs(tmp_path)

    payload, error = claude_runner.run_memo_english_spine_standalone(**kwargs)

    assert payload is None
    assert "unusable skeleton" in error
    spine_path = kwargs["run_dir"] / "logs" / "english_units" / "spine.json"
    assert not spine_path.exists()


def test_pipeline_spine_prompt_stays_extras_free(tmp_path, monkeypatch):
    """One-Click byte-identity guard: the pipeline's own spine call must
    not mention studio extras."""
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
    )
    assert "studio_extras" not in captured["prompt"]
    assert captured["schema"] is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
