"""Parameterized DOCX renderer for BSH investment memos.

Claude owns memo judgment and writes ``memo_package.json``. This module owns
all DOCX construction so memo runs do not generate bespoke Python/JS renderers.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

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

SECTION_TITLES = {
    "executive_summary": {
        "en": "I. Executive Summary",
        "zh": "I. 执行摘要",
    },
    "company_overview": {
        "en": "II. Company Overview",
        "zh": "II. 公司概览",
    },
    "investment_highlights": {
        "en": "III. Investment Highlights",
        "zh": "III. 投资亮点",
    },
    "investment_risk": {
        "en": "IV. Investment Risk",
        "zh": "IV. 投资风险",
    },
    "financial_forecast_valuation": {
        "en": "V. Financial Forecast & Valuation",
        "zh": "V. 财务预测与估值",
    },
    "sources": {
        "en": "VI. Sources, Source Classes, and Fact Reference Index",
        "zh": "VI. 来源、来源类别与事实索引",
    },
    "validation_log": {
        "en": "Appendix: Source Treatment And Assumptions",
        "zh": "附录：来源处理与假设",
    },
}

TOC_SECTION_IDS = (
    "executive_summary",
    "company_overview",
    "investment_highlights",
    "investment_risk",
    "financial_forecast_valuation",
    "sources",
)
REQUIRED_SECTION_IDS = (
    "executive_summary",
    "company_overview",
    "investment_highlights",
    "investment_risk",
    "financial_forecast_valuation",
)
REQUIRED_MEMO_COMPONENTS = (
    {
        "id": "key_metrics_snapshot",
        "label": "Executive Summary / Key Metrics Snapshot table",
        "block_types": {"table"},
        "patterns": (r"\bkey metrics snapshot\b",),
    },
    {
        "id": "deal_terms",
        "label": "deal mechanics / headline terms table",
        "block_types": {"table"},
        "patterns": (
            r"\bheadline terms\b",
            r"\bdeal terms\b",
            r"\btransaction terms\b",
            r"\bspv\b.*\bsafe\b",
        ),
    },
    {
        "id": "board",
        "label": "Company Overview / Board of Directors table",
        "block_types": {"table"},
        "patterns": (r"\bboard of directors\b", r"\bboard\b.*\bstrategic value\b"),
    },
    {
        "id": "revenue",
        "label": "Company Overview / Revenue table",
        "block_types": {"table"},
        "patterns": (r"\brevenue picture\b", r"\brevenue\b", r"\barr\b"),
    },
    {
        "id": "key_operating_metrics",
        "label": "Company Overview / Key Operating Metrics table",
        "block_types": {"table"},
        "patterns": (
            r"\bkey operating metrics\b",
            r"\bkey metrics\b",
            r"\barr per employee\b",
            r"\bgross margin\b",
        ),
    },
    {
        "id": "competitive_analysis",
        "label": "Investment Highlights / Competitive Analysis table",
        "block_types": {"table"},
        "patterns": (
            r"\bcompetitive analysis\b",
            r"\bcompetitive landscape\b",
            r"\bcompetitor\b.*\bweakness\b",
        ),
    },
    {
        "id": "replacement_coexistence",
        "label": "Investment Highlights / Replacement vs. Coexistence treatment",
        "block_types": {"table"},
        "patterns": (
            r"\breplacement\b.*\bcoexistence\b",
            r"\breplaces?\b.*\bcoexists?\b",
        ),
    },
    {
        "id": "moat",
        "label": "Investment Highlights / Moat or defensibility table",
        "block_types": {"table"},
        "patterns": (
            r"\bmoat\b",
            r"\bdefensibility\b",
            r"\bright[s]? durability\b",
        ),
    },
    {
        "id": "risk_register",
        "label": "Investment Risk / Risk Register table",
        "block_types": {"table"},
        "patterns": (r"\brisk register\b", r"\bseverity\b.*\blikelihood\b"),
    },
    {
        "id": "disconfirming_evidence",
        "label": "Investment Risk / disconfirming evidence treatment",
        "block_types": {"paragraph", "bullets", "callout", "table"},
        "patterns": (
            r"\bdisconfirming evidence\b",
            r"\bbear-case evidence\b",
            r"\bdownside scenario\b",
            r"\bcountercase\b",
        ),
    },
    {
        "id": "time_base_integrity",
        "label": "Financial Forecast & Valuation / Time-Base Integrity table",
        "block_types": {"table"},
        "patterns": (
            r"\btime-base integrity\b",
            r"\btime base integrity\b",
            r"\blast priced valuation\b",
            r"\bstale-mark\b",
        ),
    },
    {
        "id": "growth_bridge",
        "label": "Financial Forecast & Valuation / Growth Bridge table",
        "block_types": {"table"},
        "patterns": (
            r"\bgrowth bridge\b",
            r"\bbridge\b.*\bconversion\b",
            r"\borganic\b.*\bpricing\b",
        ),
    },
    {
        "id": "scenario_analysis",
        "label": "Financial Forecast & Valuation / Scenario Analysis table",
        "block_types": {"table"},
        "patterns": (
            r"\bscenario analysis\b",
            r"\bseries b scenario\b",
            r"\bbear\b.*\bbase\b.*\bbull\b",
            r"\bgross moic\b",
        ),
    },
    {
        "id": "investment_decision",
        "label": "Investment Decision / Closing View",
        "block_types": {"heading", "paragraph", "callout"},
        "patterns": (
            r"\binvestment decision\b",
            r"\bclosing view\b",
            r"\brecommendation\b",
            r"\bwe recommend\b",
        ),
    },
    {
        "id": "evidence_thresholds",
        "label": "Evidence thresholds / step-up support treatment",
        "block_types": {"paragraph", "bullets", "callout", "table"},
        "patterns": (
            r"\bevidence thresholds?\b",
            r"\bstep-up evidence\b",
            r"\bstep-up case\b",
            r"\bevidence required\b",
            r"\bdiligence priorit(?:y|ies)\b",
        ),
    },
    {
        "id": "source_index",
        "label": "Sources, Source Classes, and Fact Reference Index",
        "block_types": {"table"},
        "patterns": (r"\bsource index\b", r"\bfact reference index\b"),
    },
    {
        "id": "disclosures",
        "label": "Legal / offering disclosures",
        "block_types": {"paragraph", "callout", "table"},
        "patterns": (
            r"\bdisclosures?\b",
            r"\bnot an offer to sell securities\b",
            r"\bdefinitive subscription documents\b",
            r"\baccredited investors\b",
            r"\bpartial or total loss\b",
        ),
    },
)
SUPPORTED_BLOCK_TYPES = {
    "heading",
    "paragraph",
    "bullets",
    "callout",
    "table",
    "spacer",
}
# Top-level section titles ("I."–"X." or "一、"–"十、") are emitted automatically
# by ``_add_section`` from ``SECTION_TITLES``. A heading *block* that carries the
# same numbered prefix is a redundant restatement of the section title; rendering
# it produces a doubled section heading (and trips the Chinese-parity
# heading-count gate, since EN/ZH restatements are not always recognized
# symmetrically). Legitimate sub-headings are unnumbered, so this prefix is a
# safe signal to drop the block.
_NUMBERED_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\.|[一二三四五六七八九十]+[、.．])",
    re.IGNORECASE,
)
VALUATION_CONTENT_TERMS = (
    "model treatment",
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


def _package_validation_errors(package: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(package, dict):
        return ["memo package must be a JSON object"]
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

    by_id: dict[str, dict] = {}
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{location} must be an object")
            continue
        section_id = str(section.get("id") or "").strip()
        if section_id:
            by_id[section_id] = section
            if section_id not in SECTION_TITLES and not _loc(
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

    for section_id in REQUIRED_SECTION_IDS:
        if section_id not in by_id:
            errors.append(f"missing required section {section_id}")
        else:
            _validate_section_content_floor(section_id, by_id[section_id], errors)
    _validate_required_memo_components(package, errors)

    if isinstance(sources, list):
        for index, source in enumerate(sources):
            _validate_source(source, f"sources[{index}]", errors)
    return errors


def _validate_required_memo_components(package: dict, errors: list[str]) -> None:
    coverage = _memo_component_coverage(package)
    for component in REQUIRED_MEMO_COMPONENTS:
        component_id = str(component["id"])
        if not coverage.get(component_id):
            errors.append(
                f"missing required memo component {component_id}: "
                f"{component['label']}"
            )


def _memo_component_coverage(package: dict) -> dict[str, bool]:
    coverage = {str(component["id"]): False for component in REQUIRED_MEMO_COMPONENTS}
    if isinstance(package.get("sources"), list) and package.get("sources"):
        coverage["source_index"] = True
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_title = _content_text(section.get("title")) or _section_title(section, "en")
        previous_heading = ""
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for component_id in _declared_component_ids(block):
                if component_id in coverage:
                    coverage[component_id] = True
            signature = _block_signature_text(block, section_title, previous_heading)
            kind = str(block.get("type") or "paragraph")
            for component in REQUIRED_MEMO_COMPONENTS:
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
    for key in ("component", "title", "label", "text", "body"):
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
) -> None:
    score = _section_content_score(section)
    if score["real_blocks"] < 1:
        errors.append(f"section {section_id} must contain substantive memo content")
        return
    if section_id == "executive_summary" and score["real_blocks"] < 2:
        errors.append(
            "section executive_summary must contain at least two substantive "
            "content blocks"
        )
    if section_id in {"investment_highlights", "investment_risk"}:
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
    if (
        section_id == "financial_forecast_valuation"
        and score["valuation_refs"] < 1
    ):
        errors.append(
            "section financial_forecast_valuation must reference model treatment, "
            "scenario ranges, valuation, revenue, margins, or valuation sensitivities"
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


def _validate_source(source: Any, location: str, errors: list[str]) -> None:
    if not isinstance(source, dict):
        errors.append(f"{location} must be an object")
        return
    for key in ("id", "title", "class", "treatment", "as_of"):
        if not str(source.get(key) or "").strip():
            errors.append(f"{location}.{key} is required")
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
    errors.append(f"{location} must be bilingual with en and zh")


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


def _build_document(package: dict, locale: str) -> Document:
    document = Document()
    _configure_document(document, package, locale)
    _add_cover(document, package, locale)
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        _add_section(document, section, locale)
    if package.get("sources") and not _has_section(package, "sources"):
        _add_sources_section(document, package, locale)
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


def _add_section(document: Document, section: dict, locale: str) -> None:
    title = _section_title(section, locale)
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
        for item in block.get("items") or []:
            _add_bullet(document, _loc(item, locale), locale=locale)
    elif kind == "table":
        if block.get("title"):
            _add_heading(document, _loc(block.get("title"), locale), level=3, locale=locale)
        _add_table(document, block, locale)
    elif kind == "callout":
        _add_callout(document, block, locale)
    elif kind == "spacer":
        document.add_paragraph()
    else:
        text = _loc(block.get("text") or block.get("body") or "", locale)
        if text:
            _add_paragraph(document, text, locale=locale)


def _add_sources_section(document: Document, package: dict, locale: str) -> None:
    _add_heading(document, _section_title({"id": "sources"}, locale), level=1, locale=locale)
    headers = (
        ["Source", "Class", "Treatment", "As of"]
        if locale == "en"
        else ["来源", "类别", "处理方式", "时点"]
    )
    rows = []
    for source in package.get("sources") or []:
        if not isinstance(source, dict):
            continue
        rows.append([
            _loc(source.get("title") or source.get("id"), locale),
            _loc(source.get("class") or source.get("type"), locale),
            _loc(source.get("treatment"), locale),
            _loc(source.get("as_of"), locale),
        ])
    _add_table(document, {"headers": headers, "rows": rows}, locale)


def _add_heading(document: Document, text: str, *, level: int, locale: str) -> None:
    if not text:
        return
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.space_before = Pt(12 if level == 1 else 7)
    paragraph.paragraph_format.space_after = Pt(5 if level == 1 else 3)
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


def _add_bullet(document: Document, text: str, *, locale: str) -> None:
    paragraph = document.add_paragraph(style=None)
    paragraph.paragraph_format.left_indent = Cm(0.45)
    paragraph.paragraph_format.first_line_indent = Cm(-0.18)
    paragraph.paragraph_format.space_after = Pt(3)
    _add_run(paragraph, f"• {text}", locale=locale)


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


def _add_run(
    paragraph: Any,
    text: str,
    *,
    size: float = 10.2,
    bold: bool = False,
    color: str = BLACK,
    locale: str = "en",
) -> Any:
    run = paragraph.add_run(str(text or ""))
    _style_run(run, size=size, bold=bold, color=color, locale=locale)
    return run


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
    coverage = _memo_component_coverage(package)
    coverage_lines = [
        f"- {component['id']}: {'present' if coverage[str(component['id'])] else 'missing'}"
        for component in REQUIRED_MEMO_COMPONENTS
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


def _section_title(section: dict, locale: str) -> str:
    return _loc(section.get("title"), locale) or _loc(
        SECTION_TITLES.get(str(section.get("id") or ""), ""), locale
    )


def _toc_titles(package: dict, locale: str) -> list[str]:
    titles: list[str] = []
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        title = _section_title(section, locale)
        if title:
            titles.append(title)
    if package.get("sources") and not _has_section(package, "sources"):
        titles.append(_section_title({"id": "sources"}, locale))
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
