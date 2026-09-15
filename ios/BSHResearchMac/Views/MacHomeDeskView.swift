import SwiftUI

struct MacHomeDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var searchQuery = ""
    @State private var autocompleteHits: [MacAutocompleteHit] = []
    @State private var searching = false
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Command Center Search Bar
                searchCommandBar

                // Search Results Overlay / Section if active
                if !searchQuery.isEmpty {
                    searchResultsSection
                }

                // Active Research Jobs & Pipelines
                if !store.activeJobs.isEmpty || !store.runningReports.isEmpty {
                    activePipelinesSection
                }

                // Market Posture & Regime Pill
                postureAndRegimeSection

                // Ticker tape + Major Market Indices Ribbon
                MacTickerTapeView()
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                marketIndicesRibbon

                // Watchlist Quick Deck & Top Movers
                HStack(alignment: .top, spacing: 20) {
                    watchlistSection
                        .frame(maxWidth: .infinity, alignment: .leading)

                    moversSection
                        .frame(maxWidth: 340, alignment: .leading)
                }

                // Recent Research Memos Library (with 1-click Document Viewer link)
                recentMemosSection

                // Breaking Market Headlines Preview
                breakingNewsSection
            }
                .dsPage()
            }
            .background(Color.dsCanvas)
        .task {
            if shouldRefreshOnAppear {
                await store.refreshHome()
            }
        }
    }

    private var shouldRefreshOnAppear: Bool {
        // Until the session check has run, bootstrap owns the first load; a second
        // refreshHome here would duplicate every request at launch.
        if !store.authChecked || store.loading { return false }
        if store.isOfflineMode || store.error != nil { return true }
        guard let last = store.lastSyncDate else { return true }
        return Date().timeIntervalSince(last) > 60
    }

    private func open(_ hit: MacAutocompleteHit) {
        let name = hit.name?.lowercased()
        let ticker = hit.ticker?.uppercased()
        let local = store.companies.first { company in
            (hit.companyId != nil && company.id == hit.companyId)
                || (name != nil && company.name?.lowercased() == name)
                || (ticker != nil && !ticker!.isEmpty && company.ticker?.uppercased() == ticker)
        }
        if let local {
            store.showCompany(local)
        } else if let ticker, !ticker.isEmpty {
            store.showTicker(ticker)
        } else {
            store.openCommandPalette(seed: hit.name ?? searchQuery)
        }
    }

    // MARK: - Search Command Bar

    private var searchCommandBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)

                TextField("Search companies and tickers — or press ⌘K for the command line", text: $searchQuery)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15))
                    .onChange(of: searchQuery) { _, newValue in
                        performSearch(query: newValue)
                    }

                if searching {
                    ProgressView()
                        .controlSize(.small)
                }

                if !searchQuery.isEmpty {
                    Button {
                        searchQuery = ""
                        autocompleteHits = []
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .appleGlassCard(isInteractive: true)
        }
    }

    private func performSearch(query: String) {
        searchTask?.cancel()
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else {
            autocompleteHits = []
            searching = false
            return
        }

        searching = true
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 200_000_000)
            if Task.isCancelled { return }
            do {
                let hits = try await MacAPIClient.shared.searchAutocomplete(query: q, limit: 8)
                if !Task.isCancelled {
                    autocompleteHits = hits
                    searching = false
                }
            } catch {
                if !Task.isCancelled {
                    searching = false
                }
            }
        }
    }

    @ViewBuilder
    private var searchResultsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Matches", systemImage: "building.2")
                                    .font(.dsHeadline)
                Spacer()
                Text("\(autocompleteHits.count) results")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if autocompleteHits.isEmpty && !searching {
                HStack(spacing: 12) {
                    Text("No matching companies found for '\(searchQuery)'")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Button {
                        store.openCommandPalette(seed: searchQuery)
                    } label: {
                        Label("Deep Search with Claude…", systemImage: "sparkle.magnifyingglass")
                    }
                    .controlSize(.small)
                    .disabled(!store.canRunTasks)
                    .help(store.canRunTasks ? "Find the company with Claude and add it to the pipeline (⌘K)" : "Sign in to run searches")
                }
                .padding(.vertical, 8)
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(autocompleteHits) { hit in
                        Button {
                            open(hit)
                        } label: {
                            HStack(spacing: 12) {
                                if let ticker = hit.ticker, !ticker.isEmpty {
                                    Text(ticker.uppercased())
                                        .font(.caption.monospacedDigit().weight(.bold))
                                        .foregroundStyle(Color.accentColor)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(hit.displayTitle)
                                        .font(.subheadline.weight(.medium))
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)
                                    Text(hit.displaySubtitle)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }

                                Spacer()

                                Image(systemName: "arrow.right.circle")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(10)
                            .appleGlassTile()
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(16)
        .appleGlassCard()
    }

    // MARK: - Active Research Pipelines

    private var activePipelinesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Running now", systemImage: "gearshape.arrow.triangle.2.circlepath")
                            .font(.dsHeadline)

            VStack(spacing: 8) {
                // Running Reports
                ForEach(store.runningReports) { report in
                    HStack(spacing: 12) {
                        ProgressView()
                            .controlSize(.small)

                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 6) {
                                Text(report.companyName ?? report.companyId ?? "Research Memo")
                                    .font(.subheadline.weight(.semibold))
                                Text("·")
                                    .foregroundStyle(.secondary)
                                Text(report.reportType ?? "Analysis")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            if let stage = report.stage, !stage.isEmpty {
                                Text(stage)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        Spacer()

                        if let prog = report.progress {
                            Text("\(prog)%")
                                .font(.caption.monospacedDigit().weight(.bold))
                                .foregroundStyle(Color.accentColor)
                        }

                        Button("Follow") {
                            store.showBlotter = true
                            store.blotterTab = .jobs
                            store.selectedJobId = report.id
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .help("Follow this run in the Jobs blotter")
                    }
                    .padding(12)
                    .appleGlassTile()
                }

                // Other Background Jobs
                ForEach(store.activeJobs.prefix(3)) { job in
                    HStack(spacing: 12) {
                        ProgressView()
                            .controlSize(.small)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(job.title ?? job.kind ?? "Background Task")
                                .font(.subheadline.weight(.semibold))
                            if let msg = job.lastMessage ?? job.subtitle {
                                Text(msg)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        Spacer()

                        if let prog = job.progress {
                            Text("\(prog)%")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .appleGlassTile()
                }
            }
        }
        .padding(16)
        .appleGlassCard(tint: .orange)
    }

    // MARK: - Posture & Regime Section

    private var postureAndRegimeSection: some View {
        let regime = store.marketPulsePayload?.sections?.marketRegime
        let posture = (regime?.posture ?? "neutral").capitalized
        let rawSignal = store.marketPulsePayload?.summary?.topSignal ?? ""
        let topSignal = rawSignal.isEmpty ? "Source-backed signal pending." : rawSignal
        let breadth = regime?.breadth

        return HStack(spacing: 16) {
            // Posture Badge
            VStack(alignment: .leading, spacing: 4) {
                Text("Market posture")
                                    .font(.dsLabel)
                    .foregroundStyle(.secondary)

                HStack(spacing: 8) {
                    Circle()
                        .fill(postureColor(posture))
                        .frame(width: 10, height: 10)
                    Text(posture)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.primary)
                }
            }
            .padding(.trailing, 8)

            Divider().frame(height: 36)

            // Top Signal
            VStack(alignment: .leading, spacing: 2) {
                Text("Regime signal")
                                    .font(.dsLabel)
                    .foregroundStyle(.secondary)
                Text(topSignal)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
            }

            Spacer()

            if let breadth, breadth.total > 0 {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("Breadth")
                                            .font(.dsLabel)
                        .foregroundStyle(.secondary)
                    Text("\(breadth.positiveSignals ?? 0) up · \(breadth.negativeSignals ?? 0) down · \(breadth.neutralSignals ?? 0) flat")
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                        .foregroundStyle((breadth.positiveSignals ?? 0) >= (breadth.negativeSignals ?? 0) ? Color.green : Color.orange)
                }
                .padding(.trailing, 8)
            }

            Button {
                store.selectedTab = .pulse
            } label: {
                        Label("Market Pulse", systemImage: "waveform.path.ecg")
                    }
                    .controlSize(.small)
                }
                .padding(14)
                .appleGlassCard()
    }

    private func postureColor(_ posture: String) -> Color {
        let p = posture.lowercased()
        if p.contains("risk-on") || p.contains("bull") { return .green }
        if p.contains("defensive") || p.contains("bear") { return .orange }
        return .blue
    }

    // MARK: - Major Market Indices Ribbon

    private var marketIndicesRibbon: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Benchmarks", systemImage: "chart.line.uptrend.xyaxis")
                                    .font(.dsHeadline)
                Spacer()
                Button {
                    Task { await store.refreshMarket() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .font(.caption)
                .help("Refresh market indices")
            }

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 10) {
                ForEach(store.indicesQuotes) { quote in
                    Button {
                        store.selectTicker(quote.ticker)
                        store.selectedTab = .market
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(quote.ticker)
                                    .font(.subheadline.monospacedDigit().weight(.bold))
                                Spacer()
                                Image(systemName: (quote.pct ?? 0) >= 0 ? "arrow.up.right" : "arrow.down.right")
                                    .font(.caption2)
                                    .foregroundStyle((quote.pct ?? 0) >= 0 ? Color.green : Color.red)
                            }

                            if let last = quote.last {
                                Text(String(format: "$%.2f", last))
                                    .font(.headline.monospacedDigit())
                            } else {
                                Text("—")
                                    .font(.headline)
                            }

                            if let pct = quote.pct {
                                Text(String(format: "%+.2f%%", pct))
                                    .font(.caption.monospacedDigit().weight(.semibold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(
                                        pct >= 0 ? Color.green.opacity(0.85) : Color.red.opacity(0.85),
                                        in: RoundedRectangle(cornerRadius: 4)
                                    )
                            }
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .appleGlassCard(isInteractive: true)
                    }
                    .buttonStyle(.plain)
                    .help("Open \(quote.ticker) in Market Radar")
                }
            }
        }
    }

    // MARK: - Watchlist Section

    private var pinnedQuotes: [MacQuote] {
        let pinned = Set(store.pinnedTickers.map { $0.uppercased() })
        return store.watchlist.filter { pinned.contains($0.ticker.uppercased()) }
    }

    private var watchlistSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Watchlist", systemImage: "star")
                    .font(.dsHeadline)
                Spacer()
                Button("Market Radar") { store.selectedTab = .market }
                    .buttonStyle(.link)
                    .font(.dsCaption.weight(.semibold))
            }

            if store.pinnedTickers.isEmpty {
                Text("No pinned tickers. Star tickers in Market Radar to track them here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else if pinnedQuotes.isEmpty {
                Text("No quotes yet for your pinned tickers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    ForEach(pinnedQuotes.prefix(5)) { quote in
                        Button {
                            store.selectTicker(quote.ticker)
                            store.selectedTab = .market
                        } label: {
                            HStack(spacing: 10) {
                                Text(quote.ticker)
                                    .font(.subheadline.monospacedDigit().weight(.bold))
                                    .frame(width: 55, alignment: .leading)

                                if let name = quote.name, !name.isEmpty {
                                    Text(name)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }

                                Spacer()

                                if let last = quote.last {
                                    Text(String(format: "$%.2f", last))
                                        .font(.subheadline.monospacedDigit())
                                }

                                if let pct = quote.pct {
                                    Text(String(format: "%+.2f%%", pct))
                                        .font(.caption.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(pct >= 0 ? Color.green : Color.red)
                                        .frame(width: 55, alignment: .trailing)
                                }
                            }
                            .padding(10)
                            .appleGlassTile()
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(16)
        .appleGlassCard()
    }

    // MARK: - Movers Section

    private var moversSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Top movers", systemImage: "flame")
                .font(.dsHeadline)

            VStack(spacing: 8) {
                // Gainers
                ForEach(store.gainers.prefix(3)) { quote in
                    Button {
                        store.selectTicker(quote.ticker)
                        store.selectedTab = .market
                    } label: {
                        HStack {
                            Text(quote.ticker)
                                .font(.caption.monospacedDigit().weight(.bold))
                            Spacer()
                            if let last = quote.last {
                                Text(String(format: "$%.2f", last))
                                    .font(.caption.monospacedDigit())
                            }
                            if let pct = quote.pct {
                                Text(String(format: "+%.2f%%", pct))
                                    .font(.caption.monospacedDigit().weight(.bold))
                                    .foregroundStyle(Color.green)
                            }
                        }
                        .padding(8)
                        .appleGlassTile()
                    }
                    .buttonStyle(.plain)
                }

                // Losers
                ForEach(store.losers.prefix(2)) { quote in
                    Button {
                        store.selectTicker(quote.ticker)
                        store.selectedTab = .market
                    } label: {
                        HStack {
                            Text(quote.ticker)
                                .font(.caption.monospacedDigit().weight(.bold))
                            Spacer()
                            if let last = quote.last {
                                Text(String(format: "$%.2f", last))
                                    .font(.caption.monospacedDigit())
                            }
                            if let pct = quote.pct {
                                Text(String(format: "%.2f%%", pct))
                                    .font(.caption.monospacedDigit().weight(.bold))
                                    .foregroundStyle(Color.red)
                            }
                        }
                        .padding(8)
                        .appleGlassTile()
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .appleGlassCard()
    }

    // MARK: - Recent Memos Section (1-Click Document Viewer Link)

    private var recentMemosSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Recent memos", systemImage: "doc.text")
                    .font(.dsHeadline)
                Spacer()
                Button("Documents") { store.selectedTab = .documents }
                    .buttonStyle(.link)
                    .font(.dsCaption.weight(.semibold))
            }

            if store.recentReports.isEmpty {
                Text("No memos yet. Press ⌘N to run the first one.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(store.recentReports.prefix(6)) { report in
                        HStack(spacing: 12) {
                            MacMonogram(name: report.companyName ?? report.companyId ?? "Memo", size: 34)

                            VStack(alignment: .leading, spacing: 3) {
                                Text(report.companyName ?? report.companyId ?? "Investment Memo")
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                HStack(spacing: 6) {
                                    Text(report.reportType ?? "Memo")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("·")
                                        .foregroundStyle(.tertiary)
                                    Text(report.timeAgo)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }

                            Spacer()

                            if report.canOpen {
                                Button {
                                    store.openReportInViewer(report)
                                } label: {
                                    Label("Read", systemImage: "doc.richtext")
                                }
                                .controlSize(.small)
                                .help("Open in the document viewer")
                            } else if !report.isComplete && !report.isFailed {
                                Button {
                                    store.showBlotter = true
                                    store.blotterTab = .jobs
                                    store.selectedJobId = report.id
                                } label: {
                                    Label("Follow", systemImage: "waveform.path.ecg")
                                }
                                .controlSize(.small)
                                .help("Follow this run in the Jobs blotter")
                            } else {
                                Text(report.statusLabel)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                                }
                                .padding(10)
                                .appleGlassTile()
                    }
                }
            }
        }
        .padding(16)
        .appleGlassCard()
    }

    private func avatarInitials(_ report: MacReport) -> String {
        let name = report.companyName ?? report.companyId ?? "BS"
        let parts = name.split(separator: " ").prefix(2)
        return parts.compactMap { $0.first }.map { String($0) }.joined().uppercased()
    }

    // MARK: - Breaking News Section

    private var breakingNewsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Latest news", systemImage: "newspaper")
                    .font(.dsHeadline)
                Spacer()
                Button("News Desk") { store.selectedTab = .news }
                    .buttonStyle(.link)
                    .font(.dsCaption.weight(.semibold))
            }

            VStack(spacing: 8) {
                ForEach(store.news.prefix(4)) { item in
                    Button {
                        store.newsFocusId = item.id
                        store.selectedTab = .news
                    } label: {
                        HStack(spacing: 12) {
                            if let ticker = item.ticker, !ticker.isEmpty {
                                Text(ticker.uppercased())
                                    .font(.caption2.monospacedDigit().weight(.bold))
                                    .foregroundStyle(Color.accentColor)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                            }

                            Text(item.title)
                                .font(.subheadline)
                                .lineLimit(1)
                                .foregroundStyle(.primary)

                            Spacer()

                            if let src = item.source {
                                Text(src)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }

                            if !item.timeAgo.isEmpty {
                                Text(item.timeAgo)
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .padding(10)
                        .appleGlassTile()
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .appleGlassCard()
    }
}
