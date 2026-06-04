# Serena Memo Studio Completion Handoff

Last updated: 2026-06-03

This document is the finish-line handoff for completing Serena's Memo Studio.
It assumes the current `main` checkout already includes durable analysis
sessions, the Memo Studio UI, selected research-task jobs, approved-analysis
memo generation, and the Claude-backed `strategic_risk_mapper`.

## Operating Rules

- Work directly on `main`; do not create branches or worktrees.
- Keep `data/uploads/<slug>/` excluded from memo analysis.
- Serena's allowed company research folder is `data/research/<slug>/`.
- Keep deterministic implementations as direct-call test/fallback behavior.
- When adding Claude-backed tools, preserve existing artifact schemas and
  previous good artifacts on Claude failure.
- Update `docs/serena-agent-analysis-tools.md` as items are completed.

## Current State

The core workflow is functional:

- `server/serena_analysis.py` owns YAML-backed analysis sessions under
  `data/serena_analysis/<company_slug>/<session_id>/`.
- Memo Studio can generate and edit strategic risks, priorities, research
  tasks, thesis spine, chart specs, narrative hooks, benchmark scaffolds, and
  approval state.
- Selected research tasks run as Claude-backed background jobs with progress
  logs, active-job rail entries, SSE streaming, result persistence, and
  deterministic fallback.
- `strategic_risk_mapper` now runs as a Claude-backed background analysis-tool
  job from the API and uses the same rail/log/SSE conventions.
- Final memo generation accepts `analysis_session_id` and is blocked until the
  analysis session and thesis spine are approved.
- Interrupted Serena research-task and analysis-tool runs are recovered from
  stale `running` state on session reads and `/api/jobs/active` polling, using
  terminal/missing/idle progress-log detection while preserving prior artifacts
  and results.

Latest backend verification from this checkout:

```bash
PYTHONPATH=. pytest -q tests/test_serena_analysis.py  # 22 passed
PYTHONPATH=. pytest -q                              # 174 passed, 2 deselected
PYTHONPATH=. python -m py_compile server/serena_analysis.py server/api.py
git diff --check
```

Prior frontend verification from the previous handoff remains:

```bash
npm test       # 56 passed
npm run build  # passed, Vite chunk warning only
```

## What Remains

### P0 - Convert More Deterministic Analysis Tools To Claude Jobs

Recommended order:

1. `private_benchmark_dashboard`
2. `chart_spec_builder`
3. `narrative_hooks`

Use the `strategic_risk_mapper` pattern:

- API starts a background job for the Claude-backed tool and returns `202`.
- `tool_runs[tool_name].status` transitions through `running`, `done`, or
  `error`.
- Progress writes to
  `data/serena_analysis/<company>/<session>/logs/tools/<tool>.progress.jsonl`.
- `/api/jobs/active`, `/api/jobs/log`, and the tool SSE endpoint expose the
  job to the AI Tasks rail.
- Claude output is normalized before persistence.
- Existing artifact is preserved on Claude failure.
- Deterministic fallback is written only when there is no previous good
  artifact.
- `_refresh_memo_packet(session)` runs after success/fallback.

Files to extend:

- `server/serena_analysis.py`
- `server/claude_runner.py`
- `server/api.py`
- `tests/test_serena_analysis.py`

### P0 - Stale Run Recovery / Cancellation

Recovery is implemented as of 2026-06-03:

- Session reads and `/api/jobs/active` polling sweep Serena sessions.
- Interrupted `running` research tasks in
  `artifacts.research_tasks.tasks[*]` are marked `error`.
- Interrupted `running` analysis tools in `tool_runs[tool_name]` are marked
  `error`.
- Recovery handles missing, terminal, and idle progress logs with the
  active-job timeout and preserves previous artifacts/results.

Optional remaining enhancement: add an explicit cancel endpoint that records a
terminal `error` event immediately for user-requested cancellation.

### P1 - Readiness Waivers / Review State

Current issue: additional areas needed are computed and displayed but cannot be
reviewed, waived, or explained.

Likely artifact:

```yaml
readiness_reviews:
  updated_at: ...
  items:
    - id: chart-gap-chart-adoption-ladder
      status: waived
      rationale: ...
      reviewed_at: ...
```

Backend work:

- Add artifact patch handling if a specialized merge is needed.
- Update `_readiness()` so reviewed/waived gaps do not block the final gate, or
  show separately if they should remain visible.

Frontend work:

- Add waive/reopen controls in `MemoAnalysisDashboard.vue`.
- Display rationale and review timestamp.

### P1 - Private Benchmark Dashboard Completion

Current issue: `private_benchmark_dashboard` is a deterministic scaffold with
nullable metrics and read-only rows.

Finish target:

- Claude-backed mature public comp research.
- Editable public comp rows.
- Metrics for revenue growth, gross margin, EV/revenue, EV/EBITDA, FCF margin,
  and Rule of 40 where available.
- Source trace per metric or row.
- Benchmark gaps and "must prove" claims that flow into `memo_packet.md`.

Recommended reuse:

- Public stock snapshot concepts in `server/trader_stats.py` and related
  public-company dashboard code.
- Existing `claude_runner.run_web_research_json` or a specialized Serena
  benchmark runner.

### P1 - Memo Grader And Training Loop

Current issue: `memo_grader` only writes a waiting scaffold.

Finish target:

- Let Serena select a completed memo/report.
- Grade highlight sharpness, risk sharpness, evidence quality, chart clarity,
  intro strength, ending/recommendation strength, and missing diligence.
- Persist feedback under `data/serena_training/<company_slug>/`.
- Generate or update distilled `serena_memo_lessons.md`.
- Inject distilled lessons into future analysis and memo prompts without
  letting stale lessons override current evidence.

### P2 - Approval, Audit, And Test Cleanup

- Add per-artifact version history or audit trail beyond timestamps and
  `tool_runs`.
- Refine thesis-only approval; current analysis approval marks the thesis spine
  approved.
- Add dedicated prompt-construction tests for priority prompts and Claude tool
  prompts.
- Add dedicated nullable metric/schema tests for benchmark artifacts.
- Split `MemoAnalysisDashboard.vue` into smaller components if it gets harder
  to maintain.

## Suggested Next Slice

Convert `private_benchmark_dashboard` to a Claude-backed job.

Why this next:

- It is the first remaining P0 Claude-tool conversion in the recommended
  order.
- The shared tool job, active-rail, SSE, and stale-recovery paths are now in
  place for reuse.
- Benchmark context materially affects final memo quality and currently remains
  a deterministic scaffold.

Minimum acceptance criteria:

- API starts a background benchmark job and returns `202`.
- The tool writes progress JSONL and appears in `/api/jobs/active`.
- Claude output is normalized into the existing benchmark artifact schema.
- Previous good benchmark artifacts are preserved on Claude failure.
- Deterministic fallback is used only when no previous good artifact exists.

## Do Not Regress

- Never add `data/uploads/<slug>/` to Claude allow-lists or memo prompts.
- Do not make final memo generation possible from an unapproved analysis
  session.
- Do not let priority changes reorder or delete existing research task results
  for the same `risk_id`.
- Do not overwrite a previous good artifact just because Claude failed.
- Do not require Claude availability for the unit test suite.

## Exit Checklist For Completion

Before calling the full Memo Studio work complete:

- All major analysis tools that materially affect the memo are Claude-backed or
  deliberately marked deterministic by design.
- Interrupted `running` tasks/tools recover cleanly.
- Additional areas can be reviewed or waived with rationale.
- Benchmark dashboard contains usable public-comp metrics and source traces.
- Completed memos can be graded and lessons reused.
- The final memo generated from an approved analysis packet reflects the
  selected risks, research task results, thesis spine, charts, narrative hooks,
  and benchmark context.
- Run:

```bash
PYTHONPATH=. pytest -q tests/test_serena_analysis.py
PYTHONPATH=. pytest -q
npm test
npm run build
PYTHONPATH=. python -m py_compile server/serena_analysis.py server/api.py server/claude_runner.py
git diff --check
```
