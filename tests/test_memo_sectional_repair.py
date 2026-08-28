"""Tests for the per-section parallel surgical repair (Round 2, lever 3)."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _package() -> dict:
    return {
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
        "sections": [
            {
                "id": section_id,
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": _loc(f"original prose for {section_id}"),
                    }
                ],
            }
            for section_id in claude_runner.MEMO_PACKAGE_SECTION_IDS
        ],
    }


def test_flag_helper_defaults_off(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SECTIONAL_REPAIR", raising=False)
    assert claude_runner._memo_sectional_repair_enabled() is False
    monkeypatch.setenv("BSH_MEMO_SECTIONAL_REPAIR", "1")
    assert claude_runner._memo_sectional_repair_enabled() is True


def test_section_repair_prompt_schema_and_forced_id(tmp_path, monkeypatch):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "section": {"id": "wrong-id", "blocks": []},
            "claude_cost_usd": 0.3,
            "claude_duration_ms": 900,
        }, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    result, error = claude_runner.run_memo_section_repair(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        run_id="r1",
        section={"id": "investment_risk", "blocks": []},
        section_id="investment_risk",
        findings=['quality gate em_dash_bridge: "text — text" — split it'],
    )
    assert error is None
    # The repair cannot rename the section.
    assert result["section"]["id"] == "investment_risk"
    assert captured["schema"] is claude_runner._MEMO_ENGLISH_SECTION_SCHEMA
    assert "ONE SECTION" in captured["prompt"]
    assert "em_dash_bridge" in captured["prompt"]
    # The risk section repair must carry the risk-card contract.
    assert "Risk Register Format Contract" in captured["prompt"]
    input_path = (
        run_dir / "logs" / "english_units" / "investment_risk.repair-input.json"
    )
    assert json.loads(input_path.read_text())["id"] == "investment_risk"


def test_sectional_repair_splices_and_preserves_order(tmp_path, monkeypatch):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    package = _package()
    repaired_ids: list[str] = []

    def fake_section_repair(**kw):
        repaired_ids.append(kw["section_id"])
        return {
            "section": {
                "id": kw["section_id"],
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": _loc(f"repaired {kw['section_id']}"),
                    }
                ],
            },
            "claude_cost_usd": 0.2,
            "claude_duration_ms": 700,
        }, None

    monkeypatch.setattr(
        claude_runner, "run_memo_section_repair", fake_section_repair
    )
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        run_id="r1",
        package=package,
        findings=[
            "section investment_risk must present risks as per-risk cards",
            "missing required section company_overview content",
        ],
    )
    assert error is None
    assert sorted(repaired_ids) == ["company_overview", "investment_risk"]
    assert [s["id"] for s in repaired["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    by_id = {s["id"]: s for s in repaired["sections"]}
    assert (
        by_id["company_overview"]["blocks"][0]["text"]["en"]
        == "repaired company_overview"
    )
    assert (
        by_id["investment_risk"]["blocks"][0]["text"]["en"]
        == "repaired investment_risk"
    )
    # Untouched sections come through unchanged, and the input package is
    # not mutated.
    assert (
        by_id["executive_summary"]["blocks"][0]["text"]["en"]
        == "original prose for executive_summary"
    )
    assert (
        package["sections"][3]["blocks"][0]["text"]["en"]
        == "original prose for investment_risk"
    )


def test_sectional_repair_refuses_unmappable_findings(tmp_path, monkeypatch):
    def forbidden(**_kw):
        raise AssertionError("no section repair may run for envelope errors")

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", forbidden)
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        package=_package(),
        findings=[
            "section investment_risk must present risks as per-risk cards",
            "sources[0].treatment is required",
        ],
    )
    assert repaired is None
    assert "not attributable" in error


def test_sectional_repair_bubbles_section_failure(tmp_path, monkeypatch):
    def flaky(**kw):
        if kw["section_id"] == "investment_risk":
            return None, "repair timed out"
        return {
            "section": {"id": kw["section_id"], "blocks": []},
        }, None

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", flaky)
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        package=_package(),
        findings=[
            "section investment_risk must present risks as per-risk cards",
            "missing required section company_overview content",
        ],
    )
    assert repaired is None
    assert "investment_risk" in error and "timed out" in error
