import AppKit
import Combine
import Foundation

@MainActor
final class MacAppStore: ObservableObject {
    // MARK: - Navigation & Active Tab
    @Published var selectedTab: MacTab = .home

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
    @Published private(set) var pinnedTickers: [String] = ["SPY", "QQQ", "DIA", "IWM"]
    @Published private(set) var bookLots: [MacBookLot] = []
    @Published private(set) var alertRules: [MacAlertRule] = []
    @Published private(set) var deskPrefsLoaded = false

    // MARK: - News, Jobs & Pulse
    @Published private(set) var news: [MacNewsItem] = []
    @Published private(set) var activeJobs: [MacActiveJob] = []
    @Published private(set) var pulse: MacPulseBrief?
    @Published private(set) var marketPulsePayload: MacMarketPulsePayload?
    @Published var pulseLanguage: String = "en"

    // MARK: - Reader & iPad Annotation Overlay
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

    // MARK: - Embedded Web Browser Panel (Cursor Style)
    @Published var showBrowserPanel: Bool = false
    @Published var browserCurrentURL: URL = MacConfig.baseURL

    // MARK: - General Status
    @Published private(set) var loading = false
    @Published var error: String?

    private var tempFiles: [URL] = []
    private var copilotTask: Task<Void, Never>?

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

    // MARK: - Bootstrap & Refresh

    func bootstrap() async {
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
            activeJobs = (try? await jobs) ?? []
            marketPulsePayload = try? await pulsePayload
            indicesQuotes = (try? await indices) ?? []

            if selectedCompany == nil, let first = companies.first {
                selectedCompany = first
            }
            if selectedReport == nil, let firstReport = recentReports.first {
                selectedReport = firstReport
            }

            preloadAllCompanyData()
        } catch {
            self.error = error.localizedDescription
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

    func openReportInViewer(_ report: MacReport, language: String = "en") {
        selectedReport = report
        selectedTab = .documents
        Task {
            await openMemo(report, language: language)
        }
    }

    // MARK: - Desk Preferences Synchronization

    func refreshDeskPrefs() async {
        do {
            let res = try await MacAPIClient.shared.fetchDeskPrefs()
            pinnedTickers = res.watchlist.isEmpty ? ["SPY", "QQQ", "DIA", "IWM"] : res.watchlist
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
            let combined = Array(Set(["SPY", "QQQ", "DIA", "IWM"] + userTickers + companyTickers))
            
            async let quotes = MacAPIClient.shared.fetchQuotes(tickers: Array(combined.prefix(30)))
            async let screeners = MacAPIClient.shared.fetchScreeners(limit: 12)
            
            watchlist = try await quotes
            let s = try await screeners
            gainers = s.gainers
            losers = s.losers

            if selectedTicker == nil, let first = watchlist.first?.ticker {
                selectTicker(first)
            }
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
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshPulse() async {
        do {
            pulse = try await MacAPIClient.shared.fetchPulse()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Research Memos & Annotation Overlays

    func reports(for companyId: String) -> [MacReport] {
        let list = companyReportsCache[companyId] ?? reports.filter { $0.companyId == companyId }
        return list.sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
    }

    func openMemo(_ report: MacReport, language: String? = nil) async {
        let lang = language ?? readerLanguage
        readerLanguage = lang
        openReportId = report.id
        openingMemo = true
        defer { openingMemo = false }
        do {
            var detail = report
            if let fetched = try? await MacAPIClient.shared.getReport(id: report.id) {
                detail = fetched
            }
            guard let doc = detail.documentPath(prefer: lang) else {
                error = "No memo file found for \(lang.uppercased())"
                return
            }

            async let memoData = MacAPIClient.shared.download(pathOrURL: doc.path)
            async let overlay = MacAPIClient.shared.fetchOverlayPNG(reportId: report.id, overlayUrl: nil)

            let (data, inkOverlay) = try await (memoData, overlay)

            let ext = doc.isPDF ? "pdf" : "docx"
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("bsh-memo-\(detail.id)-\(lang).\(ext)")
            try data.write(to: url, options: .atomic)
            tempFiles.append(url)

            openDocumentURL = url
            openDocumentIsPDF = doc.isPDF
            openDocumentOverlayData = inkOverlay
            openReportTitle = "\(detail.companyName ?? "") — \(detail.displayTitle)"
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

    // MARK: - Copilot ("Ask Warren" Assistant)

    func sendCopilotMessage(prompt: String) {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !copilotStreaming else { return }

        let userMsg = MacCopilotMessage(role: .user, text: trimmed)
        copilotMessages.append(userMsg)
        copilotDraft = ""
        copilotStreaming = true

        let cid = selectedCompany?.id ?? companies.first?.id ?? "general"
        let persona = copilotPersona

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
                    persona: persona
                )
                for try await chunk in stream {
                    reply += chunk
                    copilotMessages[assistantIndex].text = reply
                }
            } catch {
                if !Task.isCancelled {
                    copilotMessages[assistantIndex].text = reply.isEmpty
                        ? "Co-Pilot encountered an issue: \(error.localizedDescription)"
                        : reply + "\n\n*(Stream interrupted)*"
                }
            }
            copilotStreaming = false
        }
    }

    func selectCompany(_ company: MacCompany) {
        selectedCompany = company
        if let ticker = company.ticker, !ticker.isEmpty {
            selectTicker(ticker)
        }
    }
}

// MARK: - News & Quotes Models

struct MacNewsItem: Identifiable, Hashable {
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

struct MacQuote: Identifiable, Hashable {
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

struct MacPulseBrief: Decodable {
    let date: String?
    let indices: [MacPulseQuote]?
    let note: MacPulseNote?

    struct MacPulseQuote: Decodable, Identifiable {
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

    struct MacPulseNote: Decodable {
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
