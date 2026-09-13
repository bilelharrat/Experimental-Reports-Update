import SwiftUI

@MainActor
final class HomeDeskViewModel: ObservableObject {
    @Published var indexes: [Quote] = []
    @Published var movers: [Quote] = []
    @Published var watchlistQuotes: [Quote] = []
    @Published var activeJobs: [ActiveJob] = []
    @Published var runningReports: [ReportSummary] = []
    @Published var recentReports: [ReportSummary] = []
    @Published var pulse: MarketPulsePayload?
    @Published var news: [NewsItem] = []
    @Published var companies: [Company] = []
    @Published var loading = false
    @Published var offline = false
    @Published var error: String?

    // Search (same bar as before — lives on Home, not a separate tab)
    @Published var query = ""
    @Published var autocomplete: [AutocompleteHit] = []
    @Published var deepMatches: [AutocompleteHit] = []
    @Published var deepSearching = false
    @Published var deepStatus = ""
    @Published var deepError: String?
    @Published var selectingId: String?
    @Published var resolveError: String?

    private var autocompleteTask: Task<Void, Never>?
    private let indexTickers = ["SPY", "QQQ", "DIA", "IWM", "GLD", "USO", "TLT", "VIXY"]

    var isSearching: Bool {
        !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var filteredLocal: [Company] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return companies }
        return companies.filter { company in
            let hay = [
                company.name,
                company.nameZh,
                company.ticker,
                company.id,
                company.sector,
            ]
            .compactMap { $0?.lowercased() }
            .joined(separator: " ")
            return hay.contains(q)
        }
    }

    var posture: String {
        pulse?.sections?.marketRegime?.posture ?? "empty"
    }

    var breadth: MarketBreadth? {
        pulse?.sections?.marketRegime?.breadth
    }

    var signals: [RankedSignal] {
        Array((pulse?.sections?.rankedSignals ?? []).prefix(5))
    }

    var topSignal: String {
        pulse?.summary?.topSignal ?? ""
    }

    init() {
        if !AppDataCache.shared.companies.isEmpty {
            self.companies = AppDataCache.shared.companies
        }
        if !AppDataCache.shared.newsItems.isEmpty {
            self.news = Array(AppDataCache.shared.newsItems.prefix(40))
        }
        let cached = QuoteCache.quotes(for: indexTickers)
        if !cached.isEmpty {
            self.indexes = cached
        }
    }

    func load() async {
        if companies.isEmpty && news.isEmpty && indexes.isEmpty {
            loading = true
        }
        error = nil
        defer { loading = false }

        async let quotesTask: QuotesResponse? = {
            try? await APIClient.shared.get(
                "quotes",
                query: indexTickers.map { URLQueryItem(name: "ticker", value: $0) }
            )
        }()
        async let pulseTask: MarketPulsePayload? = {
            try? await APIClient.shared.get("research-pages/market-pulse")
        }()
        async let companiesTask: CompaniesResponse? = {
            try? await APIClient.shared.get("companies")
        }()
        async let feedTask: [ExternalFeedDTO]? = {
            try? await APIClient.shared.get("external/feed")
        }()
        async let liveNewsTask: LiveNewsResponse? = {
            try? await APIClient.shared.get(
                "quotes/news",
                query: [URLQueryItem(name: "limit", value: "40")]
            )
        }()

        async let jobsTask: [ActiveJob]? = {
            try? await APIClient.shared.get("jobs/active")
        }()
        async let reportsTask: [ReportSummary]? = {
            try? await APIClient.shared.get("reports")
        }()

        let (quotesRes, pulseRes, companiesRes, feedRes) = await (quotesTask, pulseTask, companiesTask, feedTask)
        let liveNewsRes = await liveNewsTask
        let (jobsRes, reportsRes) = await (jobsTask, reportsTask)

        if let quotesRes {
            indexes = indexTickers.compactMap { quotesRes.quotes[$0] }
            QuoteCache.save(Array(quotesRes.quotes.values))
            offline = false
        } else {
            // Network blip — serve the last good tape, flagged stale.
            indexes = QuoteCache.quotes(for: indexTickers)
            offline = !indexes.isEmpty
        }
        pulse = pulseRes
        companies = companiesRes?.companies ?? []
        activeJobs = jobsRes ?? []
        let allReports = reportsRes ?? []
        runningReports = allReports.filter { $0.isRunning && !($0.status ?? "").isEmpty }
        recentReports = allReports
            .sorted { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
            .prefix(20)
            .map { $0 }

        let publicTickers = Array(
            Set(
                companies.compactMap { $0.ticker?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
                    .filter { !$0.isEmpty }
            )
        ).prefix(30)
        if !publicTickers.isEmpty {
            do {
                let moverQuotes: QuotesResponse = try await APIClient.shared.get(
                    "quotes",
                    query: publicTickers.map { URLQueryItem(name: "ticker", value: $0) }
                )
                movers = moverQuotes.quotes.values
                    .filter { $0.changePct1d != nil }
                    .sorted { abs($0.changePct1d ?? 0) > abs($1.changePct1d ?? 0) }
                    .prefix(8)
                    .map { $0 }
                QuoteCache.save(Array(moverQuotes.quotes.values))
            } catch {
                movers = []
            }
        }

        let feedNews = NewsAssembler.fromExternalFeed(feedRes ?? [])
        let companyNews = NewsAssembler.fromCompanies(companies)
        let liveNews = NewsAssembler.fromLive(liveNewsRes?.items ?? [])
        news = NewsAssembler.merge(
            live: liveNews,
            feed: feedNews,
            companyNews: companyNews,
            limit: 40
        )

        if indexes.isEmpty && news.isEmpty && pulse == nil {
            error = "Could not load the home desk"
        }
    }

    func loadWatchlist(_ tickers: [String]) async {
        guard !tickers.isEmpty else {
            watchlistQuotes = []
            return
        }
        do {
            let res: QuotesResponse = try await APIClient.shared.get(
                "quotes",
                query: tickers.map { URLQueryItem(name: "ticker", value: $0) }
            )
            watchlistQuotes = tickers.compactMap { res.quotes[$0.uppercased()] }
            QuoteCache.save(Array(res.quotes.values))
        } catch {
            watchlistQuotes = QuoteCache.quotes(for: tickers)
        }
    }

    func onQueryChanged(_ value: String) {
        autocompleteTask?.cancel()
        resolveError = nil
        let q = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else {
            autocomplete = []
            return
        }
        autocompleteTask = Task {
            try? await Task.sleep(nanoseconds: 280_000_000)
            guard !Task.isCancelled else { return }
            do {
                let hits: [AutocompleteHit] = try await APIClient.shared.get(
                    "companies/autocomplete",
                    query: [
                        URLQueryItem(name: "q", value: q),
                        URLQueryItem(name: "limit", value: "8"),
                    ]
                )
                guard !Task.isCancelled else { return }
                autocomplete = hits
            } catch {
                // Soft-fail typeahead
            }
        }
    }

    func runDeepSearch(refresh: Bool = false) async {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        deepSearching = true
        deepError = nil
        deepStatus = "Starting…"
        deepMatches = []
        defer { deepSearching = false }

        do {
            var queryItems = [URLQueryItem(name: "q", value: q)]
            if refresh { queryItems.append(URLQueryItem(name: "refresh", value: "true")) }
            let start: DeepSearchStart = try await APIClient.shared.post(
                "companies/search/start",
                query: queryItems
            )

            if let matches = start.matches, !matches.isEmpty {
                deepMatches = matches
                deepStatus = start.cached == true ? "Cached results" : "Done"
                return
            }

            guard let streamPath = start.streamUrl ?? start.jobId.map({ "/api/companies/search/stream/\($0)" }) else {
                deepStatus = "No results"
                return
            }

            deepStatus = "Searching…"
            let client = SSEClient()
            for try await event in await client.stream(path: streamPath) {
                guard !Task.isCancelled else { break }
                guard let payload = parseJSON(event.data) else { continue }
                let type = (payload["type"] as? String) ?? event.event ?? ""
                if type == "stage" {
                    deepStatus = (payload["message"] as? String)
                        ?? (payload["stage"] as? String)
                        ?? deepStatus
                } else if type == "done" {
                    if let matches = payload["matches"] as? [[String: Any]] {
                        deepMatches = matches.compactMap { decodeHit($0) }
                    }
                    deepStatus = "Done"
                    break
                } else if type == "error" {
                    deepError = (payload["error"] as? String) ?? "Search failed"
                    break
                }
            }
        } catch is CancellationError {
            deepStatus = "Cancelled"
        } catch {
            deepError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func resolveCompanyId(for hit: AutocompleteHit) async throws -> String {
        if let id = hit.companyId, !id.isEmpty { return id }
        selectingId = hit.stableId
        defer { selectingId = nil }
        let body = SelectCompanyBody(
            name: hit.name ?? hit.ticker ?? "Unknown",
            ticker: hit.ticker,
            description: hit.description,
            sector: hit.sector,
            industry: hit.industry,
            exchange: hit.exchange,
            status: hit.status,
            companyType: hit.companyType
        )
        let company: CompanyDetail = try await APIClient.shared.post("companies/select", body: body)
        await load()
        return company.id
    }

    private func parseJSON(_ text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return obj
    }

    private func decodeHit(_ dict: [String: Any]) -> AutocompleteHit? {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
        return try? JSONDecoder().decode(AutocompleteHit.self, from: data)
    }
}

struct TickerNav: Hashable {
    let ticker: String
}

struct CompanyNav: Hashable, Identifiable {
    let id: String
}

struct HomeView: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var router: DeepLinkRouter
    @EnvironmentObject private var desk: DeskStore
    @StateObject private var model = HomeDeskViewModel()
    @State private var path = NavigationPath()
    @State private var showSettings = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if model.isSearching {
                    searchResults
                } else {
                    deskContent
                }
            }
            .listStyle(.insetGrouped)
            .headerProminence(.increased)
            .readableContentWidth(AdaptiveLayout.wideReadableMaxWidth)
            .compactRootChrome(
                title: language.t("tab.home"),
                searchText: $model.query,
                searchPrompt: language.t("search.placeholder")
            ) {
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "gearshape")
                        .font(.title3)
                        .symbolRenderingMode(.hierarchical)
                }
                .accessibilityLabel(language.t("tab.settings"))
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
                    .bshSheetChrome()
            }
            .onChange(of: model.query) { _, value in model.onQueryChanged(value) }
            .navigationDestination(for: TickerNav.self) { nav in
                QuoteDetailView(ticker: nav.ticker)
            }
            .navigationDestination(for: CompanyNav.self) { nav in
                CompanyResearchView(companyId: nav.id)
            }
            .navigationDestination(for: ReportNav.self) { nav in
                ReportDetailView(reportId: nav.id)
                    .id(nav.id)
            }
            .navigationDestination(for: NewsItem.self) { item in
                NewsDetailView(item: item)
            }
            .refreshable {
                if !model.isSearching { await model.load() }
            }
            .task {
                await model.load()
                await desk.loadIfNeeded()
                await model.loadWatchlist(desk.watchlist)
                consumeDeepLink()
            }
            .onChange(of: router.pending) { _, _ in consumeDeepLink() }
            .onChange(of: desk.watchlist) { _, tickers in
                Task { await model.loadWatchlist(tickers) }
            }
        }
    }

    private func consumeDeepLink() {
        guard let link = router.pending else { return }
        switch link {
        case .ticker(let t):
            router.pending = nil
            path.append(TickerNav(ticker: t))
        case .company(let id):
            router.pending = nil
            path.append(CompanyNav(id: id))
        case .report(let id):
            router.pending = nil
            path.append(ReportNav(id: id))
        case .settings:
            router.pending = nil
            showSettings = true
        case .tab:
            // Tab switches are the root view's business, not Home's.
            break
        }
    }

    @ViewBuilder
    private var deskContent: some View {
        if model.loading && model.indexes.isEmpty && model.news.isEmpty {
            ProgressView(language.t("common.loading"))
                .frame(maxWidth: .infinity, alignment: .center)
                .listRowSeparator(.hidden)
        }

        if let err = model.error, model.indexes.isEmpty {
            Text(err).foregroundStyle(.red)
        }

        if model.offline {
            Label(language.t("home.offline"), systemImage: "wifi.slash")
                .font(.caption)
                .foregroundStyle(.orange)
                .listRowSeparator(.hidden)
        }

        jobsSection
        indexesSection
        watchlistSection
        postureSection
        moversSection
        signalsSection
        newsSection
        reportsLibrarySection
    }

    @ViewBuilder
    private var reportsLibrarySection: some View {
        if !model.recentReports.isEmpty {
            Section {
                ForEach(model.recentReports) { report in
                    NavigationLink(value: ReportNav(id: report.id)) {
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(report.companyName ?? report.companyId ?? report.id)
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                Text(report.reportType ?? language.t("research.report"))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 6)
                            StatusPill(text: report.statusLabel, color: reportStatusColor(report))
                        }
                    }
                }
            } header: {
                Text(language.t("home.reports"))
            } footer: {
                Text(language.t("home.reports_footer"))
            }
        }
    }

    private func reportStatusColor(_ report: ReportSummary) -> Color {
        let s = (report.status ?? "").lowercased()
        if s.hasPrefix("complete") { return .green }
        if s.hasPrefix("failed") || s == "cancelled" { return .red }
        if report.isRunning { return .orange }
        return .secondary
    }

    @ViewBuilder
    private var jobsSection: some View {
        let reportJobs = model.runningReports
        let otherJobs = model.activeJobs.filter { $0.reportId == nil }
        if !reportJobs.isEmpty || !otherJobs.isEmpty {
            Section(language.t("home.jobs")) {
                ForEach(reportJobs) { report in
                    NavigationLink(value: ReportNav(id: report.id)) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                ProgressView().controlSize(.small)
                                Text(report.companyName ?? report.reportType ?? report.id)
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                            }
                            HStack(spacing: 6) {
                                Text(report.statusLabel).font(.caption).foregroundStyle(.orange)
                                if let progress = report.progress {
                                    Text("\(progress)%")
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                ForEach(otherJobs.prefix(4)) { job in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            ProgressView().controlSize(.small)
                            Text(job.title ?? job.kind ?? "Job")
                                .font(.subheadline.weight(.semibold))
                                .lineLimit(1)
                        }
                        if let sub = job.subtitle ?? job.lastMessage {
                            Text(sub).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var watchlistSection: some View {
        if !desk.watchlist.isEmpty {
            Section(language.t("home.watchlist")) {
                if model.watchlistQuotes.isEmpty {
                    Text(language.t("common.loading")).foregroundStyle(.secondary)
                } else {
                    ForEach(model.watchlistQuotes) { quote in
                        NavigationLink(value: TickerNav(ticker: quote.ticker)) {
                            QuoteRow(quote: quote)
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                Task { await desk.toggleWatch(quote.ticker) }
                            } label: {
                                Label(language.t("watch.remove"), systemImage: "star.slash")
                            }
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var searchResults: some View {
        if !model.autocomplete.isEmpty {
            Section(language.t("search.suggestions")) {
                ForEach(model.autocomplete) { hit in
                    Button { Task { await openHit(hit) } } label: { hitRow(hit) }
                        .disabled(model.selectingId == hit.stableId)
                }
            }
        }

        Section {
            Button {
                Task { await model.runDeepSearch() }
            } label: {
                Label(
                    model.deepSearching ? language.t("search.deep_running") : language.t("search.deep"),
                    systemImage: "sparkle.magnifyingglass"
                )
            }
            .disabled(model.deepSearching)

            if model.deepSearching || !model.deepStatus.isEmpty {
                Text(model.deepStatus).font(.caption).foregroundStyle(.secondary)
            }
            if let err = model.deepError {
                Text(err).font(.caption).foregroundStyle(.red)
            }
            if let err = model.resolveError {
                Text(err).font(.caption).foregroundStyle(.red)
            }
        }

        if !model.deepMatches.isEmpty {
            Section(language.t("search.deep_results")) {
                ForEach(model.deepMatches) { hit in
                    Button { Task { await openHit(hit) } } label: { hitRow(hit) }
                }
            }
        }

        Section(language.t("search.library")) {
            if model.filteredLocal.isEmpty {
                Text(language.t("search.empty")).foregroundStyle(.secondary)
            } else {
                ForEach(model.filteredLocal) { company in
                    NavigationLink(value: CompanyNav(id: company.id)) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(company.displayName(lang: language.language))
                                    .font(.headline)
                                if let ticker = company.ticker, !ticker.isEmpty {
                                    Text(ticker)
                                        .font(.caption.monospaced())
                                        .foregroundStyle(.secondary)
                                }
                            }
                            if let sector = company.sector {
                                Text(sector).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func hitRow(_ hit: AutocompleteHit) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(hit.name ?? hit.ticker ?? "—")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.primary)
                    if let ticker = hit.ticker, !ticker.isEmpty {
                        Text(ticker)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
                Text([hit.sector, hit.industry, hit.source].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if model.selectingId == hit.stableId {
                ProgressView()
            } else if !hit.hasLocalId {
                Image(systemName: "plus.circle").foregroundStyle(.tint)
            }
        }
    }

    private func openHit(_ hit: AutocompleteHit) async {
        model.resolveError = nil
        do {
            let id = try await model.resolveCompanyId(for: hit)
            path.append(CompanyNav(id: id))
        } catch {
            model.resolveError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private var indexesSection: some View {
        Section(language.t("home.indexes")) {
            if model.indexes.isEmpty {
                Text(language.t("market.empty")).foregroundStyle(.secondary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(model.indexes) { quote in
                            NavigationLink(value: TickerNav(ticker: quote.ticker)) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(quote.ticker)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Text(QuoteRow.price(quote.lastPrice, currency: quote.currency))
                                        .font(.headline.monospacedDigit())
                                        .foregroundStyle(.primary)
                                    Text(QuoteRow.pct(quote.changePct1d))
                                        .font(.footnote.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(
                                            QuoteRow.tone(quote.changePct1d) == .secondary
                                                ? Color(.systemGray3)
                                                : QuoteRow.tone(quote.changePct1d),
                                            in: RoundedRectangle(cornerRadius: 5, style: .continuous)
                                        )
                                }
                                .padding(12)
                                .frame(width: 124, alignment: .leading)
                                .background(Color(.secondarySystemGroupedBackground))
                                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 2)
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }
        }
    }

    private var postureSection: some View {
        Section(language.t("home.posture")) {
            VStack(alignment: .leading, spacing: 8) {
                Text(postureLabel(model.posture))
                    .font(.title3.weight(.semibold))
                if let breadth = model.breadth {
                    Text(
                        language.t("home.breadth")
                            .replacingOccurrences(of: "{up}", with: "\(breadth.positiveSignals ?? 0)")
                            .replacingOccurrences(of: "{down}", with: "\(breadth.negativeSignals ?? 0)")
                            .replacingOccurrences(of: "{flat}", with: "\(breadth.neutralSignals ?? 0)")
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                if !model.topSignal.isEmpty {
                    Text(model.topSignal)
                        .font(.body)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var moversSection: some View {
        Section(language.t("home.movers")) {
            if model.movers.isEmpty {
                Text(language.t("home.movers_empty")).foregroundStyle(.secondary)
            } else {
                ForEach(model.movers) { quote in
                    NavigationLink(value: TickerNav(ticker: quote.ticker)) {
                        QuoteRow(quote: quote)
                    }
                }
            }
        }
    }

    private var signalsSection: some View {
        Section(language.t("home.signals")) {
            if model.signals.isEmpty {
                Text(language.t("home.signals_empty")).foregroundStyle(.secondary)
            } else {
                ForEach(model.signals) { signal in
                    VStack(alignment: .leading, spacing: 4) {
                        if !signal.badge.isEmpty {
                            Text(signal.badge.uppercased())
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                        Text(signal.signal ?? "—")
                            .font(.subheadline)
                        if let direction = signal.direction {
                            Text(direction)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private var newsSection: some View {
        Section {
            if model.news.isEmpty {
                Text(language.t("news.empty")).foregroundStyle(.secondary)
            } else {
                ForEach(model.news.prefix(12)) { item in
                    NavigationLink(value: item) {
                        NewsRowView(item: item)
                    }
                }
            }
        } header: {
            Text(language.t("home.news"))
        } footer: {
            Text(language.t("home.news_footer"))
        }
    }

    private func postureLabel(_ raw: String) -> String {
        switch raw.lowercased() {
        case "risk-on", "risk_on": return language.t("home.posture_risk_on")
        case "risk-off", "risk_off": return language.t("home.posture_risk_off")
        case "mixed": return language.t("home.posture_mixed")
        case "neutral": return language.t("home.posture_neutral")
        default: return language.t("home.posture_empty")
        }
    }
}

struct NewsRowView: View {
    let item: NewsItem

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    let byline = item.ticker?.isEmpty == false ? item.ticker : item.companyName
                    if let byline, !byline.isEmpty {
                        Text(byline)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(Color.accentColor)
                            .lineLimit(1)
                    }
                    // The tape often attributes a company story to itself.
                    if let source = item.source, !source.isEmpty, source != byline,
                       source != item.companyName {
                        Text(source)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Text(item.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                if let summary = item.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(5)
                }
                if !item.whenLabel.isEmpty {
                    Text(item.whenLabel)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer(minLength: 0)
            NewsThumbnail(seed: item.title, category: item.category)
        }
        .padding(.vertical, 4)
    }
}

/// Stand-in artwork: the feed has no images, so each story gets a stable
/// tinted tile keyed off its headline.
struct NewsThumbnail: View {
    let seed: String
    let category: String?

    var body: some View {
        let palette: [Color] = [.blue, .indigo, .purple, .teal, .orange, .pink, .mint]
        let tone = palette[abs(seed.hashValue) % palette.count]
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [tone.opacity(0.9), tone.opacity(0.55)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 58, height: 58)
            .overlay {
                Image(systemName: symbol)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.9))
            }
    }

    private var symbol: String {
        switch (category ?? "").lowercased() {
        case let c where c.contains("earning"): return "chart.bar.doc.horizontal"
        case let c where c.contains("deal"), let c where c.contains("m&a"):
            return "arrow.triangle.merge"
        case let c where c.contains("product"): return "shippingbox"
        case let c where c.contains("regulat"), let c where c.contains("legal"):
            return "building.columns"
        case let c where c.contains("partner"): return "person.2"
        default: return "newspaper"
        }
    }
}
