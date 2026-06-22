"""Quality gate for generated investment memo DOCX files.

The memo skill may keep detailed source provenance in analysis artifacts and
in a dedicated source/fact index. The final memo body and operating tables
should not expose those internal tokens.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class MemoLintFinding:
    severity: str
    code: str
    location: str
    snippet: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MemoLintResult:
    path: str
    findings: list[MemoLintFinding]

    @property
    def p0_findings(self) -> list[MemoLintFinding]:
        return [finding for finding in self.findings if finding.severity == "P0"]

    @property
    def has_blocking_findings(self) -> bool:
        return bool(self.p0_findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": "failed" if self.has_blocking_findings else "passed",
            "finding_count": len(self.findings),
            "p0_count": len(self.p0_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class _TextBlock:
    kind: str
    text: str
    location: str
    section: str
    allowed_trace_section: bool
    operating_table: bool


_BRACKET_RE = re.compile(r"\[[^\[\]\n]{1,100}\]")
_SOURCE_ID_RE = re.compile(r"s\d+(?:\s*[,;]\s*s\d+)*", re.IGNORECASE)
_SOURCE_BRACKET_KEYWORDS = (
    "wv",
    "spv",
    "memo",
    "companies.yaml",
    "internal",
    "source",
    "trace",
    "yaml",
    "claim",
    "packet",
)
_MODEL_TREATMENT_TERMS = (
    "model",
    "treat",
    "treatment",
    "conversion",
    "range",
    "proxy",
    "estimate",
    "fermi",
    "diligence",
    "threshold",
    "credit",
    "binding",
    "mou",
    "loi",
    "pipeline",
    "contracted",
    "contract",
    "recognized",
    "assumption",
    "sanity bridge",
    "what would change",
)
_ALLOWED_SECTION_PATTERNS = (
    re.compile(r"\bsources?\b.*\b(source classes?|fact reference index|references?)\b", re.IGNORECASE),
    re.compile(r"\bfact reference index\b", re.IGNORECASE),
    re.compile(r"\bvalidation\b.*\bassumptions?\b", re.IGNORECASE),
    re.compile(r"\bvalidation appendix\b", re.IGNORECASE),
)
_INTERNAL_ARTIFACT_PATTERNS = (
    re.compile(r"\bcompanies\.ya?ml\b", re.IGNORECASE),
    re.compile(r"\bmemo_packet(?:\.md)?\b", re.IGNORECASE),
    re.compile(r"\bsource_traces?\b", re.IGNORECASE),
    re.compile(r"\bclaim_register(?:\.md)?\b", re.IGNORECASE),
    re.compile(r"\bresearch_tasks?\b", re.IGNORECASE),
    re.compile(r"\breviewer_prompts?\b", re.IGNORECASE),
    re.compile(r"\bchart_specs?\b", re.IGNORECASE),
    re.compile(r"\binfographic_source_brief\b", re.IGNORECASE),
    re.compile(r"\bbenchmark_dashboard\b", re.IGNORECASE),
    re.compile(r"\bWV\b"),
)
_SCAFFOLD_PATTERNS = (
    re.compile(r"\bCritical Reality Check\b", re.IGNORECASE),
    re.compile(r"\bpresent-state\b", re.IGNORECASE),
    re.compile(r"\bupside-state\b", re.IGNORECASE),
    re.compile(r"\bupside-only\b", re.IGNORECASE),
    re.compile(r"\bStrongest independent support\b", re.IGNORECASE),
    re.compile(r"\bStrongest independent supporting facts\b", re.IGNORECASE),
    re.compile(r"\bStrongest disconfirming facts\b", re.IGNORECASE),
    re.compile(r"\bStill unproven\b", re.IGNORECASE),
    re.compile(r"\bAlready true\b.*\b(upside|today)\b", re.IGNORECASE),
)
_FUZZY_PATTERNS = (
    re.compile(r"\bsoft instrument\b", re.IGNORECASE),
    re.compile(r"\bhard IP wall\b", re.IGNORECASE),
    re.compile(r"\bmoat narrows\b", re.IGNORECASE),
    re.compile(r"\bno-rights SAFE\b", re.IGNORECASE),
    re.compile(r"\bwhere nothing else works\b", re.IGNORECASE),
    re.compile(r"\bleast-proven part of the story\b", re.IGNORECASE),
)
_META_LANGUAGE_PATTERNS = (
    re.compile(r"\bthe memo\b", re.IGNORECASE),
    re.compile(r"\bthe analysis\b", re.IGNORECASE),
    re.compile(r"\bthe framework\b", re.IGNORECASE),
    re.compile(r"\bthis section\b", re.IGNORECASE),
)


def lint_memo_docx(path: str | Path) -> MemoLintResult:
    """Lint one generated memo DOCX and return structured findings."""
    docx_path = Path(path)
    try:
        blocks = _extract_docx_blocks(docx_path)
    except Exception as exc:  # noqa: BLE001
        return MemoLintResult(
            path=str(docx_path),
            findings=[
                MemoLintFinding(
                    severity="P0",
                    code="docx_extract_error",
                    location="document",
                    snippet=f"{type(exc).__name__}: {exc}",
                    suggestion=(
                        "Generate a valid DOCX before marking the memo ready."
                    ),
                )
            ],
        )
    return MemoLintResult(path=str(docx_path), findings=_lint_blocks(blocks))


def render_markdown_report(result: MemoLintResult) -> str:
    """Render a compact human-readable lint artifact."""
    payload = result.to_dict()
    lines = [
        "# Memo Quality Lint",
        "",
        f"- source: `{payload['path']}`",
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


def _extract_docx_blocks(path: Path) -> list[_TextBlock]:
    from docx import Document  # type: ignore
    from docx.oxml.table import CT_Tbl  # type: ignore
    from docx.oxml.text.paragraph import CT_P  # type: ignore
    from docx.table import Table  # type: ignore
    from docx.text.paragraph import Paragraph  # type: ignore

    document = Document(path)
    blocks: list[_TextBlock] = []
    section = "front matter"
    paragraph_index = 0
    table_index = 0

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = _clean_text(paragraph.text)
            if not text:
                continue
            paragraph_index += 1
            section = _section_after_heading(text, section)
            allowed = _allowed_trace_section(section)
            blocks.append(
                _TextBlock(
                    kind="paragraph",
                    text=text,
                    location=f"paragraph {paragraph_index}",
                    section=section,
                    allowed_trace_section=allowed,
                    operating_table=False,
                )
            )
        elif isinstance(child, CT_Tbl):
            table_index += 1
            table = Table(child, document)
            allowed = _allowed_trace_section(section)
            for row_index, row in enumerate(table.rows, start=1):
                for col_index, cell in enumerate(row.cells, start=1):
                    text = _clean_text(cell.text)
                    if not text:
                        continue
                    blocks.append(
                        _TextBlock(
                            kind="table_cell",
                            text=text,
                            location=(
                                f"table {table_index} row {row_index} "
                                f"cell {col_index}"
                            ),
                            section=section,
                            allowed_trace_section=allowed,
                            operating_table=not allowed,
                        )
                    )
    return blocks


def _lint_blocks(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    findings: list[MemoLintFinding] = []
    for block in blocks:
        if block.allowed_trace_section:
            continue

        for match in _BRACKET_RE.finditer(block.text):
            if _source_like_bracket(match.group(0)):
                findings.append(
                    _finding(
                        block,
                        "P0",
                        (
                            "operating_table_source_token"
                            if block.operating_table
                            else "source_token_leak"
                        ),
                        match.group(0),
                        (
                            "Move detailed source IDs to the fact reference index "
                            "and use source-class language here."
                        ),
                    )
                )

        for pattern in _INTERNAL_ARTIFACT_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "internal_artifact_leak",
                        match.group(0),
                        (
                            "Remove internal file or artifact names from the body "
                            "and operating tables."
                        ),
                    )
                )

        for pattern in _SCAFFOLD_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "scaffold_label",
                        match.group(0),
                        "Rewrite prompt taxonomy as investor-facing prose.",
                    )
                )

        for pattern in _FUZZY_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "banned_fuzzy_phrase",
                        match.group(0),
                        "Replace clever shorthand with concrete deal mechanics.",
                    )
                )

        if "—" in block.text:
            findings.append(
                _finding(
                    block,
                    "P0",
                    "em_dash_bridge",
                    "—",
                    (
                        "Split the sentence, use a colon, or use concise "
                        "punctuation instead of em dash bridging."
                    ),
                )
            )

        if _unresolved_disclosure_gap(block.text):
            findings.append(
                _finding(
                    block,
                    "P0",
                    "disclosure_gap_without_treatment",
                    "not disclosed",
                    (
                        "Pair missing disclosure with source class, model "
                        "treatment, conversion range, proxy, or diligence threshold."
                    ),
                )
            )

        for pattern in _META_LANGUAGE_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P1",
                        "meta_language",
                        match.group(0),
                        "Rewrite process language as direct investment judgment.",
                    )
                )
                break
    return _dedupe_findings(findings)


def _section_after_heading(text: str, current: str) -> str:
    lowered = text.strip().lower()
    if _allowed_trace_section(lowered):
        return lowered
    if len(text) <= 140 and (
        re.match(r"^(i|ii|iii|iv|v|vi)\.\s+", lowered)
        or lowered in {
            "executive summary",
            "company overview",
            "investment highlights",
            "investment risk",
            "financial forecast & valuation",
            "financial forecast and valuation",
            "investment decision / closing view",
            "closing view",
            "investment decision",
            "key metrics snapshot",
            "sources",
            "references",
        }
    ):
        return lowered
    return current


def _allowed_trace_section(section: str) -> bool:
    return any(pattern.search(section or "") for pattern in _ALLOWED_SECTION_PATTERNS)


def _source_like_bracket(value: str) -> bool:
    inner = value.strip()[1:-1].strip()
    lowered = inner.lower()
    if _SOURCE_ID_RE.fullmatch(inner):
        return True
    return any(keyword in lowered for keyword in _SOURCE_BRACKET_KEYWORDS)


def _unresolved_disclosure_gap(text: str) -> bool:
    lowered = text.lower()
    if "not disclosed" not in lowered and "not computable" not in lowered:
        return False
    return not any(term in lowered for term in _MODEL_TREATMENT_TERMS)


def _finding(
    block: _TextBlock,
    severity: str,
    code: str,
    match_text: str,
    suggestion: str,
) -> MemoLintFinding:
    return MemoLintFinding(
        severity=severity,
        code=code,
        location=f"{block.location} ({block.section})",
        snippet=_snippet(block.text, match_text),
        suggestion=suggestion,
    )


def _snippet(text: str, match_text: str, *, radius: int = 100) -> str:
    clean = _clean_text(text)
    index = clean.lower().find(match_text.lower())
    if index < 0:
        return clean[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(clean), index + len(match_text) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}".strip()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_findings(findings: list[MemoLintFinding]) -> list[MemoLintFinding]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MemoLintFinding] = []
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

    parser = argparse.ArgumentParser(description="Lint generated memo DOCX output.")
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    lint_result = lint_memo_docx(args.docx_path)
    if args.markdown:
        print(render_markdown_report(lint_result))
    else:
        print(json.dumps(lint_result.to_dict(), indent=2, ensure_ascii=False))
    raise SystemExit(1 if lint_result.has_blocking_findings else 0)
