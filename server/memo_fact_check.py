"""Deterministic fact check: every figure a memo states must be on file.

What counts as "on file" (the corpus): the curated fact ledger, the
research folder's documents and digests, the company's registry entry,
the source cache (what retrieval fetched — ``source_cache``), the sources
frozen with this run, and the firm's own records (transcripts, founder
updates, KPI rows, reference calls, evidence excerpts). Model output is
never corpus: the analysis-pass artifacts, the spine's pins and the
memo's own source titles cannot vouch for a number the model wrote.

Each figure ends up in one bucket:

- ``verified``    the source the sentence cites carries it;
- ``supported``   some source on file carries it — the same spelling, or
                  the same value in another spelling within one rounding
                  step ("$2.6B" is carried by "$2,580 million");
- ``derived``     a calculation note carries it;
- ``unsupported`` none of the above — the finding the gate reports.

The extractor is conservative on purpose, like the pin check: money,
percentages, multiples, scaled amounts ("40 million"), thousands-separated
counts and counted nouns ("30 customers", "95+ patents") are checked;
bare small integers, years, ids and citation tokens are not, because a
false positive costs a repair round and a false negative costs nothing
the memo did not already have.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import company_paths, numbers_lint, research_store, source_cache, storage

logger = logging.getLogger(__name__)

# Below this much evidence text (ledger, documents, retrieved sources,
# firm records) the check still reports, but nothing is enforced: with
# nothing to check against, every figure is "unsupported" and a repair
# would strip a memo of its numbers for no gain.
THIN_CORPUS_CHARS = 2_000
# Enforcement in "auto" mode needs a corpus this rich and this much of
# the memo already traceable before an unsupported figure is worth a
# repair round: past that point the figure, not the corpus, is the problem.
AUTO_ENFORCE_MIN_CHARS = 50_000
AUTO_ENFORCE_MIN_COVERAGE = 60
MAX_FED_FINDINGS = 12
MAX_DOC_CHARS = 300_000

_CITATION_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]")
_CITATION_ID_RE = re.compile(r"[SC]\d+")
_URL_RE = re.compile(r"https?://\S+", re.I)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")

_CURRENCY = r"(?:US\$|U\.S\.\$|USD\s?|\$|€|EUR\s?|£|GBP\s?|¥|JPY\s?|RMB\s?|CN¥|HK\$|A\$|C\$|S\$)"
_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_SCALE = r"(?:trillion|billion|million|thousand|tn|bn|mm|mn|k|m|b|t)"
_PCT = r"(?:%|percent(?:age points)?|pct\.?|pp|bps|basis points)"
_COUNT_NOUNS = (
    "customers|clients|patents|employees|staff|engineers|headcount|countries|"
    "markets|sites|stores|units|vehicles|contracts|partners|users|subscribers|"
    "deployments|locations|facilities|plants|hospitals|banks|logos|enterprises|"
    "installations|devices|sensors|satellites|aircraft|ships|vessels|trucks|"
    "robots|patients|trials|months|enterprises|accounts|merchants|suppliers|"
    "distributors|dealers|branches|offices|schools|universities|cities|states|"
    "projects|pilots|licenses|licences|shareholders|investors|founders|"
    "team members|people|megawatts|gigawatts|mw|gw|kwh|mwh|gwh|tons|tonnes|"
    "barrels|acres|hectares|square feet|sq ft|km|miles|nodes|towers|rigs|wells"
)

_FIGURE_RE = re.compile(
    rf"(?P<pct_range>{_NUM}\s?(?:–|—|-|to)\s?{_NUM}\s?{_PCT})(?![\w])"
    rf"|(?P<mult_range>{_NUM}\s?(?:–|—|-|to)\s?{_NUM}\s?(?:x|×))(?![\w])(?!\s?[$€£¥\d])"
    rf"|(?P<range>{_CURRENCY}?\s?{_NUM}\s?(?:–|—|-|to)\s?{_CURRENCY}?\s?{_NUM}\s?{_SCALE}?)(?![\w%.])"
    rf"|(?P<money>{_CURRENCY}\s?{_NUM}\s?{_SCALE}?)(?![\w%])"
    rf"|(?P<pct>{_NUM}\s?{_PCT})(?![\w])"
    rf"|(?P<mult>{_NUM}\s?(?:x|×))(?![\w])(?!\s?[$€£¥\d])"
    rf"|(?P<scaled>{_NUM}\s?{_SCALE})(?![\w])"
    rf"|(?P<thousands>\d{{1,3}}(?:,\d{{3}})+)(?![\w.]\d)"
    rf"|(?P<plus>\d{{2,}}(?:,\d{{3}})*\+)(?![\w])"
    rf"|(?P<counted>\d{{2,}}(?:,\d{{3}})*)(?=\s+(?:[a-z][\w-]*\s+){{0,2}}(?:{_COUNT_NOUNS})\b)",
    re.I,
)
_BARE_RE = re.compile(r"(?<![\w.,])\d{2,}(?:,\d{3})*(?:\.\d+)?(?![\w.])")
# A count preceded by one of these is an ordinal, a label or a window, not
# a fact about the company ("top 10 customers", "past 12 months", "page 12").
_NON_FACT_LEADERS = {
    "top", "first", "last", "next", "past", "prior", "previous", "another",
    "every", "each", "per", "page", "figure", "table", "section", "chapter",
    "step", "phase", "round", "series", "tier", "level", "grade", "class",
    "q", "fy", "h", "week", "day", "year", "item", "note", "rule", "form",
}
_SCALES = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}


@dataclass
class Figure:
    raw: str
    value: float
    klass: str  # "amount" (money or count), "pct", "mult"
    start: int
    end: int
    mantissa: str
    plus: bool = False

    @property
    def forms(self) -> set[str]:
        return numbers_lint._digits_forms(self.raw.rstrip("+"))


def _strip_citations(text: str) -> str:
    """Blank citation tokens and URLs so their digits are never figures."""
    out = _CITATION_RE.sub(lambda m: " " * len(m.group(0)), text)
    return _URL_RE.sub(lambda m: " " * len(m.group(0)), out)


def _parse_number(raw: str) -> tuple[float, str] | None:
    """``(value, mantissa)`` of a number with optional currency/scale."""
    text = raw.strip().rstrip("+").lower()
    text = re.sub(rf"^{_CURRENCY.lower()}\s?", "", text, flags=re.I)
    match = re.match(rf"({_NUM})\s?([a-z%.]*(?:\s+[a-z]+)*)$", text)
    if not match:
        return None
    mantissa = match.group(1)
    try:
        value = float(mantissa.replace(",", ""))
    except ValueError:
        return None
    unit = (match.group(2).split() or [""])[0].rstrip(".")
    return value * _SCALES.get(unit, 1.0), mantissa


def _significant(mantissa: str) -> tuple[int, int]:
    """Bounds on how many significant digits ``mantissa`` states.

    "500" may be "about five hundred" (2 significant, once the leading
    digit is joined by its neighbour) or exactly 500 (3); "2.58" is 3. The
    lower bound is never below 2: one significant digit would let $450M
    stand in for $500M, and those were different facts in the run that
    motivated this module.
    """
    digits = mantissa.replace(",", "").replace(".", "").lstrip("0")
    total = max(1, len(digits))
    nonzero = max(1, len(digits.rstrip("0")))
    lo = max(2, nonzero)
    return lo, max(lo, total)


def _rounds_to(value: float, target: float, sig: int) -> bool:
    if value == 0 or target == 0:
        return value == target
    if (value < 0) != (target < 0):
        return False
    value, target = abs(value), abs(target)
    magnitude = math.floor(math.log10(value))
    step = 10 ** (magnitude - sig + 1)
    rounded = math.floor(value / step + 0.5) * step
    return math.isclose(rounded, target, rel_tol=1e-9, abs_tol=1e-12)


def _value_supported(figure: Figure, values: dict[str, list[float]]) -> bool:
    """Whether some corpus value of a compatible class rounds to the figure."""
    candidates = values.get(figure.klass) or []
    if not candidates:
        return False
    lo, hi = _significant(figure.mantissa)
    target = figure.value
    for value in candidates:
        if math.isclose(value, target, rel_tol=1e-9, abs_tol=1e-12):
            return True
        for sig in range(lo, hi + 1):
            if _rounds_to(value, target, sig):
                return True
    return False


def extract_figures(text: str) -> list[Figure]:
    """Figures the memo asserts in ``text``, left to right."""
    cleaned = _strip_citations(text or "")
    out: list[Figure] = []
    for match in _FIGURE_RE.finditer(cleaned):
        kind = match.lastgroup or ""
        raw = match.group(0).strip()
        start, end = match.start(), match.end()
        before = cleaned[max(0, start - 3):start]
        # "10-K", "FY24", "Q3", "S-1", "H1" style identifiers are not figures.
        if re.search(r"[A-Za-z-]$", before.rstrip()) and not before.endswith(" "):
            continue
        if kind in {"counted", "plus", "thousands"}:
            leader = re.search(r"([A-Za-z]+)\s+$", cleaned[max(0, start - 16):start])
            if leader and leader.group(1).lower() in _NON_FACT_LEADERS:
                continue
        if kind == "range":
            out.extend(_range_figures(raw, start, cleaned))
            continue
        if kind in {"pct_range", "mult_range"}:
            out.extend(_unit_range_figures(raw, start, kind))
            continue
        parsed = _parse_number(raw)
        if parsed is None:
            continue
        value, mantissa = parsed
        if kind == "pct":
            unit = raw.lower()
            if "bps" in unit or "basis" in unit:
                value = value / 100.0
            klass = "pct"
        elif kind == "mult":
            if value > 1000:
                continue
            klass = "mult"
        else:
            if kind in {"thousands", "counted", "plus"} and _YEAR_RE.match(mantissa.replace(",", "")):
                continue
            if kind == "counted" and value < 10:
                continue
            klass = "amount"
        out.append(
            Figure(
                raw=raw,
                value=value,
                klass=klass,
                start=start,
                end=end,
                mantissa=mantissa,
                plus=raw.endswith("+"),
            )
        )
    return out


def _range_figures(raw: str, start: int, text: str) -> list[Figure]:
    """"$20–25M" / "$1.2 to $1.5B" / "20-25%" as two figures sharing the
    scale and currency the range states once. A range with neither a
    currency nor a scale is a bare pair ("3-5") and is skipped."""
    match = re.match(
        rf"(?P<c1>{_CURRENCY})?\s?(?P<n1>{_NUM})\s?(?:–|—|-|to)\s?(?P<c2>{_CURRENCY})?\s?(?P<n2>{_NUM})\s?(?P<scale>{_SCALE})?$",
        raw,
        re.I,
    )
    if not match:
        return []
    currency = match.group("c1") or match.group("c2")
    scale = match.group("scale") or ""
    if not currency and not scale:
        return []
    out: list[Figure] = []
    for key in ("n1", "n2"):
        mantissa = match.group(key)
        if _YEAR_RE.match(mantissa) and not currency and not scale:
            continue
        parsed = _parse_number(f"{mantissa}{scale}")
        if parsed is None:
            continue
        piece = f"{currency or ''}{mantissa}{scale}"
        offset = raw.find(mantissa)
        out.append(
            Figure(
                raw=piece,
                value=parsed[0],
                klass="amount",
                start=start + max(0, offset),
                end=start + max(0, offset) + len(mantissa),
                mantissa=mantissa,
            )
        )
    return out


def _unit_range_figures(raw: str, start: int, kind: str) -> list[Figure]:
    """"20-25%" / "1.5–2.0x" as two figures sharing the trailing unit."""
    match = re.match(rf"(?P<n1>{_NUM})\s?(?:–|—|-|to)\s?(?P<n2>{_NUM})\s?(?P<unit>.+)$", raw, re.I)
    if not match:
        return []
    unit = match.group("unit").strip()
    out: list[Figure] = []
    for key in ("n1", "n2"):
        mantissa = match.group(key)
        parsed = _parse_number(mantissa)
        if parsed is None:
            continue
        value = parsed[0]
        if kind == "pct_range":
            klass = "pct"
            if "bps" in unit.lower() or "basis" in unit.lower():
                value = value / 100.0
        else:
            klass = "mult"
            if value > 1000:
                continue
        offset = raw.find(mantissa)
        out.append(
            Figure(
                raw=f"{mantissa}{unit if klass == 'pct' and unit == '%' else (' ' + unit if klass == 'pct' else unit)}",
                value=value,
                klass=klass,
                start=start + max(0, offset),
                end=start + max(0, offset) + len(mantissa),
                mantissa=mantissa,
            )
        )
    return out


@dataclass
class TextIndex:
    """What one text can vouch for: the exact spellings of its figures
    (in every canonical form) and their values by class. Membership is
    O(1), so a 200-figure memo checks against a multi-megabyte corpus in
    milliseconds instead of re-scanning it per figure."""

    forms: set[str] = field(default_factory=set)
    values: dict[str, list[float]] = field(default_factory=lambda: {"amount": [], "pct": [], "mult": []})

    @classmethod
    def of(cls, text: str) -> "TextIndex":
        index = cls()
        index.values = corpus_values(text)
        cleaned = _strip_citations(text or "")
        for figure in extract_figures(cleaned):
            index.forms |= figure.forms
        for match in _BARE_RE.finditer(cleaned):
            index.forms.add(match.group(0).replace(",", "").lower())
        return index

    def merge(self, other: "TextIndex") -> None:
        self.forms |= other.forms
        for klass, found in other.values.items():
            self.values.setdefault(klass, []).extend(found)

    def supports(self, figure: Figure) -> bool:
        if figure.forms & self.forms:
            return True
        return _value_supported(figure, self.values)


def corpus_values(text: str) -> dict[str, list[float]]:
    """Every number a source text carries, by class — the permissive side
    of the match, so a memo's "30 customers" is carried by a KPI row that
    says only "30"."""
    values: dict[str, list[float]] = {"amount": [], "pct": [], "mult": []}
    cleaned = _strip_citations(text or "")
    covered: list[tuple[int, int]] = []
    for figure in extract_figures(cleaned):
        values[figure.klass].append(figure.value)
        covered.append((figure.start, figure.end))
    for match in _BARE_RE.finditer(cleaned):
        if any(start <= match.start() < end for start, end in covered):
            continue
        mantissa = match.group(0)
        if _YEAR_RE.match(mantissa):
            continue
        try:
            values["amount"].append(float(mantissa.replace(",", "")))
        except ValueError:
            continue
    return values


# ---- corpus ----------------------------------------------------------------


@dataclass
class Corpus:
    texts: list[tuple[str, str]] = field(default_factory=list)  # (label, text)
    evidence_labels: list[str] = field(default_factory=list)
    evidence_chars: int = 0
    index: TextIndex = field(default_factory=TextIndex)

    def add(self, label: str, text: str, *, evidence: bool = True) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if len(text) > MAX_DOC_CHARS:
            text = text[:MAX_DOC_CHARS]
        self.texts.append((label, text))
        if evidence:
            self.evidence_labels.append(label)
            self.evidence_chars += len(text)

    def finish(self) -> "Corpus":
        index = TextIndex()
        for _, text in self.texts:
            index.merge(TextIndex.of(text))
        index.values = {klass: sorted(set(found)) for klass, found in index.values.items()}
        self.index = index
        return self

    @property
    def thin(self) -> bool:
        return self.evidence_chars < THIN_CORPUS_CHARS

    def summary(self) -> str:
        parts = [f"{len(self.texts)} texts", f"{self.evidence_chars:,} evidence chars"]
        return ", ".join(parts)

    def describe(self) -> list[dict]:
        return [{"label": label, "chars": len(text)} for label, text in self.texts]


_DIGEST_FILES = {"known_sources.md"}


def _research_folder_texts(research_dir: Path | None) -> list[tuple[str, str]]:
    """Text of every document and digest in the research folder, extracted
    the way the Gemini path reads them (PDF, DOCX, PPTX, text)."""
    if research_dir is None:
        return []
    root = Path(research_dir)
    if not root.is_dir():
        return []
    from . import memo_engine

    out: list[tuple[str, str]] = []
    try:
        entries = sorted(p for p in root.iterdir() if p.is_file())
    except OSError:
        return []
    for path in entries:
        name = path.name
        if name.startswith("index.yaml") or name.endswith(".progress.jsonl") or name in _DIGEST_FILES:
            continue
        try:
            text = memo_engine.file_text(path)
        except Exception:  # noqa: BLE001
            logger.warning("fact check: could not read %s", path, exc_info=True)
            continue
        if text.strip():
            out.append((f"research file: {name}", text))
    return out


def build_corpus(
    company_id: str,
    *,
    run_dir: Path | None = None,
    research_dir: Path | None = None,
) -> Corpus:
    """Everything on file for ``company_id`` that can vouch for a figure."""
    corpus = Corpus()
    if research_dir is None:
        try:
            research_dir = research_store.RESEARCH_ROOT / company_paths.storage_key(company_id)
        except ValueError:
            research_dir = None
    for label, text in _research_folder_texts(research_dir):
        corpus.add(label, text)
    try:
        from . import claude_runner

        entry = claude_runner._extract_company_registry_entry_yaml(
            storage.COMPANIES_FILE, company_id
        )
        if entry:
            corpus.add("registry entry", entry, evidence=False)
    except Exception:  # noqa: BLE001
        logger.debug("fact check: no registry entry for %s", company_id, exc_info=True)
    for label, text in source_cache.corpus_texts(company_id):
        corpus.add(label, text)
    if run_dir is not None:
        cached_files = {
            str(row.get("file"))
            for row in source_cache.list_sources(company_id)
        }
        for label, text in source_cache.run_source_texts(run_dir):
            file_hint = label.split("run source ", 1)[-1].split(":", 1)[0]
            if f"{file_hint}.txt" in cached_files:
                continue  # the company cache already carries this text
            corpus.add(label, text)
    try:
        texts, labels = numbers_lint._corpus(company_id)
    except Exception:  # noqa: BLE001
        logger.debug("fact check: firm corpus unavailable for %s", company_id, exc_info=True)
        texts, labels = [], []
    for index, text in enumerate(texts):
        if not str(text or "").strip():
            continue
        label = labels[min(index, len(labels) - 1)] if labels else "firm record"
        corpus.add(f"firm record: {label}", text, evidence=label != "company record")
    return corpus.finish()


# ---- the check --------------------------------------------------------------


@dataclass
class FactFinding:
    code: str
    section_id: str
    location: str
    figure: str
    snippet: str
    detail: str
    severity: str = "P0"
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "section_id": self.section_id,
            "location": self.location,
            "figure": self.figure,
            "snippet": self.snippet,
            "suggestion": self.detail,
            "severity": self.severity,
            "citations": list(self.citations),
        }


@dataclass
class FactCheckResult:
    checked: int = 0
    verified: int = 0
    supported: int = 0
    derived: int = 0
    unsupported: int = 0
    unverifiable_citations: int = 0
    findings: list[FactFinding] = field(default_factory=list)
    corpus_summary: str = ""
    corpus_texts: list[dict] = field(default_factory=list)
    evidence_chars: int = 0
    thin_corpus: bool = False
    repair_feed: bool = False
    repair_feed_reason: str = ""
    error: str | None = None

    @property
    def coverage_pct(self) -> int | None:
        if not self.checked:
            return None
        return round((self.checked - self.unsupported) / self.checked * 100)

    @property
    def unsupported_findings(self) -> list[FactFinding]:
        return [f for f in self.findings if f.code == "unsupported_figure"]

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if not self.checked:
            return "skipped"
        if not self.unsupported:
            return "pass"
        return "warn" if self.thin_corpus or not self.repair_feed else "fail"

    def to_dict(self) -> dict:
        unsupported = self.unsupported_findings
        return {
            "status": self.status,
            "checked": self.checked,
            "verified": self.verified,
            "supported": self.supported,
            "derived": self.derived,
            "unsupported": self.unsupported,
            "unverifiable_citations": self.unverifiable_citations,
            "coverage_pct": self.coverage_pct,
            "evidence_chars": self.evidence_chars,
            "thin_corpus": self.thin_corpus,
            "repair_feed": self.repair_feed,
            "repair_feed_reason": self.repair_feed_reason,
            "corpus": self.corpus_texts,
            "p0_count": len(unsupported) if not self.thin_corpus else 0,
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings[:60]],
            "error": self.error,
        }

    def summary_lines(self) -> list[str]:
        """Findings as repair feedback, shaped like the pin-check lines so
        the error→section mapper routes each to its owning section. Only
        unsupported figures are fed; a citation mismatch is a note for the
        analyst, not a rewrite instruction. Empty unless enforcement is on."""
        if not self.repair_feed:
            return []
        lines = []
        for finding in self.unsupported_findings[:MAX_FED_FINDINGS]:
            lines.append(
                f"fact check {finding.code} in section {finding.section_id}: "
                f"\"{finding.snippet}\" — {finding.detail}"
            )
        return lines


def _loc(value: Any) -> str:
    if isinstance(value, dict):
        en = value.get("en")
        return en if isinstance(en, str) else ""
    return value if isinstance(value, str) else ""


_SKIP_KEYS = {"id", "type", "component", "level", "source_ids", "zh", "kind", "slug", "style"}


def _iter_block_strings(value: Any, path: str = ""):
    """``(path, text)`` for every English string in a block, skipping ids
    and Chinese twins. Dicts with an ``en`` key yield only that string."""
    if isinstance(value, dict):
        if isinstance(value.get("en"), str):
            yield path, value["en"]
            return
        for key, item in value.items():
            if key in _SKIP_KEYS:
                continue
            yield from _iter_block_strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_block_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _citations_in(text: str) -> list[str]:
    ids: list[str] = []
    for token in _CITATION_RE.findall(text or ""):
        ids.extend(_CITATION_ID_RE.findall(token))
    return ids


def _calc_texts(package: dict) -> dict[str, str]:
    """What each calculation note DERIVES: its result, its meaning, and the
    right-hand side of every "=" in its formula. Inputs and the left-hand
    side are what the note consumes; those figures must be sourced on
    their own, or a note could launder any number by using it once."""
    out: dict[str, str] = {}
    for calc in package.get("calculations") or []:
        if not isinstance(calc, dict):
            continue
        calc_id = str(calc.get("id") or "").strip()
        if not calc_id:
            continue
        parts = []
        for key in ("result", "meaning"):
            parts.append(_loc(calc.get(key)) or str(calc.get(key) or ""))
        formula = _loc(calc.get("formula")) or str(calc.get("formula") or "")
        for segment in formula.split("=")[1:]:
            # "13 × $200B = $2.6T; $2.6T ÷ $1.75T = 1.5x": keep "$2.6T" and
            # "1.5x", not the "$2.6T ÷ $1.75T" that feeds the second step.
            parts.append(re.split(r"[;,]|\band\b", segment, maxsplit=1)[0] if "÷" in segment or "×" in segment or "*" in segment or "/" in segment else segment)
        out[calc_id] = " \n ".join(parts)
    return out


def _source_texts(package: dict, company_id: str, run_dir: Path | None) -> dict[str, str]:
    """Text on file for each package source, by id, when its URL (or a
    strong title match) points at a cached page."""
    out: dict[str, str] = {}
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
    for source in package.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            continue
        url = source.get("url")
        record = source_cache.find_by_url(company_id, url) if url else None
        text = ""
        if record is not None:
            text = source_cache.source_text(company_id, record)
        canon = source_cache.canonical_url(url) if url else None
        if not text and canon and canon in run_texts:
            text = run_texts[canon]
        if not text and not url:
            match = source_cache.match_title(company_id, _loc(source.get("title")) or "", min_score=0.75)
            if match is not None:
                text = source_cache.source_text(company_id, match)
        if text:
            out[source_id] = text
    return out


def _repair_policy(corpus: Corpus, coverage: int | None) -> tuple[bool, str]:
    raw = os.environ.get("BSH_MEMO_FACT_CHECK_REPAIR", "auto").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False, "BSH_MEMO_FACT_CHECK_REPAIR=0: report only"
    if corpus.thin:
        return False, f"corpus too thin to enforce ({corpus.evidence_chars:,} evidence chars < {THIN_CORPUS_CHARS:,})"
    if raw in {"1", "true", "yes", "on"}:
        return True, "BSH_MEMO_FACT_CHECK_REPAIR=1"
    if corpus.evidence_chars < AUTO_ENFORCE_MIN_CHARS:
        return False, (
            f"auto: corpus has {corpus.evidence_chars:,} evidence chars, enforcement starts at "
            f"{AUTO_ENFORCE_MIN_CHARS:,}"
        )
    if coverage is not None and coverage < AUTO_ENFORCE_MIN_COVERAGE:
        return False, (
            f"auto: only {coverage}% of figures traceable, enforcement starts at "
            f"{AUTO_ENFORCE_MIN_COVERAGE}% (the corpus, not the memo, is short)"
        )
    return True, "auto: corpus rich enough to enforce"


def check_package(
    package: dict,
    corpus: Corpus,
    *,
    source_texts: dict[str, str] | None = None,
) -> FactCheckResult:
    """Check every figure in the package's sections against the corpus."""
    result = FactCheckResult(
        corpus_summary=corpus.summary(),
        corpus_texts=corpus.describe(),
        evidence_chars=corpus.evidence_chars,
        thin_corpus=corpus.thin,
    )
    if not isinstance(package, dict):
        result.error = "memo package must be a JSON object"
        return result
    source_texts = source_texts or {}
    source_index = {sid: TextIndex.of(text) for sid, text in source_texts.items()}
    calc_texts = _calc_texts(package)
    calc_index = {cid: TextIndex.of(text) for cid, text in calc_texts.items()}
    corpus_label = corpus.summary()

    for s_index, section in enumerate(package.get("sections") or []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or f"sections[{s_index}]")
        for b_index, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict) or block.get("type") == "heading":
                continue
            location_base = f"sections[{s_index}].blocks[{b_index}]"
            for path, text in _iter_block_strings(block):
                figures = extract_figures(text)
                if not figures:
                    continue
                cited = _citations_in(text)
                cited_sources = [c for c in cited if c.startswith("S")]
                cited_calcs = [c for c in cited if c.startswith("C")]
                for figure in figures:
                    result.checked += 1
                    # 1. Derived by a note the sentence cites.
                    if any(cid in calc_index and calc_index[cid].supports(figure) for cid in cited_calcs):
                        result.derived += 1
                        continue
                    # 2. Verified: the cited source's own text carries it.
                    with_text = [sid for sid in cited_sources if sid in source_index]
                    if with_text and any(source_index[sid].supports(figure) for sid in with_text):
                        result.verified += 1
                        continue
                    if cited_sources and not with_text:
                        result.unverifiable_citations += 1
                    # 3. Derived by any note (the sentence forgot the [C#]).
                    if any(index.supports(figure) for index in calc_index.values()):
                        result.derived += 1
                        continue
                    # 4. Supported: anything on file carries it.
                    if corpus.index.supports(figure):
                        result.supported += 1
                        if with_text:
                            result.findings.append(
                                FactFinding(
                                    code="citation_mismatch",
                                    section_id=section_id,
                                    location=f"{location_base}.{path}" if path else location_base,
                                    figure=figure.raw,
                                    snippet=_excerpt(text, figure),
                                    detail=(
                                        f"{figure.raw} is on file, but not in the text of the cited "
                                        f"source{'s' if len(with_text) > 1 else ''} {', '.join(with_text)}; "
                                        "check the citation"
                                    ),
                                    severity="P1",
                                    citations=list(cited_sources),
                                )
                            )
                        continue
                    result.unsupported += 1
                    result.findings.append(
                        FactFinding(
                            code="unsupported_figure",
                            section_id=section_id,
                            location=f"{location_base}.{path}" if path else location_base,
                            figure=figure.raw,
                            snippet=_excerpt(text, figure),
                            detail=(
                                f"the figure {figure.raw} appears in none of the sources on file "
                                f"({corpus_label}); cite the source that carries it — adding it to the "
                                "package sources with its URL if it is missing — or state it as an "
                                "estimate with a [C#] calculation note whose inputs are sourced"
                            ),
                            severity="P0",
                            citations=list(cited),
                        )
                    )
    result.repair_feed, result.repair_feed_reason = _repair_policy(corpus, result.coverage_pct)
    return result


def _excerpt(text: str, figure: Figure, *, width: int = 70) -> str:
    lo = max(0, figure.start - width)
    hi = min(len(text), figure.end + width)
    piece = " ".join(text[lo:hi].split())
    return (("…" if lo > 0 else "") + piece + ("…" if hi < len(text) else ""))[:220]


def check_memo_run(
    *,
    run_dir: Path,
    package: dict,
    company_id: str,
    research_dir: Path | None = None,
) -> FactCheckResult:
    """The gate's entry point: build the corpus for this run and check."""
    try:
        corpus = build_corpus(company_id, run_dir=run_dir, research_dir=research_dir)
        source_texts = _source_texts(package, company_id, run_dir)
        return check_package(package, corpus, source_texts=source_texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memo fact check failed", exc_info=True)
        result = FactCheckResult()
        result.error = f"{type(exc).__name__}: {exc}"
        return result


def render_markdown_report(result: FactCheckResult, *, attempt: int | None = None) -> str:
    lines = ["# Memo fact check", ""]
    if attempt is not None:
        lines.append(f"Attempt: {attempt}")
    lines.extend(
        [
            f"Status: {result.status}",
            f"Figures checked: {result.checked}",
            f"- verified in the cited source: {result.verified}",
            f"- supported by a source on file: {result.supported}",
            f"- derived in a calculation note: {result.derived}",
            f"- unsupported: {result.unsupported}",
            f"- citations without text on file: {result.unverifiable_citations}",
            f"Coverage: {result.coverage_pct if result.coverage_pct is not None else 'n/a'}%",
            f"Corpus: {result.corpus_summary}",
            f"Enforced (fed to repair): {'yes' if result.repair_feed else 'no'} — {result.repair_feed_reason}",
        ]
    )
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.corpus_texts:
        lines.extend(["", "## Sources on file"])
        for row in result.corpus_texts[:80]:
            lines.append(f"- {row['label']} ({row['chars']:,} chars)")
        if len(result.corpus_texts) > 80:
            lines.append(f"- … and {len(result.corpus_texts) - 80} more")
    lines.extend(["", "## Findings"])
    if not result.findings:
        lines.append("None.")
    for finding in result.findings:
        lines.append(
            f"- [{finding.severity}] {finding.code} — {finding.figure} in {finding.section_id} "
            f"({finding.location}): \"{finding.snippet}\" — {finding.detail}"
        )
    return "\n".join(lines) + "\n"


# ---- deterministic URL attachment ------------------------------------------


def _artifact_url_candidates(run_dir: Path | None) -> list[tuple[str, str]]:
    """``(source name, url)`` pairs the analysis passes recorded."""
    if run_dir is None:
        return []
    fast_dir = Path(run_dir) / "analysis" / "fast"
    out: list[tuple[str, str]] = []
    try:
        files = sorted(fast_dir.glob("*.json"))
    except OSError:
        return []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for item in payload.get("supporting_evidence") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if source_cache.canonical_url(url):
                out.append((str(item.get("source") or ""), str(url).strip()))
    return out


def _best_url_match(title: str, candidates: list[tuple[str, str]], *, min_score: float = 0.6) -> tuple[str, str, float] | None:
    query = source_cache.significant_tokens(title)
    if len(query) < 2:
        return None
    best: tuple[str, str, float] | None = None
    for name, url in candidates:
        tokens = source_cache.significant_tokens(name) | source_cache.significant_tokens(
            re.sub(r"[/._-]+", " ", url.split("://", 1)[-1])
        )
        if not tokens:
            continue
        score = len(query & tokens) / len(query)
        if score >= min_score and (best is None or score > best[2]):
            best = (name, url, score)
    return best


# Files the pipeline writes into a research folder by itself, from the web:
# the known-sources digest and the tracked-news digest. They can vouch for a
# figure, but they are not private material — a source drawn from them came
# from a page a reader can open, so it has a URL to carry.
_WEB_DIGEST_FILES = {"known_sources.md", "recent_news.md"}


def private_material_on_file(
    company_id: str, *, research_dir: Path | None = None
) -> list[str]:
    """What the firm holds on this company that a reader cannot browse to:
    research-folder documents (not the web digests the pipeline writes
    there), founder updates and KPI rows, call transcripts and reference
    calls. One label per kind found; empty means there is nothing private
    on file, so no source in the memo can honestly be one.

    The renderer's URL rule exempts a source whose class or title says it is
    private. Nothing checked that claim, and live on 2026-09-21 a RadixArk
    Gemini memo — no research folder, no uploads, nothing private at all —
    classed three public sources as "internal document" and passed, because
    the rule's own error message told it that was the way out.
    """
    found: list[str] = []
    if research_dir is None:
        try:
            research_dir = research_store.RESEARCH_ROOT / company_paths.storage_key(company_id)
        except ValueError:
            research_dir = None
    root = Path(research_dir) if research_dir is not None else None
    if root is not None and root.is_dir():
        try:
            for path in sorted(p for p in root.iterdir() if p.is_file()):
                name = path.name
                if (
                    name.startswith("index.yaml")
                    or name.endswith(".progress.jsonl")
                    or name in _WEB_DIGEST_FILES
                ):
                    continue
                if path.stat().st_size > 0:
                    found.append(f"research file: {name}")
        except OSError:
            logger.warning("private material: could not list %s", root, exc_info=True)
    try:
        from . import portfolio

        if portfolio.has_record(company_id):
            record = portfolio.get_portfolio(company_id)
            if record.get("updates") or record.get("kpis"):
                found.append("founder updates / KPI rows")
    except Exception:  # noqa: BLE001
        logger.debug("private material: no portfolio record for %s", company_id, exc_info=True)
    try:
        from . import transcripts

        if any(t.get("company_id") == company_id for t in transcripts.all_transcripts()):
            found.append("call transcripts")
    except Exception:  # noqa: BLE001
        logger.debug("private material: transcripts unavailable", exc_info=True)
    try:
        from . import ic_room

        if ic_room.list_reference_calls(company_id).get("items"):
            found.append("reference calls")
    except Exception:  # noqa: BLE001
        logger.debug("private material: reference calls unavailable", exc_info=True)
    return found


def stamp_private_material(
    package: dict, *, company_id: str, research_dir: Path | None = None
) -> list[str]:
    """Record on the package envelope whether the firm holds anything private
    on this company, so the renderer's URL rule can tell an honest "internal
    document" from a public page that dropped its URL. Returns the labels."""
    found = private_material_on_file(company_id, research_dir=research_dir)
    if isinstance(package, dict):
        run = package.get("run")
        if not isinstance(run, dict):
            run = {}
            package["run"] = run
        run["private_material_on_file"] = bool(found)
    return found


def attach_source_urls(package: dict, *, company_id: str, run_dir: Path | None) -> list[str]:
    """Fill in ``url`` on package sources that lack one, from what this
    run's analysis passes recorded and from the company's source cache.
    Deterministic and logged: returns one line per attachment. Only a
    strong title match attaches, so a wrong URL is far rarer than a
    missing one — and a missing one fails validation, where the repair
    can still supply it."""
    if not isinstance(package, dict):
        return []
    sources = package.get("sources")
    if not isinstance(sources, list):
        return []
    artifact_candidates = _artifact_url_candidates(run_dir)
    try:
        page_candidates = [
            (str(page.get("title") or ""), str(page.get("url") or ""))
            for page in source_cache.known_pages(company_id, limit=200)
        ]
    except ValueError:
        page_candidates = []
    notes: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        if str(source.get("url") or "").strip():
            continue
        title = _loc(source.get("title")) or str(source.get("title") or "")
        if not title.strip():
            continue
        match = _best_url_match(title, artifact_candidates)
        origin = "analysis artifact"
        if match is None:
            match = _best_url_match(title, page_candidates, min_score=0.7)
            origin = "known source"
        if match is None:
            continue
        name, url, score = match
        source["url"] = url
        notes.append(
            f"{source.get('id')} ← {url} (matched {origin} '{name[:80]}', score {score:.2f})"
        )
    return notes


# ---- company-level view (the research desk card) ---------------------------


def check_company(company_id: str) -> dict:
    """The latest memo package for ``company_id`` checked against everything
    on file — the payload behind the research desk's numbers card."""
    from . import comps

    path, package = comps._latest_memo_package(company_id)
    base = {
        "company_id": company_id,
        "memo_package": str(path) if path else None,
        "checked": 0,
        "supported": 0,
        "unsupported": 0,
        "coverage_pct": None,
        "findings": [],
        "sources": [],
    }
    if not package or path is None:
        base["note"] = "No memo package on record"
        return base
    run_dir = path.parent.parent if path.parent.name == "logs" else path.parent
    result = check_memo_run(run_dir=run_dir, package=package, company_id=company_id)
    titles = {
        str(section.get("id")): _loc(section.get("title")) or str(section.get("id"))
        for section in package.get("sections") or []
        if isinstance(section, dict)
    }
    base.update(
        {
            "checked": result.checked,
            "supported": result.checked - result.unsupported,
            "verified": result.verified,
            "derived": result.derived,
            "unsupported": result.unsupported,
            "coverage_pct": result.coverage_pct,
            "status": result.status,
            "thin_corpus": result.thin_corpus,
            "evidence_chars": result.evidence_chars,
            "findings": [
                {
                    "section": titles.get(f.section_id, f.section_id),
                    "number": f.figure,
                    "excerpt": f.snippet,
                    "code": f.code,
                    "looked_for": sorted(numbers_lint._digits_forms(f.figure.rstrip("+")))[:4],
                }
                for f in result.findings
                if f.code == "unsupported_figure"
            ],
            "sources": [row["label"] for row in result.corpus_texts][:60],
            "note": (
                "A figure counts as supported when a source on file carries the same value "
                "in any spelling, or a calculation note derives it."
                + (" The corpus is thin: add a fact ledger, documents or run a memo so retrieval is cached." if result.thin_corpus else "")
            ),
            "error": result.error,
        }
    )
    return base
