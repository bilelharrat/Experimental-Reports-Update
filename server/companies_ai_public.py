"""Public-company trader snapshot — the schema + system prompt used to
populate ``company.trader_snapshot`` for public companies.

Companion to ``companies_ai.py`` (which does dossier-style search for
ALL companies). This module is invoked only when an existing company's
``company_type == "public"`` and the user clicks Refresh.

See docs/public-company-trader-view.md §3 for the on-disk shape and §4
for the pipeline.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, storage
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)


# JSON schema for the strict-mode structured output. Strict mode rules
# Claude Code enforces: every property must appear in `required`, every
# object must have `additionalProperties: false`, optional fields use
# union types with ``null``.

_NUM_NULL = {"type": ["number", "null"]}
_STR_NULL = {"type": ["string", "null"]}
_INT_NULL = {"type": ["integer", "null"]}
_BOOL_NULL = {"type": ["boolean", "null"]}

# Declarative per-section confidence. "unavailable" means the model
# couldn't source the data fields; the paired confidence_note_* still
# has to explain *why* so the iOS UI can render "couldn't source: X"
# rather than a silent blank. See docs/heat-card-v2.md §4.
_CONFIDENCE = {
    "type": ["string", "null"],
    "enum": ["high", "medium", "low", "unavailable", None],
}
_CONFIDENCE_REQUIRED = [
    "confidence", "confidence_note_en", "confidence_note_zh",
]


def _localized_props(base: str) -> dict[str, Any]:
    return {f"{base}_en": _STR_NULL, f"{base}_zh": _STR_NULL}


def _localized_required(base: str) -> list[str]:
    return [f"{base}_en", f"{base}_zh"]


def _confidence_props() -> dict[str, Any]:
    return {
        "confidence": _CONFIDENCE,
        "confidence_note_en": _STR_NULL,
        "confidence_note_zh": _STR_NULL,
    }


# Current trader_snapshot.schema_version. Bumped when a breaking
# heat_card / structural change lands. The server's startup migration
# strips snapshots older than this; the worker stamps the current
# value on every fresh snapshot it writes. See docs/heat-card-v2.md §6.
TRADER_SNAPSHOT_SCHEMA_VERSION: int = 2

SECTION_STATUS_KEY = "section_status"
SECTION_ARTIFACT_SCHEMA_VERSION = 1

SECTION_KEYS: tuple[str, ...] = (
    "market_session",
    "price_card",
    "momentum_card",
    "sentiment_card",
    "heat_card",
    "catalysts",
    "trader_news",
    "research_overview",
    "tech_movers",
)

SECTION_LABELS: dict[str, str] = {
    "market_session": "Market session",
    "price_card": "Price & returns",
    "momentum_card": "Momentum",
    "sentiment_card": "Analyst sentiment",
    "heat_card": "Positioning structure",
    "catalysts": "Upcoming catalysts",
    "trader_news": "Trader news",
    "research_overview": "Research overview",
    "tech_movers": "Tech movers",
}

SECTION_TTL_SECONDS: dict[str, int] = {
    "market_session": 15 * 60,
    "price_card": 15 * 60,
    "momentum_card": 30 * 60,
    "tech_movers": 30 * 60,
    "trader_news": 60 * 60,
    "catalysts": 12 * 60 * 60,
    "sentiment_card": 24 * 60 * 60,
    "heat_card": 4 * 60 * 60,
    "research_overview": 7 * 24 * 60 * 60,
}


SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "price_card": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "last_price": _NUM_NULL,
                "currency": _STR_NULL,
                "as_of": _STR_NULL,
                "change_pct_1d": _NUM_NULL,
                "change_pct_5d": _NUM_NULL,
                "change_pct_30d": _NUM_NULL,
                "change_pct_ytd": _NUM_NULL,
                "change_pct_1y": _NUM_NULL,
                "vs_sector_30d_pct": _NUM_NULL,
                "vs_sp500_30d_pct": _NUM_NULL,
            },
            "required": [
                "last_price", "currency", "as_of",
                "change_pct_1d", "change_pct_5d", "change_pct_30d",
                "change_pct_ytd", "change_pct_1y",
                "vs_sector_30d_pct", "vs_sp500_30d_pct",
            ],
        },

        "momentum_card": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "trend": {
                    "type": ["string", "null"],
                    "enum": ["bullish", "neutral", "bearish", None],
                },
                "trend_en": _STR_NULL,
                "trend_zh": _STR_NULL,
                "above_50dma": _BOOL_NULL,
                "above_200dma": _BOOL_NULL,
                "ma_crossover_recent": {
                    "type": ["string", "null"],
                    "enum": ["golden_cross", "death_cross", None],
                },
                "breakout_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "breakout_signals_en": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "breakout_signals_zh": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "notable_levels": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "support": _NUM_NULL,
                        "resistance": _NUM_NULL,
                    },
                    "required": ["support", "resistance"],
                },
            },
            "required": [
                "trend", "trend_en", "trend_zh",
                "above_50dma", "above_200dma",
                "ma_crossover_recent",
                "breakout_signals", "breakout_signals_en", "breakout_signals_zh",
                "notable_levels",
            ],
        },

        "sentiment_card": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "analyst_consensus": {
                    "type": ["string", "null"],
                    "enum": ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell", None],
                },
                "analyst_consensus_en": _STR_NULL,
                "analyst_consensus_zh": _STR_NULL,
                "coverage_count": _INT_NULL,
                "rating_distribution": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "strong_buy": _INT_NULL,
                        "buy": _INT_NULL,
                        "hold": _INT_NULL,
                        "sell": _INT_NULL,
                        "strong_sell": _INT_NULL,
                    },
                    "required": [
                        "strong_buy", "buy", "hold", "sell", "strong_sell",
                    ],
                },
                "target_price": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "mean": _NUM_NULL,
                        "high": _NUM_NULL,
                        "low": _NUM_NULL,
                    },
                    "required": ["mean", "high", "low"],
                },
                "recent_rating_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "firm": {"type": "string"},
                            "action": _STR_NULL,
                            "action_en": _STR_NULL,
                            "action_zh": _STR_NULL,
                            "from": _STR_NULL,
                            "from_en": _STR_NULL,
                            "from_zh": _STR_NULL,
                            "to": _STR_NULL,
                            "to_en": _STR_NULL,
                            "to_zh": _STR_NULL,
                            "date": _STR_NULL,
                            "target": _NUM_NULL,
                        },
                        "required": [
                            "firm",
                            "action", "action_en", "action_zh",
                            "from", "from_en", "from_zh",
                            "to", "to_en", "to_zh",
                            "date", "target",
                        ],
                    },
                },
            },
            "required": [
                "analyst_consensus",
                "analyst_consensus_en", "analyst_consensus_zh",
                "coverage_count",
                "rating_distribution", "target_price", "recent_rating_changes",
            ],
        },

        # heat_card v2 — Positioning Structure. Eight high-signal
        # institutional sub-objects + three derived composites. Every
        # estimated section carries a declarative `confidence` enum
        # and paired bilingual `confidence_note_*` strings. See
        # docs/heat-card-v2.md for the full spec.
        "heat_card": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {

                # 1. Institutional cost basis — anchored VWAPs.
                "anchored_vwaps": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "current_price": _NUM_NULL,
                        "anchors": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "earnings", "ai_event", "ipo",
                                            "secondary", "52w_high",
                                            "macro_event", "other",
                                        ],
                                    },
                                    "label_en": _STR_NULL,
                                    "label_zh": _STR_NULL,
                                    "date": _STR_NULL,
                                    "price": _NUM_NULL,
                                },
                                "required": [
                                    "kind", "label_en", "label_zh",
                                    "date", "price",
                                ],
                            },
                        },
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "current_price", "anchors",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 2. Float turnover zones — where shares changed hands.
                "float_turnover_zones": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "zones": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "low": _NUM_NULL,
                                    "high": _NUM_NULL,
                                    "pct_float": _NUM_NULL,
                                    "note_en": _STR_NULL,
                                    "note_zh": _STR_NULL,
                                },
                                "required": [
                                    "low", "high", "pct_float",
                                    "note_en", "note_zh",
                                ],
                            },
                        },
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "zones", "confidence",
                        "confidence_note_en", "confidence_note_zh",
                    ],
                },

                # 3. Holder mix — institutional ownership stability.
                "holder_mix": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "passive_pct": _NUM_NULL,
                        "long_only_pct": _NUM_NULL,
                        "hedge_fund_pct": _NUM_NULL,
                        "retail_pct": _NUM_NULL,
                        "insider_pct": _NUM_NULL,
                        "strategic_pct": _NUM_NULL,
                        "quality_label_en": _STR_NULL,
                        "quality_label_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "passive_pct", "long_only_pct",
                        "hedge_fund_pct", "retail_pct",
                        "insider_pct", "strategic_pct",
                        "quality_label_en", "quality_label_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 4. Options positioning — dealer gamma + walls.
                "options_positioning": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "gamma_flip": _NUM_NULL,
                        "put_wall": _NUM_NULL,
                        "call_wall": _NUM_NULL,
                        "regime_en": _STR_NULL,
                        "regime_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "gamma_flip", "put_wall", "call_wall",
                        "regime_en", "regime_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 5. Short pressure — squeeze fuel + structural shorts.
                "short_pressure": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "si_pct_float": _NUM_NULL,
                        "days_to_cover": _NUM_NULL,
                        "borrow_rate_pct": _NUM_NULL,
                        "trend": {
                            "type": ["string", "null"],
                            "enum": ["rising", "falling", "flat", None],
                        },
                        "note_en": _STR_NULL,
                        "note_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "si_pct_float", "days_to_cover",
                        "borrow_rate_pct", "trend",
                        "note_en", "note_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 6. Relative valuation — downside asymmetry.
                "valuation": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "ev_revenue_current": _NUM_NULL,
                        "ev_revenue_5y_percentile": _INT_NULL,
                        "fwd_ev_ebitda": _NUM_NULL,
                        "peg": _NUM_NULL,
                        "note_en": _STR_NULL,
                        "note_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "ev_revenue_current",
                        "ev_revenue_5y_percentile",
                        "fwd_ev_ebitda", "peg",
                        "note_en", "note_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 7. Estimate revision momentum.
                "revisions": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "eps_up_30d": _INT_NULL,
                        "eps_down_30d": _INT_NULL,
                        "eps_up_90d": _INT_NULL,
                        "eps_down_90d": _INT_NULL,
                        "direction": {
                            "type": ["string", "null"],
                            "enum": ["up", "down", "mixed", None],
                        },
                        "note_en": _STR_NULL,
                        "note_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "eps_up_30d", "eps_down_30d",
                        "eps_up_90d", "eps_down_90d",
                        "direction", "note_en", "note_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # 8. Next catalyst — repricing trigger + implied move.
                "next_catalyst": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "label_en": _STR_NULL,
                        "label_zh": _STR_NULL,
                        "date": _STR_NULL,
                        "implied_move_pct": _NUM_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "label_en", "label_zh",
                        "date", "implied_move_pct",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # Composite 1. Support confidence by price zone.
                "support_confidence": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "zones": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "low": _NUM_NULL,
                                    "high": _NUM_NULL,
                                    "confidence": _CONFIDENCE,
                                    "reasons_en": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "reasons_zh": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": [
                                    "low", "high", "confidence",
                                    "reasons_en", "reasons_zh",
                                ],
                            },
                        },
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "zones", "confidence",
                        "confidence_note_en", "confidence_note_zh",
                    ],
                },

                # Composite 2. Fragility — 0-100 score + drivers.
                "fragility": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "score": _INT_NULL,
                        "rating": {
                            "type": ["string", "null"],
                            "enum": [
                                "low", "medium", "high", "extreme", None,
                            ],
                        },
                        "drivers_en": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "drivers_zh": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "score", "rating",
                        "drivers_en", "drivers_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },

                # Composite 3. Repricing risk — directional probability.
                "repricing_risk": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "positive_pct": _INT_NULL,
                        "neutral_pct": _INT_NULL,
                        "negative_pct": _INT_NULL,
                        "note_en": _STR_NULL,
                        "note_zh": _STR_NULL,
                        "confidence": _CONFIDENCE,
                        "confidence_note_en": _STR_NULL,
                        "confidence_note_zh": _STR_NULL,
                    },
                    "required": [
                        "positive_pct", "neutral_pct",
                        "negative_pct",
                        "note_en", "note_zh",
                        "confidence", "confidence_note_en",
                        "confidence_note_zh",
                    ],
                },
            },
            "required": [
                "anchored_vwaps", "float_turnover_zones",
                "holder_mix", "options_positioning",
                "short_pressure", "valuation", "revisions",
                "next_catalyst", "support_confidence",
                "fragility", "repricing_risk",
            ],
        },

        "catalysts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "earnings", "guidance", "regulatory",
                            "conference", "product", "legal",
                            "dividend", "other",
                        ],
                    },
                    "title": {"type": "string"},
                    "title_en": _STR_NULL,
                    "title_zh": _STR_NULL,
                    "summary": _STR_NULL,
                    "summary_en": _STR_NULL,
                    "summary_zh": _STR_NULL,
                    "est_impact": {
                        "type": ["string", "null"],
                        "enum": ["high", "medium", "low", None],
                    },
                },
                "required": [
                    "date", "type",
                    "title", "title_en", "title_zh",
                    "summary", "summary_en", "summary_zh",
                    "est_impact",
                ],
            },
        },

        "trader_news": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "headline": {"type": "string"},
                    "headline_en": _STR_NULL,
                    "headline_zh": _STR_NULL,
                    "date": _STR_NULL,
                    "summary": _STR_NULL,
                    "summary_en": _STR_NULL,
                    "summary_zh": _STR_NULL,
                    "bias": {
                        "type": ["string", "null"],
                        "enum": ["positive", "negative", "neutral", None],
                    },
                    "source_url": _STR_NULL,
                },
                "required": [
                    "headline", "headline_en", "headline_zh",
                    "date",
                    "summary", "summary_en", "summary_zh",
                    "bias", "source_url",
                ],
            },
        },

        "research_overview": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "updated_at": _STR_NULL,
                "business_mix": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        **_localized_props("headline"),
                        "segments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    **_localized_props("name"),
                                    "revenue_pct": _NUM_NULL,
                                    "growth_pct": _NUM_NULL,
                                    "signal": {
                                        "type": ["string", "null"],
                                        "enum": [
                                            "growth_engine", "cash_engine",
                                            "drag", "emerging", "cyclical",
                                            None,
                                        ],
                                    },
                                    **_localized_props("note"),
                                },
                                "required": [
                                    *_localized_required("name"),
                                    "revenue_pct", "growth_pct", "signal",
                                    *_localized_required("note"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        *_localized_required("headline"),
                        "segments", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
                "financial_quality": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "score": _INT_NULL,
                        **_localized_props("summary"),
                        "metrics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    **_localized_props("label"),
                                    "value": _STR_NULL,
                                    "percentile": _NUM_NULL,
                                    "direction": {
                                        "type": ["string", "null"],
                                        "enum": ["strong", "neutral", "weak", None],
                                    },
                                    **_localized_props("note"),
                                },
                                "required": [
                                    *_localized_required("label"),
                                    "value", "percentile", "direction",
                                    *_localized_required("note"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        "score", *_localized_required("summary"),
                        "metrics", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
                "growth_durability": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        **_localized_props("thesis"),
                        "horizons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "period": {"type": "string"},
                                    "revenue_growth_pct": _NUM_NULL,
                                    "eps_growth_pct": _NUM_NULL,
                                    "margin_delta_bp": _NUM_NULL,
                                    **_localized_props("note"),
                                },
                                "required": [
                                    "period", "revenue_growth_pct",
                                    "eps_growth_pct", "margin_delta_bp",
                                    *_localized_required("note"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        *_localized_required("thesis"),
                        "horizons", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
                "peer_context": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        **_localized_props("summary"),
                        "peers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "ticker": {"type": "string"},
                                    "company_en": {"type": "string"},
                                    "company_zh": {"type": "string"},
                                    "score": _INT_NULL,
                                    "revenue_growth_pct": _NUM_NULL,
                                    "gross_margin_pct": _NUM_NULL,
                                    "valuation_premium_pct": _NUM_NULL,
                                    **_localized_props("note"),
                                },
                                "required": [
                                    "ticker", "company_en", "company_zh",
                                    "score", "revenue_growth_pct",
                                    "gross_margin_pct",
                                    "valuation_premium_pct",
                                    *_localized_required("note"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        *_localized_required("summary"),
                        "peers", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
                "scenario_matrix": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        **_localized_props("summary"),
                        "scenarios": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "case": {
                                        "type": "string",
                                        "enum": ["bear", "base", "bull"],
                                    },
                                    **_localized_props("label"),
                                    "probability_pct": _NUM_NULL,
                                    "implied_return_pct": _NUM_NULL,
                                    **_localized_props("key_driver"),
                                },
                                "required": [
                                    "case", *_localized_required("label"),
                                    "probability_pct", "implied_return_pct",
                                    *_localized_required("key_driver"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        *_localized_required("summary"),
                        "scenarios", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
                "diligence_questions": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        **_localized_props("summary"),
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    **_localized_props("question"),
                                    **_localized_props("why_it_matters"),
                                    "severity": {
                                        "type": ["string", "null"],
                                        "enum": [
                                            "watch", "important", "critical",
                                            None,
                                        ],
                                    },
                                    **_localized_props("evidence_gap"),
                                },
                                "required": [
                                    *_localized_required("question"),
                                    *_localized_required("why_it_matters"),
                                    "severity",
                                    *_localized_required("evidence_gap"),
                                ],
                            },
                        },
                        "source_url": _STR_NULL,
                        **_confidence_props(),
                    },
                    "required": [
                        *_localized_required("summary"),
                        "questions", "source_url", *_CONFIDENCE_REQUIRED,
                    ],
                },
            },
            "required": [
                "updated_at",
                "business_mix",
                "financial_quality",
                "growth_durability",
                "peer_context",
                "scenario_matrix",
                "diligence_questions",
            ],
        },

        # Authoritative exchange trading-session calendar as of
        # generation. The web/iOS clients use last_close / next_close to
        # measure freshness in *trading sessions* (a Fri-after-close run
        # is current until the next real session close), correctly
        # handling weekends, holidays, half-days AND unscheduled
        # closures that a rule-based calendar cannot know.
        "market_session": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "exchange": _STR_NULL,
                "tz": _STR_NULL,
                "as_of": _STR_NULL,
                "is_open_now": _BOOL_NULL,
                "last_session_date": _STR_NULL,
                "last_close": _STR_NULL,
                "next_session_date": _STR_NULL,
                "next_open": _STR_NULL,
                "next_close": _STR_NULL,
                "next_is_early_close": _BOOL_NULL,
                "source_url": _STR_NULL,
                "confidence": _CONFIDENCE,
                "confidence_note_en": _STR_NULL,
                "confidence_note_zh": _STR_NULL,
            },
            "required": [
                "exchange", "tz", "as_of", "is_open_now",
                "last_session_date", "last_close",
                "next_session_date", "next_open", "next_close",
                "next_is_early_close", "source_url",
                "confidence", "confidence_note_en", "confidence_note_zh",
            ],
        },

        "tech_movers": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "updated_at": _STR_NULL,
                "movers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "ticker": {"type": "string"},
                            "company_en": {"type": "string"},
                            "company_zh": {"type": "string"},
                            "change_pct_1d": _NUM_NULL,
                            "direction": {
                                "type": ["string", "null"],
                                "enum": ["up", "down", "flat", None],
                            },
                            "market_driver_en": {"type": "string"},
                            "market_driver_zh": {"type": "string"},
                            "source_url": _STR_NULL,
                        },
                        "required": [
                            "ticker",
                            "company_en",
                            "company_zh",
                            "change_pct_1d",
                            "direction",
                            "market_driver_en",
                            "market_driver_zh",
                            "source_url",
                        ],
                    },
                },
            },
            "required": ["updated_at", "movers"],
        },
    },
    "required": [
        "price_card",
        "momentum_card",
        "sentiment_card",
        "heat_card",
        "catalysts",
        "trader_news",
        "research_overview",
        "market_session",
        "tech_movers",
    ],
}


SYSTEM_PROMPT = (
    "You are a sell-side trader's research desk. Given a publicly-traded "
    "company (ticker + name), produce a JSON snapshot covering price "
    "action, momentum, sentiment, heat, upcoming catalysts, "
    "trader-relevant news, and a research-grade overview that goes "
    "beyond commodity quote-page facts.\n\n"
    "Use WebSearch and WebFetch aggressively against Yahoo Finance, "
    "Nasdaq, the official IR page, the SEC, Refinitiv-style aggregator "
    "pages, Reuters, Bloomberg, and recent analyst reports. NEVER invent "
    "numbers — if a field can't be verified from a public source, return "
    "null. The user is making a snap trading decision; a null is much "
    "better than a guess.\n\n"
    "BILINGUAL OUTPUT — HARD CONTRACT. Every prose field in this "
    "schema has paired `_en` (English) and `_zh` (Simplified Chinese) "
    "siblings. The acceptable states for any pair are:\n"
    "  - BOTH filled — preferred, this is the goal.\n"
    "  - BOTH null — only when the underlying fact is genuinely "
    "    unknown / unsourceable.\n"
    "ONE-FILLED-ONE-NULL IS NEVER ACCEPTABLE. If you can produce the "
    "English text, you MUST produce the Chinese translation, and vice "
    "versa — the iOS app's language toggle is broken when a pair is "
    "half-populated. The Chinese version is a faithful translation of "
    "the same fact, not a different summary, not a transliteration of "
    "English words. Use natural trader/finance Chinese (e.g. "
    "'看涨'/'看跌'/'中性' for trend, '强力买入'/'买入'/'持有'/'卖出'/"
    "'强力卖出' for ratings, '上调'/'下调'/'首次覆盖'/'重申' for rating "
    "actions, '财报'/'指引'/'监管'/'会议'/'产品'/'法律'/'分红' for "
    "catalyst types). Keep tickers, firm names, and product codes in "
    "Latin script in both languages. Legacy single-language fields "
    "(`trend`, `breakout_signals`, `analyst_consensus`, `title`, "
    "`summary`, `headline`, and `recent_rating_changes[*].action/from/"
    "to`) should carry the same content as the `_en` variant for "
    "back-compat with consumers that haven't been updated yet.\n\n"
    f"{INVESTMENT_RESEARCH_CHINESE_STYLE}\n"
    "Belt-and-suspenders: the server runs a translation pass after "
    "your output that fills any half-populated pair you leave behind. "
    "Don't rely on it — produce both languages yourself when you can. "
    "Save the translation pass for the cases where you couldn't.\n\n"
    "Per-card guidance:\n"
    "- price_card: last close + percent returns vs prior day, 5 trading "
    "  days, 30 calendar days, year-to-date, and trailing 12 months, "
    "  plus the 30-day return relative to a sector ETF and to the S&P "
    "  500. Currency is the listing currency (USD for US, etc.).\n"
    "  HOW TO GET change_pct_30d / vs_sector_30d_pct / vs_sp500_30d_pct "
    "  (these are frequently left null — do NOT skip them): WebFetch the "
    "  Yahoo Finance historical-prices page for the ticker "
    "  (finance.yahoo.com/quote/<TICKER>/history) and read the close ~30 "
    "  CALENDAR days ago (use the nearest trading day on/just before that "
    "  date). change_pct_30d = (last_close / close_30cal_days_ago - 1) * "
    "  100, rounded to 1 decimal. Then do the SAME 30-day return for the "
    "  S&P 500 (ticker ^GSPC) and for the company's sector ETF, and "
    "  report the DIFFERENCES: vs_sp500_30d_pct = stock_30d - sp500_30d; "
    "  vs_sector_30d_pct = stock_30d - sector_etf_30d. Sector→ETF map: "
    "  tech/software→XLK (software-heavy→IGV), semiconductors→SOXX, "
    "  internet/comms→XLC, energy→XLE, financials→XLF, healthcare/"
    "  biotech→XLV, consumer discretionary→XLY, consumer staples→XLP, "
    "  industrials→XLI, materials→XLB, utilities→XLU, real estate→XLRE. "
    "  Pick the closest fit for the company's primary business. Only "
    "  return null for one of these three if the underlying historical "
    "  series genuinely can't be fetched — then say so is implied by the "
    "  null (there is no note field here).\n"
    "- momentum_card: trend label (bullish/neutral/bearish — your call "
    "  given price action and MA position) plus localized trend_en/"
    "  trend_zh display strings, whether the close is above the 50-day "
    "  and 200-day MAs, any recent golden/death cross, breakout/"
    "  breakdown signals (e.g. '5-day high', '20-day low', "
    "  'channel break') with parallel breakout_signals_en and "
    "  breakout_signals_zh arrays of the SAME length and order, and "
    "  approximate nearest support / resistance levels.\n"
    "- sentiment_card: current analyst consensus (enum + "
    "  analyst_consensus_en/analyst_consensus_zh display strings) + "
    "  coverage count + rating distribution + price-target mean/high/"
    "  low + the last 30 days of meaningful rating changes (firm, "
    "  action, from→to, target). Each rating change carries bilingual "
    "  action_en/action_zh, from_en/from_zh, to_en/to_zh strings. "
    "  Source from a reputable aggregator (Yahoo Finance, Nasdaq, "
    "  MarketBeat, Zacks).\n"
    "- heat_card (Positioning Structure): institutional-trading "
    "  positioning snapshot in eight sub-objects plus three composites. "
    "  Every sub-object is independently nullable. Every estimated "
    "  sub-object MUST carry a declarative `confidence` enum "
    "  (high/medium/low/unavailable) AND paired bilingual "
    "  `confidence_note_en` / `confidence_note_zh` strings — these "
    "  explain *how* you sourced the data and, when "
    "  confidence==`unavailable`, *why* you couldn't (e.g. \"SpotGamma "
    "  pay-walled\", \"borrow rate not public\"). NEVER silently leave "
    "  a section blank — the iOS app renders these notes verbatim. "
    "  Sub-objects:\n"
    "    1. anchored_vwaps — current_price + a list of AVWAP anchors "
    "       from key events (earnings, AI events, IPO, secondaries, "
    "       52-week high, macro events). Each anchor has kind (enum), "
    "       label_en, label_zh, date, price. Source from Yahoo charts, "
    "       sell-side notes, or compute from publicly-listed event "
    "       dates plus close prices.\n"
    "    2. float_turnover_zones — top 3-5 price ranges where the "
    "       most float changed hands. Each zone has low/high price + "
    "       pct_float (percent of float traded inside the range) + "
    "       a one-line note_en/note_zh explaining why this zone "
    "       matters (e.g. \"post-earnings accumulation\").\n"
    "    3. holder_mix — institutional ownership breakdown as "
    "       percentages: passive_pct, long_only_pct, hedge_fund_pct, "
    "       retail_pct, insider_pct, strategic_pct. Should sum to ~100. "
    "       Plus quality_label_en / quality_label_zh — one-line "
    "       interpretation (e.g. \"Passive anchor, HF overhang\" / "
    "       \"被动资金提供锚定，对冲基金存在抛压\").\n"
    "    4. options_positioning — dealer-gamma regime: gamma_flip "
    "       price (level below which dealers are short gamma), "
    "       put_wall (largest put OI), call_wall (largest call OI), "
    "       plus regime_en / regime_zh one-line summary "
    "       (e.g. \"Above gamma flip — stable\").\n"
    "    5. short_pressure — si_pct_float (FINRA), days_to_cover, "
    "       borrow_rate_pct (broker / Iborrow), trend "
    "       (rising/falling/flat), plus note_en/note_zh "
    "       interpreting fragility (e.g. \"High SI + low borrow → "
    "       weak bearish conviction\").\n"
    "    6. valuation — ev_revenue_current, "
    "       ev_revenue_5y_percentile (0-100), fwd_ev_ebitda, peg, "
    "       plus note_en/note_zh on downside asymmetry "
    "       (e.g. \"EV/Rev at 18th percentile vs 5y — downside "
    "       compressed\").\n"
    "    7. revisions — eps_up_30d, eps_down_30d, eps_up_90d, "
    "       eps_down_90d (counts), direction (up/down/mixed), plus "
    "       note_en/note_zh summarizing forward momentum.\n"
    "    8. next_catalyst — the single most-imminent catalyst that "
    "       will reprice the name: label_en/label_zh, date, "
    "       implied_move_pct from the ATM straddle.\n"
    "    Composite 1. support_confidence — for the top float-turnover "
    "       zones, rate confidence (high/medium/low) with bilingual "
    "       reason arrays explaining the weighting (holder quality, "
    "       valuation, gamma, turnover, insider activity).\n"
    "    Composite 2. fragility — single 0-100 score + rating "
    "       (low/medium/high/extreme) + bilingual drivers arrays "
    "       listing what makes the name fragile (narrative %, leverage, "
    "       crowding, option instability, liquidity thinness).\n"
    "    Composite 3. repricing_risk — directional probability "
    "       distribution: positive_pct, neutral_pct, negative_pct "
    "       (integers summing to 100) + note_en/note_zh.\n"
    "  Sources: Whalewisdom / Fintel for holder mix; SpotGamma / "
    "  Tier1Alpha / CBOE OI for gamma; FINRA SI; Iborrow / broker "
    "  pages for borrow; YCharts / Macrotrends for valuation history; "
    "  Zacks / Refinitiv pages on Yahoo Finance for revisions; "
    "  earnings whisper / options chain for implied moves. If any of "
    "  these aren't accessible, mark that section "
    "  confidence=\"unavailable\" and explain in confidence_note_*.\n"
    "- catalysts: dated events in the next ~90 days, sorted earliest "
    "  first. Earnings date, guidance updates, regulatory dates (FDA, "
    "  CFIUS, DOJ), conferences, product launches, legal milestones "
    "  (court rulings, settlements), ex-dividend dates, M&A votes. "
    "  Each one gets a type tag and your read on est_impact "
    "  (high/medium/low). Provide title_en/title_zh and "
    "  summary_en/summary_zh for every item.\n"
    "- trader_news: 3-5 items from the LAST 14 DAYS that meaningfully "
    "  moved the stock or are likely to. Provide headline_en/"
    "  headline_zh and summary_en/summary_zh for every item. Tag bias "
    "  (positive/negative/neutral). Always include a source_url.\n\n"
    "- research_overview: a second, non-duplicative group of cards for "
    "  fundamental / strategic context. Do NOT repeat price returns, "
    "  moving averages, analyst ratings, upcoming catalysts, or recent "
    "  news already covered by the trader cards. This section should be "
    "  better than a generic finance overview because it synthesizes "
    "  segment economics, quality, peers, scenarios, and diligence gaps "
    "  into visualizable facts. updated_at should be an ISO timestamp or "
    "  today's date. Every sub-object carries confidence + bilingual "
    "  confidence notes. Sub-objects:\n"
    "    1. business_mix — 3-6 revenue / profit pools or end markets. "
    "       Each segment gets name_en/name_zh, revenue_pct, growth_pct, "
    "       signal (growth_engine/cash_engine/drag/emerging/cyclical), "
    "       and note_en/note_zh explaining what makes it matter.\n"
    "    2. financial_quality — score 0-100 plus 4-6 metrics such as "
    "       gross margin, operating margin, FCF margin, R&D/revenue, "
    "       net cash/debt, ROIC, inventory turns, or SBC/revenue. Each "
    "       metric gets label_en/zh, value as a compact display string, "
    "       percentile (0-100, against peers or company history), "
    "       direction (strong/neutral/weak), and note_en/zh.\n"
    "    3. growth_durability — forward revenue/EPS/margin trajectory "
    "       by annual or quarterly horizon. Use consensus estimates and "
    "       official guidance when public. The thesis_en/zh should say "
    "       whether growth is compounding, normalizing, or at risk.\n"
    "    4. peer_context — 4-6 closest public peers with ticker, "
    "       company_en/company_zh, score 0-100, revenue growth, gross "
    "       margin, valuation premium/discount vs the peer set, and a "
    "       short note_en/zh. This powers a relative-quality scoreboard, "
    "       not another related-stocks list.\n"
    "    5. scenario_matrix — bear/base/bull cases with probability_pct, "
    "       implied_return_pct, label_en/zh, and key_driver_en/zh. These "
    "       are desk scenarios derived from consensus, valuation, and "
    "       thesis drivers, not sell-side target prices copied from the "
    "       sentiment card.\n"
    "    6. diligence_questions — 3-5 unresolved questions with "
    "       severity (watch/important/critical), why_it_matters_en/zh, "
    "       and evidence_gap_en/zh. Favor disconfirming evidence and "
    "       hard-to-answer questions over generic risks.\n"
    "  Suggested sources: latest 10-K/10-Q, earnings slides/transcript, "
    "  official IR KPI tables, segment notes, YCharts/Macrotrends, "
    "  Nasdaq/Yahoo financials, peer filings, and reputable current "
    "  market-data aggregators. Return null for specific numbers you "
    "  cannot verify; explain the sourcing gap in confidence_note_*.\n\n"
    "- tech_movers: the top 5-8 one-day movers among liquid public "
    "  technology stocks today. Include both sharp gainers and sharp "
    "  decliners when available. updated_at should be today's market "
    "  date or an ISO timestamp. For each mover, provide ticker, "
    "  company_en, company_zh, 1-day percent move, direction "
    "  (up/down/flat), and concise market_driver_en + market_driver_zh "
    "  explaining what moved it (earnings, guidance, analyst action, "
    "  product news, regulatory item, sector/AI/chip/software macro "
    "  flow, M&A, rates, etc.). Chinese fields must be usable UI copy, "
    "  not machine placeholders. If a company has no widely used Chinese "
    "  name, use a clear transliteration or the English name in "
    "  company_zh. Always include a source_url when publicly available. "
    "  This section is daily market context, not necessarily related to "
    "  the target company.\n\n"
    "- market_session: the target exchange's authoritative trading "
    "  calendar AS OF NOW. You already look up recent prices and dates — "
    "  use the same sources to report, in ISO 8601 WITH the "
    "  America/New_York UTC offset (e.g. 2026-05-15T16:00:00-04:00): "
    "  last_session_date + last_close (the most recent COMPLETED regular "
    "  session), next_session_date + next_open + next_close (the next "
    "  SCHEDULED regular session), is_open_now, and next_is_early_close "
    "  (true for 1:00pm ET half-days). Account for weekends, exchange "
    "  holidays, half-days, AND any unscheduled closures you find "
    "  (e.g. national day of mourning, weather). Clients measure "
    "  freshness in trading sessions from these, so they must be the "
    "  real session boundaries, not rule-of-thumb guesses. Set the "
    "  confidence triad; use confidence=`unavailable` with a reason "
    "  note if you cannot source the calendar.\n\n"
    "Return ONE JSON object matching the attached schema. No preamble, "
    "no markdown fences — just the JSON.\n\n"
    "STRICT-SCHEMA SELF-CHECK (do this before you emit the structured "
    "output): the output is validated in strict mode — if ANY estimated "
    "sub-object (especially every heat_card sub-object) is missing its "
    "`confidence`, `confidence_note_en`, or `confidence_note_zh`, the "
    "ENTIRE output is rejected and the whole run is wasted. Before "
    "emitting, walk every heat_card sub-object, every research_overview "
    "sub-object, AND market_session and "
    "confirm all three are present (use confidence=`unavailable` with a "
    "reason note rather than omitting them). Never drop the triad to "
    "save space."
)


# --- Parallel section passes ------------------------------------------------
#
# The top-level snapshot sections have ZERO data dependencies on each
# other (each sources its own web data). Generating them in one Claude run
# serializes independent research jobs behind one another. Instead we fan
# out one `claude -p` per section, run them concurrently, and merge — wall
# time ≈ the slowest section instead of the sum. Same idea as the memo
# skill's parallel passes. Each pass tags its progress events with a
# `thread` label so the Active-Jobs modal renders them as grouped
# sub-tasks (the composite view already exists).

_PRICE_FOCUS = (
    "FOCUS: produce ONLY the `price_card` object. Spend your effort getting "
    "change_pct_30d, vs_sector_30d_pct and vs_sp500_30d_pct right — fetch the "
    "Yahoo Finance history page and compute them per the price_card guidance "
    "above. Do not return null for these unless the history truly can't be "
    "fetched."
)

@dataclass(frozen=True)
class SnapshotPass:
    pass_id: str
    label: str
    keys: tuple[str, ...]
    focus: str = ""
    section_id: str | None = None
    overview_fields: tuple[str, ...] = ()

    @property
    def status_section_id(self) -> str:
        return self.section_id or self.keys[0]

    @property
    def artifact_section_id(self) -> str:
        return self.pass_id if self.overview_fields else self.status_section_id


_OVERVIEW_BUSINESS_FOCUS = (
    "FOCUS: produce ONLY `research_overview` with `updated_at` and "
    "`business_mix`. Cover business model, segment exposure, geography, "
    "and the revenue/growth signal by segment. Do not produce the other "
    "research_overview sub-objects."
)

_OVERVIEW_FINANCIALS_FOCUS = (
    "FOCUS: produce ONLY `research_overview` with `updated_at`, "
    "`financial_quality`, `growth_durability`, and `peer_context`. Cover "
    "revenue/profit trend, margin quality, balance sheet or dilution/debt "
    "where relevant, and the closest public peer context. Do not produce "
    "business_mix, scenario_matrix, or diligence_questions."
)

_OVERVIEW_THESIS_FOCUS = (
    "FOCUS: produce ONLY `research_overview` with `updated_at` and "
    "`scenario_matrix`. Build a compact bull/base/bear trader setup: what "
    "must happen next, implied return, and the key driver for each case. "
    "Do not produce the other research_overview sub-objects."
)

_OVERVIEW_QUESTIONS_FOCUS = (
    "FOCUS: produce ONLY `research_overview` with `updated_at` and "
    "`diligence_questions`. Emphasize key downside risks, uncertainty, "
    "evidence gaps, and unresolved diligence questions. Do not produce the "
    "other research_overview sub-objects."
)


# Passes are smaller than top-level cards when a section has been split.
# `research_overview` intentionally fans out into focused sub-passes and
# merges back into the existing snapshot schema, so clients do not need a
# schema migration for the reliability improvement.
SNAPSHOT_PASSES: list[SnapshotPass] = [
    SnapshotPass("price", "Price & returns", ("price_card",), _PRICE_FOCUS),
    SnapshotPass("momentum", "Momentum", ("momentum_card",)),
    SnapshotPass("sentiment", "Analyst sentiment", ("sentiment_card",)),
    SnapshotPass("heat", "Positioning structure", ("heat_card",)),
    SnapshotPass("catalysts", "Upcoming catalysts", ("catalysts",)),
    SnapshotPass("news", "Trader news", ("trader_news",)),
    SnapshotPass(
        "overview_business",
        "Research overview: business",
        ("research_overview",),
        _OVERVIEW_BUSINESS_FOCUS,
        section_id="research_overview",
        overview_fields=("updated_at", "business_mix"),
    ),
    SnapshotPass(
        "overview_financials",
        "Research overview: financials",
        ("research_overview",),
        _OVERVIEW_FINANCIALS_FOCUS,
        section_id="research_overview",
        overview_fields=(
            "updated_at",
            "financial_quality",
            "growth_durability",
            "peer_context",
        ),
    ),
    SnapshotPass(
        "overview_thesis",
        "Research overview: thesis",
        ("research_overview",),
        _OVERVIEW_THESIS_FOCUS,
        section_id="research_overview",
        overview_fields=("updated_at", "scenario_matrix"),
    ),
    SnapshotPass(
        "overview_questions",
        "Research overview: risks",
        ("research_overview",),
        _OVERVIEW_QUESTIONS_FOCUS,
        section_id="research_overview",
        overview_fields=("updated_at", "diligence_questions"),
    ),
    SnapshotPass("session", "Market session", ("market_session",)),
    SnapshotPass("movers", "Tech movers", ("tech_movers",)),
]

_PASSES_BY_SECTION: dict[str, list[SnapshotPass]] = {}
for _pass in SNAPSHOT_PASSES:
    _PASSES_BY_SECTION.setdefault(_pass.status_section_id, []).append(_pass)

# Safe placeholders for a section whose pass failed, so consumers
# (frontend optional-chaining, bilingual fill, schema-version stamp) keep
# working with partial results instead of crashing.
_EMPTY_SECTION: dict[str, Any] = {
    "price_card": {},
    "momentum_card": {},
    "sentiment_card": {},
    "heat_card": {},
    "catalysts": [],
    "trader_news": [],
    "research_overview": None,
    "market_session": None,
    "tech_movers": {"updated_at": None, "movers": []},
}


def _sub_schema(keys: tuple[str, ...] | list[str]) -> dict:
    """A schema that accepts only the given top-level section keys."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: copy.deepcopy(SCHEMA["properties"][k]) for k in keys},
        "required": list(keys),
    }


def _overview_sub_schema(fields: tuple[str, ...]) -> dict:
    overview = copy.deepcopy(SCHEMA["properties"]["research_overview"])
    overview["properties"] = {
        key: overview["properties"][key]
        for key in fields
        if key in overview["properties"]
    }
    overview["required"] = list(fields)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"research_overview": overview},
        "required": ["research_overview"],
    }


def _schema_for_pass(spec: SnapshotPass) -> dict:
    if spec.overview_fields:
        return _overview_sub_schema(spec.overview_fields)
    return _sub_schema(spec.keys)


_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "").strip()))
        except ValueError:
            return 0
    return 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return 0.0
    return 0.0


def _blank_usage() -> dict[str, Any]:
    usage = {field: 0 for field in _TOKEN_FIELDS}
    usage.update({
        "total_tokens": 0,
        "server_tool_use": {},
    })
    return usage


def _usage_summary(usage: Any) -> dict[str, Any]:
    totals = _blank_usage()
    if not isinstance(usage, dict):
        return totals
    for field in _TOKEN_FIELDS:
        totals[field] += _as_int(usage.get(field))
    server_tools = usage.get("server_tool_use")
    if isinstance(server_tools, dict):
        for key, value in server_tools.items():
            count = _as_int(value)
            if count:
                totals["server_tool_use"][key] = (
                    totals["server_tool_use"].get(key, 0) + count
                )
    if not any(totals[field] for field in _TOKEN_FIELDS):
        for iteration in usage.get("iterations") or []:
            if not isinstance(iteration, dict):
                continue
            for field in _TOKEN_FIELDS:
                totals[field] += _as_int(iteration.get(field))
    totals["total_tokens"] = sum(totals[field] for field in _TOKEN_FIELDS)
    return totals


def _add_usage(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for field in _TOKEN_FIELDS:
        dst[field] = _as_int(dst.get(field)) + _as_int(src.get(field))
    dst["total_tokens"] = _as_int(dst.get("total_tokens")) + _as_int(
        src.get("total_tokens")
    )
    server_tool_use = dst.setdefault("server_tool_use", {})
    for key, count in (src.get("server_tool_use") or {}).items():
        server_tool_use[key] = _as_int(server_tool_use.get(key)) + _as_int(count)


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", (value or "").strip())
    return cleaned.strip("-") or "unknown"


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _input_hash(company: dict, section_id: str) -> str:
    payload = {
        "schema_version": TRADER_SNAPSHOT_SCHEMA_VERSION,
        "section_id": section_id,
        "company_id": company.get("id"),
        "name": company.get("name"),
        "ticker": company.get("ticker"),
        "exchange": company.get("exchange"),
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()[:16]


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _section_artifact_dir(company_id: str) -> Path:
    path = storage.DATA_DIR / "_trader_sections" / _safe_id(company_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def section_artifact_path(company_id: str, section_id: str) -> Path:
    return _section_artifact_dir(company_id) / f"{_safe_id(section_id)}.json"


def _read_section_artifact(company_id: str, section_id: str) -> dict | None:
    path = section_artifact_path(company_id, section_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to read trader section artifact: %s", path)
        return None
    return data if isinstance(data, dict) else None


def _write_section_artifact(
    company_id: str,
    section_id: str,
    artifact: dict,
) -> None:
    path = section_artifact_path(company_id, section_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8",
    )
    tmp.replace(path)


def _artifact_is_fresh(
    artifact: dict,
    *,
    input_hash: str,
    ttl_seconds: int,
) -> bool:
    if artifact.get("status") != "fresh":
        return False
    if artifact.get("input_hash") != input_hash:
        return False
    finished = _parse_iso(artifact.get("finished_at"))
    if finished is None:
        return False
    age = (datetime.now(timezone.utc) - finished).total_seconds()
    return age <= ttl_seconds


def _has_section_data(section_id: str, value: Any) -> bool:
    if value is None:
        return False
    if section_id == "tech_movers":
        return isinstance(value, dict) and bool(value.get("movers"))
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return True


def _section_status_template(
    section_id: str,
    *,
    status: str,
    attempted_at: str | None = None,
    successful_at: str | None = None,
    error: str | None = None,
    retryable: bool = True,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "label": SECTION_LABELS.get(section_id, section_id),
        "status": status,
        "last_successful_at": successful_at,
        "last_attempted_at": attempted_at,
        "last_error": error,
        "retryable": retryable,
        "source_run_id": source_run_id,
    }


def _previous_section_status(
    previous_snapshot: dict | None,
    section_id: str,
) -> dict[str, Any]:
    if not isinstance(previous_snapshot, dict):
        return {}
    status_map = previous_snapshot.get(SECTION_STATUS_KEY)
    if not isinstance(status_map, dict):
        return {}
    status = status_map.get(section_id)
    return copy.deepcopy(status) if isinstance(status, dict) else {}


def ensure_section_status(
    snapshot: dict,
    *,
    previous_snapshot: dict | None = None,
    source_run_id: str | None = None,
) -> dict:
    """Ensure every saved snapshot has first-class section state.

    Older tests and any fallback generator stubs may still return only the
    card data. This normalizes that output before persistence.
    """
    if not isinstance(snapshot, dict):
        return snapshot
    existing = snapshot.get(SECTION_STATUS_KEY)
    if not isinstance(existing, dict):
        existing = {}
    now = snapshot.get("refreshed_at") or _now()
    normalized: dict[str, dict] = {}
    for section_id in SECTION_KEYS:
        current = existing.get(section_id)
        if isinstance(current, dict) and current.get("status"):
            row = copy.deepcopy(current)
            row.setdefault("section_id", section_id)
            row.setdefault("label", SECTION_LABELS.get(section_id, section_id))
            row.setdefault("retryable", True)
            normalized[section_id] = row
            continue
        value = snapshot.get(section_id)
        previous = _previous_section_status(previous_snapshot, section_id)
        if _has_section_data(section_id, value):
            successful_at = previous.get("last_successful_at") or now
            normalized[section_id] = _section_status_template(
                section_id,
                status="fresh",
                attempted_at=now,
                successful_at=successful_at,
                retryable=True,
                source_run_id=source_run_id,
            )
        else:
            normalized[section_id] = _section_status_template(
                section_id,
                status="empty",
                attempted_at=now,
                successful_at=previous.get("last_successful_at"),
                error=previous.get("last_error"),
                retryable=True,
                source_run_id=source_run_id,
            )
    snapshot[SECTION_STATUS_KEY] = normalized
    return snapshot


def normalize_section_ids(sections: list[str] | tuple[str, ...] | None) -> list[str]:
    aliases = {
        "price": "price_card",
        "momentum": "momentum_card",
        "sentiment": "sentiment_card",
        "heat": "heat_card",
        "positioning": "heat_card",
        "news": "trader_news",
        "overview": "research_overview",
        "session": "market_session",
        "movers": "tech_movers",
    }
    out: list[str] = []
    for raw in sections or []:
        key = str(raw or "").strip().lower().replace("-", "_")
        key = aliases.get(key, key)
        if key in SECTION_KEYS and key not in out:
            out.append(key)
    return out


class _ThreadProgress:
    """Wraps a ProgressLog so every emit from one parallel pass carries a
    stable `thread` label — that's what makes the JobLogModal group the
    passes into collapsible sections (composite view)."""

    def __init__(self, base, thread: str):
        self._base = base
        self._thread = thread
        self.cost_usd = 0.0
        self.duration_ms = 0
        self.token_usage = _blank_usage()

    def emit(self, type_: str, **fields: Any) -> None:
        fields.setdefault("thread", self._thread)
        if type_ == "claude_action" and fields.get("action") == "result":
            usage = _usage_summary(fields.get("usage"))
            _add_usage(self.token_usage, usage)
            self.cost_usd += _as_float(fields.get("cost_usd"))
            self.duration_ms += _as_int(fields.get("duration_ms"))
        self._base.emit(type_, **fields)

    @property
    def is_terminated(self) -> bool:
        try:
            return self._base.is_terminated
        except Exception:  # noqa: BLE001
            return False


@dataclass
class _PassResult:
    spec: SnapshotPass
    part: dict | None
    error: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    cost_usd: float
    token_usage: dict[str, Any]
    input_hash: str
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return isinstance(self.part, dict) and not self.error


def _run_snapshot_pass(
    *,
    company: dict,
    spec: SnapshotPass,
    progress,
    global_semaphore=None,
) -> _PassResult:
    name = company.get("name") or company.get("id") or "Unknown"
    ticker = company.get("ticker") or ""
    exchange = company.get("exchange") or ""
    started_monotonic = time.monotonic()
    started_at = _now()
    input_hash = _input_hash(company, spec.artifact_section_id)
    sub_progress = (
        _ThreadProgress(progress, spec.label) if progress is not None else None
    )
    if sub_progress is not None:
        sub_progress.emit(
            "thread_started",
            title=spec.label,
            section_id=spec.status_section_id,
            pass_id=spec.pass_id,
        )
    focus_hint = (
        spec.focus
        or (
            f"FOCUS: produce ONLY the following top-level field(s): "
            f"{', '.join(spec.keys)}. Output a JSON object containing exactly "
            f"those key(s) and nothing else, matching the schema."
        )
    )
    try:
        if global_semaphore is not None:
            global_semaphore.acquire()
        try:
            part, err = claude_runner.run_public_company_snapshot(
                company_name=name,
                ticker=ticker,
                exchange=exchange,
                schema=_schema_for_pass(spec),
                system_prompt=SYSTEM_PROMPT,
                progress=sub_progress,
                focus_hint=focus_hint,
            )
        finally:
            if global_semaphore is not None:
                global_semaphore.release()
    except Exception as exc:  # noqa: BLE001
        logger.exception("snapshot pass %s crashed", spec.pass_id)
        part, err = None, f"{type(exc).__name__}: {exc}"
    finished_at = _now()
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    if sub_progress is not None:
        sub_progress.emit(
            "thread_finished" if (part and not err) else "thread_failed",
            error=err or None,
            section_id=spec.status_section_id,
            pass_id=spec.pass_id,
            duration_ms=duration_ms,
        )
    return _PassResult(
        spec=spec,
        part=part if isinstance(part, dict) else None,
        error=err,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        cost_usd=round(float(getattr(sub_progress, "cost_usd", 0.0)), 6),
        token_usage=copy.deepcopy(
            getattr(sub_progress, "token_usage", _blank_usage())
        ),
        input_hash=input_hash,
    )


def _cached_pass_result(
    *,
    company: dict,
    spec: SnapshotPass,
    progress,
) -> _PassResult | None:
    company_id = str(company.get("id") or company.get("ticker") or "unknown")
    input_hash = _input_hash(company, spec.artifact_section_id)
    artifact = _read_section_artifact(company_id, spec.artifact_section_id)
    ttl = SECTION_TTL_SECONDS.get(spec.status_section_id, 60 * 60)
    if not artifact or not _artifact_is_fresh(
        artifact, input_hash=input_hash, ttl_seconds=ttl,
    ):
        return None
    now = _now()
    if progress is not None:
        progress.emit(
            "thread_started",
            thread=spec.label,
            title=spec.label,
            section_id=spec.status_section_id,
            pass_id=spec.pass_id,
            cached=True,
        )
        progress.emit(
            "thread_finished",
            thread=spec.label,
            section_id=spec.status_section_id,
            pass_id=spec.pass_id,
            cached=True,
        )
    return _PassResult(
        spec=spec,
        part=copy.deepcopy(artifact.get("data"))
        if isinstance(artifact.get("data"), dict)
        else None,
        error=None,
        started_at=artifact.get("started_at") or now,
        finished_at=artifact.get("finished_at") or now,
        duration_ms=_as_int(artifact.get("duration_ms")),
        cost_usd=_as_float(artifact.get("cost_usd")),
        token_usage=artifact.get("token_usage")
        if isinstance(artifact.get("token_usage"), dict)
        else _blank_usage(),
        input_hash=input_hash,
        from_cache=True,
    )


def _artifact_from_result(company: dict, result: _PassResult) -> dict:
    company_id = str(company.get("id") or company.get("ticker") or "unknown")
    return {
        "company_id": company_id,
        "section_id": result.spec.artifact_section_id,
        "logical_section_id": result.spec.status_section_id,
        "schema_version": SECTION_ARTIFACT_SCHEMA_VERSION,
        "snapshot_schema_version": TRADER_SNAPSHOT_SCHEMA_VERSION,
        "input_hash": result.input_hash,
        "status": "fresh" if result.ok else "failed",
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_ms": result.duration_ms,
        "cost_usd": round(float(result.cost_usd or 0.0), 6),
        "token_usage": result.token_usage,
        "error": result.error,
        "data": result.part,
    }


def _persist_pass_artifact(company: dict, result: _PassResult) -> None:
    if result.from_cache:
        return
    company_id = str(company.get("id") or company.get("ticker") or "unknown")
    try:
        _write_section_artifact(
            company_id,
            result.spec.artifact_section_id,
            _artifact_from_result(company, result),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to write trader section artifact for %s/%s",
            company_id,
            result.spec.artifact_section_id,
        )


def _set_section_data(snapshot: dict, section_id: str, value: Any) -> None:
    snapshot[section_id] = copy.deepcopy(value)


def _merge_overview_parts(results: list[_PassResult]) -> dict | None:
    merged: dict[str, Any] = {}
    for result in results:
        if not result.ok:
            continue
        overview = (
            result.part.get("research_overview")
            if isinstance(result.part, dict)
            else None
        )
        if not isinstance(overview, dict):
            continue
        for key, value in overview.items():
            if value is not None:
                merged[key] = value
    if not merged:
        return None
    merged.setdefault("updated_at", _now())
    for key in (
        "business_mix",
        "financial_quality",
        "growth_durability",
        "peer_context",
        "scenario_matrix",
        "diligence_questions",
    ):
        merged.setdefault(key, None)
    return merged


def _merge_results(
    *,
    company: dict,
    results: list[_PassResult],
    previous_snapshot: dict | None,
    requested_sections: list[str],
    preserve_existing_sections: bool,
    source_run_id: str,
) -> dict:
    previous = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    snapshot = copy.deepcopy(previous) if preserve_existing_sections else {}
    status_map: dict[str, dict] = {}
    previous_status = (
        previous.get(SECTION_STATUS_KEY)
        if isinstance(previous.get(SECTION_STATUS_KEY), dict)
        else {}
    )

    by_section: dict[str, list[_PassResult]] = {}
    for result in results:
        by_section.setdefault(result.spec.status_section_id, []).append(result)

    now = _now()
    for section_id in SECTION_KEYS:
        prev_status = (
            copy.deepcopy(previous_status.get(section_id))
            if isinstance(previous_status, dict)
            and isinstance(previous_status.get(section_id), dict)
            else {}
        )
        if section_id not in requested_sections:
            if prev_status:
                status_map[section_id] = prev_status
            elif _has_section_data(section_id, snapshot.get(section_id)):
                status_map[section_id] = _section_status_template(
                    section_id,
                    status="fresh",
                    attempted_at=previous.get("refreshed_at"),
                    successful_at=previous.get("refreshed_at"),
                    source_run_id=prev_status.get("source_run_id"),
                )
            else:
                status_map[section_id] = _section_status_template(
                    section_id,
                    status="empty",
                    attempted_at=None,
                    successful_at=None,
                    retryable=True,
                )
            continue

        section_results = by_section.get(section_id, [])
        errors = [r.error for r in section_results if r.error]
        attempted_at = max((r.finished_at for r in section_results), default=now)
        successful_results = [r for r in section_results if r.ok]
        value: Any = None
        if section_id == "research_overview":
            value = _merge_overview_parts(section_results)
        else:
            for result in successful_results:
                if isinstance(result.part, dict) and section_id in result.part:
                    value = result.part.get(section_id)
                    break

        has_new_data = _has_section_data(section_id, value)
        had_previous_data = _has_section_data(section_id, previous.get(section_id))
        if has_new_data and not errors:
            _set_section_data(snapshot, section_id, value)
            status_map[section_id] = _section_status_template(
                section_id,
                status="fresh",
                attempted_at=attempted_at,
                successful_at=attempted_at,
                retryable=True,
                source_run_id=source_run_id,
            )
        elif has_new_data and errors:
            _set_section_data(snapshot, section_id, value)
            status_map[section_id] = _section_status_template(
                section_id,
                status="stale",
                attempted_at=attempted_at,
                successful_at=attempted_at,
                error=" | ".join(str(e) for e in errors if e)[:500],
                retryable=True,
                source_run_id=source_run_id,
            )
        elif had_previous_data and preserve_existing_sections:
            _set_section_data(snapshot, section_id, previous.get(section_id))
            status_map[section_id] = _section_status_template(
                section_id,
                status="stale",
                attempted_at=attempted_at,
                successful_at=(
                    prev_status.get("last_successful_at")
                    or previous.get("refreshed_at")
                ),
                error=" | ".join(str(e) for e in errors if e)[:500]
                or "section returned no data",
                retryable=True,
                source_run_id=source_run_id,
            )
        else:
            _set_section_data(snapshot, section_id, _EMPTY_SECTION[section_id])
            status_map[section_id] = _section_status_template(
                section_id,
                status="failed" if errors else "empty",
                attempted_at=attempted_at,
                successful_at=prev_status.get("last_successful_at"),
                error=" | ".join(str(e) for e in errors if e)[:500]
                or "section returned no data",
                retryable=True,
                source_run_id=source_run_id,
            )

    snapshot[SECTION_STATUS_KEY] = status_map
    for section_id in SECTION_KEYS:
        snapshot.setdefault(section_id, copy.deepcopy(_EMPTY_SECTION[section_id]))
    return snapshot


def generate_snapshot(
    *,
    company: dict,
    progress=None,
    previous_snapshot: dict | None = None,
    section_ids: list[str] | tuple[str, ...] | None = None,
    force: bool = False,
    preserve_existing_sections: bool = True,
    max_workers: int | None = None,
    global_semaphore=None,
) -> tuple[dict | None, str | None]:
    """Produce a fresh trader snapshot by fanning the sections out
    into concurrent ``claude -p`` runs and merging. Returns
    ``(snapshot, error)`` — ``error`` is None if at least one section
    came back; a section whose pass failed is filled with a safe empty
    placeholder so partial snapshots still render.
    """
    name = company.get("name") or company.get("id") or "Unknown"
    ticker = company.get("ticker") or ""
    exchange = company.get("exchange") or ""

    if not ticker:
        return None, (
            "Refusing to generate a trader snapshot for a company with "
            "no ticker. The bucketing rule should have routed this to "
            "private — investigate why company_type == 'public' here."
        )

    if not claude_runner.is_available():
        return None, (
            "Claude Code CLI not installed; install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    requested_sections = normalize_section_ids(section_ids)
    if not requested_sections:
        requested_sections = list(SECTION_KEYS)
    pass_specs = [
        spec
        for section_id in requested_sections
        for spec in _PASSES_BY_SECTION.get(section_id, [])
    ]
    source_run_id = f"{company.get('id') or ticker}:{_now()}"

    if progress is not None:
        progress.emit(
            "stage",
            stage="parallel_dispatch",
            message=(
                f"Gathering {len(pass_specs)} section pass(es) in parallel"
            ),
            passes=[p.label for p in pass_specs],
            sections=requested_sections,
        )

    def _run_or_reuse(spec: SnapshotPass) -> _PassResult:
        if not force:
            cached = _cached_pass_result(
                company=company,
                spec=spec,
                progress=progress,
            )
            if cached is not None:
                return cached
        result = _run_snapshot_pass(
            company=company,
            spec=spec,
            progress=progress,
            global_semaphore=global_semaphore,
        )
        _persist_pass_artifact(company, result)
        return result

    worker_count = max(1, min(max_workers or len(pass_specs), len(pass_specs)))
    results: list[_PassResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for result in pool.map(_run_or_reuse, pass_specs):
            results.append(result)

    merged = _merge_results(
        company=company,
        results=results,
        previous_snapshot=previous_snapshot,
        requested_sections=requested_sections,
        preserve_existing_sections=preserve_existing_sections,
        source_run_id=source_run_id,
    )
    errors = [
        f"{result.spec.pass_id}: {result.error}"
        for result in results
        if result.error
    ]

    # Persist a top-level artifact for split sections so retry/status
    # consumers can still inspect `research_overview.json` directly.
    for section_id in requested_sections:
        if section_id == "research_overview":
            status = merged.get(SECTION_STATUS_KEY, {}).get(section_id, {})
            section_results = [
                r for r in results if r.spec.status_section_id == section_id
            ]
            artifact = {
                "company_id": str(company.get("id") or ticker or "unknown"),
                "section_id": section_id,
                "logical_section_id": section_id,
                "schema_version": SECTION_ARTIFACT_SCHEMA_VERSION,
                "snapshot_schema_version": TRADER_SNAPSHOT_SCHEMA_VERSION,
                "input_hash": _input_hash(company, section_id),
                "status": status.get("status") if isinstance(status, dict) else None,
                "started_at": min(
                    (r.started_at for r in section_results),
                    default=_now(),
                ),
                "finished_at": max(
                    (r.finished_at for r in section_results),
                    default=_now(),
                ),
                "duration_ms": sum(r.duration_ms for r in section_results),
                "cost_usd": round(
                    sum(r.cost_usd for r in section_results),
                    6,
                ),
                "token_usage": _blank_usage(),
                "error": status.get("last_error") if isinstance(status, dict) else None,
                "data": {"research_overview": merged.get("research_overview")},
            }
            for result in section_results:
                _add_usage(artifact["token_usage"], result.token_usage)
            try:
                _write_section_artifact(
                    str(company.get("id") or ticker or "unknown"),
                    section_id,
                    artifact,
                )
            except Exception:  # noqa: BLE001
                logger.exception("failed to write merged research overview artifact")

    got_any = any(
        _has_section_data(k, merged.get(k))
        for k in SECTION_KEYS
    )
    if not got_any:
        return None, (
            "All snapshot sections failed. "
            + (" | ".join(errors[:7]) if errors else "no data returned")
        )

    if errors and progress is not None:
        progress.emit(
            "stage",
            stage="partial_snapshot",
            message=f"{len(errors)} section(s) failed; returning partial",
        )
    return merged, None
