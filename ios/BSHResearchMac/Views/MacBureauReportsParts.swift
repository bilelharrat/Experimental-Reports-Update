//
//  MacBureauReportsParts.swift
//  BSHResearchMac
//
//  The pieces of Bureau's Reports desk (MacBureauReports.swift): how the website reads a
//  report (reportStatus.js: its state, type, call, review, versions), a row of the list, the
//  folded rail's marks, the document viewer, and the Mac's transcripts in the same trays.
//

import AppKit
import PDFKit
import SwiftUI

// MARK: - What the list reads beyond the Mac's report model

/// The fields of a report summary (GET /api/reports) the website's list and viewer read and
/// the Mac's `MacReport` does not carry.
struct MacBureauReportsExtras: Equatable {
    var decision = ""
    var headlineEN = ""
    var headlineZH = ""
    var callLabelEN = ""
    var passKind = ""
    var buyPriceValue: Double?
    var currency = ""
    var valueBasis = ""
    var buyPriceText = ""
    var reviewState = ""
    var reviewer = ""
    var structureVersion = ""
    var isLatest: Bool?
    var versionIndex = 0
    var versionCount = 0
    var latestVersionId = ""
    var previousVersionId = ""
    var verdictChangedFrom = ""
    var unstableCall = false
    var dismissedAt = ""
    var supersededBy = ""
    var openFlags = 0
    var hasDocument: Bool?
    var resumeAvailable = false
    var failureKind = ""
    var failureSummary = ""
    var failureDetail = ""
    var failureSpend: Double?
    var memoAsOf = ""
    var reportReadyAt = ""
    var evidenceLatest = ""
    var ticker = ""
    var logoUrl = ""
    var website = ""
    /// `memo_quality_lint` and `memo_chinese_parity`: whether each gate ran, flagged, and its P0s and findings.
    var gates: [(ran: Bool, flagged: Bool, p0: Int, findings: Int)] = []
    /// `memo_fact_check`, reduced to what the list's chip says.
    var factStatus = ""
    var factPresent = false
    var factChecked = 0
    var factVerified = 0
    var factNotTraced = 0
    var factP0 = 0
    var factThin = false

    static func == (lhs: MacBureauReportsExtras, rhs: MacBureauReportsExtras) -> Bool {
        lhs.decision == rhs.decision && lhs.headlineEN == rhs.headlineEN && lhs.reviewState == rhs.reviewState
            && lhs.isLatest == rhs.isLatest && lhs.versionCount == rhs.versionCount && lhs.dismissedAt == rhs.dismissedAt
            && lhs.supersededBy == rhs.supersededBy && lhs.openFlags == rhs.openFlags && lhs.factStatus == rhs.factStatus
            && lhs.factVerified == rhs.factVerified && lhs.hasDocument == rhs.hasDocument
    }

    init(_ o: [String: Any]) {
        func text(_ value: Any?) -> String {
            (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }
        func number(_ value: Any?) -> Double? {
            if let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() { return n.doubleValue }
            if let s = value as? String { return Double(s) }
            return nil
        }
        func count(_ value: Any?) -> Int {
            if let list = value as? [Any] { return list.count }
            guard let n = number(value), n.isFinite, n > 0 else { return 0 }
            return Int(n.rounded())
        }
        func flag(_ value: Any?) -> Bool? {
            if let n = value as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() { return n.boolValue }
            return nil
        }

        let reader = o["reader"] as? [String: Any] ?? [:]
        decision = text(o["decision"]).isEmpty ? text(reader["decision"]) : text(o["decision"])
        if let headline = reader["headline"] as? [String: Any] {
            headlineEN = text(headline["en"]).replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            headlineZH = text(headline["zh"]).replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        }
        let label = (o["call_label"] as? [String: Any]) ?? (reader["call_label"] as? [String: Any]) ?? [:]
        callLabelEN = text(label["en"])
        passKind = (text(o["pass_kind"]).isEmpty ? text(reader["pass_kind"]) : text(o["pass_kind"])).lowercased()
        buyPriceValue = number(o["buy_price_value"])
        let valuation = o["buffett_valuation"] as? [String: Any] ?? [:]
        currency = text(o["currency"]).isEmpty ? text(valuation["currency"]) : text(o["currency"])
        valueBasis = text(valuation["value_basis"])
        if let raw = o["buy_price"] as? String {
            buyPriceText = raw
        } else if let raw = o["buy_price"] as? [String: Any] {
            buyPriceText = text(raw["en"])
        }
        if buyPriceText.isEmpty { buyPriceText = text(reader["buy_price_text"]) }
        reviewState = text(o["review_state"]).lowercased()
        reviewer = text(o["reviewer_name"]).isEmpty ? text(o["reviewer"]) : text(o["reviewer_name"])
        structureVersion = text(o["structure_version"])
        isLatest = flag(o["is_latest"])
        versionIndex = count(o["version_index"])
        versionCount = count(o["version_count"])
        latestVersionId = text(o["latest_version_id"])
        previousVersionId = text(o["previous_version_id"])
        verdictChangedFrom = text(o["verdict_changed_from"])
        unstableCall = flag(o["unstable_call"]) == true
        dismissedAt = text(o["dismissed_at"])
        supersededBy = text(o["superseded_by"])
        openFlags = count(o["open_flags"])
        hasDocument = flag(o["has_document"])
        resumeAvailable = flag(o["resume_available"]) == true
        failureKind = text(o["failure_kind"]).lowercased()
        failureSummary = text(o["failure_summary_en"])
        failureDetail = text(o["failure_detail"])
        failureSpend = number(o["failure_spend_usd"])
        memoAsOf = text(reader["memo_as_of"])
        reportReadyAt = text(o["report_ready_at"])
        evidenceLatest = text(reader["evidence_latest"])
        ticker = text(o["ticker"])
        logoUrl = text(o["logo_url"])
        website = text(o["website"])

        for key in ["memo_quality_lint", "memo_chinese_parity"] {
            guard let payload = o[key] as? [String: Any] else { continue }
            let status = text(payload["status"]).lowercased()
            let p0 = count(payload["p0_count"])
            let flagged: Bool
            if p0 > 0 {
                flagged = true
            } else if !status.isEmpty {
                flagged = !["passed", "ok", "pass", "clean"].contains(status)
            } else {
                flagged = !((payload["findings"] as? [Any]) ?? []).isEmpty
            }
            gates.append((true, flagged, p0, count(payload["finding_count"])))
        }

        if let fc = o["memo_fact_check"] as? [String: Any] {
            factPresent = true
            factStatus = text(fc["status"]).lowercased()
            factChecked = count(fc["checked"])
            factVerified = count(fc["verified"])
            factNotTraced = count(fc["not_traced"] ?? fc["unsupported"])
            factP0 = count(fc["p0_count"])
            factThin = flag(fc["thin_corpus"]) == true
        }
    }

    /// Every report's summary, as the website reads the list (the full rows, as it asks).
    static func load() async -> [String: MacBureauReportsExtras]? {
        guard let url = MacConfig.serverURL("reports") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        guard let result = try? await URLSession.shared.data(for: request),
              let http = result.1 as? HTTPURLResponse, (200..<300).contains(http.statusCode),
              let rows = try? JSONSerialization.jsonObject(with: result.0) as? [[String: Any]] else { return nil }
        var out: [String: MacBureauReportsExtras] = [:]
        for row in rows {
            if let id = row["id"] as? String { out[id] = MacBureauReportsExtras(row) }
        }
        return out
    }
}

// MARK: - How the website reads a report (reportStatus.js)

@MainActor
struct MacBureauReportsModel {
    struct Row: Identifiable {
        let report: MacReport
        let older: Int
        let nested: Bool
        var id: String { report.id }
    }

    let reports: [MacReport]
    let extras: [String: MacBureauReportsExtras]
    let companies: [MacCompany]
    let companyFilter: String

    let filtered: [MacReport]
    let flatRows: [Row]
    let hiddenCount: Int
    let runningCount: Int
    let countLabel: String
    let companyOptions: [(String, String)]
    let kindOptions: [(String, String)]
    let emptyTitle: String
    var filteredIds: [String] { filtered.map(\.id) }

    static let statusOptions: [(String, String)] = [
        ("all", "Any status"), ("complete", "Ready"), ("running", "Running"),
        ("needs_attention", "Attention"), ("failed", "Failed"),
    ]

    init(
        reports: [MacReport], extras: [String: MacBureauReportsExtras], companies: [MacCompany],
        query: String, company: String, status: String, kind: String, showDismissed: Bool, expanded: Set<String>
    ) {
        self.reports = reports
        self.extras = extras
        self.companies = companies
        self.companyFilter = company

        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        func matches(_ r: MacReport) -> Bool {
            if company != "all" && r.companyId != company { return false }
            if status != "all" && Self.listStatus(r) != status { return false }
            if kind != "all" && Self.typeKey(r) != kind { return false }
            guard !q.isEmpty else { return true }
            let x = extras[r.id]
            let haystack = [
                r.companyName ?? "", Self.companyName(r), r.companyId ?? "", r.reportType ?? "", r.kind ?? "",
                Self.typeLabel(r), x?.decision ?? "", Self.verdict(r, x)?.label ?? "", x?.headlineEN ?? "", x?.headlineZH ?? "",
            ]
            return haystack.contains { $0.lowercased().contains(q) }
        }

        let visible = showDismissed ? reports : reports.filter { !Self.isHidden($0, extras[$0.id]) }
        let matching = reports.filter(matches)
        let filtered = showDismissed ? matching : matching.filter { !Self.isHidden($0, extras[$0.id]) }
        self.filtered = filtered
        hiddenCount = matching.filter { Self.isHidden($0, extras[$0.id]) }.count
        runningCount = visible.filter { Self.listStatus($0) == "running" }.count
        countLabel = filtered.count == visible.count
            ? "\(visible.count) reports"
            : "\(filtered.count) of \(visible.count) reports"

        // Older memos of a company and kind fold under their latest when it is on the list.
        let shown = Set(filtered.map(\.id))
        var older: [String: [MacReport]] = [:]
        var top: [MacReport] = []
        for r in filtered {
            let x = extras[r.id]
            if let x, x.isLatest != nil, x.isLatest == false, !x.latestVersionId.isEmpty,
               x.latestVersionId != r.id, shown.contains(x.latestVersionId) {
                older[x.latestVersionId, default: []].append(r)
            } else {
                top.append(r)
            }
        }
        var rows: [Row] = []
        for r in top {
            let folded = older[r.id] ?? []
            rows.append(Row(report: r, older: folded.count, nested: false))
            if !folded.isEmpty && expanded.contains(r.id) {
                rows += folded.map { Row(report: $0, older: 0, nested: true) }
            }
        }
        flatRows = rows

        var names: [String: String] = [:]
        var order: [String] = []
        for r in reports {
            guard let id = r.companyId, !id.isEmpty else { continue }
            if names[id] == nil { order.append(id) }
            names[id] = Self.companyName(r)
        }
        var pickedName = ""
        if company != "all" {
            pickedName = companies.first { $0.id == company }?.name
                ?? reports.first { $0.companyId == company }.map(Self.companyName)
                ?? company
            if names[company] == nil {
                names[company] = pickedName
                order.append(company)
            }
        }
        companyOptions = [("all", "All Companies")] + order.map { ($0, names[$0] ?? $0) }

        var kinds: [(String, String)] = []
        var seenKinds = Set<String>()
        for r in reports {
            let key = Self.typeKey(r)
            if !key.isEmpty, seenKinds.insert(key).inserted { kinds.append((key, Self.typeLabel(r))) }
        }
        kindOptions = kinds
        emptyTitle = pickedName.isEmpty ? "No reports found" : "No reports on \(pickedName) yet"
    }

    /// The workspace's own record of a report's company, if it has one.
    func workspaceCompany(for report: MacReport) -> MacCompany? {
        guard let cid = report.companyId, !cid.isEmpty else { return nil }
        return companies.first { $0.id == cid }
            ?? companies.first { ($0.ticker ?? "").lowercased() == cid.lowercased() && !($0.ticker ?? "").isEmpty }
    }

    /// Widths of a row of filters sharing `width` by fractions, 6pt apart (a CSS grid's `fr`).
    /// Each lands on a half point, as the browser paints them; the last takes what is left.
    static func columns(_ fractions: [CGFloat], width: CGFloat) -> [CGFloat] {
        let free = width - 6 * CGFloat(fractions.count - 1)
        let total = fractions.reduce(0, +)
        var widths = fractions.dropLast().map { (free * $0 / total * 2).rounded() / 2 }
        widths.append(free - widths.reduce(0, +))
        return widths
    }

    // MARK: State

    /// complete, warnings, failed, cards_ready, paused or running.
    static func state(_ r: MacReport) -> String {
        let status = (r.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if status == "complete_with_warnings" { return "warnings" }
        if status.hasPrefix("complete") || status == "ready" { return "complete" }
        if status.contains("fail") || status == "error" || status == "cancelled" { return "failed" }
        if status == "awaiting_studio" || status == "cards_ready" { return "cards_ready" }
        if status == "english_ready_paused" { return "paused" }
        return "running"
    }

    /// The filter's bucket: complete, running, needs_attention or failed.
    static func listStatus(_ r: MacReport) -> String {
        switch state(r) {
        case "warnings", "cards_ready", "paused": return "needs_attention"
        case let s: return s
        }
    }

    static func isComplete(_ r: MacReport) -> Bool {
        let s = state(r)
        return s == "complete" || s == "warnings"
    }

    /// Something to read is on file (the Mac also opens a memo from its file list).
    static func canOpen(_ r: MacReport, _ x: MacBureauReportsExtras?) -> Bool {
        if x?.hasDocument == false { return false }
        return !(r.downloadUrls ?? [:]).isEmpty || !(r.previewUrls ?? [:]).isEmpty || !(r.memoFiles ?? []).isEmpty
    }

    static func isDocless(_ r: MacReport, _ x: MacBureauReportsExtras?) -> Bool {
        isComplete(r) && !canOpen(r, x)
    }

    static func isHidden(_ r: MacReport, _ x: MacBureauReportsExtras?) -> Bool {
        guard let x else { return false }
        return !x.dismissedAt.isEmpty || !x.supersededBy.isEmpty
    }

    static func isMemo(_ r: MacReport) -> Bool {
        ["investment_memo_latestage", "buffett_investment_memo"].contains(r.kind ?? "")
    }

    static func isBuffett(_ r: MacReport) -> Bool {
        if let kind = r.kind, !kind.isEmpty { return kind == "buffett_investment_memo" }
        return r.reportType == "Buffett Investment Memo"
    }

    static func hasICMemo(_ r: MacReport) -> Bool {
        (r.downloadUrls ?? [:]).keys.contains { $0.lowercased().hasPrefix("internal") }
    }

    // MARK: Names

    static func typeKey(_ r: MacReport) -> String {
        let type = (r.reportType ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return type.isEmpty ? (r.kind ?? "").trimmingCharacters(in: .whitespacesAndNewlines) : type
    }

    private static let typeLabels: [String: String] = [
        "Investment Report (Auto)": "Investment Report (Auto)",
        "Investment Memo (Late-Stage)": "Investment Memo (Late-Stage)",
        "Buffett Investment Memo": "Buffett-Method Memo",
        "Financial Analysis": "Financial Analysis",
        "Market Analysis": "Market Analysis",
        "Background": "Background",
        "Investment Report": "Investment Report",
    ]
    private static let kindLabels: [String: String] = [
        "investment_memo_latestage": "Investment Memo (Late-Stage)",
        "buffett_investment_memo": "Buffett-Method Memo",
        "hormuz_appendix": "Hormuz Appendix",
    ]

    static func typeLabel(_ r: MacReport) -> String {
        let type = (r.reportType ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let kind = (r.kind ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if let label = typeLabels[type] ?? kindLabels[kind] ?? kindLabels[type] { return label }
        let raw = (type.isEmpty ? kind : type)
            .replacingOccurrences(of: "[_-]+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        guard let first = raw.first else { return "Investment Report" }
        return first.uppercased() + raw.dropFirst()
    }

    /// A company name without EDGAR suffixes, slashes or control characters (cleanDisplayName).
    /// Names and dates are read on every redraw of the list; each is worked out once.
    private static var names: [String: String] = [:]
    private static var dates: [String: Date] = [:]
    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static let naive: [DateFormatter] = ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd"].map { format in
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = format
        return f
    }
    private static let dayLabel: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.dateFormat = "MMM d, yyyy"
        return f
    }()

    static func cleanName(_ name: String?) -> String {
        let key = name ?? ""
        if let known = names[key] { return known }
        let clean = cleanedName(key)
        names[key] = clean
        return clean
    }

    nonisolated private static func cleanedName(_ name: String) -> String {
        var text = String(name.unicodeScalars.map { $0.value < 32 || $0.value == 127 ? " " : Character($0) })
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return "" }
        let stripped = text.replacingOccurrences(of: "(?:\\s*/\\s*[A-Za-z]{2,4}\\s*/?)+\\s*$", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        if !stripped.isEmpty { text = stripped }
        text = text.replacingOccurrences(of: "\\s*[/\\\\]+\\s*", with: "-", options: .regularExpression)
        text = text.replacingOccurrences(of: "^[.\\s-]+", with: "", options: .regularExpression)
            .replacingOccurrences(of: "[\\s,;:-]+$", with: "", options: .regularExpression)
        return text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespaces)
    }

    static func companyName(_ r: MacReport) -> String {
        let name = cleanName(r.companyName)
        if !name.isEmpty && name != "x" { return name }
        if let id = r.companyId, !id.isEmpty, id != "x" { return id }
        return "Investment Report"
    }

    // MARK: Dates

    static func date(_ raw: String?) -> Date? {
        guard let raw = raw?.trimmingCharacters(in: .whitespaces), !raw.isEmpty else { return nil }
        if let known = dates[raw] { return known }
        let parsed = isoFractional.date(from: raw) ?? iso.date(from: raw) ?? naive.lazy.compactMap { $0.date(from: raw) }.first
        if let parsed { dates[raw] = parsed }
        return parsed
    }

    /// "Sep 24, 2026", as `toLocaleDateString("en-US", {year, month: "short", day})`.
    static func dateLabel(_ raw: String?) -> String {
        guard let d = date(raw) else { return raw ?? "" }
        return dayLabel.string(from: d)
    }

    // MARK: The call, its review, its checks

    private static func decisionKey(_ decision: String) -> String {
        decision.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            .replacingOccurrences(of: "[\\s_-]+", with: " ", options: .regularExpression)
    }

    /// A decision in words: a Buffett "Pass", a late-stage "Watch".
    static func decisionWord(_ decision: String, _ r: MacReport) -> String {
        let key = decisionKey(decision)
        guard !key.isEmpty else { return "" }
        let words = isBuffett(r)
            ? ["buy": "Buy", "pass": "Pass", "too hard": "Too Hard"]
            : ["strong buy": "Strong Buy", "buy": "Buy", "invest": "Invest", "watch": "Watch", "pass": "Pass"]
        return words[key] ?? decision.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static let currencySymbols = ["USD": "$", "EUR": "€", "GBP": "£", "HKD": "HK$", "TWD": "NT$"]

    private static func grouped(_ value: Double, decimals: Int) -> String {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_US")
        f.numberStyle = .decimal
        f.minimumFractionDigits = decimals
        f.maximumFractionDigits = decimals
        return f.string(from: NSNumber(value: value)) ?? String(value)
    }

    /// The buy price as a chip says it ("$215", "US$220", "$75 million").
    static func buyPriceAmount(_ x: MacBureauReportsExtras) -> String {
        if let value = x.buyPriceValue, value > 0, value.isFinite {
            let code = (x.currency.isEmpty ? "USD" : x.currency).uppercased()
            let prefix = currencySymbols[code] ?? "\(code) "
            if x.valueBasis != "company" {
                let whole = abs(value - value.rounded()) < 0.005
                return prefix + grouped(value, decimals: whole ? 0 : 2)
            }
            func total(_ v: Double) -> String {
                let r = (v * 100).rounded() / 100
                return r == r.rounded() ? String(Int(r)) : String(r)
            }
            if value >= 1_000_000 { return "\(prefix)\(total(value / 1_000_000)) trillion" }
            if value >= 1_000 { return "\(prefix)\(total(value / 1_000)) billion" }
            return "\(prefix)\(total(value)) million"
        }
        let pattern = "(US\\$|NT\\$|HK\\$|\\$|€|£)\\s?(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?)(?:\\s?(million|billion|trillion)\\b)?"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) else { return "" }
        for text in [x.callLabelEN, x.buyPriceText] where !text.isEmpty {
            let ns = text as NSString
            if let m = regex.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) {
                let unit = m.range(at: 3).location == NSNotFound ? "" : " " + ns.substring(with: m.range(at: 3)).lowercased()
                return ns.substring(with: m.range(at: 1)) + ns.substring(with: m.range(at: 2)) + unit
            }
        }
        return ""
    }

    /// The memo's call as a chip (verdictChip), or nil when it records none.
    static func verdict(_ r: MacReport, _ x: MacBureauReportsExtras?) -> (label: String, tone: MacBureauReportsTone)? {
        guard let x, !x.decision.isEmpty else { return nil }
        let key = decisionKey(x.decision)
        if isBuffett(r) {
            let amount = key == "too hard" ? "" : buyPriceAmount(x)
            switch key {
            case "buy":
                return (amount.isEmpty ? "Buy" : "Buy · up to \(amount)", .success)
            case "pass":
                let kind = (x.passKind == "price" || x.passKind == "business") ? x.passKind : (amount.isEmpty ? "" : "price")
                if kind == "price" {
                    return (amount.isEmpty ? "Pass at today's price" : "Pass · buy ≤ \(amount)", .notice)
                }
                return (kind == "business" ? "Pass · not at any price" : "Pass", .neutral)
            case "too hard":
                return ("Too Hard", .purple)
            default:
                return (x.decision, .neutral)
            }
        }
        switch key {
        case "strong buy": return ("Strong Buy", .success)
        case "buy": return ("Buy", .success)
        case "invest": return ("Invest", .success)
        case "watch": return ("Watch", .teal)
        case "pass": return ("Pass", .neutral)
        default: return (x.decision, .neutral)
        }
    }

    /// The memo's one-line headline, in English (or the Chinese when that is all it has).
    static func headline(_ x: MacBureauReportsExtras?) -> String {
        guard let x else { return "" }
        return x.headlineEN.isEmpty ? x.headlineZH : x.headlineEN
    }

    /// Draft, In review, Approved (by), Withdrawn — for a finished memo or one whose review moved.
    static func review(_ r: MacReport, _ x: MacBureauReportsExtras?) -> (label: String, tone: MacBureauReportsTone)? {
        guard isMemo(r) else { return nil }
        let raw = x?.reviewState ?? ""
        let state = ["draft", "in_review", "approved", "withdrawn"].contains(raw) ? raw : "draft"
        if state == "draft" && !isComplete(r) { return nil }
        switch state {
        case "in_review": return ("In review", .info)
        case "approved":
            let name = x?.reviewer ?? ""
            return (name.isEmpty ? "Approved" : "Approved by \(name)", .success)
        case "withdrawn": return ("Withdrawn", .danger)
        default: return ("Draft", .neutral)
        }
    }

    /// The quality gates' chip: Checked, "n P0", "n flagged".
    static func quality(_ x: MacBureauReportsExtras?) -> (label: String, flagged: Bool)? {
        guard let x, !x.gates.isEmpty else { return nil }
        let flagged = x.gates.contains { $0.flagged }
        let p0 = x.gates.reduce(0) { $0 + $1.p0 }
        let findings = x.gates.reduce(0) { $0 + $1.findings }
        if !flagged { return ("Checked", false) }
        if p0 > 0 { return ("\(p0) P0", true) }
        return ("\(max(findings, 1)) flagged", true)
    }

    /// What the number check found (factCheckChip), for a finished memo.
    static func factCheck(_ r: MacReport, _ x: MacBureauReportsExtras?) -> (label: String, tone: MacBureauReportsTone)? {
        guard isMemo(r), isComplete(r) else { return nil }
        guard let x, x.factPresent, x.factStatus != "not_run" else { return ("Checks not run", .neutral) }
        if x.factStatus == "error" { return ("Number check failed", .neutral) }
        if x.factThin || x.factStatus == "not_checkable" { return ("Not checkable: no sources on file", .neutral) }
        if x.factChecked == 0 || x.factStatus == "no_figures" { return ("No figures to check", .neutral) }
        let flagged = x.factNotTraced > 0 || x.factP0 > 0 || x.factStatus == "warn" || x.factStatus == "fail"
        var label = "\(x.factVerified) of \(x.factChecked) verified"
        if x.factNotTraced > 0 { label += " · \(x.factNotTraced) not traced" }
        return (label, flagged ? .warning : x.factVerified > 0 ? .success : .neutral)
    }

    /// "Changed from Buy" / "Unstable call · was Buy", when the call moved from the previous memo.
    static func changedFrom(_ r: MacReport, _ x: MacBureauReportsExtras?) -> String {
        guard let x, !x.verdictChangedFrom.isEmpty else { return "" }
        let word = decisionWord(x.verdictChangedFrom, r)
        return x.unstableCall ? "Unstable call · was \(word)" : "Changed from \(word)"
    }

    /// "Written Sep 1 · 21 days ago · latest source Jun 13", for a finished memo.
    static func freshness(_ r: MacReport, _ x: MacBureauReportsExtras?) -> (text: String, stale: Bool)? {
        guard isMemo(r), isComplete(r) else { return nil }
        let calendar = Calendar.current
        func day(_ raw: String) -> Date? { date(raw).map { calendar.startOfDay(for: $0) } }
        guard let written = day(x?.memoAsOf ?? "") ?? day(x?.reportReadyAt ?? "") ?? day(r.createdAt ?? "") else { return nil }
        let today = calendar.startOfDay(for: Date())
        let age = max(0, calendar.dateComponents([.day], from: written, to: today).day ?? 0)
        func short(_ d: Date) -> String {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US")
            f.dateFormat = calendar.component(.year, from: d) == calendar.component(.year, from: today) ? "MMM d" : "MMM d, yyyy"
            return f.string(from: d)
        }
        var parts = ["Written \(short(written))", age == 0 ? "today" : age == 1 ? "yesterday" : "\(age) days ago"]
        if let source = day(x?.evidenceLatest ?? ""),
           (calendar.dateComponents([.day], from: source, to: written).day ?? 0) > 14 {
            parts.append("latest source \(short(source))")
        }
        return (parts.joined(separator: " · "), age > 30)
    }

    /// Whether the row's line of tags has anything on it.
    static func hasTags(_ r: MacReport, _ x: MacBureauReportsExtras?) -> Bool {
        review(r, x) != nil || state(r) == "warnings" || hasICMemo(r) || x?.structureVersion == "v2"
            || quality(x) != nil || (x?.openFlags ?? 0) > 0 || factCheck(r, x) != nil
            || !changedFrom(r, x).isEmpty || !(x?.dismissedAt ?? "").isEmpty || !(x?.supersededBy ?? "").isEmpty
    }
}

// MARK: - A row of the list

/// `.doc-row`: the company's mark, its name and the date, the report's type and state, the
/// call and its headline, and the tags under them. Chosen, a slip of fresh paper with a brass
/// ribbon down the edge it was pulled out by.
struct MacBureauReportsRow: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport
    let extras: MacBureauReportsExtras?
    let company: MacCompany?
    let nested: Bool
    let olderCount: Int
    let expanded: Bool
    let selected: Bool
    let select: () -> Void
    let toggleGroup: () -> Void
    @State private var hovered = false
    @State private var continueArmed = false
    @State private var continuing = false

    private typealias Model = MacBureauReportsModel

    private func continuePaused() {
        guard !continuing else { return }
        guard continueArmed else {
            continueArmed = true
            Task {
                try? await Task.sleep(for: .seconds(4))
                continueArmed = false
            }
            return
        }
        continueArmed = false
        continuing = true
        Task {
            await store.resumeReport(id: report.id)
            continuing = false
        }
    }
    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 12, style: .circular)
        HStack(alignment: .top, spacing: 12) {
            mark.padding(.top, 2)
            VStack(alignment: .leading, spacing: 0) {
                nameLine
                typeLine.padding(.top, 2)
                if let verdictLine { verdictLine.padding(.top, 4) }
                if Model.hasTags(report, extras) { tags.padding(.top, 6) }
                if olderCount > 0 {
                    // An inline button on a 24pt line: the browser leaves 3pt of that line below it.
                    MacBureauReportsLinkButton(
                        title: expanded ? "Hide earlier versions" : olderCount == 1 ? "1 earlier version" : "\(olderCount) earlier versions",
                        icon: expanded ? "chevron-down" : "chevron-right",
                        style: .compact,
                        action: toggleGroup
                    )
                    .padding(.top, 4)
                    .padding(.bottom, 3)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background {
            // The row is a button under its content (whose own buttons sit on top of it).
            Button(action: select) {
                ZStack {
                    background(shape)
                    Color.clear
                }
                .contentShape(shape)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(Model.companyName(report)), \(Model.typeLabel(report))")
        }
        .contentShape(shape)
        .onTapGesture(perform: select)
        .onHover { hovered = $0 }
        .padding(.leading, nested ? 17.6 : 0)
        .overlay(alignment: .leading) {
            if nested {
                Rectangle()
                    .fill(ink.ink(0.12))
                    .frame(width: 1)
                    .padding(.vertical, 6.4)
                    .offset(x: 8.8)
            }
        }
        .contextMenu { menuItems }
    }

    @ViewBuilder
    private func background(_ shape: RoundedRectangle) -> some View {
        if selected {
            shape
                .fill(ink.raised)
                .shadow(color: ink.shadow(0.08), radius: 1.5, y: 1)
                .overlay(
                    shape.subtracting(shape.offset(x: 3, y: 0))
                        .fill(ink.accentGlow(1))
                )
                .overlay(shape.inset(by: -0.5).stroke(ink.ink(0.06), lineWidth: 1))
        } else if hovered {
            shape.fill(ink.ink(0.035))
        }
    }

    private var mark: some View {
        let size: CGFloat = nested ? 26 : 34
        return Group {
            if let company {
                MacBureauReportsMark(company: company, size: size)
            } else {
                MacBureauReportsMark(
                    name: Model.companyName(report),
                    ticker: extras?.ticker.isEmpty == false ? extras?.ticker : nil,
                    companyId: report.companyId,
                    logoUrl: extras?.logoUrl.isEmpty == false ? extras?.logoUrl : nil,
                    website: extras?.website.isEmpty == false ? extras?.website : nil,
                    size: size
                )
            }
        }
    }

    private var nameLine: some View {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                MacBureauReportsTruncating {
                    Text(Model.companyName(report))
                        .font(BSHType.bureauSans(14, weight: .semibold))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .frame(height: 20)
                }
                if let x = extras, x.isLatest == true, x.versionCount > 1 {
                    MacBureauReportsTag(text: "Latest", foreground: ink.accentInk, background: ink.accentSoft)
                        .help("The newest finished memo of this type on this company")
                } else if nested, let x = extras, x.versionCount > 1 {
                    Text("Version \(x.versionIndex) of \(x.versionCount)")
                        .font(BSHType.bureauSans(10).monospacedDigit())
                        .tracking(0.12)
                        .foregroundStyle(ink.muted)
                        .fixedSize()
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(Model.dateLabel(report.createdAt))
                .font(BSHType.bureauSans(11).monospacedDigit())
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .lineLimit(1)
                .fixedSize()
                .padding(.leading, 8)
        }
    }

    private var typeLine: some View {
        MacBureauReportsOverflow {
            typeLineContent
        }
    }

    private var typeLineContent: some View {
        HStack(spacing: 0) {
            Text(Model.typeLabel(report))
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauLines(16, size: 12)
                .help(Model.typeLabel(report))
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 4) {
                statusChip
                ForEach(downloads, id: \.self) { lang in
                    MacBureauReportsDownload(report: report, language: lang)
                }
                moreMenu
            }
            .padding(.leading, 8)
        }
        .frame(minHeight: 20)
    }

    @ViewBuilder
    private var statusChip: some View {
        let state = Model.state(report)
        if Model.isDocless(report, extras) {
            MacBureauReportsChip(text: "No document", icon: "file-exclamation-point", foreground: ink.secondary, background: ink.ink(0.06))
        } else if Model.listStatus(report) == "complete" && !Model.isMemo(report) {
            MacBureauReportsChip(text: "Ready", icon: "circle-check", foreground: ink.successInk, background: ink.successSoft)
        } else if state == "running" {
            MacBureauReportsChip(text: "Running", icon: "loader-circle", spinning: true, foreground: ink.reportsInfoInk, background: ink.reportsInfoSoft)
        } else if state == "cards_ready" {
            MacBureauReportsChip(text: "Cards ready", icon: "circle-alert", foreground: ink.warningInk, background: ink.reportsWarningSoft)
        } else if state == "paused" {
            MacBureauReportsChip(text: "English ready — paused", icon: "circle-pause", foreground: ink.reportsNoticeInk, background: ink.reportsNoticeSoft)
                .help(report.stage ?? "")
            // Continue from the row: the Chinese, the artifacts and the IC memo. It runs the
            // model, so it asks twice.
            Button(continuing ? "Resuming…" : continueArmed ? "Click again to continue — this runs the model" : "Continue (Chinese + IC memo)") {
                continuePaused()
            }
            .buttonStyle(MacBureauReportsRowPill())
            .disabled(continuing)
        } else if state == "failed" {
            MacBureauReportsChip(text: "Failed", foreground: ink.dangerInk, background: ink.dangerSoft)
        }
    }

    /// The row's Word downloads, for a memo and a reader who may export.
    private var downloads: [String] {
        guard Model.isMemo(report), store.can("memo:export") else { return [] }
        let urls = report.downloadUrls ?? [:]
        return ["en", "zh"].filter { urls[$0] != nil }
    }

    private var moreMenu: some View {
        Menu { menuItems } label: {
            MacBureauReportsRowMore()
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More actions")
    }

    @ViewBuilder
    private var menuItems: some View {
        if let company {
            Button("Open Studio") { store.openCompanyPage(company) }
        }
        Button("Copy link") {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(MacConfig.webReportURL(id: report.id).absoluteString, forType: .string)
        }
        Divider()
        Button("Open in a new window") { store.openReportWindow(report) }
            .disabled(!Model.canOpen(report, extras))
        Button("Open in the Research Browser") {
            store.openInEmbeddedBrowser(MacConfig.webReportURL(id: report.id))
        }
    }

    private var verdictLine: AnyView? {
        let verdict = Model.verdict(report, extras)
        let headline = Model.headline(extras)
        guard verdict != nil || !headline.isEmpty else { return nil }
        return AnyView(
            HStack(spacing: 6) {
                if let verdict {
                    let tone = ink.reportsTone(verdict.tone)
                    MacBureauReportsTag(text: verdict.label, foreground: tone.foreground, background: tone.background)
                }
                if !headline.isEmpty {
                    Text(headline)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .offset(y: 0.5)
                        .help(headline)
                }
            }
            .frame(minHeight: 15)
        )
    }

    private var tags: some View {
        MacBureauReportsFlow(spacing: 4) {
            if let review = Model.review(report, extras) {
                let tone = ink.reportsTone(review.tone)
                MacBureauReportsTag(text: review.label, foreground: tone.foreground, background: tone.background)
            }
            if Model.state(report) == "warnings" {
                MacBureauReportsTag(text: "Attention", icon: "circle-alert", foreground: ink.warningInk, background: ink.reportsWarningSoft)
            }
            if Model.hasICMemo(report) {
                MacBureauReportsTag(text: "IC memo", foreground: ink.secondary, background: ink.ink(0.06))
                    .help("Internal IC decision memo — never shared outside BSH")
            }
            if extras?.structureVersion == "v2" {
                MacBureauReportsTag(text: "IC template", foreground: ink.accentInk, background: ink.accentSoft)
                    .help("Written on the founder's IC template (v2)")
            }
            if let quality = Model.quality(extras) {
                MacBureauReportsTag(
                    text: quality.label, icon: "sparkles", tabular: true,
                    foreground: quality.flagged ? ink.warningInk : ink.successInk,
                    background: quality.flagged ? ink.reportsWarningSoft : ink.successSoft
                )
            }
            if let flags = extras?.openFlags, flags > 0 {
                MacBureauReportsTag(text: "\(flags)", icon: "flag", tabular: true, foreground: ink.warningInk, background: ink.reportsWarningSoft)
                    .help(flags == 1 ? "1 open flag" : "\(flags) open flags")
            }
            if let fact = Model.factCheck(report, extras) {
                let tone = ink.reportsTone(fact.tone)
                MacBureauReportsTag(text: fact.label, icon: "shield-check", tabular: true, foreground: tone.foreground, background: tone.background)
            }
            let changed = Model.changedFrom(report, extras)
            if !changed.isEmpty {
                MacBureauReportsTag(
                    text: changed, icon: extras?.unstableCall == true ? "triangle-alert" : nil,
                    foreground: ink.warningInk, background: ink.reportsWarningSoft
                )
            }
            if let x = extras, !x.dismissedAt.isEmpty || !x.supersededBy.isEmpty {
                MacBureauReportsTag(
                    text: x.supersededBy.isEmpty ? "Dismissed" : "Replaced", weight: .medium,
                    foreground: ink.muted, background: ink.ink(0.06)
                )
            }
        }
    }
}

/// A row's small brass button (`btn-filled btn-sm !px-2 !py-0.5 !text-caption1`).
private struct MacBureauReportsRowPill: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        MacBureauReportsRowPillBody(configuration: configuration)
    }
}

private struct MacBureauReportsRowPillBody: View {
    let configuration: ButtonStyleConfiguration
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        configuration.label
            .font(BSHType.bureauSans(11, weight: .medium))
            .tracking(0.066)
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(Color.bshFixed(BSHRGB(255, 253, 246)))
            .bureauLines(14, size: 11)
            .padding(.vertical, 2)
            .padding(.horizontal, 8)
            .background(
                Capsule()
                    .fill(hovered && isEnabled ? ink.accentHover : ink.accent)
                    .overlay(Capsule().fill(LinearGradient(
                        stops: [.init(color: .white.opacity(0.16), location: 0), .init(color: .white.opacity(0), location: 0.6)],
                        startPoint: .top, endPoint: .bottom
                    )))
                    .background(Capsule().inset(by: -0.5).stroke(ink.accentHover.opacity(0.55), lineWidth: 1))
            )
            .contentShape(Capsule())
            .offset(y: configuration.isPressed ? 0.5 : 0)
            .opacity(isEnabled ? 1 : 0.4)
            .onHover { hovered = $0 }
    }
}

/// The row's "…" (a 20pt square, washed in ink when pointed at).
private struct MacBureauReportsRowMore: View {
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        LucideIcon("ellipsis", size: 14)
            .foregroundStyle(hovered ? ink.ink : ink.muted)
            .frame(width: 20, height: 20)
            .background(RoundedRectangle(cornerRadius: 5, style: .circular).fill(hovered ? ink.ink(0.06) : .clear))
            .contentShape(Rectangle())
            .onHover { hovered = $0 }
    }
}

/// A row's "EN" / "ZH": the memo's Word file, saved where the reader chooses.
private struct MacBureauReportsDownload: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport
    let language: String
    @State private var hovered = false
    @State private var busy = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button {
            Task { await save() }
        } label: {
            HStack(spacing: 2) {
                LucideIcon("download", size: 12)
                Text(language.uppercased())
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
            }
            .foregroundStyle(hovered ? ink.ink : ink.muted)
            .padding(.horizontal, 4)
            .frame(height: 16)
            .background(RoundedRectangle(cornerRadius: 5, style: .circular).fill(hovered ? ink.ink(0.06) : .clear))
            .contentShape(Rectangle())
            .opacity(busy ? 0.5 : 1)
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(language == "en" ? "Download English (.docx)" : "下载中文 (.docx)")
    }

    private func save() async {
        guard !busy, let path = report.downloadUrls?[language] else { return }
        busy = true
        defer { busy = false }
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: path) else { return }
        let panel = NSSavePanel()
        let name = MacBureauReportsModel.companyName(report)
        panel.nameFieldStringValue = "\(name) — \(MacBureauReportsModel.typeLabel(report)) (\(language.uppercased())).docx"
        if panel.runModal() == .OK, let url = panel.url {
            try? data.write(to: url, options: .atomic)
        }
    }
}

/// Tags that wrap onto a second line when the row runs out of width (`flex-wrap`).
struct MacBureauReportsFlow: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                y += line + spacing
                x = 0
                line = 0
            }
            x += size.width + spacing
            line = max(line, size.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: proposal.width ?? widest, height: y + line)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, line: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                y += line + spacing
                x = bounds.minX
                line = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            line = max(line, size.height)
        }
    }
}

/// A logo on the folded list's rail: lifts when pointed at; the open report's stays lifted.
struct MacBureauReportsRailMark: View {
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport
    let extras: MacBureauReportsExtras?
    let company: MacCompany?
    let selected: Bool
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            Group {
                if let company {
                    MacBureauReportsMark(company: company, size: 26)
                } else {
                    MacBureauReportsMark(name: MacBureauReportsModel.companyName(report), companyId: report.companyId, size: 26)
                }
            }
            .shadow(color: .black.opacity(selected ? (colorScheme == .dark ? 0.55 : 0.2) : 0), radius: 2.5, y: 2)
            .padding(3)
            .scaleEffect(selected ? 1.14 : hovered ? 1.1 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: hovered)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help("\(MacBureauReportsModel.companyName(report)) — \(MacBureauReportsModel.typeLabel(report))")
    }
}

// MARK: - The document viewer

/// DocumentViewerWindow.vue: one slim bar naming the report (or "Document Viewer Window"),
/// its controls on the right; a line with the call and its review for a finished memo; and
/// the document, or what the run is doing when there is none.
struct MacBureauReportsViewer: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport?
    let extras: MacBureauReportsExtras?
    let company: MacCompany?

    private typealias Model = MacBureauReportsModel
    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var sources: [String] {
        guard let report, Model.canOpen(report, extras) else { return [] }
        let keys = Set(((report.downloadUrls ?? [:]).keys.map { $0.lowercased() }) + ((report.previewUrls ?? [:]).keys.map { $0.lowercased() }))
        let order = ["en": 0, "zh": 1, "internal": 2, "internal_zh": 3]
        let readable = keys.filter { !$0.hasPrefix("internal") || store.canEditMemo }
        let sorted = readable.sorted { (order[$0] ?? 9) < (order[$1] ?? 9) }
        return sorted.isEmpty ? ["en"] : sorted
    }

    private var showMeta: Bool {
        guard let report, Model.isMemo(report), Model.isComplete(report), !sources.isEmpty else { return false }
        return Model.verdict(report, extras) != nil || Model.review(report, extras) != nil || Model.freshness(report, extras) != nil
    }

    /// The website drops the Export button's word when its viewer is under 900pt wide.
    @State private var compact = true
    /// PDF, or the Word file laid out as pages (the website's "Web"), where a memo has both.
    @AppStorage("bsh.docViewerMode") private var viewMode = "pdf"
    /// A Word file fetched and shown here rather than through the Mac's reader (which keeps to
    /// the memo's PDF, English or Chinese): the IC memo, or the memo in the Web view.
    @State private var sideDocument: (reportId: String, key: String, url: URL)?
    @State private var sideLoading: String?
    @State private var sideError: String?

    /// The source on screen: the IC memo when it is open, else the reader's language.
    private var activeSource: String {
        if let key = sideLoading, key.hasPrefix("internal") { return key }
        if let side = sideDocument, side.reportId == report?.id, side.key.hasPrefix("internal") { return side.key }
        return store.readerLanguage
    }

    /// Both a PDF and a Word file for the language on screen: the PDF | Web switch.
    private func offersPdf(_ report: MacReport) -> Bool {
        let key = activeSource
        guard !key.hasPrefix("internal") else { return false }
        return report.previewUrls?[key] != nil && report.downloadUrls?[key] != nil
    }

    /// The Word file the viewer should show beside the reader, if any ("internal", or "word:en").
    private var wantedSide: String? {
        guard let report else { return nil }
        if activeSource.hasPrefix("internal") { return activeSource }
        return viewMode == "web" && offersPdf(report) ? "word:\(activeSource)" : nil
    }

    /// The document on screen, for Export.
    private var shownDocument: URL? {
        guard let report else { return nil }
        if let side = sideDocument, side.reportId == report.id, side.key == wantedSide { return side.url }
        return store.openReportId == report.id ? store.openDocumentURL : nil
    }

    private func choose(_ key: String, for report: MacReport) {
        sideError = nil
        if key.hasPrefix("internal") {
            Task { await loadSide(key, for: report) }
            return
        }
        if let side = sideDocument, side.key.hasPrefix("internal") { sideDocument = nil }
        store.readerLanguage = key
        Task { await store.openMemo(report, language: key) }
    }

    /// Fetches a Word file (the IC memo, or the memo's for the Web view) into a temporary file.
    private func loadSide(_ key: String, for report: MacReport) async {
        if let side = sideDocument, side.reportId == report.id, side.key == key { return }
        let language = key.hasPrefix("word:") ? String(key.dropFirst(5)) : key
        guard let path = report.downloadUrls?[language] ?? report.downloadUrls?[language.uppercased()] else { return }
        sideLoading = key
        defer { if sideLoading == key { sideLoading = nil } }
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: path) else {
            sideError = "This file could not be previewed here. Download it instead."
            return
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("bsh-memo-\(report.id)-\(language)-word.docx")
        do {
            try data.write(to: url, options: .atomic)
            sideDocument = (report.id, key, url)
        } catch {
            sideError = error.localizedDescription
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
                .overlay(alignment: .bottom) { Rectangle().fill(ink.rule).frame(height: 1) }
            if showMeta, let report {
                metaBar(report)
                    .overlay(alignment: .bottom) { Rectangle().fill(ink.rule).frame(height: 1) }
            }
            // Paused after the English memo, with that memo open: read it here, continue from here.
            if let report, !sources.isEmpty, Model.state(report) == "paused" {
                MacBureauReportsPausedStrip(report: report)
                    .overlay(alignment: .bottom) { Rectangle().fill(ink.rule).frame(height: 1) }
            }
            ZStack {
                ink.reportsViewerBody
                content
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(GeometryReader { geo in
            Color.clear
                .onAppear { compact = geo.size.width < 900 }
                .onChange(of: geo.size.width) { _, width in compact = width < 900 }
        })
        .onChange(of: report?.id) { _, _ in
            sideError = nil
            sideLoading = nil
        }
        // The Web view's Word file follows the report, its language and the switch.
        .task(id: "\(report?.id ?? "")|\(wantedSide ?? "")") {
            guard let report, let key = wantedSide, key.hasPrefix("word:") else { return }
            await loadSide(key, for: report)
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 8) {
            HStack(spacing: 8) {
                if let report {
                    Group {
                        if let company {
                            MacBureauReportsMark(company: company, size: 20)
                        } else {
                            MacBureauReportsMark(name: Model.companyName(report), companyId: report.companyId, size: 20)
                        }
                    }
                    Text("\(Model.companyName(report)) — \(Model.typeLabel(report))")
                        .font(BSHType.bureauSans(14, weight: .semibold))
                        .tracking(-0.28)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .help("\(Model.companyName(report)) — \(Model.typeLabel(report))")
                    if extras?.structureVersion == "v2" {
                        MacBureauReportsChip(text: "IC template", foreground: ink.accentInk, background: ink.accentSoft)
                    }
                    if let company {
                        Button {
                            store.openCompanyPage(company)
                        } label: {
                            LucideIcon("external-link", size: 12)
                                .foregroundStyle(ink.accent)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help("Company Profile: \(company.name ?? company.id)")
                    }
                    if !showMeta {
                        Text("· \(Model.dateLabel(report.createdAt))")
                            .font(BSHType.bureauSans(12).monospacedDigit())
                            .foregroundStyle(ink.muted)
                            .lineLimit(1)
                            .fixedSize()
                            .bureauLines(16, size: 12)
                    }
                } else {
                    LucideIcon("file-text", size: 16)
                        .foregroundStyle(ink.accent)
                    Text("Document Viewer Window")
                        .font(BSHType.bureauSans(14, weight: .semibold))
                        .tracking(-0.28)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(height: 20)

            if let report {
                controls(report)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .padding(.bottom, 7)
    }

    @ViewBuilder
    private func controls(_ report: MacReport) -> some View {
        HStack(spacing: 6) {
            if store.openReportId == report.id && store.openDocumentOverlayData != nil {
                MacBureauViewerToggle(icon: "pen-line", on: $store.showAnnotationOverlay, help: "Show the iPad's Apple Pencil ink")
            }
            if sources.count > 1 {
                MacBureauViewerSources(sources: sources, selection: Binding(
                    get: { activeSource },
                    set: { key in choose(key, for: report) }
                ))
            }
            if offersPdf(report) {
                MacBureauViewerModeSwitch(mode: $viewMode)
            }
            if !sources.isEmpty, let url = shownDocument {
                ShareLink(item: url) {
                    MacBureauViewerBoxLabel(icon: "download", title: compact ? nil : "Export", chevron: true)
                }
                .buttonStyle(.plain)
                .help("Export options")
            }
            if !sources.isEmpty || Model.isMemo(report) {
                Menu {
                    Button("Ask Warren about this memo") {
                        let prompt = "I am reviewing this investment memo (\(report.displayTitle)). What are your primary reflections on the return on invested capital (ROIC), durable competitive advantages, and conservative valuation assumptions?"
                        store.askWarren(prompt, context: .memo(reportId: report.id, page: nil, selectionText: nil), company: company)
                    }
                    .disabled(!store.canRunTasks || store.copilotStreaming)
                    Button("Open in the Research Browser") {
                        store.openInEmbeddedBrowser(MacConfig.webReportURL(id: report.id))
                    }
                    Button("Copy link") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(MacConfig.webReportURL(id: report.id).absoluteString, forType: .string)
                    }
                } label: {
                    MacBureauViewerBoxLabel(icon: "ellipsis", title: nil, chevron: false)
                }
                .menuStyle(.button)
                .buttonStyle(.plain)
                .menuIndicator(.hidden)
                .fixedSize()
                .help("More")
            }
            Button {
                if sources.isEmpty {
                    store.openInEmbeddedBrowser(MacConfig.webReportURL(id: report.id))
                } else {
                    store.openReportWindow(report)
                }
            } label: {
                MacBureauViewerBoxLabel(icon: "maximize-2", title: nil, chevron: false)
            }
            .buttonStyle(.plain)
            .help(sources.isEmpty ? "Open in the Research Browser" : "Open in a window of its own")
        }
    }

    private func metaBar(_ report: MacReport) -> some View {
        HStack(spacing: 8) {
            if let verdict = Model.verdict(report, extras) {
                let tone = ink.reportsTone(verdict.tone)
                MacBureauReportsChip(text: verdict.label, foreground: tone.foreground, background: tone.background)
            }
            if let review = Model.review(report, extras) {
                let tone = ink.reportsTone(review.tone)
                MacBureauReportsChip(text: review.label, foreground: tone.foreground, background: tone.background)
            }
            if let fresh = Model.freshness(report, extras) {
                Text(fresh.text)
                    .font(BSHType.bureauSans(11, weight: fresh.stale ? .medium : .regular).monospacedDigit())
                    .tracking(0.066)
                    .foregroundStyle(fresh.stale ? ink.warningInk : ink.muted)
                    .lineLimit(1)
            }
            let changed = Model.changedFrom(report, extras)
            if !changed.isEmpty {
                MacBureauReportsChip(
                    text: changed, icon: extras?.unstableCall == true ? "triangle-alert" : nil,
                    foreground: ink.warningInk, background: ink.reportsWarningSoft
                )
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.top, 4)
        .padding(.bottom, 5)
    }

    // MARK: Body

    @ViewBuilder
    private var content: some View {
        if let report {
            if !Model.canOpen(report, extras) {
                MacBureauViewerStatus(report: report, extras: extras, company: company)
            } else if let wanted = wantedSide {
                if let side = sideDocument, side.reportId == report.id, side.key == wanted {
                    MacQuickLookView(url: side.url)
                        .padding(12)
                } else if let sideError {
                    loadError(report, message: sideError)
                } else {
                    VStack(spacing: 8) {
                        MacBureauReportsSpinner(size: 24)
                            .foregroundStyle(ink.accent)
                        Text("Loading preview…")
                            .font(BSHType.bureauSans(14))
                            .foregroundStyle(ink.muted)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            } else if store.openReportId == report.id, let url = store.openDocumentURL {
                document(url)
            } else if store.openReportId == report.id, !store.openingMemo, let error = store.openDocumentError {
                loadError(report, message: error)
            } else {
                VStack(spacing: 8) {
                    MacBureauReportsSpinner(size: 24)
                        .foregroundStyle(ink.accent)
                    Text("Loading preview…")
                        .font(BSHType.bureauSans(14))
                        .foregroundStyle(ink.muted)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            VStack(spacing: 0) {
                LucideIcon("file-text", size: 32)
                    .foregroundStyle(ink.subtle)
                    .padding(.bottom, 8)
                Text("Select a report to view")
                    .font(BSHType.bureauSans(14, weight: .medium))
                    .foregroundStyle(ink.secondary)
                    .frame(height: 20)
                Text("Choose any investment memo or diligence report from the catalog to open and inspect it in the document viewer window.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .multilineTextAlignment(.center)
                    .bureauLines(16, size: 12)
                    .frame(maxWidth: 448)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
            }
            // Centered, the stack can land on a half point; the browser paints it on a whole one.
            .reportsWholePoint()
            .padding(36)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func document(_ url: URL) -> some View {
        if store.openDocumentIsPDF {
            MacBureauReportsPDFView(
                url: url,
                overlayData: store.showAnnotationOverlay ? store.openDocumentOverlayData : nil,
                background: NSColor(srgbRed: ink.reportsViewerBodyRGB.r / 255, green: ink.reportsViewerBodyRGB.g / 255, blue: ink.reportsViewerBodyRGB.b / 255, alpha: 1)
            )
        } else {
            MacQuickLookView(url: url)
                .padding(12)
        }
    }

    private func loadError(_ report: MacReport, message: String) -> some View {
        VStack(spacing: 12) {
            LucideIcon("file-text", size: 24)
                .foregroundStyle(ink.danger)
                .frame(width: 48, height: 48)
                .background(Circle().fill(ink.danger.opacity(0.1)))
            VStack(spacing: 4) {
                Text("This file could not be previewed here. Download it instead.")
                    .font(BSHType.bureauSans(16, weight: .medium))
                    .foregroundStyle(ink.ink)
                    .multilineTextAlignment(.center)
                Text(message)
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 384)
            }
            Button {
                Task { await store.openMemo(report, language: store.readerLanguage) }
            } label: {
                HStack(spacing: 6) {
                    LucideIcon("refresh-cw", size: 14)
                    Text("Retry")
                }
            }
            .buttonStyle(MacBureauPillStyle(kind: .bordered))
            .controlSize(.small)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A run with no document to read: what it is doing, as the website's status card says it,
/// with its actions. Cancel, Resume and Clear each ask twice, as on the website.
private struct MacBureauViewerStatus: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport
    let extras: MacBureauReportsExtras?
    let company: MacCompany?
    @State private var armed: String?
    @State private var busy: String?
    @State private var failed = false

    private typealias Model = MacBureauReportsModel

    private var kind: String {
        switch Model.state(report) {
        case "running", "failed", "cards_ready", "paused": return Model.state(report)
        default: return "docless"
        }
    }

    private var title: String {
        switch kind {
        case "running": return "This report is being written"
        case "failed": return failureTitle
        case "cards_ready": return "Cards ready — review the studio cards"
        case "paused": return "English ready — paused"
        default: return "This report has no document"
        }
    }

    private var failureTitle: String {
        let kind = extras?.failureKind ?? ""
        let phase = (report.failurePhase ?? "").lowercased()
        let status = (report.status ?? "").lowercased()
        let stage = (report.stage ?? "").lowercased()
        if kind == "cancelled" || phase == "cancelled" || status == "cancelled" { return "The run was cancelled" }
        if kind == "interrupted" || ["shutdown", "orphaned", "interrupted"].contains(phase) || status == "failed_orphaned" {
            return "The run was interrupted before it finished"
        }
        if kind == "provider_limit" { return "Stopped at the model's usage limit" }
        if kind == "login" { return "The model tool was not signed in" }
        if kind == "timeout" { return "A step ran too long and was stopped" }
        if kind == "out_of_scope" || status == "failed_scope_check" { return "The scope check stopped this run" }
        if phase == "renderer_contract" || stage.contains("renderer") { return "Memo rendering failed" }
        if phase == "internal_diligence_memo" { return "Internal diligence memo failed" }
        if phase == "chinese_parity_gate" { return "Chinese memo parity check failed" }
        if phase == "quality_gate" || status == "failed_quality_gate" || stage.contains("quality") { return "Memo quality check failed" }
        return "Memo generation failed"
    }

    /// The run's job on the jobs poll, for its live transcript and its Cancel.
    private var job: MacActiveJob? {
        store.activeJobs.first { $0.reportId == report.id }
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let tone: (fg: Color, bg: Color, icon: String) = {
            switch kind {
            case "running": return (ink.reportsInfoInk, ink.reportsInfoSoft, "loader-circle")
            case "failed": return (ink.dangerInk, ink.dangerSoft, "circle-alert")
            case "cards_ready": return (ink.accentInk, ink.accentSoft, "sparkles")
            case "paused": return (ink.reportsNoticeInk, ink.reportsNoticeSoft, "circle-pause")
            default: return (ink.muted, ink.fillTertiary, "file-exclamation-point")
            }
        }()
        HStack(alignment: .top, spacing: 12) {
            Group {
                if kind == "running" {
                    MacBureauReportsSpinner(size: 16)
                } else {
                    LucideIcon(tone.icon, size: 16)
                }
            }
            .foregroundStyle(tone.fg)
            .frame(width: 36, height: 36)
            .background(Circle().fill(tone.bg))
            VStack(alignment: .leading, spacing: 0) {
                Text(title)
                    .font(BSHType.bureauSans(14, weight: .semibold))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .bureauLines(20, size: 14)
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line.text)
                        .font(line.style == .small ? BSHType.bureauSans(11).monospacedDigit() : BSHType.bureauSans(12))
                        .tracking(line.style == .small ? 0.066 : 0)
                        .foregroundStyle(line.style == .strong ? ink.ink : line.style == .small ? ink.muted : ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .bureauLines(line.style == .small ? 14 : 16, size: line.style == .small ? 11 : 12)
                        .padding(.top, line.gap)
                }
                if kind == "running", let progress = report.progress, progress > 0 {
                    VStack(alignment: .leading, spacing: 4) {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule().fill(ink.ink(0.08))
                                Capsule().fill(ink.accentGlow(1)).frame(width: geo.size.width * CGFloat(min(progress, 100)) / 100)
                            }
                        }
                        .frame(height: 4)
                        Text("\(progress)% done")
                            .font(BSHType.bureauSans(11).monospacedDigit())
                            .tracking(0.066)
                            .foregroundStyle(ink.muted)
                            .frame(height: 14)
                    }
                    .padding(.top, 8)
                }
                actions
                    .padding(.top, 16)
                if failed {
                    Text("That didn't go through. Try again.")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.danger)
                        .padding(.top, 8)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // `p-5` inside a 1pt border.
        .padding(21)
        .frame(maxWidth: 512)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .circular)
                .fill(ink.tray)
                .shadow(color: .black.opacity(0.05), radius: 1, y: 1)
        )
        .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(ink.rule, lineWidth: 1))
        .reportsWholePoint()
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onChange(of: report.id) { _, _ in
            armed = nil
            busy = nil
            failed = false
        }
    }

    private enum LineStyle { case body, strong, small }

    /// "Sep 20, 5:10 AM", as `toLocaleString("en-US", {month: "short", day, hour, minute})`.
    private var failedAt: String {
        guard let date = Model.date(report.updatedAt ?? report.createdAt) else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: date)
    }

    private var lines: [(text: String, style: LineStyle, gap: CGFloat)] {
        switch kind {
        case "running":
            var out: [(String, LineStyle, CGFloat)] = [("It opens here as soon as its first document is ready. You can leave this page; the run carries on.", .body, 4)]
            if let stage = job?.latestStage ?? report.stage, !stage.isEmpty { out.append(("Stage: \(stage)", .strong, 8)) }
            return out
        case "failed":
            var out: [(String, LineStyle, CGFloat)] = []
            let summary = extras?.failureSummary ?? ""
            let rawDetail = (extras?.failureDetail).flatMap { $0.isEmpty ? nil : $0 } ?? (report.error ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let detail = rawDetail != title && rawDetail != summary ? rawDetail : ""
            let rawStage = (report.stage ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let stage = rawStage != title && rawStage != detail ? rawStage : ""
            if !summary.isEmpty { out.append((summary, .strong, 4)) }
            if !stage.isEmpty { out.append((stage, .body, 4)) }
            if !detail.isEmpty {
                out.append((detail, .body, 4))
            } else if stage.isEmpty && summary.isEmpty {
                out.append(("The run stopped before it wrote a document.", .body, 4))
            }
            if let spend = extras?.failureSpend, spend > 0 {
                out.append((String(format: "Spent before it stopped: $%.2f (API-equivalent)", spend), .small, 8))
            }
            if !failedAt.isEmpty {
                let dismissed = !(extras?.dismissedAt ?? "").isEmpty
                out.append((dismissed ? "Failed \(failedAt)" : "Failed \(failedAt) — this is the preserved record of that run; it stays until a resume or a fresh run replaces it.", .small, 8))
            }
            if !(extras?.supersededBy ?? "").isEmpty {
                out.append(("A newer run for this company has replaced this record.", .small, 4))
            }
            if !(extras?.dismissedAt ?? "").isEmpty {
                out.append(("This failure record was cleared. It stays here for reference.", .small, 4))
            }
            return out
        case "cards_ready":
            return [("This Memo Studio investigation is waiting for review on the company's desk.", .body, 4)]
        case "paused":
            var out: [(String, LineStyle, CGFloat)] = [("The English memo is on file and opens here. Continuing writes the Chinese version, the artifacts and the IC memo — that runs the model again.", .body, 4)]
            if let stage = report.stage, !stage.isEmpty { out.append(("Stage: \(stage)", .strong, 8)) }
            return out
        default:
            return [("The run finished without writing a document to read.", .body, 4)]
        }
    }

    @ViewBuilder
    private var actions: some View {
        HStack(spacing: 8) {
            switch kind {
            case "running":
                if let job {
                    Button("Open live transcript") { openTranscript(job) }
                        .buttonStyle(MacBureauPillStyle(kind: .bordered))
                }
                Button(label("cancel")) { run("cancel") }
                    .buttonStyle(MacBureauPillStyle(kind: .bordered))
                    .disabled(busy != nil)
            case "failed":
                if extras?.resumeAvailable == true {
                    Button(label("resume")) { run("resume") }
                        .buttonStyle(MacBureauPillStyle(kind: .filled))
                        .disabled(busy != nil)
                }
                if (extras?.dismissedAt ?? "").isEmpty {
                    Button(label("dismiss")) { run("dismiss") }
                        .buttonStyle(MacBureauPillStyle(kind: .bordered))
                        .disabled(busy != nil)
                }
                Button("Generate report") { store.requestNewReport(for: company) }
                    .buttonStyle(MacBureauPillStyle(kind: .plain))
            case "paused":
                Button(label("resume")) { run("resume") }
                    .buttonStyle(MacBureauPillStyle(kind: .filled))
                    .disabled(busy != nil)
                if let job {
                    Button("Open live transcript") { openTranscript(job) }
                        .buttonStyle(MacBureauPillStyle(kind: .bordered))
                }
            case "cards_ready":
                if let company {
                    Button("Open Studio") { store.openCompanyPage(company) }
                        .buttonStyle(MacBureauPillStyle(kind: .bordered))
                }
            default:
                EmptyView()
            }
        }
        .controlSize(.small)
    }

    private func label(_ action: String) -> String {
        let paused = kind == "paused"
        if busy == action {
            return action == "cancel" ? "Cancelling…" : action == "resume" ? "Resuming…" : "Clearing…"
        }
        if armed == action {
            if action == "cancel" { return "Click again to confirm" }
            if action == "resume" { return paused ? "Click again to continue — this runs the model" : "Click again to resume — this runs the model" }
            return "Click again to clear"
        }
        if action == "cancel" { return "Cancel run" }
        if action == "resume" { return paused ? "Continue (Chinese + IC memo)" : "Resume" }
        return "Clear failure record"
    }

    /// The first click arms the button for four seconds; the second acts.
    private func run(_ action: String) {
        guard busy == nil else { return }
        guard armed == action else {
            armed = action
            Task {
                try? await Task.sleep(for: .seconds(4))
                if armed == action { armed = nil }
            }
            return
        }
        armed = nil
        busy = action
        failed = false
        let id = report.id
        Task {
            switch action {
            case "cancel":
                if let job = store.activeJobs.first(where: { $0.reportId == id }) {
                    await store.cancelJob(job)
                } else if (try? await MacAPIClient.shared.cancelReport(id: id)) == nil {
                    failed = true
                } else {
                    await store.refreshReports()
                }
            case "resume":
                await store.resumeReport(id: id)
            default:
                await store.dismissReport(id: id)
            }
            busy = nil
        }
    }

    private func openTranscript(_ job: MacActiveJob) {
        store.selectedJobId = job.id
        store.blotterTab = .jobs
        withAnimation(.easeInOut(duration: 0.18)) { store.showBlotter = true }
    }
}

/// The viewer's EN / ZH / IC memo switch: a groove, the chosen one in brass.
private struct MacBureauViewerSources: View {
    @Environment(\.colorScheme) private var colorScheme
    let sources: [String]
    @Binding var selection: String

    private func label(_ key: String) -> String {
        let both = sources.contains("internal") && sources.contains("internal_zh")
        switch key {
        case "internal": return both ? "IC memo · EN" : "IC memo"
        case "internal_zh": return both ? "IC memo · 中文" : "IC memo"
        default: return key.uppercased()
        }
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 4) {
            ForEach(sources, id: \.self) { key in
                let chosen = key == selection
                Button {
                    selection = key
                } label: {
                    Text(label(key))
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .foregroundStyle(chosen ? Color.white : ink.secondary)
                        .bureauLines(16.5, size: 11)
                        .padding(.vertical, 2)
                        .padding(.horizontal, 10)
                        .background(Capsule().fill(chosen ? ink.accent : .clear).shadow(color: .black.opacity(chosen ? 0.05 : 0), radius: 0.5, y: 0.5))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .help(key.hasPrefix("internal") ? "Internal IC decision memo — never shared outside BSH" : "")
            }
        }
        .padding(3)
        .background(Capsule().fill(ink.reportsSurfaceMuted))
        .overlay(Capsule().strokeBorder(ink.rule, lineWidth: 1))
    }
}

/// A run paused after its English memo: the notice under the viewer's bar, with Continue
/// (which runs the model, so it asks twice) and the run's live transcript.
private struct MacBureauReportsPausedStrip: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let report: MacReport
    @State private var armed = false
    @State private var busy = false

    private var job: MacActiveJob? { store.activeJobs.first { $0.reportId == report.id } }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 12) {
            LucideIcon("circle-pause", size: 14)
                .foregroundStyle(ink.reportsNoticeInk)
            (Text("English ready — paused").fontWeight(.semibold).foregroundColor(ink.reportsNoticeInk)
                + Text(" · The English memo is on file and opens here. Continuing writes the Chinese version, the artifacts and the IC memo — that runs the model again.").foregroundColor(ink.secondary))
                .font(BSHType.bureauSans(12))
                .fixedSize(horizontal: false, vertical: true)
                .bureauLines(16, size: 12)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let job {
                Button("Open live transcript") {
                    store.selectedJobId = job.id
                    store.blotterTab = .jobs
                    withAnimation(.easeInOut(duration: 0.18)) { store.showBlotter = true }
                }
                .buttonStyle(MacBureauPillStyle(kind: .bordered))
            }
            Button(busy ? "Resuming…" : armed ? "Click again to continue — this runs the model" : "Continue (Chinese + IC memo)") {
                guard !busy else { return }
                guard armed else {
                    armed = true
                    Task {
                        try? await Task.sleep(for: .seconds(4))
                        armed = false
                    }
                    return
                }
                armed = false
                busy = true
                Task {
                    await store.resumeReport(id: report.id)
                    busy = false
                }
            }
            .buttonStyle(MacBureauPillStyle(kind: .filled))
            .disabled(busy)
        }
        .controlSize(.small)
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .padding(.bottom, 7)
        .background(ink.reportsNoticeSoft)
    }
}

/// PDF (pages as they print) or Web (the Word file laid out as pages): a groove, the chosen
/// one in brass.
private struct MacBureauViewerModeSwitch: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var mode: String

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 2) {
            ForEach([("pdf", "PDF", "The PDF: pages as they print and forward"), ("web", "Web", "The Word file, laid out as its pages")], id: \.0) { option in
                let chosen = mode == option.0
                Button {
                    mode = option.0
                } label: {
                    Text(option.1)
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .foregroundStyle(chosen ? Color.white : ink.secondary)
                        .bureauLines(16.5, size: 11)
                        .padding(.vertical, 2)
                        .padding(.horizontal, 8)
                        .background(Capsule().fill(chosen ? ink.accent : .clear).shadow(color: .black.opacity(chosen ? 0.05 : 0), radius: 0.5, y: 0.5))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .help(option.2)
            }
        }
        .padding(3)
        .background(Capsule().fill(ink.reportsSurfaceMuted))
        .overlay(Capsule().strokeBorder(ink.rule, lineWidth: 1))
    }
}

/// A round toggle in the viewer's bar; on, brass with a white glyph.
private struct MacBureauViewerToggle: View {
    @Environment(\.colorScheme) private var colorScheme
    let icon: String
    @Binding var on: Bool
    let help: String
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button {
            on.toggle()
        } label: {
            LucideIcon(icon, size: 14)
                .foregroundStyle(on ? Color.white : hovered ? ink.ink : ink.muted)
                .frame(width: 26, height: 26)
                .background(Circle().fill(on ? ink.accent : hovered ? ink.reportsSurfaceMuted : .clear))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(help)
    }
}

/// The viewer's boxed buttons (Export, More, Full screen): 4pt corners, ruled, the tray's paper.
private struct MacBureauViewerBoxLabel: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    let icon: String
    let title: String?
    let chevron: Bool
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 4) {
            LucideIcon(icon, size: 14)
            if let title {
                Text(title)
                    .font(BSHType.bureauSans(12, weight: .medium))
            }
            if chevron {
                LucideIcon("chevron-down", size: 12)
                    .foregroundStyle(ink.muted)
            }
        }
        .foregroundStyle(hovered && isEnabled ? ink.ink : title == nil && !chevron ? ink.muted : ink.secondary)
        .padding(.horizontal, title == nil && !chevron ? 6 : 11)
        .frame(height: title == nil && !chevron ? 28 : title == nil ? 24 : 26)
        .frame(minWidth: 28)
        .background(RoundedRectangle(cornerRadius: 4, style: .circular).fill(hovered && isEnabled ? ink.reportsSurfaceMuted : ink.tray))
        .overlay(RoundedRectangle(cornerRadius: 4, style: .circular).strokeBorder(ink.rule, lineWidth: 1))
        .contentShape(Rectangle())
        .opacity(isEnabled ? 1 : 0.4)
        .onHover { hovered = $0 }
    }
}

/// The memo's PDF in PDFKit, on the viewer's paper rather than the window's gray, with the
/// iPad's ink laid over its pages (MacPDFKitView's overlay).
struct MacBureauReportsPDFView: NSViewRepresentable {
    let url: URL
    let overlayData: Data?
    let background: NSColor

    func makeCoordinator() -> MacPDFKitView.Coordinator {
        MacPDFKitView.Coordinator(onSelection: nil, onPageChange: nil)
    }

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.backgroundColor = background
        // The website's page sits 12pt in from the viewer's edges, 24pt from the next; PDFKit
        // adds 3pt round a page of its own.
        view.pageBreakMargins = NSEdgeInsets(top: 9, left: 9, bottom: 15, right: 9)
        view.document = PDFDocument(url: url)
        view.pageOverlayViewProvider = context.coordinator
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        view.backgroundColor = background
        if view.document?.documentURL != url {
            view.document = PDFDocument(url: url)
            context.coordinator.invalidateOverlay()
        }
        context.coordinator.updateOverlay(data: overlayData, canvasSize: nil, opacity: 0.95, in: view)
    }

    static func dismantleNSView(_ view: PDFView, coordinator: MacPDFKitView.Coordinator) {
        view.pageOverlayViewProvider = nil
    }
}

// MARK: - Transcripts (the Mac's own), in the same trays

/// A transcript in the list: its company's mark, title and date, kind and company, and how
/// long it is and how many passages were marked.
struct MacBureauReportsTranscriptRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let transcript: MacTranscript
    let company: MacCompany?
    let selected: Bool
    let select: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: 12, style: .circular)
        HStack(alignment: .top, spacing: 12) {
            Group {
                if let company {
                    MacBureauReportsMark(company: company, size: 34)
                } else {
                    LucideIcon("audio-lines", size: 16)
                        .foregroundStyle(ink.muted)
                        .frame(width: 34, height: 34)
                        .background(RoundedRectangle(cornerRadius: 34 * 0.28, style: .circular).fill(ink.ink(0.06)))
                }
            }
            .padding(.top, 2)
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(transcript.title)
                        .font(BSHType.bureauSans(14, weight: .semibold))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                        .frame(height: 20)
                    Spacer(minLength: 0)
                    Text(MacBureauReportsModel.dateLabel(transcript.callDate ?? transcript.createdAt))
                        .font(BSHType.bureauSans(11).monospacedDigit())
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .fixedSize()
                }
                Text([transcript.kindLabel, transcript.companyName].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .frame(height: 16)
                    .padding(.top, 2)
                HStack(spacing: 4) {
                    MacBureauReportsTag(text: "\(transcript.wordCount) words", foreground: ink.secondary, background: ink.ink(0.06))
                    if transcript.highlightCount > 0 {
                        MacBureauReportsTag(
                            text: transcript.highlightCount == 1 ? "1 highlight" : "\(transcript.highlightCount) highlights",
                            foreground: ink.accentInk, background: ink.accentSoft
                        )
                    }
                }
                .padding(.top, 6)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background {
            Button(action: select) {
                ZStack {
                    if selected {
                        shape.fill(ink.raised)
                            .shadow(color: ink.shadow(0.08), radius: 1.5, y: 1)
                            .overlay(shape.subtracting(shape.offset(x: 3, y: 0)).fill(ink.accentGlow(1)))
                            .overlay(shape.inset(by: -0.5).stroke(ink.ink(0.06), lineWidth: 1))
                    } else if hovered {
                        shape.fill(ink.ink(0.035))
                    }
                    Color.clear
                }
                .contentShape(shape)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(transcript.title)
        }
        .contentShape(shape)
        .onTapGesture(perform: select)
        .onHover { hovered = $0 }
    }
}

/// The chosen transcript in the viewer tray: its bar, the text, and its highlights beside it.
struct MacBureauReportsTranscriptViewer: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Binding var transcriptId: String?
    @State private var quote = ""
    @State private var note = ""
    @State private var saving = false
    @State private var errorText: String?
    @State private var confirmDelete: MacTranscript?

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var transcript: MacTranscript? { transcriptId.flatMap { store.transcriptById[$0] } }

    var body: some View {
        VStack(spacing: 0) {
            header
                .overlay(alignment: .bottom) { Rectangle().fill(ink.rule).frame(height: 1) }
            ZStack {
                ink.reportsViewerBody
                if let transcript {
                    HStack(spacing: 0) {
                        ScrollView {
                            Text(transcript.text)
                                .font(BSHType.bureauSans(13))
                                .foregroundStyle(ink.ink)
                                .lineSpacing(5)
                                .textSelection(.enabled)
                                .frame(maxWidth: 720, alignment: .leading)
                                .padding(24)
                                .frame(maxWidth: .infinity)
                        }
                        Rectangle().fill(ink.rule).frame(width: 1)
                        highlights(transcript)
                            .frame(width: 280)
                    }
                } else if transcriptId != nil {
                    VStack(spacing: 8) {
                        MacBureauReportsSpinner(size: 24).foregroundStyle(ink.accent)
                        Text("Loading preview…").font(BSHType.bureauSans(14)).foregroundStyle(ink.muted)
                    }
                } else {
                    VStack(spacing: 0) {
                        LucideIcon("audio-lines", size: 32)
                            .foregroundStyle(ink.subtle)
                            .padding(.bottom, 8)
                        Text("Select a transcript to read")
                            .font(BSHType.bureauSans(14, weight: .medium))
                            .foregroundStyle(ink.secondary)
                            .frame(height: 20)
                        Text("Read a call's transcript here and mark the passages that matter; highlights show up in Firm Memory and the IC room.")
                            .font(BSHType.bureauSans(12))
                            .foregroundStyle(ink.muted)
                            .multilineTextAlignment(.center)
                            .bureauLines(16, size: 12)
                            .frame(maxWidth: 448)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 4)
                    }
                    .padding(36)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task(id: transcriptId) {
            quote = ""
            note = ""
            errorText = nil
            if let id = transcriptId { await store.loadTranscript(id) }
        }
        .confirmationDialog(
            "Delete this transcript?",
            isPresented: Binding(get: { confirmDelete != nil }, set: { if !$0 { confirmDelete = nil } }),
            presenting: confirmDelete
        ) { t in
            Button("Delete", role: .destructive) {
                Task {
                    await store.deleteTranscript(t.id)
                    if store.transcriptById[t.id] == nil {
                        if transcriptId == t.id { transcriptId = nil }
                    } else {
                        errorText = store.error ?? "Could not delete the transcript."
                    }
                }
            }
        } message: { t in
            Text("\(t.title) and its \(t.highlightCount) highlight(s) will be permanently deleted. This cannot be undone.")
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            HStack(spacing: 8) {
                LucideIcon("audio-lines", size: 16).foregroundStyle(ink.accent)
                Text(transcript?.title ?? "Transcript Viewer")
                    .font(BSHType.bureauSans(14, weight: .semibold))
                    .tracking(-0.28)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                if let t = transcript {
                    let meta = [t.kindLabel, t.companyName, t.callDate.map { MacBureauReportsModel.dateLabel($0) }, t.participants.isEmpty ? nil : t.participants.joined(separator: ", ")]
                        .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                    Text("· \(meta)")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(height: 20)
            if let t = transcript {
                if let cid = t.companyId, let company = store.companies.first(where: { $0.id == cid }) {
                    Button {
                        store.showCompany(company)
                    } label: {
                        MacBureauViewerBoxLabel(icon: "external-link", title: company.title, chevron: false)
                    }
                    .buttonStyle(.plain)
                    .help("Open \(company.title)")
                }
                Button {
                    confirmDelete = t
                } label: {
                    MacBureauViewerBoxLabel(icon: "trash-2", title: nil, chevron: false)
                }
                .buttonStyle(.plain)
                .disabled(!store.canDeleteDocuments)
                .help("Delete transcript")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .frame(minHeight: 33)
    }

    private func highlights(_ t: MacTranscript) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Highlights")
                .font(.custom(BSHType.bureauSerif, size: 20))
                .foregroundStyle(ink.ink)
            Text("Paste a passage from the transcript and a note; highlights show up in Firm Memory and the IC room.")
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .fixedSize(horizontal: false, vertical: true)
            TextField("Quote", text: $quote, axis: .vertical)
                .lineLimit(2...5)
                .textFieldStyle(.dsField)
                .controlSize(.small)
            TextField("Why it matters", text: $note)
                .textFieldStyle(.dsField)
                .controlSize(.small)
            Button("Add highlight") { add(t) }
                .buttonStyle(MacBureauPillStyle(kind: .filled))
                .controlSize(.small)
                .disabled(quote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canEditMemo || saving)
            if let errorText {
                Text(errorText).font(BSHType.bureauSans(11)).foregroundStyle(ink.dangerInk)
            }
            Rectangle().fill(ink.rule).frame(height: 1).padding(.vertical, 4)
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(t.highlights) { h in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("“\(h.text)”")
                                .font(.custom(BSHType.bureauSerifItalic, size: 14))
                                .foregroundStyle(ink.ink)
                            if let n = h.note, !n.isEmpty {
                                Text(n).font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary)
                            }
                            HStack {
                                Text(h.createdBy?.isEmpty == false ? h.createdBy! : "dev")
                                    .font(BSHType.bureauSans(11))
                                    .foregroundStyle(ink.subtle)
                                Spacer()
                                if store.canEditMemo {
                                    Button {
                                        Task { await store.removeHighlight(transcriptId: t.id, highlightId: h.id) }
                                    } label: {
                                        LucideIcon("x", size: 12).foregroundStyle(ink.muted)
                                    }
                                    .buttonStyle(.plain)
                                    .help("Remove highlight")
                                }
                            }
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.accentSoft))
                        .draggable("“\(h.text)” — \(t.title)")
                    }
                }
            }
        }
        .padding(12)
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private func add(_ t: MacTranscript) {
        let q = quote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !saving else { return }
        let draft = quote, draftNote = note, id = t.id
        saving = true
        errorText = nil
        Task {
            let ok = await store.addHighlight(transcriptId: id, text: q, note: draftNote)
            saving = false
            guard ok else {
                errorText = store.error ?? "Could not save the highlight. The transcript may have been deleted."
                return
            }
            if transcriptId == id && quote == draft && note == draftNote {
                quote = ""
                note = ""
            }
        }
    }
}
