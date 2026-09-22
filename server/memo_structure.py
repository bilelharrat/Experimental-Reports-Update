"""Single source of truth for the memo report structure.

Stage profiles live in ``skills/memo/structures/{stage}.md`` (per-section
YAML metadata + the section's prompt contract as the markdown body) plus the
shared ``components.yaml``. Everything that used to be a scattered literal —
section ids, numbered titles, Chinese-parity regexes, section specs,
component→section routing, content floors, pass affinity, lint heading
recognition — derives from one loaded :class:`MemoStructure`.

Round 0 encodes the pre-restructure 5-section memo verbatim, so every
derived value is byte-equal to the old constants (pinned by
``tests/test_memo_structure.py``). Later rounds add stage profiles and the
v2 structure; the profile files are the iteration surface.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import memo_flags

# Repo-root skills/memo/structures — the editorial stage profiles, beside
# the other memo prompts the founder's team edits (see skills/memo/README.md).
STRUCTURES_DIR = Path(__file__).resolve().parents[1] / "skills" / "memo" / "structures"

_ROMAN = (
    "I II III IV V VI VII VIII IX X XI XII XIII XIV XV".split()
)


def _roman(position: int) -> str:
    return _ROMAN[position - 1]


@dataclass(frozen=True)
class ContentFloor:
    min_real_blocks: int = 1
    bullets_or_prose: bool = False
    require_valuation_refs: bool = False


@dataclass(frozen=True)
class SubsectionDef:
    """A fixed, numbered subsection inside a section (v2-family profiles).

    Rendered as a level-2 heading block "N. {title}" in both locales
    (numbering restarts at 1 inside each section, arabic in both
    languages — roman/Chinese-numeral prefixes get dropped by the
    renderer as section-title restatements). The generation-time gate
    requires each declared subsection to appear, in order."""

    en: str
    zh: str


@dataclass(frozen=True)
class SectionDef:
    id: str
    en_title: str  # bare — numbering is positional
    zh_title: str
    parity_en: str | None
    parity_zh: str | None
    contract_md: str
    components: tuple[str, ...]
    floor: ContentFloor
    pass_affinity: frozenset[str]
    title_word_aliases: tuple[str, ...] = ()
    role: str | None = None
    # Scorecard dimensions this section owns (v2-family profiles): the
    # section's analysis produces those dimensions' scores.
    scorecard_dimensions: tuple[str, ...] = ()
    # Fixed numbered subsections (v2-family profiles); empty for late v1.
    subsections: tuple[SubsectionDef, ...] = ()
    # SOFT English word target for the whole section (all `en` text, table
    # cells included). None = no gate — declared only by compact profiles,
    # whose prose budgets alone failed to keep sections short in two live
    # runs. Reaching it is a signal to land the section, not a stop: the
    # writer finishes the point it is on and closes.
    budget_words: int | None = None
    # What multiple of `budget_words` the generation-time gate actually
    # rejects at. Per-section because the sections differ in how much a
    # complete answer costs — a risk register that has genuinely found
    # eight risks cannot be as short as a valuation summary. Owner-set
    # 2026-09-16. None falls back to _BUDGET_GRACE in the renderer.
    budget_hard_multiple: float | None = None


@dataclass(frozen=True)
class PseudoSection:
    id: str
    en_title: str
    zh_title: str
    numbered: bool
    parity_en: str | None = None
    parity_zh: str | None = None


# The nine fixed scorecard dimensions, canonical order (weights vary per
# stage profile; the keys never do).
SCORECARD_DIMENSION_KEYS: tuple[str, ...] = (
    "market_size_growth",
    "industry_position",
    "moat",
    "revenue_growth_quality",
    "business_model_ue",
    "team_governance",
    "valuation",
    "exit_certainty",
    "risk_reward",
)

# Plain-language names for the nine dimensions. The pin sheet, the
# executive summary's opening "case rests on ..." sentence, and the
# highlight headlines all use these so every section names a dimension
# the same way (founder feedback 2026-09-13: say WHICH aspects carry the
# case before explaining them).
SCORECARD_DIMENSION_LABELS: dict[str, dict[str, str]] = {
    "market_size_growth": {"en": "market size and growth", "zh": "市场空间与增速"},
    "industry_position": {"en": "industry position", "zh": "行业地位"},
    "moat": {"en": "moat", "zh": "护城河"},
    "revenue_growth_quality": {
        "en": "revenue growth and quality",
        "zh": "收入增长与质量",
    },
    "business_model_ue": {
        "en": "business model and unit economics",
        "zh": "商业模式与单位经济",
    },
    "team_governance": {"en": "team and governance", "zh": "团队与治理"},
    "valuation": {"en": "valuation", "zh": "估值"},
    "exit_certainty": {"en": "exit certainty", "zh": "退出确定性"},
    "risk_reward": {"en": "risk-reward balance", "zh": "风险收益比"},
}

# How a dimension's score reads in one word. Derived, never written by a
# model, so the scan, the highlights and the risk list can never disagree
# about whether a dimension is a strength.
SCORECARD_BANDS: tuple[tuple[str, float], ...] = (
    ("strong", 0.75),
    ("adequate", 0.50),
    ("weak", 0.0),
)
SCORECARD_BAND_LABELS: dict[str, dict[str, str]] = {
    "strong": {"en": "strong", "zh": "强"},
    "adequate": {"en": "adequate", "zh": "中等"},
    "weak": {"en": "weak", "zh": "弱"},
}


def scorecard_band(score: int, max_score: int) -> str:
    """"strong" / "adequate" / "weak" for one dimension's score."""
    if not isinstance(max_score, int) or max_score <= 0:
        return "weak"
    ratio = score / max_score
    for name, floor in SCORECARD_BANDS:
        if ratio >= floor:
            return name
    return "weak"


# How many risks a run pins, and therefore how many cards the register
# renders. ONE definition, read by the spine schema and by the renderer's
# card gate, because they were written separately and disagreed: the
# schema was raised to ten for the 16,000-word memo while the gate still
# demanded four to six, so a run that pinned ten risks could not produce
# a package that validated (live 2026-09-17).
#
# v1 keeps its own four-to-six: it is the default pipeline's frozen
# contract and its memo is a third of the length.
RISK_COUNT_V1 = (4, 6)
RISK_COUNT_V2 = (4, 10)


def risk_count_bounds(structure: "MemoStructure") -> tuple[int, int]:
    """(min, max) risk cards for this structure's family."""
    return RISK_COUNT_V2 if structure.scorecard_weights() else RISK_COUNT_V1


# The seven areas a pinned risk is filed under, so a risk first says
# WHICH aspect of the case it concentrates on.
RISK_AREA_KEYS: tuple[str, ...] = (
    "market",
    "technology",
    "competition",
    # Defensibility. The scorecard has weighted `moat` as high as 18 —
    # the single heaviest dimension in three of the six type files — while
    # the risk register had nowhere to file a moat risk. On the
    # 2026-09-17 RadixArk run the spine chose `area: "moat"` for the
    # memo's central risk ("the asset the price is paid for does not
    # belong to RadixArk"), was rejected by the enum, and on retry filed
    # it under `competition`, which is not what the argument says.
    "moat",
    "commercialization",
    "concentration",
    "team_governance_regulatory",
    "valuation_exit",
)

RISK_AREA_LABELS: dict[str, dict[str, str]] = {
    "market": {"en": "Market", "zh": "市场"},
    "technology": {"en": "Technology", "zh": "技术"},
    "competition": {"en": "Competition", "zh": "竞争"},
    "moat": {"en": "Moat & defensibility", "zh": "护城河与壁垒"},
    "commercialization": {"en": "Commercialization", "zh": "商业化"},
    "concentration": {"en": "Concentration", "zh": "集中度"},
    "team_governance_regulatory": {
        "en": "Team, governance & regulation",
        "zh": "团队、治理与监管",
    },
    "valuation_exit": {"en": "Valuation & exit", "zh": "估值与退出"},
}

# Company types (the fund's five focus verticals plus a fallback). Phase 1
# classifies a run into one; the type file under skills/memo/types/
# steers Phase 2 research focus, the Phase 3 analysis lens, and an
# optional per-stage scorecard weight overlay. Registry key: `vertical`
# (`company_type` is already public|private).
COMPANY_TYPE_KEYS: tuple[str, ...] = (
    "ai_foundation_model",
    "ai_infra",
    "ai_application",
    "ai_video_short_drama",
    "robotics",
    "other",
)

COMPANY_TYPE_LABELS: dict[str, dict[str, str]] = {
    "ai_foundation_model": {
        "en": "AI foundation model",
        "zh": "AI 大模型与前沿实验室",
    },
    "ai_infra": {"en": "AI infrastructure", "zh": "AI 基础设施"},
    "ai_application": {"en": "AI application", "zh": "AI 应用"},
    "ai_video_short_drama": {"en": "AI video & short drama", "zh": "AI 视频与短剧"},
    "robotics": {"en": "Robotics", "zh": "机器人与具身智能"},
    "other": {"en": "Other", "zh": "其他"},
}

# Verdict tiers and their scorecard-total bands (inclusive bounds).
VERDICT_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Strong Buy", 85, 100),
    ("Buy", 80, 84),
    ("Watch", 70, 79),
    ("Pass", 0, 69),
)

VERDICT_ZH: dict[str, str] = {
    "Strong Buy": "强烈推荐",
    "Buy": "推荐投资",
    "Watch": "观察名单",
    "Pass": "不建议投资",
}


@dataclass(frozen=True)
class MemoStructure:
    stage: str
    version: int
    sections: tuple[SectionDef, ...]
    pseudo_sections: tuple[PseudoSection, ...]
    components: tuple[dict[str, Any], ...]
    lint_extra_titles: tuple[str, ...] = ()
    # dimension -> weight for the v2-family scorecard; empty for profiles
    # without one (late v1). Doubles as the v2-family marker: a structure
    # with a scorecard runs the v2 pin sheet, contracts, and gates.
    scorecard: dict[str, int] = field(default_factory=dict)
    # How the risk section presents the pinned risks: "cards" (heading +
    # six-row key_value table per risk — the full-report format, enforced
    # by the renderer's card gate) or "bullets" (compact profiles: one
    # verdict-lead bullet per pinned risk; the card gate stands down).
    risk_format: str = "cards"
    # The company type this structure was resolved for (None = no type
    # lens, stage-default weights). Carried in meta() so gates and the
    # renderer re-resolve the same effective weights.
    company_type: str | None = None
    # The INVESTMENT stage this run CLASSIFIED, when the profile serving
    # it belongs to another one. Compact mode loads `late_compact` for
    # every stage, and its `pin_stage` is "late", so keying anything off
    # the profile made `growth` and `early` unreachable in the mode we
    # actually ship — every type file's `growth:` block was dead code
    # (measured 2026-09-17 on the RadixArk seed run, which was scored on
    # late weights). The classified stage travels here instead, and
    # `declared_stage` is what the run says out loud.
    overlay_stage: str | None = None

    @property
    def section_ids(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sections)

    @property
    def pin_stage(self) -> str:
        """The investment stage the spine pins (early/growth/late).

        A compact profile is named "{stage}_compact" so the loader and
        the package stamp can address it, but its INVESTMENT stage is
        the parent's: the spine schema enums early/growth/late, and the
        deterministic pin gate must compare against that — comparing
        against the profile name killed the first compact live run
        (pinned 'late' vs profile 'late_compact')."""
        stage = self.stage
        return stage[: -len("_compact")] if stage.endswith("_compact") else stage

    @property
    def declared_stage(self) -> str:
        """The investment stage this run SAYS it is — what the spine pins,
        the pin gate checks, the memo prose reads and the UI chip shows.

        `pin_stage` answers a different question: which stage family the
        profile belongs to. The two agree in full mode, where each stage
        has its own profile. In compact mode they do not: every stage is
        served by `late_compact`, so a seed company used to be told to
        pin "late" — and did, correctly by the gate and wrongly by the
        facts, while its own scorecard was already scored on early
        weights (RadixArk 2026-09-20__042036: team scored 16, over the
        late map's max of 10)."""
        return self.overlay_stage or self.pin_stage

    def section(self, section_id: str) -> SectionDef | None:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def section_for_role(self, role: str) -> SectionDef:
        for s in self.sections:
            if s.role == role:
                return s
        raise KeyError(f"no section carries role {role!r} in stage {self.stage}")

    # ---- derivations (each byte-equal to a former literal) ---------------

    def section_titles(self) -> dict[str, dict[str, str]]:
        """Renderer SECTION_TITLES: numbered from position, both locales."""
        titles: dict[str, dict[str, str]] = {}
        position = 0
        for s in self.sections:
            position += 1
            titles[s.id] = {
                "en": f"{_roman(position)}. {s.en_title}",
                "zh": f"{_roman(position)}. {s.zh_title}",
            }
        for ps in self.pseudo_sections:
            if ps.numbered:
                position += 1
                titles[ps.id] = {
                    "en": f"{_roman(position)}. {ps.en_title}",
                    "zh": f"{_roman(position)}. {ps.zh_title}",
                }
            else:
                titles[ps.id] = {"en": ps.en_title, "zh": ps.zh_title}
        return titles

    def parity_patterns(self) -> dict[str, dict[str, re.Pattern]]:
        patterns: dict[str, dict[str, re.Pattern]] = {}
        for s in self.sections:
            if s.parity_en and s.parity_zh:
                patterns[s.id] = {
                    "en": re.compile(s.parity_en, re.IGNORECASE),
                    "zh": re.compile(s.parity_zh, re.IGNORECASE),
                }
        for ps in self.pseudo_sections:
            if ps.parity_en and ps.parity_zh:
                patterns[ps.id] = {
                    "en": re.compile(ps.parity_en, re.IGNORECASE),
                    "zh": re.compile(ps.parity_zh, re.IGNORECASE),
                }
        return patterns

    def section_specs(self) -> dict[str, str]:
        return {s.id: s.contract_md for s in self.sections}

    def component_section(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for s in self.sections:
            for slug in s.components:
                mapping[slug] = s.id
        return mapping

    def title_words(self) -> dict[str, str]:
        words: dict[str, str] = {}
        for s in self.sections:
            words[s.en_title.lower()] = s.id
            for alias in s.title_word_aliases:
                words[alias.lower()] = s.id
        return words

    def pass_affinity(self) -> dict[str, frozenset[str]]:
        return {
            s.id: s.pass_affinity for s in self.sections if s.pass_affinity
        }

    def content_floors(self) -> dict[str, ContentFloor]:
        return {s.id: s.floor for s in self.sections}

    def numbered_prefix_pattern(self) -> re.Pattern:
        """Lowercased roman-prefix recognizer for lint section boundaries
        (covers every numbered position this structure renders)."""
        count = len(self.sections) + sum(
            1 for ps in self.pseudo_sections if ps.numbered
        )
        alternatives = "|".join(_roman(i).lower() for i in range(1, count + 1))
        return re.compile(rf"^({alternatives})\.\s+")

    def lint_section_titles(self) -> frozenset[str]:
        """Bare heading strings lint recognizes as section boundaries."""
        titles = {s.en_title.lower() for s in self.sections}
        for s in self.sections:
            titles.update(a.lower() for a in s.title_word_aliases)
        titles.update(t.lower() for t in self.lint_extra_titles)
        return frozenset(titles)

    def numbered_lint_key(self, role: str) -> str:
        """The lowercased numbered EN title lint uses as a block.section
        key (e.g. "iv. investment risk")."""
        target = self.section_for_role(role)
        position = self.section_ids.index(target.id) + 1
        return f"{_roman(position).lower()}. {target.en_title.lower()}"

    def scorecard_weights(self) -> dict[str, int]:
        """dimension -> max score for this stage; empty means the profile
        predates the scorecard (late v1)."""
        return dict(self.scorecard)

    def scorecard_owner(self, dimension: str) -> SectionDef | None:
        for section in self.sections:
            if dimension in section.scorecard_dimensions:
                return section
        return None

    def meta(self) -> dict[str, Any]:
        """The identity stamp carried inside every memo package, so gates
        and renderers resolve the structure the package was written
        against (:func:`for_package`)."""
        meta: dict[str, Any] = {"stage": self.stage, "version": self.version}
        if self.company_type:
            meta["company_type"] = self.company_type
        # Only when it disagrees with the profile: a `late` company in
        # the compact profile resolves identically either way, and
        # stamping it there would churn every existing package.
        if self.overlay_stage and self.overlay_stage != self.pin_stage:
            meta["overlay_stage"] = self.overlay_stage
        return meta

    def profile_digest(self) -> str:
        """Short digest of the profile + component files (+ the company
        type file when one applies) — lets a run record (and a prompt
        assert) exactly which structure text it ran against."""
        hasher = hashlib.sha256()
        hasher.update(_profile_path(self.stage, self.version).read_bytes())
        hasher.update((STRUCTURES_DIR / "components.yaml").read_bytes())
        if self.company_type:
            type_path = _type_path(self.company_type)
            if type_path.exists():
                hasher.update(type_path.read_bytes())
        return hasher.hexdigest()[:12]


# ---- company type profiles ----------------------------------------------

# Repo-root skills/memo/types/<type>.md — the editorial prompt files the
# founder's team edits (with zh twins under skills/memo/zh/).
TYPES_DIR = Path(__file__).resolve().parents[1] / "skills" / "memo" / "types"


@dataclass(frozen=True)
class CompanyTypeProfile:
    type: str
    label: dict[str, str]
    # stage family (early|growth|late) -> full nine-key weight map
    scorecard: dict[str, dict[str, int]]
    # pass_id (or "all") -> research focus addendum for Phase 2
    research_focus: dict[str, str]
    # section id -> how much MORE (or less) of the report this type
    # deserves to spend there, as a multiplier on the profile's
    # `budget_words`. The owner's ask, 2026-09-16: "different types of
    # companies may have different things to write more about, and we
    # should adjust accordingly". Total length is preserved — emphasis
    # moves words between sections, it never adds them.
    section_emphasis: dict[str, float]
    # The analysis lens appended to the Phase 3 shared context
    body: str

    def focus_for(self, pass_id: str) -> str:
        parts = [
            str(self.research_focus.get("all") or "").strip(),
            str(self.research_focus.get(pass_id) or "").strip(),
        ]
        return "\n".join(p for p in parts if p)


def _type_path(company_type: str) -> Path:
    return TYPES_DIR / f"{company_type}.md"


@lru_cache(maxsize=None)
def load_company_type(company_type: str | None) -> CompanyTypeProfile | None:
    """The type profile for ``company_type``; None when the type is unset,
    unknown, or has no file (a run then behaves exactly as before)."""
    if not company_type or company_type not in COMPANY_TYPE_KEYS:
        return None
    path = _type_path(company_type)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter")
    _, front, body = text.split("---", 2)
    head = yaml.safe_load(front) or {}
    if str(head.get("type") or "") != company_type:
        raise ValueError(
            f"{path.name}: declares type {head.get('type')!r}, expected "
            f"{company_type!r}"
        )
    scorecard: dict[str, dict[str, int]] = {}
    for family, weights in (head.get("scorecard") or {}).items():
        if not isinstance(weights, dict):
            continue
        scorecard[str(family)] = {str(k): int(v) for k, v in weights.items()}
    label = head.get("label") or {}
    return CompanyTypeProfile(
        type=company_type,
        label={
            "en": str(label.get("en") or COMPANY_TYPE_LABELS[company_type]["en"]),
            "zh": str(label.get("zh") or COMPANY_TYPE_LABELS[company_type]["zh"]),
        },
        scorecard=scorecard,
        research_focus={
            str(k): str(v) for k, v in (head.get("research_focus") or {}).items()
        },
        section_emphasis={
            str(k): float(v)
            for k, v in (head.get("section_emphasis") or {}).items()
        },
        body=body.strip(),
    )


# How far a type may push one section's share. A type file that wanted a
# section at four times the profile's length would be arguing for a
# different profile, not an emphasis.
_EMPHASIS_MIN = 0.6
_EMPHASIS_MAX = 2.0


# Sections a company type may NOT re-cut. Their length is set by what
# they must contain, not by how interesting the type finds them: the
# decision section carries the recommendation, the conditions and the
# disconfirming evidence, and valuation carries three scenarios with MOIC
# and IRR, the fair-value bridge and the entry multiple. None of that
# shrinks because a type cares more about moat.
#
# Every type file marks at least one of the two down, and between
# 2026-09-16 and 2026-09-17 they produced four cap overruns across three
# live runs (Databricks investment_decision 1794/1725 and
# valuation_returns 2467/2405, RadixArk investment_decision 1816/1725,
# Figure AI valuation_returns at its cap) — each one buying a repair pass
# to shed a few dozen words.
_EMPHASIS_EXEMPT = frozenset({"investment_decision", "valuation_returns"})


def _emphasized_sections(
    sections: tuple["SectionDef", ...], emphasis: dict[str, float]
) -> tuple["SectionDef", ...]:
    """Re-cut the section word budgets by a type's emphasis, same total.

    Emphasis is a claim about PROPORTION — "for a robotics company the
    deployment evidence deserves more of the report than the moat
    argument does" — so the weights are renormalized back onto the
    profile's own total. A type cannot lengthen the memo; only the owner
    editing `budget_words` can do that.

    Two sections are exempt, because their length is set by the structure
    rather than by how interesting the type finds them (see
    ``_EMPHASIS_EXEMPT``).
    """
    budgeted = [
        s for s in sections
        if s.budget_words and s.id not in _EMPHASIS_EXEMPT
    ]
    if not budgeted or not emphasis:
        return sections
    total = sum(s.budget_words or 0 for s in budgeted)
    weights = {
        s.id: (s.budget_words or 0)
        * min(_EMPHASIS_MAX, max(_EMPHASIS_MIN, emphasis.get(s.id, 1.0)))
        for s in budgeted
    }
    weighted_total = sum(weights.values())
    if weighted_total <= 0:
        return sections
    scale = total / weighted_total
    recut: dict[str, int] = {
        section_id: max(1, round(weight * scale / 50) * 50)
        for section_id, weight in weights.items()
    }
    return tuple(
        replace(s, budget_words=recut[s.id]) if s.id in recut else s
        for s in sections
    )


def company_type_lens(structure: "MemoStructure") -> str:
    """The Phase 3 shared-context block for the structure's company type
    (empty when none): a heading plus the type file body."""
    profile = load_company_type(structure.company_type)
    if profile is None or not profile.body:
        return ""
    return f"## Company type lens — {profile.label['en']}\n{profile.body}"


def company_type_research_focus(
    structure: "MemoStructure", pass_id: str
) -> str:
    """The Phase 2 per-pass research addendum for the structure's company
    type (empty when none)."""
    profile = load_company_type(structure.company_type)
    if profile is None:
        return ""
    return profile.focus_for(pass_id)


_SECTION_HEADER_RE = re.compile(r"^## section: ([a-z0-9_]+)\s*$")


def _parse_profile(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter")
    _, front, rest = text.split("---", 2)
    head = yaml.safe_load(front)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    lines = rest.splitlines()
    i = 0
    while i < len(lines):
        match = _SECTION_HEADER_RE.match(lines[i])
        if match:
            if lines[i + 1].strip() != "```yaml":
                raise ValueError(
                    f"{path.name}: section {match.group(1)} missing yaml fence"
                )
            j = i + 2
            meta_lines = []
            while lines[j].strip() != "```":
                meta_lines.append(lines[j])
                j += 1
            current = yaml.safe_load("\n".join(meta_lines))
            if current.get("id") != match.group(1):
                raise ValueError(
                    f"{path.name}: header/id mismatch at {match.group(1)}"
                )
            current["contract_md"] = []
            sections.append(current)
            i = j + 1
            continue
        if current is not None:
            current["contract_md"].append(lines[i])
        i += 1
    for section in sections:
        section["contract_md"] = "\n".join(section["contract_md"]).strip()
    head["section_list"] = sections
    return head


def _profile_path(stage: str, version: int = 1) -> Path:
    name = stage if version == 1 else f"{stage}_v{version}"
    return STRUCTURES_DIR / f"{name}.md"


# The investment stages a run can classify a company into — the spine
# schema's `stage` enum, and the only values `declared_stage` may take.
INVESTMENT_STAGES = ("early", "growth", "late")


@lru_cache(maxsize=None)
def load_structure(
    stage: str,
    version: int = 1,
    company_type: str | None = None,
    overlay_stage: str | None = None,
) -> MemoStructure:
    """Load a stage profile. With ``company_type``, the type file's
    scorecard overlay for this stage family (if any) replaces the
    profile's weights — the sum-100 validation still runs on the
    result — and the structure carries the type in its meta.

    ``overlay_stage`` is the stage the run CLASSIFIED. It is kept on the
    structure (and stamped into the package meta) whenever the profile
    serving the run belongs to another stage, with or without a company
    type: it is what the run declares as the company's stage, not just
    where the weight overlay is read from."""
    # A stage we do not recognise is not a stage the run can declare:
    # the spine schema enums early/growth/late, so an unclassified run
    # must fall back to the profile's own family rather than pin a word
    # the schema will reject.
    if overlay_stage not in INVESTMENT_STAGES:
        overlay_stage = None
    if company_type:
        base = load_structure(stage, version)
        type_profile = load_company_type(company_type)
        if type_profile is None:
            return base
        key = overlay_stage or base.pin_stage
        overlay = type_profile.scorecard.get(key)
        scorecard = dict(base.scorecard)
        if overlay and base.scorecard:
            scorecard = {str(k): int(v) for k, v in overlay.items()}
        structure = replace(
            base,
            scorecard=scorecard,
            company_type=company_type,
            overlay_stage=key,
            sections=_emphasized_sections(
                base.sections, type_profile.section_emphasis
            ),
        )
        _validate_structure(structure)
        return structure
    profile = _parse_profile(_profile_path(stage, version))
    components_doc = yaml.safe_load(
        (STRUCTURES_DIR / "components.yaml").read_text(encoding="utf-8")
    )
    # A profile may declare `components:` in its front matter to include
    # only a subset of the shared registry (an early-stage memo has no
    # moat table to require). Default: every component.
    include = profile.get("components")
    include_set = set(include) if isinstance(include, list) else None
    components = tuple(
        {
            "id": c["id"],
            "label": c["label"],
            "block_types": set(c["block_types"]),
            "patterns": tuple(c["patterns"]),
        }
        for c in components_doc["components"]
        if include_set is None or c["id"] in include_set
    )
    if include_set is not None:
        known = {c["id"] for c in components_doc["components"]}
        unknown = include_set - known
        if unknown:
            raise ValueError(
                f"{stage} v{version} includes unknown components "
                f"{sorted(unknown)}"
            )
    sections = tuple(
        SectionDef(
            id=s["id"],
            en_title=s["en_title"],
            zh_title=s["zh_title"],
            parity_en=s.get("parity_en"),
            parity_zh=s.get("parity_zh"),
            contract_md=s["contract_md"],
            components=tuple(s.get("components") or ()),
            floor=ContentFloor(**(s.get("floor") or {})),
            pass_affinity=frozenset(s.get("pass_affinity") or ()),
            title_word_aliases=tuple(s.get("title_word_aliases") or ()),
            role=s.get("role"),
            scorecard_dimensions=tuple(s.get("scorecard_dimensions") or ()),
            subsections=tuple(
                SubsectionDef(en=str(sub["en"]), zh=str(sub["zh"]))
                for sub in s.get("subsections") or ()
            ),
            budget_words=(
                int(s["budget_words"]) if s.get("budget_words") else None
            ),
            budget_hard_multiple=(
                float(s["budget_hard_multiple"])
                if s.get("budget_hard_multiple")
                else None
            ),
        )
        for s in profile["section_list"]
    )
    pseudo = tuple(
        PseudoSection(
            id=ps["id"],
            en_title=ps["en_title"],
            zh_title=ps["zh_title"],
            numbered=bool(ps.get("numbered")),
            parity_en=ps.get("parity_en"),
            parity_zh=ps.get("parity_zh"),
        )
        for ps in profile.get("pseudo_sections") or ()
    )
    structure = MemoStructure(
        stage=profile["stage"],
        version=int(profile.get("version") or 1),
        sections=sections,
        pseudo_sections=pseudo,
        components=components,
        lint_extra_titles=tuple(profile.get("lint_extra_titles") or ()),
        scorecard={
            str(k): int(v)
            for k, v in (profile.get("scorecard") or {}).items()
        },
        risk_format=str(profile.get("risk_format") or "cards"),
    )
    if structure.stage != stage or structure.version != version:
        raise ValueError(
            f"profile {_profile_path(stage, version).name} declares "
            f"stage={structure.stage!r} version={structure.version} but was "
            f"loaded as stage={stage!r} version={version}"
        )
    if overlay_stage and overlay_stage != structure.pin_stage:
        structure = replace(structure, overlay_stage=overlay_stage)
    _validate_structure(structure)
    return structure


def _validate_structure(structure: MemoStructure) -> None:
    ids = structure.section_ids
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate section ids in stage {structure.stage}")
    known_components = {c["id"] for c in structure.components}
    for s in structure.sections:
        unknown = set(s.components) - known_components
        if unknown:
            raise ValueError(
                f"section {s.id} references unknown components {sorted(unknown)}"
            )
        if s.parity_en:
            re.compile(s.parity_en)
        if s.parity_zh:
            re.compile(s.parity_zh)
        seen_subs: set[str] = set()
        for sub in s.subsections:
            if not sub.en.strip() or not sub.zh.strip():
                raise ValueError(
                    f"section {s.id} declares a subsection with an empty title"
                )
            if re.match(r"^\s*\d", sub.en):
                raise ValueError(
                    f"section {s.id} subsection {sub.en!r} must not carry its "
                    "own number — numbering is positional"
                )
            key = sub.en.strip().lower()
            if key in seen_subs:
                raise ValueError(
                    f"section {s.id} declares duplicate subsection {sub.en!r}"
                )
            seen_subs.add(key)
    if structure.scorecard:
        keys = tuple(structure.scorecard)
        if set(keys) != set(SCORECARD_DIMENSION_KEYS):
            raise ValueError(
                f"stage {structure.stage} scorecard must carry exactly the "
                f"nine fixed dimensions; got {sorted(keys)}"
            )
        total = sum(structure.scorecard.values())
        if total != 100:
            raise ValueError(
                f"stage {structure.stage} scorecard weights sum to {total}, "
                "not 100"
            )
        owners: dict[str, str] = {}
        for s in structure.sections:
            for dimension in s.scorecard_dimensions:
                if dimension not in structure.scorecard:
                    raise ValueError(
                        f"section {s.id} owns unknown scorecard dimension "
                        f"{dimension!r}"
                    )
                if dimension in owners:
                    raise ValueError(
                        f"scorecard dimension {dimension!r} owned by both "
                        f"{owners[dimension]} and {s.id}"
                    )
                owners[dimension] = s.id
        missing = set(structure.scorecard) - set(owners)
        if missing:
            raise ValueError(
                f"stage {structure.stage} scorecard dimensions without an "
                f"owning section: {sorted(missing)}"
            )


def clear_cache() -> None:
    load_structure.cache_clear()


LATE = load_structure("late")


def active_structure(
    stage: str = "late", mode: str = "full", company_type: str | None = None
) -> MemoStructure:
    """The structure a NEW pipeline run should use for this stage.

    The restructure is on by default (``BSH_MEMO_STRUCTURE_V2``, see
    ``memo_flags``; the owner signed it off on 2026-09-22): the classified
    stage picks its profile (late -> the 12-section late v2, growth/early
    -> their own profiles), and a stage without a profile falls back to
    the late v2 chain. ``BSH_MEMO_STRUCTURE_V2=0`` restores the
    historical late v1 structure for every stage.

    ``mode="compact"`` prefers the stage's compact profile
    (``{stage}_compact.md`` — the short Wisdom-style memo: fewer merged
    sections, tight budgets, bullet-format risks) and falls back to the
    full chain when the stage has none, so the mode can ship stage by
    stage without ever failing a run."""
    if not memo_flags.enabled("BSH_MEMO_STRUCTURE_V2"):
        return LATE
    candidates: list[tuple[str, int]] = []
    if mode == "compact":
        candidates.append((f"{stage}_compact", 1))
        if stage != "late":
            candidates.append(("late_compact", 1))
    candidates.extend([(stage, 2), (stage, 1), ("late", 2)])
    for candidate in candidates:
        try:
            return load_structure(
                *candidate,
                company_type=company_type or None,
                # The stage the run CLASSIFIED, not the profile that ended
                # up serving it: compact falls back to `late_compact` for
                # every stage, so without this a growth or early company
                # is scored on late weights.
                overlay_stage=stage,
            )
        except (FileNotFoundError, ValueError):
            continue
    return LATE


def for_package(package: Any) -> MemoStructure:
    """Resolve the structure a memo package was written against, from the
    ``structure`` meta stamped into it at assembly. Packages without a
    stamp (legacy runs, hand-built fixtures) resolve to the late v1
    structure — exactly what every pre-registry package was."""
    meta = package.get("structure") if isinstance(package, dict) else None
    if isinstance(meta, dict):
        stage = str(meta.get("stage") or "").strip() or "late"
        try:
            version = int(meta.get("version") or 1)
        except (TypeError, ValueError):
            version = 1
        company_type = str(meta.get("company_type") or "").strip() or None
        overlay_stage = str(meta.get("overlay_stage") or "").strip() or None
        try:
            return load_structure(
                stage, version, company_type, overlay_stage=overlay_stage
            )
        except (FileNotFoundError, ValueError):
            return LATE
    return LATE
