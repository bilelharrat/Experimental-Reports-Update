import SwiftUI

struct MacShortcutOverlay: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "command")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(Color.accentColor)
                    Text("Terminal Keyboard Shortcuts")
                        .font(.title3.weight(.bold))
                }

                Spacer()

                Button("Done") {
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .background(.ultraThinMaterial)

            Divider()

            ScrollView {
                VStack(spacing: 20) {
                    // Terminal & Navigation Section
                    ShortcutSection(title: "Terminal & Spotlight", icon: "terminal.fill") {
                        ShortcutRow(keys: ["⌘", "K"], description: "Open Command Palette / Spotlight")
                        ShortcutRow(keys: ["/"], description: "Quick Filter / Search Bar")
                        ShortcutRow(keys: ["?"], description: "Show Keyboard Shortcuts Cheat Sheet")
                        ShortcutRow(keys: ["↑", "↓"], description: "Navigate list rows & results")
                        ShortcutRow(keys: ["⏎"], description: "Select or execute highlighted row")
                        ShortcutRow(keys: ["Space"], description: "Quick Look preview on selected memo")
                        ShortcutRow(keys: ["Esc"], description: "Dismiss palettes & popovers")
                    }

                    // Desk Switching
                    ShortcutSection(title: "Desk Navigation", icon: "square.grid.2x2") {
                        ShortcutRow(keys: ["⌘", "1"], description: "Home Desk (Portfolio Overview)")
                        ShortcutRow(keys: ["⌘", "2"], description: "Research Desk (Company Dossiers)")
                        ShortcutRow(keys: ["⌘", "3"], description: "Documents Desk (Memo Viewer)")
                        ShortcutRow(keys: ["⌘", "4"], description: "Market Radar (Blotter & Comps)")
                        ShortcutRow(keys: ["⌘", "5"], description: "News Desk (Market Intelligence)")
                        ShortcutRow(keys: ["⌘", "6"], description: "Market Pulse (Signals & Regime)")
                        ShortcutRow(keys: ["⌘", "7"], description: "Ask Warren (AI Investment Copilot)")
                    }

                    // Workflow Actions
                    ShortcutSection(title: "Institutional Workflows", icon: "bolt.fill") {
                        ShortcutRow(keys: ["⌘", "N"], description: "Generate New Investment Memo")
                        ShortcutRow(keys: ["⌘", "R"], description: "Refresh All Desks & Sync Cache")
                        ShortcutRow(keys: ["⌘", "B"], description: "Toggle Embedded Web Browser")
                        ShortcutRow(keys: ["⌥", "⌘", "I"], description: "Toggle Inspector Sidebar")
                        ShortcutRow(keys: ["⇧", "⌘", "W"], description: "Open Current Asset on Web Portal")
                    }
                }
                .padding(20)
            }
            .frame(maxHeight: 460)

            Divider()

            // Footer
            HStack {
                Text("BSH Research Terminal Edition · Apple Human Interface Guidelines")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial)
        }
        .frame(width: 520)
        .appleGlassCard(cornerRadius: 18)
    }
}

private struct ShortcutSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Color.accentColor)
                Text(title.uppercased())
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 6) {
                content()
            }
            .padding(12)
            .appleGlassTile(cornerRadius: 12)
        }
    }
}

private struct ShortcutRow: View {
    let keys: [String]
    let description: String

    var body: some View {
        HStack {
            Text(description)
                .font(.system(size: 13))
            Spacer()
            HStack(spacing: 4) {
                ForEach(keys, id: \.self) { key in
                    KeyCapView(key: key)
                }
            }
        }
    }
}

private struct KeyCapView: View {
    let key: String

    var body: some View {
        Text(key)
            .font(.system(size: 11, weight: .semibold, design: .monospaced))
            .foregroundStyle(.primary)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .appleGlassTile(cornerRadius: 4)
    }
}
