"""Single source of truth for the memo report structure.

Stage profiles live in ``server/skills/structures/{stage}.md`` (per-section
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
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

STRUCTURES_DIR = Path(__file__).resolve().parent / "skills" / "structures"

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

    @property
    def section_ids(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sections)

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
        return {"stage": self.stage, "version": self.version}

    def profile_digest(self) -> str:
        """Short digest of the profile + component files — lets a run
        record (and a prompt assert) exactly which structure text it ran
        against."""
        hasher = hashlib.sha256()
        hasher.update(_profile_path(self.stage, self.version).read_bytes())
        hasher.update((STRUCTURES_DIR / "components.yaml").read_bytes())
        return hasher.hexdigest()[:12]


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


@lru_cache(maxsize=None)
def load_structure(stage: str, version: int = 1) -> MemoStructure:
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
    )
    if structure.stage != stage or structure.version != version:
        raise ValueError(
            f"profile {_profile_path(stage, version).name} declares "
            f"stage={structure.stage!r} version={structure.version} but was "
            f"loaded as stage={stage!r} version={version}"
        )
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


def active_structure(stage: str = "late") -> MemoStructure:
    """The structure a NEW pipeline run should use for this stage.

    Default (flag off): every run writes the historical late v1
    structure regardless of stage — classification is advisory until the
    owner's live test rounds sign the restructure off (Round 5 flips
    this default). ``BSH_MEMO_STRUCTURE_V2=1`` opts a run into the
    restructure: the classified stage picks its profile (late -> the
    12-section late v2, growth/early -> their own profiles), and a stage
    without a profile falls back to the late v2 chain."""
    if os.environ.get("BSH_MEMO_STRUCTURE_V2", "0") != "1":
        return LATE
    for candidate in ((stage, 2), (stage, 1), ("late", 2)):
        try:
            return load_structure(*candidate)
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
        try:
            return load_structure(stage, version)
        except (FileNotFoundError, ValueError):
            return LATE
    return LATE
