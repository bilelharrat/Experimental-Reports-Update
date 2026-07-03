# BSH Research Center v2 Context Transfer

Status date: 2026-07-03

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
- Implemented and validated the M1 foundation slice:
  - Design System v2 token/theme foundation.
  - Authenticated global shell with header, PRD left rail, active jobs, and
    co-pilot drawer frame.
  - Home search-first layout with Quick Add directly under search.
  - Innovation Lab entry for Hormuz and research-page experiments, while
    preserving legacy `/hormuz` and `/research-pages/*` routes.
  - Company schema/API extensions for PRD Overview fields.
  - ZaiNar Overview rendered from real company data rather than hardcoded Vue
    mock literals.
  - PRD five-tab company workspace with Company News and Industry Views
    placeholders.
  - Focused route/sidebar/i18n/schema tests plus frontend build and manual
    browser screenshot QA.
- Added Git-persistent company data and server-local materialization:
  - `server/seed_data/company_records.yaml` carries curated product seed
    records, including ZaiNar.
  - `server/seed_data/company_fixtures.yaml` carries opt-in QA fixtures for
    Databricks, Stripe, NextNav, and empty-state testing.
  - `server.local_generation` materializes tracked seed data into ignored
    `data/` runtime files and is used by startup.

## Current App Snapshot

The app is not a blank slate. It already has:

- Vue 3 + Vite + Tailwind frontend.
- FastAPI backend.
- Login/session auth.
- Company search/autocomplete and deep AI search.
- Per-company route at `/:companyId`.
- PRD company tabs:
  - `Overview`
  - `Documents`
  - `Memo Studio`
  - `Company News`
  - `Industry Views`
- Existing document flows:
  - Per-company Document Library under `data/uploads/<company>`.
  - Memo-input Background Documents under `data/research/<company>`.
  - External research upload/analysis/translation.
  - URL archive/summarization.
  - Hormuz/internal note flows.
- Existing incubated workflow surfaces:
  - Hormuz source library and detail routes.
  - Research pages: Market Pulse, Evidence Matrix, Hypothesis Lab.
  - These are now gathered under `Innovation Lab`; legacy routes are preserved.
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
- Existing global language state for EN/ZH, with incomplete coverage on later
  PRD surfaces.
- Tracked company seed data under `server/seed_data/`, materialized into
  ignored `data/companies.yaml` on startup or via:

```bash
python -m server.local_generation
```

## Remaining Core Gap

The M1 shell/data foundation is in place, and the needed M2 Memo Studio
foundation now exists. The remaining PRD gap is turning the foundation into a
complete investor workflow:

- PRD Memo Studio integration:
  durable editor state, five visible sections, check/rank/expand cards, bullet
  edit, recursive Dive Deeper, Discuss to co-pilot, collapsed appendix, and
  guarded export projection exist under `data/memo_editor/<company_id>/`.
  The remaining M2 integration gap is final DOCX/PDF memo-run consumption of
  the PRD editor projection.
- PRD co-pilot actioning:
  the drawer frame exists; it still needs context injection from memo
  sections/cards/bullets and task acceptance back into Memo Studio.
- PRD evidence/provenance:
  every key figure source-linked or source-classed before export.
- PRD Documents:
  one user-facing grouped Documents tab with provenance/source classes, while
  preserving the backend split between Document Library and Background
  Documents.
- PRD Company News, Industry Views, and Competitor detail:
  placeholders/data fields exist; full aggregation, filters, comps, signals,
  and detail routes remain to build.
- Settings/User Center:
  routes/placeholders exist; real preference/account/usage backing remains.

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

- `frontend/src/App.vue` now owns the authenticated shell, header/breadcrumbs,
  left rail, active jobs, modal layer, and co-pilot drawer frame. It must keep
  auth-gated polling and keep `/login` chrome-free.
- `frontend/src/router.js` now includes Settings/User Center, Source Library,
  Innovation Lab, Innovation Lab research-page routes, and legacy aliases for
  Hormuz/research-page deep links.
- `frontend/src/views/ResearchView.vue` exposes PRD tabs:
  `Overview`, `Documents`, `Memo Studio`, `Company News`, and `Industry Views`.
  It maps legacy `?tab=analysis` to Memo Studio and uses the co-pilot drawer
  path for legacy console intent. Preserve `?report=<id>` deep links.
- `frontend/src/views/HomeView.vue` is search-first with Quick Add under the
  search box. Operations/admin controls live below the first viewport.
- The current `Source Library & Appendix` destination is a placeholder route,
  not the finished PRD Memo Appendix or evidence source model.

Pass 3 - current backend and data contracts:

- `server/api.py` `CompanyOut` and `_company_view()` now expose PRD Overview
  fields: positioning, metrics, team profiles, typed-or-legacy competitors,
  board/investors, cap-table lineage, company news, industry view, expert
  opinions, disclosures, memo state, and audit records.
- `server/storage.py` now preserves typed competitor records during search
  refreshes and materializes Git-tracked company seed data into local runtime
  storage without overwriting populated generated fields such as translation,
  trader snapshots, memo state, or audit records.
- `data/companies.yaml` remains ignored runtime data. Curated company records
  that must persist through Git belong under `server/seed_data/`.
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
- The next implementation slice should add durable backend tests for memo
  editor state, ranking, edits, nested Dive Deeper children, Discuss context,
  and export projection. Add focused frontend tests for the PRD Memo Studio
  editor once the component surface exists.
- Do not wait until M5 for source/provenance verification on memo data
  surfaces: every key figure in Memo Studio and export should render with an
  explicit source/source class, or export should block with a clear reason.

Pass 6 - Innovation Lab IA:

- User decision is implemented: Hormuz and current experimental research pages
  (`Market Pulse`, `Evidence Matrix`, `Hypothesis Lab`) live under Innovation
  Lab.
- Existing `/hormuz`, `/hormuz/:id`, and `/research-pages/*` routes are
  preserved as aliases during migration so existing links keep working.
- Innovation Lab remains an organizing shell for experiments; it must not
  redefine the PRD Evidence/Appendix source model or couple `data/uploads` into
  memo generation.

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

Start with M3 Evidence. M1 is complete enough to stop spending new work on
shell/IA foundations unless a regression is found, and M2 now has the durable
editor/export-projection foundation needed for evidence work.

## Remaining Implementation Plan

1. M3 Evidence and Documents:
   build one grouped Documents tab over the existing two backend stores; add
   source classes, provenance badges, category editing, source trace drawer,
   intake assignment, unresolved queue, and key-figure source enforcement.
2. M4 Context:
   complete Company News aggregation/filtering, Industry Views with expert
   opinions/comps/signals, competitor detail routes, and public-market comp
   integration.
3. M5 Productization:
   back Settings/User Center with real or clearly scoped placeholder adapters;
   add role/permission checks, audit/version replay, product analytics,
   accessibility, responsive QA, performance checks, and visual regression.

Recommended immediate next slice:

- Implement M3 Evidence foundations on top of `server/memo_editor_store.py` and
  the PRD-facing Memo Studio editor.
- Build one grouped Documents tab while preserving `data/uploads/<company>` /
  `server/files_store.py` and `data/research/<company>` /
  `server/research_store.py` separation.
- Add source-class/provenance editing, source trace drawer, intake assignment,
  unresolved queue, dedupe, and document-backed source guardrails.
- Keep existing memo generation/DOCX/PDF paths intact until the PRD editor
  projection is deliberately wired into memo-run input.

Required validation for the next slice:

```bash
python -m pytest tests/test_memo_editor_store.py tests/test_memo_analysis.py
npm --prefix frontend test -- MemoStudioEditor.spec.js RouteSmoke.spec.js i18n.spec.js
npm --prefix frontend run build
git diff --check
```

## Current Dirty Worktree Notes

As of 2026-07-03, the active uncommitted work is the seed/local-generation and
documentation slice:

- `README.md`
- `docs/architecture.md`
- `docs/bsh-research-center-v2-prd-development-plan.md`
- `docs/bsh-research-center-v2-context-transfer.md`
- `frontend/src/i18n.js`
- `server/main.py`
- `server/storage.py`
- `frontend/tests/AppShell.spec.js`
- `frontend/tests/HomeView.spec.js`
- `server/local_generation.py`
- `server/seed_data/company_records.yaml`
- `server/seed_data/company_fixtures.yaml`
- `tests/test_company_seed_data.py`
- `tests/test_local_generation.py`

## Commands Already Run

Reference extraction and validation:

```bash
git diff --check -- docs/bsh-research-center-v2-prd-development-plan.md docs/reference/bsh-research-center-v2
find docs/reference/bsh-research-center-v2 -maxdepth 1 -type f -print | sort
shasum -a 256 docs/reference/bsh-research-center-v2/* | sort
```

M1 and local-generation validation:

```bash
python -m pytest tests/test_local_generation.py tests/test_company_seed_data.py tests/test_company_schema_v2.py tests/test_storage_company_type.py
npm --prefix frontend test -- RouteSmoke.spec.js Sidebar.spec.js i18n.spec.js
npm --prefix frontend run build
git diff --check
```

Direct whitespace checks for planning docs and seed files:

```bash
rg -n "[ \t]+$" README.md docs/architecture.md docs/bsh-research-center-v2-context-transfer.md docs/bsh-research-center-v2-prd-development-plan.md server/seed_data/company_records.yaml server/seed_data/company_fixtures.yaml
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

## M1 Status

M1 is complete and validated. Use the remaining milestones above as the working
plan unless a regression is found in shell, Home, left rail, Innovation Lab,
company schema, ZaiNar Overview, or route compatibility.
