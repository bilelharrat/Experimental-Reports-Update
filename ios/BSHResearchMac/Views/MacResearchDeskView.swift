import SwiftUI

struct MacResearchDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var searchText = ""
    @State private var selectedSector: String = "All"
    @State private var showNewReportSheet = false

    private var sectors: [String] {
        let set = Set(store.companies.compactMap { $0.sector }.filter { !$0.isEmpty })
        return ["All"] + Array(set).sorted()
    }

    private var filteredCompanies: [MacCompany] {
        store.companies.filter { company in
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
                .frame(minWidth: 220, idealWidth: 260, maxWidth: 360)
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

                Text("\(filteredCompanies.count) companies")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)

            Divider()

            List(selection: $store.selectedCompany) {
                ForEach(filteredCompanies) { company in
                    CompanyListRow(company: company)
                        .tag(company)
                }
            }
            .listStyle(.inset(alternatesRowBackgrounds: true))
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

    private var initials: String {
        if let ticker = company.ticker, !ticker.isEmpty {
            return String(ticker.prefix(2)).uppercased()
        }
        return String(company.id.prefix(2)).uppercased()
    }

    var body: some View {
        HStack(spacing: 10) {
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

// MARK: - Company Dossier Detail View

struct CompanyDossierView: View {
    let company: MacCompany
    var onNewReport: () -> Void

    @EnvironmentObject private var store: MacAppStore

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
                        }

                        Text(company.subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    // Action buttons
                    HStack(spacing: 8) {
                        Button {
                            onNewReport()
                        } label: {
                            Label("New Memo", systemImage: "plus.doc.fill")
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
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                // Active Pipeline Monitor (if any runs in progress)
                if !runningReports.isEmpty {
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
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("Research Memos & Artifacts")
                            .font(.headline)
                        Spacer()
                        Text("\(companyReports.count) documents")
                            .font(.caption)
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
                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            .padding(20)
        }
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
                    .font(.caption)
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
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
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
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12), in: Capsule())
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
