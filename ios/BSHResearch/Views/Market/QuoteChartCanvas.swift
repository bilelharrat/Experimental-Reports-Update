import Charts
import SwiftUI
import UIKit

/// Google-Finance-style quote chart: dragging moves a crosshair + price
/// bubble; pressing and holding, then dragging, measures a range.
///
/// Everything the chart body needs is computed once per render (``Prepared``).
/// Recomputing the series per mark is what made dense intraday charts —
/// 1D is ~960 points — lock up the screen.
struct QuoteChartCanvas: View {
    let points: [ChartPoint]
    let previousClose: Double?
    let range: ChartRange
    var currency: String? = nil

    @State private var scrubIndex: Int?
    @State private var rangeAnchor: Int?
    @State private var rangeEnd: Int?
    @State private var mode: Mode = .idle
    @State private var holdToken = 0

    private enum Mode {
        case idle
        case scrubbing
        case ranging
    }

    struct Row: Identifiable {
        let id: Int
        let date: Date
        let price: Double
    }

    /// One-shot view model for a render pass.
    struct Prepared {
        let rows: [Row]
        let drawn: [Row]
        let domain: ClosedRange<Double>
        let isUp: Bool
        let formatter: DateFormatter
    }

    var body: some View {
        let prepared = prepare()
        return Group {
            if prepared.rows.count < 2 {
                ContentUnavailableView("No chart data", systemImage: "chart.xyaxis.line")
                    .frame(height: 220)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    headerReadout(prepared)
                    chart(prepared)
                    hintRow
                }
                .onChange(of: points.count) { _, _ in clearInteraction() }
                .onChange(of: range) { _, _ in clearInteraction() }
            }
        }
    }

    // MARK: - Prepared data

    func prepare() -> Prepared {
        var rows: [Row] = []
        rows.reserveCapacity(points.count)
        for point in points {
            guard let close = point.close else { continue }
            rows.append(
                Row(
                    id: rows.count,
                    date: Date(timeIntervalSince1970: TimeInterval(point.t)),
                    price: close
                )
            )
        }

        var lo = Double.greatestFiniteMagnitude
        var hi = -Double.greatestFiniteMagnitude
        for row in rows {
            lo = min(lo, row.price)
            hi = max(hi, row.price)
        }
        if rows.isEmpty { lo = 0; hi = 1 }
        if let previousClose, range == .d1 {
            lo = min(lo, previousClose)
            hi = max(hi, previousClose)
        }
        let pad = max((hi - lo) * 0.08, abs(hi) * 0.002, 0.01)

        return Prepared(
            rows: rows,
            drawn: Self.downsample(rows),
            domain: (lo - pad)...(hi + pad),
            isUp: (rows.last?.price ?? 0) >= (rows.first?.price ?? 0),
            formatter: Self.formatter(for: range)
        )
    }

    /// Swift Charts chokes on thousands of marks; sample the drawn line while
    /// hit-testing still uses every real point.
    static func downsample(_ rows: [Row], limit: Int = 320) -> [Row] {
        guard rows.count > limit else { return rows }
        let stride = Double(rows.count - 1) / Double(limit - 1)
        var out: [Row] = []
        out.reserveCapacity(limit)
        for i in 0..<limit {
            out.append(rows[Int((Double(i) * stride).rounded())])
        }
        if out.last?.id != rows.last?.id, let last = rows.last { out.append(last) }
        return out
    }

    // MARK: - Header readout

    @ViewBuilder
    private func headerReadout(_ prepared: Prepared) -> some View {
        if let (lo, hi) = orderedRange(in: prepared) {
            let start = prepared.rows[lo].price
            let end = prepared.rows[hi].price
            let change = end - start
            let pct = start != 0 ? (change / start) * 100 : 0
            let slice = prepared.rows[lo...hi]
            let up = change >= 0
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(QuoteRow.price(change, currency: currency))
                        .font(.title3.monospacedDigit().weight(.bold))
                        .foregroundStyle(up ? Color.green : Color.red)
                    Text(String(format: "%+.2f%%", pct))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                        .foregroundStyle(up ? Color.green : Color.red)
                    Spacer(minLength: 0)
                }
                Text("\(stamp(prepared.rows[lo].date, prepared)) → \(stamp(prepared.rows[hi].date, prepared))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text("High \(QuoteRow.price(slice.map(\.price).max(), currency: currency))  ·  Low \(QuoteRow.price(slice.map(\.price).min(), currency: currency))")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        } else if let index = scrubIndex, prepared.rows.indices.contains(index) {
            let row = prepared.rows[index]
            let base = prepared.rows.first?.price
            let pct = (base != nil && base != 0) ? ((row.price - base!) / base!) * 100 : nil
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(QuoteRow.price(row.price, currency: currency))
                    .font(.title3.monospacedDigit().weight(.bold))
                if let pct {
                    Text(String(format: "%+.2f%%", pct))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                        .foregroundStyle(pct >= 0 ? Color.green : Color.red)
                }
                Spacer(minLength: 0)
                Text(stamp(row.date, prepared))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(QuoteRow.price(prepared.rows.last?.price, currency: currency))
                    .font(.title3.monospacedDigit().weight(.bold))
                Spacer(minLength: 0)
            }
        }
    }

    private var hintRow: some View {
        Text(scrubIndex == nil && rangeAnchor == nil
             ? "Drag to scrub · hold, then drag, to measure"
             : " ")
            .font(.caption2)
            .foregroundStyle(.tertiary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Chart

    private func chart(_ prepared: Prepared) -> some View {
        let tone = prepared.isUp ? Color.green : Color.red
        let floor = prepared.domain.lowerBound
        return Chart {
            if let previousClose, range == .d1 {
                RuleMark(y: .value("Prev", previousClose))
                    .foregroundStyle(.secondary.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
            }

            ForEach(prepared.drawn) { row in
                AreaMark(
                    x: .value("Time", row.date),
                    yStart: .value("Floor", floor),
                    yEnd: .value("Price", row.price)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [tone.opacity(0.22), tone.opacity(0.02)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
            }

            ForEach(prepared.drawn) { row in
                LineMark(
                    x: .value("Time", row.date),
                    y: .value("Price", row.price)
                )
                .foregroundStyle(tone)
                .lineStyle(StrokeStyle(lineWidth: 2, lineJoin: .round))
            }

            if let (lo, hi) = orderedRange(in: prepared) {
                let a = prepared.rows[lo]
                let b = prepared.rows[hi]
                let rangeTone: Color = b.price >= a.price ? .green : .red
                RectangleMark(
                    xStart: .value("A", a.date),
                    xEnd: .value("B", b.date)
                )
                .foregroundStyle(rangeTone.opacity(0.12))
                RuleMark(x: .value("A", a.date))
                    .foregroundStyle(rangeTone.opacity(0.9))
                RuleMark(x: .value("B", b.date))
                    .foregroundStyle(rangeTone.opacity(0.9))
                PointMark(x: .value("A", a.date), y: .value("P", a.price))
                    .symbolSize(36)
                    .foregroundStyle(rangeTone)
                PointMark(x: .value("B", b.date), y: .value("P", b.price))
                    .symbolSize(36)
                    .foregroundStyle(rangeTone)
            } else if let index = scrubIndex, prepared.rows.indices.contains(index) {
                let row = prepared.rows[index]
                RuleMark(x: .value("Scrub", row.date))
                    .foregroundStyle(Color.primary.opacity(0.3))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                PointMark(x: .value("Scrub", row.date), y: .value("Price", row.price))
                    .symbolSize(60)
                    .foregroundStyle(tone)
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                AxisValueLabel(format: range == .d1 ? .dateTime.hour() : .dateTime.month().day())
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 4))
        }
        .chartYScale(domain: prepared.domain)
        .frame(height: 250)
        .chartOverlay { proxy in
            GeometryReader { geo in
                Color.clear
                    .contentShape(Rectangle())
                    .gesture(dragGesture(prepared: prepared, proxy: proxy, geo: geo))
            }
        }
    }

    // MARK: - Gesture (single recognizer; hold-to-measure is time based)

    private func dragGesture(prepared: Prepared, proxy: ChartProxy, geo: GeometryProxy) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if mode == .idle {
                    let dx = abs(value.translation.width)
                    let dy = abs(value.translation.height)
                    // Vertical intent belongs to the List, not the chart.
                    if dy > 14, dy > dx * 1.5 { return }
                    mode = .scrubbing
                    rangeAnchor = nil
                    rangeEnd = nil
                    armHoldTimer(at: value.location, prepared: prepared, proxy: proxy, geo: geo)
                }

                guard let index = index(at: value.location, prepared: prepared, proxy: proxy, geo: geo) else { return }

                if mode == .ranging {
                    if rangeEnd != index { rangeEnd = index }
                    return
                }

                // Finger travelled — it's a scrub, not a hold.
                if abs(value.translation.width) > 10 || abs(value.translation.height) > 10 {
                    holdToken &+= 1
                }
                if scrubIndex != index { scrubIndex = index }
            }
            .onEnded { _ in
                holdToken &+= 1
                mode = .idle
            }
    }

    /// A hold in place (finger down, barely moving) switches to range mode.
    private func armHoldTimer(at location: CGPoint, prepared: Prepared, proxy: ChartProxy, geo: GeometryProxy) {
        holdToken &+= 1
        let token = holdToken
        let anchor = index(at: location, prepared: prepared, proxy: proxy, geo: geo)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            guard token == holdToken, mode == .scrubbing, let anchor else { return }
            mode = .ranging
            scrubIndex = nil
            rangeAnchor = anchor
            rangeEnd = anchor
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        }
    }

    // MARK: - Helpers

    private func orderedRange(in prepared: Prepared) -> (Int, Int)? {
        guard let a = rangeAnchor, let b = rangeEnd,
              prepared.rows.indices.contains(a), prepared.rows.indices.contains(b)
        else { return nil }
        let lo = min(a, b), hi = max(a, b)
        return lo == hi ? nil : (lo, hi)
    }

    private func index(at location: CGPoint, prepared: Prepared, proxy: ChartProxy, geo: GeometryProxy) -> Int? {
        guard let anchor = proxy.plotFrame else { return nil }
        let frame = geo[anchor]
        let x = min(max(0, location.x - frame.origin.x), frame.size.width)
        guard let date: Date = proxy.value(atX: x) else { return nil }
        return nearestIndex(to: date, in: prepared.rows)
    }

    private func nearestIndex(to date: Date, in rows: [Row]) -> Int? {
        guard !rows.isEmpty else { return nil }
        if date <= rows[0].date { return 0 }
        var lo = 0
        var hi = rows.count - 1
        if date >= rows[hi].date { return hi }
        while lo + 1 < hi {
            let mid = (lo + hi) / 2
            if rows[mid].date <= date { lo = mid } else { hi = mid }
        }
        let dLo = abs(rows[lo].date.timeIntervalSince(date))
        let dHi = abs(rows[hi].date.timeIntervalSince(date))
        return dLo <= dHi ? lo : hi
    }

    private func stamp(_ date: Date, _ prepared: Prepared) -> String {
        prepared.formatter.string(from: date)
    }

    private func clearInteraction() {
        holdToken &+= 1
        scrubIndex = nil
        rangeAnchor = nil
        rangeEnd = nil
        mode = .idle
    }

    private static func formatter(for range: ChartRange) -> DateFormatter {
        // Allocating a DateFormatter mid-drag is a real hitch; cache per range.
        if let cached = formatterCache[range.rawValue] { return cached }
        let formatter = DateFormatter()
        formatter.locale = .current
        switch range {
        case .d1, .d5: formatter.dateFormat = "MMM d · HH:mm"
        case .y5, .max: formatter.dateFormat = "MMM yyyy"
        default: formatter.dateFormat = "MMM d, yyyy"
        }
        formatterCache[range.rawValue] = formatter
        return formatter
    }
}

@MainActor
private var formatterCache: [String: DateFormatter] = [:]
