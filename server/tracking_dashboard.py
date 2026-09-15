"""Research-state rollup behind the Tracking dashboard.

The dashboard answers one question: across the companies an analyst
follows, where is research incomplete, stale, or broken? Answering that
per company means reading the memo session, the evidence matrix, the
report list, the document inventory and the news feed. Fanning those out
from the browser is one request per company per source, so the join
happens here and ships as a single response.

The follow list lives in browser storage, so callers pass the ids they
care about — the server does not own a watchlist.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import (
    context_store,
    decisions_store,
    evidence_matrix,
    evidence_store,
    serena_analysis,
    storage,
    thesis_store,
)

# Guardrail on fan-out: each company costs five store reads, so an
# unbounded id list would let one request walk the entire workspace.
MAX_COMPANIES = 60

NEWS_WINDOW_DAYS = 7

# One next action per company. A pile of findings is what buried the
# two broken memos under 38 empty-state rows on the first dashboard.
MAX_ATTENTION_PER_COMPANY = 1

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
BUCKET_RANK = {
    "needs_action": 0,
    "in_progress": 1,
    "not_started": 2,
    "clear": 3,
}

# Memo runs that are still moving. Anything else terminal is either a
# `failed_*` status or one of the `complete*` pair.
RUNNING_REPORT_STATUSES = {
    "queued",
    "prepping",
    "ready_for_analysis",
    "analyzing",
    "running",
}

RESEARCHED_RISK_STATUSES = {"researched"}
REVIEW_RISK_STATUSES = {"needs_review"}

# Deal lifecycle, in pipeline order. Derived once here so the web board and
# the native Mac board never disagree about where a company sits.
LIFECYCLE_STAGES = (
    "sourcing",
    "screening",
    "diligence",
    "ic",
    "portfolio",
    "watch",
    "passed",
)
DECISION_STAGES = {"invest": "portfolio", "pass": "passed", "watch": "watch"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _newest(*values: Any) -> datetime | None:
    parsed = [dt for dt in (_parse_iso(v) for v in values) if dt is not None]
    return max(parsed) if parsed else None


def _price(company: dict) -> dict | None:
    """Relative performance for public names, or None for private ones."""
    snapshot = company.get("trader_snapshot")
    if not isinstance(snapshot, dict):
        return None
    card = snapshot.get("price_card")
    if not isinstance(card, dict):
        return None
    moves = {
        name: _as_float(card.get(name))
        for name in (
            "change_pct_1d",
            "change_pct_5d",
            "change_pct_30d",
            "vs_sector_30d_pct",
            "vs_sp500_30d_pct",
        )
    }
    if all(value is None for value in moves.values()):
        return None
    return {
        **moves,
        "last_price": _as_float(card.get("last_price")),
        "currency": card.get("currency") or None,
        "as_of": card.get("as_of") or None,
    }


def _risk_counts(session: dict | None) -> dict:
    counts = {
        "total": 0,
        "researched": 0,
        "needs_review": 0,
        "unresearched": 0,
        "high_severity_open": 0,
    }
    artifacts = (session or {}).get("artifacts")
    if not isinstance(artifacts, dict):
        return counts
    wrapper = artifacts.get("strategic_risks")
    if not isinstance(wrapper, dict):
        return counts
    for risk in wrapper.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        counts["total"] += 1
        status = str(risk.get("status") or "").strip().lower()
        if status in RESEARCHED_RISK_STATUSES:
            counts["researched"] += 1
            continue
        # Anything not explicitly researched is still open work; treating
        # an unrecognized status as done would hide it from the queue.
        if status in REVIEW_RISK_STATUSES:
            counts["needs_review"] += 1
        else:
            counts["unresearched"] += 1
        if str(risk.get("severity") or "").strip().lower() == "high":
            counts["high_severity_open"] += 1
    return counts


def _evidence_counts(matrix: dict | None) -> dict:
    counts = {
        "total": 0,
        "supported": 0,
        "partial": 0,
        "missing": 0,
        "contradicted": 0,
        "mixed": 0,
    }
    for claim in (matrix or {}).get("claims") or []:
        if not isinstance(claim, dict):
            continue
        counts["total"] += 1
        status = str(claim.get("status") or "").strip().lower()
        if status in counts:
            counts[status] += 1
    return counts


def _memo_summary(reports: list[dict]) -> dict:
    """Latest run plus terminal-state counts across a company's reports."""
    ordered = sorted(
        reports,
        key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""),
        reverse=True,
    )
    latest = ordered[0] if ordered else None
    latest_status = str((latest or {}).get("status") or "").strip().lower()
    failed = sum(
        1
        for r in reports
        if str(r.get("status") or "").strip().lower().startswith("failed")
    )
    running = sum(
        1
        for r in reports
        if str(r.get("status") or "").strip().lower() in RUNNING_REPORT_STATUSES
    )
    complete = sum(
        1
        for r in reports
        if str(r.get("status") or "").strip().lower().startswith("complete")
    )
    return {
        "total": len(reports),
        "failed": failed,
        "running": running,
        "complete": complete,
        "latest_id": (latest or {}).get("id"),
        "latest_status": latest_status or None,
        "latest_report_type": (latest or {}).get("report_type"),
        "latest_updated_at": (latest or {}).get("updated_at")
        or (latest or {}).get("created_at"),
        "latest_failure_detail": (latest or {}).get("failure_detail")
        or (latest or {}).get("error"),
        "warning_count": len((latest or {}).get("quality_warnings") or []),
    }


def _news_summary(company_id: str, now: datetime) -> dict:
    try:
        feed = context_store.company_news(company_id)
    except (ValueError, KeyError):
        return {"recent_count": 0, "latest_title": None, "latest_at": None}
    rows = [row for row in (feed.get("rows") or []) if isinstance(row, dict)]
    dated = []
    for row in rows:
        stamp = _newest(row.get("published_at"), row.get("captured_at"))
        if stamp is not None:
            dated.append((stamp, row))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    cutoff = now - timedelta(days=NEWS_WINDOW_DAYS)
    latest = dated[0] if dated else None
    return {
        "recent_count": sum(1 for stamp, _ in dated if stamp >= cutoff),
        "latest_title": (latest[1].get("title") if latest else None),
        "latest_at": (_iso(latest[0]) if latest else None),
    }


def _research_route(company_id: str, tab: str | None = None) -> dict:
    route: dict[str, Any] = {
        "name": "research",
        "params": {"companyId": company_id},
    }
    if tab:
        route["query"] = {"tab": tab}
    return route


def _attention_items(
    *,
    company_id: str,
    company_name: str,
    memo: dict,
    risks: dict,
    evidence: dict,
    documents: dict,
    session: dict | None,
) -> list[dict]:
    """Broken or in-flight work only.

    Coverage gaps (no memo, no risk map, idle) stay off this list so they
    do not bury a failed run. The caller keeps the single highest-severity
    item as the company's next action.
    """
    items: list[dict] = []

    def add(
        kind: str,
        severity: str,
        label: str,
        detail: str,
        tab: str | None,
        count: int = 0,
    ) -> None:
        # `label`/`detail` are English fallbacks. The client re-renders the
        # headline from `kind` + `count` so the dashboard localizes without
        # the rules leaking into the frontend.
        items.append(
            {
                "id": f"{company_id}:{kind}",
                "company_id": company_id,
                "company_name": company_name,
                "kind": kind,
                "severity": severity,
                "count": count,
                "label": label,
                "detail": detail,
                "route": _research_route(company_id, tab),
            }
        )

    latest_status = memo.get("latest_status") or ""
    if latest_status.startswith("failed"):
        detail = memo.get("latest_failure_detail") or (
            "The most recent memo run stopped before producing a document."
        )
        add(
            "memo_failed",
            "high",
            "Memo run failed",
            str(detail),
            "memo",
        )

    if evidence.get("contradicted"):
        count = evidence["contradicted"]
        add(
            "evidence_contradicted",
            "high",
            f"{count} contradicted {_plural(count, 'claim')}",
            "Evidence on file argues against these claims — resolve before the memo cites them.",
            "memo",
            count=count,
        )

    if latest_status == "complete_with_warnings":
        warnings = memo.get("warning_count") or 0
        add(
            "memo_warnings",
            "medium",
            "Memo completed with warnings",
            (
                f"The latest run passed with {warnings} quality "
                f"{_plural(warnings, 'warning')}."
                if warnings
                else "The latest run passed the quality gate with warnings."
            ),
            "memo",
            count=warnings,
        )

    open_risks = (risks.get("unresearched") or 0) + (risks.get("needs_review") or 0)
    if open_risks:
        high = risks.get("high_severity_open") or 0
        detail = (
            f"{high} of them {_plural(high, 'is', 'are')} rated high severity."
            if high
            else "Research them or mark them reviewed before generating the report."
        )
        add(
            "risks_open",
            "high" if high else "medium",
            f"{open_risks} open {_plural(open_risks, 'risk')}",
            detail,
            "memo",
            count=open_risks,
        )

    if evidence.get("missing"):
        count = evidence["missing"]
        add(
            "evidence_missing",
            "medium",
            f"{count} {_plural(count, 'claim')} without evidence",
            "No supporting source is attached yet.",
            "memo",
            count=count,
        )

    if session and session.get("has_unapproved_work"):
        add(
            "unapproved_work",
            "medium",
            "Analysis not approved",
            "Memo Studio has draft work that has not been approved for the memo.",
            "memo",
        )

    unresolved = documents.get("unresolved") or 0
    if unresolved:
        add(
            "documents_unresolved",
            "medium",
            f"{unresolved} {_plural(unresolved, 'document')} need review",
            "Intake could not confidently assign these to a company or category.",
            "documents",
            count=unresolved,
        )

    items.sort(key=lambda item: SEVERITY_RANK.get(item["severity"], 9))
    return items[:MAX_ATTENTION_PER_COMPANY]


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


ACTION_LABELS = {
    "memo_failed": "Resume failed memo",
    "evidence_contradicted": "Review contradicted claims",
    "memo_warnings": "Review quality warnings",
    "risks_open": "Research open risks",
    "evidence_missing": "Attach missing evidence",
    "unapproved_work": "Approve analysis",
    "documents_unresolved": "Review documents",
    "start_investigation": "Start investigation",
    "open_running": "Open running memo",
}


def _next_action(attention: list[dict], memo: dict, company_id: str) -> dict | None:
    if attention:
        item = attention[0]
        return {
            "kind": item["kind"],
            "label": ACTION_LABELS.get(item["kind"], item["label"]),
            "route": item["route"],
        }
    status = memo.get("latest_status") or ""
    if status in RUNNING_REPORT_STATUSES:
        return {
            "kind": "open_running",
            "label": ACTION_LABELS["open_running"],
            "route": _research_route(company_id, "memo"),
        }
    if not memo.get("total"):
        return {
            "kind": "start_investigation",
            "label": ACTION_LABELS["start_investigation"],
            "route": _research_route(company_id, "memo"),
        }
    return None


def _bucket(attention: list[dict], memo: dict) -> str:
    if attention:
        return "needs_action"
    status = memo.get("latest_status") or ""
    if status in RUNNING_REPORT_STATUSES:
        return "in_progress"
    if status.startswith("complete"):
        return "clear"
    return "not_started"


def _latest_decision(company_id: str) -> dict | None:
    """Newest decision on the record, trimmed to what a board row needs."""
    try:
        items = decisions_store.list_decisions(company_id).get("items") or []
    except Exception:  # noqa: BLE001 - a corrupt decisions file must not sink the rollup
        return None
    if not items:
        return None
    row = items[0]
    return {
        "id": row.get("id"),
        "verdict": row.get("verdict"),
        "decided_at": row.get("decided_at") or row.get("created_at"),
        "report_id": row.get("report_id"),
    }


def _lifecycle_stage(
    memo: dict,
    documents: dict,
    session: dict | None,
    decision: dict | None,
) -> str:
    """Where the company sits in the deal lifecycle.

    A standing decision wins (Invest → portfolio, Pass → passed, Watch →
    watch). Otherwise the memo state decides: running → diligence, complete
    → ic, no memo yet → screening once any research or analysis exists,
    else sourcing.
    """
    verdict = str((decision or {}).get("verdict") or "").lower()
    if verdict in DECISION_STAGES:
        return DECISION_STAGES[verdict]
    status = memo.get("latest_status") or ""
    if status in RUNNING_REPORT_STATUSES:
        return "diligence"
    if status.startswith("complete"):
        return "ic"
    if (memo.get("total") or 0) == 0:
        if (documents.get("total") or 0) > 0 or session:
            return "screening"
        return "sourcing"
    return "diligence"


def _company_rollup(company: dict, reports: list[dict], now: datetime, thesis: dict | None = None) -> dict:
    company_id = str(company.get("id") or "")

    try:
        session = serena_analysis.get_current_session(company_id, create=False)
    except ValueError:
        session = None

    try:
        matrix = evidence_matrix.build_company_evidence_matrix(company_id)
    except (ValueError, KeyError):
        matrix = None

    try:
        documents_payload = evidence_store.list_documents(company_id, reports=reports)
    except (ValueError, KeyError):
        documents_payload = {}

    company_reports = [r for r in reports if r.get("company_id") == company_id]

    memo = _memo_summary(company_reports)
    risks = _risk_counts(session)
    evidence = _evidence_counts(matrix)
    news = _news_summary(company_id, now)
    documents = {
        "total": len(documents_payload.get("rows") or []),
        "unresolved": int(documents_payload.get("unresolved_intake_count") or 0),
    }

    session_summary = (
        {
            "id": session.get("id"),
            "approved_for_memo": bool(session.get("approved_for_memo")),
            "has_unapproved_work": bool(session.get("has_unapproved_work")),
            "updated_at": session.get("updated_at"),
        }
        if session
        else None
    )

    last_activity = _newest(
        memo.get("latest_updated_at"),
        (session_summary or {}).get("updated_at"),
        news.get("latest_at"),
    )

    attention = _attention_items(
        company_id=company_id,
        company_name=company.get("name") or company_id,
        memo=memo,
        risks=risks,
        evidence=evidence,
        documents=documents,
        session=session_summary,
    )
    next_action = _next_action(attention, memo, company_id)
    bucket = _bucket(attention, memo)
    decision = _latest_decision(company_id)
    lifecycle_stage = _lifecycle_stage(memo, documents, session_summary, decision)
    try:
        thesis_fit = thesis_store.score_company(company, thesis=thesis)
    except Exception:  # noqa: BLE001 - a bad thesis file must not sink the rollup
        thesis_fit = None

    return {
        "id": company_id,
        "name": company.get("name") or company_id,
        "ticker": company.get("ticker") or None,
        "status": company.get("status") or None,
        "company_type": company.get("company_type") or None,
        "category": company.get("industry") or company.get("sector") or None,
        "price": _price(company),
        "memo": memo,
        "risks": risks,
        "evidence": evidence,
        "documents": documents,
        "news": news,
        "session": session_summary,
        "last_activity_at": _iso(last_activity) if last_activity else None,
        "bucket": bucket,
        "next_action": next_action,
        "attention": attention,
        "lifecycle_stage": lifecycle_stage,
        "latest_decision": decision,
        "thesis_fit": thesis_fit,
    }


def _totals(rows: list[dict]) -> dict:
    attention = [item for row in rows for item in row["attention"]]
    return {
        "company_count": len(rows),
        "attention_count": len(attention),
        "high_count": sum(1 for i in attention if i["severity"] == "high"),
        "medium_count": sum(1 for i in attention if i["severity"] == "medium"),
        "needs_action_count": sum(1 for row in rows if row["bucket"] == "needs_action"),
        "in_progress_count": sum(1 for row in rows if row["bucket"] == "in_progress"),
        "not_started_count": sum(1 for row in rows if row["bucket"] == "not_started"),
        "clear_company_count": sum(1 for row in rows if row["bucket"] == "clear"),
        "failed_memo_count": sum(
            1 for row in rows if str(row["memo"].get("latest_status") or "").startswith("failed")
        ),
        "running_memo_count": sum(1 for row in rows if row["bucket"] == "in_progress"),
    }


def build_rollup(company_ids: list[str]) -> dict:
    """Aggregate research state for the given companies.

    Unknown ids are dropped rather than raising: the follow list lives in
    browser storage and can outlive a deleted company, and one stale entry
    should not blank the whole dashboard.
    """
    thesis = thesis_store.get_thesis()
    now = _now()

    requested: list[str] = []
    for value in company_ids or []:
        # The client may send either repeated params or one comma-joined
        # value; normalizing both here keeps the query string short.
        for part in str(value or "").split(","):
            slug = part.strip()
            if slug and slug not in requested:
                requested.append(slug)

    # `get_company` rather than `list_companies`, because the slim list
    # records omit the `trader_snapshot` sidecar the price block needs.
    resolved: list[dict] = []
    missing: list[str] = []
    for slug in requested[:MAX_COMPANIES]:
        company = storage.get_company(slug)
        if company is None:
            missing.append(slug)
        else:
            resolved.append(company)

    reports = storage.list_reports()
    rows = [_company_rollup(company, reports, now, thesis) for company in resolved]

    # Worst-first, then most recently touched, so the top of the dashboard
    # is always the company that needs the analyst today.
    rows.sort(
        key=lambda row: (
            BUCKET_RANK.get(row["bucket"], 9),
            SEVERITY_RANK.get(
                row["attention"][0]["severity"] if row["attention"] else "none", 9
            ),
            str(row["name"]).lower(),
        )
    )

    attention = [item for row in rows for item in row["attention"]]
    attention.sort(
        key=lambda item: (
            SEVERITY_RANK.get(item["severity"], 9),
            str(item["company_name"]).lower(),
        )
    )

    return {
        "generated_at": _iso(now),
        "companies": rows,
        "attention": attention,
        "totals": _totals(rows),
        "unknown_company_ids": missing,
    }
