import Foundation

struct MacCompany: Identifiable, Hashable, Codable {
    let id: String
    let name: String?
    let ticker: String?
    let companyType: String?
    let status: String?
    let sector: String?
    let industry: String?
    let website: String?
    let logoUrl: String?
    let logoDomain: String?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector, industry, website
        case companyType = "company_type"
        case logoUrl = "logo_url"
        case logoDomain = "logo_domain"
    }

    init(
        id: String,
        name: String? = nil,
        ticker: String? = nil,
        companyType: String? = nil,
        status: String? = nil,
        sector: String? = nil,
        industry: String? = nil,
        website: String? = nil,
        logoUrl: String? = nil,
        logoDomain: String? = nil
    ) {
        self.id = id
        self.name = name
        self.ticker = ticker
        self.companyType = companyType
        self.status = status
        self.sector = sector
        self.industry = industry
        self.website = website
        self.logoUrl = logoUrl
        self.logoDomain = logoDomain
    }

    var title: String { name ?? id }

    var subtitle: String {
        [ticker, sector ?? industry]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

// MARK: - Founder Pedigree & Developer Traction Models (Harmonic/Ampersand Grade)

struct MacFounderProfile: Identifiable, Hashable, Codable {
    var id: String { name }
    let name: String
    let role: String
    let bio: String?
    let pedigreeTags: [String]
    let education: String?
    let pastCompanies: [String]
    let priorExits: String?
    let patentsOrPapersCount: Int?
    let githubHandle: String?
    let linkedinUrl: String?

    enum CodingKeys: String, CodingKey {
        case name, role, bio, education
        case pedigreeTags = "pedigree_tags"
        case pastCompanies = "past_companies"
        case priorExits = "prior_exits"
        case patentsOrPapersCount = "patents_papers_count"
        case githubHandle = "github_handle"
        case linkedinUrl = "linkedin_url"
    }
}

struct MacDeveloperTraction: Hashable, Codable {
    let repoUrl: String?
    let stars: Int?
    let starsGrowthWeekly: String?
    let forks: Int?
    let weeklyDownloads: String?
    let commitCadence: String?
    let inflectionSignal: String?

    enum CodingKeys: String, CodingKey {
        case stars, forks
        case repoUrl = "repo_url"
        case starsGrowthWeekly = "stars_growth_weekly"
        case weeklyDownloads = "weekly_downloads"
        case commitCadence = "commit_cadence"
        case inflectionSignal = "inflection_signal"
    }
}

struct MacTeamHeadcount: Hashable, Codable {
    let employeeCountEstimate: String?
    let engineeringPct: Int?
    let gtmSalesPct: Int?
    let operationsPct: Int?
    let openRolesCount: Int?
    let hiringVelocity: String?

    enum CodingKeys: String, CodingKey {
        case employeeCountEstimate = "employee_count_estimate"
        case engineeringPct = "engineering_pct"
        case gtmSalesPct = "gtm_sales_pct"
        case operationsPct = "operations_pct"
        case openRolesCount = "open_roles_count"
        case hiringVelocity = "hiring_velocity"
    }
}

struct MacFounderDossier: Hashable, Codable {
    let companyId: String
    let founders: [MacFounderProfile]
    let advisorsAndBoard: [MacFounderProfile]?
    let teamHeadcount: MacTeamHeadcount?
    let developerTraction: MacDeveloperTraction?
    let searchedAt: String?
    let isDeepAudited: Bool?
    /// Which engine researched the team ("gemini") and with what model; nil
    /// when the dossier is only the company record.
    let engine: String?
    let model: String?
    let sources: [MacDossierSource]?
    /// Set when a research pass failed; the record-built people still show.
    let researchError: String?

    enum CodingKeys: String, CodingKey {
        case founders, engine, model, sources
        case companyId = "company_id"
        case advisorsAndBoard = "advisors_and_board"
        case teamHeadcount = "team_headcount"
        case developerTraction = "developer_traction"
        case searchedAt = "searched_at"
        case isDeepAudited = "is_deep_audited"
        case researchError = "research_error"
    }
}

struct MacDossierSource: Hashable, Codable {
    let title: String?
    let url: String?
}

// MARK: - Deal Pipeline & Affinity-Grade CRM Models

struct MacDealPipeline: Hashable, Codable {
    let companyId: String
    var stage: String
    let stages: [String]
    var dealLead: String?
    var warmthScore: Int?
    var introPath: String?
    var daysInStage: Int
    var lastTouchpoint: String?
    var nextStep: String?
    /// YYYY-MM-DD the next step is due by.
    var nextStepDue: String?
    /// Server-computed: a next step past its due date.
    var nextStepOverdue: Bool?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case stage, stages
        case companyId = "company_id"
        case dealLead = "deal_lead"
        case warmthScore = "warmth_score"
        case introPath = "intro_path"
        case daysInStage = "days_in_stage"
        case lastTouchpoint = "last_touchpoint"
        case nextStep = "next_step"
        case nextStepDue = "next_step_due"
        case nextStepOverdue = "next_step_overdue"
        case updatedAt = "updated_at"
    }
}



struct MacMemoFile: Codable, Hashable {
    let language: String?
    let path: String?
    let pdfPath: String?

    enum CodingKeys: String, CodingKey {
        case language, path
        case pdfPath = "pdf_path"
    }
}

struct MacReport: Identifiable, Hashable, Codable {
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
    let failurePhase: String?

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
        case failurePhase = "failure_phase"
    }

    var isCancelled: Bool {
        (failurePhase ?? "").lowercased() == "cancelled" || (status ?? "").lowercased() == "cancelled"
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
    let canvasWidth: Double?
    let canvasHeight: Double?

    enum CodingKeys: String, CodingKey {
        case overlayPngBase64 = "overlay_png_base64"
        case overlayUrl = "overlay_url"
        case updatedAt = "updated_at"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        overlayPngBase64 = try? c.decodeIfPresent(String.self, forKey: .overlayPngBase64)
        overlayUrl = try? c.decodeIfPresent(String.self, forKey: .overlayUrl)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
        canvasWidth = try? c.decodeIfPresent(Double.self, forKey: .canvasWidth)
        canvasHeight = try? c.decodeIfPresent(Double.self, forKey: .canvasHeight)
    }

    var canvasSize: CGSize? {
        guard let canvasWidth, let canvasHeight, canvasWidth > 0, canvasHeight > 0 else { return nil }
        return CGSize(width: canvasWidth, height: canvasHeight)
    }
}

// MARK: - Market & Chart Models

enum MacChartRange: String, CaseIterable, Identifiable {
    case d1 = "1D"
    case d5 = "5D"
    case m1 = "1M"
    case m6 = "6M"
    case ytd = "YTD"
    case y1 = "1Y"
    case y5 = "5Y"
    case max = "MAX"

    var id: String { rawValue }

    var apiValue: String {
        switch self {
        case .d1: return "1d"
        case .d5: return "5d"
        case .m1: return "1mo"
        case .m6: return "6mo"
        case .ytd: return "ytd"
        case .y1: return "1y"
        case .y5: return "5y"
        case .max: return "max"
        }
    }
}

struct MacChartPoint: Decodable, Identifiable, Hashable {
    var id: Int { t }
    let t: Int
    let close: Double?
    var open: Double? = nil
    var high: Double? = nil
    var low: Double? = nil
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
    var lastPrice: Double? = nil
    var change: Double? = nil
    var changePct: Double? = nil
    var open: Double? = nil
    var high: Double? = nil
    var low: Double? = nil
    var volume: Double? = nil
    var avgVolume: Double? = nil
    var marketCap: Double? = nil
    var peRatio: Double? = nil
    var eps: Double? = nil
    var beta: Double? = nil
    var dividendYield: Double? = nil
    var fiftyTwoWeekHigh: Double? = nil
    var fiftyTwoWeekLow: Double? = nil
    var asOf: String? = nil

    enum CodingKeys: String, CodingKey {
        case ticker, name, exchange, currency, points, open, high, low, volume, eps, beta, change
        case previousClose = "previous_close"
        case lastPrice = "last_price"
        case changePct = "change_pct_1d"
        case avgVolume = "avg_volume"
        case marketCap = "market_cap"
        case peRatio = "pe_ratio"
        case dividendYield = "dividend_yield"
        case fiftyTwoWeekHigh = "fifty_two_week_high"
        case fiftyTwoWeekLow = "fifty_two_week_low"
        case asOf = "as_of"
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
    var exDividend: String? = nil
    var alpha: String? = nil
    var aum: String? = nil
    var expenseRatio: String? = nil

    enum CodingKeys: String, CodingKey {
        case exchange, sector, industry, volume, dividend, yield, beta, bid, ask, alpha, aum
        case exDividend = "ex_dividend"
        case expenseRatio = "expense_ratio"
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
        exDividend = text(.exDividend)
        alpha = text(.alpha)
        aum = text(.aum)
        expenseRatio = text(.expenseRatio)
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
    var financials: MacQuoteFinancials? = nil
    var analysis: MacQuoteAnalysis? = nil
    var holders: MacQuoteHolders? = nil
    var insiders: MacQuoteInsiders? = nil
    var options: MacQuoteOptions? = nil
    var earnings: MacQuoteEarnings? = nil

    enum CodingKeys: String, CodingKey {
        case summary, profile, financials, analysis, holders, insiders, options, earnings
    }

    init(from decoder: Decoder) throws {
        // Each block decodes on its own so one malformed section never blanks the workspace.
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = try? c.decodeIfPresent(MacQuoteSummary.self, forKey: .summary)
        profile = try? c.decodeIfPresent(MacQuoteProfile.self, forKey: .profile)
        financials = try? c.decodeIfPresent(MacQuoteFinancials.self, forKey: .financials)
        analysis = try? c.decodeIfPresent(MacQuoteAnalysis.self, forKey: .analysis)
        holders = try? c.decodeIfPresent(MacQuoteHolders.self, forKey: .holders)
        insiders = try? c.decodeIfPresent(MacQuoteInsiders.self, forKey: .insiders)
        options = try? c.decodeIfPresent(MacQuoteOptions.self, forKey: .options)
        earnings = try? c.decodeIfPresent(MacQuoteEarnings.self, forKey: .earnings)
    }
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

    /// First name used in prompts and placeholders ("Ask Warren about TSM…").
    var shortName: String {
        switch self {
        case .warren: return "Warren"
        case .growth: return "the growth analyst"
        case .macro: return "the macro strategist"
        }
    }

    /// One line on how this lens reads a company, shown wherever the lens is picked.
    var tagline: String {
        switch self {
        case .warren: return "Moat, management, intrinsic value and margin of safety"
        case .growth: return "Market size, unit economics, retention and product velocity"
        case .macro: return "Rates, liquidity, currencies and geopolitics"
        }
    }

    /// Starter questions for the empty chat, written about the company on screen.
    func starters(company: String) -> [String] {
        switch self {
        case .warren:
            return [
                "Does \(company) have a durable moat? What could erode it?",
                "Is management allocating capital well at \(company)?",
                "What is \(company) worth, and is there a margin of safety at today's price?",
                "Would you own \(company) for ten years? Why or why not?"
            ]
        case .growth:
            return [
                "How big is the real market for \(company), and how much can it win?",
                "Are \(company)'s unit economics improving or getting worse?",
                "What are the top growth drivers and headwinds for \(company)?",
                "Which metric would tell us early that \(company)'s growth is stalling?"
            ]
        case .macro:
            return [
                "How exposed is \(company) to interest rates and liquidity?",
                "What currency and geopolitical risks does \(company) carry?",
                "Where are we in the cycle, and what does that mean for \(company)?",
                "Which macro scenario hurts \(company) the most?"
            ]
        }
    }

    /// Short follow-ups offered under the latest answer.
    static let followUps = [
        "Summarize that in three bullets",
        "What would change your mind?",
        "What's the biggest risk here?",
        "What evidence is this based on?"
    ]

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
    /// Lens that produced an assistant answer, so switching lenses keeps old answers labeled.
    var persona: MacCopilotPersona?
    /// The answer failed; `text` holds the reason and the bubble offers a retry.
    var isError = false
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
    var id: String { "\(source ?? "")|\(companyId ?? ticker ?? "")|\(name ?? "")" }
    let companyId: String?
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
        case companyId = "id"
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

/// `latest_action` on an active job: an object from the server, or a plain string on older builds.
struct MacJobAction: Hashable, Decodable {
    let action: String?
    let tool: String?
    let preview: String?
    let text: String?
    let error: String?
    let isError: Bool?
    let apiErrorStatus: Int?
    let ts: String?

    enum CodingKeys: String, CodingKey {
        case action, tool, preview, text, error, ts
        case isError = "is_error"
        case apiErrorStatus = "api_error_status"
    }

    init(action: String? = nil, tool: String? = nil, preview: String? = nil, text: String? = nil, error: String? = nil, isError: Bool? = nil, apiErrorStatus: Int? = nil, ts: String? = nil) {
        self.action = action
        self.tool = tool
        self.preview = preview
        self.text = text
        self.error = error
        self.isError = isError
        self.apiErrorStatus = apiErrorStatus
        self.ts = ts
    }

    init(from decoder: Decoder) throws {
        if let single = try? decoder.singleValueContainer(), let string = try? single.decode(String.self) {
            self.init(text: string)
            return
        }
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            action: try? c.decodeIfPresent(String.self, forKey: .action),
            tool: try? c.decodeIfPresent(String.self, forKey: .tool),
            preview: try? c.decodeIfPresent(String.self, forKey: .preview),
            text: try? c.decodeIfPresent(String.self, forKey: .text),
            error: try? c.decodeIfPresent(String.self, forKey: .error),
            isError: try? c.decodeIfPresent(Bool.self, forKey: .isError),
            apiErrorStatus: (try? c.decodeIfPresent(Int.self, forKey: .apiErrorStatus))
                ?? (try? c.decodeIfPresent(Double.self, forKey: .apiErrorStatus)).flatMap { Int($0) },
            ts: try? c.decodeIfPresent(String.self, forKey: .ts)
        )
    }

    var summary: String? {
        let candidates = [text, preview, tool.map { "\(action ?? "tool") \($0)" }, action, error]
        return candidates.compactMap { $0 }.first { !$0.isEmpty }
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
    let latestAction: MacJobAction?
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
        kind = try? c.decodeIfPresent(String.self, forKey: .kind)
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        subtitle = try? c.decodeIfPresent(String.self, forKey: .subtitle)
        progress = (try? c.decodeIfPresent(Int.self, forKey: .progress))
            ?? (try? c.decodeIfPresent(Double.self, forKey: .progress)).flatMap { Int($0) }
        lastMessage = try? c.decodeIfPresent(String.self, forKey: .lastMessage)
        reportId = try? c.decodeIfPresent(String.self, forKey: .reportId)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        streamUrl = try? c.decodeIfPresent(String.self, forKey: .streamUrl)
        logUrl = try? c.decodeIfPresent(String.self, forKey: .logUrl)
        startedAt = try? c.decodeIfPresent(String.self, forKey: .startedAt)
        lastEventAt = try? c.decodeIfPresent(String.self, forKey: .lastEventAt)
        elapsedMs = try? c.decodeIfPresent(Double.self, forKey: .elapsedMs)
        latestStage = try? c.decodeIfPresent(String.self, forKey: .latestStage)
        latestAction = try? c.decodeIfPresent(MacJobAction.self, forKey: .latestAction)
        error = try? c.decodeIfPresent(String.self, forKey: .error)
        reportReady = (try? c.decodeIfPresent(Bool.self, forKey: .reportReady)) ?? false
        index = try? c.decodeIfPresent(Int.self, forKey: .index)
        totalCount = try? c.decodeIfPresent(Int.self, forKey: .totalCount)
        let explicit = try? c.decodeIfPresent(String.self, forKey: .id)
        let runId = try? c.decodeIfPresent(String.self, forKey: .runId)
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
    var overlayCanvasSize: CGSize? = nil
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

// MARK: - Memo Studio Editor & Customization Models

struct MacReportCustomizerConfig: Hashable, Codable {
    var reportType: String = "Investment Report (Auto)"
    var audience: String = "Internal"
    var language: String = "en"
    var generationMode: String = "studio_review" // "one_click" or "studio_review"
    var reportMode: String = "full" // "full" or "compact"
    var quality: String = "best" // "best", "balanced", "economy"
    var customPrompt: String = ""
    var focusPillars: [String] = []
    var companyTypeLens: String = "auto"
    var selectedDocumentIds: [String] = []
}

struct MacMemoEditorSourceRef: Identifiable, Hashable, Codable {
    var id: String { title + (origin ?? "") + (url ?? "") }
    let title: String
    let origin: String?
    let url: String?
    let file: String?
    let capturedAt: String?
    let publishedAt: String?
    let language: String?
    let sourceClass: String?
    let confidence: String?

    enum CodingKeys: String, CodingKey {
        case title, origin, url, file, language, confidence
        case capturedAt = "captured_at"
        case publishedAt = "published_at"
        case sourceClass = "source_class"
    }
}

struct MacMemoEditorBullet: Identifiable, Hashable, Codable {
    let id: String
    var text: String
    var sourceClass: String?
    var sourceRefs: [MacMemoEditorSourceRef]?

    enum CodingKeys: String, CodingKey {
        case id, text
        case sourceClass = "source_class"
        case sourceRefs = "source_refs"
    }
    init(id: String = UUID().uuidString, text: String, sourceClass: String? = nil, sourceRefs: [MacMemoEditorSourceRef]? = nil) {
        self.id = id
        self.text = text
        self.sourceClass = sourceClass
        self.sourceRefs = sourceRefs
    }
}

struct MacMemoEditorCard: Identifiable, Hashable, Codable {
    let id: String
    var title: String
    var category: String?
    var severity: String?
    var likelihood: String?
    var rating: String?
    var confidence: String?
    var included: Bool?
    var expanded: Bool?
    var sourceClass: String?
    var bullets: [MacMemoEditorBullet]
    var sourceRefs: [MacMemoEditorSourceRef]?
    /// Built from the company record, not researched: the server marks the
    /// template cards an un-investigated company starts with, and clears the
    /// mark when someone writes into the card or an investigation replaces it.
    var placeholder: Bool = false

    init(
        id: String = UUID().uuidString,
        title: String,
        category: String? = nil,
        severity: String? = nil,
        likelihood: String? = nil,
        rating: String? = nil,
        confidence: String? = nil,
        included: Bool? = true,
        expanded: Bool? = false,
        sourceClass: String? = nil,
        bullets: [MacMemoEditorBullet] = [],
        sourceRefs: [MacMemoEditorSourceRef]? = nil
    ) {
        self.id = id
        self.title = title
        self.category = category
        self.severity = severity
        self.likelihood = likelihood
        self.rating = rating
        self.confidence = confidence
        self.included = included
        self.expanded = expanded
        self.sourceClass = sourceClass
        self.bullets = bullets
        self.sourceRefs = sourceRefs
    }

    enum CodingKeys: String, CodingKey {
        case id, title, category, severity, likelihood, rating, confidence, included, expanded, bullets, placeholder
        case sourceClass = "source_class"
        case sourceRefs = "source_refs"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        category = try c.decodeIfPresent(String.self, forKey: .category)
        severity = try c.decodeIfPresent(String.self, forKey: .severity)
        likelihood = try c.decodeIfPresent(String.self, forKey: .likelihood)
        rating = try c.decodeIfPresent(String.self, forKey: .rating)
        confidence = try c.decodeIfPresent(String.self, forKey: .confidence)
        included = try c.decodeIfPresent(Bool.self, forKey: .included)
        expanded = try c.decodeIfPresent(Bool.self, forKey: .expanded)
        sourceClass = try c.decodeIfPresent(String.self, forKey: .sourceClass)
        bullets = (try c.decodeIfPresent([MacMemoEditorBullet].self, forKey: .bullets)) ?? []
        sourceRefs = try c.decodeIfPresent([MacMemoEditorSourceRef].self, forKey: .sourceRefs)
        placeholder = (try? c.decodeIfPresent(Bool.self, forKey: .placeholder)) ?? false
    }

    var isCardIncluded: Bool { included ?? true }
}

struct MacMemoEditorSectionCards: Hashable, Codable {
    let id: String
    let title: String
    let status: String?
    var cards: [MacMemoEditorCard]
}

struct MacMemoEditorExecutiveSummary: Hashable, Codable {
    let id: String
    let title: String
    let status: String?
    let body: String?
    let recommendation: String?
    let round: String?
    let preMoney: String?
    let checkSize: String?
    let targetOwnership: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, body, recommendation, round
        case preMoney = "pre_money"
        case checkSize = "check_size"
        case targetOwnership = "target_ownership"
    }
}

struct MacMemoEditorConclusion: Hashable, Codable {
    let id: String
    let title: String
    let status: String?
    let recommendation: String?
    let valuationTarget: String?
    let keyCatalysts: [String]?

    enum CodingKeys: String, CodingKey {
        case id, title, status, recommendation
        case valuationTarget = "valuation_target"
        case keyCatalysts = "key_catalysts"
    }
}

struct MacMemoEditorAppendixBlock: Identifiable, Hashable, Codable {
    let id: String
    let title: String
    let status: String?
    var expanded: Bool?
    let facts: [String]
    let sourceClass: String?
    let sourceRefs: [MacMemoEditorSourceRef]?

    enum CodingKeys: String, CodingKey {
        case id, title, status, expanded, facts
        case sourceClass = "source_class"
        case sourceRefs = "source_refs"
    }
}

struct MacMemoEditorAppendix: Hashable, Codable {
    let id: String
    let title: String
    let status: String?
    var blocks: [MacMemoEditorAppendixBlock]
}

struct MacMemoEditorSections: Hashable, Codable {
    var executiveSummary: MacMemoEditorExecutiveSummary?
    var investmentThesis: MacMemoEditorSectionCards?
    var risksMitigations: MacMemoEditorSectionCards?
    var conclusion: MacMemoEditorConclusion?
    var appendix: MacMemoEditorAppendix?

    enum CodingKeys: String, CodingKey {
        case executiveSummary = "executive_summary"
        case investmentThesis = "investment_thesis"
        case risksMitigations = "risks_mitigations"
        case conclusion, appendix
    }
}

struct MacMemoEditorState: Identifiable, Hashable, Codable {
    var id: String { companyId }
    let schemaVersion: Int?
    let companyId: String
    let companyName: String?
    let version: Int?
    let versionId: String?
    let revision: Int?
    let revisionId: String?
    let status: String?
    let createdAt: String?
    let updatedAt: String?
    var sections: MacMemoEditorSections
    /// Set once an investigation has seeded the cards; nil means everything
    /// in the editor is still the company-record template or hand-written.
    let agentRun: AgentRun?

    struct AgentRun: Hashable, Codable {
        let mode: String?
        let seededAt: String?
        enum CodingKeys: String, CodingKey {
            case mode
            case seededAt = "seeded_at"
        }
    }

    var templateCardCount: Int {
        (sections.investmentThesis?.cards ?? []).filter(\.placeholder).count
            + (sections.risksMitigations?.cards ?? []).filter(\.placeholder).count
    }

    enum CodingKeys: String, CodingKey {
        case version, revision, status, sections
        case agentRun = "agent_run"
        case schemaVersion = "schema_version"
        case companyId = "company_id"
        case companyName = "company_name"
        case versionId = "version_id"
        case revisionId = "revision_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

