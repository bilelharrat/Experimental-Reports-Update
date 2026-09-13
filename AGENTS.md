# BSH Research Center — workflow

> Keep this file and CLAUDE.md in sync: they are the same workflow doc for
> different agents and differ ONLY in the agent name on the branch-prefix
> and commit-trailer lines. Edit both when you change either.

## Verifying changes

Run these before declaring any change done:

```sh
uv run python -m pytest              # backend (~4 min, 500 tests, no network/LLM calls)
npm --prefix frontend test           # frontend unit (vitest, ~10s)
npm --prefix frontend run lint       # eslint gate (CI enforces --max-warnings=0)
uv run ruff check server scripts tests
```

Targeted runs are fine while iterating (`uv run python -m pytest
tests/test_weekly_stocks.py`); run the relevant suite in full before
finishing. `scripts/quality.sh` is the complete CI-equivalent gate
(includes the frontend build and Playwright browser smoke). Tests marked
`e2e` spawn a real Claude CLI and cost money — they are deselected by
default; never run them casually.

Architecture orientation (which module owns what, memo pipeline stages,
what "Serena" and "Hormuz" are) lives in `docs/architecture.md`. Env vars
are documented in `.env.example`.

The memo agents' editorial prompts (voice contract, structure profiles,
risk cards, Phase 2 pass focus texts, company-type lenses) are files under
`skills/memo/`, with Chinese twins under `skills/memo/zh/` that the
founder's team edits — see `skills/memo/README.md`. Edit the files, never
the `memo_prompts.load_prompt(...)` lines; after porting a zh edit into
English run `uv run python scripts/skills_sync.py --stamp`.

## Branching

**All work happens directly on `main`.** No worktree branches, no feature
branches, no `Codex/*` ephemeral branches. The user runs the dev server
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
  the `Co-Authored-By: Codex …` trailer.
- Push to `origin/main` when the user asks to submit / push / ship.
- Never push to a branch other than `main`.
