"""Tests for the parallel per-section English package synthesis."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _sample_package() -> dict:
    return {
        "schema_version": 1,
        "company": {"name": "Generalist, Inc."},
        "run": {"run_id": "2026-05-22__191917", "language": "en"},
        "sources": [
            {
                "id": "S1",
                "title": _loc("Company data room"),
                "class": "company-reported",
                "treatment": _loc("Weighted as company-reported."),
                "as_of": "2026-05-01",
            }
        ],
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {"type": "paragraph", "text": _loc("BSH is committing capital.")},
                    {
                        "type": "table",
                        "component": "key_metrics_snapshot",
                        "title": _loc("Key Metrics Snapshot"),
                        "headers": [_loc("Metric"), _loc("Value")],
                        "rows": [[_loc("ARR"), _loc("$10M")]],
                    },
                ],
            },
            {
                "id": "company_overview",
                "blocks": [
                    {"type": "heading", "text": _loc("Board of Directors")},
                    {
                        "type": "paragraph",
                        "text": _loc("Deployment coverage is broad and repeatable."),
                    },
                ],
            },
            {
                "id": "investment_highlights",
                "blocks": [
                    {"type": "paragraph", "text": _loc("Moat treatment.")},
                ],
            },
            {
                "id": "investment_risk",
                "blocks": [
                    {"type": "paragraph", "text": _loc("Risk framing.")},
                ],
            },
            {
                "id": "financial_forecast_valuation",
                "blocks": [
                    {"type": "paragraph", "text": _loc("Valuation sensitivity.")},
                ],
            },
        ],
    }


def _parallel_kwargs(tmp_path: Path) -> dict:
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "company_name": "Generalist, Inc.",
        "company_slug": "generalist-inc",
        "run_id": "2026-05-22__191917",
        "settings_path": tmp_path / "settings" / "serena_background.md",
        "companies_yaml_path": tmp_path / "companies.yaml",
        "memo_paths": {"en": "memo/en.docx", "zh": "memo/zh.docx"},
    }


def _spine_result() -> dict:
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "Generalist, Inc."},
            "run": {"run_id": "2026-05-22__191917", "language": "en"},
            "sources": _sample_package()["sources"],
        },
        "shared_facts": {
            "recommendation_sentence": "We recommend participating.",
            "key_metrics": [
                {
                    "name": "ARR",
                    "value": "$10M",
                    "as_of": "2026-05-01",
                    "source_ids": ["S1"],
                }
            ],
            "scenarios": {"bear": "0.8x", "base": "1.5x", "bull": "2.4x"},
            "risks": [
                {
                    "summary": "Customer concentration",
                    "rating": "7/10",
                    "likelihood": "Medium",
                },
                {
                    "summary": "Execution slip",
                    "rating": "6/10",
                    "likelihood": "High",
                },
                {
                    "summary": "Competitive compression",
                    "rating": "5/10",
                    "likelihood": "Medium",
                },
                {
                    "summary": "Regulatory drag",
                    "rating": "3/10",
                    "likelihood": "Low",
                },
            ],
            "source_topics": {"S1": "Company data room coverage"},
        },
        "section_notes": {"investment_risk": "Lead with concentration."},
        "claude_cost_usd": 1.0,
        "claude_duration_ms": 2000,
    }


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


# ---- error → section mapping ---------------------------------------------


def test_error_mapping_by_section_id_token():
    package = _sample_package()
    assert (
        claude_runner._section_for_validation_error(
            package,
            "section investment_risk must present risks as per-risk cards: ...",
        )
        == "investment_risk"
    )
    assert (
        claude_runner._section_for_validation_error(
            package, "missing required section company_overview"
        )
        == "company_overview"
    )


def test_error_mapping_by_sections_index():
    package = _sample_package()
    assert (
        claude_runner._section_for_validation_error(
            package, "sections[1].blocks[0].text.en is required"
        )
        == "company_overview"
    )
    assert (
        claude_runner._section_for_validation_error(
            package, "sections[99] must be an object"
        )
        is None
    )


def test_error_mapping_by_component():
    package = _sample_package()
    assert (
        claude_runner._section_for_validation_error(
            package,
            "missing required memo component growth_bridge: Financial "
            "Forecast & Valuation / Growth Bridge table",
        )
        == "financial_forecast_valuation"
    )


def test_error_mapping_by_quality_gate_context():
    package = _sample_package()
    error = (
        "quality gate disclosure_gap_without_treatment at table 4 row 5 "
        'cell 2 (key metrics snapshot): "Not disclosed for any period" — '
        "Pair missing disclosure with treatment."
    )
    assert (
        claude_runner._section_for_validation_error(package, error)
        == "executive_summary"
    )
    roman = (
        "quality gate em_dash_bridge at paragraph 3 (ii. company overview): "
        '"text — text" — Split the sentence.'
    )
    assert (
        claude_runner._section_for_validation_error(package, roman)
        == "company_overview"
    )


def test_error_mapping_by_snippet_search():
    package = _sample_package()
    error = (
        "quality gate sell_side_voice_violation at paragraph 9 (unknown "
        'context): "...coverage is broad and repeatable..." — Rewrite.'
    )
    assert (
        claude_runner._section_for_validation_error(package, error)
        == "company_overview"
    )


def test_error_mapping_envelope_errors_are_unmappable():
    package = _sample_package()
    assert (
        claude_runner._section_for_validation_error(
            package, "sources[0].treatment is required"
        )
        is None
    )
    assert (
        claude_runner._map_validation_errors_to_sections(
            package,
            [
                "section investment_risk must present risks as per-risk cards",
                "sources[0].treatment is required",
            ],
        )
        is None
    )


# ---- full parallel pass ---------------------------------------------------


def test_full_parallel_assembles_package(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    section_calls: list[str] = []

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )

    def fake_section(**kw):
        section_calls.append(kw["section_id"])
        # The pinned shared facts must reach every section verbatim.
        assert "We recommend participating." in kw["shared_facts_block"]
        assert "Customer concentration — 7/10 (Medium)" in kw["shared_facts_block"]
        if kw["section_id"] == "investment_risk":
            assert kw["section_note"] == "Lead with concentration."
        else:
            assert kw["section_note"] == ""
        return {
            "section": {
                "id": kw["section_id"],
                "blocks": [
                    {"type": "paragraph", "text": _loc(kw["section_id"])}
                ],
            },
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    package = result["memo_package"]
    assert [s["id"] for s in package["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    assert sorted(section_calls) == sorted(claude_runner.MEMO_PACKAGE_SECTION_IDS)
    assert package["company"]["name"] == "Generalist, Inc."
    assert result["analysis_artifacts"]["claim_register_md"] == "# Claim Register"
    # spine + artifacts agent + 5 sections at 0.5 each
    assert result["claude_cost_usd"] == 4.0
    # spine duration + slowest concurrent worker (artifacts 1500 vs 1000),
    # not the sum of all workers
    assert result["claude_duration_ms"] == 3500
    assert isinstance(result["claude_wall_ms"], int)
    units_dir = kwargs["run_dir"] / "logs" / "english_units"
    assert (units_dir / "spine.json").exists()
    spine_payload = json.loads((units_dir / "spine.json").read_text())
    assert set(spine_payload) == {
        "package_skeleton",
        "shared_facts",
        "section_notes",
    }
    assert (units_dir / "analysis_artifacts.json").exists()


def test_spine_failure_falls_back_to_monolithic(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (None, "spine exploded"),
    )
    fallback_calls = []

    def fake_monolithic(**kw):
        fallback_calls.append(kw)
        return {"analysis_artifacts": {}, "memo_package": _sample_package()}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package", fake_monolithic
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, validation_feedback="- some error"
    )

    assert error is None
    assert len(fallback_calls) == 1
    assert fallback_calls[0]["validation_feedback"] == "- some error"
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."


def test_section_failure_falls_back_to_monolithic(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )

    def fake_section(**kw):
        if kw["section_id"] == "investment_risk":
            return None, "section timed out"
        return {
            "section": {"id": kw["section_id"], "blocks": []},
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (
            {"analysis_artifacts": {}, "memo_package": _sample_package()},
            None,
        ),
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."


def test_env_flag_disables_parallel(tmp_path, monkeypatch):
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("spine must not run when parallel is disabled")
        ),
    )
    monolithic_calls = []

    def fake_monolithic(**kw):
        monolithic_calls.append(kw)
        return {"analysis_artifacts": {}, "memo_package": _sample_package()}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package", fake_monolithic
    )

    _result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert len(monolithic_calls) == 1


def test_parallel_is_disabled_by_default(tmp_path, monkeypatch):
    """The parallel path must be opt-in: the 2026-08-21 NVIDIA validation run
    showed ~5x cost per attempt with no wall-clock win, so the default is the
    monolithic call."""
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("spine must not run by default")
        ),
    )
    monolithic_calls = []

    def fake_monolithic(**kw):
        monolithic_calls.append(kw)
        return {"analysis_artifacts": {}, "memo_package": _sample_package()}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package", fake_monolithic
    )

    _result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert len(monolithic_calls) == 1


# ---- selective section retry ----------------------------------------------


def _seed_selective_state(kwargs: dict, *, spine_payload: dict | None = None) -> Path:
    """Write the previous attempt package and spine cache the selective path
    needs, returning the previous package path."""
    run_dir = kwargs["run_dir"]
    units_dir = run_dir / "logs" / "english_units"
    units_dir.mkdir(parents=True, exist_ok=True)
    spine = _spine_result()
    if spine_payload is None:
        spine_payload = {
            "package_skeleton": spine["package_skeleton"],
            "shared_facts": spine["shared_facts"],
            "section_notes": spine["section_notes"],
        }
    (units_dir / "spine.json").write_text(
        json.dumps(spine_payload), encoding="utf-8"
    )
    (units_dir / "analysis_artifacts.json").write_text(
        json.dumps(_artifacts_result()["analysis_artifacts"]), encoding="utf-8"
    )
    previous_path = run_dir / "logs" / "memo_package.en.attempt-1.json"
    previous_path.write_text(json.dumps(_sample_package()), encoding="utf-8")
    return previous_path


def test_selective_retry_reruns_only_named_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    previous_path = _seed_selective_state(kwargs)
    section_calls: list[str] = []

    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("selective retry must not regenerate the spine")
        ),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError(
                "selective retry must reuse cached artifacts, not re-run them"
            )
        ),
    )

    def fake_section(**kw):
        section_calls.append(kw["section_id"])
        assert kw["validation_errors"], "retry must receive its errors"
        assert kw["previous_section_path"] is not None
        assert kw["previous_section_path"].exists()
        assert "We recommend participating." in kw["shared_facts_block"]
        return {
            "section": {
                "id": kw["section_id"],
                "blocks": [{"type": "paragraph", "text": _loc("fixed")}],
            },
            "claude_cost_usd": 0.25,
            "claude_duration_ms": 500,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        validation_feedback="- section investment_risk must present risks as per-risk cards",
        previous_validation_errors=[
            "section investment_risk must present risks as per-risk cards"
        ],
        previous_package_path=previous_path,
    )

    assert error is None
    assert section_calls == ["investment_risk"]
    package = result["memo_package"]
    assert [s["id"] for s in package["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    risk = package["sections"][3]
    assert risk["blocks"][0]["text"]["en"] == "fixed"
    # untouched sections spliced verbatim from the previous attempt
    assert (
        package["sections"][0]["blocks"][0]["text"]["en"]
        == "BSH is committing capital."
    )
    assert result["analysis_artifacts"]["claim_register_md"] == "# Claim Register"
    assert result["claude_cost_usd"] == 0.25


def test_selective_retry_with_unmappable_error_runs_full_pass(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    previous_path = _seed_selective_state(kwargs)
    spine_calls = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )
    section_calls: list[str] = []

    def fake_section(**kw):
        section_calls.append(kw["section_id"])
        return {
            "section": {"id": kw["section_id"], "blocks": []},
            "claude_cost_usd": 0.1,
            "claude_duration_ms": 100,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    _result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        validation_feedback="- sources[0].treatment is required",
        previous_validation_errors=["sources[0].treatment is required"],
        previous_package_path=previous_path,
    )

    assert error is None
    assert len(spine_calls) == 1
    assert spine_calls[0]["validation_feedback"] == "- sources[0].treatment is required"
    assert sorted(section_calls) == sorted(claude_runner.MEMO_PACKAGE_SECTION_IDS)


# ---- spine-lite specifics --------------------------------------------------


def test_spine_lite_schema_drops_artifacts_and_bounds_output():
    schema = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    assert "analysis_artifacts" not in schema["properties"]
    assert "shared_facts" in schema["required"]
    facts = schema["properties"]["shared_facts"]
    risks = facts["properties"]["risks"]
    assert risks["minItems"] == 4 and risks["maxItems"] == 6
    assert risks["items"]["properties"]["rating"]["pattern"] == "^(10|[1-9])/10$"
    assert risks["items"]["properties"]["likelihood"]["enum"] == [
        "High",
        "Medium",
        "Low",
    ]
    recommendation = facts["properties"]["recommendation_sentence"]
    assert recommendation["maxLength"] == 300
    artifacts_schema = claude_runner.MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA
    artifact_props = artifacts_schema["properties"]["analysis_artifacts"][
        "properties"
    ]
    assert artifact_props["claim_register_md"]["maxLength"] == 8000
    assert "content_coverage_md" in artifact_props


def test_artifacts_agent_failure_degrades_to_stubs(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (None, "artifacts exploded"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("artifacts failure must not fall back the pass")
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

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert result["analysis_artifacts"] == {}
    artifacts_path = (
        kwargs["run_dir"] / "logs" / "english_units" / "analysis_artifacts.json"
    )
    assert json.loads(artifacts_path.read_text()) == {}


def test_stale_spine_format_forces_full_pass(tmp_path, monkeypatch):
    """A cached spine.json from the pre-spine-lite format (section_briefs,
    no shared_facts) must not feed the selective retry."""
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    spine = _spine_result()
    previous_path = _seed_selective_state(
        kwargs,
        spine_payload={
            "package_skeleton": spine["package_skeleton"],
            "section_briefs": {
                sid: f"Brief for {sid}."
                for sid in claude_runner.MEMO_PACKAGE_SECTION_IDS
            },
        },
    )
    spine_calls: list[dict] = []

    def fake_spine(**kw):
        spine_calls.append(kw)
        return _spine_result(), None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )
    section_calls: list[str] = []
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: (
            section_calls.append(kw["section_id"])
            or (
                {
                    "section": {"id": kw["section_id"], "blocks": []},
                    "claude_cost_usd": 0.1,
                    "claude_duration_ms": 100,
                },
                None,
            )
        ),
    )

    _result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        previous_validation_errors=[
            "section investment_risk must present risks as per-risk cards"
        ],
        previous_package_path=previous_path,
    )

    assert error is None
    assert len(spine_calls) == 1, "stale spine cache must force the full pass"
    assert sorted(section_calls) == sorted(claude_runner.MEMO_PACKAGE_SECTION_IDS)


def test_parallel_prompts_share_common_system_prefix(tmp_path, monkeypatch):
    """The shared context must ride --append-system-prompt byte-identically
    on every phase-3 call, and the five section prompts must share their
    leading region so nothing defeats the prompt cache."""
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    captured: list[dict] = []

    def fake_artifact_runner(**kw):
        captured.append(kw)
        schema = kw["schema"]
        if schema is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA:
            return _spine_result(), None
        if schema is claude_runner.MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA:
            return _artifacts_result(), None
        section_id = kw["timeout_label"].split("(")[-1].rstrip(")")
        return {
            "section": {"id": section_id, "blocks": []},
            "claude_cost_usd": 0.1,
            "claude_duration_ms": 100,
        }, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact_runner
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None and result is not None
    assert len(captured) == 7  # spine + artifacts + 5 sections
    shared = {kw["append_system_prompt"] for kw in captured}
    assert len(shared) == 1, "system-prompt context must be byte-identical"
    context = shared.pop()
    assert claude_runner.MEMO_PACKAGE_SOURCES_CONTRACT.splitlines()[0] in context
    assert claude_runner.MEMO_CONTENT_PARITY_CONTRACT.splitlines()[0] in context
    assert "first-person sponsor voice" in context
    for kw in captured:
        assert claude_runner.HUMAN_EXEC_MEMO_VOICE_CONTRACT not in kw["prompt"]
    section_prompts = [
        kw["prompt"]
        for kw in captured
        if kw["schema"] is claude_runner._MEMO_ENGLISH_SECTION_SCHEMA
    ]
    assert len(section_prompts) == 5
    heads = {prompt.split("## Your section")[0] for prompt in section_prompts}
    assert len(heads) == 1, "section prompts must share their leading region"


# ---- chasing hook contract -------------------------------------------------


def test_full_parallel_fires_section_hook_on_success_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )

    def fake_section(**kw):
        if kw["section_id"] == "investment_risk":
            return None, "section timed out"
        return {
            "section": {"id": kw["section_id"], "blocks": []},
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (
            {"analysis_artifacts": {}, "memo_package": _sample_package()},
            None,
        ),
    )
    hook_calls: list[str] = []

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        on_section=lambda section_id, section: hook_calls.append(section_id),
    )

    assert error is None
    assert "investment_risk" not in hook_calls
    assert sorted(hook_calls) == sorted(
        sid
        for sid in claude_runner.MEMO_PACKAGE_SECTION_IDS
        if sid != "investment_risk"
    )


def test_spine_hook_fires_after_spine_file_written(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
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
    seen: list[dict] = []

    def on_spine(payload):
        spine_file = kwargs["run_dir"] / "logs" / "english_units" / "spine.json"
        assert spine_file.exists(), "hook must fire after the spine is written"
        assert isinstance(payload.get("shared_facts"), dict)
        assert payload["package_skeleton"]["sources"]
        seen.append(payload)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, on_spine=on_spine
    )

    assert error is None
    assert len(seen) == 1


def test_hook_exceptions_do_not_fail_the_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_spine_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
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

    def explode(*_args):
        raise RuntimeError("chaser bug")

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, on_spine=explode, on_section=explode
    )

    assert error is None
    assert result["memo_package"]["company"]["name"] == "Generalist, Inc."


def test_selective_retry_never_fires_hooks(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    previous_path = _seed_selective_state(kwargs)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("no spine on retry")),
    )
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: (
            {
                "section": {"id": kw["section_id"], "blocks": []},
                "claude_cost_usd": 0.25,
                "claude_duration_ms": 500,
            },
            None,
        ),
    )
    hook_calls: list[str] = []

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        previous_validation_errors=[
            "section investment_risk must present risks as per-risk cards"
        ],
        previous_package_path=previous_path,
        on_spine=lambda payload: hook_calls.append("spine"),
        on_section=lambda section_id, section: hook_calls.append(section_id),
    )

    assert error is None
    assert hook_calls == []
