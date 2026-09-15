import Charts
import SwiftUI

// Everything the web desk shows for a selected ticker besides the chart
// (frontend/src/views/MarketRadarView.vue + components/QuoteWorkspace.vue).

// MARK: - Loader

/// Peers, calendar and compare-ticker charts for the selected quote. The chart and Nasdaq
/// workspace already load through the store; these are only read on this page.
@MainActor
final class MacQuoteDetailModel: ObservableObject {
    @Published private(set) var peers: MacQuotePeers?
    @Published private(set) var calendar: [MacCalendarEvent] = []
    @Published private(set) var compareSeries: [MacCompareSeries] = []

    private var detailTicker: String?
    private var compareKey: String?

    func loadDetail(ticker: String) async {
        let symbol = ticker.uppercased()
        guard detailTicker != symbol else { return }
        detailTicker = symbol
        peers = nil
        calendar = []
        async let peerResult = try? MacAPIClient.shared.fetchPeers(ticker: symbol)
        async let calendarResult = try? MacAPIClient.shared.fetchQuoteCalendar(tickers: [symbol])
        let (loadedPeers, loadedCalendar) = await (peerResult, calendarResult)
        guard detailTicker == symbol else { return }
        peers = loadedPeers
        calendar = loadedCalendar?.events ?? []
    }

    func loadCompare(tickers: [String], range: MacChartRange) async {
        let key = tickers.joined(separator: ",") + "|" + range.apiValue
        guard compareKey != key else { return }
        compareKey = key
        compareSeries = compareSeries.filter { tickers.contains($0.ticker) }
        var loaded: [MacCompareSeries] = []
        await withTaskGroup(of: MacCompareSeries?.self) { group in
            for symbol in tickers {
                group.addTask {
                    guard let payload = try? await MacAPIClient.shared.fetchChart(ticker: symbol, range: range),
                          let points = payload.points, !points.isEmpty else { return nil }
                    return MacCompareSeries(ticker: symbol, points: points)
                }
            }
            for await series in group { if let series { loaded.append(series) } }
        }
        guard compareKey == key else { return }
        compareSeries = tickers.compactMap { symbol in loaded.first { $0.ticker == symbol } }
    }

    /// SPY first, then sector/book peers, as the web desk layers them.
    var peerSeries: [MacCompareSeries] {
        guard let peers else { return [] }
        var rows: [MacCompareSeries] = []
        if let bench = peers.benchmark, !bench.points.isEmpty { rows.append(MacCompareSeries(ticker: bench.ticker, points: bench.points)) }
        rows += peers.peers.prefix(3).filter { !$0.points.isEmpty }.map { MacCompareSeries(ticker: $0.ticker, points: $0.points) }
        return rows
    }
}

// MARK: - Shared bits

private struct MacInsightCard<Content: View, Trailing: View>: View {
    let title: String
    var systemImage: String? = nil
    @ViewBuilder var trailing: () -> Trailing
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                if let systemImage {
                    Image(systemName: systemImage).foregroundStyle(Color.accentColor)
                }
                Text(title).font(.dsHeadline)
                Spacer()
                trailing()
            }
            content()
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .appleGlassCard()
    }
}

extension MacInsightCard where Trailing == EmptyView {
    init(title: String, systemImage: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.trailing = { EmptyView() }
        self.content = content
    }
}

private func pctText(_ value: Double?, digits: Int = 2) -> Text {
    guard let value else { return Text("—").foregroundStyle(.secondary) }
    return Text(String(format: "%@%.\(digits)f%%", value >= 0 ? "+" : "−", abs(value)))
        .foregroundStyle(value >= 0 ? Color.green : Color.red)
}

private func money(_ value: Double?) -> String {
    guard let value else { return "—" }
    return MacChartFormat.price(value)
}

private let statColumns = [GridItem(.adaptive(minimum: 150), spacing: 10)]

// MARK: - Price header

struct MacQuotePriceLine: View {
    let payload: MacChartPayload?

    var body: some View {
        if let payload, let last = payload.lastPrice ?? payload.points?.last?.close {
            let change = payload.change ?? payload.previousClose.map { last - $0 }
            let pct = payload.changePct ?? {
                guard let prev = payload.previousClose, prev != 0 else { return nil }
                return (last - prev) / prev * 100
            }()
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(MacChartFormat.price(last))
                    .font(.system(size: 30, weight: .semibold).monospacedDigit())
                    .fixedSize()
                if let change {
                    Label {
                        Text("\(change >= 0 ? "+" : "−")\(String(format: "%.2f", abs(change))) (\(MacChartFormat.signedPct(pct ?? 0)))")
                    } icon: {
                        Image(systemName: change >= 0 ? "arrow.up.right" : "arrow.down.right")
                    }
                    .font(.title3.monospacedDigit().weight(.semibold))
                    .foregroundStyle(change >= 0 ? Color.green : Color.red)
                    .fixedSize()
                }
                if let asOf = payload.asOf, let date = MacQuoteInsight.parseISO(asOf) {
                    Text("As of \(date.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    let minutes = Int(Date().timeIntervalSince(date) / 60)
                    if minutes >= 20 && minutes < 60 * 24 * 3 {
                        Text("Stale \(minutes)m")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.orange)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Capsule().fill(Color.orange.opacity(0.14)))
                    }
                }
            }
        }
    }
}

enum MacQuoteInsight {
    static func parseISO(_ raw: String) -> Date? {
        let full = ISO8601DateFormatter()
        full.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = full.date(from: raw) { return d }
        return ISO8601DateFormatter().date(from: raw)
    }
}

// MARK: - Session & returns, 52-week range, earnings strip

struct MacQuoteSessionCard: View {
    let payload: MacChartPayload
    let range: MacChartRange
    let peers: MacQuotePeers?

    var body: some View {
        let points = payload.points ?? []
        let last = payload.lastPrice ?? points.last?.close
        let gap = MacQuoteMath.gapSplit(open: payload.open, previousClose: payload.previousClose, last: last)
        // Horizons come from a year of daily closes (peers) when available, so the ladder is
        // meaningful even on the intraday chart; 1D is the live session move.
        let base = (peers?.primary?.points.isEmpty == false) ? peers!.primary!.points : points
        var overrides: [String: Double] = [:]
        if let v = payload.changePct { overrides["1d"] = v }
        if let v = peers?.primary?.ret1m { overrides["1m"] = v }
        if let v = peers?.primary?.retYtd { overrides["ytd"] = v }
        if let v = peers?.primary?.ret1y { overrides["1y"] = v }
        let longRange = range == .y1 || range == .y5 || range == .max
        let ladder = MacQuoteMath.returnLadder(longRange ? points : base, overrides: overrides, includeThreeYear: range == .y5 || range == .max)

        return MacInsightCard(title: "Session & returns", systemImage: "clock.arrow.2.circlepath") {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 18) {
                    Text("Gap split").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    HStack(spacing: 4) { Text("Overnight").font(.caption).foregroundStyle(.secondary); pctText(gap.gap).font(.callout.monospacedDigit().weight(.semibold)) }
                    HStack(spacing: 4) { Text("Open→last").font(.caption).foregroundStyle(.secondary); pctText(gap.session).font(.callout.monospacedDigit().weight(.semibold)) }
                }
                HStack(spacing: 8) {
                    ForEach(ladder) { rung in
                        VStack(spacing: 2) {
                            Text(rung.label).font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                            pctText(rung.value, digits: 1).font(.callout.monospacedDigit().weight(.semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .appleGlassTile()
                    }
                }
                fiftyTwoWeek(last: last)
            }
        }
    }

    @ViewBuilder
    private func fiftyTwoWeek(last: Double?) -> some View {
        let low = payload.fiftyTwoWeekLow ?? peers?.primary?.low1y
        let high = payload.fiftyTwoWeekHigh ?? peers?.primary?.high1y
        if let low, let high, high > low {
            VStack(alignment: .leading, spacing: 4) {
                Text("52-week range").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    Text(money(low)).font(.caption.monospacedDigit())
                    GeometryReader { geo in
                        let position = last.map { min(max(($0 - low) / (high - low), 0), 1) } ?? 0.5
                        ZStack(alignment: .leading) {
                            Capsule().fill(LinearGradient(colors: [.red.opacity(0.35), .green.opacity(0.35)], startPoint: .leading, endPoint: .trailing))
                                .frame(height: 6)
                            Circle()
                                .fill(Color.primary)
                                .frame(width: 11, height: 11)
                                .offset(x: max(0, geo.size.width * position - 5.5))
                        }
                        .frame(maxHeight: .infinity)
                    }
                    .frame(height: 12)
                    Text(money(high)).font(.caption.monospacedDigit())
                }
            }
        }
    }
}

struct MacQuoteEarningsStripCard: View {
    let workspace: MacQuoteWorkspace?

    var body: some View {
        let strip = MacQuoteMath.earningsStrip(workspace)
        MacInsightCard(title: "Earnings & revisions", systemImage: "calendar.badge.clock") {
            LazyVGrid(columns: statColumns, alignment: .leading, spacing: 10) {
                MacStatTile(
                    label: "Next earnings",
                    value: strip.nextDate ?? "—",
                    detail: [strip.nextEstimated ? "est." : nil, strip.days.map { "\($0)d" }].compactMap { $0 }.joined(separator: " · "),
                    compact: true
                )
                MacStatTile(label: "Last surprise", value: strip.lastSurprise.map { String(format: "%+.1f%%", $0) } ?? "—",
                            tone: strip.lastSurprise.map { $0 >= 0 ? .green : .red }, compact: true)
                MacStatTile(label: "Next EPS cons.", value: strip.consensus.map { String(format: "%.2f", $0) } ?? "—", compact: true)
                MacStatTile(label: "Estimate revisions",
                            value: "+\(Int(strip.revisionsUp ?? 0)) / −\(Int(strip.revisionsDown ?? 0))", compact: true)
                MacStatTile(label: "Avg surprise", value: strip.avgSurprise.map { String(format: "%+.1f%%", $0) } ?? "—",
                            tone: strip.avgSurprise.map { $0 >= 0 ? .green : .red }, compact: true)
            }
        }
    }
}

// MARK: - All stats

struct MacQuoteAllStatsCard: View {
    let payload: MacChartPayload?
    let workspace: MacQuoteWorkspace?
    @AppStorage("mac.quote.allStats") private var showAll = false

    var body: some View {
        let summary = workspace?.summary
        let stats: [(String, String)] = [
            ("Previous close", payload?.previousClose.map(money) ?? summary?.previousClose ?? "—"),
            ("Open", money(payload?.open)),
            ("Day high", money(payload?.high)),
            ("Day low", money(payload?.low)),
            ("Volume", payload?.volume.map { MacNumber.compact($0, currency: false) } ?? MacNumber.compactString(summary?.volume).replacingOccurrences(of: "$", with: "")),
            ("Avg. volume", payload?.avgVolume.map { MacNumber.compact($0, currency: false) } ?? MacNumber.compactString(summary?.avgVolume).replacingOccurrences(of: "$", with: "")),
            ("Market cap", payload?.marketCap.map { MacNumber.compact($0) } ?? MacNumber.compactString(summary?.marketCap)),
            ("P/E (TTM)", payload?.peRatio.map { String(format: "%.2f", $0) } ?? "—"),
            ("EPS (TTM)", payload?.eps.map { String(format: "%.2f", $0) } ?? "—"),
            ("Beta", payload?.beta.map { String(format: "%.2f", $0) } ?? summary?.beta ?? "—"),
            ("Dividend", summary?.dividend ?? "—"),
            ("Yield", summary?.yield ?? payload?.dividendYield.map { String(format: "%.2f%%", $0) } ?? "—"),
            ("Ex-dividend", summary?.exDividend ?? "—"),
            ("52-week range", {
                if let lo = payload?.fiftyTwoWeekLow, let hi = payload?.fiftyTwoWeekHigh { return "\(money(lo)) – \(money(hi))" }
                return summary?.fiftyTwoWeek ?? "—"
            }()),
            ("Next earnings", workspace?.earnings?.nextDate.map { $0 + ((workspace?.earnings?.nextEstimated ?? false) ? " est." : "") } ?? "—"),
        ]
        let visible = showAll ? stats : Array(stats.prefix(9))

        MacInsightCard(title: "Key statistics", systemImage: "list.number") {
            Button(showAll ? "Fewer stats" : "All stats") {
                withAnimation(.easeInOut(duration: 0.2)) { showAll.toggle() }
            }
            .controlSize(.small)
        } content: {
            LazyVGrid(columns: statColumns, alignment: .leading, spacing: 10) {
                ForEach(visible, id: \.0) { stat in
                    MacStatTile(label: stat.0, value: stat.1, compact: true)
                }
            }
        }
    }
}

// MARK: - Workspace tabs

struct MacQuoteWorkspaceCard: View {
    enum Tab: String, CaseIterable {
        case profile = "Profile", statistics = "Statistics", financials = "Financials", analysis = "Analysis"
        case holders = "Holders", options = "Options", history = "Historical", earnings = "Earnings"
    }

    let ticker: String
    let workspace: MacQuoteWorkspace?
    let points: [MacChartPoint]
    let range: MacChartRange
    let lastPrice: Double?
    @AppStorage("mac.quote.workspaceTab") private var tabRaw = Tab.profile.rawValue

    var body: some View {
        let tab = Tab(rawValue: tabRaw) ?? .profile
        MacInsightCard(title: "Quote workspace", systemImage: "square.grid.2x2") {
            VStack(alignment: .leading, spacing: 14) {
                GlassSegmentedPicker("Workspace", selection: $tabRaw, options: Tab.allCases.map(\.rawValue), title: { $0 })
                    .controlSize(.small)
                if workspace == nil {
                    HStack { ProgressView().controlSize(.small); Text("Loading…").foregroundStyle(.secondary) }
                } else {
                    switch tab {
                    case .profile: profile
                    case .statistics: statistics
                    case .financials: financials
                    case .analysis: analysis
                    case .holders: holders
                    case .options: options
                    case .history: history
                    case .earnings: earnings
                    }
                }
            }
        }
    }

    private func grid(_ items: [(String, String)]) -> some View {
        LazyVGrid(columns: statColumns, alignment: .leading, spacing: 10) {
            ForEach(items, id: \.0) { MacStatTile(label: $0.0, value: $0.1, compact: true) }
        }
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text.uppercased()).font(.caption2.weight(.semibold)).tracking(0.5).foregroundStyle(.secondary)
    }

    @ViewBuilder private var profile: some View {
        let p = workspace?.profile
        let s = workspace?.summary
        Text(p?.description?.isEmpty == false ? p!.description! : "No company profile for this symbol.")
            .font(.callout)
            .foregroundStyle(p?.description?.isEmpty == false ? .primary : .secondary)
            .textSelection(.enabled)
        grid([
            ("Sector", p?.sector ?? s?.sector ?? "—"),
            ("Industry", p?.industry ?? s?.industry ?? "—"),
            ("Region", p?.region ?? "—"),
            ("Website", p?.website ?? "—"),
        ])
        if let site = p?.website, let url = URL(string: site) {
            Link(destination: url) { Label("Open website", systemImage: "safari") }.font(.caption)
        }
    }

    @ViewBuilder private var statistics: some View {
        let s = workspace?.summary
        let p = workspace?.profile
        grid([
            ("1y target", s?.oneYearTarget ?? "—"), ("Bid", s?.bid ?? "—"), ("Ask", s?.ask ?? "—"),
            ("Dividend", s?.dividend ?? "—"), ("Ex-dividend", s?.exDividend ?? "—"), ("Beta", s?.beta ?? "—"),
            ("Alpha", s?.alpha ?? "—"), ("AUM", s?.aum ?? "—"), ("Expense ratio", s?.expenseRatio ?? "—"),
            ("Sector", s?.sector ?? p?.sector ?? "—"), ("Industry", s?.industry ?? p?.industry ?? "—"), ("Yield", s?.yield ?? "—"),
        ])
    }

    @ViewBuilder private var financials: some View {
        let lines = MacQuoteMath.faLite(workspace?.financials)
        if !lines.isEmpty {
            HStack { sectionLabel("FA lite"); Spacer(); Text("YoY").font(.caption2).foregroundStyle(.secondary) }
            LazyVGrid(columns: statColumns, alignment: .leading, spacing: 10) {
                ForEach(lines) { line in
                    MacStatTile(label: line.label, value: line.latestRaw, detail: line.yoy.map { String(format: "%+.1f%% YoY", $0) }, compact: true)
                }
            }
        }
        let sheets: [(String, MacFinTable?)] = [
            ("Income statement", workspace?.financials?.income),
            ("Balance sheet", workspace?.financials?.balance),
            ("Cash flow", workspace?.financials?.cashflow),
            ("Financial ratios", workspace?.financials?.ratios),
        ]
        ForEach(sheets, id: \.0) { sheet in
            sectionLabel(sheet.0)
            if let table = sheet.1, !table.rows.isEmpty {
                MacFinTableView(table: table)
            } else {
                Text("No financial statements for this symbol.").font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private var analysis: some View {
        let a = workspace?.analysis
        grid([
            ("1y target", money(a?.target)), ("Target low", money(a?.targetLow)), ("Target high", money(a?.targetHigh)),
            ("Buy", "\(a?.buy ?? 0)"), ("Hold", "\(a?.hold ?? 0)"), ("Sell", "\(a?.sell ?? 0)"),
        ])
        let total = (a?.buy ?? 0) + (a?.hold ?? 0) + (a?.sell ?? 0)
        if total > 0, let a {
            VStack(alignment: .leading, spacing: 4) {
                Text("\(total) analyst ratings").font(.footnote).foregroundStyle(.secondary)
                GeometryReader { geo in
                    HStack(spacing: 2) {
                        Rectangle().fill(Color.green.opacity(0.7)).frame(width: geo.size.width * CGFloat(a.buy) / CGFloat(total))
                        Rectangle().fill(Color.orange.opacity(0.7)).frame(width: geo.size.width * CGFloat(a.hold) / CGFloat(total))
                        Rectangle().fill(Color.red.opacity(0.7))
                    }
                    .clipShape(Capsule())
                }
                .frame(height: 6)
            }
        }
        MacSimpleTable(
            headers: ["Period", "EPS", "High", "Low", "Est."],
            rows: (a?.quarterly ?? []).map { row in
                [row.period, row.consensus.map { String(format: "%.2f", $0) } ?? "—", row.high.map { String(format: "%.2f", $0) } ?? "—",
                 row.low.map { String(format: "%.2f", $0) } ?? "—", row.estimates.map { String(format: "%.0f", $0) } ?? "—"]
            }
        )
    }

    @ViewBuilder private var holders: some View {
        let h = workspace?.holders
        grid([("Inst. ownership", h?.ownershipPct ?? "—"), ("Shares out", h?.sharesOut ?? "—"), ("Holdings value", h?.holdingsValue ?? "—")])
        let movers = MacQuoteMath.ownershipMovers(h)
        if !movers.buyers.isEmpty || !movers.sellers.isEmpty {
            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 4) {
                    sectionLabel("Top increases")
                    ForEach(movers.buyers) { row in
                        HStack { Text(row.owner).font(.footnote); Text(row.changePct ?? "—").font(.footnote.monospacedDigit()).foregroundStyle(.green) }
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    sectionLabel("Top decreases")
                    ForEach(movers.sellers) { row in
                        HStack { Text(row.owner).font(.footnote); Text(row.changePct ?? "—").font(.footnote.monospacedDigit()).foregroundStyle(.red) }
                    }
                }
            }
        }
        MacSimpleTable(headers: ["Holder", "Shares", "Change", "Value"],
                       rows: (h?.holders ?? []).map { [$0.owner, $0.shares ?? "—", $0.changePct ?? "—", $0.value ?? "—"] })
        if let insiders = workspace?.insiders {
            if !insiders.summary.isEmpty {
                MacSimpleTable(headers: ["Insider activity", "3 mo", "12 mo"],
                               rows: insiders.summary.map { [$0.label, $0.months3 ?? "—", $0.months12 ?? "—"] })
            }
            if !insiders.recent.isEmpty {
                sectionLabel("Recent insider trades")
                MacSimpleTable(headers: ["Insider", "Relation", "Date", "Type", "Shares", "Price", "Held"],
                               rows: insiders.recent.map { [$0.insider, $0.relation ?? "—", $0.lastDate ?? "—", $0.transactionType ?? "—", $0.sharesTraded ?? "—", $0.lastPrice ?? "—", $0.sharesHeld ?? "—"] })
            }
        }
    }

    @ViewBuilder private var options: some View {
        let rows = workspace?.options?.rows ?? []
        if let move = MacQuoteMath.expectedMove(rows, spot: lastPrice) {
            HStack(spacing: 8) {
                sectionLabel("Expected move")
                Text(String(format: "±%.1f%%", move.movePct)).font(.callout.monospacedDigit().weight(.semibold))
                Text("to \(move.expiry) (\(move.days)d) · straddle \(money(move.moveUsd)) at \(String(format: "%.2f", move.strike))")
                    .font(.caption).foregroundStyle(.secondary)
                if let next = workspace?.earnings?.nextDate, let nextDate = MacQuoteMath.expiryDate(next), nextDate <= move.expiryDate {
                    Text("EARNINGS INSIDE").font(.caption2.weight(.bold)).foregroundStyle(.orange)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(Color.orange.opacity(0.15)))
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .appleGlassTile()
        }
        if let snap = MacQuoteMath.optionsSnapshot(rows, spot: lastPrice) {
            grid([
                ("Nearest expiry", snap.nearestExpiry ?? "—"),
                ("ATM strike", snap.atmStrike.map { String(format: "%.2f", $0) } ?? "—"),
                ("Put/call vol", snap.putCallVolume.map { String(format: "%.2f", $0) } ?? "—"),
                ("Put/call OI", snap.putCallOi.map { String(format: "%.2f", $0) } ?? "—"),
                ("Call volume", MacNumber.compact(snap.callVolume, currency: false)),
                ("Put volume", MacNumber.compact(snap.putVolume, currency: false)),
            ])
        }
        if rows.isEmpty {
            Text("No option chain for this symbol.").font(.callout).foregroundStyle(.secondary)
        } else {
            if let lastTrade = workspace?.options?.lastTrade { Text(lastTrade).font(.caption2).foregroundStyle(.secondary) }
            MacSimpleTable(headers: ["Expiry", "Call", "Strike", "Put", "Volume"],
                           rows: rows.map { [$0.expiry, $0.callLast ?? "—", $0.strike.map { String(format: "%.2f", $0) } ?? "—", $0.putLast ?? "—", "\($0.callVolume ?? "—") / \($0.putVolume ?? "—")"] })
        }
    }

    private func cell(_ v: Double?) -> String { v.map { String(format: "%.2f", $0) } ?? "—" }

    @ViewBuilder private var history: some View {
        let recent = Array(points.suffix(80).reversed())
        MacSimpleTable(headers: ["Date", "Open", "High", "Low", "Price", "Volume"],
                       rows: recent.map { p in
                           [MacChartFormat.stamp(p.t, range: range), cell(p.open), cell(p.high), cell(p.low), cell(p.close),
                            p.volume.map { MacNumber.compact($0, currency: false) } ?? "—"]
                       })
    }

    @ViewBuilder private var earnings: some View {
        let e = workspace?.earnings
        grid([("Next earnings", (e?.nextDate ?? "—") + ((e?.nextEstimated ?? false) ? " est." : ""))])
        if let past = e?.past, !past.isEmpty {
            MacSimpleTable(headers: ["Period", "Date", "EPS", "Est.", "Surprise"],
                           rows: past.map { [$0.period, $0.reported ?? "—", $0.eps.map { String(format: "%.2f", $0) } ?? "—",
                                             $0.estimate.map { String(format: "%.2f", $0) } ?? "—", $0.surprisePct.map { String(format: "%+.1f%%", $0) } ?? "—"] })
        } else {
            Text("No earnings history for this symbol.").font(.callout).foregroundStyle(.secondary)
        }
    }
}

/// A Nasdaq statement table: labels down the left, one column per period, section rows in bold.
private struct MacFinTableView: View {
    let table: MacFinTable

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            Grid(alignment: .trailing, horizontalSpacing: 18, verticalSpacing: 5) {
                GridRow {
                    Text("").gridColumnAlignment(.leading)
                    ForEach(Array(table.headers.enumerated()), id: \.offset) { _, header in
                        Text(header).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    }
                }
                Divider().gridCellUnsizedAxes(.horizontal)
                ForEach(table.rows) { row in
                    GridRow {
                        Text(row.label)
                            .font(row.section ? .caption.weight(.bold) : .caption)
                            .foregroundStyle(row.section ? .primary : .secondary)
                            .frame(minWidth: 200, alignment: .leading)
                        ForEach(0..<table.headers.count, id: \.self) { index in
                            Text(index < row.values.count && !row.values[index].isEmpty ? row.values[index] : (row.section ? "" : "—"))
                                .font(.caption.monospacedDigit())
                        }
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }
}

/// A plain data table with a header row; first column left-aligned, the rest right-aligned.
struct MacSimpleTable: View {
    let headers: [String]
    let rows: [[String]]

    var body: some View {
        if !rows.isEmpty {
            ScrollView(.horizontal, showsIndicators: true) {
                Grid(alignment: .trailing, horizontalSpacing: 16, verticalSpacing: 5) {
                    GridRow {
                        ForEach(Array(headers.enumerated()), id: \.offset) { index, header in
                            Text(header).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                .gridColumnAlignment(index == 0 ? .leading : .trailing)
                        }
                    }
                    Divider().gridCellUnsizedAxes(.horizontal)
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        GridRow {
                            ForEach(Array(row.enumerated()), id: \.offset) { index, value in
                                Text(value)
                                    .font(index == 0 ? .caption : .caption.monospacedDigit())
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }
}

// MARK: - COMP · Relative value

struct MacQuoteCompCard: View {
    let peers: MacQuotePeers?
    let onSelect: (String) -> Void
    @AppStorage("mac.quote.compMore") private var showMore = false

    var body: some View {
        MacInsightCard(title: "COMP · Relative value", systemImage: "chart.bar.doc.horizontal") {
            Button(showMore ? "Less" : "More") { showMore.toggle() }.controlSize(.small)
        } content: {
            if let peers, let primary = peers.primary {
                let rows = [primary] + peers.peers + (peers.benchmark.map { [$0] } ?? [])
                let bench = peers.benchmark?.points ?? []
                ScrollView(.horizontal, showsIndicators: true) {
                    Grid(alignment: .trailing, horizontalSpacing: 14, verticalSpacing: 7) {
                        GridRow {
                            header("Symbol").gridColumnAlignment(.leading)
                            header("1Y")
                            header("Price")
                            header("1Y %")
                            header("vs SPY 1Y")
                            header("β 60d")
                            header("ρ 60d")
                            if showMore {
                                header("Rev growth"); header("Gross mgn"); header("Op mgn"); header("P/E")
                            }
                            header("Max DD")
                            header("Mkt cap")
                        }
                        Divider().gridCellUnsizedAxes(.horizontal)
                        ForEach(rows) { row in
                            let stats = MacQuoteMath.betaAndCorrelation(row.points, bench)
                            GridRow {
                                Button {
                                    onSelect(row.ticker)
                                } label: {
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(row.ticker).font(.caption.monospacedDigit().weight(row.ticker == primary.ticker ? .heavy : .bold))
                                        if let name = row.name { Text(name).font(.caption2).foregroundStyle(.secondary).lineLimit(1).frame(maxWidth: 140, alignment: .leading) }
                                    }
                                }
                                .buttonStyle(.plain)
                                .help("Open \(row.ticker)")
                                MacSparkline(values: row.spark.isEmpty ? row.points.compactMap(\.close) : row.spark)
                                    .frame(width: 72, height: 22)
                                Text(money(row.last)).font(.caption.monospacedDigit())
                                pctText(row.ret1y, digits: 1).font(.caption.monospacedDigit())
                                pctText(row.vsSpy1y, digits: 1).font(.caption.monospacedDigit())
                                Text(stats.beta.map { String(format: "%.2f", $0) } ?? "—").font(.caption.monospacedDigit())
                                Text(stats.corr.map { String(format: "%.2f", $0) } ?? "—").font(.caption.monospacedDigit())
                                if showMore {
                                    Text(row.revenueGrowth.map { String(format: "%.1f%%", $0) } ?? "—").font(.caption.monospacedDigit())
                                    Text(row.grossMargin.map { String(format: "%.1f%%", $0) } ?? "—").font(.caption.monospacedDigit())
                                    Text(row.operatingMargin.map { String(format: "%.1f%%", $0) } ?? "—").font(.caption.monospacedDigit())
                                    Text(row.peRatio.map { String(format: "%.1f", $0) } ?? "—").font(.caption.monospacedDigit())
                                }
                                Text(row.drawdown1y.map { String(format: "%.1f%%", $0) } ?? "—").font(.caption.monospacedDigit()).foregroundStyle(.red)
                                Text(row.marketCap.map { MacNumber.compact($0) } ?? "—").font(.caption.monospacedDigit())
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
                Text("β and ρ from 60 daily returns vs \(peers.benchmark?.ticker ?? "SPY").").font(.caption2).foregroundStyle(.secondary)
            } else {
                HStack { ProgressView().controlSize(.small); Text("Loading peers…").foregroundStyle(.secondary) }
            }
        }
    }

    private func header(_ text: String) -> some View {
        Text(text).font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
    }
}

struct MacSparkline: View {
    let values: [Double]

    var body: some View {
        let up = (values.last ?? 0) >= (values.first ?? 0)
        Chart(Array(values.enumerated()), id: \.offset) { index, value in
            LineMark(x: .value("i", index), y: .value("v", value))
                .foregroundStyle(up ? Color.green : Color.red)
                .lineStyle(StrokeStyle(lineWidth: 1.25))
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartYScale(domain: (values.min() ?? 0)...(max(values.max() ?? 1, (values.min() ?? 0) + 0.0001)))
    }
}

// MARK: - Calendar, filings, note & actions

struct MacQuoteCalendarCard: View {
    let ticker: String
    let events: [MacCalendarEvent]
    @State private var filter = "all"

    var body: some View {
        let symbol = ticker.uppercased()
        let relevant = events.filter { ($0.ticker?.uppercased() == symbol) || $0.kind == "macro" }
        let shown = relevant.filter { filter == "all" || $0.kind == filter }.prefix(12)
        MacInsightCard(title: "EVTS · Calendar", systemImage: "calendar") {
            VStack(alignment: .leading, spacing: 10) {
                GlassSegmentedPicker("Filter", selection: $filter, segments: ["all": "All", "earnings": "Earnings", "dividends": "Dividends", "macro": "Macro"])
                    .controlSize(.small)
                    .frame(maxWidth: 360)
                if shown.isEmpty {
                    Text("No events in this filter.").font(.callout).foregroundStyle(.secondary)
                } else {
                    ForEach(Array(shown)) { event in
                        HStack(spacing: 10) {
                            Text(event.date).font(.caption.monospacedDigit()).frame(width: 84, alignment: .leading)
                            Text(event.kind.capitalized)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(event.kind == "earnings" ? .orange : (event.kind == "macro" ? .secondary : .accentColor))
                                .frame(width: 70, alignment: .leading)
                            Text(event.title).font(.caption).lineLimit(1)
                            Spacer()
                            if let time = event.time, !time.isEmpty { Text(time).font(.caption2).foregroundStyle(.secondary) }
                            if !event.confirmed { Text("unconfirmed").font(.caption2).foregroundStyle(.tertiary) }
                        }
                    }
                }
            }
        }
    }
}

struct MacQuoteFilingsCard: View {
    let ticker: String
    let news: [MacNewsItem]

    var body: some View {
        let symbol = ticker.uppercased()
        let filings = news.filter { ($0.ticker?.uppercased() == symbol) && (($0.category ?? $0.kind ?? "").lowercased().contains("filing")) }.prefix(5)
        let edgar = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=\(symbol)"
        MacInsightCard(title: "Filings & transcripts", systemImage: "doc.text") {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 12) {
                    ForEach([("EDGAR", ""), ("10-K", "10-K"), ("10-Q", "10-Q"), ("8-K", "8-K")], id: \.0) { item in
                        if let url = URL(string: edgar + (item.1.isEmpty ? "" : "&type=\(item.1)")) {
                            Link(item.0, destination: url).font(.caption.weight(.semibold))
                        }
                    }
                }
                if filings.isEmpty {
                    Text("No filing headlines in the desk feed — use EDGAR links above.").font(.callout).foregroundStyle(.secondary)
                } else {
                    ForEach(Array(filings)) { item in
                        VStack(alignment: .leading, spacing: 2) {
                            if let link = item.url, let url = URL(string: link) {
                                Link(item.title, destination: url).font(.callout)
                            } else {
                                Text(item.title).font(.callout)
                            }
                            if let summary = item.summary { Text(summary).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        }
                    }
                }
            }
        }
    }
}

struct MacQuoteNoteAndActionsCard: View {
    let ticker: String
    let payload: MacChartPayload?
    let peers: MacQuotePeers?
    @EnvironmentObject private var store: MacAppStore
    @State private var note = ""
    @State private var logStatus: String?

    private var noteKey: String { "mac.tickerNote.\(ticker.uppercased())" }

    var body: some View {
        MacInsightCard(title: "Desk note & calls", systemImage: "note.text") {
            VStack(alignment: .leading, spacing: 10) {
                TextEditor(text: $note)
                    .font(.callout)
                    .frame(minHeight: 60, maxHeight: 110)
                    .scrollContentBackground(.hidden)
                    .padding(6)
                    .appleGlassTile()
                    .overlay(alignment: .topLeading) {
                        if note.isEmpty {
                            Text("Desk note for this symbol…").font(.callout).foregroundStyle(.tertiary).padding(11).allowsHitTesting(false)
                        }
                    }
                    .onChange(of: note) { _, value in UserDefaults.standard.set(value, forKey: noteKey) }
                HStack(spacing: 8) {
                    Text("Log call").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Button { logCall("bullish") } label: { Label("Bullish", systemImage: "arrow.up.right") }
                        .tint(.green)
                    Button { logCall("bearish") } label: { Label("Bearish", systemImage: "arrow.down.right") }
                        .tint(.red)
                    if let logStatus { Text(logStatus).font(.caption).foregroundStyle(.secondary) }
                    Spacer()
                    Button { askWhyMoving() } label: { Label("Why is this moving?", systemImage: "sparkles") }
                        .disabled(!store.canRunTasks)
                    if let company = store.companies.first(where: { $0.ticker?.uppercased() == ticker.uppercased() }) {
                        Button { store.showCompany(company) } label: { Label("Open Company", systemImage: "building.2") }
                    }
                }
                .controlSize(.small)
                .disabled(false)
            }
        }
        .onAppear { note = UserDefaults.standard.string(forKey: noteKey) ?? "" }
        .onChange(of: ticker) { _, _ in
            note = UserDefaults.standard.string(forKey: noteKey) ?? ""
            logStatus = nil
        }
    }

    private func logCall(_ direction: String) {
        let symbol = ticker.uppercased()
        Task {
            let ok = await store.logSignal(ticker: symbol, direction: direction, label: "Market desk \(direction) call")
            logStatus = ok ? "Logged \(symbol)" : "Could not log \(symbol)"
        }
    }

    /// The web desk's prompt: headlines, the session gap, the return ladder and the desk note.
    private func askWhyMoving() {
        let symbol = ticker.uppercased()
        var lines = ["Why is \(symbol) moving? Explain the move using the context below, then say what would change the view."]
        if let payload {
            let last = payload.lastPrice ?? payload.points?.last?.close
            let gap = MacQuoteMath.gapSplit(open: payload.open, previousClose: payload.previousClose, last: last)
            if let pct = payload.changePct { lines.append(String(format: "Today: %+.2f%%", pct)) }
            if let g = gap.gap { lines.append(String(format: "Overnight gap: %+.2f%%, open→last: %+.2f%%", g, gap.session ?? 0)) }
        }
        if let primary = peers?.primary {
            let parts = [("1M", primary.ret1m), ("YTD", primary.retYtd), ("1Y", primary.ret1y), ("vs SPY 1Y", primary.vsSpy1y)]
                .compactMap { label, value in value.map { String(format: "%@ %+.1f%%", label, $0) } }
            if !parts.isEmpty { lines.append("Returns: " + parts.joined(separator: ", ")) }
        }
        let headlines = store.news.filter { $0.ticker?.uppercased() == symbol }.prefix(6).map { "- \($0.title)" }
        if !headlines.isEmpty { lines.append("Recent headlines:\n" + headlines.joined(separator: "\n")) }
        if !note.isEmpty { lines.append("Desk note: \(note)") }
        let company = store.companies.first { $0.ticker?.uppercased() == symbol }
        store.askWarren(lines.joined(separator: "\n"), context: .market(ticker: symbol), company: company)
    }
}
