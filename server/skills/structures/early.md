---
stage: early
version: 1
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
Chart slots are bridged as small tables until the chart round.

## section: executive_summary
```yaml
id: executive_summary
en_title: Executive Summary
zh_title: 执行摘要
parity_en: ^\s*(?:(?:i|1)[\.\、]\s*)?executive\s+summary\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:i|1|一)[\.\、]\s*)?(?:执行摘要|核心摘要)\s*[:：]?\s*$
components:
- key_metrics_snapshot
floor:
  min_real_blocks: 2
pass_affinity: []
title_word_aliases: []
role: exec
```

600-800 words. Fixed block order:

1. REQUIRED opening passage headed "The bet": one short paragraph
   stating, in plain language, exactly what has to become true for this
   investment to work — the market emerges, this team wins it, the
   entry terms pay for the risk. This is the honest register of an
   early-stage memo: a bet named as a bet.
2. Positioning paragraph (≤60 words): what the company does, for whom,
   and what exists today (product shipped / pilot / prototype).
3. "Key Facts" table with `component: "key_metrics_snapshot"` titled
   "Key Metrics Snapshot": Stage & round | Raise & instrument |
   Valuation or cap | Revenue or traction proxy | Runway | Team size |
   Founded. Missing cells: "Not disclosed — <implication>".
4. Exactly 3 thesis bullets, complete verdict sentences: (a) the wedge
   opens a market that matters, (b) this team is the reason to believe,
   (c) the terms pay for the risk. A bullet the evidence cannot support
   says so.
5. ≤3 top-risk bullets quoting the highest-rated pinned risk summaries
   verbatim with ratings.
6. Verdict callout: the pinned recommendation sentence verbatim, the
   entry terms, the required-exit arithmetic in one line ("a 3x fund
   return needs a $NNN M exit"), and the fund placeholders verbatim.
   With a pinned verdict tier and scorecard, open on
   "{tier} — {total}/100".
7. A pinned `decision_history_sentence` is stated verbatim as history.

## section: company_team
```yaml
id: company_team
en_title: Founders & Company
zh_title: 创始团队与公司
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?founders?\s*(?:&|and)\s*company\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:创始团队与公司|创始人与公司|团队与公司)\s*[:：]?\s*$
components:
- board
floor: {}
pass_affinity:
- team_governance
title_word_aliases:
- founders and company
```

700-900 words. At this stage the team carries 25 of 100 points; this
section earns or denies them. Fixed blocks:

1. "Founders" table — one row PER FOUNDER: Name & role | Verified track
   record (facts with dates, separated from self-claimed bio) |
   Domain edge (why this person, this problem) | Commitment
   (full-time? vested? prior exits?).
2. "What exists today" inventory passage: product state, code or
   hardware shipped, pilots running, team headcount by function — an
   inventory of the demonstrable, each item dated.
3. "Board of Directors" table with `component: "board"`: members and
   affiliation; a company with no formal board states "None — governance
   rests entirely with the founders" as the row, plus the consequence.
4. Verdict passage headed "Why this team wins — or doesn't": weigh the
   founders' edge against what the problem actually requires; name the
   gap the next two hires must fill. End on the verdict sentence.

## section: market_thesis
```yaml
id: market_thesis
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
```

600-800 words. Whether the wedge opens a market big enough to matter.
Fixed blocks:

1. Wedge passage: the specific entry problem, why it is urgent for the
   first customers, and what larger market winning it opens.
2. "Market Sizing" table — TAM | SAM | SOM rows always, columns
   Definition | Size today | Size in 5-7y | Basis/source. At this
   stage most cells will be estimates or missing — say which is which;
   never present a founder's pitch-deck TAM as independent.
3. Chart slot `chart_market_size` (bridged): the sizing series as a
   small table plus one sentence, or the chart-omitted fallback.
4. REQUIRED passage headed "Why now": the technology, cost, or
   regulatory change that makes this buildable and buyable today when
   it wasn't five years ago — with a datum, or named as an assumption.
5. REQUIRED passage headed "The ceiling question" (Chinese: 天花板问题) —
   weighted MORE at this stage, because the market bet is most of the
   bet: if everything works, is this a $500M company or a $20B one,
   and which assumption decides it. Verdict sentence last.

## section: product_traction
```yaml
id: product_traction
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
```

700-900 words. What has actually been validated, versus claimed. Fixed
blocks:

1. Product passage: what the product does today (not the roadmap), and
   the honest distance between today's product and the thesis product.
2. "Traction" table with `component: "revenue"` titled "Revenue &
   Traction Picture" — exactly these 6 rows: Revenue/ARR | Paying
   customers | Pilots or LOIs | Usage metric (the one the company
   leads with) | Retention or repeat usage | Pipeline. Columns:
   Value | As of | Reading — and every Reading cell must state whether
   the row is EVIDENCE or REVENUE ("6 pilots — evidence of interest,
   not revenue").
3. "Key Operating Metrics" table with
   `component: "key_operating_metrics"`: the handful that exist at this
   stage — burn, runway, headcount, cost per pilot/unit — Value |
   As of | Reading. Rows that cannot exist yet say so.
4. MANDATORY both-ways passage on the strongest validation signal: the
   bull reading, the bear reading, and which the evidence favors.
5. REQUIRED passage headed "What compounds": the moat-potential
   question asked honestly — IF this works, what accumulates
   (data, network, switching cost, brand) that a copy cannot shortcut?
   At this stage the answer is potential, and is labeled as such.

## section: deal_returns
```yaml
id: deal_returns
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
```

800-1,000 words. Early-stage price discipline lives here: the
instrument's mechanics and the outcome the entry price already
requires. Fixed blocks:

1. "Deal Terms" table with `component: "deal_terms"` — exactly these
   rows: Instrument (SAFE/note/priced) | Raise size | Valuation or cap
   | Discount | Pro-rata rights | Information rights | Board seat |
   Liquidation preference | Option pool shuffle. A missing TERM here
   is a RISK, not a footnote: "Not disclosed — uncapped exposure to
   the next round's price", and material gaps are echoed in the risk
   section.
3. Entry-vs-stage-norms passage: the entry valuation against disclosed
   stage norms for this sector and geography — above, at, or below,
   and what being above demands.
4. "Required Exits" table with `component: "scenario_analysis"` — rows
   3x | 5x | 10x gross MOIC, columns Required exit valuation |
   Dilution assumption | Implied revenue at exit (at a stated
   multiple) | How plausible (verdict fragment). Cells repeat the
   pinned scenario numbers exactly where pins exist; the required-exit
   arithmetic is shown in-line. Chart slot `chart_required_exits`
   (bridged) renders the three thresholds as a small table plus one
   sentence.
5. Consequence-arithmetic passage: what a merely-good outcome (the
   most common early-stage "success": a $50-150M acquisition) returns
   to this cheque after the stack above it — in dollars and MOIC.
6. Closing verdict passage: do the terms pay for the risk — the price
   against the bet, in two or three sentences.

## section: risks_milestones
```yaml
id: risks_milestones
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
```

700-900 words. What kills this company, and what proves it is working.
Fixed blocks:

1. One-paragraph intro naming which single risk carries the bet.
2. 4-6 per-risk cards, ordered by rating highest first, using EXACTLY
   the pinned risk list and ratings. Card = heading (the pinned
   summary — a complete verdict sentence, never a topic label) +
   key_value table with `component: "risk_register"`, rows: Risk Type |
   Why it matters (fact → failure mode → consequence) | What we watch
   (at this stage: the MILESTONE that retires the risk — the observable
   proof point with its expected date, because that is what the next
   round prices) | Likelihood | Risk Rating N/10.
3. Disconfirming-evidence treatment with
   `component: "disconfirming_evidence"`: the strongest facts against
   the bet, each weighed in one sentence.
4. "Milestone Map" table: the next 18-24 months — Milestone | Expected
   date | Risk it retires | What missing it means. This is the
   spending plan for the raise, read as evidence.
5. Closing risk/reward verdict paragraph.

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
```

500-700 words. Fixed blocks:

1. "Six Questions" table with `component: "evidence_thresholds"` titled
   "Evidence Thresholds — The Six Questions" — the early-stage six,
   each answered Yes / No / Qualified with a one-line basis: Does the
   wedge open a market that matters? | Is this team the reason to
   believe? | Is there real early validation, not just interest? |
   Could the advantage compound if it works? | Do the terms pay for
   the risk? | Can a fund-returning exit plausibly exist? Every No or
   Qualified gets a what-would-flip-it paragraph.
2. "Scorecard" table — the 9 fixed dimensions with EARLY weights and
   reinterpretations: 市场空间与增速 20 | 行业地位（切入点）5 |
   护城河（潜在壁垒）10 | 收入增长与质量（早期验证）10 |
   商业模式与单位经济 10 | 团队与治理 25 | 估值（交易条款）10 |
   退出确定性 5 | 风险收益比 5. Columns Score | Why (one line). Pinned
   scorecards are repeated exactly; close with the total row and the
   threshold sentence (80+ invest / 70-79 watch / below 70 pass).
3. Symmetric close: equal-length lists (3-4 each) "What is
   demonstrated" / "What remains a bet" — the early-stage honest
   framing of unresolved items.
4. Recommendation callout with `component: "investment_decision"`:
   pinned recommendation sentence verbatim, the entry terms, the
   required-exit line, and the fund placeholders verbatim.
5. "Monitoring Indicators" table (投后监控): 3-5 rows — Indicator |
   Current value | Trigger threshold | Response — drawn from the
   Milestone Map. Titled "What changes the verdict" when the verdict
   is watch/pass.
6. One-line legal disclosure paragraph with `component: "disclosures"`.
7. A pinned `decision_history_sentence` restated verbatim as history.
