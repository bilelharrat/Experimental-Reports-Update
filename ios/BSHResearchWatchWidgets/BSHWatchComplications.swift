import WidgetKit
import SwiftUI

// MARK: - Shared complication data (mirrors watch app App Group keys)

enum ComplicationAPI {
    static let suite = "group.com.bilelharrrat.bshresearch"
    static let watchlistKey = "bsh.marketPinnedTickers"
    static let baseURLKey = "bsh.baseURL"
    static let cacheKey = "bsh.watch.complication.cache"

    static var baseURL: URL {
        let defaults = UserDefaults(suiteName: suite) ?? .standard
        if let override = defaults.string(forKey: baseURLKey),
           let url = URL(string: override), !override.isEmpty {
            return url
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = URL(string: plist), !plist.isEmpty {
            return url
        }
        return URL(string: "http://10.0.0.218:8010")!
    }

    static func pinnedTickers() -> [String] {
        let defaults = UserDefaults(suiteName: suite) ?? .standard
        let pins = (defaults.array(forKey: watchlistKey) as? [String]) ?? []
        let merged = (["SPY", "QQQ"] + pins.map { $0.uppercased() })
        var seen = Set<String>()
        return merged.filter { seen.insert($0).inserted }.prefix(4).map { $0 }
    }

    static func fetchQuotes(_ tickers: [String]) async -> [ComplicationQuote]? {
        var components = URLComponents(
            url: baseURL.appendingPathComponent("api/quotes"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = tickers.map { URLQueryItem(name: "ticker", value: $0) }
        guard let url = components.url else { return nil }
        var req = URLRequest(url: url)
        req.timeoutInterval = 10
        req.setValue("watchos-complication", forHTTPHeaderField: "X-BSH-Client")
        guard let (data, response) = try? await URLSession.shared.data(for: req),
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let quotes = obj["quotes"] as? [String: [String: Any]]
        else { return nil }
        return tickers.compactMap { ticker in
            guard let row = quotes[ticker.uppercased()] else { return nil }
            return ComplicationQuote(
                ticker: ticker.uppercased(),
                last: row["last_price"] as? Double,
                pct: row["change_pct_1d"] as? Double
            )
        }
    }

    static func saveCache(_ quotes: [ComplicationQuote]) {
        if let data = try? JSONEncoder().encode(quotes) {
            (UserDefaults(suiteName: suite) ?? .standard).set(data, forKey: cacheKey)
        }
    }

    static func loadCache() -> [ComplicationQuote]? {
        let defaults = UserDefaults(suiteName: suite) ?? .standard
        guard let data = defaults.data(forKey: cacheKey),
              let quotes = try? JSONDecoder().decode([ComplicationQuote].self, from: data),
              !quotes.isEmpty
        else { return nil }
        return quotes
    }
}

struct ComplicationQuote: Identifiable, Codable {
    var id: String { ticker }
    let ticker: String
    let last: Double?
    let pct: Double?
}

struct ComplicationEntry: TimelineEntry {
    let date: Date
    let quotes: [ComplicationQuote]
    let stale: Bool

    static let placeholder = ComplicationEntry(
        date: .now,
        quotes: [
            ComplicationQuote(ticker: "SPY", last: 520.12, pct: 0.4),
            ComplicationQuote(ticker: "QQQ", last: 448.30, pct: -0.2),
        ],
        stale: false
    )

    var primary: ComplicationQuote? { quotes.first }
}

struct ComplicationProvider: TimelineProvider {
    func placeholder(in context: Context) -> ComplicationEntry { .placeholder }

    func getSnapshot(in context: Context, completion: @escaping (ComplicationEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        Task { completion(await makeEntry()) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ComplicationEntry>) -> Void) {
        Task {
            let entry = await makeEntry()
            let next = Calendar.current.date(byAdding: .minute, value: 15, to: .now) ?? .now
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func makeEntry() async -> ComplicationEntry {
        let tickers = ComplicationAPI.pinnedTickers()
        if let quotes = await ComplicationAPI.fetchQuotes(tickers), !quotes.isEmpty {
            ComplicationAPI.saveCache(quotes)
            return ComplicationEntry(date: .now, quotes: quotes, stale: false)
        }
        if let cached = ComplicationAPI.loadCache() {
            return ComplicationEntry(date: .now, quotes: cached, stale: true)
        }
        return .placeholder
    }
}

// MARK: - Views

private func fmtPct(_ v: Double?) -> String {
    guard let v else { return "—" }
    return String(format: "%+.1f%%", v)
}

private func tone(_ v: Double?) -> Color {
    guard let v else { return .secondary }
    return v >= 0 ? .green : .red
}

struct CircularComplicationView: View {
    let entry: ComplicationEntry

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            VStack(spacing: 1) {
                Text(entry.primary?.ticker ?? "BSH")
                    .font(.system(.caption2, design: .rounded).weight(.bold))
                    .minimumScaleFactor(0.7)
                Text(fmtPct(entry.primary?.pct))
                    .font(.system(.caption2, design: .rounded).weight(.semibold))
                    .foregroundStyle(tone(entry.primary?.pct))
                    .minimumScaleFactor(0.6)
            }
            .padding(2)
        }
        .widgetURL(WatchConfigURL.ticker(entry.primary?.ticker ?? "SPY"))
    }
}

struct RectangularComplicationView: View {
    let entry: ComplicationEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("BSH")
                .font(.system(.caption2, design: .rounded).weight(.bold))
            ForEach(entry.quotes.prefix(2)) { q in
                HStack {
                    Text(q.ticker)
                        .font(.system(.caption2, design: .monospaced).weight(.semibold))
                    Spacer(minLength: 2)
                    Text(fmtPct(q.pct))
                        .font(.system(.caption2, design: .rounded).weight(.semibold))
                        .foregroundStyle(tone(q.pct))
                }
            }
        }
        .widgetURL(WatchConfigURL.ticker(entry.primary?.ticker ?? "SPY"))
    }
}

enum WatchConfigURL {
    static func ticker(_ symbol: String) -> URL {
        URL(string: "bshresearch://ticker/\(symbol.uppercased())")!
    }
}

struct BSHCircularComplication: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "BSHCircularQuote", provider: ComplicationProvider()) { entry in
            CircularComplicationView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("BSH Quote")
        .description("Primary watchlist quote change.")
        .supportedFamilies([.accessoryCircular])
    }
}

struct BSHRectangularComplication: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "BSHRectangularQuotes", provider: ComplicationProvider()) { entry in
            RectangularComplicationView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("BSH Tape")
        .description("Two watchlist quotes on the face.")
        .supportedFamilies([.accessoryRectangular])
    }
}

@main
struct BSHWatchWidgetsBundle: WidgetBundle {
    var body: some Widget {
        BSHCircularComplication()
        BSHRectangularComplication()
    }
}
