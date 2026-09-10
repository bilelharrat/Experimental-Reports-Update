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

    func load() async {
        loading = true
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

        async let jobsTask: [ActiveJob]? = {
            try? await APIClient.shared.get("jobs/active")
        }()
        async let reportsTask: [ReportSummary]? = {
            try? await APIClient.shared.get("reports")
        }()

        let (quotesRes, pulseRes, companiesRes, feedRes) = await (quotesTask, pulseTask, companiesTask, feedTask)
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
        news = NewsAssembler.merge(feed: feedNews, companyNews: companyNews, limit: 40)

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
    @State private var showAlerts = false

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
            .compactRootChrome(
                title: language.t("tab.home"),
                searchText: $model.query,
                searchPrompt: language.t("search.placeholder")
            ) {
                Button {
                    showAlerts = true
                } label: {
                    Image(systemName: "bell")
                        .font(.title3)
                }
            }
            .sheet(isPresented: $showAlerts) {
                AlertsView()
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
        router.pending = nil
        switch link {
        case .ticker(let t): path.append(TickerNav(ticker: t))
        case .company(let id): path.append(CompanyNav(id: id))
        case .report(let id): path.append(ReportNav(id: id))
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
                        VStack(alignment: .leading, spacing: 3) {
                            Text(report.companyName ?? report.companyId ?? report.id)
                                .font(.subheadline.weight(.semibold))
                                .lineLimit(1)
                            HStack(spacing: 6) {
                                Text(report.reportType ?? language.t("research.report"))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                Text("·").font(.caption2).foregroundStyle(.tertiary)
                                Text(report.statusLabel)
                                    .font(.caption)
                                    .foregroundStyle(reportStatusColor(report))
                                    .lineLimit(1)
                            }
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
                    HStack(spacing: 10) {
                        ForEach(model.indexes) { quote in
                            NavigationLink(value: TickerNav(ticker: quote.ticker)) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(quote.ticker)
                                        .font(.caption.monospaced().weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Text(QuoteRow.price(quote.lastPrice, currency: quote.currency))
                                        .font(.subheadline.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(.primary)
                                    Text(QuoteRow.pct(quote.changePct1d))
                                        .font(.caption.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(QuoteRow.tone(quote.changePct1d))
                                }
                                .padding(10)
                                .frame(width: 108, alignment: .leading)
                                .background(Color(.secondarySystemGroupedBackground))
                                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 4)
                }
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
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
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(3)
            HStack(spacing: 6) {
                if let ticker = item.ticker, !ticker.isEmpty {
                    Text(ticker).font(.caption.monospaced().weight(.semibold))
                } else if let company = item.companyName {
                    Text(company).font(.caption).lineLimit(1)
                }
                if let source = item.source, !source.isEmpty {
                    Text(source).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                if !item.whenLabel.isEmpty {
                    Text(item.whenLabel).font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
