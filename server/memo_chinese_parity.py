"""Chinese memo parity and fluency checks for rendered DOCX output."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from server import memo_structure

REQUIRED_SECTION_IDS = memo_structure.LATE.section_ids

# Section headings are full-line anchored patterns per id per locale,
# defined in the structure profile (skills/memo/structures/).
SECTION_PATTERNS = memo_structure.LATE.parity_patterns()

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]")
COUNTABLE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffA-Za-z0-9]")
TRANSLATIONESE_PATTERNS = (
    re.compile(r"关键现实检查"),
    re.compile(r"当前状态与上行状态"),
    re.compile(r"上行状态"),
    re.compile(r"现态"),
    re.compile(r"源追踪"),
    re.compile(r"备忘录包"),
    re.compile(r"审阅者提示"),
    re.compile(r"声明登记"),
    re.compile(r"硬\s*IP\s*墙", re.IGNORECASE),
    re.compile(r"软性?工具"),
)


@dataclass(frozen=True)
class ChineseParityFinding:
    severity: str
    code: str
    location: str
    snippet: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ChineseParityResult:
    en_path: str
    zh_path: str
    findings: list[ChineseParityFinding]

    @property
    def p0_findings(self) -> list[ChineseParityFinding]:
        return [finding for finding in self.findings if finding.severity == "P0"]

    @property
    def has_blocking_findings(self) -> bool:
        return bool(self.p0_findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "en_path": self.en_path,
            "zh_path": self.zh_path,
            "status": "failed" if self.has_blocking_findings else "passed",
            "finding_count": len(self.findings),
            "p0_count": len(self.p0_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class _DocBlock:
    kind: str
    text: str
    location: str
    section_id: str


@dataclass(frozen=True)
class _DocShape:
    path: Path
    locale: str
    blocks: list[_DocBlock]
    section_ids: list[str]
    table_count: int
    paragraph_count: int
    callout_like_table_count: int

    @property
    def section_count(self) -> int:
        # English DOCX often restates the Sources heading (TOC / disclosures /
        # fact index). Count unique section ids so those duplicates do not
        # falsely trip section_heading_count_mismatch vs Chinese.
        return len(dict.fromkeys(self.section_ids))


def lint_chinese_memo_pair(
    en_path: str | Path,
    zh_path: str | Path,
    structure: memo_structure.MemoStructure | None = None,
) -> ChineseParityResult:
    """Compare rendered English and Chinese memo DOCX files.

    ``structure`` names the report structure the pair was rendered
    against (section ids + heading patterns); default is late v1."""
    structure = structure or memo_structure.LATE
    patterns = structure.parity_patterns()
    en_docx = Path(en_path)
    zh_docx = Path(zh_path)
    try:
        en_shape = _extract_docx_shape(en_docx, "en", patterns)
        zh_shape = _extract_docx_shape(zh_docx, "zh", patterns)
    except Exception as exc:  # noqa: BLE001
        return ChineseParityResult(
            en_path=str(en_docx),
            zh_path=str(zh_docx),
            findings=[
                ChineseParityFinding(
                    severity="P0",
                    code="docx_extract_error",
                    location="document",
                    snippet=f"{type(exc).__name__}: {exc}",
                    suggestion="Generate valid English and Chinese DOCX files.",
                )
            ],
        )
    findings = _lint_shapes(en_shape, zh_shape, structure)
    return ChineseParityResult(
        en_path=str(en_docx),
        zh_path=str(zh_docx),
        findings=findings,
    )


def render_markdown_report(result: ChineseParityResult) -> str:
    payload = result.to_dict()
    lines = [
        "# Chinese Memo Parity Lint",
        "",
        f"- english: `{payload['en_path']}`",
        f"- chinese: `{payload['zh_path']}`",
        f"- status: {payload['status']}",
        f"- p0_count: {payload['p0_count']}",
        f"- finding_count: {payload['finding_count']}",
        "",
    ]
    if not result.findings:
        lines.append("No findings.")
        return "\n".join(lines).strip() + "\n"

    lines += [
        "| Severity | Code | Location | Snippet | Suggestion |",
        "|---|---|---|---|---|",
    ]
    for finding in result.findings:
        lines.append(
            "| "
            f"{_md_cell(finding.severity)} | "
            f"{_md_cell(finding.code)} | "
            f"{_md_cell(finding.location)} | "
            f"{_md_cell(finding.snippet)} | "
            f"{_md_cell(finding.suggestion)} |"
        )
    return "\n".join(lines).strip() + "\n"


def _extract_docx_shape(
    path: Path,
    locale: str,
    patterns: dict | None = None,
) -> _DocShape:
    from docx import Document  # type: ignore
    from docx.oxml.table import CT_Tbl  # type: ignore
    from docx.oxml.text.paragraph import CT_P  # type: ignore
    from docx.table import Table  # type: ignore
    from docx.text.paragraph import Paragraph  # type: ignore

    document = Document(path)
    blocks: list[_DocBlock] = []
    section_ids: list[str] = []
    current_section = "front_matter"
    paragraph_index = 0
    table_index = 0
    callout_like_table_count = 0

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = _clean_text(paragraph.text)
            if not text:
                continue
            paragraph_index += 1
            section_id = _section_id_from_heading(text, locale, patterns)
            kind = "heading" if section_id else "paragraph"
            if section_id:
                current_section = section_id
                section_ids.append(section_id)
            blocks.append(
                _DocBlock(
                    kind=kind,
                    text=text,
                    location=f"paragraph {paragraph_index}",
                    section_id=current_section,
                )
            )
        elif isinstance(child, CT_Tbl):
            table_index += 1
            table = Table(child, document)
            row_count = len(table.rows)
            col_count = max((len(row.cells) for row in table.rows), default=0)
            if row_count == 1 and col_count == 1:
                callout_like_table_count += 1
            for row_index, row in enumerate(table.rows, start=1):
                for col_index, cell in enumerate(row.cells, start=1):
                    text = _clean_text(cell.text)
                    if not text:
                        continue
                    blocks.append(
                        _DocBlock(
                            kind="table_cell",
                            text=text,
                            location=(
                                f"table {table_index} row {row_index} "
                                f"cell {col_index}"
                            ),
                            section_id=current_section,
                        )
                    )

    return _DocShape(
        path=path,
        locale=locale,
        blocks=blocks,
        section_ids=section_ids,
        table_count=table_index,
        paragraph_count=paragraph_index,
        callout_like_table_count=callout_like_table_count,
    )


def _lint_shapes(
    en_shape: _DocShape,
    zh_shape: _DocShape,
    structure: memo_structure.MemoStructure | None = None,
) -> list[ChineseParityFinding]:
    structure = structure or memo_structure.LATE
    findings: list[ChineseParityFinding] = []

    if en_shape.section_count != zh_shape.section_count:
        findings.append(
            _finding(
                "P0",
                "section_heading_count_mismatch",
                "document",
                f"en={en_shape.section_count}, zh={zh_shape.section_count}",
                "Keep the Chinese memo's top-level structure aligned to English.",
            )
        )

    for section_id in structure.section_ids:
        if section_id not in zh_shape.section_ids:
            findings.append(
                _finding(
                    "P0",
                    "zh_core_section_missing",
                    section_id,
                    section_id,
                    "Render every required core section in the Chinese memo.",
                )
            )
            continue
        section_body = _section_body_text(zh_shape, section_id)
        if not CJK_RE.search(section_body):
            findings.append(
                _finding(
                    "P0",
                    "zh_core_section_no_cjk_body",
                    section_id,
                    _snippet(section_body or section_id),
                    "Use native Chinese body text in each required core section.",
                )
            )

    if "sources" in en_shape.section_ids and "sources" not in zh_shape.section_ids:
        findings.append(
            _finding(
                "P0",
                "zh_source_section_missing",
                "sources",
                "sources",
                "Include the Chinese sources and fact-reference section.",
            )
        )

    if en_shape.table_count != zh_shape.table_count:
        findings.append(
            _finding(
                "P0",
                "table_count_mismatch",
                "document",
                f"en={en_shape.table_count}, zh={zh_shape.table_count}",
                "Keep tables and callouts structurally aligned across languages.",
            )
        )

    if en_shape.callout_like_table_count != zh_shape.callout_like_table_count:
        findings.append(
            _finding(
                "P1",
                "callout_count_mismatch",
                "document",
                (
                    f"en={en_shape.callout_like_table_count}, "
                    f"zh={zh_shape.callout_like_table_count}"
                ),
                "Check that Chinese callouts match the English memo.",
            )
        )

    if _paragraph_count_out_of_range(en_shape.paragraph_count, zh_shape.paragraph_count):
        findings.append(
            _finding(
                "P1",
                "paragraph_count_out_of_range",
                "document",
                f"en={en_shape.paragraph_count}, zh={zh_shape.paragraph_count}",
                "Review whether Chinese prose was collapsed or expanded excessively.",
            )
        )

    zh_body = _non_source_body_text(zh_shape)
    if zh_body and _cjk_ratio(zh_body) < 0.25:
        findings.append(
            _finding(
                "P1",
                "low_cjk_ratio",
                "document",
                f"cjk_ratio={_cjk_ratio(zh_body):.2f}",
                "Review the Chinese memo for English-heavy body prose.",
            )
        )

    for block in zh_shape.blocks:
        if block.kind == "heading" or block.section_id == "sources":
            continue
        if _large_english_only_block(block.text):
            findings.append(
                _finding(
                    "P1",
                    "english_only_body_prose",
                    block.location,
                    _snippet(block.text),
                    "Translate body prose into professional Chinese.",
                )
            )
        for pattern in TRANSLATIONESE_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        "P1",
                        "literal_prompt_scaffold",
                        block.location,
                        _snippet(block.text, match.group(0)),
                        "Rewrite prompt scaffolding as investor-facing Chinese.",
                    )
                )
                break

    return _dedupe_findings(findings)


def _section_id_from_heading(
    text: str,
    locale: str,
    patterns: dict | None = None,
) -> str | None:
    for section_id, locale_patterns in (patterns or SECTION_PATTERNS).items():
        if locale_patterns[locale].search(text):
            return section_id
    return None


def _section_body_text(shape: _DocShape, section_id: str) -> str:
    return " ".join(
        block.text
        for block in shape.blocks
        if block.section_id == section_id and block.kind != "heading"
    )


def _non_source_body_text(shape: _DocShape) -> str:
    return " ".join(
        block.text
        for block in shape.blocks
        if block.section_id not in {"front_matter", "sources"}
        and block.kind != "heading"
    )


def _paragraph_count_out_of_range(en_count: int, zh_count: int) -> bool:
    if en_count <= 0 or zh_count <= 0:
        return True
    return zh_count < max(1, int(en_count * 0.65)) or zh_count > int(en_count * 1.6) + 2


def _cjk_ratio(text: str) -> float:
    countable = COUNTABLE_RE.findall(text)
    if not countable:
        return 0.0
    return len(CJK_RE.findall(text)) / len(countable)


def _large_english_only_block(text: str) -> bool:
    if CJK_RE.search(text):
        return False
    return len(text) >= 80 and len(LATIN_RE.findall(text)) >= 45


def english_left_untranslated(text: str) -> bool:
    """True when this string is Chinese-slot prose that never got translated.

    The same rule the rendered-document gate reports as
    ``english_only_body_prose``, exposed so the package pipeline can catch
    it while there is still something to do about it. Deliberately
    conservative — a zh half that is a number, a ticker or a proper noun
    carries no CJK either and is correct as it stands.
    """
    return _large_english_only_block(text)


def _finding(
    severity: str,
    code: str,
    location: str,
    snippet: str,
    suggestion: str,
) -> ChineseParityFinding:
    return ChineseParityFinding(
        severity=severity,
        code=code,
        location=location,
        snippet=snippet,
        suggestion=suggestion,
    )


def _snippet(text: str, match_text: str | None = None, *, radius: int = 100) -> str:
    clean = _clean_text(text)
    if not match_text:
        return clean[: radius * 2].strip()
    index = clean.find(match_text)
    if index < 0:
        return clean[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(clean), index + len(match_text) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}".strip()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_findings(
    findings: list[ChineseParityFinding],
) -> list[ChineseParityFinding]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ChineseParityFinding] = []
    for finding in findings:
        key = (finding.code, finding.location, finding.snippet)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Lint English/Chinese generated memo DOCX parity."
    )
    parser.add_argument("english_docx", type=Path)
    parser.add_argument("chinese_docx", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    parity_result = lint_chinese_memo_pair(args.english_docx, args.chinese_docx)
    if args.markdown:
        print(render_markdown_report(parity_result))
    else:
        print(json.dumps(parity_result.to_dict(), indent=2, ensure_ascii=False))
    raise SystemExit(1 if parity_result.has_blocking_findings else 0)
