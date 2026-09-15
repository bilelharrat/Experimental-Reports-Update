"""Tracked-company news updates — ingest, dedupe, impact, auto-run labels.

Pipeline:
1. Ingest news for a company (from the existing news feed).
2. Fingerprint + dedupe so old items are not re-processed.
3. Classify impact (low / medium / high).
4. Record recommended / executed auto actions (investigate / report).
5. Optionally launch Deep Investigate (medium) or full report (high).
6. Surface labels for Overview / Memo Studio when an auto-run applied.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import context_store, storage

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
        if os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") != "1":
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
        from . import memo_prep

        try:
            result = memo_prep.bootstrap_memo_run(
                company_id,
                trigger="tracking_auto_run",
                auto_run_id=run_id,
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

        result = companies_ai.deep_search(
            query,
            force_refresh=True,
            only_company_id=company_id,
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


def start_tracking_sync_loop() -> None:
    """Periodically sync + optionally execute auto-runs for the watchlist."""
    enabled = os.environ.get("BSH_TRACKING_AUTO_SYNC", "1") == "1"
    if not enabled:
        return
    global _SYNC_THREAD_STARTED
    with _SYNC_THREAD_LOCK:
        if _SYNC_THREAD_STARTED:
            return
        _SYNC_THREAD_STARTED = True
    interval = float(os.environ.get("BSH_TRACKING_SYNC_INTERVAL_SECONDS", "900"))
    execute = os.environ.get("BSH_TRACKING_AUTO_EXECUTE", "1") == "1"

    def _loop() -> None:
        while True:
            time.sleep(max(60.0, interval))
            try:
                summary = sync_all_tracked(mark_auto=True, execute=execute)
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
            except Exception:  # noqa: BLE001
                logger.exception("background tracking sync failed")

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


def sync_from_news_feed(
    company_id: str,
    *,
    lang: str | None = None,
    mark_auto: bool = False,
    execute: bool = False,
    refresh_news: bool = False,
) -> dict:
    """Optionally refresh company news, then ingest into the updates store."""
    if storage.get_company(company_id) is None:
        raise ValueError("company_not_found")
    news_refresh = None
    if refresh_news:
        news_refresh = refresh_company_news(company_id)
    feed = context_store.company_news(company_id, lang=lang)
    rows = list(feed.get("rows") or [])
    created = 0
    with _LOCK:
        payload = _load(company_id)
        known = {
            str(item.get("fingerprint") or item.get("id"))
            for item in (payload.get("items") or [])
        }
        items = list(payload.get("items") or [])
        new_medium_or_high: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fp = fingerprint(row)
            if fp in known:
                continue
            impact = classify_impact(row)
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
                "recommended_action": action,
                "captured_at": _now(),
                "source": row.get("source") or row.get("provenance", {}).get("origin"),
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
