import SwiftUI

enum MacTab: String, CaseIterable, Identifiable, Hashable {
    case home, news, market, pulse, settings
    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: return "Home"
        case .news: return "News"
        case .market: return "Market"
        case .pulse: return "Pulse"
        case .settings: return "Settings"
        }
    }

    var systemImage: String? {
        switch self {
        case .home: return "house"
        case .news: return "newspaper"
        case .market: return "chart.line.uptrend.xyaxis"
        case .pulse: return nil
        case .settings: return "gearshape"
        }
    }
}

/// Same landscape chrome as iPad `MainSidebarChrome` — icon rail + detail.
struct MacRootView: View {
    @StateObject private var store = MacAppStore()
    @State private var selection: MacTab = .home
    @AppStorage("bsh.rootSidebarExpanded") private var isExpanded = true

    var body: some View {
        HStack(spacing: 0) {
            MacSidebarRail(selection: $selection, isExpanded: $isExpanded)
                .frame(width: isExpanded ? 240 : 64)
                .animation(.easeInOut(duration: 0.22), value: isExpanded)

            Divider()

            detail(for: selection)
                .id(selection)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .environmentObject(store)
        .background(Color(nsColor: .windowBackgroundColor))
        .task { await store.bootstrap() }
    }

    @ViewBuilder
    private func detail(for tab: MacTab) -> some View {
        NavigationStack {
            switch tab {
            case .home:
                MacHomeView()
            case .news:
                MacNewsTabView()
            case .market:
                MacMarketTabView()
            case .pulse:
                MacPulseTabView()
            case .settings:
                MacSettingsTabView()
            }
        }
    }
}

private struct MacSidebarRail: View {
    @Binding var selection: MacTab
    @Binding var isExpanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                if isExpanded {
                    Text("BSH Research")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Button {
                    isExpanded.toggle()
                } label: {
                    Image(systemName: isExpanded
                          ? "rectangle.lefthalf.inset.filled"
                          : "sidebar.left")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.secondary)
                        .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .frame(maxWidth: isExpanded ? nil : .infinity)
            }
            .padding(.bottom, 6)

            ForEach(MacTab.allCases) { tab in
                railRow(tab)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, isExpanded ? 10 : 8)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.72))
    }

    private func railRow(_ tab: MacTab) -> some View {
        let selected = selection == tab
        return Button {
            selection = tab
        } label: {
            HStack(spacing: isExpanded ? 10 : 0) {
                Group {
                    if let symbol = tab.systemImage {
                        Image(systemName: symbol)
                            .font(.body.weight(selected ? .semibold : .regular))
                    } else {
                        MacPulseECGIcon()
                            .frame(width: 18, height: 14)
                    }
                }
                .frame(width: 22, height: 22)

                if isExpanded {
                    Text(tab.title)
                        .font(.callout.weight(selected ? .semibold : .regular))
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .foregroundStyle(selected ? Color.accentColor : Color.secondary)
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
            .background {
                if selected {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color.accentColor.opacity(0.14))
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

/// Tiny ECG glyph for Pulse (same role as iOS PulseECGTabIcon).
struct MacPulseECGIcon: View {
    var body: some View {
        Canvas { ctx, size in
            var path = Path()
            let midY = size.height * 0.55
            path.move(to: CGPoint(x: 0, y: midY))
            path.addLine(to: CGPoint(x: size.width * 0.22, y: midY))
            path.addLine(to: CGPoint(x: size.width * 0.32, y: size.height * 0.15))
            path.addLine(to: CGPoint(x: size.width * 0.42, y: size.height * 0.85))
            path.addLine(to: CGPoint(x: size.width * 0.52, y: size.height * 0.35))
            path.addLine(to: CGPoint(x: size.width * 0.62, y: midY))
            path.addLine(to: CGPoint(x: size.width, y: midY))
            ctx.stroke(path, with: .foreground, style: StrokeStyle(lineWidth: 1.6, lineJoin: .round))
        }
    }
}
