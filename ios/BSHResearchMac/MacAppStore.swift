import AppKit
import Combine
import Foundation
import UserNotifications

enum MacBlotterTab: String, CaseIterable, Identifiable {
    case jobs
    case alerts
    case signals
    var id: String { rawValue }
}

/// One shared store for every window (main desks, memo windows, Settings).
@MainActor
final class MacAppStore: ObservableObject {
    // MARK: - Navigation & Active Tab
    @Published var selectedTab: MacTab = .home
    @Published var showBlotter = false
    @Published var blotterTab: MacBlotterTab = .jobs
    @Published var showCommandPalette = false
    @Published var commandPaletteSeed = ""
    @Published var showNewReportSheet = false
    @Published var newReportCompany: MacCompany?
    @Published var showLoginSheet = false

    /// Set by the root view: opens a memo `WindowGroup` window for a request.
    var openMemoWindow: ((MacMemoWindowRequest) -> Void)?
    /// Set by the root view: opens an IC Review window (memo + thesis + decision form).
    var openICWindow: ((MacICReviewRequest) -> Void)?

    // MARK: - Pipeline, decisions, IC prep, portfolio
    @Published private(set) var rollup: MacRollup?
    @Published private(set) var followedCompanyIds: [String] = []
    @Published private(set) var decisionsByCompany: [String: [MacDecision]] = [:]
    @Published private(set) var pipelineLoading = false
    @Published private(set) var pipelineSyncing = false
    @Published private(set) var pipelineLoadedAt: Date?
    @Published var showDecisionSheet = false
    @Published var decisionTarget: MacCompany?
    @Published var decisionSeedReportId: String?
    @Published private(set) var trackingByCompany: [String: MacTrackingUpdates] = [:]
    @Published private(set) var trackingBusy: Set<String> = []
    @Published private(set) var analysisByCompany: [String: MacMemoAnalysis] = [:]
    @Published private(set) var analysisBusy: Set<String> = []
    @Published private(set) var evidenceByCompany: [String: MacEvidenceMatrix] = [:]

    // MARK: - Session
    @Published private(set) var session: MacSession?
    @Published private(set) var authChecked = false
    @Published var authError: String?
    @Published private(set) var signingIn = false

    // MARK: - Companies & Reports
    @Published private(set) var companies: [MacCompany] = []
    @Published private(set) var reports: [MacReport] = []
    @Published private(set) var companyDetailsCache: [String: MacCompany] = [:]
    @Published private(set) var companyReportsCache: [String: [MacReport]] = [:]
    @Published var selectedCompany: MacCompany?
    @Published var selectedReport: MacReport?

    // MARK: - Market Radar & Quotes
    @Published private(set) var watchlist: [MacQuote] = []
    @Published private(set) var gainers: [MacQuote] = []
    @Published private(set) var losers: [MacQuote] = []
    @Published private(set) var indicesQuotes: [MacQuote] = []
    @Published var selectedTicker: String?
    @Published var selectedChart: MacChartPayload?
    @Published var selectedWorkspace: MacQuoteWorkspace?
    @Published var selectedChartRange: MacChartRange = .d1
    @Published var loadingChart = false

    // MARK: - Desk Preferences (Syncs with Web & iPadOS)
    @Published private(set) var pinnedTickers: [String] = MacAPIClient.defaultWatchlist
    @Published private(set) var bookLots: [MacBookLot] = []
    @Published private(set) var alertRules: [MacAlertRule] = []
    @Published private(set) var deskPrefsLoaded = false

    // MARK: - News, Jobs, Alerts & Pulse
    @Published private(set) var news: [MacNewsItem] = []
    @Published private(set) var activeJobs: [MacActiveJob] = []
    @Published private(set) var jobHistory: [MacJobHistoryRow] = []
    @Published private(set) var jobLogs: [String: [String]] = [:]
    @Published var selectedJobId: String?
    @Published private(set) var alertEvents: [MacAlertEvent] = []
    @Published private(set) var lastAlertCheck: Date?
    @Published private(set) var checkingAlerts = false
    @Published private(set) var pulse: MacPulseBrief?
    @Published private(set) var marketPulsePayload: MacMarketPulsePayload?
    @Published var pulseLanguage: String = "en"

    // MARK: - Documents desk inline reader & iPad annotation overlay
    @Published var openDocumentURL: URL?
    @Published var openDocumentIsPDF = false
    @Published var openReportTitle = ""
    @Published var openReportId = ""
    @Published var readerLanguage = "en"
    @Published var openDocumentOverlayData: Data?
    @Published var showAnnotationOverlay = true
    @Published private(set) var openingMemo = false

    // MARK: - Copilot (Ask Warren)
    @Published var copilotMessages: [MacCopilotMessage] = []
    @Published var copilotPersona: MacCopilotPersona = .warren
    @Published var copilotDraft: String = ""
    @Published var copilotStreaming = false
    @Published var copilotCurrentThinking: String?
    /// What's on screen for the next Ask — set by desks, shown as a chip, sent with the prompt.
    @Published var copilotContext: MacCopilotContext = .none
    @Published private(set) var copilotContextInfo: MacCopilotContextInfo?
    @Published var copilotDeepMode = false

    // MARK: - Attention queue
    @Published private(set) var screenerItems: [MacScreenerItem] = []
    @Published private(set) var digestItems: [MacDigestItem] = []
    @Published private(set) var intakeItems: [MacIntakeItem] = []
    @Published private(set) var attentionLoadedAt: Date?
    @Published private(set) var attentionLoading = false

    // MARK: - Signal ledger
    @Published private(set) var signals: [MacSignal] = []
    @Published private(set) var signalsLoading = false
    @Published var signalSeedTicker: String?

    // MARK: - Console sessions (persistent, per company)
    @Published private(set) var consoleSessions: [String: [MacConsoleSession]] = [:]
    @Published private(set) var consoleTurns: [String: [MacConsoleTurn]] = [:]
    @Published var consoleSelectedSessionId: String?
    @Published private(set) var consoleStreamingTurn: (sessionId: String, turnId: String)?
    @Published private(set) var consoleActivity: String?
    private var consoleTask: Task<Void, Never>?

    // MARK: - Embedded Web Browser Panel (Cursor Style)
    @Published var showBrowserPanel: Bool = false
    @Published var browserCurrentURL: URL = MacConfig.baseURL

    // MARK: - Terminal Polish, Command Palette & Shortcuts
    @Published var showShortcutSheet: Bool = false
    @Published var showDeckIntakeSheet: Bool = false
    @Published var droppedDeckURL: URL? = nil
    @Published var isOfflineMode: Bool = false
    @Published var lastSyncDate: Date? = nil
    @Published var visitedCompanyTimestamps: [String: Date] = [:]
    @Published var showOnlyModifiedCompanies: Bool = false

    // MARK: - Founder Dossiers & Deep Search (Harmonic/Ampersand Grade)
    @Published var founderDossiers: [String: MacFounderDossier] = [:]
    @Published var deepSearchingFounders: Set<String> = []

    // MARK: - Deal Pipeline & CRM (Affinity Grade)
    @Published var dealPipelines: [String: MacDealPipeline] = [:]

    // MARK: - General Status
    @Published private(set) var loading = false
    @Published var error: String?

    private var tempFiles: [URL] = []
    private var copilotTask: Task<Void, Never>?
    private var jobPollTask: Task<Void, Never>?
    private var alertLoopTask: Task<Void, Never>?
    private var logTailTasks: [String: Task<Void, Never>] = [:]
    private var knownActiveMemoReports: Set<String> = []
    private var bootstrapped = false

    init() {
        hydrateFromCache()
    }

    func hydrateFromCache() {
        if let cos = MacDataCache.shared.loadCompanies(), !cos.isEmpty {
            self.companies = cos
            self.selectedCompany = cos.first
        }
        if let reps = MacDataCache.shared.loadReports(), !reps.isEmpty {
            self.reports = reps
            self.selectedReport = reps.first
        }
        if let qs = MacDataCache.shared.loadQuotes(), !qs.isEmpty {
            self.watchlist = qs
        }
        if let ns = MacDataCache.shared.loadNews(), !ns.isEmpty {
            self.news = ns
        }
        if let p = MacDataCache.shared.loadPulse() {
            self.pulse = p
        }
        self.visitedCompanyTimestamps = MacDataCache.shared.loadBaselines()
        self.lastSyncDate = MacDataCache.shared.lastSyncDate()
    }

    // MARK: - Computed Properties

    var recentReports: [MacReport] {
        reports
            .sorted { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
            .prefix(25)
            .map { $0 }
    }

    var runningReports: [MacReport] {
        reports.filter { !$0.isComplete && !$0.isFailed && !($0.status ?? "").isEmpty }
    }

    /// True once the server has told us who we are (or accepted us as local dev).
    var isSignedIn: Bool { session != nil }

    /// RBAC check mirroring `product_store.ROLE_PERMISSIONS`. Unknown → read-only.
    func can(_ permission: String) -> Bool {
        session?.permissions.contains(permission) ?? false
    }

    var canRunTasks: Bool { can("tasks:action") }
    var canWriteDesk: Bool { can("desk:write") }
    var canEditSources: Bool { can("sources:edit") }
    var canDeleteDocuments: Bool { can("documents:delete") }

    // MARK: - Bootstrap & Refresh

    func bootstrap() async {
        await refreshSession()
        await refreshDeskPrefs()
        await refreshHome()
        await refreshMarket()
        await refreshNews()
        await refreshPulse()
        if selectedCompany == nil, let first = companies.first {
            selectedCompany = first
            if let t = first.ticker, !t.isEmpty {
                selectTicker(t)
            }
        }
        await loadPipeline()
        if !bootstrapped {
            bootstrapped = true
            startBackgroundLoops()
        }
    }

    // MARK: - Session

    func refreshSession() async {
        do {
            session = try await MacAPIClient.shared.me()
            authChecked = true
            if session?.mustReset == true {
                authError = "Your password must be reset on the web before continuing."
            }
        } catch MacAPIError.unauthorized {
            // A stored token the server no longer honours is useless — drop it.
            MacConfig.clearToken()
            session = nil
            authChecked = true
            showLoginSheet = true
        } catch {
            // Offline / server down: keep whatever we had; the desks surface their own errors.
            authChecked = true
        }
    }

    func signIn(email: String, password: String) async {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !password.isEmpty else {
            authError = "Enter your email and password."
            return
        }
        signingIn = true
        authError = nil
        defer { signingIn = false }
        do {
            let res = try await MacAPIClient.shared.login(email: trimmed, password: password)
            MacConfig.writeToken(res.token)
            await refreshSession()
            if session != nil {
                showLoginSheet = false
                await bootstrap()
            }
        } catch {
            authError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func signOut() async {
        try? await MacAPIClient.shared.logout()
        MacConfig.clearToken()
        session = nil
        await refreshSession()
        if session != nil {
            // Local anon-dev keeps working without a user; reload as that identity.
            await bootstrap()
        }
    }

    func refreshHome() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let cos = MacAPIClient.shared.listCompanies()
            async let reps = MacAPIClient.shared.listReports()
            async let jobs = MacAPIClient.shared.fetchActiveJobs()
            async let pulsePayload = MacAPIClient.shared.fetchMarketPulsePayload()
            async let indices = MacAPIClient.shared.fetchQuotes(tickers: ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT"])

            companies = try await cos.sorted {
                ($0.name ?? $0.id).localizedCaseInsensitiveCompare($1.name ?? $1.id) == .orderedAscending
            }
            reports = try await reps
            applyActiveJobs((try? await jobs) ?? [])
            marketPulsePayload = try? await pulsePayload
            indicesQuotes = (try? await indices) ?? []

            if selectedCompany == nil, let first = companies.first {
                selectedCompany = first
            }
            if selectedReport == nil, let firstReport = recentReports.first {
                selectedReport = firstReport
            }

            preloadAllCompanyData()
            MacDataCache.shared.saveCompanies(companies)
            MacDataCache.shared.saveReports(reports)
            lastSyncDate = Date()
            isOfflineMode = false
        } catch MacAPIError.unauthorized {
            session = nil
            showLoginSheet = true
        } catch {
            self.error = error.localizedDescription
            self.isOfflineMode = true
        }
    }

    func refreshReports() async {
        if let reps = try? await MacAPIClient.shared.listReports() {
            reports = reps
        }
    }

    private func preloadAllCompanyData() {
        let targets = self.companies
        guard !targets.isEmpty else { return }
        Task.detached(priority: .utility) {
            let chunkSize = 6
            for chunkIndex in stride(from: 0, to: targets.count, by: chunkSize) {
                let end = min(chunkIndex + chunkSize, targets.count)
                let chunk = targets[chunkIndex..<end]
                await withTaskGroup(of: (String, MacCompany?, [MacReport]?).self) { group in
                    for comp in chunk {
                        group.addTask {
                            let cid = comp.id
                            async let cTask: MacCompany? = try? await MacAPIClient.shared.getCompany(id: cid)
                            async let rTask: [MacReport]? = try? await MacAPIClient.shared.listCompanyReports(companyId: cid)
                            let (c, r) = await (cTask, rTask)
                            return (cid, c, r)
                        }
                    }
                    for await (cid, c, r) in group {
                        await MainActor.run {
                            if let c { self.companyDetailsCache[cid] = c }
                            if let r { self.companyReportsCache[cid] = r }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Windows & navigation helpers

    /// Open a memo in its own window (one window per report + language).
    func openReportWindow(_ report: MacReport, language: String? = nil) {
        selectedReport = report
        let request = MacMemoWindowRequest(reportId: report.id, language: language ?? readerLanguage)
        if let openMemoWindow {
            openMemoWindow(request)
        } else {
            // No window opener yet (very early launch) — fall back to the Documents desk.
            selectedTab = .documents
            Task { await openMemo(report, language: request.language) }
        }
    }

    /// Back-compat name used by desk views.
    func openReportInViewer(_ report: MacReport, language: String = "en") {
        openReportWindow(report, language: language)
    }

    func showCompany(_ company: MacCompany) {
        selectCompany(company)
        selectedTab = .research
    }

    func showTicker(_ ticker: String) {
        selectTicker(ticker)
        selectedTab = .market
    }

    func requestNewReport(for company: MacCompany? = nil) {
        newReportCompany = company ?? selectedCompany ?? companies.first
        showNewReportSheet = true
    }

    /// A memo run just started: land on the company row with the blotter open —
    /// there is no PDF to open for 20–40 minutes.
    func handleCreatedReport(_ report: MacReport) {
        showNewReportSheet = false
        selectedReport = report
        if let cid = report.companyId, let company = companies.first(where: { $0.id == cid }) {
            selectedCompany = company
        }
        selectedTab = .research
        showBlotter = true
        blotterTab = .jobs
        selectedJobId = report.id
        knownActiveMemoReports.insert(report.id)
        Task {
            await refreshReports()
            await refreshJobs()
        }
    }

    func toggleBlotter() {
        showBlotter.toggle()
    }

    func openCommandPalette(seed: String = "") {
        commandPaletteSeed = seed
        showCommandPalette = true
    }

    // MARK: - Desk Preferences Synchronization

    func refreshDeskPrefs() async {
        do {
            let res = try await MacAPIClient.shared.fetchDeskPrefs()
            pinnedTickers = res.watchlist.isEmpty ? MacAPIClient.defaultWatchlist : res.watchlist
            bookLots = res.lots
            alertRules = res.rules
            deskPrefsLoaded = true
        } catch {
            // Keep current local state
        }
    }

    func isPinned(_ ticker: String) -> Bool {
        pinnedTickers.contains(ticker.uppercased())
    }

    func toggleWatchlist(_ ticker: String) async {
        let t = ticker.uppercased()
        if pinnedTickers.contains(t) {
            pinnedTickers.removeAll { $0 == t }
        } else {
            pinnedTickers.append(t)
        }
        await saveDeskState()
        await refreshMarket()
    }

    func addLot(ticker: String, shares: Double, costBasis: Double) async {
        let newLot = MacBookLot(
            id: UUID().uuidString,
            ticker: ticker.uppercased(),
            shares: shares,
            costBasis: costBasis
        )
        bookLots.append(newLot)
        await saveDeskState()
    }

    func removeLot(id: String) async {
        bookLots.removeAll { $0.id == id }
        await saveDeskState()
    }

    func addAlertRule(ticker: String, threshold: Double, direction: String, kind: String = "price") async {
        let newRule = MacAlertRule(
            id: UUID().uuidString,
            ticker: ticker.uppercased(),
            kind: kind,
            threshold: threshold,
            direction: direction,
            enabled: true
        )
        alertRules.append(newRule)
        await saveDeskState()
    }

    func toggleAlertRule(id: String) async {
        if let idx = alertRules.firstIndex(where: { $0.id == id }) {
            alertRules[idx].enabled.toggle()
            await saveDeskState()
        }
    }

    func deleteAlertRule(id: String) async {
        alertRules.removeAll { $0.id == id }
        await saveDeskState()
    }

    private func saveDeskState() async {
        do {
            try await MacAPIClient.shared.saveDeskPrefs(
                watchlist: pinnedTickers,
                lots: bookLots,
                rules: alertRules
            )
        } catch {
            self.error = "Sync with desk preferences failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Market Radar & Charting

    func refreshMarket() async {
        do {
            let userTickers = pinnedTickers.map { $0.uppercased() }
            let companyTickers = companies.compactMap { $0.ticker?.uppercased() }.filter { !$0.isEmpty }
            let combined = Array(Set(MacAPIClient.defaultWatchlist + userTickers + companyTickers))

            async let quotes = MacAPIClient.shared.fetchQuotes(tickers: Array(combined.prefix(30)))
            async let screeners = MacAPIClient.shared.fetchScreeners(limit: 12)

            watchlist = try await quotes
            let s = try await screeners
            gainers = s.gainers
            losers = s.losers

            if selectedTicker == nil, let first = watchlist.first?.ticker {
                selectTicker(first)
            }
            MacDataCache.shared.saveQuotes(watchlist)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func selectTicker(_ ticker: String) {
        selectedTicker = ticker.uppercased()
        Task {
            await loadChart(range: selectedChartRange)
            await loadWorkspace()
        }
    }

    func loadChart(range: MacChartRange) async {
        guard let ticker = selectedTicker else { return }
        selectedChartRange = range
        loadingChart = true
        defer { loadingChart = false }
        do {
            selectedChart = try await MacAPIClient.shared.fetchChart(ticker: ticker, range: range)
        } catch {
            // Best effort
        }
    }

    func loadWorkspace() async {
        guard let ticker = selectedTicker else { return }
        do {
            selectedWorkspace = try await MacAPIClient.shared.fetchWorkspace(ticker: ticker)
        } catch {
            selectedWorkspace = nil
        }
    }

    // MARK: - News & Pulse

    func refreshNews() async {
        do {
            let tickers = companies.compactMap(\.ticker).prefix(12).map { $0 }
            news = try await MacAPIClient.shared.fetchNews(tickers: Array(tickers), limit: 50)
            MacDataCache.shared.saveNews(news)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshPulse() async {
        do {
            pulse = try await MacAPIClient.shared.fetchPulse()
            if let pulse {
                MacDataCache.shared.savePulse(pulse)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Jobs blotter (live)

    private func startBackgroundLoops() {
        jobPollTask?.cancel()
        jobPollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refreshJobs()
                let interval: UInt64 = self.activeJobs.isEmpty ? 15_000_000_000 : 3_000_000_000
                try? await Task.sleep(nanoseconds: interval)
            }
        }
        alertLoopTask?.cancel()
        alertLoopTask = Task { [weak self] in
            await self?.refreshAlertEvents()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                guard let self else { return }
                if Self.isUSMarketOpen(), !self.alertRules.isEmpty {
                    await self.runAlertCheck(notify: true)
                }
            }
        }
    }

    func refreshJobs() async {
        async let active = MacAPIClient.shared.fetchActiveJobs()
        async let history = MacAPIClient.shared.fetchJobHistory(limit: 30)
        if let rows = try? await active {
            applyActiveJobs(rows)
        }
        if let rows = try? await history {
            jobHistory = rows
        }
    }

    private func applyActiveJobs(_ rows: [MacActiveJob]) {
        let previous = knownActiveMemoReports
        activeJobs = rows
        let nowActive = Set(rows.filter(\.isMemo).compactMap(\.reportId))
        knownActiveMemoReports = nowActive

        // Memo runs that just left the active list → refresh the library and notify.
        let finished = previous.subtracting(nowActive)
        if !finished.isEmpty {
            Task {
                await refreshReports()
                for reportId in finished {
                    if let report = reports.first(where: { $0.id == reportId }) {
                        let company = report.companyName ?? report.companyId ?? "Memo"
                        if report.isComplete {
                            MacNotifier.post(
                                title: "Memo ready — \(company)",
                                body: "\(report.displayTitle) finished. Open it from the Jobs blotter.",
                                identifier: "memo-\(reportId)"
                            )
                        } else if report.isFailed {
                            MacNotifier.post(
                                title: "Memo run failed — \(company)",
                                body: report.error ?? report.statusLabel,
                                identifier: "memo-\(reportId)"
                            )
                        }
                    }
                }
            }
        }

        // Keep an SSE tail on every active job that streams; drop tails for finished ones.
        let ids = Set(rows.map(\.id))
        for (id, task) in logTailTasks where !ids.contains(id) {
            task.cancel()
            logTailTasks[id] = nil
        }
        for job in rows where logTailTasks[job.id] == nil {
            guard let stream = job.streamUrl, !stream.isEmpty else { continue }
            logTailTasks[job.id] = Task { [weak self] in
                let events = MacAPIClient.shared.streamEvents(path: stream)
                do {
                    for try await event in events {
                        guard !Task.isCancelled else { break }
                        let line = Self.logLine(from: event)
                        guard !line.isEmpty else { continue }
                        await MainActor.run {
                            guard let self else { return }
                            var lines = self.jobLogs[job.id] ?? []
                            lines.append(line)
                            if lines.count > 80 { lines.removeFirst(lines.count - 80) }
                            self.jobLogs[job.id] = lines
                        }
                    }
                } catch {
                    // Polling remains the safety net.
                }
                await MainActor.run { self?.logTailTasks[job.id] = nil }
            }
        }
    }

    private static func logLine(from event: MacSSEEvent) -> String {
        if let obj = event.json {
            let type = (obj["type"] as? String) ?? event.event ?? ""
            let message = (obj["message"] as? String)
                ?? (obj["stage"] as? String)
                ?? (obj["error"] as? String)
                ?? (obj["text"] as? String)
                ?? ""
            let stamp = (obj["ts"] as? String).map { String($0.suffix(15).prefix(8)) } ?? ""
            let body = message.isEmpty ? type : message
            return [stamp, type.isEmpty ? "" : "[\(type)]", body]
                .filter { !$0.isEmpty }
                .joined(separator: " ")
        }
        return event.data
    }

    func cancelJob(_ job: MacActiveJob) async {
        guard let reportId = job.reportId, job.isMemo else { return }
        do {
            _ = try await MacAPIClient.shared.cancelReport(id: reportId)
            await refreshJobs()
            await refreshReports()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func resumeReport(id: String) async {
        do {
            _ = try await MacAPIClient.shared.resumeReport(id: id)
            showBlotter = true
            blotterTab = .jobs
            await refreshJobs()
            await refreshReports()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func dismissReport(id: String) async {
        do {
            _ = try await MacAPIClient.shared.dismissReport(id: id)
            await refreshJobs()
            await refreshReports()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteReport(id: String) async {
        do {
            try await MacAPIClient.shared.deleteReport(id: id)
            if selectedReport?.id == id { selectedReport = nil }
            await refreshJobs()
            await refreshReports()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func report(for id: String?) -> MacReport? {
        guard let id else { return nil }
        return reports.first { $0.id == id }
    }

    // MARK: - Alerts

    func refreshAlertEvents() async {
        if let events = try? await MacAPIClient.shared.fetchAlertEvents(limit: 100) {
            alertEvents = events
        }
    }

    func runAlertCheck(notify: Bool) async {
        guard !checkingAlerts else { return }
        checkingAlerts = true
        defer { checkingAlerts = false }
        do {
            let result = try await MacAPIClient.shared.runAlertCheck()
            lastAlertCheck = Date()
            if notify {
                for fired in result.fired ?? [] {
                    MacNotifier.post(
                        title: "Price alert — \(fired.ticker ?? "")",
                        body: fired.headline,
                        identifier: "alert-\(fired.id)"
                    )
                }
            }
            await refreshAlertEvents()
            if !(result.fired ?? []).isEmpty {
                showBlotter = true
                blotterTab = .alerts
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    static func isUSMarketOpen(now: Date = Date()) -> Bool {
        guard let tz = TimeZone(identifier: "America/New_York") else { return false }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = tz
        let comps = cal.dateComponents([.weekday, .hour, .minute], from: now)
        guard let weekday = comps.weekday, (2...6).contains(weekday),
              let hour = comps.hour, let minute = comps.minute else { return false }
        let minutes = hour * 60 + minute
        return minutes >= 9 * 60 + 30 && minutes <= 16 * 60
    }

    // MARK: - Search & pipeline

    /// Promote a hit to a tracked company and show its dossier.
    func addToPipeline(_ match: MacCompanyMatch) async -> MacCompany? {
        do {
            let company = try await MacAPIClient.shared.selectCompany(match)
            await refreshHome()
            let resolved = companies.first { $0.id == company.id } ?? company
            showCompany(resolved)
            return resolved
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    // MARK: - Pipeline board (tracking rollup + follow list)

    /// Companies on the board: the server follow-list, or every company when nobody follows anything yet.
    var pipelineCompanyIds: [String] {
        followedCompanyIds.isEmpty ? companies.map(\.id) : followedCompanyIds
    }

    func rollupRow(for companyId: String) -> MacRollupRow? {
        rollup?.companies.first { $0.id == companyId }
    }

    func latestDecision(for companyId: String) -> MacDecision? {
        decisionsByCompany[companyId]?.first
    }

    func stage(for companyId: String) -> MacLifecycleStage {
        MacLifecycleStage.derive(row: rollupRow(for: companyId), latestDecision: latestDecision(for: companyId))
    }

    func isFollowed(_ companyId: String) -> Bool {
        followedCompanyIds.contains(companyId)
    }

    func loadPipeline() async {
        guard !pipelineLoading else { return }
        pipelineLoading = true
        defer { pipelineLoading = false }
        if let ids = try? await MacAPIClient.shared.fetchTrackingWatchlist() {
            followedCompanyIds = ids
        }
        let ids = Array(pipelineCompanyIds.prefix(60))
        do {
            rollup = try await MacAPIClient.shared.fetchTrackingRollup(companyIds: ids)
        } catch MacAPIError.unauthorized {
            session = nil
            showLoginSheet = true
            return
        } catch {
            self.error = "Pipeline rollup failed: \(error.localizedDescription)"
        }
        await loadDecisions(for: ids)
        pipelineLoadedAt = Date()
    }

    func loadDecisions(for ids: [String]) async {
        let fetched = await withTaskGroup(of: (String, [MacDecision]?).self) { group in
            for id in ids {
                group.addTask {
                    (id, try? await MacAPIClient.shared.fetchDecisions(companyId: id))
                }
            }
            var out: [String: [MacDecision]] = [:]
            for await (id, list) in group {
                if let list { out[id] = list }
            }
            return out
        }
        decisionsByCompany.merge(fetched) { _, new in new }
    }

    func toggleFollow(_ companyId: String) async {
        var ids = followedCompanyIds
        if let index = ids.firstIndex(of: companyId) {
            ids.remove(at: index)
        } else {
            ids.append(companyId)
        }
        do {
            followedCompanyIds = try await MacAPIClient.shared.saveTrackingWatchlist(ids)
            await loadPipeline()
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Server-side, synchronous, can take minutes — runs detached and notifies on completion.
    func syncAllTracking() {
        guard !pipelineSyncing else { return }
        pipelineSyncing = true
        let ids = followedCompanyIds.isEmpty ? nil : followedCompanyIds
        Task {
            do {
                let created = try await MacAPIClient.shared.syncAllTracking(companyIds: ids)
                MacNotifier.post(
                    title: "Tracking sync finished",
                    body: created == 0 ? "No new tracked news." : "\(created) new tracked item(s).",
                    identifier: "tracking-sync"
                )
                await loadPipeline()
                for id in Array(trackingByCompany.keys) {
                    await loadTracking(id, sync: false)
                }
            } catch {
                self.error = "Tracking sync failed: \(error.localizedDescription)"
            }
            pipelineSyncing = false
        }
    }

    // MARK: - Decisions

    func requestDecision(for company: MacCompany, reportId: String? = nil) {
        decisionTarget = company
        decisionSeedReportId = reportId
        showDecisionSheet = true
    }

    @discardableResult
    func recordDecision(companyId: String, verdict: String, explanation: String, decidedAt: Date, reportId: String?) async -> Bool {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let body = MacDecisionCreate(
            verdict: verdict,
            explanation: explanation,
            decidedAt: formatter.string(from: decidedAt),
            reportId: reportId
        )
        do {
            let decision = try await MacAPIClient.shared.createDecision(companyId: companyId, body: body)
            decisionsByCompany[companyId, default: []].insert(decision, at: 0)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func deleteDecision(companyId: String, decisionId: String) async {
        do {
            try await MacAPIClient.shared.deleteDecision(companyId: companyId, decisionId: decisionId)
            decisionsByCompany[companyId]?.removeAll { $0.id == decisionId }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Companies with a standing Invest / Watch decision.
    var portfolioEntries: [(company: MacCompany, decision: MacDecision)] {
        companies.compactMap { company in
            guard let decision = latestDecision(for: company.id),
                  decision.verdict == "invest" || decision.verdict == "watch" else { return nil }
            return (company, decision)
        }
        .sorted { a, b in
            if a.decision.verdict != b.decision.verdict { return a.decision.verdict == "invest" }
            return a.company.title.localizedCaseInsensitiveCompare(b.company.title) == .orderedAscending
        }
    }

    // MARK: - Tracking updates (portfolio monitoring)

    func loadTracking(_ companyId: String, sync: Bool) async {
        guard !trackingBusy.contains(companyId) else { return }
        trackingBusy.insert(companyId)
        defer { trackingBusy.remove(companyId) }
        do {
            let updates = sync
                ? try await MacAPIClient.shared.syncTrackingUpdates(companyId: companyId)
                : try await MacAPIClient.shared.fetchTrackingUpdates(companyId: companyId)
            trackingByCompany[companyId] = updates
            if sync {
                await loadDecisions(for: [companyId])
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func executeAutoRun(companyId: String, autoRun: MacAutoRun) async -> MacAutoRunExecuteResult? {
        do {
            let result = try await MacAPIClient.shared.executeAutoRun(companyId: companyId, autoRunId: autoRun.id)
            await loadTracking(companyId, sync: false)
            if result.executed {
                showBlotter = true
                blotterTab = .jobs
                await refreshReports()
                await refreshJobs()
            }
            return result
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    // MARK: - IC prep (memo analysis session) & evidence

    func loadMemoAnalysis(_ companyId: String) async {
        guard !analysisBusy.contains(companyId) else { return }
        analysisBusy.insert(companyId)
        defer { analysisBusy.remove(companyId) }
        do {
            analysisByCompany[companyId] = try await MacAPIClient.shared.fetchMemoAnalysis(companyId: companyId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func runMemoTool(companyId: String, tool: String) async {
        do {
            analysisByCompany[companyId] = try await MacAPIClient.shared.runMemoTool(companyId: companyId, tool: tool)
            showBlotter = true
            blotterTab = .jobs
            await refreshJobs()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func reviewReadinessArea(companyId: String, areaId: String, status: String, rationale: String) async {
        do {
            analysisByCompany[companyId] = try await MacAPIClient.shared.patchReadinessReviews(
                companyId: companyId,
                items: [MacReadinessReviewPatch.Item(id: areaId, status: status, rationale: rationale)]
            )
        } catch {
            self.error = error.localizedDescription
        }
    }

    @discardableResult
    func approveMemoAnalysis(companyId: String) async -> Bool {
        do {
            analysisByCompany[companyId] = try await MacAPIClient.shared.approveMemoAnalysis(companyId: companyId)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func loadEvidence(_ companyId: String) async {
        if let matrix = try? await MacAPIClient.shared.fetchEvidenceMatrix(companyId: companyId) {
            evidenceByCompany[companyId] = matrix
        }
    }

    func openICReview(report: MacReport, language: String? = nil) {
        guard let companyId = report.companyId else {
            openReportWindow(report, language: language)
            return
        }
        let request = MacICReviewRequest(companyId: companyId, reportId: report.id, language: language ?? readerLanguage)
        if let openICWindow {
            openICWindow(request)
        } else {
            openReportWindow(report, language: language)
        }
    }

    // MARK: - "What Changed" Baseline Diffs

    func markCompanyVisited(_ companyId: String) {
        visitedCompanyTimestamps[companyId] = Date()
        MacDataCache.shared.saveBaselines(visitedCompanyTimestamps)
    }

    func isCompanyModified(_ companyId: String) -> Bool {
        guard let baseline = visitedCompanyTimestamps[companyId] else {
            return true
        }
        let list = companyReportsCache[companyId] ?? reports.filter { $0.companyId == companyId }
        for r in list {
            if let dateStr = r.updatedAt ?? r.createdAt,
               let d = ISO8601DateFormatter().date(from: dateStr),
               d > baseline {
                return true
            }
        }
        return false
    }

    func isReportNew(_ report: MacReport) -> Bool {
        guard let cid = report.companyId, let baseline = visitedCompanyTimestamps[cid] else {
            return true
        }
        if let dateStr = report.updatedAt ?? report.createdAt,
           let d = ISO8601DateFormatter().date(from: dateStr),
           d > baseline {
            return true
        }
        return false
    }

    // MARK: - Pitch Deck Intake

    func ingestDeck(url: URL) {
        droppedDeckURL = url
        showDeckIntakeSheet = true
    }

    // MARK: - Research Memos & Annotation Overlays

    func reports(for companyId: String) -> [MacReport] {
        let list = companyReportsCache[companyId] ?? reports.filter { $0.companyId == companyId }
        return list.sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
    }

    /// Download a memo file (+ iPad ink overlay) to a temp URL. Shared by the
    /// Documents desk and memo windows; throws when the report has no file yet.
    func loadMemoDocument(reportId: String, language: String) async throws -> MacLoadedMemo {
        var detail = report(for: reportId)
        if let fetched = try? await MacAPIClient.shared.getReport(id: reportId) {
            detail = fetched
        }
        guard let detail else {
            throw MacAPIError.http(404, "Report not found")
        }
        guard let doc = detail.documentPath(prefer: language) else {
            throw MacAPIError.http(404, "No memo file for \(language.uppercased()) yet")
        }

        async let memoData = MacAPIClient.shared.download(pathOrURL: doc.path)
        async let overlay = MacAPIClient.shared.fetchOverlayPNG(reportId: reportId, overlayUrl: nil)
        let data = try await memoData
        let inkOverlay = try? await overlay

        let ext = doc.isPDF ? "pdf" : "docx"
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("bsh-memo-\(detail.id)-\(language).\(ext)")
        try data.write(to: url, options: .atomic)
        tempFiles.append(url)

        return MacLoadedMemo(
            url: url,
            isPDF: doc.isPDF,
            overlayData: inkOverlay,
            title: "\(detail.companyName ?? "") — \(detail.displayTitle)",
            report: detail
        )
    }

    /// Documents-desk inline reader.
    func openMemo(_ report: MacReport, language: String? = nil) async {
        let lang = language ?? readerLanguage
        readerLanguage = lang
        openReportId = report.id
        openingMemo = true
        defer { openingMemo = false }
        do {
            let loaded = try await loadMemoDocument(reportId: report.id, language: lang)
            openDocumentURL = loaded.url
            openDocumentIsPDF = loaded.isPDF
            openDocumentOverlayData = loaded.overlayData
            openReportTitle = loaded.title
        } catch {
            self.error = error.localizedDescription
        }
    }

    func closeMemo() {
        openDocumentURL = nil
        openReportTitle = ""
        openReportId = ""
        openDocumentOverlayData = nil
    }

    func toggleAnnotationOverlay() {
        showAnnotationOverlay.toggle()
    }

    func openInEmbeddedBrowser(_ url: URL) {
        browserCurrentURL = url
        showBrowserPanel = true
    }

    // MARK: - Copilot ("Ask Warren" Assistant) — context-aware

    /// Desks call this before opening Ask so the assistant knows what's on screen.
    func setCopilotContext(_ context: MacCopilotContext, company: MacCompany? = nil) {
        if let company { selectCompany(company) }
        copilotContext = context
        copilotContextInfo = nil
        let cid = selectedCompany?.id ?? companies.first?.id
        guard let cid, !cid.isEmpty else { return }
        Task {
            if let info = try? await MacAPIClient.shared.fetchCopilotContext(companyId: cid, context: context) {
                if self.copilotContext == context { self.copilotContextInfo = info }
            }
        }
    }

    func clearCopilotContext() {
        copilotContext = .none
        copilotContextInfo = nil
    }

    /// Ask with the current on-screen context, switching to the Ask desk.
    func askWarren(_ prompt: String, context: MacCopilotContext, company: MacCompany? = nil) {
        setCopilotContext(context, company: company)
        selectedTab = .copilot
        sendCopilotMessage(prompt: prompt)
    }

    func sendCopilotMessage(prompt: String) {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !copilotStreaming else { return }

        var userMsg = MacCopilotMessage(role: .user, text: trimmed)
        userMsg.contextLabel = copilotContext.chipLabel
        copilotMessages.append(userMsg)
        copilotDraft = ""
        copilotStreaming = true
        copilotCurrentThinking = nil

        let cid = selectedCompany?.id ?? companies.first?.id ?? "general"
        let persona = copilotPersona
        let context = copilotContext
        let mode = copilotDeepMode ? "deep" : "quick"
        if copilotDeepMode {
            showBlotter = true
            blotterTab = .jobs
        }

        copilotTask?.cancel()
        copilotTask = Task {
            var reply = ""
            let assistantMsg = MacCopilotMessage(role: .assistant, text: "")
            copilotMessages.append(assistantMsg)
            let assistantIndex = copilotMessages.count - 1

            do {
                let stream = await MacAPIClient.shared.askCopilotStream(
                    companyId: cid,
                    prompt: trimmed,
                    persona: persona,
                    context: context,
                    mode: mode
                )
                for try await chunk in stream {
                    switch chunk {
                    case .partial(let text):
                        reply += (reply.isEmpty ? "" : "\n\n") + text
                        copilotMessages[assistantIndex].text = reply
                    case .tool(let activity):
                        copilotCurrentThinking = activity
                    case .final(let text):
                        if !text.isEmpty { reply = text }
                        copilotMessages[assistantIndex].text = reply
                    }
                }
                if reply.isEmpty {
                    copilotMessages[assistantIndex].text = "No answer came back — try again or ask on the web console."
                }
            } catch {
                if !Task.isCancelled {
                    let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                    copilotMessages[assistantIndex].text = reply.isEmpty
                        ? "Assistant error: \(detail)"
                        : reply + "\n\n*(Stream interrupted: \(detail))*"
                }
            }
            copilotCurrentThinking = nil
            copilotStreaming = false
        }
    }

    // MARK: - Attention queue ("what needs me today")

    static let lastLaunchKey = "bsh.mac.lastLaunchAt"

    func loadAttention() async {
        guard !attentionLoading else { return }
        attentionLoading = true
        defer { attentionLoading = false }
        let since = UserDefaults.standard.object(forKey: Self.lastLaunchKey) as? Date
            ?? Calendar.current.date(byAdding: .hour, value: -24, to: Date())
        async let screener = MacAPIClient.shared.fetchDeskScreener(limit: 30)
        async let digest = MacAPIClient.shared.fetchDeskDigest(since: since, limit: 30)
        async let intake = MacAPIClient.shared.fetchIntakeUnresolved()
        screenerItems = (try? await screener) ?? []
        digestItems = (try? await digest) ?? []
        intakeItems = (try? await intake) ?? []
        if rollup == nil { await loadPipeline() }
        attentionLoadedAt = Date()
    }

    /// Called once per launch after the first attention load so "what changed" measures from the previous launch.
    func stampLaunch() {
        UserDefaults.standard.set(Date(), forKey: Self.lastLaunchKey)
    }

    // MARK: - Signal ledger

    func loadSignals() async {
        guard !signalsLoading else { return }
        signalsLoading = true
        defer { signalsLoading = false }
        if let rows = try? await MacAPIClient.shared.fetchSignals() {
            signals = rows
        }
    }

    @discardableResult
    func logSignal(ticker: String, direction: String, label: String) async -> Bool {
        let price = watchlist.first(where: { $0.ticker == ticker.uppercased() })?.last
        do {
            _ = try await MacAPIClient.shared.logSignal(ticker: ticker, direction: direction, label: label, priceAtSignal: price)
            await loadSignals()
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func deleteSignal(id: String) async {
        do {
            try await MacAPIClient.shared.deleteSignal(id: id)
            signals.removeAll { $0.id == id }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func openSignalLog(seedTicker: String? = nil) {
        signalSeedTicker = seedTicker ?? selectedTicker
        showBlotter = true
        blotterTab = .signals
        Task { await loadSignals() }
    }

    // MARK: - Console sessions

    func loadConsoleSessions(companyId: String) async {
        if let rows = try? await MacAPIClient.shared.listConsoleSessions(companyId: companyId) {
            consoleSessions[companyId] = rows.sorted { ($0.lastUsedAt ?? "") > ($1.lastUsedAt ?? "") }
            if consoleSelectedSessionId == nil || !rows.contains(where: { $0.id == consoleSelectedSessionId }) {
                consoleSelectedSessionId = rows.first(where: { !$0.isArchived })?.id ?? rows.first?.id
            }
        }
    }

    func loadConsoleTurns(companyId: String, sessionId: String) async {
        if let turns = try? await MacAPIClient.shared.fetchConsoleTurns(companyId: companyId, sessionId: sessionId) {
            consoleTurns[sessionId] = turns
        }
    }

    func createConsoleSession(companyId: String, includeLibraryDocs: Bool, language: String) async {
        do {
            let session = try await MacAPIClient.shared.createConsoleSession(
                companyId: companyId,
                includeBackgroundDocs: true,
                includeLibraryDocs: includeLibraryDocs,
                outputLanguage: language
            )
            consoleSessions[companyId, default: []].insert(session, at: 0)
            consoleSelectedSessionId = session.id
            consoleTurns[session.id] = []
        } catch {
            self.error = error.localizedDescription
        }
    }

    func askConsole(companyId: String, sessionId: String, prompt: String, attachments: [URL]) {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, consoleStreamingTurn == nil else { return }
        consoleTask?.cancel()
        consoleTask = Task {
            do {
                let result = try await MacAPIClient.shared.askConsole(companyId: companyId, sessionId: sessionId, prompt: trimmed, attachments: attachments)
                consoleTurns[sessionId, default: []].append(MacConsoleTurn(turnId: result.turnId, role: "user", text: trimmed))
                consoleTurns[sessionId, default: []].append(MacConsoleTurn(turnId: result.turnId, role: "assistant", text: ""))
                consoleStreamingTurn = (sessionId, result.turnId)
                consoleActivity = (result.queuePosition ?? 0) > 0 ? "Queued (#\(result.queuePosition ?? 0))…" : "Asking Claude…"
                guard let path = result.streamUrl else { throw MacAPIError.stream("No stream for this turn") }

                var reply = ""
                let stream = AsyncThrowingStream<MacCopilotChunk, Error> { continuation in
                    let pump = Task {
                        do {
                            try await MacAPIClient.shared.pumpConsoleStream(path: path, into: continuation)
                            continuation.finish()
                        } catch {
                            continuation.finish(throwing: error)
                        }
                    }
                    continuation.onTermination = { _ in pump.cancel() }
                }
                do {
                    for try await chunk in stream {
                        switch chunk {
                        case .partial(let text):
                            reply += (reply.isEmpty ? "" : "\n\n") + text
                            consoleActivity = "Writing…"
                        case .tool(let activity):
                            consoleActivity = activity
                        case .final(let text):
                            if !text.isEmpty { reply = text }
                        }
                        updateConsoleReply(sessionId: sessionId, turnId: result.turnId, text: reply)
                    }
                } catch {
                    if !Task.isCancelled {
                        let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                        updateConsoleReply(sessionId: sessionId, turnId: result.turnId, text: reply.isEmpty ? "Error: \(detail)" : reply + "\n\n*(\(detail))*")
                    }
                }
                await loadConsoleTurns(companyId: companyId, sessionId: sessionId)
                await loadConsoleSessions(companyId: companyId)
            } catch {
                self.error = error.localizedDescription
            }
            consoleStreamingTurn = nil
            consoleActivity = nil
        }
    }

    private func updateConsoleReply(sessionId: String, turnId: String, text: String) {
        guard var turns = consoleTurns[sessionId],
              let index = turns.lastIndex(where: { $0.turnId == turnId && !$0.isUser }) else { return }
        turns[index].text = text
        consoleTurns[sessionId] = turns
    }

    func cancelConsoleTurn(companyId: String) async {
        guard let (sessionId, turnId) = consoleStreamingTurn else { return }
        try? await MacAPIClient.shared.cancelConsoleTurn(companyId: companyId, sessionId: sessionId, turnId: turnId)
        consoleTask?.cancel()
        consoleStreamingTurn = nil
        consoleActivity = nil
    }

    func archiveConsoleSession(companyId: String, sessionId: String) async {
        if let updated = try? await MacAPIClient.shared.archiveConsoleSession(companyId: companyId, sessionId: sessionId) {
            if let index = consoleSessions[companyId]?.firstIndex(where: { $0.id == sessionId }) {
                consoleSessions[companyId]?[index] = updated
            }
        }
    }

    func deleteConsoleSession(companyId: String, sessionId: String) async {
        do {
            try await MacAPIClient.shared.deleteConsoleSession(companyId: companyId, sessionId: sessionId)
            consoleSessions[companyId]?.removeAll { $0.id == sessionId }
            consoleTurns[sessionId] = nil
            if consoleSelectedSessionId == sessionId {
                consoleSelectedSessionId = consoleSessions[companyId]?.first?.id
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func selectCompany(_ company: MacCompany) {
        selectedCompany = company
        markCompanyVisited(company.id)
        if let ticker = company.ticker, !ticker.isEmpty {
            selectTicker(ticker)
        }
        Task {
            await fetchFounderDossier(for: company.id)
            await fetchDealPipeline(for: company.id)
        }
    }

    func fetchDealPipeline(for companyId: String) async {
        if let pipeline = try? await MacAPIClient.shared.fetchDealPipeline(companyId: companyId) {
            dealPipelines[companyId] = pipeline
        }
    }

    func updateDealStage(companyId: String, newStage: String) async {
        guard var current = dealPipelines[companyId] else { return }
        current.stage = newStage
        current.daysInStage = 0
        dealPipelines[companyId] = current
        do {
            dealPipelines[companyId] = try await MacAPIClient.shared.updateDealPipeline(
                companyId: companyId,
                fields: ["stage": newStage, "days_in_stage": 0]
            )
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateDealFields(companyId: String, fields: [String: Any]) async {
        do {
            dealPipelines[companyId] = try await MacAPIClient.shared.updateDealPipeline(companyId: companyId, fields: fields)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func fetchFounderDossier(for companyId: String) async {
        if let dossier = try? await MacAPIClient.shared.fetchFounderDossier(companyId: companyId) {
            founderDossiers[companyId] = dossier
        }
    }

    /// Re-reads people, board and links from the company record (no external lookup yet).
    func deepSearchFounder(for companyId: String) async {
        deepSearchingFounders.insert(companyId)
        defer { deepSearchingFounders.remove(companyId) }
        do {
            founderDossiers[companyId] = try await MacAPIClient.shared.refreshFounderDossier(companyId: companyId)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - macOS notifications

enum MacNotifier {
    private static var requested = false

    static func post(title: String, body: String, identifier: String) {
        let center = UNUserNotificationCenter.current()
        let deliver = {
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            let request = UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
            center.add(request)
        }
        if requested {
            deliver()
            return
        }
        requested = true
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            if granted { deliver() }
        }
    }
}

// MARK: - News & Quotes Models

struct MacNewsItem: Identifiable, Hashable, Codable {
    let id: String
    let title: String
    let summary: String?
    let source: String?
    let publishedAt: String?
    let ticker: String?
    let url: String?
    let category: String?
    let kind: String?
    let companyName: String?

    init(
        id: String,
        title: String,
        summary: String? = nil,
        source: String? = nil,
        publishedAt: String? = nil,
        ticker: String? = nil,
        url: String? = nil,
        category: String? = nil,
        kind: String? = "news",
        companyName: String? = nil
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.source = source
        self.publishedAt = publishedAt
        self.ticker = ticker
        self.url = url
        self.category = category
        self.kind = kind
        self.companyName = companyName
    }

    var timeAgo: String {
        guard let publishedAt, !publishedAt.isEmpty else { return "" }
        if let date = ISO8601DateFormatter().date(from: publishedAt) {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .abbreviated
            return formatter.localizedString(for: date, relativeTo: Date())
        }
        if publishedAt.count >= 10 {
            return String(publishedAt.prefix(10))
        }
        return publishedAt
    }
}

struct MacQuote: Identifiable, Hashable, Codable {
    var id: String { ticker }
    let ticker: String
    let last: Double?
    let pct: Double?
    let name: String?

    var priceText: String {
        guard let last else { return "—" }
        return String(format: "$%.2f", last)
    }

    var pctText: String {
        guard let pct else { return "—" }
        return String(format: "%+.2f%%", pct)
    }

    var isUp: Bool { (pct ?? 0) >= 0 }
}

struct MacPulseBrief: Codable {
    let date: String?
    let indices: [MacPulseQuote]?
    let note: MacPulseNote?

    struct MacPulseQuote: Codable, Identifiable {
        var id: String { ticker }
        let ticker: String
        let lastPrice: Double?
        let changePct1d: Double?
        enum CodingKeys: String, CodingKey {
            case ticker
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
        }
    }

    struct MacPulseNote: Codable {
        let headlineEn: String?
        let headlineZh: String?
        let bulletsEn: [String]?
        let bulletsZh: [String]?
        enum CodingKeys: String, CodingKey {
            case headlineEn = "headline_en"
            case headlineZh = "headline_zh"
            case bulletsEn = "bullets_en"
            case bulletsZh = "bullets_zh"
        }
    }
}
