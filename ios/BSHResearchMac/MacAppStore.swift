#if canImport(AppKit)
import AppKit
#endif
#if canImport(UIKit)
import UIKit
#endif
import Combine
import Foundation
import UserNotifications

enum MacBlotterTab: String, CaseIterable, Identifiable {
    case jobs
    case alerts
    case signals
    case chat
    case audit
    var id: String { rawValue }
}

/// One shared store for every window (main desks, memo windows, Settings).
@MainActor
final class MacAppStore: ObservableObject {
    // MARK: - Navigation & Active Tab
    @Published var selectedTab: MacTab = .home {
        // Chart and workspace fetches are third-party calls that only Market Radar shows;
        // they run when the desk is on screen, not on every row selection elsewhere.
        didSet { if selectedTab == .market { loadSelectedTickerIfVisible() } }
    }
    @Published var showBlotter = false
    @Published var blotterTab: MacBlotterTab = .jobs {
        didSet { if blotterTab == .alerts { unseenAlertCount = 0 } }
    }
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
    @Published private(set) var rollup: MacRollup? {
        didSet { rollupById = Dictionary((rollup?.companies ?? []).map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a }) }
    }
    @Published private(set) var rollupById: [String: MacRollupRow] = [:]
    @Published private(set) var followedCompanyIds: [String] = []
    @Published private(set) var decisionsByCompany: [String: [MacDecision]] = [:]
    @Published private(set) var pipelineLoading = false
    @Published private(set) var pipelineSyncing = false
    @Published private(set) var pipelineLoadedAt: Date?
    /// The rollup on screen is a cached or previous one: the last fetch failed.
    @Published private(set) var rollupStale = false
    @Published private(set) var pipelineError: String?
    @Published var showDecisionSheet = false
    @Published var decisionTarget: MacCompany?
    @Published var decisionSeedReportId: String?
    @Published private(set) var trackingByCompany: [String: MacTrackingUpdates] = [:]
    @Published private(set) var trackingBusy: Set<String> = []
    @Published private(set) var analysisByCompany: [String: MacMemoAnalysis] = [:]
    @Published private(set) var analysisBusy: Set<String> = []
    @Published private(set) var evidenceByCompany: [String: MacEvidenceMatrix] = [:]
    @Published private(set) var memoEditorByCompany: [String: MacMemoEditorState] = [:]
    @Published private(set) var memoEditorBusy: Set<String> = []
    @Published private(set) var memoEditorError: [String: String] = [:]

    // MARK: - Session
    @Published private(set) var session: MacSession?
    @Published private(set) var authChecked = false
    @Published var authError: String?
    @Published private(set) var signingIn = false
    /// The server refused our credentials (401); nothing else is fetched until sign-in.
    @Published private(set) var sessionRejected = false
    /// Why the login sheet is up: first run ("Sign in to continue") or a revoked session.
    @Published private(set) var sessionNotice: String?
    static let sessionEndedMessage = "Signed-in session ended — sign in again."

    // MARK: - Companies & Reports
    @Published private(set) var companies: [MacCompany] = []
    @Published private(set) var reports: [MacReport] = []
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
    @Published private(set) var chartError: String?
    private var tickerLoadTask: Task<Void, Never>?
    /// The ticker whose chart + workspace load has been started (or finished) for Market Radar.
    private var tickerLoadedFor: String?
    private var chartLoadGen = 0
    private var workspaceLoadGen = 0
    private var watchlistFetchedAt: Date?

    // MARK: - Desk Preferences (Syncs with Web & iPadOS)
    @Published private(set) var pinnedTickers: [String] = []
    @Published private(set) var bookLots: [MacBookLot] = []
    @Published private(set) var alertRules: [MacAlertRule] = []
    @Published private(set) var deskPrefsLoaded = false

    // MARK: - News, Jobs, Alerts & Pulse
    @Published private(set) var news: [MacNewsItem] = []
    /// A news item the News desk should scroll to and highlight on its next appearance.
    @Published var newsFocusId: String?
    /// A company whose headlines the News desk should open on, set by the sidebar's
    /// company pages (the web's `?company=` on the News desk). The desk adopts and clears it.
    @Published var newsCompanyFocus: MacCompany?
    /// A company the Documents desk should open filtered to, from the same place.
    @Published var documentsCompanyFilter: String?
    @Published private(set) var activeJobs: [MacActiveJob] = []
    @Published private(set) var jobHistory: [MacJobHistoryRow] = []
    @Published private(set) var jobLogs: [String: [String]] = [:]
    @Published var selectedJobId: String?
    @Published private(set) var alertEvents: [MacAlertEvent] = []
    @Published private(set) var unseenAlertCount = 0
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
    @Published private(set) var openDocumentError: String?
    private var openMemoGeneration = 0

    // MARK: - Copilot (Ask Warren)
    @Published var copilotMessages: [MacCopilotMessage] = [] {
        // Clearing the transcript mid-stream must also stop the stream.
        didSet { if copilotMessages.isEmpty, copilotStreaming { cancelCopilot() } }
    }
    @Published var copilotPersona: MacCopilotPersona = .warren
    @Published var copilotDraft: String = ""
    @Published var copilotStreaming = false
    @Published var copilotCurrentThinking: String?
    /// What's on screen for the next Ask — set by desks, shown as a chip, sent with the prompt.
    @Published var copilotContext: MacCopilotContext = .none
    @Published private(set) var copilotContextInfo: MacCopilotContextInfo?
    @Published var copilotDeepMode = false
    private var copilotContextTask: Task<Void, Never>?

    /// The company's current Warren thread on the server, and the earlier ones — the
    /// team's, not this Mac's. `copilotMessages` mirrors the current thread.
    @Published private(set) var copilotSessionId: String?
    @Published private(set) var copilotThreads: [MacCopilotThread] = []
    @Published private(set) var copilotThreadsLoading = false
    /// An earlier thread being read. Read-only: nobody adds to a closed thread.
    @Published private(set) var copilotViewingThread: MacCopilotThread?
    @Published private(set) var copilotViewingMessages: [MacCopilotMessage] = []
    private var copilotThreadCompanyId: String?
    /// Files picked for the next question, staged on the server as they are picked.
    @Published var copilotAttachments: [MacStagedAttachment] = []
    /// What happened when the analyst pressed the button on work Warren offered.
    @Published private(set) var copilotWorkRunning = false
    @Published private(set) var copilotWorkNote: String?
    @Published private(set) var copilotWorkError: String?

    /// Context info only while it still belongs to the company on screen.
    var visibleCopilotContextInfo: MacCopilotContextInfo? {
        guard let info = copilotContextInfo else { return nil }
        let current = selectedCompany?.id ?? companies.first?.id
        return (info.companyId == nil || info.companyId == current) ? info : nil
    }

    // MARK: - Attention queue
    @Published private(set) var screenerItems: [MacScreenerItem] = []
    @Published private(set) var digestItems: [MacDigestItem] = []
    @Published private(set) var intakeItems: [MacIntakeItem] = []
    @Published private(set) var attentionLoadedAt: Date?
    @Published private(set) var attentionLoading = false
    @Published private(set) var attentionErrors: [String: String] = [:]
    private let attentionSince: Date
    private var didStampLaunch = false

    // MARK: - Signal ledger
    @Published private(set) var signals: [MacSignal] = []
    @Published private(set) var signalsLoading = false
    @Published var signalSeedTicker: String?

    // MARK: - Thesis, comps, cap model, intake
    @Published private(set) var thesis: MacThesis = .empty
    @Published private(set) var thesisLoaded = false
    @Published private(set) var compsByCompany: [String: MacComps] = [:]
    @Published private(set) var capModelByCompany: [String: MacCapModel] = [:]
    @Published private(set) var intakeResult: MacIntakeResult?
    @Published private(set) var intakeBusy = false

    // MARK: - Private portfolio
    @Published private(set) var portfolioDashboard: MacPortfolioDashboard?
    @Published private(set) var portfolioByCompany: [String: MacPortfolioCompany] = [:]
    @Published private(set) var portfolioLoading = false
    @Published private(set) var reservesPlan: MacReservesPlan?
    @Published private(set) var reservesError: String?

    // MARK: - IC room
    @Published private(set) var referenceCallsByCompany: [String: MacReferenceCalls] = [:]
    @Published private(set) var icMeetingsByCompany: [String: [MacICMeeting]] = [:]
    @Published private(set) var comparablesByCompany: [String: MacComparables] = [:]
    @Published private(set) var redTeamByCompany: [String: MacRedTeam] = [:]

    // MARK: - Firm layer
    @Published var showFirmSearch = false
    @Published private(set) var commentsByCompany: [String: MacComments] = [:]
    @Published private(set) var mentions: MacMentions?
    @Published private(set) var chatChannels: [MacChatChannel] = []
    @Published private(set) var chatHandles: [String] = []
    @Published var chatChannel: String = "general"
    @Published private(set) var chatMessages: [MacChatMessage] = []
    @Published private(set) var chatLatest: String?
    @Published private(set) var auditRows: [MacAuditRow] = []
    @Published private(set) var transcripts: [MacTranscript] = []
    @Published private(set) var transcriptById: [String: MacTranscript] = [:]
    @Published private(set) var signalScoreByCompany: [String: MacSignalScore] = [:]
    private var chatPollTask: Task<Void, Never>?
    private var chatPollRefs = 0
    private var chatGeneration = 0
    private var transcriptQuery = ""
    private var transcriptCompanyId: String?

    // MARK: - Unified profile, filings, signal watch, lint, workspaces
    @Published private(set) var profileByCompany: [String: MacCompanyProfile] = [:]
    /// One listed company's next report, recent quarters and SEC filings.
    @Published private(set) var earningsFilingsByCompany: [String: MacCompanyEarningsFilings] = [:]
    @Published private(set) var earningsFilingsFailed: Set<String> = []
    @Published private(set) var filingsWatch: MacFilingsWatch?
    @Published private(set) var filingsLoading = false
    @Published private(set) var signalMoves: MacSignalMoves?
    @Published private(set) var numberLintByCompany: [String: MacNumberLint] = [:]
    @Published private(set) var workspaces: [MacWorkspace] = MacAppStore.loadWorkspaces()

    // MARK: - Console sessions (persistent, per company)
    @Published private(set) var consoleSessions: [String: [MacConsoleSession]] = [:]
    @Published private(set) var consoleTurns: [String: [MacConsoleTurn]] = [:]
    @Published var consoleSelectedSessionId: String?
    @Published private(set) var consoleStreamingTurn: (sessionId: String, turnId: String)?
    @Published private(set) var consoleActivity: String?
    @Published var consoleError: String?
    private var consoleTask: Task<Void, Never>?
    private var consoleAskGen = 0

    // MARK: - Embedded Web Browser Panel & Ask Warren Side Panel
    @Published var showBrowserPanel: Bool = false
    @Published var browserCurrentURL: URL = MacConfig.baseURL
    @Published var showCopilotPanel: Bool = false

    // MARK: - Terminal Polish, Command Palette & Shortcuts
    @Published var showShortcutSheet: Bool = false

    // MARK: - Welcome tour (first launch)
    /// v2: the tour walks the terminal instead of paging through cards.
    static let welcomeTourVersion = 2
    static let welcomeTourSeenKey = "bsh.mac.welcomeTourVersionSeen"
    @Published var showWelcomeTour: Bool = false
    /// Which step the walkthrough is on. The selected desk follows it, because
    /// the tour moves the real terminal rather than describing it.
    @Published var welcomeTourStep: Int = 0 {
        didSet { followWelcomeTour() }
    }

    var needsWelcomeTour: Bool {
        UserDefaults.standard.integer(forKey: Self.welcomeTourSeenKey) < Self.welcomeTourVersion
    }

    /// Runs after bootstrap and after a later sign-in. Never while the login sheet
    /// is up: the tour would fight the sheet for the window.
    func presentWelcomeTourIfNeeded() {
        guard needsWelcomeTour, session != nil, !showLoginSheet, !showWelcomeTour else { return }
        welcomeTourStep = 0
        showWelcomeTour = true
    }

    /// Put the terminal on the desk the current step is talking about.
    private func followWelcomeTour() {
        let pages = MacWelcomeTourCatalog.pages
        guard showWelcomeTour, pages.indices.contains(welcomeTourStep) else { return }
        guard let tab = pages[welcomeTourStep].tab, selectedTab != tab else { return }
        selectedTab = tab
    }

    /// Any way out counts as seen: Get started, Skip or Esc.
    func completeWelcomeTour() {
        UserDefaults.standard.set(Self.welcomeTourVersion, forKey: Self.welcomeTourSeenKey)
        showWelcomeTour = false
        welcomeTourStep = 0
    }

    /// Replay from Settings: start over without touching the seen version.
    func replayWelcomeTour() {
        welcomeTourStep = 0
        showWelcomeTour = true
    }
    @Published var showDeckIntakeSheet: Bool = false
    @Published var droppedDeckURL: URL? = nil
    @Published private(set) var isOfflineMode: Bool = false
    @Published private(set) var homeSyncError: String?
    @Published var lastSyncDate: Date? = nil
    @Published var visitedCompanyTimestamps: [String: Date] = [:]
    @Published var showOnlyModifiedCompanies: Bool = false
    private var previousVisitByCompany: [String: Date] = [:]
    private var recoveryInFlight = false
    private var lastRecoveryAt: Date = .distantPast
    /// Company ids the server answered 404 for; cleared when a company list contains them again.
    @Published private(set) var missingCompanyIds: Set<String> = []

    // MARK: - Founder Dossiers & Deep Search (Harmonic/Ampersand Grade)
    @Published var founderDossiers: [String: MacFounderDossier] = [:]
    @Published var founderDossierErrors: [String: String] = [:]
    @Published var deepSearchingFounders: Set<String> = []

    // MARK: - Deal Pipeline & CRM (Affinity Grade)
    @Published var dealPipelines: [String: MacDealPipeline] = [:]

    // MARK: - General Status
    @Published private(set) var loading = false
    @Published var error: String?
    /// Bumped whenever server-scoped state is thrown away (base URL or identity change, sign-out).
    @Published private(set) var serverEpoch = 0

    private var tempFiles: [URL] = []
    private var copilotTask: Task<Void, Never>?
    private var jobPollTask: Task<Void, Never>?
    private var alertLoopTask: Task<Void, Never>?
    private var logTailTasks: [String: Task<Void, Never>] = [:]
    private var logTailRetryAt: [String: Date] = [:]
    private var logTailDelay: [String: TimeInterval] = [:]
    private var logTailTerminal: Set<String> = []
    private var knownActiveMemoReports: Set<String> = []
    private var locallyCancelledReports: Set<String> = []
    private var bootstrapped = false
    private var bootstrapOrigin: String?
    private var bootstrapIdentity: String?
    private var followChain: Task<Void, Never>?
    private var followEditGeneration = 0
    private var followListLoaded = false
    private var pipelineReloadPending = false

    init() {
        attentionSince = UserDefaults.standard.object(forKey: Self.lastLaunchKey) as? Date
            ?? Calendar.current.date(byAdding: .hour, value: -24, to: Date())
            ?? Date()
        hydrateFromCache()
        MacAPIClient.onUnauthorized = { [weak self] url in
            Task { @MainActor in self?.handleSessionLoss(from: url) }
        }
    }

    /// The one path for a 401 from the configured server: drop the token, end the session,
    /// stop the background loops and ask to sign in. Safe to call repeatedly.
    func handleSessionLoss(from url: URL? = nil) {
        if let url, !MacAPIClient.isOwnOrigin(url) { return }
        let hadSession = session != nil
        MacConfig.clearToken()
        session = nil
        authChecked = true
        sessionRejected = true
        showLoginSheet = true
        if hadSession {
            sessionNotice = "Your session ended — sign in again."
            error = Self.sessionEndedMessage
            jobPollTask?.cancel(); jobPollTask = nil
            alertLoopTask?.cancel(); alertLoopTask = nil
            bootstrapped = false
        } else if sessionNotice == nil {
            sessionNotice = "Sign in to continue."
        }
    }

    // MARK: - Server / identity scope

    /// Drops everything that belongs to one server and one identity: per-company
    /// dictionaries, cursors, selection and background loops. The disk cache is
    /// cleared too, because it is not keyed by server.
    func resetServerScopedState(clearDiskCache: Bool = true) {
        jobPollTask?.cancel(); jobPollTask = nil
        alertLoopTask?.cancel(); alertLoopTask = nil
        // Chat panes that are still on screen keep their reference; the loop restarts below
        // against the new server instead of going quiet until the pane reappears.
        chatPollTask?.cancel(); chatPollTask = nil
        consoleTask?.cancel(); consoleTask = nil
        copilotTask?.cancel(); copilotTask = nil
        copilotContextTask?.cancel(); copilotContextTask = nil
        tickerLoadTask?.cancel(); tickerLoadTask = nil
        tickerLoadedFor = nil
        followChain?.cancel(); followChain = nil
        for (_, task) in logTailTasks { task.cancel() }
        logTailTasks = [:]
        logTailRetryAt = [:]
        logTailDelay = [:]
        logTailTerminal = []
        bootstrapped = false
        knownActiveMemoReports = []
        locallyCancelledReports = []
        chartLoadGen += 1
        workspaceLoadGen += 1
        openMemoGeneration += 1
        chatGeneration += 1
        followEditGeneration += 1
        followListLoaded = false
        pipelineReloadPending = false

        companies = []
        reports = []
        selectedCompany = nil
        selectedReport = nil
        selectedTicker = nil
        selectedChart = nil
        selectedWorkspace = nil
        chartError = nil
        loadingChart = false
        watchlist = []
        watchlistFetchedAt = nil
        gainers = []
        losers = []
        indicesQuotes = []
        news = []
        pulse = nil
        marketPulsePayload = nil
        rollup = nil
        followedCompanyIds = []
        decisionsByCompany = [:]
        pipelineLoadedAt = nil
        rollupStale = false
        pipelineError = nil
        missingCompanyIds = []
        trackingByCompany = [:]
        trackingBusy = []
        analysisByCompany = [:]
        analysisBusy = []
        evidenceByCompany = [:]
        memoEditorByCompany = [:]
        memoEditorBusy = []
        memoEditorError = [:]
        pinnedTickers = []
        bookLots = []
        alertRules = []
        deskPrefsLoaded = false
        activeJobs = []
        jobHistory = []
        jobLogs = [:]
        selectedJobId = nil
        alertEvents = []
        unseenAlertCount = 0
        closeMemo()
        openDocumentError = nil
        openingMemo = false
        copilotMessages = []
        copilotStreaming = false
        copilotCurrentThinking = nil
        copilotContext = .none
        copilotContextInfo = nil
        screenerItems = []
        digestItems = []
        intakeItems = []
        attentionLoadedAt = nil
        attentionErrors = [:]
        signals = []
        thesis = .empty
        thesisLoaded = false
        compsByCompany = [:]
        capModelByCompany = [:]
        intakeResult = nil
        portfolioDashboard = nil
        portfolioByCompany = [:]
        reservesPlan = nil
        reservesError = nil
        referenceCallsByCompany = [:]
        icMeetingsByCompany = [:]
        comparablesByCompany = [:]
        redTeamByCompany = [:]
        commentsByCompany = [:]
        mentions = nil
        chatChannels = []
        chatHandles = []
        chatChannel = "general"
        chatMessages = []
        chatLatest = nil
        auditRows = []
        transcripts = []
        transcriptById = [:]
        transcriptQuery = ""
        transcriptCompanyId = nil
        signalScoreByCompany = [:]
        profileByCompany = [:]
        earningsFilingsByCompany = [:]
        earningsFilingsFailed = []
        filingsWatch = nil
        signalMoves = nil
        numberLintByCompany = [:]
        consoleSessions = [:]
        consoleTurns = [:]
        consoleSelectedSessionId = nil
        consoleStreamingTurn = nil
        consoleActivity = nil
        consoleError = nil
        consoleSubmitting = false
        consoleAskGen += 1
        founderDossiers = [:]
        founderDossierErrors = [:]
        deepSearchingFounders = []
        dealPipelines = [:]
        isOfflineMode = false
        homeSyncError = nil
        lastRecoveryAt = .distantPast
        sessionRejected = false
        sessionNotice = nil
        lastSyncDate = nil
        error = nil

        for url in tempFiles { try? FileManager.default.removeItem(at: url) }
        tempFiles = []
        if clearDiskCache { MacDataCache.shared.clearAll() }
        serverEpoch += 1
        if chatPollRefs > 0 { restartChatPolling() }
    }

    /// Settings › Server › Save: switch servers, dropping the old server's state first.
    func switchServer(to raw: String) async {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let current = MacConfig.baseURL.absoluteString
        if trimmed.isEmpty || Self.normalizedOrigin(trimmed) == Self.normalizedOrigin(current) {
            await bootstrap()
            return
        }
        MacConfig.saveBaseURL(trimmed)
        // bootstrap() sees the changed origin and resets (keeping the per-server disk cache).
        await bootstrap()
    }

    private static func normalizedOrigin(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// The company the Research Desk opens on when nothing is selected: the one
    /// visited most recently — the web desk reopens `bsh.lastCompanyId` the same
    /// way — else the top of the directory list. It used to always take the
    /// first company, so every launch landed on the same one.
    func defaultCompany(in list: [MacCompany]) -> MacCompany? {
        let known = Set(list.map(\.id))
        let recent = visitedCompanyTimestamps
            .filter { known.contains($0.key) }
            .max { $0.value < $1.value }?
            .key
        if let recent, let company = list.first(where: { $0.id == recent }) { return company }
        return list.first
    }

    func hydrateFromCache() {
        if let cos = MacDataCache.shared.loadCompanies(), !cos.isEmpty {
            self.companies = cos
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
        if let cachedRollup = MacDataCache.shared.loadRollup() {
            self.rollup = cachedRollup
            self.rollupStale = true
        }
        if let cachedDecisions = MacDataCache.shared.loadDecisions() {
            self.decisionsByCompany = cachedDecisions
        }
        self.visitedCompanyTimestamps = MacDataCache.shared.loadBaselines()
        self.lastSyncDate = MacDataCache.shared.lastSyncDate()
        // After the visit baselines, so the last company visited can win.
        if !companies.isEmpty { self.selectedCompany = defaultCompany(in: companies) }
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
    var canUpdateSettings: Bool { can("settings:update") }

    // MARK: - Bootstrap & Refresh

    /// `open BSHResearchMac.app --args -bsh.launchTab pipeline -bsh.launchBlotter YES` opens straight onto a desk (QA and screenshots).
    func applyLaunchOverrides() {
        let defaults = UserDefaults.standard
        if let raw = defaults.string(forKey: "bsh.launchTab"), let tab = MacTab(rawValue: raw) { selectedTab = tab }
        if let raw = defaults.string(forKey: "bsh.launchTicker"), !raw.isEmpty { selectTicker(raw) }
        if defaults.bool(forKey: "bsh.launchBlotter") { showBlotter = true }
        if let raw = defaults.string(forKey: "bsh.launchBlotterTab"), let tab = MacBlotterTab(rawValue: raw) { blotterTab = tab }
            if let cid = defaults.string(forKey: "bsh.launchCompany"), let company = companies.first(where: { $0.id == cid }) { selectCompany(company) }
            if defaults.bool(forKey: "bsh.launchPalette") { openCommandPalette() }
            if defaults.bool(forKey: "bsh.launchWelcome") { showWelcomeTour = true }
            if defaults.bool(forKey: "bsh.launchFirmSearch") { showFirmSearch = true }
            if defaults.bool(forKey: "bsh.launchDecision"), let company = selectedCompany ?? companies.first { requestDecision(for: company) }
            if defaults.bool(forKey: "bsh.launchICReview"), let report = reports.first(where: \.canOpen) { openICReview(report: report) }
            if defaults.bool(forKey: "bsh.launchMemoWindow"), let report = reports.first(where: \.canOpen) { openReportWindow(report) }
            #if DEBUG
            if defaults.bool(forKey: "bsh.qaStress") { MacQAStress.start(store: self) }
            // Seeds a canned Ask Warren transcript (formatted answer + failed answer) for
            // screenshots, without calling the model.
            if defaults.bool(forKey: "bsh.launchCopilotSample") {
                var answer = MacCopilotMessage(role: .assistant, text: """
                ## Moat
                The business has a **narrow but real** moat: switching costs in its data contracts.

                - Customers sign *multi-year* terms
                - Renewal rate is above 90%
                  - but concentrated in the top 5 accounts

                1. Price rises have held for three years
                2. No competitor matches the historical dataset

                The main risk is a well-funded entrant rebuilding the dataset.
                """)
                answer.persona = .warren
                var failed = MacCopilotMessage(role: .assistant, text: "You've hit your weekly limit · resets Sep 15 at 5pm (America/Los_Angeles)")
                failed.persona = .warren
                failed.isError = true
                copilotMessages = [
                    MacCopilotMessage(role: .user, text: "Does this company have a durable moat?"),
                    answer,
                    MacCopilotMessage(role: .user, text: "What would change your mind?"),
                    failed
                ]
            }
            #endif
        }

    func bootstrap() async {
        let origin = Self.normalizedOrigin(MacConfig.baseURL.absoluteString)
        if let bootstrapOrigin, bootstrapOrigin != origin {
            // The disk cache is keyed by server, so the old server's files stay where they
            // are; clearing here would wipe the new server's folder instead.
            resetServerScopedState(clearDiskCache: false)
            hydrateFromCache()
        }
        bootstrapOrigin = origin
        var epoch = serverEpoch
        await refreshSession()
        guard epoch == serverEpoch else { return }
        if session == nil, sessionRejected { return }
        if MacConfig.requireLogin, session == nil { return }
        let identity = session.map { "\($0.auth ?? "")|\($0.email ?? "")" }
        if let bootstrapIdentity, let identity, bootstrapIdentity != identity {
            // Another user on the same server: chat cursors, drafts and selection are theirs.
            resetServerScopedState(clearDiskCache: false)
            // The reset bumped the epoch on purpose; this bootstrap continues as the new one.
            epoch = serverEpoch
        }
        if identity != nil { bootstrapIdentity = identity }

        // Local, cheap data first; third-party quotes, screeners and news must not delay it.
        async let prefs: Void = refreshDeskPrefs()
        await refreshHome()
        await prefs
        if selectedCompany == nil, let first = defaultCompany(in: companies) {
            selectedCompany = first
            if let t = first.ticker, !t.isEmpty {
                selectTicker(t)
            }
        }
        async let pipeline: Void = loadPipeline()
        async let market: Void = refreshMarket()
        async let indices: Void = refreshIndices()
        async let newsTask: Void = refreshNews()
        async let pulseTask: Void = refreshPulse()
        _ = await (pipeline, market, indices, newsTask, pulseTask)
        guard epoch == serverEpoch else { return }
        await refreshMenuBarCounts()
        guard epoch == serverEpoch else { return }
        if !bootstrapped {
            bootstrapped = true
            startBackgroundLoops()
        }
    }

    /// Menu-bar extra counts: quiet fetches that never touch `error` or the desk spinners.
    func refreshMenuBarCounts() async {
        let epoch = serverEpoch
        async let mentionsResult = try? MacAPIClient.shared.fetchMentions()
        async let dashboardResult = try? MacAPIClient.shared.fetchPortfolioDashboard()
        let (m, dash) = await (mentionsResult, dashboardResult)
        guard epoch == serverEpoch else { return }
        if let m { mentions = m }
        if let dash {
            portfolioDashboard = dash
            reservesPlan = dash.reserves
        }
    }

    // MARK: - Session

    /// The account is still on a temporary password; the server accepts it, so this is a notice, not a block.
    var needsPasswordReset: Bool { session?.mustReset == true }

    func refreshSession() async {
        let origin = MacConfig.baseURL
        do {
            session = try await MacAPIClient.shared.me()
            authChecked = true
            authError = nil
            sessionRejected = false
            sessionNotice = nil
            if error == Self.sessionEndedMessage { error = nil }
            if MacConfig.requireLogin, session?.isAnonDev == true {
                session = nil
                showLoginSheet = true
            }
        } catch MacAPIError.unauthorized {
            handleSessionLoss(from: origin)
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
        authError = nil
        sessionNotice = nil
        sessionRejected = false
        bootstrapIdentity = nil
        resetServerScopedState()
        await refreshSession()
        if session != nil {
            // Local anon-dev keeps working without a user; reload as that identity.
            await bootstrap()
        }
    }

    func refreshHome() async {
        loading = true
        defer { loading = false }
        let epoch = serverEpoch
        do {
            async let cos = MacAPIClient.shared.listCompanies()
            async let reps = MacAPIClient.shared.listReports()
            async let jobs = MacAPIClient.shared.fetchActiveJobs()

            let freshCompanies = try await cos.sorted {
                ($0.name ?? $0.id).localizedCaseInsensitiveCompare($1.name ?? $1.id) == .orderedAscending
            }
            let freshReports = try await reps
            let activeRows = try? await jobs
            guard epoch == serverEpoch else { return }
            companies = freshCompanies
            reports = freshReports
            missingCompanyIds.subtract(companies.map(\.id))
            if let activeRows { applyActiveJobs(activeRows) }

            // Re-resolve the selection by id: a company gone from this server must not stay selected.
            if let current = selectedCompany {
                selectedCompany = companies.first { $0.id == current.id }
            }
            if selectedCompany == nil, let first = defaultCompany(in: companies) {
                selectedCompany = first
            }
            if let current = selectedReport {
                selectedReport = reports.first { $0.id == current.id }
            }
            if selectedReport == nil, let firstReport = recentReports.first {
                selectedReport = firstReport
            }

            MacDataCache.shared.saveCompanies(companies)
            MacDataCache.shared.saveReports(reports)
            lastSyncDate = Date()
            homeSyncError = nil
            noteReachability(true)
        } catch MacAPIError.unauthorized {
            handleSessionLoss()
        } catch {
            guard epoch == serverEpoch else { return }
            noteSyncFailure(error)
        }
    }

    /// Index quotes and the market-pulse payload: third-party calls kept out of `refreshHome`.
    func refreshIndices() async {
        async let pulsePayload = MacAPIClient.shared.fetchMarketPulsePayload()
        async let indices = MacAPIClient.shared.fetchQuotes(tickers: ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT"])
        let payload = try? await pulsePayload
        let quotes = try? await indices
        if let payload { marketPulsePayload = payload }
        if let quotes { indicesQuotes = quotes }
    }

    /// Sync state has two writers only: `noteSyncFailure` records what broke (transport
    /// errors mean offline, HTTP errors mean a degraded server) and `noteReachability(true)`,
    /// called by any succeeding poll, runs one recovery pass while either flag is up.
    func noteSyncFailure(_ error: Error) {
        if error is CancellationError { return }
        if case MacAPIError.unauthorized = error { return }
        homeSyncError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        if case MacAPIError.transport = error { isOfflineMode = true } else { isOfflineMode = false }
    }

    func noteReachability(_ reachable: Bool) {
        if !reachable {
            isOfflineMode = true
            return
        }
        let degraded = isOfflineMode || homeSyncError != nil
        isOfflineMode = false
        guard degraded, !recoveryInFlight, Date().timeIntervalSince(lastRecoveryAt) >= 10 else { return }
        recoveryInFlight = true
        lastRecoveryAt = Date()
        Task {
            await refreshHome()
            if homeSyncError == nil {
                await refreshNews()
                await refreshPulse()
            }
            recoveryInFlight = false
        }
    }

    func refreshReports() async {
        let epoch = serverEpoch
        if let reps = try? await MacAPIClient.shared.listReports(), epoch == serverEpoch {
            reports = reps
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
        guard canRunTasks else {
            if let company { showCompany(company) }
            return
        }
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
        let epoch = serverEpoch
        do {
            let res = try await MacAPIClient.shared.fetchDeskPrefs()
            guard epoch == serverEpoch else { return }
            // The server's list is the truth even when empty; index tickers are a display fallback only.
            pinnedTickers = res.watchlist.map { $0.uppercased() }
            bookLots = res.lots
            alertRules = res.rules
            deskPrefsLoaded = true
        } catch {
            // Keep current local state; a later save re-reads before writing.
        }
    }

    /// Never write local placeholder state over the shared blob: a save needs a
    /// successful load first.
    private func ensureDeskPrefsLoaded() async -> Bool {
        guard canWriteDesk else {
            self.error = "A read-only session cannot change the desk."
            return false
        }
        if deskPrefsLoaded { return true }
        await refreshDeskPrefs()
        if !deskPrefsLoaded {
            self.error = "Desk preferences could not be loaded from the server, so the change was not saved."
        }
        return deskPrefsLoaded
    }

    func isPinned(_ ticker: String) -> Bool {
        pinnedTickers.contains(ticker.uppercased())
    }

    /// Every desk edit goes through here: the local change is applied, saved, and rolled
    /// back when the save fails so a retry never appends a second copy.
    private func changeDeskState(_ change: () -> Bool) async -> Bool {
        guard await ensureDeskPrefsLoaded() else { return false }
        let epoch = serverEpoch
        let snapshot = (pinnedTickers, bookLots, alertRules)
        guard change() else { return false }
        let ok = await saveDeskState()
        if !ok, epoch == serverEpoch {
            (pinnedTickers, bookLots, alertRules) = snapshot
        }
        return ok
    }

    @discardableResult
    func toggleWatchlist(_ ticker: String) async -> Bool {
        let t = ticker.uppercased()
        let ok = await changeDeskState {
            if pinnedTickers.contains(t) {
                pinnedTickers.removeAll { $0 == t }
            } else {
                pinnedTickers.append(t)
            }
            return true
        }
        await refreshMarket()
        return ok
    }

    @discardableResult
    func addLot(ticker: String, shares: Double, costBasis: Double) async -> Bool {
        guard shares.isFinite, costBasis.isFinite else {
            self.error = "Shares and cost basis must be numbers."
            return false
        }
        return await changeDeskState {
            bookLots.append(MacBookLot(
                id: UUID().uuidString,
                ticker: ticker.uppercased(),
                shares: shares,
                costBasis: costBasis
            ))
            return true
        }
    }

    @discardableResult
    func removeLot(id: String) async -> Bool {
        await changeDeskState {
            bookLots.removeAll { $0.id == id }
            return true
        }
    }

    @discardableResult
    func addAlertRule(ticker: String, threshold: Double, direction: String, kind: String = "price") async -> Bool {
        guard threshold.isFinite else {
            self.error = "The alert threshold must be a number."
            return false
        }
        return await changeDeskState {
            alertRules.append(MacAlertRule(
                id: UUID().uuidString,
                ticker: ticker.uppercased(),
                kind: kind,
                threshold: threshold,
                direction: direction,
                enabled: true
            ))
            return true
        }
    }

    @discardableResult
    func toggleAlertRule(id: String) async -> Bool {
        await changeDeskState {
            guard let idx = alertRules.firstIndex(where: { $0.id == id }) else { return false }
            alertRules[idx].enabled.toggle()
            return true
        }
    }

    @discardableResult
    func deleteAlertRule(id: String) async -> Bool {
        await changeDeskState {
            alertRules.removeAll { $0.id == id }
            return true
        }
    }

    /// Rules the server can evaluate on a quote check; drives the background loop and "Check now".
    var armedAlertRules: [MacAlertRule] {
        alertRules.filter { $0.enabled && ["price", "pct"].contains($0.kind.lowercased()) }
    }

    @discardableResult
    private func saveDeskState() async -> Bool {
        guard deskPrefsLoaded else { return false }
        let epoch = serverEpoch
        do {
            let saved = try await MacAPIClient.shared.saveDeskPrefs(
                watchlist: pinnedTickers,
                lots: bookLots,
                rules: alertRules
            )
            guard epoch == serverEpoch else { return false }
            pinnedTickers = saved.watchlist
            bookLots = saved.lots
            alertRules = saved.rules
            return true
        } catch {
            self.error = "Sync with desk preferences failed: \(error.localizedDescription)"
            return false
        }
    }

    // MARK: - Market Radar & Charting

    func refreshMarket() async {
        let epoch = serverEpoch
        do {
            let known = Set(companies.map(\.id))
            let followedTickers = followedCompanyIds
                .filter { known.contains($0) }
                .compactMap { id in companies.first { $0.id == id }?.ticker?.uppercased() }
            let companyTickers = companies.compactMap { $0.ticker?.uppercased() }
            // Pinned first so a long list can never truncate a pin away.
            var seen: Set<String> = []
            let ordered = (pinnedTickers.map { $0.uppercased() } + MacAPIClient.defaultWatchlist + followedTickers + companyTickers)
                .filter { !$0.isEmpty && seen.insert($0).inserted }
            let requested = Array(ordered.prefix(40))

            async let quotes = MacAPIClient.shared.fetchQuotes(tickers: requested)
            async let screeners = MacAPIClient.shared.fetchScreeners(limit: 12)

            let fresh = try await quotes
            guard epoch == serverEpoch else { return }
            // The client sorts alphabetically; restore request order so pinned tickers lead
            // (the Home card and the tape take a prefix of this list).
            let rank = Dictionary(uniqueKeysWithValues: ordered.enumerated().map { ($0.element, $0.offset) })
            watchlist = fresh.sorted { (rank[$0.ticker] ?? Int.max) < (rank[$1.ticker] ?? Int.max) }
            watchlistFetchedAt = Date()
            let s = try await screeners
            guard epoch == serverEpoch else { return }
            gainers = s.gainers
            losers = s.losers

            if selectedTicker == nil, let first = watchlist.first?.ticker {
                selectTicker(first)
            }
            MacDataCache.shared.saveQuotes(watchlist)
        } catch {
            guard epoch == serverEpoch else { return }
            self.error = error.localizedDescription
        }
    }

    func selectTicker(_ ticker: String) {
        let t = ticker.uppercased()
        if t != selectedTicker {
            selectedChart = nil
            selectedWorkspace = nil
            chartError = nil
            tickerLoadTask?.cancel()
            tickerLoadTask = nil
            tickerLoadedFor = nil
        } else if chartError != nil {
            // Re-selecting a ticker whose chart failed is a retry.
            tickerLoadedFor = nil
        }
        selectedTicker = t
        loadSelectedTickerIfVisible()
    }

    /// Starts the chart + workspace pair once per ticker (again after a failed chart load), and
    /// only while Market Radar is the active desk (it is the only reader of `selectedChart` /
    /// `selectedWorkspace`).
    private func loadSelectedTickerIfVisible() {
        guard selectedTab == .market, let t = selectedTicker else { return }
        guard tickerLoadedFor != t || (chartError != nil && !loadingChart) else { return }
        tickerLoadedFor = t
        tickerLoadTask?.cancel()
        tickerLoadTask = Task {
            async let chart: Void = loadChart(range: selectedChartRange)
            async let workspace: Void = loadWorkspace()
            _ = await (chart, workspace)
        }
    }

    func loadChart(range: MacChartRange) async {
        guard let ticker = selectedTicker else { return }
        selectedChartRange = range
        chartLoadGen += 1
        let gen = chartLoadGen
        loadingChart = true
        chartError = nil
        defer { if gen == chartLoadGen { loadingChart = false } }
        do {
            let payload = try await MacAPIClient.shared.fetchChart(ticker: ticker, range: range)
            guard gen == chartLoadGen, ticker == selectedTicker, range == selectedChartRange else { return }
            selectedChart = payload
        } catch {
            guard gen == chartLoadGen, ticker == selectedTicker, !Task.isCancelled else { return }
            selectedChart = nil
            chartError = "Chart unavailable for \(ticker)"
        }
    }

    func loadWorkspace() async {
        guard let ticker = selectedTicker else { return }
        workspaceLoadGen += 1
        let gen = workspaceLoadGen
        do {
            let ws = try await MacAPIClient.shared.fetchWorkspace(ticker: ticker)
            guard gen == workspaceLoadGen, ticker == selectedTicker else { return }
            selectedWorkspace = ws
        } catch {
            guard gen == workspaceLoadGen, ticker == selectedTicker, !Task.isCancelled else { return }
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
        } catch MacAPIError.http(404, _) {
            pulse = nil
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
                let interval: TimeInterval = self.activeJobs.isEmpty ? 15 : 3
                try? await Task.sleep(for: .seconds(max(interval, MacAPIClient.retryAfterDelay())))
            }
        }
        alertLoopTask?.cancel()
        alertLoopTask = Task { [weak self] in
            await self?.refreshAlertEvents()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(max(60, MacAPIClient.retryAfterDelay())))
                guard let self else { return }
                if Self.isUSMarketOpen(), !self.armedAlertRules.isEmpty {
                    await self.runAlertCheck(notify: true, reveal: false)
                }
                await self.refreshMenuBarCounts()
            }
        }
    }

    func refreshJobs() async {
        let epoch = serverEpoch
        async let active = MacAPIClient.shared.fetchActiveJobs()
        async let history = MacAPIClient.shared.fetchJobHistory(limit: 30)
        do {
            let rows = try await active
            guard epoch == serverEpoch else { return }
            applyActiveJobs(rows)
            noteReachability(true)
        } catch {
            guard epoch == serverEpoch else { return }
            noteSyncFailure(error)
        }
        if let rows = try? await history, epoch == serverEpoch, rows != jobHistory {
            jobHistory = rows
        }
    }

    private func applyActiveJobs(_ rows: [MacActiveJob]) {
        let previous = knownActiveMemoReports
        if rows != activeJobs { activeJobs = rows }
        let nowActive = Set(rows.filter(\.isMemo).compactMap(\.reportId))
        knownActiveMemoReports = nowActive

        // Memo runs that just left the active list → refresh the library and notify.
        let finished = previous.subtracting(nowActive)
        if !finished.isEmpty {
            let cancelled = locallyCancelledReports.intersection(finished)
            locallyCancelledReports.subtract(finished)
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
                        } else if cancelled.contains(reportId) || report.isCancelled {
                            MacNotifier.post(
                                title: "Memo run cancelled — \(company)",
                                body: report.displayTitle,
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
        for id in Array(logTailRetryAt.keys) where !ids.contains(id) {
            logTailRetryAt[id] = nil
            logTailDelay[id] = nil
        }
        logTailTerminal = logTailTerminal.intersection(ids)
        let now = Date()
        for job in rows where logTailTasks[job.id] == nil {
            guard let stream = job.streamUrl, !stream.isEmpty else { continue }
            // A stream that already delivered its terminal event is not reopened; a dropped
            // one reconnects with backoff.
            if logTailTerminal.contains(job.id) { continue }
            if let retryAt = logTailRetryAt[job.id], retryAt > now { continue }
            logTailTasks[job.id] = Task { [weak self] in
                await self?.tailJobLog(jobId: job.id, stream: stream)
            }
        }
    }

    /// Every connection replays the run from the start, so the buffer replaces (never appends to)
    /// the previous connection's lines.
    private func tailJobLog(jobId: String, stream: String) async {
        let events = MacAPIClient.shared.streamEvents(path: stream)
        var buffer: [String] = []
        var pending = 0
        var sawTerminal = false
        var lastFlush = Date.distantPast
        var failed = false
        func flush() {
            let tail = Array(buffer.suffix(80))
            if jobLogs[jobId] != tail { jobLogs[jobId] = tail }
            pending = 0
            lastFlush = Date()
        }
        do {
            for try await event in events {
                guard !Task.isCancelled else { break }
                if let obj = event.json {
                    let type = ((obj["type"] as? String) ?? event.event ?? "").lowercased()
                    if ["done", "error", "cancelled", "recovered", "complete", "completed"].contains(type) { sawTerminal = true }
                }
                let line = Self.logLine(from: event)
                guard !line.isEmpty else { continue }
                buffer.append(line)
                if buffer.count > 400 { buffer.removeFirst(buffer.count - 400) }
                pending += 1
                if pending >= 50 || Date().timeIntervalSince(lastFlush) > 0.1 { flush() }
            }
        } catch {
            failed = !Task.isCancelled
        }
        flush()
        guard !Task.isCancelled else { return }
        logTailTasks[jobId] = nil
        if sawTerminal {
            logTailTerminal.insert(jobId)
        } else {
            let delay = min(60, max(3, (logTailDelay[jobId] ?? 1.5) * 2))
            logTailDelay[jobId] = delay
            logTailRetryAt[jobId] = Date().addingTimeInterval(failed ? delay : max(delay, 3))
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
            locallyCancelledReports.insert(reportId)
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

    /// `reveal` switches the blotter to Alerts; the background loop passes false so a fire
    /// never tears down a Chat or Signals pane with typed text in it.
    func runAlertCheck(notify: Bool, reveal: Bool = true) async {
        guard !checkingAlerts else { return }
        checkingAlerts = true
        defer { checkingAlerts = false }
        do {
            let result = try await MacAPIClient.shared.runAlertCheck()
            lastAlertCheck = Date()
            let fired = result.fired ?? []
            if notify {
                for f in fired {
                    MacNotifier.post(
                        title: "Price alert — \(f.ticker ?? "")",
                        body: f.headline,
                        identifier: "alert-\(f.id)"
                    )
                }
            }
            await refreshAlertEvents()
            if !fired.isEmpty {
                let paneHasDraft = showBlotter && [.chat, .signals, .audit].contains(blotterTab)
                if reveal || !paneHasDraft {
                    showBlotter = true
                    blotterTab = .alerts
                } else {
                    unseenAlertCount += fired.count
                }
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
    /// Followed companies drive the board; stale follow ids (companies removed on the server) are ignored,
    /// and with nothing followed every company is on the board.
    var pipelineCompanyIds: [String] {
        let followed = validFollowedIds
        return followed.isEmpty ? companies.map(\.id) : followed
    }

    /// Follow ids that still exist on this server (unpruned while the company list is loading).
    var validFollowedIds: [String] {
        guard !companies.isEmpty else { return followedCompanyIds }
        let known = Set(companies.map(\.id))
        return followedCompanyIds.filter { known.contains($0) }
    }

    func rollupRow(for companyId: String) -> MacRollupRow? {
        rollupById[companyId]
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
        guard !pipelineLoading else {
            pipelineReloadPending = true
            return
        }
        pipelineLoading = true
        defer { pipelineLoading = false }
        let epoch = serverEpoch
        let followGen = followEditGeneration
        if let ids = try? await MacAPIClient.shared.fetchTrackingWatchlist() {
            guard epoch == serverEpoch else { return }
            // A follow edit queued meanwhile owns the list; the GET result would be stale.
            if followGen == followEditGeneration {
                followedCompanyIds = ids
                followListLoaded = true
            }
        }
        // Nothing to roll up before the company list is known; an empty rollup must not be cached.
        guard !companies.isEmpty else { return }
        let ids = pipelineCompanyIds
        do {
            let fresh = try await MacAPIClient.shared.fetchTrackingRollup(companyIds: ids)
            guard epoch == serverEpoch else { return }
            rollup = fresh
            rollupStale = false
            pipelineError = nil
            attentionErrors["pipeline"] = nil
            pipelineLoadedAt = Date()
            MacDataCache.shared.saveRollup(fresh)
        } catch MacAPIError.unauthorized {
            handleSessionLoss()
            return
        } catch {
            guard epoch == serverEpoch, !(error is CancellationError) else { return }
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            pipelineError = message
            rollupStale = rollup != nil
            attentionErrors["pipeline"] = message
            self.error = "Pipeline rollup failed: \(message)"
        }
        await loadDecisions(for: pipelineCompanyIds)
        guard epoch == serverEpoch else { return }
        MacDataCache.shared.saveDecisions(decisionsByCompany)
        if pipelineReloadPending {
            pipelineReloadPending = false
            pipelineLoading = false
            await loadPipeline()
        }
    }

    func loadDecisions(for ids: [String]) async {
        let epoch = serverEpoch
        let fetched = await withTaskGroup(of: (String, [MacDecision]?).self) { group in
            var out: [String: [MacDecision]] = [:]
            var iterator = ids.makeIterator()
            var inFlight = 0
            func enqueue() {
                guard let id = iterator.next() else { return }
                inFlight += 1
                group.addTask {
                    (id, try? await MacAPIClient.shared.fetchDecisions(companyId: id))
                }
            }
            for _ in 0..<8 { enqueue() }
            while inFlight > 0, let (id, list) = await group.next() {
                inFlight -= 1
                if let list { out[id] = Self.sortedDecisions(list) }
                enqueue()
            }
            return out
        }
        guard epoch == serverEpoch else { return }
        decisionsByCompany.merge(fetched) { _, new in new }
    }

    /// Server order: `decided_at` descending, ties keep the older record first.
    private static func sortedDecisions(_ list: [MacDecision]) -> [MacDecision] {
        list.enumerated().sorted { a, b in
            let ka = a.element.decidedAt ?? a.element.createdAt ?? ""
            let kb = b.element.decidedAt ?? b.element.createdAt ?? ""
            if ka != kb { return ka > kb }
            return a.offset < b.offset
        }.map(\.element)
    }

    /// Optimistic and serialized: every PUT sends the latest list, never a stale snapshot.
    func toggleFollow(_ companyId: String) async {
        if !followListLoaded {
            if let ids = try? await MacAPIClient.shared.fetchTrackingWatchlist() {
                followedCompanyIds = ids
                followListLoaded = true
            } else {
                self.error = "The follow list could not be loaded; try again."
                return
            }
        }
        let wasFollowed = followedCompanyIds.contains(companyId)
        var ids = validFollowedIds
        if wasFollowed {
            ids.removeAll { $0 == companyId }
        } else {
            ids.append(companyId)
        }
        followedCompanyIds = ids
        followEditGeneration += 1
        let gen = followEditGeneration
        let epoch = serverEpoch
        let previous = followChain
        followChain = Task { [weak self] in
            _ = await previous?.value
            guard let self, epoch == self.serverEpoch else { return }
            let body = self.followedCompanyIds
            do {
                let saved = try await MacAPIClient.shared.saveTrackingWatchlist(body)
                guard epoch == self.serverEpoch else { return }
                if gen == self.followEditGeneration { self.followedCompanyIds = saved }
            } catch {
                guard epoch == self.serverEpoch else { return }
                self.error = error.localizedDescription
                if wasFollowed {
                    if !self.followedCompanyIds.contains(companyId) { self.followedCompanyIds.append(companyId) }
                } else {
                    self.followedCompanyIds.removeAll { $0 == companyId }
                }
            }
            if gen == self.followEditGeneration {
                await self.loadPipeline()
            }
        }
        await followChain?.value
    }

    /// Server-side, synchronous, can take minutes — runs detached and notifies on completion.
    func syncAllTracking() {
        guard !pipelineSyncing else { return }
        let ids = validFollowedIds
        guard !ids.isEmpty else {
            self.error = "Follow at least one company to sync its tracked news."
            return
        }
        pipelineSyncing = true
        Task {
            do {
                let created = try await MacAPIClient.shared.syncAllTracking(companyIds: ids)
                MacNotifier.post(
                    title: "Tracking sync finished",
                    body: created == 0 ? "Synced \(ids.count) companies · no new tracked news." : "\(created) new tracked item(s).",
                    identifier: "tracking-sync"
                )
                await loadPipeline()
                for id in Array(trackingByCompany.keys) where companies.contains(where: { $0.id == id }) {
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
            var list = decisionsByCompany[companyId] ?? []
            list.insert(decision, at: 0)
            decisionsByCompany[companyId] = Self.sortedDecisions(list)
            await loadDecisions(for: [companyId])
            MacDataCache.shared.saveDecisions(decisionsByCompany)
            Task { await loadPipeline() }
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

    /// `create: false` is the read the dossier does on sight: a company with no
    /// Memo Studio session stays without one (the server answers 404, which is
    /// "nothing logged yet", not an error). Refresh and the tools still create.
    func loadMemoAnalysis(_ companyId: String, create: Bool = true) async {
        guard !analysisBusy.contains(companyId) else { return }
        analysisBusy.insert(companyId)
        defer { analysisBusy.remove(companyId) }
        do {
            analysisByCompany[companyId] = try await MacAPIClient.shared.fetchMemoAnalysis(
                companyId: companyId,
                create: create
            )
        } catch MacAPIError.http(let status, _) where status == 404 && !create {
            // No session yet — nothing to show, and nothing went wrong.
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

    // MARK: - Memo Studio Editor State & Actions

    func loadMemoEditor(_ companyId: String) async {
        guard !memoEditorBusy.contains(companyId) else { return }
        memoEditorBusy.insert(companyId)
        defer { memoEditorBusy.remove(companyId) }
        do {
            let state = try await MacAPIClient.shared.fetchMemoEditor(companyId: companyId)
            memoEditorByCompany[companyId] = state
            memoEditorError[companyId] = nil
        } catch {
            memoEditorError[companyId] = error.localizedDescription
        }
    }

    func patchMemoCard(
        companyId: String,
        sectionId: String,
        cardId: String,
        included: Bool? = nil,
        expanded: Bool? = nil,
        title: String? = nil,
        category: String? = nil,
        severity: String? = nil,
        likelihood: String? = nil,
        agentRating: String? = nil
    ) async {
        do {
            let updated = try await MacAPIClient.shared.patchMemoEditorCard(
                companyId: companyId,
                sectionId: sectionId,
                cardId: cardId,
                included: included,
                expanded: expanded,
                title: title,
                category: category,
                severity: severity,
                likelihood: likelihood,
                agentRating: agentRating
            )
            memoEditorByCompany[companyId] = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    func addMemoCard(
        companyId: String,
        sectionId: String,
        title: String,
        category: String? = nil,
        severity: String? = nil,
        rating: String? = nil,
        likelihood: String? = nil,
        bullets: [String]? = nil
    ) async {
        do {
            let updated = try await MacAPIClient.shared.addMemoEditorCard(
                companyId: companyId,
                sectionId: sectionId,
                title: title,
                category: category,
                severity: severity,
                rating: rating,
                likelihood: likelihood,
                bullets: bullets
            )
            memoEditorByCompany[companyId] = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteMemoCard(companyId: String, sectionId: String, cardId: String) async {
        do {
            let updated = try await MacAPIClient.shared.deleteMemoEditorCard(
                companyId: companyId,
                sectionId: sectionId,
                cardId: cardId
            )
            memoEditorByCompany[companyId] = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    func reorderMemoCards(companyId: String, sectionId: String, orderedIds: [String]) async {
        do {
            let updated = try await MacAPIClient.shared.reorderMemoEditorCards(
                companyId: companyId,
                sectionId: sectionId,
                orderedIds: orderedIds
            )
            memoEditorByCompany[companyId] = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    func moveMemoCard(companyId: String, sectionId: String, cardId: String, direction: String) async {
        do {
            let updated = try await MacAPIClient.shared.moveMemoEditorCard(
                companyId: companyId,
                sectionId: sectionId,
                cardId: cardId,
                direction: direction
            )
            memoEditorByCompany[companyId] = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refineRisk(companyId: String, riskId: String, framing: String = "other", analystNote: String = "") async {
        do {
            try await MacAPIClient.shared.refineMemoRisk(
                companyId: companyId,
                riskId: riskId,
                framing: framing,
                analystNote: analystNote
            )
            await loadMemoAnalysis(companyId)
            await loadMemoEditor(companyId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func launchCustomReport(
        companyId: String,
        config: MacReportCustomizerConfig
    ) async throws -> MacReport {
        let rep: MacReport
        if config.generationMode == "studio_review" {
            rep = try await MacAPIClient.shared.startMemoStudioInvestigate(
                companyId: companyId,
                reportType: config.reportType
            )
        } else {
            rep = try await MacAPIClient.shared.createReport(
                companyId: companyId,
                reportType: config.reportType,
                audience: config.audience,
                language: config.language,
                reportMode: config.reportMode,
                quality: config.quality
            )
        }
        handleCreatedReport(rep)
        return rep
    }

    func generateReportFromStudio(reportId: String) async throws -> MacReport {
        let rep = try await MacAPIClient.shared.generateMemoFromStudio(reportId: reportId)
        handleCreatedReport(rep)
        return rep
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
        // The baseline a badge compares against is the visit before this one, so opening a
        // company does not instantly hide what changed since the last look.
        if let current = visitedCompanyTimestamps[companyId], previousVisitByCompany[companyId] == nil {
            previousVisitByCompany[companyId] = current
        }
        visitedCompanyTimestamps[companyId] = Date()
        MacDataCache.shared.saveBaselines(visitedCompanyTimestamps)
    }

    private func visitBaseline(for companyId: String) -> Date? {
        previousVisitByCompany[companyId] ?? visitedCompanyTimestamps[companyId]
    }

    func isCompanyModified(_ companyId: String) -> Bool {
        guard let baseline = visitBaseline(for: companyId) else {
            return true
        }
        for r in reports where r.companyId == companyId {
            if let d = MacTimeFormat.parse(r.updatedAt ?? r.createdAt), d > baseline {
                return true
            }
        }
        return false
    }

    func isReportNew(_ report: MacReport) -> Bool {
        guard let cid = report.companyId, let baseline = visitBaseline(for: cid) else {
            return true
        }
        if let d = MacTimeFormat.parse(report.updatedAt ?? report.createdAt), d > baseline {
            return true
        }
        return false
    }

    // MARK: - Pitch Deck Intake

    func ingestDeck(url: URL) {
        droppedDeckURL = url
        showDeckIntakeSheet = true
    }

    // MARK: - Thesis

    func loadThesis() async {
        if let t = try? await MacAPIClient.shared.fetchThesis() {
            thesis = t
            thesisLoaded = true
        }
    }

    @discardableResult
    func saveThesis(_ draft: MacThesis) async -> Bool {
        do {
            thesis = try await MacAPIClient.shared.saveThesis(draft)
            thesisLoaded = true
            await loadPipeline()
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func thesisFit(for companyId: String) -> MacThesisScore? {
        rollupRow(for: companyId)?.thesisFit
    }

    // MARK: - Comps & cap model

    func loadComps(_ companyId: String, refresh: Bool) async {
        do {
            compsByCompany[companyId] = try await MacAPIClient.shared.fetchComps(companyId: companyId, refresh: refresh)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func saveCompsPeers(_ companyId: String, tickers: [String]) async {
        do {
            try await MacAPIClient.shared.saveCompsPeers(companyId: companyId, tickers: tickers)
            await loadComps(companyId, refresh: true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadCapModel(_ companyId: String) async {
        if let model = try? await MacAPIClient.shared.fetchCapModel(companyId: companyId) {
            capModelByCompany[companyId] = model
        }
    }

    @discardableResult
    func saveCapModel(_ companyId: String, inputs: MacCapModelInputs) async -> Bool {
        do {
            capModelByCompany[companyId] = try await MacAPIClient.shared.saveCapModel(companyId: companyId, inputs: inputs)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    // MARK: - Deck intake (real upload + extraction)

    func intakeDeck(fileURL: URL, companyName: String?, companyId: String?) async -> MacIntakeResult? {
        intakeBusy = true
        defer { intakeBusy = false }
        do {
            let result = try await MacAPIClient.shared.intakeDeck(fileURL: fileURL, companyName: companyName, companyId: companyId)
            intakeResult = result
            await refreshHome()
            await loadPipeline()
            return result
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            return nil
        }
    }

    func summarizeFile(companyId: String, fileId: String) async {
        do {
            try await MacAPIClient.shared.startFileSummary(companyId: companyId, fileId: fileId)
            showBlotter = true
            blotterTab = .jobs
            await refreshJobs()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Private portfolio

    func loadPortfolioDashboard() async {
        portfolioLoading = true
        defer { portfolioLoading = false }
        do {
            let dash = try await MacAPIClient.shared.fetchPortfolioDashboard()
            portfolioDashboard = dash
            reservesPlan = dash.reserves
            reservesError = dash.reserves == nil ? "Reserves plan missing from the portfolio response." : nil
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            reservesError = message
            self.error = message
        }
    }

    /// A per-company 404 means the server no longer knows the id; desks show that instead of a spinner.
    private func noteCompanyFetchFailure(_ companyId: String, _ error: Error) {
        if case MacAPIError.http(404, _) = error { missingCompanyIds.insert(companyId) }
    }

    func loadPortfolio(_ companyId: String) async {
        do {
            portfolioByCompany[companyId] = try await MacAPIClient.shared.fetchPortfolio(companyId: companyId)
        } catch {
            noteCompanyFetchFailure(companyId, error)
        }
    }

    private func applyPortfolio(_ record: MacPortfolioCompany) async {
        portfolioByCompany[record.companyId] = record
        await loadPortfolioDashboard()
    }

    @discardableResult
    func savePosition(_ companyId: String, fields: [String: Any?]) async -> Bool {
        do {
            await applyPortfolio(try await MacAPIClient.shared.updatePortfolioPosition(companyId: companyId, fields: fields))
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    @discardableResult
    func addKpi(_ companyId: String, fields: [String: Any?]) async -> Bool {
        do {
            await applyPortfolio(try await MacAPIClient.shared.addPortfolioKpi(companyId: companyId, fields: fields))
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    @discardableResult
    func addFounderUpdate(_ companyId: String, text: String, asOf: String?, subject: String, source: String) async -> MacPortfolioCompany? {
        do {
            let record = try await MacAPIClient.shared.addFounderUpdate(companyId: companyId, text: text, asOf: asOf, subject: subject, source: source)
            await applyPortfolio(record)
            return record
        } catch { self.error = error.localizedDescription; return nil }
    }

    @discardableResult
    func addMark(_ companyId: String, valueUsd: Double, basis: String, asOf: String?, note: String) async -> Bool {
        do {
            await applyPortfolio(try await MacAPIClient.shared.addPortfolioMark(companyId: companyId, valueUsd: valueUsd, basis: basis, asOf: asOf, note: note))
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func deletePortfolioItem(_ companyId: String, kind: String, itemId: String) async {
        do {
            await applyPortfolio(try await MacAPIClient.shared.deletePortfolioItem(companyId: companyId, kind: kind, itemId: itemId))
        } catch { self.error = error.localizedDescription }
    }

    @discardableResult
    func saveReserves(_ settings: MacReservesSettings) async -> Bool {
        do {
            reservesPlan = try await MacAPIClient.shared.saveReserves(settings)
            reservesError = nil
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    /// Downloads the LP tear sheet and lets the user pick where to save it.
    func exportTearSheet(_ companyId: String, companyName: String) async {
        do {
            let data = try await MacAPIClient.shared.downloadTearSheet(companyId: companyId)
            #if os(macOS)
            let panel = NSSavePanel()
            panel.allowedContentTypes = [.init(filenameExtension: "docx") ?? .data]
            panel.nameFieldStringValue = "\(companyName) — LP tear sheet.docx"
            panel.canCreateDirectories = true
            if panel.runModal() == .OK, let url = panel.url {
                try data.write(to: url, options: .atomic)
                NSWorkspace.shared.activateFileViewerSelecting([url])
            }
            #else
            _ = data
            #endif
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - IC room

    var memberName: String { session?.displayName ?? "me" }
    var canEditMemo: Bool { can("memo:edit") }

    func loadICRoom(_ companyId: String) async {
        async let refs = MacAPIClient.shared.fetchReferenceCalls(companyId: companyId)
        async let meetings = MacAPIClient.shared.fetchICMeetings(companyId: companyId)
        async let comps = MacAPIClient.shared.fetchComparables(companyId: companyId)
        async let red = MacAPIClient.shared.fetchRedTeam(companyId: companyId)
        do { referenceCallsByCompany[companyId] = try await refs } catch { noteCompanyFetchFailure(companyId, error) }
        do { icMeetingsByCompany[companyId] = try await meetings.items } catch { noteCompanyFetchFailure(companyId, error) }
        do { comparablesByCompany[companyId] = try await comps } catch { noteCompanyFetchFailure(companyId, error) }
        do { redTeamByCompany[companyId] = try await red } catch { noteCompanyFetchFailure(companyId, error) }
    }

    func addReferenceCall(_ companyId: String, fields: [String: Any?]) async -> Bool {
        do {
            referenceCallsByCompany[companyId] = try await MacAPIClient.shared.addReferenceCall(companyId: companyId, fields: fields)
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func deleteReferenceCall(_ companyId: String, itemId: String) async {
        do {
            referenceCallsByCompany[companyId] = try await MacAPIClient.shared.deleteReferenceCall(companyId: companyId, itemId: itemId)
        } catch { self.error = error.localizedDescription }
    }

    private func upsertMeeting(_ companyId: String, _ meeting: MacICMeeting) {
        var list = icMeetingsByCompany[companyId] ?? []
        if let i = list.firstIndex(where: { $0.id == meeting.id }) { list[i] = meeting } else { list.insert(meeting, at: 0) }
        icMeetingsByCompany[companyId] = list
    }

    func openICMeeting(_ companyId: String, title: String, reportId: String?) async -> Bool {
        do {
            upsertMeeting(companyId, try await MacAPIClient.shared.openICMeeting(companyId: companyId, title: title, reportId: reportId))
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func castICVote(_ companyId: String, meetingId: String, vote: String, conviction: Int?, note: String) async -> Bool {
        do {
            let member = session?.isAnonDev == true ? memberName : nil
            upsertMeeting(companyId, try await MacAPIClient.shared.castICVote(companyId: companyId, meetingId: meetingId, member: member, vote: vote, conviction: conviction, note: note))
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func closeICMeeting(_ companyId: String, meetingId: String, recordDecision: Bool, explanation: String) async -> Bool {
        do {
            upsertMeeting(companyId, try await MacAPIClient.shared.closeICMeeting(companyId: companyId, meetingId: meetingId, recordDecision: recordDecision, explanation: explanation))
            if recordDecision { await loadDecisions(for: [companyId]) }
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    /// Starts the red-team job and polls until it finishes (results are small; no SSE needed).
    func runRedTeam(_ companyId: String) async {
        do {
            try await MacAPIClient.shared.startRedTeam(companyId: companyId)
        } catch {
            self.error = error.localizedDescription
            return
        }
        for _ in 0..<300 {
            try? await Task.sleep(for: .seconds(max(3, MacAPIClient.retryAfterDelay())))
            guard let rt = try? await MacAPIClient.shared.fetchRedTeam(companyId: companyId) else { continue }
            redTeamByCompany[companyId] = rt
            if !rt.isRunning { break }
        }
    }

    // MARK: - Firm layer

    func loadComments(_ companyId: String) async {
        do {
            commentsByCompany[companyId] = try await MacAPIClient.shared.fetchComments(companyId: companyId)
        } catch {
            noteCompanyFetchFailure(companyId, error)
        }
    }

    @discardableResult
    func addComment(_ companyId: String, text: String, target: MacCommentTarget?, parentId: String? = nil) async -> Bool {
        do {
            _ = try await MacAPIClient.shared.addComment(companyId: companyId, text: text, target: target, parentId: parentId)
            await loadComments(companyId)
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func resolveComment(_ companyId: String, commentId: String, resolved: Bool) async {
        do {
            _ = try await MacAPIClient.shared.resolveComment(companyId: companyId, commentId: commentId, resolved: resolved)
        } catch { self.error = error.localizedDescription }
        await loadComments(companyId)
        await loadMentions()
    }

    func deleteComment(_ companyId: String, commentId: String) async {
        do {
            commentsByCompany[companyId] = try await MacAPIClient.shared.deleteComment(companyId: companyId, commentId: commentId)
        } catch { self.error = error.localizedDescription }
    }

    func loadMentions() async {
        if let m = try? await MacAPIClient.shared.fetchMentions() { mentions = m }
    }

    func loadChatChannels() async {
        if let c = try? await MacAPIClient.shared.fetchChatChannels() {
            chatChannels = c.items
            chatHandles = c.handles
        }
    }

    func openChat(channel: String) async {
        if chatChannel != channel {
            chatChannel = channel
            chatMessages = []
            chatLatest = nil
            chatGeneration += 1
        }
        await pollChat()
    }

    /// The server drops `at <= since` and stamps whole seconds, so poll from one second
    /// before the cursor; the id de-dupe absorbs the overlap.
    private static func chatSince(_ latest: String?) -> String? {
        guard let latest, let d = MacTimeFormat.parse(latest) else { return latest }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: d.addingTimeInterval(-1))
    }

    func pollChat() async {
        let channel = chatChannel
        let since = Self.chatSince(chatLatest)
        let gen = chatGeneration
        guard let page = try? await MacAPIClient.shared.fetchChat(channel: channel, since: since) else { return }
        guard gen == chatGeneration, channel == chatChannel else { return }
        let known = Set(chatMessages.map(\.id))
        let fresh = page.items.filter { !known.contains($0.id) }
        if !fresh.isEmpty {
            chatMessages.append(contentsOf: fresh)
            if chatMessages.count > 500 { chatMessages.removeFirst(chatMessages.count - 500) }
        }
        // Only move the cursor forward on real data; the server echoes `since` when nothing is new.
        if !page.items.isEmpty, let latest = page.items.last?.at ?? page.latest, latest != chatLatest {
            chatLatest = latest
        }
    }

    /// Polls the open channel every few seconds while any chat pane is visible.
    /// Reference-counted: one window closing its blotter must not stop the others.
    func startChatPolling() {
        chatPollRefs += 1
        guard chatPollTask == nil else { return }
        restartChatPolling()
    }

    private func restartChatPolling() {
        chatPollTask?.cancel()
        chatPollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollChat()
                try? await Task.sleep(for: .seconds(max(4, MacAPIClient.retryAfterDelay())))
            }
        }
    }

    func stopChatPolling() {
        chatPollRefs = max(0, chatPollRefs - 1)
        guard chatPollRefs == 0 else { return }
        chatPollTask?.cancel()
        chatPollTask = nil
    }

    @discardableResult
    func sendChat(_ text: String, companyId: String? = nil) async -> Bool {
        let channel = chatChannel
        let gen = chatGeneration
        do {
            let msg = try await MacAPIClient.shared.postChat(channel: channel, text: text, companyId: companyId)
            guard gen == chatGeneration, channel == chatChannel else {
                await loadChatChannels()
                return true
            }
            // Poll from the unchanged cursor so teammates' messages posted just before ours
            // arrive in server order; the cursor advances from the page.
            await pollChat()
            if gen == chatGeneration, channel == chatChannel,
               !chatMessages.contains(where: { $0.id == msg.id }) {
                chatMessages.append(msg)
            }
            await loadChatChannels()
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func loadAudit(companyId: String? = nil) async {
        if let page = try? await MacAPIClient.shared.fetchAudit(companyId: companyId) { auditRows = page.items }
    }

    func loadTranscripts(companyId: String? = nil, query: String = "") async {
        transcriptQuery = query
        transcriptCompanyId = companyId
        let gen = serverEpoch
        if let list = try? await MacAPIClient.shared.fetchTranscripts(companyId: companyId, query: query),
           gen == serverEpoch, query == transcriptQuery, companyId == transcriptCompanyId {
            transcripts = list.items
        }
    }

    /// Reload with the active search kept, so an edit never wipes the library's filter.
    func reloadTranscripts() async {
        await loadTranscripts(companyId: transcriptCompanyId, query: transcriptQuery)
    }

    func loadTranscript(_ id: String) async {
        if let t = try? await MacAPIClient.shared.fetchTranscript(id: id) { transcriptById[id] = t }
    }

    @discardableResult
    func addTranscript(fields: [String: Any?]) async -> MacTranscript? {
        do {
            let t = try await MacAPIClient.shared.addTranscript(fields: fields)
            transcriptById[t.id] = t
            await reloadTranscripts()
            return t
        } catch { self.error = error.localizedDescription; return nil }
    }

    @discardableResult
    func uploadTranscript(fileURL: URL, title: String, kind: String, companyId: String?, tags: String, participants: String) async -> MacTranscript? {
        do {
            let accessed = fileURL.startAccessingSecurityScopedResource()
            defer { if accessed { fileURL.stopAccessingSecurityScopedResource() } }
            let t = try await MacAPIClient.shared.uploadTranscript(fileURL: fileURL, title: title, kind: kind, companyId: companyId, tags: tags, participants: participants)
            transcriptById[t.id] = t
            await reloadTranscripts()
            return t
        } catch { self.error = error.localizedDescription; return nil }
    }

    /// A 404 counts as done: the transcript is gone either way.
    @discardableResult
    func deleteTranscript(_ id: String) async -> Bool {
        do {
            try await MacAPIClient.shared.deleteTranscript(id: id)
        } catch MacAPIError.http(404, _) {
        } catch {
            self.error = error.localizedDescription
            return false
        }
        transcriptById[id] = nil
        await reloadTranscripts()
        return true
    }

    @discardableResult
    func addHighlight(transcriptId: String, text: String, note: String) async -> Bool {
        do {
            let t = try await MacAPIClient.shared.addHighlight(transcriptId: transcriptId, text: text, note: note)
            transcriptById[t.id] = t
            await reloadTranscripts()
            return true
        } catch {
            self.error = error.localizedDescription
            if case MacAPIError.http(404, _) = error {
                transcriptById[transcriptId] = nil
                await reloadTranscripts()
            }
            return false
        }
    }

    @discardableResult
    func removeHighlight(transcriptId: String, highlightId: String) async -> Bool {
        do {
            let t = try await MacAPIClient.shared.removeHighlight(transcriptId: transcriptId, highlightId: highlightId)
            transcriptById[t.id] = t
            await reloadTranscripts()
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func loadSignalScore(_ companyId: String) async {
        if let s = try? await MacAPIClient.shared.fetchSignalScore(companyId: companyId) { signalScoreByCompany[companyId] = s }
    }

    /// Jump to whatever a firm-search hit points at.
    func open(hit: MacSearchHit) {
        switch hit.kind {
        case "transcript", "highlight":
            // The Documents desk mounts with this value already set, so its onChange never fires;
            // put the desk into transcript mode up front (same as the command palette).
            UserDefaults.standard.set("transcripts", forKey: "mac.documents.mode")
            selectedTab = .documents
            transcriptToOpen = hit.ref
        case "chat":
            showBlotter = true
            blotterTab = .chat
            if let ch = hit.channel { Task { await openChat(channel: ch) } }
        default:
            if let cid = hit.companyId, let company = companies.first(where: { $0.id == cid }) {
                showCompany(company)
            }
        }
        showFirmSearch = false
    }
    @Published var transcriptToOpen: String?

    // MARK: - Unified profile, filings, signal watch, lint

    func loadProfile(_ companyId: String) async {
        if let p = try? await MacAPIClient.shared.fetchProfile(companyId: companyId) { profileByCompany[companyId] = p }
    }

    func loadEarningsFilings(_ companyId: String, refresh: Bool = false) async {
        do {
            earningsFilingsByCompany[companyId] = try await MacAPIClient.shared.fetchCompanyEarningsFilings(
                companyId: companyId,
                refresh: refresh
            )
            earningsFilingsFailed.remove(companyId)
        } catch {
            guard !Task.isCancelled else { return }
            earningsFilingsFailed.insert(companyId)
        }
    }

    func loadFilingsWatch(refresh: Bool = false) async {
        filingsLoading = true
        defer { filingsLoading = false }
        if let w = try? await MacAPIClient.shared.fetchFilingsWatch(refresh: refresh) { filingsWatch = w }
    }

    func loadSignalMoves() async {
        if let m = try? await MacAPIClient.shared.fetchSignalMoves() { signalMoves = m }
    }

    func snapshotSignals() async {
        do {
            try await MacAPIClient.shared.snapshotSignals()
            await loadSignalMoves()
        } catch { self.error = error.localizedDescription }
    }

    func loadNumberLint(_ companyId: String) async {
        if let l = try? await MacAPIClient.shared.fetchNumberLint(companyId: companyId) { numberLintByCompany[companyId] = l }
    }

    // MARK: - Saved workspaces (layouts live in UserDefaults; nothing leaves the Mac)

    static let workspacesKey = "bsh.mac.workspaces"

    static func loadWorkspaces() -> [MacWorkspace] {
        guard let data = UserDefaults.standard.data(forKey: workspacesKey),
              let list = try? JSONDecoder().decode([MacWorkspace].self, from: data) else { return [] }
        return list
    }

    private func persistWorkspaces() {
        if let data = try? JSONEncoder().encode(workspaces) { UserDefaults.standard.set(data, forKey: Self.workspacesKey) }
    }

    func saveWorkspace(named name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let ws = MacWorkspace(
            name: trimmed,
            tab: selectedTab.rawValue,
            blotterOpen: showBlotter,
            blotterTab: blotterTab.rawValue,
            portfolioMode: UserDefaults.standard.string(forKey: "mac.portfolio.mode") ?? "holdings",
            documentsMode: UserDefaults.standard.string(forKey: "mac.documents.mode") ?? "files",
            companyId: selectedCompany?.id,
            savedAt: Date()
        )
        workspaces.removeAll { $0.name == trimmed }
        workspaces.insert(ws, at: 0)
        persistWorkspaces()
    }

    func restoreWorkspace(_ ws: MacWorkspace) {
        if let tab = MacTab(rawValue: ws.tab) { selectedTab = tab }
        showBlotter = ws.blotterOpen
        if let bt = MacBlotterTab(rawValue: ws.blotterTab) { blotterTab = bt }
        UserDefaults.standard.set(ws.portfolioMode, forKey: "mac.portfolio.mode")
        UserDefaults.standard.set(ws.documentsMode, forKey: "mac.documents.mode")
        if let cid = ws.companyId, let company = companies.first(where: { $0.id == cid }) { selectCompany(company) }
    }

    func deleteWorkspace(_ ws: MacWorkspace) {
        workspaces.removeAll { $0.name == ws.name }
        persistWorkspaces()
    }

    /// Menu-bar extra summary: what needs a person right now.
    var menuBarSummary: (jobs: Int, alerts: Int, mentions: Int, highHoldings: Int) {
        (activeJobs.count, alertEvents.count, mentions?.openCount ?? 0, portfolioDashboard?.totals?.highAlertCount ?? 0)
    }

    // MARK: - Research Memos & Annotation Overlays

    func reports(for companyId: String) -> [MacReport] {
        reports
            .filter { $0.companyId == companyId }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
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
        openMemoGeneration += 1
        let generation = openMemoGeneration
        openReportId = report.id
        openDocumentURL = nil
        openDocumentIsPDF = false
        openDocumentOverlayData = nil
        openReportTitle = ""
        openDocumentError = nil
        openingMemo = true
        defer { if generation == openMemoGeneration { openingMemo = false } }
        do {
            let loaded = try await loadMemoDocument(reportId: report.id, language: lang)
            guard generation == openMemoGeneration else { return }
            openDocumentURL = loaded.url
            openDocumentIsPDF = loaded.isPDF
            openDocumentOverlayData = loaded.overlayData
            openReportTitle = loaded.title
        } catch {
            guard generation == openMemoGeneration else { return }
            openDocumentError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func closeMemo() {
        openMemoGeneration += 1
        openingMemo = false
        openDocumentURL = nil
        openDocumentIsPDF = false
        openReportTitle = ""
        openReportId = ""
        openDocumentOverlayData = nil
        openDocumentError = nil
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
        copilotContextTask?.cancel()
        let cid = selectedCompany?.id ?? companies.first?.id
        guard let cid, !cid.isEmpty else { return }
        copilotContextTask = Task { [weak self] in
            guard let info = try? await MacAPIClient.shared.fetchCopilotContext(companyId: cid, context: context),
                  !Task.isCancelled, let self else { return }
            guard self.copilotContext == context,
                  (self.selectedCompany?.id ?? self.companies.first?.id) == cid else { return }
            self.copilotContextInfo = info
        }
    }

    func clearCopilotContext() {
        copilotContextTask?.cancel()
        copilotContextTask = nil
        copilotContext = .none
        copilotContextInfo = nil
    }

    /// Stops a streaming answer and clears the transcript; safe to call mid-stream.
    func cancelCopilot() {
        copilotTask?.cancel()
        copilotTask = nil
        copilotStreaming = false
        copilotCurrentThinking = nil
    }

    func clearCopilot() {
        cancelCopilot()
        copilotMessages.removeAll()
    }

    /// Drops the last answer (and its question) and asks the same question again.
    func retryLastCopilotQuestion() {
        guard !copilotStreaming,
              let userIndex = copilotMessages.lastIndex(where: { $0.role == .user }) else { return }
        let prompt = copilotMessages[userIndex].text
        copilotMessages.removeSubrange(userIndex...)
        sendCopilotMessage(prompt: prompt)
    }

    func toggleCopilotPanel() {
        showCopilotPanel.toggle()
    }

    /// Ask with the current on-screen context, opening the Ask Warren side panel (matching the web experience).
    func askWarren(_ prompt: String, context: MacCopilotContext, company: MacCompany? = nil) {
        setCopilotContext(context, company: company)
        showCopilotPanel = true
        sendCopilotMessage(prompt: prompt)
    }

    /// `edits` is the server turn id of a question this one rewrites; `displayFiles`
    /// names the files an edit inherits from the question it replaces.
    func sendCopilotMessage(prompt: String, edits: String? = nil, displayFiles: [String] = []) {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !copilotStreaming, !copilotAttachmentsStaging else { return }
        guard canRunTasks else {
            copilotMessages.append(MacCopilotMessage(role: .assistant, text: "Sign in with an analyst or partner role to ask Warren."))
            return
        }
        guard let cid = selectedCompany?.id ?? companies.first?.id, !cid.isEmpty else {
            copilotMessages.append(MacCopilotMessage(role: .assistant, text: "Add or select a company to ask."))
            return
        }

        let staged = copilotAttachments.compactMap { item in item.storedName.map { ($0, item.name) } }
        var userMsg = MacCopilotMessage(role: .user, text: trimmed)
        userMsg.contextLabel = copilotContext.isSpecific ? copilotContext.chipLabel : nil
        userMsg.files = staged.isEmpty ? displayFiles : staged.map(\.1)
        userMsg.edited = edits != nil
        copilotMessages.append(userMsg)
        // The question carries them now; the composer starts clean.
        copilotAttachments.removeAll()
        copilotWorkNote = nil
        copilotWorkError = nil
        copilotDraft = ""
        copilotStreaming = true
        copilotCurrentThinking = nil

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
            var assistantMsg = MacCopilotMessage(role: .assistant, text: "")
            assistantMsg.persona = persona
            copilotMessages.append(assistantMsg)
            // The placeholder is looked up by id on every write: Clear can empty the array mid-stream.
            let setAssistantText: (String, Bool) -> Void = { [weak self] s, isError in
                guard !Task.isCancelled, let self,
                      let i = self.copilotMessages.firstIndex(where: { $0.id == assistantMsg.id }) else { return }
                self.copilotMessages[i].text = s
                self.copilotMessages[i].isError = isError
            }

            do {
                let stream = await MacAPIClient.shared.askCopilotStream(
                    companyId: cid,
                    prompt: trimmed,
                    persona: persona,
                    context: context,
                    mode: mode,
                    attachments: staged.map(\.0),
                    attachmentNames: Dictionary(staged, uniquingKeysWith: { first, _ in first }),
                    edits: edits
                )
                for try await chunk in stream {
                    guard !Task.isCancelled else { break }
                    switch chunk {
                    case .started(let sessionId, let turnId):
                        // The thread and turn the question landed in: what a later
                        // edit points at, and what the history lists.
                        copilotSessionId = sessionId
                        copilotThreadCompanyId = cid
                        if let i = copilotMessages.firstIndex(where: { $0.id == userMsg.id }) {
                            copilotMessages[i].turnId = turnId
                        }
                        if let i = copilotMessages.firstIndex(where: { $0.id == assistantMsg.id }) {
                            copilotMessages[i].turnId = turnId
                        }
                    case .partial(let text):
                        reply += (reply.isEmpty ? "" : "\n\n") + text
                        setAssistantText(reply, false)
                    case .tool(let activity):
                        copilotCurrentThinking = activity
                    case .final(let text):
                        if !text.isEmpty { reply = text }
                        setAssistantText(reply, false)
                    }
                }
                if reply.isEmpty, !Task.isCancelled {
                    setAssistantText("No answer came back. Try again, or switch to Deep for a longer run.", true)
                }
            } catch {
                if !Task.isCancelled {
                    let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                    // The runner often echoes the failure as text before the error event
                    // ("You've hit your weekly limit"); show it once, as an error.
                    let echoed = reply.isEmpty || detail.contains(reply) || reply.contains(detail)
                    if echoed {
                        setAssistantText(detail, true)
                    } else {
                        setAssistantText(reply + "\n\n*(The answer was cut off: \(detail))*", false)
                    }
                }
            }
            guard !Task.isCancelled else { return }
            copilotCurrentThinking = nil
            copilotStreaming = false
        }
    }

    // MARK: - Warren's shared thread

    /// Load the company's Warren thread from the server. The Mac used to keep the
    /// conversation only in memory, so two people on the same company — or this Mac
    /// after a relaunch — saw different conversations; the web shows the server's
    /// thread, and now so does the Mac.
    func loadCopilotThread(force: Bool = false) async {
        guard let cid = selectedCompany?.id ?? companies.first?.id, !cid.isEmpty,
              !copilotStreaming, canRunTasks else { return }
        if !force, copilotThreadCompanyId == cid { return }
        copilotThreadCompanyId = cid
        copilotViewingThread = nil
        copilotViewingMessages = []
        do {
            let threads = try await MacAPIClient.shared.fetchCopilotThreads(companyId: cid)
            guard copilotThreadCompanyId == cid else { return }
            copilotThreads = threads
            guard let active = threads.first(where: \.active) else {
                copilotSessionId = nil
                if !copilotStreaming { copilotMessages = [] }
                return
            }
            let turns = try await MacAPIClient.shared.fetchConsoleTurns(companyId: cid, sessionId: active.id)
            guard copilotThreadCompanyId == cid, !copilotStreaming else { return }
            copilotSessionId = active.id
            copilotMessages = Self.copilotMessages(from: turns, me: session?.email)
        } catch {
            // Offline or signed out: keep what is on screen rather than blanking it.
            copilotThreadCompanyId = nil
        }
    }

    func refreshCopilotThreads() async {
        guard let cid = selectedCompany?.id ?? companies.first?.id, !cid.isEmpty else { return }
        copilotThreadsLoading = true
        defer { copilotThreadsLoading = false }
        if let threads = try? await MacAPIClient.shared.fetchCopilotThreads(companyId: cid) {
            copilotThreads = threads
        }
    }

    /// File the current thread into the history and open a fresh one — for everyone,
    /// which is the point. Replaces the old Clear, which only emptied this Mac's copy.
    func newCopilotThread() async {
        guard let cid = selectedCompany?.id ?? companies.first?.id, !cid.isEmpty,
              !copilotStreaming else { return }
        do {
            let sid = try await MacAPIClient.shared.startCopilotThread(
                companyId: cid, mode: copilotDeepMode ? "deep" : "quick"
            )
            copilotThreadCompanyId = cid
            copilotSessionId = sid
            copilotViewingThread = nil
            copilotViewingMessages = []
            copilotMessages = []
            copilotWorkNote = nil
            copilotWorkError = nil
            await refreshCopilotThreads()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Read an earlier thread. The current one stays where it is.
    func openCopilotThread(_ thread: MacCopilotThread) async {
        guard let cid = selectedCompany?.id ?? companies.first?.id else { return }
        guard !thread.active else {
            backToCurrentCopilotThread()
            return
        }
        copilotViewingThread = thread
        copilotViewingMessages = []
        if let turns = try? await MacAPIClient.shared.fetchConsoleTurns(companyId: cid, sessionId: thread.id),
           copilotViewingThread?.id == thread.id {
            copilotViewingMessages = Self.copilotMessages(from: turns, me: session?.email)
        }
    }

    func backToCurrentCopilotThread() {
        copilotViewingThread = nil
        copilotViewingMessages = []
    }

    /// Rewrite a question already asked. The old question and its answer leave the
    /// thread for everyone (the server drops them), and the new one inherits any
    /// files the old one carried.
    func editCopilotQuestion(_ message: MacCopilotMessage, to text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard message.role == .user, let turnId = message.turnId, !trimmed.isEmpty,
              trimmed != message.text, !copilotStreaming,
              let index = copilotMessages.firstIndex(where: { $0.id == message.id }) else { return }
        var end = index + 1
        while end < copilotMessages.count, copilotMessages[end].role == .assistant { end += 1 }
        copilotMessages.removeSubrange(index..<end)
        sendCopilotMessage(prompt: trimmed, edits: turnId, displayFiles: message.files)
    }

    /// Server turns as the chat shows them. Assistant turns carry the id of the
    /// question they answer, so the pair shares a turn id.
    static func copilotMessages(from turns: [MacConsoleTurn], me: String?) -> [MacCopilotMessage] {
        turns.map { turn in
            let when = MacTimeFormat.parse(turn.ts) ?? Date()
            if turn.isUser {
                var message = MacCopilotMessage(id: turn.id, role: .user, text: turn.text, date: when)
                message.turnId = turn.turnId
                message.files = turn.attachments.compactMap(\.name)
                message.edited = turn.edits != nil
                let email = turn.authorEmail ?? ""
                if !email.isEmpty, email.lowercased() != (me ?? "").lowercased() {
                    message.author = turn.authorName.flatMap { $0.isEmpty ? nil : $0 }
                        ?? email.components(separatedBy: "@").first
                }
                return message
            }
            let failed = turn.subtype == "error" || (turn.text.isEmpty && turn.error != nil)
            var message = MacCopilotMessage(
                id: turn.id,
                role: .assistant,
                text: turn.text.isEmpty ? (turn.error ?? "") : turn.text,
                date: when
            )
            message.turnId = turn.turnId
            message.persona = .warren
            message.isError = failed
            return message
        }
    }

    // MARK: - Warren attachments

    var copilotAttachmentsStaging: Bool {
        copilotAttachments.contains { if case .staging = $0.state { return true } else { return false } }
    }

    /// Upload each file as it is picked, so one Warren cannot read is refused while
    /// the analyst is still at the composer (the server turns documents into text).
    func stageCopilotAttachments(_ urls: [URL]) {
        guard let cid = selectedCompany?.id ?? companies.first?.id, !cid.isEmpty else { return }
        let mode = copilotDeepMode ? "deep" : "quick"
        for url in urls {
            let entry = MacStagedAttachment(url: url)
            copilotAttachments.append(entry)
            Task { [weak self] in
                let outcome: MacStagedAttachment.State
                do {
                    let stored = try await MacAPIClient.shared.stageCopilotAttachment(
                        companyId: cid, fileURL: url, mode: mode
                    )
                    outcome = .ready(storedName: stored)
                } catch {
                    outcome = .failed((error as? LocalizedError)?.errorDescription ?? error.localizedDescription)
                }
                guard let self, let i = self.copilotAttachments.firstIndex(where: { $0.id == entry.id }) else { return }
                self.copilotAttachments[i].state = outcome
            }
        }
    }

    func removeCopilotAttachment(_ id: UUID) {
        copilotAttachments.removeAll { $0.id == id }
    }

    // MARK: - Work Warren offers to start

    /// He proposes; the analyst presses the button. Nothing here runs unless they do.
    func confirmCopilotWork(_ work: MacCopilotWork) async {
        guard let company = selectedCompany ?? companies.first, !copilotWorkRunning else { return }
        copilotWorkRunning = true
        copilotWorkError = nil
        copilotWorkNote = nil
        defer { copilotWorkRunning = false }
        do {
            switch work.kind {
            case .report:
                _ = try await MacAPIClient.shared.createReport(
                    companyId: company.id,
                    reportType: work.reportType,
                    audience: work.audience,
                    language: work.language,
                    reportMode: work.reportMode,
                    quality: work.quality
                )
                copilotWorkNote = "\(work.reportType) is running — it will appear in Jobs."
                await refreshJobs()
            case .documentAnalysis:
                try await MacAPIClient.shared.analyzeResearchFile(companyId: company.id, fileId: work.fileId)
                copilotWorkNote = "Reading \(work.fileName.isEmpty ? work.title : work.fileName) — it will appear in Jobs."
                await refreshJobs()
            case .decision:
                let recorded = await recordDecision(
                    companyId: company.id,
                    verdict: work.verdict,
                    explanation: work.explanation,
                    decidedAt: Date(),
                    reportId: nil
                )
                guard recorded else {
                    copilotWorkError = error ?? "The decision was not recorded."
                    return
                }
                copilotWorkNote = "Recorded on \(company.title)'s decision log."
            case .follow:
                // Idempotent: confirming twice should not unfollow.
                if !isFollowed(company.id) { await toggleFollow(company.id) }
                copilotWorkNote = "Following \(company.title)."
            }
        } catch {
            copilotWorkError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    // MARK: - Attention queue ("what needs me today")

    static let lastLaunchKey = "bsh.mac.lastLaunchAt"

    /// Each source keeps its previous items on failure and records the error; "All clear"
    /// is only honest when `attentionErrors` is empty. The digest baseline is fixed per
    /// launch so Refresh keeps comparing against the previous launch.
    func loadAttention() async {
        guard !attentionLoading, !(session == nil && sessionRejected) else { return }
        attentionLoading = true
        defer { attentionLoading = false }
        let epoch = serverEpoch
        async let screener = MacAPIClient.shared.fetchDeskScreener(limit: 30)
        async let digest = MacAPIClient.shared.fetchDeskDigest(since: attentionSince, limit: 30)
        async let intake = MacAPIClient.shared.fetchIntakeUnresolved()
        var errors: [String: String] = [:]
        var anySucceeded = false
        var unauthorized = false
        func describe(_ error: Error) -> String {
            if case MacAPIError.unauthorized = error { unauthorized = true }
            return (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
        let screenerResult: Result<[MacScreenerItem], Error>
        do { screenerResult = .success(try await screener) } catch { screenerResult = .failure(error) }
        let digestResult: Result<[MacDigestItem], Error>
        do { digestResult = .success(try await digest) } catch { digestResult = .failure(error) }
        let intakeResult: Result<[MacIntakeItem], Error>
        do { intakeResult = .success(try await intake) } catch { intakeResult = .failure(error) }
        guard epoch == serverEpoch else { return }
        switch screenerResult {
        case .success(let items): screenerItems = items; anySucceeded = true
        case .failure(let e): errors["screener"] = describe(e)
        }
        switch digestResult {
        case .success(let items): digestItems = items; anySucceeded = true
        case .failure(let e): errors["digest"] = describe(e)
        }
        switch intakeResult {
        case .success(let items): intakeItems = items; anySucceeded = true
        case .failure(let e): errors["intake"] = describe(e)
        }
        if let pipelineError { errors["pipeline"] = pipelineError }
        attentionErrors = errors
        if errors["digest"] == nil { stampLaunch() }
        if unauthorized { handleSessionLoss() }
        if rollup == nil { await loadPipeline() }
        if anySucceeded { attentionLoadedAt = Date() }
    }

    /// Moves the "since last launch" baseline forward once per launch, and only after the
    /// digest actually loaded, so changes from a failed load are not lost.
    func stampLaunch() {
        guard !didStampLaunch, attentionErrors["digest"] == nil, attentionLoadedAt != nil || attentionLoading else { return }
        didStampLaunch = true
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
        guard canWriteDesk else {
            self.error = "A read-only session cannot log signals."
            return false
        }
        // Only a quote fetched in the last minute may be the entry price; otherwise the
        // server records the live print (cached quotes can be days old).
        let fresh = watchlistFetchedAt.map { Date().timeIntervalSince($0) < 60 } ?? false
        let price = fresh ? watchlist.first(where: { $0.ticker == ticker.uppercased() })?.last : nil
        do {
            let result = try await MacAPIClient.shared.logSignal(ticker: ticker, direction: direction, label: label, priceAtSignal: price)
            await loadSignals()
            if result.deduplicated {
                let at = result.entry.priceAtSignal.map { String(format: "$%.2f", $0) } ?? "the earlier price"
                self.error = "Already logged today at \(at)."
                return false
            }
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func deleteSignal(id: String) async {
        guard canWriteDesk else {
            self.error = "A read-only session cannot change the signal ledger."
            return
        }
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

    /// `adoptSelection` only applies for the company on screen: a finishing turn for another
    /// company must not replace the session the user is looking at.
    func loadConsoleSessions(companyId: String, adoptSelection: Bool = true) async {
        if let rows = try? await MacAPIClient.shared.listConsoleSessions(companyId: companyId) {
            consoleSessions[companyId] = rows.sorted { ($0.lastUsedAt ?? "") > ($1.lastUsedAt ?? "") }
            guard adoptSelection, companyId == selectedCompany?.id else { return }
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

    /// True while a turn is being submitted or streamed in any session; Send must stay
    /// disabled (and keep its draft) until it clears.
    var consoleBusy: Bool { consoleSubmitting || consoleStreamingTurn != nil }
    @Published private(set) var consoleSubmitting = false

    /// Returns false when the request was not accepted (busy, empty prompt); the view keeps
    /// the draft in that case. A failed POST sets `consoleError`.
    @discardableResult
    func askConsole(companyId: String, sessionId: String, prompt: String, attachments: [URL]) -> Bool {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        guard !consoleBusy else {
            consoleError = "Warren is still answering another question; wait for it or cancel it first."
            return false
        }
        consoleError = nil
        consoleSubmitting = true
        consoleAskGen += 1
        let gen = consoleAskGen
        let epoch = serverEpoch
        consoleTask = Task {
            var turnId: String?
            do {
                let result = try await MacAPIClient.shared.askConsole(companyId: companyId, sessionId: sessionId, prompt: trimmed, attachments: attachments)
                guard epoch == serverEpoch else { return }
                turnId = result.turnId
                consoleSubmitting = false
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
                        guard !Task.isCancelled else { break }
                        switch chunk {
                        case .started:
                            // The Console knows its turn already (from the ask's reply).
                            break
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
                // A cancelled task's own requests fail at once; reload in a task that does not
                // inherit the cancellation, and apply only if no newer ask took over.
                let fresh = await Task { try? await MacAPIClient.shared.fetchConsoleTurns(companyId: companyId, sessionId: sessionId) }.value
                let sessions = await Task { try? await MacAPIClient.shared.listConsoleSessions(companyId: companyId) }.value
                guard epoch == serverEpoch, gen == consoleAskGen,
                      consoleStreamingTurn == nil || consoleStreamingTurn?.turnId == result.turnId else { return }
                if var fresh {
                    // The server writes the assistant row after cancel with a grace period; keep the
                    // local row (partial reply or "Cancelled") until it appears.
                    if !fresh.contains(where: { $0.turnId == result.turnId && !$0.isUser }),
                       let local = consoleTurns[sessionId]?.last(where: { $0.turnId == result.turnId && !$0.isUser }) {
                        if let userIndex = fresh.lastIndex(where: { $0.turnId == result.turnId && $0.isUser }) {
                            fresh.insert(local, at: userIndex + 1)
                        } else {
                            fresh.append(contentsOf: consoleTurns[sessionId]?.filter { $0.turnId == result.turnId } ?? [local])
                        }
                    }
                    consoleTurns[sessionId] = fresh
                }
                if let sessions {
                    consoleSessions[companyId] = sessions.sorted { ($0.lastUsedAt ?? "") > ($1.lastUsedAt ?? "") }
                }
            } catch {
                guard epoch == serverEpoch, gen == consoleAskGen else { return }
                let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                consoleError = detail
                self.error = detail
            }
            guard epoch == serverEpoch, gen == consoleAskGen else { return }
            consoleSubmitting = false
            if consoleStreamingTurn == nil || consoleStreamingTurn?.turnId == turnId {
                consoleStreamingTurn = nil
                consoleActivity = nil
            }
        }
        return true
    }

    private func updateConsoleReply(sessionId: String, turnId: String, text: String) {
        guard var turns = consoleTurns[sessionId],
              let index = turns.lastIndex(where: { $0.turnId == turnId && !$0.isUser }) else { return }
        turns[index].text = text
        consoleTurns[sessionId] = turns
    }

    func cancelConsoleTurn(companyId: String) async {
        guard let (sessionId, turnId) = consoleStreamingTurn else { return }
        do {
            try await MacAPIClient.shared.cancelConsoleTurn(companyId: companyId, sessionId: sessionId, turnId: turnId)
        } catch MacAPIError.http(404, _) {
            // Already finished on the server.
        } catch {
            self.error = error.localizedDescription
            consoleError = error.localizedDescription
            return
        }
        if let turns = consoleTurns[sessionId],
           let row = turns.last(where: { $0.turnId == turnId && !$0.isUser }), row.text.isEmpty {
            updateConsoleReply(sessionId: sessionId, turnId: turnId, text: "Cancelled")
        }
        consoleTask?.cancel()
        consoleTask = nil
        consoleStreamingTurn = nil
        consoleActivity = nil
    }

    func archiveConsoleSession(companyId: String, sessionId: String) async {
        guard canRunTasks else {
            self.error = "A read-only session cannot archive console sessions."
            return
        }
        do {
            let updated = try await MacAPIClient.shared.archiveConsoleSession(companyId: companyId, sessionId: sessionId)
            if let index = consoleSessions[companyId]?.firstIndex(where: { $0.id == sessionId }) {
                consoleSessions[companyId]?[index] = updated
            }
        } catch {
            self.error = error.localizedDescription
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
        // The founder radar loads its own dossier; the stage pill needs the pipeline once.
        if dealPipelines[company.id] == nil {
            Task { await fetchDealPipeline(for: company.id) }
        }
    }

    func fetchDealPipeline(for companyId: String) async {
        do {
            dealPipelines[companyId] = try await MacAPIClient.shared.fetchDealPipeline(companyId: companyId)
        } catch {
            noteCompanyFetchFailure(companyId, error)
        }
    }

    /// Optimistic; on rejection the server's record is restored and the message returned.
    /// `days_in_stage` is server-computed, so the local zero only applies to a real stage change.
    @discardableResult
    func updateDealStage(companyId: String, newStage: String) async -> String? {
        var optimistic: MacDealPipeline?
        if var current = dealPipelines[companyId], current.stage != newStage {
            current.stage = newStage
            current.daysInStage = 0
            dealPipelines[companyId] = current
            optimistic = current
        }
        do {
            let saved = try await MacAPIClient.shared.updateDealPipeline(
                companyId: companyId,
                fields: ["stage": newStage]
            )
            if optimistic == nil || dealPipelines[companyId] == optimistic { dealPipelines[companyId] = saved }
            return nil
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            self.error = message
            if optimistic == nil || dealPipelines[companyId] == optimistic {
                await fetchDealPipeline(for: companyId)
            }
            return message
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
        do {
            founderDossiers[companyId] = try await MacAPIClient.shared.fetchFounderDossier(companyId: companyId)
            founderDossierErrors[companyId] = nil
        } catch {
            founderDossierErrors[companyId] = error.localizedDescription
        }
    }

    /// Gemini web research on the team, merged over the record. Results are
    /// keyed by company, so switching company mid-run is safe.
    func deepSearchFounder(for companyId: String) async {
        deepSearchingFounders.insert(companyId)
        defer { deepSearchingFounders.remove(companyId) }
        do {
            founderDossiers[companyId] = try await MacAPIClient.shared.refreshFounderDossier(companyId: companyId)
            founderDossierErrors[companyId] = nil
        } catch {
            founderDossierErrors[companyId] = error.localizedDescription
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

    struct MacPulseSection: Codable, Hashable {
        let title: String
        let body: String
        enum CodingKeys: String, CodingKey { case title, body }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? ""
            body = (try? c.decodeIfPresent(String.self, forKey: .body)) ?? ""
        }
    }

    struct MacPulseNote: Codable {
        let headlineEn: String?
        let headlineZh: String?
        /// The standfirst under the headline. Notes written before it existed have none.
        let dekEn: String?
        let dekZh: String?
        let bulletsEn: [String]?
        let bulletsZh: [String]?
        /// "short" notes carry bullets; "long" notes carry titled sections instead.
        let length: String?
        let sectionsEn: [MacPulseSection]?
        let sectionsZh: [MacPulseSection]?
        enum CodingKeys: String, CodingKey {
            case length
            case headlineEn = "headline_en"
            case headlineZh = "headline_zh"
            case dekEn = "dek_en"
            case dekZh = "dek_zh"
            case bulletsEn = "bullets_en"
            case bulletsZh = "bullets_zh"
            case sectionsEn = "sections_en"
            case sectionsZh = "sections_zh"
        }

        func dek(zh: Bool) -> String? {
            let dek = zh ? (dekZh ?? dekEn) : (dekEn ?? dekZh)
            return (dek?.isEmpty ?? true) ? nil : dek
        }

        /// Falls back to the other language when the requested list is missing or empty.
        func bullets(zh: Bool) -> [String] {
            let preferred = (zh ? bulletsZh : bulletsEn) ?? []
            return preferred.isEmpty ? ((zh ? bulletsEn : bulletsZh) ?? []) : preferred
        }

        func sections(zh: Bool) -> [MacPulseSection] {
            let preferred = (zh ? sectionsZh : sectionsEn) ?? []
            return preferred.isEmpty ? ((zh ? sectionsEn : sectionsZh) ?? []) : preferred
        }
    }
}
