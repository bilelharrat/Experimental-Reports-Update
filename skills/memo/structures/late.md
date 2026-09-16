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
memo encoded as data (Round 0: byte-equal to the old literals).

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
