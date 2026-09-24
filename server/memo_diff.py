"""Repeat memos on one company as versions, and what changed between two.

``annotate_versions`` derives, at read time and in one pass, which memo is
the latest of its (company, kind) group, the neighbouring versions, and
whether the call flipped since the previous version. Nothing is persisted —
in particular ``superseded_by`` is never written: it already means "failed
run replaced" and drives resume and the Memo Studio 409.

``diff_reports`` compares two finished memos deterministically, from what
is on disk, with no model call:

- Buffett: the decision, the buy-price text and any structured price fields;
- late-stage v1 packages: side-by-side rows — scenarios matched by their
  bear/base/bull prefix, risks by risk type, key metrics and deal terms by
  label (conservative fuzzy matching), sources by URL (else exact title);
- runs with ``logs/english_units/spine.json``: the spine's shared facts.

Labels drift between runs, so the diff shows rows side by side with how
they were matched and never claims a row was added or removed on a fuzzy
match: an unmatched row is only "not matched".
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from . import memo_prep
from .report_reader import (
    PRICE_FIELDS,
    load_package,
    load_spine_facts,
    report_decision,
)

VERSION_STATUSES = ("complete", "complete_with_warnings")
UNSTABLE_DAYS = 7


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _days_between(a: Any, b: Any) -> float | None:
    first, second = _parse_ts(a), _parse_ts(b)
    if first is None or second is None:
        return None
    return round(abs((second - first).total_seconds()) / 86400.0, 2)


def _norm_decision(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def version_eligible(report: dict) -> bool:
    return (
        memo_prep.is_memo_kind(report.get("kind"))
        and str(report.get("status") or "") in VERSION_STATUSES
        and not report.get("dismissed_at")
        and bool(report.get("company_id"))
    )


def annotate_versions(rows: list[dict]) -> list[dict]:
    """Add version fields to report summaries (or records) in place.

    Groups finished, undismissed memos by (company_id, kind) and ranks them
    by created_at. Each eligible row gets ``is_latest``, ``version_index``
    (1 = oldest), ``version_count``, ``previous_version_id``,
    ``newer_version_id`` (the next newer), ``latest_version_id``,
    ``verdict_changed_from`` (the previous version's call when it differs),
    ``verdict_flip_days`` and ``unstable_call`` (a flip within
    ``UNSTABLE_DAYS``). Rows outside any group (failed, running, dismissed,
    non-memo) get ``is_latest`` None and no neighbours.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        row.setdefault("is_latest", None)
        row.setdefault("version_index", None)
        row.setdefault("version_count", None)
        row.setdefault("previous_version_id", None)
        row.setdefault("newer_version_id", None)
        row.setdefault("latest_version_id", None)
        row.setdefault("verdict_changed_from", None)
        row.setdefault("verdict_flip_days", None)
        row.setdefault("unstable_call", None)
        if version_eligible(row):
            key = (str(row.get("company_id")), str(row.get("kind")))
            groups.setdefault(key, []).append(row)
    for group in groups.values():
        group.sort(key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")))
        latest_id = group[-1].get("id")
        for index, row in enumerate(group):
            previous = group[index - 1] if index > 0 else None
            newer = group[index + 1] if index + 1 < len(group) else None
            row["is_latest"] = newer is None
            row["version_index"] = index + 1
            row["version_count"] = len(group)
            row["previous_version_id"] = previous.get("id") if previous else None
            row["newer_version_id"] = newer.get("id") if newer else None
            row["latest_version_id"] = latest_id
            if previous is not None:
                before = report_decision(previous)
                now = report_decision(row)
                if before and now and _norm_decision(before) != _norm_decision(now):
                    days = _days_between(previous.get("created_at"), row.get("created_at"))
                    row["verdict_changed_from"] = before
                    row["verdict_flip_days"] = days
                    row["unstable_call"] = bool(days is not None and days < UNSTABLE_DAYS)
                else:
                    row["unstable_call"] = False
    return rows


# ---- cell helpers ---------------------------------------------------------------------


def _cell(value: Any) -> dict:
    if isinstance(value, dict):
        en = value.get("en")
        zh = value.get("zh")
        return {"en": en if isinstance(en, str) else None, "zh": zh if isinstance(zh, str) else None}
    if value is None:
        return {"en": None, "zh": None}
    return {"en": str(value), "zh": None}


def _text(value: Any) -> str:
    cell = _cell(value)
    return cell["en"] or cell["zh"] or ""


def _norm_text(value: Any) -> str:
    text = _text(value) if not isinstance(value, str) else value
    return re.sub(r"\s+", " ", text).strip().lower()


_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "at", "for", "on", "our", "us", "we", "vs"}


def _label_tokens(value: Any) -> frozenset[str]:
    text = _norm_text(value)
    text = re.sub(r"\([^)]*\)", " ", text)
    tokens = re.findall(r"[a-z0-9一-鿿]+", text)
    return frozenset(t for t in tokens if t not in _STOP)


def _label_key(value: Any) -> str:
    return " ".join(sorted(_label_tokens(value)))


def match_labels(current: list[Any], previous: list[Any]) -> list[tuple[int | None, int | None, str]]:
    """Pair two label lists: exact (normalized) first, then a conservative
    fuzzy pass — a pair only when each is the other's single candidate and
    one label's words contain the other's, or they share at least 75% of
    their words. Returns (current_index, previous_index, match) triples;
    unpaired rows carry None on the other side and match "none"."""
    pairs: list[tuple[int | None, int | None, str]] = []
    used_prev: set[int] = set()
    used_cur: set[int] = set()
    prev_keys: dict[str, list[int]] = {}
    for j, label in enumerate(previous):
        prev_keys.setdefault(_label_key(label), []).append(j)
    for i, label in enumerate(current):
        key = _label_key(label)
        if not key:
            continue
        for j in prev_keys.get(key, []):
            if j not in used_prev:
                pairs.append((i, j, "exact"))
                used_prev.add(j)
                used_cur.add(i)
                break

    def similar(a: frozenset[str], b: frozenset[str]) -> bool:
        if not a or not b:
            return False
        if a <= b or b <= a:
            return True
        return len(a & b) / len(a | b) >= 0.75

    cur_tokens = {i: _label_tokens(label) for i, label in enumerate(current) if i not in used_cur}
    prev_tokens = {j: _label_tokens(label) for j, label in enumerate(previous) if j not in used_prev}
    cur_candidates = {
        i: [j for j, pt in prev_tokens.items() if similar(ct, pt)] for i, ct in cur_tokens.items()
    }
    prev_candidates = {
        j: [i for i, ct in cur_tokens.items() if similar(ct, pt)] for j, pt in prev_tokens.items()
    }
    for i, candidates in cur_candidates.items():
        if len(candidates) == 1 and prev_candidates.get(candidates[0]) == [i]:
            pairs.append((i, candidates[0], "fuzzy"))
            used_cur.add(i)
            used_prev.add(candidates[0])
    for i in range(len(current)):
        if i not in used_cur:
            pairs.append((i, None, "none"))
    for j in range(len(previous)):
        if j not in used_prev:
            pairs.append((None, j, "none"))
    pairs.sort(
        key=lambda p: (
            p[0] if p[0] is not None else len(current) + (p[1] or 0),
            p[1] if p[1] is not None else -1,
        )
    )
    return pairs


# ---- package extraction ----------------------------------------------------------------


def _tables(package: dict | None, component: str) -> list[dict]:
    out: list[dict] = []
    for section in (package or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("component") == component:
                out.append(block)
    return out


def _rows(block: dict) -> list[list[Any]]:
    return [row for row in block.get("rows") or [] if isinstance(row, list) and row]


def _row_changed(a: list[Any] | None, b: list[Any] | None) -> bool | None:
    if a is None or b is None:
        return None
    return [_norm_text(x) for x in a] != [_norm_text(x) for x in b]


_SCENARIO_PREFIXES = {
    "bear": "bear", "downside": "bear", "悲观": "bear", "下行": "bear",
    "base": "base", "基准": "base", "基本": "base",
    "bull": "bull", "upside": "bull", "乐观": "bull", "上行": "bull",
}


def _scenario_key(label: Any) -> str | None:
    for locale_text in (_cell(label)["en"] or "", _cell(label)["zh"] or ""):
        text = locale_text.strip().lower()
        for prefix, key in _SCENARIO_PREFIXES.items():
            if text.startswith(prefix):
                return key
    return None


def _headers(block: dict | None) -> list[dict]:
    return [_cell(h) for h in (block or {}).get("headers") or []]


def _diff_scenarios(current: dict | None, previous: dict | None) -> dict | None:
    cur_tables = _tables(current, "scenario_analysis")
    prev_tables = _tables(previous, "scenario_analysis")
    if not cur_tables and not prev_tables:
        return None
    cur_rows = [r for t in cur_tables for r in _rows(t)]
    prev_rows = [r for t in prev_tables for r in _rows(t)]
    out_rows: list[dict] = []
    used_prev: set[int] = set()
    rest_cur: list[int] = []
    for i, row in enumerate(cur_rows):
        key = _scenario_key(row[0])
        match_j = None
        if key:
            match_j = next(
                (j for j, prow in enumerate(prev_rows) if j not in used_prev and _scenario_key(prow[0]) == key),
                None,
            )
        if match_j is None:
            rest_cur.append(i)
            continue
        used_prev.add(match_j)
        out_rows.append({
            "key": key,
            "match": "scenario",
            "current": [_cell(c) for c in row],
            "previous": [_cell(c) for c in prev_rows[match_j]],
            "changed": _row_changed(row, prev_rows[match_j]),
        })
    rest_prev = [j for j in range(len(prev_rows)) if j not in used_prev]
    pairs = match_labels([cur_rows[i][0] for i in rest_cur], [prev_rows[j][0] for j in rest_prev])
    for ci, pj, how in pairs:
        crow = cur_rows[rest_cur[ci]] if ci is not None else None
        prow = prev_rows[rest_prev[pj]] if pj is not None else None
        out_rows.append({
            "key": _label_key((crow or prow)[0]),
            "match": how,
            "current": [_cell(c) for c in crow] if crow else None,
            "previous": [_cell(c) for c in prow] if prow else None,
            "changed": _row_changed(crow, prow),
        })
    return {
        "component": "scenario_analysis",
        "headers": {
            "current": _headers(cur_tables[0] if cur_tables else None),
            "previous": _headers(prev_tables[0] if prev_tables else None),
        },
        "rows": out_rows,
    }


def _diff_labelled_table(component: str, current: dict | None, previous: dict | None) -> dict | None:
    cur_tables = _tables(current, component)
    prev_tables = _tables(previous, component)
    if not cur_tables and not prev_tables:
        return None
    cur_rows = [r for t in cur_tables for r in _rows(t)]
    prev_rows = [r for t in prev_tables for r in _rows(t)]
    rows = []
    for ci, pj, how in match_labels([r[0] for r in cur_rows], [r[0] for r in prev_rows]):
        crow = cur_rows[ci] if ci is not None else None
        prow = prev_rows[pj] if pj is not None else None
        rows.append({
            "label": {
                "current": _cell(crow[0]) if crow else None,
                "previous": _cell(prow[0]) if prow else None,
            },
            "match": how,
            "current": [_cell(c) for c in crow[1:]] if crow else None,
            "previous": [_cell(c) for c in prow[1:]] if prow else None,
            "changed": _row_changed(crow[1:] if crow else None, prow[1:] if prow else None),
        })
    return {
        "component": component,
        "headers": {
            "current": _headers(cur_tables[0] if cur_tables else None),
            "previous": _headers(prev_tables[0] if prev_tables else None),
        },
        "rows": rows,
    }


_RISK_FIELD_KEYS = {
    "risk type": "risk_type",
    "风险类型": "risk_type",
    "risk rating": "rating",
    "rating": "rating",
    "风险评级": "rating",
    "likelihood": "likelihood",
    "probability": "likelihood",
    "可能性": "likelihood",
    "impact": "impact",
    "影响": "impact",
    "why it matters": "why",
    "为什么重要": "why",
    "what we watch": "watch",
    "跟踪信号": "watch",
}


def _risks(package: dict | None) -> list[dict]:
    risks = []
    for block in _tables(package, "risk_register"):
        fields: dict[str, dict] = {}
        for row in _rows(block):
            if len(row) < 2:
                continue
            label = _cell(row[0])
            key = _RISK_FIELD_KEYS.get((label["en"] or "").strip().lower()) or _RISK_FIELD_KEYS.get(
                (label["zh"] or "").strip()
            )
            if key and key not in fields:
                fields[key] = _cell(row[1])
        if fields:
            risks.append({"title": _cell(block.get("title")), **fields})
    return risks


def _diff_risks(current: dict | None, previous: dict | None) -> dict | None:
    cur = _risks(current)
    prev = _risks(previous)
    if not cur and not prev:
        return None
    rows = []
    compared = ("rating", "likelihood", "impact")
    for ci, pj, how in match_labels(
        [r.get("risk_type") or r.get("title") for r in cur],
        [r.get("risk_type") or r.get("title") for r in prev],
    ):
        crisk = cur[ci] if ci is not None else None
        prisk = prev[pj] if pj is not None else None
        changed = None
        if crisk is not None and prisk is not None:
            changed = any(
                _norm_text(crisk.get(k)) != _norm_text(prisk.get(k)) for k in compared
            )
        rows.append({
            "risk_type": {
                "current": (crisk or {}).get("risk_type") if crisk else None,
                "previous": (prisk or {}).get("risk_type") if prisk else None,
            },
            "match": how,
            "current": {k: crisk.get(k) for k in ("rating", "likelihood", "impact", "watch")} if crisk else None,
            "previous": {k: prisk.get(k) for k in ("rating", "likelihood", "impact", "watch")} if prisk else None,
            "rating_changed": changed,
        })
    return {"component": "risk_register", "rows": rows}


def _source_key(source: dict) -> tuple[str, str]:
    url = str(source.get("url") or "").strip().lower().rstrip("/")
    url = re.sub(r"^https?://(www\.)?", "", url)
    if url:
        return "url", url
    return "title", _norm_text(source.get("title"))


def _diff_sources(current: dict | None, previous: dict | None) -> dict | None:
    cur = [s for s in (current or {}).get("sources") or [] if isinstance(s, dict)]
    prev = [s for s in (previous or {}).get("sources") or [] if isinstance(s, dict)]
    if not cur and not prev:
        return None
    prev_index: dict[tuple[str, str], int] = {}
    for j, source in enumerate(prev):
        key = _source_key(source)
        if key[1]:
            prev_index.setdefault(key, j)
    rows = []
    used: set[int] = set()

    def view(source: dict) -> dict:
        return {
            "id": source.get("id"),
            "title": _cell(source.get("title")),
            "url": source.get("url"),
            "as_of": source.get("as_of"),
            "class": _cell(source.get("class")),
        }

    for source in cur:
        key = _source_key(source)
        j = prev_index.get(key) if key[1] else None
        if j is not None and j not in used:
            used.add(j)
            rows.append({"match": key[0], "current": view(source), "previous": view(prev[j])})
        else:
            rows.append({"match": "none", "current": view(source), "previous": None})
    for j, source in enumerate(prev):
        if j not in used:
            rows.append({"match": "none", "current": None, "previous": view(source)})
    return {
        "component": "sources",
        "matched": sum(1 for r in rows if r["match"] != "none"),
        "current_total": len(cur),
        "previous_total": len(prev),
        "rows": rows,
    }


_SPINE_FIELDS = (
    "recommendation_sentence",
    "verdict",
    "fair_value_range",
    "entry",
    "key_metrics",
    "scenarios",
    "risks",
)


def _diff_spine(current: dict | None, previous: dict | None) -> dict | None:
    if not current or not previous:
        return None
    fields = []
    for key in _SPINE_FIELDS:
        a = current.get(key)
        b = previous.get(key)
        if a is None and b is None:
            continue
        fields.append({"field": key, "current": a, "previous": b, "changed": a != b})
    return {"fields": fields} if fields else None


def _buffett_fields(report: dict, package: dict | None) -> dict:
    from .report_reader import price_fields

    pkg = package or {}
    out: dict[str, Any] = {
        "decision": report.get("decision") or pkg.get("decision"),
        "buy_price": report.get("buy_price") or pkg.get("buy_price"),
        "pass_kind": report.get("pass_kind") or pkg.get("pass_kind"),
    }
    structured = price_fields(report, package)
    for key in PRICE_FIELDS:
        out[key] = structured.get(key)
    return out


def _side(report: dict) -> dict:
    reader = report.get("reader") if isinstance(report.get("reader"), dict) else {}
    return {
        "id": report.get("id"),
        "created_at": report.get("created_at"),
        "report_type": report.get("report_type"),
        "status": report.get("status"),
        "decision": report_decision(report),
        "memo_as_of": reader.get("memo_as_of"),
        "headline": reader.get("headline"),
    }


def diff_reports(current: dict, previous: dict) -> dict:
    """A deterministic comparison of two finished memos of the same kind."""
    cur_pkg = load_package(current)
    prev_pkg = load_package(previous)
    cur_decision = report_decision(current)
    prev_decision = report_decision(previous)
    days = _days_between(previous.get("created_at"), current.get("created_at"))
    changed = bool(
        cur_decision and prev_decision and _norm_decision(cur_decision) != _norm_decision(prev_decision)
    )
    result: dict[str, Any] = {
        "report_id": current.get("id"),
        "against_id": previous.get("id"),
        "kind": current.get("kind"),
        "current": _side(current),
        "previous": _side(previous),
        "days_apart": days,
        "verdict": {
            "current": cur_decision,
            "previous": prev_decision,
            "changed": changed,
            "unstable": bool(changed and days is not None and days < UNSTABLE_DAYS),
        },
        "tables": [],
        "sources": None,
        "spine": None,
        "buffett": None,
        "notes": [],
    }
    if memo_prep.is_buffett_kind(current.get("kind")):
        cur_fields = _buffett_fields(current, cur_pkg)
        prev_fields = _buffett_fields(previous, prev_pkg)
        result["buffett"] = {
            "fields": [
                {
                    "field": key,
                    "current": cur_fields.get(key),
                    "previous": prev_fields.get(key),
                    "changed": _norm_text(str(cur_fields.get(key) or ""))
                    != _norm_text(str(prev_fields.get(key) or "")),
                }
                for key in ("decision", "buy_price", "pass_kind", *PRICE_FIELDS)
                if cur_fields.get(key) is not None or prev_fields.get(key) is not None
            ]
        }
    else:
        if cur_pkg is None or prev_pkg is None:
            result["notes"].append(
                "One of the two runs has no memo package on disk; only the call is compared."
            )
        tables = [
            _diff_scenarios(cur_pkg, prev_pkg),
            _diff_risks(cur_pkg, prev_pkg),
            _diff_labelled_table("key_metrics_snapshot", cur_pkg, prev_pkg),
            _diff_labelled_table("deal_terms", cur_pkg, prev_pkg),
        ]
        result["tables"] = [table for table in tables if table]
        result["sources"] = _diff_sources(cur_pkg, prev_pkg)
        result["spine"] = _diff_spine(load_spine_facts(current), load_spine_facts(previous))
    if any(
        row.get("match") == "fuzzy"
        for table in result["tables"]
        for row in table.get("rows") or []
    ):
        result["notes"].append(
            "Some rows were paired by similar labels; they are shown side by side, "
            "not as additions or removals."
        )
    return result
