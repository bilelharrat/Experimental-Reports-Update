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
    # Full text of the table row this cell belongs to (empty for paragraphs).
    # Lets the disclosure-gap check see treatment supplied in a sibling cell —
    # e.g. a "Value: Not disclosed" cell whose "Note" cell carries the
    # diligence treatment in the same row.
    row_text: str = ""


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
    "sensitivity",
    "valuation",
    "risk",
    "scenario",
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
    # Analytical characterizations that themselves treat an undisclosed figure
    # (e.g. a valuation step-table whose multiple column reads "undefined (no
    # denominator)" or "forward, not yet closed").
    "undefined",
    "denominator",
    "forward",
    "aspirational",
    "outside-in",
    "not yet closed",
    "unconfirmed",
    # An explicit "not computable" determination (with its cause) is itself
    # analytical handling, not a bare blank — treat it as resolved even though
    # the same phrase is one of the gap triggers.
    "not computable",
    # Morphological stems for treatment verbs writers actually use. Three
    # consecutive Tenstorrent runs (2026-08-18/20/21) burned 10-18 minute
    # full-package retries on cells that DID treat the gap but phrased it as
    # "our downside case assumes ..." or "we value the team ... and take a
    # discount" — forms the exact-word list above never matched.
    "assum",
    "downside",
    "haircut",
    "discount",
    "we value",
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
_PACKET_PROCESS_LABEL_PATTERNS = (
    re.compile(r"\bPrompt\s*:", re.IGNORECASE),
    re.compile(r"\bDesign prompt\b", re.IGNORECASE),
    re.compile(r"\bReviewer prompts?\b", re.IGNORECASE),
    re.compile(r"\bNarrative reviewer prompts?\b", re.IGNORECASE),
    re.compile(r"\bConfidence\s*:", re.IGNORECASE),
    re.compile(r"\bSource traces?\b", re.IGNORECASE),
    re.compile(r"\bsource[-_ ]trace notes?\b", re.IGNORECASE),
    re.compile(r"\bNo-go\b", re.IGNORECASE),
    re.compile(r"\bprohibited visual\b", re.IGNORECASE),
    re.compile(r"\bMust-prove\b", re.IGNORECASE),
    re.compile(r"\bBenchmark gaps?\b", re.IGNORECASE),
    re.compile(r"\bReadiness Reviews?\b", re.IGNORECASE),
    re.compile(r"\bWaivers?\b", re.IGNORECASE),
    re.compile(r"\bMemo Uses?\b", re.IGNORECASE),
    re.compile(r"\bPre-Mortem\b", re.IGNORECASE),
    re.compile(r"\bReverse IC\b", re.IGNORECASE),
    re.compile(r"\bValidation\s*&\s*Assumptions Log\b", re.IGNORECASE),
    re.compile(r"\bsupport thresholds?\b", re.IGNORECASE),
    re.compile(r"\bconfirmation evidence\b", re.IGNORECASE),
    re.compile(r"\btop\s+gating\s+questions\b", re.IGNORECASE),
)
_FUZZY_PATTERNS = (
    re.compile(r"\bsoft instrument\b", re.IGNORECASE),
    re.compile(r"\bhard IP wall\b", re.IGNORECASE),
    re.compile(r"\bmoat narrows\b", re.IGNORECASE),
    re.compile(r"\bno-rights SAFE\b", re.IGNORECASE),
    re.compile(r"\bwhere nothing else works\b", re.IGNORECASE),
    re.compile(r"\bleast-proven part of the story\b", re.IGNORECASE),
)
_SELL_SIDE_BANNED_PATTERNS = (
    re.compile(
        r"\bthe recommendation (?:is|should|would|must|remain|remains)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bthe current recommendation posture\b", re.IGNORECASE),
    re.compile(r"\bthe right posture is\b", re.IGNORECASE),
    re.compile(r"\bthe opportunity offered to investors is\b", re.IGNORECASE),
    re.compile(r"\bthe base case credits\b", re.IGNORECASE),
    re.compile(r"\bthe investment view is\b", re.IGNORECASE),
    re.compile(r"\bwe invest behind\b", re.IGNORECASE),
    re.compile(r"\bwe back\b(?!-)", re.IGNORECASE),
    re.compile(r"\bwe want exposure\b", re.IGNORECASE),
    re.compile(r"\bwhy we want exposure\b", re.IGNORECASE),
    re.compile(r"\bcontrol layer underneath\b", re.IGNORECASE),
    re.compile(r"\bonly scaled platform\b", re.IGNORECASE),
    re.compile(r"\bas framed\b", re.IGNORECASE),
    re.compile(r"\bframed (?:A2|terms|economics|round)\b", re.IGNORECASE),
    re.compile(r"\bon the framed\b", re.IGNORECASE),
    re.compile(r"\bdecision posture\b", re.IGNORECASE),
    re.compile(r"\brecommendation posture\b", re.IGNORECASE),
    re.compile(r"\bopen questions\b", re.IGNORECASE),
    re.compile(r"\btop\s+3\s+(?:decision|gating)\s+questions\b", re.IGNORECASE),
    re.compile(r"\(for BSH\)", re.IGNORECASE),
    re.compile(r"\bunderwrit(?:e|es|ing|ten|er|ers)\b", re.IGNORECASE),
    re.compile(r"\btickets?\b", re.IGNORECASE),
    re.compile(r"\bBSH target allocation\b", re.IGNORECASE),
    re.compile(r"\btarget allocation\b", re.IGNORECASE),
    re.compile(r"\bposition size\b", re.IGNORECASE),
    re.compile(r"\bBSH should\b", re.IGNORECASE),
    re.compile(r"\bwhat BSH should do\b", re.IGNORECASE),
    re.compile(r"\bkill criteria\b", re.IGNORECASE),
    re.compile(r"\bNeed More Information\b", re.IGNORECASE),
    re.compile(r"\bConditional Yes\b", re.IGNORECASE),
    re.compile(r"\bProceed if confirmed\b", re.IGNORECASE),
    re.compile(r"\bHold pending confirmation\b", re.IGNORECASE),
    re.compile(r"\bwe proceed once\b", re.IGNORECASE),
    re.compile(r"\bwe would proceed if\b", re.IGNORECASE),
    re.compile(r"\bwe would revisit if\b", re.IGNORECASE),
    re.compile(r"\bwe recommend proceeding if\b", re.IGNORECASE),
    re.compile(r"\bwe recommend proceeding once\b", re.IGNORECASE),
    re.compile(r"\bproceed only after\b", re.IGNORECASE),
    re.compile(r"\b(?:proceed|participate|recommend)[^.]{0,80}\bsubject to\b", re.IGNORECASE),
    re.compile(r"\bClosing Confirmations?\b", re.IGNORECASE),
    re.compile(r"\bClosing Confirmation Bars?\b", re.IGNORECASE),
    re.compile(r"\bWhat Must Be Confirmed\b", re.IGNORECASE),
    re.compile(r"\bConfirmation Items?\b", re.IGNORECASE),
    re.compile(r"\bExpected Bars?\b", re.IGNORECASE),
    re.compile(r"\bValuation Sensitivity Bars?\b", re.IGNORECASE),
    re.compile(r"\bInvestment Conditions?\b", re.IGNORECASE),
    re.compile(r"\bStop or Revisit Conditions?\b", re.IGNORECASE),
    re.compile(r"\bStop\s*/\s*Revisit Triggers?\b", re.IGNORECASE),
    re.compile(r"\bWhat Would Make Us Revisit\b", re.IGNORECASE),
    re.compile(r"\bImmediate Confirmation Work\b", re.IGNORECASE),
    re.compile(r"\bClosing bar\b", re.IGNORECASE),
    re.compile(r"^\s*Cross-check\b", re.IGNORECASE),
    re.compile(r"^\s*Source two\b", re.IGNORECASE),
    re.compile(r"^\s*Request\b", re.IGNORECASE),
    re.compile(r"^\s*Commission\b", re.IGNORECASE),
    re.compile(r"^\s*Patent counsel\b", re.IGNORECASE),
    re.compile(r"\binvestment conditions?\b", re.IGNORECASE),
    re.compile(r"\bconfirm before funding\b", re.IGNORECASE),
    re.compile(r"^\s*Confirm\b", re.IGNORECASE),
    re.compile(r"\bbefore signing subscription documents\b", re.IGNORECASE),
    re.compile(r"\bwe still need\b", re.IGNORECASE),
    re.compile(r"\bneed to confirm\b", re.IGNORECASE),
    re.compile(r"\brequire (?:the )?(?:split|signed-vs-MOU split)\b", re.IGNORECASE),
    re.compile(r"\bdiligence actions?\b", re.IGNORECASE),
    re.compile(r"\bDiligence Thresholds\b", re.IGNORECASE),
    re.compile(r"\bdiligence thresholds?\b", re.IGNORECASE),
    re.compile(r"\bNext Diligence Actions\b", re.IGNORECASE),
    re.compile(r"\bsupport thresholds?\b", re.IGNORECASE),
    re.compile(r"\bnamed institutional lead\b", re.IGNORECASE),
    re.compile(r"\bnamed lead\b", re.IGNORECASE),
    re.compile(r"\bdown-?round protection\b", re.IGNORECASE),
    re.compile(r"\bMFN\b"),
    re.compile(r"\binformation rights\b", re.IGNORECASE),
    re.compile(r"\bvoting rights\b", re.IGNORECASE),
    re.compile(r"\brequire data room\b", re.IGNORECASE),
    re.compile(r"\b(?:should|would|could|ought to) be able to\b", re.IGNORECASE),
    re.compile(r"\bshould be closeable\b", re.IGNORECASE),
    re.compile(r"\brealistically obtainable\b", re.IGNORECASE),
    re.compile(r"\bbefore BSH funds\b", re.IGNORECASE),
    re.compile(r"\bkeep (?:the )?(?:position|allocation|check|ticket) small\b", re.IGNORECASE),
    re.compile(r"\blate-stage financial-return exception\b", re.IGNORECASE),
    re.compile(r"\bfinancial-return exception\b", re.IGNORECASE),
    re.compile(r"\bthesis-fit exception", re.IGNORECASE),
    re.compile(r"\bBSH preference\b", re.IGNORECASE),
    re.compile(r"\bAsian-immigrant\b", re.IGNORECASE),
    re.compile(r"\bAsian ethnicity preferred\b", re.IGNORECASE),
    re.compile(r"\bimmigrant background founders\b", re.IGNORECASE),
    re.compile(r"\bpaper-mark outcome\b", re.IGNORECASE),
    re.compile(r"\bflat-to-modest carry\b", re.IGNORECASE),
)
_META_LANGUAGE_PATTERNS = (
    re.compile(r"\b(?:the|this|our) memo\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) analysis\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) framework\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) section\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) document\b", re.IGNORECASE),
    re.compile(r"\bmemo language was\b", re.IGNORECASE),
    re.compile(r"\bthe sponsor (?:itself )?(?:implies|frames|flags)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:the )?sponsor (?:itself |explicitly )?(?:acknowledges|discloses)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\binside the memo\b", re.IGNORECASE),
    re.compile(r"\bsource material\b", re.IGNORECASE),
    re.compile(r"\bembedded in the registry\b", re.IGNORECASE),
    re.compile(r"\bthe registry\b", re.IGNORECASE),
    re.compile(
        r"\bwe (?:will )?(?:outline|discuss|summari[sz]e|cover|frame|review|walk through)\b",
        re.IGNORECASE,
    ),
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
                row_text = _clean_text(
                    " ".join(cell.text for cell in row.cells)
                )
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
                            row_text=row_text,
                        )
                    )
    return blocks


def _lint_blocks(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    findings: list[MemoLintFinding] = []
    for block in blocks:
        if not block.allowed_trace_section:
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
                                "Move detailed source IDs to the fact reference "
                                "index and use source-class language here."
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
                                "Remove internal file or artifact names from the "
                                "body and operating tables."
                            ),
                        )
                    )

            for pattern in _PACKET_PROCESS_LABEL_PATTERNS:
                match = pattern.search(block.text)
                if match:
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            "packet_process_label",
                            match.group(0),
                            (
                                "Convert copied packet or review labels into "
                                "investor-facing evidence, source-treatment, "
                                "risk, or valuation language."
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

        for pattern in _SELL_SIDE_BANNED_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "sell_side_voice_violation",
                        match.group(0),
                        (
                            "Rewrite buyer-side, detached, or IC jargon as "
                            "first-person exec-ready sell-side investment "
                            "memo language."
                        ),
                    )
                )
                break

        for pattern in _META_LANGUAGE_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "meta_process_language",
                        match.group(0),
                        (
                            "Rewrite writer/process language as direct "
                            "investment judgment."
                        ),
                    )
                )
                break

        if not block.allowed_trace_section and "—" in block.text:
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

        if (
            not block.allowed_trace_section
            and _unresolved_disclosure_gap(block.text, block.row_text)
        ):
            findings.append(
                _finding(
                    block,
                    "P0",
                    "disclosure_gap_without_treatment",
                    "not disclosed",
                    (
                        "Pair missing disclosure with source class, model "
                        "treatment, conversion range, proxy, risk factor, or "
                        "valuation sensitivity."
                    ),
                )
            )

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


def _unresolved_disclosure_gap(text: str, row_text: str = "") -> bool:
    lowered = text.lower()
    if "not disclosed" not in lowered and "not computable" not in lowered:
        return False
    # A disclosure gap is treated when the same block — or, for a table cell,
    # any sibling cell in the same row — supplies a source class, model
    # treatment, proxy, risk factor, valuation sensitivity, or an explicit analytical
    # characterization of why the figure is absent.
    scope = f"{lowered} {row_text.lower()}".strip()
    return not any(term in scope for term in _MODEL_TREATMENT_TERMS)


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
