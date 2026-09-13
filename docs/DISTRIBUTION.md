# Distributing BSH Research (no public App Store)

This covers making the **native app** work without your laptop and sharing
it with colleagues **without** listing it on the App Store.

## Two separate requirements

1. **API online** — the app must call a public HTTPS host, not `localhost`
   or a LAN IP. Without this, the phone has nothing to talk to when your
   Mac is off.
2. **Signed install** — iOS only keeps apps installed long-term with a paid
   [Apple Developer](https://developer.apple.com) account (TestFlight or
   Enterprise). Free signing expires in ~7 days.

## 1. Host the API

The repo already ships a production container:

```sh
docker compose build
docker compose up -d
```

Or on any Linux host with Docker:

```sh
docker build -t bsh-research .
docker run -d --name bsh -p 8010:8010 \
  -e BSH_ALLOW_ANON_DEV=0 \
  -e BSH_COOKIE_SECURE=1 \
  -v "$PWD/data:/app/data" \
  bsh-research
```

Put TLS in front (Caddy, nginx, Cloudflare, Envoy). Point DNS at that host,
e.g. `https://research.yourcompany.com`.

Unset `BSH_ALLOW_ANON_DEV` in production and create real users:

```sh
uv run python -m server.auth_store set-password you@company.com
```

## 2. Point the app at production

- **iOS Settings → API base URL** — paste `https://research.yourcompany.com`
  (no trailing slash). Stored in `UserDefaults` `bsh.baseURL`.
- **Release Info.plist `BSHBaseURL`** — set this before archiving so devices
  get the right default without opening Settings. Today Debug defaults to
  the LAN IP in `ios/project.yml`.
- **Web** — same-origin with the Docker image; no separate API host needed.

## 3. TestFlight (recommended for the team)

Needs Apple Developer Program (~$99/yr).

1. Xcode → Product → Archive → Distribute App → App Store Connect → Upload.
2. In [App Store Connect](https://appstoreconnect.apple.com) → TestFlight,
   add internal testers (your team) or external (light review).
3. Colleagues install **TestFlight** from the App Store, accept the invite,
   install BSH Research.

The app is **not** publicly searchable on the App Store.

### Alternatives

| Path | When |
|---|---|
| Unlisted App Store app | Want a private link, still Apple review |
| Enterprise Program | Employees only + MDM; stricter Apple eligibility |
| Ad Hoc | ≤100 devices; register every UDID |

## 4. Push notifications (briefing / memo ready)

Scaffolding lives under `server/push_notify.py` and `POST /api/device-tokens`.
To go live you still need:

- An Apple Push (APNs) key in the Developer portal
- The iOS app entitlement `aps-environment`
- Wiring `registerForRemoteNotifications` + sending the device token to the API

Until then, the app already uses **local** notifications for alerts after
`POST /api/alerts/check`.

## Checklist

- [ ] Public HTTPS API running
- [ ] `BSH_ALLOW_ANON_DEV` off; real passwords set
- [ ] iOS Release / Settings base URL = production
- [ ] Archive uploaded to TestFlight
- [ ] Colleagues invited
- [ ] (Optional) APNs key + push enabled
