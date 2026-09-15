"""Signal watch: snapshots of every company's transparent signal score, and the moves between them."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import research_store, serena_analysis, signal_score, storage

CACHE_TTL_S = 120.0
_COMPANY_SCORE_FILES = frozenset({"decisions.json", "ic_meetings.json", "portfolio.json", "reference_calls.json"})
_SCORES_LOCK = threading.Lock()
_SCORES: dict[str, Any] = {"key": None, "at": 0.0, "scores": {}}


def _snapshot_file():
    return storage.DATA_DIR / "signal_snapshots.jsonl"


def _settings_file():
    return storage.DATA_DIR / "settings" / "signal_watch.yaml"
DEFAULTS = {"up_threshold": 70, "down_threshold": 40, "min_delta": 10}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_settings() -> dict:
    data = storage._read_yaml_lenient(_settings_file(), {}) or {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if data.get(key) is not None:
            try:
                out[key] = float(data[key])
            except (TypeError, ValueError):
                pass
    return out


def save_settings(patch: dict) -> dict:
    with storage._WRITE_LOCK:
        storage._quarantine_unparseable(_settings_file())
        current = get_settings()
        for key in DEFAULTS:
            if key in patch and patch[key] is not None:
                try:
                    current[key] = float(patch[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{key} must be a number") from exc
        if not 0 <= current["down_threshold"] <= current["up_threshold"] <= 100:
            raise ValueError("thresholds must satisfy 0 ≤ down ≤ up ≤ 100")
        _settings_file().parent.mkdir(parents=True, exist_ok=True)
        storage._write_yaml(_settings_file(), current)
    return current


def _snapshots() -> list[dict]:
    if not _snapshot_file().exists():
        return []
    out = []
    for line in _snapshot_file().read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _file_stats(root: Path, names: frozenset[str] | None = None) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    pending = [str(root)]
    while pending:
        try:
            entries = os.scandir(pending.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif names is None or entry.name in names:
                        st = entry.stat(follow_symlinks=False)
                        out.append((entry.path, st.st_mtime_ns, st.st_size))
                except OSError:
                    continue
    return out


def _scores_key() -> tuple:
    stats = _file_stats(storage.DATA_DIR / "companies", _COMPANY_SCORE_FILES)
    for root in (
        storage.DATA_DIR / "company_ext",
        storage.DATA_DIR / "settings",
        research_store.RESEARCH_ROOT,
        serena_analysis.ANALYSIS_ROOT,
    ):
        stats.extend(_file_stats(root))
    try:
        st = storage.COMPANIES_FILE.stat()
        stats.append((str(storage.COMPANIES_FILE), st.st_mtime_ns, st.st_size))
    except OSError:
        pass
    stats.sort()
    return (str(storage.DATA_DIR), storage.reports_version(), tuple(stats))


def _compute_scores() -> dict[str, dict]:
    scores: dict[str, dict] = {}
    reports = storage.reports_by_company()
    for company in storage.list_companies():
        cid = company.get("id")
        if not cid:
            continue
        try:
            result = signal_score.compute(cid, reports=reports.get(cid, []))
        except Exception:  # noqa: BLE001
            continue
        scores[cid] = {"score": result.get("score"), "coverage": result.get("coverage"), "name": company.get("name") or cid}
    return scores


def _current_scores() -> dict[str, dict]:
    with _SCORES_LOCK:
        key = _scores_key()
        if _SCORES["key"] == key and time.monotonic() - _SCORES["at"] < CACHE_TTL_S:
            return _SCORES["scores"]
        scores = _compute_scores()
        _SCORES.update(key=key, at=time.monotonic(), scores=scores)
        return scores


def snapshot(*, taken_by: str | None = None) -> dict:
    scores = _current_scores()
    entry = {"at": _now(), "by": taken_by or "", "scores": {cid: s["score"] for cid, s in scores.items()}}
    _snapshot_file().parent.mkdir(parents=True, exist_ok=True)
    with _snapshot_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"at": entry["at"], "company_count": len(scores)}


def moves() -> dict:
    settings = get_settings()
    snaps = _snapshots()
    previous = snaps[-1] if snaps else None
    current = _current_scores()
    items = []
    for cid, cur in current.items():
        prev_score = (previous or {}).get("scores", {}).get(cid)
        score = cur["score"]
        delta = (score - prev_score) if (score is not None and prev_score is not None) else None
        flags = []
        if score is not None:
            if score >= settings["up_threshold"] and (prev_score is None or prev_score < settings["up_threshold"]):
                flags.append("crossed_up")
            if score <= settings["down_threshold"] and (prev_score is None or prev_score > settings["down_threshold"]):
                flags.append("crossed_down")
        if delta is not None and abs(delta) >= settings["min_delta"]:
            flags.append("big_move")
        items.append({
            "company_id": cid,
            "company_name": cur["name"],
            "score": score,
            "previous": prev_score,
            "delta": delta,
            "coverage": cur["coverage"],
            "flags": flags,
        })
    items.sort(key=lambda i: (-len(i["flags"]), -abs(i["delta"] or 0), -(i["score"] or 0)))
    return {
        "generated_at": _now(),
        "settings": settings,
        "previous_snapshot_at": (previous or {}).get("at"),
        "snapshot_count": len(snaps),
        "items": items,
        "flagged": [i for i in items if i["flags"]],
    }


__all__ = ["get_settings", "save_settings", "snapshot", "moves", "Any"]
