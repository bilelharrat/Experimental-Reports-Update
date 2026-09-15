"""Firm thesis — editable filters that score every company for fit.

The thesis lives at ``data/settings/thesis.yaml``. Scoring is deterministic
and explainable: every point comes from a rule the user can read in the
result (``reasons``), and a disqualifier zeroes the score with the matching
term named. No model call, no hidden weights.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from . import storage

def _thesis_file():
    return storage.DATA_DIR / "settings" / "thesis.yaml"

DEFAULT_THESIS: dict[str, Any] = {
    "name": "BSH thesis",
    "sectors": [],
    "stages": [],
    "geographies": [],
    "check_size_min_musd": None,
    "check_size_max_musd": None,
    "keywords": [],
    "must_be_true": [],
    "disqualifiers": [],
    "updated_at": None,
}

WEIGHTS = {
    "sector": 35,
    "stage": 20,
    "geography": 10,
    "keywords": 25,
    "check_size": 10,
}

STAGE_ALIASES = {
    "pre-seed": ("pre-seed", "preseed", "pre seed"),
    "seed": ("seed",),
    "series a": ("series a", "a round"),
    "series b": ("series b", "b round"),
    "series c": ("series c", "c round"),
    "growth": ("growth", "series d", "series e", "series f", "series g", "series h", "late-stage", "late stage", "pre-ipo"),
}
STAGE_PHRASES = {
    "pre-seed": ("pre-seed", "preseed", "pre seed"),
    "seed": ("seed round", "seed stage", "seed funding"),
    "series a": ("series a",),
    "series b": ("series b",),
    "series c": ("series c",),
    "growth": ("series d", "series e", "series f", "series g", "series h", "growth stage", "late-stage", "late stage", "pre-ipo"),
}
STAGE_ORDER = ("pre-seed", "seed", "series a", "series b", "series c", "growth")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_list(value: Any, *, limit: int = 40) -> list[str]:
    if isinstance(value, str):
        value = [part for part in re.split(r"[,\n]", value)]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split()).strip()
        if text and text.lower() not in {x.lower() for x in out}:
            out.append(text[:120])
    return out[:limit]


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "" or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _term_pattern(term: str) -> re.Pattern:
    """Whole-token match for a thesis term: plurals allowed, ``health*`` matches any continuation, ``C++`` still works."""
    cached = _PATTERN_CACHE.get(term)
    if cached is None:
        stem = term.strip()
        prefix = stem.endswith("*")
        stem = stem.rstrip("*").strip()
        body = r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", stem) if part)
        tail = r"[a-z0-9-]*" if prefix else r"(?:e?s)?"
        cached = _PATTERN_CACHE[term] = re.compile(r"(?<![a-z0-9-])" + body + tail + r"(?![a-z0-9])", 0 if _is_acronym(term) else re.I)
    return cached


def _is_acronym(term: str) -> bool:
    return term.isalpha() and term.isupper() and len(term) <= 4


def _matches(term: str, text_lower: str, text_raw: str) -> bool:
    term = term.strip()
    if not term:
        return False
    return _term_pattern(term).search(text_raw if _is_acronym(term) else text_lower) is not None


def _stages_in(text: str, table: dict[str, tuple[str, ...]]) -> set[str]:
    """Canonical stages named in ``text``; longer aliases win and are blanked so ``pre-seed`` never also counts as ``seed``."""
    found: set[str] = set()
    haystack = text.lower()
    aliases = sorted(((alias, stage) for stage, names in table.items() for alias in names), key=lambda a: -len(a[0]))
    for alias, stage in aliases:
        pattern = re.compile(r"(?<![a-z0-9-])" + r"[\s-]+".join(re.escape(p) for p in re.split(r"[\s-]+", alias) if p) + r"(?![a-z0-9])")
        if pattern.search(haystack):
            found.add(stage)
            haystack = pattern.sub(" ", haystack)
    return found


def get_thesis() -> dict:
    payload = storage._read_yaml_lenient(_thesis_file(), {})
    thesis = dict(DEFAULT_THESIS)
    if isinstance(payload, dict):
        thesis.update({k: v for k, v in payload.items() if k in DEFAULT_THESIS})
    for key in ("sectors", "stages", "geographies", "keywords", "must_be_true", "disqualifiers"):
        thesis[key] = _clean_list(thesis.get(key))
    thesis["check_size_min_musd"] = _float(thesis.get("check_size_min_musd"))
    thesis["check_size_max_musd"] = _float(thesis.get("check_size_max_musd"))
    return thesis


def save_thesis(patch: dict) -> dict:
    with storage._WRITE_LOCK:
        storage._quarantine_unparseable(_thesis_file())
        current = get_thesis()
        for key in ("sectors", "stages", "geographies", "keywords", "must_be_true", "disqualifiers"):
            if key in patch:
                current[key] = _clean_list(patch.get(key))
        for key in ("check_size_min_musd", "check_size_max_musd"):
            if key in patch:
                current[key] = _float(patch.get(key))
        if "name" in patch:
            current["name"] = " ".join(str(patch.get("name") or "").split())[:80] or "BSH thesis"
        current["updated_at"] = _now()
        _thesis_file().parent.mkdir(parents=True, exist_ok=True)
        storage._write_yaml(_thesis_file(), current)
    return current


def _localized(value: Any) -> str:
    """Company records carry either strings or {en, zh} dicts."""
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), "") or "")
    return str(value or "")


def _company_text(company: dict, extra_text: str = "", *, lower: bool = True) -> str:
    parts = []
    for key in ("name", "description", "descriptor", "sector", "industry", "tags", "keywords", "hq", "location", "stage", "round"):
        value = company.get(key)
        if isinstance(value, list):
            parts.append(" ".join(_localized(v) for v in value))
        else:
            parts.append(_localized(value))
    parts.append(extra_text or "")
    joined = " ".join(parts)
    return joined.lower() if lower else joined


def _stage_of(company: dict, text: str) -> str | None:
    explicit = _localized(company.get("stage") or company.get("round")).lower()
    found = _stages_in(explicit, STAGE_ALIASES) if explicit else _stages_in(text, STAGE_PHRASES)
    if not found:
        return None
    return max(found, key=STAGE_ORDER.index)


def score_company(company: dict, *, extra_text: str = "", thesis: dict | None = None) -> dict:
    """Explainable fit score 0–100 with the rules that fired."""
    thesis = thesis or get_thesis()
    text = _company_text(company, extra_text)
    raw_text = _company_text(company, extra_text, lower=False)
    reasons: list[str] = []
    score = 0
    configured = 0

    disqualified = [term for term in thesis["disqualifiers"] if _matches(term, text, raw_text)]
    if disqualified:
        return {
            "score": 0,
            "fit": "disqualified",
            "reasons": [f"Disqualifier matched: {', '.join(disqualified)}"],
            "disqualified_by": disqualified,
            "open_questions": list(thesis["must_be_true"]),
            "configured": True,
        }

    if thesis["sectors"]:
        configured += WEIGHTS["sector"]
        hits = [s for s in thesis["sectors"] if _matches(s, text, raw_text)]
        if hits:
            score += WEIGHTS["sector"]
            reasons.append(f"Sector matches thesis: {hits[0]}")
        else:
            reasons.append("Sector not in thesis")

    if thesis["stages"]:
        configured += WEIGHTS["stage"]
        stage = _stage_of(company, text)
        wanted: set[str] = set()
        for entry in thesis["stages"]:
            wanted |= _stages_in(entry, STAGE_ALIASES) or {entry.lower()}
        if stage and stage in wanted:
            score += WEIGHTS["stage"]
            reasons.append(f"Stage fits: {stage}")
        elif stage:
            reasons.append(f"Stage outside thesis: {stage}")
        else:
            reasons.append("Stage unknown")

    if thesis["geographies"]:
        configured += WEIGHTS["geography"]
        hits = [g for g in thesis["geographies"] if _matches(g, text, raw_text)]
        if hits:
            score += WEIGHTS["geography"]
            reasons.append(f"Geography fits: {hits[0]}")
        else:
            reasons.append("Geography not in thesis")

    if thesis["keywords"]:
        configured += WEIGHTS["keywords"]
        hits = [k for k in thesis["keywords"] if _matches(k, text, raw_text)]
        if hits:
            share = min(1.0, len(hits) / max(1, min(3, len(thesis["keywords"]))))
            points = round(WEIGHTS["keywords"] * share)
            score += points
            reasons.append(f"Keywords: {', '.join(hits[:4])} (+{points})")
        else:
            reasons.append("No thesis keywords found")

    lo, hi = thesis["check_size_min_musd"], thesis["check_size_max_musd"]
    if lo is not None or hi is not None:
        configured += WEIGHTS["check_size"]
        raise_musd = _float(company.get("raise_musd")) or _float(company.get("round_size_musd"))
        if raise_musd is None:
            reasons.append("Round size unknown")
        elif (lo is None or raise_musd >= lo) and (hi is None or raise_musd <= hi):
            score += WEIGHTS["check_size"]
            reasons.append(f"Round size ${raise_musd:g}M within check range")
        else:
            reasons.append(f"Round size ${raise_musd:g}M outside check range")

    if configured == 0:
        return {
            "score": None,
            "fit": "unconfigured",
            "reasons": ["Thesis is empty — set sectors, stages or keywords in Settings › Thesis"],
            "disqualified_by": [],
            "open_questions": list(thesis["must_be_true"]),
            "configured": False,
        }

    normalized = round(100 * score / configured)
    fit = "strong" if normalized >= 70 else "partial" if normalized >= 40 else "weak"
    return {
        "score": normalized,
        "fit": fit,
        "reasons": reasons,
        "disqualified_by": [],
        "open_questions": list(thesis["must_be_true"]),
        "configured": True,
    }
