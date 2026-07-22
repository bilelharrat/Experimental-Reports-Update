# UI Consistency Remediation Tracker

Source: `BSH Research Center UI Consistency Check (final) by ss.pdf`  
Reviewed: 2026-07-20  
Scope: 35 mismatches across the global shell, company workspace, documents, Memo Studio, news, industry views, Co-Pilot, sidebar, and home.

## Status key

- [ ] Not started
- [x] In progress
- [x] Implemented and verified

## A. Global

- [x] **A1 - Compact key numbers.** Format currency and large numeric metrics with `$`, `K/M/B/T`, percentages, and the mono numeric style.
- [x] **A2 - Remove internal/developer artifacts.** Replace provider/backend/PRD language, raw paths, enum values, and raw timestamps with user-facing copy.
- [x] **A3 - Complete Chinese-mode localization.** Keep company overview, documents, Memo Studio, news, industry, Co-Pilot, sidebar, and home copy in the selected language.
- [x] **A4 - Coral active-tab underline.** Use the Design System v2 coral underline without rounded tab boxes.
- [x] **A5 - Tight heading tracking.** Apply `-0.02em` letter spacing to `h1`, `h2`, and `h3`.
- [x] **A6 - Pill or quiet-link small controls.** Remove 4px-radius rectangles from small text controls such as show-all and back-to-search.

## B. Company header and Overview

- [x] **B1 - Remove duplicated company header.** Render one co-head with identity, tags, metadata, funding, website/refresh actions, and positioning.
- [x] **B2 - Join the metric strip.** Use one four-cell metric bar with interior hairlines.
- [x] **B3 - Quiet unknown states.** Render unavailable metric values as an em dash with a restrained pending label.
- [x] **B4 - Restore Core Team card anatomy.** Use white bordered cards with avatar, role, bio/note, and available profile links.
- [x] **B5 - Restore Products and Competitors card surfaces.** Use white surfaces, hairline borders, and 14px radii.
- [x] **B6 - Restore editorial positioning treatment.** Use editorial text with highlighted/underlined emphasis instead of a gray callout.

## C. Documents

- [x] **C1 - Restore document-row anatomy.** Add file-type tiles, human labels, metadata, type tags, and pill Open/View/Export actions in user-facing groups.
- [x] **C2 - Use ISO mono dates.** Display document dates as `YYYY-MM-DD` in the mono numeric style.
- [x] **C3 - Replace PRD/backend copy.** Describe the evidence library in user terms and hide implementation ownership.

## D. Memo Studio

- [x] **D1 - Style checkboxes.** Use 20px custom controls with tiffany checked state and a white check.
- [x] **D2 - Use hover-revealed icon actions.** Show 27px icon-only Edit, Dive Deeper, and Discuss actions with accessible labels.
- [x] **D3 - Restore numbered section headers.** Add mono section numbers, 22px titles, bottom rules, and right-aligned subtitles/actions.
- [x] **D4 - Correct card surfaces.** Keep cards white with hairlines and colored left borders; separate bullets with rules instead of nested boxes.
- [x] **D5 - Make readiness truthful.** Count only genuinely complete sections and reflect incomplete/blocked editor state.
- [x] **D6 - Deduplicate rendered content.** Suppress duplicate memo cards and action-queue tasks by normalized content signature.
- [x] **D7 - Quiet run failures.** Show an editorial recovery state without raw errors, paths, timestamps, or stack-style diagnostics.

## E. Company News

- [x] **E1 - Use category filter pills.** Replace the category dropdown and filter/reset button cluster with All/Filings/Funding/Product/Press pills; retain search as a quiet input.
- [x] **E2 - Add Live pulse badge.** Show the live-feed affordance in the news header.
- [x] **E3 - Restore news-row anatomy.** Use white rows, colored dots, normalized source/category/date metadata, and an external-link icon.

## F. Industry Views

- [x] **F1 - Implement all designed modules and empty states.** Always render the sector metric strip, expert opinions, public comps/sparklines, and sector signals with designed empty states.

## G. AI Co-Pilot

- [x] **G1 - Dock the panel.** Make the 372px full-height panel participate in the app layout on desktop so it does not cover content.
- [x] **G2 - Provide the composer.** Keep the session composer and quick actions visible in the panel.
- [x] **G3 - Match the panel header.** Use a tiffany icon tile, Memo Co-Pilot title, context line, and collapse control.
- [x] **G4 - Add research-task bubbles.** Distinguish task cards from user and assistant chat bubbles.

## H. Sidebar and Home

- [x] **H1 - Add company research-status chips.** Show Researched, Analyzing, or In review in each company rail row.
- [x] **H2 - Color-code intake icons.** Use tiffany for link, navy for upload, and coral for note.
- [x] **H3 - Restore the user identity block.** Show an avatar, display name, and email and remove duplicate settings/profile links from the rail.
- [x] **H4 - Add the Stock side-link.** Keep `Stock - Public market research` immediately above the user block.
- [x] **H5 - Restore the circular search send control.** Use a 38px circular tiffany icon button inside the search pill.

## Verification log

- [x] Report text extracted and all five pages visually reviewed.
- [x] Full frontend test suite passes: 21 files, 123 tests.
- [x] ESLint passes with zero warnings.
- [x] Production frontend build passes.
- [x] Browser-level visual review completed for Overview, Documents, Memo Studio, Company News, Industry Views, docked Co-Pilot, sidebar, and Home.
- [x] English and Chinese modes reviewed; existing error states and server-provided option labels switch reactively.

## Completion notes

- Shared formatting now normalizes large numbers, pending values, ISO dates, and backend status labels.
- Company workspace surfaces share one co-head, a joined metric strip, editorial positioning, consistent white card anatomy, and coral active tabs.
- Documents, Memo Studio, News, and Industry Views now use the specified information architecture and designed empty/error states.
- Co-Pilot is docked on desktop with a context header, research-task card, composer, and quick actions; mobile behavior remains fixed and collapsible.
- Sidebar and Home now match the status, identity, intake-color, stock-link, and circular search-control requirements.
- Raw backend paths, provider names, status enums, and request error payloads were removed from the remediated user-facing states.
