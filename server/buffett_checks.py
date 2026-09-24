"""Deterministic checks on a Buffett-method memo — every one a warning.

Run by ``buffett_memo_analysis`` when a run finalizes (after the Word files
render) and usable from a re-render script. Nothing here can fail a run or
a render: each check reports findings at P1/P2, the material ones become
``quality_warnings`` on the report (status ``complete_with_warnings``), and
the fact check keeps its own P0 count for unsupported figures exactly as
the late-stage pipeline stores it. No model call, no network.

- **Voice** — the memo is BSH Research applying Buffett's method, so an
  "Omaha" dateline, first-person Berkshire Hathaway holdings or trades, and
  "Charlie and I" are flagged, as are the stock phrases the old skill
  prompted ("toll bridge", "if the market closed tomorrow…").
- **Price basis** — a price built only from assumed inputs must say
  "illustrative, built from assumptions" (or the call is Too Hard).
- **Valuation** — ``buffett_memo_renderer.check_valuation`` reconciles the
  optional structured fields.
- **Numbers** — every figure in ``markdown_en`` is traced to the sources on
  file (``memo_fact_check`` corpus, ``## `` headings as section ids), and
  the Chinese memo's figures are compared with the English ones.
- **Research** — a run that made no WebSearch/WebFetch lookup, or whose
  share price and Treasury yield could not be pinned, is flagged.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import buffett_memo_renderer

logger = logging.getLogger(__name__)

CHECKS_REPORT_FILENAME = "buffett_checks.md"
FACT_CHECK_MD = "fact_check.md"
FACT_CHECK_JSON = "fact_check.json"
RETRIEVAL_TOOLS = ("WebSearch", "WebFetch")
MAX_FINDINGS_PER_KIND = 20

# House numbers the skill itself sets (hurdle floor and spread, the growth
# cap, the required-margin-of-safety table). A memo that states them is
# quoting the method, not a fact that needs a source.
HOUSE_RULE_TEXT = "10% 3% 4% 10% 15% 25% 33%"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    location: str
    snippet: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# ---- text helpers ------------------------------------------------------------------

_SENTENCE_EN = re.compile(r"(?<=[.!?])\s+(?=[\"“‘(A-Z*])")
_SENTENCE_ZH = re.compile(r"(?<=[。！？；])")
_MARKER_RE = re.compile(r"\[(\d{1,3})\]")


def _sentences_en(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_EN.split(text or "") if piece.strip()]


def _sentences_zh(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_ZH.split(text or "") if piece.strip()]


def _snippet(text: str, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _opening_lines(markdown: str, count: int = 4) -> list[str]:
    lines = [line.strip() for line in (markdown or "").splitlines() if line.strip()]
    return lines[:count]


def _body_text(markdown: str) -> str:
    """The memo without its headings (so section titles never match)."""
    return "\n".join(
        line for line in (markdown or "").splitlines() if not line.lstrip().startswith("#")
    )


# ---- voice ----------------------------------------------------------------------------

_OMAHA_EN = re.compile(r"^\W*Omaha\b")
_OMAHA_ZH = re.compile(r"^\W*奥马哈")
_BERKSHIRE_EN = re.compile(r"\bBerkshire\b")
_OWNERSHIP_EN = re.compile(
    r"\b(?:[Ww]e|[Oo]urs?|[Uu]s|I|[Mm]y|[Mm]e)\b(?P<gap>[^.;!?]{0,80}?)"
    r"\b(?P<verb>own(?:s|ed)?|bought|sold|stakes?|positions?|holdings?|holds?|held|"
    r"adding|added|trimmed|trimming|shares|shareholders)\b"
)
_MODAL_EN = re.compile(r"\b(?:would|could|might|should|will|wouldn't|won't|may)\b", re.I)
# BSH writes as a prospective buyer with no position, so a first-person
# statement of a current or past holding or trade is the Buffett persona
# whether or not the sentence names Berkshire ("We hold warrants on…",
# "in January we bought OxyChem", "what I already own").
_HOLDING_EN = re.compile(
    r"\b(?:[Ww]e|I)\s+(?:still\s+|already\s+|also\s+|currently\s+|now\s+|have\s+|had\s+|were\s+|was\s+)*"
    r"(?:own|owned|hold|held|bought|sold|adding|added|trimmed|trimming|been\s+adding|been\s+buying)\b"
    r"|\b(?:[Oo]ur|[Mm]y)\s+(?:stake|position|holding|holdings|shares|warrants|preferred|preferreds|"
    r"investment\s+in|purchase\s+of|sale\s+of)\b"
    r"|\bwhat\s+(?:we|I)\s+(?:already\s+)?own\b"
    r"|\b(?:[Ww]e|I)\s+have\s+no\s+intention\s+of\s+selling\b"
)
_HYPOTHETICAL_EN = re.compile(r"\b(?:if|when|once|unless|whether|would|could|might|should|will)\b", re.I)
_MUNGER_EN = re.compile(r"\b(?:Charlie|Munger)\b")
_FIRST_PERSON_EN = re.compile(r"\b(?:I|[Mm]y|[Mm]e|[Ww]e|[Oo]ur)\b")
_BERKSHIRE_ZH = re.compile(r"伯克希尔")
_OWNERSHIP_ZH = re.compile(
    r"(?:我们|我)[^。！？；]{0,20}?(?:持有|持股|持仓|仓位|股份|买入了|买进了|卖出了|卖掉了|增持|减持|加仓|减仓)"
)
_MODAL_ZH = re.compile(r"会|愿意|将|可以|可能")
_HOLDING_ZH = re.compile(
    r"(?:我们|我)(?:仍然|仍|还|已经|也|一直|目前|手里)?"
    r"(?:持有|买入了|买进了|卖出了|卖掉了|增持了|减持了|加仓|减仓)"
    r"|(?:我们|我)的(?:持仓|仓位|股份|持股|认股权证|优先股)"
)
_HYPOTHETICAL_ZH = re.compile(r"如果|假如|若|一旦|即使|假设|倘若|愿意|会|将|可以|可能|要")


def voice_findings(markdown_en: str, markdown_zh: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in _opening_lines(markdown_en):
        if _OMAHA_EN.search(line):
            findings.append(
                Finding(
                    "P1",
                    "persona_omaha_dateline",
                    "markdown_en dateline",
                    _snippet(line),
                    "The memo is BSH Research's owner's analysis, not a memo from Omaha: use "
                    "'BSH Research · Owner's analysis (Buffett method) · prices as of <date>'.",
                )
            )
            break
    else:
        if not any("BSH Research" in line for line in _opening_lines(markdown_en)):
            findings.append(
                Finding(
                    "P2",
                    "dateline_missing",
                    "markdown_en dateline",
                    _snippet(" / ".join(_opening_lines(markdown_en, 2))),
                    "Open with 'BSH Research · Owner's analysis (Buffett method) · prices as of <date>'.",
                )
            )
    for line in _opening_lines(markdown_zh):
        if _OMAHA_ZH.search(line):
            findings.append(
                Finding(
                    "P1",
                    "persona_omaha_dateline",
                    "markdown_zh dateline",
                    _snippet(line),
                    "中文日期行应为「BSH 研究 · 巴菲特方法所有者分析 · 价格截至……」，不要写奥马哈。",
                )
            )
            break

    body_en = _body_text(markdown_en)
    persona_hits = 0
    for sentence in _sentences_en(body_en):
        flagged = False
        if _BERKSHIRE_EN.search(sentence):
            for match in _OWNERSHIP_EN.finditer(sentence):
                if _MODAL_EN.search(match.group("gap")):
                    continue
                flagged = True
                break
        if not flagged:
            for match in _HOLDING_EN.finditer(sentence):
                lead = sentence[max(0, match.start() - 30) : match.start()]
                if _HYPOTHETICAL_EN.search(lead) or _MODAL_EN.search(match.group(0)):
                    continue
                flagged = True
                break
        if flagged:
            persona_hits += 1
            if persona_hits <= MAX_FINDINGS_PER_KIND:
                findings.append(
                    Finding(
                        "P1",
                        "persona_berkshire_first_person",
                        "markdown_en",
                        _snippet(sentence),
                        "BSH has no position: state Berkshire Hathaway's holdings or trades only as a "
                        "sourced third-party fact, never in the first person and never as a reason to act.",
                    )
                )
        if _MUNGER_EN.search(sentence) and _FIRST_PERSON_EN.search(sentence):
            findings.append(
                Finding(
                    "P1",
                    "persona_buffett_first_person",
                    "markdown_en",
                    _snippet(sentence),
                    "Do not write as Warren Buffett ('Charlie and I', personal recollections); "
                    "apply the method in BSH's own voice.",
                )
            )
    for sentence in _sentences_zh(_body_text(markdown_zh)):
        flagged = False
        if _BERKSHIRE_ZH.search(sentence):
            flagged = any(
                not _MODAL_ZH.search(match.group(0)) for match in _OWNERSHIP_ZH.finditer(sentence)
            )
        if not flagged:
            for match in _HOLDING_ZH.finditer(sentence):
                lead = sentence[max(0, match.start() - 8) : match.start()]
                if _HYPOTHETICAL_ZH.search(lead) or _HYPOTHETICAL_ZH.search(match.group(0)):
                    continue
                flagged = True
                break
        if flagged:
            findings.append(
                Finding(
                    "P1",
                    "persona_berkshire_first_person",
                    "markdown_zh",
                    _snippet(sentence),
                    "BSH 并无持仓：伯克希尔的持仓或交易只能作为有出处的第三方事实出现，不能用第一人称，也不能作为行动理由。",
                )
            )

    singular = len(re.findall(r"\bI\b", body_en))
    if singular > 25:
        findings.append(
            Finding(
                "P2",
                "first_person_singular",
                "markdown_en",
                f"'I' appears {singular} times",
                "The memo's voice is BSH Research's 'we' (an analyst's 'I' at most), never Buffett's.",
            )
        )
    return findings


# ---- stock phrases ---------------------------------------------------------------------------

_STOCK_PHRASES_EN = (
    (
        re.compile(r"\btoll[- ]bridges?\b", re.I),
        "stock_phrase_toll_bridge",
        "Drop 'toll bridge'; use at most one analogy, specific to this company.",
    ),
    (
        re.compile(
            r"\bmarkets?\s+(?:(?:were|was|is|to|be|were\s+to)\s+){0,3}clos(?:ed|es|e|ing)\b[^.]{0,120}?"
            r"\b(?:tomorrow|ten years|10 years|a decade|decade|reopen(?:s|ed)?)\b",
            re.I,
        ),
        "stock_phrase_market_closed",
        "State the ten-year judgment in this business's own terms, not as 'if the market closed…'.",
    ),
)
_STOCK_PHRASES_ZH = (
    (re.compile(r"收费桥"), "stock_phrase_toll_bridge", "不要用「收费桥」这类套话；类比最多一个，而且要贴合这家公司。"),
    (
        re.compile(
            r"(?:市场|股市|交易所)[^。]{0,20}?(?:关闭|休市|停止交易|关门)[^。]{0,30}?(?:十年|10 ?年|明天|重新开)"
            r"|(?:市场|股市|交易所)[^。]{0,10}?(?:明天|十年|10 ?年)[^。]{0,10}?(?:关闭|休市|停止交易|关门)"
        ),
        "stock_phrase_market_closed",
        "用这家企业自己的语言回答十年检验，不要写「如果市场关闭十年」。",
    ),
)


def stock_phrase_findings(markdown_en: str, markdown_zh: str) -> list[Finding]:
    findings: list[Finding] = []
    for locale, text, phrases in (
        ("markdown_en", _body_text(markdown_en), _STOCK_PHRASES_EN),
        ("markdown_zh", _body_text(markdown_zh), _STOCK_PHRASES_ZH),
    ):
        for pattern, code, suggestion in phrases:
            for match in list(pattern.finditer(text))[:3]:
                start = max(0, match.start() - 60)
                findings.append(
                    Finding("P2", code, locale, _snippet(text[start : match.end() + 60]), suggestion)
                )
    return findings


# ---- price basis (illustrative prices) ------------------------------------------------------

_MONEY_EN = re.compile(r"(?:US\$|NT\$|HK\$|\$|€|£|¥)\s?\d")
_MONEY_ZH = re.compile(r"\d[\d,.]*\s?(?:万亿|亿|万)?\s?(?:美元|港元|新台币|元)")
_SHARE_WORDS = re.compile(r"\b(?:a share|per share|per-share|ADR|ADS|share price|stock)\b", re.I)


def price_basis_findings(validated: dict[str, Any]) -> list[Finding]:
    """Rule: a price derived only from assumed inputs carries the words
    "illustrative, built from assumptions" wherever it appears (§I, §VIII,
    §X), or the call is Too Hard with no price."""
    fields = validated["fields"]
    markdown_en = validated["markdown_en"]
    markdown_zh = validated["markdown_zh"]
    decision = validated["decision"]
    en_sections = buffett_memo_renderer.REQUIRED_HEADINGS_EN
    zh_sections = buffett_memo_renderer.REQUIRED_HEADINGS_ZH
    findings: list[Finding] = []
    if fields.get("valuation_basis") == "assumed":
        for heading in (en_sections[0], en_sections[7], en_sections[9]):
            body = buffett_memo_renderer.section_body(markdown_en, heading)
            if _MONEY_EN.search(body) and "illustrative" not in body.lower():
                findings.append(
                    Finding(
                        "P1",
                        "assumed_price_unlabelled",
                        heading[3:],
                        _snippet(body),
                        "This valuation rests on assumed inputs: label every price 'illustrative, built "
                        "from assumptions', or make the call Too Hard with no price.",
                    )
                )
        for heading in (zh_sections[0], zh_sections[7], zh_sections[9]):
            body = buffett_memo_renderer.section_body(markdown_zh, heading)
            if _MONEY_ZH.search(body) and "示意" not in body:
                findings.append(
                    Finding(
                        "P2",
                        "assumed_price_unlabelled",
                        heading[3:],
                        _snippet(body),
                        "估值基于假设：每个价格都要注明「示意性，基于假设」。",
                    )
                )
        return findings
    section_one = buffett_memo_renderer.section_body(markdown_en, en_sections[0])
    if (
        decision != "Too Hard"
        and fields.get("price") is None
        and fields.get("valuation_basis") != "disclosed"
        and _MONEY_EN.search(section_one)
        and not _SHARE_WORDS.search(section_one)
        and "illustrative" not in markdown_en.lower()
    ):
        findings.append(
            Finding(
                "P2",
                "price_basis_unstated",
                en_sections[0][3:],
                _snippet(section_one),
                "Section I prices a company with no quoted share price. If the figure rests only on "
                "assumed inputs, label it 'illustrative, built from assumptions' (and set "
                "valuation_basis 'assumed'), or make the call Too Hard with no price.",
            )
        )
    return findings


# ---- length and citations -----------------------------------------------------------------------


def budget_findings(markdown_en: str, decision: str) -> list[Finding]:
    words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,-]*", _body_text(markdown_en)))
    limit = 2200 if decision == "Too Hard" else 4200
    if words > limit:
        return [
            Finding(
                "P2",
                "over_word_budget",
                "markdown_en",
                f"{words:,} words (budget about {limit - 700:,})",
                "Keep to the skill's word budget: about 2,500–3,500 words with a real record, "
                "1,200–1,800 when disclosure is thin or the call is Too Hard.",
            )
        ]
    return []


def citation_findings(markdown_en: str, sources: list[dict[str, Any]]) -> list[Finding]:
    known = {int(source["n"]) for source in sources}
    cited = {int(n) for n in _MARKER_RE.findall(_body_text(markdown_en))}
    missing = sorted(cited - known)
    if not missing:
        return []
    return [
        Finding(
            "P2",
            "citation_without_source",
            "markdown_en",
            "markers " + ", ".join(f"[{n}]" for n in missing[:12]),
            "Every [n] marker needs a matching entry in the package's sources list.",
        )
    ]


# ---- research signals ---------------------------------------------------------------------------


def web_lookup_count(run_dir: Path | str | None) -> int | None:
    """WebSearch/WebFetch tool uses recorded in the run's progress streams
    (current and archived-before-resume). None when no stream exists."""
    if run_dir is None:
        return None
    logs = Path(run_dir) / "logs"
    try:
        streams = sorted(logs.glob("stream*.jsonl"))
    except OSError:
        return None
    if not streams:
        return None
    total = 0
    for stream in streams:
        try:
            lines = stream.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"tool_use"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if (
                event.get("type") == "claude_action"
                and event.get("action") == "tool_use"
                and event.get("tool") in RETRIEVAL_TOOLS
            ):
                total += 1
    return total


def market_input_findings(market_inputs: dict[str, Any] | None) -> list[Finding]:
    if not isinstance(market_inputs, dict):
        return []
    missing = []
    if market_inputs.get("ticker") and market_inputs.get("price") is None:
        missing.append(f"share price ({market_inputs.get('ticker')})")
    if market_inputs.get("ust10y") is None:
        missing.append("10-year Treasury yield")
    if not missing:
        return []
    return [
        Finding(
            "P1",
            "inputs_not_pinned",
            "market inputs",
            ", ".join(missing) + " not pinned at run start",
            "The memo's figures for these are model-sourced; check them against their stated dates.",
        )
    ]


# ---- EN / ZH number parity --------------------------------------------------------------------

_ZH_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_ZH_FIGURE_RE = re.compile(
    r"(?P<cur>US\$|NT\$|HK\$|\$)?\s?"
    rf"(?:(?P<lo>{_ZH_NUM})\s?(?:–|—|-|~|～|至|到)\s?)?"
    rf"(?P<num>{_ZH_NUM})\s?"
    r"(?P<scale>万亿|亿|万|千)?\s?"
    r"(?P<unit>美元|港元|新台币|元人民币|人民币|欧元|英镑|日元|元|个百分点|%|％|倍|×|x(?![A-Za-z])|股)?"
)
_ZH_SCALE = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "千": 1e3}
_BARE_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
_DATE_LIKE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{4}\s?年(?:\s?\d{1,2}\s?月)?(?:\s?\d{1,2}\s?日)?|\b(?:19|20)\d{2}\b"
)
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_WORD_NUMBER_RE = re.compile(
    r"\b(?P<tens>twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?P<unit>one|two|three|four|five|six|seven|eight|nine))?\b"
    r"|\b(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred)\b",
    re.I,
)
_EN_TIMES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:times|×)\b")
# Currency prefixes memo_fact_check's extractor reads as an identifier
# ("NT$" looks like "10-K"): spelled as "$" for the comparison.
_EN_CURRENCY_ALIASES = re.compile(r"\b(?:NT|NTD\s?|R|Rs\.?\s?|RM|MX|NZ)\$")


def _zh_figures(text: str) -> list[tuple[str, float, str]]:
    """``(raw, value, class)`` for Chinese figures that carry a unit — a
    currency, a 万/亿 scale, %, 倍 or 股 (both ends of a range such as
    "600–640 亿美元"). Bare numbers (dates, counts, ordinals) are skipped:
    they cannot be compared reliably."""
    out: list[tuple[str, float, str]] = []
    cleaned = _MARKER_RE.sub(lambda match: " " * len(match.group(0)), text or "")
    for match in _ZH_FIGURE_RE.finditer(cleaned):
        scale = match.group("scale")
        unit = match.group("unit")
        currency = match.group("cur")
        if not (scale or unit or currency):
            continue
        if unit in {"%", "％", "个百分点"}:
            klass = "pct"
        elif unit in {"倍", "×", "x"}:
            klass = "mult"
        else:
            klass = "amount"
        for key in ("lo", "num"):
            raw_number = match.group(key)
            if not raw_number:
                continue
            try:
                value = float(raw_number.replace(",", ""))
            except ValueError:
                continue
            if scale:
                value *= _ZH_SCALE[scale]
            out.append((match.group(0).strip(), value, klass))
    return out


def _word_numbers(text: str) -> list[float]:
    values = []
    for match in _WORD_NUMBER_RE.finditer(text or ""):
        if match.group("tens"):
            value = _NUMBER_WORDS[match.group("tens").lower()]
            if match.group("unit"):
                value += _NUMBER_WORDS[match.group("unit").lower()]
        else:
            value = _NUMBER_WORDS[match.group("word").lower()]
        values.append(float(value))
    return values


def _bare_numbers(text: str) -> list[float]:
    """Every number a text spells, unit or not, plus English number words —
    the permissive side of the comparison (a unit a translation adds or
    drops, "twenty-eight times" vs "28 倍", is not a changed figure)."""
    values = []
    # Dates and years are not figures ("2026-08-20" must not vouch for "20 倍").
    text = _DATE_LIKE_RE.sub(" ", text or "")
    for match in _BARE_NUMBER_RE.finditer(text):
        try:
            values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return values + _word_numbers(text)


def _en_values(text: str) -> tuple[list[tuple[str, float, str]], dict[str, list[float]]]:
    from . import memo_fact_check

    cleaned = _MARKER_RE.sub(lambda match: " " * len(match.group(0)), text or "")
    cleaned = _EN_CURRENCY_ALIASES.sub("$", cleaned)
    figures = [(f.raw, f.value, f.klass) for f in memo_fact_check.extract_figures(cleaned)]
    for match in _EN_TIMES_RE.finditer(cleaned):
        figures.append((match.group(0), float(match.group(1)), "mult"))
    values: dict[str, list[float]] = {"amount": [], "pct": [], "mult": []}
    for _raw, value, klass in figures:
        values.setdefault(klass, []).append(value)
    return figures, values


def _matches(value: float, candidates: list[float]) -> bool:
    for candidate in candidates:
        scale = max(abs(value), abs(candidate))
        if scale == 0 or abs(value - candidate) / scale <= 0.02:
            return True
    return False


def _mantissas(value: float) -> list[float]:
    """``value`` and the forms a scale word hides: 4.3e12 is also "4.3"
    (trillion), "43,000" (亿) and "4,300" (billion)."""
    out = [value]
    for divisor in (1e3, 1e4, 1e6, 1e8, 1e9, 1e12):
        if abs(value) >= divisor:
            out.append(value / divisor)
    return out


_ZH_CALL_WORDS = {
    "Buy": ("买入",),
    "Pass": ("放弃", "暂不买入", "不买"),
    "Too Hard": ("Too Hard", "超出能力圈"),
}


def number_parity(validated: dict[str, Any], *, en_path: str = "", zh_path: str = "") -> dict[str, Any]:
    """Compare the figures of the two memos (same shape as the late-stage
    ``memo_chinese_parity`` payload; findings are P1/P2 only)."""
    findings: list[Finding] = []
    markdown_en = _body_text(validated["markdown_en"])
    markdown_zh = _body_text(validated["markdown_zh"])
    en_figures, en_values = _en_values(markdown_en)
    en_bare = _bare_numbers(_EN_CURRENCY_ALIASES.sub("$", markdown_en))
    zh_figures = _zh_figures(markdown_zh)
    zh_values: dict[str, list[float]] = {"amount": [], "pct": [], "mult": []}
    for _raw, value, klass in zh_figures:
        zh_values[klass].append(value)
    zh_bare = _bare_numbers(markdown_zh)

    def in_english(value: float, klass: str) -> bool:
        if _matches(value, en_values.get(klass, [])):
            return True
        # A unit or scale the translation added ("1.3 倍" for "debt to
        # equity of about 1.3", "28 倍" for "twenty-eight times").
        return any(_matches(form, en_bare) for form in _mantissas(value))

    def in_chinese(value: float, klass: str) -> bool:
        if _matches(value, zh_values.get(klass, [])):
            return True
        return any(_matches(form, zh_bare) for form in _mantissas(value))

    reported: set[tuple[str, float]] = set()
    for raw, value, klass in zh_figures:
        key = (klass, round(value, 6))
        if key in reported or in_english(value, klass):
            continue
        if len(reported) >= MAX_FINDINGS_PER_KIND:
            break
        reported.add(key)
        findings.append(
            Finding(
                "P1",
                "zh_number_not_in_en",
                "markdown_zh",
                raw,
                "The Chinese memo states a figure the English memo does not; the two must carry the same numbers.",
            )
        )
    missing: list[str] = []
    seen: set[tuple[str, float]] = set()
    for raw, value, klass in en_figures:
        key = (klass, round(value, 6))
        if key in seen:
            continue
        seen.add(key)
        if klass == "amount" and not re.search(r"[$€£¥]|million|billion|trillion|thousand|\d[mbk]\b", raw, re.I):
            continue  # a bare count ("30 customers") is often spelled out in Chinese
        if not in_chinese(value, klass):
            missing.append(raw)
    if missing:
        findings.append(
            Finding(
                "P2",
                "en_numbers_missing_in_zh",
                "markdown_zh",
                ", ".join(missing[:MAX_FINDINGS_PER_KIND]),
                "These English figures do not appear in the Chinese memo (a dropped or changed number).",
            )
        )
    decision = validated["decision"]
    section_one = buffett_memo_renderer.section_body(
        validated["markdown_zh"], buffett_memo_renderer.REQUIRED_HEADINGS_ZH[0]
    )
    words = _ZH_CALL_WORDS.get(decision, ())
    if words and not any(word in section_one[:400] for word in words):
        findings.append(
            Finding(
                "P1",
                "zh_decision_missing",
                buffett_memo_renderer.REQUIRED_HEADINGS_ZH[0][3:],
                _snippet(section_one[:200]),
                f"Section 一 of the Chinese memo should state the call ({' / '.join(words)}).",
            )
        )
    p0 = [finding for finding in findings if finding.severity == "P0"]
    return {
        "en_path": en_path,
        "zh_path": zh_path,
        "status": "failed" if p0 else "passed",
        "finding_count": len(findings),
        "p0_count": len(p0),
        "p1_count": sum(1 for finding in findings if finding.severity == "P1"),
        "findings": [finding.to_dict() for finding in findings],
    }


# ---- fact check (adapter over memo_fact_check) ------------------------------------------------


def _market_inputs_text(market_inputs: dict[str, Any] | None) -> str:
    if not isinstance(market_inputs, dict):
        return ""
    parts = []
    if market_inputs.get("price") is not None:
        parts.append(
            f"{market_inputs.get('ticker') or 'share'} price {market_inputs['price']} "
            f"{market_inputs.get('currency') or ''} as of {market_inputs.get('price_as_of') or ''}"
        )
    if market_inputs.get("ust10y") is not None:
        parts.append(
            f"US 10-year Treasury yield {market_inputs['ust10y']}% as of {market_inputs.get('ust10y_as_of') or ''}"
        )
    return "\n".join(parts)


def _derived_text(fields: dict[str, Any]) -> str:
    """The figures the valuation computes (not facts that need a source):
    the value range, buy price, margins of safety, hurdle, multiple and
    owner's earnings, in the spellings a memo would use."""
    company = fields.get("value_basis") == "company"
    parts = [HOUSE_RULE_TEXT]
    for key in ("value_low", "value_central", "value_high", "buy_price_value"):
        value = fields.get(key)
        if value is not None:
            parts.append(f"${value * (1_000_000 if company else 1):,.2f}")
    for key in ("mos_pct", "required_mos_pct", "hurdle", "g"):
        if fields.get(key) is not None:
            parts.append(f"{fields[key]}%")
    if fields.get("ust10y") is not None:
        parts.append(f"{max(fields['ust10y'] + 3.0, 10.0):.2f}%")
    if fields.get("multiple") is not None:
        parts.append(f"{fields['multiple']}x")
    if fields.get("owner_earnings") is not None:
        parts.append(f"${fields['owner_earnings'] * 1_000_000:,.0f}")
    per_share = buffett_memo_renderer.owner_earnings_per_share(fields)
    if per_share is not None:
        parts.append(f"${per_share:,.2f}")
    return "\n".join(parts)


def _source_texts_by_n(
    sources: list[dict[str, Any]], *, company_id: str, run_dir: Path | None
) -> dict[int, str]:
    """Text on file for each numbered source: the company source cache by
    URL, else this run's frozen copy, else a strong title match."""
    from . import source_cache

    run_texts: dict[str, str] = {}
    if run_dir is not None:
        base = Path(run_dir) / source_cache.SOURCES_DIRNAME
        for row in source_cache.run_manifest(run_dir):
            canon = source_cache.canonical_url(row.get("url"))
            if canon and row.get("file"):
                try:
                    run_texts[canon] = (base / str(row["file"])).read_text(encoding="utf-8")
                except OSError:
                    continue
    out: dict[int, str] = {}
    for source in sources:
        url = source.get("url")
        text = ""
        try:
            record = source_cache.find_by_url(company_id, url) if url else None
            if record is not None:
                text = source_cache.source_text(company_id, record)
            canon = source_cache.canonical_url(url) if url else None
            if not text and canon and canon in run_texts:
                text = run_texts[canon]
            if not text and not url and source.get("title"):
                match = source_cache.match_title(company_id, source["title"], min_score=0.75)
                if match is not None:
                    text = source_cache.source_text(company_id, match)
        except ValueError:
            text = ""
        if text:
            out[int(source["n"])] = text
    return out


def _paragraphs(body: str) -> list[str]:
    blocks: list[str] = []
    buffer: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if buffer:
                blocks.append(" ".join(buffer))
                buffer = []
            continue
        if stripped.startswith(("- ", "* ", "|")):
            if buffer:
                blocks.append(" ".join(buffer))
                buffer = []
            blocks.append(stripped)
            continue
        buffer.append(stripped)
    if buffer:
        blocks.append(" ".join(buffer))
    return blocks


def _sentence_span(text: str, position: int) -> tuple[int, int]:
    start = 0
    for match in _SENTENCE_EN.finditer(text):
        if match.start() >= position:
            return start, match.start()
        start = match.end()
    return start, len(text)


def _excerpt(text: str, start: int, end: int, width: int = 70) -> str:
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    piece = " ".join(text[lo:hi].split())
    return (("…" if lo > 0 else "") + piece + ("…" if hi < len(text) else ""))[:220]


def fact_check(
    validated: dict[str, Any],
    *,
    company_id: str,
    run_dir: Path | None,
    research_dir: Path | None = None,
    market_inputs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Trace every figure in ``markdown_en`` to the sources on file.

    Buckets as in ``memo_fact_check``: *verified* (the cited ``[n]``
    source's own text carries it), *derived* (a figure the structured
    valuation computes), *supported* (anything on file carries it) and
    *unsupported*. Report only — never fed to a repair round. Returns the
    payload stored as ``memo_fact_check`` and the Markdown report."""
    from . import memo_fact_check as mfc

    corpus = mfc.build_corpus(company_id, run_dir=run_dir, research_dir=research_dir)
    pinned = _market_inputs_text(market_inputs)
    # The quotes BSH pinned at run start are evidence (a quote service, not
    # the model). Indexed on their own so the corpus is not re-indexed.
    pinned_index = mfc.TextIndex.of(pinned) if pinned else None
    if pinned:
        corpus.add("pinned market inputs (live quotes at run start)", pinned)
    source_index = {
        n: mfc.TextIndex.of(text)
        for n, text in _source_texts_by_n(
            validated["sources"], company_id=company_id, run_dir=run_dir
        ).items()
    }
    derived_index = mfc.TextIndex.of(_derived_text(validated["fields"]))
    result = mfc.FactCheckResult(
        corpus_summary=corpus.summary(),
        corpus_texts=corpus.describe(),
        evidence_chars=corpus.evidence_chars,
        thin_corpus=corpus.thin,
    )
    for s_index, (heading, body) in enumerate(
        buffett_memo_renderer.split_sections(validated["markdown_en"])
    ):
        section_id = heading or "title"
        for p_index, paragraph in enumerate(_paragraphs(body)):
            if paragraph.startswith("#"):
                continue
            cleaned = _MARKER_RE.sub(lambda match: " " * len(match.group(0)), paragraph)
            for figure in mfc.extract_figures(cleaned):
                result.checked += 1
                span = _sentence_span(paragraph, figure.start)
                cited = [int(n) for n in _MARKER_RE.findall(paragraph[span[0] : span[1] + 8])]
                with_text = [n for n in cited if n in source_index]
                if with_text and any(source_index[n].supports(figure) for n in with_text):
                    result.verified += 1
                    continue
                if cited and not with_text:
                    result.unverifiable_citations += 1
                if derived_index.supports(figure):
                    result.derived += 1
                    continue
                location = f"{section_id} ¶{p_index + 1}"
                if corpus.index.supports(figure) or (
                    pinned_index is not None and pinned_index.supports(figure)
                ):
                    result.supported += 1
                    if with_text:
                        result.findings.append(
                            mfc.FactFinding(
                                code="citation_mismatch",
                                section_id=section_id,
                                location=location,
                                figure=figure.raw,
                                snippet=_excerpt(paragraph, figure.start, figure.end),
                                detail=(
                                    f"{figure.raw} is on file, but not in the text of the cited "
                                    f"source{'s' if len(with_text) > 1 else ''} "
                                    + ", ".join(f"[{n}]" for n in with_text)
                                    + "; check the citation"
                                ),
                                severity="P1",
                                citations=[f"[{n}]" for n in cited],
                            )
                        )
                    continue
                result.unsupported += 1
                result.findings.append(
                    mfc.FactFinding(
                        code="unsupported_figure",
                        section_id=section_id,
                        location=location,
                        figure=figure.raw,
                        snippet=_excerpt(paragraph, figure.start, figure.end),
                        detail=(
                            f"the figure {figure.raw} appears in none of the sources on file "
                            f"({corpus.summary()}); cite the source that carries it with an [n] "
                            "marker and a sources entry, or state it as our estimate"
                        ),
                        severity="P0",
                        citations=[f"[{n}]" for n in cited],
                    )
                )
    result.repair_feed = False
    result.repair_feed_reason = "Buffett-method memo: report only (no repair round)"
    payload = result.to_dict()
    payload["memo_kind"] = buffett_memo_renderer.KIND
    return payload, mfc.render_markdown_report(result)


# ---- the whole set ------------------------------------------------------------------------------


@dataclass
class BuffettCheckReport:
    lint: dict[str, Any]
    parity: dict[str, Any] | None
    fact_check: dict[str, Any] | None
    quality_warnings: list[str] = field(default_factory=list)
    quality_warnings_zh: list[str] = field(default_factory=list)
    web_lookups: int | None = None

    def record_patch(self) -> dict[str, Any]:
        """Fields for ``storage.update_report``."""
        patch: dict[str, Any] = {
            "memo_quality_lint": self.lint,
            "memo_chinese_parity": self.parity,
            "memo_fact_check": self.fact_check,
            "quality_warnings": self.quality_warnings or None,
            "quality_warnings_zh": self.quality_warnings_zh or None,
        }
        if self.web_lookups is not None:
            patch["web_lookups"] = self.web_lookups
        return patch


def _warning(report: BuffettCheckReport, en: str, zh: str) -> None:
    report.quality_warnings.append(en)
    report.quality_warnings_zh.append(zh)


def _lint_payload(findings: list[Finding], path: str) -> dict[str, Any]:
    p0 = [finding for finding in findings if finding.severity == "P0"]
    return {
        "path": path,
        "status": "failed" if p0 else "passed",
        "finding_count": len(findings),
        "p0_count": len(p0),
        "p1_count": sum(1 for finding in findings if finding.severity == "P1"),
        "findings": [finding.to_dict() for finding in findings],
    }


def _render_report(findings: list[Finding], report: BuffettCheckReport) -> str:
    lines = ["# Buffett-method memo checks", ""]
    lines.append("All checks are warnings; none blocks the memo.")
    lines.append("")
    if report.web_lookups is not None:
        lines.append(f"- External lookups (WebSearch/WebFetch): {report.web_lookups}")
    if report.fact_check:
        lines.append(
            f"- Fact check: {report.fact_check.get('checked')} figures, "
            f"{report.fact_check.get('unsupported')} unsupported "
            f"(P0 open: {report.fact_check.get('p0_count')}; see logs/{FACT_CHECK_MD})"
        )
    if report.parity:
        lines.append(f"- EN/ZH number parity: {report.parity.get('finding_count')} finding(s)")
    lines.extend(["", "## Quality warnings", ""])
    lines.extend(f"- {warning}" for warning in report.quality_warnings or ["None."])
    lines.extend(["", "## Findings", ""])
    if not findings:
        lines.append("None.")
    for finding in findings:
        lines.append(
            f"- [{finding.severity}] {finding.code} — {finding.location}: \"{finding.snippet}\" — "
            f"{finding.suggestion}"
        )
    if report.parity and report.parity.get("findings"):
        lines.extend(["", "## EN/ZH number parity", ""])
        for item in report.parity["findings"]:
            lines.append(f"- [{item['severity']}] {item['code']} — {item['snippet']}")
    return "\n".join(lines) + "\n"


def run_checks(
    package: dict[str, Any],
    *,
    run_dir: Path | str | None,
    company_id: str,
    research_dir: Path | str | None = None,
    market_inputs: dict[str, Any] | None = None,
    web_lookups: int | None = None,
    write_logs: bool = True,
) -> BuffettCheckReport:
    """Every check, never raising. ``web_lookups`` None means "count them
    from the run's progress streams"."""
    run_path = Path(run_dir) if run_dir is not None else None
    research_path = Path(research_dir) if research_dir is not None else None
    validated = buffett_memo_renderer.validate_package(package)
    findings: list[Finding] = []

    def collect(label: str, produce) -> None:
        try:
            findings.extend(produce())
        except Exception:  # noqa: BLE001 — a check must never sink a run
            logger.warning("Buffett check %s failed", label, exc_info=True)

    collect("voice", lambda: voice_findings(validated["markdown_en"], validated["markdown_zh"]))
    collect("stock phrases", lambda: stock_phrase_findings(validated["markdown_en"], validated["markdown_zh"]))
    collect("price basis", lambda: price_basis_findings(validated))
    collect(
        "valuation",
        lambda: [
            Finding(**item) for item in buffett_memo_renderer.check_valuation(package)
        ],
    )
    collect("length", lambda: budget_findings(validated["markdown_en"], validated["decision"]))
    collect("citations", lambda: citation_findings(validated["markdown_en"], validated["sources"]))
    collect("market inputs", lambda: market_input_findings(market_inputs))

    if web_lookups is None:
        try:
            web_lookups = web_lookup_count(run_path)
        except Exception:  # noqa: BLE001
            web_lookups = None
    if web_lookups == 0:
        findings.append(
            Finding(
                "P1",
                "no_external_lookups",
                "run",
                "0 WebSearch/WebFetch lookups",
                "Research the company before writing (owner, products and customers, disclosed "
                "figures, a listed parent's filings, recent press).",
            )
        )

    parity: dict[str, Any] | None = None
    try:
        parity = number_parity(validated)
    except Exception:  # noqa: BLE001
        logger.warning("Buffett number parity failed", exc_info=True)

    fact_payload: dict[str, Any] | None = None
    fact_md = ""
    try:
        fact_payload, fact_md = fact_check(
            validated,
            company_id=company_id,
            run_dir=run_path,
            research_dir=research_path,
            market_inputs=market_inputs,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Buffett fact check failed", exc_info=True)
        fact_payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}", "p0_count": 0}

    report = BuffettCheckReport(
        lint=_lint_payload(findings, f"logs/{CHECKS_REPORT_FILENAME}"),
        parity=parity,
        fact_check=fact_payload,
        web_lookups=web_lookups,
    )
    codes = {finding.code for finding in findings if finding.severity in {"P0", "P1"}}
    if "persona_omaha_dateline" in codes:
        _warning(
            report,
            "Dateline reads 'Omaha': the memo must read as BSH Research's owner's analysis, not as written by Warren Buffett.",
            "日期行写作「奥马哈」：本备忘录应以 BSH 研究的所有者分析呈现，而非巴菲特本人撰写。",
        )
    persona = [
        finding
        for finding in findings
        if finding.code in {"persona_berkshire_first_person", "persona_buffett_first_person"}
    ]
    if persona:
        _warning(
            report,
            f"The memo speaks as Warren Buffett or Berkshire Hathaway in {len(persona)} place(s) "
            "(first-person holdings, trades or recollections). BSH has no position; Berkshire's trades "
            "may appear only as sourced third-party facts.",
            f"备忘录有 {len(persona)} 处以沃伦·巴菲特或伯克希尔·哈撒韦的第一人称陈述持仓、交易或往事。"
            "BSH 并无持仓，伯克希尔的交易只能作为有出处的第三方事实出现。",
        )
    if "no_external_lookups" in codes:
        _warning(report, "Written without any external lookups", "未进行任何外部检索")
    if "inputs_not_pinned" in codes:
        _warning(
            report,
            "The share price or 10-year Treasury yield could not be pinned at run start; the memo's figures "
            "for them are model-sourced and dated.",
            "运行开始时未能锁定股价或 10 年期美债收益率；备忘录中的相关数字由模型检索，请核对其日期。",
        )
    valuation = [
        finding
        for finding in findings
        if finding.location == "valuation" and finding.severity in {"P0", "P1"}
    ]
    if valuation:
        _warning(
            report,
            f"Valuation arithmetic does not reconcile in {len(valuation)} place(s) "
            f"(see logs/{CHECKS_REPORT_FILENAME}).",
            f"估值算术有 {len(valuation)} 处前后不一致（见 logs/{CHECKS_REPORT_FILENAME}）。",
        )
    if "assumed_price_unlabelled" in codes:
        _warning(
            report,
            "A price built only from assumptions is not labelled 'illustrative, built from assumptions'.",
            "仅基于假设得出的价格未注明「示意性，基于假设」。",
        )
    p0 = int((fact_payload or {}).get("p0_count") or 0)
    if p0:
        _warning(
            report,
            f"Fact check: {p0} figure(s) not found in any source on file (see logs/{FACT_CHECK_MD}).",
            f"数字核查：{p0} 个数字在已存档资料中找不到出处（见 logs/{FACT_CHECK_MD}）。",
        )

    if write_logs and run_path is not None:
        try:
            logs = run_path / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / CHECKS_REPORT_FILENAME).write_text(
                _render_report(findings, report), encoding="utf-8"
            )
            if fact_md:
                (logs / FACT_CHECK_MD).write_text(fact_md, encoding="utf-8")
            if fact_payload is not None:
                (logs / FACT_CHECK_JSON).write_text(
                    json.dumps(fact_payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except OSError:
            logger.warning("Buffett check logs could not be written", exc_info=True)
    return report
