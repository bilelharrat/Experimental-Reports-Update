"""Forward hypothesis cycle commands for Stock Research."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from . import hypothesis_store, stock_research


def current_date() -> date:
    return date.today()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generated_at_for_current_date() -> str:
    now = datetime.now(timezone.utc)
    today = current_date()
    if now.date() == today:
        return now.isoformat()
    return now.replace(year=today.year, month=today.month, day=today.day).isoformat()


def _as_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value).strip() or default


def _safe_direction(value: Any) -> str:
    text = _as_str(value).lower()
    return text if text in {"bullish", "bearish", "neutral", "watch"} else "watch"


def _tracker_by_id() -> dict[str, dict[str, Any]]:
    return {
        tracker["id"]: tracker for tracker in stock_research.list_trackers(include_archived=True)
    }


def _signal_rows_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    signals = manifest.get("aggregate_signals")
    if isinstance(signals, list) and signals:
        return [row for row in signals if isinstance(row, dict)]
    rows = []
    for run in manifest.get("tracker_runs") or []:
        if not isinstance(run, dict) or not run.get("thesis"):
            continue
        rows.append(
            {
                "id": run.get("run_id"),
                "source_tracker_id": run.get("tracker_id"),
                "tracker_run_id": run.get("run_id"),
                "direction": "watch",
                "confidence": run.get("confidence"),
                "observation": run.get("thesis"),
                "source_refs": [],
                "source_quality_score": None,
                "source_quality_reason": "Tracker thesis fallback.",
                "primary_source_count": 0,
                "weak_source_count": 0,
            }
        )
    return rows


def _ticker_for_signal(signal: dict[str, Any], tracker: dict[str, Any] | None) -> str:
    ticker = _as_str(signal.get("ticker") or signal.get("company_ticker"))
    if ticker:
        return ticker.upper()
    tickers = (tracker or {}).get("tickers") or []
    return _as_str(tickers[0] if tickers else "").upper()


def _source_quality(signal: dict[str, Any]) -> tuple[float | None, str, int, int]:
    score = _as_float(signal.get("source_quality_score"), None)
    reason = _as_str(signal.get("source_quality_reason"))
    primary = int(_as_float(signal.get("primary_source_count"), 0) or 0)
    weak = int(_as_float(signal.get("weak_source_count"), 0) or 0)
    refs = signal.get("source_refs") or signal.get("source_traces") or []
    if score is None and refs:
        score = 0.6
        reason = reason or "Source traces present."
    elif score is None:
        score = 0.25
        reason = reason or "No source trace attached."
    return score, reason, primary, weak


def create_hypotheses(
    *,
    vintage_date: str,
    vintage_kind: str = "forward_live",
    allow_debug_backfill: bool = False,
    horizon_days: int = 7,
    created_by: str = "stock_research_hypothesis_cycle",
) -> dict[str, Any]:
    parsed_vintage = date.fromisoformat(vintage_date)
    if vintage_kind not in {"forward_live", "debug_backfill"}:
        raise ValueError("vintage_kind must be forward_live or debug_backfill")
    actual_kind = vintage_kind
    if vintage_kind == "forward_live" and parsed_vintage < current_date():
        if not allow_debug_backfill:
            raise ValueError("forward_live hypotheses cannot be created for a past vintage date")
        actual_kind = "debug_backfill"
    if actual_kind == "debug_backfill":
        if parsed_vintage > current_date():
            raise ValueError("debug_backfill hypotheses cannot be created for a future vintage date")
        allow_debug_backfill = True

    started = time.monotonic()
    generated_at = _generated_at_for_current_date()
    window_start, window_end = hypothesis_store.evaluation_window(
        vintage_date,
        horizon_days=horizon_days,
    )
    cutoff = f"{vintage_date}T23:59:59+00:00"
    manifest_payload = hypothesis_store.build_point_in_time_manifest(cutoff)
    manifest = manifest_payload["manifest"]
    manifest_sha = manifest_payload["input_manifest_sha256"]
    trackers = _tracker_by_id()
    rows = []
    for signal in _signal_rows_from_manifest(manifest):
        tracker_id = _as_str(signal.get("source_tracker_id") or signal.get("tracker_id"))
        tracker = trackers.get(tracker_id)
        claim = _as_str(
            signal.get("observation") or signal.get("claim") or signal.get("thesis"),
            "No claim.",
        )
        ticker = _ticker_for_signal(signal, tracker)
        source_quality_score, source_quality_reason, primary_count, weak_count = _source_quality(
            signal
        )
        hypothesis_id = hypothesis_store.hypothesis_id_for(
            vintage_date=vintage_date,
            vintage_kind=actual_kind,
            tracker_id=tracker_id,
            ticker=ticker,
            claim=claim,
            input_manifest_sha256=manifest_sha,
        )
        rows.append(
            hypothesis_store.write_hypothesis_snapshot(
                {
                    "hypothesis_id": hypothesis_id,
                    "vintage_kind": actual_kind,
                    "eligible_for_training": False,
                    "generated_at": generated_at,
                    "vintage_date": vintage_date,
                    "eligible_source_cutoff": cutoff,
                    "evaluation_window_start": window_start,
                    "evaluation_window_end": window_end,
                    "tracker_id": tracker_id,
                    "tracker_type": (tracker or {}).get("type") or signal.get("tracker_type") or "",
                    "company_id": (tracker or {}).get("company_id"),
                    "ticker": ticker,
                    "claim": claim,
                    "direction": _safe_direction(signal.get("direction")),
                    "expected_horizon_days": max(1, int(horizon_days)),
                    "confidence": _as_float(signal.get("confidence"), None),
                    "source_refs": signal.get("source_refs") or signal.get("source_traces") or [],
                    "source_quality_score": source_quality_score,
                    "source_quality_reason": source_quality_reason,
                    "primary_source_count": primary_count,
                    "weak_source_count": weak_count,
                    "prompt_version": "deterministic-aggregate-signal-v1",
                    "model_id": "deterministic",
                    "generation_mode": (
                        "deterministic_fixture" if actual_kind == "debug_backfill" else "manual"
                    ),
                    "input_manifest": manifest,
                    "input_manifest_sha256": manifest_sha,
                    "created_by": created_by,
                    "notes": "Created from point-in-time aggregate ranked signals.",
                }
            )
        )

    stock_research._upsert_run_ledger_entry(
        {
            "ledger_id": f"stock_hypothesis:{actual_kind}:{vintage_date}",
            "job_kind": "stock_hypothesis",
            "run_id": vintage_date,
            "period_id": vintage_date,
            "artifact_id": f"hypothesis_vintage:{vintage_date}",
            "status": "done",
            "created_at": generated_at,
            "updated_at": _now(),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "source_count": len(manifest.get("sources") or []),
        }
    )
    return {
        "vintage_date": vintage_date,
        "vintage_kind": actual_kind,
        "created_count": len(rows),
        "hypotheses": rows,
        "input_manifest_sha256": manifest_sha,
        "warnings": manifest_payload.get("warnings") or [],
    }


class FixtureMarketDataAdapter:
    """In-memory market data adapter used by tests and mocked API calls."""

    def __init__(
        self,
        prices: Mapping[str, Mapping[str, float]] | None = None,
        *,
        source_name: str = "fixture",
    ) -> None:
        self.prices = {
            str(ticker).upper(): {str(day): float(price) for day, price in (series or {}).items()}
            for ticker, series in (prices or {}).items()
        }
        self.source_name = source_name

    def get_price(self, ticker: str, day: str) -> float | None:
        return self.prices.get(str(ticker).upper(), {}).get(day)

    def get_return(self, ticker: str, start_date: str, end_date: str) -> float | None:
        start = self.get_price(ticker, start_date)
        end = self.get_price(ticker, end_date)
        if start is None or end is None or start == 0:
            return None
        return round(((end / start) - 1) * 100, 6)

    def price_points(self, ticker: str, start_date: str, end_date: str) -> list[float]:
        current = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        out = []
        while current <= end:
            price = self.get_price(ticker, current.isoformat())
            if price is not None:
                out.append(price)
            current += timedelta(days=1)
        return out

    def snapshot_hash(self) -> str:
        return hypothesis_store.market_data_snapshot_hash(self.prices)


def _max_drawdown_pct(points: list[float]) -> float | None:
    if len(points) < 2:
        return None
    peak = points[0]
    max_drawdown = 0.0
    for price in points:
        peak = max(peak, price)
        if peak:
            max_drawdown = min(max_drawdown, (price / peak - 1) * 100)
    return round(max_drawdown, 6)


def _volatility_pct(points: list[float]) -> float | None:
    if len(points) < 3:
        return None
    returns = []
    for previous, current in zip(points, points[1:]):
        if previous:
            returns.append((current / previous - 1) * 100)
    if len(returns) < 2:
        return None
    return round(statistics.pstdev(returns), 6)


def _directional_result(direction: str, relative_return: float | None) -> str:
    if relative_return is None:
        return "unresolved"
    if direction == "bullish":
        return "hit" if relative_return > 0 else "miss"
    if direction == "bearish":
        return "hit" if relative_return < 0 else "miss"
    if direction in {"neutral", "watch"}:
        return "neutral" if abs(relative_return) <= 1 else "unresolved"
    return "unresolved"


def evaluate_hypothesis(
    hypothesis: dict[str, Any],
    adapter: FixtureMarketDataAdapter,
    *,
    benchmark_ticker: str = "SPY",
    eligible_for_training: bool | None = None,
) -> dict[str, Any]:
    ticker = _as_str(hypothesis.get("ticker")).upper()
    start = hypothesis["evaluation_window_start"]
    end = hypothesis["evaluation_window_end"]
    start_price = adapter.get_price(ticker, start) if ticker else None
    end_price = adapter.get_price(ticker, end) if ticker else None
    absolute_return = adapter.get_return(ticker, start, end) if ticker else None
    benchmark_return = adapter.get_return(benchmark_ticker, start, end)
    relative_return = (
        round(absolute_return - benchmark_return, 6)
        if absolute_return is not None and benchmark_return is not None
        else None
    )
    result = _directional_result(
        _as_str(hypothesis.get("direction"), "watch"),
        relative_return,
    )
    requested_training = (
        result != "unresolved" if eligible_for_training is None else bool(eligible_for_training)
    )
    if hypothesis.get("vintage_kind") != "forward_live":
        requested_training = False
    if result == "unresolved":
        requested_training = False
    points = adapter.price_points(ticker, start, end) if ticker else []
    return hypothesis_store.write_hypothesis_outcome(
        {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "evaluated_at": _now(),
            "evaluation_window_start": start,
            "evaluation_window_end": end,
            "ticker": ticker,
            "benchmark_ticker": benchmark_ticker,
            "start_price": start_price,
            "end_price": end_price,
            "absolute_return_pct": absolute_return,
            "benchmark_return_pct": benchmark_return,
            "relative_return_pct": relative_return,
            "max_drawdown_pct": _max_drawdown_pct(points),
            "realized_volatility_pct": _volatility_pct(points),
            "directional_result": result,
            "confidence_bucket": hypothesis_store.confidence_bucket(
                _as_float(hypothesis.get("confidence"), None)
            ),
            "calibration_bucket": f"{hypothesis.get('direction')}:{result}",
            "outcome_notes": (
                "Missing ticker or price data."
                if result == "unresolved"
                else "Fixture market data evaluation."
            ),
            "market_data_source": adapter.source_name,
            "market_data_snapshot_sha256": adapter.snapshot_hash(),
            "eligible_for_training": requested_training,
        }
    )


def evaluate_vintage(
    vintage_date: str,
    *,
    adapter: FixtureMarketDataAdapter | None = None,
    benchmark_ticker: str = "SPY",
) -> dict[str, Any]:
    adapter = adapter or FixtureMarketDataAdapter()
    vintage = hypothesis_store.get_vintage(vintage_date)
    outcomes = []
    for hypothesis in vintage["hypotheses"]:
        outcomes.append(
            evaluate_hypothesis(
                hypothesis,
                adapter,
                benchmark_ticker=benchmark_ticker,
            )
        )
    return {
        "vintage_date": vintage_date,
        "evaluated_count": len(outcomes),
        "outcomes": outcomes,
    }


def _rate(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return round(
        len([row for row in rows if row.get("directional_result") == "hit"]) / len(rows),
        6,
    )


def _group_metric(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_as_str(row.get(field), "unknown"), []).append(row)
    return [
        {"bucket": key, "count": len(items), "hit_rate": _rate(items)}
        for key, items in sorted(groups.items())
    ]


def calibrate() -> dict[str, Any]:
    snapshots = {
        row["hypothesis_id"]: row
        for row in hypothesis_store.list_hypotheses(vintage_kind="forward_live")
    }
    completed = []
    for outcome in hypothesis_store.list_outcomes():
        snapshot = snapshots.get(outcome.get("hypothesis_id"))
        if not snapshot:
            continue
        if not outcome.get("eligible_for_training"):
            continue
        if outcome.get("directional_result") == "unresolved":
            continue
        completed.append({**snapshot, **outcome, "snapshot": snapshot})

    by_direction: dict[str, list[float]] = {}
    for row in completed:
        rel = _as_float(row.get("relative_return_pct"), None)
        if rel is not None:
            by_direction.setdefault(_as_str(row.get("direction"), "watch"), []).append(rel)

    high_conf_wrong = [
        {
            "hypothesis_id": row.get("hypothesis_id"),
            "ticker": row.get("ticker"),
            "claim": row.get("snapshot", {}).get("claim"),
            "relative_return_pct": row.get("relative_return_pct"),
        }
        for row in completed
        if row.get("confidence_bucket") == "high" and row.get("directional_result") == "miss"
    ][:10]
    weak_source_false_positives = [
        {
            "hypothesis_id": row.get("hypothesis_id"),
            "ticker": row.get("ticker"),
            "claim": row.get("snapshot", {}).get("claim"),
            "weak_source_count": row.get("snapshot", {}).get("weak_source_count"),
        }
        for row in completed
        if (row.get("snapshot", {}).get("weak_source_count") or 0) > 0
        and row.get("directional_result") == "miss"
    ][:10]
    summary = {
        "schema_version": hypothesis_store.TRAINING_SUMMARY_SCHEMA_VERSION,
        "created_at": _now(),
        "eligible_outcome_count": len(completed),
        "hit_rate_by_confidence_bucket": _group_metric(completed, "confidence_bucket"),
        "hit_rate_by_source_category": [
            {
                "bucket": "primary",
                "count": len(
                    [
                        row
                        for row in completed
                        if (row.get("snapshot", {}).get("primary_source_count") or 0) > 0
                    ]
                ),
                "hit_rate": _rate(
                    [
                        row
                        for row in completed
                        if (row.get("snapshot", {}).get("primary_source_count") or 0) > 0
                    ]
                ),
            },
            {
                "bucket": "weak",
                "count": len(
                    [
                        row
                        for row in completed
                        if (row.get("snapshot", {}).get("weak_source_count") or 0) > 0
                    ]
                ),
                "hit_rate": _rate(
                    [
                        row
                        for row in completed
                        if (row.get("snapshot", {}).get("weak_source_count") or 0) > 0
                    ]
                ),
            },
        ],
        "hit_rate_by_tracker_type": _group_metric(completed, "tracker_type"),
        "average_relative_return_by_direction": [
            {
                "direction": direction,
                "count": len(values),
                "average_relative_return_pct": round(sum(values) / len(values), 6),
            }
            for direction, values in sorted(by_direction.items())
            if values
        ],
        "high_confidence_wrong_examples": high_conf_wrong,
        "weak_source_false_positives": weak_source_false_positives,
    }
    return hypothesis_store.write_training_summary(summary)


def _parse_prices(path: str | None) -> dict[str, dict[str, float]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Price fixture must be a JSON object")
    return data


def debug_backfill(vintage_date: str, *, horizon_days: int = 7) -> dict[str, Any]:
    return create_hypotheses(
        vintage_date=vintage_date,
        vintage_kind="debug_backfill",
        allow_debug_backfill=True,
        horizon_days=horizon_days,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m server.hypothesis_cycle",
        description="Run Stock Research forward-hypothesis cycle commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Create a forward-live weekly vintage.")
    create.add_argument("--vintage-date", required=True)
    create.add_argument("--horizon-days", type=int, default=7)
    create.add_argument("--allow-debug-backfill", action="store_true")

    debug = sub.add_parser("debug-backfill", help="Create a debug-only vintage.")
    debug.add_argument("--vintage-date", required=True)
    debug.add_argument("--horizon-days", type=int, default=7)

    evaluate = sub.add_parser("evaluate", help="Evaluate a hypothesis vintage.")
    evaluate.add_argument("--vintage-date", required=True)
    evaluate.add_argument("--prices-json")
    evaluate.add_argument("--benchmark-ticker", default="SPY")

    sub.add_parser("calibrate", help="Write a training-eligible calibration summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            payload = create_hypotheses(
                vintage_date=args.vintage_date,
                allow_debug_backfill=args.allow_debug_backfill,
                horizon_days=args.horizon_days,
            )
        elif args.command == "debug-backfill":
            payload = debug_backfill(
                args.vintage_date,
                horizon_days=args.horizon_days,
            )
        elif args.command == "evaluate":
            payload = evaluate_vintage(
                args.vintage_date,
                adapter=FixtureMarketDataAdapter(_parse_prices(args.prices_json)),
                benchmark_ticker=args.benchmark_ticker,
            )
        elif args.command == "calibrate":
            payload = calibrate()
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
