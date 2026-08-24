# BSH Research Center — Two-feature architecture

There are **two independent AI features** in the system. They share no
code paths, no run folders, no inputs. They do not invoke each other.

| | Document Library | Investment Memo |
|---|---|---|
| **Whose data** | The user's | Serena's |
| **Where files live** | `data/uploads/<slug>/` | `data/settings/serena_background.md` + `data/companies.yaml` record + optional `data/research/<slug>/` and approved Memo Studio packets |
| **User-facing surface** | Per-file Sparkle button inside the Library | "Generate Report → Investment Memo (Late-Stage)" or "Buffett Investment Memo" |
| **What it produces** | A structured per-document summary (bilingual exec summary, sections, key points) saved onto the file's record | Two `.docx` files (English + Simplified Chinese) saved into a versioned run folder under `data/memos/<slug>/<run_id>__<slug>__memo-run/memo/` |
| **Backend module** | `server/deck_summary.py` + the document-summary endpoints in `server/api.py` | `server/memo_prep.py` + `server/memo_analysis.py` (late-stage) or `server/buffett_memo_analysis.py` (Buffett) + the memo endpoints in `server/api.py` |
| **Runs Claude how** | One subprocess per uploaded file, page-by-page Read (configurable: granular or 8-page batch) | Default fast path runs eight narrow analysis subprocesses in parallel, then English package and Chinese package subprocesses. `BSH_MEMO_FAST_PIPELINE=0` restores the legacy one-subprocess Serena skill run. |

## Hard rules

1. **The memo skill never reads from `data/uploads/`.** The Document
   Library is the user's storage. The memo skill is Serena's flow.
   They are not the same library.

2. **The Sparkle button never produces inputs for the memo.** Sparkling
   a document and then generating a memo are two independent decisions.

3. **`memo_prep.py` does not stage any files into the run folder.** It
   creates the versioned run folder and a manifest, nothing else.

4. **Python owns orchestration and DOCX rendering, but not memo judgment.**
   In the default fast path, Python fans out independent Claude analysis
   subprocesses, writes compact artifacts from their structured outputs, then
   asks Claude for the English source package and Chinese completion package.
   In legacy mode (`BSH_MEMO_FAST_PIPELINE=0`), Serena's full skill runs in
   one subprocess. In both modes, Claude emits structured memo content and
   Python validates `logs/memo_package.json`, calls the tracked renderer
   (`server.memo_docx_renderer`), and creates both `.docx` files, validation
   logs, file inventory, and manifest finalization. Per-run renderer scripts
   such as `build_memo.py` are forbidden.

## Where Serena's "company folder" lives in this codebase

Serena's skill text refers to `[BSH Assistant]/[Company Name]/` — a
folder where Serena historically dropped PitchBook PDFs, partner
notes, CB Insights exports, and other research she wanted the memo to
read.

**In this codebase, Serena's folder lives at `data/research/<slug>/`.**
That folder is populated from the company **Files** list when **Use in
report** is on (the `UnifiedDocumentsView.vue` component); the backend
is `server/research_store.py`. Memo runs add this folder to Claude's
allowed read paths when it exists, and files there carry a per-doc quick
AI summary in their `index.yaml` row so the analyst can scan the library
without opening every file.

This folder is **distinct** from `data/uploads/<slug>/`:

| Folder | Owned by | UI surface | What lives here |
|---|---|---|---|
| `data/uploads/<slug>/` | the user | Files list with **Use in report** off + per-file Sparkle button | General per-company files (decks, PDFs) the user wants summarized in detail. **Never consumed by the memo flow.** |
| `data/research/<slug>/` | Serena | Files list with **Use in report** on | Research material the memo should read. Each file gets a *quick* AI summary (2–3 sentences + 3–5 bullets, single language). |

The memo skill consumes files from `data/research/<slug>/` when they are
present. It must continue to ignore `data/uploads/<slug>/`.

The skill should use the files' raw bytes (via normal Claude file reads
and local conversion helpers where needed), not their quick summaries.
The quick summary is a UI affordance for the analyst, not a memo input.
Re-reading the raw file keeps the memo faithful to the source instead of
summary-of-a-summary.

## Tracked seed data vs server-local generated data

The repository keeps runtime state under ignored `data/` paths, but curated
company records that must survive a GitHub checkout live in tracked seed files:

| Path | Owned by | Purpose |
|---|---|---|
| `server/seed_data/company_records.yaml` | Git-tracked product data | Curated company profile and PRD overview fields, including the ZaiNar v2 demo record. |
| `server/seed_data/company_fixtures.yaml` | Git-tracked QA data | Opt-in deterministic fixtures for Databricks, Stripe, NextNav, and empty company states. |
| `data/companies.yaml` | Server-local runtime data | Materialized company registry consumed by the API, memo generation, translations, trader snapshots, and local edits. |

Startup runs `local_generation.generate_local_runtime_state()`, which calls
`storage.bootstrap_seed_data()` and
`storage.materialize_seed_company_records()`. The materializer merges tracked
seed fields into `data/companies.yaml` so GitHub carries curated records while
the server still owns local generation.

The same startup path is available as an explicit local-generation command:

```sh
python -m server.local_generation
```

Use `python -m server.local_generation --include-fixture-companies` for QA
runs that need the fixture-company pack. Startup does not include fixture
companies by default.

The materializer may update seeded profile fields such as positioning, metrics,
team profiles, competitors, company news, industry view, disclosures, and other
PRD facts. It must preserve populated local generated fields including
`translation`, `trader_snapshot`, `memo_state`, and `audit_records`.

## Other AI surfaces (outside the two-feature contract)

The two features above are the ones bound by the hard rules. Several
other AI-driven surfaces exist and are deliberately independent of both:

- **Hormuz** (`server/hormuz_store.py`, `hormuz_prep.py`,
  `hormuz_analysis.py`, `hormuz_console.py`) — the Strait-of-Hormuz daily
  geopolitical research feature. Analysts upload date-organized source
  reports into `data/external/hormuz_research/sources/<date>/`; the
  appendix skill (`claude_runner.run_hormuz_appendix`) generates a
  bilingual (CN-first, EN-translated) appendix into
  `data/hormuz_appendix/<date>/`. The Hormuz Console is a chat scoped to
  the last two days of reports.
- **Trader snapshots** (`server/companies_ai_public.py`, trader endpoints
  in `api.py`) — per-public-company bilingual trading dashboards stored on
  the company record as `trader_snapshot`.
- **Weekly stocks** (`server/weekly_stocks.py`) — the weekly hot-stock
  dashboard: one scan pass, then per-stock verification passes. Payloads
  carry `scan_fallback` / per-stock `is_fallback` flags when the live scan
  or a verification pass failed; the frontend must render those as
  unverified content.
- **Stock research trackers + Hypothesis Lab** (`server/stock_research.py`,
  `hypothesis_store.py`, `hypothesis_cycle.py`) — recurring research
  trackers and the hypothesis→evidence→verdict cycle under
  `data/stock_research/`.
- **Company consoles** (`server/console_store.py`, `console_session.py`,
  console sections of `claude_runner.py`) — per-company interactive chat
  sessions with document staging, under `data/consoles/`.
- **Deep search** (`server/companies_ai.py`) — company search via the
  Claude CLI with WebSearch; cached per query in `data/cache/`.

"Serena" names the research-analyst persona whose memo/research flows the
Investment Memo feature implements; `serena_analysis.py` holds her
per-company research tools (thesis spine, benchmarks, chart specs, etc.)
with artifacts under `data/serena_analysis/`.

## Cross-feature checks the code must keep enforcing

- `server/memo_prep.py` must never import from or reference
  `server/files_store.py`, `data/uploads/`, or the upload index.
- `server/memo_analysis.py` and the memo prompt must never list
  `data/uploads/` as an accessible directory.
- The Document Library backend (`server/files_store.py`, deck-summary
  endpoints) must never know that a memo report exists for the
  company.

If a future change creates a coupling between the two, it's a defect.
