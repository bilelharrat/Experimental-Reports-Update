import SwiftUI

@MainActor
final class QuoteDetailViewModel: ObservableObject {
    let ticker: String

    @Published var range: ChartRange = .d1
    @Published var chart: QuoteChartPayload?
    @Published var workspace: QuoteWorkspace?
    @Published var chartLoading = false
    @Published var workspaceLoading = false
    @Published var workspaceError: String?
    @Published var error: String?
    @Published var tab: WorkspaceTab = .overview

    enum WorkspaceTab: String, CaseIterable, Identifiable {
        case overview, profile, analysis, holders, options, earnings
        var id: String { rawValue }
        var label: String {
            switch self {
            case .overview: return "Overview"
            case .profile: return "Profile"
            case .analysis: return "Analysis"
            case .holders: return "Holders"
            case .options: return "Options"
            case .earnings: return "Earnings"
            }
        }
    }

    init(ticker: String) {
        self.ticker = ticker.uppercased()
    }

    func loadAll() async {
        async let c: () = loadChart()
        async let w: () = loadWorkspace()
        _ = await (c, w)
    }

    func loadChart() async {
        chartLoading = true
        defer { chartLoading = false }
        do {
            chart = try await APIClient.shared.get(
                "quotes/\(ticker)/chart",
                query: [URLQueryItem(name: "range", value: range.rawValue)]
            )
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func loadWorkspace() async {
        workspaceLoading = true
        workspaceError = nil
        defer { workspaceLoading = false }
        do {
            workspace = try await APIClient.shared.get("quotes/\(ticker)/workspace")
        } catch {
            workspace = nil
            workspaceError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct QuoteDetailView: View {
    @StateObject private var model: QuoteDetailViewModel
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var desk: DeskStore

    init(ticker: String) {
        _model = StateObject(wrappedValue: QuoteDetailViewModel(ticker: ticker))
    }

    private var shareText: String {
        let price = QuoteRow.price(model.chart?.lastPrice, currency: model.chart?.currency)
        let pct = QuoteRow.pct(model.chart?.changePct1d)
        return "\(model.ticker) \(price) (\(pct) today) — BSH Research"
    }

    var body: some View {
        List {
            headerSection
            rangeSection
            chartSection
            statsSection
            tabPickerSection
            workspaceSections
                .id(model.tab)
        }
        .listStyle(.insetGrouped)
        .navigationTitle(model.ticker)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    Task { await desk.toggleWatch(model.ticker) }
                } label: {
                    Image(systemName: desk.isWatched(model.ticker) ? "star.fill" : "star")
                        .foregroundStyle(desk.isWatched(model.ticker) ? .yellow : .accentColor)
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                ShareLink(item: shareText) {
                    Image(systemName: "square.and.arrow.up")
                }
            }
        }
        .refreshable { await model.loadAll() }
        .task {
            await desk.loadIfNeeded()
            await model.loadAll()
        }
        .onChange(of: model.range) { _, _ in
            Task { await model.loadChart() }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Text(model.chart?.name ?? model.workspace?.profile?.name ?? model.ticker)
                    .font(.title3.weight(.semibold))
                if let exchange = model.chart?.exchange ?? model.workspace?.summary?.exchange {
                    Text(exchange)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(QuoteRow.price(model.chart?.lastPrice, currency: model.chart?.currency))
                        .font(.largeTitle.monospacedDigit().weight(.bold))
                    Text(QuoteRow.pct(model.chart?.changePct1d))
                        .font(.title3.monospacedDigit().weight(.semibold))
                        .foregroundStyle(QuoteRow.tone(model.chart?.changePct1d))
                }
                if let asOf = model.chart?.asOf {
                    Text(asOf)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let err = model.error {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }
            .padding(.vertical, 4)
        }
    }

    // MARK: - Range + chart

    private var rangeSection: some View {
        Section {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ChartRange.allCases) { span in
                        Button(span.label) { model.range = span }
                            .buttonStyle(.bordered)
                            .tint(model.range == span ? .accentColor : .secondary)
                            .controlSize(.small)
                    }
                }
                .padding(.vertical, 2)
            }
            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
        }
    }

    private var chartSection: some View {
        Section {
            ZStack {
                QuoteChartCanvas(
                    points: model.chart?.points ?? [],
                    previousClose: model.chart?.previousClose,
                    range: model.range,
                    currency: model.chart?.currency
                )
                if model.chartLoading {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 240)
                }
            }
        }
    }

    // MARK: - Stats

    private var statsSection: some View {
        Section(language.t("market.stats")) {
            let chart = model.chart
            let summary = model.workspace?.summary
            statRow("Open", QuoteRow.price(chart?.open, currency: chart?.currency))
            statRow("High", QuoteRow.price(chart?.high, currency: chart?.currency))
            statRow("Low", QuoteRow.price(chart?.low, currency: chart?.currency))
            statRow("Prev close", chart?.previousClose.map { QuoteRow.price($0, currency: chart?.currency) } ?? summary?.previousClose ?? "—")
            if let day = summary?.dayRange { statRow("Day range", day) }
            if let week = summary?.fiftyTwoWeek { statRow("52W", week) }
            else {
                let hi = QuoteRow.price(chart?.fiftyTwoWeekHigh, currency: chart?.currency)
                let lo = QuoteRow.price(chart?.fiftyTwoWeekLow, currency: chart?.currency)
                if hi != "—" || lo != "—" { statRow("52W", "\(lo) – \(hi)") }
            }
            if let cap = summary?.marketCap { statRow("Market cap", cap) }
            else if let cap = chart?.marketCap { statRow("Market cap", formatCompact(cap)) }
            if let vol = chart?.volume { statRow("Volume", formatCompact(vol)) }
            else if let vol = summary?.volume { statRow("Volume", vol) }
            if let avg = chart?.avgVolume { statRow("Avg volume", formatCompact(avg)) }
            else if let avg = summary?.avgVolume { statRow("Avg volume", avg) }
            if let pe = chart?.peRatio { statRow("P/E", String(format: "%.1f", pe)) }
            if let eps = chart?.eps { statRow("EPS", String(format: "%.2f", eps)) }
            if let beta = chart?.beta { statRow("Beta", String(format: "%.2f", beta)) }
            if let div = summary?.dividend { statRow("Dividend", div) }
            if let yld = summary?.yield { statRow("Yield", yld) }
            else if let dy = chart?.dividendYield { statRow("Div yield", String(format: "%.2f%%", dy * (dy < 1 ? 100 : 1))) }
            if let target = summary?.oneYearTarget { statRow("Target", target) }
            else if let target = model.workspace?.analysis?.target {
                statRow("Target", String(format: "%.2f", target))
            }
        }
    }

    private func statRow(_ label: String, _ value: String) -> some View {
        LabeledContent(label, value: value)
    }

    // MARK: - Workspace tabs

    private var tabPickerSection: some View {
        Section {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(QuoteDetailViewModel.WorkspaceTab.allCases) { tab in
                        Button(tab.label) {
                            model.tab = tab
                        }
                        .buttonStyle(.bordered)
                        .tint(model.tab == tab ? .accentColor : .secondary)
                        .controlSize(.small)
                    }
                }
                .padding(.vertical, 4)
            }
            .listRowInsets(EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12))

            if let err = model.workspaceError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    @ViewBuilder
    private var workspaceSections: some View {
        if model.workspaceLoading && model.workspace == nil {
            Section {
                ProgressView(language.t("common.loading"))
            }
        }

        switch model.tab {
        case .overview:
            overviewBlocks
        case .profile:
            profileBlocks
        case .analysis:
            analysisBlocks
        case .holders:
            holdersBlocks
        case .options:
            optionsBlocks
        case .earnings:
            earningsBlocks
        }
    }

    @ViewBuilder
    private var overviewBlocks: some View {
        if let desc = model.workspace?.profile?.description, !desc.isEmpty {
            Section("About") {
                Text(desc).font(.body).foregroundStyle(.secondary)
            }
        }
        if let profile = model.workspace?.profile {
            Section("Identity") {
                if let sector = profile.sector { LabeledContent("Sector", value: sector) }
                if let industry = profile.industry { LabeledContent("Industry", value: industry) }
                if let region = profile.region { LabeledContent("Region", value: region) }
                if let website = profile.website, let url = URL(string: website) {
                    Link(website, destination: url)
                }
            }
        }
        if let next = model.workspace?.earnings?.nextDate {
            Section("Next earnings") {
                LabeledContent("Date", value: next)
            }
        }
    }

    @ViewBuilder
    private var profileBlocks: some View {
        if let profile = model.workspace?.profile {
            Section("Profile") {
                if let sector = profile.sector { LabeledContent("Sector", value: sector) }
                if let industry = profile.industry { LabeledContent("Industry", value: industry) }
                if let region = profile.region { LabeledContent("Region", value: region) }
                if let website = profile.website, let url = URL(string: website) {
                    Link(website, destination: url)
                }
            }
            if let desc = profile.description, !desc.isEmpty {
                Section("Description") {
                    Text(desc).font(.body)
                }
            }
        } else {
            Section { Text(language.t("market.workspace_empty")).foregroundStyle(.secondary) }
        }
    }

    @ViewBuilder
    private var analysisBlocks: some View {
        if let analysis = model.workspace?.analysis {
            Section("Street") {
                if let t = analysis.target { LabeledContent("Target", value: String(format: "%.2f", t)) }
                if let lo = analysis.targetLow { LabeledContent("Low", value: String(format: "%.2f", lo)) }
                if let hi = analysis.targetHigh { LabeledContent("High", value: String(format: "%.2f", hi)) }
                LabeledContent("Buy / Hold / Sell", value: "\(analysis.buy ?? 0) / \(analysis.hold ?? 0) / \(analysis.sell ?? 0)")
            }
        } else {
            Section { Text(language.t("market.workspace_empty")).foregroundStyle(.secondary) }
        }
    }

    @ViewBuilder
    private var holdersBlocks: some View {
        if let holders = model.workspace?.holders {
            Section("Ownership") {
                if let pct = holders.ownershipPct {
                    LabeledContent("Inst. ownership", value: pct.display)
                }
                if let shares = holders.sharesOut {
                    LabeledContent("Shares out", value: shares.display)
                }
                if let value = holders.holdingsValue {
                    LabeledContent("Holdings value", value: value.display)
                }
            }
            if let rows = holders.holders, !rows.isEmpty {
                Section("Top holders") {
                    ForEach(rows.prefix(12)) { row in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.displayName).font(.subheadline.weight(.semibold))
                            HStack {
                                Text(row.shares?.display ?? "—").font(.caption).foregroundStyle(.secondary)
                                Spacer()
                                Text(row.value?.display ?? "—").font(.caption.monospacedDigit())
                            }
                        }
                    }
                }
            }
        } else {
            Section { Text(language.t("market.workspace_empty")).foregroundStyle(.secondary) }
        }
    }

    @ViewBuilder
    private var optionsBlocks: some View {
        if let options = model.workspace?.options, let rows = options.rows, !rows.isEmpty {
            if let last = options.lastTrade {
                Section { LabeledContent("Last trade", value: last) }
            }
            Section("Chain (near ATM)") {
                ForEach(rows.prefix(20)) { row in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(row.expiry ?? "—").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Text(row.strike.map { String(format: "%.1f", $0) } ?? "—")
                                .font(.subheadline.monospacedDigit().weight(.semibold))
                        }
                        HStack {
                            Text("C \(row.callLast ?? "—")")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.green)
                            Spacer()
                            Text("P \(row.putLast ?? "—")")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.red)
                        }
                    }
                }
            }
        } else {
            Section { Text(language.t("market.workspace_empty")).foregroundStyle(.secondary) }
        }
    }

    @ViewBuilder
    private var earningsBlocks: some View {
        if let earnings = model.workspace?.earnings {
            Section("Upcoming") {
                LabeledContent("Next", value: earnings.nextDate ?? "—")
            }
            if let past = earnings.past, !past.isEmpty {
                Section("Past") {
                    ForEach(past.prefix(8)) { row in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.period ?? row.reported ?? "—")
                                .font(.subheadline.weight(.semibold))
                            HStack {
                                Text("EPS \(row.eps.map { String(format: "%.2f", $0) } ?? "—")")
                                    .font(.caption.monospacedDigit())
                                Text("Est \(row.estimate.map { String(format: "%.2f", $0) } ?? "—")")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(row.surprisePct.map { String(format: "%+.1f%%", $0) } ?? "—")
                                    .font(.caption.monospacedDigit().weight(.semibold))
                                    .foregroundStyle(QuoteRow.tone(row.surprisePct))
                            }
                        }
                    }
                }
            }
        } else {
            Section { Text(language.t("market.workspace_empty")).foregroundStyle(.secondary) }
        }
    }

    private func formatCompact(_ value: Double) -> String {
        if abs(value) >= 1_000_000_000_000 { return String(format: "%.2fT", value / 1_000_000_000_000) }
        if abs(value) >= 1_000_000_000 { return String(format: "%.2fB", value / 1_000_000_000) }
        if abs(value) >= 1_000_000 { return String(format: "%.2fM", value / 1_000_000) }
        if abs(value) >= 1_000 { return String(format: "%.1fK", value / 1_000) }
        return String(format: "%.0f", value)
    }
}
