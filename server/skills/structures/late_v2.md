---
stage: late
version: 2
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
sections; every run renders the same tables, the same chart slots, and
the same named passages, with missing data stated as missing (the
run-wide data-honesty rules ride the shared context). Chart slots are
BRIDGED for now: render each as a small data table plus interpretation;
a later round replaces the bridge with real charts.

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

900-1,100 words. This section is the memo an IC member reads when they
read nothing else: positioning, deal, thesis, numbers, risks, verdict.
Fixed block order:

1. Positioning paragraph (≤60 words): one plain-language sentence on what
   the company does and for whom, then one sentence placing it on the
   late-stage ladder.
2. Deal paragraph: what is being offered — round, instrument, size,
   price — and what that price already assumes. Interpret the entry
   multiple in the same breath ("...priced at ~NNx, which already
   includes X of the success case").
3. "Deal Snapshot" key_value table with `component: "deal_terms"`, exactly
   these 10 rows: Round | Instrument | Raise size | Pre-money | Post-money
   | Implied stake | Primary / secondary split | Use of proceeds |
   Co-investors | Expected close. Missing cells follow the missing-data
   rule ("Not disclosed — <implication>").
4. Exactly 3 thesis bullets, each a complete verdict sentence with its
   strongest supporting number: (a) the market is big enough to matter,
   (b) the company is (or is not) top-1-3 in it, (c) the price does (or
   does not) leave a return. A bullet the evidence cannot support states
   that instead — the thesis structure never bends to advocacy.
5. "Core Financials & Valuation" table with
   `component: "key_metrics_snapshot"` titled "Key Metrics Snapshot":
   7 rows — Revenue/ARR | Growth rate | Gross margin | Burn or FCF |
   Cash runway | Last/current valuation | Implied multiple — with columns
   for the two most recent actual years/periods plus a +3y column whose
   cells may contain ONLY numbers the pinned base scenario states
   (otherwise "Not modeled — no pinned basis").
6. At most 3 top-risk bullets, quoting the highest-rated pinned risk
   summaries verbatim with their N/10 ratings.
7. Verdict callout: state the recommendation sentence EXACTLY as the
   shared fact sheet pins it, then the entry valuation, the base-case
   outcome from the pinned scenarios, and the fund placeholders
   ("Proposed amount: [TO BE DETERMINED BY IC]", "Allocation: [TO BE
   DETERMINED BY IC]"). When the pin sheet carries a verdict tier and
   scorecard total, open the callout with "{tier} — {total}/100".
8. When the shared fact sheet pins a `decision_history_sentence`, state
   it verbatim as factual history — what BSH previously decided, never
   this memo's own conclusion.

## section: company_overview
```yaml
id: company_overview
en_title: Company Overview & Stage
zh_title: 公司概况与发展阶段
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s+overview(?:\s*(?:&|and)\s*stage)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司概况与发展阶段|公司概览|公司概况|项目简介)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- deployment_behavior
- gtm_operating_burden
title_word_aliases:
- company overview and stage
- company overview
```

800-1,000 words. What the company is, how it got here, and — the point
of this section — which claims about it are proven versus still a bet.
Fixed blocks:

1. "Company Facts" key_value table: Founded | Headquarters | Headcount |
   Founders & CEO | Ownership snapshot | What it sells, one line.
2. "Funding History" table: every disclosed round — Date | Round | Amount
   | Post-money | Lead investors | Price change vs prior round. An
   undisclosed round keeps its row.
3. Milestones narrative: 2-3 short paragraphs telling the company's
   development as cause and effect ("X worked, so Y followed"), not a
   date list.
4. REQUIRED passage headed "Proven and unproven" (Chinese:
   已验证与未验证): name the company's position on the late-stage ladder
   (PMF → Scale-up → Category leader → Pre-IPO → Public candidate),
   then list what the evidence has demonstrated and what remains
   asserted. Each item is one sentence with its supporting or missing
   datum. Close with one verdict sentence on whether the stage the
   round is priced for matches the stage the evidence supports.

## section: market_industry
```yaml
id: market_industry
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
```

900-1,100 words. Whether the market can carry the valuation, and what
could cap it. Fixed blocks:

1. Market-definition passage: what market the company actually competes
   in (not the largest label it markets), where it sits in the value
   chain, and who captures the value above and below it.
2. "Market Sizing" table — ALWAYS all three rows TAM | SAM | SOM, columns
   Definition | Size today | Size at exit year | CAGR | Basis/source.
   Rows without a disclosed or derivable figure follow the missing-data
   rule; never substitute a bigger adjacent market's number.
3. Chart slot `chart_market_size` (bridged): a small table of the sizing
   series plus one interpretation sentence, or the chart-omitted fallback
   line when the series is not disclosed.
4. Growth-drivers passage: each claimed driver gets one sentence of claim
   and one datum supporting it. A driver with no supporting datum is
   named as an assumption.
5. REQUIRED passage headed "The ceiling question" (Chinese: 天花板问题):
   argue whether this market caps the company nearer $20B, $100B, or
   $500B of enterprise value, and say which assumption moves it between
   those bands. End on the verdict sentence.
6. Policy & regulatory passage — never silently omitted: name the
   regimes that constrain or subsidize the business (data, export,
   sector-specific, procurement). When none applies, write the sentence
   "No regulatory regime materially constrains this business today" and
   say why that could change.

## section: product_business_model
```yaml
id: product_business_model
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
- business model and unit economics
```

1,100-1,400 words. Why customers pay, how the revenue machine works,
and whether a dollar in produces more than a dollar out. Fixed blocks:

1. "Why customers pay" opening passage: the buyer, the problem, the
   alternative they would otherwise use, and the economic case from the
   customer's side — with the strongest disclosed proof point.
2. "Revenue Model" key_value table: Revenue streams | Pricing model |
   Contract length & terms | Revenue recognition character (recurring /
   committed / usage / project).
3. "Key Operating Metrics" table with
   `component: "key_operating_metrics"` — exactly these 8 rows:
   Customer count | Largest-customer penetration | Top-10 revenue
   concentration | Net revenue retention | Gross retention | CAC payback
   | LTV/CAC or magic number | ARR per employee. Columns: Value | As of
   | Benchmark | Reading. The Reading cell is a verdict fragment
   ("healthy for stage", "below the bar because ..."), never a
   restatement of the number.
4. "Revenue Quality Split" table: recurring vs committed vs project vs
   concentrated revenue as rows, with share and the risk each carries.
5. Revenue-equation passage: walk 收入 = 客户数 × 客单价 × 使用量 × 留存 —
   which factor drove growth to date, which must drive the next phase,
   and what evidence supports that hand-off.
6. Both-ways passage on the strongest demand signal (the pipeline, the
   backlog, the waitlist — whichever the company leads with): the honest
   bull reading AND the honest bear reading, then which reading the
   evidence favors. "The pipeline is valuable evidence of demand. It is
   not revenue." is the register to hit.
7. Backlog / committed-revenue statement: orders, prepayments, and
   reference checks where disclosed; the missing-data sentence where not.

## section: competitive_landscape
```yaml
id: competitive_landscape
en_title: Competitive Landscape
zh_title: 竞争格局
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?competitive\s+landscape\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?竞争格局\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
floor: {}
pass_affinity:
- replacement_coexistence
- competitive_rights
title_word_aliases: []
```

900-1,200 words. Who wins this market, on what evidence. Fixed blocks:

1. Industry-map passage: upstream suppliers → the company → downstream
   channels/customers, and where in that chain the profit pools sit
   today versus after the market matures.
2. "Competitive Analysis" table with `component: "competitive_analysis"`:
   the target company FIRST, then 3-6 named competitors. Columns:
   Offering | Revenue/scale | Growth | Gross margin | Flagship customers
   | Last valuation | Core advantage. Undisclosed competitor cells
   follow the missing-data rule — a sparse competitor row is itself
   evidence about market opacity.
3. Chart slot `chart_competitor_scale` (bridged): revenue or scale of
   the table's companies as a small comparison table plus one sentence
   on what the gap means.
4. "Replacement vs. Coexistence" treatment with
   `component: "replacement_coexistence"`: does the company replace the
   incumbent stack or coexist with it, category by category — and what
   each answer implies for the growth ceiling.
5. REQUIRED passage headed "Number one — now and in five years": three
   explicit answers — who leads today (with the datum), who most likely
   leads in 3-5 years, and WHY the structure of the market makes it so.
   If the company is not the projected leader, say what following the
   leader is worth at this price.

## section: moat
```yaml
id: moat
en_title: Moat & Defensibility
zh_title: 护城河
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?moat\s*(?:(?:&|and)\s*defensibility)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:护城河|护城河与壁垒)\s*[:：]?\s*$
components:
- moat
floor: {}
pass_affinity:
- competitive_rights
- replacement_coexistence
title_word_aliases:
- moat and defensibility
- moat
```

700-900 words. Whether the advantage survives success — because at
$5B+ every incumbent and well-funded copy will come. Fixed blocks:

1. "Moat Audit" table with `component: "moat"` — ALWAYS all 8 fixed
   rows: Technology | Data | Distribution | Ecosystem | Switching cost |
   Network effect | Brand | Scale economics. Columns: Strength
   (Strong / Moderate / Weak / None) | Evidence | Trajectory
   (Widening / Stable / Narrowing). A dimension with no evidence reads
   "None — no evidence", never a blank and never a guess.
2. REQUIRED passage headed "The $5B question" (Chinese: 50亿美元问题):
   assume the company succeeds to a $5B+ outcome — what stops the
   then-obvious competitors from taking the margin? Answer from the
   audit rows, not from adjectives.
3. Closing verdict passage headed "Widening or narrowing": weigh the
   trajectory column overall, address commoditization of the underlying
   technology base explicitly, and end on one sentence: the moat is
   widening / stable / narrowing, and what that implies for exit
   multiple assumptions.

## section: financial_analysis
```yaml
id: financial_analysis
en_title: Financial Analysis
zh_title: 财务分析
parity_en: ^\s*(?:(?:vii|7)[\.\、]\s*)?financial\s+analysis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vii|7|七)[\.\、]\s*)?财务分析\s*[:：]?\s*$
components:
- revenue
- growth_bridge
floor: {}
pass_affinity:
- arithmetic_denominators
- growth_bridge
title_word_aliases: []
```

1,000-1,300 words. Whether the reported growth is real, and whether the
forecast deserves belief. Fixed blocks:

1. "Financial History" table with `component: "revenue"` titled
   "Revenue Picture": at least 3 fiscal years plus YTD where disclosed —
   Revenue | Growth | Gross margin | Opex | EBITDA/net | Burn | Cash.
   Missing years keep their rows.
2. "Forecast" table: +3 to +5 years, one row per year, with a "Key
   assumption" column naming the single assumption that year's number
   leans on hardest. Cells without a disclosed or pinned basis follow
   the missing-data rule.
3. "Growth Quality" table with `component: "growth_bridge"`: fixed rows —
   Rule of 40 | Organic vs acquired growth | Pricing vs volume split |
   Incremental gross profit vs incremental opex | Burn multiple | Cash
   conversion & receivables. Columns: Value | Reading.
4. Chart slot `chart_revenue_trajectory` (bridged): history + forecast
   revenue as a small series table plus one sentence on the shape
   (accelerating, decelerating, hockey-stick where history is flat).
5. Revenue-authenticity passage: subsidies, one-time items, related-party
   or channel-stuffed revenue, audit status. State what was checked and
   what could not be checked.
6. Forecast-credibility passage: compare the forecast's implied
   trajectory against the company's own history and disclosed peers'
   trajectories at the same scale; do the consequence arithmetic on the
   gap ("the forecast asks for NNx in N years; the best disclosed
   comparable did MMx").
7. Closing verdict passage headed "Healthier or hungrier" (Chinese:
   增长更健康还是更烧钱): is each incremental revenue dollar getting
   cheaper or dearer to buy, and what follows for the financing risk.

## section: team_governance
```yaml
id: team_governance
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
```

600-800 words. Whether this team can run the company the price assumes,
and whether shareholders can course-correct if not. Fixed blocks:

1. "Leadership" table: CEO and the 3-6 key executives — Role | Prior
   record (one line of facts) | Strength or gap (a verdict fragment).
   An empty key seat (CFO, especially, at pre-IPO stage) is a row:
   "Vacant — <consequence>".
2. "Board of Directors" table with `component: "board"`: members,
   affiliation, and strategic value; then an "Ownership & Governance"
   key_value block — Founder control (votes vs economics) | ESOP size |
   Investor roster | Protective provisions | Public-company readiness
   (this cell is a verdict: Ready / 12-18 months of work / Not close).
3. Verdict passage headed "Founder dependence": what breaks if the
   founder leaves or fails to scale, and what evidence exists that the
   organization runs beyond them.
4. "Public-company readiness" passage: audit history, financial
   reporting cadence, missing officers, related-party exposure — each
   stated as fact plus consequence, not as a checklist.

## section: valuation
```yaml
id: valuation
en_title: Valuation Analysis
zh_title: 估值分析
parity_en: ^\s*(?:(?:ix|9)[\.\、]\s*)?valuation(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ix|9|九)[\.\、]\s*)?(?:估值分析|估值)\s*[:：]?\s*$
components:
- time_base_integrity
floor:
  require_valuation_refs: true
pass_affinity:
- time_base
- arithmetic_denominators
- valuation_comps
title_word_aliases:
- valuation analysis
- valuation
```

900-1,100 words. What the price already assumes, and what the company
is worth on the evidence. Fixed blocks:

1. "Comparables" table: 4-8 disclosed comparables with growth-adjusted
   multiples, the target's row highlighted by listing it first. Columns:
   Company | Revenue | Growth | Multiple | Growth-adjusted multiple |
   Note.
2. Chart slot `chart_comps_multiples` (bridged): the comparables'
   multiples as a small table plus one sentence placing the target's
   entry multiple against the set.
3. "Valuation Methods" table — ALWAYS these 3 method rows: Comparable
   companies | Precedent transactions | DCF / earnings power. Columns:
   Result or range | Basis | Why trusted or not. A method that cannot be
   run states WHY in its row ("No positive FCF within the forecast —
   DCF not computable"), never disappears. Final row: "Fair value
   range", stating the range this memo concludes.
4. "Time-Base Integrity" table with `component: "time_base_integrity"`:
   the valuation marks in play (last priced round, current round,
   any secondary), their dates, and whether each mark is fresh or stale.
5. Passage headed "What is priced in" (Chinese: 当前价格已经包含了什么):
   translate the entry multiple into the growth and margin the buyer is
   already paying for, with the arithmetic shown.
6. PAIRED advocate/counter passages with explicit headings "Why this
   merits $X" and "Why the cap is $Y", where $X/$Y are the fair-value
   range ends: the strongest honest case for each end of the range,
   argued from the tables above.
7. Both-ways passage on the round dynamics: oversubscription, insider
   support, or a stale mark — read it both as validation and as
   adverse-selection risk, then say which reading the evidence favors.

## section: returns_exit
```yaml
id: returns_exit
en_title: Return & Exit Analysis
zh_title: 回报测算与退出分析
parity_en: ^\s*(?:(?:x|10)[\.\、]\s*)?returns?\s*(?:&|and)\s*exit(?:\s+analysis)?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:x|10|十)[\.\、]\s*)?(?:回报测算与退出分析|回报与退出分析|退出分析)\s*[:：]?\s*$
components:
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- arithmetic_denominators
- time_base
- growth_bridge
- exit_paths
title_word_aliases:
- return and exit analysis
- return analysis
- exit analysis
role: valuation
```

1,000-1,200 words. What this investment returns in each world, and how
the money actually comes back. Fixed blocks:

1. "Scenario Analysis" table with `component: "scenario_analysis"`:
   rows bear | base | bull, columns Exit year | Exit-year revenue |
   Exit multiple | Exit valuation | Dilution assumption | Value to this
   round | Gross MOIC | IRR. Every numeric cell repeats the pinned
   scenario numbers from the shared fact sheet exactly; cells the pins
   do not state follow the missing-data rule. No new scenario numbers
   may be invented here.
2. Return-decomposition passage plus small table: how much of the base
   return comes from revenue growth versus multiple change ("NNx from
   growth × 0.MMx from multiple compression = base MOIC"). State the
   crossover: at what exit multiple the return goes to zero.
3. Chart slots `chart_return_scenarios` and `chart_return_decomposition`
   (bridged): the scenario MOICs and the decomposition as small tables,
   each with its one-sentence reading.
4. "Exit Map" table: the next 4 calendar years × the three routes (IPO /
   M&A / secondary), each cell Readiness + Likelihood. Follow with one
   passage per route: IPO readiness against the governance section's
   verdict; M&A with NAMED plausible acquirers and the antitrust or
   strategic constraint on each; secondary market depth for this name.
5. "Catalyst Timeline" table: 3-6 dated catalysts over the next 12-36
   months, each with the metric it moves and the direction.
6. Consequence-arithmetic passage: take at least one non-premium outcome
   (the bear case, or a flat exit multiple) and show what happens to
   this round's money, in dollars and MOIC, before later dilution.
7. Closing verdict passage headed "Growth or multiple": which the return
   depends on more, and how exposed the outcome is to multiple
   compression alone.

## section: investment_risk
```yaml
id: investment_risk
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
- competitive_rights
title_word_aliases:
- investment risk
- risk analysis
role: risk
```

1,000-1,300 words. The risks that actually kill the return, argued —
not listed. Fixed blocks:

1. One-paragraph intro naming the risk profile's center of gravity
   (which single risk carries the thesis).
2. 4-6 per-risk cards, ordered by rating highest first, using EXACTLY
   the risk list and ratings the shared fact sheet pins. Each card is a
   heading plus a key_value table with `component: "risk_register"`.
   The heading is the pinned summary — a complete verdict sentence with
   a finite verb ("The entry price already assumes success — ordinary
   execution earns nothing"), never a topic label like "Entry Price".
   Card rows: Risk Type | Why it matters (fact → failure mode →
   economic consequence, with the arithmetic when quantifiable) | What
   we watch (the observable leading indicator) | Likelihood | Risk
   Rating N/10.
3. Disconfirming-evidence treatment with
   `component: "disconfirming_evidence"`: the strongest facts AGAINST
   this memo's recommendation, stated fairly, each with one sentence on
   how much weight it deserves.
4. Downside-scenario passage: narrate the bear case as a sequence of
   events (which risk fires first, what it triggers), ending in the
   pinned bear numbers.
5. Closing risk/reward verdict passage: weigh the rated risks against
   the return analysis in one short paragraph, ending on a verdict
   sentence.

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
```

700-900 words. The section that decides. Fixed blocks:

1. "Six Questions" table with `component: "evidence_thresholds"` titled
   "Evidence Thresholds — The Six Questions" — ALWAYS these fixed rows,
   each answered Yes / No / Qualified with a one-line basis:
   Is the market big enough to matter? | Is the company top-1-3 with
   evidence? | Does the moat survive success? | Is the growth real and
   healthy? | Does the price leave a return? | Can we get our money
   out? Every No or Qualified answer gets a follow-up paragraph naming
   what evidence would flip it.
2. "Scorecard" table: the 9 fixed dimensions with their weights —
   市场空间与增速 15 | 行业地位 15 | 护城河 15 | 收入增长与质量 15 |
   商业模式与单位经济 10 | 团队与治理 10 | 估值 10 | 退出确定性 5 |
   风险收益比 5 — columns Score | Why (one line). When the shared fact
   sheet pins a scorecard, repeat its scores and why-lines exactly and
   state the pinned total; otherwise score each dimension here from the
   owning section's verdict. Close the table with the total row and the
   threshold sentence: 80+ = investable, 70-79 = watch list, below
   70 = pass.
3. Symmetric close: two matched lists of EQUAL length (3-5 items each) —
   "What is demonstrated" and "What remains unresolved" — each item one
   sentence with its number or its gap.
4. Recommendation callout with `component: "investment_decision"`:
   repeat the pinned recommendation sentence exactly, then entry, the
   pinned base-case outcome, holding period, exit route, and the fund
   placeholders verbatim: "Proposed amount: [TO BE DETERMINED BY IC]",
   "Allocation: [TO BE DETERMINED BY IC]", "Strategy: [重仓 / 跟投 /
   卡位 — IC to select]".
5. "Monitoring Indicators" table (投后监控): 4-6 rows — Indicator |
   Current value | Trigger threshold | Response if triggered. When the
   verdict is a watch/pass, title this table "What changes the verdict"
   and make the triggers the re-entry conditions.
6. A one-line legal disclosure paragraph with
   `component: "disclosures"`: this memo is not an offer to sell
   securities; terms are governed by definitive subscription documents.
7. When the shared fact sheet pins a `decision_history_sentence`,
   restate it here verbatim as history, adjacent to (never inside) the
   recommendation callout.
