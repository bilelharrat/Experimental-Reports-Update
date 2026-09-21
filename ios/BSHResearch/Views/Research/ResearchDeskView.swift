import SwiftUI

public enum DossierSection: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case memos = "Memo Studio"
    case ic = "Decisions"
    case team = "Team"
    case pipeline = "Pipeline"
    case capTable = "Cap table"
    case comps = "Comps"
    case ratios = "Ratios"
    case all = "All"

    public var id: String { rawValue }
    public var icon: String {
        switch self {
        case .overview: return "rectangle.3.group"
        case .all: return "square.grid.2x2.fill"
        case .ic: return "checkmark.seal.fill"
        case .team: return "person.3.fill"
        case .pipeline: return "point.topleft.down.to.point.bottomright.curvepath"
        case .capTable: return "chart.pie.fill"
        case .comps: return "chart.bar.xaxis"
        case .ratios: return "gauge.with.dots.needle.bottom.50percent"
        case .memos: return "sparkles"
        }
    }
}

public struct MacResearchDeskView: View {
    @StateObject private var store = ResearchDeskStore.shared
    @State private var searchText = ""
    @State private var selectedSector: String = "All"
    @State private var showOnlyModified: Bool = false
    @State private var reportCompany: MacCompany?
    @State private var decisionCompany: MacCompany?

    public init() {}

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

    public var body: some View {
        NavigationSplitView {
            directoryPane
                .navigationTitle("Research Desk")
                .navigationBarTitleDisplayMode(.inline)
        } detail: {
            detailPane
        }
        .environmentObject(store)
        .sheet(item: $reportCompany) { company in
            ResearchReportCustomizerSheet(company: company) { _ in
                Task { await store.fetchReports(for: company.id) }
            }
            .environmentObject(store)
        }
        .sheet(item: $decisionCompany) { company in
            MacDecisionSheet(company: company)
                .environmentObject(store)
        }
        .sheet(isPresented: Binding(
            get: { store.intakeDeckURL != nil },
            set: { if !$0 { store.intakeDeckURL = nil } }
        )) {
            MacPitchDeckIntakeSheet(fileURL: store.intakeDeckURL)
                .environmentObject(store)
        }
        .task {
            if store.companies.isEmpty {
                await store.loadAll()
            }
        }
        .onChange(of: store.companies) { _, newComps in
            if store.selectedCompany == nil, let first = store.defaultCompany(in: newComps) {
                store.selectedCompany = first
            }
        }
    }

    // MARK: - Directory Pane
    private var directoryPane: some View {
        VStack(spacing: 0) {
            // Sector filter & Diffs strip
            HStack(spacing: 8) {
                Menu {
                    ForEach(sectors, id: \.self) { s in
                        Button(s) { selectedSector = s }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(selectedSector)
                            .font(.caption.weight(.medium))
                            .lineLimit(1)
                        Image(systemName: "chevron.down").font(.system(size: 10))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .appleGlassTile(cornerRadius: 6)
                }

                Spacer()

                Button {
                    showOnlyModified.toggle()
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: showOnlyModified ? "sparkle" : "sparkles")
                        Text("Diffs")
                    }
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(showOnlyModified ? Color.accentColor.opacity(0.18) : Color.clear, in: Capsule())
                    .overlay(Capsule().strokeBorder(showOnlyModified ? Color.accentColor : Color.secondary.opacity(0.3), lineWidth: 1))
                }

                Text("\(filteredCompanies.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color.dsCard.opacity(0.5))

            Divider()

            List(filteredCompanies, selection: $store.selectedCompany) { company in
                NavigationLink(value: company) {
                    CompanyListRow(company: company)
                }
                .tag(company)
            }
            .listStyle(.plain)
            .searchable(text: $searchText, prompt: "Search companies or tickers…")
            .navigationDestination(for: MacCompany.self) { comp in
                CompanyDossierView(
                    company: comp,
                    onNewReport: { reportCompany = comp },
                    onDecision: { decisionCompany = comp }
                )
            }
            .refreshable {
                await store.loadAll()
            }

            Divider()
            MacPitchDeckDropBanner()
        }
    }

    // MARK: - Detail Pane
    @ViewBuilder
    private var detailPane: some View {
        if let company = store.selectedCompany {
            CompanyDossierView(
                company: company,
                onNewReport: { reportCompany = company },
                onDecision: { decisionCompany = company }
            )
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
public struct CompanyListRow: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore

    public init(company: MacCompany) {
        self.company = company
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

    public var body: some View {
        HStack(spacing: 10) {
            MacMonogram(company: company, size: 36)
                .overlay(alignment: .topTrailing) {
                    if store.isCompanyModified(company.id) {
                        Circle().fill(Color.accentColor).frame(width: 8, height: 8)
                            .overlay(Circle().stroke(Color.dsCard, lineWidth: 1.5))
                            .offset(x: 3, y: -3)
                    }
                }

            VStack(alignment: .leading, spacing: 2) {
                Text(company.name ?? company.id)
                    .font(.system(size: 14, weight: .medium))
                    .lineLimit(1)
                Text(secondaryLine.isEmpty ? " " : secondaryLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            if let status = company.status?.lowercased(), status == "private" {
                MacDot(.purple)
            }
        }
        .padding(.vertical, 3)
    }
}

// MARK: - Company Dossier View
public struct CompanyDossierView: View {
    public let company: MacCompany
    public var onNewReport: () -> Void
    public var onDecision: () -> Void

    @EnvironmentObject private var store: ResearchDeskStore
    @State private var activeSection: DossierSection = .overview

    public init(company: MacCompany, onNewReport: @escaping () -> Void, onDecision: @escaping () -> Void) {
        self.company = company
        self.onNewReport = onNewReport
        self.onDecision = onDecision
    }

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

    /// Listed on an exchange — a ticker or a public status, unless the record
    /// says private — the same rule as the server, the web and the Mac. A
    /// listed name's Overview leads with earnings and filings; its deal
    /// pipeline stays one tab away for anyone tracking it as a deal.
    private var isListed: Bool {
        let status = (company.status ?? "").lowercased()
        if status == "private" { return false }
        return !(company.ticker ?? "").trimmingCharacters(in: .whitespaces).isEmpty || status == "public"
    }

    private var companyReports: [MacReport] {
        store.reports(for: company.id)
    }

    private var runningReports: [MacReport] {
        companyReports.filter { !$0.isComplete && !$0.isFailed }
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Dossier Header
                HStack(alignment: .center, spacing: 14) {
                    MacMonogram(company: company, size: 52)

                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text(company.name ?? company.id)
                                .font(.title3.weight(.bold))
                                .lineLimit(1)
                            if !isListed, let stage = store.dealPipelines[company.id]?.stage {
                                MacStatusPill(text: stage, color: .accentColor)
                            }
                        }
                        Text(headerLine.isEmpty ? company.subtitle : headerLine)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 8)

                    // Action buttons
                    HStack(spacing: 8) {
                        Button {
                            onNewReport()
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "sparkles")
                                Text("Memo")
                            }
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                        }
                        .buttonStyle(.borderedProminent)

                        Button {
                            onDecision()
                        } label: {
                            Image(systemName: "checkmark.seal")
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 6)
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.bottom, 2)

                // Tab Bar
                MacTabBar(
                    items: DossierSection.allCases.map { ($0, $0.rawValue) },
                    selection: $activeSection
                )

                // Overview cards
                if shows(.overview) {
                    MacUnifiedProfileView(companyId: company.id)
                    MacSignalScoreView(companyId: company.id)
                }

                // A listed company's next report, quarters and SEC filings
                if isListed && shows(.overview) {
                    MacEarningsFilingsView(company: company).id(company.id)
                }

                // Deal Pipeline card
                if isListed ? shows(.pipeline) : shows(.pipeline, .overview) {
                    MacDealPipelineView(company: company)
                }

                // Valuation Comps Rail
                if shows(.comps) {
                    MacCompsRailView(company: company)
                }

                // Cap Table Simulator
                if shows(.capTable) {
                    MacCapTableSimulatorView(company: company)
                }

                // Team & Leadership Radar
                if shows(.team) {
                    MacFounderRadarView(company: company)
                }

                // VC Ratios Blotter
                if shows(.ratios) {
                    MacVCRatiosBlotterView(company: company)
                }

                // Active Pipeline Monitor
                if shows(.memos, .overview) && !runningReports.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
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
                            .appleGlassTile(cornerRadius: 6)
                        }
                    }
                    .padding(14)
                    .appleGlassCard(cornerRadius: 14)
                }

                // Research Reports & Memos
                if shows(.memos, .overview) {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            MacCardHeader("Research Reports & Memos", subtitle: companyReports.isEmpty ? nil : "\(companyReports.count) dossiers", systemImage: "doc.text.fill")
                            Spacer()
                            Button {
                                onNewReport()
                            } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: "plus")
                                    Text("New")
                                }
                                .font(.caption.weight(.medium))
                            }
                        }

                        if companyReports.isEmpty {
                            Text("No research reports on file yet.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.vertical, 16)
                        } else {
                            VStack(spacing: 8) {
                                ForEach(companyReports) { report in
                                    MemoRowView(report: report)
                                }
                            }
                        }
                    }
                    .padding(14)
                    .appleGlassCard(cornerRadius: 14)

                    // Embedded Memo Studio
                    MacMemoStudioView(company: company, onInvestigate: onNewReport)
                }

                // Decisions Timeline
                if shows(.ic, .overview) {
                    MacDecisionTimeline(companyId: company.id)
                }

                // IC Diligence Stack
                if shows(.ic) {
                    MacICPrepView(company: company)
                    MacICRoomView(companyId: company.id, reportId: nil)
                    MacNumberLintView(companyId: company.id)
                    MacThesisTrackerView(company: company)
                    MacCommentsView(companyId: company.id, target: MacCommentTarget(kind: "company", ref: company.id, label: company.title))
                }
            }
            .padding(16)
        }
        .task(id: company.id) {
            store.markCompanyVisited(company.id)
            await store.fetchReports(for: company.id)
        }
    }
}

// MARK: - Memo Row View
public struct MemoRowView: View {
    public let report: MacReport
    @EnvironmentObject private var store: ResearchDeskStore

    public init(report: MacReport) {
        self.report = report
    }

    public var body: some View {
        HStack(spacing: 12) {
            Image(systemName: report.isComplete ? "doc.text.fill" : "doc.badge.gearshape")
                .font(.title3)
                .foregroundStyle(report.isComplete ? Color.blue : Color.orange)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(report.displayTitle)
                        .font(.body.weight(.semibold))

                    if store.isReportNew(report) {
                        Text("NEW")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.accentColor, in: Capsule())
                    }

                    if let lang = report.language {
                        Text(lang.uppercased())
                            .font(.caption2.monospacedDigit())
                            .padding(.horizontal, 3)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                    }

                    MacStatusPill(
                        text: report.statusTone.capitalized,
                        color: report.isComplete ? .green : (report.isFailed ? .red : .orange)
                    )
                }

                Text("Updated \(report.dateLabel) · \(report.audience ?? "Internal")")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if report.status == "awaiting_studio" {
                Button {
                    Task {
                        _ = try? await store.generateReportFromStudio(reportId: report.id)
                    }
                } label: {
                    Text("Synthesize")
                        .font(.caption2.weight(.bold))
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(10)
        .appleGlassTile(cornerRadius: 8)
    }
}
