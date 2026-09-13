import SwiftUI

@main
struct BSHResearchMacApp: App {
    var body: some Scene {
        WindowGroup("BSH Research") {
            MacRootView()
                .frame(minWidth: 1050, minHeight: 680)
        }
        .windowToolbarStyle(.unified)
        .defaultSize(width: 1280, height: 820)
        .commands {
            SidebarCommands()
            InspectorCommands()

            CommandGroup(replacing: .newItem) {
                Button("New Investment Report…") {
                    // Handled by window toolbar and ⌘N
                }
                .keyboardShortcut("n", modifiers: .command)
            }

            CommandMenu("Desks") {
                Button("Home") {
                    // ⌘1 handled in MacRootView
                }
                .keyboardShortcut("1", modifiers: .command)

                Button("Research Desk") {
                    // ⌘2 handled in MacRootView
                }
                .keyboardShortcut("2", modifiers: .command)

                Button("Documents") {
                    // ⌘3 handled in MacRootView
                }
                .keyboardShortcut("3", modifiers: .command)

                Button("Market Radar") {
                    // ⌘4 handled in MacRootView
                }
                .keyboardShortcut("4", modifiers: .command)

                Button("News Desk") {
                    // ⌘5 handled in MacRootView
                }
                .keyboardShortcut("5", modifiers: .command)

                Button("Market Pulse") {
                    // ⌘6 handled in MacRootView
                }
                .keyboardShortcut("6", modifiers: .command)

                Button("Ask Warren (Copilot)") {
                    // ⌘7 handled in MacRootView
                }
                .keyboardShortcut("7", modifiers: .command)
            }

            CommandMenu("Web") {
                Button("Open Research Portal on Web") {
                    MacConfig.openInBrowser(MacConfig.baseURL)
                }
                .keyboardShortcut("w", modifiers: [.command, .shift])
            }
        }

        Settings {
            MacSettingsView()
                .environmentObject(MacAppStore())
        }
    }
}
