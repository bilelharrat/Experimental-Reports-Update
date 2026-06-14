"""Persistent Stock Research tracker store and deterministic job contracts.

The Phase 8 stock-research workspace is intentionally separate from Memo
Studio and from the existing weekly hot-stock dashboard. Tracker agents own
their source folders and durable memory; aggregator and strategy-map jobs only
consume structured tracker outputs plus source traces.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, deck_summary, job_progress, storage

SCHEMA_VERSION = 1
TRACKER_OUTPUT_SCHEMA_VERSION = 1
WEEKLY_AGGREGATE_SCHEMA_VERSION = 1
STRATEGY_MAP_SCHEMA_VERSION = 1
WORK_PRODUCT_SCHEMA_VERSION = 1
RUN_LEDGER_SCHEMA_VERSION = 1

TRACKER_TYPES = ("macro", "industry", "company")
TRACKER_STATUSES = ("active", "disabled", "archived")
WORK_PRODUCT_STATUSES = (
    "draft",
    "needs_review",
    "approved",
    "published",
    "superseded",
    "archived",
    "failed",
)
REVIEW_STATUSES = ("open", "resolved", "waived", "rejected")
RUN_STATES = job_progress.RESEARCH_JOB_STATES
RUN_TERMINAL_STATES = job_progress.RESEARCH_JOB_TERMINAL_STATES

SOURCE_TRACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "tracker_id",
        "tracker_run_id",
        "source_id",
        "source_title",
        "locator",
        "excerpt",
        "confidence",
        "checked_at",
    ],
    "properties": {
        "tracker_id": {"type": "string"},
        "tracker_run_id": {"type": "string"},
        "source_id": {"type": ["string", "null"]},
        "source_title": {"type": "string"},
        "url": {"type": ["string", "null"]},
        "file_id": {"type": ["string", "null"]},
        "locator": {"type": "string"},
        "timestamp": {"type": ["string", "null"]},
        "excerpt": {"type": "string"},
        "confidence": {"type": ["number", "null"]},
        "checked_at": {"type": "string"},
    },
}

TRACKER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema_version",
        "tracker_id",
        "tracker_type",
        "tracker_run_id",
        "period_start",
        "period_end",
        "generated_at",
        "status",
        "confidence",
        "thesis",
        "key_signals",
        "metrics",
        "source_traces",
    ],
    "properties": {
        "schema_version": {"const": TRACKER_OUTPUT_SCHEMA_VERSION},
        "tracker_id": {"type": "string"},
        "tracker_type": {"enum": list(TRACKER_TYPES)},
        "tracker_run_id": {"type": "string"},
        "period_start": {"type": "string"},
        "period_end": {"type": "string"},
        "generated_at": {"type": "string"},
        "status": {"type": "string"},
        "confidence": {"type": ["number", "null"]},
        "thesis": {"type": "string"},
        "key_signals": {"type": "array"},
        "metrics": {"type": "array"},
        "recommendations": {"type": "array"},
        "open_questions": {"type": "array"},
        "missing_sources": {"type": "array"},
        "contradictions": {"type": "array"},
        "watch_items": {"type": "array"},
        "source_traces": {"type": "array", "items": SOURCE_TRACE_SCHEMA},
        "knowledge_updates": {"type": "array"},
        "type_sections": {"type": "object"},
    },
}

WEEKLY_AGGREGATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema_version",
        "period_id",
        "included_tracker_run_ids",
        "modules",
        "ranked_signals",
        "deduped_claims",
        "markdown",
    ],
    "properties": {
        "schema_version": {"const": WEEKLY_AGGREGATE_SCHEMA_VERSION},
        "period_id": {"type": "string"},
        "period_start": {"type": "string"},
        "period_end": {"type": "string"},
        "generated_at": {"type": "string"},
        "included_tracker_run_ids": {"type": "array"},
        "excluded_tracker_warnings": {"type": "array"},
        "modules": {"type": "object"},
        "ranked_signals": {"type": "array"},
        "deduped_claims": {"type": "array"},
        "contradictions": {"type": "array"},
        "missing_source_warnings": {"type": "array"},
        "event_calendar": {"type": "array"},
        "trigger_conditions": {"type": "array"},
        "markdown": {"type": "string"},
        "html_blocks": {"type": "array"},
    },
}

STRATEGY_MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema_version",
        "period_id",
        "current_weekly_aggregate_id",
        "nodes",
        "edges",
        "diff",
        "markdown",
    ],
    "properties": {
        "schema_version": {"const": STRATEGY_MAP_SCHEMA_VERSION},
        "period_id": {"type": "string"},
        "generated_at": {"type": "string"},
        "current_weekly_aggregate_id": {"type": ["string", "null"]},
        "previous_strategy_map_id": {"type": ["string", "null"]},
        "nodes": {"type": "array"},
        "edges": {"type": "array"},
        "diff": {"type": "array"},
        "contradictions": {"type": "array"},
        "markdown": {"type": "string"},
        "layout_metadata": {"type": "object"},
    },
}

WORK_PRODUCT_METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "artifact_id",
        "artifact_type",
        "title",
        "status",
        "version",
        "created_at",
        "updated_at",
        "source_trace_count",
        "review_state",
        "pinned",
        "archived",
    ],
    "properties": {
        "artifact_id": {"type": "string"},
        "artifact_type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"enum": list(WORK_PRODUCT_STATUSES)},
        "version": {"type": "integer"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "generated_by": {"type": "string"},
        "reviewer": {"type": ["string", "null"]},
        "source_refs": {"type": "array"},
        "source_trace_count": {"type": "integer"},
        "confidence": {"type": ["number", "null"]},
        "review_state": {"enum": list(REVIEW_STATUSES)},
        "supersedes": {"type": ["string", "null"]},
        "superseded_by": {"type": ["string", "null"]},
        "pinned": {"type": "boolean"},
        "archived": {"type": "boolean"},
        "export_paths": {"type": "object"},
        "notes": {"type": "string"},
    },
}

STOCK_RESEARCH_ROOT: Path = storage.DATA_DIR / "stock_research"
ACTIVE_JOB_MAX_IDLE_SECONDS = 1800
SOURCE_EXTRACTION_TEXT_LIMIT = 20_000
SOURCE_CHUNK_TEXT_LIMIT = 2_000
SOURCE_OCR_MIN_TEXT_CHARS = 200

SOURCE_PRIORITY_SCORES = {
    "official": 1.0,
    "company_disclosure": 1.0,
    "transcript": 0.95,
    "primary_data": 0.92,
    "sell_side": 0.78,
    "vertical_media": 0.7,
    "reputable_media": 0.66,
    "financial_media": 0.62,
    "user_provided": 0.58,
    "note": 0.45,
    "unknown": 0.35,
}

_LOCK = threading.RLock()
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.RLock()


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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text or "", encoding="utf-8")
    tmp.replace(path)


def _slug(value: str, *, fallback: str = "item") -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_.-]+", "-", raw)
    raw = raw.strip(".-")
    raw = re.sub(r"-{2,}", "-", raw)
    if not raw:
        raw = fallback
    if raw in {".", ".."} or "/" in raw or "\\" in raw:
        raise ValueError("Invalid id")
    return raw[:96]


def _safe_component(value: str, *, label: str = "id") -> str:
    safe = _slug(value, fallback="")
    if not safe or safe != value:
        raise ValueError(f"Invalid {label}: {value}")
    return safe


def _root() -> Path:
    return STOCK_RESEARCH_ROOT


def trackers_root() -> Path:
    return _root() / "trackers"


def aggregates_root() -> Path:
    return _root() / "aggregates"


def strategy_maps_root() -> Path:
    return _root() / "strategy_maps"


def catalog_path() -> Path:
    return _root() / "work_products.json"


def run_ledger_path() -> Path:
    return _root() / "run_ledger.json"


def review_queue_path() -> Path:
    return _root() / "review_queue.json"


def tracker_dir(tracker_id: str) -> Path:
    return trackers_root() / _safe_component(tracker_id, label="tracker id")


def tracker_config_path(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "tracker.json"


def tracker_knowledge_path(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "knowledge.json"


def tracker_notes_path(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "notes.md"


def tracker_sources_dir(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "sources"


def tracker_source_manifest_path(tracker_id: str) -> Path:
    return tracker_sources_dir(tracker_id) / "source_manifest.json"


def tracker_runs_dir(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "runs"


def tracker_run_dir(tracker_id: str, run_id: str) -> Path:
    return tracker_runs_dir(tracker_id) / _safe_component(run_id, label="run id")


def tracker_run_metadata_path(tracker_id: str, run_id: str) -> Path:
    return tracker_run_dir(tracker_id, run_id) / "run.json"


def tracker_run_output_path(tracker_id: str, run_id: str) -> Path:
    return tracker_run_dir(tracker_id, run_id) / "tracker_output.json"


def tracker_run_report_path(tracker_id: str, run_id: str) -> Path:
    return tracker_run_dir(tracker_id, run_id) / "report.md"


def tracker_run_source_manifest_path(tracker_id: str, run_id: str) -> Path:
    return tracker_run_dir(tracker_id, run_id) / "source_manifest.json"


def tracker_logs_dir(tracker_id: str) -> Path:
    return tracker_dir(tracker_id) / "logs"


def tracker_progress_path(tracker_id: str, run_id: str) -> Path:
    return tracker_logs_dir(tracker_id) / f"{_safe_component(run_id, label='run id')}.progress.jsonl"


def aggregate_dir(period_id: str) -> Path:
    return aggregates_root() / _safe_component(period_id, label="period id")


def aggregate_json_path(period_id: str) -> Path:
    return aggregate_dir(period_id) / "weekly_report.json"


def aggregate_markdown_path(period_id: str) -> Path:
    return aggregate_dir(period_id) / "weekly_report.md"


def aggregate_progress_path(period_id: str) -> Path:
    return aggregate_dir(period_id) / "weekly_report.progress.jsonl"


def strategy_map_dir(period_id: str) -> Path:
    return strategy_maps_root() / _safe_component(period_id, label="period id")


def strategy_map_json_path(period_id: str) -> Path:
    return strategy_map_dir(period_id) / "strategy_map.json"


def strategy_map_markdown_path(period_id: str) -> Path:
    return strategy_map_dir(period_id) / "strategy_map.md"


def strategy_map_progress_path(period_id: str) -> Path:
    return strategy_map_dir(period_id) / "strategy_map.progress.jsonl"


def _ensure_roots() -> None:
    for path in (
        trackers_root(),
        aggregates_root(),
        strategy_maps_root(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value).strip() or default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
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


def _string_list(value: Any) -> list[str]:
    out = []
    for item in _as_list(value):
        text = _as_str(item)
        if text and text not in out:
            out.append(text)
    return out


def _append_source_chunk(
    chunks: list[dict],
    *,
    label: str,
    locator: str,
    text: str,
    remaining: list[int],
    page_no: int | None = None,
    slide_no: int | None = None,
) -> bool:
    cleaned = _as_str(text)
    if not cleaned or remaining[0] <= 0:
        return remaining[0] > 0
    if len(cleaned) > remaining[0]:
        cleaned = cleaned[: remaining[0]].rstrip()
    excerpt = cleaned[:SOURCE_CHUNK_TEXT_LIMIT].rstrip()
    entry = {
        "id": f"chunk-{len(chunks) + 1}",
        "label": label,
        "locator": locator,
        "excerpt": excerpt,
        "char_count": len(cleaned),
    }
    if page_no is not None:
        entry["page_no"] = page_no
    if slide_no is not None:
        entry["slide_no"] = slide_no
    chunks.append(entry)
    remaining[0] -= len(cleaned)
    return remaining[0] > 0


def _ocr_source_chunks_from_path(path: Path) -> list[dict]:
    """Best-effort OCR hook; returns no chunks when local tools are missing."""
    if shutil.which("tesseract") is None:
        return []
    suffix = path.suffix.lower()
    chunks: list[dict] = []
    remaining = [SOURCE_EXTRACTION_TEXT_LIMIT]

    def run_tesseract(image_path: Path) -> str:
        try:
            proc = subprocess.run(
                ["tesseract", str(image_path), "stdout"],
                capture_output=True,
                text=True,
                timeout=90,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout or ""

    if suffix == ".pdf":
        if shutil.which("pdftoppm") is None:
            return []
        with tempfile.TemporaryDirectory(prefix="stock-research-ocr-") as tmp:
            prefix = Path(tmp) / "page"
            try:
                proc = subprocess.run(
                    [
                        "pdftoppm",
                        "-png",
                        "-r",
                        "200",
                        "-f",
                        "1",
                        "-l",
                        "10",
                        str(path),
                        str(prefix),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except Exception:
                return []
            if proc.returncode != 0:
                return []
            for index, image_path in enumerate(sorted(Path(tmp).glob("page-*.png")), start=1):
                keep_going = _append_source_chunk(
                    chunks,
                    label=f"Page {index} OCR",
                    locator=f"page {index} ocr",
                    text=run_tesseract(image_path),
                    remaining=remaining,
                    page_no=index,
                )
                if not keep_going:
                    break
        return chunks

    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        _append_source_chunk(
            chunks,
            label="Image OCR",
            locator="image ocr",
            text=run_tesseract(path),
            remaining=remaining,
        )
        return chunks
    return []


def _extract_source_chunks_from_upload(filename: str, data: bytes) -> dict:
    """Best-effort, bounded text extraction for tracker-owned source files."""
    suffix = Path(filename).suffix.lower()
    chunks: list[dict] = []
    remaining = [SOURCE_EXTRACTION_TEXT_LIMIT]
    ocr_needed = False
    extraction_error = ""
    try:
        if suffix in {".txt", ".md", ".csv", ".tsv"}:
            _append_source_chunk(
                chunks,
                label="Document",
                locator="document",
                text=data.decode("utf-8", errors="replace"),
                remaining=remaining,
            )
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                extraction_error = "pypdf_not_available"
            else:
                reader = PdfReader(io.BytesIO(data))
                for index, page in enumerate(reader.pages[:50], start=1):
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    keep_going = _append_source_chunk(
                        chunks,
                        label=f"Page {index}",
                        locator=f"page {index}",
                        text=page_text,
                        remaining=remaining,
                        page_no=index,
                    )
                    if not keep_going:
                        break
                total_text = sum(len(_as_str(chunk.get("excerpt"))) for chunk in chunks)
                ocr_needed = total_text < SOURCE_OCR_MIN_TEXT_CHARS
        elif suffix in {".docx", ".doc"}:
            try:
                from docx import Document  # type: ignore
            except ImportError:
                extraction_error = "python_docx_not_available"
            else:
                doc = Document(io.BytesIO(data))
                _append_source_chunk(
                    chunks,
                    label="Document",
                    locator="document",
                    text="\n".join(p.text for p in doc.paragraphs),
                    remaining=remaining,
                )
        elif suffix == ".pptx":
            with tempfile.TemporaryDirectory(prefix="stock-research-pptx-") as tmp:
                staged = Path(tmp) / filename
                staged.write_bytes(data)
                for slide in deck_summary.extract_slides(staged, "pptx"):
                    if slide.text:
                        keep_going = _append_source_chunk(
                            chunks,
                            label=f"Slide {slide.slide_no}",
                            locator=f"slide {slide.slide_no}",
                            text=slide.text,
                            remaining=remaining,
                            slide_no=slide.slide_no,
                        )
                        if not keep_going:
                            break
                    if slide.notes:
                        keep_going = _append_source_chunk(
                            chunks,
                            label=f"Slide {slide.slide_no} notes",
                            locator=f"slide {slide.slide_no} notes",
                            text=slide.notes,
                            remaining=remaining,
                            slide_no=slide.slide_no,
                        )
                        if not keep_going:
                            break
        elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            ocr_needed = True
        else:
            extraction_error = "unsupported_file_type"
    except Exception as exc:  # noqa: BLE001
        extraction_error = f"{type(exc).__name__}: {exc}"

    if ocr_needed and not chunks:
        with tempfile.TemporaryDirectory(prefix="stock-research-ocr-src-") as tmp:
            staged = Path(tmp) / filename
            staged.write_bytes(data)
            chunks = _ocr_source_chunks_from_path(staged)

    if chunks:
        return {
            "status": "ready",
            "chunks": chunks,
            "ocr_needed": False,
            "extraction_error": extraction_error,
        }
    return {
        "status": "ocr_needed" if ocr_needed else "stored",
        "chunks": [],
        "ocr_needed": ocr_needed,
        "extraction_error": extraction_error,
    }


def _normalize_tracker_status(value: Any) -> str:
    text = _as_str(value, "active").lower()
    if text not in TRACKER_STATUSES:
        return "active"
    return text


def _normalize_work_product_status(value: Any) -> str:
    text = _as_str(value, "draft").lower()
    if text not in WORK_PRODUCT_STATUSES:
        return "draft"
    return text


def _normalize_review_status(value: Any) -> str:
    text = _as_str(value, "open").lower()
    if text not in REVIEW_STATUSES:
        return "open"
    return text


def _normalize_tracker_type(value: Any) -> str:
    text = _as_str(value).lower()
    if text not in TRACKER_TYPES:
        raise ValueError(f"Tracker type must be one of: {', '.join(TRACKER_TYPES)}")
    return text


def _normalize_language(value: Any) -> str:
    text = _as_str(value, "en").lower()
    return text if text in {"en", "zh"} else "en"


def _source_policy_for(tracker_type: str, current: dict | None = None) -> dict:
    defaults = {
        "macro": {
            "official_sources": [
                "central bank releases",
                "fiscal authority releases",
                "statistical agency data",
            ],
            "primary_data": ["market prices", "rates", "FX", "commodities"],
            "financial_media": ["Reuters", "Bloomberg", "Financial Times"],
            "sell_side_sources": ["macro strategy notes"],
            "user_sources": ["tracker-owned local sources"],
        },
        "industry": {
            "official_sources": ["company disclosures", "industry filings"],
            "sell_side_sources": ["sector research", "call notes"],
            "vertical_sources": ["industry media", "supply-chain checks"],
            "financial_media": ["Reuters", "Bloomberg"],
            "user_sources": ["tracker-owned local sources"],
        },
        "company": {
            "official_sources": ["company filings", "transcripts", "press releases"],
            "sell_side_sources": ["coverage notes", "valuation updates"],
            "vertical_sources": ["company-specific reporting"],
            "financial_media": ["Reuters", "Bloomberg"],
            "user_sources": ["tracker-owned local sources"],
        },
    }
    policy = copy.deepcopy(defaults[tracker_type])
    if isinstance(current, dict):
        for key, value in current.items():
            if isinstance(value, list):
                policy[key] = _string_list(value)
            elif value is not None:
                policy[key] = value
    return policy


def _freshness_policy(current: dict | None = None) -> dict:
    base = {
        "stale_after_days": 7,
        "last_successful_run": None,
        "next_due_run": None,
        "run_blocking_missing_inputs": [],
    }
    if isinstance(current, dict):
        base.update({
            "stale_after_days": max(1, _as_int(current.get("stale_after_days"), 7)),
            "last_successful_run": current.get("last_successful_run"),
            "next_due_run": current.get("next_due_run"),
            "run_blocking_missing_inputs": _string_list(
                current.get("run_blocking_missing_inputs")
            ),
        })
    return base


def _cadence(current: dict | str | None = None) -> dict:
    if isinstance(current, str):
        frequency = current
        event_driven = False
    elif isinstance(current, dict):
        frequency = current.get("frequency") or "weekly"
        event_driven = bool(current.get("event_driven"))
    else:
        frequency = "weekly"
        event_driven = False
    frequency = _as_str(frequency, "weekly").lower()
    if frequency not in {"daily", "weekly", "monthly", "event_driven"}:
        frequency = "weekly"
    return {"frequency": frequency, "event_driven": event_driven}


def _normalize_tracker(payload: dict, *, existing: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Tracker payload must be an object")
    current = copy.deepcopy(existing or {})
    tracker_type = _normalize_tracker_type(payload.get("type", current.get("type")))
    display_name = _as_str(
        payload.get("display_name", current.get("display_name")),
        "Untitled tracker",
    )
    proposed_id = payload.get("id", current.get("id")) or _slug(
        display_name, fallback=f"{tracker_type}-tracker"
    )
    tracker_id = _slug(_as_str(proposed_id), fallback=f"{tracker_type}-tracker")
    now = _now()
    created_at = current.get("created_at") or now

    default_language = _normalize_language(
        payload.get("default_language", current.get("default_language"))
    )
    output_languages = _string_list(
        payload.get("output_languages", current.get("output_languages"))
    )
    if default_language not in output_languages:
        output_languages.insert(0, default_language)
    output_languages = [lang for lang in output_languages if lang in {"en", "zh"}]
    if not output_languages:
        output_languages = ["en"]

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "id": tracker_id,
        "type": tracker_type,
        "display_name": display_name,
        "status": _normalize_tracker_status(
            payload.get("status", current.get("status", "active"))
        ),
        "owner": _as_str(payload.get("owner", current.get("owner")), "Research"),
        "priority": max(1, min(5, _as_int(payload.get("priority", current.get("priority")), 3))),
        "market": _as_str(payload.get("market", current.get("market"))),
        "country": _as_str(payload.get("country", current.get("country"))),
        "sector": _as_str(payload.get("sector", current.get("sector"))),
        "industry": _as_str(payload.get("industry", current.get("industry"))),
        "subsegments": _string_list(
            payload.get("subsegments", current.get("subsegments"))
        ),
        "tickers": [ticker.upper() for ticker in _string_list(
            payload.get("tickers", current.get("tickers"))
        )],
        "cadence": _cadence(payload.get("cadence", current.get("cadence"))),
        "default_language": default_language,
        "output_languages": output_languages,
        "writing_profile": _as_str(
            payload.get("writing_profile", current.get("writing_profile")),
            "professional_restrained_investment_research",
        ),
        "source_policy": _source_policy_for(
            tracker_type,
            payload.get("source_policy", current.get("source_policy")),
        ),
        "freshness_policy": _freshness_policy(
            payload.get("freshness_policy", current.get("freshness_policy"))
        ),
        "latest_run_id": current.get("latest_run_id"),
        "latest_thesis": current.get("latest_thesis"),
        "latest_confidence": current.get("latest_confidence"),
        "current_run": current.get("current_run"),
        "created_at": created_at,
        "updated_at": now,
    }
    if tracker_type == "company" and not normalized["tickers"]:
        raise ValueError("Company trackers require at least one ticker")
    if tracker_type == "industry" and not (
        normalized["industry"] or normalized["sector"] or normalized["subsegments"]
    ):
        raise ValueError("Industry trackers require industry, sector, or subsegments")
    if tracker_type == "macro" and not (normalized["market"] or normalized["country"]):
        raise ValueError("Macro trackers require market or country")
    return normalized


STARTER_TRACKERS = [
    {
        "id": "us-macro",
        "type": "macro",
        "display_name": "US Macro Tracker",
        "owner": "Research",
        "priority": 1,
        "market": "United States",
        "country": "US",
        "sector": "Macro",
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
    },
    {
        "id": "ai-cloud-infrastructure",
        "type": "industry",
        "display_name": "AI Cloud Infrastructure",
        "owner": "Research",
        "priority": 1,
        "market": "Global",
        "sector": "Technology",
        "industry": "AI infrastructure",
        "subsegments": ["accelerators", "cloud capex", "networking"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
    },
    {
        "id": "nvidia",
        "type": "company",
        "display_name": "NVIDIA",
        "owner": "Research",
        "priority": 1,
        "market": "United States",
        "country": "US",
        "sector": "Technology",
        "industry": "Semiconductors",
        "tickers": ["NVDA"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
    },
]


def _default_knowledge(tracker: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tracker_id": tracker["id"],
        "facts": [],
        "accepted_lessons": [],
        "reviewer_notes": [],
        "updated_at": _now(),
    }


def _ensure_tracker_files(tracker: dict) -> None:
    tid = tracker["id"]
    tdir = tracker_dir(tid)
    (tdir / "runs").mkdir(parents=True, exist_ok=True)
    (tdir / "logs").mkdir(parents=True, exist_ok=True)
    tracker_sources_dir(tid).mkdir(parents=True, exist_ok=True)
    if not tracker_knowledge_path(tid).exists():
        _write_json(tracker_knowledge_path(tid), _default_knowledge(tracker))
    if not tracker_notes_path(tid).exists():
        _write_text(
            tracker_notes_path(tid),
            f"# {tracker['display_name']} Notes\n\n",
        )
    if not tracker_source_manifest_path(tid).exists():
        _write_json(tracker_source_manifest_path(tid), {"sources": []})


def seed_tracker_registry() -> list[dict]:
    """Create exactly three starter trackers when the registry is empty."""
    with _LOCK:
        _ensure_roots()
        existing = list(trackers_root().glob("*/tracker.json"))
        if existing:
            return list_trackers(include_archived=True, seed=False)
        for item in STARTER_TRACKERS:
            tracker = _normalize_tracker(item)
            _write_json(tracker_config_path(tracker["id"]), tracker)
            _ensure_tracker_files(tracker)
        return list_trackers(include_archived=True, seed=False)


def list_trackers(*, include_archived: bool = False, seed: bool = True) -> list[dict]:
    with _LOCK:
        _ensure_roots()
        if seed:
            seed_tracker_registry()
        trackers: list[dict] = []
        for path in sorted(trackers_root().glob("*/tracker.json")):
            data = _read_json(path, {})
            if not isinstance(data, dict) or not data.get("id"):
                continue
            try:
                tracker = _normalize_tracker(data, existing=data)
            except ValueError:
                continue
            if not include_archived and tracker.get("status") == "archived":
                continue
            tracker["source_count"] = len(list_tracker_sources(tracker["id"]))
            tracker["run_count"] = len(list_tracker_runs(tracker["id"]))
            tracker["is_due"] = tracker_is_due(tracker)
            tracker["is_stale"] = tracker_is_stale(tracker)
            trackers.append(tracker)
        trackers.sort(key=lambda t: (t.get("status") == "archived", t.get("priority", 9), t.get("display_name", "")))
        return trackers


def get_tracker(tracker_id: str) -> dict | None:
    with _LOCK:
        path = tracker_config_path(tracker_id)
        if not path.exists():
            return None
        data = _read_json(path, {})
        if not isinstance(data, dict):
            return None
        tracker = _normalize_tracker(data, existing=data)
        tracker["sources"] = list_tracker_sources(tracker_id)
        tracker["runs"] = list_tracker_runs(tracker_id)
        tracker["knowledge"] = _read_json(tracker_knowledge_path(tracker_id), {})
        tracker["notes"] = tracker_notes_path(tracker_id).read_text(
            encoding="utf-8"
        ) if tracker_notes_path(tracker_id).exists() else ""
        return tracker


def create_tracker(payload: dict) -> dict:
    with _LOCK:
        _ensure_roots()
        tracker = _normalize_tracker(payload)
        if tracker_config_path(tracker["id"]).exists():
            raise ValueError(f"Tracker already exists: {tracker['id']}")
        _write_json(tracker_config_path(tracker["id"]), tracker)
        _ensure_tracker_files(tracker)
        return tracker


def update_tracker(tracker_id: str, patch: dict) -> dict:
    with _LOCK:
        current = get_tracker(tracker_id)
        if current is None:
            raise ValueError(f"Unknown tracker: {tracker_id}")
        merged = {**current, **(patch or {}), "id": tracker_id}
        tracker = _normalize_tracker(merged, existing=current)
        _write_json(tracker_config_path(tracker_id), tracker)
        _ensure_tracker_files(tracker)
        return tracker


def disable_tracker(tracker_id: str, *, archive: bool = False) -> dict:
    return update_tracker(tracker_id, {"status": "archived" if archive else "disabled"})


def import_company_trackers(limit: int = 20) -> dict:
    """Explicitly import public companies from companies.yaml as candidates."""
    created: list[dict] = []
    skipped: list[dict] = []
    for company in storage.list_companies():
        if len(created) >= limit:
            break
        ticker = _as_str(company.get("ticker")).upper()
        if not ticker:
            continue
        if storage.infer_company_type(company) != "public":
            continue
        tracker_id = _slug(ticker.lower())
        if tracker_config_path(tracker_id).exists():
            skipped.append({"id": tracker_id, "reason": "exists"})
            continue
        try:
            created.append(
                create_tracker(
                    {
                        "id": tracker_id,
                        "type": "company",
                        "display_name": company.get("name") or ticker,
                        "market": company.get("exchange") or "Public equities",
                        "country": "US",
                        "sector": company.get("sector") or "",
                        "industry": company.get("industry") or "",
                        "tickers": [ticker],
                        "priority": 3,
                    }
                )
            )
        except ValueError as exc:
            skipped.append({"id": tracker_id, "reason": str(exc)})
    return {"created": created, "skipped": skipped}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def tracker_is_stale(tracker: dict) -> bool:
    policy = tracker.get("freshness_policy") or {}
    last = _parse_dt(policy.get("last_successful_run"))
    if last is None:
        return True
    days = max(1, _as_int(policy.get("stale_after_days"), 7))
    return datetime.now(timezone.utc) - last > timedelta(days=days)


def tracker_is_due(tracker: dict) -> bool:
    policy = tracker.get("freshness_policy") or {}
    next_due = _parse_dt(policy.get("next_due_run"))
    if next_due is None:
        return tracker_is_stale(tracker)
    return datetime.now(timezone.utc) >= next_due


def _source_manifest(tracker_id: str) -> dict:
    data = _read_json(tracker_source_manifest_path(tracker_id), {"sources": []})
    if not isinstance(data, dict):
        data = {"sources": []}
    data["sources"] = [s for s in _as_list(data.get("sources")) if isinstance(s, dict)]
    return data


def _write_source_manifest(tracker_id: str, manifest: dict) -> None:
    sources = [s for s in _as_list(manifest.get("sources")) if isinstance(s, dict)]
    sources.sort(key=lambda s: str(s.get("created_at", "")), reverse=True)
    _write_json(tracker_source_manifest_path(tracker_id), {"sources": sources})


def list_tracker_sources(tracker_id: str) -> list[dict]:
    try:
        tracker_config_path(tracker_id)
    except ValueError:
        return []
    manifest = _source_manifest(tracker_id)
    sources = manifest["sources"]
    for source in sources:
        source["tracker_id"] = tracker_id
        stored_name = source.get("stored_name")
        if stored_name:
            exists = (tracker_sources_dir(tracker_id) / stored_name).exists()
            source["exists"] = exists
            if not exists:
                source["extraction_status"] = "missing"
                source["missing_reason"] = "Stored file is missing from tracker source folder."
                _upsert_review_item(
                    {
                        "id": f"missing-file:{tracker_id}:{source.get('id')}",
                        "item_type": "missing_source",
                        "status": "open",
                        "title": f"Stored source file missing: {source.get('title') or source.get('filename')}",
                        "artifact_id": f"source:{tracker_id}:{source.get('id')}",
                        "tracker_id": tracker_id,
                        "severity": "high",
                        "source_refs": [source],
                    }
                )
        else:
            source["exists"] = True
        source["source_quality_score"] = source_quality_score(source)
    return sources


def _source_id(seed: str | None = None) -> str:
    if seed:
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"src-{digest}"
    return f"src-{uuid.uuid4().hex[:12]}"


def _normalize_source_payload(payload: dict, *, source_type: str) -> dict:
    title = _as_str(payload.get("title")) or _as_str(payload.get("url")) or "Untitled source"
    priority = _as_str(payload.get("priority"), "user_provided").lower()
    relevance = _as_str(payload.get("relevance"), "this_week_input").lower()
    return {
        "source_type": source_type,
        "title": title,
        "url": _as_str(payload.get("url")) or None,
        "priority": priority,
        "relevance": relevance,
        "freshness": _as_str(payload.get("freshness"), "current"),
        "notes": _as_str(payload.get("notes")),
    }


def _copy_source_record_to_tracker(tracker_id: str, record: dict, data: bytes | None) -> dict:
    if get_tracker(tracker_id) is None:
        raise ValueError(f"Unknown tracker: {tracker_id}")
    manifest = _source_manifest(tracker_id)
    existing_ids = {s.get("id") for s in manifest["sources"]}
    out = copy.deepcopy(record)
    if data is not None and out.get("stored_name"):
        path = tracker_sources_dir(tracker_id) / out["stored_name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if out["id"] in existing_ids:
        for index, item in enumerate(manifest["sources"]):
            if item.get("id") == out["id"]:
                merged = {**item, **out, "updated_at": _now()}
                manifest["sources"][index] = merged
                _write_source_manifest(tracker_id, manifest)
                return {**merged, "tracker_id": tracker_id}
    manifest["sources"].append(out)
    _write_source_manifest(tracker_id, manifest)
    return {**out, "tracker_id": tracker_id}


def create_link_source(payload: dict) -> dict:
    tracker_ids = _string_list(payload.get("tracker_ids"))
    if not tracker_ids and payload.get("tracker_id"):
        tracker_ids = [_as_str(payload.get("tracker_id"))]
    if not tracker_ids:
        raise ValueError("At least one tracker_id is required")
    normalized = _normalize_source_payload(payload, source_type="link")
    if not normalized.get("url"):
        raise ValueError("Link sources require a url")
    now = _now()
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": _source_id(normalized["url"]),
        **normalized,
        "created_at": now,
        "updated_at": now,
        "extraction_status": "metadata_only",
        "chunks": [
            {
                "locator": normalized["url"],
                "excerpt": normalized["notes"] or normalized["title"],
            }
        ],
    }
    assigned = [_copy_source_record_to_tracker(tid, record, None) for tid in tracker_ids]
    return {"source": record, "assigned": assigned}


def create_note_source(payload: dict) -> dict:
    tracker_ids = _string_list(payload.get("tracker_ids"))
    if not tracker_ids and payload.get("tracker_id"):
        tracker_ids = [_as_str(payload.get("tracker_id"))]
    if not tracker_ids:
        raise ValueError("At least one tracker_id is required")
    body = _as_str(payload.get("body") or payload.get("notes"))
    if not body:
        raise ValueError("Note sources require body text")
    normalized = _normalize_source_payload({**payload, "notes": body}, source_type="note")
    now = _now()
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": _source_id(f"{normalized['title']}:{body}"),
        **normalized,
        "body": body,
        "created_at": now,
        "updated_at": now,
        "extraction_status": "ready",
        "chunks": [{"locator": "note", "excerpt": body[:1200]}],
    }
    assigned = [_copy_source_record_to_tracker(tid, record, None) for tid in tracker_ids]
    return {"source": record, "assigned": assigned}


def create_file_source(
    *,
    tracker_ids: list[str],
    filename: str,
    content_type: str | None,
    data: bytes,
    title: str | None = None,
    priority: str = "user_provided",
    relevance: str = "this_week_input",
) -> dict:
    if not tracker_ids:
        raise ValueError("At least one tracker_id is required")
    if not filename:
        raise ValueError("Missing filename")
    if not data:
        raise ValueError("Empty file")
    safe_name = Path(filename).name.replace("\x00", "").strip() or "file"
    source_id = _source_id(hashlib.sha256(data).hexdigest() + safe_name)
    stored_name = f"{source_id}__{safe_name}"
    extraction = _extract_source_chunks_from_upload(safe_name, data)
    chunks = extraction.get("chunks") or [
        {
            "locator": "file:stored",
            "excerpt": f"{safe_name} stored for tracker review.",
        }
    ]
    now = _now()
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": source_id,
        "source_type": "file",
        "title": title or safe_name,
        "filename": safe_name,
        "stored_name": stored_name,
        "content_type": content_type,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "priority": priority,
        "relevance": relevance,
        "freshness": "current",
        "created_at": now,
        "updated_at": now,
        "extraction_status": extraction.get("status") or "stored",
        "ocr_needed": bool(extraction.get("ocr_needed")),
        "extraction_error": extraction.get("extraction_error") or "",
        "chunks": chunks,
    }
    assigned = [_copy_source_record_to_tracker(tid, record, data) for tid in tracker_ids]
    return {"source": record, "assigned": assigned}


def remove_source_assignment(tracker_id: str, source_id: str) -> dict:
    with _LOCK:
        manifest = _source_manifest(tracker_id)
        kept = [s for s in manifest["sources"] if s.get("id") != source_id]
        removed = len(kept) != len(manifest["sources"])
        _write_source_manifest(tracker_id, {"sources": kept})
        return {"removed": removed, "tracker_id": tracker_id, "source_id": source_id}


def _default_period_range(period_id: str | None = None) -> tuple[str, str, str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    if period_id:
        safe = _safe_component(period_id, label="period id")
        match = re.match(r"^(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})$", safe)
        if match:
            return safe, match.group(1), match.group(2)
        return safe, start.isoformat(), end.isoformat()
    period = f"{start.isoformat()}_to_{end.isoformat()}"
    return period, start.isoformat(), end.isoformat()


def _source_traces_from_sources(
    tracker_id: str,
    run_id: str,
    sources: list[dict],
    *,
    limit: int = 8,
) -> list[dict]:
    traces = []
    for source in sources[:limit]:
        chunks = source.get("chunks") if isinstance(source.get("chunks"), list) else []
        first_chunk = chunks[0] if chunks and isinstance(chunks[0], dict) else {}
        extraction_status = _as_str(source.get("extraction_status"), "metadata_only")
        confidence = 0.75 if extraction_status == "ready" else 0.25 if extraction_status == "missing" else 0.45 if extraction_status == "ocr_needed" else 0.55
        traces.append(
            {
                "tracker_id": tracker_id,
                "tracker_run_id": run_id,
                "source_id": source.get("id"),
                "source_title": source.get("title") or source.get("filename"),
                "url": source.get("url"),
                "file_id": source.get("id") if source.get("source_type") == "file" else None,
                "locator": first_chunk.get("locator") or source.get("url") or "source",
                "timestamp": source.get("created_at"),
                "excerpt": first_chunk.get("excerpt") or source.get("missing_reason") or source.get("notes") or source.get("title"),
                "confidence": confidence,
                "checked_at": _now(),
            }
        )
    return traces


def _signal_from_tracker(tracker: dict, trace: dict | None) -> dict:
    name = tracker.get("display_name") or tracker.get("id")
    tickers = tracker.get("tickers") or []
    affected = tickers or tracker.get("subsegments") or [tracker.get("sector") or tracker.get("market") or name]
    direction = "watch"
    if tracker.get("type") == "macro":
        direction = "neutral"
    elif tracker.get("type") == "industry":
        direction = "positive"
    elif tracker.get("type") == "company":
        direction = "watch"
    return {
        "id": f"sig-{_slug(name)}",
        "observation": f"{name} has new tracker input requiring weekly review.",
        "importance": tracker.get("priority", 3),
        "direction": direction,
        "affected_tickers": tickers,
        "affected_themes": [item for item in affected if item],
        "source_traces": [trace] if trace else [],
        "review_status": "open",
    }


def _metric_from_source(tracker: dict, trace: dict | None) -> dict:
    return {
        "name": "source_count",
        "value": len(list_tracker_sources(tracker["id"])),
        "unit": "sources",
        "period": "current",
        "prior_value": None,
        "expectation": None,
        "source_trace": trace,
    }


def _type_sections(tracker: dict, traces: list[dict]) -> dict:
    base_trace = traces[0] if traces else None
    if tracker["type"] == "macro":
        return {
            "major_events": [],
            "macro_data": [],
            "monetary_policy": {
                "summary": "Source-backed policy read is pending tracker review.",
                "source_traces": [base_trace] if base_trace else [],
            },
            "market_performance": [],
            "next_week_calendar": [],
            "strategy_suggestions": [],
        }
    if tracker["type"] == "industry":
        return {
            "industry_thesis": "Industry thesis needs a full source-backed run.",
            "subsegment_dynamics": [],
            "company_spotlights": [],
            "cross_subsegment_links": [],
            "next_week_catalysts": [],
        }
    return {
        "weekly_core_view": [],
        "financial_updates": [],
        "business_updates": [],
        "management_guidance": [],
        "special_events": [],
        "valuation_matrix": [],
        "action_recommendation": {
            "rating": "monitor",
            "target_range": None,
            "key_nodes": [],
            "take_profit_reference": None,
            "rating_change_triggers": [],
            "source_traces": [base_trace] if base_trace else [],
        },
    }


def fallback_tracker_output(
    tracker: dict,
    *,
    run_id: str,
    period_start: str,
    period_end: str,
    reason: str | None = None,
) -> dict:
    sources = list_tracker_sources(tracker["id"])
    traces = _source_traces_from_sources(tracker["id"], run_id, sources)
    primary_trace = traces[0] if traces else None
    thesis = (
        f"{tracker['display_name']} has {len(sources)} assigned sources; "
        "a model-backed tracker pass is still needed for final judgment."
    )
    output = {
        "schema_version": TRACKER_OUTPUT_SCHEMA_VERSION,
        "output_type": "tracker_output",
        "tracker_id": tracker["id"],
        "tracker_type": tracker["type"],
        "tracker_run_id": run_id,
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": _now(),
        "status": "done",
        "confidence": 0.45 if sources else 0.25,
        "thesis": thesis,
        "key_signals": [_signal_from_tracker(tracker, primary_trace)],
        "metrics": [_metric_from_source(tracker, primary_trace)],
        "recommendations": [
            {
                "rating": "monitor",
                "action": "review",
                "target_range": None,
                "catalysts": [],
                "risk_triggers": [],
                "review_status": "open",
                "source_traces": [primary_trace] if primary_trace else [],
            }
        ],
        "open_questions": [
            {
                "id": "oq-source-backed-run",
                "question": "What changed this period after checking priority sources?",
                "severity": "medium",
                "source_needed": True,
            }
        ],
        "missing_sources": [] if sources else [
            {
                "id": "missing-tracker-sources",
                "description": "No tracker-owned sources are assigned.",
                "priority": "high",
            }
        ],
        "contradictions": [],
        "watch_items": [
            {
                "id": "watch-next-run",
                "description": "Run a full tracker update before using this in a published aggregate.",
                "due": period_end,
            }
        ],
        "source_traces": traces,
        "knowledge_updates": [
            {
                "id": "ku-source-baseline",
                "kind": "lesson",
                "text": "Prefer tracker-owned source manifests over raw cross-topic folders.",
                "review_status": "open",
                "source_traces": traces[:1],
            }
        ],
        "type_sections": _type_sections(tracker, traces),
        "fallback_reason": reason,
        "generated_by": "deterministic_fallback",
    }
    return coerce_tracker_output(output, tracker=tracker, run_id=run_id, period_start=period_start, period_end=period_end)


def _coerce_trace(value: Any, *, tracker_id: str, run_id: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        "tracker_id": _as_str(value.get("tracker_id"), tracker_id),
        "tracker_run_id": _as_str(value.get("tracker_run_id"), run_id),
        "source_id": value.get("source_id"),
        "source_title": _as_str(value.get("source_title") or value.get("title")),
        "url": value.get("url"),
        "file_id": value.get("file_id"),
        "locator": _as_str(value.get("locator"), "source"),
        "timestamp": value.get("timestamp"),
        "excerpt": _as_str(value.get("excerpt")),
        "confidence": _as_float(value.get("confidence"), 0.5),
        "checked_at": value.get("checked_at") or _now(),
    }


def _coerce_trace_list(value: Any, *, tracker_id: str, run_id: str) -> list[dict]:
    traces = []
    for item in _as_list(value):
        trace = _coerce_trace(item, tracker_id=tracker_id, run_id=run_id)
        if trace:
            traces.append(trace)
    return traces


def _coerce_signal(value: Any, *, tracker: dict, run_id: str, index: int) -> dict:
    item = value if isinstance(value, dict) else {"observation": _as_str(value)}
    return {
        "id": _as_str(item.get("id"), f"sig-{index}"),
        "observation": _as_str(item.get("observation"), "Source-backed signal pending."),
        "importance": max(1, min(5, _as_int(item.get("importance"), 3))),
        "direction": _as_str(item.get("direction"), "watch"),
        "affected_tickers": [ticker.upper() for ticker in _string_list(item.get("affected_tickers"))],
        "affected_themes": _string_list(item.get("affected_themes")),
        "source_traces": _coerce_trace_list(
            item.get("source_traces"),
            tracker_id=tracker["id"],
            run_id=run_id,
        ),
        "review_status": _normalize_review_status(item.get("review_status")),
    }


def _coerce_metric(value: Any, *, tracker: dict, run_id: str) -> dict:
    item = value if isinstance(value, dict) else {}
    return {
        "name": _as_str(item.get("name"), "metric"),
        "value": item.get("value"),
        "unit": _as_str(item.get("unit")),
        "period": _as_str(item.get("period")),
        "prior_value": item.get("prior_value"),
        "expectation": item.get("expectation"),
        "source_trace": _coerce_trace(
            item.get("source_trace"),
            tracker_id=tracker["id"],
            run_id=run_id,
        ),
    }


def coerce_tracker_output(
    raw: Any,
    *,
    tracker: dict,
    run_id: str,
    period_start: str,
    period_end: str,
) -> dict:
    data = raw if isinstance(raw, dict) else {}
    traces = _coerce_trace_list(
        data.get("source_traces"),
        tracker_id=tracker["id"],
        run_id=run_id,
    )
    signals = [
        _coerce_signal(item, tracker=tracker, run_id=run_id, index=index)
        for index, item in enumerate(_as_list(data.get("key_signals")), start=1)
    ]
    if not signals:
        signals = [_signal_from_tracker(tracker, traces[0] if traces else None)]
    metrics = [
        _coerce_metric(item, tracker=tracker, run_id=run_id)
        for item in _as_list(data.get("metrics"))
    ]
    if not metrics:
        metrics = [_metric_from_source(tracker, traces[0] if traces else None)]
    output = {
        "schema_version": TRACKER_OUTPUT_SCHEMA_VERSION,
        "output_type": "tracker_output",
        "tracker_id": tracker["id"],
        "tracker_type": tracker["type"],
        "tracker_run_id": run_id,
        "period_start": _as_str(data.get("period_start"), period_start),
        "period_end": _as_str(data.get("period_end"), period_end),
        "generated_at": data.get("generated_at") or _now(),
        "status": _as_str(data.get("status"), "done"),
        "confidence": _as_float(data.get("confidence"), 0.0),
        "thesis": _as_str(data.get("thesis"), "No source-backed thesis yet."),
        "key_signals": signals,
        "metrics": metrics,
        "recommendations": [
            item if isinstance(item, dict) else {"action": _as_str(item)}
            for item in _as_list(data.get("recommendations"))
        ],
        "open_questions": [
            item if isinstance(item, dict) else {"question": _as_str(item)}
            for item in _as_list(data.get("open_questions"))
        ],
        "missing_sources": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("missing_sources"))
        ],
        "contradictions": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("contradictions"))
        ],
        "watch_items": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("watch_items"))
        ],
        "source_traces": traces,
        "knowledge_updates": [
            item if isinstance(item, dict) else {"text": _as_str(item)}
            for item in _as_list(data.get("knowledge_updates"))
        ],
        "type_sections": data.get("type_sections") if isinstance(data.get("type_sections"), dict) else _type_sections(tracker, traces),
    }
    if data.get("fallback_reason"):
        output["fallback_reason"] = data["fallback_reason"]
    for key in ("generated_by", "result_payload", "claude_error"):
        if key in data:
            output[key] = data[key]
    return output


def build_tracker_prompt(tracker: dict, *, period_start: str, period_end: str) -> str:
    policy = _source_policy_for(tracker["type"], tracker.get("source_policy"))
    priorities = "\n".join(
        f"- {key}: {', '.join(values) if isinstance(values, list) else values}"
        for key, values in policy.items()
    )
    type_rules = {
        "macro": (
            "Cover major events, macro data versus expectation/prior, monetary "
            "policy, market performance, next-week events, and source-backed "
            "sector/theme/ticker strategy suggestions."
        ),
        "industry": (
            "Open with an industry thesis, then cover subsegment/player "
            "dynamics, company spotlights, cross-subsegment links, catalysts, "
            "and next-week risks."
        ),
        "company": (
            "Cover weekly storylines, financial/operating updates versus "
            "consensus and peers, company events, management guidance, special "
            "events, sell-side valuation matrix, and action triggers."
        ),
    }
    zh_rule = (
        "If Simplified Chinese output is requested, use professional restrained "
        "investment-research Chinese; avoid vague filler, awkward direct "
        "translation, and unsupported certainty."
    )
    return f"""You are a public-equity tracker agent.

Tracker: {tracker['display_name']} ({tracker['type']})
Period: {period_start} to {period_end}

Single responsibility:
- Research only this tracker topic.
- Do not use raw context from other trackers.
- Cross-tracker flow must happen through structured tracker outputs and source traces.

Source priority:
{priorities}

Writing and evidence rules:
- Start with the thesis.
- Every datapoint must include source metadata or be marked source_needed.
- Unsupported facts must be null, missing, or source_needed; never invent facts.
- Use concrete values, dates, catalysts, trigger conditions, and source locators.
- Current evidence overrides older accepted lessons when they conflict.
- {zh_rule}

Tracker-specific output requirements:
{type_rules[tracker['type']]}
"""


def _tracker_source_prompt_context(sources: list[dict], *, limit: int = 18_000) -> str:
    if not sources:
        return "No tracker-owned sources are currently assigned."
    parts: list[str] = []
    remaining = limit
    for source in sources:
        if remaining <= 0:
            break
        header = (
            f"Source id: {source.get('id')}\n"
            f"Title: {source.get('title') or source.get('filename')}\n"
            f"Type: {source.get('source_type')} | priority={source.get('priority')} | "
            f"relevance={source.get('relevance')} | status={source.get('extraction_status')}\n"
        )
        if source.get("url"):
            header += f"URL: {source.get('url')}\n"
        if source.get("missing_reason"):
            header += f"Missing state: {source.get('missing_reason')}\n"
        chunks = [
            chunk
            for chunk in _as_list(source.get("chunks"))
            if isinstance(chunk, dict) and _as_str(chunk.get("excerpt"))
        ]
        chunk_lines = []
        for chunk in chunks[:5]:
            chunk_lines.append(
                f"- {chunk.get('locator') or chunk.get('label') or 'source'}: "
                f"{_as_str(chunk.get('excerpt'))[:1200]}"
            )
        body = "\n".join(chunk_lines) or f"- {_as_str(source.get('notes') or source.get('body') or source.get('title'))[:1200]}"
        entry = f"{header}Excerpts:\n{body}\n"
        if len(entry) > remaining:
            entry = entry[:remaining].rstrip()
        parts.append(entry)
        remaining -= len(entry)
    return "\n\n".join(parts)


def _tracker_knowledge_prompt_context(tracker_id: str, *, limit: int = 4_000) -> str:
    knowledge = _read_json(tracker_knowledge_path(tracker_id), {})
    if not isinstance(knowledge, dict):
        return "No accepted tracker lessons yet."
    lessons = [
        item
        for item in _as_list(knowledge.get("accepted_lessons"))
        if isinstance(item, dict) and _as_str(item.get("text"))
    ]
    if not lessons:
        return "No accepted tracker lessons yet."
    text = "\n".join(f"- {item.get('text')}" for item in lessons[-12:])
    return text[:limit]


def _merge_output_trace_previews(output: dict) -> dict:
    if output.get("source_traces"):
        return output
    traces: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for collection_name in ("key_signals", "recommendations", "contradictions"):
        for row in output.get(collection_name) or []:
            if not isinstance(row, dict):
                continue
            for trace in row.get("source_traces") or []:
                if not isinstance(trace, dict):
                    continue
                key = (_as_str(trace.get("source_id")), _as_str(trace.get("locator")))
                if key in seen:
                    continue
                seen.add(key)
                traces.append(trace)
    if traces:
        output["source_traces"] = traces[:12]
    return output


def claude_tracker_output(
    tracker: dict,
    *,
    run_id: str,
    period_start: str,
    period_end: str,
    progress: job_progress.ProgressLog | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[dict | None, str | None]:
    sources = list_tracker_sources(tracker["id"])
    system_prompt = build_tracker_prompt(
        tracker,
        period_start=period_start,
        period_end=period_end,
    )
    user_prompt = f"""Return the structured tracker output for this run.

Required identifiers:
- tracker_id: {tracker['id']}
- tracker_type: {tracker['type']}
- tracker_run_id: {run_id}
- period_start: {period_start}
- period_end: {period_end}

Use only the tracker-owned source context below plus accepted lessons. Every
material claim must cite a source trace with source_id, source_title, locator,
excerpt, confidence, and checked_at. If the source context is insufficient,
mark the gap in missing_sources or open_questions instead of inventing facts.

Accepted tracker lessons:
{_tracker_knowledge_prompt_context(tracker['id'])}

Tracker-owned source context:
{_tracker_source_prompt_context(sources)}
"""
    result, error = claude_runner.run_structured_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=TRACKER_OUTPUT_SCHEMA,
        name=f"stock_tracker_{tracker['type']}",
        timeout_sec=300,
        progress=progress,
        cancel_event=cancel_event,
    )
    if error:
        return None, error
    output = coerce_tracker_output(
        result,
        tracker=tracker,
        run_id=run_id,
        period_start=period_start,
        period_end=period_end,
    )
    output["generated_by"] = "claude_code"
    output["result_payload"] = result
    return _merge_output_trace_previews(output), None


def deterministic_tracker_output(
    tracker_id: str,
    *,
    run_id: str,
    period_start: str,
    period_end: str,
) -> dict:
    tracker = get_tracker(tracker_id)
    if tracker is None:
        raise ValueError(f"Unknown tracker: {tracker_id}")
    return fallback_tracker_output(
        tracker,
        run_id=run_id,
        period_start=period_start,
        period_end=period_end,
        reason="deterministic_phase8_fallback",
    )


def _run_event_key(kind: str, *parts: str) -> str:
    return f"{kind}:" + "/".join(parts)


def _start_cancel_event(key: str) -> threading.Event:
    event = threading.Event()
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[key] = event
    return event


def _get_cancel_event(key: str) -> threading.Event | None:
    with _CANCEL_LOCK:
        return _CANCEL_EVENTS.get(key)


def _clear_cancel_event(key: str, event: threading.Event | None) -> None:
    if event is None:
        return
    with _CANCEL_LOCK:
        if _CANCEL_EVENTS.get(key) is event:
            _CANCEL_EVENTS.pop(key, None)


def _is_cancelled(path: Path, event: threading.Event | None) -> bool:
    if event is not None and event.is_set():
        return True
    return job_progress.scan_progress_state(path).get("terminal_type") == "cancelled"


def _progress_in_flight(path: Path) -> bool:
    state = job_progress.scan_progress_state(path)
    return job_progress.progress_state_in_flight(
        state,
        max_idle_seconds=ACTIVE_JOB_MAX_IDLE_SECONDS,
    )


def _run_metadata(
    *,
    run_id: str,
    tracker_id: str,
    period_id: str,
    period_start: str,
    period_end: str,
    status: str,
) -> dict:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "tracker_id": tracker_id,
        "period_id": period_id,
        "period_start": period_start,
        "period_end": period_end,
        "status": status,
        "created_at": now,
        "updated_at": now,
        "duration_ms": None,
        "token_usage": {},
        "estimated_cost_usd": 0.0,
        "source_count": 0,
        "source_priority_mix": {},
        "source_quality": {},
        "evidence_coverage": 0.0,
        "contradiction_count": 0,
        "missing_source_count": 0,
        "reviewer_score": None,
        "reviewer_scores": {},
        "failure_reason": "",
        "fallback_used": False,
        "preserved_previous_artifact": None,
        "cancellation_reason": "",
    }


def _source_priority_mix(sources: list[dict]) -> dict:
    mix: dict[str, int] = {}
    for source in sources:
        priority = _as_str(source.get("priority"), "unknown")
        mix[priority] = mix.get(priority, 0) + 1
    return mix


def source_quality_score(source: dict | None) -> float:
    if not isinstance(source, dict):
        return SOURCE_PRIORITY_SCORES["unknown"]
    priority = _as_str(source.get("priority"), "unknown")
    source_type = _as_str(source.get("source_type"), "")
    relevance = _as_str(source.get("relevance"), "")
    score = SOURCE_PRIORITY_SCORES.get(priority, SOURCE_PRIORITY_SCORES["unknown"])
    if source_type == "link":
        score += 0.03
    elif source_type == "file":
        score += 0.02
    elif source_type == "note":
        score -= 0.08
    if relevance in {"earnings", "valuation", "management_commentary"}:
        score += 0.04
    elif relevance == "this_week_input":
        score += 0.02
    if source.get("extraction_status") == "missing" or source.get("exists") is False:
        score -= 0.35
    return round(max(0.0, min(1.0, score)), 3)


def _source_quality_summary(sources: list[dict]) -> dict:
    if not sources:
        return {"average": 0.0, "count": 0, "official_or_primary_count": 0}
    scores = [source_quality_score(source) for source in sources]
    return {
        "average": round(sum(scores) / len(scores), 3),
        "count": len(scores),
        "official_or_primary_count": sum(
            1
            for source in sources
            if _as_str(source.get("priority")) in {"official", "company_disclosure", "transcript", "primary_data"}
        ),
    }


def _source_lookup_for_tracker(tracker_id: str | None) -> dict[str, dict]:
    if not tracker_id:
        return {}
    return {
        _as_str(source.get("id")): source
        for source in list_tracker_sources(tracker_id)
        if source.get("id")
    }


def _signal_source_quality(signal: dict) -> float:
    traces = _as_list(signal.get("source_traces"))
    if not traces:
        return 0.0
    source_lookup = _source_lookup_for_tracker(signal.get("source_tracker_id") or signal.get("tracker_id"))
    scores = []
    for trace in traces:
        source = source_lookup.get(_as_str((trace or {}).get("source_id")))
        if source is not None:
            scores.append(source_quality_score(source))
            continue
        confidence = _as_float((trace or {}).get("confidence"), None)
        scores.append(max(0.0, min(1.0, confidence)) if confidence is not None else SOURCE_PRIORITY_SCORES["unknown"])
    return round(sum(scores) / len(scores), 3)


def _signal_rank_score(signal: dict) -> float:
    importance = max(1, min(5, _as_int(signal.get("importance"), 3)))
    confidence = _as_float(signal.get("confidence"), 0.0) or 0.0
    source_quality = _as_float(signal.get("source_quality_score"), 0.0) or 0.0
    return round((importance * 0.5) + (confidence * 2.0) + (source_quality * 2.0), 4)


def _normalize_run_ledger_entry(item: dict) -> dict:
    now = _now()
    job_kind = _as_str(item.get("job_kind"), "stock_tracker")
    run_id = _as_str(item.get("run_id") or item.get("job_id"), "")
    period_id = item.get("period_id")
    tracker_id = item.get("tracker_id")
    ledger_id = _as_str(
        item.get("ledger_id"),
        ":".join(part for part in [job_kind, _as_str(tracker_id), _as_str(period_id), run_id] if part),
    )
    if not ledger_id:
        raise ValueError("Run ledger entry missing id")
    return {
        "schema_version": RUN_LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "job_kind": job_kind,
        "artifact_id": item.get("artifact_id"),
        "tracker_id": tracker_id,
        "run_id": run_id,
        "period_id": period_id,
        "period_start": item.get("period_start"),
        "period_end": item.get("period_end"),
        "status": _as_str(item.get("status"), "unknown"),
        "created_at": item.get("created_at") or now,
        "updated_at": item.get("updated_at") or now,
        "duration_ms": item.get("duration_ms"),
        "token_usage": item.get("token_usage") if isinstance(item.get("token_usage"), dict) else {},
        "estimated_cost_usd": _as_float(item.get("estimated_cost_usd"), 0.0) or 0.0,
        "source_count": max(0, _as_int(item.get("source_count"), 0)),
        "source_priority_mix": item.get("source_priority_mix") if isinstance(item.get("source_priority_mix"), dict) else {},
        "source_quality": item.get("source_quality") if isinstance(item.get("source_quality"), dict) else {},
        "evidence_coverage": _as_float(item.get("evidence_coverage"), 0.0) or 0.0,
        "contradiction_count": max(0, _as_int(item.get("contradiction_count"), 0)),
        "missing_source_count": max(0, _as_int(item.get("missing_source_count"), 0)),
        "reviewer_score": _as_float(item.get("reviewer_score"), None),
        "reviewer_scores": item.get("reviewer_scores") if isinstance(item.get("reviewer_scores"), dict) else {},
        "failure_reason": _as_str(item.get("failure_reason") or item.get("error")),
        "fallback_used": bool(item.get("fallback_used")),
        "preserved_previous_artifact": item.get("preserved_previous_artifact") or item.get("preserved_previous_run_id"),
        "cancellation_reason": _as_str(item.get("cancellation_reason")),
    }


def _upsert_run_ledger_entry(item: dict) -> dict:
    entry = _normalize_run_ledger_entry(item)
    with _LOCK:
        data = _read_json(run_ledger_path(), {"runs": []})
        rows = [
            _normalize_run_ledger_entry(row)
            for row in _as_list(data.get("runs") if isinstance(data, dict) else [])
            if isinstance(row, dict)
        ]
        for index, existing in enumerate(rows):
            if existing["ledger_id"] == entry["ledger_id"]:
                rows[index] = {**existing, **entry}
                break
        else:
            rows.append(entry)
        rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        _write_json(run_ledger_path(), {"schema_version": RUN_LEDGER_SCHEMA_VERSION, "runs": rows})
    return entry


def _tracker_run_ledger_entry(metadata: dict, tracker: dict | None = None) -> dict:
    tracker_id = metadata.get("tracker_id") or (tracker or {}).get("id")
    run_id = metadata.get("run_id")
    return _normalize_run_ledger_entry(
        {
            **metadata,
            "job_kind": "stock_tracker",
            "artifact_id": f"tracker_run:{tracker_id}:{run_id}" if tracker_id and run_id else None,
            "fallback_used": bool(metadata.get("fallback_used") or metadata.get("claude_error")),
            "preserved_previous_artifact": metadata.get("preserved_previous_run_id"),
            "failure_reason": metadata.get("error"),
            "cancellation_reason": metadata.get("cancellation_reason"),
        }
    )


def _upsert_job_ledger_entry(
    *,
    job_kind: str,
    period_id: str,
    status: str,
    artifact_id: str,
    started_at: float | None = None,
    error: str | None = None,
    cancellation_reason: str | None = None,
    source_count: int = 0,
) -> dict:
    existing = {}
    ledger_id = f"{job_kind}:{period_id}"
    data = _read_json(run_ledger_path(), {"runs": []})
    rows = data.get("runs") if isinstance(data, dict) else []
    for row in _as_list(rows):
        if isinstance(row, dict) and row.get("ledger_id") == ledger_id:
            existing = row
            break
    now = _now()
    return _upsert_run_ledger_entry(
        {
            **existing,
            "ledger_id": ledger_id,
            "job_kind": job_kind,
            "artifact_id": artifact_id,
            "run_id": period_id,
            "period_id": period_id,
            "status": status,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "duration_ms": int((time.monotonic() - started_at) * 1000) if started_at is not None else existing.get("duration_ms"),
            "source_count": source_count or existing.get("source_count") or 0,
            "failure_reason": error or "",
            "cancellation_reason": cancellation_reason or "",
        }
    )


def list_run_ledger() -> list[dict]:
    data = _read_json(run_ledger_path(), {"runs": []})
    rows_by_id = {
        row["ledger_id"]: row
        for row in (
            _normalize_run_ledger_entry(item)
            for item in _as_list(data.get("runs") if isinstance(data, dict) else [])
            if isinstance(item, dict)
        )
    }
    for tracker in list_trackers(include_archived=True):
        for run in list_tracker_runs(tracker["id"]):
            entry = _tracker_run_ledger_entry(run, tracker)
            rows_by_id[entry["ledger_id"]] = {**rows_by_id.get(entry["ledger_id"], {}), **entry}
    rows = list(rows_by_id.values())
    rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
    return rows


def _write_tracker_run_artifacts(
    tracker: dict,
    run_id: str,
    output: dict,
    *,
    started_at: float,
    status: str = "done",
) -> dict:
    sources = list_tracker_sources(tracker["id"])
    metadata = _read_json(
        tracker_run_metadata_path(tracker["id"], run_id),
        _run_metadata(
            run_id=run_id,
            tracker_id=tracker["id"],
            period_id=output.get("period_id") or _default_period_range()[0],
            period_start=output.get("period_start"),
            period_end=output.get("period_end"),
            status=status,
        ),
    )
    metadata.update(
        {
            "status": status,
            "updated_at": _now(),
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "source_count": len(sources),
            "source_priority_mix": _source_priority_mix(sources),
            "source_quality": _source_quality_summary(sources),
            "evidence_coverage": 1.0 if output.get("source_traces") else 0.0,
            "contradiction_count": len(output.get("contradictions") or []),
            "missing_source_count": len(output.get("missing_sources") or []),
        }
    )
    _write_json(tracker_run_output_path(tracker["id"], run_id), output)
    _write_json(tracker_run_source_manifest_path(tracker["id"], run_id), {"sources": sources})
    _write_text(tracker_run_report_path(tracker["id"], run_id), tracker_output_markdown(output, tracker))
    _write_json(tracker_run_metadata_path(tracker["id"], run_id), metadata)
    _upsert_run_ledger_entry(_tracker_run_ledger_entry(metadata, tracker))
    return metadata


def _write_tracker_run_metadata(tracker_id: str, run_id: str, patch: dict) -> dict:
    metadata = {
        **_read_json(tracker_run_metadata_path(tracker_id, run_id), {}),
        **(patch or {}),
        "updated_at": patch.get("updated_at") if isinstance(patch, dict) and patch.get("updated_at") else _now(),
    }
    _write_json(tracker_run_metadata_path(tracker_id, run_id), metadata)
    _upsert_run_ledger_entry(_tracker_run_ledger_entry(metadata, get_tracker(tracker_id)))
    return metadata


def tracker_output_markdown(output: dict, tracker: dict) -> str:
    signals = "\n".join(
        f"- {s.get('observation')} ({s.get('direction')}, importance {s.get('importance')})"
        for s in output.get("key_signals") or []
    ) or "- No signals."
    missing = "\n".join(
        f"- {m.get('description') or m.get('id')}"
        for m in output.get("missing_sources") or []
    ) or "- None."
    return f"""# {tracker.get('display_name')} Tracker Report

Period: {output.get('period_start')} to {output.get('period_end')}

## Thesis

{output.get('thesis')}

## Ranked Signals

{signals}

## Missing Sources

{missing}
"""


def _latest_successful_run_id(tracker_id: str) -> str | None:
    runs = list_tracker_runs(tracker_id)
    for run in runs:
        if run.get("status") == "done" and tracker_run_output_path(tracker_id, run["run_id"]).exists():
            return run["run_id"]
    return None


def _update_tracker_after_success(tracker: dict, run_id: str, output: dict) -> None:
    last = output.get("generated_at") or _now()
    last_dt = _parse_dt(last) or datetime.now(timezone.utc)
    next_due = last_dt + timedelta(days=max(1, _as_int((tracker.get("freshness_policy") or {}).get("stale_after_days"), 7)))
    tracker["freshness_policy"] = _freshness_policy(tracker.get("freshness_policy"))
    tracker["freshness_policy"]["last_successful_run"] = last
    tracker["freshness_policy"]["next_due_run"] = next_due.isoformat()
    tracker["latest_run_id"] = run_id
    tracker["latest_thesis"] = output.get("thesis")
    tracker["latest_confidence"] = output.get("confidence")
    tracker["current_run"] = None
    tracker["updated_at"] = _now()
    _write_json(tracker_config_path(tracker["id"]), tracker)


def _update_tracker_current_run(tracker_id: str, run_info: dict | None) -> None:
    tracker = get_tracker(tracker_id)
    if tracker is None:
        return
    tracker["current_run"] = run_info
    tracker["updated_at"] = _now()
    _write_json(tracker_config_path(tracker_id), _normalize_tracker(tracker, existing=tracker))


def _register_run_review_items(tracker: dict, run_id: str, output: dict) -> None:
    for item in output.get("missing_sources") or []:
        _upsert_review_item(
            {
                "id": f"missing:{tracker['id']}:{run_id}:{item.get('id') or _slug(item.get('description', 'missing'))}",
                "item_type": "missing_source",
                "status": "open",
                "title": item.get("description") or "Missing source",
                "artifact_id": f"tracker_run:{tracker['id']}:{run_id}",
                "tracker_id": tracker["id"],
                "run_id": run_id,
                "severity": item.get("priority") or "medium",
                "source_refs": [],
            }
        )
    for item in output.get("contradictions") or []:
        _upsert_review_item(
            {
                "id": f"contradiction:{tracker['id']}:{run_id}:{item.get('id') or _slug(item.get('description', 'contradiction'))}",
                "item_type": "contradiction",
                "status": "open",
                "title": item.get("description") or "Contradiction",
                "artifact_id": f"tracker_run:{tracker['id']}:{run_id}",
                "tracker_id": tracker["id"],
                "run_id": run_id,
                "severity": item.get("severity") or "medium",
                "source_refs": item.get("source_traces") or [],
            }
        )
    for item in output.get("knowledge_updates") or []:
        _upsert_review_item(
            {
                "id": f"knowledge:{tracker['id']}:{run_id}:{item.get('id') or _slug(item.get('text', 'knowledge'))}",
                "item_type": "knowledge_update",
                "status": _normalize_review_status(item.get("review_status")),
                "title": item.get("text") or "Knowledge update",
                "artifact_id": f"tracker_run:{tracker['id']}:{run_id}",
                "tracker_id": tracker["id"],
                "run_id": run_id,
                "severity": "low",
                "source_refs": item.get("source_traces") or [],
            }
        )


def _register_job_review_item(
    *,
    job_kind: str,
    job_status: str,
    title: str,
    artifact_id: str,
    tracker_id: str | None = None,
    run_id: str | None = None,
    period_id: str | None = None,
    error: str | None = None,
) -> None:
    severity = "high" if job_status in {"error", "recovered"} else "medium"
    item_type = "cancelled_job" if job_status == "cancelled" else "failed_job"
    item_key = ":".join(
        part
        for part in [job_kind, job_status, tracker_id, run_id, period_id]
        if part
    )
    _upsert_review_item(
        {
            "id": f"job:{_slug(item_key)}",
            "item_type": item_type,
            "status": "open",
            "title": title,
            "artifact_id": artifact_id,
            "tracker_id": tracker_id,
            "run_id": run_id,
            "period_id": period_id,
            "job_kind": job_kind,
            "job_status": job_status,
            "severity": severity,
            "rationale": error or "",
            "error": error or "",
            "source_refs": [],
        }
    )


def _register_tracker_run_product(tracker: dict, run_id: str, output: dict, metadata: dict) -> None:
    register_work_product(
        {
            "artifact_id": f"tracker_run:{tracker['id']}:{run_id}",
            "artifact_type": "tracker_report",
            "title": f"{tracker['display_name']} tracker report",
            "status": "needs_review" if output.get("missing_sources") else "draft",
            "version": 1,
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "generated_by": "stock_research_tracker",
            "reviewer": None,
            "source_refs": output.get("source_traces") or [],
            "source_trace_count": len(output.get("source_traces") or []),
            "confidence": output.get("confidence"),
            "review_state": "open",
            "supersedes": None,
            "superseded_by": None,
            "pinned": False,
            "archived": False,
            "export_paths": {
                "json": str(tracker_run_output_path(tracker["id"], run_id)),
                "markdown": str(tracker_run_report_path(tracker["id"], run_id)),
                "source_manifest": str(tracker_run_source_manifest_path(tracker["id"], run_id)),
            },
            "notes": "",
            "tracker_id": tracker["id"],
            "run_id": run_id,
            "period_start": output.get("period_start"),
            "period_end": output.get("period_end"),
        }
    )


def _run_tracker_job(
    tracker_id: str,
    run_id: str,
    period_id: str,
    period_start: str,
    period_end: str,
    *,
    use_claude: bool = True,
) -> None:
    key = _run_event_key("tracker", tracker_id, run_id)
    event = _start_cancel_event(key)
    progress_path = tracker_progress_path(tracker_id, run_id)
    progress = job_progress.ProgressLog(progress_path)
    started = time.monotonic()
    progress.emit(
        "job_init",
        kind="stock_tracker",
        title="Stock tracker run",
        subtitle=tracker_id,
        tracker_id=tracker_id,
        run_id=run_id,
        period_id=period_id,
    )
    try:
        tracker = get_tracker(tracker_id)
        if tracker is None:
            raise ValueError(f"Unknown tracker: {tracker_id}")
        progress.emit("stage", stage="sources", message="Reading tracker-owned sources")
        if _is_cancelled(progress_path, event):
            _write_tracker_run_metadata(tracker_id, run_id, {
                "status": "cancelled",
                "cancellation_reason": "Tracker run cancelled",
            })
            _update_tracker_current_run(tracker_id, None)
            _register_job_review_item(
                job_kind="stock_tracker",
                job_status="cancelled",
                title=f"Tracker run cancelled: {tracker.get('display_name') or tracker_id}",
                artifact_id=f"tracker_run:{tracker_id}:{run_id}",
                tracker_id=tracker_id,
                run_id=run_id,
            )
            return
        if use_claude:
            output, claude_error = claude_tracker_output(
                tracker,
                run_id=run_id,
                period_start=period_start,
                period_end=period_end,
                progress=progress,
                cancel_event=event,
            )
            if claude_error:
                raise RuntimeError(claude_error)
            if output is None:
                raise RuntimeError("Claude returned no tracker output")
        else:
            output = deterministic_tracker_output(
                tracker_id,
                run_id=run_id,
                period_start=period_start,
                period_end=period_end,
            )
        output["period_id"] = period_id
        if _is_cancelled(progress_path, event):
            job_progress.cancel_progress_file(
                progress_path,
                reason="Tracker run cancelled",
                kind="stock_tracker",
                tracker_id=tracker_id,
                run_id=run_id,
            )
            _write_tracker_run_metadata(tracker_id, run_id, {
                "status": "cancelled",
                "cancellation_reason": "Tracker run cancelled",
            })
            _update_tracker_current_run(tracker_id, None)
            _register_job_review_item(
                job_kind="stock_tracker",
                job_status="cancelled",
                title=f"Tracker run cancelled: {tracker.get('display_name') or tracker_id}",
                artifact_id=f"tracker_run:{tracker_id}:{run_id}",
                tracker_id=tracker_id,
                run_id=run_id,
            )
            return
        progress.emit("stage", stage="write", message="Writing tracker artifacts")
        metadata = _write_tracker_run_artifacts(tracker, run_id, output, started_at=started)
        _update_tracker_after_success(tracker, run_id, output)
        _register_tracker_run_product(tracker, run_id, output, metadata)
        _register_run_review_items(tracker, run_id, output)
        progress.emit(
            "done",
            tracker_id=tracker_id,
            run_id=run_id,
            period_id=period_id,
            thesis=output.get("thesis"),
        )
    except Exception as exc:  # noqa: BLE001
        if _is_cancelled(progress_path, event):
            job_progress.cancel_progress_file(
                progress_path,
                reason="Tracker run cancelled",
                kind="stock_tracker",
                tracker_id=tracker_id,
                run_id=run_id,
            )
            _write_tracker_run_metadata(tracker_id, run_id, {
                "status": "cancelled",
                "cancellation_reason": "Tracker run cancelled",
            })
            _update_tracker_current_run(tracker_id, None)
            _register_job_review_item(
                job_kind="stock_tracker",
                job_status="cancelled",
                title=f"Tracker run cancelled: {tracker_id}",
                artifact_id=f"tracker_run:{tracker_id}:{run_id}",
                tracker_id=tracker_id,
                run_id=run_id,
            )
            return
        tracker = get_tracker(tracker_id)
        latest = _latest_successful_run_id(tracker_id)
        if tracker is not None and latest is None:
            output = fallback_tracker_output(
                tracker,
                run_id=run_id,
                period_start=period_start,
                period_end=period_end,
                reason=f"first_run_fallback_after_error: {type(exc).__name__}: {exc}",
            )
            output["period_id"] = period_id
            output["claude_error"] = f"{type(exc).__name__}: {exc}"
            metadata = _write_tracker_run_artifacts(tracker, run_id, output, started_at=started)
            metadata["fallback_used"] = True
            metadata["failure_reason"] = f"{type(exc).__name__}: {exc}"
            _write_tracker_run_metadata(tracker_id, run_id, metadata)
            _update_tracker_after_success(tracker, run_id, output)
            _register_tracker_run_product(tracker, run_id, output, metadata)
            _register_run_review_items(tracker, run_id, output)
            progress.emit(
                "done",
                tracker_id=tracker_id,
                run_id=run_id,
                period_id=period_id,
                fallback=True,
                error=str(exc),
            )
        else:
            _write_tracker_run_metadata(
                tracker_id,
                run_id,
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                    "preserved_previous_run_id": latest,
                    "preserved_previous_artifact": latest,
                },
            )
            _update_tracker_current_run(tracker_id, None)
            _register_job_review_item(
                job_kind="stock_tracker",
                job_status="error",
                title=f"Tracker run failed: {tracker.get('display_name') if tracker else tracker_id}",
                artifact_id=f"tracker_run:{tracker_id}:{run_id}",
                tracker_id=tracker_id,
                run_id=run_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            progress.emit("error", error=f"Tracker run failed: {type(exc).__name__}: {exc}")
    finally:
        _clear_cancel_event(key, event)


def start_tracker_run(
    tracker_id: str,
    *,
    period_id: str | None = None,
    force: bool = False,
    use_claude: bool = True,
) -> dict:
    with _LOCK:
        tracker = get_tracker(tracker_id)
        if tracker is None:
            raise ValueError(f"Unknown tracker: {tracker_id}")
        if tracker.get("status") != "active":
            raise ValueError(f"Tracker is not active: {tracker_id}")
        current = tracker.get("current_run") or {}
        current_run_id = current.get("run_id")
        if current_run_id and _progress_in_flight(tracker_progress_path(tracker_id, current_run_id)) and not force:
            return {
                "status": "already_running",
                "tracker_id": tracker_id,
                "run_id": current_run_id,
                "stream_url": f"/api/stock-research/trackers/{tracker_id}/runs/{current_run_id}/stream",
                "log_url": f"/api/jobs/log?path=stock_tracker:{tracker_id}/{current_run_id}",
            }
        period_id, period_start, period_end = _default_period_range(period_id)
        run_id = f"{period_id}-{uuid.uuid4().hex[:8]}"
        metadata = _run_metadata(
            run_id=run_id,
            tracker_id=tracker_id,
            period_id=period_id,
            period_start=period_start,
            period_end=period_end,
            status="queued",
        )
        _write_json(tracker_run_metadata_path(tracker_id, run_id), metadata)
        _upsert_run_ledger_entry(_tracker_run_ledger_entry(metadata, tracker))
        _update_tracker_current_run(
            tracker_id,
            {
                "run_id": run_id,
                "period_id": period_id,
                "status": "queued",
                "started_at": metadata["created_at"],
            },
        )
    threading.Thread(
        target=_run_tracker_job,
        args=(tracker_id, run_id, period_id, period_start, period_end),
        kwargs={"use_claude": use_claude},
        name=f"stock-tracker:{tracker_id}:{run_id}",
        daemon=True,
    ).start()
    return {
        "status": "queued",
        "tracker_id": tracker_id,
        "run_id": run_id,
        "period_id": period_id,
        "stream_url": f"/api/stock-research/trackers/{tracker_id}/runs/{run_id}/stream",
        "log_url": f"/api/jobs/log?path=stock_tracker:{tracker_id}/{run_id}",
    }


def run_tracker_now(tracker_id: str, *, period_id: str | None = None) -> dict:
    """Synchronous deterministic runner for unit tests and maintenance scripts."""
    period_id, period_start, period_end = _default_period_range(period_id)
    run_id = f"{period_id}-{uuid.uuid4().hex[:8]}"
    metadata = _run_metadata(
        run_id=run_id,
        tracker_id=tracker_id,
        period_id=period_id,
        period_start=period_start,
        period_end=period_end,
        status="running",
    )
    _write_json(tracker_run_metadata_path(tracker_id, run_id), metadata)
    _upsert_run_ledger_entry(_tracker_run_ledger_entry(metadata, get_tracker(tracker_id)))
    _run_tracker_job(
        tracker_id,
        run_id,
        period_id,
        period_start,
        period_end,
        use_claude=False,
    )
    return _read_json(tracker_run_metadata_path(tracker_id, run_id), {})


def start_selected_tracker_runs(
    tracker_ids: list[str],
    *,
    retry_failed: bool = True,
    period_id: str | None = None,
) -> dict:
    launches = []
    errors = []
    for tracker_id in tracker_ids:
        try:
            launches.append(start_tracker_run(tracker_id, period_id=period_id))
        except ValueError as exc:
            if retry_failed:
                errors.append({"tracker_id": tracker_id, "error": str(exc)})
            else:
                errors.append({"tracker_id": tracker_id, "error": str(exc)})
    return {"launched": launches, "errors": errors}


def start_due_tracker_runs(*, period_id: str | None = None) -> dict:
    due_ids = [
        tracker["id"]
        for tracker in list_trackers()
        if tracker.get("status") == "active" and tracker.get("is_due")
    ]
    return {
        "due_tracker_ids": due_ids,
        **start_selected_tracker_runs(due_ids, period_id=period_id),
    }


def cancel_tracker_run(tracker_id: str, run_id: str) -> dict:
    key = _run_event_key("tracker", tracker_id, run_id)
    event = _get_cancel_event(key)
    path = tracker_progress_path(tracker_id, run_id)
    if event is not None:
        event.set()
    state = job_progress.cancel_progress_file(
        path,
        reason="cancelled by user",
        kind="stock_tracker",
        tracker_id=tracker_id,
        run_id=run_id,
    )
    _write_tracker_run_metadata(
        tracker_id,
        run_id,
        {"status": "cancelled", "cancellation_reason": "cancelled by user"},
    )
    _update_tracker_current_run(tracker_id, None)
    tracker = get_tracker(tracker_id)
    _register_job_review_item(
        job_kind="stock_tracker",
        job_status="cancelled",
        title=f"Tracker run cancelled: {(tracker or {}).get('display_name') or tracker_id}",
        artifact_id=f"tracker_run:{tracker_id}:{run_id}",
        tracker_id=tracker_id,
        run_id=run_id,
    )
    return {"cancelled": True, "state": state, "tracker_id": tracker_id, "run_id": run_id}


def retry_tracker_run(
    tracker_id: str,
    run_id: str,
    *,
    use_claude: bool = True,
) -> dict:
    metadata = _read_json(tracker_run_metadata_path(tracker_id, run_id), {})
    if not metadata:
        raise ValueError(f"Unknown run: {tracker_id}/{run_id}")
    if _progress_in_flight(tracker_progress_path(tracker_id, run_id)):
        return {
            "status": "already_running",
            "tracker_id": tracker_id,
            "run_id": run_id,
            "stream_url": f"/api/stock-research/trackers/{tracker_id}/runs/{run_id}/stream",
            "log_url": f"/api/jobs/log?path=stock_tracker:{tracker_id}/{run_id}",
        }
    if metadata.get("status") not in {"error", "cancelled", "recovered"}:
        raise ValueError("Only failed, cancelled, or recovered tracker runs can be retried")
    return start_tracker_run(
        tracker_id,
        period_id=metadata.get("period_id"),
        force=True,
        use_claude=use_claude,
    )


def list_tracker_runs(tracker_id: str) -> list[dict]:
    root = tracker_runs_dir(tracker_id)
    if not root.exists():
        return []
    runs = []
    for path in root.glob("*/run.json"):
        data = _read_json(path, {})
        if isinstance(data, dict) and data.get("run_id"):
            output_path = tracker_run_output_path(tracker_id, data["run_id"])
            if output_path.exists():
                output = _read_json(output_path, {})
                data["thesis"] = output.get("thesis")
                data["confidence"] = output.get("confidence")
                data["source_trace_count"] = len(output.get("source_traces") or [])
                data["source_traces"] = (output.get("source_traces") or [])[:3]
                data["knowledge_updates"] = output.get("knowledge_updates") or []
                data["key_signals"] = output.get("key_signals") or []
                data["open_questions"] = output.get("open_questions") or []
                data["missing_sources"] = output.get("missing_sources") or []
                report_path = tracker_run_report_path(tracker_id, data["run_id"])
                if report_path.exists():
                    data["report_markdown"] = report_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )[:12_000]
            data["progress_state"] = job_progress.scan_progress_state(
                tracker_progress_path(tracker_id, data["run_id"])
            )
            runs.append(data)
    runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return runs


def get_tracker_run_output(tracker_id: str, run_id: str) -> dict | None:
    path = tracker_run_output_path(tracker_id, run_id)
    if not path.exists():
        return None
    data = _read_json(path, {})
    return data if isinstance(data, dict) else None


def latest_tracker_outputs() -> list[dict]:
    outputs = []
    for tracker in list_trackers():
        run_id = tracker.get("latest_run_id")
        if not run_id:
            continue
        output = get_tracker_run_output(tracker["id"], run_id)
        if output:
            outputs.append(output)
    return outputs


def coerce_weekly_aggregate(raw: Any, *, period_id: str, period_start: str, period_end: str) -> dict:
    data = raw if isinstance(raw, dict) else {}
    modules = data.get("modules") if isinstance(data.get("modules"), dict) else {}
    for key in ("macro", "industry", "company", "cross_tracker", "watchlist"):
        modules.setdefault(key, [])
    aggregate = {
        "schema_version": WEEKLY_AGGREGATE_SCHEMA_VERSION,
        "artifact_type": "weekly_aggregate",
        "period_id": period_id,
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": data.get("generated_at") or _now(),
        "included_tracker_run_ids": _string_list(data.get("included_tracker_run_ids")),
        "excluded_tracker_warnings": [
            item if isinstance(item, dict) else {"warning": _as_str(item)}
            for item in _as_list(data.get("excluded_tracker_warnings"))
        ],
        "modules": modules,
        "ranked_signals": [
            item if isinstance(item, dict) else {"observation": _as_str(item)}
            for item in _as_list(data.get("ranked_signals"))
        ],
        "deduped_claims": [
            item if isinstance(item, dict) else {"claim": _as_str(item)}
            for item in _as_list(data.get("deduped_claims"))
        ],
        "contradictions": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("contradictions"))
        ],
        "missing_source_warnings": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("missing_source_warnings"))
        ],
        "event_calendar": [
            item if isinstance(item, dict) else {"event": _as_str(item)}
            for item in _as_list(data.get("event_calendar"))
        ],
        "trigger_conditions": _as_list(data.get("trigger_conditions")),
        "markdown": _as_str(data.get("markdown")),
        "html_blocks": _as_list(data.get("html_blocks")),
        "visual_report_metadata": data.get("visual_report_metadata") if isinstance(data.get("visual_report_metadata"), dict) else {},
    }
    return aggregate


def build_weekly_aggregate(period_id: str | None = None) -> dict:
    period_id, period_start, period_end = _default_period_range(period_id)
    outputs = latest_tracker_outputs()
    trackers_by_id = {t["id"]: t for t in list_trackers()}
    included_ids = []
    modules = {"macro": [], "industry": [], "company": [], "cross_tracker": [], "watchlist": []}
    signals = []
    missing = []
    contradictions = []
    claim_seen: dict[str, dict] = {}
    for output in outputs:
        tracker_id = output.get("tracker_id")
        run_id = output.get("tracker_run_id")
        if tracker_id and run_id:
            included_ids.append(f"{tracker_id}:{run_id}")
        module_key = output.get("tracker_type")
        if module_key in modules:
            modules[module_key].append(
                {
                    "tracker_id": tracker_id,
                    "tracker_run_id": run_id,
                    "thesis": output.get("thesis"),
                    "confidence": output.get("confidence"),
                    "source_traces": output.get("source_traces") or [],
                }
            )
        for signal in output.get("key_signals") or []:
            row = copy.deepcopy(signal)
            row["source_tracker_id"] = tracker_id
            row["tracker_run_id"] = run_id
            row.setdefault("timestamp", output.get("generated_at"))
            row.setdefault("confidence", output.get("confidence"))
            row["source_traces"] = row.get("source_traces") or output.get("source_traces") or []
            row["source_quality_score"] = _signal_source_quality(row)
            row["rank_score"] = _signal_rank_score(row)
            signals.append(row)
            claim_key = _slug(row.get("observation", "claim"))
            existing = claim_seen.setdefault(
                claim_key,
                {
                    "claim": row.get("observation"),
                    "contributing_tracker_refs": [],
                    "source_traces": [],
                },
            )
            existing["contributing_tracker_refs"].append(
                {"tracker_id": tracker_id, "tracker_run_id": run_id}
            )
            existing["source_traces"].extend(row.get("source_traces") or [])
        missing.extend(output.get("missing_sources") or [])
        contradictions.extend(output.get("contradictions") or [])
    active_trackers = [t for t in trackers_by_id.values() if t.get("status") == "active"]
    covered_ids = {out.get("tracker_id") for out in outputs}
    excluded = [
        {
            "tracker_id": tracker["id"],
            "warning": "No latest tracker output for this period.",
            "stale": tracker.get("is_stale"),
        }
        for tracker in active_trackers
        if tracker["id"] not in covered_ids
    ]
    signals.sort(key=lambda s: (_as_float(s.get("rank_score"), 0.0) or 0.0, str(s.get("observation"))))
    signals = list(reversed(signals))
    modules["watchlist"] = [
        {
            "tracker_id": output.get("tracker_id"),
            "tracker_run_id": output.get("tracker_run_id"),
            "items": output.get("watch_items") or [],
        }
        for output in outputs
        if output.get("watch_items")
    ]
    modules["cross_tracker"] = _cross_tracker_links(signals)
    markdown = aggregate_markdown(
        period_start=period_start,
        period_end=period_end,
        signals=signals,
        excluded=excluded,
    )
    aggregate = coerce_weekly_aggregate(
        {
            "included_tracker_run_ids": included_ids,
            "excluded_tracker_warnings": excluded,
            "modules": modules,
            "ranked_signals": signals,
            "deduped_claims": list(claim_seen.values()),
            "contradictions": contradictions,
            "missing_source_warnings": missing,
            "event_calendar": [],
            "trigger_conditions": [],
            "markdown": markdown,
            "html_blocks": [
                {"kind": "markdown", "body": markdown},
            ],
            "visual_report_metadata": {"ready_for_infographic": False},
        },
        period_id=period_id,
        period_start=period_start,
        period_end=period_end,
    )
    return aggregate


def _cross_tracker_links(signals: list[dict]) -> list[dict]:
    links = []
    for left_index, left in enumerate(signals):
        left_themes = set(_string_list(left.get("affected_themes")) + _string_list(left.get("affected_tickers")))
        if not left_themes:
            continue
        for right in signals[left_index + 1:]:
            right_themes = set(_string_list(right.get("affected_themes")) + _string_list(right.get("affected_tickers")))
            overlap = sorted(left_themes & right_themes)
            if not overlap:
                continue
            links.append(
                {
                    "id": f"link-{len(links) + 1}",
                    "shared_context": overlap,
                    "source_tracker_refs": [
                        {
                            "tracker_id": left.get("source_tracker_id"),
                            "tracker_run_id": left.get("tracker_run_id"),
                        },
                        {
                            "tracker_id": right.get("source_tracker_id"),
                            "tracker_run_id": right.get("tracker_run_id"),
                        },
                    ],
                    "source_traces": (left.get("source_traces") or [])[:1] + (right.get("source_traces") or [])[:1],
                }
            )
    return links


def aggregate_markdown(*, period_start: str, period_end: str, signals: list[dict], excluded: list[dict]) -> str:
    signal_lines = "\n".join(
        f"- {s.get('observation')} ({s.get('source_tracker_id')} / {s.get('tracker_run_id')})"
        for s in signals[:12]
    ) or "- No tracker signals yet."
    excluded_lines = "\n".join(
        f"- {w.get('tracker_id')}: {w.get('warning')}"
        for w in excluded
    ) or "- None."
    return f"""# Stock Research Weekly Aggregate

Period: {period_start} to {period_end}

## Ranked Signals

{signal_lines}

## Stale Or Excluded Trackers

{excluded_lines}
"""


def _write_weekly_aggregate(aggregate: dict) -> None:
    period_id = aggregate["period_id"]
    _write_json(aggregate_json_path(period_id), aggregate)
    _write_text(aggregate_markdown_path(period_id), aggregate.get("markdown") or "")
    register_work_product(
        {
            "artifact_id": f"weekly_aggregate:{period_id}",
            "artifact_type": "weekly_aggregate",
            "title": f"Weekly aggregate {period_id}",
            "status": "needs_review",
            "version": 1,
            "created_at": aggregate.get("generated_at"),
            "updated_at": aggregate.get("generated_at"),
            "generated_by": "stock_research_aggregate",
            "reviewer": None,
            "source_refs": aggregate.get("ranked_signals") or [],
            "source_trace_count": sum(len(s.get("source_traces") or []) for s in aggregate.get("ranked_signals") or []),
            "confidence": _aggregate_confidence(aggregate),
            "review_state": "open",
            "supersedes": None,
            "superseded_by": None,
            "pinned": False,
            "archived": False,
            "export_paths": {
                "json": str(aggregate_json_path(period_id)),
                "markdown": str(aggregate_markdown_path(period_id)),
            },
            "notes": "",
            "period_id": period_id,
        }
    )
    for warning in aggregate.get("excluded_tracker_warnings") or []:
        _upsert_review_item(
            {
                "id": f"stale:{period_id}:{warning.get('tracker_id')}",
                "item_type": "stale_tracker",
                "status": "open",
                "title": warning.get("warning") or "Stale tracker",
                "artifact_id": f"weekly_aggregate:{period_id}",
                "tracker_id": warning.get("tracker_id"),
                "severity": "medium",
                "source_refs": [],
            }
        )
    for claim in aggregate.get("deduped_claims") or []:
        refs = claim.get("contributing_tracker_refs") or []
        if not claim.get("ambiguous") and len(refs) < 2:
            continue
        title = claim.get("claim") or claim.get("observation") or "Ambiguous aggregate claim"
        _upsert_review_item(
            {
                "id": f"ambiguous-claim:{period_id}:{_slug(title, fallback='claim')}",
                "item_type": "ambiguous_claim",
                "status": "open",
                "title": title,
                "artifact_id": f"weekly_aggregate:{period_id}",
                "period_id": period_id,
                "severity": "medium",
                "source_refs": refs,
            }
        )


def _aggregate_confidence(aggregate: dict) -> float:
    signals = aggregate.get("ranked_signals") or []
    if not signals:
        return 0.0
    values = [_as_float(s.get("confidence"), 0.0) or 0.0 for s in signals]
    return round(sum(values) / len(values), 3)


def _run_aggregate_job(period_id: str) -> None:
    key = _run_event_key("aggregate", period_id)
    event = _start_cancel_event(key)
    path = aggregate_progress_path(period_id)
    progress = job_progress.ProgressLog(path)
    started = time.monotonic()
    progress.emit(
        "job_init",
        kind="stock_aggregate",
        title="Stock Research weekly aggregate",
        subtitle=period_id,
        period_id=period_id,
    )
    try:
        progress.emit("stage", stage="collect", message="Collecting structured tracker outputs")
        if _is_cancelled(path, event):
            job_progress.cancel_progress_file(
                path,
                reason="Aggregate cancelled",
                kind="stock_aggregate",
                period_id=period_id,
            )
            _register_job_review_item(
                job_kind="stock_aggregate",
                job_status="cancelled",
                title=f"Weekly aggregate cancelled: {period_id}",
                artifact_id=f"weekly_aggregate:{period_id}",
                period_id=period_id,
            )
            _upsert_job_ledger_entry(
                job_kind="stock_aggregate",
                period_id=period_id,
                status="cancelled",
                artifact_id=f"weekly_aggregate:{period_id}",
                started_at=started,
                cancellation_reason="Aggregate cancelled",
            )
            return
        aggregate = build_weekly_aggregate(period_id)
        progress.emit("stage", stage="write", message="Writing aggregate artifacts")
        if _is_cancelled(path, event):
            job_progress.cancel_progress_file(
                path,
                reason="Aggregate cancelled",
                kind="stock_aggregate",
                period_id=period_id,
            )
            _register_job_review_item(
                job_kind="stock_aggregate",
                job_status="cancelled",
                title=f"Weekly aggregate cancelled: {period_id}",
                artifact_id=f"weekly_aggregate:{period_id}",
                period_id=period_id,
            )
            _upsert_job_ledger_entry(
                job_kind="stock_aggregate",
                period_id=period_id,
                status="cancelled",
                artifact_id=f"weekly_aggregate:{period_id}",
                started_at=started,
                cancellation_reason="Aggregate cancelled",
            )
            return
        _write_weekly_aggregate(aggregate)
        _upsert_job_ledger_entry(
            job_kind="stock_aggregate",
            period_id=period_id,
            status="done",
            artifact_id=f"weekly_aggregate:{period_id}",
            started_at=started,
            source_count=sum(
                len(signal.get("source_traces") or [])
                for signal in aggregate.get("ranked_signals") or []
            ),
        )
        progress.emit("done", period_id=period_id, signal_count=len(aggregate.get("ranked_signals") or []))
    except Exception as exc:  # noqa: BLE001
        _register_job_review_item(
            job_kind="stock_aggregate",
            job_status="error",
            title=f"Weekly aggregate failed: {period_id}",
            artifact_id=f"weekly_aggregate:{period_id}",
            period_id=period_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        _upsert_job_ledger_entry(
            job_kind="stock_aggregate",
            period_id=period_id,
            status="error",
            artifact_id=f"weekly_aggregate:{period_id}",
            started_at=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        progress.emit("error", error=f"Aggregate failed: {type(exc).__name__}: {exc}")
    finally:
        _clear_cancel_event(key, event)


def start_aggregate_job(period_id: str | None = None, *, force: bool = False) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    path = aggregate_progress_path(period_id)
    if _progress_in_flight(path) and not force:
        return {
            "status": "already_running",
            "period_id": period_id,
            "stream_url": f"/api/stock-research/aggregates/{period_id}/stream",
            "log_url": f"/api/jobs/log?path=stock_aggregate:{period_id}",
        }
    _upsert_job_ledger_entry(
        job_kind="stock_aggregate",
        period_id=period_id,
        status="queued",
        artifact_id=f"weekly_aggregate:{period_id}",
    )
    threading.Thread(
        target=_run_aggregate_job,
        args=(period_id,),
        name=f"stock-aggregate:{period_id}",
        daemon=True,
    ).start()
    return {
        "status": "queued",
        "period_id": period_id,
        "stream_url": f"/api/stock-research/aggregates/{period_id}/stream",
        "log_url": f"/api/jobs/log?path=stock_aggregate:{period_id}",
    }


def cancel_aggregate_job(period_id: str) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    key = _run_event_key("aggregate", period_id)
    event = _get_cancel_event(key)
    if event is not None:
        event.set()
    path = aggregate_progress_path(period_id)
    state = job_progress.cancel_progress_file(
        path,
        reason="cancelled by user",
        kind="stock_aggregate",
        period_id=period_id,
    )
    _register_job_review_item(
        job_kind="stock_aggregate",
        job_status="cancelled",
        title=f"Weekly aggregate cancelled: {period_id}",
        artifact_id=f"weekly_aggregate:{period_id}",
        period_id=period_id,
    )
    _upsert_job_ledger_entry(
        job_kind="stock_aggregate",
        period_id=period_id,
        status="cancelled",
        artifact_id=f"weekly_aggregate:{period_id}",
        cancellation_reason="cancelled by user",
    )
    return {"cancelled": True, "state": state, "period_id": period_id}


def retry_aggregate_job(period_id: str) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    return start_aggregate_job(period_id=period_id, force=True)


def run_aggregate_now(period_id: str | None = None) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    started = time.monotonic()
    aggregate = build_weekly_aggregate(period_id)
    _write_weekly_aggregate(aggregate)
    _upsert_job_ledger_entry(
        job_kind="stock_aggregate",
        period_id=period_id,
        status="done",
        artifact_id=f"weekly_aggregate:{period_id}",
        started_at=started,
        source_count=sum(
            len(signal.get("source_traces") or [])
            for signal in aggregate.get("ranked_signals") or []
        ),
    )
    return aggregate


def load_aggregate(period_id: str) -> dict | None:
    path = aggregate_json_path(period_id)
    if not path.exists():
        return None
    data = _read_json(path, {})
    return data if isinstance(data, dict) else None


def latest_aggregate() -> dict | None:
    if not aggregates_root().exists():
        return None
    candidates = []
    for path in aggregates_root().glob("*/weekly_report.json"):
        data = _read_json(path, {})
        if isinstance(data, dict):
            candidates.append(data)
    candidates.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return candidates[0] if candidates else None


def _latest_strategy_before(period_id: str) -> dict | None:
    maps = []
    if strategy_maps_root().exists():
        for path in strategy_maps_root().glob("*/strategy_map.json"):
            data = _read_json(path, {})
            if isinstance(data, dict) and data.get("period_id") != period_id:
                maps.append(data)
    maps.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return maps[0] if maps else None


def coerce_strategy_map(raw: Any, *, period_id: str) -> dict:
    data = raw if isinstance(raw, dict) else {}
    return {
        "schema_version": STRATEGY_MAP_SCHEMA_VERSION,
        "artifact_type": "strategy_map",
        "period_id": period_id,
        "generated_at": data.get("generated_at") or _now(),
        "current_weekly_aggregate_id": data.get("current_weekly_aggregate_id"),
        "previous_strategy_map_id": data.get("previous_strategy_map_id"),
        "nodes": [
            item if isinstance(item, dict) else {"label": _as_str(item)}
            for item in _as_list(data.get("nodes"))
        ],
        "edges": [
            item if isinstance(item, dict) else {"label": _as_str(item)}
            for item in _as_list(data.get("edges"))
        ],
        "diff": [
            item if isinstance(item, dict) else {"label": _as_str(item)}
            for item in _as_list(data.get("diff"))
        ],
        "contradictions": [
            item if isinstance(item, dict) else {"description": _as_str(item)}
            for item in _as_list(data.get("contradictions"))
        ],
        "markdown": _as_str(data.get("markdown")),
        "layout_metadata": data.get("layout_metadata") if isinstance(data.get("layout_metadata"), dict) else {},
    }


def build_strategy_map(period_id: str | None = None) -> dict:
    aggregate = load_aggregate(_default_period_range(period_id)[0]) or latest_aggregate()
    if aggregate is None:
        period_id, _, _ = _default_period_range(period_id)
        aggregate = run_aggregate_now(period_id)
    period_id = aggregate["period_id"]
    previous = _latest_strategy_before(period_id)
    previous_node_ids = {node.get("id") for node in (previous or {}).get("nodes", [])}
    nodes = []
    for signal in aggregate.get("ranked_signals") or []:
        if not signal.get("source_traces"):
            continue
        themes = _string_list(signal.get("affected_themes")) or _string_list(signal.get("affected_tickers"))
        label = themes[0] if themes else signal.get("source_tracker_id") or "Theme"
        node_id = f"node-{_slug(label)}"
        direction = _as_str(signal.get("direction"), "watch")
        posture = "positive" if direction == "positive" else "negative" if direction == "negative" else "watch" if direction == "watch" else "neutral"
        nodes.append(
            {
                "id": node_id,
                "label": label,
                "node_type": "theme",
                "posture": posture,
                "qualitative_action": "monitor" if posture in {"watch", "neutral"} else "accumulate" if posture == "positive" else "trim",
                "attention_weight_range": "research guidance only; not a portfolio instruction",
                "trigger_conditions": [],
                "source_tracker_refs": [
                    {
                        "tracker_id": signal.get("source_tracker_id"),
                        "tracker_run_id": signal.get("tracker_run_id"),
                    }
                ],
                "source_traces": signal.get("source_traces") or [],
                "confidence": signal.get("confidence"),
            }
        )
    deduped_nodes: dict[str, dict] = {}
    for node in nodes:
        current = deduped_nodes.get(node["id"])
        if current is None:
            deduped_nodes[node["id"]] = node
        else:
            current["source_tracker_refs"].extend(node.get("source_tracker_refs") or [])
            current["source_traces"].extend(node.get("source_traces") or [])
    nodes = list(deduped_nodes.values())
    edges = []
    for link in (aggregate.get("modules") or {}).get("cross_tracker", []):
        refs = link.get("source_tracker_refs") or []
        if len(refs) < 2:
            continue
        edges.append(
            {
                "id": link.get("id") or f"edge-{len(edges) + 1}",
                "from": refs[0].get("tracker_id"),
                "to": refs[1].get("tracker_id"),
                "relationship": "transmission_link",
                "posture": "watch",
                "qualitative_action": "monitor",
                "trigger_conditions": [],
                "source_tracker_refs": refs,
                "source_traces": link.get("source_traces") or [],
            }
        )
    diff = []
    node_ids = {node["id"] for node in nodes}
    for node in nodes:
        diff.append({"id": node["id"], "label": node["label"], "state": "unchanged" if node["id"] in previous_node_ids else "new"})
    for removed in sorted(previous_node_ids - node_ids):
        if removed:
            diff.append({"id": removed, "label": removed, "state": "removed"})
    markdown = strategy_map_markdown(period_id, nodes, edges, diff)
    return coerce_strategy_map(
        {
            "period_id": period_id,
            "current_weekly_aggregate_id": f"weekly_aggregate:{period_id}",
            "previous_strategy_map_id": (previous or {}).get("period_id"),
            "nodes": nodes,
            "edges": edges,
            "diff": diff,
            "contradictions": aggregate.get("contradictions") or [],
            "markdown": markdown,
            "layout_metadata": {"layout": "table_first", "graph_canvas_deferred": True},
        },
        period_id=period_id,
    )


def strategy_map_markdown(period_id: str, nodes: list[dict], edges: list[dict], diff: list[dict]) -> str:
    node_lines = "\n".join(
        f"- {n.get('label')}: {n.get('posture')} / {n.get('qualitative_action')}"
        for n in nodes
    ) or "- No map nodes."
    diff_lines = "\n".join(
        f"- {d.get('label')}: {d.get('state')}"
        for d in diff
    ) or "- No changes."
    return f"""# Stock Research Strategy Map

Period: {period_id}

Qualitative research guidance only. This is not automated trading or position sizing.

## Nodes

{node_lines}

## Diff

{diff_lines}
"""


def _write_strategy_map(strategy_map: dict) -> None:
    period_id = strategy_map["period_id"]
    _write_json(strategy_map_json_path(period_id), strategy_map)
    _write_text(strategy_map_markdown_path(period_id), strategy_map.get("markdown") or "")
    register_work_product(
        {
            "artifact_id": f"strategy_map:{period_id}",
            "artifact_type": "strategy_map",
            "title": f"Strategy map {period_id}",
            "status": "needs_review",
            "version": 1,
            "created_at": strategy_map.get("generated_at"),
            "updated_at": strategy_map.get("generated_at"),
            "generated_by": "stock_research_strategy",
            "reviewer": None,
            "source_refs": strategy_map.get("nodes") or [],
            "source_trace_count": sum(len(n.get("source_traces") or []) for n in strategy_map.get("nodes") or []),
            "confidence": _strategy_confidence(strategy_map),
            "review_state": "open",
            "supersedes": strategy_map.get("previous_strategy_map_id"),
            "superseded_by": None,
            "pinned": False,
            "archived": False,
            "export_paths": {
                "json": str(strategy_map_json_path(period_id)),
                "markdown": str(strategy_map_markdown_path(period_id)),
            },
            "notes": "",
            "period_id": period_id,
        }
    )
    for item in strategy_map.get("diff") or []:
        if item.get("state") in {"new", "removed", "strengthened", "weakened", "contradicted"}:
            _upsert_review_item(
                {
                    "id": f"strategy-diff:{period_id}:{item.get('id')}",
                    "item_type": "strategy_map_change",
                    "status": "open",
                    "title": f"{item.get('label')}: {item.get('state')}",
                    "artifact_id": f"strategy_map:{period_id}",
                    "severity": "medium",
                    "source_refs": [],
                }
            )


def _strategy_confidence(strategy_map: dict) -> float:
    nodes = strategy_map.get("nodes") or []
    if not nodes:
        return 0.0
    values = [_as_float(n.get("confidence"), 0.0) or 0.0 for n in nodes]
    return round(sum(values) / len(values), 3)


def _run_strategy_job(period_id: str) -> None:
    key = _run_event_key("strategy", period_id)
    event = _start_cancel_event(key)
    path = strategy_map_progress_path(period_id)
    progress = job_progress.ProgressLog(path)
    started = time.monotonic()
    progress.emit(
        "job_init",
        kind="stock_strategy",
        title="Stock Research strategy map",
        subtitle=period_id,
        period_id=period_id,
    )
    try:
        progress.emit("stage", stage="collect", message="Reading weekly aggregate and previous strategy map")
        if _is_cancelled(path, event):
            job_progress.cancel_progress_file(
                path,
                reason="Strategy map cancelled",
                kind="stock_strategy",
                period_id=period_id,
            )
            _register_job_review_item(
                job_kind="stock_strategy",
                job_status="cancelled",
                title=f"Strategy map cancelled: {period_id}",
                artifact_id=f"strategy_map:{period_id}",
                period_id=period_id,
            )
            _upsert_job_ledger_entry(
                job_kind="stock_strategy",
                period_id=period_id,
                status="cancelled",
                artifact_id=f"strategy_map:{period_id}",
                started_at=started,
                cancellation_reason="Strategy map cancelled",
            )
            return
        strategy_map = build_strategy_map(period_id)
        progress.emit("stage", stage="write", message="Writing strategy-map artifacts")
        if _is_cancelled(path, event):
            job_progress.cancel_progress_file(
                path,
                reason="Strategy map cancelled",
                kind="stock_strategy",
                period_id=period_id,
            )
            _register_job_review_item(
                job_kind="stock_strategy",
                job_status="cancelled",
                title=f"Strategy map cancelled: {period_id}",
                artifact_id=f"strategy_map:{period_id}",
                period_id=period_id,
            )
            _upsert_job_ledger_entry(
                job_kind="stock_strategy",
                period_id=period_id,
                status="cancelled",
                artifact_id=f"strategy_map:{period_id}",
                started_at=started,
                cancellation_reason="Strategy map cancelled",
            )
            return
        _write_strategy_map(strategy_map)
        _upsert_job_ledger_entry(
            job_kind="stock_strategy",
            period_id=period_id,
            status="done",
            artifact_id=f"strategy_map:{period_id}",
            started_at=started,
            source_count=sum(
                len(node.get("source_traces") or [])
                for node in strategy_map.get("nodes") or []
            ),
        )
        progress.emit("done", period_id=period_id, node_count=len(strategy_map.get("nodes") or []))
    except Exception as exc:  # noqa: BLE001
        _register_job_review_item(
            job_kind="stock_strategy",
            job_status="error",
            title=f"Strategy map failed: {period_id}",
            artifact_id=f"strategy_map:{period_id}",
            period_id=period_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        _upsert_job_ledger_entry(
            job_kind="stock_strategy",
            period_id=period_id,
            status="error",
            artifact_id=f"strategy_map:{period_id}",
            started_at=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        progress.emit("error", error=f"Strategy map failed: {type(exc).__name__}: {exc}")
    finally:
        _clear_cancel_event(key, event)


def start_strategy_map_job(period_id: str | None = None, *, force: bool = False) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    path = strategy_map_progress_path(period_id)
    if _progress_in_flight(path) and not force:
        return {
            "status": "already_running",
            "period_id": period_id,
            "stream_url": f"/api/stock-research/strategy-maps/{period_id}/stream",
            "log_url": f"/api/jobs/log?path=stock_strategy:{period_id}",
        }
    _upsert_job_ledger_entry(
        job_kind="stock_strategy",
        period_id=period_id,
        status="queued",
        artifact_id=f"strategy_map:{period_id}",
    )
    threading.Thread(
        target=_run_strategy_job,
        args=(period_id,),
        name=f"stock-strategy:{period_id}",
        daemon=True,
    ).start()
    return {
        "status": "queued",
        "period_id": period_id,
        "stream_url": f"/api/stock-research/strategy-maps/{period_id}/stream",
        "log_url": f"/api/jobs/log?path=stock_strategy:{period_id}",
    }


def cancel_strategy_map_job(period_id: str) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    key = _run_event_key("strategy", period_id)
    event = _get_cancel_event(key)
    if event is not None:
        event.set()
    path = strategy_map_progress_path(period_id)
    state = job_progress.cancel_progress_file(
        path,
        reason="cancelled by user",
        kind="stock_strategy",
        period_id=period_id,
    )
    _register_job_review_item(
        job_kind="stock_strategy",
        job_status="cancelled",
        title=f"Strategy map cancelled: {period_id}",
        artifact_id=f"strategy_map:{period_id}",
        period_id=period_id,
    )
    _upsert_job_ledger_entry(
        job_kind="stock_strategy",
        period_id=period_id,
        status="cancelled",
        artifact_id=f"strategy_map:{period_id}",
        cancellation_reason="cancelled by user",
    )
    return {"cancelled": True, "state": state, "period_id": period_id}


def retry_strategy_map_job(period_id: str) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    return start_strategy_map_job(period_id=period_id, force=True)


def run_strategy_map_now(period_id: str | None = None) -> dict:
    period_id, _, _ = _default_period_range(period_id)
    started = time.monotonic()
    strategy_map = build_strategy_map(period_id)
    _write_strategy_map(strategy_map)
    _upsert_job_ledger_entry(
        job_kind="stock_strategy",
        period_id=period_id,
        status="done",
        artifact_id=f"strategy_map:{period_id}",
        started_at=started,
        source_count=sum(
            len(node.get("source_traces") or [])
            for node in strategy_map.get("nodes") or []
        ),
    )
    return strategy_map


def load_strategy_map(period_id: str) -> dict | None:
    path = strategy_map_json_path(period_id)
    if not path.exists():
        return None
    data = _read_json(path, {})
    return data if isinstance(data, dict) else None


def latest_strategy_map() -> dict | None:
    if not strategy_maps_root().exists():
        return None
    maps = []
    for path in strategy_maps_root().glob("*/strategy_map.json"):
        data = _read_json(path, {})
        if isinstance(data, dict):
            maps.append(data)
    maps.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return maps[0] if maps else None


def _normalize_work_product(item: dict) -> dict:
    now = _now()
    artifact_id = _as_str(item.get("artifact_id"))
    if not artifact_id:
        raise ValueError("Work product missing artifact_id")
    history = [
        row
        for row in _as_list(item.get("version_history"))
        if isinstance(row, dict)
    ]
    return {
        "schema_version": WORK_PRODUCT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "artifact_type": _as_str(item.get("artifact_type"), "artifact"),
        "title": _as_str(item.get("title"), artifact_id),
        "status": _normalize_work_product_status(item.get("status")),
        "version": max(1, _as_int(item.get("version"), 1)),
        "created_at": item.get("created_at") or now,
        "updated_at": item.get("updated_at") or now,
        "generated_by": _as_str(item.get("generated_by"), "stock_research"),
        "reviewer": item.get("reviewer"),
        "source_refs": _as_list(item.get("source_refs")),
        "source_trace_count": max(0, _as_int(item.get("source_trace_count"), 0)),
        "confidence": _as_float(item.get("confidence"), None),
        "review_state": _normalize_review_status(item.get("review_state")),
        "supersedes": item.get("supersedes"),
        "superseded_by": item.get("superseded_by"),
        "pinned": bool(item.get("pinned")),
        "archived": bool(item.get("archived")),
        "export_paths": item.get("export_paths") if isinstance(item.get("export_paths"), dict) else {},
        "version_history": history,
        "notes": _as_str(item.get("notes")),
        **{
            key: value
            for key, value in item.items()
            if key
            in {
                "tracker_id",
                "run_id",
                "period_id",
                "period_start",
                "period_end",
            }
        },
    }


def _work_product_history_event(
    product: dict,
    *,
    action: str,
    previous: dict | None = None,
    patch: dict | None = None,
) -> dict:
    changed_fields = []
    if previous:
        for key in (
            "version",
            "status",
            "review_state",
            "reviewer",
            "pinned",
            "archived",
            "supersedes",
            "superseded_by",
            "export_paths",
        ):
            if previous.get(key) != product.get(key):
                changed_fields.append(key)
    elif patch:
        changed_fields = sorted(str(key) for key in patch.keys())
    return {
        "event_id": f"vp-{uuid.uuid4().hex[:10]}",
        "action": action,
        "version": product.get("version") or 1,
        "status": product.get("status"),
        "review_state": product.get("review_state"),
        "reviewer": product.get("reviewer"),
        "updated_at": product.get("updated_at") or _now(),
        "changed_fields": changed_fields,
    }


def _append_work_product_history(
    product: dict,
    *,
    action: str,
    previous: dict | None = None,
    patch: dict | None = None,
) -> dict:
    history = [
        row
        for row in _as_list((previous or product).get("version_history"))
        if isinstance(row, dict)
    ]
    if action == "registered" and history:
        product["version_history"] = history
        return product
    history.append(
        _work_product_history_event(
            product,
            action=action,
            previous=previous,
            patch=patch,
        )
    )
    product["version_history"] = history[-25:]
    return product


def register_work_product(item: dict) -> dict:
    product = _normalize_work_product(item)
    with _LOCK:
        catalog = list_work_products(include_archived=True)
        replaced = False
        for index, existing in enumerate(catalog):
            if existing.get("artifact_id") == product["artifact_id"]:
                product["pinned"] = bool(existing.get("pinned")) if "pinned" not in item else product["pinned"]
                product["archived"] = bool(existing.get("archived")) if "archived" not in item else product["archived"]
                product = _append_work_product_history(
                    product,
                    action="registered",
                    previous=existing,
                    patch=item,
                )
                catalog[index] = {**existing, **product, "updated_at": product["updated_at"]}
                replaced = True
                break
        if not replaced:
            product = _append_work_product_history(product, action="created", patch=item)
            catalog.append(product)
        catalog.sort(key=lambda row: (not row.get("pinned"), str(row.get("updated_at", ""))), reverse=False)
        _write_json(catalog_path(), {"work_products": catalog})
    return product


def list_work_products(
    *,
    include_archived: bool = False,
    artifact_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    data = _read_json(catalog_path(), {"work_products": []})
    rows = [
        _normalize_work_product(item)
        for item in _as_list(data.get("work_products") if isinstance(data, dict) else [])
        if isinstance(item, dict)
    ]
    if not include_archived:
        rows = [row for row in rows if not row.get("archived") and row.get("status") != "archived"]
    if artifact_type:
        rows = [row for row in rows if row.get("artifact_type") == artifact_type]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    rows.sort(key=lambda row: (not row.get("pinned"), str(row.get("updated_at", ""))), reverse=False)
    return rows


def update_work_product(artifact_id: str, patch: dict) -> dict:
    with _LOCK:
        rows = list_work_products(include_archived=True)
        for index, row in enumerate(rows):
            if row.get("artifact_id") == artifact_id:
                updated = _normalize_work_product(
                    {
                        **row,
                        **(patch or {}),
                        "artifact_id": artifact_id,
                        "updated_at": _now(),
                    }
                )
                updated = _append_work_product_history(
                    updated,
                    action="updated",
                    previous=row,
                    patch=patch or {},
                )
                rows[index] = updated
                _write_json(catalog_path(), {"work_products": rows})
                return updated
    raise ValueError(f"Unknown work product: {artifact_id}")


def _review_items_raw() -> list[dict]:
    data = _read_json(review_queue_path(), {"items": []})
    items = data.get("items") if isinstance(data, dict) else []
    return [item for item in _as_list(items) if isinstance(item, dict)]


def _normalize_review_item(item: dict) -> dict:
    now = _now()
    item_id = _as_str(item.get("id"))
    if not item_id:
        raise ValueError("Review item missing id")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": item_id,
        "item_type": _as_str(item.get("item_type"), "review"),
        "status": _normalize_review_status(item.get("status")),
        "title": _as_str(item.get("title"), item_id),
        "artifact_id": item.get("artifact_id"),
        "tracker_id": item.get("tracker_id"),
        "run_id": item.get("run_id"),
        "period_id": item.get("period_id"),
        "job_kind": item.get("job_kind"),
        "job_status": item.get("job_status"),
        "error": _as_str(item.get("error")),
        "severity": _as_str(item.get("severity"), "medium"),
        "rationale": _as_str(item.get("rationale")),
        "source_refs": _as_list(item.get("source_refs")),
        "created_at": item.get("created_at") or now,
        "updated_at": item.get("updated_at") or now,
    }


def _write_review_items(items: list[dict]) -> None:
    items.sort(key=lambda row: (row.get("status") != "open", str(row.get("updated_at", ""))), reverse=False)
    _write_json(review_queue_path(), {"items": items})


def _upsert_review_item(item: dict) -> dict:
    incoming = _normalize_review_item(item)
    items = [_normalize_review_item(row) for row in _review_items_raw()]
    for index, existing in enumerate(items):
        if existing["id"] == incoming["id"]:
            if existing.get("status") != "open":
                incoming["status"] = existing["status"]
                incoming["rationale"] = existing.get("rationale", "")
            incoming["created_at"] = existing.get("created_at") or incoming["created_at"]
            items[index] = {**existing, **incoming, "updated_at": _now()}
            _write_review_items(items)
            return items[index]
    items.append(incoming)
    _write_review_items(items)
    return incoming


def list_review_items(*, status: str | None = None) -> list[dict]:
    # Add current stale trackers as derived, durable queue items.
    for tracker in list_trackers():
        if tracker.get("status") == "active" and tracker.get("is_stale"):
            _upsert_review_item(
                {
                    "id": f"stale-current:{tracker['id']}",
                    "item_type": "stale_tracker",
                    "status": "open",
                    "title": f"{tracker['display_name']} is stale or has never run.",
                    "tracker_id": tracker["id"],
                    "severity": "medium",
                    "source_refs": [],
                }
            )
    rows = [_normalize_review_item(item) for item in _review_items_raw()]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    rows.sort(key=lambda row: (row.get("status") != "open", str(row.get("updated_at", ""))), reverse=False)
    return rows


def update_review_item(item_id: str, patch: dict) -> dict:
    items = [_normalize_review_item(item) for item in _review_items_raw()]
    for index, item in enumerate(items):
        if item["id"] == item_id:
            updated = _normalize_review_item(
                {
                    **item,
                    **(patch or {}),
                    "id": item_id,
                    "updated_at": _now(),
                }
            )
            items[index] = updated
            _write_review_items(items)
            return updated
    raise ValueError(f"Unknown review item: {item_id}")


def update_run_review(tracker_id: str, run_id: str, patch: dict) -> dict:
    metadata = _read_json(tracker_run_metadata_path(tracker_id, run_id), {})
    if not metadata:
        raise ValueError(f"Unknown run: {tracker_id}/{run_id}")
    scores = metadata.get("reviewer_scores") if isinstance(metadata.get("reviewer_scores"), dict) else {}
    for key in ("factual_accuracy", "usefulness", "source_quality", "writing_quality", "actionability"):
        if key in patch:
            scores[key] = max(0, min(5, _as_int(patch.get(key), 0)))
    metadata["reviewer_scores"] = scores
    metadata["reviewer_score"] = round(sum(scores.values()) / len(scores), 2) if scores else None
    metadata["review_notes"] = _as_str(patch.get("review_notes"), metadata.get("review_notes") or "")
    metadata["updated_at"] = _now()
    _write_json(tracker_run_metadata_path(tracker_id, run_id), metadata)
    _upsert_run_ledger_entry(_tracker_run_ledger_entry(metadata, get_tracker(tracker_id)))
    return metadata


def review_knowledge_update(
    tracker_id: str,
    run_id: str,
    update_id: str,
    *,
    status: str,
    rationale: str | None = None,
) -> dict:
    output = get_tracker_run_output(tracker_id, run_id)
    if output is None:
        raise ValueError(f"Unknown run: {tracker_id}/{run_id}")
    normalized_status = _normalize_review_status(status)
    found = None
    for item in output.get("knowledge_updates") or []:
        if item.get("id") == update_id:
            item["review_status"] = normalized_status
            item["review_rationale"] = rationale
            found = item
            break
    if found is None:
        raise ValueError(f"Unknown knowledge update: {update_id}")
    _write_json(tracker_run_output_path(tracker_id, run_id), output)
    review_id = f"knowledge:{tracker_id}:{run_id}:{update_id}"
    try:
        update_review_item(
            review_id,
            {
                "status": normalized_status,
                "rationale": rationale or "",
            },
        )
    except ValueError:
        _upsert_review_item(
            {
                "id": review_id,
                "item_type": "knowledge_update",
                "status": normalized_status,
                "title": found.get("text") or "Knowledge update",
                "artifact_id": f"tracker_run:{tracker_id}:{run_id}",
                "tracker_id": tracker_id,
                "run_id": run_id,
                "severity": "low",
                "rationale": rationale or "",
                "source_refs": found.get("source_traces") or [],
            }
        )
    if normalized_status == "resolved":
        knowledge = _read_json(tracker_knowledge_path(tracker_id), _default_knowledge({"id": tracker_id}))
        knowledge.setdefault("accepted_lessons", []).append(
            {
                "id": update_id,
                "text": found.get("text"),
                "accepted_at": _now(),
                "source_run_id": run_id,
                "source_traces": found.get("source_traces") or [],
            }
        )
        knowledge["updated_at"] = _now()
        _write_json(tracker_knowledge_path(tracker_id), knowledge)
        with tracker_notes_path(tracker_id).open("a", encoding="utf-8") as f:
            f.write(f"\n- {knowledge['updated_at']}: {found.get('text')}\n")
    return found


def list_evaluation() -> dict:
    rows = []
    for tracker in list_trackers(include_archived=True):
        for run in list_tracker_runs(tracker["id"]):
            rows.append(
                {
                    "tracker_id": tracker["id"],
                    "tracker_name": tracker.get("display_name"),
                    "run_id": run.get("run_id"),
                    "status": run.get("status"),
                    "period_id": run.get("period_id"),
                    "duration_ms": run.get("duration_ms"),
                    "token_usage": run.get("token_usage") or {},
                    "estimated_cost_usd": run.get("estimated_cost_usd"),
                    "source_count": run.get("source_count"),
                    "source_priority_mix": run.get("source_priority_mix") or {},
                    "source_quality": run.get("source_quality") or {},
                    "evidence_coverage": run.get("evidence_coverage"),
                    "contradiction_count": run.get("contradiction_count"),
                    "missing_source_count": run.get("missing_source_count"),
                    "reviewer_score": run.get("reviewer_score"),
                    "reviewer_scores": run.get("reviewer_scores") or {},
                    "failure_reason": run.get("failure_reason") or run.get("error") or "",
                    "fallback_used": bool(run.get("fallback_used")),
                    "preserved_previous_artifact": run.get("preserved_previous_artifact") or run.get("preserved_previous_run_id"),
                    "cancellation_reason": run.get("cancellation_reason") or "",
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("updated_at"),
                }
            )
    rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return {"runs": rows, "run_ledger": list_run_ledger()}


def work_product_catalog_summary() -> dict:
    products = list_work_products()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for product in products:
        by_type[product["artifact_type"]] = by_type.get(product["artifact_type"], 0) + 1
        by_status[product["status"]] = by_status.get(product["status"], 0) + 1
    return {"total": len(products), "by_type": by_type, "by_status": by_status}


def _doctor_issue(
    issues: list[dict],
    *,
    severity: str,
    issue_type: str,
    message: str,
    path: Path | str | None = None,
    tracker_id: str | None = None,
    artifact_id: str | None = None,
) -> None:
    issues.append(
        {
            "id": f"{issue_type}:{len(issues) + 1}",
            "severity": severity,
            "type": issue_type,
            "message": message,
            "path": str(path) if path is not None else None,
            "tracker_id": tracker_id,
            "artifact_id": artifact_id,
        }
    )


def _trace_has_source_ref(trace: dict, valid_source_ids: set[str]) -> bool:
    source_id = _as_str((trace or {}).get("source_id"))
    return not source_id or source_id in valid_source_ids


def stock_research_doctor() -> dict:
    """Return a non-mutating health report for Stock Research artifacts."""
    trackers = list_trackers(include_archived=True)
    products = list_work_products(include_archived=True)
    issues: list[dict] = []
    source_ids_by_tracker: dict[str, set[str]] = {}
    run_refs: set[str] = set()

    if not _root().exists():
        _doctor_issue(
            issues,
            severity="error",
            issue_type="missing_root",
            message="Stock Research root does not exist.",
            path=_root(),
        )

    for tracker in trackers:
        tracker_id = tracker["id"]
        for label, path in {
            "tracker_config": tracker_config_path(tracker_id),
            "knowledge": tracker_knowledge_path(tracker_id),
            "notes": tracker_notes_path(tracker_id),
            "source_manifest": tracker_source_manifest_path(tracker_id),
        }.items():
            if not path.exists():
                _doctor_issue(
                    issues,
                    severity="error",
                    issue_type=f"missing_{label}",
                    message=f"Missing {label} for tracker {tracker_id}.",
                    path=path,
                    tracker_id=tracker_id,
                )
        if tracker.get("schema_version") != SCHEMA_VERSION:
            _doctor_issue(
                issues,
                severity="warning",
                issue_type="schema_version",
                message=f"Tracker {tracker_id} has schema_version={tracker.get('schema_version')}.",
                path=tracker_config_path(tracker_id),
                tracker_id=tracker_id,
            )
        sources = list_tracker_sources(tracker_id)
        source_ids_by_tracker[tracker_id] = {_as_str(source.get("id")) for source in sources if source.get("id")}
        for source in sources:
            if source.get("source_type") == "file" and source.get("exists") is False:
                _doctor_issue(
                    issues,
                    severity="error",
                    issue_type="missing_source_file",
                    message=f"Stored source file is missing: {source.get('title') or source.get('filename')}.",
                    path=tracker_sources_dir(tracker_id) / _as_str(source.get("stored_name")),
                    tracker_id=tracker_id,
                    artifact_id=f"source:{tracker_id}:{source.get('id')}",
                )
        for run in list_tracker_runs(tracker_id):
            run_id = run.get("run_id")
            run_refs.add(f"{tracker_id}:{run_id}")
            artifact_id = f"tracker_run:{tracker_id}:{run_id}"
            for label, path in {
                "run_output": tracker_run_output_path(tracker_id, run_id),
                "run_metadata": tracker_run_metadata_path(tracker_id, run_id),
                "source_manifest": tracker_run_source_manifest_path(tracker_id, run_id),
                "report": tracker_run_report_path(tracker_id, run_id),
            }.items():
                if not path.exists():
                    _doctor_issue(
                        issues,
                        severity="error" if label in {"run_metadata", "run_output"} else "warning",
                        issue_type=f"missing_{label}",
                        message=f"Missing {label} for tracker run {tracker_id}/{run_id}.",
                        path=path,
                        tracker_id=tracker_id,
                        artifact_id=artifact_id,
                    )
            for trace in run.get("source_traces") or []:
                if not _trace_has_source_ref(trace, source_ids_by_tracker.get(tracker_id, set())):
                    _doctor_issue(
                        issues,
                        severity="warning",
                        issue_type="broken_source_trace",
                        message=f"Run {tracker_id}/{run_id} references an unknown source id.",
                        tracker_id=tracker_id,
                        artifact_id=artifact_id,
                    )

    for aggregate in [item for item in [latest_aggregate()] if item]:
        for signal in aggregate.get("ranked_signals") or []:
            tracker_id = signal.get("source_tracker_id")
            run_id = signal.get("tracker_run_id")
            if tracker_id and run_id and f"{tracker_id}:{run_id}" not in run_refs:
                _doctor_issue(
                    issues,
                    severity="warning",
                    issue_type="broken_aggregate_run_ref",
                    message=f"Aggregate signal references unknown run {tracker_id}/{run_id}.",
                    artifact_id=f"weekly_aggregate:{aggregate.get('period_id')}",
                    tracker_id=tracker_id,
                )
            for trace in signal.get("source_traces") or []:
                if tracker_id and not _trace_has_source_ref(trace, source_ids_by_tracker.get(tracker_id, set())):
                    _doctor_issue(
                        issues,
                        severity="warning",
                        issue_type="broken_aggregate_source_ref",
                        message=f"Aggregate signal references an unknown source id for {tracker_id}.",
                        artifact_id=f"weekly_aggregate:{aggregate.get('period_id')}",
                        tracker_id=tracker_id,
                    )

    for strategy_map in [item for item in [latest_strategy_map()] if item]:
        for item in (strategy_map.get("nodes") or []) + (strategy_map.get("edges") or []):
            refs = item.get("source_tracker_refs") or []
            for ref in refs:
                tracker_id = ref.get("tracker_id")
                run_id = ref.get("tracker_run_id")
                if tracker_id and run_id and f"{tracker_id}:{run_id}" not in run_refs:
                    _doctor_issue(
                        issues,
                        severity="warning",
                        issue_type="broken_strategy_run_ref",
                        message=f"Strategy map references unknown run {tracker_id}/{run_id}.",
                        artifact_id=f"strategy_map:{strategy_map.get('period_id')}",
                        tracker_id=tracker_id,
                    )

    for product in products:
        artifact_id = product.get("artifact_id")
        for label, path_value in (product.get("export_paths") or {}).items():
            path = Path(path_value)
            if not path.exists():
                _doctor_issue(
                    issues,
                    severity="warning",
                    issue_type="missing_export",
                    message=f"Work product export is missing: {label}.",
                    path=path,
                    artifact_id=artifact_id,
                    tracker_id=product.get("tracker_id"),
                )
        tracker_id = product.get("tracker_id")
        run_id = product.get("run_id")
        if tracker_id and run_id and f"{tracker_id}:{run_id}" not in run_refs:
            _doctor_issue(
                issues,
                severity="warning",
                issue_type="broken_product_run_ref",
                message=f"Work product references unknown run {tracker_id}/{run_id}.",
                artifact_id=artifact_id,
                tracker_id=tracker_id,
            )

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": "ok" if error_count == 0 else "issues",
        "summary": {
            "tracker_count": len(trackers),
            "source_count": sum(len(ids) for ids in source_ids_by_tracker.values()),
            "work_product_count": len(products),
            "run_count": len(run_refs),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "issues": issues,
    }


def list_all_sources() -> list[dict]:
    sources = []
    for tracker in list_trackers(include_archived=True):
        for source in list_tracker_sources(tracker["id"]):
            sources.append({**source, "tracker_name": tracker.get("display_name")})
    sources.sort(key=lambda s: str(s.get("created_at", "")), reverse=True)
    return sources


def dashboard_payload() -> dict:
    trackers = list_trackers()
    sources = list_all_sources()
    aggregate = latest_aggregate()
    strategy_map = latest_strategy_map()
    review_items = list_review_items()
    products = list_work_products()
    evaluation = list_evaluation()
    doctor = stock_research_doctor()
    counts_by_type = {t: 0 for t in TRACKER_TYPES}
    for tracker in trackers:
        counts_by_type[tracker["type"]] = counts_by_type.get(tracker["type"], 0) + 1
    failed_runs = [
        run
        for tracker in trackers
        for run in list_tracker_runs(tracker["id"])
        if run.get("status") == "error"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "summary": {
            "tracker_count": len(trackers),
            "tracker_counts_by_type": counts_by_type,
            "due_count": sum(1 for t in trackers if t.get("is_due")),
            "stale_count": sum(1 for t in trackers if t.get("is_stale")),
            "failed_run_count": len(failed_runs),
            "missing_source_warning_count": sum(
                1 for item in review_items if item.get("item_type") in {"missing_source", "stale_tracker"} and item.get("status") == "open"
            ),
            "open_review_item_count": sum(1 for item in review_items if item.get("status") == "open"),
            "work_product_count": len(products),
            "source_count": len(sources),
            "doctor_error_count": doctor["summary"]["error_count"],
            "doctor_warning_count": doctor["summary"]["warning_count"],
            "run_ledger_count": len(evaluation.get("run_ledger") or []),
        },
        "trackers": trackers,
        "sources": sources,
        "runs": [
            {**run, "tracker_name": tracker.get("display_name")}
            for tracker in trackers
            for run in list_tracker_runs(tracker["id"])
        ],
        "latest_aggregate": aggregate,
        "latest_strategy_map": strategy_map,
        "work_products": products,
        "review_items": review_items,
        "evaluation": evaluation,
        "doctor": doctor,
    }


def iter_tracker_progress_paths() -> list[tuple[str, str, Path]]:
    if not trackers_root().exists():
        return []
    out = []
    for path in trackers_root().glob("*/logs/*.progress.jsonl"):
        tracker_id = path.parent.parent.name
        run_id = path.name.removesuffix(".progress.jsonl")
        out.append((tracker_id, run_id, path))
    return out


def iter_aggregate_progress_paths() -> list[tuple[str, Path]]:
    if not aggregates_root().exists():
        return []
    return [
        (path.parent.name, path)
        for path in aggregates_root().glob("*/weekly_report.progress.jsonl")
    ]


def iter_strategy_progress_paths() -> list[tuple[str, Path]]:
    if not strategy_maps_root().exists():
        return []
    return [
        (path.parent.name, path)
        for path in strategy_maps_root().glob("*/strategy_map.progress.jsonl")
    ]


def recover_stale_runs(*, max_idle_seconds: int = ACTIVE_JOB_MAX_IDLE_SECONDS) -> int:
    recovered = 0
    for tracker_id, run_id, path in iter_tracker_progress_paths():
        state = job_progress.scan_progress_state(path)
        if state.get("terminated"):
            continue
        if job_progress.progress_state_in_flight(state, max_idle_seconds=max_idle_seconds):
            continue
        job_progress.ProgressLog(path, truncate=False).emit(
            "recovered",
            recovered=True,
            error="Recovered interrupted stock tracker run",
            kind="stock_tracker",
            tracker_id=tracker_id,
            run_id=run_id,
        )
        _write_tracker_run_metadata(
            tracker_id,
            run_id,
            {
                "status": "recovered",
                "failure_reason": "Recovered interrupted stock tracker run",
            },
        )
        _update_tracker_current_run(tracker_id, None)
        tracker = get_tracker(tracker_id)
        _register_job_review_item(
            job_kind="stock_tracker",
            job_status="recovered",
            title=f"Tracker run recovered after interruption: {(tracker or {}).get('display_name') or tracker_id}",
            artifact_id=f"tracker_run:{tracker_id}:{run_id}",
            tracker_id=tracker_id,
            run_id=run_id,
            error="Recovered interrupted stock tracker run",
        )
        recovered += 1
    for period_id, path in iter_aggregate_progress_paths():
        state = job_progress.scan_progress_state(path)
        if state.get("terminated"):
            continue
        if job_progress.progress_state_in_flight(state, max_idle_seconds=max_idle_seconds):
            continue
        job_progress.ProgressLog(path, truncate=False).emit(
            "recovered",
            recovered=True,
            error="Recovered interrupted stock aggregate run",
            kind="stock_aggregate",
            period_id=period_id,
        )
        _register_job_review_item(
            job_kind="stock_aggregate",
            job_status="recovered",
            title=f"Weekly aggregate recovered after interruption: {period_id}",
            artifact_id=f"weekly_aggregate:{period_id}",
            period_id=period_id,
            error="Recovered interrupted stock aggregate run",
        )
        recovered += 1
    for period_id, path in iter_strategy_progress_paths():
        state = job_progress.scan_progress_state(path)
        if state.get("terminated"):
            continue
        if job_progress.progress_state_in_flight(state, max_idle_seconds=max_idle_seconds):
            continue
        job_progress.ProgressLog(path, truncate=False).emit(
            "recovered",
            recovered=True,
            error="Recovered interrupted stock strategy-map run",
            kind="stock_strategy",
            period_id=period_id,
        )
        _register_job_review_item(
            job_kind="stock_strategy",
            job_status="recovered",
            title=f"Strategy map recovered after interruption: {period_id}",
            artifact_id=f"strategy_map:{period_id}",
            period_id=period_id,
            error="Recovered interrupted stock strategy-map run",
        )
        recovered += 1
    return recovered


def cleanup_stock_research_root() -> None:
    """Test helper: remove the configured Stock Research root."""
    shutil.rmtree(_root(), ignore_errors=True)
