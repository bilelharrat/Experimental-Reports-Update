import SwiftUI

@MainActor
final class CompanyResearchViewModel: ObservableObject {
    let companyId: String

    @Published var company: CompanyDetail?
    @Published var reports: [ReportSummary] = []
    @Published var liveQuote: Quote?
    @Published var loading = false
    @Published var error: String?
    @Published var showGenerate = false
    @Published var studioBusy = false
    @Published var studioError: String?
    @Published var openedReportId: String?

    init(companyId: String, seed: CompanyDetail? = nil) {
        self.companyId = companyId
        let cached = seed ?? AppDataCache.shared.cachedCompany(id: companyId) ?? APIClient.shared.getCached("companies/\(companyId)")
        self.company = cached
        let cachedReps: [ReportSummary]? = AppDataCache.shared.cachedReports(for: companyId) ?? APIClient.shared.getCached("companies/\(companyId)/reports")
        self.reports = (cachedReps ?? []).sorted { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
        if let ticker = cached?.ticker, !ticker.isEmpty {
            self.liveQuote = AppDataCache.shared.cachedQuote(for: ticker) ?? QuoteCache.load()[ticker.uppercased()]?.asQuote
        }
        self.loading = cached == nil
    }

    func load() async {
        if company == nil {
            loading = true
        }
        error = nil
        defer { loading = false }
        do {
            async let companyTask: CompanyDetail = APIClient.shared.get("companies/\(companyId)")
            async let reportsTask: [ReportSummary] = APIClient.shared.get("companies/\(companyId)/reports")
            let (c, r) = try await (companyTask, reportsTask)
            company = c
            reports = r.sorted { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
            AppDataCache.shared.update(company: c)
            AppDataCache.shared.update(reports: reports, for: companyId)
            await loadQuote()
        } catch {
            if company == nil {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    func studioInvestigate() async {
        studioBusy = true
        studioError = nil
        defer { studioBusy = false }
        do {
            struct Body: Encodable {
                let companyId: String
                enum CodingKeys: String, CodingKey { case companyId = "company_id" }
            }
            let report: ReportDetail = try await APIClient.shared.post(
                "memos/studio/investigate", body: Body(companyId: companyId)
            )
            openedReportId = report.id
            await load()
        } catch {
            studioError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func studioGenerate(reportId: String) async {
        studioBusy = true
        studioError = nil
        defer { studioBusy = false }
        do {
            let report: ReportDetail = try await APIClient.shared.post(
                "memos/studio/\(reportId)/generate",
                query: []
            )
            openedReportId = report.id
            await load()
        } catch {
            studioError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func loadQuote() async {
        guard let ticker = company?.ticker, !ticker.isEmpty else {
            liveQuote = nil
            return
        }
        do {
            let res: QuotesResponse = try await APIClient.shared.get(
                "quotes",
                query: [URLQueryItem(name: "ticker", value: ticker)]
            )
            liveQuote = res.quotes[ticker.uppercased()]
        } catch {
            liveQuote = nil
        }
    }
}

struct CompanyResearchView: View {
    @StateObject private var model: CompanyResearchViewModel
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var askPersona: AskPersonaStore
    @EnvironmentObject private var session: SessionStore
    @State private var openedReport: ReportNav?
    @State private var showAsk = false

    init(companyId: String, seed: CompanyDetail? = nil) {
        _model = StateObject(wrappedValue: CompanyResearchViewModel(companyId: companyId, seed: seed))
    }

    var body: some View {
        List {
            if model.loading && model.company == nil {
                ProgressView(language.t("common.loading"))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else if let err = model.error, model.company == nil {
                ContentUnavailableView {
                    Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
                } description: {
                    Text(err)
                } actions: {
                    Button(language.t("common.retry")) { Task { await model.load() } }
                }
                .listRowSeparator(.hidden)
            } else if let company = model.company {
                overviewSection(company)
                marketSection(company)
                if company.isPublic {
                    TraderCardsSection(
                        companyId: company.id,
                        snapshot: company.traderSnapshot
                    ) {
                        Task { await model.load() }
                    }
                }
                reportsSection(company)
                studioSection(company)
                consoleSection(company)
                linksSection(company)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(model.company?.displayName(lang: language.language) ?? model.companyId)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                if model.company != nil {
                    HStack(spacing: 12) {
                        Button {
                            showAsk = true
                        } label: {
                            Label {
                                Text(askPersona.investor.inviteTitle(lang: language.language))
                            } icon: {
                                AskMark(size: 24)
                            }
                        }
                        Button {
                            model.showGenerate = true
                        } label: {
                            Label(language.t("research.generate"), systemImage: "doc.badge.plus")
                        }
                        .disabled(!session.canWriteDesk)
                        .opacity(session.canWriteDesk ? 1 : 0.4)
                    }
                }
            }
        }
        .refreshable { await model.load() }
        .task { await model.load() }
        .sheet(isPresented: $showAsk) {
            if let company = model.company {
                CopilotSheet(
                    companyId: company.id,
                    companyName: company.displayName(lang: language.language),
                    surface: "ios_company"
                )
            }
        }
        .sheet(isPresented: $model.showGenerate) {
            if let company = model.company {
                GenerateReportSheet(company: company) { report in
                    model.showGenerate = false
                    openedReport = ReportNav(id: report.id)
                    Task { await model.load() }
                }
            }
        }
        .navigationDestination(item: $openedReport) { nav in
            ReportDetailView(reportId: nav.id)
                .id(nav.id)
        }
        .onChange(of: model.openedReportId) { _, id in
            if let id {
                model.openedReportId = nil
                openedReport = ReportNav(id: id)
            }
        }
    }

    @ViewBuilder
    private func overviewSection(_ company: CompanyDetail) -> some View {
        Section {
            HStack(spacing: 12) {
                MonogramAvatar(
                    name: company.displayName(lang: language.language),
                    ticker: company.ticker,
                    companyId: company.id,
                    logoUrl: company.logoUrl,
                    logoDomain: company.logoDomain,
                    website: company.website,
                    size: 52
                )
                VStack(alignment: .leading, spacing: 3) {
                    Text(company.displayName(lang: language.language))
                        .font(.headline)
                        .lineLimit(2)
                    HStack(spacing: 6) {
                        if let ticker = company.ticker, !ticker.isEmpty {
                            Text(ticker)
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color(.systemGray5), in: Capsule())
                        }
                        Text(company.companyType ?? company.status ?? "—")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.vertical, 4)
            if let sector = company.sector {
                LabeledContent(language.t("company.sector"), value: sector)
            }
            if let industry = company.industry {
                LabeledContent(language.t("research.industry"), value: industry)
            }
            let desc = company.displayDescription(lang: language.language)
            if !desc.isEmpty {
                Text(desc)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        } footer: {
            if company.isPublic {
                Text(language.t("research.public_memo_note"))
            }
        }
    }

    @ViewBuilder
    private func marketSection(_ company: CompanyDetail) -> some View {
        if let quote = model.liveQuote {
            Section(language.t("market.title")) {
                NavigationLink {
                    QuoteDetailView(ticker: quote.ticker)
                } label: {
                    QuoteRow(quote: quote)
                }
            }
        } else if let ticker = company.ticker, !ticker.isEmpty {
            Section(language.t("market.title")) {
                NavigationLink {
                    QuoteDetailView(ticker: ticker)
                } label: {
                    Label(language.t("market.open_quote"), systemImage: "chart.xyaxis.line")
                }
            }
        }
    }

    @ViewBuilder
    private func reportsSection(_ company: CompanyDetail) -> some View {
        Section {
            Button {
                model.showGenerate = true
            } label: {
                Label(language.t("research.generate"), systemImage: "doc.badge.plus")
            }
            if model.reports.isEmpty {
                Text(language.t("research.no_reports"))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(model.reports) { report in
                    NavigationLink(value: ReportNav(id: report.id)) {
                        reportRow(report)
                    }
                }
            }
        } header: {
            Text(language.t("research.reports"))
        }
    }

    private func reportRow(_ report: ReportSummary) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(report.reportType ?? language.t("research.report"))
                    .font(.body.weight(.medium))
                HStack(spacing: 8) {
                    if let progress = report.progress, report.isRunning {
                        Text("\(progress)%")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    if let audience = report.audience {
                        Text(audience)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                if let err = report.error, !(report.status ?? "").hasPrefix("complete") {
                    Text(err)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 6)
            StatusPill(text: report.statusLabel, color: statusColor(report))
        }
        .padding(.vertical, 2)
    }

    private func statusColor(_ report: ReportSummary) -> Color {
        let s = (report.status ?? "").lowercased()
        if s.hasPrefix("complete") { return .green }
        if s.hasPrefix("failed") || s == "cancelled" { return .red }
        if report.isRunning { return .orange }
        return .secondary
    }

    @ViewBuilder
    private func studioSection(_ company: CompanyDetail) -> some View {
        // Memo Studio lite: kick a deep investigation; full card review stays web.
        let awaiting = model.reports.first { ($0.status ?? "") == "awaiting_studio" }
        Section {
            if let awaiting {
                Button {
                    Task { await model.studioGenerate(reportId: awaiting.id) }
                } label: {
                    Label(language.t("studio.generate"), systemImage: "wand.and.stars")
                }
                .disabled(model.studioBusy)
                Text(language.t("studio.awaiting_hint"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Button {
                    Task { await model.studioInvestigate() }
                } label: {
                    Label(
                        model.studioBusy ? language.t("common.loading") : language.t("studio.investigate"),
                        systemImage: "sparkle.magnifyingglass"
                    )
                }
                .disabled(model.studioBusy)
            }
            if let err = model.studioError {
                Text(err).font(.caption).foregroundStyle(.red)
            }
        } header: {
            Text(language.t("studio.title"))
        } footer: {
            Text(language.t("studio.footer"))
        }
    }

    @ViewBuilder
    private func consoleSection(_ company: CompanyDetail) -> some View {
        Section {
            Button {
                showAsk = true
            } label: {
                CopilotInviteCard()
            }
            .buttonStyle(.borderless)
            NavigationLink {
                ConsoleSessionsView(companyId: company.id)
            } label: {
                Label(language.t("copilot.open_console"), systemImage: "bubble.left.and.text.bubble.right")
            }
        } header: {
            Text(askPersona.investor.inviteTitle(lang: language.language))
        } footer: {
            Text(language.t("copilot.footer"))
        }
    }

    @ViewBuilder
    private func linksSection(_ company: CompanyDetail) -> some View {
        Section {
            Link(language.t("company.open_web"), destination: AppConfig.baseURL.appendingPathComponent(company.id))
        }
    }
}

/// Back-compat wrapper used by older call sites that still pass a ``Company``.
struct CompanyDetailView: View {
    let company: Company

    var body: some View {
        CompanyResearchView(companyId: company.id)
    }
}
