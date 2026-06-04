# Serena Agent Analysis Tools Plan

Last updated: 2026-06-03

This document tracks the plan to improve Serena's investment memo agent by
adding targeted analysis tools, a human-in-the-loop workflow, persistent
training feedback, and a UI analysis dashboard.

All work is tracked here as it is completed. Each item should move through:

- `Not Started`
- `In Progress`
- `Blocked`
- `Done`
- `Deferred`

When an item is completed, update its status, add the completion date, and add
a short note explaining what shipped and where it lives in the codebase.

## Objective

Move Serena's workflow from one-shot memo generation to a co-created investment
judgment process:

1. Build sharp strategic risks and decision questions.
2. Let Serena prioritize the risks and choose what to research.
3. Convert the selected risks into a thesis spine.
4. Build chart/table plans and benchmark context before drafting.
5. Generate the final memo only after the analysis is approved.
6. Grade completed memos and feed lessons back into future runs.

## Current Baseline

| Area | Status | Notes |
|---|---|---|
| Existing memo pipeline inspected | Done | `memo_prep.py`, `memo_analysis.py`, `claude_runner.py`, and the memo skill were reviewed. Current flow is single-shot generation. |
| Existing Console workflow inspected | Done | Console already supports resumable human-AI interaction and should be reused where possible. |
| Existing research library inspected | Done | `data/research/<slug>/` is Serena's intended company folder, but the memo flow does not yet consume it. |
| Existing public-company dashboard inspected | Done | Public trader snapshots already include peer context, scenarios, and diligence questions that can inform private benchmarking. |

## Workstreams

### 1. Serena Analysis Sessions

Persist pre-memo analysis work under:

```text
data/serena_analysis/<company_slug>/<session_id>/
```

Planned artifacts:

- `input_manifest.json`
- `strategic_risks.json`
- `risk_priorities.json`
- `research_tasks.json`
- `thesis_spine.json`
- `chart_specs.json`
- `narrative_hooks.json`
- `benchmark_dashboard.json`
- `memo_packet.md`

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define analysis-session storage schema | Done | 2026-06-02 | First durable YAML-backed schema added under `data/serena_analysis/<company>/<session>/`. |
| Add `server/serena_analysis.py` | Done | 2026-06-02 | Added persistent session/tool/artifact module. |
| Add session create/read/update helpers | Done | 2026-06-02 | Added current-session creation, tool execution, artifact patching, approval, and artifact file writes. |
| Add artifact versioning and audit metadata | In Progress | 2026-06-02 | Session version, timestamps, status, approval, and tool run metadata are stored; per-artifact version history is still future work. |

### 2. Strategic Risk Mapper

Generate 5-8 sharp strategic risks for a company. Risks should be framed as
decision questions, not generic risk labels.

Example:

```text
Can they achieve economically viable deployment at scale?
```

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define strategic-risk JSON schema | Done | 2026-06-02 | First schema persists `id`, `title`, `decision_question`, bull/bear answers, evidence, sources, prompt, memo section, and status. |
| Add risk-generation prompt/tool | Done | 2026-06-03 | `strategic_risk_mapper` now runs as a Claude-backed background job from the API, streams progress through the AI Tasks rail, and keeps deterministic output as the direct-call/test/fallback path. |
| Include bull answer, bear answer, evidence needed, best sources, and memo section | Done | 2026-06-02 | Included in persisted risk objects. |
| Add tests for schema and missing-field handling | Done | 2026-06-02 | Added `tests/test_serena_analysis.py` coverage for humanoid-specific risks. |

### 3. Priority And Prompt Harness

Let Serena rank risks, choose which ones to research, and generate targeted
research prompts from those selections.

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Add risk priority model | Done | 2026-06-02 | Added default priority model in `risk_priorities`. |
| Add prompt-builder output artifact | Done | 2026-06-02 | Added `research_tasks` artifact with targeted prompts. |
| Regenerate tasks from selected risks in priority order | Done | 2026-06-02 | `risk_priorities` PATCH now normalizes contiguous ranks, persists selected flags, and rebuilds `research_tasks` from selected risks only. |
| Add ability to run selected prompts through Console or background jobs | Done | 2026-06-03 | `POST /memo-analysis/research-tasks/{task_id}/run` now enqueues a Claude-backed background job, streams progress through the AI Tasks rail, persists Claude result payloads, and falls back to the deterministic local result when Claude is unavailable. |
| Add tests for prompt construction | In Progress | 2026-06-02 | Tool flow is covered indirectly; dedicated prompt-construction tests still needed. |

### 4. Thesis Spine Builder

Convert selected analysis into the true memo core:

- 3-5 Investment Highlights
- 3-5 Investment Risks
- recommendation logic
- top 3 gating diligence questions
- what must be true for the bull case
- what would make Serena pass

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define `thesis_spine.json` schema | Done | 2026-06-02 | First schema includes highlights, risks, recommendation logic, gates, bull-case requirements, and pass triggers. |
| Add thesis-spine generation tool | Done | 2026-06-03 | `thesis_spine_builder` now runs as a Claude-backed background job from the API, streams progress through the AI Tasks rail, preserves previous good thesis artifacts on Claude failure, and keeps deterministic output as the direct-call/test/fallback path. |
| Add editable review state for highlights and risks | Done | 2026-06-02 | `MemoAnalysisDashboard.vue` now provides inline editors for highlight, risk, and top-gating-question text and saves through the artifact PATCH endpoint. |
| Make memo generation require approved thesis spine | Done | 2026-06-02 | `memo_prep.bootstrap_memo_run` now rejects analysis-backed memo generation unless the session is approved for memo use and its thesis spine is approved. |

### 5. Research Folder Memo Ingestion

Wire Serena's research folder into the memo process while keeping
`data/uploads/<slug>/` off-limits.

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Record `data/research/<slug>/` files in memo run manifest | Done | 2026-06-02 | Memo prep records analysis-session metadata; analysis session records research file manifest. |
| Add research folder to memo Claude `--add-dir` paths | Done | 2026-06-02 | `run_investment_memo` adds the Serena research folder when present. |
| Update memo prompt to read raw research files | Done | 2026-06-02 | Prompt now maps Serena's company folder to `data/research/<slug>/` and instructs raw-file use. |
| Preserve hard separation from Document Library | Done | 2026-06-02 | Prompt still explicitly forbids `data/uploads/<slug>/`. |
| Add tests proving `data/uploads/<slug>/` remains excluded | Done | 2026-06-02 | Prompt test asserts the exclusion language remains present. |

### 6. Chart Spec Builder

Generate chart/table plans before the memo is written.

Candidate specs:

- growth bridge waterfall
- public comps benchmark table
- valuation timing table
- risk severity matrix
- deployment/adoption ladder
- scenario matrix

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define `chart_specs.json` schema | Done | 2026-06-02 | First schema includes title, takeaway, required data, availability, and final-memo toggle. |
| Add chart-spec generation tool | Done | 2026-06-02 | Added deterministic `chart_spec_builder`. |
| Track required data and availability per chart | Done | 2026-06-02 | Tool marks each chart as available, partial, or missing. |
| Add include/exclude flag for final memo | Done | 2026-06-02 | Added `include_in_final_memo`. |

### 7. Opening And Ending Punch Tool

Generate alternative openings and endings from the approved thesis spine. Serena
selects the version that should drive final memo tone.

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define `narrative_hooks.json` schema | Done | 2026-06-02 | First schema includes opening options, ending options, and selected ids. |
| Add opening/ending generation tool | Done | 2026-06-02 | Added deterministic `narrative_hooks` tool. |
| Add selected-opening and selected-ending state | Done | 2026-06-02 | Persisted selected opening/ending ids. |
| Feed selected hooks into final memo prompt | Done | 2026-06-02 | `memo_packet.md` now includes the selected opening and ending from `narrative_hooks`, so the memo runner sees the chosen hook text through the approved analysis packet. |

### 8. Memo Grader And Training Loop

Grade completed memos like homework and preserve lessons for future runs.

Rubric areas:

- investment highlight sharpness
- risk sharpness
- evidence quality
- chart clarity
- intro strength
- ending/recommendation strength
- missing diligence
- correct-answer rewrite
- what to read
- how to think next time

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define memo grading rubric schema | In Progress | 2026-06-02 | First rubric scaffold is persisted by `memo_grader`. |
| Add grader tool for completed memo runs | In Progress | 2026-06-02 | Tool currently records a waiting state when no completed memo is selected. |
| Store feedback under `data/serena_training/` | Not Started |  |  |
| Generate distilled `serena_memo_lessons.md` | Not Started |  |  |
| Inject lessons into future analysis/memo prompts | Not Started |  |  |

### 9. Private Company Benchmark Dashboard

Create a private-company underwriting dashboard using mature public comps and
sell-side/public metric benchmarks.

Dashboard should include:

- comparable public companies
- why each comp is relevant
- revenue growth
- margin profile
- EV/revenue and EV/EBITDA where available
- FCF margin / Rule of 40 where available
- sell-side thesis themes
- benchmark gaps
- what the private company must prove to deserve the comp

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Define private benchmark dashboard schema | Done | 2026-06-02 | First schema includes public comps, metric placeholders, sell-side theme, gaps, and must-prove items. |
| Reuse public snapshot peer-context concepts where practical | In Progress | 2026-06-02 | Current scaffold mirrors peer-context concepts; direct public snapshot reuse remains future work. |
| Add mature-public-comps research tool | In Progress | 2026-06-02 | Added deterministic comp scaffold; Claude/web-backed mature comp research remains future work. |
| Add benchmark dashboard persistence | Done | 2026-06-02 | Persisted as `benchmark_dashboard`. |
| Add tests for schema and nullable metrics | In Progress | 2026-06-02 | Flow is covered indirectly; dedicated nullable metric tests still needed. |

### 10. UI Analysis Dashboard

Add a Memo Studio / Analysis Dashboard in the company Research view. This UI
must display tools, results, missing areas, and readiness to generate the final
memo.

Planned frontend components:

- `MemoAnalysisDashboard.vue`
- `memo/StrategicRiskBoard.vue`
- `memo/ThesisSpineEditor.vue`
- `memo/ResearchTaskQueue.vue`
- `memo/ChartSpecPanel.vue`
- `memo/BenchmarkDashboard.vue`
- `memo/MemoReadinessGate.vue`

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Add Research view tab or panel for Memo Studio | Done | 2026-06-02 | Added `analysis` tab in `ResearchView.vue`. |
| Add tool launcher UI | Done | 2026-06-02 | Added tool launcher in `MemoAnalysisDashboard.vue`. |
| Display current analysis state and tool run history | Done | 2026-06-02 | Dashboard shows session id/status, tool status, last run time, and summaries. |
| Display strategic risk board with prioritization | Done | 2026-06-02 | Risk board now sorts by saved rank and supports compact up/down reprioritization plus selected-for-research checkboxes saved through `risk_priorities`. |
| Add editable highlights and risks draft | Done | 2026-06-02 | Added inline text editors for highlights, risks, and top gating questions with artifact PATCH persistence. |
| Add research task queue | Done | 2026-06-03 | Research task queue is displayed after prompt harness runs and now supports per-task deterministic runs with persisted status/result summaries. |
| Add chart/table plan panel | Done | 2026-06-02 | Chart specs are displayed with data availability and final-memo include/exclude toggles. |
| Add narrative hooks selector | Done | 2026-06-02 | Opening and ending options now have single-select controls saved to `narrative_hooks`. |
| Add private benchmark dashboard panel | Done | 2026-06-02 | Benchmark comps table is displayed. |
| Add memo readiness gate | Done | 2026-06-02 | Readiness gate and progress bar are displayed. |
| Add additional-areas-needed panel | Done | 2026-06-02 | Dashboard displays computed gaps. |
| Block regular memo generation with unapproved Memo Studio work | Done | 2026-06-02 | Overview report generation now checks Memo Studio state and blocks regular investment-memo runs when meaningful unapproved analysis artifacts exist. |

### 11. API Surface

Planned endpoints:

```text
GET   /api/companies/{id}/memo-analysis
POST  /api/companies/{id}/memo-analysis/tools/{tool_name}/run
PATCH /api/companies/{id}/memo-analysis/artifacts/{artifact}
POST  /api/companies/{id}/memo-analysis/approve
POST  /api/reports  # accepts optional analysis_session_id for memo runs
```

| Item | Status | Completion Date | Notes |
|---|---|---|---|
| Add analysis session read endpoint | Done | 2026-06-02 | Added `GET /api/companies/{id}/memo-analysis`. |
| Add tool run endpoint | Done | 2026-06-03 | Added `POST /api/companies/{id}/memo-analysis/tools/{tool_name}/run`; deterministic tools return synchronously, while Claude-backed `strategic_risk_mapper` and `thesis_spine_builder` return `202` and run in the background. |
| Add artifact patch endpoint | Done | 2026-06-02 | Added `PATCH /api/companies/{id}/memo-analysis/artifacts/{artifact}` with focused tests for `thesis_spine`, `chart_specs`, and `narrative_hooks`. |
| Add research task patch endpoint | Done | 2026-06-03 | Added `PATCH /api/companies/{id}/memo-analysis/research-tasks/{task_id}` for task status/result updates. |
| Add research task run endpoint | Done | 2026-06-03 | Added `POST /api/companies/{id}/memo-analysis/research-tasks/{task_id}/run` for deterministic first-pass research summaries. |
| Add approval endpoint | Done | 2026-06-02 | Added `POST /api/companies/{id}/memo-analysis/approve`. |
| Update memo report creation to accept `analysis_session_id` | Done | 2026-06-02 | `POST /api/reports` and `/api/memos/prep` accept optional analysis session id, expose analysis-session metadata in report responses, and return 400 for unapproved analysis-backed runs. |
| Expose unapproved Memo Studio work warning | Done | 2026-06-02 | `GET /api/companies/{id}/memo-analysis` now returns `has_unapproved_work` and `regular_memo_warning` when draft analysis artifacts exist without memo approval. |
| Add active-job rail integration for long-running tools | Done | 2026-06-03 | Selected research-task runs and Claude-backed `strategic_risk_mapper` and `thesis_spine_builder` runs now appear in `/api/jobs/active` with log replay, SSE streaming, and Memo Studio route metadata. Future Claude-backed tools should reuse the same pattern. |
| Add stale-run recovery for interrupted background jobs | Done | 2026-06-03 | Session reads and `/api/jobs/active` now sweep Serena research-task and analysis-tool runs, mark stale `running` state as `error`, preserve completed artifacts/results, and append recovery errors to non-terminal progress logs. |

## Memo Readiness Gate

The UI should not treat memo generation as ready until the following are true
or explicitly waived:

| Gate | Status | Notes |
|---|---|---|
| Strategic risks generated | Done | Tracked by readiness gate. |
| Serena prioritized risks | Done | Tracked by readiness gate. |
| Thesis spine approved | In Progress | Approval exists; separate thesis-only approval state needs refinement. |
| 3-5 Investment Highlights drafted | Done | Tracked by readiness gate. |
| 3-5 Investment Risks drafted | Done | Tracked by readiness gate. |
| Top 3 gating questions selected | Done | Tracked by readiness gate. |
| Chart/table plan reviewed | Done | Tracked by readiness gate. |
| Benchmark dashboard reviewed | Done | Tracked by readiness gate. |
| Additional areas needed reviewed | In Progress | Gaps are displayed; explicit reviewed/waived state is future work. |
| Final memo generation approved | Done | Approval button sets `approved_for_memo`. |

## Additional Areas Needed

The dashboard should automatically surface gaps such as:

- missing revenue quality evidence
- no mature public comps selected
- unclear deployment depth
- missing disconfirming evidence
- weak or generic investment highlights
- weak or generic risks
- no valuation timing sanity check
- chart data incomplete
- thesis/risk mismatch
- intro not selected
- ending/recommendation not selected
- missing benchmark context
- missing BSH-specific gating questions

## Implementation Phases

| Phase | Status | Completion Date | Notes |
|---|---|---|---|
| Phase 1: storage, schemas, and API skeleton | Done | 2026-06-02 | YAML storage, API endpoints, and frontend API wrapper added. |
| Phase 2: Strategic Risk Mapper and Prompt Harness | Done | 2026-06-02 | Deterministic first versions added. |
| Phase 3: Thesis Spine, Chart Specs, Narrative Hooks | Done | 2026-06-02 | Deterministic first versions added. |
| Phase 4: UI Analysis Dashboard | Done | 2026-06-02 | Memo Studio tab and dashboard added. |
| Phase 5: research-folder memo ingestion | Done | 2026-06-02 | Memo runner now receives `data/research/<slug>/` and analysis packet dirs when present. |
| Phase 6: private benchmark dashboard | In Progress | 2026-06-02 | Scaffold added; metrics research remains future work. |
| Phase 7: memo grader and training loop | In Progress | 2026-06-02 | Grader scaffold added; completed-memo grading/training store remains future work. |
| Phase 8: final memo generation from approved analysis | Done | 2026-06-02 | Memo generation accepts approved analysis session ids and now enforces approved session plus approved thesis spine before prep side effects. |
| Phase 9: regular memo guardrails around draft analysis | Done | 2026-06-02 | Regular investment-memo generation now warns/blocks when Memo Studio has meaningful unapproved draft work. |
| Phase 10: selected research prompt runner | Done | 2026-06-03 | Added task run/status persistence and memo packet output for task results. Runs now enqueue Claude-backed background jobs with deterministic fallback. |
| Phase 11: selected prompt job rail integration | Done | 2026-06-03 | Added progress JSONL logs, `/api/jobs/active` discovery, log replay, SSE streaming, dashboard running-state polling, and regression coverage for Memo Studio research-task jobs. |
| Phase 12: Claude-backed strategic risk mapper | Done | 2026-06-03 | `strategic_risk_mapper` now uses a Claude-backed analysis-tool job, preserves previous good risk artifacts on Claude failure, writes deterministic fallback risks on first-run failure, and exposes progress through the AI Tasks rail. |
| Phase 13: Claude-backed thesis spine builder | Done | 2026-06-03 | `thesis_spine_builder` now uses a Claude-backed analysis-tool job, receives Memo Studio context, preserves previous good thesis artifacts on failure, writes deterministic fallback thesis output on first-run failure, refreshes the memo packet, and appears in the AI Tasks rail. |
| Phase 14: stale run recovery | Done | 2026-06-03 | Added shared recovery for interrupted Serena research-task and analysis-tool jobs using terminal/missing/idle progress-log detection and active-job timeout semantics. |

## Completion Log

Add entries here as work lands.

| Date | Item | Status Change | Notes |
|---|---|---|---|
| 2026-06-02 | Initial plan document | Created | Tracking document added. |
| 2026-06-02 | First Memo Studio implementation slice | In Progress → Done | Added durable Serena analysis sessions, deterministic tool runners, API endpoints, dashboard UI, memo prompt integration, and tests. |
| 2026-06-02 | Regular memo guard for unapproved drafts | Not Started → Done | Added derived API warning fields, frontend overview block, localized copy, and backend lifecycle coverage. |
| 2026-06-03 | Risk prioritization controls and task regeneration | In Progress → Done | Added manual risk up/down controls, selected-for-research checkboxes, priority normalization, selected-risk task regeneration, and regression coverage. |
| 2026-06-03 | Selected research prompt runner | Not Started → Done | Added task patch/run API endpoints, deterministic first-pass result summaries, task queue run controls, memo packet task-result output, and regression coverage that priority order remains unchanged. |
| 2026-06-03 | Claude-backed selected prompt jobs | In Progress → Done | Replaced inline task execution at the API boundary with background Claude research jobs, AI Tasks rail integration, durable logs, task polling, and deterministic fallback when Claude fails or is unavailable. |
| 2026-06-03 | Claude-backed strategic risk mapper | In Progress → Done | Added a streamed Claude risk-mapper job, analysis-tool active-job rail integration, schema normalization, previous-artifact preservation on failure, first-run deterministic fallback, UI polling for running tools, and regression coverage. |
| 2026-06-03 | Completion handoff | Created | Added `docs/serena-agent-completion-handoff.md` with the prioritized remaining work, next slice, implementation pattern, and exit checklist. |
| 2026-06-03 | Claude-backed thesis spine builder | In Progress → Done | Added a streamed Claude thesis-spine job, Memo Studio context handoff, schema normalization, previous-artifact preservation on failure, first-run deterministic fallback, memo-packet refresh, active-job coverage, and regression tests. |
| 2026-06-03 | Stale Serena job recovery | Not Started → Done | Added shared recovery for interrupted `running` research tasks and analysis tools, active-job rail sweep integration, preserved prior artifacts/results, recovery progress events, and regression tests. |
