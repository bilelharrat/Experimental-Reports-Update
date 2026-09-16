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

    enum CodingKeys: String, CodingKey {
        case name, role, bio, education
        case pedigreeTags = "pedigree_tags"
        case pastCompanies = "past_companies"
        case priorExits = "prior_exits"
        case patentsOrPapersCount = "patents_papers_count"
        case githubHandle = "github_handle"
        case linkedinUrl = "linkedin_url"
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

    enum CodingKeys: String, CodingKey {
        case founders
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case advisorsAndBoard = "advisors_and_board"
        case developerTraction = "developer_traction"
        case teamHeadcount = "team_headcount"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        founders = (try? c.decodeIfPresent([MacFounderProfile].self, forKey: .founders)) ?? []
        advisorsAndBoard = try? c.decodeIfPresent([MacFounderProfile].self, forKey: .advisorsAndBoard)
        developerTraction = try? c.decodeIfPresent(MacDeveloperTraction.self, forKey: .developerTraction)
        teamHeadcount = try? c.decodeIfPresent(MacTeamHeadcount.self, forKey: .teamHeadcount)
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

public struct MacCompanyProfile: Decodable, Hashable {
    public struct PublicSide: Decodable, Hashable {
        public let ticker: String?
        public let lastPrice: Double?
        public let changePct1d: Double?
        public let marketCapUsd: Double?

        enum CodingKeys: String, CodingKey {
            case ticker
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
            case marketCapUsd = "market_cap_usd"
        }
    }

    public struct PrivateSide: Decodable, Hashable {
        public let position: String?
        public let ownershipPct: Double?
        public let arrUsd: Double?
        public let runwayMonths: Double?
        public let currentMarkUsd: Double?
        public let moic: Double?

        enum CodingKeys: String, CodingKey {
            case position, moic
            case ownershipPct = "ownership_pct"
            case arrUsd = "arr_usd"
            case runwayMonths = "runway_months"
            case currentMarkUsd = "current_mark_usd"
        }
    }

    public struct ProcessSide: Decodable, Hashable {
        public let stage: String?
        public let thesisFit: String?
        public let lastDecision: String?
        public let icVotesCount: Int?
        public let attachedFilesCount: Int?

        enum CodingKeys: String, CodingKey {
            case stage
            case thesisFit = "thesis_fit"
            case lastDecision = "last_decision"
            case icVotesCount = "ic_votes_count"
            case attachedFilesCount = "attached_files_count"
        }
    }

    public let companyId: String?
    public let name: String?
    public let kind: String?
    public let publicSide: PublicSide?
    public let privateSide: PrivateSide?
    public let process: ProcessSide?

    enum CodingKeys: String, CodingKey {
        case name, kind, process
        case companyId = "company_id"
        case publicSide = "public"
        case privateSide = "private"
    }
}

public struct MacSignalBreakdown: Decodable, Hashable {
    public let momentum: Double?
    public let fundamentals: Double?
    public let devTraction: Double?
    public let sentiment: Double?
    public let riskAdjusted: Double?

    enum CodingKeys: String, CodingKey {
        case momentum, fundamentals, sentiment
        case devTraction = "dev_traction"
        case riskAdjusted = "risk_adjusted"
    }
}

public struct MacSignalScore: Decodable, Hashable {
    public let companyId: String?
    public let score: Int?
    public let confidence: Double?
    public let percentile: Int?
    public let breakdown: MacSignalBreakdown?
    public let headline: String?

    enum CodingKeys: String, CodingKey {
        case score, confidence, percentile, breakdown, headline
        case companyId = "company_id"
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
