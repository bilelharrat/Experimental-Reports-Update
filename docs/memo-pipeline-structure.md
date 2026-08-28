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
tool set, including web search — nothing fences retrieval (see §6,
"fact lottery"). Cost/duration flow through progress side-channels;
every worker gets a thread row and `phase_timing` events.

### Phase 1 — bootstrap (seconds)

Run folder, registry entry (`companies.yaml`), scope check. No AI at
run time.

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

Flags: `BSH_MEMO_SPINE_SPECULATIVE=1` (+`_AFTER`, default 6 of 8) and
`BSH_MEMO_SECTION_EARLY_START=1` (requires the former).

- At the threshold, the spine launches with the not-yet-finished passes
  named in its prompt (`speculative_missing`).
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
- Observed live (4 draws): fresh 2/2 on zainar (thin private corpus),
  stale 2/2 on nvda (rich public corpus — and the slow passes are
  exactly the pin-feeding ones). Stale costs ~4 m + ~$4–5 and both
  times produced a materially better pin sheet. See §6 for the queued
  pin-affine launch fix.

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
| `BSH_MEMO_SECTION_EARLY_START` (0) | affinity early sections |
| `BSH_MEMO_PIN_CHECK` (1), `BSH_MEMO_PIN_CHECK_REPAIR` (0) | pin echo; feed repair |
| `BSH_MEMO_SECTIONAL_REPAIR` (0) | hybrid per-section + envelope repair |
| `BSH_MEMO_ZH_CHASING` (0), `BSH_MEMO_ZH_CHASE_WORKERS` (4), `BSH_MEMO_ZH_CHASE_JOIN_TIMEOUT_SEC` (900) | chasing |
| `BSH_MEMO_ZH_COMPACT` (0), `BSH_MEMO_ZH_SPLIT_CHARS` (20000) | compact translation + split |
| `BSH_MEMO_MODEL`/`BSH_MEMO_EFFORT` + `_{ROLE}` | per-role model/effort; roles: ANALYSIS_PASS, ENGLISH, SPINE, SECTION, ARTIFACTS, SPINE_CHECK, TRANSLATION, REPAIR |

Live `.env` today: parallel + chasing + artifacts async + sectional
repair + speculation + zh compact, `MODEL_TRANSLATION=claude-sonnet-5`,
`EFFORT_TRANSLATION=medium`.

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
- **Fact lottery**: headline commercial facts (e.g. zainar's April
  $500M+/95+ update) exist in no on-disk corpus and enter runs only
  via per-pass web retrieval. 3 of 4 zainar runs missed them. The
  delta check partially nets this on the speculative path only.
- Repair rounds fire on roughly half of runs, always for genuine
  voice/disclosure findings since the lint alignment; the hybrid path
  has handled every one since it shipped.
- Pin echo: 22 checked / 0 findings on six consecutive live runs.

## 6. Queued work (agreed 2026-08-28, not built)

1. **Pin-affine spine launch** — launch the speculative spine when the
   pin-feeding passes (arithmetic_denominators, growth_bridge,
   time_base) are done, instead of any 6 of 8. Motivated by nvda's 2/2
   stale draws, both caused by exactly those passes finishing late.
2. **Fact ledger** — a durable dated home for headline commercial
   facts that the spine always reads; kills the fact lottery. Freeze
   ledger state inside benchmark comparisons (rule recorded in
   memo-benchmarks.md).
3. **Pin-repair arming** — `BSH_MEMO_PIN_CHECK_REPAIR=1` after the
   clean streak; watch the first fed run closely.
4. Chase eviction on respin (rare-path; today stale respins strand
   chase output and gap-fill absorbs it).
5. More D-vs-E testing (fresh-branch speculation on a slow-pass run is
   still unobserved on nvda).
6. Effort=low trial for translation; web-retrieval fencing via
   `--disallowedTools` if provenance tightening is wanted.

## 7. Code landmark index

| File | What lives there |
|---|---|
| `server/claude_runner.py` | all agent calls and prompts; section ids/specs/contracts; parallel orchestrator; `AsyncArtifacts`; `SpeculativeEnglish` (+delta check); `BilingualChaser`; compact translation; hybrid repair; role/model/effort knobs |
| `server/memo_analysis.py` | pipeline driver: phases, attempt loop, gates, repairs wiring, pass specs, Phase-4 seam |
| `server/memo_pin_check.py` | deterministic pin-echo checker |
| `server/memo_quality_lint.py` | DOCX quality lint (voice/meta/disclosure rules) |
| `server/memo_chinese_parity.py` | EN/ZH parity gate |
| `server/memo_docx_renderer.py` | deterministic renderer; required ids/components; validation; structure auto-repair |
| `server/job_progress.py` | ProgressLog, ThreadProgress (lock-guarded) |
| `scripts/memo_phase_report.py` | run extraction for benchmarks |
