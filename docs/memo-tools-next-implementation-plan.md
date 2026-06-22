# Memo Tools Next Implementation Plan

Last updated: 2026-06-13

This is the handoff plan for the next implementation context. It assumes the
current `main` checkout includes the research-tool hardening from
`docs/research-tools-improvement-plan.md` plus the existing Memo Studio
implementation in `server/serena_analysis.py`,
`frontend/src/components/MemoAnalysisDashboard.vue`, and the related API/tests.

Use this document as the working tracker. Move items through:

- `Not Started`
- `In Progress`
- `Blocked`
- `Done`
- `Deferred`

When a slice lands, update the checklist, add a completion-log entry, and run
the verification listed for that slice.

## Operating Rules

- Work directly on `main`. Do not create branches or worktrees.
- Keep `data/uploads/<slug>/` excluded from memo analysis. Memo tooling may use
  `data/research/<slug>/` and Memo Studio analysis-session folders only.
- Preserve deterministic direct-call behavior for tests and fallback paths.
- Claude-backed tools must preserve previous good artifacts on Claude failure.
- Long-running jobs must use progress JSONL, active-job rail descriptors,
  stale-run recovery, terminal cancellation/recovery events, and focused tests.
- Update this plan and, when appropriate,
  `docs/serena-agent-analysis-tools.md` as work is completed.

## Current State Snapshot

### Implemented

- Memo Studio sessions persist under
  `data/serena_analysis/<company>/<session>/`.
- `strategic_risk_mapper`, `thesis_spine_builder`, and individual research
  tasks can run as Claude-backed background jobs.
- Research tasks support source selection, structured results, evidence,
  open questions, cancellation, stale recovery, run-all-selected, concurrency
  gating, and active-job rail entries on the backend.
- Final memo generation accepts `analysis_session_id` and requires an approved
  analysis session plus approved thesis spine.
- The evidence matrix endpoint can rebuild claim/evidence state from quick
  summaries and Memo Studio research-task evidence.
- Approval now requires computed readiness or explicit review/waiver state
  before memo generation can unlock.
- The Memo Studio dashboard exposes run-all-selected, task cancellation,
  source selection, structured research evidence, evidence matrix review,
  source-backed benchmark metrics, and memo grading controls.
- Private benchmark dashboard and memo grader are Claude-backed with
  previous-artifact preservation and deterministic test/fallback paths.
- Memo packet and final memo prompts include readiness waivers, evidence
  matrix context, benchmark context, selected chart/narrative context, and
  reusable memo lessons.

### Next Decisions

- Phase 6 is now approved for implementation: upgrade both chart specs and
  narrative hooks into Claude-backed, image-generation-ready infographic
  planning tools.
- Phase 6 needs a first-pass durable source brief so the image/narrative
  generation prompts use a compact, high-signal evidence package instead of
  repeatedly consuming the full document set.
- Phase 7 component splitting remains deferred. The active Phase 7 objective
  is maintainability and addressing the Vite large-chunk warning without a
  broad dashboard rewrite.
- Phase 8 should implement the multi-agent public-equity research architecture
  from the AI stock-analysis design document: persistent tracker agents,
  source-traced structured handoffs, a weekly aggregator, and a qualitative
  strategy-map layer, all managed through a comprehensive Stock Research
  dashboard/toolbox.
- Memo Tools should evolve in parallel into a comprehensive early-stage company
  memo dashboard/toolbox. The two toolboxes should share the concrete product
  primitives listed in Phase 8 after those primitives have two real use cases,
  while remaining separate workflows with separate data boundaries.

### Latest Verification Baseline

Run before starting new work if the tree has changed substantially:

```bash
python -m pytest
npm --prefix frontend test
git diff --check
```

Most recent known good results from this context:

- `python -m pytest tests/test_serena_analysis.py tests/test_memo_prep.py`:
  54 passed
- `python -m pytest`: 240 passed, 2 deselected
- `npm --prefix frontend test`: 70 passed
- `npm --prefix frontend run build`: passed with route-level lazy chunks and
  no Vite large-chunk warning
- `python -m py_compile server/serena_analysis.py server/api.py server/claude_runner.py server/memo_prep.py server/stock_research.py`:
  passed
- `git diff --check`: passed

## Priority Order

1. Close approval/readiness correctness gaps.
2. Expose shipped backend research-task controls in the UI.
3. Make source selection and structured evidence usable in the dashboard.
4. Upgrade private benchmark dashboard to source-backed memo-grade output.
5. Add readiness waivers/review history into the memo packet and approval flow.
6. Finish memo grader and training loop.
7. Upgrade chart specs and narrative hooks into Claude-backed infographic and
   narrative planning tools.
8. Address Memo Studio maintainability and the Vite large-chunk warning while
   deferring broad component splitting.
9. Build the multi-agent stock research tracker system as a comprehensive
   dashboard/toolbox for tracker work, source intake, weekly research, strategy
   maps, review state, and work products.
10. Tighten Memo Tools into a parallel comprehensive dashboard/toolbox for
    early-stage company memo work products and workflow state.

## Slice 1 - Approval And Readiness Gate Hardening

Status: Done

Goal: approval should mean the analysis is ready or explicitly waived, not just
that the button was clicked.

### Implementation

- [x] Add a `readiness_reviews` artifact:

  ```yaml
  readiness_reviews:
    updated_at: ...
    items:
      - id: chart-gap-chart-adoption-ladder
        status: waived        # open | reviewed | waived
        rationale: ...
        reviewed_at: ...
  ```

- [x] Add helpers in `server/serena_analysis.py`:
  - [x] Normalize readiness review rows by `id`.
  - [x] Apply review state to `additional_areas`.
  - [x] Compute `ready_for_approval` excluding the approval gate itself.
  - [x] Compute `approval_blockers` from missing required gates and open,
        unwaived additional areas.
- [x] Update `_readiness()` so:
  - [x] The `approved` gate remains visible.
  - [x] Non-approval blockers prevent `ready_for_approval`.
  - [x] Waived/reviewed areas remain visible with rationale but do not block if
        explicitly waived.
- [x] Update `approve(company_id)` to reject approval with a clear `ValueError`
      when `approval_blockers` remain.
- [x] Update `memo_prep._validate_analysis_session_for_memo()` to reject
      stale/inconsistent approved sessions that still have open blockers.
- [x] Add `PATCH /memo-analysis/artifacts/readiness_reviews` handling if the
      generic merge behavior is insufficient.
- [x] Update `MemoAnalysisDashboard.vue`:
  - [x] Disable Approve until `ready_for_approval`.
  - [x] Show blocking reasons in the readiness panel.
  - [x] Add waive/reopen controls with rationale for additional areas.
  - [x] Keep Generate Memo disabled unless backend says the session is approved
        and has no approval blockers.

### Verification

- [x] Add backend tests that approval fails when required gates are missing.
- [x] Add backend tests that approval succeeds after explicit waiver of
      additional areas.
- [x] Add backend tests that memo prep rejects an approved session if later
      edits reopen blockers.
- [x] Add frontend tests for disabled approve/generate state and waiver save.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py tests/test_memo_prep.py
  npm --prefix frontend test
  ```

## Slice 2 - Research Task UI Parity

Status: Done

Goal: expose backend capabilities that already exist: run all selected tasks,
cancel running tasks, choose sources, and inspect structured evidence.

### Implementation

- [x] Extend `frontend/src/api.js`:
  - [x] `memoAnalysis.runSelectedTasks(companyId, retryFailed = true)`
  - [x] `memoAnalysis.cancelTask(companyId, taskId)`
- [x] Update the Research Task Queue in `MemoAnalysisDashboard.vue`:
  - [x] Add a toolbar button for Run selected tasks.
  - [x] Add per-task cancel button while status is `running`.
  - [x] Display batch launch status returned by the backend.
  - [x] Keep polling until all running tasks reach a terminal state.
- [x] Add source selection UI:
  - [x] Read available files from `artifacts.input_manifest.research_files`.
  - [x] Add per-task source picker with checkboxes.
  - [x] Persist `selected_source_ids` through `patchTask`.
  - [x] Show fallback text when no source is selected: all research-folder
        sources will be available.
- [x] Add structured result display:
  - [x] Show `answer`, `confidence`, `sources_checked`.
  - [x] Expand supporting evidence, contradicting evidence, and open questions.
  - [x] Show file/locator/excerpt with concise formatting.
  - [x] Surface low-confidence/fallback/error states clearly.
- [x] Avoid losing manual task edits when priority selections refresh tasks.

### Verification

- [x] Add API wrapper tests or component tests for run-all and cancel calls.
- [x] Add dashboard tests for source selection patch payload.
- [x] Add dashboard tests for evidence/open-question rendering.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py
  npm --prefix frontend test
  ```

## Slice 3 - Evidence Matrix Integration In Memo Studio

Status: Done

Goal: make the per-company evidence matrix usable during memo review instead of
only available as an API endpoint.

### Implementation

- [x] Add `api.getEvidenceMatrix(companyId)` or a namespaced Memo Studio API
      helper.
- [x] Add a compact Evidence Matrix panel to Memo Studio:
  - [x] Claim
  - [x] status: supported, contradicted, mixed, partial, missing
  - [x] supporting/contradicting/missing counts
  - [x] confidence
  - [x] top source locator/excerpt
- [x] Add filters for mixed/contradicted/missing claims.
- [x] Link matrix rows back to task/source sections where possible.
- [x] Feed high-signal matrix summary into `memo_packet.md`:
  - [x] Mixed and contradicted claims.
  - [x] Missing evidence with high-severity open questions.
  - [x] Strongest source-backed support.

### Verification

- [x] Add backend test that memo packet includes evidence matrix summary when
      task evidence exists.
- [x] Add frontend test for evidence matrix rendering and filters.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py
  npm --prefix frontend test
  ```

## Slice 4 - Source-Backed Private Benchmark Dashboard

Status: Done

Goal: replace the benchmark scaffold with a memo-grade public comp and metric
research tool.

### Implementation

- [x] Add `SERENA_BENCHMARK_DASHBOARD_SCHEMA` to `server/claude_runner.py`.
      Suggested fields:
  - [x] `summary`
  - [x] `public_comps[]`
  - [x] `company`, `ticker`, `why_relevant`
  - [x] `revenue_growth_pct`, `gross_margin_pct`, `ev_revenue`,
        `ev_ebitda`, `fcf_margin_pct`, `rule_of_40`
  - [x] `metric_period`
  - [x] `sell_side_theme`
  - [x] `source_traces[]` with source title/url/locator/excerpt/confidence
  - [x] `benchmark_gaps[]`
  - [x] `must_prove[]`
  - [x] `confidence`
- [x] Add `run_serena_private_benchmark_dashboard()` to
      `server/claude_runner.py`.
- [x] Add `private_benchmark_dashboard` to `_CLAUDE_BACKED_TOOLS`.
- [x] Extend `_run_analysis_tool_job()` with a benchmark path mirroring
      strategic risk and thesis spine behavior:
  - [x] Progress JSONL.
  - [x] Active jobs rail.
  - [x] Stale recovery.
  - [x] Previous good artifact preservation.
  - [x] Deterministic fallback only when no previous good benchmark exists.
- [x] Add `_coerce_benchmark_dashboard()` in `server/serena_analysis.py`.
- [x] Update `_benchmark_dashboard()` fallback to match the richer schema.
- [x] Update `_refresh_memo_packet()` to include:
  - [x] Public comp table with metrics.
  - [x] Benchmark gaps.
  - [x] Must-prove claims.
  - [x] Source-trace notes.
- [x] Update dashboard UI:
  - [x] Show metrics columns.
  - [x] Allow manual row edits where practical.
  - [x] Show source trace and confidence.

### Verification

- [x] Test successful Claude benchmark persistence and normalization.
- [x] Test previous benchmark artifact is preserved on Claude failure.
- [x] Test deterministic fallback on first-run failure.
- [x] Test active-job rail entry for benchmark job.
- [x] Test memo packet includes benchmark metrics/gaps.
- [x] Add frontend test for metric table rendering.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py tests/test_memo_prep.py
  npm --prefix frontend test
  ```

## Slice 5 - Memo Grader And Training Loop

Status: Done

Goal: completed memos should produce reusable lessons, not just one-off files.

### Implementation

- [x] Define `data/serena_training/<company_slug>/` storage.
- [x] Define grader artifact schema:
  - [x] completed report id/run id
  - [x] scores by rubric area
  - [x] strongest sections
  - [x] weakest sections
  - [x] missing diligence
  - [x] rewrite guidance
  - [x] lessons for future memo runs
  - [x] source files reviewed
- [x] Add completed-memo selector:
  - [x] API returns completed memo runs for the company.
  - [x] UI lets Serena select a memo to grade.
- [x] Add Claude-backed `run_serena_memo_grader()`:
  - [x] Reads memo artifacts and `memo_packet.md`.
  - [x] Produces structured grader output.
  - [x] Preserves previous grading on failure.
- [x] Add distilled lessons:
  - [x] Update `data/serena_training/<company>/serena_memo_lessons.md`.
  - [x] Add global or per-sector lesson aggregation only if useful.
- [x] Inject lessons into:
  - [x] strategic risk prompt
  - [x] thesis spine prompt
  - [x] final memo prompt
  - [x] with explicit instruction that current evidence overrides stale
        lessons.

### Verification

- [x] Test completed report selection.
- [x] Test memo grader persistence.
- [x] Test lessons file creation/update.
- [x] Test future prompts include lessons when available.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py tests/test_memo_analysis.py
  npm --prefix frontend test
  ```

## Slice 6 - Chart Spec And Narrative Tool Upgrade

Status: Done

Goal: upgrade chart specs and narrative hooks into Claude-backed,
image-generation-ready planning tools for high-quality memo infographics and
storytelling.

### Decisions

- Upgrade both `chart_spec_builder` and `narrative_hooks`.
- The primary product objective is high-quality image-generated infographics,
  not deterministic low-fidelity charts.
- The system should support two infographic production modes:
  - Image generated without text, with application-rendered text layered later
    for crisp and controllable typography.
  - Fully text-in-image generation when that is the better fit or explicitly
    chosen by the human reviewer.
- Do a first-pass source distillation job that creates a durable, high-signal
  source brief from all relevant company documents and current Memo Studio
  artifacts. Use that brief as the main input to chart/narrative generation to
  improve token efficiency and factual accuracy.
- Use rich schemas with enough metadata to validate, review, preserve, and
  audit the work product.
- Preserve manual edits by default.
- Prompt the human reviewer for ambiguous choices instead of guessing.
- Run chart, narrative, and source-brief work as parallel-safe background jobs
  with progress JSONL, active-job rail descriptors, stale recovery, and
  previous-good-artifact preservation.
- Verification should emphasize work completion and information preservation,
  not just happy-path schema shape.

### Implementation

- [x] Add a durable infographic source brief artifact:
  - [x] Suggested artifact id: `infographic_source_brief`.
  - [x] Source inputs: approved thesis spine, selected risks, research-task
        evidence, evidence matrix, benchmark dashboard, readiness reviews,
        selected chart specs, selected narrative hooks, memo lessons, and
        selected research-folder source excerpts.
  - [x] Include compact claims, numeric metrics, source traces,
        contradictions, missing evidence, no-go claims, visual opportunities,
        and narrative opportunities.
  - [x] Preserve previous good source brief on Claude failure.
- [x] Add Claude schema and runner for `chart_spec_builder`:
  - [x] Chart/infographic title and purpose.
  - [x] Recommended visual format and alternate formats.
  - [x] Image-generation mode: no text with overlay, text-in-image, or needs
        human choice.
  - [x] Text overlay plan with headline, labels, callouts, footnotes, and
        safe copy length.
  - [x] Required metrics, source availability, source traces, confidence, and
        information gaps.
  - [x] Data payload or values to render, including units, periods,
        calculations, and denominator notes.
  - [x] Design prompt for image generation, including composition, visual
        metaphor, style constraints, aspect ratio, and prohibited claims.
  - [x] Owner, diligence needed, memo section placement, and final memo
        inclusion state.
- [x] Add Claude schema and runner for `narrative_hooks`:
  - [x] Opening, transition, and closing hook candidates.
  - [x] Claims supported by each hook, evidence references, confidence, and
        overclaiming risk.
  - [x] Suggested pairing with infographic concepts where useful.
  - [x] Human-choice fields for ambiguous tone, aggressiveness, or claim
        framing.
  - [x] Selected state and preservation of selected opening/ending ids across
        reruns.
- [x] Add explicit ambiguity handling:
  - [x] Represent choices as reviewer prompts in the artifact rather than
        silently choosing.
  - [x] Keep generation blocked or marked needs-review when a required choice
        is unresolved.
- [x] Preserve manual edits and selected ids across reruns wherever the item
      remains semantically matched.
- [x] Preserve previous artifacts on failure and use deterministic fallback
      only for first-run/no-previous-good-artifact paths.
- [x] Update backend job orchestration so source brief, chart spec, and
      narrative jobs can run in parallel when dependencies are satisfied.
- [x] Update Memo Studio UI to review source brief status, chart infographic
      plans, generation modes, overlay copy, reviewer prompts, source traces,
      and inclusion state.
- [x] Feed the source brief, selected infographic plans, and selected narrative
      hooks into `memo_packet.md` and the final memo prompt.

### Verification

- [x] Test source brief creation, normalization, source trace preservation,
      and previous-artifact preservation.
- [x] Test chart spec normalization, image-generation metadata, overlay copy,
      source trace preservation, selected-state preservation, manual edit
      preservation, and previous-artifact preservation.
- [x] Test narrative hook normalization, evidence preservation, ambiguity
      prompts, selected-id preservation, manual edit preservation, and
      previous-artifact preservation.
- [x] Test deterministic first-run fallback and previous-good-artifact
      preservation after Claude failure for all three jobs.
- [x] Test active-job rail entries, progress JSONL, stale recovery, and
      parallel launch behavior.
- [x] Test memo packet and final prompt include the source brief, selected
      infographic metadata, and selected narrative hooks without dropping
      citations or warnings.
- [x] Add frontend tests for reviewer prompts, generation mode display,
      overlay-copy display, source trace display, and selected-state edits.
- [x] Run:

  ```bash
  python -m pytest tests/test_serena_analysis.py
  npm --prefix frontend test
  ```

## Slice 7 - Dashboard Refactor And Frontend Coverage

Status: Done

Goal: keep the UI maintainable and address the Vite large-chunk warning while
deferring a broad component split until later.

### Decisions

- Defer broad dashboard refactoring and component extraction.
- Focus this phase on maintainability fixes that directly support the Phase 6
  work and on reducing or intentionally managing the Vite large-chunk warning.
- Avoid behavior changes unless required by Phase 6 integration.

### Implementation

- [x] Audit the production bundle to identify the source of the current
      >500 kB chunk warning.
- [x] Decide whether to address the warning through route-level lazy loading,
      targeted dynamic imports, Rollup `manualChunks`, or an explicit
      `chunkSizeWarningLimit` only if the warning is not actionable.
- [x] Keep any code movement narrow and behavior-preserving.
- [x] Preserve current Memo Studio visual density and workflow controls.
- [ ] Deferred component split candidates:
  - [ ] `memo/MemoReadinessGate.vue`
  - [ ] `memo/StrategicRiskBoard.vue`
  - [ ] `memo/ThesisSpineEditor.vue`
  - [ ] `memo/ResearchTaskQueue.vue`
  - [ ] `memo/ChartSpecPanel.vue`
  - [ ] `memo/NarrativeHooksPanel.vue`
  - [ ] `memo/BenchmarkDashboard.vue`
  - [ ] `memo/EvidenceMatrixPanel.vue`

### Verification

- [x] Capture before/after build chunk output if changing bundling.
- [x] Keep existing Memo Studio component tests passing.
- [x] Run:

  ```bash
  npm --prefix frontend test
  npm --prefix frontend run build
  ```

## Slice 8 - Multi-Agent Stock Research Tracker System

Status: Done

Goal: implement the stock-analysis architecture described in the AI stock
analysis design document as a persistent, source-traced, multi-agent research
system with a comprehensive dashboard/toolbox for managing the work and work
products. This is broader than Memo Studio: it should reduce context
interference, prevent weekly reset-to-zero behavior, preserve domain memory,
replace manual stitching of separate research threads with a structured
tracker -> aggregator -> strategy workflow, and give the analyst one place to
operate the full public-equity research machine.

### Source Document Interpretation

The source design identifies three engineering failures in single-context
long-report generation:

- Context interference: unrelated macro, industry, and company topics dilute
  model attention and weaken factual precision.
- Iterative degradation: long-running conversations accumulate redundant
  context and output quality decays across turns.
- No knowledge persistence: each weekly report starts from scratch instead of
  reusing prior sector, macro, and company judgments.

The plan below translates the document's architecture into this codebase while
preserving existing guardrails: structured schemas, source traces, active-job
rail entries, deterministic tests/fallbacks, stale recovery, cancellation, and
previous-good-artifact preservation.

### Architectural Decisions

- Build three layers:
  - Layer 1: tracker agents for one topic each.
  - Layer 2: aggregator agent that does not perform primary topic research by
    default; it composes tracker outputs into daily or weekly research reports.
  - Layer 3: strategy agent that compares the current weekly report to the
    previous strategy map and produces a qualitative portfolio strategy map.
- Tracker agents must have single responsibility, isolated durable knowledge,
  structured handoffs, source traceability, and composability.
- Tracker raw context must not be shared across trackers. Cross-tracker flow
  happens only through structured outputs and source-trace references.
- Each tracker owns a durable knowledge base with structured facts,
  unstructured notes, source manifests, run history, reviewer notes, and
  accepted lessons.
- The weekly aggregator does not directly browse or re-research every topic by
  default. It consumes tracker outputs, dedupes them, ranks importance, detects
  cross-topic links, and preserves source references back to tracker runs.
- The strategy agent is qualitative and visual. It may summarize exposure,
  catalysts, risks, and suggested attention/weight ranges, but final valuation
  models and portfolio decisions stay team-owned.
- Output plans and prompts are written in English in code/docs, but tracker
  report outputs may support professional Simplified Chinese where the product
  needs it. Chinese research style constraints from the source document should
  be encoded as prompt/profile metadata, not hard-coded UI copy.
- Phase 8 ships as a dashboard/toolbox, not only as backend agent jobs. The
  analyst must be able to see work status, launch work, review source quality,
  inspect outputs, resolve gaps, approve knowledge updates, and manage
  published work products from one Stock Research workspace.
- Stock Research and Memo Tools are sibling toolboxes:
  - Stock Research is for public-equity tracking, weekly research, and
    strategy-map work.
  - Memo Tools is for early-stage company investment analysis, memo preparation,
    memo generation, and memo learning loops.
  - Shared UI and backend patterns are encouraged for job lifecycle, source
    traces, artifact catalogs, review queues, exports, and evaluation metadata.
  - Data boundaries stay explicit. Stock Research must not implicitly consume
    Memo Studio sessions, and Memo Tools must not implicitly consume stock
    tracker context.

### Non-Goals

- Do not replace Memo Studio investment-analysis flows with the stock tracker system.
- Do not let this system consume `data/uploads/<slug>/` implicitly.
- Do not make the strategy agent a fully automated trading or position-sizing
  engine.
- Do not build a scheduler that runs unbounded Claude jobs. Cadence and
  concurrency controls are part of the scope.
- Do not merge all tracker context into one giant weekly prompt.

### Proposed Storage Model

- [x] Add a dedicated tracker store under `data/stock_research/`:
  - [x] `trackers/<tracker_id>/tracker.json` for tracker config.
  - [x] `trackers/<tracker_id>/knowledge.json` for structured durable facts.
  - [x] `trackers/<tracker_id>/notes.md` for analyst notes and accepted
        lessons.
  - [x] `trackers/<tracker_id>/sources/` for tracker-owned uploaded or
        promoted documents.
  - [x] `trackers/<tracker_id>/runs/<run_id>/tracker_output.json` for
        structured run output.
  - [x] `trackers/<tracker_id>/runs/<run_id>/report.md` for the human-readable
        tracker report.
  - [x] `trackers/<tracker_id>/runs/<run_id>/source_manifest.json` for all
        local and web sources checked.
  - [x] `trackers/<tracker_id>/logs/<run_id>.progress.jsonl` for progress.
  - [x] `aggregates/<period_id>/weekly_report.json` and `weekly_report.md`.
  - [x] `strategy_maps/<period_id>/strategy_map.json` and
        `strategy_map.md`.
- [x] Keep file and source ids stable so aggregator/strategy outputs can link
      back to tracker runs, source files, locators, excerpts, and timestamps.
- [x] Define migration-safe schema versions for tracker configs, tracker
      outputs, weekly aggregate outputs, and strategy maps.

### Tracker Registry

- [x] Add a tracker registry data model:
  - [x] `id`, `type`, `display_name`, `status`, `owner`, `priority`.
  - [x] `type`: `macro`, `industry`, or `company`.
  - [x] `market`, `country`, `sector`, `industry`, `subsegments`, `tickers`.
  - [x] `cadence`: weekly by default, with earnings/event-driven overrides.
  - [x] `default_language`, `output_languages`, and writing-style profile.
  - [x] Source policy: preferred official sources, media sources, vertical
        sources, sell-side sources, and user-provided source folders.
  - [x] Freshness policy: stale-after duration, last successful run, next due
        run, and run-blocking missing inputs.
- [x] Seed initial tracker examples from the source document:
  - [x] One macro tracker, one industry tracker, and one company tracker for
        the first vertical slice.
  - [x] Add an explicit `companies.yaml` import flow for expanding company
        tracker coverage without making `companies.yaml` the source of truth.
  - [x] Preserve the broader source-document scale target as a registry
        expansion path rather than a blocking seed-data requirement.
- [x] Add CRUD helpers and API endpoints for tracker registry management.
- [x] Add tests for tracker creation, update, deletion/disable, stable ids,
      schema versioning, and invalid config rejection.

### Tracker Output Schemas

- [x] Define shared tracker-output fields:
  - [x] `tracker_id`, `tracker_type`, `period_start`, `period_end`,
        `generated_at`, `status`, `confidence`.
  - [x] `thesis`: one-sentence top judgment.
  - [x] `key_signals`: ranked observations with importance, direction,
        affected tickers/themes, and source traces.
  - [x] `metrics`: numeric datapoints with value, unit, period, prior value,
        expectation/consensus where relevant, and source trace.
  - [x] `recommendations`: rating/action, target range where applicable,
        catalysts, risk triggers, and review status.
  - [x] `open_questions`, `missing_sources`, `contradictions`, and
        `watch_items`.
  - [x] `source_traces`: source title, url or file id, locator, timestamp,
        excerpt, confidence, and checked-at time.
  - [x] `knowledge_updates`: facts or lessons proposed for durable tracker
        memory, with reviewer status.
- [x] Define macro tracker schema:
  - [x] Major events and geopolitics.
  - [x] Macro data table: actual, expectation, prior, year-over-year or
        period-over-period change, and structural interpretation.
  - [x] Monetary policy and central-bank dynamics.
  - [x] Market performance, valuation, flows, FX, bonds, commodities, and
        sector concentration effects.
  - [x] Next-week event calendar and quantitative trigger conditions.
  - [x] Strategy suggestions tied to sectors, themes, or tickers, with
        attention/weight ranges and trigger conditions when source-backed.
- [x] Define industry tracker schema:
  - [x] Opening industry thesis covering the 3-5 most important weekly
        developments.
  - [x] Subsegment/player dynamics.
  - [x] Major company/event spotlights with timeline, bull case, risks,
        rating, target range, and catalysts when source-backed.
  - [x] Cross-subsegment transmission links, industry-level catalysts, and
        risks for the next week.
- [x] Define company tracker schema:
  - [x] Weekly core view with 2-3 parallel storylines.
  - [x] Financial/operating updates versus consensus and direct peers.
  - [x] Business, product, contract, customer, regulatory, M&A, litigation,
        or personnel updates.
  - [x] Management guidance and structural signals from calls or public
        remarks.
  - [x] Special event analysis.
  - [x] Sell-side valuation reference matrix: firm, rating, target price,
        upside/downside, and key disagreement.
  - [x] Action recommendation: rating, target range, key nodes, take-profit
        reference levels, and quantified rating-change triggers.
- [x] Add coercion helpers so malformed Claude output normalizes into safe
      structured rows without inventing facts.
- [x] Add schema tests for macro, industry, company, and legacy/fallback
      normalization paths.

### Tracker Prompt Profiles

- [x] Add prompt builders for macro, industry, and company trackers in
      `server/stock_research.py`. Split into a `server/stock_research/`
      package only when the implementation becomes too large for one module.
- [x] Encode the source-priority rules from the document:
  - [x] Macro: official central bank/fiscal/statistical sources first, then
        primary macro data, reputable financial media, sell-side views, and
        user-provided sources.
  - [x] Industry: official company disclosures first, sell-side research and
        call notes, vertical industry media, mainstream financial media, and
        user-provided sources.
  - [x] Company: company disclosures and transcripts first, sell-side
        coverage, vertical company-specific reporting, financial media, and
        user-provided sources.
- [x] Encode writing constraints:
  - [x] Thesis-first paragraphs.
  - [x] Every datapoint must include source metadata or be marked missing.
  - [x] Avoid vague language; use concrete values, dates, catalysts, and
        trigger conditions.
  - [x] Target report length by tracker type: macro 2,500-4,000 Chinese
        characters when generating Chinese reports; industry and company
        3,000-5,000 Chinese characters when generating Chinese reports.
  - [x] For Chinese outputs, use professional restrained investment-research
        Chinese and avoid the specific weak or awkward phrasing patterns from
        the source document.
- [x] Include a hard rule that unsupported facts must be null, missing, or
      marked as `source_needed`; never invented.
- [x] Include durable-memory instructions: current evidence overrides older
      accepted lessons when they conflict.

### Tracker Job Lifecycle

- [x] Make each tracker run a background job:
  - [x] `queued`, `running`, `done`, `error`, `cancelled`, and `recovered`
        states.
  - [x] Idempotent start semantics while the same tracker/period is active.
  - [x] Stale recovery on server startup and active-jobs scan.
  - [x] Cancellation with terminal progress event.
  - [x] Previous-good-artifact preservation on Claude failure.
  - [x] Deterministic fallback only when no previous good artifact exists.
- [x] Add run batching:
  - [x] Run selected trackers.
  - [x] Run due trackers.
  - [x] Retry failed/cancelled trackers.
  - [x] Concurrency gate by tracker type and global Claude process count.
- [x] Add active-job rail descriptors and log URLs for tracker, aggregator,
      and strategy-map jobs.
- [x] Add lifecycle tests modeled on existing research and Memo Studio job
      tests.

### Human-In-The-Loop Source Intake

- [x] Add tracker-specific source ingestion:
  - [x] Upload files into tracker-owned `sources/`.
  - [x] Attach links or notes to a tracker.
  - [x] Promote relevant company background or external research items into a
        tracker source folder with metadata preserved and explicit user action.
  - [x] Mark source relevance: general context, this-week input, earnings,
        valuation, management commentary, sell-side, or watch item.
- [x] Extract source chunks using existing extraction/OCR helpers where
      possible.
- [x] Store source manifests with file ids, locators, timestamps, excerpts,
      source type, and source priority.
- [x] Add UI to push a source to one or more trackers without manually
      stitching weekly reports.
- [x] Test idempotent promotion, OCR/extraction handoff, source metadata
      preservation, and missing/deleted source behavior.

### Weekly Aggregator Agent

- [x] Add a structured aggregator schema:
  - [x] `period_start`, `period_end`, `generated_at`.
  - [x] Included tracker run ids and excluded/stale tracker warnings.
  - [x] Modules: macro, industry, company, cross-tracker links, and watchlist.
  - [x] Ranked signals with source tracker id, tracker run id, timestamp,
        source traces, affected tickers/themes, and confidence.
  - [x] Deduped claims and contradiction/missing-source warnings.
  - [x] Event calendar and quantitative triggers for the next week.
  - [x] Suggested report sections in Markdown and optional HTML-ready blocks.
  - [x] Visual-report metadata for later dashboard or infographic rendering.
- [x] Implement aggregator job:
  - [x] Consume only structured tracker outputs and selected source-trace
        excerpts by default.
  - [x] Classify tracker outputs into weekly-report modules.
  - [x] Link related macro, industry, and company signals.
  - [x] Deduplicate repeated facts while preserving all contributing tracker
        references.
  - [x] Rank by materiality, freshness, source quality, and portfolio
        relevance.
  - [x] Produce Markdown and JSON.
- [x] Keep the current `weekly_stocks` dashboard as a separate hot-stock
      surface in Phase 8. The weekly aggregator may link to it only through an
      explicit artifact reference.
- [x] Add backend and frontend tests that every aggregate conclusion traces
      back to a tracker output and source trace.

### Strategy Map Agent

- [x] Add strategy-map schema:
  - [x] Period id, generated_at, current weekly aggregate id, previous strategy
        map id.
  - [x] Themes, sectors, companies, catalysts, risks, and edges showing
        transmission links.
  - [x] Directional posture: positive, neutral, negative, or watch.
  - [x] Suggested qualitative action: hold, accumulate, trim, take profit,
        avoid, or monitor.
  - [x] Optional attention/weight range as qualitative research guidance, not
        final portfolio instruction.
  - [x] Trigger conditions that would change the posture.
  - [x] Source tracker references and source traces for every node/edge.
  - [x] Diff versus the previous strategy map: new, removed, strengthened,
        weakened, contradicted, or unchanged.
  - [x] HTML/infographic-ready layout metadata for later visual rendering.
- [x] Implement strategy-map job:
  - [x] Read current weekly aggregate and previous strategy map.
  - [x] Generate JSON plus Markdown.
  - [x] Preserve previous map on failure.
  - [x] Require explicit source references for every actionable claim.
- [x] Add UI for a visual strategy map or table-first preview before any
      infographic work.
- [x] Add tests for diffing, source preservation, unsupported-claim rejection,
      and previous-map preservation.

### UI Plan

- [x] Add a comprehensive Stock Research dashboard/toolbox:
  - [x] Dashboard home:
    - [x] Tracker coverage by macro, industry, and company.
    - [x] Due/stale trackers, failed runs, missing-source warnings, and open
          reviewer prompts.
    - [x] Active jobs, queued work, recent completions, and cost/token
          summaries.
    - [x] Latest weekly aggregate, latest strategy map, and current watchlist.
  - [x] Tracker registry:
    - [x] Type filters, cadence, status, freshness, owner, priority, next due
          run, latest thesis, and latest confidence.
    - [x] Bulk run selected, run due, cancel, retry, disable, and archive
          controls.
  - [x] Tracker detail:
    - [x] Durable knowledge, source library, run history, latest report,
          source traces, reviewer notes, accepted lessons, and proposed
          knowledge updates.
    - [x] Diff view between current and previous tracker outputs.
    - [x] Buttons to accept/reject knowledge updates and resolve contradictions.
  - [x] Source intake center:
    - [x] Upload files, attach links, add notes, promote external/company
          research with explicit user action, and assign each source to one or
          more trackers.
    - [x] Extraction/OCR status, source priority, source relevance, freshness,
          and source-trace preview.
  - [x] Run orchestration:
    - [x] Dependency-aware run queue for tracker, aggregator, and strategy-map
          jobs.
    - [x] Active-job rail integration, job log modal, progress JSONL stream,
          stale recovery status, cancellation, and retry controls.
  - [x] Weekly aggregate workspace:
    - [x] Module filters for macro, industry, company, cross-tracker links, and
          watchlist.
    - [x] Ranked signals, stale tracker warnings, contradictions, missing
          sources, event calendar, trigger conditions, and source drilldown.
    - [x] Markdown, HTML-ready, and dashboard-preview modes.
  - [x] Strategy-map workspace:
    - [x] Visual or table-first map with themes, sectors, companies, catalysts,
          risks, edges, posture, suggested qualitative action, trigger
          conditions, and confidence.
    - [x] Diff versus prior map: new, removed, strengthened, weakened,
          contradicted, and unchanged nodes/edges.
    - [x] Source-backed node/edge inspector and unresolved contradiction panel.
  - [x] Work products catalog:
    - [x] Tracker reports, weekly aggregates, strategy maps, source manifests,
          data artifacts, Markdown exports, HTML-ready exports, and reserved
          infographic package records.
    - [x] Status fields: draft, needs review, approved, published, superseded,
          archived, and failed.
    - [x] Version history, reviewer, generated_at, source coverage, confidence,
          export links, and pin/archive controls.
  - [x] Review queue:
    - [x] Ambiguous claims, missing sources, contradictions, proposed knowledge
          updates, stale trackers, failed jobs, and strategy-map changes needing
          human approval.
  - [x] Evaluation view:
    - [x] Run-level duration, token usage, cost, source count, evidence
          coverage, contradiction count, missing-source count, reviewer score,
          and accepted/rejected lessons.
- [x] Reuse existing active-job rail and job log modal conventions.
- [x] Keep UI text in English, with report output language controlled by
      tracker configuration.
- [x] Build the dashboard with dense, work-focused operational UI:
  - [x] Avoid landing-page treatment, marketing cards, or decorative hero
        sections.
  - [x] Prefer tables, filters, tabs, compact panels, status chips, source
        trace drawers, and artifact previews.
  - [x] Keep repeated work products in cards or tables, but do not nest cards
        inside cards.
- [x] Add frontend tests for dashboard home, tracker registry, tracker detail,
      source assignment, run controls, weekly aggregate rendering, source
      drilldown, strategy-map diff states, review queue, and work-product
      catalog states.

### Memo Tools Dashboard Alignment

The codebase should end up with two comprehensive dashboard/toolboxes:

- Stock Research Toolbox:
  - Public-equity tracker agents, source intake, weekly aggregation, strategy
    maps, and public-equity work products.
- Memo Tools Toolbox:
  - Early-stage company investment analysis, source-backed analysis sessions, memo
    preparation, final memo generation, memo grading, lessons, and memo work
    products.

Implementation expectations for improving Memo Tools along the same product
lines:

- [x] Treat `MemoAnalysisDashboard.vue` / Memo Studio as the early-stage Memo
      Tools toolbox, not just a single long dashboard.
- [x] Add or refine a Memo Tools home/status layer:
  - [x] Readiness state, blockers, waivers, approved-for-memo state, thesis
        approval, active jobs, recent outputs, generated memo runs, and next
        required analyst actions.
- [x] Add a Memo Tools work products catalog:
  - [x] Analysis sessions, risk maps, thesis spines, research-task results,
        evidence matrices, benchmark dashboards, infographic source briefs,
        chart/infographic plans, narrative hooks, memo packets, generated
        memos, memo grader outputs, and lessons files.
  - [x] Status fields: draft, needs review, approved, used in memo, superseded,
        archived, failed, and manually edited.
  - [x] Version history, reviewer, generated_at, source coverage, confidence,
        source traces, export links, and pin/archive controls.
- [x] Add a Memo Tools review queue:
  - [x] Readiness blockers, unwaived gaps, ambiguous infographic choices,
        low-confidence research results, contradictions, missing evidence,
        stale approved state, memo grader findings, and proposed lessons.
- [x] Add source and evidence management surfaces:
  - [x] Research-folder source inventory, source selection by task/tool,
        source trace drilldown, evidence matrix filters, and missing-evidence
        resolution actions.
- [x] Add run orchestration parity:
  - [x] One place to run/cancel/retry analysis tools, research tasks,
        infographic source brief, chart specs, narrative hooks, benchmark,
        memo grader, and final memo generation jobs that expose backend run
        endpoints.
  - [x] Active-job rail, log modal, progress JSONL, stale recovery, and
        previous-good-artifact preservation must remain consistent.
- [x] Add evaluation/learning view:
  - [x] Memo grader scores, missing diligence, rewrite guidance, lessons,
        accepted/rejected lessons, source coverage, token/cost metadata, and
        changes in future output quality.
- [x] Keep Memo Tools data boundaries:
  - [x] Continue excluding `data/uploads/<slug>/` from memo analysis.
  - [x] Continue using `data/research/<slug>/` and Memo Studio session folders
        for memo analysis.
  - [x] Do not implicitly consume Stock Research tracker context unless a
        future explicit promotion/import flow is designed and approved.
- [x] Share these reusable primitives with Stock Research after each primitive
      has a concrete Stock Research implementation:
  - [x] Artifact/work-product catalog components.
  - [x] Review queue patterns.
  - [x] Source-trace drawers.
  - [x] Job control and log components.
  - [x] Evaluation metadata displays.
  - [x] Export/version-history controls.

### Evaluation And Observability

- [x] Track per-run duration, token usage, estimated cost, source count,
      source priority mix, evidence coverage, contradiction count, missing
      source count, and reviewer score.
- [x] Add fixture-based evals for:
  - [x] Macro tracker output shape and source preservation.
  - [x] Industry tracker output shape and cross-subsegment links.
  - [x] Company tracker valuation matrix and action-trigger preservation.
  - [x] Aggregator dedupe/source-reference preservation.
  - [x] Strategy-map diff correctness.
- [x] Add analyst review fields:
  - [x] factual accuracy.
  - [x] usefulness.
  - [x] source quality.
  - [x] writing quality.
  - [x] actionability.
- [x] Feed accepted lessons back only into the owning tracker knowledge base,
      unless a reviewer explicitly promotes a lesson to a shared profile.

### Implementation Defaults

Use these defaults unless the user explicitly changes them before work begins:

- Initial delivery is a thin vertical slice across all three tracker types:
  one macro tracker, one industry tracker, and one company tracker, followed by
  one weekly aggregate and one strategy map.
- Seed tracker config from a new Stock Research registry under
  `data/stock_research/`. `companies.yaml` may be used as an explicit import
  source for company tracker candidates, but it is not the source of truth for
  tracker configuration.
- UI route is `/stock-research`; navigation label is `Stock Research`.
- UI copy is English. Tracker outputs use English as the required canonical
  language. Simplified Chinese output is enabled per tracker through
  `output_languages` and must follow the style constraints in the prompt
  profile.
- First implementation uses manual runs and a `run due` queue. No automatic
  background scheduler runs without user action.
- First implementation uses assigned local sources plus bounded Claude web
  research. No paid or credentialed market-data source is assumed.
- Existing `weekly_stocks` remains a separate hot-stock dashboard in Phase 8.
  The weekly aggregator may link to it as context only after an explicit
  artifact reference exists.
- Memo Tools dashboard alignment is tracked in Phase 8 for shared primitives
  and acceptance criteria, but the Stock Research dashboard is the first
  implementation target. A follow-up slice may apply the shared primitives to
  Memo Tools after they exist.
- Shared primitives should be created only when the second concrete use is
  reached. Do not prematurely abstract the first Stock Research implementation.

### Phase 8 Delivery Slices

The slices below are the authoritative implementation order for Phase 8. The
earlier Phase 8 sections define product and architecture requirements; this
section defines the buildable work plan.

#### Slice 8A - Stock Research Store And Artifact Contract

Status: Done

Deliverables:

- [x] Add `server/stock_research.py` or a `server/stock_research/` package.
- [x] Create `data/stock_research/` with durable read/write helpers for:
  - [x] tracker registry records.
  - [x] tracker knowledge files.
  - [x] tracker run outputs and reports.
  - [x] source manifests.
  - [x] weekly aggregate artifacts.
  - [x] strategy-map artifacts.
  - [x] work-product catalog metadata.
- [x] Define a canonical work-product metadata schema:
  - [x] `artifact_id`, `artifact_type`, `title`, `status`, `version`.
  - [x] `created_at`, `updated_at`, `generated_by`, `reviewer`.
  - [x] `source_refs`, `source_trace_count`, `confidence`.
  - [x] `review_state`, `supersedes`, `superseded_by`.
  - [x] `pinned`, `archived`, `export_paths`, `notes`.
- [x] Define status enums:
  - [x] work product: `draft`, `needs_review`, `approved`, `published`,
        `superseded`, `archived`, `failed`.
  - [x] review item: `open`, `resolved`, `waived`, `rejected`.
- [x] Add API endpoints for reading the Stock Research dashboard payload and
      work-product catalog.

Verification:

- [x] Unit tests cover registry/artifact path safety, schema version defaults,
      status normalization, archive/pin behavior, and missing-file recovery.
- [x] `python -m pytest tests/test_stock_research_trackers.py`

#### Slice 8B - Tracker Registry And Dashboard Shell

Status: Done

Deliverables:

- [x] Add tracker registry CRUD helpers and API endpoints:
  - [x] list trackers.
  - [x] create tracker.
  - [x] update tracker.
  - [x] disable/archive tracker.
  - [x] import company tracker candidates from `companies.yaml`.
- [x] Add seed data for exactly three starter trackers:
  - [x] one macro tracker.
  - [x] one industry tracker.
  - [x] one company tracker.
- [x] Add `/stock-research` route and navigation entry.
- [x] Build dashboard shell with tabs or sections:
  - [x] Home.
  - [x] Trackers.
  - [x] Sources.
  - [x] Runs.
  - [x] Weekly Aggregate.
  - [x] Strategy Map.
  - [x] Work Products.
  - [x] Review Queue.
  - [x] Evaluation.
- [x] Dashboard home shows tracker counts, stale/due counts, active jobs,
      failed jobs, latest aggregate, latest strategy map, and open review
      items.

Verification:

- [x] Backend tests cover tracker CRUD, stable ids, invalid config rejection,
      archive/disable behavior, and seed creation idempotency.
- [x] Frontend tests cover route rendering, tab navigation, dashboard summary
      counts, empty states, and tracker table rendering.
- [x] `python -m pytest tests/test_stock_research_trackers.py`
- [x] `npm --prefix frontend test -- StockResearchView`

#### Slice 8C - Shared Tracker Schemas And Prompt Profiles

Status: Done

Deliverables:

- [x] Add JSON schemas and coercion helpers for:
  - [x] shared tracker output fields.
  - [x] macro tracker output.
  - [x] industry tracker output.
  - [x] company tracker output.
- [x] Add prompt builders for macro, industry, and company trackers.
- [x] Encode source-priority rules by tracker type.
- [x] Encode writing rules:
  - [x] thesis-first.
  - [x] source metadata required for datapoints.
  - [x] unsupported facts become `null`, `missing`, or `source_needed`.
  - [x] Chinese outputs follow professional restrained investment-research
        style.
- [x] Add deterministic fallback outputs for each tracker type.

Verification:

- [x] Tests cover valid output normalization for macro, industry, and company.
- [x] Tests cover malformed Claude output fallback without invented facts.
- [x] Tests cover source trace preservation and missing-source marking.
- [x] Tests cover prompt inclusion of source priorities and writing rules.
- [x] `python -m pytest tests/test_stock_research_trackers.py`

#### Slice 8D - Source Intake Center

Status: Done

Deliverables:

- [x] Add tracker source records and APIs:
  - [x] upload source file to a tracker.
  - [x] attach link to a tracker.
  - [x] add analyst note to a tracker.
  - [x] assign one source to multiple trackers.
  - [x] remove or archive a source assignment.
- [x] Reuse existing extraction/OCR helpers for uploaded files.
- [x] Store source manifests with source type, priority, relevance, freshness,
      chunks, locators, excerpts, and extraction status.
- [x] Add Source Intake UI:
  - [x] source list.
  - [x] tracker assignment controls.
  - [x] extraction/OCR state.
  - [x] source trace preview.
  - [x] missing/deleted source states.

Verification:

- [x] Backend tests cover upload/link/note source creation, multi-tracker
      assignment, idempotent assignment, extraction metadata, OCR handoff, and
      missing/deleted source behavior.
- [x] Frontend tests cover source upload/link/note flows, assignment payloads,
      source trace preview, and extraction status rendering.
- [x] `python -m pytest tests/test_stock_research_trackers.py tests/test_external_research_jobs.py`
- [x] `npm --prefix frontend test`

#### Slice 8E - Tracker Run Lifecycle And Tracker Detail

Status: Done

Deliverables:

- [x] Add Claude-backed tracker run jobs for macro, industry, and company
      trackers.
- [x] Add run endpoints:
  - [x] run one tracker.
  - [x] run selected trackers.
  - [x] run due trackers.
  - [x] cancel tracker run.
  - [x] retry failed or cancelled run.
- [x] Use shared job lifecycle:
  - [x] progress JSONL.
  - [x] active-job rail descriptor.
  - [x] idempotent attach while active.
  - [x] stale recovery.
  - [x] terminal cancellation/recovery events.
  - [x] previous-good-artifact preservation.
  - [x] deterministic fallback only when no previous artifact exists.
- [x] Add Tracker Detail UI:
  - [x] latest thesis and confidence.
  - [x] latest report.
  - [x] source traces.
  - [x] run history.
  - [x] proposed knowledge updates.
  - [x] accept/reject knowledge update controls.
  - [x] current-vs-previous output diff.

Verification:

- [x] Backend tests cover start, duplicate attach, cancel, stale recovery,
      retry, previous-good preservation, deterministic fallback, and active-job
      rail records.
- [x] Backend tests prove tracker raw folders are not sent to other trackers.
- [x] Frontend tests cover run/cancel/retry controls, progress states, latest
      output rendering, source trace drilldown, and knowledge update review.
- [x] `python -m pytest tests/test_stock_research_trackers.py`
- [x] `npm --prefix frontend test`

#### Slice 8F - Weekly Aggregator Workspace

Status: Done

Deliverables:

- [x] Add weekly aggregate schema and coercion helper.
- [x] Add aggregate job that consumes structured tracker outputs and selected
      source-trace excerpts only.
- [x] Add aggregate endpoints:
  - [x] create aggregate for period.
  - [x] read latest aggregate.
  - [x] read aggregate by id.
  - [x] cancel/retry aggregate job.
- [x] Aggregate output includes:
  - [x] included tracker run ids.
  - [x] stale/excluded tracker warnings.
  - [x] macro, industry, company, cross-tracker, and watchlist modules.
  - [x] ranked signals with tracker/source references.
  - [x] deduped claims.
  - [x] contradictions and missing-source warnings.
  - [x] next-week event calendar and trigger conditions.
  - [x] Markdown report and HTML-ready blocks.
- [x] Add Weekly Aggregate UI with filters, ranked signals, warnings,
      source drilldown, Markdown preview, and HTML-ready preview.

Verification:

- [x] Backend tests prove every aggregate conclusion traces to tracker run ids
      and source traces.
- [x] Backend tests cover dedupe, contradiction handling, stale tracker
      warnings, and no raw tracker-folder context leakage.
- [x] Frontend tests cover module filters, warning display, source drilldown,
      Markdown preview, and empty/error states.
- [x] `python -m pytest tests/test_stock_research_trackers.py tests/test_weekly_stocks.py`
- [x] `npm --prefix frontend test`

#### Slice 8G - Strategy Map Workspace

Status: Done

Deliverables:

- [x] Add strategy-map schema and coercion helper.
- [x] Add strategy-map job that reads current weekly aggregate and previous
      strategy map.
- [x] Add strategy-map endpoints:
  - [x] create map for period.
  - [x] read latest map.
  - [x] read map by id.
  - [x] cancel/retry map job.
- [x] Strategy map output includes:
  - [x] themes, sectors, companies, catalysts, risks, and edges.
  - [x] posture and qualitative action.
  - [x] trigger conditions.
  - [x] optional attention/weight ranges clearly labeled as research guidance.
  - [x] source tracker references and source traces for every node/edge.
  - [x] diff versus previous map.
  - [x] Markdown and HTML/infographic-ready layout metadata.
- [x] Add Strategy Map UI:
  - [x] table-first view.
  - [x] table-first visual layout using rows and edge/group indicators.
  - [x] no graph/canvas map in this slice; defer that until table-first review
        is working and tested.
  - [x] prior-map diff mode.
  - [x] node/edge source inspector.
  - [x] unresolved contradiction panel.

Verification:

- [x] Backend tests cover prior-map diff, unsupported actionable claim
      rejection, previous-map preservation on failure, and source trace
      preservation for every node/edge.
- [x] Frontend tests cover table view, diff states, source inspector, and
      contradiction panel.
- [x] `python -m pytest tests/test_stock_research_trackers.py`
- [x] `npm --prefix frontend test`

#### Slice 8H - Work Products Catalog And Review Queue

Status: Done

Deliverables:

- [x] Populate work-product catalog from tracker reports, source manifests,
      weekly aggregates, strategy maps, Markdown exports, HTML-ready exports,
      and reserved infographic package records.
- [x] Add catalog APIs for list, filter, pin, archive, and status update.
- [x] Add review queue APIs for open/resolved/waived/rejected review items.
- [x] Review queue includes:
  - [x] ambiguous claims.
  - [x] missing sources.
  - [x] contradictions.
  - [x] proposed knowledge updates.
  - [x] stale trackers.
  - [x] failed jobs.
  - [x] strategy-map changes needing human approval.
- [x] Add Work Products UI with filters by type/status/tracker/period,
      version history, source coverage, confidence, export links, pin/archive,
      and status controls.
- [x] Add Review Queue UI with item type filters, source links, resolve/waive
      controls, rationale capture, and affected artifact links.

Verification:

- [x] Backend tests cover catalog indexing, pin/archive/status updates,
      superseded artifacts, review item lifecycle, and rationale persistence.
- [x] Frontend tests cover catalog filters, pin/archive/status updates, review
      queue filters, resolve/waive flows, and artifact linking.
- [x] `python -m pytest tests/test_stock_research_trackers.py`
- [x] `npm --prefix frontend test`

#### Slice 8I - Evaluation And Observability

Status: Done

Deliverables:

- [x] Persist per-run metrics:
  - [x] duration.
  - [x] token usage.
  - [x] estimated cost.
  - [x] source count.
  - [x] source priority mix.
  - [x] evidence coverage.
  - [x] contradiction count.
  - [x] missing-source count.
  - [x] reviewer score.
- [x] Add analyst review fields for factual accuracy, usefulness, source
      quality, writing quality, and actionability.
- [x] Add Evaluation UI with run-level metrics, tracker-level trend, and
      accepted/rejected lessons.
- [x] Feed accepted lessons only into the owning tracker knowledge base unless
      explicitly promoted by a reviewer.

Verification:

- [x] Backend tests cover metric persistence for success, error, cancellation,
      recovery, and fallback.
- [x] Backend tests cover reviewer score updates and lesson promotion rules.
- [x] Frontend tests cover evaluation table, tracker metric trend, reviewer
      score edit, and lesson accept/reject controls.
- [x] `python -m pytest tests/test_stock_research_trackers.py`
- [x] `npm --prefix frontend test`

#### Slice 8J - Memo Tools Toolbox Alignment Pass

Status: Done

Deliverables:

- [x] Use the concrete primitives from Stock Research after they exist:
  - [x] work-product catalog pattern.
  - [x] review queue pattern.
  - [x] source-trace drawer pattern.
  - [x] job control panel pattern.
  - [x] evaluation metadata display pattern.
- [x] Add Memo Tools home/status summary:
  - [x] readiness state.
  - [x] blockers and waivers.
  - [x] approved-for-memo state.
  - [x] thesis approval.
  - [x] active jobs.
  - [x] recent outputs.
  - [x] generated memo runs.
  - [x] next required analyst actions.
- [x] Add Memo Tools work-product catalog for analysis sessions, risk maps,
      thesis spines, research-task results, evidence matrices, benchmark
      dashboards, infographic source briefs, chart/infographic plans,
      narrative hooks, memo packets, generated memos, memo grader outputs, and
      lessons files.
- [x] Add Memo Tools review queue for readiness blockers, unwaived gaps,
      ambiguous infographic choices, low-confidence research results,
      contradictions, missing evidence, stale approved state, memo grader
      findings, and proposed lessons.
- [x] Preserve existing memo data boundaries:
  - [x] no `data/uploads/<slug>/` in memo analysis.
  - [x] use `data/research/<slug>/` and Memo Studio session folders.
  - [x] no implicit Stock Research context import.

Verification:

- [x] Existing Memo Studio tests continue passing.
- [x] Frontend tests cover Memo Tools home/status, work-product catalog, review
      queue, source/evidence management, run orchestration, and
      evaluation/learning.
- [x] Backend tests cover catalog metadata for memo artifacts and no
      `data/uploads/<slug>/` regression.
- [x] `python -m pytest tests/test_serena_analysis.py tests/test_memo_prep.py`
- [x] `npm --prefix frontend test`

### Phase 8 Final Verification

- [x] Run after all Phase 8 delivery slices:

  ```bash
  python -m pytest tests/test_stock_research_trackers.py
  python -m pytest tests/test_external_research_jobs.py tests/test_trader_snapshot.py tests/test_weekly_stocks.py
  python -m pytest tests/test_serena_analysis.py tests/test_memo_prep.py
  python -m pytest
  npm --prefix frontend test
  npm --prefix frontend run build
  git diff --check
  ```

### Source Coverage Check

The Phase 8 plan covers each major requirement from the design document:

- [x] Single-context failure modes are represented as architectural motivation.
- [x] Single responsibility, context isolation, structured handoff,
      traceability, and composability are explicit design constraints.
- [x] Layer 1 tracker agents, Layer 2 aggregator, and Layer 3 strategy agent
      are represented as separate implementation surfaces.
- [x] Macro, industry, and company tracker classes are represented with
      source priorities, report structure, output schema, and cadence.
- [x] Initial tracker scale from the source document is represented as a
      three-tracker vertical slice plus an explicit company-tracker import
      path for expansion.
- [x] Tracker report length expectations are represented for Chinese report
      generation.
- [x] HITL source intake is represented through tracker-specific file, link,
      note, and promotion workflows.
- [x] Weekly report output and strategy-map output are represented as
      structured JSON plus Markdown/HTML-ready artifacts.
- [x] Source traceability back to tracker run, source locator, excerpt, and
      timestamp is required for aggregate and strategy conclusions.
- [x] The strategy layer is bounded to qualitative research presentation and
      does not automate final portfolio decisions.
- [x] The dashboard/toolbox requirement is explicit: Stock Research must manage
      trackers, sources, jobs, review state, aggregates, strategy maps, and
      work products from one workspace.
- [x] The parallel Memo Tools toolbox direction is explicit, with shared
      product primitives but separate workflow/data boundaries.

## Full Completion Criteria

This roadmap is not complete until all of these are true:

- [x] Approval cannot unlock memo generation while required readiness blockers
      remain open.
- [x] All computed blockers can be addressed, reviewed, or waived with
      rationale.
- [x] Run-all-selected, task cancellation, source selection, and structured
      evidence are usable from the dashboard.
- [x] Evidence matrix is visible in Memo Studio and informs `memo_packet.md`.
- [x] Benchmark dashboard has source-backed public comps and usable metrics.
- [x] Completed memos can be graded and lessons reused in future runs.
- [x] The final memo prompt receives selected risks, research-task evidence,
      readiness waivers, evidence matrix summary, benchmark context, selected
      chart specs, selected narrative hooks, and memo lessons.
- [x] Existing guardrails remain intact: no `data/uploads/<slug>/`, no
      unapproved analysis-backed memo generation, no overwritten good artifacts
      after Claude failure, no Claude dependency in unit tests.
- [x] Chart specs and narrative hooks are upgraded into Claude-backed,
      image-generation-ready infographic and narrative planning tools.
- [x] A durable infographic source brief preserves high-signal evidence,
      source traces, contradictions, no-go claims, and visual/narrative
      opportunities for efficient downstream prompting.
- [x] Reviewer prompts capture ambiguous visual, tone, and claim-framing
      choices instead of silently guessing.
- [x] The UI can review infographic generation mode, overlay copy,
      image-generation prompts, source traces, reviewer prompts, and final
      memo inclusion state.
- [x] Phase 7 either reduces the Vite large-chunk warning or documents why the
      warning is intentionally managed.
- [x] Phase 8 tracker registry, tracker storage, and tracker job lifecycle are
      implemented with source-traced outputs and previous-good-artifact
      preservation.
- [x] Macro, industry, and company tracker schemas preserve the source
      document's report structure, source-priority rules, and actionability
      requirements.
- [x] Weekly aggregator outputs preserve tracker/source references for every
      material conclusion and never merge raw tracker contexts into one giant
      prompt.
- [x] Strategy-map outputs compare against the prior map, preserve source
      traces for every node/edge, and remain qualitative rather than automated
      portfolio execution.
- [x] The Stock Research UI supports tracker review, source assignment,
      run/cancel/retry controls, aggregate review, strategy-map review, review
      queues, and a work-products catalog.
- [x] The Memo Tools UI supports early-stage memo work as a comprehensive
      toolbox: home/status, source/evidence management, run orchestration,
      review queue, work-products catalog, memo generation, memo grading, and
      learning loops.
- [x] Stock Research and Memo Tools share the listed reusable primitives after
      each primitive has two concrete uses, while preserving explicit data
      boundaries between public-equity tracker work and early-stage company
      memo work.

## Final Verification Commands

Run before marking the plan complete:

```bash
python -m pytest tests/test_serena_analysis.py
python -m pytest tests/test_memo_prep.py tests/test_memo_analysis.py
python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
python -m py_compile server/serena_analysis.py server/api.py server/claude_runner.py server/memo_prep.py
git diff --check
```

## Progress Log

| Date | Slice | Status Change | Notes |
|---|---|---|---|
| 2026-06-13 | Plan refresh | Created | Added this next-context implementation tracker after reviewing current Memo Studio backend, frontend, docs, and tests. |
| 2026-06-13 | Slices 1-5 | Done | Added approval blockers and readiness reviews, research-task UI parity, Evidence Matrix panel and packet summary, Claude-backed benchmark dashboard, memo grader/training lessons, and prompt lesson injection. |
| 2026-06-13 | Phase 6 | Not Started | Scope defined for Claude-backed, image-generation-ready chart and narrative tools with a durable source brief; implementation has not begun. |
| 2026-06-13 | Phase 7 | Deferred | Deferred broad dashboard component splitting; active scope is maintainability and Vite chunk handling only. |
| 2026-06-13 | Final verification | Done | Ran all final verification commands; backend, frontend, build, compile, and diff checks passed. |
| 2026-06-13 | Phase 6/7 decisions | Updated | Confirmed Phase 6 should upgrade both chart and narrative tools for image-generation-ready infographics with a durable source brief; narrowed Phase 7 to maintainability and Vite chunk handling while deferring component splitting. |
| 2026-06-13 | Phase 8 plan | Created | Added a multi-agent stock research tracker plan from the AI stock-analysis design document, covering persistent tracker agents, structured aggregation, strategy maps, HITL source intake, UI, tests, and source-coverage checks. |
| 2026-06-13 | Phase 8 dashboard tightening | Updated | Tightened Phase 8 around a comprehensive Stock Research dashboard/toolbox and added the parallel Memo Tools toolbox direction so the codebase has two separate workspaces for public-equity research and early-stage memo work products. |
| 2026-06-13 | Phase 8 delivery slices | Updated | Split Phase 8 into executable slices 8A-8J with implementation defaults, concrete deliverables, and per-slice verification. |
| 2026-06-13 | Phase 6 | Done | Added durable infographic source briefs, Claude-backed chart and narrative planning, reviewer prompts for ambiguous choices, source-trace-preserving normalization, previous-good-artifact preservation, packet/final-prompt integration, and dashboard review UI. |
| 2026-06-13 | Phase 7 | Done | Addressed the Vite large-chunk warning with route-level lazy loading while keeping the Memo Studio component split deferred. |
| 2026-06-13 | Phase 8 vertical slice | In Progress | Added the Stock Research store, tracker registry, source intake, deterministic tracker runs, weekly aggregate, strategy map, work-product catalog, review queue, evaluation metadata, active-job rail integration, `/stock-research` dashboard, and focused backend/frontend tests. Claude-backed tracker generation, richer detail/drilldown UI, aggregate/strategy retry controls, and Memo Tools alignment remain open. |
| 2026-06-13 | Phase 8 lifecycle/source controls | In Progress | Added bounded source extraction/OCR metadata, missing-file source states, tracker retry, aggregate/strategy cancel-retry, failed/cancelled/recovered job review items, run-level knowledge update review, source trace previews, review rationale filters, and focused backend/frontend tests. Claude-backed tracker generation, richer filters/detail UI, and Memo Tools alignment remain open. |
| 2026-06-13 | Phase 8 verification | Updated | Ran `python -m pytest` (236 passed, 2 deselected), `npm --prefix frontend test` (70 passed), `npm --prefix frontend run build`, `python -m py_compile server/stock_research.py server/api.py`, and `git diff --check`. |
| 2026-06-13 | Phase 8 Claude tracker runs | In Progress | Added Claude-backed structured tracker generation for queued tracker jobs while keeping synchronous direct runs deterministic. First-run Claude failures fall back; later Claude failures preserve the previous good tracker artifact and create failed-job review items. Richer filters/detail UI and Memo Tools alignment remain open. |
| 2026-06-13 | Phase 8 dashboard detail panels | In Progress | Added aggregate filters, warning panels, source-trace previews, HTML-ready block preview, strategy contradiction panel, work-product filters and approval action, review item type filters, tracker-level evaluation trend, and knowledge lesson visibility. Full catalog version/export controls and Memo Tools alignment remain open. |
| 2026-06-13 | Phase 8 tracker detail panel | In Progress | Added run-level report preview, source trace list, and current-vs-previous diff inside the Stock Research runs workspace. Full catalog version/export controls and Memo Tools alignment remain open. |
| 2026-06-13 | Phase 8 Memo Tools alignment | In Progress | Added a Memo Tools Toolbox layer to Memo Studio with home/status metrics, work-product catalog rows, review queue rows, explicit source/evidence boundaries, memo grader learning visibility, and focused component coverage. Backend catalog metadata, source-trace drawers, job-control extraction, and version/export controls remain open. |
| 2026-06-13 | Phase 8 Stock Research UI coverage | In Progress | Added the strategy-map node/edge Source Inspector, evaluation reviewer-score editor, evaluation lesson accept/reject controls, and focused tests for source upload/link/note flows, catalog filters/actions, review rationale, source inspector rendering, and reviewer score saving. Backend edge-case tests and version/export controls remain open. |
| 2026-06-13 | Phase 8 Memo Tools alignment | Done | Added backend Memo Tools work-product catalog metadata, an API helper, a source-boundary regression test proving `data/uploads/<slug>/` remains excluded, and a Memo Source Trace Drawer in the toolbox. |
| 2026-06-13 | Phase 8 final verification | Done | Ran Phase 8 verification: stock tracker tests 13 passed; external/trader/weekly group 58 passed; Memo backend group 54 passed; full `python -m pytest` 240 passed, 2 deselected; frontend tests 70 passed; frontend build, py_compile, and `git diff --check` passed. |
| 2026-06-13 | Post-Phase-8 hardening | Done | Split stable Stock Research and Memo toolbox panels into reusable components, added route smoke tests, added `/api/stock-research/doctor` and `/api/stock-research/run-ledger`, added work-product version history, normalized Stock Research run observability, and weighted aggregate ranking by source quality. |
