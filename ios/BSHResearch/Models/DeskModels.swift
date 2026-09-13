import Foundation

// MARK: - Desk prefs (server copy of the web desk localStorage blob)

/// Whole-blob GET /desk/prefs response.
struct DeskPrefsResponse: Decodable {
    let updatedAt: String?
    let data: JSONBlob?

    enum CodingKeys: String, CodingKey {
        case data
        case updatedAt = "updated_at"
    }
}

/// Arbitrary JSON dictionary passthrough — the desk prefs blob is owned by
/// the frontend key shape, so we round-trip unknown keys untouched.
struct JSONBlob: Codable {
    let value: [String: AnyCodable]

    init(_ value: [String: AnyCodable]) { self.value = value }

    init(from decoder: Decoder) throws {
        value = try decoder.singleValueContainer().decode([String: AnyCodable].self)
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.singleValueContainer()
        try box.encode(value)
    }
}

/// Minimal Any-JSON Codable wrapper for the prefs blob round-trip.
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let box = try decoder.singleValueContainer()
        if box.decodeNil() { value = NSNull() }
        else if let b = try? box.decode(Bool.self) { value = b }
        else if let i = try? box.decode(Int.self) { value = i }
        else if let d = try? box.decode(Double.self) { value = d }
        else if let s = try? box.decode(String.self) { value = s }
        else if let arr = try? box.decode([AnyCodable].self) { value = arr.map(\.value) }
        else if let dict = try? box.decode([String: AnyCodable].self) {
            value = dict.mapValues(\.value)
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.singleValueContainer()
        switch value {
        case is NSNull: try box.encodeNil()
        case let b as Bool: try box.encode(b)
        case let i as Int: try box.encode(i)
        case let d as Double: try box.encode(d)
        case let s as String: try box.encode(s)
        case let arr as [Any]: try box.encode(arr.map { AnyCodable($0) })
        case let dict as [String: Any]: try box.encode(dict.mapValues { AnyCodable($0) })
        default: try box.encodeNil()
        }
    }
}

// MARK: - Alerts

struct AlertRule: Codable, Identifiable, Equatable {
    var id: String
    var ticker: String
    var kind: String          // "price" | "pct" (server engine evaluates these)
    var threshold: Double
    var window: Int?
    var direction: String     // "above" | "below"
    var enabled: Bool
}

struct AlertEvent: Decodable, Identifiable {
    let id: String
    let firedAt: String?
    let ruleId: String?
    let ticker: String?
    let kind: String?
    let message: String?
    let lastPrice: Double?
    let changePct1d: Double?

    enum CodingKeys: String, CodingKey {
        case id, ticker, kind, message
        case firedAt = "fired_at"
        case ruleId = "rule_id"
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
    }
}

struct AlertEventsResponse: Decodable {
    let events: [AlertEvent]
}

struct AlertCheckResponse: Decodable {
    let fired: [AlertEvent]?
    let checked: Int?
    let errors: [String]?
}

// MARK: - Positions (web `bsh.bookLots`)

struct BookLot: Codable, Identifiable, Equatable {
    var id: String
    var ticker: String
    var shares: Double
    var costBasis: Double
}

// MARK: - Desk digest / screener

struct DeskDigestItem: Decodable, Identifiable {
    let id: String
    let kind: String?
    let ticker: String?
    let title: String?
    let detail: String?
    let href: String?
}

struct DeskDigestResponse: Decodable {
    let generatedAt: String?
    let since: String?
    let items: [DeskDigestItem]?

    enum CodingKeys: String, CodingKey {
        case since, items
        case generatedAt = "generated_at"
    }
}

struct DeskScreenerItem: Decodable, Identifiable {
    let id: String
    let kind: String?
    let ticker: String?
    let companyId: String?
    let title: String?
    let detail: String?
    let href: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, ticker, title, detail, href
        case companyId = "company_id"
    }
}

struct DeskScreenerResponse: Decodable {
    let generatedAt: String?
    let items: [DeskScreenerItem]?

    enum CodingKeys: String, CodingKey {
        case items
        case generatedAt = "generated_at"
    }
}

struct MarketCalendarEvent: Decodable, Identifiable {
    var id: String { "\(ticker ?? "")-\(date ?? "")-\(kind ?? "")-\(label ?? "")" }
    let date: String?
    let ticker: String?
    let kind: String?
    let label: String?
    let title: String?
}

struct MarketCalendarResponse: Decodable {
    let events: [MarketCalendarEvent]?
}

// MARK: - Active jobs rail

struct ActiveJob: Decodable, Identifiable {
    var id: String { "\(kind ?? "job"):\(reportId ?? streamUrl ?? title ?? UUID().uuidString)" }
    let kind: String?
    let title: String?
    let subtitle: String?
    let streamUrl: String?
    let reportId: String?
    let companyId: String?
    let startedAt: String?
    let lastMessage: String?
    let stage: String?

    enum CodingKeys: String, CodingKey {
        case kind, title, subtitle, stage
        case streamUrl = "stream_url"
        case reportId = "report_id"
        case companyId = "company_id"
        case startedAt = "started_at"
        case lastMessage = "last_message"
    }
}

// MARK: - Quote offline cache

struct CachedQuote: Codable {
    let ticker: String
    let lastPrice: Double?
    let changePct1d: Double?
    let currency: String?
    let asOf: String?
    let name: String?

    init(from quote: Quote) {
        ticker = quote.ticker
        lastPrice = quote.lastPrice
        changePct1d = quote.changePct1d
        currency = quote.currency
        asOf = quote.asOf
        name = quote.name
    }

    var asQuote: Quote {
        Quote(
            ticker: ticker,
            lastPrice: lastPrice,
            changePct1d: changePct1d,
            currency: currency,
            asOf: asOf,
            name: name
        )
    }
}
