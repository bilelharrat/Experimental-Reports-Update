import Foundation

enum MacAPIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden(String)
    case http(Int, String)
    case decoding
    case transport(String)
    case stream(String)
    case invalidPayload(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Bad API URL"
        case .invalidPayload(let msg): return msg.isEmpty ? "Request contains a value that cannot be sent" : msg
        case .unauthorized: return "Signed out — sign in again"
        case .forbidden(let detail): return detail.isEmpty ? "Permission denied" : detail
        case .http(let code, let detail): return detail.isEmpty ? "HTTP \(code)" : detail
        case .decoding: return "Bad response"
        case .transport(let msg): return msg
        case .stream(let msg): return msg
        }
    }
}

/// Follows a redirect only when it keeps the request's method and body and, for a request that
/// carries the session token, stays on the configured server. Anything else hands the 3xx back to
/// `check`, so a write can never silently turn into a GET or leak its credentials to another host.
final class MacRedirectPolicy: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    static let shared = MacRedirectPolicy()

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        let original = task.originalRequest
        let method = (original?.httpMethod ?? "GET").uppercased()
        let newMethod = (request.httpMethod ?? "GET").uppercased()
        let droppedBody = (original?.httpBody != nil || original?.httpBodyStream != nil)
            && request.httpBody == nil && request.httpBodyStream == nil
        let carriesToken = original?.value(forHTTPHeaderField: "Authorization") != nil
        guard let target = request.url,
              newMethod == method,
              !droppedBody,
              !carriesToken || MacAPIClient.isOwnOrigin(target)
        else {
            completionHandler(nil)
            return
        }
        completionHandler(request)
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
        do {
            return try await request("auth/token", method: "POST", body: Body(email: email, password: password))
        } catch MacAPIError.unauthorized {
            throw MacAPIError.http(401, "Invalid email or password.")
        }
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
        try await request("reports", method: "GET", query: [URLQueryItem(name: "lite", value: "1")])
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

    // MARK: - Quotes, news, pulse

    func fetchQuotes(tickers: [String]) async throws -> [MacQuote] {
        let unique = Array(Set(tickers.map { $0.uppercased() })).sorted()
        guard !unique.isEmpty else { return [] }
        guard let url = MacConfig.serverURL(
            "quotes",
            query: unique.map { URLQueryItem(name: "ticker", value: $0) }
        ) else { throw MacAPIError.invalidURL }
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
            do {
                let brief: MacNewsBrief = try await request("news/brief", method: "GET", query: query)
                return brief
            } catch MacAPIError.http(404, _) {
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
        return try await request("news/brief", method: "POST", body: req, timeout: 120)
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
            query: [URLQueryItem(name: "range", value: range.apiValue)]
        )
    }

    func fetchWorkspace(ticker: String) async throws -> MacQuoteWorkspace {
        try await request("quotes/\(ticker.uppercased())/workspace", method: "GET")
    }

    func fetchPeers(ticker: String) async throws -> MacQuotePeers {
        try await request("quotes/\(ticker.uppercased())/peers", method: "GET", timeout: 60)
    }

    func fetchQuoteCalendar(tickers: [String]) async throws -> MacQuoteCalendar {
        try await request(
            "quotes/calendar",
            method: "GET",
            query: tickers.map { URLQueryItem(name: "ticker", value: $0.uppercased()) }
        )
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
        return try Self.deskPrefsBlob(from: data)
    }

    private static func deskPrefsBlob(from data: Data) throws -> [String: Any] {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MacAPIError.decoding
        }
        return (root["data"] as? [String: Any]) ?? [:]
    }

    func fetchDeskPrefs() async throws -> DeskPrefsResult {
        let blob = try await fetchDeskPrefsBlob()
        return Self.deskPrefs(from: blob)
    }

    private static func deskPrefs(from blob: [String: Any]) -> DeskPrefsResult {
        let watchlist = (blob["bsh.marketPinnedTickers"] as? [Any])?.compactMap { ($0 as? String)?.uppercased() } ?? []

        let lots = ((blob["bsh.bookLots"] as? [[String: Any]]) ?? []).compactMap(lot(from:))
        let rules = ((blob["bsh.marketAlertRules"] as? [[String: Any]]) ?? []).compactMap(rule(from:))
        return DeskPrefsResult(watchlist: watchlist, lots: lots, rules: rules)
    }

    /// A finite number, or a string holding one; booleans and anything else are not numbers.
    static func finiteNumber(_ value: Any?) -> Double? {
        if let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() {
            return n.doubleValue.isFinite ? n.doubleValue : nil
        }
        if let s = value as? String, let d = Double(s.trimmingCharacters(in: .whitespaces)), d.isFinite {
            return d
        }
        return nil
    }

    /// Rows another client wrote with a non-numeric quantity are left out of the parsed list
    /// (and kept verbatim on save) rather than shown and rewritten as zero.
    private static func lot(from item: [String: Any]) -> MacBookLot? {
        guard let t = item["ticker"] as? String, !t.isEmpty,
              let shares = finiteNumber(item["shares"]) ?? finiteNumber(item["qty"]),
              let cost = finiteNumber(item["costBasis"]) ?? finiteNumber(item["cost"]) else { return nil }
        let id = (item["id"] as? String) ?? UUID().uuidString
        return MacBookLot(id: id, ticker: t.uppercased(), shares: shares, costBasis: cost)
    }

    private static func rule(from item: [String: Any]) -> MacAlertRule? {
        guard let t = item["ticker"] as? String, !t.isEmpty,
              let threshold = finiteNumber(item["threshold"]) else { return nil }
        let id = (item["id"] as? String) ?? UUID().uuidString
        let kind = (item["kind"] as? String) ?? "price"
        let direction = (item["direction"] as? String) ?? "above"
        let enabled = (item["enabled"] as? Bool) ?? true
        return MacAlertRule(id: id, ticker: t.uppercased(), kind: kind, threshold: threshold, direction: direction, enabled: enabled)
    }

    /// Read-modify-write: only the three keys the Mac owns change; everything the
    /// web desk stores in the same blob survives.
    /// Returns the prefs as saved by the server, so callers can replace any stale local copy.
    @discardableResult
    func saveDeskPrefs(watchlist: [String], lots: [MacBookLot], rules: [MacAlertRule]) async throws -> DeskPrefsResult {
        var blob = try await fetchDeskPrefsBlob()

        var lotsById: [String: [String: Any]] = [:]
        var lotsByTicker: [String: [String: Any]] = [:]
        var rawLots: [[String: Any]] = []
        for item in (blob["bsh.bookLots"] as? [[String: Any]]) ?? [] {
            if Self.lot(from: item) == nil { rawLots.append(item); continue }
            if let id = item["id"] as? String, lotsById[id] == nil { lotsById[id] = item }
            if let t = item["ticker"] as? String, lotsByTicker[t.uppercased()] == nil {
                lotsByTicker[t.uppercased()] = item
            }
        }
        for l in lots {
            var d = lotsById[l.id] ?? lotsByTicker[l.ticker.uppercased()] ?? [:]
            d["id"] = l.id
            d["ticker"] = l.ticker.uppercased()
            d["shares"] = l.shares
            d["qty"] = l.shares
            d["costBasis"] = l.costBasis
            d["cost"] = l.costBasis
            rawLots.append(d)
        }

        var rulesById: [String: [String: Any]] = [:]
        var rawRules: [[String: Any]] = []
        for item in (blob["bsh.marketAlertRules"] as? [[String: Any]]) ?? [] {
            if Self.rule(from: item) == nil { rawRules.append(item); continue }
            if let id = item["id"] as? String, rulesById[id] == nil { rulesById[id] = item }
        }
        for r in rules {
            var d = rulesById[r.id] ?? [:]
            d["id"] = r.id
            d["ticker"] = r.ticker.uppercased()
            d["kind"] = r.kind
            d["threshold"] = r.threshold
            d["direction"] = r.direction
            d["enabled"] = r.enabled
            if r.kind == "sma_cross", !(d["window"] is NSNumber) {
                d["window"] = r.threshold
            }
            rawRules.append(d)
        }

        blob["bsh.marketPinnedTickers"] = watchlist.map { $0.uppercased() }
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
        guard JSONSerialization.isValidJSONObject(payload) else {
            throw MacAPIError.invalidPayload("Desk preferences contain a value that is not a finite number.")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        } catch {
            throw MacAPIError.transport(error.localizedDescription)
        }
        try Self.check(response: response, data: data)
        let saved = try Self.deskPrefsBlob(from: data)
        return Self.deskPrefs(from: saved)
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

    func createReport(
        companyId: String,
        reportType: String,
        audience: String,
        language: String,
        reportMode: String = "full",
        quality: String = "best",
        analysisSessionId: String? = nil
    ) async throws -> MacReport {
        struct Body: Encodable {
            let companyId: String
            let reportType: String
            let audience: String
            let language: String
            let reportMode: String
            let quality: String
            let analysisSessionId: String?

            enum CodingKeys: String, CodingKey {
                case audience, language, quality
                case companyId = "company_id"
                case reportType = "report_type"
                case reportMode = "report_mode"
                case analysisSessionId = "analysis_session_id"
            }
        }
        return try await request(
            "reports",
            method: "POST",
            body: Body(
                companyId: companyId,
                reportType: reportType,
                audience: audience,
                language: language,
                reportMode: reportMode,
                quality: quality,
                analysisSessionId: analysisSessionId
            )
        )
    }

    func startMemoStudioInvestigate(
        companyId: String,
        reportType: String? = nil,
        analysisSessionId: String? = nil
    ) async throws -> MacReport {
        struct Body: Encodable {
            let companyId: String
            let reportType: String?
            let analysisSessionId: String?
            enum CodingKeys: String, CodingKey {
                case companyId = "company_id"
                case reportType = "report_type"
                case analysisSessionId = "analysis_session_id"
            }
        }
        return try await request(
            "memos/studio/investigate",
            method: "POST",
            body: Body(companyId: companyId, reportType: reportType, analysisSessionId: analysisSessionId)
        )
    }

    func generateMemoFromStudio(reportId: String) async throws -> MacReport {
        try await request("memos/studio/\(reportId)/generate", method: "POST")
    }

    // MARK: - Memo Studio Editor State & Mutations

    func fetchMemoEditor(companyId: String) async throws -> MacMemoEditorState {
        try await request("companies/\(companyId)/memo-editor", method: "GET")
    }

    func patchMemoEditorCard(
        companyId: String,
        sectionId: String,
        cardId: String,
        included: Bool? = nil,
        expanded: Bool? = nil,
        title: String? = nil,
        category: String? = nil,
        severity: String? = nil,
        likelihood: String? = nil,
        agentRating: String? = nil
    ) async throws -> MacMemoEditorState {
        struct PatchBody: Encodable {
            let included: Bool?
            let expanded: Bool?
            let title: String?
            let category: String?
            let severity: String?
            let likelihood: String?
            let agentRating: String?

            enum CodingKeys: String, CodingKey {
                case included, expanded, title, category, severity, likelihood
                case agentRating = "agent_rating"
            }
        }
        return try await request(
            "companies/\(companyId)/memo-editor/sections/\(sectionId)/cards/\(cardId)",
            method: "PATCH",
            body: PatchBody(
                included: included,
                expanded: expanded,
                title: title,
                category: category,
                severity: severity,
                likelihood: likelihood,
                agentRating: agentRating
            )
        )
    }

    func addMemoEditorCard(
        companyId: String,
        sectionId: String,
        title: String,
        category: String? = nil,
        severity: String? = nil,
        rating: String? = nil,
        likelihood: String? = nil,
        bullets: [String]? = nil
    ) async throws -> MacMemoEditorState {
        struct CreateBody: Encodable {
            let title: String
            let category: String?
            let severity: String?
            let rating: String?
            let likelihood: String?
            let bullets: [String]?
        }
        return try await request(
            "companies/\(companyId)/memo-editor/sections/\(sectionId)/cards",
            method: "POST",
            body: CreateBody(
                title: title,
                category: category,
                severity: severity,
                rating: rating,
                likelihood: likelihood,
                bullets: bullets
            )
        )
    }

    func deleteMemoEditorCard(companyId: String, sectionId: String, cardId: String) async throws -> MacMemoEditorState {
        try await request(
            "companies/\(companyId)/memo-editor/sections/\(sectionId)/cards/\(cardId)",
            method: "DELETE"
        )
    }

    func moveMemoEditorCard(companyId: String, sectionId: String, cardId: String, direction: String) async throws -> MacMemoEditorState {
        struct MoveBody: Encodable {
            let direction: String
        }
        return try await request(
            "companies/\(companyId)/memo-editor/sections/\(sectionId)/cards/\(cardId)/move",
            method: "POST",
            body: MoveBody(direction: direction)
        )
    }

    func reorderMemoEditorCards(companyId: String, sectionId: String, orderedIds: [String]) async throws -> MacMemoEditorState {
        struct ReorderBody: Encodable {
            let orderedIds: [String]
            enum CodingKeys: String, CodingKey {
                case orderedIds = "ordered_ids"
            }
        }
        return try await request(
            "companies/\(companyId)/memo-editor/sections/\(sectionId)/cards/reorder",
            method: "POST",
            body: ReorderBody(orderedIds: orderedIds)
        )
    }

    func refineMemoRisk(
        companyId: String,
        riskId: String,
        framing: String = "other",
        analystNote: String = ""
    ) async throws {
        struct RefineBody: Encodable {
            let framing: String
            let analystNote: String
            enum CodingKeys: String, CodingKey {
                case framing
                case analystNote = "analyst_note"
            }
        }
        let _: [String: String]? = try? await request(
            "companies/\(companyId)/memo-analysis/risks/\(riskId)/refine",
            method: "POST",
            body: RefineBody(framing: framing, analystNote: analystNote)
        )
    }

    // MARK: - Pipeline: tracking rollup, watchlist, sync

    func fetchTrackingRollup(companyIds: [String]) async throws -> MacRollup {
        guard !companyIds.isEmpty else {
            return MacRollup(generatedAt: nil, companies: [], attention: [], totals: nil, unknownCompanyIds: nil)
        }
        var parts: [MacRollup] = []
        for start in stride(from: 0, to: companyIds.count, by: 60) {
            let chunk = Array(companyIds[start..<min(start + 60, companyIds.count)])
            let part: MacRollup = try await request(
                "tracking/rollup",
                method: "GET",
                query: chunk.map { URLQueryItem(name: "company_id", value: $0) }
            )
            parts.append(part)
        }
        if parts.count == 1 { return parts[0] }
        func rank(_ severity: String?) -> Int {
            switch (severity ?? "").lowercased() {
            case "high": return 0
            case "medium": return 1
            case "low": return 2
            default: return 3
            }
        }
        let attention = parts.flatMap(\.attention).sorted {
            let l = rank($0.severity), r = rank($1.severity)
            if l != r { return l < r }
            return ($0.companyName ?? $0.companyId ?? "") < ($1.companyName ?? $1.companyId ?? "")
        }
        let unknown = parts.compactMap(\.unknownCompanyIds).flatMap { $0 }
        return MacRollup(
            generatedAt: parts.compactMap(\.generatedAt).max(),
            companies: parts.flatMap(\.companies),
            attention: attention,
            totals: MacRollupTotals.merged(parts.compactMap(\.totals)),
            unknownCompanyIds: unknown.isEmpty ? nil : unknown
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

    /// `create: false` only reads: a company with no Memo Studio session answers
    /// 404 instead of having one started for it. The dossier loads readiness
    /// gates on sight, and opening a company must not leave a session file
    /// behind for every company glanced at.
    func fetchMemoAnalysis(companyId: String, create: Bool = true) async throws -> MacMemoAnalysis {
        try await request(
            "companies/\(companyId)/memo-analysis",
            method: "GET",
            query: create ? [] : [URLQueryItem(name: "create", value: "false")],
            timeout: 60
        )
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
        guard JSONSerialization.isValidJSONObject(fields) else {
            throw MacAPIError.invalidPayload("Deal pipeline fields contain a value that is not a finite number.")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: fields)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        } catch {
            throw MacAPIError.transport(error.localizedDescription)
        }
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

    /// Gemini web research on the team. It runs 50-120s (the server allows
    /// Gemini 240s), so the 30s default timed out every refresh.
    func refreshFounderDossier(companyId: String) async throws -> MacFounderDossier {
        try await request("companies/\(companyId)/founder-dossier/deep-search", method: "POST", timeout: 300)
    }

    // MARK: - Thesis, intake, comps, cap model

    func fetchThesis() async throws -> MacThesis {
        try await request("thesis", method: "GET")
    }

    func saveThesis(_ thesis: MacThesis) async throws -> MacThesis {
        try await request("thesis", method: "PUT", body: thesis)
    }

    func scoreThesis(companyId: String) async throws -> MacThesisScore {
        struct Body: Encodable { let companyId: String; enum CodingKeys: String, CodingKey { case companyId = "company_id" } }
        return try await request("thesis/score", method: "POST", body: Body(companyId: companyId))
    }

    /// Multipart upload of a deck; the server files it, extracts facts with page refs and scores the thesis.
    func intakeDeck(fileURL: URL, companyName: String?, companyId: String?) async throws -> MacIntakeResult {
        let data = try Data(contentsOf: fileURL)
        let boundary = "bsh-\(UUID().uuidString)"
        var body = Data()
        func append(_ s: String) { body.append(s.data(using: .utf8)!) }
        if let companyName, !companyName.isEmpty {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"company_name\"\r\n\r\n\(companyName)\r\n")
        }
        if let companyId, !companyId.isEmpty {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"company_id\"\r\n\r\n\(companyId)\r\n")
        }
        append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\r\nContent-Type: \(Self.mimeType(for: fileURL))\r\n\r\n")
        body.append(data)
        append("\r\n--\(boundary)--\r\n")

        let url = try apiURL("intake/decks")
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
        let (respData, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        try Self.check(response: response, data: respData)
        do {
            return try decoder.decode(MacIntakeResult.self, from: respData)
        } catch {
            throw MacAPIError.decoding
        }
    }

    /// Kick off the Claude structured summary for an uploaded file (shows in the Jobs blotter).
    func startFileSummary(companyId: String, fileId: String) async throws {
        try await requestVoid("companies/\(companyId)/files/\(fileId)/summary", method: "POST")
    }

    func fetchComps(companyId: String, refresh: Bool) async throws -> MacComps {
        try await request(
            "companies/\(companyId)/comps",
            method: "GET",
            query: [URLQueryItem(name: "refresh", value: refresh ? "true" : "false")],
            timeout: 90
        )
    }

    func saveCompsPeers(companyId: String, tickers: [String]) async throws {
        struct Body: Encodable { let tickers: [String] }
        try await requestVoid("companies/\(companyId)/comps/peers", method: "PUT", body: Body(tickers: tickers))
    }

    func fetchCapModel(companyId: String) async throws -> MacCapModel {
        try await request("companies/\(companyId)/cap-model", method: "GET")
    }

    func saveCapModel(companyId: String, inputs: MacCapModelInputs) async throws -> MacCapModel {
        try await request("companies/\(companyId)/cap-model", method: "PUT", body: inputs)
    }

    // MARK: - Private portfolio

    func fetchPortfolioDashboard() async throws -> MacPortfolioDashboard {
        try await request("portfolio", method: "GET")
    }

    func fetchPortfolio(companyId: String) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)", method: "GET")
    }

    func updatePortfolioPosition(companyId: String, fields: [String: Any?]) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)/position", method: "PUT", body: MacJSONObject(fields))
    }

    func addPortfolioKpi(companyId: String, fields: [String: Any?]) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)/kpis", method: "POST", body: MacJSONObject(fields))
    }

    func addFounderUpdate(companyId: String, text: String, asOf: String?, subject: String, source: String) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)/updates", method: "POST",
                          body: MacJSONObject(["text": text, "as_of": asOf, "subject": subject, "source": source]))
    }

    func addPortfolioMark(companyId: String, valueUsd: Double, basis: String, asOf: String?, note: String) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)/marks", method: "POST",
                          body: MacJSONObject(["value_usd": valueUsd, "basis": basis, "as_of": asOf, "note": note]))
    }

    func deletePortfolioItem(companyId: String, kind: String, itemId: String) async throws -> MacPortfolioCompany {
        try await request("portfolio/\(companyId)/\(kind)/\(itemId)", method: "DELETE")
    }

    func fetchReserves() async throws -> MacReservesPlan {
        try await request("portfolio/reserves", method: "GET")
    }

    func saveReserves(_ settings: MacReservesSettings) async throws -> MacReservesPlan {
        try await request("portfolio/reserves", method: "PUT", body: settings)
    }

    func downloadTearSheet(companyId: String) async throws -> Data {
        try await rawData("portfolio/\(companyId)/tear-sheet.docx", method: "GET", timeout: 60)
    }

    // MARK: - IC room

    func fetchReferenceCalls(companyId: String) async throws -> MacReferenceCalls {
        try await request("companies/\(companyId)/reference-calls", method: "GET")
    }

    func addReferenceCall(companyId: String, fields: [String: Any?]) async throws -> MacReferenceCalls {
        try await request("companies/\(companyId)/reference-calls", method: "POST", body: MacJSONObject(fields))
    }

    func deleteReferenceCall(companyId: String, itemId: String) async throws -> MacReferenceCalls {
        try await request("companies/\(companyId)/reference-calls/\(itemId)", method: "DELETE")
    }

    func fetchICMeetings(companyId: String) async throws -> MacICMeetings {
        try await request("companies/\(companyId)/ic/meetings", method: "GET")
    }

    func openICMeeting(companyId: String, title: String, reportId: String?) async throws -> MacICMeeting {
        try await request("companies/\(companyId)/ic/meetings", method: "POST", body: MacJSONObject(["title": title, "report_id": reportId]))
    }

    func castICVote(companyId: String, meetingId: String, member: String?, vote: String, conviction: Int?, note: String) async throws -> MacICMeeting {
        var fields: [String: Any?] = ["vote": vote, "conviction": conviction, "note": note]
        if let member { fields["member"] = member }
        return try await request("companies/\(companyId)/ic/meetings/\(meetingId)/votes", method: "POST", body: MacJSONObject(fields))
    }

    func closeICMeeting(companyId: String, meetingId: String, recordDecision: Bool, explanation: String) async throws -> MacICMeeting {
        try await request("companies/\(companyId)/ic/meetings/\(meetingId)/close", method: "POST",
                          body: MacJSONObject(["record_decision": recordDecision, "explanation": explanation]))
    }

    func fetchComparables(companyId: String) async throws -> MacComparables {
        try await request("companies/\(companyId)/ic/comparables", method: "GET")
    }

    func fetchRedTeam(companyId: String) async throws -> MacRedTeam {
        try await request("companies/\(companyId)/ic/red-team", method: "GET")
    }

    func startRedTeam(companyId: String) async throws {
        try await requestVoid("companies/\(companyId)/ic/red-team", method: "POST")
    }

    // MARK: - Firm layer

    func firmSearch(_ query: String, kinds: [String] = [], companyId: String? = nil) async throws -> MacFirmSearch {
        var q = [URLQueryItem(name: "q", value: query), URLQueryItem(name: "limit", value: "40")]
        if !kinds.isEmpty { q.append(URLQueryItem(name: "kinds", value: kinds.joined(separator: ","))) }
        if let companyId { q.append(URLQueryItem(name: "company_id", value: companyId)) }
        return try await request("firm/search", method: "GET", query: q)
    }

    func fetchComments(companyId: String) async throws -> MacComments {
        try await request("companies/\(companyId)/comments", method: "GET")
    }

    func addComment(companyId: String, text: String, target: MacCommentTarget?, parentId: String?) async throws -> MacComment {
        struct Body: Encodable { let text: String; let target: MacCommentTarget?; let parent_id: String? }
        return try await request("companies/\(companyId)/comments", method: "POST", body: Body(text: text, target: target, parent_id: parentId))
    }

    func resolveComment(companyId: String, commentId: String, resolved: Bool) async throws -> MacComment {
        try await request("companies/\(companyId)/comments/\(commentId)/resolve", method: "POST", body: MacJSONObject(["resolved": resolved]))
    }

    func deleteComment(companyId: String, commentId: String) async throws -> MacComments {
        try await request("companies/\(companyId)/comments/\(commentId)", method: "DELETE")
    }

    func fetchMentions() async throws -> MacMentions {
        try await request("me/mentions", method: "GET")
    }

    func fetchChatChannels() async throws -> MacChatChannels {
        try await request("chat/channels", method: "GET")
    }

    func fetchChat(channel: String, since: String?) async throws -> MacChatPage {
        var q: [URLQueryItem] = []
        if let since { q.append(URLQueryItem(name: "since", value: since)) }
        return try await request("chat/\(channel)", method: "GET", query: q)
    }

    func postChat(channel: String, text: String, companyId: String?) async throws -> MacChatMessage {
        try await request("chat/\(channel)", method: "POST", body: MacJSONObject(["text": text, "company_id": companyId]))
    }

    func fetchAudit(companyId: String?, limit: Int = 200) async throws -> MacAuditPage {
        var q = [URLQueryItem(name: "limit", value: String(limit))]
        if let companyId { q.append(URLQueryItem(name: "company_id", value: companyId)) }
        return try await request("audit", method: "GET", query: q)
    }

    func fetchTranscripts(companyId: String?, query: String) async throws -> MacTranscriptList {
        var q = [URLQueryItem(name: "q", value: query)]
        if let companyId { q.append(URLQueryItem(name: "company_id", value: companyId)) }
        return try await request("transcripts", method: "GET", query: q)
    }

    func fetchTranscript(id: String) async throws -> MacTranscript {
        try await request("transcripts/\(id)", method: "GET")
    }

    func addTranscript(fields: [String: Any?]) async throws -> MacTranscript {
        try await request("transcripts", method: "POST", body: MacJSONObject(fields))
    }

    func uploadTranscript(fileURL: URL, title: String, kind: String, companyId: String?, tags: String, participants: String) async throws -> MacTranscript {
        let data = try Data(contentsOf: fileURL)
        let boundary = "bsh-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        field("title", title)
        field("kind", kind)
        field("company_id", companyId ?? "")
        field("tags", tags)
        field("participants", participants)
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\r\nContent-Type: \(Self.mimeType(for: fileURL))\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        var req = URLRequest(url: try apiURL("transcripts/upload"))
        req.httpMethod = "POST"
        req.timeoutInterval = 120
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        req.httpBody = body
        let (respData, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        try Self.check(response: response, data: respData)
        do { return try decoder.decode(MacTranscript.self, from: respData) } catch { throw MacAPIError.decoding }
    }

    func deleteTranscript(id: String) async throws {
        try await requestVoid("transcripts/\(id)", method: "DELETE")
    }

    func addHighlight(transcriptId: String, text: String, note: String) async throws -> MacTranscript {
        try await request("transcripts/\(transcriptId)/highlights", method: "POST", body: MacJSONObject(["text": text, "note": note]))
    }

    func removeHighlight(transcriptId: String, highlightId: String) async throws -> MacTranscript {
        try await request("transcripts/\(transcriptId)/highlights/\(highlightId)", method: "DELETE")
    }

    func fetchSignalScore(companyId: String) async throws -> MacSignalScore {
        try await request("companies/\(companyId)/signal-score", method: "GET", timeout: 60)
    }

    // MARK: - Unified profile, filings watch, signal watch, numbers lint

    func fetchProfile(companyId: String) async throws -> MacCompanyProfile {
        try await request("companies/\(companyId)/profile", method: "GET", timeout: 60)
    }

    /// Next earnings date, recent quarters against estimates and SEC filings for
    /// one listed company (server-cached six hours per ticker).
    func fetchCompanyEarningsFilings(companyId: String, refresh: Bool = false) async throws -> MacCompanyEarningsFilings {
        try await request(
            "companies/\(companyId)/earnings-filings",
            method: "GET",
            query: refresh ? [URLQueryItem(name: "refresh", value: "true")] : [],
            timeout: 60
        )
    }

    func fetchFilingsWatch(refresh: Bool) async throws -> MacFilingsWatch {
        try await request("filings-watch", method: "GET", query: [URLQueryItem(name: "refresh", value: refresh ? "true" : "false")], timeout: 120)
    }

    func fetchSignalMoves() async throws -> MacSignalMoves {
        try await request("signal-watch", method: "GET", timeout: 120)
    }

    func snapshotSignals() async throws {
        try await requestVoid("signal-watch/snapshot", method: "POST")
    }

    func fetchNumberLint(companyId: String) async throws -> MacNumberLint {
        try await request("companies/\(companyId)/memo-number-lint", method: "GET", timeout: 60)
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
                    if Self.isOwnOrigin(url), let token = MacConfig.readToken() {
                        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    let (bytes, response) = try await URLSession.shared.bytes(for: req, delegate: MacRedirectPolicy.shared)
                    if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        throw MacAPIError.http(http.statusCode, "Stream HTTP \(http.statusCode)")
                    }
                    var parser = MacSSEParser()
                    var lineBuffer: [UInt8] = []
                    for try await byte in bytes {
                        if byte != 0x0A {
                            lineBuffer.append(byte)
                            continue
                        }
                        try Task.checkCancellation()
                        if lineBuffer.last == 0x0D { lineBuffer.removeLast() }
                        let line = String(decoding: lineBuffer, as: UTF8.self)
                        lineBuffer.removeAll(keepingCapacity: true)
                        if let event = parser.feed(line: line) {
                            continuation.yield(event)
                        }
                    }
                    if !lineBuffer.isEmpty {
                        if lineBuffer.last == 0x0D { lineBuffer.removeLast() }
                        if let event = parser.feed(line: String(decoding: lineBuffer, as: UTF8.self)) {
                            continuation.yield(event)
                        }
                    }
                    if let event = parser.finish() {
                        continuation.yield(event)
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
        guard let url = MacConfig.serverURL(path) else { throw MacAPIError.invalidURL }
        return url
    }

    // MARK: - Copilot (context-aware Ask)

    func fetchCopilotContext(companyId: String, context: MacCopilotContext) async throws -> MacCopilotContextInfo {
        try await request("companies/\(companyId)/copilot/context", method: "POST", body: context)
    }

    /// Quick or deep Ask. The console stream has no token deltas: assistant text arrives as
    /// `claude_action/thinking` blocks and the canonical reply on the terminal `done` event.
    ///
    /// The lens rides as `lens_instruction`, not glued onto the question: the thread is
    /// shared with the team, and they should read the question, not the lens.
    /// `attachments` are stored names from `stageCopilotAttachment`; `edits` is the
    /// turn id of a question this one rewrites.
    func askCopilotStream(
        companyId: String,
        prompt: String,
        persona: MacCopilotPersona,
        context: MacCopilotContext,
        mode: String = "quick",
        attachments: [String] = [],
        attachmentNames: [String: String] = [:],
        edits: String? = nil
    ) -> AsyncThrowingStream<MacCopilotChunk, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    struct AskBody: Encodable {
                        let prompt: String
                        let mode: String
                        let outputLanguage: String
                        let context: MacCopilotContext
                        let lensInstruction: String
                        let attachments: [String]
                        let attachmentNames: [String: String]
                        let edits: String?
                        enum CodingKeys: String, CodingKey {
                            case prompt, mode, context, attachments, edits
                            case outputLanguage = "output_language"
                            case lensInstruction = "lens_instruction"
                            case attachmentNames = "attachment_names"
                        }
                    }
                    struct AskResponse: Decodable {
                        let streamUrl: String?
                        let sessionId: String?
                        let turnId: String?
                        enum CodingKeys: String, CodingKey {
                            case streamUrl = "stream_url"
                            case sessionId = "session_id"
                            case turnId = "turn_id"
                        }
                    }

                    let res: AskResponse = try await self.request(
                        "companies/\(companyId)/copilot/ask",
                        method: "POST",
                        body: AskBody(
                            prompt: prompt,
                            mode: mode,
                            outputLanguage: "en",
                            context: context,
                            lensInstruction: persona.promptPrefix,
                            attachments: attachments,
                            attachmentNames: attachmentNames,
                            edits: edits
                        )
                    )
                    if let sid = res.sessionId, let tid = res.turnId {
                        continuation.yield(.started(sessionId: sid, turnId: tid))
                    }
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

    // MARK: - Warren threads, attachments, offered work

    /// The company's Warren threads, newest first — the team's, not this Mac's.
    func fetchCopilotThreads(companyId: String, mode: String = "quick") async throws -> [MacCopilotThread] {
        try await request(
            "companies/\(companyId)/copilot/threads",
            method: "GET",
            query: [URLQueryItem(name: "mode", value: mode)]
        )
    }

    /// Files the current thread into the history and opens a fresh one, for everyone.
    func startCopilotThread(companyId: String, mode: String = "quick") async throws -> String {
        struct Body: Encodable { let mode: String }
        struct Started: Decodable {
            let sessionId: String
            enum CodingKeys: String, CodingKey { case sessionId = "session_id" }
        }
        let started: Started = try await request(
            "companies/\(companyId)/copilot/threads", method: "POST", body: Body(mode: mode)
        )
        return started.sessionId
    }

    /// Stage one file beside Warren's session; returns the stored name the ask carries.
    /// The server turns documents into text here, so an unreadable one fails now.
    func stageCopilotAttachment(companyId: String, fileURL: URL, mode: String = "quick") async throws -> String {
        let data = try Data(contentsOf: fileURL)
        let boundary = "bsh-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\n\(mode)\r\n".data(using: .utf8)!)
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\r\nContent-Type: \(Self.mimeType(for: fileURL))\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        var req = URLRequest(url: try apiURL("companies/\(companyId)/copilot/attachments"))
        req.httpMethod = "POST"
        req.timeoutInterval = 120
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        req.httpBody = body
        let (respData, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        try Self.check(response: response, data: respData)
        struct Staged: Decodable {
            let storedName: String
            enum CodingKeys: String, CodingKey { case storedName = "stored_name" }
        }
        do { return try decoder.decode(Staged.self, from: respData).storedName } catch { throw MacAPIError.decoding }
    }

    /// Start the deep read of a research file (the web's "Analyze" on a file).
    func analyzeResearchFile(companyId: String, fileId: String) async throws {
        let escaped = fileId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? fileId
        try await requestVoid("companies/\(companyId)/research-files/\(escaped)/analysis", method: "POST")
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
        try Task.checkCancellation()
        throw MacAPIError.stream("The connection closed before the answer finished.")
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

    func logSignal(ticker: String, direction: String, label: String, priceAtSignal: Double?) async throws -> (entry: MacSignal, deduplicated: Bool) {
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
        struct Payload: Decodable { let entry: MacSignal; let deduplicated: Bool? }
        let payload: Payload = try await request(
            "signals/ledger",
            method: "POST",
            body: Body(ticker: ticker.uppercased(), direction: direction, label: label, priceAtSignal: priceAtSignal)
        )
        return (payload.entry, payload.deduplicated ?? false)
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
        let (data, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
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
        case "pptx": return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        case "xlsx": return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        case "gif": return "image/gif"
        case "rtf": return "application/rtf"
        case "txt", "log": return "text/plain"
        case "md", "markdown": return "text/markdown"
        case "csv": return "text/csv"
        case "tsv": return "text/tab-separated-values"
        case "json": return "application/json"
        case "yaml", "yml": return "application/yaml"
        case "html", "htm": return "text/html"
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
            (data, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        } catch is CancellationError {
            throw CancellationError()
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw CancellationError()
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
        if Self.isOwnOrigin(url), let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req, delegate: MacRedirectPolicy.shared)
        } catch is CancellationError {
            throw CancellationError()
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw CancellationError()
        } catch {
            throw MacAPIError.transport(error.localizedDescription)
        }
        try Self.check(response: response, data: data)
        return data
    }

    /// True when `url` points at the configured server (scheme, host and port).
    static func isOwnOrigin(_ url: URL) -> Bool {
        let base = MacConfig.baseURL
        let scheme = (url.scheme ?? "http").lowercased()
        let baseScheme = (base.scheme ?? "http").lowercased()
        let port = url.port ?? (scheme == "https" ? 443 : 80)
        let basePort = base.port ?? (baseScheme == "https" ? 443 : 80)
        return scheme == baseScheme
            && (url.host ?? "").lowercased() == (base.host ?? "").lowercased()
            && port == basePort
    }

    // MARK: - Session loss & server back-off (shared by every request path)

    /// Called once per 401 from the configured server, off the main actor.
    nonisolated(unsafe) static var onUnauthorized: (@Sendable (URL) -> Void)?

    private static let retryAfterLock = NSLock()
    nonisolated(unsafe) private static var retryAfterUntil: Date?

    /// Seconds the server asked clients to wait (429/503 `Retry-After`), 0 when none is pending.
    static func retryAfterDelay() -> TimeInterval {
        retryAfterLock.lock()
        defer { retryAfterLock.unlock() }
        guard let until = retryAfterUntil else { return 0 }
        let remaining = until.timeIntervalSinceNow
        if remaining <= 0 { retryAfterUntil = nil; return 0 }
        return remaining
    }

    private static func noteRetryAfter(_ http: HTTPURLResponse) {
        guard let raw = http.value(forHTTPHeaderField: "Retry-After")?.trimmingCharacters(in: .whitespaces),
              !raw.isEmpty else { return }
        let until: Date
        if let seconds = Double(raw) {
            until = Date().addingTimeInterval(min(max(seconds, 1), 300))
        } else {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = TimeZone(identifier: "GMT")
            f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
            guard let date = f.date(from: raw) else { return }
            until = min(date, Date().addingTimeInterval(300))
        }
        retryAfterLock.lock()
        if until > (retryAfterUntil ?? .distantPast) { retryAfterUntil = until }
        retryAfterLock.unlock()
    }

    private static func check(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw MacAPIError.http(-1, "No HTTP response")
        }
        if http.statusCode == 401 {
            if let url = http.url, isOwnOrigin(url) { onUnauthorized?(url) }
            throw MacAPIError.unauthorized
        }
        if http.statusCode == 403 {
            throw MacAPIError.forbidden(detail(from: data, status: 403))
        }
        if http.statusCode == 429 || http.statusCode == 503 { noteRetryAfter(http) }
        if (300..<400).contains(http.statusCode) {
            let target = http.value(forHTTPHeaderField: "Location")
                .flatMap { URL(string: $0, relativeTo: http.url)?.absoluteURL.absoluteString }
            throw MacAPIError.http(
                http.statusCode,
                target.map { "The server redirected this request to \($0). Update the server address in Settings." }
                    ?? "The server redirected this request. Check the server address in Settings."
            )
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http(http.statusCode, detail(from: data, status: http.statusCode))
        }
    }

    private func apiURL(_ path: String, query: [URLQueryItem] = []) throws -> URL {
        guard let url = MacConfig.serverURL(path, query: query) else { throw MacAPIError.invalidURL }
        return url
    }

    private func absoluteURL(_ path: String) throws -> URL {
        guard let url = MacConfig.serverURL(path) else { throw MacAPIError.invalidURL }
        return url
    }

    private static func detail(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let d = obj["detail"] as? String, !d.isEmpty { return d }
            if let d = obj["detail"] as? [String: Any] {
                if let m = d["message"] as? String, !m.isEmpty { return m }
                if let m = d["detail"] as? String, !m.isEmpty { return m }
                if let c = d["code"] as? String, !c.isEmpty { return c }
            }
            if let items = obj["detail"] as? [[String: Any]] {
                let msgs = items.compactMap { item -> String? in
                    guard let msg = item["msg"] as? String, !msg.isEmpty else { return nil }
                    let loc = ((item["loc"] as? [Any]) ?? [])
                        .map { "\($0)" }
                        .filter { $0 != "body" && $0 != "query" && $0 != "path" }
                    return loc.isEmpty ? msg : "\(loc.joined(separator: ".")): \(msg)"
                }
                if !msgs.isEmpty { return msgs.joined(separator: "; ") }
            }
            if let d = obj["message"] as? String, !d.isEmpty { return d }
            if let d = obj["error"] as? String, !d.isEmpty { return d }
        }
        return "HTTP \(status)"
    }
}

/// Incremental server-sent-events parser: feed one line at a time (without its line
/// terminator); an empty line dispatches the pending event.
struct MacSSEParser {
    private var eventName: String?
    private var dataLines: [String] = []

    mutating func feed(line: String) -> MacSSEEvent? {
        if line.isEmpty {
            return finish()
        }
        if line.hasPrefix(":") { return nil }
        if line.hasPrefix("event:") {
            eventName = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
        } else if line.hasPrefix("data:") {
            dataLines.append(String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces))
        }
        return nil
    }

    mutating func finish() -> MacSSEEvent? {
        defer {
            eventName = nil
            dataLines = []
        }
        guard !dataLines.isEmpty else { return nil }
        return MacSSEEvent(event: eventName, data: dataLines.joined(separator: "\n"))
    }
}

private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ value: any Encodable) {
        encodeFunc = value.encode
    }
    func encode(to encoder: Encoder) throws { try encodeFunc(encoder) }
}


/// Encodes a loose `[String: Any?]` (String / Double / Int / Bool / nil) as a JSON object.
struct MacJSONObject: Encodable {
    let fields: [String: Any?]
    init(_ fields: [String: Any?]) { self.fields = fields }

    private struct Key: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Key.self)
        for (name, value) in fields {
            let key = Key(stringValue: name)
            switch value {
            case nil: try c.encodeNil(forKey: key)
            case let v as String: try c.encode(v, forKey: key)
            case let v as Double: try c.encode(v, forKey: key)
            case let v as Int: try c.encode(v, forKey: key)
            case let v as Bool: try c.encode(v, forKey: key)
            case let v as [String]: try c.encode(v, forKey: key)
            case let v as [Double]: try c.encode(v, forKey: key)
            default: try c.encode(String(describing: value!), forKey: key)
            }
        }
    }
}
