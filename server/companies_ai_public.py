"""Public-company trader snapshot — the schema + system prompt used to
populate ``company.trader_snapshot`` for public companies.

Companion to ``companies_ai.py`` (which does dossier-style search for
ALL companies). This module is invoked only when an existing company's
``company_type == "public"`` and the user clicks Refresh.

See docs/public-company-trader-view.md §3 for the on-disk shape and §4
for the pipeline.
"""
from __future__ import annotations

import logging
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

        "heat_card": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rel_volume_20d": _NUM_NULL,
                "iv_30d_pct": _NUM_NULL,
                "iv_percentile_1y": _INT_NULL,
                "options_skew": {
                    "type": ["string", "null"],
                    "enum": ["call_bid", "balanced", "put_bid", None],
                },
                "news_flow_24h": _INT_NULL,
                "insider_activity_30d": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "buys": _INT_NULL,
                        "sells": _INT_NULL,
                        "net_share_count_change": _INT_NULL,
                    },
                    "required": ["buys", "sells", "net_share_count_change"],
                },
                "short_interest_pct_float": _NUM_NULL,
                "days_to_cover": _NUM_NULL,
                "social_mentions_trend": {
                    "type": ["string", "null"],
                    "enum": ["rising", "flat", "falling", None],
                },
            },
            "required": [
                "rel_volume_20d", "iv_30d_pct", "iv_percentile_1y",
                "options_skew", "news_flow_24h", "insider_activity_30d",
                "short_interest_pct_float", "days_to_cover",
                "social_mentions_trend",
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
    "BILINGUAL OUTPUT — every prose field in this schema has paired "
    "`_en` (English) and `_zh` (Simplified Chinese) siblings. Populate "
    "BOTH for every item. The Chinese version is a faithful translation "
    "of the same fact, not a different summary, not a transliteration of "
    "English words. Use natural trader/finance Chinese (e.g. "
    "'看涨'/'看跌'/'中性' for trend, '强力买入'/'买入'/'持有'/'卖出'/"
    "'强力卖出' for ratings, '上调'/'下调'/'首次覆盖'/'重申' for rating "
    "actions, '财报'/'指引'/'监管'/'会议'/'产品'/'法律'/'分红' for "
    "catalyst types). Keep tickers, firm names, and product codes in "
    "Latin script in both languages. If a field is genuinely unknown, "
    "return null in BOTH `_en` and `_zh` (don't fabricate a translation "
    "of nothing). Legacy single-language fields (`trend`, "
    "`breakout_signals`, `analyst_consensus`, `title`, `summary`, "
    "`headline`, and `recent_rating_changes[*].action/from/to`) should "
    "carry the same content as the `_en` variant for back-compat with "
    "consumers that haven't been updated yet.\n\n"
    "Per-card guidance:\n"
    "- price_card: last close + percent returns vs prior day, 5 trading "
    "  days, 30 calendar days, year-to-date, and trailing 12 months, "
    "  plus the 30-day return relative to a sector ETF and to the S&P "
    "  500. Currency is the listing currency (USD for US, etc.).\n"
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
    "- heat_card: relative volume vs 20-day average, 30-day implied "
    "  volatility (percent), 1-year IV percentile, options skew "
    "  direction (call_bid / balanced / put_bid), news-item count in "
    "  the last 24 hours, insider 30-day activity (buys, sells, net "
    "  share-count change), short-interest as percent of float, days-"
    "  to-cover, and qualitative social-mention trend.\n"
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
    "Return ONE JSON object matching the attached schema. No preamble, "
    "no markdown fences — just the JSON."
)


def generate_snapshot(
    *, company: dict, progress=None
) -> tuple[dict | None, str | None]:
    """Spawn ``claude -p`` to produce a fresh trader snapshot for one
    public company. Returns ``(snapshot, error)`` — on success ``error``
    is None.
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

    snapshot, err = claude_runner.run_public_company_snapshot(
        company_name=name,
        ticker=ticker,
        exchange=exchange,
        schema=SCHEMA,
        system_prompt=SYSTEM_PROMPT,
        progress=progress,
    )
    return snapshot, err
