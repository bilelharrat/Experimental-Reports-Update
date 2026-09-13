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
    @Published var showAsk = false
    @Published var resolvingAsk = false
    @Published var askError: String?
    @Published private(set) var resolvedCompanyId: String?
    @Published private(set) var resolvedCompanyName: String?

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

    /// Resolve a research-company id for Co-Pilot (workspace coverage or create via select).
    func openAsk() async {
        askError = nil
        if resolvedCompanyId != nil {
            showAsk = true
            return
        }
        resolvingAsk = true
        defer { resolvingAsk = false }
        do {
            struct CompanyRef: Decodable {
                let id: String
                let name: String?
                let ticker: String?
            }
            if let companies: [CompanyRef] = try? await APIClient.shared.get("companies"),
               let match = companies.first(where: { ($0.ticker ?? "").uppercased() == ticker }) {
                resolvedCompanyId = match.id
                resolvedCompanyName = match.name ?? chart?.name ?? workspace?.profile?.name
                showAsk = true
                return
            }

            let hits: [AutocompleteHit] = (try? await APIClient.shared.get(
                "companies/autocomplete",
                query: [
                    URLQueryItem(name: "q", value: ticker),
                    URLQueryItem(name: "limit", value: "8"),
                ]
            )) ?? []
            let exact = hits.filter { ($0.ticker ?? "").uppercased() == ticker }
            if let local = exact.first(where: { $0.hasLocalId }), let id = local.companyId {
                resolvedCompanyId = id
                resolvedCompanyName = local.name ?? chart?.name ?? workspace?.profile?.name
                showAsk = true
                return
            }

            let seed = exact.first ?? hits.first
            let body = SelectCompanyBody(
                name: seed?.name
                    ?? chart?.name
                    ?? workspace?.profile?.name
                    ?? ticker,
                ticker: ticker,
                description: seed?.description ?? workspace?.profile?.description,
                sector: seed?.sector ?? workspace?.profile?.sector,
                industry: seed?.industry ?? workspace?.profile?.industry,
                exchange: seed?.exchange ?? chart?.exchange ?? workspace?.summary?.exchange,
                status: seed?.status,
                companyType: seed?.companyType
            )
            let company: CompanyDetail = try await APIClient.shared.post("companies/select", body: body)
            resolvedCompanyId = company.id
            resolvedCompanyName = company.name ?? company.id
            showAsk = true
        } catch {
            askError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct QuoteDetailView: View {
    @StateObject private var model: QuoteDetailViewModel
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var desk: DeskStore
    @EnvironmentObject private var askPersona: AskPersonaStore

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
            askInviteSection
            tabPickerSection
            workspaceSections
                .id(model.tab)
        }
        .listStyle(.insetGrouped)
        .navigationTitle(model.ticker)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await model.openAsk() }
                } label: {
                    if model.resolvingAsk {
                        ProgressView()
                    } else {
                        AskMark(size: 28)
                    }
                }
                .disabled(model.resolvingAsk)
                .accessibilityLabel(askPersona.investor.inviteTitle(lang: language.language))
            }
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
        .sheet(isPresented: $model.showAsk) {
            if let companyId = model.resolvedCompanyId {
                CopilotSheet(
                    companyId: companyId,
                    companyName: model.resolvedCompanyName
                        ?? model.chart?.name
                        ?? model.workspace?.profile?.name
                        ?? model.ticker,
                    surface: "ios_market"
                )
            }
        }
        .alert(
            language.t("common.error"),
            isPresented: Binding(
                get: { model.askError != nil },
                set: { if !$0 { model.askError = nil } }
            )
        ) {
            Button(language.t("common.done"), role: .cancel) { model.askError = nil }
        } message: {
            Text(model.askError ?? "")
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 2) {
                Text(model.chart?.name ?? model.workspace?.profile?.name ?? model.ticker)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Text(QuoteRow.price(model.chart?.lastPrice, currency: model.chart?.currency))
                    .font(.system(size: 38, weight: .semibold, design: .default).monospacedDigit())
                    .contentTransition(.numericText())
                HStack(spacing: 6) {
                    Image(systemName: (model.chart?.changePct1d ?? 0) >= 0 ? "arrowtriangle.up.fill" : "arrowtriangle.down.fill")
                        .font(.caption2)
                    Text(changeLine)
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                }
                .foregroundStyle(QuoteRow.tone(model.chart?.changePct1d))
                HStack(spacing: 6) {
                    if let exchange = model.chart?.exchange ?? model.workspace?.summary?.exchange {
                        Text(exchange)
                    }
                    if let asOf = formattedAsOf {
                        Text(asOf)
                    }
                }
                .font(.caption)
                .foregroundStyle(.tertiary)
                if let err = model.error {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }
            .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 2, trailing: 4))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
        }
    }

    private var askInviteSection: some View {
        Section {
            Button {
                Task { await model.openAsk() }
            } label: {
                CopilotInviteCard()
            }
            .buttonStyle(.borderless)
            .disabled(model.resolvingAsk)
            .opacity(model.resolvingAsk ? 0.6 : 1)
            if let err = model.askError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private var changeLine: String {
        let pct = model.chart?.changePct1d
        if let change = model.chart?.change, let pct {
            return String(format: "%+.2f (%+.2f%%)", change, pct)
        }
        return QuoteRow.pct(pct)
    }

    /// "2026-09-09T19:59:00Z" → "Sep 9, 12:59 PM" in the user's zone.
    private var formattedAsOf: String? {
        guard let raw = model.chart?.asOf else { return nil }
        let iso = ISO8601DateFormatter()
        guard let date = iso.date(from: raw) ?? {
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return iso.date(from: raw)
        }() else { return raw }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    // MARK: - Range + chart

    private var rangeSection: some View {
        Section {
            HStack(spacing: 4) {
                ForEach(ChartRange.allCases) { span in
                    Button {
                        UISelectionFeedbackGenerator().selectionChanged()
                        withAnimation(.snappy(duration: 0.2)) { model.range = span }
                    } label: {
                        Text(span.label)
                            .font(.footnote.weight(model.range == span ? .semibold : .medium))
                            .foregroundStyle(model.range == span ? Color.primary : Color.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background {
                                if model.range == span {
                                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                                        .fill(Color(.systemGray5))
                                }
                            }
                    }
                    .buttonStyle(.plain)
                }
            }
            .listRowInsets(EdgeInsets(top: 2, leading: 4, bottom: 2, trailing: 4))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
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
                .opacity(model.chartLoading ? 0.4 : 1)
                if model.chartLoading {
                    ProgressView()
                }
            }
            .animation(.easeInOut(duration: 0.15), value: model.chartLoading)
            .listRowInsets(EdgeInsets(top: 0, leading: 4, bottom: 8, trailing: 4))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
        }
    }

    // MARK: - Stats

    private var statsSection: some View {
        Section(language.t("market.stats")) {
            let stats = collectStats()
            LazyVGrid(
                columns: [GridItem(.flexible(), spacing: 24), GridItem(.flexible())],
                alignment: .leading,
                spacing: 0
            ) {
                ForEach(stats, id: \.0) { stat in
                    VStack(spacing: 0) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(stat.0)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            Spacer(minLength: 8)
                            Text(stat.1)
                                .font(.footnote.monospacedDigit().weight(.semibold))
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                        }
                        .padding(.vertical, 8)
                        Divider()
                    }
                }
            }
            .listRowSeparator(.hidden)
        }
    }

    private func collectStats() -> [(String, String)] {
        let chart = model.chart
        let summary = model.workspace?.summary
        var stats: [(String, String)] = []
        func add(_ label: String, _ value: String?) {
            if let value, !value.isEmpty, value != "—" { stats.append((label, value)) }
        }
        add("Open", QuoteRow.price(chart?.open, currency: chart?.currency))
        add("High", QuoteRow.price(chart?.high, currency: chart?.currency))
        add("Low", QuoteRow.price(chart?.low, currency: chart?.currency))
        add("Prev close", chart?.previousClose.map { QuoteRow.price($0, currency: chart?.currency) } ?? summary?.previousClose)
        if let cap = summary?.marketCap { add("Mkt cap", cap) }
        else if let cap = chart?.marketCap { add("Mkt cap", formatCompact(cap)) }
        if let vol = chart?.volume { add("Volume", formatCompact(vol)) }
        else { add("Volume", summary?.volume) }
        if let avg = chart?.avgVolume { add("Avg vol", formatCompact(avg)) }
        else { add("Avg vol", summary?.avgVolume) }
        if let week = summary?.fiftyTwoWeek { add("52W range", week) }
        else {
            let hi = QuoteRow.price(chart?.fiftyTwoWeekHigh, currency: chart?.currency)
            let lo = QuoteRow.price(chart?.fiftyTwoWeekLow, currency: chart?.currency)
            if hi != "—" || lo != "—" { add("52W range", "\(lo)–\(hi)") }
        }
        if let pe = chart?.peRatio { add("P/E", String(format: "%.1f", pe)) }
        if let eps = chart?.eps { add("EPS", String(format: "%.2f", eps)) }
        if let beta = chart?.beta { add("Beta", String(format: "%.2f", beta)) }
        add("Dividend", summary?.dividend)
        if let yld = summary?.yield { add("Yield", yld) }
        else if let dy = chart?.dividendYield { add("Yield", String(format: "%.2f%%", dy * (dy < 1 ? 100 : 1))) }
        add("Ex-dividend", summary?.exDividend)
        add("Div pay", summary?.dividendPay)
        if let target = summary?.oneYearTarget { add("1Y target", target) }
        else if let target = model.workspace?.analysis?.target {
            add("1Y target", String(format: "%.2f", target))
        }
        return stats
    }

    // MARK: - Workspace tabs

    private var tabPickerSection: some View {
        Section {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(QuoteDetailViewModel.WorkspaceTab.allCases) { tab in
                        Button {
                            UISelectionFeedbackGenerator().selectionChanged()
                            withAnimation(.snappy(duration: 0.2)) { model.tab = tab }
                        } label: {
                            Text(tab.label)
                                .font(.subheadline.weight(model.tab == tab ? .semibold : .regular))
                                .foregroundStyle(model.tab == tab ? Color(.systemBackground) : .primary)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 7)
                                .background(
                                    model.tab == tab ? Color.primary : Color(.systemGray5),
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 2)
            }
            .listRowInsets(EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)

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
