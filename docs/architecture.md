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
| `server/seed_data/serena_background.md` | Git-tracked product data | Default analyst background (`memo_prep.ensure_settings_file()` copies it to `data/settings/serena_background.md` at startup and at memo prep when no background exists), so a fresh checkout can generate memos immediately. A locally present background is never overwritten. |
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
- **Team dossier** (`server/founder_dossier.py`) — the Research Desk Team
  tab. Two layers: a record layer that reshapes people already on the
  company record, and a research layer (the Refresh button) that runs a
  web-grounded pass and fills in the blanks. Cached under
  `data/founder_dossiers/`; reads replay the cache and never call a model.
- **Company news sweep** (`server/company_news_research.py`) — the refresh
  behind the company news feed. Appends genuinely new rows to the record's
  `recent_news`, which `context_store.company_news` already assembles.

## The second engine: Gemini Flash

Most AI surfaces shell out to the `claude` CLI (`server/claude_runner.py`),
which spends the user's Claude Code subscription. Three surfaces do not:

| Surface | Module | Why Gemini |
|---|---|---|
| Team dossier refresh | `founder_dossier.py` | Web-grounded, needs machine-readable source URLs |
| Morning Brief written note | `market_brief.py` | Short, frequent, no tools needed |
| Company news sweep | `company_news_research.py` | Web-grounded, needs source URLs |
| Story briefings | `news_brief.py` | Highest-frequency call in the app; no tools needed |
| Memos and reports | `memo_engine.py` | Opt-in per run only — see below |

`server/gemini_runner.py` is the backend — the Gemini `generateContent`
REST API over `httpx`, no new dependency. It mirrors
`claude_runner.run_structured_prompt`'s `(data, error)` contract, and adds
`run_grounded_json` for Google Search-grounded calls that return the
sources the model read.

Two things about the Gemini API that are not guessable and cost real time
to rediscover, both measured against the live API:

1. **A grounded call must not set `responseSchema`.** Combining it with the
   `google_search` tool makes the response come back with an *empty*
   `groundingMetadata` — no chunks, no queries — so every source URL is lost
   and a researched answer is indistinguishable from unsourced recall.
   `run_grounded_json` therefore puts the schema in the prompt instead.
2. **A grounded call is two calls, and must stay that way.** Whether the
   model calls `google_search` is its own decision, and asking for a search
   and schema JSON in one request measured only 2 grounded responses in 5:
   a long schema-carrying prompt reads as a formatting task, so it answers
   from memory. Retrying does not help (resampling three times measured the
   same 2/5 — the decision is sticky per prompt, not random per call), but
   removing the schema does. `run_grounded_json` therefore researches in
   prose with the search tool and no schema, then converts those notes to
   the schema in a second ungrounded, tool-less call. That took the weekly
   scan and the founder dossier from 0/1 and 2/5 to 3/3 each.

   `BSH_GEMINI_GROUNDED_THINKING` (default `medium`) still matters for the
   research step; `low` and `high` both ground far less often.

   `meta["grounded"]` reports whether any search actually ran. Callers must
   keep honouring it — `founder_dossier` keys `is_deep_audited` off the
   source list, and `weekly_stocks` treats an ungrounded scan as a failed
   one, because "this week's movers" answered from memory is stale data
   wearing this week's confidence.

`response_schema` also takes an OpenAPI-flavored subset of JSON Schema and
400s on keywords outside it (`additionalProperties`, which our Claude-era
schemas all carry), so `gemini_runner` strips those before sending.

### Memos are the exception

The memo pipeline does not use `ai_engine`. Every stage — the parallel
analysis passes, the English spine, the bilingual package, every repair
pass — funnels through `claude_runner._run_memo_local_json_artifact`, which
spawns a Claude CLI subprocess with `--add-dir` and `Read,Bash,Grep,Glob`:
the prompts hand the agent a *listing* of the company research folder and
expect it to open those files itself.

`server/memo_engine.py` adds a per-run toggle at that one funnel, so a
Gemini memo runs the same stage graph, prompts, schemas, retries, repair
passes, validation and DOCX renderer as a Claude one. Only two things
differ, and both are consequences of Gemini having no filesystem:

- Research is extracted to text and inlined into the prompt, ordered
  digests-first, with every truncation and omission named in the text so a
  shortened source is never read as a complete one.
- A scanned PDF with no text layer contributes nothing, where a Claude
  agent could still have described the pages it read.

One thing is added, for the mirror-image reason: Gemini writes shorter
than Claude on identical prompts (the ZaiNar wave came back at 7,695
English words against the 12,202 and 12,212 of the benchmarked Claude
runs). The late-stage editorial prompts under `skills/memo/` carry no word
targets — Claude never needed one — so the target lives on the engine that
does. `memo_engine` tells each Gemini section worker the length its Claude
twin writes (the Round-2 reference split across the sections;
`BSH_MEMO_GEMINI_WORDS` moves the total, 0 disables it), and a
deterministic gate after the section wave sends any section outside its
band back to its worker with the draft to revise, three rounds at most. The
gate works in both directions, because Gemini misses the length either
way: under the contract the first live run came back a quarter over
(13,958 English words), and a renderer-validation retry inflated the same
sections to 18,084. A revision is kept only when it lands closer to the
band than the draft it replaces.

The monolithic pass is not a fallback on Gemini, for the same reason: one
response cannot carry the memo, so degrading to it would deliver a memo a
quarter the length without saying so. A Gemini spine or section that fails
draws a second sample — nearly always sampling noise, a dropped or doubled
bracket in 26KB of JSON, which `gemini_runner` also repairs from the
decoder's own position — and if that fails too the run stops and says why.
Claude keeps its single attempt and its fallback, where the monolithic
pass carries the full memo.

The spine and section handoffs — the model writing its parts to files on
disk and returning a receipt — are off for the same reason: a Gemini run
keeps the inline contracts, and the compact Chinese method, whatever the
operator's flags say for Claude. Claude prompts are byte-identical to before; profiles that carry
their own ranges (growth, early, late v2) are read as written, and the
compact profile's ceilings are left alone.

The engine is pinned per run (like the quality tier) *and* stored on the
report record, so a resume or repair pass after a restart uses the engine
the memo was started with rather than the current default. Claude stays the
default: a memo is the most expensive and most scrutinised artifact here,
so moving one to another model is an explicit per-run choice, never
something an env default does quietly.

`server/ai_engine.py` owns the policy (`BSH_AI_ENGINE`) for the other
surfaces, and this is the
part to keep enforcing: **the fallback is never silent.** Every call
returns a `meta` dict naming the engine that produced the answer and why
Gemini was skipped, and each call site persists it — `note.engine` on the
desk note, `sweep.engine` on the news feed, `engine` on the dossier. A
Claude-fallback dossier also may not set `is_deep_audited`, because the CLI
path returns no machine-readable sources to evidence the audit with. A
change that drops that provenance is a defect: it turns a degraded answer
into one that looks normal.


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

## Retrieved-source cache and fact check (2026-09-20)

Memo facts used to enter a run through one hand-written registry entry,
three optional digests in the research folder, and whatever each analysis
pass happened to retrieve from the web — retrieval nothing logged, cached
or verified (the "fact lottery" in `docs/memo-benchmarks.md`). Two modules
close that:

- `server/source_cache.py` — every WebFetch/WebSearch result a memo run's
  agents see, and the research prose of every grounded Gemini sweep, is
  written to `data/research/<slug>/sources/` (index + one text file per
  content hash, deduped on canonical URL) and frozen in the run's
  `sources/manifest.jsonl`. `known_sources.md`, rendered from the cache,
  is injected into the analysis passes and the spine like the fact
  ledger. The API exposes it at `GET /api/companies/{id}/source-cache`.
- `server/memo_fact_check.py` — a deterministic gate beside the pin check:
  every figure the English package states is traced to a source on file
  (ledger, research documents, registry entry, cache, run sources, firm
  records — never model output), with one rounding step of tolerance
  across spellings ("$2.6B" is carried by "$2,580 million"). Results:
  `logs/fact_check.{md,json}`, the report's `memo_fact_check` field,
  `GET /api/reports/{id}/fact-check`, and the research desk's numbers
  card (`numbers_lint.lint` now delegates here). Unsupported figures are
  fed to the surgical repair only when the corpus is rich enough
  (`BSH_MEMO_FACT_CHECK_REPAIR`, default `auto`).

The fact ledger itself is editable from the research desk (Files tab) and
at `GET/PUT /api/companies/{id}/fact-ledger`; a run without one emits
`memo_fact_ledger_missing`. Package sources retrieved from the web must
carry their URL (`BSH_MEMO_SOURCE_URL_REQUIRED`); before validation the
pipeline attaches URLs the analysis passes or the cache already recorded.

