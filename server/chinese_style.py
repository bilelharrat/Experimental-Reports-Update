"""Prompt snippets for natural Simplified-Chinese investment writing."""
from __future__ import annotations


INVESTMENT_RESEARCH_CHINESE_STYLE = """\
CHINESE LOCALIZATION QUALITY BAR
- Write for mainland Chinese institutional investors. Prefer natural finance
  and research Chinese over literal word-by-word translation.
- If an English term has no idiomatic Chinese equivalent, keep the English
  term and add a short Chinese gloss on first mention. Do not invent awkward
  calques just to avoid English.
- Preserve company names, product names, framework/library names, model names,
  tickers, acronyms, metrics, numbers, dates, and URLs unless there is a
  widely used Chinese name.
- Reorder clauses so the Chinese sentence reads naturally. Do not preserve
  English syntax when it produces stiff or confusing Chinese.
- Avoid known bad calques:
  * Do not translate "tailwind" as "顺风". Depending on context use
    "行业利好", "需求侧利好", "结构性利好", "顺势因素", or
    "tailwind（利好因素）".
  * Do not translate coined phrases like "credible second wave" as
    "可信第二波". Use the meaning, e.g. "第二轮增长的可信度",
    "有望形成第二波增长", or keep the English phrase with a short gloss.
  * Do not translate "runway" mechanically as "跑道" unless the phrase is
    already idiomatic in context; prefer "现金可支撑时间", "增长空间", or
    keep "runway（可支撑时间/增长空间）".
  * Do not translate "stickiness" as a literal physical adjective; use
    "客户黏性", "用户黏性", or describe retention/switching costs.
- The Chinese output should be faithful in facts and numbers, but it should
  sound authored by a bilingual investment analyst, not machine-translated.
"""
