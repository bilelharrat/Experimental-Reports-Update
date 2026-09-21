import Foundation

// MARK: - Company & Organization

public struct MacCompany: Identifiable, Hashable, Codable {
    public let id: String
    public let name: String?
    public let ticker: String?
    public let companyType: String?
    public let status: String?
    public let sector: String?
    public let industry: String?
    public let website: String?
    public let logoUrl: String?
    public let logoDomain: String?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector, industry, website
        case companyType = "company_type"
        case logoUrl = "logo_url"
        case logoDomain = "logo_domain"
    }

    public init(
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

    public var title: String { name ?? id }

    public var subtitle: String {
        [ticker, sector ?? industry]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

// MARK: - Founder Pedigree & Developer Traction

public struct MacFounderProfile: Identifiable, Hashable, Codable {
    public var id: String { name }
    public let name: String
    public let role: String
    public let bio: String?
    public let pedigreeTags: [String]
    public let education: String?
    public let pastCompanies: [String]
    public let priorExits: String?
    public let patentsOrPapersCount: Int?
    public let githubHandle: String?
    public let linkedinUrl: String?
    public let profileUrl: String?

    enum CodingKeys: String, CodingKey {
        case name, role, bio, education
        case pedigreeTags = "pedigree_tags"
        case pastCompanies = "past_companies"
        case priorExits = "prior_exits"
        case patentsOrPapersCount = "patents_papers_count"
        case githubHandle = "github_handle"
        case linkedinUrl = "linkedin_url"
        case profileUrl = "profile_url"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? "Founder"
        role = (try? c.decodeIfPresent(String.self, forKey: .role)) ?? "Founder"
        bio = try? c.decodeIfPresent(String.self, forKey: .bio)
        pedigreeTags = (try? c.decodeIfPresent([String].self, forKey: .pedigreeTags)) ?? []
        education = try? c.decodeIfPresent(String.self, forKey: .education)
        pastCompanies = (try? c.decodeIfPresent([String].self, forKey: .pastCompanies)) ?? []
        priorExits = try? c.decodeIfPresent(String.self, forKey: .priorExits)
        patentsOrPapersCount = try? c.decodeIfPresent(Int.self, forKey: .patentsOrPapersCount)
        githubHandle = try? c.decodeIfPresent(String.self, forKey: .githubHandle)
        linkedinUrl = try? c.decodeIfPresent(String.self, forKey: .linkedinUrl)
        profileUrl = try? c.decodeIfPresent(String.self, forKey: .profileUrl)
    }
}

public struct MacDeveloperTraction: Hashable, Codable {
    public let repoUrl: String?
    public let stars: Int?
    public let starsGrowthWeekly: String?
    public let forks: Int?
    public let weeklyDownloads: String?
    public let commitCadence: String?
    public let inflectionSignal: String?

    enum CodingKeys: String, CodingKey {
        case stars, forks
        case repoUrl = "repo_url"
        case starsGrowthWeekly = "stars_growth_weekly"
        case weeklyDownloads = "weekly_downloads"
        case commitCadence = "commit_cadence"
        case inflectionSignal = "inflection_signal"
    }
}

public struct MacTeamHeadcount: Hashable, Codable {
    public let employeeCountEstimate: String?
    public let engineeringPct: Int?
    public let gtmSalesPct: Int?
    public let operationsPct: Int?
    public let openRolesCount: Int?
    public let hiringVelocity: String?

    enum CodingKeys: String, CodingKey {
        case employeeCountEstimate = "employee_count_estimate"
        case engineeringPct = "engineering_pct"
        case gtmSalesPct = "gtm_sales_pct"
        case operationsPct = "operations_pct"
        case openRolesCount = "open_roles_count"
        case hiringVelocity = "hiring_velocity"
    }
}

public struct MacFounderDossier: Hashable, Codable {
    public let companyId: String
    public let founders: [MacFounderProfile]
    public let advisorsAndBoard: [MacFounderProfile]?
    public let teamHeadcount: MacTeamHeadcount?
    public let developerTraction: MacDeveloperTraction?
    public let searchedAt: String?
    public let isDeepAudited: Bool?

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

public struct MacFounderRadar: Decodable {
    public let companyId: String?
    public let generatedAt: String?
    public let founders: [MacFounderProfile]
    public let advisorsAndBoard: [MacFounderProfile]?
    public let developerTraction: MacDeveloperTraction?
    public let teamHeadcount: MacTeamHeadcount?
    /// Which engine researched the team ("gemini") and with what model; nil
    /// when the dossier is only the company record.
    public let engine: String?
    public let model: String?
    public let sourceCount: Int
    /// Set when a research pass failed; the record-built people still show.
    public let researchError: String?

    enum CodingKeys: String, CodingKey {
        case founders, engine, model, sources
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case advisorsAndBoard = "advisors_and_board"
        case developerTraction = "developer_traction"
        case teamHeadcount = "team_headcount"
        case researchError = "research_error"
    }

    private struct SourceRef: Decodable {
        let url: String?
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        founders = (try? c.decodeIfPresent([MacFounderProfile].self, forKey: .founders)) ?? []
        advisorsAndBoard = try? c.decodeIfPresent([MacFounderProfile].self, forKey: .advisorsAndBoard)
        developerTraction = try? c.decodeIfPresent(MacDeveloperTraction.self, forKey: .developerTraction)
        teamHeadcount = try? c.decodeIfPresent(MacTeamHeadcount.self, forKey: .teamHeadcount)
        engine = try? c.decodeIfPresent(String.self, forKey: .engine)
        model = try? c.decodeIfPresent(String.self, forKey: .model)
        sourceCount = ((try? c.decodeIfPresent([SourceRef].self, forKey: .sources)) ?? nil)?.count ?? 0
        researchError = try? c.decodeIfPresent(String.self, forKey: .researchError)
    }
}

// MARK: - Deal Pipeline

public struct MacDealPipeline: Hashable, Codable {
    public let companyId: String
    public var stage: String
    public let stages: [String]
    public var dealLead: String?
    public var warmthScore: Int?
    public var introPath: String?
    public var daysInStage: Int
    public var lastTouchpoint: String?
    public var nextStep: String?
    /// YYYY-MM-DD the next step is due by.
    public var nextStepDue: String? = nil
    /// Server-computed: a next step past its due date.
    public var nextStepOverdue: Bool? = nil
    public let updatedAt: String?

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

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = (try? c.decodeIfPresent(String.self, forKey: .companyId)) ?? ""
        stage = (try? c.decodeIfPresent(String.self, forKey: .stage)) ?? "Sourced"
        stages = (try? c.decodeIfPresent([String].self, forKey: .stages)) ?? ["Sourced", "Partner Intro", "Technical Diligence", "Term Sheet / IC", "Portfolio"]
        dealLead = try? c.decodeIfPresent(String.self, forKey: .dealLead)
        warmthScore = try? c.decodeIfPresent(Int.self, forKey: .warmthScore)
        introPath = try? c.decodeIfPresent(String.self, forKey: .introPath)
        daysInStage = (try? c.decodeIfPresent(Int.self, forKey: .daysInStage)) ?? 0
        lastTouchpoint = try? c.decodeIfPresent(String.self, forKey: .lastTouchpoint)
        nextStep = try? c.decodeIfPresent(String.self, forKey: .nextStep)
        nextStepDue = try? c.decodeIfPresent(String.self, forKey: .nextStepDue)
        nextStepOverdue = try? c.decodeIfPresent(Bool.self, forKey: .nextStepOverdue)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

// MARK: - Reports & Memos

public struct MacMemoFile: Codable, Hashable {
    public let language: String?
    public let path: String?
    public let pdfPath: String?

    enum CodingKeys: String, CodingKey {
        case language, path
        case pdfPath = "pdf_path"
    }
}

public struct MacReport: Identifiable, Hashable, Codable {
    public let id: String
    public let companyId: String?
    public let companyName: String?
    public let reportType: String?
    public let audience: String?
    public let language: String?
    public let status: String?
    public let progress: Int?
    public let stage: String?
    public let error: String?
    public let kind: String?
    public let createdAt: String?
    public let updatedAt: String?
    public let downloadUrls: [String: String]?
    public let previewUrls: [String: String]?
    public let memoFiles: [MacMemoFile]?
    public let failurePhase: String?
    public let logoUrl: String?
    public let logoDomain: String?

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
        case logoUrl = "logo_url"
        case logoDomain = "logo_domain"
    }

    public var isCancelled: Bool {
        (failurePhase ?? "").lowercased() == "cancelled" || (status ?? "").lowercased() == "cancelled"
    }

    public var displayTitle: String {
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

    public var isComplete: Bool {
        let s = (status ?? "").lowercased()
        return s.hasPrefix("complete")
    }

    public var isFailed: Bool {
        (status ?? "").lowercased().contains("fail")
    }

    public var canOpen: Bool {
        !(previewUrls ?? [:]).isEmpty || !(downloadUrls ?? [:]).isEmpty || !(memoFiles ?? []).isEmpty
    }

    public var statusLabel: String {
        let s = (status ?? "").lowercased()
        if s.hasPrefix("complete") { return "Complete" }
        if s.contains("fail") { return "Failed" }
        if s.contains("run") || !(stage ?? "").isEmpty { return stage ?? "Running" }
        return status?.capitalized ?? "—"
    }

    public var statusTone: String { statusLabel }

    public var dateLabel: String {
        String((updatedAt ?? createdAt ?? "").prefix(10))
    }
}

// MARK: - Batch E: Company Profile & Signal Score

/// `GET /api/companies/:id/profile`, in the server's own shape. This twin used
/// to read a shape the server never sent — `market_cap_usd`, `private.position`
/// as text, a `process` block — so market cap always showed "—", stage, fit,
/// decision and IC fell back to defaults, and any company the firm holds
/// failed to decode at all. Same shape as the Mac's MacCompanyProfile.
public struct MacCompanyProfile: Decodable, Hashable {
    public struct PublicSide: Decodable, Hashable {
        public let ticker: String?
        public let lastPrice: Double?
        public let changePct1d: Double?
        public let marketCap: Double?
        // What a listed company's profile shows in place of ARR and runway.
        public let peRatio: Double?
        public let eps: Double?
        public let fiftyTwoWeekHigh: Double?
        public let fiftyTwoWeekLow: Double?
        /// A fraction (0.0031 = 0.31%), as the quote feed stores it.
        public let dividendYield: Double?

        enum CodingKeys: String, CodingKey {
            case ticker, eps
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
            case marketCap = "market_cap"
            case peRatio = "pe_ratio"
            case fiftyTwoWeekHigh = "fifty_two_week_high"
            case fiftyTwoWeekLow = "fifty_two_week_low"
            case dividendYield = "dividend_yield"
        }
    }

    /// The firm's own position, when there is a portfolio record.
    public struct PrivateSide: Decodable, Hashable {
        public let round: String?
        public let investedUsd: Double?
        public let ownershipPct: Double?
        public let arrUsd: Double?
        public let runwayMonths: Double?
        public let markUsd: Double?
        public let moic: Double?

        enum CodingKeys: String, CodingKey {
            case position, moic
            case latestKpi = "latest_kpi"
            case latestMark = "latest_mark"
        }
        private enum PositionKeys: String, CodingKey {
            case round
            case investedUsd = "invested_usd"
            case ownershipPct = "ownership_pct"
        }
        private enum KpiKeys: String, CodingKey {
            case arrUsd = "arr_usd"
            case runwayMonths = "runway_months"
        }
        private enum MarkKeys: String, CodingKey {
            case valueUsd = "value_usd"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            let position = try? c.nestedContainer(keyedBy: PositionKeys.self, forKey: .position)
            round = try? position?.decodeIfPresent(String.self, forKey: .round)
            investedUsd = try? position?.decodeIfPresent(Double.self, forKey: .investedUsd)
            ownershipPct = try? position?.decodeIfPresent(Double.self, forKey: .ownershipPct)
            let kpi = try? c.nestedContainer(keyedBy: KpiKeys.self, forKey: .latestKpi)
            arrUsd = try? kpi?.decodeIfPresent(Double.self, forKey: .arrUsd)
            runwayMonths = try? kpi?.decodeIfPresent(Double.self, forKey: .runwayMonths)
            let mark = try? c.nestedContainer(keyedBy: MarkKeys.self, forKey: .latestMark)
            markUsd = try? mark?.decodeIfPresent(Double.self, forKey: .valueUsd)
            moic = try? c.decodeIfPresent(Double.self, forKey: .moic)
        }
    }

    /// A figure the company record carries — the rows the memo's metric
    /// snapshot quotes — with when and where it is from.
    public struct Reported: Decodable, Hashable {
        public let label: String
        public let value: String
        public let asOf: String?
        public let sourceClass: String?

        enum CodingKeys: String, CodingKey {
            case label, value
            case asOf = "as_of"
            case sourceClass = "source_class"
        }

        /// "2026-06-13" → "2026-06"; a bare year or free text stays as is.
        public var asOfShort: String? {
            guard let raw = asOf?.trimmingCharacters(in: .whitespaces), !raw.isEmpty else { return nil }
            let isoDay = raw.range(of: #"^\d{4}-\d{2}-\d{2}"#, options: .regularExpression) != nil
            return isoDay ? String(raw.prefix(7)) : raw
        }
    }

    public let companyId: String?
    public let name: String?
    public let description: String?
    public let isPublic: Bool
    public let ticker: String?
    public let publicSide: PublicSide?
    public let privateSide: PrivateSide?
    public let thesisFitScore: Int?
    public let thesisFitLabel: String?
    public let pipelineStage: String?
    public let latestVerdict: String?
    public let icOpenMeeting: Bool
    public let icMeetingCount: Int
    public let icReferenceCalls: Int
    public let filesCount: Int
    public let transcriptsCount: Int
    public let openCommentsCount: Int
    /// Keyed arr, revenue, growth, valuation, runway, tam.
    public let reported: [String: Reported]

    enum CodingKeys: String, CodingKey {
        case name, description, ticker, pipeline, ic, counts, reported
        case companyId = "company_id"
        case isPublic = "is_public"
        case publicSide = "public"
        case privateSide = "private"
        case thesisFit = "thesis_fit"
        case latestDecision = "latest_decision"
    }
    private enum FitKeys: String, CodingKey { case score, fit }
    private enum PipelineKeys: String, CodingKey { case stage }
    private enum DecisionKeys: String, CodingKey { case verdict }
    private enum ICKeys: String, CodingKey {
        case openMeeting = "open_meeting"
        case meetingCount = "meeting_count"
        case referenceCalls = "reference_calls"
    }
    private enum CountKeys: String, CodingKey {
        case files, transcripts
        case openComments = "open_comments"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        name = try? c.decodeIfPresent(String.self, forKey: .name)
        description = try? c.decodeIfPresent(String.self, forKey: .description)
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        isPublic = (try? c.decodeIfPresent(Bool.self, forKey: .isPublic)) ?? false
        publicSide = try? c.decodeIfPresent(PublicSide.self, forKey: .publicSide)
        privateSide = try? c.decodeIfPresent(PrivateSide.self, forKey: .privateSide)
        let fit = try? c.nestedContainer(keyedBy: FitKeys.self, forKey: .thesisFit)
        thesisFitScore = try? fit?.decodeIfPresent(Int.self, forKey: .score)
        thesisFitLabel = try? fit?.decodeIfPresent(String.self, forKey: .fit)
        let pipeline = try? c.nestedContainer(keyedBy: PipelineKeys.self, forKey: .pipeline)
        pipelineStage = try? pipeline?.decodeIfPresent(String.self, forKey: .stage)
        let decision = try? c.nestedContainer(keyedBy: DecisionKeys.self, forKey: .latestDecision)
        latestVerdict = try? decision?.decodeIfPresent(String.self, forKey: .verdict)
        let ic = try? c.nestedContainer(keyedBy: ICKeys.self, forKey: .ic)
        icOpenMeeting = ((try? ic?.decodeIfPresent(String.self, forKey: .openMeeting)) ?? nil) != nil
        icMeetingCount = ((try? ic?.decodeIfPresent(Int.self, forKey: .meetingCount)) ?? nil) ?? 0
        icReferenceCalls = ((try? ic?.decodeIfPresent(Int.self, forKey: .referenceCalls)) ?? nil) ?? 0
        let counts = try? c.nestedContainer(keyedBy: CountKeys.self, forKey: .counts)
        filesCount = ((try? counts?.decodeIfPresent(Int.self, forKey: .files)) ?? nil) ?? 0
        transcriptsCount = ((try? counts?.decodeIfPresent(Int.self, forKey: .transcripts)) ?? nil) ?? 0
        openCommentsCount = ((try? counts?.decodeIfPresent(Int.self, forKey: .openComments)) ?? nil) ?? 0
        reported = (try? c.decodeIfPresent([String: Reported].self, forKey: .reported)) ?? [:]
    }
}

/// `GET /api/companies/:id/signal-score`, in the server's shape: a score only
/// when enough components have data, the components themselves, and the
/// coverage line. Same shape as the Mac's MacSignalScore.
public struct MacSignalScore: Decodable, Hashable {
    public struct Component: Decodable, Hashable, Identifiable {
        public var id: String { name }
        public let name: String
        public let available: Bool
        public let points: Double?
        public let max: Int
        public let formula: String?

        enum CodingKeys: String, CodingKey { case name, available, points, max, formula }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? ""
            available = (try? c.decodeIfPresent(Bool.self, forKey: .available)) ?? false
            points = try? c.decodeIfPresent(Double.self, forKey: .points)
            max = (try? c.decodeIfPresent(Int.self, forKey: .max)) ?? 0
            formula = try? c.decodeIfPresent(String.self, forKey: .formula)
        }
    }

    public let score: Int?
    public let provisionalScore: Int?
    public let coverage: String?
    public let formula: String?
    public let components: [Component]

    /// Scored, but from fewer than half its components: a partial read.
    public var isPartial: Bool {
        guard score != nil, !components.isEmpty else { return false }
        return components.filter(\.available).count * 2 < components.count
    }

    public var availableCount: Int { components.filter(\.available).count }

    enum CodingKeys: String, CodingKey {
        case score, coverage, formula, components
        case provisionalScore = "provisional_score"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        provisionalScore = try? c.decodeIfPresent(Int.self, forKey: .provisionalScore)
        coverage = try? c.decodeIfPresent(String.self, forKey: .coverage)
        formula = try? c.decodeIfPresent(String.self, forKey: .formula)
        components = (try? c.decodeIfPresent([Component].self, forKey: .components)) ?? []
    }
}

// MARK: - A listed company's earnings and filings

public struct MacFiling: Identifiable, Hashable, Decodable {
    public var id: String { "\(form)-\(filed)-\(url)" }
    public let form: String
    public let filed: String
    public let description: String?
    public let url: String
    public let material: Bool

    enum CodingKeys: String, CodingKey { case form, filed, description, url, material }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        form = (try? c.decodeIfPresent(String.self, forKey: .form)) ?? ""
        filed = (try? c.decodeIfPresent(String.self, forKey: .filed)) ?? ""
        description = try? c.decodeIfPresent(String.self, forKey: .description)
        url = (try? c.decodeIfPresent(String.self, forKey: .url)) ?? ""
        material = (try? c.decodeIfPresent(Bool.self, forKey: .material)) ?? false
    }

    /// EDGAR's own description is often just the form again ("FORM 4").
    public var plainLabel: String {
        let desc = (description ?? "").trimmingCharacters(in: .whitespaces)
        let bare = desc.replacingOccurrences(of: "^form\\s+", with: "", options: [.regularExpression, .caseInsensitive]).uppercased()
        if !desc.isEmpty && bare != form.uppercased() { return desc }
        let labels: [String: String] = [
            "4": "Insider transaction", "8-K": "Current report", "10-Q": "Quarterly report",
            "10-K": "Annual report", "DEF 14A": "Proxy statement", "S-1": "Registration statement",
            "S-1/A": "Registration amendment", "424B4": "Prospectus",
            "SC 13D": "Ownership stake · active", "SC 13D/A": "Ownership stake · active, amended",
            "SC 13G": "Ownership stake · passive", "SC 13G/A": "Ownership stake · passive, amended",
            "6-K": "Foreign issuer report", "20-F": "Foreign annual report",
        ]
        return labels[form] ?? (desc.isEmpty ? form : desc)
    }
}

/// `GET /api/companies/:id/earnings-filings` — the public-company counterpart
/// of the deal pipeline. Same shape as the Mac's MacCompanyEarningsFilings.
public struct MacCompanyEarningsFilings: Decodable, Hashable {
    public struct Quarter: Identifiable, Decodable, Hashable {
        public var id: String { (period ?? "") + (reported ?? "") }
        public let period: String?
        public let reported: String?
        public let eps: Double?
        public let estimate: Double?
        public let surprisePct: Double?

        enum CodingKeys: String, CodingKey {
            case period, reported, eps, estimate
            case surprisePct = "surprise_pct"
        }
    }

    public struct Earnings: Decodable, Hashable {
        public let nextDate: String?
        public let nextEstimated: Bool
        public let daysToNext: Int?
        public let history: [Quarter]

        enum CodingKeys: String, CodingKey {
            case history
            case nextDate = "next_date"
            case nextEstimated = "next_estimated"
            case daysToNext = "days_to_next"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            nextDate = try? c.decodeIfPresent(String.self, forKey: .nextDate)
            nextEstimated = (try? c.decodeIfPresent(Bool.self, forKey: .nextEstimated)) ?? false
            daysToNext = try? c.decodeIfPresent(Int.self, forKey: .daysToNext)
            history = (try? c.decodeIfPresent([Quarter].self, forKey: .history)) ?? []
        }
    }

    public let ticker: String?
    public let earnings: Earnings?
    public let filings: [MacFiling]
    public let error: String?

    enum CodingKeys: String, CodingKey { case ticker, earnings, filings, error }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        earnings = try? c.decodeIfPresent(Earnings.self, forKey: .earnings)
        filings = (try? c.decodeIfPresent([MacFiling].self, forKey: .filings)) ?? []
        error = try? c.decodeIfPresent(String.self, forKey: .error)
    }
}

// MARK: - Memo Studio: has anything been investigated?

/// The slice of `GET /api/companies/:id/memo-editor` this app needs: whether an
/// investigation has seeded the cards, and how many cards are still the
/// company-record template. The Mac and web show the cards themselves.
public struct MacMemoEditorSummary: Decodable, Hashable {
    public let investigated: Bool
    public let templateCardCount: Int

    private enum Keys: String, CodingKey {
        case sections
        case agentRun = "agent_run"
    }
    private enum SectionKeys: String, CodingKey {
        case investmentThesis = "investment_thesis"
        case risksMitigations = "risks_mitigations"
    }
    private enum CardListKeys: String, CodingKey { case cards }
    private struct Card: Decodable { let placeholder: Bool? }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        investigated = c.contains(.agentRun) && !((try? c.decodeNil(forKey: .agentRun)) ?? true)
        var templates = 0
        if let sections = try? c.nestedContainer(keyedBy: SectionKeys.self, forKey: .sections) {
            for key in [SectionKeys.investmentThesis, .risksMitigations] {
                let list = try? sections.nestedContainer(keyedBy: CardListKeys.self, forKey: key)
                let cards = (try? list?.decodeIfPresent([Card].self, forKey: .cards)) ?? nil
                templates += (cards ?? []).filter { $0.placeholder == true }.count
            }
        }
        templateCardCount = templates
    }
}

// MARK: - Comps & Valuation Multiples

public struct MacCompPeer: Identifiable, Hashable, Decodable {
    public var id: String { ticker }
    public let ticker: String
    public let name: String?
    public let lastPrice: Double?
    public let changePct1d: Double?
    public let marketCapUsd: Double?
    public let revenueUsd: Double?
    public let priceToSales: Double?
    public let revenueGrowth: Double?
    public let grossMargin: Double?
    public let source: String?

    enum CodingKeys: String, CodingKey {
        case ticker, name, source
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
        case marketCapUsd = "market_cap_usd"
        case revenueUsd = "revenue_usd"
        case priceToSales = "price_to_sales"
        case revenueGrowth = "revenue_growth"
        case grossMargin = "gross_margin"
    }
}

public struct MacCompsPrivate: Decodable {
    public struct Source: Hashable, Decodable {
        public let field: String?
        public let section: String?
        public let excerpt: String?
    }
    public let postMoneyUsd: Double?
    public let revenueUsd: Double?
    public let impliedMultiple: Double?
    public let vsPeerMedianPct: Double?
    public let basis: String?
    public let sources: [Source]

    enum CodingKeys: String, CodingKey {
        case sources, basis
        case postMoneyUsd = "post_money_usd"
        case revenueUsd = "revenue_usd"
        case impliedMultiple = "implied_multiple"
        case vsPeerMedianPct = "vs_peer_median_pct"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        postMoneyUsd = try? c.decodeIfPresent(Double.self, forKey: .postMoneyUsd)
        revenueUsd = try? c.decodeIfPresent(Double.self, forKey: .revenueUsd)
        impliedMultiple = try? c.decodeIfPresent(Double.self, forKey: .impliedMultiple)
        vsPeerMedianPct = try? c.decodeIfPresent(Double.self, forKey: .vsPeerMedianPct)
        basis = try? c.decodeIfPresent(String.self, forKey: .basis)
        sources = (try? c.decodeIfPresent([Source].self, forKey: .sources)) ?? []
    }
}

public struct MacComps: Decodable {
    public let companyId: String?
    public let generatedAt: String?
    public let peers: [MacCompPeer]
    public let peerMedianPriceToSales: Double?
    public let privateSide: MacCompsPrivate?
    public let note: String?

    enum CodingKeys: String, CodingKey {
        case peers, note
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case peerMedianPriceToSales = "peer_median_price_to_sales"
        case privateSide = "private"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        peers = (try? c.decodeIfPresent([MacCompPeer].self, forKey: .peers)) ?? []
        peerMedianPriceToSales = try? c.decodeIfPresent(Double.self, forKey: .peerMedianPriceToSales)
        privateSide = try? c.decodeIfPresent(MacCompsPrivate.self, forKey: .privateSide)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - Cap Table Simulator

public struct MacCapModelInputs: Codable, Equatable {
    public var preMoneyMusd: Double?
    public var newMoneyMusd: Double?
    public var ourCheckMusd: Double?
    public var optionPoolPctPost: Double?
    public var liquidationPreferenceX: Double?
    public var participating: Bool
    public var exitValuesMusd: [Double]
    public var notes: String

    enum CodingKeys: String, CodingKey {
        case participating, notes
        case preMoneyMusd = "pre_money_musd"
        case newMoneyMusd = "new_money_musd"
        case ourCheckMusd = "our_check_musd"
        case optionPoolPctPost = "option_pool_pct_post"
        case liquidationPreferenceX = "liquidation_preference_x"
        case exitValuesMusd = "exit_values_musd"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        preMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .preMoneyMusd)
        newMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .newMoneyMusd)
        ourCheckMusd = try? c.decodeIfPresent(Double.self, forKey: .ourCheckMusd)
        optionPoolPctPost = try? c.decodeIfPresent(Double.self, forKey: .optionPoolPctPost)
        liquidationPreferenceX = try? c.decodeIfPresent(Double.self, forKey: .liquidationPreferenceX)
        participating = (try? c.decodeIfPresent(Bool.self, forKey: .participating)) ?? false
        exitValuesMusd = (try? c.decodeIfPresent([Double].self, forKey: .exitValuesMusd)) ?? []
        notes = (try? c.decodeIfPresent(String.self, forKey: .notes)) ?? ""
    }

    public init(
        preMoneyMusd: Double?,
        newMoneyMusd: Double?,
        ourCheckMusd: Double?,
        optionPoolPctPost: Double?,
        liquidationPreferenceX: Double?,
        participating: Bool,
        exitValuesMusd: [Double],
        notes: String
    ) {
        self.preMoneyMusd = preMoneyMusd
        self.newMoneyMusd = newMoneyMusd
        self.ourCheckMusd = ourCheckMusd
        self.optionPoolPctPost = optionPoolPctPost
        self.liquidationPreferenceX = liquidationPreferenceX
        self.participating = participating
        self.exitValuesMusd = exitValuesMusd
        self.notes = notes
    }
}

public struct MacCapWaterfallRow: Identifiable, Hashable, Decodable {
    public var id: Double { exitMusd }
    public let exitMusd: Double
    public let ourProceedsMusd: Double?
    public let multipleOnCheck: Double?
    public let converted: Bool?

    enum CodingKeys: String, CodingKey {
        case converted
        case exitMusd = "exit_musd"
        case ourProceedsMusd = "our_proceeds_musd"
        case multipleOnCheck = "multiple_on_check"
    }
}

public struct MacCapModelResult: Decodable {
    public let ready: Bool
    public let reason: String?
    public let postMoneyMusd: Double?
    public let roundOwnershipPct: Double?
    public let ourOwnershipPct: Double?
    public let existingOwnershipPctAfter: Double?
    public let waterfall: [MacCapWaterfallRow]

    enum CodingKeys: String, CodingKey {
        case ready, reason, waterfall
        case postMoneyMusd = "post_money_musd"
        case roundOwnershipPct = "round_ownership_pct"
        case ourOwnershipPct = "our_ownership_pct"
        case existingOwnershipPctAfter = "existing_ownership_pct_after"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ready = (try? c.decodeIfPresent(Bool.self, forKey: .ready)) ?? false
        reason = try? c.decodeIfPresent(String.self, forKey: .reason)
        postMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .postMoneyMusd)
        roundOwnershipPct = try? c.decodeIfPresent(Double.self, forKey: .roundOwnershipPct)
        ourOwnershipPct = try? c.decodeIfPresent(Double.self, forKey: .ourOwnershipPct)
        existingOwnershipPctAfter = try? c.decodeIfPresent(Double.self, forKey: .existingOwnershipPctAfter)
        waterfall = (try? c.decodeIfPresent([MacCapWaterfallRow].self, forKey: .waterfall)) ?? []
    }
}

public struct MacCapModelPayload: Decodable {
    public let companyId: String?
    public let inputs: MacCapModelInputs
    public let result: MacCapModelResult?

    enum CodingKeys: String, CodingKey {
        case inputs, result
        case companyId = "company_id"
    }
}

// MARK: - VC Ratios Blotter

public struct MacVCRatios: Decodable {
    public struct MetricItem: Decodable, Hashable {
        public let name: String
        public let value: Double?
        public let formatted: String
        public let benchmark: String?
        public let statusTone: String? // "green", "orange", "red"
        public let description: String?

        enum CodingKeys: String, CodingKey {
            case name, value, formatted, benchmark, description
            case statusTone = "status_tone"
        }
    }

    public let companyId: String?
    public let generatedAt: String?
    public let ruleOf40: MetricItem?
    public let magicNumber: MetricItem?
    public let netRetention: MetricItem?
    public let burnMultiple: MetricItem?
    public let cacPaybackMonths: MetricItem?
    public let grossMargin: MetricItem?

    enum CodingKeys: String, CodingKey {
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case ruleOf40 = "rule_of_40"
        case magicNumber = "magic_number"
        case netRetention = "net_retention"
        case burnMultiple = "burn_multiple"
        case cacPaybackMonths = "cac_payback_months"
        case grossMargin = "gross_margin"
    }
}

// MARK: - Decisions & Retrospectives

public struct MacRetrospective: Identifiable, Hashable, Codable {
    public let id: String
    public let assessedAt: String?
    public let verdict: String
    public let rationaleEn: String?
    public let rationaleZh: String?
    public let newsTitles: [String]

    enum CodingKeys: String, CodingKey {
        case id, verdict
        case assessedAt = "assessed_at"
        case rationaleEn = "rationale_en"
        case rationaleZh = "rationale_zh"
        case newsTitles = "news_titles"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        assessedAt = try? c.decodeIfPresent(String.self, forKey: .assessedAt)
        verdict = (try? c.decodeIfPresent(String.self, forKey: .verdict)) ?? "still_right"
        rationaleEn = try? c.decodeIfPresent(String.self, forKey: .rationaleEn)
        rationaleZh = try? c.decodeIfPresent(String.self, forKey: .rationaleZh)
        newsTitles = (try? c.decodeIfPresent([String].self, forKey: .newsTitles)) ?? []
    }

    public var label: String {
        switch verdict {
        case "still_right": return "Still right"
        case "questionable": return "Questionable"
        case "looks_wrong": return "Looks wrong"
        default: return verdict.capitalized
        }
    }
}

public struct MacDecision: Identifiable, Hashable, Codable {
    public let id: String
    public let verdict: String
    public let explanation: String
    public let decidedAt: String?
    public let createdAt: String?
    public let createdBy: String?
    public let reportId: String?
    public let retrospectives: [MacRetrospective]

    enum CodingKeys: String, CodingKey {
        case id, verdict, explanation, retrospectives
        case decidedAt = "decided_at"
        case createdAt = "created_at"
        case createdBy = "created_by"
        case reportId = "report_id"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        verdict = ((try? c.decodeIfPresent(String.self, forKey: .verdict)) ?? "watch").lowercased()
        explanation = (try? c.decodeIfPresent(String.self, forKey: .explanation)) ?? ""
        decidedAt = try? c.decodeIfPresent(String.self, forKey: .decidedAt)
        createdAt = try? c.decodeIfPresent(String.self, forKey: .createdAt)
        createdBy = try? c.decodeIfPresent(String.self, forKey: .createdBy)
        reportId = try? c.decodeIfPresent(String.self, forKey: .reportId)
        retrospectives = (try? c.decodeIfPresent([MacRetrospective].self, forKey: .retrospectives)) ?? []
    }

    public var verdictLabel: String {
        switch verdict {
        case "invest": return "Invest"
        case "pass": return "Pass"
        default: return "Watch"
        }
    }
}

public enum MacLifecycleStage: String, CaseIterable, Identifiable {
    case sourced = "Sourced"
    case technicalDD = "Technical DD"
    case icReview = "IC Review"
    case termSheet = "Term Sheet"
    case portfolio = "Portfolio"
    case passed = "Passed"
    case watching = "Watching"

    public var id: String { rawValue }

    public static func derive(row: Any?, latestDecision: MacDecision?) -> MacLifecycleStage {
        if let d = latestDecision {
            switch d.verdict.lowercased() {
            case "invest": return .portfolio
            case "pass": return .passed
            case "watch": return .watching
            default: break
            }
        }
        return .sourced
    }
}

// MARK: - Memo Studio Workbench Models

public struct MacThesisSpine: Hashable, Codable {
    public var id: String { premise }
    public var premise: String
    public var whyNow: String?
    public var coreDilemma: String?
    public var convictionScore: Int?
    public var pillars: [MacThesisPillar]?

    enum CodingKeys: String, CodingKey {
        case premise, pillars
        case whyNow = "why_now"
        case coreDilemma = "core_dilemma"
        case convictionScore = "conviction_score"
    }

    public init(premise: String = "", whyNow: String? = nil, coreDilemma: String? = nil, convictionScore: Int? = nil, pillars: [MacThesisPillar]? = nil) {
        self.premise = premise
        self.whyNow = whyNow
        self.coreDilemma = coreDilemma
        self.convictionScore = convictionScore
        self.pillars = pillars
    }
}

public struct MacRiskCard: Identifiable, Hashable, Codable {
    public var id: String
    public var title: String
    public var category: String
    public var severity: String
    public var mitigation: String?
    public var reframing: String?

    public init(id: String = UUID().uuidString, title: String, category: String = "Moat", severity: String = "high", mitigation: String? = nil, reframing: String? = nil) {
        self.id = id
        self.title = title
        self.category = category
        self.severity = severity
        self.mitigation = mitigation
        self.reframing = reframing
    }
}

public struct MacReadinessGate: Identifiable, Hashable, Codable {
    public var id: String { name }
    public let name: String
    public let passed: Bool
    public let detail: String?
    public var isDone: Bool { passed }
    public var label: String? { name }
    public var notes: String? { detail }
}

public struct MacReadinessArea: Identifiable, Hashable, Codable {
    public var id: String { title }
    public let title: String
    public let status: String
    public let notes: String?
}

public struct MacEvidenceClaim: Identifiable, Hashable, Codable {
    public var id: String { claim }
    public let claim: String
    public let sourceDoc: String?
    public let verified: Bool?
    public let confidence: Double?
    public var metric: String? { nil }
    public var source: String? { sourceDoc }

    enum CodingKeys: String, CodingKey {
        case claim, verified, confidence
        case sourceDoc = "source_doc"
    }
}

public struct MacEvidenceMatrix: Decodable {
    public let companyId: String?
    public let claims: [MacEvidenceClaim]
}

public struct MacMemoAnalysis: Decodable {
    public struct Readiness: Decodable {
        public let score: Int?
        public let total: Int?
        public let readyForMemo: Bool?
        public let gates: [MacReadinessGate]

        public var pct: Double? {
            guard let score, let total, total > 0 else { return nil }
            return Double(score) / Double(total)
        }

        enum CodingKeys: String, CodingKey {
            case score, total, gates
            case readyForMemo = "ready_for_memo"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            score = try? c.decodeIfPresent(Int.self, forKey: .score)
            total = try? c.decodeIfPresent(Int.self, forKey: .total)
            readyForMemo = try? c.decodeIfPresent(Bool.self, forKey: .readyForMemo)
            gates = (try? c.decodeIfPresent([MacReadinessGate].self, forKey: .gates)) ?? []
        }
    }

    public let companyId: String?
    public let readiness: Readiness?
    public let areas: [MacReadinessArea]?
    public let risks: [MacRiskCard]?
    public let thesisSpine: MacThesisSpine?
    public let readinessGates: [MacReadinessGate]?
    public let evidenceClaims: [MacEvidenceClaim]?

    enum CodingKeys: String, CodingKey {
        case readiness, areas, risks
        case companyId = "company_id"
        case thesisSpine = "thesis_spine"
        case readinessGates = "readiness_gates"
        case evidenceClaims = "evidence_claims"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        readiness = try? c.decodeIfPresent(Readiness.self, forKey: .readiness)
        areas = try? c.decodeIfPresent([MacReadinessArea].self, forKey: .areas)
        risks = try? c.decodeIfPresent([MacRiskCard].self, forKey: .risks)
        thesisSpine = try? c.decodeIfPresent(MacThesisSpine.self, forKey: .thesisSpine)
        readinessGates = try? c.decodeIfPresent([MacReadinessGate].self, forKey: .readinessGates)
        evidenceClaims = try? c.decodeIfPresent([MacEvidenceClaim].self, forKey: .evidenceClaims)
    }
}

public struct MacMemoEditorState: Codable {
    public var thesis: MacThesisSpine?
    public var risks: [MacRiskCard]
    public var gates: [MacReadinessGate]

    public init(thesis: MacThesisSpine? = nil, risks: [MacRiskCard] = [], gates: [MacReadinessGate] = []) {
        self.thesis = thesis
        self.risks = risks
        self.gates = gates
    }
}

// MARK: - IC Room & Review Models

public struct MacICVote: Identifiable, Hashable, Decodable {
    public var id: String { member }
    public let member: String
    public let memberName: String?
    public let vote: String
    public let conviction: Int?
    public let note: String?
    public let at: String?

    public var displayName: String { memberName ?? member }
    public var label: String { vote == "invest" ? "Invest" : (vote == "pass" ? "Pass" : "More work") }

    enum CodingKeys: String, CodingKey {
        case member, vote, conviction, note, at
        case memberName = "member_name"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        member = (try? c.decodeIfPresent(String.self, forKey: .member)) ?? "?"
        memberName = try? c.decodeIfPresent(String.self, forKey: .memberName)
        vote = (try? c.decodeIfPresent(String.self, forKey: .vote)) ?? "more_work"
        conviction = try? c.decodeIfPresent(Int.self, forKey: .conviction)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        at = try? c.decodeIfPresent(String.self, forKey: .at)
    }
}

public struct MacICTally: Decodable {
    public let invest: Int
    public let pass: Int
    public let moreWork: Int
    public let total: Int
    public let averageConviction: Double?

    enum CodingKeys: String, CodingKey {
        case invest, pass, total
        case moreWork = "more_work"
        case averageConviction = "average_conviction"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        invest = (try? c.decodeIfPresent(Int.self, forKey: .invest)) ?? 0
        pass = (try? c.decodeIfPresent(Int.self, forKey: .pass)) ?? 0
        moreWork = (try? c.decodeIfPresent(Int.self, forKey: .moreWork)) ?? 0
        total = (try? c.decodeIfPresent(Int.self, forKey: .total)) ?? 0
        averageConviction = try? c.decodeIfPresent(Double.self, forKey: .averageConviction)
    }
}

public struct MacICPrepPayload: Decodable {
    public let companyId: String?
    public let ready: Bool
    public let checklist: [MacReadinessGate]
}

public struct MacICRoomPayload: Decodable {
    public let companyId: String?
    public let reportId: String?
    public let votes: [MacICVote]
    public let tally: MacICTally?
    public let questions: [String]?
}

// MARK: - Thesis Tracker & Lint

public struct MacThesisPillar: Identifiable, Hashable, Codable {
    public var id: String { title }
    public let title: String
    public let assertion: String?
    public let status: String? // "on_track", "tracking_behind", "broken"
    public let latestEvidence: String?
    public let confidence: Double?
    public let whyItMatters: String?

    enum CodingKeys: String, CodingKey {
        case title, assertion, status, confidence
        case latestEvidence = "latest_evidence"
        case whyItMatters = "why_it_matters"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? ""
        assertion = try? c.decodeIfPresent(String.self, forKey: .assertion)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        latestEvidence = try? c.decodeIfPresent(String.self, forKey: .latestEvidence)
        confidence = try? c.decodeIfPresent(Double.self, forKey: .confidence)
        whyItMatters = try? c.decodeIfPresent(String.self, forKey: .whyItMatters)
    }
}

public struct MacThesisTrackerPayload: Decodable {
    public let companyId: String?
    public let pillars: [MacThesisPillar]
}

// MARK: - Team Comments

public struct MacCommentTarget: Hashable, Codable {
    public let kind: String
    public let ref: String
    public let label: String?

    public init(kind: String, ref: String, label: String? = nil) {
        self.kind = kind
        self.ref = ref
        self.label = label
    }
}

public struct MacComment: Identifiable, Hashable, Codable {
    public let id: String
    public let author: String
    public let content: String
    public let createdAt: String?
    public let targetKind: String?
    public let targetRef: String?

    public var authorHandle: String { author }
    public var body: String { content }
    public var isResolved: Bool { false }

    enum CodingKeys: String, CodingKey {
        case id, author, content
        case createdAt = "created_at"
        case targetKind = "target_kind"
        case targetRef = "target_ref"
    }
}

// MARK: - Pitch Deck Intake

public struct MacThesisScore: Decodable {
    public let fit: String
    public let score: Int?
    public let label: String
    public let reasons: [String]
    public let openQuestions: [String]

    enum CodingKeys: String, CodingKey {
        case fit, score, label, reasons
        case openQuestions = "open_questions"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        fit = (try? c.decodeIfPresent(String.self, forKey: .fit)) ?? ""
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        label = (try? c.decodeIfPresent(String.self, forKey: .label)) ?? ""
        reasons = (try? c.decodeIfPresent([String].self, forKey: .reasons)) ?? []
        openQuestions = (try? c.decodeIfPresent([String].self, forKey: .openQuestions)) ?? []
    }
}

public struct MacIntakeField: Identifiable, Hashable, Decodable {
    public var id: String { name + (page.map { "-\($0)" } ?? "") }
    public let name: String
    public let value: String
    public let usd: Double?
    public let page: Int?
    public let excerpt: String?

    enum CodingKeys: String, CodingKey {
        case name, value, usd, page, excerpt
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? c.decode(String.self, forKey: .name)) ?? ""
        if let s = try? c.decodeIfPresent(String.self, forKey: .value) {
            value = s
        } else if let d = try? c.decodeIfPresent(Double.self, forKey: .value) {
            value = String(d)
        } else {
            value = ""
        }
        usd = try? c.decodeIfPresent(Double.self, forKey: .usd)
        page = try? c.decodeIfPresent(Int.self, forKey: .page)
        excerpt = try? c.decodeIfPresent(String.self, forKey: .excerpt)
    }

    public var label: String {
        switch name {
        case "post_money": return "Post-money"
        case "arr": return "ARR"
        default: return name.capitalized
        }
    }

    public var display: String {
        if let usd {
            if usd >= 1e9 { return String(format: "$%.2fB", usd / 1e9) }
            if usd >= 1e6 { return String(format: "$%.1fM", usd / 1e6) }
            if usd >= 1e3 { return String(format: "$%.0fK", usd / 1e3) }
        }
        if name == "runway" { return "\(value) months" }
        return value
    }
}

public struct MacIntakeResult: Decodable {
    public let company: MacCompany
    public let fileId: String?
    public let fileName: String?
    public let slideCount: Int
    public let fields: [MacIntakeField]
    public let thesis: MacThesisScore?

    private struct FileRef: Decodable { let id: String?; let filename: String? }
    private struct Extraction: Decodable { let fields: [MacIntakeField]? }

    enum CodingKeys: String, CodingKey {
        case company, file, extraction, thesis
        case slideCount = "slide_count"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        company = try c.decode(MacCompany.self, forKey: .company)
        let file = try? c.decodeIfPresent(FileRef.self, forKey: .file)
        fileId = file?.id
        fileName = file?.filename
        slideCount = (try? c.decodeIfPresent(Int.self, forKey: .slideCount)) ?? 0
        fields = (try? c.decodeIfPresent(Extraction.self, forKey: .extraction))?.fields ?? []
        thesis = try? c.decodeIfPresent(MacThesisScore.self, forKey: .thesis)
    }
}

// MARK: - Report Customizer Configuration

public struct MacReportCustomizerConfig: Hashable, Codable, Sendable {
    public var reportType: String = "Investment Report (Auto)"
    public var audience: String = "Internal"
    public var language: String = "en"
    public var generationMode: String = "studio_review" // "one_click" or "studio_review"
    public var reportMode: String = "full" // "full" or "compact"
    public var quality: String = "best" // "best", "balanced", "economy"
    public var customPrompt: String = ""
    public var focusPillars: [String] = []
    public var companyTypeLens: String = "auto"
    public var selectedDocumentIds: [String] = []

    public init(
        reportType: String = "Investment Report (Auto)",
        audience: String = "Internal",
        language: String = "en",
        generationMode: String = "studio_review",
        reportMode: String = "full",
        quality: String = "best",
        customPrompt: String = "",
        focusPillars: [String] = [],
        companyTypeLens: String = "auto",
        selectedDocumentIds: [String] = []
    ) {
        self.reportType = reportType
        self.audience = audience
        self.language = language
        self.generationMode = generationMode
        self.reportMode = reportMode
        self.quality = quality
        self.customPrompt = customPrompt
        self.focusPillars = focusPillars
        self.companyTypeLens = companyTypeLens
        self.selectedDocumentIds = selectedDocumentIds
    }
}
