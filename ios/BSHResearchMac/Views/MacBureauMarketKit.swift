//
//  MacBureauMarketKit.swift
//  BSHResearchMac
//
//  What Bureau's Market page reads beyond the store, and the website's small market
//  controls (style.css "Market desk"): the full quote rows the website's desk reads
//  (GET /api/quotes), the index sparklines, the screener universe and the desk calendar;
//  the website's number formats; and `.yf-range-item`, `.icon-btn`, `.news-grouped`,
//  `.yf-search` and the plain inputs, drawn with the page's ink.
//

import AppKit
import SwiftUI
import UserNotifications

// MARK: - Data

/// One row of `GET /api/quotes` as the website's desk reads it (useLiveQuotes).
struct MacBureauMarketQuote: Decodable, Hashable {
    let ticker: String
    let lastPrice: Double?
    let changePct: Double?
    let currency: String?
    let asOf: String?
    let name: String?
    let exchange: String?
    let open: Double?
    let high: Double?
    let low: Double?
    let previousClose: Double?
    let volume: Double?
    let avgVolume: Double?
    let marketCap: Double?
    let peRatio: Double?
    let eps: Double?
    let beta: Double?
    let dividend: String?
    let dividendYield: Double?
    let weekHigh: Double?
    let weekLow: Double?

    private enum Key: String, CodingKey {
        case ticker, currency, name, exchange, open, high, low, volume, eps, beta, dividend
        case lastPrice = "last_price", changePct = "change_pct_1d", asOf = "as_of"
        case previousClose = "previous_close", avgVolume = "avg_volume", marketCap = "market_cap"
        case peRatio = "pe_ratio", dividendYield = "dividend_yield"
        case weekHigh = "fifty_two_week_high", weekLow = "fifty_two_week_low"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        func number(_ key: Key) -> Double? {
            if let value = try? c.decodeIfPresent(Double.self, forKey: key) { return value.isFinite ? value : nil }
            if let text = try? c.decodeIfPresent(String.self, forKey: key) { return MacFinNumber.parse(text) }
            return nil
        }
        func text(_ key: Key) -> String? {
            if let value = try? c.decodeIfPresent(String.self, forKey: key), !value.isEmpty { return value }
            if let value = try? c.decodeIfPresent(Double.self, forKey: key) { return String(value) }
            return nil
        }
        ticker = (text(.ticker) ?? "").uppercased()
        lastPrice = number(.lastPrice)
        changePct = number(.changePct)
        currency = text(.currency)
        asOf = text(.asOf)
        name = text(.name)
        exchange = text(.exchange)
        open = number(.open)
        high = number(.high)
        low = number(.low)
        previousClose = number(.previousClose)
        volume = number(.volume)
        avgVolume = number(.avgVolume)
        marketCap = number(.marketCap)
        peRatio = number(.peRatio)
        eps = number(.eps)
        beta = number(.beta)
        dividend = text(.dividend)
        dividendYield = number(.dividendYield)
        weekHigh = number(.weekHigh)
        weekLow = number(.weekLow)
    }
}

/// A row of the screener universe (`GET /api/quotes/screeners`).
struct MacBureauMarketScreenerRow: Decodable, Identifiable, Hashable {
    var id: String { ticker }
    let ticker: String
    let name: String?
    let last: Double?
    let changePct: Double?
    let volume: Double?
    let marketCap: Double?
    let sector: String?

    private enum Key: String, CodingKey {
        case ticker, name, last, volume, sector
        case changePct = "change_pct", marketCap = "market_cap"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        func number(_ key: Key) -> Double? {
            if let value = try? c.decodeIfPresent(Double.self, forKey: key) { return value.isFinite ? value : nil }
            return nil
        }
        ticker = ((try? c.decodeIfPresent(String.self, forKey: .ticker)) ?? "").uppercased()
        name = try? c.decodeIfPresent(String.self, forKey: .name)
        last = number(.last)
        changePct = number(.changePct)
        volume = number(.volume)
        marketCap = number(.marketCap)
        sector = try? c.decodeIfPresent(String.self, forKey: .sector)
    }
}

/// An item of the workspace feed (`GET /api/external/feed`): news and external research.
struct MacBureauMarketFeedItem: Decodable, Identifiable {
    let id: String
    let kind: String
    let title: String
    let summary: String?
    let ticker: String?
    let source: String?
    let url: String?
    let companyId: String?
    let stamp: String?

    private enum Key: String, CodingKey {
        case id, kind, title, name, summary, ticker, source, publisher, url, link
        case companyId = "company_id", capturedAt = "captured_at", publishedAt = "published_at", ts
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        func text(_ key: Key) -> String? {
            if let value = try? c.decodeIfPresent(String.self, forKey: key), !value.isEmpty { return value }
            if let value = try? c.decodeIfPresent(Int.self, forKey: key) { return String(value) }
            return nil
        }
        kind = text(.kind) ?? "news"
        title = text(.title) ?? text(.name) ?? ""
        id = text(.id) ?? text(.url) ?? title
        summary = text(.summary)
        ticker = text(.ticker)
        source = text(.source) ?? text(.publisher)
        url = text(.url) ?? text(.link)
        companyId = text(.companyId)
        stamp = text(.ts) ?? text(.publishedAt) ?? text(.capturedAt)
    }
}

/// The quotes, sparklines, screener universe, desk calendar and 2-up chart the website's
/// desk loads for itself. Every call is a GET; nothing here starts a run.
@MainActor
final class MacBureauMarketFeed: ObservableObject {
    @Published private(set) var peers: MacQuotePeers?
    @Published private(set) var external: [MacBureauMarketFeedItem] = []
    @Published private(set) var quotes: [String: MacBureauMarketQuote] = [:]
    @Published private(set) var sparks: [String: [Double]] = [:]
    @Published private(set) var universe: [MacBureauMarketScreenerRow] = []
    @Published private(set) var sectors: [String] = []
    @Published private(set) var calendar: [MacCalendarEvent] = []
    @Published private(set) var calendarLoading = false
    @Published private(set) var secondary: MacChartPayload?
    @Published private(set) var secondaryLoading = false

    private var quoteKey = ""
    private var peersKey: String?
    private var externalLoaded = false
    private var calendarKey = ""
    private var secondaryKey = ""
    private var screenersLoaded = false
    /// Sparkline charts are asked for once a session, as the website prefetches them once.
    private static var sparkCache: [String: [Double]] = [:]
    private static var sparkTried: Set<String> = []

    /// The peers table (`GET /api/quotes/{t}/peers`); a cold one takes the server a while,
    /// so a failure is retried and never pins the symbol as loaded.
    func loadPeers(_ ticker: String) async {
        let symbol = ticker.uppercased()
        if peersKey == symbol, peers != nil { return }
        peersKey = symbol
        if let primary = peers?.primary?.ticker, primary.uppercased() != symbol { peers = nil }
        for attempt in 0..<3 {
            if let loaded = try? await MacAPIClient.shared.fetchPeers(ticker: symbol) {
                guard peersKey == symbol else { return }
                peers = loaded
                return
            }
            guard !Task.isCancelled, peersKey == symbol else { break }
            try? await Task.sleep(for: .seconds(Double(attempt + 1) * 2))
        }
        if peersKey == symbol { peersKey = nil }
    }

    /// SPY first, then up to three peers, as the website layers them on the chart.
    var peerSeries: [MacCompareSeries] {
        guard let peers else { return [] }
        var rows: [MacCompareSeries] = []
        if let bench = peers.benchmark, !bench.points.isEmpty { rows.append(MacCompareSeries(ticker: bench.ticker, points: bench.points)) }
        rows += peers.peers.prefix(3).filter { !$0.points.isEmpty }.map { MacCompareSeries(ticker: $0.ticker, points: $0.points) }
        return rows
    }

    func loadExternal() async {
        guard !externalLoaded else { return }
        guard let rows: [MacBureauMarketFeedItem] = try? await Self.get("external/feed", query: []) else { return }
        externalLoaded = true
        external = rows.filter { !$0.title.isEmpty }
    }

    func quote(_ ticker: String?) -> MacBureauMarketQuote? {
        guard let ticker else { return nil }
        return quotes[ticker.uppercased()]
    }

    func loadQuotes(_ tickers: [String], force: Bool = false) async {
        var seen = Set<String>()
        let list = tickers.map { $0.uppercased() }.filter { !$0.isEmpty && seen.insert($0).inserted }
        let key = list.sorted().joined(separator: ",")
        guard !list.isEmpty, force || key != quoteKey else { return }
        quoteKey = key
        struct Payload: Decodable { let quotes: [String: MacBureauMarketQuote]? }
        var merged = quotes
        // The server takes the list in slices, as the website's live-quote hook asks.
        for start in stride(from: 0, to: list.count, by: 40) {
            let slice = Array(list[start..<min(start + 40, list.count)])
            guard let payload: Payload = try? await Self.get("quotes", query: slice.map { URLQueryItem(name: "ticker", value: $0) }) else { continue }
            for (ticker, row) in payload.quotes ?? [:] { merged[ticker.uppercased()] = row }
        }
        quotes = merged
    }

    func loadSparks(_ tickers: [String]) async {
        sparks = Self.sparkCache
        let missing = tickers.filter { !Self.sparkTried.contains($0) }
        guard !missing.isEmpty else { return }
        for ticker in missing { Self.sparkTried.insert(ticker) }
        await withTaskGroup(of: (String, [Double]).self) { group in
            for ticker in missing {
                group.addTask {
                    guard let payload = try? await MacAPIClient.shared.fetchChart(ticker: ticker, range: .m6) else { return (ticker, []) }
                    let closes = (payload.points ?? []).compactMap(\.close)
                    return (ticker, Array(closes.suffix(42)))
                }
            }
            for await (ticker, values) in group where values.count > 1 {
                Self.sparkCache[ticker] = values
            }
        }
        sparks = Self.sparkCache
    }

    func loadScreeners() async {
        guard !screenersLoaded else { return }
        struct Payload: Decodable {
            let universe: [MacBureauMarketScreenerRow]?
            let sectors: [String]?
        }
        guard let payload: Payload = try? await Self.get("quotes/screeners", query: []) else { return }
        screenersLoaded = true
        universe = payload.universe ?? []
        sectors = payload.sectors ?? []
    }

    func loadCalendar(_ tickers: [String]) async {
        let list = Array(tickers.prefix(24))
        let key = list.joined(separator: ",")
        guard key != calendarKey else { return }
        calendarKey = key
        calendarLoading = true
        defer { calendarLoading = false }
        guard let payload = try? await MacAPIClient.shared.fetchQuoteCalendar(tickers: list) else { return }
        calendar = payload.events
    }

    func loadSecondary(_ ticker: String?, range: MacChartRange) async {
        guard let ticker else {
            secondaryKey = ""
            secondary = nil
            return
        }
        let key = "\(ticker)|\(range.apiValue)"
        guard key != secondaryKey else { return }
        secondaryKey = key
        secondaryLoading = true
        defer { secondaryLoading = false }
        secondary = try? await MacAPIClient.shared.fetchChart(ticker: ticker, range: range)
    }

    /// A read-only GET on the configured server, as the API client sends it.
    private static func get<T: Decodable>(_ path: String, query: [URLQueryItem]) async throws -> T {
        guard let url = MacConfig.serverURL(path, query: query) else { throw MacAPIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw MacAPIError.http((response as? HTTPURLResponse)?.statusCode ?? -1, "")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

// MARK: - The website's number formats

enum MacBureauMarketFormat {
    /// The website's placeholders keep Tailwind's gray-400 on every desk and appearance.
    static let placeholder = Color.bshFixed(BSHRGB(156, 163, 175))

    private static let grouped: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 2
        f.minimumFractionDigits = 0
        f.locale = Locale(identifier: "en_US")
        return f
    }()

    /// `lastPriceLabel`: "$" and up to two decimals, grouped ("$767.37", "$391.4").
    static func price(_ value: Double?, currency: String? = "USD") -> String {
        guard let value, value.isFinite else { return "—" }
        let symbol: String = {
            guard let currency, !currency.isEmpty, currency != "USD" else { return "$" }
            return "\(currency) "
        }()
        return symbol + (grouped.string(from: NSNumber(value: value)) ?? String(value))
    }

    /// `number`: up to two decimals, grouped.
    static func number(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        return grouped.string(from: NSNumber(value: value)) ?? String(value)
    }

    /// `signedChange`: one decimal, "+" only above zero ("+2.8%", "-0.1%", "0.0%").
    static func signed(_ value: Double?) -> String? {
        guard let value, value.isFinite else { return nil }
        return (value > 0 ? "+" : "") + String(format: "%.1f", value) + "%"
    }

    /// `retLabel`: one decimal, "+" from zero up, "—" when missing.
    static func ret(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        return (value >= 0 ? "+" : "") + String(format: "%.1f", value) + "%"
    }

    /// `formatCompactNumber`: K / M / B / T with one decimal under 100.
    static func compact(_ value: Double?, currency: Bool = false) -> String {
        guard let value, value.isFinite else { return "—" }
        let magnitude = abs(value)
        let scale: (Double, String) = magnitude >= 1e12 ? (1e12, "T") : magnitude >= 1e9 ? (1e9, "B") : magnitude >= 1e6 ? (1e6, "M") : magnitude >= 1e3 ? (1e3, "K") : (1, "")
        let scaled = value / scale.0
        let decimals = scale.0 == 1 || abs(scaled) >= 100 ? 0 : 1
        let text = String(format: "%.\(decimals)f", abs(scaled))
        return (value < 0 ? "-" : "") + (currency ? "$" : "") + text + scale.1
    }

    /// `money(value, currency, true)`: compact from a thousand up.
    static func money(_ value: Double?, compact: Bool = false) -> String {
        guard let value, value.isFinite else { return "—" }
        if compact && abs(value) >= 1000 { return self.compact(value, currency: true) }
        return price(value)
    }

    /// `percent`: fractions read as percentages.
    static func percent(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        let pct = abs(value) <= 1 && value != 0 ? value * 100 : value
        return String(format: "%.2f%%", pct)
    }

    /// `radarAge`: "now", "15m ago", "6h ago", "2d ago".
    static func age(_ iso: String?, now: Date = Date()) -> String {
        guard let date = parse(iso) else { return "" }
        let seconds = max(0, Int(now.timeIntervalSince(date).rounded()))
        if seconds < 60 { return "now" }
        if seconds < 3600 { return "\(Int((Double(seconds) / 60).rounded()))m ago" }
        if seconds < 86400 { return "\(Int((Double(seconds) / 3600).rounded()))h ago" }
        return "\(Int((Double(seconds) / 86400).rounded()))d ago"
    }

    /// `asOfLabel`: "Sep 24, 12:12 PM".
    static func asOf(_ iso: String?) -> String? {
        guard let date = parse(iso) else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: date)
    }

    static func parse(_ iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        let full = ISO8601DateFormatter()
        full.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = full.date(from: iso) { return date }
        let plain = ISO8601DateFormatter()
        if let date = plain.date(from: iso) { return date }
        // Server stamps without a zone are UTC; bare dates are midnight UTC.
        let posix = DateFormatter()
        posix.locale = Locale(identifier: "en_US_POSIX")
        posix.timeZone = TimeZone(identifier: "UTC")
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd"] {
            posix.dateFormat = format
            if let date = posix.date(from: String(iso.prefix(format.count + 2).prefix(26))) { return date }
        }
        return nil
    }
}

// MARK: - The website's market controls, in the page's ink

/// A line of Instrument Sans measured as the browser lays it out: its exact advance width
/// (SwiftUI rounds a text's frame up to the pixel, and a row of pills drifts by the sum).
enum MacBureauMarketText {
    private static var cache: [String: CGFloat] = [:]
    private static var fonts: [String: Font] = [:]

    /// Bureau's sans at an exact size, with the website's fallback. `Font.custom(_:size:)`,
    /// which `BSHType.bureauSans` uses, rounds to a whole point, so the website's rem sizes
    /// (0.78rem is 12.48px) would come out 4% small; and what Instrument Sans lacks (arrows,
    /// Greek, ±, ≤, ≥) the browser takes from the system face, where Core Text alone would
    /// reach for Lucida Grande.
    static func font(_ size: CGFloat, weight: Font.Weight = .regular, tabular: Bool = false) -> Font {
        let key = "\(face(weight))|\(size)|\(tabular)"
        if let known = fonts[key] { return known }
        let font = Font(nsFont(face(weight), size: size, tabular: tabular))
        fonts[key] = font
        return font
    }

    static func face(_ weight: Font.Weight) -> String {
        switch weight {
        case .medium: return "InstrumentSans-Medium"
        case .semibold: return "InstrumentSans-SemiBold"
        case .bold, .heavy, .black: return "InstrumentSans-Bold"
        default: return "InstrumentSans-Regular"
        }
    }

    /// The face at `size`, cascading to the system face of the same weight; `tabular` sets
    /// the website's `tabular-nums`.
    static func nsFont(_ face: String, size: CGFloat, tabular: Bool = false) -> NSFont {
        let weight: NSFont.Weight
        switch face {
        case "InstrumentSans-Medium": weight = .medium
        case "InstrumentSans-SemiBold": weight = .semibold
        case "InstrumentSans-Bold": weight = .bold
        default: weight = .regular
        }
        var attributes: [NSFontDescriptor.AttributeName: Any] = [
            .cascadeList: [NSFont.systemFont(ofSize: size, weight: weight).fontDescriptor],
        ]
        if tabular {
            attributes[.featureSettings] = [[
                NSFontDescriptor.FeatureKey.typeIdentifier: kNumberSpacingType,
                NSFontDescriptor.FeatureKey.selectorIdentifier: kMonospacedNumbersSelector,
            ]]
        }
        let descriptor = NSFontDescriptor(name: face, size: size).addingAttributes(attributes)
        return NSFont(descriptor: descriptor, size: size) ?? NSFont.systemFont(ofSize: size, weight: weight)
    }

    static func width(_ text: String, size: CGFloat, weight: Font.Weight = .regular, tracking: CGFloat = 0, tabular: Bool = false) -> CGFloat {
        width(text, face: face(weight), size: size, tracking: tracking, tabular: tabular)
    }

    static func width(_ text: String, face: String, size: CGFloat, tracking: CGFloat = 0, tabular: Bool = false) -> CGFloat {
        let key = "\(face)|\(size)|\(tracking)|\(tabular)|\(text)"
        if let known = cache[key] { return known }
        let font = nsFont(face, size: size, tabular: tabular)
        // The face's own pair kerning stays; letter-spacing is added after every character.
        let width = NSAttributedString(string: text, attributes: [.font: font]).size().width + tracking * CGFloat(text.count)
        cache[key] = width
        return width
    }
}

/// A label in the website's `text-footnote font-semibold text-ink-muted` (12pt, line 16).
struct MacBureauMarketLabel: View {
    @Environment(\.colorScheme) private var colorScheme
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(BSHType.bureauSans(12, weight: .semibold))
            .foregroundStyle(MacBureauPageInk(scheme: colorScheme).muted)
            .lineLimit(1)
            .fixedSize()
            .frame(width: MacBureauMarketText.width(text, size: 12, weight: .semibold))
            .bureauLines(16, size: 12)
    }
}

/// `.yf-range-item`: a small pill of muted ink; chosen, a slip of fresh paper with a
/// hairline ring and a soft shadow, its label in ink.
struct MacBureauMarketRangeItem: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    let title: String
    var icon: String? = nil
    var selected = false
    var count: String? = nil
    let action: () -> Void
    @State private var hovered = false

    init(_ title: String, icon: String? = nil, selected: Bool = false, count: String? = nil, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.selected = selected
        self.count = count
        self.action = action
    }

    private var labelWidth: CGFloat {
        var width = MacBureauMarketText.width(title, size: 11, weight: .semibold, tracking: 0.066)
        if icon != nil { width += 14 + 4 }
        if let count { width += 4 + MacBureauMarketText.width(count, size: 11, weight: .medium) }
        return width
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 4) {
                if let icon { LucideIcon(icon, size: 14) }
                Text(title)
                    .font(MacBureauMarketText.font(11, weight: .semibold))
                    .tracking(0.066)
                    .lineLimit(1)
                    .fixedSize()
                if let count {
                    Text(count)
                        .font(BSHType.bureauSans(11, weight: .medium).monospacedDigit())
                        .foregroundStyle(ink.muted)
                        .fixedSize()
                }
            }
            .frame(width: labelWidth)
            .foregroundStyle(selected || (hovered && isEnabled) ? ink.ink : ink.muted)
            .padding(.horizontal, 10)
            .frame(height: 22)
            .background {
                if selected {
                    Capsule()
                        .fill(ink.raised)
                        .shadow(color: ink.dark ? .black.opacity(0.12) : ink.shadow(0.12), radius: 1.5, y: 1)
                        .overlay(Capsule().inset(by: -0.5).stroke(ink.ink(0.1), lineWidth: 1))
                } else if hovered && isEnabled {
                    Capsule().fill(ink.ink(0.05))
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// `.icon-btn`: a round button holding a muted glyph; hovered, a wash of ink behind it.
struct MacBureauMarketIconButton: View {
    @Environment(\.colorScheme) private var colorScheme
    let icon: String
    var size: CGFloat = 32
    var glyph: CGFloat = 18
    var tint: Color? = nil
    var pressed = false
    var help: String = ""
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            LucideIcon(icon, size: glyph)
                .foregroundStyle(tint ?? (hovered || pressed ? ink.ink : ink.muted))
                .frame(width: size, height: size)
                .background(Circle().fill(pressed ? ink.ink(0.08) : (hovered ? ink.ink(0.07) : .clear)))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(help)
    }
}

/// `.news-grouped`: a tray pressed into the sheet, with its faint inner edge and shade.
struct MacBureauMarketTray: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    var radius: CGFloat = 14

    func body(content: Content) -> some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        content
            .background(shape.fill(ink.tray))
            .overlay {
                // inset 0 1px 2px (by day) / 0 1px 3px (by night): shade under the top edge.
                ZStack {
                    shape.fill(ink.dark ? Color.black.opacity(0.35) : ink.shadow(0.04))
                    shape.fill(Color.black).offset(y: 1).blur(radius: ink.dark ? 1.5 : 1).blendMode(.destinationOut)
                }
                .compositingGroup()
                .clipShape(shape)
                .allowsHitTesting(false)
            }
            .overlay(shape.strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.ink(0.035), lineWidth: 1).allowsHitTesting(false))
    }
}

extension View {
    func bureauMarketTray(radius: CGFloat = 14) -> some View {
        modifier(MacBureauMarketTray(radius: radius))
    }
}

/// The website's bare inputs on the desk (an unstyled `<input>`): a square of the
/// field color, 11pt medium muted ink.
struct MacBureauMarketInput: View {
    @Environment(\.colorScheme) private var colorScheme
    let placeholder: String
    @Binding var text: String
    var width: CGFloat
    var height: CGFloat = 22
    var size: CGFloat = 11
    var uppercase = false
    var onSubmit: () -> Void = {}

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        // The placeholder is drawn here: a field's prompt ignores the letter-spacing.
        TextField("", text: $text)
            .textFieldStyle(.plain)
            .font(BSHType.bureauSans(size, weight: .medium))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .onSubmit(onSubmit)
            .onChange(of: text) { _, value in
                if uppercase, value != value.uppercased() { text = value.uppercased() }
            }
            .background(alignment: .leading) {
                if text.isEmpty {
                    Text(placeholder)
                        .font(BSHType.bureauSans(size, weight: .medium))
                        .tracking(0.066)
                        .foregroundStyle(MacBureauMarketFormat.placeholder)
                        .lineLimit(1)
                        .allowsHitTesting(false)
                }
            }
            .padding(.horizontal, 8)
            .frame(width: width, height: height)
            .background(Rectangle().fill(ink.dark ? Color.bshFixed(BSHRGB(59, 59, 59)) : Color.white))
    }
}

/// `.yf-search`: a round field of fresh paper ruled in ink, the glass at its left.
struct MacBureauMarketSearchField: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var text: String
    var focused: FocusState<Bool>.Binding
    let onSubmit: () -> Void

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let isFocused = focused.wrappedValue
        ZStack(alignment: .leading) {
            LucideIcon("search", size: 16)
                .foregroundStyle(ink.muted)
                .padding(.leading, 12)
            TextField("", text: $text)
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .focused(focused)
                .onSubmit(onSubmit)
                .onExitCommand { text = "" }
                .background(alignment: .leading) {
                    if text.isEmpty {
                        Text("Search quotes (AAPL, NVIDIA…)")
                            .font(BSHType.bureauSans(14))
                            .tracking(-0.084)
                            .foregroundStyle(MacBureauMarketFormat.placeholder)
                            .lineLimit(1)
                            .allowsHitTesting(false)
                    }
                }
                .padding(.leading, 36)
                .padding(.trailing, 16)
        }
        .frame(height: 36)
        .background(Capsule().fill(ink.raised))
        .overlay(Capsule().strokeBorder(isFocused ? ink.accent : ink.ink(0.14), lineWidth: 1))
        .overlay(
            Capsule()
                .inset(by: -1.5)
                .stroke(isFocused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                .allowsHitTesting(false)
        )
    }
}

/// `QuoteSparkline`: 72 × 22, a 1.5pt line in the day's direction.
struct MacBureauMarketSparkline: View {
    @Environment(\.colorScheme) private var colorScheme
    let values: [Double]
    var width: CGFloat = 72
    var height: CGFloat = 22

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let nums = values.filter(\.isFinite)
        if nums.count >= 2 {
            let up = (nums.last ?? 0) >= (nums.first ?? 0)
            Path { path in
                let lo = nums.min() ?? 0, hi = nums.max() ?? 1
                let span = hi - lo == 0 ? 1 : hi - lo
                let pad: CGFloat = 2
                let innerW = max(width - pad * 2, 1), innerH = max(height - pad * 2, 1)
                for (index, value) in nums.enumerated() {
                    let x = pad + CGFloat(index) / CGFloat(max(nums.count - 1, 1)) * innerW
                    let y = pad + (1 - CGFloat((value - lo) / span)) * innerH
                    if index == 0 { path.move(to: CGPoint(x: x, y: y)) } else { path.addLine(to: CGPoint(x: x, y: y)) }
                }
            }
            .stroke(up ? ink.success : ink.danger, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
            .frame(width: width, height: height)
        } else {
            Text("—")
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.subtle)
        }
    }
}

/// `.segmented` as Bureau draws it: a grooved track with a lifted slip of paper under the
/// chosen item, and a `.yf-tab-count` after the label when there is one. Each label takes its
/// exact width (a row of SwiftUI texts drifts as each rounds up to the pixel) and sits where
/// Blink puts it: a 16pt line inside 3pt of padding.
struct MacBureauMarketSegmented<Value: Hashable>: View {
    @Environment(\.colorScheme) private var colorScheme
    let options: [(value: Value, title: String, count: Int?)]
    @Binding var selection: Value
    @Namespace private var slip
    @State private var hovered: Value?

    init(options: [(value: Value, title: String, count: Int?)], selection: Binding<Value>) {
        self.options = options
        self._selection = selection
    }

    init(_ options: [(Value, String)], selection: Binding<Value>) {
        self.options = options.map { (value: $0.0, title: $0.1, count: nil) }
        self._selection = selection
    }

    /// The item's flex gap (4) plus the count's `margin-left: 0.3rem`.
    private static var countGap: CGFloat { 4 + 4.8 }

    private func labelWidth(_ title: String, count: Int?, chosen: Bool) -> CGFloat {
        var width = MacBureauMarketText.width(title, size: 12, weight: chosen ? .semibold : .medium)
        if let count { width += Self.countGap + MacBureauMarketText.width(String(count), size: 12, weight: .medium, tabular: true) }
        return width
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 2) {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                let chosen = option.value == selection
                Button {
                    guard !chosen else { return }
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.82)) { selection = option.value }
                } label: {
                    HStack(spacing: Self.countGap) {
                        Text(option.title)
                            .font(BSHType.bureauSans(12, weight: chosen ? .semibold : .medium))
                            .foregroundStyle(chosen || hovered == option.value ? ink.ink : ink.ink(0.62))
                        if let count = option.count {
                            Text(verbatim: String(count))
                                .font(BSHType.bureauSans(12, weight: .medium).monospacedDigit())
                                .foregroundStyle(ink.muted)
                        }
                    }
                    .lineLimit(1)
                    .fixedSize()
                    .frame(width: labelWidth(option.title, count: option.count, chosen: chosen), alignment: .leading)
                    .bureauLines(16, size: 12)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 3)
                    .background {
                        if chosen {
                            Capsule()
                                .fill(ink.raised)
                                .overlay(Capsule().inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
                                .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                                .matchedGeometryEffect(id: "slip", in: slip)
                        } else if hovered == option.value {
                            Capsule().fill(ink.ink(0.05))
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .onHover { inside in
                    if inside { hovered = option.value } else if hovered == option.value { hovered = nil }
                }
                .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
        .padding(3)
        .background(Capsule().fill(ink.ink(0.06)))
        .overlay(
            // inset 0 1px 2px: the groove's shade.
            ZStack {
                Capsule().fill(ink.shadow(0.06))
                Capsule().fill(Color.black).offset(y: 1).blur(radius: 1).blendMode(.destinationOut)
            }
            .compositingGroup()
            .clipShape(Capsule())
            .allowsHitTesting(false)
        )
        .fixedSize()
    }
}

/// Wraps whole items onto the next line when the row is full, with separate gaps across
/// and down (the website's `flex flex-wrap gap-x-* gap-y-*`). An item wider than the row
/// is offered the row's width (so a nested flow wraps inside it).
struct MacBureauMarketFlow: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8
    var alignment: VerticalAlignment = .center

    private struct Row {
        var items: [(index: Int, size: CGSize)] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = rows.map(\.width).max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width.map { min($0, width) } ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for item in row.items {
                let dy: CGFloat = alignment == .top ? 0 : (alignment == .bottom ? row.height - item.size.height : (row.height - item.size.height) / 2)
                subviews[item.index].place(at: CGPoint(x: x, y: y + dy), proposal: ProposedViewSize(item.size))
                x += item.size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = []
        var current = Row()
        for (index, subview) in subviews.enumerated() {
            var size = subview.sizeThatFits(.unspecified)
            if size.width > width, width.isFinite {
                size = subview.sizeThatFits(ProposedViewSize(width: width, height: nil))
            }
            let needed = current.items.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width + 0.5, !current.items.isEmpty {
                rows.append(current)
                current = Row(items: [(index, size)], width: size.width, height: size.height)
            } else {
                current.items.append((index, size))
                current.width = needed
                current.height = max(current.height, size.height)
            }
        }
        if !current.items.isEmpty { rows.append(current) }
        return rows
    }
}

/// `grid-template-columns: repeat(auto-fill, minmax(minimum, 1fr))`: as many columns as fit,
/// sharing the width; each row as tall as its tallest cell and every cell stretched to it.
struct MacBureauMarketAutoGrid: Layout {
    var minimum: CGFloat
    var spacing: CGFloat

    private func columns(_ width: CGFloat) -> (count: Int, width: CGFloat) {
        let count = max(1, Int(((width + spacing) / (minimum + spacing)).rounded(.down)))
        return (count, (width - spacing * CGFloat(count - 1)) / CGFloat(count))
    }

    private func rowHeights(_ subviews: Subviews, count: Int, column: CGFloat) -> [CGFloat] {
        stride(from: 0, to: subviews.count, by: count).map { start in
            subviews[start..<min(start + count, subviews.count)]
                .map { $0.sizeThatFits(ProposedViewSize(width: column, height: nil)).height }
                .max() ?? 0
        }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? (minimum * 4 + spacing * 3)
        let (count, column) = columns(width)
        let heights = rowHeights(subviews, count: count, column: column)
        return CGSize(width: width, height: heights.reduce(0, +) + spacing * CGFloat(max(0, heights.count - 1)))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (count, column) = columns(bounds.width)
        var y = bounds.minY
        for (row, height) in rowHeights(subviews, count: count, column: column).enumerated() {
            for index in (row * count)..<min((row + 1) * count, subviews.count) {
                let x = bounds.minX + CGFloat(index - row * count) * (column + spacing)
                subviews[index].place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(width: column, height: height))
            }
            y += height + spacing
        }
    }
}

/// The desk's two columns (`grid lg:grid-cols-12`, 8 and 4 of twelve, 24pt apart).
struct MacBureauMarketColumns: Layout {
    var gap: CGFloat = 24

    private func widths(_ total: CGFloat) -> (CGFloat, CGFloat) {
        let column = (total - gap * 11) / 12
        return (column * 8 + gap * 7, column * 4 + gap * 3)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width ?? 1138
        let (left, right) = widths(total)
        let heights = subviews.enumerated().map { index, view in
            view.sizeThatFits(ProposedViewSize(width: index == 0 ? left : right, height: nil)).height
        }
        return CGSize(width: total, height: heights.max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (left, right) = widths(bounds.width)
        for (index, view) in subviews.enumerated() {
            let x = index == 0 ? bounds.minX : bounds.minX + left + gap
            view.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(width: index == 0 ? left : right, height: nil))
        }
    }
}

// MARK: - Illustrative ETF weights (etfConstituents.js)

enum MacBureauMarketETFBook {
    struct Holding: Identifiable {
        var id: String { ticker }
        let ticker: String
        let weight: Double
    }

    struct Book {
        let name: String
        let asOf: String
        let holdings: [Holding]
    }

    static func book(_ ticker: String?) -> Book? {
        guard let ticker else { return nil }
        return books[ticker.uppercased()]
    }

    private static func rows(_ pairs: [(String, Double)]) -> [Holding] {
        pairs.map { Holding(ticker: $0.0, weight: $0.1) }
    }

    private static let books: [String: Book] = [
        "SPY": Book(name: "S&P 500", asOf: "2026-Q1 illustrative", holdings: rows([
            ("NVDA", 7.2), ("MSFT", 6.8), ("AAPL", 6.5), ("AMZN", 3.8), ("META", 2.9),
            ("GOOGL", 2.1), ("AVGO", 2.0), ("GOOG", 1.8), ("BRK.B", 1.7), ("TSLA", 1.6),
        ])),
        "QQQ": Book(name: "Nasdaq 100", asOf: "2026-Q1 illustrative", holdings: rows([
            ("NVDA", 9.5), ("MSFT", 8.4), ("AAPL", 8.1), ("AMZN", 5.6), ("META", 4.8),
            ("AVGO", 4.2), ("GOOGL", 2.9), ("GOOG", 2.8), ("TSLA", 2.7), ("COST", 2.4),
        ])),
        "DIA": Book(name: "Dow 30", asOf: "2026-Q1 illustrative", holdings: rows([
            ("GS", 9.2), ("MSFT", 7.1), ("CAT", 6.4), ("HD", 6.1), ("V", 5.5),
            ("SHW", 5.2), ("UNH", 4.8), ("AXP", 4.5), ("AMGN", 4.3), ("JPM", 4.1),
        ])),
        "IWM": Book(name: "Russell 2000", asOf: "2026-Q1 illustrative", holdings: rows([
            ("SMCI", 0.7), ("FTAI", 0.5), ("INSM", 0.4), ("SATS", 0.4), ("FIX", 0.4),
            ("FN", 0.3), ("CRS", 0.3), ("MLI", 0.3), ("AIT", 0.3), ("UFPI", 0.3),
        ])),
        "TLT": Book(name: "20+ Year Treasury", asOf: "2026-Q1 illustrative", holdings: rows([
            ("US912810", 4.2), ("US912810B", 3.9), ("US912810C", 3.7), ("US912810D", 3.5), ("US912810E", 3.4),
            ("US912810F", 3.2), ("US912810G", 3.1), ("US912810H", 3.0), ("US912810I", 2.9), ("US912810J", 2.8),
        ])),
    ]
}

// MARK: - Desktop alerts

enum MacBureauMarketDesktopAlerts {
    static func authorized() async -> Bool {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        return settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
    }

    static func request() async -> Bool {
        (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }
}
