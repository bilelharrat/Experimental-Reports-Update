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


## Layout

```
ios/
  project.yml                 # XcodeGen spec
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
