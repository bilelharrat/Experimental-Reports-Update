import Foundation

struct MacCompany: Identifiable, Hashable, Codable {
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
    let stars: Int
    let starsGrowthWeekly: String
    let forks: Int
    let weeklyDownloads: String?
    let commitCadence: String
    let inflectionSignal: String

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
    let employeeCountEstimate: String
    let engineeringPct: Int
    let gtmSalesPct: Int
    let operationsPct: Int
    let openRolesCount: Int
    let hiringVelocity: String

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

    enum CodingKeys: String, CodingKey {
        case founders
        case companyId = "company_id"
        case advisorsAndBoard = "advisors_and_board"
        case teamHeadcount = "team_headcount"
        case developerTraction = "developer_traction"
        case searchedAt = "searched_at"
        case isDeepAudited = "is_deep_audited"
    }
}

// MARK: - Deal Pipeline & Affinity-Grade CRM Models

struct MacDealPipeline: Hashable, Codable {
    let companyId: String
    var stage: String
    let stages: [String]
    var dealLead: String?
    var warmthScore: Int
    var introPath: String?
    var daysInStage: Int
    var lastTouchpoint: String?
    var nextStep: String?
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

struct MacQuoteSummary: Decodable {
    let ticker: String?
    let name: String?
    let price: Double?
    let change: Double?
    let changePct: Double?
    let volume: Double?
    let marketCap: Double?
    let peRatio: Double?
    let high52w: Double?
    let low52w: Double?
    let exchange: String?

    enum CodingKeys: String, CodingKey {
        case ticker, name, price, change, volume, exchange
        case changePct = "change_pct"
        case marketCap = "market_cap"
        case peRatio = "pe_ratio"
        case high52w = "high_52w"
        case low52w = "low_52w"
    }
}

struct MacQuoteProfile: Decodable {
    let name: String?
    let description: String?
    let sector: String?
    let industry: String?
    let employees: Int?
    let website: String?
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

struct MacActiveJob: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let title: String?
    let subtitle: String?
    let progress: Int?
    let lastMessage: String?
    let reportId: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, subtitle, progress
        case lastMessage = "last_message"
        case reportId = "report_id"
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

        struct Breadth: Decodable {
            let advanceDeclineRatio: Double?
            let pctAbove50d: Double?
            enum CodingKeys: String, CodingKey {
                case advanceDeclineRatio = "advance_decline_ratio"
                case pctAbove50d = "pct_above_50d"
            }
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

