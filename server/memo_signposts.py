"""Signposts, phase 1 (R32): the falsifiable things a memo says it watches.

``extract(package)`` returns every signpost a memo package states, in one
shape the next phase's store can track against what actually happens::

    {id, claim_en, claim_zh, kind: "metric"|"event"|"price", metric,
     threshold, direction: "above"|"below"|None, due_by, links_to_risk,
     source_section, origin: "package"|"monitoring_table"|"risk_card"}

- the package's own optional top-level ``signposts[]`` (the writer's list,
  when the model supplied one), else
- derived deterministically from what every package already carries: the
  monitoring table (Indicator | Current value | Trigger threshold |
  Response — "Monitoring Indicators" / "What changes the verdict") and the
  risk cards' "What we watch" rows.

``echo_findings(package)`` checks that each writer-supplied signpost is
stated somewhere in the memo — a signpost the document never states is one
no reader will hold the memo to. Warnings only.

Nothing here calls a model, and signposts are never rendered into the
document (the voice contract bans checklist lists in the LP memo).
"""
from __future__ import annotations

import re
from typing import Any

KINDS = ("metric", "event", "price")
DIRECTIONS = ("above", "below")
MAX_SIGNPOSTS = 24

_PRICE_RE = re.compile(
    r"\b(?:valuation|post-money|pre-money|price|share price|entry|mark)\b", re.IGNORECASE
)
_NUMBER_RE = re.compile(r"\d")
_BELOW_RE = re.compile(r"(?:[≤<]|\bbelow\b|\bunder\b|\bless than\b|\bat or below\b|\bfalls?\b|\bdrops?\b)", re.IGNORECASE)
_ABOVE_RE = re.compile(r"(?:[≥>]|\babove\b|\bover\b|\bmore than\b|\bat least\b|\bexceeds?\b|\brises?\b)", re.IGNORECASE)
_QUARTER_RE = re.compile(r"\b(?:Q([1-4])\s*(?:FY)?\s*((?:19|20)\d{2})|((?:19|20)\d{2})\s*Q([1-4]))\b", re.IGNORECASE)
_YEAR_MONTH_RE = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])\b")
_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_YEAR_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+((?:19|20)\d{2})\b")
# Digits, not word boundaries, delimit a bare year: "by FY2027" and
# "by 2027E" are due dates too.
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_WORD_RE = re.compile(r"[a-z0-9]+")
_CITATION_RE = re.compile(r"\s*\[[SC]\d+(?:\s*,\s*[SC]\d+)*\]")
_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "with", "is", "are",
    "at", "by", "from", "each", "every", "its", "our", "we", "this", "that",
}


def _text(value: Any, locale: str = "en") -> str:
    if isinstance(value, dict):
        chosen = value.get(locale)
        return str(chosen or "").strip()
    if value is None:
        return ""
    return str(value).strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _CITATION_RE.sub("", str(text or ""))).strip()


def direction_of(text: str) -> str | None:
    """"above" / "below" from a threshold's comparator; None when it names
    neither (or both)."""
    below = bool(_BELOW_RE.search(text or ""))
    above = bool(_ABOVE_RE.search(text or ""))
    if below == above:
        return None
    return "below" if below else "above"


def due_by_of(text: str) -> str | None:
    """The date a signpost is due, as written precision: "2026-Q3",
    "2026-09", "2026" — None when the text names no date."""
    source = str(text or "")
    match = _QUARTER_RE.search(source)
    if match:
        quarter = match.group(1) or match.group(4)
        year = match.group(2) or match.group(3)
        return f"{year}-Q{quarter}"
    match = _YEAR_MONTH_RE.search(source)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    for match in _MONTH_YEAR_RE.finditer(source):
        month = _MONTHS.get(match.group(1).lower())
        if month:
            return f"{match.group(2)}-{month:02d}"
    match = _YEAR_RE.search(source)
    return match.group(1) if match else None


def _kind_of(*texts: str) -> str:
    joined = " ".join(texts)
    if _PRICE_RE.search(joined):
        return "price"
    return "metric" if _NUMBER_RE.search(joined) else "event"


def _row_cells(row: Any) -> list[Any]:
    if isinstance(row, dict):
        cells = row.get("cells")
        return list(cells) if isinstance(cells, list) else []
    return list(row) if isinstance(row, (list, tuple)) else []


def _is_monitoring_table(block: dict) -> bool:
    headers = [_text(header).lower() for header in block.get("headers") or []]
    return any("indicator" in h for h in headers) and any("trigger" in h for h in headers)


def _from_package(package: dict) -> list[dict]:
    rows: list[dict] = []
    for index, raw in enumerate(package.get("signposts") or []):
        if not isinstance(raw, dict):
            continue
        claim_en = _clean(_text(raw.get("claim_en")) or _text(raw.get("claim"), "en"))
        if not claim_en:
            continue
        kind = str(raw.get("kind") or "").strip().lower()
        direction = str(raw.get("direction") or "").strip().lower()
        threshold = _clean(_text(raw.get("threshold")))
        rows.append(
            {
                "id": str(raw.get("id") or f"SP{index + 1}").strip()[:12],
                "claim_en": claim_en,
                "claim_zh": _clean(_text(raw.get("claim_zh")) or _text(raw.get("claim"), "zh")),
                "kind": kind if kind in KINDS else _kind_of(claim_en),
                "metric": _clean(_text(raw.get("metric"))) or None,
                "threshold": threshold or None,
                "direction": direction if direction in DIRECTIONS else direction_of(threshold or claim_en),
                "due_by": _clean(_text(raw.get("due_by"))) or due_by_of(claim_en),
                "links_to_risk": _clean(_text(raw.get("links_to_risk"))) or None,
                "source_section": str(raw.get("source_section") or "").strip() or None,
                "origin": "package",
            }
        )
    return rows


def _derived(package: dict) -> list[dict]:
    rows: list[dict] = []
    for section in package.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "").strip() or None
        last_heading = {"en": "", "zh": ""}
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "heading":
                last_heading = {"en": _clean(_text(block.get("text"))), "zh": _clean(_text(block.get("text"), "zh"))}
                continue
            if block.get("type") != "table":
                continue
            if _is_monitoring_table(block):
                for row in block.get("rows") or []:
                    cells = _row_cells(row)
                    if len(cells) < 3:
                        continue
                    indicator, current, threshold = (_clean(_text(c)) for c in cells[:3])
                    indicator_zh, current_zh, threshold_zh = (_clean(_text(c, "zh")) for c in cells[:3])
                    if not indicator or not threshold:
                        continue
                    claim_en = f"{indicator}: {threshold}" + (f" (now {current})" if current else "")
                    claim_zh = (
                        f"{indicator_zh}：{threshold_zh}" + (f"（当前 {current_zh}）" if current_zh else "")
                        if indicator_zh and threshold_zh
                        else ""
                    )
                    rows.append(
                        {
                            "claim_en": claim_en,
                            "claim_zh": claim_zh,
                            "kind": _kind_of(indicator, threshold),
                            "metric": indicator,
                            "threshold": threshold,
                            "direction": direction_of(threshold),
                            "due_by": due_by_of(f"{indicator} {threshold}"),
                            "links_to_risk": None,
                            "source_section": section_id,
                            "origin": "monitoring_table",
                        }
                    )
                continue
            if block.get("layout") != "key_value":
                continue
            for row in block.get("rows") or []:
                cells = _row_cells(row)
                if len(cells) != 2 or not _text(cells[0]).lower().startswith("what we watch"):
                    continue
                claim_en = _clean(_text(cells[1]))
                if not claim_en:
                    continue
                rows.append(
                    {
                        "claim_en": claim_en,
                        "claim_zh": _clean(_text(cells[1], "zh")),
                        "kind": _kind_of(claim_en),
                        "metric": None,
                        "threshold": None,
                        "direction": direction_of(claim_en),
                        "due_by": due_by_of(claim_en),
                        "links_to_risk": last_heading["en"] or None,
                        "source_section": section_id,
                        "origin": "risk_card",
                    }
                )
    for index, row in enumerate(rows, start=1):
        row["id"] = f"SP{index}"
    return [{"id": row.pop("id"), **row} for row in rows]


def extract(package: Any) -> list[dict]:
    """Every signpost ``package`` states (see the module docstring), the
    writer's own list first; [] for anything that is not a package."""
    if not isinstance(package, dict):
        return []
    rows = _from_package(package) or _derived(package)
    return rows[:MAX_SIGNPOSTS]


def _document_text(package: dict) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "en" in value and isinstance(value.get("en"), str):
                parts.append(value["en"])
                return
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            parts.append(value)

    walk(package.get("sections"))
    return re.sub(r"\s+", " ", _CITATION_RE.sub("", " \n ".join(parts))).casefold()


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in _WORD_RE.findall(str(text or "").casefold())
        if len(token) > 2 and token not in _STOPWORDS
    ]


def echo_findings(package: Any) -> list[dict]:
    """Writer-supplied signposts the memo never states: ``[{id, claim,
    detail}]``. Matched generously — verbatim, else most of the claim's
    significant words — so a reworded restatement passes."""
    if not isinstance(package, dict):
        return []
    supplied = _from_package(package)
    if not supplied:
        return []
    document = _document_text(package)
    findings: list[dict] = []
    for signpost in supplied:
        claim = signpost["claim_en"].casefold()
        if claim.rstrip(".") in document:
            continue
        tokens = _tokens(claim)
        present = sum(1 for token in tokens if token in document)
        if tokens and present * 3 >= len(tokens) * 2:
            continue
        findings.append(
            {
                "id": signpost["id"],
                "claim": signpost["claim_en"],
                "detail": (
                    f'signpost {signpost["id"]} ("{signpost["claim_en"][:160]}") is not '
                    "stated anywhere in the memo — restate it where the memo "
                    "says what it watches, or drop it"
                ),
            }
        )
    return findings
