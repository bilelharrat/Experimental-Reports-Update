# BSH Research Center PRD by SS - Extracted Text

Source: `BSH_Research_Center_PRD_by_SS.docx`

BERKELEY SUMMIT HOUSE

Research Center

Product Requirements Document

Version 2.0  ·  Engineering Handoff

Prepared for the engineering team. Companion document: BSH Research Center — Design System v2 (HTML). This PRD describes the product scope, users, information architecture, feature requirements, flows, and acceptance criteria for the AI-assisted investment-research and memo-drafting workspace.

Status: Draft for review   ·   Owner:Seline   ·   Date: July 1, 2026

Contents

1. Overview & Purpose

The BSH Research Center is an AI-assisted workspace where venture investors research private and public companies.

It replaces a fragmented workflow, scattered documents, ad-hoc notes, and manually written memos with a single, opinionated environment in which an AI co-pilot gathers evidence, surfaces disconfirming signals, and helps assemble a structured, defensible memo.

The product is built as an “Editorial Terminal”

1.1 Product Overview

A partner types a company name and, within one workspace, moves from raw signals to a structured, evidence-backed memo, with an AI co-pilot acting as a research peer throughout, and every key figure traceable to a source.

2. Goals & Success Metrics

2.1 Goals

Compress the time from “company of interest” to a first-draft investment memo from days to hours.

Make every highlight and risk in a memo checkable, rankable, and traceable to evidence.

Keep the analyst in control: AI proposes; the human edits, ranks, and decides.

Present dense financial material without cognitive overload.

2.2 Success Metrics

2.3 Non-Goals (v2)

Portfolio accounting, cap-table management, or fund administration.

Executing trades, wiring funds, or any transaction on the user’s behalf.

3. Target Users & Personas

4. Design Principles

The interface follows the BSH Design System v2 (delivered separately as an interactive HTML reference). Engineering should treat that document as the source of truth for tokens and components. Core principles:

Breathable density. Whitespace and hairline borders organize dense data; avoid heavy chrome.

Restrained color. Near-monochrome slate/pearl base; Tiffany (#0ABAB5) accent used sparingly for action and positive signal; Coral for risk; Amber for caution.

Numbers are data. All metrics, valuations, ranks, and dates use a monospaced face.

Flat elevation. Soft, low-opacity shadows and hairline borders; no skeuomorphism.

Co-pilot as peer. Discussion routes to a single slide-in co-pilot panel rather than chat boxes scattered across the UI.

5. Information Architecture

The application is a three-zone shell: a persistent left navigation rail, a central content area that switches between views, and a co-pilot panel that slides in on demand from the right.

5.1 Global Shell

Left rail (288px). Signature teal-gradient panel: logo, Quick Intake, and the Companies list (Portfolio / Pipeline / Watchlist buckets). Persistent across all views.

Central content. Hosts the active view: Home, Company Workspace, Competitor detail, Settings, or User Center.

Co-pilot panel (372px). Opens via a floating “Ask Co-Pilot” button available on every view; hides while open.

Breadcrumb + header. Shows context (Research Center › Company › Section) and account entry points (Settings, User Center).

5.2 Company Workspace Sub-Views

Within a company, five sub-tabs organize the work: Overview, Documents, Memo Studio, Company News, and Industry Views (which includes Expert Opinions).

6. Features & Requirements

6.1 Home — Find a Company

The landing view centers on a single search action, with a prominent instruction and a Quick Add panel beneath the search box for ingesting material.

Prominent prompt: “Type a company name and press Enter to search. Existing researched or public companies will autocomplete.”

Search accepts private (already-researched) and public companies; autocomplete surfaces both.

Quick Add panel directly under the search box: Submit a Link (archive & summarize a URL), Upload External Research (PDF / DOCX; summarize & translate), Add Research (internal note, PDF optional), and a Source Library & Appendix link.

6.2 Company Workspace — Overview

The Overview is the analyst’s at-a-glance company brief and the default landing when a company is opened. The five sub-tabs (Overview, Documents, Memo Studio, Company News, Industry Views) sit directly beneath the company header.

Company header

Monogram tile plus the company name (e.g., “ZaiNar, Inc.”).

Stage / sector tags beside the name (e.g., “Series B”, “Physical AI”).

One-line metadata beneath the name: founded year, HQ, and headcount (e.g., “Founded 2017 · Belmont, California, USA · 50–200 employees”).

Funding line — top-right, emphasized. Last round, post-money valuation, round date, and total raised, with the figures enlarged and in mono (e.g., “Last round: $100M+ · post-money $1.0B+ · (2026-02-19) · Total raised: $100M+”).

Positioning summary

A bordered, full-width frame rendered in a single uniform weight, using the template: “[Company] is a [category] for [customer] who [need], that [benefit]. Unlike [alternative], it [differentiator].”

Example — ZaiNar is a network-based positioning platform for healthcare, construction, and industrial enterprises who need precise location indoors and where GPS fails, that locates any device to sub-meter accuracy in real time. Unlike GPS or dedicated UWB / RTLS hardware, it leverages existing 5G and Wi-Fi networks as a software sensing layer to deliver it with no new hardware.

Metric strip

Four cells with mono values: ARR (~$24M), YoY Growth (+180%), Valuation ($1.0B+), and TAM (~$45B).

Core Team

A “Core Team” card of founder / advisor cards; each shows a monogram avatar, name, role, a one-line bio, and LinkedIn + Profile links.

Products

A titled product grid with a count. Each card = product name + one-line description. Click the card will go to the product detailed introduction page.

Competitors

A competitor grid with a count

Each card = monogram, name, a Public/Private tag, a one-line note, and a “View profile & compare →” action that opens the Competitor detail view:

NextNav (Public) — closest listed terrestrial-PNT pure-play (NASDAQ); primary public comp.

Skyhook (Public) — Wi-Fi positioning under Qualcomm; broad device-level reach.

Ubisense (Private) — UWB real-time location for industrial and manufacturing.

GXC (Private) — private-5G networking with integrated sensing heritage.

HERE (Private) — mapping & location platform; automotive and enterprise.

Card-set actions: “Compare to ZaiNar →” and “+ Add competitor”.

Investors & Cap Table

Two columns under a “Board · Cap Table” label.

Board & Lead Investors, rows with avatar, name, and role/affiliation plus a profile/firm link.

Cap Table Lineage,  proportional ownership bars with linked holders: Koch Disruptive Technologies 18.5%, Foundation Capital 12.0%, Founders 65.0% (percentages in mono).

6.3 Documents

Document rows grouped by category: Company Materials, Legal, Financial, and External Reports,Internal Notes & Sources

Each row shows type badge, name, meta, and quick actions; supports upload and provenance tagging.

6.4 Memo Studio (flagship)

The memo is organized into five top-level sections. A compact task board at the top shows generation progress (Section X of 5), plus Export Memo, Regenerate, and a live status.

Section structure

Executive Summary — a one-paragraph synthesis and headline recommendation, with key sub-boxes (recommendation, round, top gate).

Investment Thesis — the AI runs across categ ories (Market & Opportunity; Product & Technology / Moat; The Team; Business Model; Competitive Landscape; Financials; Return / Exit) and surfaces 3–5 highlights.

Risks & Mitigations — the AI runs across categories (the thesis set plus Geopolitics and Macro) and surfaces 3–5 risks.

Conclusion — invest-or-not framing (conditional / lead & anchor / pass).

Appendix — supporting fact blocks (Company Overview, Business Model, Market Context, Technology/IP & Competitive Position, Team & Investor Base, Investment Risks & Model Treatment, Return Framework & Exit Scenarios, Evidence Required for a Step-Up Case, Sources/Source Classes/Disclosures), collapsed by default.

Highlight & risk card behavior

Each highlight/risk is a card with a left-rail: an include checkbox, rank up/down arrows, and a mono index. Ranking renumbers within its section only (Thesis and Risks number independently from 1).

Clicking a card expands a dropdown of supporting bullet points.

Each bullet exposes, on hover, three actions: Edit (inline), Dive Deeper (appends a nested, AI-expanded sub-point — recursively), and Discuss (opens the co-pilot with that point as context). No inline chat box is embedded in cards.

Left-border color encodes category/severity: Tiffany (thesis), Coral, Amber, Indigo, Slate.

Summary & conclusion sections

Rendered as prose cards with a Rerun action and option sub-boxes, consistent with the current design.

6.5 Company News

Reverse-chronological feed of company-specific items with source, category dot, and external-link affordance.

Add AI-generated tags to news items so users can filter by category (e.g., fundraising, product launch).

6.6 Industry Views & Expert Opinions

Sector header with a metric strip (Sector TAM, CAGR, tracked comps, median multiple).

Expert Opinions (Notable Voices): quoted investor/operator/analyst views with stance chips (Bullish / Neutral / Cautious), placed above the Public Comps / Sector Signals grid.

Public Comps cards with sparklines; Sector Signals as categorized alert cards.

6.7 Competitor / Comps Detail

Dedicated detail view per competitor, reachable from Insights and Comps; includes benchmark, win/loss, and patent-overlap placeholders.

6.8 AI Co-Pilot

Slide-in panel (372px) available on every view via a floating button; context-aware (knows the current company and section).

Message types: user prompt (Deep Slate bubble), AI response (surface-alt bubble), and Research Task (Tiffany-tinted) that can be actioned into the memo.

“Dive Deeper” and “Discuss” actions across the app pipe context into the co-pilot.

6.9 Settings & User Center

Account, workspace, and preference management; user profile / center reachable from the header.

6.10 Language switch

A persistent English/Chinese toggle in the top-right header lets users switch the interface language between EN and 中文. The control reflects the active language and applies globally; all UI chrome, labels, and AI-generated summaries should be localizable, with ingested external research summarized and translated into the selected language.

6.11 Public Market Research (Stock)

The left navigation includes a Stock entry that opens a dedicated Public Market Research view.

7. Key User Flows

7.1 Research a new company → first memo draft

Partner types a company name on Home and presses Enter (autocomplete assists).

Workspace opens on Overview; metric strip, positioning summary, and team populate.

Partner opens Memo Studio; if it’s the first time of searching this company then partners should click” generate” to get the first version of memo. After click “generate” the AI generates sections, showing progress on the task board. If the company has been researched before, then opening Memo Studio should show the latest version Memo.

Partner reviews Investment Thesis highlights: checks the ones to include, ranks them, expands bullets.

For a weak point, partner clicks Dive Deeper (nested detail) or Discuss (co-pilot).

Partner reviews Risks & Mitigations the same way, sets the Conclusion framing, and clicks Export Memo.

All the exported memos go to [Documents]-[Memos]

7.2 Ingest external evidence

From Home Quick Add or the sidebar Quick Intake, the user submits a link, uploads a PDF/DOCX, or adds an internal note.

The item is archived, summarized (and translated if needed), and filed under the right Documents category with provenance.

Relevant facts become available to the co-pilot and to memo generation.

When a file is uploaded via the homepage or sidebar, the AI should read its content and automatically sort it into the correct company's 'Uploaded Documents' section.

8. Functional Requirements

Priority: P0 = must-have for launch, P1 = important, P2 = later. Each requirement includes its acceptance criterion.

9. Non-Functional Requirements

10. Data & Integrations

Source classes. Company materials (deck, data room), public filings (standards, patents), third-party market data (news, research), and BSH primary diligence.

Ingestion. URL archiving + summarization; PDF/DOCX parsing, summarization, and translation; internal note capture.

Disclosures. Position/interest disclosures maintained and shown in the Sources appendix.

AI generation. Section drafting, thesis/risk extraction across categories, and co-pilot dialogue; all outputs human-editable.

11. Milestones & Phasing

12. Open Questions & Assumptions

Confirm final naming for internal-note ingestion (generic “Add Research” vs. a codename) across Home and sidebar.

Confirm memo Export target(s): PDF, DOCX, or shareable link.

Confirm contrast requirements for muted labels over the tinted sidebar to meet AA.

Define retention/versioning policy for memo edits and rank history.

Appendix A. Glossary

## Table 1

| Metric | Target |
| --- | --- |
| Median time to first memo draft | < 2 hours from first search |
| Memos with all key figures source-linked | 100% |
| Weekly active partners / analysts | ≥ 80% of licensed seats |
| Co-pilot task acceptance rate | ≥ 60% of proposed research tasks actioned |
| Sections reused vs. re-generated | Trending down over time (rising trust) |

## Table 2

| Persona | Needs | Primary surfaces |
| --- | --- | --- |
| VC Partner | Fast, high-signal read on a company; a defensible memo and clear recommendation; ability to rank what matters. | Overview, Memo Studio, Co-pilot |
| Investment Analyst | Gather and organize evidence; draft memo sections; run comparables and news; manage documents. | Documents, Memo Studio, Industry Views, Quick Intake |
| Research / Ops | Ingest external material, maintain the source library, ensure provenance and disclosures. | Quick Intake, Documents, Appendix / Sources |

## Table 3

| ID | Requirement & acceptance criterion | Priority |
| --- | --- | --- |
| FR-1 | Global search accepts a company name and opens the corresponding workspace; autocomplete suggests researched and public companies. Accept: pressing Enter on a valid name routes to Overview within 2s. | P0 |
| FR-2 | Quick Add / Quick Intake supports link submission, PDF/DOCX upload, and internal notes. Accept: an uploaded PDF is summarized and filed under a Documents category with a visible source. | P0 |
| FR-3 | Company Overview renders header, positioning summary, metric strip, team, insights, and investors. Accept: all key figures render in the mono face and match source data. | P0 |
| FR-4 | Memo Studio generates the five-section memo and shows generation progress. Accept: each section shows a status (Done / Ready / Not started) and a Rerun action. | P0 |
| FR-5 | Thesis and Risk highlights are checkable, rankable, and expandable. Accept: toggling include updates state; rank arrows reorder and renumber within the section only (each starts at 1). | P0 |
| FR-6 | Each bullet supports Edit, Dive Deeper (recursive nested expansion), and Discuss (opens co-pilot with context). Accept: Dive Deeper appends a nested sub-point that itself supports the same actions. | P0 |
| FR-7 | Appendix fact blocks are collapsed by default and expand on demand. Accept: all appendix sections load collapsed; expanding one does not affect others. | P1 |
| FR-8 | Co-pilot panel is reachable on every view and is context-aware. Accept: the floating button appears on Home, Workspace, Competitor, Settings, and User Center; opening it shows the current context. | P0 |
| FR-9 | Documents are grouped by Legal / Financial / External Reports with provenance. Accept: each document displays type, source, and date. | P1 |
| FR-10 | Industry Views shows Expert Opinions above the Comps/Signals grid, with stance chips. Accept: opinions render with Bullish/Neutral/Cautious styling and source lines. | P1 |
| FR-11 | Company News renders a reverse-chronological, source-attributed feed. Accept: items show source, category, and recency; external links open safely. | P1 |
| FR-12 | Export Memo produces a shareable memo reflecting included, ranked sections. Accept: excluded highlights/risks are omitted; order matches the on-screen rank. | P0 |
| FR-13 | Every quantitative claim in a memo links to a source or source class. Accept: no key figure ships without provenance; disclosures appear in the Sources appendix. | P0 |
| FR-14 | Settings and User Center are reachable from the header. Accept: both open as dedicated views and return cleanly to prior context. | P2 |

## Table 4

| Area | Requirement |
| --- | --- |
| Performance | Primary views interactive < 2s on a warm cache; memo section generation is streamed with visible progress. |
| Accessibility | WCAG 2.1 AA: keyboard operability for checkboxes, ranking, expansion, and edit; visible focus; sufficient contrast (note: verify muted text on tinted sidebar). |
| Responsiveness | Optimized for desktop ≥ 1280px; graceful reflow of three-zone shell when the co-pilot opens. |
| Browser support | Latest Chrome, Edge, Safari, Firefox. |
| Security & privacy | Role-based access to workspaces; provenance retained; no execution of financial transactions from the tool. |
| Trust & provenance | Source class (company / public / third-party) and disclosures tracked and surfaced; AI outputs are editable and attributable. |
| Auditability | Edits, rank order, and inclusion decisions are recoverable for a given memo version. |

## Table 5

| Phase | Scope |
| --- | --- |
| M1 — Foundations | Global shell, sidebar, Home search + Quick Add, Company Overview, design-system tokens/components. |
| M2 — Memo Studio | Five-section memo, highlight/risk cards (check/rank/expand), bullet actions (edit/deeper/discuss), Export. |
| M3 — Evidence | Documents, ingestion pipeline, provenance & disclosures, Appendix fact blocks. |
| M4 — Context | Company News, Industry Views + Expert Opinions, Competitor detail, co-pilot refinements. |
| M5 — Polish | Settings/User Center, accessibility pass, performance, audit trail. |

## Table 6

| Term | Meaning |
| --- | --- |
| Memo Studio | The workspace for generating and editing the five-section investment memo. |
| Highlight | A checkable, rankable thesis point with expandable supporting bullets. |
| Risk | A checkable, rankable risk with mitigation and evidence bullets. |
| Dive Deeper | Action that appends an AI-expanded nested sub-point beneath a bullet. |
| Co-Pilot | The context-aware AI panel that handles discussion and research tasks. |
| Source class | Provenance category: company, public, or third-party. |
