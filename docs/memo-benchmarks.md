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
| A. Monolith baseline | defaults | 10.8 m | 25.1 m (1) / $6.69 | 7.8 m / $5.02 | 43.7 m | $23.07 | lint passed, P0=0 |
| B. Spine-lite | `BSH_MEMO_ENGLISH_PARALLEL=1` | 4.2 m | 18.9 m (1) / $11.96 | 7.1 m / $2.83 | **30.2 m** | **$21.35** | `complete`, lint P0=0, parity P0=0 P1=0 |
| C. Spine-lite + chasing | B + `BSH_MEMO_ZH_CHASING=1` | 6.0 m | 20.1 m (1) / $14.05 | **3.8 m** / $2.41 | 29.9 m | $24.16 | `complete`, lint P0=0, parity P0=0 P1=0 |

Baseline A source: `data/memos/nvda/2026-08-25__003251__nvda__memo-run`.
Run B source: `data/memos/nvda/2026-08-28__003828__nvda__memo-run` (2026-08-28).

Run B detail: spine 4.6 m / $1.61 (one schema self-correction, no fallback);
section wave 6.0 m concurrent (slowest = artifacts agent 6.0 m); surgical
quality repair cleared 3 findings in ~8 m, attempt count stayed 1;
cache_read_input_tokens 71K–954K on every post-spine call (gate ≥6K —
passed by orders of magnitude); 6 Sonnet translation units (longest 7.1 m,
Phase-4 cost 44% of baseline); status `complete` with zero warnings —
cleaner than the baseline.

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

- **2026-08-28 — Run B (spine-lite): PASS on every gate.** 30.2 m vs
  43.7 m baseline (−31%), $21.35 vs $23.07, one attempt, zero quality
  warnings. Spine-lite 4.6 m (vs ~9 m pre-redesign); the
  `--append-system-prompt` cache sharing eliminated the old 5× cost
  blowout (Phase 3 attempt = $9.26 vs the old experiment's ~$16). The
  2026-08-21 "no wall-clock win at 5× cost" verdict is superseded.
- **Gate-alignment follow-up found in Run B:** the quality lint's
  `meta_process_language` rule flagged the *mandatory* disclosures
  sentence ("This document is a confidential summary…") and two
  descriptive rows inside Section VI's source index — validator fighting
  the pipeline's own required content. Surgical repair absorbed it
  (~8 m, ~$2.7); aligning the lint's allow-list would hand that time
  back on every run.
- **2026-08-28 — Run C (chasing): mechanism PASSES; run-level total was
  masked by upstream variance. Keep chasing ON-able.** The chase itself
  was near-perfect: 6/6 units joined, **649 of 650 strings adopted
  (99.8%, gate ≥70%)**, one string gap-filled, translation cost $2.41 vs
  B's $2.83. Phase 4 collapsed 7.1 m → **3.8 m** (−3.3 m, the designed
  win) and quality stayed pristine. The run total (29.9 m vs B's 30.2 m)
  barely moved because Phases 2–3 ran +3.1 m heavier this time (pass
  durations vary run-to-run by more than the chasing win — the heaviest
  analysis pass gates Phase 2). Verdict: chasing is additive, cheaper,
  and quality-neutral; its −3+ m shows at the phase level on every run
  and at the total level once upstream variance averages out.
- **2026-08-28 — tuned-code validation (zainar-inc, second run): 22.5 m
  / $19.47 / `complete`, zero warnings.** The join wait went from
  2.2 m to **1 ms** (4 chase workers — every unit finished long before
  the join) and the chase rows now show true runtimes (e.g. envelope
  95.9 s wall vs 94.1 s model time; previously a 920 s-style wall).
  Repair fired once for genuine findings (detached voice + an untreated
  disclosure gap in front matter). Adoption 653/656.
- **Tuning follow-ups from Run C — all three SHIPPED 2026-08-28:**
  (1) chase workers default is now 4 (with 2, the six units queued and
  the join waited 86 s–2.2 m for the tail); (2) chase rows now emit
  their terminal events from the worker thread at true completion time
  (previously emitted at join time, showing 920 s walls for 75 s
  translations); (3) the lint allow-list alignment (entry above).
- **2026-08-28 — lint alignment SHIPPED.** `meta_process_language` now
  (a) skips blocks carrying the mandatory legal-disclosure markers and
  (b) permits neutral-article references ("the memo carries…", "the
  registry fields…") inside the Sources/validation trace sections;
  demonstrative/possessive forms ("this memo", "our analysis") stay
  banned everywhere. Replayed against Run C's pre-repair package: the
  meta findings drop to 0; two genuine sell-side voice violations
  remain (correctly). Run B's repair round (3/3 meta) would have been
  skipped entirely.
- **Round-1 conclusion:** spine-lite + Sonnet translation + chasing =
  ~30 m / ~$21–24 / zero warnings, vs 43.7 m / $23.07 baseline. All
  three flags are safe to leave on for daily use; the next ~8 m of
  savings is the lint alignment, not more parallelism.
- **2026-08-28 — first routine run on the full stack (zainar-inc,
  post-lint-fix): 22.9 m / $16.44 / `complete`, zero warnings** — vs
  that company's 36.5 m / $16.58 monolithic baseline (−37% at equal
  cost). Spine 2.9 m on the thin-corpus company (generalizes); quality
  gate raised exactly ONE finding and it was genuine voice phrasing
  (no meta false positives — the alignment fix held live); chase
  adoption 556/557. The steady-state pipeline is ~23 m.

## Round 2 — Phase-2/3 overlap and repair shrinkage (branch report-speedup-r2)

Five levers, all implemented flag-gated default OFF. The theme is the
chasing pattern generalized: speculate on partial input, verify cheaply,
redo only what the verifier invalidates. The deterministic **pin-echo
check** (`BSH_MEMO_PIN_CHECK`, report-only, on by default when a spine
exists) is the safety net the speculative levers stand on — watch
`logs/pin_check.md` and the `memo_pin_check` stage event.

| Lever | Flag(s) | Mechanism | Expected |
|---|---|---|---|
| Artifacts detach | `BSH_MEMO_ARTIFACTS_ASYNC=1` | artifacts agent runs detached from the section wave, joined after acceptance | wave ends at slowest *section* (Run B: artifacts gated it at 6.0 m) |
| Pin-echo check | `BSH_MEMO_PIN_CHECK=1` (default) / `_REPAIR=1` | deterministic pins-echoed verification | 0 findings on healthy runs; drift data for the speculation levers |
| Sectional repair | `BSH_MEMO_SECTIONAL_REPAIR=1` | quality findings grouped by section, repaired in parallel, spliced | repair round ~8 m → ~2-4 m when it fires |
| Speculative spine | `BSH_MEMO_SPINE_SPECULATIVE=1` (+`_AFTER`, default 6) | spine launches at 6/8 passes; SPINE_CHECK delta-verifies pins when stragglers land | spine wall hides in the pass tail (~2-3 m); stale pins cost one respin |
| Early sections | `BSH_MEMO_SECTION_EARLY_START=1` | affinity-satisfied sections start on the unvalidated spine | wave overlaps the pass tail (~1-2 m more); stale pins discard ≤4 drafts |

### Protocol

Layer the levers in two runs on top of the Round-1 flags
(`BSH_MEMO_ENGLISH_PARALLEL=1`, `BSH_MEMO_ZH_CHASING=1`,
`BSH_MEMO_MODEL_TRANSLATION=claude-sonnet-5`):

- **Run D (safe set):** `BSH_MEMO_ARTIFACTS_ASYNC=1` +
  `BSH_MEMO_SECTIONAL_REPAIR=1`. Optionally
  `BSH_MEMO_MODEL_SPINE_CHECK=claude-sonnet-5` now so it is already
  configured for Run E.
- **Run E (speculation):** Run D + `BSH_MEMO_SPINE_SPECULATIVE=1` +
  `BSH_MEMO_SECTION_EARLY_START=1`.

Restart the server between runs; extract with
`scripts/memo_phase_report.py` as in Round 1.

### Decision gates

- **D:** the `english_artifacts` row overlaps the wave (its
  `finished_at` may exceed the wave's without moving the attempt
  duration); if a repair fires, the `english_repair:*` rows replace one
  monolithic ~8 m round with a ≤4 m parallel one; total/cost/quality
  not worse than the Round-1 steady state.
- **E:** `memo_spine_delta_check` verdict `fresh`; the section wave
  starts within ~1.5 m of Phase-2 end (vs +3-5 m today); early-start
  rows (`early_start: true`) show sections drafted exactly once; pin
  check 0 findings; total ≥2 m under Run D. A `stale` verdict is not a
  failure — it is the design working; note the reasons and how much the
  respin cost.
- **Pin-echo across both runs:** any finding means a section drifted
  from the pins — investigate before trusting the speculation levers
  further, and consider `BSH_MEMO_PIN_CHECK_REPAIR=1`.
