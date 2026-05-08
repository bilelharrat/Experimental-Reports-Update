"""OpenAI-backed deep search for companies.

Uses the Responses API with the `web_search` tool so results are grounded in
2026-current information, plus a JSON-schema structured output to keep the
shape consistent. Cached by query for 24h.

Requires OPENAI_API_KEY. Falls back to local-only results if the key is
missing or the call fails — the app still works without an OpenAI key.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import cache, storage

logger = logging.getLogger(__name__)

CACHE_TTL = 24 * 60 * 60
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
MAX_RESULTS = 6


# JSON schema for the structured output. Strict mode requires every property
# to be listed in `required` and `additionalProperties: false`. Optional
# fields are typed as `["string", "null"]` etc. so the model can emit null.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "ticker": {"type": ["string", "null"]},
                    "exchange": {"type": ["string", "null"]},
                    "status": {
                        "type": ["string", "null"],
                        "description": "public | private | subsidiary | nonprofit | null",
                    },
                    "sector": {"type": ["string", "null"]},
                    "industry": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "hq": {"type": ["string", "null"]},
                    "founded_year": {"type": ["integer", "null"]},
                    "website": {"type": ["string", "null"]},
                    "logo_domain": {
                        "type": ["string", "null"],
                        "description": "Bare domain like 'apple.com' for use with Clearbit-style logos",
                    },
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
                            "headline": {"type": "string"},
                            "date": {"type": ["string", "null"]},
                        },
                        "required": ["headline", "date"],
                    },
                    "latest_funding": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "round": {"type": ["string", "null"]},
                            "amount_usd": {"type": ["string", "null"]},
                            "date": {"type": ["string", "null"]},
                            "lead_investor": {"type": ["string", "null"]},
                            "post_money_usd": {"type": ["string", "null"]},
                        },
                        "required": [
                            "round",
                            "amount_usd",
                            "date",
                            "lead_investor",
                            "post_money_usd",
                        ],
                    },
                    "latest_earnings": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "period": {"type": ["string", "null"]},
                            "revenue_yoy": {"type": ["string", "null"]},
                            "eps": {"type": ["string", "null"]},
                            "beat_or_miss": {"type": ["string", "null"]},
                        },
                        "required": ["period", "revenue_yoy", "eps", "beat_or_miss"],
                    },
                },
                "required": [
                    "name",
                    "ticker",
                    "exchange",
                    "status",
                    "sector",
                    "industry",
                    "description",
                    "hq",
                    "founded_year",
                    "website",
                    "logo_domain",
                    "employee_band",
                    "parent_company",
                    "key_people",
                    "highlight_2026",
                    "latest_funding",
                    "latest_earnings",
                ],
            },
        }
    },
    "required": ["matches"],
}


SYSTEM_PROMPT = (
    "You are a company research assistant for an investment-research dashboard. "
    "Given a user's free-form query, return up to 6 distinct, real companies that "
    "best match it. Use the web_search tool to ground your answers in current "
    "(2026) information — especially for funding rounds, earnings, and recent "
    "news. Prefer disambiguating across multiple plausible matches when the query "
    "is ambiguous (e.g. 'Apple' vs 'Apple Hospitality REIT'). If a field is "
    "unknown or unverifiable, return null rather than guessing. Keep descriptions "
    "to a single sentence."
)


def _is_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _call_openai(query: str) -> list[dict] | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return None

    client = OpenAI()
    try:
        response = client.responses.create(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Find companies matching: {query}",
                },
            ],
            tools=[{"type": "web_search"}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "company_matches",
                    "schema": SCHEMA,
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        logger.warning("OpenAI deep search failed: %s", exc)
        return None

    text = getattr(response, "output_text", None)
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("OpenAI returned non-JSON output: %s", exc)
        return None
    matches = data.get("matches") or []
    return matches[:MAX_RESULTS]


def deep_search(query: str) -> dict:
    """Run a deep search and persist any new matches into local storage.

    Returns a dict with:
      - source: "openai" | "cache" | "fallback"
      - matches: list of enriched company dicts (each carries a local `id`)
    """
    q = (query or "").strip()
    if not q:
        return {"source": "fallback", "matches": []}

    cached = cache.get("companies_ai", q.lower(), CACHE_TTL)
    if cached is not None:
        return {"source": "cache", "matches": cached}

    if not _is_available():
        local = storage.search_companies(q, limit=MAX_RESULTS)
        return {
            "source": "fallback",
            "matches": [_local_to_match(c) for c in local],
        }

    raw = _call_openai(q)
    if raw is None:
        local = storage.search_companies(q, limit=MAX_RESULTS)
        return {
            "source": "fallback",
            "matches": [_local_to_match(c) for c in local],
        }

    enriched = [storage.upsert_company_from_match(m) for m in raw]
    cache.put("companies_ai", q.lower(), enriched)
    return {"source": "openai", "matches": enriched}


def _local_to_match(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "ticker": c.get("ticker"),
        "description": c.get("description"),
        "sector": c.get("sector"),
        "industry": None,
        "exchange": None,
        "status": None,
        "hq": None,
        "founded_year": None,
        "website": None,
        "logo_domain": None,
        "employee_band": None,
        "parent_company": None,
        "key_people": [],
        "highlight_2026": None,
        "latest_funding": None,
        "latest_earnings": None,
    }
