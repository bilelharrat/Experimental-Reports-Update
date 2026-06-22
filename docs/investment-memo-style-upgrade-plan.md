# Investment Memo Style Upgrade Plan

## Current Phase

Phase 6 - Implementation re-verification complete for human executive memo style upgrade.

## Scope

Upgrade the investment memo prompt stack so final memo prose reads like a senior BSH investment partner's IC memo, while preserving the current falsification-first diligence process and required DOCX outputs.

## Target Files

- `server/claude_runner.py` - add and inject a Human Executive Memo Voice Contract into the investment memo prompt.
- `server/skills/bsh_investment_memo_latestage.md` - sharpen final-writing instructions, section prose behavior, and final QA.
- `server/serena_analysis.py` - mark the Serena memo packet as source material, not final prose.
- `frontend/src/components/memo/MemoNarrativeHooksPanel.vue` - present narrative hook selections as intro, risk, and conclusion choices.
- `tests/test_memo_prep.py` and/or `tests/test_serena_analysis.py` - add focused prompt/packet construction checks if existing patterns fit.
- `docs/investment-memo-style-upgrade-plan.md` - durable progress record.

## Phase Checklist

- [x] Read user request and AGENTS.md.
- [x] Read `investment_memo_human_exec_spec.md`.
- [x] Read `docs/memo-pipeline.md`.
- [x] Inspect `server/claude_runner.py`, `server/skills/bsh_investment_memo_latestage.md`, and `server/serena_analysis.py`.
- [x] Extract style regression examples from the ZaiNar DOCX.
- [x] Add prompt-level Human Executive Memo Voice Contract.
- [x] Update memo skill final-writing and QA instructions.
- [x] Add packet-level source-material guidance.
- [x] Add or update tests.
- [x] Run relevant tests or lightweight prompt-construction checks.
- [x] Sharpen memo tools for source-backed intro, risk-section, and conclusion content.
- [x] Present operator choices as intro stance, risk-section posture, and conclusion posture.
- [x] Re-read the human executive spec, ZaiNar sample, memo pipeline docs, prompt wrapper, memo skill, and Serena packet handoff.
- [x] Verify existing implementation includes prompt-level voice contract, banned phrase rewrite guidance, source-material packet guidance, section-level prose rules, and final prose QA.
- [x] Re-run focused memo prompt and Serena packet tests.

## Tone Principles

- Write like a senior BSH investment partner making a decision under uncertainty.
- Convert diligence evidence into judgment; do not narrate the diligence process.
- Keep private analysis artifacts private.
- State uncertainty directly without methodology apology.
- Avoid visible template language, balanced-but-mechanical phrasing, and model-like scaffolding.
- Preserve rigor: missing evidence should still reduce conviction and produce gating questions.

## Banned Phrase / Rewrite Table

| Avoid | Prefer |
|---|---|
| The investment case is not that... | This is not a conventional SaaS case. |
| The memo therefore... | Remove, or rewrite as direct judgment. |
| The analysis suggests... | State the conclusion directly. |
| Due to lack of data... | Revenue is not disclosed. |
| implies false precision | would be misleading to forecast precisely |
| not treated as ARR | not revenue-recognized |
| commercial momentum is material, but... | The pipeline is large but not contractually binding. |
| The principal risk is that... | Key risk centers on... |

## Decisions Made

- Work directly on `main`; do not create branches or worktrees.
- Do not touch unrelated dirty files already present in the worktree.
- Use a prompt wrapper contract plus skill-level instructions. The wrapper acts as an override close to the prompt boundary, while the skill update gives the subprocess concrete final-writing behavior.
- Add focused tests using the existing memo prompt and Serena analysis test files.

## Progress Notes

- The current pipeline is `POST /api/reports` -> `memo_prep.bootstrap_memo_run` -> `memo_analysis._run` -> `claude_runner.run_investment_memo` -> `_build_investment_memo_prompt` -> `server/skills/bsh_investment_memo_latestage.md`.
- Existing skill is rigorous, but it emphasizes validation artifacts and table structure enough that internal scaffolding can leak into final body prose.
- Existing tests already cover `_build_investment_memo_prompt` and `_refresh_memo_packet`, so new checks should be narrow.
- Worktree has unrelated modified and untracked files; this task should not revert or normalize them.
- ZaiNar sample contains the target regression phrases: "The investment case is not that...", "The memo therefore...", "would imply false precision", "not treated as ARR", and "Commercial momentum is material, but not treated as backlog."
- Added `HUMAN_EXEC_MEMO_VOICE_CONTRACT` to `server/claude_runner.py` and inject it before the verbatim skill text.
- Updated `server/skills/bsh_investment_memo_latestage.md` with a Human Executive Memo Voice Contract, section-specific prose rules, and a final prose QA gate.
- Updated `server/serena_analysis.py` so `memo_packet.md` explicitly says to use the packet as source material, not prose.
- Added focused assertions in `tests/test_memo_prep.py` and `tests/test_serena_analysis.py`.
- Updated the Claude-backed memo tools so the source brief, thesis spine, risk mapper, and narrative hook prompts ask for source-backed intro stance, risk posture, and conclusion posture rather than generic report prose.
- Improved deterministic fallbacks so narrative hooks produce operator-selectable intro, risk framing, and conclusion choices even without Claude.
- Updated `memo_packet.md` generation to label selected choices as operator narrative guidance.
- Relabeled the memo UI choice panel to "Intro, Risk, Conclusion Choices".
- Re-verification found the requested memo style upgrade already present in the active `main` checkout: `HUMAN_EXEC_MEMO_VOICE_CONTRACT` is injected before the skill text, the skill has partner-level final-writing and QA rules, and the Serena memo packet warns that analysis artifacts are source material rather than prose.

## Open Questions

- None blocking. The implementation can proceed from the provided spec and sample memo.

## Tests Run

- `python -m pytest tests/test_memo_prep.py tests/test_serena_analysis.py -q`
  - First run: 55 passed, 1 failed. The failure was a brittle line-wrap assertion in the new prompt-contract test.
  - Second run after assertion fix: 56 passed, 2 warnings. Warnings are existing FastAPI `on_event` deprecations.
- `python -m pytest tests/test_memo_prep.py tests/test_serena_analysis.py -q`
  - HIL/tool sharpening run: 57 passed, 2 warnings. Warnings are existing FastAPI `on_event` deprecations.
- `python -m pytest tests/test_memo_prep.py tests/test_serena_analysis.py -q`
  - Phase 6 verification run: 57 passed, 2 warnings. Warnings are existing FastAPI `on_event` deprecations.

## Remaining Work

- No code changes remain for this prompt/style upgrade verification.
- A fresh end-to-end memo generation run remains the best style regression check, because the change affects downstream Claude-authored prose and operator choice behavior.

## Before / After Examples

| Before | After |
|---|---|
| The investment case is not that ZaiNar is a conventional software company priced on current ARR. | This is not a conventional SaaS case. |
| Current revenue is too early and not disclosed, and a precise financial forecast would imply false precision. | Revenue is not disclosed, and a precise forecast would be misleading. |
| The memo therefore treats the case as infrastructure scarcity. | The bet is infrastructure scarcity. |
| Commercial momentum is material, but not treated as backlog. | The pipeline is large but not contractually binding. |
| LOI economics are not treated as ARR until site-level binding contracts are disclosed. | LOI economics are not revenue-recognized until site-level binding contracts are disclosed. |
