"""Shared helpers for the strategic-risk workbench.

Keeps ranking, framing, evidence merge, and packet rendering in one place so
the mapper, prioritizer, thesis spine, and UI all see the same risk contract.
"""
from __future__ import annotations

from typing import Any

SEVERITY_VALUES = ("high", "medium", "low")
LIKELIHOOD_VALUES = ("high", "medium", "low")
DISPOSITIONS = (
    "lead_risk",
    "downside_trigger",
    "valuation_sensitivity",
    "monitoring",
    "dismissed",
)
FRAMINGS = (
    "technology",
    "market_structure",
    "competitive_moat",
    "go_to_market",
    "financial",
    "regulatory",
    "other",
)
SOURCE_CLASSES = (
    "first_party",
    "third_party",
    "market_data",
    "filing",
    "transcript",
    "news",
    "research_file",
    "inference",
)

_SEVERITY_SCORE = {"high": 3, "medium": 2, "low": 1}
_DISPOSITION_PACKET_ORDER = {
    "lead_risk": 0,
    "downside_trigger": 1,
    "valuation_sensitivity": 2,
    "monitoring": 3,
}

_FRAMING_PROMPTS = {
    "technology": (
        "Approach this as a technology / product-feasibility problem: "
        "what has to work technically, what is still unproven, and what "
        "would falsify the technical bar."
    ),
    "market_structure": (
        "Approach this as a market-structure problem: who pays, budget "
        "ownership, switching costs, and whether the category can support "
        "the implied scale."
    ),
    "competitive_moat": (
        "Approach this as a competitive / moat problem: why this company "
        "keeps the advantage, what a well-resourced rival would copy, and "
        "what evidence would show the moat is thinning."
    ),
    "go_to_market": (
        "Approach this as a go-to-market and adoption problem: conversion "
        "from pilots to production, sales motion, and evidence of repeat use."
    ),
    "financial": (
        "Approach this as a financial / valuation problem: unit economics, "
        "dilution, duration, and the valuation assumption that breaks first."
    ),
    "regulatory": (
        "Approach this as a regulatory / compliance problem: what approval "
        "or disclosure path is required and how delay or denial changes value."
    ),
    "other": (
        "Keep the current framing unless the analyst note specifies a "
        "sharper investment question."
    ),
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return text if text in allowed else default


def _string_list(value: Any, *, fallback: list[str] | None = None, limit: int = 8) -> list[str]:
    if isinstance(value, list):
        out = [_clean(item) for item in value if _clean(item)]
        if out:
            return out[:limit]
    if isinstance(value, str) and value.strip():
        return [value.strip()][:limit]
    return list(fallback or [])[:limit]


def _evidence_row(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        excerpt = item.strip()
        if not excerpt:
            return None
        return {
            "file_id": None,
            "filename": None,
            "locator": None,
            "excerpt": excerpt,
            "confidence": "medium",
            "source_class": "inference",
        }
    if not isinstance(item, dict):
        return None
    excerpt = _clean(item.get("excerpt") or item.get("text") or item.get("claim"))
    if not excerpt:
        return None
    return {
        "file_id": item.get("file_id"),
        "filename": _clean(item.get("filename")) or None,
        "locator": _clean(item.get("locator")) or None,
        "excerpt": excerpt,
        "confidence": _enum(item.get("confidence"), ("low", "medium", "high"), "medium"),
        "source_class": _enum(
            item.get("source_class") or item.get("source_type"),
            SOURCE_CLASSES,
            "inference",
        ),
    }


def coerce_evidence_rows(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        row = _evidence_row(item)
        if not row:
            continue
        key = row["excerpt"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def risk_score(risk: dict | None) -> int:
    if not isinstance(risk, dict):
        return 0
    return (
        _SEVERITY_SCORE.get(_enum(risk.get("severity"), SEVERITY_VALUES, "medium"), 2)
        * _SEVERITY_SCORE.get(_enum(risk.get("likelihood"), LIKELIHOOD_VALUES, "medium"), 2)
    )


def suggested_disposition(risk: dict | None) -> str:
    if not isinstance(risk, dict):
        return "monitoring"
    explicit = _enum(risk.get("suggested_posture") or risk.get("disposition"), DISPOSITIONS, "")
    if explicit:
        return explicit
    score = risk_score(risk)
    if score >= 9:
        return "lead_risk"
    if score >= 6:
        return "downside_trigger"
    if score >= 4:
        return "valuation_sensitivity"
    return "monitoring"


def complete_risk(row: dict, company: dict, *, index: int = 1) -> dict[str, Any]:
    """Fill missing workbench fields without wiping human edits."""
    company_name = company.get("name") or company.get("id") or "the company"
    title = _clean(row.get("title") or row.get("decision_question")) or f"Risk {index}"
    decision_question = _clean(row.get("decision_question") or title)
    why = _clean(row.get("why_it_matters")) or (
        "This can change whether we recommend the investment, at what "
        "valuation, or on what terms."
    )
    description = _clean(row.get("description")) or why
    completed = {
        **row,
        "id": _clean(row.get("id")) or f"risk-{index}",
        "title": title,
        "description": description,
        "decision_question": decision_question,
        "why_it_matters": why,
        "materiality": _clean(row.get("materiality")) or why,
        "bull_case_answer": _clean(row.get("bull_case_answer")) or (
            f"The bull case is that {company_name} already has enough "
            "source-backed proof that this risk is priced or manageable."
        ),
        "bear_case_answer": _clean(row.get("bear_case_answer")) or (
            "The bear case is that this is still an unproven future state, "
            "and a weak answer should cut conviction or valuation support."
        ),
        "key_questions": _string_list(
            row.get("key_questions"),
            fallback=[decision_question],
            limit=6,
        ),
        "evidence_needed": _string_list(
            row.get("evidence_needed"),
            fallback=["independent support", "disconfirming evidence"],
            limit=6,
        ),
        "best_sources": _string_list(
            row.get("best_sources"),
            fallback=["Serena research folder", "public filings", "company news"],
            limit=8,
        ),
        "supporting_evidence": coerce_evidence_rows(row.get("supporting_evidence")),
        "contradicting_evidence": coerce_evidence_rows(row.get("contradicting_evidence")),
        "missing_evidence": _string_list(row.get("missing_evidence"), fallback=[], limit=6),
        "evidence_that_would_change_assessment": _string_list(
            row.get("evidence_that_would_change_assessment"),
            fallback=["A sourced fact that proves or disproves the decision question."],
            limit=6,
        ),
        "research_prompt": _clean(row.get("research_prompt")) or (
            f"Research whether {decision_question.rstrip('?')}? Separate "
            "company claims from independent evidence and name the strongest "
            "disconfirming facts."
        ),
        "memo_section": _clean(row.get("memo_section")) or "Investment Risk",
        "status": _clean(row.get("status")) or "unresearched",
        "severity": _enum(row.get("severity"), SEVERITY_VALUES, "medium"),
        "likelihood": _enum(row.get("likelihood"), LIKELIHOOD_VALUES, "medium"),
        "mitigation_or_monitoring": _clean(row.get("mitigation_or_monitoring")) or (
            "Identify the metric or disclosure that would show this risk is contained."
        ),
        "suggested_posture": suggested_disposition(row),
        "framing": _enum(row.get("framing") or row.get("analyst_framing"), FRAMINGS, "other"),
        "edited_by_human": bool(row.get("edited_by_human")),
    }
    if row.get("analyst_note") is not None:
        completed["analyst_note"] = _clean(row.get("analyst_note"))
    if row.get("generated_by"):
        completed["generated_by"] = _clean(row.get("generated_by"))
    return completed


def apply_framing(
    risk: dict,
    framing: str,
    analyst_note: str = "",
) -> dict[str, Any]:
    """Stamp an analyst framing onto one risk and rewrite the research prompt."""
    chosen = _enum(framing, FRAMINGS, "other")
    note = _clean(analyst_note)
    instruction = _FRAMING_PROMPTS[chosen]
    question = _clean(risk.get("decision_question") or risk.get("title"))
    prompt_bits = [
        instruction,
        f"Decision question: {question}" if question else "",
        f"Analyst note: {note}" if note else "",
        "Do not regenerate the full risk map. Deepen only this risk.",
        "Return competing bull and bear readings and the evidence that would change the call.",
    ]
    updated = {
        **risk,
        "framing": chosen,
        "suggested_posture": suggested_disposition({**risk, "framing": chosen}),
        "research_prompt": " ".join(bit for bit in prompt_bits if bit),
        "edited_by_human": True,
        "status": "needs_review" if risk.get("status") == "researched" else (
            risk.get("status") or "unresearched"
        ),
    }
    if note:
        updated["analyst_note"] = note
        why = _clean(risk.get("why_it_matters"))
        if why and note.lower() not in why.lower():
            updated["why_it_matters"] = f"{why} Analyst framing: {note}"
    return complete_risk(updated, {}, index=1)


def merge_task_evidence_into_risk(risk: dict, task: dict) -> dict[str, Any]:
    """Copy completed research-task evidence onto the parent risk."""
    if not isinstance(risk, dict) or not isinstance(task, dict):
        return risk if isinstance(risk, dict) else {}
    supporting = coerce_evidence_rows(
        list(risk.get("supporting_evidence") or [])
        + list(task.get("supporting_evidence") or [])
    )
    contradicting = coerce_evidence_rows(
        list(risk.get("contradicting_evidence") or [])
        + list(task.get("contradicting_evidence") or [])
    )
    missing = _string_list(
        list(risk.get("missing_evidence") or [])
        + list(task.get("remaining_evidence_limits") or task.get("open_questions") or []),
        fallback=[],
        limit=6,
    )
    status = _clean(risk.get("status")) or "unresearched"
    if task.get("status") == "done":
        if contradicting and not supporting:
            status = "needs_review"
        else:
            status = "researched"
    updated = {
        **risk,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "missing_evidence": missing,
        "status": status,
        "result_summary": _clean(task.get("result_summary") or task.get("answer")) or risk.get("result_summary"),
    }
    return complete_risk(updated, {}, index=1)


def default_priorities(risks: list[dict], previous: Any = None) -> list[dict[str, Any]]:
    """Rank by severity × likelihood unless a human ranking already exists."""
    previous_rows = previous if isinstance(previous, list) else []
    previous_by_id = {
        _clean(row.get("risk_id")): row
        for row in previous_rows
        if isinstance(row, dict) and row.get("risk_id")
    }
    human_ranked = any(
        bool(row.get("human_ranked")) or _clean(row.get("rationale")).startswith("Analyst")
        for row in previous_by_id.values()
    )
    indexed = [risk for risk in risks if isinstance(risk, dict) and risk.get("id")]
    if human_ranked:
        ordered = sorted(
            indexed,
            key=lambda risk: (
                int(previous_by_id.get(str(risk["id"]), {}).get("rank") or 10_000),
                str(risk.get("title") or ""),
            ),
        )
    else:
        ordered = sorted(
            indexed,
            key=lambda risk: (-risk_score(risk), str(risk.get("title") or "")),
        )
    out: list[dict[str, Any]] = []
    for index, risk in enumerate(ordered):
        prior = previous_by_id.get(str(risk["id"]), {})
        disposition = _enum(
            prior.get("disposition") or risk.get("suggested_posture"),
            DISPOSITIONS,
            suggested_disposition(risk),
        )
        selected = prior.get("selected")
        if selected is None:
            selected = index < 3 and disposition != "dismissed"
        rationale = _clean(prior.get("rationale")) or (
            f"{str(risk.get('severity') or 'medium').title()} severity × "
            f"{str(risk.get('likelihood') or 'medium')} likelihood; "
            f"treat as {disposition.replace('_', ' ')}."
        )
        row = {
            "risk_id": str(risk["id"]),
            "rank": index + 1,
            "selected": bool(selected) and disposition != "dismissed",
            "rationale": rationale,
            "disposition": disposition,
            "framing": _enum(prior.get("framing") or risk.get("framing"), FRAMINGS, "other"),
            "human_ranked": bool(prior.get("human_ranked")) or human_ranked,
        }
        if prior.get("analyst_note") is not None:
            row["analyst_note"] = _clean(prior.get("analyst_note"))
        out.append(row)
    return out


def ordered_active_risks(risks: list[dict], priorities: Any) -> list[dict]:
    """Risks in analyst rank order, excluding dismissed rows."""
    by_id = {
        str(risk["id"]): risk
        for risk in risks
        if isinstance(risk, dict) and risk.get("id")
    }
    rows = priorities if isinstance(priorities, list) else []
    ordered: list[dict] = []
    seen: set[str] = set()
    ranked = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("risk_id") or "") in by_id
    ]
    ranked.sort(key=lambda row: (int(row.get("rank") or 10_000), str(row.get("risk_id"))))
    for row in ranked:
        risk_id = str(row.get("risk_id"))
        if risk_id in seen:
            continue
        if _enum(row.get("disposition"), DISPOSITIONS, "monitoring") == "dismissed":
            seen.add(risk_id)
            continue
        seen.add(risk_id)
        ordered.append({**by_id[risk_id], "priority": row})
    for risk in risks:
        if not isinstance(risk, dict) or not risk.get("id"):
            continue
        risk_id = str(risk["id"])
        if risk_id in seen:
            continue
        ordered.append(risk)
    return ordered


def packet_strategic_risk_lines(risks: list[dict], priorities: Any) -> list[str]:
    lines = ["", "## Strategic Risks"]
    active = ordered_active_risks(risks, priorities)
    if not active:
        lines.append("- No active strategic risks after analyst review.")
        return lines
    grouped = sorted(
        active,
        key=lambda risk: (
            _DISPOSITION_PACKET_ORDER.get(
                _enum((risk.get("priority") or {}).get("disposition"), DISPOSITIONS, "monitoring"),
                3,
            ),
            int((risk.get("priority") or {}).get("rank") or 10_000),
        ),
    )
    for risk in grouped:
        priority = risk.get("priority") if isinstance(risk.get("priority"), dict) else {}
        rank = priority.get("rank") or "—"
        disposition = _enum(priority.get("disposition"), DISPOSITIONS, "monitoring").replace("_", " ")
        framing = _enum(priority.get("framing") or risk.get("framing"), FRAMINGS, "other").replace("_", " ")
        lines.append(
            f"- **#{rank} [{disposition}] {risk.get('title')}** — "
            f"{risk.get('why_it_matters') or risk.get('description')}"
        )
        lines.append(
            f"  - Materiality: {risk.get('materiality') or risk.get('why_it_matters')}"
        )
        lines.append(
            f"  - Severity / likelihood: {risk.get('severity')}/{risk.get('likelihood')}"
        )
        if risk.get("bull_case_answer"):
            lines.append(f"  - Bull: {risk.get('bull_case_answer')}")
        if risk.get("bear_case_answer"):
            lines.append(f"  - Bear: {risk.get('bear_case_answer')}")
        if framing != "other":
            lines.append(f"  - Analyst framing: {framing}")
        if priority.get("analyst_note") or risk.get("analyst_note"):
            lines.append(
                f"  - Analyst note: {priority.get('analyst_note') or risk.get('analyst_note')}"
            )
        if risk.get("mitigation_or_monitoring"):
            lines.append(f"  - Mitigation / monitor: {risk.get('mitigation_or_monitoring')}")
        supporting = risk.get("supporting_evidence") or []
        if supporting:
            lines.append("  - Supporting evidence:")
            for item in supporting[:3]:
                locator = item.get("locator") or item.get("filename") or item.get("source_class")
                prefix = f"{locator}: " if locator else ""
                lines.append(f"    - {prefix}{item.get('excerpt')}")
        contradicting = risk.get("contradicting_evidence") or []
        if contradicting:
            lines.append("  - Contradicting evidence:")
            for item in contradicting[:3]:
                locator = item.get("locator") or item.get("filename") or item.get("source_class")
                prefix = f"{locator}: " if locator else ""
                lines.append(f"    - {prefix}{item.get('excerpt')}")
        missing = risk.get("missing_evidence") or []
        if missing:
            lines.append("  - Missing evidence: " + "; ".join(str(item) for item in missing[:3]))
        change = risk.get("evidence_that_would_change_assessment") or []
        if change:
            lines.append(
                "  - What would change the call: "
                + "; ".join(str(item) for item in change[:3])
            )
    dismissed = [
        row for row in (priorities if isinstance(priorities, list) else [])
        if isinstance(row, dict)
        and _enum(row.get("disposition"), DISPOSITIONS, "monitoring") == "dismissed"
    ]
    if dismissed:
        lines += ["", "### Dismissed by analyst (do not treat as memo risks)"]
        for row in dismissed:
            lines.append(f"- {row.get('risk_id')}: {row.get('rationale') or 'Dismissed.'}")
    return lines


def company_evidence_rows(company: dict, *, limit: int = 6) -> list[dict[str, Any]]:
    """Turn company-record facts into traceable evidence rows for fallbacks."""
    rows: list[dict[str, Any]] = []
    for item in list(company.get("recent_news") or company.get("company_news") or []):
        if isinstance(item, dict):
            excerpt = _clean(item.get("summary") or item.get("headline") or item.get("title"))
            if excerpt:
                rows.append({
                    "file_id": None,
                    "filename": None,
                    "locator": _clean(item.get("headline") or item.get("title")) or None,
                    "excerpt": excerpt[:400],
                    "confidence": "medium",
                    "source_class": "news",
                })
        elif _clean(item):
            rows.append({
                "file_id": None,
                "filename": None,
                "locator": None,
                "excerpt": _clean(item)[:400],
                "confidence": "medium",
                "source_class": "news",
            })
    funding = company.get("latest_funding") if isinstance(company.get("latest_funding"), dict) else None
    if funding:
        bits = [
            _clean(funding.get("round")),
            _clean(funding.get("amount_usd")),
            _clean(funding.get("date")),
            _clean(funding.get("lead_investor")),
        ]
        excerpt = " ".join(bit for bit in bits if bit)
        if excerpt:
            rows.append({
                "file_id": None,
                "filename": None,
                "locator": "latest_funding",
                "excerpt": excerpt[:400],
                "confidence": "medium",
                "source_class": "market_data",
            })
    earnings = company.get("latest_earnings") if isinstance(company.get("latest_earnings"), dict) else None
    if earnings:
        bits = [
            _clean(earnings.get("period")),
            _clean(earnings.get("revenue_yoy")),
            _clean(earnings.get("eps")),
            _clean(earnings.get("beat_or_miss")),
        ]
        excerpt = " ".join(bit for bit in bits if bit)
        if excerpt:
            rows.append({
                "file_id": None,
                "filename": None,
                "locator": "latest_earnings",
                "excerpt": excerpt[:400],
                "confidence": "medium",
                "source_class": "filing",
            })
    for item in list(company.get("notable_contracts") or [])[:3]:
        if not isinstance(item, dict):
            continue
        excerpt = " ".join(
            bit for bit in (
                _clean(item.get("customer")),
                _clean(item.get("scope")),
                _clean(item.get("value_usd")),
            ) if bit
        )
        if excerpt:
            rows.append({
                "file_id": None,
                "filename": None,
                "locator": "notable_contracts",
                "excerpt": excerpt[:400],
                "confidence": "medium",
                "source_class": "third_party",
            })
    for item in list(company.get("disclosures") or [])[:3]:
        excerpt = _clean(item.get("title") or item.get("summary") or item) if isinstance(item, dict) else _clean(item)
        if excerpt:
            rows.append({
                "file_id": None,
                "filename": None,
                "locator": "disclosures",
                "excerpt": excerpt[:400],
                "confidence": "medium",
                "source_class": "filing",
            })
    return coerce_evidence_rows(rows, limit=limit)


def company_risk_context(company: dict) -> dict[str, Any]:
    """Compact, source-bearing context for the mapper instead of the full record."""
    news = []
    for item in list(company.get("company_news") or company.get("recent_news") or [])[:6]:
        if isinstance(item, dict):
            title = _clean(item.get("title") or item.get("headline"))
            if title:
                news.append({
                    "title": title,
                    "date": item.get("published_at") or item.get("date"),
                    "summary": _clean(item.get("summary") or item.get("detail"))[:280],
                })
        elif _clean(item):
            news.append({"title": _clean(item)})
    competitors = []
    for item in list(company.get("competitors") or [])[:6]:
        if isinstance(item, dict):
            name = _clean(item.get("name"))
            if name:
                competitors.append(name)
        elif _clean(item):
            competitors.append(_clean(item))
    industry = company.get("industry_view") if isinstance(company.get("industry_view"), dict) else {}
    return {
        "id": company.get("id"),
        "name": company.get("name"),
        "ticker": company.get("ticker"),
        "company_type": company.get("company_type") or company.get("status"),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "description": company.get("description"),
        "positioning": company.get("positioning"),
        "latest_funding": company.get("latest_funding"),
        "latest_earnings": company.get("latest_earnings"),
        "metrics": (company.get("metrics") or [])[:8],
        "products": (company.get("products") or [])[:6],
        "competitors": competitors,
        "recent_news": news,
        "disclosures": (company.get("disclosures") or [])[:6],
        "industry_view_summary": industry.get("summary") or industry.get("title"),
        "notable_contracts": (company.get("notable_contracts") or [])[:4],
    }
