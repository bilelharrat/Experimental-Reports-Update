import SwiftUI

enum MacTab: String, CaseIterable, Identifiable, Hashable {
    case home
    case attention
    case pipeline
    case research
    case documents
    case market
    case news
    case pulse
    case portfolio
    case copilot
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: return "Home"
        case .attention: return "Attention"
        case .pipeline: return "Pipeline"
        case .research: return "Research Desk"
        case .documents: return "Documents"
        case .market: return "Market Radar"
        case .news: return "News Desk"
        case .pulse: return "Market Pulse"
        case .portfolio: return "Portfolio & Watch"
        case .copilot: return "Ask Warren"
        case .settings: return "Settings"
        }
    }

    var systemImage: String {
        switch self {
        case .home: return "house.fill"
        case .attention: return "bell.badge"
        case .pipeline: return "list.bullet.rectangle.portrait"
        case .research: return "building.columns"
        case .documents: return "doc.text.magnifyingglass"
        case .market: return "chart.line.uptrend.xyaxis"
        case .news: return "newspaper"
        case .pulse: return "waveform.path.ecg"
        case .portfolio: return "briefcase.fill"
        case .copilot: return "bubble.left.and.bubble.right.fill"
        case .settings: return "gearshape"
        }
    }
}

struct MacRootView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.openWindow) private var openWindow
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @State private var showInspector = false
    @State private var shownTab: MacTab = .home
    @State private var blotterShown = false
    @State private var lastTabChange = Date.distantPast
    @State private var lastBlotterChange = Date.distantPast
    private static var launchOverridesApplied = false

    private var deskTarget: MacDeskCommandTarget {
        MacDeskCommandTarget(
            companyId: store.selectedCompany?.id,
            reportId: nil,
            commandPalette: { store.openCommandPalette() },
            firmSearch: { store.showFirmSearch = true },
            newMemo: { store.requestNewReport() },
            shortcuts: { store.showShortcutSheet = true },
            recordDecision: { if let company = store.selectedCompany { store.requestDecision(for: company) } },
            openICReview: nil
        )
    }

    private var signInRequired: Bool {
        !MacConfig.bypassLogin && store.session?.isAnonDev == true
    }

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebar
        } detail: {
            detail
        }
        .navigationSplitViewStyle(.balanced)
        // The tour rides over the whole window so it can ring the sidebar row
        // and the toolbar button it is describing.
        .macWelcomeTourOverlay()
        .focusedSceneValue(\.deskTarget, deskTarget)
        .onAppear {
            shownTab = store.selectedTab
            blotterShown = store.showBlotter
            store.openMemoWindow = { request in
                openWindow(id: "memo", value: request)
            }
            store.openICWindow = { request in
                openWindow(id: "ic", value: request)
            }
        }
        .onDisappear {
            store.showCommandPalette = false
            store.showShortcutSheet = false
            store.showWelcomeTour = false
            store.showFirmSearch = false
            store.showNewReportSheet = false
            store.showDecisionSheet = false
            store.showDeckIntakeSheet = false
            store.showCopilotPanel = false
        }
        .onChange(of: store.selectedTab) { _, tab in
            let now = Date()
            lastTabChange = now
            if now.timeIntervalSince(lastBlotterChange) < 0.3 {
                Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(300))
                    lastTabChange = Date()
                    shownTab = store.selectedTab
                }
            } else {
                shownTab = tab
            }
        }
        .onChange(of: store.showBlotter) { _, open in
            let now = Date()
            lastBlotterChange = now
            if now.timeIntervalSince(lastTabChange) < 0.3 {
                Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(300))
                    lastBlotterChange = Date()
                    withAnimation(.easeInOut(duration: 0.18)) { blotterShown = store.showBlotter }
                }
            } else {
                withAnimation(.easeInOut(duration: 0.18)) { blotterShown = open }
            }
        }
        .onChange(of: store.session?.isAnonDev) { _, _ in
            if signInRequired { store.showLoginSheet = true }
        }
        .sheet(isPresented: $store.showDecisionSheet) {
            if let company = store.decisionTarget {
                MacDecisionSheet(company: company, seedReportId: store.decisionSeedReportId)
                    .environmentObject(store)
            }
        }
        .task {
            await store.bootstrap()
            if !Self.launchOverridesApplied {
                Self.launchOverridesApplied = true
                store.applyLaunchOverrides()
            }
            store.presentWelcomeTourIfNeeded()
        }
        .onChange(of: store.session == nil) { _, signedOut in
            guard !signedOut else { return }
            // The login sheet is still closing; give it a beat before presenting the tour.
            Task { @MainActor in
                try? await Task.sleep(for: .milliseconds(450))
                store.presentWelcomeTourIfNeeded()
            }
        }
        .sheet(isPresented: $store.showLoginSheet) {
            MacLoginView()
                .environmentObject(store)
                .interactiveDismissDisabled(store.session == nil || signInRequired)
        }
        .sheet(isPresented: $store.showNewReportSheet) {
            if let company = store.newReportCompany ?? store.selectedCompany ?? store.companies.first {
                MacGenerateReportSheet(company: company) { newRep in
                    store.handleCreatedReport(newRep)
                }
                .environmentObject(store)
            } else {
                VStack(spacing: 12) {
                    Text("Add a company to the pipeline first.")
                    Button("Close") { store.showNewReportSheet = false }
                        .keyboardShortcut(.cancelAction)
                }
                .padding(24)
            }
        }
        .sheet(isPresented: $store.showCommandPalette) {
            MacCommandPalette()
                .environmentObject(store)
        }
        .sheet(isPresented: $store.showShortcutSheet) {
            MacShortcutOverlay()
        }
        .sheet(isPresented: $store.showFirmSearch) {
            MacFirmSearchSheet()
                .environmentObject(store)
        }
        .sheet(isPresented: $store.showDeckIntakeSheet) {
            MacPitchDeckIntakeSheet(fileURL: store.droppedDeckURL)
                .environmentObject(store)
        }
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        VStack(spacing: 0) {
            List(selection: $store.selectedTab) {
                Section("Desks") {
                    sidebarRow(.home)
                    sidebarRow(.attention, badge: (store.rollup?.attention.count ?? 0) + store.intakeItems.count)
                    sidebarRow(.pipeline, badge: store.rollup?.totals?.needsActionCount ?? 0)
                    sidebarRow(.research, badge: store.runningReports.count)
                    sidebarRow(.documents, badge: store.reports.count)
                    sidebarRow(.market, badge: store.pinnedTickers.count)
                    sidebarRow(.news)
                    sidebarRow(.pulse)
                    sidebarRow(.portfolio, badge: store.portfolioEntries.count)
                }

                Section("Intelligence") {
                    sidebarRow(.copilot)
                }

                Section("System") {
                    sidebarRow(.settings)
                }

                MacSidebarCompaniesSection()
            }
            .listStyle(.sidebar)

            Divider()
            accountFooter
        }
        .navigationTitle("BSH Research")
        .navigationSplitViewColumnWidth(min: 220, ideal: 240, max: 280)
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await store.bootstrap() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Refresh All Desks (⌘R)")
            }
        }
    }

    private func sidebarRow(_ tab: MacTab, badge: Int = 0) -> some View {
        HStack(spacing: 8) {
            if tab == .copilot {
                WarrenMarkView(size: 16, isBusy: store.copilotStreaming)
            } else {
                Image(systemName: tab.systemImage)
                    .frame(width: 16)
            }
            Text(tab.title)
            Spacer()
        }
        .badge(badge)
        .tag(tab)
        .glassListRow(isSelected: store.selectedTab == tab, cornerRadius: 10)
        .macWelcomeTourAnchor(MacWelcomeTourCatalog.tabAnchor(tab))
    }

    /// Who is signed in and what they may do — the gate for every write action.
    private var accountFooter: some View {
        HStack(spacing: 8) {
            if let session = store.session {
                MacMonogram(name: session.displayName, size: 26)
            } else {
                Image(systemName: "person.crop.circle.badge.exclamationmark")
                    .font(.title3)
                    .foregroundStyle(Color.orange)
            }

            VStack(alignment: .leading, spacing: 1) {
                if let session = store.session {
                    Text(session.displayName)
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                    Text(session.isAnonDev ? "Local dev · \(session.roleLabel)" : session.roleLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    Text(store.authChecked ? "Not signed in" : "Connecting…")
                        .font(.caption.weight(.semibold))
                    Text(store.authChecked ? "Read-only until you sign in" : MacConfig.baseURL.host ?? "")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 4)

            if let session = store.session, !session.isAnonDev {
                Button {
                    Task { await store.signOut() }
                } label: {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                }
                .buttonStyle(.plain)
                .help("Sign out")
            } else {
                Button("Sign In") {
                    store.showLoginSheet = true
                }
                .controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Detail

    private var detail: some View {
        VStack(spacing: 0) {
            if let message = store.error {
                errorBanner(message)
                Divider()
            }

            HSplitView {
                Group {
                    switch shownTab {
                    case .home:
                        MacHomeDeskView()
                    case .attention:
                        MacAttentionDeskView()
                    case .pipeline:
                        MacPipelineDeskView()
                    case .portfolio:
                        MacPortfolioDeskView()
                    case .research:
                        MacResearchDeskView()
                    case .documents:
                        MacDocumentsDeskView()
                    case .market:
                        MacMarketRadarView()
                    case .news:
                        MacNewsDeskView()
                    case .pulse:
                        MacPulseDeskView()
                    case .copilot:
                        MacCopilotView()
                    case .settings:
                        MacSettingsView()
                    }
                }
                .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)

                if store.showBrowserPanel {
                    MacEmbeddedBrowserPanel()
                        .frame(minWidth: 360, idealWidth: 460, maxWidth: 850)
                        .layoutPriority(0)
                        .transition(.move(edge: .trailing).combined(with: .opacity))
                }

                if store.showCopilotPanel {
                    MacCopilotSidePanel()
                        .frame(minWidth: 340, idealWidth: 400, maxWidth: 580)
                        .layoutPriority(0)
                        .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if blotterShown {
                Divider()
                MacBlotterView()
                    .frame(minHeight: 180, idealHeight: 240, maxHeight: 360)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                // Cache & sync status (local-first: desks paint from cache, then refresh)
                if store.isOfflineMode {
                    HStack(spacing: 4) {
                        Circle().fill(Color.orange).frame(width: 6, height: 6)
                        Text("Offline · cached").font(.caption2.weight(.medium)).foregroundStyle(.secondary)
                    }
                    .help("The server is unreachable; showing the last cached data")
                } else if let syncError = store.homeSyncError {
                    HStack(spacing: 4) {
                        Circle().fill(Color.red).frame(width: 6, height: 6)
                        Text("Sync failed").font(.caption2.weight(.medium)).foregroundStyle(.secondary)
                    }
                    .help(syncError)
                } else if let sync = store.lastSyncDate {
                    HStack(spacing: 4) {
                        Circle().fill(Color.green).frame(width: 6, height: 6)
                        Text("Synced \(sync, style: .time)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    .help("Last successful sync; data is cached locally for instant launch")
                }
                if store.needsPasswordReset {
                    HStack(spacing: 4) {
                        Circle().fill(Color.orange).frame(width: 6, height: 6)
                        Text("Password reset required").font(.caption2.weight(.medium)).foregroundStyle(.secondary)
                    }
                    .help("Your account is on a temporary password; change it in the web portal")
                }

                Button {
                    store.openCommandPalette()
                } label: {
                    Label("Command Line", systemImage: "terminal")
                }
                .help("Command line — type a company, ticker or NAME CODE (⌘K)")
                .macWelcomeTourAnchor(MacWelcomeTourCatalog.commandAnchor)

                Button {
                    store.requestNewReport()
                } label: {
                    HStack(spacing: 5) {
                        AiOrbView(size: 14)
                        Text("Generate report")
                            .font(.system(size: 12, weight: .medium))
                    }
                }
                .help(store.canRunTasks ? "Generate research report / memo (⌘N)" : "Sign in with an analyst or partner role to run memos")
                .disabled(!store.canRunTasks)

                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        store.showBrowserPanel.toggle()
                    }
                } label: {
                    Label("Research Browser", systemImage: store.showBrowserPanel ? "globe.americas.fill" : "globe")
                }
                .help("Toggle Embedded Research Browser (⌘B)")
                .keyboardShortcut("b", modifiers: .command)

                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        store.showCopilotPanel.toggle()
                    }
                } label: {
                    HStack(spacing: 5) {
                        WarrenMarkView(size: 19, isBusy: store.copilotStreaming)
                        Text("Ask")
                            .font(.system(size: 12, weight: .medium))
                    }
                }
                .help("Ask Warren (⌥⌘C)")
                .keyboardShortcut("c", modifiers: [.command, .option])

                Button {
                    store.toggleBlotter()
                } label: {
                    Label("Jobs & Alerts", systemImage: store.showBlotter ? "rectangle.bottomthird.inset.filled" : "dock.rectangle")
                }
                .help("Jobs, alerts, signals, chat and audit (⌥⌘J)")
                .badge(store.activeJobs.count)

                Button {
                    withAnimation { showInspector.toggle() }
                } label: {
                    Label("Inspector", systemImage: "sidebar.trailing")
                }
                .help("Inspector (⌥⌘I)")
                .keyboardShortcut("i", modifiers: [.command, .option])

                Menu {
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { store.showBrowserPanel.toggle() }
                    } label: {
                        Label(store.showBrowserPanel ? "Hide Research Browser" : "Show Research Browser", systemImage: "globe")
                    }

                    Button {
                        openWebPortal()
                    } label: {
                        Label("Open This Page in Research Browser", systemImage: "globe")
                    }

                    Button {
                        MacConfig.openInBrowser(store.currentWebURL)
                    } label: {
                        Label("Open This Page on Web", systemImage: "safari")
                    }

                    Button {
                        store.showFirmSearch = true
                    } label: {
                        Label("Firm Memory Search…", systemImage: "brain.head.profile")
                    }

                    Divider()

                    Button {
                        store.showShortcutSheet = true
                    } label: {
                        Label("Keyboard Shortcuts", systemImage: "keyboard")
                    }
                } label: {
                    Label("More", systemImage: "ellipsis.circle")
                }
                .help("Browser, web portal, firm search, shortcuts")
            }
        }
        .inspector(isPresented: $showInspector) {
            MacInspectorView()
        }
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.dsLabel)
                .foregroundStyle(Color.dsWarning)
            Text(message)
                .font(.dsCaption)
                .lineLimit(2)
                .textSelection(.enabled)
            Spacer(minLength: 8)
            Button {
                store.error = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.dsLabel)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Dismiss")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.dsWarning.opacity(0.10))
    }

    private func openWebPortal() {
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(store.currentWebURL)
        }
    }
}

extension MacAppStore {
    /// The web-portal page matching what the desk shows right now.
    var currentWebURL: URL {
        switch selectedTab {
        case .market:
            return selectedTicker.map { MacConfig.webQuoteURL(ticker: $0) } ?? MacConfig.webURL(path: "market-radar")
        case .news:
            return MacConfig.webNewsURL()
        case .research, .pipeline, .copilot:
            return selectedCompany.map { MacConfig.webCompanyURL(id: $0.id) } ?? MacConfig.baseURL
        case .documents:
            return selectedReport.map { MacConfig.webReportURL(id: $0.id) } ?? MacConfig.webURL(path: "reports")
        case .pulse:
            return MacConfig.webURL(path: "innovation-lab/market-pulse")
        case .portfolio:
            return MacConfig.webURL(path: "tracking")
        case .settings:
            return MacConfig.webURL(path: "settings")
        case .attention, .home:
            return MacConfig.baseURL
        }
    }
}

// MARK: - Sidebar companies

/// How the sidebar orders companies — the website's sort menu (Sidebar.vue). The
/// company payload carries no creation date, so, as on the web, "newest" and "oldest"
/// read the list's own order; "recently viewed" stands in for the web's view count,
/// since what the Mac keeps is when each company was last opened.
enum MacCompanySort: String, CaseIterable, Identifiable {
    case az, za, newest, oldest, viewed

    var id: String { rawValue }

    var title: String {
        switch self {
        case .az: return "Name, A to Z"
        case .za: return "Name, Z to A"
        case .newest: return "Newest first"
        case .oldest: return "Oldest first"
        case .viewed: return "Recently viewed"
        }
    }

    var shortTitle: String {
        switch self {
        case .az: return "A–Z"
        case .za: return "Z–A"
        case .newest: return "Newest"
        case .oldest: return "Oldest"
        case .viewed: return "Viewed"
        }
    }

    /// Followed companies first, then the chosen order — the web's favorites-first rule.
    static func apply(
        _ sort: MacCompanySort,
        to companies: [MacCompany],
        followed: Set<String>,
        visits: [String: Date]
    ) -> [MacCompany] {
        let rows = companies.enumerated().map { (index: $0.offset, company: $0.element) }
        func name(_ c: MacCompany) -> String { c.name ?? c.id }
        return rows.sorted { a, b in
            let fa = followed.contains(a.company.id), fb = followed.contains(b.company.id)
            if fa != fb { return fa }
            switch sort {
            case .az:
                return name(a.company).localizedStandardCompare(name(b.company)) == .orderedAscending
            case .za:
                return name(a.company).localizedStandardCompare(name(b.company)) == .orderedDescending
            case .newest:
                return a.index > b.index
            case .oldest:
                return a.index < b.index
            case .viewed:
                let va = visits[a.company.id] ?? .distantPast, vb = visits[b.company.id] ?? .distantPast
                if va != vb { return va > vb }
                return name(a.company).localizedStandardCompare(name(b.company)) == .orderedAscending
            }
        }
        .map(\.company)
    }
}

/// The website's sidebar company list, on the Mac: every company, sortable and
/// filterable, with the open one's pages under it like a folder. As on the web,
/// opening a company only opens its folder; its pages — Reports, News, Research
/// Desk, Market — are what go somewhere. This list is the Research desk's directory
/// now, the way the web moved the desk's own column into its sidebar.
struct MacSidebarCompaniesSection: View {
    @EnvironmentObject private var store: MacAppStore
    @AppStorage("bsh.sidebar.companySort") private var sortRaw = MacCompanySort.az.rawValue
    @State private var filter = ""
    @State private var sector = Self.allSectors
    @State private var diffsOnly = false
    @State private var openCompanyId: String?

    private static let allSectors = "All sectors"
    /// A filter field earns its place once the list outgrows a glance (web: > 8).
    private static let filterThreshold = 8

    private var sort: MacCompanySort { MacCompanySort(rawValue: sortRaw) ?? .az }

    private var sectors: [String] {
        let found = Set(store.companies.compactMap(\.sector).filter { !$0.isEmpty })
        return [Self.allSectors] + found.sorted()
    }

    private var visible: [MacCompany] {
        let query = filter.trimmingCharacters(in: .whitespacesAndNewlines)
        return MacCompanySort.apply(
            sort,
            to: store.companies,
            followed: Set(store.followedCompanyIds),
            visits: store.visitedCompanyTimestamps
        )
        .filter { company in
            if diffsOnly && !store.isCompanyModified(company.id) { return false }
            if sector != Self.allSectors && company.sector != sector { return false }
            guard !query.isEmpty else { return true }
            return (company.name ?? "").localizedCaseInsensitiveContains(query)
                || (company.ticker ?? "").localizedCaseInsensitiveContains(query)
                || company.id.localizedCaseInsensitiveContains(query)
        }
    }

    var body: some View {
        Section {
            if store.companies.count > Self.filterThreshold {
                filterField
            }
            if !store.companies.isEmpty {
                filterRow
            }
            if store.companies.isEmpty {
                Text("No companies yet")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            } else if visible.isEmpty {
                Text(filter.isEmpty ? "Nothing changed since you last looked" : "No company matches")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(visible) { company in
                    companyRow(company)
                    if openCompanyId == company.id {
                        pages(for: company)
                    }
                }
            }
        } header: {
            header
        }
        // However a company was reached — the ⌘K palette, a link, another desk — its
        // folder opens here too, as on the web.
        .onChange(of: store.selectedCompany?.id, initial: true) { _, id in
            if let id { openCompanyId = id }
        }
    }

    // MARK: Header, filter, sector

    private var header: some View {
        HStack(spacing: 6) {
            Text("Companies")
            Spacer(minLength: 4)
            Text("\(store.companies.count)")
                .monospacedDigit()
                .foregroundStyle(.tertiary)
            Menu {
                Picker("Sort", selection: $sortRaw) {
                    ForEach(MacCompanySort.allCases) { option in
                        Text(option.title).tag(option.rawValue)
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
            } label: {
                Label(sort.shortTitle, systemImage: "arrow.up.arrow.down")
                    .labelStyle(.titleAndIcon)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Sort companies")
        }
    }

    private var filterField: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.tertiary)
            TextField("Filter companies", text: $filter)
                .textFieldStyle(.plain)
                .onExitCommand { filter = "" }
            if !filter.isEmpty {
                Button {
                    filter = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.tertiary)
                .help("Clear the filter")
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
    }

    /// Sector and Diffs: the two filters the Research desk's directory carried.
    private var filterRow: some View {
        HStack(spacing: 6) {
            // Hidden when every company shares one sector: a one-item menu says nothing.
            if sectors.count > 2 {
                Picker("Sector", selection: $sector) {
                    ForEach(sectors, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .controlSize(.small)
            }
            Spacer(minLength: 0)
            Button {
                diffsOnly.toggle()
            } label: {
                Label("Diffs", systemImage: diffsOnly ? "sparkle" : "sparkles")
                    .font(.caption2.weight(.medium))
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
            .tint(diffsOnly ? .accentColor : .secondary)
            .help("Only companies with updates or new memos since you last looked")
        }
    }

    // MARK: Rows

    private func companyRow(_ company: MacCompany) -> some View {
        let open = openCompanyId == company.id
        return Button {
            withAnimation(.easeOut(duration: 0.15)) {
                openCompanyId = open ? nil : company.id
            }
        } label: {
            HStack(spacing: 4) {
                CompanyListRow(company: company)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .rotationEffect(.degrees(open ? 0 : -90))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .glassListRow(isSelected: isShowing(company), cornerRadius: 10)
        .help(company.name ?? company.id)
        .contextMenu {
            Button("Open Research Desk") { go(company, to: .research) }
            Button(store.isFollowed(company.id) ? "Unfollow" : "Follow") {
                Task { await store.toggleFollow(company.id) }
            }
        }
    }

    /// The company is what the current desk is showing.
    private func isShowing(_ company: MacCompany) -> Bool {
        guard store.selectedCompany?.id == company.id else { return false }
        return store.selectedTab == .research
    }

    @ViewBuilder
    private func pages(for company: MacCompany) -> some View {
        let reports = store.reports.filter { $0.companyId == company.id }.count
        pageRow("Reports", systemImage: "doc.text", count: reports) {
            store.documentsCompanyFilter = company.id
            go(company, to: .documents)
        }
        pageRow("News", systemImage: "newspaper", count: nil) {
            store.newsCompanyFocus = company
            go(company, to: .news)
        }
        pageRow("Research Desk", systemImage: "building.columns", count: nil) {
            go(company, to: .research)
        }
        if let ticker = company.ticker, !ticker.isEmpty {
            pageRow("Market", systemImage: "chart.line.uptrend.xyaxis", count: nil) {
                go(company, to: .market)
            }
        }
    }

    private func pageRow(
        _ title: String,
        systemImage: String,
        count: Int?,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: systemImage)
                    .frame(width: 16)
                    .foregroundStyle(.secondary)
                Text(title)
                Spacer(minLength: 4)
                if let count {
                    Text("\(count)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
            }
            .font(.system(size: 12))
            .padding(.leading, 30)
            .padding(.vertical, 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// Select the company (so every desk and Ask Warren follow it), then open the page.
    private func go(_ company: MacCompany, to tab: MacTab) {
        store.selectCompany(company)
        store.selectedTab = tab
    }
}
