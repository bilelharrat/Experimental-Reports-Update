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

    private var currentItemId: String = ""

    func load(item: MacNewsItem, lang: String = "en", forceRefresh: Bool = false) async {
        if currentItemId == item.id && brief != nil && !forceRefresh { return }
        currentItemId = item.id
        if !forceRefresh {
            brief = nil
        }
        loading = true
        error = nil
        defer { loading = false }

        do {
            brief = try await MacAPIClient.shared.fetchNewsBrief(item: item, lang: lang, refresh: forceRefresh)
        } catch {
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
                            Picker("Scope", selection: $scope) {
                                ForEach(MacNewsScope.allCases) { s in
                                    Text(s.rawValue).tag(s)
                                }
                            }
                            .pickerStyle(.segmented)

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
                                }
                            }

                            // Subsequent Magazine Story Rows
                            if scopedNews.count > 1 {
                                Section("Earlier Stories") {
                                    ForEach(scopedNews.dropFirst()) { item in
                                        MacNewsStoryRow(item: item)
                                            .tag(item)
                                            .padding(.vertical, 3)
                                    }
                                }
                            }
                        }
                        .listStyle(.inset(alternatesRowBackgrounds: true))
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
                    ContentUnavailableView("Select a Story", systemImage: "newspaper", description: Text("Select an article from the news stream to view the full intelligence brief."))
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

            ToolbarItem(placement: .automatic) {
                Picker("Language", selection: $language) {
                    Text("English").tag("en")
                    Text("中文").tag("zh")
                }
                .pickerStyle(.segmented)
                .controlSize(.small)
            }
        }
        .onChange(of: selectedNews) { _, newItem in
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
        .task {
            if let first = scopedNews.first {
                await detailModel.load(item: first, lang: language)
            }
        }
    }

    // MARK: - Detail Reading Pane

    private func detailPane(for item: MacNewsItem) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Editorial Masthead
                masthead(for: item)

                Divider()

                // AI Briefing or Standfirst
                if let brief = detailModel.brief {
                    briefingContent(brief: brief, item: item)
                } else if detailModel.loading {
                    writingBanner
                } else {
                    standfirstView(for: item)
                }

                if let err = detailModel.error {
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

                if let rawURL = item.url, let url = URL(string: rawURL) {
                    Button {
                        withAnimation {
                            store.openInEmbeddedBrowser(url)
                        }
                    } label: {
                        Label("Read Source in Browser", systemImage: "globe")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Open original story inside embedded research browser")
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
                Label("Generate Investment Briefing", systemImage: "sparkles")
                    .font(.headline)
                Text("Synthesize what happened, why it matters for equity valuation, risk vectors, and checkable markers using Serena LLM.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button {
                    Task {
                        await detailModel.load(item: item, lang: language, forceRefresh: true)
                    }
                } label: {
                    HStack {
                        Image(systemName: "bolt.fill")
                        Text("Draft Long-Form Briefing")
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
                Text("Synthesizing investment brief with Serena LLM…")
                    .font(.subheadline.weight(.medium))
                Text("Ingesting article content and grounding thesis implications.")
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
                articleBlock("What Happened", body: what)
            }

            // Why It Matters
            let why = brief.whyItMatters(lang: language)
            if !why.isEmpty {
                articleBlock("Why It Matters", body: why)
            }

            // Context
            let contextRows = brief.contextBullets(lang: language)
            if !contextRows.isEmpty {
                bulletBlock("Market & Company Context", rows: contextRows)
            }

            // Watch Next
            let watchRows = brief.watchNextBullets(lang: language)
            if !watchRows.isEmpty {
                bulletBlock("Upcoming Markers & Risks", rows: watchRows)
            }

            // Sources & Quality
            if let sources = brief.sources, !sources.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("SOURCES")
                        .font(.caption.weight(.bold))
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
                    Task {
                        await detailModel.load(item: item, lang: language, forceRefresh: true)
                    }
                } label: {
                    Label("Regenerate Brief", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
    }

    private func articleBlock(_ title: String, body: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.caption.weight(.bold))
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
            Text(title.uppercased())
                .font(.caption.weight(.bold))
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
            Label("Consult Warren Buffett / Co-Pilot", systemImage: "bubble.left.and.bubble.right.fill")
                .font(.headline)
            Text("Engage the Warren Buffett analytical model on moats, capital efficiency, and valuation impact.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Button {
                let prompt = "Please evaluate this news event from a value investing perspective: '\(item.title)'. Company/Ticker: \(item.companyName ?? item.ticker ?? "Market"). What does this tell us about the competitive moat and long-term earnings power?"
                store.sendCopilotMessage(prompt: prompt)
                store.selectedTab = .copilot
            } label: {
                Label("Ask Warren About This Story", systemImage: "sparkles")
            }
            .buttonStyle(.bordered)
        }
        .padding(.top, 8)
    }
}

// MARK: - Apple News Lead Card

struct MacNewsLeadCard: View {
    let item: MacNewsItem

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                LinearGradient(
                    colors: [tone.opacity(0.85), tone.opacity(0.45)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                Image(systemName: symbol)
                    .font(.system(size: 68, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.2))
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .padding(.trailing, 14)

                VStack(alignment: .leading, spacing: 6) {
                    if let badge = item.ticker ?? item.companyName {
                        Text(badge.uppercased())
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
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
            .frame(height: 150)

            VStack(alignment: .leading, spacing: 8) {
                if let summary = item.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }

                HStack(spacing: 6) {
                    if let src = item.source, !src.isEmpty {
                        Text(src).font(.caption2.weight(.semibold))
                    }
                    if !item.timeAgo.isEmpty {
                        Text("·").font(.caption2).foregroundStyle(.tertiary)
                        Text(item.timeAgo).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .foregroundStyle(.secondary)
            }
            .padding(12)
        }
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
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
