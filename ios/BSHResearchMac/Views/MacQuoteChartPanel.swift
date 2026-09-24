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
        case .dividend: return .dsAccent
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

/// The chart's strokes under Bureau, from the page's ink (QuoteChart.vue's palette).
struct MacChartPalette {
    let sma: (Color, Color, Color)
    let vwap: Color
    let bandInner: Color
    let bandOuter: Color
    let compare: [Color]
    let accent: Color
    let notice: Color
    let danger: Color

    static func bureau(_ ink: MacBureauPageInk) -> MacChartPalette {
        MacChartPalette(
            sma: (ink.accent, ink.secondary, ink.notice),
            vwap: ink.notice,
            bandInner: ink.accent,
            bandOuter: ink.muted,
            compare: [ink.accent, ink.secondary, ink.notice, ink.muted],
            accent: ink.accent,
            notice: ink.notice,
            danger: ink.danger
        )
    }

    /// Splits in danger, dividends in brass, earnings and calls in notice yellow.
    func marker(_ kind: MacChartMarker.Kind) -> Color {
        switch kind {
        case .split: return danger
        case .dividend: return accent
        default: return notice
        }
    }
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
    /// Bureau draws the website's "Loading…" in place of the plot while the chart loads.
    var loading = false

    @Environment(\.colorScheme) private var colorScheme
    /// Bureau keeps the website's own Peers toggle (on by default there); peers are drawn
    /// once the plot is rebased (Relative %).
    @AppStorage("mac.chart.bureau.peers") private var bureauShowPeers = true
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
        if BSHDesign.active == .bureau {
            bureauBody
        } else {
            glassBody
        }
    }

    @ViewBuilder
    private var glassBody: some View {
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

    // MARK: Bureau (QuoteChart.vue)

    /// Compare lines rebase the plot, as on the Mac; the website's Relative % does the same.
    private var bureauRelative: Bool { relativeMode || !compare.isEmpty }

    /// The website's chart: its tool groups, then a bare plot (no axes) with the day's
    /// area under the price line, the panes under it, and the readout centered below.
    @ViewBuilder
    private var bureauBody: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let relative = bureauRelative
        let peerLines = bureauShowPeers && relative && peersAvailable ? peers.map { ($0.ticker, $0.points) } : []
        let model = MacQuoteChartModel(
            points: points,
            previousClose: payload.previousClose,
            relative: relative,
            logScale: logScale && !relative,
            sma: (showSMA20 && !relative, showSMA50 && !relative, showSMA200 && !relative),
            vwap: showVWAP && !relative && hasVolume,
            vwapBands: showVWAPBands && !relative && hasVolume,
            profile: false,
            compare: compare.map { ($0.ticker, $0.points) } + peerLines,
            markers: showMarkers ? markers : [],
            palette: .bureau(ink),
            tight: true
        )
        let lineColor = MacQuoteMath.direction(points, previousClose: payload.previousClose) >= 0 ? ink.success : ink.danger

        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketChartTools(
                peersAvailable: !peers.isEmpty || !compare.isEmpty,
                eventsAvailable: !markers.isEmpty,
                hasVolume: hasVolume,
                relativeLocked: !compare.isEmpty,
                onExport: points.count > 1 ? { exportCSV() } : nil
            )
            .padding(.bottom, 8)

            if points.count < 2 {
                Text(loading ? "Loading…" : "No chart data for this range yet.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .frame(maxWidth: .infinity)
                    .frame(height: 20)
                    .padding(.vertical, 64)
            } else {
                MacChartMainPlot(model: model, lineColor: lineColor, range: range, interaction: interaction, bureau: ink)
                    .frame(height: expanded ? 380 : 220)
                if showProfile && hasVolume && !relative {
                    MacBureauMarketChartProfile(buckets: MacQuoteMath.volumeProfile(points, buckets: 18), ink: ink)
                        .padding(.top, 5.6)
                }
                if showVolume && hasVolume {
                    MacChartVolumePane(model: model, color: lineColor, interaction: interaction, bureau: ink)
                        .frame(height: 72)
                        .padding(.top, 4)
                }
                if showRSI {
                    MacChartLinePane(title: "RSI 14", values: MacQuoteMath.rsi(points), count: points.count, color: ink.accent, domain: 0...100, guides: [30, 50, 70], interaction: interaction, bureau: ink)
                        .frame(height: 72)
                        .padding(.top, 4)
                }
                if showDrawdown {
                    MacChartLinePane(title: "Drawdown %", values: MacQuoteMath.drawdown(points), count: points.count, color: ink.danger, domain: nil, guides: [0], interaction: interaction, bureau: ink)
                        .frame(height: 72)
                        .padding(.top, 4)
                }
                if showSeasonality {
                    MacChartSeasonalityPane(months: MacQuoteMath.seasonality(points), bureau: ink)
                        .frame(height: 96)
                        .padding(.top, 4)
                }
            }
            MacChartReadout(points: points, model: model, range: range, interaction: interaction, showDrawdownHint: points.count > 1, bureau: ink)
                .padding(.top, 8)
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
                .font(.ui(.caption).weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(Array(compareTickers.enumerated()), id: \.element) { index, symbol in
                Button {
                    compareTickers.removeAll { $0 == symbol }
                } label: {
                    HStack(spacing: 4) {
                        Circle().fill(Self.comparePalette[index % Self.comparePalette.count]).frame(width: 6, height: 6)
                        Text(symbol).font(.ui(.caption).monospacedDigit().weight(.semibold))
                        Image(systemName: "xmark").font(.ui(size: 8, weight: .bold)).foregroundStyle(.secondary)
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
                    .textFieldStyle(.dsField)
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
        var lineWidth: CGFloat = 1.25
        var dash: [CGFloat]? = nil

        var stroke: StrokeStyle { StrokeStyle(lineWidth: lineWidth, dash: dash ?? (dashed ? [4, 3] : [])) }
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
        markers: [MacChartMarker],
        palette: MacChartPalette? = nil,
        tight: Bool = false
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
        if let palette {
            // QuoteChart.vue's strokes: SMA 20 brass, SMA 50 secondary ink, SMA 200 notice,
            // VWAP notice dashed, the bands brass (±1σ) and muted (±2σ), peers dashed.
            if sma.0 { overlays.append(Overlay(id: "SMA 20", color: palette.sma.0, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 20)), lineWidth: 1.25)) }
            if sma.1 { overlays.append(Overlay(id: "SMA 50", color: palette.sma.1, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 50)), lineWidth: 1.25)) }
            if sma.2 { overlays.append(Overlay(id: "SMA 200", color: palette.sma.2, dashed: false, samples: samples(MacQuoteMath.movingAverage(points, window: 200)), lineWidth: 1.4)) }
            if vwap || vwapBands {
                let bands = MacQuoteMath.vwapBands(points)
                if vwapBands {
                    overlays.append(Overlay(id: "+2σ", color: palette.bandOuter.opacity(0.7), dashed: true, samples: samples(bands.map(\.upper2)), lineWidth: 1, dash: [2, 4]))
                    overlays.append(Overlay(id: "−2σ", color: palette.bandOuter.opacity(0.7), dashed: true, samples: samples(bands.map(\.lower2)), lineWidth: 1, dash: [2, 4]))
                    overlays.append(Overlay(id: "+1σ", color: palette.bandInner.opacity(0.85), dashed: true, samples: samples(bands.map(\.upper1)), lineWidth: 1.1, dash: [3, 3]))
                    overlays.append(Overlay(id: "−1σ", color: palette.bandInner.opacity(0.85), dashed: true, samples: samples(bands.map(\.lower1)), lineWidth: 1.1, dash: [3, 3]))
                }
                if vwap { overlays.append(Overlay(id: "VWAP", color: palette.vwap, dashed: true, samples: samples(bands.map(\.vwap)), lineWidth: 1.35, dash: [5, 3])) }
            }
            for (offset, series) in compare.enumerated() {
                let aligned = MacQuoteMath.relative(MacQuoteMath.aligned(series.1, to: points))
                let color = palette.compare[offset % palette.compare.count].opacity(0.85)
                overlays.append(Overlay(id: series.0, color: color, dashed: true, samples: samples(aligned), lineWidth: 1.25, dash: [4, 3]))
            }
        } else {
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
        }
        self.overlays = overlays

        // The y-range follows the price line (plus compare lines when rebased), padded like the web.
        var values = plotted.compactMap { $0 }
        if relative { values += overlays.flatMap { $0.samples.map(\.value) } }
        let lo = values.min() ?? 0, hi = values.max() ?? 1
        if tight {
            // chartGeometry: the line spans exactly its low to its high inside the plot's pad.
            let span = hi - lo
            domain = span > 0 ? lo...hi : (lo - 1)...(hi + 1)
        } else {
            let pad = Swift.max((hi - lo) * 0.08, Swift.max(abs(hi) * 0.002, 0.01))
            var lower = lo - pad
            if logScale { lower = Swift.max(lower, lo * 0.98, 0.0001) }
            domain = lower...(hi + pad)
        }

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
            return PlacedMarker(id: marker.id, index: best, label: marker.label, color: palette?.marker(marker.kind) ?? marker.color)
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
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        if let bureau {
            bureauPlot(bureau)
        } else {
            glassPlot
        }
    }

    /// QuoteChart.vue's plot: no axes or grid, the area under the line at 16%, a 2pt line,
    /// the previous close dashed, events as dashed rules with a dot and label at the top,
    /// all inside an 18 × 14pt margin (the SVG's pad of 18 in a 280-high box drawn 220 high).
    private func bureauPlot(_ ink: MacBureauPageInk) -> some View {
        Chart {
            ForEach(model.profile) { bucket in
                RectangleMark(
                    xStart: .value("Profile start", Double(model.count - 1) * (1 - bucket.share * 0.22)),
                    xEnd: .value("Profile end", Double(model.count - 1)),
                    yStart: .value("Low", bucket.low),
                    yEnd: .value("High", bucket.high)
                )
                .foregroundStyle(ink.accent.opacity(0.18))
            }

            ForEach(model.mainSamples) { sample in
                AreaMark(
                    x: .value("Index", sample.index),
                    yStart: .value("Floor", model.domain.lowerBound),
                    yEnd: .value("Price", sample.value)
                )
                .foregroundStyle(lineColor.opacity(0.16))
            }

            if let previousClose = model.previousCloseLine {
                RuleMark(y: .value("Previous close", previousClose))
                    .foregroundStyle(ink.muted)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
            }

            ForEach(model.overlays) { overlay in
                ForEach(overlay.samples) { sample in
                    LineMark(x: .value("Index", sample.index), y: .value("Value", sample.value), series: .value("Series", overlay.id))
                        .foregroundStyle(overlay.color)
                        .lineStyle(overlay.stroke)
                }
            }

            ForEach(model.mainSamples) { sample in
                LineMark(x: .value("Index", sample.index), y: .value("Price", sample.value), series: .value("Series", "main"))
                    .foregroundStyle(lineColor)
                    .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }

            ForEach(model.markers) { marker in
                RuleMark(x: .value("Event", marker.index))
                    .foregroundStyle(marker.color)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 3]))
                    .annotation(position: .top, alignment: .leading, spacing: -3.5) {
                        HStack(alignment: .bottom, spacing: 0.5) {
                            Circle().fill(marker.color).frame(width: 7, height: 7)
                            Text(marker.label)
                                .font(BSHType.bureauSans(9))
                                .foregroundStyle(ink.secondary)
                                .fixedSize()
                                .offset(y: -3.5)
                        }
                        .offset(x: -3.5)
                    }
            }
        }
        .chartXScale(domain: model.xDomain)
        .chartYScale(domain: model.domain, type: model.logScale ? .log : .linear)
        .chartLegend(.hidden)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPriceInteractionLayer(model: model, lineColor: lineColor, proxy: proxy, geo: geo, interaction: interaction, bureau: ink)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .clipped()
    }

    private var glassPlot: some View {
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
                            .font(.ui(size: 9, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
            }

            ForEach(model.markers) { marker in
                RuleMark(x: .value("Event", marker.index))
                    .foregroundStyle(marker.color.opacity(0.45))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .top, spacing: 0) {
                        Text(marker.label)
                            .font(.ui(size: 9, weight: .bold))
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
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        let plot = proxy.plotFrame.map { geo[$0] } ?? .zero
        ZStack(alignment: .topLeading) {
            if let span = interaction.span, let a = model.plotted[span.lower], let b = model.plotted[span.upper] {
                let rising = (model.closes[span.upper] ?? b) >= (model.closes[span.lower] ?? a)
                let tone: Color = bureau.map { rising ? $0.success : $0.danger } ?? (rising ? .green : .red)
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
                .stroke(bureau?.muted ?? Color.secondary.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: bureau == nil ? [4, 4] : [3, 3]))
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
                .stroke(bureau?.secondary ?? tone.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [2, 4]))
                if bureau == nil {
                    Text("\(Int((level.ratio * 100).rounded()))%")
                        .font(.ui(size: 8, weight: .semibold).monospacedDigit())
                        .foregroundStyle(tone.opacity(0.8))
                        .position(x: plot.minX + 14, y: yPos - 6)
                }
            }
        }
    }
}

// MARK: - Panes

private struct MacChartVolumePane: View {
    let model: MacQuoteChartModel
    let color: Color
    let interaction: MacChartInteraction
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        if bureau != nil {
            bureauPane
        } else {
            glassPane
        }
    }

    /// The website's volume pane: 2.4pt bars at 45% of the line's color, 8pt clear above
    /// the tallest and 4pt below, no axis.
    private var bureauPane: some View {
        let peak = Swift.max(model.volumes.map(\.value).max() ?? 1, 1)
        return Chart(model.volumes) { sample in
            BarMark(x: .value("Index", sample.index), y: .value("Volume", sample.value), width: .fixed(2.4))
                .foregroundStyle(color.opacity(0.45))
        }
        .chartXScale(domain: model.xDomain)
        .chartYScale(domain: 0...peak)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPaneHoverLayer(proxy: proxy, geo: geo, interaction: interaction, bureau: bureau)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
        .padding(.bottom, 4)
    }

    private var glassPane: some View {
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
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        if let bureau {
            bureauPane(bureau)
        } else {
            glassPane
        }
    }

    /// The website's RSI and drawdown panes: a 1.5pt line inside an 8pt pad, dashed guides
    /// in subtle ink, no axis or title.
    private func bureauPane(_ ink: MacBureauPageInk) -> some View {
        let samples = values.enumerated().compactMap { index, value in value.map { MacQuoteChartModel.Sample(index: index, value: $0) } }
        let lo = samples.map(\.value).min() ?? 0
        let yDomain = domain ?? Swift.min(lo, -1)...0
        return Chart {
            ForEach(guides, id: \.self) { guide in
                RuleMark(y: .value("Guide", guide))
                    .foregroundStyle(ink.subtle)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }
            ForEach(samples) { sample in
                LineMark(x: .value("Index", sample.index), y: .value(title, sample.value))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
            }
        }
        .chartXScale(domain: 0...Swift.max(count - 1, 1))
        .chartYScale(domain: yDomain)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartOverlay { proxy in
            GeometryReader { geo in
                MacChartPaneHoverLayer(proxy: proxy, geo: geo, interaction: interaction, bureau: ink)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .clipped()
    }

    @ViewBuilder
    private var glassPane: some View {
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
    var bureau: MacBureauPageInk? = nil
    private let symbols = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]

    var body: some View {
        if let bureau {
            bureauPane(bureau)
        } else {
            glassPane
        }
    }

    /// `.yf-season`: twelve cells, each a bar (4 to 36pt, 8pt per percent) over its initial.
    private func bureauPane(_ ink: MacBureauPageInk) -> some View {
        HStack(alignment: .bottom, spacing: 4) {
            ForEach(months) { month in
                VStack(spacing: 2) {
                    Spacer(minLength: 0)
                    RoundedRectangle(cornerRadius: 2, style: .circular)
                        .fill(((month.average ?? 0) >= 0 ? ink.success : ink.danger).opacity(0.55))
                        .frame(height: Swift.min(36, Swift.max(4, abs(month.average ?? 0) * 8)))
                    Text(symbols[month.month])
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.muted)
                        .frame(height: 13)
                }
                .frame(maxWidth: .infinity)
                .help(month.average.map { String(format: "%.2f%%", $0) } ?? "—")
            }
        }
        .padding(.horizontal, 18)
    }

    private var glassPane: some View {
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
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        let plot = proxy.plotFrame.map { geo[$0] } ?? .zero
        if let index = interaction.hoverIndex, let position = proxy.position(forX: index) {
            Path { path in
                path.move(to: CGPoint(x: plot.minX + position, y: plot.minY))
                path.addLine(to: CGPoint(x: plot.minX + position, y: plot.maxY))
            }
            .stroke(bureau?.muted.opacity(0.7) ?? Color.secondary.opacity(0.5), style: StrokeStyle(lineWidth: 1, dash: bureau == nil ? [4, 4] : [3, 3]))
            .allowsHitTesting(false)
        }
    }
}

private func paneTitle(_ text: String) -> some View {
    Text(text)
        .font(.ui(size: 9, weight: .semibold))
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
    var bureau: MacBureauPageInk? = nil

    var body: some View {
        if let bureau {
            bureauReadout(bureau)
        } else {
            glassReadout
        }
    }

    /// The website's readout, centered under the chart: the drawdown note, then the
    /// measured move (or the hovered print, or the hint).
    private func bureauReadout(_ ink: MacBureauPageInk) -> some View {
        VStack(spacing: 0) {
            if showDrawdownHint {
                let maxDD = MacQuoteMath.maxDrawdown(points)
                if maxDD < 0 {
                    Text(String(format: "Max drawdown %.1f%%", maxDD))
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.secondary)
                        .frame(height: 16)
                        .padding(.bottom, 8)
                }
            }
            if let span = interaction.span, let measure = MacQuoteMath.measure(points, from: span.lower, to: span.upper) {
                Text("\(measure.change >= 0 ? "+" : "-")\(MacBureauMarketFormat.price(abs(measure.change))) (\(String(format: "%+.2f", measure.changePct))%) · \(MacQuoteMath.duration(measure.durationSec))")
                    .font(BSHType.bureauSans(18, weight: .semibold).monospacedDigit())
                    .tracking(-0.18)
                    .foregroundStyle(measure.change >= 0 ? ink.success : ink.danger)
                    .frame(height: 24)
                Text("\(MacBureauMarketFormat.price(measure.start)) → \(MacBureauMarketFormat.price(measure.end)) · \(MacChartFormat.stamp(points[span.lower].t, range: range)) → \(MacChartFormat.stamp(points[span.upper].t, range: range))")
                    .font(MacBureauMarketText.font(14, weight: .medium, tabular: true))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .frame(height: 20)
                    .padding(.top, 4)
                Text("High \(MacBureauMarketFormat.price(measure.high)) · Low \(MacBureauMarketFormat.price(measure.low))")
                    .font(BSHType.bureauSans(12, weight: .medium).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                    .frame(height: 16)
                    .padding(.top, 2)
                Text("Fibonacci " + MacQuoteMath.fibonacci(high: measure.high, low: measure.low)
                    .map { "\(Int(($0.ratio * 100).rounded()))% \(MacBureauMarketFormat.price($0.value))" }
                    .joined(separator: " · "))
                    .font(BSHType.bureauSans(12, weight: .medium).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                    .multilineTextAlignment(.center)
                    .bureauLines(16, size: 12)
                    .padding(.top, 2)
            } else if let hover = interaction.hoverIndex, points.indices.contains(hover), let close = points[hover].close {
                Text([MacBureauMarketFormat.price(close), MacChartFormat.stamp(points[hover].t, range: range)].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(BSHType.bureauSans(14, weight: .medium).monospacedDigit())
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .frame(height: 20)
            } else {
                Text("Hover for a print. Drag to measure a range.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .frame(height: 16)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var glassReadout: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let span = interaction.span, let measure = MacQuoteMath.measure(points, from: span.lower, to: span.upper) {
                let tone: Color = measure.change >= 0 ? .green : .red
                Text("\(measure.change >= 0 ? "+" : "−")\(MacChartFormat.price(abs(measure.change))) (\(MacChartFormat.signedPct(measure.changePct))) · \(MacQuoteMath.duration(measure.durationSec))")
                    .font(.ui(.headline).monospacedDigit())
                    .foregroundStyle(tone)
                Text("\(MacChartFormat.price(measure.start)) → \(MacChartFormat.price(measure.end)) · \(MacChartFormat.stamp(points[span.lower].t, range: range)) → \(MacChartFormat.stamp(points[span.upper].t, range: range))")
                    .font(.ui(.caption).monospacedDigit())
                Text("High \(MacChartFormat.price(measure.high)) · Low \(MacChartFormat.price(measure.low))")
                    .font(.ui(.caption).monospacedDigit())
                    .foregroundStyle(.secondary)
                Text("Fibonacci " + MacQuoteMath.fibonacci(high: measure.high, low: measure.low)
                    .map { "\(Int(($0.ratio * 100).rounded()))% \(MacChartFormat.price($0.value))" }
                    .joined(separator: " · "))
                    .font(.ui(.caption2).monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            } else if let hover = interaction.hoverIndex, points.indices.contains(hover), let close = points[hover].close {
                HStack(spacing: 6) {
                    Text(MacChartFormat.price(close)).font(.ui(.headline).monospacedDigit())
                    if model.relative, let rel = model.plotted[hover] {
                        Text(MacChartFormat.signedPct(rel)).font(.ui(.subheadline).monospacedDigit()).foregroundStyle(rel >= 0 ? Color.green : Color.red)
                    }
                    Text("· \(MacChartFormat.stamp(points[hover].t, range: range))").font(.ui(.caption)).foregroundStyle(.secondary)
                }
            } else {
                Text("Hover for a print. Drag to measure a range.")
                    .font(.ui(.caption))
                    .foregroundStyle(.secondary)
            }
            if showDrawdownHint {
                let maxDD = MacQuoteMath.maxDrawdown(points)
                if maxDD < 0 {
                    Text(String(format: "Max drawdown %.1f%%", maxDD)).font(.ui(.caption2)).foregroundStyle(.red)
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
            .font(.ui(size: 11, weight: .medium))
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

// MARK: - Bureau tools (QuoteChart.vue `.yf-chart-tools-grouped`)

/// The website's chart tools: "Overlays", "Panes" and "Export", each a muted label and its
/// toggles as range pills, the groups wrapping 20pt apart across and 8pt down. They read
/// and write the same settings as the Mac's chart, so both designs keep one set.
struct MacBureauMarketChartTools: View {
    let peersAvailable: Bool
    let eventsAvailable: Bool
    let hasVolume: Bool
    /// Compare lines keep the plot rebased (Relative % stays on while they are there).
    let relativeLocked: Bool
    let onExport: (() -> Void)?

    @Environment(\.colorScheme) private var colorScheme
    @AppStorage("mac.chart.sma20") private var showSMA20 = true
    @AppStorage("mac.chart.sma50") private var showSMA50 = true
    @AppStorage("mac.chart.sma200") private var showSMA200 = false
    @AppStorage("mac.chart.vwap") private var showVWAP = true
    @AppStorage("mac.chart.vwapBands") private var showVWAPBands = false
    @AppStorage("mac.chart.log") private var logScale = false
    @AppStorage("mac.chart.relative") private var relativeMode = false
    @AppStorage("mac.chart.bureau.peers") private var showPeers = true
    @AppStorage("mac.chart.events") private var showMarkers = true
    @AppStorage("mac.chart.volume") private var showVolume = true
    @AppStorage("mac.chart.profile") private var showProfile = false
    @AppStorage("mac.chart.rsi") private var showRSI = false
    @AppStorage("mac.chart.drawdown") private var showDrawdown = false
    @AppStorage("mac.chart.seasonality") private var showSeasonality = false

    var body: some View {
        let relative = relativeMode || relativeLocked
        MacBureauMarketFlow(spacing: 20, lineSpacing: 8) {
            group("Overlays") {
                MacBureauMarketRangeItem("SMA 20", selected: showSMA20) { showSMA20.toggle() }
                MacBureauMarketRangeItem("SMA 50", selected: showSMA50) { showSMA50.toggle() }
                MacBureauMarketRangeItem("SMA 200", selected: showSMA200) { showSMA200.toggle() }
                MacBureauMarketRangeItem("VWAP", selected: showVWAP) { showVWAP.toggle() }
                MacBureauMarketRangeItem("VWAP bands", selected: showVWAPBands) { showVWAPBands.toggle() }
                MacBureauMarketRangeItem("Log", selected: logScale) { logScale.toggle() }
                if peersAvailable {
                    MacBureauMarketRangeItem("Peers", selected: showPeers) { showPeers.toggle() }
                    MacBureauMarketRangeItem("Relative %", selected: relative) {
                        if !relativeLocked { relativeMode.toggle() }
                    }
                }
                if eventsAvailable {
                    MacBureauMarketRangeItem("Earnings", selected: showMarkers) { showMarkers.toggle() }
                }
            }
            group("Panes") {
                MacBureauMarketRangeItem("Volume", selected: showVolume) { showVolume.toggle() }
                MacBureauMarketRangeItem("Profile", selected: showProfile) { showProfile.toggle() }
                MacBureauMarketRangeItem("RSI", selected: showRSI) { showRSI.toggle() }
                MacBureauMarketRangeItem("Drawdown", selected: showDrawdown) { showDrawdown.toggle() }
                MacBureauMarketRangeItem("Seasonality", selected: showSeasonality) { showSeasonality.toggle() }
            }
            group("Export") {
                MacBureauMarketRangeItem("Export CSV") { onExport?() }
            }
        }
    }

    private func group<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        MacBureauMarketFlow(spacing: 4, lineSpacing: 8) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .semibold))
                .tracking(0.066)
                .foregroundStyle(MacBureauPageInk(scheme: colorScheme).muted)
                .fixedSize()
                .frame(height: 14)
                .padding(.trailing, 4)
            content()
        }
    }
}

/// `.yf-profile`: the volume at each price as brass bars, low prices at the foot.
struct MacBureauMarketChartProfile: View {
    let buckets: [MacQuoteMath.ProfileBucket]
    let ink: MacBureauPageInk

    var body: some View {
        let peak = max(buckets.map(\.volume).max() ?? 1, 1)
        GeometryReader { geo in
            VStack(alignment: .leading, spacing: 1) {
                ForEach(buckets.reversed()) { bucket in
                    RoundedRectangle(cornerRadius: 1, style: .circular)
                        .fill(ink.accent.opacity(0.55))
                        .frame(width: geo.size.width * max(bucket.volume / peak * 100, 2) / 100, height: 3)
                        .help("\(MacBureauMarketFormat.price(bucket.mid)) · \(Int((bucket.volume / peak * 100).rounded()))%")
                }
            }
        }
        .frame(height: min(96, CGFloat(buckets.count) * 4 - 1))
        .padding(.vertical, 4)
    }
}
