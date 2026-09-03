# Memo pipeline — current structure and optimization record

Written 2026-08-28, at the end of the Round 2–3 optimization work on
branch `report-speedup-r2`. Three docs cover this system:

- `docs/memo-pipeline-anatomy.html` (+ `.zh.html`) — the deep anatomy of
  the PRE-optimization pipeline (how agents work, sources, assembly).
  Still correct about fundamentals; superseded on timings and structure.
- `docs/memo-benchmarks.md` — every benchmark run, gate, and decision.
- **This file** — the pipeline as it exists NOW, where each piece lives
  in code, every flag, and (most importantly) the map of everything that
  depends on the memo's section structure. Read this before changing
  the sections.

## 1. The pipeline today, end to end

All agents are `claude -p` subprocesses (`--permission-mode
bypassPermissions`, stream-json, `--json-schema`). They have the full
tool set, including web search — nothing fences retrieval (see §5,
"fact lottery"). Cost/duration flow through progress side-channels;
every worker gets a thread row and `phase_timing` events.

### Phase 1 — bootstrap (seconds)

Run folder, registry entry (`companies.yaml`), scope check. No AI at
run time. If `data/research/<slug>/fact_ledger.md` exists (the curated
per-company fact ledger, Round 4), a `memo_fact_ledger` stage records
that it will be injected downstream
(`claude_runner.load_memo_fact_ledger`; kill switch
`BSH_MEMO_FACT_LEDGER=0`; 6,000-char cap). The tracked-news digest
rides the same mechanism: the workers refresh
`data/research/<slug>/recent_news.md` from the tracking-updates store
before Phase 2 (`memo_analysis._write_recent_news_file`, best-effort),
and `claude_runner.load_memo_recent_news` injects it into every pass
and the spine — never the shared section context (kill switch
`BSH_MEMO_TRACKED_NEWS=0`).

### Phase 2 — 8 analysis passes (~2.3–6.3 m, gated by slowest pass)

`memo_analysis._FAST_MEMO_PASSES` defines 8 pass specs (id, label,
artifact filename, focus). Dispatch: `ThreadPoolExecutor` with
`as_completed` (8 workers, `BSH_MEMO_FAST_MAX_WORKERS`). Each pass
writes `analysis/fast/{pass_id}.json` (schema-capped: ≤8 findings, ≤8
supporting, ≤6 disconfirming, ≤5 limits, ≤6 implications) plus a
markdown artifact, at its own completion time.

Each completion also calls `speculator.note_pass_result(pass_id, ok)`
when the speculative spine is on.

### Phase 2.5 — speculation (`claude_runner.SpeculativeEnglish`)

Flags: `BSH_MEMO_SPINE_SPECULATIVE=1` (+`_AFTER`, default 6 of 8;
+`_REQUIRE`, default the pin-feeding passes) and
`BSH_MEMO_SECTION_EARLY_START=1` (requires the former).

- Launch condition (pin-affine since Round 4): the count threshold AND
  every pass in `MEMO_SPINE_PIN_FEEDING_PASSES`
  (`arithmetic_denominators`, `time_base`, `growth_bridge`) completed —
  either outcome; a failed pass has nothing left to wait for. If the
  count is met but a required pass is still running, a one-time
  `memo_spine_speculation_holding` stage fires and the spine waits;
  when the pin passes are dead last it launches with nothing late and
  the run degrades cleanly to normal spine timing. The spine launches
  with the not-yet-finished passes named in its prompt
  (`speculative_missing`).
- On spine success the coordinator validates the skeleton shape, writes
  `logs/english_units/spine.json`, fires the zh chaser's envelope hook,
  and launches any section whose affine passes are done
  (`MEMO_SECTION_PASS_AFFINITY`; the executive summary never starts
  early).
- When all passes land, `consume()` runs the **delta check**
  (`run_memo_spine_delta_check`, role `SPINE_CHECK`, ~40 s): do the
  late passes force any pinned fact to change?
  - **fresh** → the wrapper reuses the spine; early sections are
    harvested; the wave drafts only what's left.
  - **stale / any failure** → early drafts discarded
    (`memo_early_sections_discarded`), fresh spine respin
    ("English spine (respin)"), full wave.
- Observed live (4 draws, pre-pin-affine): fresh 2/2 on zainar (thin
  private corpus), stale 2/2 on nvda (rich public corpus — and the slow
  passes were exactly the pin-feeding ones). Stale costs ~4 m + ~$4–5
  and both times produced a materially better pin sheet. The Round-4
  pin-affine gate above exists to convert that class of stale draw into
  a wait; the delta check stays armed for pin-relevant facts arriving
  from non-required passes.

### Phase 3 — parallel English (`claude_runner.run_memo_fast_english_package_parallel`)

Flag: `BSH_MEMO_ENGLISH_PARALLEL=1` (monolithic fallback otherwise and
on any structural failure).

- **Common context** (`_memo_english_common_context`, ~21 KB) goes to
  every call as `--append-system-prompt` (prompt-cache shared). It
  carries the voice contract, block contract, sources contract, parity
  contract (component slugs), registry entry, file listings, and the
  read instructions (`analysis/fast/*.json` first).
- **Spine-lite** (`run_memo_fast_english_spine`): envelope
  (company/run/complete sources) + `shared_facts` pin sheet
  (recommendation sentence, ≤12 metrics, bear/base/bull, 4–6 rated
  risks, source topics) + optional `section_notes`. Hard schema caps.
- **Five section workers** (`_run_english_section`): shared head =
  rendered fact sheet (`_render_shared_facts_block`, byte-identical to
  all) + spine path (cite sources by id, cannot add); unique tail =
  `_MEMO_SECTION_SPECS[id]` (+ risk-register contract for
  `investment_risk`). Output schema is loose (`{"section": object}`) —
  enforcement is post-hoc.
- **Detached artifacts** (`claude_runner.AsyncArtifacts`,
  `BSH_MEMO_ARTIFACTS_ASYNC=1`): the 7 private artifacts run on their
  own thread from wrapper entry, joined by `memo_analysis` after
  acceptance. Failure degrades to stub files, never sinks the pass.
- **Acceptance gates**, in order (in `memo_analysis`'s attempt loop):
  1. deterministic structure repair (`repair_package_structure`);
  2. renderer validation (`english_package_validation_errors`);
  3. prerender quality gate (render to temp DOCX → `memo_quality_lint`);
  4. **pin-echo check** (`memo_pin_check.check_package_pins`,
     `BSH_MEMO_PIN_CHECK` default on, report-only; feeds repair only
     with `_REPAIR=1`): recommendation verbatim in the exec summary,
     metric numeric tokens somewhere, risk ratings in the risk
     section, scenario numbers in the financial section. 22/0 across
     six straight live runs.
  5. **hybrid repair** (`BSH_MEMO_SECTIONAL_REPAIR=1`): findings
     partitioned per-section / envelope / unattributable
     (`_partition_repair_findings`). Section repairs
     (`run_memo_section_repair`) and a small envelope repair
     (`run_memo_envelope_repair`) run in parallel and splice; only an
     unattributable finding falls back to the ~9 m whole-package pass
     (`run_memo_package_structure_repair`). Observed: 1.4–2.0 m rounds.
  6. selective section retry / full retry (max 3 attempts) with
     cumulative error feedback; final-resort whole-package structure
     repair.
- Acceptance writes `logs/memo_package.en.json` (pure, pre-chase).

### Phase 4 — Chinese (`BSH_MEMO_BILINGUAL_PARALLEL` default on)

- **Chasing** (`claude_runner.BilingualChaser`,
  `BSH_MEMO_ZH_CHASING=1`): envelope translates at spine completion,
  each section at its completion (attempt 1 only; snapshots under
  `logs/bilingual_units/chase/`). Post-acceptance: `collect()` join
  (workers `BSH_MEMO_ZH_CHASE_WORKERS`=4) → `merge_into` adopts only
  exact-`en`-match strings → `logs/memo_package.en.chased.json` →
  gap-fill (`only_missing=True`). A repair or respin after chasing
  just strands some strings for gap-fill — bounded waste.
- **Compact translation** (`BSH_MEMO_ZH_COMPACT=1`, in
  `_run_bilingual_unit`): sends a numbered list of ONLY the blank-`zh`
  English strings; gets back a schema-enforced array of exactly that
  many Chinese strings; Python pastes them via the same walker that
  built the list. Units over `BSH_MEMO_ZH_SPLIT_CHARS` (~20 KB) run as
  two parallel halves. Any failure falls back per-unit to the legacy
  full-unit method. Measured: sections 56–110 s (was 222–398 s).
  Root cause it fixed: the legacy method re-emits all the English
  (38K output tokens / 6 m for one section).
- **Style note** (`MEMO_ZH_NUMBER_STYLE_NOTE`, both methods): `$24M`,
  `x`-form multiples (grammar-driven 倍 accepted — operator decision),
  `+180%`, dates `2026 年 2 月 19 日`. Fixed the per-unit currency
  style coin flip.
- Safety net unchanged: render validation + zh-repair; monolithic zh
  fallback untouched by all of the above.
- **Render**: `memo_docx_renderer.render_memos` — fully deterministic
  (Arial / Microsoft YaHei 10.2 pt, roman-numeral titles, cover,
  Section VI generated from the envelope's sources list). Post-render:
  quality lint + Chinese parity gates (warning-only at this point).

### The Memo Studio seam (2026-09-01, branch memo-studio)

The pipeline is split at the Phase 2 → Phase 3 boundary
(`memo_analysis._run_fast_phase2` + `_run_fast_synthesis`; the One-Click
composition in `_run_fast_memo_pipeline` is emit-for-emit identical to
the old straight line). Two modes on the report record (`memo_mode`,
absent = `auto`):

- **Studio Review** (`POST /api/memos/studio/investigate`, requires
  `BSH_MEMO_ENGLISH_PARALLEL=1`): Phase 1-2 + ONE deterministic
  standalone spine (`claude_runner.run_memo_english_spine_standalone`,
  no speculation/delta check, studio-extended schema with optional
  `studio_extras`: thesis seeds + conclusion stances), cards seeded into
  `memo_editor_store` via `apply_agent_spine`, then the run parks at
  status **`awaiting_studio`** with a terminal `done` on the stream
  (that event is what keeps SSE, the jobs rail, and the orphan sweep
  correct for a parked run). `POST /api/memos/studio/{id}/generate`
  composes the user's edited cards back into `spine.json` +
  `studio_pin_sheet.md` (`server/memo_studio_bridge.compose_spine`,
  freeze semantics) and re-enters `_run_fast_synthesis` with
  `pinned_spine_path`: the spine agent and speculative consume are
  skipped on every attempt, and every monolithic fallback is a hard
  error (it would discard the card edits). The pin-echo gate then
  enforces the user's decisions mechanically — cards ARE pins.
  Regeneration = the same endpoint again (streams/packages archived,
  `generation_count` bumps). Studio runs never use the monolithic
  resume path; recovery is Investigate again / Generate again.
- **One-Click** (`POST /api/reports`, unchanged): the full pipeline,
  byte-identical, plus a post-finalize `_publish_studio_cards` so the
  studio cards show the agent's ranking after every successful run.

Report type **"Investment Report (Auto)"** (default in the UI) replaces
the old stub type: same late-stage kind and pipeline, but
`_assess_stage(calibrate_only=True)` turns early-stage/indeterminate
from a scope warning into neutral stage-calibration guidance (nonprofit
still hard-fails).

### Observability

Thread rows: phase_index 2.x passes, 3.01 spine (3.015 delta check),
3.02 artifacts, 3.03+ sections, 3.50 envelope repair, 3.51+ section
repairs, 4.01+ chase units, 4.11+ gap-fill units. `phase_timing` names:
`english_spine[_delta_check]`, `english_artifacts`,
`english_section:{id}`, `english_repair:{id|envelope}`,
`zh_chase:{id}`, `zh_section:{id}`, `memo_zh_chase`.
`scripts/memo_phase_report.py <run_dir>` prints the table plus derived
lines (attempts, chase, speculation verdict, early sections, repairs,
pin echo, gates).

## 2. Flag reference (defaults in parentheses)

| Flag | Meaning |
|---|---|
| `BSH_MEMO_FAST_PIPELINE` (1) | fast pipeline vs legacy monolith |
| `BSH_MEMO_FAST_MAX_WORKERS` (8) | Phase-2 pool |
| `BSH_MEMO_ENGLISH_PARALLEL` (0) | spine-lite + section workers |
| `BSH_MEMO_ENGLISH_SECTION_WORKERS` (6) | wave pool |
| `BSH_MEMO_ARTIFACTS_ASYNC` (0) | detach artifacts agent |
| `BSH_MEMO_SPINE_SPECULATIVE` (0), `BSH_MEMO_SPINE_SPECULATE_AFTER` (6) | early spine + delta check |
| `BSH_MEMO_SPINE_SPECULATE_REQUIRE` (pin-feeding passes) | pin-affine launch gate; `none` = count-only |
| `BSH_MEMO_SECTION_EARLY_START` (0) | affinity early sections |
| `BSH_MEMO_PIN_CHECK` (1), `BSH_MEMO_PIN_CHECK_REPAIR` (0) | pin echo; feed repair |
| `BSH_MEMO_FACT_LEDGER` (1) | inject `data/research/<slug>/fact_ledger.md` into passes + spine (file presence is the real switch) |
| `BSH_MEMO_TRACKED_NEWS` (1) | inject `data/research/<slug>/recent_news.md` (auto-refreshed from the tracking-updates store before Phase 2) into passes + spine |
| `BSH_MEMO_SECTIONAL_REPAIR` (0) | hybrid per-section + envelope repair |
| `BSH_MEMO_ZH_CHASING` (0), `BSH_MEMO_ZH_CHASE_WORKERS` (4), `BSH_MEMO_ZH_CHASE_JOIN_TIMEOUT_SEC` (900) | chasing |
| `BSH_MEMO_ZH_COMPACT` (0), `BSH_MEMO_ZH_SPLIT_CHARS` (20000) | compact translation + split |
| `BSH_MEMO_MODEL`/`BSH_MEMO_EFFORT` + `_{ROLE}` | per-role model/effort; roles: ANALYSIS_PASS, ENGLISH, SPINE, SECTION, ARTIFACTS, SPINE_CHECK, TRANSLATION, REPAIR |

Live `.env` today (2026-08-31): parallel + chasing + artifacts async +
sectional repair + speculation + zh compact + **pin repair armed**
(`BSH_MEMO_PIN_CHECK_REPAIR=1`), `MODEL_TRANSLATION=claude-sonnet-5`,
`EFFORT_TRANSLATION=medium`. Fact ledgers seeded for `zainar-inc` and
`nvda`.

## 3. THE SECTION-CHANGE MAP

Everything below hardcodes or depends on the current five-section
structure. Changing the section set means touching, in order:

**The section list itself (two synced copies):**
- `claude_runner.MEMO_PACKAGE_SECTION_IDS` — kept literal so
  claude_runner stays import-free of the renderer;
- `memo_docx_renderer.REQUIRED_SECTION_IDS` — MUST match. Validation
  fails on any missing required id.

**Renderer (visual structure):**
- `memo_docx_renderer.SECTION_TITLES` — fixed bilingual titles with
  roman numerals ("I. Executive Summary" … "VI. Sources…"). A new/renamed
  section needs an entry here, or the package must carry a bilingual
  `title` (unknown ids without titles fail validation).
- Section VI is NOT a section object — it renders from the envelope's
  `sources` list. Quality findings located there belong to the
  ENVELOPE (see the repair partition below).
- `memo_docx_renderer.REQUIRED_MEMO_COMPONENTS` — 17 component slugs
  with regex patterns and allowed block types; coverage written to
  `logs/validation.txt`. Moving a component between sections is fine
  (coverage is package-wide); removing one breaks validation.

**Prompts (content structure):**
- `claude_runner._MEMO_SECTION_SPECS` — the per-section recipe (which
  components each section must carry). The single most important thing
  to edit when sections change.
- `MEMO_CONTENT_PARITY_CONTRACT` — lists the same component slugs in
  the shared context; must stay consistent with the renderer's list.
- `MEMO_RISK_REGISTER_CONTRACT` — applies only to `investment_risk`
  (wired in `_run_english_section` and `run_memo_section_repair`).
- The spine prompt enumerates section ids (`section_list`) and the
  spine schema generates `section_notes` properties from
  `MEMO_PACKAGE_SECTION_IDS`.

**Error attribution (repairs and retries):**
- `claude_runner._MEMO_SECTION_TITLE_WORDS` — maps lint location
  context ("iii. investment highlights") to section ids. New titles
  need entries.
- `_section_for_validation_error` — id-token, `sections[N]` index,
  component, title-context, then snippet search.
- `_is_envelope_repair_finding` — `_ENVELOPE_CONTEXT_MARKERS` contains
  "sources, source classes" / "fact reference index" (the Section VI
  heading words). Renaming Section VI means updating these markers.

**Speculation:**
- `claude_runner.MEMO_SECTION_PASS_AFFINITY` — section id →
  pass-id set. New sections need affinity entries (or they simply
  never early-start, which is safe). The executive summary is absent
  by design.

**Pin check:**
- `memo_pin_check` targets sections by id constants
  (`_SECTION_EXEC`, `_SECTION_RISK`, `_SECTION_FINANCE`): the
  recommendation must appear in the exec summary, risk ratings in the
  risk section, scenario numbers in the financial section.

**Chinese:**
- Chase units are envelope + one per section (`BilingualChaser
  .on_section` indexes into `MEMO_PACKAGE_SECTION_IDS` for
  phase_index). Compact translation and split are structure-agnostic
  (they walk whatever unit they get).
- `_MEMO_BILINGUAL_STYLE` fixed label translations assume the
  risk-card row labels.

**Tests that pin section structure:** `tests/test_memo_english_parallel.py`
(assembly order, spine shape), `test_memo_sectional_repair.py`
(mapping), `test_memo_early_sections.py` (affinity consistency check —
it asserts affinity keys ⊂ section ids and pass ids ⊂ the 8 passes),
`test_memo_pin_check.py`, renderer tests. The affinity/consistency test
will catch a renamed section id immediately.

**Safe-change recipe:** update the two id lists + SECTION_TITLES +
_MEMO_SECTION_SPECS + parity contract + title words + affinity (+ pin
check ids if exec/risk/financial change), run the full suite (the
structure-pinning tests fail loudly), then one live validation run.

## 4. Optimization record (what changed, in order)

| Round | What | Result (same-company deltas) |
|---|---|---|
| — | Monolithic baseline | nvda 43.7 m / zainar 36.5 m |
| 1 | Spine-lite (+cache sharing), Sonnet translation, zh chasing, workers 8, lint alignment | nvda ~30 m, zainar 22.5–22.9 m |
| 2 | Artifacts detach, pin-echo check, sectional→hybrid repair, speculative spine, early sections | zainar 16.6–18.9 m; repair rounds 9.3 m → 1.4–2.0 m |
| 3 | Compact zh translation, effort medium, style note, big-unit split | zainar **12.9 m**, nvda **18.1 m** (D-config) |
| 4 | Pin-affine spine launch, fact ledger, pin-repair armed | shipped 2026-08-31, live validation pending (ledger resets baselines) |

Full run records and decision logs: `docs/memo-benchmarks.md`. The
recurring design pattern: **speculate on partial input, verify cheaply,
redo only what the verifier invalidates** (chasing → speculative spine
→ early sections), with deterministic verifiers (pin echo, exact-en
merge, schema-enforced counts) making the speculation safe.

## 5. Known structural facts worth remembering

- The run is now **English-bound end to end**: translation finishes
  before English acceptance; render is ~1 s.
- Phase-2 pass durations vary run-to-run more than most optimizations
  (1.3–10.8 m slowest-pass observed) — judge variants at phase level.
- **Fact lottery** (addressed in Round 4): headline commercial facts
  (e.g. zainar's $500M+/95+ revision) existed in no on-disk corpus and
  entered runs only via per-pass web retrieval — 3 of 4 zainar runs
  missed them. The fact ledger (§1 Phase 1, §2) is the durable fix;
  the delta check remains a partial net on the speculative path for
  facts newer than the ledger. Keep ledgers dated and current — a
  stale ledger is a new way to pin an old number.
- Repair rounds fire on roughly half of runs, always for genuine
  voice/disclosure findings since the lint alignment; the hybrid path
  has handled every one since it shipped.
- Pin echo: 22 checked / 0 findings on six consecutive live runs.

## 6. Queued work

Shipped 2026-08-31 (Round 4, commits 9404039/ca0b061 + `.env`):
**pin-affine spine launch** (launch gate now waits for the pin-feeding
passes; `BSH_MEMO_SPINE_SPECULATE_REQUIRE`), **fact ledger**
(`data/research/<slug>/fact_ledger.md`, seeded for zainar-inc and
nvda), **pin-repair arming** (`BSH_MEMO_PIN_CHECK_REPAIR=1` in the live
`.env`; watch the first run where a finding actually fires). Not yet
validated live — see memo-benchmarks.md Round 4 for the validation
plan, and note the ledger breaks comparability with pre-ledger runs.

Still queued:

0. **Per-component format contracts** (user, 2026-09-01): section
   format varies draw to draw — e.g. the closing decision came out as a
   labeled "core bet" bullet list on 8-28, a rich callout on other
   draws, and plain paragraphs after the 8-31 voice polish (which also
   thinned it: "action ... in sentence form"). Fix = the risk-register
   pattern, per component: a fixed format contract in the section spec
   (e.g. `investment_decision` = labeled callout with the six spine
   rows; `evidence_thresholds` = fixed-column table) + a deterministic
   shape check like `_risk_card_format_errors` feeding the existing
   hybrid repair. §3 lists every file this touches. Fixes One-Click
   and Studio at once.
1. Chase eviction on respin (rare-path; today stale respins strand
   chase output and gap-fill absorbs it — rarer now that pin-affine
   should prevent most stale respins).
2. More D-vs-E testing (fresh-branch speculation on a slow-pass run is
   still unobserved on nvda; post-ledger baselines needed anyway).
3. Effort=low trial for translation; web-retrieval fencing via
   `--disallowedTools` if provenance tightening is wanted.

## 7. Code landmark index

| File | What lives there |
|---|---|
| `server/claude_runner.py` | all agent calls and prompts; section ids/specs/contracts; parallel orchestrator; `AsyncArtifacts`; `SpeculativeEnglish` (+delta check, pin-affine gate `MEMO_SPINE_PIN_FEEDING_PASSES`); `BilingualChaser`; compact translation; hybrid repair; fact ledger (`load_memo_fact_ledger`); role/model/effort knobs |
| `server/memo_analysis.py` | pipeline driver: phases, attempt loop, gates, repairs wiring, pass specs, Phase-4 seam |
| `server/memo_studio_bridge.py` | Memo Studio cards → spine composition (`compose_spine`, pin sheet, rating normalization) |
| `server/memo_editor_store.py` | studio card state; `apply_agent_spine` (spine → cards seed), card CRUD, version snapshots |
| `server/memo_pin_check.py` | deterministic pin-echo checker |
| `server/memo_quality_lint.py` | DOCX quality lint (voice/meta/disclosure rules) |
| `server/memo_chinese_parity.py` | EN/ZH parity gate |
| `server/memo_docx_renderer.py` | deterministic renderer; required ids/components; validation; structure auto-repair |
| `server/job_progress.py` | ProgressLog, ThreadProgress (lock-guarded) |
| `scripts/memo_phase_report.py` | run extraction for benchmarks |
