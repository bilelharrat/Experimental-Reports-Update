"""Chinese memo parity and fluency checks for rendered DOCX output."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
import json
import math
import re
from typing import Any, Iterable

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
    # (label, value, location) for each row of the cover-facts table
    # (Stage / Sector / Location / Round) on page one.
    cover_rows: list[tuple[str, str, str]] = field(default_factory=list)

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
    *,
    package: dict | None = None,
    run_dir: Path | str | None = None,
    glossary: list[dict] | None = None,
) -> ChineseParityResult:
    """Compare rendered English and Chinese memo DOCX files.

    ``structure`` names the report structure the pair was rendered
    against (section ids + heading patterns); default is late v1.

    ``package`` (optional, the memo package the pair was rendered from)
    makes the figure and untranslated-text checks compare each ``{en, zh}``
    string with its own translation instead of matching sections of the
    two documents — more precise, and it names the block.

    ``glossary`` (or ``run_dir``, whose ``logs/glossary.json`` is read —
    by default the run folder two levels above ``en_path``) is the run's
    frozen term list ``[{"en", "zh"}]``; with it the term-drift check
    runs (P1 ``term_drift``)."""
    structure = structure or memo_structure.LATE
    patterns = structure.parity_patterns()
    en_docx = Path(en_path)
    zh_docx = Path(zh_path)
    if glossary is None:
        glossary = load_run_glossary(
            Path(run_dir) if run_dir is not None else en_docx.parent.parent
        )
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
    try:
        findings += _content_findings(
            en_shape, zh_shape, structure, package, glossary=glossary
        )
    except Exception as exc:  # noqa: BLE001 — the added checks never fail the gate
        findings.append(
            _finding(
                "P2",
                "parity_content_check_error",
                "document",
                f"{type(exc).__name__}: {exc}",
                "The figure/translation comparison could not run; the structural checks above still apply.",
            )
        )
    return ChineseParityResult(
        en_path=str(en_docx),
        zh_path=str(zh_docx),
        findings=_dedupe_findings(findings),
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

    cover_rows: list[tuple[str, str, str]] = []

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            # Renderer-derived text (masthead and date line, contents list,
            # footnotes, legends) is not the model's prose; both languages
            # carry the same blocks.
            if memo_structure.is_derived_docx_element(child):
                continue
            paragraph = Paragraph(child, document)
            text = _clean_text(memo_structure.docx_paragraph_text(paragraph))
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
            # A derived table still counts toward the EN/ZH table parity
            # (both languages must carry it); its text is not re-checked.
            if memo_structure.is_derived_docx_element(child):
                continue
            if current_section == "front_matter" and _is_cover_table(table):
                for row_index, row in enumerate(table.rows, start=1):
                    cells = row.cells
                    cover_rows.append(
                        (
                            _clean_text(cells[0].text),
                            _clean_text(cells[1].text),
                            f"table {table_index} row {row_index} cell 2",
                        )
                    )
            for row_index, row in enumerate(table.rows, start=1):
                for col_index, cell in enumerate(row.cells, start=1):
                    text = _clean_text(memo_structure.docx_cell_text(cell))
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
        cover_rows=cover_rows,
    )


# The cover-facts labels the renderer prints on page one (and the older
# "Date" row), in both languages.
_COVER_LABELS = frozenset(
    {
        "Date", "Stage", "Sector", "Location", "Round",
        "日期", "阶段", "行业", "地点", "轮次",
    }
)


def _is_cover_table(table: Any) -> bool:
    rows = list(table.rows)
    if not rows or any(len(row.cells) != 2 for row in rows):
        return False
    return all(_clean_text(row.cells[0].text) in _COVER_LABELS for row in rows)


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
        else:
            left = embedded_english_sentence(block.text)
            if left:
                findings.append(
                    _finding(
                        "P1",
                        "english_sentence_in_chinese",
                        block.location,
                        _snippet(block.text, left[:60]),
                        "Translate the English sentence; keep English only for names and titles.",
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


# ---- figures, untranslated text, glossary --------------------------------------
#
# Report-only checks (P1/P2 — never P0: the numbers and wording are the
# model's, and a P0 would force a regeneration). P1 findings count toward
# the report's quality chip, so each check is built to stay quiet on a
# clean pair: figures are compared by value with one rounding step of
# tolerance, text only counts as untranslated when it carries ordinary
# English words, and every list is capped.

_NUMBER_FINDING_CAP = 3
_IDENTICAL_FINDING_CAP = 5

# Words a proper noun may carry in lower case ("Bank of America").
_NAME_PARTICLES = frozenset(
    {
        "a", "an", "and", "at", "by", "da", "de", "del", "der", "des", "di",
        "du", "e", "et", "for", "in", "la", "le", "of", "on", "the", "to",
        "van", "von", "vs", "y",
    }
)
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")
_URL_TEXT_RE = re.compile(
    r"https?://\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|gov|io|ai|cn|co|edu|uk|de|jp)\b",
    re.IGNORECASE,
)
_CITATION_TOKEN_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]")


def needs_translation(text: str) -> bool:
    """True when a Chinese-document string carries no CJK but ordinary
    English words — as opposed to a figure, a date, a ticker, an acronym, a
    URL or a proper noun ("San Francisco, CA", "iPhone 17", "Bank of
    America"), which a Chinese memo may print as they are."""
    clean = _URL_TEXT_RE.sub(" ", _CITATION_TOKEN_RE.sub(" ", str(text or "")))
    if CJK_RE.search(clean):
        return False
    for word in _LATIN_WORD_RE.findall(clean):
        if any(ch.isupper() for ch in word):
            continue
        if len(word) < 2 or word.lower() in _NAME_PARTICLES:
            continue
        return True
    return False


def _content_findings(
    en_shape: _DocShape,
    zh_shape: _DocShape,
    structure: memo_structure.MemoStructure | None,
    package: dict | None,
    *,
    glossary: list[dict] | None = None,
) -> list[ChineseParityFinding]:
    findings = _cover_findings(zh_shape)
    if isinstance(package, dict):
        findings += _package_identical_findings(package)
        findings += _package_number_findings(package)
        findings += untranslated_zh_lines(package, glossary=glossary)
        findings += glued_citation_findings(package)
        findings += glossary_term_drift(package, glossary)
    else:
        findings += _identical_block_findings(en_shape, zh_shape)
        findings += _number_findings(en_shape, zh_shape)
        findings += untranslated_zh_lines(zh_shape, glossary=glossary)
        findings += glued_citation_findings(zh_shape)
    findings += _glossary_findings(zh_shape, structure)
    return findings


# -- Latin-only lines, glued citation tags, run-glossary drift (2026-09-23) -----
#
# Three report-only checks from the ZaiNar Chinese memos: a scorecard
# label left in English at the head of a Chinese paragraph ("business
# model and unit economics — 7/10, adequate。..."), a source tag printed
# hard against the word before it ("软件SAM[C7]", "承诺[S1]"), and one
# English term rendered three ways in Chinese ("phase-based" as 分阶段 /
# 阶段式 / 按阶段) when the run had frozen a glossary.

_LATIN_LINE_CAP = 6
_GLUED_CAP = 5
_DRIFT_CAP = 6
_LEADING_LATIN_RE = re.compile(r"^[^\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_MONEY_TOKEN_RE = re.compile(
    r"(?:US)?[$€£¥]\s?\d[\d,.]*\s?(?:[KMBT]|bn|mn|million|billion|trillion)?\b",
    re.IGNORECASE,
)
_SC_TOKEN_RE = re.compile(r"\b[SC]\d+\b")
_GLUED_CITATION_RE = re.compile(
    r"(?:[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[A-Za-z0-9%$])"
    r"\[[SC]\d+(?:\s*,\s*[SC]\d+)*\]"
)
# The rendered document carries the id without brackets (a superscript
# link): "软件SAMC7", "承诺S1。".
_GLUED_BARE_CITATION_RE = re.compile(
    r"(?:[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[A-Za-z%$])"
    r"[SC]\d+(?:,[SC]\d+)*(?![A-Za-z0-9])"
)


def load_run_glossary(run_dir: Path | str | None) -> list[dict]:
    """``logs/glossary.json`` of a run as ``[{"en", "zh"}]`` — the list the
    translation froze (claude_runner.build_memo_glossary). [] when there
    is none, or it is unreadable; never raises."""
    if run_dir is None:
        return []
    path = Path(run_dir) / "logs" / "glossary.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("terms") or payload.get("glossary") or []
    out: list[dict] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        en = str(item.get("en") or "").strip()
        zh = str(item.get("zh") or "").strip()
        if en:
            out.append({"en": en, "zh": zh})
    return out


def _zh_units(source: Any) -> Iterable[tuple[str, str, str]]:
    """(location, en, zh) for every Chinese string to check: the package's
    ``{en, zh}`` pairs, or a Chinese document's body blocks (en empty)."""
    if isinstance(source, dict):
        for section_id, path, en, zh in _package_pairs(source):
            if section_id == "sources":
                continue
            yield f"{section_id} {path}", en, zh
        return
    for block in getattr(source, "blocks", None) or []:
        if block.kind == "heading" or block.section_id == "sources":
            continue
        yield block.location, "", block.text


def _strip_allowed_latin(text: str, glossary: list[dict] | None) -> str:
    """The Chinese string without the Latin a Chinese memo legitimately
    prints: citations, URLs, money figures, S#/C# ids, and the glossary's
    English terms (product names and the like)."""
    clean = _CITATION_TOKEN_RE.sub(" ", str(text or ""))
    clean = _URL_TEXT_RE.sub(" ", clean)
    clean = _MONEY_TOKEN_RE.sub(" ", clean)
    clean = _SC_TOKEN_RE.sub(" ", clean)
    for term in glossary or []:
        en = str(term.get("en") or "").strip()
        if len(en) >= 2:
            clean = re.sub(re.escape(en), " ", clean, flags=re.IGNORECASE)
    return clean


def untranslated_zh_lines(
    source: Any, *, glossary: list[dict] | None = None
) -> list[ChineseParityFinding]:
    """P1 ``zh_line_untranslated``: a Chinese cell or paragraph that is
    English prose (no CJK, ordinary lowercase words), or that opens with an
    English label of two or more ordinary words before its first Chinese
    character. Tickers, S#/C# ids, money figures, citations, URLs and the
    run glossary's English terms are allowed."""
    findings: list[ChineseParityFinding] = []
    total = 0
    for location, _en, zh in _zh_units(source):
        clean = _strip_allowed_latin(zh, glossary)
        if not clean.strip():
            continue
        if not CJK_RE.search(clean):
            if not needs_translation(clean):
                continue
            what = "English with no Chinese"
        else:
            lead = _LEADING_LATIN_RE.match(clean)
            head = lead.group(0) if lead else ""
            words = [
                word
                for word in _LATIN_WORD_RE.findall(head)
                if not any(ch.isupper() for ch in word) and word.lower() not in _NAME_PARTICLES
            ]
            if len(words) < 2 or not needs_translation(head):
                continue
            what = "an English label before the Chinese"
        total += 1
        if len(findings) < _LATIN_LINE_CAP:
            findings.append(
                _finding(
                    "P1",
                    "zh_line_untranslated",
                    location,
                    _snippet(zh),
                    f"Translate this line ({what}); a Chinese memo prints only "
                    "figures, tickers, ids and product names in Latin script.",
                )
            )
    if total > len(findings) and findings:
        findings[0] = _finding(
            findings[0].severity,
            findings[0].code,
            findings[0].location,
            findings[0].snippet,
            findings[0].suggestion + f" ({total} such lines in all)",
        )
    return findings


def glued_citation_findings(source: Any) -> list[ChineseParityFinding]:
    """P2 ``citation_glued``: a ``[S#]`` / ``[C#]`` tag printed hard against
    the character before it ("软件SAM[C7]", "承诺[S1]") — the memo renders
    the tag as a superscript, so the word and the id read as one token."""
    findings: list[ChineseParityFinding] = []
    total = 0
    pattern = _GLUED_CITATION_RE if isinstance(source, dict) else _GLUED_BARE_CITATION_RE
    for location, _en, zh in _zh_units(source):
        matches = list(pattern.finditer(zh))
        if not matches:
            continue
        total += len(matches)
        if len(findings) < _GLUED_CAP:
            findings.append(
                _finding(
                    "P2",
                    "citation_glued",
                    location,
                    _snippet(zh, matches[0].group(0), radius=40),
                    "Put a space (or the sentence's punctuation) between the word "
                    "and the source tag.",
                )
            )
    if total > len(findings) and findings:
        findings[0] = _finding(
            findings[0].severity,
            findings[0].code,
            findings[0].location,
            findings[0].snippet,
            findings[0].suggestion + f" ({total} glued tags in all)",
        )
    return findings


def glossary_term_drift(
    package: dict | None, glossary: list[dict] | None
) -> list[ChineseParityFinding]:
    """P1 ``term_drift``: an English term the run's glossary froze whose
    Chinese rendering is not the frozen one in some of the strings that
    use the term — more than one rendering of one term in one memo."""
    if not isinstance(package, dict) or not glossary:
        return []
    pairs = [
        (f"{section_id} {path}", en, zh)
        for section_id, path, en, zh in _package_pairs(package)
        if section_id != "sources"
    ]
    findings: list[ChineseParityFinding] = []
    for term in glossary:
        en = str(term.get("en") or "").strip()
        zh = str(term.get("zh") or "").strip()
        if len(en) < 2 or not zh:
            continue
        pattern = re.compile(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])", re.IGNORECASE)
        canonical = 0
        other: list[tuple[str, str]] = []
        for location, en_text, zh_text in pairs:
            if not pattern.search(en_text):
                continue
            if zh in zh_text or en.lower() in zh_text.lower():
                canonical += 1
            else:
                other.append((location, zh_text))
        if not other:
            continue
        location, zh_text = other[0]
        findings.append(
            _finding(
                "P1",
                "term_drift",
                location,
                _snippet(zh_text, radius=60),
                f"“{en}” is {zh} in this memo's glossary; {len(other)} of "
                f"{canonical + len(other)} strings that use the term render it "
                "another way. Use the glossary term everywhere.",
            )
        )
        if len(findings) >= _DRIFT_CAP:
            break
    return findings


def _capped(findings: list[ChineseParityFinding], cap: int) -> list[ChineseParityFinding]:
    if len(findings) <= cap:
        return findings
    from dataclasses import replace

    kept = findings[:cap]
    kept[-1] = replace(
        kept[-1], snippet=f"{kept[-1].snippet} (+{len(findings) - cap} more)"
    )
    return kept


def _cover_findings(zh_shape: _DocShape) -> list[ChineseParityFinding]:
    """Every cover-facts value in the Chinese memo, whatever its length: a
    value with no CJK that is more than a name, a figure or a ticker was
    never translated ("Late-stage / pre-IPO")."""
    findings = []
    for label, value, location in zh_shape.cover_rows:
        # A long English value is already english_only_body_prose.
        if value and needs_translation(value) and not _large_english_only_block(value):
            findings.append(
                _finding(
                    "P1",
                    "cover_field_untranslated",
                    location,
                    f"{label}: {value}",
                    "Write this cover field in Chinese; names, tickers and figures may stay as written.",
                )
            )
    return findings


def _identical_block_findings(
    en_shape: _DocShape, zh_shape: _DocShape
) -> list[ChineseParityFinding]:
    """A Chinese block identical to an English one that still needs
    translation, whatever its length (long ones are already
    english_only_body_prose)."""
    english = {block.text for block in en_shape.blocks if block.section_id != "sources"}
    findings = []
    for block in zh_shape.blocks:
        if block.section_id == "sources" or block.kind == "heading":
            continue
        if block.section_id == "front_matter" and block.kind == "table_cell":
            continue  # the cover facts: _cover_findings
        if block.text not in english or _large_english_only_block(block.text):
            continue
        if not needs_translation(block.text):
            continue
        findings.append(
            _finding(
                "P1",
                "zh_identical_to_en",
                block.location,
                _snippet(block.text),
                "Translate this text; the Chinese memo prints it exactly as the English does.",
            )
        )
    return _capped(findings, _IDENTICAL_FINDING_CAP)


def _package_pairs(package: dict) -> Iterable[tuple[str, str, str, str]]:
    """(section id, path, en, zh) for every filled {en, zh} string in the
    package's sections."""

    def walk(value: Any, path: str) -> Iterable[tuple[str, str, str]]:
        if isinstance(value, dict):
            if "en" in value and "zh" in value:
                en, zh = value.get("en"), value.get("zh")
                if isinstance(en, str) and isinstance(zh, str) and en.strip() and zh.strip():
                    yield path, en, zh
                return
            for key, item in value.items():
                yield from walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from walk(item, f"{path}[{index}]")

    for s_index, section in enumerate(package.get("sections") or []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or f"sections[{s_index}]")
        for path, en, zh in walk(section.get("blocks"), "blocks"):
            yield section_id, path, en, zh


def _package_identical_findings(package: dict) -> list[ChineseParityFinding]:
    findings = []
    for section_id, path, en, zh in _package_pairs(package):
        if en.strip() != zh.strip() or _large_english_only_block(_clean_text(zh)):
            continue
        if not needs_translation(zh):
            continue
        findings.append(
            _finding(
                "P1",
                "zh_identical_to_en",
                f"{section_id} {path}",
                _snippet(zh),
                "Translate this text; its Chinese half repeats the English.",
            )
        )
    return _capped(findings, _IDENTICAL_FINDING_CAP)


# -- figures ---------------------------------------------------------------------


@dataclass(frozen=True)
class _Figure:
    kind: str  # "money:USD" | "x" | "%"
    value: Decimal
    precision: Decimal  # the smallest step the writer expressed
    raw: str
    reportable: bool = True  # False for Chinese-numeral multiples (两倍)


_CURRENCY_CODES = {
    "$": "USD", "us$": "USD", "usd": "USD", "美元": "USD",
    "€": "EUR", "eur": "EUR", "欧元": "EUR",
    "£": "GBP", "gbp": "GBP", "英镑": "GBP",
    "¥": "CNY", "rmb": "CNY", "cny": "CNY", "人民币": "CNY", "元": "CNY", "元人民币": "CNY",
    "hk$": "HKD", "hkd": "HKD", "港元": "HKD", "港币": "HKD",
    "nt$": "TWD", "新台币": "TWD",
    "jpy": "JPY", "日元": "JPY",
    "a$": "AUD", "c$": "CAD", "s$": "SGD",
}
_EN_SCALES = {
    "k": 3, "thousand": 3, "m": 6, "mn": 6, "million": 6,
    "b": 9, "bn": 9, "billion": 9, "t": 12, "tn": 12, "trillion": 12,
}
_ZH_SCALES = {"千": 3, "万": 4, "百万": 6, "千万": 7, "亿": 8, "万亿": 12}

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CUR = r"US\$|HK\$|NT\$|A\$|C\$|S\$|\$|€|£|¥|(?:RMB|CNY|EUR|USD|GBP|JPY|HKD)\s?"
# English scale words, or a Chinese one after an English currency ("EUR 41.4 亿").
_SCALE = r"(?:\s?(?:trillion|billion|million|thousand|tn|bn|mn|[KMBT])(?![A-Za-z])|\s?(?:万亿|千万|百万|亿|万))"
# A range joins two figures: "8-12%", "$55–66B", "30 to 36 times", "8% 至 12%".
# A hyphen or dash counts only when it touches both numbers (or is a
# spaced en/em dash), so "FY2025 -16%" is a year and a figure, not a range.
_RANGE = r"(?:\s?(?:to|至|到|~|～)\s?|[-–—](?:to[-–—])?|\s[–—]\s)"
_ZH_CUR = r"元人民币|人民币|美元|欧元|英镑|日元|港元|港币|新台币|元"
_ZH_SCALE = r"万亿|千万|百万|亿|万"
_EN_MULTIPLE = r"(?:\s?[x×](?![A-Za-z0-9])|\s?倍)"
# "24 times revenue" is a multiple; "selected 17 to 18 times" is a count —
# so "N times" only ever confirms a figure, it is never reported alone.
_EN_TIMES = r"\stimes\b"

_MONEY_RANGE_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<cur>{_CUR})\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?{_RANGE}"
    rf"(?:{_CUR})?\s?(?P<b>{_NUM})(?P<sb>{_SCALE})?",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<cur>{_CUR})\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?",
    re.IGNORECASE,
)
_ZH_MONEY_RANGE_RE = re.compile(
    rf"(?P<a>{_NUM})\s*(?P<sa>{_ZH_SCALE})?\s*(?:[-–—~～]|至|到)\s*(?P<b>{_NUM})\s*(?P<sb>{_ZH_SCALE})?\s*(?P<cur>{_ZH_CUR})"
)
_ZH_MONEY_RE = re.compile(rf"(?P<a>{_NUM})\s*(?P<sa>{_ZH_SCALE})?\s*(?P<cur>{_ZH_CUR})")
# "340 亿、560 亿与 1100 亿美元": a scaled figure sharing a later currency.
_ZH_BARE_SCALED_RE = re.compile(rf"(?P<a>{_NUM})\s*(?P<sa>{_ZH_SCALE})")
_MULTIPLE_RANGE_RE = re.compile(
    rf"(?<![A-Za-z0-9.])(?P<a>\d+(?:\.\d+)?)(?:x|×)?{_RANGE}(?P<b>\d+(?:\.\d+)?)(?P<times>{_EN_TIMES})?"
    rf"(?(times)|{_EN_MULTIPLE})",
    re.IGNORECASE,
)
_MULTIPLE_RE = re.compile(
    rf"(?<![A-Za-z0-9.])(?P<a>\d+(?:\.\d+)?)(?:(?P<times>{_EN_TIMES})|{_EN_MULTIPLE})",
    re.IGNORECASE,
)
_WORD_MULTIPLE_RE = re.compile(
    r"\b(?:(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|hundred)"
    r"[- ]?(?:fold|times)|(?P<num>\d+)-fold)\b",
    re.IGNORECASE,
)
_ZH_NUMERAL_MULTIPLE_RE = re.compile(r"(?P<cn>[一二两三四五六七八九十百]+)\s*倍")
_PERCENT_RANGE_RE = re.compile(
    rf"(?P<a>\d+(?:\.\d+)?)[%％]?{_RANGE}(?P<b>\d+(?:\.\d+)?)\s?(?:[%％]|percent\b|per cent\b)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(?P<a>\d+(?:\.\d+)?)\s?(?:[%％]|percent\b|per cent\b)", re.IGNORECASE)
_FOLD_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "hundred": 100,
}
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _decimal(text: str) -> tuple[Decimal, int] | None:
    raw = str(text or "").replace(",", "").replace("−", "-")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
    return value, decimals


def _money(
    amount: str, scale: int, currency: str, raw: str, *, reportable: bool = True
) -> _Figure | None:
    parsed = _decimal(amount)
    if parsed is None:
        return None
    value, decimals = parsed
    token = currency.strip()
    code = "?" if token == "?" else _CURRENCY_CODES.get(
        token.lower(), _CURRENCY_CODES.get(token, "USD")
    )
    unit = Decimal(10) ** scale
    return _Figure(
        f"money:{code}", abs(value) * unit, Decimal(10) ** -decimals * unit, raw, reportable
    )


def _plain(kind: str, amount: str, raw: str, *, reportable: bool = True) -> _Figure | None:
    # Signs are not compared: "down 4.5%" and "-4.5%" say the same thing.
    parsed = _decimal(amount)
    if parsed is None:
        return None
    value, decimals = parsed
    return _Figure(kind, abs(value), Decimal(10) ** -decimals, raw, reportable)


def _cn_number(text: str) -> int | None:
    """Small Chinese numerals (两 = 2, 十二 = 12, 二十 = 20, 一百 = 100)."""
    if not text:
        return None
    if text.endswith("百") and len(text) <= 2:
        return _CN_DIGITS.get(text[0], 1) * 100 if len(text) == 2 else 100
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        units = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + units
    if len(text) == 1:
        return _CN_DIGITS.get(text)
    return None


def figures(text: str, *, chinese: bool = False) -> list[_Figure]:
    """The money, multiple and percentage figures in ``text``, each as a
    value with the precision it was written to. Dates, counts and plain
    numbers are left out — they are compared by eye, not by the gate.

    ``chinese`` marks the Chinese side, whose figures only ever confirm an
    English one: the check asks whether each English figure survived the
    translation. (Chinese legitimately restates "the high 50s" as "50% 后段"
    or "2x" as 两倍, so an unmatched Chinese figure is not evidence of an
    error; a changed one shows up as its unmatched English original.) Bare
    scaled Chinese figures ("340 亿" in a list that shares one "美元") count
    too."""
    remaining = _CITATION_TOKEN_RE.sub(" ", str(text or ""))
    found: list[_Figure] = []

    def take(pattern: re.Pattern, build) -> None:
        nonlocal remaining
        pieces = []
        last = 0
        for match in pattern.finditer(remaining):
            for figure in build(match):
                if figure is not None:
                    found.append(figure)
            pieces.append(remaining[last : match.start()])
            pieces.append(" " * (match.end() - match.start()))
            last = match.end()
        pieces.append(remaining[last:])
        remaining = "".join(pieces)

    def scale(value: str | None) -> int:
        word = str(value or "").strip()
        return _EN_SCALES.get(word.lower(), _ZH_SCALES.get(word, 0))

    take(
        _MONEY_RANGE_RE,
        lambda m: [
            _money(m["a"], scale(m["sa"] or m["sb"]), m["cur"], m.group(0)),
            _money(m["b"], scale(m["sb"] or m["sa"]), m["cur"], m.group(0)),
        ],
    )
    take(_MONEY_RE, lambda m: [_money(m["a"], scale(m["sa"]), m["cur"], m.group(0))])
    take(
        _ZH_MONEY_RANGE_RE,
        lambda m: [
            _money(m["a"], scale(m["sa"] or m["sb"]), m["cur"], m.group(0)),
            _money(m["b"], scale(m["sb"]), m["cur"], m.group(0)),
        ],
    )
    take(_ZH_MONEY_RE, lambda m: [_money(m["a"], scale(m["sa"]), m["cur"], m.group(0))])
    if chinese:
        take(
            _ZH_BARE_SCALED_RE,
            lambda m: [_money(m["a"], scale(m["sa"]), "?", m.group(0), reportable=False)],
        )
    take(
        _MULTIPLE_RANGE_RE,
        lambda m: [
            _plain("x", m["a"], m.group(0), reportable=not (chinese or m["times"])),
            _plain("x", m["b"], m.group(0), reportable=not (chinese or m["times"])),
        ],
    )
    take(
        _MULTIPLE_RE,
        lambda m: [_plain("x", m["a"], m.group(0), reportable=not (chinese or m["times"]))],
    )
    take(
        _WORD_MULTIPLE_RE,
        lambda m: [
            _plain(
                "x",
                str(_FOLD_WORDS[m["word"].lower()]) if m["word"] else m["num"],
                m.group(0),
                reportable=False,
            )
        ],
    )
    take(
        _ZH_NUMERAL_MULTIPLE_RE,
        lambda m: [
            _plain("x", str(number), m.group(0), reportable=False)
            if (number := _cn_number(m["cn"])) is not None
            else None
        ],
    )
    take(
        _PERCENT_RANGE_RE,
        lambda m: [_plain("%", m["a"], m.group(0)), _plain("%", m["b"], m.group(0))],
    )
    take(_PERCENT_RE, lambda m: [_plain("%", m["a"], m.group(0))])
    if chinese:
        from dataclasses import replace

        return [replace(figure, reportable=False) for figure in found]
    return found


def _same_kind(a: str, b: str) -> bool:
    if a == b:
        return True
    # A Chinese figure whose currency is written once for a whole list.
    return a.startswith("money:") and b.startswith("money:") and "money:?" in (a, b)


def _same_figure(a: _Figure, b: _Figure) -> bool:
    if not _same_kind(a.kind, b.kind):
        return False
    tolerance = max(a.precision, b.precision) / 2
    return abs(a.value - b.value) <= tolerance + Decimal("1e-9") * max(abs(a.value), 1)


def _unmatched(ours: list[_Figure], theirs: list[_Figure]) -> list[_Figure]:
    out: list[_Figure] = []
    seen: set[tuple[str, Decimal]] = set()
    for figure in ours:
        key = (figure.kind, figure.value)
        if key in seen or not figure.reportable:
            continue
        seen.add(key)
        if not any(_same_figure(figure, other) for other in theirs):
            out.append(figure)
    return out


_NUMBER_SUGGESTION = (
    "Carry every figure into the Chinese exactly as the English writes it "
    "($24M stays $24M); check which language holds the right number."
)


def _number_findings(en_shape: _DocShape, zh_shape: _DocShape) -> list[ChineseParityFinding]:
    """English money, multiples and percentages the Chinese document does
    not carry. A figure counts as carried when the Chinese has it anywhere
    (so a paragraph the two gates file under different sections is not a
    mismatch), within one rounding step; the sources section is skipped."""
    zh_all = [
        figure
        for block in zh_shape.blocks
        if block.section_id != "sources"
        for figure in figures(block.text, chinese=True)
    ]
    findings = []
    reported: set[tuple[str, Decimal]] = set()
    for block in en_shape.blocks:
        if block.section_id == "sources":
            continue
        for figure in figures(block.text):
            key = (figure.kind, figure.value)
            if key in reported or not figure.reportable:
                continue
            if any(_same_figure(figure, other) for other in zh_all):
                continue
            reported.add(key)
            findings.append(
                _finding(
                    "P1",
                    "number_mismatch",
                    f"{block.section_id} {block.location}",
                    f"English {figure.raw.strip()} has no Chinese counterpart: "
                    + _snippet(block.text, figure.raw.strip(), radius=60),
                    _NUMBER_SUGGESTION,
                )
            )
    return _capped(findings, _NUMBER_FINDING_CAP)


def _package_number_findings(package: dict) -> list[ChineseParityFinding]:
    """The same comparison string by string: each English figure against
    its own Chinese translation, located by block. A figure the Chinese
    restates elsewhere (an English "not 17" beside a Chinese "而非 17 倍")
    is not a mismatch."""
    parsed = [
        (section_id, path, en, figures(en), figures(zh, chinese=True))
        for section_id, path, en, zh in _package_pairs(package)
    ]
    zh_all = [figure for *_rest, zh_figs in parsed for figure in zh_figs]
    findings = []
    for section_id, path, en, en_figs, zh_figs in parsed:
        for figure in _unmatched(en_figs, zh_figs):
            if any(_same_figure(figure, other) for other in zh_all):
                continue
            findings.append(
                _finding(
                    "P1",
                    "number_mismatch",
                    f"{section_id} {path}",
                    f"English {figure.raw.strip()} has no Chinese counterpart: "
                    + _snippet(en, figure.raw.strip(), radius=60),
                    _NUMBER_SUGGESTION,
                )
            )
    return _capped(findings, _NUMBER_FINDING_CAP)


# -- glossary ------------------------------------------------------------------------

# The Chinese style guide A6a's prompts load (English file; the team edits
# its zh twin). Its "Glossary" table rows read | English | 中文 | Avoid |.
ZH_STYLE_PATH = Path(__file__).resolve().parents[1] / "skills" / "memo" / "zh_style.md"
_AVOID_SPLIT_RE = re.compile(r"[、,，;；/]")
# A row the team has yet to settle: "bear case (to confirm / 待团队确认)".
_TO_CONFIRM_RE = re.compile(r"\s*[(（]\s*to confirm[^)）]*[)）]\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class GlossaryTerm:
    english: str
    chinese: str
    avoid: tuple[str, ...]


def parse_glossary(markdown: str) -> list[GlossaryTerm]:
    """Rows of the first ``| English | 中文 | Avoid |`` table in ``markdown``."""
    terms: list[GlossaryTerm] = []
    in_table = False
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not in_table:
            lowered = [cell.lower() for cell in cells]
            if len(cells) >= 3 and lowered[0] == "english" and cells[1] == "中文" and lowered[2] == "avoid":
                in_table = True
            continue
        if len(cells) < 3 or set("".join(cells)) <= set("-: "):
            continue
        avoid = tuple(
            variant.strip()
            for variant in _AVOID_SPLIT_RE.split(cells[2])
            if variant.strip() and variant.strip() not in {"—", "-", "–", "无"}
        )
        if cells[1] and avoid:
            english = _TO_CONFIRM_RE.sub("", cells[0]).strip()
            terms.append(GlossaryTerm(english, cells[1], avoid))
    return terms


@lru_cache(maxsize=4)
def _glossary_cached(path: str, mtime: float) -> tuple[GlossaryTerm, ...]:
    return tuple(parse_glossary(Path(path).read_text(encoding="utf-8")))


def glossary_terms(path: Path | None = None) -> tuple[GlossaryTerm, ...]:
    """The glossary, or nothing when the style guide is absent."""
    target = Path(path) if path else ZH_STYLE_PATH
    try:
        return _glossary_cached(str(target), target.stat().st_mtime)
    except OSError:
        return ()


_SUBSECTION_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s*[.、．]\s*")


def _fixed_titles(structure: memo_structure.MemoStructure | None) -> set[str]:
    """Headings the structure fixes (the model copies them; the glossary
    does not re-translate them)."""
    if structure is None:
        return set()
    titles = {section.zh_title for section in structure.sections}
    titles.update(sub.zh for section in structure.sections for sub in section.subsections)
    titles.update(ps.zh_title for ps in structure.pseudo_sections)
    return {title.strip() for title in titles if title}


def _glossary_findings(
    zh_shape: _DocShape, structure: memo_structure.MemoStructure | None
) -> list[ChineseParityFinding]:
    terms = glossary_terms()
    if not terms:
        return []
    fixed = _fixed_titles(structure or memo_structure.LATE)
    hits: dict[str, tuple[GlossaryTerm, _DocBlock, int]] = {}
    for block in zh_shape.blocks:
        if block.section_id == "sources":
            continue
        if _SUBSECTION_NUMBER_PREFIX_RE.sub("", block.text).strip() in fixed:
            continue
        matched = [
            (term, variant)
            for term in terms
            for variant in term.avoid
            if variant in block.text
        ]
        for term, variant in matched:
            # "运行率" inside "年化运行率" is one drift, reported as the
            # longer variant; only its own free-standing uses count.
            count = block.text.count(variant) - sum(
                block.text.count(other)
                for _t, other in matched
                if other != variant and variant in other
            )
            if count <= 0:
                continue
            first = hits.get(variant)
            hits[variant] = (
                term,
                first[1] if first else block,
                (first[2] if first else 0) + count,
            )
    findings = []
    for variant, (term, block, count) in hits.items():
        findings.append(
            _finding(
                "P2",
                "glossary_variant",
                block.location,
                f"{variant}: "
                + _snippet(block.text, variant, radius=40)
                + (f" (×{count})" if count > 1 else ""),
                f"Use {term.chinese} for “{term.english}”; the glossary avoids {variant}.",
            )
        )
    return findings


def _section_id_from_heading(
    text: str,
    locale: str,
    patterns: dict | None = None,
) -> str | None:
    """The section a heading opens. The renderer numbers back matter after
    any extra sections ("XV. Sources, ..."), so a heading also matches its
    profile pattern once its numeral is set aside."""
    candidates = (patterns or SECTION_PATTERNS).items()
    for section_id, locale_patterns in candidates:
        if locale_patterns[locale].search(text):
            return section_id
    for section_id, locale_patterns in candidates:
        if memo_structure.heading_matches(locale_patterns[locale], text):
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


# An English sentence left inside Chinese prose: a run between CJK
# characters of at least this many English words, some of them the
# function words only running English has ("the", "of", "and"). A list of
# proper names ("Future Ventures, AME Cloud Ventures, Evolution VC
# Partners") has none, so it is never flagged. Live 2026-09-23 (Gemini's
# translator) kept "Impact: Delays in carrier core network certification
# can extend enterprise deployment cycles past 18 months..." in English with
# a Chinese gloss in brackets, and the whole-block rule could not see it
# because the block also held Chinese.
_EMBEDDED_ENGLISH_MIN_WORDS = 8
_EMBEDDED_ENGLISH_MIN_FUNCTION_WORDS = 2
_ENGLISH_FUNCTION_WORDS = frozenset(
    "the a an of and or to in on at for with by from is are was were be been "
    "that this these those it its as than but not no into over under after "
    "before while can could will would should may might has have had".split()
)
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
_CJK_SPLIT_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff08-\uff1f\u3010\u3011\u300c-\u300f\u300a\u300b]+"
)


# What a translator rightly keeps in English: a title in 《》 or quotes,
# a URL. Removed before the sentence test.
_KEPT_ENGLISH_RE = re.compile(
    r"《[^》]*》|“[^”]*”|「[^」]*」|『[^』]*』|\"[^\"\n]*\"|https?://\S+|www\.\S+"
)
# A sentence has lowercase content words; a name ("Bank of America, The
# Carlyle Group and Temasek") or a title in title case has none.
_EMBEDDED_ENGLISH_MIN_CONTENT_WORDS = 3


def embedded_english_sentence(text: str) -> str | None:
    """The first English sentence left inside Chinese prose, or None. Names,
    titles in title case or in 《》/quotes, and URLs are not sentences."""
    if not text or not CJK_RE.search(text):
        return None
    for segment in _CJK_SPLIT_RE.split(_KEPT_ENGLISH_RE.sub("\u3000", text)):
        words = _ENGLISH_WORD_RE.findall(segment)
        if len(words) < _EMBEDDED_ENGLISH_MIN_WORDS:
            continue
        function_words = sum(1 for word in words if word.lower() in _ENGLISH_FUNCTION_WORDS)
        content_words = sum(
            1
            for word in words
            if word[:1].islower() and word.lower() not in _ENGLISH_FUNCTION_WORDS
        )
        if (
            function_words >= _EMBEDDED_ENGLISH_MIN_FUNCTION_WORDS
            and content_words >= _EMBEDDED_ENGLISH_MIN_CONTENT_WORDS
        ):
            return segment.strip()
    return None


# A translation that changes a number: the English has a figure the Chinese
# does not, and the Chinese has one the English does not (ZaiNar
# 2026-09-23, Gemini: "its 95+ issued patents" became "90 余项已授权专利").
# Compared by value after the Chinese money form is normalised, so "$1,500M"
# and "15 亿美元" agree; years, and whole numbers up to 31 (days, months,
# small counts a translator spells out), are not compared.
# A number is delimited by Latin letters and digits, never by a Chinese
# character ("拥有90余项" holds a 90). Its scale is an English word, an
# abbreviation, or a Chinese unit (万/亿 count anything — users, RMB, units —
# not just dollars). A single-letter scale is upper case, or lower case only
# after a currency sign ("$5m"): "50 m" is metres and "100 t" is tonnes.
_NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.,])(?P<cur>[$€£¥])?\s?(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)"
    r"(?:\s?(?P<scale>(?i:trillion|billion|million|thousand|bn|mn)(?![A-Za-z])|"
    r"[KMBTkmbt](?![A-Za-z²³\d])|万亿|千亿|百亿|亿|千万|百万|万))?"
    r"(?P<unit>\s?(?:%|[xX](?![A-Za-z])|×|(?i:percent)\b))?"
)
_TOKEN_SCALES = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12,
    "万": 1e4, "百万": 1e6, "千万": 1e7, "亿": 1e8, "百亿": 1e10, "千亿": 1e11,
    "万亿": 1e12,
}
# Two numbers joined as a range share the second one's scale and unit:
# "$400-750M" is $400M-$750M, "20-30%" is 20%-30%.
_RANGE_JOIN_TOKEN_RE = re.compile(r"\s?(?:[-–—~]|to|至|到)\s?[$€£¥]?\s?", re.IGNORECASE)
_CITATION_IDS_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]|\b[SC]\d+\b")
_NUMBER_MATCH_REL_TOL = 0.005


def _number_values(text: str) -> list[float]:
    """Every number in a string by value: an amount with a currency sign or
    a scale at its full value ("$1.35B", "$1,350M"), a percent or multiple
    as written. Years and bare whole numbers up to 31 (days, months, small
    counts a translator spells out) are left out."""
    source = _CITATION_IDS_RE.sub(" ", text or "")
    tokens = []
    for match in _NUMBER_TOKEN_RE.finditer(source):
        scale = match.group("scale") or ""
        if len(scale) == 1 and scale.islower() and not match.group("cur"):
            scale = ""  # "50 m", "100 t": a unit, not a scale
        tokens.append(
            {
                "match": match,
                "raw": match.group("num"),
                "cur": match.group("cur"),
                "scale": scale.lower() if scale.isascii() else scale,
                "unit": (match.group("unit") or "").strip().lower(),
            }
        )
    for token, following in zip(tokens, tokens[1:]):
        if token["scale"] or token["unit"]:
            continue
        joined = source[token["match"].end():following["match"].start()]
        if _RANGE_JOIN_TOKEN_RE.fullmatch(joined) and (following["scale"] or following["unit"]):
            token["scale"], token["unit"] = following["scale"], following["unit"]
            token["cur"] = token["cur"] or following["cur"]
    values: list[float] = []
    for token in tokens:
        try:
            value = float(token["raw"].replace(",", ""))
        except ValueError:
            continue
        if token["scale"]:
            value *= _TOKEN_SCALES.get(token["scale"], 1.0)
        bare = not (token["cur"] or token["scale"] or token["unit"])
        # A year is four bare digits; "2,000 employees" is a count.
        if bare and value.is_integer() and (
            value <= 31 or (1900 <= value <= 2100 and "," not in token["raw"])
        ):
            continue
        values.append(value)
    return values


def translation_changes_a_number(en: str, zh: str) -> bool:
    """True when the Chinese swapped a figure for another one."""
    from . import memo_docx_renderer

    en_values = _number_values(en)
    zh_values = _number_values(memo_docx_renderer.normalize_zh_money(zh or ""))

    def matched(value: float, pool: list[float]) -> bool:
        return any(math.isclose(value, other, rel_tol=_NUMBER_MATCH_REL_TOL) for other in pool)

    en_only = [value for value in en_values if not matched(value, zh_values)]
    zh_only = [value for value in zh_values if not matched(value, en_values)]
    return bool(en_only and zh_only)


def english_left_untranslated(text: str) -> bool:
    """True when this string is Chinese-slot prose that never got translated.

    The same rule the rendered-document gate reports as
    ``english_only_body_prose``, exposed so the package pipeline can catch
    it while there is still something to do about it. Deliberately
    conservative — a zh half that is a number, a ticker or a proper noun
    carries no CJK either and is correct as it stands. A Chinese string that
    keeps an English sentence inside it (``embedded_english_sentence``) is
    untranslated too.
    """
    return _large_english_only_block(text) or embedded_english_sentence(text) is not None


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
