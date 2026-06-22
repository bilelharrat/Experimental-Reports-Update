"""Refresh statistics and longitudinal history for trader snapshots."""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

VOLATILE_SNAPSHOT_KEYS = {
    "refreshed_at",
    "generation_duration_ms",
    "generation_cost_usd",
    "available_languages",
    "schema_version",
    "refresh_stats",
    "section_status",
}

SECTION_KEYS = (
    "market_session",
    "price_card",
    "momentum_card",
    "sentiment_card",
    "heat_card",
    "catalysts",
    "trader_news",
    "research_overview",
    "tech_movers",
)

MAX_COMPARE_CHARS = 300_000

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stats_dir() -> Path:
    path = storage.DATA_DIR / "_trader_stats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(company_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", (company_id or "").strip())
    return cleaned.strip("-") or "unknown"


def history_path(company_id: str) -> Path:
    return _stats_dir() / f"{_safe_id(company_id)}.jsonl"


def _default_progress_path(company_id: str) -> Path:
    return storage.DATA_DIR / "_trader" / f"{_safe_id(company_id)}__snapshot.progress.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    out.append(item)
    except OSError:
        return []
    return out


def _json_default(value: Any) -> str:
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()[:16]


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> int:
    number = _as_float(value)
    return int(number) if number is not None else 0


def _rounded(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _usage_summary(usage: Any) -> dict:
    totals = {field: 0 for field in TOKEN_FIELDS}
    server_tool_use: dict[str, int] = {}
    if isinstance(usage, dict):
        for field in TOKEN_FIELDS:
            totals[field] += _as_int(usage.get(field))
        server_tools = usage.get("server_tool_use")
        if isinstance(server_tools, dict):
            for key, value in server_tools.items():
                count = _as_int(value)
                if count:
                    server_tool_use[key] = server_tool_use.get(key, 0) + count

        # Most Claude result events already expose aggregate usage. Only
        # fall back to iteration sums when the aggregate fields are absent.
        if not any(totals.values()):
            for iteration in usage.get("iterations") or []:
                if not isinstance(iteration, dict):
                    continue
                for field in TOKEN_FIELDS:
                    totals[field] += _as_int(iteration.get(field))

    totals["total_tokens"] = sum(totals.values())
    totals["server_tool_use"] = server_tool_use
    return totals


def _blank_usage() -> dict:
    usage = {field: 0 for field in TOKEN_FIELDS}
    usage.update({
        "total_tokens": 0,
        "cost_usd": 0.0,
        "model_duration_ms": 0,
        "result_count": 0,
        "server_tool_use": {},
        "by_thread": [],
    })
    return usage


def parse_progress_stats(progress_path: Path | str | None) -> dict:
    """Aggregate token/cost/thread stats from a trader progress JSONL."""
    path = Path(progress_path) if progress_path else None
    events = _read_jsonl(path) if path else []
    token_usage = _blank_usage()
    by_thread: dict[str, dict] = {}
    started_sections: set[str] = set()
    finished_sections: set[str] = set()
    failed_sections: list[dict] = []
    errors: list[str] = []
    done_event: dict | None = None
    terminal_event: dict | None = None
    started_at: str | None = None
    completed_at: str | None = None
    tool_calls = 0

    for entry in events:
        ts = entry.get("ts")
        if ts and started_at is None:
            started_at = ts
        typ = entry.get("type")
        thread = str(entry.get("thread") or "run")
        if typ == "thread_started":
            started_sections.add(thread)
        elif typ == "thread_finished":
            finished_sections.add(thread)
        elif typ == "thread_failed":
            error = str(entry.get("error") or "failed")
            row = {"thread": thread, "error": error}
            if entry.get("section_id"):
                row["section"] = entry.get("section_id")
            if entry.get("pass_id"):
                row["pass_id"] = entry.get("pass_id")
            failed_sections.append(row)
        elif typ == "error":
            error = str(entry.get("error") or "error")
            errors.append(error)
            terminal_event = entry
            completed_at = ts or completed_at
        elif typ == "done":
            done_event = entry
            terminal_event = entry
            completed_at = ts or completed_at
        elif typ == "claude_action":
            action = entry.get("action")
            if action == "tool_use":
                tool_calls += 1
            if action != "result":
                continue
            usage = _usage_summary(entry.get("usage"))
            cost = _as_float(entry.get("cost_usd")) or 0.0
            duration = _as_int(entry.get("duration_ms"))
            bucket = by_thread.setdefault(
                thread,
                {
                    "thread": thread,
                    **{field: 0 for field in TOKEN_FIELDS},
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "duration_ms": 0,
                    "result_count": 0,
                    "server_tool_use": {},
                },
            )
            for field in TOKEN_FIELDS:
                bucket[field] += usage[field]
                token_usage[field] += usage[field]
            bucket["total_tokens"] += usage["total_tokens"]
            token_usage["total_tokens"] += usage["total_tokens"]
            bucket["cost_usd"] += cost
            token_usage["cost_usd"] += cost
            bucket["duration_ms"] += duration
            token_usage["model_duration_ms"] += duration
            bucket["result_count"] += 1
            token_usage["result_count"] += 1
            for key, count in (usage.get("server_tool_use") or {}).items():
                bucket["server_tool_use"][key] = (
                    bucket["server_tool_use"].get(key, 0) + count
                )
                token_usage["server_tool_use"][key] = (
                    token_usage["server_tool_use"].get(key, 0) + count
                )

    thread_rows = sorted(
        by_thread.values(),
        key=lambda item: (-item.get("total_tokens", 0), item.get("thread", "")),
    )
    for row in thread_rows:
        row["cost_usd"] = round(float(row.get("cost_usd") or 0.0), 6)
    token_usage["cost_usd"] = round(float(token_usage["cost_usd"] or 0.0), 6)
    token_usage["by_thread"] = thread_rows

    return {
        "progress_path": str(path) if path else None,
        "event_count": len(events),
        "started_at": started_at,
        "completed_at": completed_at,
        "done_event": done_event,
        "terminal_event": terminal_event,
        "errors": errors,
        "started_sections": sorted(started_sections),
        "finished_sections": sorted(finished_sections),
        "failed_sections": failed_sections,
        "tool_calls": tool_calls,
        "token_usage": token_usage,
        "cost_usd": token_usage["cost_usd"],
        "wall_duration_ms": _as_int(done_event.get("duration_ms")) if done_event else 0,
    }


def _strip_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_snapshot(item)
            for key, item in value.items()
            if key not in VOLATILE_SNAPSHOT_KEYS
        }
    if isinstance(value, list):
        return [_strip_snapshot(item) for item in value]
    return value


def _canonical_for_compare(value: Any) -> str:
    text = _json_dumps(value)
    if len(text) <= MAX_COMPARE_CHARS:
        return text
    half = MAX_COMPARE_CHARS // 2
    return text[:half] + text[-half:]


def _snapshot_similarity(before: Any, after: Any) -> float | None:
    before_text = _canonical_for_compare(before)
    after_text = _canonical_for_compare(after)
    if not before_text and not after_text:
        return 1.0
    if not before_text or not after_text:
        return None
    return difflib.SequenceMatcher(None, before_text, after_text).ratio()


def _get(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _pick_text(obj: Any, *path: str, base: str) -> Any:
    section = _get(obj, *path) if path else obj
    if not isinstance(section, dict):
        return None
    for key in (f"{base}_en", base, f"{base}_zh"):
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return f"{int(value):,}"
        return f"{float(value):,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    if isinstance(value, dict):
        return "object"
    text = str(value).strip()
    return text[:80] + "..." if len(text) > 80 else text


def _add_value_change(
    highlights: list[str],
    field_changes: list[dict],
    label: str,
    before: Any,
    after: Any,
) -> None:
    if before == after:
        return
    if before is None and after is None:
        return
    field_changes.append({
        "field": label,
        "before": before,
        "after": after,
    })
    if len(highlights) < 14:
        highlights.append(
            f"{label}: {_fmt_scalar(before)} -> {_fmt_scalar(after)}"
        )


def _item_label(item: Any, *bases: str) -> str | None:
    if not isinstance(item, dict):
        return None
    date = item.get("date") or item.get("published_at") or item.get("updated_at")
    text = None
    for base in bases:
        text = _pick_text(item, base=base)
        if text:
            break
    if not text:
        text = item.get("headline") or item.get("title") or item.get("name")
    if not text:
        return None
    label = str(text).strip()
    return f"{date}: {label}" if date else label


def _list_label_set(items: Any, *bases: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    labels = set()
    for item in items:
        label = _item_label(item, *bases)
        if label:
            labels.add(label)
    return labels


def _add_list_delta(
    highlights: list[str],
    label: str,
    before_items: Any,
    after_items: Any,
    *bases: str,
) -> None:
    before = _list_label_set(before_items, *bases)
    after = _list_label_set(after_items, *bases)
    added = sorted(after - before)
    removed = sorted(before - after)
    if added and len(highlights) < 14:
        highlights.append(f"{label} added: {', '.join(added[:3])}")
    if removed and len(highlights) < 14:
        highlights.append(f"{label} removed: {', '.join(removed[:3])}")


def _high_signal_changes(before: dict, after: dict) -> tuple[list[str], list[dict]]:
    highlights: list[str] = []
    field_changes: list[dict] = []
    comparisons = (
        ("Last price", _get(before, "price_card", "last_price"), _get(after, "price_card", "last_price")),
        ("1d move", _get(before, "price_card", "change_pct_1d"), _get(after, "price_card", "change_pct_1d")),
        ("30d move", _get(before, "price_card", "change_pct_30d"), _get(after, "price_card", "change_pct_30d")),
        ("Vs sector 30d", _get(before, "price_card", "vs_sector_pct_30d"), _get(after, "price_card", "vs_sector_pct_30d")),
        ("Vs S&P 500 30d", _get(before, "price_card", "vs_sp500_pct_30d"), _get(after, "price_card", "vs_sp500_pct_30d")),
        ("Momentum trend", _pick_text(before, "momentum_card", base="trend"), _pick_text(after, "momentum_card", base="trend")),
        ("Above 50dma", _get(before, "momentum_card", "above_50dma"), _get(after, "momentum_card", "above_50dma")),
        ("Above 200dma", _get(before, "momentum_card", "above_200dma"), _get(after, "momentum_card", "above_200dma")),
        ("MA crossover", _get(before, "momentum_card", "ma_crossover_recent"), _get(after, "momentum_card", "ma_crossover_recent")),
        ("Support", _get(before, "momentum_card", "support_level"), _get(after, "momentum_card", "support_level")),
        ("Resistance", _get(before, "momentum_card", "resistance_level"), _get(after, "momentum_card", "resistance_level")),
        ("Analyst consensus", _pick_text(before, "sentiment_card", base="analyst_consensus"), _pick_text(after, "sentiment_card", base="analyst_consensus")),
        ("Analyst coverage", _get(before, "sentiment_card", "coverage_count"), _get(after, "sentiment_card", "coverage_count")),
        ("Mean target", _get(before, "sentiment_card", "price_target_mean"), _get(after, "sentiment_card", "price_target_mean")),
        ("Short interest % float", _get(before, "heat_card", "short_pressure", "si_pct_float"), _get(after, "heat_card", "short_pressure", "si_pct_float")),
        ("Days to cover", _get(before, "heat_card", "short_pressure", "days_to_cover"), _get(after, "heat_card", "short_pressure", "days_to_cover")),
        ("Short trend", _get(before, "heat_card", "short_pressure", "trend"), _get(after, "heat_card", "short_pressure", "trend")),
        ("EV/Revenue", _get(before, "heat_card", "valuation", "ev_revenue_current"), _get(after, "heat_card", "valuation", "ev_revenue_current")),
        ("PEG", _get(before, "heat_card", "valuation", "peg"), _get(after, "heat_card", "valuation", "peg")),
        ("Fragility score", _get(before, "heat_card", "fragility", "score"), _get(after, "heat_card", "fragility", "score")),
        ("Fragility rating", _get(before, "heat_card", "fragility", "rating"), _get(after, "heat_card", "fragility", "rating")),
        ("Next catalyst", _pick_text(before, "heat_card", "next_catalyst", base="label"), _pick_text(after, "heat_card", "next_catalyst", base="label")),
        ("Next catalyst date", _get(before, "heat_card", "next_catalyst", "date"), _get(after, "heat_card", "next_catalyst", "date")),
        ("Research quality score", _get(before, "research_overview", "quality_score"), _get(after, "research_overview", "quality_score")),
    )
    for label, old, new in comparisons:
        _add_value_change(highlights, field_changes, label, old, new)

    _add_list_delta(
        highlights,
        "Catalysts",
        before.get("catalysts"),
        after.get("catalysts"),
        "title",
    )
    _add_list_delta(
        highlights,
        "Trader news",
        before.get("trader_news"),
        after.get("trader_news"),
        "headline",
    )
    if not highlights:
        highlights.append("No high-signal fields changed.")
    return highlights, field_changes


def build_change_summary(
    previous_snapshot: dict | None,
    new_snapshot: dict | None,
) -> dict:
    previous = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current = new_snapshot if isinstance(new_snapshot, dict) else {}
    before = _strip_snapshot(copy.deepcopy(previous))
    after = _strip_snapshot(copy.deepcopy(current))

    has_previous = bool(before)
    if not has_previous:
        return {
            "has_previous": False,
            "baseline": True,
            "previous_refreshed_at": previous.get("refreshed_at"),
            "new_refreshed_at": current.get("refreshed_at"),
            "similarity_pct": None,
            "change_pct": None,
            "changed_sections": [],
            "section_changes": [],
            "field_changes": [],
            "highlights": [
                "Baseline captured; no previous snapshot was available for comparison."
            ],
        }

    ratio = _snapshot_similarity(before, after)
    similarity_pct = round(ratio * 100, 2) if ratio is not None else None
    change_pct = round((1 - ratio) * 100, 2) if ratio is not None else None
    section_changes: list[dict] = []
    for section in SECTION_KEYS:
        old = before.get(section)
        new = after.get(section)
        if old == new:
            continue
        if old is None and new is not None:
            status = "added"
        elif old is not None and new is None:
            status = "removed"
        else:
            status = "changed"
        section_changes.append({
            "section": section,
            "status": status,
            "before_fingerprint": _fingerprint(old),
            "after_fingerprint": _fingerprint(new),
            "before_size": len(_json_dumps(old)),
            "after_size": len(_json_dumps(new)),
        })

    highlights, field_changes = _high_signal_changes(before, after)
    return {
        "has_previous": True,
        "baseline": False,
        "previous_refreshed_at": previous.get("refreshed_at"),
        "new_refreshed_at": current.get("refreshed_at"),
        "similarity_pct": similarity_pct,
        "change_pct": change_pct,
        "changed_sections": [item["section"] for item in section_changes],
        "section_changes": section_changes,
        "field_changes": field_changes,
        "highlights": highlights,
    }


def build_snapshot_summary(snapshot: dict | None) -> dict:
    snap = snapshot if isinstance(snapshot, dict) else {}
    heat = snap.get("heat_card") if isinstance(snap.get("heat_card"), dict) else {}
    next_catalyst = (
        heat.get("next_catalyst") if isinstance(heat.get("next_catalyst"), dict) else {}
    )
    return {
        "last_price": _get(snap, "price_card", "last_price"),
        "currency": _get(snap, "price_card", "currency"),
        "as_of": _get(snap, "price_card", "as_of"),
        "change_pct_1d": _get(snap, "price_card", "change_pct_1d"),
        "change_pct_30d": _get(snap, "price_card", "change_pct_30d"),
        "momentum_trend": _pick_text(snap, "momentum_card", base="trend"),
        "analyst_consensus": _pick_text(snap, "sentiment_card", base="analyst_consensus"),
        "coverage_count": _get(snap, "sentiment_card", "coverage_count"),
        "fragility_score": _get(snap, "heat_card", "fragility", "score"),
        "fragility_rating": _get(snap, "heat_card", "fragility", "rating"),
        "next_catalyst": _pick_text(next_catalyst, base="label"),
        "next_catalyst_date": next_catalyst.get("date") if next_catalyst else None,
        "catalyst_count": len(snap.get("catalysts") or []),
        "news_count": len(snap.get("trader_news") or []),
    }


def _status_failed_sections(snapshot: dict | None) -> list[dict]:
    snap = snapshot if isinstance(snapshot, dict) else {}
    status_map = snap.get("section_status")
    if not isinstance(status_map, dict):
        return []
    rows: list[dict] = []
    for section_id, status in status_map.items():
        if not isinstance(status, dict):
            continue
        state = status.get("status")
        error = status.get("last_error")
        if state not in {"failed", "stale"} or not error:
            continue
        rows.append({
            "section": section_id,
            "thread": status.get("label") or section_id,
            "status": state,
            "error": error,
            "last_attempted_at": status.get("last_attempted_at"),
            "last_successful_at": status.get("last_successful_at"),
            "retryable": status.get("retryable", True),
        })
    return rows


def _merge_failed_sections(progress_failed: list[dict], status_failed: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in [*(progress_failed or []), *(status_failed or [])]:
        if not isinstance(item, dict):
            continue
        thread = str(item.get("thread") or item.get("section") or "section")
        error = str(item.get("error") or "")
        key = (thread, error)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _build_record(
    *,
    company_id: str,
    company: dict,
    previous_snapshot: dict | None,
    new_snapshot: dict,
    progress_path: Path | str | None,
    duration_ms: int | None = None,
    status: str = "done",
    baseline_seeded: bool = False,
    retry_scope: str = "snapshot",
    retried_sections: list[str] | None = None,
) -> dict:
    progress_stats = parse_progress_stats(progress_path)
    token_usage = progress_stats["token_usage"]
    done_event = progress_stats.get("done_event") or {}
    wall_duration = duration_ms or progress_stats.get("wall_duration_ms") or _as_int(
        new_snapshot.get("generation_duration_ms")
    )
    change_summary = build_change_summary(previous_snapshot, new_snapshot)
    if baseline_seeded:
        change_summary["baseline"] = True
        change_summary["has_previous"] = False
    failed_sections = _merge_failed_sections(
        progress_stats.get("failed_sections") or [],
        _status_failed_sections(new_snapshot),
    )
    return {
        "schema_version": 1,
        "recorded_at": _now(),
        "status": status,
        "baseline_seeded": bool(baseline_seeded),
        "retry_scope": retry_scope,
        "retried_sections": retried_sections or [],
        "company_id": company_id,
        "ticker": (company.get("ticker") or "").strip().upper(),
        "company_name": company.get("name") or company_id,
        "refreshed_at": new_snapshot.get("refreshed_at") or done_event.get("refreshed_at"),
        "snapshot_schema_version": new_snapshot.get("schema_version"),
        "duration_ms": wall_duration,
        "model_duration_ms": token_usage.get("model_duration_ms") or 0,
        "token_usage": token_usage,
        "cost_usd": _rounded(progress_stats.get("cost_usd") or 0.0, 6),
        "tool_calls": progress_stats.get("tool_calls") or 0,
        "thread_count": len(token_usage.get("by_thread") or []),
        "started_sections": progress_stats.get("started_sections") or [],
        "finished_sections": progress_stats.get("finished_sections") or [],
        "failed_sections": failed_sections,
        "section_status": copy.deepcopy(new_snapshot.get("section_status") or {}),
        "errors": progress_stats.get("errors") or [],
        "progress_path": progress_stats.get("progress_path"),
        "change_summary": change_summary,
        "snapshot_summary": build_snapshot_summary(new_snapshot),
    }


def _append_record(record: dict) -> None:
    path = history_path(str(record.get("company_id") or "unknown"))
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _record_exists(company_id: str, refreshed_at: str | None) -> bool:
    if not refreshed_at:
        return False
    return any(
        item.get("refreshed_at") == refreshed_at
        for item in _read_jsonl(history_path(company_id))
    )


def record_trader_refresh(
    *,
    company_id: str,
    company: dict,
    previous_snapshot: dict | None,
    new_snapshot: dict,
    progress_path: Path | str | None = None,
    duration_ms: int | None = None,
    status: str = "done",
    retry_scope: str = "snapshot",
    retried_sections: list[str] | None = None,
) -> dict:
    """Append one durable stats record for a completed trader refresh."""
    record = _build_record(
        company_id=company_id,
        company=company,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
        progress_path=progress_path,
        duration_ms=duration_ms,
        status=status,
        retry_scope=retry_scope,
        retried_sections=retried_sections,
    )
    _append_record(record)
    return record


def read_history(company_id: str, *, limit: int = 50) -> list[dict]:
    rows = _read_jsonl(history_path(company_id))
    rows.sort(
        key=lambda item: (
            str(item.get("recorded_at") or ""),
            str(item.get("refreshed_at") or ""),
        ),
        reverse=True,
    )
    return rows[: max(1, limit)]


def seed_baseline_records(companies: list[dict]) -> int:
    """Create first longitudinal records from existing snapshots/logs."""
    created = 0
    with _LOCK:
        for company in companies:
            company_id = str(company.get("id") or "").strip()
            snapshot = company.get("trader_snapshot")
            if not company_id or not isinstance(snapshot, dict):
                continue
            company_type = company.get("company_type") or storage.infer_company_type(company)
            if company_type != "public":
                continue
            refreshed_at = snapshot.get("refreshed_at")
            if _record_exists(company_id, refreshed_at):
                continue
            if read_history(company_id, limit=1):
                continue
            progress_path = _default_progress_path(company_id)
            progress_stats = parse_progress_stats(progress_path)
            if (
                progress_path.exists()
                and progress_stats.get("event_count")
                and not progress_stats.get("terminal_event")
            ):
                continue
            record = _build_record(
                company_id=company_id,
                company=company,
                previous_snapshot=None,
                new_snapshot=snapshot,
                progress_path=progress_path,
                duration_ms=_as_int(snapshot.get("generation_duration_ms")),
                status="baseline",
                baseline_seeded=True,
            )
            _append_record(record)
            created += 1
    return created


def _latest_record(company_id: str) -> dict | None:
    history = read_history(company_id, limit=1)
    return history[0] if history else None


def _public_companies(companies: list[dict]) -> list[dict]:
    out = []
    for company in companies:
        company_type = company.get("company_type") or storage.infer_company_type(company)
        if company_type == "public":
            out.append(company)
    return out


def _rollup(items: list[dict], baseline_records_created: int) -> dict:
    latest_records = [
        item.get("latest_record")
        for item in items
        if isinstance(item.get("latest_record"), dict)
    ]
    change_values = [
        rec.get("change_summary", {}).get("change_pct")
        for rec in latest_records
        if isinstance(rec.get("change_summary", {}).get("change_pct"), (int, float))
    ]
    token_totals = {
        field: sum(
            _as_int(rec.get("token_usage", {}).get(field))
            for rec in latest_records
        )
        for field in TOKEN_FIELDS
    }
    total_tokens = sum(_as_int(rec.get("token_usage", {}).get("total_tokens")) for rec in latest_records)
    cost = sum(_as_float(rec.get("cost_usd")) or 0.0 for rec in latest_records)
    failed = sum(len(rec.get("failed_sections") or []) for rec in latest_records)
    retry_needed = sum(
        1
        for rec in latest_records
        if rec.get("failed_sections")
        or any(
            isinstance(row, dict)
            and row.get("status") in {"failed", "stale"}
            and row.get("retryable", True)
            for row in (rec.get("section_status") or {}).values()
        )
    )
    latest_recorded_at = max(
        (str(rec.get("recorded_at") or "") for rec in latest_records),
        default=None,
    )
    return {
        "company_count": len(items),
        "recorded_count": len(latest_records),
        "baseline_records_created": baseline_records_created,
        "total_tokens": total_tokens,
        **token_totals,
        "cost_usd": round(cost, 6),
        "failed_section_count": failed,
        "retry_needed_count": retry_needed,
        "average_change_pct": (
            round(sum(change_values) / len(change_values), 2)
            if change_values
            else None
        ),
        "latest_recorded_at": latest_recorded_at,
    }


def build_dashboard(companies: list[dict], *, limit: int = 30) -> dict:
    baseline_count = seed_baseline_records(companies)
    items: list[dict] = []
    for company in _public_companies(companies):
        company_id = str(company.get("id") or "").strip()
        if not company_id:
            continue
        history = read_history(company_id, limit=limit)
        latest = history[0] if history else _latest_record(company_id)
        items.append({
            "company_id": company_id,
            "ticker": (company.get("ticker") or "").strip().upper(),
            "company_name": company.get("name") or company_id,
            "latest_record": latest,
            "history": history,
            "current_snapshot_summary": build_snapshot_summary(
                company.get("trader_snapshot")
                if isinstance(company.get("trader_snapshot"), dict)
                else None
            ),
        })
    items.sort(key=lambda item: item.get("ticker") or item.get("company_name") or "")
    return {
        "generated_at": _now(),
        "history_limit": limit,
        "items": items,
        "totals": _rollup(items, baseline_count),
    }


def build_company_stats(company_id: str, company: dict, *, limit: int = 80) -> dict:
    seed_baseline_records([company])
    history = read_history(company_id, limit=limit)
    return {
        "generated_at": _now(),
        "company_id": company_id,
        "ticker": (company.get("ticker") or "").strip().upper(),
        "company_name": company.get("name") or company_id,
        "latest_record": history[0] if history else None,
        "history": history,
        "current_snapshot_summary": build_snapshot_summary(
            company.get("trader_snapshot")
            if isinstance(company.get("trader_snapshot"), dict)
            else None
        ),
    }
