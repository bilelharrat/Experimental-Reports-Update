import Foundation

// Quote chart analytics, ported from the web desk (frontend/src/quoteChart.js,
// marketAnalytics.js, marketDesk.js, homeDesk.js) so the Mac and web show the same numbers.
// Series outputs are index-aligned with the input points; nil marks "no value here".

enum MacQuoteMath {
    // MARK: Direction & measuring

    /// last − baseline, where the baseline is the previous close when known, else the first print.
    static func direction(_ points: [MacChartPoint], previousClose: Double?) -> Double {
        guard let last = points.last?.close else { return 0 }
        let base = previousClose ?? points.first?.close
        guard let base else { return 0 }
        return last - base
    }

    struct Measure {
        let start: Double
        let end: Double
        let change: Double
        let changePct: Double
        let durationSec: Int
        let high: Double
        let low: Double
    }

    /// Drag-measure stats between two point indices (either order).
    static func measure(_ points: [MacChartPoint], from a: Int, to b: Int) -> Measure? {
        guard points.indices.contains(a), points.indices.contains(b),
              let first = points[a].close, let last = points[b].close else { return nil }
        let lo = min(a, b), hi = max(a, b)
        let slice = points[lo...hi].compactMap(\.close)
        let values = slice.isEmpty ? [first, last] : slice
        let change = last - first
        return Measure(
            start: first,
            end: last,
            change: change,
            changePct: first != 0 ? change / first * 100 : 0,
            durationSec: abs(points[b].t - points[a].t),
            high: values.max() ?? max(first, last),
            low: values.min() ?? min(first, last)
        )
    }

    static func duration(_ seconds: Int) -> String {
        let sec = abs(seconds)
        if sec < 60 { return "\(sec)s" }
        if sec < 3600 { return "\(max(1, Int((Double(sec) / 60).rounded())))m" }
        if sec < 86400 {
            let hours = sec / 3600
            let minutes = Int((Double(sec % 3600) / 60).rounded())
            return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h"
        }
        if sec < 86400 * 14 { return "\(max(1, Int((Double(sec) / 86400).rounded())))d" }
        if sec < 86400 * 70 { return "\(max(1, Int((Double(sec) / (86400 * 7)).rounded())))w" }
        if sec < 86400 * 365 { return "\(max(1, Int((Double(sec) / (86400 * 30)).rounded())))mo" }
        let years = Double(sec) / (86400 * 365)
        if years >= 10 { return "\(Int(years.rounded()))y" }
        let tenths = (years * 10).rounded() / 10
        return tenths == tenths.rounded() ? "\(Int(tenths))y" : String(format: "%.1fy", tenths)
    }

    static let fibonacciRatios: [Double] = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]

    static func fibonacci(high: Double, low: Double) -> [(ratio: Double, value: Double)] {
        guard high != low else { return [] }
        return fibonacciRatios.map { ($0, high - (high - low) * $0) }
    }

    // MARK: Overlays

    static func movingAverage(_ points: [MacChartPoint], window: Int) -> [Double?] {
        let closes = points.map(\.close)
        var out = [Double?](repeating: nil, count: closes.count)
        guard window > 0, closes.count >= window else { return out }
        for index in (window - 1)..<closes.count {
            let slice = closes[(index + 1 - window)...index]
            guard !slice.contains(where: { $0 == nil }) else { continue }
            out[index] = slice.reduce(0) { $0 + ($1 ?? 0) } / Double(window)
        }
        return out
    }

    struct VWAPPoint {
        let vwap: Double?
        let upper1: Double?
        let lower1: Double?
        let upper2: Double?
        let lower2: Double?
    }

    /// Cumulative VWAP from typical price (H+L+C)/3 with ±1σ / ±2σ bands.
    static func vwapBands(_ points: [MacChartPoint]) -> [VWAPPoint] {
        var pv = 0.0, p2v = 0.0, vol = 0.0
        return points.map { point in
            let typical: Double? = {
                if let h = point.high, let l = point.low, let c = point.close { return (h + l + c) / 3 }
                return point.close
            }()
            guard let typical else {
                return VWAPPoint(vwap: vol > 0 ? pv / vol : nil, upper1: nil, lower1: nil, upper2: nil, lower2: nil)
            }
            if let volume = point.volume, volume > 0 {
                pv += typical * volume
                p2v += typical * typical * volume
                vol += volume
            }
            guard vol > 0 else { return VWAPPoint(vwap: nil, upper1: nil, lower1: nil, upper2: nil, lower2: nil) }
            let vwap = pv / vol
            let variance = p2v / vol - vwap * vwap
            let sigma = variance > 0 ? variance.squareRoot() : 0
            return VWAPPoint(vwap: vwap, upper1: vwap + sigma, lower1: vwap - sigma, upper2: vwap + 2 * sigma, lower2: vwap - 2 * sigma)
        }
    }

    /// Closes rebased to % change from the first finite close.
    static func relative(_ closes: [Double?]) -> [Double?] {
        guard let first = closes.compactMap({ $0 }).first, first != 0 else { return closes.map { _ in nil } }
        return closes.map { $0.map { ($0 - first) / first * 100 } }
    }

    /// A compare series re-sampled onto the main series' timestamps (last close at or before
    /// each stamp), so overlays line up in time whatever interval each series uses.
    static func aligned(_ other: [MacChartPoint], to points: [MacChartPoint]) -> [Double?] {
        let series = other.compactMap { p in p.close.map { (t: p.t, close: $0) } }.sorted { $0.t < $1.t }
        guard let firstT = series.first?.t, let lastT = series.last?.t else { return points.map { _ in nil } }
        var cursor = 0
        return points.map { point in
            guard point.t >= firstT, point.t <= lastT + 86400 * 7 else { return nil }
            while cursor + 1 < series.count, series[cursor + 1].t <= point.t { cursor += 1 }
            return series[cursor].close
        }
    }

    // MARK: Panes

    /// 14-period Wilder RSI.
    static func rsi(_ points: [MacChartPoint], period: Int = 14) -> [Double?] {
        let closes = points.map(\.close)
        var out = [Double?](repeating: nil, count: closes.count)
        guard closes.compactMap({ $0 }).count > period else { return out }
        var gain = 0.0, loss = 0.0, counted = 0
        for i in 1..<closes.count {
            guard let cur = closes[i], let prev = closes[i - 1] else { continue }
            let delta = cur - prev
            if counted < period {
                if delta >= 0 { gain += delta } else { loss -= delta }
                counted += 1
                if counted == period {
                    gain /= Double(period)
                    loss /= Double(period)
                    out[i] = loss == 0 ? 100 : 100 - 100 / (1 + gain / loss)
                }
                continue
            }
            gain = (gain * Double(period - 1) + max(delta, 0)) / Double(period)
            loss = (loss * Double(period - 1) + max(-delta, 0)) / Double(period)
            out[i] = loss == 0 ? 100 : 100 - 100 / (1 + gain / loss)
        }
        return out
    }

    /// % below the running peak.
    static func drawdown(_ points: [MacChartPoint]) -> [Double?] {
        var peak: Double?
        return points.map { point in
            guard let close = point.close else { return nil }
            if peak == nil || close > peak! { peak = close }
            guard let peak, peak != 0 else { return 0 }
            return (close - peak) / peak * 100
        }
    }

    static func maxDrawdown(_ points: [MacChartPoint]) -> Double {
        drawdown(points).compactMap { $0 }.min() ?? 0
    }

    struct SeasonalityMonth: Identifiable {
        var id: Int { month }
        let month: Int
        let average: Double?
        let samples: Int
    }

    /// Average point-to-point % move bucketed by UTC month.
    static func seasonality(_ points: [MacChartPoint]) -> [SeasonalityMonth] {
        var buckets = [[Double]](repeating: [], count: 12)
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let rows = points.compactMap { p in p.close.map { (t: p.t, close: $0) } }
        if rows.count > 1 {
            for i in 1..<rows.count where rows[i - 1].close != 0 {
                let month = calendar.component(.month, from: Date(timeIntervalSince1970: TimeInterval(rows[i].t))) - 1
                buckets[month].append((rows[i].close - rows[i - 1].close) / rows[i - 1].close * 100)
            }
        }
        return buckets.enumerated().map { month, values in
            SeasonalityMonth(month: month, average: values.isEmpty ? nil : values.reduce(0, +) / Double(values.count), samples: values.count)
        }
    }

    struct ProfileBucket: Identifiable {
        var id: Int { index }
        let index: Int
        let low: Double
        let high: Double
        let mid: Double
        let volume: Double
        let share: Double
    }

    /// Volume by price bucket, `share` relative to the busiest bucket.
    static func volumeProfile(_ points: [MacChartPoint], buckets: Int = 18) -> [ProfileBucket] {
        let rows = points.compactMap { p -> (price: Double, volume: Double)? in
            guard let price = p.close ?? p.high ?? p.low, let volume = p.volume, volume > 0 else { return nil }
            return (price, volume)
        }
        guard let minP = rows.map(\.price).min(), let maxP = rows.map(\.price).max() else { return [] }
        let span = maxP - minP == 0 ? 1 : maxP - minP
        let n = max(4, min(48, buckets))
        var volumes = [Double](repeating: 0, count: n)
        for row in rows {
            let idx = min(n - 1, max(0, Int(((row.price - minP) / span) * Double(n))))
            volumes[idx] += row.volume
        }
        let peak = max(volumes.max() ?? 1, 1)
        let step = span / Double(n)
        return (0..<n).map { i -> ProfileBucket in
            let low: Double = minP + step * Double(i)
            return ProfileBucket(index: i, low: low, high: low + step, mid: low + step / 2, volume: volumes[i], share: volumes[i] / peak)
        }
    }

    // MARK: Session & returns

    struct LadderRung: Identifiable {
        let id: String
        let label: String
        let value: Double?
    }

    static func periodReturn(_ points: [MacChartPoint], days: Int?, ytd: Bool, now: Date = Date()) -> Double? {
        let series = points.compactMap { p in p.close.map { (t: p.t, close: $0) } }
        guard series.count >= 2, let last = series.last else { return nil }
        func closeAtOrBefore(_ target: Int) -> Double? { series.last(where: { $0.t <= target })?.close }
        var start: Double?
        if ytd {
            var calendar = Calendar(identifier: .gregorian)
            calendar.timeZone = TimeZone(identifier: "UTC")!
            let year = calendar.component(.year, from: now)
            let jan1 = calendar.date(from: DateComponents(year: year, month: 1, day: 1)) ?? now
            start = closeAtOrBefore(Int(jan1.timeIntervalSince1970)) ?? series[0].close
        } else if let days, days > 0 {
            start = closeAtOrBefore(last.t - days * 86400) ?? series[0].close
        } else {
            start = series[0].close
        }
        guard let start, start != 0 else { return nil }
        return (last.close - start) / start * 100
    }

    /// 1D 1W 1M 3M YTD 1Y 3Y; 1M/YTD/1Y prefer the peers API values when present (like the web).
    static func returnLadder(_ points: [MacChartPoint], overrides: [String: Double], includeThreeYear: Bool) -> [LadderRung] {
        var windows: [(id: String, label: String, days: Int?)] = [
            ("1d", "1D", 1), ("1w", "1W", 7), ("1m", "1M", 30), ("3m", "3M", 90),
            ("ytd", "YTD", nil), ("1y", "1Y", 365),
        ]
        if includeThreeYear { windows.append(("3y", "3Y", 365 * 3)) }
        return windows.map { w in
            LadderRung(id: w.id, label: w.label, value: overrides[w.id] ?? periodReturn(points, days: w.days, ytd: w.id == "ytd"))
        }
    }

    struct GapSplit {
        let gap: Double?
        let session: Double?
    }

    static func gapSplit(open: Double?, previousClose: Double?, last: Double?) -> GapSplit {
        let gap: Double? = {
            guard let open, let previousClose, previousClose != 0 else { return nil }
            return (open - previousClose) / previousClose * 100
        }()
        let session: Double? = {
            guard let last, let open, open != 0 else { return nil }
            return (last - open) / open * 100
        }()
        return GapSplit(gap: gap, session: session)
    }

    // MARK: Relative value

    static func dailyReturns(_ points: [MacChartPoint]) -> [Double?] {
        guard points.count > 1 else { return [] }
        return (1..<points.count).map { i in
            guard let cur = points[i].close, let prev = points[i - 1].close, prev != 0 else { return nil }
            return (cur - prev) / prev
        }
    }

    /// 60-session beta and correlation of `asset` against `bench` (needs ≥10 paired days).
    static func betaAndCorrelation(_ asset: [MacChartPoint], _ bench: [MacChartPoint], window: Int = 60) -> (beta: Double?, corr: Double?) {
        let a = Array(dailyReturns(asset).suffix(window))
        let b = Array(dailyReturns(bench).suffix(window))
        let pairs = zip(a, b).compactMap { x, y -> (Double, Double)? in
            guard let x, let y else { return nil }
            return (x, y)
        }
        guard pairs.count >= 10 else { return (nil, nil) }
        let n = Double(pairs.count)
        let meanA = pairs.reduce(0) { $0 + $1.0 } / n
        let meanB = pairs.reduce(0) { $0 + $1.1 } / n
        var cov = 0.0, varA = 0.0, varB = 0.0
        for (x, y) in pairs {
            cov += (x - meanA) * (y - meanB)
            varA += (x - meanA) * (x - meanA)
            varB += (y - meanB) * (y - meanB)
        }
        let beta = varB != 0 ? cov / varB : nil
        let corr = varA != 0 && varB != 0 ? cov / (varA * varB).squareRoot() : nil
        return (beta, corr)
    }

    // MARK: Options

    /// "Sep 14" / "Sep 14, 2026" / "2026-09-14" → a date; year-less expiries roll to the
    /// next occurrence (a chain never lists expiries more than a few weeks in the past).
    static func expiryDate(_ raw: String, now: Date = Date()) -> Date? {
        let text = raw.trimmingCharacters(in: .whitespaces)
        let posix = Locale(identifier: "en_US_POSIX")
        for format in ["yyyy-MM-dd", "MMM d, yyyy", "MM/dd/yyyy"] {
            let f = DateFormatter()
            f.locale = posix
            f.dateFormat = format
            if let d = f.date(from: text) { return d }
        }
        let f = DateFormatter()
        f.locale = posix
        f.dateFormat = "MMM d yyyy"
        let calendar = Calendar(identifier: .gregorian)
        let year = calendar.component(.year, from: now)
        guard var date = f.date(from: "\(text) \(year)") else { return nil }
        if date < calendar.date(byAdding: .day, value: -60, to: now)! {
            date = calendar.date(byAdding: .year, value: 1, to: date)!
        }
        return date
    }

    struct ExpectedMove {
        let expiry: String
        let expiryDate: Date
        let strike: Double
        let movePct: Double
        let moveUsd: Double
        let days: Int
    }

    private static func optionMid(bid: String?, ask: String?, last: String?) -> Double? {
        if let b = MacFinNumber.parse(bid), let a = MacFinNumber.parse(ask), b >= 0, a >= b { return (a + b) / 2 }
        if let l = MacFinNumber.parse(last), l > 0 { return l }
        return nil
    }

    /// ATM straddle on the nearest unexpired chain: the move the options market prices in.
    static func expectedMove(_ rows: [MacOptionRow], spot: Double?, now: Date = Date()) -> ExpectedMove? {
        guard let spot, spot > 0 else { return nil }
        let startOfToday = Calendar.current.startOfDay(for: now)
        let candidates = rows.compactMap { row -> (row: MacOptionRow, strike: Double, date: Date)? in
            guard let strike = row.strike, let date = expiryDate(row.expiry, now: now), date > startOfToday else { return nil }
            return (row, strike, date)
        }
        guard let nearest = candidates.map(\.date).min() else { return nil }
        guard let atm = candidates.filter({ $0.date == nearest }).min(by: { abs($0.strike - spot) < abs($1.strike - spot) }),
              let call = optionMid(bid: atm.row.callBid, ask: atm.row.callAsk, last: atm.row.callLast),
              let put = optionMid(bid: atm.row.putBid, ask: atm.row.putAsk, last: atm.row.putLast) else { return nil }
        let straddle = call + put
        guard straddle > 0 else { return nil }
        return ExpectedMove(
            expiry: atm.row.expiry,
            expiryDate: nearest,
            strike: atm.strike,
            movePct: straddle / spot * 100,
            moveUsd: straddle,
            days: max(Int((nearest.timeIntervalSince(now) / 86400).rounded()), 0)
        )
    }

    struct OptionsSnapshot {
        let nearestExpiry: String?
        let atmStrike: Double?
        let callVolume: Double
        let putVolume: Double
        let putCallVolume: Double?
        let putCallOi: Double?
    }

    static func optionsSnapshot(_ rows: [MacOptionRow], spot: Double?) -> OptionsSnapshot? {
        guard !rows.isEmpty else { return nil }
        let dated = rows.map { ($0, expiryDate($0.expiry)) }
        let nearestDate = dated.compactMap(\.1).min()
        let nearestRows = nearestDate.map { d in dated.filter { $0.1 == d }.map(\.0) } ?? rows
        var atm = nearestRows.first
        if let spot {
            atm = nearestRows.min(by: { abs(($0.strike ?? .infinity) - spot) < abs(($1.strike ?? .infinity) - spot) })
        }
        func num(_ s: String?) -> Double { MacFinNumber.parse(s) ?? 0 }
        let callVolume = rows.reduce(0) { $0 + num($1.callVolume) }
        let putVolume = rows.reduce(0) { $0 + num($1.putVolume) }
        let callOi = rows.reduce(0) { $0 + num($1.callOi) }
        let putOi = rows.reduce(0) { $0 + num($1.putOi) }
        return OptionsSnapshot(
            nearestExpiry: nearestRows.first?.expiry,
            atmStrike: atm?.strike,
            callVolume: callVolume,
            putVolume: putVolume,
            putCallVolume: callVolume > 0 ? putVolume / callVolume : nil,
            putCallOi: callOi > 0 ? putOi / callOi : nil
        )
    }

    // MARK: Fundamentals & ownership

    struct FALine: Identifiable {
        let id: String
        let label: String
        let latestRaw: String
        let yoy: Double?
    }

    private static let faPatterns: [(id: String, pattern: String)] = [
        ("revenue", "^(total\\s+)?revenue|net\\s+sales|sales$"),
        ("gross_margin", "gross\\s+margin"),
        ("operating_income", "operating\\s+income|income\\s+from\\s+operations"),
        ("op_margin", "operating\\s+margin"),
        ("eps", "diluted\\s+eps|earnings\\s+per\\s+share|eps$"),
        ("fcf", "free\\s+cash\\s+flow|fcf"),
        ("net_cash", "cash\\s+and\\s+cash\\s+equivalents|net\\s+cash"),
    ]

    /// "FA lite": headline lines with YoY change across the Nasdaq statement tables.
    static func faLite(_ financials: MacQuoteFinancials?) -> [FALine] {
        guard let financials else { return [] }
        let tables = [financials.income, financials.ratios, financials.cashflow, financials.balance].compactMap { $0 }
        return faPatterns.compactMap { def in
            guard let regex = try? NSRegularExpression(pattern: def.pattern, options: .caseInsensitive) else { return nil }
            let found = tables.lazy.flatMap(\.rows).first { row in
                let label = row.label.trimmingCharacters(in: .whitespaces)
                return regex.firstMatch(in: label, range: NSRange(label.startIndex..., in: label)) != nil
            }
            guard let found else { return nil }
            let numbers = found.values.compactMap { MacFinNumber.parse($0) }
            var yoy: Double?
            if numbers.count > 1, numbers[1] != 0 { yoy = (numbers[0] - numbers[1]) / abs(numbers[1]) * 100 }
            return FALine(id: def.id, label: found.label, latestRaw: found.values.first ?? "—", yoy: yoy)
        }
    }

    /// Top 3 increases and decreases by reported period change.
    static func ownershipMovers(_ holders: MacQuoteHolders?) -> (buyers: [MacQuoteHolder], sellers: [MacQuoteHolder]) {
        let rows = (holders?.holders ?? []).compactMap { row -> (MacQuoteHolder, Double)? in
            guard let change = MacFinNumber.parse(row.changePct ?? row.change) else { return nil }
            return (row, change)
        }
        let buyers = rows.sorted { $0.1 > $1.1 }.prefix(3).map(\.0)
        let sellers = rows.sorted { $0.1 < $1.1 }.prefix(3).map(\.0)
        return (Array(buyers), Array(sellers))
    }

    struct EarningsStrip {
        let nextDate: String?
        let nextEstimated: Bool
        let days: Int?
        let lastSurprise: Double?
        let consensus: Double?
        let revisionsUp: Double?
        let revisionsDown: Double?
        let avgSurprise: Double?
    }

    static func earningsStrip(_ workspace: MacQuoteWorkspace?, now: Date = Date()) -> EarningsStrip {
        let earnings = workspace?.earnings
        let forecast = workspace?.analysis?.quarterly.first ?? workspace?.analysis?.yearly.first
        let surprises = (earnings?.past ?? []).compactMap(\.surprisePct)
        var days: Int?
        if let next = earnings?.nextDate, let date = expiryDate(next, now: now) {
            days = Int(ceil(date.timeIntervalSince(now) / 86400))
        }
        return EarningsStrip(
            nextDate: earnings?.nextDate,
            nextEstimated: earnings?.nextEstimated ?? false,
            days: days,
            lastSurprise: earnings?.past.first?.surprisePct,
            consensus: forecast?.consensus,
            revisionsUp: forecast?.revisionsUp,
            revisionsDown: forecast?.revisionsDown,
            avgSurprise: surprises.isEmpty ? nil : surprises.reduce(0, +) / Double(surprises.count)
        )
    }

    // MARK: Export

    static func csv(_ points: [MacChartPoint]) -> String {
        let iso = ISO8601DateFormatter()
        var lines = ["timestamp,open,high,low,close,volume"]
        func cell(_ v: Double?) -> String { v.map { String($0) } ?? "" }
        for p in points {
            lines.append([
                iso.string(from: Date(timeIntervalSince1970: TimeInterval(p.t))),
                cell(p.open), cell(p.high), cell(p.low), cell(p.close), cell(p.volume),
            ].joined(separator: ","))
        }
        return lines.joined(separator: "\n")
    }
}
