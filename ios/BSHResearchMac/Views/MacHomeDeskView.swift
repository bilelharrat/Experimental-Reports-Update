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

                // Major Market Indices Ribbon
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
            .padding(24)
            .frame(maxWidth: 1100, alignment: .leading)
        }
        .background(Color(NSColor.windowBackgroundColor))
        .task {
            await store.refreshHome()
        }
    }

    // MARK: - Search Command Bar

    private var searchCommandBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                Image(systemName: "sparkle.magnifyingglass")
                    .font(.title2)
                    .foregroundStyle(Color.accentColor)

                TextField("Search companies, tickers, memos, or SEC filings (e.g. AAPL, Berkshire, Semiconductor)…", text: $searchQuery)
                    .textFieldStyle(.plain)
                    .font(.title3)
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
            .padding(14)
            .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.accentColor.opacity(searchQuery.isEmpty ? 0.15 : 0.4), lineWidth: 1.5)
            )
            .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
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
                Label("Matching Companies & Tickers", systemImage: "building.2.crop.circle")
                    .font(.headline)
                Spacer()
                Text("\(autocompleteHits.count) results")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if autocompleteHits.isEmpty && !searching {
                Text("No matching companies found for '\(searchQuery)'")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(autocompleteHits) { hit in
                        Button {
                            if let ticker = hit.ticker, !ticker.isEmpty {
                                store.selectTicker(ticker)
                                store.selectedTab = .market
                            } else if let name = hit.name {
                                if let match = store.companies.first(where: { $0.name == name || $0.id == hit.id }) {
                                    store.selectedCompany = match
                                    store.selectedTab = .research
                                }
                            }
                        } label: {
                            HStack(spacing: 12) {
                                if let ticker = hit.ticker, !ticker.isEmpty {
                                    Text(ticker.uppercased())
                                        .font(.caption.monospaced().weight(.bold))
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
                            .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
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
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Active Research Pipelines

    private var activePipelinesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Active Research Pipelines & Jobs", systemImage: "gearshape.arrow.triangle.2.circlepath")
                .font(.headline)

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

                        Button("View") {
                            store.openReportInViewer(report)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    .padding(12)
                    .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
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
                    .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(16)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.orange.opacity(0.2), lineWidth: 1)
        )
    }

    // MARK: - Posture & Regime Section

    private var postureAndRegimeSection: some View {
        let posture = store.marketPulsePayload?.sections?.marketRegime?.posture ?? "Neutral"
        let topSignal = store.marketPulsePayload?.summary?.topSignal ?? "Fed rate trajectory and earnings revisions drive market dispersion."
        let adRatio = store.marketPulsePayload?.sections?.marketRegime?.breadth?.advanceDeclineRatio

        return HStack(spacing: 16) {
            // Posture Badge
            VStack(alignment: .leading, spacing: 4) {
                Text("MARKET POSTURE")
                    .font(.caption2.weight(.bold))
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
                Text("STRATEGIC REGIME SIGNAL")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                Text(topSignal)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
            }

            Spacer()

            if let ad = adRatio {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("BREADTH A/D")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.2f", ad))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                        .foregroundStyle(ad >= 1.0 ? Color.green : Color.orange)
                }
                .padding(.trailing, 8)
            }

            Button {
                store.selectedTab = .pulse
            } label: {
                Label("Pulse Desk", systemImage: "waveform.path.ecg")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(14)
        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
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
                Label("Major Indices & Benchmarks", systemImage: "chart.line.uptrend.xyaxis")
                    .font(.headline)
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
                                    .font(.subheadline.monospaced().weight(.bold))
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
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .help("Open \(quote.ticker) in Market Radar")
                }
            }
        }
    }

    // MARK: - Watchlist Section

    private var watchlistSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Pinned Watchlist", systemImage: "star.fill")
                    .font(.headline)
                    .foregroundStyle(Color.orange)
                Spacer()
                Button {
                    store.selectedTab = .market
                } label: {
                    Text("View Radar →")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.plain)
            }

            if store.watchlist.isEmpty {
                Text("No pinned tickers. Star tickers in Market Radar to track them here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    ForEach(store.watchlist.prefix(5)) { quote in
                        Button {
                            store.selectTicker(quote.ticker)
                            store.selectedTab = .market
                        } label: {
                            HStack(spacing: 10) {
                                Text(quote.ticker)
                                    .font(.subheadline.monospaced().weight(.bold))
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
                            .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Movers Section

    private var moversSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Top Movers", systemImage: "flame.fill")
                .font(.headline)
                .foregroundStyle(Color.red)

            VStack(spacing: 8) {
                // Gainers
                ForEach(store.gainers.prefix(3)) { quote in
                    Button {
                        store.selectTicker(quote.ticker)
                        store.selectedTab = .market
                    } label: {
                        HStack {
                            Text(quote.ticker)
                                .font(.caption.monospaced().weight(.bold))
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
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 6))
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
                                .font(.caption.monospaced().weight(.bold))
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
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Recent Memos Section (1-Click Document Viewer Link)

    private var recentMemosSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Recent Research Memos", systemImage: "doc.text.magnifyingglass")
                    .font(.headline)
                Spacer()
                Button {
                    store.selectedTab = .documents
                } label: {
                    Text("All Documents Library →")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.plain)
            }

            if store.recentReports.isEmpty {
                Text("No generated research memos available.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(store.recentReports.prefix(6)) { report in
                        HStack(spacing: 12) {
                            // Initials Avatar
                            Circle()
                                .fill(Color.accentColor.opacity(0.15))
                                .frame(width: 38, height: 38)
                                .overlay(
                                    Text(avatarInitials(report))
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(Color.accentColor)
                                )

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

                            // Direct 1-Click Button to Document Viewer
                            Button {
                                store.openReportInViewer(report)
                            } label: {
                                Label("Read Memo", systemImage: "doc.richtext")
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                            .help("Open in Document Viewer")
                        }
                        .padding(12)
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
                        )
                    }
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
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
                Label("Breaking Market & Company Disclosures", systemImage: "newspaper")
                    .font(.headline)
                Spacer()
                Button {
                    store.selectedTab = .news
                } label: {
                    Text("News Desk →")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.plain)
            }

            VStack(spacing: 8) {
                ForEach(store.news.prefix(4)) { item in
                    Button {
                        store.selectedTab = .news
                    } label: {
                        HStack(spacing: 12) {
                            if let ticker = item.ticker, !ticker.isEmpty {
                                Text(ticker.uppercased())
                                    .font(.caption2.monospaced().weight(.bold))
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
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }
}
