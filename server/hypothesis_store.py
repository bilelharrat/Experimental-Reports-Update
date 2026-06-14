"""Durable forward-hypothesis store for Stock Research.

Hypotheses are point-in-time artifacts. A snapshot can be written once and
re-read many times, but changing a frozen hypothesis id is rejected so debug
backfills cannot silently overwrite the live evidence trail.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import stock_research

HYPOTHESIS_SCHEMA_VERSION = 1
OUTCOME_SCHEMA_VERSION = 1
TRAINING_SUMMARY_SCHEMA_VERSION = 1

VintageKind = Literal["forward_live", "debug_backfill"]
Direction = Literal["bullish", "bearish", "neutral", "watch"]
GenerationMode = Literal["live_model", "deterministic_fixture", "manual"]
DirectionalResult = Literal["hit", "miss", "neutral", "unresolved"]

_DIRECTIONS = {"bullish", "bearish", "neutral", "watch"}
_VINTAGE_KINDS = {"forward_live", "debug_backfill"}
_GENERATION_MODES = {"live_model", "deterministic_fixture", "manual"}


class HypothesisSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = HYPOTHESIS_SCHEMA_VERSION
    hypothesis_id: str
    vintage_kind: VintageKind = "forward_live"
    eligible_for_training: bool = False
    generated_at: str
    vintage_date: str
    eligible_source_cutoff: str
    evaluation_window_start: str
    evaluation_window_end: str
    tracker_id: str = ""
    tracker_type: str = ""
    company_id: str | None = None
    ticker: str = ""
    claim: str
    direction: Direction = "watch"
    expected_horizon_days: int = 7
    confidence: float | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_quality_score: float | None = None
    source_quality_reason: str = ""
    primary_source_count: int = 0
    weak_source_count: int = 0
    prompt_version: str = "deterministic-v1"
    model_id: str = "deterministic"
    generation_mode: GenerationMode = "deterministic_fixture"
    input_manifest: dict[str, Any] = Field(default_factory=dict)
    input_manifest_sha256: str = ""
    artifact_id: str = ""
    version_id: str = ""
    frozen: bool = True
    created_by: str = "stock_research_hypothesis_cycle"
    notes: str = ""

    @field_validator("vintage_date", "evaluation_window_start", "evaluation_window_end")
    @classmethod
    def _valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def _training_rules(self) -> "HypothesisSnapshot":
        if self.schema_version != HYPOTHESIS_SCHEMA_VERSION:
            raise ValueError("Unsupported hypothesis schema_version")
        if self.vintage_kind == "debug_backfill" and self.eligible_for_training:
            raise ValueError("debug_backfill hypotheses are never training-eligible")
        if not self.frozen:
            raise ValueError("hypothesis snapshots must be frozen")
        if self.expected_horizon_days < 1:
            raise ValueError("expected_horizon_days must be positive")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return self


class HypothesisOutcome(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = OUTCOME_SCHEMA_VERSION
    hypothesis_id: str
    evaluated_at: str
    evaluation_window_start: str
    evaluation_window_end: str
    ticker: str = ""
    benchmark_ticker: str = "SPY"
    start_price: float | None = None
    end_price: float | None = None
    absolute_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    relative_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    realized_volatility_pct: float | None = None
    directional_result: DirectionalResult = "unresolved"
    confidence_bucket: str = "unknown"
    calibration_bucket: str = "unresolved"
    outcome_notes: str = ""
    market_data_source: str = "fixture"
    market_data_snapshot_sha256: str = ""
    eligible_for_training: bool = False

    @field_validator("evaluation_window_start", "evaluation_window_end")
    @classmethod
    def _valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def _schema_rules(self) -> "HypothesisOutcome":
        if self.schema_version != OUTCOME_SCHEMA_VERSION:
            raise ValueError("Unsupported outcome schema_version")
        return self


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    return str(value)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return copy.deepcopy(default)
    return data if data is not None else copy.deepcopy(default)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)
        f.write("\n")
    tmp.replace(path)


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


def _safe_component(value: str, *, label: str = "id") -> str:
    return stock_research._safe_component(value, label=label)


def hypothesis_root() -> Path:
    return stock_research.STOCK_RESEARCH_ROOT / "hypotheses"


def vintage_dir(vintage_date: str) -> Path:
    date.fromisoformat(vintage_date)
    return hypothesis_root() / _safe_component(vintage_date, label="vintage date")


def hypotheses_path(vintage_date: str) -> Path:
    return vintage_dir(vintage_date) / "hypotheses.json"


def outcomes_path(vintage_date: str) -> Path:
    return vintage_dir(vintage_date) / "outcomes.json"


def training_summaries_root() -> Path:
    return hypothesis_root() / "training_summaries"


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_input_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = _canonical(manifest if isinstance(manifest, dict) else {})
    return {"manifest": frozen, "sha256": _stable_hash(frozen)}


def _snapshot_from_row(row: dict[str, Any]) -> dict[str, Any]:
    data = {**row}
    data["schema_version"] = HYPOTHESIS_SCHEMA_VERSION
    data["vintage_kind"] = (
        data.get("vintage_kind") if data.get("vintage_kind") in _VINTAGE_KINDS else "forward_live"
    )
    data["direction"] = data.get("direction") if data.get("direction") in _DIRECTIONS else "watch"
    data["generation_mode"] = (
        data.get("generation_mode")
        if data.get("generation_mode") in _GENERATION_MODES
        else "deterministic_fixture"
    )
    data["generated_at"] = _as_str(data.get("generated_at"), _now())
    data["eligible_source_cutoff"] = _as_str(
        data.get("eligible_source_cutoff"),
        data["generated_at"],
    )
    data["frozen"] = True
    data["eligible_for_training"] = bool(data.get("eligible_for_training", False))
    frozen = freeze_input_manifest(data.get("input_manifest") or {})
    data["input_manifest"] = frozen["manifest"]
    data["input_manifest_sha256"] = _as_str(
        data.get("input_manifest_sha256"),
        frozen["sha256"],
    )
    if data["input_manifest_sha256"] != frozen["sha256"]:
        raise ValueError("input_manifest_sha256 does not match input_manifest")
    if not data.get("artifact_id"):
        data["artifact_id"] = f"hypothesis:{data.get('vintage_date')}:{data.get('hypothesis_id')}"
    if not data.get("version_id"):
        data["version_id"] = f"{data['artifact_id']}:v1:{data['input_manifest_sha256'][:12]}"
    return HypothesisSnapshot(**data).model_dump(mode="json")


def _outcome_from_row(row: dict[str, Any]) -> dict[str, Any]:
    data = {**row}
    data["schema_version"] = OUTCOME_SCHEMA_VERSION
    data["evaluated_at"] = _as_str(data.get("evaluated_at"), _now())
    return HypothesisOutcome(**data).model_dump(mode="json")


def _read_hypothesis_file(vintage_date: str) -> list[dict[str, Any]]:
    data = _read_json(hypotheses_path(vintage_date), {"hypotheses": []})
    rows = data.get("hypotheses") if isinstance(data, dict) else []
    return [_snapshot_from_row(row) for row in rows if isinstance(row, dict)]


def _read_outcome_file(vintage_date: str) -> list[dict[str, Any]]:
    data = _read_json(outcomes_path(vintage_date), {"outcomes": []})
    rows = data.get("outcomes") if isinstance(data, dict) else []
    return [_outcome_from_row(row) for row in rows if isinstance(row, dict)]


def list_vintage_dates() -> list[str]:
    if not hypothesis_root().exists():
        return []
    dates = [
        path.name
        for path in hypothesis_root().iterdir()
        if path.is_dir() and path.name != "training_summaries"
    ]
    return sorted(dates, reverse=True)


def list_hypotheses(vintage_kind: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for vintage_date in list_vintage_dates():
        rows.extend(_read_hypothesis_file(vintage_date))
    if vintage_kind:
        rows = [row for row in rows if row.get("vintage_kind") == vintage_kind]
    rows.sort(
        key=lambda row: (str(row.get("vintage_date", "")), str(row.get("generated_at", ""))),
        reverse=True,
    )
    return rows


def list_outcomes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for vintage_date in list_vintage_dates():
        rows.extend(_read_outcome_file(vintage_date))
    rows.sort(
        key=lambda row: (
            str(row.get("evaluation_window_end", "")),
            str(row.get("evaluated_at", "")),
        ),
        reverse=True,
    )
    return rows


def get_hypothesis(hypothesis_id: str) -> dict[str, Any] | None:
    for row in list_hypotheses():
        if row.get("hypothesis_id") == hypothesis_id:
            return row
    return None


def get_vintage(vintage_date: str) -> dict[str, Any]:
    hypotheses = _read_hypothesis_file(vintage_date)
    outcomes = _read_outcome_file(vintage_date)
    outcomes_by_id = {row.get("hypothesis_id"): row for row in outcomes}
    return {
        "schema_version": HYPOTHESIS_SCHEMA_VERSION,
        "vintage_date": vintage_date,
        "hypotheses": hypotheses,
        "outcomes": outcomes,
        "rows": [
            {**row, "outcome": outcomes_by_id.get(row.get("hypothesis_id"))} for row in hypotheses
        ],
    }


def _same_artifact(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _stable_hash(left) == _stable_hash(right)


def write_hypothesis_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    candidate = _snapshot_from_row(row)
    vintage_date = candidate["vintage_date"]
    with stock_research._LOCK:
        all_existing = list_hypotheses()
        for existing in all_existing:
            if existing.get("hypothesis_id") != candidate["hypothesis_id"]:
                continue
            if _same_artifact(existing, candidate):
                return existing
            raise ValueError(f"Frozen hypothesis already exists: {candidate['hypothesis_id']}")
        rows = _read_hypothesis_file(vintage_date)
        rows.append(candidate)
        rows.sort(key=lambda item: str(item.get("hypothesis_id", "")))
        _write_json(
            hypotheses_path(vintage_date),
            {
                "schema_version": HYPOTHESIS_SCHEMA_VERSION,
                "vintage_date": vintage_date,
                "hypotheses": rows,
            },
        )
    return candidate


def _snapshot_allows_training(snapshot: dict[str, Any], outcome: dict[str, Any]) -> bool:
    if snapshot.get("vintage_kind") != "forward_live":
        return False
    if outcome.get("directional_result") == "unresolved":
        return False
    generated_at = datetime.fromisoformat(str(snapshot.get("generated_at")).replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    window_start = datetime.combine(
        date.fromisoformat(snapshot["evaluation_window_start"]),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return generated_at < window_start


def write_hypothesis_outcome(row: dict[str, Any]) -> dict[str, Any]:
    candidate = _outcome_from_row(row)
    snapshot = get_hypothesis(candidate["hypothesis_id"])
    if snapshot is None:
        raise ValueError(f"Unknown hypothesis_id: {candidate['hypothesis_id']}")
    if candidate.get("eligible_for_training") and not _snapshot_allows_training(
        snapshot,
        candidate,
    ):
        raise ValueError("Outcome is not eligible for training")
    if snapshot.get("vintage_kind") == "debug_backfill":
        candidate["eligible_for_training"] = False
    vintage_date = snapshot["vintage_date"]
    with stock_research._LOCK:
        rows = _read_outcome_file(vintage_date)
        for existing in rows:
            if existing.get("hypothesis_id") != candidate["hypothesis_id"]:
                continue
            if _same_artifact(existing, candidate):
                return existing
            raise ValueError(
                f"Frozen hypothesis outcome already exists: {candidate['hypothesis_id']}"
            )
        rows.append(candidate)
        rows.sort(key=lambda item: str(item.get("hypothesis_id", "")))
        _write_json(
            outcomes_path(vintage_date),
            {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "vintage_date": vintage_date,
                "outcomes": rows,
            },
        )
    return candidate


def _parse_timestamp(value: Any) -> datetime | None:
    text = _as_str(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.combine(
                date.fromisoformat(text),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None


def _included_before_cutoff(
    item: dict[str, Any],
    cutoff: datetime,
    *,
    label: str,
    warnings: list[dict[str, str]],
) -> bool:
    timestamp = (
        item.get("created_at")
        or item.get("generated_at")
        or item.get("updated_at")
        or item.get("checked_at")
        or item.get("timestamp")
    )
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        warnings.append(
            {
                "type": "missing_timestamp",
                "label": label,
                "id": _as_str(item.get("id") or item.get("run_id") or item.get("artifact_id")),
            }
        )
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= cutoff


def build_point_in_time_manifest(eligible_source_cutoff: str) -> dict[str, Any]:
    cutoff = _parse_timestamp(eligible_source_cutoff)
    if cutoff is None:
        raise ValueError("eligible_source_cutoff must be an ISO timestamp")
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    warnings: list[dict[str, str]] = []
    trackers = []
    tracker_runs = []
    sources = []
    aggregate_signals = []
    work_products = []

    for tracker in stock_research.list_trackers(include_archived=True):
        trackers.append(
            {
                "id": tracker.get("id"),
                "type": tracker.get("type"),
                "status": tracker.get("status"),
                "tickers": tracker.get("tickers") or [],
                "latest_run_id": tracker.get("latest_run_id"),
            }
        )
        for source in stock_research.list_tracker_sources(tracker["id"]):
            source_row = {
                "id": source.get("id"),
                "tracker_id": tracker["id"],
                "title": source.get("title"),
                "source_type": source.get("source_type"),
                "priority": source.get("priority"),
                "relevance": source.get("relevance"),
                "created_at": source.get("created_at"),
                "path": source.get("path") or source.get("stored_name"),
                "url": source.get("url"),
            }
            if _included_before_cutoff(
                source_row,
                cutoff,
                label=f"source:{tracker['id']}",
                warnings=warnings,
            ):
                sources.append(source_row)
        for run in stock_research.list_tracker_runs(tracker["id"]):
            run_row = {
                "tracker_id": tracker["id"],
                "tracker_type": tracker.get("type"),
                "run_id": run.get("run_id"),
                "period_id": run.get("period_id"),
                "created_at": run.get("created_at"),
                "generated_at": run.get("generated_at"),
                "updated_at": run.get("updated_at"),
                "status": run.get("status"),
                "artifact_id": f"tracker_run:{tracker['id']}:{run.get('run_id')}",
                "source_trace_count": len(run.get("source_traces") or []),
                "confidence": run.get("confidence"),
                "thesis": run.get("thesis"),
            }
            if _included_before_cutoff(
                run_row,
                cutoff,
                label=f"tracker_run:{tracker['id']}",
                warnings=warnings,
            ):
                tracker_runs.append(run_row)

    if stock_research.aggregates_root().exists():
        for path in stock_research.aggregates_root().glob("*/weekly_report.json"):
            aggregate = _read_json(path, {})
            if not isinstance(aggregate, dict):
                continue
            if not _included_before_cutoff(
                aggregate,
                cutoff,
                label="weekly_aggregate",
                warnings=warnings,
            ):
                continue
            for signal in aggregate.get("ranked_signals") or []:
                if isinstance(signal, dict):
                    aggregate_signals.append(
                        {
                            "period_id": aggregate.get("period_id"),
                            "generated_at": aggregate.get("generated_at"),
                            "id": signal.get("id"),
                            "source_tracker_id": signal.get("source_tracker_id"),
                            "tracker_run_id": signal.get("tracker_run_id"),
                            "ticker": signal.get("ticker"),
                            "direction": signal.get("direction"),
                            "confidence": signal.get("confidence"),
                            "observation": signal.get("observation")
                            or signal.get("claim")
                            or signal.get("thesis"),
                            "source_refs": signal.get("source_traces") or [],
                            "source_quality_score": signal.get("source_quality_score"),
                            "source_quality_reason": signal.get("source_quality_reason"),
                            "primary_source_count": signal.get("primary_source_count"),
                            "weak_source_count": signal.get("weak_source_count"),
                        }
                    )

    for product in stock_research.list_work_products(include_archived=True):
        product_row = {
            "artifact_id": product.get("artifact_id"),
            "artifact_type": product.get("artifact_type"),
            "version_id": product.get("version_id"),
            "version": product.get("version"),
            "updated_at": product.get("updated_at"),
            "tracker_id": product.get("tracker_id"),
            "run_id": product.get("run_id"),
            "period_id": product.get("period_id"),
        }
        if _included_before_cutoff(
            product_row,
            cutoff,
            label="work_product",
            warnings=warnings,
        ):
            work_products.append(product_row)

    manifest = {
        "schema_version": HYPOTHESIS_SCHEMA_VERSION,
        "eligible_source_cutoff": eligible_source_cutoff,
        "trackers": sorted(trackers, key=lambda row: str(row.get("id"))),
        "sources": sorted(
            sources,
            key=lambda row: (str(row.get("tracker_id")), str(row.get("id"))),
        ),
        "tracker_runs": sorted(
            tracker_runs,
            key=lambda row: (str(row.get("tracker_id")), str(row.get("run_id"))),
        ),
        "aggregate_signals": sorted(
            aggregate_signals,
            key=lambda row: (
                str(row.get("period_id")),
                str(row.get("source_tracker_id")),
                str(row.get("id")),
            ),
        ),
        "work_products": sorted(
            work_products,
            key=lambda row: str(row.get("artifact_id")),
        ),
        "warnings": sorted(
            warnings,
            key=lambda row: (row.get("type", ""), row.get("label", ""), row.get("id", "")),
        ),
    }
    frozen = freeze_input_manifest(manifest)
    return {
        "manifest": frozen["manifest"],
        "input_manifest_sha256": frozen["sha256"],
        "warnings": manifest["warnings"],
    }


def hypothesis_id_for(
    *,
    vintage_date: str,
    vintage_kind: str,
    tracker_id: str,
    ticker: str,
    claim: str,
    input_manifest_sha256: str,
) -> str:
    digest = _stable_hash(
        {
            "vintage_date": vintage_date,
            "vintage_kind": vintage_kind,
            "tracker_id": tracker_id,
            "ticker": ticker,
            "claim": claim,
            "input_manifest_sha256": input_manifest_sha256,
        }
    )
    return f"hyp-{vintage_date}-{digest[:16]}"


def evaluation_window(vintage_date: str, horizon_days: int = 7) -> tuple[str, str]:
    start = date.fromisoformat(vintage_date) + timedelta(days=1)
    end = start + timedelta(days=max(1, int(horizon_days)) - 1)
    return start.isoformat(), end.isoformat()


def confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"


def market_data_snapshot_hash(payload: dict[str, Any]) -> str:
    return _stable_hash(payload)


def training_summary_path(summary: dict[str, Any]) -> Path:
    created = str(summary.get("created_at") or _now()).replace(":", "").replace("+", "z")
    digest = _stable_hash(summary)[:12]
    return training_summaries_root() / f"{created}_{digest}.json"


def write_training_summary(summary: dict[str, Any]) -> dict[str, Any]:
    row = {
        "schema_version": TRAINING_SUMMARY_SCHEMA_VERSION,
        "summary_id": summary.get("summary_id") or f"cal-{uuid.uuid4().hex[:12]}",
        "created_at": summary.get("created_at") or _now(),
        **summary,
    }
    _write_json(training_summary_path(row), row)
    return row


def list_training_summaries() -> list[dict[str, Any]]:
    if not training_summaries_root().exists():
        return []
    rows = []
    for path in training_summaries_root().glob("*.json"):
        data = _read_json(path, {})
        if isinstance(data, dict):
            rows.append(data)
    rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return rows


def _vintage_summary(vintage_date: str) -> dict[str, Any]:
    vintage = get_vintage(vintage_date)
    hypotheses = vintage["hypotheses"]
    outcomes = vintage["outcomes"]
    kind_counts: dict[str, int] = {}
    for row in hypotheses:
        kind_counts[row["vintage_kind"]] = kind_counts.get(row["vintage_kind"], 0) + 1
    completed_ids = {row.get("hypothesis_id") for row in outcomes}
    return {
        "vintage_date": vintage_date,
        "vintage_kind": (hypotheses[0]["vintage_kind"] if hypotheses else "forward_live"),
        "hypothesis_count": len(hypotheses),
        "outcome_count": len(outcomes),
        "pending_count": len(
            [row for row in hypotheses if row["hypothesis_id"] not in completed_ids]
        ),
        "training_eligible_count": len(
            [row for row in outcomes if row.get("eligible_for_training")]
        ),
        "kind_counts": kind_counts,
    }


def hypothesis_dashboard_payload() -> dict[str, Any]:
    vintage_dates = list_vintage_dates()
    rows = []
    for vintage_date in vintage_dates:
        rows.extend(get_vintage(vintage_date)["rows"])
    rows.sort(
        key=lambda row: (str(row.get("vintage_date", "")), str(row.get("generated_at", ""))),
        reverse=True,
    )
    summaries = [_vintage_summary(vintage_date) for vintage_date in vintage_dates]
    pending = [row for row in rows if not row.get("outcome")]
    return {
        "schema_version": HYPOTHESIS_SCHEMA_VERSION,
        "generated_at": _now(),
        "summary": {
            "vintage_count": len(summaries),
            "hypothesis_count": len(rows),
            "pending_count": len(pending),
            "training_eligible_count": len(
                [row for row in rows if (row.get("outcome") or {}).get("eligible_for_training")]
            ),
        },
        "vintages": summaries,
        "rows": rows,
        "latest": get_vintage(vintage_dates[0]) if vintage_dates else None,
        "calibration": list_training_summaries()[:5],
    }
