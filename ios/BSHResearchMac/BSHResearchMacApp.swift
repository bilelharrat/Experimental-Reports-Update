import SwiftUI

@main
struct BSHResearchMacApp: App {
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

            CommandGroup(replacing: .newItem) {
                Button("New Investment Memo…") {
                    store.requestNewReport()
                }
                .keyboardShortcut("n", modifiers: .command)
                .disabled(!store.canRunTasks)
            }

            CommandMenu("Go") {
                Button("Command Line…") {
                    store.openCommandPalette()
                }
                .keyboardShortcut("k", modifiers: .command)

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
            }

            CommandMenu("Deal") {
                Button("Record Decision…") {
                    if let company = store.selectedCompany { store.requestDecision(for: company) }
                }
                .keyboardShortcut("d", modifiers: .command)
                .disabled(!store.canRunTasks || store.selectedCompany == nil)

                Button("Open IC Review") {
                    if let company = store.selectedCompany,
                       let report = store.reports(for: company.id).first(where: \.canOpen) {
                        store.openICReview(report: report)
                    }
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])
                .disabled(store.selectedCompany.map { store.reports(for: $0.id).contains(where: \.canOpen) } != true)

                Button(store.selectedCompany.map { store.isFollowed($0.id) } == true ? "Unfollow Company" : "Follow Company") {
                    if let company = store.selectedCompany {
                        Task { await store.toggleFollow(company.id) }
                    }
                }
                .disabled(!store.canRunTasks || store.selectedCompany == nil)

                Divider()

                Button("Sync All Tracked News") {
                    store.syncAllTracking()
                }
                .disabled(!store.canRunTasks || store.pipelineSyncing)
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
                        store.showLoginSheet = true
                    }
                }
            }

            CommandMenu("Web") {
                Button("Open Research Portal on Web") {
                    MacConfig.openInBrowser(MacConfig.baseURL)
                }
                .keyboardShortcut("w", modifiers: [.command, .shift])
            }
        }

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
