"""Weekly hot-stock dashboard research prompt, schema, and cache."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import claude_runner, storage
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

SCHEMA_VERSION = 2

WEEKLY_DIR: Path = storage.DATA_DIR / "_weekly_stocks"
SUMMARY_PATH: Path = WEEKLY_DIR / "summary.json"
PROGRESS_PATH: Path = WEEKLY_DIR / "weekly_summary.progress.jsonl"

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


def progress_path() -> Path:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    return PROGRESS_PATH


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
    prompt = build_research_prompt()
    data, err = claude_runner.run_web_research_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        schema=WEEKLY_SUMMARY_SCHEMA,
        name="weekly_stocks",
        timeout_sec=900,
        progress=progress,
        use_json_schema=False,
    )
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, "weekly stock research returned no JSON object"
    return save_summary(data), None
