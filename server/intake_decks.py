"""Pitch-deck intake: store the deck, read its text, pull the obvious facts with page
references, score it against the thesis, and file the company as Sourcing.

Extraction here is deterministic (regex over slide text) and every field carries
the page and excerpt it came from. The Claude-backed structured summary is a
separate, explicit step (`POST /companies/{id}/files/{file_id}/summary`).
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from . import deck_summary, files_store, storage, thesis_store

MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(k|m|mm|b|bn|million|billion|thousand)?\b"
NUM = r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{1,6})"
PRICE_GUARD = r"(?!\s*(?:/|per\s+)(?:seat|user|unit|license|licence)\b)"
DECK_KINDS = {"pdf", "ppt", "pptx"}
MONEY_FIELDS = {"raise", "post_money", "arr", "revenue", "burn"}
COUNT_FIELDS = {"runway", "headcount", "customers"}


def _gap(limit: int, forbid: str) -> str:
    """Up to ``limit`` characters between a keyword and its amount: no sentence end, no other KPI keyword."""
    return r"(?:(?!\b(?:" + forbid + r")\b)[^$\n.;!?]){0," + str(limit) + "}"


FIELD_PATTERNS: list[tuple[str, str]] = [
    ("round", r"\b(pre[- ]?seed|seed|series\s+[a-h]|bridge|growth round)\b"),
    ("raise", r"\b(?:raising|raise|seeking|round of|round size)\b[^$\n]{0,40}" + MONEY + PRICE_GUARD),
    ("post_money", r"(?:post[- ]money|valuation)[^$\n]{0,40}" + MONEY + r"|" + MONEY + r"[^.\n$]{0,30}post[- ]money"),
    ("arr", r"\b(?:arr|annual recurring revenue|(?<!burn )(?<!burn-)run[- ]rate)\b" + _gap(30, "burn|cash|runway") + MONEY + PRICE_GUARD
            + r"|" + MONEY + r"\s+(?:of\s+|in\s+)?(?:arr|annual recurring revenue)\b"),
    ("revenue", r"\b(?:revenue|sales)\b(?!\s+model)" + _gap(30, "burn|cash|runway") + MONEY + PRICE_GUARD),
    ("burn", r"\b(?:net )?burn\b" + _gap(30, "arr|revenue|cash balance|in the bank|runway") + MONEY + r"(?:[^$\n.]{0,12}?\bto\s+" + MONEY + r")?"),
    ("runway", r"(?<!by )(?<![\d,.])\b(\d{1,2})\s*(?:\+\s*)?months?\s+(?:of\s+)?runway|runway[^\n.]{0,30}?(?<!by )(?<![\d,.])(\d{1,2})\s*months?(?!\s+to\s+\d)"),
    ("headcount", r"(?<!hired )(?<!added )(?<!hiring )(?<!onboarded )" + NUM + r"\s+(?:employees|fte|ftes|team members)\b|\bteam of\s+" + NUM),
    ("customers", NUM + r"\+?\s+(?:customers|logos|paying customers)\b"),
]

MULTIPLIERS = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


def _money_usd(amount: str, unit: str | None) -> float | None:
    try:
        value = float(amount.replace(",", ""))
    except ValueError:
        return None
    return value * MULTIPLIERS.get((unit or "").lower(), 1.0)


def _money_pairs(match: re.Match) -> list[tuple[str, str | None]]:
    """(amount, unit) pairs in match order; money patterns only ever capture MONEY groups."""
    groups = match.groups()
    return [(groups[i], groups[i + 1]) for i in range(0, len(groups) - 1, 2) if groups[i]]


def _excerpt(text: str, start: int, end: int, width: int = 90) -> str:
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    return " ".join(text[lo:hi].split())


def extract_fields(slides: list) -> list[dict]:
    """First match per field across slides, with page and excerpt."""
    found: dict[str, dict] = {}
    for slide in slides:
        text = f"{getattr(slide, 'text', '') or ''}\n{getattr(slide, 'notes', '') or ''}"
        flat = " ".join(text.split())
        page = getattr(slide, "slide_no", None)
        for name, pattern in FIELD_PATTERNS:
            if name in found:
                continue
            match = re.search(pattern, flat, flags=re.I)
            if not match:
                continue
            raw = match.group(0)
            value: Any = " ".join(raw.split())
            usd = None
            groups = [g for g in match.groups() if g]
            if name in MONEY_FIELDS:
                pairs = _money_pairs(match)
                if pairs:
                    amount, unit = pairs[-1] if name == "burn" else pairs[0]
                    usd = _money_usd(amount, unit)
            elif name in COUNT_FIELDS and groups:
                value = groups[0].replace(",", "")
            elif name == "round":
                value = groups[0].title()
            found[name] = {
                "name": name,
                "value": value,
                "usd": usd,
                "page": page,
                "excerpt": _excerpt(flat, match.start(), match.end()),
            }
    order = [name for name, _ in FIELD_PATTERNS]
    return [found[n] for n in order if n in found]


def _guess_name(slides: list, fallback: str) -> str:
    """The deck's first slide title is usually the company name."""
    for slide in slides[:2]:
        text = (getattr(slide, "text", "") or "").strip()
        for line in text.splitlines():
            line = " ".join(line.split())
            if 2 <= len(line) <= 48 and not re.search(r"\d{4}|confidential|deck|pitch", line, flags=re.I):
                return line
    return fallback


def ingest(
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    company_id: str | None,
    company_name: str | None,
    created_by: str | None = None,
) -> dict:
    """Store the deck under the company (creating it if needed) and return the extraction."""
    if not filename:
        raise ValueError("Missing filename")
    if len(data) == 0:
        raise ValueError("Empty file")
    if len(data) > files_store.MAX_FILE_BYTES:
        raise ValueError(f"File exceeds {files_store.MAX_FILE_BYTES // (1024 * 1024)}MB limit")
    kind = files_store._kind_from(content_type, filename)
    if kind not in DECK_KINDS:
        raise ValueError("Unsupported deck type — only PDF, PPT and PPTX are accepted")
    slides: list = []
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".bin", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            slides = deck_summary.extract_slides(Path(tmp.name), kind)
        except Exception:  # noqa: BLE001 - unreadable decks still get filed
            slides = []

    fallback = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "New company"
    name = (company_name or "").strip() or _guess_name(slides, fallback)

    company = storage.get_company(company_id) if company_id else None
    if company is None:
        company = storage.upsert_company_from_match({"name": name, "status": "private", "company_type": "private"})
    cid = company["id"]

    record = files_store.upload_file(
        cid,
        filename=filename,
        content_type=content_type,
        data=data,
        label="Pitch deck (intake)",
        language="en",
    )

    fields = extract_fields(slides)
    deck_text = " ".join((getattr(s, "text", "") or "") for s in slides[:12])
    round_field = next((f for f in fields if f["name"] == "round"), None)
    raise_field = next((f for f in fields if f["name"] == "raise"), None)
    scoring_company = dict(company)
    if round_field:
        scoring_company["stage"] = round_field["value"]
    if raise_field and raise_field.get("usd"):
        scoring_company["raise_musd"] = raise_field["usd"] / 1e6
    thesis = thesis_store.score_company(scoring_company, extra_text=deck_text[:6000])

    return {
        "company": storage.get_company(cid) or company,
        "file": record,
        "slide_count": len(slides),
        "extraction": {"fields": fields, "method": "regex-over-slide-text"},
        "thesis": thesis,
        "created_by": created_by,
    }
