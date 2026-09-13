import SwiftUI

@MainActor
final class NewsViewModel: ObservableObject {
    @Published var items: [NewsItem] = []
    @Published var query = ""
    @Published var scope: Scope = .all
    @Published var loading = false
    @Published var error: String?

    enum Scope: String, CaseIterable, Identifiable {
        case all, market, company
        var id: String { rawValue }
    }

    var filtered: [NewsItem] {
        var rows = items
        switch scope {
        case .all: break
        case .market:
            rows = rows.filter { $0.kind != "company_news" }
        case .company:
            rows = rows.filter { $0.kind == "company_news" }
        }
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return rows }
        return rows.filter {
            "\($0.title) \($0.summary ?? "") \($0.source ?? "") \($0.ticker ?? "") \($0.companyName ?? "")"
                .lowercased()
                .contains(q)
        }
    }

    /// Newest story gets the Apple-News-style lead treatment.
    var lead: NewsItem? {
        query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? filtered.first : nil
    }

    var rest: [NewsItem] {
        guard lead != nil else { return filtered }
        return Array(filtered.dropFirst())
    }

    func load(lang: AppLanguage = .en) async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let feedTask: [ExternalFeedDTO] = APIClient.shared.get("external/feed")
            async let companiesTask: CompaniesResponse = APIClient.shared.get("companies")
            let companiesRes = try await companiesTask
            let companies = companiesRes.companies ?? []
            let bookTickers = Array(
                Set(
                    companies.compactMap { $0.ticker?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
                        .filter { !$0.isEmpty }
                )
            ).prefix(10)
            var newsQuery = [URLQueryItem(name: "limit", value: "50")]
            newsQuery.append(contentsOf: bookTickers.map { URLQueryItem(name: "ticker", value: $0) })
            async let liveTask: LiveNewsResponse = APIClient.shared.get("quotes/news", query: newsQuery)
            let feed = (try? await feedTask) ?? []
            let live = (try? await liveTask)?.items ?? []
            items = NewsAssembler.merge(
                live: NewsAssembler.fromLive(live),
                feed: NewsAssembler.fromExternalFeed(feed),
                companyNews: NewsAssembler.fromCompanies(companies),
                limit: 100
            )
            if items.isEmpty {
                error = "No headlines yet"
            } else {
                prewarmBriefs(lang: lang)
            }
        } catch {
            // Soft-fallback: company news alone still fills the tape.
            do {
                let companiesRes: CompaniesResponse = try await APIClient.shared.get("companies")
                let live = (try? await APIClient.shared.get(
                    "quotes/news",
                    query: [URLQueryItem(name: "limit", value: "50")]
                ) as LiveNewsResponse)?.items ?? []
                items = NewsAssembler.merge(
                    live: NewsAssembler.fromLive(live),
                    feed: [],
                    companyNews: NewsAssembler.fromCompanies(companiesRes.companies ?? []),
                    limit: 100
                )
                if items.isEmpty {
                    self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                } else {
                    prewarmBriefs(lang: lang)
                }
            } catch {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    /// Fire-and-forget: expand the top of the tape in parallel on the server
    /// so opening a story is usually a cache hit.
    func prewarmBriefs(lang: AppLanguage, limit: Int = 16) {
        let top = Array(items.prefix(limit))
        guard !top.isEmpty else { return }
        struct Item: Encodable {
            let title: String
            let summary: String?
            let source: String?
            let publishedAt: String?
            let company: String?
            let ticker: String?
            let url: String?
        }
        struct Body: Encodable {
            let items: [Item]
            let lang: String
            let limit: Int
        }
        struct Plan: Decodable {
            let queued: Int?
            let started: Bool?
            let workers: Int?
            let parallel: Bool?
        }
        let body = Body(
            items: top.map {
                Item(
                    title: $0.title,
                    summary: $0.summary,
                    source: $0.source,
                    publishedAt: $0.capturedAt,
                    company: $0.companyName,
                    ticker: $0.ticker,
                    url: $0.url
                )
            },
            lang: lang.rawValue,
            limit: limit
        )
        Task {
            let _: Plan? = try? await APIClient.shared.post("news/brief/prewarm", body: body, timeout: 15)
        }
    }
}

struct NewsView: View {
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.embeddedInRootSplit) private var embeddedInRootSplit
    @StateObject private var model = NewsViewModel()
    @State private var selectedItem: NewsItem?
    /// Landscape dual-pane: remember whether the article list is expanded.
    @AppStorage("bsh.newsListExpanded") private var listExpanded = true

    /// Dual-pane only inside landscape root sidebar detail. Portrait iPad uses
    /// the same phone TabView + NavigationStack as iPhone — never
    /// NavigationSplitView (that column chrome looks like a broken top menu).
    private var usesDualPane: Bool {
        embeddedInRootSplit
    }

    var body: some View {
        Group {
            if usesDualPane {
                embeddedDualPane
            } else {
                compactStack
            }
        }
        .task { await model.load(lang: language.language) }
        .onChange(of: model.filtered.map(\.id)) { _, _ in
            syncSelectionIfNeeded()
        }
    }

    private var compactStack: some View {
        NavigationStack {
            // Plain List (no selection binding) so NavigationLink can push.
            // List(selection:) — even with .constant(nil) — swallows taps on iPad.
            newsListContent(selectionMode: false)
                .navigationDestination(for: NewsItem.self) { item in
                    NewsDetailView(item: item)
                }
        }
    }

    /// Landscape root detail: HStack dual-pane avoids competing column swipes.
    /// When reading, the list collapses to a chevron rail for full-width article.
    private var embeddedDualPane: some View {
        NavigationStack {
            HStack(spacing: 0) {
                if listExpanded {
                    newsListContent(selectionMode: true)
                        .frame(
                            minWidth: AdaptiveLayout.embeddedMasterMin,
                            idealWidth: AdaptiveLayout.embeddedMasterIdeal,
                            maxWidth: AdaptiveLayout.embeddedMasterIdeal
                        )
                        .transition(.move(edge: .leading).combined(with: .opacity))
                    Divider()
                } else {
                    newsListRail
                    Divider()
                }
                newsDetailPane
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .animation(.easeInOut(duration: 0.22), value: listExpanded)
        }
    }

    /// Narrow peek when the article list is collapsed — expand without leaving the story.
    private var newsListRail: some View {
        VStack(spacing: 12) {
            Button {
                listExpanded = true
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(language.t("news.list_expand"))
            .padding(.top, 10)

            Image(systemName: "newspaper")
                .font(.body.weight(.medium))
                .foregroundStyle(.tertiary)
            Spacer(minLength: 0)
        }
        .frame(width: AdaptiveLayout.embeddedMasterRail)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Color(.secondarySystemBackground).opacity(0.72))
    }

    @ViewBuilder
    private var newsDetailPane: some View {
        // List collapse lives on the list header / chevron rail — not a duplicate
        // sidebar.left in this toolbar (that sat next to the root rail toggle).
        Group {
            if let item = selectedItem {
                NewsDetailView(item: item)
                    .id(item.id)
            } else {
                ContentUnavailableView(
                    language.t("news.empty"),
                    systemImage: "newspaper",
                    description: Text(language.t("news.search"))
                )
            }
        }
    }

    /// Shared list chrome; `selectionMode` chooses List(selection:) vs plain List.
    @ViewBuilder
    private func newsListContent(selectionMode: Bool) -> some View {
        Group {
            if selectionMode {
                List(selection: $selectedItem) {
                    newsListSections(selectionMode: true)
                }
            } else {
                List {
                    newsListSections(selectionMode: false)
                }
            }
        }
        .listStyle(.insetGrouped)
        .headerProminence(.increased)
        .compactRootChrome(
            title: language.t("tab.news"),
            searchText: $model.query,
            searchPrompt: language.t("news.search"),
            trailing: {
                if selectionMode, selectedItem != nil {
                    Button {
                        listExpanded = false
                    } label: {
                        Image(systemName: "rectangle.lefthalf.inset.filled")
                    }
                    .accessibilityLabel(language.t("news.list_collapse"))
                }
            }
        )
        .refreshable { await model.load(lang: language.language) }
    }

    @ViewBuilder
    private func newsListSections(selectionMode: Bool) -> some View {
        Section {
            Picker(language.t("news.scope"), selection: $model.scope) {
                Text(language.t("news.scope_all")).tag(NewsViewModel.Scope.all)
                Text(language.t("news.scope_market")).tag(NewsViewModel.Scope.market)
                Text(language.t("news.scope_company")).tag(NewsViewModel.Scope.company)
            }
            .pickerStyle(.segmented)
            .listRowInsets(EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
        }

        if model.loading && model.items.isEmpty {
            Section {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
            }
        } else if let err = model.error, model.filtered.isEmpty {
            ContentUnavailableView {
                Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
            } description: {
                Text(err)
            } actions: {
                Button(language.t("common.retry")) { Task { await model.load() } }
            }
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
        } else if model.filtered.isEmpty {
            ContentUnavailableView(language.t("news.empty"), systemImage: "newspaper")
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
        } else if selectionMode {
            if let lead = model.lead {
                Section {
                    NewsLeadCard(item: lead)
                        .tag(lead)
                        .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 6, trailing: 4))
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                } header: {
                    Text(language.t("news.top_story"))
                }
            }

            Section {
                ForEach(model.rest) { item in
                    NewsStoryRow(item: item)
                        .tag(item)
                }
            } header: {
                if model.lead != nil {
                    Text(language.t("news.latest"))
                }
            }
        } else {
            if let lead = model.lead {
                Section {
                    // Real NavigationLink (not opacity-0 background) so taps reach
                    // the destination on portrait iPad / phone.
                    NavigationLink(value: lead) {
                        NewsLeadCard(item: lead)
                    }
                    .buttonStyle(.plain)
                    .navigationLinkIndicatorVisibility(.hidden)
                    .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 6, trailing: 4))
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                } header: {
                    Text(language.t("news.top_story"))
                }
            }

            Section {
                ForEach(model.rest) { item in
                    NavigationLink(value: item) {
                        NewsStoryRow(item: item)
                    }
                }
            } header: {
                if model.lead != nil {
                    Text(language.t("news.latest"))
                }
            }
        }
    }

    private func syncSelectionIfNeeded() {
        guard usesDualPane else { return }
        let rows = model.filtered
        guard !rows.isEmpty else {
            selectedItem = nil
            return
        }
        if let selectedItem, rows.contains(where: { $0.id == selectedItem.id }) {
            return
        }
        selectedItem = rows.first
    }
}

/// Apple-News lead story: big headline over a tinted category banner.
struct NewsLeadCard: View {
    let item: NewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                LinearGradient(
                    colors: [tone.opacity(0.85), tone.opacity(0.45)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Image(systemName: symbol)
                    .font(.system(size: 64, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.22))
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .padding(.trailing, 12)
                VStack(alignment: .leading, spacing: 4) {
                    if let badge = item.ticker ?? item.companyName {
                        Text(badge.uppercased())
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(.ultraThinMaterial, in: Capsule())
                    }
                    Text(item.title)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.white)
                        .lineLimit(3)
                        .multilineTextAlignment(.leading)
                }
                .padding(14)
            }
            .frame(height: 168)

            VStack(alignment: .leading, spacing: 8) {
                if let summary = item.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(8)
                }
                HStack(spacing: 6) {
                    if let source = item.source, !source.isEmpty {
                        Text(source).font(.caption.weight(.medium))
                    }
                    if !item.whenLabel.isEmpty {
                        Text("·").font(.caption2).foregroundStyle(.tertiary)
                        Text(item.whenLabel).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .foregroundStyle(.secondary)
            }
            .padding(14)
        }
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var tone: Color {
        let palette: [Color] = [.blue, .indigo, .purple, .teal, .orange, .pink]
        return palette[abs(item.title.hashValue) % palette.count]
    }

    private var symbol: String {
        switch (item.category ?? "").lowercased() {
        case let c where c.contains("earning"): return "chart.bar.doc.horizontal"
        case let c where c.contains("deal"), let c where c.contains("m&a"):
            return "arrow.triangle.merge"
        case let c where c.contains("product"): return "shippingbox"
        case let c where c.contains("regulat"), let c where c.contains("legal"):
            return "building.columns"
        default: return "newspaper"
        }
    }
}

/// Magazine row: headline + a long dek, not a two-line teaser.
struct NewsStoryRow: View {
    let item: NewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        if let ticker = item.ticker, !ticker.isEmpty {
                            Text(ticker)
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(Color.accentColor)
                        } else if let company = item.companyName, !company.isEmpty {
                            Text(company)
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(Color.accentColor)
                                .lineLimit(1)
                        }
                        if let source = item.source, !source.isEmpty, source != item.companyName {
                            Text(source)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    Text(item.title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                NewsThumbnail(seed: item.title, category: item.category)
            }
            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(6)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !item.whenLabel.isEmpty {
                Text(item.whenLabel)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Detail

@MainActor
final class NewsDetailViewModel: ObservableObject {
    @Published var brief: NewsBrief?
    @Published var loading = false
    @Published var error: String?

    private let item: NewsItem

    init(item: NewsItem) {
        self.item = item
    }

    /// Cached briefing if one exists; otherwise kick off the long write.
    /// While generating, also poll the cache so a parallel prewarm finish
    /// can surface without waiting on this request's full timeout.
    func open(lang: AppLanguage) async {
        await loadCached(lang: lang)
        if brief != nil { return }
        loading = true
        error = nil
        defer { loading = false }

        async let generateTask: Void = generate(lang: lang, manageLoading: false)
        let pollTask = Task { @MainActor in
            for _ in 0..<60 {
                try? await Task.sleep(nanoseconds: 1_500_000_000)
                if Task.isCancelled || brief != nil { return }
                await loadCached(lang: lang)
                if brief != nil { return }
            }
        }
        await generateTask
        pollTask.cancel()
        if brief == nil {
            await loadCached(lang: lang)
        }
    }

    func loadCached(lang: AppLanguage) async {
        guard brief == nil else { return }
        var query = [
            URLQueryItem(name: "title", value: item.title),
            URLQueryItem(name: "lang", value: lang.rawValue),
        ]
        if let company = item.companyName {
            query.append(URLQueryItem(name: "company", value: company))
        }
        brief = try? await APIClient.shared.get("news/brief", query: query)
    }

    func generate(lang: AppLanguage, refresh: Bool = false, manageLoading: Bool = true) async {
        if manageLoading {
            loading = true
            error = nil
        }
        defer {
            if manageLoading { loading = false }
        }
        struct Body: Encodable {
            let title: String
            let summary: String?
            let source: String?
            let published_at: String?
            let company: String?
            let ticker: String?
            let url: String?
            let lang: String
            let refresh: Bool
        }
        do {
            brief = try await APIClient.shared.post(
                "news/brief",
                body: Body(
                    title: item.title,
                    summary: item.summary,
                    source: item.source,
                    published_at: item.capturedAt,
                    company: item.companyName,
                    ticker: item.ticker,
                    url: item.url,
                    lang: lang.rawValue,
                    refresh: refresh
                ),
                timeout: 120
            )
        } catch {
            if brief == nil {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}

struct NewsDetailView: View {
    let item: NewsItem
    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model: NewsDetailViewModel

    init(item: NewsItem) {
        self.item = item
        _model = StateObject(wrappedValue: NewsDetailViewModel(item: item))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                masthead
                Divider()
                if let brief = model.brief {
                    briefingBody(brief)
                } else {
                    standfirst
                    if model.loading {
                        writingBanner
                    } else {
                        expandCallout
                    }
                }
                if let err = model.error {
                    Label(err, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
                footerLinks
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .readableContentWidth()
        }
        .background(Color(.systemBackground))
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button {
                        Task { await model.generate(lang: language.language, refresh: true) }
                    } label: {
                        Label(language.t("news.regenerate"), systemImage: "arrow.clockwise")
                    }
                    .disabled(model.loading)
                    ShareLink(item: shareText) {
                        Label(language.t("common.share"), systemImage: "square.and.arrow.up")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .task { await model.open(lang: language.language) }
    }

    // MARK: Pieces

    private var masthead: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if let ticker = item.ticker, !ticker.isEmpty {
                    Text(ticker)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Color.accentColor, in: Capsule())
                }
                if let category = item.category, !category.isEmpty {
                    Text(category.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                }
            }
            Text(item.title)
                .font(.system(.largeTitle, design: .serif).weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                if let source = item.source, !source.isEmpty {
                    Text(source).font(.subheadline.weight(.semibold))
                }
                if !item.whenLabel.isEmpty {
                    Text("·").foregroundStyle(.tertiary)
                    Text(item.whenLabel).font(.subheadline).foregroundStyle(.secondary)
                }
            }
        }
    }

    private var standfirst: some View {
        Text(item.summary ?? "")
            .font(.system(.title3, design: .serif))
            .foregroundStyle(.secondary)
            .lineSpacing(5)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var writingBanner: some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(language.t("news.briefing_auto"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var expandCallout: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(language.t("news.full_briefing"), systemImage: "sparkles")
                .font(.headline)
            Text(language.t("news.full_briefing_hint"))
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button {
                Task { await model.generate(lang: language.language) }
            } label: {
                HStack {
                    if model.loading {
                        ProgressView().controlSize(.small).tint(.white)
                        Text(language.t("news.briefing_running"))
                    } else {
                        Text(language.t("news.read_briefing"))
                    }
                }
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.loading)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    @ViewBuilder
    private func briefingBody(_ brief: NewsBrief) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            let headline = brief.headline(lang: language.language)
            if !headline.isEmpty, headline != item.title {
                Text(headline)
                    .font(.system(.title3, design: .serif).weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            articleBlock(
                language.t("news.what_happened"),
                body: brief.whatHappened(lang: language.language)
            )
            articleBlock(
                language.t("news.why_it_matters"),
                body: brief.whyItMatters(lang: language.language)
            )
            bulletBlock(language.t("news.context"), rows: brief.context(lang: language.language))
            bulletBlock(language.t("news.watch_next"), rows: brief.watchNext(lang: language.language))

            if let sources = brief.sources, !sources.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader(language.t("news.sources"))
                    ForEach(sources) { source in
                        if let url = URL(string: source.url) {
                            Link(destination: url) {
                                HStack(alignment: .top, spacing: 8) {
                                    Image(systemName: "link")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(source.title ?? source.url)
                                        .font(.footnote)
                                        .multilineTextAlignment(.leading)
                                    Spacer(minLength: 0)
                                }
                            }
                        }
                    }
                }
            }

            HStack(spacing: 6) {
                if let confidence = brief.confidence {
                    StatusPill(text: confidence.capitalized, color: confidenceTone(confidence))
                }
                Spacer()
                if model.loading {
                    ProgressView().controlSize(.small)
                }
            }
            .font(.caption)
        }
    }

    private func articleBlock(_ title: String, body: String) -> some View {
        Group {
            if !body.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader(title)
                    // Serif body copy at reading size, like Apple News articles.
                    Text(body)
                        .font(.system(.title3, design: .serif))
                        .lineSpacing(6)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func bulletBlock(_ title: String, rows: [String]) -> some View {
        Group {
            if !rows.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader(title)
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        HStack(alignment: .top, spacing: 10) {
                            Circle()
                                .fill(Color.accentColor)
                                .frame(width: 5, height: 5)
                                .padding(.top, 7)
                            Text(row)
                                .font(.callout)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.caption.weight(.bold))
            .foregroundStyle(.secondary)
            .tracking(0.6)
    }

    private func confidenceTone(_ value: String) -> Color {
        switch value.lowercased() {
        case "high": return .green
        case "low": return .orange
        default: return .secondary
        }
    }

    @ViewBuilder
    private var footerLinks: some View {
        VStack(spacing: 10) {
            if let urlString = item.url, let url = URL(string: urlString) {
                Link(destination: url) {
                    Label(language.t("news.open_source"), systemImage: "safari")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            if let ticker = item.ticker, !ticker.isEmpty {
                NavigationLink {
                    QuoteDetailView(ticker: ticker)
                } label: {
                    Label(
                        language.t("market.open_ticker").replacingOccurrences(of: "{t}", with: ticker),
                        systemImage: "chart.xyaxis.line"
                    )
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
        }
        .padding(.top, 4)
    }

    private var shareText: String {
        var parts = [item.title]
        if let url = item.url, !url.isEmpty { parts.append(url) }
        return parts.joined(separator: "\n")
    }
}
