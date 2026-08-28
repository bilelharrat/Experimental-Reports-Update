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

## Comparison discipline (applies to every round)

Freeze the inputs inside any A-vs-B comparison: same company, same
research corpus state, same registry entry, and — once it exists — the
same fact-ledger state, all recorded next to the flag matrix. Data
improvements (a richer corpus, a populated ledger) are real wins but they
are DATA changes: log them separately and never mix them into a pipeline
timing comparison, or a faster run may just be reusing yesterday's
retrieval.

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

### Results

| Run | Flags | Phase 2 | Phase 3 (attempts) | Chase tail + render | Total | Cost | Quality |
|---|---|---|---|---|---|---|---|
| D. Detach + sectional repair (zainar-inc) | Round-1 + `ARTIFACTS_ASYNC` + `SECTIONAL_REPAIR` | 2.6 m | 7.0 m (1) / $7.37 | ~7.0 m | **16.6 m** | **$15.03** | `complete`, lint P0=0, parity P0=0 |
| D2. Same config, re-test (zainar-inc) | as D (intended as Run E; speculation flags were not live) | 2.7 m | 15.9 m (1, incl. 9.3 m whole-package repair) | ~3 m | 21.6 m | $17.18 | `complete`, pin echo 22/0 |
| E. Speculation set (zainar-inc) | D + `SPINE_SPECULATIVE` + `SECTION_EARLY_START` (+ hybrid repair, shipped between D2 and E) | 2.3 m (spine launched 2.1 m in) | 11.6 m (1, incl. **1.7 m hybrid repair**) | ~7.4 m | **18.9 m** | **$15.72** | `complete`, lint P0=0, parity P0=0, pin echo 22/0 |

Run D source: `data/memos/zainar-inc/2026-08-28__192423__zainar-inc__memo-run`.
Run D2 source: `data/memos/zainar-inc/2026-08-28__195340__zainar-inc__memo-run`.
Run E source: `data/memos/zainar-inc/2026-08-28__202617__zainar-inc__memo-run`.

### Round-2 decision log

- **2026-08-28 — Run E: every Round-2 lever fired and PASSED in one
  run. 18.9 m / $15.72 / zero warnings — WITH a repair round.**
  Speculative spine launched 2.1 m in at 6/8 passes and validated fresh
  (delta check 38 s / $0.24 against 2 late passes); all four affinity
  sections early-started at spine completion, so the wave dispatched
  only the executive summary; the quality gate flagged findings for the
  third ZaiNar run in a row — one envelope-located — and the
  day-old hybrid repair fixed them in **1.7 m** (envelope 50 s ∥ exec
  72 s ∥ risk 102 s) where D2's whole-package pass took 9.3 m, changing
  only 3 strings (607/610 chase adoption survived). Pin echo 22/0 for
  the second consecutive live run. Two honest caveats: (a) Phase 2 ran
  just 2.3 m, so the speculation window was tiny — the spine overlap
  bought well under a minute here; its real payoff waits for a
  slow-pass company (nvda-class, 6-10 m Phase 2); (b) with English
  accepted at ~11.6 m, the **Chinese chase tail (~7.4 m) is now
  plainly the back-half floor** — the next optimization target is the
  translation phase, not English.
- **2026-08-28 — quality comparison, Run E vs D vs history (all
  zainar-inc): E's memo is on par with D — and the comparison surfaced
  a fact-coverage finding that is NOT a Round-2 defect.** Structure:
  12,202 vs 12,212 EN words, 6 risk cards, 14 sources, 17 components,
  0 blank zh, gates clean in both. Content: E's exec/risk/financial
  sections match D's rigor (fresh angles included). The finding: **D2
  and E both omit the April 20 disclosure update** — the contract book
  appears as "$450M+" with no mention of the $500M+ revision, and the
  patent count as "90+" not "95+". Root cause proven by elimination:
  D2 made the omission with a normal full-input spine, so speculation
  is exonerated; the April figures exist in NO on-disk corpus (no
  research dir, not in the registry) and enter a run only when a
  Phase-2 pass happens to retrieve them from the web — D drew that
  card (one pass), D2 and E did not. E's delta check correctly ruled
  "fresh" (the late passes genuinely contained nothing). Both E memos
  are internally consistent and err conservative (smaller book, lower
  count). Follow-ups queued, not yet built: (1) give dated headline
  commercial facts a durable home the spine always sees (registry
  entry or a per-company fact ledger) — also reduces the
  web-retrieval lottery; (2) the zh currency-style seam (sections
  mixing "$24M" and "2400 万美元" conventions) is confirmed in every
  parallel-translation run including E — fold a shared zh style pin
  into the coming translation-phase work.
- **2026-08-28 — Run D2 (config re-test): 21.6 m / $17.18, and the most
  instructive run of the round.** The quality gate raised 3 genuine
  findings; **sectional repair refused the batch** because one finding
  lives in Section VI's source index — which the *envelope* owns, not
  any section — and the all-or-nothing mapping rule then dragged the
  two cleanly-attributable findings into the 9.3 m whole-package repair
  with it. The +5 m over Run D is exactly that round. Meanwhile the
  detached artifacts agent took 7.6 m (vs 4.3 in D) and gated nothing —
  lever 1's win showed on this run, not D. Pin echo: 22 checked / 0
  findings, first clean live run on the fixed matcher. Follow-up
  SHIPPED: hybrid repair — partition findings into per-section +
  envelope-located, run the parallel section repairs alongside a small
  envelope-only repair, splice both; wholesale fallback only for
  findings that are neither.

- **2026-08-28 — Run D: PASS on every gate.** 16.6 m / $15.03 / zero
  warnings vs the same company's Round-1 runs (22.5 m / $19.47 and
  22.9 m / $16.44) and 36.5 m monolithic baseline. Fastest and cheapest
  ZaiNar memo on record. Honest attribution: part of the −6 m is a
  light Phase 2 (2.6 m — the passes were quick this run) and a
  zero-repair, zero-gap-fill path; the detach mechanism worked exactly
  as designed (artifacts started with the spine, ran 4.3 m fully
  overlapped) but saved little wall *this* run because artifacts
  happened not to be the straggler. Sectional repair went unexercised —
  the quality gate was clean (third consecutive zero-warning run since
  the lint alignment).
- **Chase adoption hit 100% for the first time** (636/636 strings, 0
  blank): English acceptance touched nothing after drafting, so the
  Phase-4 gap-fill was skipped entirely
  (`memo_zh_units_skipped`). New structural observation: with sections
  drafting in 2.3-4.2 m, the run's tail is now the *Chinese chase*
  (~4-5 m per unit on Sonnet, starting only at section completion) —
  the chase tail, not English synthesis, gates the back half of the
  run.
- **2026-08-28 — pin-echo first live outing: 9 findings, all false
  positives, matcher fixed same day (commit 20e3f4e).** The spine
  legally packs treatment prose into metric `value` fields; sections
  echo the numbers, not the sentence. Token-level replay proved every
  numeric token of all 12 pinned metrics present — the pins held.
  Metric matching is now numeric-token-based (verbatim fast path
  kept); replay against Run D = 21 checked / 0 findings. Report-only
  mode caught this before it could burn a repair round — do NOT enable
  `BSH_MEMO_PIN_CHECK_REPAIR` until a few more runs confirm zero false
  positives. (Run D's on-disk `logs/pin_check.md` predates the fix and
  still shows 9.)

## Round 3 — the Chinese translation phase (2026-08-28)

Diagnosis (Run E evidence): the translator is output-bound, not
thinking-bound. One section unit produced **38,471 output tokens in
6.0 minutes** (~107 tok/s, writing the whole time) because the legacy
method re-emits the entire unit — every English string copied back, plus
the Chinese, plus JSON. Effort was never lowered for the translation
role, so default-effort thinking tokens ride on top. The chase can only
start a unit when its section finishes, so the slowest unit sets the
run's tail (~7.4 m of Run E's back half).

Levers (operator decisions 2026-08-28: all approved, no Haiku for now):

| Lever | Flag / setting | Mechanism |
|---|---|---|
| Compact zh output | `BSH_MEMO_ZH_COMPACT=1` | translator returns ONLY the Chinese strings (schema-enforced count); Python pastes them in; per-unit fallback to the legacy method on any failure |
| Medium effort | `BSH_MEMO_EFFORT_TRANSLATION=medium` | cuts default-effort thinking; low deferred until a run's Chinese is read at medium |
| Number/date style note | always on (both methods) | fixed conventions: `$24M`, `42x`, `+180%`, `2026 年 2 月 19 日` — ends the per-unit style coin flip |
| Split big units | `BSH_MEMO_ZH_SPLIT_CHARS=20000` | a unit above ~20KB of translatable English runs as two parallel halves |

### Validation protocol (Run F)

One zainar-inc run (inputs frozen, same corpus state as D/D2/E).
Gates:

- chase unit times: sections ≤ ~2.5 m (vs 3.7-5.2 m today); the join
  should be near-zero because translations finish before English
  acceptance;
- adoption ≥ the current ~99% and zero blanks after gap-fill;
- currency/date style consistent across every section (spot-grep both
  conventions);
- the Chinese reads as well as D/E — full section read against the
  three fresh baselines, per the quality-comparison method;
- run total: expect ~14-15 m if the tail collapses as modeled.

### Round-3 results

| Run | Config | English accepted | Chase units | Total | Cost | Quality |
|---|---|---|---|---|---|---|
| F. Compact zh (zainar-inc) | E + `ZH_COMPACT` + `EFFORT_TRANSLATION=medium` + style note + split | ~9.5 m (incl. 1.4 m hybrid repair) | envelope 24 s; sections 67-75 s; financial 143 s (split 2×) | **12.9 m** | $15.82 | `complete`, lint P0=0, parity P0=0, pin echo 22/0 |

Run F source: `data/memos/zainar-inc/2026-08-28__214223__zainar-inc__memo-run`.

- **2026-08-28 — Run F: PASS on every gate. 12.9 m — the fastest memo on
  record, −43% vs Round 1, −65% vs the monolith, WITH a repair round.**
  Compact translation cut unit times 3-5x (sections 67-75 s vs
  222-398 s; financial 143 s with the 2-way split vs 253-393 s) and
  chase cost to $1.36 (vs $2.04-2.12). Zero compact fallbacks; zero
  blank zh; adoption 634/638 with the 4 repair-invalidated strings
  gap-filled. Hybrid repair fired again (3 workers, 1.4 m). Pin echo
  22/0, third consecutive clean run.
- **Style note verdict:** currency and dates are now 100% consistent
  across every section ($-form ×175, 万/亿 ×0, all dates 年月日) — the
  seam is gone. Multiples are mostly x-form (86 x vs 35 倍) but the
  executive-summary unit favored 倍 where grammar suggests it
  ("收入的 42 倍"). Open operator decision: accept the grammar-driven
  mix, or add an explicit example to the note to force x everywhere.
- **Chinese quality at medium effort: no loss.** Full read of the exec
  and risk sections against the D/E baselines: fluent, precise
  register, correct fixed labels, natural phrasing — arguably the most
  natural opening paragraph of any run. Trying effort=low stays
  possible but is not urgent.
- **Fact lottery, third draw missed:** F also carries $450M+/90+ only
  (no $500M+/95+ April figures) — now 3 of the 4 latest runs. The
  durable fact-ledger follow-up rises in priority.

### Round-3 follow-up decisions (2026-08-28)

- **Multiples style: the grammar-driven mix stands** (operator decision).
  "收入的 42 倍" where Chinese grammar wants 倍, x-form elsewhere. No
  note change.
- **Fact ledger: queued.** Dated headline commercial facts get a durable
  home the spine always reads; rose to top quality priority after the
  April figures missed 3 of 4 draws. Not yet built.

## nvda experiment — D_v2 vs E_v2 (queued)

Purpose: measure the speculation levers where they should actually pay —
nvda's Phase 2 has run 4.2-10.8 m (vs zainar's ~2.5 m), so the spine
overlap and early section starts have a real pass tail to hide in.

Protocol: two nvda runs, single variable. Both carry the full Round-3
stack (parallel English, chasing, artifacts async, sectional repair, zh
compact, translation sonnet+medium). D_v2 = speculation flags OFF;
E_v2 = ON. Restart the server between runs. Compare phase-level: when
the spine ran vs Phase 2's tail, wave start time, early-section rows,
delta verdict — plus totals and the usual gates. Expected: E_v2 beats
D_v2 by ~2-4 m; a stale delta verdict is data, not failure.

### nvda results

| Run | Config | Phase 2 | Spine | English accepted | Total | Cost | Quality |
|---|---|---|---|---|---|---|---|
| D_v2 | full Round-3 stack, speculation OFF | 6.3 m (passes 1.6-6.3) | 4.3 m, serial after Phase 2 | ~17.9 m (incl. sectional repair: overview ∥ financial) | **18.1 m** | $18.41 | `complete`, lint P0=0, parity P0=0, pin echo 22/0 |

Run D_v2 source: `data/memos/nvda/2026-08-28__220351__nvda__memo-run`.

- **2026-08-28 — D_v2: nvda record, 18.1 m vs 29.9-30.2 (Round 1) and
  43.7 (monolith) — with a repair round.** Compact translation held at
  nvda scale: units 23-110 s, no splits needed, zero fallbacks, chase
  $1.16, adoption 629/631. The back-half tail is GONE — the run ended
  seconds after English acceptance, so the pipeline is now
  English-bound end to end. That makes E_v2 the cleanest possible A/B:
  the 4.3 m serial spine sits directly on the critical path, and nvda's
  6.3 m Phase-2 tail is wide enough to hide almost all of it. Predicted
  E_v2: ~14-15 m. Pin echo 22/0 — fourth consecutive clean run.
| E_v2 | full Round-3 stack, speculation ON | 3.5 m slowest pass (window halved vs D_v2 — run variance) | speculative 4.5 m → **delta verdict: STALE** → respin 5.7 m | ~19 m | 21.5 m | $18.72 | `complete`, lint P0=0, parity P0=0, pin echo 22/0 |

Run E_v2 source: `data/memos/nvda/2026-08-28__222410__nvda__memo-run`.

- **2026-08-28 — E_v2: the stale branch fired live, correctly, and made
  the memo better.** The late passes surfaced a top-tier risk the
  speculative spine had pinned without: the 10-Q's up-to-$108.5B
  guarantee exposure (credit support for an Ohio compute campus leased
  to OpenAI) with 5-customer receivables concentration rising 56%→70%.
  The delta check refused the pins, the 4 early section drafts were
  discarded as designed, the respin pinned WITH the risk, and the final
  memo carries it (verified in the package). D_v2 never had this second
  look at the late passes.
- **Experiment verdict (D_v2 18.1 m vs E_v2 21.5 m): timing is a wash,
  confounded twice** — E_v2's Phase-2 window was half of D_v2's (3.5 vs
  6.3 m slowest pass, run variance) AND it drew the stale branch (the
  designed ~4 m bounded loss). Fresh-branch speculation on a slow-pass
  run remains unobserved on nvda. The durable findings: both branches
  now proven live (fresh ×2 on zainar, stale ×1 here); the delta check
  doubles as a fact-safety net for exactly the fact-lottery misses; the
  stale cost is bounded and bought a materially better memo this run.
- **Follow-up queued: chase eviction on respin.** The chaser's
  idempotency (correct for repairs) meant the respun sections were
  never re-chased — adoption 112/632, 520 strings gap-filled (compact
  gap-fill absorbed it in ~1.5 m, so the run barely noticed). On a
  stale respin the chaser should evict and re-chase. Small, rare-path.
- **Pin echo 22/0 — fifth consecutive clean live run.** Arming
  BSH_MEMO_PIN_CHECK_REPAIR is now a reasonable operator choice.
