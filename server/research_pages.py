"""Stable payload assembly for analyst-facing research pages.

These functions intentionally sit beside the existing Stock Research, Memo
Studio, and hypothesis modules. They normalize durable local artifacts into
page contracts without starting jobs or calling external services.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import evidence_matrix, hypothesis_store, stock_research, storage

SCHEMA_VERSION = 1

SOURCE_TYPES = {
    "sec_filing",
    "company_press_release",
    "earnings_call_transcript",
    "investor_presentation",
    "regulatory_filing",
    "primary_dataset",
    "broker_note",
    "reputable_media",
    "weak_media",
    "analyst_note",
    "unsourced_note",
    "unknown",
}

SOURCE_TYPE_ALIASES = {
    "official": "company_press_release",
    "company_disclosure": "company_press_release",
    "transcript": "earnings_call_transcript",
    "primary_data": "primary_dataset",
    "sell_side": "broker_note",
    "vertical_media": "reputable_media",
    "financial_media": "reputable_media",
    "user_provided": "analyst_note",
    "note": "analyst_note",
}

PRIMARY_SOURCE_TYPES = {
    "sec_filing",
    "company_press_release",
    "earnings_call_transcript",
    "investor_presentation",
    "regulatory_filing",
    "primary_dataset",
}

WEAK_SOURCE_TYPES = {"weak_media", "analyst_note", "unsourced_note", "unknown"}

HYPOTHESIS_DOCTOR_TYPES = {
    "missing_current_live_hypothesis_vintage",
    "hypothesis_generated_after_window_start",
    "hypothesis_outcome_missing_after_window_close",
    "training_summary_includes_debug_rows",
    "hypothesis_source_cutoff_violation",
    "malformed_hypothesis_data",
}

PLACEHOLDER_ACTION_REASON = "Planned action; no durable endpoint is wired yet."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value).strip() or default


def _as_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean(value: Any, *, limit: int | None = None) -> str:
    text = " ".join(_as_str(value).split())
    return text[:limit].rstrip() if limit else text


def _parse_dt(value: Any) -> datetime | None:
    text = _as_str(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(
                date.fromisoformat(text),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: Any) -> date | None:
    text = _as_str(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _days_since(value: Any) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max(0, (date.today() - parsed).days)


def _slug(value: str, *, fallback: str = "item") -> str:
    raw = re.sub(r"[^a-z0-9_.-]+", "-", (value or "").lower()).strip(".-")
    raw = re.sub(r"-{2,}", "-", raw)
    return (raw or fallback)[:96]


def _issue(
    severity: str,
    issue_type: str,
    message: str,
    **fields: Any,
) -> dict[str, Any]:
    row = {"severity": severity, "type": issue_type, "message": message}
    row.update({key: value for key, value in fields.items() if value not in (None, "", [], {})})
    return row


def _placeholder_action(
    action_id: str,
    label: str,
    *,
    method: str = "POST",
    reason: str = PLACEHOLDER_ACTION_REASON,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "method": method,
        "endpoint": None,
        "disabled": True,
        "placeholder": True,
        "reason": reason,
    }


def _common_payload(
    page_id: str,
    *,
    generated_at: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "generated_at": generated_at or _now(),
        "as_of": as_of or _today(),
        "status": "empty",
        "summary": {},
        "sections": {},
        "source_health": {},
        "doctor_issues": [],
        "actions": [],
    }


def _status_for(rows: list[Any], issues: list[dict[str, Any]]) -> str:
    if not rows:
        return "empty"
    if any(issue.get("severity") == "error" for issue in issues):
        return "issues"
    if issues:
        return "partial"
    return "ok"


def _read_json(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _all_aggregates() -> list[dict[str, Any]]:
    root = stock_research.aggregates_root()
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.glob("*/weekly_report.json"):
        data = _read_json(path)
        if isinstance(data, dict):
            rows.append(data)
    rows.sort(
        key=lambda row: (
            _as_str(row.get("generated_at")),
            _as_str(row.get("period_end")),
            _as_str(row.get("period_id")),
        ),
        reverse=True,
    )
    return rows


def _previous_aggregate(current: dict[str, Any] | None) -> dict[str, Any] | None:
    if not current:
        return None
    current_period = current.get("period_id")
    current_generated = current.get("generated_at")
    for row in _all_aggregates():
        if row.get("period_id") == current_period and row.get("generated_at") == current_generated:
            continue
        return row
    return None


def _source_quality_type(source: dict[str, Any] | None, trace: dict[str, Any] | None = None) -> str:
    if isinstance(source, dict):
        priority = _as_str(source.get("priority"), "unknown").lower()
    else:
        priority = _as_str((trace or {}).get("source_type") or (trace or {}).get("priority"), "unknown").lower()
    normalized = SOURCE_TYPE_ALIASES.get(priority, priority)
    return normalized if normalized in SOURCE_TYPES else "unknown"


def _source_lookup() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    by_tracker: dict[tuple[str, str], dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for tracker in stock_research.list_trackers(include_archived=True):
        tracker_id = _as_str(tracker.get("id"))
        for source in stock_research.list_tracker_sources(tracker_id):
            source_id = _as_str(source.get("id"))
            if not source_id:
                continue
            by_tracker[(tracker_id, source_id)] = source
            by_id.setdefault(source_id, source)
    return by_tracker, by_id


def _normalize_trace(
    value: Any,
    *,
    source_lookup: tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]],
    default_tracker_id: str = "",
    artifact_id: str | None = None,
) -> dict[str, Any]:
    trace = value if isinstance(value, dict) else {}
    by_tracker, by_id = source_lookup
    tracker_id = _as_str(trace.get("tracker_id") or default_tracker_id)
    source_id = _as_str(trace.get("source_id"))
    source = (
        by_tracker.get((tracker_id, source_id)) or by_id.get(source_id)
        if source_id
        else None
    )
    source_type = _source_quality_type(source, trace)
    confidence = _as_float(trace.get("confidence"), None)
    if confidence is None and isinstance(source, dict):
        confidence = stock_research.source_quality_score(source)
    if confidence is None:
        confidence = 0.0 if not source_id else stock_research.SOURCE_PRIORITY_SCORES["unknown"]
    published_at = (
        trace.get("published_at")
        or trace.get("timestamp")
        or (source or {}).get("published_at")
        or (source or {}).get("created_at")
    )
    return {
        "source_id": source_id or None,
        "source_title": _clean(
            trace.get("source_title")
            or trace.get("title")
            or (source or {}).get("title")
            or (source or {}).get("filename")
            or "Missing source",
            limit=180,
        ),
        "source_type": source_type,
        "url": trace.get("url") or (source or {}).get("url"),
        "file_id": trace.get("file_id") or ((source or {}).get("id") if (source or {}).get("source_type") == "file" else None),
        "artifact_id": artifact_id,
        "locator": _clean(trace.get("locator") or trace.get("timestamp") or "source", limit=120),
        "excerpt": _clean(trace.get("excerpt") or (source or {}).get("notes") or "", limit=320),
        "published_at": published_at[:10] if isinstance(published_at, str) and len(published_at) >= 10 else published_at,
        "checked_at": trace.get("checked_at") or _now(),
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "source_quality_score": round(stock_research.SOURCE_PRIORITY_SCORES.get(source_type, stock_research.SOURCE_PRIORITY_SCORES["unknown"]), 3),
        "source_exists": bool(source) if source_id else False,
    }


def _trace_stats(refs: list[dict[str, Any]]) -> dict[str, Any]:
    if not refs:
        return {
            "source_count": 0,
            "primary_source_count": 0,
            "weak_source_count": 0,
            "source_quality_score": 0.0,
            "stale_source_count": 0,
            "missing_source_count": 1,
        }
    source_ids = {ref.get("source_id") or f"trace-{index}" for index, ref in enumerate(refs)}
    primary = sum(1 for ref in refs if ref.get("source_type") in PRIMARY_SOURCE_TYPES)
    weak = sum(1 for ref in refs if ref.get("source_type") in WEAK_SOURCE_TYPES)
    stale = sum(
        1
        for ref in refs
        if (_days_since(ref.get("published_at")) is not None and (_days_since(ref.get("published_at")) or 0) > 180)
    )
    missing = sum(1 for ref in refs if ref.get("source_id") and not ref.get("source_exists"))
    score = round(sum(_as_float(ref.get("confidence"), 0.0) or 0.0 for ref in refs) / len(refs), 3)
    return {
        "source_count": len(source_ids),
        "primary_source_count": primary,
        "weak_source_count": weak,
        "source_quality_score": score,
        "stale_source_count": stale,
        "missing_source_count": missing,
    }


def _signal_text(signal: dict[str, Any]) -> str:
    return _clean(
        signal.get("signal")
        or signal.get("observation")
        or signal.get("claim")
        or signal.get("thesis")
        or signal.get("description")
        or "Untitled market signal",
        limit=420,
    )


def _signal_key(row: dict[str, Any]) -> str:
    return _slug(f"{row.get('tracker_id') or row.get('company_id') or ''}-{row.get('signal') or row.get('claim')}")


def _signal_direction_score(direction: str) -> int:
    text = direction.lower()
    if text in {"bullish", "positive", "risk_on", "up"}:
        return 1
    if text in {"bearish", "negative", "risk_off", "down"}:
        return -1
    return 0


def _normalize_market_signal(
    signal: dict[str, Any],
    *,
    index: int,
    source_lookup: tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    tracker_id = _as_str(signal.get("source_tracker_id") or signal.get("tracker_id"))
    run_id = _as_str(signal.get("tracker_run_id") or signal.get("run_id"))
    artifact_id = f"tracker_run:{tracker_id}:{run_id}" if tracker_id and run_id else None
    refs = [
        _normalize_trace(
            trace,
            source_lookup=source_lookup,
            default_tracker_id=tracker_id,
            artifact_id=artifact_id,
        )
        for trace in _as_list(signal.get("source_traces") or signal.get("source_refs"))
        if isinstance(trace, dict)
    ]
    stats = _trace_stats(refs)
    source_quality = _as_float(signal.get("source_quality_score"), stats["source_quality_score"]) or 0.0
    primary_count = _as_int(signal.get("primary_source_count"), stats["primary_source_count"])
    weak_count = _as_int(signal.get("weak_source_count"), stats["weak_source_count"])
    confidence = _as_float(signal.get("confidence"), None)
    if confidence is None:
        confidence = source_quality if refs else 0.2
    importance = max(1, min(5, _as_int(signal.get("importance"), 3)))
    actionability = round((importance / 5 * 0.3) + (confidence * 0.3) + (source_quality * 0.4), 3)
    tickers = [
        _as_str(item).upper()
        for item in _as_list(signal.get("affected_tickers") or signal.get("tickers") or signal.get("ticker"))
        if _as_str(item)
    ]
    themes = [
        _as_str(item)
        for item in _as_list(signal.get("affected_themes") or signal.get("themes") or signal.get("theme"))
        if _as_str(item)
    ]
    signal_text = _signal_text(signal)
    return {
        "signal_id": _as_str(signal.get("id"), f"signal-{index}"),
        "signal": signal_text,
        "direction": _as_str(signal.get("direction"), "watch"),
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "importance": importance,
        "source_quality_score": round(max(0.0, min(1.0, source_quality)), 3),
        "source_quality_reason": _as_str(signal.get("source_quality_reason")),
        "primary_source_count": primary_count,
        "weak_source_count": weak_count,
        "source_count": stats["source_count"],
        "related_tickers": tickers,
        "related_themes": themes,
        "tracker_id": tracker_id,
        "tracker_run_id": run_id,
        "artifact_id": artifact_id,
        "source_refs": refs,
        "novelty_vs_previous_period": "unknown",
        "actionability": actionability,
        "rank_score": round((importance * 0.5) + (confidence * 2.0) + (source_quality * 2.0), 4),
        "review_status": _as_str(signal.get("review_status"), "open"),
    }


def _market_heatmap(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        keys = signal.get("related_themes") or signal.get("related_tickers") or [signal.get("tracker_id") or "Unmapped"]
        for key in keys:
            groups.setdefault(_as_str(key, "Unmapped"), []).append(signal)
    rows = []
    for key, items in groups.items():
        net = sum(_signal_direction_score(_as_str(item.get("direction"))) for item in items)
        quality = round(
            sum(_as_float(item.get("source_quality_score"), 0.0) or 0.0 for item in items)
            / len(items),
            3,
        )
        rows.append(
            {
                "theme": key,
                "signal_count": len(items),
                "average_quality": quality,
                "net_direction": net,
                "posture": "positive" if net > 0 else "negative" if net < 0 else "mixed",
            }
        )
    rows.sort(key=lambda row: (row["signal_count"], row["average_quality"]), reverse=True)
    return rows


def _market_diff(
    current: list[dict[str, Any]],
    previous_aggregate: dict[str, Any] | None,
    *,
    source_lookup: tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    if not previous_aggregate:
        return {
            "previous_period_id": None,
            "new_signals": [],
            "fading_signals": [],
            "revised_conviction": [],
            "new_contradictions": [],
        }
    previous = [
        _normalize_market_signal(signal, index=index, source_lookup=source_lookup)
        for index, signal in enumerate(_as_list(previous_aggregate.get("ranked_signals")), start=1)
        if isinstance(signal, dict)
    ]
    current_by_key = {_signal_key(row): row for row in current}
    previous_by_key = {_signal_key(row): row for row in previous}
    revised = []
    for key, row in current_by_key.items():
        old = previous_by_key.get(key)
        if not old:
            continue
        if row.get("direction") != old.get("direction") or abs(
            (_as_float(row.get("confidence"), 0.0) or 0.0)
            - (_as_float(old.get("confidence"), 0.0) or 0.0)
        ) >= 0.1:
            revised.append(
                {
                    "signal_id": row["signal_id"],
                    "signal": row["signal"],
                    "previous_direction": old.get("direction"),
                    "current_direction": row.get("direction"),
                    "previous_confidence": old.get("confidence"),
                    "current_confidence": row.get("confidence"),
                }
            )
    return {
        "previous_period_id": previous_aggregate.get("period_id"),
        "new_signals": [row for key, row in current_by_key.items() if key not in previous_by_key][:10],
        "fading_signals": [row for key, row in previous_by_key.items() if key not in current_by_key][:10],
        "revised_conviction": revised[:10],
        "new_contradictions": _as_list(previous_aggregate.get("contradictions"))[:10],
    }


def _source_health_from_refs(
    refs: list[dict[str, Any]],
    *,
    contradiction_count: int = 0,
    missing_trace_count: int = 0,
) -> dict[str, Any]:
    counts: dict[str, int] = {source_type: 0 for source_type in sorted(SOURCE_TYPES)}
    for ref in refs:
        counts[_as_str(ref.get("source_type"), "unknown")] = counts.get(_as_str(ref.get("source_type"), "unknown"), 0) + 1
    quality_values = [_as_float(ref.get("confidence"), None) for ref in refs]
    quality_values = [value for value in quality_values if value is not None]
    return {
        "source_counts_by_type": {key: value for key, value in counts.items() if value},
        "source_trace_count": len(refs),
        "average_source_quality": round(sum(quality_values) / len(quality_values), 3) if quality_values else 0.0,
        "primary_source_count": sum(1 for ref in refs if ref.get("source_type") in PRIMARY_SOURCE_TYPES),
        "weak_source_count": sum(1 for ref in refs if ref.get("source_type") in WEAK_SOURCE_TYPES),
        "missing_trace_count": missing_trace_count,
        "stale_source_count": sum(
            1
            for ref in refs
            if (_days_since(ref.get("published_at")) is not None and (_days_since(ref.get("published_at")) or 0) > 180)
        ),
        "contradiction_count": contradiction_count,
    }


def market_pulse_page() -> dict[str, Any]:
    aggregate = stock_research.latest_aggregate()
    as_of = (
        _as_str((aggregate or {}).get("period_end"))
        or _as_str((aggregate or {}).get("generated_at"))[:10]
        or _today()
    )
    payload = _common_payload("market_pulse", as_of=as_of)
    issues: list[dict[str, Any]] = []
    if not aggregate:
        issues.append(
            _issue(
                "error",
                "market_pulse_missing_latest_aggregate",
                "No Stock Research weekly aggregate exists. Run /api/stock-research/aggregates/run after tracker runs complete.",
            )
        )
        payload.update(
            {
                "status": "empty",
                "summary": {
                    "signal_count": 0,
                    "empty_state": "Missing latest Stock Research weekly aggregate.",
                },
                "sections": {
                    "market_regime": {
                        "posture": "empty",
                        "breadth": {
                            "positive_signals": 0,
                            "negative_signals": 0,
                            "neutral_signals": 0,
                        },
                        "sector_leadership": [],
                        "volatility": {
                            "status": "placeholder",
                            "message": "Point-in-time volatility data is not connected yet.",
                        },
                        "rates": {
                            "status": "placeholder",
                            "message": "Rates data is pending the data foundation.",
                        },
                        "liquidity": {
                            "status": "placeholder",
                            "message": "Liquidity data is pending the data foundation.",
                        },
                    },
                    "ranked_signals": [],
                    "theme_heatmap": [],
                    "changed_since_last_week": {
                        "previous_period_id": None,
                        "new_signals": [],
                        "fading_signals": [],
                        "revised_conviction": [],
                        "new_contradictions": [],
                    },
                    "catalyst_calendar": [],
                    "next_steps": [
                        {
                            "label": "Run Stock Research weekly aggregate",
                            "method": "POST",
                            "endpoint": "/api/stock-research/aggregates/run",
                            "requires": "Completed tracker runs with source traces.",
                        }
                    ],
                },
                "source_health": _source_health_from_refs([]),
                "doctor_issues": issues,
                "actions": [
                    {
                        "id": "refresh_market_pulse",
                        "label": "Run weekly aggregate",
                        "method": "POST",
                        "endpoint": "/api/stock-research/aggregates/run",
                    }
                ],
            }
        )
        return payload

    lookup = _source_lookup()
    signals = [
        _normalize_market_signal(signal, index=index, source_lookup=lookup)
        for index, signal in enumerate(_as_list(aggregate.get("ranked_signals")), start=1)
        if isinstance(signal, dict)
    ]
    signals.sort(key=lambda row: row["rank_score"], reverse=True)
    if not signals:
        issues.append(
            _issue(
                "warning",
                "market_pulse_no_ranked_signals",
                "The latest aggregate has no ranked signals.",
                artifact_id=f"weekly_aggregate:{aggregate.get('period_id')}",
            )
        )
    for signal in signals:
        if not signal["source_refs"]:
            issues.append(
                _issue(
                    "error",
                    "market_pulse_signal_missing_source_trace",
                    "Market Pulse signal has no source trace.",
                    artifact_id=signal.get("artifact_id"),
                    source_ref=signal.get("signal_id"),
                )
            )
        elif signal["primary_source_count"] == 0 and signal["weak_source_count"] >= signal["source_count"]:
            issues.append(
                _issue(
                    "warning",
                    "market_pulse_weak_source_only_signal",
                    "Market Pulse signal is supported only by weak, note-based, or unknown sources.",
                    artifact_id=signal.get("artifact_id"),
                    source_ref=signal.get("signal_id"),
                )
            )
        for ref in signal["source_refs"]:
            if ref.get("source_id") and not ref.get("source_exists"):
                issues.append(
                    _issue(
                        "error",
                        "market_pulse_broken_artifact_ref",
                        "Signal source trace points at a source id that is not present in the tracker manifest.",
                        artifact_id=signal.get("artifact_id"),
                        source_ref=ref.get("source_id"),
                    )
                )
    previous = _previous_aggregate(aggregate)
    if previous is None:
        issues.append(
            _issue(
                "info",
                "market_pulse_missing_previous_period_for_diff",
                "No previous weekly aggregate is available for the change-since-last-week panel.",
            )
        )
    refs = [ref for signal in signals for ref in signal["source_refs"]]
    heatmap = _market_heatmap(signals)
    positives = sum(1 for signal in signals if _signal_direction_score(signal["direction"]) > 0)
    negatives = sum(1 for signal in signals if _signal_direction_score(signal["direction"]) < 0)
    posture = "risk-on" if positives > negatives else "risk-off" if negatives > positives else "neutral"
    payload.update(
        {
            "status": _status_for(signals, issues),
            "summary": {
                "period_id": aggregate.get("period_id"),
                "signal_count": len(signals),
                "primary_source_signal_count": sum(1 for signal in signals if signal["primary_source_count"] > 0),
                "weak_or_missing_signal_count": sum(
                    1
                    for signal in signals
                    if not signal["source_refs"]
                    or (signal["primary_source_count"] == 0 and signal["weak_source_count"] >= signal["source_count"])
                ),
                "top_signal": signals[0]["signal"] if signals else "",
            },
            "sections": {
                "market_regime": {
                    "posture": posture,
                    "breadth": {
                        "positive_signals": positives,
                        "negative_signals": negatives,
                        "neutral_signals": len(signals) - positives - negatives,
                    },
                    "sector_leadership": heatmap[:5],
                    "volatility": {"status": "placeholder", "message": "Point-in-time volatility data is not connected yet."},
                    "rates": {"status": "placeholder", "message": "Rates data is pending the data foundation."},
                    "liquidity": {"status": "placeholder", "message": "Liquidity data is pending the data foundation."},
                },
                "ranked_signals": signals,
                "theme_heatmap": heatmap,
                "changed_since_last_week": _market_diff(signals, previous, source_lookup=lookup),
                "catalyst_calendar": [
                    {
                        "event_date": item.get("event_date") or item.get("date") or item.get("expected_date"),
                        "ticker_or_theme": item.get("ticker") or item.get("theme") or item.get("tracker_id") or "Unmapped",
                        "event": item.get("event") or item.get("title") or item.get("description") or "Catalyst",
                        "expected_impact": item.get("expected_impact") or item.get("impact") or "unknown",
                        "source_refs": [
                            _normalize_trace(trace, source_lookup=lookup, default_tracker_id=_as_str(item.get("tracker_id")))
                            for trace in _as_list(item.get("source_traces") or item.get("source_refs"))
                            if isinstance(trace, dict)
                        ],
                    }
                    for item in _as_list(aggregate.get("event_calendar"))
                    if isinstance(item, dict)
                ][:12],
            },
            "source_health": _source_health_from_refs(
                refs,
                contradiction_count=len(_as_list(aggregate.get("contradictions"))),
                missing_trace_count=sum(1 for signal in signals if not signal["source_refs"]),
            ),
            "doctor_issues": issues,
            "actions": [
                {
                    "id": "create_hypothesis",
                    "label": "Create hypothesis from signal",
                    "endpoint": "/api/stock-research/hypotheses/create",
                    "method": "POST",
                    "disabled": True,
                    "placeholder": True,
                    "reason": "Signal-specific hypothesis drafting is planned; use Hypothesis Lab to create a dated vintage.",
                },
                {
                    "id": "refresh_market_pulse",
                    "label": "Run weekly aggregate",
                    "method": "POST",
                    "endpoint": "/api/stock-research/aggregates/run",
                },
                _placeholder_action("start_research_task", "Start missing-source research task"),
            ],
        }
    )
    return payload


def _claim_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("tam", "market", "demand", "adoption")):
        return "market"
    if any(token in lowered for token in ("product", "platform", "technical", "technology")):
        return "product"
    if any(token in lowered for token in ("revenue", "margin", "cash", "financial", "multiple")):
        return "financial"
    if any(token in lowered for token in ("customer", "contract", "pipeline")):
        return "customer"
    if any(token in lowered for token in ("competition", "competitive", "peer")):
        return "competitive"
    if any(token in lowered for token in ("legal", "regulatory", "lawsuit")):
        return "legal"
    if any(token in lowered for token in ("management", "ceo", "founder")):
        return "management"
    if any(token in lowered for token in ("valuation", "price target", "ev/")):
        return "valuation"
    if any(token in lowered for token in ("traction", "growth", "retention")):
        return "traction"
    return "other"


def _confidence_score(value: Any) -> float:
    text = _as_str(value).lower()
    if text == "high":
        return 0.85
    if text == "medium":
        return 0.6
    if text == "low":
        return 0.35
    number = _as_float(value, None)
    return max(0.0, min(1.0, number)) if number is not None else 0.45


def _normalize_company_claim(
    row: dict[str, Any],
    *,
    company_id: str,
    company_name: str,
    index: int,
) -> dict[str, Any]:
    refs = []
    lookup = ({}, {})
    for evidence in _as_list(row.get("supporting_evidence")):
        if isinstance(evidence, dict):
            refs.append(
                _normalize_trace(
                    {
                        "source_id": evidence.get("file_id") or evidence.get("task_id"),
                        "source_title": evidence.get("filename") or evidence.get("task_title"),
                        "source_type": evidence.get("source_kind"),
                        "locator": evidence.get("locator"),
                        "excerpt": evidence.get("excerpt"),
                        "confidence": _confidence_score(evidence.get("confidence")),
                    },
                    source_lookup=lookup,
                    artifact_id=evidence.get("task_id") or evidence.get("file_id"),
                )
            )
    contradictions = []
    for evidence in _as_list(row.get("contradicting_evidence")):
        if isinstance(evidence, dict):
            contradictions.append(
                _normalize_trace(
                    {
                        "source_id": evidence.get("file_id") or evidence.get("task_id"),
                        "source_title": evidence.get("filename") or evidence.get("task_title"),
                        "source_type": evidence.get("source_kind"),
                        "locator": evidence.get("locator"),
                        "excerpt": evidence.get("excerpt"),
                        "confidence": _confidence_score(evidence.get("confidence")),
                    },
                    source_lookup=lookup,
                    artifact_id=evidence.get("task_id") or evidence.get("file_id"),
                )
            )
    status = _as_str(row.get("status"), "needs_review")
    mapped_status = {
        "supported": "supported",
        "partial": "needs_review",
        "mixed": "needs_review",
        "contradicted": "contradicted",
        "missing": "unsupported",
    }.get(status, status)
    coverage = row.get("source_coverage") if isinstance(row.get("source_coverage"), dict) else {}
    source_count = _as_int(coverage.get("source_count"), len(refs))
    contradiction_count = _as_int(coverage.get("contradicting_count"), len(contradictions))
    confidence = _confidence_score(row.get("confidence"))
    support_factor = min(1.0, source_count / 3)
    evidence_strength = round(max(0.0, min(1.0, confidence * 0.7 + support_factor * 0.3 - contradiction_count * 0.1)), 3)
    claim = _clean(row.get("claim"), limit=650)
    stats = _trace_stats(refs)
    eligible_for_memo = mapped_status == "supported" and stats["primary_source_count"] > 0
    eligible_for_hypothesis = mapped_status in {"supported", "needs_review", "contradicted"}
    if eligible_for_memo:
        memo_reason = "Primary-source supported and ready for memo use."
    elif mapped_status != "supported":
        memo_reason = f"Memo blocked because claim status is {mapped_status}."
    elif stats["primary_source_count"] == 0:
        memo_reason = "Memo blocked until a primary source trace is attached."
    else:
        memo_reason = "Memo blocked pending evidence review."
    hypothesis_reason = (
        "Eligible for hypothesis review."
        if eligible_for_hypothesis
        else "Hypothesis blocked until the claim has reviewable evidence."
    )
    return {
        "claim_id": f"claim-{_slug(company_id)}-{index}",
        "company_id": company_id,
        "company_name": company_name,
        "claim": claim,
        "claim_type": _claim_type(claim),
        "importance": "high" if contradiction_count or source_count >= 3 else "medium" if source_count else "low",
        "status": mapped_status,
        "evidence_strength": evidence_strength,
        "source_quality_score": stats["source_quality_score"],
        "source_count": source_count,
        "primary_source_count": stats["primary_source_count"],
        "weak_source_count": stats["weak_source_count"] if refs else 0,
        "contradiction_count": contradiction_count,
        "recency_days": None,
        "source_refs": refs,
        "contradictions": contradictions,
        "eligible_for_memo": eligible_for_memo,
        "eligible_for_hypothesis": eligible_for_hypothesis,
        "memo_eligibility_reason": memo_reason,
        "hypothesis_eligibility_reason": hypothesis_reason,
        "notes": "",
    }


def _normalize_signal_claim(
    signal: dict[str, Any],
    *,
    index: int,
    source_lookup: tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    market_signal = _normalize_market_signal(signal, index=index, source_lookup=source_lookup)
    claim = market_signal["signal"]
    company_id = (
        _slug(market_signal["related_tickers"][0].lower())
        if market_signal["related_tickers"]
        else market_signal.get("tracker_id") or "market"
    )
    stats = _trace_stats(market_signal["source_refs"])
    eligible_for_hypothesis = bool(market_signal["source_refs"])
    if market_signal["source_refs"]:
        memo_reason = "Memo blocked until the signal is promoted to a primary-source-supported company claim."
    else:
        memo_reason = "Memo blocked because no source trace is attached."
    hypothesis_reason = (
        "Eligible for hypothesis review from Stock Research signal."
        if eligible_for_hypothesis
        else "Hypothesis blocked until a source trace is attached."
    )
    return {
        "claim_id": f"stock-signal-{market_signal['signal_id']}",
        "company_id": company_id,
        "company_name": market_signal["related_tickers"][0] if market_signal["related_tickers"] else company_id,
        "claim": claim,
        "claim_type": _claim_type(claim),
        "importance": "high" if market_signal["importance"] >= 4 else "medium" if market_signal["importance"] >= 2 else "low",
        "status": "needs_review" if market_signal["source_refs"] else "unsupported",
        "evidence_strength": round((market_signal["confidence"] * 0.45) + (market_signal["source_quality_score"] * 0.55), 3),
        "source_quality_score": market_signal["source_quality_score"],
        "source_count": stats["source_count"],
        "primary_source_count": market_signal["primary_source_count"],
        "weak_source_count": market_signal["weak_source_count"],
        "contradiction_count": 0,
        "recency_days": min(
            [days for days in (_days_since(ref.get("published_at")) for ref in market_signal["source_refs"]) if days is not None],
            default=None,
        ),
        "source_refs": market_signal["source_refs"],
        "contradictions": [],
        "eligible_for_memo": False,
        "eligible_for_hypothesis": eligible_for_hypothesis,
        "memo_eligibility_reason": memo_reason,
        "hypothesis_eligibility_reason": hypothesis_reason,
        "notes": "From latest Stock Research ranked signal.",
    }


def _dedupe_claims(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicates = []
    for row in rows:
        key = (
            _as_str(row.get("company_id")),
            _as_str(row.get("claim_type")),
            _slug(_as_str(row.get("claim"))[:160]),
        )
        if key in seen:
            duplicates.append(row)
            existing = seen[key]
            existing["source_refs"] = [*existing.get("source_refs", []), *row.get("source_refs", [])]
            existing["source_count"] = len({ref.get("source_id") or ref.get("source_title") for ref in existing["source_refs"]})
            existing["contradiction_count"] += _as_int(row.get("contradiction_count"), 0)
            existing["contradictions"] = [*existing.get("contradictions", []), *row.get("contradictions", [])]
            existing["evidence_strength"] = max(existing.get("evidence_strength") or 0, row.get("evidence_strength") or 0)
            continue
        seen[key] = row
    return list(seen.values()), duplicates


def _companies_for_evidence(company_id: str | None) -> list[dict[str, Any]]:
    if company_id:
        company = storage.get_company(company_id) or {"id": company_id, "name": company_id}
        return [company]
    return []


def _strength_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        quality = row.get("source_quality_score") or 0
        band = "high" if quality >= 0.75 else "medium" if quality >= 0.45 else "low"
        key = (band, row.get("importance") or "medium", "contradicted" if row.get("contradiction_count") else row.get("status") or "needs_review")
        groups.setdefault(key, []).append(row)
    return [
        {
            "evidence_quality": quality,
            "claim_importance": importance,
            "status": status,
            "claim_count": len(items),
            "contradiction_count": sum(_as_int(item.get("contradiction_count"), 0) for item in items),
        }
        for (quality, importance, status), items in sorted(groups.items())
    ]


def _source_provenance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for row in rows:
        for ref in row.get("source_refs") or []:
            key = _as_str(ref.get("source_id") or ref.get("source_title"), "missing-source")
            current = sources.setdefault(
                key,
                {
                    "source_id": ref.get("source_id"),
                    "source_title": ref.get("source_title") or "Missing source",
                    "source_type": ref.get("source_type") or "unknown",
                    "published_at": ref.get("published_at"),
                    "trace_count": 0,
                    "claims_supported": 0,
                    "claim_ids": [],
                    "average_confidence": 0.0,
                    "_confidence_total": 0.0,
                },
            )
            current["trace_count"] += 1
            current["_confidence_total"] += _as_float(ref.get("confidence"), 0.0) or 0.0
            if row.get("claim_id") not in current["claim_ids"]:
                current["claim_ids"].append(row.get("claim_id"))
                current["claims_supported"] += 1
    out = []
    for row in sources.values():
        trace_count = row["trace_count"] or 1
        row["average_confidence"] = round(row.pop("_confidence_total") / trace_count, 3)
        out.append(row)
    out.sort(key=lambda row: (row["claims_supported"], row["trace_count"]), reverse=True)
    return out


def evidence_matrix_page(company_id: str | None = None) -> dict[str, Any]:
    payload = _common_payload(
        "evidence_matrix",
        as_of=_today(),
    )
    lookup = _source_lookup()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for company in _companies_for_evidence(company_id):
        cid = _as_str(company.get("id") or company.get("company_id"))
        if not cid:
            continue
        try:
            matrix = evidence_matrix.build_company_evidence_matrix(cid)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                _issue(
                    "warning",
                    "evidence_matrix_company_load_failed",
                    f"Could not load evidence matrix for {cid}: {exc}",
                    path=cid,
                )
            )
            continue
        company_name = _as_str(matrix.get("company_name") or company.get("name"), cid)
        for index, claim_row in enumerate(_as_list(matrix.get("claims")), start=len(rows) + 1):
            if isinstance(claim_row, dict):
                rows.append(
                    _normalize_company_claim(
                        claim_row,
                        company_id=cid,
                        company_name=company_name,
                        index=index,
                    )
                )

    aggregate = stock_research.latest_aggregate()
    if aggregate and not company_id:
        for index, signal in enumerate(_as_list(aggregate.get("ranked_signals")), start=len(rows) + 1):
            if isinstance(signal, dict):
                rows.append(_normalize_signal_claim(signal, index=index, source_lookup=lookup))

    rows, duplicates = _dedupe_claims(rows)
    issues = [*errors]
    if not rows:
        issues.append(
            _issue(
                "warning",
                "evidence_matrix_empty",
                "No claim evidence rows exist yet. Upload company research, run Memo Studio tasks, or create Stock Research tracker outputs.",
            )
        )
    for row in rows:
        if row["source_count"] == 0:
            issues.append(
                _issue(
                    "error",
                    "evidence_claim_missing_source_trace",
                    "Claim has no source trace.",
                    artifact_id=row.get("claim_id"),
                )
            )
        elif row["primary_source_count"] == 0 and row["weak_source_count"] >= row["source_count"]:
            issues.append(
                _issue(
                    "warning",
                    "evidence_claim_weak_source_only",
                    "Claim is supported only by weak, note-based, or unknown sources.",
                    artifact_id=row.get("claim_id"),
                )
            )
        if row["contradiction_count"] > 0:
            issues.append(
                _issue(
                    "warning",
                    "evidence_claim_has_unresolved_contradiction",
                    "Claim has unresolved contradicting evidence.",
                    artifact_id=row.get("claim_id"),
                )
            )
        if row.get("recency_days") is not None and row["recency_days"] > 180:
            issues.append(
                _issue(
                    "info",
                    "evidence_claim_stale_source",
                    "Claim source trace is stale.",
                    artifact_id=row.get("claim_id"),
                )
            )
        if row.get("eligible_for_memo") and row.get("primary_source_count", 0) == 0:
            issues.append(
                _issue(
                    "error",
                    "evidence_memo_eligible_without_primary_source",
                    "Claim is memo-eligible without a primary source.",
                    artifact_id=row.get("claim_id"),
                )
            )
    if duplicates:
        issues.append(
            _issue(
                "info",
                "evidence_duplicate_claims",
                f"{len(duplicates)} duplicate claim row(s) were merged by company, type, and text.",
            )
        )
    rows.sort(
        key=lambda row: (
            0 if row["source_count"] == 0 else 1,
            0 if row["contradiction_count"] else 1,
            -(row.get("evidence_strength") or 0),
            row.get("claim") or "",
        )
    )
    refs = [ref for row in rows for ref in row.get("source_refs") or []]
    contradictions = [
        {
            "claim_id": row["claim_id"],
            "claim": row["claim"],
            "supporting_source": (row.get("source_refs") or [{}])[0],
            "contradicting_source": contradiction,
            "analyst_action": "Start research task or mark contradiction resolved.",
        }
        for row in rows
        for contradiction in row.get("contradictions") or []
    ]
    payload.update(
        {
            "status": _status_for(rows, issues),
            "summary": {
                "claim_count": len(rows),
                "company_count": len({row.get("company_id") for row in rows}),
                "unsupported_claim_count": sum(1 for row in rows if row["source_count"] == 0 or row["status"] == "unsupported"),
                "contradicted_claim_count": sum(1 for row in rows if row["contradiction_count"] > 0 or row["status"] == "contradicted"),
                "memo_eligible_claim_count": sum(1 for row in rows if row.get("eligible_for_memo")),
                "company_id": company_id,
            },
            "sections": {
                "evidence_strength_matrix": _strength_matrix(rows),
                "claim_table": rows,
                "source_provenance": _source_provenance(rows),
                "contradictions_lane": contradictions,
                "unsupported_filters": {
                    "no_source_trace": sum(1 for row in rows if row["source_count"] == 0),
                    "weak_source_only": sum(
                        1
                        for row in rows
                        if row["source_count"] > 0 and row["primary_source_count"] == 0 and row["weak_source_count"] >= row["source_count"]
                    ),
                    "stale_source_only": sum(1 for row in rows if row.get("recency_days") is not None and row["recency_days"] > 180),
                },
            },
            "source_health": _source_health_from_refs(
                refs,
                contradiction_count=sum(row["contradiction_count"] for row in rows),
                missing_trace_count=sum(1 for row in rows if row["source_count"] == 0),
            ),
            "doctor_issues": issues,
            "actions": [
                _placeholder_action("approve_claim_for_memo", "Approve claim for memo use", method="PATCH"),
                _placeholder_action("start_research_task", "Start research task"),
                _placeholder_action("link_claim_to_hypothesis", "Link claim to hypothesis"),
                _placeholder_action("add_analyst_note", "Add analyst note"),
            ],
        }
    )
    return payload


def _snapshot_generated_after_window_start(row: dict[str, Any]) -> bool:
    generated_at = _parse_dt(row.get("generated_at"))
    window_start = _parse_date(row.get("evaluation_window_start"))
    if generated_at is None or window_start is None:
        return False
    start_dt = datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc)
    return generated_at >= start_dt


def _contains_debug_row(value: Any, debug_ids: set[str]) -> bool:
    if isinstance(value, dict):
        if value.get("vintage_kind") == "debug_backfill":
            return True
        if value.get("hypothesis_id") in debug_ids:
            return True
        return any(_contains_debug_row(item, debug_ids) for item in value.values())
    if isinstance(value, list):
        return any(_contains_debug_row(item, debug_ids) for item in value)
    return False


def _calibration_rows(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summaries:
        return []
    rows = []
    latest = summaries[0]
    for item in _as_list(latest.get("hit_rate_by_confidence_bucket")):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "confidence_bucket": item.get("bucket") or "unknown",
                "hit_rate": item.get("hit_rate"),
                "average_relative_return": item.get("average_relative_return_pct"),
                "sample_size": item.get("count") or 0,
            }
        )
    return rows


def _issue_date_identity(issue: dict[str, Any]) -> str:
    for field in (
        "vintage_date",
        "as_of",
        "as_of_date",
        "period_id",
        "date",
        "evaluation_window_start",
        "evaluation_window_end",
    ):
        value = _as_str(issue.get(field))
        if value:
            return value
    match = re.search(r"\d{4}-\d{2}-\d{2}", _as_str(issue.get("message")))
    return match.group(0) if match else ""


def _doctor_issue_identity(issue: dict[str, Any]) -> tuple[str, str, str]:
    issue_type = _as_str(issue.get("type"))
    date_key = _issue_date_identity(issue)
    if issue_type == "missing_current_live_hypothesis_vintage":
        return (issue_type, date_key, "")
    artifact_key = _as_str(
        issue.get("artifact_id")
        or issue.get("path")
        or issue.get("source_ref")
        or issue.get("summary_id")
    )
    return (issue_type, date_key, artifact_key)


def _doctor_issue_richness(issue: dict[str, Any]) -> tuple[int, int, int]:
    metadata_score = 0
    for field, score in (
        ("artifact_id", 8),
        ("path", 8),
        ("source_ref", 4),
        ("summary_id", 4),
        ("source", 2),
    ):
        if issue.get(field):
            metadata_score += score
    return (metadata_score, len(issue), len(_as_str(issue.get("message"))))


def _dedupe_doctor_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for issue in issues:
        key = _doctor_issue_identity(issue)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = issue
            order.append(key)
            continue
        if _doctor_issue_richness(issue) > _doctor_issue_richness(existing):
            by_key[key] = issue
    return [by_key[key] for key in order]


def hypothesis_lab_page() -> dict[str, Any]:
    dashboard = hypothesis_store.hypothesis_dashboard_payload()
    rows = _as_list(dashboard.get("rows"))
    summaries = _as_list(dashboard.get("calibration"))
    issues: list[dict[str, Any]] = []
    current_live = [
        row
        for row in rows
        if row.get("vintage_kind") == "forward_live" and row.get("vintage_date") == _today()
    ]
    if not current_live:
        issues.append(
            _issue(
                "warning",
                "missing_current_live_hypothesis_vintage",
                "No current forward-live hypothesis vintage exists. Create one with POST /api/stock-research/hypotheses/create.",
                as_of=_today(),
                source="research_pages",
            )
        )
    for row in rows:
        if _snapshot_generated_after_window_start(row):
            issues.append(
                _issue(
                    "error",
                    "hypothesis_generated_after_window_start",
                    "Hypothesis was generated after its evaluation window started.",
                    artifact_id=row.get("artifact_id") or row.get("hypothesis_id"),
                    vintage_date=row.get("vintage_date"),
                    source="research_pages",
                )
            )
        end = _parse_date(row.get("evaluation_window_end"))
        if end and end < date.today() and not row.get("outcome"):
            issues.append(
                _issue(
                    "warning",
                    "hypothesis_outcome_missing_after_window_close",
                    "Hypothesis evaluation window is closed but no outcome exists.",
                    artifact_id=row.get("artifact_id") or row.get("hypothesis_id"),
                    vintage_date=row.get("vintage_date"),
                    source="research_pages",
                )
            )
    if rows and dashboard.get("summary", {}).get("training_eligible_count", 0) == 0:
            issues.append(
                _issue(
                    "info",
                    "hypothesis_lab_no_training_eligible_rows",
                    "No training-eligible evaluated forward-live outcomes exist yet.",
                    source="research_pages",
                )
            )
    debug_ids = {row.get("hypothesis_id") for row in rows if row.get("vintage_kind") == "debug_backfill"}
    for summary in summaries:
        if _contains_debug_row(summary, debug_ids):
            issues.append(
                _issue(
                    "error",
                    "training_summary_includes_debug_rows",
                    "Calibration summary includes debug backfill rows.",
                    artifact_id=summary.get("summary_id"),
                    source="research_pages",
                )
            )
    try:
        stock_doctor = stock_research.stock_research_doctor()
    except Exception:
        stock_doctor = {}
    for issue in _as_list(stock_doctor.get("issues")):
        if isinstance(issue, dict) and issue.get("type") in HYPOTHESIS_DOCTOR_TYPES:
            issue = {**issue, "source": issue.get("source") or "stock_research_doctor"}
            issues.append(issue)
    issues = _dedupe_doctor_issues(issues)

    timeline = []
    for vintage in _as_list(dashboard.get("vintages")):
        if not isinstance(vintage, dict):
            continue
        timeline.append(
            {
                "vintage_date": vintage.get("vintage_date"),
                "vintage_kind": vintage.get("vintage_kind"),
                "generated_count": vintage.get("hypothesis_count") or 0,
                "evaluated_count": vintage.get("outcome_count") or 0,
                "pending_count": vintage.get("pending_count") or 0,
                "training_eligible_count": vintage.get("training_eligible_count") or 0,
                "training_eligibility": (
                    "ineligible_debug_backfill"
                    if vintage.get("vintage_kind") == "debug_backfill"
                    else "eligible_after_evaluation"
                ),
                "kind_counts": vintage.get("kind_counts") or {},
            }
        )
    hypothesis_rows = []
    outcome_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else None
        end = _parse_date(row.get("evaluation_window_end"))
        status = "evaluated" if outcome else "closed_pending" if end and end < date.today() else "live_pending"
        training_eligible = bool(
            row.get("vintage_kind") == "forward_live"
            and outcome
            and outcome.get("eligible_for_training")
        )
        source_refs = [
            _normalize_trace(trace, source_lookup=({}, {}), artifact_id=row.get("hypothesis_id"))
            for trace in _as_list(row.get("source_refs"))
            if isinstance(trace, dict)
        ]
        hypothesis_rows.append(
            {
                "hypothesis_id": row.get("hypothesis_id"),
                "vintage_date": row.get("vintage_date"),
                "vintage_kind": row.get("vintage_kind"),
                "training_eligible": training_eligible,
                "ticker": row.get("ticker"),
                "claim": row.get("claim"),
                "direction": row.get("direction"),
                "confidence": row.get("confidence"),
                "source_quality_score": row.get("source_quality_score"),
                "primary_source_count": row.get("primary_source_count") or 0,
                "weak_source_count": row.get("weak_source_count") or 0,
                "generated_at": row.get("generated_at"),
                "evaluation_window_start": row.get("evaluation_window_start"),
                "evaluation_window_end": row.get("evaluation_window_end"),
                "status": status,
                "outcome": outcome,
                "source_refs": source_refs,
            }
        )
        if outcome:
            outcome_rows.append(
                {
                    "hypothesis_id": row.get("hypothesis_id"),
                    "ticker": outcome.get("ticker") or row.get("ticker"),
                    "absolute_return_pct": outcome.get("absolute_return_pct"),
                    "benchmark_return_pct": outcome.get("benchmark_return_pct"),
                    "relative_return_pct": outcome.get("relative_return_pct"),
                    "max_drawdown_pct": outcome.get("max_drawdown_pct"),
                    "realized_volatility_pct": outcome.get("realized_volatility_pct"),
                    "directional_result": outcome.get("directional_result"),
                    "confidence_bucket": outcome.get("confidence_bucket"),
                    "eligible_for_training": training_eligible,
                    "market_data_source": outcome.get("market_data_source"),
                }
            )
    refs = [
        ref for row in hypothesis_rows for ref in row.get("source_refs") or []
    ]
    payload = _common_payload("hypothesis_lab", as_of=_today())
    payload.update(
        {
            "status": _status_for(hypothesis_rows, issues),
            "summary": {
                **(dashboard.get("summary") if isinstance(dashboard.get("summary"), dict) else {}),
                "live_hypothesis_count": sum(1 for row in hypothesis_rows if row["vintage_kind"] == "forward_live"),
                "debug_hypothesis_count": sum(1 for row in hypothesis_rows if row["vintage_kind"] == "debug_backfill"),
                "evaluated_count": len(outcome_rows),
            },
            "sections": {
                "vintage_timeline": timeline,
                "hypotheses": hypothesis_rows,
                "outcomes": outcome_rows,
                "calibration": _calibration_rows(summaries),
                "calibration_summaries": summaries,
                "leakage_doctor": issues,
            },
            "source_health": _source_health_from_refs(
                refs,
                missing_trace_count=sum(1 for row in hypothesis_rows if not row.get("source_refs")),
            ),
            "doctor_issues": issues,
            "actions": [
                {
                    "id": "create_live_vintage",
                    "label": "Create current live vintage",
                    "method": "POST",
                    "endpoint": "/api/stock-research/hypotheses/create",
                },
                {
                    "id": "run_debug_backfill",
                    "label": "Run debug backfill",
                    "method": "POST",
                    "endpoint": "/api/stock-research/hypotheses/create",
                },
                {
                    "id": "evaluate_vintage",
                    "label": "Evaluate closed vintage",
                    "method": "POST",
                    "endpoint": "/api/stock-research/hypotheses/{vintage_date}/evaluate",
                },
                {
                    "id": "calibrate",
                    "label": "Generate calibration summary",
                    "method": "POST",
                    "endpoint": "/api/stock-research/hypotheses/calibrate",
                },
            ],
        }
    )
    return payload
