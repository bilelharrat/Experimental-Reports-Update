"""Desk digest — what changed + coverage screener for the mobile home desk."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from . import desk_store, live_quotes, storage


def _parse_iso(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ago(ts: datetime | None) -> str:
    if ts is None:
        return ""
    delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def build_what_changed(
    *,
    tickers: list[str] | None = None,
    since: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Surface movers / news / memo activity since ``since`` (ISO) or 24h."""
    since_dt = _parse_iso(since) or (datetime.now(timezone.utc) - timedelta(hours=24))
    watch = [t.upper() for t in (tickers or desk_store.pinned_tickers() or []) if t]
    if not watch:
        watch = ["SPY", "QQQ", "DIA"]

    quotes = live_quotes.fetch_quotes(watch).get("quotes") or {}
    news_payload = live_quotes.fetch_news(watch, limit=40)
    news_items = news_payload.get("items") or news_payload.get("news") or []

    changes: list[dict[str, Any]] = []

    for ticker in watch:
        row = quotes.get(ticker) or {}
        pct = row.get("change_pct_1d")
        try:
            pct_f = float(pct) if pct is not None else None
        except (TypeError, ValueError):
            pct_f = None
        if pct_f is not None and abs(pct_f) >= 1.5:
            changes.append(
                {
                    "id": f"move:{ticker}",
                    "kind": "mover",
                    "ticker": ticker,
                    "title": f"{ticker} {pct_f:+.1f}% today",
                    "detail": row.get("name") or ticker,
                    "magnitude": abs(pct_f),
                    "href": f"bshresearch://ticker/{ticker}",
                }
            )

    for item in news_items:
        if not isinstance(item, dict):
            continue
        ts = _parse_iso(item.get("published_at") or item.get("ts") or item.get("captured_at"))
        if ts and ts < since_dt:
            continue
        tickers_row = item.get("tickers") or item.get("symbols") or []
        ticker = ""
        if isinstance(tickers_row, list) and tickers_row:
            ticker = str(tickers_row[0]).upper()
        elif item.get("ticker"):
            ticker = str(item.get("ticker")).upper()
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        changes.append(
            {
                "id": f"news:{item.get('id') or title[:40]}",
                "kind": "news",
                "ticker": ticker or None,
                "title": title,
                "detail": _ago(ts),
                "magnitude": 0.5,
                "href": item.get("url"),
            }
        )

    for report in storage.list_reports()[:40]:
        if not isinstance(report, dict):
            continue
        status = str(report.get("status") or "")
        updated = _parse_iso(report.get("updated_at") or report.get("completed_at"))
        if updated and updated < since_dt:
            continue
        if not (
            status.startswith("complete")
            or status.startswith("failed")
            or report.get("stage")
        ):
            continue
        company_id = report.get("company_id")
        company = storage.get_company(str(company_id)) if company_id else None
        name = (company or {}).get("name") or company_id or "Memo"
        ticker = (company or {}).get("ticker")
        label = "Memo ready" if status.startswith("complete") else f"Memo · {status}"
        changes.append(
            {
                "id": f"memo:{report.get('id')}",
                "kind": "memo",
                "ticker": ticker,
                "title": f"{label}: {name}",
                "detail": _ago(updated),
                "magnitude": 2.0 if status.startswith("complete") else 1.0,
                "href": f"bshresearch://report/{report.get('id')}",
            }
        )

    changes.sort(key=lambda row: float(row.get("magnitude") or 0), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "since": since_dt.isoformat().replace("+00:00", "Z"),
        "items": changes[: max(1, min(limit, 40))],
    }


def build_desk_screener(*, limit: int = 20) -> dict[str, Any]:
    """Coverage hygiene: watched names down hard, or companies with stale/no memo."""
    watch = [t.upper() for t in (desk_store.pinned_tickers() or []) if t]
    quotes = live_quotes.fetch_quotes(watch).get("quotes") or {} if watch else {}

    rows: list[dict[str, Any]] = []
    for ticker in watch:
        q = quotes.get(ticker) or {}
        try:
            pct = float(q.get("change_pct_1d"))
        except (TypeError, ValueError):
            continue
        if pct <= -3.0:
            rows.append(
                {
                    "id": f"down:{ticker}",
                    "kind": "drawdown",
                    "ticker": ticker,
                    "title": f"{ticker} {pct:+.1f}%",
                    "detail": "Watchlist drawdown",
                    "score": abs(pct),
                    "href": f"bshresearch://ticker/{ticker}",
                }
            )

    # Stale memos: companies with no complete report in 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    latest_by_company: dict[str, datetime] = {}
    for report in storage.list_reports():
        if not isinstance(report, dict):
            continue
        if not str(report.get("status") or "").startswith("complete"):
            continue
        cid = str(report.get("company_id") or "")
        ts = _parse_iso(report.get("updated_at") or report.get("completed_at"))
        if not cid or ts is None:
            continue
        prev = latest_by_company.get(cid)
        if prev is None or ts > prev:
            latest_by_company[cid] = ts

    for company in storage.list_companies()[:80]:
        if not isinstance(company, dict):
            continue
        cid = str(company.get("id") or "")
        if not cid:
            continue
        last = latest_by_company.get(cid)
        if last is not None and last >= cutoff:
            continue
        ticker = company.get("ticker")
        name = company.get("name") or cid
        rows.append(
            {
                "id": f"stale:{cid}",
                "kind": "stale_memo",
                "ticker": ticker,
                "company_id": cid,
                "title": name,
                "detail": "No fresh memo in 30 days" if last else "No completed memo",
                "score": 5.0 if last is None else 3.0,
                "href": f"bshresearch://company/{cid}",
            }
        )

    rows.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "items": rows[: max(1, min(limit, 40))],
    }
