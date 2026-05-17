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
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import claude_runner

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


# Current trader_snapshot.schema_version. Bumped when a breaking
# heat_card / structural change lands. The server's startup migration
# strips snapshots older than this; the worker stamps the current
# value on every fresh snapshot it writes. See docs/heat-card-v2.md §6.
TRADER_SNAPSHOT_SCHEMA_VERSION: int = 2


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
        "market_session",
        "tech_movers",
    ],
}


SYSTEM_PROMPT = (
    "You are a sell-side trader's research desk. Given a publicly-traded "
    "company (ticker + name), produce a JSON snapshot covering price "
    "action, momentum, sentiment, heat, upcoming catalysts, and "
    "trader-relevant news.\n\n"
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
    "emitting, walk every heat_card sub-object AND market_session and "
    "confirm all three are present (use confidence=`unavailable` with a "
    "reason note rather than omitting them). Never drop the triad to "
    "save space."
)


# --- Parallel section passes ------------------------------------------------
#
# The seven top-level snapshot sections have ZERO data dependencies on each
# other (each sources its own web data). Generating them in one Claude run
# serializes ~7 independent research jobs behind one another. Instead we fan
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

# pass_id, thread label, [top-level schema keys], focus hint
SNAPSHOT_PASSES: list[tuple[str, str, list[str], str]] = [
    ("price", "Price & returns", ["price_card"], _PRICE_FOCUS),
    ("momentum", "Momentum", ["momentum_card"], ""),
    ("sentiment", "Analyst sentiment", ["sentiment_card"], ""),
    ("heat", "Positioning structure", ["heat_card"], ""),
    ("catalysts", "Upcoming catalysts", ["catalysts"], ""),
    ("news", "Trader news", ["trader_news"], ""),
    ("movers", "Tech movers", ["tech_movers"], ""),
]

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
    "tech_movers": {"updated_at": None, "movers": []},
}


def _sub_schema(keys: list[str]) -> dict:
    """A schema that accepts only the given top-level section keys."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: copy.deepcopy(SCHEMA["properties"][k]) for k in keys},
        "required": list(keys),
    }


class _ThreadProgress:
    """Wraps a ProgressLog so every emit from one parallel pass carries a
    stable `thread` label — that's what makes the JobLogModal group the
    passes into collapsible sections (composite view)."""

    def __init__(self, base, thread: str):
        self._base = base
        self._thread = thread

    def emit(self, type_: str, **fields: Any) -> None:
        fields.setdefault("thread", self._thread)
        self._base.emit(type_, **fields)

    @property
    def is_terminated(self) -> bool:
        try:
            return self._base.is_terminated
        except Exception:  # noqa: BLE001
            return False


def generate_snapshot(
    *, company: dict, progress=None
) -> tuple[dict | None, str | None]:
    """Produce a fresh trader snapshot by fanning the seven sections out
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

    if progress is not None:
        progress.emit(
            "stage",
            stage="parallel_dispatch",
            message=(
                f"Gathering {len(SNAPSHOT_PASSES)} sections in parallel"
            ),
            passes=[p[1] for p in SNAPSHOT_PASSES],
        )

    def _run_pass(spec: tuple[str, str, list[str], str]):
        pass_id, label, keys, focus = spec
        sub_progress = (
            _ThreadProgress(progress, label) if progress is not None else None
        )
        if sub_progress is not None:
            sub_progress.emit("thread_started", title=label)
        focus_hint = (
            focus
            or (
                f"FOCUS: produce ONLY the following top-level field(s): "
                f"{', '.join(keys)}. Output a JSON object containing exactly "
                f"those key(s) and nothing else, matching the schema."
            )
        )
        try:
            part, err = claude_runner.run_public_company_snapshot(
                company_name=name,
                ticker=ticker,
                exchange=exchange,
                schema=_sub_schema(keys),
                system_prompt=SYSTEM_PROMPT,
                progress=sub_progress,
                focus_hint=focus_hint,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("snapshot pass %s crashed", pass_id)
            part, err = None, f"{type(exc).__name__}: {exc}"
        if sub_progress is not None:
            sub_progress.emit(
                "thread_finished" if (part and not err) else "thread_failed",
                error=err or None,
            )
        return pass_id, keys, part, err

    merged: dict[str, Any] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(SNAPSHOT_PASSES)) as pool:
        for pass_id, keys, part, err in pool.map(_run_pass, SNAPSHOT_PASSES):
            for k in keys:
                if isinstance(part, dict) and k in part and part[k] is not None:
                    merged[k] = part[k]
                else:
                    merged[k] = copy.deepcopy(_EMPTY_SECTION[k])
                    if err:
                        errors.append(f"{pass_id}: {err}")

    got_any = any(
        merged.get(k) not in (None, {}, [], _EMPTY_SECTION.get(k))
        for k in _EMPTY_SECTION
    )
    if not got_any:
        return None, (
            "All snapshot sections failed. "
            + " | ".join(errors[:7]) if errors else "no data returned"
        )

    if errors and progress is not None:
        progress.emit(
            "stage",
            stage="partial_snapshot",
            message=f"{len(errors)} section(s) failed; returning partial",
        )
    return merged, None
