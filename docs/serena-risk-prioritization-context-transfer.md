# Serena Risk Prioritization Context Handoff

Last updated: 2026-06-03

This note records the risk-prioritization slice after implementation. It is no
longer the next task. The old target behavior has shipped.

## Status

Done.

Serena can now:

1. See strategic risks sorted by current priority rank.
2. Move a risk up or down.
3. Toggle whether a risk is selected for research.
4. Save priority changes.
5. See `research_tasks` regenerate from selected risks in priority order.

## Operating Constraints

- Work directly on `main`.
- Do not create worktrees or feature branches.
- Keep `data/uploads/<slug>/` excluded from memo analysis.
- Serena's memo/background research folder remains `data/research/<slug>/`.
- Update `docs/serena-agent-analysis-tools.md` as future slices ship.

## Files Changed For This Slice

- `server/serena_analysis.py`
  - Added priority normalization helpers.
  - Added `risk_priorities`-specific PATCH behavior.
  - Changed `priority_prompt_harness` to generate tasks from selected risks.
- `frontend/src/components/MemoAnalysisDashboard.vue`
  - Added `riskPriorityDraft`.
  - Added sorted risk rendering.
  - Added compact up/down controls.
  - Added selected-for-research checkboxes.
  - Added "Save priorities".
- `tests/test_serena_analysis.py`
  - Added API coverage for reordering, selected flags, task regeneration,
    persisted priority/task state, and the no-selected-risks empty queue case.
- `docs/serena-agent-analysis-tools.md`
  - Marked risk-priority task regeneration and prioritized board controls done.

## Backend Contract

`risk_priorities` remains:

```yaml
updated_at: "..."
priorities:
  - risk_id: risk-1
    rank: 1
    selected: true
    rationale: Default priority based on decision impact and memo centrality.
```

`research_tasks` remains:

```yaml
updated_at: "..."
tasks:
  - id: task-1
    risk_id: risk-1
    title: "Research: <risk title>"
    priority: high
    status: not_started
    source_type: "..."
    prompt: "..."
    result_summary: null
```

Implemented behavior:

- Ranks normalize to contiguous `1..n` on every `risk_priorities` save.
- `rationale` is preserved when provided.
- Missing `selected` is treated as `False` outside initial harness defaults.
- Every known risk is included in `risk_priorities.priorities`.
- Missing known risks are appended after provided priorities.
- `research_tasks` are regenerated from selected risks sorted by rank.
- If no risks are selected, `research_tasks.tasks` is an empty list.
- `_research_tasks(company, risks)` remains deterministic.

## Frontend Contract

The Strategic Risk Board:

- sorts by priority rank;
- shows rank numbers;
- uses lucide up/down icons for rank movement;
- uses checkboxes for selected-for-research state;
- saves through `api.memoAnalysis.patchArtifact`;
- disables saves while another artifact save is in progress;
- refreshes from the returned session after save.

If `risk_priorities` does not exist, the board still shows known risks in
source order with `selected: false`; saving creates a normalized priorities
artifact.

## Verification

Passed after this slice:

```bash
PYTHONPATH=. pytest -q tests/test_serena_analysis.py
PYTHONPATH=. pytest -q
npm test
npm run build
PYTHONPATH=. python -m py_compile server/serena_analysis.py server/api.py
```

Browser smoke:

```text
http://127.0.0.1:8010/research/research/amd?tab=analysis
```

Confirmed the risk board rendered with up/down controls, selected-for-research
checkboxes, and a save button. A local draft move/toggle interaction worked.

## Remaining Work Related To Risk Tasks

Risk prioritization itself is complete, but generated tasks still need an
execution workflow:

1. Add task status/result editing or patching for `research_tasks`.
2. Add UI controls to run or mark selected research tasks.
3. Wire selected tasks into Console or background jobs.
4. Persist task result summaries.
5. Feed completed task results into `memo_packet.md` and future thesis updates.
