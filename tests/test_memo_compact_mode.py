"""Compact report mode + the founder-feedback voice/format gates:

- `late_compact` profile: 7 sections, bullet-format risks, same
  scorecard and pin discipline as the full report.
- active_structure(stage, mode) resolves compact profiles with full
  fallback.
- Exec-summary bullets must open with a claim, not a topic label.
- Charts require a `reading` note and support hbar/pie.
"""
from __future__ import annotations

import pytest

import test_memo_subsections_charts as full_fixtures
from server import memo_docx_renderer, memo_structure

COMPACT = memo_structure.load_structure("late_compact", 1)


# ---- profile ----------------------------------------------------------------


def test_compact_profile_shape():
    assert len(COMPACT.section_ids) == 7
    # The founder's verdict on the bullet register (2026-09-16): "a
    # paragraph of description, hard to catch the main point". Compact now
    # uses the full report's per-risk cards.
    assert COMPACT.risk_format == "cards"
    assert COMPACT.scorecard_weights() == memo_structure.load_structure(
        "late", 2
    ).scorecard_weights()
    for role in ("exec", "risk", "valuation"):
        assert COMPACT.section_for_role(role).id in COMPACT.section_ids
    for section in COMPACT.sections:
        assert section.subsections, section.id
        for sub in section.subsections:
            assert sub.en.lower() in section.contract_md.lower(), (
                section.id,
                sub.en,
            )


def test_compact_recognizer_canary():
    titles = COMPACT.section_titles()
    patterns = COMPACT.parity_patterns()
    prefix = COMPACT.numbered_prefix_pattern()
    for section_id in COMPACT.section_ids:
        for locale in ("en", "zh"):
            assert patterns[section_id][locale].match(
                titles[section_id][locale]
            ), (section_id, locale)
        assert prefix.match(titles[section_id]["en"].lower())
    assert patterns["sources"]["en"].match(titles["sources"]["en"])


def test_compact_contracts_demand_the_scorecard_sentences():
    """Live compact run 2 lost two retry cycles to sections dropping the
    pinned 'scores N of M' closers under the tight word budgets — every
    owning section's contract must ask for them explicitly."""
    for section in COMPACT.sections:
        if section.scorecard_dimensions:
            assert "scores" in section.contract_md.lower(), section.id


def test_sources_table_may_reference_this_memo(tmp_path):
    """The sources contract asks how 'the memo weighs and uses this
    source'; lint must not flag 'in this memo' inside the sources table
    (a live run lost a full regeneration cycle to exactly that)."""
    from server import memo_quality_lint

    package = full_fixtures._v2_gen_package()
    package["sources"][0]["treatment"] = {
        "en": "The recognized-revenue base for every multiple in this memo.",
        "zh": "本备忘录中所有倍数的确认收入基础。",
    }
    out_en = tmp_path / "memo" / "en.docx"
    memo_docx_renderer.render_memos(
        package, out_en=out_en, out_zh=tmp_path / "memo" / "zh.docx"
    )
    structure = memo_structure.load_structure("late", 2)
    lint = memo_quality_lint.lint_memo_docx(out_en, structure)
    meta = [
        f for f in lint.p0_findings if f.code == "meta_process_language"
    ]
    assert not meta, [f.to_dict() for f in meta]


def test_full_profiles_keep_card_risk_format():
    for stage, version in (("late", 1), ("late", 2), ("growth", 1), ("early", 1)):
        assert memo_structure.load_structure(stage, version).risk_format == "cards"


def test_pin_stage_strips_the_compact_suffix():
    """The spine pins early/growth/late (schema enum); the deterministic
    gate must compare against the profile's INVESTMENT stage, not its
    file name — the first compact live run died on 'late' != 'late_compact'."""
    assert COMPACT.pin_stage == "late"
    assert memo_structure.LATE.pin_stage == "late"
    assert memo_structure.load_structure("late", 2).pin_stage == "late"
    assert memo_structure.load_structure("early", 1).pin_stage == "early"


def test_spine_gate_accepts_parent_stage_pin_for_compact():
    from server import memo_pin_check

    facts = {"stage": "late"}
    problems = memo_pin_check.check_spine_pins_v2(facts, COMPACT)
    assert not [p for p in problems if "pinned stage" in p], problems
    problems = memo_pin_check.check_spine_pins_v2({"stage": "early"}, COMPACT)
    assert any("pinned stage 'early'" in p and "'late'" in p for p in problems)


# A seed company runs on `late_compact` like everyone else, and used to
# be told to pin "late" — in the spine, in the memo prose and on the UI
# chip — while its own scorecard was already scored on early weights
# (RadixArk 2026-09-20__042036: team scored 16, above the late map's max
# of 10). `declared_stage` is the one place the run says which stage it
# classified; `pin_stage` stays the profile's own family.


def test_declared_stage_follows_the_classified_stage(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    seed = memo_structure.active_structure("early", "compact")
    assert seed.stage == "late_compact"
    assert seed.pin_stage == "late"
    assert seed.declared_stage == "early"
    # and it survives the package round trip
    reloaded = memo_structure.for_package({"structure": seed.meta()})
    assert reloaded.declared_stage == "early"
    # a late company on the same profile declares late, unstamped
    late = memo_structure.active_structure("late", "compact")
    assert late.declared_stage == "late"
    assert "overlay_stage" not in late.meta()


def test_spine_gate_checks_the_declared_stage(monkeypatch):
    from server import memo_pin_check

    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    seed = memo_structure.active_structure("early", "compact")
    assert not [
        p
        for p in memo_pin_check.check_spine_pins_v2({"stage": "early"}, seed)
        if "pinned stage" in p
    ]
    problems = memo_pin_check.check_spine_pins_v2({"stage": "late"}, seed)
    assert any("pinned stage 'late'" in p and "'early'" in p for p in problems)


def test_an_unclassified_stage_never_becomes_a_declared_one():
    # The spine schema enums early/growth/late. A stage the classifier
    # could not name must not reach the pin.
    odd = memo_structure.load_structure(
        "late_compact", 1, overlay_stage="indeterminate"
    )
    assert odd.declared_stage == "late"
    assert "overlay_stage" not in odd.meta()


def test_spine_prompt_pins_parent_stage(monkeypatch, tmp_path):
    """The spine prompt must ask for the schema-legal parent stage."""
    from server import claude_runner

    captured = {}

    def fake_artifact(**kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return None, "stop here"

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="",
        add_dirs=[],
        progress=None,
        structure=COMPACT,
    )
    assert '`stage`: "late"' in captured["prompt"]

    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="",
        add_dirs=[],
        progress=None,
        structure=memo_structure.active_structure("early", "compact"),
    )
    assert '`stage`: "early"' in captured["prompt"]


# ---- mode mapping -----------------------------------------------------------


def test_active_structure_compact_mode(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    assert memo_structure.active_structure("late", "compact").meta() == {
        "stage": "late_compact",
        "version": 1,
    }
    # Stages without a compact profile fall back to the late compact
    # one — but the run still declares the stage it classified. Without
    # `overlay_stage` in the package stamp, `for_package` would resolve
    # a growth company back to "late" and every reader-facing stage (the
    # spine pin, the memo prose, the UI chip) would say late.
    assert memo_structure.active_structure("growth", "compact").meta() == {
        "stage": "late_compact",
        "version": 1,
        "overlay_stage": "growth",
    }
    # full mode is untouched
    assert memo_structure.active_structure("late", "full").meta() == {
        "stage": "late",
        "version": 2,
    }


def test_flag_off_compact_still_runs_late_v1(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)
    assert (
        memo_structure.active_structure("late", "compact")
        is memo_structure.LATE
    )


# ---- compact package clears every gate --------------------------------------


def _compact_package() -> dict:
    return full_fixtures._v2_gen_package(COMPACT)


def test_compact_package_passes_generation_gates():
    package = _compact_package()
    errors = memo_docx_renderer.english_package_validation_errors(package)
    # No risk-card demands for a bullets-format profile.
    assert errors == []


def test_compact_package_renders_and_clears_docx_gates(tmp_path):
    from server import memo_chinese_parity, memo_quality_lint

    package = _compact_package()
    out_en = tmp_path / "memo" / "en.docx"
    out_zh = tmp_path / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    lint = memo_quality_lint.lint_memo_docx(out_en, COMPACT)
    assert not lint.p0_findings, [f.to_dict() for f in lint.p0_findings]
    parity = memo_chinese_parity.lint_chinese_memo_pair(out_en, out_zh, COMPACT)
    assert not parity.p0_findings, [f.to_dict() for f in parity.p0_findings]


def test_compact_risk_contract_is_cards_like_the_full_report():
    from server import claude_runner

    contract = claude_runner.memo_risk_register_contract(COMPACT)
    v2 = memo_structure.load_structure("late", 2)
    assert contract is claude_runner.memo_risk_register_contract(v2)
    assert "Mitigation" in contract


# ---- exec bullet topic-label gate -------------------------------------------


def test_exec_bullet_topic_label_rejected():
    package = full_fixtures._v2_gen_package()
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"].append(
        {
            "type": "bullets",
            "items": [
                {"en": "Price. 13.8x vs a 21x median.", "zh": ""},
                {
                    "en": (
                        "The price sits below every disclosed peer — 13.8x "
                        "against a 21x median."
                    ),
                    "zh": "",
                },
            ],
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    label_errors = [e for e in errors if "topic label" in e]
    assert len(label_errors) == 1
    assert "'Price'" in label_errors[0]


def test_exec_bullet_colon_lead_accepted():
    package = full_fixtures._v2_gen_package()
    exec_section = next(
        s for s in package["sections"] if s["id"] == "executive_summary"
    )
    exec_section["blocks"].append(
        {
            "type": "bullets",
            "items": [
                {
                    "en": (
                        "Market size: the pool is $125B and the company "
                        "already holds half of it."
                    ),
                    "zh": "",
                }
            ],
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert not [e for e in errors if "topic label" in e]


# ---- chart reading + new types ----------------------------------------------


def test_chart_without_reading_is_rejected():
    chart = full_fixtures._chart_block()
    chart.pop("reading", None)
    package = full_fixtures._package_with_chart(chart)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any("`reading` note" in e for e in errors)


def test_chart_with_reading_passes_and_renders_caption(tmp_path):
    chart = full_fixtures._chart_block(
        reading={"en": "Higher is better", "zh": "越高越好"}
    )
    package = full_fixtures._package_with_chart(chart)
    assert memo_docx_renderer.english_package_validation_errors(package) == []
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    for locale, needle in (
        ("en", "Reading: Higher is better"),
        ("zh", "读法：越高越好"),
    ):
        doc = Document(tmp_path / "memo" / f"{locale}.docx")
        text = "\n".join(p.text for p in doc.paragraphs)
        assert needle in text, locale


@pytest.mark.parametrize("chart_type", ["hbar", "pie"])
def test_new_chart_types_validate_and_render(chart_type):
    from server import memo_charts

    chart = full_fixtures._chart_block(
        chart_type=chart_type,
        reading={"en": "Shares of the pool", "zh": ""},
    )
    chart["series"] = chart["series"][:1]
    package = full_fixtures._package_with_chart(chart)
    assert memo_docx_renderer.english_package_validation_errors(package) == []
    png = memo_charts.chart_png(chart)
    assert png.startswith(b"\x89PNG"), chart_type


@pytest.mark.parametrize("chart_type", ["hbar", "pie"])
def test_new_chart_types_take_one_series(chart_type):
    chart = full_fixtures._chart_block(
        chart_type=chart_type,
        reading={"en": "Higher is better", "zh": ""},
    )
    package = full_fixtures._package_with_chart(chart)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert any("exactly one series" in e for e in errors)


# ---- pagination -------------------------------------------------------------


def test_each_section_starts_on_a_new_page(tmp_path):
    package = full_fixtures._v2_gen_package()
    memo_docx_renderer.render_memos(
        package,
        out_en=tmp_path / "memo" / "en.docx",
        out_zh=tmp_path / "memo" / "zh.docx",
    )
    from docx import Document

    doc = Document(tmp_path / "memo" / "en.docx")
    xml = doc.element.body.xml
    # Cover break + one break before each section after the first (11)
    # + one before the auto-rendered sources section.
    assert xml.count("w:br") >= 12


# ---- run plumbing -----------------------------------------------------------


def test_bootstrap_rejects_unknown_report_mode():
    from server import memo_prep

    with pytest.raises(ValueError, match="report_mode"):
        memo_prep.bootstrap_memo_run("whatever", report_mode="tiny")


# ---- artifacts prompt stays consistent with its schema -----------------------


def test_artifacts_prompt_matches_schema_cap(monkeypatch, tmp_path):
    """The artifacts prompt once kept an old 8,000-char figure after the
    schema cap moved to 16,000 AND told the agent to 'count the
    markdown' — a live run burned 17 minutes in shell trim loops chasing
    the phantom limit. The prompt must state the real cap and ban
    scratch-file measuring."""
    from server import claude_runner

    captured = {}

    def fake_artifact(**kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return None, "stop here"

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    claude_runner.run_memo_fast_english_artifacts(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="",
        add_dirs=[],
        progress=None,
    )
    prompt = captured["prompt"]
    schema_cap = claude_runner.MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA[
        "properties"
    ]["analysis_artifacts"]["properties"]["claim_register_md"]["maxLength"]
    assert f"{schema_cap:,}" in prompt
    assert "8,000" not in prompt
    assert "Do NOT draft them in scratch files" in prompt


# ---- word-budget ceiling gate -----------------------------------------------


def test_compact_declares_word_ceilings():
    for section in COMPACT.sections:
        assert section.budget_words, section.id
    # full profiles carry no ceiling — the gate must not touch them
    for section in memo_structure.load_structure("late", 2).sections:
        assert section.budget_words is None


def test_word_budget_gate_flags_overrun_and_accepts_fit():
    package = _compact_package()
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert not [e for e in errors if "hard cap" in e], errors
    risks = next(s for s in package["sections"] if s["id"] == "risks")
    risks_def = next(s for s in COMPACT.sections if s.id == "risks")
    ceiling = risks_def.budget_words
    # Derived from the profile, so widening a budget or a multiple never
    # quietly turns this gate test into a no-op the way a hardcoded 300 did.
    hard = ceiling * (
        risks_def.budget_hard_multiple or memo_docx_renderer._BUDGET_GRACE
    )
    over_by = int(hard) + 50
    risks["blocks"].append(
        {
            "type": "paragraph",
            "text": {"en": "filler word " * over_by, "zh": ""},
        }
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    overruns = [e for e in errors if "hard cap" in e]
    assert len(overruns) == 1 and "section risks" in overruns[0]
    assert f"{ceiling}-word target" in overruns[0]
    assert f"{int(hard)}-word hard cap" in overruns[0]


def test_a_section_between_its_target_and_its_cap_is_left_alone():
    """The budget is a soft target: a section that ran past it to finish
    its argument is fine, and re-emitting it has never shortened one."""
    package = _compact_package()
    risks = next(s for s in package["sections"] if s["id"] == "risks")
    risks_def = next(s for s in COMPACT.sections if s.id == "risks")
    ceiling = risks_def.budget_words
    current = memo_docx_renderer._section_en_word_count(risks)
    hard = ceiling * (
        risks_def.budget_hard_multiple or memo_docx_renderer._BUDGET_GRACE
    )
    # Land above the target but inside the cap.
    filler = int(hard) - current - 5
    assert filler > ceiling - current
    assert filler > 0
    risks["blocks"].append(
        {"type": "paragraph", "text": {"en": "filler word " * (filler // 2), "zh": ""}}
    )
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert not [e for e in errors if "hard cap" in e], errors


def test_money_parser_handles_digit_grouping():
    from server import memo_pin_check

    assert memo_pin_check._parse_money("$1,950B") == 1_950_000_000_000
    assert memo_pin_check._parse_money("$1,200 billion") == 1_200_000_000_000
    assert memo_pin_check._parse_money("$1.95T") == 1_950_000_000_000
    assert memo_pin_check._parse_money("$965B") == 965_000_000_000
    # A leading bare number (a year, a range's low end) must not shadow
    # the suffixed value — the "~0.0x" MOIC respin in two live runs.
    assert memo_pin_check._parse_money("2029: $2.6T") == 2_600_000_000_000
    assert memo_pin_check._parse_money("$1.9-2.3T") == 2_300_000_000_000
    assert memo_pin_check._parse_money("2028E, $190B") == 190_000_000_000
