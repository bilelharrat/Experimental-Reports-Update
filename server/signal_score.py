"""Transparent signal score: every component is a record-backed rule with its formula shown.

Components that have no data are listed as "not scored" and excluded from the denominator —
the score is never padded with assumptions.
"""
from __future__ import annotations

from typing import Any

from . import decisions_store, evidence_matrix, ic_room, portfolio, storage, thesis_store

MIN_COMPONENTS = 2
MIN_MAX_POINTS = 35


def _component(name: str, *, points: float | None, max_points: int, formula: str, basis: str, available: bool) -> dict:
    return {
        "name": name,
        "points": round(points, 1) if (available and points is not None) else None,
        "max": max_points,
        "formula": formula,
        "basis": basis,
        "available": available,
    }


def compute(company_id: str, *, reports: list[dict] | None = None) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        return {"company_id": company_id, "score": None, "components": [], "note": "Company not found"}
    components: list[dict] = []

    fit = thesis_store.score_company(company)
    components.append(_component(
        "Thesis fit", points=(fit["score"] or 0) * 0.30 if fit["configured"] else None, max_points=30,
        formula="thesis fit % × 0.30", basis="; ".join(fit.get("reasons") or []) or "No thesis configured",
        available=bool(fit["configured"] and fit["fit"] != "disqualified"),
    ))
    if fit["configured"] and fit["fit"] == "disqualified":
        components[-1]["basis"] = "Disqualified by thesis: " + ", ".join(fit.get("disqualified_by") or [])
        components[-1]["available"] = True
        components[-1]["points"] = 0

    rows = [r for r in (evidence_matrix.build_company_evidence_matrix(company_id).get("claims") or []) if isinstance(r, dict)]
    if rows:
        supported = sum(1 for r in rows if r.get("status") == "supported")
        partial = sum(1 for r in rows if r.get("status") == "partial")
        contradicted = sum(1 for r in rows if r.get("status") == "contradicted")
        ratio = (supported + 0.5 * partial - contradicted) / len(rows)
        components.append(_component(
            "Evidence", points=max(0.0, ratio) * 20, max_points=20,
            formula="(supported + ½ partial − contradicted) ÷ claims × 20",
            basis=f"{supported} supported, {partial} partial, {contradicted} contradicted of {len(rows)} claims", available=True,
        ))
    else:
        components.append(_component("Evidence", points=None, max_points=20, formula="(supported + ½ partial − contradicted) ÷ claims × 20", basis="No evidence matrix yet", available=False))

    if reports is None:
        reports = storage.list_reports_for(company_id)
    if reports:
        statuses = [str(r.get("status") or "").lower() for r in reports]
        complete = any(s.startswith("complete") for s in statuses)
        running = any(s in {"running", "queued"} for s in statuses)
        pts = 15 if complete else (5 if running else 0)
        components.append(_component("Memo", points=pts, max_points=15, formula="complete memo 15 · running 5 · none 0",
                                     basis=f"{len(reports)} memo run(s); latest status {statuses[0]}", available=True))
    else:
        components.append(_component("Memo", points=None, max_points=15, formula="complete memo 15 · running 5 · none 0", basis="No memo run", available=False))

    refs = ic_room.list_reference_calls(company_id)
    if refs["average_rating"] is not None:
        components.append(_component("Reference calls", points=refs["average_rating"] / 5 * 15, max_points=15, formula="average rating ÷ 5 × 15",
                                     basis=f"{refs['count']} calls, avg {refs['average_rating']}/5, {refs['concern_count']} concerns", available=True))
    else:
        components.append(_component("Reference calls", points=None, max_points=15, formula="average rating ÷ 5 × 15",
                                     basis="No rated reference calls" if not refs["count"] else f"{refs['count']} calls without ratings", available=False))

    record = portfolio.get_portfolio(company_id)
    arr_rows = [k for k in record.get("kpis") or [] if k.get("arr_usd")]
    if len(arr_rows) >= 2 and arr_rows[-2]["arr_usd"] > 0:
        growth = (arr_rows[-1]["arr_usd"] - arr_rows[-2]["arr_usd"]) / arr_rows[-2]["arr_usd"]
        components.append(_component("KPI momentum", points=max(0.0, min(1.0, growth)) * 10, max_points=10, formula="ARR growth between last two rows, capped at 100%, × 10",
                                     basis=f"ARR ${arr_rows[-2]['arr_usd']:,.0f} → ${arr_rows[-1]['arr_usd']:,.0f} ({growth * 100:+.0f}%)", available=True))
    else:
        components.append(_component("KPI momentum", points=None, max_points=10, formula="ARR growth between last two rows, capped at 100%, × 10", basis="Fewer than two ARR data points", available=False))

    meetings = ic_room.list_meetings(company_id).get("items") or []
    voted = next((m for m in meetings if (m.get("tally") or {}).get("total")), None)
    if voted:
        t = voted["tally"]
        components.append(_component("IC votes", points=t["invest"] / t["total"] * 10, max_points=10, formula="invest votes ÷ total votes × 10",
                                     basis=f"{t['invest']} invest / {t['pass']} pass / {t['more_work']} more work ({voted.get('status')})", available=True))
    else:
        components.append(_component("IC votes", points=None, max_points=10, formula="invest votes ÷ total votes × 10", basis="No votes cast", available=False))

    latest = (decisions_store.list_decisions(company_id).get("items") or [None])[0]
    available = [c for c in components if c["available"]]
    max_total = sum(c["max"] for c in available)
    pts_total = sum(c["points"] or 0 for c in available)
    provisional = round(pts_total / max_total * 100) if max_total else None
    sufficient = len(available) >= MIN_COMPONENTS and max_total >= MIN_MAX_POINTS
    return {
        "company_id": company_id,
        "score": provisional if sufficient else None,
        "provisional_score": provisional,
        "sufficient_coverage": sufficient,
        "points": round(pts_total, 1),
        "max_available": max_total,
        "max_possible": sum(c["max"] for c in components),
        "coverage": f"{len(available)} of {len(components)} components have data",
        "components": components,
        "latest_decision": {"verdict": latest.get("verdict"), "decided_at": latest.get("decided_at")} if latest else None,
        "formula": f"score = Σ points ÷ Σ max of components with data × 100, shown only with ≥{MIN_COMPONENTS} components and ≥{MIN_MAX_POINTS} max points",
        "note": None if sufficient else f"Not enough components with data to score (need ≥{MIN_COMPONENTS} components and ≥{MIN_MAX_POINTS} max points)",
    }


__all__ = ["compute", "Any"]
