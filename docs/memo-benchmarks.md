# Memo pipeline benchmarks

Live-run comparisons of memo-pipeline variants. Full pipeline anatomy and
the reasoning behind the variants: `docs/memo-pipeline-anatomy.html`.

## Protocol

- Company: **nvda** (rich registry entry; prior runs on record make
  results comparable).
- One variant per run. Set the flags in `.env`, **restart the server**
  (`run.sh` sources `.env` at startup), then trigger an
  "Investment Memo (Late-Stage)" run from the UI.
- Afterwards extract the numbers:

  ```sh
  uv run python scripts/memo_phase_report.py data/memos/nvda/<run_dir>
  ```

- Paste the table below with the flag matrix, and record a decision.
- A live run costs roughly $15–30 and 30–45 minutes. Do not run
  variants casually.

## Round 1 — spine-lite and Chinese chasing (2026-08)

Held constant across B and C: `BSH_MEMO_MODEL_TRANSLATION=claude-sonnet-5`
(translation units on Sonnet). Baseline A predates spine-lite and
tiering — the chasing decision is strictly C vs B; A anchors the overall
"was this worth it" comparison.

| Run | Flags | Phase 2 | Phase 3 (attempts) | Phase 4 | Total | Cost | Quality |
|---|---|---|---|---|---|---|---|
| A. Monolith baseline | defaults | 10.8 m | 25.1 m (1) | 7.8 m | 43.7 m | $23.07 | lint passed, P0=0 |
| B. Spine-lite | `BSH_MEMO_ENGLISH_PARALLEL=1` | _pending_ | | | | | |
| C. Spine-lite + chasing | B + `BSH_MEMO_ZH_CHASING=1` | _pending_ | | | | | |

Baseline A source: `data/memos/nvda/2026-08-25__003251__nvda__memo-run`.

### Decision gates

- Spine-lite call itself ≤ ~4 min (the old spine took ~9).
- `cache_read_input_tokens` ≥ ~6K on every post-spine Phase-3 call
  (proves the shared `--append-system-prompt` context is cache-hitting).
- B beats A on wall-clock at equal attempts, with no new lint P0s and no
  extra parity warnings.
- C beats B by ≥ 3 min, chase adoption ≥ 70%
  (`strings_adopted / strings chased`), and C's Phase-4 cost
  (chase + gap-fill) ≤ B's Phase-4 cost + $1.
- Judge **cost per completed run**, not per call — a variant that retries
  less can cost more per attempt and still win.

### Decision log

- _pending benchmark runs B and C._
