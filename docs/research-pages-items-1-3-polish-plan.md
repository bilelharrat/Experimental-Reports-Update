# Research Pages Items 1-3 Polish Plan

Status date: 2026-06-17

This document tracks the polish work required before moving from the first
research-page slice to later items in
`docs/research-pages-visual-tools-plan.md`.

Scope is limited to:

1. Market Pulse
2. Evidence Matrix
3. Hypothesis Lab

## Review Summary

The first implementation establishes the right foundation:

- Dedicated backend payload assembly lives in `server/research_pages.py`.
- Routes exist for all three pages under `/api/research-pages/*` and
  `/research-pages/*`.
- The common page contract is present: `schema_version`, `page_id`,
  `generated_at`, `as_of`, `status`, `summary`, `sections`, `source_health`,
  `doctor_issues`, and `actions`.
- Focused backend and frontend tests cover the primary page payloads and
  fixture-backed visual surfaces.
- The implementation does not require live Claude or external market data.

The remaining work is mostly contract hardening, action semantics, visual QA,
and making empty/partial states more analyst-ready.

## Must Fix Before Moving On

### 1. Correct Hypothesis Lab Debug Semantics

Current risk:

- The Hypothesis Lab UI labels an action as "Debug Backfill", but the API call
  only sends `allow_debug_backfill`.
- The backend only turns a `forward_live` request into `debug_backfill` when
  the requested vintage date is in the past.
- A same-day or future debug action can therefore create a `forward_live`
  vintage while the UI says it created a debug backfill.

Polish work:

- Add an explicit debug creation path from the UI to the backend.
- Either expose `vintage_kind` in the `POST /api/stock-research/hypotheses/create`
  request model or add a wrapper endpoint that calls
  `hypothesis_cycle.debug_backfill()`.
- Constrain or clearly validate debug vintage dates.
- Add a regression test for same-day debug creation.

Acceptance:

- Clicking "Debug Backfill" can only produce `vintage_kind=debug_backfill`.
- Debug rows remain visually and contractually training-ineligible.

### 2. Separate Mixed Live And Debug Timeline Rows

Current risk:

- Hypothesis vintages are summarized by `vintage_date`.
- The summary carries a single `vintage_kind`, chosen from the first hypothesis
  row for that date.
- If live and debug rows ever share a date, the timeline can collapse them into
  one row and hide the distinction the plan requires.

Polish work:

- Group timeline rows by `(vintage_date, vintage_kind)`.
- Key frontend timeline rows by both date and kind.
- Show kind-specific generated, evaluated, pending, and training-eligible
  counts.
- Add a backend test fixture with both live and debug rows on the same date.

Acceptance:

- Live and debug rows are always distinct in the timeline.
- A mixed-date fixture renders two timeline rows.

### 3. Dedupe Hypothesis Doctor Issues

Current risk:

- Hypothesis Lab creates page-level doctor issues and also appends Stock
  Research doctor issues.
- The same issue type can appear twice with different as-of assumptions.

Polish work:

- Normalize issue identity by `type`, `artifact_id`, `path`, and relevant
  date fields.
- Prefer the richer existing doctor issue when it has path/artifact metadata.
- Align page-level `as_of` and Stock Research doctor date handling, or clearly
  label the source of each issue.

Acceptance:

- The same actionable warning appears once.
- If two warnings share a type but refer to different artifacts or dates, the
  UI makes that distinction explicit.

## Should Polish Before Moving On

### 4. Make Placeholder Actions Honest

Current state:

- Several actions are listed in payloads but have `endpoint: null`.
- Some UI buttons only set a local message.

Polish work:

- Mark unimplemented actions as `disabled` or `placeholder` in the payload.
- In the UI, show placeholders as disabled controls or non-clickable intent
  rows.
- Only leave clickable buttons for actions with real effects or deliberate
  browser-test mocks.

Acceptance:

- Analysts can tell which actions are available now versus planned.
- No placeholder action looks like it changed durable state.

### 5. Tighten Evidence Matrix Claim Safety

Polish work:

- Disable "Approve for memo" unless `eligible_for_memo` is true.
- Add visible reason text for blocked memo/hypothesis eligibility.
- Show source previews or source trace details from the claim row, not only the
  source provenance aggregate.
- Add a weak-source-only company-scoped fixture, not only a stock-signal
  fixture.

Acceptance:

- No unsupported or weak-source-only claim appears memo-approved or actionable
  for memo approval.
- The page makes the source gap obvious without requiring table inspection.

### 6. Improve Market Pulse Empty And Partial States

Polish work:

- Keep the current exact missing-aggregate message.
- Add a compact "what is needed next" panel with the required API/action.
- Show placeholder panels for regime, heat map, diff, and catalyst preview even
  in empty state so the page shape is stable.
- Add a browser-level fixture test for empty Market Pulse.

Acceptance:

- Empty Market Pulse explains the missing aggregate and preserves the expected
  page layout.

### 7. Improve Source Trace Presentation

Polish work:

- Display source health consistently across the three pages.
- Surface broken source refs near the affected row, not only in Doctor Issues.
- Include source type, confidence, locator, published date, and excerpt in a
  consistent compact component.

Acceptance:

- A user can inspect why a claim or signal is trusted, weak, stale, missing, or
  broken without leaving the page.

## Visual QA Checklist

Run browser-level QA after the contract fixes above:

- Desktop viewport: Market Pulse, Evidence Matrix, Hypothesis Lab.
- Mobile/narrow viewport: all three pages.
- Empty state for each page.
- Fixture-backed populated state for each page.
- Table overflow behavior.
- Sidebar plus page header behavior after the responsive sidebar changes.
- No incoherent overlap between nav, controls, tables, cards, and doctor issue
  panels.

Known QA note:

- Component tests and production build pass, but in-app browser visual QA was
  blocked by the auth/session behavior during review. Re-run visual QA once the
  browser test session can authenticate or use an authenticated app shell
  harness.

## Test Plan

Required focused tests:

- `PYTHONPATH=. pytest tests/test_research_pages.py tests/test_hypothesis_cycle.py`
- `cd frontend && npm test -- ResearchPagesView.spec.js`
- `cd frontend && npm test -- RouteSmoke.spec.js Sidebar.spec.js`
- `cd frontend && npm run build`

Additional tests to add:

- Same-day debug backfill cannot become `forward_live`.
- Mixed live/debug timeline rows on the same date render separately.
- Duplicate hypothesis doctor issues are deduped.
- Evidence Matrix disables memo approval for ineligible claims.
- Market Pulse empty state preserves the expected page frame.

## Completion Gate

Do not move to page 4 or later items until:

- All Must Fix items are implemented and covered by tests.
- Placeholder actions are visually honest.
- Empty and populated states have been checked for all three pages.
- The focused backend, frontend, route/sidebar, and build checks pass.
