"""Tests for the parallel per-section English package synthesis."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner, memo_engine, memo_structure


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
                    {"type": "paragraph", "text": _loc("Recommendation: BSH commits capital.")},
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


def test_remediation_advice_never_decides_the_section(monkeypatch):
    """A finding's coaching tail must not route the repair.

    Live run 2026-09-16: the gate flagged a paragraph in "valuation,
    returns & exit" and closed with "...named terms, plain risks." The id
    scan saw "risks", sent the repair to the wrong section, and the repair
    introduced a second violation there. Two package attempts (8.7m and
    1.2m) died on the same untouched paragraph.
    """
    from server import memo_structure

    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    # the compact profile the live run used: `valuation_returns`, whose
    # rendered title is "valuation, returns & exit"
    structure = memo_structure.active_structure("late", "compact")
    package = {
        "sections": [{"id": sid, "blocks": []} for sid in structure.section_ids]
    }
    error = (
        "quality gate sell_side_voice_violation at paragraph 91 "
        '(v. valuation, returns & exit): "...tilted upward: the bear case '
        "loses more than half the capital while the bull returns five "
        "times, so position size matters more than the point estimate. "
        'Sources: S1, S4, S8" — Rewrite buyer-side, detached, '
        "treatment-speak, or stock participation slogans as LP co-invest "
        "English: firm as subject, named terms, plain risks."
    )
    assert (
        claude_runner._section_for_validation_error(package, error, structure)
        == "valuation_returns"
    )


def test_error_location_stops_at_the_quote_or_the_advice():
    assert claude_runner._error_location(
        'gate x at paragraph 9 (vi. risks): "quoted" — advice'
    ) == "gate x at paragraph 9 (vi. risks): "
    assert claude_runner._error_location(
        "gate x at paragraph 9 (vi. risks) — advice about risks"
    ) == "gate x at paragraph 9 (vi. risks) "
    # nothing to cut: the whole error locates the defect
    assert (
        claude_runner._error_location("missing required section company_overview")
        == "missing required section company_overview"
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


def test_parallel_switched_off_takes_the_monolithic_call(tmp_path, monkeypatch):
    """With the switch at 0 the English stage is one monolithic call. The
    parallel path was opt-in until 2026-09-22 (the 2026-08-21 NVIDIA run
    measured ~5x cost per attempt); it is now the default, because the v2
    structure has no monolithic twin — see server/memo_flags.py."""
    kwargs = _parallel_kwargs(tmp_path)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
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
        == "Recommendation: BSH commits capital."
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
    assert artifact_props["claim_register_md"]["maxLength"] == 16000
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


def _write_spine_pieces(run_dir, payload, structure=None):
    """Lay a spine payload out as the per-part files the agent would write.

    Uses the production piece plan, so a test can never disagree with it
    about which key belongs in which file.
    """
    import json as _json

    from server import memo_structure as _ms

    structure = structure or _ms.LATE
    schema = claude_runner.memo_fast_english_spine_schema(structure)
    plan = claude_runner._spine_piece_plan(run_dir, schema)
    for _stem, target, keys, _required, _what, path in plan:
        bucket = payload.get(target, {}) if target else payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _json.dumps(
                {key: bucket[key] for key in keys if key in bucket},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return plan


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
        if schema is claude_runner._MEMO_SPINE_MANIFEST_SCHEMA:
            # the spine delivers its parts as files and returns a receipt
            _write_spine_pieces(kwargs["run_dir"], _spine_result())
            return {"pieces": []}, None
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
    assert "The conclusion is a recommendation" in context
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


# ---- Memo Studio: pinned spine ------------------------------------------


def _write_pinned_spine(kwargs: dict, payload: dict | None = None) -> Path:
    units_dir = kwargs["run_dir"] / "logs" / "english_units"
    units_dir.mkdir(parents=True, exist_ok=True)
    if payload is None:
        spine = _spine_result()
        payload = {
            "package_skeleton": spine["package_skeleton"],
            "shared_facts": spine["shared_facts"],
            "section_notes": spine["section_notes"],
            # A studio spine carries extras; the orchestrator must tolerate
            # (and preserve) the extra key.
            "studio_extras": {"thesis_points": []},
        }
    path = units_dir / "spine.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _StubSpeculator:
    """consume() must never run in pinned mode."""

    had_early_sections = False

    def consume(self, progress=None):
        raise AssertionError("speculative consume must be skipped when pinned")

    def early_futures(self):
        return {}


def test_pinned_spine_skips_spine_agent_and_uses_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    pinned = _write_pinned_spine(kwargs)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("spine agent must not run in pinned mode")
        ),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )

    def fake_section(**kw):
        # The user-composed pins must reach the workers verbatim.
        assert "We recommend participating." in kw["shared_facts_block"]
        return {
            "section": {
                "id": kw["section_id"],
                "blocks": [{"type": "paragraph", "text": _loc("x")}],
            },
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    hook_payloads: list[dict] = []

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        pinned_spine_path=pinned,
        speculative_english=_StubSpeculator(),
        on_spine=lambda payload: hook_payloads.append(payload),
    )

    assert error is None
    package = result["memo_package"]
    assert [s["id"] for s in package["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    # The chaser hook still fires, fed from the pinned file.
    assert hook_payloads and hook_payloads[0]["package_skeleton"]["company"][
        "name"
    ] == "Generalist, Inc."
    # The pinned file is the source of truth — never rewritten (the studio
    # extras key would be dropped by a rewrite).
    assert "studio_extras" in json.loads(pinned.read_text(encoding="utf-8"))


def test_pinned_spine_invalid_shape_is_hard_error(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    pinned = _write_pinned_spine(
        kwargs,
        payload={"package_skeleton": {}, "shared_facts": "not a dict"},
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("monolithic fallback must not run in pinned mode")
        ),
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, pinned_spine_path=pinned
    )

    assert result is None
    assert "refusing the monolithic fallback" in error


def test_pinned_spine_missing_file_is_hard_error(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        pinned_spine_path=kwargs["run_dir"] / "logs" / "english_units" / "spine.json",
    )

    assert result is None
    assert "pinned studio spine unreadable" in error


def test_pinned_spine_section_failure_refuses_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    pinned = _write_pinned_spine(kwargs)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: (None, "section worker exploded"),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("monolithic fallback must not run in pinned mode")
        ),
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, pinned_spine_path=pinned
    )

    assert result is None
    assert "refusing the monolithic fallback" in error


def test_pinned_spine_requires_parallel_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    kwargs = _parallel_kwargs(tmp_path)
    pinned = _write_pinned_spine(kwargs)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("monolithic path must not run with a pinned spine")
        ),
    )

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs, pinned_spine_path=pinned
    )

    assert result is None
    assert "BSH_MEMO_ENGLISH_PARALLEL=1" in error


def test_pinned_spine_survives_validation_retry(tmp_path, monkeypatch):
    """A retry attempt must keep the user's pins: feedback goes to the
    section workers, never to a spine regeneration."""
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)
    pinned = _write_pinned_spine(kwargs)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_spine",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("spine agent must not run in pinned mode")
        ),
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_artifacts",
        lambda **_kw: (_artifacts_result(), None),
    )
    seen_feedback: list[list[str] | None] = []

    def fake_section(**kw):
        seen_feedback.append(kw["validation_errors"])
        return {
            "section": {"id": kw["section_id"], "blocks": []},
            "claude_cost_usd": 0.25,
            "claude_duration_ms": 500,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        pinned_spine_path=pinned,
        validation_feedback="- fix the exec summary voice",
        attempt=2,
    )

    assert error is None
    assert all(
        errors == ["fix the exec summary voice"] for errors in seen_feedback
    )


# ---- length gate (Gemini) ---------------------------------------------------


def _words(section_id: str, count: int) -> dict:
    return {
        "id": section_id,
        "blocks": [{"type": "paragraph", "text": _loc(" ".join(["word"] * count))}],
    }


def _gemini_wave(tmp_path: Path, monkeypatch) -> tuple[dict, dict]:
    kwargs = _parallel_kwargs(tmp_path)
    memo_engine.register_run_engine(kwargs["run_dir"], "gemini")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    monkeypatch.delenv("BSH_MEMO_GEMINI_WORDS", raising=False)
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
    targets = memo_engine.section_word_targets(kwargs["run_dir"], memo_structure.LATE)
    return kwargs, targets


def test_an_out_of_band_gemini_section_is_revised_before_the_package_is_assembled(
    tmp_path, monkeypatch
):
    """Both directions: the risk section comes back short and is deepened,
    the valuation section comes back long and is tightened."""
    kwargs, targets = _gemini_wave(tmp_path, monkeypatch)
    revisions: list[tuple[str, int]] = []
    first_draft = {
        "investment_risk": targets["investment_risk"].low // 2,
        "financial_forecast_valuation": (
            targets["financial_forecast_valuation"].high * 2
        ),
    }

    def fake_section(**kw):
        section_id = kw["section_id"]
        target = targets[section_id]
        revision = kw.get("depth_revision")
        if revision is None:
            count = first_draft.get(section_id, target.target)
        else:
            draft_path, words_before = revision
            assert json.loads(draft_path.read_text())["id"] == section_id
            revisions.append((section_id, words_before))
            count = target.target
        return {
            "section": _words(section_id, count),
            "claude_cost_usd": 0.5,
            "claude_duration_ms": 1000,
        }, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    hook_calls: list[tuple[str, int]] = []

    result, error = claude_runner.run_memo_fast_english_package_parallel(
        **kwargs,
        on_section=lambda sid, section: hook_calls.append(
            (sid, memo_engine.en_word_count(section))
        ),
    )

    assert error is None
    assert sorted(revisions) == sorted(first_draft.items())
    by_id = {s["id"]: s for s in result["memo_package"]["sections"]}
    for section_id, target in targets.items():
        assert memo_engine.en_word_count(by_id[section_id]) == target.target
    # The Chinese chase sees the revised sections, never the first drafts,
    # and each section exactly once.
    assert sorted(sid for sid, _count in hook_calls) == sorted(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )
    assert dict(hook_calls)["investment_risk"] == targets["investment_risk"].target
    # spine 1.0 + artifacts 0.5 + five drafts at 0.5 + two revisions at 0.5
    assert result["claude_cost_usd"] == 5.0


def test_a_revision_that_fails_or_lands_no_closer_leaves_the_draft_standing(
    tmp_path, monkeypatch
):
    kwargs, targets = _gemini_wave(tmp_path, monkeypatch)
    floor = targets["investment_risk"].low
    attempts: list[int] = []

    def fake_section(**kw):
        section_id = kw["section_id"]
        revision = kw.get("depth_revision")
        if section_id != "investment_risk":
            return {"section": _words(section_id, targets[section_id].target)}, None
        if revision is None:
            return {"section": _words(section_id, floor // 2)}, None
        attempts.append(revision[1])
        if len(attempts) == 1:
            return None, "gemini output didn't parse as JSON"
        # Round 2 overshoots the other way, further out than it started.
        return {"section": _words(section_id, targets[section_id].high * 3)}, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    # Round 1 failed and drew its second sample (a Gemini section always
    # does); rounds 2 and 3 landed further out. Every attempt was made
    # against the same standing draft, and none replaced it.
    assert attempts == [floor // 2] * (memo_engine.DEPTH_ROUNDS + 1)
    by_id = {s["id"]: s for s in result["memo_package"]["sections"]}
    assert memo_engine.en_word_count(by_id["investment_risk"]) == floor // 2
    units_dir = kwargs["run_dir"] / "logs" / "english_units"
    assert len(list(units_dir.glob("investment_risk.length-*.json"))) == memo_engine.DEPTH_ROUNDS


def test_a_claude_wave_is_never_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    kwargs = _parallel_kwargs(tmp_path)  # the Claude default engine
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
    calls: list[dict] = []

    def fake_section(**kw):
        calls.append(kw)
        return {"section": _words(kw["section_id"], 12)}, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert len(calls) == 5
    assert all(kw.get("depth_revision") is None for kw in calls)



# ---- a Gemini wave draws a second sample, and never degrades ---------------


def _monolithic_guard(monkeypatch) -> list:
    """Record any monolithic call; on Gemini there must be none."""
    calls: list = []
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_english_package",
        lambda **kw: calls.append(kw)
        or ({"analysis_artifacts": {}, "memo_package": _sample_package()}, None),
    )
    return calls


def test_a_failed_gemini_section_gets_a_second_sample_before_anything_else(
    tmp_path, monkeypatch
):
    """Live (Koch, 2026-09-18): one section's JSON dropped a bracket and the
    wave fell to the monolithic pass — the 2,700-word memo. A second sample
    is nearly always enough, and costs a minute."""
    kwargs, targets = _gemini_wave(tmp_path, monkeypatch)
    calls: list[str] = []

    def fake_section(**kw):
        calls.append(kw["section_id"])
        if kw["section_id"] == "investment_risk" and calls.count("investment_risk") == 1:
            return None, "gemini output didn't parse as JSON (name=memo English section)"
        return {"section": _words(kw["section_id"], targets[kw["section_id"]].target)}, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    monolithic = _monolithic_guard(monkeypatch)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert calls.count("investment_risk") == 2
    assert monolithic == []
    assert [s["id"] for s in result["memo_package"]["sections"]] == list(
        claude_runner.MEMO_PACKAGE_SECTION_IDS
    )


def test_a_gemini_wave_that_fails_twice_stops_rather_than_writing_the_shallow_memo(
    tmp_path, monkeypatch
):
    kwargs, targets = _gemini_wave(tmp_path, monkeypatch)

    def fake_section(**kw):
        if kw["section_id"] == "investment_risk":
            return None, "gemini output didn't parse as JSON"
        return {"section": _words(kw["section_id"], targets[kw["section_id"]].target)}, None

    monkeypatch.setattr(claude_runner, "_run_english_section", fake_section)
    monolithic = _monolithic_guard(monkeypatch)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert result is None
    assert "monolithic fallback cannot carry a full memo in one Gemini response" in error
    assert "investment_risk" in error
    assert monolithic == []


def test_a_failed_gemini_spine_gets_a_second_sample(tmp_path, monkeypatch):
    kwargs, targets = _gemini_wave(tmp_path, monkeypatch)
    spine_calls: list[int] = []

    def fake_spine(**_kw):
        spine_calls.append(1)
        if len(spine_calls) == 1:
            return None, "gemini output didn't parse as JSON (name=memo English spine)"
        return _spine_result(), None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_spine", fake_spine)
    monkeypatch.setattr(
        claude_runner,
        "_run_english_section",
        lambda **kw: ({"section": _words(kw["section_id"], targets[kw["section_id"]].target)}, None),
    )
    monolithic = _monolithic_guard(monkeypatch)

    result, error = claude_runner.run_memo_fast_english_package_parallel(**kwargs)

    assert error is None
    assert len(spine_calls) == 2
    assert monolithic == []
