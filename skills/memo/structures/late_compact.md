---
stage: late_compact
version: 1
risk_format: cards
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

COMPACT late-stage profile — the fund's main memo: seven sections,
roughly 15,000-17,000 words, written to be read by someone who is new to
investing and must still reach the right decision. It is "compact" in
SHAPE, not in depth: seven sections instead of twelve, two tables the
reader actually needs (Deal Snapshot, Key Metrics Snapshot), the
scorecard, the risk register, and at most two charts per section. The
same evidence discipline as the full report — the same pin sheet, the
same scorecard, the same data-honesty rules.

Depth is now the point. An earlier version of this profile ran 6,600
words and the founder's verdict was that the reader could not see what
the case rested on without hunting through the report. Room exists so
that every judgment is EXPLAINED: what the number measures, how it was
worked out, what counts as normal for a company of this type, and what
would change the answer. Spend the room on explanation, never on new
claims or on repeating a claim in different words. PINS ARE THE FLOOR:
compactness cuts commentary, never pinned facts. Every pinned key
metric (with its exact values), every scenario number, the fair-value
range, the entry terms, every risk summary verbatim with its rating,
and each owning section's scorecard sentence ("This dimension scores
N of M.") must appear in this memo — the pin-echo gate rejects the
package otherwise, however elegant the prose. PINS ARE STATED ONCE PER
SECTION: the section that owns a pinned fact states it verbatim once,
in the passage that owns it, and every other mention — in that section
and in every other — refers to it without the figure ("the February
2026 mark", "the base case"). One verbatim statement per required
section is the floor, and it is also the ceiling: a live run of this
profile restated its entry mark forty-nine times and its commercial
aggregate thirty-five, and the risks section alone ran 5,300 words on
the repetition. Section word budgets are
SOFT TARGETS, and the gate that rejects a section sits well above them.
Each section's `budget_words` (in its yaml) is the length to aim at for
ALL its English text, table cells included; `budget_hard_multiple` is
what multiple of it a deterministic gate actually rejects at — 1.3x for
the executive summary, company & team and valuation, 1.5x for the market
thesis, the financials and the decision, 2x for the risk register, whose
honest length depends on how many risks there are. Reaching the target
is a signal to LAND, never to stop mid-argument: finish the point you
are making, close the section, and move on. A judgment cut off halfway
through is worse than a section that runs long, so never drop a pinned
fact, a subsection or a scorecard sentence to come in under a number.
Coming in far UNDER the target is also a failure, and the more common
one: it means a judgment was asserted where it should have been
explained. When a section is short, the fix is never to pad it — it is
to go back and explain the reasoning behind each verdict that is
currently only stated. Every section is organized
under its declared numbered subsections; the run-wide data-honesty,
navigation, and chart rules ride the shared context. Bullets and prose
both earn their place: a list of parallel facts is bullets, an argument
that moves from evidence to conclusion is prose.

## section: executive_summary
```yaml
id: executive_summary
budget_words: 2600
budget_hard_multiple: 1.3
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

2,400-2,600 words — four to five pages. This is the section partners
actually read end to end, and many read NOTHING else, so it carries the
whole case on its own: a reader who stops here must know what the
company is, what the round asks, where the case is strong AND where it
is weak on every dimension the decision turns on, how each number was
worked out, what could break the investment, and what we recommend.

Write it for a reader who is new to investing. Every number is
introduced by what it measures before it appears; every comparison
states the rule it is measured against; every verdict is followed by the
evidence that earns it and, where the number is derived, by how it was
derived. Explanation is what the room is for — never new claims, never
the same claim in different words.

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
   brackets is a pinned field, NOT printed in the memo). Tarnwell
   Robotics is a fictional company: copy the shape, never the facts or
   the wording, and vary how each evidence sentence says what its
   number measures:

   ```
   Tarnwell's case rests on market size and growth (13/15), industry
   position (12/15) and moat (11/15); it is thinnest on business model
   and unit economics (4/10) and valuation (5/10).

   "component": "investment_highlights"

   [market_size_growth]
   Labour, not technology, sets the size of this market, and the
   labour gap is widening.
   A trade-association survey counted about 38,000 unfilled US
   cold-storage operator roles in 2025 — a gauge of how many seats a
   robot can take without displacing anyone [S6]. Our own estimate
   puts the addressable fleet at $9-11B a year, built from that
   vacancy count and the annual lease price per robot [C3].

   [industry_position]
   The robots already work in the hardest aisles — few autonomy vendors
   run unattended freezer shifts at all, and none at this scale.
   Hours run with nobody on board rose from about 40,000 in 2025 to
   310,000 in the first half of 2026, on the company's own fleet logs
   [S4]. About 70% of those hours were logged in freezers, the sites
   where hiring fails first [S4].

   [moat]
   Distribution does not have to be built, because the three largest
   equipment dealers already resell the robots — an operator buys
   through a vendor it has already approved.
   Dealer agreements now cover the three largest US forklift networks,
   the channel most operators already buy through; the last was signed
   in June 2026 [S9]. The dealers carry an estimated 55-60% of new
   units, our reading of the disclosed channel split and the measure
   of how much of the order book depends on them [C7].
   ```
   After the three highlights, print the DIMENSION SCAN: one `bullets`
   block, `"component": "dimension_scan"`, containing EVERY line of the
   pin sheet's dimension scan, in pin order, one bullet per dimension.
   This exists because a reader must be able to see the eight things the
   decision turns on — how big the market is, how fast it is growing,
   where the company ranks, what protects it, how strong the team is,
   how it makes money, whether it is profitable, and when it could list
   — in ONE place, with their numbers, instead of hunting for them
   across the report.

   Each bullet reads: "<Dimension> — <score>/<max>, <band>. <the why
   line>." followed by the pinned evidence sentence(s), which carry the
   number, what it measures, and where it came from ([S#] for a source,
   [C#] for our own calculation). Open the block with one sentence
   saying what the scan is, so a new reader knows how to read it. The
   business model and unit economics bullet carries TWO evidence
   sentences: how the company charges and whether that survives the next
   product shift, then whether it makes money — gross margin now and
   what has to change for it to turn positive. Any dimension banded
   `weak` ends with "→ see Key risks", and MUST appear in subsection 4.

4. Key risks: 800-900 words, and that budget is the binding one. Open
   with one sentence naming the single risk that carries the thesis.
   Then ONE `bullets` block, `"component": "key_risks"`, with the THREE
   highest-rated pinned risks, in pinned order — plus, only if a
   dimension the scan banded `weak` is not already covered by those
   three, one further item per uncovered weak dimension, to a maximum of
   FIVE items in total. Every weak dimension must be covered by one of
   these items or by the scan line pointing at the risk register; that
   is the check the reader is relying on.

   Do not write one item per pinned risk. The register in the risks
   section carries all of them at full length; this subsection carries
   the ones a reader who stops here must know about. (Written as one
   item per risk it came to 2,039 words on a live run and blew the
   section's cap by itself.)

   Each item opens with "<Area label> — <pinned summary verbatim>." and
   then EXPLAINS it in three or four sentences, in this order:

   - the arithmetic that sizes it, with the numbers in it and the [C#]
     of the calculation note, so the reader can see how it was worked
     out rather than taking it on trust;
   - what counts as normal here, so the reader can judge whether this
     number is bad ("mature software trades near 8x revenue; a frontier
     lab can hold more in a strong market, so 9x is high but not
     absurd") — the company-type lens in your instructions says what
     normal looks like for this type;
   - what would have to be true for the risk not to bite, or the
     mitigation, or "No structural mitigation exists.";
   - one line naming what to verify: the two or three facts that would
     settle it.

   Close each item with "Impact: <pinned impact verbatim>. (N/10,
   <likelihood> likelihood)" and, in the same parentheses, the one
   reason the likelihood is what it is.
5. Recommendation: a verdict callout — the pinned recommendation
   sentence verbatim, entry, fair-value range, base-case MOIC·IRR,
   holding period, and the fund placeholders verbatim. With a pinned
   verdict tier and scorecard, open on "{tier} — {total}/100". A
   pinned `decision_history_sentence` is stated verbatim after the
   callout as history. Then, as the LAST block of the section, the
   "Terms used" glossary: a `glossary` block with `component:
   "glossary"` and `items`, one per term of art this memo uses (MOIC,
   IRR, ARR, NRR, CAGR, TAM/SAM/SOM, run-rate, post-money, MOU and the
   like — 6-15 items), each `{"term": {"en", "zh"}, "definition":
   {"en", "zh"}}` with the definition in five to ten words. It is
   where every such term is defined: no section defines them again.

## section: company_team
```yaml
id: company_team
budget_words: 2400
budget_hard_multiple: 1.3
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

2,200-2,400 words. The founders and the people around them are one of the eight things the decision turns on, so this section argues the team rather than listing it: who they are, what they have already done that predicts this, where the bench is thin, and what the governance structure lets them do that a normal board would not. Every judgment about a person is evidenced — a role held, a result delivered, a departure, a filing — never an impression. Content per subsection:

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
budget_words: 2600
budget_hard_multiple: 1.5
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

2,400-2,600 words. This section carries four of the eight dimensions — how big the market is, how fast it is growing, where the company ranks in it, and what protects that rank — so it is the longest of the argument sections. Size the market from every external estimate you have, say which definition the memo adopts and why, and show the arithmetic. Then place the company in it, and only then argue the moat: what it is made of, what would erode it, and how long it holds. Content per subsection:

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
budget_words: 2300
budget_hard_multiple: 1.5
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

2,200-2,300 words. How the company charges and whether it makes money are two separate questions and this section answers both, in that order, with numbers. Profitability gets its own argument: the gross margin now, what sits inside it, the path to positive, and what breaks that path. A reader who has never seen a cost structure like this one should finish the section able to say whether it works. Content per subsection:

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
budget_words: 2400
budget_hard_multiple: 1.3
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

2,300-2,400 words. Every number here is derived, so every number here shows its arithmetic and carries the [C#] of its calculation note. Say what the entry price already assumes before you say whether it is fair, and give the reader the comparison that lets them judge the multiple — what companies of this type trade at, and why this one sits where it does against them. The exit outlook belongs here too: when a listing could realistically happen and what has to be true first. Content per subsection:

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
   Then "What has to be true": when the shared fact sheet carries the
   Python-computed price lines — the exit value and exit-year revenue
   that return the money, clear the firm's bar and return 3x at this
   price; the breakeven entry price; the growth each case implies from
   the latest disclosed revenue; the base-case IRR if the exit slips a
   year or two; BSH's own proceeds by case when a check is on file —
   state each line verbatim with its [C#], then say in one sentence
   what the gap between what is needed and what the base case assumes
   means: a base case that already needs more than the company has
   shown is a bull case wearing a base case's label. When the fact
   sheet carries none of these lines, write nothing for them — never
   compute them here.
3. Exit paths: the realistic route(s) with named acquirers or the IPO
   window, the constraint on each, and the consequence arithmetic on
   one non-premium outcome. Answer first: how does the money actually
   come back, and how certain is that. Close the section with its two
   pinned scorecard sentences — "This dimension scores N of M." for
   估值 and 退出确定性.

## section: risks
```yaml
id: risks
budget_words: 2800
budget_hard_multiple: 2.0
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

2,600-2,800 words. This section used to be a paragraph of description
and the founder could not find the point in it; it is now a REGISTER —
one card per risk, in the same shape the full report uses, so a reader
can scan the headings and stop at the one that matters.

Content per subsection:

1. The center of gravity: two or three sentences naming the single risk
   that carries the thesis, why it outranks the others, and what the
   investment looks like if it lands.
2. Risk register: one CARD per pinned risk, ordered by rating highest
   first, using EXACTLY the pinned risk list — never a new risk the pins
   do not carry, never a pinned risk left out. The card format is the
   contract in your instructions: a `heading` titled "Risk N: <the
   pinned summary>", then the fixed rows. Budget about 300-400 words per
   card, and spend them on the "Why it matters" row: the arithmetic with
   its numbers and the [C#] note that shows how it was worked out, then
   what counts as normal for a company of this type (the company-type
   lens says what normal looks like), then what would have to be true
   for the risk not to bite. "What we watch" names the actual signal and
   the two or three facts that would settle the question — never
   "monitor execution" or "track traction".
3. Disconfirming evidence: 3-5 bullets with
   `component: "disconfirming_evidence"` — the strongest facts AGAINST
   this memo's recommendation, each weighed in two or three sentences:
   the fact, why it cuts against us, and why we still hold the
   recommendation (or, honestly, that it is the reason the rating is
   what it is). Close the section with its pinned scorecard sentence:
   "This dimension scores N of M." for 风险收益比.

## section: investment_decision
```yaml
id: investment_decision
budget_words: 1400
budget_hard_multiple: 1.5
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

1,300-1,400 words. The shortest section, because by now the case is made: state the recommendation, the terms, what would change it, and what we will watch. No new evidence, no new numbers — anything that matters enough to appear here has already been argued somewhere above. Content per subsection:

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
   When it pins a `prior_view_sentence` — what BSH's previous memo on
   this company concluded — restate it verbatim beside the callout
   too, followed by one sentence on what changed since, or why the
   view holds. It is history, not evidence: no figure from the
   previous memo is cited.
4. Monitoring & triggers: 3-4 bullets — Indicator, current value,
   trigger threshold, response. Titled "What changes the verdict"
   framing when the verdict is watch/pass: the triggers are the
   re-entry conditions.
