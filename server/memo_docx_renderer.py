"""Parameterized DOCX renderer for BSH investment memos.

Claude owns memo judgment and writes ``memo_package.json``. This module owns
all DOCX construction so memo runs do not generate bespoke Python/JS renderers.
"""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path
from typing import Any

import itertools

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from server import memo_structure

SCHEMA_VERSION = 1

EN_FONT = "Arial"
ZH_FONT = "Microsoft YaHei"
NAVY = "1B2A4A"
TIFFANY = "0ABAB5"
PALE_TIFFANY = "E6F7F6"
PALE_GOLD = "F7F0D9"
WARM_GREY = "F3F3F3"
WHITE = "FFFFFF"
BLACK = "111111"
GREY = "666666"
BORDER = "BFBFBF"

GENERATED_RENDERER_SCRIPT_PATTERNS = (
    "build_memo*.py",
    "build_memos*.py",
    "generate_memo*.py",
    "generate_memos*.py",
    "render_memo*.py",
    "render_memos*.py",
    "build_memo*.js",
    "build_memos*.js",
    "generate_memo*.js",
    "generate_memos*.js",
    "render_memo*.js",
    "render_memos*.js",
)

# Structure-derived skeleton (server/memo_structure.py is the single
# source of truth; numbering is positional). The module constants are the
# late v1 defaults; every validation/render path resolves the package's own
# structure from its ``structure`` meta stamp via ``_structure_for``.
SECTION_TITLES = memo_structure.LATE.section_titles()
REQUIRED_SECTION_IDS = memo_structure.LATE.section_ids
REQUIRED_MEMO_COMPONENTS = memo_structure.LATE.components


def _structure_for(package: Any) -> memo_structure.MemoStructure:
    return memo_structure.for_package(package)
SUPPORTED_BLOCK_TYPES = {
    "heading",
    "paragraph",
    "bullets",
    "callout",
    "table",
    "chart",
    "spacer",
}
SUPPORTED_CHART_TYPES = {"bar", "grouped_bar", "hbar", "line", "pie"}
_SINGLE_SERIES_CHART_TYPES = {"bar", "hbar", "pie"}
# Top-level section titles ("I."–"X." or "一、"–"十、") are emitted automatically
# by ``_add_section`` from ``SECTION_TITLES``. A heading *block* that carries the
# same numbered prefix is a redundant restatement of the section title; rendering
# it produces a doubled section heading (and trips the Chinese-parity
# heading-count gate, since EN/ZH restatements are not always recognized
# symmetrically). Legitimate sub-headings are unnumbered, so this prefix is a
# safe signal to drop the block.
_NUMBERED_SECTION_HEADING_RE = re.compile(
    # longest-first so xi..xv match before their x/i prefixes
    r"^\s*(?:(?:xiii|xiv|xii|xv|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\."
    r"|[一二三四五六七八九十]+[、.．])",
    re.IGNORECASE,
)
# Per-risk cards in `investment_risk`: a "Risk N: <one-line summary>" heading
# followed by a key_value table with these five row labels. Enforced at
# generation time only (english_package_validation_errors), so packages from
# runs that predate the format still re-render.
_RISK_CARD_HEADING_RE = re.compile(r"^\s*risk\s+(\d+)\s*[:：]\s*\S", re.IGNORECASE)
_RISK_RATING_VALUE_RE = re.compile(r"^\s*(10|[1-9])\s*/\s*10\b")
_RISK_LIKELIHOOD_VALUE_RE = re.compile(
    r"^\s*(high|medium|low|高|中|低)\s*[:：]\s*\S", re.IGNORECASE
)
_RISK_GENERIC_HEADINGS = {
    "commercial risk",
    "competition risk",
    "execution risk",
    "financing risk",
    "liquidity risk",
    "market risk",
    "regulatory risk",
    "technology risk",
    "valuation risk",
}
_RISK_GENERIC_WATCH_RE = re.compile(
    r"^\s*(?:monitor|track|watch|confirm|request|obtain|"
    r"cross[- ]check|verify|require|ensure|validate|ask for)\b",
    re.IGNORECASE,
)
_RISK_CARD_ROW_LABELS = (
    ("risk type", "Risk Type"),
    ("why it matters", "Why it matters"),
    ("what we watch", "What we watch"),
    ("likelihood", "Likelihood"),
    ("risk rating", "Risk Rating"),
)
# Risk Card v2 (structure-v2 family): Verdict and Impact rows open the
# card (founder feedback 2026-09-13 — say which aspect, how big, then
# explain), Mitigation joins it. "Why it matters" / "What we watch" keep
# their exact labels: the checks below index rows by those prefixes.
_RISK_CARD_ROW_LABELS_V2 = (
    ("risk type", "Risk Type"),
    ("verdict", "Verdict"),
    ("impact", "Impact"),
    ("why it matters", "Why it matters"),
    ("what we watch", "What we watch"),
    ("mitigation", "Mitigation"),
    ("likelihood", "Likelihood"),
    ("risk rating", "Risk Rating"),
)


def _risk_card_row_labels(
    structure: "memo_structure.MemoStructure",
) -> tuple[tuple[str, str], ...]:
    if structure.scorecard_weights():
        return _RISK_CARD_ROW_LABELS_V2
    return _RISK_CARD_ROW_LABELS


def _spelled_row_count(count: int) -> str:
    words = {5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    return words.get(count, str(count))
# The {section_id} placeholder is filled with the structure's risk-role
# section at check time, so the repair mapper can attribute the finding.
_RISK_CARD_FORMAT_HINT = (
    "section {section_id} must present risks as per-risk cards: 4-6 "
    "`heading` blocks titled 'Risk N: <one-line summary>', each immediately "
    "followed by a `table` block with component 'risk_register', layout "
    "'key_value', headers [], and exactly {row_count} two-cell rows labeled "
    "{row_list}, with 'Likelihood' written as 'High|Medium|Low: short "
    "reason' and 'Risk Rating' written as 'N/10: short reason', ordered "
    "highest rating first"
)
VALUATION_CONTENT_TERMS = (
    "model",
    "scenario",
    "range",
    "valuation",
    "revenue",
    "arr",
    "margin",
    "gross margin",
    "valuation sensitivity",
    "sensitivity",
    "multiple",
    "forecast",
    "收入",
    "估值",
    "情景",
    "区间",
    "毛利率",
    "利润率",
    "模型",
    "敏感性",
)
GENERIC_CONTENT_PATTERNS = (
    re.compile(r"^more diligence is needed\.?$", re.IGNORECASE),
    re.compile(r"^further diligence is needed\.?$", re.IGNORECASE),
    re.compile(r"^additional diligence is needed\.?$", re.IGNORECASE),
    re.compile(r"^to be determined\.?$", re.IGNORECASE),
    re.compile(r"^tbd\.?$", re.IGNORECASE),
)


class MemoRenderError(ValueError):
    """Raised when a memo package cannot be rendered."""


def find_generated_renderer_scripts(run_dir: Path | str) -> list[Path]:
    """Return forbidden per-run renderer scripts left by old memo workflows."""
    root = Path(run_dir)
    matches: list[Path] = []
    if not root.exists():
        return matches
    for pattern in GENERATED_RENDERER_SCRIPT_PATTERNS:
        matches.extend(path for path in root.rglob(pattern) if path.is_file())
    return sorted(set(matches))


def load_package(path: Path | str) -> dict:
    package_path = Path(path)
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoRenderError(f"Invalid memo package JSON: {exc}") from exc
    validate_package(package)
    return package


def validate_package(package: Any) -> None:
    """Fail closed when Claude's memo package is structurally incomplete."""
    errors = _package_validation_errors(package)
    if errors:
        raise MemoRenderError("Invalid memo package: " + "; ".join(errors))


def fill_blank_zh_placeholders(package: dict) -> dict:
    """Deep-copy a package and fill blank ``zh`` strings with a placeholder,
    so English-only (phase 3) output can pass through render-shaped checks."""
    import copy as _copy

    probe = _copy.deepcopy(package)

    def _fill_zh(node: Any) -> None:
        if isinstance(node, dict):
            if "en" in node and not str(node.get("zh") or "").strip():
                node["zh"] = "占位"
            for value in node.values():
                _fill_zh(value)
        elif isinstance(node, list):
            for value in node:
                _fill_zh(value)

    _fill_zh(probe)
    return probe


_SOURCE_KEY_SYNONYMS = {
    # Analysis-pass evidence vocabulary that keeps leaking into package
    # sources. Renaming is lossless, so repair it instead of failing the run.
    "label": "title",
    "source_class": "class",
    "evidence_class": "class",
    "source_type": "class",
    "detail": "treatment",
    "name": "title",
}

# A block names its own fields as often as it names the schema's. Each of
# these cost a whole generation attempt on one live Gemini run (Koch, Inc.,
# 2026-09-18: three attempts, a different one of these killing each), so
# they are renamed rather than allowed to fail the memo.
_BLOCK_KEY_SYNONYMS = {
    # The block's type under another name; without it the block reads as an
    # untyped paragraph and fails as "text is required" (22 blocks in one run).
    "kind": "type",
    # The component slug under the analysis passes' word for it.
    "slug": "component",
    # A table's header row.
    "columns": "headers",
    "column_headers": "headers",
}

# A bullets or callout list under a key that echoes the block's own type.
_ITEMS_KEY_SYNONYMS = ("bullets", "points", "list_items", "entries")

_BLOCK_TYPE_SYNONYMS = {
    "bullet": "bullets",
    "bullet_list": "bullets",
    "bulleted_list": "bullets",
    "list": "bullets",
    "para": "paragraph",
    "text": "paragraph",
    "call_out": "callout",
    "box": "callout",
    # Seen from the per-section wave on Gemini: prose under its own name.
    "prose": "paragraph",
    "narrative": "paragraph",
    "body_text": "paragraph",
    "header": "heading",
    "subheading": "heading",
    "subheader": "heading",
    # Compound types the model invents for a titled paragraph, or a table
    # with its commentary in the same block; the prose half of a table is
    # split out into the paragraph that follows it before the main pass.
    "header_and_prose": "paragraph",
    "heading_and_prose": "paragraph",
    "table_and_prose": "table",
    "table_with_prose": "table",
}


def _repair_titleish(value: Any) -> str:
    """First-sentence-ish English text usable as a derived title."""
    text = _content_text(value)
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?;:])\s", text, maxsplit=1)[0].strip()
    words = sentence.split()
    if len(words) > 10:
        sentence = " ".join(words[:10]).rstrip(",;:") + "…"
    return sentence.rstrip(".")


def _repair_localized(node: dict, key: str, repairs: list[str], where: str) -> None:
    """Wrap a plain non-language-neutral string as {"en": ..., "zh": ""}."""
    value = node.get(key)
    if (
        isinstance(value, str)
        and value.strip()
        and not _is_language_neutral_text(value)
    ):
        node[key] = {"en": value, "zh": ""}
        repairs.append(f"{where}: wrapped plain string as bilingual en value")


def _decode_serialized_list(
    block: dict, key: str, repairs: list[str], where: str
) -> None:
    """Decode a list the model serialized as a JSON string inside the block
    — the escaping the section prompt warns against, seen live on a
    table's ``headers`` and ``rows``."""
    value = block.get(key)
    if isinstance(value, str) and value.lstrip().startswith("["):
        try:
            decoded = json.loads(value)
        except ValueError:
            return
        if isinstance(decoded, list):
            block[key] = decoded
            repairs.append(f"{where}.{key}: decoded a list serialized as a string")


def _adopt_items_synonym(block: dict, repairs: list[str], where: str) -> None:
    """Move a bullet list filed under the block's own name into ``items``.

    Live: a bullets block arrived as ``{"type": "bullets", "bullets": [...],
    "items": null}`` and failed as "items must be a non-empty list", which
    ended the run's last attempt. A populated ``items`` always wins.
    """
    current = block.get("items")
    if isinstance(current, list) and current:
        return
    for key in _ITEMS_KEY_SYNONYMS:
        candidate = block.get(key)
        if isinstance(candidate, list) and candidate:
            block["items"] = candidate
            block.pop(key, None)
            repairs.append(f"{where}: moved {key!r} into 'items'")
            return


_SOURCE_CLASS_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")


def _repair_source_class_and_treatment(
    source: dict, repairs: list[str], where: str
) -> None:
    """Fill a source's ``class`` and ``treatment`` from whichever one arrived.

    A source classes itself in exactly one of these two fields and leaves the
    other empty, and both halves are required. One live run (Koch, Inc.,
    2026-09-18) failed twice on this, once each way: every source came back
    with ``class: "company_reported"`` and no treatment, then on the next
    attempt with ``treatment: {"en": "company_reported"}`` and no class.

    A bare slug is a class, never a treatment sentence, so it is promoted and
    the treatment restated as the sentence that field is for. A treatment
    already written as prose is left exactly as the author wrote it.
    """
    class_text = _content_text(source.get("class")).strip()
    treatment = source.get("treatment")
    treatment_text = _content_text(treatment).strip()

    def _label(slug: str) -> str:
        return slug.replace("_", " ").replace("-", " ").strip()

    if not class_text and treatment_text and _SOURCE_CLASS_SLUG_RE.match(
        treatment_text
    ):
        label = _label(treatment_text)
        source["class"] = label
        sentence = f"Weighted as {label}."
        if isinstance(treatment, dict):
            treatment["en"] = sentence
        else:
            source["treatment"] = {"en": sentence, "zh": ""}
        repairs.append(
            f"{where}: read class {label!r} from a treatment holding only "
            "that slug, and restated the treatment"
        )
        return

    if class_text and not treatment_text:
        label = _label(class_text)
        if _SOURCE_CLASS_SLUG_RE.match(class_text):
            source["class"] = label
        source["treatment"] = {"en": f"Weighted as {label}.", "zh": ""}
        repairs.append(
            f"{where}: wrote the treatment its class {label!r} implies"
        )


def _repair_localized_list(items: Any, repairs: list[str], where: str) -> list:
    if not isinstance(items, list):
        return items
    out = []
    for index, item in enumerate(items):
        if (
            isinstance(item, str)
            and item.strip()
            and not _is_language_neutral_text(item)
        ):
            out.append({"en": item, "zh": ""})
            repairs.append(f"{where}[{index}]: wrapped plain string as bilingual en value")
        else:
            out.append(item)
    return out


def repair_package_structure(package: Any) -> tuple[Any, list[str]]:
    """Deterministically fix mechanical package defects before validation.

    Only lossless, unambiguous repairs are applied — a missing callout title
    is derived from the callout's own body, plain strings in bilingual slots
    are wrapped as ``{"en": ..., "zh": ""}``, and analysis-pass source
    vocabulary (``label``/``source_class``/``detail``) is renamed to the
    renderer contract. Anything judgment-shaped is left for the validation
    feedback loop. Returns ``(repaired_copy, repair_descriptions)``; the
    input is never mutated and an empty repair list means the package was
    returned unchanged.
    """
    import copy as _copy

    if not isinstance(package, dict):
        return package, []
    repaired = _copy.deepcopy(package)
    repairs: list[str] = []

    if not str(repaired.get("schema_version") or "").strip():
        repaired["schema_version"] = SCHEMA_VERSION
        repairs.append(f"schema_version: defaulted to {SCHEMA_VERSION}")

    sections = repaired.get("sections")
    for s_index, section in enumerate(sections if isinstance(sections, list) else []):
        if not isinstance(section, dict):
            continue
        where_section = f"sections[{s_index}]"
        _repair_localized(section, "title", repairs, f"{where_section}.title")
        blocks = section.get("blocks")
        # An empty table — no headers, no rows — is a placeholder the model
        # never filled. Validation rejects the whole package over it and a
        # regeneration attempt follows; dropping the block is what a human
        # editor would do. Seen live from the per-section wave on Gemini.
        if isinstance(blocks, list):
            kept = []
            for b_index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    kept.append(block)
                    continue
                where = f"{where_section}.blocks[{b_index}]"
                raw_type = str(block.get("type") or "").strip().lower()
                if _BLOCK_TYPE_SYNONYMS.get(raw_type, raw_type) == "table":
                    for key in ("headers", "rows"):
                        _decode_serialized_list(block, key, repairs, where)
                    if not (block.get("headers") or block.get("rows")):
                        repairs.append(f"{where}: dropped empty table")
                        continue
                    # "table_and_prose": the commentary becomes the
                    # paragraph after the table, which is what it was.
                    prose = block.pop("content", None)
                    if isinstance(prose, (str, dict)) and _content_text(prose):
                        kept.append(block)
                        kept.append({"type": "paragraph", "text": prose})
                        repairs.append(
                            f"{where}: split its prose into a paragraph "
                            "after the table"
                        )
                        continue
                    if prose is not None:
                        block["content"] = prose
                kept.append(block)
            if len(kept) != len(blocks):
                blocks[:] = kept
        for b_index, block in enumerate(blocks if isinstance(blocks, list) else []):
            if not isinstance(block, dict):
                continue
            where = f"{where_section}.blocks[{b_index}]"
            for old_key, new_key in _BLOCK_KEY_SYNONYMS.items():
                if old_key in block and not block.get(new_key):
                    block[new_key] = block.pop(old_key)
                    repairs.append(
                        f"{where}: renamed {old_key!r} to {new_key!r}"
                    )
            # Prose under `content`, with the block's `text` carrying what
            # is really its title (nine blocks of one live valuation
            # section). The prose is the text; the short line above it is
            # the title. A list under `content` is never prose.
            content = block.get("content")
            if isinstance(content, (str, dict)) and _content_text(content):
                if not _content_text(block.get("text")):
                    block["text"] = block.pop("content")
                    repairs.append(f"{where}: moved 'content' into 'text'")
                elif not _content_text(block.get("title")):
                    block["title"] = block.pop("text")
                    block["text"] = block.pop("content")
                    repairs.append(
                        f"{where}: moved 'content' into 'text' and the "
                        "line it carried as text into 'title'"
                    )
            raw_kind = str(block.get("type") or "paragraph").strip().lower()
            kind = _BLOCK_TYPE_SYNONYMS.get(raw_kind, raw_kind)
            if not str(block.get("type") or "").strip():
                # The validator reads an untyped block as a paragraph; say so
                # in the package rather than leave every reader to default it.
                block["type"] = kind
                repairs.append(f"{where}.type: untyped block read as {kind!r}")
            elif kind != str(block.get("type")):
                block["type"] = kind
                repairs.append(f"{where}.type: normalized {raw_kind!r} to {kind!r}")
            if kind == "paragraph" and not _content_text(
                block.get("text") or block.get("body")
            ):
                # Some generations put paragraph prose under `title`.
                if _content_text(block.get("title")):
                    block["text"] = block.pop("title")
                    repairs.append(f"{where}: moved paragraph title into text")
            if kind == "heading":
                _repair_localized(block, "text", repairs, f"{where}.text")
                _repair_localized(block, "title", repairs, f"{where}.title")
            elif kind == "paragraph":
                _repair_localized(block, "text", repairs, f"{where}.text")
                _repair_localized(block, "body", repairs, f"{where}.body")
                _repair_localized(block, "title", repairs, f"{where}.title")
            elif kind == "bullets":
                _adopt_items_synonym(block, repairs, where)
                block["items"] = _repair_localized_list(
                    block.get("items"), repairs, f"{where}.items"
                )
            elif kind == "callout":
                _repair_localized(block, "title", repairs, f"{where}.title")
                _repair_localized(block, "label", repairs, f"{where}.label")
                _repair_localized(block, "body", repairs, f"{where}.body")
                # The validator reads a callout's prose as `body or text`, so
                # prose left as a plain string under `text` fails as ".body
                # must be bilingual". That single unrepaired shape was what
                # sent a 5,000-word first draft into the regeneration retry.
                _repair_localized(block, "text", repairs, f"{where}.text")
                _adopt_items_synonym(block, repairs, where)
                block["items"] = _repair_localized_list(
                    block.get("items"), repairs, f"{where}.items"
                )
                if not _content_text(block.get("title") or block.get("label")):
                    derived = _repair_titleish(
                        block.get("body") or block.get("text")
                    ) or _repair_titleish(
                        next(iter(block.get("items") or []), None)
                    ) or "Key Consideration"
                    block["title"] = {"en": derived, "zh": ""}
                    repairs.append(
                        f"{where}.title: derived callout title from its content"
                    )
            elif kind == "chart":
                _repair_localized(block, "title", repairs, f"{where}.title")
                _repair_localized(block, "caption", repairs, f"{where}.caption")
                _repair_localized(block, "reading", repairs, f"{where}.reading")
            elif kind == "table":
                _repair_localized(block, "title", repairs, f"{where}.title")
                block["headers"] = _repair_localized_list(
                    block.get("headers"), repairs, f"{where}.headers"
                )
                rows = block.get("rows")
                # An empty row is the same placeholder as an empty table,
                # one level down ("rows[0] must contain cells" cost a live
                # attempt). Drop it rather than fail the package.
                if isinstance(rows, list):
                    kept_rows = [
                        row for row in rows
                        if (row.get("cells") if isinstance(row, dict) else row)
                    ]
                    if len(kept_rows) != len(rows):
                        repairs.append(
                            f"{where}.rows: dropped {len(rows) - len(kept_rows)} empty row(s)"
                        )
                        rows[:] = kept_rows
                for r_index, row in enumerate(rows if isinstance(rows, list) else []):
                    cells = row.get("cells") if isinstance(row, dict) else row
                    # A cell written as {"text": <localized>} carries its
                    # value one level down; the validator wants the localized
                    # object itself and reports "cells[0].en is required".
                    if isinstance(cells, list):
                        for c_index, cell in enumerate(cells):
                            if (
                                isinstance(cell, dict)
                                and "en" not in cell
                                and "zh" not in cell
                                and isinstance(cell.get("text"), (dict, str))
                                and len(cell) == 1
                            ):
                                cells[c_index] = cell["text"]
                                repairs.append(
                                    f"{where}.rows[{r_index}].cells[{c_index}]: "
                                    "unwrapped cell text"
                                )
                    fixed = _repair_localized_list(
                        cells, repairs, f"{where}.rows[{r_index}].cells"
                    )
                    if isinstance(row, dict):
                        row["cells"] = fixed
                    elif isinstance(rows, list):
                        rows[r_index] = fixed

    sources = repaired.get("sources")
    for index, source in enumerate(sources if isinstance(sources, list) else []):
        if not isinstance(source, dict):
            continue
        where = f"sources[{index}]"
        for old_key, new_key in _SOURCE_KEY_SYNONYMS.items():
            if old_key in source and not str(source.get(new_key) or "").strip():
                source[new_key] = source.pop(old_key)
                repairs.append(f"{where}: renamed {old_key!r} to {new_key!r}")
        _repair_source_class_and_treatment(source, repairs, where)
        if not str(source.get("id") or "").strip():
            source["id"] = f"S{index + 1}"
            repairs.append(f"{where}.id: assigned S{index + 1}")
        # `title` may legally stay a plain string; only `treatment` is
        # validated as a bilingual value.
        _repair_localized(source, "treatment", repairs, f"{where}.treatment")

    return repaired, repairs


def english_package_validation_errors(package: Any) -> list[str]:
    """Validate an English-only package (phase 3 output, ``zh`` still blank).

    Runs the full renderer validation against a copy whose empty ``zh``
    strings are placeholder-filled, so structural defects (wrong source
    vocabulary, missing sections, shallow content) surface at generation
    time — where the synthesis pass can retry with the errors fed back —
    instead of 20 minutes later at render time.
    """
    if not isinstance(package, dict):
        return ["memo package must be a JSON object"]
    filled = fill_blank_zh_placeholders(package)
    errors = _package_validation_errors(filled)
    errors.extend(_risk_card_format_errors(filled))
    errors.extend(_subsection_heading_errors(filled))
    errors.extend(_exec_summary_format_errors(filled))
    errors.extend(_chart_reading_errors(filled))
    errors.extend(_word_budget_errors(filled))
    return errors


def _section_en_word_count(section: dict) -> int:
    """All English words in a section's blocks — prose, bullets, table
    cells, chart captions alike. What the reader has to get through."""
    words = 0

    def walk(value: Any) -> None:
        nonlocal words
        if isinstance(value, dict):
            if "en" in value:
                words += len(str(value.get("en") or "").split())
            else:
                for item in value.values():
                    walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(section.get("blocks") or [])
    return words


def _word_budget_errors(package: dict) -> list[str]:
    """Generation-time gate for profiles that declare hard word ceilings
    (compact only). Prose budgets alone failed twice live (5.2K and
    5.5K words against a 2.6-3.2K target); the ceiling is deterministic
    so the retry loop can enforce it."""
    sections = package.get("sections")
    if not isinstance(sections, list):
        return []
    structure = _structure_for(package)
    errors: list[str] = []
    by_id = {
        str(s.get("id") or ""): s for s in sections if isinstance(s, dict)
    }
    for sdef in structure.sections:
        if not sdef.budget_words:
            continue
        section = by_id.get(sdef.id)
        if section is None:
            continue
        count = _section_en_word_count(section)
        # 5% grace: a marginal overshoot (618 vs 600 live) is not worth
        # a full section re-emit; the gate is for real blowouts (1435
        # vs 750 in the same run).
        if count > sdef.budget_words * 1.05:
            errors.append(
                f"section {sdef.id} runs {count} English words against its "
                f"{sdef.budget_words}-word ceiling — this is the COMPACT "
                "memo: cut commentary (one bullet per point, one clause per "
                "judgment) until it fits; never cut pinned facts, "
                "subsection headings, or the scorecard sentences"
            )
    return errors


def _chart_reading_errors(package: dict) -> list[str]:
    """Generation-time gate: every structure-v2 chart carries a `reading`
    note ("Higher is better", "Bars below 1.0x lose money") so the
    reader knows how to read it. Render-time validation stays lenient —
    packages from runs that predate the field still re-render."""
    structure = _structure_for(package)
    if not structure.scorecard_weights():
        return []
    errors: list[str] = []
    sections = package.get("sections")
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        for index, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict) or block.get("type") != "chart":
                continue
            if not _content_text(block.get("reading")):
                errors.append(
                    f"section {section_id} blocks[{index}]: chart must carry "
                    "a `reading` note (bilingual) telling the reader how to "
                    "read it — 'Higher is better', 'Bars below 1.0x lose "
                    "money'"
                )
    return errors


_SUBSECTION_NUMBER_RE = re.compile(r"^\s*(\d+)\s*[\.、]\s*")


def _subsection_heading_errors(package: dict) -> list[str]:
    """Generation-time gate for the fixed numbered subsections a
    structure-v2 profile declares per section.

    Each declared subsection must appear, in order, as a heading block
    whose text starts with its position number ("2. Market size").
    Extra headings between declared ones (risk cards, sub-headings the
    contract asks for) are allowed. Kept out of render-time validation
    so packages from runs that predate subsections still re-render.
    """
    sections = package.get("sections")
    if not isinstance(sections, list):
        return []
    structure = _structure_for(package)
    errors: list[str] = []
    by_id = {
        str(s.get("id") or ""): s for s in sections if isinstance(s, dict)
    }
    for sdef in structure.sections:
        if not sdef.subsections:
            continue
        section = by_id.get(sdef.id)
        if section is None:
            continue  # the missing-section error is raised elsewhere
        headings = [
            _content_text(b.get("text") or b.get("title"))
            for b in section.get("blocks") or []
            if isinstance(b, dict)
            and str(b.get("type") or "paragraph") == "heading"
        ]
        cursor = 0
        for number, sub in enumerate(sdef.subsections, start=1):
            expected = f"{number}. {sub.en}"
            found = False
            while cursor < len(headings):
                heading = headings[cursor]
                cursor += 1
                match = _SUBSECTION_NUMBER_RE.match(heading)
                if (
                    match
                    and int(match.group(1)) == number
                    and sub.en.lower()
                    in _SUBSECTION_NUMBER_RE.sub("", heading).strip().lower()
                ):
                    found = True
                    break
            if not found:
                errors.append(
                    f"section {sdef.id} must contain its fixed numbered "
                    f"subsection heading {expected!r} (a `heading` block, "
                    "level 2, in the declared order)"
                )
    return errors


def _exec_summary_format_errors(package: dict) -> list[str]:
    """Generation-time gate: a structure-v2 executive summary carries no
    tables — its job is the point, not the data. The snapshot tables
    live in the overview section the profile routes them to."""
    structure = _structure_for(package)
    if not structure.scorecard_weights():
        return []
    try:
        exec_id = structure.section_for_role("exec").id
    except KeyError:
        return []
    sections = package.get("sections")
    if not isinstance(sections, list):
        return []
    section = next(
        (
            s
            for s in sections
            if isinstance(s, dict) and str(s.get("id") or "") == exec_id
        ),
        None,
    )
    if section is None:
        return []
    routing = structure.component_section()
    homes = ", ".join(
        f"{slug} belongs in {routing[slug]}"
        for slug in ("deal_terms", "key_metrics_snapshot")
        if routing.get(slug)
    )
    errors: list[str] = []
    for index, block in enumerate(section.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "") == "table":
            errors.append(
                f"section {exec_id} blocks[{index}]: the executive summary "
                "must contain NO table blocks — state its numbers in "
                "interpreted prose"
                + (f" ({homes})" if homes else "")
            )
        if str(block.get("type") or "") == "bullets":
            for item_index, item in enumerate(block.get("items") or []):
                lead = _bullet_lead_sentence(_content_text(item))
                if (
                    lead
                    and len(lead.split()) < 4
                    # Digits or an inner period mean a figure or an
                    # abbreviation ("U.S."), not a bare topic label.
                    and "." not in lead
                    and not any(ch.isdigit() for ch in lead)
                ):
                    errors.append(
                        f"section {exec_id} blocks[{index}]"
                        f".items[{item_index}]: bullet opens with the topic "
                        f"label {lead!r} — open with a short claim that "
                        "carries the direction ('The price sits below every "
                        "disclosed peer — 13.8x vs a 21x median.'), never a "
                        "naked label"
                    )
    return errors


_BULLET_LEAD_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|(?<=[。])")


def _bullet_lead_sentence(text: str) -> str:
    """The words a bullet leads with — up to the first sentence break.
    A bare topic label ("Price. 13.8x vs 21x.") shows up here as a one-
    to three-word fragment; a colon lead ("Market size: the pool is
    $125B...") keeps its judgment in the same sentence and passes."""
    stripped = text.strip().lstrip("*_•- ").strip()
    if not stripped:
        return ""
    parts = _BULLET_LEAD_SPLIT_RE.split(stripped, maxsplit=1)
    return parts[0].strip().rstrip(".!?。*_").strip()


def _risk_card_format_errors(package: dict) -> list[str]:
    """Generation-time gate for the per-risk card format in investment_risk.

    Kept out of ``_package_validation_errors`` on purpose: render-time
    validation must keep accepting packages from runs that predate the card
    format, while the synthesis retry loop gets precise errors to fix.
    """
    sections = package.get("sections")
    if not isinstance(sections, list):
        return []
    structure = _structure_for(package)
    if structure.risk_format != "cards":
        # Compact profiles present the pinned risks as verdict-lead
        # bullets; the pin-echo gate still enforces the risk list.
        return []
    try:
        risk_id = structure.section_for_role("risk").id
    except KeyError:
        return []
    row_labels = _risk_card_row_labels(structure)
    row_index = {prefix: i for i, (prefix, _label) in enumerate(row_labels)}
    row_list_text = " / ".join(label for _p, label in row_labels)
    section = next(
        (
            s
            for s in sections
            if isinstance(s, dict) and str(s.get("id") or "") == risk_id
        ),
        None,
    )
    if section is None:
        # The missing-section error is already raised by shared validation.
        return []
    errors: list[str] = []
    blocks = [b for b in section.get("blocks") or [] if isinstance(b, dict)]
    cards: list[tuple[str, dict, str]] = []
    for index, block in enumerate(blocks):
        if str(block.get("type") or "paragraph") != "heading":
            continue
        heading_text = _content_text(block.get("text") or block.get("title"))
        if not _RISK_CARD_HEADING_RE.match(heading_text):
            continue
        location = f"{risk_id} blocks[{index}]"
        nxt = blocks[index + 1] if index + 1 < len(blocks) else None
        if not isinstance(nxt, dict) or str(nxt.get("type") or "") != "table":
            errors.append(
                f"{location}: risk heading {heading_text!r} must be "
                "immediately followed by its key_value risk card table"
            )
            continue
        cards.append((heading_text, nxt, f"{risk_id} blocks[{index + 1}]"))
    row_count_word = _spelled_row_count(len(row_labels))
    if not 4 <= len(cards) <= 6:
        errors.append(
            _RISK_CARD_FORMAT_HINT.format(
                section_id=risk_id,
                row_count=row_count_word,
                row_list=", ".join(
                    f"'{label}'" for _p, label in row_labels
                ),
            )
        )
        errors.append(
            f"{risk_id}: risk register must contain 4-6 material "
            f"risk cards, found {len(cards)}"
        )
        return errors

    ratings: list[tuple[str, int]] = []
    seen_headings: set[str] = set()
    for heading_text, table, location in cards:
        summary = heading_text.split(":", 1)[-1].strip().lower()
        if summary in _RISK_GENERIC_HEADINGS:
            errors.append(
                f"{location}: risk heading {heading_text!r} is only a "
                "generic category; name the concrete failure mode"
            )
        normalized_summary = re.sub(r"[^a-z0-9]+", " ", summary).strip()
        if normalized_summary in seen_headings:
            errors.append(
                f"{location}: risk heading {heading_text!r} duplicates "
                "another risk card"
            )
        seen_headings.add(normalized_summary)
        if str(table.get("layout") or "").strip().lower() != "key_value":
            errors.append(
                f"{location}: risk card table must declare \"layout\": \"key_value\""
            )
        if [header for header in table.get("headers") or [] if _content_text(header)]:
            errors.append(f"{location}: risk card table must have empty headers")
        row_texts: list[tuple[str, str] | None] = []
        for row in table.get("rows") or []:
            cells = row.get("cells") if isinstance(row, dict) else row
            if isinstance(cells, (list, tuple)) and len(cells) == 2:
                row_texts.append((_content_text(cells[0]), _content_text(cells[1])))
            else:
                row_texts.append(None)
        if len(row_texts) != len(row_labels) or any(
            row is None for row in row_texts
        ):
            errors.append(
                f"{location}: risk card table needs exactly "
                f"{row_count_word} two-cell rows "
                f"({row_list_text})"
            )
            continue
        for (prefix, label), row in zip(row_labels, row_texts):
            label_text, value_text = row  # type: ignore[misc]
            if not label_text.lower().startswith(prefix):
                errors.append(
                    f"{location}: row label {label_text!r} must be {label!r}"
                )
            elif not value_text.strip():
                errors.append(f"{location}: row {label!r} must not be empty")
        why_row = row_texts[row_index["why it matters"]]
        if why_row and why_row[0].lower().startswith("why it matters"):
            why_text = why_row[1].strip()
            if not _has_meaningful_text(why_text, min_chars=35, min_words=6):
                errors.append(
                    f"{location}: Why it matters must name the fact, failure "
                    "mode, and economic consequence"
                )
            # "pric" covers price/pricing; discount, fee, billing, profit,
            # burn and churn are the vocabulary of services and SaaS risks —
            # "15-25% productivity discounts on time-and-materials
            # contracts" is an economic consequence, and a live run failed
            # three retries and a repair pass on exactly that sentence.
            if not re.search(
                r"\b(?:revenue|margin|cash|valuation|pric|return|dilut|"
                r"capital|exit|control|loss|multiple|growth|financ|cost|"
                r"conversion|discount|fee|billing|profit|burn|churn)\w*\b",
                why_text,
                re.IGNORECASE,
            ):
                # The message is fed back to the retry and to the repair
                # pass, so it has to say what would satisfy it: a model that
                # believes it stated a consequence cannot act on a bare
                # "must state one".
                errors.append(
                    f"{location}: Why it matters must state an economic "
                    "consequence — name the effect with a financial term "
                    "(revenue, margin, cost, cash, pricing, valuation, "
                    "dilution or exit value), not only the operational cause"
                )
        watch_row = row_texts[row_index["what we watch"]]
        if watch_row and watch_row[0].lower().startswith("what we watch"):
            watch_text = watch_row[1].strip()
            if not _has_meaningful_text(watch_text, min_chars=18, min_words=3):
                errors.append(
                    f"{location}: What we watch must name an observable signal"
                )
            if _RISK_GENERIC_WATCH_RE.match(watch_text):
                errors.append(
                    f"{location}: What we watch must be a signal, not a "
                    "confirmation or diligence command"
                )
        likelihood_row = row_texts[row_index["likelihood"]]
        if (
            likelihood_row
            and likelihood_row[0].lower().startswith("likelihood")
            and not _RISK_LIKELIHOOD_VALUE_RE.match(likelihood_row[1])
        ):
            errors.append(
                f"{location}: Likelihood must be written as "
                "'High|Medium|Low: short reason'"
            )
        rating_row = row_texts[row_index["risk rating"]]
        if rating_row and rating_row[0].lower().startswith("risk rating"):
            match = _RISK_RATING_VALUE_RE.match(rating_row[1])
            if match:
                ratings.append((heading_text, int(match.group(1))))
            else:
                errors.append(
                    f"{location}: Risk Rating must be written as "
                    "'N/10: short reason' with N from 1-10"
                )
    for (prev_title, prev_rating), (title, rating) in zip(ratings, ratings[1:]):
        if rating > prev_rating:
            errors.append(
                f"{risk_id}: risk cards must be ordered by Risk Rating, "
                f"highest first — {title!r} ({rating}/10) is rated above "
                f"{prev_title!r} ({prev_rating}/10) but listed after it"
            )
            break
    return errors


def _package_validation_errors(package: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(package, dict):
        return ["memo package must be a JSON object"]
    structure = _structure_for(package)
    section_titles = structure.section_titles()
    floors = structure.content_floors()
    try:
        version = int(package.get("schema_version") or SCHEMA_VERSION)
    except (TypeError, ValueError):
        errors.append(
            f"unsupported schema_version {package.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
        version = SCHEMA_VERSION
    if version != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version {version}; expected {SCHEMA_VERSION}"
        )
    if not isinstance(package.get("company"), dict):
        errors.append("company must be an object")
    elif not str(package["company"].get("name") or "").strip():
        errors.append("company.name is required")
    sections = package.get("sections")
    if not isinstance(sections, list):
        errors.append("sections must be a list")
        sections = []
    sources = package.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
    errors.extend(_calculation_errors(package))
    errors.extend(_citation_errors(package))

    by_id: dict[str, dict] = {}
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{location} must be an object")
            continue
        section_id = str(section.get("id") or "").strip()
        if section_id:
            by_id[section_id] = section
            if section_id not in section_titles and not _loc(
                section.get("title"), "en"
            ):
                errors.append(
                    f"{location} section id {section_id!r} must provide a "
                    "bilingual title or use a renderer-supported section id"
                )
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append(f"{location} blocks must be a non-empty list")
            blocks = []
        _validate_localized_value(
            section.get("title"),
            f"{location}.title",
            errors,
            required=False,
        )
        for block_index, block in enumerate(blocks):
            _validate_block(block, f"{location}.blocks[{block_index}]", errors)

    for section_id in structure.section_ids:
        if section_id not in by_id:
            errors.append(f"missing required section {section_id}")
        else:
            _validate_section_content_floor(
                section_id, by_id[section_id], errors, floors.get(section_id)
            )
    _validate_required_memo_components(package, errors, structure)

    if isinstance(sources, list):
        for index, source in enumerate(sources):
            _validate_source(source, f"sources[{index}]", errors)
    return errors


def _validate_required_memo_components(
    package: dict,
    errors: list[str],
    structure: memo_structure.MemoStructure | None = None,
) -> None:
    structure = structure or _structure_for(package)
    coverage = _memo_component_coverage(package, structure)
    for component in structure.components:
        component_id = str(component["id"])
        if not coverage.get(component_id):
            errors.append(
                f"missing required memo component {component_id}: "
                f"{component['label']}"
            )


def _memo_component_coverage(
    package: dict,
    structure: memo_structure.MemoStructure | None = None,
) -> dict[str, bool]:
    structure = structure or _structure_for(package)
    components = structure.components
    section_titles = structure.section_titles()
    coverage = {str(component["id"]): False for component in components}
    if isinstance(package.get("sources"), list) and package.get("sources"):
        coverage["source_index"] = True
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_title = _content_text(section.get("title")) or _section_title(
            section, "en", section_titles
        )
        previous_heading = ""
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for component_id in _declared_component_ids(block):
                if component_id in coverage:
                    coverage[component_id] = True
            signature = _block_signature_text(block, section_title, previous_heading)
            kind = str(block.get("type") or "paragraph")
            for component in components:
                component_id = str(component["id"])
                if coverage.get(component_id) or kind not in component["block_types"]:
                    continue
                if any(
                    re.search(pattern, signature, flags=re.IGNORECASE)
                    for pattern in component["patterns"]
                ):
                    coverage[component_id] = True
            if kind == "heading":
                previous_heading = _content_text(block.get("text") or block.get("title"))
    return coverage


def _declared_component_ids(block: dict) -> list[str]:
    value = block.get("component") or block.get("components")
    if isinstance(value, str):
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _block_signature_text(block: dict, section_title: str, previous_heading: str) -> str:
    values = [section_title, previous_heading]
    for key in ("component", "title", "label", "text", "body", "caption"):
        value = block.get(key)
        if isinstance(value, list):
            values.extend(_content_text(item) for item in value)
        else:
            values.append(_content_text(value))
    if block.get("type") == "table":
        values.extend(_content_text(header) for header in block.get("headers") or [])
        for row in block.get("rows") or []:
            cells = row.get("cells") if isinstance(row, dict) else row
            if isinstance(cells, (list, tuple)):
                values.extend(_content_text(cell) for cell in cells)
    if block.get("type") in {"bullets", "callout"}:
        values.extend(_content_text(item) for item in block.get("items") or [])
    return " ".join(value for value in values if value)


def _validate_section_content_floor(
    section_id: str,
    section: dict,
    errors: list[str],
    floor: memo_structure.ContentFloor | None,
) -> None:
    score = _section_content_score(section)
    if score["real_blocks"] < 1:
        errors.append(f"section {section_id} must contain substantive memo content")
        return
    if floor is None:
        return
    if floor.min_real_blocks > 1 and score["real_blocks"] < floor.min_real_blocks:
        errors.append(
            f"section {section_id} must contain at least "
            f"{'two' if floor.min_real_blocks == 2 else floor.min_real_blocks} "
            "substantive content blocks"
        )
    if floor.bullets_or_prose:
        has_bullets = score["bullet_items"] >= 2
        has_table_or_callout_with_prose = (
            score["paragraphs"] >= 1
            and (score["tables"] + score["callouts"]) >= 1
        )
        if not has_bullets and not has_table_or_callout_with_prose:
            errors.append(
                f"section {section_id} must contain at least two substantive "
                "bullets or explanatory prose plus a substantive table/callout"
            )
    if floor.require_valuation_refs and score["valuation_refs"] < 1:
        errors.append(
            f"section {section_id} must reference scenario "
            "ranges, valuation, revenue, margins, or what moves the number"
        )


def _section_content_score(section: dict) -> dict[str, int]:
    score = {
        "real_blocks": 0,
        "paragraphs": 0,
        "bullet_items": 0,
        "tables": 0,
        "callouts": 0,
        "valuation_refs": 0,
    }
    for block in section.get("blocks") or []:
        block_score = _block_content_score(block)
        for key, value in block_score.items():
            score[key] += value
    return score


def _block_content_score(block: Any) -> dict[str, int]:
    score = {
        "real_blocks": 0,
        "paragraphs": 0,
        "bullet_items": 0,
        "tables": 0,
        "callouts": 0,
        "valuation_refs": 0,
    }
    if not isinstance(block, dict):
        return score

    kind = str(block.get("type") or "paragraph")
    if kind == "paragraph":
        text = block.get("text") or block.get("body")
        if _has_meaningful_text(text, min_chars=35, min_words=6):
            score["real_blocks"] = 1
            score["paragraphs"] = 1
            score["valuation_refs"] = int(_has_valuation_reference(text))
    elif kind == "bullets":
        item_count = sum(
            1
            for item in block.get("items") or []
            if _has_meaningful_text(item, min_chars=24, min_words=4)
        )
        if item_count:
            score["real_blocks"] = 1
            score["bullet_items"] = item_count
    elif kind == "callout":
        body = block.get("body") or block.get("text")
        items = block.get("items") or []
        item_count = sum(
            1
            for item in items
            if _has_meaningful_text(item, min_chars=24, min_words=4)
        )
        if _has_meaningful_text(body, min_chars=35, min_words=6) or item_count:
            score["real_blocks"] = 1
            score["callouts"] = 1
    elif kind == "table":
        if _table_has_real_body_row(block):
            score["real_blocks"] = 1
            score["tables"] = 1
            score["valuation_refs"] = int(_has_valuation_reference(_table_body_text(block)))
    elif kind == "chart":
        if any(
            isinstance(series, dict) and series.get("points")
            for series in block.get("series") or []
        ):
            score["real_blocks"] = 1
            score["tables"] = 1
            score["valuation_refs"] = int(
                _has_valuation_reference(
                    " ".join(
                        _content_text(block.get(key))
                        for key in ("title", "caption")
                    )
                )
            )
    return score


def _table_has_real_body_row(block: dict) -> bool:
    for row in block.get("rows") or []:
        cells = row.get("cells") if isinstance(row, dict) else row
        if not isinstance(cells, (list, tuple)):
            continue
        clean_cells = [_content_text(cell) for cell in cells]
        non_empty_cells = [cell for cell in clean_cells if cell]
        if any(
            _has_meaningful_text(cell, min_chars=12, min_words=2)
            for cell in non_empty_cells
        ):
            return True
        if len(non_empty_cells) >= 2:
            return True
    return False


def _table_body_text(block: dict) -> str:
    values: list[str] = []
    for row in block.get("rows") or []:
        cells = row.get("cells") if isinstance(row, dict) else row
        if isinstance(cells, (list, tuple)):
            values.extend(_content_text(cell) for cell in cells)
    return " ".join(value for value in values if value)


def _has_meaningful_text(
    value: Any,
    *,
    min_chars: int,
    min_words: int,
) -> bool:
    text = _content_text(value)
    if not text:
        return False
    lowered = text.lower().strip(" .")
    if any(pattern.fullmatch(lowered) for pattern in GENERIC_CONTENT_PATTERNS):
        return False
    words = re.findall(r"[\w$%][\w$%'-]*", text, flags=re.UNICODE)
    return len(text) >= min_chars or len(words) >= min_words


def _has_valuation_reference(value: Any) -> bool:
    text = _content_text(value).lower()
    return any(term in text for term in VALUATION_CONTENT_TERMS)


def _content_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _loc(value, "en")).strip()


def _validate_block(block: Any, location: str, errors: list[str]) -> None:
    if not isinstance(block, dict):
        errors.append(f"{location} must be an object")
        return
    kind = str(block.get("type") or "paragraph")
    if kind not in SUPPORTED_BLOCK_TYPES:
        errors.append(f"{location}.type {kind!r} is unsupported")
        return
    if kind == "heading":
        _validate_localized_value(
            block.get("text") or block.get("title"),
            f"{location}.text",
            errors,
        )
    elif kind == "paragraph":
        _validate_localized_value(
            block.get("text") or block.get("body"),
            f"{location}.text",
            errors,
        )
    elif kind == "bullets":
        items = block.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{location}.items must be a non-empty list")
            return
        for index, item in enumerate(items):
            _validate_localized_value(item, f"{location}.items[{index}]", errors)
    elif kind == "callout":
        _validate_localized_value(
            block.get("title") or block.get("label"),
            f"{location}.title",
            errors,
        )
        _validate_localized_value(
            block.get("body") or block.get("text"),
            f"{location}.body",
            errors,
            required=False,
        )
        items = block.get("items") or []
        if not isinstance(items, list):
            errors.append(f"{location}.items must be a list")
            return
        for index, item in enumerate(items):
            _validate_localized_value(item, f"{location}.items[{index}]", errors)
    elif kind == "chart":
        _validate_chart_block(block, location, errors)
    elif kind == "table":
        _validate_localized_value(
            block.get("title"),
            f"{location}.title",
            errors,
            required=False,
        )
        headers = block.get("headers") or []
        rows = block.get("rows") or []
        if not headers and not rows:
            errors.append(f"{location} table must include headers or rows")
        for index, header in enumerate(headers):
            _validate_localized_value(header, f"{location}.headers[{index}]", errors)
        for row_index, row in enumerate(rows):
            cells = row.get("cells") if isinstance(row, dict) else row
            if not isinstance(cells, (list, tuple)) or not cells:
                errors.append(f"{location}.rows[{row_index}] must contain cells")
                continue
            for cell_index, cell in enumerate(cells):
                _validate_localized_value(
                    cell,
                    f"{location}.rows[{row_index}].cells[{cell_index}]",
                    errors,
                )


def _validate_chart_block(block: dict, location: str, errors: list[str]) -> None:
    """Validate a ``chart`` block (structure-v2 chart slots).

    Text INSIDE the image (series labels, x categories) is plain
    English/neutral strings — one PNG serves both locales. The text
    AROUND the image (title, caption, unit) is bilingual like any other
    block text.
    """
    chart_type = str(block.get("chart_type") or "").strip().lower()
    if chart_type not in SUPPORTED_CHART_TYPES:
        errors.append(
            f"{location}.chart_type must be one of "
            f"{sorted(SUPPORTED_CHART_TYPES)}"
        )
        return
    _validate_localized_value(block.get("title"), f"{location}.title", errors)
    _validate_localized_value(
        block.get("caption"), f"{location}.caption", errors, required=False
    )
    _validate_localized_value(
        block.get("reading"), f"{location}.reading", errors, required=False
    )
    _validate_localized_value(
        block.get("unit"), f"{location}.unit", errors, required=False,
        allow_plain=True,
    )
    series = block.get("series")
    if not isinstance(series, list) or not 1 <= len(series) <= 4:
        errors.append(f"{location}.series must be a list of 1-4 series")
        return
    if chart_type in _SINGLE_SERIES_CHART_TYPES and len(series) != 1:
        errors.append(
            f"{location}: chart_type {chart_type!r} takes exactly one series "
            "— use 'grouped_bar' for several"
        )
    x_shapes: list[tuple[str, ...]] = []
    total_points = 0
    for s_index, one in enumerate(series):
        where = f"{location}.series[{s_index}]"
        if not isinstance(one, dict):
            errors.append(f"{where} must be an object")
            continue
        if not str(one.get("label") or "").strip():
            errors.append(f"{where}.label must be a non-empty plain string")
        points = one.get("points")
        if not isinstance(points, list) or not points:
            errors.append(f"{where}.points must be a non-empty list")
            continue
        xs: list[str] = []
        for p_index, point in enumerate(points):
            spot = f"{where}.points[{p_index}]"
            if not isinstance(point, dict):
                errors.append(f"{spot} must be an object with x and y")
                continue
            x = point.get("x")
            if not str(x if x is not None else "").strip():
                errors.append(f"{spot}.x must be a non-empty label")
            y = point.get("y")
            if isinstance(y, bool) or not isinstance(y, (int, float)):
                errors.append(f"{spot}.y must be a plain number")
            xs.append(str(x))
            total_points += 1
        x_shapes.append(tuple(xs))
    if len({shape for shape in x_shapes}) > 1:
        errors.append(
            f"{location}: every series must share the same x categories in "
            "the same order"
        )
    if total_points < 2 and not errors:
        errors.append(
            f"{location}: a chart needs at least two data points — use "
            "prose for a single number"
        )
    source_ids = block.get("source_ids")
    if source_ids is not None and (
        not isinstance(source_ids, list)
        or any(not str(item or "").strip() for item in source_ids)
    ):
        errors.append(f"{location}.source_ids must be a list of source ids")


_CALC_ID_RE = re.compile(r"^C\d+$")


def _calculation_errors(package: dict) -> list[str]:
    """`calculations` is optional; when present it is a list of notes with
    an id "C<n>", a formula and a result (label/meaning may be localized
    or plain), and ids are unique."""
    calculations = package.get("calculations")
    if calculations is None:
        return []
    if not isinstance(calculations, list):
        return ["calculations must be a list when present"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, calc in enumerate(calculations):
        location = f"calculations[{index}]"
        if not isinstance(calc, dict):
            errors.append(f"{location} must be an object")
            continue
        calc_id = str(calc.get("id") or "").strip()
        if not _CALC_ID_RE.match(calc_id):
            errors.append(f"{location}.id must look like C1, C2, ...")
        elif calc_id in seen:
            errors.append(f"{location}.id {calc_id} is duplicated")
        seen.add(calc_id)
        for key in ("formula", "result"):
            if not str(calc.get(key) or "").strip():
                errors.append(f"{location}.{key} is required")
        inputs = calc.get("inputs")
        if inputs is not None and not isinstance(inputs, list):
            errors.append(f"{location}.inputs must be a list")
    return errors


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _citation_errors(package: dict) -> list[str]:
    """Every inline `[S#]` / `[C#]` must name an existing source or
    calculation note — a dangling link is a fabricated citation."""
    known: set[str] = set()
    for source in package.get("sources") or []:
        if isinstance(source, dict):
            known.add(str(source.get("id") or "").strip())
    for calc in package.get("calculations") or []:
        if isinstance(calc, dict):
            known.add(str(calc.get("id") or "").strip())
    errors: list[str] = []
    reported: set[str] = set()
    for index, section in enumerate(package.get("sections") or []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or f"sections[{index}]")
        for text in _iter_strings(section.get("blocks")):
            for citation_id in citation_ids(text):
                if citation_id in known or citation_id in reported:
                    continue
                reported.add(citation_id)
                errors.append(
                    f"{section_id}: unknown_citation [{citation_id}] — cite "
                    "only ids that exist in the package sources or the "
                    "pinned calculation notes"
                )
    return errors


def _validate_source(source: Any, location: str, errors: list[str]) -> None:
    if not isinstance(source, dict):
        errors.append(f"{location} must be an object")
        return
    for key in ("id", "title", "class", "treatment", "as_of"):
        if not str(source.get(key) or "").strip():
            errors.append(f"{location}.{key} is required")
    url = source.get("url")
    if url is not None and str(url).strip():
        if not isinstance(url, str) or not url.strip().startswith(
            ("http://", "https://")
        ):
            errors.append(f"{location}.url must be an http(s) URL when present")
    _validate_localized_value(
        source.get("class"),
        f"{location}.class",
        errors,
        allow_plain=True,
    )
    _validate_localized_value(
        source.get("treatment"),
        f"{location}.treatment",
        errors,
        allow_plain=False,
    )


_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_CJK_CHAR_RE = re.compile(r"[㐀-䶿一-鿿]")


def _is_language_neutral_text(text: str) -> bool:
    """True for plain strings safe to render identically in both locales.

    Dates, figures, percentages, tickers, and proper-noun names carry no
    translatable prose, so ``{"en": "2026-05", "zh": "2026-05"}`` would be
    pure ceremony. Anything containing ordinary lowercase English words
    ("120+ filed / 90+ issued") still requires an explicit bilingual pair.
    """
    stripped = text.strip()
    if not stripped or _CJK_CHAR_RE.search(stripped):
        return False
    words = _LATIN_WORD_RE.findall(stripped)
    if not words:
        return True
    if len(words) > 5:
        return False
    return all(word[0].isupper() for word in words)


def _validate_localized_value(
    value: Any,
    location: str,
    errors: list[str],
    *,
    required: bool = True,
    allow_plain: bool = False,
) -> None:
    if value is None or value == "":
        if required:
            errors.append(f"{location} is required")
        return
    if isinstance(value, dict):
        if not str(value.get("en") or "").strip():
            errors.append(f"{location}.en is required")
        if not str(value.get("zh") or "").strip():
            errors.append(f"{location}.zh is required")
        return
    if allow_plain or isinstance(value, (int, float)):
        return
    if isinstance(value, str) and _is_language_neutral_text(value):
        return
    errors.append(
        f"{location} must be bilingual with en and zh (plain strings are "
        "allowed only for language-neutral values such as dates, figures, "
        "or proper-noun names)"
    )


def render_memos(
    package: dict | Path | str,
    *,
    out_en: Path | str,
    out_zh: Path | str,
    validation_en: Path | str | None = None,
    validation_zh: Path | str | None = None,
    inventory_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> dict:
    """Render English and Chinese DOCX files from one structured package."""
    payload = load_package(package) if isinstance(package, (str, Path)) else package
    validate_package(payload)
    outputs = {
        "en": Path(out_en),
        "zh": Path(out_zh),
    }
    for locale, path in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        document = _build_document(payload, locale)
        document.save(path)

    run_dir = outputs["en"].parent.parent
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    validation_paths = {
        "en": Path(validation_en) if validation_en else logs_dir / "validation.txt",
        "zh": Path(validation_zh) if validation_zh else logs_dir / "validation_cn.txt",
    }
    for locale, path in validation_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_validation_report(payload, outputs[locale], locale), encoding="utf-8")
    if inventory_path:
        _write_inventory(Path(inventory_path), payload, outputs, validation_paths)
    else:
        _write_inventory(logs_dir / "file_inventory.md", payload, outputs, validation_paths)
    if manifest_path:
        _append_manifest(Path(manifest_path), payload, outputs, validation_paths)
    else:
        _append_manifest(logs_dir / "run_manifest.md", payload, outputs, validation_paths)
    return {
        "ok": True,
        "outputs": {locale: str(path) for locale, path in outputs.items()},
        "validation": {locale: str(path) for locale, path in validation_paths.items()},
    }


def pin_section_titles(package: dict, structure) -> list[str]:
    """Replace a core section's heading with the canonical title when the
    parity gate would not recognise it. Returns one note per change.

    The package's own heading normally wins, so a model that writes
    "公司概况与公司治理" where the profile says "公司概览" ships that heading —
    and the Chinese parity gate, which finds sections by full-line anchored
    patterns, then reports the section missing although every paragraph of
    it is there. A live Gemini run produced four such false "missing" P0s.
    Only headings the gate would reject are replaced: a recognised variant
    such as "II. Company Overview" keeps its numbering.
    """
    titles = structure.section_titles()
    patterns = structure.parity_patterns()
    notes: list[str] = []
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        if section_id not in titles or section_id not in patterns:
            continue
        for locale in ("en", "zh"):
            canonical = _loc(titles[section_id], locale)
            pattern = patterns[section_id].get(locale)
            if not canonical or pattern is None:
                continue
            own = _loc(section.get("title"), locale)
            if own and pattern.match(own):
                continue
            title = section.get("title")
            if not isinstance(title, dict):
                title = {"en": own, "zh": own} if own else {}
            title[locale] = canonical
            section["title"] = title
            notes.append(f"{section_id}.title.{locale}: {own!r} -> {canonical!r}")
    return notes


def _build_document(package: dict, locale: str) -> Document:
    structure = _structure_for(package)
    pin_section_titles(package, structure)
    section_titles = structure.section_titles()
    document = Document()
    _configure_document(document, package, locale)
    _add_cover(document, package, locale)
    # Each numbered section opens on a fresh page (the cover's own page
    # break already precedes the first one) — sections packed back to
    # back read cramped.
    first = True
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if not first:
            document.add_page_break()
        first = False
        _add_section(document, section, locale, section_titles)
    if package.get("sources") and not _has_section(package, "sources"):
        if not first:
            document.add_page_break()
        _add_sources_section(document, package, locale, section_titles)
    if package.get("calculations"):
        _add_calculations_section(document, package, locale)
    return document


def _configure_document(document: Document, package: dict, locale: str) -> None:
    font = _font(locale)
    section = document.sections[0]
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(1.9)
    section.right_margin = Cm(1.9)
    section.different_first_page_header_footer = True

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = font
    normal.font.size = Pt(10.2)
    _set_rfonts(normal.element.get_or_add_rPr(), font, locale)

    header_text = (
        f"{_company_name(package)} | BSH Confidential Investment Memo"
        if locale == "en"
        else f"{_company_name(package)} | BSH 机密投资备忘录"
    )
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(header, header_text, size=8.5, color=GREY, locale=locale)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_number(footer, locale)
    for run in footer.runs:
        _style_run(run, size=8.5, color=GREY, locale=locale)


def _add_cover(document: Document, package: dict, locale: str) -> None:
    company = package.get("company") or {}
    meta = package.get("run") if isinstance(package.get("run"), dict) else {}
    title = "BERKELEY SUMMIT HOUSE" if locale == "en" else "BERKELEY SUMMIT HOUSE"
    subtitle = "Confidential Investment Memo" if locale == "en" else "机密投资备忘录"
    descriptor = _loc(company.get("descriptor"), locale)

    _add_paragraph(document, title, size=18, bold=True, color=NAVY, align="center", after=4)
    _add_paragraph(document, subtitle, size=12, color=GREY, align="center", after=28)
    _add_paragraph(
        document,
        _company_name(package),
        size=26,
        bold=True,
        color=NAVY,
        align="center",
        after=4,
    )
    if descriptor:
        _add_paragraph(document, descriptor, size=12, color=GREY, align="center", after=18)

    rows = [
        (_label("Date", "日期", locale), meta.get("as_of") or meta.get("run_id") or ""),
        (_label("Stage", "阶段", locale), _loc(company.get("stage"), locale)),
        (_label("Sector", "行业", locale), _loc(company.get("sector"), locale)),
        (_label("Location", "地点", locale), _loc(company.get("location"), locale)),
        (_label("Round", "轮次", locale), _loc(company.get("round"), locale)),
    ]
    _add_key_value_table(document, [(k, v) for k, v in rows if str(v or "").strip()], locale)

    _add_paragraph(
        document,
        "TABLE OF CONTENTS" if locale == "en" else "目录",
        size=9.5,
        bold=True,
        color=TIFFANY,
        align="center",
        before=16,
        after=6,
    )
    toc_rows = []
    for index, title in enumerate(_toc_titles(package, locale), start=1):
        toc_rows.append([title, str(index)])
    _add_table(document, {"headers": [], "rows": toc_rows, "compact": True}, locale)
    document.add_page_break()


def _add_section(
    document: Document,
    section: dict,
    locale: str,
    section_titles: dict[str, dict[str, str]] | None = None,
) -> None:
    title = _section_title(section, locale, section_titles)
    if title:
        _add_heading(document, title, level=1, locale=locale)
    for block in section.get("blocks") or []:
        if isinstance(block, dict):
            _add_block(document, block, locale)


def _is_numbered_section_heading(text: str) -> bool:
    """True when a heading block restates a top-level numbered section title.

    Numbered section titles are rendered automatically by :func:`_add_section`,
    so a heading block carrying such a prefix is a duplicate and must be
    dropped. See :data:`_NUMBERED_SECTION_HEADING_RE`.
    """
    return bool(text and _NUMBERED_SECTION_HEADING_RE.match(text))


def _add_block(document: Document, block: dict, locale: str) -> None:
    kind = str(block.get("type") or "paragraph")
    if kind == "heading":
        text = _loc(block.get("text") or block.get("title"), locale)
        if _is_numbered_section_heading(text):
            # Redundant restatement of the auto-rendered section title — skip.
            return
        _add_heading(
            document,
            text,
            level=int(block.get("level") or 2),
            locale=locale,
        )
    elif kind == "bullets":
        bold_lead = str(block.get("component") or "") in _BOLD_LEAD_COMPONENTS
        for item in block.get("items") or []:
            _add_bullet(
                document, _loc(item, locale), locale=locale, bold_lead=bold_lead
            )
    elif kind == "table":
        if block.get("title"):
            _add_heading(document, _loc(block.get("title"), locale), level=3, locale=locale)
        _add_table(document, block, locale)
    elif kind == "chart":
        _add_chart(document, block, locale)
    elif kind == "callout":
        _add_callout(document, block, locale)
    elif kind == "spacer":
        document.add_paragraph()
    else:
        text = _loc(block.get("text") or block.get("body") or "", locale)
        if text:
            _add_paragraph(document, text, locale=locale)


def _add_sources_section(
    document: Document,
    package: dict,
    locale: str,
    section_titles: dict[str, dict[str, str]] | None = None,
) -> None:
    _add_heading(
        document,
        _section_title({"id": "sources"}, locale, section_titles),
        level=1,
        locale=locale,
    )
    headers = (
        ["Source", "Class", "Treatment", "As of"]
        if locale == "en"
        else ["来源", "类别", "处理方式", "时点"]
    )
    rows = []
    sources = [s for s in package.get("sources") or [] if isinstance(s, dict)]
    for source in sources:
        rows.append([
            _loc(source.get("title") or source.get("id"), locale),
            _loc(source.get("class") or source.get("type"), locale),
            _loc(source.get("treatment"), locale),
            _loc(source.get("as_of"), locale),
        ])
    _add_table(document, {"headers": headers, "rows": rows}, locale)
    if not rows:
        return
    # Bookmark every row (the target of inline `[S#]` links) and turn the
    # title into an external link when the source carries a URL.
    table = document.tables[-1]
    for index, source in enumerate(sources):
        source_id = str(source.get("id") or "").strip()
        cell = table.rows[index + 1].cells[0]
        paragraph = cell.paragraphs[0]
        if source_id:
            _add_bookmark(paragraph, citation_anchor(source_id))
        url = str(source.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            for run in list(paragraph.runs):
                run._r.getparent().remove(run._r)
            _append_hyperlink(
                paragraph,
                _loc(source.get("title") or source_id, locale),
                url=url,
                locale=locale,
                size=9.3,
            )


CALCULATIONS_TITLE = {"en": "Calculation notes", "zh": "计算说明"}


def _calculation_inputs_text(calculation: dict) -> str:
    parts = []
    for item in calculation.get("inputs") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        ref_note = f" [{ref}]" if ref else ""
        parts.append(f"{item.get('name')} = {item.get('value')}{ref_note}")
    return "; ".join(parts)


def _add_calculations_section(
    document: Document, package: dict, locale: str
) -> None:
    """The appendix behind every `[C#]` link: one bookmarked row per
    pinned calculation note — what was computed, from which inputs, the
    arithmetic, the result, and what it means."""
    calculations = [
        c for c in package.get("calculations") or [] if isinstance(c, dict)
    ]
    if not calculations:
        return
    _add_heading(document, CALCULATIONS_TITLE[locale], level=1, locale=locale)
    headers = (
        ["ID", "What", "Inputs", "Formula", "Result", "Meaning"]
        if locale == "en"
        else ["编号", "计算内容", "输入", "公式", "结果", "含义"]
    )
    rows = [
        [
            str(calc.get("id") or ""),
            _loc(calc.get("label"), locale),
            _calculation_inputs_text(calc),
            str(calc.get("formula") or ""),
            str(calc.get("result") or ""),
            _loc(calc.get("meaning"), locale),
        ]
        for calc in calculations
    ]
    _add_table(document, {"headers": headers, "rows": rows}, locale)
    table = document.tables[-1]
    for index, calc in enumerate(calculations):
        calc_id = str(calc.get("id") or "").strip()
        if calc_id:
            _add_bookmark(
                table.rows[index + 1].cells[0].paragraphs[0],
                citation_anchor(calc_id),
            )


def _add_heading(document: Document, text: str, *, level: int, locale: str) -> None:
    if not text:
        return
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    # Level-2 subsection headings get real air above them so the fixed
    # numbered subsections read as visual units, not a wall of text.
    paragraph.paragraph_format.space_before = Pt(
        12 if level == 1 else 16 if level == 2 else 7
    )
    paragraph.paragraph_format.space_after = Pt(
        5 if level == 1 else 4 if level == 2 else 3
    )
    if level == 1:
        _add_bottom_border(paragraph, TIFFANY)
    _add_run(
        paragraph,
        text.upper() if locale == "en" and level == 1 else text,
        bold=True,
        size=15 if level == 1 else 11.5 if level == 2 else 10.2,
        color=NAVY if level <= 2 else BLACK,
        locale=locale,
    )


def _add_paragraph(
    document_or_cell: Any,
    text: str,
    *,
    locale: str = "en",
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    align: str = "left",
    before: float = 0,
    after: float = 5,
) -> None:
    paragraph = document_or_cell.add_paragraph()
    paragraph.alignment = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }.get(align, WD_ALIGN_PARAGRAPH.LEFT)
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.12 if locale == "en" else 1.25
    _add_run(paragraph, text, size=size, bold=bold, color=color, locale=locale)


# Bullet blocks whose items open with a verdict headline (the executive
# summary's investment highlights and key risks): the lead sentence is
# rendered bold, the way the fund's own LP deck sets its highlights.
_BOLD_LEAD_COMPONENTS = frozenset({"investment_highlights", "key_risks"})
_LEAD_SENTENCE_RE = re.compile(r"^(.+?(?:[.!?](?=\s)|[。！？]))(.*)$", re.DOTALL)
# The docx has no markdown. Writers told a headline "is rendered bold"
# sometimes wrap it in "**...**" themselves (live compact run,
# 2026-09-14: the asterisks printed literally in both languages).
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_BOLD_LEAD_RE = re.compile(r"^\s*\*\*(.+?)\*\*(.*)$", re.DOTALL)


def strip_markdown_bold(text: str) -> str:
    """Drop markdown bold markers ("**Acme leads.**" -> "Acme leads.")."""
    if "**" not in text:
        return text
    return _MD_BOLD_RE.sub(r"\1", text).replace("**", "")


def split_lead_sentence(text: str) -> tuple[str, str]:
    """Split ``text`` into (lead sentence, remainder). The lead ends at
    the first sentence-final mark followed by whitespace (so "$1.5T" and
    "vs." inside a sentence do not split it) or at a CJK full stop. A
    single sentence with no remainder is entirely the lead. A lead the
    writer wrapped in markdown bold is taken as written, markers dropped."""
    marked = _MD_BOLD_LEAD_RE.match(text)
    if marked:
        lead = marked.group(1).strip()
        rest = strip_markdown_bold(marked.group(2))
        if rest[:1].isalnum() and lead.endswith((".", "!", "?")):
            rest = f" {rest}"
        return lead, rest
    text = strip_markdown_bold(text)
    match = _LEAD_SENTENCE_RE.match(text)
    if match:
        return match.group(1), match.group(2)
    return text, ""


def _add_bullet(
    document: Document, text: str, *, locale: str, bold_lead: bool = False
) -> None:
    paragraph = document.add_paragraph(style=None)
    paragraph.paragraph_format.left_indent = Cm(0.45)
    paragraph.paragraph_format.first_line_indent = Cm(-0.18)
    paragraph.paragraph_format.space_after = Pt(3)
    if bold_lead:
        lead, rest = split_lead_sentence(str(text or ""))
        _add_run(paragraph, f"• {lead}", bold=True, locale=locale)
        if rest:
            _add_run(paragraph, rest, locale=locale)
        return
    _add_run(paragraph, f"• {text}", locale=locale)


def _add_chart(document: Document, block: dict, locale: str) -> None:
    """Render a ``chart`` block: localized heading, one shared PNG (all
    image-internal text is English/neutral), localized caption. When the
    chart cannot be drawn (matplotlib missing or a render fault), fall
    back to the series as a small table so the data always ships."""
    title = _loc(block.get("title"), locale)
    if title:
        _add_heading(document, title, level=3, locale=locale)
    png: bytes | None = None
    try:
        from server import memo_charts

        png = memo_charts.chart_png(block)
    except Exception:
        png = None
    if png:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.add_run().add_picture(io.BytesIO(png), width=Inches(6.0))
    else:
        _add_table(document, _chart_fallback_table(block), locale)
    caption = _loc(block.get("caption"), locale)
    reading = _loc(block.get("reading"), locale)
    if reading:
        reading_text = (
            f"Reading: {reading}" if locale == "en" else f"读法：{reading}"
        )
        caption = f"{reading_text}  {caption}".strip() if caption else reading_text
    source_ids = ", ".join(
        str(item).strip()
        for item in block.get("source_ids") or []
        if str(item or "").strip()
    )
    if source_ids:
        sources_text = (
            f"Sources: {source_ids}" if locale == "en" else f"来源：{source_ids}"
        )
        caption = f"{caption}  {sources_text}".strip() if caption else sources_text
    if caption:
        _add_paragraph(
            document, caption, locale=locale, size=8.5, color=GREY, after=8
        )


def _chart_fallback_table(block: dict) -> dict:
    """The chart's series as a plain table block (language-neutral cells)."""
    series = [s for s in block.get("series") or [] if isinstance(s, dict)]
    first = series[0] if series else {}
    xs = [str(p.get("x")) for p in first.get("points") or [] if isinstance(p, dict)]
    unit = _content_text(block.get("unit"))
    headers: list[Any] = [unit or "", *xs]
    rows = []
    for one in series:
        cells: list[Any] = [str(one.get("label") or "")]
        for point in one.get("points") or []:
            value = point.get("y") if isinstance(point, dict) else ""
            cells.append(str(value))
        rows.append(cells)
    return {"type": "table", "headers": headers, "rows": rows}


def _add_callout(document: Document, block: dict, locale: str) -> None:
    title = _loc(block.get("title") or block.get("label"), locale)
    body = _loc(block.get("body") or block.get("text"), locale)
    items = [_loc(item, locale) for item in block.get("items") or [] if _loc(item, locale)]
    tone = str(block.get("tone") or "info")
    fill = PALE_GOLD if tone in {"warning", "critical", "risk"} else PALE_TIFFANY
    table = document.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _shade_cell(cell, fill)
    _set_cell_borders(cell, left=(TIFFANY, "24"))
    if title:
        _add_paragraph(cell, title, locale=locale, bold=True, color=NAVY, after=2)
    if body:
        _add_paragraph(cell, body, locale=locale, after=2)
    for item in items:
        _add_paragraph(cell, f"• {item}", locale=locale, after=1)
    document.add_paragraph().paragraph_format.space_after = Pt(4)


def _add_key_value_card_table(document: Document, rows: list[list[str]], locale: str) -> None:
    """Render a ``layout: "key_value"`` block: label column left, prose right.

    This is the risk-card layout — a shaded bold label column so the reader
    scans Risk Type / Why it matters / What we watch / Likelihood / Risk
    Rating at a glance. Rating ("8/10: …") and likelihood ("High: …")
    values are bolded so the assessment stands out.
    """
    table = document.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for idx, (label, value) in enumerate(rows):
        cells = table.rows[idx].cells
        cells[0].width = Cm(4.2)
        cells[1].width = Cm(11.3)
        _shade_cell(cells[0], WARM_GREY)
        _set_cell_borders(cells[0])
        _set_cell_borders(cells[1])
        _cell_text(cells[0], label, locale=locale, bold=True, color=NAVY)
        _cell_text(
            cells[1],
            value,
            locale=locale,
            bold=bool(
                _RISK_RATING_VALUE_RE.match(str(value or ""))
                or _RISK_LIKELIHOOD_VALUE_RE.match(str(value or ""))
            ),
        )
    document.add_paragraph().paragraph_format.space_after = Pt(4)


def _add_key_value_table(document: Document, rows: list[tuple[str, str]], locale: str) -> None:
    if not rows:
        return
    table = document.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, (key, value) in enumerate(rows):
        cells = table.rows[idx].cells
        cells[0].width = Cm(4.0)
        cells[1].width = Cm(9.0)
        _shade_cell(cells[0], WARM_GREY)
        _set_cell_borders(cells[0])
        _set_cell_borders(cells[1])
        _cell_text(cells[0], key, locale=locale, bold=True, color=NAVY)
        _cell_text(cells[1], str(value), locale=locale)


def _add_table(document: Document, block: dict, locale: str) -> None:
    headers = [_loc(header, locale) for header in block.get("headers") or []]
    rows = [_row_values(row, locale) for row in block.get("rows") or []]
    if not rows and not headers:
        return
    if (
        str(block.get("layout") or "").strip().lower() == "key_value"
        and not headers
        and rows
        and all(len(row) == 2 for row in rows)
    ):
        _add_key_value_card_table(document, rows, locale)
        return
    col_count = max([len(headers), *(len(row) for row in rows)] or [1])
    table = document.add_table(rows=(1 if headers else 0) + len(rows), cols=col_count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    row_offset = 0
    if headers:
        for col_idx, value in enumerate(headers):
            cell = table.rows[0].cells[col_idx]
            _shade_cell(cell, NAVY)
            _set_cell_borders(cell, color=WHITE)
            _cell_text(cell, value, locale=locale, bold=True, color=WHITE)
        row_offset = 1
    for row_idx, row in enumerate(rows, start=row_offset):
        for col_idx in range(col_count):
            cell = table.rows[row_idx].cells[col_idx]
            if row_idx % 2 == row_offset % 2:
                _shade_cell(cell, "FAFAFA")
            _set_cell_borders(cell)
            _cell_text(cell, row[col_idx] if col_idx < len(row) else "", locale=locale)
    document.add_paragraph().paragraph_format.space_after = Pt(4)


def _cell_text(cell: Any, text: Any, *, locale: str, bold: bool = False, color: str = BLACK) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    _add_run(paragraph, _loc(text, locale), locale=locale, bold=bold, color=color, size=9.3)


# Inline citations: `[S3]`, `[C2]`, `[S3, C2]` — ids of package sources
# (S) and calculation notes (C). The renderer turns each id into a
# superscript link to its bookmarked row in the Sources table or the
# Calculation notes appendix, so a reader can click through to where a
# number came from and how it was computed (founder feedback 2026-09-13).
_CITATION_RE = re.compile(r"\[((?:[SC]\d+)(?:\s*,\s*[SC]\d+)*)\]")
_BOOKMARK_IDS = itertools.count(9000)
CITATION_LINK_COLOR = "1F4E79"


def citation_ids(text: Any) -> list[str]:
    """Every citation id in ``text`` in order (with repeats)."""
    ids: list[str] = []
    for group in _CITATION_RE.findall(str(text or "")):
        ids.extend(part.strip() for part in group.split(","))
    return ids


def citation_anchor(citation_id: str) -> str:
    return f"src_{citation_id}" if citation_id.startswith("S") else f"calc_{citation_id}"


def _add_bookmark(paragraph: Any, name: str) -> None:
    bookmark_id = str(next(_BOOKMARK_IDS))
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bookmark_id)
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bookmark_id)
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def _append_hyperlink(
    paragraph: Any,
    text: str,
    *,
    anchor: str | None = None,
    url: str | None = None,
    locale: str = "en",
    size: float = 10.2,
    superscript: bool = False,
) -> Any:
    """Append a run wrapped in ``w:hyperlink`` — internal (``anchor`` to a
    bookmark) or external (``url`` via a document relationship)."""
    hyperlink = OxmlElement("w:hyperlink")
    if url:
        r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
        hyperlink.set(qn("r:id"), r_id)
    elif anchor:
        hyperlink.set(qn("w:anchor"), anchor)
    run = paragraph.add_run(str(text or ""))
    _style_run(run, size=size, bold=False, color=CITATION_LINK_COLOR, locale=locale)
    if superscript:
        run.font.superscript = True
    else:
        run.font.underline = True
    hyperlink.append(run._r)
    paragraph._p.append(hyperlink)
    return run


def _add_run(
    paragraph: Any,
    text: str,
    *,
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    locale: str = "en",
) -> Any:
    text = strip_markdown_bold(str(text or ""))
    if "[" not in text or not _CITATION_RE.search(text):
        run = paragraph.add_run(text)
        _style_run(run, size=size, bold=bold, color=color, locale=locale)
        return run
    last: Any = None
    position = 0
    for match in _CITATION_RE.finditer(text):
        if match.start() > position:
            last = paragraph.add_run(text[position : match.start()])
            _style_run(last, size=size, bold=bold, color=color, locale=locale)
        ids = [part.strip() for part in match.group(1).split(",")]
        for index, citation_id in enumerate(ids):
            label = citation_id if index == len(ids) - 1 else f"{citation_id},"
            last = _append_hyperlink(
                paragraph,
                label,
                anchor=citation_anchor(citation_id),
                locale=locale,
                size=size,
                superscript=True,
            )
        position = match.end()
    if position < len(text):
        last = paragraph.add_run(text[position:])
        _style_run(last, size=size, bold=bold, color=color, locale=locale)
    return last


def _style_run(
    run: Any,
    *,
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    locale: str = "en",
) -> None:
    font = _font(locale)
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    _set_rfonts(run._element.get_or_add_rPr(), font, locale)


def _set_rfonts(rpr: Any, font: str, locale: str) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    if locale == "zh":
        rfonts.set(qn("w:eastAsia"), ZH_FONT)
        rfonts.set(qn("w:ascii"), EN_FONT)
        rfonts.set(qn("w:hAnsi"), EN_FONT)
        rfonts.set(qn("w:cs"), EN_FONT)
    else:
        rfonts.set(qn("w:ascii"), font)
        rfonts.set(qn("w:hAnsi"), font)
        rfonts.set(qn("w:cs"), font)


def _add_page_number(paragraph: Any, locale: str) -> None:
    if locale == "zh":
        _add_run(paragraph, "第 ", locale=locale, size=8.5, color=GREY)
    else:
        _add_run(paragraph, "Page ", locale=locale, size=8.5, color=GREY)
    run = paragraph.add_run()
    for element in (
        _field_char("begin"),
        _instr_text("PAGE"),
        _field_char("end"),
    ):
        run._r.append(element)
    _style_run(run, locale=locale, size=8.5, color=GREY)
    if locale == "zh":
        _add_run(paragraph, " 页", locale=locale, size=8.5, color=GREY)


def _field_char(kind: str) -> Any:
    element = OxmlElement("w:fldChar")
    element.set(qn("w:fldCharType"), kind)
    return element


def _instr_text(value: str) -> Any:
    element = OxmlElement("w:instrText")
    element.set(qn("xml:space"), "preserve")
    element.text = value
    return element


def _shade_cell(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def _set_cell_borders(
    cell: Any,
    *,
    color: str = BORDER,
    size: str = "4",
    left: tuple[str, str] | None = None,
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcBorders"))
    if existing is not None:
        tc_pr.remove(existing)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        if side == "left" and left:
            border.set(qn("w:sz"), left[1])
            border.set(qn("w:color"), left[0])
        else:
            border.set(qn("w:sz"), size)
            border.set(qn("w:color"), color)
        borders.append(border)
    tc_pr.append(borders)


def _add_bottom_border(paragraph: Any, color: str) -> None:
    p_pr = paragraph._element.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)


def _validation_report(package: dict, output_path: Path, locale: str) -> str:
    document = Document(output_path)
    table_count = len(document.tables)
    paragraph_count = sum(1 for paragraph in document.paragraphs if paragraph.text.strip())
    callout_count = sum(
        1
        for section in package.get("sections") or []
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") == "callout"
    )
    structure = _structure_for(package)
    coverage = _memo_component_coverage(package, structure)
    coverage_lines = [
        f"- {component['id']}: {'present' if coverage[str(component['id'])] else 'missing'}"
        for component in structure.components
    ]
    return "\n".join([
        "# Memo Renderer Validation",
        "",
        f"- output: `{output_path}`",
        f"- locale: {locale}",
        f"- schema_version: {package.get('schema_version')}",
        f"- paragraphs: {paragraph_count}",
        f"- tables: {table_count}",
        f"- declared_callouts: {callout_count}",
        "",
        "## Content Coverage",
        "",
        *coverage_lines,
        "",
        "- status: passed",
        "",
    ])


def _write_inventory(
    path: Path,
    package: dict,
    outputs: dict[str, Path],
    validation_paths: dict[str, Path],
) -> None:
    lines = ["# Memo File Inventory", ""]
    lines.append(f"- company: {_company_name(package)}")
    lines.append(f"- schema_version: {package.get('schema_version')}")
    for locale, output in outputs.items():
        lines.append(f"- memo_{locale}: `{output}`")
    for locale, validation in validation_paths.items():
        lines.append(f"- validation_{locale}: `{validation}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _append_manifest(
    path: Path,
    package: dict,
    outputs: dict[str, Path],
    validation_paths: dict[str, Path],
) -> None:
    lines = [
        "",
        "## Analysis Finalization",
        "",
        f"- renderer: server.memo_docx_renderer",
        f"- memo_package_schema_version: {package.get('schema_version')}",
    ]
    for locale, output in outputs.items():
        lines.append(f"- memo_{locale}: `{output}`")
    for locale, validation in validation_paths.items():
        lines.append(f"- validation_{locale}: `{validation}`")
    lines.append("- validation_status: passed")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def _has_section(package: dict, section_id: str) -> bool:
    return any(
        isinstance(section, dict) and section.get("id") == section_id
        for section in package.get("sections") or []
    )


def _section_title(
    section: dict,
    locale: str,
    section_titles: dict[str, dict[str, str]] | None = None,
) -> str:
    titles = SECTION_TITLES if section_titles is None else section_titles
    return _loc(section.get("title"), locale) or _loc(
        titles.get(str(section.get("id") or ""), ""), locale
    )


def _toc_titles(package: dict, locale: str) -> list[str]:
    section_titles = _structure_for(package).section_titles()
    titles: list[str] = []
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        title = _section_title(section, locale, section_titles)
        if title:
            titles.append(title)
    if package.get("sources") and not _has_section(package, "sources"):
        titles.append(_section_title({"id": "sources"}, locale, section_titles))
    if package.get("calculations"):
        titles.append(CALCULATIONS_TITLE[locale])
    return titles


def _row_values(row: Any, locale: str) -> list[str]:
    if isinstance(row, dict):
        if isinstance(row.get("cells"), list):
            return [_loc(value, locale) for value in row["cells"]]
        return [_loc(value, locale) for value in row.values()]
    if isinstance(row, (list, tuple)):
        return [_loc(value, locale) for value in row]
    return [_loc(row, locale)]


def _loc(value: Any, locale: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        selected = value.get(locale)
        if selected is None:
            selected = value.get("en")
        if selected is None:
            selected = next(iter(value.values()), "")
        return str(selected or "")
    return str(value)


def _company_name(package: dict) -> str:
    company = package.get("company") or {}
    return _loc(company.get("name") or company.get("display_name") or "Company", "en")


def _font(locale: str) -> str:
    return ZH_FONT if locale == "zh" else EN_FONT


def _label(en: str, zh: str, locale: str) -> str:
    return zh if locale == "zh" else en


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render BSH memo DOCX files from memo_package.json")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--out-en", required=True, type=Path)
    parser.add_argument("--out-zh", required=True, type=Path)
    parser.add_argument("--validation-en", type=Path)
    parser.add_argument("--validation-zh", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    render_memos(
        args.package,
        out_en=args.out_en,
        out_zh=args.out_zh,
        validation_en=args.validation_en,
        validation_zh=args.validation_zh,
        inventory_path=args.inventory,
        manifest_path=args.manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
