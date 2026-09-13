import Foundation

struct ChartPoint: Decodable, Identifiable {
    var id: Int { t }
    let t: Int
    let close: Double?
    let open: Double?
    let high: Double?
    let low: Double?
    let volume: Double?
}

struct QuoteChartPayload: Decodable {
    let ticker: String?
    let name: String?
    let range: String?
    let interval: String?
    let lastPrice: Double?
    let change: Double?
    let changePct1d: Double?
    let previousClose: Double?
    let open: Double?
    let high: Double?
    let low: Double?
    let volume: Double?
    let avgVolume: Double?
    let marketCap: Double?
    let peRatio: Double?
    let eps: Double?
    let beta: Double?
    let dividendYield: Double?
    let fiftyTwoWeekHigh: Double?
    let fiftyTwoWeekLow: Double?
    let currency: String?
    let exchange: String?
    let asOf: String?
    let points: [ChartPoint]?

    enum CodingKeys: String, CodingKey {
        case ticker, name, range, interval, currency, exchange, points
        case lastPrice = "last_price"
        case change
        case changePct1d = "change_pct_1d"
        case previousClose = "previous_close"
        case open, high, low, volume
        case avgVolume = "avg_volume"
        case marketCap = "market_cap"
        case peRatio = "pe_ratio"
        case eps, beta
        case dividendYield = "dividend_yield"
        case fiftyTwoWeekHigh = "fifty_two_week_high"
        case fiftyTwoWeekLow = "fifty_two_week_low"
        case asOf = "as_of"
    }
}

struct QuoteWorkspace: Decodable {
    let ticker: String?
    let profile: WorkspaceProfile?
    let summary: WorkspaceSummary?
    let analysis: WorkspaceAnalysis?
    let holders: WorkspaceHolders?
    let options: WorkspaceOptions?
    let earnings: WorkspaceEarnings?
    // financials omitted — Nasdaq tables are nested dicts that vary by
    // symbol; decoding them strictly blanked the whole workspace payload.
}

struct WorkspaceProfile: Decodable {
    let ticker: String?
    let name: String?
    let sector: String?
    let industry: String?
    let region: String?
    let website: String?
    let description: String?
}

struct WorkspaceSummary: Decodable {
    let exchange: String?
    let sector: String?
    let industry: String?
    let oneYearTarget: String?
    let dayRange: String?
    let volume: String?
    let avgVolume: String?
    let previousClose: String?
    let fiftyTwoWeek: String?
    let marketCap: String?
    let dividend: String?
    let yield: String?
    let exDividend: String?
    let dividendPay: String?

    enum CodingKeys: String, CodingKey {
        case exchange, sector, industry, volume, dividend, yield
        case oneYearTarget = "one_year_target"
        case dayRange = "day_range"
        case avgVolume = "avg_volume"
        case previousClose = "previous_close"
        case fiftyTwoWeek = "fifty_two_week"
        case marketCap = "market_cap"
        case exDividend = "ex_dividend"
        case dividendPay = "dividend_pay"
    }
}


struct WorkspaceAnalysis: Decodable {
    let target: Double?
    let targetLow: Double?
    let targetHigh: Double?
    let buy: Int?
    let hold: Int?
    let sell: Int?

    enum CodingKeys: String, CodingKey {
        case target, buy, hold, sell
        case targetLow = "target_low"
        case targetHigh = "target_high"
    }
}

struct WorkspaceHolders: Decodable {
    let ownershipPct: FlexibleValue?
    let sharesOut: FlexibleValue?
    let holdingsValue: FlexibleValue?
    let holders: [WorkspaceHolder]?

    enum CodingKeys: String, CodingKey {
        case holders
        case ownershipPct = "ownership_pct"
        case sharesOut = "shares_out"
        case holdingsValue = "holdings_value"
    }
}

struct WorkspaceHolder: Decodable, Identifiable {
    var id: String { owner ?? name ?? UUID().uuidString }
    let owner: String?
    let name: String?
    let shares: FlexibleValue?
    let value: FlexibleValue?
    let pct: FlexibleValue?
    let changePct: FlexibleValue?

    enum CodingKeys: String, CodingKey {
        case owner, name, shares, value
        case pct
        case changePct = "change_pct"
    }

    var displayName: String { owner ?? name ?? "—" }
}

struct WorkspaceOptions: Decodable {
    let lastTrade: String?
    let rows: [OptionRow]?

    enum CodingKeys: String, CodingKey {
        case rows
        case lastTrade = "last_trade"
    }
}

struct OptionRow: Decodable, Identifiable {
    var id: String { "\(expiry ?? "")-\(strike ?? 0)" }
    let expiry: String?
    let strike: Double?
    let callLast: String?
    let putLast: String?
    let callVolume: String?
    let putVolume: String?

    enum CodingKeys: String, CodingKey {
        case expiry, strike
        case callLast = "call_last"
        case putLast = "put_last"
        case callVolume = "call_volume"
        case putVolume = "put_volume"
    }
}

struct WorkspaceEarnings: Decodable {
    let nextDate: String?
    let nextEstimated: FlexibleValue?
    let past: [EarningsPast]?

    enum CodingKeys: String, CodingKey {
        case past
        case nextDate = "next_date"
        case nextEstimated = "next_estimated"
    }
}

struct EarningsPast: Decodable, Identifiable {
    var id: String { reported ?? period ?? UUID().uuidString }
    let period: String?
    let reported: String?
    let eps: Double?
    let estimate: Double?
    let surprisePct: Double?

    enum CodingKeys: String, CodingKey {
        case period, reported, eps, estimate
        case surprisePct = "surprise_pct"
    }
}

/// Tolerant JSON value so financial statement cells (string or number) decode cleanly.
enum FlexibleValue: Decodable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let box = try decoder.singleValueContainer()
        if box.decodeNil() { self = .null; return }
        if let v = try? box.decode(Double.self) { self = .number(v); return }
        if let v = try? box.decode(Bool.self) { self = .bool(v); return }
        if let v = try? box.decode(String.self) { self = .string(v); return }
        self = .null
    }

    var display: String {
        switch self {
        case .string(let s): return s
        case .number(let n):
            if abs(n) >= 1_000_000_000 { return String(format: "%.2fB", n / 1_000_000_000) }
            if abs(n) >= 1_000_000 { return String(format: "%.2fM", n / 1_000_000) }
            return String(format: "%.2f", n)
        case .bool(let b): return b ? "true" : "false"
        case .null: return "—"
        }
    }
}

enum ChartRange: String, CaseIterable, Identifiable {
    case d1 = "1d", d5 = "5d", m1 = "1mo", m6 = "6mo", ytd = "ytd", y1 = "1y", y5 = "5y", max = "max"
    var id: String { rawValue }
    var label: String {
        switch self {
        case .d1: return "1D"
        case .d5: return "5D"
        case .m1: return "1M"
        case .m6: return "6M"
        case .ytd: return "YTD"
        case .y1: return "1Y"
        case .y5: return "5Y"
        case .max: return "MAX"
        }
    }
}
