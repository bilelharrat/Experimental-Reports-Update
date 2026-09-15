# Web design language — Summit Glass

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

## Page anatomy

- A desk opens with a large title (`.page-title`, or `<PageHeader>`). Register
  it with `useLargeTitle(ref)` from `src/chrome.js` so the toolbar's small
  title only fades in once the large title scrolls away. Pages that don't
  register get the same behavior for their first `h1` automatically.
- Use sentence case for section labels (`.vogue-label` / `.section-label`),
  never all caps. The i18n strings are already sentence case.
- Numbers: `.mono-data` / `tabular` set SF Pro with tabular figures, not a
  monospace face. Keep `font-mono` for code, paths and logs.
- Containers: `.page` (max 1240px) or `.page-wide`.

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
