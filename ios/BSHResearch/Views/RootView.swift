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
    @State private var selection: AppTab = {
        if let tabArg = ProcessInfo.processInfo.environment["BSH_INITIAL_TAB"],
           let tab = AppTab(rawValue: tabArg.lowercased()) {
            return tab
        }
        return .home
    }()
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
        .onChange(of: router.pending) {
            let link = router.pending
            switch link {
            case .none:
                break
            case .tab(let target):
                router.pending = nil
                selection = target
            case .company(let cid):
                router.pending = nil
                selection = .research
                Task {
                    await ResearchDeskStore.shared.selectCompany(id: cid)
                }
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
            MacResearchDeskView()
                .tabItem { Label(language.t("tab.research"), systemImage: "building.2") }
                .tag(AppTab.research)
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
        case .research:
            MacResearchDeskView()
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

/// Liquid Glass surface for selected sidebar items, matching macOS and Web.
private struct SidebarGlassPill: View {
    var cornerRadius: CGFloat = 10
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let isDark = colorScheme == .dark
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        ZStack {
            // Material blur + lift fill
            shape
                .fill(.regularMaterial)
                .overlay(
                    shape.fill(Color.white.opacity(isDark ? 0.10 : 0.65))
                )

            // Specular top rim highlight (crisp white along top, softer toward bottom)
            shape
                .strokeBorder(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(isDark ? 0.28 : 0.95),
                            Color.white.opacity(isDark ? 0.05 : 0.40)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 0.5
                )

            // Hairline perimeter border for edge contrast over sidebar background
            shape
                .strokeBorder(
                    Color.black.opacity(isDark ? 0.45 : 0.07),
                    lineWidth: 0.5
                )
        }
        // Tight contact shadow
        .shadow(
            color: Color.black.opacity(isDark ? 0.35 : 0.04),
            radius: 1,
            x: 0,
            y: 0.5
        )
        // Soft levitating ambient drop shadow
        .shadow(
            color: Color.black.opacity(isDark ? 0.50 : 0.11),
            radius: 5,
            x: 0,
            y: 2
        )
    }
}

/// Web-like source-list rail: expanded = icons+labels; collapsed = narrow icon peek.
private struct RootSidebarRail: View {
    @EnvironmentObject private var language: LanguageStore
    @Binding var selection: AppTab
    @Binding var isExpanded: Bool
    @State private var showSettings = false
    @State private var hoveredTab: AppTab? = nil
    @State private var isSettingsHovered = false
    @State private var isHeaderToggleHovered = false
    @Namespace private var sidebarNamespace

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            header

            if isExpanded {
                Text(language.t("sidebar.desks"))
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(Color.secondary)
                    .padding(.horizontal, 10)
                    .padding(.top, 8)
                    .padding(.bottom, 2)
            }

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
        .background {
            ZStack {
                Color(.systemBackground).opacity(0.70)
                Rectangle().fill(.ultraThinMaterial)
            }
            .ignoresSafeArea()
        }
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
                        .font(.callout.weight(isSettingsHovered ? .medium : .regular))
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .foregroundStyle(isSettingsHovered ? Color.primary : Color.secondary)
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
            .background {
                if isSettingsHovered {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color.primary.opacity(0.045))
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { inside in
            withAnimation(.easeInOut(duration: 0.15)) {
                isSettingsHovered = inside
            }
        }
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
                withAnimation(.easeInOut(duration: 0.22)) {
                    isExpanded.toggle()
                }
            } label: {
                // Matches web PanelLeft / PanelLeftClose: rail peek vs collapse.
                Image(systemName: isExpanded
                      ? "rectangle.lefthalf.inset.filled"
                      : "sidebar.left")
                    .font(.body.weight(.medium))
                    .foregroundStyle(isHeaderToggleHovered ? Color.primary : Color.secondary)
                    .frame(width: 32, height: 32)
                    .background {
                        if isHeaderToggleHovered {
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color.primary.opacity(0.045))
                        }
                    }
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .onHover { inside in
                withAnimation(.easeInOut(duration: 0.15)) {
                    isHeaderToggleHovered = inside
                }
            }
            .accessibilityLabel(
                language.t(isExpanded ? "sidebar.collapse" : "sidebar.expand")
            )
            .frame(maxWidth: isExpanded ? nil : .infinity)
        }
        .padding(.horizontal, isExpanded ? 6 : 0)
        .padding(.bottom, 4)
    }

    private func sidebarRow(_ tab: AppTab) -> some View {
        let selected = selection == tab
        let hovered = hoveredTab == tab && !selected
        return Button {
            withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
                selection = tab
            }
        } label: {
            HStack(spacing: isExpanded ? 10 : 0) {
                tabIcon(tab, selected: selected, hovered: hovered)
                    .frame(width: 22, height: 22)
                if isExpanded {
                    Text(language.t(tab.titleKey))
                        .font(.callout.weight(selected ? .semibold : (hovered ? .medium : .regular)))
                        .foregroundStyle(selected ? Color.primary : (hovered ? Color.primary : Color.secondary))
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
            .background {
                if selected {
                    SidebarGlassPill(cornerRadius: 10)
                        .matchedGeometryEffect(id: "activeSidebarPill", in: sidebarNamespace)
                } else if hovered {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color.primary.opacity(0.045))
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { isHovered in
            withAnimation(.easeInOut(duration: 0.15)) {
                if isHovered {
                    hoveredTab = tab
                } else if hoveredTab == tab {
                    hoveredTab = nil
                }
            }
        }
        .accessibilityLabel(language.t(tab.titleKey))
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    @ViewBuilder
    private func tabIcon(_ tab: AppTab, selected: Bool, hovered: Bool) -> some View {
        let iconColor: Color = selected ? Color.accentColor : (hovered ? Color.primary : Color.secondary)
        if let symbol = tab.systemImage {
            Image(systemName: symbol)
                .font(.body.weight(selected ? .semibold : .regular))
                .foregroundStyle(iconColor)
        } else {
            Image(uiImage: PulseECGTabIcon.makeImage(pointSize: 18))
                .resizable()
                .renderingMode(.template)
                .scaledToFit()
                .foregroundStyle(iconColor)
        }
    }
}
