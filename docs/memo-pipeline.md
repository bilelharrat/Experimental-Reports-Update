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
  ├── Spawn one Claude subprocess via claude_runner.run_investment_memo()
  │   Prompt = Serena's skill text + fixed renderer contract + a
  │   parallel-tool-call hint for the 8 orthogonal passes.
  │   Tools: Read, Write, Edit, Bash, Grep, Glob.
  │
  │   Claude itself:
  │   - Reads Serena_Background.md  (BSH thesis)
  │   - Reads the companies.yaml entry for this company
  │   - Runs the 8 orthogonal analytical passes in parallel via batched tool
  │     calls — writes analysis/*.md as it goes
  │   - Writes the synthesis artifacts (claim register, scenarios, gating
  │     questions, pre-mortem, reverse IC, validation log)
  │   - Writes logs/memo_package.json as structured memo data
  │
  ├── On Claude exit:
  │     If returncode != 0 → mark report failed_during_analysis
  │     Else block generated render scripts like build_memo.py
  │     Else validate logs/memo_package.json
  │     Else Python runs server.memo_docx_renderer
  │     Else verify the two .docx files, validation logs, file inventory,
  │     and manifest renderer marker exist → continue post-run gates
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

## Why a single Claude subprocess instead of N

Serena's `bsh-investment-memo-latestage` skill is a coherent script. It
reads inputs, runs analyses, writes artifacts, renders `.docx`,
validates. Splitting it into N Python-orchestrated subprocesses means
rewriting Serena's script in pieces — which lost fidelity and merged
in concepts from the Document Library (we tried this; it was wrong).

The script's analytical passes are naturally parallelizable because the
**8 orthogonal passes have no inter-dependencies**. We exploit that by
adding one instruction to the prompt: "issue the eight orthogonal
passes via parallel tool calls in a single response." Claude executes
them concurrently inside its own process.

## Run-folder layout

```
data/memos/<slug>/<YYYY-MM-DD>__<HHMMSS>__<slug>__memo-run/
├── analysis/                  # produced by the skill
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
├── memo/                      # produced by the skill
│   ├── <Company> - Investment Memo - <run_id>.docx
│   ├── <Company> - 投资备忘录 - <run_id>.docx
│   └── (optional) memo_en.md, memo_zh.md (working drafts)
└── logs/
    ├── run_manifest.md        # prep writes skeleton; skill appends finalization
    ├── stream.jsonl           # progress events (used by SSE + active-jobs rail)
    ├── validation.txt         # skill's docx validate.py output (English)
    ├── validation_cn.txt      # skill's docx validate.py output (Chinese)
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
- Spawning one Claude subprocess and translating its stream-json output
  into our progress events (`server/claude_runner.py`).
- Stable DOCX rendering from `logs/memo_package.json`
  (`server/memo_docx_renderer.py`).
- Post-run verification: did Claude avoid generated renderer scripts, did
  the package pass schema validation, do the expected `.docx` files and
  renderer logs exist, and does the English memo pass the quality gate?

**Claude (running Serena's skill):**

- All analytical work (the 8 orthogonal passes, synthesis, etc.).
- Reading inputs.
- Producing `logs/memo_package.json` as structured memo content.
- Not invoking renderers or writing final `.docx` files.

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
