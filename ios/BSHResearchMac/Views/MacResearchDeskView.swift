import SwiftUI

struct MacResearchDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var searchText = ""
    @State private var selectedSector: String = "All"
    @State private var showOnlyModified: Bool = false
    @State private var showNewReportSheet = false

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
        .sheet(isPresented: $showNewReportSheet) {
            sheetContent
        }
    }

    @ViewBuilder
    private var sheetContent: some View {
        if let company = store.selectedCompany {
            MacGenerateReportSheet(company: company) { newReport in
                showNewReportSheet = false
                store.openReportInViewer(newReport)
            }
            .environmentObject(store)
        } else {
            EmptyView()
        }
    }

    private var directoryPane: some View {
        VStack(spacing: 0) {
            // Drag & Drop Pitch Deck intake zone
            MacPitchDeckDropBanner()
                .padding(.horizontal, 10)
                .padding(.top, 8)
                .padding(.bottom, 6)

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
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.ultraThinMaterial)

            Divider()

            List(selection: $store.selectedCompany) {
                ForEach(filteredCompanies) { company in
                    CompanyListRow(company: company)
                        .tag(company)
                }
            }
            .listStyle(.inset(alternatesRowBackgrounds: true))
            .onChange(of: store.selectedCompany) { newComp in
                if let newComp {
                    store.markCompanyVisited(newComp.id)
                }
            }
        }
    }

    @ViewBuilder
    private var detailPane: some View {
        if let company = store.selectedCompany {
            CompanyDossierView(company: company, onNewReport: {
                showNewReportSheet = true
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

    var body: some View {
        HStack(spacing: 8) {
            if store.isCompanyModified(company.id) {
                Circle()
                    .fill(Color.accentColor)
                    .frame(width: 6, height: 6)
            } else {
                Spacer().frame(width: 6)
            }

            Circle()
                .fill(colorForString(company.ticker ?? company.id))
                .frame(width: 28, height: 28)
                .overlay(
                    Text(initials)
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(.white)
                )

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(company.name ?? company.id)
                        .font(.body.weight(.medium))
                        .lineLimit(1)
                    if let t = company.ticker, !t.isEmpty {
                        Text(t)
                            .font(.caption2.monospaced())
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 3))
                    }
                }
                Text(company.subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            if let status = company.status, !status.isEmpty {
                Text(status.capitalized)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private func colorForString(_ s: String) -> Color {
        let hash = abs(s.hashValue)
        let colors: [Color] = [.blue, .indigo, .purple, .teal, .cyan, .orange, .mint]
        return colors[hash % colors.count]
    }
}

enum DossierSection: String, CaseIterable, Identifiable {
    case all = "All Modules"
    case team = "Team & Founders"
    case pipeline = "Deal CRM"
    case capTable = "Cap Table"
    case comps = "Public Comps"
    case ratios = "VC Ratios"
    case memos = "Memos & Docs"

    var id: String { rawValue }
    var icon: String {
        switch self {
        case .all: return "square.grid.2x2.fill"
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
    @State private var activeSection: DossierSection = .all

    private var companyReports: [MacReport] {
        store.reports(for: company.id)
    }

    private var runningReports: [MacReport] {
        companyReports.filter { !$0.isComplete && !$0.isFailed }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header Card
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 10) {
                            Text(company.name ?? company.id)
                                .font(.title2.weight(.bold))
                            if let ticker = company.ticker, !ticker.isEmpty {
                                Text(ticker)
                                    .font(.title3.monospaced().weight(.semibold))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 2)
                                    .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
                            }
                            if let stage = store.dealPipelines[company.id]?.stage {
                                Text(stage)
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundStyle(Color.accentColor)
                                    .padding(.horizontal, 7)
                                    .padding(.vertical, 2.5)
                                    .background(Color.accentColor.opacity(0.1), in: Capsule())
                            }
                        }

                        Text(company.subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    // Quick Actions
                    HStack(spacing: 8) {
                        Button {
                            onNewReport()
                        } label: {
                            Label("New Memo", systemImage: "plus")
                        }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut("n", modifiers: .command)
                        .help("Generate an investment memo (⌘N)")

                        Button {
                            let url = MacConfig.webCompanyURL(id: company.id)
                            withAnimation {
                                store.openInEmbeddedBrowser(url)
                            }
                        } label: {
                            Label("Open in Web", systemImage: "globe")
                        }
                        .buttonStyle(.bordered)
                        .help("View comprehensive company portal in embedded browser (⌘⇧W)")
                    }
                }
                .padding()
                .appleGlassCard(cornerRadius: 16)

                // Quick Navigation / Section Filter Bar
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(DossierSection.allCases) { sec in
                            Button {
                                withAnimation(.spring(response: 0.25, dampingFraction: 0.8)) {
                                    activeSection = sec
                                }
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: sec.icon)
                                        .font(.caption2)
                                    Text(sec.rawValue)
                                        .font(.caption.weight(activeSection == sec ? .bold : .medium))
                                }
                                .padding(.horizontal, 11)
                                .padding(.vertical, 6)
                                .background(
                                    activeSection == sec ? Color.accentColor.opacity(0.18) : Color.white.opacity(0.05),
                                    in: Capsule()
                                )
                                .foregroundStyle(activeSection == sec ? Color.accentColor : Color.secondary)
                                .overlay(
                                    Capsule().stroke(
                                        activeSection == sec ? Color.accentColor.opacity(0.4) : Color.white.opacity(0.12),
                                        lineWidth: 0.75
                                    )
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 2)
                }

                // Portfolio Financial Health & Runway Blotter
                if activeSection == .all || activeSection == .memos {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Portfolio Financial Health & Runway", systemImage: "cross.case.fill")
                                .font(.headline)
                            Spacer()
                            Text("FACT INDEX SNAPSHOT")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2.5)
                                .appleGlassPill(color: .secondary)
                        }

                        HStack(spacing: 12) {
                            KPICard(title: "ARR / REVENUE", value: "$14.2M", subtext: "+32% YoY growth", isGood: true)
                            KPICard(title: "NET BURN RATE", value: "$480K / mo", subtext: "Operating outflow", isGood: nil)
                            KPICard(title: "CASH BALANCE", value: "$3.5M", subtext: "Audited treasury", isGood: nil)
                            KPICard(title: "IMPLIED RUNWAY", value: "7.3 mos", subtext: "< 9.0 mo Alert threshold", isGood: false)
                        }

                        // Runway Alert Banner (< 9 months)
                        HStack(spacing: 12) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.title3)
                                .foregroundStyle(.red)

                            VStack(alignment: .leading, spacing: 2) {
                                Text("Runway Alert: 7.3 Months Remaining (Threshold: 9.0 Mos)")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.red)
                                Text("Asset burn exceeds safe operational runway. Syndicate bridge extension or recapitalization memo recommended.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            Button {
                                onNewReport()
                            } label: {
                                Label("Draft Bridge Memo", systemImage: "doc.badge.plus")
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                        .padding(10)
                        .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.red.opacity(0.2), lineWidth: 1)
                        )
                    }
                    .padding()
                    .appleGlassCard(cornerRadius: 16)
                }

                // Deal Pipeline & Relationship Warmth (Affinity Grade)
                if activeSection == .all || activeSection == .pipeline {
                    MacDealPipelineView(company: company)
                }

                // Public ↔ Private Comps Rail
                if activeSection == .all || activeSection == .comps {
                    MacCompsRailView(company: company)
                }

                // Cap Table & Waterfall Dilution Simulator (Carta/Excel Grade)
                if activeSection == .all || activeSection == .capTable {
                    MacCapTableSimulatorView(company: company)
                }

                // Founder Pedigree & Developer Traction Radar (Harmonic/Ampersand Grade)
                if activeSection == .all || activeSection == .team {
                    MacFounderRadarView(company: company)
                }

                // Institutional VC Ratios & Efficiency Blotter (Bessemer / a16z / Sequoia)
                if activeSection == .all || activeSection == .ratios {
                    MacVCRatiosBlotterView(company: company)
                }

                // Active Pipeline Monitor (if any runs in progress)
                if (activeSection == .all || activeSection == .memos) && !runningReports.isEmpty {
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
                                    .font(.caption.monospaced())
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
                if activeSection == .all || activeSection == .memos {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Research Memos & Artifacts")
                                .font(.headline)
                            Spacer()
                            Text("\(companyReports.count) documents")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }

                        if companyReports.isEmpty {
                            Text("No investment memos generated yet for this company.")
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
            }
            .padding(20)
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
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 17, weight: .bold, design: .monospaced))
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
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1.5)
                            .background(Color.accentColor, in: Capsule())
                    }

                    if let lang = report.language {
                        Text(lang.uppercased())
                            .font(.caption2.monospaced())
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
                    store.openReportInViewer(report)
                } label: {
                    Label("Read Memo", systemImage: "book.pages")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .help("Open in Document Viewer Desk")
            }

            Button {
                let url = MacConfig.webReportURL(id: report.id)
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

    @Environment(\.dismiss) private var dismiss

    @State private var reportType = "Investment Report (Auto)"
    @State private var audience = "Institutional"
    @State private var language = "en"
    @State private var submitting = false
    @State private var error: String?

    let availableTypes = [
        "Investment Report (Auto)",
        "Buffett Memo",
        "Earnings Analysis",
        "Competitor Deep Dive",
        "Quick Note"
    ]

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
                            Text(ticker).font(.body.monospaced())
                        }
                    }
                }

                Section("Memo Parameters") {
                    Picker("Report Type", selection: $reportType) {
                        ForEach(availableTypes, id: \.self) { type in
                            Text(type).tag(type)
                        }
                    }

                    Picker("Audience", selection: $audience) {
                        Text("Institutional").tag("Institutional")
                        Text("Internal").tag("Internal")
                        Text("Retail").tag("Retail")
                    }

                    Picker("Language", selection: $language) {
                        Text("English").tag("en")
                        Text("Chinese (中文)").tag("zh")
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
                Button("Start Pipeline") {
                    Task { await submit() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(submitting)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 480, height: 420)
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
