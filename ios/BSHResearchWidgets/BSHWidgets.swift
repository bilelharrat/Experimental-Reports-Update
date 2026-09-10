import WidgetKit
import SwiftUI

// MARK: - Data

struct WidgetQuote: Identifiable, Codable {
    var id: String { ticker }
    let ticker: String
    let last: Double?
    let pct: Double?
}

struct QuotesEntry: TimelineEntry {
    let date: Date
    let quotes: [WidgetQuote]
    let movers: [WidgetQuote]
    let stale: Bool

    static let placeholder = QuotesEntry(
        date: .now,
        quotes: [
            WidgetQuote(ticker: "SPY", last: 762.40, pct: -0.5),
            WidgetQuote(ticker: "QQQ", last: 716.31, pct: -0.3),
            WidgetQuote(ticker: "DIA", last: 524.07, pct: -0.8),
            WidgetQuote(ticker: "IWM", last: 243.11, pct: 0.4),
        ],
        movers: [
            WidgetQuote(ticker: "GOOGL", last: 330.65, pct: -2.3),
            WidgetQuote(ticker: "OXY", last: 61.30, pct: 1.1),
            WidgetQuote(ticker: "TSM", last: 427.30, pct: 2.3),
        ],
        stale: false
    )
}

enum WidgetAPI {
    static let indexTickers = ["SPY", "QQQ", "DIA", "IWM"]

    static var baseURL: URL {
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = URL(string: plist), !plist.isEmpty {
            return url
        }
        return URL(string: "http://127.0.0.1:8010")!
    }

    static func fetchQuotes(_ tickers: [String]) async -> [WidgetQuote]? {
        var components = URLComponents(url: baseURL.appendingPathComponent("api/quotes"), resolvingAgainstBaseURL: false)!
        components.queryItems = tickers.map { URLQueryItem(name: "ticker", value: $0) }
        guard let url = components.url else { return nil }
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        req.setValue("ios-widget", forHTTPHeaderField: "X-BSH-Client")
        guard let (data, response) = try? await URLSession.shared.data(for: req),
              let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let quotes = obj["quotes"] as? [String: [String: Any]]
        else { return nil }
        return tickers.compactMap { ticker in
            guard let row = quotes[ticker.uppercased()] else { return nil }
            return WidgetQuote(
                ticker: ticker.uppercased(),
                last: row["last_price"] as? Double,
                pct: row["change_pct_1d"] as? Double
            )
        }
    }

    static func fetchMovers(limit: Int) async -> [WidgetQuote]? {
        let url = baseURL.appendingPathComponent("api/quotes/screeners")
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        req.setValue("ios-widget", forHTTPHeaderField: "X-BSH-Client")
        guard let (data, response) = try? await URLSession.shared.data(for: req),
              let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        func rows(_ key: String) -> [[String: Any]] {
            obj[key] as? [[String: Any]] ?? []
        }
        let merged = rows("gainers").prefix(limit) + rows("losers").prefix(limit)
        return merged.compactMap { row in
            guard let ticker = row["ticker"] as? String else { return nil }
            let last = (row["last"] as? Double) ?? (row["last_price"] as? Double)
            let pct = (row["change_pct"] as? Double)
                ?? (row["change_pct_1d"] as? Double)
                ?? (row["change"] as? Double)
            return WidgetQuote(ticker: ticker.uppercased(), last: last, pct: pct)
        }
        .sorted { abs($0.pct ?? 0) > abs($1.pct ?? 0) }
    }

    private static let cacheKey = "bsh.widget.cache"

    static func saveCache(_ entry: (quotes: [WidgetQuote], movers: [WidgetQuote])) {
        let payload = ["quotes": entry.quotes, "movers": entry.movers]
        if let data = try? JSONEncoder().encode(payload) {
            UserDefaults.standard.set(data, forKey: cacheKey)
        }
    }

    static func loadCache() -> (quotes: [WidgetQuote], movers: [WidgetQuote])? {
        guard let data = UserDefaults.standard.data(forKey: cacheKey),
              let payload = try? JSONDecoder().decode([String: [WidgetQuote]].self, from: data)
        else { return nil }
        return (payload["quotes"] ?? [], payload["movers"] ?? [])
    }
}

// MARK: - Provider

struct QuotesProvider: TimelineProvider {
    func placeholder(in context: Context) -> QuotesEntry { .placeholder }

    func getSnapshot(in context: Context, completion: @escaping (QuotesEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        Task { completion(await makeEntry()) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<QuotesEntry>) -> Void) {
        Task {
            let entry = await makeEntry()
            // Refresh roughly every 15 minutes.
            let next = Calendar.current.date(byAdding: .minute, value: 15, to: .now) ?? .now
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func makeEntry() async -> QuotesEntry {
        async let quotesTask = WidgetAPI.fetchQuotes(WidgetAPI.indexTickers)
        async let moversTask = WidgetAPI.fetchMovers(limit: 4)
        let (quotes, movers) = await (quotesTask, moversTask)

        if let quotes, !quotes.isEmpty {
            let entry = QuotesEntry(date: .now, quotes: quotes, movers: movers ?? [], stale: false)
            WidgetAPI.saveCache((entry.quotes, entry.movers))
            return entry
        }
        if let cached = WidgetAPI.loadCache() {
            return QuotesEntry(date: .now, quotes: cached.quotes, movers: cached.movers, stale: true)
        }
        return .placeholder
    }
}

// MARK: - Views

private func fmtPrice(_ v: Double?) -> String {
    guard let v else { return "—" }
    return String(format: "$%.2f", v)
}

private func fmtPct(_ v: Double?) -> String {
    guard let v else { return "—" }
    return String(format: "%+.1f%%", v)
}

private func tone(_ v: Double?) -> Color {
    guard let v else { return .secondary }
    return v >= 0 ? .green : .red
}

struct QuoteCell: View {
    let quote: WidgetQuote
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(quote.ticker)
                .font(.caption2.monospaced().weight(.semibold))
                .foregroundStyle(.secondary)
            if !compact {
                Text(fmtPrice(quote.last))
                    .font(.footnote.monospacedDigit().weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            Text(fmtPct(quote.pct))
                .font(.caption2.monospacedDigit().weight(.semibold))
                .foregroundStyle(tone(quote.pct))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct MarketsWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: QuotesEntry

    var body: some View {
        content
            .containerBackground(for: .widget) {
                Color(.systemBackground)
            }
            .widgetURL(URL(string: "bshresearch://ticker/SPY"))
    }

    @ViewBuilder
    private var content: some View {
        switch family {
        case .systemSmall:
            VStack(alignment: .leading, spacing: 6) {
                header
                ForEach(entry.quotes.prefix(3)) { q in
                    HStack {
                        Text(q.ticker).font(.caption.monospaced().weight(.semibold))
                        Spacer()
                        Text(fmtPct(q.pct))
                            .font(.caption.monospacedDigit().weight(.semibold))
                            .foregroundStyle(tone(q.pct))
                    }
                }
                Spacer(minLength: 0)
            }
        case .systemLarge:
            VStack(alignment: .leading, spacing: 10) {
                header
                HStack(spacing: 8) {
                    ForEach(entry.quotes.prefix(4)) { QuoteCell(quote: $0) }
                }
                Divider()
                Text("Movers")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(entry.movers.prefix(6)) { q in
                    HStack {
                        Text(q.ticker).font(.footnote.monospaced().weight(.semibold))
                        Spacer()
                        Text(fmtPrice(q.last))
                            .font(.footnote.monospacedDigit())
                            .foregroundStyle(.secondary)
                        Text(fmtPct(q.pct))
                            .font(.footnote.monospacedDigit().weight(.semibold))
                            .foregroundStyle(tone(q.pct))
                            .frame(width: 58, alignment: .trailing)
                    }
                }
                Spacer(minLength: 0)
            }
        default: // systemMedium
            VStack(alignment: .leading, spacing: 8) {
                header
                HStack(spacing: 8) {
                    ForEach(entry.quotes.prefix(4)) { QuoteCell(quote: $0) }
                }
                if !entry.movers.isEmpty, let top = entry.movers.first {
                    Divider()
                    HStack(spacing: 4) {
                        Text("Top mover")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(top.ticker).font(.caption.monospaced().weight(.semibold))
                        Text(fmtPct(top.pct))
                            .font(.caption.monospacedDigit().weight(.semibold))
                            .foregroundStyle(tone(top.pct))
                        Spacer()
                    }
                }
            }
        }
    }

    private var header: some View {
        HStack {
            Text("BSH Markets")
                .font(.caption.weight(.bold))
            if entry.stale {
                Image(systemName: "wifi.slash")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text(entry.date, style: .time)
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
    }
}

// MARK: - Widget declarations

struct MarketsWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "BSHMarketsWidget", provider: QuotesProvider()) { entry in
            MarketsWidgetView(entry: entry)
        }
        .configurationDisplayName("BSH Markets")
        .description("Indexes and top movers from your research desk.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct BSHWidgetsBundle: WidgetBundle {
    var body: some Widget {
        MarketsWidget()
    }
}
