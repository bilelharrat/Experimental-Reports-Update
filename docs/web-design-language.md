# Web design language

The web app has three designs. **Bureau** (the page on the desk) is the
default. **Folio** (paper and ink) and **Summit Glass**, the Mac twin
described in the rest of this document, stay one click away in Settings →
Preferences → Design. The choice is kept per browser (`bsh.research.design`)
and set as `data-design` on `<html>` before first paint (`index.html`,
`src/design.js`), which also gives the browser chrome the design's ground.
The iPhone/iPad and Mac apps offer the same three designs with the same
colors and faces. Each device keeps its own choice. See "Designs" in
`ios/README.md`.

## Bureau

Everything Bureau changes lives in `frontend/src/bureau.css`, scoped under
`:root[data-design="bureau"]`. Four rules:

- **A page on a desk.** The window is a bottle-green desk (`--bureau-frame`,
  `15 31 26`) with a faint grain and a warm lamp glow in its top-left corner;
  the work is one ivory sheet (`--bureau-sheet`, `247 244 236`) laid on it
  (`.app-sheet`, the routed view's wrapper in `App.vue`). Chrome lives on the
  desk: the masthead, the company rail, the drawer. Inside the sheet a group
  is a tray pressed a shade into the paper (`surface`, drawn with an inset
  edge, never lifted); only what sits over the page — menus, dialogs, the
  command palette, fields and chosen chips — is fresh paper
  (`surface-raised`) with a shadow. Nothing blurs.
- **Where you are is cut from the page.** The desks are index tabs along the
  top edge of the sheet and the companies a rail of logos down its left edge.
  The one you are on is made of the sheet itself (`--bureau-sheet`) and its
  corners flare into it, so tab and page read as one piece of paper; a small
  brass notch sits over the tab's label. On the rail, a company whose folder
  is open becomes a single tab holding its logo and page glyphs, with the
  page on screen picked out in brass — the rail never shows two tabs. Inside
  the sheet, a chosen segment or row is a slip of fresh paper lifted from it
  (`.segmented`, `.doc-row`, `.mac-row`, Market ranges).
- **Brass is for acting.** The accent is brass (`148 112 47`), deep enough
  that white type on it passes AA, so a view's own `bg-accent text-white`
  stays legible: primary buttons, links (`accent-ink`), focus rings
  (`accent-glow`, a brighter brass) and Generate report. Switches and checks
  that are on take the desk's green. Green and red belong to prices.
- **Type carries the hierarchy.** Titles are set in Instrument Serif (page
  titles, headings in `text-title2`/`text-title3`, the Home title, a
  company's name, the News lead, the brand); the interface in Instrument
  Sans, which has true tabular figures for `.tabular`/`.mono-data`. Both are
  bundled with the app (`@fontsource`, imported in `main.js`), never fetched
  from a third party; Songti and PingFang set Chinese. Section labels
  (`.vogue-label`) are italic serif kickers in sentence case.

Dark mode keeps the idea: the desk goes almost black, the sheet a deep green
slate, and the ink turns to the ivory the desk is written in.

**The desk re-points the tokens.** `.app-toolbar` and `.app-sidebar`
redefine the `--color-*` tokens to ivory-on-green, so every control inside
them — rows, icon buttons, filters, the sort and account menus, the `+`
menu — is written on the desk without knowing where it is. Reach the
page's own colors from there through `--bureau-sheet` and `--bureau-ink`,
which the desk leaves alone.

**The shell changes shape.** `DESK_TAB_DESIGNS` in `src/design.js` lists the
designs whose shell works this way (`desksAsTabs`):

- The sidebar's desk rows are carried into the masthead
  (`<Teleport to="#masthead-desk-tabs">` in `Sidebar.vue`), so the tabs keep
  the rows' links, selection rule (none while a company's page holds it),
  counts and welcome-tour anchors. Below lg they stay in the drawer.
- The company list starts as a rail of logos. Its toggle opens the named
  index (sort, filter, sectors, Diffs, folders) and folds it back; the choice
  is `companyIndexOpen` (`bsh.companyIndexOpen`, a device key), kept apart
  from the list sidebar's `sidebarCollapsed`.
- Generate report moves beside Warren as a brass pill (`.masthead-generate`);
  the sidebar's own button stays in the drawer.
- The masthead gives way by its own width, through a container query
  (`container-name: masthead`), because the open index and Warren both
  narrow it: the jump field goes first (⌘K still opens the palette), then
  Generate's label, Warren's name, and last the tab labels (their glyphs
  stay, named on hover).
- Warren docks as a second sheet beside the page. Desks sized to the window
  under the 52px toolbar (`h-[calc(100vh-52px)]`, the Research Desk's
  `-mt-[52px]` band) are refitted to the sheet's gutter.

Hook classes: `.app-sheet`, `.app-toolbar-row`, `.masthead-desk-tabs`,
`.masthead-generate`, `.toolbar-jump`, `.copilot-toolbar-label`,
`.sidebar-brand`, `.sidebar-generate-wrap`, `.sidebar-desks`,
`.sidebar-desks-rule`, `.sidebar-companies`, `.sidebar-account`, and the
sign-in sheet's `.login-sheet` / `.login-glow` (Summit and Folio ignore them).
When you build something new, style it in `style.css` as usual; if it floats
over the page, give it `surface-raised` and `--shadow-sheet`, and check it in
all three designs and both appearances. A pseudo-element can't go inside
`:is()` — the whole argument is dropped silently — so give
`.foo::before` a rule of its own.

## Folio

Everything Folio changes lives in `frontend/src/folio.css`, scoped under
`:root[data-design="folio"]`. It redefines what the tokens resolve to and
recuts the shapes; views don't know which design is on. Four rules:

- **Paper, not glass.** The canvas is warm paper (`244 242 237`) with a faint
  grain on the fixed `.canvas-wash` layer; a card is a fresher sheet
  (`surface`) drawn with a 1px rule, never lifted by a shadow. Nothing blurs:
  `--glass-blur` is `none`, and sheets, menus and the command palette are
  opaque paper with a short, close shadow (`--shadow-sheet`). Only menus and
  sheets that sit over the page get a shadow at all.
- **Ink marks where you are.** Selection is solid ink (`--folio-ink`) with
  the label knocked out (`--folio-on-ink`): the sidebar row, the chosen
  segment, the Market ranges, a Research Desk row, a menu row under the
  pointer, the command palette's active line and views' hand-made
  `bg-accent text-white` choices. It snaps instead of gliding (a knocked-out
  label can't wait for its ink to arrive), so the sidebar's glider is hidden.
  Rows too rich to knock out (a report with its chips, `.doc-row`) take a
  bookmark: a shaded sheet with a 3px ink ribbon down the left edge. A chosen
  option card in a form is ruled in ink.
- **Blue ink is for acting.** The accent is ultramarine (`38 60 212`):
  primary buttons (`.btn-filled`, `.mac-btn--prominent`), links, focus rings,
  Generate report and Warren. It is never a selection, so an action and the
  place you are never look alike. Green and red belong to prices.
- **Type carries the hierarchy.** Titles (`.page-title`, `text-large-title`,
  `text-title1`, headings set in `text-title2`/`text-title3`, the Home title,
  a company's name, the News lead, the brand) are set in a book serif,
  `--font-folio-serif`: Iowan Old Style, then Charter, Palatino, Georgia and
  Songti SC. Nothing is downloaded. The serif never touches a figure
  (`.tabular` and `.mono-data` keep SF) or a control. Section labels
  (`.vogue-label`) are small tracked capitals. Reading surfaces (Warren's
  answers, the News briefing, the Pulse brief) are set in the serif too:
  Warren writes letters.

Shapes: buttons, fields and icon buttons are cut rectangles (6px); cards 6px,
sheets 10px, chips and tags 3–4px. Only dots, avatars, switches, spinners and
progress bars stay round. Text selection is a highlighter stroke. The browser
chrome takes the paper color (`theme-color`).

The shell changes shape as well as color: the sidebar stops floating and
becomes a full-height index column ruled off from the page; Warren docks as
a full-height margin column; the toolbar's capsules dissolve into bare
buttons; the Research Desk's directory becomes a ruled column. The hook
classes are `.app-sidebar`, `.app-sidebar-panel`, `.app-toolbar`,
`.app-inspector` and `.sidebar-generate` (Summit ignores them).

When you build something new, style it in `style.css` as usual. If it uses
glass, a capsule, a glass-pill selection or a baked-in radius above 8px,
add its Folio cut to `folio.css`, and check it in both designs and both
appearances.

## Summit Glass

The web app is the sibling of the Mac terminal
(`ios/BSHResearchMac/Views/MacDesign.swift`, `MacGlassStyles.swift`).
Content sits on calm white cards drawn with hairlines. Liquid Glass is kept
for chrome: the floating sidebar and Ask inspector, toolbar capsules, menus,
sheets, and the selection pill. Three things are specific to the web:

- **Summit light.** The canvas is lit from above: a sky glow over the sidebar
  corner and a faint violet at the top right (`.canvas-wash::before`).
- **Gliding selection.** Selection moves between rows on a spring instead of
  jumping (`src/glassMotion.js`).
- **Floating side panels.** The sidebar and the Ask inspector float on either
  side of the content column.

Everything lives in `frontend/src/style.css` (tokens, materials, controls) and
`frontend/tailwind.config.cjs` (type scale, radii, color utilities). The class
names are older than this design, so existing views picked it up without
template changes.

## Tokens

| Token | Use |
|---|---|
| `canvas` / `surface` | Page ground / card. Cards are `bg-surface` + `shadow-card` (a hairline, almost no shadow). |
| `ink-primary … ink-subtle` | Label hierarchy. `ink-muted` is the default secondary text and meets ~4.3:1 on white. |
| `accent` | Summit blue `#0B87D6`: filled buttons, selection, active tab bar. |
| `accent-ink` | Links and accent text on white. |
| `accent-glow` | The original brand sky `#38A8E8`: focus rings, halos, glows. Never text. |
| `success / danger / warning / info / notice` | Apple system palette. Use the `-soft` background and `-ink` text for chips. |

Dark mode redefines the same tokens under `.dark`. Appearance follows the
system by default (Settings can force Light or Dark), as the Mac app does.

## Materials

| Class | What it is |
|---|---|
| `.glass-panel` | Floating chrome panel (sidebar, Ask). The glass is on `::before`, so **the host must be positioned**. Don't put `overflow-hidden` on it, because that clips the edge shadow. |
| `.glass-popover` | Add to `.glass-panel` for popovers over content (denser fill). |
| `.glass-capsule` | A group of toolbar controls sharing one capsule. Host must be positioned. |
| `.glass-pill` | The levitating selection surface (sidebar glider). |
| `.material-menu`, `.toolbar-menu` | Menus: glass, 13px radius, items highlight in the accent with white text. |
| `.material-glass` | The Home Spotlight plate. |
| `.group-card`, `.desk-card`, `.glass-card` | White content cards. `.glass-card` also lifts on hover. |

Why `::before`: an element with `backdrop-filter` becomes a *backdrop root*,
and glass nested inside it (a menu under the toolbar) could then only blur its
parent. Putting the blur on a pseudo-element keeps nested glass working.

Keep `backdrop-filter` off anything that repeats many times on a page
(buttons, rows). It is expensive to scroll.

## Controls

- Buttons are capsules: `.btn-filled` (primary), `.btn-bordered` (the default
  secondary), `.btn-tinted`, `.btn-plain`. Add `.btn-sm` in dense rows.
- `.icon-btn` is round. `.segmented` + `.segmented-item` with `data-selected` /
  `aria-selected` / `aria-checked` gives the glass thumb, and it glides
  automatically.
- `.workspace-tab` with `role="tablist"` on the parent gives underline tabs
  whose bar glides.
- `.field` (text and `select`, which gets the macOS double chevron),
  `.field-sm`, and `.switch` for boolean settings.
- `.chip` for status; `.price-pill[data-up]` for day change; `.kbd` for key caps.
- `<Monogram>`: company initials in a squircle. It is neutral in the sidebar;
  pass `tinted` in content lists (the hash is stable across sessions).

## Ask Warren

The assistant is **Warren**, as on iPhone (`AskPersonaStore.swift`): his
portrait is the mark, the panel is "Ask Warren", and while he answers the
status reads "Buffetting…".

- `<WarrenMark :size :busy>` is the portrait. Use it wherever you open the
  assistant (the toolbar, "Ask Warren" buttons, the drag lens). `busy` adds a
  breathing sky ring. `<AiMark>` stays the icon for generic AI features
  (summaries, memo runs).
- The inspector header names the company Warren reads ("About Acme ⌄",
  `CopilotCompanyPicker.vue`). He follows the company page on screen,
  otherwise the last company opened.
- `CopilotPanel.vue` has an empty hero with starter questions, answers with
  Copy / Ask again, follow-up chips, Stop while streaming, and a context chip
  above the composer naming what the page handed him.
- Classes: `.warren-mark`, `.warren-md` (13px answers), `.warren-status` (the
  sheen on "Buffetting…"), `.warren-action`, `.warren-card`, `.warren-cite`,
  `.warren-context`.

## The Research Desk

`ResearchDeskView.vue` and its cards are the web twin of the Mac terminal, so
they use a `mac-*` class family under a `.mac-desk` root (`style.css`, bottom
section) rather than the classes above: hairline-separated surfaces, the SF
point type scale, capsule controls and a levitating selection pill.

That is a difference of **shape only**. Every `--mac-*` token resolves to an
app token — `--mac-accent` is Summit blue, `--mac-canvas` is the page ground,
the selection pill is the sidebar glider's glass — so the desk reads as the
same app as the chrome around it, and dark mode follows from `.dark` without a
second set of values. When adding to the desk, point new tokens at
`--color-*` / `--glass-*`; never re-sample a platform palette, and never
redefine a `--color-*` token inside `.mac-desk` (that inverts the dependency
and re-tones nested Summit components such as Memo Studio).

## Welcome tour

`WelcomeTour.vue` is the first-sign-in walkthrough, modeled on the "Welcome
to" sheet iOS shows after a major update: a brand tile and feature rows, then
one page per desk with a glyph, two lines and tips. `src/welcomeTour.js` owns
the state: it opens once per browser (`bsh.welcomeTourSeen` stores the tour
version; bump `WELCOME_TOUR_VERSION` when the content changes enough to show
again) and Settings can replay it. Classes: `.welcome-tour-*` and the
`tour-forward` / `tour-back` page transitions. The iPhone/iPad and Mac apps
carry the same tour (`WelcomeTourView.swift`, `MacWelcomeTourView.swift`),
except for the web's "Open a company like a folder" step: it opens the last
company visited (else the top of the list) and spotlights its folder in the
sidebar (`[data-tour="company-folder"]`), which the apps don't have.

## Company pages in the sidebar

Clicking a company in the sidebar opens it in place, like a folder in the
Finder sidebar: rows appear under it, indented along a hairline guide —
Reports, News, Research Desk and, for a listed company, Market (its stock on
the Market desk). Reports and News show how many reports and headlines they
hold, counted the way those pages build them (the reports list, and the
News desk's headlines for the company with its own ticker's wire), never
with an AI call. A count waits until its numbers are in rather than showing
a wrong 0.

- One company is open at a time. Clicking it again closes it; `→` and `←`
  open and close it from the keyboard. A modified click (new tab) keeps the
  row's plain link to the Research Desk.
- Reaching a company's page any other way (search, ⌘K, a link, a ticker
  tape) opens that company in the list with the page marked, so the sidebar
  always says where you are. The Market desk counts as the company's page
  while it shows the company's stock.
- The page on screen takes the glass pill. While it does, the desk row above
  (Reports, News, Market) gives up its own highlight: the sidebar holds one
  selection. Shut, the company row itself holds it.
- Each row keeps its glyph's tint: accent for Reports, the warning ink for
  News, the info ink for Research Desk and the success ink for Market. The
  open company shows a chevron.
- In the icon rail the rows stack as glyphs on a quiet tray under the logo,
  named on hover.

The rows link to `/reports?company=`, `/news-desk?company=`, the Research
Desk and `/market-radar?ticker=`. The classes are `.company-pages`,
`.company-page-row[data-kind]` and `.company-disclosure`; the counting
helpers are in `src/companyPages.js`.

## Page anatomy

- A desk opens with a large title (`.page-title`, or `<PageHeader>`). Register
  it with `useLargeTitle(ref)` from `src/chrome.js` so the toolbar's small
  title only fades in once the large title scrolls away. Pages that don't
  register get the same behavior for their first `h1` automatically.
- A document desk (Reports) is the exception: it has no header row above its
  panes. The title, count, search, filters and actions sit on the list pane's
  own header, so the viewer runs the window's full height. Collapse the list
  and the toolbar's small title takes over.
- The document viewer (`DocumentViewerWindow.vue`) keeps its header to one
  line and fits a Word page to the viewer's width (`src/docxFit.js`). Its zoom
  capsule steps − and + from 50% to 300%, the percentage returns to actual
  size, the arrows return to fit, and a trackpad pinch zooms around the
  pointer. The choice is kept per browser (`bsh.docViewerZoom`).
- Use sentence case for section labels (`.vogue-label` / `.section-label`),
  never all caps. The i18n strings are already sentence case.
- Numbers: `.mono-data` / `tabular` set SF Pro with tabular figures, not a
  monospace face. Keep `font-mono` for code, paths and logs.
- Containers: `.page` (max 1240px) or `.page-wide`.

## The Reports viewer

The pieces around the document in `DocumentViewerWindow.vue`. They read
report records through `src/reportStatus.js`, never fields of their own.

- **Status card.** A report with no document shows its run, not an empty
  page: one card (`data-testid="viewer-status"`) whose tinted glyph says
  running (info, spinner, stage and a progress bar), failed (danger, the
  server's plain-words summary, what was spent, Resume / Dismiss / New
  report), cards ready (accent, a link to Memo Studio) or no document.
  Dismiss and Cancel arm on the first click and act on the second.
- **Outline panel.** The contents button in the header opens a 224px column
  of the memo's sections beside the page, or over it on a phone. The section
  on screen is marked like a sidebar row (accent tint, `aria-current`).
- **Full-screen layer.** Full screen moves the same viewer — zoom, language,
  place in the document — to a fixed layer over the whole window
  (`.reports-viewer-fullscreen`): above the jobs rail, below sheets.
- **Working-papers menu.** A capsule in the header opens a glass popover
  (`.glass-panel.glass-popover`) listing the run's analysis files; a pass
  that did not run says so. Opening one swaps the document for the paper,
  with a Back capsule in place of the language switch.
- **Review chip.** Under the header, one row of chips says what the memo
  concludes (verdict), where its review stands (draft, in review, approved,
  withdrawn) and whether it is current. Review moves live in the header's
  overflow menu, and only for the permissions the reader has.
- **Comments and flags panel.** The Comments button (with the count of open
  comments and flags) opens a side panel of the report's threads, open first.
  Selecting text in the document offers Flag, which files the quote with a
  kind (wrong number, unsupported, unclear, missing, tone).
- **Two-line header.** Line one is the title, the language switch and the
  tools; line two is the chip row above (verdict, review, freshness —
  "Written Aug 31 · 22 days ago", with the latest source date only when it
  lags the memo by more than two weeks, amber after 30 days).
- **Export and ⋯ menus.** Export is a menu, never a bare link: PDF for
  sharing (only once the server's PDF is ready), Word (editable), both
  languages as a zip; every item is an explicit export (`purpose=export`) and
  the menu is absent without `memo:export`. The ⋯ menu holds Copy link, Open
  Studio and the review moves.
- **PDF / Web toggle.** When a PDF is ready the viewer can show it in an
  iframe; the Web view (docx-preview) stays the default working surface —
  outline, zoom and Flag only exist there. The choice is remembered per
  browser (`bsh.docViewerMode`).
- **Printing.** Print prints the PDF when it is shown, else the page with
  print rules that keep only the document (`html[data-bsh-print="document"]`).
- **Rows.** A report row carries the company, the type, a verdict chip, a
  one-line headline in the UI language, the review chip, the quality and
  fact-check chips and the open-flag count; older versions of the same
  company and type fold under "n earlier versions" beneath the latest.

## The Generate dialog

`ReportCustomizerModal.vue` says what a run will cost and what could stop it
before anything is spent.

- The header names the entity under its display name: legal name ·
  disambiguator · domain (`companyIdentityParts` in `src/companyLogo.js`).
- A pre-flight strip above the footer lists the readiness blockers
  (danger-soft, with the time a usage limit resets), warnings (warning-soft)
  and soft notes (fill-tertiary): a subsidiary's parent, a nonprofit, a listed
  company better served by the Buffett-method memo. A fix is a small bordered
  button on the row ("Switch engine to Gemini", "Run on Microsoft Corp"). It
  never changes a choice by itself and never disables Generate.
- The footer carries the estimate from finished runs at the same settings, or
  "No runs at this setting yet".
- A control a run cannot use is locked with its reason in italics
  (`text-[11px] italic text-ink-muted`), not hidden: audience on a Buffett
  memo, the engine on Buffett and Memo Studio runs.

## Gotchas

- Component classes (`.icon-btn`, `.monogram`, `.btn-*`) come after Tailwind's
  base utilities in the stylesheet, so a plain `hidden` loses to their
  `display`. Use a responsive variant instead (`max-lg:hidden`,
  `max-sm:hidden`), which is emitted last.
- `.field` width sits in `:where()`, so `w-auto` / `w-40` on a field win.
- Chrome's UA stylesheet gives `<button>` `align-items: flex-start`. On a
  `flex-col` button whose children truncate, add `items-stretch`.
- Every new template string needs `en` and `zh` keys (`tests/i18n.spec.js`
  fails on bare text).
- Motion must respect `prefers-reduced-motion`. The global rule in `style.css`
  handles CSS, and `glassMotion.js` skips its glide when reduced motion is on.
