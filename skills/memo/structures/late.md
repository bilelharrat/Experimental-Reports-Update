---
stage: late
version: 1
lint_extra_titles:
- investment decision / closing view
- closing view
- investment decision
- key metrics snapshot
- sources
- references
pseudo_sections:
- id: sources
  en_title: Sources, Source Classes, and Fact Reference Index
  zh_title: 来源、来源类别与事实索引
  numbered: true
  parity_en: ^\s*(?:(?:vi|6)[\.\、]\s*)?sources?(?:,\s*source\s+classes,\s*and\s+(?:fact\s+reference\s+index|disclosures))?\s*[:：]?\s*$
  parity_zh: ^\s*(?:(?:vi|6|六)[\.\、]\s*)?(?:来源、来源类别与事实索引|来源与事实索引|来源)\s*[:：]?\s*$
- id: validation_log
  en_title: 'Appendix: Source Treatment And Assumptions'
  zh_title: 附录：来源处理与假设
  numbered: false
---

Late-stage structure profile v1 — the pre-restructure 5-section
memo encoded as data (Round 0: byte-equal to the old literals; the
2026-09 round added calculation notes, the three-line round summary,
the `base_case_outcome` echo and the Terms used block). A pinned fact
is stated verbatim once in each section the pin sheet requires it in,
and referred to without the figure everywhere else ("the February 2026
mark", "the base case"); a term of art is defined once, in the
executive summary's "Terms used" block, and used bare after that.

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

Open from the sponsor thesis, not a tombstone. At least two substantive
content blocks. Must include the Key Metrics Snapshot table with
`component: "key_metrics_snapshot"`. State the recommendation exactly as the
spine brief fixes it. When the shared fact sheet pins a
`decision_history_sentence`, state it verbatim as factual history — it
records what BSH previously decided, never the memo's own conclusion.

No deal table here. The round is a three-line summary in prose, after
the Key Metrics Snapshot: (1) the round as the sources report it —
round, date, size, post-money; (2) BSH's vehicle and instrument when
deal terms are on file, otherwise "No vehicle or terms on file
(pipeline stage: <stage>)"; (3) one sentence pointing to the full
table — "Headline terms are in Financial Forecast & Valuation" (see
Valuation). The `deal_terms` table lives there, once; a live memo
printed it twice, and the two copies drifted.

When the shared fact sheet pins `base_case_outcome` (one sentence
stating what the base case returns and how), state it verbatim in the
paragraph that interprets the entry price. The scenarios table in
Financial Forecast & Valuation states the same sentence verbatim in its
base row, so the summary and the table cannot disagree — a live memo's
summary called the base case "a modest premium" while its table said
"a few times the mark".

Close the section with the "Terms used" glossary as its LAST block: a
`glossary` block with `component: "glossary"` and `items`, one per
term of art this memo uses (MOIC, IRR, ARR, NRR, CAGR, TAM/SAM/SOM,
run-rate, post-money, MOU and the like — 6-15 items), each `{"term":
{"en", "zh"}, "definition": {"en", "zh"}}` with the definition in five
to ten words (the renderer prints the "Terms used" heading and the
term-definition table). It is where every such term is defined; no
section defines them again.

## section: company_overview
```yaml
id: company_overview
en_title: Company Overview
zh_title: 公司概览
parity_en: ^\s*(?:(?:ii|2)[\.\、]\s*)?company\s+overview\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:ii|2|二)[\.\、]\s*)?(?:公司概览|公司概况|项目简介)\s*[:：]?\s*$
components:
- board
- revenue
- key_operating_metrics
floor: {}
pass_affinity:
- adoption_distribution
title_word_aliases: []
```

Must include three tables, each carrying its component slug:
`component: "revenue"` (revenue picture), `component: "key_operating_metrics"`
(key operating metrics), and `component: "board"` (Board of Directors with
strategic value).

## section: investment_highlights
```yaml
id: investment_highlights
en_title: Investment Highlights
zh_title: 投资亮点
parity_en: ^\s*(?:(?:iii|3)[\.\、]\s*)?investment\s+highlights\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iii|3|三)[\.\、]\s*)?投资亮点\s*[:：]?\s*$
components:
- competitive_analysis
- replacement_coexistence
- moat
floor:
  bullets_or_prose: true
pass_affinity:
- competitive_position
title_word_aliases: []
```

At least two substantive bullets, or explanatory prose plus a substantive
table/callout. Must include tables with `component: "competitive_analysis"`,
`component: "replacement_coexistence"` (replacement vs. coexistence), and
`component: "moat"` (moat / defensibility).

## section: investment_risk
```yaml
id: investment_risk
en_title: Investment Risk
zh_title: 投资风险
parity_en: ^\s*(?:(?:iv|4)[\.\、]\s*)?investment\s+risks?\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:iv|4|四)[\.\、]\s*)?投资风险\s*[:：]?\s*$
components:
- risk_register
- disconfirming_evidence
floor:
  bullets_or_prose: true
pass_affinity:
- alternative_explanations
- competitive_position
title_word_aliases: []
role: risk
```

Present 4-6 material risks as per-risk cards (contract below), every card
table carrying `component: "risk_register"`, plus a disconfirming-evidence
treatment block with `component: "disconfirming_evidence"`. Use the risk list
and ratings the spine brief fixes. Each card must connect a named fact to a
failure mode, an economic consequence, and an observable signal.

## section: financial_forecast_valuation
```yaml
id: financial_forecast_valuation
en_title: Financial Forecast & Valuation
zh_title: 财务预测与估值
parity_en: ^\s*(?:(?:v|5)[\.\、]\s*)?financial\s+forecast\s+(?:&|and)\s+valuation\s*[:：]?\s*$
parity_zh: ^\s*(?:(?:v|5|五)[\.\、]\s*)?财务预测与估值\s*[:：]?\s*$
components:
- time_base_integrity
- growth_bridge
- scenario_analysis
- deal_terms
- evidence_thresholds
- investment_decision
- disclosures
floor:
  require_valuation_refs: true
pass_affinity:
- numbers_integrity
- growth_bridge
title_word_aliases:
- financial forecast and valuation
role: valuation
```

Must reference scenario ranges, valuation, revenue, margins,
or what moves the number, and include blocks carrying these component
slugs: `time_base_integrity` (valuation/date/multiple timing table),
`growth_bridge`, `scenario_analysis` (bear/base/bull), `deal_terms`
(headline terms / deal mechanics), `evidence_thresholds` (written as
valuation sensitivities), `investment_decision` (final Investment Decision /
Closing View in recommendation register — the concluding call repeats the
pinned recommendation sentence, which opens with "Recommendation: "), and
`disclosures` (concise legal/offering disclosure language).

Calculation notes. Every derived number in this section — the entry
multiple, the fair-value bounds, each scenario's exit value, gross MOIC
and IRR, the growth bridge's conversion arithmetic, any market-slice
figure — shows its arithmetic in the sentence or the next one (inputs,
operation, result) and names each input's source in the sentence.
When the shared fact sheet pins calculation notes (the "Calculation
notes" lines, ids C1, C2, ...), cite the note as `[C#]` after the
result wherever it appears in prose or a table cell — the renderer
links it to the Calculation notes appendix — and cite ONLY the ids the
pin sheet lists; an id it does not carry fails a deterministic gate.
When the pin sheet carries no calculation notes, show the arithmetic
in the sentence and cite no `[C#]` at all. A figure with neither a
named source nor shown arithmetic is "not disclosed", in those words;
an estimate is called our estimate, with its assumptions named beside
it, and never passes as a disclosure.

The `scenario_analysis` table's base row states the pinned
`base_case_outcome` sentence verbatim when the shared fact sheet pins
one — the same sentence the executive summary carries — so the two
cannot disagree.

The `deal_terms` table here is the memo's ONLY deal table ("Headline
terms"): the executive summary carries a three-line summary that points
to it, never a second copy.
