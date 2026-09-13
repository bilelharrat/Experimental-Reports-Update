import SwiftUI

struct SparkSeries: Decodable {
    let closes: [Double]
    let previousClose: Double?

    enum CodingKeys: String, CodingKey {
        case closes
        case previousClose = "previous_close"
    }
}

private struct SparkResponse: Decodable {
    let sparks: [String: SparkSeries]
}

/// Coalesces per-row sparkline requests into one batched `/quotes/spark`
/// call: rows ask individually, the store flushes every 250ms.
actor SparkStore {
    static let shared = SparkStore()

    private var cache: [String: (Date, SparkSeries)] = [:]
    private var pending: Set<String> = []
    private var waiters: [String: [CheckedContinuation<SparkSeries?, Never>]] = [:]
    private var flushScheduled = false
    private let ttl: TimeInterval = 300

    func series(for ticker: String) async -> SparkSeries? {
        let symbol = ticker.trimmingCharacters(in: .whitespaces).uppercased()
        guard !symbol.isEmpty else { return nil }
        if let (at, series) = cache[symbol], Date().timeIntervalSince(at) < ttl {
            return series
        }
        return await withCheckedContinuation { continuation in
            waiters[symbol, default: []].append(continuation)
            pending.insert(symbol)
            scheduleFlush()
        }
    }

    private func scheduleFlush() {
        guard !flushScheduled else { return }
        flushScheduled = true
        Task {
            try? await Task.sleep(nanoseconds: 250_000_000)
            await self.flush()
        }
    }

    private func flush() async {
        flushScheduled = false
        let batch = Array(pending.prefix(40))
        pending.subtract(batch)
        if !pending.isEmpty { scheduleFlush() }
        guard !batch.isEmpty else { return }

        let response: SparkResponse? = try? await APIClient.shared.get(
            "quotes/spark",
            query: batch.map { URLQueryItem(name: "ticker", value: $0) }
        )
        let now = Date()
        for symbol in batch {
            let series = response?.sparks[symbol]
            if let series { cache[symbol] = (now, series) }
            for continuation in waiters[symbol] ?? [] {
                continuation.resume(returning: series)
            }
            waiters[symbol] = nil
        }
    }
}

/// The little day-chart line Apple Stocks shows in every list row.
struct SparklineView: View {
    let ticker: String
    @State private var series: SparkSeries?

    var body: some View {
        ZStack {
            if let series, series.closes.count > 1 {
                SparklineShape(closes: series.closes)
                    .stroke(tone(series), style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                if let previous = series.previousClose,
                   let lo = series.closes.min(), let hi = series.closes.max(),
                   hi > lo, previous >= lo, previous <= hi {
                    let y = 1 - (previous - lo) / (hi - lo)
                    SparklineBaseline(fraction: y)
                        .stroke(Color(.systemGray4), style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                }
            }
        }
        .frame(width: 52, height: 26)
        .task(id: ticker) {
            series = await SparkStore.shared.series(for: ticker)
        }
    }

    private func tone(_ series: SparkSeries) -> Color {
        let reference = series.previousClose ?? series.closes.first ?? 0
        let last = series.closes.last ?? 0
        return last >= reference ? Color(.systemGreen) : Color(.systemRed)
    }
}

private struct SparklineShape: Shape {
    let closes: [Double]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard closes.count > 1,
              let lo = closes.min(), let hi = closes.max()
        else { return path }
        let span = max(hi - lo, 0.0001)
        let stepX = rect.width / CGFloat(closes.count - 1)
        for (index, close) in closes.enumerated() {
            let x = rect.minX + CGFloat(index) * stepX
            let y = rect.maxY - CGFloat((close - lo) / span) * rect.height
            if index == 0 {
                path.move(to: CGPoint(x: x, y: y))
            } else {
                path.addLine(to: CGPoint(x: x, y: y))
            }
        }
        return path
    }
}

private struct SparklineBaseline: Shape {
    let fraction: Double

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let y = rect.minY + rect.height * CGFloat(fraction)
        path.move(to: CGPoint(x: rect.minX, y: y))
        path.addLine(to: CGPoint(x: rect.maxX, y: y))
        return path
    }
}
