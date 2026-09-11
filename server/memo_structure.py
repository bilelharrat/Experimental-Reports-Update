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


@dataclass(frozen=True)
class PseudoSection:
    id: str
    en_title: str
    zh_title: str
    numbered: bool
    parity_en: str | None = None
    parity_zh: str | None = None


@dataclass(frozen=True)
class MemoStructure:
    stage: str
    version: int
    sections: tuple[SectionDef, ...]
    pseudo_sections: tuple[PseudoSection, ...]
    components: tuple[dict[str, Any], ...]
    lint_extra_titles: tuple[str, ...] = ()

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


@lru_cache(maxsize=None)
def load_structure(stage: str) -> MemoStructure:
    profile = _parse_profile(STRUCTURES_DIR / f"{stage}.md")
    components_doc = yaml.safe_load(
        (STRUCTURES_DIR / "components.yaml").read_text(encoding="utf-8")
    )
    components = tuple(
        {
            "id": c["id"],
            "label": c["label"],
            "block_types": set(c["block_types"]),
            "patterns": tuple(c["patterns"]),
        }
        for c in components_doc["components"]
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


def clear_cache() -> None:
    load_structure.cache_clear()


LATE = load_structure("late")
