# BSH Research Center — workflow

## Branching

**All work happens directly on `main`.** No worktree branches, no feature
branches, no `claude/*` ephemeral branches. The user runs the dev server
from `main` and edits made anywhere else don't take effect.

This rule exists because past sessions left stale worktrees (`epic-cohen`,
`trusting-snyder`, etc.) holding uncommitted experiments on top of
older-than-main snapshots. Those experiments were eventually discarded
because re-merging them would have reverted improvements already on main.

Concrete rules for future sessions:

- Do not create git worktrees. If a task wants isolation, just work on
  main and commit as you go — main is the source of truth.
- Do not spawn agents with `isolation: "worktree"`. Use the in-place
  workspace.
- If you find yourself in a worktree (e.g. a previous session left one),
  port the edits to the main checkout, commit there, and remove the
  worktree before finishing the session.

## Commits and pushes

- Commit when the user asks ("commit", "ship it", "submit it"). Sign with
  the `Co-Authored-By: Claude …` trailer.
- Push to `origin/main` when the user asks to submit / push / ship.
- Never push to a branch other than `main`.
