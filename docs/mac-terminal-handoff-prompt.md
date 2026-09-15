# Handoff prompt — BSH Research macOS terminal, Phases 4–6 + Apple-grade polish

Paste everything below this line into the next model.

---

You are continuing work on **BSH Research Center**, a FastAPI + Vue + native Apple-client app that a venture firm (Berkeley Summit House; analyst persona "Serena") uses to research companies, run AI-generated investment memos, record decisions and monitor a book. Your job is to turn the **native macOS app** into a "Bloomberg Terminal for private companies that also does public companies", with an Apple-grade, keyboard-first, fast UI. Three phases of that work are already built and uncommitted; you will build the next three phases and the polish layer described here. **Do not remove or regress any existing feature.**

## 0. Ground rules (non-negotiable)

- Repo root: `/Users/bilelharrrat/BSH Updated UI From Main Repo /` (note the trailing space in the folder name — always quote paths). Read `CLAUDE.md` and `docs/architecture.md` first and obey them.
- **All work happens on `main`.** No branches, no worktrees. Commit only when the user asks. Sign commits with `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Verification gate before you say anything is done:
  ```sh
  uv run python -m pytest              # backend, ~1–4 min, no network/LLM calls
  npm --prefix frontend test           # vitest
  npm --prefix frontend run lint       # eslint --max-warnings=0
  uv run ruff check server scripts tests
  cd ios && xcodegen generate && xcodebuild -project BSHResearch.xcodeproj -scheme BSHResearchMac -configuration Debug -destination 'platform=macOS' -derivedDataPath build/DerivedDataMacPhase1 CODE_SIGNING_ALLOWED=NO build
  ```
  The Mac build must finish with **zero warnings in `ios/BSHResearchMac/`**. Never run tests marked `e2e` (they spawn a paid Claude CLI).
- The Xcode project is generated from `ios/project.yml` by XcodeGen. If you add a Swift file, run `xcodegen generate` (it picks up files automatically); never hand-edit `project.pbxproj`.
- You cannot see the user's screen. After each phase, launch the built `.app` (`open -n ios/build/DerivedDataMacPhase1/Build/Products/Debug/BSHResearchMac.app`), confirm it stays alive for 15 s with `pgrep -x BSHResearchMac`, check `log show --last 60s --predicate 'process == "BSHResearchMac" AND messageType == error'`, then quit it. Then ask the user to look.
- Before touching any existing view, run this feature-loss audit and keep its output empty except for deliberate renames you list explicitly:
  ```sh
  git show HEAD:ios/BSHResearchMac/... | grep -oE '(Label|Button|Text|Section|Toggle|Picker)\("[^"]{3,}"' | sort -u   # vs the same grep over the working tree
  ```
- The user's design bar: **Apple-like, clean, fast, interactive** — Linear/Raycast/Things-level craft, not a web dashboard in a window. Density is welcome; noise is not.

## 1. Current state of the repo (uncommitted — do not lose it)

`git status` shows a large uncommitted Mac-app change set plus a small backend/web change. **Commit nothing until the user asks**, but never `git checkout`/`stash` these files away. The Watch app files (`ios/BSHResearchWatch/*`) and `ios/BSHResearch/Info.plist` are the user's own unrelated edits — leave them alone.

What the uncommitted work added (Phases 1–3 of the roadmap in `docs/` history; see the synthesis in the conversation that produced it):

**Phase 1 — Foundation**: Keychain session + login sheet + roles/permissions (`MacConfig.swift`, `MacLoginView.swift`, `MacAppStore.session`, `store.can("tasks:action")` etc.); one shared `MacAppStore` across all windows (`BSHResearchMacApp.swift`); memo reader as its own `WindowGroup(id: "memo")` (`MacMemoWindowView.swift`); Jobs & Alerts blotter with live SSE logs and macOS notifications (`MacBlotterView.swift`, `MacNotifier`); ⌘K command palette with Bloomberg-style codes `NAME MEMO|DES|GP|Q|N|NEW|ASK` (`MacCommandPalette.swift`); fixed `/api/options` loading, desk-prefs read-modify-write, web deep links, Market Pulse/Key-Stats decoders, stuck "Thinking…" bubble.

**Phase 2 — Deal desk**: Pipeline board `Table` (⌘2) over `GET /api/tracking/rollup` + follow list (`MacPipelineDeskView.swift`); Record Decision sheet ⌘D + decision timeline with retrospectives (`MacDecisionSheet.swift`); IC Review `WindowGroup(id: "ic")` = memo beside thesis spine/risks/evidence/decision form (`MacICReviewWindowView.swift`); IC Prep card with readiness gates, reviewed/waived areas, ranked risk cards, tool runs, "Approve for memo" (`MacICPrepView.swift`); Portfolio & Watch desk (⌘8) with tracked news, auto-run Execute, re-underwriting filter (`MacPortfolioDeskView.swift`).

**Phase 3 — Edge**: context-aware Ask Warren — every Ask sends `context` (`MacCopilotContext`), chat shows context chip + server-suggested actions + source chips, Deep mode; **fixed a real bug**: the copilot stream sends no token deltas, the final answer is on the `done` event's `text` (`MacAPIClient.pumpConsoleStream`); Attention Queue desk ⌘0 (`MacAttentionDeskView.swift`) from `/api/desk/screener`, `/api/desk/digest?since=lastLaunch`, `/api/intake/unresolved`; Thesis Tracker (`MacThesisTrackerView.swift`) with jump-to-passage in the memo (`MacPDFKitView.findText`); persistent Console sessions with attachments, cancel, archive (`MacConsoleView.swift`, multipart `askConsole`); Signal log ⌘L as third blotter tab (`MacSignalsPane`).

**Backend/web (also uncommitted)**: `server/tracking_dashboard.py` now emits `lifecycle_stage` (`sourcing|screening|diligence|ic|portfolio|watch|passed`) and `latest_decision` on every rollup row (tests in `tests/test_tracking_dashboard.py`); `frontend/src/views/TrackingView.vue` shows the stage badge (i18n keys `tracking.stage_*` in `frontend/src/i18n.js`, EN + ZH).

**Open issue to investigate first**: the user says the Mac app now "looks way different" from what they remember and is "missing so many features". A label-level audit found nothing removed except intentional renames, so either they were looking at a different build/scheme (e.g. the iPad app on "My Mac (Designed for iPad)") or at a version that never lived on `main`. Ask them for one concrete example before changing anything, and check `git log --all -- ios/BSHResearchMac` and the `redesign` remote (`bilelharrat/BSH-Research-Center-UI-Redesign-`) for a divergent Mac app.

## 2. Map of the code you will touch

Mac app (`ios/BSHResearchMac/`, SwiftUI, macOS 14+, sandboxed, `com.apple.security.files.user-selected.read-write` + network client):
- `BSHResearchMacApp.swift` — scenes (`main`, `memo`, `ic`, Settings) and all menus/shortcuts. Every action must exist here as a menu item with its shortcut.
- `MacRootView.swift` — `MacTab` enum, sidebar, detail `HSplitView`, blotter strip, toolbar, sheets (login, new report, decision, command palette).
- `MacAppStore.swift` — the single `@MainActor ObservableObject`; sections: session, home/market/news/pulse refresh, desk prefs, jobs & alerts loops, pipeline/decisions/tracking/IC prep/evidence, memo loading, copilot, attention, signals, console.
- `MacAPIClient.swift` — actor; `request/requestVoid/rawData` with per-call `timeout`, `streamEvents(path:)` SSE reader, multipart `askConsole`. Bearer from Keychain, header `X-BSH-Client: macos`.
- `MacMemoModels.swift`, `MacDeskModels.swift` — every decoder is lenient (custom `init(from:)`, `try?`, optional everything) because server dicts drift. Keep that style.
- `Views/` — one file per desk/window. Shared bits: `MacSharedViews.swift` (`MacStatusPill`, `MacMonogram`), `MacPaperDeskReader.swift` (`MacPDFKitView` with `findText`, `onSelection`, `onPageChange`; `MacQuickLookView`).
- iOS app in `ios/BSHResearch/` is the reference for patterns (`Networking/APIClient.swift`, `SSEClient.swift`, `TokenStore.swift`, `Views/Search/ReportDetailView.swift`). Don't change it unless a Phase needs a shared model.

Backend (`server/`, FastAPI, all routes under `/api`, `router` requires a session token or anon-dev; permissions via `_require_permission(request, "…")` with roles in `product_store.ROLE_PERMISSIONS` — `tasks:action`, `memo:edit`, `desk:write`, `sources:edit`, `documents:delete`, `settings:update`). Modules you will build on: `tracking_dashboard.py` (rollup), `tracking_updates.py` (tracked news, auto-runs), `decisions_store.py`, `serena_analysis.py` (Memo Studio session: readiness, tools, thesis spine, risk cards), `evidence_matrix.py`, `evidence_store.py` (intake/unresolved uploads), `deck_summary.py` (per-file structured summaries), `copilot.py` + `console_session.py`/`console_store.py` (Claude sessions, SSE via `job_progress.py`), `desk_digest.py`, `desk_store.py` (prefs, alerts, signal ledger), `live_quotes.py` + `quote_workspace.py` (public quotes, fundamentals, news), `hypothesis_store.py`/`hypothesis_cycle.py`, `memo_docx_renderer.py` (DOCX output, EN/ZH), `storage.py` (YAML companies/reports), `research_store.py` (`data/research/<slug>/`), `files_store.py` (`data/uploads/<slug>/`).

Data lives under `data/` (gitignored). Two hard rules from `docs/architecture.md`: the memo pipeline never reads `data/uploads/`, and Python never renders memo judgment — Claude emits structured content, Python validates and renders.

Exact JSON shapes for the endpoints already consumed are encoded in the Swift decoders; when you add an endpoint, read the handler in `server/api.py` (grep `@router.get("/…")`) and the store module, and write a lenient decoder.

## 3. What to build — Phases 4, 5, 6 and the polish layer

Research basis (VC tooling surveys and practitioner posts, 2025–26): firms pay $60–150K/yr for Affinity + PitchBook/Harmonic + AlphaSense + Carta and still complain about stale private data, CRMs that die from manual entry, no single screen, painful founder-data collection, and no public+private in one place; 65% build internal tools. The most-requested features that a small firm can build without buying data are: inbound intake with thesis scoring, signal detection (hiring/web/GitHub), "what changed" diffs, memos with sentence-level sources (already have), burn/runway alerts, LP tear sheets, private-vs-public comps, dilution/waterfall, founder/investor graph. Skip: chat network, expert transcripts, predictive success scoring, ticker tape.

Build in this order unless the user reorders: **12 → 1 → 3 → 14/15 → 5 → 9**, then the rest.

### Phase 4 — Inbound & signals

1. **Forward-a-deck intake.** Mac: drag a PDF/PPTX/DOCX or an `.eml` onto the Pipeline (or ⌘K → "Intake…" → file picker) → `POST` it to a new `POST /api/intake/decks` (multipart) that stores it under `data/uploads/<slug>/` via `files_store`, runs `deck_summary` to extract company name, stage, round size/ask, key metrics **with page references**, matches/creates the company (`storage.upsert_company_from_match`), scores it against the firm's thesis (item 4), and returns `{company, extraction: {fields:[{name,value,page,excerpt}]}, thesis_score}`. Show an "Intake" sheet: extracted fields (editable, each with a "p.N" chip that opens Quick Look at that page), score, "Add to pipeline as Sourcing". Keep the existing intake/unresolved flow working.
2. **Signal watch.** New `server/signals_watch.py` + `data/signals/<slug>/snapshots.jsonl`: per company, a weekly snapshot job (reuse the job pattern from `tracking_updates.sync_all_tracked`, run via `POST /api/signals/watch/sync`) capturing: open job postings count (careers page + Greenhouse/Lever/Ashby JSON endpoints when present), headcount (LinkedIn "employees" text from the company page HTML if fetchable, else skip), GitHub org stars/forks/contributors (public API), App Store/Play rank if an app id is on the record, website change hash. Expose `GET /api/companies/{id}/signals` → `{snapshots:[…], deltas:{jobs_30d_pct, headcount_30d_pct, stars_30d, …}}`. Mac: a "Signals" card on the dossier and delta badges on Pipeline rows; the Attention Queue gets a "Signals moved" section. Every fetch must be best-effort with timeouts; never block the rollup.
3. **"What changed" diffs.** Mac: persist a per-launch baseline (companies, reports statuses, rollup rows, quotes) in the local cache (item 12) and render diff badges ("memo: running → complete", "stage: diligence → ic", "+2 high-impact news") on Pipeline rows and the dossier header; the Attention desk's "since last launch" section merges these with the server digest.
4. **Thesis filters.** `GET/PUT /api/thesis` (store under `data/settings/thesis.yaml`; sectors, stages, geographies, check size, must-be-true statements, disqualifiers). Score = rule matches + Claude-free keyword overlap; expose `POST /api/thesis/score` used by intake and shown as a column on the Pipeline ("Fit 72%"). Mac: Settings → Thesis editor (Form), and the score column.

### Phase 5 — Public ↔ private fusion

5. **Comps rail.** Per private company a peer set of public tickers (editable, default from the memo's "comparable companies" facts if present, else the company's sector). Backend `GET /api/companies/{id}/comps` returns, per peer, `market_cap, ev, revenue_ttm, growth_yoy, ev_to_revenue` from `quote_workspace` fundamentals (already fetched for Market Radar), plus the private company's last-round post-money and any revenue figure **only if it exists in the memo fact index** (`data/memos/<slug>/…/logs/memo_package.json` — read via the report record; never scrape revenue). Mac: a "Comps" card on the dossier and in IC Review with tabular-digit columns and a one-line "implied multiple vs peer median" sentence; every number gets a source chip (memo page or quote timestamp).
6. **Round & dilution model.** `GET/PUT /api/companies/{id}/cap-model` (pre/post-money, option pool, new money, pro-rata, three exit values) → waterfall table. Pure arithmetic in Python with tests. Mac: "Round model" sheet from the dossier and a summary line in IC Review.
7. **MCP connectors.** Settings → Data connectors: PitchBook, Sacra, Harmonic, Forge each as `{name, mcp_url, token}` stored server-side (`product_store` preferences); when configured, `copilot.py` adds the connector as an MCP server for Ask Warren/Console (check how `claude_runner.py` launches the CLI and pass `--mcp-config`). Mac shows connector status pills; nothing breaks when none are configured.
8. **Secondary marks.** Ingest the public Forge Private Market Index (`^FPMI` via the existing quotes path) for a "private market tape" pill on the Portfolio desk; optional Caplight/Forge/Notice API keys through the connectors panel, showing a "mark" column on Portfolio rows when available.

### Phase 6 — Portfolio & LP

9. **Founder update ingestion.** Drop an email/PDF update on a Portfolio row → `POST /api/companies/{id}/updates` → `deck_summary`-style extraction into a KPI table (`arr, mrr, burn, cash, runway_months, headcount, pipeline`) with sentence/page sources; store `data/companies/<slug>/kpis.jsonl`. Alerts: runway < 9 months, burn up > 25% QoQ, ARR down → fire into `desk_store` alert events (the blotter Alerts tab already renders them) and macOS notifications.
10. **LP tear sheets.** `POST /api/companies/{id}/tear-sheet?lang=en|zh` → DOCX via `memo_docx_renderer` (decision + thesis spine + KPIs + latest memo exec summary + tracked news since the last sheet). Mac: "Tear sheet" button on Portfolio rows, opens in the memo window; "Quarterly letter draft" runs a Console session with all tear sheets staged.
11. **Founder/investor graph.** Backend `GET /api/graph?company_id=` from memo facts (investors, board, founders' prior companies) + decisions; Mac: an inspector section "Connections" (people/firms with counts, click → filter Pipeline). No external data.

### Terminal polish — the Apple-grade layer (do item 12 first)

12. **Local-first cache.** SwiftData or SQLite (GRDB is not vendored — prefer SwiftData or `NSCache`+disk JSON) holding companies, reports, rollup, quotes, decisions, recent news; every desk renders from cache immediately and refreshes in the background; show a subtle "updated 12s ago" in the footer, never a spinner on a desk that has cached data. Target: any desk switch paints in <100 ms.
13. **Linked panes across windows.** Selecting a company anywhere updates `store.selectedCompany`; memo/IC windows show a lock toggle (🔒 follows selection / pinned). Inspector always follows.
14. **Keyboard grammar.** Single keys when no text field is focused: `C` new company (intake), `N` new memo, `D` decision, `F` follow, `/` or ⌘K command bar, `?` shortcut overlay (a sheet listing everything), `G` then `P/R/D/M/N/A` go-to desk; j/k in every list/table; ⏎ opens, ⌘⏎ opens in new window. All shortcuts also appear in menus.
15. **Row craft.** `.monospacedDigit()` on every numeric `Text`; hover-revealed row actions (`.onHover` + opacity) on Pipeline/Portfolio/Blotter rows; semantic colours only for up/down/high; one accent; grey-scale hierarchy (`.secondary`/`.tertiary`); animations 0.18–0.22 s ease-out, springs only for spatial moves; dark-mode audit with contrast ≥4.5:1 (no pure black backgrounds — use `windowBackgroundColor`/materials).
16. **Native surfaces.** Drag a memo row to Finder/Mail as its PDF (`NSItemProvider` file promise from the temp memo URL); drag a table selection to Numbers/Excel as CSV; space-bar Quick Look on any file row (`QLPreviewPanel`); Share toolbar button (`ShareLink`) on memo windows; a **menu-bar extra** (`MenuBarExtra`) showing running jobs + last fired alert + quick ⌘K; Services/Shortcuts: expose "Open company", "New memo" as App Intents.
17. **Saved workspaces.** "Window › Save Workspace…" stores the set of open scenes (main tab, memo/IC requests, blotter state) in `UserDefaults`; "Restore" reopens them via `openWindow`. Name them ("IC Monday", "Market open").

## 4. Definition of done for each item

- Backend: route + store module + tests (`tests/test_<module>.py`, no network — monkeypatch fetches), ruff clean.
- Mac: model decoder (lenient) + API client method + store method (MainActor, `error` surfaced, permission-gated with `store.can(...)`) + view + menu item with shortcut + `.help()` tooltips; builds with zero warnings; smoke-launch passes.
- Web: only if the feature has a web counterpart already (e.g. thesis score on `TrackingView.vue`); keep EN/ZH i18n keys in `frontend/src/i18n.js`; lint + vitest clean.
- Update `docs/architecture.md` with any new module in one line each.
- Report faithfully: if a test fails or a step was skipped, say so with the output.

## 5. Working style

- Read before writing: `sed -n`/grep the handler and store for exact dict keys; do not guess field names.
- Use lenient Swift decoders; server dicts have nulls and drift.
- Keep every existing desk's content; the Research Desk, Documents desk, Market Radar, News, Pulse, Ask Warren, Inspector and embedded browser are all in use.
- Prefer one shared store method over per-view fetching; never fetch `memo-analysis` per company on list screens (it creates a Serena session server-side).
- Long server operations (`tracking/sync-all`, deck ingestion) run detached from the UI with a notification on completion and progress in the blotter.
- After each phase: build, smoke-launch, run the feature-loss audit, then summarize what the user should look at and stop for feedback. Do not commit unless asked.
