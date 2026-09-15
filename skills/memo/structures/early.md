---
stage: early
version: 1
scorecard:
  market_size_growth: 20
  industry_position: 5
  moat: 10
  revenue_growth_quality: 10
  business_model_ue: 10
  team_governance: 25
  valuation: 10
  exit_certainty: 5
  risk_reward: 5
components:
- key_metrics_snapshot
- deal_terms
- board
- revenue
- key_operating_metrics
- scenario_analysis
- risk_register
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

Early-stage structure profile (pre-seed through Series A): seven fixed
sections. An early company has little disclosed history, so this
structure judges the bet, the founders, and the deal mechanics instead
of pretending to a late-stage evidence base — and its data-honesty duty
is heavier, not lighter: what is unknown is stated as unknown, every
time. No moat table, no growth bridge, no comparables chapter: those
claims cannot be evidenced at this stage, and the sections that replace
them say what is knowable instead. Scorecard weights for this stage
(reinterpreted dimensions): 市场空间与增速 20 | 行业地位（切入点）5 |
护城河（潜在壁垒）10 | 收入增长与质量（早期验证）10 | 商业模式与单位经济 10 |
团队与治理 25 | 估值（交易条款）10 | 退出确定性 5 | 风险收益比 5.
Every section is organized under its declared numbered subsections;
the run-wide data-honesty, navigation, and chart rules ride the shared
context.

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
- en: The bet
  zh: 这笔投资的赌注
- en: The round
  zh: 本轮融资方案
- en: Investment highlights
  zh: 核心投资亮点
- en: Key risks
  zh: 核心风险提示
- en: Recommendation
  zh: 投资结论与建议
```

500-700 words. The summary's one job is to say what matters. It
contains NO tables — every number it needs lives in a sentence that
interprets it (the Key Facts table lives in the Founders & Company
section, the Deal Terms table in Deal Terms & Required Returns).
Content per subsection:

1. The bet: one short paragraph stating, in plain language, exactly
   what has to become true for this investment to work — the market
   emerges, this team wins it, the entry terms pay for the risk. This
   is the honest register of an early-stage memo: a bet named as a
   bet. Then one positioning sentence (≤40 words): what the company
   does, for whom, and what exists today (product shipped / pilot /
   prototype).
2. The round: the instrument (SAFE/note/priced), raise size, valuation
   or cap, and what the terms already assume — interpreted in the same
   breath. Prose only.
3. Investment highlights: OPEN with the pinned case-summary sentence
   from the shared fact sheet, the company's name in place of "The
   case" — which dimensions carry the bet and which are weak, with
   their scores (at this stage the team and the market usually carry
   it). Then ONE `bullets` block with `"component":
   "investment_highlights"` and EXACTLY three items, one per pinned
   highlight, in pinned order: the pinned headline VERBATIM (plain
   text, no asterisks or markdown; the renderer bolds it), then the
   pinned evidence sentences, every number introduced
   by what it measures and where it comes from before the reader meets
   the figure. Never a naked topic label ("Team.", "Market."), never
   a new number.
4. Key risks: ONE `bullets` block with `"component": "key_risks"` and
   EXACTLY three items — the three highest-rated pinned risks in
   pinned order, each "<Area label> — <pinned summary verbatim>.
   Impact: <pinned impact verbatim>. (N/10, <likelihood> likelihood)".
5. Recommendation: a verdict callout — the pinned recommendation
   sentence verbatim, the entry terms, the required-exit arithmetic in
   one line ("a 3x fund return needs a $NNN M exit"), and the fund
   placeholders verbatim. With a pinned verdict tier and scorecard,
   open on "{tier} — {total}/100". A pinned
   `decision_history_sentence` is stated verbatim after the callout as
   history.

## section: company_team
```yaml
id: company_team
scorecard_dimensions:
- team_governance
en_title: Founders & Company
zh_title: 创始团队与公司
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?founders?\s*(?:&|and)\s*company\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:创始团队与公司|创始人与公司|团队与公司)\s*[:：]?\s*$
components:
- board
- key_metrics_snapshot
floor: {}
pass_affinity:
- team_governance
title_word_aliases:
- founders and company
subsections:
- en: Key facts
  zh: 关键事实
- en: Founders
  zh: 创始团队
- en: What exists today
  zh: 现有进展
- en: Board & governance
  zh: 董事会与治理
- en: Why this team wins — or doesn't
  zh: 团队为什么能赢
```

800-1,000 words. At this stage the team carries 25 of 100 points; this
section earns or denies them. Content per subsection:

1. Key facts: the "Key Facts" table with
   `component: "key_metrics_snapshot"` titled "Key Metrics Snapshot":
   Stage & round | Raise & instrument | Valuation or cap | Revenue or
   traction proxy | Runway | Team size | Founded. Missing cells: "Not
   disclosed — <implication>".
2. Founders: the "Founders" table — one row PER FOUNDER: Name & role |
   Verified track record (facts with dates, separated from
   self-claimed bio) | Domain edge (why this person, this problem) |
   Commitment (full-time? vested? prior exits?).
3. What exists today: an inventory passage of the demonstrable —
   product state, code or hardware shipped, pilots running, team
   headcount by function — each item dated.
4. Board & governance: the "Board of Directors" table with
   `component: "board"`: members and affiliation; a company with no
   formal board states "None — governance rests entirely with the
   founders" as the row, plus the consequence.
5. Why this team wins — or doesn't: weigh the founders' edge against
   what the problem actually requires; name the gap the next two hires
   must fill. Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 团队与治理 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: market_thesis
```yaml
id: market_thesis
scorecard_dimensions:
- market_size_growth
- industry_position
en_title: Market & Thesis
zh_title: 市场与投资逻辑
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?market\s*(?:&|and)\s*thesis\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?(?:市场与投资逻辑|市场与论点|市场分析)\s*[:：]?\s*$
components: []
floor: {}
pass_affinity:
- market_sizing
title_word_aliases:
- market and thesis
subsections:
- en: The wedge
  zh: 切入点
- en: Market size
  zh: 市场空间
- en: Why now
  zh: 为什么是现在
- en: The ceiling question
  zh: 天花板问题
```

600-800 words. Whether the wedge opens a market big enough to matter.
Content per subsection:

1. The wedge: the specific entry problem, why it is urgent for the
   first customers, and what larger market winning it opens.
2. Market size: FIRST the "Market estimates" table — one row per
   estimate found (syndicated houses, the founder's pitch-deck TAM
   labeled as such, analyst sizing, and LAST the memo's own
   derivation), columns Source | What it counts (definition) | Value |
   Year | How it was built; nothing is dropped for disagreeing. Follow
   it with a reading that OPENS with the range the memo adopts and
   why, then explains the disagreements in plain words. Then the
   "Market Sizing" table — TAM | SAM | SOM rows always, columns
   Definition | Size today | Size in 5-7y | Basis/source (naming the
   estimate row or the memo's own inputs each rests on). At this stage
   most cells will be estimates or missing — say which is which; never
   present a founder's pitch-deck TAM as independent. Then chart slot
   `chart_market_size`: a `chart` block
   (grouped_bar; x = TAM / SAM / SOM; one series for today and one for
   the 5-7y horizon, labeled with their years) built ONLY from the
   table's disclosed or independently derived figures, followed by one
   interpretation sentence. When the sizing is estimates without an
   independent basis, no chart: the chart-omitted fallback line.
3. Why now: the technology, cost, or regulatory change that makes this
   buildable and buyable today when it wasn't five years ago — with a
   datum, or named as an assumption.
4. The ceiling question — weighted MORE at this stage, because the
   market bet is most of the bet: if everything works, is this a $500M
   company or a $20B one, and which assumption decides it. Verdict
   sentence last.

Close this section with its pinned scorecard sentences — one per dimension, "This dimension scores N of M." for 市场空间与增速、行业地位 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: product_traction
```yaml
id: product_traction
scorecard_dimensions:
- moat
- revenue_growth_quality
- business_model_ue
en_title: Product & Early Validation
zh_title: 产品与早期验证
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?product\s*(?:&|and)\s*early\s+validation\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?(?:产品与早期验证|产品与验证|早期验证)\s*[:：]?\s*$
components:
- revenue
- key_operating_metrics
floor: {}
pass_affinity:
- deployment_behavior
- gtm_operating_burden
title_word_aliases:
- product and early validation
subsections:
- en: The product today
  zh: 产品现状
- en: Traction
  zh: 早期验证
- en: Operating metrics
  zh: 运营指标
- en: The strongest signal — both ways
  zh: 最强信号的两面
- en: What compounds
  zh: 什么能积累成壁垒
```

700-900 words. What has actually been validated, versus claimed.
Content per subsection:

1. The product today: what the product does today (not the roadmap),
   and the honest distance between today's product and the thesis
   product.
2. Traction: the "Traction" table with `component: "revenue"` titled
   "Revenue & Traction Picture" — exactly these 6 rows: Revenue/ARR |
   Paying customers | Pilots or LOIs | Usage metric (the one the
   company leads with) | Retention or repeat usage | Pipeline.
   Columns: Value | As of | Reading — and every Reading cell must
   state whether the row is EVIDENCE or REVENUE ("6 pilots — evidence
   of interest, not revenue").
3. Operating metrics: the "Key Operating Metrics" table with
   `component: "key_operating_metrics"`: the handful that exist at
   this stage — burn, runway, headcount, cost per pilot/unit — Value |
   As of | Reading. Rows that cannot exist yet say so.
4. The strongest signal — both ways: the strongest validation signal
   argued both ways: the bull reading, the bear reading, and which the
   evidence favors.
5. What compounds: the moat-potential question asked honestly — IF
   this works, what accumulates (data, network, switching cost, brand)
   that a copy cannot shortcut? At this stage the answer is potential,
   and is labeled as such.

Close this section with its pinned scorecard sentences — one per dimension, "This dimension scores N of M." for 护城河、收入增长与质量、商业模式与单位经济 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: deal_returns
```yaml
id: deal_returns
scorecard_dimensions:
- valuation
- exit_certainty
en_title: Deal Terms & Required Returns
zh_title: 交易条款与回报测算
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?deal\s+terms\s*(?:&|and)\s*required\s+returns?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?(?:交易条款与回报测算|交易与回报|交易条款)\s*[:：]?\s*$
components:
- deal_terms
- scenario_analysis
floor:
  require_valuation_refs: true
pass_affinity:
- arithmetic_denominators
- time_base
- valuation_comps
- exit_paths
title_word_aliases:
- deal terms and required returns
- deal terms
role: valuation
subsections:
- en: Deal terms
  zh: 交易条款
- en: Entry vs stage norms
  zh: 估值对标
- en: Required exits
  zh: 回报所需退出
- en: The merely-good outcome
  zh: 一般成功情形
- en: Do the terms pay for the risk
  zh: 条款是否补偿风险
```

800-1,000 words. Early-stage price discipline lives here: the
instrument's mechanics and the outcome the entry price already
requires. Content per subsection:

1. Deal terms: the "Deal Terms" table with `component: "deal_terms"` —
   exactly these rows: Instrument (SAFE/note/priced) | Raise size |
   Valuation or cap | Discount | Pro-rata rights | Information rights
   | Board seat | Liquidation preference | Option pool shuffle. A
   missing TERM here is a RISK, not a footnote: "Not disclosed —
   uncapped exposure to the next round's price", and material gaps are
   echoed in the risk section.
2. Entry vs stage norms: the entry valuation against disclosed stage
   norms for this sector and geography — above, at, or below, and what
   being above demands.
3. Required exits: the "Required Exits" table with
   `component: "scenario_analysis"` — rows 3x | 5x | 10x gross MOIC,
   columns Required exit valuation | Dilution assumption | Implied
   revenue at exit (at a stated multiple) | How plausible (verdict
   fragment). Cells repeat the pinned scenario numbers exactly where
   pins exist; the required-exit arithmetic is shown in-line. Then
   chart slot `chart_required_exits`: a `chart` block (suggested bar; x = 3x /
   5x / 10x; y = the required exit valuation) from those same
   numbers, followed by its one-sentence reading.
4. The merely-good outcome: what a merely-good outcome (the most
   common early-stage "success": a $50-150M acquisition) returns to
   this cheque after the stack above it — in dollars and MOIC.
5. Do the terms pay for the risk: the price against the bet, in two or
   three sentences. Open with the one-line answer; end by restating the verdict.

Close this section with its pinned scorecard sentences — one per dimension, "This dimension scores N of M." for 估值、退出确定性 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: risks_milestones
```yaml
id: risks_milestones
scorecard_dimensions:
- risk_reward
en_title: Risks & Milestones
zh_title: 风险与里程碑
parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?risks?\s*(?:&|and)\s*milestones?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:风险与里程碑|风险分析|投资风险)\s*[:：]?\s*$
components:
- risk_register
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
title_word_aliases:
- risks and milestones
- risk analysis
role: risk
subsections:
- en: The center of gravity
  zh: 风险重心
- en: Risk cards
  zh: 风险卡片
- en: Disconfirming evidence
  zh: 反面证据
- en: Milestone map
  zh: 里程碑地图
- en: Risk/reward verdict
  zh: 风险收益结论
```

700-900 words. What kills this company, and what proves it is working.
Content per subsection:

1. The center of gravity: one paragraph naming which single risk
   carries the bet.
2. Risk cards: 4-6 per-risk cards, ordered by rating highest first,
   using EXACTLY the pinned risk list and ratings. Card = level-3
   heading (the pinned summary — a complete verdict sentence, never a
   topic label) + key_value table with `component: "risk_register"`,
   rows: Risk Type | Why it matters (fact → failure mode →
   consequence) | What we watch (at this stage: the MILESTONE that
   retires the risk — the observable proof point with its expected
   date, because that is what the next round prices) | Mitigation
   (the real mechanism — company action, deal structure, or position
   sizing; when none exists: "No structural mitigation exists.
   <consequence>") | Likelihood | Risk Rating N/10.
3. Disconfirming evidence: the treatment with
   `component: "disconfirming_evidence"`: the strongest facts against
   the bet, each weighed in one sentence.
4. Milestone map: the "Milestone Map" table — the next 18-24 months —
   Milestone | Expected date | Risk it retires | What missing it
   means. This is the spending plan for the raise, read as evidence.
5. Risk/reward verdict: the closing risk/reward verdict paragraph.

Close this section with its pinned scorecard sentence — "This dimension scores N of M." for 风险收益比 — repeated verbatim from the shared fact sheet (the pin-echo gate rejects the section without it, and a regenerated section drops it most often).

## section: investment_decision
```yaml
id: investment_decision
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
- en: The six questions
  zh: 六个关键问题
- en: Scorecard
  zh: 评分卡
- en: Demonstrated vs still a bet
  zh: 已证明与仍是赌注
- en: Recommendation
  zh: 投资建议
- en: Monitoring & triggers
  zh: 投后监控与触发条件
```

500-700 words. Content per subsection:

1. The six questions: the "Six Questions" table with
   `component: "evidence_thresholds"` titled "Evidence Thresholds —
   The Six Questions" — the early-stage six, each answered Yes / No /
   Qualified with a one-line basis: Does the wedge open a market that
   matters? | Is this team the reason to believe? | Is there real
   early validation, not just interest? | Could the advantage compound
   if it works? | Do the terms pay for the risk? | Can a
   fund-returning exit plausibly exist? Every No or Qualified gets a
   what-would-flip-it paragraph.
2. Scorecard: the "Scorecard" table — the 9 fixed dimensions with
   EARLY weights and reinterpretations: 市场空间与增速 20 |
   行业地位（切入点）5 | 护城河（潜在壁垒）10 |
   收入增长与质量（早期验证）10 | 商业模式与单位经济 10 | 团队与治理 25 |
   估值（交易条款）10 | 退出确定性 5 | 风险收益比 5. Columns Score | Why
   (one line). Pinned scorecards are repeated exactly; close with the
   total row and the threshold sentence (80+ invest / 70-79 watch /
   below 70 pass).
3. Demonstrated vs still a bet: equal-length lists (3-4 each) "What is
   demonstrated" / "What remains a bet" — the early-stage honest
   framing of unresolved items.
4. Recommendation: the recommendation callout with
   `component: "investment_decision"`: pinned recommendation sentence
   verbatim, the entry terms, the required-exit line, and the fund
   placeholders verbatim. A one-line legal disclosure paragraph with
   `component: "disclosures"` follows. A pinned
   `decision_history_sentence` is restated verbatim as history.
5. Monitoring & triggers: the "Monitoring Indicators" table (投后监控):
   3-5 rows — Indicator | Current value | Trigger threshold | Response
   — drawn from the Milestone Map. Titled "What changes the verdict"
   when the verdict is watch/pass.
