---
stage: growth
version: 1
scorecard:
  market_size_growth: 15
  industry_position: 12
  moat: 13
  revenue_growth_quality: 15
  business_model_ue: 12
  team_governance: 13
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
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
  parity_en: ^\s*(?:(?:x|10)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:x|10|十)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

Growth-stage structure profile (Series B/C): nine fixed sections derived
from the late v2 merged IC structure — overview and team merge, the
competitive and moat chapters merge, and valuation/returns/exit merge,
because a growth company discloses less and the judgment weight shifts
toward growth quality and team. Scorecard weights for this stage:
市场空间与增速 15 | 行业地位 12 | 护城河 13 | 收入增长与质量 15 |
商业模式与单位经济 12 | 团队与治理 13 | 估值 10 | 退出确定性 5 |
风险收益比 5. Every section is organized under its declared numbered
subsections; the run-wide data-honesty, navigation, and chart rules
ride the shared context.

## section: executive_summary
```yaml
id: executive_summary
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

600-800 words. The summary's one job is to say what matters. It
contains NO tables — every number it needs lives in a sentence that
interprets it (the Deal Snapshot and Key Metrics Snapshot tables live
in the Company & Team section). Content per subsection:

1. Company profile: what the company does, for whom, sector and
   geography, and one sentence placing it on the growth ladder
   (repeatable sales motion proven or not). ≤80 words of prose.
2. The round: round, instrument, size, price, implied stake — and what
   the price already assumes, interpreted in the same breath. Prose
   only.
3. Investment highlights: OPEN with the pinned case-summary sentence
   from the shared fact sheet, the company's name in place of "The
   case" — one short paragraph saying WHICH dimensions carry the case
   and which are weak, with their scores. Then ONE `bullets` block
   with `"component": "investment_highlights"` and EXACTLY three
   items, one per pinned highlight, in pinned order: the pinned
   headline VERBATIM (plain text, no asterisks or markdown; the
   renderer bolds it), then the pinned evidence
   sentences. Every number is introduced by what it measures and where
   it comes from — a named source, or "our own estimate" with
   its inputs — before the reader meets the figure. Never a naked
   topic label ("Price.", "Market size."), never a new number.
4. Key risks: ONE `bullets` block with `"component": "key_risks"` and
   EXACTLY three items — the three highest-rated pinned risks in
   pinned order, each "<Area label> — <pinned summary verbatim>.
   Impact: <pinned impact verbatim>. (N/10, <likelihood> likelihood)".
   No new numbers, no rewritten summaries.
5. Recommendation: a verdict callout — the pinned recommendation
   sentence verbatim, entry, the fair-value range, base-case outcome
   from the pinned scenarios, holding period, and the fund
   placeholders verbatim. With a pinned verdict tier and scorecard,
   open on "{tier} — {total}/100". A pinned
   `decision_history_sentence` is stated verbatim after the callout as
   history.

## section: company_team
```yaml
id: company_team
scorecard_dimensions:
- team_governance
en_title: Company & Team
zh_title: 公司与团队
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s*(?:&|and)\s*team\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司与团队|公司与创始团队|公司概况与团队)\s*[:：]?\s*$
components:
- board
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- adoption_distribution
- team_governance
title_word_aliases:
- company and team
subsections:
- en: Company facts & key metrics
  zh: 公司基本情况与关键指标
- en: Funding history & this round
  zh: 融资历史与本轮方案
- en: Development milestones
  zh: 发展历程
- en: Leadership & board
  zh: 管理团队与董事会
- en: Founder-market fit
  zh: 创始人与赛道匹配
- en: Scale-up readiness
  zh: 规模化准备度
```

1,100-1,400 words. The company's story and the people scaling it,
judged together — at growth stage the team IS most of the evidence.
Content per subsection:

1. Company facts & key metrics: a "Company Facts" key_value table
   (Founded | Headquarters | Headcount with 12-month change |
   Founders & CEO | What it sells, one line), then the "Key Metrics
   Snapshot" table with `component: "key_metrics_snapshot"`:
   ARR/Revenue | Growth rate | Gross margin | Net revenue retention |
   Burn multiple | Cash runway | Last/current valuation and implied
   multiple. Columns: the two most recent periods plus a +3y column
   carrying ONLY pinned base-scenario numbers.
2. Funding history & this round: a "Funding History" table (every
   disclosed round — Date | Round | Amount | Post-money | Lead
   investors | Price change vs prior round), then the "Deal Snapshot"
   key_value table with `component: "deal_terms"`, exactly these 10
   rows: Round | Instrument | Raise size | Pre-money | Post-money |
   Implied stake | Primary / secondary split | Use of proceeds |
   Co-investors | Expected close. Missing cells: "Not disclosed —
   <implication>". Close with a short reading of the tables that
   OPENS with its verdict — do the marks support or undercut the
   entry price — then the numbers that prove it.
3. Development milestones: 2-3 paragraphs, cause and effect, not
   dates.
4. Leadership & board: the "Leadership" table (CEO plus key executives
   — Role | Prior record | Strength or gap as a verdict fragment;
   empty key seats are rows with consequences), then the "Board of
   Directors" table with `component: "board"` (members, affiliation,
   strategic value) plus an Ownership & Governance key_value block
   (founder control, ESOP, protective provisions).
5. Founder-market fit: open with the one-line answer — are these
   founders demonstrably the right people for THIS problem — then the
   proof: what each founder built or ran before that this business
   actually requires (verified facts with dates, separated from
   self-claimed bio), and where the record is silent. A celebrated
   background in a different discipline is stated as exactly that.
   End on the verdict: fit proven by prior work, asserted but
   unproven, or absent.
6. Scale-up readiness: can this team run a company 5-10x this size —
   hiring record, executive bench, founder dependence, and what the
   organization looks like without its founder for a quarter. Open
   with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 团队与治理 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: market_industry
```yaml
id: market_industry
scorecard_dimensions:
- market_size_growth
en_title: Market & Industry Analysis
zh_title: 市场与行业分析
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?market\s*(?:&|and)\s*industry(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:市场与行业分析|市场分析|行业分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
title_word_aliases:
- market and industry analysis
subsections:
- en: Market definition & value chain
  zh: 赛道定义与产业链位置
- en: Market size
  zh: 市场空间
- en: Growth drivers
  zh: 增长驱动
- en: The ceiling question
  zh: 天花板问题
- en: Policy & regulation
  zh: 政策与监管
```

800-1,000 words. Whether the market supports the 5-10x the price
needs. Content per subsection:

1. Market definition & value chain: the market actually competed in,
   the value-chain position, who captures value above and below.
2. Market size: FIRST the "Market estimates" table — one row per
   estimate the research found (each syndicated house, the company's
   own pitched TAM, bank or analyst sizing, and LAST the memo's own
   derivation), columns Source | What it counts (definition) | Value |
   Year | How it was built; an estimate is never dropped for
   disagreeing — the table shows which definition each uses. Follow it
   with a reading that OPENS with the range the memo adopts and why
   that definition fits this company, then explains the disagreements
   in plain words. Then the "Market Sizing" table — ALWAYS TAM | SAM |
   SOM rows, columns Definition | Size today | Size at exit year |
   CAGR | Basis/source (naming the estimate row or the memo's own
   inputs each rests on); missing rows follow the missing-data rule,
   never a borrowed number. Then chart slot `chart_market_size`: a `chart`
   block (grouped_bar; x = TAM / SAM / SOM; one series for today and
   one for the exit year, labeled with their actual years) built ONLY
   from the table's disclosed or derivable figures, followed by one
   interpretation sentence. When the series is not disclosed, no
   chart: the chart-omitted fallback line.
3. Growth drivers: one claim sentence plus one supporting datum per
   driver; unsupported drivers are named assumptions.
4. The ceiling question: what the market caps this company at, which
   assumption moves the band, open with the one-line answer; restate the verdict last.
5. Policy & regulation — never silently omitted; when nothing applies,
   say so and say what could change it.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 市场空间与增速 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: product_business_model
```yaml
id: product_business_model
scorecard_dimensions:
- business_model_ue
en_title: Product, Business Model & Unit Economics
zh_title: 产品、商业模式与单位经济
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?product,?\s*business\s+model\s*(?:&|and)\s*unit\s+economics\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:产品、商业模式与单位经济|产品与商业模式|商业模式与单位经济)\s*[:：]?\s*$
components:
- key_operating_metrics
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases:
- product, business model and unit economics
- product and business model
subsections:
- en: Why customers pay
  zh: 客户为什么付费
- en: Revenue model
  zh: 收入模式
- en: Key operating metrics
  zh: 关键运营指标
- en: Revenue quality
  zh: 收入质量
- en: Demand signals — both ways
  zh: 需求信号的两面
- en: Repeatability
  zh: 销售可复制性
```

1,000-1,300 words. Why customers pay and whether the sales motion is a
machine yet. Content per subsection:

1. Why customers pay: buyer, problem, alternative, customer-side
   economics, strongest disclosed proof point.
2. Revenue model: a "Revenue Model" key_value table — Revenue streams
   | Pricing model | Contract length & terms | Revenue recognition
   character.
3. Key operating metrics: the "Key Operating Metrics" table with
   `component: "key_operating_metrics"` — exactly these 8 rows:
   Customer count | Largest-customer penetration | Top-10 revenue
   concentration | Net revenue retention | Gross retention | CAC
   payback | LTV/CAC or magic number | ARR per employee. Columns:
   Value | As of | Benchmark | Reading (a verdict fragment).
4. Revenue quality: the "Revenue Quality Split" table (recurring vs
   committed vs project vs concentrated, with share and the risk each
   carries), then the revenue-equation passage: 收入 = 客户数 × 客单价 ×
   使用量 × 留存 — which factor drove growth so far, which must drive
   the next 5-10x, and the evidence for the hand-off.
5. Demand signals — both ways: the strongest demand signal argued both
   ways — the honest bull reading AND the honest bear reading, then
   which one the evidence favors ("The pipeline is valuable evidence
   of demand. It is not revenue.").
6. Repeatability: what fraction of revenue was founder-sold vs
   rep-sold, ramp time of the last cohort of reps, and the verdict on
   whether the motion scales with money.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 商业模式与单位经济 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: competition_moat
```yaml
id: competition_moat
scorecard_dimensions:
- industry_position
- moat
en_title: Competition & Moat
zh_title: 竞争格局与护城河
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?competition\s*(?:&|and)\s*moat\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:竞争格局与护城河|竞争与护城河|竞争格局)\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
- moat
floor: {}
pass_affinity:
- competitive_position
title_word_aliases:
- competition and moat
subsections:
- en: Industry map
  zh: 产业地图
- en: Competitor comparison
  zh: 竞争对比
- en: Replacement or coexistence
  zh: 替代还是共存
- en: Moat audit
  zh: 护城河审计
- en: The fast-follower question
  zh: 快速跟随者问题
- en: Number one — now and in five years
  zh: 现在与五年后的第一名
```

900-1,100 words. Who wins, and whether the advantage survives the
company getting noticed. Content per subsection:

1. Industry map: upstream → company → downstream, where the profit
   pools sit now and at maturity.
2. Competitor comparison: the "Competitive Analysis" table with
   `component: "competitive_analysis"`: the target FIRST, then 3-5
   named competitors. Columns (reduced for the disclosure level of
   this stage): Offering | Scale/funding | Growth | Flagship customers
   | Core advantage. Sparse rows keep the missing-data rule. Then
   chart slot `chart_competitor_scale`: a `chart` block (suggested bar; x = the
   table's companies, target first; y = the stated scale measure)
   built ONLY from disclosed figures, followed by one sentence on the
   gap. When the series is not disclosed, no chart: the chart-omitted
   fallback line.
3. Replacement or coexistence: the treatment with
   `component: "replacement_coexistence"`: replace or coexist,
   category by category, with what each implies for the ceiling.
4. Moat audit: the "Moat Audit" table with `component: "moat"` —
   ALWAYS all 8 rows: Technology | Data | Distribution | Ecosystem |
   Switching cost | Network effect | Brand | Scale economics. Columns:
   Strength (Strong / Moderate / Weak / Too early / None) | Evidence |
   Trajectory (Widening / Stable / Narrowing). "Too early" is an
   honest answer at this stage; a guess is not.
5. The fast-follower question: when this category is proven, what
   stops a better-funded fast follower — answered from the audit rows.
6. Number one — now and in five years: who leads today, who most
   likely leads in 3-5 years, and why. Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentences — one per dimension, "This dimension scores N of M." for 行业地位、护城河 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: financial_analysis
```yaml
id: financial_analysis
scorecard_dimensions:
- revenue_growth_quality
en_title: Financial Analysis
zh_title: 财务分析
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?financial\s+analysis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?财务分析\s*[:：]?\s*$
components:
- revenue
- growth_bridge
floor: {}
pass_affinity:
- numbers_integrity
- growth_bridge
title_word_aliases: []
subsections:
- en: Financial history
  zh: 历史业绩
- en: Forecast
  zh: 业绩预测
- en: Growth quality
  zh: 增长质量
- en: Revenue authenticity
  zh: 收入真实性
- en: Healthier or hungrier
  zh: 增长更健康还是更烧钱
```

900-1,200 words. Whether the growth is real and what each new dollar
of it costs. Content per subsection:

1. Financial history: the "Financial History" table with
   `component: "revenue"` titled "Revenue Picture": every disclosed
   year plus YTD — Revenue | Growth | Gross margin | Opex | Burn |
   Cash. Missing years keep rows.
2. Forecast: the "Forecast" table (+3 years, one row per year, "Key
   assumption" column naming what each year's number leans on;
   unpinned, undisclosed cells follow the missing-data rule). Then
   chart slot `chart_revenue_trajectory`: a `chart` block (suggested line;
   x = the fiscal years, history then forecast; one series "Revenue")
   built ONLY from the tables' disclosed or pinned figures, followed
   by one sentence on the shape that also names where actuals end and
   the forecast begins. When the series is not disclosed, no chart:
   the chart-omitted fallback line. Close with the
   forecast-credibility passage with consequence arithmetic: the
   forecast's implied trajectory against the company's own history and
   the best disclosed comparable at the same scale.
3. Growth quality: the "Growth Quality" table with
   `component: "growth_bridge"` — fixed rows, burn-efficiency first
   for this stage: Burn multiple | Net-new-ARR per $ burned | Rule of
   40 | Organic vs acquired | Pricing vs volume split | Cash
   conversion & receivables. Columns: Value | Reading.
4. Revenue authenticity: subsidies, one-offs, related-party revenue,
   audit status — checked and uncheckable both stated.
5. Healthier or hungrier: is incremental revenue getting cheaper or
   dearer, and what that means for how many more rounds this company
   needs. Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 收入增长与质量 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: valuation_returns_exit
```yaml
id: valuation_returns_exit
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Valuation, Returns & Exit
zh_title: 估值、回报与退出
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?valuation,?\s*returns?\s*(?:&|and)\s*exit\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?(?:估值、回报与退出|估值与回报|估值、回报测算与退出)\s*[:：]?\s*$
components:
- time_base_integrity
- scenario_analysis
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
- en: Comparables
  zh: 可比公司
- en: Valuation methods
  zh: 估值方法
- en: Time-base integrity
  zh: 估值时点核查
- en: What is priced in
  zh: 当前价格已经包含了什么
- en: The case for each end
  zh: 区间两端的论证
- en: Scenario analysis & return decomposition
  zh: 情景分析与回报分解
- en: The exit horizon
  zh: 退出窗口
- en: Milestone timeline
  zh: 里程碑时间线
```

1,100-1,400 words. What the price assumes, what the investment returns
in each world, and how the money comes back. Content per subsection:

1. Comparables: the "Comparables" table — 4-6 disclosed comparables
   with growth-adjusted multiples, the target listed first. Then chart
   slot `chart_comps_multiples`: a `chart` block (suggested bar; x = the
   table's companies, target first; y = the revenue multiple) built
   ONLY from disclosed figures, followed by one sentence placing the
   entry multiple. When the multiples are not disclosed, no chart: the
   chart-omitted fallback line.
2. Valuation methods: the "Valuation Methods" table — ALWAYS 3 method
   rows (Comparable companies | Precedent transactions | DCF /
   earnings power), each with Result or range | Basis | Why trusted or
   not; un-runnable methods state why in their row. Final row: the
   fair-value range this memo concludes.
3. Time-base integrity: the "Time-Base Integrity" table with
   `component: "time_base_integrity"`: the marks in play, their dates,
   fresh or stale.
4. What is priced in: translate the entry multiple into what the buyer
   is already paying for, arithmetic shown.
5. The case for each end: PAIRED advocate/counter passages with
   explicit sub-headings "Why this merits $X" and "Why the cap is $Y"
   — $X is the fair-value range's HIGH end (the strongest honest case
   the company earns it), $Y the LOW end (the strongest honest case
   value stops there).
6. Scenario analysis & return decomposition: the "Scenario Analysis"
   table with `component: "scenario_analysis"`: rows bear | base |
   bull, columns Exit year | Exit-year revenue | Exit multiple | Exit
   valuation | Dilution assumption | Value to this round | Gross MOIC
   | IRR — every numeric cell repeats the pinned scenario numbers
   exactly; unpinned cells follow the missing-data rule. Then the
   return-decomposition passage (growth x vs multiple x, with the
   crossover stated), and chart slot `chart_return_scenarios`: a
   `chart` block (bar; x = Bear / Base / Bull; y = gross MOIC) from
   the pinned MOICs, with its one-sentence reading.
7. The exit horizon — replaces a late-stage exit map, because
   growth-stage exits are horizons, not calendars: the plausible exit
   window, what must be true by then (scale, margins, governance),
   named plausible acquirers with the constraint on each, and the
   consequence arithmetic on at least one non-premium outcome.
8. Milestone timeline: a "Milestone Timeline" table — 3-6 dated
   milestones over the next 12-36 months, each with the metric it
   moves and what hitting or missing it does to the thesis.

Close this section with its pinned scorecard sentences — one per dimension, "This dimension scores N of M." for 估值、退出确定性 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: investment_risk
```yaml
id: investment_risk
scorecard_dimensions:
- risk_reward
en_title: Investment Risk
zh_title: 风险分析
parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:风险分析|投资风险)\s*[:：]?\s*$
components:
- risk_register
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
- competitive_position
title_word_aliases:
- investment risk
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk cards
  zh: 风险卡片
- en: Disconfirming evidence
  zh: 反面证据
- en: Downside scenario & verdict
  zh: 下行情景与风险结论
```

900-1,200 words. Content per subsection:

1. The center of gravity: one paragraph naming which single risk
   carries the thesis.
2. Risk cards: 4-6 per-risk cards, ordered by rating highest first,
   using EXACTLY the pinned risk list and ratings. Card = level-3
   heading (the pinned summary — a complete verdict sentence with a
   finite verb, never a topic label) + key_value table with
   `component: "risk_register"`, rows: Risk Type | Why it matters
   (fact → failure mode → economic consequence, arithmetic when
   quantifiable) | What we watch | Mitigation (the real mechanism —
   company action, deal structure, or position sizing; when none
   exists: "No structural mitigation exists. <consequence>") |
   Likelihood | Risk Rating N/10.
3. Disconfirming evidence: the treatment with
   `component: "disconfirming_evidence"`: the strongest facts against
   the recommendation, each weighed in one sentence.
4. Downside scenario & verdict: the bear case narrated as a sequence
   of events ending in the pinned bear numbers, then the closing
   risk/reward verdict paragraph.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 风险收益比 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: investment_decision
```yaml
id: investment_decision
en_title: Investment Decision
zh_title: 最终投资决定
parity_en: ^\s*(?:(?:ix|9)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ix|9|九)[\.\、]\s*)?(?:最终投资决定|投资决定|投资结论)\s*[:：]?\s*$
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
- en: The six questions
  zh: 六个关键问题
- en: Scorecard
  zh: 评分卡
- en: Demonstrated vs unresolved
  zh: 已证明与未解决
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

700-900 words. Content per subsection:

1. The six questions: the "Six Questions" table with
   `component: "evidence_thresholds"` titled "Evidence Thresholds —
   The Six Questions" — fixed rows, each answered Yes / No / Qualified
   with a one-line basis: Is the market big enough to matter? | Is the
   company top-1-3 with evidence? | Does the moat survive being
   noticed? | Can this company grow 5-10x from here? | Does the price
   leave a venture return? | Can we get our money out? Every No or
   Qualified gets a what-would-flip-it paragraph.
2. Scorecard: the "Scorecard" table — the 9 fixed dimensions with
   GROWTH weights: 市场空间与增速 15 | 行业地位 12 | 护城河 13 |
   收入增长与质量 15 | 商业模式与单位经济 12 | 团队与治理 13 | 估值 10 |
   退出确定性 5 | 风险收益比 5. Columns Score | Why (one line). Pinned
   scorecards are repeated exactly; close with the total row and the
   threshold sentence (80+ invest / 70-79 watch / below 70 pass).
3. Demonstrated vs unresolved: equal-length lists (3-5 each) "What is
   demonstrated" / "What remains unresolved", one sentence with a
   number or gap per item.
4. Recommendation: the recommendation callout with
   `component: "investment_decision"`: pinned recommendation sentence
   verbatim, entry, pinned base-case outcome, holding period, exit
   route, fund placeholders verbatim. A one-line legal disclosure
   paragraph with `component: "disclosures"` follows. A pinned
   `decision_history_sentence` is restated verbatim as history,
   adjacent to (never inside) the callout.
5. Monitoring & triggers: the "Monitoring Indicators" table (投后监控):
   4-6 rows — Indicator | Current value | Trigger threshold |
   Response. Titled "What changes the verdict" when the verdict is
   watch/pass.
