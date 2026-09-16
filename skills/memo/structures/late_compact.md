---
stage: late_compact
version: 1
risk_format: bullets
scorecard:
  market_size_growth: 15
  industry_position: 15
  moat: 15
  revenue_growth_quality: 15
  business_model_ue: 10
  team_governance: 10
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
components:
- key_metrics_snapshot
- deal_terms
- disconfirming_evidence
- investment_decision
- evidence_thresholds
- disclosures
- source_index
lint_extra_titles:
- investment decision
- closing view
- key metrics snapshot
- deal snapshot
- scorecard
- sources
- references
pseudo_sections:
- id: sources
  en_title: Sources, Source Classes, and Fact Reference Index
  zh_title: 来源、来源类别与事实索引
  numbered: true
  parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

COMPACT late-stage profile — the short memo, modeled on the tightest
partner-memo style: seven sections, roughly 5,000-6,000 words total,
almost everything said in verdict-lead bullets ("An IP position that is
hard to overstate. 120+ patents, 90+ issued, zero rejections."), two
tables the reader actually needs (Deal Snapshot, Key Metrics Snapshot),
the scorecard, and at most two charts. Same evidence discipline as the
full report: the same pin sheet, the same scorecard, the same
data-honesty rules — LESS information, never worse information. Every
number that survives into this memo is one the decision turns on; the
detail lives in the full report, not here. PINS ARE THE FLOOR:
compactness cuts commentary, never pinned facts. Every pinned key
metric (with its exact values), every scenario number, the fair-value
range, the entry terms, every risk summary verbatim with its rating,
and each owning section's scorecard sentence ("This dimension scores
N of M.") must appear in this memo — the pin-echo gate rejects the
package otherwise, however elegant the prose. Section word budgets are
CEILINGS, not targets: each section's `budget_words` (in its yaml) is
the hard maximum for ALL its English text — table cells included — and
a deterministic gate rejects a section over it. The ceilings are set
ABOVE what this memo should normally run to, so hitting one is a signal
that the section has drifted into commentary, not a sign that the
budget is tight: aim for the material the decision turns on and the
ceiling will not come up. A section past its
budget cuts commentary — one bullet per point, one clause per
judgment — until it fits. When in doubt, cut; the full report exists
for depth. Every section is organized
under its declared numbered subsections; the run-wide data-honesty,
navigation, and chart rules ride the shared context. Bullets, not
paragraphs, are the default: prose only where an argument genuinely
needs consecutive sentences.

## section: executive_summary
```yaml
id: executive_summary
budget_words: 1200
en_title: Executive Summary
zh_title: 执行摘要
parity_en: ^\s*(?:(?:i|1)[\.\、]\s*)?executive\s+summary\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:i|1|一)[\.\、]\s*)?(?:执行摘要|核心摘要)\s*[:：]?\s*$
components: []
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases: []
role: exec
subsections:
- en: Company profile
  zh: 项目基本概况
- en: The round
  zh: 本轮融资方案
- en: Investment highlights
  zh: 核心投资亮点
- en: Key risks
  zh: 核心风险提示
- en: Recommendation
  zh: 投资结论与建议
```

1,000-1,200 words. NO tables. This is the section partners actually
read end to end — about two pages — so it carries the whole case on its
own: a reader who stops here must still know what the company is, what
the round asks, why the case holds, what could break it, and what we
recommend. Spend the extra room on EXPLANATION, not on new claims: every
number introduced by what it measures, every comparison stating the rule
it is measured against, every verdict followed by the evidence that earns
it. The counts below are fixed — more room per item, never more items.
Content per subsection:

1. Company profile: one plain-language sentence on what the company
   does and for whom, one on sector/geography, one placing it on the
   late-stage ladder, and one on the company type and what that type
   makes decisive. ≤120 words.
2. The round: round, instrument, size, price, implied stake, and what
   the price already assumes — the entry multiple interpreted in the
   same breath. 3-4 sentences.
3. Investment highlights: OPEN with the pinned case-summary sentence
   from the shared fact sheet, the company's name in place of "The
   case" — which dimensions carry the case and which are weak, with
   scores. Then ONE `bullets` block, `"component":
   "investment_highlights"`, EXACTLY three items in pinned order: the
   pinned headline VERBATIM (plain text, no asterisks or markdown; the
   renderer bolds it), then the pinned evidence
   sentences, each number introduced by what it measures and where it
   comes from (a named source, or "our own estimate" with its
   inputs). Never a naked topic label ("Price."), never a new number,
   never a risk, a valuation sensitivity or a recommendation here.

   Each headline is a VERDICT the reader could quote on its own: it
   states what is true about this company and why that matters, not the
   topic it belongs to. "Enterprise channels carry distribution" is a
   topic and fails; "Distribution does not have to be built, because the
   three largest clouds already resell it" is a verdict and passes. Each
   headline is followed by TWO evidence sentences (the pin carries 2-3),
   each a complete sentence naming what its number measures, the number,
   and where the number came from. Evidence sentences never open with a
   label such as "Evidence:" — they read as prose.

   Worked example (exactly three; the scorecard dimension shown in
   brackets is a pinned field, NOT printed in the memo):

   ```
   Anthropic's case rests on industry position (14/15), revenue growth
   and quality (13/15) and moat (12/15); it is weakest on valuation
   (6/10) and exit certainty (4/8).

   "component": "investment_highlights"

   [industry_position]
   The technical lead is already proven commercially — this is one of
   very few companies turning a frontier model into revenue at scale.
   Run-rate revenue, which measures how fast that conversion is
   happening, rose from about $9B in December 2025 to $65B in July
   2026 on the company's own basis of latest month times twelve [S4].
   The enterprise share, which measures whether that revenue is durable
   rather than consumer churn, is about 80% of the total on the same
   disclosure [S4].

   [revenue_growth_quality]
   Claude Code turned a coding tool into the entry point for agents,
   and took that position before the industry turned.
   Claude Code run-rate, which measures how much of the growth is one
   product, is above $2.5B on the company's basis [S4]. Customers
   paying more than $1M a year, which measures depth rather than
   breadth of adoption, doubled between February and April 2026 [S4].

   [moat]
   Distribution does not have to be built, because the three largest
   clouds already resell it — an enterprise buys through a vendor it has
   already approved.
   Availability across AWS Bedrock, Google Vertex AI and Microsoft
   Foundry, which measures how many procurement paths exist without a
   new vendor review, covers all three major clouds, with Microsoft
   Foundry generally available on 29 June 2026 [S9]. Revenue reaching
   the company through those channels, which measures how much of the
   book depends on them, is our own estimate of 25-30% from the
   disclosed enterprise split [C7].
   ```
4. Key risks: ONE `bullets` block, `"component": "key_risks"`, EXACTLY
   three items — the three highest-rated pinned risks in pinned
   order, each "<Area label> — <pinned summary verbatim>. Impact:
   <pinned impact verbatim>. (N/10, <likelihood> likelihood)".
5. Recommendation: a verdict callout — the pinned recommendation
   sentence verbatim, entry, fair-value range, base-case MOIC·IRR,
   holding period, and the fund placeholders verbatim. With a pinned
   verdict tier and scorecard, open on "{tier} — {total}/100". A
   pinned `decision_history_sentence` is stated verbatim after the
   callout as history.

## section: company_team
```yaml
id: company_team
budget_words: 1100
scorecard_dimensions:
- team_governance
en_title: Company, Team & Deal
zh_title: 公司、团队与交易
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company,?\s*team\s*(?:&|and)\s*deal\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司、团队与交易|公司与团队|公司与交易)\s*[:：]?\s*$
components:
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- adoption_distribution
- team_governance
title_word_aliases:
- company, team and deal
- company and team
subsections:
- en: Company & key metrics
  zh: 公司概况与关键指标
- en: The deal
  zh: 交易条款
- en: Team & founder-market fit
  zh: 团队与创始人匹配
```

400-550 words. Content per subsection:

1. Company & key metrics: 3-4 verdict-lead bullets (founded/HQ/what it
   sells/how it got here — one line each), then the "Key Metrics
   Snapshot" table with `component: "key_metrics_snapshot"`: 7 rows —
   Revenue/ARR | Growth rate | Gross margin | Burn or FCF | Cash
   runway | Last/current valuation | Implied multiple — columns
   Value | Reading (the Reading cell is a verdict fragment). Missing
   cells: "Not disclosed — <implication>". When the pin sheet carries
   key metrics beyond these seven, ADD a row per pinned metric with
   its exact pinned values — every pinned number must live somewhere
   in this memo.
2. The deal: the "Deal Snapshot" key_value table with
   `component: "deal_terms"`, exactly these 10 rows: Round |
   Instrument | Raise size | Pre-money | Post-money | Implied stake |
   Primary / secondary split | Use of proceeds | Co-investors |
   Expected close. Then ONE reading sentence that opens with its
   verdict: do the marks support or undercut this entry price.
3. Team & founder-market fit: one bullet per key person in the
   partner-memo style — "Name — Role. What they built or ran before
   that THIS business requires, verified with dates." — then one
   answer-first verdict sentence on founder-market fit (proven by
   prior work / asserted but unproven / absent) and one on governance
   (who can course-correct if the founders are wrong). Close the
   section with its pinned scorecard sentence: "This dimension scores
   N of M." for 团队与治理.

## section: thesis_market
```yaml
id: thesis_market
budget_words: 900
scorecard_dimensions:
- market_size_growth
- industry_position
- moat
en_title: Thesis, Market & Competition
zh_title: 投资逻辑、市场与竞争
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?thesis,?\s*market\s*(?:&|and)\s*competition\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:投资逻辑、市场与竞争|市场与竞争|投资逻辑)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
- competitive_position
title_word_aliases:
- thesis, market and competition
- market and competition
subsections:
- en: Why this matters now
  zh: 为什么是现在
- en: Market & ceiling
  zh: 市场空间与天花板
- en: Competition & moat
  zh: 竞争与护城河
```

450-550 words. Content per subsection:

1. Why this matters now: the investment thesis in 2-3 verdict-lead
   bullets — what market this opens, why the timing is now, why this
   company — each with its hardest number.
2. Market & ceiling: first ONE bullet per external estimate the
   research found (house or company, what it counts, value, year —
   never fewer than three when they exist, never dropped for
   disagreeing), then TAM/SAM/SOM in ONE bullet each (size, year, and
   the estimate or our own inputs it rests on — or the
   missing-data sentence), opening with the range the memo adopts and
   why that definition fits this company, then the ceiling answer
   first: does this market cap the company nearer $20B, $100B, or
   $500B, and the one assumption that moves it. One sentence on the
   policy/regulatory regime (or "No regulatory regime materially
   constrains this business today").
3. Competition & moat: who leads today and who most likely leads in
   3-5 years (with the datum); the 2-3 moat sources that are real,
   each with its evidence, and the ones that are absent, named; one
   answer-first verdict: the moat is widening / stable / narrowing and
   what that implies for the exit multiple. Close the section with its
   three pinned scorecard sentences — "This dimension scores N of M."
   for each of 市场空间与增速, 行业地位, and 护城河.

## section: business_financials
```yaml
id: business_financials
budget_words: 850
scorecard_dimensions:
- business_model_ue
- revenue_growth_quality
en_title: Business & Financials
zh_title: 业务与财务
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?business\s*(?:&|and)\s*financials\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:业务与财务|商业模式与财务|财务分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- numbers_integrity
- growth_bridge
- adoption_distribution
title_word_aliases:
- business and financials
subsections:
- en: How it makes money
  zh: 商业模式
- en: The numbers
  zh: 关键财务
- en: Healthier or hungrier
  zh: 增长更健康还是更烧钱
```

400-500 words. Content per subsection:

1. How it makes money: who pays, for what, on what pricing, and the
   strongest disclosed proof point — 2-3 verdict-lead bullets. One
   both-ways sentence on the strongest demand signal ("The pipeline is
   valuable evidence of demand. It is not revenue.").
2. The numbers: revenue trajectory (the 2-3 numbers that matter, each
   interpreted), retention/unit economics where disclosed, burn and
   runway — verdict-lead bullets, missing data stated as missing. A
   chart slot `chart_revenue_trajectory` (suggested line) is allowed
   here when the series is disclosed; otherwise no chart and no
   fallback line needed in compact — the bullets carry the gap.
3. Healthier or hungrier: open with the one-line answer; two sentences
   of the arithmetic that proves it; end by restating the verdict.
   Close the section with its two pinned scorecard sentences — "This
   dimension scores N of M." for 商业模式与单位经济 and 收入增长与质量.

## section: valuation_returns
```yaml
id: valuation_returns
budget_words: 950
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Valuation, Returns & Exit
zh_title: 估值、回报与退出
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?valuation,?\s*returns?\s*(?:&|and)\s*exit\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:估值、回报与退出|估值与回报|估值分析)\s*[:：]?\s*$
components: []
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- valuation_exit
title_word_aliases:
- valuation, returns and exit
- valuation and returns
role: valuation
subsections:
- en: What the price assumes
  zh: 价格已经包含了什么
- en: Fair value & scenarios
  zh: 公允价值与情景
- en: Exit paths
  zh: 退出路径
```

450-550 words. Content per subsection:

1. What the price assumes: the entry multiple against the 2-3
   comparables that matter (one bullet each, target first), then the
   arithmetic of what the buyer is already paying for. Answer first:
   is the price above, at, or below what the evidence supports.
2. Fair value & scenarios: the pinned fair-value range verbatim with
   its basis; then bear | base | bull in one bullet each carrying
   EVERY pinned scenario number exactly — exit year, exit-year
   revenue, exit multiple, exit value, gross MOIC, IRR (the pin gate
   checks each figure). Chart slot `chart_return_scenarios` (suggested
   bar; x = Bear / Base / Bull; y = gross MOIC) from the pinned MOICs,
   with its reading note and one-sentence caption.
3. Exit paths: the realistic route(s) with named acquirers or the IPO
   window, the constraint on each, and the consequence arithmetic on
   one non-premium outcome. Answer first: how does the money actually
   come back, and how certain is that. Close the section with its two
   pinned scorecard sentences — "This dimension scores N of M." for
   估值 and 退出确定性.

## section: risks
```yaml
id: risks
budget_words: 800
scorecard_dimensions:
- risk_reward
en_title: Risks
zh_title: 风险
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:风险|风险分析|投资风险)\s*[:：]?\s*$
components:
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
- competitive_position
title_word_aliases:
- risks
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk register
  zh: 风险清单
- en: Disconfirming evidence
  zh: 反面证据
```

300-400 words. Content per subsection:

1. The center of gravity: one or two sentences naming which single
   risk carries the thesis.
2. Risk register: one bullet PER PINNED RISK, ordered by rating
   highest first, using EXACTLY the pinned risk list. Each bullet:
   the pinned summary verbatim (it is already a complete verdict
   sentence), then " — N/10." with the rating, then ONE clause of
   mitigation or "No structural mitigation exists." Never a topic
   label, never a new risk the pins do not carry.
3. Disconfirming evidence: 2-3 bullets with
   `component: "disconfirming_evidence"` — the strongest facts
   AGAINST this memo's recommendation, each weighed in one clause.
   Close the section with its pinned scorecard sentence: "This
   dimension scores N of M." for 风险收益比.

## section: investment_decision
```yaml
id: investment_decision
budget_words: 900
en_title: Investment Decision
zh_title: 投资决定
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?(?:投资决定|最终投资决定|投资结论)\s*[:：]?\s*$
components:
- investment_decision
- evidence_thresholds
- disclosures
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases:
- final investment decision
- investment decision
subsections:
- en: Scorecard
  zh: 评分卡
- en: What decides it
  zh: 决定性因素
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

350-450 words. Content per subsection:

1. Scorecard: the "Scorecard" table — the 9 fixed dimensions with
   their weights — 市场空间与增速 15 | 行业地位 15 | 护城河 15 |
   收入增长与质量 15 | 商业模式与单位经济 10 | 团队与治理 10 | 估值 10 |
   退出确定性 5 | 风险收益比 5 — columns Score | Why (one line). Repeat
   the pinned scores and why-lines exactly; close with the total row
   and the threshold sentence (80+ invest / 70-79 watch / below 70
   pass).
2. What decides it: the six questions compressed to 6 bullets with
   `component: "evidence_thresholds"` — each "Question — Yes/No/
   Qualified: one-line basis." A No or Qualified adds one clause on
   what evidence would flip it.
3. Recommendation: the callout with `component: "investment_decision"`
   — pinned recommendation sentence verbatim, entry, pinned base-case
   outcome, holding period, exit route, and the fund placeholders
   verbatim: "Proposed amount: [TO BE DETERMINED BY IC]", "Allocation:
   [TO BE DETERMINED BY IC]", "Strategy: [重仓 / 跟投 / 卡位 — IC to
   select]". A one-line legal disclosure paragraph with
   `component: "disclosures"` follows. A pinned
   `decision_history_sentence` is restated verbatim as history.
4. Monitoring & triggers: 3-4 bullets — Indicator, current value,
   trigger threshold, response. Titled "What changes the verdict"
   framing when the verdict is watch/pass: the triggers are the
   re-entry conditions.
