"""Durable PRD Memo Studio editor state.

This module owns the investor-facing memo editor layer. It is deliberately
separate from ``serena_analysis`` and final memo run folders: analysis artifacts
can seed an initial draft, but user include/rank/edit/export state lives here.
"""
from __future__ import annotations

import copy
import hashlib
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import analytics_store, serena_analysis, storage

SCHEMA_VERSION = 1
EDITOR_ROOT = storage.DATA_DIR / "memo_editor"

_LOCK = threading.RLock()

SECTION_INVESTMENT_THESIS = "investment_thesis"
SECTION_RISKS = "risks_mitigations"
SECTION_CONCLUSION = "conclusion"
SECTION_APPENDIX = "appendix"

CARD_SECTIONS = {SECTION_INVESTMENT_THESIS, SECTION_RISKS}

SOURCE_CLASSES = {
    "company material",
    "public filing",
    "third-party market data",
    "BSH primary diligence",
    "internal note",
    "generated memo",
    "unknown/pending",
}

_SOURCE_CLASS_ALIASES = {
    "company": "company material",
    "company materials": "company material",
    "company material": "company material",
    "company-reported": "company material",
    "public": "public filing",
    "public comp": "public filing",
    "public comps": "public filing",
    "public filing": "public filing",
    "filing": "public filing",
    "third party": "third-party market data",
    "third-party": "third-party market data",
    "third-party market data": "third-party market data",
    "market data": "third-party market data",
    "bsh": "BSH primary diligence",
    "bsh diligence": "BSH primary diligence",
    "bsh comp set": "BSH primary diligence",
    "bsh primary diligence": "BSH primary diligence",
    "internal": "internal note",
    "internal note": "internal note",
    "generated": "generated memo",
    "generated memo": "generated memo",
    "memo": "generated memo",
    "unknown": "unknown/pending",
    "pending": "unknown/pending",
    "unknown/pending": "unknown/pending",
}

_KEY_FIGURE_PATTERNS = [
    re.compile(r"[$€¥]\s?\d[\d,]*(?:\.\d+)?\s?(?:[KMB]|bn|mm|million|billion)?\+?", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?%"),
    re.compile(r"\b\d+(?:\.\d+)?x\b", re.I),
    re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:M|B|bn|mm|million|billion)\+?\b", re.I),
    re.compile(
        r"\b(?:ARR|TAM|valuation|revenue|growth|post-money|contract|pipeline|"
        r"ownership|CAGR|EV/NTM|multiple)[^.\n;:]{0,100}?\d",
        re.I,
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]", "", str(value or "").lower())
    if not cleaned:
        raise ValueError("Invalid company id")
    return cleaned


def _company_dir(company_id: str) -> Path:
    return EDITOR_ROOT / _safe_id(company_id)


def state_path(company_id: str) -> Path:
    return _company_dir(company_id) / "state.yaml"


def _versions_dir(company_id: str) -> Path:
    return _company_dir(company_id) / "versions"


def _version_snapshot_path(company_id: str, revision_id: str) -> Path:
    return _versions_dir(company_id) / f"{_safe_id(revision_id)}.yaml"


def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else default


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    tmp.replace(path)


def _write_version_snapshot(company_id: str, state: dict, event: str) -> None:
    revision_id = _clean_text(state.get("revision_id"), limit=80)
    if not revision_id:
        return
    payload = {
        "revision_id": revision_id,
        "revision": state.get("revision"),
        "version_id": state.get("version_id"),
        "company_id": company_id,
        "company_name": state.get("company_name"),
        "status": state.get("status"),
        "event": event,
        "created_at": _now(),
        "state": copy.deepcopy(state),
    }
    _write_yaml(_version_snapshot_path(company_id, revision_id), payload)


def _clean_text(value: Any, *, limit: int = 1000) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _slug_part(value: Any, *, fallback: str) -> str:
    text = _clean_text(value, limit=120).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or fallback


def _stable_id(prefix: str, text: Any, index: int) -> str:
    slug = _slug_part(text, fallback=f"{prefix}-{index}")[:42].strip("-")
    digest = hashlib.sha1(f"{prefix}:{index}:{text}".encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{slug}-{digest}"


def normalize_source_class(value: Any) -> str:
    raw = _clean_text(value, limit=80).lower()
    if not raw:
        return "unknown/pending"
    if raw in _SOURCE_CLASS_ALIASES:
        return _SOURCE_CLASS_ALIASES[raw]
    raw = raw.replace("_", " ").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return _SOURCE_CLASS_ALIASES.get(raw, "unknown/pending")


def normalize_source_ref(
    value: Any,
    *,
    default_source_class: Any = None,
    fallback_title: str = "Source pending",
) -> dict:
    if isinstance(value, str):
        value = {"title": value}
    payload = value if isinstance(value, dict) else {}
    source_class = normalize_source_class(
        payload.get("source_class") or default_source_class
    )
    title = _clean_text(
        payload.get("title")
        or payload.get("label")
        or payload.get("source")
        or payload.get("origin")
        or fallback_title,
        limit=240,
    )
    return {
        "title": title or fallback_title,
        "origin": _clean_text(
            payload.get("origin") or payload.get("source") or payload.get("author"),
            limit=240,
        ),
        "url": _clean_text(payload.get("url"), limit=500),
        "file": _clean_text(
            payload.get("file")
            or payload.get("filename")
            or payload.get("path")
            or payload.get("stored_name"),
            limit=500,
        ),
        "captured_at": _clean_text(
            payload.get("captured_at")
            or payload.get("uploaded_at")
            or payload.get("created_at"),
            limit=80,
        ),
        "published_at": _clean_text(
            payload.get("published_at") or payload.get("as_of") or payload.get("date"),
            limit=80,
        ),
        "language": _clean_text(payload.get("language"), limit=20) or "unknown",
        "source_class": source_class,
        "confidence": _clean_text(payload.get("confidence"), limit=40) or "pending",
        "status": _clean_text(payload.get("status"), limit=40) or "pending",
    }


def normalize_source_refs(
    value: Any,
    *,
    default_source_class: Any = None,
    fallback_title: str = "Source pending",
) -> list[dict]:
    refs = [
        normalize_source_ref(
            item,
            default_source_class=default_source_class,
            fallback_title=fallback_title,
        )
        for item in _list(value)
    ]
    if refs:
        return refs
    source_class = normalize_source_class(default_source_class)
    if source_class == "unknown/pending":
        return []
    return [
        normalize_source_ref(
            {"title": fallback_title, "source_class": source_class},
            fallback_title=fallback_title,
        )
    ]


def _source_covered(value: dict) -> bool:
    refs = [
        ref for ref in _list(value.get("source_refs"))
        if normalize_source_class(ref.get("source_class")) != "unknown/pending"
        or _clean_text(ref.get("title")) not in {"", "Source pending"}
    ]
    if refs:
        return True
    return normalize_source_class(value.get("source_class")) != "unknown/pending"


def _key_figure_terms(text: Any) -> list[str]:
    body = _clean_text(text, limit=4000)
    if not body:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for pattern in _KEY_FIGURE_PATTERNS:
        for match in pattern.finditer(body):
            term = match.group(0).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                out.append(term)
    return out


def _company_source_refs(company: dict, *, fallback_title: str) -> list[dict]:
    refs = normalize_source_refs(
        company.get("source_refs"),
        default_source_class=company.get("source_class") or "company material",
        fallback_title=fallback_title,
    )
    if refs:
        return refs
    return normalize_source_refs(
        [{"title": fallback_title, "source_class": "company material"}],
        fallback_title=fallback_title,
    )


def _metric_source_refs(metric: dict) -> list[dict]:
    return normalize_source_refs(
        metric.get("source_refs"),
        default_source_class=metric.get("source_class"),
        fallback_title=f"{metric.get('label') or 'Metric'} source",
    )


def _metric_line(metric: dict) -> str:
    label = _clean_text(metric.get("label"), limit=80)
    value = _clean_text(metric.get("value"), limit=80)
    unit = _clean_text(metric.get("unit"), limit=40)
    if not label and not value:
        return ""
    suffix = f" {unit}" if unit and unit not in value else ""
    as_of = _clean_text(metric.get("as_of"), limit=80)
    return f"{label}: {value}{suffix}{f' as of {as_of}' if as_of else ''}."


def _first_metric(company: dict, label: str) -> dict:
    target = label.lower()
    for metric in _list(company.get("metrics")):
        if isinstance(metric, dict) and _clean_text(metric.get("label")).lower() == target:
            return metric
    return {}


def _analysis_thesis(company_id: str) -> dict:
    try:
        session = serena_analysis.get_current_session(company_id, create=False)
    except Exception:
        return {}
    if not isinstance(session, dict):
        return {}
    artifacts = session.get("artifacts") if isinstance(session.get("artifacts"), dict) else {}
    thesis = artifacts.get("thesis_spine") if isinstance(artifacts.get("thesis_spine"), dict) else {}
    return copy.deepcopy(thesis)


def _bullet(
    text: str,
    *,
    index: int,
    source_refs: list[dict] | None = None,
    source_class: Any = None,
    confidence: Any = None,
) -> dict:
    return {
        "id": _stable_id("bullet", text, index),
        "text": text,
        "children": [],
        "source_refs": source_refs or [],
        "source_class": normalize_source_class(source_class),
        "confidence": _clean_text(confidence, limit=40) or "pending",
    }


def _card(
    *,
    prefix: str,
    index: int,
    title: str,
    category: str,
    bullets: list[dict],
    source_refs: list[dict],
    source_class: Any,
    confidence: Any = None,
    severity: Any = None,
) -> dict:
    return {
        "id": _stable_id(prefix, title, index),
        "title": title,
        "category": category,
        "severity": _clean_text(severity, limit=40),
        "included": True,
        "rank": index,
        "expanded": index == 1,
        "bullets": bullets,
        "source_refs": source_refs,
        "source_class": normalize_source_class(source_class),
        "confidence": _clean_text(confidence, limit=40) or "pending",
    }


def _analysis_cards(rows: Any, *, prefix: str, fallback_class: str) -> list[dict]:
    out: list[dict] = []
    for index, row in enumerate(_list(rows), start=1):
        if not isinstance(row, dict):
            continue
        title = _clean_text(
            row.get("title")
            or row.get("claim")
            or row.get("risk")
            or row.get("sensitivity"),
            limit=220,
        )
        if not title:
            continue
        refs = normalize_source_refs(
            row.get("source_refs")
            or row.get("source_traces")
            or row.get("supporting_evidence"),
            default_source_class=row.get("source_class") or fallback_class,
            fallback_title=f"{title} source",
        )
        bullet_texts = [
            _clean_text(value, limit=700)
            for value in [
                row.get("support"),
                row.get("evidence"),
                row.get("why_it_matters"),
                row.get("memo_treatment"),
                row.get("mitigation"),
                row.get("expected_bar"),
            ]
            if _clean_text(value)
        ]
        if not bullet_texts:
            bullet_texts = [title]
        bullets = [
            _bullet(
                text,
                index=bullet_index,
                source_refs=refs,
                source_class=row.get("source_class") or fallback_class,
                confidence=row.get("confidence"),
            )
            for bullet_index, text in enumerate(bullet_texts[:5], start=1)
        ]
        out.append(
            _card(
                prefix=prefix,
                index=index,
                title=title,
                category=_clean_text(row.get("category"), limit=80) or "Evidence",
                bullets=bullets,
                source_refs=refs,
                source_class=row.get("source_class") or fallback_class,
                confidence=row.get("confidence"),
                severity=row.get("severity"),
            )
        )
        if len(out) >= 5:
            break
    return out


def _fallback_thesis_cards(company: dict) -> list[dict]:
    company_refs = _company_source_refs(
        company,
        fallback_title=f"{company.get('name') or company.get('id')} company record",
    )
    positioning = company.get("positioning") if isinstance(company.get("positioning"), dict) else {}
    positioning_refs = normalize_source_refs(
        positioning.get("source_refs"),
        default_source_class=positioning.get("source_class") or "company material",
        fallback_title="Positioning source",
    ) or company_refs
    metrics = [m for m in _list(company.get("metrics")) if isinstance(m, dict)]
    metric_refs: list[dict] = []
    for metric in metrics:
        metric_refs.extend(_metric_source_refs(metric))
    if not metric_refs:
        metric_refs = company_refs
    products = _list(company.get("products"))
    product_names = ", ".join(
        _clean_text(p.get("name") if isinstance(p, dict) else p, limit=60)
        for p in products[:3]
        if _clean_text(p.get("name") if isinstance(p, dict) else p)
    )
    company_label = (
        _clean_text(company.get("name"), limit=80)
        or _clean_text(company.get("id"), limit=80)
        or "The company"
    )
    # Fallback card text must stay company-neutral or company-derived.
    # Earlier revisions hardcoded Zainar-specific claims (sub-meter
    # positioning, GPS-alternative) here, which seeded every other
    # company's editor with another company's assets.
    cards = [
        _card(
            prefix="thesis",
            index=1,
            title=f"{company_label} claims a differentiated technology position.",
            category="Technology moat",
            bullets=[
                _bullet(
                    _clean_text(positioning.get("differentiator"), limit=500)
                    or _clean_text(company.get("description"), limit=500)
                    or "Differentiation claims are not yet documented; treat this thesis as pending diligence.",
                    index=1,
                    source_refs=positioning_refs,
                    source_class="company material",
                    confidence="medium",
                ),
                _bullet(
                    _clean_text(positioning.get("benefit"), limit=500)
                    or "The core customer benefit has not been independently verified; source it before export.",
                    index=2,
                    source_refs=positioning_refs,
                    source_class="company material",
                    confidence="medium",
                ),
            ],
            source_refs=positioning_refs,
            source_class="company material",
            confidence="medium",
        ),
        _card(
            prefix="thesis",
            index=2,
            title="Disclosed metrics frame the underwriting baseline.",
            category="Commercial traction",
            bullets=[
                _bullet(
                    _metric_line(metric),
                    index=i,
                    source_refs=_metric_source_refs(metric),
                    source_class=metric.get("source_class"),
                    confidence=metric.get("confidence"),
                )
                for i, metric in enumerate(metrics[:4], start=1)
                if _metric_line(metric)
            ] or [
                _bullet(
                    "Company metrics are not yet populated; underwriting should keep this section incomplete.",
                    index=1,
                    source_class="unknown/pending",
                )
            ],
            source_refs=metric_refs,
            source_class="BSH primary diligence",
            confidence="medium",
        ),
        _card(
            prefix="thesis",
            index=3,
            title="Use cases span multiple enterprise demand pools.",
            category="Market expansion",
            bullets=[
                _bullet(
                    f"Initial product areas include {product_names}.",
                    index=1,
                    source_refs=company_refs,
                    source_class="company material",
                    confidence="medium",
                ),
                _bullet(
                    _clean_text(company.get("description"), limit=500)
                    or "Product-market context is incomplete.",
                    index=2,
                    source_refs=company_refs,
                    source_class="company material",
                    confidence="medium",
                ),
            ],
            source_refs=company_refs,
            source_class="company material",
            confidence="medium",
        ),
    ]
    return cards


def _fallback_risk_cards(company: dict) -> list[dict]:
    diligence_refs = normalize_source_refs(
        [{"title": "BSH PRD reference package", "source_class": "BSH primary diligence"}],
        fallback_title="BSH diligence source",
    )
    industry = company.get("industry_view") if isinstance(company.get("industry_view"), dict) else {}
    signals = [s for s in _list(industry.get("sector_signals")) if isinstance(s, dict)]
    signal_refs = normalize_source_refs(
        [{"title": "Industry view signal set", "source_class": "third-party market data"}],
        fallback_title="Industry view signal set",
    )
    valuation = _first_metric(company, "Valuation")
    valuation_refs = _metric_source_refs(valuation) if valuation else diligence_refs
    cards = [
        _card(
            prefix="risk",
            index=1,
            title="Revenue quality needs independent source coverage.",
            category="Evidence gap",
            severity="high",
            bullets=[
                _bullet(
                    "Booked ARR, contract terms, and pilot-to-production conversion should be independently verified before export.",
                    index=1,
                    source_refs=diligence_refs,
                    source_class="BSH primary diligence",
                    confidence="medium",
                )
            ],
            source_refs=diligence_refs,
            source_class="BSH primary diligence",
            confidence="medium",
        ),
        _card(
            prefix="risk",
            index=2,
            title="Competitive or platform shifts could compress moat durability.",
            category="Technology/IP",
            severity="medium",
            bullets=[
                _bullet(
                    _clean_text(signals[0].get("implication"), limit=500)
                    if signals
                    else "Patent, standards, and competitive diligence should test whether the claimed moat survives platform-level adoption by larger players.",
                    index=1,
                    source_refs=signal_refs,
                    source_class="third-party market data",
                    confidence="medium",
                )
            ],
            source_refs=signal_refs,
            source_class="third-party market data",
            confidence="medium",
        ),
        _card(
            prefix="risk",
            index=3,
            title="Valuation step-up requires stronger third-party validation.",
            category="Valuation",
            severity="medium",
            bullets=[
                _bullet(
                    _metric_line(valuation)
                    or "Valuation support is incomplete and should stay sensitivity-weighted.",
                    index=1,
                    source_refs=valuation_refs,
                    source_class=valuation.get("source_class") if valuation else "BSH primary diligence",
                    confidence=valuation.get("confidence") if valuation else "medium",
                )
            ],
            source_refs=valuation_refs,
            source_class=valuation.get("source_class") if valuation else "BSH primary diligence",
            confidence=valuation.get("confidence") if valuation else "medium",
        ),
    ]
    return cards


def _appendix_blocks(company: dict) -> list[dict]:
    company_refs = _company_source_refs(
        company,
        fallback_title=f"{company.get('name') or company.get('id')} company record",
    )
    metrics = [m for m in _list(company.get("metrics")) if isinstance(m, dict)]
    metric_refs: list[dict] = []
    metric_facts = []
    for metric in metrics:
        line = _metric_line(metric)
        if line:
            metric_facts.append(line)
            metric_refs.extend(_metric_source_refs(metric))
    industry = company.get("industry_view") if isinstance(company.get("industry_view"), dict) else {}
    team = [
        _clean_text(f"{p.get('name')} - {p.get('role')}", limit=160)
        for p in _list(company.get("team_profiles") or company.get("key_people"))
        if isinstance(p, dict) and _clean_text(p.get("name"))
    ]
    investors = [
        _clean_text(f"{p.get('name')} - {p.get('role')}", limit=180)
        for p in _list(company.get("board_investors"))
        if isinstance(p, dict) and _clean_text(p.get("name"))
    ]
    disclosures = [
        _clean_text(d.get("body") or d.get("label"), limit=260)
        for d in _list(company.get("disclosures"))
        if isinstance(d, dict) and _clean_text(d.get("body") or d.get("label"))
    ]
    blocks = [
        {
            "id": "company_overview",
            "title": "Company Overview",
            "status": "ready" if company.get("description") else "incomplete",
            "expanded": False,
            "facts": [
                _clean_text(company.get("description"), limit=700),
                f"HQ: {_clean_text(company.get('hq'), limit=120)}" if company.get("hq") else "",
                f"Founded: {_clean_text(company.get('founded_year'), limit=40)}" if company.get("founded_year") else "",
            ],
            "source_refs": company_refs,
            "source_class": "company material",
        },
        {
            "id": "business_model",
            "title": "Business Model",
            "status": "ready" if metric_facts else "incomplete",
            "expanded": False,
            "facts": metric_facts or ["Business model metrics are incomplete."],
            "source_refs": metric_refs,
            "source_class": "BSH primary diligence",
        },
        {
            "id": "market_context",
            "title": "Market Context",
            "status": "ready" if industry.get("metrics") else "incomplete",
            "expanded": False,
            "facts": [
                _metric_line(metric)
                for metric in _list(industry.get("metrics"))
                if isinstance(metric, dict) and _metric_line(metric)
            ] or ["Market context is incomplete."],
            "source_refs": normalize_source_refs(
                [{"title": "Industry view metrics", "source_class": "third-party market data"}],
                fallback_title="Industry view metrics",
            ),
            "source_class": "third-party market data",
        },
        {
            "id": "technology_ip",
            "title": "Technology/IP & Competitive Position",
            "status": "ready" if company.get("products") or company.get("competitors") else "incomplete",
            "expanded": False,
            "facts": [
                _clean_text(p.get("description"), limit=260)
                for p in _list(company.get("products"))
                if isinstance(p, dict) and _clean_text(p.get("description"))
            ][:4] or ["Technology/IP detail is incomplete."],
            "source_refs": company_refs,
            "source_class": "company material",
        },
        {
            "id": "team_investors",
            "title": "Team & Investor Base",
            "status": "ready" if team or investors else "incomplete",
            "expanded": False,
            "facts": (team[:4] + investors[:4]) or ["Team and investor data is incomplete."],
            "source_refs": company_refs,
            "source_class": "company material",
        },
        {
            "id": "risks_model_treatment",
            "title": "Investment Risks & Model Treatment",
            "status": "ready",
            "expanded": False,
            "facts": [
                "Quantitative claims must retain source/source-class coverage before export.",
                "Missing revenue quality evidence should remain visible as a model sensitivity.",
            ],
            "source_refs": normalize_source_refs(
                [{"title": "BSH memo guardrail policy", "source_class": "BSH primary diligence"}],
                fallback_title="BSH memo guardrail policy",
            ),
            "source_class": "BSH primary diligence",
        },
        {
            "id": "return_exit",
            "title": "Return Framework & Exit Scenarios",
            "status": "incomplete",
            "expanded": False,
            "facts": ["Return framework is not populated yet; keep exit scenarios pending."],
            "source_refs": [],
            "source_class": "unknown/pending",
        },
        {
            "id": "evidence_required",
            "title": "Evidence Required for a Step-Up Case",
            "status": "ready",
            "expanded": False,
            "facts": [
                "Confirmed lead investor, round size, and timing.",
                "Audited revenue, pilot-to-production conversion, and contract terms.",
                "Claim-chart analysis versus relevant standards and carrier licensing intent.",
            ],
            "source_refs": normalize_source_refs(
                [{"title": "BSH diligence checklist", "source_class": "BSH primary diligence"}],
                fallback_title="BSH diligence checklist",
            ),
            "source_class": "BSH primary diligence",
        },
        {
            "id": "sources_disclosures",
            "title": "Sources/Source Classes/Disclosures",
            "status": "ready" if disclosures else "incomplete",
            "expanded": False,
            "facts": disclosures or ["Disclosures are pending."],
            "source_refs": normalize_source_refs(
                [{"title": "Company disclosure record", "source_class": "internal note"}],
                fallback_title="Company disclosure record",
            ),
            "source_class": "internal note",
        },
    ]
    for block in blocks:
        block["facts"] = [fact for fact in block["facts"] if fact]
    return blocks


def _initial_state(company_id: str) -> dict:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    thesis = _analysis_thesis(company_id)
    highlights = _analysis_cards(
        thesis.get("investment_highlights"),
        prefix="thesis",
        fallback_class="BSH primary diligence",
    ) or _fallback_thesis_cards(company)
    risks = _analysis_cards(
        thesis.get("investment_risks"),
        prefix="risk",
        fallback_class="BSH primary diligence",
    ) or _fallback_risk_cards(company)
    metrics = [m for m in _list(company.get("metrics")) if isinstance(m, dict)]
    metric_lines = [_metric_line(metric) for metric in metrics if _metric_line(metric)]
    metric_refs: list[dict] = []
    for metric in metrics:
        metric_refs.extend(_metric_source_refs(metric))
    company_name = company.get("name") or company_id
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "company_id": company_id,
        "company_name": company_name,
        "version": 1,
        "version_id": "v1",
        "revision": 1,
        "revision_id": "rev-0001",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "sections": {
            "executive_summary": {
                "id": "executive_summary",
                "title": "Executive Summary",
                "status": "ready_for_input",
                "body": (
                    f"{company_name} is framed as a late-stage investment candidate. "
                    f"Current metric snapshot: {' '.join(metric_lines[:4])}"
                    if metric_lines
                    else f"{company_name} has no complete metric snapshot yet."
                ),
                "recommendation": "Conditional: proceed only where source-backed traction and valuation support are visible.",
                "round": _clean_text(
                    (company.get("latest_funding") or {}).get("round")
                    if isinstance(company.get("latest_funding"), dict)
                    else "",
                    limit=120,
                ),
                "top_gate": "Resolve unsupported revenue, growth, valuation, and market-size claims before export.",
                "source_refs": metric_refs,
                "source_class": "BSH primary diligence",
            },
            SECTION_INVESTMENT_THESIS: {
                "id": SECTION_INVESTMENT_THESIS,
                "title": "Investment Thesis",
                "status": "ready_for_input",
                "cards": highlights,
            },
            SECTION_RISKS: {
                "id": SECTION_RISKS,
                "title": "Risks and Mitigations",
                "status": "ready_for_input",
                "cards": risks,
            },
            SECTION_CONCLUSION: {
                "id": SECTION_CONCLUSION,
                "title": "Conclusion",
                "status": "ready_for_input",
                "selected_option_id": "conditional",
                "options": [
                    {
                        "id": "conditional",
                        "label": "Conditional proceed",
                        "text": "Proceed if the next diligence pass confirms source-backed traction, valuation support, and risk controls.",
                        "source_refs": normalize_source_refs(
                            [{"title": "BSH investment committee framing", "source_class": "BSH primary diligence"}],
                            fallback_title="BSH investment committee framing",
                        ),
                        "source_class": "BSH primary diligence",
                    },
                    {
                        "id": "lead_anchor",
                        "label": "Lead and anchor",
                        "text": "Lead or anchor only if pricing and source-backed growth support a clear step-up case.",
                        "source_refs": normalize_source_refs(
                            [{"title": "BSH investment committee framing", "source_class": "BSH primary diligence"}],
                            fallback_title="BSH investment committee framing",
                        ),
                        "source_class": "BSH primary diligence",
                    },
                    {
                        "id": "pass",
                        "label": "Pass",
                        "text": "Pass if revenue quality, IP durability, or valuation evidence remains unresolved.",
                        "source_refs": normalize_source_refs(
                            [{"title": "BSH investment committee framing", "source_class": "BSH primary diligence"}],
                            fallback_title="BSH investment committee framing",
                        ),
                        "source_class": "BSH primary diligence",
                    },
                ],
            },
            SECTION_APPENDIX: {
                "id": SECTION_APPENDIX,
                "title": "Appendix",
                "status": "ready_for_input",
                "blocks": _appendix_blocks(company),
            },
        },
        "audit_records": [
            {
                "id": "audit-initialized",
                "event": "memo_editor_initialized",
                "created_at": now,
                "detail": "Initialized PRD Memo Studio editor state.",
            }
        ],
        "memo_tasks": [],
    }


def _audit(state: dict, event: str, **detail: Any) -> None:
    rows = _list(state.get("audit_records"))
    rows.append({
        "id": _stable_id("audit", f"{event}:{_now()}:{len(rows)}", len(rows) + 1),
        "event": event,
        "created_at": _now(),
        "detail": detail,
    })
    state["audit_records"] = rows


def _append_task(
    state: dict,
    *,
    action_type: str,
    title: str,
    description: str = "",
    context: dict | None = None,
    status: str = "proposed",
    created_by: str = "co-pilot",
) -> dict:
    status = status if status in {"proposed", "accepted", "rejected", "completed"} else "proposed"
    rows = _list(state.get("memo_tasks"))
    task = {
        "id": _stable_id("task", f"{action_type}:{title}:{_now()}:{len(rows)}", len(rows) + 1),
        "action_type": _clean_text(action_type, limit=80) or "memo_task",
        "title": _clean_text(title, limit=240) or "Memo task",
        "description": _clean_text(description, limit=1000),
        "context": copy.deepcopy(context or {}),
        "status": status,
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": _now() if status == "completed" else "",
    }
    rows.append(task)
    state["memo_tasks"] = rows
    _audit(
        state,
        "memo_task_created",
        task_id=task["id"],
        action_type=task["action_type"],
        status=task["status"],
    )
    analytics_store.record_event(
        "copilot_task_proposed",
        company_id=state.get("company_id"),
        task_id=task["id"],
        action_type=task["action_type"],
        status=task["status"],
    )
    if status in {"accepted", "completed"}:
        analytics_store.record_event(
            "copilot_task_actioned",
            company_id=state.get("company_id"),
            task_id=task["id"],
            action_type=task["action_type"],
            status=task["status"],
        )
    return task


def get_state(company_id: str, *, create: bool = True) -> dict | None:
    path = state_path(company_id)
    with _LOCK:
        data = _read_yaml(path, None)
        if isinstance(data, dict):
            return copy.deepcopy(_normalize_state(data))
        if not create:
            return None
        state = _initial_state(company_id)
        _write_yaml(path, state)
        _write_version_snapshot(company_id, state, "memo_editor_initialized")
        analytics_store.record_event(
            "memo_first_draft_ready",
            company_id=company_id,
            version_id=state.get("version_id"),
            revision_id=state.get("revision_id"),
        )
        return copy.deepcopy(state)


def _save_state(company_id: str, state: dict) -> dict:
    state["schema_version"] = SCHEMA_VERSION
    state["revision"] = int(state.get("revision") or 1) + 1
    state["revision_id"] = f"rev-{int(state['revision']):04d}"
    state["updated_at"] = _now()
    _write_yaml(state_path(company_id), state)
    latest_event = "memo_editor_updated"
    audit_rows = _list(state.get("audit_records"))
    if audit_rows:
        latest_event = audit_rows[-1].get("event") or latest_event
    _write_version_snapshot(company_id, state, latest_event)
    return copy.deepcopy(state)


def _normalize_state(state: dict) -> dict:
    normalized = copy.deepcopy(state)
    normalized.setdefault("schema_version", SCHEMA_VERSION)
    normalized.setdefault("version", 1)
    normalized.setdefault("version_id", "v1")
    normalized.setdefault("revision", 1)
    normalized.setdefault("revision_id", f"rev-{int(normalized.get('revision') or 1):04d}")
    normalized.setdefault("status", "draft")
    normalized.setdefault("sections", {})
    normalized.setdefault("audit_records", [])
    normalized.setdefault("memo_tasks", [])
    sections = normalized["sections"]
    for section_id in CARD_SECTIONS:
        section = sections.get(section_id)
        if not isinstance(section, dict):
            continue
        cards = [card for card in _list(section.get("cards")) if isinstance(card, dict)]
        cards.sort(key=lambda c: int(c.get("rank") or 999))
        for index, card in enumerate(cards, start=1):
            card["rank"] = index
            card["source_class"] = normalize_source_class(card.get("source_class"))
            raw_card_refs = (
                card.get("source_refs") if "source_refs" in card else None
            )
            card["source_refs"] = normalize_source_refs(
                raw_card_refs,
                default_source_class=card.get("source_class"),
                fallback_title=f"{card.get('title') or 'Card'} source",
            )
            card["bullets"] = _normalize_bullets(card.get("bullets"), card)
        section["cards"] = cards
    appendix = sections.get(SECTION_APPENDIX)
    if isinstance(appendix, dict):
        for block in _list(appendix.get("blocks")):
            if isinstance(block, dict):
                block["source_class"] = normalize_source_class(block.get("source_class"))
                raw_block_refs = (
                    block.get("source_refs") if "source_refs" in block else None
                )
                block["source_refs"] = normalize_source_refs(
                    raw_block_refs,
                    default_source_class=block.get("source_class"),
                    fallback_title=f"{block.get('title') or 'Appendix'} source",
                )
    return normalized


def _normalize_bullets(value: Any, parent: dict) -> list[dict]:
    bullets = []
    for index, bullet in enumerate(_list(value), start=1):
        if not isinstance(bullet, dict):
            continue
        item = copy.deepcopy(bullet)
        item.setdefault("id", _stable_id("bullet", item.get("text"), index))
        item["source_class"] = normalize_source_class(
            item.get("source_class") or parent.get("source_class")
        )
        raw_refs = item.get("source_refs") if "source_refs" in item else parent.get("source_refs")
        item["source_refs"] = normalize_source_refs(
            raw_refs,
            default_source_class=item.get("source_class"),
            fallback_title=f"{parent.get('title') or 'Bullet'} source",
        )
        item["children"] = _normalize_bullets(item.get("children"), item)
        bullets.append(item)
    return bullets


def _get_section(state: dict, section_id: str) -> dict:
    section = (state.get("sections") or {}).get(section_id)
    if not isinstance(section, dict):
        raise ValueError(f"Unknown memo editor section: {section_id}")
    return section


def _find_card(state: dict, section_id: str, card_id: str) -> dict:
    if section_id not in CARD_SECTIONS:
        raise ValueError(f"Section does not contain cards: {section_id}")
    for card in _list(_get_section(state, section_id).get("cards")):
        if isinstance(card, dict) and card.get("id") == card_id:
            return card
    raise ValueError(f"Unknown memo editor card: {card_id}")


def patch_card(company_id: str, section_id: str, card_id: str, patch: dict) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        card = _find_card(state, section_id, card_id)
        changed: dict[str, Any] = {}
        for key in ("included", "expanded"):
            if key in patch and patch[key] is not None:
                card[key] = bool(patch[key])
                changed[key] = card[key]
        for key in ("title", "category", "severity", "confidence"):
            if key in patch and patch[key] is not None:
                card[key] = _clean_text(patch[key], limit=240)
                changed[key] = card[key]
        if patch.get("source_class") is not None:
            card["source_class"] = normalize_source_class(patch.get("source_class"))
            changed["source_class"] = card["source_class"]
        if patch.get("source_refs") is not None:
            card["source_refs"] = normalize_source_refs(
                patch.get("source_refs"),
                default_source_class=card.get("source_class"),
                fallback_title=f"{card.get('title') or 'Card'} source",
            )
            changed["source_refs"] = card["source_refs"]
        _audit(state, "card_updated", section_id=section_id, card_id=card_id, patch=changed)
        return _save_state(company_id, state)


def move_card(company_id: str, section_id: str, card_id: str, direction: str) -> dict:
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'")
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        section = _get_section(state, section_id)
        cards = [card for card in _list(section.get("cards")) if isinstance(card, dict)]
        cards.sort(key=lambda c: int(c.get("rank") or 999))
        index = next((i for i, card in enumerate(cards) if card.get("id") == card_id), -1)
        if index < 0:
            raise ValueError(f"Unknown memo editor card: {card_id}")
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(cards):
            cards[index], cards[target] = cards[target], cards[index]
        for rank, card in enumerate(cards, start=1):
            card["rank"] = rank
        section["cards"] = cards
        _audit(state, "card_rank_changed", section_id=section_id, card_id=card_id, direction=direction)
        return _save_state(company_id, state)


def _find_bullet(bullets: list, bullet_id: str) -> dict | None:
    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        if bullet.get("id") == bullet_id:
            return bullet
        found = _find_bullet(_list(bullet.get("children")), bullet_id)
        if found is not None:
            return found
    return None


def patch_bullet(
    company_id: str,
    section_id: str,
    card_id: str,
    bullet_id: str,
    patch: dict,
) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        card = _find_card(state, section_id, card_id)
        bullet = _find_bullet(_list(card.get("bullets")), bullet_id)
        if bullet is None:
            raise ValueError(f"Unknown memo editor bullet: {bullet_id}")
        if patch.get("text") is not None:
            previous = bullet.get("text")
            bullet["text"] = _clean_text(patch.get("text"), limit=1200)
            _audit(
                state,
                "bullet_edited",
                section_id=section_id,
                card_id=card_id,
                bullet_id=bullet_id,
                previous=previous,
                text=bullet["text"],
            )
        if patch.get("source_class") is not None:
            bullet["source_class"] = normalize_source_class(patch.get("source_class"))
        if patch.get("source_refs") is not None:
            bullet["source_refs"] = normalize_source_refs(
                patch.get("source_refs"),
                default_source_class=bullet.get("source_class"),
                fallback_title=f"{card.get('title') or 'Bullet'} source",
            )
        return _save_state(company_id, state)


def add_dive_deeper(
    company_id: str,
    section_id: str,
    card_id: str,
    bullet_id: str,
    *,
    text: str | None = None,
) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        card = _find_card(state, section_id, card_id)
        bullet = _find_bullet(_list(card.get("bullets")), bullet_id)
        if bullet is None:
            raise ValueError(f"Unknown memo editor bullet: {bullet_id}")
        child_text = _clean_text(text, limit=1200) or (
            "Dive deeper: validate this point against primary evidence before "
            "raising its weight in the exported memo."
        )
        children = _list(bullet.get("children"))
        children.append(
            _bullet(
                child_text,
                index=len(children) + 1,
                source_refs=_list(bullet.get("source_refs")),
                source_class=bullet.get("source_class"),
                confidence=bullet.get("confidence"),
            )
        )
        bullet["children"] = children
        _audit(
            state,
            "bullet_dive_deeper_added",
            section_id=section_id,
            card_id=card_id,
            bullet_id=bullet_id,
        )
        _append_task(
            state,
            action_type="dive_deeper",
            title=f"Review deeper evidence for {card.get('title') or 'memo point'}",
            description=child_text,
            context={
                "section_id": section_id,
                "card_id": card_id,
                "card_title": card.get("title"),
                "bullet_id": bullet_id,
                "bullet_text": bullet.get("text"),
            },
            status="completed",
        )
        return _save_state(company_id, state)


def select_conclusion(company_id: str, conclusion_id: str) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        conclusion = _get_section(state, SECTION_CONCLUSION)
        ids = {row.get("id") for row in _list(conclusion.get("options")) if isinstance(row, dict)}
        if conclusion_id not in ids:
            raise ValueError(f"Unknown conclusion option: {conclusion_id}")
        conclusion["selected_option_id"] = conclusion_id
        _audit(state, "conclusion_selected", conclusion_id=conclusion_id)
        return _save_state(company_id, state)


def request_section_rerun(company_id: str, section_id: str) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        section = _get_section(state, section_id)
        section["status"] = "ready_for_input"
        section["last_rerun_requested_at"] = _now()
        section["last_rerun_status"] = "recorded"
        section["last_rerun_note"] = (
            "Rerun request recorded for the PRD editor foundation. "
            "AI section regeneration is not yet connected."
        )
        _audit(state, "section_rerun_requested", section_id=section_id)
        analytics_store.record_event(
            "section_rerun",
            company_id=company_id,
            section_id=section_id,
            version_id=state.get("version_id"),
        )
        return _save_state(company_id, state)


def patch_appendix_block(company_id: str, block_id: str, patch: dict) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        appendix = _get_section(state, SECTION_APPENDIX)
        for block in _list(appendix.get("blocks")):
            if isinstance(block, dict) and block.get("id") == block_id:
                if patch.get("expanded") is not None:
                    block["expanded"] = bool(patch["expanded"])
                if patch.get("source_class") is not None:
                    block["source_class"] = normalize_source_class(patch["source_class"])
                if patch.get("source_refs") is not None:
                    block["source_refs"] = normalize_source_refs(
                        patch["source_refs"],
                        default_source_class=block.get("source_class"),
                        fallback_title=f"{block.get('title') or 'Appendix'} source",
                    )
                _audit(state, "appendix_block_updated", block_id=block_id, patch=patch)
                return _save_state(company_id, state)
        raise ValueError(f"Unknown appendix block: {block_id}")


def _append_missing(
    missing: list[dict],
    *,
    location: str,
    text: str,
    source: dict,
) -> None:
    terms = _key_figure_terms(text)
    if not terms:
        return
    if _source_covered(source):
        return
    missing.append({
        "location": location,
        "text": text,
        "terms": terms,
        "reason": "Key figure lacks source reference or source class coverage.",
    })


def _projection_card(card: dict) -> dict:
    return {
        "id": card.get("id"),
        "rank": card.get("rank"),
        "title": card.get("title"),
        "category": card.get("category"),
        "severity": card.get("severity"),
        "bullets": copy.deepcopy(_list(card.get("bullets"))),
        "source_refs": copy.deepcopy(_list(card.get("source_refs"))),
        "source_class": normalize_source_class(card.get("source_class")),
        "confidence": card.get("confidence"),
    }


def export_projection(company_id: str, *, record_attempt: bool = False) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        sections = state.get("sections") or {}
        missing: list[dict] = []
        key_figure_count = 0
        covered_key_figure_count = 0

        def check(location: str, text: str, source: dict) -> None:
            nonlocal key_figure_count, covered_key_figure_count
            terms = _key_figure_terms(text)
            if not terms:
                return
            key_figure_count += len(terms)
            if _source_covered(source):
                covered_key_figure_count += len(terms)
                return
            _append_missing(missing, location=location, text=text, source=source)

        executive = sections.get("executive_summary") or {}
        for key in ("body", "recommendation", "round", "top_gate"):
            check(f"Executive Summary / {key}", _clean_text(executive.get(key)), executive)

        projection = {
            "company_id": state.get("company_id"),
            "company_name": state.get("company_name"),
            "version_id": state.get("version_id"),
            "sections": {
                "executive_summary": copy.deepcopy(executive),
                SECTION_INVESTMENT_THESIS: [],
                SECTION_RISKS: [],
                SECTION_CONCLUSION: None,
                SECTION_APPENDIX: copy.deepcopy((sections.get(SECTION_APPENDIX) or {}).get("blocks") or []),
            },
            "source_disclosures": [],
        }

        for section_id in (SECTION_INVESTMENT_THESIS, SECTION_RISKS):
            section = sections.get(section_id) or {}
            cards = [
                card for card in _list(section.get("cards"))
                if isinstance(card, dict) and card.get("included", True)
            ]
            cards.sort(key=lambda card: int(card.get("rank") or 999))
            for card in cards:
                check(f"{section.get('title')} / {card.get('title')}", _clean_text(card.get("title")), card)
                for bullet in _flatten_bullets(_list(card.get("bullets"))):
                    check(
                        f"{section.get('title')} / {card.get('title')} / bullet",
                        _clean_text(bullet.get("text")),
                        bullet,
                    )
                projection["sections"][section_id].append(_projection_card(card))

        conclusion = sections.get(SECTION_CONCLUSION) or {}
        selected = conclusion.get("selected_option_id")
        for option in _list(conclusion.get("options")):
            if not isinstance(option, dict):
                continue
            if option.get("id") == selected:
                check(f"Conclusion / {option.get('label')}", _clean_text(option.get("text")), option)
                projection["sections"][SECTION_CONCLUSION] = copy.deepcopy(option)

        for block in _list((sections.get(SECTION_APPENDIX) or {}).get("blocks")):
            if not isinstance(block, dict):
                continue
            for fact in _list(block.get("facts")):
                check(f"Appendix / {block.get('title')}", _clean_text(fact), block)
            projection["source_disclosures"].append({
                "block_id": block.get("id"),
                "title": block.get("title"),
                "source_class": normalize_source_class(block.get("source_class")),
                "source_refs": copy.deepcopy(_list(block.get("source_refs"))),
                "status": block.get("status"),
            })

        coverage = {
            "key_figure_count": key_figure_count,
            "covered_key_figure_count": covered_key_figure_count,
            "missing_key_figure_count": len(missing),
            "coverage": (
                1.0 if key_figure_count == 0 else covered_key_figure_count / key_figure_count
            ),
        }
        result = {
            "blocked": bool(missing),
            "block_reason": (
                "Export blocked: key figures lack source/source-class coverage."
                if missing
                else ""
            ),
            "missing_sources": missing,
            "source_coverage": coverage,
            "projection": projection,
            "generated_at": _now(),
        }
        if record_attempt:
            _audit(
                state,
                "export_projection_requested",
                blocked=result["blocked"],
                missing_key_figure_count=len(missing),
                coverage=coverage,
            )
            analytics_store.record_event(
                "memo_exported",
                company_id=company_id,
                version_id=state.get("version_id"),
                revision_id=state.get("revision_id"),
                blocked=result["blocked"],
                source_coverage=coverage,
            )
            if result["blocked"]:
                analytics_store.record_event(
                    "memo_key_figure_source_missing",
                    company_id=company_id,
                    version_id=state.get("version_id"),
                    missing_key_figure_count=len(missing),
                )
            _save_state(company_id, state)
        return result


def create_task(company_id: str, payload: dict) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        task = _append_task(
            state,
            action_type=payload.get("action_type") or "discuss",
            title=payload.get("title") or "Review co-pilot context",
            description=payload.get("description") or "",
            context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
            status=payload.get("status") or "proposed",
            created_by=payload.get("created_by") or "co-pilot",
        )
        saved = _save_state(company_id, state)
        return next(row for row in _list(saved.get("memo_tasks")) if row.get("id") == task["id"])


def update_task(company_id: str, task_id: str, patch: dict) -> dict:
    with _LOCK:
        state = get_state(company_id, create=True)
        if state is None:
            raise ValueError(f"Unknown company: {company_id}")
        for task in _list(state.get("memo_tasks")):
            if not isinstance(task, dict) or task.get("id") != task_id:
                continue
            previous_status = task.get("status")
            if patch.get("title") is not None:
                task["title"] = _clean_text(patch.get("title"), limit=240)
            if patch.get("description") is not None:
                task["description"] = _clean_text(patch.get("description"), limit=1000)
            if patch.get("status") is not None:
                status = _clean_text(patch.get("status"), limit=40)
                if status not in {"proposed", "accepted", "rejected", "completed"}:
                    raise ValueError("Invalid task status")
                task["status"] = status
                if status == "completed":
                    task["completed_at"] = _now()
            if isinstance(patch.get("context"), dict):
                task["context"] = {**(task.get("context") or {}), **patch["context"]}
            task["updated_at"] = _now()
            _audit(
                state,
                "memo_task_updated",
                task_id=task_id,
                previous_status=previous_status,
                status=task.get("status"),
            )
            if task.get("status") in {"accepted", "completed"} and previous_status != task.get("status"):
                analytics_store.record_event(
                    "copilot_task_actioned",
                    company_id=company_id,
                    task_id=task_id,
                    action_type=task.get("action_type"),
                    status=task.get("status"),
                )
            saved = _save_state(company_id, state)
            return next(row for row in _list(saved.get("memo_tasks")) if row.get("id") == task_id)
        raise ValueError(f"Unknown memo task: {task_id}")


def history(company_id: str) -> dict:
    state = get_state(company_id, create=True)
    if state is None:
        raise ValueError(f"Unknown company: {company_id}")
    versions = []
    vdir = _versions_dir(company_id)
    if vdir.exists():
        for path in sorted(vdir.glob("*.yaml")):
            data = _read_yaml(path, {})
            if not isinstance(data, dict):
                continue
            versions.append({
                "revision_id": data.get("revision_id"),
                "revision": data.get("revision"),
                "version_id": data.get("version_id"),
                "status": data.get("status"),
                "event": data.get("event"),
                "created_at": data.get("created_at"),
            })
    versions.sort(key=lambda row: int(row.get("revision") or 0), reverse=True)
    return {
        "company_id": company_id,
        "version_id": state.get("version_id"),
        "current_revision_id": state.get("revision_id"),
        "versions": versions,
        "audit_records": list(reversed(_list(state.get("audit_records")))),
        "memo_tasks": _list(state.get("memo_tasks")),
    }


def get_revision(company_id: str, revision_id: str) -> dict:
    data = _read_yaml(_version_snapshot_path(company_id, revision_id), None)
    if not isinstance(data, dict):
        raise ValueError(f"Unknown memo revision: {revision_id}")
    return data


def _flatten_bullets(bullets: list) -> list[dict]:
    out: list[dict] = []
    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        out.append(bullet)
        out.extend(_flatten_bullets(_list(bullet.get("children"))))
    return out
