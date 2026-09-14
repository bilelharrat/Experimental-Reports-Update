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

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebar
        } detail: {
            detail
        }
        .navigationSplitViewStyle(.balanced)
        .onAppear {
            store.openMemoWindow = { request in
                openWindow(id: "memo", value: request)
            }
            store.openICWindow = { request in
                openWindow(id: "ic", value: request)
            }
        }
        .sheet(isPresented: $store.showDecisionSheet) {
            if let company = store.decisionTarget {
                MacDecisionSheet(company: company, seedReportId: store.decisionSeedReportId)
                    .environmentObject(store)
            }
        }
        .task {
            await store.bootstrap()
        }
        .sheet(isPresented: $store.showLoginSheet) {
            MacLoginView()
                .environmentObject(store)
                .interactiveDismissDisabled(store.session == nil)
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
                    Label(MacTab.home.title, systemImage: MacTab.home.systemImage)
                        .tag(MacTab.home)

                    Label(MacTab.attention.title, systemImage: MacTab.attention.systemImage)
                        .badge((store.rollup?.attention.count ?? 0) + store.intakeItems.count)
                        .tag(MacTab.attention)

                    Label(MacTab.pipeline.title, systemImage: MacTab.pipeline.systemImage)
                        .badge(store.rollup?.totals?.needsActionCount ?? 0)
                        .tag(MacTab.pipeline)

                    Label(MacTab.research.title, systemImage: MacTab.research.systemImage)
                        .badge(store.runningReports.isEmpty ? 0 : store.runningReports.count)
                        .tag(MacTab.research)

                    Label(MacTab.documents.title, systemImage: MacTab.documents.systemImage)
                        .badge(store.reports.isEmpty ? 0 : store.reports.count)
                        .tag(MacTab.documents)

                    Label(MacTab.market.title, systemImage: MacTab.market.systemImage)
                        .badge(store.pinnedTickers.count)
                        .tag(MacTab.market)

                    Label(MacTab.news.title, systemImage: MacTab.news.systemImage)
                        .tag(MacTab.news)

                    Label(MacTab.pulse.title, systemImage: MacTab.pulse.systemImage)
                        .tag(MacTab.pulse)

                    Label(MacTab.portfolio.title, systemImage: MacTab.portfolio.systemImage)
                        .badge(store.portfolioEntries.count)
                        .tag(MacTab.portfolio)
                }

                Section("Intelligence") {
                    Label(MacTab.copilot.title, systemImage: MacTab.copilot.systemImage)
                        .tag(MacTab.copilot)
                }

                Section("System") {
                    Label(MacTab.settings.title, systemImage: MacTab.settings.systemImage)
                        .tag(MacTab.settings)
                }
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

    /// Who is signed in and what they may do — the gate for every write action.
    private var accountFooter: some View {
        HStack(spacing: 8) {
            Image(systemName: store.session == nil ? "person.crop.circle.badge.exclamationmark" : "person.crop.circle.fill")
                .font(.title3)
                .foregroundStyle(store.session == nil ? Color.orange : Color.accentColor)

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
            HSplitView {
                Group {
                    switch store.selectedTab {
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
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if store.showBlotter {
                Divider()
                MacBlotterView()
                    .frame(minHeight: 180, idealHeight: 240, maxHeight: 360)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.18), value: store.showBlotter)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                // Cache & sync status (local-first: desks paint from cache, then refresh)
                if store.isOfflineMode {
                    HStack(spacing: 4) {
                        Circle().fill(Color.orange).frame(width: 6, height: 6)
                        Text("Offline · cached").font(.caption2.weight(.medium)).foregroundStyle(.secondary)
                    }
                    .help("The server is unreachable; showing the last cached data")
                } else if let sync = store.lastSyncDate {
                    HStack(spacing: 4) {
                        Circle().fill(Color.green).frame(width: 6, height: 6)
                        Text("Synced \(sync, style: .time)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    .help("Last successful sync; data is cached locally for instant launch")
                }

                Button {
                    store.openCommandPalette()
                } label: {
                    Label("Command Line", systemImage: "terminal")
                }
                .help("Command line — type a company, ticker or NAME CODE (⌘K)")

                Button {
                    store.showShortcutSheet = true
                } label: {
                    Label("Shortcuts", systemImage: "questionmark.circle")
                }
                .help("Keyboard shortcuts (⌘/)")

                Button {
                    store.requestNewReport()
                } label: {
                    Label("New Memo", systemImage: "plus.rectangle.on.rectangle")
                }
                .help(store.canRunTasks ? "Generate New Investment Memo (⌘N)" : "Sign in with an analyst or partner role to run memos")
                .disabled(!store.canRunTasks)

                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        store.showBrowserPanel.toggle()
                    }
                } label: {
                    Label("Web Browser", systemImage: store.showBrowserPanel ? "globe.americas.fill" : "globe")
                }
                .help("Toggle Embedded Research Browser (⌘B)")
                .keyboardShortcut("b", modifiers: .command)

                Button {
                    openWebPortal()
                } label: {
                    Label("Open on Web", systemImage: "safari")
                }
                .help("Open Web Portal in Embedded Browser")

                Button {
                    store.toggleBlotter()
                } label: {
                    Label("Jobs & Alerts", systemImage: store.showBlotter ? "rectangle.bottomthird.inset.filled" : "rectangle.bottomthird.inset")
                }
                .help("Toggle Jobs & Alerts blotter (⌥⌘J)")
                .badge(store.activeJobs.count)

                Button {
                    withAnimation { showInspector.toggle() }
                } label: {
                    Label("Inspector", systemImage: "sidebar.trailing")
                }
                .help("Toggle Inspector Panel (⌥⌘I)")
                .keyboardShortcut("i", modifiers: [.command, .option])
            }
        }
        .inspector(isPresented: $showInspector) {
            MacInspectorView()
        }
    }

    private func openWebPortal() {
        let url: URL
        if let company = store.selectedCompany {
            url = MacConfig.webCompanyURL(id: company.id)
        } else if let ticker = store.selectedTicker {
            url = MacConfig.webQuoteURL(ticker: ticker)
        } else {
            url = MacConfig.baseURL
        }
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(url)
        }
    }
}
