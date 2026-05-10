"""Deep search for companies — Claude Code (primary) + OpenAI (fallback).

Primary path: spawn `claude -p` with WebSearch/WebFetch tools and the same
JSON schema, so results stay structured and grounded without depending on
an OpenAI key.

Fallback path: the original OpenAI Responses API + `web_search` tool. Used
when the Claude CLI isn't on PATH or its run fails for any reason.

Both paths share the same SCHEMA and SYSTEM_PROMPT so downstream callers
don't care which one produced the result. Results are cached by query
(no TTL); pass `force_refresh=True` to re-query.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import cache, claude_runner, storage

logger = logging.getLogger(__name__)

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
                    "total_funding_usd": {"type": ["string", "null"]},
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
                                "date": {"type": ["string", "null"]},
                                "summary": {"type": ["string", "null"]},
                            },
                            "required": ["headline", "date", "summary"],
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
                                "value_usd": {"type": ["string", "null"]},
                                "date": {"type": ["string", "null"]},
                            },
                            "required": ["customer", "scope", "value_usd", "date"],
                        },
                    },
                    "notable_acquisitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "company": {"type": "string"},
                                "date": {"type": ["string", "null"]},
                                "amount_usd": {"type": ["string", "null"]},
                            },
                            "required": ["company", "date", "amount_usd"],
                        },
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
                    "total_funding_usd",
                    "products",
                    "competitors",
                    "recent_news",
                    "notable_contracts",
                    "notable_acquisitions",
                ],
            },
        }
    },
    "required": ["matches"],
}


SYSTEM_PROMPT = (
    "You are a company research assistant for an investment-research dashboard. "
    "Given a user's free-form query, return up to 6 distinct, real companies "
    "that best match it. Use the web_search tool aggressively to ground every "
    "field in current (2026) public information — funding rounds, earnings, "
    "product releases, customer contracts, M&A activity, leadership changes. "
    "Prefer disambiguating across multiple plausible matches when the query is "
    "ambiguous (e.g. 'Apple' vs 'Apple Hospitality REIT').\n\n"
    "Aim for HIGH FILL — every field that has a verifiable answer should be "
    "populated. Use null only when the field genuinely doesn't apply (e.g. "
    "earnings for a private company) or no public source exists. Use the "
    "company's legal/canonical name ('Anduril Industries, Inc.', not "
    "'Anduril Industries') so repeat searches reconcile to the same record.\n\n"
    "Per-field guidance:\n"
    "- description: One sentence — what they do and how they make money.\n"
    "- key_people: 4–5 entries. ALWAYS include the founder(s), even if no "
    "longer in an exec role; combine founder status with current title where "
    "applicable ('Founder & CEO', 'Co-founder & CTO'). Then current CEO and "
    "CFO if not already covered, plus any other high-profile leaders.\n"
    "- products: 3–6 flagship products, platforms, or business lines, each "
    "with a one-line description of what it does.\n"
    "- competitors: 3–5 direct competitors by name.\n"
    "- recent_news: 3–5 noteworthy items from the last 12 months. Each: "
    "headline, ISO-style date if available, one-sentence summary.\n"
    "- notable_contracts: For B2B / government-facing companies, 2–5 publicly-"
    "reported customer contracts. Include customer, scope, disclosed value if "
    "any, and date.\n"
    "- notable_acquisitions: 2–5 most recent acquisitions the company made, "
    "with date and amount (null if undisclosed).\n"
    "- total_funding_usd: Cumulative funding raised to date (private only).\n"
    "- highlight_2026: The single biggest news for this calendar year.\n"
    "- latest_funding: Most recent round (private only).\n"
    "- latest_earnings: Most recent reported quarter (public only).\n"
    "- founded_year: Integer.\n"
    "- employee_band: Approximate employee range ('1,000–5,000').\n"
    "- logo_domain: Bare domain ('anduril.com').\n\n"
    "Do not invent funding numbers, contract values, or earnings figures — "
    "if you can't verify via web_search, return null."
)


def _is_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _call_openai(query: str) -> tuple[list[dict] | None, str | None]:
    """Returns (matches, error). On success error is None."""
    try:
        from openai import OpenAI
    except ImportError:
        return None, "openai package not installed"

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
        msg = f"OpenAI call failed: {type(exc).__name__}: {exc}"
        logger.warning(msg)
        return None, msg

    text = getattr(response, "output_text", None)
    if not text:
        return None, "OpenAI returned empty output_text"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"OpenAI returned non-JSON: {exc}"
        logger.warning(msg)
        return None, msg
    matches = data.get("matches") or []
    return matches[:MAX_RESULTS], None


def deep_search(query: str, *, force_refresh: bool = False) -> dict:
    """Run a deep search and persist any new matches into local storage.

    Cached results live forever (no TTL) — `force_refresh=True` re-queries
    and overwrites the cache. The response always includes `cached_at` (ISO
    8601, nullable) so the UI can show how stale the data is.

    Returns:
      - source: "openai" | "cache" | "fallback"
      - matches: list of enriched company dicts (each carries a local `id`)
      - cached_at: ISO 8601 of the last successful query, or null
      - reason: present only on `fallback`, explains why
    """
    q = (query or "").strip()
    if not q:
        return {"source": "fallback", "matches": [], "cached_at": None}

    if not force_refresh:
        cached = cache.get("companies_ai", q.lower())
        if cached is not None:
            return {
                "source": "cache",
                "matches": cached["value"] or [],
                "cached_at": cached["stored_at_iso"],
            }

    raw: list[dict] | None = None
    source_used: str | None = None
    last_err: str | None = None

    # Primary: Claude Code CLI with WebSearch/WebFetch tools.
    if claude_runner.is_available():
        raw, err = claude_runner.run_company_search(
            query=q,
            schema=SCHEMA,
            system_prompt=SYSTEM_PROMPT,
            max_results=MAX_RESULTS,
        )
        if raw is not None:
            source_used = "claude_code"
        else:
            last_err = err
            logger.warning("Claude Code search failed, falling back: %s", err)

    # Fallback: OpenAI Responses API + web_search.
    if raw is None and _is_available():
        raw, err = _call_openai(q)
        if raw is not None:
            source_used = "openai"
        else:
            last_err = err

    if raw is None:
        local = storage.search_companies(q, limit=MAX_RESULTS)
        reason = last_err or (
            "Neither Claude Code nor OPENAI_API_KEY is configured — showing "
            "local matches only"
        )
        return {
            "source": "fallback",
            "reason": reason,
            "matches": [_local_to_match(c) for c in local],
            "cached_at": None,
        }

    enriched = [storage.upsert_company_from_match(m) for m in raw]
    if enriched:
        cache.put("companies_ai", q.lower(), enriched)
        # Invalidate the autocomplete researched index so new hits are visible
        # on the next keystroke.
        from . import companies_autocomplete

        companies_autocomplete.invalidate_researched_cache()
    fresh = cache.get("companies_ai", q.lower())
    return {
        "source": source_used or "openai",
        "matches": enriched,
        "cached_at": fresh["stored_at_iso"] if fresh else None,
    }


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
