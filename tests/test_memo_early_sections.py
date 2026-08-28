"""Tests for early section starts keyed to affine passes (Round 2, lever 5)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from server import claude_runner, memo_analysis


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


_PASS_IDS = [spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES]

# The six passes noted first in these tests: satisfies the affinity of
# every early-startable section except company_overview (whose two affine
# passes are the two stragglers).
_FIRST_SIX = [
    "arithmetic_denominators",
    "time_base",
    "growth_bridge",
    "replacement_coexistence",
    "competitive_rights",
    "alternative_explanations",
]
_STRAGGLERS = ["deployment_behavior", "gtm_operating_burden"]


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
        "section_notes": {"investment_risk": "Lead with concentration."},
        "claude_cost_usd": 1.0,
        "claude_duration_ms": 2000,
    }


def _fake_section(calls: list[str]):
    def fake(**kw):
        calls.append(kw["section_id"])
        return {
            "section": {
                "id": kw["section_id"],
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": _loc(f"drafted {kw['section_id']}"),
                    }
                ],
            },
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    return fake


def _speculator(tmp_path: Path, **overrides) -> claude_runner.SpeculativeEnglish:
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        all_pass_ids=list(_PASS_IDS),
        threshold=6,
        early_sections=True,
    )
    kwargs.update(overrides)
    return claude_runner.SpeculativeEnglish(**kwargs)


def test_flag_helper_requires_all_three_flags(monkeypatch):
    for name in (
        "BSH_MEMO_ENGLISH_PARALLEL",
        "BSH_MEMO_SPINE_SPECULATIVE",
        "BSH_MEMO_SECTION_EARLY_START",
    ):
        monkeypatch.delenv(name, raising=False)
    assert claude_runner._memo_section_early_start_enabled() is False
    monkeypatch.setenv("BSH_MEMO_SECTION_EARLY_START", "1")
    assert claude_runner._memo_section_early_start_enabled() is False
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATIVE", "1")
    assert claude_runner._memo_section_early_start_enabled() is True


def test_affinity_map_is_consistent_with_pipeline_ids():
    for section_id, affinity in claude_runner.MEMO_SECTION_PASS_AFFINITY.items():
        assert section_id in claude_runner.MEMO_PACKAGE_SECTION_IDS
        for pass_id in affinity:
            assert pass_id in _PASS_IDS
    # The executive summary distills everything: never early-started.
    assert (
        "executive_summary" not in claude_runner.MEMO_SECTION_PASS_AFFINITY
    )


def test_sections_start_only_after_spine_and_their_affine_passes(
    tmp_path, monkeypatch
):
    gate = threading.Event()

    def gated_spine(**_kw):
        gate.wait(timeout=30)
        return _spine_result(), None

    section_calls: list[str] = []
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", gated_spine
    )
    monkeypatch.setattr(
        claude_runner, "_run_english_section", _fake_section(section_calls)
    )
    spec = _speculator(tmp_path)
    for pass_id in _FIRST_SIX:
        spec.note_pass_result(pass_id, True)
    # Spine still gated: nothing may start.
    assert spec.had_early_sections is False
    gate.set()
    result, reason = spec.consume()
    assert reason is None and isinstance(result, dict)
    # Spine done + six passes: three sections are affinity-satisfied;
    # company_overview waits on the two stragglers.
    started = set(spec.early_futures())
    assert started == {
        "financial_forecast_valuation",
        "investment_highlights",
        "investment_risk",
    }
    spec.note_pass_result(_STRAGGLERS[0], True)
    assert "company_overview" not in spec.early_futures()
    spec.note_pass_result(_STRAGGLERS[1], True)
    futures = spec.early_futures()
    assert set(futures) == {
        "financial_forecast_valuation",
        "investment_highlights",
        "investment_risk",
        "company_overview",
    }
    for future in futures.values():
        section_result, section_error = future.result(timeout=10)
        assert section_error is None
        assert isinstance(section_result["section"], dict)
    spec.shutdown()
    assert "executive_summary" not in section_calls
    # The early sections read the speculator-written spine.
    spine_path = tmp_path / "memo-run" / "logs" / "english_units" / "spine.json"
    assert json.loads(spine_path.read_text())["shared_facts"]


def test_early_sections_fire_the_chase_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    section_calls: list[str] = []
    monkeypatch.setattr(
        claude_runner, "_run_english_section", _fake_section(section_calls)
    )
    hooked: list[str] = []
    spec = _speculator(
        tmp_path, on_section=lambda section_id, _section: hooked.append(section_id)
    )
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    spec.consume()
    for future in spec.early_futures().values():
        future.result(timeout=10)
    spec.shutdown()
    assert sorted(hooked) == sorted(claude_runner.MEMO_SECTION_PASS_AFFINITY)


def test_stale_pins_abandon_early_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner, "_run_english_section", _fake_section([])
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_spine_delta_check",
        lambda **_kw: ({"pins_stale": True, "reasons": ["moved"]}, None),
    )

    class _Stream:
        def __init__(self):
            self.events: list[dict] = []

        def emit(self, type_, **fields):
            self.events.append({"type": type_, **fields})

    stream = _Stream()
    spec = _speculator(tmp_path, stream=stream)
    run_dir = tmp_path / "memo-run"
    fast_dir = run_dir / "analysis" / "fast"
    fast_dir.mkdir(parents=True)
    for pass_id in _PASS_IDS:
        (fast_dir / f"{pass_id}.json").write_text("{}", encoding="utf-8")
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    result, reason = spec.consume()
    assert result is None and "stale" in reason
    assert spec.early_futures() == {}
    assert spec.had_early_sections is True
    discard = [
        e
        for e in stream.events
        if e.get("stage") == "memo_early_sections_discarded"
    ]
    assert len(discard) == 1 and discard[0]["sections"]
    spec.shutdown()


def test_wrapper_harvests_early_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    section_calls: list[str] = []
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner, "_run_english_section", _fake_section(section_calls)
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: ({"analysis_artifacts": {"claim_register_md": "# C"}}, None),
    )
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path / "memo-run",
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        speculative_english=spec,
    )
    spec.shutdown()
    assert error is None
    # Every section drafted exactly once: four early, executive_summary in
    # the wave.
    assert sorted(section_calls) == sorted(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    package = result["memo_package"]
    assert [s["id"] for s in package["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    by_id = {s["id"]: s for s in package["sections"]}
    assert (
        by_id["company_overview"]["blocks"][0]["text"]["en"]
        == "drafted company_overview"
    )
    # spine 1.0 + artifacts 0 (no cost field) + 5 sections at 0.5
    assert result["claude_cost_usd"] == 3.5


def test_wrapper_respins_all_sections_after_stale_pins(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    section_calls: list[str] = []
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner, "_run_english_section", _fake_section(section_calls)
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: ({"analysis_artifacts": {}}, None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_spine_delta_check",
        lambda **_kw: ({"pins_stale": True, "reasons": ["moved"]}, None),
    )
    spec = _speculator(tmp_path)
    run_dir = tmp_path / "memo-run"
    fast_dir = run_dir / "analysis" / "fast"
    fast_dir.mkdir(parents=True)
    for pass_id in _PASS_IDS:
        (fast_dir / f"{pass_id}.json").write_text("{}", encoding="utf-8")
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    # Let the early drafts finish before the wrapper discards them, so the
    # call counting below is deterministic.
    for future in spec.early_futures().values():
        future.result(timeout=10)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=run_dir,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id="r1",
        settings_path=tmp_path / "settings" / "serena_background.md",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "memo/en.docx", "zh": "memo/zh.docx"},
        speculative_english=spec,
    )
    spec.shutdown()
    assert error is None
    # Two spines (speculative + respin) and a full 5-section respin wave on
    # top of the 4 discarded early drafts.
    assert len(spine_calls) == 2
    assert len(section_calls) == 9
    assert section_calls.count("executive_summary") == 1
    assert section_calls.count("company_overview") == 2
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."
