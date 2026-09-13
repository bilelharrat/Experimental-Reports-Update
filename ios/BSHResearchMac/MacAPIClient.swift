import Foundation

enum MacAPIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case http(Int, String)
    case decoding
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Bad API URL"
        case .unauthorized: return "Signed out — sign in again"
        case .http(let code, let detail): return detail.isEmpty ? "HTTP \(code)" : detail
        case .decoding: return "Bad response"
        case .transport(let msg): return msg
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

    func login(email: String, password: String) async throws -> String {
        struct Body: Encodable { let email: String; let password: String }
        let res: MacAuthTokenResponse = try await request(
            "auth/token",
            method: "POST",
            body: Body(email: email, password: password)
        )
        return res.token
    }

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

    func fetchPDF(pathOrURL: String) async throws -> Data {
        try await download(pathOrURL: pathOrURL)
    }

    func download(pathOrURL: String) async throws -> Data {
        try await downloadBinary(pathOrURL)
    }

    func getCompany(id: String) async throws -> MacCompany {
        try await request("companies/\(id)", method: "GET")
    }

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

    func searchAutocomplete(query: String, limit: Int = 8) async throws -> [MacAutocompleteHit] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return [] }
        return try await request(
            "companies/autocomplete",
            method: "GET",
            query: [URLQueryItem(name: "q", value: q), URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    func fetchActiveJobs() async throws -> [MacActiveJob] {
        try await request("jobs/active", method: "GET")
    }

    func fetchMarketPulsePayload() async throws -> MacMarketPulsePayload {
        try await request("research-pages/market-pulse", method: "GET")
    }

    func fetchPulse() async throws -> MacPulseBrief {
        try await request("market-brief", method: "GET")
    }

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

    // MARK: - Market Chart & Workspace

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

    // MARK: - Desk Preferences (Synced with Web & iPad)

    struct DeskPrefsResult {
        let watchlist: [String]
        let lots: [MacBookLot]
        let rules: [MacAlertRule]
    }

    func fetchDeskPrefs() async throws -> DeskPrefsResult {
        let url = try apiURL("desk/prefs")
        var req = URLRequest(url: url)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            return DeskPrefsResult(watchlist: ["SPY", "QQQ", "DIA", "IWM"], lots: [], rules: [])
        }
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let blob = root["data"] as? [String: Any] else {
            return DeskPrefsResult(watchlist: ["SPY", "QQQ", "DIA", "IWM"], lots: [], rules: [])
        }

        let watchlist = (blob["bsh.marketPinnedTickers"] as? [String]) ?? ["SPY", "QQQ", "DIA", "IWM"]
        
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

    func saveDeskPrefs(watchlist: [String], lots: [MacBookLot], rules: [MacAlertRule]) async throws {
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

        let blob: [String: Any] = [
            "bsh.marketPinnedTickers": watchlist,
            "bsh.bookLots": rawLots,
            "bsh.marketAlertRules": rawRules,
        ]

        let url = try apiURL("desk/prefs")
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let payload: [String: Any] = ["data": blob]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (_, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http((response as? HTTPURLResponse)?.statusCode ?? -1, "Failed to save desk preferences")
        }
    }

    // MARK: - Report Options & Generation

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

    // MARK: - Copilot AI Stream

    func askCopilotStream(
        companyId: String,
        prompt: String,
        persona: MacCopilotPersona
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let fullPrompt = persona.promptPrefix + prompt
                    struct AskBody: Encodable {
                        let prompt: String
                        let mode: String
                        let outputLanguage: String
                        enum CodingKeys: String, CodingKey {
                            case prompt, mode
                            case outputLanguage = "output_language"
                        }
                    }
                    struct AskResponse: Decodable {
                        let streamUrl: String?
                        let turnId: String?
                        let sessionId: String?
                        enum CodingKeys: String, CodingKey {
                            case streamUrl = "stream_url"
                            case turnId = "turn_id"
                            case sessionId = "session_id"
                        }
                    }

                    let res: AskResponse = try await self.request(
                        "companies/\(companyId)/copilot/ask",
                        method: "POST",
                        body: AskBody(prompt: fullPrompt, mode: "quick", outputLanguage: "en")
                    )

                    guard let streamPath = res.streamUrl, !streamPath.isEmpty else {
                        continuation.yield("No response stream available.")
                        continuation.finish()
                        return
                    }

                    let streamURL: URL
                    let trimmed = streamPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                    if trimmed.hasPrefix("api/") {
                        streamURL = MacConfig.baseURL.appendingPathComponent(trimmed)
                    } else {
                        streamURL = MacConfig.apiRoot.appendingPathComponent(trimmed)
                    }

                    var streamReq = URLRequest(url: streamURL)
                    streamReq.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    if let token = MacConfig.readToken() {
                        streamReq.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }

                    let (bytes, response) = try await self.session.bytes(for: streamReq)
                    if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        continuation.finish(throwing: MacAPIError.http(http.statusCode, "Stream HTTP error"))
                        return
                    }

                    for try await line in bytes.lines {
                        try Task.checkCancellation()
                        if line.hasPrefix("data:") {
                            let raw = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                            guard let data = raw.data(using: .utf8),
                                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                            else { continue }

                            let type = (obj["type"] as? String) ?? ""
                            if type == "delta" || type == "text" {
                                if let chunk = obj["text"] as? String {
                                    continuation.yield(chunk)
                                }
                            } else if type == "claude_action" {
                                if let action = obj["action"] as? String, action == "thinking",
                                   let chunk = obj["text"] as? String {
                                    continuation.yield(chunk)
                                }
                            } else if type == "done" {
                                break
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    // MARK: - HTTP

    private func request<T: Decodable>(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil
    ) async throws -> T {
        let url = try apiURL(path, query: query)
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 30
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

        guard let http = response as? HTTPURLResponse else {
            throw MacAPIError.http(-1, "No HTTP response")
        }
        if http.statusCode == 401 {
            MacConfig.clearToken()
            throw MacAPIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http(http.statusCode, Self.detail(from: data, status: http.statusCode))
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw MacAPIError.decoding
        }
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
        guard let http = response as? HTTPURLResponse else {
            throw MacAPIError.http(-1, "No HTTP response")
        }
        if http.statusCode == 401 {
            MacConfig.clearToken()
            throw MacAPIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http(http.statusCode, Self.detail(from: data, status: http.statusCode))
        }
        return data
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
