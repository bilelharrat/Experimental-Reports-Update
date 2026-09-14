import Foundation

enum MacAPIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden(String)
    case http(Int, String)
    case decoding
    case transport(String)
    case stream(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Bad API URL"
        case .unauthorized: return "Signed out — sign in again"
        case .forbidden(let detail): return detail.isEmpty ? "Permission denied" : detail
        case .http(let code, let detail): return detail.isEmpty ? "HTTP \(code)" : detail
        case .decoding: return "Bad response"
        case .transport(let msg): return msg
        case .stream(let msg): return msg
        }
    }
}

/// Memo-first API client for the Mac desk (Bearer + anon-dev).
actor MacAPIClient {
    static let shared = MacAPIClient()

    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }()

    init(session: URLSession = .shared) {
        self.session = session
    }

    // MARK: - Auth

    func login(email: String, password: String) async throws -> MacAuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await request("auth/token", method: "POST", body: Body(email: email, password: password))
    }

    func me() async throws -> MacSession {
        try await request("auth/me", method: "GET")
    }

    func logout() async throws {
        try await requestVoid("auth/logout", method: "POST")
    }

    // MARK: - Companies & reports

    func listCompanies() async throws -> [MacCompany] {
        try await request("companies", method: "GET")
    }

    func listReports() async throws -> [MacReport] {
        try await request("reports", method: "GET")
    }

    func listCompanyReports(companyId: String) async throws -> [MacReport] {
        try await request("companies/\(companyId)/reports", method: "GET")
    }

    func getReport(id: String) async throws -> MacReport {
        try await request("reports/\(id)", method: "GET")
    }

    func cancelReport(id: String) async throws -> MacReport {
        try await request("reports/\(id)/cancel", method: "POST")
    }

    func resumeReport(id: String) async throws -> MacReport {
        try await request("reports/\(id)/resume", method: "POST")
    }

    func dismissReport(id: String) async throws -> MacReport {
        try await request("reports/\(id)/dismiss", method: "POST")
    }

    func deleteReport(id: String) async throws {
        try await requestVoid("reports/\(id)", method: "DELETE")
    }

    func fetchPDF(pathOrURL: String) async throws -> Data {
        try await download(pathOrURL: pathOrURL)
    }

    func download(pathOrURL: String) async throws -> Data {
        try await downloadBinary(pathOrURL)
    }

    func getCompany(id: String) async throws -> MacCompany {
        try await request("companies/\(id)", method: "GET")
    }

    /// Promote an autocomplete / deep-search hit to a tracked company.
    func selectCompany(_ match: MacCompanyMatch) async throws -> MacCompany {
        try await request("companies/select", method: "POST", body: match)
    }

    // MARK: - Search

    func searchAutocomplete(query: String, limit: Int = 8) async throws -> [MacAutocompleteHit] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return [] }
        return try await request(
            "companies/autocomplete",
            method: "GET",
            query: [URLQueryItem(name: "q", value: q), URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    func searchSymbols(query: String) async throws -> [MacSymbolMatch] {
        struct Payload: Decodable { let matches: [MacSymbolMatch]? }
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return [] }
        let payload: Payload = try await request(
            "quotes/search",
            method: "GET",
            query: [URLQueryItem(name: "q", value: q)]
        )
        return (payload.matches ?? []).filter { !$0.symbol.isEmpty }
    }

    /// Kick off a Claude deep search; cached queries return matches inline.
    func startDeepSearch(query: String, refresh: Bool = false) async throws -> MacDeepSearchStart {
        try await request(
            "companies/search/start",
            method: "POST",
            query: [URLQueryItem(name: "q", value: query), URLQueryItem(name: "refresh", value: refresh ? "true" : "false")]
        )
    }

    /// Cached / finished deep-search results for a query (the job writes to the same cache).
    func fetchDeepSearchResults(query: String) async throws -> [MacCompanyMatch] {
        struct Payload: Decodable { let matches: [MacCompanyMatch]? }
        let payload: Payload = try await request(
            "companies/search",
            method: "GET",
            query: [URLQueryItem(name: "q", value: query)]
        )
        return payload.matches ?? []
    }

    // MARK: - Quotes, news, pulse

    func fetchQuotes(tickers: [String]) async throws -> [MacQuote] {
        let unique = Array(Set(tickers.map { $0.uppercased() })).sorted()
        guard !unique.isEmpty else { return [] }
        var components = URLComponents(
            url: MacConfig.apiRoot.appendingPathComponent("quotes"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = unique.map { URLQueryItem(name: "ticker", value: $0) }
        guard let url = components.url else { throw MacAPIError.invalidURL }
        let data = try await downloadBinary(url.absoluteString)
        struct Payload: Decodable {
            let quotes: [String: DTO]?
            struct DTO: Decodable {
                let lastPrice: Double?
                let changePct1d: Double?
                let name: String?
                enum CodingKeys: String, CodingKey {
                    case name
                    case lastPrice = "last_price"
                    case changePct1d = "change_pct_1d"
                }
            }
        }
        let payload = try decoder.decode(Payload.self, from: data)
        return unique.compactMap { t in
            guard let dto = payload.quotes?[t] else { return nil }
            return MacQuote(ticker: t, last: dto.lastPrice, pct: dto.changePct1d, name: dto.name)
        }
    }

    struct Screeners { let gainers: [MacQuote]; let losers: [MacQuote] }

    func fetchScreeners(limit: Int = 10) async throws -> Screeners {
        struct Row: Decodable {
            let ticker: String
            let name: String?
            let last: Double?
            let changePct: Double?
            enum CodingKeys: String, CodingKey {
                case ticker, name, last
                case changePct = "change_pct"
                case changePct1d = "change_pct_1d"
                case lastPrice = "last_price"
            }
            init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                ticker = try c.decode(String.self, forKey: .ticker)
                name = try c.decodeIfPresent(String.self, forKey: .name)
                last = try c.decodeIfPresent(Double.self, forKey: .last)
                    ?? c.decodeIfPresent(Double.self, forKey: .lastPrice)
                changePct = try c.decodeIfPresent(Double.self, forKey: .changePct)
                    ?? c.decodeIfPresent(Double.self, forKey: .changePct1d)
            }
            var quote: MacQuote {
                MacQuote(ticker: ticker.uppercased(), last: last, pct: changePct, name: name)
            }
        }
        struct Payload: Decodable {
            let gainers: [Row]?
            let losers: [Row]?
        }
        let payload: Payload = try await request("quotes/screeners", method: "GET")
        return Screeners(
            gainers: (payload.gainers ?? []).prefix(limit).map(\.quote),
            losers: (payload.losers ?? []).prefix(limit).map(\.quote)
        )
    }

    func fetchNews(tickers: [String], limit: Int = 60) async throws -> [MacNewsItem] {
        struct DTO: Decodable {
            let id: String?
            let title: String?
            let summary: String?
            let source: String?
            let publishedAt: String?
            let capturedAt: String?
            let ticker: String?
            let url: String?
            let category: String?
            let kind: String?
            enum CodingKeys: String, CodingKey {
                case id, title, summary, source, ticker, url, category, kind
                case publishedAt = "published_at"
                case capturedAt = "captured_at"
            }
        }
        struct Payload: Decodable { let items: [DTO]? }
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        for t in tickers.prefix(12) { query.append(URLQueryItem(name: "ticker", value: t)) }
        let payload: Payload = try await request("quotes/news", method: "GET", query: query)
        return (payload.items ?? []).compactMap { dto in
            guard let title = dto.title, !title.isEmpty else { return nil }
            return MacNewsItem(
                id: dto.id ?? title,
                title: title,
                summary: dto.summary,
                source: dto.source,
                publishedAt: dto.publishedAt ?? dto.capturedAt,
                ticker: dto.ticker,
                url: dto.url,
                category: dto.category ?? "markets",
                kind: dto.kind ?? "live_news"
            )
        }
    }

    func fetchNewsBrief(item: MacNewsItem, lang: String = "en", refresh: Bool = false) async throws -> MacNewsBrief {
        if !refresh {
            var query = [
                URLQueryItem(name: "title", value: item.title),
                URLQueryItem(name: "lang", value: lang)
            ]
            if let company = item.companyName, !company.isEmpty {
                query.append(URLQueryItem(name: "company", value: company))
            }
            if let brief: MacNewsBrief = try? await request("news/brief", method: "GET", query: query) {
                return brief
            }
        }

        struct BriefRequest: Encodable {
            let title: String
            let summary: String?
            let source: String?
            let published_at: String?
            let company: String?
            let ticker: String?
            let url: String?
            let lang: String
            let refresh: Bool
        }

        let req = BriefRequest(
            title: item.title,
            summary: item.summary,
            source: item.source,
            published_at: item.publishedAt,
            company: item.companyName,
            ticker: item.ticker,
            url: item.url,
            lang: lang,
            refresh: refresh
        )
        return try await request("news/brief", method: "POST", body: req)
    }

    func fetchMarketPulsePayload() async throws -> MacMarketPulsePayload {
        try await request("research-pages/market-pulse", method: "GET")
    }

    func fetchPulse() async throws -> MacPulseBrief {
        try await request("market-brief", method: "GET")
    }

    // MARK: - Jobs & alerts

    func fetchActiveJobs() async throws -> [MacActiveJob] {
        try await request("jobs/active", method: "GET")
    }

    func fetchJobHistory(limit: Int = 30) async throws -> [MacJobHistoryRow] {
        try await request("jobs/history", method: "GET", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    func fetchAlertEvents(limit: Int = 100) async throws -> [MacAlertEvent] {
        struct Payload: Decodable { let events: [MacAlertEvent]? }
        let payload: Payload = try await request(
            "alerts/events",
            method: "GET",
            query: [URLQueryItem(name: "limit", value: String(limit))]
        )
        return payload.events ?? []
    }

    func runAlertCheck() async throws -> MacAlertCheckResult {
        try await request("alerts/check", method: "POST")
    }

    // MARK: - Annotations

    func fetchAnnotations(reportId: String) async throws -> MacAnnotationPayload {
        try await request(
            "reports/\(reportId)/annotations",
            method: "GET",
            query: [URLQueryItem(name: "include_drawing", value: "true"),
                    URLQueryItem(name: "include_overlay", value: "true")]
        )
    }

    func fetchOverlayPNG(reportId: String, overlayUrl: String?) async throws -> Data? {
        if let overlayUrl, !overlayUrl.isEmpty {
            return try await downloadBinary(overlayUrl)
        }
        let payload = try await fetchAnnotations(reportId: reportId)
        if let b64 = payload.overlayPngBase64, let data = Data(base64Encoded: b64) {
            return data
        }
        return nil
    }

    // MARK: - Market chart & workspace

    func fetchChart(ticker: String, range: MacChartRange = .d1) async throws -> MacChartPayload {
        try await request(
            "quotes/\(ticker.uppercased())/chart",
            method: "GET",
            query: [URLQueryItem(name: "range", value: range.rawValue.lowercased())]
        )
    }

    func fetchWorkspace(ticker: String) async throws -> MacQuoteWorkspace {
        try await request("quotes/\(ticker.uppercased())/workspace", method: "GET")
    }

    // MARK: - Desk preferences (one blob shared with web & iPad — never overwrite other keys)

    struct DeskPrefsResult {
        let watchlist: [String]
        let lots: [MacBookLot]
        let rules: [MacAlertRule]
    }

    static let defaultWatchlist = ["SPY", "QQQ", "DIA", "IWM"]

    private func fetchDeskPrefsBlob() async throws -> [String: Any] {
        let data = try await rawData("desk/prefs", method: "GET")
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MacAPIError.decoding
        }
        return (root["data"] as? [String: Any]) ?? [:]
    }

    func fetchDeskPrefs() async throws -> DeskPrefsResult {
        let blob = try await fetchDeskPrefsBlob()
        let watchlist = (blob["bsh.marketPinnedTickers"] as? [String]) ?? Self.defaultWatchlist

        var lots: [MacBookLot] = []
        if let rawLots = blob["bsh.bookLots"] as? [[String: Any]] {
            for item in rawLots {
                if let t = item["ticker"] as? String {
                    let id = (item["id"] as? String) ?? UUID().uuidString
                    let sh = (item["shares"] as? Double) ?? (item["qty"] as? Double) ?? 0
                    let cost = (item["costBasis"] as? Double) ?? (item["cost"] as? Double) ?? 0
                    lots.append(MacBookLot(id: id, ticker: t.uppercased(), shares: sh, costBasis: cost))
                }
            }
        }

        var rules: [MacAlertRule] = []
        if let rawRules = blob["bsh.marketAlertRules"] as? [[String: Any]] {
            for item in rawRules {
                if let t = item["ticker"] as? String {
                    let id = (item["id"] as? String) ?? UUID().uuidString
                    let kind = (item["kind"] as? String) ?? "price"
                    let threshold = (item["threshold"] as? Double) ?? 0
                    let direction = (item["direction"] as? String) ?? "above"
                    let enabled = (item["enabled"] as? Bool) ?? true
                    rules.append(MacAlertRule(id: id, ticker: t.uppercased(), kind: kind, threshold: threshold, direction: direction, enabled: enabled))
                }
            }
        }

        return DeskPrefsResult(watchlist: watchlist, lots: lots, rules: rules)
    }

    /// Read-modify-write: only the three keys the Mac owns change; everything the
    /// web desk stores in the same blob survives.
    func saveDeskPrefs(watchlist: [String], lots: [MacBookLot], rules: [MacAlertRule]) async throws {
        var blob = (try? await fetchDeskPrefsBlob()) ?? [:]

        var rawLots: [[String: Any]] = []
        for l in lots {
            rawLots.append([
                "id": l.id,
                "ticker": l.ticker.uppercased(),
                "shares": l.shares,
                "qty": l.shares,
                "costBasis": l.costBasis,
                "cost": l.costBasis,
            ])
        }

        var rawRules: [[String: Any]] = []
        for r in rules {
            rawRules.append([
                "id": r.id,
                "ticker": r.ticker.uppercased(),
                "kind": r.kind,
                "threshold": r.threshold,
                "direction": r.direction,
                "enabled": r.enabled,
            ])
        }

        blob["bsh.marketPinnedTickers"] = watchlist
        blob["bsh.bookLots"] = rawLots
        blob["bsh.marketAlertRules"] = rawRules

        let url = try apiURL("desk/prefs")
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let payload: [String: Any] = ["data": blob]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, response) = try await session.data(for: req)
        try Self.check(response: response, data: data)
    }

    // MARK: - Report options & generation

    struct MacReportOptionItem: Decodable, Identifiable {
        var id: String { code }
        let code: String
        let label: String?
    }

    struct MacReportOptions: Decodable {
        let reportTypes: [String]
        let audiences: [String]
        let languages: [MacReportOptionItem]

        enum CodingKeys: String, CodingKey {
            case audiences, languages
            case reportTypes = "report_types"
        }
    }

    func fetchReportOptions() async throws -> MacReportOptions {
        try await request("options", method: "GET")
    }

    func createReport(companyId: String, reportType: String, audience: String, language: String) async throws -> MacReport {
        struct Body: Encodable {
            let companyId: String
            let reportType: String
            let audience: String
            let language: String
            enum CodingKeys: String, CodingKey {
                case audience, language
                case companyId = "company_id"
                case reportType = "report_type"
            }
        }
        return try await request(
            "reports",
            method: "POST",
            body: Body(companyId: companyId, reportType: reportType, audience: audience, language: language)
        )
    }

    // MARK: - Pipeline: tracking rollup, watchlist, sync

    func fetchTrackingRollup(companyIds: [String]) async throws -> MacRollup {
        let ids = Array(companyIds.prefix(60))
        guard !ids.isEmpty else {
            let empty = "{\"companies\":[],\"attention\":[]}".data(using: .utf8)!
            return try decoder.decode(MacRollup.self, from: empty)
        }
        return try await request(
            "tracking/rollup",
            method: "GET",
            query: ids.map { URLQueryItem(name: "company_id", value: $0) }
        )
    }

    func fetchTrackingWatchlist() async throws -> [String] {
        struct Payload: Decodable { let companyIds: [String]?; enum CodingKeys: String, CodingKey { case companyIds = "company_ids" } }
        let payload: Payload = try await request("tracking/watchlist", method: "GET")
        return payload.companyIds ?? []
    }

    func saveTrackingWatchlist(_ companyIds: [String]) async throws -> [String] {
        struct Body: Encodable { let companyIds: [String]; enum CodingKeys: String, CodingKey { case companyIds = "company_ids" } }
        struct Payload: Decodable { let companyIds: [String]?; enum CodingKeys: String, CodingKey { case companyIds = "company_ids" } }
        let payload: Payload = try await request("tracking/watchlist", method: "PUT", body: Body(companyIds: companyIds))
        return payload.companyIds ?? companyIds
    }

    /// Synchronous on the server (Claude news search per company) — long timeout.
    func syncAllTracking(companyIds: [String]?) async throws -> Int {
        struct Body: Encodable {
            let companyIds: [String]?
            let markAuto = true
            let execute = false
            enum CodingKeys: String, CodingKey {
                case companyIds = "company_ids"
                case markAuto = "mark_auto"
                case execute
            }
        }
        struct Payload: Decodable { let createdTotal: Int?; enum CodingKeys: String, CodingKey { case createdTotal = "created_total" } }
        let payload: Payload = try await request(
            "tracking/sync-all",
            method: "POST",
            body: Body(companyIds: companyIds),
            timeout: 600
        )
        return payload.createdTotal ?? 0
    }

    func fetchTrackingUpdates(companyId: String, limit: Int = 50) async throws -> MacTrackingUpdates {
        try await request(
            "companies/\(companyId)/tracking-updates",
            method: "GET",
            query: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    func syncTrackingUpdates(companyId: String) async throws -> MacTrackingUpdates {
        struct Body: Encodable {
            let markAuto = true
            let execute = false
            let refreshNews = true
            enum CodingKeys: String, CodingKey {
                case markAuto = "mark_auto"
                case execute
                case refreshNews = "refresh_news"
            }
        }
        return try await request(
            "companies/\(companyId)/tracking-updates/sync",
            method: "POST",
            body: Body(),
            timeout: 300
        )
    }

    func executeAutoRun(companyId: String, autoRunId: String) async throws -> MacAutoRunExecuteResult {
        struct Body: Encodable {
            let acknowledgeReview = true
            enum CodingKeys: String, CodingKey { case acknowledgeReview = "acknowledge_review" }
        }
        return try await request(
            "companies/\(companyId)/tracking-updates/auto-runs/\(autoRunId)/execute",
            method: "POST",
            body: Body(),
            timeout: 120
        )
    }

    // MARK: - Decisions

    func fetchDecisions(companyId: String) async throws -> [MacDecision] {
        struct Payload: Decodable { let items: [MacDecision]? }
        let payload: Payload = try await request("companies/\(companyId)/decisions", method: "GET")
        return payload.items ?? []
    }

    func createDecision(companyId: String, body: MacDecisionCreate) async throws -> MacDecision {
        try await request("companies/\(companyId)/decisions", method: "POST", body: body)
    }

    func deleteDecision(companyId: String, decisionId: String) async throws {
        try await requestVoid("companies/\(companyId)/decisions/\(decisionId)", method: "DELETE")
    }

    // MARK: - Memo analysis (IC prep) & evidence

    func fetchMemoAnalysis(companyId: String) async throws -> MacMemoAnalysis {
        try await request("companies/\(companyId)/memo-analysis", method: "GET", timeout: 60)
    }

    func runMemoTool(companyId: String, tool: String) async throws -> MacMemoAnalysis {
        try await request("companies/\(companyId)/memo-analysis/tools/\(tool)/run", method: "POST", timeout: 120)
    }

    func patchReadinessReviews(companyId: String, items: [MacReadinessReviewPatch.Item]) async throws -> MacMemoAnalysis {
        try await request(
            "companies/\(companyId)/memo-analysis/artifacts/readiness_reviews",
            method: "PATCH",
            body: MacReadinessReviewPatch(items: items)
        )
    }

    func approveMemoAnalysis(companyId: String) async throws -> MacMemoAnalysis {
        try await request("companies/\(companyId)/memo-analysis/approve", method: "POST")
    }

    func fetchEvidenceMatrix(companyId: String) async throws -> MacEvidenceMatrix {
        try await request("companies/\(companyId)/evidence-matrix", method: "GET", timeout: 60)
    }

    // MARK: - Deal CRM & people (company record only — nothing inferred)

    func fetchDealPipeline(companyId: String) async throws -> MacDealPipeline {
        try await request("companies/\(companyId)/deal-pipeline", method: "GET")
    }

    func updateDealPipeline(companyId: String, fields: [String: Any]) async throws -> MacDealPipeline {
        let url = try apiURL("companies/\(companyId)/deal-pipeline")
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: fields)
        let (data, response) = try await session.data(for: req)
        try Self.check(response: response, data: data)
        do {
            return try decoder.decode(MacDealPipeline.self, from: data)
        } catch {
            throw MacAPIError.decoding
        }
    }

    func fetchFounderDossier(companyId: String) async throws -> MacFounderDossier {
        try await request("companies/\(companyId)/founder-dossier", method: "GET")
    }

    func refreshFounderDossier(companyId: String) async throws -> MacFounderDossier {
        try await request("companies/\(companyId)/founder-dossier/deep-search", method: "POST")
    }

    // MARK: - Server-sent events

    /// Generic SSE tail. `path` may be an absolute API path ("/api/memos/…/stream")
    /// or relative to the API root.
    nonisolated func streamEvents(path: String) -> AsyncThrowingStream<MacSSEEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = try Self.streamURL(for: path)
                    var req = URLRequest(url: url)
                    req.timeoutInterval = 60 * 60
                    req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
                    if let token = MacConfig.readToken() {
                        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    let (bytes, response) = try await URLSession.shared.bytes(for: req)
                    if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        throw MacAPIError.http(http.statusCode, "Stream HTTP \(http.statusCode)")
                    }
                    var eventName: String?
                    var dataLines: [String] = []
                    for try await line in bytes.lines {
                        try Task.checkCancellation()
                        if line.hasPrefix(":") { continue }
                        if line.isEmpty {
                            if !dataLines.isEmpty {
                                continuation.yield(MacSSEEvent(event: eventName, data: dataLines.joined(separator: "\n")))
                            }
                            eventName = nil
                            dataLines = []
                            continue
                        }
                        if line.hasPrefix("event:") {
                            eventName = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            dataLines.append(String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces))
                        }
                    }
                    if !dataLines.isEmpty {
                        continuation.yield(MacSSEEvent(event: eventName, data: dataLines.joined(separator: "\n")))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func streamURL(for path: String) throws -> URL {
        if path.hasPrefix("http") {
            guard let url = URL(string: path) else { throw MacAPIError.invalidURL }
            return url
        }
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.hasPrefix("api/") {
            var components = URLComponents(url: MacConfig.baseURL, resolvingAgainstBaseURL: false)!
            components.path = "/" + trimmed
            guard let url = components.url else { throw MacAPIError.invalidURL }
            return url
        }
        return MacConfig.apiRoot.appendingPathComponent(trimmed)
    }

    // MARK: - Copilot (context-aware Ask)

    func fetchCopilotContext(companyId: String, context: MacCopilotContext) async throws -> MacCopilotContextInfo {
        try await request("companies/\(companyId)/copilot/context", method: "POST", body: context)
    }

    /// Quick or deep Ask. The console stream has no token deltas: assistant text arrives as
    /// `claude_action/thinking` blocks and the canonical reply on the terminal `done` event.
    func askCopilotStream(
        companyId: String,
        prompt: String,
        persona: MacCopilotPersona,
        context: MacCopilotContext,
        mode: String = "quick"
    ) -> AsyncThrowingStream<MacCopilotChunk, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let fullPrompt = persona.promptPrefix + prompt
                    struct AskBody: Encodable {
                        let prompt: String
                        let mode: String
                        let outputLanguage: String
                        let context: MacCopilotContext
                        enum CodingKeys: String, CodingKey {
                            case prompt, mode, context
                            case outputLanguage = "output_language"
                        }
                    }
                    struct AskResponse: Decodable {
                        let streamUrl: String?
                        enum CodingKeys: String, CodingKey { case streamUrl = "stream_url" }
                    }

                    let res: AskResponse = try await self.request(
                        "companies/\(companyId)/copilot/ask",
                        method: "POST",
                        body: AskBody(prompt: fullPrompt, mode: mode, outputLanguage: "en", context: context)
                    )
                    guard let streamPath = res.streamUrl, !streamPath.isEmpty else {
                        throw MacAPIError.stream("No response stream available.")
                    }
                    try await self.pumpConsoleStream(path: streamPath, into: continuation)
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Shared reader for copilot and console turn streams.
    nonisolated func pumpConsoleStream(
        path: String,
        into continuation: AsyncThrowingStream<MacCopilotChunk, Error>.Continuation
    ) async throws {
        for try await event in streamEvents(path: path) {
            try Task.checkCancellation()
            if event.event == "error" {
                throw MacAPIError.stream(event.json?["error"] as? String ?? "Stream error")
            }
            guard let obj = event.json else { continue }
            let type = (obj["type"] as? String) ?? ""
            switch type {
            case "claude_action":
                let action = (obj["action"] as? String) ?? ""
                if action == "thinking", let text = obj["text"] as? String, !text.isEmpty {
                    continuation.yield(.partial(text))
                } else if action == "tool_use", let tool = obj["tool"] as? String {
                    continuation.yield(.tool("Using \(tool)…"))
                } else if action == "interrupted" {
                    throw MacAPIError.stream("Interrupted: \((obj["reason"] as? String) ?? "unknown")")
                }
            case "done":
                continuation.yield(.final((obj["text"] as? String) ?? ""))
                return
            case "error":
                throw MacAPIError.stream((obj["error"] as? String) ?? (obj["message"] as? String) ?? "Assistant error")
            case "cancelled":
                throw MacAPIError.stream("Cancelled")
            default:
                break
            }
        }
    }

    // MARK: - Attention queue

    func fetchDeskScreener(limit: Int = 20) async throws -> [MacScreenerItem] {
        struct Payload: Decodable { let items: [MacScreenerItem]? }
        let payload: Payload = try await request("desk/screener", method: "GET", query: [URLQueryItem(name: "limit", value: String(limit))])
        return payload.items ?? []
    }

    func fetchDeskDigest(since: Date?, limit: Int = 20) async throws -> [MacDigestItem] {
        struct Payload: Decodable { let items: [MacDigestItem]? }
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        if let since {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            query.append(URLQueryItem(name: "since", value: f.string(from: since)))
        }
        let payload: Payload = try await request("desk/digest", method: "GET", query: query)
        return payload.items ?? []
    }

    func fetchIntakeUnresolved() async throws -> [MacIntakeItem] {
        try await request("intake/unresolved", method: "GET")
    }

    // MARK: - Signal ledger

    func fetchSignals() async throws -> [MacSignal] {
        struct Payload: Decodable { let entries: [MacSignal]? }
        let payload: Payload = try await request("signals/ledger", method: "GET", query: [URLQueryItem(name: "score", value: "true")], timeout: 45)
        return payload.entries ?? []
    }

    func logSignal(ticker: String, direction: String, label: String, priceAtSignal: Double?) async throws -> MacSignal {
        struct Body: Encodable {
            let ticker: String
            let direction: String
            let label: String
            let source = "macos"
            let priceAtSignal: Double?
            enum CodingKeys: String, CodingKey {
                case ticker, direction, label, source
                case priceAtSignal = "price_at_signal"
            }
        }
        struct Payload: Decodable { let entry: MacSignal }
        let payload: Payload = try await request(
            "signals/ledger",
            method: "POST",
            body: Body(ticker: ticker.uppercased(), direction: direction, label: label, priceAtSignal: priceAtSignal)
        )
        return payload.entry
    }

    func deleteSignal(id: String) async throws {
        try await requestVoid("signals/ledger/\(id)", method: "DELETE")
    }

    // MARK: - Console sessions

    func listConsoleSessions(companyId: String) async throws -> [MacConsoleSession] {
        try await request("companies/\(companyId)/console/sessions", method: "GET")
    }

    func createConsoleSession(companyId: String, includeBackgroundDocs: Bool, includeLibraryDocs: Bool, outputLanguage: String) async throws -> MacConsoleSession {
        struct Body: Encodable {
            let includeBackgroundDocs: Bool
            let includeLibraryDocs: Bool
            let outputLanguage: String
            enum CodingKeys: String, CodingKey {
                case includeBackgroundDocs = "include_background_docs"
                case includeLibraryDocs = "include_library_docs"
                case outputLanguage = "output_language"
            }
        }
        return try await request(
            "companies/\(companyId)/console/sessions",
            method: "POST",
            body: Body(includeBackgroundDocs: includeBackgroundDocs, includeLibraryDocs: includeLibraryDocs, outputLanguage: outputLanguage),
            timeout: 60
        )
    }

    func fetchConsoleTurns(companyId: String, sessionId: String) async throws -> [MacConsoleTurn] {
        try await request("companies/\(companyId)/console/sessions/\(sessionId)/turns", method: "GET")
    }

    /// `multipart/form-data` — `prompt` field plus repeatable `images` files (PDF/DOC/DOCX allowed too).
    func askConsole(companyId: String, sessionId: String, prompt: String, attachments: [URL]) async throws -> MacConsoleAskResult {
        let boundary = "bsh-\(UUID().uuidString)"
        var body = Data()
        func append(_ s: String) { body.append(s.data(using: .utf8)!) }
        append("--\(boundary)\r\nContent-Disposition: form-data; name=\"prompt\"\r\n\r\n\(prompt)\r\n")
        for url in attachments {
            guard let data = try? Data(contentsOf: url) else { continue }
            let mime = Self.mimeType(for: url)
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"images\"; filename=\"\(url.lastPathComponent)\"\r\nContent-Type: \(mime)\r\n\r\n")
            body.append(data)
            append("\r\n")
        }
        append("--\(boundary)--\r\n")

        let url = try apiURL("companies/\(companyId)/console/sessions/\(sessionId)/ask")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 120
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = body
        let (data, response) = try await session.data(for: req)
        try Self.check(response: response, data: data)
        do {
            return try decoder.decode(MacConsoleAskResult.self, from: data)
        } catch {
            throw MacAPIError.decoding
        }
    }

    private static func mimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "webp": return "image/webp"
        case "pdf": return "application/pdf"
        case "doc": return "application/msword"
        case "docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        default: return "application/octet-stream"
        }
    }

    func cancelConsoleTurn(companyId: String, sessionId: String, turnId: String) async throws {
        try await requestVoid("companies/\(companyId)/console/sessions/\(sessionId)/ask/\(turnId)/cancel", method: "POST")
    }

    func archiveConsoleSession(companyId: String, sessionId: String) async throws -> MacConsoleSession {
        try await request("companies/\(companyId)/console/sessions/\(sessionId)/archive", method: "POST")
    }

    func deleteConsoleSession(companyId: String, sessionId: String) async throws {
        try await requestVoid("companies/\(companyId)/console/sessions/\(sessionId)", method: "DELETE")
    }

    // MARK: - HTTP

    private func request<T: Decodable>(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        timeout: TimeInterval = 30
    ) async throws -> T {
        let data = try await rawData(path, method: method, query: query, body: body, timeout: timeout)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw MacAPIError.decoding
        }
    }

    private func requestVoid(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil
    ) async throws {
        _ = try await rawData(path, method: method, query: query, body: body)
    }

    private func rawData(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        timeout: TimeInterval = 30
    ) async throws -> Data {
        let url = try apiURL(path, query: query)
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = timeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try encoder.encode(AnyEncodable(body))
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw MacAPIError.transport(error.localizedDescription)
        }
        try Self.check(response: response, data: data)
        return data
    }

    private func downloadBinary(_ pathOrURL: String) async throws -> Data {
        let url: URL
        if pathOrURL.hasPrefix("http") {
            guard let remote = URL(string: pathOrURL) else { throw MacAPIError.invalidURL }
            url = remote
        } else {
            url = try absoluteURL(pathOrURL)
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 60
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: req)
        try Self.check(response: response, data: data)
        return data
    }

    private static func check(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw MacAPIError.http(-1, "No HTTP response")
        }
        if http.statusCode == 401 {
            throw MacAPIError.unauthorized
        }
        if http.statusCode == 403 {
            throw MacAPIError.forbidden(detail(from: data, status: 403))
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http(http.statusCode, detail(from: data, status: http.statusCode))
        }
    }

    private func apiURL(_ path: String, query: [URLQueryItem] = []) throws -> URL {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard var components = URLComponents(url: MacConfig.apiRoot, resolvingAgainstBaseURL: false) else {
            throw MacAPIError.invalidURL
        }
        let root = MacConfig.apiRoot.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [root, trimmed].filter { !$0.isEmpty }.joined(separator: "/")
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw MacAPIError.invalidURL }
        return url
    }

    private func absoluteURL(_ path: String) throws -> URL {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard var components = URLComponents(url: MacConfig.baseURL, resolvingAgainstBaseURL: false) else {
            throw MacAPIError.invalidURL
        }
        if let q = trimmed.firstIndex(of: "?") {
            components.path = "/" + String(trimmed[..<q])
            components.query = String(trimmed[trimmed.index(after: q)...])
        } else {
            components.path = "/" + trimmed
        }
        guard let url = components.url else { throw MacAPIError.invalidURL }
        return url
    }

    private static func detail(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let d = obj["detail"] as? String { return d }
            if let d = obj["message"] as? String { return d }
        }
        return "HTTP \(status)"
    }
}

private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ value: any Encodable) {
        encodeFunc = value.encode
    }
    func encode(to encoder: Encoder) throws { try encodeFunc(encoder) }
}
