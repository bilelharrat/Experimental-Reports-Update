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


def test_flag_helper_defaults_on(monkeypatch):
    """Default flipped 2026-09-17.

    The whole-package repair must return the entire memo in one
    structured response. At 16,000 words it does not finish: a live
    repair had every section under its cap by minute eight and was killed
    by the 900-second timeout at minute fifteen, losing all of it and the
    run with it. Per-section repair re-emits ~2,000 words per call.
    """
    monkeypatch.delenv("BSH_MEMO_SECTIONAL_REPAIR", raising=False)
    assert claude_runner._memo_sectional_repair_enabled() is True
    monkeypatch.setenv("BSH_MEMO_SECTIONAL_REPAIR", "0")
    assert claude_runner._memo_sectional_repair_enabled() is False


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
        # The re-emit path is the explicit fallback since 2026-09-23; the
        # default is edits mode (tests/test_p1b_repair_edits.py).
        mode="full",
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


def test_envelope_finding_classifier():
    package = _package()
    # Structural error paths rooted at the envelope.
    assert claude_runner._is_envelope_repair_finding(
        package, "sources[0].treatment is required"
    )
    # The quality gate's Section-VI location context (the Run D2 case).
    assert claude_runner._is_envelope_repair_finding(
        package,
        "quality gate sell_side_voice_violation at table 25 row 2 cell 3 "
        '(vi. sources, source classes, and fact reference index): '
        '"...treat the absence of a named lead as a sensitivity." — Rewrite',
    )
    # A quoted snippet that lives in the envelope's source treatments.
    assert claude_runner._is_envelope_repair_finding(
        package,
        'quality gate x at row 1 (unknown): "Weighted as company-reported." '
        "— fix",
    )
    # Section prose and unmatchable text are NOT envelope findings.
    assert not claude_runner._is_envelope_repair_finding(
        package,
        'quality gate x at paragraph 2 (unknown): "original prose for '
        'investment_risk" — fix',
    )
    assert not claude_runner._is_envelope_repair_finding(
        package,
        'quality gate mystery at paragraph 3 (unknown context): '
        '"completely absent snippet text here" — fix',
    )


def test_hybrid_repair_splits_sections_and_envelope(tmp_path, monkeypatch):
    """One envelope finding must no longer drag mappable section findings
    into the whole-package fallback (the Run D2 9-minute round)."""
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    package = _package()
    section_repairs: list[str] = []

    def fake_section_repair(**kw):
        section_repairs.append(kw["section_id"])
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
        }, None

    envelope_calls: list[dict] = []

    def fake_envelope_repair(**kw):
        envelope_calls.append(kw)
        envelope = dict(kw["envelope"])
        envelope["sources"] = [
            dict(kw["envelope"]["sources"][0], treatment=_loc("Fixed treatment."))
        ]
        return {"envelope": envelope}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_section_repair", fake_section_repair
    )
    monkeypatch.setattr(
        claude_runner, "run_memo_envelope_repair", fake_envelope_repair
    )
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=run_dir,
        company_name="G",
        run_id="r1",
        package=package,
        findings=[
            "section investment_risk must present risks as per-risk cards",
            "quality gate sell_side_voice_violation at table 25 row 2 "
            "(vi. sources, source classes, and fact reference index): "
            '"...a named lead as a sensitivity..." — Rewrite',
        ],
    )
    assert error is None
    assert section_repairs == ["investment_risk"]
    assert len(envelope_calls) == 1
    # The envelope repair received only the envelope finding, and no
    # sections.
    assert "sections" not in envelope_calls[0]["envelope"]
    assert len(envelope_calls[0]["findings"]) == 1
    assert "source classes" in envelope_calls[0]["findings"][0]
    # Both repairs spliced; untouched parts preserved.
    assert repaired["sources"][0]["treatment"]["en"] == "Fixed treatment."
    by_id = {s["id"]: s for s in repaired["sections"]}
    assert (
        by_id["investment_risk"]["blocks"][0]["text"]["en"]
        == "repaired investment_risk"
    )
    assert (
        by_id["executive_summary"]["blocks"][0]["text"]["en"]
        == "original prose for executive_summary"
    )
    assert repaired["company"]["name"] == "Generalist, Inc."


def test_envelope_repair_failure_refuses_hybrid(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_section_repair",
        lambda **kw: ({"section": {"id": kw["section_id"], "blocks": []}}, None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_envelope_repair",
        lambda **_kw: (None, "envelope repair timed out"),
    )
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
    assert "envelope" in error and "timed out" in error


def test_repair_refuses_truly_unattributable_findings(tmp_path, monkeypatch):
    def forbidden(**_kw):
        raise AssertionError("no repair worker may run for unmapped findings")

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", forbidden)
    monkeypatch.setattr(claude_runner, "run_memo_envelope_repair", forbidden)
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        package=_package(),
        findings=[
            "section investment_risk must present risks as per-risk cards",
            'quality gate mystery at paragraph 3 (unknown context): '
            '"completely absent snippet text here" — fix',
        ],
    )
    assert repaired is None
    assert "not attributable" in error


def test_envelope_repair_prompt_schema_and_sections_guard(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "envelope": {
                "company": {"name": "G"},
                "sources": [],
                "sections": [{"id": "smuggled"}],
            },
            "claude_cost_usd": 0.2,
        }, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    result, error = claude_runner.run_memo_envelope_repair(
        run_dir=run_dir,
        company_name="G",
        run_id="r1",
        envelope={"company": {"name": "G"}, "sources": []},
        findings=["sources[0].treatment is required"],
    )
    assert error is None
    assert captured["schema"] is claude_runner._MEMO_ENVELOPE_REPAIR_SCHEMA
    assert "ENVELOPE" in captured["prompt"]
    assert "sources[0].treatment" in captured["prompt"]
    # An envelope repair can never smuggle sections into the package.
    assert "sections" not in result["envelope"]
    input_path = (
        run_dir / "logs" / "english_units" / "envelope.repair-input.json"
    )
    assert input_path.exists()


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
