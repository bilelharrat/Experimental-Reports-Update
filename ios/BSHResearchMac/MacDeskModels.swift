import Foundation

// MARK: - Tracking rollup (`GET /api/tracking/rollup`)

struct MacRollup: Codable {
    let generatedAt: String?
    let companies: [MacRollupRow]
    let attention: [MacAttentionItem]
    let totals: MacRollupTotals?
    let unknownCompanyIds: [String]?

    enum CodingKeys: String, CodingKey {
        case companies, attention, totals
        case generatedAt = "generated_at"
        case unknownCompanyIds = "unknown_company_ids"
    }

    init(generatedAt: String?, companies: [MacRollupRow], attention: [MacAttentionItem], totals: MacRollupTotals?, unknownCompanyIds: [String]?) {
        self.generatedAt = generatedAt
        self.companies = companies
        self.attention = attention
        self.totals = totals
        self.unknownCompanyIds = unknownCompanyIds
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
        companies = try c.decodeIfPresent([MacRollupRow].self, forKey: .companies) ?? []
        attention = try c.decodeIfPresent([MacAttentionItem].self, forKey: .attention) ?? []
        totals = try? c.decodeIfPresent(MacRollupTotals.self, forKey: .totals)
        unknownCompanyIds = try? c.decodeIfPresent([String].self, forKey: .unknownCompanyIds)
    }
}

struct MacRollupTotals: Codable {
    let companyCount: Int?
    let attentionCount: Int?
    let highCount: Int?
    let needsActionCount: Int?
    let inProgressCount: Int?
    let notStartedCount: Int?
    let clearCompanyCount: Int?
    let failedMemoCount: Int?
    let runningMemoCount: Int?

    enum CodingKeys: String, CodingKey {
        case companyCount = "company_count"
        case attentionCount = "attention_count"
        case highCount = "high_count"
        case needsActionCount = "needs_action_count"
        case inProgressCount = "in_progress_count"
        case notStartedCount = "not_started_count"
        case clearCompanyCount = "clear_company_count"
        case failedMemoCount = "failed_memo_count"
        case runningMemoCount = "running_memo_count"
    }

    init(companyCount: Int?, attentionCount: Int?, highCount: Int?, needsActionCount: Int?, inProgressCount: Int?, notStartedCount: Int?, clearCompanyCount: Int?, failedMemoCount: Int?, runningMemoCount: Int?) {
        self.companyCount = companyCount
        self.attentionCount = attentionCount
        self.highCount = highCount
        self.needsActionCount = needsActionCount
        self.inProgressCount = inProgressCount
        self.notStartedCount = notStartedCount
        self.clearCompanyCount = clearCompanyCount
        self.failedMemoCount = failedMemoCount
        self.runningMemoCount = runningMemoCount
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyCount = try? c.decodeIfPresent(Int.self, forKey: .companyCount)
        attentionCount = try? c.decodeIfPresent(Int.self, forKey: .attentionCount)
        highCount = try? c.decodeIfPresent(Int.self, forKey: .highCount)
        needsActionCount = try? c.decodeIfPresent(Int.self, forKey: .needsActionCount)
        inProgressCount = try? c.decodeIfPresent(Int.self, forKey: .inProgressCount)
        notStartedCount = try? c.decodeIfPresent(Int.self, forKey: .notStartedCount)
        clearCompanyCount = try? c.decodeIfPresent(Int.self, forKey: .clearCompanyCount)
        failedMemoCount = try? c.decodeIfPresent(Int.self, forKey: .failedMemoCount)
        runningMemoCount = try? c.decodeIfPresent(Int.self, forKey: .runningMemoCount)
    }

    static func merged(_ parts: [MacRollupTotals]) -> MacRollupTotals? {
        guard !parts.isEmpty else { return nil }
        func sum(_ path: KeyPath<MacRollupTotals, Int?>) -> Int? {
            let values = parts.compactMap { $0[keyPath: path] }
            return values.isEmpty ? nil : values.reduce(0, +)
        }
        return MacRollupTotals(
            companyCount: sum(\.companyCount),
            attentionCount: sum(\.attentionCount),
            highCount: sum(\.highCount),
            needsActionCount: sum(\.needsActionCount),
            inProgressCount: sum(\.inProgressCount),
            notStartedCount: sum(\.notStartedCount),
            clearCompanyCount: sum(\.clearCompanyCount),
            failedMemoCount: sum(\.failedMemoCount),
            runningMemoCount: sum(\.runningMemoCount)
        )
    }
}

struct MacAttentionItem: Identifiable, Hashable, Codable {
    let id: String
    let companyId: String?
    let companyName: String?
    let kind: String?
    let severity: String?
    let count: Int?
    let label: String?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, severity, count, label, detail
        case companyId = "company_id"
        case companyName = "company_name"
    }

    var isHigh: Bool { severity == "high" }
}

struct MacNextAction: Hashable, Codable {
    let kind: String?
    let label: String?
}

struct MacRollupRow: Identifiable, Hashable, Codable {
    struct Price: Hashable, Codable {
        let changePct1d: Double?
        let changePct30d: Double?
        let lastPrice: Double?
        let currency: String?
        enum CodingKeys: String, CodingKey {
            case changePct1d = "change_pct_1d"
            case changePct30d = "change_pct_30d"
            case lastPrice = "last_price"
            case currency
        }
    }

    struct Memo: Hashable, Codable {
        let total: Int?
        let failed: Int?
        let running: Int?
        let complete: Int?
        let latestId: String?
        let latestStatus: String?
        let latestReportType: String?
        let latestUpdatedAt: String?
        let latestFailureDetail: String?
        let warningCount: Int?
        enum CodingKeys: String, CodingKey {
            case total, failed, running, complete
            case latestId = "latest_id"
            case latestStatus = "latest_status"
            case latestReportType = "latest_report_type"
            case latestUpdatedAt = "latest_updated_at"
            case latestFailureDetail = "latest_failure_detail"
            case warningCount = "warning_count"
        }
    }

    struct Risks: Hashable, Codable {
        let total: Int?
        let researched: Int?
        let needsReview: Int?
        let unresearched: Int?
        let highSeverityOpen: Int?
        enum CodingKeys: String, CodingKey {
            case total, researched, unresearched
            case needsReview = "needs_review"
            case highSeverityOpen = "high_severity_open"
        }
    }

    struct Evidence: Hashable, Codable {
        let total: Int?
        let supported: Int?
        let partial: Int?
        let missing: Int?
        let contradicted: Int?
        let mixed: Int?
    }

    struct Documents: Hashable, Codable {
        let total: Int?
        let unresolved: Int?
    }

    struct News: Hashable, Codable {
        let recentCount: Int?
        let latestTitle: String?
        let latestAt: String?
        enum CodingKeys: String, CodingKey {
            case recentCount = "recent_count"
            case latestTitle = "latest_title"
            case latestAt = "latest_at"
        }
    }

    struct Session: Hashable, Codable {
        let id: String?
        let approvedForMemo: Bool?
        let hasUnapprovedWork: Bool?
        enum CodingKeys: String, CodingKey {
            case id
            case approvedForMemo = "approved_for_memo"
            case hasUnapprovedWork = "has_unapproved_work"
        }
    }

    let id: String
    let name: String
    let ticker: String?
    let status: String?
    let companyType: String?
    let category: String?
    let price: Price?
    let memo: Memo?
    let risks: Risks?
    let evidence: Evidence?
    let documents: Documents?
    let news: News?
    let session: Session?
    let lastActivityAt: String?
    let bucket: String?
    let nextAction: MacNextAction?
    let attention: [MacAttentionItem]
    /// Server-derived deal stage (sourcing … passed) — shared with the web so both agree.
    let lifecycleStage: String?
    /// Explainable thesis fit computed server-side from the firm thesis.
    let thesisFit: MacThesisScore?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, category, price, memo, risks, evidence, documents, news, session, bucket, attention
        case companyType = "company_type"
        case lastActivityAt = "last_activity_at"
        case nextAction = "next_action"
        case lifecycleStage = "lifecycle_stage"
        case thesisFit = "thesis_fit"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? id
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        companyType = try? c.decodeIfPresent(String.self, forKey: .companyType)
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        price = try? c.decodeIfPresent(Price.self, forKey: .price)
        memo = try? c.decodeIfPresent(Memo.self, forKey: .memo)
        risks = try? c.decodeIfPresent(Risks.self, forKey: .risks)
        evidence = try? c.decodeIfPresent(Evidence.self, forKey: .evidence)
        documents = try? c.decodeIfPresent(Documents.self, forKey: .documents)
        news = try? c.decodeIfPresent(News.self, forKey: .news)
        session = try? c.decodeIfPresent(Session.self, forKey: .session)
        lastActivityAt = try? c.decodeIfPresent(String.self, forKey: .lastActivityAt)
        bucket = try? c.decodeIfPresent(String.self, forKey: .bucket)
        nextAction = try? c.decodeIfPresent(MacNextAction.self, forKey: .nextAction)
        attention = (try? c.decodeIfPresent([MacAttentionItem].self, forKey: .attention)) ?? []
        lifecycleStage = try? c.decodeIfPresent(String.self, forKey: .lifecycleStage)
        thesisFit = try? c.decodeIfPresent(MacThesisScore.self, forKey: .thesisFit)
    }

    var memoRunning: Bool { (memo?.running ?? 0) > 0 || MacRollupRow.runningStatuses.contains(memo?.latestStatus ?? "") }
    var memoComplete: Bool { (memo?.latestStatus ?? "").hasPrefix("complete") }
    var memoFailed: Bool { (memo?.latestStatus ?? "").hasPrefix("failed") }
    var primaryAttention: MacAttentionItem? { attention.first }

    static let runningStatuses: Set<String> = ["queued", "prepping", "ready_for_analysis", "analyzing", "running"]

    var memoStatusLabel: String {
        guard let s = memo?.latestStatus, !s.isEmpty else { return (memo?.total ?? 0) == 0 ? "No memo" : "—" }
        if s.hasPrefix("complete_with") { return "Complete · \(memo?.warningCount ?? 0) warnings" }
        if s.hasPrefix("complete") { return "Complete" }
        if s.hasPrefix("failed") { return "Failed" }
        return s.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

/// Deal lifecycle stage — derived from the rollup row plus the latest decision (client-side; no
/// per-company probing so the board never spawns a Serena session).
enum MacLifecycleStage: String, CaseIterable, Identifiable {
    case sourcing = "Sourcing"
    case screening = "Screening"
    case diligence = "Diligence"
    case ic = "IC"
    case portfolio = "Portfolio"
    case watch = "Watch"
    case passed = "Passed"
    case unknown = "—"

    var id: String { rawValue }

    /// Stages a company can actually be in; `.unknown` only means no rollup row or decision is loaded.
    static let knownCases: [MacLifecycleStage] = allCases.filter { $0 != .unknown }

    var isKnown: Bool { self != .unknown }

    var order: Int {
        switch self {
        case .sourcing: return 0
        case .screening: return 1
        case .diligence: return 2
        case .ic: return 3
        case .portfolio: return 4
        case .watch: return 5
        case .passed: return 6
        case .unknown: return 7
        }
    }

    var systemImage: String {
        switch self {
        case .sourcing: return "binoculars"
        case .screening: return "line.3.horizontal.decrease.circle"
        case .diligence: return "magnifyingglass.circle"
        case .ic: return "person.3"
        case .portfolio: return "briefcase.fill"
        case .watch: return "eye"
        case .passed: return "xmark.circle"
        case .unknown: return "questionmark.circle"
        }
    }

    static func derive(row: MacRollupRow?, latestDecision: MacDecision?) -> MacLifecycleStage {
        // Prefer the server's stage when it sends one so Mac and web never disagree.
        if let raw = row?.lifecycleStage, let stage = MacLifecycleStage.knownCases.first(where: { $0.rawValue.lowercased() == raw.lowercased() }) {
            return stage
        }
        if let verdict = latestDecision?.verdict {
            switch verdict {
            case "invest": return .portfolio
            case "pass": return .passed
            case "watch": return .watch
            default: break
            }
        }
        guard let row else { return .unknown }
        if row.memoRunning { return .diligence }
        if row.memoComplete { return .ic }
        if (row.memo?.total ?? 0) == 0 {
            return (row.documents?.total ?? 0) > 0 || (row.session != nil) ? .screening : .sourcing
        }
        return .diligence
    }
}

// MARK: - Decisions (`/api/companies/{id}/decisions`)

struct MacDecision: Identifiable, Hashable, Codable {
    let id: String
    let verdict: String
    let explanation: String
    let decidedAt: String?
    let createdAt: String?
    let createdBy: String?
    let reportId: String?
    let retrospectives: [MacRetrospective]

    enum CodingKeys: String, CodingKey {
        case id, verdict, explanation, retrospectives
        case decidedAt = "decided_at"
        case createdAt = "created_at"
        case createdBy = "created_by"
        case reportId = "report_id"
    }

    init(from decoder: Decoder) throws {
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

    var verdictLabel: String {
        switch verdict {
        case "invest": return "Invest"
        case "pass": return "Pass"
        default: return "Watch"
        }
    }

    /// Most recent retrospective the tracking sync wrote against this decision.
    var latestRetrospective: MacRetrospective? { retrospectives.first }

    var needsReunderwriting: Bool {
        guard let r = latestRetrospective else { return false }
        return r.verdict == "looks_wrong" || r.verdict == "questionable"
    }
}

struct MacRetrospective: Identifiable, Hashable, Codable {
    let id: String
    let assessedAt: String?
    let verdict: String
    let rationaleEn: String?
    let rationaleZh: String?
    let newsTitles: [String]

    enum CodingKeys: String, CodingKey {
        case id, verdict
        case assessedAt = "assessed_at"
        case rationaleEn = "rationale_en"
        case rationaleZh = "rationale_zh"
        case newsTitles = "news_titles"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        assessedAt = try? c.decodeIfPresent(String.self, forKey: .assessedAt)
        verdict = (try? c.decodeIfPresent(String.self, forKey: .verdict)) ?? "still_right"
        rationaleEn = try? c.decodeIfPresent(String.self, forKey: .rationaleEn)
        rationaleZh = try? c.decodeIfPresent(String.self, forKey: .rationaleZh)
        newsTitles = (try? c.decodeIfPresent([String].self, forKey: .newsTitles)) ?? []
    }

    var label: String {
        switch verdict {
        case "still_right": return "Still right"
        case "questionable": return "Questionable"
        case "looks_wrong": return "Looks wrong"
        default: return verdict.capitalized
        }
    }
}

struct MacDecisionCreate: Encodable {
    let verdict: String
    let explanation: String
    let decidedAt: String?
    let reportId: String?

    enum CodingKeys: String, CodingKey {
        case verdict, explanation
        case decidedAt = "decided_at"
        case reportId = "report_id"
    }
}

// MARK: - Tracking updates (`/api/companies/{id}/tracking-updates`)

struct MacTrackingItem: Identifiable, Hashable, Decodable {
    let id: String
    let title: String?
    let summary: String?
    let url: String?
    let publishedAt: String?
    let category: String?
    let tags: [String]
    let impact: String
    let recommendedAction: String?
    let capturedAt: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case id, title, summary, url, category, tags, impact, source
        case publishedAt = "published_at"
        case recommendedAction = "recommended_action"
        case capturedAt = "captured_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        summary = try? c.decodeIfPresent(String.self, forKey: .summary)
        url = try? c.decodeIfPresent(String.self, forKey: .url)
        publishedAt = try? c.decodeIfPresent(String.self, forKey: .publishedAt)
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        tags = (try? c.decodeIfPresent([String].self, forKey: .tags)) ?? []
        impact = ((try? c.decodeIfPresent(String.self, forKey: .impact)) ?? "low").lowercased()
        recommendedAction = try? c.decodeIfPresent(String.self, forKey: .recommendedAction)
        capturedAt = try? c.decodeIfPresent(String.self, forKey: .capturedAt)
        source = try? c.decodeIfPresent(String.self, forKey: .source)
    }

    var impactRank: Int {
        switch impact {
        case "high": return 0
        case "medium": return 1
        default: return 2
        }
    }
}

struct MacAutoRun: Identifiable, Hashable, Decodable {
    let id: String
    let action: String?
    let surface: String?
    let status: String?
    let newsTitles: [String]
    let updatedAt: String?
    let label: String?
    let error: String?
    let reportId: String?

    enum CodingKeys: String, CodingKey {
        case id, action, surface, status, label, error
        case newsTitles = "news_titles"
        case updatedAt = "updated_at"
        case jobRef = "job_ref"
    }

    private struct JobRef: Decodable {
        let reportId: String?
        enum CodingKeys: String, CodingKey { case reportId = "report_id" }
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        action = try? c.decodeIfPresent(String.self, forKey: .action)
        surface = try? c.decodeIfPresent(String.self, forKey: .surface)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        newsTitles = (try? c.decodeIfPresent([String].self, forKey: .newsTitles)) ?? []
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
        label = try? c.decodeIfPresent(String.self, forKey: .label)
        error = try? c.decodeIfPresent(String.self, forKey: .error)
        reportId = (try? c.decodeIfPresent(JobRef.self, forKey: .jobRef))?.reportId
    }

    var isRecommended: Bool { status == "recommended" }

    var actionLabel: String {
        switch action {
        case "full_report": return "Regenerate full memo"
        case "deep_investigate": return "Deep investigation"
        default: return "No action"
        }
    }
}

struct MacTrackingUpdates: Decodable {
    let companyId: String?
    let items: [MacTrackingItem]
    let autoRuns: [MacAutoRun]
    let latestAutoRun: MacAutoRun?
    let lastSyncedAt: String?
    let created: Int?

    enum CodingKeys: String, CodingKey {
        case items, created
        case companyId = "company_id"
        case autoRuns = "auto_runs"
        case latestAutoRun = "latest_auto_run"
        case lastSyncedAt = "last_synced_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        items = (try? c.decodeIfPresent([MacTrackingItem].self, forKey: .items)) ?? []
        autoRuns = (try? c.decodeIfPresent([MacAutoRun].self, forKey: .autoRuns)) ?? []
        latestAutoRun = try? c.decodeIfPresent(MacAutoRun.self, forKey: .latestAutoRun)
        lastSyncedAt = try? c.decodeIfPresent(String.self, forKey: .lastSyncedAt)
        created = try? c.decodeIfPresent(Int.self, forKey: .created)
    }

    var recommendedAutoRun: MacAutoRun? {
        autoRuns.first(where: \.isRecommended)
    }
}

struct MacAutoRunExecuteResult: Decodable {
    let executed: Bool
    let reason: String?
    let action: String?
    let reportId: String?

    enum CodingKeys: String, CodingKey {
        case executed, reason, action
        case reportId = "report_id"
    }

    var reasonLabel: String {
        switch reason {
        case "no_recommended_auto_run": return "Nothing is recommended right now."
        case "auto_run_not_recommended": return "This auto-run is no longer recommended."
        case "action_none": return "No action needed for that news."
        case "company_busy": return "A run is already in flight for this company."
        case "awaiting_studio_review": return "Memo Studio cards need a human review first."
        case "run_slots_full": return "All run slots are busy — try again shortly."
        case "studio_requires_parallel": return "Deep investigation needs the parallel memo engine enabled on the server."
        case "scope_check_failed": return "Scope check failed."
        default: return reason ?? "Not executed."
        }
    }
}

// MARK: - Memo analysis / IC prep (`/api/companies/{id}/memo-analysis`)

struct MacMemoTool: Identifiable, Hashable, Decodable {
    var id: String { name }
    let name: String
    let label: String?
    let description: String?
    let stage: String?
    let critical: Bool?
    let visibility: String?
    let produces: String?
    let status: String?
    let lastRunAt: String?
    let summary: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case name, label, description, stage, critical, visibility, produces, status, summary, error
        case lastRunAt = "last_run_at"
    }

    var isRunning: Bool { status == "running" }
    var isDone: Bool { status == "done" }
    var isHidden: Bool { visibility == "hidden" || stage == "hidden" }
}

struct MacReadinessGate: Identifiable, Hashable, Decodable {
    let id: String
    let label: String?
    let status: String?
    var isDone: Bool { status == "done" }
}

struct MacApprovalBlocker: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let label: String?
    let severity: String?
    let reason: String?
    let tool: String?
}

struct MacReadiness: Decodable {
    let score: Int?
    let total: Int?
    let pct: Double?
    let readyForApproval: Bool?
    let readyForMemo: Bool?
    let gates: [MacReadinessGate]
    let approvalBlockers: [MacApprovalBlocker]

    enum CodingKeys: String, CodingKey {
        case score, total, pct, gates
        case readyForApproval = "ready_for_approval"
        case readyForMemo = "ready_for_memo"
        case approvalBlockers = "approval_blockers"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        total = try? c.decodeIfPresent(Int.self, forKey: .total)
        pct = try? c.decodeIfPresent(Double.self, forKey: .pct)
        readyForApproval = try? c.decodeIfPresent(Bool.self, forKey: .readyForApproval)
        readyForMemo = try? c.decodeIfPresent(Bool.self, forKey: .readyForMemo)
        gates = (try? c.decodeIfPresent([MacReadinessGate].self, forKey: .gates)) ?? []
        approvalBlockers = (try? c.decodeIfPresent([MacApprovalBlocker].self, forKey: .approvalBlockers)) ?? []
    }
}

struct MacReadinessArea: Identifiable, Hashable, Decodable {
    let id: String
    let severity: String?
    let area: String?
    let whyItMatters: String?
    let tool: String?
    let status: String?
    let rationale: String?
    let reviewedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, severity, area, tool, status, rationale
        case whyItMatters = "why_it_matters"
        case reviewedAt = "reviewed_at"
    }

    var isOpen: Bool { (status ?? "open") == "open" }
}

struct MacRiskCard: Identifiable, Hashable, Decodable {
    let id: String
    let title: String?
    let description: String?
    let whyItMatters: String?
    let severity: String?
    let likelihood: String?
    let status: String?
    let suggestedPosture: String?
    let memoSection: String?
    let mitigationOrMonitoring: String?

    enum CodingKeys: String, CodingKey {
        case id, title, description, severity, likelihood, status
        case whyItMatters = "why_it_matters"
        case suggestedPosture = "suggested_posture"
        case memoSection = "memo_section"
        case mitigationOrMonitoring = "mitigation_or_monitoring"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        description = try? c.decodeIfPresent(String.self, forKey: .description)
        whyItMatters = try? c.decodeIfPresent(String.self, forKey: .whyItMatters)
        severity = try? c.decodeIfPresent(String.self, forKey: .severity)
        likelihood = try? c.decodeIfPresent(String.self, forKey: .likelihood)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        suggestedPosture = try? c.decodeIfPresent(String.self, forKey: .suggestedPosture)
        memoSection = try? c.decodeIfPresent(String.self, forKey: .memoSection)
        mitigationOrMonitoring = try? c.decodeIfPresent(String.self, forKey: .mitigationOrMonitoring)
    }

    var severityRank: Int {
        switch severity {
        case "high": return 0
        case "medium": return 1
        default: return 2
        }
    }

    var isOpen: Bool { (status ?? "unresearched") != "researched" }
}

struct MacThesisClaim: Identifiable, Hashable, Decodable {
    let id: String
    let claim: String?
    let detail: String?
    let state: String?
    let sourceTrace: [String]
    let needsStrongerEvidence: Bool?

    enum CodingKeys: String, CodingKey {
        case id, claim, detail, state
        case sourceTrace = "source_trace"
        case needsStrongerEvidence = "needs_stronger_evidence"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        claim = try? c.decodeIfPresent(String.self, forKey: .claim)
        detail = try? c.decodeIfPresent(String.self, forKey: .detail)
        state = try? c.decodeIfPresent(String.self, forKey: .state)
        sourceTrace = (try? c.decodeIfPresent([String].self, forKey: .sourceTrace)) ?? []
        needsStrongerEvidence = try? c.decodeIfPresent(Bool.self, forKey: .needsStrongerEvidence)
    }
}

struct MacThesisSensitivity: Identifiable, Hashable, Decodable {
    let id: String
    let sensitivity: String?
    let supportEvidence: String?
    let downsideImpact: String?
    let recommendationSensitivity: String?

    enum CodingKeys: String, CodingKey {
        case id, sensitivity
        case supportEvidence = "support_evidence"
        case downsideImpact = "downside_impact"
        case recommendationSensitivity = "recommendation_sensitivity"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        sensitivity = try? c.decodeIfPresent(String.self, forKey: .sensitivity)
        supportEvidence = try? c.decodeIfPresent(String.self, forKey: .supportEvidence)
        downsideImpact = try? c.decodeIfPresent(String.self, forKey: .downsideImpact)
        recommendationSensitivity = try? c.decodeIfPresent(String.self, forKey: .recommendationSensitivity)
    }
}

struct MacThesisSpine: Decodable {
    let updatedAt: String?
    let approved: Bool?
    let investmentHighlights: [MacThesisClaim]
    let investmentRisks: [MacThesisClaim]
    let recommendationLogic: String?
    let riskValuationSensitivities: [MacThesisSensitivity]
    let bullCaseMustBeTrue: [String]
    let downsideSensitivities: [String]

    enum CodingKeys: String, CodingKey {
        case approved
        case updatedAt = "updated_at"
        case investmentHighlights = "investment_highlights"
        case investmentRisks = "investment_risks"
        case recommendationLogic = "recommendation_logic"
        case riskValuationSensitivities = "risk_valuation_sensitivities"
        case bullCaseMustBeTrue = "bull_case_must_be_true"
        case downsideSensitivities = "downside_sensitivities"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
        approved = try? c.decodeIfPresent(Bool.self, forKey: .approved)
        investmentHighlights = (try? c.decodeIfPresent([MacThesisClaim].self, forKey: .investmentHighlights)) ?? []
        investmentRisks = (try? c.decodeIfPresent([MacThesisClaim].self, forKey: .investmentRisks)) ?? []
        recommendationLogic = try? c.decodeIfPresent(String.self, forKey: .recommendationLogic)
        riskValuationSensitivities = (try? c.decodeIfPresent([MacThesisSensitivity].self, forKey: .riskValuationSensitivities)) ?? []
        bullCaseMustBeTrue = (try? c.decodeIfPresent([String].self, forKey: .bullCaseMustBeTrue)) ?? []
        downsideSensitivities = (try? c.decodeIfPresent([String].self, forKey: .downsideSensitivities)) ?? []
    }

    var isEmpty: Bool { investmentHighlights.isEmpty && investmentRisks.isEmpty && riskValuationSensitivities.isEmpty }
}

struct MacMemoAnalysis: Decodable {
    let id: String?
    let companyId: String?
    let status: String?
    let approvedForMemo: Bool
    let approvedAt: String?
    let updatedAt: String?
    let tools: [MacMemoTool]
    let readiness: MacReadiness?
    let additionalAreas: [MacReadinessArea]
    let hasUnapprovedWork: Bool
    let risks: [MacRiskCard]
    let thesisSpine: MacThesisSpine?

    enum CodingKeys: String, CodingKey {
        case id, status, tools, readiness, artifacts
        case companyId = "company_id"
        case approvedForMemo = "approved_for_memo"
        case approvedAt = "approved_at"
        case updatedAt = "updated_at"
        case additionalAreas = "additional_areas"
        case hasUnapprovedWork = "has_unapproved_work"
    }

    private enum ArtifactKeys: String, CodingKey {
        case strategicRisks = "strategic_risks"
        case thesisSpine = "thesis_spine"
    }

    private struct RiskMap: Decodable {
        let risks: [MacRiskCard]?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try? c.decodeIfPresent(String.self, forKey: .id)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        approvedForMemo = (try? c.decodeIfPresent(Bool.self, forKey: .approvedForMemo)) ?? false
        approvedAt = try? c.decodeIfPresent(String.self, forKey: .approvedAt)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
        tools = (try? c.decodeIfPresent([MacMemoTool].self, forKey: .tools)) ?? []
        readiness = try? c.decodeIfPresent(MacReadiness.self, forKey: .readiness)
        additionalAreas = (try? c.decodeIfPresent([MacReadinessArea].self, forKey: .additionalAreas)) ?? []
        hasUnapprovedWork = (try? c.decodeIfPresent(Bool.self, forKey: .hasUnapprovedWork)) ?? false
        var risks: [MacRiskCard] = []
        var spine: MacThesisSpine?
        if let artifacts = try? c.nestedContainer(keyedBy: ArtifactKeys.self, forKey: .artifacts) {
            risks = (try? artifacts.decodeIfPresent(RiskMap.self, forKey: .strategicRisks))?.risks ?? []
            spine = try? artifacts.decodeIfPresent(MacThesisSpine.self, forKey: .thesisSpine)
        }
        self.risks = risks
        thesisSpine = spine
    }

    var rankedRisks: [MacRiskCard] {
        risks.sorted { a, b in
            if a.isOpen != b.isOpen { return a.isOpen && !b.isOpen }
            if a.severityRank != b.severityRank { return a.severityRank < b.severityRank }
            return (a.title ?? "") < (b.title ?? "")
        }
    }
}

struct MacReadinessReviewPatch: Encodable {
    struct Item: Encodable {
        let id: String
        let status: String
        let rationale: String
    }
    let items: [Item]
}

// MARK: - Evidence matrix (`/api/companies/{id}/evidence-matrix`)

struct MacEvidenceEntry: Hashable, Decodable {
    let sourceKind: String?
    let filename: String?
    let taskTitle: String?
    let locator: String?
    let excerpt: String?
    let confidence: String?

    enum CodingKeys: String, CodingKey {
        case filename, locator, excerpt, confidence
        case sourceKind = "source_kind"
        case taskTitle = "task_title"
    }
}

struct MacEvidenceClaim: Identifiable, Hashable, Decodable {
    var id: String { claim + "|" + (status ?? "") }
    let claim: String
    let status: String?
    let confidence: String?
    let supportingEvidence: [MacEvidenceEntry]
    let contradictingEvidence: [MacEvidenceEntry]
    let missingEvidence: [String]

    enum CodingKeys: String, CodingKey {
        case claim, status, confidence
        case supportingEvidence = "supporting_evidence"
        case contradictingEvidence = "contradicting_evidence"
        case missingEvidence = "missing_evidence"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        claim = (try? c.decodeIfPresent(String.self, forKey: .claim)) ?? ""
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        confidence = try? c.decodeIfPresent(String.self, forKey: .confidence)
        supportingEvidence = (try? c.decodeIfPresent([MacEvidenceEntry].self, forKey: .supportingEvidence)) ?? []
        contradictingEvidence = (try? c.decodeIfPresent([MacEvidenceEntry].self, forKey: .contradictingEvidence)) ?? []
        missingEvidence = (try? c.decodeIfPresent([String].self, forKey: .missingEvidence)) ?? []
    }

    var statusLabel: String {
        switch status {
        case "supported": return "Supported"
        case "contradicted": return "Contradicted"
        case "partial": return "Partial"
        case "mixed": return "Mixed"
        default: return "Missing"
        }
    }
}

struct MacEvidenceMatrix: Decodable {
    let companyId: String?
    let generatedAt: String?
    let claims: [MacEvidenceClaim]
    let claimCount: Int?

    enum CodingKeys: String, CodingKey {
        case claims
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case claimCount = "claim_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        claims = (try? c.decodeIfPresent([MacEvidenceClaim].self, forKey: .claims)) ?? []
        claimCount = try? c.decodeIfPresent(Int.self, forKey: .claimCount)
    }

    func count(_ status: String) -> Int { claims.filter { $0.status == status }.count }
}

/// Value handed to the IC Review `WindowGroup`.
struct MacICReviewRequest: Codable, Hashable {
    let companyId: String
    let reportId: String
    let language: String
}

// MARK: - Copilot context (`POST /api/companies/{id}/copilot/context`)

/// Client-side context sent with every Ask; mirrors `CopilotContextBody`.
struct MacCopilotContext: Encodable, Equatable {
    var surface: String?
    var tab: String?
    var selection: [String: String] = [:]
    var attention: [String: String] = [:]
    var job: [String: String] = [:]
    var documentIds: [String] = []

    enum CodingKeys: String, CodingKey {
        case surface, tab, selection, attention, job
        case documentIds = "document_ids"
    }

    static let none = MacCopilotContext()

    /// True when the context points at something concrete (a passage, ticker, job, alert),
    /// not just "the research desk"; only then is it worth showing as a chip.
    var isSpecific: Bool {
        !selection.isEmpty || !attention.isEmpty || !job.isEmpty
            || (surface != nil && surface != "research")
    }

    /// Short human label shown as a chip in the chat ("Memo · page 4", "TSM · Market Radar").
    var chipLabel: String? {
        if let text = selection["bullet_text"] ?? selection["claim"] ?? selection["excerpt"], !text.isEmpty {
            return String(text.prefix(60)) + (text.count > 60 ? "…" : "")
        }
        if let title = selection["title"], !title.isEmpty { return String(title.prefix(60)) }
        if let ticker = selection["ticker"], !ticker.isEmpty { return ticker }
        if let title = job["title"], !title.isEmpty { return "Job · " + String(title.prefix(50)) }
        if let kind = attention["kind"], !kind.isEmpty {
            let detail = attention["detail"].map { " · " + String($0.prefix(50)) } ?? ""
            return kind.replacingOccurrences(of: "_", with: " ").capitalized + detail
        }
        if let surface, !surface.isEmpty { return surface.replacingOccurrences(of: "_", with: " ").capitalized }
        return nil
    }

    static func memo(reportId: String, page: Int?, selectionText: String?) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "memo", tab: "memo")
        ctx.selection["report_id"] = reportId
        if let page { ctx.selection["page"] = String(page) }
        if let text = selectionText?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty {
            ctx.selection["target_kind"] = "memo_bullet"
            ctx.selection["bullet_text"] = String(text.prefix(1400))
        }
        return ctx
    }

    static func market(ticker: String) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "market", tab: "market")
        ctx.selection["ticker"] = ticker.uppercased()
        return ctx
    }

    static func news(item: MacNewsItem) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "news", tab: "news")
        ctx.selection["target_kind"] = "report_signal"
        ctx.selection["title"] = item.title
        ctx.selection["signal"] = item.title
        if let s = item.summary { ctx.selection["implication"] = String(s.prefix(600)) }
        if let t = item.ticker { ctx.selection["ticker"] = t }
        if let u = item.url { ctx.selection["url"] = u }
        if let c = item.category { ctx.selection["category"] = c }
        return ctx
    }

    static func attention(kind: String, detail: String?, count: Int?) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "research", tab: "memo")
        ctx.attention["kind"] = kind
        if let detail { ctx.attention["detail"] = detail }
        if let count { ctx.attention["count"] = String(count) }
        return ctx
    }

    static func job(_ job: MacActiveJob) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "jobs", tab: "jobs")
        ctx.job["status"] = job.error == nil ? "running" : "failed"
        if let t = job.title { ctx.job["title"] = t }
        if let k = job.kind { ctx.job["kind"] = k }
        if let e = job.error { ctx.job["error"] = e }
        return ctx
    }

    static func failedJob(_ row: MacJobHistoryRow) -> MacCopilotContext {
        var ctx = MacCopilotContext(surface: "jobs", tab: "jobs")
        ctx.job["status"] = "failed"
        if let t = row.title { ctx.job["title"] = t }
        if let k = row.kind { ctx.job["kind"] = k }
        if let e = row.error { ctx.job["error"] = e }
        return ctx
    }
}

struct MacCopilotAction: Identifiable, Hashable, Decodable {
    let id: String
    let labelKey: String?
    let promptKey: String?

    enum CodingKeys: String, CodingKey {
        case id
        case labelKey = "label_key"
        case promptKey = "prompt_key"
    }

    /// The server hands back i18n keys; the Mac renders them in English.
    var label: String {
        switch id {
        case "trace_sources": return "Trace the sources"
        case "diagnose_job": return "Diagnose this failure"
        case "discuss_selection": return "Discuss this passage"
        case "find_contradictions": return "Find contradictions"
        case "diagnose_memo": return "Why did the memo fail?"
        case "review_warnings": return "Review quality warnings"
        case "resolve_contradictions": return "Resolve contradicted claims"
        case "evidence_gaps": return "Where are the evidence gaps?"
        case "stress_thesis": return "Stress-test the thesis"
        case "draft_update": return "Draft a partner update"
        default: return id.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var prompt: String {
        switch id {
        case "trace_sources": return "Trace the sources behind the selected item. List each source, what it supports, and how confident we should be."
        case "diagnose_job": return "Diagnose why this job failed and tell me the fastest way to get it running again."
        case "discuss_selection": return "Discuss the selected passage: what it claims, what evidence supports it, and what would change our view."
        case "find_contradictions": return "Find anything in our evidence that contradicts the selected passage."
        case "diagnose_memo": return "The memo run failed. Explain the failure and the concrete next step."
        case "review_warnings": return "Walk through the memo's quality warnings and which ones matter for the investment committee."
        case "resolve_contradictions": return "List the contradicted evidence claims and propose how to resolve each one."
        case "evidence_gaps": return "Where are the evidence gaps in our thesis, ranked by how much they could change the decision?"
        case "stress_thesis": return "Stress-test the investment thesis: the three things that must be true, and what breaks it."
        case "draft_update": return "Draft a short partner update on this company: status, what changed, what we need to decide."
        default: return label
        }
    }
}

struct MacProvenanceSource: Identifiable, Hashable, Decodable {
    var id: String { (fileId ?? "") + "|" + (filename ?? "") + "|" + (locator ?? "") + "|" + String((excerpt ?? "").prefix(40)) }
    let fileId: String?
    let filename: String?
    let locator: String?
    let excerpt: String?
    let sourceClass: String?
    let confidence: String?

    enum CodingKeys: String, CodingKey {
        case filename, locator, excerpt, confidence
        case fileId = "file_id"
        case sourceClass = "source_class"
    }
}

struct MacProvenance: Decodable {
    let targetKind: String?
    let label: String?
    let sources: [MacProvenanceSource]
    let gaps: [String]
    let contradictions: [MacProvenanceSource]

    enum CodingKeys: String, CodingKey {
        case label, sources, gaps, contradictions
        case targetKind = "target_kind"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        targetKind = try? c.decodeIfPresent(String.self, forKey: .targetKind)
        label = try? c.decodeIfPresent(String.self, forKey: .label)
        sources = (try? c.decodeIfPresent([MacProvenanceSource].self, forKey: .sources)) ?? []
        gaps = (try? c.decodeIfPresent([String].self, forKey: .gaps)) ?? []
        contradictions = (try? c.decodeIfPresent([MacProvenanceSource].self, forKey: .contradictions)) ?? []
    }
}

struct MacCopilotContextInfo: Decodable {
    let companyId: String?
    let label: String?
    let actions: [MacCopilotAction]
    let provenance: MacProvenance?
    let autoPrompt: String?

    enum CodingKeys: String, CodingKey {
        case label, actions, provenance
        case companyId = "company_id"
        case autoPrompt = "auto_prompt"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        label = try? c.decodeIfPresent(String.self, forKey: .label)
        actions = (try? c.decodeIfPresent([MacCopilotAction].self, forKey: .actions)) ?? []
        provenance = try? c.decodeIfPresent(MacProvenance.self, forKey: .provenance)
        autoPrompt = try? c.decodeIfPresent(String.self, forKey: .autoPrompt)
    }
}

/// What the copilot / console stream yields to the UI.
enum MacCopilotChunk {
    case partial(String)   // a `claude_action/thinking` text block
    case tool(String)      // tool use / result preview, for the activity line
    case final(String)     // the canonical reply from `done.text`
}

// MARK: - Attention queue (`/api/desk/screener`, `/api/desk/digest`, `/api/intake/unresolved`)

struct MacScreenerItem: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let ticker: String?
    let companyId: String?
    let title: String?
    let detail: String?
    let score: Double?

    enum CodingKeys: String, CodingKey {
        case id, kind, ticker, title, detail, score
        case companyId = "company_id"
    }
}

struct MacDigestItem: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let ticker: String?
    let title: String?
    let detail: String?
    let magnitude: Double?
    let href: String?

    var reportId: String? {
        guard let href, href.hasPrefix("bshresearch://report/") else { return nil }
        return String(href.dropFirst("bshresearch://report/".count))
    }
}

struct MacIntakeItem: Identifiable, Hashable, Decodable {
    struct Assignment: Hashable, Decodable {
        let status: String?
        let companyId: String?
        let companyName: String?
        let companyConfidence: Double?
        let reviewReason: String?
        enum CodingKeys: String, CodingKey {
            case status
            case companyId = "company_id"
            case companyName = "company_name"
            case companyConfidence = "company_confidence"
            case reviewReason = "review_reason"
        }
    }

    let id: String
    let kind: String?
    let title: String?
    let createdAt: String?
    let assignment: Assignment?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, assignment
        case createdAt = "created_at"
    }
}

// MARK: - Signal ledger (`/api/signals/ledger`)

struct MacSignal: Identifiable, Hashable, Decodable {
    let id: String
    let recordedAt: String?
    let ticker: String
    let direction: String
    let label: String?
    let source: String?
    let priceAtSignal: Double?
    let lastPrice: Double?
    let returnSincePct: Double?
    let scorePct: Double?

    enum CodingKeys: String, CodingKey {
        case id, ticker, direction, label, source
        case recordedAt = "recorded_at"
        case priceAtSignal = "price_at_signal"
        case lastPrice = "last_price"
        case returnSincePct = "return_since_pct"
        case scorePct = "score_pct"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        recordedAt = try? c.decodeIfPresent(String.self, forKey: .recordedAt)
        ticker = ((try? c.decodeIfPresent(String.self, forKey: .ticker)) ?? "").uppercased()
        direction = (try? c.decodeIfPresent(String.self, forKey: .direction)) ?? "watch"
        label = try? c.decodeIfPresent(String.self, forKey: .label)
        source = try? c.decodeIfPresent(String.self, forKey: .source)
        priceAtSignal = try? c.decodeIfPresent(Double.self, forKey: .priceAtSignal)
        lastPrice = try? c.decodeIfPresent(Double.self, forKey: .lastPrice)
        returnSincePct = try? c.decodeIfPresent(Double.self, forKey: .returnSincePct)
        scorePct = try? c.decodeIfPresent(Double.self, forKey: .scorePct)
    }
}

// MARK: - Console sessions (`/api/companies/{id}/console/*`)

struct MacConsoleSession: Identifiable, Hashable, Decodable {
    let id: String
    let companyId: String?
    let status: String?
    let title: String?
    let createdAt: String?
    let lastUsedAt: String?
    let archivedAt: String?
    let outputLanguage: String?
    let hydrationStatus: String?
    let sessionKind: String?
    let includedFiles: [MacConsoleFile]
    let pctUsed: Double?
    let contextUsed: Int?
    let totalCostUsd: Double?
    let summaryHeadline: String?
    let summaryBullets: [String]

    enum CodingKeys: String, CodingKey {
        case id, status, title, tokens, summary
        case companyId = "company_id"
        case createdAt = "created_at"
        case lastUsedAt = "last_used_at"
        case archivedAt = "archived_at"
        case outputLanguage = "output_language"
        case hydrationStatus = "hydration_status"
        case sessionKind = "session_kind"
        case includedFiles = "included_files"
        case pctUsed = "pct_used"
        case contextUsed = "context_used"
    }

    private struct Tokens: Decodable {
        let totalCostUsd: Double?
        enum CodingKeys: String, CodingKey { case totalCostUsd = "total_cost_usd" }
    }

    private struct Summary: Decodable {
        let headline: String?
        let bullets: [String]?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        createdAt = try? c.decodeIfPresent(String.self, forKey: .createdAt)
        lastUsedAt = try? c.decodeIfPresent(String.self, forKey: .lastUsedAt)
        archivedAt = try? c.decodeIfPresent(String.self, forKey: .archivedAt)
        outputLanguage = try? c.decodeIfPresent(String.self, forKey: .outputLanguage)
        hydrationStatus = try? c.decodeIfPresent(String.self, forKey: .hydrationStatus)
        sessionKind = try? c.decodeIfPresent(String.self, forKey: .sessionKind)
        includedFiles = (try? c.decodeIfPresent([MacConsoleFile].self, forKey: .includedFiles)) ?? []
        pctUsed = try? c.decodeIfPresent(Double.self, forKey: .pctUsed)
        contextUsed = try? c.decodeIfPresent(Int.self, forKey: .contextUsed)
        totalCostUsd = (try? c.decodeIfPresent(Tokens.self, forKey: .tokens))?.totalCostUsd
        let summary = try? c.decodeIfPresent(Summary.self, forKey: .summary)
        summaryHeadline = summary?.headline
        summaryBullets = summary?.bullets ?? []
    }

    var isArchived: Bool { status == "archived" }
    var displayTitle: String { (title?.isEmpty == false ? title : nil) ?? "Session" }
}

struct MacConsoleFile: Identifiable, Hashable, Decodable {
    let id: String
    let kind: String?
    let filename: String?
}

struct MacConsoleTurn: Identifiable, Hashable, Decodable {
    struct Attachment: Hashable, Decodable {
        let id: String?
        let name: String?
    }

    /// Turn ids are shared by the user turn and its reply, so identity includes the role.
    var id: String { turnId + "|" + role }
    let turnId: String
    let ts: String?
    let role: String
    var text: String
    let attachments: [Attachment]
    let durationMs: Int?
    let costUsd: Double?
    let subtype: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ts, id, role, text, attachments, subtype, error
        case durationMs = "duration_ms"
        case costUsd = "cost_usd"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        turnId = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        ts = try? c.decodeIfPresent(String.self, forKey: .ts)
        role = (try? c.decodeIfPresent(String.self, forKey: .role)) ?? "assistant"
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        attachments = (try? c.decodeIfPresent([Attachment].self, forKey: .attachments)) ?? []
        durationMs = try? c.decodeIfPresent(Int.self, forKey: .durationMs)
        costUsd = try? c.decodeIfPresent(Double.self, forKey: .costUsd)
        subtype = try? c.decodeIfPresent(String.self, forKey: .subtype)
        error = try? c.decodeIfPresent(String.self, forKey: .error)
    }

    init(turnId: String, role: String, text: String) {
        self.turnId = turnId
        self.ts = ISO8601DateFormatter().string(from: Date())
        self.role = role
        self.text = text
        self.attachments = []
        self.durationMs = nil
        self.costUsd = nil
        self.subtype = nil
        self.error = nil
    }

    var isUser: Bool { role == "user" }
}

struct MacConsoleAskResult: Decodable {
    let turnId: String
    let queuePosition: Int?
    let streamUrl: String?

    enum CodingKeys: String, CodingKey {
        case turnId = "turn_id"
        case queuePosition = "queue_position"
        case streamUrl = "stream_url"
    }
}
