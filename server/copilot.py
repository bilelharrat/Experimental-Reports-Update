"""Co-Pilot adapter — scoped context assembly and quick-inspect sessions.

Quick Inspect reuses the company console engine but keeps one lightweight session per
company (background research files only) and prepends structured workspace context to
each ask so the drawer answers about *what the analyst is looking at*.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from . import (
    console_session,
    console_store,
    evidence_matrix,
    memo_editor_store,
    memo_prep,
    quote_workspace,
    research_store,
    storage,
    tracking_dashboard,
)

COPILOT_SESSION_KIND = "copilot_quick"
COPILOT_SESSION_TITLE = "Co-Pilot Inspector"
COPILOT_IOS_SESSION_KIND = "copilot_quick_ios"
COPILOT_IOS_SESSION_TITLE = "Ask"
COPILOT_DEEP_SESSION_KIND = "copilot_deep"
COPILOT_DEEP_SESSION_TITLE = "Co-Pilot Console"
INSPECTOR_SKILL = Path(__file__).parent / "skills" / "bsh_copilot_inspector.md"
IOS_ASK_SKILL = Path(__file__).parent / "skills" / "bsh_copilot_ask_ios.md"
_CONTEXT_CACHE: dict[str, tuple[float, dict]] = {}
_CONTEXT_CACHE_TTL_SEC = 45

_STRUCTURED_BLOCK = re.compile(
    r"```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
_STRUCTURED_KEYS = (
    "research_task",
    "suggested_edit",
    "next_route",
    "contradiction",
    # Work Warren offers to start. The analyst confirms it in the UI; the
    # server never acts on this block by itself.
    "run_work",
)


def _clean(value: Any, *, limit: int = 800) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _latest_report(company_id: str) -> dict | None:
    for report in storage.list_reports():
        if str(report.get("company_id")) == str(company_id):
            return report
    return None


def _memo_run_dir(report: dict) -> Path | None:
    run_dir = report.get("run_dir")
    if not run_dir:
        return None
    return (memo_prep.DATA_DIR.parent / str(run_dir)).resolve()


def _memo_package_summary(company_id: str) -> dict[str, Any] | None:
    report = _latest_report(company_id)
    if not report:
        return None
    summary: dict[str, Any] = {
        "report_id": report.get("id"),
        "status": report.get("status"),
        "quality_warnings": list((report.get("quality_warnings") or [])[:8]),
        "failure_detail": report.get("failure_detail"),
        "pins": [],
        "risks": [],
    }
    run_dir = _memo_run_dir(report)
    if run_dir is None:
        return summary
    pkg_path = run_dir / "logs" / "memo_package.json"
    if not pkg_path.exists():
        return summary
    try:
        package = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return summary
    for section in (package.get("sections") or [])[:12]:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or section.get("title") or "").lower()
        items = section.get("bullets") or section.get("items") or []
        if "risk" in section_id:
            for item in items[:6]:
                text = _clean(item.get("text") if isinstance(item, dict) else item, limit=200)
                if text:
                    summary["risks"].append(text)
        for pin in (section.get("pins") or section.get("key_metrics") or [])[:4]:
            if isinstance(pin, dict):
                label = _clean(pin.get("label") or pin.get("name") or pin.get("metric"), limit=120)
                if label:
                    summary["pins"].append(label)
    return summary


def _evidence_contradictions(company_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    matrix = evidence_matrix.build_company_evidence_matrix(company_id)
    rows: list[dict[str, Any]] = []
    for row in matrix.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "contradicted":
            continue
        rows.append(
            {
                "claim": _clean(row.get("claim"), limit=220),
                "supporting": len(row.get("supporting_evidence") or []),
                "contradicting": len(row.get("contradicting_evidence") or []),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _indexed_files(company_id: str) -> list[dict[str, str]]:
    return [
        {
            "id": str(entry.get("id") or ""),
            "filename": str(entry.get("filename") or ""),
            "kind": str(entry.get("kind") or "research"),
        }
        for entry in research_store.list_files(company_id)
        if entry.get("id")
    ]


def _cache_key(company_id: str, client: dict[str, Any]) -> str:
    payload = json.dumps(client, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{company_id}:{digest}"


def needs_hydration(prompt: str, client: dict[str, Any]) -> bool:
    # iPhone Ask should feel instant — skip the hydrate pass unless the
    # analyst explicitly scoped documents.
    if _is_ios_surface(client) and not client.get("document_ids"):
        return False
    lower = str(prompt or "").lower()
    if client.get("document_ids"):
        return True
    workspace_only = [
        "diagnose",
        "why flagged",
        "fastest",
        "quality warning",
        "what broke",
        "next step",
        "evidence gap",
        "ic update",
    ]
    source_terms = [
        "read",
        "deck",
        "filing",
        "10-k",
        "source",
        "cite",
        "slide",
        "page",
        "document",
    ]
    if any(term in lower for term in workspace_only) and not any(
        term in lower for term in source_terms
    ):
        return False
    if any(term in lower for term in source_terms):
        return True
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    if selection.get("bullet_text") and "contradict" in lower:
        return True
    return False


def _is_ios_surface(client: dict[str, Any] | None) -> bool:
    surface = str((client or {}).get("surface") or "")
    return surface.startswith("ios_")


_MARKET_SURFACES = frozenset({"ios_market", "market", "quote", "radar"})
_OPTIONS_PROMPT_HINT = re.compile(
    r"\b(option|options|premium|premiums|call|calls|put|puts|strike|"
    r"iv|implied\s*vol(?:atility)?|open\s*interest|\boi\b)\b",
    re.IGNORECASE,
)


def _is_market_surface(client: dict[str, Any] | None) -> bool:
    surface = str((client or {}).get("surface") or "")
    return surface in _MARKET_SURFACES or surface.endswith("_market")


def _wants_options_context(prompt: str, client: dict[str, Any] | None) -> bool:
    if _OPTIONS_PROMPT_HINT.search(prompt or ""):
        return True
    # Market/quote Ask: include a snapshot when chain data is already warm
    # (quote detail just loaded workspace). Avoid a cold Nasdaq round-trip
    # for unrelated "why is this moving?" questions.
    return _is_market_surface(client)


def _options_context_block(company_id: str, prompt: str, client: dict[str, Any]) -> str:
    if not _wants_options_context(prompt, client):
        return ""
    company = storage.get_company(company_id) or {}
    ticker = str(company.get("ticker") or "").strip()
    if not ticker:
        return ""
    keywords = bool(_OPTIONS_PROMPT_HINT.search(prompt or ""))
    try:
        snap = quote_workspace.compact_options_snapshot(
            ticker,
            cache_only=not keywords,
        )
    except Exception:
        return ""
    return quote_workspace.format_options_snapshot_for_prompt(snap)


_IOS_STYLE = (
    "## Mobile Ask style (required)\n"
    "iPhone sheet — tight and human. Lead with one sentence, then short bullets.\n"
    "No JSON/code fences. Answer from context first; tools only for live "
    "facts/filings (max 1–2 rounds). Under ~120 words unless asked for depth.\n"
)


def _prepare_runtime_prompt(company_id: str, prompt: str, client_context: dict[str, Any]) -> str:
    options_block = _options_context_block(company_id, prompt, client_context)
    if _is_ios_surface(client_context):
        company = storage.get_company(company_id) or {}
        name = company.get("name") or company_id
        ticker = company.get("ticker") or ""
        label = f"{name} ({ticker})" if ticker else str(name)
        parts = [
            _IOS_STYLE,
            f"## Company\n{label}",
        ]
        if options_block:
            parts.append(options_block)
        parts.append(f"## Analyst question\n\n{prompt.strip()}")
        return "\n\n".join(parts)
    packet = assemble_context(company_id, client_context).get("packet") or {}
    preamble = build_context_preamble(packet)
    if options_block:
        return f"{preamble}\n\n{options_block}\n\n---\n\n## Analyst question\n\n{prompt.strip()}"
    return f"{preamble}\n\n---\n\n## Analyst question\n\n{prompt.strip()}"


def scoped_research_file_ids(client: dict[str, Any]) -> list[str] | None:
    doc_ids = [str(value) for value in (client.get("document_ids") or []) if value]
    if doc_ids:
        return doc_ids
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    refs = selection.get("source_refs") or []
    ids = [
        str(ref.get("file_id"))
        for ref in refs
        if isinstance(ref, dict) and ref.get("file_id")
    ]
    return ids or None


def proactive_strip(
    row: dict | None,
    client: dict[str, Any],
    *,
    report_summary: dict | None = None,
    contradictions: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    attention = client.get("attention") if isinstance(client.get("attention"), dict) else {}
    kind = str(attention.get("kind") or "")
    memo_status = ""
    if row:
        memo_status = str((row.get("memo") or {}).get("latest_status") or "")
    if kind == "memo_failed" or memo_status.startswith("failed"):
        messages.append(
            {
                "kind": "alert",
                "action_id": "diagnose_memo",
                "label_key": "copilot.proactive_memo_failed",
            }
        )
    if kind == "memo_warnings" or memo_status == "complete_with_warnings":
        messages.append(
            {
                "kind": "warning",
                "action_id": "review_warnings",
                "label_key": "copilot.proactive_memo_warnings",
            }
        )
    contradicted = len(contradictions or [])
    if kind == "evidence_contradicted" or contradicted:
        messages.append(
            {
                "kind": "warning",
                "action_id": "resolve_contradictions",
                "label_key": "copilot.proactive_contradictions",
            }
        )
    job = client.get("job") if isinstance(client.get("job"), dict) else {}
    if client.get("surface") == "jobs" and str(job.get("status") or "").startswith("fail"):
        messages.append(
            {
                "kind": "alert",
                "action_id": "diagnose_job",
                "label_key": "copilot.proactive_job_failed",
            }
        )
    if report_summary and report_summary.get("quality_warnings"):
        if not any(msg["action_id"] == "review_warnings" for msg in messages):
            messages.append(
                {
                    "kind": "warning",
                    "action_id": "review_warnings",
                    "label_key": "copilot.proactive_memo_warnings",
                }
            )
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for message in messages:
        action_id = message.get("action_id") or ""
        if action_id in seen:
            continue
        seen.add(action_id)
        unique.append(message)
        if len(unique) >= 3:
            break
    return unique


def auto_prompt(
    client: dict[str, Any],
    row: dict | None,
    *,
    report_summary: dict | None = None,
) -> str | None:
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    if selection.get("target_kind"):
        return None
    attention = client.get("attention") if isinstance(client.get("attention"), dict) else {}
    if attention.get("kind") == "memo_failed":
        failure = (
            attention.get("detail")
            or (report_summary or {}).get("failure_detail")
            or ((row or {}).get("memo") or {}).get("latest_failure_detail")
            or ""
        )
        return (
            "Diagnose the failed memo run. Explain the most likely root cause and "
            f"the fastest recovery path. Failure: {failure}".strip()
        )
    job = client.get("job") if isinstance(client.get("job"), dict) else {}
    if client.get("surface") == "jobs" and str(job.get("status") or "").startswith("fail"):
        label = _clean(job.get("title") or job.get("kind") or "job", limit=120)
        detail = _clean(job.get("detail") or job.get("error"), limit=240)
        return (
            f"Diagnose this failed job ({label}). What broke and what should I do next? "
            f"{detail}".strip()
        )
    if attention.get("kind") == "evidence_contradicted":
        count = attention.get("count") or 0
        return (
            f"Explain the {count} contradicted claims and what evidence would resolve each one."
        )
    return None


def parse_structured_outputs(text: str) -> dict[str, Any | None]:
    outputs: dict[str, Any | None] = {key: None for key in _STRUCTURED_KEYS}
    for match in _STRUCTURED_BLOCK.finditer(text or ""):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for key in _STRUCTURED_KEYS:
            value = payload.get(key)
            if isinstance(value, dict) and value:
                outputs[key] = value
    return outputs


def strip_structured_blocks(text: str) -> str:
    return _STRUCTURED_BLOCK.sub("", text or "").strip()


def _provenance_label(selection: dict[str, Any]) -> str:
    for key in (
        "bullet_text",
        "claim",
        "metric_label",
        "warning",
        "signal",
        "excerpt",
        "label",
    ):
        value = _clean(selection.get(key), limit=160)
        if value:
            return value
    return "Selected item"


def _resolve_memo_bullet(company_id: str, selection: dict[str, Any]) -> dict | None:
    section_id = selection.get("section_id")
    card_id = selection.get("card_id")
    bullet_id = selection.get("bullet_id")
    if not section_id or not card_id or not bullet_id:
        return None
    try:
        state = memo_editor_store.get_state(company_id, create=False)
    except ValueError:
        return None
    if not state:
        return None
    for section in state.get("sections") or []:
        if not isinstance(section, dict) or section.get("id") != section_id:
            continue
        for card in section.get("cards") or []:
            if not isinstance(card, dict) or card.get("id") != card_id:
                continue
            for bullet in card.get("bullets") or []:
                if isinstance(bullet, dict) and bullet.get("id") == bullet_id:
                    return bullet
    return None


def _normalize_source_rows(rows: list[Any], *, limit: int = 6) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "file_id": row.get("file_id"),
                "filename": row.get("filename") or row.get("source_title"),
                "locator": row.get("locator"),
                "excerpt": _clean(row.get("excerpt"), limit=220),
                "source_class": row.get("source_class") or row.get("source_type"),
                "confidence": row.get("confidence"),
            }
        )
    return normalized


def build_provenance(company_id: str, client: dict[str, Any]) -> dict[str, Any] | None:
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    kind = str(selection.get("target_kind") or "")
    if not kind:
        return None

    result: dict[str, Any] = {
        "target_kind": kind,
        "label": _provenance_label(selection),
        "sources": [],
        "gaps": [],
        "contradictions": [],
        "metadata": {},
    }

    if kind == "memo_bullet":
        bullet = _resolve_memo_bullet(company_id, selection)
        if bullet:
            result["sources"] = _normalize_source_rows(bullet.get("source_refs") or [])
            result["metadata"] = {
                "text": _clean(bullet.get("text"), limit=400),
                "source_class": bullet.get("source_class"),
                "section_id": selection.get("section_id"),
                "card_id": selection.get("card_id"),
                "bullet_id": selection.get("bullet_id"),
            }
        elif selection.get("bullet_text"):
            result["metadata"]["text"] = _clean(selection.get("bullet_text"), limit=400)

    elif kind == "metric":
        result["sources"] = _normalize_source_rows(selection.get("source_refs") or [])
        result["metadata"] = {
            "metric_label": selection.get("metric_label"),
            "metric_value": selection.get("metric_value"),
            "as_of": selection.get("as_of"),
            "source_class": selection.get("source_class"),
        }

    elif kind == "evidence_claim":
        claim_text = _clean(selection.get("claim"), limit=600)
        matrix = evidence_matrix.build_company_evidence_matrix(company_id)
        for row in matrix.get("claims") or []:
            if not isinstance(row, dict):
                continue
            if claim_text and row.get("claim") != claim_text:
                continue
            result["label"] = _clean(row.get("claim"), limit=160)
            result["sources"] = _normalize_source_rows(row.get("supporting_evidence") or [])
            result["contradictions"] = _normalize_source_rows(
                row.get("contradicting_evidence") or [],
                limit=4,
            )
            result["gaps"] = [
                _clean(item, limit=200)
                for item in (row.get("missing_evidence") or [])[:4]
                if item
            ]
            result["metadata"] = {
                "status": row.get("status"),
                "confidence": row.get("confidence"),
                "coverage": row.get("source_coverage") or {},
            }
            break

    elif kind == "memo_warning":
        result["metadata"] = {
            "warning": _clean(selection.get("warning"), limit=400),
            "report_id": selection.get("report_id"),
        }
        result["gaps"] = [_clean(selection.get("warning"), limit=200)]

    elif kind == "gate_finding":
        result["metadata"] = {
            "code": selection.get("code"),
            "location": selection.get("location"),
            "snippet": _clean(selection.get("snippet"), limit=240),
            "gate_label": selection.get("gate_label"),
        }
        if selection.get("snippet"):
            result["gaps"] = [_clean(selection.get("snippet"), limit=200)]

    elif kind == "document_summary":
        file_id = selection.get("file_id")
        result["metadata"] = {
            "filename": selection.get("filename"),
            "excerpt": _clean(selection.get("excerpt"), limit=400),
            "file_id": file_id,
        }
        if file_id:
            result["sources"] = [
                {
                    "file_id": file_id,
                    "filename": selection.get("filename"),
                    "excerpt": _clean(selection.get("excerpt"), limit=220),
                }
            ]

    elif kind == "report_signal":
        result["metadata"] = {
            "signal": _clean(selection.get("signal"), limit=200),
            "implication": _clean(selection.get("implication"), limit=240),
            "category": selection.get("category"),
            "source_class": selection.get("source_class"),
        }

    document_ids = [
        str(row.get("file_id"))
        for row in result.get("sources") or []
        if isinstance(row, dict) and row.get("file_id")
    ]
    if document_ids:
        result["document_ids"] = document_ids
    return result


def _company_row(company_id: str) -> dict | None:
    rollup = tracking_dashboard.build_rollup([company_id])
    for row in rollup.get("companies") or []:
        if str(row.get("id")) == str(company_id):
            return row
    return None


def _memo_excerpt(company_id: str) -> dict[str, Any] | None:
    try:
        state = memo_editor_store.get_state(company_id, create=False)
    except ValueError:
        return None
    if not state:
        return None
    sections = [
        row for row in (state.get("sections") or []) if isinstance(row, dict)
    ]
    cards = []
    for section in sections[:6]:
        title = _clean(section.get("title") or section.get("id"), limit=120)
        for card in (section.get("cards") or [])[:3]:
            if not isinstance(card, dict):
                continue
            bullets = [
                _clean(b.get("text"), limit=160)
                for b in (card.get("bullets") or [])
                if isinstance(b, dict) and b.get("text")
            ][:3]
            cards.append(
                {
                    "section": title,
                    "title": _clean(card.get("title"), limit=160),
                    "bullets": bullets,
                }
            )
            if len(cards) >= 8:
                break
        if len(cards) >= 8:
            break
    return {
        "version_id": state.get("version_id"),
        "conclusion_id": state.get("selected_conclusion_id"),
        "open_tasks": len(
            [
                t
                for t in (state.get("memo_tasks") or [])
                if isinstance(t, dict) and t.get("status") in {"proposed", "accepted"}
            ]
        ),
        "cards": cards,
    }


def _default_actions() -> list[dict[str, str]]:
    return [
        {
            "id": "evidence_gaps",
            "label_key": "copilot.action_evidence_gaps",
            "prompt_key": "copilot.prompt_evidence_gaps",
        },
        {
            "id": "stress_thesis",
            "label_key": "copilot.action_stress_thesis",
            "prompt_key": "copilot.prompt_stress_thesis",
        },
        {
            "id": "draft_update",
            "label_key": "copilot.action_draft_update",
            "prompt_key": "copilot.prompt_draft_update",
        },
    ]


def situational_actions(
    row: dict | None,
    client: dict[str, Any],
    *,
    editor_excerpt: dict | None = None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    attention = client.get("attention") if isinstance(client.get("attention"), dict) else {}

    if selection.get("bullet_text") or selection.get("card_title"):
        actions.append(
            {
                "id": "discuss_selection",
                "label_key": "copilot.action_discuss_selection",
                "prompt_key": "copilot.prompt_discuss_selection",
            }
        )
        actions.append(
            {
                "id": "find_contradictions",
                "label_key": "copilot.action_find_contradictions",
                "prompt_key": "copilot.prompt_find_contradictions",
            }
        )

    kind = str(attention.get("kind") or "")
    if kind == "memo_failed":
        actions.append(
            {
                "id": "diagnose_memo",
                "label_key": "copilot.action_diagnose_memo",
                "prompt_key": "copilot.prompt_diagnose_memo",
            }
        )
    elif kind == "memo_warnings":
        actions.append(
            {
                "id": "review_warnings",
                "label_key": "copilot.action_review_warnings",
                "prompt_key": "copilot.prompt_review_warnings",
            }
        )
    elif kind == "evidence_contradicted":
        actions.append(
            {
                "id": "resolve_contradictions",
                "label_key": "copilot.action_resolve_contradictions",
                "prompt_key": "copilot.prompt_resolve_contradictions",
            }
        )

    if row:
        memo = row.get("memo") or {}
        status = str(memo.get("latest_status") or "")
        if status.startswith("failed") and not any(a["id"] == "diagnose_memo" for a in actions):
            actions.append(
                {
                    "id": "diagnose_memo",
                    "label_key": "copilot.action_diagnose_memo",
                    "prompt_key": "copilot.prompt_diagnose_memo",
                }
            )
        if status == "complete_with_warnings" and not any(
            a["id"] == "review_warnings" for a in actions
        ):
            actions.append(
                {
                    "id": "review_warnings",
                    "label_key": "copilot.action_review_warnings",
                    "prompt_key": "copilot.prompt_review_warnings",
                }
            )
        contradicted = int((row.get("evidence") or {}).get("contradicted") or 0)
        if contradicted and not any(a["id"] == "resolve_contradictions" for a in actions):
            actions.append(
                {
                    "id": "resolve_contradictions",
                    "label_key": "copilot.action_resolve_contradictions",
                    "prompt_key": "copilot.prompt_resolve_contradictions",
                }
            )

    if client.get("surface") == "jobs" and client.get("job"):
        actions.insert(
            0,
            {
                "id": "diagnose_job",
                "label_key": "copilot.action_diagnose_job",
                "prompt_key": "copilot.prompt_diagnose_job",
            },
        )

    target_kind = str(selection.get("target_kind") or "")
    if target_kind:
        actions.insert(
            0,
            {
                "id": "trace_sources",
                "label_key": "copilot.action_trace_sources",
                "prompt_key": "copilot.prompt_trace_sources",
            },
        )

    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for action in actions + _default_actions():
        if action["id"] in seen:
            continue
        seen.add(action["id"])
        merged.append(action)
        if len(merged) >= 6:
            break
    return merged


def build_context_packet(
    company: dict,
    row: dict | None,
    client: dict[str, Any],
    *,
    editor_excerpt: dict | None = None,
    report_summary: dict | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    files: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    attention = client.get("attention") if isinstance(client.get("attention"), dict) else {}
    job = client.get("job") if isinstance(client.get("job"), dict) else {}
    workspace: dict[str, Any] = {}
    if row:
        workspace = {
            "bucket": row.get("bucket"),
            "memo_status": (row.get("memo") or {}).get("latest_status"),
            "memo_failure": (row.get("memo") or {}).get("latest_failure_detail"),
            "warning_count": (row.get("memo") or {}).get("warning_count"),
            "evidence_contradicted": (row.get("evidence") or {}).get("contradicted"),
            "open_risks": (row.get("risks") or {}).get("open"),
            "next_action": row.get("next_action"),
        }
    return {
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "ticker": company.get("ticker"),
            "company_type": company.get("company_type"),
        },
        "surface": client.get("surface"),
        "tab": client.get("tab"),
        "selection": selection,
        "attention": attention,
        "job": job,
        "workspace": workspace,
        "memo_excerpt": editor_excerpt,
        "memo_package": report_summary,
        "evidence_contradictions": contradictions or [],
        "files": files or [],
        "document_ids": list(client.get("document_ids") or []),
    }


def build_context_label(
    company: dict,
    client: dict[str, Any],
    *,
    editor_excerpt: dict | None = None,
) -> str:
    parts = [_clean(company.get("name"), limit=120)]
    selection = client.get("selection") if isinstance(client.get("selection"), dict) else {}
    if selection.get("section_title"):
        parts.append(_clean(selection["section_title"], limit=80))
    elif selection.get("card_title"):
        parts.append(_clean(selection["card_title"], limit=80))
    elif selection.get("target_kind"):
        parts.append(_provenance_label(selection))
    elif client.get("tab"):
        parts.append(_clean(client.get("tab"), limit=40))
    return " · ".join(parts)


def build_context_preamble(packet: dict[str, Any]) -> str:
    return (
        "## Workspace context (authoritative for this turn)\n\n"
        f"```json\n{json.dumps(packet, ensure_ascii=False, indent=2)}\n```\n\n"
        "Use this context to scope your answer. Read staged files when you need "
        "primary-source support."
    )


def assemble_context(company_id: str, client: dict[str, Any] | None = None) -> dict[str, Any]:
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError("company_not_found")
    client = client if isinstance(client, dict) else {}
    cache_key = _cache_key(company_id, client)
    cached = _CONTEXT_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CONTEXT_CACHE_TTL_SEC:
        return cached[1]

    row = _company_row(company_id)
    editor_excerpt = _memo_excerpt(company_id)
    report_summary = _memo_package_summary(company_id)
    contradictions = _evidence_contradictions(company_id)
    files = _indexed_files(company_id)
    packet = build_context_packet(
        company,
        row,
        client,
        editor_excerpt=editor_excerpt,
        report_summary=report_summary,
        contradictions=contradictions,
        files=files,
    )
    session = find_quick_session(company_id)
    provenance = build_provenance(company_id, client)
    result = {
        "company_id": company_id,
        "label": build_context_label(company, client, editor_excerpt=editor_excerpt),
        "surface": client.get("surface"),
        "tab": client.get("tab"),
        "selection": packet.get("selection") or {},
        "actions": situational_actions(row, client, editor_excerpt=editor_excerpt),
        "workspace": packet.get("workspace") or {},
        "packet": packet,
        "files": files,
        "provenance": provenance,
        "proactive": proactive_strip(
            row,
            client,
            report_summary=report_summary,
            contradictions=contradictions,
        ),
        "auto_prompt": auto_prompt(client, row, report_summary=report_summary),
        "session": _serialize_quick_session(session) if session else None,
        "deep_session": _serialize_quick_session(find_deep_session(company_id))
        if find_deep_session(company_id)
        else None,
    }
    _CONTEXT_CACHE[cache_key] = (now, result)
    return result


def find_quick_session(company_id: str, *, session_kind: str = COPILOT_SESSION_KIND) -> dict | None:
    for meta in console_store.list_sessions(company_id):
        if (
            meta.get("status") == "active"
            and meta.get("session_kind") == session_kind
        ):
            return meta
    return None


def _serialize_quick_session(meta: dict) -> dict:
    return {
        "id": meta.get("id"),
        "hydration_status": meta.get("hydration_status"),
        "title": meta.get("title"),
    }


def ensure_quick_session(
    company_id: str,
    *,
    output_language: str = "en",
    hydrate: bool = False,
    research_file_ids: list[str] | None = None,
    include_background_docs: bool = True,
    session_kind: str = COPILOT_SESSION_KIND,
    title: str = COPILOT_SESSION_TITLE,
) -> dict:
    existing = find_quick_session(company_id, session_kind=session_kind)
    if existing is not None:
        return existing
    skill = (
        IOS_ASK_SKILL
        if session_kind == COPILOT_IOS_SESSION_KIND and IOS_ASK_SKILL.exists()
        else INSPECTOR_SKILL
    )
    meta = console_session.create_session(
        company_id=company_id,
        include_background_docs=include_background_docs,
        include_library_docs=False,
        output_language=output_language,
        title=title,
        session_kind=session_kind,
        skill_path=skill,
        research_file_ids=research_file_ids,
        skip_hydrate=not hydrate,
    )
    return meta


# ---- Threads ------------------------------------------------------------
# A Warren thread is a console session of a copilot kind. There is one
# active thread per company per mode, and it belongs to the company, not
# to whoever opened it: everyone on the desk reads and adds to the same
# one. Starting a new thread archives the old one, which is how the
# history gets written — nothing is hidden or deleted.

_THREAD_KINDS = {
    "quick": (COPILOT_SESSION_KIND, COPILOT_IOS_SESSION_KIND),
    "deep": (COPILOT_DEEP_SESSION_KIND,),
}


def list_threads(company_id: str, *, mode: str = "quick") -> list[dict]:
    """Every Warren thread for this company, newest first."""
    kinds = _THREAD_KINDS.get(mode, _THREAD_KINDS["quick"])
    out: list[dict] = []
    for meta in console_store.list_sessions(company_id):
        if meta.get("session_kind") not in kinds:
            continue
        active = meta.get("status") == "active"
        turns = console_store.read_turns(company_id, meta["id"])
        questions = [t for t in turns if t.get("role") == "user"]
        # An archived thread nobody asked anything in is not history.
        if not questions and not active:
            continue
        askers: list[str] = []
        for turn in questions:
            author = turn.get("author") or {}
            name = str(author.get("name") or author.get("email") or "").strip()
            if name and name not in askers:
                askers.append(name)
        last = questions[-1] if questions else None
        out.append({
            "id": meta.get("id"),
            "active": active,
            "started_at": meta.get("created_at"),
            "last_at": (last or {}).get("ts") or meta.get("created_at"),
            "question_count": len(questions),
            "opening_question": str(questions[0].get("text") or "")[:240] if questions else "",
            "latest_question": str((last or {}).get("text") or "")[:240],
            "askers": askers,
        })
    return out


def start_new_thread(
    company_id: str, *, output_language: str = "en", mode: str = "quick"
) -> dict:
    """Archive the thread in front of everyone and open a fresh one.

    Archived here rather than through ``console_session.archive_session``
    on purpose: that one spends a Claude call summarizing, which is not
    something a "new chat" click should cost.
    """
    current = (
        find_deep_session(company_id)
        if mode == "deep"
        else find_quick_session(company_id)
    )
    if current is not None:
        console_store.archive_session(company_id, current["id"])
    meta = (
        ensure_deep_session(company_id, output_language=output_language)
        if mode == "deep"
        else ensure_quick_session(company_id, output_language=output_language)
    )
    return {
        "session_id": meta["id"],
        "previous_session_id": (current or {}).get("id") or "",
    }


def find_deep_session(company_id: str) -> dict | None:
    for meta in console_store.list_sessions(company_id):
        if (
            meta.get("status") == "active"
            and meta.get("session_kind") == COPILOT_DEEP_SESSION_KIND
        ):
            return meta
    return None


def ensure_deep_session(
    company_id: str,
    *,
    output_language: str = "en",
) -> dict:
    existing = find_deep_session(company_id)
    if existing is not None:
        return existing
    return console_session.create_session(
        company_id=company_id,
        include_background_docs=True,
        include_library_docs=False,
        output_language=output_language,
        title=COPILOT_DEEP_SESSION_TITLE,
        session_kind=COPILOT_DEEP_SESSION_KIND,
        skip_hydrate=False,
    )


def parse_research_task(text: str) -> dict | None:
    task = parse_structured_outputs(text).get("research_task")
    if isinstance(task, dict) and task.get("title"):
        return task
    return None


def strip_research_task_block(text: str) -> str:
    return strip_structured_blocks(text)


def _maybe_hydrate_quick_session(
    *,
    company_id: str,
    session_id: str,
    prompt: str,
    client_context: dict[str, Any],
    output_language: str,
) -> dict:
    meta = console_store.load_meta(company_id, session_id)
    if meta is None:
        raise ValueError("session_not_found")
    if not needs_hydration(prompt, client_context):
        return meta
    status = str(meta.get("hydration_status") or "")
    if status in {"in_progress", "done"}:
        return meta
    return console_session.hydrate_existing_session(
        company_id=company_id,
        session_id=session_id,
        research_file_ids=scoped_research_file_ids(client_context),
        output_language=output_language,
    )


def stage_attachment(
    company_id: str,
    *,
    filename: str,
    data: bytes,
    mode: str = "quick",
    output_language: str = "en",
) -> dict:
    """Save a file beside Warren's session so the next question can open it.

    Staged on pick rather than on send, so a file he cannot read is refused
    while the analyst is still looking at the composer. Returns the record
    ``console_store.save_attachment`` writes, plus the session it landed in;
    the ask carries the ``stored_name`` back.
    """
    meta = (
        ensure_deep_session(company_id, output_language=output_language)
        if mode == "deep"
        else ensure_quick_session(company_id, output_language=output_language)
    )
    record = console_store.save_attachment(
        company_id=company_id,
        session_id=meta["id"],
        filename=filename,
        data=data,
    )
    return {"session_id": meta["id"], **record}


def submit_quick_ask(
    *,
    company_id: str,
    prompt: str,
    client_context: dict[str, Any] | None = None,
    output_language: str = "en",
    attachments: list[str] | None = None,
    attachment_names: dict[str, str] | None = None,
    author: dict | None = None,
    edits: str | None = None,
) -> dict:
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt_required")
    client_context = client_context if isinstance(client_context, dict) else {}
    runtime_prompt = _prepare_runtime_prompt(company_id, prompt, client_context)
    hydrate_now = needs_hydration(prompt, client_context)
    ios = _is_ios_surface(client_context)
    meta = ensure_quick_session(
        company_id,
        output_language=output_language,
        hydrate=hydrate_now,
        research_file_ids=scoped_research_file_ids(client_context),
        include_background_docs=not ios,
        session_kind=COPILOT_IOS_SESSION_KIND if ios else COPILOT_SESSION_KIND,
        title=COPILOT_IOS_SESSION_TITLE if ios else COPILOT_SESSION_TITLE,
    )
    meta = _maybe_hydrate_quick_session(
        company_id=company_id,
        session_id=meta["id"],
        prompt=prompt,
        client_context=client_context,
        output_language=output_language,
    )
    info = console_session.submit_ask(
        company_id=company_id,
        session_id=meta["id"],
        prompt=prompt.strip(),
        attachments=list(attachments or []),
        runtime_prompt=runtime_prompt,
        attachment_names=attachment_names or {},
        author=author,
        edits=edits,
    )
    return {
        "session_id": meta["id"],
        "turn_id": info["turn_id"],
        "queue_position": info.get("queue_position", 0),
        "stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}"
            f"/ask/stream/{info['turn_id']}"
        ),
        "hydration_status": meta.get("hydration_status"),
        "hydrate_stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}/hydrate/stream"
            if meta.get("hydration_status") == "in_progress"
            else None
        ),
    }


def submit_deep_ask(
    *,
    company_id: str,
    prompt: str,
    client_context: dict[str, Any] | None = None,
    output_language: str = "en",
    attachments: list[str] | None = None,
    attachment_names: dict[str, str] | None = None,
    author: dict | None = None,
    edits: str | None = None,
) -> dict:
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt_required")
    client_context = client_context if isinstance(client_context, dict) else {}
    runtime_prompt = _prepare_runtime_prompt(company_id, prompt, client_context)
    meta = ensure_deep_session(company_id, output_language=output_language)
    info = console_session.submit_ask(
        company_id=company_id,
        session_id=meta["id"],
        prompt=prompt.strip(),
        attachments=list(attachments or []),
        runtime_prompt=runtime_prompt,
        attachment_names=attachment_names or {},
        author=author,
        edits=edits,
    )
    return {
        "session_id": meta["id"],
        "turn_id": info["turn_id"],
        "queue_position": info.get("queue_position", 0),
        "stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}"
            f"/ask/stream/{info['turn_id']}"
        ),
        "hydration_status": meta.get("hydration_status"),
        "hydrate_stream_url": (
            f"/api/companies/{company_id}/console/sessions/{meta['id']}/hydrate/stream"
            if meta.get("hydration_status") == "in_progress"
            else None
        ),
    }
