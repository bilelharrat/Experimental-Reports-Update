import AppKit
import Charts
import SwiftUI

// The quote chart from the web desk (frontend/src/components/QuoteChart.vue), native:
// hover for a print, drag to measure (change, duration, high/low, Fibonacci), SMA 20/50/200,
// VWAP and ±σ bands, log scale, relative %, compare tickers and peers, earnings and signal
// markers, volume / volume-profile / RSI / drawdown / seasonality panes, expand and CSV export.
//
// Points are plotted by index (no overnight or weekend gaps, like the web and Google).
// Hover and measure state lives in `MacChartInteraction`, observed only by the thin overlay
// layers and the readout, so moving the pointer never rebuilds the chart marks.

struct MacChartMarker: Identifiable {
    enum Kind { case earnings, split, dividend, signalUp, signalDown }
    let id = UUID()
    let t: Int
    let label: String
    let kind: Kind

    var color: Color {
        switch kind {
        case .split: return .red
        case .dividend: return .accentColor
        case .signalUp: return .green
        case .signalDown: return .red
        case .earnings: return .orange
        }
    }
}

struct MacCompareSeries: Identifiable {
    var id: String { ticker }
    let ticker: String
    let points: [MacChartPoint]
}

@MainActor
final class MacChartInteraction: ObservableObject {
    @Published var hoverIndex: Int?
    @Published var anchorIndex: Int?
    @Published var endIndex: Int?
    var isDragging = false

    /// The measured span, lower index first; nil until the drag covers two points.
    var span: (lower: Int, upper: Int)? {
        guard let a = anchorIndex, let e = endIndex, a != e else { return nil }
        return (min(a, e), max(a, e))
    }

    func reset() {
        hoverIndex = nil
        anchorIndex = nil
        endIndex = nil
        isDragging = false
    }
}

struct MacQuoteChartPanel: View {
    let ticker: String
    let payload: MacChartPayload
    let range: MacChartRange
    let markers: [MacChartMarker]
    let compare: [MacCompareSeries]
    let peers: [MacCompareSeries]
    @Binding var compareTickers: [String]

    @AppStorage("mac.chart.sma20") private var showSMA20 = true
    @AppStorage("mac.chart.sma50") private var showSMA50 = true
    @AppStorage("mac.chart.sma200") private var showSMA200 = false
    @AppStorage("mac.chart.vwap") private var showVWAP = true
    @AppStorage("mac.chart.vwapBands") private var showVWAPBands = false
    @AppStorage("mac.chart.log") private var logScale = false
    @AppStorage("mac.chart.relative") private var relativeMode = false
    @AppStorage("mac.chart.peers") private var showPeers = false
    @AppStorage("mac.chart.events") private var showMarkers = true
    @AppStorage("mac.chart.volume") private var showVolume = true
    @AppStorage("mac.chart.profile") private var showProfile = false
    @AppStorage("mac.chart.rsi") private var showRSI = false
    @AppStorage("mac.chart.drawdown") private var showDrawdown = false
    @AppStorage("mac.chart.seasonality") private var showSeasonality = false
    @AppStorage("mac.chart.expanded") private var expanded = false

    @StateObject private var interaction = MacChartInteraction()
    @State private var compareDraft = ""

    static let smaColors: (Color, Color, Color) = (.blue, .purple, .orange)
    static let vwapColor = Color.teal
    static let comparePalette: [Color] = [.pink, .indigo, .brown, .cyan, .mint]

    private var points: [MacChartPoint] { payload.points ?? [] }
    private var hasVolume: Bool { points.contains { ($0.volume ?? 0) > 0 } }
    private var isIntraday: Bool { range == .d1 || range == .d5 }
    /// Compare and peer lines only make sense rebased, so they switch the plot to relative %.
    private var plotsRelative: Bool { relativeMode || !compare.isEmpty || (showPeers && !peers.isEmpty) }
    private var peersAvailable: Bool { !peers.isEmpty && !isIntraday }

    var body: some View {
        let model = MacQuoteChartModel(
            points: points,
            previousClose: payload.previousClose,
            relative: plotsRelative,
            logScale: logScale && !plotsRelative,
            sma: (showSMA20 && !plotsRelative, showSMA50 && !plotsRelative, showSMA200 && !plotsRelative),
            vwap: showVWAP && !plotsRelative && hasVolume,
            vwapBands: showVWAPBands && !plotsRelative && hasVolume,
            profile: showProfile && !plotsRelative && hasVolume,
            compare: compare.map { ($0.ticker, $0.points) } + (showPeers && peersAvailable ? peers.map { ($0.ticker, $0.points) } : []),
            markers: showMarkers ? markers : []
        )
        let lineColor: Color = MacQuoteMath.direction(points, previousClose: payload.previousClose) >= 0 ? .green : .red

        VStack(alignment: .leading, spacing: 10) {
            toolbar
            compareBar
            MacChartMainPlot(model: model, lineColor: lineColor, range: range, interaction: interaction)
                .frame(height: expanded ? 420 : 260)
            if showVolume && hasVolume {
                MacChartVolumePane(model: model, color: lineColor, interaction: interaction)
                    .frame(height: 72)
            }
            if showRSI {
                MacChartLinePane(title: "RSI 14", values: MacQuoteMath.rsi(points), count: points.count, color: .purple, domain: 0...100, guides: [30, 50, 70], interaction: interaction)
                    .frame(height: 72)
            }
            if showDrawdown {
                MacChartLinePane(title: "Drawdown %", values: MacQuoteMath.drawdown(points), count: points.count, color: .red, domain: nil, guides: [0], interaction: interaction)
                    .frame(height: 72)
            }
            if showSeasonality {
                MacChartSeasonalityPane(months: MacQuoteMath.seasonality(points))
                    .frame(height: 96)
            }
            MacChartReadout(points: points, model: model, range: range, interaction: interaction, showDrawdownHint: showDrawdown)
        }
        .onChange(of: range) { _, newRange in
            interaction.reset()
            applyRangeDefaults(newRange)
        }
        .onChange(of: ticker) { _, _ in interaction.reset() }
        .onChange(of: points.count) { _, _ in interaction.reset() }
        .onChange(of: expanded) { _, _ in interaction.reset() }
        .onAppear { applyRangeDefaults(range) }
    }

    /// The web desk's per-range defaults: VWAP for the session, moving averages for longer views.
    private func applyRangeDefaults(_ range: MacChartRange) {
        if range == .d1 {
            showVWAP = true
        } else {
            showVWAP = false
            showVWAPBands = false
            showSMA20 = true
            showSMA50 = true
        }
    }

    // MARK: Toolbar

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 6) {
            MacChipFlowLayout(spacing: 6) {
                MacChartChip("SMA 20", color: Self.smaColors.0, isOn: $showSMA20).disabled(plotsRelative)
                MacChartChip("SMA 50", color: Self.smaColors.1, isOn: $showSMA50).disabled(plotsRelative)
                MacChartChip("SMA 200", color: Self.smaColors.2, isOn: $showSMA200).disabled(plotsRelative)
                MacChartChip("VWAP", color: Self.vwapColor, isOn: $showVWAP).disabled(plotsRelative || !hasVolume)
                MacChartChip("VWAP bands", color: Self.vwapColor.opacity(0.6), isOn: $showVWAPBands).disabled(plotsRelative || !hasVolume)
                MacChartChip("Log", isOn: $logScale).disabled(plotsRelative)
                MacChartChip("Relative %", isOn: Binding(get: { plotsRelative }, set: { relativeMode = $0 }))
                    .disabled(!compare.isEmpty || (showPeers && peersAvailable))
                if peersAvailable {
                    MacChartChip("Peers", color: Self.comparePalette[0], isOn: $showPeers)
                }
                MacChartChip("Events", color: .orange, isOn: $showMarkers)
            }
            HStack(spacing: 6) {
                MacChipFlowLayout(spacing: 6) {
                    MacChartChip("Volume", isOn: $showVolume).disabled(!hasVolume)
                    MacChartChip("Profile", isOn: $showProfile).disabled(!hasVolume || plotsRelative)
                    MacChartChip("RSI", color: .purple, isOn: $showRSI)
                    MacChartChip("Drawdown", color: .red, isOn: $showDrawdown)
                    MacChartChip("Seasonality", isOn: $showSeasonality)
                }
                Spacer(minLength: 0)
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                } label: {
                    Label(expanded ? "Collapse" : "Expand", systemImage: expanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                }
                .controlSize(.small)
                Button {
                    exportCSV()
                } label: {
                    Label("Export CSV", systemImage: "square.and.arrow.down")
                }
                .controlSize(.small)
                .help("Save \(ticker)-\(range.apiValue).csv (timestamp, open, high, low, close, volume)")
            }
        }
    }

    private var compareBar: some View {
        HStack(spacing: 6) {
            Text("Compare")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(Array(compareTickers.enumerated()), id: \.element) { index, symbol in
                Button {
                    compareTickers.removeAll { $0 == symbol }
                } label: {
                    HStack(spacing: 4) {
                        Circle().fill(Self.comparePalette[index % Self.comparePalette.count]).frame(width: 6, height: 6)
                        Text(symbol).font(.caption.monospacedDigit().weight(.semibold))
                        Image(systemName: "xmark").font(.system(size: 8, weight: .bold)).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(Color.primary.opacity(0.06)))
                }
                .buttonStyle(.plain)
                .help("Remove from compare")
            }
            if compareTickers.count < 4 {
                TextField("Ticker", text: $compareDraft)
                    .textFieldStyle(.roundedBorder)
                    .controlSize(.small)
                    .frame(width: 80)
                    .onSubmit(addCompare)
                Button("Add", action: addCompare)
                    .controlSize(.small)
                    .disabled(compareDraft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            Spacer(minLength: 0)
        }
    }

    private func addCompare() {
        let symbol = compareDraft.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        compareDraft = ""
        guard !symbol.isEmpty, symbol != ticker.uppercased(), !compareTickers.contains(symbol), compareTickers.count < 4,
              symbol.range(of: "^[A-Z0-9][A-Z0-9.\\-^=]{0,15}$", options: .regularExpression) != nil else { return }
        compareTickers.append(symbol)
    }

    private func exportCSV() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(ticker.uppercased())-\(range.apiValue).csv"
        panel.allowedContentTypes = [.commaSeparatedText]
        let csv = MacQuoteMath.csv(points)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? csv.write(to: url, atomically: true, encoding: .utf8)
    }
}

// MARK: - Plot model

/// Everything the plots draw, computed once per render of the panel (not per pointer move).
struct MacQuoteChartModel {
    struct Sample: Identifiable {
        var id: Int { index }
        let index: Int
        let value: Double
    }

    struct Overlay: Identifiable {
        let id: String
        let color: Color
        let dashed: Bool
        let samples: [Sample]
    }

    struct PlacedMarker: Identifiable {
        let id: UUID
        let index: Int
        let label: String
        let color: Color
    }

    let count: Int
    let times: [Int]
    let closes: [Double?]
    let plotted: [Double?]
    let mainSamples: [Sample]
    let overlays: [Overlay]
    let domain: ClosedRange<Double>
    let logScale: Bool
    let relative: Bool
    let previousCloseLine: Double?
    let profile: [MacQuoteMath.ProfileBucket]
    let markers: [PlacedMarker]
    let volumes: [Sample]

    init(
        points: [MacChartPoint],
        previousClose: Double?,
        relative: Bool,
        logScale: Bool,
        sma: (Bool, Bool, Bool),
        vwap: Bool,
        vwapBands: Bool,
        profile: Bool,
        compare: [(String, [MacChartPoint])],
        markers: [MacChartMarker]
    ) {
        count = points.count
        times = points.map(\.t)
        closes = points.map(\.close)
        self.relative = relative
        self.logScale = logScale
        plotted = relative ? MacQuoteMath.relative(closes) : closes

        func samples(_ values: [Double?]) -> [Sample] {
            values.enumerated().compactMap { index, value in value.map { Sample(index: index, value: $0) } }
        }
        mainSamples = samples(plotted)
        volumes = points.enumerated().compactMap { index, p in p.volume.flatMap { $0 > 0 ? Sample(index: index, value: $0) : nil } }

        var overlays: [Overlay] = []
        if sma.0 { overlays.append(Overlay(id: "SMA 20", color: MacQuoteChartPanel.smaColors.0, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 20)))) }
        if sma.1 { overlays.append(Overlay(id: "SMA 50", color: MacQuoteChartPanel.smaColors.1, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 50)))) }
        if sma.2 { overlays.append(Overlay(id: "SMA 200", color: MacQuoteChartPanel.smaColors.2, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 200)))) }
        if vwap || vwapBands {
            let bands = MacQuoteMath.vwapBands(points)
            if vwap { overlays.append(Overlay(id: "VWAP", color: MacQuoteChartPanel.vwapColor, dashed: true, samples: samples(bands.map(\.vwap)))) }
            if vwapBands {
                let band = MacQuoteChartPanel.vwapColor.opacity(0.45)
                overlays.append(Overlay(id: "+1σ", color: band, dashed: true, samples: samples(bands.map(\.upper1))))
                overlays.append(Overlay(id: "−1σ", color: band, dashed: true, samples: samples(bands.map(\.lower1))))
                overlays.append(Overlay(id: "+2σ", color: band.opacity(0.6), dashed: true, samples: samples(bands.map(\.upper2))))
                overlays.append(Overlay(id: "−2σ", color: band.opacity(0.6), dashed: true, samples: samples(bands.map(\.lower2))))
            }
        }
        for (offset, series) in compare.enumerated() {
            let aligned = MacQuoteMath.relative(MacQuoteMath.aligned(series.1, to: points))
            let color = series.0 == "SPY" ? Color.secondary : MacQuoteChartPanel.comparePalette[offset % MacQuoteChartPanel.comparePalette.count]
            overlays.append(Overlay(id: series.0, color: color, dashed: true, samples: samples(aligned)))
        }
        self.overlays = overlays

        // The y-range follows the price line (plus compare lines when rebased), padded like the web.
        var values = plotted.compactMap { $0 }
        if relative { values += overlays.flatMap { $0.samples.map(\.value) } }
        let lo = values.min() ?? 0, hi = values.max() ?? 1
        let pad = Swift.max((hi - lo) * 0.08, Swift.max(abs(hi) * 0.002, 0.01))
        var lower = lo - pad
        if logScale { lower = Swift.max(lower, lo * 0.98, 0.0001) }
        domain = lower...(hi + pad)

        if !relative, !logScale, let previousClose, domain.contains(previousClose) {
            previousCloseLine = previousClose
        } else {
            previousCloseLine = nil
        }

        self.profile = profile ? MacQuoteMath.volumeProfile(points, buckets: 18) : []

        // Markers snap to the nearest point within 3 days; outside the visible range they are dropped.
        let stamps = times
        self.markers = markers.compactMap { marker in
            guard let first = stamps.first, let last = stamps.last,
                  marker.t >= first - 86400, marker.t <= last + 86400 else { return nil }
            var best = 0
            var bestDistance = Int.max
            for (index, stamp) in stamps.enumerated() where abs(stamp - marker.t) < bestDistance {
                best = index
                bestDistance = abs(stamp - marker.t)
            }
            guard bestDistance <= 86400 * 3 else { return nil }
            return PlacedMarker(id: marker.id, index: best, label: marker.label, color: marker.color)
        }
    }

    /// The nearest index with a price, searching outward from `index`.
    func nearestPriced(_ index: Int) -> Int? {
        guard count > 0 else { return nil }
        let start = Swift.min(Swift.max(index, 0), count - 1)
        for offset in 0..<count {
            if start - offset >= 0, plotted[start - offset] != nil { return start - offset }
            if start + offset < count, plotted[start + offset] != nil { return start + offset }
        }
        return nil
    }

    var xDomain: ClosedRange<Int> { 0...Swift.max(count - 1, 1) }

    var axisTicks: [Int] {
        guard count > 1 else { return [0] }
        let step = Swift.max(1, (count - 1) / 5)
        return Array(stride(from: 0, to: count, by: step))
    }
}

enum MacChartFormat {
    static func stamp(_ t: Int, range: MacChartRange, axis: Bool = false) -> String {
        let date = Date(timeIntervalSince1970: TimeInterval(t))
        switch range {
        case .d1: return date.formatted(date: .omitted, time: .shortened)
        case .d5: return axis ? date.formatted(.dateTime.weekday(.abbreviated)) : date.formatted(.dateTime.weekday(.abbreviated).hour().minute())
        case .y5, .max: return date.formatted(.dateTime.month(.abbreviated).year())
        default: return date.formatted(.dateTime.month(.abbreviated).day())
        }
    }

    static func price(_ value: Double) -> String {
        String(format: abs(value) >= 1000 ? "$%.2f" : (abs(value) < 1 ? "$%.4f" : "$%.2f"), value)
    }

    static func signedPct(_ value: Double) -> String {
        String(format: "%@%.2f%%", value >= 0 ? "+" : "−", abs(value))
    }

    static func axisValue(_ value: Double, relative: Bool) -> String {
        if relative { return String(format: "%+.0f%%", value) }
        if abs(value) >= 1000 { return String(format: "%.0f", value) }
        return String(format: abs(value) < 10 ? "%.2f" : "%.1f", value)
    }
}

/// Fixed-width trailing axis labels so every pane's plot area lines up with the price chart.
private let axisLabelWidth: CGFloat = 46

// MARK: - Main plot

private struct MacChartMainPlot: View {
    let model: MacQuoteChartModel
    let lineColor: Color
    let range: MacChartRange
    let interaction: MacChartInteraction

    var body: some View {
        Chart {
            ForEach(model.profile) { bucket in
                RectangleMark(
                    xStart: .value("Profile start", Double(model.count - 1) * (1 - bucket.share * 0.22)),
                    xEnd: .value("Profile end", Double(model.count - 1)),
                    yStart: .value("Low", bucket.low),
                    yEnd: .value("High", bucket.high)
                )
                .foregroundStyle(Color.secondary.opacity(0.16))
            }

            ForEach(model.mainSamples) { sample in
                AreaMark(
                    x: .value("Index", sample.index),
                    yStart: .value("Floor", model.domain.lowerBound),
                    yEnd: .value("Price", sample.value)
                )
                .foregroundStyle(LinearGradient(colors: [lineColor.opacity(0.18), lineColor.opacity(0.01)], startPoint: .top, endPoint: .bottom))
            }

            ForEach(model.mainSamples) { sample in
                LineMark(x: .value("Index", sample.index), y: .value("Price", sample.value), series: .value("Series", "main"))
                    .foregroundStyle(lineColor)
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }

            ForEach(model.overlays) { overlay in
                ForEach(overlay.samples) { sample in
                    LineMark(x: .value("Index", sample.index), y: .value("Value", sample.value), series: .value("Series", overlay.id))
                        .foregroundStyle(overlay.color)
                        .lineStyle(StrokeStyle(lineWidth: 1.25, dash: overlay.dashed ? [4, 3] : []))
                }
            }

            if let previousClose = model.previousCloseLine {
                RuleMark(y: .value("Previous close", previousClose))
                    .foregroundStyle(Color.secondary.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .annotation(position: .top, alignment: .leading, spacing: 2) {
                        Text("Prev close \(MacChartFormat.price(previousClose))")
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
            }

            ForEach(model.markers) { marker in
                RuleMark(x: .value("Event", marker.index))
                    .foregroundStyle(marker.color.opacity(0.45))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .top, spacing: 0) {
                        Text(marker.label)
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(marker.color)
                    }
            }
        }
        .chartXScale(domain: model.xDomain)
        .chartYScale(domain: model.domain, type: model.logScale ? .log : .linear)
        .chartLegend(.hidden)
        .chartPlotStyle { $0.clipped() }
        .chartXAxis {
            AxisMarks(values: model.axisTicks) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                AxisValueLabel {
                    if let index = value.as(Int.self), model.times.indices.contains(index) {
                        Text(MacChartFormat.stamp(model.times[index], range: range, axis: true))
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 5)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(MacChartFormat.axisValue(v, relative: model.relative))
                            .frame(width: axisLabelWidth, alignment: .leading)
                    }
                }
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPriceInteractionLayer(model: model, lineColor: lineColor, proxy: proxy, geo: geo, interaction: interaction)
            }
        }
        .padding(.top, 12)
    }
}

/// Hover line, measure band, endpoints and Fibonacci levels, drawn over the plot with the
/// chart's own scales. Owns the pointer gestures.
private struct MacChartPriceInteractionLayer: View {
    let model: MacQuoteChartModel
    let lineColor: Color
    let proxy: ChartProxy
    let geo: GeometryProxy
    @ObservedObject var interaction: MacChartInteraction

    var body: some View {
        let plot = proxy.plotFrame.map { geo[$0] } ?? .zero
        ZStack(alignment: .topLeading) {
            if let span = interaction.span, let a = model.plotted[span.lower], let b = model.plotted[span.upper] {
                let tone: Color = (model.closes[span.upper] ?? b) >= (model.closes[span.lower] ?? a) ? .green : .red
                let x0 = x(span.lower, plot), x1 = x(span.upper, plot)
                Rectangle()
                    .fill(tone.opacity(0.14))
                    .frame(width: max(x1 - x0, 1), height: plot.height)
                    .offset(x: x0, y: plot.minY)
                fibonacciLines(span: span, plot: plot, tone: tone)
                edge(span.lower, value: a, plot: plot, tone: tone)
                edge(span.upper, value: b, plot: plot, tone: tone)
            } else if let hover = interaction.hoverIndex, let value = model.plotted[hover] {
                Path { path in
                    path.move(to: CGPoint(x: x(hover, plot), y: plot.minY))
                    path.addLine(to: CGPoint(x: x(hover, plot), y: plot.maxY))
                }
                .stroke(Color.secondary.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                Circle()
                    .fill(lineColor)
                    .frame(width: 8, height: 8)
                    .position(x: x(hover, plot), y: y(value, plot))
            }

            Rectangle()
                .fill(Color.clear)
                .contentShape(Rectangle())
                .onContinuousHover { phase in
                    guard !interaction.isDragging else { return }
                    switch phase {
                    case .active(let location): interaction.hoverIndex = index(at: location.x, plot)
                    case .ended: interaction.hoverIndex = nil
                    }
                }
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            guard let end = index(at: value.location.x, plot) else { return }
                            if !interaction.isDragging {
                                interaction.isDragging = true
                                interaction.anchorIndex = index(at: value.startLocation.x, plot) ?? end
                            }
                            interaction.endIndex = end
                            interaction.hoverIndex = end
                        }
                        .onEnded { value in
                            interaction.isDragging = false
                            // A click without a drag clears the measurement.
                            if abs(value.translation.width) < 3 || interaction.span == nil {
                                interaction.anchorIndex = nil
                                interaction.endIndex = nil
                            }
                        }
                )
        }
    }

    private func x(_ index: Int, _ plot: CGRect) -> CGFloat {
        plot.minX + (proxy.position(forX: index) ?? 0)
    }

    private func y(_ value: Double, _ plot: CGRect) -> CGFloat {
        plot.minY + (proxy.position(forY: value) ?? 0)
    }

    private func index(at locationX: CGFloat, _ plot: CGRect) -> Int? {
        guard let raw: Double = proxy.value(atX: locationX - plot.minX) else { return nil }
        return model.nearestPriced(Int(raw.rounded()))
    }

    private func edge(_ index: Int, value: Double, plot: CGRect, tone: Color) -> some View {
        ZStack(alignment: .topLeading) {
            Path { path in
                path.move(to: CGPoint(x: x(index, plot), y: plot.minY))
                path.addLine(to: CGPoint(x: x(index, plot), y: plot.maxY))
            }
            .stroke(tone.opacity(0.8), lineWidth: 1)
            Circle()
                .fill(tone)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
                .frame(width: 9, height: 9)
                .position(x: x(index, plot), y: y(value, plot))
        }
    }

    @ViewBuilder
    private func fibonacciLines(span: (lower: Int, upper: Int), plot: CGRect, tone: Color) -> some View {
        let window = model.plotted[span.lower...span.upper].compactMap { $0 }
        if let high = window.max(), let low = window.min(), high != low {
            ForEach(MacQuoteMath.fibonacci(high: high, low: low), id: \.ratio) { level in
                let yPos = y(level.value, plot)
                Path { path in
                    path.move(to: CGPoint(x: plot.minX, y: yPos))
                    path.addLine(to: CGPoint(x: plot.maxX, y: yPos))
                }
                .stroke(tone.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [2, 4]))
                Text("\(Int((level.ratio * 100).rounded()))%")
                    .font(.system(size: 8, weight: .semibold).monospacedDigit())
                    .foregroundStyle(tone.opacity(0.8))
                    .position(x: plot.minX + 14, y: yPos - 6)
            }
        }
    }
}

// MARK: - Panes

private struct MacChartVolumePane: View {
    let model: MacQuoteChartModel
    let color: Color
    let interaction: MacChartInteraction

    var body: some View {
        Chart(model.volumes) { sample in
            BarMark(x: .value("Index", sample.index), y: .value("Volume", sample.value))
                .foregroundStyle(color.opacity(0.45))
        }
        .chartXScale(domain: model.xDomain)
        .chartXAxis(.hidden)
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 2)) { value in
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(MacNumber.compact(v, currency: false)).frame(width: axisLabelWidth, alignment: .leading)
                    }
                }
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPaneHoverLayer(proxy: proxy, geo: geo, interaction: interaction)
            }
        }
        .overlay(alignment: .topLeading) { paneTitle("Volume") }
    }
}

private struct MacChartLinePane: View {
    let title: String
    let values: [Double?]
    let count: Int
    let color: Color
    let domain: ClosedRange<Double>?
    let guides: [Double]
    let interaction: MacChartInteraction

    var body: some View {
        let samples = values.enumerated().compactMap { index, value in value.map { MacQuoteChartModel.Sample(index: index, value: $0) } }
        let lo = samples.map(\.value).min() ?? 0
        let yDomain = domain ?? (Swift.min(lo, -1) * 1.05)...Swift.max(samples.map(\.value).max() ?? 0, 0.5)
        Chart {
            ForEach(guides, id: \.self) { guide in
                RuleMark(y: .value("Guide", guide))
                    .foregroundStyle(Color.secondary.opacity(0.35))
                    .lineStyle(StrokeStyle(lineWidth: 0.75, dash: [3, 3]))
            }
            ForEach(samples) { sample in
                LineMark(x: .value("Index", sample.index), y: .value(title, sample.value))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 1.25))
            }
        }
        .chartXScale(domain: 0...Swift.max(count - 1, 1))
        .chartYScale(domain: yDomain)
        .chartXAxis(.hidden)
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(String(format: "%.0f", v)).frame(width: axisLabelWidth, alignment: .leading)
                    }
                }
            }
        }
        .chartPlotStyle { $0.clipped() }
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPaneHoverLayer(proxy: proxy, geo: geo, interaction: interaction)
            }
        }
        .overlay(alignment: .topLeading) { paneTitle(title) }
    }
}

private struct MacChartSeasonalityPane: View {
    let months: [MacQuoteMath.SeasonalityMonth]
    private let symbols = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]

    var body: some View {
        Chart(months) { month in
            BarMark(x: .value("Month", "\(month.month)"), y: .value("Average %", month.average ?? 0))
                .foregroundStyle((month.average ?? 0) >= 0 ? Color.green.opacity(0.6) : Color.red.opacity(0.6))
                .annotation(position: .overlay) { EmptyView() }
        }
        .chartXAxis {
            AxisMarks { value in
                AxisValueLabel {
                    if let raw = value.as(String.self), let index = Int(raw) { Text(symbols[index]) }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(String(format: "%+.1f%%", v)).frame(width: axisLabelWidth, alignment: .leading)
                    }
                }
            }
        }
        .overlay(alignment: .topLeading) { paneTitle("Seasonality · avg move by month") }
        .help(months.map { m in "\(symbols[m.month]): \(m.average.map { String(format: "%+.2f%%", $0) } ?? "—")" }.joined(separator: "  "))
    }
}

/// A dashed hover line in a pane, following the price chart's pointer.
private struct MacChartPaneHoverLayer: View {
    let proxy: ChartProxy
    let geo: GeometryProxy
    @ObservedObject var interaction: MacChartInteraction

    var body: some View {
        let plot = proxy.plotFrame.map { geo[$0] } ?? .zero
        if let index = interaction.hoverIndex, let position = proxy.position(forX: index) {
            Path { path in
                path.move(to: CGPoint(x: plot.minX + position, y: plot.minY))
                path.addLine(to: CGPoint(x: plot.minX + position, y: plot.maxY))
            }
            .stroke(Color.secondary.opacity(0.5), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
            .allowsHitTesting(false)
        }
    }
}

private func paneTitle(_ text: String) -> some View {
    Text(text)
        .font(.system(size: 9, weight: .semibold))
        .foregroundStyle(.secondary)
        .padding(.leading, 2)
}

// MARK: - Readout

private struct MacChartReadout: View {
    let points: [MacChartPoint]
    let model: MacQuoteChartModel
    let range: MacChartRange
    @ObservedObject var interaction: MacChartInteraction
    let showDrawdownHint: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let span = interaction.span, let measure = MacQuoteMath.measure(points, from: span.lower, to: span.upper) {
                let tone: Color = measure.change >= 0 ? .green : .red
                Text("\(measure.change >= 0 ? "+" : "−")\(MacChartFormat.price(abs(measure.change))) (\(MacChartFormat.signedPct(measure.changePct))) · \(MacQuoteMath.duration(measure.durationSec))")
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(tone)
                Text("\(MacChartFormat.price(measure.start)) → \(MacChartFormat.price(measure.end)) · \(MacChartFormat.stamp(points[span.lower].t, range: range)) → \(MacChartFormat.stamp(points[span.upper].t, range: range))")
                    .font(.caption.monospacedDigit())
                Text("High \(MacChartFormat.price(measure.high)) · Low \(MacChartFormat.price(measure.low))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Text("Fibonacci " + MacQuoteMath.fibonacci(high: measure.high, low: measure.low)
                    .map { "\(Int(($0.ratio * 100).rounded()))% \(MacChartFormat.price($0.value))" }
                    .joined(separator: " · "))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            } else if let hover = interaction.hoverIndex, points.indices.contains(hover), let close = points[hover].close {
                HStack(spacing: 6) {
                    Text(MacChartFormat.price(close)).font(.headline.monospacedDigit())
                    if model.relative, let rel = model.plotted[hover] {
                        Text(MacChartFormat.signedPct(rel)).font(.subheadline.monospacedDigit()).foregroundStyle(rel >= 0 ? Color.green : Color.red)
                    }
                    Text("· \(MacChartFormat.stamp(points[hover].t, range: range))").font(.caption).foregroundStyle(.secondary)
                }
            } else {
                Text("Hover for a print. Drag to measure a range.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if showDrawdownHint {
                let maxDD = MacQuoteMath.maxDrawdown(points)
                if maxDD < 0 {
                    Text(String(format: "Max drawdown %.1f%%", maxDD)).font(.caption2).foregroundStyle(.red)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 58, alignment: .topLeading)
    }
}

// MARK: - Chip

struct MacChartChip: View {
    let title: String
    var color: Color? = nil
    @Binding var isOn: Bool
    @Environment(\.isEnabled) private var isEnabled

    init(_ title: String, color: Color? = nil, isOn: Binding<Bool>) {
        self.title = title
        self.color = color
        self._isOn = isOn
    }

    var body: some View {
        Button {
            isOn.toggle()
        } label: {
            HStack(spacing: 4) {
                if let color {
                    Circle().fill(color).frame(width: 6, height: 6).opacity(isOn ? 1 : 0.35)
                }
                Text(title)
            }
            .font(.system(size: 11, weight: .medium))
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(isOn ? Color.primary : Color.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule(style: .continuous).fill(Color.primary.opacity(isOn ? 0.10 : 0.03)))
            .overlay(Capsule(style: .continuous).strokeBorder(Color.primary.opacity(isOn ? 0.14 : 0.06), lineWidth: 0.5))
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }
}

/// Lays chips left to right, wrapping whole chips onto the next line when the row is full.
struct MacChipFlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = rows.map { $0.width }.max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width.map { min($0, width) } ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [(indices: [Int], width: CGFloat, height: CGFloat)] {
        var rows: [(indices: [Int], width: CGFloat, height: CGFloat)] = []
        var current: (indices: [Int], width: CGFloat, height: CGFloat) = ([], 0, 0)
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            let needed = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width, !current.indices.isEmpty {
                rows.append(current)
                current = ([index], size.width, size.height)
            } else {
                current = (current.indices + [index], needed, max(current.height, size.height))
            }
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }
}
