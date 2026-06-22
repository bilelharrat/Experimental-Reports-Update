# Trader Retry And Flow Strategy

Date: 2026-06-17

This plan covers two connected fixes:

1. Retrying the failed `3350` / Metaplanet Inc. trader snapshot.
2. Rebalancing the trader-view agent flow so long sections do not hold the whole view hostage.

## Inputs Reviewed

- `data/_trader/3350__snapshot.progress.jsonl`
- `data/_trader_stats/3350.jsonl`
- `data/_trader/__all_public_refresh.progress.jsonl`
- `data/_trader_stats/*.jsonl`
- `server/companies_ai_public.py`
- `server/api.py`
- `server/trader_bilingual_fill.py`
- `server/trader_stats.py`

## Existing Run Evidence

The Metaplanet run started at `2026-05-29T03:07:35Z` and finished as a partial snapshot at `2026-05-29T03:12:44Z`.

Observed Metaplanet outcome:

| Metric | Value |
|---|---:|
| Total duration | 308.2s |
| Cost recorded | $7.61 |
| Total tokens recorded | 3.1M |
| Successful sections | 6 of 9 |
| Failed sections | 3 of 9 |

Metaplanet section timings:

| Section | Result |
|---|---:|
| Analyst sentiment | 56.7s, succeeded |
| Market session | 69.8s, succeeded |
| Momentum | 83.4s, succeeded |
| Tech movers | 116.8s, succeeded |
| Trader news | 126.1s, succeeded |
| Price & returns | 243.4s, succeeded |
| Upcoming catalysts | 245.1s result recorded, then `claude exited 1` |
| Research overview | stalled after 120s without output |
| Positioning structure | stalled after 120s without output |

Across the latest 18 trader stats records:

| Finding | Evidence |
|---|---:|
| Research overview failed | 18 of 18 latest runs |
| Positioning structure failed | 3 of 18 latest runs |
| Upcoming catalysts failed | 1 of 18 latest runs |
| Tech movers failed | 1 of 18 latest runs |
| Price & returns was the critical path | 9 of 18 latest runs |
| Positioning structure was the critical path | 7 of 18 latest runs |
| Latest-run total if done sequentially | 77.1 minutes |

The current single-company generator already starts the 9 sections in parallel with `ThreadPoolExecutor(max_workers=len(SNAPSHOT_PASSES))`. The bigger imbalance is that some section prompts take much longer, `Research overview` reliably stalls, bilingual completion is a post-generation pass, and bulk refresh runs companies sequentially.

## Strategy 1: Retry Metaplanet Inc. (`3350`)

### Short-Term Retry

Use the existing single-company force refresh. This is the only retry path currently available without code changes.

```bash
curl -X POST 'http://localhost:8000/api/companies/3350/trader/refresh?force=true'
```

Then watch:

```bash
curl -N 'http://localhost:8000/api/companies/3350/trader/refresh/stream'
```

After completion, verify:

```bash
curl 'http://localhost:8000/api/trader/stats/3350?limit=5'
```

Expected outcome for a successful retry:

- `data/_trader/3350__snapshot.progress.jsonl` ends with `done`.
- `data/_trader_stats/3350.jsonl` gets a new record.
- `failed_sections` is empty or reduced.
- The saved `trader_snapshot` has non-placeholder content for `research_overview`, `catalysts`, and `heat_card`.

### If The Same Sections Fail Again

Do not keep burning full refreshes. The observed failure pattern says `Research overview` is structurally broken, not just transient. If the next Metaplanet force refresh still fails `Research overview`, switch to implementing section-level retry before trying again.

The first section-level retry should support this request shape:

```http
POST /api/companies/3350/trader/refresh-sections
Content-Type: application/json

{
  "sections": ["research_overview", "catalysts", "heat_card"],
  "force": true,
  "preserve_existing_sections": true
}
```

Implementation behavior:

- Load the current saved `trader_snapshot`.
- Re-run only the requested sections.
- Keep existing successful sections unchanged.
- Replace only sections whose retry succeeds.
- If a section fails again, keep the previous successful version if one exists.
- If there is no previous successful version, write a clear section failure object instead of a silent empty placeholder.
- Record retry stats as a normal trader stats row with `retry_scope: "sections"` and `retried_sections`.

### Better Failed-Section UX

The current placeholder approach makes failed sections look mysterious. Failed sections should be first-class UI state.

For each section, persist:

- `status`: `fresh`, `stale`, `failed`, or `empty`
- `last_successful_at`
- `last_attempted_at`
- `last_error`
- `retryable`
- `source_run_id`

The trader view should render failed sections as compact, section-local status rows:

- Show the section title.
- Show `Failed on last refresh`.
- Show the short error, for example `stalled after 120s without output`.
- Provide a `Retry section` action.
- If stale data exists, show it with a `stale` label instead of replacing it with an empty card.

This avoids the current all-or-nothing feeling and makes partial snapshots usable.

## Strategy 2: Rebalance The Trader Agent Flow

### Current Shape

Single-company refresh:

1. `_run_trader_snapshot_job` starts one trader snapshot job.
2. `companies_ai_public.generate_snapshot` dispatches 9 section passes in parallel.
3. Each pass runs an independent Claude snapshot call.
4. Failed sections are replaced with `_EMPTY_SECTION` placeholders.
5. `trader_bilingual_fill.ensure_bilingual_completeness` runs after generation.
6. The full snapshot is saved and stats are recorded.

Bulk refresh:

1. `_run_refresh_all_trader_snapshots_job` gets all public companies.
2. It loops companies sequentially.
3. For each company, it calls `_run_trader_snapshot_job`.
4. The latest observed bulk run refreshed 17 companies from `03:07:34Z` to `04:22:28Z`.

### Problems To Fix

- `Research overview` fails in every latest recorded run.
- Long sections determine the whole job's wall-clock time even when fast cards finish early.
- Bulk refresh is sequential across companies, so 17 companies took about 75 minutes in the observed run.
- Failed sections are persisted as empty placeholders instead of actionable, retryable state.
- The stats dashboard should not emphasize cost at the high-level summary; it should emphasize freshness, failure count, critical path, and retry needs.
- The current status presentation needs to fit without horizontal scrolling.

### Proposed Pipeline

Move from "single whole-snapshot job" to a section DAG.

```text
company refresh
  -> section planner
  -> bounded parallel section workers
      -> price_card
      -> momentum_card
      -> sentiment_card
      -> heat_card
      -> catalysts
      -> trader_news
      -> research_overview/* sub-sections
      -> market_session
      -> tech_movers
  -> section merge
  -> targeted bilingual fill
  -> stats + UI state
```

### Split The Long Sections

`Research overview` should no longer be one large prompt. Split it into smaller independent sections and merge the result.

Suggested split:

| New pass | Output |
|---|---|
| `overview_business` | Business model, segment exposure, geography |
| `overview_financials` | Revenue/profit trend, balance sheet, dilution/debt |
| `overview_trader_thesis` | Bull/base/bear setup, what matters next |
| `overview_risks` | Key downside risks and uncertainty |
| `overview_questions` | Diligence questions and unresolved items |

Then run a small deterministic or low-token reducer that assembles `research_overview`.

`Positioning structure` should also be split if it remains a critical path:

- Options/volatility
- Short interest and float
- Insider/institutional activity
- Regime and confidence summary

`Price & returns` should be moved as far as possible toward deterministic market-data retrieval and calculation. It is the critical path in 9 of the 18 latest records, which is too slow for a data-heavy card.

### Add Section Artifacts

Persist section-level artifacts separately from the merged snapshot.

Suggested path:

```text
data/_trader_sections/{company_id}/{section_id}.json
```

Each artifact should include:

- `company_id`
- `section_id`
- `schema_version`
- `input_hash`
- `status`
- `started_at`
- `finished_at`
- `duration_ms`
- `cost_usd`
- `token_usage`
- `error`
- `data`

Refresh rules:

- Reuse a section when `input_hash` is unchanged and its TTL is still valid.
- Re-run only stale, forced, or failed sections.
- Merge from latest successful section artifacts.
- Keep stale successful data visible if a retry fails.

Suggested TTLs:

| Section | TTL |
|---|---:|
| Market session | 15 minutes |
| Price & returns | 15 minutes |
| Momentum | 30 minutes |
| Tech movers | 30 minutes |
| Trader news | 60 minutes |
| Catalysts | 12 hours |
| Analyst sentiment | 24 hours |
| Positioning structure | 4 hours |
| Research overview | 7 days |

### Parallelize Bulk Refresh Safely

Do not run 17 companies times 9 section workers at once. Use bounded concurrency.

Recommended default:

- `company_workers = 3`
- `section_workers_per_company = 3`
- `global_llm_workers = 6`

That lets multiple companies progress together without creating an unbounded Claude call storm.

The bulk job should emit queue events:

- `company_queued`
- `company_started`
- `section_started`
- `section_finished`
- `section_failed`
- `company_done`
- `company_partial`
- `bulk_done`

This also gives the active-jobs rail and stats dashboard a cleaner status model.

### Make Bilingual Fill Targeted

The current post-generation bilingual fill walks the whole snapshot and may issue many single-item Claude calls. Keep the reliability gains, but reduce the blast radius.

Changes:

- Prefer bilingual output inside each section pass.
- Run bilingual completion per section after that section finishes.
- Skip bilingual fill for unchanged cached sections.
- For section retries, fill only the retried section.
- Record translation duration separately from generation duration.

### Stats Dashboard Changes

High-level dashboard should focus on operational health, not cost.

Top-level columns/cards:

- Symbol
- Freshness
- Last duration
- Critical path section
- Failed sections count
- Retry needed
- Last change

Move cost to a drilldown row or company detail drawer.

Status should fit without horizontal scrolling:

- Replace long text statuses with compact badges: `Fresh`, `Partial`, `Failed`, `Running`, `Stale`.
- Put details in a tooltip, expansion row, or side drawer.
- Show failed section names as compact chips with count-first text, for example `3 failed`.

### Acceptance Criteria

- A failed section can be retried without rerunning the whole trader snapshot.
- A failed retry preserves the last successful data instead of replacing it with an empty placeholder.
- Metaplanet can retry `research_overview`, `catalysts`, and `heat_card` independently.
- `Research overview` no longer fails as one monolithic pass.
- Bulk refresh processes multiple companies concurrently with a global LLM limit.
- Stats dashboard fits in the available width without horizontal scrolling.
- High-level stats remove cost and emphasize freshness, duration, critical path, and failures.
- Progress logs expose section-level state clearly enough to explain what failed and what to retry.

## Implementation Order

1. Add section status metadata to saved snapshots and stats records.
2. Update trader UI and stats dashboard to show failed sections as actionable state.
3. Add `refresh-sections` API and wire it to existing `SNAPSHOT_PASSES`.
4. Split `Research overview` into smaller passes.
5. Add section artifact persistence and TTL reuse.
6. Move bilingual fill to section scope.
7. Convert bulk refresh from sequential company loop to bounded company concurrency plus a global LLM semaphore.
8. Move high-level dashboard cost into drilldown and compact the status column.

## Immediate Recommendation

Run one Metaplanet force refresh to confirm whether the non-overview failures were transient. If `Research overview` fails again, stop full retries and implement section-level retry plus the research-overview split first.
