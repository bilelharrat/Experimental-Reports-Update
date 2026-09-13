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

    func fetchNews(tickers: [String], limit: Int = 40) async throws -> [MacNewsItem] {
        struct DTO: Decodable {
            let id: String?
            let title: String?
            let source: String?
            let publishedAt: String?
            let ticker: String?
            let url: String?
            enum CodingKeys: String, CodingKey {
                case id, title, source, ticker, url
                case publishedAt = "published_at"
            }
        }
        struct Payload: Decodable { let items: [DTO]? }
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        for t in tickers.prefix(8) { query.append(URLQueryItem(name: "ticker", value: t)) }
        let payload: Payload = try await request("quotes/news", method: "GET", query: query)
        return (payload.items ?? []).compactMap { dto in
            guard let title = dto.title, !title.isEmpty else { return nil }
            return MacNewsItem(
                id: dto.id ?? title,
                title: title,
                source: dto.source,
                publishedAt: dto.publishedAt,
                ticker: dto.ticker,
                url: dto.url
            )
        }
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
