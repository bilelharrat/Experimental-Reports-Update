import Foundation

struct MacCompany: Identifiable, Hashable, Decodable {
    let id: String
    let name: String?
    let ticker: String?
    let companyType: String?
    let status: String?
    let sector: String?
    let industry: String?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector, industry
        case companyType = "company_type"
    }

    var title: String { name ?? id }

    var subtitle: String {
        [ticker, sector ?? industry]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

struct MacMemoFile: Decodable, Hashable {
    let language: String?
    let path: String?
    let pdfPath: String?

    enum CodingKeys: String, CodingKey {
        case language, path
        case pdfPath = "pdf_path"
    }
}

struct MacReport: Identifiable, Hashable, Decodable {
    let id: String
    let companyId: String?
    let companyName: String?
    let reportType: String?
    let audience: String?
    let language: String?
    let status: String?
    let progress: Int?
    let stage: String?
    let error: String?
    let kind: String?
    let createdAt: String?
    let updatedAt: String?
    let downloadUrls: [String: String]?
    let previewUrls: [String: String]?
    let memoFiles: [MacMemoFile]?

    enum CodingKeys: String, CodingKey {
        case id, audience, language, status, progress, stage, error, kind
        case companyId = "company_id"
        case companyName = "company_name"
        case reportType = "report_type"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case downloadUrls = "download_urls"
        case previewUrls = "preview_urls"
        case memoFiles = "memo_files"
    }

    /// Human title — not "Investment Memo Latestage".
    var displayTitle: String {
        let raw = (reportType ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !raw.isEmpty { return raw }
        switch (kind ?? "").lowercased() {
        case "investment_memo_latestage": return "Investment memo"
        case "buffett_memo", "buffett-memo": return "Buffett memo"
        default:
            return (kind ?? "Research memo")
                .replacingOccurrences(of: "_", with: " ")
                .replacingOccurrences(of: "-", with: " ")
                .capitalized
        }
    }

    var isComplete: Bool {
        let s = (status ?? "").lowercased()
        return s.hasPrefix("complete")
    }

    var isFailed: Bool {
        (status ?? "").lowercased().contains("fail")
    }

    /// Openable on Mac: PDF preview and/or DOCX download (most desk memos are DOCX-only).
    var canOpen: Bool {
        !(previewUrls ?? [:]).isEmpty || !(downloadUrls ?? [:]).isEmpty || !(memoFiles ?? []).isEmpty
    }

    var statusLabel: String {
        let s = (status ?? "").lowercased()
        if s.hasPrefix("complete") { return "Complete" }
        if s.contains("fail") { return "Failed" }
        if s.contains("run") || !(stage ?? "").isEmpty { return stage ?? "Running" }
        return status?.capitalized ?? "—"
    }

    var statusTone: String { statusLabel }

    var timeAgo: String {
        guard let raw = updatedAt ?? createdAt, !raw.isEmpty else { return "" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = formatter.date(from: raw)
        if date == nil {
            formatter.formatOptions = [.withInternetDateTime]
            date = formatter.date(from: raw)
        }
        guard let d = date else {
            return String(raw.prefix(10))
        }
        let interval = Date().timeIntervalSince(d)
        if interval < 60 { return "just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        if interval < 604800 { return "\(Int(interval / 86400))d ago" }
        return String(raw.prefix(10))
    }

    var dateLabel: String {
        String((updatedAt ?? createdAt ?? "").prefix(10))
    }

    func documentPath(prefer language: String) -> (path: String, isPDF: Bool)? {
        if let urls = previewUrls {
            if let p = urls[language] ?? urls["en"] ?? urls["zh"] ?? urls.values.first {
                return (p, true)
            }
        }
        if let urls = downloadUrls {
            if let p = urls[language] ?? urls["en"] ?? urls["zh"] ?? urls.values.first {
                return (p, false)
            }
        }
        // Fallback: construct download URL when memo_files exist but maps omitted.
        if !(memoFiles ?? []).isEmpty {
            return ("/api/reports/\(id)/download?language=\(language)", false)
        }
        return nil
    }
}

struct MacAuthTokenResponse: Decodable {
    let token: String
    let email: String?
    let mustReset: Bool?

    enum CodingKeys: String, CodingKey {
        case token, email
        case mustReset = "must_reset"
    }
}

/// `GET /api/auth/me` — who the server thinks we are and what we may do.
struct MacSession: Decodable, Equatable {
    let email: String?
    let name: String?
    let auth: String?
    let role: String?
    let permissions: [String]
    let mustReset: Bool?

    enum CodingKeys: String, CodingKey {
        case email, name, auth, role, permissions
        case mustReset = "must_reset"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        email = try c.decodeIfPresent(String.self, forKey: .email)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        auth = try c.decodeIfPresent(String.self, forKey: .auth)
        role = try c.decodeIfPresent(String.self, forKey: .role)
        permissions = try c.decodeIfPresent([String].self, forKey: .permissions) ?? []
        mustReset = try c.decodeIfPresent(Bool.self, forKey: .mustReset)
    }

    var isAnonDev: Bool { auth == "anon_dev" }
    var isSharedToken: Bool { auth == "shared" }

    var displayName: String {
        if let name, !name.isEmpty { return name }
        if let email, !email.isEmpty { return email }
        if isAnonDev { return "Local dev" }
        if isSharedToken { return "Service token" }
        return "Signed in"
    }

    var roleLabel: String {
        (role ?? "guest").replacingOccurrences(of: "_", with: " ").capitalized
    }
}

struct MacAnnotationPayload: Decodable {
    let overlayPngBase64: String?
    let overlayUrl: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case overlayPngBase64 = "overlay_png_base64"
        case overlayUrl = "overlay_url"
        case updatedAt = "updated_at"
    }
}

// MARK: - Market & Chart Models

enum MacChartRange: String, CaseIterable, Identifiable {
    case d1 = "1D"
    case d5 = "5D"
    case m1 = "1M"
    case m6 = "6M"
    case y1 = "1Y"
    case max = "MAX"

    var id: String { rawValue }
}

struct MacChartPoint: Decodable, Identifiable, Hashable {
    var id: Int { t }
    let t: Int
    let close: Double?
    let volume: Double?

    var timestamp: Date {
        Date(timeIntervalSince1970: TimeInterval(t))
    }
}

struct MacChartPayload: Decodable {
    let ticker: String?
    let name: String?
    let exchange: String?
    let currency: String?
    let previousClose: Double?
    let points: [MacChartPoint]?

    enum CodingKeys: String, CodingKey {
        case ticker, name, exchange, currency, points
        case previousClose = "previous_close"
    }
}

/// Nasdaq "summary" block from `GET /api/quotes/{ticker}/workspace`. Every value is
/// a display string as the server sends it (e.g. "$1.2T", "$120.10 - $199.62").
struct MacQuoteSummary: Decodable {
    let exchange: String?
    let sector: String?
    let industry: String?
    let oneYearTarget: String?
    let dayRange: String?
    let volume: String?
    let avgVolume: String?
    let previousClose: String?
    let fiftyTwoWeek: String?
    let marketCap: String?
    let dividend: String?
    let yield: String?
    let beta: String?
    let bid: String?
    let ask: String?

    enum CodingKeys: String, CodingKey {
        case exchange, sector, industry, volume, dividend, yield, beta, bid, ask
        case oneYearTarget = "one_year_target"
        case dayRange = "day_range"
        case avgVolume = "avg_volume"
        case previousClose = "previous_close"
        case fiftyTwoWeek = "fifty_two_week"
        case marketCap = "market_cap"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func text(_ key: CodingKeys) -> String? {
            if let s = try? c.decodeIfPresent(String.self, forKey: key) { return s }
            if let d = try? c.decodeIfPresent(Double.self, forKey: key) { return String(d) }
            return nil
        }
        exchange = text(.exchange)
        sector = text(.sector)
        industry = text(.industry)
        oneYearTarget = text(.oneYearTarget)
        dayRange = text(.dayRange)
        volume = text(.volume)
        avgVolume = text(.avgVolume)
        previousClose = text(.previousClose)
        fiftyTwoWeek = text(.fiftyTwoWeek)
        marketCap = text(.marketCap)
        dividend = text(.dividend)
        yield = text(.yield)
        beta = text(.beta)
        bid = text(.bid)
        ask = text(.ask)
    }

    /// Numeric previous close when the string parses ("$123.45" → 123.45).
    var previousCloseValue: Double? {
        guard let raw = previousClose else { return nil }
        let cleaned = raw.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")
        return Double(cleaned.trimmingCharacters(in: .whitespaces))
    }
}

struct MacQuoteProfile: Decodable {
    let ticker: String?
    let name: String?
    let sector: String?
    let industry: String?
    let region: String?
    let website: String?
    let description: String?
}

struct MacQuoteWorkspace: Decodable {
    let summary: MacQuoteSummary?
    let profile: MacQuoteProfile?
}

// MARK: - Desk Preferences & Portfolio Sync

struct MacBookLot: Identifiable, Hashable, Codable {
    var id: String
    var ticker: String
    var shares: Double
    var costBasis: Double

    var totalCost: Double {
        shares * costBasis
    }

    func currentEquity(currentPrice: Double) -> Double {
        shares * currentPrice
    }

    func unrealizedGain(currentPrice: Double) -> Double {
        currentEquity(currentPrice: currentPrice) - totalCost
    }

    func gainPct(currentPrice: Double) -> Double {
        guard totalCost > 0 else { return 0 }
        return (unrealizedGain(currentPrice: currentPrice) / totalCost) * 100.0
    }
}

struct MacAlertRule: Identifiable, Hashable, Codable {
    var id: String
    var ticker: String
    var kind: String
    var threshold: Double
    var direction: String
    var enabled: Bool
}

// MARK: - Copilot & AI Models

enum MacCopilotPersona: String, CaseIterable, Identifiable {
    case warren = "warren"
    case growth = "growth"
    case macro = "macro"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .warren: return "Warren Buffett"
        case .growth: return "Growth Analyst"
        case .macro: return "Macro Strategist"
        }
    }

    var icon: String {
        switch self {
        case .warren: return "building.columns"
        case .growth: return "chart.line.uptrend.xyaxis"
        case .macro: return "globe.americas"
        }
    }

    var promptPrefix: String {
        switch self {
        case .warren:
            return "Adopt the perspective of Warren Buffett. Emphasize moat, capital allocation, intrinsic value, and margin of safety. "
        case .growth:
            return "Adopt the perspective of a Silicon Valley tech & growth equity research analyst. Focus on TAM, unit economics, NDR, and product velocity. "
        case .macro:
            return "Adopt the perspective of a global macro strategist. Focus on rates, liquidity, currency cycles, and geopolitical headwinds. "
        }
    }
}

struct MacCopilotMessage: Identifiable, Hashable {
    let id: String
    let role: Role
    var text: String
    var thinking: String?
    var sources: [String]?
    /// On-screen context the question was asked with ("Memo · page 4", "TSM").
    var contextLabel: String?
    let date: Date

    enum Role {
        case user
        case assistant
    }

    init(id: String = UUID().uuidString, role: Role, text: String, thinking: String? = nil, sources: [String]? = nil, date: Date = Date()) {
        self.id = id
        self.role = role
        self.text = text
        self.thinking = thinking
        self.sources = sources
        self.date = date
    }
}

// MARK: - Report Generation Request

struct MacGenerateReportRequest: Encodable {
    let companyId: String
    let reportType: String
    let language: String
    let audience: String

    enum CodingKeys: String, CodingKey {
        case language, audience
        case companyId = "company_id"
        case reportType = "report_type"
    }
}

// MARK: - Autocomplete & Active Jobs

struct MacAutocompleteHit: Identifiable, Hashable, Decodable {
    var id: String { ticker ?? name ?? UUID().uuidString }
    let ticker: String?
    let name: String?
    let sector: String?
    let industry: String?
    let exchange: String?
    let source: String?
    let status: String?
    let companyType: String?

    enum CodingKeys: String, CodingKey {
        case ticker, name, sector, industry, exchange, source, status
        case companyType = "company_type"
    }

    var displayTitle: String {
        name ?? ticker ?? "Unknown"
    }

    var displaySubtitle: String {
        [ticker, sector ?? industry, source]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

/// One row of `GET /api/jobs/active`. Rows carry no stable `id` for memo runs, so the
/// identity falls back to the report id / run id.
struct MacActiveJob: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let title: String?
    let subtitle: String?
    let progress: Int?
    let lastMessage: String?
    let reportId: String?
    let companyId: String?
    let streamUrl: String?
    let logUrl: String?
    let startedAt: String?
    let lastEventAt: String?
    let elapsedMs: Double?
    let latestStage: String?
    let latestAction: String?
    let error: String?
    let reportReady: Bool
    let index: Int?
    let totalCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, subtitle, progress, error, index
        case lastMessage = "last_message"
        case reportId = "report_id"
        case companyId = "company_id"
        case runId = "run_id"
        case streamUrl = "stream_url"
        case logUrl = "log_url"
        case startedAt = "started_at"
        case lastEventAt = "last_event_at"
        case elapsedMs = "elapsed_ms"
        case latestStage = "latest_stage"
        case latestAction = "latest_action"
        case reportReady = "report_ready"
        case totalCount = "total_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = try c.decodeIfPresent(String.self, forKey: .kind)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        progress = (try? c.decodeIfPresent(Int.self, forKey: .progress))
            ?? (try? c.decodeIfPresent(Double.self, forKey: .progress)).flatMap { Int($0) }
        lastMessage = try c.decodeIfPresent(String.self, forKey: .lastMessage)
        reportId = try c.decodeIfPresent(String.self, forKey: .reportId)
        companyId = try c.decodeIfPresent(String.self, forKey: .companyId)
        streamUrl = try c.decodeIfPresent(String.self, forKey: .streamUrl)
        logUrl = try c.decodeIfPresent(String.self, forKey: .logUrl)
        startedAt = try c.decodeIfPresent(String.self, forKey: .startedAt)
        lastEventAt = try c.decodeIfPresent(String.self, forKey: .lastEventAt)
        elapsedMs = try? c.decodeIfPresent(Double.self, forKey: .elapsedMs)
        latestStage = try c.decodeIfPresent(String.self, forKey: .latestStage)
        latestAction = try c.decodeIfPresent(String.self, forKey: .latestAction)
        error = try c.decodeIfPresent(String.self, forKey: .error)
        reportReady = (try? c.decodeIfPresent(Bool.self, forKey: .reportReady)) ?? false
        index = try? c.decodeIfPresent(Int.self, forKey: .index)
        totalCount = try? c.decodeIfPresent(Int.self, forKey: .totalCount)
        let explicit = try c.decodeIfPresent(String.self, forKey: .id)
        let runId = try c.decodeIfPresent(String.self, forKey: .runId)
        id = explicit
            ?? reportId
            ?? runId
            ?? [kind ?? "job", title ?? "", subtitle ?? "", startedAt ?? ""].joined(separator: "|")
    }

    var isMemo: Bool { (kind ?? "").lowercased() == "memo" }

    var stageText: String {
        latestStage ?? lastMessage ?? subtitle ?? "Running…"
    }

    var elapsedText: String {
        if let ms = elapsedMs, ms > 0 { return MacTimeFormat.duration(seconds: ms / 1000) }
        if let start = MacTimeFormat.parse(startedAt) {
            return MacTimeFormat.duration(seconds: Date().timeIntervalSince(start))
        }
        return ""
    }
}

/// One row of `GET /api/jobs/history` (terminal-event ledger, memo rows enriched).
struct MacJobHistoryRow: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let title: String?
    let subtitle: String?
    let terminalType: String?
    let error: String?
    let startedAt: String?
    let finishedAt: String?
    let elapsedMs: Double?
    let claudeCostUsd: Double?
    let reportReady: Bool
    let reportId: String?
    let companyId: String?
    let status: String?
    let logUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, subtitle, error, status
        case terminalType = "terminal_type"
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case elapsedMs = "elapsed_ms"
        case claudeCostUsd = "claude_cost_usd"
        case reportReady = "report_ready"
        case reportId = "report_id"
        case companyId = "company_id"
        case logUrl = "log_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        kind = try c.decodeIfPresent(String.self, forKey: .kind)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        terminalType = try c.decodeIfPresent(String.self, forKey: .terminalType)
        error = try c.decodeIfPresent(String.self, forKey: .error)
        startedAt = try c.decodeIfPresent(String.self, forKey: .startedAt)
        finishedAt = try c.decodeIfPresent(String.self, forKey: .finishedAt)
        elapsedMs = try? c.decodeIfPresent(Double.self, forKey: .elapsedMs)
        claudeCostUsd = try? c.decodeIfPresent(Double.self, forKey: .claudeCostUsd)
        reportReady = (try? c.decodeIfPresent(Bool.self, forKey: .reportReady)) ?? false
        reportId = try c.decodeIfPresent(String.self, forKey: .reportId)
        companyId = try c.decodeIfPresent(String.self, forKey: .companyId)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        logUrl = try c.decodeIfPresent(String.self, forKey: .logUrl)
    }

    var isMemo: Bool { (kind ?? "").lowercased() == "memo" }
    var failed: Bool {
        (terminalType ?? "").lowercased() == "error" || (status ?? "").lowercased().hasPrefix("failed")
    }
    var succeeded: Bool {
        !failed && ((terminalType ?? "").lowercased() == "done" || (status ?? "").lowercased().hasPrefix("complete"))
    }
    var canResume: Bool {
        guard isMemo else { return false }
        let s = (status ?? "").lowercased()
        return s.hasPrefix("failed") && s != "failed_scope_check" || s == "complete_with_warnings"
    }
    var canDismiss: Bool {
        guard isMemo else { return false }
        let s = (status ?? "").lowercased()
        return s.hasPrefix("failed") || s == "awaiting_studio"
    }
    var outcomeLabel: String {
        if failed { return "Failed" }
        if succeeded { return "Done" }
        return (terminalType ?? status ?? "Finished").capitalized
    }
}

/// Fired price alert from `GET /api/alerts/events` / `POST /api/alerts/check`.
struct MacAlertEvent: Identifiable, Hashable, Decodable {
    let id: String
    let ruleId: String?
    let ticker: String?
    let kind: String?
    let direction: String?
    let threshold: Double?
    let lastPrice: Double?
    let message: String?
    let firedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, ticker, kind, direction, threshold, message
        case ruleId = "rule_id"
        case lastPrice = "last_price"
        case firedAt = "fired_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        ruleId = try? c.decodeIfPresent(String.self, forKey: .ruleId)
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        kind = try? c.decodeIfPresent(String.self, forKey: .kind)
        direction = try? c.decodeIfPresent(String.self, forKey: .direction)
        threshold = try? c.decodeIfPresent(Double.self, forKey: .threshold)
        lastPrice = try? c.decodeIfPresent(Double.self, forKey: .lastPrice)
        message = try? c.decodeIfPresent(String.self, forKey: .message)
        firedAt = try? c.decodeIfPresent(String.self, forKey: .firedAt)
    }

    var headline: String {
        if let message, !message.isEmpty { return message }
        let t = ticker ?? "?"
        if let threshold, let direction {
            return "\(t) \(direction) \(String(format: "%.2f", threshold))"
        }
        return "\(t) alert"
    }
}

struct MacAlertCheckResult: Decodable {
    let checked: Int?
    let fired: [MacAlertEvent]?
}

/// `GET /api/quotes/search` match (listed symbol lookup).
struct MacSymbolMatch: Identifiable, Hashable, Decodable {
    var id: String { symbol }
    let symbol: String
    let name: String?
    let exchange: String?
    let type: String?

    enum CodingKeys: String, CodingKey {
        case symbol, ticker, name, exchange, type
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let s = (try? c.decodeIfPresent(String.self, forKey: .symbol))
            ?? (try? c.decodeIfPresent(String.self, forKey: .ticker))
            ?? ""
        symbol = s.uppercased()
        name = try? c.decodeIfPresent(String.self, forKey: .name)
        exchange = try? c.decodeIfPresent(String.self, forKey: .exchange)
        type = try? c.decodeIfPresent(String.self, forKey: .type)
    }
}

/// A deep-search (Claude) company match — also the body of `POST /api/companies/select`.
struct MacCompanyMatch: Identifiable, Hashable, Codable {
    var id: String { (ticker ?? "") + "|" + name }
    let name: String
    let ticker: String?
    let description: String?
    let sector: String?
    let industry: String?
    let exchange: String?
    let status: String?
    let companyType: String?

    enum CodingKeys: String, CodingKey {
        case name, ticker, description, sector, industry, exchange, status
        case companyType = "company_type"
    }

    init(name: String, ticker: String? = nil, description: String? = nil, sector: String? = nil,
         industry: String? = nil, exchange: String? = nil, status: String? = nil, companyType: String? = nil) {
        self.name = name
        self.ticker = ticker
        self.description = description
        self.sector = sector
        self.industry = industry
        self.exchange = exchange
        self.status = status
        self.companyType = companyType
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? "Unknown"
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        description = try? c.decodeIfPresent(String.self, forKey: .description)
        sector = try? c.decodeIfPresent(String.self, forKey: .sector)
        industry = try? c.decodeIfPresent(String.self, forKey: .industry)
        exchange = try? c.decodeIfPresent(String.self, forKey: .exchange)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        companyType = try? c.decodeIfPresent(String.self, forKey: .companyType)
    }

    init(hit: MacAutocompleteHit) {
        self.init(
            name: hit.name ?? hit.ticker ?? "Unknown",
            ticker: hit.ticker,
            sector: hit.sector,
            industry: hit.industry,
            exchange: hit.exchange,
            status: hit.status,
            companyType: hit.companyType
        )
    }
}

struct MacDeepSearchStart: Decodable {
    let cached: Bool?
    let matches: [MacCompanyMatch]?
    let jobId: String?
    let streamUrl: String?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case cached, matches, status
        case jobId = "job_id"
        case streamUrl = "stream_url"
    }
}

struct MacSSEEvent: Sendable {
    let event: String?
    let data: String

    var json: [String: Any]? {
        guard let d = data.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any]
        else { return nil }
        return obj
    }
}

/// Value handed to the memo `WindowGroup` — one window per (report, language).
struct MacMemoWindowRequest: Codable, Hashable {
    let reportId: String
    let language: String
}

/// A memo file downloaded to a temp URL, ready for the reader.
struct MacLoadedMemo {
    let url: URL
    let isPDF: Bool
    let overlayData: Data?
    let title: String
    let report: MacReport
}

enum MacTimeFormat {
    static func parse(_ raw: String?) -> Date? {
        guard let raw, !raw.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: raw) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: raw)
    }

    static func duration(seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        if s < 60 { return "\(s)s" }
        if s < 3600 { return "\(s / 60)m \(s % 60)s" }
        return "\(s / 3600)h \((s % 3600) / 60)m"
    }

    static func relative(_ raw: String?) -> String {
        guard let d = parse(raw) else { return raw.map { String($0.prefix(16)) } ?? "" }
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f.localizedString(for: d, relativeTo: Date())
    }
}

// MARK: - Market Pulse Payload

struct MacMarketPulsePayload: Decodable {
    let periodId: String?
    let summary: Summary?
    let sections: Sections?

    struct Summary: Decodable {
        let topSignal: String?
        enum CodingKeys: String, CodingKey {
            case topSignal = "top_signal"
        }
    }

    struct Sections: Decodable {
        let marketRegime: MarketRegime?
        let rankedSignals: [RankedSignal]?

        enum CodingKeys: String, CodingKey {
            case marketRegime = "market_regime"
            case rankedSignals = "ranked_signals"
        }
    }

    struct MarketRegime: Decodable {
        let posture: String?
        let breadth: Breadth?

        /// Signal breadth as the server computes it (counts, not an A/D ratio).
        struct Breadth: Decodable {
            let positiveSignals: Int?
            let negativeSignals: Int?
            let neutralSignals: Int?
            enum CodingKeys: String, CodingKey {
                case positiveSignals = "positive_signals"
                case negativeSignals = "negative_signals"
                case neutralSignals = "neutral_signals"
            }

            var total: Int { (positiveSignals ?? 0) + (negativeSignals ?? 0) + (neutralSignals ?? 0) }
        }
    }

    struct RankedSignal: Identifiable, Hashable, Decodable {
        var id: String { signalId ?? signal ?? UUID().uuidString }
        let signalId: String?
        let signal: String?
        let direction: String?
        let confidence: Double?
        let relatedTickers: [String]?

        enum CodingKeys: String, CodingKey {
            case direction, confidence, signal
            case signalId = "signal_id"
            case relatedTickers = "related_tickers"
        }
    }

    enum CodingKeys: String, CodingKey {
        case summary, sections
        case periodId = "period_id"
    }
}

// MARK: - News Brief & AI Analysis

struct MacNewsBriefSource: Decodable, Hashable {
    let title: String?
    let url: String?
}

struct MacNewsBrief: Decodable {
    let key: String?
    let generatedAt: String?
    let headlineEn: String?
    let headlineZh: String?
    let whatHappenedEn: String?
    let whatHappenedZh: String?
    let whyItMattersEn: String?
    let whyItMattersZh: String?
    let contextEn: [String]?
    let contextZh: [String]?
    let watchNextEn: [String]?
    let watchNextZh: [String]?
    let confidence: String?
    let sources: [MacNewsBriefSource]?

    enum CodingKeys: String, CodingKey {
        case key, confidence, sources, headline, context
        case generatedAt = "generated_at"
        case headlineEn = "headline_en"
        case headlineZh = "headline_zh"
        case whatHappened = "what_happened"
        case whatHappenedEn = "what_happened_en"
        case whatHappenedZh = "what_happened_zh"
        case whyItMatters = "why_it_matters"
        case whyItMattersEn = "why_it_matters_en"
        case whyItMattersZh = "why_it_matters_zh"
        case contextEn = "context_en"
        case contextZh = "context_zh"
        case watchNext = "watch_next"
        case watchNextEn = "watch_next_en"
        case watchNextZh = "watch_next_zh"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        key = try box.decodeIfPresent(String.self, forKey: .key)
        generatedAt = try box.decodeIfPresent(String.self, forKey: .generatedAt)
        confidence = try box.decodeIfPresent(String.self, forKey: .confidence)
        sources = try box.decodeIfPresent([MacNewsBriefSource].self, forKey: .sources)
        let bareHeadline = try box.decodeIfPresent(String.self, forKey: .headline)
        headlineEn = try box.decodeIfPresent(String.self, forKey: .headlineEn) ?? bareHeadline
        headlineZh = try box.decodeIfPresent(String.self, forKey: .headlineZh)
        let bareWhat = try box.decodeIfPresent(String.self, forKey: .whatHappened)
        whatHappenedEn = try box.decodeIfPresent(String.self, forKey: .whatHappenedEn) ?? bareWhat
        whatHappenedZh = try box.decodeIfPresent(String.self, forKey: .whatHappenedZh)
        let bareWhy = try box.decodeIfPresent(String.self, forKey: .whyItMatters)
        whyItMattersEn = try box.decodeIfPresent(String.self, forKey: .whyItMattersEn) ?? bareWhy
        whyItMattersZh = try box.decodeIfPresent(String.self, forKey: .whyItMattersZh)
        let bareContext = try box.decodeIfPresent([String].self, forKey: .context)
        contextEn = try box.decodeIfPresent([String].self, forKey: .contextEn) ?? bareContext
        contextZh = try box.decodeIfPresent([String].self, forKey: .contextZh)
        let bareWatch = try box.decodeIfPresent([String].self, forKey: .watchNext)
        watchNextEn = try box.decodeIfPresent([String].self, forKey: .watchNextEn) ?? bareWatch
        watchNextZh = try box.decodeIfPresent([String].self, forKey: .watchNextZh)
    }

    func whatHappened(lang: String = "en") -> String {
        if lang == "zh", let zh = whatHappenedZh, !zh.isEmpty { return zh }
        return whatHappenedEn ?? ""
    }

    func whyItMatters(lang: String = "en") -> String {
        if lang == "zh", let zh = whyItMattersZh, !zh.isEmpty { return zh }
        return whyItMattersEn ?? ""
    }

    func contextBullets(lang: String = "en") -> [String] {
        if lang == "zh", let zh = contextZh, !zh.isEmpty { return zh }
        return contextEn ?? []
    }

    func watchNextBullets(lang: String = "en") -> [String] {
        if lang == "zh", let zh = watchNextZh, !zh.isEmpty { return zh }
        return watchNextEn ?? []
    }
}

