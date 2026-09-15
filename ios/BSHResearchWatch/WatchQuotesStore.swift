import Combine
import Foundation
import WidgetKit

@MainActor
final class WatchQuotesStore: ObservableObject {
    @Published private(set) var watchlist: [WatchQuote] = WatchConfig.demoQuotes()
    @Published private(set) var gainers: [WatchQuote] = []
    @Published private(set) var losers: [WatchQuote] = []
    @Published private(set) var active: [WatchQuote] = []
    @Published private(set) var news: [WatchNewsItem] = []
    @Published private(set) var pulse: WatchPulseBrief?
    @Published private(set) var sparks: [String: WatchSparkSeries] = [:]
    @Published private(set) var loading = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var lastRefresh: Date?
    @Published private(set) var stale = false
    @Published var layoutStyle: WatchLayoutStyle = WatchConfig.layoutStyle

    private static let cacheKey = "bsh.watch.desk.cache.v2"
    private var didLoadCache = false

    init() {
        _ = loadCache()
        if watchlist.isEmpty {
            watchlist = WatchConfig.demoQuotes()
            stale = true
        }
    }

    var movers: [WatchQuote] {
        (gainers + losers).sorted { abs($0.pct ?? 0) > abs($1.pct ?? 0) }
    }

    /// Compact tape: pins first, then hottest movers, de-duped. Never empty.
    var tapeQuotes: [WatchQuote] {
        var seen = Set<String>()
        var out: [WatchQuote] = []
        for quote in watchlist + gainers.prefix(4) + losers.prefix(4) + active.prefix(3) {
            if seen.insert(quote.ticker).inserted {
                out.append(quote)
            }
        }
        if out.isEmpty {
            return WatchConfig.demoQuotes()
        }
        // Prefer default tape order when we only have demos / sparse pins.
        let preferred = WatchConfig.resolvedTapeTickers()
        if out.count < 3 {
            for demo in WatchConfig.demoQuotes() where seen.insert(demo.ticker).inserted {
                out.append(demo)
            }
        }
        out.sort { a, b in
            let ia = preferred.firstIndex(of: a.ticker) ?? 999
            let ib = preferred.firstIndex(of: b.ticker) ?? 999
            if ia != ib { return ia < ib }
            return a.ticker < b.ticker
        }
        return out
    }

    /// Compact live Tape: exactly two companies (equity pins / defaults).
    var featureQuotes: [WatchQuote] {
        let wanted = WatchConfig.featureCompanyTickers()
        var byTicker = Dictionary(uniqueKeysWithValues: tapeQuotes.map { ($0.ticker, $0) })
        for demo in WatchConfig.demoQuotes() where byTicker[demo.ticker] == nil {
            byTicker[demo.ticker] = demo
        }
        let resolved = wanted.compactMap { byTicker[$0] }
        if resolved.count >= 2 { return Array(resolved.prefix(2)) }
        return Array((resolved + tapeQuotes.filter { !wanted.contains($0.ticker) }).prefix(2))
    }

    func spark(for ticker: String) -> WatchSparkSeries? {
        sparks[ticker.uppercased()]
    }

    var pulseHeadline: String {
        pulse?.note?.headlineEn?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
            ?? "Morning brief"
    }

    var pulseBullets: [String] {
        Array((pulse?.note?.bulletsEn ?? []).prefix(3))
    }

    var pulseIndices: [WatchQuote] {
        Array((pulse?.indices ?? []).prefix(4).map(\.asQuote))
    }

    var pulseGainers: [WatchQuote] {
        Array((pulse?.movers?.gainers ?? []).prefix(3).map(\.asQuote))
    }

    var pulseLosers: [WatchQuote] {
        Array((pulse?.movers?.losers ?? []).prefix(3).map(\.asQuote))
    }

    var pulseAlerts: [WatchPulseAlert] {
        Array((pulse?.alertsLastDay ?? []).prefix(3))
    }

    func setLayoutStyle(_ style: WatchLayoutStyle) {
        layoutStyle = style
        WatchConfig.layoutStyle = style
    }

    func refresh() async {
        if !didLoadCache {
            _ = loadCache()
            didLoadCache = true
        }

        loading = true
        errorMessage = nil
        defer { loading = false }

        let tickers = resolvedTickers()
        let featureTickers = WatchConfig.featureCompanyTickers()
        async let quotesTask = WatchAPIClient.shared.fetchQuotes(tickers: tickers)
        async let screenersTask = WatchAPIClient.shared.fetchScreeners(limit: 6)
        async let newsTask = WatchAPIClient.shared.fetchNews(tickers: tickers, limit: 12)
        async let pulseTask = WatchAPIClient.shared.fetchPulse()
        async let sparksTask = WatchAPIClient.shared.fetchSparks(tickers: featureTickers)

        var firstError: String?

        do {
            let quotes = try await quotesTask
            if !quotes.isEmpty {
                watchlist = quotes
            }
        } catch {
            firstError = error.localizedDescription
        }

        do {
            let screeners = try await screenersTask
            gainers = screeners.gainers
            losers = screeners.losers
            active = screeners.active
        } catch {
            firstError = firstError ?? error.localizedDescription
        }

        do {
            news = try await newsTask
        } catch {
            firstError = firstError ?? error.localizedDescription
        }

        do {
            pulse = try await pulseTask
        } catch {
            // Brief may 404 if never built — keep prior / empty, not fatal.
            if pulse == nil {
                firstError = firstError ?? error.localizedDescription
            }
        }

        do {
            let fetched = try await sparksTask
            if !fetched.isEmpty {
                sparks.merge(fetched) { _, new in new }
            }
        } catch {
            // Sparks are optional; keep prior series when offline.
        }

        if !watchlist.isEmpty || !gainers.isEmpty || !news.isEmpty || pulse != nil {
            stale = firstError != nil
            lastRefresh = .now
            errorMessage = stale ? firstError : nil
            saveCache()
            WidgetCenter.shared.reloadAllTimelines()
        } else if loadCache() {
            stale = true
            errorMessage = firstError
        } else {
            watchlist = WatchConfig.demoQuotes()
            stale = true
            errorMessage = firstError ?? "Demo tape (offline)"
        }

        if watchlist.isEmpty {
            watchlist = WatchConfig.demoQuotes()
            stale = true
        }
    }

    func resolvedTickers() -> [String] {
        WatchConfig.resolvedTapeTickers()
    }

    private func saveCache() {
        let payload = CachePayload(
            watchlist: watchlist,
            gainers: gainers,
            losers: losers,
            active: active,
            news: news,
            pulse: pulse,
            savedAt: .now
        )
        if let data = try? JSONEncoder().encode(payload) {
            WatchConfig.sharedDefaults.set(data, forKey: Self.cacheKey)
            UserDefaults.standard.set(data, forKey: Self.cacheKey)
        }
    }

    @discardableResult
    private func loadCache() -> Bool {
        let data = WatchConfig.sharedDefaults.data(forKey: Self.cacheKey)
            ?? UserDefaults.standard.data(forKey: Self.cacheKey)
        guard let data,
              let payload = try? JSONDecoder().decode(CachePayload.self, from: data)
        else { return false }
        let hasAnything = !payload.watchlist.isEmpty
            || !payload.gainers.isEmpty
            || !payload.news.isEmpty
            || payload.pulse != nil
        guard hasAnything else { return false }
        if !payload.watchlist.isEmpty {
            watchlist = payload.watchlist
        }
        gainers = payload.gainers
        losers = payload.losers
        active = payload.active
        news = payload.news
        pulse = payload.pulse
        lastRefresh = payload.savedAt
        stale = true
        didLoadCache = true
        return true
    }

    private struct CachePayload: Codable {
        let watchlist: [WatchQuote]
        let gainers: [WatchQuote]
        let losers: [WatchQuote]
        let active: [WatchQuote]
        let news: [WatchNewsItem]
        let pulse: WatchPulseBrief?
        let savedAt: Date
    }
}

private extension String {
    var nilIfEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
