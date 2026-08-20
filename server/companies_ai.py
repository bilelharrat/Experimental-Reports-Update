"""Deep search for companies via Claude Code CLI.

Spawns `claude -p` with WebSearch/WebFetch tools and a strict JSON
schema. Results are cached by query (no TTL); pass `force_refresh=True`
to re-query.

This module **does not** call the OpenAI SDK. If the `claude` CLI isn't
installed, the search returns a `fallback` payload (local-registry matches
only) with an explanatory reason.
"""
from __future__ import annotations

import logging
from typing import Any

from . import cache, claude_runner, storage

logger = logging.getLogger(__name__)

MAX_RESULTS = 6

# The 11 GICS sectors. `sector` is constrained to this vocabulary so two
# megacap records can't land in different taxonomies ("Technology" vs
# "Communication Services" — colloquial vs GICS); free-text stays in
# `industry`.
GICS_SECTORS = [
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Information Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
]


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
                    "name": {
                        "type": "string",
                        "description": "Canonical display name, with NO parenthetical qualifiers — disambiguation goes in `disambiguator`",
                    },
                    "legal_name": {
                        "type": ["string", "null"],
                        "description": "Registered legal name ('Anduril Industries, Inc.')",
                    },
                    "disambiguator": {
                        "type": ["string", "null"],
                        "description": "Short qualifier when the plain name is ambiguous — location, DBA, or line of business ('Dallas, TX signage manufacturer'). Never fold this into `name`.",
                    },
                    "ticker": {"type": ["string", "null"]},
                    "exchange": {"type": ["string", "null"]},
                    "status": {
                        "type": ["string", "null"],
                        "description": "public | private | subsidiary | nonprofit | null",
                    },
                    "sector": {
                        "type": ["string", "null"],
                        "enum": [*GICS_SECTORS, None],
                        "description": "One of the 11 GICS sectors, or null",
                    },
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
                    "legal_name",
                    "disambiguator",
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
    "You are a company identification assistant for an investment-research dashboard. "
    "Given a user's free-form query, return up to 6 distinct, real companies "
    "that best match the name, ticker, product, or short description they typed. "
    "Your job in this step is identification, not a full investment analysis.\n\n"
    "Work identity-first:\n"
    "- Confirm which real companies the query could mean.\n"
    "- Prefer disambiguating across multiple plausible matches when the query is "
    "ambiguous (e.g. 'Apple' vs 'Apple Hospitality REIT').\n"
    "- Fill identity fields first: name, legal_name, disambiguator, ticker, "
    "exchange, status, sector, industry, description, hq, website, logo_domain.\n"
    "- Leave deep research fields null or empty when they are not needed to "
    "identify the company. Do not run a full funding, product, contract, or "
    "earnings analysis just to decide which company the user meant.\n"
    "- Use web_search only to resolve identity and to fetch a short description. "
    "Do not treat search as a mandate to populate every optional field.\n\n"
    "Do NOT aim for high fill. Arrays such as key_people, products, competitors, "
    "recent_news, notable_contracts, and notable_acquisitions may be empty. "
    "Objects such as highlight_2026, latest_funding, and latest_earnings may be "
    "null. Enrichment happens later, after the user selects a company.\n\n"
    "Identity fields — these keep repeat searches reconciling to the same "
    "record, so follow them exactly:\n"
    "- name: the canonical display name ('Anduril Industries'). NEVER append "
    "parenthetical qualifiers, locations, or DBAs to it.\n"
    "- legal_name: the registered legal name ('Anduril Industries, Inc.').\n"
    "- disambiguator: when the plain name is ambiguous (two companies share "
    "it), put the distinguishing detail HERE — location, DBA, or line of "
    "business ('Dallas, TX signage manufacturer') — not in name.\n"
    "- sector: exactly one of the 11 GICS sectors from the schema enum; use "
    "industry for the free-text specific business.\n"
    "- description: One sentence — what they do and how they make money.\n"
    "- logo_domain: Bare domain ('anduril.com').\n\n"
    "If a field is not needed for identification and you have not verified it, "
    "return null or []. Do not invent funding numbers, contract values, or "
    "earnings figures."
)


def deep_search(
    query: str,
    *,
    force_refresh: bool = False,
    progress=None,
    only_company_id: str | None = None,
) -> dict:
    """Run a deep search and persist any new matches into local storage.

    Cached results live forever (no TTL) — `force_refresh=True` re-queries
    and overwrites the cache. The response always includes `cached_at` (ISO
    8601, nullable) so the UI can show how stale the data is.

    ``only_company_id`` restricts persistence: only returned matches that
    resolve (by ticker/host/alias evidence) to that existing local record
    are upserted; everything else is discarded unwritten. Refresh flows use
    this so a re-query can never mint a sibling record (QA R5c).

    Returns:
      - source: "claude_code" | "cache" | "fallback"
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

    # All LLM calls go through Claude Code CLI. If `claude` isn't on PATH,
    # we return local-registry matches only — no third-party API fallback.
    if not claude_runner.is_available():
        local = storage.search_companies(q, limit=MAX_RESULTS)
        return {
            "source": "fallback",
            "reason": (
                "Claude Code CLI not installed; install it with "
                "`npm install -g @anthropic-ai/claude-code` and authenticate. "
                "Showing local registry matches only."
            ),
            "matches": [_local_to_match(c) for c in local],
            "cached_at": None,
        }

    if progress:
        progress.emit("stage", stage="claude_starting", message="Starting Claude Code")
    raw, err = claude_runner.run_company_search(
        query=q,
        schema=SCHEMA,
        system_prompt=SYSTEM_PROMPT,
        max_results=MAX_RESULTS,
        progress=progress,
    )

    if raw is None:
        logger.warning("Claude Code search failed: %s", err)
        local = storage.search_companies(q, limit=MAX_RESULTS)
        return {
            "source": "fallback",
            "reason": err or "Claude Code search failed",
            "matches": [_local_to_match(c) for c in local],
            "cached_at": None,
        }

    if only_company_id is not None:
        raw = [
            m for m in raw
            if storage.resolve_company_match(m) == only_company_id
        ]
    enriched = [storage.upsert_company_from_match(m) for m in raw]
    if enriched:
        cache.put("companies_ai", q.lower(), enriched)
        # Invalidate the autocomplete researched index so new hits are
        # visible on the next keystroke.
        from . import companies_autocomplete
        companies_autocomplete.invalidate_researched_cache()
    fresh = cache.get("companies_ai", q.lower())
    return {
        "source": "claude_code",
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
        "industry": c.get("industry"),
        "exchange": c.get("exchange"),
        "status": c.get("status"),
        "company_type": c.get("company_type") or storage.infer_company_type(c),
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
