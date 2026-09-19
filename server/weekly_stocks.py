"""Weekly hot-stock dashboard research prompt, schema, and cache."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import ai_engine, claude_runner, storage
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

WEEKLY_DIR: Path = storage.DATA_DIR / "_weekly_stocks"
SUMMARY_PATH: Path = WEEKLY_DIR / "summary.json"
PROGRESS_PATH: Path = WEEKLY_DIR / "weekly_summary.progress.jsonl"
DRAFT_PATH: Path = WEEKLY_DIR / "weekly_summary.draft.json"

_STR_NULL = {"type": ["string", "null"]}
_NUM_NULL = {"type": ["number", "null"]}
_INT_NULL = {"type": ["integer", "null"]}


SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "label_en": {"type": "string"},
        "label_zh": {"type": "string"},
        "url": _STR_NULL,
        "date": _STR_NULL,
    },
    "required": ["label", "label_en", "label_zh", "url", "date"],
}

FAST_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "url": _STR_NULL,
        "date": _STR_NULL,
    },
    "required": ["label", "url", "date"],
}

WEEKLY_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "week_label": {"type": "string"},
        "week_label_en": {"type": "string"},
        "week_label_zh": {"type": "string"},
        "as_of": {"type": "string"},
        "market_pulse": {"type": "string"},
        "market_pulse_en": {"type": "string"},
        "market_pulse_zh": {"type": "string"},
        "benchmark_context": {"type": "string"},
        "benchmark_context_en": {"type": "string"},
        "benchmark_context_zh": {"type": "string"},
        "methodology": {"type": "string"},
        "methodology_en": {"type": "string"},
        "methodology_zh": {"type": "string"},
        "summary_cards": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "label_en": {"type": "string"},
                    "label_zh": {"type": "string"},
                    "value": {"type": "string"},
                    "note": {"type": "string"},
                    "note_en": {"type": "string"},
                    "note_zh": {"type": "string"},
                },
                "required": [
                    "label",
                    "label_en",
                    "label_zh",
                    "value",
                    "note",
                    "note_en",
                    "note_zh",
                ],
            },
        },
        "sector_mix": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sector": {"type": "string"},
                    "sector_en": {"type": "string"},
                    "sector_zh": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["sector", "sector_en", "sector_zh", "count"],
            },
        },
        "stocks": {
            "type": "array",
            "minItems": 5,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rank": {"type": "integer"},
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "exchange": _STR_NULL,
                    "sector": _STR_NULL,
                    "sector_en": _STR_NULL,
                    "sector_zh": _STR_NULL,
                    "score": {"type": "number"},
                    "weekly_change_pct": _NUM_NULL,
                    "relative_volume": _NUM_NULL,
                    "relative_strength_pct": _NUM_NULL,
                    "market_cap_usd": _NUM_NULL,
                    "why_awesome": {"type": "string"},
                    "why_awesome_en": {"type": "string"},
                    "why_awesome_zh": {"type": "string"},
                    "setup": {"type": "string"},
                    "setup_en": {"type": "string"},
                    "setup_zh": {"type": "string"},
                    "catalyst": _STR_NULL,
                    "catalyst_en": _STR_NULL,
                    "catalyst_zh": _STR_NULL,
                    "risk": _STR_NULL,
                    "risk_en": _STR_NULL,
                    "risk_zh": _STR_NULL,
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tags_en": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tags_zh": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "drivers": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "label_en": {"type": "string"},
                                "label_zh": {"type": "string"},
                                "value": {"type": "string"},
                                "score": {"type": "number"},
                                "note": {"type": "string"},
                                "note_en": {"type": "string"},
                                "note_zh": {"type": "string"},
                            },
                            "required": [
                                "label",
                                "label_en",
                                "label_zh",
                                "value",
                                "score",
                                "note",
                                "note_en",
                                "note_zh",
                            ],
                        },
                    },
                    "sparkline": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "label_en": {"type": "string"},
                                "label_zh": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["label", "label_en", "label_zh", "value"],
                        },
                    },
                    "sources": {
                        "type": "array",
                        "items": SOURCE_SCHEMA,
                    },
                },
                "required": [
                    "rank",
                    "ticker",
                    "name",
                    "exchange",
                    "sector",
                    "sector_en",
                    "sector_zh",
                    "score",
                    "weekly_change_pct",
                    "relative_volume",
                    "relative_strength_pct",
                    "market_cap_usd",
                    "why_awesome",
                    "why_awesome_en",
                    "why_awesome_zh",
                    "setup",
                    "setup_en",
                    "setup_zh",
                    "catalyst",
                    "catalyst_en",
                    "catalyst_zh",
                    "risk",
                    "risk_en",
                    "risk_zh",
                    "tags",
                    "tags_en",
                    "tags_zh",
                    "drivers",
                    "sparkline",
                    "sources",
                ],
            },
        },
        "watchlist": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                    "reason_en": {"type": "string"},
                    "reason_zh": {"type": "string"},
                },
                "required": ["ticker", "name", "reason", "reason_en", "reason_zh"],
            },
        },
        "sources": {
            "type": "array",
            "items": SOURCE_SCHEMA,
        },
    },
    "required": [
        "week_label",
        "week_label_en",
        "week_label_zh",
        "as_of",
        "market_pulse",
        "market_pulse_en",
        "market_pulse_zh",
        "benchmark_context",
        "benchmark_context_en",
        "benchmark_context_zh",
        "methodology",
        "methodology_en",
        "methodology_zh",
        "summary_cards",
        "sector_mix",
        "stocks",
        "watchlist",
        "sources",
    ],
}

STOCK_DETAIL_SCHEMA: dict[str, Any] = WEEKLY_SUMMARY_SCHEMA["properties"]["stocks"]["items"]

CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rank": {"type": "integer"},
        "ticker": {"type": "string"},
        "name": {"type": "string"},
        "exchange": _STR_NULL,
        "sector": _STR_NULL,
        "sector_en": _STR_NULL,
        "sector_zh": _STR_NULL,
        "score_hint": {"type": "number"},
        "weekly_change_pct": _NUM_NULL,
        "catalyst": {"type": "string"},
        "catalyst_en": {"type": "string"},
        "catalyst_zh": {"type": "string"},
        "reason": {"type": "string"},
        "reason_en": {"type": "string"},
        "reason_zh": {"type": "string"},
        "sources": {"type": "array", "items": SOURCE_SCHEMA},
    },
    "required": [
        "rank",
        "ticker",
        "name",
        "exchange",
        "sector",
        "sector_en",
        "sector_zh",
        "score_hint",
        "weekly_change_pct",
        "catalyst",
        "catalyst_en",
        "catalyst_zh",
        "reason",
        "reason_en",
        "reason_zh",
        "sources",
    ],
}

FAST_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rank": {"type": "integer"},
        "ticker": {"type": "string"},
        "name": {"type": "string"},
        "exchange": _STR_NULL,
        "sector": _STR_NULL,
        "score_hint": {"type": "number"},
        "weekly_change_pct": _NUM_NULL,
        "catalyst": {"type": "string"},
        "reason": {"type": "string"},
        "sources": {"type": "array", "items": FAST_SOURCE_SCHEMA},
    },
    "required": [
        "rank",
        "ticker",
        "name",
        "exchange",
        "sector",
        "score_hint",
        "weekly_change_pct",
        "catalyst",
        "reason",
        "sources",
    ],
}

WEEKLY_SCAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "week_label": {"type": "string"},
        "week_label_en": {"type": "string"},
        "week_label_zh": {"type": "string"},
        "as_of": {"type": "string"},
        "market_pulse": {"type": "string"},
        "market_pulse_en": {"type": "string"},
        "market_pulse_zh": {"type": "string"},
        "benchmark_context": {"type": "string"},
        "benchmark_context_en": {"type": "string"},
        "benchmark_context_zh": {"type": "string"},
        "methodology": {"type": "string"},
        "methodology_en": {"type": "string"},
        "methodology_zh": {"type": "string"},
        "summary_cards": WEEKLY_SUMMARY_SCHEMA["properties"]["summary_cards"],
        "candidates": {
            "type": "array",
            "minItems": 6,
            "maxItems": 8,
            "items": CANDIDATE_SCHEMA,
        },
        "watchlist": WEEKLY_SUMMARY_SCHEMA["properties"]["watchlist"],
        "sources": {"type": "array", "items": SOURCE_SCHEMA},
    },
    "required": [
        "week_label",
        "week_label_en",
        "week_label_zh",
        "as_of",
        "market_pulse",
        "market_pulse_en",
        "market_pulse_zh",
        "benchmark_context",
        "benchmark_context_en",
        "benchmark_context_zh",
        "methodology",
        "methodology_en",
        "methodology_zh",
        "summary_cards",
        "candidates",
        "watchlist",
        "sources",
    ],
}

FAST_WEEKLY_SCAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "week_label": {"type": "string"},
        "as_of": {"type": "string"},
        "market_pulse": {"type": "string"},
        "benchmark_context": {"type": "string"},
        "methodology": {"type": "string"},
        "candidates": {
            "type": "array",
            "minItems": 6,
            "maxItems": 8,
            "items": FAST_CANDIDATE_SCHEMA,
        },
        "watchlist": WEEKLY_SUMMARY_SCHEMA["properties"]["watchlist"],
    },
    "required": ["candidates"],
}


# The Claude CLI path capped these at 115s because an agentic WebSearch run
# is slow. A metered grounded call is not, so the cap is now about how long
# a user will wait on a refresh rather than about the engine.
SCAN_TIMEOUT_SEC = 180
DETAIL_TIMEOUT_SEC = 150

SYSTEM_PROMPT = f"""\
You are BSH's weekly public-equities research desk. Your job is to identify
the hottest US-listed common stocks and ADRs for the current trading week and
turn them into a concise, visually useful dashboard dataset.

Definition of "hottest":
- Strong current-week price action and relative strength versus the S&P 500.
- Clear volume expansion or unusual attention.
- Fresh, verifiable catalysts: earnings, guidance, product/regulatory news,
  analyst revisions, M&A, macro exposure, short squeeze pressure, or sector
  rotation.
- Liquidity suitable for institutional review. Avoid penny stocks, thin
  microcaps, warrants, ETFs, closed-end funds, SPAC remnants, and meme-only
  claims without a business catalyst.

Be enthusiastic in the prose, but stay evidence-based. This is a research
dashboard, not investment advice.

Bilingual contract:
- Every field ending in `_en` must be natural, concise English.
- Every field ending in `_zh` must be natural 简体中文, not literal word-by-word
  translation. Use finance/trader Chinese.
- The matching legacy field without suffix is required for compatibility and
  must mirror the English value.

{INVESTMENT_RESEARCH_CHINESE_STYLE}
"""


def build_research_prompt(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    date_label = current.strftime("%Y-%m-%d")
    return f"""\
CURRENT DATE: {date_label}

Research the hottest US-listed stocks for this trading week. Return exactly
six ranked stocks unless a seventh/eighth name is clearly necessary.

Workflow:
1. Search current-week market-mover roundups, top gainers, unusual-volume
   screens, sector momentum, and major financial news.
2. Fetch source pages for price action, relative volume, catalyst details,
   and dates. Prefer official IR/SEC/company pages for company events and
   reputable finance/news pages for market data.
3. Score each stock from 0-100 using a blended judgment of weekly move,
   relative volume, catalyst quality, institutional relevance, and durability.
4. Provide 3-5 drivers per stock. Each driver has a label, short value,
   score from 0-100, and a plain-English note.
5. Provide 5-8 sparkline points normalized to 0-100 for the current week.
   These are visual trend points, not raw prices.
6. Include sources with labels, URLs, and dates wherever available.
7. Populate every bilingual pair. For example: `market_pulse`,
   `market_pulse_en`, and `market_pulse_zh`; `why_awesome`,
   `why_awesome_en`, and `why_awesome_zh`; `tags`, `tags_en`, and
   `tags_zh`. The unsuffixed field mirrors English.

Tone:
- "why_awesome" should explain why the stock is exciting in one sentence.
- "setup" should say what kind of trade/investor narrative is developing.
- "risk" should name the fastest way the story can break.
- Keep strings compact enough for cards; avoid paragraphs.
- Chinese copy must fit the same cards: concise, high-signal, and polished.
- For Chinese copy, apply the Chinese localization quality bar from the system
  prompt. Preserve English terms when a literal Chinese translation would sound
  unnatural.
"""


def build_research_prompt_zh(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    date_label = current.strftime("%Y-%m-%d")
    return f"""\
当前日期：{date_label}

研究本交易周最热门的美国上市股票。默认返回六只排名股票，除非第七/第八只明显值得纳入。

工作流程：
1. 搜索本周市场异动、涨幅榜、异常成交量、板块动量和主要财经新闻。
2. 抓取来源页面验证价格表现、相对成交量、催化剂细节和日期。公司事件优先使用官方IR、SEC或公司页面；市场数据优先使用可靠财经/新闻页面。
3. 用0-100分评价每只股票，综合考虑周内涨幅、相对成交量、催化剂质量、机构相关性和持续性。
4. 每只股票提供3-5个驱动因素。每个驱动包括标签、简短数值、0-100分和一句说明。
5. 提供5-8个本周趋势点，归一化为0-100。这些点用于可视化趋势，不是原始股价。
6. 尽可能列出来源，包含标签、URL和日期。
7. 填充每一组中英文配对字段。例如：`market_pulse`、`market_pulse_en`、`market_pulse_zh`；`why_awesome`、`why_awesome_en`、`why_awesome_zh`；`tags`、`tags_en`、`tags_zh`。不带后缀的字段镜像英文。

文风：
- `why_awesome` 用一句话解释这只股票为什么令人兴奋。
- `setup` 说明正在形成什么样的交易/投资叙事。
- `risk` 点明故事最快失效的方式。
- 所有文案必须足够短，能放进卡片；避免段落。
- 中文文案要精炼、有金融语感，并适配同一套卡片布局。
- 中文字段必须遵守系统提示里的中文本地化质量标准：不要硬译术语；没有自然中文表达时保留英文，并在首次出现时加简短中文解释。
"""


def build_candidate_scan_prompt(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    date_label = current.strftime("%Y-%m-%d")
    return f"""\
CURRENT DATE: {date_label}

Phase 1 of the weekly hot-stock dashboard: scan the current trading week and
return only the market-level context plus 6-8 candidate stocks. Keep this pass
small and fast.

Workflow:
1. Use at most two WebSearch calls total. Do not use WebFetch in this scan.
   Produce the candidate JSON immediately after the second WebSearch result.
   Do not spend time on deep verification here; the next phase verifies each
   ticker separately.
2. Candidate stocks must be liquid US-listed common stocks or ADRs. Exclude
   penny stocks, ETFs, warrants, SPAC remnants, and meme-only claims.
3. For each candidate, include the freshest catalyst, a score_hint, rough
   weekly move, sector, and 1-3 compact sources.
4. Include only the fields in the attached schema. English-only context is OK
   in this scan; the detail and assembly phases fill the bilingual dashboard.

Do not produce full stock cards here. The next phase researches each selected
ticker separately.

The JSON root must contain a `candidates` array. If you include context fields,
keep them as siblings of `candidates`, never as a replacement for it.
"""


def build_stock_detail_prompt(
    scan: dict[str, Any],
    candidate: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    date_label = current.strftime("%Y-%m-%d")
    ticker = candidate.get("ticker") or ""
    return f"""\
CURRENT DATE: {date_label}

Phase 2 of the weekly hot-stock dashboard: produce one complete stock card for
{ticker}. Keep this pass bounded: use at most two WebSearch calls and one
WebFetch unless the first sources are unusable.

Candidate from scan:
{json.dumps(candidate, ensure_ascii=False)}

Market context from scan:
{json.dumps(_scan_context(scan), ensure_ascii=False)}

Return one stock object matching the schema. Requirements:
- Preserve the ticker and company identity unless the scan clearly used a bad
  match.
- Populate every English/Chinese field. Unsuffixed fields mirror English.
- Provide 3-5 drivers, 5-8 sparkline points, compact sources, and a clear risk.
- Keep every string card-sized. No paragraphs.
"""


def progress_path() -> Path:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    return PROGRESS_PATH


def draft_path() -> Path:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFT_PATH


def load_draft() -> dict[str, Any] | None:
    if not DRAFT_PATH.exists():
        return None
    try:
        with DRAFT_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    return data


def save_draft(draft: dict[str, Any]) -> dict[str, Any]:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(draft)
    payload["schema_version"] = SCHEMA_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(DRAFT_PATH)
    return payload


def clear_draft() -> None:
    try:
        DRAFT_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def load_summary() -> dict[str, Any] | None:
    if not SUMMARY_PATH.exists():
        return None
    try:
        with SUMMARY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    return data


def save_summary(summary: dict[str, Any]) -> dict[str, Any]:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    payload["schema_version"] = SCHEMA_VERSION
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["research_prompt"] = build_research_prompt()
    payload["research_prompt_en"] = payload["research_prompt"]
    payload["research_prompt_zh"] = build_research_prompt_zh()
    payload["available_languages"] = ["en", "zh"]
    tmp = SUMMARY_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(SUMMARY_PATH)
    return payload


def generate_summary(progress=None) -> tuple[dict[str, Any] | None, str | None]:
    started_at = datetime.now(timezone.utc).isoformat()
    draft: dict[str, Any] = save_draft({
        "status": "running",
        "phase": "scan",
        "started_at": started_at,
        "candidates": [],
        "stocks": [],
        "errors": [],
    })
    if progress:
        progress.emit(
            "stage",
            stage="scan",
            message="Scanning market movers",
        )

    scan, scan_meta, err = ai_engine.grounded(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_candidate_scan_prompt(),
        schema=FAST_WEEKLY_SCAN_SCHEMA,
        name="weekly_scan",
        gemini_timeout_sec=SCAN_TIMEOUT_SEC,
        claude_timeout_sec=SCAN_TIMEOUT_SEC,
    )
    # "This week's actual movers" is a claim about the live market. A model
    # answering it from memory would name stale movers with this week's
    # confidence, which is worse than admitting the scan failed — the static
    # watchlist at least announces itself as a static watchlist.
    if not err and not scan_meta.get("grounded"):
        err = (
            "weekly stock scan answered without searching the web, so its "
            "movers are not this week's"
        )
    if err:
        if progress:
            progress.emit(
                "stage",
                stage="scan_fallback",
                message="Using fallback weekly candidates",
                error=err,
            )
        draft["errors"] = [{"phase": "scan", "error": err}]
        scan = _fallback_scan(err)
    if not isinstance(scan, dict):
        err = "weekly stock scan returned no JSON object"
        if progress:
            progress.emit(
                "stage",
                stage="scan_fallback",
                message="Using fallback weekly candidates",
                error=err,
            )
        draft["errors"] = [{"phase": "scan", "error": err}]
        scan = _fallback_scan(err)

    candidates = _normalize_candidates(scan.get("candidates") or [])
    if len(candidates) < 5:
        err = "weekly stock scan returned fewer than five candidates"
        if progress:
            progress.emit(
                "stage",
                stage="scan_fallback",
                message="Using fallback weekly candidates",
                error=err,
            )
        draft["errors"] = [{"phase": "scan", "error": err}]
        scan = _fallback_scan(err)
        candidates = _normalize_candidates(scan.get("candidates") or [])

    draft.update(
        phase="details",
        candidates=candidates,
        total_count=len(candidates),
        scan_context=_scan_context(scan),
    )
    draft = save_draft(draft)
    if progress:
        progress.emit(
            "candidates",
            message=f"Found {len(candidates)} candidates",
            candidates=candidates,
            total_count=len(candidates),
        )

    stocks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        ticker = _clean_ticker(candidate.get("ticker"))
        if not ticker:
            continue
        draft.update(
            phase="details",
            active_ticker=ticker,
            index=index,
            total_count=len(candidates),
        )
        draft = save_draft(draft)
        if progress:
            progress.emit(
                "stock_started",
                ticker=ticker,
                name=candidate.get("name"),
                index=index,
                total_count=len(candidates),
                message=f"Researching {ticker}",
            )

        detail = None
        detail_err: str | None = None
        # One retry on transient failures (socket blips, CLI crashes) before
        # falling back to an unverified scan-only card.
        for attempt in range(2):
            detail, detail_meta, detail_err = ai_engine.grounded(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_stock_detail_prompt(scan, candidate),
                schema=STOCK_DETAIL_SCHEMA,
                name=f"weekly_stock_{ticker.lower()}",
                gemini_timeout_sec=DETAIL_TIMEOUT_SEC,
                claude_timeout_sec=DETAIL_TIMEOUT_SEC,
            )
            if not detail_err and not detail_meta.get("grounded"):
                detail_err = (
                    f"{ticker} verification answered without searching, so "
                    "it verifies nothing"
                )
            if not detail_err or attempt == 1:
                break
            if not claude_runner.is_transient_claude_error(detail_err):
                break
            if progress:
                progress.emit(
                    "stock_retry",
                    ticker=ticker,
                    index=index,
                    total_count=len(candidates),
                    error=detail_err,
                    message=f"Retrying {ticker} after transient error",
                )
        if detail_err:
            error = {
                "ticker": ticker,
                "name": candidate.get("name") or ticker,
                "error": detail_err,
            }
            errors.append(error)
            stock = _fallback_stock_from_candidate(candidate, detail_err)
            stocks.append(stock)
            draft["stocks"] = stocks
            draft["errors"] = errors
            draft["completed_count"] = len(stocks)
            draft = save_draft(draft)
            if progress:
                progress.emit(
                    "stock_error",
                    ticker=ticker,
                    index=index,
                    total_count=len(candidates),
                    error=detail_err,
                    message=f"Used scan fallback for {ticker}",
                )
                progress.emit(
                    "stock_done",
                    ticker=stock.get("ticker") or ticker,
                    index=index,
                    total_count=len(candidates),
                    completed_count=len(stocks),
                    stock=stock,
                    fallback=True,
                    message=f"Completed {stock.get('ticker') or ticker} from scan",
                )
            continue

        stock = _coerce_stock_detail(detail, candidate)
        if stock is None:
            detail_err = f"{ticker} detail returned no stock object"
            error = {
                "ticker": ticker,
                "name": candidate.get("name") or ticker,
                "error": detail_err,
            }
            errors.append(error)
            stock = _fallback_stock_from_candidate(candidate, detail_err)
            stocks.append(stock)
            draft["stocks"] = stocks
            draft["errors"] = errors
            draft["completed_count"] = len(stocks)
            draft = save_draft(draft)
            if progress:
                progress.emit(
                    "stock_error",
                    ticker=ticker,
                    index=index,
                    total_count=len(candidates),
                    error=detail_err,
                    message=f"Used scan fallback for {ticker}",
                )
                progress.emit(
                    "stock_done",
                    ticker=stock.get("ticker") or ticker,
                    index=index,
                    total_count=len(candidates),
                    completed_count=len(stocks),
                    stock=stock,
                    fallback=True,
                    message=f"Completed {stock.get('ticker') or ticker} from scan",
                )
            continue

        stocks.append(stock)
        draft["stocks"] = stocks
        draft["errors"] = errors
        draft["completed_count"] = len(stocks)
        draft = save_draft(draft)
        if progress:
            progress.emit(
                "stock_done",
                ticker=stock.get("ticker") or ticker,
                index=index,
                total_count=len(candidates),
                completed_count=len(stocks),
                stock=stock,
                message=f"Completed {stock.get('ticker') or ticker}",
            )

    if len(stocks) < 5:
        err = (
            f"weekly stock refresh completed only {len(stocks)} usable "
            "stock cards"
        )
        _fail_draft(draft, err, errors=errors)
        return None, err

    if progress:
        progress.emit(
            "stage",
            stage="assemble",
            message="Assembling weekly dashboard",
        )
    summary = _assemble_summary(scan, stocks, errors)
    _fill_missing_summary_zh(summary, scan, progress=progress)
    saved = save_summary(summary)
    draft.update(
        status="complete",
        phase="published",
        active_ticker=None,
        stocks=saved.get("stocks") or stocks,
        errors=errors,
        completed_count=len(saved.get("stocks") or stocks),
        skipped_count=len(errors),
        summary_generated_at=saved.get("generated_at"),
    )
    save_draft(draft)
    if progress:
        progress.emit(
            "publish_done",
            generated_at=saved.get("generated_at"),
            completed_count=len(saved.get("stocks") or stocks),
            skipped_count=len(errors),
            message="Published weekly dashboard",
        )
    return saved, None


def _fail_draft(
    draft: dict[str, Any],
    error: str,
    *,
    errors: list[dict[str, Any]] | None = None,
) -> None:
    draft.update(
        status="error",
        phase="error",
        error=error,
    )
    if errors is not None:
        draft["errors"] = errors
    save_draft(draft)


# Static seed list used only when the live scan fails. Deliberately carries
# no price data, no current-week claims, and no fabricated catalysts: each
# candidate still goes through the real per-stock verification pass, and
# anything that can't be verified is published flagged as fallback content
# (see `is_fallback` handling in `_assemble_summary` and the frontend).
_FALLBACK_SEED_CANDIDATES: list[dict[str, Any]] = [
    {"ticker": "SNOW", "name": "Snowflake Inc.", "exchange": "NYSE", "sector": "Software"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ", "sector": "Semiconductors"},
    {"ticker": "MRVL", "name": "Marvell Technology, Inc.", "exchange": "NASDAQ", "sector": "Semiconductors"},
    {"ticker": "MDB", "name": "MongoDB, Inc.", "exchange": "NASDAQ", "sector": "Software"},
    {"ticker": "DELL", "name": "Dell Technologies Inc.", "exchange": "NYSE", "sector": "Hardware"},
    {"ticker": "CRWD", "name": "CrowdStrike Holdings, Inc.", "exchange": "NASDAQ", "sector": "Cybersecurity"},
]


def _fallback_scan(error: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    date_label = current.strftime("%Y-%m-%d")
    week_start = current - timedelta(days=current.weekday())
    week_label = (
        f"Week of {week_start.strftime('%B')} {week_start.day}-"
        f"{current.day}, {current.year}"
    )
    source = {
        "label": "Static fallback watchlist (live scan unavailable)",
        "url": None,
        "date": date_label,
    }
    candidates = []
    for rank, seed in enumerate(_FALLBACK_SEED_CANDIDATES, start=1):
        candidates.append(
            {
                **seed,
                "rank": rank,
                "score_hint": 50,
                "weekly_change_pct": None,
                "catalyst": (
                    "Live market scan unavailable; standing watchlist name "
                    "pending per-stock verification."
                ),
                "reason": (
                    "Included from the static fallback watchlist, not from "
                    "a live scan of this week's movers."
                ),
                "sources": [source],
            }
        )
    context = {
        "is_fallback": True,
        "week_label": week_label,
        "as_of": date_label,
        "market_pulse": (
            "The live weekly market scan failed, so this dashboard was "
            "seeded from a static watchlist instead of this week's actual "
            "movers. Treat rankings and narratives as unverified."
        ),
        "market_pulse_zh": (
            "本周实时市场扫描失败，本页内容来自静态备用观察名单，"
            "并非本周真实的市场热点。排名与叙述均未经验证。"
        ),
        "benchmark_context": (
            "Fallback mode: entries come from a standing watchlist, not "
            "verified weekly price action."
        ),
        "benchmark_context_zh": "兜底模式：条目来自固定观察名单，并非经过验证的本周走势。",
        "methodology": (
            "Live scan unavailable; a static watchlist was substituted and "
            "each name was individually verified where possible."
        ),
        "candidates": candidates,
        "watchlist": [
            {
                "ticker": "HPE",
                "name": "Hewlett Packard Enterprise Co.",
                "reason": "Standing watchlist name (fallback mode).",
                "reason_en": "Standing watchlist name (fallback mode).",
                "reason_zh": "固定观察名单标的（兜底模式）。",
            },
            {
                "ticker": "PSTG",
                "name": "Pure Storage, Inc.",
                "reason": "Standing watchlist name (fallback mode).",
                "reason_en": "Standing watchlist name (fallback mode).",
                "reason_zh": "固定观察名单标的（兜底模式）。",
            },
        ],
    }
    if error:
        context["scan_error"] = error
    return context


def _scan_context(scan: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "week_label",
        "week_label_en",
        "week_label_zh",
        "as_of",
        "market_pulse",
        "market_pulse_en",
        "market_pulse_zh",
        "benchmark_context",
        "benchmark_context_en",
        "benchmark_context_zh",
        "methodology",
        "methodology_en",
        "methodology_zh",
    ]
    return {key: scan.get(key) for key in keys if scan.get(key) is not None}


def _normalize_candidates(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        ticker = _clean_ticker(item.get("ticker"))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        candidate = dict(item)
        candidate["ticker"] = ticker
        candidate["rank"] = len(out) + 1
        candidate["name"] = candidate.get("name") or ticker
        _ensure_bilingual_text(candidate, "sector", fallback="")
        _ensure_bilingual_text(candidate, "catalyst", fallback="")
        _ensure_bilingual_text(candidate, "reason", fallback="")
        candidate["sources"] = _normalize_sources(candidate.get("sources") or [])
        out.append(candidate)
    return out[:8]


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker)
    return ticker[:12]


def _coerce_stock_detail(
    detail: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None
    stock = detail.get("stock") if isinstance(detail.get("stock"), dict) else detail
    if not isinstance(stock, dict):
        return None
    stock = dict(stock)
    ticker = _clean_ticker(stock.get("ticker") or candidate.get("ticker"))
    if not ticker:
        return None
    stock["ticker"] = ticker
    stock["name"] = stock.get("name") or candidate.get("name") or ticker
    stock["exchange"] = stock.get("exchange") or candidate.get("exchange")
    stock["sector"] = stock.get("sector") or candidate.get("sector")
    stock["sector_en"] = stock.get("sector_en") or candidate.get("sector_en")
    stock["sector_zh"] = stock.get("sector_zh") or candidate.get("sector_zh")
    stock["score"] = _number(stock.get("score"), candidate.get("score_hint") or 70)
    stock["weekly_change_pct"] = _nullable_number(
        stock.get("weekly_change_pct"),
        candidate.get("weekly_change_pct"),
    )
    for key in ("relative_volume", "relative_strength_pct", "market_cap_usd"):
        stock[key] = _nullable_number(stock.get(key))
    for base in ("sector", "why_awesome", "setup", "catalyst", "risk"):
        _ensure_bilingual_text(stock, base, fallback="")
    _ensure_string_array(stock, "tags")
    _ensure_string_array(stock, "tags_en", fallback=stock.get("tags"))
    _ensure_string_array(stock, "tags_zh", fallback=stock.get("tags_en"))
    stock["drivers"] = _normalize_drivers(stock.get("drivers") or [])
    stock["sparkline"] = _normalize_sparkline(stock.get("sparkline") or [])
    stock["sources"] = _normalize_sources(stock.get("sources") or [])
    return stock


def _fallback_stock_from_candidate(
    candidate: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    row = dict(candidate)
    ticker = _clean_ticker(row.get("ticker"))
    row["ticker"] = ticker
    row["name"] = row.get("name") or ticker
    for base in ("sector", "catalyst", "reason"):
        _ensure_bilingual_text(row, base, fallback="")
    score = _number(row.get("score_hint"), 70)
    move = _nullable_number(row.get("weekly_change_pct"))
    catalyst = str(row.get("catalyst") or "No verified catalyst (detail research failed)")
    catalyst_en = str(row.get("catalyst_en") or catalyst)
    catalyst_zh = str(row.get("catalyst_zh") or catalyst_en)
    reason = str(row.get("reason") or "surfaced by the weekly scan; not verified")
    reason_en = str(row.get("reason_en") or reason)
    reason_zh = str(row.get("reason_zh") or reason_en)
    move_value = _format_pct(move)
    sparkline = _fallback_sparkline(move)
    sources = _normalize_sources(row.get("sources") or [])
    source_note = "Detailed verification timed out; this card uses the scan result."
    if error:
        source_note = f"{source_note} Detail error: {error[:140]}"
    return {
        "rank": int(_number(row.get("rank"), 0)),
        "ticker": ticker,
        "name": str(row.get("name") or ticker),
        "exchange": row.get("exchange"),
        "sector": row.get("sector"),
        "sector_en": row.get("sector_en"),
        "sector_zh": row.get("sector_zh"),
        "is_fallback": True,
        "sparkline_synthetic": True,
        "score": score,
        "weekly_change_pct": move,
        "relative_volume": None,
        "relative_strength_pct": None,
        "market_cap_usd": None,
        "why_awesome": f"{ticker} surfaced in the weekly scan (unverified): {reason_en}",
        "why_awesome_en": f"{ticker} surfaced in the weekly scan (unverified): {reason_en}",
        "why_awesome_zh": f"{ticker} 出现在本周扫描中（未经验证）：{reason_zh}",
        "setup": "Scan result only — per-stock verification did not complete.",
        "setup_en": "Scan result only — per-stock verification did not complete.",
        "setup_zh": "仅为扫描结果——个股深度验证未完成。",
        "catalyst": catalyst,
        "catalyst_en": catalyst_en,
        "catalyst_zh": catalyst_zh,
        "risk": "The thesis weakens if follow-up data does not confirm the scan catalyst.",
        "risk_en": "The thesis weakens if follow-up data does not confirm the scan catalyst.",
        "risk_zh": "若后续数据无法确认扫描阶段的催化剂，交易逻辑会走弱。",
        "tags": ["weekly momentum", "scan fallback"],
        "tags_en": ["weekly momentum", "scan fallback"],
        "tags_zh": ["周度动量", "扫描兜底"],
        "drivers": [
            {
                "label": "Weekly move",
                "label_en": "Weekly move",
                "label_zh": "周涨幅",
                "value": move_value,
                "score": min(100, max(0, score)),
                "note": reason_en,
                "note_en": reason_en,
                "note_zh": reason_zh,
            },
            {
                "label": "Catalyst",
                "label_en": "Catalyst",
                "label_zh": "催化剂",
                "value": "Unverified",
                "score": min(100, max(0, score - 5)),
                "note": catalyst_en,
                "note_en": catalyst_en,
                "note_zh": catalyst_zh,
            },
            {
                "label": "Verification",
                "label_en": "Verification",
                "label_zh": "验证状态",
                "value": "Scan",
                "score": 55,
                "note": source_note,
                "note_en": source_note,
                "note_zh": "深度验证未完成；本卡片基于扫描阶段结果。",
            },
        ],
        "sparkline": sparkline,
        "sources": sources,
    }


def _fallback_sparkline(move: float | None) -> list[dict[str, Any]]:
    if move is None:
        values = [42, 48, 54, 59, 64]
    elif move >= 0:
        values = [35, 45, 58, 72, min(96, 72 + move)]
    else:
        values = [65, 58, 50, 44, max(15, 44 + move)]
    labels = [
        ("Mon", "Mon", "周一"),
        ("Tue", "Tue", "周二"),
        ("Wed", "Wed", "周三"),
        ("Thu", "Thu", "周四"),
        ("Fri", "Fri", "周五"),
    ]
    return [
        {
            "label": label,
            "label_en": label_en,
            "label_zh": label_zh,
            "value": max(0, min(100, _number(value, 50))),
        }
        for (label, label_en, label_zh), value in zip(labels, values)
    ]


def _assemble_summary(
    scan: dict[str, Any],
    stocks: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    # Candidates are deduped by ticker before research, but a detail pass can
    # come back naming a different company than the candidate it was asked
    # about — two candidates then collapse onto one ticker and the dashboard
    # shows the same name twice with two different weekly moves. Keep the
    # best-scoring row per ticker.
    by_ticker: dict[str, dict[str, Any]] = {}
    for item in sorted(
        stocks,
        key=lambda item: (
            _number(item.get("score"), 0),
            _number(item.get("weekly_change_pct"), 0),
        ),
        reverse=True,
    ):
        key = _clean_ticker(item.get("ticker")) or str(item.get("name") or "").strip().lower()
        if key and key not in by_ticker:
            by_ticker[key] = item
    ranked = list(by_ticker.values())[:8]
    for index, stock in enumerate(ranked, start=1):
        stock["rank"] = index
    watchlist = scan.get("watchlist") if isinstance(scan.get("watchlist"), list) else []
    summary_cards = (
        scan.get("summary_cards")
        if isinstance(scan.get("summary_cards"), list) and len(scan["summary_cards"]) == 4
        else _default_summary_cards(ranked, watchlist)
    )
    market_pulse_en, market_pulse_zh = _market_pulse_fallback(ranked)
    benchmark_en, benchmark_zh = _benchmark_context_fallback(ranked)
    methodology_en = (
        scan.get("methodology")
        or "Phased scan plus per-stock verification of price action, volume, catalysts, liquidity and narrative durability."
    )
    methodology_zh = "先进行市场扫描，再逐只股票验证走势、成交量、催化剂、流动性和叙事持续性。"
    fallback_stock_count = sum(1 for stock in ranked if stock.get("is_fallback"))
    summary = {
        # Honesty flags: `scan_fallback` means the candidate list itself came
        # from the static seed watchlist (live scan failed); per-stock
        # `is_fallback` means that card skipped detail verification. The
        # frontend must render these as degraded/unverified content.
        "scan_fallback": bool(scan.get("is_fallback")),
        "fallback_stock_count": fallback_stock_count,
        "week_label": scan.get("week_label") or _week_label_fallback(),
        "week_label_en": scan.get("week_label_en") or scan.get("week_label") or _week_label_fallback(),
        "week_label_zh": scan.get("week_label_zh") or scan.get("week_label_en") or scan.get("week_label") or _week_label_fallback(),
        "as_of": scan.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "market_pulse": scan.get("market_pulse") or market_pulse_en,
        "market_pulse_en": scan.get("market_pulse_en") or scan.get("market_pulse") or market_pulse_en,
        "market_pulse_zh": scan.get("market_pulse_zh") or market_pulse_zh,
        "benchmark_context": scan.get("benchmark_context") or benchmark_en,
        "benchmark_context_en": scan.get("benchmark_context_en") or scan.get("benchmark_context") or benchmark_en,
        "benchmark_context_zh": scan.get("benchmark_context_zh") or benchmark_zh,
        "methodology": methodology_en,
        "methodology_en": scan.get("methodology_en") or methodology_en,
        "methodology_zh": scan.get("methodology_zh") or methodology_zh,
        "summary_cards": summary_cards,
        "sector_mix": _sector_mix(ranked),
        "stocks": ranked,
        "watchlist": _normalize_watchlist(watchlist),
        "sources": _dedupe_sources(
            _normalize_sources(scan.get("sources") or [])
            + [source for stock in ranked for source in stock.get("sources", [])]
        )[:12],
    }
    return summary


_SUMMARY_ZH_PAIRS = (
    ("week_label", "week_label_zh"),
    ("market_pulse", "market_pulse_zh"),
    ("benchmark_context", "benchmark_context_zh"),
    ("methodology", "methodology_zh"),
)

_STOCK_ZH_FIELDS = ("why_awesome", "setup", "catalyst", "risk")
_LOWERCASE_EN_WORD_RE = re.compile(r"\b[a-z][a-z'-]+\b")


def _zh_needs_translation(value: Any) -> bool:
    """True when a `_zh` field is blank or carries untranslated English prose.

    Fallback stock cards stitch candidate English (reason/catalyst) into
    Chinese templates, producing half-English strings like
    "PYPL 进入本周热门名单：Best-in-class relative strength...". Genuine
    Chinese carries at most a few Latin proper nouns/tickers (all
    capitalized), so a run of lowercase English words is a reliable signal.
    """
    text = str(value or "").strip()
    if not text:
        return True
    return len(_LOWERCASE_EN_WORD_RE.findall(text)) >= 4


def _fill_missing_summary_zh(
    summary: dict[str, Any],
    scan: dict[str, Any],
    progress=None,
) -> None:
    """Translate top-level narrative fields the fast scan left English-only.

    FAST_WEEKLY_SCAN_SCHEMA intentionally skips the `_zh` fields for speed,
    which used to leave `market_pulse_zh` / `benchmark_context_zh` on a
    generic stats template while the English carried the real weekly
    narrative. Fill the missing Chinese with one small translation call; on
    any failure the template fallback stays so publishing never blocks.
    """
    needed: dict[str, str] = {}
    for base, zh_key in _SUMMARY_ZH_PAIRS:
        if str(scan.get(zh_key) or "").strip():
            continue  # the scan produced real Chinese for this field
        source = str(
            summary.get(f"{base}_en") or summary.get(base) or ""
        ).strip()
        if source:
            needed[zh_key] = source
    # Stock cards: fallback-built cards embed untranslated English in their
    # `_zh` fields; detection is content-based so genuine scan Chinese is
    # never touched.
    stocks = summary.get("stocks") if isinstance(summary.get("stocks"), list) else []
    for index, stock in enumerate(stocks):
        if not isinstance(stock, dict):
            continue
        for base in _STOCK_ZH_FIELDS:
            zh_key = f"{base}_zh"
            if not _zh_needs_translation(stock.get(zh_key)):
                continue
            source = str(
                stock.get(f"{base}_en") or stock.get(base) or ""
            ).strip()
            if source:
                needed[f"stocks[{index}].{zh_key}"] = source
    if not needed:
        return
    if progress:
        progress.emit(
            "stage",
            stage="translate_zh",
            message="Translating weekly narrative to Chinese",
        )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {key: {"type": "string"} for key in needed},
        "required": list(needed),
    }
    payload = json.dumps(needed, ensure_ascii=False, indent=2)
    data, _meta, err = ai_engine.structured(
        system_prompt=(
            "You translate a weekly public-equities dashboard from English "
            "to Simplified Chinese for institutional investors. Produce "
            "natural finance/trader Chinese, not literal word-by-word "
            "translation. Keep tickers, company names, index names, dates, "
            "percentages, and dollar figures in their original form.\n\n"
            + INVESTMENT_RESEARCH_CHINESE_STYLE
        ),
        user_prompt=(
            "Translate each English value in this JSON object to Simplified "
            "Chinese and return a JSON object with the SAME keys.\n\n"
            f"INPUT:\n{payload}"
        ),
        schema=schema,
        name="weekly_summary_zh",
        timeout_sec=120,
        # No `progress` passthrough: the Gemini path is a single HTTP call
        # with no per-turn stream to translate into ProgressLog events, and
        # the caller already emits its own stage events around this.
    )
    if err or not isinstance(data, dict):
        logger.warning("weekly summary zh translation failed: %s", err)
        if progress:
            progress.emit(
                "stage",
                stage="translate_zh_fallback",
                message="Chinese translation failed; keeping fallback text",
                error=err,
            )
        return
    stock_key_re = re.compile(r"^stocks\[(\d+)\]\.(\w+)$")
    for key in needed:
        value = data.get(key)
        if not (isinstance(value, str) and value.strip()):
            continue
        match = stock_key_re.match(key)
        if match:
            index = int(match.group(1))
            if 0 <= index < len(stocks) and isinstance(stocks[index], dict):
                stocks[index][match.group(2)] = value.strip()
        else:
            summary[key] = value.strip()


def _market_pulse_fallback(stocks: list[dict[str, Any]]) -> tuple[str, str]:
    if not stocks:
        return (
            "Weekly momentum is being refreshed from the current scan.",
            "本周动量正在根据最新扫描刷新。",
        )
    leader = stocks[0]
    sector = str(leader.get("sector") or "active leaders")
    ticker = str(leader.get("ticker") or "the top name")
    move = _format_pct(leader.get("weekly_change_pct"))
    return (
        f"Momentum is led by {ticker} in {sector}, with the top card showing {move} for the week.",
        f"本周动量由 {ticker} 领衔，所属板块为{sector}，榜首周表现为 {move}。",
    )


def _benchmark_context_fallback(stocks: list[dict[str, Any]]) -> tuple[str, str]:
    usable = [s for s in stocks if _nullable_number(s.get("weekly_change_pct")) is not None]
    if not usable:
        return (
            "The refresh ranks candidates by weekly price action, catalyst quality, volume attention, and narrative durability.",
            "本次刷新按周内走势、催化剂质量、成交量关注度和叙事持续性排序。",
        )
    avg_move = sum(_number(s.get("weekly_change_pct"), 0) for s in usable) / len(usable)
    return (
        f"Published names average {_format_pct(avg_move)} this week before deeper benchmark normalization.",
        f"已发布标的本周平均表现为 {_format_pct(avg_move)}，后续可继续细化相对基准表现。",
    )


def _week_label_fallback() -> str:
    now = datetime.now(timezone.utc)
    return f"Week of {now.strftime('%Y-%m-%d')}"


def _default_summary_cards(
    stocks: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
) -> list[dict[str, str]]:
    leader = stocks[0] if stocks else {}
    avg_score = round(sum(_number(s.get("score"), 0) for s in stocks) / max(1, len(stocks)))
    sectors = {str(s.get("sector") or "") for s in stocks if s.get("sector")}
    return [
        {
            "label": "Top move",
            "label_en": "Top move",
            "label_zh": "最大涨幅",
            "value": f"{leader.get('ticker') or 'n/a'} { _format_pct(leader.get('weekly_change_pct')) }",
            "note": "Highest-ranked weekly setup.",
            "note_en": "Highest-ranked weekly setup.",
            "note_zh": "本周排名最高的交易机会。",
        },
        {
            "label": "Avg heat",
            "label_en": "Avg heat",
            "label_zh": "平均热度",
            "value": str(avg_score),
            "note": "Average score across published names.",
            "note_en": "Average score across published names.",
            "note_zh": "已发布标的的平均评分。",
        },
        {
            "label": "Sectors",
            "label_en": "Sectors",
            "label_zh": "板块",
            "value": str(len(sectors)),
            "note": "Distinct sectors represented.",
            "note_en": "Distinct sectors represented.",
            "note_zh": "覆盖的不同板块数量。",
        },
        {
            "label": "Watch",
            "label_en": "Watch",
            "label_zh": "观察",
            "value": str(len(watchlist)),
            "note": "Near misses to monitor.",
            "note_en": "Near misses to monitor.",
            "note_zh": "值得继续跟踪的候选标的。",
        },
    ]


def _sector_mix(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(s.get("sector") or "Unclassified") for s in stocks)
    out = []
    for sector, count in counts.most_common():
        sample = next((s for s in stocks if (s.get("sector") or "Unclassified") == sector), {})
        out.append({
            "sector": sector,
            "sector_en": sample.get("sector_en") or sector,
            "sector_zh": sample.get("sector_zh") or sample.get("sector_en") or sector,
            "count": count,
        })
    return out


def _normalize_watchlist(raw: list[Any]) -> list[dict[str, str]]:
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ticker = _clean_ticker(item.get("ticker"))
        if not ticker:
            continue
        row = {
            "ticker": ticker,
            "name": str(item.get("name") or ticker),
            "reason": str(item.get("reason") or item.get("reason_en") or ""),
            "reason_en": str(item.get("reason_en") or item.get("reason") or ""),
            "reason_zh": str(item.get("reason_zh") or item.get("reason_en") or item.get("reason") or ""),
        }
        out.append(row)
    return out


def _normalize_drivers(raw: list[Any]) -> list[dict[str, Any]]:
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        _ensure_bilingual_text(row, "label", fallback="")
        _ensure_bilingual_text(row, "note", fallback="")
        row["value"] = str(row.get("value") or "")
        row["score"] = _number(row.get("score"), 0)
        out.append(row)
    return out[:5]


def _normalize_sparkline(raw: list[Any]) -> list[dict[str, Any]]:
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        _ensure_bilingual_text(row, "label", fallback="")
        row["value"] = max(0, min(100, _number(row.get("value"), 0)))
        out.append(row)
    return out[:8]


def _normalize_sources(raw: list[Any]) -> list[dict[str, Any]]:
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        _ensure_bilingual_text(row, "label", fallback="Source")
        row["url"] = row.get("url") if isinstance(row.get("url"), str) else None
        row["date"] = row.get("date") if isinstance(row.get("date"), str) else None
        out.append(row)
    return out


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen: set[str] = set()
    for source in sources:
        key = str(source.get("url") or source.get("label") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def _ensure_bilingual_text(
    obj: dict[str, Any],
    base: str,
    *,
    fallback: str,
) -> None:
    value = obj.get(base)
    en = obj.get(f"{base}_en")
    zh = obj.get(f"{base}_zh")
    text = next(
        (str(v) for v in (value, en, zh, fallback) if isinstance(v, str) and v),
        "",
    )
    obj[base] = str(value or en or text)
    obj[f"{base}_en"] = str(en or value or text)
    obj[f"{base}_zh"] = str(zh or en or value or text)


def _ensure_string_array(
    obj: dict[str, Any],
    key: str,
    *,
    fallback: Any = None,
) -> None:
    value = obj.get(key)
    if not isinstance(value, list):
        value = fallback if isinstance(fallback, list) else []
    obj[key] = [str(item) for item in value if item is not None]


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _nullable_number(value: Any, default: Any = None) -> float | None:
    if value is None:
        value = default
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_pct(value: Any) -> str:
    n = _nullable_number(value)
    if n is None:
        return "n/a"
    return f"{'+' if n > 0 else ''}{n:.1f}%"
