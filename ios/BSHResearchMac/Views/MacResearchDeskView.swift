import SwiftUI

struct MacResearchDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var searchText = ""
    @State private var selectedSector: String = "All"
    @State private var showOnlyModified: Bool = false

    private var sectors: [String] {
        let set = Set(store.companies.compactMap { $0.sector }.filter { !$0.isEmpty })
        return ["All"] + Array(set).sorted()
    }

    private var filteredCompanies: [MacCompany] {
        store.companies.filter { company in
            if showOnlyModified && !store.isCompanyModified(company.id) {
                return false
            }
            let matchesSearch = searchText.isEmpty
                || (company.name ?? "").localizedCaseInsensitiveContains(searchText)
                || (company.ticker ?? "").localizedCaseInsensitiveContains(searchText)
                || company.id.localizedCaseInsensitiveContains(searchText)

            let matchesSector = selectedSector == "All" || company.sector == selectedSector
            return matchesSearch && matchesSector
        }
    }

    var body: some View {
        HSplitView {
            directoryPane
                .frame(minWidth: 230, idealWidth: 270, maxWidth: 380)
                .layoutPriority(0)

            detailPane
                .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)
        }
        .searchable(text: $searchText, placement: .toolbar, prompt: "Search companies or tickers…")
    }

    private var directoryPane: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Picker("Sector", selection: $selectedSector) {
                    ForEach(sectors, id: \.self) { s in
                        Text(s).tag(s)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .controlSize(.small)

                Spacer()

                Button {
                    showOnlyModified.toggle()
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: showOnlyModified ? "sparkle" : "sparkles")
                        Text("Diffs")
                    }
                    .font(.caption2.weight(.medium))
                }
                .buttonStyle(.bordered)
                .tint(showOnlyModified ? .accentColor : .secondary)
                .controlSize(.mini)
                .help("Show only companies with updates or new memos since last visit")

                Text("\(filteredCompanies.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .dsToolbarStrip()

            Divider()

            List(selection: $store.selectedCompany) {
                ForEach(filteredCompanies) { company in
                    CompanyListRow(company: company)
                        .tag(company)
                        .listRowSeparator(.hidden)
                        .glassListRow(isSelected: store.selectedCompany?.id == company.id)
                }
            }
            .listStyle(.inset)
            .onChange(of: store.selectedCompany) { _, newComp in
                if let newComp {
                    store.markCompanyVisited(newComp.id)
                }
            }

            Divider()
            MacPitchDeckDropBanner()
        }
    }

    @ViewBuilder
    private var detailPane: some View {
        if let company = store.selectedCompany {
            CompanyDossierView(company: company, onNewReport: {
                store.requestNewReport(for: company)
            })
        } else {
            ContentUnavailableView(
                "No Company Selected",
                systemImage: "building.2",
                description: Text("Select an enterprise from the directory to review research dossiers and investment memos.")
            )
        }
    }
}

// MARK: - Company List Row

struct CompanyListRow: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    private var initials: String {
        if let ticker = company.ticker, !ticker.isEmpty {
            return String(ticker.prefix(2)).uppercased()
        }
        return String(company.id.prefix(2)).uppercased()
    }

    private var secondaryLine: String {
        var parts: [String] = []
        if let t = company.ticker, !t.isEmpty { parts.append(t.uppercased()) }
        if let s = company.sector, !s.isEmpty { parts.append(s) }
        else if let i = company.industry, !i.isEmpty { parts.append(i) }
        if let status = company.status?.lowercased(), !status.isEmpty, status != "public", status != "private" {
            parts.append(status.capitalized)
        }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 10) {
            MacMonogram(name: company.name ?? company.id, size: 30)
                .overlay(alignment: .topTrailing) {
                    if store.isCompanyModified(company.id) {
                        Circle().fill(Color.accentColor).frame(width: 8, height: 8)
                            .overlay(Circle().stroke(Color.dsCard, lineWidth: 1.5))
                            .offset(x: 3, y: -3)
                    }
                }

            VStack(alignment: .leading, spacing: 2) {
                Text(company.name ?? company.id)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(secondaryLine.isEmpty ? " " : secondaryLine)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            if let status = company.status?.lowercased(), status == "private" {
                MacDot(color: .purple).help("Private company")
            }
        }
        .padding(.vertical, 3)
    }

    private func colorForString(_ s: String) -> Color {
        let hash = abs(s.hashValue)
        let colors: [Color] = [.blue, .indigo, .purple, .teal, .cyan, .orange, .mint]
        return colors[hash % colors.count]
    }
}

enum DossierSection: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case ic = "Decisions"
    case team = "Team"
    case pipeline = "Pipeline"
    case capTable = "Cap table"
    case comps = "Comps"
    case ratios = "Ratios"
    case memos = "Memos"
    case all = "All"

    var id: String { rawValue }
    var icon: String {
        switch self {
        case .overview: return "rectangle.3.group"
        case .all: return "square.grid.2x2.fill"
        case .ic: return "checkmark.seal.fill"
        case .team: return "person.3.fill"
        case .pipeline: return "point.topleft.down.to.point.bottomright.curvepath"
        case .capTable: return "chart.pie.fill"
        case .comps: return "chart.bar.xaxis"
        case .ratios: return "gauge.with.dots.needle.bottom.50percent"
        case .memos: return "doc.text.fill"
        }
    }
}

// MARK: - Company Dossier Detail View

struct CompanyDossierView: View {
    let company: MacCompany
    var onNewReport: () -> Void

    @EnvironmentObject private var store: MacAppStore
    @State private var activeSection: DossierSection = DossierSection(rawValue: UserDefaults.standard.string(forKey: "bsh.launchDossierSection") ?? "") ?? .overview

    private var headerLine: String {
        var parts: [String] = []
        if let t = company.ticker, !t.isEmpty { parts.append(t.uppercased()) }
        if let s = company.sector, !s.isEmpty { parts.append(s) } else if let i = company.industry, !i.isEmpty { parts.append(i) }
        if let status = company.status, !status.isEmpty { parts.append(status.capitalized) }
        return parts.joined(separator: " · ")
    }

    private func shows(_ sections: DossierSection...) -> Bool {
        activeSection == .all || sections.contains(activeSection)
    }

    private var companyReports: [MacReport] {
        store.reports(for: company.id)
    }

    private var runningReports: [MacReport] {
        companyReports.filter { !$0.isComplete && !$0.isFailed }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                HStack(alignment: .center, spacing: 14) {
                    MacMonogram(name: company.name ?? company.id, size: 48)
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 10) {
                            Text(company.name ?? company.id)
                                .font(.dsTitle)
                                .lineLimit(1)
                            if let stage = store.dealPipelines[company.id]?.stage {
                                MacStatusPill(text: stage, color: .accentColor)
                            }
                            if store.isFollowed(company.id) {
                                Image(systemName: "star.fill").font(.caption).foregroundStyle(Color.yellow).help("Followed on the Pipeline board")
                            }
                        }
                        Text(headerLine.isEmpty ? company.subtitle : headerLine)
                            .font(.dsBody)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 12)

                    HStack(spacing: 8) {
                        Button {
                            onNewReport()
                        } label: {
                            Label("New Memo", systemImage: "plus")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!store.canRunTasks)
                        .help(store.canRunTasks ? "Generate an investment memo (⌘N)" : "Sign in with an analyst or partner role to run memos")

                        Button {
                            store.requestDecision(for: company)
                        } label: {
                            Label("Decision", systemImage: "checkmark.seal")
                        }
                        .disabled(!store.canRunTasks)
                        .help("Record Invest / Pass / Watch (⌘D)")

                        if let report = companyReports.first(where: \.canOpen) {
                            Button {
                                store.openICReview(report: report)
                            } label: {
                                Label("IC Review", systemImage: "rectangle.split.2x1")
                            }
                            .help("Memo beside thesis, risks, evidence and the decision form (⌘⇧O)")
                        }

                        Menu {
                            Button {
                                Task { await store.toggleFollow(company.id) }
                            } label: {
                                Label(store.isFollowed(company.id) ? "Unfollow" : "Follow on Pipeline", systemImage: store.isFollowed(company.id) ? "star.slash" : "star")
                            }
                            .disabled(!store.canRunTasks)
                            Button {
                                withAnimation { store.openInEmbeddedBrowser(MacConfig.webCompanyURL(id: company.id)) }
                            } label: {
                                Label("Open in Research Browser", systemImage: "globe")
                            }
                            Button {
                                MacConfig.openInBrowser(MacConfig.webCompanyURL(id: company.id))
                            } label: {
                                Label("Open on Web", systemImage: "safari")
                            }
                            Divider()
                            Button {
                                store.askWarren("Give me the one-paragraph state of play for \(company.title).", context: MacCopilotContext(surface: "research", tab: "memo"), company: company)
                            } label: {
                                Label("Ask Warren", systemImage: "bubble.left.and.bubble.right")
                            }
                            .disabled(!store.canRunTasks)
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                        .menuIndicator(.hidden)
                        .fixedSize()
                    }
                }
                .padding(.bottom, 4)

                MacTabBar(items: DossierSection.allCases.map { ($0, $0.rawValue) }, selection: $activeSection)

                // Overview: the one object, its score, the record and the memos
                if shows(.overview) {
                    MacUnifiedProfileView(companyId: company.id)
                    MacSignalScoreView(companyId: company.id)
                }

                if shows(.pipeline, .overview) {
                    MacDealPipelineView(company: company)
                }

                if shows(.comps) {
                    MacCompsRailView(company: company).id(company.id)
                }

                if shows(.capTable) {
                    MacCapTableSimulatorView(company: company).id(company.id)
                }

                if shows(.team) {
                    MacFounderRadarView(company: company)
                }

                if shows(.ratios) {
                    MacVCRatiosBlotterView(company: company).id(company.id)
                }

                // Active Pipeline Monitor (if any runs in progress)
                if shows(.memos, .overview) && !runningReports.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Active Analysis Pipelines", systemImage: "gearshape.arrow.triangle.2.circlepath")
                            .font(.headline)
                        ForEach(runningReports) { rep in
                            HStack {
                                ProgressView()
                                    .controlSize(.small)
                                Text(rep.displayTitle)
                                    .font(.subheadline.weight(.medium))
                                Spacer()
                                Text(rep.stage ?? "Processing…")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                        }
                    }
                    .padding()
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
                }

                // Investment Memos & Research Reports Table
                if shows(.memos, .overview) {
                    VStack(alignment: .leading, spacing: 12) {
                        MacCardHeader("Memos", subtitle: companyReports.isEmpty ? nil : "\(companyReports.count) on file", systemImage: "doc.text")

                        if companyReports.isEmpty {
                            Text("No memo yet. New Memo runs the research pipeline for this company.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .padding(.vertical, 24)
                                .frame(maxWidth: .infinity, alignment: .center)
                        } else {
                            VStack(spacing: 8) {
                                ForEach(companyReports) { report in
                                    MemoRowView(report: report)
                                }
                            }
                        }
                    }
                    .padding()
                    .appleGlassCard(cornerRadius: 16)
                }

                // Decisions: the firm's record, readiness gates, IC room and thesis vs evidence
                if shows(.ic, .overview) {
                    VStack(alignment: .leading, spacing: 12) {
                        MacCardHeader("Decision record", subtitle: store.stage(for: company.id).rawValue, systemImage: "checkmark.seal")
                        MacDecisionTimeline(companyId: company.id)
                    }
                    .padding()
                    .appleGlassCard()
                }

                if shows(.ic) {
                    MacICPrepView(company: company)
                    MacICRoomView(companyId: company.id, reportId: nil)
                        .id(company.id)
                    MacNumberLintView(companyId: company.id)
                    MacThesisTrackerView(company: company)
                    MacCommentsView(companyId: company.id, target: MacCommentTarget(kind: "company", ref: company.id, label: company.title))
                        .id(company.id)
                }
            }
            .dsPage()
        }
        .embeddedInAmbientGlass()
    }
}

// MARK: - KPI Card

private struct KPICard: View {
    let title: String
    let value: String
    let subtext: String
    let isGood: Bool?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 17, weight: .bold).monospacedDigit())
                .monospacedDigit()
                .foregroundStyle(isGood == false ? Color.red : (isGood == true ? Color.green : Color.primary))
            Text(subtext)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .appleGlassTile(cornerRadius: 10)
    }
}

// MARK: - Memo Row View

struct MemoRowView: View {
    let report: MacReport
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: report.isComplete ? "doc.text.fill" : "doc.badge.gearshape")
                .font(.title3)
                .foregroundStyle(report.isComplete ? Color.blue : Color.orange)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(report.displayTitle)
                        .font(.body.weight(.semibold))

                    if store.isReportNew(report) {
                        Text("NEW")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1.5)
                            .background(Color.accentColor, in: Capsule())
                    }

                    if let lang = report.language {
                        Text(lang.uppercased())
                            .font(.caption2.monospacedDigit())
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                    }

                    StatusTag(status: report.statusTone)
                }

                Text("Updated \(report.dateLabel) · \(report.audience ?? "Internal")")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if report.canOpen {
                Button {
                    store.openReportWindow(report)
                } label: {
                    Label("Read Memo", systemImage: "book.pages")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .help("Open in its own memo window")
            } else if !report.isComplete && !report.isFailed {
                Button {
                    store.showBlotter = true
                    store.blotterTab = .jobs
                    store.selectedJobId = report.id
                } label: {
                    Label("Follow run", systemImage: "waveform.path.ecg")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help("Follow this run in the Jobs blotter")
            }

            Button {
                let url: URL
                if let cid = report.companyId {
                    url = MacConfig.webCompanyMemoURL(companyId: cid, reportId: report.id)
                } else {
                    url = MacConfig.webReportURL(id: report.id)
                }
                MacConfig.openInBrowser(url)
            } label: {
                Image(systemName: "safari")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Open memo on Web")
        }
        .padding(10)
        .appleGlassTile(cornerRadius: 10)
        .onDrag {
            NSItemProvider(object: ((report.companyName ?? "Memo") + " - " + report.displayTitle) as NSString)
        }
    }
}

// MARK: - Status Tag

struct StatusTag: View {
    let status: String

    var color: Color {
        switch status.lowercased() {
        case "complete": return .green
        case "failed": return .red
        default: return .orange
        }
    }

    var body: some View {
        Text(status)
            .font(.caption2.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 2.5)
            .appleGlassPill(color: color)
    }
}

// MARK: - Generate Report Sheet

struct MacGenerateReportSheet: View {
    let company: MacCompany
    var onCreated: (MacReport) -> Void

    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    // Defaults mirror server REPORT_TYPES / AUDIENCES; replaced by GET /api/options on appear.
    @State private var availableTypes = [
        "Investment Report (Auto)",
        "Investment Memo (Late-Stage)",
        "Buffett Investment Memo",
        "Background",
        "Financial Analysis",
        "Market Analysis",
    ]
    @State private var availableAudiences = ["LP", "Assistant", "Partner", "Internal"]
    @State private var availableLanguages: [(code: String, label: String)] = [("en", "English"), ("zh", "中文")]
    @State private var reportType = "Investment Report (Auto)"
    @State private var audience = "Internal"
    @State private var language = "en"
    @State private var submitting = false
    @State private var loadingOptions = true
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Generate Research Memo")
                    .font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            .background(.ultraThinMaterial)

            Divider()

            Form {
                Section {
                    LabeledContent("Target Enterprise") {
                        Text(company.name ?? company.id)
                            .font(.body.weight(.semibold))
                    }
                    if let ticker = company.ticker {
                        LabeledContent("Ticker") {
                            Text(ticker).font(.body.monospacedDigit())
                        }
                    }
                }

                Section("Memo Parameters") {
                    Picker("Report Type", selection: $reportType) {
                        ForEach(availableTypes, id: \.self) { type in
                            Text(type).tag(type)
                        }
                    }
                    .disabled(loadingOptions)

                    Picker("Audience", selection: $audience) {
                        ForEach(availableAudiences, id: \.self) { item in
                            Text(item).tag(item)
                        }
                    }
                    .disabled(loadingOptions)

                    Picker("Language", selection: $language) {
                        ForEach(availableLanguages, id: \.code) { item in
                            Text(item.label).tag(item.code)
                        }
                    }
                }

                if let error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            .formStyle(.grouped)
            .padding()

            Divider()

            HStack {
                Spacer()
                Button(submitting ? "Starting…" : "Start Pipeline") {
                    Task { await submit() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(submitting || loadingOptions || !store.canRunTasks)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 480, height: 420)
        .task { await loadOptions() }
    }

    /// The server rejects report types it doesn't know — always offer its own list.
    private func loadOptions() async {
        defer { loadingOptions = false }
        guard let options = try? await MacAPIClient.shared.fetchReportOptions() else { return }
        if !options.reportTypes.isEmpty {
            availableTypes = options.reportTypes
            if !availableTypes.contains(reportType) { reportType = availableTypes[0] }
        }
        if !options.audiences.isEmpty {
            availableAudiences = options.audiences
            if !availableAudiences.contains(audience) {
                audience = availableAudiences.contains("Internal") ? "Internal" : availableAudiences[0]
            }
        }
        if !options.languages.isEmpty {
            availableLanguages = options.languages.map { ($0.code, $0.label ?? $0.code.uppercased()) }
            if !availableLanguages.contains(where: { $0.code == language }) { language = availableLanguages[0].code }
        }
    }

    private func submit() async {
        submitting = true
        error = nil
        defer { submitting = false }
        do {
            let rep = try await MacAPIClient.shared.createReport(
                companyId: company.id,
                reportType: reportType,
                audience: audience,
                language: language
            )
            onCreated(rep)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
