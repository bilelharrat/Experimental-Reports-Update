"""No-invented-numbers lint: every figure in the memo must appear somewhere in the company's sources.

Sources = uploaded file summaries and traces, founder updates, KPI rows, transcripts, reference
calls, the company record and evidence excerpts. A number the memo states that none of them
contain is reported as unsupported with the section it sits in. Deterministic; no model.
"""
from __future__ import annotations

import re
from typing import Any

from . import comps, evidence_matrix, ic_room, portfolio, research_store, storage, transcripts

NUMBER_RE = re.compile(
    r"(?P<money>\$\s?\d[\d,]*(?:\.\d+)?\s?(?:k|m|mm|b|bn|t|thousand|million|billion|trillion)?)"
    r"|(?P<pct>\d[\d,]*(?:\.\d+)?\s?%)"
    r"|(?P<mult>\d[\d,]*(?:\.\d+)?\s?x\b)"
    r"|(?P<plain>\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?(?:k|m|mm|bn|million|billion)\b)",
    re.I,
)
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_UNIT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}


def _value_of(text: str) -> float | None:
    m = re.match(r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s?([a-z]+)?", text.strip().lower())
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").strip()
    return value * _UNIT.get(unit, 1.0)


def _digits_forms(text: str) -> set[str]:
    """Canonical spellings a source could use for the same figure."""
    forms = {re.sub(r"[\s,$]", "", text.lower())}
    value = _value_of(text)
    if value is not None and "%" not in text and not text.lower().rstrip().endswith("x"):
        for unit, mult in (("k", 1e3), ("m", 1e6), ("b", 1e9)):
            scaled = value / mult
            if 0.01 <= scaled < 1000 and abs(scaled - round(scaled, 2)) < 1e-9:
                s = f"{scaled:.2f}".rstrip("0").rstrip(".")
                forms.add(f"{s}{unit}")
                forms.add(f"{s}{ {'k': 'thousand', 'm': 'million', 'b': 'billion'}[unit]}")
        if value >= 1000 and abs(value - round(value)) < 1e-9:
            forms.add(f"{int(round(value))}")
    return forms


_UNITS = r"(?:k|mm|m|bn|b|t|thousand|million|billion|trillion)"


def _normalize_corpus(text: str) -> str:
    t = text.lower().replace("$", "")
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
    t = re.sub(r"(?<=\d)\s+(?=(?:%|x\b|" + _UNITS + r"\b))", "", t)
    return t


def _supported(form: str, corpus: str) -> bool:
    """``form`` appears in ``corpus`` as a whole figure: ``5m`` is not inside ``15m`` or ``5months``."""
    if form[-1].isdigit():
        tail = r"(?:\.0+)?(?!\d|\.\d)"
    elif form[-1] == "%":
        tail = ""
    elif form.endswith("m"):
        tail = r"m?(?![a-z\d])"
    elif form.endswith("b"):
        tail = r"n?(?![a-z\d])"
    else:
        tail = r"(?![a-z\d])"
    return re.search(r"(?<![\d.])" + re.escape(form) + tail, corpus) is not None


def extract_numbers(text: str) -> list[str]:
    out = []
    for m in NUMBER_RE.finditer(text):
        raw = m.group(0).strip()
        bare = re.sub(r"[^\d]", "", raw)
        if _YEAR_RE.match(bare) and "%" not in raw and "$" not in raw:
            continue
        if raw.lower().rstrip().endswith("x") and _value_of(raw) is not None and _value_of(raw) > 1000:
            continue
        out.append(raw)
    return out


def lint_blocks(blocks: list[tuple[str, str]], corpus_texts: list[str]) -> dict:
    corpus = _normalize_corpus("\n".join(corpus_texts))
    findings = []
    supported = unsupported = 0
    for section, text in blocks:
        for raw in extract_numbers(text):
            forms = _digits_forms(raw)
            ok = any(form and _supported(form, corpus) for form in forms)
            supported += ok
            unsupported += (not ok)
            if not ok:
                idx = text.find(raw)
                lo, hi = max(0, idx - 80), min(len(text), idx + len(raw) + 80)
                findings.append({"section": section, "number": raw, "excerpt": " ".join(text[lo:hi].split()), "looked_for": sorted(forms)[:4]})
    total = supported + unsupported
    return {
        "checked": total,
        "supported": supported,
        "unsupported": unsupported,
        "coverage_pct": round(supported / total * 100) if total else None,
        "findings": findings,
    }


def _corpus(company_id: str) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    sources: list[str] = []
    company = storage.get_company(company_id) or {}
    desc = company.get("description")
    texts.append(desc.get("en", "") if isinstance(desc, dict) else str(desc or ""))
    texts.append(str(company.get("round") or ""))
    sources.append("company record")
    for record in research_store.list_files(company_id):
        summary = record.get("quick_summary")
        if isinstance(summary, dict):
            texts.append(_flatten(summary))
            sources.append(f"file summary: {record.get('filename')}")
    for row in (evidence_matrix.build_company_evidence_matrix(company_id).get("claims") or []):
        if isinstance(row, dict):
            texts.append(_flatten(row))
    sources.append("evidence matrix")
    if portfolio.has_record(company_id):
        record = portfolio.get_portfolio(company_id)
        for u in record.get("updates") or []:
            texts.append(u.get("text") or "")
        for k in record.get("kpis") or []:
            texts.append(" ".join(f"{v}" for key, v in k.items() if key.endswith(("_usd", "_month", "_months")) or key in {"headcount", "customers"}))
        sources.append(f"{len(record.get('updates') or [])} founder updates, {len(record.get('kpis') or [])} KPI rows")
    for t in transcripts.all_transcripts():
        if t.get("company_id") == company_id:
            texts.append(t.get("text") or "")
            sources.append(f"transcript: {t.get('title')}")
    for ref in ic_room.list_reference_calls(company_id).get("items") or []:
        texts.append(" ".join([ref.get("notes") or ""] + list(ref.get("quotes") or []) + list(ref.get("strengths") or []) + list(ref.get("concerns") or [])))
    return texts, sources


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    return str(value or "")


def lint(company_id: str) -> dict:
    path, package = comps._latest_memo_package(company_id)
    if not package:
        return {"company_id": company_id, "memo_package": None, "checked": 0, "supported": 0, "unsupported": 0, "coverage_pct": None, "findings": [], "sources": [], "note": "No memo package on record"}
    blocks = comps._memo_text_blocks(package)
    texts, sources = _corpus(company_id)
    result = lint_blocks(blocks, texts)
    result.update({"company_id": company_id, "memo_package": str(path), "sources": sources, "note": "A number counts as supported when any source on file contains the same figure (any spelling)."})
    return result
