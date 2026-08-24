"""Unified PRD evidence/document adapter.

This module presents one investor-facing evidence model over the existing
Document Library and Background Documents stores. It deliberately keeps those
stores separate; rows here carry their backend source so callers can preserve
the memo-input boundary from docs/architecture.md.
"""
from __future__ import annotations

import copy
import hashlib
import re
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from . import external_store, files_store, research_store, storage

# Serializes read-modify-write cycles on the unresolved-intake queue file.
_QUEUE_LOCK = threading.RLock()

DOCUMENT_CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": "memos", "label": "Memos"},
    {"id": "company_materials", "label": "Company Materials"},
    {"id": "legal_corporate", "label": "Legal and Corporate"},
    {"id": "financial", "label": "Financial"},
    {"id": "external_reports", "label": "External Reports"},
    {"id": "internal_notes_sources", "label": "Internal Notes and Sources"},
)

SOURCE_CLASSES: tuple[str, ...] = (
    "company material",
    "public filing",
    "third-party market data",
    "BSH primary diligence",
    "internal note",
    "generated memo",
    "unknown/pending",
)

_SOURCE_CLASS_ALIASES = {
    "company": "company material",
    "company materials": "company material",
    "company material": "company material",
    "company-reported": "company material",
    "company reported": "company material",
    "public": "public filing",
    "public filing": "public filing",
    "filing": "public filing",
    "sec filing": "public filing",
    "third party": "third-party market data",
    "third-party": "third-party market data",
    "third-party market data": "third-party market data",
    "market data": "third-party market data",
    "external report": "third-party market data",
    "external research": "third-party market data",
    "bsh": "BSH primary diligence",
    "bsh diligence": "BSH primary diligence",
    "bsh primary diligence": "BSH primary diligence",
    "serena": "BSH primary diligence",
    "internal": "internal note",
    "internal note": "internal note",
    "note": "internal note",
    "generated": "generated memo",
    "generated memo": "generated memo",
    "memo": "generated memo",
    "unknown": "unknown/pending",
    "pending": "unknown/pending",
    "unknown/pending": "unknown/pending",
}

_CATEGORY_ALIASES = {
    "memo": "memos",
    "memos": "memos",
    "generated memo": "memos",
    "company": "company_materials",
    "company material": "company_materials",
    "company materials": "company_materials",
    "deck": "company_materials",
    "presentation": "company_materials",
    "legal": "legal_corporate",
    "legal and corporate": "legal_corporate",
    "legal_corporate": "legal_corporate",
    "corporate": "legal_corporate",
    "filing": "legal_corporate",
    "public filing": "legal_corporate",
    "financial": "financial",
    "finance": "financial",
    "model": "financial",
    "external": "external_reports",
    "external report": "external_reports",
    "external reports": "external_reports",
    "external research": "external_reports",
    "research": "external_reports",
    "market": "external_reports",
    "market report": "external_reports",
    "internal": "internal_notes_sources",
    "internal note": "internal_notes_sources",
    "internal notes": "internal_notes_sources",
    "internal notes and sources": "internal_notes_sources",
    "source": "internal_notes_sources",
    "sources": "internal_notes_sources",
}

_CATEGORY_KEYWORDS = (
    ("legal_corporate", re.compile(r"\b(legal|corporate|sec|edgar|filing|10-k|10-q|s-1|certificate|charter|bylaw|contract|cap table|cap-table)\b", re.I)),
    ("financial", re.compile(r"\b(financial|finance|arr|revenue|valuation|model|forecast|budget|income|cash flow|balance sheet|audit)\b", re.I)),
    ("external_reports", re.compile(r"\b(report|market|pitchbook|cb insights|gartner|forrester|idc|survey|analyst|external|research)\b", re.I)),
    ("internal_notes_sources", re.compile(r"\b(note|notes|diligence|interview|call|meeting|memo|hormuz|internal)\b", re.I)),
    ("company_materials", re.compile(r"\b(deck|presentation|company|product|customer|roadmap|overview|materials?)\b", re.I)),
)

_SOURCE_LABELS = {
    "document_library": "Document Library",
    "background_documents": "Background Documents",
    "generated_report": "Generated Reports",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _category_label(category_id: str) -> str:
    return next(
        (row["label"] for row in DOCUMENT_CATEGORIES if row["id"] == category_id),
        category_id,
    )


def normalize_source_class(value: Any) -> str:
    raw = _clean(value, limit=80).lower()
    if not raw:
        return "unknown/pending"
    if raw in _SOURCE_CLASS_ALIASES:
        return _SOURCE_CLASS_ALIASES[raw]
    raw = raw.replace("_", " ").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return _SOURCE_CLASS_ALIASES.get(raw, "unknown/pending")


def normalize_document_category(
    value: Any,
    *,
    filename: Any = "",
    kind: Any = "",
    source_class: Any = "",
    backend: str = "",
) -> str:
    raw = _clean(value, limit=100).lower()
    if raw:
        raw = raw.replace("-", " ").replace("_", " ")
        if raw in _CATEGORY_ALIASES:
            return _CATEGORY_ALIASES[raw]
    sc = normalize_source_class(source_class)
    if sc == "generated memo":
        return "memos"
    if sc == "public filing":
        return "legal_corporate"
    if sc == "internal note":
        return "internal_notes_sources"
    text = " ".join(
        part for part in (_clean(filename, limit=240), _clean(kind, limit=40), raw) if part
    )
    for category, pattern in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category
    if backend == "background_documents":
        return "external_reports"
    if backend == "generated_report":
        return "memos"
    return "company_materials"


def _doc_status(record: dict) -> str:
    explicit = _clean(record.get("status"), limit=80)
    if explicit:
        return explicit
    summary = record.get("summary")
    quick = record.get("quick_summary")
    if isinstance(summary, dict) and summary.get("error"):
        return "failed"
    if isinstance(quick, dict) and quick.get("error"):
        return "failed"
    if summary or quick:
        return "summarized"
    return "ready"


def _provenance(record: dict, *, backend: str, title: str, filename: str) -> dict:
    payload = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    external_meta = (
        record.get("external_research_metadata")
        if isinstance(record.get("external_research_metadata"), dict)
        else {}
    )
    source_class = normalize_source_class(
        record.get("source_class")
        or payload.get("source_class")
        or external_meta.get("source_class")
    )
    language = (
        payload.get("language")
        or record.get("language")
        or (record.get("summary") or {}).get("language")
        or (record.get("quick_summary") or {}).get("language")
        or "unknown"
    )
    origin = (
        payload.get("origin")
        or payload.get("source")
        or record.get("source_company")
        or record.get("contact_name")
        or _SOURCE_LABELS.get(backend, backend)
    )
    captured_at = (
        payload.get("captured_at")
        or record.get("captured_at")
        or record.get("uploaded_at")
        or record.get("created_at")
    )
    return {
        "title": _clean(payload.get("title") or record.get("title") or title, limit=240),
        "origin": _clean(origin, limit=240),
        "url": _clean(payload.get("url") or record.get("source_url") or record.get("final_url"), limit=600),
        "file": _clean(payload.get("file") or filename or record.get("stored_name"), limit=500),
        "captured_at": _clean(captured_at, limit=80),
        "uploaded_at": _clean(payload.get("uploaded_at") or record.get("uploaded_at"), limit=80),
        "published_at": _clean(
            payload.get("published_at") or record.get("published_at") or record.get("date"),
            limit=80,
        ),
        "language": _clean(language, limit=30) or "unknown",
        "source_class": source_class,
        "confidence": _clean(
            payload.get("confidence")
            or record.get("source_confidence")
            or record.get("assignment_confidence"),
            limit=40,
        ) or "pending",
        "status": _clean(payload.get("status") or record.get("source_status"), limit=80)
        or "pending",
    }


def _source_traces(record: dict) -> list[dict]:
    for candidate in (
        record.get("source_traces"),
        (record.get("summary") or {}).get("source_traces"),
        (record.get("quick_summary") or {}).get("source_traces"),
        (record.get("external_research_metadata") or {}).get("source_traces"),
    ):
        if isinstance(candidate, list):
            return copy.deepcopy(candidate)
    return []


def _source_refs(record: dict, provenance: dict) -> list[dict]:
    refs = record.get("source_refs")
    if isinstance(refs, list) and refs:
        return copy.deepcopy(refs)
    return [
        {
            "title": provenance["title"] or "Source pending",
            "origin": provenance["origin"],
            "url": provenance["url"],
            "file": provenance["file"],
            "captured_at": provenance["captured_at"],
            "published_at": provenance["published_at"],
            "language": provenance["language"],
            "source_class": provenance["source_class"],
            "confidence": provenance["confidence"],
            "status": provenance["status"],
        }
    ]


def _document_row(
    *,
    company_id: str,
    backend: str,
    record: dict,
    record_id: str,
    title: str,
    filename: str,
    kind: str,
    editable: bool,
    report: dict | None = None,
) -> dict:
    provenance = _provenance(record, backend=backend, title=title, filename=filename)
    source_class = normalize_source_class(record.get("source_class") or provenance["source_class"])
    category = normalize_document_category(
        record.get("document_category") or record.get("category") or record.get("prd_category"),
        filename=filename or title,
        kind=kind,
        source_class=source_class,
        backend=backend,
    )
    status = _doc_status(record)
    traces = _source_traces(record)
    row = {
        "id": f"{backend}:{record_id}",
        "company_id": company_id,
        "backend": backend,
        "backend_label": _SOURCE_LABELS.get(backend, backend),
        "record_id": record_id,
        "title": title,
        "filename": filename,
        "kind": kind,
        "type_badge": _type_badge(kind, filename),
        "category": category,
        "category_label": _category_label(category),
        "source_class": source_class,
        "source_class_label": source_class,
        "language": provenance["language"],
        "status": status,
        "captured_at": provenance["captured_at"] or record.get("created_at") or "",
        "uploaded_at": provenance["uploaded_at"],
        "published_at": provenance["published_at"],
        "provenance": provenance,
        "source_refs": _source_refs(record, provenance),
        "source_traces": traces,
        "source_trace_count": len(traces),
        "editable_metadata": editable,
        "use_in_report": backend == "background_documents",
        "use_in_report_locked": _use_in_report_locked(backend, filename, record),
        "summary": record.get("summary"),
        "quick_summary": record.get("quick_summary"),
        "record": copy.deepcopy(record),
    }
    if report is not None:
        row["report"] = copy.deepcopy(report)
        row["download_urls"] = copy.deepcopy(report.get("download_urls") or {})
        row["preview_urls"] = copy.deepcopy(report.get("preview_urls") or {})
    return row


def _type_badge(kind: str, filename: str) -> str:
    raw = _clean(kind or "", limit=40).lower()
    if raw:
        if raw == "text":
            return "TXT"
        if raw == "markdown":
            return "MD"
        return raw.upper()
    suffix = filename.rsplit(".", 1)[-1].upper() if "." in filename else ""
    return suffix or "DOC"


def report_document_row(company_id: str, report: dict) -> dict:
    record = {
        "id": report.get("id"),
        "kind": report.get("kind") or "memo",
        "status": report.get("status"),
        "title": report.get("report_type") or "Generated report",
        "created_at": report.get("created_at"),
        "updated_at": report.get("updated_at"),
        "language": report.get("language") or "en",
        "source_class": "generated memo",
        "document_category": "memos",
        "provenance": {
            "title": report.get("report_type") or "Generated report",
            "origin": "Generated memo",
            "captured_at": report.get("created_at"),
            "language": report.get("language") or "en",
            "source_class": "generated memo",
            "confidence": "high",
            "status": report.get("status") or "pending",
        },
    }
    title = report.get("report_type") or "Generated report"
    return _document_row(
        company_id=company_id,
        backend="generated_report",
        record=record,
        record_id=report.get("id") or "",
        title=title,
        filename=f"{title}.memo",
        kind="memo",
        editable=False,
        report=report,
    )


def list_documents(company_id: str, *, reports: list[dict] | None = None) -> dict:
    rows: list[dict] = []
    for record in files_store.list_files(company_id):
        title = record.get("label") or record.get("filename") or "Document"
        rows.append(
            _document_row(
                company_id=company_id,
                backend="document_library",
                record=record,
                record_id=record.get("id") or "",
                title=title,
                filename=record.get("filename") or "",
                kind=record.get("kind") or "",
                editable=True,
            )
        )
    for record in research_store.list_files(company_id):
        title = (
            record.get("external_title")
            or record.get("label")
            or record.get("filename")
            or "Background document"
        )
        rows.append(
            _document_row(
                company_id=company_id,
                backend="background_documents",
                record=record,
                record_id=record.get("id") or "",
                title=title,
                filename=record.get("filename") or "",
                kind=record.get("kind") or "",
                editable=True,
            )
        )
    for report in reports or []:
        if report.get("company_id") == company_id:
            rows.append(report_document_row(company_id, report))

    rows.sort(key=lambda row: str(row.get("captured_at") or row.get("uploaded_at") or ""), reverse=True)
    groups = []
    for category in DOCUMENT_CATEGORIES:
        category_rows = [row for row in rows if row.get("category") == category["id"]]
        groups.append({**category, "count": len(category_rows), "rows": category_rows})

    return {
        "company_id": company_id,
        "rows": rows,
        "groups": groups,
        "categories": list(DOCUMENT_CATEGORIES),
        "source_classes": list(SOURCE_CLASSES),
        "filters": {
            "languages": sorted({row.get("language") or "unknown" for row in rows}),
            "statuses": sorted({row.get("status") or "pending" for row in rows}),
            "categories": list(DOCUMENT_CATEGORIES),
            "source_classes": list(SOURCE_CLASSES),
        },
        "unresolved_intake_count": len(list_unresolved_intake(company_id=company_id)),
    }


def update_document_metadata(
    company_id: str,
    backend: str,
    record_id: str,
    patch: dict,
) -> dict:
    if backend not in {"document_library", "background_documents"}:
        raise ValueError("Only library/background document metadata is editable")
    normalized: dict[str, Any] = {}
    if patch.get("category") is not None:
        normalized["document_category"] = normalize_document_category(patch.get("category"))
    if patch.get("source_class") is not None:
        normalized["source_class"] = normalize_source_class(patch.get("source_class"))
    if patch.get("status") is not None:
        normalized["source_status"] = _clean(patch.get("status"), limit=80)
    if patch.get("confidence") is not None:
        normalized["source_confidence"] = _clean(patch.get("confidence"), limit=40)
    if isinstance(patch.get("provenance"), dict):
        existing = _lookup_record(company_id, backend, record_id) or {}
        provenance = existing.get("provenance") if isinstance(existing.get("provenance"), dict) else {}
        merged = {**provenance, **patch["provenance"]}
        if "source_class" in normalized:
            merged["source_class"] = normalized["source_class"]
        elif merged.get("source_class") is not None:
            merged["source_class"] = normalize_source_class(merged.get("source_class"))
        normalized["provenance"] = {
            key: _clean(value, limit=600)
            for key, value in merged.items()
            if value not in (None, "")
        }
    updater = files_store.update_record if backend == "document_library" else research_store.update_record
    updated = updater(company_id, record_id, **normalized)
    if updated is None:
        raise ValueError("Document not found")
    return updated


def _lookup_record(company_id: str, backend: str, record_id: str) -> dict | None:
    rows = (
        files_store.list_files(company_id)
        if backend == "document_library"
        else research_store.list_files(company_id)
    )
    for record in rows:
        if record.get("id") == record_id:
            return record
    return None


_METADATA_COPY_KEYS = (
    "label",
    "language",
    "source_class",
    "document_category",
    "provenance",
    "source_status",
    "source_confidence",
)


def _file_ext(filename: str) -> str:
    name = str(filename or "")
    if "." not in name:
        return ""
    return f".{name.rsplit('.', 1)[-1].lower()}"


def _can_store_in_library(filename: str, content_type: str | None = None) -> bool:
    ext = _file_ext(filename)
    if ext in files_store.ALLOWED_EXTENSIONS:
        return True
    return bool(content_type and content_type in files_store.ALLOWED_TYPES)


def _can_store_in_research(filename: str, content_type: str | None = None) -> bool:
    ext = _file_ext(filename)
    if ext in research_store.ALLOWED_KINDS_BY_EXT:
        return True
    return research_store._kind_from(content_type, filename) is not None


def _use_in_report_locked(backend: str, filename: str, record: dict) -> bool:
    content_type = record.get("content_type")
    if backend == "background_documents":
        return not _can_store_in_library(filename, content_type)
    if backend == "document_library":
        return not _can_store_in_research(filename, content_type)
    return True


def _copy_metadata(record: dict) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key in _METADATA_COPY_KEYS:
        value = record.get(key)
        if value not in (None, ""):
            patch[key] = copy.deepcopy(value)
    return patch


def _row_for_record(company_id: str, backend: str, record: dict) -> dict:
    title = (
        record.get("external_title")
        or record.get("label")
        or record.get("filename")
        or ("Background document" if backend == "background_documents" else "Document")
    )
    return _document_row(
        company_id=company_id,
        backend=backend,
        record=record,
        record_id=record.get("id") or "",
        title=title,
        filename=record.get("filename") or "",
        kind=record.get("kind") or "",
        editable=True,
    )


def set_use_in_report(
    company_id: str,
    backend: str,
    record_id: str,
    use: bool,
) -> dict:
    """Move an uploaded file between library and memo-input stores.

    The two folders stay separate on disk (see docs/architecture.md). The
    investor-facing Files list exposes that boundary as a single
    "Use in report" flag.
    """
    if backend not in {"document_library", "background_documents"}:
        raise ValueError("Only uploaded documents can change Use in report")
    current = backend == "background_documents"
    found = (
        files_store.get_file(company_id, record_id)
        if backend == "document_library"
        else research_store.get_file(company_id, record_id)
    )
    if found is None:
        raise ValueError("Document not found")
    record, path = found
    if current == use:
        return _row_for_record(company_id, backend, record)

    filename = record.get("filename") or "upload"
    content_type = record.get("content_type")
    if use and not _can_store_in_research(filename, content_type):
        raise ValueError(
            "This file type cannot be used in a report. Convert it to PDF, PPTX, Word, text, or an image."
        )
    if not use and not _can_store_in_library(filename, content_type):
        raise ValueError(
            "This file type has to stay in the report set. Keep Use in report on, or delete the file."
        )

    data = path.read_bytes()
    metadata = _copy_metadata(record)
    if use:
        created = research_store.upload_file(
            company_id,
            filename=filename,
            content_type=content_type,
            data=data,
            label=record.get("label"),
        )
        if metadata:
            created = research_store.update_record(company_id, created["id"], **metadata) or created
        files_store.delete_file(company_id, record_id)
        return _row_for_record(company_id, "background_documents", created)

    language = record.get("language") if record.get("language") in files_store.SUPPORTED_LANGUAGES else "en"
    created = files_store.upload_file(
        company_id,
        filename=filename,
        content_type=content_type,
        data=data,
        label=record.get("label"),
        language=language,
    )
    if metadata:
        created = files_store.update_record(company_id, created["id"], **metadata) or created
    research_store.delete_file(company_id, record_id)
    return _row_for_record(company_id, "document_library", created)


def assignment_for_intake(kind: str, payload: dict) -> dict:
    source_text = " ".join(
        _clean(payload.get(key), limit=500)
        for key in ("title", "filename", "source_company", "url", "body", "notes")
        if payload.get(key)
    )
    source_text_lower = source_text.lower()
    best_company: dict | None = None
    best_score = 0.0
    best_reason = ""
    for company in storage.list_companies():
        name = _clean(company.get("name"), limit=120)
        aliases = [str(a) for a in _list(company.get("aliases"))]
        candidates = [name, company.get("id"), company.get("ticker"), *aliases]
        for candidate in candidates:
            text = _clean(candidate, limit=120)
            if not text:
                continue
            score = 0.0
            if _clean(payload.get("source_company"), limit=120).lower() == text.lower():
                score = 0.96
                reason = f"source company matched {name}"
            elif len(text) >= 4 and text.lower() in source_text_lower:
                score = 0.88 if text == name else 0.84
                reason = f"intake text mentioned {text}"
            elif text.isupper() and re.search(rf"\b{re.escape(text)}\b", source_text):
                score = 0.82
                reason = f"ticker matched {text}"
            else:
                continue
            if score > best_score:
                best_company = company
                best_score = score
                best_reason = reason

    source_class = source_class_for_intake(kind, payload)
    category = normalize_document_category(
        payload.get("category"),
        filename=payload.get("filename") or payload.get("title") or "",
        kind=kind,
        source_class=source_class,
        backend="background_documents" if kind == "external_research" else "",
    )
    status = "assigned" if best_company and best_score >= 0.82 else "unresolved"
    return {
        "status": status,
        "company_id": best_company.get("id") if best_company else None,
        "company_name": best_company.get("name") if best_company else None,
        "company_confidence": round(best_score, 2),
        "company_reason": best_reason or "No high-confidence company match.",
        "document_category": category,
        "category_label": _category_label(category),
        "category_confidence": 0.9 if category else 0.0,
        "source_class": source_class,
        "review_reason": "" if status == "assigned" else "Needs manual company/category assignment.",
        "assigned_at": _now() if status == "assigned" else None,
    }


def source_class_for_intake(kind: str, payload: dict) -> str:
    url = _clean(payload.get("url"), limit=600).lower()
    title = _clean(payload.get("title") or payload.get("filename"), limit=240).lower()
    if kind == "hormuz_research" or kind == "internal_note":
        return "internal note"
    if "sec.gov" in url or "edgar" in url or re.search(r"\b(10-k|10-q|s-1)\b", title):
        return "public filing"
    if payload.get("source_company"):
        return "third-party market data"
    if kind in {"external_research", "news"}:
        return "third-party market data"
    return "unknown/pending"


def normalized_url(value: str) -> str:
    url = _clean(value, limit=1000)
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def dedupe_key(kind: str, payload: dict, *, content_hash: str | None = None) -> str:
    if kind == "news":
        return f"news:url:{hashlib.sha256(normalized_url(payload.get('url') or '').encode('utf-8')).hexdigest()}"
    if content_hash:
        return f"{kind}:sha256:{content_hash}"
    body = "\n".join(
        _clean(payload.get(key), limit=2000)
        for key in ("title", "body", "filename", "notes")
        if payload.get(key)
    )
    return f"{kind}:text:{hashlib.sha256(body.encode('utf-8')).hexdigest()}"


def find_duplicate_intake(kind: str, key: str, *, url: str | None = None) -> dict | None:
    store_kind = _external_kind(kind)
    normalized = normalized_url(url or "")
    for item in external_store.list_items(store_kind):
        if item.get("dedupe_key") == key:
            return item
        if store_kind == "news" and normalized:
            existing = normalized_url(item.get("source_url") or item.get("final_url") or "")
            if existing and existing == normalized:
                return item
    return None


def annotate_intake_record(
    *,
    kind: str,
    item_id: str,
    payload: dict,
    content_hash: str | None = None,
) -> dict:
    key = dedupe_key(kind, payload, content_hash=content_hash)
    assignment = assignment_for_intake(kind, payload)
    annotation = {
        "dedupe_key": key,
        "intake_assignment": assignment,
        "document_category": assignment["document_category"],
        "source_class": assignment["source_class"],
    }
    if assignment["status"] == "unresolved":
        add_unresolved_intake(kind=kind, item_id=item_id, payload=payload, assignment=assignment)
    return annotation


def _external_kind(kind: str) -> str:
    if kind in {"news", "external_research", "hormuz_research"}:
        return kind
    if kind == "internal_note":
        return "hormuz_research"
    raise ValueError(f"Unsupported intake kind: {kind}")


def _queue_path() -> Any:
    return storage.DATA_DIR / "intake" / "unresolved.yaml"


def _read_queue() -> list[dict]:
    path = _queue_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
    except Exception as exc:  # noqa: BLE001
        # Quarantine and fail loud: silently reading a corrupt queue as []
        # meant the next add wiped every pending intake row.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantined = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            path.replace(quarantined)
        except OSError:
            raise RuntimeError(f"Unreadable intake queue {path}: {exc}") from exc
        raise RuntimeError(
            f"Corrupt intake queue quarantined to {quarantined.name}: {exc}"
        ) from exc
    return data if isinstance(data, list) else []


def _write_queue(rows: list[dict]) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(rows, f, sort_keys=False, allow_unicode=True)
    tmp.replace(path)


def add_unresolved_intake(
    *,
    kind: str,
    item_id: str,
    payload: dict,
    assignment: dict,
) -> dict:
    key = f"{kind}:{item_id}"
    row = {
        "id": key,
        "kind": kind,
        "item_id": item_id,
        "title": _clean(payload.get("title") or payload.get("filename") or payload.get("url"), limit=240),
        "created_at": _now(),
        "payload": {
            k: _clean(v, limit=600)
            for k, v in payload.items()
            if isinstance(v, (str, int, float)) and v not in ("", None)
        },
        "assignment": assignment,
        "status": "unresolved",
    }
    # The queue lives in one file; the lock makes the read-modify-write
    # atomic against concurrent intake submissions.
    with _QUEUE_LOCK:
        rows = [existing for existing in _read_queue() if existing.get("id") != key]
        rows.append(row)
        rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        _write_queue(rows)
    return row


def list_unresolved_intake(*, company_id: str | None = None) -> list[dict]:
    rows = [row for row in _read_queue() if row.get("status") == "unresolved"]
    if company_id:
        rows = [
            row
            for row in rows
            if (row.get("assignment") or {}).get("company_id") in (None, company_id)
        ]
    return rows


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
