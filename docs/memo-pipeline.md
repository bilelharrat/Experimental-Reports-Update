# Investment Memo Pipeline

How "Generate Report" investment memos work. There are two Claude-backed
types:

- **Investment Memo (Late-Stage)** — BSH LP-facing late-stage / pre-IPO memo
- **Buffett Investment Memo** — first-person Buffett investment analysis and
  memorandum (Buy / Pass / Too Hard)

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
  voice + decision style + late-stage criteria). On a fresh checkout this
  is seeded from the Git-tracked `server/seed_data/serena_background.md`
  (`memo_prep.ensure_settings_file()`, run at startup and at memo prep);
  an existing local file always wins.
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
- `generated_with` — the engine, template, structure and the model that
  actually answered for each role (page one of the memo prints the line)
- `quality_metrics` — deterministic quality numbers computed at finalize
  (`server/memo_quality_metrics.py`): figures traced, over-cap sections,
  conflicting figures, repetition index, Chinese term drift
- `quality_warning_items` — one entry per warning, with its gate:
  `quality`, `chinese_parity`, `chinese_package`, `ic_memo`,
  `private_diligence`, `boundary`, `returns`, `pins` (a pinned sentence —
  the base case, the prior view — not echoed where its section contract
  puts it), `signposts`, `risk_cards`,
  `length` (a section delivered slightly over its word cap), `claims`
  (an evidence quote the cached page does not contain), `consistency`
  (the same metric with different values), `red_team` (a challenge the
  repair did not address), `cost` (the spend ceiling stopped the run)
- `pause_after_english` / status `english_ready_paused` — the run stopped
  after rendering the English so a reviewer can read it before the
  Chinese, artifacts and IC memo are paid for; the resume endpoint
  continues it
- `cost_ceiling_usd` — the per-run spend ceiling, when the request set one

Run-folder additions from the same work: `logs/glossary.json` (the
bilingual term list every translation call is held to),
`logs/evidence_quotes.json` (verbatim quotes the analysis passes recorded
per claim), `logs/red_team.json`, `logs/quality_metrics.json`, and
`.claude/settings.json` (the per-run sandbox: agents may read only the run
folder and the company's research folder).

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
- The returns arithmetic on the v2 pin sheet (`server/memo_returns.py`):
  exit values, MOIC and IRR recomputed; the probability-weighted MOIC; the
  walk-away price against the saved fund policy; and the partner's price
  questions — the exit value and exit-year revenue that return the money,
  clear the bar and return 3x at this price, the breakeven entry, the
  growth each case implies from the latest pinned revenue, the base-case
  IRR if the exit slips, and BSH's ownership, proceeds and share of the
  fund when the deal record carries a proposed check (and the reserves
  page a saved fund size). Each lands as a `[C#]` note and a pin-sheet
  line; the section contracts state them verbatim ("What has to be
  true"), and the IC memo copies them.
- The prior view (`memo_analysis.prior_view_for_report`): the company's
  most recent delivered memo of the same kind — verdict, score, entry mark
  and date, never its evidence — pinned as `shared_facts.prior_view_sentence`
  so the section that carries the recommendation (the decision section; the
  executive summary on the v1 template) and the IC memo state it and say
  what changed. A missing echo is a `pins` warning. `BSH_MEMO_PRIOR_VIEW=0`
  turns it off.
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

## Buffett Investment Memo

`POST /api/reports` with `report_type = "Buffett Investment Memo"` uses the
same prep handshake (`memo_prep.bootstrap_memo_run(..., report_type=...)`)
and the same run-folder / SSE / DOCX download surface. Differences:

- Report `kind` is `buffett_investment_memo`; the reader-facing label is
  "Buffett-Method Memo" / "巴菲特方法备忘录".
- Skill: `skills/memo/buffett.md` (loaded with `memo_prompts.load_prompt`),
  with the Chinese team's twin at `skills/memo/zh/buffett.md`.
- Worker: `server/buffett_memo_analysis.py` (one Claude subprocess, not the
  eight-pass late-stage fast pipeline). The run pins the share price and the
  10-year yield from live quotes (`BSH_BUFFETT_PIN_QUOTES`), requires a short
  web-research step, and captures what it reads into the source cache.
- Renderer: `server/buffett_memo_renderer.py` turns `logs/memo_package.json`
  markdown into both `.docx` files with the BSH frame (header, review stamp,
  "Page X of Y", disclaimer). Claude must not write Word files.
- Checks: `server/buffett_checks.py` (voice, stock phrases, valuation
  arithmetic, EN/ZH number parity, a report-only fact check). Findings are
  warnings; they never fail a run.
- Voice: BSH Research applying Buffett's owner framework, as a prospective
  buyer — never Buffett or Berkshire in the first person. It does not consume
  `data/settings/serena_background.md` as an investment thesis.
- The memo is still bilingual (English + Simplified Chinese).
- The decision is **Buy**, **Pass**, or **Too Hard**; a Pass records whether
  it is about the price or the business (`pass_kind`).

