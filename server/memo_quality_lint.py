"""Quality gate for generated investment memo DOCX files.

The memo skill may keep detailed source provenance in analysis artifacts and
in a dedicated source/fact index. The final memo body and operating tables
should not expose those internal tokens.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from server import memo_structure
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
    # Lets the disclosure-gap check see implication supplied in a sibling cell —
    # e.g. a "Value: Not disclosed" cell whose "Note" cell carries the risk.
    row_text: str = ""


_BRACKET_RE = re.compile(r"\[[^\[\]\n]{1,100}\]")
_CITATION_TOKEN_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]")
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
_GAP_PHRASE_RE = re.compile(r"\bnot disclosed\b|\bnot computable\b", re.IGNORECASE)
_GAP_NOISE_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "to",
    "of",
    "or",
    "and",
    "for",
    "any",
    "period",
    "value",
    "metric",
    "n",
    "a",
    "na",
    "none",
    "unknown",
    "tbd",
}
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
    # A copied packet label is "Confidence: High" — the label plus a
    # rating. Bare "confidence:" fires on ordinary prose punctuation
    # ("...with much confidence: at $2T the...") and survived THREE
    # repair attempts in a live run because no rewording removes a colon
    # the writer cannot see as the trigger.
    re.compile(
        r"\bConfidence\s*:\s*(?:very\s+)?(?:high|medium|moderate|low|\d)",
        re.IGNORECASE,
    ),
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
# The memo's conclusion is a recommendation — no decision exists when it is
# written. Decided-action constructions are banned, EXCEPT inside a sentence
# recording an actual past decision (the pinned decision-history sentence
# "BSH made the decision to ... on ... because ...", whose user-entered
# reason may itself contain decided phrasing). The exemption is
# sentence-scoped and keyed on the history markers, which the pin template
# guarantees are present in the one legitimate sentence.
_DECIDED_LANGUAGE_PATTERNS = (
    re.compile(
        r"\bBSH is (?:committing|investing|participating)\b", re.IGNORECASE
    ),
    re.compile(
        r"\bBSH is not (?:committing|investing|participating)\b",
        re.IGNORECASE,
    ),
)
_DECISION_HISTORY_SENTENCE_PATTERN = re.compile(
    r"[^.!?]*(?:\bmade the decision\b|\bdecided (?:on|to)\b)[^.!?]*[.!?]?",
    re.IGNORECASE,
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
    re.compile(r"\bwe are being offered\b", re.IGNORECASE),
    re.compile(r"\bwe are participating through\b", re.IGNORECASE),
    re.compile(r"\bwe recommend participating\b", re.IGNORECASE),
    re.compile(r"\bwe give credit to\b", re.IGNORECASE),
    re.compile(r"\bour base case credits\b", re.IGNORECASE),
    re.compile(r"\bour base case gives credit\b", re.IGNORECASE),
    re.compile(r"\bthe investment case rests on\b", re.IGNORECASE),
    re.compile(r"\bthe investment case uses\b", re.IGNORECASE),
    re.compile(r"\bthe investment case treats\b", re.IGNORECASE),
    re.compile(r"\bthe investment case assumes\b", re.IGNORECASE),
    re.compile(r"\bthe investment case identifies\b", re.IGNORECASE),
    re.compile(r"\bthe investment case gives credit\b", re.IGNORECASE),
    re.compile(r"\bvaluation-support factor\b", re.IGNORECASE),
    re.compile(r"\bvaluation support is strongest\b", re.IGNORECASE),
    re.compile(r"\brather than treating\b", re.IGNORECASE),
    re.compile(r"\bkey risk centers on\b", re.IGNORECASE),
    re.compile(r"\bis compelling because\b", re.IGNORECASE),
    re.compile(r"\bavailable evidence does not document\b", re.IGNORECASE),
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
    # Deal-context underwriting only: "we underwrite", "the underwriting
    # case/posture". The bare profession noun ("insurance underwriters
    # use the product") is legitimate domain content — the blanket ban
    # locked a live Anthropic run in an unfixable repair loop
    # (2026-09-11: customer-evidence prose about underwriters).
    re.compile(
        r"\b(?:we|bsh)\s+underwrit(?:e|es|ing|ten)\b"
        r"|\bunderwriting\s+(?:case|view|posture|assumption|basis|lens)\b",
        re.IGNORECASE,
    ),
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
    # Scaffold references only ("This section examines...", "in this
    # section, we..."): the answer-first register legitimately writes
    # "the strongest number in the section" and "every other risk in
    # this section works through that channel" — both burned repair
    # cycles in a live full run.
    re.compile(
        r"\b(?:the|this) section,?\s+(?:we|will|discusses|examines|covers|"
        r"outlines|reviews|summari[sz]es|analy[sz]es|addresses|turns|"
        r"presents|explores)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bour section\b", re.IGNORECASE),
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
_RISK_GENERIC_WATCH_RE = re.compile(
    r"^\s*(?:monitor|track|watch|confirm|request|obtain|"
    r"cross[- ]check|verify|require|ensure|validate|ask for)\b",
    re.IGNORECASE,
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
_RISK_GENERIC_FILLER_PATTERNS = (
    re.compile(r"\bcompetition is a risk\b", re.IGNORECASE),
    re.compile(r"\bexecution could be difficult\b", re.IGNORECASE),
    re.compile(r"\bmarket conditions may change\b", re.IGNORECASE),
    re.compile(r"\bthere are risks?\b", re.IGNORECASE),
    re.compile(r"\bthe company faces risks?\b", re.IGNORECASE),
)
_RISK_UNSUPPORTED_CLAIM_RE = re.compile(
    r"\b(?:guaranteed|certain to|will definitely|cannot fail|"
    r"no competitor can)\b",
    re.IGNORECASE,
)
_BODY_TREATMENT_SPEAK_PATTERNS = (
    re.compile(r"\bsource class\b", re.IGNORECASE),
    re.compile(r"\bmodel treatment\b", re.IGNORECASE),
)

# The mandatory legal-disclosure sentence necessarily says "this document"
# — the renderer's `disclosures` component REQUIRES this language, so the
# meta-language gate must not fight it (it forced a surgical-repair round
# on both 2026-08-28 benchmark runs). Markers mirror the renderer's
# disclosures-component coverage patterns in memo_docx_renderer.
_DISCLOSURE_LANGUAGE_PATTERNS = (
    re.compile(r"\bnot an offer to (?:sell|purchase)\b", re.IGNORECASE),
    re.compile(r"\boffer to sell securities\b", re.IGNORECASE),
    re.compile(r"\bdefinitive subscription documents\b", re.IGNORECASE),
    re.compile(r"\baccredited investors\b", re.IGNORECASE),
    re.compile(r"\bpartial or total loss\b", re.IGNORECASE),
)


def lint_memo_docx(
    path: str | Path,
    structure: memo_structure.MemoStructure | None = None,
) -> MemoLintResult:
    """Lint one generated memo DOCX and return structured findings.

    ``structure`` names the report structure the memo was rendered
    against (heading recognizers, the risk section key); default late v1."""
    structure = structure or memo_structure.LATE
    docx_path = Path(path)
    try:
        blocks = _extract_docx_blocks(docx_path, structure)
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
    return MemoLintResult(
        path=str(docx_path), findings=_lint_blocks(blocks, structure)
    )


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


def _extract_docx_blocks(
    path: Path,
    structure: memo_structure.MemoStructure | None = None,
) -> list[_TextBlock]:
    structure = structure or memo_structure.LATE
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
            section = _section_after_heading(text, section, structure)
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


def _lint_blocks(
    blocks: list[_TextBlock],
    structure: memo_structure.MemoStructure | None = None,
) -> list[MemoLintFinding]:
    structure = structure or memo_structure.LATE
    risk_section_key = structure.numbered_lint_key("risk")
    findings: list[MemoLintFinding] = []
    # Structure-v2 memos cite sources and calculation notes inline as
    # [S3] / [C2] (rendered as links); v1 memos keep ids in the index.
    citations_allowed = bool(structure.scorecard_weights())
    for block in blocks:
        if not block.allowed_trace_section:
            for match in _BRACKET_RE.finditer(block.text):
                if citations_allowed and _CITATION_TOKEN_RE.fullmatch(
                    match.group(0)
                ):
                    continue
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
                                "index and name the person, contract, or "
                                "publication in the body."
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

        # The Sources index describes how each source shaped the memo —
        # "which is why the recommendation is capped at..." is treatment
        # language there, not body voice (two live source cells burned a
        # repair cycle on exactly that).
        for pattern in (
            () if block.allowed_trace_section else _SELL_SIDE_BANNED_PATTERNS
        ):
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "sell_side_voice_violation",
                        match.group(0),
                        (
                            "Rewrite buyer-side, detached, treatment-speak, or "
                            "stock participation slogans as LP co-invest "
                            "English: firm as subject, named terms, plain risks."
                        ),
                    )
                )
                break

        decided_scope = _DECISION_HISTORY_SENTENCE_PATTERN.sub(" ", block.text)
        for pattern in _DECIDED_LANGUAGE_PATTERNS:
            match = pattern.search(decided_scope)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "decided_voice_violation",
                        match.group(0),
                        (
                            "The memo's conclusion is a recommendation, not a "
                            "decision: write 'Recommendation: BSH commits ...' "
                            "or 'Recommendation: pass on ...'. Decided "
                            "language is allowed only in the pinned "
                            "decision-history sentence."
                        ),
                    )
                )
                break

        block_is_disclosure_language = any(
            pattern.search(block.text)
            for pattern in _DISCLOSURE_LANGUAGE_PATTERNS
        )
        if not block_is_disclosure_language:
            for pattern in _META_LANGUAGE_PATTERNS:
                match = pattern.search(block.text)
                if not match:
                    continue
                # The Sources / Fact Reference Index and validation
                # appendix describe the memo's own sourcing by definition —
                # article and demonstrative references ("the memo
                # carries…", "figures in this memo", "the registry fields
                # are not used") are treatment language there, not process
                # leakage; the sources contract itself asks how "the memo
                # weighs and uses this source". Possessive/process forms
                # ("our analysis", "we will outline") stay banned
                # everywhere — a live compact run lost a full regeneration
                # cycle to "in this memo" flagged inside the sources table.
                if block.allowed_trace_section and match.group(0).lower().startswith(
                    ("the ", "this ")
                ):
                    continue
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "meta_process_language",
                        match.group(0),
                        (
                            "Delete the self-reference and keep the "
                            "judgment: \"every multiple in this memo\" -> "
                            "\"every multiple we use\"; \"the margin risk "
                            "that carries this memo\" -> \"the margin risk "
                            "that carries the investment case\"; \"What the "
                            "gap costs the analysis\" -> \"What the gap "
                            "costs us\". Never name the memo, the analysis, "
                            "the document, the framework or the section — "
                            "name the investment instead. Table headers and "
                            "table cells count."
                        ),
                    )
                )
                break

        if not block.allowed_trace_section:
            for pattern in _BODY_TREATMENT_SPEAK_PATTERNS:
                match = pattern.search(block.text)
                if match:
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            "sell_side_voice_violation",
                            match.group(0),
                            (
                                "Name the person, contract, or publication. "
                                "Put source class in the fact index."
                            ),
                        )
                    )
                    break

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
                        "A bare 'Not disclosed' cell is unfinished. Add the "
                        "implication in the same cell or the note cell: "
                        "'Revenue is not disclosed. $3.0B is high relative "
                        "to disclosed commercial proof.'"
                    ),
                )
            )

    risk_headings: dict[str, _TextBlock] = {}
    for index, block in enumerate(blocks):
        if block.section != risk_section_key:
            continue
        for pattern in _RISK_GENERIC_FILLER_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "generic_risk_filler",
                        match.group(0),
                        "Replace generic risk language with a named fact, failure mode, and consequence.",
                    )
                )
        match = _RISK_UNSUPPORTED_CLAIM_RE.search(block.text)
        if match:
            findings.append(
                _finding(
                    block,
                    "P0",
                    "unsupported_risk_claim",
                    match.group(0),
                    "State the evidence behind the risk or qualify it as an inference.",
                )
            )
        if block.kind == "paragraph" and re.match(
            r"^\s*risk\s+\d+\s*[:：]\s*\S", block.text, re.IGNORECASE
        ):
            summary = block.text.split(":", 1)[-1].strip()
            normalized = re.sub(r"[^a-z0-9]+", " ", summary.lower()).strip()
            if summary.lower().strip(" .") in _RISK_GENERIC_HEADINGS:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "generic_risk_heading",
                        summary,
                        "Name the concrete failure mode, not only the risk category.",
                    )
                )
            if normalized in risk_headings:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "duplicate_risk_card",
                        summary,
                        "Combine duplicate risks or distinguish their failure modes.",
                    )
                )
            else:
                risk_headings[normalized] = block
        if (
            block.kind == "table_cell"
            and block.text.lower().strip() == "what we watch"
            and index + 1 < len(blocks)
        ):
            watch = blocks[index + 1]
            if watch.section == block.section and _RISK_GENERIC_WATCH_RE.match(
                watch.text
            ):
                findings.append(
                    _finding(
                        watch,
                        "P0",
                        "risk_watch_checklist",
                        watch.text,
                        "Name an observable operating or transaction signal, not a confirmation command.",
                    )
                )

    return _dedupe_findings(findings)


def _section_after_heading(
    text: str,
    current: str,
    structure: memo_structure.MemoStructure | None = None,
) -> str:
    structure = structure or memo_structure.LATE
    lowered = text.strip().lower()
    if _allowed_trace_section(lowered):
        return lowered
    if len(text) <= 140 and (
        structure.numbered_prefix_pattern().match(lowered)
        or lowered in structure.lint_section_titles()
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


def _substance_remainder(text: str) -> str:
    remainder = _GAP_PHRASE_RE.sub(" ", text.lower())
    remainder = re.sub(r"[^a-z0-9$]+", " ", remainder)
    words = [word for word in remainder.split() if word not in _GAP_NOISE_WORDS]
    return " ".join(words)


def _unresolved_disclosure_gap(text: str, row_text: str = "") -> bool:
    cell = text.lower().strip()
    if not _GAP_PHRASE_RE.search(cell):
        return False
    if _substance_remainder(cell):
        return False
    if not row_text:
        return True
    row_without_cell = row_text.lower().replace(cell, " ", 1)
    return len(_substance_remainder(row_without_cell)) < 20


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
