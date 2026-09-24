"""Local product analytics event store.

The PRD asks for product-success instrumentation without external telemetry.
This module keeps that surface deliberately local and inspectable: append-only
JSONL under ``data/analytics`` plus a small summary helper for Settings/Admin.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _events_file() -> Path:
    return storage.DATA_DIR / "analytics" / "events.jsonl"


def record_event(event: str, **payload: Any) -> dict:
    row = {
        "event": str(event or "").strip(),
        "ts": _now(),
        **payload,
    }
    if not row["event"]:
        raise ValueError("event is required")
    with _LOCK:
        path = _events_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def list_events(*, limit: int = 500, event: str | None = None) -> list[dict]:
    path = _events_file()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if event and row.get("event") != event:
                    continue
                rows.append(row)
    except OSError:
        return []
    rows.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    return rows[: max(1, int(limit or 1))]


def summary() -> dict:
    rows = list_events(limit=10000)
    chronological = sorted(rows, key=lambda row: str(row.get("ts") or ""))
    counts: dict[str, int] = {}
    for row in rows:
        event = str(row.get("event") or "")
        counts[event] = counts.get(event, 0) + 1

    first_interest_by_company: dict[str, datetime] = {}
    first_memo_by_company: dict[str, datetime] = {}
    latest_coverage: dict[str, Any] | None = None
    proposed = counts.get("copilot_task_proposed", 0)
    actioned = counts.get("copilot_task_actioned", 0)
    section_reruns = counts.get("section_rerun", 0)
    section_reused = counts.get("section_reused", 0)

    for row in chronological:
        event = row.get("event")
        company_id = str(row.get("company_id") or "").strip()
        ts = _parse_ts(row.get("ts"))
        if not ts:
            continue
        if event in {"search_started", "workspace_opened"} and company_id:
            first_interest_by_company.setdefault(company_id, ts)
        if event == "memo_first_draft_ready" and company_id:
            first_memo_by_company.setdefault(company_id, ts)
        if event == "memo_exported" and isinstance(row.get("source_coverage"), dict):
            latest_coverage = row.get("source_coverage")

    deltas: list[float] = []
    for company_id, memo_ts in first_memo_by_company.items():
        start_ts = first_interest_by_company.get(company_id)
        if start_ts and memo_ts >= start_ts:
            deltas.append((memo_ts - start_ts).total_seconds() / 60.0)
    deltas.sort()
    median_minutes = None
    if deltas:
        mid = len(deltas) // 2
        if len(deltas) % 2:
            median_minutes = deltas[mid]
        else:
            median_minutes = (deltas[mid - 1] + deltas[mid]) / 2.0

    acceptance_rate = None if proposed == 0 else actioned / proposed
    reuse_ratio = None
    if section_reruns + section_reused:
        reuse_ratio = section_reused / (section_reruns + section_reused)

    reports_read = _reports_read_block(rows)

    return {
        "generated_at": _now(),
        "event_counts": counts,
        "time_to_first_memo": {
            "company_count": len(deltas),
            "median_minutes": median_minutes,
            "target_minutes": 120,
        },
        "source_coverage": latest_coverage
        or {
            "key_figure_count": 0,
            "covered_key_figure_count": 0,
            "missing_key_figure_count": 0,
            "coverage": None,
        },
        "copilot_task_acceptance": {
            "proposed": proposed,
            "actioned": actioned,
            "acceptance_rate": acceptance_rate,
            "target": 0.6,
        },
        "section_reuse": {
            "reused": section_reused,
            "regenerated": section_reruns,
            "reuse_ratio": reuse_ratio,
        },
        "reports_read": reports_read,
        "recent_events": rows[:25],
    }


def _reports_read_block(rows: list[dict]) -> dict:
    """Reports read / flagged: report_opened and report_downloaded events
    (one per reader session, see POST /api/reports/{id}/events) and the
    reader flags on report comments. Readers are counted by a hash, never
    named."""
    opened = [r for r in rows if r.get("event") == "report_opened"]
    downloaded = [r for r in rows if r.get("event") == "report_downloaded"]
    readers = {str(r.get("reader")) for r in opened + downloaded if r.get("reader")}
    flags_total = 0
    flags_open = 0
    flags_by_type: dict[str, int] = {}
    flagged_reports: set[str] = set()
    try:
        from . import firm

        for item in firm.all_comments():
            if not isinstance(item, dict) or not item.get("flag"):
                continue
            target = item.get("target") or {}
            if target.get("kind") not in firm.REPORT_TARGET_KINDS:
                continue
            flags_total += 1
            flag = str(item.get("flag"))
            flags_by_type[flag] = flags_by_type.get(flag, 0) + 1
            if not item.get("resolved_at"):
                flags_open += 1
            if target.get("ref"):
                flagged_reports.add(str(target.get("ref")))
    except Exception:  # noqa: BLE001 — a summary block must not break Settings
        pass
    return {
        "opened": len(opened),
        "reports_opened": len({str(r.get("report_id")) for r in opened if r.get("report_id")}),
        "downloaded": len(downloaded),
        "reports_downloaded": len(
            {str(r.get("report_id")) for r in downloaded if r.get("report_id")}
        ),
        "readers": len(readers),
        "flags_total": flags_total,
        "flags_open": flags_open,
        "flags_by_type": flags_by_type,
        "reports_flagged": len(flagged_reports),
    }
