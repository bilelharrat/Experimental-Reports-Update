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
风险收益比 5. Chart slots are bridged as small tables until the chart
round. The run-wide data-honesty and register rules ride the shared
context.

## section: executive_summary
```yaml
id: executive_summary
en_title: Executive Summary
zh_title: 执行摘要
parity_en: ^\s*(?:(?:i|1)[\.\、]\s*)?executive\s+summary\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:i|1|一)[\.\、]\s*)?(?:执行摘要|核心摘要)\s*[:：]?\s*$
components:
- key_metrics_snapshot
- deal_terms
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases: []
role: exec
```

800-1,000 words. Fixed block order:

1. Positioning paragraph (≤60 words): what the company does, for whom,
   and one sentence placing it on the growth ladder (repeatable sales
   motion proven or not).
2. Deal paragraph: round, instrument, size, price — and what the price
   already assumes, interpreted in the same breath.
3. "Deal Snapshot" key_value table with `component: "deal_terms"`, exactly
   these 10 rows: Round | Instrument | Raise size | Pre-money | Post-money
   | Implied stake | Primary / secondary split | Use of proceeds |
   Co-investors | Expected close. Missing cells: "Not disclosed —
   <implication>".
4. Exactly 3 thesis bullets, complete verdict sentences with numbers:
   (a) the market supports a 5-10x bigger company, (b) the growth is
   repeatable, not founder-sold, (c) the price leaves a venture return.
   A bullet the evidence cannot support says so.
5. "Core Financials" table with `component: "key_metrics_snapshot"`
   titled "Key Metrics Snapshot": ARR/Revenue | Growth rate | Gross
   margin | Net revenue retention | Burn multiple | Cash runway |
   Last/current valuation and implied multiple. Columns: two most recent
   periods plus a +3y column carrying ONLY pinned base-scenario numbers.
6. ≤3 top-risk bullets quoting the highest-rated pinned risk summaries
   verbatim with ratings.
7. Verdict callout: the pinned recommendation sentence verbatim, entry,
   base-case outcome from the pinned scenarios, fund placeholders
   verbatim. With a pinned verdict tier and scorecard, open on
   "{tier} — {total}/100".
8. A pinned `decision_history_sentence` is stated verbatim as history.

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
floor: {}
pass_affinity:
- deployment_behavior
- team_governance
title_word_aliases:
- company and team
```

900-1,100 words. The company's story and the people scaling it, judged
together — at growth stage the team IS most of the evidence. Fixed
blocks:

1. "Company Facts" key_value table: Founded | Headquarters | Headcount
   (with 12-month change) | Founders & CEO | What it sells, one line.
2. "Funding History" table: every disclosed round — Date | Round |
   Amount | Post-money | Lead investors | Price change vs prior round.
3. Milestones narrative (2-3 paragraphs, cause and effect, not dates).
4. "Leadership" table: CEO plus key executives — Role | Prior record |
   Strength or gap (verdict fragment). Empty key seats are rows with
   consequences.
5. "Board of Directors" table with `component: "board"`: members,
   affiliation, strategic value; plus an Ownership & Governance
   key_value block (founder control, ESOP, protective provisions).
6. REQUIRED verdict passage headed "Scale-up readiness": can this team
   run a company 5-10x this size — hiring record, executive bench,
   founder dependence, and what the organization looks like without
   its founder for a quarter. End on the verdict sentence.

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
```

800-1,000 words. Whether the market supports the 5-10x the price needs.
Fixed blocks:

1. Market-definition passage: the market actually competed in, the
   value-chain position, who captures value above and below.
2. "Market Sizing" table — ALWAYS TAM | SAM | SOM rows, columns
   Definition | Size today | Size at exit year | CAGR | Basis/source;
   missing rows follow the missing-data rule, never a borrowed number.
3. Chart slot `chart_market_size` (bridged): sizing series as a small
   table plus one interpretation sentence, or the chart-omitted
   fallback.
4. Growth-drivers passage: one claim sentence plus one supporting datum
   per driver; unsupported drivers are named assumptions.
5. REQUIRED passage headed "The ceiling question" (Chinese: 天花板问题):
   what the market caps this company at, which assumption moves the
   band, verdict sentence last.
6. Policy & regulatory passage — never silently omitted; when nothing
   applies, say so and say what could change it.

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
- deployment_behavior
- gtm_operating_burden
title_word_aliases:
- product, business model and unit economics
- product and business model
```

1,000-1,300 words. Why customers pay and whether the sales motion is a
machine yet. Fixed blocks:

1. "Why customers pay" opening passage: buyer, problem, alternative,
   customer-side economics, strongest disclosed proof point.
2. "Revenue Model" key_value table: Revenue streams | Pricing model |
   Contract length & terms | Revenue recognition character.
3. "Key Operating Metrics" table with
   `component: "key_operating_metrics"` — exactly these 8 rows:
   Customer count | Largest-customer penetration | Top-10 revenue
   concentration | Net revenue retention | Gross retention | CAC
   payback | LTV/CAC or magic number | ARR per employee. Columns:
   Value | As of | Benchmark | Reading (a verdict fragment).
4. "Revenue Quality Split" table: recurring vs committed vs project vs
   concentrated, with share and the risk each carries.
5. Revenue-equation passage: 收入 = 客户数 × 客单价 × 使用量 × 留存 —
   which factor drove growth so far, which must drive the next 5-10x,
   and the evidence for the hand-off.
6. MANDATORY both-ways passage on the strongest demand signal: the
   honest bull reading AND the honest bear reading, then which one the
   evidence favors ("The pipeline is valuable evidence of demand. It is
   not revenue.").
7. Repeatability passage: what fraction of revenue was founder-sold vs
   rep-sold, ramp time of the last cohort of reps, and the verdict on
   whether the motion scales with money.

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
- replacement_coexistence
- competitive_rights
title_word_aliases:
- competition and moat
```

900-1,100 words. Who wins, and whether the advantage survives the
company getting noticed. Fixed blocks:

1. Industry-map passage: upstream → company → downstream, where the
   profit pools sit now and at maturity.
2. "Competitive Analysis" table with `component: "competitive_analysis"`:
   the target FIRST, then 3-5 named competitors. Columns (reduced for
   the disclosure level of this stage): Offering | Scale/funding |
   Growth | Flagship customers | Core advantage. Sparse rows keep the
   missing-data rule.
3. Chart slot `chart_competitor_scale` (bridged): scale comparison as a
   small table plus one sentence on the gap.
4. "Replacement vs. Coexistence" treatment with
   `component: "replacement_coexistence"`: replace or coexist, category
   by category, with what each implies for the ceiling.
5. "Moat Audit" table with `component: "moat"` — ALWAYS all 8 rows:
   Technology | Data | Distribution | Ecosystem | Switching cost |
   Network effect | Brand | Scale economics. Columns: Strength
   (Strong / Moderate / Weak / Too early / None) | Evidence | Trajectory
   (Widening / Stable / Narrowing). "Too early" is an honest answer at
   this stage; a guess is not.
6. REQUIRED passage headed "The fast-follower question": when this
   category is proven, what stops a better-funded fast follower —
   answered from the audit rows.
7. Closing verdict passage headed "Number one — now and in five years":
   who leads today, who most likely leads in 3-5 years, and why.

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
- arithmetic_denominators
- growth_bridge
title_word_aliases: []
```

900-1,200 words. Whether the growth is real and what each new dollar of
it costs. Fixed blocks:

1. "Financial History" table with `component: "revenue"` titled
   "Revenue Picture": every disclosed year plus YTD — Revenue | Growth |
   Gross margin | Opex | Burn | Cash. Missing years keep rows.
2. "Forecast" table: +3 years, one row per year, "Key assumption"
   column naming what each year's number leans on. Unpinned,
   undisclosed cells follow the missing-data rule.
3. "Growth Quality" table with `component: "growth_bridge"` — fixed
   rows, burn-efficiency first for this stage: Burn multiple |
   Net-new-ARR per $ burned | Rule of 40 | Organic vs acquired |
   Pricing vs volume split | Cash conversion & receivables. Columns:
   Value | Reading.
4. Chart slot `chart_revenue_trajectory` (bridged): history + forecast
   series as a small table plus one sentence on the shape.
5. Revenue-authenticity passage: subsidies, one-offs, related-party
   revenue, audit status — checked and uncheckable both stated.
6. Forecast-credibility passage with consequence arithmetic: the
   forecast's implied trajectory against the company's own history and
   the best disclosed comparable at the same scale.
7. Closing verdict passage headed "Healthier or hungrier" (Chinese:
   增长更健康还是更烧钱): is incremental revenue getting cheaper or
   dearer, and what that means for how many more rounds this company
   needs.

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
- arithmetic_denominators
- time_base
- valuation_comps
- exit_paths
title_word_aliases:
- valuation, returns and exit
- valuation and returns
role: valuation
```

1,100-1,400 words. What the price assumes, what the investment returns
in each world, and how the money comes back. Fixed blocks:

1. "Comparables" table: 4-6 disclosed comparables with growth-adjusted
   multiples, the target listed first.
2. Chart slot `chart_comps_multiples` (bridged): the multiples as a
   small table plus one sentence placing the entry multiple.
3. "Valuation Methods" table — ALWAYS 3 method rows (Comparable
   companies | Precedent transactions | DCF / earnings power), each
   with Result or range | Basis | Why trusted or not; un-runnable
   methods state why in their row. Final row: the fair-value range this
   memo concludes.
4. "Time-Base Integrity" table with `component: "time_base_integrity"`:
   the marks in play, their dates, fresh or stale.
5. Passage headed "What is priced in" (Chinese: 当前价格已经包含了什么),
   arithmetic shown.
6. PAIRED advocate/counter passages "Why this merits $X" / "Why the cap
   is $Y" for the range ends.
7. "Scenario Analysis" table with `component: "scenario_analysis"`:
   rows bear | base | bull, columns Exit year | Exit-year revenue |
   Exit multiple | Exit valuation | Dilution assumption | Value to this
   round | Gross MOIC | IRR — every numeric cell repeats the pinned
   scenario numbers exactly; unpinned cells follow the missing-data
   rule. Then the return-decomposition passage (growth x vs multiple x,
   with the crossover stated) and chart slots `chart_return_scenarios`
   and `chart_return_decomposition` (bridged).
8. REQUIRED passage headed "The exit horizon" — replaces a late-stage
   exit map, because growth-stage exits are horizons, not calendars:
   the plausible exit window, what must be true by then (scale,
   margins, governance), named plausible acquirers with the constraint
   on each, and the consequence arithmetic on at least one non-premium
   outcome.
9. "Milestone Timeline" table: 3-6 dated milestones over the next
   12-36 months, each with the metric it moves and what hitting or
   missing it does to the thesis.

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
- competitive_rights
title_word_aliases:
- investment risk
- risk analysis
role: risk
```

900-1,200 words. Fixed blocks:

1. One-paragraph intro naming which single risk carries the thesis.
2. 4-6 per-risk cards, ordered by rating highest first, using EXACTLY
   the pinned risk list and ratings. Card = heading (the pinned
   summary — a complete verdict sentence with a finite verb, never a
   topic label) + key_value table with `component: "risk_register"`,
   rows: Risk Type | Why it matters (fact → failure mode → economic
   consequence, arithmetic when quantifiable) | What we watch |
   Likelihood | Risk Rating N/10.
3. Disconfirming-evidence treatment with
   `component: "disconfirming_evidence"`: the strongest facts against
   the recommendation, each weighed in one sentence.
4. Downside-scenario passage: the bear case narrated as a sequence of
   events ending in the pinned bear numbers.
5. Closing risk/reward verdict paragraph.

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
```

700-900 words. Fixed blocks:

1. "Six Questions" table with `component: "evidence_thresholds"` titled
   "Evidence Thresholds — The Six Questions" — fixed rows, each
   answered Yes / No / Qualified with a one-line basis: Is the market
   big enough to matter? | Is the company top-1-3 with evidence? |
   Does the moat survive being noticed? | Can this company grow 5-10x
   from here? | Does the price leave a venture return? | Can we get
   our money out? Every No or Qualified gets a what-would-flip-it
   paragraph.
2. "Scorecard" table — the 9 fixed dimensions with GROWTH weights:
   市场空间与增速 15 | 行业地位 12 | 护城河 13 | 收入增长与质量 15 |
   商业模式与单位经济 12 | 团队与治理 13 | 估值 10 | 退出确定性 5 |
   风险收益比 5. Columns Score | Why (one line). Pinned scorecards are
   repeated exactly; close with the total row and the threshold
   sentence (80+ invest / 70-79 watch / below 70 pass).
3. Symmetric close: equal-length lists (3-5 each) "What is
   demonstrated" / "What remains unresolved", one sentence with a
   number or gap per item.
4. Recommendation callout with `component: "investment_decision"`:
   pinned recommendation sentence verbatim, entry, pinned base-case
   outcome, holding period, exit route, fund placeholders verbatim.
5. "Monitoring Indicators" table (投后监控): 4-6 rows — Indicator |
   Current value | Trigger threshold | Response. Titled "What changes
   the verdict" when the verdict is watch/pass.
6. One-line legal disclosure paragraph with `component: "disclosures"`.
7. A pinned `decision_history_sentence` restated verbatim as history,
   adjacent to (never inside) the recommendation callout.
