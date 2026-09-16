"""Round 1 of the report restructure: the 12-section late v2 profile and
the structure threading that carries it (flagged behind
BSH_MEMO_STRUCTURE_V2=1; the default pipeline stays late v1).
"""
from __future__ import annotations

import pytest

from server import claude_runner, memo_structure

V2 = memo_structure.load_structure("late", 2)

V2_SECTION_IDS = (
    "executive_summary",
    "company_overview",
    "market_industry",
    "product_business_model",
    "competitive_landscape",
    "moat",
    "financial_analysis",
    "team_governance",
    "valuation",
    "returns_exit",
    "investment_risk",
    "investment_decision",
)


# ---- profile canaries ------------------------------------------------------


def test_v2_section_ids():
    assert V2.section_ids == V2_SECTION_IDS
    assert V2.stage == "late"
    assert V2.version == 2


def test_v2_parity_patterns_match_rendered_titles_both_locales():
    """Every heading the renderer emits must be recognized by the parity
    gate's own patterns — the silent-degradation canary."""
    titles = V2.section_titles()
    patterns = V2.parity_patterns()
    for section_id in V2.section_ids:
        assert section_id in patterns, section_id
        for locale in ("en", "zh"):
            rendered = titles[section_id][locale]
            assert patterns[section_id][locale].match(rendered), (
                section_id,
                locale,
                rendered,
            )
    # the numbered sources pseudo-section too (position XIII)
    assert patterns["sources"]["en"].match(titles["sources"]["en"])
    assert patterns["sources"]["zh"].match(titles["sources"]["zh"])


def test_v2_lint_recognizers_cover_every_numbered_title():
    prefix = V2.numbered_prefix_pattern()
    titles = V2.section_titles()
    for section_id in V2.section_ids:
        assert prefix.match(titles[section_id]["en"].lower()), section_id
    bare = V2.lint_section_titles()
    for section in V2.sections:
        assert section.en_title.lower() in bare


def test_v2_roles():
    assert V2.section_for_role("exec").id == "executive_summary"
    assert V2.section_for_role("risk").id == "investment_risk"
    # The valuation role marks the section that echoes the pinned
    # scenario numbers — returns_exit owns the Scenario Analysis table
    # in v2.
    assert V2.section_for_role("valuation").id == "returns_exit"
    assert V2.numbered_lint_key("risk") == "xi. investment risk"


def test_v2_routes_every_component():
    routing = V2.component_section()
    component_ids = {component["id"] for component in V2.components}
    # source_index renders from the envelope, never a body section.
    assert component_ids - set(routing) == {"source_index"}
    assert set(routing.values()) <= set(V2.section_ids)


def test_v2_pass_affinity_uses_only_real_passes():
    from server import memo_analysis

    known = {spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES}
    for section_id, affinity in V2.pass_affinity().items():
        assert affinity <= known, (section_id, affinity - known)


def test_v2_floors():
    floors = V2.content_floors()
    assert floors["executive_summary"].min_real_blocks == 2
    assert floors["investment_decision"].min_real_blocks == 2
    assert floors["investment_risk"].bullets_or_prose
    assert floors["valuation"].require_valuation_refs
    assert floors["returns_exit"].require_valuation_refs


def test_v2_contracts_are_substantive():
    for section_id, spec in V2.section_specs().items():
        assert len(spec) > 500, section_id


# ---- resolution ------------------------------------------------------------


def test_active_structure_honors_flag(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)
    assert memo_structure.active_structure("late").version == 1
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    assert memo_structure.active_structure("late").version == 2


def test_for_package_resolves_stamp():
    stamped = {"structure": {"stage": "late", "version": 2}}
    # compare by meta, not identity — another test may have cleared the
    # profile cache, and the resolver hands out the freshly cached object
    assert memo_structure.for_package(stamped).meta() == V2.meta()
    legacy = {"sections": []}
    assert memo_structure.for_package(legacy) is memo_structure.LATE
    junk = {"structure": {"stage": "nonsense", "version": 9}}
    assert memo_structure.for_package(junk) is memo_structure.LATE
    assert memo_structure.for_package(None) is memo_structure.LATE


def test_profile_version_mismatch_raises(tmp_path):
    # late.md declares version 1; asking for it as version 2 must not
    # silently hand back the wrong structure.
    with pytest.raises(FileNotFoundError):
        memo_structure.load_structure("late", 3)


# ---- spine schema and prompts ----------------------------------------------


def test_spine_schema_default_identity_and_v2_notes():
    assert (
        claude_runner.memo_fast_english_spine_schema(memo_structure.LATE)
        is claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    )
    v2_schema = claude_runner.memo_fast_english_spine_schema(V2)
    notes = v2_schema["properties"]["section_notes"]["properties"]
    assert tuple(notes) == V2_SECTION_IDS
    # the envelope half is identical to the base schema; shared_facts
    # gains the v2 pins (covered by test_memo_pins_v2)
    base = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA
    assert (
        v2_schema["properties"]["package_skeleton"]
        == base["properties"]["package_skeleton"]
    )
    v1_props = set(base["properties"]["shared_facts"]["properties"])
    v2_props = set(v2_schema["properties"]["shared_facts"]["properties"])
    assert v1_props <= v2_props


def test_common_context_v1_unchanged_and_v2_appends(tmp_path):
    kwargs = dict(
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        run_dir=tmp_path,
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "a.docx", "zh": "b.docx"},
        research_dir=None,
        analysis_session_path=None,
        scope_check=None,
        warnings=None,
    )
    default = claude_runner._memo_english_common_context(**kwargs)
    v1 = claude_runner._memo_english_common_context(
        structure=memo_structure.LATE, **kwargs
    )
    assert default == v1
    assert "Data honesty" not in v1
    v2 = claude_runner._memo_english_common_context(structure=V2, **kwargs)
    assert v2.startswith(v1.rstrip("\n"))
    assert "## Data honesty" in v2
    assert "## Explanatory register" in v2
    assert "Not disclosed —" in v2


def test_section_worker_reads_v2_spec(tmp_path, monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"section": {"id": "moat", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_run
    )
    result, error = claude_runner._run_english_section(
        run_dir=tmp_path,
        section_id="moat",
        common_context="ctx",
        shared_facts_block="facts",
        spine_path=tmp_path / "spine.json",
        add_dirs=[],
        progress=None,
        timeout_sec=60,
        structure=V2,
    )
    assert error is None
    assert "Moat Audit" in captured["prompt"]
    assert "The $5B question" in captured["prompt"]


def test_risk_contract_attaches_by_role_in_v2(tmp_path, monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"section": {"id": "investment_risk", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_run
    )
    claude_runner._run_english_section(
        run_dir=tmp_path,
        section_id="investment_risk",
        common_context="ctx",
        shared_facts_block="facts",
        spine_path=tmp_path / "spine.json",
        add_dirs=[],
        progress=None,
        timeout_sec=60,
        structure=V2,
    )
    assert claude_runner.MEMO_RISK_REGISTER_CONTRACT.splitlines()[0] in (
        captured["prompt"]
    )


def test_spine_prompt_lists_v2_sections(tmp_path, monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {}, "stop here"

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_run
    )
    claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="ctx",
        add_dirs=[],
        structure=V2,
    )
    prompt = captured["prompt"]
    assert "Twelve section" in prompt
    for section_id in V2_SECTION_IDS:
        assert f"`{section_id}`" in prompt
    # With the spine handoff on, the CLI is handed a receipt schema and the
    # real one is enforced server-side, so read the section list from the
    # structure's schema rather than from the call.
    notes = claude_runner.memo_fast_english_spine_schema(V2)["properties"][
        "section_notes"
    ]["properties"]
    assert tuple(notes) == V2_SECTION_IDS


def test_spine_prompt_lists_v2_sections_inline(tmp_path, monkeypatch):
    """The same prompt, with the handoff turned off."""
    monkeypatch.setenv("BSH_MEMO_SPINE_HANDOFF", "0")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {}, "stop here"

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_run
    )
    claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="ctx",
        add_dirs=[],
        structure=V2,
    )
    assert "Return only the JSON matching the attached schema." in (
        captured["prompt"]
    )
    notes = captured["schema"]["properties"]["section_notes"]["properties"]
    assert tuple(notes) == V2_SECTION_IDS


# ---- monolithic-fallback guard ---------------------------------------------


def test_parallel_disabled_refuses_v2(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ENGLISH_PARALLEL", raising=False)
    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=tmp_path / "settings.json",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "a.docx", "zh": "b.docx"},
        structure=V2,
    )
    assert result is None
    assert "monolithic" in (error or "")


def test_parallel_failure_refuses_monolithic_fallback_for_v2(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")

    def failing_spine(**kwargs):
        return None, "boom"

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_spine", failing_spine
    )
    called = {"monolithic": False}

    def fake_monolithic(**kwargs):
        called["monolithic"] = True
        return {"memo_package": {}}, None

    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package", fake_monolithic
    )
    result, error = claude_runner.run_memo_fast_english_package_parallel(
        run_dir=tmp_path,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=tmp_path / "settings.json",
        companies_yaml_path=tmp_path / "companies.yaml",
        memo_paths={"en": "a.docx", "zh": "b.docx"},
        structure=V2,
    )
    assert result is None
    assert not called["monolithic"]
    assert "refusing the monolithic fallback" in (error or "")


# ---- renderer with a stamped v2 package ------------------------------------


def _v2_section(section_id: str) -> dict:
    """A minimal section that satisfies v2 floors and declares its
    components explicitly (declaration counts for coverage)."""
    structure = V2
    components = [
        slug
        for slug, owner in structure.component_section().items()
        if owner == section_id
    ]
    blocks: list[dict] = [
        {
            "type": "paragraph",
            "text": {
                "en": (
                    "This paragraph interprets the valuation scenario "
                    "evidence for the section in complete sentences and "
                    "states what moves the number."
                ),
                "zh": "本段解释估值与情景证据。",
            },
        },
        {
            "type": "table",
            "title": {"en": "Evidence table", "zh": "证据表"},
            "headers": [
                {"en": "Metric", "zh": "指标"},
                {"en": "Value", "zh": "数值"},
            ],
            "rows": [
                [
                    {"en": "Revenue", "zh": "收入"},
                    {"en": "$24M", "zh": "$24M"},
                ],
                [
                    {"en": "Growth", "zh": "增长"},
                    {"en": "80%", "zh": "80%"},
                ],
            ],
        },
        {
            "type": "bullets",
            "items": [
                {"en": "First substantive bullet with a number: 42%.", "zh": "一"},
                {"en": "Second substantive bullet with a verdict.", "zh": "二"},
            ],
        },
    ]
    for slug in components:
        blocks.append(
            {
                "type": "table",
                "component": slug,
                "title": {"en": slug.replace("_", " "), "zh": slug},
                "headers": [{"en": "K", "zh": "K"}, {"en": "V", "zh": "V"}],
                "rows": [
                    [{"en": "row", "zh": "行"}, {"en": "value", "zh": "值"}]
                ],
            }
        )
    return {"id": section_id, "blocks": blocks}


def _v2_package() -> dict:
    return {
        "schema_version": 1,
        "structure": {"stage": "late", "version": 2},
        "company": {"name": {"en": "Acme", "zh": "Acme"}},
        "run": {"run_id": "r1", "as_of": "2026-09-11"},
        "sources": [
            {
                "id": "s1",
                "title": {"en": "Company filing", "zh": "公司文件"},
                "class": {"en": "company-reported", "zh": "公司披露"},
                "treatment": {"en": "verified", "zh": "已核对"},
                "as_of": "2026-09-01",
            }
        ],
        "sections": [_v2_section(section_id) for section_id in V2_SECTION_IDS],
    }


def test_renderer_validates_and_renders_stamped_v2_package(tmp_path):
    from server import memo_docx_renderer

    package = _v2_package()
    memo_docx_renderer.validate_package(package)
    result = memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    assert result["ok"]
    from docx import Document

    doc = Document(tmp_path / "memo" / "en.docx")
    headings = [p.text.upper() for p in doc.paragraphs if p.text.strip()]
    assert any(h.startswith("XI. INVESTMENT RISK") for h in headings)
    assert any(h.startswith("XII. INVESTMENT DECISION") for h in headings)
    assert any(
        h.startswith("XIII. SOURCES") for h in headings
    ), "sources numbered after the 12 sections"


def test_renderer_requires_all_twelve_sections(tmp_path):
    from server import memo_docx_renderer

    package = _v2_package()
    package["sections"] = package["sections"][:5]
    errors = memo_docx_renderer._package_validation_errors(package)
    missing = [e for e in errors if e.startswith("missing required section")]
    assert len(missing) == 7


def test_unstamped_package_still_validates_as_v1(tmp_path):
    from server import memo_docx_renderer

    package = _v2_package()
    del package["structure"]
    errors = memo_docx_renderer._package_validation_errors(package)
    # v1 rules: the five v1 ids are required and absent by those names
    # except the ones the structures share.
    assert any("investment_highlights" in e for e in errors)


# ---- gates with the v2 structure -------------------------------------------


def test_lint_section_recognition_v2():
    from server import memo_quality_lint

    assert (
        memo_quality_lint._section_after_heading(
            "XI. Investment Risk", "front matter", V2
        )
        == "xi. investment risk"
    )
    assert (
        memo_quality_lint._section_after_heading(
            "XII. Investment Decision", "front matter", V2
        )
        == "xii. investment decision"
    )
    # v1 recognizer does not know the deep numerals
    assert (
        memo_quality_lint._section_after_heading(
            "XI. Investment Risk", "front matter", memo_structure.LATE
        )
        == "front matter"
    )


def test_pin_check_uses_returns_exit_for_scenarios_in_v2():
    from server import memo_pin_check

    shared_facts = {
        "recommendation_sentence": "Recommendation: watch Acme.",
        "key_metrics": [],
        "scenarios": {"bear": "$10M exit", "base": "", "bull": ""},
        "risks": [],
    }
    package = {
        "structure": {"stage": "late", "version": 2},
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": {"en": "Recommendation: watch Acme."},
                    }
                ],
            },
            {
                "id": "returns_exit",
                "blocks": [
                    {"type": "paragraph", "text": {"en": "Bear case: $10M exit."}}
                ],
            },
        ],
    }
    result = memo_pin_check.check_package_pins(package, shared_facts)
    assert result.ok, [f.to_dict() for f in result.findings]
    # move the scenario text out of returns_exit and the pin check fails
    package["sections"][1]["blocks"][0]["text"]["en"] = "No numbers here."
    result = memo_pin_check.check_package_pins(package, shared_facts)
    codes = {finding.code for finding in result.findings}
    assert "scenario_numbers_missing" in codes
    assert {finding.location for finding in result.findings} == {"returns_exit"}


def test_v2_addendum_closes_the_input_surface():
    """Live runs showed spine agents grepping the server source and
    opening OTHER companies' memo packages as schema examples — a token
    sink and a contamination vector. The shared v2 context must pin the
    input surface shut."""
    addendum = claude_runner.MEMO_STRUCTURE_V2_ADDENDUM
    assert "## Inputs are closed" in addendum
    assert "authoritative output contract" in addendum
    assert "another company's or another run's folders" in addendum
