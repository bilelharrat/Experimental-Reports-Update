# Research Pages And Visual Tools Plan

Status date: 2026-06-17

This plan defines the research pages BSH Research Center should expose before
the larger data-foundation rebuild. The goal is to build the right analyst
surfaces first: pages that make research questions, evidence, hypotheses,
visualizations, review gates, and next actions explicit. Once those surfaces
exist, the data-foundation work can be driven by concrete page contracts rather
than abstract data wishes.

## Working Rules

- Work directly on `main`; do not create branches or git worktrees.
- Build page contracts and visual tools before broad data-platform rewrites.
- Keep the first implementation step limited to pages 1-3:
  1. Market Pulse
  2. Evidence Matrix
  3. Hypothesis Lab
- Use deterministic fixtures or existing local stores for first-pass visuals.
- Require source traces on all material research claims, even if the first
  implementation only shows "missing source" states.
- Preserve existing Memo Studio, Stock Research, Trader View, Console, and
  Document Library behavior.
- Prefer new backend modules for page payload assembly instead of adding more
  orchestration to `server/api.py`, `server/stock_research.py`, or
  `server/serena_analysis.py`.

## Why This Comes Before The Data Foundation

The long-term data foundation should include point-in-time market data,
filings, transcripts, estimates, fundamentals, options, corporate actions,
news, source lineage, and outcome attribution. But building all of that first
would risk creating infrastructure without clear analyst pull.

These pages define the pull:

- What question does an analyst ask?
- What evidence must be present?
- What chart or table makes the answer legible?
- What action should the analyst take from the page?
- What doctor checks prevent bad research from becoming trusted output?

When the page contracts are stable, the data foundation can be upgraded one
source at a time behind those contracts.

## Current Repo Context

Relevant existing modules and surfaces:

- `server/stock_research.py`: trackers, sources, runs, weekly aggregates,
  strategy maps, work products, source quality scoring, doctor inputs.
- `server/hypothesis_store.py`: immutable forward/debug hypothesis snapshots,
  outcomes, training summaries.
- `server/hypothesis_cycle.py`: CLI and service functions for create, evaluate,
  debug backfill, and calibration.
- `server/evidence_matrix.py`: evidence/claim extraction support for company
  research material.
- `server/serena_analysis.py`: Memo Studio sessions, research tasks, readiness,
  memo work products, benchmark/chart/narrative/grader artifacts.
- `server/trader_stats.py`: trader snapshot history and refresh statistics.
- `server/weekly_stocks.py`: weekly public-market summary structure.
- `frontend/src/views/StockResearchView.vue`: current stock workspace.
- `frontend/src/components/MemoAnalysisDashboard.vue`: current Memo Studio
  orchestration surface.
- `frontend/src/components/RunLedgerTable.vue`: reusable run ledger table.
- `frontend/src/components/stock/StockHypothesesPanel.vue`: first hypothesis UI.

Recommended new module names:

- `server/research_pages.py`: payload assembly for the new research pages.
- `tests/test_research_pages.py`: backend page-contract tests.
- `frontend/src/views/ResearchPagesView.vue`: optional parent shell if the
  pages share navigation.
- `frontend/src/views/MarketPulseView.vue`
- `frontend/src/views/EvidenceMatrixView.vue`
- `frontend/src/views/HypothesisLabView.vue`

The exact frontend split can change if the existing router/sidebar structure
points to a better local pattern.

## Common Page Contract

Every research page should expose a stable payload with this top-level shape:

```json
{
  "schema_version": 1,
  "page_id": "market_pulse",
  "generated_at": "2026-06-17T00:00:00+00:00",
  "as_of": "2026-06-17",
  "status": "ok",
  "summary": {},
  "sections": {},
  "source_health": {},
  "doctor_issues": [],
  "actions": []
}
```

Common fields:

- `schema_version`: integer, starts at 1.
- `page_id`: stable page id.
- `generated_at`: payload assembly time.
- `as_of`: analyst-facing as-of date or period.
- `status`: `ok`, `partial`, `empty`, or `issues`.
- `summary`: compact page-specific metrics.
- `sections`: page-specific structured data for cards, charts, tables, and
  panels.
- `source_health`: source counts by type, source quality, staleness, missing
  traces, contradiction counts.
- `doctor_issues`: stable issue rows with `severity`, `type`, `message`,
  optional `path`, optional `artifact_id`, optional `source_ref`.
- `actions`: page actions the UI can expose, such as `create_hypothesis`,
  `open_claim`, `run_doctor`, `refresh_market_pulse`, or `start_research_task`.

Common source trace shape:

```json
{
  "source_id": "src-1",
  "source_title": "Q1 2026 earnings transcript",
  "source_type": "earnings_call_transcript",
  "url": "https://...",
  "file_id": null,
  "artifact_id": "tracker_run:nvda:...",
  "locator": "p. 4",
  "excerpt": "Short excerpt, not a full copied source.",
  "published_at": "2026-05-07",
  "checked_at": "2026-06-17T00:00:00+00:00",
  "confidence": 0.86
}
```

Source quality fields should use the same vocabulary already present in
`server/stock_research.py` where possible:

- `sec_filing`
- `company_press_release`
- `earnings_call_transcript`
- `investor_presentation`
- `regulatory_filing`
- `primary_dataset`
- `broker_note`
- `reputable_media`
- `weak_media`
- `analyst_note`
- `unsourced_note`
- `unknown`

## Page 1: Market Pulse

### Research Question

What changed this week, what matters, and what should enter the research loop?

### Route And API

Recommended frontend route:

- `/research-pages/market-pulse`

Recommended backend route:

- `GET /api/research-pages/market-pulse`

Optional action routes for later slices:

- `POST /api/research-pages/market-pulse/refresh`
- `POST /api/research-pages/market-pulse/actions/create-hypotheses`

### Inputs

First-pass inputs from existing stores:

- Latest Stock Research weekly aggregate from `server.stock_research`.
- Stock tracker runs and ranked signals.
- Stock source registry and source quality fields.
- Weekly public-stock summary from `server.weekly_stocks` if present.
- Existing run ledger rows from `server.run_ledger` through Stock Research.
- Existing doctor output from `server.stock_research_doctor`.

Future data-foundation inputs:

- Market breadth, sector ETFs, index returns, rates, liquidity, volatility.
- Point-in-time news flow with entity mapping.
- Earnings/calendar data.
- Options positioning and short-interest data where licensed/available.

### Analysis Method

Assemble a weekly market state from existing artifacts:

1. Load latest aggregate and tracker runs.
2. Normalize ranked signals into a single `market_signal` row shape.
3. Score each signal with:
   - `importance`
   - `confidence`
   - `source_quality_score`
   - `primary_source_count`
   - `weak_source_count`
   - `novelty_vs_previous_period`
   - `actionability`
4. Separate primary-source signals from media-only or note-only signals.
5. Detect contradictions and missing-source warnings.
6. Produce a "what changed" diff versus the prior period where available.
7. Recommend candidate hypotheses from high-importance, high-source-quality
   signals.

### Required Visuals

- Market regime strip:
  - risk-on/risk-off/neutral
  - breadth
  - sector leadership
  - volatility/rates/liquidity placeholders until data foundation exists
- Ranked signal table:
  - signal
  - direction
  - confidence
  - source quality
  - primary source count
  - weak source count
  - related tickers/themes
  - action buttons
- Sector/theme heat map:
  - theme or sector
  - signal count
  - average quality
  - net direction
- "Changed since last week" diff panel:
  - new signals
  - fading signals
  - revised conviction
  - new contradictions
- Catalyst calendar preview:
  - event date
  - ticker/theme
  - expected impact
  - source

### Actions

- Create hypothesis from signal.
- Open source traces for a signal.
- Send signal to Strategy Map.
- Start research task for missing source or contradiction.
- Mark signal as reviewed/ignored.

### Doctor Checks

Issue types:

- `market_pulse_missing_latest_aggregate`
- `market_pulse_no_ranked_signals`
- `market_pulse_signal_missing_source_trace`
- `market_pulse_weak_source_only_signal`
- `market_pulse_broken_artifact_ref`
- `market_pulse_missing_previous_period_for_diff`
- `market_pulse_stale_source`

### Acceptance Criteria

- Empty state explains exactly what data or runs are missing.
- At least one fixture-backed visual test renders ranked signals and a heat map.
- Backend test proves weak/no-source signals are flagged.
- A "create hypothesis" action can be mocked in browser tests without leaving
  the page.
- The page does not require live Claude or external market data.

## Page 2: Evidence Matrix

### Research Question

What do we actually know, how strong is the evidence, and which claims are weak
or contradicted?

### Route And API

Recommended frontend routes:

- `/research-pages/evidence-matrix`
- Optional company-scoped view: `/research/{company_id}/evidence`

Recommended backend routes:

- `GET /api/research-pages/evidence-matrix`
- `GET /api/companies/{company_id}/evidence-matrix` already exists and should
  be reused or wrapped if it provides the better local shape.

### Inputs

First-pass inputs from existing stores:

- Company research files under `data/research/<company_id>/`.
- Existing company evidence matrix endpoint/data.
- Memo Studio artifacts from `server.serena_analysis`.
- Stock Research source traces and ranked signals.
- Trader snapshot and trader refresh history for public companies where
  relevant.
- Generated memos and memo packets where source traces are available.

Future data-foundation inputs:

- Filing extracts, transcript extracts, financial statement tables.
- Company KPIs and metric definitions.
- Source document embeddings or claim index.
- Entity-level source lineage and contradiction history.

### Claim Row Shape

```json
{
  "claim_id": "claim-1",
  "company_id": "generalist-inc",
  "claim": "The company has durable enterprise adoption.",
  "claim_type": "traction",
  "importance": "high",
  "status": "needs_review",
  "evidence_strength": 0.72,
  "source_quality_score": 0.81,
  "source_count": 4,
  "primary_source_count": 2,
  "weak_source_count": 0,
  "contradiction_count": 1,
  "recency_days": 12,
  "source_refs": [],
  "contradictions": [],
  "eligible_for_memo": false,
  "eligible_for_hypothesis": true,
  "notes": ""
}
```

Claim types:

- `market`
- `product`
- `traction`
- `financial`
- `customer`
- `competitive`
- `legal`
- `management`
- `valuation`
- `technical`
- `other`

### Analysis Method

1. Ingest existing claim/evidence rows from current evidence matrix tooling.
2. Normalize claims from stock signals, memo artifacts, and research tasks.
3. Deduplicate near-identical claims by company, claim type, and normalized
   text.
4. Score each claim:
   - evidence strength
   - source quality
   - recency
   - contradiction count
   - memo eligibility
   - hypothesis eligibility
5. Show unsupported claims and contradictions first.
6. Keep all generated summaries subordinate to raw source traces.

### Required Visuals

- Evidence strength matrix:
  - x-axis: evidence quality
  - y-axis: claim importance
  - color: contradiction count or status
- Claim table:
  - claim
  - type
  - strength
  - source count
  - primary count
  - contradictions
  - eligibility
- Source provenance panel:
  - grouped source list
  - source type
  - date
  - trace count
  - claims supported
- Contradictions lane:
  - claim
  - supporting source
  - contradicting source
  - analyst action
- Unsupported-claims filter:
  - no source trace
  - weak-source only
  - stale source only

### Actions

- Approve claim for memo use.
- Mark claim as unsupported.
- Start research task to support or refute claim.
- Link claim to hypothesis.
- Open source preview.
- Add analyst note.

### Doctor Checks

Issue types:

- `evidence_matrix_empty`
- `evidence_claim_missing_source_trace`
- `evidence_claim_weak_source_only`
- `evidence_claim_has_unresolved_contradiction`
- `evidence_claim_stale_source`
- `evidence_claim_broken_source_ref`
- `evidence_duplicate_claims`
- `evidence_memo_eligible_without_primary_source`

### Acceptance Criteria

- The page can render global and company-scoped empty states.
- Fixture data covers supported, unsupported, weak-source, and contradicted
  claims.
- Backend tests assert stable issue types.
- UI exposes filters for unsupported and contradicted claims.
- The page makes no claim appear "approved" without an explicit status field.

## Page 3: Hypothesis Lab

### Research Question

What predictions are we making before outcomes are known, what happened, and
how calibrated are we?

### Route And API

Recommended frontend route:

- `/research-pages/hypothesis-lab`

Recommended backend routes:

- `GET /api/stock-research/hypotheses` already exists and should be reused.
- `POST /api/stock-research/hypotheses/create` already exists.
- `POST /api/stock-research/hypotheses/{vintage_date}/evaluate` already exists.
- `POST /api/stock-research/hypotheses/calibrate` already exists.

If a research-pages wrapper is useful:

- `GET /api/research-pages/hypothesis-lab`

### Inputs

First-pass inputs from existing stores:

- `server.hypothesis_store` snapshots, outcomes, and training summaries.
- `server.hypothesis_cycle` create/evaluate/calibrate flows.
- Stock Research aggregate signals used to create live vintages.
- Stock Research doctor hypothesis issue types.

Future data-foundation inputs:

- Point-in-time adjusted close prices.
- Benchmark returns by ticker/sector.
- Corporate action adjusted returns.
- Intraperiod drawdown and volatility.
- Event outcome data.

### Analysis Method

1. List vintages by date and kind.
2. Separate `forward_live` from `debug_backfill`.
3. Show live vintages that are not yet evaluable.
4. Show closed vintages that need outcomes.
5. Show evaluated vintages with hit/miss/unresolved results.
6. Show calibration by confidence bucket.
7. Flag any source cutoff or lookahead violation.
8. Keep debug backfills visibly ineligible for training.

### Required Visuals

- Vintage timeline:
  - date
  - live/debug kind
  - generated count
  - evaluated count
  - training eligibility
- Hypothesis cards/table:
  - ticker
  - claim
  - direction
  - confidence
  - source quality
  - generated at
  - evaluation window
  - status
- Outcome table:
  - absolute return
  - benchmark return
  - relative return
  - max drawdown
  - realized volatility
  - hit/miss/unresolved
- Calibration chart:
  - confidence bucket
  - hit rate
  - average relative return
  - sample size
- Leakage/doctor panel:
  - malformed snapshots
  - generated-after-window-start
  - missing closed-window outcomes
  - debug rows in training summaries

### Actions

- Create current live vintage.
- Run debug backfill, clearly labeled.
- Evaluate a closed vintage with fixture or market-data adapter.
- Generate calibration summary.
- Open source manifest for a hypothesis.
- Link hypothesis back to Market Pulse signal or Evidence Matrix claim.

### Doctor Checks

Existing issue types to reuse:

- `missing_current_live_hypothesis_vintage`
- `hypothesis_generated_after_window_start`
- `hypothesis_outcome_missing_after_window_close`
- `training_summary_includes_debug_rows`
- `hypothesis_source_cutoff_violation`
- `malformed_hypothesis_data`

Additional page-specific issue types:

- `hypothesis_lab_no_training_eligible_rows`
- `hypothesis_lab_closed_vintage_not_evaluated`
- `hypothesis_lab_missing_market_data_adapter`

### Acceptance Criteria

- The page clearly separates live from debug backfill rows.
- Debug rows can never appear training-eligible in the UI.
- A fixture-backed browser test renders a vintage timeline, hypothesis table,
  outcome table, and calibration chart.
- Backend tests assert no-lookahead warnings are surfaced.
- The page works when there are no hypotheses and gives the exact command/API
  action needed to create a current live vintage.

## Page 4: Company Research

### Research Question

What is the current investable view on this company?

### Route And API

Existing route:

- `/research/{company_id}`

Recommended new subroute if the page becomes too dense:

- `/research/{company_id}/research`

Existing APIs to reuse:

- `GET /api/companies/{company_id}`
- `GET /api/companies/{company_id}/memo-analysis`
- `GET /api/companies/{company_id}/research-files`
- `GET /api/companies/{company_id}/evidence-matrix`
- `POST /api/companies/{company_id}/trader/refresh`

### Inputs

- Company registry and `company_type`.
- Public-company trader snapshot for public companies.
- Research files and quick summaries.
- Evidence Matrix rows.
- Memo Studio session artifacts.
- Completed reports and generated memos.
- Stock hypotheses and signals linked to the company or ticker.

### Analysis Method

Public companies:

1. Show price, positioning, sentiment, catalysts, and news from trader snapshot.
2. Attach a source/provenance panel for each material card.
3. Link public-market claims to hypotheses and outcomes.
4. Highlight stale trader cards and missing source confidence.

Private companies:

1. Show business model, funding, customers, product proof, competition, risks.
2. Pull readiness and evidence strength from Memo Studio.
3. Promote open diligence gaps and unsupported claims.
4. Link source files to claims and memo packet inputs.

### Required Visuals

- Shared company header with source freshness and language controls.
- Public company trader card grid.
- Private company diligence strip.
- Thesis and risk panel.
- Claim/evidence sidebar.
- Change log since last refresh.
- Open diligence gaps panel.

### Actions

- Refresh trader snapshot.
- Open Evidence Matrix scoped to company.
- Start Memo Studio analysis.
- Create research task from open gap.
- Create or link hypothesis.

### Doctor Checks

- `company_research_missing_company`
- `company_research_public_without_trader_snapshot`
- `company_research_private_without_research_files`
- `company_research_stale_snapshot`
- `company_research_unresolved_evidence_blockers`
- `company_research_missing_memo_session`

## Page 5: Strategy Map

### Research Question

How do current signals connect into a portfolio or thematic view?

### Route And API

Recommended frontend route:

- `/research-pages/strategy-map`

Existing APIs to reuse:

- `GET /api/stock-research/strategy-maps/latest`
- `GET /api/stock-research/aggregates/latest`
- `POST /api/stock-research/strategy-maps/run`

### Inputs

- Latest weekly aggregate.
- Latest strategy map.
- Tracker outputs and source traces.
- Hypotheses and outcomes.
- Company-level thesis/risk/evidence rows.

### Analysis Method

1. Normalize themes, companies, catalysts, risks, and signals into graph nodes.
2. Normalize dependencies, contradictions, and reinforcing relationships into
   graph edges.
3. Deduplicate repeated claims.
4. Color graph by source quality, contradiction status, and freshness.
5. Provide a tabular fallback for dense graphs or browser limitations.

### Required Visuals

- Theme/company/catalyst/risk node graph.
- Edge confidence and source quality coloring.
- Contradiction overlays.
- Theme momentum lanes.
- "What changed since prior strategy map" diff panel.
- Source trace drawer.

### Actions

- Send node to Evidence Matrix.
- Create hypothesis from edge or theme.
- Start research task for contradiction.
- Pin theme for Market Pulse.

### Doctor Checks

- `strategy_map_missing_latest`
- `strategy_map_broken_node_source_ref`
- `strategy_map_broken_edge_source_ref`
- `strategy_map_orphaned_hypothesis_ref`
- `strategy_map_high_confidence_without_primary_source`

## Page 6: Benchmark And Comps

### Research Question

What is the right comparison set and investment frame?

### Route And API

Recommended frontend routes:

- `/research-pages/benchmarks`
- Optional company-scoped view: `/research/{company_id}/benchmarks`

Existing APIs/modules to reuse:

- Memo Studio `private_benchmark_dashboard` artifact.
- Public-company trader/stat modules where relevant.

### Inputs

- Memo Studio benchmark artifacts.
- Public comps selected by Claude or analyst.
- Public-company market/fundamental stats when available.
- Private-company funding comps from research files.
- Evidence rows supporting comp inclusion.

### Analysis Method

Private-company version:

1. Select public comps, private comps, and funding comps.
2. Explain why each comp belongs.
3. Track metric availability and source trace per metric.
4. Surface gaps where metrics are null or weakly sourced.

Public-company version:

1. Compare peer multiples, growth, margins, FCF, and revision trend.
2. Show relative momentum and valuation context.
3. Link key valuation claims to hypotheses where useful.

### Required Visuals

- Editable comps table.
- Growth vs margin scatter.
- EV/revenue and EV/EBITDA band charts.
- Rule of 40 and FCF margin chart.
- "Why this comp belongs" evidence drawer.
- Metric source coverage table.

### Actions

- Add/remove comp.
- Approve comp set.
- Request missing metric research.
- Send benchmark gap to Memo Studio readiness.

### Doctor Checks

- `benchmark_no_approved_comp_set`
- `benchmark_metric_missing_source`
- `benchmark_metric_null_for_key_comp`
- `benchmark_comp_without_rationale`
- `benchmark_stale_market_metric`

## Page 7: Catalyst And Event Book

### Research Question

What upcoming events can move the thesis, and how did past catalysts resolve?

### Route And API

Recommended frontend route:

- `/research-pages/catalysts`

Potential backend route:

- `GET /api/research-pages/catalysts`

### Inputs

- Stock aggregate event calendars.
- Trader snapshot catalysts.
- Company news and external research.
- Memo research tasks and risk registers.
- Hypotheses with event-linked claims.

### Analysis Method

1. Normalize events into a common event row.
2. Classify type: earnings, guidance, regulatory, conference, product, legal,
   financing, lockup, dividend, contract, other.
3. Attach expected impact and uncertainty.
4. Link events to hypotheses, risks, and companies.
5. After the event, record outcome and thesis impact.

### Required Visuals

- Calendar timeline.
- Event impact matrix.
- Event-to-hypothesis links.
- Past catalyst result history.
- Upcoming high-impact events strip.

### Actions

- Create event-linked hypothesis.
- Mark event outcome.
- Start pre-event research task.
- Add event to Strategy Map.

### Doctor Checks

- `catalyst_missing_date`
- `catalyst_missing_source`
- `catalyst_high_impact_without_hypothesis`
- `catalyst_past_event_missing_outcome`
- `catalyst_duplicate_event`

## Page 8: Risk Register

### Research Question

What can break the thesis, and what evidence would prove or disprove the risk?

### Route And API

Recommended frontend routes:

- `/research-pages/risks`
- Optional company-scoped view: `/research/{company_id}/risks`

Existing inputs to reuse:

- Memo Studio strategic risks and risk priorities.
- Evidence Matrix contradictions.
- Stock strategy map contradictions.
- Trader/news risk notes.

### Analysis Method

1. Normalize risks across memo, stock, and company artifacts.
2. Score severity, likelihood, time horizon, detectability, and evidence
   strength.
3. Track mitigation evidence and disconfirming evidence.
4. Separate thesis-breaking risks from ordinary diligence tasks.

### Required Visuals

- Risk heat map.
- Thesis risk waterfall.
- Risk owner/status table.
- New-since-last-review panel.
- Evidence and disconfirmation drawer.

### Actions

- Waive/reopen risk.
- Start research task.
- Add risk to memo packet.
- Link risk to hypothesis or catalyst.

### Doctor Checks

- `risk_missing_source`
- `risk_high_severity_unreviewed`
- `risk_has_contradiction_without_task`
- `risk_stale_review`
- `risk_memo_ready_without_disconfirmation_check`

## Page 9: Research Task Workbench

### Research Question

What should the analyst or AI research next, what is running, and what was
learned?

### Route And API

Recommended frontend route:

- `/research-pages/research-tasks`

Existing APIs to reuse:

- Memo Studio research task endpoints.
- `/api/jobs/active`
- `/api/jobs/log`
- Stock Research run/retry/cancel endpoints.

### Inputs

- Memo Studio research tasks.
- Evidence Matrix weak claims and contradictions.
- Stock Research review queue.
- Market Pulse missing-source items.
- Hypothesis Lab closed/unevaluated or weakly sourced items.

### Analysis Method

1. Normalize tasks from multiple workspaces.
2. Track status, owner, source selection, result summary, confidence, and
   reviewer score.
3. Preserve failed/fallback runs and previous good artifacts.
4. Group tasks by why they exist: missing source, contradiction, stale data,
   readiness blocker, hypothesis follow-up, catalyst prep.

### Required Visuals

- Queue table or Kanban lanes.
- Task detail panel:
  - prompt
  - selected sources
  - sources checked
  - result
  - evidence
  - contradictions
  - confidence
- Active jobs rail integration.
- Batch run controls.
- Review scoring panel.

### Actions

- Run task.
- Cancel task.
- Retry task.
- Approve result.
- Send result to Evidence Matrix, Memo Studio, or Hypothesis Lab.

### Doctor Checks

- `research_task_running_stale`
- `research_task_done_without_result`
- `research_task_result_without_source`
- `research_task_failed_without_preserved_previous`
- `research_task_ready_for_memo_unreviewed`

## Page 10: Memo And IC Prep

### Research Question

Is this company or theme ready for an investment memo or IC discussion?

### Route And API

Existing company route:

- `/research/{company_id}?tab=analysis`

Potential standalone route:

- `/research-pages/ic-prep`

Existing APIs to reuse:

- Memo Studio session and artifact endpoints.
- Memo prep/final memo endpoints.
- Memo run ledger endpoint.

### Inputs

- Approved thesis spine.
- Approved risks and risk priorities.
- Evidence Matrix approved claims.
- Benchmark/comps artifacts.
- Chart plans and narrative hooks.
- Research tasks and readiness reviews.
- Completed memo grader lessons.

### Analysis Method

1. Pull only reviewed or explicitly waived material into the IC packet.
2. Block final memo generation unless readiness gates pass.
3. Show open blockers separately from waived blockers.
4. Grade completed memos and feed distilled lessons into future runs.

### Required Visuals

- Readiness checklist.
- Memo packet preview.
- Chart plan gallery.
- Narrative hook selector.
- Evidence coverage summary.
- Memo grader and lessons panel.
- Final generate controls.

### Actions

- Approve analysis.
- Waive readiness gap with rationale.
- Generate final memo.
- Grade completed memo.
- Save lesson for future memo runs.

### Doctor Checks

- `ic_prep_unapproved_thesis`
- `ic_prep_unwaived_readiness_blocker`
- `ic_prep_claim_without_evidence`
- `ic_prep_chart_without_source`
- `ic_prep_benchmark_gap_unresolved`
- `ic_prep_lessons_stale`

## First Implementation Step: Pages 1-3

The first engineering step is not to build all ten pages. It is to build the
core observe -> prove -> predict loop:

1. Market Pulse: observe and rank what changed.
2. Evidence Matrix: prove or challenge the claims.
3. Hypothesis Lab: freeze predictions and evaluate outcomes.

These three pages should be implemented as one coherent slice because they
share source traces, signal/claim normalization, doctor checks, and actions.

### Slice 1A: Backend Contracts For Pages 1-3

Files to add or modify:

- Add `server/research_pages.py`.
- Add Pydantic response models in `server/api.py` or a new model module if the
  repo has an established pattern by the time this is implemented.
- Add routes:
  - `GET /api/research-pages/market-pulse`
  - `GET /api/research-pages/evidence-matrix`
  - `GET /api/research-pages/hypothesis-lab`
- Add tests in `tests/test_research_pages.py`.

Implementation details:

- Use existing stores only. Do not add external data providers in this slice.
- Return `status: "empty"` when stores do not have enough data.
- Include `doctor_issues` even in empty states.
- Keep payloads compact and deterministic.
- Include fixtures in tests for:
  - strong primary-source signal
  - weak-source signal
  - unsupported claim
  - contradicted claim
  - forward live hypothesis
  - debug backfill hypothesis
  - evaluated outcome

Acceptance criteria:

- All three endpoints return stable schema-versioned payloads.
- OpenAPI includes the new response models.
- Tests assert stable doctor issue `type` values.
- No live Claude, API key, or network dependency is required.

### Slice 1B: Frontend Shell And Navigation

Files to inspect and modify:

- `frontend/src/router.js`
- `frontend/src/components/Sidebar.vue`
- Add:
  - `frontend/src/views/MarketPulseView.vue`
  - `frontend/src/views/EvidenceMatrixView.vue`
  - `frontend/src/views/HypothesisLabView.vue`
- Optionally add shared components:
  - `frontend/src/components/research/SourceQualityBadge.vue`
  - `frontend/src/components/research/DoctorIssuesPanel.vue`
  - `frontend/src/components/research/SourceTraceDrawer.vue`
  - `frontend/src/components/research/ResearchPageHeader.vue`

Implementation details:

- Add navigation under a clear "Research Pages" or equivalent sidebar group.
- Keep the first UI implementation dense and analyst-oriented, not a landing
  page.
- Use existing visual styling and table/card patterns.
- Use charts only where they add analysis value:
  - Market Pulse heat map can start as CSS grid cells.
  - Evidence Matrix can start as a grid/scatter-style SVG or div plot.
  - Hypothesis calibration can start as a simple bar chart.
- Every visual must have a table fallback or adjacent table.

Acceptance criteria:

- All three pages load from the router.
- Empty states are useful and specific.
- Fixture/mocked API browser tests verify the main panels render.
- Text does not overflow compact cards/buttons on desktop or mobile.

### Slice 1C: Page-Specific Visuals

Market Pulse first visuals:

- Summary cards.
- Ranked signals table.
- Source quality badges.
- Sector/theme heat map.
- Change-since-last-period panel.
- Doctor issues panel.

Evidence Matrix first visuals:

- Claim/evidence table.
- Evidence strength matrix.
- Unsupported/contradicted filters.
- Source provenance list.
- Contradictions lane.
- Doctor issues panel.

Hypothesis Lab first visuals:

- Vintage timeline.
- Hypothesis table.
- Outcome table.
- Calibration chart.
- Leakage/doctor panel.
- Create/evaluate/calibrate action buttons, mocked where needed.

Acceptance criteria:

- Each page is useful with mocked data.
- Each page is still useful with an empty local store.
- Action buttons either call existing endpoints or are visibly disabled with a
  clear reason.

### Slice 1D: Tests And Verification

Backend tests:

- `python -m pytest tests/test_research_pages.py`
- Existing hypothesis tests must still pass:
  - `python -m pytest tests/test_hypothesis_store.py tests/test_hypothesis_cycle.py`
- Stock Research doctor tests must still pass.

Frontend tests:

- Add unit/component tests for each page.
- Add Playwright smoke coverage for pages 1-3 with mocked API responses.
- Existing frontend tests must still pass.

Full verification before finishing:

```bash
scripts/quality.sh
python -m server.stock_research_doctor --json
git diff --check
```

If the local data doctor reports issues, do not hide that in the UI. The first
page implementation should surface those issues clearly.

## Later Implementation Sequence

After pages 1-3 are implemented and tested:

### Slice 2: Company Research Integration

- Refine `/research/{company_id}` around public/private routing.
- Add links into Evidence Matrix and Hypothesis Lab.
- Add company-level source freshness and open diligence gaps.

### Slice 3: Strategy Map Page

- Promote existing strategy map into a standalone visual research page.
- Add graph/table dual view and contradiction overlays.
- Link Strategy Map nodes to Market Pulse signals, Evidence Matrix claims, and
  hypotheses.

### Slice 4: Benchmark And Comps Page

- Promote Memo Studio benchmark artifacts into a page.
- Add editable comp set, metric source coverage, and benchmark doctor checks.
- Keep public and private versions under one contract where possible.

### Slice 5: Catalyst And Event Book

- Normalize catalysts from trader snapshots, weekly aggregates, and research
  tasks.
- Add event timeline, event outcome recording, and hypothesis links.

### Slice 6: Risk Register

- Normalize risks from Memo Studio, Evidence Matrix, Strategy Map, and news.
- Add risk heat map, risk waterfall, and disconfirmation tracking.

### Slice 7: Research Task Workbench

- Normalize task queues across Memo Studio, Evidence Matrix, Market Pulse, and
  Stock Research.
- Add unified run/cancel/retry/review actions where supported.

### Slice 8: Memo And IC Prep

- Consolidate readiness, memo packet, chart plans, benchmark gaps, evidence
  coverage, and memo grader lessons.
- Keep final memo generation blocked by existing readiness gates.

### Slice 9: Data Foundation Backfill

Only after the page contracts are working:

- Add point-in-time market data adapter.
- Add filings/transcripts/fundamentals/estimates source stores.
- Add event/catalyst store.
- Add company/entity/source graph.
- Add outcome attribution and calibration history.
- Add source lineage migration for older artifacts.

## Data Foundation Requirements Implied By The Pages

The page plan implies these future stores:

- `market_prices`: adjusted prices, benchmarks, volumes, corporate actions.
- `market_context`: breadth, sector/index/rate/volatility state.
- `events`: catalysts, event dates, event outcomes.
- `source_catalog`: normalized source documents with source type, date,
  issuer, URL/file path, extraction status, and trust category.
- `claim_index`: durable claims, normalized text, source refs, contradiction
  links, review state.
- `hypothesis_results`: immutable predictions, outcomes, calibration summaries.
- `company_metrics`: public/private metrics, source traces, metric definitions.
- `research_tasks`: cross-workspace queue, status, output, reviewer score.

These should be introduced incrementally, behind the page contracts.

## Design Requirements

- These are work surfaces, not marketing pages.
- Favor dense but readable information over large hero sections.
- Every chart needs labels, units, and a nearby way to inspect the underlying
  rows.
- Cards should be used for repeated items, not nested page-section decoration.
- Use icons for actions where appropriate, with tooltips for unfamiliar icons.
- Avoid page text that explains how to use the app; the UI should be obvious
  from controls and labels.
- Tables need sensible default sorting.
- Empty states must name the missing store/run/action.
- Warnings should be specific and actionable.

## Definition Of Done For The Full Plan

The full research-pages effort is complete when:

- All ten pages exist or are intentionally folded into a clearly named existing
  page.
- Pages 1-3 form a working loop:
  - Market Pulse identifies signals.
  - Evidence Matrix proves/challenges claims.
  - Hypothesis Lab freezes and evaluates predictions.
- Every material claim has visible source health.
- Doctor panels expose stale, missing, weak, or broken data.
- Page payloads are schema-versioned and tested.
- Browser smoke tests cover all critical page routes.
- The data foundation roadmap is backed by concrete missing fields surfaced in
  the pages.
