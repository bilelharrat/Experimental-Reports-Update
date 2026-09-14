import SwiftUI

enum MacTab: String, CaseIterable, Identifiable, Hashable {
    case home
    case research
    case documents
    case market
    case news
    case pulse
    case copilot
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: return "Home"
        case .research: return "Research Desk"
        case .documents: return "Documents"
        case .market: return "Market Radar"
        case .news: return "News Desk"
        case .pulse: return "Market Pulse"
        case .copilot: return "Ask Warren"
        case .settings: return "Settings"
        }
    }

    var systemImage: String {
        switch self {
        case .home: return "house.fill"
        case .research: return "building.columns"
        case .documents: return "doc.text.magnifyingglass"
        case .market: return "chart.line.uptrend.xyaxis"
        case .news: return "newspaper"
        case .pulse: return "waveform.path.ecg"
        case .copilot: return "bubble.left.and.bubble.right.fill"
        case .settings: return "gearshape"
        }
    }
}

struct MacRootView: View {
    @StateObject private var store = MacAppStore()
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @State private var showInspector = false
    @State private var showNewReportSheet = false

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // macOS Native Sidebar
            List(selection: $store.selectedTab) {
                Section("Desks") {
                    Label(MacTab.home.title, systemImage: MacTab.home.systemImage)
                        .tag(MacTab.home)

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
                    .keyboardShortcut("r", modifiers: .command)
                }
            }
        } detail: {
            HSplitView {
                Group {
                    switch store.selectedTab {
                    case .home:
                        MacHomeDeskView()
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
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    // Cache & Sync Status
                    if store.isOfflineMode {
                        HStack(spacing: 4) {
                            Circle().fill(Color.orange).frame(width: 6, height: 6)
                            Text("Offline Cache")
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(.secondary)
                        }
                    } else if let sync = store.lastSyncDate {
                        HStack(spacing: 4) {
                            Circle().fill(Color.green).frame(width: 6, height: 6)
                            Text("Synced \(sync, style: .time)")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        .help("Data hydrated and cached locally (sub-20ms startup)")
                    }

                    // Command Palette Spotlight Trigger
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            store.showCommandPalette = true
                        }
                    } label: {
                        Label("Command Palette", systemImage: "command")
                    }
                    .help("Open Command Palette & Global Search (⌘K)")

                    // Keyboard Shortcuts Sheet Trigger
                    Button {
                        store.showShortcutSheet = true
                    } label: {
                        Label("Shortcuts", systemImage: "questionmark.circle")
                    }
                    .help("Terminal Keyboard Shortcuts Cheat Sheet (?)")

                    // New Report Button
                    Button {
                        showNewReportSheet = true
                    } label: {
                        Label("New Report", systemImage: "plus.rectangle.on.rectangle")
                    }
                    .help("Generate New Investment Memo (⌘N)")
                    .keyboardShortcut("n", modifiers: .command)

                    // Embedded Browser Panel Toggle (Cursor Style)
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) {
                            store.showBrowserPanel.toggle()
                        }
                    } label: {
                        Label("Web Browser", systemImage: store.showBrowserPanel ? "globe.americas.fill" : "globe")
                    }
                    .help("Toggle Embedded Research Browser (⌘B)")
                    .keyboardShortcut("b", modifiers: .command)

                    // Open Web Portal directly
                    Button {
                        openWebPortal()
                    } label: {
                        Label("Open on Web", systemImage: "safari")
                    }
                    .help("Open Web Portal in Embedded Browser (⌘⇧W)")
                    .keyboardShortcut("w", modifiers: [.command, .shift])

                    // Inspector Toggle
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
        .navigationSplitViewStyle(.balanced)
        .environmentObject(store)
        .task {
            await store.bootstrap()
        }
        .sheet(isPresented: Binding(
            get: { store.openDocumentURL != nil && store.selectedTab != .documents },
            set: { if !$0 { store.closeMemo() } }
        )) {
            MacPaperDeskReader()
                .environmentObject(store)
        }
        .sheet(isPresented: $showNewReportSheet) {
            if let company = store.selectedCompany ?? store.companies.first {
                MacGenerateReportSheet(company: company) { newRep in
                    showNewReportSheet = false
                    store.openReportInViewer(newRep)
                }
                .environmentObject(store)
            } else {
                Text("Please register or select a company first.")
                    .padding()
            }
        }
        .sheet(isPresented: $store.showShortcutSheet) {
            MacShortcutOverlay()
        }
        .sheet(isPresented: $store.showDeckIntakeSheet) {
            MacPitchDeckIntakeSheet(fileURL: store.droppedDeckURL)
                .environmentObject(store)
        }
        .overlay {
            if store.showCommandPalette {
                MacCommandPalette(isPresented: $store.showCommandPalette)
                    .environmentObject(store)
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            }
        }
        // Keyboard shortcuts to jump between tabs & trigger overlays
        .background {
            Group {
                Button("") { store.selectedTab = .home }.keyboardShortcut("1", modifiers: .command)
                Button("") { store.selectedTab = .research }.keyboardShortcut("2", modifiers: .command)
                Button("") { store.selectedTab = .documents }.keyboardShortcut("3", modifiers: .command)
                Button("") { store.selectedTab = .market }.keyboardShortcut("4", modifiers: .command)
                Button("") { store.selectedTab = .news }.keyboardShortcut("5", modifiers: .command)
                Button("") { store.selectedTab = .pulse }.keyboardShortcut("6", modifiers: .command)
                Button("") { store.selectedTab = .copilot }.keyboardShortcut("7", modifiers: .command)
                Button("") {
                    withAnimation(.easeInOut(duration: 0.12)) {
                        store.showCommandPalette.toggle()
                    }
                }.keyboardShortcut("k", modifiers: .command)
                Button("") {
                    store.showShortcutSheet.toggle()
                }.keyboardShortcut("?", modifiers: [])
            }
            .opacity(0)
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

