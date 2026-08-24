# Investment Memo Pipeline

How "Generate Report → Investment Memo (Late-Stage)" works.

> See also: [architecture.md](architecture.md) — the two-feature split.
> The memo flow is **completely independent** of the Document Library.

## Pipeline

```
POST /api/reports  (report_type = "Investment Memo (Late-Stage)")
  │
  ▼
memo_prep.bootstrap_memo_run(company_id)          # synchronous, seconds
  ├── Resolve company → look up the record in data/companies.yaml
  ├── Scope check    → late-stage / pre-IPO preferred; warn early-stage
  ├── Mint run dir   → data/memos/<slug>/<YYYY-MM-DD>__<HHMMSS>__<slug>__memo-run/
  ├── Create subdirs → memo/, analysis/, logs/, logs/previews/, logs/previews_cn/
  ├── Write skeleton → logs/run_manifest.md (run_id, company, skill version)
  ├── Create report  → data/reports/<id>.yaml (status: prepping → ready_for_analysis)
  └── Emit prep events to logs/stream.jsonl  (job_init, company_resolved, scope_check, prep_complete)
  │
  ▼  (hand off to background daemon thread)
memo_analysis._run(report_id)                      # long-running
  ├── Default fast path (BSH_MEMO_FAST_PIPELINE defaults to on)
  │   ├── If no approved Memo Studio packet exists:
  │   │   ├── Spawn 8 narrow Claude subprocesses for independent analysis
  │   │   │   passes (bounded by BSH_MEMO_FAST_MAX_WORKERS, default 4)
  │   │   └── Python writes concise analysis/*.md + analysis/fast/*.json
  │   ├── If an approved Memo Studio packet exists:
  │   │   └── Skip the analysis fan-out and use the packet as synthesis input
  │   ├── Spawn one Claude subprocess to write:
  │   │   ├── synthesis artifacts (claim register, scenarios, gates, etc.)
  │   │   └── logs/memo_package.en.json, the English source package
  │   └── Spawn one Claude subprocess to fill Chinese strings and write
  │       logs/memo_package.json
  │
  ├── Legacy fallback path (BSH_MEMO_FAST_PIPELINE=0)
  │   └── Spawn one Claude subprocess via claude_runner.run_investment_memo()
  │       using Serena's full skill prompt and prompt-level parallel tool calls
  │
  ├── After logs/memo_package.json exists:
  │     Block generated render scripts like build_memo.py
  │     Else validate logs/memo_package.json
  │     Else Python runs server.memo_docx_renderer
  │     Else verify the two .docx files, validation logs, file inventory,
  │     and manifest renderer marker exist
  │     Else run Chinese parity and English memo quality gates
  │     Else mark the LP-facing memo ready
  │
  │     Optional post-processing:
  │     - BSH_MEMO_RENDER_PDF_PREVIEWS=1 renders PDF previews via Word.
  │     - BSH_MEMO_GENERATE_INTERNAL=1 runs the separate internal diligence
  │       memo Claude pass.
  │
  └── Emit terminal `done` (or `error`) on logs/stream.jsonl
```

## Inputs the memo skill consumes

**Always:**

- `data/settings/serena_background.md` — BSH investment thesis (Serena's
  voice + decision style + late-stage criteria).
- `data/companies.yaml` — the company's registry record (the entry whose
  `id` matches the slug). This carries description, sector, stage,
  status, exchange, founded year, website, key people, latest funding,
  total funding, latest earnings, products, competitors, recent news,
  notable contracts, notable acquisitions, and the Chinese translation
  block of all the above.

**Never:**

- `data/uploads/<slug>/` — that's the **Document Library** and belongs
  to a separate feature. The memo skill does not see it.
- Per-document summaries (the structured `summary` fields the Sparkle
  button writes onto upload records). Same reason.

**Planned but not built** (see the "Future feature" section in
[architecture.md](architecture.md)):

- A user-toggled subset of Document Library files marked "include as
  background for the memo." Off by default. Photo-heavy files and
  translated files are excluded from auto-suggestion.

## Fast Path vs. Legacy Path

The default path now uses real Python-orchestrated parallelism for the
independent analysis work. Each analysis pass is a narrow Claude subprocess
with a compact JSON schema. Python writes the markdown artifacts from those
structured results, then a synthesis/package subprocess drafts the English
source package and a final translation/package subprocess fills Simplified
Chinese.

This keeps wall-clock time closer to the slowest analysis pass plus synthesis,
rather than serializing all reasoning and writing behind one model stream.

The legacy single-subprocess skill remains available with
`BSH_MEMO_FAST_PIPELINE=0`. Keep it as a fallback for regressions or for
comparing output quality, but it is no longer the default latency path.

## Run-folder layout

```
data/memos/<slug>/<YYYY-MM-DD>__<HHMMSS>__<slug>__memo-run/
├── analysis/                  # produced by Claude/Python analysis passes
│   ├── fast/*.json             # default fast-path structured pass outputs
│   ├── claim_register.md
│   ├── pressure_tests.md
│   ├── time_base_checks.md
│   ├── growth_bridge.md
│   ├── distribution_notes.md
│   ├── disconfirming_evidence.md
│   ├── scenario_swim_lanes.md
│   ├── validation_log.md
│   ├── gating_questions.md
│   └── (optional) adoption_ladder.md, replacement_vs_coexistence.md,
│                  core_franchise_resilience.md, competitive_notes.md
├── memo/                      # rendered by server.memo_docx_renderer
│   ├── <Company> - Investment Memo - <run_id>.docx
│   ├── <Company> - 投资备忘录 - <run_id>.docx
│   └── (optional) memo_en.md, memo_zh.md (working drafts)
└── logs/
    ├── memo_package.en.json   # default fast-path English source package
    ├── memo_package.json      # renderer input package
    ├── run_manifest.md        # prep skeleton + renderer finalization
    ├── stream.jsonl           # progress events (used by SSE + active-jobs rail)
    ├── validation.txt         # renderer validation output (English)
    ├── validation_cn.txt      # renderer validation output (Chinese)
    ├── memo_chinese_parity.md # Chinese/English parity gate report
    ├── file_inventory.md      # renderer output inventory
    ├── previews/              # optional visual QA PNGs for the English memo
    └── previews_cn/           # optional visual QA PNGs for the Chinese memo
```

## Versioning

Every run gets its own folder. Same-second collisions append `__2`,
`__3`. Prior runs are never overwritten — Serena browses historic
versions by opening their folders. The report record in
`data/reports/<id>.yaml` carries `run_dir` so the UI can deep-link to
any prior run.

## What's in the report record

`data/reports/<id>.yaml` for a memo run carries:

- `kind: investment_memo_latestage`
- `company_id`, `company_name`
- `run_id`, `run_dir`, `skill`, `skill_version`
- `memo_files: [{language: en, path: ...}, {language: zh, path: ...}]`
- `status`, `stage`, `progress`, `created_at`, `updated_at`
- After completion: `content_en`, `content_zh` (one-screen previews),
  `validation`, `claude_cost_usd`, `claude_duration_ms`

## What Python contributes vs. what Claude contributes

**Python (this codebase):**

- Versioned run-folder creation + manifest skeleton (`memo_prep.py`).
- Scope check (late-stage / pre-IPO preferred; warn early-stage).
- Report record bookkeeping (`server/storage.py`).
- Orchestrating the default fast memo pipeline: parallel analysis
  subprocesses, English package subprocess, Chinese completion subprocess,
  and phase timing events (`server/memo_analysis.py`,
  `server/claude_runner.py`).
- Running the legacy single-subprocess memo skill when
  `BSH_MEMO_FAST_PIPELINE=0`.
- Stable DOCX rendering from `logs/memo_package.json`
  (`server/memo_docx_renderer.py`).
- Post-run verification: did Claude avoid generated renderer scripts, did
  the package pass schema validation, do the expected `.docx` files and
  renderer logs exist, and does the English memo pass the quality gate?
- Optional post-run conveniences:
  - `BSH_MEMO_RENDER_PDF_PREVIEWS=1` renders PDF previews. This can be slow
    because it automates Microsoft Word and has a per-DOCX timeout.
  - `BSH_MEMO_GENERATE_INTERNAL=1` runs a second Claude subprocess for the
    internal diligence memo. It is no longer part of the default critical path.

**Claude:**

- Fast path: runs narrow independent analysis passes, then a synthesis /
  English-package pass, then a Chinese-package pass.
- Legacy path: runs Serena's full skill in one subprocess.
- In both paths, Claude does not invoke renderers or write final `.docx` files.

If a memo run misbehaves, the first question is: is the failure on the
Python side (wrong inputs, missing run folder, scope check wrong) or on
the Claude side (skill ran but produced bad artifacts)? Each side has
its own diagnostics: Python errors land in the server log; Claude
errors land in `logs/stream.jsonl` and the run-folder artifacts.

## Scope check rules

`memo_prep._assess_stage()` reads the `companies.yaml` record and
decides:

- `status: nonprofit` → **fail** (out-of-scope).
- `exchange` set (publicly listed) → **pass** (treated as
  pre-IPO-equivalent for secondaries / PIPE).
- `latest_funding.round` matches a late-stage pattern (Series D+, Late,
  Growth, Pre-IPO, Secondary, IPO) → **pass**.
- `latest_funding.round` matches an early-stage pattern (Pre-Seed,
  Seed, Series A/B) → **warn**.
- `total_funding_usd >= $50M` → **pass** (late-stage signal).
- `total_funding_usd < $5M` → **warn** (early-stage signal).
- Otherwise → **warn** (pass with a warning; the skill verifies stage
  in its Section II).

Early-stage scope warnings continue into analysis and must be carried
as explicit stage-fit caveats in the memo. Hard scope failures, such as
nonprofit / out-of-scope records, preserve the run folder so the UI can
show the reason; no Claude invocation is spent.
