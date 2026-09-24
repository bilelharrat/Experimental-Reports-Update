//
//  MacBureauTracking.swift
//  BSHResearchMac
//
//  Tracking under Bureau, laid out as the website's page (TrackingView.vue): the title with
//  All / Followed, Sync news and Refresh; the book's P&L once something is followed; the live
//  tape; what needs attention; a card for every company (its mark, stage, price and move,
//  what it does, its KPIs, last round, latest news, people, products and competitors); and
//  the news that mentions them, from the endpoints the website reads. What only the Mac has,
//  its private holdings and the monitoring of Invest and Watch decisions, follows at the foot
//  of the page in sections of the same kind, each opening the Mac's own record in a sheet.
//

import AppKit
import SwiftUI

// MARK: - The website's company record, read loosely

/// A JSON value, read as the website reads its company records: by key, with whatever type
/// the record happens to carry (an amount can be a number or "$100,000,000+").
enum MacTrackingJSON: Decodable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([MacTrackingJSON])
    case object([String: MacTrackingJSON])
    case null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            self = .null
        } else if let v = try? c.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? c.decode(Double.self) {
            self = .number(v)
        } else if let v = try? c.decode(String.self) {
            self = .string(v)
        } else if let v = try? c.decode([MacTrackingJSON].self) {
            self = .array(v)
        } else if let v = try? c.decode([String: MacTrackingJSON].self) {
            self = .object(v)
        } else {
            self = .null
        }
    }

    subscript(key: String) -> MacTrackingJSON {
        if case .object(let o) = self { return o[key] ?? .null }
        return .null
    }

    var array: [MacTrackingJSON] {
        if case .array(let a) = self { return a }
        return []
    }

    var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    /// `String(value)` as JavaScript writes it; nil for null, objects and arrays.
    var text: String? {
        switch self {
        case .string(let s): return s
        case .number(let n): return Self.jsNumber(n)
        case .bool(let b): return b ? "true" : "false"
        default: return nil
        }
    }

    /// The value's text when JavaScript would call it truthy.
    var truthy: String? {
        switch self {
        case .string(let s): return s.isEmpty ? nil : s
        case .number(let n): return n == 0 || n.isNaN ? nil : Self.jsNumber(n)
        case .bool(let b): return b ? "true" : nil
        default: return nil
        }
    }

    /// `Number(value)` when it is a finite number.
    var number: Double? {
        switch self {
        case .number(let n): return n.isFinite ? n : nil
        case .string(let s):
            guard let n = Double(s.trimmingCharacters(in: .whitespacesAndNewlines)), n.isFinite else { return nil }
            return n
        default: return nil
        }
    }

    /// `isPendingValue`: missing, or one of the words the records use for "not known yet".
    var isPending: Bool {
        let raw: String
        switch self {
        case .null: return true
        case .array(let a): raw = a.compactMap(\.text).joined(separator: ",")
        case .object: raw = "[object Object]"
        default: raw = text ?? ""
        }
        return Self.pendingWords.contains(raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    private static let pendingWords: Set<String> = [
        "", "unknown", "unknown/pending", "pending", "source pending", "n/a", "na", "null", "undefined",
    ]

    static func jsNumber(_ n: Double) -> String {
        if n.isNaN { return "NaN" }
        if n == n.rounded(), abs(n) < 1e21 { return String(format: "%.0f", n) }
        return "\(n)"
    }
}

// MARK: - The website's formatting (formatters.js, liveTicker.js)

enum MacTrackingFormat {
    /// `Number.prototype.toFixed`: halves round away from zero.
    static func toFixed(_ x: Double, _ digits: Int) -> String {
        let p = pow(10, Double(digits))
        let r = (abs(x) * p).rounded(.toNearestOrAwayFromZero) / p
        let s = String(format: "%.\(digits)f", r)
        return x < 0 ? "-" + s : s
    }

    /// A number, or a string that is exactly one.
    static func numeric(_ v: MacTrackingJSON) -> Double? {
        switch v {
        case .number(let n): return n.isFinite ? n : nil
        case .string(let s):
            let raw = s.trimmingCharacters(in: .whitespacesAndNewlines)
            guard raw.range(of: #"^[-+]?\d+(?:\.\d+)?$"#, options: .regularExpression) != nil else { return nil }
            return Double(raw)
        default: return nil
        }
    }

    static func compactNumber(_ v: MacTrackingJSON, currency: Bool = false) -> String {
        if v.isPending { return "—" }
        guard let n = numeric(v) else { return v.text ?? "" }
        let a = abs(n)
        let scale: (Double, String) = a >= 1e12 ? (1e12, "T") : a >= 1e9 ? (1e9, "B") : a >= 1e6 ? (1e6, "M") : a >= 1e3 ? (1e3, "K") : (1, "")
        let scaled = n / scale.0
        let decimals = scale.0 == 1 || abs(scaled) >= 100 ? 0 : 1
        return "\(n < 0 ? "-" : "")\(currency ? "$" : "")\(toFixed(abs(scaled), decimals))\(scale.1)"
    }

    static func metricValue(label: String, _ v: MacTrackingJSON) -> String {
        if v.isPending { return "—" }
        let raw = (v.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let normalized = label.lowercased()
        if raw.contains("%") || raw.range(of: #"[KMBT]$"#, options: [.regularExpression, .caseInsensitive]) != nil || raw.hasPrefix("$") {
            return raw
        }
        if normalized.range(of: "growth|cagr|margin|rate|change|return", options: .regularExpression) != nil {
            guard let n = numeric(v) else { return raw }
            return "\(n > 0 ? "+" : "")\(MacTrackingJSON.jsNumber(n))%"
        }
        let money = normalized.range(of: "arr|tam|valuation|revenue|funding|raised|investment|ev|price", options: .regularExpression) != nil
        return compactNumber(v, currency: money)
    }

    static func isoDate(_ value: String?, fallback: String? = "—") -> String? {
        guard let raw = value, !raw.isEmpty else { return fallback }
        if let m = raw.range(of: #"^\d{4}-\d{2}-\d{2}"#, options: .regularExpression) { return String(raw[m]) }
        guard let date = MacTimeFormat.parse(raw) else { return fallback }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }

    /// `toLocaleString(undefined, { maximumFractionDigits: 2 })` in the website's locale.
    static func grouped(_ n: Double) -> String {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_US")
        f.numberStyle = .decimal
        f.minimumFractionDigits = 0
        f.maximumFractionDigits = 2
        f.roundingMode = .halfUp
        return f.string(from: NSNumber(value: n)) ?? MacTrackingJSON.jsNumber(n)
    }

    /// `lastPriceLabel`.
    static func price(_ last: Double?, currency: String?) -> String? {
        guard let last, last.isFinite else { return nil }
        let symbol = (currency ?? "").isEmpty || currency == "USD" ? "$" : "\(currency ?? "") "
        return symbol + grouped(last)
    }

    /// `signedChange`: one decimal, a plus for gains.
    static func signed(_ v: Double?) -> String? {
        guard let v, v.isFinite else { return nil }
        return "\(v > 0 ? "+" : "")\(toFixed(v, 1))%"
    }

    static func moneyUSD(_ v: Double?) -> String {
        guard let v, v.isFinite else { return "—" }
        return price(v, currency: "USD") ?? "—"
    }

    static func signedMoneyUSD(_ v: Double?) -> String {
        guard let v, v.isFinite else { return "—" }
        let magnitude = moneyUSD(abs(v))
        if magnitude == "—" { return "—" }
        return v > 0 ? "+" + magnitude : (v < 0 ? "-" + magnitude : magnitude)
    }

    private static let statusLabels: [String: String] = [
        "complete": "Ready", "completed": "Ready", "awaiting_studio": "Cards ready",
        "complete_with_warnings": "Needs attention", "english_ready_paused": "English ready — paused",
        "failed": "Failed", "failed_during_analysis": "Failed", "failed_scope_check": "Failed",
        "failed_quality_gate": "Failed", "failed_orphaned": "Failed", "memo_task_created": "Task created",
        "in_progress": "Running", "ready_for_input": "Needs input", "not_started": "Not started",
        "proposed": "Proposed", "accepted": "Accepted", "rejected": "Dismissed",
    ]

    /// `humanizeStatus(value, "")`.
    static func status(_ value: String?) -> String {
        let n = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if n.isEmpty { return "" }
        if let label = statusLabels[n] { return label }
        return n.replacingOccurrences(of: #"[_-]+"#, with: " ", options: .regularExpression).capitalized
    }

    /// `radarAge`: now, minutes, hours or days ago.
    static func age(_ iso: String?) -> String {
        guard let date = MacTimeFormat.parse(iso) else { return "" }
        let sec = max(0, Int((Date().timeIntervalSince(date)).rounded()))
        if sec < 60 { return "now" }
        if sec < 3600 { return "\(Int((Double(sec) / 60).rounded()))m ago" }
        if sec < 86400 { return "\(Int((Double(sec) / 3600).rounded()))h ago" }
        return "\(Int((Double(sec) / 86400).rounded()))d ago"
    }
}

/// The website's words for the rollup's stages, actions and attention rules (i18n.js).
enum MacTrackingText {
    static func stage(_ raw: String) -> String {
        let stages = [
            "sourcing": "Sourcing", "screening": "Screening", "diligence": "Diligence", "ic": "IC",
            "portfolio": "Portfolio", "watch": "Watch", "passed": "Passed",
        ]
        return stages[raw.lowercased()] ?? "tracking.stage_\(raw)"
    }

    /// `trackingActionLabel`.
    static func action(kind: String?, label: String?) -> String {
        guard let kind, !kind.isEmpty else { return "" }
        let actions = [
            "memo_failed": "Resume failed memo", "evidence_contradicted": "Review contradicted claims",
            "memo_warnings": "Review quality warnings", "risks_open": "Research open risks",
            "evidence_missing": "Attach missing evidence", "unapproved_work": "Approve analysis",
            "documents_unresolved": "Review documents", "start_investigation": "Start investigation",
            "open_running": "Open running memo",
        ]
        return actions[kind] ?? label ?? ""
    }

    /// `trackingAttentionLabel`.
    static func attention(_ item: MacAttentionItem) -> String {
        let count = item.count ?? 0
        let kind = item.kind ?? ""
        let one = [
            "evidence_contradicted": "1 contradicted claim", "risks_open": "1 open risk",
            "evidence_missing": "1 claim without evidence", "documents_unresolved": "1 document needs review",
        ]
        if count == 1, let label = one[kind] { return label }
        let many = [
            "memo_failed": "Memo run failed", "evidence_contradicted": "\(count) contradicted claims",
            "memo_warnings": "Memo completed with warnings", "risks_open": "\(count) open risks",
            "evidence_missing": "\(count) claims without evidence", "unapproved_work": "Analysis not approved",
            "documents_unresolved": "\(count) documents need review", "no_memo": "No memo yet",
            "no_risk_map": "No risk map", "stale": "Idle \(count) days",
        ]
        return many[kind] ?? item.label ?? ""
    }

    static let metricLabels = [
        "company.metric_arr": "ARR", "company.metric_yoy_growth": "YoY Growth",
        "company.metric_valuation": "Valuation", "company.metric_tam": "TAM",
        "company.metric_quarterly_revenue": "Quarterly Revenue", "company.metric_ev_revenue": "EV / Revenue",
        "company.metric_operating_margin": "Operating Margin",
    ]

    static let inferredMetricKeys = [
        "arr": "company.metric_arr", "yoy growth": "company.metric_yoy_growth",
        "valuation": "company.metric_valuation", "tam": "company.metric_tam",
    ]
}

// MARK: - Text cut where the website's CSS cuts it

/// A run of text in one style, for lines the page cuts as CSS does.
struct MacTrackingRun {
    var text: String
    var color: Color
    var size: CGFloat
    var weight: Font.Weight = .regular
    var tracking: CGFloat = 0
    var mono = false
}

/// `text-overflow: ellipsis` cuts a line at the last character that leaves room for "…",
/// spaces included; `-webkit-line-clamp` keeps the lines as they wrapped and ends the last
/// one in "…". SwiftUI cuts differently (by words, dropping a trailing space), so these
/// lines are cut here, measured in the faces SwiftUI draws them in.
enum MacTrackingCut {
    static func nsFont(_ run: MacTrackingRun) -> NSFont {
        let name: String
        switch run.weight {
        case .medium: name = "InstrumentSans-Medium"
        case .semibold: name = "InstrumentSans-SemiBold"
        case .bold, .heavy, .black: name = "InstrumentSans-Bold"
        default: name = "InstrumentSans-Regular"
        }
        let font = NSFont(name: name, size: run.size) ?? NSFont.systemFont(ofSize: run.size)
        guard run.mono else { return font }
        let tabular: [NSFontDescriptor.FeatureKey: Int] = [
            .typeIdentifier: kNumberSpacingType,
            .selectorIdentifier: kMonospacedNumbersSelector,
        ]
        let descriptor = font.fontDescriptor.addingAttributes([.featureSettings: [tabular]])
        return NSFont(descriptor: descriptor, size: run.size) ?? font
    }

    static func attributed(_ runs: [MacTrackingRun]) -> NSAttributedString {
        let out = NSMutableAttributedString()
        for run in runs where !run.text.isEmpty {
            // Tracking, as SwiftUI's `.tracking` sets it: on top of the face's own kerning
            // (a `.kern` attribute would replace it, and 0 would switch it off).
            var attributes: [NSAttributedString.Key: Any] = [.font: nsFont(run)]
            if run.tracking != 0 { attributes[.tracking] = run.tracking }
            out.append(NSAttributedString(string: run.text, attributes: attributes))
        }
        return out
    }

    static func width(_ runs: [MacTrackingRun]) -> CGFloat {
        CGFloat(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(attributed(runs)), nil, nil, nil))
    }

    /// The runs up to a UTF-16 offset into their joined text.
    private static func prefix(_ runs: [MacTrackingRun], _ length: Int) -> [MacTrackingRun] {
        var left = length
        var out: [MacTrackingRun] = []
        for run in runs {
            let count = (run.text as NSString).length
            if left <= 0 { break }
            if count <= left {
                out.append(run)
            } else {
                var cut = run
                cut.text = (run.text as NSString).substring(to: left)
                out.append(cut)
            }
            left -= count
        }
        return out
    }

    /// The last character boundary in `line` (from `start`, before `end`) whose offset leaves
    /// `room` for the ellipsis.
    private static func boundary(in text: NSString, line: CTLine, from start: Int, to end: Int, limit: CGFloat) -> Int {
        var k = end
        while k > start {
            if CGFloat(CTLineGetOffsetForStringIndex(line, k - start, nil)) <= limit { return k }
            k = text.rangeOfComposedCharacterSequence(at: k - 1).location
        }
        return start
    }

    /// One line, cut with "…" when it runs past `width`.
    static func line(_ runs: [MacTrackingRun], ellipsis: MacTrackingRun, width: CGFloat) -> [MacTrackingRun] {
        let attr = attributed(runs)
        let line = CTLineCreateWithAttributedString(attr)
        guard CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil)) > width + 0.01 else { return runs }
        let text = attr.string as NSString
        let cut = boundary(in: text, line: line, from: 0, to: text.length, limit: width - Self.width([ellipsis]))
        return prefix(runs, cut) + [ellipsis]
    }

    /// The lines as they wrap in `width`, at most `lines` of them, the last ending in "…"
    /// when there was more.
    static func clamp(_ runs: [MacTrackingRun], ellipsis: MacTrackingRun, lines maxLines: Int, width: CGFloat) -> [[MacTrackingRun]] {
        let attr = attributed(runs)
        let setter = CTFramesetterCreateWithAttributedString(attr)
        let path = CGPath(rect: CGRect(x: 0, y: 0, width: width, height: 100_000), transform: nil)
        let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path, nil)
        guard maxLines > 0, let laid = CTFrameGetLines(frame) as? [CTLine], !laid.isEmpty else { return [runs] }
        let text = attr.string as NSString
        func trimmed(_ end: Int, from start: Int) -> Int {
            var e = end
            while e > start, let scalar = UnicodeScalar(text.character(at: e - 1)), CharacterSet.whitespacesAndNewlines.contains(scalar) { e -= 1 }
            return e
        }
        func slice(_ from: Int, _ to: Int) -> [MacTrackingRun] {
            var out: [MacTrackingRun] = []
            var cursor = 0
            for run in runs {
                let count = (run.text as NSString).length
                defer { cursor += count }
                let a = max(cursor, from), b = min(cursor + count, to)
                guard b > a else { continue }
                var piece = run
                piece.text = (run.text as NSString).substring(with: NSRange(location: a - cursor, length: b - a))
                out.append(piece)
            }
            return out
        }
        let kept = min(laid.count, maxLines)
        var lines: [[MacTrackingRun]] = []
        for index in 0..<kept {
            let range = CTLineGetStringRange(laid[index])
            let end = trimmed(range.location + range.length, from: range.location)
            guard index == kept - 1, laid.count > maxLines else {
                lines.append(slice(range.location, end))
                continue
            }
            // The last kept line, and there was more: as much of it as leaves room for "…".
            let line = CTLineCreateWithAttributedString(attr.attributedSubstring(from: NSRange(location: range.location, length: end - range.location)))
            let room = width - Self.width([ellipsis])
            let cut = CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil)) <= room
                ? end
                : boundary(in: text, line: line, from: range.location, to: end, limit: room)
            lines.append(slice(range.location, cut) + [ellipsis])
        }
        return lines
    }

    static func text(_ runs: [MacTrackingRun]) -> Text {
        runs.reduce(Text("")) { joined, run in
            let font = BSHType.bureauSans(run.size, weight: run.weight)
            return joined + Text(run.text)
                .font(run.mono ? font.monospacedDigit() : font)
                .tracking(run.tracking)
                .foregroundStyle(run.color)
        }
    }
}

/// A line of the page that is cut, as the website's `truncate` is, to the width it is given.
private struct MacTrackingLine: View {
    let runs: [MacTrackingRun]
    /// The ellipsis takes the line's own style, as CSS draws it.
    let ellipsis: MacTrackingRun
    var height: CGFloat
    @State private var width: CGFloat = 0

    var body: some View {
        Color.clear
            .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
            .overlay(alignment: .topLeading) {
                Group {
                    if width > 0 {
                        MacTrackingCut.text(MacTrackingCut.line(runs, ellipsis: ellipsis, width: width))
                            .lineLimit(1)
                            .fixedSize()
                    } else {
                        MacTrackingCut.text(runs).lineLimit(1)
                    }
                }
                .bureauLines(height, size: runs.map(\.size).max() ?? 12)
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
    }
}

/// Text that wraps and is clamped, as the website's `line-clamp-2` is, to the width it is
/// given. Each line is set on its own, where the browser sets it: a line box of a fractional
/// height (16.5) puts every other baseline on a half point, which the browser rounds.
private struct MacTrackingClamp: View {
    let runs: [MacTrackingRun]
    let ellipsis: MacTrackingRun
    let lines: Int
    let lineHeight: CGFloat
    @State private var width: CGFloat = 0

    var body: some View {
        let size = runs.first?.size ?? 12
        Group {
            if width > 0 {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(MacTrackingCut.clamp(runs, ellipsis: ellipsis, lines: lines, width: width).enumerated()), id: \.offset) { index, line in
                        let y = CGFloat(index) * lineHeight
                        MacTrackingCut.text(line)
                            .lineLimit(1)
                            .fixedSize()
                            .bureauLines(lineHeight, size: size)
                            .offset(y: y.rounded(.toNearestOrAwayFromZero) - y)
                    }
                }
            } else {
                MacTrackingCut.text(runs)
                    .lineLimit(lines)
                    .bureauLines(lineHeight, size: size)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
    }
}

// MARK: - What the page reads

/// A live quote (`GET /api/quotes`).
struct MacTrackingQuote {
    let lastPrice: Double?
    let changePct1d: Double?
    let currency: String?
    let asOf: String?
    let beta: Double?
    let sector: String?

    init(_ json: MacTrackingJSON) {
        lastPrice = json["last_price"].number
        changePct1d = json["change_pct_1d"].number
        currency = json["currency"].truthy
        asOf = json["as_of"].truthy
        beta = json["beta"].number
        sector = json["sector"].truthy
    }

    /// `quoteStaleness`: minutes since the quote, stale from twenty.
    var staleness: (minutes: Int, stale: Bool)? {
        guard let date = MacTimeFormat.parse(asOf) else { return nil }
        let minutes = max(0, Int((Date().timeIntervalSince(date) / 60).rounded()))
        return (minutes, minutes >= 20)
    }
}

/// A story from the research feed (`GET /api/external/feed`, kind "news").
struct MacTrackingNews: Identifiable {
    let id: String
    let title: String
    let summary: String
    let company: String
    let capturedAt: String?

    init?(_ json: MacTrackingJSON) {
        guard json["kind"].text == "news", let id = json["id"].truthy else { return nil }
        self.id = id
        title = json["title"].text ?? ""
        summary = json["summary"].text ?? ""
        company = json["company"].text ?? ""
        capturedAt = json["captured_at"].truthy
    }
}

/// One company's card, as `cards` in TrackingView.vue computes it.
struct MacTrackingCard: Identifiable {
    struct Price {
        let day: Double?
        let vs: Double?
        let last: Double?
        let currency: String
        let live: Bool
    }

    struct Metric: Hashable {
        let label: String
        let value: String
    }

    let company: MacCompany
    let row: MacRollupRow?
    let status: String?
    let description: String?
    let facts: String
    let funding: String?
    let earnings: String?
    let event: (text: String, date: String?)?
    let people: String
    let products: String
    let competitors: String
    let metrics: [Metric]
    let coverage: [String]
    let price: Price?

    var id: String { company.id }
    var lastPrice: String? { price.flatMap { MacTrackingFormat.price($0.last, currency: $0.currency) } }
    var priceUp: Bool { price?.day.map { $0 >= 0 } ?? false }
    var live: Bool { price?.live ?? false }

    init(company: MacCompany, record: MacTrackingJSON, row: MacRollupRow?, quote: MacTrackingQuote?, headline: MacTrackingNews?) {
        self.company = company
        self.row = row
        status = company.bureauStatusLine
        description = record["description"].truthy
        facts = Self.facts(record)
        funding = Self.funding(record)
        earnings = Self.earnings(record)
        event = Self.event(record, headline: headline)
        people = Self.people(record)
        products = Self.named(record["products"].array)
        let cards = record["competitor_cards"].array
        competitors = Self.named(cards.isEmpty ? record["competitors"].array : cards)
        metrics = Self.metrics(record, company: company)
        coverage = Self.coverage(row)
        price = Self.price(record, row: row, quote: quote)
    }

    private static func facts(_ r: MacTrackingJSON) -> String {
        var parts: [String] = []
        if let hq = r["hq"].truthy { parts.append(hq) }
        if let year = r["founded_year"].truthy { parts.append("Founded \(year)") }
        if let band = r["employee_band"].truthy { parts.append("\(band) employees") }
        let host = (r["website"].text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"^https?://"#, with: "", options: [.regularExpression, .caseInsensitive])
            .replacingOccurrences(of: #"/$"#, with: "", options: .regularExpression)
        if !host.isEmpty { parts.append(host) }
        return parts.joined(separator: " · ")
    }

    private static func money(_ v: MacTrackingJSON) -> String? {
        v.isPending ? nil : MacTrackingFormat.compactNumber(v, currency: true)
    }

    private static func funding(_ r: MacTrackingJSON) -> String? {
        let f = r["latest_funding"]
        guard case .object = f else { return nil }
        var parts: [String] = []
        if let round = f["round"].truthy { parts.append(round) }
        if let amount = money(f["amount_usd"]) { parts.append(amount) }
        if let post = money(f["post_money_usd"]) { parts.append("post-money \(post)") }
        if let lead = f["lead_investor"].truthy { parts.append("led by \(lead)") }
        if let raised = money(r["total_funding_usd"]) { parts.append("Total raised: \(raised)") }
        if let date = f["date"].truthy, let iso = MacTrackingFormat.isoDate(date) { parts.append(iso) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private static func earnings(_ r: MacTrackingJSON) -> String? {
        let e = r["latest_earnings"]
        guard case .object = e else { return nil }
        var parts: [String] = []
        if let period = e["period"].truthy { parts.append(period) }
        if let yoy = e["revenue_yoy"].truthy { parts.append("revenue \(yoy) YoY") }
        if let eps = e["eps"].truthy { parts.append("EPS \(eps)") }
        if let beat = e["beat_or_miss"].truthy { parts.append(beat) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private static func event(_ r: MacTrackingJSON, headline: MacTrackingNews?) -> (text: String, date: String?)? {
        let highlight = r["highlight_2026"]
        if let text = highlight["headline"].truthy { return (text, highlight["date"].truthy) }
        // `recent_news || company_news`: an empty list still wins over the other.
        let list = r["recent_news"].isNull ? r["company_news"].array : r["recent_news"].array
        if let first = list.first, case .object = first {
            let text = first["headline"].truthy ?? first["title"].truthy ?? first["summary"].text ?? ""
            return (text, first["date"].truthy ?? first["published_at"].truthy)
        }
        if let headline, !headline.title.isEmpty { return (headline.title, headline.capturedAt) }
        return nil
    }

    private static func people(_ r: MacTrackingJSON) -> String {
        let team = r["team_profiles"].array
        let list = team.isEmpty ? r["key_people"].array : team
        return list.prefix(3).compactMap { person -> String? in
            guard let name = person["name"].truthy ?? person.truthy else { return nil }
            if let role = person["role"].truthy { return "\(name) (\(role))" }
            return name
        }
        .joined(separator: " · ")
    }

    private static func named(_ items: [MacTrackingJSON]) -> String {
        items.compactMap { $0.truthy ?? $0["name"].truthy }.prefix(3).joined(separator: " · ")
    }

    /// `companySummaryMetrics`, less what is still pending, at most four.
    private static func metrics(_ r: MacTrackingJSON, company: MacCompany) -> [Metric] {
        typealias Raw = (label: String, key: String?, value: MacTrackingJSON)
        var raw: [Raw] = r["metrics"].array.map { ($0["label"].text ?? "", $0["label_key"].truthy, $0["value"]) }
        if raw.isEmpty {
            let isPublic = r["company_type"].text == "public" || r["status"].text == "public" || r["ticker"].truthy != nil
            raw = isPublic ? publicMetrics(r) : privateMetrics(r)
        }
        return raw.filter { !$0.value.isPending }.prefix(4).map { metric in
            let key = metric.key ?? MacTrackingText.inferredMetricKeys[metric.label.trimmingCharacters(in: .whitespaces).lowercased()]
            let label = key.map { MacTrackingText.metricLabels[$0] ?? $0 } ?? metric.label
            return Metric(label: label, value: MacTrackingFormat.metricValue(label: metric.label, metric.value))
        }
    }

    private static func publicMetrics(_ r: MacTrackingJSON) -> [(label: String, key: String?, value: MacTrackingJSON)] {
        let disclosure = (r["latest_earnings"]["revenue_yoy"].truthy ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        func match(_ pattern: String, group: Int) -> String? {
            guard let re = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
                  let m = re.firstMatch(in: disclosure, range: NSRange(disclosure.startIndex..., in: disclosure)),
                  let range = Range(m.range(at: group), in: disclosure) else { return nil }
            return String(disclosure[range])
        }
        let revenue = match(#"\$[\d,.]+\s*[KMBT]?"#, group: 0)
        let growth = match(#"([+-]?\d+(?:\.\d+)?)%\s*(?:YoY)?"#, group: 1).flatMap(Double.init)
        let snapshot = r["trader_snapshot"]
        let ev = snapshot["heat_card"]["valuation"]["ev_revenue_current"]
        let margin = snapshot["research_overview"]["financial_quality"]["metrics"].array.first {
            ($0["label_en"].truthy ?? $0["label"].truthy ?? "").lowercased().contains("operating margin")
        }
        return [
            ("Quarterly Revenue", "company.metric_quarterly_revenue", revenue.map(MacTrackingJSON.string) ?? .string("Unknown")),
            ("YoY Growth", "company.metric_yoy_growth", growth.map(MacTrackingJSON.number) ?? .string("Unknown")),
            ("EV / Revenue", "company.metric_ev_revenue", ev.isNull ? .string("Unknown") : .string("\(ev.text ?? "")x")),
            ("Operating Margin", "company.metric_operating_margin", margin.flatMap { $0["value"].truthy }.map(MacTrackingJSON.string) ?? .string("Unknown")),
        ]
    }

    private static func privateMetrics(_ r: MacTrackingJSON) -> [(label: String, key: String?, value: MacTrackingJSON)] {
        let post = r["latest_funding"]["post_money_usd"]
        return [
            ("ARR", "company.metric_arr", .string("Unknown")),
            ("YoY Growth", "company.metric_yoy_growth", .string("Unknown")),
            ("Valuation", "company.metric_valuation", post.truthy != nil ? post : .string("Unknown")),
            ("TAM", "company.metric_tam", .string("Unknown")),
        ]
    }

    private static func coverage(_ row: MacRollupRow?) -> [String] {
        guard let row else { return [] }
        var bits: [String] = []
        if let total = row.risks?.total, total > 0 { bits.append("\(row.risks?.researched ?? 0)/\(total) researched") }
        if let total = row.evidence?.total, total > 0 { bits.append("\(row.evidence?.supported ?? 0)/\(total) supported") }
        if let count = row.news?.recentCount, count > 0 { bits.append("\(count) news") }
        if let docs = row.documents?.total, docs > 0 { bits.append("\(docs) docs") }
        return bits
    }

    /// `priceBits`: the live quote first, then the rollup's price, then the stock snapshot.
    private static func price(_ r: MacTrackingJSON, row: MacRollupRow?, quote: MacTrackingQuote?) -> Price? {
        let card = row?.price
        let fallback = r["trader_snapshot"]["price_card"]
        let day = quote?.changePct1d ?? card?.changePct1d ?? fallback["change_pct_1d"].number
        let vs = fallback["vs_sp500_30d_pct"].number ?? card?.changePct30d ?? fallback["change_pct_30d"].number
        let last = quote?.lastPrice ?? card?.lastPrice ?? fallback["last_price"].number
        if day == nil && vs == nil && last == nil { return nil }
        let currency = quote?.currency ?? card?.currency ?? fallback["currency"].truthy ?? "USD"
        let live = quote.map { $0.lastPrice != nil || $0.changePct1d != nil } ?? false
        return Price(day: day, vs: vs, last: last, currency: currency, live: live)
    }
}

// MARK: - The page

/// What the page last read from a server, kept for the session so that coming back to the
/// page paints at once while it reads again.
@MainActor
private enum MacTrackingMemory {
    static var server = ""
    static var records: [String: MacTrackingJSON] = [:]
    static var rollup: (ids: [String], rollup: MacRollup)?
    static var quotes: [String: MacTrackingQuote] = [:]
    static var feed: [MacTrackingNews] = []

    /// Forgets another server's reads.
    static func check() {
        let current = MacConfig.baseURL.absoluteString
        guard server != current else { return }
        server = current
        records = [:]
        rollup = nil
        quotes = [:]
        feed = []
    }
}

struct MacBureauTrackingView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    @State private var followedOnly = false
    @State private var records: [String: MacTrackingJSON]
    @State private var rollup: MacRollup?
    @State private var rollupLoading = false
    @State private var rollupError = false
    @State private var quotes: [String: MacTrackingQuote]
    @State private var feed: [MacTrackingNews]
    @State private var lotTicker = ""
    @State private var lotShares = ""
    @State private var lotCost = ""
    @State private var windowWidth: CGFloat = 1280
    @State private var gridWidth: CGFloat = 0
    @State private var sheet: MacTrackingSheet?
    @State private var showReserves = false
    @State private var showAddHolding = false
    @State private var reunderwritingOnly = false

    init() {
        MacTrackingMemory.check()
        _records = State(initialValue: MacTrackingMemory.records)
        _rollup = State(initialValue: MacTrackingMemory.rollup?.rollup)
        _quotes = State(initialValue: MacTrackingMemory.quotes)
        _feed = State(initialValue: MacTrackingMemory.feed)
    }

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    // MARK: What is on the page

    private var followedIds: [String] { store.validFollowedIds }
    private var followedSet: Set<String> { Set(followedIds) }

    private var trackedCompanies: [MacCompany] {
        store.companies.filter { followedSet.contains($0.id) }
    }

    /// Followed companies first, then A to Z (sortCompanies with the follow set as favorites).
    private var visibleCompanies: [MacCompany] {
        let followed = followedSet
        let rows = followedOnly ? store.companies.filter { followed.contains($0.id) } : store.companies
        return rows.enumerated().sorted { a, b in
            let fa = followed.contains(a.element.id), fb = followed.contains(b.element.id)
            if fa != fb { return fa }
            let order = (a.element.name ?? "").localizedCompare(b.element.name ?? "")
            if order != .orderedSame { return order == .orderedAscending }
            return a.offset < b.offset
        }
        .map(\.element)
    }

    private var visibleIds: [String] { visibleCompanies.map(\.id) }

    private func isPublic(_ company: MacCompany) -> Bool {
        company.companyType?.lowercased() == "public" || company.status?.lowercased() == "public"
            || !(company.ticker ?? "").trimmingCharacters(in: .whitespaces).isEmpty
    }

    private func tickers(of companies: [MacCompany]) -> [String] {
        var seen = Set<String>()
        return companies.compactMap { company in
            guard isPublic(company) else { return nil }
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            guard !ticker.isEmpty, seen.insert(ticker).inserted else { return nil }
            return ticker
        }
    }

    /// The tape's tickers, plus any held in the book so every lot is marked.
    private var quoteTickers: [String] {
        var list = tickers(of: visibleCompanies)
        for lot in store.bookLots where !list.contains(lot.ticker.uppercased()) {
            list.append(lot.ticker.uppercased())
        }
        return list
    }

    private var rowsById: [String: MacRollupRow] {
        Dictionary((rollup?.companies ?? []).map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
    }

    private var work: [MacAttentionItem] {
        let ids = Set(visibleIds)
        return (rollup?.attention ?? []).filter { ids.contains($0.companyId ?? "") }
    }

    private var cards: [MacTrackingCard] {
        let rows = rowsById
        return visibleCompanies.map { company in
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            return MacTrackingCard(
                company: company,
                record: records[company.id] ?? .null,
                row: rows[company.id],
                quote: ticker.isEmpty ? nil : quotes[ticker],
                headline: relatedNews(for: [company], limit: 1).first
            )
        }
    }

    /// `relatedNews`: stories whose title, summary or company names one of these.
    private func relatedNews(for companies: [MacCompany], limit: Int) -> [MacTrackingNews] {
        guard !companies.isEmpty else { return [] }
        let needles = companies.flatMap { [$0.name, $0.ticker] }.compactMap { $0?.lowercased() }.filter { !$0.isEmpty }
        return feed
            .filter { item in
                let hay = "\(item.title) \(item.summary) \(item.company)".lowercased()
                return needles.contains { hay.contains($0) }
            }
            .sorted { ($0.capturedAt ?? "") > ($1.capturedAt ?? "") }
            .prefix(limit)
            .map { $0 }
    }

    /// `xl:grid-cols-3`, `sm:grid-cols-2`: the website's breakpoints are the window's width.
    private var columns: Int { windowWidth >= 1280 ? 3 : (windowWidth >= 640 ? 2 : 1) }

    // MARK: Body

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauPageHeader("Tracking", subtitle: "The book — news, price, and memo state.") {
                    headerActions
                }
                .padding(.bottom, 24)

                if !trackedCompanies.isEmpty {
                    MacTrackingBook(
                        tracked: trackedCompanies,
                        records: records,
                        quotes: quotes,
                        lotTicker: $lotTicker,
                        lotShares: $lotShares,
                        lotCost: $lotCost,
                        submit: submitLot
                    )
                    .padding(.bottom, 20)
                }

                if store.loading && store.companies.isEmpty {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading…")
                    }
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .bureauLines(20, size: 14)
                } else if followedOnly && cards.isEmpty {
                    emptyCard {
                        VStack(spacing: 8) {
                            Text("Nothing tracked yet")
                                .font(BSHType.bureauSans(15, weight: .semibold))
                                .tracking(-0.15)
                                .foregroundStyle(ink.ink)
                            Text("Star a company in the sidebar to start tracking its research.")
                                .font(BSHType.bureauSans(12))
                                .foregroundStyle(ink.muted)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: 448)
                        }
                    }
                } else if store.companies.isEmpty {
                    emptyCard {
                        Text("No companies in this list yet.")
                            .font(BSHType.bureauSans(14))
                            .tracking(-0.084)
                            .foregroundStyle(ink.muted)
                    }
                } else {
                    MacTrackingTape(tickers: tickers(of: visibleCompanies), quotes: quotes)
                        .padding(.bottom, 24)

                    if !work.isEmpty {
                        VStack(spacing: 8) {
                            ForEach(work) { item in
                                MacTrackingAttentionRow(item: item, ink: ink)
                            }
                        }
                        .padding(.bottom, 24)
                    }

                    if rollupError {
                        HStack(spacing: 8) {
                            Text("Could not load tracking data.")
                                .foregroundStyle(ink.danger)
                            Button("Try again") { Task { await loadRollup() } }
                                .buttonStyle(.plain)
                                .foregroundStyle(ink.accent)
                        }
                        .font(BSHType.bureauSans(12))
                        .bureauLines(16, size: 12)
                        .padding(.bottom, 16)
                    }

                    grid
                    newsSection
                        .padding(.top, 40)
                }

                MacTrackingHoldings(
                    open: { sheet = MacTrackingSheet(kind: .holding, companyId: $0) },
                    showReserves: $showReserves,
                    showAddHolding: $showAddHolding
                )
                .padding(.top, 40)

                MacTrackingMonitoring(
                    reunderwritingOnly: $reunderwritingOnly,
                    open: { sheet = MacTrackingSheet(kind: .monitoring, companyId: $0) }
                )
                .padding(.top, 40)
            }
            .padding(.horizontal, 32)
            .padding(.top, 16)
            .padding(.bottom, 48)
            .frame(maxWidth: 1240, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .background(ink.sheet)
        .background(MacTrackingWindowWidth(width: $windowWidth))
        .task(id: store.companies.map(\.id).joined(separator: ",")) {
            await loadRecords()
            await loadFeed()
        }
        .task(id: visibleIds.joined(separator: ",")) {
            await loadRollup()
        }
        .task(id: quoteTickers.joined(separator: ",")) {
            // The website polls its quotes every 45 seconds while the page is open.
            while !Task.isCancelled {
                await loadQuotes()
                try? await Task.sleep(for: .seconds(45))
            }
        }
        .task {
            // The book's lots are the desk's, shared with the website and the iPad.
            await store.refreshDeskPrefs()
        }
        .onChange(of: followedIds.isEmpty) { _, empty in
            if empty { followedOnly = false }
        }
        .sheet(item: $sheet) { item in
            MacTrackingSheetView(item: item)
                .environmentObject(store)
        }
        .sheet(isPresented: $showReserves) { MacReservesPlannerSheet().environmentObject(store) }
        .sheet(isPresented: $showAddHolding) {
            MacAddHoldingSheet { id in
                // Open the new holding once the picker has gone.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    sheet = MacTrackingSheet(kind: .holding, companyId: id)
                }
            }
            .environmentObject(store)
        }
    }

    // MARK: Header

    @ViewBuilder
    private var headerActions: some View {
        if !followedIds.isEmpty {
            MacTrackingFilter(followedOnly: $followedOnly, off: ("All", store.companies.count), on: ("Followed", followedIds.count))
        }
        MacBureauButton(store.pipelineSyncing ? "Syncing…" : "Sync news", size: .small, busy: store.pipelineSyncing) {
            // The website asks before anything that spends tokens.
            guard MacTokenConfirm.ask() else { return }
            store.syncAllTracking()
        }
        .disabled(store.pipelineSyncing || followedIds.isEmpty || !store.canRunTasks)
        .help(followedIds.isEmpty
              ? "Follow companies to sync their tracked news"
              : "Refresh tracked news for every followed company (runs on the server; can take minutes)")
        MacBureauButton("Refresh", icon: "refresh-cw", size: .small, busy: rollupLoading) {
            Task { await refresh() }
        }
        .disabled(rollupLoading)
    }

    // MARK: Cards

    private var grid: some View {
        let cards = cards
        let count = max(1, columns)
        let width = gridWidth > 0 ? (gridWidth - CGFloat(count - 1) * 12) / CGFloat(count) : 0
        let rows = stride(from: 0, to: cards.count, by: count).map { Array(cards[$0..<min($0 + count, cards.count)]) }
        return VStack(alignment: .leading, spacing: 12) {
            ForEach(rows, id: \.first?.id) { row in
                HStack(alignment: .top, spacing: 12) {
                    ForEach(row) { card in
                        MacTrackingCardView(
                            card: card,
                            followed: followedSet.contains(card.id),
                            ink: ink
                        )
                        .frame(width: max(0, width))
                        .frame(maxHeight: .infinity, alignment: .top)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { gridWidth = $0 }
    }

    // MARK: News

    private var newsSection: some View {
        let stories = relatedNews(for: visibleCompanies, limit: 10)
        return VStack(alignment: .leading, spacing: 0) {
            Text("News")
                .font(BSHType.bureauSans(15, weight: .semibold))
                .tracking(-0.15)
                .foregroundStyle(ink.ink)
                .bureauLines(20, size: 15)
            Text("Stories that mention these companies.")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .bureauLines(14, size: 11)
                .padding(.top, 2)
            if stories.isEmpty {
                Text("No related news in the feed yet.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .bureauLines(16, size: 12)
                    .padding(.top, 12)
            } else {
                VStack(spacing: 4) {
                    ForEach(stories) { story in
                        MacTrackingNewsRow(story: story, ink: ink) { open(story) }
                    }
                }
                .padding(.top, 12)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The website opens the story's own page (`/news/:id`); here it opens beside the page.
    private func open(_ story: MacTrackingNews) {
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(MacConfig.webURL(path: "news/\(story.id)"))
        }
    }

    private func emptyCard<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        content()
            .padding(32)
            .frame(maxWidth: .infinity)
            .modifier(MacTrackingTray(ink: ink))
    }

    // MARK: Loading (every call a GET)

    /// The website's Refresh reloads the rollup; here it also brings the rest of the page up
    /// to date, the Mac's holdings and decisions included.
    private func refresh() async {
        await loadRollup()
        async let records: Void = loadRecords()
        async let quotes: Void = loadQuotes()
        async let feed: Void = loadFeed()
        async let holdings: Void = store.loadPortfolioDashboard()
        async let decisions: Void = store.loadPipeline()
        _ = await (records, quotes, feed, holdings, decisions)
    }

    private func loadRollup() async {
        let ids = visibleIds
        guard !ids.isEmpty else {
            rollup = nil
            rollupError = false
            rollupLoading = false
            return
        }
        rollupLoading = true
        rollupError = false
        defer { rollupLoading = false }
        do {
            let fresh = try await MacAPIClient.shared.fetchTrackingRollup(companyIds: ids)
            guard ids == visibleIds else { return }
            rollup = fresh
            MacTrackingMemory.rollup = (ids, fresh)
        } catch is CancellationError {
        } catch {
            rollupError = true
        }
    }

    /// The company records as the website reads them (`GET /api/companies`), each by id.
    private func loadRecords() async {
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: "companies") else { return }
        // A long list is a lot of JSON: read it off the main thread.
        let map = await Task.detached(priority: .userInitiated) { () -> [String: MacTrackingJSON]? in
            guard let rows = try? JSONDecoder().decode([MacTrackingJSON].self, from: data) else { return nil }
            var map: [String: MacTrackingJSON] = [:]
            for row in rows {
                if let id = row["id"].truthy { map[id] = row }
            }
            return map
        }.value
        guard let map else { return }
        records = map
        MacTrackingMemory.records = map
    }

    private func loadQuotes() async {
        let symbols = quoteTickers
        guard !symbols.isEmpty else {
            quotes = [:]
            return
        }
        var components = URLComponents()
        components.queryItems = symbols.map { URLQueryItem(name: "ticker", value: $0) }
        let query = MacConfig.escapePlus(components.percentEncodedQuery) ?? ""
        // Keep the last good tape rather than flashing empty on a blip.
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: "quotes?\(query)"),
              let payload = try? JSONDecoder().decode(MacTrackingJSON.self, from: data),
              case .object(let rows) = payload["quotes"] else { return }
        var next: [String: MacTrackingQuote] = [:]
        for (ticker, row) in rows { next[ticker.uppercased()] = MacTrackingQuote(row) }
        quotes = next
        MacTrackingMemory.quotes = next
    }

    private func loadFeed() async {
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: "external/feed"),
              let rows = try? JSONDecoder().decode([MacTrackingJSON].self, from: data) else { return }
        feed = rows.compactMap(MacTrackingNews.init)
        MacTrackingMemory.feed = feed
    }

    // MARK: The book's lots

    /// `upsertBookLot`: one lot per ticker; the fields clear whether or not it was valid.
    private func submitLot() {
        let ticker = lotTicker.trimmingCharacters(in: .whitespaces).uppercased()
        let shares = Double(lotShares.trimmingCharacters(in: .whitespaces))
        let cost = Double(lotCost.trimmingCharacters(in: .whitespaces))
        lotTicker = ""
        lotShares = ""
        lotCost = ""
        guard !ticker.isEmpty, let shares, shares.isFinite, shares > 0, let cost, cost.isFinite, cost >= 0 else { return }
        Task {
            for lot in store.bookLots where lot.ticker.uppercased() == ticker {
                guard await store.removeLot(id: lot.id) else { return }
            }
            await store.addLot(ticker: ticker, shares: shares, costBasis: cost)
        }
    }
}

// MARK: - Header filter

/// `.segmented` with the website's counts beside each label (All and Followed).
private struct MacTrackingFilter: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var followedOnly: Bool
    let off: (title: String, count: Int)
    let on: (title: String, count: Int)
    @Namespace private var slip
    @State private var hovered: Bool?

    init(followedOnly: Binding<Bool>, off: (title: String, count: Int), on: (title: String, count: Int)) {
        _followedOnly = followedOnly
        self.off = off
        self.on = on
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 2) {
            segment(off.title, count: off.count, value: false, ink: ink)
            segment(on.title, count: on.count, value: true, ink: ink)
        }
        .padding(3)
        .background(
            Capsule()
                .fill(ink.ink(0.06))
                .overlay(MacTrackingInsetShadow(shape: Capsule(), color: ink.shadow(0.06), blur: 2))
        )
        .fixedSize()
    }

    private func segment(_ title: String, count: Int, value: Bool, ink: MacBureauPageInk) -> some View {
        let chosen = followedOnly == value
        return Button {
            guard !chosen else { return }
            withAnimation(.spring(response: 0.3, dampingFraction: 0.82)) { followedOnly = value }
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(title)
                    .font(BSHType.bureauSans(12, weight: chosen ? .semibold : .medium))
                    .foregroundStyle(chosen || hovered == value ? ink.ink : ink.ink(0.62))
                Text("\(count)")
                    .font(BSHType.bureauSans(11, weight: chosen ? .semibold : .medium).monospacedDigit())
                    .tracking(-0.11)
                    .foregroundStyle(ink.subtle)
            }
            .fixedSize()
            .bureauLines(16, size: 12)
            .padding(.horizontal, 12)
            .padding(.top, 3)
            .frame(height: 22, alignment: .top)
            .background {
                if chosen {
                    Capsule()
                        .fill(ink.raised)
                        .overlay(Capsule().inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
                        .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                        .matchedGeometryEffect(id: "slip", in: slip)
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { inside in
            if inside { hovered = value } else if hovered == value { hovered = nil }
        }
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }
}

// MARK: - Surfaces

/// `--shadow` under Bureau: a hairline ring inside the edge and a soft shadow along its top.
struct MacTrackingInsetShadow<S: InsettableShape>: View {
    let shape: S
    let color: Color
    var blur: CGFloat = 2
    var y: CGFloat = 1

    var body: some View {
        GeometryReader { proxy in
            let rect = CGRect(origin: .zero, size: proxy.size)
            Path { path in
                path.addRect(rect.insetBy(dx: -24, dy: -24))
                path.addPath(shape.path(in: rect))
            }
            .fill(color, style: FillStyle(eoFill: true))
            .offset(y: y)
            // SwiftUI's blur radius is twice the Gaussian deviation CSS derives from its blur (blur / 2).
            .blur(radius: blur)
            .mask(shape)
        }
        .allowsHitTesting(false)
    }
}

/// `.group-card`, `.news-grouped`, `.ticker-tape`: a tray pressed into the sheet.
struct MacTrackingTray: ViewModifier {
    let ink: MacBureauPageInk
    var radius: CGFloat = 14
    var fillOpacity: Double = 1

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        content
            .background(shape.fill(ink.tray.opacity(fillOpacity)))
            .overlay(
                ZStack {
                    MacTrackingInsetShadow(
                        shape: shape,
                        color: ink.dark ? Color.black.opacity(0.35) : ink.shadow(0.04),
                        blur: ink.dark ? 3 : 2
                    )
                    shape.strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.ink(0.035), lineWidth: 1)
                }
                .allowsHitTesting(false)
            )
    }
}

/// The website's `live-pulse` dot.
private struct MacTrackingPulse: View {
    let color: Color
    var size: CGFloat = 6
    @State private var dim = false

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .opacity(dim ? 0.35 : 1)
            .scaleEffect(dim ? 0.72 : 1)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.85).repeatForever(autoreverses: true)) { dim = true }
            }
    }
}

// MARK: - Book P&L

/// The tray of the book (shown once anything is followed): its beta and sector mix, the
/// day's P&L on the lots entered, the form that adds a lot, the lots, and the day's movers.
private struct MacTrackingBook: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let tracked: [MacCompany]
    let records: [String: MacTrackingJSON]
    let quotes: [String: MacTrackingQuote]
    @Binding var lotTicker: String
    @Binding var lotShares: String
    @Binding var lotCost: String
    let submit: () -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private struct Mover: Identifiable {
        let ticker: String
        let change: Double
        var id: String { ticker }
    }

    private struct Lens {
        var sectorMix: [(sector: String, pct: Double)] = []
        var avgBeta: Double?
        var movers: [Mover] = []
    }

    /// `bookConcentration`: the followed names' sector mix and beta, weighted by price.
    private var lens: Lens {
        var sectors: [(String, Double)] = []
        var weightedBeta = 0.0, betaWeight = 0.0
        var movers: [Mover] = []
        for company in tracked {
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            guard !ticker.isEmpty else { continue }
            let quote = quotes[ticker]
            let record = records[company.id] ?? .null
            let last = quote?.lastPrice
            let beta = quote?.beta ?? record["trader_snapshot"]["price_card"]["beta"].number
            let sector = company.sector.flatMap { $0.isEmpty ? nil : $0 }
                ?? record["trader_snapshot"]["profile"]["sector"].truthy
                ?? quote?.sector
                ?? "Unknown"
            let weight = last ?? 1
            if let i = sectors.firstIndex(where: { $0.0 == sector }) { sectors[i].1 += weight } else { sectors.append((sector, weight)) }
            if let beta {
                weightedBeta += beta * weight
                betaWeight += weight
            }
            if let change = quote?.changePct1d { movers.append(Mover(ticker: ticker, change: change)) }
        }
        let total = sectors.reduce(0) { $0 + $1.1 }
        let divisor = total == 0 ? 1 : total
        var lens = Lens()
        lens.sectorMix = sectors.map { ($0.0, $0.1 / divisor * 100) }
            .enumerated().sorted { $0.element.1 != $1.element.1 ? $0.element.1 > $1.element.1 : $0.offset < $1.offset }
            .map(\.element).prefix(6).map { $0 }
        lens.avgBeta = betaWeight > 0 ? weightedBeta / betaWeight : nil
        lens.movers = movers.enumerated()
            .sorted { abs($0.element.change) != abs($1.element.change) ? abs($0.element.change) > abs($1.element.change) : $0.offset < $1.offset }
            .map(\.element).prefix(6).map { $0 }
        return lens
    }

    private struct LotRow: Identifiable {
        let id: String
        let ticker: String
        let shares: Double
        let cost: Double
        let unrealized: Double?
        let dayPnl: Double?
    }

    /// `bookPnl`: each lot marked at its live quote.
    private var pnl: (rows: [LotRow], unrealized: Double, dayPnl: Double) {
        var rows: [LotRow] = []
        var marketValue = 0.0, costBasis = 0.0, dayPnl = 0.0
        for lot in store.bookLots where lot.shares.isFinite && lot.shares > 0 && lot.costBasis.isFinite && lot.costBasis >= 0 {
            let quote = quotes[lot.ticker.uppercased()]
            let value = quote?.lastPrice.map { $0 * lot.shares }
            let cost = lot.costBasis * lot.shares
            var day: Double?
            if let last = quote?.lastPrice, let change = quote?.changePct1d {
                let usd = (last / (1 + change / 100)) * lot.shares * (change / 100)
                if usd.isFinite { day = usd }
            }
            if let value { marketValue += value }
            costBasis += cost
            if let day { dayPnl += day }
            rows.append(LotRow(id: lot.id, ticker: lot.ticker.uppercased(), shares: lot.shares, cost: lot.costBasis,
                               unrealized: value.map { $0 - cost }, dayPnl: day))
        }
        rows = rows.enumerated()
            .sorted { abs($0.element.dayPnl ?? 0) != abs($1.element.dayPnl ?? 0) ? abs($0.element.dayPnl ?? 0) > abs($1.element.dayPnl ?? 0) : $0.offset < $1.offset }
            .map(\.element)
        return (rows, marketValue - costBasis, dayPnl)
    }

    var body: some View {
        let lens = lens
        let pnl = pnl
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Book P&L")
                        .font(BSHType.bureauSans(12, weight: .semibold))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                    if let beta = lens.avgBeta {
                        // Each sector is a span 8pt after the space the template leaves.
                        lens.sectorMix.prefix(3).reduce(Text("Avg beta \(MacTrackingFormat.toFixed(beta, 2))")) { line, row in
                            line + Text(" ").kerning(8) + Text("\(row.sector) \(MacTrackingFormat.toFixed(row.pct, 0))%")
                        }
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.secondary)
                        .bureauLines(16, size: 12)
                    }
                }
                Spacer(minLength: 0)
                if !pnl.rows.isEmpty {
                    VStack(alignment: .trailing, spacing: 0) {
                        Text("Day \(MacTrackingFormat.signedMoneyUSD(pnl.dayPnl))")
                            .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                            .tracking(-0.15)
                            .foregroundStyle(pnl.dayPnl >= 0 ? ink.success : ink.danger)
                            .bureauLines(20, size: 15)
                        Text("Unrealized \(MacTrackingFormat.moneyUSD(pnl.unrealized))")
                            .font(BSHType.bureauSans(11))
                            .tracking(0.066)
                            .foregroundStyle(ink.muted)
                            .bureauLines(14, size: 11)
                    }
                } else {
                    Text("Add shares and cost to mark the book to market.")
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .bureauLines(14, size: 11)
                }
            }

            HStack(alignment: .bottom, spacing: 8) {
                lotField("Ticker", placeholder: "NVDA", text: $lotTicker)
                lotField("Shares", placeholder: "", text: $lotShares)
                lotField("Cost", placeholder: "", text: $lotCost)
                MacTrackingRangeItem(ink: ink, action: submit) {
                    Text("Add lot")
                }
            }
            .padding(.top, 12)

            if !pnl.rows.isEmpty {
                VStack(spacing: 4) {
                    ForEach(pnl.rows) { row in
                        lotRow(row)
                    }
                }
                .padding(.top, 12)
            }

            if !lens.movers.isEmpty {
                HStack(spacing: 8) {
                    ForEach(lens.movers) { mover in
                        MacTrackingRangeItem(ink: ink, action: { store.showTicker(mover.ticker) }) {
                            Text(mover.ticker)
                            + Text(" ")
                            + Text(MacTrackingFormat.signed(mover.change) ?? "").foregroundStyle(mover.change >= 0 ? ink.success : ink.danger)
                        }
                    }
                }
                .padding(.top, 12)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(MacTrackingTray(ink: ink))
    }

    /// `.yf-screener-field`: a label over a field.
    private func lotField(_ label: String, placeholder: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .bureauLines(14, size: 11)
            MacTrackingLotField(placeholder: placeholder, text: text, ink: ink, onSubmit: submit)
        }
        .frame(width: 182)
    }

    /// A lot: its ticker (to the market desk), shares at cost, what it has made, Remove.
    private func lotRow(_ row: LotRow) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Button {
                store.showTicker(row.ticker)
            } label: {
                HStack(alignment: .firstTextBaseline, spacing: 0) {
                    Text(row.ticker)
                        .foregroundStyle(ink.ink)
                    Text(" ")
                    Text("\(MacTrackingJSON.jsNumber(row.shares)) @ \(MacTrackingFormat.moneyUSD(row.cost))")
                        .foregroundStyle(ink.muted)
                        .padding(.leading, 8)
                }
                .font(BSHType.bureauSans(12).monospacedDigit())
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            Spacer(minLength: 8)
            Text(MacTrackingFormat.signedMoneyUSD(row.unrealized))
                .font(BSHType.bureauSans(12))
                .foregroundStyle((row.unrealized ?? 0) >= 0 ? ink.success : ink.danger)
            Button {
                Task { await store.removeLot(id: row.id) }
            } label: {
                Text("Remove")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
            }
            .buttonStyle(.plain)
        }
        .bureauLines(16, size: 12)
    }
}

/// The field of `.yf-screener-field`: 8pt corners on the tray's color, ruled in ink.
private struct MacTrackingLotField: View {
    let placeholder: String
    @Binding var text: String
    let ink: MacBureauPageInk
    let onSubmit: () -> Void
    @FocusState private var focused: Bool

    var body: some View {
        TextField("", text: $text)
            .textFieldStyle(.plain)
            .font(BSHType.bureauSans(14, weight: .medium))
            .tracking(-0.084)
            .foregroundStyle(ink.ink)
            .focused($focused)
            .onSubmit(onSubmit)
            .background(alignment: .leading) {
                // The browser's placeholder gray (Tailwind's gray-400), in either appearance;
                // a TextField's own prompt keeps the system's color.
                if text.isEmpty {
                    Text(placeholder)
                        .font(BSHType.bureauSans(14, weight: .medium))
                        .tracking(-0.084)
                        .foregroundStyle(Color.bshFixed(BSHRGB(156, 163, 175)))
                        .allowsHitTesting(false)
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 32)
            .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(ink.tray))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .circular)
                    .strokeBorder(ink.ink(0.11), lineWidth: 1)
            )
            .overlay(
                // `.focus-ring`: a 3pt halo of brass glow at half strength.
                RoundedRectangle(cornerRadius: 8, style: .circular)
                    .inset(by: -1.5)
                    .stroke(focused ? ink.accentGlow(0.5) : .clear, lineWidth: 3)
                    .allowsHitTesting(false)
            )
    }
}

/// `.yf-range-item`: a small pill of caption text, inked on hover.
private struct MacTrackingRangeItem<Label: View>: View {
    let ink: MacBureauPageInk
    let action: () -> Void
    @ViewBuilder var label: () -> Label
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            label()
                .font(BSHType.bureauSans(11, weight: .semibold))
                .tracking(0.066)
                .foregroundStyle(hovered ? ink.ink : ink.muted)
                .padding(.horizontal, 10)
                .frame(height: 22)
                .background(Capsule().fill(hovered ? ink.ink(0.05) : .clear))
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Live tape

/// LiveTickerTape.vue: the listed companies on the page with their last price, the day's
/// move and how fresh the quote is, on one strip that fades out at its end.
private struct MacTrackingTape: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let tickers: [String]
    let quotes: [String: MacTrackingQuote]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        if !tickers.isEmpty {
            HStack(spacing: 0) {
                HStack(spacing: 6) {
                    MacTrackingPulse(color: ink.success)
                    Text("Live")
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                }
                .padding(.leading, 4)
                .padding(.trailing, 12)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        ForEach(tickers, id: \.self) { ticker in
                            MacTrackingTapeItem(ticker: ticker, quote: quotes[ticker], ink: ink) {
                                store.showTicker(ticker)
                            }
                        }
                    }
                    .padding(.leading, 6)
                    .padding(.trailing, 24)
                }
                .mask {
                    HStack(spacing: 0) {
                        Color.black
                        LinearGradient(colors: [.black, .clear], startPoint: .leading, endPoint: .trailing).frame(width: 40)
                    }
                }
                .overlay(alignment: .leading) { Rectangle().fill(ink.ink(0.08)).frame(width: 1) }
            }
            .padding(.vertical, 6)
            .padding(.leading, 10)
            .frame(height: 36)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(MacTrackingTray(ink: ink, fillOpacity: 0.8))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        }
    }
}

private struct MacTrackingTapeItem: View {
    let ticker: String
    let quote: MacTrackingQuote?
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    private var hint: (text: String, stale: Bool)? {
        guard let staleness = quote?.staleness else { return nil }
        if staleness.stale { return ("Stale \(staleness.minutes)m", true) }
        if staleness.minutes < 1 { return ("just now", false) }
        if staleness.minutes < 60 { return ("\(staleness.minutes)m ago", false) }
        return nil
    }

    var body: some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(ticker)
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.ink)
                if let price = MacTrackingFormat.price(quote?.lastPrice, currency: quote?.currency) {
                    Text(price)
                        .font(BSHType.bureauSans(12).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(ink.secondary)
                }
                if let day = quote?.changePct1d {
                    Text(MacTrackingFormat.signed(day) ?? "")
                        .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(day >= 0 ? ink.success : ink.danger)
                } else {
                    Text("Waiting")
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.subtle)
                }
                if let hint {
                    Text(hint.text)
                        .font(BSHType.bureauSans(10))
                        .tracking(0.12)
                        .foregroundStyle(hint.stale ? ink.warningInk : ink.subtle)
                }
            }
            .bureauLines(16, size: 12)
            .padding(.horizontal, 8)
            .padding(.top, 4)
            .frame(height: 24, alignment: .top)
            .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(ticker)
    }
}

// MARK: - Attention strip

/// TrackingAttentionStrip.vue: one row per flagged company, with its next step and Ask.
private struct MacTrackingAttentionRow: View {
    @EnvironmentObject private var store: MacAppStore
    let item: MacAttentionItem
    let ink: MacBureauPageInk
    @State private var hovered = false

    private var company: MacCompany? { store.companies.first { $0.id == item.companyId } }

    var body: some View {
        HStack(spacing: 8) {
            Button {
                if let company { store.openCompanyPage(company) }
            } label: {
                HStack(spacing: 12) {
                    Circle()
                        .fill(item.severity == "high" ? ink.danger : ink.warning)
                        .frame(width: 8, height: 8)
                    (Text(item.companyName ?? company?.title ?? "").fontWeight(.medium).foregroundStyle(ink.ink)
                     + Text(" · \(MacTrackingText.attention(item))").foregroundStyle(ink.muted))
                        .font(BSHType.bureauSans(16))
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(MacTrackingText.action(kind: item.kind, label: item.label))
                        .font(BSHType.bureauSans(12, weight: .medium))
                        .foregroundStyle(ink.accent)
                        .bureauLines(16, size: 12)
                }
                .frame(height: 24)
                .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(hovered ? ink.fillTertiary.opacity(0.7) : .clear))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .onHover { hovered = $0 }

            Button {
                guard let company else { return }
                store.askWarren(
                    "Why is this company flagged (\(item.label ?? item.kind ?? ""))? What is the fastest next step?",
                    context: .attention(kind: item.kind ?? "", detail: item.detail, count: item.count),
                    company: company
                )
            } label: {
                Text("Ask Warren")
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .tracking(0.066)
                    .foregroundStyle(ink.accent)
                    .padding(.horizontal, 4)
            }
            .buttonStyle(.plain)
            .disabled(!store.canRunTasks)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .modifier(MacTrackingTray(ink: ink))
    }
}

// MARK: - A company's card

private struct MacTrackingCardView: View {
    @EnvironmentObject private var store: MacAppStore
    let card: MacTrackingCard
    let followed: Bool
    let ink: MacBureauPageInk
    @State private var hovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                store.openCompanyPage(card.company)
            } label: {
                content
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // `mt-3` holds its 12pt even when the footer has nothing in it.
            footer
                .frame(maxWidth: .infinity, minHeight: 0, alignment: .leading)
                .padding(.top, 12)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        // The website asks for a danger ring round a card that needs action, but the card's
        // own shadow overrides it, so none is drawn there, and none here.
        .modifier(MacTrackingTray(ink: ink))
        .overlay(alignment: .topTrailing) {
            if followed || hovered {
                MacTrackingFollowButton(companyId: card.id, followed: followed, ink: ink)
                    .padding(8)
            }
        }
        .onHover { hovered = $0 }
    }

    // MARK: Content

    private var content: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            if let description = card.description {
                MacTrackingClamp(
                    runs: [run(description, ink.secondary, 12)],
                    ellipsis: run("…", ink.secondary, 12),
                    lines: 2,
                    lineHeight: 16.5
                )
                .padding(.top, 8)
            }
            if !card.facts.isEmpty {
                Text(card.facts)
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .bureauLines(14, size: 11)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
            }
            if !card.metrics.isEmpty {
                metrics
                    .padding(.top, 12)
            }
            if let funding = card.funding {
                MacTrackingCut.text([
                    run("Last round: ", ink.muted, 11, tracking: 0.066),
                    run(funding, ink.secondary, 11, tracking: -0.11, mono: true),
                ])
                .bureauLines(14, size: 11)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 8)
            }
            if let earnings = card.earnings {
                MacTrackingCut.text([
                    run("Last earnings: ", ink.muted, 11, tracking: 0.066),
                    run(earnings, ink.secondary, 11, tracking: 0.066),
                ])
                .bureauLines(14, size: 11)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)
            }
            if let event = card.event {
                MacTrackingClamp(
                    runs: eventRuns(event),
                    ellipsis: run("…", ink.ink, 12),
                    lines: 2,
                    lineHeight: 16
                )
                .padding(.top, 8)
            }
            if !card.people.isEmpty {
                MacTrackingLine(runs: [caption(card.people, ink.muted)], ellipsis: caption("…", ink.muted), height: 14)
                    .padding(.top, 8)
            }
            if !card.products.isEmpty {
                MacTrackingLine(
                    runs: [caption("Products ", ink.muted), caption(card.products, ink.secondary)],
                    ellipsis: caption("…", ink.muted),
                    height: 14
                )
                .padding(.top, 4)
            }
            if !card.competitors.isEmpty {
                MacTrackingLine(
                    runs: [caption("Competitors ", ink.muted), caption(card.competitors, ink.secondary)],
                    ellipsis: caption("…", ink.muted),
                    height: 14
                )
                .padding(.top, 4)
            }
        }
    }

    private func run(_ text: String, _ color: Color, _ size: CGFloat, weight: Font.Weight = .regular, tracking: CGFloat = 0, mono: Bool = false) -> MacTrackingRun {
        MacTrackingRun(text: text, color: color, size: size, weight: weight, tracking: tracking, mono: mono)
    }

    /// `text-caption1`: 11pt with its letter spacing.
    private func caption(_ text: String, _ color: Color, mono: Bool = false) -> MacTrackingRun {
        run(text, color, 11, tracking: mono ? -0.11 : 0.066, mono: mono)
    }

    private func eventRuns(_ event: (text: String, date: String?)) -> [MacTrackingRun] {
        var runs = [run(event.text, ink.ink, 12)]
        if let date = event.date, let iso = MacTrackingFormat.isoDate(date, fallback: date) {
            runs.append(run(" · \(iso)", ink.subtle, 12))
        }
        return runs
    }

    // MARK: Header: mark, name, stage and what it is; the price and the day's move

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                MacTrackingLogo(company: card.company, size: 36)
                    .padding(.top, 2)
                VStack(alignment: .leading, spacing: 2) {
                    MacTrackingLine(
                        runs: [run(card.company.name ?? card.company.id, ink.ink, 15, weight: .semibold, tracking: -0.15)],
                        ellipsis: run("…", ink.ink, 15, weight: .semibold, tracking: -0.15),
                        height: 20
                    )
                    statusLine
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if let price = card.price {
                priceBlock(price)
                    .fixedSize()
            }
        }
        .padding(.trailing, 32)
    }

    /// The stage's chip, then the ticker and what the company is, cut to the card.
    private var statusLine: some View {
        let stage = card.row?.lifecycleStage.flatMap { $0.isEmpty ? nil : $0 }
        let ticker = (card.company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        let status = card.status ?? ""
        var runs: [MacTrackingRun] = []
        if !ticker.isEmpty {
            runs.append(caption(ticker, ink.secondary, mono: true))
            if !status.isEmpty { runs.append(caption(" · ", ink.muted)) }
            runs.append(caption(status, ink.muted))
        } else if !status.isEmpty {
            // After the chip the website keeps the space its template leaves before the text.
            runs.append(caption(stage != nil ? " " + status : status, ink.muted))
        }
        return HStack(alignment: .center, spacing: 6) {
            if let stage {
                Text(MacTrackingText.stage(stage))
                    .font(BSHType.bureauSans(10, weight: .semibold))
                    .tracking(0.12)
                    .foregroundStyle(ink.secondary)
                    .fixedSize()
                    .frame(height: 13)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(ink.fillTertiary))
                    .frame(height: 14)
                    .offset(y: 0.5)
                    .help(MacTrackingText.stage(stage))
            }
            MacTrackingLine(runs: runs, ellipsis: caption("…", ink.muted), height: 14)
        }
        .frame(height: 14)
        // The line is `truncate` (overflow hidden) on the website, which cuts the chip, 17pt
        // tall, to the line's 14.
        .clipped()
    }

    private func priceBlock(_ price: MacTrackingCard.Price) -> some View {
        VStack(alignment: .trailing, spacing: 0) {
            if let last = card.lastPrice {
                // The first line sits on the card's 24pt line, below its baseline as the
                // website sets an inline row there.
                HStack(spacing: 6) {
                    if card.live {
                        MacTrackingPulse(color: ink.accent)
                            .help("Live")
                    }
                    Text(last)
                        .font(BSHType.bureauSans(14).monospacedDigit())
                        .tracking(-0.14)
                        .foregroundStyle(ink.ink)
                }
                .frame(height: 20)
                .padding(.top, card.live ? 4.76 : 2.72)
                .frame(height: card.live ? 24.76 : 24, alignment: .top)
            }
            if let day = price.day {
                HStack(spacing: 3.4) {
                    LucideIcon(card.priceUp ? "trending-up" : "trending-down", size: 14)
                        .offset(y: 0.4)
                    Text(MacTrackingFormat.signed(day) ?? "")
                        .font(BSHType.bureauSans(14, weight: .semibold).monospacedDigit())
                        .tracking(-0.14)
                }
                .foregroundStyle(card.priceUp ? ink.success : ink.danger)
                .frame(height: 20)
            }
            if let vs = price.vs {
                Text("30d vs S&P \(MacTrackingFormat.signed(vs) ?? "")")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.subtle)
                    .frame(height: 14)
            }
        }
    }

    // MARK: KPIs

    private var metrics: some View {
        let pairs = stride(from: 0, to: card.metrics.count, by: 2).map { Array(card.metrics[$0..<min($0 + 2, card.metrics.count)]) }
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(pairs.enumerated()), id: \.offset) { _, pair in
                HStack(alignment: .top, spacing: 12) {
                    ForEach(pair, id: \.self) { metric in
                        VStack(alignment: .leading, spacing: 2) {
                            // `.vogue-label`: an italic serif kicker.
                            Text(metric.label)
                                .font(.custom(BSHType.bureauSerifItalic, size: 15.5))
                                .foregroundStyle(ink.secondary)
                                .bureauLines(20, size: 15.5, em: 1.30)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(metric.value)
                                .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                                .tracking(-0.12)
                                .foregroundStyle(ink.ink)
                                .bureauLines(16, size: 12)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if pair.count == 1 {
                        Color.clear.frame(maxWidth: .infinity, maxHeight: 0)
                    }
                }
            }
        }
    }

    // MARK: Footer: memo state, coverage and the next step

    private var footer: some View {
        let memo = memoChip
        let coverage = card.coverage
        let action = card.row?.bucket == "needs_action" ? card.row?.nextAction : nil
        // `flex flex-wrap items-center gap-2`: the chips wrap onto more lines as needed.
        return MacTrackingFlow(spacing: 8, lineSpacing: 8) {
            if memo != nil || !coverage.isEmpty || action != nil {
                if let memo {
                    chip(memo.label, foreground: memo.foreground, background: memo.background, weight: .medium)
                }
                ForEach(coverage, id: \.self) { bit in
                    chip(bit, foreground: ink.secondary, background: ink.fillTertiary, weight: .regular)
                }
                if let action {
                    Button {
                        store.openCompanyPage(card.company)
                    } label: {
                        Text(MacTrackingText.action(kind: action.kind, label: action.label))
                            .font(BSHType.bureauSans(11, weight: .medium))
                            .tracking(0.066)
                            .foregroundStyle(ink.accent)
                            .bureauLines(14, size: 11)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var memoChip: (label: String, foreground: Color, background: Color)? {
        guard let memo = card.row?.memo, (memo.total ?? 0) > 0 else { return nil }
        let label = MacTrackingFormat.status(memo.latestStatus)
        guard !label.isEmpty else { return nil }
        let status = memo.latestStatus ?? ""
        if status.hasPrefix("failed") { return (label, ink.danger, ink.danger.opacity(0.15)) }
        if status == "complete_with_warnings" { return (label, ink.warning, ink.warning.opacity(0.15)) }
        if status.hasPrefix("complete") { return (label, ink.success, ink.success.opacity(0.15)) }
        return (label, ink.secondary, ink.fillTertiary)
    }

    private func chip(_ text: String, foreground: Color, background: Color, weight: Font.Weight) -> some View {
        Text(text)
            .font(BSHType.bureauSans(11, weight: weight))
            .tracking(0.066)
            .foregroundStyle(foreground)
            .lineLimit(1)
            .fixedSize()
            .bureauLines(14, size: 11)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(Capsule().fill(background))
    }
}

/// Monogram.vue, tinted: the company's logo on a white tile, inside an 8% margin with its
/// corners rounded to the tile's; until a logo loads (or when there is none), the company's
/// initials on its tint. The Mac's MacAvatar draws the logo square and its tile rounder,
/// so the page draws its own, from the same logo addresses and image cache.
private struct MacTrackingLogo: View {
    @Environment(\.colorScheme) private var colorScheme
    let company: MacCompany
    let size: CGFloat
    @State private var image: NSImage?

    init(company: MacCompany, size: CGFloat) {
        self.company = company
        self.size = size
        _image = State(initialValue: Self.urls(for: company).lazy.compactMap { MacImageCache.shared.image(for: $0) }.first)
    }

    /// The addresses MacAvatar reads, so both share one cache.
    private static func urls(for company: MacCompany) -> [URL] {
        let name = company.name ?? company.id
        return [
            MacCompanyLogoResolver.resolvePrimaryLogoUrl(logoUrl: company.logoUrl, website: company.website, ticker: company.ticker, companyId: company.id, name: name),
            MacCompanyLogoResolver.resolveFallbackLogoUrl(website: company.website, ticker: company.ticker, companyId: company.id, name: name),
        ].compactMap { $0 }
    }

    var body: some View {
        let dark = colorScheme == .dark
        let radius = size * 0.28
        let tile = RoundedRectangle(cornerRadius: radius, style: .circular)
        Group {
            if let image {
                let inset = size * 0.08
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size - inset * 2, height: size - inset * 2)
                    .clipShape(RoundedRectangle(cornerRadius: radius - inset, style: .circular))
                    .frame(width: size, height: size)
                    .background(Color.white)
                    .overlay(tile.strokeBorder(dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5))
                    .clipShape(tile)
                    .background(
                        // `0 1px 2px` by day, `0 1px 3px` by night; SwiftUI's radius is the CSS blur.
                        tile.fill(Color.white)
                            .shadow(color: .black.opacity(dark ? 0.35 : 0.06), radius: dark ? 3 : 2, y: 1)
                    )
            } else {
                let tint = Self.tint(for: company)
                Text(Self.initials(for: company))
                    .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
                    .tracking(size * 0.0037)
                    .foregroundStyle(Color.white)
                    .frame(width: size, height: size)
                    .background(LinearGradient(
                        colors: [.bshFixed(tint), .bshFixed(tint, opacity: 0.72)],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    ))
                    .overlay(tile.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
                    .clipShape(tile)
            }
        }
        .task(id: company.id) { await load() }
    }

    private func load() async {
        guard image == nil else { return }
        for url in Self.urls(for: company) where !MacImageCache.shared.isFailed(url) {
            if let cached = MacImageCache.shared.image(for: url) {
                image = cached
                return
            }
            var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            if let (data, response) = try? await URLSession.shared.data(for: request),
               (response as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true,
               let fetched = NSImage(data: Self.sized(data)) {
                MacImageCache.shared.setImage(fetched, for: url)
                image = fetched
                return
            }
            MacImageCache.shared.markFailed(url)
        }
    }

    /// An SVG sized in ems has no size NSImage can use; give it one (as MacAvatar does).
    private static func sized(_ data: Data) -> Data {
        guard let svg = String(data: data, encoding: .utf8), svg.contains("<svg") else { return data }
        return svg
            .replacingOccurrences(of: "width=\"1em\"", with: "width=\"64\"")
            .replacingOccurrences(of: "height=\"1em\"", with: "height=\"64\"")
            .data(using: .utf8) ?? data
    }

    /// `companyInitials`: a short ticker, else the first letters of two words.
    private static func initials(for company: MacCompany) -> String {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        if ticker.range(of: "^[A-Za-z]{1,5}$", options: .regularExpression) != nil {
            return String(ticker.prefix(2)).uppercased()
        }
        let name = (company.name ?? "").trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return "?" }
        let tokens = name.components(separatedBy: CharacterSet(charactersIn: " \t\n,./&+_–—-")).filter { !$0.isEmpty }
        if tokens.count >= 2, let a = tokens[0].first, let b = tokens[1].first { return "\(a)\(b)".uppercased() }
        let word = (tokens.first ?? name).filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let caps = word.filter { $0.isUppercase }
        if caps.count >= 2 { return String(caps.prefix(2)) }
        if word.count >= 2 { return String(word.prefix(2)).uppercased() }
        return word.isEmpty ? "?" : word.uppercased()
    }

    /// The tint Monogram.vue hashes from the company's id.
    private static func tint(for company: MacCompany) -> BSHRGB {
        let tints = [
            BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
            BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
        ]
        var hash: UInt32 = 0
        for unit in company.id.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        return tints[Int(hash % 10)]
    }
}

/// `flex-wrap`: items side by side, onto a new line when the next would not fit, each line's
/// items centered on it.
private struct MacTrackingFlow: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8

    private func lines(_ subviews: Subviews, width: CGFloat) -> [[(index: Int, size: CGSize)]] {
        var lines: [[(index: Int, size: CGSize)]] = [[]]
        var x: CGFloat = 0
        for (index, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if !lines[lines.count - 1].isEmpty, x + size.width > width {
                lines.append([])
                x = 0
            }
            lines[lines.count - 1].append((index, size))
            x += size.width + spacing
        }
        return lines.filter { !$0.isEmpty }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let laid = lines(subviews, width: proposal.width ?? .infinity)
        guard !laid.isEmpty else { return .zero }
        let width = laid.map { line in line.reduce(0) { $0 + $1.size.width } + spacing * CGFloat(line.count - 1) }.max() ?? 0
        let height = laid.map { $0.map(\.size.height).max() ?? 0 }.reduce(0, +) + lineSpacing * CGFloat(laid.count - 1)
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in lines(subviews, width: bounds.width) {
            let height = line.map(\.size.height).max() ?? 0
            var x = bounds.minX
            for item in line {
                subviews[item.index].place(
                    at: CGPoint(x: x, y: y + (height - item.size.height) / 2),
                    proposal: ProposedViewSize(item.size)
                )
                x += item.size.width + spacing
            }
            y += height + lineSpacing
        }
    }
}

/// CompanyFollowButton.vue: a star in a 24pt circle; gold and filled once followed.
private struct MacTrackingFollowButton: View {
    @EnvironmentObject private var store: MacAppStore
    let companyId: String
    let followed: Bool
    let ink: MacBureauPageInk
    @State private var hovered = false

    var body: some View {
        Button {
            Task { await store.toggleFollow(companyId) }
        } label: {
            LucideIcon(followed ? "star-fill" : "star", size: 14)
                .foregroundStyle(followed ? ink.notice : (hovered ? ink.ink : ink.muted))
                .frame(width: 24, height: 24)
                .background(Circle().fill(followed ? ink.ink(0.08) : (hovered ? ink.ink(0.06) : .clear)))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(followed ? "Unfollow" : "Follow")
    }
}

// MARK: - News rows

/// `.source-row`: a story's title and age beside a newspaper.
private struct MacTrackingNewsRow: View {
    let story: MacTrackingNews
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                LucideIcon("newspaper", size: 16)
                    .foregroundStyle(ink.muted)
                VStack(alignment: .leading, spacing: 0) {
                    MacTrackingLine(
                        runs: [MacTrackingRun(text: story.title, color: hovered ? ink.ink : ink.secondary, size: 13, weight: .medium, tracking: -0.078)],
                        ellipsis: MacTrackingRun(text: "…", color: hovered ? ink.ink : ink.secondary, size: 13, weight: .medium, tracking: -0.078),
                        height: 24
                    )
                    Text(MacTrackingFormat.age(story.capturedAt))
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .bureauLines(14, size: 11)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - The Mac's holdings and monitoring

/// What a section at the foot of the page opens in a sheet.
struct MacTrackingSheet: Identifiable {
    enum Kind { case holding, monitoring }
    let kind: Kind
    let companyId: String
    var id: String { "\(kind)-\(companyId)" }
}

/// A section heading as the page sets "News": a headline, a line of help, and actions.
private struct MacTrackingSectionHead<Actions: View>: View {
    let title: String
    let hint: String
    let ink: MacBureauPageInk
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(BSHType.bureauSans(15, weight: .semibold))
                    .tracking(-0.15)
                    .foregroundStyle(ink.ink)
                    .bureauLines(20, size: 15)
                Text(hint)
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .bureauLines(14, size: 11)
            }
            Spacer(minLength: 8)
            HStack(spacing: 8) { actions() }
        }
    }
}

/// The Mac's private holdings: the book's totals, then a row per position that opens its
/// KPIs, founder updates, marks and tear sheet.
private struct MacTrackingHoldings: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let open: (String) -> Void
    @Binding var showReserves: Bool
    @Binding var showAddHolding: Bool

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var holdings: [MacPortfolioCompany] {
        (store.portfolioDashboard?.companies ?? []).sorted { a, b in
            let ra = rank(a.highestAlert), rb = rank(b.highestAlert)
            if ra != rb { return ra < rb }
            return a.companyName.localizedCompare(b.companyName) == .orderedAscending
        }
    }

    private func rank(_ alert: MacPortfolioAlert?) -> Int {
        guard let alert else { return 3 }
        return alert.severity == "high" ? 0 : (alert.severity == "medium" ? 1 : 2)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacTrackingSectionHead(
                title: "Holdings",
                hint: "Private positions from Invest decisions, plus any added here.",
                ink: ink
            ) {
                MacBureauButton("Reserves", size: .small) { showReserves = true }
                    .help("Follow-on reserves planner")
                MacBureauButton("Add holding", icon: "plus", size: .small) { showAddHolding = true }
                    .disabled(!store.canWriteDesk)
            }

            if let totals = store.portfolioDashboard?.totals, !holdings.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(alignment: .top, spacing: 12) {
                        stat("Invested", MacMoney.short(totals.investedUsd))
                        stat("Marked value", totals.markedValueUsd.map(MacMoney.short) ?? "—")
                            .help(totals.markedCount == 0 ? "No marks entered yet" : "\(totals.markedCount) of \(totals.companyCount) positions have a mark")
                        stat("MOIC (marked)", totals.markedMoic.map { String(format: "%.2fx", $0) } ?? "—")
                        stat("Alerts", "\(totals.alertCount)", tone: totals.highAlertCount > 0 ? ink.danger : nil)
                            .help("\(totals.highAlertCount) high")
                    }
                    VStack(spacing: 2) {
                        ForEach(holdings) { holding in
                            MacTrackingHoldingRow(holding: holding, ink: ink) { open(holding.companyId) }
                        }
                    }
                    .padding(.top, 12)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(MacTrackingTray(ink: ink))
                .padding(.top, 12)
            } else {
                Text(store.portfolioLoading && store.portfolioDashboard == nil
                     ? "Loading holdings…"
                     : "No holdings yet. Record an Invest decision (⌘D) or press Add holding.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .bureauLines(16, size: 12)
                    .padding(.top, 12)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task {
            if store.portfolioDashboard == nil { await store.loadPortfolioDashboard() }
        }
    }

    private func stat(_ label: String, _ value: String, tone: Color? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.custom(BSHType.bureauSerifItalic, size: 15.5))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .bureauLines(20, size: 15.5, em: 1.30)
            Text(value)
                .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                .tracking(-0.12)
                .foregroundStyle(tone ?? ink.ink)
                .bureauLines(16, size: 12)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct MacTrackingHoldingRow: View {
    @EnvironmentObject private var store: MacAppStore
    let holding: MacPortfolioCompany
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    private var facts: String {
        let p = holding.position
        var parts: [String] = []
        if let round = p.round, !round.isEmpty { parts.append(round) }
        if let invested = p.investedUsd, invested > 0 { parts.append("Invested \(MacMoney.short(invested))") }
        if let own = p.ownershipPct, own > 0 { parts.append(String(format: "%.1f%% owned", own)) }
        if let arr = holding.latestKpi?.arrUsd, arr > 0 { parts.append("ARR \(MacMoney.short(arr))") }
        if let burn = holding.latestKpi?.burnUsdMonth, burn > 0 { parts.append("Burn \(MacMoney.short(burn))/mo") }
        if let runway = holding.latestKpi?.runwayMonths, runway > 0 { parts.append(String(format: "Runway %.0f mo", runway)) }
        return parts.isEmpty ? "No position details yet" : parts.joined(separator: " · ")
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                MacTrackingLogo(
                    company: store.companies.first { $0.id == holding.companyId }
                        ?? MacCompany(id: holding.companyId, name: holding.companyName, ticker: holding.ticker),
                    size: 22
                )
                VStack(alignment: .leading, spacing: 0) {
                    Text(holding.companyName)
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .tracking(-0.078)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                        .frame(height: 18)
                    Text(facts)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .frame(height: 14)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 0) {
                    Text(holding.latestMark.map { "Mark \(MacMoney.short($0.valueUsd))" } ?? "No mark")
                        .font(BSHType.bureauSans(13).monospacedDigit())
                        .tracking(-0.13)
                        .foregroundStyle(holding.latestMark == nil ? ink.subtle : ink.ink)
                        .frame(height: 18)
                    Text(holding.moic.map { String(format: "MOIC %.2fx", $0) } ?? "MOIC —")
                        .font(BSHType.bureauSans(11).monospacedDigit())
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .frame(height: 14)
                }
                if let alert = holding.highestAlert {
                    let high = alert.severity == "high"
                    Text(alert.label)
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .foregroundStyle(high ? ink.dangerInk : (alert.severity == "medium" ? ink.warningInk : ink.secondary))
                        .lineLimit(1)
                        .padding(.horizontal, 8)
                        .frame(height: 18)
                        .background(Capsule().fill(high ? ink.dangerSoft : (alert.severity == "medium" ? ink.warning.opacity(0.15) : ink.fillTertiary)))
                        .help(alert.detail ?? alert.label)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// Companies with a standing Invest or Watch decision: tracked news by impact and the ones
/// that need re-underwriting; a row opens the decision record, news and recommended run.
private struct MacTrackingMonitoring: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Binding var reunderwritingOnly: Bool
    let open: (String) -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private func needsReunderwriting(_ companyId: String, _ decision: MacDecision) -> Bool {
        if decision.needsReunderwriting { return true }
        if let updates = store.trackingByCompany[companyId], updates.items.contains(where: { $0.impact == "high" }) { return true }
        return false
    }

    private var entries: [(company: MacCompany, decision: MacDecision)] {
        let all = store.portfolioEntries
        guard reunderwritingOnly else { return all }
        return all.filter { needsReunderwriting($0.company.id, $0.decision) }
    }

    var body: some View {
        let all = store.portfolioEntries
        let flagged = all.filter { needsReunderwriting($0.company.id, $0.decision) }.count
        VStack(alignment: .leading, spacing: 0) {
            MacTrackingSectionHead(
                title: "Monitoring",
                hint: "Invest and Watch decisions, with their tracked news by impact.",
                ink: ink
            ) {
                if !all.isEmpty {
                    MacTrackingFilter(followedOnly: $reunderwritingOnly, off: ("All", all.count), on: ("Needs re-underwriting", flagged))
                }
            }

            if entries.isEmpty {
                Text(all.isEmpty
                     ? "No Invest or Watch decisions yet. Record one with ⌘D from the Pipeline or a dossier."
                     : "Nothing needs re-underwriting.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .bureauLines(16, size: 12)
                    .padding(.top, 12)
            } else {
                VStack(spacing: 4) {
                    ForEach(entries, id: \.company.id) { entry in
                        MacTrackingMonitoringRow(
                            company: entry.company,
                            decision: entry.decision,
                            flagged: needsReunderwriting(entry.company.id, entry.decision),
                            ink: ink
                        ) { open(entry.company.id) }
                    }
                }
                .padding(.top, 12)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task {
            if store.rollup == nil { await store.loadPipeline() }
            for entry in store.portfolioEntries where store.trackingByCompany[entry.company.id] == nil {
                await store.loadTracking(entry.company.id, sync: false)
            }
        }
    }
}

private struct MacTrackingMonitoringRow: View {
    @EnvironmentObject private var store: MacAppStore
    let company: MacCompany
    let decision: MacDecision
    let flagged: Bool
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                MacTrackingLogo(company: company, size: 22)
                Text(company.title)
                    .font(BSHType.bureauSans(13, weight: .medium))
                    .tracking(-0.078)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                MacBureauChip(
                    text: decision.verdictLabel,
                    foreground: decision.verdict == "invest" ? ink.successInk : ink.warningInk,
                    background: decision.verdict == "invest" ? ink.successSoft : ink.warning.opacity(0.15)
                )
                if let retro = decision.latestRetrospective, retro.verdict != "still_right" {
                    Text(retro.label)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.dangerInk)
                }
                if let updates = store.trackingByCompany[company.id] {
                    let high = updates.items.filter { $0.impact == "high" }.count
                    if high > 0 {
                        Text("\(high) high-impact")
                            .font(BSHType.bureauSans(11))
                            .tracking(0.066)
                            .foregroundStyle(ink.dangerInk)
                    }
                }
                Spacer(minLength: 8)
                if flagged {
                    LucideIcon("triangle-alert", size: 14)
                        .foregroundStyle(ink.warning)
                        .help("Needs re-underwriting")
                }
            }
            .frame(height: 24)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// A holding's or a position's record, in a sheet over the page.
private struct MacTrackingSheetView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    let item: MacTrackingSheet

    private var company: MacCompany? { store.companies.first { $0.id == item.companyId } }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Text(item.kind == .holding ? "Holding" : "Monitoring")
                    .font(.custom(BSHType.bureauSerif, size: 23))
                    .tracking(-0.23)
                    .foregroundStyle(ink.ink)
                Spacer(minLength: 0)
                MacBureauButton("Done", size: .small) { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            Rectangle().fill(ink.rule).frame(height: 1)
            switch item.kind {
            case .holding:
                MacHoldingDetailView(companyId: item.companyId)
            case .monitoring:
                if let company {
                    MacMonitoringDetail(company: company)
                } else {
                    Text("This company is no longer on the server.")
                        .font(BSHType.bureauSans(13))
                        .foregroundStyle(ink.muted)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .frame(width: 680, height: 720)
        .background(ink.sheet)
        .font(BSHType.bureauSans(13))
        .buttonStyle(.dsBordered)
        .textFieldStyle(.dsField)
        .onAppear {
            if let company { store.selectCompany(company) }
        }
    }
}

// MARK: - The window's width

/// The website's grid breaks on the window's width, not the page's; this reads it.
private struct MacTrackingWindowWidth: NSViewRepresentable {
    @Binding var width: CGFloat

    func makeNSView(context: Context) -> Probe {
        let probe = Probe()
        probe.report = { value in
            DispatchQueue.main.async { if abs(width - value) > 0.5 { width = value } }
        }
        return probe
    }

    func updateNSView(_ nsView: Probe, context: Context) {}

    final class Probe: NSView {
        var report: ((CGFloat) -> Void)?
        private var observer: NSObjectProtocol?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if let observer { NotificationCenter.default.removeObserver(observer) }
            observer = nil
            guard let window else { return }
            report?(window.frame.width)
            observer = NotificationCenter.default.addObserver(
                forName: NSWindow.didResizeNotification, object: window, queue: .main
            ) { [weak self] _ in
                guard let width = self?.window?.frame.width else { return }
                self?.report?(width)
            }
        }

        deinit {
            if let observer { NotificationCenter.default.removeObserver(observer) }
        }
    }
}
