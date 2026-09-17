---
stage: late
version: 2
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
lint_extra_titles:
- investment decision
- investment decision / closing view
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
  parity_en: ^\s*(?:(?:xiii|13)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:xiii|13|十三)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

Late-stage structure profile v2 — the merged IC structure from
docs/Report-Structure.md (V1 research framework + scorecard, V2 PE IC
memo), written in the explanatory verdict-first register. Twelve fixed
sections; every run renders the same subsections, the same tables, the
same charts, and the same named passages, with missing data stated as
missing (the run-wide data-honesty, navigation, and chart rules ride
the shared context). Every section is organized under its declared
numbered subsections — the reader learns what a passage is about from
its heading, never from the paragraph explaining itself.

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

700-900 words. This section is the memo an IC member reads when they
read nothing else, and its one job is to say what matters. It contains
NO tables — every number it needs lives in a sentence that interprets
it (the Deal Snapshot and Key Metrics Snapshot tables live in the
Company Overview section). Content per subsection:

1. Company profile: one plain-language sentence on what the company
   does and for whom; one sentence on sector and geography; one
   sentence placing it on the late-stage ladder (PMF → Scale-up →
   Category leader → Pre-IPO → Public candidate). ≤80 words of prose.
2. The round: what is being offered — round, instrument, size, price,
   implied stake — and what that price already assumes. Interpret the
   entry multiple in the same breath ("...priced at ~NNx, which
   already includes X of the success case"). Prose only; every figure
   interpreted where it appears.
3. Investment highlights: OPEN with the pinned case-summary sentence
   from the shared fact sheet, with the company's name in place of
   "The case" — one short paragraph that says WHICH dimensions carry
   the case and which are weak, with their scores ("Anthropic's case
   rests on market size and growth (14/15), industry position (13/15)
   and revenue growth and quality (12/15); it is thinnest on
   business model and unit economics (5/10) and valuation (6/10)."),
   optionally followed by one sentence saying what that pattern
   means. Then ONE `bullets` block with `"component":
   "investment_highlights"` and EXACTLY three items, one per pinned
   highlight, in pinned order. Each item opens with the pinned
   headline VERBATIM (plain text, no asterisks or markdown; the
   renderer bolds it, so the reader gets the judgment before the first
   period), then the pinned evidence
   sentences. An evidence sentence that carries a number says what the
   number measures and where it comes from — a named source, or "our
   own estimate" with its inputs — before the reader meets the
   figure; never "a $450-675B market" without saying who sized it and
   how. No highlight rests on a derived number whose derivation is not
   named. Nothing here is new: the headlines and the evidence are the
   pin sheet's, repeated exactly.
4. Key risks: ONE `bullets` block with `"component": "key_risks"` and
   EXACTLY three items — the three highest-rated pinned risks, in
   pinned order. Each item reads "<Area label> — <pinned summary
   verbatim>. Impact: <pinned impact verbatim>. (N/10, <likelihood>
   likelihood)", for example "Valuation & exit — The entry price
   already assumes the 2028 plan is delivered. Impact: the base case
   returns 0.9x, a loss even if the plan lands. (9/10, High
   likelihood)". The area label is the one the pin sheet files the
   risk under. No new numbers, no rewritten summaries, no arithmetic
   chain — the risk section's card explains each risk in full.
5. Recommendation: a verdict callout — state the recommendation
   sentence EXACTLY as the shared fact sheet pins it, then the entry
   valuation, the fair-value range, the base-case outcome from the
   pinned scenarios (MOIC and IRR), holding period, and the fund
   placeholders ("Proposed amount: [TO BE DETERMINED BY IC]",
   "Allocation: [TO BE DETERMINED BY IC]"). When the pin sheet carries
   a verdict tier and scorecard total, open the callout with
   "{tier} — {total}/100". When the shared fact sheet pins a
   `decision_history_sentence`, state it verbatim after the callout as
   factual history — what BSH previously decided, never this memo's
   own conclusion.

## section: company_overview
```yaml
id: company_overview
en_title: Company Overview & Stage
zh_title: 公司概况与发展阶段
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s+overview(?:\s*(?:&|and)\s*stage)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司概况与发展阶段|公司概览|公司概况|项目简介)\s*[:：]?\s*$
components:
- key_metrics_snapshot
- deal_terms
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases:
- company overview and stage
- company overview
subsections:
- en: Company facts & key metrics
  zh: 公司基本情况与关键指标
- en: Funding history & this round
  zh: 融资历史与本轮方案
- en: Development milestones
  zh: 发展历程
- en: Proven and unproven
  zh: 已验证与未验证
```

900-1,200 words. What the company is, how it got here, and — the point
of this section — which claims about it are proven versus still a bet.
Content per subsection:

1. Company facts & key metrics: a "Company Facts" key_value table
   (Founded | Headquarters | Headcount | Founders & CEO | Ownership
   snapshot | What it sells, one line), then the "Key Metrics
   Snapshot" table with `component: "key_metrics_snapshot"`: 7 rows —
   Revenue/ARR | Growth rate | Gross margin | Burn or FCF | Cash
   runway | Last/current valuation | Implied multiple — with columns
   for the two most recent actual years/periods plus a +3y column
   whose cells may contain ONLY numbers the pinned base scenario
   states (otherwise "Not modeled — no pinned basis"). One short
   paragraph reads the two tables together: what kind of company these
   numbers describe.
2. Funding history & this round: a "Funding History" table (every
   disclosed round — Date | Round | Amount | Post-money | Lead
   investors | Price change vs prior round; an undisclosed round keeps
   its row), then the "Deal Snapshot" key_value table with
   `component: "deal_terms"`, exactly these 10 rows: Round |
   Instrument | Raise size | Pre-money | Post-money | Implied stake |
   Primary / secondary split | Use of proceeds | Co-investors |
   Expected close. Missing cells follow the missing-data rule
   ("Not disclosed — <implication>"). Close the subsection with a
   short reading of the tables that OPENS with its verdict in one
   plain sentence — do the marks support or undercut the entry price,
   and is that positive or negative for this deal — then the two or
   three numbers that prove it. A paragraph that only restates the
   rounds and prices without saying what they mean fails the register.
3. Development milestones: 2-3 short paragraphs telling the company's
   development as cause and effect ("X worked, so Y followed"), not a
   date list.
4. Proven and unproven: name the company's position on the late-stage
   ladder (PMF → Scale-up → Category leader → Pre-IPO → Public
   candidate), echoing the `stage` pin, then list what the evidence
   has demonstrated and what remains asserted. Each item is one
   sentence with its supporting or missing datum. Close with one
   verdict sentence on whether the stage the round is priced for
   matches the stage the evidence supports.

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
- market & industry
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

900-1,100 words. Whether the market can carry the valuation, and what
could cap it. Content per subsection:

1. Market definition & value chain: what market the company actually
   competes in (not the largest label it markets), where it sits in
   the value chain, and who captures the value above and below it.
2. Market size: FIRST the "Market estimates" table — one row per
   estimate the research found, never fewer than three when they
   exist: each syndicated house (Gartner, IDC, Stratpace, Technavio,
   MarketsandMarkets, Grand View ...), the company's own pitched TAM,
   bank or analyst sizing, and LAST the memo's own derivation; columns
   Source | What it counts (definition) | Value | Year | How it was
   built. An estimate is never dropped because it disagrees — a
   $23B "foundation-model spend" figure and a $30T "labor
   substitution" pitch can both be true of different definitions, and
   the table shows which definition each uses. Follow it with a
   reading that OPENS with the range the memo adopts and why that
   definition is the right one for this company, then explains the
   disagreements in plain words (what each counts that the others do
   not). Then the "Market Sizing" table — ALWAYS all three rows
   TAM | SAM | SOM, columns Definition | Size today | Size at exit
   year | CAGR | Basis/source, where Basis/source names the estimate
   row it rests on or states the memo's own inputs and factors. Rows
   without a disclosed or derivable figure follow the missing-data
   rule; never substitute a bigger adjacent market's number. Then
   chart slot `chart_market_size`: a
   `chart` block (grouped_bar; x = TAM / SAM / SOM; one series for
   today and one for the exit year, labeled with their actual years)
   built ONLY from the table's disclosed or derivable figures,
   followed by one interpretation sentence. When the series is not
   disclosed, no chart: write the chart-omitted fallback line instead.
3. Growth drivers: each claimed driver gets one sentence of claim and
   one datum supporting it. A driver with no supporting datum is named
   as an assumption.
4. The ceiling question: argue whether this market caps the company
   nearer $20B, $100B, or $500B of enterprise value, and say which
   assumption moves it between those bands. Open with the one-line
   answer; end by restating the verdict.
5. Policy & regulation — never silently omitted: name the regimes that
   constrain or subsidize the business (data, export, sector-specific,
   procurement). When none applies, write the sentence "No regulatory
   regime materially constrains this business today" and say why that
   could change.

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
- business model and unit economics
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
```

1,100-1,400 words. Why customers pay, how the revenue machine works,
and whether a dollar in produces more than a dollar out. Content per
subsection:

1. Why customers pay: the buyer, the problem, the alternative they
   would otherwise use, and the economic case from the customer's side
   — with the strongest disclosed proof point.
2. Revenue model: a "Revenue Model" key_value table — Revenue streams |
   Pricing model | Contract length & terms | Revenue recognition
   character (recurring / committed / usage / project).
3. Key operating metrics: the "Key Operating Metrics" table with
   `component: "key_operating_metrics"` — exactly these 8 rows:
   Customer count | Largest-customer penetration | Top-10 revenue
   concentration | Net revenue retention | Gross retention | CAC
   payback | LTV/CAC or magic number | ARR per employee. Columns:
   Value | As of | Benchmark | Reading. The Reading cell is a verdict
   fragment ("healthy for stage", "below the bar because ..."), never
   a restatement of the number.
4. Revenue quality: the "Revenue Quality Split" table (recurring vs
   committed vs project vs concentrated revenue as rows, with share
   and the risk each carries), then the revenue-equation passage: walk
   收入 = 客户数 × 客单价 × 使用量 × 留存 — which factor drove growth to
   date, which must drive the next phase, and what evidence supports
   that hand-off.
5. Demand signals — both ways: the strongest demand signal (the
   pipeline, the backlog, the waitlist — whichever the company leads
   with) argued both ways: the honest bull reading AND the honest bear
   reading, then which reading the evidence favors. "The pipeline is
   valuable evidence of demand. It is not revenue." is the register to
   hit. Close with the backlog / committed-revenue statement: orders,
   prepayments, and reference checks where disclosed; the missing-data
   sentence where not.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 商业模式与单位经济 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: competitive_landscape
```yaml
id: competitive_landscape
scorecard_dimensions:
- industry_position
en_title: Competitive Landscape
zh_title: 竞争格局
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?competitive\s+landscape\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?竞争格局\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
floor: {}
pass_affinity:
- competitive_position
title_word_aliases: []
subsections:
- en: Industry map
  zh: 产业地图
- en: Competitor comparison
  zh: 竞争对比
- en: Replacement or coexistence
  zh: 替代还是共存
- en: Number one — now and in five years
  zh: 现在与五年后的第一名
```

900-1,200 words. Who wins this market, on what evidence. Content per
subsection:

1. Industry map: upstream suppliers → the company → downstream
   channels/customers, and where in that chain the profit pools sit
   today versus after the market matures.
2. Competitor comparison: the "Competitive Analysis" table with
   `component: "competitive_analysis"` — the target company FIRST,
   then 3-6 named competitors. Columns: Offering | Revenue/scale |
   Growth | Gross margin | Flagship customers | Last valuation | Core
   advantage. Undisclosed competitor cells follow the missing-data
   rule — a sparse competitor row is itself evidence about market
   opacity. Then chart slot `chart_competitor_scale`: a `chart` block
   (bar; x = the table's companies, target first; y = revenue or the
   stated scale measure) built ONLY from the table's disclosed
   figures, followed by one sentence on what the gap means. When the
   series is not disclosed, no chart: the chart-omitted fallback line.
3. Replacement or coexistence: the treatment with
   `component: "replacement_coexistence"`: does the company replace
   the incumbent stack or coexist with it, category by category — and
   what each answer implies for the growth ceiling.
4. Number one — now and in five years: three explicit answers — who
   leads today (with the datum), who most likely leads in 3-5 years,
   and WHY the structure of the market makes it so. If the company is
   not the projected leader, say what following the leader is worth at
   this price.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 行业地位 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: moat
```yaml
id: moat
scorecard_dimensions:
- moat
en_title: Moat & Defensibility
zh_title: 护城河
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?moat\s*(?:(?:&|and)\s*defensibility)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:护城河|护城河与壁垒)\s*[:：]?\s*$
components:
- moat
floor: {}
pass_affinity:
- competitive_position
title_word_aliases:
- moat and defensibility
- moat
subsections:
- en: Moat audit
  zh: 护城河审计
- en: The $5B question
  zh: 50亿美元问题
- en: Widening or narrowing
  zh: 变宽还是变窄
```

700-900 words. Whether the advantage survives success — because at
$5B+ every incumbent and well-funded copy will come. Content per
subsection:

1. Moat audit: the "Moat Audit" table with `component: "moat"` —
   ALWAYS all 8 fixed rows: Technology | Data | Distribution |
   Ecosystem | Switching cost | Network effect | Brand | Scale
   economics. Columns: Strength (Strong / Moderate / Weak / None) |
   Evidence | Trajectory (Widening / Stable / Narrowing). A dimension
   with no evidence reads "None — no evidence", never a blank and
   never a guess.
2. The $5B question: assume the company succeeds to a $5B+ outcome —
   what stops the then-obvious competitors from taking the margin?
   Answer from the audit rows, not from adjectives.
3. Widening or narrowing: weigh the trajectory column overall, address
   commoditization of the underlying technology base explicitly, and
   end on one sentence: the moat is widening / stable / narrowing, and
   what that implies for exit multiple assumptions.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 护城河 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: financial_analysis
```yaml
id: financial_analysis
scorecard_dimensions:
- revenue_growth_quality
en_title: Financial Analysis
zh_title: 财务分析
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?financial\s+analysis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?财务分析\s*[:：]?\s*$
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

1,000-1,300 words. Whether the reported growth is real, and whether
the forecast deserves belief. Content per subsection:

1. Financial history: the "Financial History" table with
   `component: "revenue"` titled "Revenue Picture": at least 3 fiscal
   years plus YTD where disclosed — Revenue | Growth | Gross margin |
   Opex | EBITDA/net | Burn | Cash. Missing years keep their rows.
2. Forecast: the "Forecast" table (+3 to +5 years, one row per year,
   with a "Key assumption" column naming the single assumption that
   year's number leans on hardest; cells without a disclosed or pinned
   basis follow the missing-data rule). Then chart slot
   `chart_revenue_trajectory`: a `chart` block (suggested line; x = the fiscal
   years, history then forecast; one series "Revenue") built ONLY
   from the tables' disclosed or pinned figures, followed by one
   sentence on the shape (accelerating, decelerating, hockey-stick
   where history is flat) that also names where actuals end and the
   forecast begins. When the series is not disclosed, no chart: the
   chart-omitted fallback line. Close with the forecast-credibility
   passage: compare the forecast's implied trajectory against the
   company's own history and disclosed peers' trajectories at the same
   scale; do the consequence arithmetic on the gap ("the forecast asks
   for NNx in N years; the best disclosed comparable did MMx").
3. Growth quality: the "Growth Quality" table with
   `component: "growth_bridge"`: fixed rows — Rule of 40 | Organic vs
   acquired growth | Pricing vs volume split | Incremental gross
   profit vs incremental opex | Burn multiple | Cash conversion &
   receivables. Columns: Value | Reading.
4. Revenue authenticity: subsidies, one-time items, related-party or
   channel-stuffed revenue, audit status. State what was checked and
   what could not be checked.
5. Healthier or hungrier: is each incremental revenue dollar getting
   cheaper or dearer to buy, and what follows for the financing risk.
   Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 收入增长与质量 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: team_governance
```yaml
id: team_governance
scorecard_dimensions:
- team_governance
en_title: Team & Governance
zh_title: 团队与治理
parity_en: ^\s*(?:(?:viii|8)[\.\、]\s*)?team\s*(?:&|and)\s*governance\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:viii|8|八)[\.\、]\s*)?(?:团队与治理|管理层与治理|团队与管理层)\s*[:：]?\s*$
components:
- board
floor: {}
pass_affinity:
- team_governance
title_word_aliases:
- team and governance
subsections:
- en: Leadership
  zh: 管理团队
- en: Board & ownership
  zh: 董事会与股权治理
- en: Founder-market fit
  zh: 创始人与赛道匹配
- en: Founder dependence
  zh: 创始人依赖
- en: Public-company readiness
  zh: 上市公司准备度
```

700-950 words. Whether this team can run the company the price
assumes, and whether shareholders can course-correct if not. Content
per subsection:

1. Leadership: the "Leadership" table — CEO and the 3-6 key executives
   — Role | Prior record (one line of facts) | Strength or gap (a
   verdict fragment). An empty key seat (CFO, especially, at pre-IPO
   stage) is a row: "Vacant — <consequence>".
2. Board & ownership: the "Board of Directors" table with
   `component: "board"` (members, affiliation, and strategic value),
   then an "Ownership & Governance" key_value block — Founder control
   (votes vs economics) | ESOP size | Investor roster | Protective
   provisions | Public-company readiness (this cell is a verdict:
   Ready / 12-18 months of work / Not close).
3. Founder-market fit: open with the one-line answer — are these
   founders demonstrably the right people for THIS problem — then the
   proof. For each founder who matters: what they built or ran before
   that this business actually requires (verified facts with dates,
   separated from self-claimed bio), what in their record maps to the
   next phase's hardest job, and where the record is silent. A
   celebrated background in a different discipline is stated as
   exactly that. End on the verdict sentence: fit proven by prior
   work, fit asserted but unproven, or fit absent.
4. Founder dependence: what breaks if the founder leaves or fails to
   scale, and what evidence exists that the organization runs beyond
   them.
5. Public-company readiness: audit history, financial reporting
   cadence, missing officers, related-party exposure — each stated as
   fact plus consequence, not as a checklist.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 团队与治理 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: valuation
```yaml
id: valuation
scorecard_dimensions:
- valuation
en_title: Valuation Analysis
zh_title: 估值分析
parity_en: ^\s*(?:(?:ix|9)[\.\、]\s*)?valuation(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ix|9|九)[\.\、]\s*)?(?:估值分析|估值)\s*[:：]?\s*$
components:
- time_base_integrity
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- valuation_exit
title_word_aliases:
- valuation analysis
- valuation
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
```

900-1,100 words. What the price already assumes, and what the company
is worth on the evidence. Content per subsection:

1. Comparables: the "Comparables" table — 4-8 disclosed comparables
   with growth-adjusted multiples, the target's row highlighted by
   listing it first. Columns: Company | Revenue | Growth | Multiple |
   Growth-adjusted multiple | Note. Then chart slot
   `chart_comps_multiples`: a `chart` block (suggested bar; x = the table's
   companies, target first; y = the revenue multiple) built ONLY from
   the table's disclosed figures, followed by one sentence placing the
   target's entry multiple against the set. When the multiples are not
   disclosed, no chart: the chart-omitted fallback line.
2. Valuation methods: the "Valuation Methods" table — ALWAYS these 3
   method rows: Comparable companies | Precedent transactions | DCF /
   earnings power. Columns: Result or range | Basis | Why trusted or
   not. A method that cannot be run states WHY in its row ("No
   positive FCF within the forecast — DCF not computable"), never
   disappears. Final row: "Fair value range", stating the range this
   memo concludes.
3. Time-base integrity: the "Time-Base Integrity" table with
   `component: "time_base_integrity"`: the valuation marks in play
   (last priced round, current round, any secondary), their dates, and
   whether each mark is fresh or stale.
4. What is priced in: translate the entry multiple into the growth and
   margin the buyer is already paying for, with the arithmetic shown.
5. The case for each end: PAIRED advocate/counter passages with
   explicit sub-headings "Why this merits $X" and "Why the cap is
   $Y" — $X is the fair-value range's HIGH end (the strongest honest
   case that the company earns it), $Y the LOW end (the strongest
   honest case that value stops there) — each argued from the tables
   above. Close with the both-ways passage on the round dynamics:
   oversubscription, insider support, or a stale mark — read it both
   as validation and as adverse-selection risk, then say which reading
   the evidence favors.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 估值 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: returns_exit
```yaml
id: returns_exit
scorecard_dimensions:
- exit_certainty
en_title: Return & Exit Analysis
zh_title: 回报测算与退出分析
parity_en: ^\s*(?:(?:x|10)[\.\、]\s*)?returns?\s*(?:&|and)\s*exit(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:x|10|十)[\.\、]\s*)?(?:回报测算与退出分析|回报与退出分析|退出分析)\s*[:：]?\s*$
components:
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- growth_bridge
- valuation_exit
title_word_aliases:
- return and exit analysis
- return analysis
- exit analysis
role: valuation
subsections:
- en: Scenario analysis
  zh: 情景分析
- en: Return decomposition
  zh: 回报分解
- en: Exit map
  zh: 退出路径
- en: Catalyst timeline
  zh: 催化剂时间线
- en: Growth or multiple
  zh: 增长还是倍数
```

1,000-1,200 words. What this investment returns in each world, and how
the money actually comes back. Content per subsection:

1. Scenario analysis: the "Scenario Analysis" table with
   `component: "scenario_analysis"`: rows bear | base | bull, columns
   Exit year | Exit-year revenue | Exit multiple | Exit valuation |
   Dilution assumption | Value to this round | Gross MOIC | IRR. Every
   numeric cell repeats the pinned scenario numbers from the shared
   fact sheet exactly; cells the pins do not state follow the
   missing-data rule. No new scenario numbers may be invented here.
   Then chart slot `chart_return_scenarios`: a `chart` block (suggested bar;
   x = Bear / Base / Bull; y = gross MOIC as a plain number) built
   ONLY from the pinned MOICs, followed by its one-sentence reading.
2. Return decomposition: how much of the base return comes from
   revenue growth versus multiple change ("NNx from growth × 0.MMx
   from multiple compression = base MOIC"), with a small table or the
   arithmetic in prose. State the crossover: at what exit multiple the
   return goes to zero. Then chart slot `chart_return_decomposition`:
   a `chart` block (suggested bar; x = Growth factor / Multiple factor / Base
   MOIC; y = the three factors) from those same numbers, with its
   one-sentence reading. When the decomposition cannot be computed
   from pinned numbers, no chart: the chart-omitted fallback line.
3. Exit map: the "Exit Map" table — the next 4 calendar years × the
   three routes (IPO / M&A / secondary), each cell Readiness +
   Likelihood. Follow with one passage per route: IPO readiness
   against the governance section's verdict; M&A with NAMED plausible
   acquirers and the antitrust or strategic constraint on each;
   secondary market depth for this name.
4. Catalyst timeline: the "Catalyst Timeline" table — 3-6 dated
   catalysts over the next 12-36 months, each with the metric it moves
   and the direction.
5. Growth or multiple: which the return depends on more, and how
   exposed the outcome is to multiple compression alone. Take at least
   one non-premium outcome (the bear case, or a flat exit multiple)
   and show what happens to this round's money, in dollars and MOIC,
   before later dilution. Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 退出确定性 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: investment_risk
```yaml
id: investment_risk
scorecard_dimensions:
- risk_reward
en_title: Investment Risk
zh_title: 风险分析
parity_en: ^\s*(?:(?:xi|11)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:xi|11|十一)[\.\、]\s*)?(?:风险分析|投资风险)\s*[:：]?\s*$
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

1,000-1,300 words. The risks that actually kill the return, argued —
not listed. Content per subsection:

1. The center of gravity: one paragraph naming the risk profile's
   center of gravity (which single risk carries the thesis).
2. Risk cards: 4-6 per-risk cards, ordered by rating highest first,
   using EXACTLY the risk list and ratings the shared fact sheet pins.
   Each card is a level-3 heading plus a key_value table with
   `component: "risk_register"`. The heading is the pinned summary — a
   complete verdict sentence with a finite verb ("The entry price
   already assumes success — ordinary execution earns nothing"), never
   a topic label like "Entry Price". Card rows: Risk Type | Why it
   matters (fact → failure mode → economic consequence, with the
   arithmetic when quantifiable) | What we watch (the observable
   leading indicator) | Mitigation (the real mechanism — company
   action, deal structure, or position sizing; when none exists: "No
   structural mitigation exists. <consequence>") | Likelihood | Risk
   Rating N/10.
3. Disconfirming evidence: the treatment with
   `component: "disconfirming_evidence"`: the strongest facts AGAINST
   this memo's recommendation, stated fairly, each with one sentence
   on how much weight it deserves.
4. Downside scenario & verdict: narrate the bear case as a sequence of
   events (which risk fires first, what it triggers), ending in the
   pinned bear numbers. Then weigh the rated risks against the return
   analysis in one short paragraph, ending on a verdict sentence.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 风险收益比 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: investment_decision
```yaml
id: investment_decision
en_title: Investment Decision
zh_title: 最终投资决定
parity_en: ^\s*(?:(?:xii|12)[\.\、]\s*)?(?:final\s+)?investment\s+decision\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:xii|12|十二)[\.\、]\s*)?(?:最终投资决定|投资决定|投资结论)\s*[:：]?\s*$
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

700-900 words. The section that decides. Content per subsection:

1. The six questions: the "Six Questions" table with
   `component: "evidence_thresholds"` titled "Evidence Thresholds —
   The Six Questions" — ALWAYS these fixed rows, each answered Yes /
   No / Qualified with a one-line basis: Is the market big enough to
   matter? | Is the company top-1-3 with evidence? | Does the moat
   survive success? | Is the growth real and healthy? | Does the price
   leave a return? | Can we get our money out? Every No or Qualified
   answer gets a follow-up paragraph naming what evidence would flip
   it.
2. Scorecard: the "Scorecard" table — the 9 fixed dimensions with
   their weights — 市场空间与增速 15 | 行业地位 15 | 护城河 15 |
   收入增长与质量 15 | 商业模式与单位经济 10 | 团队与治理 10 | 估值 10 |
   退出确定性 5 | 风险收益比 5 — columns Score | Why (one line). When
   the shared fact sheet pins a scorecard, repeat its scores and
   why-lines exactly and state the pinned total; otherwise score each
   dimension here from the owning section's verdict. Close the table
   with the total row and the threshold sentence: 80+ = investable,
   70-79 = watch list, below 70 = pass.
3. Demonstrated vs unresolved: two matched lists of EQUAL length (3-5
   items each) — "What is demonstrated" and "What remains unresolved"
   — each item one sentence with its number or its gap.
4. Recommendation: the recommendation callout with
   `component: "investment_decision"`: repeat the pinned
   recommendation sentence exactly, then entry, the pinned base-case
   outcome, holding period, exit route, and the fund placeholders
   verbatim: "Proposed amount: [TO BE DETERMINED BY IC]",
   "Allocation: [TO BE DETERMINED BY IC]", "Strategy: [重仓 / 跟投 /
   卡位 — IC to select]". A one-line legal disclosure paragraph with
   `component: "disclosures"` follows: this memo is not an offer to
   sell securities; terms are governed by definitive subscription
   documents. When the shared fact sheet pins a
   `decision_history_sentence`, restate it here verbatim as history,
   adjacent to (never inside) the recommendation callout.
5. Monitoring & triggers: the "Monitoring Indicators" table (投后监控):
   4-6 rows — Indicator | Current value | Trigger threshold | Response
   if triggered. When the verdict is a watch/pass, title this table
   "What changes the verdict" and make the triggers the re-entry
   conditions.
