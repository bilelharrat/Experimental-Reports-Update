import Charts
import SwiftUI

struct MacMarketRadarView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var radarTab: RadarTab = .watchlist
    @State private var newTickerSearch = ""
    @State private var showAddLotSheet = false
    @State private var showAddAlertSheet = false
    @State private var pinError: String?
    @StateObject private var detail = MacQuoteDetailModel()
    @AppStorage("mac.chart.compareTickers") private var compareTickersRaw = ""

    private var compareTickers: Binding<[String]> {
        Binding(
            get: { compareTickersRaw.split(separator: ",").map(String.init).filter { !$0.isEmpty } },
            set: { compareTickersRaw = $0.joined(separator: ",") }
        )
    }

    /// Earnings prints (E), the next estimated print (E?) and logged calls (S↑ / S↓) on the chart.
    private func chartMarkers(for ticker: String) -> [MacChartMarker] {
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
                markers.append(MacChartMarker(t: t, label: earnings.nextEstimated ? "E?" : "E", kind: .earnings))
            }
        }
        for signal in store.signals where signal.ticker.uppercased() == ticker.uppercased() {
            guard let raw = signal.recordedAt, let date = MacQuoteInsight.parseISO(raw) else { continue }
            let up = signal.direction == "bullish"
            markers.append(MacChartMarker(t: Int(date.timeIntervalSince1970), label: up ? "S↑" : "S↓", kind: up ? .signalUp : .signalDown))
        }
        return markers
    }

    private static let tickerPattern = try! NSRegularExpression(pattern: "^[A-Z0-9][A-Z0-9.\\-]{0,15}$")

    enum RadarTab: String, CaseIterable, Identifiable {
        case watchlist = "Watchlist"
        case gainers = "Gainers"
        case losers = "Losers"
        case filings = "Filings"
        var id: String { rawValue }
    }

    private var activeQuotes: [MacQuote] {
        switch radarTab {
        case .watchlist: return store.watchlist
        case .gainers: return store.gainers
        case .losers: return store.losers
        case .filings: return []
        }
    }

    var body: some View {
        HSplitView {
            // Left Pane: Quotes Radar & Screeners
            VStack(spacing: 0) {
                MacTickerTapeView()
                // Section Picker
                GlassSegmentedPicker("Radar", selection: $radarTab, options: RadarTab.allCases, title: \.rawValue)
                .padding(10)
                .background(.bar)

                Divider()

                // Add to Watchlist quick bar (when on watchlist tab)
                if radarTab == .watchlist {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Image(systemName: "plus.magnifyingglass")
                                .foregroundStyle(.secondary)
                            TextField("Pin ticker (e.g. MSFT)…", text: $newTickerSearch)
                                .textFieldStyle(.plain)
                                .disabled(!store.canWriteDesk)
                                .onSubmit { pinTypedTicker() }
                                .onChange(of: newTickerSearch) { _, _ in pinError = nil }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.dsTile, in: RoundedRectangle(cornerRadius: 7))
                        if let pinError {
                            Text(pinError)
                                .font(.caption)
                                .foregroundStyle(Color.orange)
                                .padding(.horizontal, 4)
                        }
                    }
                    .padding(8)

                    Divider()
                }

                if radarTab == .filings {
                    MacFilingsWatchPane()
                } else {
                // Quotes List
                List(selection: Binding(
                    get: { store.selectedTicker },
                    set: { if let val = $0 { store.selectTicker(val) } }
                )) {
                    ForEach(activeQuotes) { q in
                        HStack(spacing: 8) {
                            Button {
                                Task { await store.toggleWatchlist(q.ticker) }
                            } label: {
                                Image(systemName: store.isPinned(q.ticker) ? "star.fill" : "star")
                                    .foregroundStyle(store.isPinned(q.ticker) ? Color.yellow : Color.secondary)
                                    .font(.caption)
                            }
                            .disabled(!store.canWriteDesk)
                            .buttonStyle(.plain)
                            .help(store.isPinned(q.ticker) ? "Unpin from desk" : "Pin to desk (syncs with web/iPad)")

                            VStack(alignment: .leading, spacing: 2) {
                                Text(q.ticker)
                                    .font(.body.monospacedDigit().weight(.bold))
                                if let name = q.name, !name.isEmpty {
                                    Text(name)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }

                            Spacer()

                            VStack(alignment: .trailing, spacing: 2) {
                                Text(q.priceText)
                                    .font(.body.monospacedDigit().weight(.medium))

                                Text(q.pctText)
                                    .font(.caption.monospacedDigit().weight(.semibold))
                                    .foregroundStyle(q.isUp ? Color.green : Color.red)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background((q.isUp ? Color.green : Color.red).opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            }
                        }
                        .tag(q.ticker)
                        .padding(.vertical, 2)
                        .glassListRow(isSelected: store.selectedTicker == q.ticker)
                    }
                }
                .listStyle(.inset)
                }
            }
            .frame(minWidth: 260, idealWidth: 300, maxWidth: 360)

            // Right Pane: Chart, Statistics, Book Lots & Alert Rules
            if let ticker = store.selectedTicker {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Ticker Header
                        HStack(alignment: .center) {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 10) {
                                    Text(ticker)
                                        .font(.dsTitle)

                                    Button {
                                        Task { await store.toggleWatchlist(ticker) }
                                    } label: {
                                        Image(systemName: store.isPinned(ticker) ? "star.fill" : "star")
                                            .font(.title2)
                                            .foregroundStyle(store.isPinned(ticker) ? Color.yellow : Color.secondary)
                                    }
                                    .buttonStyle(.plain)
                                    .disabled(!store.canWriteDesk)
                                    .help("Pin to desk")

                                    if let name = store.selectedChart?.name ?? store.selectedWorkspace?.profile?.name {
                                        Text(name)
                                            .font(.headline)
                                            .foregroundStyle(.secondary)
                                    }
                                }

                                if let exchange = store.selectedChart?.exchange ?? store.selectedWorkspace?.summary?.exchange {
                                    Text(exchange)
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                            }

                            Spacer()

                            // Action buttons
                            HStack(spacing: 8) {
                                Button {
                                    let url = MacConfig.webQuoteURL(ticker: ticker)
                                    MacConfig.openInBrowser(url)
                                } label: {
                                    Image(systemName: "safari")
                                }
                                .help("Open the quote workspace on the web")

                                Button {
                                    store.openSignalLog(seedTicker: ticker)
                                } label: {
                                    Label("Log signal", systemImage: "flag")
                                }
                                .help("Log a bullish / bearish call on \(ticker) — scored against live prices (⌘L)")

                                Button {
                                    let company = store.companies.first { $0.ticker?.uppercased() == ticker.uppercased() }
                                    store.askWarren("Provide an investment breakdown for \(ticker).", context: .market(ticker: ticker), company: company)
                                } label: {
                                    Label("Ask Warren", systemImage: "bubble.left.and.bubble.right.fill")
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(!store.canRunTasks)
                            }
                        }
                        .padding(.bottom, 4)

                        MacQuotePriceLine(payload: store.selectedChart)

                        // Interactive Chart Canvas
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Price")
                                    .font(.dsHeadline)
                                Spacer()

                                // Range Selector
                                GlassSegmentedPicker("Timeframe", selection: Binding(
                                    get: { store.selectedChartRange },
                                    set: { newRange in
                                        Task { await store.loadChart(range: newRange) }
                                    }
                                ), options: MacChartRange.allCases, title: \.rawValue)
                                .controlSize(.small)
                                .frame(width: 380)
                            }

                            if store.loadingChart && store.selectedChart == nil {
                                ProgressView()
                                    .frame(height: 260)
                                    .frame(maxWidth: .infinity)
                            } else if let payload = store.selectedChart, (payload.points?.count ?? 0) > 1 {
                                MacQuoteChartPanel(
                                    ticker: ticker,
                                    payload: payload,
                                    range: store.selectedChartRange,
                                    markers: chartMarkers(for: ticker),
                                    compare: detail.compareSeries,
                                    peers: detail.peerSeries,
                                    compareTickers: compareTickers
                                )
                                .opacity(store.loadingChart ? 0.5 : 1)
                            } else {
                                ContentUnavailableView(store.chartError ?? "No chart data", systemImage: "chart.line.uptrend.xyaxis")
                                    .frame(height: 260)
                            }
                        }
                        .padding()
                        .appleGlassCard()
                        .task(id: ticker) { await detail.loadDetail(ticker: ticker) }
                        .task(id: "\(compareTickersRaw)|\(store.selectedChartRange.apiValue)") {
                            await detail.loadCompare(tickers: compareTickers.wrappedValue, range: store.selectedChartRange)
                        }

                        if let payload = store.selectedChart {
                            MacQuoteSessionCard(payload: payload, range: store.selectedChartRange, peers: detail.peers)
                        }

                        MacQuoteAllStatsCard(payload: store.selectedChart, workspace: store.selectedWorkspace)

                        MacQuoteEarningsStripCard(workspace: store.selectedWorkspace)

                        MacQuoteWorkspaceCard(
                            ticker: ticker,
                            workspace: store.selectedWorkspace,
                            points: store.selectedChart?.points ?? [],
                            range: store.selectedChartRange,
                            lastPrice: store.selectedChart?.lastPrice ?? store.selectedChart?.points?.last?.close
                        )

                        MacQuoteCompCard(peers: detail.peers) { symbol in
                            store.selectTicker(symbol)
                        }

                        MacQuoteNoteAndActionsCard(ticker: ticker, payload: store.selectedChart, peers: detail.peers)

                        MacQuoteCalendarCard(ticker: ticker, events: detail.calendar)

                        MacQuoteFilingsCard(ticker: ticker, news: store.news)

                        // Portfolio Lots Tracker (Synced with Web & iPad)
                        let matchingLots = store.bookLots.filter { $0.ticker == ticker }
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Book lots")
                                        .font(.dsHeadline)
                                    Text("Shared with the web and iPad desk")
                                        .font(.dsCaption)
                                        .foregroundStyle(.secondary)
                                }

                                Spacer()

                                Button {
                                    showAddLotSheet = true
                                } label: {
                                    Label("Add lot", systemImage: "plus")
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }

                            if matchingLots.isEmpty {
                                Text("No open book lots for \(ticker).")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .padding(.vertical, 8)
                            } else {
                                ForEach(matchingLots) { lot in
                                    let curPrice = store.selectedChart?.points?.last?.close
                                        ?? store.watchlist.first(where: { $0.ticker == ticker })?.last
                                        ?? store.selectedWorkspace?.summary?.previousCloseValue
                                        ?? lot.costBasis
                                    let gain = lot.unrealizedGain(currentPrice: curPrice)
                                    let gainPct = lot.gainPct(currentPrice: curPrice)

                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(String(format: "%.1f shares @ $%.2f", lot.shares, lot.costBasis))
                                                .font(.body.monospacedDigit().weight(.medium))
                                            Text(String(format: "Cost: $%.2f · Equity: $%.2f", lot.totalCost, lot.currentEquity(currentPrice: curPrice)))
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }

                                        Spacer()

                                        VStack(alignment: .trailing, spacing: 2) {
                                            Text((gain >= 0 ? "+$" : "-$") + String(format: "%.2f", abs(gain)))
                                                .font(.body.monospacedDigit().weight(.semibold))
                                                .foregroundStyle(gain >= 0 ? Color.green : Color.red)
                                            Text(String(format: "%+.2f%%", gainPct))
                                                .font(.caption.monospacedDigit())
                                                .foregroundStyle(gain >= 0 ? Color.green : Color.red)
                                        }

                                        Button {
                                            Task { await store.removeLot(id: lot.id) }
                                        } label: {
                                            Image(systemName: "trash")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        .buttonStyle(.plain)
                                        .disabled(!store.canWriteDesk)
                                        .padding(.leading, 8)
                                    }
                                    .padding(8)
                                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                                }
                            }
                        }
                        .padding()
                        .appleGlassCard()

                        // Price Alerts Manager
                        let matchingAlerts = store.alertRules.filter { $0.ticker == ticker }
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Alerts")
                                    .font(.dsHeadline)
                                Spacer()
                                Button {
                                    showAddAlertSheet = true
                                } label: {
                                    Label("New alert", systemImage: "bell.badge")
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }

                            if matchingAlerts.isEmpty {
                                Text("No alerts set for \(ticker).")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .padding(.vertical, 8)
                            } else {
                                ForEach(matchingAlerts) { rule in
                                    HStack {
                                        Toggle(isOn: Binding(
                                            get: { rule.enabled },
                                            set: { _ in Task { await store.toggleAlertRule(id: rule.id) } }
                                        )) {
                                            Text(alertRuleLabel(rule))
                                                .font(.body.monospacedDigit())
                                        }
                                        .disabled(!store.canWriteDesk)

                                        Spacer()

                                        Button {
                                            Task { await store.deleteAlertRule(id: rule.id) }
                                        } label: {
                                            Image(systemName: "trash")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        .buttonStyle(.plain)
                                        .disabled(!store.canWriteDesk)
                                    }
                                    .padding(8)
                                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                                }
                            }
                        }
                        .padding()
                        .appleGlassCard()
                    }
                    .padding(20)
                }
            } else {
                ContentUnavailableView("Select a ticker", systemImage: "chart.bar.xaxis", description: Text("Pick a quote on the left for the chart, key statistics, book lots and price alerts."))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .sheet(isPresented: $showAddLotSheet) {
            if let ticker = store.selectedTicker {
                AddBookLotSheet(ticker: ticker)
                    .environmentObject(store)
            }
        }
        .sheet(isPresented: $showAddAlertSheet) {
            if let ticker = store.selectedTicker {
                AddPriceAlertSheet(ticker: ticker)
                    .environmentObject(store)
            }
        }
    }

    private func pinTypedTicker() {
        let t = newTickerSearch.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !t.isEmpty else { return }
        let range = NSRange(t.startIndex..., in: t)
        guard Self.tickerPattern.firstMatch(in: t, range: range) != nil else {
            pinError = "Not a valid ticker symbol"
            return
        }
        pinError = nil
        Task {
            if !store.isPinned(t) {
                await store.toggleWatchlist(t)
            }
            store.selectTicker(t)
            newTickerSearch = ""
        }
    }

    private func alertRuleLabel(_ rule: MacAlertRule) -> String {
        let t = rule.threshold.formatted(.number.precision(.fractionLength(0...2)))
        switch rule.kind {
        case "price":
            return String(format: "%@ when price %@ $%.2f", rule.ticker, rule.direction == "below" ? "drops below" : "rises above", rule.threshold)
        case "pct":
            return "\(rule.ticker) moves ±\(t)% in a day"
        case "volume":
            return "\(rule.ticker) volume ≥ \(t)× average"
        case "earnings":
            return "\(rule.ticker) earnings within \(Int(rule.threshold)) days"
        case "sma_cross":
            return "\(rule.ticker) crosses \(rule.direction == "below" ? "below" : "above") \(Int(rule.threshold))-day SMA"
        default:
            return "\(rule.ticker) \(rule.kind) \(t)"
        }
    }

    private func formatLargeNumber(_ val: Double?) -> String {
        guard let val else { return "—" }
        if val >= 1_000_000_000_000 {
            return String(format: "$%.2fT", val / 1_000_000_000_000)
        } else if val >= 1_000_000_000 {
            return String(format: "$%.2fB", val / 1_000_000_000)
        } else if val >= 1_000_000 {
            return String(format: "$%.2fM", val / 1_000_000)
        } else {
            return String(format: "$%.0f", val)
        }
    }
}

// MARK: - Stat Box

struct StatBox: View {
    let label: String
    let value: String

    var body: some View {
        MacStatTile(label: label, value: value, compact: true)
    }
}

// MARK: - Add Book Lot Sheet

enum MacSheetNumber {
    static func parse(_ raw: String) -> Double? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        text = text.replacingOccurrences(of: "$", with: "")
        if let grouping = Locale.current.groupingSeparator {
            text = text.replacingOccurrences(of: grouping, with: "")
        }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.isLenient = true
        guard !text.isEmpty, let value = formatter.number(from: text)?.doubleValue, value.isFinite else { return nil }
        return value
    }
}

struct AddBookLotSheet: View {
    let ticker: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var sharesText = "10"
    @State private var costBasisText = "100.00"
    @State private var saving = false
    @State private var errorText: String?

    private var shares: Double? {
        guard let v = MacSheetNumber.parse(sharesText), v > 0 else { return nil }
        return v
    }

    private var costBasis: Double? {
        guard let v = MacSheetNumber.parse(costBasisText), v >= 0 else { return nil }
        return v
    }

    private var validationHint: String? {
        if shares == nil { return "Shares must be a number greater than zero." }
        if costBasis == nil { return "Cost basis must be a number of zero or more." }
        return nil
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Add Portfolio Position")
                    .font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            .background(.ultraThinMaterial)

            Divider()

            Form {
                LabeledContent("Ticker") {
                    Text(ticker).font(.body.monospacedDigit().weight(.bold))
                }
                TextField("Shares (Quantity)", text: $sharesText)
                TextField("Cost Basis per Share ($)", text: $costBasisText)
            }
            .formStyle(.grouped)
            .padding()

            Divider()

            HStack {
                if let message = errorText ?? validationHint {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(errorText == nil ? Color.secondary : Color.orange)
                        .lineLimit(2)
                }
                Spacer()
                if saving { ProgressView().controlSize(.small) }
                Button("Save Position") {
                    guard let sh = shares, let cost = costBasis, !saving else { return }
                    saving = true
                    errorText = nil
                    Task {
                        let ok = await store.addLot(ticker: ticker, shares: sh, costBasis: cost)
                        saving = false
                        if ok {
                            dismiss()
                        } else {
                            errorText = "Could not save to the desk: \(store.error ?? "unknown error")"
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving || validationHint != nil || !store.canWriteDesk)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 400, height: 280)
    }
}

// MARK: - Add Price Alert Sheet

struct AddPriceAlertSheet: View {
    let ticker: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var direction = "above"
    @State private var thresholdText = "150.00"
    @State private var saving = false
    @State private var errorText: String?

    private var threshold: Double? {
        guard let v = MacSheetNumber.parse(thresholdText), v > 0 else { return nil }
        return v
    }

    private var validationHint: String? {
        threshold == nil ? "Price target must be a number greater than zero." : nil
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Add Price Alert")
                    .font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            .background(.ultraThinMaterial)

            Divider()

            Form {
                LabeledContent("Ticker") {
                    Text(ticker).font(.body.monospacedDigit().weight(.bold))
                }
                Picker("Direction", selection: $direction) {
                    Text("Rises Above").tag("above")
                    Text("Drops Below").tag("below")
                }
                TextField("Price Target ($)", text: $thresholdText)
            }
            .formStyle(.grouped)
            .padding()

            Divider()

            HStack {
                if let message = errorText ?? validationHint {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(errorText == nil ? Color.secondary : Color.orange)
                        .lineLimit(2)
                }
                Spacer()
                if saving { ProgressView().controlSize(.small) }
                Button("Create Alert") {
                    guard let th = threshold, !saving else { return }
                    saving = true
                    errorText = nil
                    Task {
                        let ok = await store.addAlertRule(ticker: ticker, threshold: th, direction: direction)
                        saving = false
                        if ok {
                            dismiss()
                        } else {
                            errorText = "Could not save to the desk: \(store.error ?? "unknown error")"
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving || validationHint != nil || !store.canWriteDesk)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 400, height: 280)
    }
}
