import SwiftUI

enum MacNewsScope: String, CaseIterable, Identifiable {
    case all = "All"
    case market = "Market"
    case company = "Company"

    var id: String { rawValue }
}

@MainActor
final class MacNewsDetailViewModel: ObservableObject {
    @Published var brief: MacNewsBrief?
    @Published var loading = false
    @Published var error: String?

    @Published private(set) var briefKey: String?

    private var generation = 0

    static func key(for item: MacNewsItem, lang: String) -> String {
        "\(item.id)|\(lang)"
    }

    func load(item: MacNewsItem, lang: String = "en", forceRefresh: Bool = false) async {
        let key = Self.key(for: item, lang: lang)
        if briefKey == key && (brief != nil || loading) && !forceRefresh { return }
        briefKey = key
        generation += 1
        let token = generation
        if !forceRefresh {
            brief = nil
        }
        loading = true
        error = nil
        defer { if token == generation { loading = false } }

        do {
            let result = try await MacAPIClient.shared.fetchNewsBrief(item: item, lang: lang, refresh: forceRefresh)
            guard token == generation else { return }
            brief = result
        } catch {
            guard token == generation, !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }
    }
}

struct MacNewsDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var newsSearch = ""
    @State private var scope: MacNewsScope = .all
    @State private var selectedNews: MacNewsItem?
    @State private var language: String = "en"
    @State private var listExpanded: Bool = true
    @StateObject private var detailModel = MacNewsDetailViewModel()

    private var scopedNews: [MacNewsItem] {
        let base: [MacNewsItem]
        switch scope {
        case .all:
            base = store.news
        case .market:
            base = store.news.filter { ($0.category ?? "").lowercased().contains("market") || $0.companyName == nil }
        case .company:
            base = store.news.filter { $0.companyName != nil || !($0.ticker ?? "").isEmpty }
        }

        let q = newsSearch.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return base }
        return base.filter {
            $0.title.localizedCaseInsensitiveContains(q)
                || ($0.ticker ?? "").localizedCaseInsensitiveContains(q)
                || ($0.source ?? "").localizedCaseInsensitiveContains(q)
                || ($0.summary ?? "").localizedCaseInsensitiveContains(q)
        }
    }

    private var effectiveSelection: MacNewsItem? {
        selectedNews ?? scopedNews.first
    }

    var body: some View {
        HSplitView {
            // Left Pane: News Stream Rail (Collapsible)
            if listExpanded {
                VStack(spacing: 0) {
                    // Scope & Search Header
                    VStack(spacing: 8) {
                        HStack {
                            GlassSegmentedPicker("Scope", selection: $scope, options: MacNewsScope.allCases, title: \.rawValue)

                            Button {
                                Task { await store.refreshNews() }
                            } label: {
                                Image(systemName: "arrow.clockwise")
                            }
                            .buttonStyle(.plain)
                            .help("Refresh news tape")
                        }

                        HStack(spacing: 6) {
                            Image(systemName: "magnifyingglass")
                                .foregroundStyle(.secondary)
                            TextField("Search news, tickers, sources…", text: $newsSearch)
                                .textFieldStyle(.plain)
                            if !newsSearch.isEmpty {
                                Button {
                                    newsSearch = ""
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                    }
                    .padding(10)

                    Divider()

                    // News List with Lead Story Banner & Rows
                    if scopedNews.isEmpty {
                        VStack(spacing: 12) {
                            Spacer()
                            Image(systemName: "newspaper")
                                .font(.system(size: 36))
                                .foregroundStyle(.secondary)
                            Text("No news headlines found")
                                .font(.headline)
                            Text("Try switching scopes or clearing search terms.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List(selection: $selectedNews) {
                            // Lead Hero Card for the First Story
                            if let first = scopedNews.first {
                                Section {
                                    MacNewsLeadCard(item: first)
                                        .tag(first)
                                        .listRowInsets(EdgeInsets(top: 8, leading: 10, bottom: 8, trailing: 10))
                                        .listRowSeparator(.hidden)
                                        .glassListRow(isSelected: selectedNews == first, cornerRadius: 12)
                                }
                            }

                            // Subsequent Magazine Story Rows
                            if scopedNews.count > 1 {
                                Section("Earlier") {
                                    ForEach(scopedNews.dropFirst()) { item in
                                        MacNewsStoryRow(item: item)
                                            .tag(item)
                                            .padding(.vertical, 3)
                                            .glassListRow(isSelected: selectedNews == item)
                                    }
                                }
                            }
                        }
                        .listStyle(.inset)
                    }
                }
                .frame(minWidth: 260, idealWidth: 320, maxWidth: 420)
                .layoutPriority(0)
            }

            // Right Pane: Full Reading Pane & Serena AI Briefing
            Group {
                if let item = effectiveSelection {
                    detailPane(for: item)
                } else {
                    ContentUnavailableView("Select a story", systemImage: "newspaper", description: Text("Pick a headline on the left to read it with its brief."))
                }
            }
            .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
            .layoutPriority(1)
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        listExpanded.toggle()
                    }
                } label: {
                    Image(systemName: listExpanded ? "sidebar.left" : "sidebar.leading")
                }
                .help(listExpanded ? "Collapse news rail" : "Show news rail")
            }

        }
        .onChange(of: effectiveSelection) { _, newItem in
            if let newItem {
                Task {
                    await detailModel.load(item: newItem, lang: language)
                }
            }
        }
        .onChange(of: language) { _, newLang in
            if let item = effectiveSelection {
                Task {
                    await detailModel.load(item: item, lang: newLang)
                }
            }
        }
        .onChange(of: store.newsFocusId) { _, _ in
            adoptFocus()
        }
        .onChange(of: store.newsCompanyFocus?.id) { _, _ in
            adoptCompanyFocus()
        }
        .task {
            adoptFocus()
            adoptCompanyFocus()
            if let item = effectiveSelection {
                await detailModel.load(item: item, lang: language)
            }
        }
    }

    /// One company's headlines, as the sidebar's News page asks for them.
    private func adoptCompanyFocus() {
        guard let company = store.newsCompanyFocus else { return }
        store.newsCompanyFocus = nil
        scope = .company
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        newsSearch = ticker.isEmpty ? (company.name ?? company.id) : ticker
    }

    private func adoptFocus() {
        guard let id = store.newsFocusId else { return }
        store.newsFocusId = nil
        guard let match = store.news.first(where: { $0.id == id }) else { return }
        scope = .all
        newsSearch = ""
        selectedNews = match
    }

    // MARK: - Detail Reading Pane

    private func detailPane(for item: MacNewsItem) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Editorial Masthead
                masthead(for: item)

                Divider()

                // AI Briefing or Standfirst
                let isCurrent = detailModel.briefKey == MacNewsDetailViewModel.key(for: item, lang: language)
                if isCurrent, let brief = detailModel.brief {
                    briefingContent(brief: brief, item: item)
                } else if isCurrent, detailModel.loading {
                    writingBanner
                } else {
                    standfirstView(for: item)
                }

                if isCurrent, let err = detailModel.error {
                    Label(err, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }

                // Quick Action Buttons
                actionRow(for: item)
            }
            .padding(24)
            .frame(maxWidth: 900, alignment: .leading)
        }
        .background(Color(NSColor.textBackgroundColor))
    }

    private func masthead(for item: MacNewsItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if let ticker = item.ticker, !ticker.isEmpty {
                    Button {
                        store.selectTicker(ticker)
                        store.selectedTab = .market
                    } label: {
                        Text(ticker.uppercased())
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.accentColor, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .help("View quote in Market Radar")
                }

                if let category = item.category, !category.isEmpty {
                    Text(category.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                }

                Spacer()

                GlassSegmentedPicker("Language", selection: $language, segments: ["en": "English", "zh": "中文"])
                .controlSize(.small)
                .frame(width: 140)

                if let rawURL = item.url, let url = URL(string: rawURL) {
                    Button {
                        withAnimation {
                            store.openInEmbeddedBrowser(url)
                        }
                    } label: {
                        Label("Read source", systemImage: "globe")
                    }
                    .controlSize(.small)
                    .help("Open the original story in the research browser")
                }
            }

            Text(item.title)
                .font(.system(.title, design: .serif).weight(.bold))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 6) {
                if let source = item.source, !source.isEmpty {
                    Text(source)
                        .font(.subheadline.weight(.semibold))
                }
                if !item.timeAgo.isEmpty {
                    Text("·").foregroundStyle(.tertiary)
                    Text(item.timeAgo)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func standfirstView(for item: MacNewsItem) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(.system(.title3, design: .serif))
                    .foregroundStyle(.secondary)
                    .lineSpacing(5)
            }

            VStack(alignment: .leading, spacing: 12) {
                Label("Investment brief", systemImage: "sparkles")
                    .font(.dsHeadline)
                Text("What happened, why it matters for the valuation, the risks, and the markers to check next — written from the article and grounded sources.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button {
                    Task {
                        await detailModel.load(item: item, lang: language, forceRefresh: false)
                    }
                } label: {
                    HStack {
                        Image(systemName: "bolt.fill")
                        Text("Write the brief")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
            .padding(16)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        }
    }

    private var writingBanner: some View {
        HStack(spacing: 12) {
            ProgressView().controlSize(.small)
            VStack(alignment: .leading, spacing: 2) {
                Text("Writing the brief…")
                    .font(.subheadline.weight(.medium))
                Text("Reading the article and grounding the implications.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }

    private func briefingContent(brief: MacNewsBrief, item: MacNewsItem) -> some View {
        VStack(alignment: .leading, spacing: 22) {
            // What Happened
            let what = brief.whatHappened(lang: language)
            if !what.isEmpty {
                articleBlock("What happened", body: what)
            }

            // Why It Matters
            let why = brief.whyItMatters(lang: language)
            if !why.isEmpty {
                articleBlock("Why it matters", body: why)
            }

            // Context
            let contextRows = brief.contextBullets(lang: language)
            if !contextRows.isEmpty {
                bulletBlock("Context", rows: contextRows)
            }

            // Watch Next
            let watchRows = brief.watchNextBullets(lang: language)
            if !watchRows.isEmpty {
                bulletBlock("Watch next", rows: watchRows)
            }

            // Sources & Quality
            if let sources = brief.sources, !sources.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Sources")
                        .font(.dsLabel)
                        .foregroundStyle(.secondary)
                    ForEach(Array(sources.enumerated()), id: \.offset) { _, s in
                        if let u = s.url, let linkURL = URL(string: u) {
                            Link(destination: linkURL) {
                                HStack(spacing: 6) {
                                    Image(systemName: "link")
                                        .font(.caption2)
                                    Text(s.title ?? u)
                                        .font(.footnote)
                                        .lineLimit(1)
                                }
                            }
                        }
                    }
                }
            }

            HStack(spacing: 8) {
                if let confidence = brief.confidence {
                    MacStatusPill(text: "\(confidence.capitalized) Confidence", color: confidence.lowercased() == "high" ? .green : .orange)
                }
                Spacer()
                Button {
                    guard MacTokenConfirm.ask() else { return }
                    Task {
                        await detailModel.load(item: item, lang: language, forceRefresh: true)
                    }
                } label: {
                    Label("Regenerate", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
    }

    private func articleBlock(_ title: String, body: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.dsLabel)
                .foregroundStyle(.secondary)
            Text(body)
                .font(.system(.body, design: .serif))
                .lineSpacing(5)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func bulletBlock(_ title: String, rows: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.dsLabel)
                .foregroundStyle(.secondary)
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top, spacing: 8) {
                    Circle()
                        .fill(Color.accentColor)
                        .frame(width: 5, height: 5)
                        .padding(.top, 6)
                    Text(row)
                        .font(.callout)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func actionRow(for item: MacNewsItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()
            Label("Ask Warren", systemImage: "bubble.left.and.bubble.right")
                .font(.dsHeadline)
            Text("Moats, capital efficiency and valuation impact of this story, in the value-investing frame.")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Button {
                    let prompt = "Evaluate this news event from a value investing perspective. What does it tell us about the competitive moat and long-term earnings power?"
                    let company = store.companies.first { c in
                        (item.ticker != nil && c.ticker?.uppercased() == item.ticker?.uppercased())
                            || (item.companyName != nil && c.name == item.companyName)
                    }
                    store.askWarren(prompt, context: .news(item: item), company: company)
                } label: {
                    Label("Ask about this story", systemImage: "sparkles")
                }
                .buttonStyle(.bordered)
                .disabled(!store.canRunTasks)

                if let ticker = item.ticker, !ticker.isEmpty {
                    Button {
                        store.openSignalLog(seedTicker: ticker)
                    } label: {
                        Label("Log signal", systemImage: "flag")
                    }
                    .buttonStyle(.bordered)
                    .help("Log a bullish / bearish call on \(ticker) from this story (⌘L)")
                }
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - Apple News Lead Card

struct MacNewsLeadCard: View {
    let item: MacNewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: symbol)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(tone)
                if let badge = item.ticker ?? item.companyName {
                    MacStatusPill(text: badge.uppercased(), color: tone)
                }
                Spacer()
                Text("Top story").font(.dsLabel).foregroundStyle(.secondary)
            }

            Text(item.title)
                .font(.system(size: 17, weight: .bold))
                .lineLimit(3)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)

            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }

            HStack(spacing: 6) {
                if let src = item.source, !src.isEmpty {
                    Text(src).font(.dsCaption.weight(.semibold))
                }
                if !item.timeAgo.isEmpty {
                    Text("·").font(.dsCaption).foregroundStyle(.tertiary)
                    Text(item.timeAgo).font(.dsCaption).foregroundStyle(.secondary)
                }
            }
            .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appleGlassCard()
    }

    private var tone: Color {
        let palette: [Color] = [.blue, .indigo, .purple, .teal, .orange, .pink]
        return palette[abs(item.title.hashValue) % palette.count]
    }

    private var symbol: String {
        let c = (item.category ?? "").lowercased()
        if c.contains("earning") { return "chart.bar.doc.horizontal" }
        if c.contains("deal") || c.contains("m&a") { return "arrow.triangle.merge" }
        if c.contains("regulat") || c.contains("legal") { return "building.columns" }
        return "newspaper"
    }
}

// MARK: - Magazine Story Row

struct MacNewsStoryRow: View {
    let item: MacNewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                if let ticker = item.ticker, !ticker.isEmpty {
                    Text(ticker.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Color.accentColor)
                }
                if let src = item.source, !src.isEmpty {
                    Text(src)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if !item.timeAgo.isEmpty {
                    Text(item.timeAgo)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            Text(item.title)
                .font(.headline)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}
