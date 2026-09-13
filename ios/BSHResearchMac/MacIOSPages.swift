import SwiftUI

// MARK: - Home (mirrors iOS HomeView reports + companies)

struct MacHomeView: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var query = ""

    private var filteredCompanies: [MacCompany] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return store.companies }
        return store.companies.filter {
            [$0.name, $0.ticker, $0.id, $0.sector]
                .compactMap { $0?.lowercased() }
                .joined(separator: " ")
                .contains(q)
        }
    }

    var body: some View {
        List {
            if store.loading && store.companies.isEmpty {
                ProgressView("Loading…")
                    .frame(maxWidth: .infinity)
            }
            if let err = store.error {
                Text(err).foregroundStyle(.red)
            }

            if !store.runningReports.isEmpty {
                Section("Active") {
                    ForEach(store.runningReports) { report in
                        NavigationLink(value: report) {
                            HStack {
                                ProgressView().controlSize(.small)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(report.companyName ?? report.id)
                                        .font(.subheadline.weight(.semibold))
                                    Text(report.statusTone)
                                        .font(.caption)
                                        .foregroundStyle(.orange)
                                }
                            }
                        }
                    }
                }
            }

            if !store.recentReports.isEmpty {
                Section {
                    ForEach(store.recentReports) { report in
                        NavigationLink(value: report) {
                            HStack(spacing: 10) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(report.companyName ?? report.companyId ?? report.id)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Text(report.displayTitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                                Spacer(minLength: 6)
                                MacStatusPill(
                                    text: report.statusTone,
                                    color: statusColor(report)
                                )
                            }
                        }
                    }
                } header: {
                    Text("Reports")
                } footer: {
                    Text("Recent research memos — same library as iPhone and iPad.")
                }
            }

            Section("Companies") {
                ForEach(filteredCompanies) { company in
                    NavigationLink(value: company) {
                        HStack(spacing: 12) {
                            MacMonogram(name: company.title, size: 36)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(company.title)
                                    .font(.body.weight(.medium))
                                if !company.subtitle.isEmpty {
                                    Text(company.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .listStyle(.inset)
        .navigationTitle("Home")
        .searchable(text: $query, prompt: "Search companies")
        .refreshable { await store.refreshHome() }
        .navigationDestination(for: MacCompany.self) { company in
            MacCompanyView(companyId: company.id, seed: company)
        }
        .navigationDestination(for: MacReport.self) { report in
            MacReportView(report: report)
        }
        .sheet(isPresented: Binding(
            get: { store.openDocumentURL != nil },
            set: { if !$0 { store.closeMemo() } }
        )) {
            MacPaperDeskReader()
                .environmentObject(store)
                .frame(minWidth: 900, minHeight: 700)
        }
    }

    private func statusColor(_ report: MacReport) -> Color {
        if report.isComplete { return .green }
        if report.isFailed { return .red }
        return .orange
    }
}

// MARK: - Company (mirrors CompanyResearchView)

struct MacCompanyView: View {
    let companyId: String
    var seed: MacCompany?
    @EnvironmentObject private var store: MacAppStore
    @State private var company: MacCompany?
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        List {
            if loading && company == nil {
                ProgressView("Loading…")
            } else if let err = error, company == nil {
                Text(err).foregroundStyle(.red)
            } else if let company {
                Section {
                    HStack(spacing: 12) {
                        MacMonogram(name: company.title, size: 52)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(company.title).font(.headline)
                            if let ticker = company.ticker, !ticker.isEmpty {
                                Text(ticker)
                                    .font(.subheadline.monospaced())
                                    .foregroundStyle(.secondary)
                            }
                            if !company.subtitle.isEmpty {
                                Text(company.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section("Reports") {
                    let rows = store.reports(for: companyId)
                    if rows.isEmpty {
                        Text("No reports yet").foregroundStyle(.secondary)
                    } else {
                        ForEach(rows) { report in
                            NavigationLink(value: report) {
                                HStack(spacing: 10) {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(report.displayTitle)
                                            .font(.body.weight(.medium))
                                        if let audience = report.audience {
                                            Text(audience)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    Spacer(minLength: 6)
                                    MacStatusPill(
                                        text: report.statusTone,
                                        color: report.isComplete ? .green : (report.isFailed ? .red : .orange)
                                    )
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
            }
        }
        .listStyle(.inset)
        .navigationTitle(company?.title ?? companyId)
        .task {
            company = seed
            loading = true
            defer { loading = false }
            do {
                company = try await MacAPIClient.shared.getCompany(id: companyId)
                if store.reports(for: companyId).isEmpty {
                    await store.refreshHome()
                }
            } catch {
                if company == nil {
                    self.error = error.localizedDescription
                }
            }
        }
        .navigationDestination(for: MacReport.self) { report in
            MacReportView(report: report)
        }
    }
}

// MARK: - Report detail (mirrors ReportDetailView open-memo section)

struct MacReportView: View {
    @EnvironmentObject private var store: MacAppStore
    @State var report: MacReport

    var body: some View {
        List {
            Section {
                LabeledContent("Company", value: report.companyName ?? report.companyId ?? "—")
                LabeledContent("Type", value: report.displayTitle)
                HStack {
                    Text("Status")
                    Spacer()
                    MacStatusPill(
                        text: report.statusTone,
                        color: report.isComplete ? .green : (report.isFailed ? .red : .orange)
                    )
                }
                if let stage = report.stage {
                    LabeledContent("Stage", value: stage)
                }
                if let err = report.error {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }

            if report.canOpen {
                Section {
                    Button {
                        Task { await store.openMemo(report, language: "en") }
                    } label: {
                        Label(
                            store.openingMemo ? "Opening…" : "Open memo EN",
                            systemImage: "doc.richtext"
                        )
                    }
                    .disabled(store.openingMemo)

                    Button {
                        Task { await store.openMemo(report, language: "zh") }
                    } label: {
                        Label("Open memo 中文", systemImage: "doc.richtext")
                    }
                    .disabled(store.openingMemo)
                } header: {
                    Text("Memo files")
                } footer: {
                    Text("Opens the DOCX/PDF on the paper desk — same files as iPad.")
                }
            } else {
                Section {
                    Text("No DOCX/PDF for this report yet.")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .listStyle(.inset)
        .navigationTitle(report.displayTitle)
        .task {
            if let detail = try? await MacAPIClient.shared.getReport(id: report.id) {
                report = detail
            }
        }
        .sheet(isPresented: Binding(
            get: { store.openDocumentURL != nil },
            set: { if !$0 { store.closeMemo() } }
        )) {
            MacPaperDeskReader()
                .environmentObject(store)
                .frame(minWidth: 900, minHeight: 700)
        }
    }
}

// MARK: - Other tabs (same shell as iOS)

struct MacNewsTabView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        List {
            if store.news.isEmpty {
                Text(store.loading ? "Loading…" : "Pull to refresh news")
                    .foregroundStyle(.secondary)
            }
            ForEach(store.news) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.title).font(.body.weight(.semibold))
                    HStack {
                        if let t = item.ticker {
                            Text(t).font(.caption.monospaced().weight(.bold))
                        }
                        if let s = item.source {
                            Text(s).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .listStyle(.inset)
        .navigationTitle("News")
        .task { await store.refreshNews() }
        .refreshable { await store.refreshNews() }
    }
}

struct MacMarketTabView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        List {
            Section("Watchlist") {
                ForEach(store.watchlist) { q in
                    quoteRow(q)
                }
            }
            Section("Gainers") {
                ForEach(store.gainers) { q in quoteRow(q) }
            }
            Section("Losers") {
                ForEach(store.losers) { q in quoteRow(q) }
            }
        }
        .listStyle(.inset)
        .navigationTitle("Market")
        .task { await store.refreshMarket() }
        .refreshable { await store.refreshMarket() }
    }

    private func quoteRow(_ q: MacQuote) -> some View {
        HStack {
            VStack(alignment: .leading) {
                Text(q.ticker).font(.body.monospaced().weight(.semibold))
                if let name = q.name {
                    Text(name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            Text(q.priceText).font(.body.monospacedDigit())
            Text(q.pctText)
                .font(.body.monospacedDigit().weight(.semibold))
                .foregroundStyle(q.isUp ? Color.green : Color.red)
                .frame(width: 72, alignment: .trailing)
        }
    }
}

struct MacPulseTabView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        List {
            if let pulse = store.pulse {
                Section {
                    Text(pulse.note?.headlineEn ?? "Morning brief")
                        .font(.headline)
                    if let date = pulse.date {
                        Text(date).foregroundStyle(.secondary)
                    }
                }
                if let bullets = pulse.note?.bulletsEn, !bullets.isEmpty {
                    Section("Note") {
                        ForEach(Array(bullets.prefix(6).enumerated()), id: \.offset) { _, b in
                            Text("• \(b)")
                        }
                    }
                }
                if let indices = pulse.indices, !indices.isEmpty {
                    Section("Indices") {
                        ForEach(indices) { row in
                            HStack {
                                Text(row.ticker).font(.body.monospaced().weight(.semibold))
                                Spacer()
                                if let pct = row.changePct1d {
                                    Text(String(format: "%+.2f%%", pct))
                                        .foregroundStyle(pct >= 0 ? Color.green : Color.red)
                                }
                            }
                        }
                    }
                }
            } else {
                ContentUnavailableView("No morning brief", systemImage: "sun.horizon")
            }
        }
        .listStyle(.inset)
        .navigationTitle("Pulse")
        .task { await store.refreshPulse() }
        .refreshable { await store.refreshPulse() }
    }
}

struct MacSettingsTabView: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var baseURL = MacConfig.baseURL.absoluteString
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        Form {
            Section("Server") {
                TextField("API base URL", text: $baseURL)
                Button("Save") {
                    MacConfig.saveBaseURL(baseURL)
                    Task { await store.refreshHome() }
                }
            }
            Section("Account") {
                if MacConfig.readToken() != nil {
                    Text("Signed in").foregroundStyle(.green)
                    Button("Sign out", role: .destructive) { MacConfig.clearToken() }
                } else {
                    TextField("Email", text: $email)
                    SecureField("Password", text: $password)
                    Button("Sign in") {
                        Task {
                            if let token = try? await MacAPIClient.shared.login(
                                email: email, password: password
                            ) {
                                MacConfig.writeToken(token)
                                await store.refreshHome()
                            }
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Settings")
    }
}

struct MacStatusPill: View {
    let text: String
    let color: Color
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.16), in: Capsule())
            .lineLimit(1)
    }
}

struct MacMonogram: View {
    let name: String
    var size: CGFloat = 44
    private static let palette: [Color] = [
        .blue, .indigo, .purple, .pink, .red, .orange, .teal, .cyan, .mint, .green,
    ]
    var body: some View {
        let initials = name.split(separator: " ").prefix(2)
            .compactMap { $0.first.map(String.init) }.joined().uppercased()
        let color = Self.palette[abs(name.hashValue) % Self.palette.count]
        Text(initials.isEmpty ? "?" : initials)
            .font(.system(size: size * 0.38, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(
                LinearGradient(colors: [color, color.opacity(0.72)],
                               startPoint: .topLeading, endPoint: .bottomTrailing),
                in: RoundedRectangle(cornerRadius: size * 0.24, style: .continuous)
            )
    }
}
