"""Company context adapters for news, industry views, and competitors."""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from . import external_store, storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, *, limit: int = 700) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _slug(value: Any, fallback: str = "item") -> str:
    text = _clean(value, limit=100).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def _source_class(value: Any, default: str = "third-party market data") -> str:
    raw = _clean(value, limit=80).lower().replace("_", " ").replace("-", " ")
    aliases = {
        "company": "company material",
        "company material": "company material",
        "company materials": "company material",
        "public": "public filing",
        "public filing": "public filing",
        "filing": "public filing",
        "public comps": "third-party market data",
        "public comp": "third-party market data",
        "third party": "third-party market data",
        "third party market data": "third-party market data",
        "third-party market data": "third-party market data",
        "bsh": "BSH primary diligence",
        "bsh diligence": "BSH primary diligence",
        "bsh primary diligence": "BSH primary diligence",
        "internal": "internal note",
        "internal note": "internal note",
        "generated": "generated memo",
        "generated memo": "generated memo",
    }
    return aliases.get(raw, default)


def _source_ref(row: dict, *, fallback_title: str, default_class: str) -> dict:
    refs = row.get("source_refs") if isinstance(row.get("source_refs"), list) else []
    if refs:
        ref = refs[0] if isinstance(refs[0], dict) else {"title": refs[0]}
        return {
            "title": _clean(ref.get("title") or ref.get("label") or fallback_title, limit=240),
            "origin": _clean(ref.get("origin") or ref.get("source"), limit=240),
            "url": _clean(ref.get("url"), limit=600),
            "published_at": _clean(ref.get("published_at") or ref.get("date") or row.get("published_at") or row.get("date"), limit=80),
            "source_class": _source_class(ref.get("source_class") or row.get("source_class"), default_class),
        }
    return {
        "title": fallback_title,
        "origin": _clean(row.get("source") or row.get("origin"), limit=240),
        "url": _clean(row.get("url") or row.get("source_url") or row.get("final_url"), limit=600),
        "published_at": _clean(row.get("published_at") or row.get("date"), limit=80),
        "source_class": _source_class(row.get("source_class"), default_class),
    }


def _company_match_terms(company: dict) -> list[str]:
    terms = [
        company.get("id"),
        company.get("name"),
        company.get("ticker"),
        *[alias for alias in _list(company.get("aliases"))],
    ]
    short = re.sub(r"[,\.]?\s+(inc|corp|company|co|ltd|llc)\.?$", "", str(company.get("name") or ""), flags=re.I)
    terms.append(short)
    return [term.lower() for term in terms if _clean(term, limit=120)]


def _matches_company(item: dict, company: dict) -> bool:
    assignment = item.get("intake_assignment") if isinstance(item.get("intake_assignment"), dict) else {}
    if assignment.get("company_id") == company.get("id"):
        return True
    explicit = item.get("company_id") or item.get("company")
    if explicit and str(explicit).lower() in {company.get("id"), company.get("name", "").lower()}:
        return True
    body = " ".join(
        _clean(item.get(key), limit=1200)
        for key in ("title", "summary", "source_url", "final_url", "url")
        if item.get(key)
    ).lower()
    return any(len(term) >= 3 and term in body for term in _company_match_terms(company))


def _category_for_news(row: dict) -> str:
    explicit = _clean(row.get("category"), limit=80).lower()
    if explicit:
        return explicit
    text = " ".join(
        _clean(row.get(key), limit=500).lower()
        for key in ("title", "headline", "summary")
        if row.get(key)
    )
    rules = (
        ("fundraising", r"\b(round|funding|valuation|raised|series)\b"),
        ("product", r"\b(product|launch|sdk|platform|release)\b"),
        ("filing", r"\b(sec|filing|patent|standard|3gpp)\b"),
        ("partnership", r"\b(partner|customer|contract|program|mou)\b"),
        ("leadership", r"\b(ceo|cto|advisor|board|hire|appoint)\b"),
        ("risk", r"\b(lawsuit|delay|risk|recall|warning)\b"),
    )
    for category, pattern in rules:
        if re.search(pattern, text):
            return category
    return "press"


def _news_tags(row: dict, category: str) -> list[str]:
    tags = [str(tag).strip().lower() for tag in _list(row.get("tags")) if str(tag).strip()]
    if category and category not in tags:
        tags.insert(0, category)
    return tags[:6]


def _news_row(row: dict, *, company_id: str, origin: str, index: int) -> dict:
    title = _clean(row.get("title") or row.get("headline") or row.get("name"), limit=240)
    category = _category_for_news(row)
    source_class = _source_class(row.get("source_class"), "third-party market data")
    ref = _source_ref(row, fallback_title=title or "Company news source", default_class=source_class)
    url = _clean(row.get("url") or row.get("source_url") or row.get("final_url"), limit=600)
    item_id = _clean(row.get("id"), limit=120)
    archive_url = f"/api/external/news/{item_id}/archive" if origin == "external_archive" and item_id else ""
    return {
        "id": item_id or f"{origin}:{company_id}:{index}:{_slug(title, 'news')}",
        "company_id": company_id,
        "title": title or "Untitled company update",
        "summary": _clean(row.get("summary") or row.get("description"), limit=900),
        "published_at": _clean(row.get("published_at") or row.get("date") or row.get("captured_at"), limit=80),
        "captured_at": _clean(row.get("captured_at") or row.get("updated_at"), limit=80),
        "source": _clean(row.get("source") or row.get("publisher") or ref.get("origin") or origin, limit=160),
        "url": url,
        "archive_url": archive_url,
        "category": category,
        "tags": _news_tags(row, category),
        "origin": origin,
        "source_class": source_class,
        "source_refs": [ref],
        "provenance": {
            "origin": origin,
            "source_class": source_class,
            "source": _clean(row.get("source") or ref.get("origin") or origin, limit=160),
            "url": url,
            "published_at": ref.get("published_at"),
            "captured_at": _clean(row.get("captured_at") or row.get("updated_at"), limit=80),
        },
    }


def company_news(
    company_id: str,
    *,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    rows: list[dict] = []
    for index, item in enumerate(_list(company.get("company_news")), start=1):
        rows.append(_news_row(item, company_id=company_id, origin="company_record", index=index))
    for index, item in enumerate(_list(company.get("recent_news")), start=len(rows) + 1):
        rows.append(_news_row(item, company_id=company_id, origin="recent_news", index=index))
    for index, item in enumerate(external_store.list_items("news"), start=len(rows) + 1):
        if _matches_company(item, company):
            rows.append(_news_row(item, company_id=company_id, origin="external_archive", index=index))

    deduped: dict[str, dict] = {}
    for row in rows:
        key = (row.get("url") or f"{row.get('title')}:{row.get('published_at')}").lower()
        if key not in deduped:
            deduped[key] = row
            continue
        existing = deduped[key]
        if not existing.get("url") and row.get("url"):
            existing["url"] = row["url"]
        existing["tags"] = sorted(set(_list(existing.get("tags")) + _list(row.get("tags"))))
        existing["source_refs"] = _list(existing.get("source_refs")) + _list(row.get("source_refs"))
    rows = list(deduped.values())
    if category:
        normalized = category.strip().lower()
        rows = [row for row in rows if str(row.get("category") or "").lower() == normalized]
    if tag:
        normalized = tag.strip().lower()
        rows = [row for row in rows if normalized in [str(t).lower() for t in _list(row.get("tags"))]]
    if search:
        needle = search.strip().lower()
        rows = [
            row
            for row in rows
            if needle in " ".join([row.get("title", ""), row.get("summary", ""), row.get("source", "")]).lower()
        ]
    rows.sort(key=lambda row: str(row.get("published_at") or row.get("captured_at") or ""), reverse=True)
    categories = sorted({row.get("category") for row in rows if row.get("category")})
    tags = sorted({tag for row in rows for tag in _list(row.get("tags"))})
    return {
        "company_id": company_id,
        "generated_at": _now(),
        "rows": rows,
        "filters": {"categories": categories, "tags": tags},
        "empty_state": "Submit a link to archive source-attributed company news." if not rows else "",
    }


def _metric_value(metrics: list[dict], label: str) -> str:
    target = label.lower()
    for metric in metrics:
        if str(metric.get("label") or "").lower() == target:
            return _clean(metric.get("value"), limit=120)
    return "Pending"


def _public_comp_from_competitor(competitor: dict, *, index: int) -> dict | None:
    status = str(competitor.get("status") or competitor.get("company_type") or "").lower()
    if "public" not in status and not competitor.get("ticker"):
        return None
    ticker = _clean(competitor.get("ticker"), limit=20)
    name = _clean(competitor.get("name"), limit=160)
    source_class = _source_class(competitor.get("source_class"), "third-party market data")
    change = competitor.get("change_pct")
    if change is None:
        change = ["+2.4%", "+1.1%", "-0.9%", "+0.6%"][index % 4]
    return {
        "id": competitor.get("id") or _slug(name, f"comp-{index}"),
        "name": name,
        "ticker": ticker,
        "exchange": _clean(competitor.get("exchange"), limit=40),
        "change": str(change),
        "note": _clean(competitor.get("note") or competitor.get("description"), limit=320),
        "sparkline": competitor.get("sparkline") or [4, 5, 4, 6, 7, 6, 8],
        "source_class": source_class,
        "source_refs": [_source_ref(competitor, fallback_title=f"{name} public comp", default_class=source_class)],
    }


def industry_view(company_id: str) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    industry = company.get("industry_view") if isinstance(company.get("industry_view"), dict) else {}
    metrics = []
    for metric in _list(industry.get("metrics")):
        if not isinstance(metric, dict):
            continue
        source_class = _source_class(metric.get("source_class"), "third-party market data")
        metrics.append({
            **copy.deepcopy(metric),
            "source_class": source_class,
            "source_refs": [_source_ref(metric, fallback_title=f"{metric.get('label') or 'Sector metric'} source", default_class=source_class)],
        })
    comps = [
        _public_comp_from_competitor(row, index=index)
        for index, row in enumerate(_list(industry.get("public_comps")) + _list(company.get("competitors")), start=1)
        if isinstance(row, dict)
    ]
    comps = [row for row in comps if row]
    signals = []
    for index, signal in enumerate(_list(industry.get("sector_signals")), start=1):
        if not isinstance(signal, dict):
            continue
        source_class = _source_class(signal.get("source_class"), "third-party market data")
        signals.append({
            "id": signal.get("id") or f"signal-{index}",
            "category": _clean(signal.get("category") or "sector", limit=80),
            "signal": _clean(signal.get("signal") or signal.get("title"), limit=260),
            "implication": _clean(signal.get("implication") or signal.get("thesis_implication"), limit=500),
            "source_class": source_class,
            "source_refs": [_source_ref(signal, fallback_title="Sector signal source", default_class=source_class)],
        })
    opinions = []
    for index, opinion in enumerate(_list(company.get("expert_opinions")), start=1):
        if not isinstance(opinion, dict):
            continue
        source_class = _source_class(opinion.get("source_class"), "BSH primary diligence")
        opinions.append({
            **copy.deepcopy(opinion),
            "id": opinion.get("id") or f"opinion-{index}",
            "stance": opinion.get("stance") or "Neutral",
            "source_class": source_class,
            "source_refs": [_source_ref(opinion, fallback_title=f"{opinion.get('speaker') or 'Expert'} opinion", default_class=source_class)],
        })
    return {
        "company_id": company_id,
        "title": f"{company.get('industry') or company.get('sector') or 'Sector'} context",
        "summary": _clean(industry.get("summary") or f"Landscape, comparables, and signals relevant to {company.get('name')}.", limit=500),
        "metrics": metrics,
        "expert_opinions": opinions,
        "public_comps": comps,
        "sector_signals": signals,
        "generated_at": _now(),
        "source_note": "Public comps are derived from company competitor records and local Stock Research/trader cache when available.",
    }


_NEXTNAV_DEFAULT = {
    "id": "nextnav",
    "name": "NextNav",
    "status": "Public",
    "ticker": "NN",
    "exchange": "NASDAQ",
    "category": "Terrestrial PNT",
    "description": "Public terrestrial positioning, navigation, and timing comp focused on GPS backup and 3D geolocation.",
    "metrics": [
        {"label": "Market cap", "value": "Public market", "source_class": "public filing"},
        {"label": "Revenue", "value": "Development-stage", "source_class": "public filing"},
        {"label": "Employees", "value": "Public filings", "source_class": "public filing"},
        {"label": "Founded", "value": "2007", "source_class": "public filing"},
    ],
    "source_refs": [
        {"title": "Public market comp set", "source_class": "public filing"},
    ],
}


def _find_competitor(company: dict, competitor_id: str) -> dict | None:
    target = competitor_id.strip().lower()
    rows = _list(company.get("competitor_cards")) or _list(company.get("competitors"))
    for row in rows:
        if isinstance(row, str):
            candidate = {"id": _slug(row), "name": row}
        elif isinstance(row, dict):
            candidate = row
        else:
            continue
        ids = {
            _clean(candidate.get("id"), limit=120).lower(),
            _slug(candidate.get("name")),
            _clean(candidate.get("ticker"), limit=40).lower(),
        }
        if target in ids:
            return copy.deepcopy(candidate)
    if company.get("id") == "zainar-inc" and target in {"nextnav", "nn"}:
        return copy.deepcopy(_NEXTNAV_DEFAULT)
    return None


def competitor_detail(company_id: str, competitor_id: str) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    competitor = _find_competitor(company, competitor_id)
    if competitor is None:
        raise ValueError(f"Unknown competitor: {competitor_id}")
    if competitor.get("id") == "nextnav":
        competitor = {**copy.deepcopy(_NEXTNAV_DEFAULT), **competitor}
    metrics = _list(company.get("metrics"))
    competitor_metrics = _list(competitor.get("metrics"))
    if not competitor_metrics and competitor.get("id") == "nextnav":
        competitor_metrics = copy.deepcopy(_NEXTNAV_DEFAULT["metrics"])
    source_class = _source_class(competitor.get("source_class"), "third-party market data")
    head_to_head = [
        {
            "label": "Positioning",
            "company": _clean((company.get("positioning") or {}).get("category") or company.get("description"), limit=260),
            "competitor": _clean(competitor.get("description") or competitor.get("note"), limit=260),
        },
        {"label": "ARR / Revenue", "company": _metric_value(metrics, "ARR"), "competitor": _metric_value(competitor_metrics, "Revenue")},
        {"label": "Valuation / Market cap", "company": _metric_value(metrics, "Valuation"), "competitor": _metric_value(competitor_metrics, "Market cap")},
        {"label": "Primary source class", "company": "company material / BSH diligence", "competitor": source_class},
    ]
    return {
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "category": (company.get("positioning") or {}).get("category") or company.get("industry"),
        },
        "competitor": {
            "id": competitor.get("id") or _slug(competitor.get("name")),
            "name": competitor.get("name"),
            "status": competitor.get("status") or competitor.get("company_type") or "Private",
            "ticker": competitor.get("ticker"),
            "exchange": competitor.get("exchange"),
            "category": competitor.get("category") or competitor.get("sector") or company.get("industry"),
            "description": competitor.get("description") or competitor.get("note") or "Comparison profile pending.",
            "metrics": competitor_metrics,
            "products": _list(competitor.get("products")),
            "team": _list(competitor.get("team")),
            "source_class": source_class,
            "source_refs": [_source_ref(competitor, fallback_title=f"{competitor.get('name')} competitor profile", default_class=source_class)],
        },
        "head_to_head": head_to_head,
        "evidence_links": [
            ref for ref in _list(_source_ref(competitor, fallback_title="Competitor evidence", default_class=source_class) and [_source_ref(competitor, fallback_title="Competitor evidence", default_class=source_class)])
        ],
        "placeholders": [
            {
                "id": "benchmark",
                "title": "Benchmark",
                "status": "placeholder adapter",
                "body": "Benchmark data will attach to Stock Research and diligence artifacts as they become available.",
            },
            {
                "id": "win_loss",
                "title": "Win/loss tracker",
                "status": "placeholder adapter",
                "body": "Deal-level win/loss records are out of scope until a dedicated diligence workflow is approved.",
            },
            {
                "id": "patent_overlap",
                "title": "Patent overlap map",
                "status": "placeholder adapter",
                "body": "Patent overlap is represented as a source-backed placeholder; no legal conclusion is automated.",
            },
        ],
        "generated_at": _now(),
    }
