import Foundation

enum WatchAPIError: Error, LocalizedError {
    case invalidURL
    case http(Int)
    case decoding
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Bad API URL"
        case .http(let code): return "HTTP \(code)"
        case .decoding: return "Bad response"
        case .transport(let msg): return msg
        }
    }
}

/// Lightweight desk client for watchOS (no Keychain; works with anon-dev).
actor WatchAPIClient {
    static let shared = WatchAPIClient()

    private let session: URLSession
    private let decoder = JSONDecoder()

    init(session: URLSession = .shared) {
        self.session = session
    }

    func fetchQuotes(tickers: [String]) async throws -> [WatchQuote] {
        let unique = Array(Set(tickers.map { $0.uppercased() })).sorted()
        guard !unique.isEmpty else { return [] }

        var components = URLComponents(
            url: WatchConfig.apiRoot.appendingPathComponent("quotes"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = unique.map { URLQueryItem(name: "ticker", value: $0) }
        guard let url = components.url else { throw WatchAPIError.invalidURL }

        let data = try await get(url)
        guard let payload = try? decoder.decode(WatchQuotesPayload.self, from: data) else {
            throw WatchAPIError.decoding
        }
        return unique.compactMap { ticker in
            guard let dto = payload.quotes?[ticker] else { return nil }
            return WatchQuote(
                ticker: ticker,
                last: dto.lastPrice,
                pct: dto.changePct1d,
                name: dto.name
            )
        }
    }

    struct ScreenersBundle {
        let gainers: [WatchQuote]
        let losers: [WatchQuote]
        let active: [WatchQuote]
    }

    func fetchScreeners(limit: Int = 6) async throws -> ScreenersBundle {
        let url = WatchConfig.apiRoot.appendingPathComponent("quotes/screeners")
        let data = try await get(url)
        guard let payload = try? decoder.decode(WatchScreenersPayload.self, from: data) else {
            throw WatchAPIError.decoding
        }
        return ScreenersBundle(
            gainers: (payload.gainers ?? []).prefix(limit).map { $0.asQuote() },
            losers: (payload.losers ?? []).prefix(limit).map { $0.asQuote() },
            active: (payload.active ?? []).prefix(limit).map { $0.asQuote() }
        )
    }

    func fetchMovers(limit: Int = 6) async throws -> [WatchQuote] {
        let screeners = try await fetchScreeners(limit: limit)
        return (screeners.gainers + screeners.losers)
            .sorted { abs($0.pct ?? 0) > abs($1.pct ?? 0) }
    }

    func fetchNews(tickers: [String], limit: Int = 12) async throws -> [WatchNewsItem] {
        var components = URLComponents(
            url: WatchConfig.apiRoot.appendingPathComponent("quotes/news"),
            resolvingAgainstBaseURL: false
        )!
        var items: [URLQueryItem] = [URLQueryItem(name: "limit", value: String(limit))]
        for ticker in Array(Set(tickers.map { $0.uppercased() })).prefix(8) {
            items.append(URLQueryItem(name: "ticker", value: ticker))
        }
        components.queryItems = items
        guard let url = components.url else { throw WatchAPIError.invalidURL }

        let data = try await get(url)
        guard let payload = try? decoder.decode(WatchNewsPayload.self, from: data) else {
            throw WatchAPIError.decoding
        }
        return (payload.items ?? []).compactMap { $0.asItem() }
    }

    func fetchPulse() async throws -> WatchPulseBrief {
        let url = WatchConfig.apiRoot.appendingPathComponent("market-brief")
        let data = try await get(url)
        guard let brief = try? decoder.decode(WatchPulseBrief.self, from: data) else {
            throw WatchAPIError.decoding
        }
        return brief
    }

    func fetchSparks(tickers: [String]) async throws -> [String: WatchSparkSeries] {
        let unique = Array(Set(tickers.map { $0.uppercased() })).sorted()
        guard !unique.isEmpty else { return [:] }

        var components = URLComponents(
            url: WatchConfig.apiRoot.appendingPathComponent("quotes/spark"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = unique.map { URLQueryItem(name: "ticker", value: $0) }
        guard let url = components.url else { throw WatchAPIError.invalidURL }

        let data = try await get(url)
        guard let payload = try? decoder.decode(WatchSparkPayload.self, from: data) else {
            throw WatchAPIError.decoding
        }
        return payload.sparks ?? [:]
    }

    private func get(_ url: URL) async throws -> Data {
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        req.setValue("watchos", forHTTPHeaderField: "X-BSH-Client")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await session.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                throw WatchAPIError.http(-1)
            }
            guard (200..<300).contains(http.statusCode) else {
                throw WatchAPIError.http(http.statusCode)
            }
            return data
        } catch let err as WatchAPIError {
            throw err
        } catch {
            throw WatchAPIError.transport(error.localizedDescription)
        }
    }
}
