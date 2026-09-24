"""Prompt ↔ validator contract (I25).

Every source class, component slug, block shape, placeholder, section id
and pass id the prompts under skills/memo/ (and the sources contract in
claude_runner) prescribe must be something the deterministic gates accept.
The 2026-09-23 ZaiNar v1 run died at the final check because the prompt
prescribed the class "unverified registry value (no document on file)"
for a URL-less registry source and the renderer's validator rejected it;
this file is the guard against that class of bug. Nothing here calls a
model or touches data/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from server import (
    claude_runner,
    memo_docx_renderer,
    memo_prompts,
    memo_quality_lint,
    memo_structure,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLS = memo_prompts.MEMO_SKILLS_DIR
FIXTURES = ROOT / "tests" / "fixtures"

STRUCTURE_FILES = {
    "structures/late.md": ("late", 1),
    "structures/late_v2.md": ("late", 2),
    "structures/late_compact.md": ("late_compact", 1),
    "structures/growth.md": ("growth", 1),
    "structures/early.md": ("early", 1),
}

# Component slugs the prompts put on blocks that are neither in
# components.yaml nor special-cased in the renderer: they render as the
# ordinary block they sit on (a bullets block) and the slug is a label
# for the section worker, the pin check and the lint. Adding a slug here
# is a deliberate statement that it needs no renderer support.
PLAIN_BLOCK_SLUGS = frozenset({"dimension_scan"})

_COMPONENT_RE = re.compile(r'"?component"?\s*:\s*"([a-z_]+)"')
_SECTION_HEADER_RE = re.compile(r"^## section: ([a-z0-9_]+)\s*$", re.M)
_PLACEHOLDER_RE = re.compile(r"\[(?:TO BE DETERMINED BY IC|重仓 / 跟投 / 卡位 — IC to select)\]")


def _english_prompt_files() -> list[Path]:
    return sorted(
        path
        for path in SKILLS.rglob("*.md")
        if "zh" not in path.relative_to(SKILLS).parts
    )


def _prompt_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _english_prompt_files())


def _quoted(text: str) -> list[str]:
    return [" ".join(match.split()) for match in re.findall(r'"([^"]+)"', text)]


def _pass_ids() -> set[str]:
    passes = memo_prompts.parse_passes((SKILLS / "passes.md").read_text(encoding="utf-8"))
    return {spec["pass_id"] for spec in passes}


def _prescribed_source_classes() -> list[str]:
    """Every class string the sources contract prescribes, joined on
    whitespace (the contract wraps "unverified registry value (no
    document on file)" across a line)."""
    contract = " ".join(claude_runner.MEMO_PACKAGE_SOURCES_CONTRACT.split())
    class_bullet = contract[contract.index("`class`:") : contract.index("`treatment`:")]
    url_bullet = contract[contract.index("Omit it only") : contract.index("Never invent a URL")]
    classes = [c for c in _quoted(class_bullet) + _quoted(url_bullet) if c and c[0].islower() or c.startswith("BSH")]
    # The ellipsis placeholder in the class list is not a class.
    classes = [c for c in classes if c != "..."]
    assert "unverified registry value (no document on file)" in classes
    assert "company-reported" in classes and "BSH reference call" in classes
    return classes


def _source(cls: str, *, url: str | None) -> dict:
    source = {
        "id": "S1",
        "title": {"en": "A page about the company", "zh": "一个关于公司的页面"},
        "class": cls,
        "treatment": {"en": "Weighed as the contract says.", "zh": "按契约处理。"},
        "as_of": "2026-02",
    }
    if url:
        source["url"] = url
    return source


# ---- source classes -----------------------------------------------------------


def test_every_prescribed_source_class_validates_and_has_a_label():
    for cls in _prescribed_source_classes():
        private = memo_docx_renderer.source_url_optional({"class": cls, "title": ""})
        registry = bool(memo_docx_renderer._UNVERIFIED_REGISTRY_CLASS_RE.search(cls))
        if registry:
            # The class that cost a run: URL-less, the firm holds nothing
            # private, and it must still pass.
            errors: list[str] = []
            memo_docx_renderer._validate_source(
                _source(cls, url=None),
                "sources[0]",
                errors,
                private_material=False,
                private_inventory=[],
            )
            assert errors == [], (cls, errors)
        elif private:
            # Private material may omit the URL when the firm holds some.
            errors = []
            memo_docx_renderer._validate_source(
                _source(cls, url=None), "sources[0]", errors, private_material=True
            )
            assert errors == [], (cls, errors)
        else:
            errors = []
            memo_docx_renderer._validate_source(
                _source(cls, url="https://example.com/page"),
                "sources[0]",
                errors,
                private_material=False,
            )
            assert errors == [], (cls, errors)
            # ... and the contract's own rule — web-retrieved needs a URL —
            # is what the validator enforces, not something stricter.
            errors = []
            memo_docx_renderer._validate_source(
                _source(cls, url=None), "sources[0]", errors, private_material=False
            )
            assert errors and "url is required" in errors[0], (cls, errors)
        en_label = memo_docx_renderer._source_class_label(_source(cls, url=None), "en")
        zh_label = memo_docx_renderer._source_class_label(_source(cls, url=None), "zh")
        assert en_label, cls
        assert zh_label and zh_label != "其他来源", (cls, zh_label)
        assert memo_docx_renderer._CJK_CHAR_RE.search(zh_label), (cls, zh_label)


def test_registry_class_phrase_is_the_one_the_prompts_use():
    phrase = "unverified registry value"
    assert memo_docx_renderer._UNVERIFIED_REGISTRY_CLASS_RE.search(
        "Unverified registry value (no document on file)"
    )
    assert phrase in memo_prompts.load_pass_rules()
    assert phrase in memo_prompts.load_prompt("voice_contract.md")
    # The memo-text wording for such a value, and the ban on its label.
    voice = memo_prompts.load_prompt("voice_contract.md")
    assert "excluded; no document on file" in voice
    assert "excluded; no document on file" in memo_prompts.load_pass_rules()
    assert '"Design mock",\n  "placeholder", "demo", "mock" and "seed data"' in voice


def test_stored_packages_sources_still_validate_leniently():
    """Every source in the packages on disk passes the lenient
    (re-render) validation with the classes the model chose."""
    for name in ("zainar_v1_package.json", "zainar_v2_draft.en.json"):
        package = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        for index, source in enumerate(package.get("sources") or []):
            errors: list[str] = []
            warnings: list[str] = []
            memo_docx_renderer._validate_source(
                source,
                f"{name}:sources[{index}]",
                errors,
                private_material=False,
                strict_sources=False,
                warnings=warnings,
            )
            # The v2 draft is the English-only package (zh filled later).
            errors = [e for e in errors if not e.endswith(".zh is required")]
            assert errors == [], (name, index, errors)
            assert memo_docx_renderer._source_class_label(source, "zh") != "其他来源", (
                name,
                source.get("class"),
            )


# ---- components and block shapes ---------------------------------------------


def _registry_component_ids() -> set[str]:
    return {str(c["id"]) for c in memo_structure.LATE.components} | {
        str(c["id"])
        for stage, version in STRUCTURE_FILES.values()
        for c in memo_structure.load_structure(stage, version).components
    }


def test_every_component_the_prompts_name_is_accepted():
    renderer_source = (ROOT / "server" / "memo_docx_renderer.py").read_text(encoding="utf-8")
    known = _registry_component_ids() | set(memo_docx_renderer._BOLD_LEAD_COMPONENTS)
    prescribed = set(_COMPONENT_RE.findall(_prompt_text()))
    assert prescribed >= {"key_metrics_snapshot", "deal_terms", "glossary", "investment_highlights"}
    for slug in sorted(prescribed):
        accepted = (
            slug in known
            or f'"{slug}"' in renderer_source  # special-cased by the renderer
            or slug in PLAIN_BLOCK_SLUGS
        )
        assert accepted, f"prompts prescribe component {slug!r} nothing renders or validates"
        errors: list[str] = []
        memo_docx_renderer._validate_block(
            {
                "type": "bullets",
                "component": slug,
                "items": [{"en": "A claim with a number, 12%.", "zh": "一个带数字的论断，12%。"}],
            },
            f"block[{slug}]",
            errors,
        )
        assert errors == [], (slug, errors)
        assert memo_docx_renderer._declared_component_ids({"component": slug}) == [slug]


def test_glossary_block_shape_the_prompts_prescribe_validates():
    assert "glossary" in memo_docx_renderer.SUPPORTED_BLOCK_TYPES
    assert memo_docx_renderer.GLOSSARY_TITLE == {"en": "Terms used", "zh": "术语说明"}
    block = {
        "type": "glossary",
        "component": "glossary",
        "items": [
            {
                "term": {"en": "MOIC", "zh": "MOIC（回报倍数）"},
                "definition": {
                    "en": "money returned divided by money invested",
                    "zh": "收回的钱除以投入的钱",
                },
            },
            {
                "term": {"en": "IRR", "zh": "IRR（内部收益率）"},
                "definition": {
                    "en": "the annualized return over the holding period",
                    "zh": "持有期内的年化回报",
                },
            },
        ],
    }
    errors: list[str] = []
    memo_docx_renderer._validate_block(block, "glossary", errors)
    assert errors == []
    assert len(memo_docx_renderer.glossary_items(block)) == 2
    text = _prompt_text()
    # Every prescription names the block type the renderer validates, and
    # none still describes the glossary as a table.
    assert text.count('`glossary` block') >= 6
    assert not re.search(r'`table` block with `component:\s*"glossary"`', text)
    assert '"Terms used"' in text and "术语说明" in memo_prompts.load_prompt("structure_addendum.md")
    for rel in STRUCTURE_FILES:
        spec = memo_prompts.load_prompt(rel)
        assert re.search(r'component:\s*"glossary"', spec), rel
        assert "LAST block" in spec, rel


def test_heading_and_chart_shapes_the_addendum_prescribes_validate():
    errors: list[str] = []
    memo_docx_renderer._validate_block(
        {"type": "heading", "level": 2, "text": {"en": "1. Company profile", "zh": "1. 项目基本概况"}},
        "heading",
        errors,
    )
    assert errors == []
    chart = {
        "type": "chart",
        "chart_type": "bar",
        "title": {"en": "Gross MOIC by scenario", "zh": "各情景毛回报倍数"},
        "unit": {"en": "x", "zh": "倍"},
        "reading": {"en": "Higher is better", "zh": "越高越好"},
        "caption": {"en": "The base case barely returns capital.", "zh": "基准情形勉强收回本金。"},
        "series": [
            {
                "label": "Gross MOIC",
                "points": [{"x": "Bear", "y": 0.5}, {"x": "Base", "y": 1.5}, {"x": "Bull", "y": 3.0}],
            }
        ],
        "source_ids": ["S1"],
    }
    memo_docx_renderer._validate_chart_block(chart, "chart", errors)
    assert errors == []
    for chart_type in memo_docx_renderer.SUPPORTED_CHART_TYPES:
        assert f'"{chart_type}"' in memo_prompts.load_prompt("structure_addendum.md"), chart_type


def test_missing_cell_and_placeholder_wording_pass_validators_and_lint():
    text = _prompt_text()
    placeholders = sorted(set(_PLACEHOLDER_RE.findall(text)))
    assert placeholders == ["[TO BE DETERMINED BY IC]", "[重仓 / 跟投 / 卡位 — IC to select]"]
    for placeholder in placeholders:
        errors: list[str] = []
        memo_docx_renderer._validate_localized_value(
            {"en": f"Proposed amount: {placeholder}", "zh": f"拟投金额：{placeholder}"},
            "callout.items[0]",
            errors,
        )
        assert errors == [], placeholder
        # The lint bans bracketed source tokens; the fund placeholders are
        # not source-like and must survive it.
        assert not memo_quality_lint._source_like_bracket(placeholder), placeholder
    errors = []
    memo_docx_renderer._validate_block(
        {
            "type": "callout",
            "component": "investment_decision",
            "title": {"en": "Recommendation", "zh": "投资建议"},
            "items": [
                {"en": "Proposed amount: [TO BE DETERMINED BY IC]", "zh": "拟投金额：[TO BE DETERMINED BY IC]"},
                {"en": "Strategy: [重仓 / 跟投 / 卡位 — IC to select]", "zh": "策略：[重仓 / 跟投 / 卡位 — IC to select]"},
            ],
        },
        "callout",
        errors,
    )
    assert errors == []
    errors = []
    memo_docx_renderer._validate_localized_value(
        {"en": "Not disclosed — the mark has no denominator", "zh": "未披露——估值没有分母"},
        "cell",
        errors,
    )
    assert errors == []


# ---- calculation notes and citations ------------------------------------------


def test_calculation_note_shape_and_citation_gate_match_the_prompts():
    note = {
        "id": "C1",
        "label": "Entry multiple on the blended aggregate",
        "inputs": [
            {"name": "Entry mark", "value": "$1,000M", "ref": "S1"},
            {"name": "Aggregate", "value": "$450M", "ref": "S1"},
        ],
        "formula": "$1,000M ÷ $450M",
        "result": "2.2x",
        "meaning": "A mark divided by a number of unknown composition.",
    }
    assert memo_docx_renderer._calculation_errors({"calculations": [note]}) == []
    schema = claude_runner._spine_calculations_schema()
    assert set(note) <= set(schema["items"]["properties"])
    v2 = claude_runner.memo_fast_english_spine_schema(memo_structure.load_structure("late", 2))
    assert "calculations" in v2["properties"]["shared_facts"]["properties"]
    # Citing a pinned note passes; citing one the package does not carry is
    # the deterministic failure the v1 profile's conditional wording avoids.
    package = {
        "sources": [{"id": "S1"}],
        "calculations": [note],
        "sections": [
            {"id": "financial_forecast_valuation", "blocks": [{"type": "paragraph", "text": {"en": "2.2x [C1] on the mark [S1].", "zh": ""}}]}
        ],
    }
    assert memo_docx_renderer._citation_errors(package) == []
    package["calculations"] = []
    assert any("unknown_citation [C1]" in e for e in memo_docx_renderer._citation_errors(package))
    # v1 lint never flags a calculation-note token, so a v1 memo citing a
    # pinned note is safe; a bare source token stays banned in v1.
    assert not memo_quality_lint._source_like_bracket("[C1]")
    assert memo_quality_lint._source_like_bracket("[S1]")
    late_v1 = memo_prompts.load_prompt("structures/late.md")
    v1_props = claude_runner.MEMO_FAST_ENGLISH_SPINE_SCHEMA["properties"]["shared_facts"]["properties"]
    assert "When the pin sheet carries no calculation notes" in late_v1
    assert "cite ONLY the ids the\npin sheet lists" in late_v1
    if "base_case_outcome" not in v1_props:
        # Until the spine can pin it, the prompt must keep the echo optional.
        assert "When the shared fact sheet pins `base_case_outcome`" in late_v1
    assert "Headline terms" in late_v1 and "three-line summary" in late_v1


# ---- structure ids, pass ids, type lenses --------------------------------------


def test_section_ids_pass_ids_and_components_agree_with_the_loaders():
    pass_ids = _pass_ids()
    registry = _registry_component_ids()
    for rel, (stage, version) in STRUCTURE_FILES.items():
        text = memo_prompts.load_prompt(rel)
        structure = memo_structure.load_structure(stage, version)
        assert tuple(_SECTION_HEADER_RE.findall(text)) == structure.section_ids, rel
        for section in structure.sections:
            assert set(section.pass_affinity) <= pass_ids, (rel, section.id)
            assert set(section.components) <= registry, (rel, section.id)
            for slug in _COMPONENT_RE.findall(structure.section_specs()[section.id]):
                assert slug in registry | set(memo_docx_renderer._BOLD_LEAD_COMPONENTS) | PLAIN_BLOCK_SLUGS | {"glossary"}, (rel, section.id, slug)
    for key in memo_structure.COMPANY_TYPE_KEYS:
        profile = memo_structure.load_company_type(key)
        assert profile is not None, key
        assert set(profile.research_focus) <= pass_ids | {"all"}, (key, sorted(profile.research_focus))


def test_pass_rules_name_only_fields_the_pass_schema_carries():
    rules = memo_prompts.load_pass_rules()
    schema = claude_runner.MEMO_FAST_PASS_SCHEMA["properties"]
    finding = schema["key_findings"]["items"]["properties"]
    assert "evidence_quote" in rules and "evidence_quote" in finding
    quote_props = finding["evidence_quote"]["properties"]
    assert {"url", "quote"} <= set(quote_props)
    assert "300 characters" in rules
    for field in re.findall(r"`([a-z_]+)`", rules):
        if field in ("evidence_quote",):
            continue
        assert field in schema or field in finding or field in quote_props, field
    assert "Searched, not found:" in rules
    assert "supporting_evidence" in rules and "remaining_evidence_limits" in rules
    # The rules block is shared by every pass and the v1 writers, so it must
    # never start a pass block of its own.
    assert "## pass:" not in rules and "Pass: " not in rules


def test_define_once_and_pins_once_rules_are_stated_in_both_contexts():
    voice = memo_prompts.load_prompt("voice_contract.md")
    addendum = memo_prompts.load_prompt("structure_addendum.md")
    assert "explain a term the first time it appears; never re-define it" in voice
    assert "never re-define it" in addendum
    assert "senior investor who has never seen this company" not in addendum
    assert "## Pins once per section (structure v2)" in addendum
    assert "at most ONCE per section" in voice
    assert 'written as "not disclosed"' in voice
    assert "Estimate discipline" in addendum
    for rel in ("structures/late_compact.md", "structures/late_v2.md", "structures/growth.md", "structures/early.md"):
        assert "stated verbatim once" in memo_prompts.load_prompt(rel) or "PINS ARE STATED ONCE" in memo_prompts.load_prompt(rel), rel
    assert "PINS ARE THE FLOOR" in memo_prompts.load_prompt("structures/late_compact.md")
