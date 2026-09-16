import SwiftUI
import Combine

private struct DeskEmptyResponse: Decodable {}

@MainActor
public final class ResearchDeskStore: ObservableObject {
    public static let shared = ResearchDeskStore()

    // MARK: - Published Properties

    @Published public var companies: [MacCompany] = []
    @Published public var reports: [MacReport] = []
    @Published public var selectedCompany: MacCompany?
    @Published public var searchQuery: String = ""
    @Published public var selectedSector: String? = nil
    @Published public var showDiffsOnly: Bool = false

    @Published public var isLoadingCompanies: Bool = false
    @Published public var isLoadingReports: Bool = false
    @Published public var error: String?

    // Company Caches
    @Published public var profileByCompany: [String: MacCompanyProfile] = [:]
    @Published public var signalScoreByCompany: [String: MacSignalScore] = [:]
    @Published public var dealPipelines: [String: MacDealPipeline] = [:]
    @Published public var compsByCompany: [String: MacComps] = [:]
    @Published public var capModelByCompany: [String: MacCapModelPayload] = [:]
    @Published public var founderRadarByCompany: [String: MacFounderRadar] = [:]
    @Published public var vcRatiosByCompany: [String: MacVCRatios] = [:]
    @Published public var decisionsByCompany: [String: [MacDecision]] = [:]
    @Published public var analysisByCompany: [String: MacMemoAnalysis] = [:]
    @Published public var analysisBusy: Set<String> = []
    @Published public var icPrepByCompany: [String: MacICPrepPayload] = [:]
    @Published public var icRoomByCompany: [String: MacICRoomPayload] = [:]
    @Published public var thesisTrackerByCompany: [String: MacThesisTrackerPayload] = [:]
    @Published public var commentsByTarget: [String: [MacComment]] = [:]
    @Published public var visitedCompanyIds: Set<String> = []
    @Published public var followedCompanyIds: [String] = []
    @Published public var visitedCompanyTimestamps: [String: Date] = [:]
    @Published public var previousVisitByCompany: [String: Date] = [:]
    @Published public var intakeDeckURL: URL? = nil
    @Published public var intakeResult: MacIntakeResult? = nil
    @Published public var intakeBusy: Bool = false

    public init() {
        loadVisitedCompanies()
        loadFollowedCompanies()
        hydrateInitialData()
    }

    private func hydrateInitialData() {
        let decoder = JSONDecoder()
        if let cached = APIResponseCache.shared.load(for: APIResponseCache.cacheKey(path: "companies")),
           let list = try? decoder.decode([MacCompany].self, from: cached), !list.isEmpty {
            self.companies = list
        } else {
            self.companies = BSHResearchSeedData.companies
        }

        if let cachedReps = APIResponseCache.shared.load(for: APIResponseCache.cacheKey(path: "reports")),
           let list = try? decoder.decode([MacReport].self, from: cachedReps), !list.isEmpty {
            self.reports = list
        } else {
            self.reports = BSHResearchSeedData.reports
        }

        self.profileByCompany = BSHResearchSeedData.profiles
        self.dealPipelines = BSHResearchSeedData.dealPipelines

        if selectedCompany == nil {
            selectedCompany = companies.first
        }
    }

    // MARK: - Computed Filtered Companies

    public var sectors: [String] {
        var s = Set<String>()
        for c in companies {
            if let sec = c.sector, !sec.isEmpty {
                s.insert(sec)
            }
        }
        return s.sorted()
    }

    public var filteredCompanies: [MacCompany] {
        var result = companies
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !q.isEmpty {
            result = result.filter { c in
                (c.name?.lowercased().contains(q) == true) ||
                (c.ticker?.lowercased().contains(q) == true) ||
                (c.sector?.lowercased().contains(q) == true) ||
                c.id.lowercased().contains(q)
            }
        }
        if let sector = selectedSector, !sector.isEmpty, sector != "All" {
            result = result.filter { $0.sector == sector }
        }
        if showDiffsOnly {
            result = result.filter { hasDiff($0.id) }
        }
        return result
    }

    public func hasDiff(_ companyId: String) -> Bool {
        // Unvisited or updated since last visit
        !visitedCompanyIds.contains(companyId)
    }

    public func loadAll() async {
        await loadData()
    }

    public func selectCompany(id: String) async {
        if companies.isEmpty {
            await loadData()
        }
        if let match = companies.first(where: { $0.id == id || $0.ticker?.uppercased() == id.uppercased() }) {
            selectedCompany = match
            markVisited(match.id)
            await fetchReports()
        }
    }

    public func markVisited(_ companyId: String) {
        visitedCompanyIds.insert(companyId)
        UserDefaults.standard.set(Array(visitedCompanyIds), forKey: "bsh.visitedCompanies")
    }

    public func markCompanyVisited(_ companyId: String) {
        if let current = visitedCompanyTimestamps[companyId], previousVisitByCompany[companyId] == nil {
            previousVisitByCompany[companyId] = current
        }
        visitedCompanyTimestamps[companyId] = Date()
        markVisited(companyId)
    }

    private func visitBaseline(for companyId: String) -> Date? {
        previousVisitByCompany[companyId] ?? visitedCompanyTimestamps[companyId]
    }

    public func isCompanyModified(_ companyId: String) -> Bool {
        guard let baseline = visitBaseline(for: companyId) else {
            return true
        }
        let compReports = reports(for: companyId)
        let f = ISO8601DateFormatter()
        for r in compReports {
            if let dateStr = r.updatedAt ?? r.createdAt,
               let d = f.date(from: dateStr),
               d > baseline {
                return true
            }
        }
        return false
    }

    public func isReportNew(_ report: MacReport) -> Bool {
        guard let cid = report.companyId, let baseline = visitBaseline(for: cid) else {
            return true
        }
        let f = ISO8601DateFormatter()
        if let dateStr = report.updatedAt ?? report.createdAt,
           let d = f.date(from: dateStr),
           d > baseline {
            return true
        }
        return false
    }

    private func loadVisitedCompanies() {
        if let list = UserDefaults.standard.stringArray(forKey: "bsh.visitedCompanies") {
            visitedCompanyIds = Set(list)
        }
    }

    public func isFollowed(_ companyId: String) -> Bool {
        followedCompanyIds.contains(companyId)
    }

    public func toggleFollow(_ companyId: String) {
        if let idx = followedCompanyIds.firstIndex(of: companyId) {
            followedCompanyIds.remove(at: idx)
        } else {
            followedCompanyIds.append(companyId)
        }
        UserDefaults.standard.set(followedCompanyIds, forKey: "bsh.followedCompanies")
    }

    private func loadFollowedCompanies() {
        if let list = UserDefaults.standard.stringArray(forKey: "bsh.followedCompanies") {
            followedCompanyIds = list
        }
    }

    public func reports(for companyId: String) -> [MacReport] {
        reports.filter { $0.companyId == companyId }
    }

    public func latestDecision(for companyId: String) -> MacDecision? {
        decisionsByCompany[companyId]?.first
    }

    public func stage(for companyId: String) -> MacLifecycleStage {
        MacLifecycleStage.derive(row: nil, latestDecision: latestDecision(for: companyId))
    }

    // MARK: - Networking Methods

    public func loadData() async {
        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.fetchCompanies() }
            group.addTask { await self.fetchReports() }
        }
    }

    public func fetchCompanies() async {
        isLoadingCompanies = true
        defer { isLoadingCompanies = false }
        do {
            let list: [MacCompany] = try await APIClient.shared.get("companies")
            if !list.isEmpty {
                self.companies = list.sorted { ($0.name ?? $0.id).localizedCaseInsensitiveCompare($1.name ?? $1.id) == .orderedAscending }
                if let data = try? JSONEncoder().encode(list) {
                    APIResponseCache.shared.save(data: data, for: APIResponseCache.cacheKey(path: "companies"))
                }
            }
            if selectedCompany == nil, let first = self.companies.first {
                selectedCompany = first
            }
        } catch {
            self.error = error.localizedDescription
            if self.companies.isEmpty {
                self.companies = BSHResearchSeedData.companies
                if selectedCompany == nil { selectedCompany = self.companies.first }
            }
        }
    }

    public func fetchReports() async {
        isLoadingReports = true
        defer { isLoadingReports = false }
        do {
            let list: [MacReport] = try await APIClient.shared.get("reports", query: [URLQueryItem(name: "lite", value: "1")])
            if !list.isEmpty {
                self.reports = list
                if let data = try? JSONEncoder().encode(list) {
                    APIResponseCache.shared.save(data: data, for: APIResponseCache.cacheKey(path: "reports"))
                }
            }
        } catch {
            self.error = error.localizedDescription
            if self.reports.isEmpty {
                self.reports = BSHResearchSeedData.reports
            }
        }
    }

    public func fetchReports(for companyId: String?) async {
        await fetchReports()
    }

    public func loadProfile(for companyId: String) async {
        do {
            let profile: MacCompanyProfile = try await APIClient.shared.get("companies/\(companyId)/profile")
            self.profileByCompany[companyId] = profile
        } catch {
            if profileByCompany[companyId] == nil, let seed = BSHResearchSeedData.profiles[companyId] {
                self.profileByCompany[companyId] = seed
            }
        }
    }

    public func loadSignalScore(for companyId: String) async {
        do {
            let score: MacSignalScore = try await APIClient.shared.get("companies/\(companyId)/signal-score")
            self.signalScoreByCompany[companyId] = score
        } catch {
            // Signal score optional
        }
    }

    public func fetchDealPipeline(for companyId: String) async {
        do {
            let p: MacDealPipeline = try await APIClient.shared.get("companies/\(companyId)/deal-pipeline")
            self.dealPipelines[companyId] = p
        } catch {
            if dealPipelines[companyId] == nil {
                if let seed = BSHResearchSeedData.dealPipelines[companyId] {
                    dealPipelines[companyId] = seed
                } else {
                    dealPipelines[companyId] = MacDealPipeline(
                        companyId: companyId,
                        stage: "Sourced",
                        stages: ["Sourced", "Partner Intro", "Technical Diligence", "Term Sheet / IC", "Portfolio"],
                        dealLead: nil,
                        warmthScore: 65,
                        introPath: nil,
                        daysInStage: 3,
                        lastTouchpoint: nil,
                        nextStep: nil,
                        updatedAt: nil
                    )
                }
            }
        }
    }

    public func updateDealPipeline(companyId: String, stage: String, dealLead: String?, warmthScore: Int?, nextStep: String?) async {
        struct UpdateBody: Encodable {
            let stage: String
            let dealLead: String?
            let warmthScore: Int?
            let nextStep: String?
            enum CodingKeys: String, CodingKey {
                case stage
                case dealLead = "deal_lead"
                case warmthScore = "warmth_score"
                case nextStep = "next_step"
            }
        }
        let body = UpdateBody(stage: stage, dealLead: dealLead, warmthScore: warmthScore, nextStep: nextStep)
        if var existing = dealPipelines[companyId] {
            existing.stage = stage
            existing.dealLead = dealLead
            existing.warmthScore = warmthScore
            existing.nextStep = nextStep
            dealPipelines[companyId] = existing
        }
        let _: DeskEmptyResponse? = try? await APIClient.shared.put("companies/\(companyId)/deal-pipeline", body: body)
    }

    public func fetchComps(for companyId: String) async {
        do {
            let comps: MacComps = try await APIClient.shared.get("companies/\(companyId)/comps")
            self.compsByCompany[companyId] = comps
        } catch {
            // Comps optional
        }
    }

    public func fetchCapModel(for companyId: String) async {
        do {
            let model: MacCapModelPayload = try await APIClient.shared.get("companies/\(companyId)/cap-model")
            self.capModelByCompany[companyId] = model
        } catch {
            // Optional
        }
    }

    public func saveCapModel(for companyId: String, inputs: MacCapModelInputs) async {
        struct SaveCapBody: Encodable {
            let inputs: MacCapModelInputs
        }
        let body = SaveCapBody(inputs: inputs)
        if let updated: MacCapModelPayload = try? await APIClient.shared.post("companies/\(companyId)/cap-model", body: body) {
            self.capModelByCompany[companyId] = updated
        }
    }

    public func fetchFounderRadar(for companyId: String) async {
        do {
            let radar: MacFounderRadar = try await APIClient.shared.get("companies/\(companyId)/founder-radar")
            self.founderRadarByCompany[companyId] = radar
        } catch {
            // Optional
        }
    }

    public func fetchVCRatios(for companyId: String) async {
        do {
            let ratios: MacVCRatios = try await APIClient.shared.get("companies/\(companyId)/vc-ratios")
            self.vcRatiosByCompany[companyId] = ratios
        } catch {
            // Optional
        }
    }

    public func fetchDecisions(for companyId: String) async {
        do {
            let list: [MacDecision] = try await APIClient.shared.get("companies/\(companyId)/decisions")
            self.decisionsByCompany[companyId] = list
        } catch {
            // Optional
        }
    }

    public func recordDecision(
        companyId: String,
        verdict: String,
        explanation: String,
        decidedAt: Date? = nil,
        reportId: String? = nil,
        checkSizeMusd: Double? = nil,
        targetOwnershipPct: Double? = nil
    ) async -> Bool {
        struct DecisionBody: Encodable {
            let verdict: String
            let explanation: String
            let decidedAt: String?
            let reportId: String?
            let checkSizeMusd: Double?
            let targetOwnershipPct: Double?
            enum CodingKeys: String, CodingKey {
                case verdict, explanation
                case decidedAt = "decided_at"
                case reportId = "report_id"
                case checkSizeMusd = "check_size_musd"
                case targetOwnershipPct = "target_ownership_pct"
            }
        }
        let dateStr = decidedAt.map { ISO8601DateFormatter().string(from: $0) }
        let body = DecisionBody(
            verdict: verdict,
            explanation: explanation,
            decidedAt: dateStr,
            reportId: reportId,
            checkSizeMusd: checkSizeMusd,
            targetOwnershipPct: targetOwnershipPct
        )
        if let created: MacDecision = try? await APIClient.shared.post("companies/\(companyId)/decisions", body: body) {
            var current = decisionsByCompany[companyId] ?? []
            current.insert(created, at: 0)
            decisionsByCompany[companyId] = current
            return true
        }
        return false
    }

    public func fetchICPrep(for companyId: String) async {
        do {
            let payload: MacICPrepPayload = try await APIClient.shared.get("companies/\(companyId)/ic-prep")
            self.icPrepByCompany[companyId] = payload
        } catch {
            // Optional
        }
    }

    public func fetchICRoom(for companyId: String) async {
        do {
            let payload: MacICRoomPayload = try await APIClient.shared.get("companies/\(companyId)/ic-room")
            self.icRoomByCompany[companyId] = payload
        } catch {
            // Optional
        }
    }

    public func fetchThesisTracker(for companyId: String) async {
        do {
            let payload: MacThesisTrackerPayload = try await APIClient.shared.get("companies/\(companyId)/thesis-tracker")
            self.thesisTrackerByCompany[companyId] = payload
        } catch {
            // Optional
        }
    }

    public func fetchAnalysis(for companyId: String) async {
        do {
            let analysis: MacMemoAnalysis = try await APIClient.shared.get("companies/\(companyId)/memo-analysis")
            self.analysisByCompany[companyId] = analysis
        } catch {
            // Optional
        }
    }

    public func fetchComments(for targetKind: String, ref: String) async {
        let key = "\(targetKind):\(ref)"
        do {
            let query = [URLQueryItem(name: "target_kind", value: targetKind), URLQueryItem(name: "target_ref", value: ref)]
            let list: [MacComment] = try await APIClient.shared.get("comments", query: query)
            self.commentsByTarget[key] = list
        } catch {
            // Optional
        }
    }

    public func fetchComments(for target: MacCommentTarget) async {
        await fetchComments(for: target.kind, ref: target.ref)
    }

    public func fetchComments(for companyId: String) async {
        await fetchComments(for: "company", ref: companyId)
    }

    public func addComment(targetKind: String, ref: String, content: String, author: String) async {
        let key = "\(targetKind):\(ref)"
        struct CommentBody: Encodable {
            let author: String
            let content: String
            let targetKind: String
            let targetRef: String
            enum CodingKeys: String, CodingKey {
                case author, content
                case targetKind = "target_kind"
                case targetRef = "target_ref"
            }
        }
        let body = CommentBody(author: author, content: content, targetKind: targetKind, targetRef: ref)
        if let created: MacComment = try? await APIClient.shared.post("comments", body: body) {
            var current = commentsByTarget[key] ?? []
            current.append(created)
            commentsByTarget[key] = current
        }
    }

    public func addComment(companyId: String, body: String, target: MacCommentTarget) async {
        await addComment(targetKind: target.kind, ref: target.ref, content: body, author: "Analyst")
    }

    public func generateCustomReport(
        companyId: String,
        reportType: String,
        audience: String,
        language: String,
        prompt: String?
    ) async throws -> MacReport {
        struct ReportGenBody: Encodable {
            let companyId: String
            let reportType: String
            let audience: String
            let language: String
            let prompt: String?
            enum CodingKeys: String, CodingKey {
                case audience, language, prompt
                case companyId = "company_id"
                case reportType = "report_type"
            }
        }
        let body = ReportGenBody(companyId: companyId, reportType: reportType, audience: audience, language: language, prompt: prompt)
        let newReport: MacReport = try await APIClient.shared.post("reports", body: body)
        self.reports.removeAll { $0.id == newReport.id }
        self.reports.insert(newReport, at: 0)
        return newReport
    }

    public func startMemoStudioInvestigate(companyId: String, reportType: String? = nil) async throws -> MacReport {
        struct StudioBody: Encodable {
            let companyId: String
            let reportType: String?
            enum CodingKeys: String, CodingKey {
                case companyId = "company_id"
                case reportType = "report_type"
            }
        }
        let rep: MacReport = try await APIClient.shared.post(
            "memos/studio/investigate",
            body: StudioBody(companyId: companyId, reportType: reportType)
        )
        self.reports.removeAll { $0.id == rep.id }
        self.reports.insert(rep, at: 0)
        await fetchReports(for: companyId)
        return rep
    }

    public func launchCustomReport(
        companyId: String,
        config: MacReportCustomizerConfig
    ) async throws -> MacReport {
        let rep: MacReport
        if config.generationMode == "studio_review" {
            rep = try await startMemoStudioInvestigate(
                companyId: companyId,
                reportType: config.reportType
            )
        } else {
            // Map Archetype display names to backend keys
            var resolvedType = config.reportType
            if resolvedType == "Market & Competitive Analysis" {
                resolvedType = "Market Analysis"
            } else if resolvedType == "Background Dossier" {
                resolvedType = "Background"
            }

            // Map Audience display names to backend keys
            var resolvedAudience = config.audience
            if resolvedAudience.contains("Internal") {
                resolvedAudience = "Internal"
            } else if resolvedAudience.contains("Partner") {
                resolvedAudience = "Partner"
            } else if resolvedAudience.contains("LP") {
                resolvedAudience = "LP"
            } else if resolvedAudience.contains("Associate") || resolvedAudience.contains("Assistant") {
                resolvedAudience = "Assistant"
            }

            let resolvedLanguage = config.language == "zh" ? "zh" : "en"

            struct ReportGenBody: Encodable {
                let companyId: String
                let reportType: String
                let audience: String
                let language: String
                let reportMode: String
                let quality: String
                let prompt: String?
                let directives: String?
                let focusPillars: [String]
                let companyTypeLens: String
                let selectedDocumentIds: [String]

                enum CodingKeys: String, CodingKey {
                    case audience, language, prompt, quality, directives
                    case companyId = "company_id"
                    case reportType = "report_type"
                    case reportMode = "report_mode"
                    case focusPillars = "focus_pillars"
                    case companyTypeLens = "company_type_lens"
                    case selectedDocumentIds = "selected_document_ids"
                }
            }

            let promptText = config.customPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
            let promptVal = promptText.isEmpty ? nil : promptText

            let body = ReportGenBody(
                companyId: companyId,
                reportType: resolvedType,
                audience: resolvedAudience,
                language: resolvedLanguage,
                reportMode: config.reportMode,
                quality: config.quality,
                prompt: promptVal,
                directives: promptVal,
                focusPillars: config.focusPillars,
                companyTypeLens: config.companyTypeLens,
                selectedDocumentIds: config.selectedDocumentIds
            )
            rep = try await APIClient.shared.post("reports", body: body)
            self.reports.removeAll { $0.id == rep.id }
            self.reports.insert(rep, at: 0)
            await fetchReports(for: companyId)
        }
        return rep
    }

    public func generateReportFromStudio(reportId: String) async throws -> MacReport {
        let rep: MacReport = try await APIClient.shared.post("memos/studio/\(reportId)/generate")
        await fetchReports()
        return rep
    }

    public func intakeDeck(fileURL: URL, companyName: String? = nil, companyId: String? = nil) async -> MacIntakeResult? {
        intakeBusy = true
        defer { intakeBusy = false }
        do {
            let data = try Data(contentsOf: fileURL)
            let boundary = "bsh-\(UUID().uuidString)"
            var body = Data()
            func append(_ s: String) { body.append(s.data(using: .utf8)!) }
            if let companyName, !companyName.isEmpty {
                append("--\(boundary)\r\nContent-Disposition: form-data; name=\"company_name\"\r\n\r\n\(companyName)\r\n")
            }
            if let companyId, !companyId.isEmpty {
                append("--\(boundary)\r\nContent-Disposition: form-data; name=\"company_id\"\r\n\r\n\(companyId)\r\n")
            }
            let filename = fileURL.lastPathComponent
            let mimeType = fileURL.pathExtension.lowercased() == "pdf" ? "application/pdf" : "application/octet-stream"
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: \(mimeType)\r\n\r\n")
            body.append(data)
            append("\r\n--\(boundary)--\r\n")

            let url = AppConfig.baseURL.appendingPathComponent("api/intake/decks")
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.timeoutInterval = 120
            req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            req.setValue("ios", forHTTPHeaderField: "X-BSH-Client")
            if let token = TokenStore.read() {
                req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            req.httpBody = body
            let (respData, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw APIError.http(status: (response as? HTTPURLResponse)?.statusCode ?? -1, detail: "Failed to upload deck")
            }
            let result = try JSONDecoder().decode(MacIntakeResult.self, from: respData)
            self.intakeResult = result
            await loadData()
            return result
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    public func summarizeFile(companyId: String, fileId: String) async {
        struct EmptyBody: Encodable {}
        let _: DeskEmptyResponse? = try? await APIClient.shared.post("companies/\(companyId)/files/\(fileId)/summary", body: EmptyBody())
    }
}

// MARK: - Extension for MacDealPipeline init
extension MacDealPipeline {
    init(
        companyId: String,
        stage: String,
        stages: [String],
        dealLead: String?,
        warmthScore: Int?,
        introPath: String?,
        daysInStage: Int,
        lastTouchpoint: String?,
        nextStep: String?,
        updatedAt: String?
    ) {
        self.companyId = companyId
        self.stage = stage
        self.stages = stages
        self.dealLead = dealLead
        self.warmthScore = warmthScore
        self.introPath = introPath
        self.daysInStage = daysInStage
        self.lastTouchpoint = lastTouchpoint
        self.nextStep = nextStep
        self.updatedAt = updatedAt
    }
}
