# Phase 8 Outstanding Work Plan

Status date: 2026-06-14

Baseline: `main` after checkpoint commit `6e8f7f0` (`Checkpoint verified Phase 8 state`).

This plan captures the remaining work found in the Phase 8 audit. The current
state is usable and tested, but several hardening items are only partially done:
dashboard extraction is incomplete, browser smoke coverage is jsdom-only, the
Stock Research doctor has no CLI and misses some health checks, artifact
versioning is not immutable, and observability is normalized for Stock Research
but not Memo Tools.

## Working Rules

- Work directly on `main`; do not create branches or worktrees.
- Keep slices small enough to verify independently.
- Preserve current API payload shapes unless a slice explicitly migrates them.
- Prefer presentational component extraction first, with state and API calls
  remaining in the current view until the extracted component has tests.
- Every slice should end with focused backend/frontend tests plus `git diff --check`.

## Slice 1: Finish Stock Research Dashboard Splitting

Goal: reduce `frontend/src/views/StockResearchView.vue` from a large all-in-one
dashboard into tab-level read-only/action panels while preserving existing
behavior.

Current state:

- Extracted: `StockResearchHomePanel.vue`.
- Extracted: `StockWorkProductsPanel.vue`.
- Still in parent view: tracker table, source intake, runs, aggregate, strategy
  map, review queue, and evaluation.

Planned components:

- `frontend/src/components/stock/StockTrackerRegistryPanel.vue`
- `frontend/src/components/stock/StockSourceIntakePanel.vue`
- `frontend/src/components/stock/StockRunsPanel.vue`
- `frontend/src/components/stock/StockAggregatePanel.vue`
- `frontend/src/components/stock/StockStrategyMapPanel.vue`
- `frontend/src/components/stock/StockReviewQueuePanel.vue`
- `frontend/src/components/stock/StockEvaluationPanel.vue`

Implementation notes:

- First pass should move template and display helpers only.
- Keep `payload`, filters, routing, API calls, and mutation handlers in
  `StockResearchView.vue` until each child has stable props/events.
- Emit events for actions such as run, cancel, retry, approve, archive, and
  review updates.
- Avoid changing tab IDs or route query behavior.

Acceptance criteria:

- `StockResearchView.vue` owns orchestration, not large tab templates.
- All existing Stock Research tests still pass.
- New component tests cover each extracted panel's empty, populated, and action
  event states.
- Route smoke test still covers `/stock-research`.

## Slice 2: Apply Deferred Memo Phase 7 Component Split

Goal: reduce `frontend/src/components/MemoAnalysisDashboard.vue` by extracting
stable panels from the deferred Phase 7 list.

Current state:

- Extracted: `MemoToolboxPanel.vue`.
- Still in dashboard: readiness header, tool launcher, risk priority controls,
  research task queue, evidence matrix, source brief, chart plans, narrative
  hooks, benchmark, memo grader, and generated memo controls.

Planned components:

- `frontend/src/components/memo/MemoReadinessPanel.vue`
- `frontend/src/components/memo/MemoToolLauncherPanel.vue`
- `frontend/src/components/memo/MemoRiskPriorityPanel.vue`
- `frontend/src/components/memo/MemoResearchTasksPanel.vue`
- `frontend/src/components/memo/MemoEvidenceMatrixPanel.vue`
- `frontend/src/components/memo/MemoSourceBriefPanel.vue`
- `frontend/src/components/memo/MemoChartPlansPanel.vue`
- `frontend/src/components/memo/MemoNarrativeHooksPanel.vue`
- `frontend/src/components/memo/MemoBenchmarkPanel.vue`
- `frontend/src/components/memo/MemoGraderPanel.vue`

Implementation notes:

- Start with read-only panels and panels that already use simple draft props.
- Keep polling, API mutation functions, and cross-panel derived state in
  `MemoAnalysisDashboard.vue` until a component boundary is proven stable.
- Pass draft data and save/cancel events explicitly.
- Preserve existing `MemoAnalysisDashboard.spec.js` assertions before adding
  component-level tests.

Acceptance criteria:

- `MemoAnalysisDashboard.vue` is materially smaller and mostly orchestration.
- Existing Memo Tools tests pass unchanged or with equivalent assertions.
- Component tests cover reviewer prompts, source traces, work-product rows,
  evidence matrix rows, task action events, and grader visibility.

## Slice 3: Add Real Browser Smoke Tests

Goal: add a thin browser pass that catches routing, tab switching, table
rendering, and mocked form submissions in an actual browser environment.

Current state:

- `frontend/tests/RouteSmoke.spec.js` uses Vitest + jsdom.
- There is no Playwright or Vitest browser-mode pass.

Recommended approach:

- Add Playwright test dependency and script:
  - `frontend/package.json`: `test:browser`
  - `frontend/playwright.config.js`
- Use Vite dev server through Playwright `webServer`.
- Intercept API calls with `page.route()` and return compact fixtures.
- Keep this suite small and deterministic.

Smoke cases:

- `/stock-research` loads and shows the Home tab.
- Stock Research tab switching reaches Trackers, Sources, Runs, Aggregate,
  Strategy Map, Work Products, Review Queue, and Evaluation.
- Key Stock Research tables render at least one row from fixtures.
- Link source, note source, and upload source forms submit mocked API calls.
- `/research/generalist?tab=analysis` loads Memo Tools.
- Memo Tools panels render toolbox, work products, review queue, evidence
  matrix, and task queue fixtures.
- A Memo Tools form/action submits a mocked API call without leaving the route.

Acceptance criteria:

- `npm --prefix frontend run test:browser` passes locally.
- Browser smoke fixtures are small and do not depend on real backend data.
- CI can run the test in headless mode without a live Claude process.

## Slice 4: Complete Stock Research Data Doctor

Goal: turn the existing read-only doctor endpoint into an operator-friendly
health check with CLI coverage and explicit stale/orphan checks.

Current state:

- Implemented: `/api/stock-research/doctor`.
- Implemented checks include missing root, missing tracker files, schema
  mismatch, missing source files, broken source traces, broken aggregate refs,
  broken strategy refs, missing exports, and broken product run refs.
- Missing: CLI entry point.
- Missing or incomplete: stale active job reporting and orphaned work-product
  checks beyond run refs.

Planned backend work:

- Add `scripts/stock_research_doctor.py` or `python -m server.stock_research_doctor`.
- Support `--json`, `--strict`, and `--max-idle-seconds`.
- Extend doctor output with:
  - stale active tracker runs,
  - stale aggregate jobs,
  - stale strategy-map jobs,
  - orphaned catalog work products with no backing artifact/export,
  - malformed or missing `version_history`,
  - catalog entries whose `supersedes` / `superseded_by` targets are missing,
  - run-ledger rows with no matching run/product.
- Keep the default behavior read-only.

Acceptance criteria:

- CLI exits `0` for ok, non-zero for `--strict` with errors.
- API and CLI share the same doctor implementation.
- Backend tests create each issue class and assert stable issue `type` values.

## Slice 5: Make Artifact Versioning Immutable

Goal: replace the current mutable catalog history with a clearer immutable
version model for Stock Research first, then Memo Tools.

Current state:

- Stock Research work products have `artifact_id`, `version`,
  `version_history`, `supersedes`, `superseded_by`, `export_paths`, reviewer,
  status, and review state.
- Memo Tools catalog currently emits `version: 1` rows from session artifacts.
- There is no durable `version_id` model or immutable generated-file ledger.

Target model:

- `artifact_id`: stable logical artifact identity.
- `version_id`: immutable version identity, for example
  `<artifact_id>:v<version>:<short-hash>`.
- `version`: monotonic integer for display.
- `supersedes_version_id`: previous immutable version, if any.
- `generated_files`: list of `{kind, path, sha256, bytes, created_at}`.
- `review_log`: append-only reviewer/action log.
- `action_log`: append-only system action log.

Implementation notes:

- Add compatibility fields so existing UI can still read `version`,
  `export_paths`, `supersedes`, and `superseded_by`.
- Store immutable version records separately from the latest catalog index.
- For Stock Research, write a version record when registering tracker reports,
  weekly aggregates, strategy maps, and generated exports.
- For Memo Tools, start with generated memos and memo packet outputs, then
  expand to analysis artifacts.

Acceptance criteria:

- Updating review status does not mutate historical version records.
- Re-registering the same artifact creates a new version when generated files
  or source refs change.
- Tests prove the supersedes chain can be walked from latest to first version.
- UI can show version count, current version, generated files, and latest review
  action without breaking existing catalog filters.

## Slice 6: Normalize Run Observability Across Memo And Stock Research

Goal: create one run-ledger shape that covers Memo Tools jobs and Stock Research
jobs.

Current state:

- Stock Research has `run-ledger.json` and `/api/stock-research/run-ledger`.
- Memo Tools has job metadata and progress logs, but no normalized run-ledger
  API/model equivalent to Stock Research.

Target ledger fields:

- `schema_version`
- `ledger_id`
- `workspace`: `stock_research` or `memo_tools`
- `job_kind`
- `artifact_id`
- `run_id`
- `tracker_id` or `company_id`
- `session_id`
- `period_id`
- `status`
- `created_at`
- `updated_at`
- `duration_ms`
- `token_usage`
- `estimated_cost_usd`
- `failure_reason`
- `fallback_used`
- `preserved_previous_artifact`
- `cancellation_reason`
- `source_count`
- `evidence_coverage`

Implementation plan:

- Extract common ledger normalization into a shared server module.
- Adapt Stock Research to use the shared normalizer while preserving its API.
- Add Memo Tools ledger entries for:
  - strategic risk mapper,
  - priority prompt harness,
  - thesis spine builder,
  - benchmark dashboard,
  - infographic source brief,
  - chart specs,
  - narrative hooks,
  - research task jobs,
  - final memo generation.
- Add `/api/companies/{company_id}/memo-analysis/run-ledger`.
- Optionally add a unified admin endpoint after both workspaces are writing
  the same shape.

Acceptance criteria:

- Stock Research tests still pass.
- Memo backend tests prove success, error, fallback, preserved artifact, cancel,
  and recovered states write ledger rows.
- The frontend can render Stock and Memo run rows with the same table component.

## Slice 7: Tighten Source Quality Scoring

Goal: make aggregate ranking more transparent and harder for weak sources to
outrank primary evidence.

Current state:

- `SOURCE_PRIORITY_SCORES` exists.
- Aggregate ranking uses signal importance, signal confidence, and
  `source_quality_score`.

Planned improvements:

- Add explicit source categories for:
  - SEC filing,
  - company press release,
  - earnings call transcript,
  - investor presentation,
  - regulatory filing outside SEC,
  - primary dataset,
  - broker/sell-side note,
  - reputable media,
  - weak media,
  - analyst note,
  - unsourced note.
- Add source-quality explanation fields to ranked signals:
  - `source_priority`
  - `source_quality_score`
  - `source_quality_reason`
  - `primary_source_count`
  - `weak_source_count`
- Penalize signals with no source traces or only notes.
- Add tests proving official filings/transcripts outrank media/notes when
  importance and confidence are otherwise similar.

Acceptance criteria:

- Aggregate output explains why a signal ranked where it did.
- Existing aggregate UI displays quality score and reason in a compact way.
- Ranking tests cover official, transcript, primary data, media, note, missing
  source, and mixed-source cases.

## Suggested Execution Order

1. Complete Stock Research panel extraction.
2. Complete Memo panel extraction.
3. Add browser smoke tests while the UI boundaries are fresh.
4. Extend the Stock Research doctor and add CLI.
5. Implement immutable Stock Research artifact versions.
6. Extend versioning into Memo Tools.
7. Extract shared run-ledger normalization and onboard Memo Tools.
8. Tighten source scoring and expose ranking explanations.

## Verification Commands

Run the relevant subset after each slice, and the full set before declaring the
outstanding plan complete:

```bash
python -m pytest tests/test_stock_research_trackers.py
python -m pytest tests/test_serena_analysis.py
python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
python -m py_compile server/stock_research.py server/serena_analysis.py server/api.py server/claude_runner.py
git diff --check
```

