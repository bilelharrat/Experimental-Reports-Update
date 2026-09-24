//
//  MacBureauMarket.swift
//  BSHResearchMac
//
//  The Market desk under Bureau, laid out as the website's Market page (MarketsView.vue and
//  MarketRadarView.vue): the Market · Pulse · News tabs, the title with the quote search,
//  the saved desks, the watchlist alerts tray, the WEI strip of index cards, then the quote
//  workspace (header, ranges, compare, the chart, returns, note, calls, research, COMP, RRG,
//  statistics, the Nasdaq workspace, filings and actions), the desk calendar, breadth and
//  the market board, beside the Tape. The data is the Mac's: the store's chart, workspace,
//  news, pins, lots and alert rules, plus the quotes, screeners and calendar the website's
//  desk reads for itself (MacBureauMarketFeed).
//

import AppKit
import SwiftUI

// MARK: - What the page shows for the chosen symbol

/// The website's `selected` row: the chart payload first, then the live quote, then the
/// Mac's watchlist quote.
struct MacBureauMarketSelection {
    var ticker: String
    var label: String?
    var name: String?
    var company: MacCompany?
    var last: Double?
    var change: Double?
    var changeAbs: Double?
    var currency: String = "USD"
    var exchange: String?
    var previousClose: Double?
    var open: Double?
    var high: Double?
    var low: Double?
    var volume: Double?
    var avgVolume: Double?
    var marketCap: Double?
    var peRatio: Double?
    var eps: Double?
    var beta: Double?
    var dividendYield: Double?
    var dividend: String?
    var weekHigh: Double?
    var weekLow: Double?
    var asOf: String?

    @MainActor
    static func make(_ ticker: String, store: MacAppStore, feed: MacBureauMarketFeed) -> MacBureauMarketSelection {
        let symbol = ticker.uppercased()
        let chart = store.selectedChart.flatMap { ($0.ticker?.uppercased() ?? symbol) == symbol ? $0 : nil }
        let quote = feed.quote(symbol)
        let watch = (store.watchlist + store.indicesQuotes).first { $0.ticker.uppercased() == symbol }
        let company = store.companies.first { $0.ticker?.uppercased() == symbol }
        let def = MacBureauMarketDesk.indexDefs.first { $0.ticker == symbol }
        var row = MacBureauMarketSelection(ticker: symbol)
        row.label = def?.label
        row.company = company
        row.name = company?.name ?? chart?.name ?? quote?.name ?? watch?.name
        row.last = chart?.lastPrice ?? quote?.lastPrice ?? watch?.last
        row.change = chart?.changePct ?? quote?.changePct ?? watch?.pct
        row.changeAbs = chart?.change
        row.currency = chart?.currency ?? quote?.currency ?? "USD"
        row.exchange = chart?.exchange ?? quote?.exchange
        row.previousClose = chart?.previousClose ?? quote?.previousClose
        row.open = chart?.open ?? quote?.open
        row.high = chart?.high ?? quote?.high
        row.low = chart?.low ?? quote?.low
        row.volume = chart?.volume ?? quote?.volume
        row.avgVolume = chart?.avgVolume ?? quote?.avgVolume
        row.marketCap = chart?.marketCap ?? quote?.marketCap
        row.peRatio = chart?.peRatio ?? quote?.peRatio
        row.eps = chart?.eps ?? quote?.eps
        row.beta = chart?.beta ?? quote?.beta
        row.dividendYield = chart?.dividendYield ?? quote?.dividendYield
        row.dividend = quote?.dividend
        row.weekHigh = chart?.fiftyTwoWeekHigh ?? quote?.weekHigh
        row.weekLow = chart?.fiftyTwoWeekLow ?? quote?.weekLow
        row.asOf = chart?.asOf ?? quote?.asOf
        return row
    }
}

/// A row of the market board (MarketRadarView `quoteBoardRows`).
struct MacBureauMarketBoardRow: Identifiable, Hashable {
    var id: String { ticker }
    let ticker: String
    let name: String
    let last: Double?
    let change: Double?
    let volume: Double?
    let weekHigh: Double?
    let weekLow: Double?
    let currency: String
    var sector: String? = nil
    var marketCap: Double? = nil
}

/// Scroll position and the column geometry for the Tape, which stays in view as the
/// website's `lg:sticky lg:top-4` aside does. Only the aside observes it.
@MainActor
final class MacBureauMarketScroll: ObservableObject {
    @Published var offset: CGFloat = 0
    @Published var gridTop: CGFloat = 0
    @Published var gridHeight: CGFloat = 0
    @Published var asideHeight: CGFloat = 0

    /// The website pins the aside 16px under the top of the window, which is 36pt above
    /// the top of the sheet here (the masthead is 52pt tall).
    func stickyOffset(pin: CGFloat = 16 - 52) -> CGFloat {
        let limit = max(0, gridHeight - asideHeight)
        return min(max(0, offset + pin - gridTop), limit)
    }
}

private struct MacBureauMarketOffsetKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// Follows the page's scroll position: the scroll view's own geometry where the system
/// reports it, else the content's frame in the scroll view.
private struct MacBureauMarketScrollTracking: ViewModifier {
    let scroll: MacBureauMarketScroll

    func body(content: Content) -> some View {
        if #available(macOS 15.0, *) {
            content.onScrollGeometryChange(for: CGFloat.self) { geometry in
                geometry.contentOffset.y + geometry.contentInsets.top
            } action: { _, offset in
                if abs(scroll.offset - offset) > 0.25 { scroll.offset = offset }
            }
        } else {
            content.onPreferenceChange(MacBureauMarketOffsetKey.self) { value in
                let offset = -value
                if abs(scroll.offset - offset) > 0.25 { scroll.offset = offset }
            }
        }
    }
}

// MARK: - The page

struct MacBureauMarketDesk: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @StateObject private var detail = MacQuoteDetailModel()
    @StateObject private var feed = MacBureauMarketFeed()
    @State private var scroll = MacBureauMarketScroll()
    @AppStorage("mac.chart.compareTickers") private var compareTickersRaw = ""
    @AppStorage("mac.chart.expanded") private var deskExpanded = false
    @AppStorage("mac.market.bureau.recents") private var recentsRaw = ""
    @State private var sessionTickers: [String] = []
    @State private var twoUp = false
    @State private var secondaryTicker: String?

    /// MARKET_INDEX_TICKERS, in the website's order.
    static let indexDefs: [(ticker: String, label: String)] = [
        ("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow 30"), ("IWM", "Russell 2000"),
        ("EFA", "Developed"), ("EEM", "Emerging"), ("GLD", "Gold"), ("USO", "Oil"),
        ("TLT", "Bonds"), ("VIXY", "VIX"), ("UUP", "USD"), ("HYG", "HY credit"),
    ]
    /// WEI_TICKERS: the strip shows these, in the order above.
    static let weiTickers: Set<String> = ["SPY", "QQQ", "TLT", "UUP", "USO", "VIXY", "HYG", "GLD"]
    static var weiDefs: [(ticker: String, label: String)] { indexDefs.filter { weiTickers.contains($0.ticker) } }
    static let indexTickers: Set<String> = Set(indexDefs.map(\.ticker))

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var compareTickers: Binding<[String]> {
        Binding(
            get: { compareTickersRaw.split(separator: ",").map(String.init).filter { !$0.isEmpty } },
            set: { compareTickersRaw = $0.joined(separator: ",") }
        )
    }

    private var recents: [String] {
        recentsRaw.split(separator: ",").map(String.init).filter { !$0.isEmpty }
    }

    private var ticker: String { store.selectedTicker ?? "SPY" }

    private var followedCompanies: [MacCompany] {
        let ids = Set(store.validFollowedIds)
        return store.companies.filter { ids.contains($0.id) }
    }

    /// The pinned tickers and the followed companies' tickers (the website's watchlist).
    private var watchTickers: [String] {
        var seen = Set<String>()
        let followed = followedCompanies.compactMap { $0.ticker?.uppercased() }
        return (followed + store.pinnedTickers.map { $0.uppercased() }).filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    private var deskBTicker: String? {
        if let secondaryTicker { return secondaryTicker }
        return compareTickers.wrappedValue.first { $0 != ticker }
    }

    /// Everything the page quotes: the strip, the chosen symbol, the watchlist, compare
    /// tickers and the book's listed companies.
    private var quoteTickers: [String] {
        let companies = store.companies.compactMap { $0.ticker?.uppercased() }
        return Self.weiDefs.map(\.ticker) + [ticker] + watchTickers + compareTickers.wrappedValue + sessionTickers + companies
    }

    private var boardTickers: [String] {
        var seen = Set<String>()
        let companies = store.companies.compactMap { $0.ticker?.uppercased() }
        return (sessionTickers + store.pinnedTickers + compareTickers.wrappedValue + followedCompanies.compactMap(\.ticker) + [ticker] + companies)
            .map { $0.uppercased() }
            .filter { !$0.isEmpty && !Self.indexTickers.contains($0) && seen.insert($0).inserted }
    }

    private func boardRow(_ symbol: String) -> MacBureauMarketBoardRow? {
        let quote = feed.quote(symbol)
        let watch = store.watchlist.first { $0.ticker.uppercased() == symbol }
        guard let last = quote?.lastPrice ?? watch?.last else { return nil }
        let company = store.companies.first { $0.ticker?.uppercased() == symbol }
        return MacBureauMarketBoardRow(
            ticker: symbol,
            name: company?.name ?? quote?.name ?? watch?.name ?? symbol,
            last: last,
            change: quote?.changePct ?? watch?.pct,
            volume: quote?.volume,
            weekHigh: quote?.weekHigh,
            weekLow: quote?.weekLow,
            currency: quote?.currency ?? "USD"
        )
    }

    private var boardRows: [MacBureauMarketBoardRow] { boardTickers.compactMap(boardRow) }

    private var watchRows: [MacBureauMarketBoardRow] {
        watchTickers.map { symbol in
            boardRow(symbol) ?? MacBureauMarketBoardRow(ticker: symbol, name: store.companies.first { $0.ticker?.uppercased() == symbol }?.name ?? symbol, last: nil, change: nil, volume: nil, weekHigh: nil, weekLow: nil, currency: "USD")
        }
        .sorted { $0.ticker < $1.ticker }
    }

    // MARK: Actions

    /// Chooses a symbol, as the website's `selectTicker` does: remembered among the recent
    /// tickers and kept on the board for the session.
    func select(_ symbol: String) {
        let t = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !t.isEmpty else { return }
        store.selectTicker(t)
        var list = recents.filter { $0 != t }
        list.insert(t, at: 0)
        recentsRaw = list.prefix(8).joined(separator: ",")
        if !sessionTickers.contains(t) { sessionTickers = Array((sessionTickers + [t]).suffix(12)) }
    }

    // MARK: Body

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                MacTabBar(items: [(MacTab.market, "Market"), (MacTab.pulse, "Pulse"), (MacTab.news, "News")], selection: $store.selectedTab, plain: true)
                    .padding(.horizontal, 24)
                    // The website's sheet lays its content half a point lower on a Retina screen.
                    .padding(.top, 8.5)

                VStack(alignment: .leading, spacing: 0) {
                    MacBureauMarketHeader(select: select, recents: recents)
                        .padding(.bottom, 20)
                        .zIndex(2)

                    MacBureauMarketAlerts(feed: feed, watchRows: watchRows, select: select)
                        .padding(.bottom, 16)

                    MacBureauMarketWEI(feed: feed, selected: ticker, select: select)
                        .padding(.bottom, 20)

                    columns
                }
                .padding(.horizontal, 32)
                .padding(.top, 16)
                .padding(.bottom, 48)
            }
            .coordinateSpace(name: "bureauMarketContent")
            .background(
                GeometryReader { geo in
                    Color.clear.preference(key: MacBureauMarketOffsetKey.self, value: geo.frame(in: .named("bureauMarketScroll")).minY)
                }
            )
        }
        .coordinateSpace(name: "bureauMarketScroll")
        .modifier(MacBureauMarketScrollTracking(scroll: scroll))
        .background(ink.sheet)
        .task(id: ticker) {
            await feed.loadPeers(ticker)
        }
        .task {
            await feed.loadExternal()
        }
        .task(id: "\(compareTickersRaw)|\(store.selectedChartRange.apiValue)") {
            await detail.loadCompare(tickers: compareTickers.wrappedValue, range: store.selectedChartRange)
        }
        .task(id: quoteTickers.joined(separator: ",")) {
            await feed.loadQuotes(quoteTickers)
        }
        .task {
            await feed.loadScreeners()
        }
        .task {
            await feed.loadSparks(Self.weiDefs.map(\.ticker))
        }
        .task {
            // The website's live quotes refresh while the desk is open.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                guard !Task.isCancelled else { return }
                await feed.loadQuotes(quoteTickers, force: true)
            }
        }
        .task(id: (watchTickers.isEmpty ? [ticker] : ([ticker] + watchTickers)).joined(separator: ",")) {
            var tickers = watchTickers
            if !tickers.contains(ticker) { tickers.insert(ticker, at: 0) }
            await feed.loadCalendar(tickers)
        }
        .task(id: twoUp ? "\(deskBTicker ?? "")|\(store.selectedChartRange.apiValue)" : "off") {
            await feed.loadSecondary(twoUp ? deskBTicker.flatMap { $0 == ticker ? nil : $0 } : nil, range: store.selectedChartRange)
        }
    }

    // MARK: Columns

    @ViewBuilder
    private var columns: some View {
        if deskExpanded {
            VStack(alignment: .leading, spacing: 24) {
                leftColumn
                MacBureauMarketAside(feed: feed, expanded: true, select: select)
            }
        } else {
            MacBureauMarketColumns(gap: 24) {
                leftColumn
                MacBureauMarketStickyAside(scroll: scroll) {
                    MacBureauMarketAside(feed: feed, expanded: false, select: select)
                }
            }
            .background(
                GeometryReader { geo in
                    Color.clear
                        .onAppear { scroll.gridTop = geo.frame(in: .named("bureauMarketContent")).minY; scroll.gridHeight = geo.size.height }
                        .onChange(of: geo.frame(in: .named("bureauMarketContent"))) { _, frame in
                            scroll.gridTop = frame.minY
                            scroll.gridHeight = frame.height
                        }
                }
            )
        }
    }

    private var leftColumn: some View {
        VStack(alignment: .leading, spacing: 20) {
            MacBureauMarketArticle(
                feed: feed,
                detail: detail,
                ticker: ticker,
                compareTickers: compareTickers,
                twoUp: $twoUp,
                secondaryTicker: $secondaryTicker,
                deskBTicker: deskBTicker,
                select: select
            )
            MacBureauMarketCalendar(feed: feed, select: select)
            MacBureauMarketBreadth(rows: watchRows)
            MacBureauMarketBoard(feed: feed, boardRows: boardRows, watchRows: watchRows, selected: ticker, select: select)
                .padding(.top, 0)
        }
    }
}

/// Holds the Tape in view while the page scrolls, as the website's sticky aside does.
private struct MacBureauMarketStickyAside<Content: View>: View {
    @ObservedObject var scroll: MacBureauMarketScroll
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .background(
                GeometryReader { geo in
                    Color.clear
                        .onAppear { scroll.asideHeight = geo.size.height }
                        .onChange(of: geo.size.height) { _, height in scroll.asideHeight = height }
                }
            )
            .offset(y: scroll.stickyOffset())
    }
}

// MARK: - Header: title, search, desks

private struct MacBureauMarketHeader: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let select: (String) -> Void
    let recents: [String]

    @State private var query = ""
    @FocusState private var focused: Bool
    @State private var remote: [MacSymbolMatch] = []
    @State private var showDeskSave = false
    @State private var deskName = ""
    @AppStorage("mac.market.bureau.desks") private var desksRaw = ""
    @AppStorage("mac.chart.compareTickers") private var compareTickersRaw = ""

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    /// A saved desk: the symbol, its range and the compare list (the website's `saveDesk`).
    struct Desk: Codable, Identifiable, Hashable {
        let id: String
        let name: String
        let ticker: String
        let range: String
        let compare: [String]
    }

    private var desks: [Desk] {
        (try? JSONDecoder().decode([Desk].self, from: Data(desksRaw.utf8))) ?? []
    }

    private func save(_ desks: [Desk]) {
        if let data = try? JSONEncoder().encode(desks) { desksRaw = String(decoding: data, as: UTF8.self) }
    }

    /// lookupQuoteMatches + the server's symbol search, eight at most.
    private var suggestions: [(ticker: String, name: String)] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return [] }
        var rows: [(ticker: String, name: String)] = []
        var seen = Set<String>()
        for company in store.companies {
            guard let t = company.ticker?.uppercased(), !t.isEmpty else { continue }
            let name = company.name ?? t
            if t.lowercased().hasPrefix(q) || name.lowercased().contains(q), seen.insert(t).inserted {
                rows.append((t, name))
            }
        }
        for match in remote where seen.insert(match.symbol.uppercased()).inserted {
            rows.append((match.symbol.uppercased(), match.name ?? match.symbol))
            if rows.count >= 8 { break }
        }
        return Array(rows.prefix(8))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            MacBureauPageHeader("Market", subtitle: "Live quotes, charts, and headlines — search any company.") {
                MacBureauMarketSearchField(text: $query, focused: $focused, onSubmit: submit)
                    .frame(width: 384)
                    .overlay(alignment: .topLeading) {
                        if focused && !suggestions.isEmpty {
                            suggestionMenu
                                .offset(y: 42)
                        }
                    }
                MacBureauMarketIconButton(icon: "keyboard", help: "Press ? for keys") {
                    store.showShortcutSheet = true
                }
            }
            desksRow
        }
        .task(id: query) {
            let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
            guard q.count >= 1 else { remote = []; return }
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled else { return }
            remote = (try? await MacAPIClient.shared.searchSymbols(query: q)) ?? []
        }
    }

    private var suggestionMenu: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(suggestions, id: \.ticker) { row in
                MacBureauMarketSuggestionLine(ticker: row.ticker, name: row.name, ink: ink) {
                    pick(row.ticker)
                }
            }
        }
        .padding(5)
        .frame(width: 384, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 13, style: .circular).fill(ink.raised))
        .overlay(RoundedRectangle(cornerRadius: 13, style: .circular).inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
        .shadow(color: .black.opacity(ink.dark ? 0.5 : 0.16), radius: 14, y: 10)
    }

    private func pick(_ symbol: String) {
        query = symbol
        focused = false
        select(symbol)
    }

    private func submit() {
        if let first = suggestions.first {
            pick(first.ticker)
        } else {
            let t = query.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            if !t.isEmpty { pick(t) }
        }
    }

    private var desksRow: some View {
        MacBureauMarketFlow(spacing: 8, lineSpacing: 8) {
            MacBureauMarketLabel("Desks")
            ForEach(desks) { desk in
                MacBureauMarketRangeItem(desk.name) { apply(desk) }
                    .simultaneousGesture(TapGesture(count: 2).onEnded { save(desks.filter { $0.id != desk.id }) })
                    .help("Double-click to delete")
            }
            MacBureauMarketRangeItem("Save desk", selected: showDeskSave) { showDeskSave.toggle() }
            if showDeskSave {
                HStack(spacing: 4) {
                    MacBureauMarketInput(placeholder: "Name this layout", text: $deskName, width: 144, height: 22, onSubmit: persistDesk)
                    MacBureauMarketRangeItem("Save", action: persistDesk)
                }
            }
            if !recents.isEmpty {
                MacBureauMarketLabel("Recent")
                ForEach(recents, id: \.self) { symbol in
                    MacBureauMarketRangeItem(symbol) { select(symbol) }
                }
            }
        }
    }

    private func persistDesk() {
        let name = deskName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        let desk = Desk(
            id: UUID().uuidString,
            name: name,
            ticker: store.selectedTicker ?? "SPY",
            range: store.selectedChartRange.rawValue,
            compare: compareTickersRaw.split(separator: ",").map(String.init)
        )
        save(desks.filter { $0.name != name } + [desk])
        deskName = ""
        showDeskSave = false
    }

    private func apply(_ desk: Desk) {
        select(desk.ticker)
        compareTickersRaw = desk.compare.joined(separator: ",")
        if let range = MacChartRange(rawValue: desk.range), range != store.selectedChartRange {
            Task { await store.loadChart(range: range) }
        }
    }
}

/// A line of the search menu: the ticker, then the name in muted ink.
private struct MacBureauMarketSuggestionLine: View {
    let ticker: String
    let name: String
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Text(ticker)
                    .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                    .tracking(-0.15)
                    .foregroundStyle(ink.ink)
                Spacer(minLength: 8)
                Text(name)
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(hovered ? ink.accent.opacity(0.1) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Watchlist alerts

private struct MacBureauMarketAlerts: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let watchRows: [MacBureauMarketBoardRow]
    let select: (String) -> Void

    @State private var showRules = false
    @State private var priceLevel = ""
    @State private var above = true
    @State private var desktopAlertsOn = true
    @State private var saving = false
    @AppStorage("mac.market.bureau.alertsSeenAt") private var seenAt: Double = 0
    @AppStorage("mac.market.bureau.alertMutes") private var mutesRaw = ""

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    struct Alert: Identifiable, Hashable {
        var id: String { "\(ticker)-\(kind)" }
        let ticker: String
        let kind: String
        let label: String
    }

    private var mutes: [String: Double] {
        var out: [String: Double] = [:]
        for part in mutesRaw.split(separator: ";") {
            let pieces = part.split(separator: "=")
            if pieces.count == 2, let until = Double(pieces[1]) { out[String(pieces[0])] = until }
        }
        return out
    }

    private func mute(_ alert: Alert, minutes: Double) {
        var all = mutes.filter { $0.value > Date().timeIntervalSince1970 }
        all[alert.id] = Date().timeIntervalSince1970 + minutes * 60
        mutesRaw = all.map { "\($0.key)=\($0.value)" }.joined(separator: ";")
    }

    /// watchlistAlerts (a ±5% day, a print at the edge of the 52-week range) and the price
    /// rules the desk has armed.
    private var alerts: [Alert] {
        var out: [Alert] = []
        for row in watchRows {
            if let change = row.change, abs(change) >= 5 {
                out.append(Alert(ticker: row.ticker, kind: change >= 0 ? "gap_up" : "gap_down", label: change >= 0 ? "\(row.ticker) +\(String(format: "%.1f", change))%" : "\(row.ticker) -\(String(format: "%.1f", abs(change)))%"))
            }
            if let last = row.last, let high = row.weekHigh, let low = row.weekLow, high > low {
                let pct = (last - low) / (high - low) * 100
                if pct >= 97 { out.append(Alert(ticker: row.ticker, kind: "near_high", label: "\(row.ticker) near 52w high")) }
                if pct <= 3 { out.append(Alert(ticker: row.ticker, kind: "near_low", label: "\(row.ticker) near 52w low")) }
            }
        }
        for rule in store.alertRules where rule.enabled && rule.kind == "price" {
            let symbol = rule.ticker.uppercased()
            guard let last = feed.quote(symbol)?.lastPrice ?? store.watchlist.first(where: { $0.ticker == symbol })?.last else { continue }
            let hit = rule.direction == "below" ? last <= rule.threshold : last >= rule.threshold
            if hit {
                let level = MacBureauMarketFormat.number(rule.threshold)
                out.append(Alert(ticker: symbol, kind: "rule-\(rule.id)", label: rule.direction == "below" ? "\(symbol) ≤ \(level)" : "\(symbol) ≥ \(level)"))
            }
        }
        let now = Date().timeIntervalSince1970
        let muted = mutes
        return Array(out.filter { (muted[$0.id] ?? 0) <= now }.prefix(8))
    }

    private var firedWhileAway: [MacAlertEvent] {
        store.alertEvents.filter { event in
            guard let stamp = MacBureauMarketFormat.parse(event.firedAt) else { return false }
            return stamp.timeIntervalSince1970 > seenAt
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauMarketLabel("Watchlist alerts")
                Spacer(minLength: 0)
                HStack(spacing: 4) {
                    MacBureauMarketRangeItem("Rules", selected: showRules) { showRules.toggle() }
                    if !desktopAlertsOn {
                        MacBureauMarketRangeItem("Desktop alerts") {
                            Task { desktopAlertsOn = await MacBureauMarketDesktopAlerts.request() }
                        }
                    }
                }
            }
            .frame(height: 22)

            if alerts.isEmpty {
                Text("No live alerts — open Rules to arm price or SMA crosses.")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(14, size: 11)
                    .padding(.top, 8)
            } else {
                MacBureauMarketFlow(spacing: 8, lineSpacing: 8) {
                    ForEach(alerts) { alert in
                        HStack(spacing: 4) {
                            MacBureauMarketRangeItem(alert.label) { select(alert.ticker) }
                            smallLink("1h") { mute(alert, minutes: 60) }
                            smallLink("Mute") { mute(alert, minutes: 60 * 24) }
                        }
                    }
                }
                .padding(.top, 8)
            }

            if !firedWhileAway.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        MacBureauMarketLabel("Fired while away (\(firedWhileAway.count))")
                        Spacer()
                        MacBureauMarketRangeItem("Mark seen") { seenAt = Date().timeIntervalSince1970 }
                    }
                    ForEach(firedWhileAway.prefix(8)) { event in
                        HStack(spacing: 4) {
                            Button(event.message ?? "\(event.ticker ?? "") \(event.kind ?? "")") {
                                if let t = event.ticker { select(t) }
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(ink.secondary)
                            Text(MacBureauMarketFormat.asOf(event.firedAt) ?? "")
                                .foregroundStyle(ink.subtle)
                        }
                        .font(BSHType.bureauSans(11))
                    }
                }
                .padding(.top, 8)
                .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
                .padding(.top, 12)
            }

            if showRules {
                rulesForm
                    .padding(.top, 12)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
        .task { desktopAlertsOn = await MacBureauMarketDesktopAlerts.authorized() }
    }

    private func smallLink(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .padding(.horizontal, 4)
        }
        .buttonStyle(.plain)
    }

    /// Rules: a price alert on the chosen symbol (the Mac saves it with the desk), and the
    /// rules already armed for it.
    private var rulesForm: some View {
        let symbol = store.selectedTicker ?? "SPY"
        let rules = store.alertRules.filter { $0.ticker.uppercased() == symbol }
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                MacBureauMarketInput(placeholder: "Price", text: $priceLevel, width: 96, height: 22, onSubmit: addPriceAlert)
                MacBureauMarketRangeItem(above ? "≥" : "≤") { above.toggle() }
                    .help("Rises above or drops below")
                MacBureauMarketRangeItem("Price alert", action: addPriceAlert)
                    .disabled(saving || !store.canWriteDesk)
            }
            ForEach(rules) { rule in
                HStack(spacing: 8) {
                    MacBureauSwitch(isOn: Binding(
                        get: { rule.enabled },
                        set: { _ in Task { await store.toggleAlertRule(id: rule.id) } }
                    ), disabled: !store.canWriteDesk)
                    .scaleEffect(0.8)
                    Text(ruleLabel(rule))
                        .font(MacBureauMarketText.font(12, tabular: true))
                        .foregroundStyle(ink.secondary)
                    Spacer(minLength: 0)
                    Button {
                        Task { await store.deleteAlertRule(id: rule.id) }
                    } label: {
                        LucideIcon("x", size: 14).foregroundStyle(ink.muted)
                    }
                    .buttonStyle(.plain)
                    .disabled(!store.canWriteDesk)
                    .help("Delete this rule")
                }
            }
        }
    }

    private func ruleLabel(_ rule: MacAlertRule) -> String {
        let level = MacBureauMarketFormat.number(rule.threshold)
        switch rule.kind {
        case "price": return rule.direction == "below" ? "\(rule.ticker) ≤ \(level)" : "\(rule.ticker) ≥ \(level)"
        case "pct": return "\(rule.ticker) moves ±\(level)% in a day"
        case "volume": return "\(rule.ticker) volume ≥\(level)× avg"
        case "earnings": return "\(rule.ticker) earnings in \(Int(rule.threshold))d"
        case "sma_cross": return "\(rule.ticker) crosses \(rule.direction == "below" ? "below" : "above") SMA \(Int(rule.threshold))"
        default: return "\(rule.ticker) \(rule.kind) \(level)"
        }
    }

    private func addPriceAlert() {
        guard let level = MacSheetNumber.parse(priceLevel), level > 0, !saving else { return }
        let symbol = store.selectedTicker ?? "SPY"
        saving = true
        Task {
            if await store.addAlertRule(ticker: symbol, threshold: level, direction: above ? "above" : "below") {
                priceLevel = ""
            }
            saving = false
        }
    }
}

// MARK: - WEI strip

private struct MacBureauMarketWEI: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let selected: String
    let select: (String) -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("WEI · Rates, FX, oil, VIX")
            Text(MacBureauMarketPulse.postureLine(store.marketPulsePayload))
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .bureauLines(16, size: 12)
                .padding(.top, 2)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(MacBureauMarketDesk.weiDefs, id: \.ticker) { def in
                        let quote = feed.quote(def.ticker)
                        let fallback = (store.indicesQuotes + store.watchlist).first { $0.ticker.uppercased() == def.ticker }
                        MacBureauMarketIndexCard(
                            label: def.label,
                            ticker: def.ticker,
                            last: quote?.lastPrice ?? fallback?.last,
                            change: quote?.changePct ?? fallback?.pct,
                            currency: quote?.currency,
                            spark: feed.sparks[def.ticker] ?? [],
                            selected: selected == def.ticker
                        ) {
                            select(def.ticker)
                        }
                    }
                }
                .padding(.top, 6)
                .padding(.bottom, 10)
                .padding(.horizontal, 6)
            }
            .padding(.horizontal, -6)
            .padding(.top, 8)
        }
    }
}

/// `.yf-index-card`: the index's name, its ticker, the last price and the day's move; the
/// chosen one edged in brass.
private struct MacBureauMarketIndexCard: View {
    @Environment(\.colorScheme) private var colorScheme
    let label: String
    let ticker: String
    let last: Double?
    let change: Double?
    let currency: String?
    let spark: [Double]
    let selected: Bool
    let action: () -> Void

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: 14, style: .circular)
        Button(action: action) {
            VStack(alignment: .leading, spacing: 0) {
                Text(label)
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(16, size: 12)
                Text(ticker)
                    .font(BSHType.bureauSans(15, weight: .semibold))
                    .tracking(-0.15)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .bureauLines(20, size: 15)
                    .padding(.top, 4)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(MacBureauMarketFormat.price(last, currency: currency))
                        .font(BSHType.bureauSans(18, weight: .semibold).monospacedDigit())
                        .tracking(-0.18)
                        .foregroundStyle(ink.ink)
                        .fixedSize()
                    Spacer(minLength: 0)
                    if let signed = MacBureauMarketFormat.signed(change) {
                        Text(signed)
                            .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                            .tracking(-0.12)
                            .foregroundStyle((change ?? 0) >= 0 ? ink.success : ink.danger)
                            .fixedSize()
                            .frame(width: MacBureauMarketText.width(signed, size: 12, weight: .semibold, tracking: -0.12, tabular: true), alignment: .leading)
                    } else {
                        Text("Waiting")
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.subtle)
                            .fixedSize()
                    }
                }
                .frame(height: 24)
                .padding(.top, 8)
                if spark.count > 1 {
                    MacBureauMarketSparkline(values: spark)
                        .padding(.top, 8)
                }
            }
            .frame(minWidth: 124, alignment: .leading)
            .fixedSize(horizontal: true, vertical: false)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .modifier(MacBureauMarketCardSurface(selected: selected))
            .background {
                if selected {
                    // 0 8px 22px -14px: a soft shade tucked under the card.
                    shape.fill(ink.shadow(ink.dark ? 1 : 0.4))
                        .padding(14)
                        .blur(radius: 11)
                        .offset(y: 8)
                }
            }
            .contentShape(shape)
        }
        .buttonStyle(.plain)
    }
}

private struct MacBureauMarketCardSurface: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    let selected: Bool

    func body(content: Content) -> some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: 14, style: .circular)
        if selected {
            content
                .background(shape.fill(ink.tray))
                .overlay(shape.inset(by: -0.75).stroke(ink.accentGlow(1), lineWidth: 1.5))
        } else {
            content.bureauMarketTray()
        }
    }
}

// MARK: - Pulse wording

enum MacBureauMarketPulse {
    static func posture(_ payload: MacMarketPulsePayload?) -> String {
        let raw = (payload?.sections?.marketRegime?.posture ?? "empty").lowercased()
        switch raw.replacingOccurrences(of: "-", with: "_") {
        case "risk_on": return "Risk-on"
        case "risk_off": return "Risk-off"
        case "neutral": return "Neutral"
        case "empty", "": return "No pulse yet"
        default: return payload?.sections?.marketRegime?.posture ?? "No pulse yet"
        }
    }

    static func postureLine(_ payload: MacMarketPulsePayload?) -> String {
        let label = posture(payload)
        if let top = payload?.summary?.topSignal, !top.isEmpty { return "\(label) · \(top)" }
        return label
    }

    static func breadth(_ payload: MacMarketPulsePayload?) -> String {
        let b = payload?.sections?.marketRegime?.breadth
        return "\(b?.positiveSignals ?? 0) up · \(b?.negativeSignals ?? 0) down · \(b?.neutralSignals ?? 0) flat"
    }
}
