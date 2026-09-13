import Foundation

struct WatchQuote: Identifiable, Codable, Hashable {
    var id: String { ticker }
    let ticker: String
    let last: Double?
    let pct: Double?
    let name: String?

    var priceText: String {
        guard let last else { return "—" }
        return String(format: "%.2f", last)
    }

    var pctText: String {
        guard let pct else { return "—" }
        return String(format: "%+.1f%%", pct)
    }

    var isUp: Bool { (pct ?? 0) >= 0 }

    var tapeText: String {
        "\(ticker) \(pctText)"
    }
}

struct WatchQuotesPayload: Codable {
    let quotes: [String: WatchQuoteDTO]?
}

struct WatchQuoteDTO: Codable {
    let lastPrice: Double?
    let changePct1d: Double?
    let name: String?

    enum CodingKeys: String, CodingKey {
        case name
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
    }
}

struct WatchScreenersPayload: Decodable {
    let gainers: [WatchScreenerRow]?
    let losers: [WatchScreenerRow]?
    let active: [WatchScreenerRow]?
}

struct WatchScreenerRow: Decodable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let name: String?
    let last: Double?
    let change: Double?

    enum CodingKeys: String, CodingKey {
        case ticker, name, last, change
        case lastPrice = "last_price"
        case changePct = "change_pct"
        case changePct1d = "change_pct_1d"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        ticker = try box.decode(String.self, forKey: .ticker)
        name = try box.decodeIfPresent(String.self, forKey: .name)
        last = try box.decodeIfPresent(Double.self, forKey: .last)
            ?? box.decodeIfPresent(Double.self, forKey: .lastPrice)
        change = try box.decodeIfPresent(Double.self, forKey: .changePct)
            ?? box.decodeIfPresent(Double.self, forKey: .changePct1d)
            ?? box.decodeIfPresent(Double.self, forKey: .change)
    }

    func asQuote() -> WatchQuote {
        WatchQuote(ticker: ticker.uppercased(), last: last, pct: change, name: name)
    }
}

struct WatchNewsItem: Identifiable, Codable, Hashable {
    var id: String { stableId }
    let stableId: String
    let title: String
    let source: String?
    let publishedAt: String?
    let ticker: String?
    let url: String?

    var timeText: String {
        guard let publishedAt, !publishedAt.isEmpty else { return "" }
        if let date = ISO8601DateFormatter().date(from: publishedAt)
            ?? ISO8601DateFormatter.fractional.date(from: publishedAt) {
            let mins = max(0, Int(Date().timeIntervalSince(date) / 60))
            if mins < 60 { return "\(mins)m" }
            let hours = mins / 60
            if hours < 36 { return "\(hours)h" }
            return "\(hours / 24)d"
        }
        return String(publishedAt.prefix(10))
    }
}

struct WatchNewsPayload: Decodable {
    let items: [WatchNewsDTO]?
}

struct WatchNewsDTO: Decodable {
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

    func asItem() -> WatchNewsItem? {
        guard let title, !title.isEmpty else { return nil }
        let stable = id ?? "\(ticker ?? "")|\(publishedAt ?? "")|\(title)"
        return WatchNewsItem(
            stableId: stable,
            title: title,
            source: source,
            publishedAt: publishedAt,
            ticker: ticker?.uppercased(),
            url: url
        )
    }
}

struct WatchPulseBrief: Codable {
    let date: String?
    let generatedAt: String?
    let indices: [WatchPulseQuote]?
    let movers: WatchPulseMovers?
    let note: WatchPulseNote?
    let alertsLastDay: [WatchPulseAlert]?

    enum CodingKeys: String, CodingKey {
        case date, indices, movers, note
        case generatedAt = "generated_at"
        case alertsLastDay = "alerts_last_day"
    }
}

struct WatchPulseQuote: Identifiable, Codable {
    var id: String { ticker }
    let ticker: String
    let lastPrice: Double?
    let changePct1d: Double?

    enum CodingKeys: String, CodingKey {
        case ticker
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
    }

    var asQuote: WatchQuote {
        WatchQuote(ticker: ticker.uppercased(), last: lastPrice, pct: changePct1d, name: nil)
    }
}

struct WatchPulseMovers: Codable {
    let gainers: [WatchPulseQuote]?
    let losers: [WatchPulseQuote]?
}

struct WatchPulseNote: Codable {
    let headlineEn: String?
    let bulletsEn: [String]?

    enum CodingKeys: String, CodingKey {
        case headlineEn = "headline_en"
        case bulletsEn = "bullets_en"
    }
}

struct WatchPulseAlert: Identifiable, Codable {
    let id: String
    let ticker: String?
    let message: String?
    let kind: String?
}

private extension ISO8601DateFormatter {
    static let fractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
