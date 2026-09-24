"""Tracked-company news updates — ingest, dedupe, impact, auto-run labels.

Pipeline:
1. Refresh a company's news with a Claude web search (Sonnet, medium
   effort) and ingest the feed.
2. Fingerprint + dedupe so old items are not re-processed.
3. Judge impact (low / medium / high) with one Opus 5 call at medium
   effort per company; keyword rules are the fallback.
4. Record recommended auto actions (investigate / report).
5. Launch them only when the user clicks Run now, or when auto-apply is
   on (off by default; a toggle in the company's News tab).
6. Surface labels for Overview / Memo Studio when an auto-run applied.

The background loop syncs the watchlist every 12 hours by default (owner,
2026-09-14: a 15-minute loop with auto-execute on could start a full
report after every headline).

The server watchlist (`settings/tracking_watchlist.json`) mirrors the
browser follow list so a background daemon can sync starred companies.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import auto_update, context_store, storage
from . import memo_flags

logger = logging.getLogger("bsh.tracking_updates")

_LOCK = threading.RLock()
_SYNC_THREAD_STARTED = False
_SYNC_THREAD_LOCK = threading.Lock()

RUNNING_REPORT_STATUSES = {
    "queued",
    "prepping",
    "ready_for_analysis",
    "analyzing",
    "running",
}

def watchlist_path() -> Path:
    return storage.DATA_DIR / "settings" / "tracking_watchlist.json"

IMPACT_LOW = "low"
IMPACT_MEDIUM = "medium"
IMPACT_HIGH = "high"

ACTION_NONE = "none"
ACTION_INVESTIGATE = "deep_investigate"
ACTION_REPORT = "full_report"

# The cadence itself lives in server.auto_update (the shared bar).
AUTO_UPDATE_CHANNEL = "tracked_news"
SYNC_INTERVAL_SECONDS_DEFAULT = 12 * 3600
# How often the loop wakes to check whether a sync is due.
SYNC_CHECK_SECONDS = 600
NEWS_MODEL_DEFAULT = "sonnet"
NEWS_EFFORT_DEFAULT = "medium"
IMPACT_MODEL_DEFAULT = "claude-opus-5"
IMPACT_EFFORT_DEFAULT = "medium"
# One impact call judges at most this many new items; the rest use keywords.
IMPACT_MAX_ITEMS = 25


def _env_text(name: str, default: str) -> str:
    return str(os.environ.get(name) or "").strip() or default


def news_model() -> str:
    """Model for the tracker's news search (``BSH_TRACKING_NEWS_MODEL``)."""
    return _env_text("BSH_TRACKING_NEWS_MODEL", NEWS_MODEL_DEFAULT)


def news_effort() -> str:
    return _env_text("BSH_TRACKING_NEWS_EFFORT", NEWS_EFFORT_DEFAULT)


def impact_model() -> str:
    """Model that judges news impact and reassesses recorded decisions
    (``BSH_TRACKING_IMPACT_MODEL``)."""
    return _env_text("BSH_TRACKING_IMPACT_MODEL", IMPACT_MODEL_DEFAULT)


def impact_effort() -> str:
    return _env_text("BSH_TRACKING_IMPACT_EFFORT", IMPACT_EFFORT_DEFAULT)


def _impact_ai_enabled() -> bool:
    return os.environ.get("BSH_TRACKING_IMPACT_AI", "1") == "1"


def sync_interval_seconds() -> float:
    """Seconds between background syncs, from the auto-update bar.

    The stored choice wins; ``BSH_TRACKING_SYNC_INTERVAL_SECONDS`` is only
    the default until someone picks one. ``0`` means manual — the loop
    never fires and the Sync button is the only way in."""
    hours = auto_update.interval_hours(AUTO_UPDATE_CHANNEL)
    if hours <= 0:
        return 0.0
    return max(60.0, hours * 3600.0)


def sync_cadence() -> str:
    """Which segment of the auto-update bar is lit."""
    return auto_update.cadence(AUTO_UPDATE_CHANNEL)

_HIGH_TERMS = (
    "acquire",
    "acquisition",
    "merger",
    "bankrupt",
    "lawsuit",
    "sec ",
    "fraud",
    "ceo resign",
    "ceo steps down",
    "funding round",
    "series ",
    "ipo",
    "delist",
    "default",
    "lay off",
    "layoff",
)
_MEDIUM_TERMS = (
    "partnership",
    "contract",
    "customer",
    "product launch",
    "launch",
    "expansion",
    "earnings",
    "revenue",
    "guidance",
    "hiring",
    "executive",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _updates_path(company_id: str) -> Path:
    return storage.DATA_DIR / "companies" / company_id / "tracking_updates.json"


def _load(company_id: str) -> dict:
    path = _updates_path(company_id)
    if not path.exists():
        return {"company_id": company_id, "items": [], "auto_runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"company_id": company_id, "items": [], "auto_runs": []}
    if not isinstance(payload, dict):
        return {"company_id": company_id, "items": [], "auto_runs": []}
    payload.setdefault("company_id", company_id)
    payload.setdefault("items", [])
    payload.setdefault("auto_runs", [])
    return payload


def _save(company_id: str, payload: dict) -> dict:
    path = _updates_path(company_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def fingerprint(item: dict[str, Any]) -> str:
    url = str(item.get("url") or item.get("archive_url") or "").strip().lower()
    title = str(item.get("title") or item.get("headline") or "").strip().lower()
    published = str(item.get("published_at") or item.get("date") or "").strip()
    raw = url or f"{title}|{published}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def classify_impact(item: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(item.get("title") or item.get("headline") or ""),
            str(item.get("summary") or ""),
            " ".join(str(tag) for tag in (item.get("tags") or [])),
            str(item.get("category") or ""),
        ]
    ).lower()
    if any(term in haystack for term in _HIGH_TERMS):
        return IMPACT_HIGH
    if any(term in haystack for term in _MEDIUM_TERMS):
        return IMPACT_MEDIUM
    # Explicit tags from the news feed.
    tags = {str(tag).lower() for tag in (item.get("tags") or [])}
    if tags & {"funding", "m&a", "lawsuit", "regulatory"}:
        return IMPACT_HIGH
    if tags & {"product", "earnings", "hiring"}:
        return IMPACT_MEDIUM
    return IMPACT_LOW


def recommended_action(impact: str) -> str:
    if impact == IMPACT_HIGH:
        return ACTION_REPORT
    if impact == IMPACT_MEDIUM:
        return ACTION_INVESTIGATE
    return ACTION_NONE


def list_updates(company_id: str, *, limit: int = 50) -> dict:
    with _LOCK:
        payload = _load(company_id)
    items = list(payload.get("items") or [])
    items.sort(
        key=lambda row: str(row.get("published_at") or row.get("captured_at") or ""),
        reverse=True,
    )
    auto_runs = list(payload.get("auto_runs") or [])
    auto_runs.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return {
        "company_id": company_id,
        "items": items[: max(1, int(limit or 50))],
        "auto_runs": auto_runs[:20],
        "latest_auto_run": auto_runs[0] if auto_runs else None,
        "last_synced_at": payload.get("last_synced_at"),
        "counts": {
            "total": len(payload.get("items") or []),
            "low": sum(1 for row in payload.get("items") or [] if row.get("impact") == IMPACT_LOW),
            "medium": sum(
                1 for row in payload.get("items") or [] if row.get("impact") == IMPACT_MEDIUM
            ),
            "high": sum(1 for row in payload.get("items") or [] if row.get("impact") == IMPACT_HIGH),
        },
    }


def render_research_news_md(
    company_id: str,
    *,
    limit: int = 20,
    max_chars: int = 6000,
) -> str | None:
    """Markdown digest of tracked news for the memo pipeline's research
    folder. English on purpose — it feeds English prompts. ``None`` when
    the store has no items."""
    listed = list_updates(company_id, limit=limit)
    items = listed.get("items") or []
    if not items:
        return None
    lines = [
        "# Recent tracked news",
        "",
        "Auto-captured tracked-news digest; impact classified low/medium/high.",
        "",
    ]
    for item in items:
        date = str(item.get("published_at") or item.get("captured_at") or "")[:10]
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        source = str(item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        tail = "; ".join(part for part in (source, url) if part)
        line = f"- [{date}] ({item.get('impact') or IMPACT_LOW}) {title}"
        if summary:
            line += f" — {summary}"
        if tail:
            line += f" ({tail})"
        lines.append(line)
    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n(recent news truncated)"
    return text


def record_auto_run(
    company_id: str,
    *,
    action: str,
    news_ids: list[str] | None = None,
    news_titles: list[str] | None = None,
    surface: str = "memo_studio",
    status: str = "completed",
) -> dict:
    with _LOCK:
        payload = _load(company_id)
        entry = {
            "id": hashlib.sha256(f"{company_id}:{action}:{_now()}".encode()).hexdigest()[:16],
            "action": action,
            "surface": surface,
            "status": status,
            "news_ids": list(news_ids or []),
            "news_titles": list(news_titles or [])[:6],
            "updated_at": _now(),
            "label": _auto_run_label(action, news_titles or []),
        }
        auto_runs = list(payload.get("auto_runs") or [])
        auto_runs.insert(0, entry)
        payload["auto_runs"] = auto_runs[:50]
        _save(company_id, payload)
        return entry


def _auto_run_label(action: str, titles: list[str]) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    affected = "; ".join(titles[:2]) if titles else "tracked news"
    if action == ACTION_REPORT:
        kind = "Full report regenerated"
    elif action == ACTION_INVESTIGATE:
        kind = "Deep investigate refreshed"
    else:
        kind = "Workspace updated"
    return f"{kind} at {when}, affected by: {affected}"


def get_watchlist() -> list[str]:
    with _LOCK:
        if not watchlist_path().exists():
            return []
        try:
            payload = json.loads(watchlist_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        ids = payload.get("company_ids") if isinstance(payload, dict) else payload
        if not isinstance(ids, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for raw in ids:
            cid = str(raw or "").strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(cid)
        return out


def sync_watchlist(company_ids: list[str]) -> dict:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in company_ids or []:
        cid = str(raw or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        normalized.append(cid)
    payload = {
        "schema_version": 1,
        "updated_at": _now(),
        "company_ids": normalized,
    }
    with _LOCK:
        watchlist_path().parent.mkdir(parents=True, exist_ok=True)
        watchlist_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {"company_ids": normalized, "updated_at": payload["updated_at"]}


def remove_from_watchlist(company_id: str) -> None:
    cid = str(company_id or "").strip()
    if not cid:
        return
    with _LOCK:
        current = get_watchlist()
        if cid not in current:
            return
        sync_watchlist([row for row in current if row != cid])


def company_awaiting_studio(company_id: str) -> bool:
    """True while a live Memo Studio review is parked for the company.

    An auto-run must never snapshot-replace cards a human is reviewing,
    so both auto actions skip (stay ``recommended``) in this state — the
    human can still click Run now, which is an explicit choice.
    Dismissed or superseded parked runs don't count.
    """
    cid = str(company_id or "").strip()
    if not cid:
        return False
    for report in storage.list_reports():
        if str(report.get("company_id") or "") != cid:
            continue
        if report.get("dismissed_at") or report.get("superseded_by"):
            continue
        if str(report.get("status") or "").strip().lower() == "awaiting_studio":
            return True
    return False


def company_has_active_work(company_id: str) -> bool:
    cid = str(company_id or "").strip()
    if not cid:
        return False
    for report in storage.list_reports():
        if str(report.get("company_id") or "") != cid:
            continue
        status = str(report.get("status") or "").strip().lower()
        if status in RUNNING_REPORT_STATUSES:
            return True
    from . import serena_analysis

    session = serena_analysis.get_current_session(cid, create=False)
    if isinstance(session, dict):
        tool_run = (session.get("tool_runs") or {}).get("strategic_risk_mapper") or {}
        if str(tool_run.get("status") or "").lower() == "running":
            return True
    return False


def _patch_auto_run(company_id: str, auto_run_id: str, patch: dict[str, Any]) -> dict | None:
    with _LOCK:
        payload = _load(company_id)
        auto_runs = list(payload.get("auto_runs") or [])
        updated: dict | None = None
        for index, row in enumerate(auto_runs):
            if str(row.get("id") or "") != str(auto_run_id):
                continue
            merged = {**row, **patch, "updated_at": _now()}
            auto_runs[index] = merged
            updated = merged
            break
        if updated is None:
            return None
        payload["auto_runs"] = auto_runs
        _save(company_id, payload)
        return updated


def _retire_stale_memo_runs(company_id: str, new_report_id: str | None) -> None:
    """Retire older failed/parked memo runs once a new run claims the company."""
    try:
        from . import api

        api._supersede_stale_memo_failures(company_id, new_report_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "supersede after auto-run dispatch failed for %s", company_id
        )


def execute_auto_run(
    company_id: str,
    auto_run_id: str | None = None,
    *,
    allow_parked_review: bool = False,
) -> dict:
    """Launch the recommended auto action (investigate or full report).

    ``allow_parked_review`` bypasses the awaiting-studio guard — it is the
    human's "I reviewed the cards" acknowledgment from the manual Run now
    flow. The background sync loop never sets it.
    """
    if storage.get_company(company_id) is None:
        raise ValueError("company_not_found")
    listed = list_updates(company_id)
    target = None
    if auto_run_id:
        for row in listed.get("auto_runs") or []:
            if str(row.get("id") or "") == str(auto_run_id):
                target = row
                break
    else:
        for row in listed.get("auto_runs") or []:
            if str(row.get("status") or "") == "recommended":
                target = row
                break
    if target is None:
        return {"executed": False, "reason": "no_recommended_auto_run"}
    if str(target.get("status") or "") not in {"recommended"}:
        return {"executed": False, "reason": "auto_run_not_recommended", "auto_run": target}
    action = str(target.get("action") or ACTION_NONE)
    if action == ACTION_NONE:
        _patch_auto_run(company_id, target["id"], {"status": "skipped"})
        return {"executed": False, "reason": "action_none", "auto_run": target}
    if company_has_active_work(company_id):
        return {"executed": False, "reason": "company_busy", "auto_run": target}
    if not allow_parked_review and company_awaiting_studio(company_id):
        return {
            "executed": False,
            "reason": "awaiting_studio_review",
            "auto_run": target,
        }
    # Auto-runs live in their own small reserved lane (they never compete
    # with the user's parallel-run cap). When the lane is full, stay
    # "recommended" — the background loop simply retries next cycle.
    from . import memo_analysis

    if not memo_analysis.reserved_run_slots_available():
        return {"executed": False, "reason": "run_slots_full", "auto_run": target}

    run_id = str(target["id"])
    if action == ACTION_INVESTIGATE:
        from . import memo_prep

        # Medium impact reruns the product's Deep Investigate: the Memo
        # Studio investigation (Phase 1-2 + card refresh). It requires
        # the spine-lite architecture; without the flag the run would
        # dispatch and fail downstream, so skip and stay recommended.
        if not memo_flags.enabled("BSH_MEMO_ENGLISH_PARALLEL"):
            return {
                "executed": False,
                "reason": "studio_requires_parallel",
                "auto_run": target,
            }
        try:
            result = memo_prep.bootstrap_memo_run(
                company_id,
                memo_mode="studio",
                trigger="tracking_auto_run",
                auto_run_id=run_id,
                # A Memo Studio investigation writes the standard memo (its
                # spine is composed from the v1 studio cards).
                structure_version="v1",
                structure_version_source="studio",
            )
        except ValueError as exc:
            _patch_auto_run(
                company_id,
                run_id,
                {"status": "failed", "error": str(exc)},
            )
            raise
        if result.get("failed"):
            _patch_auto_run(
                company_id,
                run_id,
                {
                    "status": "failed",
                    "error": (result.get("scope_check") or {}).get("reason")
                    or "scope_check_failed",
                    "job_ref": {
                        "kind": "memo_report",
                        "report_id": result.get("report_id"),
                    },
                },
            )
            return {
                "executed": False,
                "reason": "scope_check_failed",
                "auto_run": list_updates(company_id).get("latest_auto_run"),
            }
        report_id = str(result.get("report_id") or "")
        _snapshot_report_identity(report_id)
        _retire_stale_memo_runs(company_id, report_id)
        updated = _patch_auto_run(
            company_id,
            run_id,
            {
                # surface stays "overview" and action stays
                # deep_investigate so the Overview auto-updated badge
                # keeps firing.
                "status": "running",
                "surface": "overview",
                "trigger": "auto",
                "job_ref": {"kind": "memo_report", "report_id": report_id},
            },
        )
        return {
            "executed": True,
            "action": action,
            "auto_run": updated,
            "report_id": report_id,
        }

    if action == ACTION_REPORT:
        from . import memo_prep, product_store

        # No person started this run: the template is the workspace default
        # (BSH_MEMO_STRUCTURE_V2), on the record before the worker starts.
        template, template_source = product_store.effective_memo_template(None)
        try:
            result = memo_prep.bootstrap_memo_run(
                company_id,
                trigger="tracking_auto_run",
                auto_run_id=run_id,
                structure_version=product_store.MEMO_TEMPLATE_STRUCTURE_VERSIONS[template],
                structure_version_source=template_source,
            )
        except ValueError as exc:
            _patch_auto_run(
                company_id,
                run_id,
                {"status": "failed", "error": str(exc)},
            )
            raise
        if result.get("failed"):
            _patch_auto_run(
                company_id,
                run_id,
                {
                    "status": "failed",
                    "error": (result.get("scope_check") or {}).get("reason")
                    or "scope_check_failed",
                    "job_ref": {
                        "kind": "memo_report",
                        "report_id": result.get("report_id"),
                    },
                },
            )
            return {
                "executed": False,
                "reason": "scope_check_failed",
                "auto_run": list_updates(company_id).get("latest_auto_run"),
            }
        report_id = str(result.get("report_id") or "")
        _snapshot_report_identity(report_id)
        _retire_stale_memo_runs(company_id, report_id)
        updated = _patch_auto_run(
            company_id,
            run_id,
            {
                "status": "running",
                "surface": "memo_studio",
                "trigger": "auto",
                "job_ref": {"kind": "memo_report", "report_id": report_id},
            },
        )
        return {"executed": True, "action": action, "auto_run": updated, "report_id": report_id}

    return {"executed": False, "reason": "unknown_action", "auto_run": target}


def _snapshot_report_identity(report_id: str) -> None:
    """Keep the company's identity (name, ticker, logo domain) with an
    auto-run's report, as a person-started report does
    (``report_reader.snapshot_company_identity``). Best-effort: a snapshot
    failure never stops the run."""
    if not report_id:
        return
    try:
        from . import report_reader

        report_reader.snapshot_company_identity(report_id)
    except Exception:  # noqa: BLE001
        logger.warning("identity snapshot failed for auto-run report %s", report_id, exc_info=True)


def complete_auto_run_for_job(
    company_id: str,
    *,
    job_kind: str,
    job_id: str | None = None,
    report_id: str | None = None,
    tool_name: str | None = None,
    success: bool = True,
    error: str | None = None,
) -> dict | None:
    """Mark a running auto-run complete when its background job finishes."""
    cid = str(company_id or "").strip()
    if not cid:
        return None
    with _LOCK:
        payload = _load(cid)
        auto_runs = list(payload.get("auto_runs") or [])
        match: dict | None = None
        for row in auto_runs:
            if str(row.get("status") or "") != "running":
                continue
            job_ref = row.get("job_ref") if isinstance(row.get("job_ref"), dict) else {}
            if str(job_ref.get("kind") or "") != str(job_kind or ""):
                continue
            if job_kind == "memo_report":
                if report_id and str(job_ref.get("report_id") or "") == str(report_id):
                    match = row
                    break
            elif job_kind == "serena_tool":
                if tool_name and str(job_ref.get("tool_name") or "") == str(tool_name):
                    match = row
                    break
            elif job_id and str(job_ref.get("job_id") or "") == str(job_id):
                match = row
                break
        if match is None:
            return None
        titles = list(match.get("news_titles") or [])
        action = str(match.get("action") or ACTION_NONE)
        status = "completed" if success else "failed"
        merged = {
            **match,
            "status": status,
            "updated_at": _now(),
            "label": _auto_run_label(action, titles),
        }
        if not success:
            merged["error"] = str(error or merged.get("error") or "background_job_failed")
        for index, row in enumerate(auto_runs):
            if str(row.get("id") or "") == str(match.get("id")):
                auto_runs[index] = merged
                break
        payload["auto_runs"] = auto_runs
        _save(cid, payload)
        return merged


def refresh_company_news(company_id: str) -> dict:
    """Best-effort Claude deep-search so ``recent_news`` is refreshed on disk.

    Sync then reads the updated feed. Failures are soft — callers still sync
    whatever news is already on the company record.
    """
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError("company_not_found")
    name = str(company.get("name") or "").strip()
    if not name:
        return {"refreshed": False, "reason": "no_name"}
    ticker = str(company.get("ticker") or "").strip()
    query = ticker or name
    try:
        from . import companies_ai

        # The tracker's search runs on Sonnet at medium effort.
        result = companies_ai.deep_search(
            query,
            force_refresh=True,
            only_company_id=company_id,
            model=news_model(),
            effort=news_effort(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("tracking news refresh failed for %s", company_id)
        return {"refreshed": False, "error": str(exc)}
    matches = result.get("matches") or []
    hit = next((row for row in matches if row.get("id") == company_id), None)
    return {
        "refreshed": hit is not None or result.get("source") != "claude_code",
        "source": result.get("source"),
        "match_count": len(matches),
    }


def sync_all_tracked(
    *,
    company_ids: list[str] | None = None,
    lang: str | None = None,
    mark_auto: bool = True,
    execute: bool = False,
    refresh_news: bool | None = None,
) -> dict:
    if refresh_news is None:
        refresh_news = os.environ.get("BSH_TRACKING_REFRESH_NEWS", "1") == "1"
    ids = list(company_ids or get_watchlist())
    results: list[dict] = []
    for company_id in ids:
        if storage.get_company(company_id) is None:
            results.append({"company_id": company_id, "skipped": True, "reason": "missing"})
            continue
        try:
            summary = sync_from_news_feed(
                company_id,
                lang=lang,
                mark_auto=mark_auto,
                execute=execute,
                refresh_news=refresh_news,
            )
            results.append({"company_id": company_id, **summary})
        except ValueError as exc:
            results.append({"company_id": company_id, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("tracking sync failed for %s", company_id)
            results.append({"company_id": company_id, "error": str(exc)})
    executed = sum(
        1
        for row in results
        if isinstance(row.get("executed_auto_run"), dict)
        and row["executed_auto_run"].get("executed")
    )
    created = sum(int(row.get("created") or 0) for row in results)
    refreshed = sum(1 for row in results if (row.get("news_refresh") or {}).get("refreshed"))
    return {
        "synced_at": _now(),
        "company_count": len(ids),
        "created_total": created,
        "executed_total": executed,
        "refreshed_total": refreshed,
        "companies": results,
    }


def _settings_path() -> Path:
    return storage.DATA_DIR / "settings" / "tracking_settings.json"


def _sync_state_path() -> Path:
    return storage.DATA_DIR / "settings" / "tracking_sync_state.json"


def _read_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def auto_apply_enabled() -> bool:
    """Whether the background sync launches recommended runs on its own.

    The toggle in the News tab decides. Until someone sets it,
    ``BSH_TRACKING_AUTO_EXECUTE`` supplies the default, which is off."""
    stored = _read_json_file(_settings_path()).get("auto_apply")
    if isinstance(stored, bool):
        return stored
    return os.environ.get("BSH_TRACKING_AUTO_EXECUTE", "0") == "1"


def set_auto_apply(enabled: bool, *, updated_by: str | None = None) -> dict:
    with _LOCK:
        _write_json_file(
            _settings_path(),
            {
                "auto_apply": bool(enabled),
                "updated_at": _now(),
                "updated_by": updated_by,
            },
        )
    return get_settings()


def last_sync_at() -> datetime | None:
    raw = str(_read_json_file(_sync_state_path()).get("last_sync_at") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _mark_synced(at: datetime | None = None) -> None:
    moment = at or datetime.now(timezone.utc)
    _write_json_file(_sync_state_path(), {"last_sync_at": moment.isoformat()})


def seconds_until_sync_due() -> float | None:
    """Seconds until the background sync is due; None when it is manual.

    A server that never synced waits a full interval rather than firing at
    startup — restarting must not cost tokens. The clock is persisted, so
    restarts don't reset it."""
    interval = sync_interval_seconds()
    if interval <= 0:
        return None
    base = last_sync_at() or datetime.now(timezone.utc)
    due = base + timedelta(seconds=interval)
    return (due - datetime.now(timezone.utc)).total_seconds()


def start_clock_if_unset() -> None:
    """Stamp the clock the first time the loop sees this install."""
    if last_sync_at() is None:
        _mark_synced()


def get_settings() -> dict:
    """Schedule, models and the auto-apply switch, for the News tab."""
    stored = _read_json_file(_settings_path())
    last = last_sync_at()
    interval = sync_interval_seconds()
    next_at = (
        (last or datetime.now(timezone.utc)) + timedelta(seconds=interval)
        if interval > 0
        else None
    )
    return {
        "auto_apply": auto_apply_enabled(),
        "auto_apply_updated_at": stored.get("updated_at"),
        "auto_apply_updated_by": stored.get("updated_by"),
        "auto_sync": os.environ.get("BSH_TRACKING_AUTO_SYNC", "1") == "1",
        "interval_hours": round(interval / 3600, 2),
        "cadence": sync_cadence(),
        "cadence_choices": list(auto_update.CADENCES),
        "last_sync_at": last.isoformat() if last else None,
        "next_sync_at": next_at.isoformat() if next_at else None,
        "news_model": news_model(),
        "news_effort": news_effort(),
        "impact_model": impact_model(),
        "impact_effort": impact_effort(),
    }


def run_scheduled_sync() -> dict:
    """One background round over the watchlist. Recommended runs launch only
    when auto-apply is on. Starting the round restarts the clock."""
    _mark_synced()
    summary = sync_all_tracked(mark_auto=True, execute=auto_apply_enabled())
    if (
        summary.get("created_total")
        or summary.get("executed_total")
        or summary.get("refreshed_total")
    ):
        logger.info(
            "Tracking sync: companies=%s refreshed=%s created=%s executed=%s",
            summary.get("company_count"),
            summary.get("refreshed_total"),
            summary.get("created_total"),
            summary.get("executed_total"),
        )
    return summary


def start_tracking_sync_loop() -> None:
    """Sync the watchlist on the cadence picked in the auto-update bar
    (12 hours by default; ``manual`` never fires). The loop runs even on
    ``manual``, so moving the bar takes effect without a restart.
    ``BSH_TRACKING_AUTO_SYNC=0`` keeps the thread from starting at all."""
    enabled = os.environ.get("BSH_TRACKING_AUTO_SYNC", "1") == "1"
    if not enabled:
        return
    global _SYNC_THREAD_STARTED
    with _SYNC_THREAD_LOCK:
        if _SYNC_THREAD_STARTED:
            return
        _SYNC_THREAD_STARTED = True

    def _loop() -> None:
        start_clock_if_unset()
        while True:
            # Re-read every tick: the bar can move at any time.
            wait = seconds_until_sync_due()
            if wait is None:
                # Manual: sleep and look again in case the bar moved.
                time.sleep(SYNC_CHECK_SECONDS)
                continue
            if wait <= 0:
                try:
                    run_scheduled_sync()
                except Exception:  # noqa: BLE001
                    logger.exception("background tracking sync failed")
                wait = float(SYNC_CHECK_SECONDS)
            time.sleep(max(30.0, min(float(SYNC_CHECK_SECONDS), wait)))

    threading.Thread(target=_loop, name="tracking-sync", daemon=True).start()


def _decision_retro_enabled() -> bool:
    return os.environ.get("BSH_TRACKING_DECISION_RETRO", "1") == "1"


_DECISION_RETRO_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assessments": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "decision_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["still_right", "questionable", "looks_wrong"],
                    },
                    "rationale_en": {"type": "string", "maxLength": 600},
                    "rationale_zh": {"type": "string", "maxLength": 600},
                    "news_ids": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "decision_id",
                    "verdict",
                    "rationale_en",
                    "rationale_zh",
                ],
            },
        },
    },
    "required": ["assessments"],
}

_DECISION_RETRO_SYSTEM_PROMPT = """\
You assess whether an investment firm's recorded decisions still look
right, given news that just landed. For each decision, weigh only the
provided news items against the decision's stated reason and date:
- still_right: the news supports or does not challenge the reasoning.
- questionable: the news meaningfully weakens the reasoning.
- looks_wrong: the news contradicts the reasoning or shows the outcome
  going clearly the other way.
Write BOTH rationales: `rationale_en` (concise English, 1-2 sentences,
name the news that drove the verdict) and `rationale_zh` (the same
content in natural simplified Chinese, not a literal translation).
Reference triggering items by their ids in `news_ids`. Assess every
decision you are given, and only those."""


def _assess_decisions_from_news(company_id: str, new_items: list[dict]) -> None:
    """Retrospective pass: does each recorded decision still look right?

    One tool-free structured call, fired only when new medium/high-impact
    items landed and the company has decisions. Best-effort by contract —
    any failure is logged and the sync proceeds untouched. Never called
    while the tracking ``_LOCK`` is held (the Claude call takes minutes).
    """
    try:
        from . import claude_runner, decisions_store

        decisions = decisions_store.list_decisions(company_id).get("items") or []
        if not decisions or not claude_runner.is_available():
            return
        by_id = {str(item.get("id")): item for item in new_items}
        decisions_payload = [
            {
                "decision_id": row.get("id"),
                "verdict": row.get("verdict"),
                "decided_at": row.get("decided_at"),
                "reason": row.get("explanation"),
            }
            for row in decisions
        ]
        news_payload = [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "published_at": item.get("published_at"),
                "impact": item.get("impact"),
            }
            for item in new_items
        ]
        user_prompt = (
            "Recorded decisions:\n"
            + json.dumps(decisions_payload, ensure_ascii=False, indent=2)
            + "\n\nNew tracked news:\n"
            + json.dumps(news_payload, ensure_ascii=False, indent=2)
        )
        data, error = claude_runner.run_structured_prompt(
            system_prompt=_DECISION_RETRO_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=_DECISION_RETRO_SCHEMA,
            name="decision_retrospective",
            timeout_sec=180,
            model=impact_model(),
            effort=impact_effort(),
            tools="",
        )
        if error or not isinstance(data, dict):
            logger.warning(
                "decision retrospective failed for %s: %s", company_id, error
            )
            return
        assessments = []
        for row in data.get("assessments") or []:
            if not isinstance(row, dict):
                continue
            news_ids = [
                str(item) for item in (row.get("news_ids") or []) if str(item) in by_id
            ]
            assessments.append(
                {
                    **row,
                    "news_ids": news_ids,
                    "news_titles": [
                        str(by_id[item].get("title") or "") for item in news_ids
                    ],
                }
            )
        decisions_store.append_retrospectives(
            company_id, assessments, source="tracking_sync"
        )
    except Exception:  # noqa: BLE001
        logger.exception("decision retrospective crashed for %s", company_id)


_IMPACT_SYSTEM_PROMPT = """\
You judge whether new news items matter to an investment case in ONE
company. For each item, decide its impact on the company's valuation,
competitive position, financing, leadership or risk:
- high: likely changes the investment view or the memo's numbers, such as
  a financing round or valuation mark, M&A, an IPO filing, a major
  customer won or lost, a lawsuit or regulatory action with teeth, a top
  leadership change, or results far from expectations.
- medium: worth recording and may refine the memo, such as a notable
  product launch, a partnership with real revenue, a senior hire, or
  guidance that confirms the plan.
- low: does not change the view, such as routine announcements,
  conference appearances, opinion pieces, rehashes of old news, or items
  about a different company with a similar name.
Judge the substance, not the keywords. Give a one-sentence reason for
each item and reference it by its id. Assess every item given, and only
those."""

_IMPACT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "maxItems": IMPACT_MAX_ITEMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "impact": {
                        "type": "string",
                        "enum": [IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH],
                    },
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["id", "impact", "reason"],
            },
        },
    },
    "required": ["items"],
}


def assess_news_impact(company: dict, rows: list[dict]) -> dict[str, dict]:
    """Opus judges which new items matter: one tool-free call per company.

    ``rows`` carry ``id`` (the fingerprint). Returns ``{id: {impact,
    reason}}``. Empty when the judgment is off, Claude is unavailable or the
    call fails; keyword rules then decide. Never called while the tracking
    ``_LOCK`` is held, since the call takes a while.
    """
    if not rows or not _impact_ai_enabled():
        return {}
    company_id = str(company.get("id") or "")
    try:
        from . import claude_runner

        if not claude_runner.is_available():
            return {}
        judged = rows[:IMPACT_MAX_ITEMS]
        lines = [f"Company: {company.get('name') or company_id}"]
        if company.get("ticker"):
            lines.append(f"Ticker: {company['ticker']}")
        for label, key in (("Industry", "industry"), ("What it does", "description")):
            value = str(company.get(key) or "").strip()
            if value:
                lines.append(f"{label}: {value[:400]}")
        user_prompt = (
            "\n".join(lines)
            + "\n\nNew news items:\n"
            + json.dumps(judged, ensure_ascii=False, indent=2)
        )
        data, error = claude_runner.run_structured_prompt(
            system_prompt=_IMPACT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=_IMPACT_SCHEMA,
            name="tracking_impact",
            timeout_sec=300,
            model=impact_model(),
            effort=impact_effort(),
            tools="",
        )
        if error or not isinstance(data, dict):
            logger.warning("tracking impact judgment failed for %s: %s", company_id, error)
            return {}
        valid = {str(row.get("id")) for row in judged}
        verdicts: dict[str, dict] = {}
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            impact = str(item.get("impact") or "").strip().lower()
            if item_id in valid and impact in {IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH}:
                verdicts[item_id] = {
                    "impact": impact,
                    "reason": str(item.get("reason") or "").strip()[:300],
                }
        return verdicts
    except Exception:  # noqa: BLE001
        logger.exception("tracking impact judgment crashed for %s", company_id)
        return {}


def _known_fingerprints(payload: dict) -> set[str]:
    return {
        str(item.get("fingerprint") or item.get("id"))
        for item in (payload.get("items") or [])
    }


def sync_from_news_feed(
    company_id: str,
    *,
    lang: str | None = None,
    mark_auto: bool = False,
    execute: bool = False,
    refresh_news: bool = False,
) -> dict:
    """Optionally refresh company news, then ingest into the updates store."""
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError("company_not_found")
    news_refresh = None
    if refresh_news:
        news_refresh = refresh_company_news(company_id)
    feed = context_store.company_news(company_id, lang=lang)
    rows = list(feed.get("rows") or [])

    # Find the new rows under the lock, then judge them outside it.
    with _LOCK:
        seen = _known_fingerprints(_load(company_id))
    candidates: list[tuple[str, dict]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fp = fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        candidates.append((fp, row))
    verdicts = assess_news_impact(
        company,
        [
            {
                "id": fp,
                "title": row.get("title") or row.get("headline"),
                "summary": row.get("summary"),
                "published_at": row.get("published_at") or row.get("date"),
                "source": row.get("source")
                or (row.get("provenance") or {}).get("origin"),
                "category": row.get("category"),
            }
            for fp, row in candidates
        ],
    )

    created = 0
    with _LOCK:
        payload = _load(company_id)
        # Re-read: a concurrent sync may have stored some of these meanwhile.
        known = _known_fingerprints(payload)
        items = list(payload.get("items") or [])
        new_medium_or_high: list[dict] = []
        for fp, row in candidates:
            if fp in known:
                continue
            verdict = verdicts.get(fp)
            impact = verdict["impact"] if verdict else classify_impact(row)
            action = recommended_action(impact)
            entry = {
                "id": fp,
                "fingerprint": fp,
                "title": row.get("title") or row.get("headline"),
                "summary": row.get("summary"),
                "url": row.get("url") or row.get("archive_url"),
                "published_at": row.get("published_at") or row.get("date"),
                "category": row.get("category"),
                "tags": list(row.get("tags") or []),
                "impact": impact,
                "impact_source": "ai" if verdict else "keywords",
                "impact_reason": verdict["reason"] if verdict else None,
                "recommended_action": action,
                "captured_at": _now(),
                "source": row.get("source")
                or (row.get("provenance") or {}).get("origin"),
            }
            items.append(entry)
            known.add(fp)
            created += 1
            if impact in {IMPACT_MEDIUM, IMPACT_HIGH}:
                new_medium_or_high.append(entry)
        payload["items"] = items
        payload["last_synced_at"] = _now()

        auto_run = None
        if mark_auto and new_medium_or_high:
            # Highest impact among new items decides the recommended action.
            if any(row["impact"] == IMPACT_HIGH for row in new_medium_or_high):
                action = ACTION_REPORT
            else:
                action = ACTION_INVESTIGATE
            titles = [str(row.get("title") or "") for row in new_medium_or_high if row.get("title")]
            auto_run = {
                "id": hashlib.sha256(
                    f"{company_id}:{action}:{payload['last_synced_at']}".encode()
                ).hexdigest()[:16],
                "action": action,
                "surface": "memo_studio" if action == ACTION_REPORT else "overview",
                "status": "recommended",
                "news_ids": [row["id"] for row in new_medium_or_high],
                "news_titles": titles[:6],
                "updated_at": _now(),
                "label": _auto_run_label(action, titles),
            }
            auto_runs = list(payload.get("auto_runs") or [])
            auto_runs.insert(0, auto_run)
            payload["auto_runs"] = auto_runs[:50]

        _save(company_id, payload)

    # Outside _LOCK: the retrospective makes a Claude call, and holding the
    # tracking lock for minutes would freeze every other company's sync.
    if new_medium_or_high and _decision_retro_enabled():
        _assess_decisions_from_news(company_id, new_medium_or_high)

    summary = list_updates(company_id)
    summary["created"] = created
    summary["news_refresh"] = news_refresh
    summary["recommended_auto_run"] = auto_run if mark_auto else None
    executed = None
    if execute and auto_run is not None:
        executed = execute_auto_run(company_id, auto_run["id"])
        summary = list_updates(company_id)
        summary["created"] = created
        summary["news_refresh"] = news_refresh
        summary["recommended_auto_run"] = auto_run
    summary["executed_auto_run"] = executed
    return summary


auto_update.register_clock(AUTO_UPDATE_CHANNEL, last_sync_at)
