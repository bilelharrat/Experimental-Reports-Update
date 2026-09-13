import Charts
import SwiftUI

struct MacMarketRadarView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var radarTab: RadarTab = .watchlist
    @State private var newTickerSearch = ""
    @State private var showAddLotSheet = false
    @State private var showAddAlertSheet = false

    enum RadarTab: String, CaseIterable, Identifiable {
        case watchlist = "Watchlist"
        case gainers = "Gainers"
        case losers = "Losers"
        var id: String { rawValue }
    }

    private var activeQuotes: [MacQuote] {
        switch radarTab {
        case .watchlist: return store.watchlist
        case .gainers: return store.gainers
        case .losers: return store.losers
        }
    }

    var body: some View {
        HSplitView {
            // Left Pane: Quotes Radar & Screeners
            VStack(spacing: 0) {
                // Section Picker
                Picker("Radar", selection: $radarTab) {
                    ForEach(RadarTab.allCases) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding(10)
                .background(.ultraThinMaterial)

                Divider()

                // Add to Watchlist quick bar (when on watchlist tab)
                if radarTab == .watchlist {
                    HStack(spacing: 6) {
                        Image(systemName: "plus.magnifyingglass")
                            .foregroundStyle(.secondary)
                        TextField("Pin ticker (e.g. MSFT)…", text: $newTickerSearch)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                let t = newTickerSearch.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                                guard !t.isEmpty else { return }
                                Task {
                                    await store.toggleWatchlist(t)
                                    newTickerSearch = ""
                                }
                            }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                    .padding(8)

                    Divider()
                }

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
                            .buttonStyle(.plain)
                            .help(store.isPinned(q.ticker) ? "Unpin from desk" : "Pin to desk (syncs with web/iPad)")

                            VStack(alignment: .leading, spacing: 2) {
                                Text(q.ticker)
                                    .font(.body.monospaced().weight(.bold))
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
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            }
            .frame(minWidth: 260, idealWidth: 300, maxWidth: 360)

            // Right Pane: Chart, Statistics, Book Lots & Alert Rules
            if let ticker = store.selectedTicker {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Ticker Header
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 10) {
                                    Text(ticker)
                                        .font(.system(size: 28, weight: .bold, design: .monospaced))

                                    Button {
                                        Task { await store.toggleWatchlist(ticker) }
                                    } label: {
                                        Image(systemName: store.isPinned(ticker) ? "star.fill" : "star")
                                            .font(.title2)
                                            .foregroundStyle(store.isPinned(ticker) ? Color.yellow : Color.secondary)
                                    }
                                    .buttonStyle(.plain)
                                    .help("Pin to desk")

                                    if let name = store.selectedChart?.name ?? store.selectedWorkspace?.summary?.name {
                                        Text(name)
                                            .font(.headline)
                                            .foregroundStyle(.secondary)
                                    }
                                }

                                if let exchange = store.selectedChart?.exchange ?? store.selectedWorkspace?.summary?.exchange {
                                    Text(exchange)
                                        .font(.caption.monospaced())
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
                                    Label("Open on Web", systemImage: "safari")
                                }
                                .buttonStyle(.bordered)
                                .help("Open quote workspace on Web")

                                Button {
                                    store.sendCopilotMessage(prompt: "Provide an investment breakdown for \(ticker).")
                                } label: {
                                    Label("Ask Warren", systemImage: "bubble.left.and.bubble.right.fill")
                                }
                                .buttonStyle(.borderedProminent)
                            }
                        }
                        .padding()
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))

                        // Interactive Chart Canvas
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Price Action")
                                    .font(.headline)
                                Spacer()

                                // Range Selector
                                Picker("Timeframe", selection: Binding(
                                    get: { store.selectedChartRange },
                                    set: { newRange in
                                        Task { await store.loadChart(range: newRange) }
                                    }
                                )) {
                                    ForEach(MacChartRange.allCases) { r in
                                        Text(r.rawValue).tag(r)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .frame(width: 260)
                            }

                            if store.loadingChart {
                                ProgressView()
                                    .frame(height: 220)
                                    .frame(maxWidth: .infinity)
                            } else if let points = store.selectedChart?.points, points.count > 1 {
                                MacQuoteChartCanvas(
                                    points: points,
                                    previousClose: store.selectedChart?.previousClose,
                                    range: store.selectedChartRange
                                )
                                .frame(height: 220)
                            } else {
                                ContentUnavailableView("No Chart Data Available", systemImage: "chart.line.uptrend.xyaxis")
                                    .frame(height: 220)
                            }
                        }
                        .padding()
                        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))

                        // Key Statistics Grid
                        if let sum = store.selectedWorkspace?.summary {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Key Financial Statistics")
                                    .font(.headline)

                                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                                    StatBox(label: "Market Cap", value: formatLargeNumber(sum.marketCap))
                                    StatBox(label: "P/E Ratio", value: sum.peRatio != nil ? String(format: "%.1fx", sum.peRatio!) : "—")
                                    StatBox(label: "Volume", value: sum.volume != nil ? formatLargeNumber(sum.volume) : "—")
                                    StatBox(label: "52-Week High", value: sum.high52w != nil ? String(format: "$%.2f", sum.high52w!) : "—")
                                    StatBox(label: "52-Week Low", value: sum.low52w != nil ? String(format: "$%.2f", sum.low52w!) : "—")
                                    StatBox(label: "Current Price", value: sum.price != nil ? String(format: "$%.2f", sum.price!) : "—")
                                }
                            }
                            .padding()
                            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                        }

                        // Portfolio Lots Tracker (Synced with Web & iPad)
                        let matchingLots = store.bookLots.filter { $0.ticker == ticker }
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: 6) {
                                        Text("Portfolio Lots")
                                            .font(.headline)
                                        Image(systemName: "arrow.triangle.2.circlepath")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                            .help("Synced across Web, iPadOS, and macOS via /api/desk/prefs")
                                    }
                                    Text("Shared live with web and iPad book")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }

                                Spacer()

                                Button {
                                    showAddLotSheet = true
                                } label: {
                                    Label("Add Lot", systemImage: "plus")
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
                                    let curPrice = store.selectedWorkspace?.summary?.price ?? store.selectedChart?.points?.last?.close ?? lot.costBasis
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
                                            Text(String(format: "%+$%.2f", gain))
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
                                        .padding(.leading, 8)
                                    }
                                    .padding(8)
                                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                                }
                            }
                        }
                        .padding()
                        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))

                        // Price Alerts Manager
                        let matchingAlerts = store.alertRules.filter { $0.ticker == ticker }
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Price Alerts")
                                    .font(.headline)
                                Spacer()
                                Button {
                                    showAddAlertSheet = true
                                } label: {
                                    Label("New Alert", systemImage: "bell.badge.plus")
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }

                            if matchingAlerts.isEmpty {
                                Text("No price alerts set for \(ticker).")
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
                                            Text(String(format: "%@ when price %@ $%.2f", rule.ticker, rule.direction, rule.threshold))
                                                .font(.body.monospacedDigit())
                                        }

                                        Spacer()

                                        Button {
                                            Task { await store.deleteAlertRule(id: rule.id) }
                                        } label: {
                                            Image(systemName: "trash")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                    .padding(8)
                                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                                }
                            }
                        }
                        .padding()
                        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                    }
                    .padding(20)
                }
            } else {
                ContentUnavailableView("Select a Ticker", systemImage: "chart.bar.xaxis", description: Text("Select a quote from the radar list to view live charts and portfolio positions."))
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

// MARK: - Swift Charts Canvas

struct MacQuoteChartCanvas: View {
    let points: [MacChartPoint]
    let previousClose: Double?
    let range: MacChartRange

    @State private var scrubPoint: MacChartPoint?

    var body: some View {
        let isUp: Bool = {
            if let first = points.first?.close, let last = points.last?.close {
                return last >= first
            }
            return true
        }()
        let lineColor: Color = isUp ? .green : .red

        VStack(alignment: .leading, spacing: 6) {
            // Hover Tooltip Display
            if let p = scrubPoint, let c = p.close {
                HStack(spacing: 8) {
                    Text(String(format: "$%.2f", c))
                        .font(.headline.monospacedDigit().weight(.bold))
                    Text(p.timestamp.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
            } else if let last = points.last?.close {
                Text(String(format: "$%.2f", last))
                    .font(.headline.monospacedDigit().weight(.bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
            }

            Chart {
                ForEach(points) { point in
                    if let close = point.close {
                        LineMark(
                            x: .value("Time", point.timestamp),
                            y: .value("Price", close)
                        )
                        .foregroundStyle(lineColor)
                        .interpolationMethod(.monotone)

                        AreaMark(
                            x: .value("Time", point.timestamp),
                            y: .value("Price", close)
                        )
                        .foregroundStyle(
                            LinearGradient(
                                colors: [lineColor.opacity(0.25), lineColor.opacity(0.01)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                    }
                }

                if let scrub = scrubPoint, let close = scrub.close {
                    RuleMark(x: .value("Time", scrub.timestamp))
                        .foregroundStyle(Color.secondary.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))

                    PointMark(
                        x: .value("Time", scrub.timestamp),
                        y: .value("Price", close)
                    )
                    .foregroundStyle(lineColor)
                    .symbolSize(36)
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic) { _ in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                    AxisValueLabel(format: .dateTime.hour().minute())
                }
            }
            .chartYAxis {
                AxisMarks(position: .trailing) { _ in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                    AxisValueLabel()
                }
            }
            .chartOverlay { proxy in
                GeometryReader { geo in
                    Rectangle()
                        .fill(Color.clear)
                        .contentShape(Rectangle())
                        .onContinuousHover { phase in
                            switch phase {
                            case .active(let location):
                                guard let date: Date = proxy.value(atX: location.x) else { return }
                                let targetTime = date.timeIntervalSince1970
                                scrubPoint = points.min(by: {
                                    abs(TimeInterval($0.t) - targetTime) < abs(TimeInterval($1.t) - targetTime)
                                })
                            case .ended:
                                scrubPoint = nil
                            }
                        }
                }
            }
        }
    }
}

// MARK: - Stat Box

struct StatBox: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body.monospacedDigit().weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
    }
}

// MARK: - Add Book Lot Sheet

struct AddBookLotSheet: View {
    let ticker: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var sharesText = "10"
    @State private var costBasisText = "100.00"

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
                    Text(ticker).font(.body.monospaced().weight(.bold))
                }
                TextField("Shares (Quantity)", text: $sharesText)
                TextField("Cost Basis per Share ($)", text: $costBasisText)
            }
            .formStyle(.grouped)
            .padding()

            Divider()

            HStack {
                Spacer()
                Button("Save Position") {
                    if let sh = Double(sharesText), let cost = Double(costBasisText) {
                        Task {
                            await store.addLot(ticker: ticker, shares: sh, costBasis: cost)
                            dismiss()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 360, height: 260)
    }
}

// MARK: - Add Price Alert Sheet

struct AddPriceAlertSheet: View {
    let ticker: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var direction = "above"
    @State private var thresholdText = "150.00"

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
                    Text(ticker).font(.body.monospaced().weight(.bold))
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
                Spacer()
                Button("Create Alert") {
                    if let th = Double(thresholdText) {
                        Task {
                            await store.addAlertRule(ticker: ticker, threshold: th, direction: direction)
                            dismiss()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 360, height: 260)
    }
}
