# BSH Research Center v2 Context Transfer

Status date: 2026-07-02

Use this document to start a fresh, purpose-built implementation context for
the BSH Research Center v2 PRD work. It summarizes what was reviewed, where the
durable source references live, what has already been planned, and what the
next context should do first.

## Start Here

Read these files in order:

1. `AGENTS.md`
   - Critical repo rule: work directly on `main`; no worktrees and no feature
     branches.
2. `docs/bsh-research-center-v2-prd-development-plan.md`
   - Main tracker, checklist, milestone sequence, FR coverage, enhancements,
     and open questions.
3. `docs/reference/bsh-research-center-v2/README.md`
   - Durable reference-pack manifest and checksums.
4. `docs/reference/bsh-research-center-v2/BSH_Research_Center_PRD_by_SS.extracted.md`
   - Fast textual PRD reference.
5. `docs/reference/bsh-research-center-v2/BSH_Research_Center_Design_System_v2.extracted.md`
   - Fast textual design-system reference.
6. `docs/reference/bsh-research-center-v2/BSH_Research_Center_Home.extracted.md`
   - Fast textual Home/workspace mockup reference.
7. `docs/architecture.md`
   - Important current architecture boundary between Document Library and
     memo-input Background Documents.

## Durable References

The original reference files have been copied into:

`docs/reference/bsh-research-center-v2/`

Files saved there:

- `BSH_Research_Center_PRD_by_SS.docx`
- `BSH_Research_Center_PRD_by_SS.extracted.md`
- `BSH_Research_Center_Home.html`
- `BSH_Research_Center_Home.extracted.md`
- `BSH_Research_Center_Design_System_v2.html`
- `BSH_Research_Center_Design_System_v2.extracted.md`
- `README.md`

Do not depend on `/Users/rparker/Downloads` in future contexts.

## Work Completed In This Planning Context

- Extracted and reviewed the updated PRD dated July 1, 2026.
- Extracted and reviewed the Home HTML reference.
- Extracted and reviewed the Design System v2 HTML reference.
- Audited the current Vue/FastAPI app:
  - `frontend/src/router.js`
  - `frontend/src/App.vue`
  - `frontend/src/api.js`
  - `frontend/src/views/HomeView.vue`
  - `frontend/src/views/ResearchView.vue`
  - `frontend/src/components/Sidebar.vue`
  - `frontend/src/components/CompanyDetail.vue`
  - `frontend/src/components/CompanyLibrary.vue`
  - `frontend/src/components/ResearchUploads.vue`
  - `frontend/src/components/CompanyConsole.vue`
  - `frontend/src/components/MemoAnalysisDashboard.vue`
  - `server/api.py`
  - `server/storage.py`
  - `server/files_store.py`
  - `server/research_store.py`
  - `docs/architecture.md`
- Created the main implementation tracker:
  `docs/bsh-research-center-v2-prd-development-plan.md`.
- Re-audited the tracker for missed PRD/design items and patched in:
  - Product-success instrumentation.
  - Persona acceptance paths.
  - Explicit non-goal guardrails.
  - Browser-support QA.
  - Bucket `Show all` / `Show less` behavior.
  - Source Library and Appendix destination.
  - Design-system review rules.
  - Co-pilot bubble details and no-inline-chat rule.
  - Disconfirming-signal treatment.
- Re-checked the handoff for IA gaps and added the user decision that Hormuz
  and other incubated workflows move under an `Innovation Lab` section.

## Current App Snapshot

The app is not a blank slate. It already has:

- Vue 3 + Vite + Tailwind frontend.
- FastAPI backend.
- Login/session auth.
- Company search/autocomplete and deep AI search.
- Per-company route at `/:companyId`.
- Existing company tabs:
  - `Overview`
  - `Documents`
  - `Memo Studio`
  - `Console`
- Existing document flows:
  - Per-company Document Library under `data/uploads/<company>`.
  - Memo-input Background Documents under `data/research/<company>`.
  - External research upload/analysis/translation.
  - URL archive/summarization.
  - Hormuz/internal note flows.
- Existing incubated workflow surfaces:
  - Hormuz source library and detail routes.
  - Research pages: Market Pulse, Evidence Matrix, Hypothesis Lab.
  - These should be gathered under `Innovation Lab` rather than remaining
    standalone primary-rail sections.
- Existing memo flows:
  - Final memo generation.
  - Memo analysis sessions.
  - Research tasks.
  - Readiness gates.
  - Evidence matrix.
  - Generated DOCX/PDF artifacts.
- Existing public-market flows:
  - Stock Research dashboard.
  - Trader snapshots and stats.
- Existing global language state for EN/ZH, with incomplete coverage.

## Core Gap

The PRD v2 asks for a more opinionated product shell and a simpler
investor-facing Memo Studio than the current app exposes.

The current app has substantial underlying systems, but the PRD needs:

- Three-zone global shell:
  left rail, central content, global co-pilot drawer.
- PRD left rail:
  Quick Intake, company buckets, Market Radar, Stock entry, account/settings.
- PRD Home:
  search-first plus Quick Add.
- PRD company workspace tabs:
  Overview, Documents, Memo Studio, Company News, Industry Views.
- PRD Overview:
  monogram, tags, funding line, positioning frame, metric strip, team,
  products, competitors, investors/cap table.
- PRD Memo Studio:
  five visible memo sections, check/rank/expand cards, bullet edit,
  recursive Dive Deeper, Discuss to co-pilot, collapsed appendix, export
  respecting current state.
- PRD co-pilot:
  global slide-in panel, not a company tab.
- PRD evidence/provenance:
  every key figure source-linked or source-classed before export.
- BSH-specific incubated workflow home:
  `Innovation Lab` for Hormuz and experimental research tools, kept distinct
  from PRD core navigation, Source Library, and Memo Appendix.

## Multi-Pass Audit Results

This handoff and the tracker were rechecked against the PRD, Design System v2,
Home HTML reference, and current codebase on 2026-07-02.

Pass 1 - PRD and design coverage:

- The tracker covers all PRD functional requirements FR-1 through FR-14.
- The top-level milestone sequence matches the PRD milestone sequence:
  Foundations, Memo Studio, Evidence, Context, Polish.
- No top-level product area is missing from the tracker.
- The remaining risk is not missing scope; it is making each scope item
  concrete enough for implementation without re-litigating architecture.

Pass 2 - current frontend contracts:

- `frontend/src/App.vue` is the current authenticated chrome. It polls
  `api.listReports()`, `api.externalFeed()`, and `api.listHormuz()` every 4s
  only while authenticated, passes those rows into `Sidebar.vue`, and owns
  `ActiveJobsRail` plus `DeckSummaryModal`.
- Any `GlobalShell` refactor must preserve that auth-gated polling behavior.
  The login route should not start sidebar/feed polling or call protected
  `/api/*` endpoints.
- `frontend/src/router.js` currently defines `/`, `/login`, weekly/trader/stock
  routes, research-page routes, `/:companyId` with alias
  `/research/:companyId`, news/external-research/Hormuz routes, and no Settings
  or User Center routes.
- `frontend/src/views/ResearchView.vue` stores workspace tab state in
  `route.query.tab`; current values are `overview`, `documents`, `analysis`,
  and `console`. The PRD tabs should migrate this URL contract deliberately.
  Preserve `route.query.report`, which deep-links the active generated report.
- `frontend/src/views/HomeView.vue` already has autocomplete, AI deep-search
  SSE progress, Quick Add tools, stock refresh, trader stats, and full company
  regeneration controls. M1 should move non-PRD admin controls out of the first
  viewport without deleting working operations.
- The current Quick Add `Source Library & Appendix` link is the Hormuz source
  library, not the PRD company/memo Source Library and Appendix. Do not treat it
  as the final PRD destination without a deliberate rename or new route.

Pass 3 - current backend and data contracts:

- `server/api.py` exposes `CompanyOut` with basic company fields, products,
  `competitors` as `list[str]`, recent news, translation, and optional public
  `trader_snapshot`.
- `_company_view()` must be kept in sync with any new `CompanyOut` fields.
  Adding fields only to `data/companies.yaml` is not enough.
- `data/companies.yaml` already contains `zainar-inc`, but it is still shaped
  like the current app: basic people/products/news plus string competitors.
  It does not yet have typed metric cards, board/cap table records, cap-table
  lineage, typed competitors, expert opinions, source refs, disclosures, or
  memo editor state.
- `server/storage.py` is YAML-backed and has merge/upsert behavior for company
  search results. Schema extension should be backward-compatible and should not
  discard fields produced by AI search refreshes.
- Current report artifacts are versioned under `data/reports` and memo run
  output under `data/memos/<slug>/<run_id>__<slug>__memo-run/memo/`. The PRD
  memo editor state needs its own persisted state model instead of being
  inferred from generated DOCX/PDF files.

Pass 4 - source, document, and co-pilot boundaries:

- `data/uploads/<company>` and `server/files_store.py` are the user-facing
  Document Library.
- `data/research/<company>` and `server/research_store.py` are Serena's
  Background Documents for memo input.
- The co-pilot console can currently hydrate both background documents and
  library documents, but the memo pipeline must continue to ignore
  `data/uploads/<company>` unless a deliberate migration changes
  `docs/architecture.md`.
- The PRD Documents tab can unify presentation, but implementation should keep
  source purpose explicit through provenance/source-class metadata.
- Existing console routes live under `/api/companies/{company_id}/console/*`
  and support sessions, estimates, hydration streams, ask streams,
  attachments, archival, and deletion. The global co-pilot should adapt these
  routes rather than rebuilding session mechanics first.

Pass 5 - QA and acceptance coverage:

- The tracker already calls for frontend tests, backend tests, build, visual QA,
  browser coverage, persona paths, analytics, accessibility, and performance.
- The first implementation slice should add or update focused tests for shell
  routing, sidebar buckets, Home Quick Add, tab query migration, company schema
  rendering, and ZaiNar Overview partial-data fallbacks.
- Do not wait until M5 for source/provenance verification on M1 data surfaces:
  every new metric/source-class field added for Overview should render with an
  explicit source or a visibly incomplete/unknown state.

Pass 6 - Innovation Lab IA gap:

- The previous handoff correctly warned that the current Hormuz source library
  is not the PRD Source Library or Memo Appendix, but it did not say where
  Hormuz should live after the PRD rail is simplified.
- User decision: create an `Innovation Lab` section for incubated workflows.
- Move Hormuz/internal-note views and current experimental research pages
  (`Market Pulse`, `Evidence Matrix`, `Hypothesis Lab`) under Innovation Lab
  unless a workflow is explicitly promoted into PRD core IA.
- Preserve existing `/hormuz`, `/hormuz/:id`, and `/research-pages/*` routes as
  aliases or redirects during migration so existing links keep working.
- Innovation Lab is an organizing shell for experiments; it must not redefine
  the PRD Evidence/Appendix source model or couple `data/uploads` into memo
  generation.

## Architectural Cautions

- Work on `main`; do not create branches or worktrees.
- Do not couple `data/uploads/<company>` into the memo-generation flow without
  a deliberate architecture change.
  - `data/uploads/<company>` is the user-facing Document Library.
  - `data/research/<company>` is the memo-input Background Documents folder.
- The PRD Documents tab can present a unified user-facing surface while the
  backend keeps these two stores separate.
- Treat the existing `CompanyConsole` backend as a strong candidate for the
  global co-pilot, but do not simply keep Console as a tab; the PRD wants a
  drawer available from every view.
- Treat the existing `MemoAnalysisDashboard` as advanced/research tooling. The
  PRD needs a default investor-facing memo editor layer above or beside it.
- Existing `CompanyDetail.vue` is a compact dossier, not the PRD Overview.
- Existing company records are too thin for the full PRD. Add schema/backfill
  carefully so old records still render.
- Do not introduce transaction execution, fund administration, cap-table
  administration, or portfolio accounting. The PRD explicitly excludes those.

## Recommended Fresh-Context Goal

Start with milestone M1 from the tracker:

1. Design System v2 tokens and shell.
2. PRD left rail and Home Quick Add.
3. Innovation Lab destination for Hormuz and incubated research-page tools.
4. Company schema extension/backfill.
5. PRD Overview for ZaiNar.
6. Tab restructure with empty Company News and Industry Views placeholders.

The first fresh context should not try to build the full Memo Studio. It should
make the product shape match the PRD while preserving existing search,
documents, memo-generation, console, and stock-research behavior.

## Suggested First Implementation Slice

Scope:

- Add/adjust design tokens in `frontend/src/style.css` and
  `frontend/tailwind.config.cjs`.
- Replace current Space Grotesk / IBM Plex font aliases with the PRD Inter
  family and a mono alias for metrics, while keeping existing utility names
  such as `font-display`, `font-body`, `text-accent`, and `bg-surface`
  backwards-compatible where possible.
- Introduce a shell-level co-pilot drawer placeholder and floating button.
- Refactor the authenticated chrome into a shell component only if it preserves
  the current `App.vue` responsibilities: auth-gated polling, `RouterView`
  rendering, `ActiveJobsRail`, and `DeckSummaryModal`.
- Refactor `Sidebar.vue` toward PRD left rail structure:
  Quick Intake, company buckets, Market Radar, Stock, Settings/Profile.
- Add a frontend API wrapper for `GET /api/companies` if company buckets need
  the real company list. Do not infer Portfolio/Pipeline/Watchlist solely from
  recent report rows.
- Add an `Innovation Lab` rail entry or route destination for incubated works.
  Move Hormuz and existing research-page experiments there instead of keeping
  them as standalone primary sections.
- Refactor `HomeView.vue` to search-first plus Quick Add.
- Keep the working autocomplete, exact company selection, deep-search SSE
  progress, and result-card refresh behavior intact.
- Add route placeholders for Settings/User Center if needed.
- Declare new static routes in `frontend/src/router.js` so they cannot be
  confused with company ids in `/:companyId`.
- Add route/tab placeholders for Company News and Industry Views.
- Migrate `ResearchView.vue` tab query values intentionally. Preserve
  `?report=<id>` deep links and public-company behavior where Memo Studio is
  hidden or redirected.
- Keep existing `CompanyConsole` and `MemoAnalysisDashboard` functioning
  during the transition.
- Extend `CompanyOut`, `_company_view()`, `data/companies.yaml`, and tests
  together. ZaiNar Overview must render from real fixture fields, not HTML mock
  literals embedded in Vue components.

Likely files:

- `frontend/src/App.vue`
- `frontend/src/router.js`
- `frontend/src/style.css`
- `frontend/tailwind.config.cjs`
- `frontend/src/components/Sidebar.vue`
- `frontend/src/views/HomeView.vue`
- `frontend/src/views/ResearchView.vue`
- `frontend/src/views/HormuzLibraryView.vue`
- `frontend/src/views/HormuzResearchView.vue`
- `frontend/src/views/MarketPulseView.vue`
- `frontend/src/views/EvidenceMatrixView.vue`
- `frontend/src/views/HypothesisLabView.vue`
- `frontend/src/components/AddHormuzResearchTool.vue`
- New shell/co-pilot/settings/profile components as needed.
- `frontend/src/i18n.js`
- Relevant frontend tests under `frontend/tests/`.

Verification for first slice:

```bash
npm --prefix frontend test -- RouteSmoke.spec.js Sidebar.spec.js i18n.spec.js
npm --prefix frontend run build
git diff --check
```

Add broader tests as soon as new behavior stabilizes.

## Current Dirty Worktree Notes

Before this planning work, these files were already modified:

- `server/claude_runner.py`
- `server/memo_docx_renderer.py`
- `server/skills/bsh_investment_memo_latestage.md`
- `tests/test_memo_analysis.py`
- `tests/test_memo_docx_renderer.py`
- `tests/test_memo_prep.py`

This planning context did not modify those files.

New/modified planning/reference files from this context:

- `docs/bsh-research-center-v2-prd-development-plan.md`
- `docs/bsh-research-center-v2-context-transfer.md`
- `docs/reference/bsh-research-center-v2/README.md`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_PRD_by_SS.docx`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_PRD_by_SS.extracted.md`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Home.html`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Home.extracted.md`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Design_System_v2.html`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Design_System_v2.extracted.md`

## Commands Already Run

Reference extraction and validation:

```bash
git diff --check -- docs/bsh-research-center-v2-prd-development-plan.md docs/reference/bsh-research-center-v2
find docs/reference/bsh-research-center-v2 -maxdepth 1 -type f -print | sort
shasum -a 256 docs/reference/bsh-research-center-v2/* | sort
```

The diff-check passed after adding the plan and reference pack.

Current review note: these planning/reference files are still untracked, so
plain `git diff --check` does not show a useful tracked-file patch for every
new file. Use direct whitespace checks such as:

```bash
rg -n "[ \t]+$" docs/bsh-research-center-v2-context-transfer.md docs/bsh-research-center-v2-prd-development-plan.md
```

## Resolved IA Decision

- Hormuz is not a standalone primary navigation section in v2.
- Hormuz moves under `Innovation Lab`.
- `Innovation Lab` is the home for incubated workflows, including current
  research-page experiments unless a workflow is explicitly promoted into PRD
  core IA.
- Innovation Lab does not replace the PRD Source Library, Memo Appendix, or
  the `docs/architecture.md` split between Document Library and Background
  Documents.

## Open Questions To Carry Forward

The main tracker has the authoritative open-question list. The ones most
likely to affect early implementation are:

- Final label for internal-note ingestion:
  `Add Research`, `Add Internal Note`, or another name.
- Export targets for launch:
  DOCX only, PDF only, DOCX plus PDF, or shareable link.
- Whether PRD Documents should hide or expose the current backend split between
  Document Library and Background Documents.
- Source of truth and bucket rules for Portfolio/Pipeline/Watchlist.
- Whether public companies should hide Memo Studio, show it disabled, or get a
  public-equity variant.
- Whether Settings/User Center should be real for launch or initially backed
  by placeholder Enterprise account data.

## Definition Of Done For M1

M1 is complete when:

- The app shell visually and structurally matches the PRD:
  left rail, central content, header, co-pilot drawer frame.
- Home is search-first with Quick Add directly under the search box.
- The left rail uses PRD company buckets and Quick Intake.
- The company workspace has the PRD five-tab structure.
- Existing Hormuz and research-page experiments remain reachable through
  Innovation Lab, with legacy routes preserved during migration.
- ZaiNar Overview can render from real app data with no hardcoded mock-only
  sections.
- Existing search, documents, memo generation, console, stock research, auth,
  and active-jobs behavior still work.
- Focused frontend tests and build pass.
- `git diff --check` passes.
