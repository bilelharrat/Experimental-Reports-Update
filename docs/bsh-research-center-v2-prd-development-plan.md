# BSH Research Center v2 PRD Development Plan

Status date: 2026-07-02

This tracker translates the July 1, 2026 PRD, the Home HTML reference, and
Design System v2 into an implementation plan for the current Vue/FastAPI app.
Use it as the working checklist. Mark items complete only after the listed
implementation and verification both pass.

## Source Review

Reviewed inputs:

- `docs/reference/bsh-research-center-v2/BSH_Research_Center_PRD_by_SS.docx`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_PRD_by_SS.extracted.md`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Home.html`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Home.extracted.md`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Design_System_v2.html`
- `docs/reference/bsh-research-center-v2/BSH_Research_Center_Design_System_v2.extracted.md`
- Current app routes, components, API client, FastAPI routes, storage models,
  docs, and sample company data in this repository.

The durable reference copies above replace the original
`/Users/rparker/Downloads` paths for future implementation contexts.

Current relevant app state:

- [x] App runs as Vue 3 + Vite + Tailwind frontend with FastAPI backend.
- [x] Auth/session flow exists with `/login`, `/api/auth/token`, and bearer
      protected API calls.
- [x] Global sidebar exists, but it is an older report/news/research-page rail,
      not the PRD v2 gradient rail with Quick Intake and company buckets.
- [x] Home search supports autocomplete, deep AI search, company selection, and
      progress streaming.
- [x] Per-company workspace exists at `/:companyId`.
- [x] Existing workspace tabs are `Overview`, `Documents`, `Memo Studio`, and
      `Console`.
- [ ] PRD workspace tabs are not yet implemented as `Overview`, `Documents`,
      `Memo Studio`, `Company News`, and `Industry Views`.
- [x] Per-company document uploads, research/background uploads, file previews,
      summaries, external research uploads, link capture, and Hormuz notes exist.
- [ ] Hormuz and current research-page experiments are not yet grouped under
      the user-decided `Innovation Lab` home for incubated workflows.
- [x] Memo generation, memo analysis sessions, readiness gates, evidence matrix,
      research tasks, and DOCX/PDF artifacts exist.
- [ ] PRD Memo Studio editor behavior is not yet implemented as five visible
      memo sections with checkable/rankable/expandable highlights and risks.
- [x] Company records include basic profile fields, products, key people,
      recent news, latest funding, translations, and public ticker snapshots.
- [ ] Company records do not yet have the richer PRD structures for board/cap
      table, typed competitors, expert opinions, source classes, disclosures,
      company news tags, memo-card state, and audit history.
- [x] EN/ZH global language state exists.
- [ ] Localized coverage is incomplete for new PRD surfaces and AI-generated
      outputs are not consistently tied to the active language.
- [ ] Product-success instrumentation for the PRD targets is not yet defined:
      time to first memo, source-linked memo coverage, WAU by licensed seat,
      co-pilot task acceptance, and section reuse versus regeneration.
- [ ] Persona-specific acceptance paths are not yet encoded in tests or QA:
      VC Partner, Investment Analyst, and Research/Ops.

Progress key:

- `[x]` done in the current app or completed after this plan was created.
- `[ ]` still required. If an item says "Partial", some foundation exists but
  the PRD behavior is not complete.

## Set Of Changes Needed

These are the major deltas between the PRD/design references and the current
codebase.

1. Re-skin the app to Design System v2.
   Replace the current blue-accent theme with the pearl/slate/Tiffany system,
   signature left-rail gradient, Inter-only typography, monospaced metrics, and
   PRD component styles.

2. Rebuild global IA around the three-zone shell.
   The product needs a persistent 288px left rail, central content, and a
   372px slide-in co-pilot panel available from every view.

3. Replace the current sidebar content model.
   The rail should prioritize logo, Quick Intake, company buckets
   (Portfolio/Pipeline/Watchlist or Top Players), Market Radar, Stock entry,
   Settings, and account access. Recent reports/news can move into the relevant
   company, documents, or source-library views.

4. Add an Innovation Lab for incubated workflows.
   Hormuz and experimental research-page tools should move out of standalone
   primary navigation into an `Innovation Lab` section. This keeps PRD core IA
   clean while preserving incubated work until it is promoted, retired, or
   folded into a core workflow.

5. Refocus Home on search plus Quick Add.
   Keep existing autocomplete/deep-search capabilities, but remove admin-like
   primary controls from the first viewport and add the PRD Quick Add cards
   directly under the search field.

6. Normalize intake into one source-ingestion pipeline.
   Link, external research upload, and internal note creation must archive,
   summarize, translate when needed, infer the relevant company, assign a
   document category, preserve provenance, and make facts available to Memo
   Studio and the co-pilot.

7. Rework company workspace tabs and default landing.
   Current `analysis` and `console` tabs should become PRD `Memo Studio` and a
   global co-pilot panel. Add `Company News` and `Industry Views`.

8. Enrich the company profile data contract.
   Add fields for positioning-summary template parts, ARR/growth/valuation/TAM
   metrics, team bios/links, product detail pages, typed competitor cards,
   board/lead investors, cap-table lineage, expert opinions, sector metrics,
   sector signals, and disclosure/source metadata.

9. Build the PRD Overview surface.
   Current `CompanyDetail.vue` is a compact collapsible dossier. The PRD needs
   a richer first-screen profile with monogram, tags, funding line, positioning
   frame, metric strip, core team, products grid, competitors grid, and
   investors/cap table.

10. Reconcile Documents with existing dual libraries.
   Current architecture intentionally splits `data/uploads/<company>` from
   `data/research/<company>`. The PRD wants one user-facing Documents view
   grouped by category and provenance. Keep the backend boundary if needed, but
   present a coherent document system.

11. Add the flagship Memo Studio editor layer.
    Keep existing memo-analysis tooling as an advanced/research layer, but add
    the PRD user-facing memo editor: five sections, live progress, first-time
    generate/latest-version behavior, check/rank/expand cards, bullet actions,
    collapsed appendix, and export respecting inclusion/rank state.

12. Convert Console into the global co-pilot UX.
    Reuse the existing console/session backend where practical, but expose it
    as a context-aware slide-in panel. `Discuss` and `Dive Deeper` actions must
    pipe current company/section/bullet context into the panel.

13. Add Company News.
    The current recent-news field and external feed need a company-specific
    reverse-chronological view with source, category, recency, tags, filters,
    and safe external links.

14. Add Industry Views and Expert Opinions.
    Add sector metric strip, Notable Voices with stance chips, public comps
    with sparklines, and sector signal cards.

15. Add Competitor/Comps detail routes.
    Competitor cards should open a dedicated detail view with profile,
    head-to-head comparison, benchmark placeholder, win/loss placeholder, and
    patent-overlap placeholder.

16. Add Settings and User Center routes.
    The PRD requires dedicated account, workspace, preferences, usage/status,
    and profile views reachable from the header/account area.

17. Complete app-wide i18n behavior.
    Every UI label and new surface needs EN/ZH dictionary entries. Generated
    summaries and ingested research must be summarized/translated according to
    the selected language while preserving source language/provenance.

18. Add auditability and provenance to PRD-level interactions.
    Track include/exclude, rank order, edits, nested dive-deeper points,
    conclusion selection, exports, source classes, and disclosures per memo
    version.

19. Harden accessibility, responsiveness, performance, and tests.
    Keyboard support, focus states, contrast, warm-cache view load time,
    streaming progress, and browser visual QA need explicit coverage.

20. Add product analytics for PRD success metrics.
    The PRD defines measurable launch outcomes, but the current plan needs
    instrumentation and reporting for those targets.

21. Preserve PRD non-goals explicitly.
    The product may display fund, cap-table, market, and public-company context,
    but v2 must not become portfolio accounting, cap-table administration,
    trade execution, wire/fund movement, or transaction automation.

## Comprehensive Development Checklist

### 0. Operating Rules

- [x] Work directly on `main`; do not create worktrees or feature branches.
- [ ] Keep this tracker updated as slices land.
- [ ] Do not disturb unrelated modified files unless the active slice requires
      it.
- [ ] Preserve the existing memo/document backend boundary until a deliberate
      migration plan replaces it.
- [ ] Add tests with each slice; do not defer all QA to the end.

### 1. Design System v2 Foundation

- [ ] Replace `frontend/src/style.css` tokens with PRD variables:
      `--bg-base`, `--surface`, `--surface-alt`, `--ink`, `--muted`,
      `--muted-2`, `--border`, `--border-2`, `--tiffany`,
      `--tiffany-dark`, `--tiffany-light`, `--coral`, `--coral-light`,
      `--amber`, `--mint`, `--shadow`, `--shadow-hover`, `--rail-grad`.
- [ ] Update `frontend/tailwind.config.cjs` aliases so existing utilities map
      to Design System v2 without broad template churn.
- [ ] Standardize radius tokens: chips 7px, sub-boxes 12px, list rows 14px,
      panels 18px, glass card 24px, buttons/badges 99px.
- [ ] Standardize shadows to low-opacity PRD elevation.
- [ ] Ensure metric, valuation, rank, and date text use the mono font.
- [ ] Use uppercase categorical labels with PRD letter spacing.
- [ ] Update button, tag, badge, stance-chip, metric-strip, sub-tab, appendix,
      quick-intake, and co-pilot bubble styles.
- [ ] Remove one-off blue-accent assumptions from existing components.
- [ ] Verify no page reads as a one-note blue theme after the token swap.
- [ ] Add design-system lint/review checklist:
      one accent per view, Tiffany only for action/selection/positive signal,
      Coral only for genuine risk/negative states, Amber only for caution,
      no serif display type, no heavy shadows, no nested chat boxes in cards.
- [ ] Style co-pilot user bubbles with dark navy, right alignment, and clipped
      top-right corner per Design System v2.
- [ ] Confirm `Done`, `Ready for input`, `Not started`, `Bullish`, `Neutral`,
      and `Cautious` status/stance chips share the PRD badge system.

Verification:

- [ ] `npm --prefix frontend run build`
- [ ] `npm --prefix frontend test -- RouteSmoke.spec.js Sidebar.spec.js`
- [ ] Desktop and mobile screenshots of Home, company Overview, Documents,
      Memo Studio, and Stock Research.
- [ ] Manual contrast check for muted text over the left rail gradient.

### 2. Global Shell And Navigation

- [ ] Create a `GlobalShell` or refactor `App.vue` so the layout explicitly
      owns left rail, central route content, active-jobs rail, modal layer, and
      co-pilot drawer.
- [ ] Preserve current `App.vue` operational contracts during the shell
      refactor:
      authenticated-only polling, `api.listReports()`, `api.externalFeed()`,
      `api.listHormuz()`, `Sidebar` feed props, `ActiveJobsRail`, and
      `DeckSummaryModal`.
- [ ] Confirm `/login` still renders without app chrome and without protected
      sidebar/feed polling.
- [ ] Implement persistent left rail width of 288px on desktop.
- [ ] Apply the signature sidebar/logo gradient only to the primary rail.
- [ ] Add a global header/breadcrumb area above central content.
- [ ] Breadcrumb format shows concrete context:
      `Research Center > Company > Section` or view equivalent.
- [ ] Add account entry points for Settings and User Center.
- [ ] Add an `Innovation Lab` route or section reachable from the shell for
      incubated workflows.
- [ ] Preserve current `/hormuz`, `/hormuz/:id`, and `/research-pages/*` URLs
      as redirects or aliases when their visible home moves under Innovation
      Lab.
- [ ] Move EN/ZH toggle into the header/top-right control per PRD while keeping
      a compact rail fallback if needed.
- [ ] Add a floating `Ask Co-Pilot` button visible on Home, Workspace,
      Competitor, Settings, User Center, and Stock Research.
- [ ] Hide the floating button while the co-pilot drawer is open.
- [ ] Define responsive behavior for widths below 1280px.
- [ ] Keep `ActiveJobsRail` available without overlapping the co-pilot drawer.
- [ ] Add browser-support verification for latest Chrome, Edge, Safari, and
      Firefox.

Verification:

- [ ] Route smoke tests cover all top-level routes with the shell.
- [ ] Playwright/browser screenshots cover co-pilot closed/open states.
- [ ] Keyboard focus can reach rail, header, content, and co-pilot controls.

### 3. Left Rail Content

- [ ] Replace report/news-first rail sections with PRD buckets:
      Portfolio, Pipeline, and Watchlist/Top Players.
- [ ] Add company bucket count badges and compact company cards.
- [ ] Add bucket expand/collapse behavior matching the mockup:
      compact default, `Show all N`, and `Show less`.
- [ ] Source company bucket data from real companies, not hardcoded HTML mock
      data.
- [ ] Add a frontend `api.listCompanies()` wrapper for `GET /api/companies`
      if buckets read from existing company records.
- [ ] Do not derive Portfolio/Pipeline/Watchlist solely from recent reports;
      the bucket source of truth is an open question until confirmed.
- [ ] Add Quick Intake actions in the rail:
      Submit Link, Upload Research, Add Internal Note.
- [ ] Add Market Radar feed section with newest-first signals.
- [ ] Add Stock/Public Market Research entry.
- [ ] Add Innovation Lab entry for incubated workflows.
- [ ] Move standalone Hormuz and current Research Pages links under Innovation
      Lab unless a specific tool is promoted to PRD core navigation.
- [ ] Add Settings and profile/account access at the bottom.
- [ ] Preserve sign-out behavior.
- [ ] Define empty states for no portfolio, no pipeline, no market radar.

Verification:

- [ ] Sidebar tests cover bucket rendering, Quick Intake opening, language
      toggle, stock route link, settings/profile route links, and sign-out.
- [ ] Visual QA confirms text truncation and no rail overflow at desktop and
      narrow widths.

### 4. Home Search And Quick Add

- [x] Autocomplete exists for researched and public companies.
- [x] Deep search exists with progress streaming.
- [ ] Refactor Home first viewport to match PRD: centered search prompt,
      search box, and Quick Add panel directly underneath.
- [ ] Ensure prompt copy matches PRD.
- [ ] Keep Enter behavior clear:
      autocomplete exact hit opens workspace; otherwise deep search starts.
- [ ] Move full-regeneration, stock-refresh, weekly summary, and stats actions
      out of first-viewport primary actions.
- [ ] Add Quick Add cards:
      Submit Link, Upload External Research, Add Research, Source Library and
      Appendix.
- [ ] Rename any generic Home/internal-note copy that still reads as
      Hormuz-specific unless the action explicitly opens the Innovation Lab
      Hormuz workflow.
- [ ] Define and implement the Source Library and Appendix destination for the
      Home Quick Add link.
- [ ] Do not treat the current Hormuz source library / V3 appendix route as
      the PRD company Source Library and Memo Appendix unless it is explicitly
      renamed and adapted.
- [ ] Ensure Quick Add cards open the same intake modals used by the rail.
- [ ] Add post-intake confirmation that names the destination company and
      Documents category when known.
- [ ] Add unresolved-company queue when intake cannot confidently assign a
      company.

Verification:

- [ ] HomeView tests for autocomplete, exact-match route, deep-search fallback,
      Quick Add interactions, and unresolved-company state.
- [ ] Browser QA for empty, searching, result, and intake modal states.

### 5. Intake And Source Pipeline

- [x] Link submission exists for external/news archive.
- [x] External research upload exists with analysis/translation flows.
- [x] Internal Hormuz note upload exists.
- [x] Company background document upload exists.
- [ ] Create a common intake service layer or adapter contract for URL, file,
      and note intake.
- [ ] Inventory existing intake endpoints before adding new ones:
      external news, external research, external-research promotion,
      Hormuz/internal note, Document Library upload, and Background Documents
      upload.
- [ ] Expose any existing server endpoint needed by the new intake UX through
      `frontend/src/api.js` instead of duplicating backend behavior.
- [ ] Treat Hormuz/internal-note intake as an incubated Innovation Lab workflow
      unless/until it is generalized into the PRD Quick Intake pipeline.
- [ ] Add company inference for uploaded files/links/notes.
- [ ] Automatically file home/rail uploads into the correct company's
      Documents view when confidence is high.
- [ ] Add manual review/assignment UI when confidence is low.
- [ ] Preserve source class:
      company material, public filing, third-party market data, BSH primary
      diligence, internal note.
- [ ] Preserve source metadata:
      title, author/source, URL/file, published date, captured date, language,
      uploaded by, source class, confidence, extraction status.
- [ ] Summarize and translate according to active app language.
- [ ] Make extracted facts available to co-pilot and memo generation.
- [ ] Add retry/cancel/error affordances consistently across intake job types.
- [ ] Add dedupe/idempotency for repeated URL/file submissions.

Verification:

- [ ] Backend tests for company inference, category assignment, source-class
      persistence, low-confidence queue, and dedupe.
- [ ] Frontend tests for assignment review and confirmation state.
- [ ] Existing research job lifecycle tests continue passing.

### 6. Company Data Model And API

- [x] `CompanyOut` includes basic profile, products, key people, funding,
      recent news, translations, and public trader snapshot.
- [ ] Keep `server/api.py` `CompanyOut` and `_company_view()` synchronized for
      every new company field. Adding only YAML fixture fields is not enough.
- [ ] Preserve backward compatibility for existing `data/companies.yaml`
      records whose `competitors` are strings and whose products/news have the
      current minimal shape.
- [ ] Add `positioning` fields:
      category, customers, need, benefit, alternative, differentiator.
- [ ] Add `metrics` array with label, value, unit, source refs, as-of date,
      and confidence.
- [ ] Add team profile fields:
      avatar/monogram, name, role, one-line bio, LinkedIn URL, profile URL.
- [ ] Add persona/workflow metadata where useful so views can be QA'd against
      the three PRD personas without hardcoding demo-only behavior.
- [ ] Add product detail fields:
      id, name, description, category, source refs, detail route slug.
- [ ] Convert `competitors` from strings to typed records:
      id, name, public/private, ticker/exchange if public, note, profile,
      comparison fields, source refs.
- [ ] Add board/investor records and cap-table lineage records.
- [ ] Add company-specific news items with category tags, source, URL,
      published/captured dates, and recency.
- [ ] Add sector/industry view payload:
      TAM, CAGR, tracked comps, median multiple, public comps, signals.
- [ ] Add expert opinions:
      speaker, affiliation, stance, quote/summary, source line, date.
- [ ] Add disclosure/source appendix metadata.
- [ ] Add memo editor state:
      section statuses, include flags, rank order, card expansion, bullet edits,
      nested dive-deeper children, conclusion option, appendix expansion state.
- [ ] Add audit records for edits, ranking, inclusion, generation, export, and
      co-pilot actions.
- [ ] Backfill/migrate existing company records into the new shape without
      losing current data.
- [ ] Preserve read-only cap-table display semantics; do not introduce
      fund-administration or cap-table-management workflows.

Verification:

- [ ] Pydantic/schema tests for new API shapes.
- [ ] Migration tests with current `data/companies.yaml` sample records.
- [ ] ZaiNar record renders all PRD mock sections without hardcoded data.

### 7. Company Workspace And Tabs

- [x] Current workspace route exists at `/:companyId`.
- [ ] Replace the tab set with PRD tabs:
      Overview, Documents, Memo Studio, Company News, Industry Views.
- [ ] Remove `Console` as a tab after global co-pilot is available.
- [ ] Keep `Memo Studio` unavailable or adapted for public companies if private
      memo behavior is not supported.
- [ ] Store active tab in route query or route segment for deep links.
- [ ] Deliberately migrate the current query values:
      `overview`, `documents`, `analysis`, `console`. Preserve
      `?report=<id>` generated-report deep links.
- [ ] Add tab-specific loading, error, and empty states.
- [ ] Ensure the company header remains visible above sub-tabs.

Verification:

- [ ] Route/query tests for each tab.
- [ ] Public-company and private-company tab behavior tests.
- [ ] Browser QA for tab switching and deep reload.

### 8. Overview

- [ ] Replace/extend `CompanyDetail.vue` with PRD Overview layout.
- [ ] Add monogram tile.
- [ ] Render company name with stage and sector tags beside it.
- [ ] Render metadata line:
      founded year, HQ, employee band.
- [ ] Render emphasized top-right funding line:
      last round, post-money, date, total raised.
- [ ] Render positioning summary in the required uniform-weight template.
- [ ] Render four-cell metric strip:
      ARR, YoY Growth, Valuation, TAM.
- [ ] Render Core Team cards with monogram, role, bio, LinkedIn, Profile.
- [ ] Render Products grid with count and detail-card navigation.
- [ ] Render Competitors grid with count, public/private tags, notes, and
      `View profile and compare` action.
- [ ] Add `Compare to [company]` and `Add competitor` actions.
- [ ] Render Investors and Cap Table two-column section.
- [ ] Render proportional ownership bars with mono percentages.
- [ ] Preserve public-company trader snapshot as a Stock/Public Market panel,
      not a substitute for Overview.

Verification:

- [ ] Component tests for every Overview section with complete and partial
      company data.
- [ ] Visual QA against the supplied Home HTML ZaiNar layout.
- [ ] Metrics use mono font; tags and sections use PRD styling.

### 9. Documents

- [x] Company file uploads and generated report listing exist.
- [x] Background Documents for memo input exist.
- [ ] Present a single PRD Documents tab with grouped rows:
      Memos, Company Materials, Legal and Corporate, Financial,
      External Reports, Internal Notes and Sources.
- [ ] Keep backend separation visible only where it matters for memo inputs.
- [ ] Add provenance/source-class badges to every document row.
- [ ] Add document type badges:
      PDF, DOCX, XLSX, MD, URL, Memo, Note, etc.
- [ ] Add quick actions:
      upload, view, summarize, translate, promote/assign, download, delete.
- [ ] Route exported memos into Documents > Memos automatically.
- [ ] Ensure upload supports PRD file types:
      PDF and DOCX for external research; internal note with optional PDF.
- [ ] Add category/tag editing for misfiled documents.
- [ ] Add document source trace drawer for summarized/analyzed documents.
- [ ] Add filters for language, source class, category, status, and uploaded
      by/source.

Verification:

- [ ] Existing file preview and summary tests continue passing.
- [ ] New Documents tests cover grouping, provenance, memo export row, and
      category editing.
- [ ] Browser QA for empty, uploading, analyzing, failed, and ready states.

### 10. Memo Studio

- [x] Backend final memo generation exists.
- [x] Existing Memo Analysis Dashboard has research tasks, readiness, evidence
      matrix, benchmark, source brief, chart plans, narrative hooks, and
      generated memo controls.
- [ ] Add a PRD-facing Memo Studio editor as the default user surface.
- [ ] Keep the current analysis dashboard as `Advanced Tools` or a collapsible
      research cockpit.
- [ ] Implement first-time behavior:
      show Generate when no memo exists for the company.
- [ ] Implement returning-company behavior:
      show latest memo version by default.
- [ ] Add compact task board:
      progress, Section X of 5, Export Memo, Regenerate, live status.
- [ ] Implement five top-level sections:
      Executive Summary, Investment Thesis, Risks and Mitigations,
      Conclusion, Appendix.
- [ ] Executive Summary:
      one-paragraph synthesis, recommendation, round, top gate, Rerun.
- [ ] Investment Thesis:
      categories, 3-5 highlight cards, include checkbox, rank controls,
      independent numbering starting at 1, expandable bullets.
- [ ] Risks and Mitigations:
      categories including geopolitics/macro, 3-5 risk cards, include checkbox,
      rank controls, independent numbering starting at 1, expandable bullets.
- [ ] Highlight/risk card left rail:
      checkbox, rank up/down, mono index.
- [ ] Card body click toggles supporting bullets.
- [ ] Bullet hover actions:
      Edit, Dive Deeper, Discuss.
- [ ] Inline Edit persists edited bullet text and audit history.
- [ ] Dive Deeper appends nested AI-expanded sub-point recursively.
- [ ] Discuss opens the global co-pilot with bullet/card/section context.
- [ ] Left-border color encodes category/severity:
      Tiffany, Coral, Amber, Indigo, Slate.
- [ ] Conclusion:
      conditional, lead-and-anchor, pass options; selected framing persists.
- [ ] Appendix:
      all PRD fact blocks collapsed by default and independently expandable.
- [ ] Rerun actions exist at section level, not just whole-memo regenerate.
- [ ] Export Memo respects include flags, rank order, conclusion option, edits,
      and appendix/source disclosures.
- [ ] Quantitative claims in memo cards and export carry source refs or source
      class.
- [ ] Memo version list shows generated/current/superseded states.
- [ ] Add invalid-state guardrails:
      cannot export with missing provenance on key figures.
- [ ] Add disconfirming-signal treatment in memo generation and co-pilot
      prompts so risks/contradictions are surfaced before optimistic synthesis.

Verification:

- [ ] Backend tests for memo editor state persistence, independent ranking,
      recursive dive-deeper children, edit history, and export projection.
- [ ] Frontend tests for include/rank/expand/edit/dive/discuss behavior.
- [ ] Export tests verify excluded cards are omitted and order matches rank.
- [ ] Existing memo generation and memo-analysis tests continue passing.
- [ ] Browser QA for generation running, completed, failed, and export states.

### 11. AI Co-Pilot

- [x] Per-company Console backend and UI exist.
- [ ] Create global co-pilot state/store:
      open/closed, current context, active session, pending task.
- [ ] Implement 372px slide-in drawer.
- [ ] Add floating `Ask Co-Pilot` button on every PRD view.
- [ ] Reuse console sessions or create a new `copilot` adapter over the
      existing console endpoints.
- [ ] Preserve console session mechanics first:
      estimate, create, hydrate stream, ask stream, attachments, archive,
      delete, and token/cost accounting.
- [ ] Context-aware hydration includes:
      route, company, tab, memo section, card, bullet, selected documents.
- [ ] Keep selected document scope explicit. Console can hydrate Background
      Documents and Document Library files, but memo generation must still
      respect the `docs/architecture.md` separation unless deliberately
      migrated.
- [ ] Message types:
      user prompt, AI response, Research Task.
- [ ] Style user bubbles as deep slate; AI bubbles as surface-alt; tasks as
      Tiffany-tinted.
- [ ] Ensure discussion is owned by the co-pilot panel; no card or list should
      embed a separate inline chat box.
- [ ] Add `Discuss` action integration from memo bullets/cards.
- [ ] Add `Dive Deeper` action integration from memo bullets.
- [ ] Add ability to action a Research Task into Memo Studio.
- [ ] Add attachments if preserving current Console image/file behavior is
      still required.
- [ ] Add session archival/history access without making it the primary tab.

Verification:

- [ ] Console backend tests continue passing.
- [ ] Co-pilot component tests for context labels and message types.
- [ ] Browser QA for every top-level view with co-pilot open/closed.

### 12. Company News

- [ ] Create Company News tab.
- [ ] Build reverse-chronological feed.
- [ ] Display source, category dot, recency, title, summary, and external-link
      affordance.
- [ ] Add AI-generated category tags:
      fundraising, product, filing, press, partnership, leadership, risk, etc.
- [ ] Add filters by category/tag.
- [ ] Merge company `recent_news`, archived URL submissions, and relevant
      external feeds by company id/source match.
- [ ] Add safe external-link behavior with `rel="noopener"`.
- [ ] Add empty state prompting Submit Link.

Verification:

- [ ] Backend tests for company-specific news aggregation and category tags.
- [ ] Frontend tests for sorting, filters, and safe external links.

### 13. Industry Views And Expert Opinions

- [ ] Create Industry Views tab.
- [ ] Add sector header with metric strip:
      Sector TAM, 5-year CAGR, tracked comps, median EV/NTM revenue.
- [ ] Add Expert Opinions / Notable Voices above comps/signals.
- [ ] Render stance chips:
      Bullish, Neutral, Cautious.
- [ ] Render quote/summary, speaker, affiliation, source line, and date.
- [ ] Add Public Comps cards with public ticker, change, note, and sparkline.
- [ ] Add Sector Signals alert cards with category, signal name, and thesis
      implication.
- [ ] Ensure public-market data can source from the existing Stock Research and
      Trader snapshot systems where possible.
- [ ] Add empty/fallback state when no sector data exists.

Verification:

- [ ] Data-shaping tests for industry view payloads.
- [ ] Component tests for stance chips, comps, signals, and empty state.
- [ ] Visual QA against the supplied Home HTML ZaiNar Industry Views section.

### 14. Competitor And Comps Detail

- [ ] Add route:
      `/companies/:companyId/competitors/:competitorId` or equivalent.
- [ ] Add competitor API payload.
- [ ] Add competitor header:
      monogram, name, public/private, sector/category, status.
- [ ] Add competitor profile fields:
      description, valuation/market cap, revenue, employees, founded, team.
- [ ] Add products and board/cap table where available.
- [ ] Add head-to-head comparison table against active company.
- [ ] Add placeholders:
      benchmark, win/loss tracker, patent overlap map.
- [ ] Add back-to-memo/back-to-company navigation.
- [ ] Add `View profile and compare` link from Overview competitor cards.

Verification:

- [ ] Route smoke test for competitor detail.
- [ ] Component tests for private and public competitors.
- [ ] Browser QA for ZaiNar vs NextNav-style comparison.

### 15. Settings And User Center

- [ ] Add `/settings` route.
- [ ] Add `/user` or `/profile` route.
- [ ] Render account:
      name, email, workspace, role, plan.
- [ ] Render preferences:
      weekly summary, stock auto-refresh, agent alerts, compact density,
      language.
- [ ] Render system status:
      research engine, memo generation, stock data feed, document index, model.
- [ ] Render usage:
      token usage, research runs, reset date.
- [ ] Add team/profile summary in User Center.
- [ ] Preserve sign-out and session-expired behavior.
- [ ] Back Settings/User Center with real data or clearly scoped placeholder
      adapter.
- [ ] Settings and User Center return cleanly to the prior context when opened
      from a company workspace.

Verification:

- [ ] Route smoke tests.
- [ ] Component tests for preference toggles and account render.
- [ ] Accessibility checks for toggles and segmented controls.

### 16. Public Market Research / Stock

- [x] Stock Research dashboard exists at `/stock-research`.
- [x] Trader stats and public-company snapshots exist.
- [ ] Fit Stock entry into the PRD left rail.
- [ ] Align Stock Research visual style with Design System v2.
- [ ] Ensure private company public comps can reuse Stock Research outputs.
- [ ] Preserve existing stock tests and route behavior.
- [ ] Confirm no trading/execution controls are introduced.

Verification:

- [ ] Existing StockResearch, TraderView, TraderStats tests pass.
- [ ] Browser QA for Stock Research after shell/design changes.

### 17. Innovation Lab / Incubated Workflows

- [ ] Create an `Innovation Lab` destination for incubated workflows that are
      useful but not part of the PRD core workspace.
- [ ] Move the visible Hormuz section under Innovation Lab.
- [ ] Move current Research Pages under Innovation Lab unless individually
      promoted:
      Market Pulse, Evidence Matrix, Hypothesis Lab.
- [ ] Keep Innovation Lab visually secondary to PRD core navigation so it does
      not compete with Home, company buckets, Market Radar, Stock, Settings,
      or User Center.
- [ ] Add a lightweight lab index/card model:
      title, status, purpose, route, source stores, owner/maintainer, promoted
      or retired state.
- [ ] Preserve legacy routes:
      `/hormuz`, `/hormuz/:id`, and `/research-pages/*` should redirect or
      alias to their Innovation Lab locations during migration.
- [ ] Rename user-facing generic labels so Hormuz-specific wording appears only
      inside the Hormuz lab workflow, not in PRD Quick Add or general internal
      note intake.
- [ ] Keep Innovation Lab separate from PRD Source Library, Memo Appendix, and
      memo-input Background Documents semantics.

Verification:

- [ ] Route smoke tests cover Innovation Lab index, Hormuz library/detail, and
      each migrated research page.
- [ ] Sidebar tests confirm incubated workflows render under Innovation Lab and
      no standalone Hormuz primary section remains.
- [ ] Existing Hormuz and research-page tests continue passing.
- [ ] i18n tests cover Innovation Lab labels in EN/ZH.

### 18. Language And Localization

- [x] `appLanguage` global state exists.
- [x] Many existing strings have EN/ZH dictionary keys.
- [ ] Add dictionary coverage for every new PRD surface.
- [ ] Remove hardcoded English from shell, rail, tabs, overview, documents,
      memo editor, news, industry views, competitor, settings, and co-pilot.
- [ ] Ensure language toggle reflects active language globally.
- [ ] Persist user language preference if settings storage is available.
- [ ] Make intake summaries and translations respect selected app language.
- [ ] Preserve source-language labels and provenance when displaying translated
      content.
- [ ] Add fallback behavior when translation is missing or stale.

Verification:

- [ ] i18n tests scan for missing keys on new components.
- [ ] Browser QA switches EN/ZH on Home, Overview, Documents, Memo Studio,
      Company News, Industry Views, Stock Research, Innovation Lab, Settings,
      and Co-Pilot.

### 19. Security, Privacy, RBAC

- [x] Auth/session and bearer-token protection exist.
- [ ] Define workspace roles:
      partner, analyst, research/ops, admin.
- [ ] Gate settings/admin-only actions by role.
- [ ] Ensure source files and memo exports remain behind auth.
- [ ] Ensure external links open safely.
- [ ] Add audit trail for sensitive actions:
      delete document, export memo, approve memo, rank/edit thesis/risk.
- [ ] Confirm no PRD surface executes trades, wires funds, or creates
      transactions.
- [ ] Confirm no PRD surface performs portfolio accounting, cap-table
      administration, or fund administration.
- [ ] Review upload file-type validation for new PRD types.

Verification:

- [ ] Backend auth/permission tests for new endpoints.
- [ ] Upload validation tests.
- [ ] Manual review of new external-link and download routes.

### 20. Performance And Reliability

- [x] Long-running job progress and active-jobs rail exist.
- [ ] Primary views interactive under 2s on warm cache.
- [ ] Memo section generation streams visible progress.
- [ ] Co-pilot drawer opens without blocking route content.
- [ ] Large route/component chunks remain split after new surfaces are added.
- [ ] Add cache/freshness labels for AI-generated company and sector payloads.
- [ ] Add stale-job recovery for any new memo section/dive-deeper jobs.
- [ ] Avoid polling storms between ActiveJobsRail, Documents, Memo Studio, and
      Co-Pilot.

Verification:

- [ ] `npm --prefix frontend run build` with bundle-size review.
- [ ] Targeted timing check for Home, Overview, Documents, Memo Studio.
- [ ] Backend tests for new job lifecycle states.

### 21. Accessibility And Responsive Behavior

- [ ] Keyboard-operable checkboxes, rank arrows, card expansion, edit controls,
      filters, tabs, and co-pilot.
- [ ] Visible focus states on all controls.
- [ ] ARIA labels for icon-only buttons.
- [ ] Screen-reader labels for progress/status updates.
- [ ] Sufficient contrast for muted labels over the rail gradient.
- [ ] Responsive shell for laptop widths and narrow/mobile viewports.
- [ ] Text never overlaps or overflows buttons/cards in supplied viewport
      checks.
- [ ] Tables/cards scroll or reflow predictably.
- [ ] Cross-browser smoke covers latest Chrome, Edge, Safari, and Firefox.

Verification:

- [ ] Playwright keyboard path for Home -> Company -> Memo Studio -> Co-Pilot.
- [ ] Desktop and mobile visual QA.
- [ ] Contrast checks for rail, badges, chips, and status states.

### 22. Product Analytics And Success Metrics

- [ ] Define event taxonomy for PRD success metrics:
      search_started, workspace_opened, memo_generate_started,
      memo_first_draft_ready, memo_exported, memo_key_figure_source_missing,
      copilot_task_proposed, copilot_task_actioned, section_rerun,
      section_reused.
- [ ] Track median time from first search to first memo draft.
- [ ] Track percentage of exported memos with all key figures source-linked.
- [ ] Track weekly active partners/analysts as a share of licensed seats.
- [ ] Track co-pilot task acceptance rate.
- [ ] Track sections reused versus regenerated over time.
- [ ] Add privacy-safe local/event storage or backend logging approach.
- [ ] Add Settings/Admin readout or export path for these metrics if launch
      needs visibility.

Verification:

- [ ] Backend or frontend tests assert key workflow events are emitted once.
- [ ] Manual QA can trace one new-company flow from search to memo export with
      timestamps sufficient for the `< 2 hours` success metric.
- [ ] Export guardrail can report key-figure source coverage.

### 23. Auditability And Memo Versioning

- [x] Generated reports are versioned by report id.
- [x] Memo analysis sessions persist under durable folders.
- [ ] Version memo editor state separately from generated DOCX artifacts.
- [ ] Record include/exclude decisions.
- [ ] Record rank changes and previous rank order.
- [ ] Record inline edits and nested AI dive-deeper children.
- [ ] Record conclusion selection.
- [ ] Record export event with exported section/card ids.
- [ ] Add restore/inspect path for a memo version's state.
- [ ] Add source/disclosure appendix to exported memo based on current state.

Verification:

- [ ] Backend tests for audit record creation and replay.
- [ ] Export tests assert version state matches exported content.

### 24. Persona Acceptance And Test Plan

- [ ] VC Partner path:
      search/open company, scan Overview, use Memo Studio, rank thesis/risks,
      discuss weak point, select conclusion, export memo.
- [ ] Investment Analyst path:
      ingest source, manage Documents, run comparables/news context, edit memo
      bullets, verify source links.
- [ ] Research/Ops path:
      process unresolved intake, maintain source library, tag provenance,
      confirm disclosures and Sources appendix.

Verification:

- [ ] Add at least one browser or high-level component test for each persona
      path once the relevant views exist.
- [ ] QA checklist explicitly marks persona path pass/fail before launch.

### 25. Test And QA Plan

- [ ] Backend:
      `python -m pytest`
- [ ] Frontend unit/component:
      `npm --prefix frontend test`
- [ ] Frontend lint:
      `npm --prefix frontend run lint`
- [ ] Frontend build:
      `npm --prefix frontend run build`
- [ ] Browser smoke:
      Home, Overview, Documents, Memo Studio, Company News, Industry Views,
      Competitor Detail, Settings, User Center, Stock Research, Innovation Lab.
- [ ] Browser responsive:
      desktop >=1280px, laptop, mobile/narrow.
- [ ] Browser states:
      empty, loading, partial, error, populated, co-pilot open, co-pilot closed.
- [ ] Export verification:
      memo export content matches include/rank/edit state.
- [ ] Source verification:
      all key figures show source class/source reference before export.
- [ ] Accessibility:
      keyboard and focus path through memo editor and co-pilot.
- [ ] Visual comparison:
      compare ZaiNar Home/Workspace against supplied Home HTML and Design
      System v2 component rules.

## PRD Functional Requirements Coverage

| ID | PRD requirement | Current state | Required work |
| --- | --- | --- | --- |
| FR-1 | Global search opens workspace with researched/public autocomplete | Partial | Keep existing autocomplete/deep search; tighten Enter/exact-match behavior and route timing. |
| FR-2 | Quick Add/Intake supports link, PDF/DOCX, internal notes with summarized filing | Partial | Unify intake UX, add auto company/category assignment, provenance, and unresolved queue. |
| FR-3 | Overview renders PRD header, positioning, metric strip, team, insights, investors | Partial | Build richer Overview and extend company schema. |
| FR-4 | Memo Studio generates five-section memo with progress/status/rerun | Partial | Current generation exists; add five-section editor and section rerun/progress model. |
| FR-5 | Thesis and Risk cards checkable, rankable, expandable | Partial | Current risk priority exists; add PRD card state and independent rank UI. |
| FR-6 | Bullets support Edit, Dive Deeper recursively, Discuss to co-pilot | Not started | Add bullet action model, AI nested expansion jobs, and co-pilot context bridge. |
| FR-7 | Appendix collapsed by default, independent expansion | Not started | Add appendix fact-block model and UI. |
| FR-8 | Co-pilot reachable on every view and context-aware | Partial | Console exists; convert to global drawer with context injection. |
| FR-9 | Documents grouped by categories with provenance | Partial | File libraries exist; add PRD grouping, source classes, provenance, and category editing. |
| FR-10 | Industry Views shows Expert Opinions above comps/signals | Not started | Add Industry Views data/API/UI. |
| FR-11 | Company News reverse-chronological source-attributed feed | Partial | Basic recent news exists; add dedicated tab, tags, filters, and feed merge. |
| FR-12 | Export Memo reflects included/ranked sections | Partial | DOCX export exists; add editor-state projection and tests. |
| FR-13 | Every quantitative memo claim links to source/source class | Partial | Source traces exist in research tools; enforce on memo editor and export. |
| FR-14 | Settings and User Center reachable from header | Not started | Add routes, header links, and backed/placeholder data adapters. |

## Milestone Sequence

### M1 - Foundations

- [ ] Design System v2 tokens and components.
- [ ] Global shell, header, left rail, co-pilot drawer frame.
- [ ] Home search/Quick Add refactor.
- [ ] Innovation Lab entry/placeholder with Hormuz and research-page workflows
      moved under it.
- [ ] Company schema extensions and migration.
- [ ] PRD Overview.
- [ ] Workspace tab restructure with Company News and Industry Views
      placeholders.

Exit criteria:

- [ ] ZaiNar Overview can be rendered from real app data with no hardcoded
      mock-only sections.
- [ ] Workspace exposes the PRD five-tab structure while existing generated
      reports, Documents, MemoAnalysisDashboard/Advanced Tools, Console/co-pilot
      path, and public-company behavior remain reachable.
- [ ] Existing Hormuz and research-page experiments remain reachable through
      Innovation Lab, and legacy URLs still resolve.
- [ ] Home and shell match the supplied references closely enough for visual QA.
- [ ] Search and existing documents/memo routes still work.

### M2 - Memo Studio

- [ ] Five-section memo editor.
- [ ] Highlight/risk card state.
- [ ] Include/rank/expand/edit/dive/discuss.
- [ ] Section rerun and progress.
- [ ] Export projection from editor state.

Exit criteria:

- [ ] A user can generate or open the latest memo, curate thesis/risk cards,
      choose conclusion, and export a memo matching on-screen state.

### M3 - Evidence

- [ ] Unified Documents view.
- [ ] Intake auto assignment.
- [ ] Source classes/provenance.
- [ ] Appendix fact blocks.
- [ ] Quantitative-claim source enforcement.

Exit criteria:

- [ ] All key figures in Memo Studio and export have visible source/source
      class, or export is blocked with a clear reason.

### M4 - Context

- [ ] Company News.
- [ ] Industry Views and Expert Opinions.
- [ ] Competitor detail.
- [ ] Co-pilot actioning into memo tasks.
- [ ] Public comps integration with Stock Research/Trader data.

Exit criteria:

- [ ] ZaiNar-style company context, sector context, news, and competitor detail
      are navigable and source-attributed.

### M5 - Polish

- [ ] Settings/User Center.
- [ ] Accessibility and responsive pass.
- [ ] Performance pass.
- [ ] Audit trail and memo version review.
- [ ] Final visual QA against PRD and HTML references.

Exit criteria:

- [ ] Full backend/frontend test suite passes.
- [ ] Browser QA passes all PRD views in desktop and narrow widths.
- [ ] No P0 PRD acceptance criteria remain unmet.

## Enhancement Backlog

These enhancements go beyond the strict PRD but are natural follow-ons once
the core v2 surface works.

- [ ] Source Trace Drawer: reusable drawer for source excerpt, locator,
      confidence, source class, and extraction path.
- [ ] Memo Diff View: compare two memo versions by section, card, rank, and
      exported prose.
- [ ] Memo Review Queue: partner/analyst review states for proposed edits,
      risks, evidence gaps, and conclusion framing.
- [ ] Saved Workspace Views: save filter/tab states for partner review meetings.
- [ ] Company Data Quality Panel: show missing fields, stale figures, weak
      sources, and conflicting claims.
- [ ] Intake Assignment Inbox: ops workflow for unresolved company/category
      assignment.
- [ ] Sector Data Builder: guided creation of sector TAM/CAGR/comps/signals
      when no industry payload exists.
- [ ] Competitor Win/Loss Tracker: durable records for deals contested against
      competitors.
- [ ] Patent Overlap Map: structured patent/standards overlap summary for
      relevant deep-tech companies.
- [ ] Export Targets: decide and implement PDF, DOCX, and shareable link
      outputs as separate export modes.
- [ ] Role-Based Workspace Admin: team/member management, seats, permissions,
      and audit export.
- [ ] Notification Center: completed memo, failed ingestion, stale sources,
      co-pilot task completed.
- [ ] Model/Usage Admin: real usage accounting, reset dates, model status, and
      per-user or workspace budgets.
- [ ] Visual Regression Harness: stable screenshots for PRD core pages and
      design-system components.
- [ ] Fixture Company Pack: ZaiNar, Databricks, Stripe, NextNav, and one empty
      company fixture for deterministic QA.

## Resolved IA Decisions

- [x] Hormuz is not a standalone primary navigation section in v2.
- [x] Hormuz moves under `Innovation Lab`.
- [x] `Innovation Lab` is the home for incubated workflows, including current
      research-page experiments unless a workflow is explicitly promoted into
      PRD core IA.
- [x] Innovation Lab does not replace the PRD Source Library, Memo Appendix, or
      the `docs/architecture.md` split between Document Library and Background
      Documents.

## Open Questions

- [ ] Confirm final label for internal note ingestion:
      `Add Research`, `Add Internal Note`, or another name.
- [ ] Confirm export targets for launch:
      DOCX only, PDF only, DOCX plus PDF, or shareable link.
- [ ] Confirm whether the PRD Documents view should hide the current backend
      split between Document Library and Background Documents or expose it
      explicitly.
- [ ] Confirm portfolio/pipeline/watchlist source of truth and bucket rules.
- [ ] Confirm if public companies should have Memo Studio hidden, disabled, or
      adapted for public-equity memos.
- [ ] Confirm source-class taxonomy and whether disclosures are company-level,
      memo-level, or workspace-level.
- [ ] Confirm how much of Settings/User Center should be real for launch versus
      placeholder Enterprise account information.
- [ ] Confirm retention policy for memo edit/rank history.
- [ ] Confirm whether the supplied Home HTML is a visual reference only or an
      exact interaction contract for ZaiNar demo data.

## Immediate Next Slice Recommendation

Start with M1 in this order:

1. Design System v2 tokens and shell.
2. PRD left rail and Home Quick Add.
3. Innovation Lab destination for Hormuz and incubated research-page tools.
4. Company schema extension/backfill.
5. PRD Overview for ZaiNar.
6. Tab restructure with empty Company News and Industry Views placeholders.

This gives the user-visible product shape first while preserving existing
search, documents, memo-generation, and stock-research functionality during the
transition.
