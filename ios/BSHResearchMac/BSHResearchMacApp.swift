import SwiftUI
import UniformTypeIdentifiers

/// What the key window exposes to the menu bar: which company its commands act on and
/// how it presents the shared sheets. Windows that leave a closure nil fall back to the main window.
struct MacDeskCommandTarget {
    var companyId: String?
    var reportId: String?
    var commandPalette: (() -> Void)?
    var firmSearch: (() -> Void)?
    var newMemo: (() -> Void)?
    var shortcuts: (() -> Void)?
    var recordDecision: (() -> Void)?
    var openICReview: (() -> Void)?
}

struct MacDeskCommandTargetKey: FocusedValueKey {
    typealias Value = MacDeskCommandTarget
}

extension FocusedValues {
    var deskTarget: MacDeskCommandTarget? {
        get { self[MacDeskCommandTargetKey.self] }
        set { self[MacDeskCommandTargetKey.self] = newValue }
    }
}

final class MacAppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            for window in sender.windows {
                if window.canBecomeMain {
                    window.makeKeyAndOrderFront(nil)
                    return true
                }
            }
        }
        return true
    }
}

@main
struct BSHResearchMacApp: App {
    @NSApplicationDelegateAdaptor(MacAppDelegate.self) private var appDelegate
    /// One store for every window — desks, memo windows and Settings all read the same data.
    @StateObject private var store = MacAppStore()

    var body: some Scene {
        WindowGroup("BSH Research", id: "main") {
            MacRootView()
                .environmentObject(store)
                .frame(minWidth: 1050, minHeight: 680)
        }
        .windowToolbarStyle(.unified)
        .defaultSize(width: 1280, height: 820)
        .commands {
            SidebarCommands()
            InspectorCommands()
            MacDeskCommands(store: store)
        }

        MenuBarExtra {
            MacMenuBarExtraContent()
                .environmentObject(store)
        } label: {
            let s = store.menuBarSummary
            let badge = s.mentions + s.highHoldings
            Label(badge > 0 ? "BSH \(badge)" : "BSH", systemImage: badge > 0 ? "briefcase.fill" : "briefcase")
        }
        .menuBarExtraStyle(.menu)

        // One window per (report, language); reopening the same memo fronts its window.
        WindowGroup("Memo", id: "memo", for: MacMemoWindowRequest.self) { $request in
            if let request {
                MacMemoWindowView(request: request)
                    .environmentObject(store)
            }
        }
        .defaultSize(width: 980, height: 840)

        // IC Review: memo + thesis spine + evidence + decision form, one window per report.
        WindowGroup("IC Review", id: "ic", for: MacICReviewRequest.self) { $request in
            if let request {
                MacICReviewWindowView(request: request)
                    .environmentObject(store)
            }
        }
        .defaultSize(width: 1400, height: 880)

        Settings {
            MacSettingsView()
                .environmentObject(store)
        }
    }
}

/// Menu-bar commands. Sheet and company commands go to the key window's target;
/// with no target they front the main window and act there.
struct MacDeskCommands: Commands {
    @ObservedObject var store: MacAppStore
    @FocusedValue(\.deskTarget) private var target
    @Environment(\.openWindow) private var openWindow

    private var targetCompany: MacCompany? {
        if let target {
            guard let id = target.companyId else { return nil }
            return store.companies.first { $0.id == id }
        }
        return store.selectedCompany
    }

    private var targetReport: MacReport? {
        guard let company = targetCompany else { return nil }
        if let id = target?.reportId, let report = store.reports(for: company.id).first(where: { $0.id == id && $0.canOpen }) {
            return report
        }
        return store.reports(for: company.id).first(where: \.canOpen)
    }

    private func onMainWindow(_ action: @escaping () -> Void) {
        NSApp.activate(ignoringOtherApps: true)
        openWindow(id: "main")
        action()
    }

    private func route(_ local: (() -> Void)?, fallback: @escaping () -> Void) {
        if let local {
            local()
        } else {
            onMainWindow(fallback)
        }
    }

    var body: some Commands {
        CommandGroup(replacing: .newItem) {
            Button("New Window") {
                openWindow(id: "main")
            }
            .keyboardShortcut("n", modifiers: [.command, .shift])

            Button("New Investment Memo…") {
                route(target?.newMemo) { store.requestNewReport(for: targetCompany) }
            }
            .keyboardShortcut("n", modifiers: .command)
            .disabled(!store.canRunTasks)
        }

        CommandMenu("Go") {
            Button("Command Line…") {
                route(target?.commandPalette) { store.openCommandPalette() }
            }
            .keyboardShortcut("k", modifiers: .command)

            Button("Firm Memory Search…") {
                route(target?.firmSearch) { store.showFirmSearch = true }
            }
            .keyboardShortcut("f", modifiers: [.command, .shift])

            Divider()

            Button("Attention Queue") { store.selectedTab = .attention }
                .keyboardShortcut("0", modifiers: .command)
            Button("Home") { store.selectedTab = .home }
                .keyboardShortcut("1", modifiers: .command)
            Button("Pipeline") { store.selectedTab = .pipeline }
                .keyboardShortcut("2", modifiers: .command)
            Button("Research Desk") { store.selectedTab = .research }
                .keyboardShortcut("3", modifiers: .command)
            Button("Documents") { store.selectedTab = .documents }
                .keyboardShortcut("4", modifiers: .command)
            Button("Market Radar") { store.selectedTab = .market }
                .keyboardShortcut("5", modifiers: .command)
            Button("News Desk") { store.selectedTab = .news }
                .keyboardShortcut("6", modifiers: .command)
            Button("Market Pulse") { store.selectedTab = .pulse }
                .keyboardShortcut("7", modifiers: .command)
            Button("Portfolio & Watch") { store.selectedTab = .portfolio }
                .keyboardShortcut("8", modifiers: .command)
            Button("Ask Warren") { store.selectedTab = .copilot }
                .keyboardShortcut("9", modifiers: .command)

            Divider()

            Button(store.showBlotter ? "Hide Jobs & Alerts" : "Show Jobs & Alerts") {
                store.toggleBlotter()
            }
            .keyboardShortcut("j", modifiers: [.command, .option])

            Button("Signal Log…") {
                store.openSignalLog()
            }
            .keyboardShortcut("l", modifiers: .command)

            Button("Refresh All Desks") {
                Task { await store.bootstrap() }
            }
            .keyboardShortcut("r", modifiers: .command)

            Button("Keyboard Shortcuts") {
                route(target?.shortcuts) { store.showShortcutSheet = true }
            }
            .keyboardShortcut("/", modifiers: .command)
        }

        CommandMenu("Deal") {
            Button("Record Decision…") {
                let company = targetCompany
                let reportId = target?.reportId
                route(target?.recordDecision) {
                    if let company { store.requestDecision(for: company, reportId: reportId) }
                }
            }
            .keyboardShortcut("d", modifiers: .command)
            .disabled(!store.canRunTasks || targetCompany == nil)

            Button("Open IC Review") {
                if let local = target?.openICReview {
                    local()
                } else if let report = targetReport {
                    store.openICReview(report: report)
                }
            }
            .keyboardShortcut("o", modifiers: [.command, .shift])
            .disabled(target?.openICReview == nil && targetReport == nil)

            Button(targetCompany.map { store.isFollowed($0.id) } == true ? "Unfollow Company" : "Follow Company") {
                if let company = targetCompany {
                    Task { await store.toggleFollow(company.id) }
                }
            }
            .disabled(!store.canRunTasks || targetCompany == nil)

            Button("Intake Pitch Deck…") {
                let panel = NSOpenPanel()
                panel.allowsMultipleSelection = false
                panel.canChooseDirectories = false
                panel.allowedContentTypes = [
                    .pdf,
                    UTType("org.openxmlformats.presentationml.presentation"),
                    UTType("com.microsoft.powerpoint.ppt"),
                ].compactMap { $0 }
                if panel.runModal() == .OK, let url = panel.url {
                    store.ingestDeck(url: url)
                }
            }
            .disabled(!store.canEditSources)

            Divider()

            Button("Sync All Tracked News") {
                store.syncAllTracking()
            }
            .disabled(!store.canRunTasks || store.pipelineSyncing || store.validFollowedIds.isEmpty)
        }

        CommandMenu("Account") {
            if let session = store.session, !session.isAnonDev {
                Text("\(session.displayName) · \(session.roleLabel)")
                Button("Sign Out") {
                    Task { await store.signOut() }
                }
            } else {
                if let session = store.session {
                    Text("\(session.displayName) · \(session.roleLabel)")
                }
                Button("Sign In…") {
                    onMainWindow { store.showLoginSheet = true }
                }
            }
        }

        CommandMenu("Workspaces") {
            Button("Save Current Layout…") {
                MacWorkspacePrompt.ask { name in store.saveWorkspace(named: name) }
            }
            .keyboardShortcut("s", modifiers: [.command, .option])
            if store.workspaces.isEmpty {
                Text("No saved layouts")
            } else {
                Divider()
                ForEach(Array(store.workspaces.prefix(9).enumerated()), id: \.element.id) { index, ws in
                    Button(ws.name) { store.restoreWorkspace(ws) }
                        .keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: [.command, .option])
                }
                Divider()
                Menu("Delete Layout") {
                    ForEach(store.workspaces) { ws in
                        Button(ws.name) { store.deleteWorkspace(ws) }
                    }
                }
            }
        }

        CommandMenu("Web") {
            Button(store.showBrowserPanel ? "Hide Research Browser" : "Show Research Browser") {
                withAnimation(.easeInOut(duration: 0.18)) { store.showBrowserPanel.toggle() }
            }
            .keyboardShortcut("b", modifiers: .command)

            Button(store.showCopilotPanel ? "Hide Ask Warren Side Panel" : "Show Ask Warren Side Panel") {
                withAnimation(.easeInOut(duration: 0.18)) { store.showCopilotPanel.toggle() }
            }
            .keyboardShortcut("c", modifiers: [.command, .option])

            Button("Open Current Page on Web") {
                MacConfig.openInBrowser(store.currentWebURL)
            }
            .keyboardShortcut("w", modifiers: [.command, .shift])

            Button("Open Research Portal on Web") {
                MacConfig.openInBrowser(MacConfig.baseURL)
            }
        }
    }
}
