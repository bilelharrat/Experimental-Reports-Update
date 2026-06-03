# Serena Agent Memo Studio Context Handoff

Last updated: 2026-06-03

This is the current handoff note for continuing Serena's memo-agent work in a
fresh context. It replaces older notes that listed risk prioritization as the
next slice or deterministic selected-prompt execution as the next slice; both
are now implemented.

## Operating Rules

- Work directly on `main`.
- Do not create feature branches or worktrees.
- Keep `data/uploads/<slug>/` excluded from memo analysis.
- Serena's memo/background research folder is `data/research/<slug>/`.
- Track shipped work in `docs/serena-agent-analysis-tools.md`.
- If the dev server is already running, use it rather than starting a second
  process on the same port.

## Current Repo State

The Memo Studio implementation is present in the main checkout, but several
Serena files are still untracked in git. Do not delete or recreate them.

New/untracked Serena files include:

- `docs/serena-agent-analysis-tools.md`
- `docs/serena-agent-handoff.md`
- `docs/serena-risk-prioritization-context-transfer.md`
- `frontend/src/components/MemoAnalysisDashboard.vue`
- `server/serena_analysis.py`
- `tests/test_serena_analysis.py`

Modified tracked files include:

- `frontend/src/api.js`
- `frontend/src/components/ActiveJobsRail.vue`
- `frontend/src/i18n.js`
- `frontend/src/views/ResearchView.vue`
- `server/api.py`
- `server/claude_runner.py`
- `server/memo_analysis.py`
- `server/memo_prep.py`

## Progress Completed

### Analysis Sessions

`server/serena_analysis.py` owns durable YAML-backed analysis sessions under:

```text
data/serena_analysis/<company_slug>/<session_id>/
```

Implemented artifacts:

- `input_manifest.yaml`
- `strategic_risks.yaml`
- `risk_priorities.yaml`
- `research_tasks.yaml`
- `thesis_spine.yaml`
- `chart_specs.yaml`
- `narrative_hooks.yaml`
- `benchmark_dashboard.yaml`
- `memo_packet.md`

Implemented first-pass tools:

- `strategic_risk_mapper`
- `priority_prompt_harness`
- `thesis_spine_builder`
- `chart_spec_builder`
- `narrative_hooks`
- `private_benchmark_dashboard`
- `memo_grader`
- `readiness_check`

### API And Memo Handoff

Implemented API routes:

```text
GET   /api/companies/{company_id}/memo-analysis
POST  /api/companies/{company_id}/memo-analysis/tools/{tool_name}/run
PATCH /api/companies/{company_id}/memo-analysis/artifacts/{artifact_name}
PATCH /api/companies/{company_id}/memo-analysis/research-tasks/{task_id}
POST  /api/companies/{company_id}/memo-analysis/research-tasks/{task_id}/run
POST  /api/companies/{company_id}/memo-analysis/approve
```

Memo generation now accepts `analysis_session_id` and is blocked unless the
analysis session is approved and the thesis spine is approved. The memo runner
adds the analysis-session folder and `data/research/<slug>/` to Claude's
available directories while still explicitly forbidding `data/uploads/<slug>/`.

Regular investment-memo generation from the Overview tab now checks for
meaningful unapproved Memo Studio work and blocks with a review prompt.

### Memo Studio UI

`frontend/src/components/MemoAnalysisDashboard.vue` is wired into the Research
view's Memo Studio tab. It currently supports:

- readiness gate
- tool launcher and tool run history
- additional areas needed
- strategic risk board
- risk priority up/down controls
- selected-for-research checkboxes
- save priority changes
- editable thesis highlights, risks, and gating questions
- research task queue
- per-task background run controls
- task status and result summary display
- chart/table include-exclude toggles
- narrative hook selection
- benchmark dashboard display
- analysis approval
- generate memo from approved analysis

### Risk Prioritization Slice

The risk-prioritization slice from
`docs/serena-risk-prioritization-context-transfer.md` is complete.

Backend behavior now:

- `priority_prompt_harness` creates default priorities and generates tasks from
  selected risks, not `risks[:5]`.
- `PATCH risk_priorities` normalizes rank order to contiguous `1..n`.
- Missing known risks are appended to `risk_priorities.priorities`.
- Missing `selected` values are treated as false outside initial defaults.
- Research tasks regenerate from selected risks in priority order.
- If no risks are selected, `research_tasks.tasks` becomes an empty list.
- Existing generic artifact patch behavior remains intact for thesis, charts,
  and narrative hooks.

Frontend behavior now:

- Strategic risks sort by current priority rank.
- Serena can move risks up/down with compact lucide icon buttons.
- Serena can toggle selected-for-research checkboxes.
- Saving calls the existing artifact PATCH endpoint.
- The returned session refreshes the research task queue.

### Selected Research Prompt Runner Slice

The selected research prompt runner is now a background job flow. It keeps the
deterministic local result as fallback behavior when Claude is unavailable or
fails before producing a usable result.

Backend behavior now:

- `PATCH /memo-analysis/research-tasks/{task_id}` updates task status,
  result summary, error, and basic timestamps.
- `POST /memo-analysis/research-tasks/{task_id}/run` returns `202`, marks the
  task `running`, and starts a background Claude Code research job.
- Task jobs write JSONL progress under the analysis session's `logs/` folder,
  appear in `/api/jobs/active`, replay through `/api/jobs/log`, and expose an
  SSE stream for the generic job transcript modal.
- Claude-backed task results persist `result_summary`, `result_payload`,
  `result_basis`, timestamps, and `result_generated_by: claude_code`.
- If Claude fails and the task has no previous good result, the worker writes a
  deterministic fallback summary with the Claude error preserved.
- If Claude fails and the task already has a result, the worker preserves that
  previous result and marks the latest run `error`.
- Task results are preserved by `risk_id` when `research_tasks` is refreshed
  after priority changes.
- Completed task summaries are included in `memo_packet.md` under
  `Research Task Results`.
- Task result persistence does not reorder `risk_priorities`.

Frontend behavior now:

- Each research task row has a compact run button.
- The queue displays task priority, status, prompt, result summary, timestamp,
  and any persisted error.
- Running a task refreshes the session into `running` state and the dashboard
  polls the session while tasks are active.
- Detailed progress uses the existing AI Tasks rail and job transcript modal.

## Verification Already Run

All of these passed after the selected research prompt background-job slice:

```bash
PYTHONPATH=. pytest -q tests/test_serena_analysis.py
PYTHONPATH=. pytest -q
npm test
npm run build
PYTHONPATH=. python -m py_compile server/serena_analysis.py server/api.py server/claude_runner.py
git diff --check
```

Latest observed results:

- `tests/test_serena_analysis.py`: 13 passed, 2 warnings.
- Full backend suite: 165 passed, 2 deselected, 2 warnings.
- Frontend suite: 7 test files passed, 56 tests passed.
- Frontend production build completed successfully.
- `PYTHONPATH=. python -m py_compile server/serena_analysis.py server/api.py server/claude_runner.py`
  passed.
- `git diff --check` passed.
- In-app browser smoke on the existing
  `http://127.0.0.1:8010/research/research/amd?tab=analysis` showed that the
  running server was stale and returned 404 for the Memo Studio API.
- A temporary current-checkout server on
  `http://127.0.0.1:8011/research/research/amd?tab=analysis` loaded the Memo
  Studio API/page successfully and was shut down afterward. No UI prompt run
  was clicked because the available local AMD session had no generated
  research tasks and running the prompt harness would have mutated local data.

## Outstanding Work

### Highest Priority

1. Replace deterministic analysis tools with Claude-backed implementations.
   - Start with `strategic_risk_mapper`.
   - Keep deterministic output as test/fallback behavior.
   - Preserve existing artifact schemas.
   - Persist tool errors without corrupting previous good artifacts.

2. Add active-job rail integration for long-running analysis tools.
   - Current state: selected research-task runs use background jobs and the AI
     Tasks rail; `/memo-analysis/tools/{tool}/run` remains synchronous.
   - Keep deterministic tools synchronous until a Claude-backed tool needs a
     job.
   - Reuse existing `/api/jobs/active` conventions.

3. Add cancellation or stale-run recovery for Memo Studio research task jobs.
   - Current state: task jobs stream progress and preserve previous good
     results on Claude failure, but there is no cancel endpoint and no startup
     sweep to mark interrupted `running` tasks as `error`.

### Medium Priority

4. Add explicit review/waive state for additional areas needed.
   - Current state: gaps are computed and displayed, but cannot be reviewed or
     waived.
   - Likely artifact: `readiness_reviews` or `waivers`.

5. Add benchmark row editing and richer benchmark metrics.
   - Current state: benchmark rows are read-only scaffolds with nullable
     metrics.
   - Add editable public comp rows before replacing the scaffold with richer
     public-market research.

6. Build completed-memo grader and training loop.
   - Current state: `memo_grader` writes a waiting scaffold.
   - Future state: select a completed memo, grade it, persist feedback under
     `data/serena_training/<company_slug>/`, and update distilled lessons.

### Lower Priority / Cleanup

7. Add artifact version history or audit trail beyond current timestamps and
   tool-run metadata.
8. Refine thesis-only approval state; current approval path marks thesis
   approved when analysis is approved.
9. Split `MemoAnalysisDashboard.vue` into smaller components if it becomes hard
   to maintain.
10. Add dedicated prompt-construction tests beyond the current end-to-end
    Serena analysis tests.

## Recommended Next Slice

Implement "Claude-backed research task jobs" as the next slice:

1. Keep the existing deterministic runner as fallback/test behavior.
2. Add a job-backed execution path for research tasks, likely starting with one
   selected task at a time.
3. Reuse existing `/api/jobs/active` and job log conventions so long-running
   work appears in the active jobs rail.
4. Persist task status transitions (`not_started` -> `running` -> `done` or
   `error`) without deleting the previous good `result_summary`.
5. Update `memo_packet.md` after task completion.
6. Add API tests that job enqueue/result persistence preserves priority order
   and previous good task output on failure.

After that contract exists, start replacing deterministic analysis tools with
Claude-backed implementations. `strategic_risk_mapper` is still the best first
analysis-tool candidate.

## Important Design Intent

The memo template should no longer be the source of insight. The approved
analysis packet should be the source of insight:

- strategic risks
- priority order
- selected research tasks and results
- thesis spine
- chart plan
- narrative hooks
- benchmark context
- missing areas / gates

The final memo skill should package that judgment into the BSH memo structure.
