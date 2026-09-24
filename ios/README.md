# BSH Research — iOS app

Native SwiftUI client for the Research Center API. Parallel frontend to
the Vue SPA — same Bearer auth, same `/api/*` endpoints.

## Status

**Phase 1 (scaffolded):**

- Sign in / sign out (session token in Keychain)
- Tabs: **Market** · **Pulse** · **Companies** · **Settings**
- Market: live index quotes (`GET /api/quotes`)
- Pulse: archived Morning Brief + AI note (`GET /api/market-brief`)
- Companies: list/search + detail with live quote chip + “Open on web”
- EN / ZH UI toggle
- Configurable API base URL (Settings)

**Next phases** (see `docs/ios-app-implementation.md`): Trader cards,
Console SSE, attachments.

## Requirements

- macOS with **Xcode 16+** (full app, not just Command Line Tools)
- [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`)
- Backend running (e.g. `./run.sh --reload` on port 8010)
- A Research Center user account

## Generate & run

```sh
cd ios
xcodegen generate
open BSHResearch.xcodeproj
```

In Xcode: pick an iPhone simulator → Run (⌘R).

### Pointing at a server

| Environment | Base URL |
|-------------|----------|
| Local `./run.sh` | `http://127.0.0.1:8010` (default; Simulator can reach host loopback) |
| Physical device + LAN | `http://<your-mac-lan-ip>:8010` (set in Settings) |
| Production | `https://<host>/research` |

`NSAllowsLocalNetworking` is enabled for local HTTP during development.

### Auth

`POST /api/auth/token` with email/password → Bearer token in Keychain.
No shared env token in the UI (operators can still paste one via a
future debug screen if needed).

## watchOS companion

Wrist app + face complications (watchOS 10+):

- **Watchlist** — App Group pins (`group.com.bilelharrrat.bshresearch`) or SPY/QQQ defaults
- **Movers** — `/api/quotes/screeners` gainers/losers glance
- **Settings** — API base URL (inherits phone Settings via App Group)
- **Complications** — circular + rectangular quote/% change
- Tap a ticker → `bshresearch://ticker/…` opens on the paired iPhone

```sh
cd ios
xcodegen generate
# Xcode → scheme BSHResearchWatch → Apple Watch Ultra / Series simulator → Run
# Or embed: scheme BSHResearch (installs phone + watch together)
open BSHResearch.xcodeproj
```

CLI build (after watchOS Simulator runtime is installed in Xcode → Settings → Platforms):

```sh
xcodebuild -scheme BSHResearchWatch \
  -destination 'platform=watchOS Simulator,name=Apple Watch Ultra 3 (49mm)' \
  -configuration Debug build
xcrun simctl install booted \
  ~/Library/Developer/Xcode/DerivedData/BSHResearch-*/Build/Products/Debug-watchsimulator/BSHResearchWatch.app
```

Physical watch: same team (`8CV4X23Y2T`), set LAN base URL on phone or watch Settings.

## macOS memo desk

Native SwiftUI Mac client (`BSHResearchMac`) — **research memos first** (Apple
`NavigationSplitView`), same library as iPad + the website:

- **Sidebar** — Companies or All memos
- **Content** — company memo list
- **Detail** — PDF memo reader (EN/ZH) + annotation overlay from iPad ink
- **Settings** — API base URL + optional sign-in (⌘,)

```sh
cd ios
xcodegen generate
# Xcode → scheme BSHResearchMac → My Mac → Run
xcodebuild -scheme BSHResearchMac -destination 'platform=macOS' -configuration Debug build
open ~/Applications/BSH\ Research.app
```

Defaults to `http://127.0.0.1:8010`. Needs `./run.sh` for live data.

### Signing (personal team)

Team **Bilel Harrat** (`8CV4X23Y2T`) is a free Personal Team. In Xcode →
Signing & Capabilities, select that team for every target.

- **App Groups** (`group.com.bilelharrrat.bshresearch`) — kept; needed for Watch/widgets.
- **Push Notifications** — stripped from entitlements (personal teams cannot
  provision `aps-environment`). Remote push stays off until you join a paid
  Apple Developer Program team, then re-add `aps-environment` to
  `BSHResearch.entitlements` and the Push capability in Xcode.


## Designs: Summit Glass, Bureau, Folio

The iPhone/iPad and Mac apps offer the website's designs (see
`docs/web-design-language.md`):

- **Summit Glass**, the original system look, is the default.
- **Bureau** lays the page on a desk, uses brass for acting, sets titles in
  Instrument Serif, and cuts where you are from the page. Its desk color is a
  second choice: **Onyx & White** (a white desk by day, black by night) is
  the default, and bottle green, maroon, navy, aubergine, tobacco and graphite
  are the others.
- **Folio** is paper and ink, with Iowan Old Style titles and selection set in
  solid ink.

Settings → Appearance → Design picks one per device. The desk colors show
only while Bureau is chosen. The welcome tour ends on the same choice
("Choose your look"; the tour is at v3, so people who saw v2 get it once more).
Choices are stored under the website's keys, `bsh.research.design` and
`bsh.research.bureauDesk`. The window rebuilds in the new look, and Settings
and the tour stay open through the rebuild.

- `BSHShared/BSHDesign.swift` (compiled into both apps) holds the choices
  (`BSHDesign`, `BSHBureauDesk`, and `BSHDesignStore` with its `identity`),
  the palette (`BSHPalette`, the website's RGB values, per desk under Bureau),
  the type (`BSHType`) and `BSHJoinedTabShape`, the tab that flares into the
  page. `BSHShared/BSHDesignPickers.swift` holds the two choosers:
  `BSHDesignCards` and `BSHBureauDeskPicker`. Instrument Serif and its
  licence ship in `BSHShared/Fonts`; Iowan comes with the OS.
- Desks don't read the design. They use the tokens and components
  (`Color.ds*`, `Font.dsTitle`/`dsHeadline`, `appleGlassCard`/`Tile`,
  `MacSectionLabel`, `MacTabBar`: `ResearchDesign.swift` on iOS,
  `MacDesign.swift` / `MacGlassStyles.swift` on the Mac), which resolve
  against `BSHDesign.active` and `BSHBureauDesk.active`. Use `Color.dsAccent`,
  never `Color.accentColor`.
- iOS extras in `Views/Shared/BSHDesignChrome.swift`:
  - Put `.bshListSurface()` on a List or Form, and wrap its sections in
    `Group { … }.bshListRows()`.
  - Title sections with `BSHSectionTitle`.
  - Use `Color.dsPage`, `.dsBar` or `.dsFloating` where a view used
    `systemBackground`, `.bar` or a thin material.
- Only the shells branch on the design: the iPhone and portrait-iPad desk bar
  and the landscape-iPad rail (`RootView.swift`); on the Mac, the sidebar,
  toolbar and page (`MacDesignChrome.swift`). Settings is presented once, from
  the app (`SettingsPresenter`), above the content that rebuilds.
- Gotchas:
  - UIKit's navigation bars and segmented controls take the design from
    appearance proxies (`BSHUIKitChrome`), which only reach bars created
    later. `BSHDesignStore` applies them before the rebuild.
  - A dark Bureau desk is dark in both appearances, as on the web
    (`BSHBureauDesk.isDark(in:)`; every desk but Onyx's white one by day).
    Over a dark desk:
    - the Mac sidebar forces the dark scheme, so the toolbar buttons over it
      read, and borrows page colors through `bshPageScheme`;
    - the Mac titlebar draws dark;
    - the landscape iPad hides the status bar, since its clock can't be read
      over the rail in light mode.
  - On Onyx's white desk by day the page, the tabs and the chosen rows are set
    off by a hairline rim instead of a shadow.

## Layout

```
ios/
  project.yml                 # XcodeGen spec
  BSHShared/                  # Designs + fonts, compiled into iOS and Mac apps
  BSHResearch/                # iPhone/iPad app
  BSHResearchWidgets/         # iOS WidgetKit
  BSHResearchWatch/           # watchOS companion
  BSHResearchWatchWidgets/    # Watch face complications
  BSHResearchMac/             # macOS desk app
  BSHResearchTests/           # Unit tests
  README.md
```

## Notes

- Decoder does **not** use `convertFromSnakeCase` globally — trader
  models in later phases use explicit CodingKeys (see doc §17).
- SSE for Console/Trader is not in Phase 1; when added, send
  `Authorization: Bearer` on the URLSession (query `?token=` was
  removed server-side).
