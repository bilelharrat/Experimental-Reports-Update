import SwiftUI
import UIKit

struct RootView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        Group {
            if session.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: session.isAuthenticated)
    }
}

struct MainTabView: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var router: DeepLinkRouter
    @State private var selection: AppTab = .home
    @State private var showSettings = false
    /// Measured window size — never wrap TabView in GeometryReader (that breaks
    /// the system tab bar safe-area / placement on iPad).
    @State private var windowSize: CGSize = .zero
    /// Stored so orientation + size changes both force chrome recomputation.
    @State private var useSidebar = false

    var body: some View {
        Group {
            if useSidebar {
                MainSidebarChrome(selection: $selection)
            } else {
                // Exact iPhone tab tree — no rail, no split remnants.
                phoneTabs
                    .environment(\.embeddedInRootSplit, false)
            }
        }
        .background {
            GeometryReader { geo in
                Color.clear
                    .preference(key: RootWindowSizeKey.self, value: geo.size)
            }
            .ignoresSafeArea()
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .bshSheetChrome()
        }
        .onPreferenceChange(RootWindowSizeKey.self) { size in
            guard size.width > 0, size.height > 0 else { return }
            windowSize = size
            recomputeChrome()
        }
        .onAppear {
            UIDevice.current.beginGeneratingDeviceOrientationNotifications()
            recomputeChrome()
        }
        .onReceive(NotificationCenter.default.publisher(
            for: UIDevice.orientationDidChangeNotification
        )) { _ in
            // Orientation can flip before GeometryReader reports a new size.
            recomputeChrome()
        }
        .onChange(of: router.pending) { _, link in
            switch link {
            case .none:
                break
            case .tab(let target):
                router.pending = nil
                selection = target
            case .report:
                selection = .reports
            case .settings:
                router.pending = nil
                showSettings = true
            default:
                // Home owns the record destinations; make sure it's frontmost.
                selection = .home
            }
        }
    }

    private func recomputeChrome() {
        let next = AdaptiveLayout.prefersRootSidebar(
            width: windowSize.width,
            height: windowSize.height
        )
        if next != useSidebar {
            useSidebar = next
        }
    }

    /// Same bottom TabView chrome for iPhone and portrait iPad.
    ///
    /// iPadOS 18+ defaults TabView to a floating **top** pill (and can morph into
    /// a sidebar). That is exactly the broken portrait chrome. Force the classic
    /// bottom tab bar by pinning a compact horizontal size class — same tree as
    /// iPhone, icons + labels under the content.
    @ViewBuilder
    private var phoneTabs: some View {
        if #available(iOS 18.0, *) {
            phoneTabView.tabViewStyle(.tabBarOnly)
        } else {
            phoneTabView
        }
    }

    private var phoneTabView: some View {
        TabView(selection: $selection) {
            HomeView()
                .tabItem { Label(language.t("tab.home"), systemImage: "house") }
                .tag(AppTab.home)
            ReportsDeskView()
                .tabItem { Label(language.t("tab.reports"), systemImage: "doc.text") }
                .tag(AppTab.reports)
            NewsView()
                .tabItem { Label(language.t("tab.news"), systemImage: "newspaper") }
                .tag(AppTab.news)
            PulseView()
                .tabItem {
                    Label {
                        Text(language.t("tab.pulse"))
                    } icon: {
                        Image(uiImage: PulseECGTabIcon.image)
                    }
                }
                .tag(AppTab.pulse)
            MarketView()
                .tabItem { Label(language.t("tab.market"), systemImage: "chart.line.uptrend.xyaxis") }
                .tag(AppTab.market)
        }
        .toolbar(.visible, for: .tabBar)
        // Compact size class is what makes iPadOS 18+ render a bottom tab bar
        // identical to iPhone (instead of the floating top pill).
        .environment(\.horizontalSizeClass, .compact)
    }
}

private struct RootWindowSizeKey: PreferenceKey {
    static var defaultValue: CGSize = .zero
    static func reduce(value: inout CGSize, nextValue: () -> CGSize) {
        let next = nextValue()
        if next.width > 0, next.height > 0 {
            value = next
        }
    }
}

/// Landscape iPad root: custom expand/collapse rail (never NavigationSplitView hide-all).
private struct MainSidebarChrome: View {
    @EnvironmentObject private var language: LanguageStore
    @Binding var selection: AppTab
    @AppStorage("bsh.rootSidebarExpanded") private var isExpanded = true

    var body: some View {
        HStack(spacing: 0) {
            RootSidebarRail(
                selection: $selection,
                isExpanded: $isExpanded
            )
            .frame(width: isExpanded
                ? AdaptiveLayout.rootSidebarExpanded
                : AdaptiveLayout.rootSidebarRail)
            .animation(.easeInOut(duration: 0.22), value: isExpanded)

            Divider()

            detail(for: selection)
                .id(selection)
                .environment(\.embeddedInRootSplit, true)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(.systemBackground))
    }

    @ViewBuilder
    private func detail(for tab: AppTab) -> some View {
        switch tab {
        case .home:
            HomeView()
        case .reports:
            ReportsDeskView()
        case .news:
            NewsView()
        case .pulse:
            PulseView()
        case .market:
            MarketView()
        }
    }
}

/// Web-like source-list rail: expanded = icons+labels; collapsed = narrow icon peek.
private struct RootSidebarRail: View {
    @EnvironmentObject private var language: LanguageStore
    @Binding var selection: AppTab
    @Binding var isExpanded: Bool
    @State private var showSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            header
            ForEach(AppTab.allCases) { tab in
                sidebarRow(tab)
            }
            Spacer(minLength: 0)
            settingsButton
        }
        .padding(.horizontal, isExpanded ? 10 : 8)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color(.secondarySystemBackground).opacity(0.72))
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .bshSheetChrome()
        }
    }

    private var settingsButton: some View {
        Button {
            showSettings = true
        } label: {
            HStack(spacing: isExpanded ? 10 : 0) {
                Image(systemName: "gearshape")
                    .font(.body)
                    .frame(width: 22, height: 22)
                if isExpanded {
                    Text(language.t("tab.settings"))
                        .font(.callout)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .foregroundStyle(Color.secondary)
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.t("tab.settings"))
    }

    private var header: some View {
        HStack(spacing: 8) {
            if isExpanded {
                Text(language.t("app.name"))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button {
                isExpanded.toggle()
            } label: {
                // Matches web PanelLeft / PanelLeftClose: rail peek vs collapse.
                Image(systemName: isExpanded
                      ? "rectangle.lefthalf.inset.filled"
                      : "sidebar.left")
                    .font(.body.weight(.medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(
                language.t(isExpanded ? "sidebar.collapse" : "sidebar.expand")
            )
            .frame(maxWidth: isExpanded ? nil : .infinity)
        }
        .padding(.bottom, 6)
    }

    private func sidebarRow(_ tab: AppTab) -> some View {
        let selected = selection == tab
        return Button {
            selection = tab
        } label: {
            HStack(spacing: isExpanded ? 10 : 0) {
                tabIcon(tab, selected: selected)
                    .frame(width: 22, height: 22)
                if isExpanded {
                    Text(language.t(tab.titleKey))
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
        .accessibilityLabel(language.t(tab.titleKey))
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    @ViewBuilder
    private func tabIcon(_ tab: AppTab, selected: Bool) -> some View {
        if let symbol = tab.systemImage {
            Image(systemName: symbol)
                .font(.body.weight(selected ? .semibold : .regular))
                .symbolRenderingMode(.monochrome)
        } else {
            Image(uiImage: PulseECGTabIcon.makeImage(pointSize: 18))
                .resizable()
                .renderingMode(.template)
                .scaledToFit()
        }
    }
}
