"""Tests for the speculative spine (Round 2, lever 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import claude_runner


@pytest.fixture(autouse=True)
def _pin_speculate_require(monkeypatch):
    """server.main loads the machine-local .env into os.environ mid-suite;
    a widened BSH_MEMO_SPINE_SPECULATE_REQUIRE there changes when the
    speculator launches and breaks the launch-order assertions below.
    Tests that exercise the knob set it explicitly."""
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", raising=False)


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


_PASS_IDS = [
    "arithmetic_denominators",
    "time_base",
    "growth_bridge",
    "deployment_behavior",
    "gtm_operating_burden",
    "replacement_coexistence",
    "competitive_rights",
    "alternative_explanations",
]


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
    )
    kwargs.update(overrides)
    return claude_runner.SpeculativeEnglish(**kwargs)


def test_flag_helpers(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATIVE", raising=False)
    assert claude_runner._memo_spine_speculative_enabled() is False
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATIVE", "1")
    assert claude_runner._memo_spine_speculative_enabled() is False
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    assert claude_runner._memo_spine_speculative_enabled() is True

    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_AFTER", raising=False)
    assert claude_runner._memo_spine_speculate_after() == 6
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_AFTER", "2")
    assert claude_runner._memo_spine_speculate_after() == 4
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_AFTER", "12")
    assert claude_runner._memo_spine_speculate_after() == 7
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_AFTER", "junk")
    assert claude_runner._memo_spine_speculate_after() == 6


def test_speculate_require_helper(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", raising=False)
    assert (
        claude_runner._memo_spine_speculate_require()
        == claude_runner.MEMO_SPINE_PIN_FEEDING_PASSES
    )
    assert claude_runner.MEMO_SPINE_PIN_FEEDING_PASSES == frozenset(
        {"arithmetic_denominators", "time_base", "growth_bridge"}
    )
    for off in ("", "none", "NONE", "0", "  none  "):
        monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", off)
        assert claude_runner._memo_spine_speculate_require() == frozenset()
    monkeypatch.setenv(
        "BSH_MEMO_SPINE_SPECULATE_REQUIRE", " time_base, growth_bridge ,"
    )
    assert claude_runner._memo_spine_speculate_require() == frozenset(
        {"time_base", "growth_bridge"}
    )


class _StubStream:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, **kw) -> None:
        self.events.append((event, kw))


def test_speculator_holds_for_pin_feeding_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", raising=False)
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", fake_spine
    )
    stream = _StubStream()
    spec = _speculator(tmp_path, stream=stream)
    # Five non-pin passes: below the count threshold, no holding stage yet.
    for pass_id in _PASS_IDS[3:]:
        spec.note_pass_result(pass_id, True)
    assert spec.launched is False
    holds = [e for e in stream.events if e[1].get("stage") == "memo_spine_speculation_holding"]
    assert holds == []
    # Sixth pass meets the count, but two pin-feeding passes are missing.
    spec.note_pass_result("arithmetic_denominators", True)
    assert spec.launched is False
    spec.note_pass_result("time_base", True)
    assert spec.launched is False
    holds = [e for e in stream.events if e[1].get("stage") == "memo_spine_speculation_holding"]
    assert len(holds) == 1  # emitted once, not per pass
    assert "growth_bridge" in holds[0][1]["message"]
    # The last pin-feeding pass releases the gate — with nothing late.
    spec.note_pass_result("growth_bridge", True)
    assert spec.launched is True
    result, reason = spec.consume()
    spec.shutdown()
    assert reason is None and isinstance(result, dict)
    assert len(spine_calls) == 1
    assert not spine_calls[0].get("speculative_missing")


def test_failed_required_pass_counts_as_satisfied(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", raising=False)
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", fake_spine
    )
    spec = _speculator(tmp_path)
    for pass_id in ["time_base", "growth_bridge", *_PASS_IDS[3:7]]:
        spec.note_pass_result(pass_id, True)
    assert spec.launched is False  # arithmetic_denominators still missing
    # A FAILED required pass will never land an artifact — nothing to
    # wait for, so it satisfies the gate.
    spec.note_pass_result("arithmetic_denominators", False)
    assert spec.launched is True
    spec.consume()
    spec.shutdown()
    assert spine_calls[0]["speculative_missing"] == [_PASS_IDS[7]]


def test_require_none_restores_count_only_launch(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", "none")
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    spec = _speculator(tmp_path, threshold=4)
    for pass_id in _PASS_IDS[3:7]:  # no pin-feeding pass among them
        spec.note_pass_result(pass_id, True)
    assert spec.launched is True
    spec.consume()
    spec.shutdown()


def test_require_unknown_ids_are_filtered(tmp_path, monkeypatch):
    # An env typo must not silently disable speculation for the whole run.
    monkeypatch.setenv("BSH_MEMO_SPINE_SPECULATE_REQUIRE", "bogus_pass")
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    spec = _speculator(tmp_path, threshold=4)
    for pass_id in _PASS_IDS[3:7]:
        spec.note_pass_result(pass_id, True)
    assert spec.launched is True
    spec.consume()
    spec.shutdown()


def test_spine_prompt_carries_speculative_block(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return _spine_result(), None

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
        speculative_missing=["competitive_rights", "alternative_explanations"],
    )
    assert "Speculative start" in captured["prompt"]
    assert "`competitive_rights`" in captured["prompt"]
    # Without the kwarg the block must be absent (byte-identical prompts).
    captured.clear()
    claude_runner.run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name="G",
        common_context="ctx",
        add_dirs=[run_dir],
    )
    assert "Speculative start" not in captured["prompt"]


def test_delta_check_prompt_and_schema(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"pins_stale": False}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    late = run_dir / "analysis" / "fast" / "competitive_rights.json"
    check, error = claude_runner.run_memo_spine_delta_check(
        run_dir=run_dir,
        shared_facts=_spine_result()["shared_facts"],
        late_pass_files=[late],
    )
    assert error is None and check == {"pins_stale": False}
    assert captured["schema"] is claude_runner.MEMO_SPINE_DELTA_CHECK_SCHEMA
    assert "competitive_rights.json" in captured["prompt"]
    assert "We recommend participating." in captured["prompt"]
    assert "pins_stale: true" in captured["prompt"] or "pins_stale" in captured["prompt"]


def test_speculator_launches_at_threshold_with_late_ids(tmp_path, monkeypatch):
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", fake_spine
    )
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS[:5]:
        spec.note_pass_result(pass_id, True)
    assert spec.launched is False
    spec.note_pass_result(_PASS_IDS[5], True)
    assert spec.launched is True
    # Late completions must not relaunch.
    spec.note_pass_result(_PASS_IDS[6], True)
    spec.note_pass_result(_PASS_IDS[7], False)
    result, reason = spec.consume()
    spec.shutdown()
    assert len(spine_calls) == 1
    assert sorted(spine_calls[0]["speculative_missing"]) == sorted(
        _PASS_IDS[6:]
    )
    # Delta check was skipped: no late artifacts exist on disk.
    assert reason is None
    assert result["shared_facts"]["recommendation_sentence"]


def test_consume_runs_delta_check_and_accepts_fresh_pins(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    delta_calls: list[dict] = []

    def fake_delta(**kw):
        delta_calls.append(kw)
        return {"pins_stale": False}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_spine_delta_check", fake_delta
    )
    spec = _speculator(tmp_path)
    run_dir = tmp_path / "memo-run"
    fast_dir = run_dir / "analysis" / "fast"
    fast_dir.mkdir(parents=True)
    for pass_id in _PASS_IDS:
        (fast_dir / f"{pass_id}.json").write_text(
            json.dumps({"pass_id": pass_id, "status": "ok"}),
            encoding="utf-8",
        )
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    result, reason = spec.consume()
    spec.shutdown()
    assert reason is None and isinstance(result, dict)
    assert len(delta_calls) == 1
    late_files = delta_calls[0]["late_pass_files"]
    assert sorted(path.name for path in late_files) == sorted(
        f"{pid}.json" for pid in _PASS_IDS[6:]
    )


def test_consume_discards_on_stale_pins_or_check_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    run_dir = tmp_path / "memo-run"
    fast_dir = run_dir / "analysis" / "fast"
    fast_dir.mkdir(parents=True)
    for pass_id in _PASS_IDS:
        (fast_dir / f"{pass_id}.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        claude_runner,
        "run_memo_spine_delta_check",
        lambda **_kw: (
            {"pins_stale": True, "reasons": ["valuation moved"]},
            None,
        ),
    )
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    result, reason = spec.consume()
    spec.shutdown()
    assert result is None
    assert "valuation moved" in reason

    # A delta-check failure is conservative: treated as stale.
    monkeypatch.setattr(
        claude_runner,
        "run_memo_spine_delta_check",
        lambda **_kw: (None, "checker exploded"),
    )
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    result, reason = spec.consume()
    spec.shutdown()
    assert result is None
    assert "treated as stale" in reason


def test_consume_discards_on_spine_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (None, "spine exploded"),
    )
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    result, reason = spec.consume()
    spec.shutdown()
    assert result is None
    assert "spine exploded" in reason


def test_speculator_fires_spine_hook_at_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    hooked: list[dict] = []
    spec = _speculator(tmp_path, on_spine=hooked.append)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)
    spec.consume()
    spec.shutdown()
    assert len(hooked) == 1
    assert hooked[0]["package_skeleton"]["company"]["name"] == "Generalist, Inc."


def test_wrapper_consumes_validated_speculative_spine(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (
            {
                "analysis_artifacts": {"claim_register_md": "# C"},
                "claude_cost_usd": 0.5,
                "claude_duration_ms": 1500,
            },
            None,
        ),
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
    spec = _speculator(tmp_path)
    for pass_id in _PASS_IDS:
        spec.note_pass_result(pass_id, True)

    run_dir = tmp_path / "memo-run"
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
    # Exactly one spine call: the speculator's. The wrapper reused it.
    assert len(spine_calls) == 1
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."
    assert (run_dir / "logs" / "english_units" / "spine.json").exists()


def test_wrapper_respins_when_speculation_missed(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        if kw.get("speculative_missing"):
            return None, "speculative spine exploded"
        return _spine_result(), None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: ({"analysis_artifacts": {}}, None),
    )
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: (
            {"section": {"id": kw["section_id"], "blocks": []}},
            None,
        ),
    )
    spec = _speculator(tmp_path, threshold=4)
    for pass_id in _PASS_IDS[:6]:
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
    # Speculative attempt failed, wrapper ran a fresh spine.
    assert len(spine_calls) == 2
    assert spine_calls[0].get("speculative_missing")
    assert not spine_calls[1].get("speculative_missing")
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."
