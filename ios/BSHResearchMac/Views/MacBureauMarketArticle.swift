//
//  MacBureauMarketArticle.swift
//  BSHResearchMac
//
//  Bureau's quote workspace, as the website's `<article class="news-grouped p-5">` on the
//  Market page: the symbol's header with its price, the ranges, the compare row, the chart,
//  session & returns, the pair spread, the ticker note and logged calls, research, COMP,
//  RRG, the 52-week range, earnings & revisions, all stats, the Nasdaq workspace, filings
//  and the page's actions.
//

import AppKit
import SwiftUI

struct MacBureauMarketArticle: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    @ObservedObject var detail: MacQuoteDetailModel
    let ticker: String
    @Binding var compareTickers: [String]
    @Binding var twoUp: Bool
    @Binding var secondaryTicker: String?
    let deskBTicker: String?
    let select: (String) -> Void

    @AppStorage("mac.chart.expanded") private var deskExpanded = false
    @AppStorage("mac.chart.vwap") private var showVWAP = true
    @State private var hpInput = ""
    @State private var showAddLotSheet = false
    @State private var showAddAlertSheet = false
    @State private var showPair = false
    @State private var pairRatio = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var row: MacBureauMarketSelection { MacBureauMarketSelection.make(ticker, store: store, feed: feed) }

    private var chartPayload: MacChartPayload? {
        guard let payload = store.selectedChart else { return nil }
        if let t = payload.ticker, t.uppercased() != ticker { return nil }
        return payload
    }

    var body: some View {
        let row = row
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketQuoteHeader(row: row, twoUp: $twoUp)
                .contextMenu {
                    // The Mac's desk tools the website keeps elsewhere: book lots and alerts.
                    Button("Add Book Lot…") { showAddLotSheet = true }
                        .disabled(!store.canWriteDesk)
                    Button("New Price Alert…") { showAddAlertSheet = true }
                        .disabled(!store.canWriteDesk)
                    Button("Open Quote on the Web") { MacConfig.openInBrowser(MacConfig.webQuoteURL(ticker: ticker)) }
                }
            rangeRow
                .padding(.top, 16)
            compareRow
                .padding(.top, 12)
            if let error = store.chartError, chartPayload == nil {
                Text(error)
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.danger)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
                    .padding(.top, 12)
            }
            charts
                .padding(.top, 12)
            MacBureauMarketReturns(row: row, points: chartPayload?.points ?? [], peers: feed.peers, range: store.selectedChartRange)
                .padding(.top, 16)
            pairRow
                .padding(.top, 12)
            if showPair, let pair = pairPayload {
                pairSection(pair)
                    .padding(.top, 8)
            }
            MacBureauMarketNote(ticker: ticker)
                .padding(.top, 12)
            MacBureauMarketSignalLog(ticker: ticker)
                .padding(.top, 8)
            MacBureauMarketResearch(row: row, feed: feed, select: select)
                .padding(.top, 16)
            MacBureauMarketComp(peers: feed.peers, select: select, setSecondary: setSecondary)
                .padding(.top, 20)
            if let peers = feed.peers, !MacBureauMarketRRG.points(peers).isEmpty {
                MacBureauMarketRRG(peers: peers, select: select)
                    .padding(.top, 20)
            }
            if let pct = weekRangePct(row) {
                weekRange(row, pct: pct)
                    .padding(.top, 16)
            }
            MacBureauMarketEarnings(workspace: store.selectedWorkspace)
            MacBureauMarketAllStats(row: row, workspace: store.selectedWorkspace)
                .padding(.top, 20)
            MacBureauMarketWorkspace(
                ticker: ticker,
                workspace: store.selectedWorkspace,
                points: chartPayload?.points ?? [],
                range: store.selectedChartRange,
                lastPrice: row.last,
                feed: feed
            )
            MacBureauMarketFilings(ticker: ticker, name: row.name)
                .padding(.top, 20)
            MacBureauMarketActions(row: row)
                .padding(.top, 20)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
        .sheet(isPresented: $showAddLotSheet) {
            AddBookLotSheet(ticker: ticker).environmentObject(store)
        }
        .sheet(isPresented: $showAddAlertSheet) {
            AddPriceAlertSheet(ticker: ticker).environmentObject(store)
        }
    }

    // MARK: Ranges

    private var rangeRow: some View {
        HStack(spacing: 4) {
            ForEach(MacChartRange.allCases) { range in
                MacBureauMarketRangeItem(range == .max ? "Max" : range.rawValue, selected: store.selectedChartRange == range) {
                    Task { await store.loadChart(range: range) }
                }
            }
            MacBureauMarketRangeItem("Session", selected: store.selectedChartRange == .d1) {
                showVWAP = true
                if store.selectedChartRange != .d1 { Task { await store.loadChart(range: .d1) } }
            }
        }
    }

    // MARK: HP · Compare

    private var compareRow: some View {
        HStack(spacing: 8) {
            MacBureauMarketLabel("HP · Compare")
            ForEach(compareTickers, id: \.self) { symbol in
                MacBureauMarketRangeItem("\(symbol) ×", selected: true) {
                    compareTickers.removeAll { $0 == symbol }
                }
                .help("Remove from compare")
            }
            HStack(spacing: 4) {
                MacBureauMarketInput(placeholder: "Ticker", text: $hpInput, width: 112, height: 22, onSubmit: addCompare)
                MacBureauMarketRangeItem("Add", action: addCompare)
            }
        }
    }

    private func addCompare() {
        let symbol = hpInput.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        hpInput = ""
        guard !symbol.isEmpty, symbol.range(of: "^[A-Z0-9][A-Z0-9.\\-^=]{0,15}$", options: .regularExpression) != nil else { return }
        if compareTickers.contains(symbol) {
            compareTickers.removeAll { $0 == symbol }
        } else if compareTickers.count < 4, symbol != ticker {
            compareTickers.append(symbol)
        }
    }

    private func setSecondary(_ symbol: String) {
        guard symbol != ticker else { return }
        secondaryTicker = symbol
        if !compareTickers.contains(symbol), compareTickers.count < 4 { compareTickers.append(symbol) }
        twoUp = true
    }

    // MARK: Charts

    private var emptyPayload: MacChartPayload {
        MacChartPayload(ticker: ticker, name: nil, exchange: nil, currency: nil, previousClose: nil, points: [])
    }

    @ViewBuilder
    private var charts: some View {
        let main = MacQuoteChartPanel(
            ticker: ticker,
            payload: chartPayload ?? emptyPayload,
            range: store.selectedChartRange,
            markers: MacBureauMarketChartEvents.markers(ticker: ticker, store: store),
            compare: detail.compareSeries,
            peers: feed.peerSeries,
            compareTickers: $compareTickers,
            loading: store.loadingChart
        )
        if twoUp, let b = deskBTicker, b != ticker {
            HStack(alignment: .top, spacing: 12) {
                main
                    .frame(maxWidth: .infinity)
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        Text(b)
                            .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                            .tracking(-0.15)
                            .foregroundStyle(ink.ink)
                            .lineLimit(1)
                            .bureauLines(20, size: 15)
                        Spacer(minLength: 0)
                        MacBureauMarketRangeItem("Focus") { select(b) }
                    }
                    .padding(.bottom, 8)
                    MacQuoteChartPanel(
                        ticker: b,
                        payload: feed.secondary ?? MacChartPayload(ticker: b, name: nil, exchange: nil, currency: nil, previousClose: nil, points: []),
                        range: store.selectedChartRange,
                        markers: [],
                        compare: [],
                        peers: [],
                        compareTickers: .constant([]),
                        loading: feed.secondaryLoading
                    )
                    let ladder = MacQuoteMath.returnLadder(feed.secondary?.points ?? [], overrides: [:], includeThreeYear: false)
                        .filter { ["1d", "1w", "1m", "ytd"].contains($0.id) }
                    if (feed.secondary?.points?.count ?? 0) > 1 {
                        MacBureauMarketLadder(rungs: ladder)
                            .padding(.top, 8)
                    }
                }
                .frame(maxWidth: .infinity)
            }
        } else {
            main
        }
    }

    // MARK: Pair spread

    private var pairPeer: (ticker: String, points: [MacChartPoint])? {
        if twoUp, let b = deskBTicker, let points = feed.secondary?.points, !points.isEmpty { return (b, points) }
        if let series = detail.compareSeries.first(where: { $0.ticker != ticker }) { return (series.ticker, series.points) }
        return nil
    }

    private var hasPairPeer: Bool {
        compareTickers.contains { $0 != ticker } || (twoUp && deskBTicker != nil)
    }

    /// pairSpreadSeries: A−B (or A/B) on the dates both series print.
    private var pairPayload: MacChartPayload? {
        guard let peer = pairPeer, let a = chartPayload?.points, a.count > 1 else { return nil }
        let other = MacQuoteMath.aligned(peer.points, to: a)
        let points: [MacChartPoint] = zip(a, other).compactMap { point, b in
            guard let close = point.close, let b, b != 0 else { return nil }
            return MacChartPoint(t: point.t, close: pairRatio ? close / b : close - b, volume: nil)
        }
        guard points.count > 1 else { return nil }
        return MacChartPayload(ticker: "\(ticker)-\(peer.ticker)", name: nil, exchange: nil, currency: "", previousClose: nil, points: points)
    }

    private var pairStats: (last: Double, z: Double?)? {
        guard let values = pairPayload?.points?.compactMap(\.close), values.count >= 5, let last = values.last else { return nil }
        let mean = values.reduce(0, +) / Double(values.count)
        let variance = values.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / Double(values.count)
        let sigma = variance.squareRoot()
        return (last, sigma > 0 ? (last - mean) / sigma : nil)
    }

    private var pairRow: some View {
        HStack(spacing: 8) {
            MacBureauMarketRangeItem("Pair spread", selected: showPair) { if hasPairPeer { showPair.toggle() } }
            if showPair, let stats = pairStats {
                (Text("Last ").foregroundColor(ink.muted)
                    + Text(MacBureauMarketFormat.number(stats.last)).foregroundColor(ink.ink)
                    + Text(stats.z == nil ? "" : " · z ").foregroundColor(ink.muted)
                    + Text(stats.z.map { MacBureauMarketFormat.number($0) } ?? "").foregroundColor(ink.ink))
                    .font(BSHType.bureauSans(11).monospacedDigit())
            }
        }
    }

    private func pairSection(_ payload: MacChartPayload) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                MacBureauMarketLabel("Pair spread · \(ticker)/\(pairPeer?.ticker ?? "SPY")")
                Spacer(minLength: 0)
                HStack(spacing: 4) {
                    MacBureauMarketRangeItem("A−B", selected: !pairRatio) { pairRatio = false }
                    MacBureauMarketRangeItem("A/B", selected: pairRatio) { pairRatio = true }
                }
            }
            MacQuoteChartPanel(
                ticker: payload.ticker ?? ticker,
                payload: payload,
                range: store.selectedChartRange,
                markers: [],
                compare: [],
                peers: [],
                compareTickers: .constant([])
            )
        }
    }

    // MARK: 52-week range

    private func weekRangePct(_ row: MacBureauMarketSelection) -> Double? {
        guard let low = row.weekLow, let high = row.weekHigh, let last = row.last, high > low else { return nil }
        return min(100, max(0, (last - low) / (high - low) * 100))
    }

    private func weekRange(_ row: MacBureauMarketSelection, pct: Double) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("52-week range")
                Spacer(minLength: 8)
                Text("\(MacBureauMarketFormat.price(row.weekLow, currency: row.currency)) – \(MacBureauMarketFormat.price(row.weekHigh, currency: row.currency))")
            }
            .font(BSHType.bureauSans(11))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .frame(height: 14)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(ink.ink(0.08)).frame(height: 6)
                    Circle()
                        .fill(ink.tray)
                        .overlay(Circle().inset(by: -0.75).stroke(ink.ink, lineWidth: 1.5))
                        .shadow(color: .black.opacity(0.2), radius: 1.5, y: 1)
                        .frame(width: 9, height: 9)
                        .offset(x: geo.size.width * pct / 100 - 4.5)
                }
                .frame(height: 6)
            }
            .frame(height: 6)
        }
    }
}

// MARK: - The symbol's header

private struct MacBureauMarketQuoteHeader: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauMarketSelection
    @Binding var twoUp: Bool
    @AppStorage("mac.chart.expanded") private var deskExpanded = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            identity
            Spacer(minLength: 0)
            quoteColumn
        }
    }

    private var staleMinutes: Int? {
        guard let date = MacBureauMarketFormat.parse(row.asOf) else { return nil }
        let minutes = Int((Date().timeIntervalSince(date) / 60).rounded())
        return minutes >= 20 ? minutes : nil
    }

    private var identity: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel(row.exchange ?? "Quote")
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(row.ticker)
                    .font(.custom(BSHType.bureauSerif, size: 28))
                    .tracking(-0.28)
                    .foregroundStyle(ink.ink)
                    .fixedSize()
                    .frame(width: MacBureauMarketText.width(row.ticker + " ", face: BSHType.bureauSerif, size: 28, tracking: -0.28), alignment: .leading)
                if let name = row.label ?? row.name, !name.isEmpty {
                    Text(name)
                        .font(.custom(BSHType.bureauSerif, size: 14))
                        .tracking(-0.084)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                }
            }
            .bureauLines(34, size: 28, em: 1.30)
            .padding(.top, 4)
            if let asOf = MacBureauMarketFormat.asOf(row.asOf) {
                let asOfText = "As of \(asOf)"
                // The chip rides the line's baseline, a space and 4pt after the stamp.
                HStack(alignment: .firstTextBaseline, spacing: 4 + MacBureauMarketText.width(" ", size: 11, tracking: 0.066)) {
                    Text(asOfText)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .fixedSize()
                        .frame(width: MacBureauMarketText.width(asOfText, size: 11, tracking: 0.066), alignment: .leading)
                    if let minutes = staleMinutes {
                        Text("Stale \(minutes)m")
                            .font(BSHType.bureauSans(10, weight: .semibold))
                            .tracking(0.12)
                            .foregroundStyle(ink.notice)
                            .padding(.horizontal, 6)
                            // An inline chip's padding paints past the line without moving it.
                            .background(Capsule().fill(ink.notice.opacity(0.15)).padding(.vertical, -2))
                    }
                }
                .bureauLines(14, size: 11)
                .padding(.top, 4)
            }
            HStack(spacing: 8) {
                MacBureauButton("Ask Warren", kind: .filled, size: .small) {
                    store.setCopilotContext(.market(ticker: row.ticker), company: row.company)
                    store.showCopilotPanel = true
                }
                if let company = row.company {
                    accentLink("Open Company") { store.openCompanyPage(company) }
                    accentLink("Console") {
                        store.openInEmbeddedBrowser(MacConfig.webURL(path: "research/\(company.id)", query: ["tab": "console"]))
                    }
                }
            }
            .padding(.top, 6)
        }
    }

    private func accentLink(_ title: String, action: @escaping () -> Void) -> some View {
        MacBureauMarketLink(title: title, ink: ink, action: action)
    }

    private var pinned: Bool { store.isPinned(row.ticker) }

    private var quoteColumn: some View {
        VStack(alignment: .trailing, spacing: 0) {
            HStack(alignment: .top, spacing: 8) {
                MacBureauMarketRangeItem("2-up DES", selected: twoUp) { twoUp.toggle() }
                if let company = row.company {
                    let followed = store.isFollowed(company.id)
                    MacBureauMarketIconButton(icon: followed ? "star-fill" : "star", size: 28, glyph: 16, tint: followed ? ink.notice : nil, pressed: followed, help: followed ? "Unfollow" : "Follow") {
                        Task { await store.toggleFollow(company.id) }
                    }
                }
                VStack(alignment: .trailing, spacing: 4) {
                    MacBureauMarketRangeItem(deskExpanded ? "Collapse" : "Expand", icon: deskExpanded ? "minimize-2" : "maximize-2", selected: deskExpanded) {
                        withAnimation(.easeInOut(duration: 0.2)) { deskExpanded.toggle() }
                    }
                    MacBureauMarketIconButton(icon: pinned ? "star-fill" : "star", size: 28, glyph: 16, tint: pinned ? ink.notice : nil, pressed: pinned, help: pinned ? "Unpin from watchlist" : "Pin to watchlist") {
                        Task { await store.toggleWatchlist(row.ticker) }
                    }
                    .disabled(!store.canWriteDesk)
                }
            }
            .padding(.bottom, 8)
            Text(MacBureauMarketFormat.price(row.last, currency: row.currency))
                .font(BSHType.bureauSans(30, weight: .bold).monospacedDigit())
                .tracking(-0.3)
                .foregroundStyle(ink.ink)
                .fixedSize()
                .frame(width: MacBureauMarketText.width(MacBureauMarketFormat.price(row.last, currency: row.currency), size: 30, weight: .bold, tracking: -0.3, tabular: true), alignment: .leading)
                .lineLimit(1)
                .bureauLines(36, size: 30)
            if let change = row.change, let signed = MacBureauMarketFormat.signed(change) {
                let absText = row.changeAbs.map { ($0 > 0 ? "+" : "") + String(format: "%.2f", $0) }
                HStack(spacing: 4) {
                    LucideIcon(change >= 0 ? "trending-up" : "trending-down", size: 16)
                    if let absText {
                        Text(absText)
                            .fixedSize()
                            .frame(width: MacBureauMarketText.width(absText, size: 15, weight: .semibold, tracking: -0.15, tabular: true), alignment: .leading)
                    }
                    Text(signed)
                        .fixedSize()
                        .frame(width: MacBureauMarketText.width(signed, size: 15, weight: .semibold, tracking: -0.15, tabular: true), alignment: .leading)
                }
                .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                .tracking(-0.15)
                .foregroundStyle(change >= 0 ? ink.success : ink.danger)
                .bureauLines(20, size: 15)
                .padding(.top, 4)
                .padding(.bottom, 4)
            }
        }
    }
}

/// A link in brass ink (`text-caption1 font-medium text-accent-ink`).
struct MacBureauMarketLink: View {
    let title: String
    let ink: MacBureauPageInk
    var size: CGFloat = 11
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(BSHType.bureauSans(size, weight: .medium))
                .tracking(0.066)
                .foregroundStyle(ink.accentInk)
                .underline(hovered)
                .lineLimit(1)
                .fixedSize()
                .frame(width: MacBureauMarketText.width(title, size: size, weight: .medium, tracking: 0.066))
                .padding(.horizontal, 4)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Chart events

enum MacBureauMarketChartEvents {
    /// Earnings prints (E), the next estimated print (E?) and logged calls (S↑ / S↓).
    @MainActor
    static func markers(ticker: String, store: MacAppStore) -> [MacChartMarker] {
        var markers: [MacChartMarker] = []
        func stamp(_ day: String?) -> Int? {
            guard let day = day?.prefix(10), let date = ISO8601DateFormatter().date(from: "\(day)T16:00:00Z") else { return nil }
            return Int(date.timeIntervalSince1970)
        }
        if let earnings = store.selectedWorkspace?.earnings {
            for print in earnings.past {
                if let t = stamp(print.reported) { markers.append(MacChartMarker(t: t, label: "E", kind: .earnings)) }
            }
            if let t = stamp(earnings.nextDate) {
                markers.append(MacChartMarker(t: t, label: "E?", kind: .earnings))
            }
        }
        for signal in store.signals where signal.ticker.uppercased() == ticker.uppercased() {
            guard let raw = signal.recordedAt, let date = MacQuoteInsight.parseISO(raw) else { continue }
            let up = signal.direction == "bullish"
            markers.append(MacChartMarker(t: Int(date.timeIntervalSince1970), label: up ? "S↑" : "S↓", kind: up ? .signalUp : .signalDown))
        }
        return markers
    }
}

// MARK: - Session & returns

private struct MacBureauMarketReturns: View {
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauMarketSelection
    let points: [MacChartPoint]
    let peers: MacQuotePeers?
    let range: MacChartRange

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let gap = MacQuoteMath.gapSplit(open: row.open, previousClose: row.previousClose, last: row.last)
        var overrides: [String: Double] = [:]
        if let v = peers?.primary?.ret1m { overrides["1m"] = v }
        if let v = peers?.primary?.retYtd { overrides["ytd"] = v }
        if let v = peers?.primary?.ret1y { overrides["1y"] = v }
        let longRange = range == .y1 || range == .y5 || range == .max
        let ladder = MacQuoteMath.returnLadder(points, overrides: overrides, includeThreeYear: longRange)
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("Session & returns")
                .padding(.bottom, 8)
            if gap.gap != nil || gap.session != nil {
                HStack(spacing: 16) {
                    gapPart("Overnight", gap.gap, ink: ink)
                    gapPart("Open→last", gap.session, ink: ink)
                }
                .bureauLines(18.72, size: 12.48)
                .padding(.bottom, 8)
            }
            MacBureauMarketLadder(rungs: ladder)
        }
    }

    private func gapPart(_ label: String, _ value: Double?, ink: MacBureauPageInk) -> some View {
        (Text(label + " ").foregroundColor(ink.ink)
            + Text(MacBureauMarketFormat.signed(value) ?? "—")
                .font(MacBureauMarketText.font(12.48, weight: .bold))
                .foregroundColor((value ?? 0) >= 0 ? ink.success : ink.danger))
            .font(MacBureauMarketText.font(12.48))
            .fixedSize()
    }
}

/// `.yf-ladder`: one cell per horizon, its label over the return.
struct MacBureauMarketLadder: View {
    @Environment(\.colorScheme) private var colorScheme
    let rungs: [MacQuoteMath.LadderRung]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 8) {
            ForEach(rungs) { rung in
                VStack(alignment: .leading, spacing: 0) {
                    Text(rung.label)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .bureauLines(14, size: 11)
                    Text(rung.value.flatMap(MacBureauMarketFormat.signed) ?? "—")
                        .font(BSHType.bureauSans(16).monospacedDigit())
                        .tracking(-0.16)
                        .foregroundStyle((rung.value ?? 0) >= 0 ? ink.success : ink.danger)
                        .lineLimit(1)
                        .bureauLines(24, size: 16)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6.4)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(ink.ink(0.04)))
            }
        }
    }
}

// MARK: - Ticker note and calls

private struct MacBureauMarketNote: View {
    @Environment(\.colorScheme) private var colorScheme
    let ticker: String
    @State private var note = ""

    private var key: String { "mac.tickerNote.\(ticker.uppercased())" }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(alignment: .leading, spacing: 4) {
            // The label's 24pt line is the block's (16pt type): its baseline 18pt down.
            MacBureauMarketLabel("Ticker note")
                .padding(.top, 6)
                .padding(.bottom, 2)
            TextField("", text: $note, axis: .vertical)
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .lineLimit(2, reservesSpace: true)
                .lineSpacing(2)
                .background(alignment: .topLeading) {
                    if note.isEmpty {
                        Text("Desk note for this symbol…")
                            .font(BSHType.bureauSans(14))
                            .tracking(-0.084)
                            .foregroundStyle(MacBureauMarketFormat.placeholder)
                            .lineLimit(1)
                            .allowsHitTesting(false)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, minHeight: 56, alignment: .topLeading)
                .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill(ink.dark ? Color.bshFixed(BSHRGB(59, 59, 59)) : Color.white))
                .overlay(alignment: .bottomTrailing) { MacBureauMarketResizeGrip(ink: ink).padding(2) }
                .onChange(of: note) { _, value in UserDefaults.standard.set(value, forKey: key) }
                .padding(.bottom, 6)
        }
        .onAppear { note = UserDefaults.standard.string(forKey: key) ?? "" }
        .onChange(of: ticker) { _, _ in note = UserDefaults.standard.string(forKey: key) ?? "" }
    }
}

/// The corner grip a text area carries on the website.
private struct MacBureauMarketResizeGrip: View {
    let ink: MacBureauPageInk

    var body: some View {
        Path { path in
            path.move(to: CGPoint(x: 7, y: 0.5)); path.addLine(to: CGPoint(x: 0.5, y: 7))
            path.move(to: CGPoint(x: 7, y: 4)); path.addLine(to: CGPoint(x: 4, y: 7))
        }
        .stroke(ink.dark ? Color.white.opacity(0.4) : Color.black.opacity(0.35), lineWidth: 1)
        .frame(width: 8, height: 8)
        .allowsHitTesting(false)
    }
}

private struct MacBureauMarketSignalLog: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let ticker: String
    @State private var toast: String?

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 4) {
            Text("Log call")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
            MacBureauMarketRangeItem("Bullish") { log("bullish") }
            MacBureauMarketRangeItem("Bearish") { log("bearish") }
            if let toast {
                Text(toast)
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.accentInk)
            }
        }
        .disabled(!store.canWriteDesk)
        .onChange(of: ticker) { _, _ in toast = nil }
    }

    private func log(_ direction: String) {
        let symbol = ticker.uppercased()
        Task {
            let ok = await store.logSignal(ticker: symbol, direction: direction, label: "Market desk \(direction) call")
            toast = ok ? "Logged \(symbol)" : "Could not log signal"
        }
    }
}

// MARK: - Research

private struct MacBureauMarketResearch: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauMarketSelection
    @ObservedObject var feed: MacBureauMarketFeed
    let select: (String) -> Void

    struct Hit: Identifiable {
        let id: String
        let kind: String
        let title: String
        let url: String?
        let company: MacCompany?
    }

    /// researchHitsForTicker: the company itself, then the workspace feed's research and
    /// news that name the symbol (or its name).
    private var hits: [Hit] {
        var out: [Hit] = []
        let symbol = row.ticker.uppercased()
        if let company = row.company {
            out.append(Hit(id: "company:\(company.id)", kind: "company", title: company.name ?? symbol, url: nil, company: company))
        }
        let needle = (row.name ?? "").lowercased()
        func named(_ item: MacBureauMarketFeedItem) -> Bool {
            let text = "\(item.title) \(item.summary ?? "") \(item.ticker ?? "")"
            if text.uppercased().contains(symbol) || item.ticker?.uppercased() == symbol { return true }
            return needle.count >= 3 && "\(item.title) \(item.summary ?? "")".lowercased().contains(needle)
        }
        let research = feed.external.filter { $0.kind == "external_research" }
        let news = feed.external.filter { $0.kind == "news" }
        for (kind, items) in [("research", research), ("news", news)] {
            for item in items where named(item) {
                let id = "\(kind):\(item.id)"
                guard out.count < 8, !out.contains(where: { $0.id == id }) else { continue }
                out.append(Hit(id: id, kind: kind, title: item.title, url: item.url, company: nil))
            }
        }
        return out
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let hits = hits
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("Research")
            if hits.isEmpty {
                Text("No research hits for this ticker.")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(14, size: 11)
                    .padding(.top, 4)
            } else {
                VStack(alignment: .leading, spacing: 5.6) {
                    ForEach(hits) { hit in
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Button {
                                if let company = hit.company {
                                    store.openCompanyPage(company)
                                } else if let link = hit.url, let url = URL(string: link) {
                                    NSWorkspace.shared.open(url)
                                }
                            } label: {
                                Text(hit.title)
                                    .font(BSHType.bureauSans(14))
                                    .tracking(-0.084)
                                    .foregroundStyle(ink.ink)
                                    .multilineTextAlignment(.leading)
                            }
                            .buttonStyle(.plain)
                            Text(hit.kind)
                                .font(BSHType.bureauSans(11))
                                .foregroundStyle(ink.muted)
                        }
                    }
                }
                .padding(.top, 8)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
    }
}

// MARK: - COMP · Relative value

private struct MacBureauMarketComp: View {
    @Environment(\.colorScheme) private var colorScheme
    let peers: MacQuotePeers?
    let select: (String) -> Void
    let setSecondary: (String) -> Void
    @State private var bench = "SPY"
    @AppStorage("mac.quote.compMore") private var showMore = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var rows: [MacPeerRow] {
        guard let peers else { return [] }
        return [peers.primary, peers.benchmark].compactMap { $0 } + peers.peers
    }

    /// The website's column widths at the article's width, in its order.
    private var columns: [(title: String, width: CGFloat)] {
        var list: [(String, CGFloat)] = [("Symbol", 165.7), ("1Y", 101.3), ("Price", 67.88), ("1Y", 60.08), ("vs SPY 1Y", 78.27), ("β 60d", 52.33), ("ρ 60d", 52.2)]
        if showMore { list += [("Rev growth", 82), ("Gross mgn", 78), ("Op mgn", 64), ("P/E", 52)] }
        list += [("Max DD", 65.98), ("Mkt cap", 66.92)]
        return list
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                MacBureauMarketLabel("COMP · Relative value")
                Spacer(minLength: 8)
                HStack(spacing: 4) {
                    Text("β / ρ vs")
                        .font(MacBureauMarketText.font(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                    MacBureauMarketInput(placeholder: "", text: $bench, width: 72, height: 22, uppercase: true)
                }
                Spacer(minLength: 8)
                MacBureauMarketRangeItem("More", selected: showMore) { showMore.toggle() }
            }
            .frame(height: 22)
            ScrollView(.horizontal, showsIndicators: showMore) {
                table
            }
        }
    }

    private var benchPoints: [MacChartPoint] {
        let symbol = bench.trimmingCharacters(in: .whitespaces).uppercased()
        return rows.first { $0.ticker.uppercased() == symbol }?.points ?? peers?.benchmark?.points ?? []
    }

    private var table: some View {
        let columns = columns
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 0) {
                ForEach(Array(columns.enumerated()), id: \.offset) { _, column in
                    Text(column.title)
                        .font(MacBureauMarketText.font(11, weight: .semibold))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .padding(.horizontal, 8)
                        .frame(width: column.width, height: 26, alignment: .leading)
                }
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                tableRow(row, columns: columns)
            }
        }
    }

    private func cell(_ text: String, width: CGFloat) -> some View {
        Text(text)
            .font(BSHType.bureauSans(11).monospacedDigit())
            .tracking(0.066)
            .foregroundStyle(ink.ink)
            .lineLimit(1)
            .padding(.horizontal, 8)
            .frame(width: width, height: 40, alignment: .leading)
    }

    private func tableRow(_ row: MacPeerRow, columns: [(title: String, width: CGFloat)]) -> some View {
        let stats = MacQuoteMath.betaAndCorrelation(row.points, benchPoints)
        // The website's cells read a missing figure as 0 (JavaScript's Number(null)).
        var values: [String] = [
            MacBureauMarketFormat.price(row.last ?? 0),
            MacBureauMarketFormat.ret(row.ret1y ?? 0),
            MacBureauMarketFormat.ret(row.vsSpy1y ?? 0),
            MacBureauMarketFormat.number(stats.beta),
            MacBureauMarketFormat.number(stats.corr),
        ]
        if showMore {
            values += [
                MacBureauMarketFormat.ret(row.revenueGrowth ?? 0),
                MacBureauMarketFormat.ret(row.grossMargin ?? 0),
                MacBureauMarketFormat.ret(row.operatingMargin ?? 0),
                MacBureauMarketFormat.number(row.peRatio ?? 0),
            ]
        }
        values += [MacBureauMarketFormat.ret(row.drawdown1y ?? 0), MacBureauMarketFormat.money(row.marketCap ?? 0, compact: true)]
        return HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 4) {
                    Button { select(row.ticker) } label: {
                        Text(row.ticker).foregroundStyle(ink.secondary)
                    }
                    .buttonStyle(.plain)
                    Button { setSecondary(row.ticker) } label: {
                        Text("2↑").foregroundStyle(ink.muted)
                    }
                    .buttonStyle(.plain)
                    .help("2-up DES")
                }
                .font(BSHType.bureauSans(11, weight: .medium))
                .tracking(0.066)
                .frame(height: 14)
                Text(row.sector ?? row.name ?? "")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(14, size: 11)
            }
            .padding(.horizontal, 8)
            .frame(width: columns[0].width, height: 40, alignment: .leading)
            MacBureauMarketSparkline(values: row.spark.isEmpty ? row.points.compactMap(\.close) : row.spark, width: 72, height: 22.4)
                .padding(.horizontal, 8)
                .frame(width: columns[1].width, height: 40, alignment: .leading)
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                cell(value, width: columns[index + 2].width)
            }
        }
    }
}

// MARK: - RRG · vs SPY

private struct MacBureauMarketRRG: View {
    @Environment(\.colorScheme) private var colorScheme
    let peers: MacQuotePeers
    let select: (String) -> Void

    struct Point {
        let ticker: String
        let x: Double
        let y: Double
        let quadrant: String
    }

    private static func rows(_ peers: MacQuotePeers) -> [MacPeerRow] {
        [peers.primary, peers.benchmark].compactMap { $0 } + peers.peers
    }

    /// rrgPoints: x is the 1-year lead over SPY, y the 1-month lead (a missing lead reads
    /// as 0, as the website's Number(null) does).
    static func points(_ peers: MacQuotePeers) -> [Point] {
        rows(peers).map { row in
            let x = row.vsSpy1y ?? 0, y = row.vsSpy1m ?? 0
            let quadrant = x >= 0 ? (y >= 0 ? "Leading" : "Weakening") : (y >= 0 ? "Improving" : "Lagging")
            return Point(ticker: row.ticker, x: x, y: y, quadrant: quadrant)
        }
    }

    /// rrgTrails: each name's last four weekly steps against SPY.
    static func trails(_ peers: MacQuotePeers, steps: Int = 4, stepDays: Int = 5) -> [(ticker: String, path: [(Double, Double)])] {
        let rows = rows(peers)
        guard let spy = rows.first(where: { $0.ticker.uppercased() == "SPY" })?.points, spy.count >= stepDays * 2 else { return [] }
        func periodReturn(_ points: [MacChartPoint], days: Int, end index: Int) -> Double? {
            guard !points.isEmpty, index >= 1 else { return nil }
            let end = points[min(index, points.count - 1)]
            guard let endClose = end.close, endClose != 0 else { return nil }
            let target = end.t - days * 86_400
            var start: Double? = nil
            for point in points where point.t <= target { if let close = point.close { start = close } }
            if start == nil || start == 0 { start = points.first?.close }
            guard let start, start != 0 else { return nil }
            return (endClose - start) / start * 100
        }
        var out: [(ticker: String, path: [(Double, Double)])] = []
        for row in rows where row.ticker.uppercased() != "SPY" && !row.points.isEmpty {
            var path: [(Double, Double)] = []
            for step in stride(from: steps - 1, through: 0, by: -1) {
                let endIndex = max(0, row.points.count - 1 - step * stepDays)
                let spyEnd = max(0, spy.count - 1 - step * stepDays)
                guard let a1y = periodReturn(row.points, days: 252, end: endIndex),
                      let s1y = periodReturn(spy, days: 252, end: spyEnd),
                      let a1m = periodReturn(row.points, days: 21, end: endIndex),
                      let s1m = periodReturn(spy, days: 21, end: spyEnd) else { continue }
                path.append((a1y - s1y, a1m - s1m))
            }
            if path.count >= 2 { out.append((row.ticker, path)) }
        }
        return out
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let points = Self.points(peers)
        let trails = Self.trails(peers)
        let size: CGFloat = 220, pad: CGFloat = 22
        let maxAbs = max(8, points.map { max(abs($0.x), abs($0.y)) }.max() ?? 1, 1)
        let mid = size / 2
        let scale = (size - pad * 2) / 2 / CGFloat(maxAbs)
        let place = { (x: Double, y: Double) in CGPoint(x: mid + CGFloat(x) * scale, y: mid - CGFloat(y) * scale) }
        VStack(alignment: .leading, spacing: 8) {
            MacBureauMarketLabel("RRG · vs SPY")
            HStack(alignment: .top, spacing: 12) {
                Canvas { context, _ in
                    var axes = Path()
                    axes.move(to: CGPoint(x: mid, y: 8)); axes.addLine(to: CGPoint(x: mid, y: size - 8))
                    axes.move(to: CGPoint(x: 8, y: mid)); axes.addLine(to: CGPoint(x: size - 8, y: mid))
                    context.stroke(axes, with: .color(ink.rule), lineWidth: 1)
                    for trail in trails {
                        var line = Path()
                        for (index, step) in trail.path.enumerated() {
                            let point = place(step.0, step.1)
                            if index == 0 { line.move(to: point) } else { line.addLine(to: point) }
                        }
                        context.stroke(line, with: .color(ink.accent.opacity(0.35)), style: StrokeStyle(lineWidth: 1.25, lineCap: .round, lineJoin: .round))
                    }
                    for point in points {
                        let center = place(point.x, point.y)
                        let up = point.quadrant == "Leading" || point.quadrant == "Improving"
                        context.fill(Path(ellipseIn: CGRect(x: center.x - 5, y: center.y - 5, width: 10, height: 10)), with: .color(up ? ink.success : ink.danger))
                        // The label's baseline 3pt under the dot's center, 7pt to its right.
                        let label = context.resolve(Text(point.ticker).font(BSHType.bureauSans(9)).foregroundColor(ink.secondary))
                        context.draw(label, at: CGPoint(x: center.x + 7, y: center.y + 3 - 9), anchor: .topLeading)
                    }
                }
                .frame(width: size, height: size)
                .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.035)))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .circular))
                .contentShape(Rectangle())
                .onTapGesture(coordinateSpace: .local) { location in
                    let hit = points.min { a, b in
                        let pa = place(a.x, a.y), pb = place(b.x, b.y)
                        return hypot(pa.x - location.x, pa.y - location.y) < hypot(pb.x - location.x, pb.y - location.y)
                    }
                    if let hit, hypot(place(hit.x, hit.y).x - location.x, place(hit.x, hit.y).y - location.y) < 12 { select(hit.ticker) }
                }
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                        Button { select(point.ticker) } label: {
                            (Text(point.ticker + " ").foregroundColor(ink.ink) + Text(point.quadrant).foregroundColor(ink.muted))
                                .font(MacBureauMarketText.font(12.48))
                                .lineLimit(1)
                                .bureauLines(18.72, size: 12.48)
                        }
                        .buttonStyle(.plain)
                    }
                }
                Spacer(minLength: 0)
            }
        }
    }
}

// MARK: - Earnings & revisions, stats

/// `.yf-stats`: a three-column grid of muted labels over their values.
struct MacBureauMarketStats: View {
    @Environment(\.colorScheme) private var colorScheme
    let items: [(label: String, value: String, tone: Color?)]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 24, alignment: .topLeading), count: 3), alignment: .leading, spacing: 12) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.label)
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .bureauLines(14, size: 11)
                    Text(item.value)
                        .font(BSHType.bureauSans(14, weight: .semibold).monospacedDigit())
                        .tracking(-0.084)
                        .foregroundStyle(item.tone ?? ink.ink)
                        .bureauLines(20, size: 14)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

private struct MacBureauMarketEarnings: View {
    @Environment(\.colorScheme) private var colorScheme
    let workspace: MacQuoteWorkspace?

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let strip = MacQuoteMath.earningsStrip(workspace)
        if strip.nextDate != nil || strip.lastSurprise != nil {
            VStack(alignment: .leading, spacing: 8) {
                MacBureauMarketLabel("Earnings & revisions")
                MacBureauMarketStats(items: [
                    ("Next earnings", (strip.nextDate ?? "—") + (strip.nextEstimated ? " est." : ""), nil),
                    ("Last surprise", MacBureauMarketFormat.ret(strip.lastSurprise), strip.lastSurprise.map { $0 >= 0 ? ink.success : ink.danger }),
                    ("Next EPS cons.", MacBureauMarketFormat.number(strip.consensus), nil),
                    ("Estimate revisions", strip.revisionsUp != nil ? "+\(Int(strip.revisionsUp ?? 0)) / −\(Int(strip.revisionsDown ?? 0))" : "—", nil),
                ] + (strip.avgSurprise.map { [("Avg surprise", MacBureauMarketFormat.ret($0), nil)] } ?? []))
            }
            .padding(.top, 24)
        }
    }
}

private struct MacBureauMarketAllStats: View {
    let row: MacBureauMarketSelection
    let workspace: MacQuoteWorkspace?
    @AppStorage("mac.quote.allStats") private var showAll = false

    var body: some View {
        let summary = workspace?.summary
        let earn = workspace?.earnings
        let week: String = {
            guard let low = row.weekLow, let high = row.weekHigh else { return "—" }
            return "\(MacBureauMarketFormat.price(low, currency: row.currency)) – \(MacBureauMarketFormat.price(high, currency: row.currency))"
        }()
        let stats: [(label: String, value: String, tone: Color?)] = [
            ("Previous close", MacBureauMarketFormat.price(row.previousClose, currency: row.currency), nil),
            ("Open", MacBureauMarketFormat.price(row.open, currency: row.currency), nil),
            ("Day high", MacBureauMarketFormat.price(row.high, currency: row.currency), nil),
            ("Day low", MacBureauMarketFormat.price(row.low, currency: row.currency), nil),
            ("Volume", MacBureauMarketFormat.compact(row.volume), nil),
            ("Avg. volume", MacBureauMarketFormat.compact(row.avgVolume), nil),
            ("Market cap", MacBureauMarketFormat.money(row.marketCap, compact: true), nil),
            ("P/E (TTM)", MacBureauMarketFormat.number(row.peRatio), nil),
            ("EPS (TTM)", MacBureauMarketFormat.price(row.eps, currency: row.currency), nil),
            ("Beta", MacBureauMarketFormat.number(row.beta), nil),
            ("Dividend", summary?.dividend ?? row.dividend ?? "—", nil),
            ("Yield", row.dividendYield.map(MacBureauMarketFormat.percent) ?? summary?.yield ?? "—", nil),
            ("Ex-dividend", summary?.exDividend ?? "—", nil),
            ("52-week range", week, nil),
            ("Next earnings", earn?.nextDate.map { $0 + ((earn?.nextEstimated ?? false) ? " (est.)" : "") } ?? "—", nil),
        ]
        return VStack(alignment: .leading, spacing: 12) {
            MacBureauMarketRangeItem("All stats", selected: showAll) {
                withAnimation(.easeInOut(duration: 0.2)) { showAll.toggle() }
            }
            .padding(.top, 3)
            if showAll {
                MacBureauMarketStats(items: stats)
            }
        }
    }
}

// MARK: - Filings & actions

private struct MacBureauMarketFilings: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let ticker: String
    let name: String?

    private static let formRE = try! NSRegularExpression(pattern: "\\b(10-?K|10-?Q|8-?K|6-?K|20-?F|S-1|13[DFG]|DEF\\s*14A|SC\\s*13[DG])\\b", options: [.caseInsensitive])

    /// filingSnips: the desk's headlines about this symbol that are filings.
    private var filings: [(item: MacNewsItem, form: String?)] {
        let symbol = ticker.uppercased()
        let needle = (name ?? "").lowercased()
        return store.news.compactMap { item -> (MacNewsItem, String?)? in
            let text = "\(item.title) \(item.summary ?? "")"
            let isFiling = (item.category ?? "").lowercased().contains("filing")
                || text.lowercased().range(of: "\\b(10-k|10-q|8-k|s-1|sec filing|earnings|13f)\\b", options: .regularExpression) != nil
            guard isFiling else { return nil }
            let named = text.uppercased().contains(symbol) || item.ticker?.uppercased() == symbol || (!needle.isEmpty && text.lowercased().contains(needle))
            guard named else { return nil }
            let range = NSRange(item.title.startIndex..., in: item.title)
            let form = Self.formRE.firstMatch(in: item.title, range: range).flatMap { Range($0.range(at: 1), in: item.title) }.map { String(item.title[$0]).uppercased() }
            return (item, form)
        }
        .prefix(8)
        .map { $0 }
    }

    private func edgar(_ type: String) -> URL? {
        var components = URLComponents(string: "https://www.sec.gov/cgi-bin/browse-edgar")
        var items = [
            URLQueryItem(name: "action", value: "getcompany"),
            URLQueryItem(name: "ticker", value: ticker.uppercased()),
            URLQueryItem(name: "owner", value: "include"),
            URLQueryItem(name: "count", value: "10"),
        ]
        if !type.isEmpty { items.append(URLQueryItem(name: "type", value: type)) }
        components?.queryItems = items
        return components?.url
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let filings = filings
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("Filings & transcripts")
                .padding(.bottom, 8)
            if filings.isEmpty {
                HStack(spacing: 8) {
                    ForEach([("EDGAR", ""), ("10-K", "10-K"), ("10-Q", "10-Q"), ("8-K", "8-K")], id: \.0) { form in
                        MacBureauMarketRangeItem(form.0) { if let url = edgar(form.1) { NSWorkspace.shared.open(url) } }
                    }
                }
                .padding(.bottom, 12)
                Text("No filing headlines in the desk feed — use EDGAR links above.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(16, size: 12)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(filings, id: \.item.id) { filing in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                if let form = filing.form {
                                    Text(form)
                                        .font(BSHType.bureauSans(11, weight: .semibold))
                                        .foregroundStyle(ink.muted)
                                }
                                Button {
                                    if let link = filing.item.url, let url = URL(string: link) { NSWorkspace.shared.open(url) }
                                } label: {
                                    Text(filing.item.title)
                                        .font(BSHType.bureauSans(14))
                                        .foregroundStyle(filing.item.url == nil ? ink.ink : ink.accentInk)
                                        .multilineTextAlignment(.leading)
                                }
                                .buttonStyle(.plain)
                                Text(MacBureauMarketFormat.age(filing.item.publishedAt))
                                    .font(BSHType.bureauSans(11))
                                    .foregroundStyle(ink.muted)
                            }
                            if let summary = filing.item.summary, !summary.isEmpty {
                                Text(summary)
                                    .font(BSHType.bureauSans(12))
                                    .foregroundStyle(ink.secondary)
                                    .lineLimit(3)
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct MacBureauMarketActions: View {
    @EnvironmentObject private var store: MacAppStore
    let row: MacBureauMarketSelection

    var body: some View {
        HStack(spacing: 8) {
            MacBureauButton("Ask Warren", kind: .filled) {
                store.setCopilotContext(.market(ticker: row.ticker), company: row.company)
                store.showCopilotPanel = true
            }
            MacBureauButton("Why is this moving?") { askWhyMoving() }
                .disabled(!store.canRunTasks)
            if let company = row.company {
                MacBureauButton("Open Company") { store.openCompanyPage(company) }
            }
            MacBureauButton("Pulse") { store.selectedTab = .pulse }
            MacBureauButton("Signals") { store.openSignalLog(seedTicker: row.ticker) }
            MacBureauButton("Tracking") { store.selectedTab = .portfolio }
        }
    }

    /// The website's prompt: the move, the session gap and the recent headlines, asked
    /// only when this is pressed.
    private func askWhyMoving() {
        let symbol = row.ticker
        var lines = ["Why is \(symbol) moving (\(MacBureauMarketFormat.signed(row.change) ?? "—"))?"]
        let headlines = store.news
            .filter { "\($0.title) \($0.summary ?? "")".uppercased().contains(symbol) || $0.ticker?.uppercased() == symbol }
            .prefix(4)
            .map { "- \($0.title)" }
        lines.append("\nRecent headlines:\n" + (headlines.isEmpty ? "(no matched headlines in the workspace feed)" : headlines.joined(separator: "\n")))
        let gap = MacQuoteMath.gapSplit(open: row.open, previousClose: row.previousClose, last: row.last)
        if let g = gap.gap { lines.append(String(format: "Overnight gap: %+.2f%%, open→last: %+.2f%%", g, gap.session ?? 0)) }
        if let note = UserDefaults.standard.string(forKey: "mac.tickerNote.\(symbol)"), !note.isEmpty { lines.append("Note: \(note)") }
        store.askWarren(lines.joined(separator: "\n"), context: .market(ticker: symbol), company: row.company)
    }
}
