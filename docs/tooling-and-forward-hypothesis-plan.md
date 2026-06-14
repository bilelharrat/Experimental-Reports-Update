# Tooling And Forward Hypothesis Plan

Status date: 2026-06-14

This plan covers two related efforts:

- Raise repository tooling toward a high-confidence engineering bar.
- Add a forward-only hypothesis analysis loop for Stock Research so weekly
  hypotheses can be evaluated and used for calibration without lookahead.

The hypothesis system is primarily a forward-cycle system. Historical weeks are
only a debug harness for logic bugs. Backfilled hypotheses must never be treated
as training-eligible model evidence.

## Principles

- Work directly on `main`; do not create worktrees or feature branches.
- Prefer one reproducible command for local and CI quality gates.
- Make correctness checks explicit and runnable before adding more AI behavior.
- Store every live hypothesis as an immutable point-in-time artifact.
- Keep `forward_live` and `debug_backfill` data separated in schema, UI, and
  training eligibility.
- Never regenerate a historical hypothesis and present it as if it was created
  at the original time.
- Prevent lookahead leakage by recording source cutoffs, input manifests, prompt
  versions, model ids, and generated artifact hashes.

## Definitions

- `forward_live`: a hypothesis snapshot generated during the real weekly cycle,
  before the outcome period is known. These rows can become training-eligible
  only after evaluation is complete.
- `debug_backfill`: a synthetic historical run used to test date-window logic,
  source filtering, return math, schema writes, and UI rendering. These rows are
  never training-eligible.
- `vintage_date`: the as-of date for the hypothesis snapshot.
- `eligible_source_cutoff`: the latest timestamp a source may have to be
  included in the snapshot input manifest.
- `evaluation_window`: the period over which the hypothesis outcome is measured.
- `input_manifest_sha256`: stable hash of the frozen source/run/artifact inputs
  used to create the hypothesis.

## Target Data Model

### Hypothesis Snapshot

Store under `data/stock_research/hypotheses/<vintage_date>/hypotheses.json`
or an equivalent versioned workspace path.

Fields:

- `schema_version`
- `hypothesis_id`
- `vintage_kind`: `forward_live` or `debug_backfill`
- `eligible_for_training`: boolean, default `false`
- `generated_at`
- `vintage_date`
- `eligible_source_cutoff`
- `evaluation_window_start`
- `evaluation_window_end`
- `tracker_id`
- `tracker_type`
- `company_id`
- `ticker`
- `claim`
- `direction`: `bullish`, `bearish`, `neutral`, or `watch`
- `expected_horizon_days`
- `confidence`
- `source_refs`
- `source_quality_score`
- `source_quality_reason`
- `primary_source_count`
- `weak_source_count`
- `prompt_version`
- `model_id`
- `generation_mode`: `live_model`, `deterministic_fixture`, or `manual`
- `input_manifest`
- `input_manifest_sha256`
- `artifact_id`
- `version_id`
- `frozen`: always `true` after write
- `created_by`
- `notes`

### Hypothesis Outcome

Store under the same vintage path or in
`data/stock_research/hypotheses/<vintage_date>/outcomes.json`.

Fields:

- `schema_version`
- `hypothesis_id`
- `evaluated_at`
- `evaluation_window_start`
- `evaluation_window_end`
- `ticker`
- `benchmark_ticker`
- `start_price`
- `end_price`
- `absolute_return_pct`
- `benchmark_return_pct`
- `relative_return_pct`
- `max_drawdown_pct`
- `realized_volatility_pct`
- `directional_result`: `hit`, `miss`, `neutral`, or `unresolved`
- `confidence_bucket`
- `calibration_bucket`
- `outcome_notes`
- `market_data_source`
- `market_data_snapshot_sha256`
- `eligible_for_training`

### Training Summary

Store append-only summaries under
`data/stock_research/hypotheses/training_summaries/`.

Only include rows where:

- `vintage_kind == "forward_live"`
- `eligible_for_training == true`
- outcome evaluation is complete
- the snapshot was generated before `evaluation_window_start`

Do not include `debug_backfill` rows.

## Tooling Plan

### Slice T1 - Unified Quality Gate

Implementation:

- Add `scripts/quality.sh`.
- Run:
  - `uv sync --locked`
  - `python -m pytest`
  - `python -m py_compile server/stock_research.py server/serena_analysis.py server/api.py server/claude_runner.py`
  - `npm --prefix frontend ci`
  - `npm --prefix frontend test`
  - `npm --prefix frontend run build`
  - `npm --prefix frontend run test:browser`
  - `git diff --check`
- Add a faster `scripts/quick-check.sh` for common local iteration:
  - focused pytest when arguments are supplied
  - `npm --prefix frontend test`
  - `git diff --check`

Acceptance criteria:

- One command verifies the same baseline developers and CI use.
- Generated artifacts such as `frontend/test-results/` remain ignored or
  cleaned up.
- The command fails on the first broken gate and prints the failed command.

Targeted tests:

- Run `scripts/quality.sh` successfully.
- Temporarily introduce a trailing whitespace fixture locally and confirm
  `git diff --check` fails, then revert the fixture.

### Slice T2 - CI

Implementation:

- Add `.github/workflows/ci.yml`.
- Use two jobs:
  - `quick`: Python install, frontend install, unit tests, lint once available.
  - `full`: full pytest, build, Playwright browser smoke.
- Cache `uv` and npm dependencies.
- Use `npm ci`, not `npm install`.
- Upload Playwright traces/screenshots only on failure.

Acceptance criteria:

- CI runs on pushes to `main` and pull requests if PRs are ever used.
- CI does not require live Claude or real API keys.
- CI uses fixture/mocked browser tests only.

Targeted tests:

- Validate workflow YAML syntax.
- Run the CI commands locally through `scripts/quality.sh`.

### Slice T3 - Lint And Format

Implementation:

- Add Ruff to Python dev dependencies.
- Configure:
  - `ruff format`
  - `ruff check`
- Add frontend ESLint with Vue rules.
- Add package scripts:
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run format:check` if a formatter is added.
- Add these gates to `scripts/quality.sh` after the first clean baseline.

Acceptance criteria:

- New code is linted automatically by the quality gate.
- Existing noisy rules are either fixed or explicitly deferred with comments in
  config, not ignored ad hoc.

Targeted tests:

- Run Ruff against `server/`, `scripts/`, and `tests/`.
- Run ESLint against `frontend/src` and `frontend/tests`.
- Confirm both commands are invoked by `scripts/quality.sh`.

### Slice T4 - Schema And API Contracts

Implementation:

- Add Pydantic models for high-value payloads:
  - run ledger rows
  - Stock Research dashboard
  - Stock Research doctor
  - work-product versions
  - hypothesis snapshots
  - hypothesis outcomes
- Add OpenAPI schema snapshot tests for the new hypothesis endpoints.
- Add JSON/YAML validators for durable stores.

Acceptance criteria:

- API payload shape changes fail tests unless snapshots/models are updated.
- Durable malformed rows produce stable doctor issue types.

Targeted tests:

- Unit tests validate good and bad hypothesis snapshot rows.
- API tests assert response models for create/list/evaluate endpoints.
- Doctor tests assert stable issue `type` values for malformed hypothesis data.

## Forward Hypothesis Plan

### Slice H1 - Durable Snapshot Store

Implementation:

- Add `server/hypothesis_store.py`.
- Add helpers:
  - `hypothesis_root()`
  - `vintage_dir(vintage_date)`
  - `list_hypotheses(vintage_kind=None)`
  - `write_hypothesis_snapshot(row)`
  - `write_hypothesis_outcome(row)`
  - `freeze_input_manifest(manifest)`
- Reject writes that mutate an existing frozen `hypothesis_id`.
- Default `eligible_for_training` to `false`.
- Enforce `debug_backfill` rows cannot become training-eligible.

Acceptance criteria:

- Snapshot records are immutable after creation.
- Duplicate writes with identical content are idempotent.
- Duplicate writes with different content fail.
- `debug_backfill` rows are never training-eligible.

Targeted tests:

- `tests/test_hypothesis_store.py`
  - creates a `forward_live` snapshot
  - verifies input-manifest hash stability
  - rejects mutation of frozen rows
  - rejects training eligibility for `debug_backfill`
  - permits training eligibility for completed `forward_live` rows only

### Slice H2 - Point-In-Time Input Builder

Implementation:

- Add a builder that creates an input manifest from existing Stock Research
  data:
  - trackers
  - tracker runs
  - aggregate signals
  - source refs
  - work-product version ids
- Filter every input by `eligible_source_cutoff`.
- Include exact artifact ids and version ids where available.
- Include source created timestamps and paths.

Acceptance criteria:

- Inputs created after the cutoff are excluded.
- Inputs with missing timestamps are either excluded or explicitly marked with a
  stable warning.
- The manifest hash changes when eligible inputs change and remains stable when
  only non-eligible future inputs change.

Targeted tests:

- Fixture with one source before cutoff and one after cutoff.
- Fixture with two tracker runs where only the earlier run is eligible.
- Assert the future source/run is absent from the manifest and hash.
- Assert warnings are stable for missing timestamps.

### Slice H3 - Forward Weekly Snapshot Command

Implementation:

- Add CLI:
  - `python -m server.hypothesis_cycle create --vintage-date YYYY-MM-DD`
- Default `vintage_kind` to `forward_live`.
- Refuse to create `forward_live` snapshots for a vintage date in the past
  unless an explicit `--allow-debug-backfill` flag is used, which writes
  `debug_backfill`.
- Create hypotheses from existing aggregate ranked signals first.
- Later, allow a model-backed hypothesis generator, but keep the same store.

Acceptance criteria:

- The normal weekly command produces only `forward_live` snapshots for the
  current cycle.
- Backfill command marks rows as `debug_backfill`.
- The command writes run-ledger rows for observability.

Targeted tests:

- Freeze current date in tests.
- `create --vintage-date 2026-06-14` creates `forward_live`.
- `create --vintage-date 2026-06-07` without debug flag fails.
- `create --vintage-date 2026-06-07 --allow-debug-backfill` creates
  `debug_backfill`.
- Assert backfill rows have `eligible_for_training == false`.

### Slice H4 - Debug Backfill Harness

Implementation:

- Add CLI:
  - `python -m server.hypothesis_cycle debug-backfill --vintage-date YYYY-MM-DD --horizon-days 7`
- Initial debug dates based on this plan date:
  - as-of `2026-05-31`, evaluate `2026-06-01` through `2026-06-07`
  - as-of `2026-06-07`, evaluate `2026-06-08` through `2026-06-14`
- Use deterministic fixtures first; do not use these rows for training.

Acceptance criteria:

- Debug backfills are visibly labeled in API/UI payloads.
- Debug rows cannot be promoted to training data.
- Date windows are correct and stable.

Targeted tests:

- Assert `2026-05-31` debug vintage uses `2026-06-01` to `2026-06-07`.
- Assert `2026-06-07` debug vintage uses `2026-06-08` to `2026-06-14`.
- Assert any source with timestamp after the vintage cutoff is excluded.
- Assert all debug outcomes remain `eligible_for_training == false`.

### Slice H5 - Outcome Evaluator

Implementation:

- Add market-data adapter interface:
  - `get_price(ticker, date)`
  - `get_return(ticker, start_date, end_date)`
  - fixture adapter for tests
  - live adapter later, if needed
- Evaluate:
  - absolute return
  - benchmark-relative return
  - directional hit/miss
  - drawdown and volatility if enough price points exist
- Store market data snapshot hashes with outcomes.

Acceptance criteria:

- Evaluator never mutates the original hypothesis snapshot.
- Missing prices produce `unresolved`, not a false miss.
- Benchmark-relative scoring is deterministic.

Targeted tests:

- Bullish hypothesis with positive relative return is `hit`.
- Bullish hypothesis with negative relative return is `miss`.
- Bearish hypothesis with negative relative return is `hit`.
- Neutral/watch hypotheses use separate neutral/unresolved logic.
- Missing ticker or missing price yields `unresolved`.
- Market-data fixture hash is persisted.

### Slice H6 - Training-Eligible Calibration

Implementation:

- Add `python -m server.hypothesis_cycle calibrate`.
- Only include completed `forward_live` outcomes.
- Produce:
  - hit rate by confidence bucket
  - hit rate by source category
  - hit rate by tracker type
  - average relative return by direction
  - high-confidence wrong examples
  - weak-source false positives
- Write a compact training summary artifact.

Acceptance criteria:

- `debug_backfill` rows are excluded even if they have outcomes.
- Calibration summaries are append-only and versioned.
- Summary includes enough examples to inspect failure modes.

Targeted tests:

- Mixed fixture with `forward_live` and `debug_backfill`.
- Assert only `forward_live` completed outcomes enter the summary.
- Assert confidence buckets and source-category metrics are correct.
- Assert high-confidence misses are listed.

### Slice H7 - API And UI

Implementation:

- Add endpoints:
  - `GET /api/stock-research/hypotheses`
  - `GET /api/stock-research/hypotheses/{vintage_date}`
  - `POST /api/stock-research/hypotheses/create`
  - `POST /api/stock-research/hypotheses/{vintage_date}/evaluate`
  - `GET /api/stock-research/hypotheses/calibration`
- Add a Stock Research tab or panel:
  - current live vintage status
  - pending evaluation windows
  - completed outcomes
  - debug backfill badge
  - training eligibility badge

Acceptance criteria:

- Analysts can see what was known at the time.
- Debug backfills are visually distinct from forward-live cycles.
- Training eligibility is explicit and not inferred by the UI.

Targeted tests:

- Backend API tests for list/detail/create/evaluate.
- Vue component tests for:
  - empty state
  - pending live hypothesis
  - completed live outcome
  - debug backfill warning badge
  - training eligibility badge
- Playwright smoke for opening the hypothesis panel with mocked API data.

### Slice H8 - Weekly Automation Guardrails

Implementation:

- Add operator command docs for the weekly cycle:
  - create live hypotheses at the chosen weekly cutoff
  - evaluate prior live vintage after its window closes
  - run calibration summary
- Add doctor checks:
  - missing current live vintage
  - live vintage generated after its evaluation window started
  - outcome missing after window close
  - training summary includes debug rows
  - source cutoff violation

Acceptance criteria:

- The doctor can tell whether the forward cycle is healthy.
- The workflow can be run manually before any scheduler is added.

Targeted tests:

- Doctor reports missing current vintage as warning.
- Doctor reports generated-after-window-start as error.
- Doctor reports debug row in training summary as error.
- Doctor reports source cutoff violation as error.

## Initial Debug Backfill Windows

Use these only after H1-H5 exist, and only as `debug_backfill`:

| Debug vintage | Evaluation start | Evaluation end | Purpose |
|---|---:|---:|---|
| 2026-05-31 | 2026-06-01 | 2026-06-07 | Validate previous-week window math and no-lookahead filters. |
| 2026-06-07 | 2026-06-08 | 2026-06-14 | Validate latest completed weekly outcome logic. |

These rows must stay `eligible_for_training: false`.

## Target Verification Commands

After implementation slices are complete, the expected verification set is:

```bash
scripts/quality.sh
python -m pytest tests/test_hypothesis_store.py
python -m pytest tests/test_hypothesis_cycle.py
python -m pytest tests/test_stock_research_trackers.py
python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
git diff --check
```

## Suggested Execution Order

1. Add `scripts/quality.sh` and CI skeleton.
2. Add Ruff/ESLint as non-negotiable gates.
3. Add hypothesis snapshot/outcome schemas and durable store.
4. Add point-in-time input builder.
5. Add forward weekly snapshot command.
6. Add debug backfill harness for `2026-05-31` and `2026-06-07`.
7. Add outcome evaluator with fixture market-data adapter.
8. Add calibration summaries that only use completed `forward_live` rows.
9. Add API/UI panels.
10. Add doctor checks and weekly operator docs.
