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

## Layout

```
ios/
  project.yml              # XcodeGen spec
  BSHResearch/             # App sources
  BSHResearchTests/        # Unit tests
  README.md
```

## Notes

- Decoder does **not** use `convertFromSnakeCase` globally — trader
  models in later phases use explicit CodingKeys (see doc §17).
- SSE for Console/Trader is not in Phase 1; when added, send
  `Authorization: Bearer` on the URLSession (query `?token=` was
  removed server-side).
