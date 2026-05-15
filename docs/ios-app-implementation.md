# BSH Research Center — iOS implementation guide

How to consume the Research Center API from a native iOS / iPadOS
client. This is the same backend the web SPA at `/research` talks to;
the iOS app is a parallel frontend, not a separate service.

Audience: a Swift developer building a SwiftUI app from scratch
against the existing FastAPI server.

---

## 1. Scope (v1)

In scope:

- Company search + per-company browse (existing `/api/companies/*`).
- Public-company **Trader view** with the six company trader cards
  (price / momentum / sentiment / heat / catalysts / news), daily
  top-moving tech stocks, and one-tap refresh.
- **Console** sessions: create, hydrate, ask, attach images / PDF /
  DOC / DOCX, stop mid-stream, archive, read archived transcripts.
- Bilingual EN / ZH UI mirroring the web app.
- Bearer-token auth (env-token first, then session-token after
  login).

Explicitly out of scope (v1):

- Long-form **memo generation** (`POST /api/reports`) — heavy
  pipeline, rare action; punt to a "View on web" deep-link.
- **Document library** uploads (PDF / PPTX management). Read-only
  access to existing uploads is fine; new uploads stay on web.
- **News / Hormuz / External research** feeds — secondary surfaces.
- **Search auto-complete** typeahead: ship later if needed.

If the user taps into something out of scope, open the equivalent
web URL in `SFSafariViewController` instead of building it natively.

---

## 2. Architecture overview

```
┌──────────────────────────────────────────────────────────────┐
│  iOS app (SwiftUI + async/await)                             │
│                                                              │
│  ┌─ Networking ───┐  ┌─ Models ──────┐  ┌─ State ─────────┐  │
│  │ APIClient      │  │ Company       │  │ AppLanguage     │  │
│  │ SSEClient      │  │ TraderSnapshot│  │ SessionToken    │  │
│  │ TokenStore     │  │ ConsoleSession│  │ ActiveJobs      │  │
│  └────────────────┘  │ ConsoleTurn   │  └─────────────────┘  │
│                      │ TraderCards   │                       │
│                      └───────────────┘                       │
│                                                              │
│  ┌─ Views ──────────────────────────────────────────────┐    │
│  │ SearchView, CompanyDetailView, TraderView,           │    │
│  │ ConsoleView, ArchivedSessionsView, AttachmentPicker  │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTPS + bearer token
                     ▼
            FastAPI server (root_path="/research")
            ┌──────────────────────────────────────┐
            │ /api/companies/*                     │
            │ /api/companies/{id}/console/*  (SSE) │
            │ /api/companies/{id}/trader/*   (SSE) │
            │ /api/jobs/active                     │
            └──────────────────────────────────────┘
```

The iOS app is stateless apart from the bearer token (Keychain) and
the user-chosen UI language (UserDefaults). Everything else lives on
the server — there's no offline mode in v1, no local DB.

---

## 3. Auth + base URL

### Token sourcing

The server accepts the same bearer token formats as the web SPA:

1. **Shared env token** (`BSH_RESEARCH_API_TOKEN`). On the web this
   gets baked into the served HTML in a `<meta>` tag; on iOS there's
   no HTML, so the operator distributes it out-of-band (TestFlight
   note, deployment config) and the app stashes it.
2. **Session token** minted by `POST /api/auth/token` with
   `{email, password}`. Returned in JSON; expires after 30 days
   (server-side TTL).

Both formats are sent as `Authorization: Bearer <token>` on every
request. SSE endpoints additionally accept `?token=<token>` query
parameter for cases where setting headers is awkward (we'll need it
for SSE — see §6).

```swift
struct TokenStore {
    private static let key = "bsh.research.session"

    static func read() -> String? {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let str = String(data: data, encoding: .utf8)
        else { return nil }
        return str
    }

    static func write(_ token: String) { /* SecItemAdd / SecItemUpdate */ }
    static func clear() { /* SecItemDelete */ }
}
```

### Base URL

Set as a build-time config. Two parts:

- **Host**: e.g. `https://api.bshventures.com`
- **Path prefix**: `/research` (the server's `root_path`)

Concatenate to get the API base: `https://api.bshventures.com/research`.

Every request hits `{base}/api/...`. No special prefixing logic
beyond that — the iOS app doesn't have an equivalent of the web's
`<meta name="bsh-research-api-base">` injection. Ship the prefix in
`Info.plist` (or a `Config.swift`) per build configuration.

### Login flow

```
User opens app
  └─ TokenStore.read()
     ├─ token present  → /api/auth/me  → succeeds: enter Search
     │                                └─ 401:    clear token, show Login
     └─ no token       → show Login
       └─ POST /api/auth/token {email, password}
          └─ TokenStore.write(response.token)
             enter Search
```

Treat any `401` from any subsequent API call the same way the web
does (`window.dispatchEvent("bsh:unauthorized")` equivalent): clear
the token, route back to Login. Implement as a single chokepoint in
the `APIClient`.

---

## 4. Networking layer

One `APIClient` actor that owns:

- The base URL
- A `URLSession` configured with default cookie / cache behavior
- Helpers for typed request / response

```swift
actor APIClient {
    private let base: URL
    private let session: URLSession

    enum APIError: Error {
        case http(status: Int, body: Data?)
        case unauthorized
        case decoding(Error)
    }

    init(base: URL, session: URLSession = .shared) {
        self.base = base
        self.session = session
    }

    func get<T: Decodable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try await request(path: path, method: "GET", body: nil)
    }

    func post<T: Decodable, Body: Encodable>(
        _ path: String, body: Body, as: T.Type = T.self
    ) async throws -> T {
        let data = try JSONEncoder().encode(body)
        return try await request(path: path, method: "POST", body: data,
                                 contentType: "application/json")
    }

    private func request<T: Decodable>(
        path: String, method: String, body: Data?,
        contentType: String? = nil
    ) async throws -> T {
        var req = URLRequest(url: base.appending(path: path))
        req.httpMethod = method
        if let token = TokenStore.read() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let ct = contentType {
            req.setValue(ct, forHTTPHeaderField: "Content-Type")
        }
        req.httpBody = body
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw APIError.http(status: 0, body: data)
        }
        if http.statusCode == 401 {
            await NotificationCenter.default
                .post(name: .bshUnauthorized, object: nil)
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(status: http.statusCode, body: data)
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }
        do { return try JSONDecoder.bshDefault.decode(T.self, from: data) }
        catch { throw APIError.decoding(error) }
    }
}

extension Notification.Name {
    static let bshUnauthorized = Notification.Name("bsh.unauthorized")
}
```

Decoding: use a single `JSONDecoder.bshDefault` configured with
`.iso8601` date strategy and snake_case key handling (the server
emits `created_at`, `last_used_at`, etc., so either decode with
`.convertFromSnakeCase` or write CodingKeys explicitly — the latter
is more robust against future field additions and is recommended).

---

## 5. Models

Mirror the server's wire types one-for-one. Optional fields use
Swift optionals; nullable values from the server (`null`) decode to
`nil`. The full set below covers Console + Trader + Company.

```swift
struct Company: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let ticker: String?
    let description: String?
    let companyType: String?      // "public" | "private"
    let sector: String?
    let exchange: String?
    let status: String?
    let logoDomain: String?
    let traderSnapshot: TraderSnapshot?
    // … see CompanyOut in server/api.py for the full list
}

struct TraderSnapshot: Codable, Hashable {
    let refreshedAt: Date?
    let priceCard: PriceCard?
    let momentumCard: MomentumCard?
    let sentimentCard: SentimentCard?
    let heatCard: HeatCard?
    let catalysts: [Catalyst]
    let traderNews: [TraderNewsItem]
    let techMovers: TechMovers?
}

struct PriceCard: Codable, Hashable {
    let lastPrice: Double?
    let currency: String?
    let asOf: String?
    let changePct1d: Double?
    let changePct5d: Double?
    let changePct30d: Double?
    let changePctYtd: Double?
    let changePct1y: Double?
    let vsSector30dPct: Double?
    let vsSp50030dPct: Double?
}

struct ConsoleSession: Codable, Identifiable, Hashable {
    let id: String
    let companyId: String
    let claudeSessionId: String
    let model: String
    let status: String           // "active" | "archived"
    let title: String
    let createdAt: Date
    let lastUsedAt: Date
    let archivedAt: Date?
    let outputLanguage: String   // "en" | "zh"
    let hydrationStatus: String? // "in_progress" | "done" | "error"
    let tokens: TokenAccounting
    let summary: SessionSummary?
    let pctUsed: Double
    let contextUsed: Int
    let contextWindow: Int
}

struct ConsoleTurn: Codable, Hashable {
    let id: String
    let ts: Date
    let role: String              // "user" | "assistant"
    let text: String?
    let subtype: String?          // "success" | "error"
    let error: String?
    let interruptReason: String?
    let attachments: [Attachment]?
    let tokens: TokenUsage?
    let costUsd: Double?
    let durationMs: Int?
}
```

All Codable types should declare explicit `CodingKeys` so the
backend can add fields without breaking decode.

---

## 6. Server-sent events

The web app uses the browser-native `EventSource`. iOS has no
equivalent — write a small streaming client over `URLSession`'s
async byte stream.

```swift
actor SSEClient {
    enum Event { case data(String), done, error(String) }

    func stream(url: URL) -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var req = URLRequest(url: url)
                req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                // SSE auth: include token in the query string instead of
                // a header, mirroring how withApiToken() wraps URLs on
                // the web. Server accepts ?token=… on every */stream*
                // endpoint.
                let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                guard let http = resp as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode) else {
                    throw APIClient.APIError.http(status: 0, body: nil)
                }
                for try await line in bytes.lines {
                    // SSE protocol: each event is `data: <json>\n\n`.
                    // We parse one line at a time.
                    if line.hasPrefix("data: ") {
                        let payload = String(line.dropFirst(6))
                        continuation.yield(.data(payload))
                        // Inspect for terminal types so the consumer
                        // can close the stream as soon as the job ends.
                        if let dict = try? JSONSerialization.jsonObject(
                            with: Data(payload.utf8)) as? [String: Any],
                           let t = dict["type"] as? String,
                           (t == "done" || t == "error") {
                            continuation.yield(.done)
                            continuation.finish()
                            return
                        }
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
```

### Token in the query string for SSE

Three endpoints stream: hydrate, ask (per turn), trader/refresh.
Build the URL with `?token=…` so `URLSession.shared.bytes` doesn't
need to set headers (it does, but query-string token mirrors the
web pattern and works through proxies that strip auth headers on
streaming responses).

```swift
func streamURL(_ relative: String) -> URL {
    var c = URLComponents(url: base.appending(path: relative),
                          resolvingAgainstBaseURL: false)!
    if let tok = TokenStore.read() {
        c.queryItems = (c.queryItems ?? []) + [URLQueryItem(name: "token", value: tok)]
    }
    return c.url!
}
```

### Reconnect / replay

The server replays the entire progress file from the start every
time you reconnect to a `*/stream/*` endpoint (it's a tail over a
durable JSONL). Mid-flight network drops are therefore safe — open
a fresh `SSEClient.stream` against the same URL and you'll see all
previously-emitted events before live tailing resumes. Use this for
the `Trader Refresh` and `Console Ask` cases.

The stream auto-closes when a `done` or `error` event lands; no
client-side timeout needed.

---

## 7. Console implementation

### Endpoint cheat-sheet

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/companies/{id}/console/sessions` | List active + archived |
| POST | `/api/companies/{id}/console/sessions` | Create — body: `{include_background_docs, include_library_docs, output_language}` |
| GET | `/api/companies/{id}/console/sessions/{sid}` | One session's metadata |
| GET | `/api/companies/{id}/console/sessions/{sid}/turns` | Full transcript |
| GET | `/api/companies/{id}/console/sessions/{sid}/hydrate/stream` | SSE for hydration |
| POST | `/api/companies/{id}/console/sessions/{sid}/ask` | multipart `prompt` + `images[]` |
| GET | `/api/companies/{id}/console/sessions/{sid}/ask/stream/{turn_id}` | SSE per turn |
| POST | `/api/companies/{id}/console/sessions/{sid}/ask/{turn_id}/cancel` | SIGINT the in-flight subprocess |
| GET | `/api/companies/{id}/console/sessions/{sid}/attachments/{img_id}` | Serve an uploaded attachment |
| POST | `/api/companies/{id}/console/sessions/{sid}/archive` | Archive + auto-summarize |
| DELETE | `/api/companies/{id}/console/sessions/{sid}` | Hard delete |

### Per-session UI state

```swift
@MainActor
final class ConsoleSessionViewModel: ObservableObject {
    @Published var meta: ConsoleSession?
    @Published var turns: [ConsoleTurn] = []
    @Published var pendingTurnId: String?
    @Published var pendingText: String = ""
    @Published var pendingAction: String = ""
    @Published var queuedTurnIds: [String] = []
    @Published var hydrationDone: Bool = true
    @Published var error: String?

    private let api: APIClient
    private let sse = SSEClient()
    private var streamTask: Task<Void, Never>?

    func send(prompt: String, attachments: [Attachment]) async throws {
        let info = try await api.ask(/* multipart */)
        let turnId = info.turnId
        if pendingTurnId == nil {
            await openAskStream(turnId: turnId)
        } else {
            queuedTurnIds.append(turnId)
        }
        // Optimistically append the user turn.
        turns.append(.user(turnId, prompt, attachments))
    }

    func stop() async {
        guard let tid = pendingTurnId, let sid = meta?.id else { return }
        _ = try? await api.cancelAsk(sessionId: sid, turnId: tid)
        // The stream will receive an `interrupted` then `error` event;
        // openAskStream's terminal-event handler closes things down.
    }

    private func openAskStream(turnId: String) async {
        streamTask?.cancel()
        pendingTurnId = turnId
        pendingText = ""
        let url = api.streamURL("/api/companies/.../ask/stream/\(turnId)")
        streamTask = Task {
            do {
                for try await event in sse.stream(url: url) {
                    handleEvent(event)
                }
            } catch { self.error = error.localizedDescription }
            // On terminal: refresh turns + meta + advance queue head.
            await afterStreamClose(turnId: turnId)
        }
    }
}
```

### Attachment picker

Two source kinds:

1. **Images** — `PhotosUI.PhotosPicker` (PNG / JPEG / WebP only;
   filter via `matching: .images`).
2. **Documents** — `UIDocumentPickerViewController` configured for
   PDF / DOC / DOCX UTIs:

```swift
import UniformTypeIdentifiers
let allowedTypes: [UTType] = [
    .png, .jpeg, .webP,
    .pdf,
    UTType(filenameExtension: "doc")!,
    UTType("org.openxmlformats.wordprocessingml.document")!,  // .docx
]
```

Client-side preflight before upload (mirrors `frontend/src/console.js
validateAttachment`):

- Size ≤ 10 MB; otherwise show a localized error and don't upload.
- MIME / extension must be in the allowlist above.

The server re-validates via magic-byte sniffing, so don't trust the
client-side check alone — but doing it first avoids a wasted round-
trip on obvious failures.

### Multipart upload

```swift
func askMultipart(sessionId: String, prompt: String,
                  files: [(name: String, mime: String, data: Data)]
) async throws -> AskResponse {
    let boundary = "Boundary-\(UUID().uuidString)"
    var body = Data()
    func append(_ s: String) { body.append(s.data(using: .utf8)!) }
    append("--\(boundary)\r\n")
    append("Content-Disposition: form-data; name=\"prompt\"\r\n\r\n")
    append("\(prompt)\r\n")
    for f in files {
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"images\"; filename=\"\(f.name)\"\r\n")
        append("Content-Type: \(f.mime)\r\n\r\n")
        body.append(f.data); append("\r\n")
    }
    append("--\(boundary)--\r\n")
    // POST with Content-Type: multipart/form-data; boundary=…
    return try await api.upload(/* … */)
}
```

The form field name is `images` (server's FastAPI signature is
`images: list[UploadFile]`); it accepts both image and document
types despite the name.

### Token meter

The server returns `pct_used` and `context_used` on every session
fetch (a derived field — backend keeps the math one place). Render
the green / yellow / red bands at 75 / 90 percent thresholds. At
≥90% disable the Send button and surface an "Archive & start new"
CTA.

```swift
extension ConsoleSession {
    enum MeterBand { case ok, warn, lock }
    var meterBand: MeterBand {
        if pctUsed >= 0.90 { return .lock }
        if pctUsed >= 0.75 { return .warn }
        return .ok
    }
}
```

---

## 8. Trader view implementation

### Trigger flow

1. User taps a public company in search → fetch
   `GET /api/companies/{id}` → returns `Company` with
   `companyType == "public"` and `traderSnapshot: nil` (or stale).
2. Show the `TraderView` SwiftUI screen with the six cards.
3. If `traderSnapshot == nil`, show the empty state ("No trader
   snapshot yet — pull to refresh"); otherwise render the cards.
4. Pull-to-refresh or top "Refresh" button:
   - `POST /api/companies/{id}/trader/refresh` →
     `{job_id, stream_url, status}`
   - Open SSE on the stream_url (or just on
     `/api/companies/{id}/trader/refresh/stream` directly — the
     stream is keyed by company id, not job id; idempotent).
   - Tail events; on `done`, re-fetch
     `GET /api/companies/{id}` to pick up the fresh
     `traderSnapshot`.

### Per-card staleness coloring

The same thresholds as the web app (see
`frontend/src/trader.js STALENESS`). Implement once as a Swift
`enum`:

```swift
enum Staleness { case fresh, warn, stale, unknown }

struct StalenessRule {
    let fresh: TimeInterval   // seconds
    let warn: TimeInterval
}

let stalenessRules: [String: StalenessRule] = [
    "priceCard":     .init(fresh: 1 * 3600, warn: 4 * 3600),
    "momentumCard":  .init(fresh: 4 * 3600, warn: 24 * 3600),
    "sentimentCard": .init(fresh: 24 * 3600, warn: 7 * 86400),
    "heatCard":      .init(fresh: 6 * 3600, warn: 24 * 3600),
    "catalysts":     .init(fresh: 24 * 3600, warn: 7 * 86400),
    "traderNews":    .init(fresh: 6 * 3600, warn: 24 * 3600),
    "techMovers":    .init(fresh: 24 * 3600, warn: 48 * 3600),
]

func staleness(of refreshedAt: Date?, card: String) -> Staleness {
    guard let ts = refreshedAt, let rule = stalenessRules[card] else { return .unknown }
    let age = Date().timeIntervalSince(ts)
    if age < rule.fresh { return .fresh }
    if age < rule.warn  { return .warn }
    return .stale
}
```

UI color picks: `.fresh` → green (`Color.green.opacity(0.15)` + dark
green text), `.warn` → yellow, `.stale` → red. Match the SF Symbols
chip styling iOS users expect, not the web's CSS variables.

### Daily top-moving tech stocks

`trader_snapshot.tech_movers` is a daily market-context block generated
by the same trader refresh job. It is not company-specific; it gives the
analyst a quick read on what moved liquid public tech stocks today and
why. The iOS app should render it as a first-class native card in the
Trader section, after the company-specific cards.

Wire shape:

```json
{
  "tech_movers": {
    "updated_at": "2026-05-13T20:15:00Z",
    "movers": [
      {
        "ticker": "NVDA",
        "company_en": "NVIDIA",
        "company_zh": "英伟达",
        "change_pct_1d": 5.8,
        "direction": "up",
        "market_driver_en": "Analyst target raise and AI data-center demand read-through.",
        "market_driver_zh": "分析师上调目标价，并受益于 AI 数据中心需求预期。",
        "source_url": "https://..."
      }
    ]
  }
}
```

Recommended Swift model:

```swift
struct TechMovers: Codable, Hashable {
    let updatedAt: Date?
    let movers: [TechMover]
}

struct TechMover: Codable, Identifiable, Hashable {
    var id: String { [ticker, companyEn, companyZh, sourceUrl].compactMap { $0 }.joined(separator: "::") }
    let ticker: String
    let companyEn: String
    let companyZh: String
    let changePct1d: Double?
    let direction: String?        // "up" | "down" | "flat"
    let marketDriverEn: String
    let marketDriverZh: String
    let sourceUrl: String?

    func companyName(language: ContentLanguage) -> String {
        language == .chinese ? companyZh : companyEn
    }

    func marketDriver(language: ContentLanguage) -> String {
        language == .chinese ? marketDriverZh : marketDriverEn
    }
}
```

Visualization requirements:

- Card title: localized app string, e.g. "Top-moving tech stocks" /
  "科技股异动".
- Subtitle/staleness: use `tech_movers.updated_at` when present; fall
  back to `trader_snapshot.refreshed_at` only for older snapshots.
- Freshness thresholds: fresh under 24 hours, warn from 24-48 hours,
  stale after 48 hours.
- Row layout: ticker and signed 1-day percent move on the left; company
  name, direction chip, driver text, and optional source link on the
  right.
- Color: positive/up is green, negative/down is red, flat/unknown is
  muted slate.
- Empty state: show a localized empty message when `tech_movers` is
  missing or `movers` is empty; do not hide the whole Trader section.
- Limit display to the first 5-8 movers so the mobile card remains
  scannable.

Localization requirements:

- The backend returns bilingual content for every natural-language field
  added by this block: `company_en`, `company_zh`, `market_driver_en`,
  and `market_driver_zh`.
- Ticker, percent move, dates, source URL, and direction enum are
  language-neutral. Localize the direction label in the app.
- The iOS card must render `company_zh` and `market_driver_zh` whenever
  the active app/company detail language is Chinese; otherwise render
  the English fields.
- Keep the decoder backward-compatible for one release by accepting the
  older `company` and `market_driver` fields as English fallbacks. Do
  not emit those legacy fields from new backend snapshots.

### Bilingual prose fields + translation-pending banner

Every prose field in `trader_snapshot` lands in three forms: the
legacy single-language field (`headline`, `title`, `summary`,
`trend`, `analyst_consensus`, etc.), an English sibling
(`headline_en`, `title_en`, …), and a Simplified-Chinese sibling
(`headline_zh`, `title_zh`, …). The Chinese sibling is a faithful
translation of the English content, not a different summary. The
legacy field mirrors the English sibling for back-compat with
clients that haven't migrated; new iOS code should ignore it
except as a last-resort fallback.

#### Refresh request shape

```http
POST /api/companies/{id}/trader/refresh
   ?languages=en,zh
   &include_translations=true
   &translation_mode=all
```

- `languages` — comma-separated list, default `en,zh`. The server
  records what you asked for on `job_init` for observability; the
  generator always produces both languages today. Unknown codes
  are dropped silently, so a typo never lands an empty
  `available_languages` on the job log.
- `include_translations` / `translation_mode` — recorded on the
  job for the same reason; reserved for a future single-language
  mode.

The POST returns `{job_id, stream_url, status, languages_requested}`.
Echo `languages_requested` into the UI if you want to surface which
languages this run targeted.

#### `done` event payload

```json
{
  "type": "done",
  "refreshed_at": "2026-05-13T20:15:00Z",
  "duration_ms": 12345,
  "available_languages": ["en", "zh"],
  "generated_languages": ["en", "zh"]
}
```

Both keys carry the same list today; consume `available_languages`
on iOS and treat `generated_languages` as a future-proofing alias
(provider-neutral name from the agent-orchestrator doc). Use this
to flip the translation-pending banner before re-fetching the
company record, so the UI updates in one hop rather than two.

#### Decode model

Every bilingual model carries paired CodingKey entries plus a
localized accessor. Pattern, illustrated for `TraderNewsItem`:

```swift
struct TraderNewsItem: Decodable, Hashable, Identifiable {
    var headline: String?           // legacy / EN mirror
    var headlineEnglish: String?    // headline_en
    var headlineChinese: String?    // headline_zh
    var summary: String?
    var summaryEnglish: String?
    var summaryChinese: String?
    // ...

    enum CodingKeys: String, CodingKey {
        case headline
        case headlineEnglish = "headline_en"
        case headlineChinese = "headline_zh"
        case summary
        case summaryEnglish = "summary_en"
        case summaryChinese = "summary_zh"
        // ...
    }

    func headlineText(language: ContentLanguage) -> String? {
        TraderLocalizedText.pick(
            language: language,
            english: headlineEnglish,
            chinese: headlineChinese,
            fallback: headline,
        )
    }
}
```

The fallback chain, identical for every bilingual model:

```swift
private enum TraderLocalizedText {
    static func pick(
        language: ContentLanguage,
        english: String?,
        chinese: String?,
        fallback: String?,
    ) -> String? {
        switch language {
        case .chinese:
            return firstNonEmpty(chinese, english, fallback)
        case .english:
            return firstNonEmpty(english, fallback, chinese)
        }
    }
    // ...
}
```

Asymmetric on purpose: an EN user prefers the legacy field (more
likely English than the Chinese sibling) over the ZH translation,
while a ZH user prefers the typed English sibling over an
unknown-language legacy string. Array fields (e.g.
`breakout_signals`) use an array-shaped variant of the same
helper that treats `[]` as "missing" and falls through.

The schema fields that need bilingual siblings today:

- `momentum_card.trend_en` / `trend_zh`
- `momentum_card.breakout_signals_en` / `breakout_signals_zh`
- `sentiment_card.analyst_consensus_en` / `analyst_consensus_zh`
- `sentiment_card.recent_rating_changes[*].action_en` / `_zh`,
  `from_en` / `_zh`, `to_en` / `_zh`
- `catalysts[*].title_en` / `title_zh`,
  `summary_en` / `summary_zh`
- `trader_news[*].headline_en` / `headline_zh`,
  `summary_en` / `summary_zh`
- `tech_movers.movers[*].company_en` / `company_zh`,
  `market_driver_en` / `market_driver_zh` (already shipped)

Render rule, no exceptions: views read the localized accessor —
never the raw `headline` / `title` field — so a language switch
is a one-line change and Chinese readers never see English copy
on a snapshot the server already translated.

#### `available_languages` and the translation-pending banner

On every successful refresh the worker stamps
`available_languages: ["en", "zh"]` on the persisted snapshot.
The iOS view shows a short warning-tinted banner above the cards
whenever the active display language isn't covered:

```swift
private var translationPendingMessage: String? {
    // Legacy snapshots predate the bilingual contract and don't
    // carry the stamp — silently accept whatever single-language
    // text they have rather than nagging the user about every
    // historical row.
    guard let snapshot, !snapshot.availableLanguages.isEmpty else {
        return nil
    }
    if snapshot.availableLanguages.contains(language) { return nil }
    return TraderCopy.text(
        "trader.translation_pending",
        language,
        ["lang": TraderCopy.text("trader.language.\(language.rawValue)", language)],
    )
}
```

Strings (already wired into the EN + ZH copy dictionaries):

| Key | EN | ZH |
|---|---|---|
| `trader.translation_pending` | This snapshot doesn't have a {lang} translation yet. Refresh to generate one. | 此快照暂无{lang}版本，请刷新生成。 |
| `trader.language.en` | English | 英文 |
| `trader.language.zh` | Chinese | 中文 |

The banner uses the `character.bubble` SF Symbol with
`BSHTheme.warning`. Sits between the live `stage` line and the
error label.

### Refresh button while in flight

The server's job is idempotent by company id — two concurrent
refresh requests for the same company share one progress file and
return `status: "already_running"` on the second call. The UI
should:

- Disable the refresh button while `pendingRefresh == true`.
- Show the latest `stage` message as italic-grey text under the
  button.
- Re-fetch the company record on `done`.

### Background refresh on app foreground (optional)

If you want to keep the trader cards live while a user holds the
detail screen open, kick off a refresh whenever the screen appears
**if** the price card is older than its fresh threshold AND no
refresh is already in flight. This isn't auto-refresh per the
design (which said manual + warn-on-stale only), but it's a
reasonable iOS-flavored variant. Confirm with product before
shipping.

---

## 9. Localization

The server returns localized content where it has both EN and ZH
(company descriptions, etc. — most fields). The iOS UI strings
(button labels, error messages, card titles) are local to the app
and live in standard `Localizable.strings` files.

Mirror the web's `app_language` ref:

```swift
@MainActor
final class LanguageStore: ObservableObject {
    @AppStorage("bsh.appLanguage") var language: String = "en"

    func toggle() { language = language == "zh" ? "en" : "zh" }
}
```

Console sessions have their own per-session `output_language` that
overrides the UI language. Set it from the create-session form
(default to whatever the UI is in). It is **immutable for the
session's lifetime** by design (§Console design doc) — show it as a
read-only badge on the active session.

### Provider attribution labels

Wherever the UI attributes a result to its upstream LLM provider
(search-result source chip, Active-Jobs cards, ad-hoc agent
request affordances), render the parent **company name**, not the
product name:

| Server key (`provider` / `source`) | iOS display label |
|---|---|
| `claude`, `claude_code`, `anthropic` | **Anthropic** |
| `codex`, `openai` | **OpenAI** |
| `cache`, `fallback`, anything else | render as-is |

The rule is "describe the provider," not "describe the model" —
chat-speaker labels for the assistant (e.g. `console.claude`,
`"Claude initialized…"` in a session header) keep the bare model
name because that's the speaker's identity. CLI install messages
that name "Claude Code" / "Codex" stay as-is because they point
the user at the actual product to install.

Centralize the mapping in two places so the rest of the app reads
them through helpers:

```swift
extension ActiveJob {
    var providerLabel: String? {
        switch (provider ?? latestAction?.provider)?.lowercased() {
        case "codex", "openai":            return "OpenAI"
        case "claude", "claude_code",
             "anthropic":                  return "Anthropic"
        default:                           return provider?.capitalized
        }
    }

    /// Use this when you need a *raw* check (icon / tone). Don't
    /// branch on the display label — the rename breaks string
    /// comparisons (`providerLabel == "Codex"` will never match).
    var isCodexProvider: Bool {
        let raw = (provider ?? latestAction?.provider)?.lowercased()
        return raw == "codex" || raw == "openai"
    }
}
```

The `searchStatus` helper in `ResearchStore` follows the same
table when picking the source chip text on a finished search.

---

## 10. Long-running tasks

Three Claude-driven endpoints can run for minutes:

| Endpoint | Typical wall time | Background-safe? |
|---|---|---|
| Console hydrate | 5-30s | Yes — survives app backgrounding via the SSE replay-on-reconnect contract |
| Console ask | 5-120s | Yes — same |
| Trader refresh | 10-60s | Yes — same |

When the app backgrounds mid-stream:

1. SwiftUI suspends the view and cancels the `Task`. The
   `URLSession.bytes` stream tears down.
2. **The server-side subprocess keeps running** — there's no
   client-tied lifetime. Progress events keep flowing into the
   on-disk JSONL.
3. When the user foregrounds the app, re-open the same SSE URL.
   The server replays every event accumulated while you were gone
   before tailing live, so the UI catches up.

For the user-cancel case (the "Stop" button), you must explicitly
`POST .../cancel` — the server has no idea your client gave up
otherwise.

There's no need for `BGProcessingTask` or push notifications in v1.
If you want a real "tell me when this finishes" path later, the
backend would need a webhook hook on `done` and an APNs setup;
neither exists today.

---

## 11. UI structure (SwiftUI)

```
RootView
 ├─ if !authenticated: LoginView
 └─ else: NavigationStack
    ├─ SearchView                              (lists/searches companies)
    │   └─ CompanyDetailView(company)          (header + tabs)
    │       ├─ OverviewTab
    │       │   ├─ if companyType == "public":
    │       │   │     TraderView(company)
    │       │   └─ existing-dossier sections (key people, news, …)
    │       ├─ DocumentsTab
    │       │   └─ list /api/companies/{id}/files (read-only v1)
    │       └─ ConsoleTab
    │           ├─ ConsoleSessionList (active tabs + archived disclosure)
    │           └─ ConsoleSessionView(session)
    │               ├─ TokenMeter
    │               ├─ TranscriptList
    │               └─ ComposerBar (textfield + attach + send/stop)
    └─ Settings
        └─ LanguageToggle, Sign out
```

Use one `Observable` (or `ObservableObject`) per pane. Pass parent
state as `let` props, child state via `@StateObject`.

### Tab-strip vs SwiftUI

The web app uses a custom 3-tab strip inside ResearchView. On iOS,
prefer a `TabView` with `.tabViewStyle(.page)` for the inner pane,
or a `Picker(selection: ..., style: .segmented)` if the tabs are
purely visual. Don't try to mirror the web's exact appearance —
iOS users expect platform conventions.

---

## 12. Error handling

Map server error shapes to localized messages:

| Status | Body shape | UX |
|---|---|---|
| 400 | `{detail: {code, message, …}}` | Inline error near the offending input. Codes to handle explicitly: `attachment_too_large`, `attachment_type_not_allowed`, `company_type_not_public`, `session_archived`. |
| 401 | string detail | Clear token, route to Login. |
| 404 | string detail | Inline; "not found" UI for the screen. |
| 409 | `{detail: {code, …}}` | `session_limit_reached` → CTA to archive an existing session. `session_archived` → "create a new session". |
| 5xx | varies | "Something went wrong, try again." Don't surface stack-trace text. |

A single `BSHError` enum that the views decode from `APIError.http`
keeps this consistent.

---

## 13. Testing

Two layers, mirroring the backend / frontend split in the rest of
the repo:

- **Unit tests** (XCTest) for the math + helpers — staleness
  buckets, token-meter band, attachment preflight, bilingual
  decode. These are pure Swift and run in milliseconds.
- **Integration tests** with a `URLProtocol`-based mock that
  intercepts requests and replays canned JSON / SSE responses.
  Cover: login, create session, send turn, cancel, attach image,
  trader refresh end-to-end.

A real-server e2e tier (against the dev backend with a real
upstream LLM) is overkill for v1 — the backend already has
`@pytest.mark.e2e` covering that contract.

### Test-target setup (`BSHResearchTests`)

The project uses `xcodegen` to keep `BSHResearch.xcodeproj` in
sync with `project.yml`. Add a unit-test bundle target alongside
the app:

```yaml
targets:
  BSHResearch:
    # ...existing app config...

  BSHResearchTests:
    type: bundle.unit-test
    platform: iOS
    sources:
      - path: BSHResearchTests
    dependencies:
      - target: BSHResearch
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.bsh.research.ios.tests
        CODE_SIGN_STYLE: Automatic
        GENERATE_INFOPLIST_FILE: YES
        # No TEST_HOST / BUNDLE_LOADER — these decode tests don't
        # need a UI host application.

schemes:
  BSHResearch:
    build:
      targets:
        BSHResearch: all
        BSHResearchTests: [test]
    run:
      config: Debug
    test:
      config: Debug
      targets:
        - BSHResearchTests
```

Regenerate the project and run the bundle:

```sh
xcodegen generate
xcodebuild test \
  -project BSHResearch.xcodeproj \
  -scheme BSHResearch \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.5' \
  -only-testing:BSHResearchTests
```

### Bilingual decode fixture pattern

Pin all three branches of the localized fallback chain with
fixture-driven decode tests. Keep the JSON inline as a
`#"""..."""#` raw string literal so the test is self-contained:

```swift
final class TraderSnapshotDecodeTests: XCTestCase {
    private func decode(_ json: String) throws -> TraderSnapshot {
        // Trader models declare explicit snake_case CodingKey raw
        // values, so they decode without a `convertFromSnakeCase`
        // strategy. See "Known issues" for the production-decoder
        // caveat — the test deliberately uses a plain decoder.
        let decoder = JSONDecoder()
        return try decoder.decode(
            TraderSnapshot.self, from: Data(json.utf8),
        )
    }

    func testFullyBilingualPayloadDecodesBothLanguages() throws { ... }
    func testLegacyPayloadFallsBackToSingleLanguageField() throws { ... }
    func testPartialBilingualPayloadFallsThrough() throws { ... }
}
```

Three minimum fixtures every bilingual model needs:

1. **Full bilingual** — every `_en` and `_zh` populated. Verifies
   `xxxText(language:)` picks the correct sibling for each
   language.
2. **Legacy single-language** — only the bare `headline` /
   `title` / `trend` fields. Verifies a ZH user still sees the
   legacy text instead of a blank.
3. **Partial bilingual** — `available_languages: ["en", "zh"]`
   but one sibling is `null` or empty array on a per-field
   basis. Verifies the fallback chain inside a single payload.

Pair these decode tests with at least one snapshot view test
that flips `appLanguage` between `.english` and `.chinese` and
asserts the rendered text changes.

---

## 14. Out of scope (v1)

These are deliberate omissions; revisit when there's demand.

- **Offline mode.** Every view assumes a live network. A read-only
  cache of the last-fetched company list is fine but isn't required
  for ship.
- **Push notifications.** No "Claude finished your memo" push
  today; the server has no APNs integration.
- **iCloud sync.** Bearer token in Keychain stays per-device.
- **Watch / iPad-specific layouts.** Build for iPhone first; let
  the SwiftUI layout adapt naturally.
- **Voice input.** Console accepts text + image / doc attachments
  only — matches the web app.
- **In-app document upload to the library.** Tap-through to web
  for now.
- **Long-form memo generation.** Tap-through to web for now.

---

## 15. Appendix — endpoint cheat-sheet

Group by feature so you can scan it cold:

### Auth + identity
- `POST /api/auth/token` — login → `{token, expires_at, …}`
- `GET /api/auth/me` — validate current token
- `POST /api/auth/logout`

### Companies
- `GET /api/companies` — full list
- `GET /api/companies/{id}` — one company (includes `companyType` + `traderSnapshot`)
- `POST /api/companies/{id}/refresh` — re-run the dossier deep-search
- `GET /api/companies/autocomplete?q=…` — typeahead

### Trader (public companies only)
- `POST /api/companies/{id}/trader/refresh?languages=en,zh&include_translations=true&translation_mode=all` —
  kick off snapshot. Bilingual contract params are recorded on
  the job (see §8 Bilingual prose fields).
- `GET /api/companies/{id}/trader/refresh/stream` — SSE progress.
  Terminal `done` carries `available_languages` and
  `generated_languages`.

### Console
- See §7 cheat-sheet above (11 routes).

### AI rail
- `GET /api/jobs/active` — all in-flight Claude jobs across kinds.
  Useful for a small status row in Settings or a debug pane.
- `GET /api/jobs/log?path={kind}:{key}` — replay any job's full
  event log. `kind` is one of `summary`, `search`, `pdf_translation`,
  `memo`, `research_summary`, `console_hydrate`, `console_ask`,
  `console_summary`, `public_snapshot`.

---

## 16. Implementation phases

Suggested rollout, mirroring the design ethos in the rest of this
repo (each phase is shippable):

1. **Skeleton + auth** — Login, root navigation, Search list, basic
   company detail (header + identity strip). No trader, no Console.
2. **Trader view** — `TraderView` cards + Refresh button + SSE
   client. Read-only.
3. **Console — view-only** — list sessions, view archived
   transcripts. No create / no send. Validates SSE replay against
   the on-disk progress files for a richer integration than just
   trader.
4. **Console — interactive** — create, send, stop, attach,
   archive. The bulk of the work.
5. **Polish** — bilingual UI, error toasts, retry logic, iPad
   layout tweaks, settings.

Each phase is ~1-2 weeks of focused work. Total ballpark: ~6-8
weeks for a single iOS dev.

---

## 17. Known issues

### Production decoder silently nils every snake_case `CodingKey`

`JSONDecoder.server` (the shared decoder used for `CompanyDTO`)
sets `keyDecodingStrategy = .convertFromSnakeCase`. Foundation
applies that strategy to nested types as well — including
`TraderSnapshot` and its sub-models, which declare CodingKey raw
values explicitly in snake_case (`case priceCard = "price_card"`).

The strategy converts incoming JSON keys to camelCase BEFORE
matching against `CodingKey.stringValue`. So `"price_card"` in
the wire becomes `"priceCard"` in the internal dict, and the
CodingKey with stringValue `"price_card"` no longer finds it. The
decode doesn't throw because every trader field uses
`decodeIfPresent` / `try?`; the cards simply land as `nil` and
the UI renders placeholders.

`BSHResearchTests/TraderSnapshotDecodeTests`
`testKnownProductionDecoderRegression` documents the bug with
inverted asserts (`XCTAssertNil`, `XCTAssertTrue ... isEmpty`).
The day someone fixes this, that test flips to failing, which
is the prompt to update the asserts to the desired post-fix
behavior.

Two reasonable fixes for a follow-up session:

- **Convert the trader CodingKeys to camelCase raw values.**
  Match what `convertFromSnakeCase` produces for the structural
  keys (`priceCard`, `momentumCard`, `tradeNews`, …) and keep
  explicit `_en` / `_zh` raw values for the bilingual siblings
  (the strategy produces `trendEn` / `trendZh`, which don't
  match the Swift property names `trendEnglish` /
  `trendChinese`). Most surgical.
- **Route trader payloads through a dedicated decoder without
  the snake-case strategy.** Extract `trader_snapshot` from
  `CompanyDTO` as raw JSON data and re-decode with a plain
  `JSONDecoder()`. Mechanical but isolates the trader models
  from the global decoder strategy.

Either fix should land alongside an update to the regression
test that flips it to `XCTAssertNotNil`.
