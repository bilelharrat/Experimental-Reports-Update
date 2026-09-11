"""Round 3 of the report restructure: structure-stage classification and
the growth/early profiles (active only under BSH_MEMO_STRUCTURE_V2=1)."""
from __future__ import annotations

import pytest

from server import memo_prep, memo_structure

GROWTH = memo_structure.load_structure("growth", 1)
EARLY = memo_structure.load_structure("early", 1)


# ---- classification matrix -------------------------------------------------


@pytest.mark.parametrize(
    ("company", "expected_stage", "expected_source"),
    [
        ({"exchange": "NASDAQ"}, "late", "public listing"),
        ({"latest_funding": {"round": "Seed"}}, "early", "funding round"),
        ({"latest_funding": {"round": "Pre-Seed"}}, "early", "funding round"),
        ({"latest_funding": {"round": "Series A"}}, "early", "funding round"),
        ({"latest_funding": {"round": "Series A-2"}}, "early", "funding round"),
        ({"latest_funding": {"round": "Series B"}}, "growth", "funding round"),
        ({"latest_funding": {"round": "Series C-1"}}, "growth", "funding round"),
        ({"latest_funding": {"round": "Series D"}}, "late", "funding round"),
        ({"latest_funding": {"round": "Series F"}}, "late", "funding round"),
        ({"latest_funding": {"round": "Pre-IPO"}}, "late", "funding round"),
        (
            {"latest_funding": {"round": "Growth Equity"}},
            "late",
            "funding round",
        ),
        ({"total_funding_usd": "$12M"}, "early", "total funding"),
        ({"total_funding_usd": "$80 million"}, "growth", "total funding"),
        ({"total_funding_usd": "$1.2B"}, "late", "total funding"),
        ({}, "late", "default"),
        ({"latest_funding": {"round": "Undisclosed"}}, "late", "default"),
    ],
)
def test_classify_structure_stage(company, expected_stage, expected_source):
    result = memo_prep.classify_structure_stage(company)
    assert result["stage"] == expected_stage
    assert result["source"] == expected_source
    assert isinstance(result["signals"], list)


def test_round_label_beats_funding_total():
    company = {
        "latest_funding": {"round": "Series B"},
        "total_funding_usd": "$500M",
    }
    assert memo_prep.classify_structure_stage(company)["stage"] == "growth"


# ---- active_structure mapping ----------------------------------------------


def test_flag_off_every_stage_runs_late_v1(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)
    for stage in ("late", "growth", "early", "nonsense"):
        assert memo_structure.active_structure(stage) is memo_structure.LATE


def test_flag_on_maps_stages_to_profiles(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    assert memo_structure.active_structure("late").meta() == {
        "stage": "late",
        "version": 2,
    }
    assert memo_structure.active_structure("growth").meta() == {
        "stage": "growth",
        "version": 1,
    }
    assert memo_structure.active_structure("early").meta() == {
        "stage": "early",
        "version": 1,
    }
    # an unknown stage falls back to the late v2 chain, never crashes
    assert memo_structure.active_structure("nonsense").meta() == {
        "stage": "late",
        "version": 2,
    }


# ---- per-stage profile canaries --------------------------------------------


@pytest.mark.parametrize("structure", [GROWTH, EARLY], ids=["growth", "early"])
def test_profile_recognizer_canary(structure):
    """Parity patterns and lint recognizers must accept every heading the
    renderer emits for the profile — the silent-degradation canary."""
    titles = structure.section_titles()
    patterns = structure.parity_patterns()
    prefix = structure.numbered_prefix_pattern()
    for section_id in structure.section_ids:
        for locale in ("en", "zh"):
            assert patterns[section_id][locale].match(
                titles[section_id][locale]
            ), (structure.stage, section_id, locale)
        assert prefix.match(titles[section_id]["en"].lower())
    assert patterns["sources"]["en"].match(titles["sources"]["en"])
    assert patterns["sources"]["zh"].match(titles["sources"]["zh"])


@pytest.mark.parametrize("structure", [GROWTH, EARLY], ids=["growth", "early"])
def test_profile_roles_and_routing(structure):
    for role in ("exec", "risk", "valuation"):
        assert structure.section_for_role(role).id in structure.section_ids
    routing = structure.component_section()
    component_ids = {component["id"] for component in structure.components}
    assert component_ids - set(routing) == {"source_index"}
    assert set(routing.values()) <= set(structure.section_ids)


def test_growth_has_nine_sections_early_seven():
    assert len(GROWTH.section_ids) == 9
    assert len(EARLY.section_ids) == 7
    # early excludes the components its contracts cannot evidence
    early_ids = {component["id"] for component in EARLY.components}
    for excluded in (
        "competitive_analysis",
        "replacement_coexistence",
        "moat",
        "growth_bridge",
        "time_base_integrity",
    ):
        assert excluded not in early_ids
    growth_ids = {component["id"] for component in GROWTH.components}
    assert len(growth_ids) == 17


@pytest.mark.parametrize("structure", [GROWTH, EARLY], ids=["growth", "early"])
def test_profile_affinity_uses_real_passes(structure):
    from server import memo_analysis

    known = {spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES}
    for section_id, affinity in structure.pass_affinity().items():
        assert affinity <= known, (section_id, affinity - known)


# ---- renderer accepts stamped growth/early packages ------------------------


def _stage_section(structure: memo_structure.MemoStructure, section_id: str) -> dict:
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
                    "This paragraph interprets the valuation and scenario "
                    "evidence in complete sentences and states what moves "
                    "the number."
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
                [{"en": "Revenue", "zh": "收入"}, {"en": "$4M", "zh": "$4M"}]
            ],
        },
        {
            "type": "bullets",
            "items": [
                {"en": "First substantive bullet: 42%.", "zh": "一"},
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


def _stage_package(structure: memo_structure.MemoStructure) -> dict:
    return {
        "schema_version": 1,
        "structure": structure.meta(),
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
        "sections": [
            _stage_section(structure, section_id)
            for section_id in structure.section_ids
        ],
    }


@pytest.mark.parametrize("structure", [GROWTH, EARLY], ids=["growth", "early"])
def test_renderer_validates_and_renders_stage_package(structure, tmp_path):
    from server import memo_docx_renderer

    package = _stage_package(structure)
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
    titles = structure.section_titles()
    for section_id in structure.section_ids:
        expected = titles[section_id]["en"].upper()
        assert any(h.startswith(expected) for h in headings), expected
    sources_title = titles["sources"]["en"].upper()
    assert any(h.startswith(sources_title.split(",")[0]) for h in headings)


@pytest.mark.parametrize("structure", [GROWTH, EARLY], ids=["growth", "early"])
def test_stage_package_requires_all_its_sections(structure):
    from server import memo_docx_renderer

    package = _stage_package(structure)
    package["sections"] = package["sections"][:2]
    errors = memo_docx_renderer._package_validation_errors(package)
    missing = [e for e in errors if e.startswith("missing required section")]
    assert len(missing) == len(structure.section_ids) - 2


@pytest.mark.parametrize(
    "structure",
    [memo_structure.load_structure("late", 2), GROWTH, EARLY],
    ids=["late_v2", "growth", "early"],
)
def test_full_docx_gate_chain_per_stage(structure, tmp_path):
    """Render a stamped stage package and run BOTH docx gates with the
    stage's structure — the end-to-end silent-degradation canary: every
    heading the renderer emits must clear quality lint and Chinese
    parity."""
    from server import (
        memo_chinese_parity,
        memo_docx_renderer,
        memo_quality_lint,
    )

    package = _stage_package(structure)
    out_en = tmp_path / "memo" / "en.docx"
    out_zh = tmp_path / "memo" / "zh.docx"
    memo_docx_renderer.render_memos(package, out_en=out_en, out_zh=out_zh)
    lint = memo_quality_lint.lint_memo_docx(out_en, structure)
    assert not lint.p0_findings, [f.to_dict() for f in lint.p0_findings]
    parity = memo_chinese_parity.lint_chinese_memo_pair(
        out_en, out_zh, structure
    )
    assert not parity.p0_findings, [f.to_dict() for f in parity.p0_findings]


def test_risk_card_hint_names_the_stage_risk_section():
    from server import memo_docx_renderer

    package = _stage_package(EARLY)
    errors = memo_docx_renderer.english_package_validation_errors(package)
    joined = " ".join(errors)
    assert "risks_milestones" in joined
    assert "investment_risk" not in joined
