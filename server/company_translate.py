"""OpenAI-backed translation for company records.

Given a company record (the dict returned by storage.get_company), produce a
parallel `translation` block in the opposite language (en↔zh). Company NAME
and all factual identifiers (ticker, exchange, hq, dates, money amounts,
URLs, founded_year, employee_band) are kept verbatim. Only free-text
descriptive fields are translated.

Returns a dict with two keys:
- `language`: detected source language ("en", "zh", or "other")
- `translation`: dict with translated fields, or None if translation failed

The translation dict mirrors the source company shape: same field names,
same nested structure, but with text values replaced by their translations.
Fields that don't need translation (ticker, hq, etc.) are simply omitted
from the translation block — the UI falls back to the source value.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4.1")


COMPANY_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "language": {
            "type": "string",
            "enum": ["en", "zh", "other"],
            "description": "Detected source language of the company record.",
        },
        "translation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["en", "zh"],
                    "description": "Target language. Always opposite of source for en/zh; en for 'other'.",
                },
                "description": {"type": ["string", "null"]},
                "sector": {"type": ["string", "null"]},
                "industry": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "hq": {"type": ["string", "null"]},
                "employee_band": {"type": ["string", "null"]},
                "parent_company": {"type": ["string", "null"]},
                "key_people": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                        },
                        "required": ["name", "role"],
                    },
                },
                "highlight_2026": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "headline": {"type": ["string", "null"]},
                    },
                    "required": ["headline"],
                },
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["name", "description"],
                    },
                },
                "competitors": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recent_news": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "headline": {"type": "string"},
                            "summary": {"type": ["string", "null"]},
                        },
                        "required": ["headline", "summary"],
                    },
                },
                "notable_contracts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "customer": {"type": "string"},
                            "scope": {"type": ["string", "null"]},
                        },
                        "required": ["customer", "scope"],
                    },
                },
                "notable_acquisitions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "company": {"type": "string"},
                        },
                        "required": ["company"],
                    },
                },
            },
            "required": [
                "language",
                "description",
                "sector",
                "industry",
                "status",
                "hq",
                "employee_band",
                "parent_company",
                "key_people",
                "highlight_2026",
                "products",
                "competitors",
                "recent_news",
                "notable_contracts",
                "notable_acquisitions",
            ],
        },
    },
    "required": ["language", "translation"],
}


SYSTEM_PROMPT = (
    "You translate company research records between English and Chinese for "
    "an investment-research dashboard. Detect the source language of the "
    "free-text fields, then produce a translation in the OPPOSITE language "
    "(English→Chinese, or Chinese→English). If the source is neither, "
    "translate to English.\n\n"
    "Rules:\n"
    "- Keep company name, ticker, dates, money amounts, URLs, founded year, "
    "and employee bands UNCHANGED in the translation. (You won't see those "
    "fields in the input — only translate what's provided.)\n"
    "- Translate person names ONLY if there's a widely-recognized form in the "
    "target language; otherwise keep the original spelling.\n"
    "- Translate company names of competitors ONLY if there's a widely-"
    "recognized form in the target language; otherwise keep the original.\n"
    "- Preserve technical terminology, product names, and acronyms — translate "
    "the surrounding context but keep proper nouns recognizable.\n"
    "- For arrays, return the SAME number of items in the same order.\n"
    "- For null/missing fields in the source, return null in the translation."
)


def _is_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _translatable_payload(company: dict) -> dict:
    """Project a company record down to the fields we want translated.

    Anything not in this projection (name, ticker, hq, founded_year, money
    amounts, dates, URLs) is preserved verbatim by the caller.
    """
    return {
        "description": company.get("description"),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "status": company.get("status"),
        "hq": company.get("hq"),
        "employee_band": company.get("employee_band"),
        "parent_company": company.get("parent_company"),
        "key_people": [
            {"name": p.get("name") or "", "role": p.get("role") or ""}
            for p in (company.get("key_people") or [])
        ],
        "highlight_2026": (
            {"headline": (company.get("highlight_2026") or {}).get("headline")}
            if company.get("highlight_2026")
            else None
        ),
        "products": [
            {"name": p.get("name") or "", "description": p.get("description")}
            for p in (company.get("products") or [])
        ],
        "competitors": list(company.get("competitors") or []),
        "recent_news": [
            {"headline": n.get("headline") or "", "summary": n.get("summary")}
            for n in (company.get("recent_news") or [])
        ],
        "notable_contracts": [
            {"customer": k.get("customer") or "", "scope": k.get("scope")}
            for k in (company.get("notable_contracts") or [])
        ],
        "notable_acquisitions": [
            {"company": a.get("company") or ""}
            for a in (company.get("notable_acquisitions") or [])
        ],
    }


def translate_company(company: dict) -> dict:
    """Translate a company record. Returns `{language, translation}`.

    On failure or missing API key returns `{language: "other", translation: None,
    error: "..."}` so the caller can persist the company without blocking.
    """
    if not _is_available():
        return {
            "language": "other",
            "translation": None,
            "error": "OPENAI_API_KEY not set — translation skipped.",
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {
            "language": "other",
            "translation": None,
            "error": "openai package not installed.",
        }

    payload = _translatable_payload(company)
    user_prompt = (
        f"Company name (do NOT translate): {company.get('name') or ''}\n"
        f"Source fields to translate (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    client = OpenAI()
    try:
        response = client.responses.create(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "company_translation",
                    "schema": COMPANY_TRANSLATION_SCHEMA,
                    "strict": True,
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        msg = f"OpenAI translation failed: {type(exc).__name__}: {exc}"
        logger.warning(msg)
        return {"language": "other", "translation": None, "error": msg}

    raw = getattr(response, "output_text", "")
    if not raw:
        return {
            "language": "other",
            "translation": None,
            "error": "OpenAI returned empty output.",
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "language": "other",
            "translation": None,
            "error": f"OpenAI returned non-JSON: {exc}",
        }
    return data
