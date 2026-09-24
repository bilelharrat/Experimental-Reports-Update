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
    @EnvironmentObject private var welcomeTour: WelcomeTourStore
    @State private var selection: AppTab = {
        if let tabArg = ProcessInfo.processInfo.environment["BSH_INITIAL_TAB"],
           let tab = AppTab(rawValue: tabArg.lowercased()) {
            return tab
        }
        return .home
    }()
    @EnvironmentObject private var settings: SettingsPresenter
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
        // The tour rides over the app instead of covering it: each step moves
        // the real tab and rings the real control.
        .welcomeTourOverlay()
        .onChange(of: welcomeTour.stepIndex) { _, _ in followTour() }
        .onChange(of: welcomeTour.isPresented) { _, presented in
            if presented { followTour() }
        }
        .onPreferenceChange(RootWindowSizeKey.self) { size in
            guard size.width > 0, size.height > 0 else { return }
            windowSize = size
            recomputeChrome()
        }
        .onAppear {
            UIDevice.current.beginGeneratingDeviceOrientationNotifications()
            recomputeChrome()
            welcomeTour.presentIfNeeded()
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
                settings.isPresented = true
            default:
                // Home owns the record destinations; make sure it's frontmost.
                selection = .home
            }
        }
    }

    /// Put the app on the desk the current tour step is talking about.
    private func followTour() {
        guard welcomeTour.isPresented, let tab = welcomeTour.focusedTab, selection != tab else { return }
        withAnimation(.spring(response: 0.34, dampingFraction: 0.82)) {
            selection = tab
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
        welcomeTour.refreshLayout(isPad: AdaptiveLayout.isPad)
    }

    /// Navigation chrome for iPhone and portrait iPad.
    ///
    /// On iPadOS (vertical / portrait mode):
    /// Uses native TabView. In regular horizontal size class, iPadOS 18 renders
    /// Apple's native floating glass capsule ("the travel bar") at the top with
    /// all 6 tabs (Home, Research, Reports, News, Pulse, Market) directly accessible
    /// without a "••• More" tab.
    ///
    /// On iPhone:
    /// Uses the same TabView content tree, paired with UIKit's native glass UITabBar
    /// at the bottom. This bypasses the UIKit 5-tab compact cutoff while retaining
    /// Apple's authentic system glass materials, blur, specular highlights, and active accents.
    init() {
        UITabBar.appearance().isHidden = true
    }

    /// Navigation chrome for iPhone and portrait iPad, in the chosen design: Summit's
    /// floating glass bar, Folio's ruled paper bar, or Bureau's page resting on the desk.
    @ViewBuilder
    private var phoneTabs: some View {
        switch BSHDesign.active {
        case .glass: glassPhoneTabs
        case .folio: folioPhoneTabs
        case .bureau: bureauPhoneTabs
        }
    }

    /// Bureau: the desks are one page resting on the green desk; the desk bar below is
    /// written on the green, and the chosen desk is a tab cut from the page's bottom edge.
    private var bureauPhoneTabs: some View {
        VStack(spacing: 0) {
            phoneTabView
                .bureauPage()

            BureauDeskBar(selection: $selection)
                .frame(maxWidth: 620)
        }
        // Like the glass bar, the desk stays put under the keyboard.
        .ignoresSafeArea(.keyboard, edges: .bottom)
        .background(BSHPalette.bureauFrame.ignoresSafeArea())
    }

    /// Folio: the desks on paper, the bar ruled off below them.
    private var folioPhoneTabs: some View {
        VStack(spacing: 0) {
            phoneTabView

            Rectangle()
                .fill(Color.dsHairline)
                .frame(height: 1)

            FolioDeskBar(selection: $selection)
                .frame(maxWidth: 620)
        }
        .ignoresSafeArea(.keyboard, edges: .bottom)
        .background(Color.dsCanvas.ignoresSafeArea())
    }

    /// Summit Glass: Apple's Liquid Glass floating travel bar capsule with all 6 desks
    /// (Home, Research, Reports, News, Pulse, Market) directly accessible.
    /// Eliminates the "••• More" tab on both iPadOS (vertical/portrait mode) and iOS.
    private var glassPhoneTabs: some View {
        ZStack(alignment: .bottom) {
            phoneTabView
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    Color.clear.frame(height: 68)
                }
                .ignoresSafeArea(.keyboard, edges: .bottom)

            FloatingTravelGlassBar(selection: $selection)
                .frame(maxWidth: 580)
                .padding(.horizontal, 16)
                .padding(.bottom, 10)
                .ignoresSafeArea(.keyboard, edges: .bottom)
        }
    }

    private var phoneTabView: some View {
        TabView(selection: $selection) {
            HomeView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.home)
            MacResearchDeskView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.research)
            ReportsDeskView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.reports)
            NewsView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.news)
            PulseView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.pulse)
            MarketView()
                .toolbar(.hidden, for: .tabBar)
                .tag(AppTab.market)
        }
    }
}

/// Floating Apple Liquid Glass travel bar for iPadOS (portrait) and iOS.
/// Retains Apple's canonical glass materials, specular rim highlight, contact shadow,
/// ambient elevation drop shadow, and active tab glass pill.
/// Displays all 6 desks directly without a "••• More" button.
private struct FloatingTravelGlassBar: View {
    @Binding var selection: AppTab
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.colorScheme) private var colorScheme
    @Namespace private var travelBarNamespace

    var body: some View {
        let isDark = colorScheme == .dark
        HStack(spacing: 2) {
            ForEach(AppTab.allCases) { tab in
                tabButton(tab, isDark: isDark)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
        .background {
            ZStack {
                // Liquid glass base material blur
                Capsule()
                    .fill(.regularMaterial)

                // Translucent specular lift fill
                Capsule()
                    .fill(Color.white.opacity(isDark ? 0.08 : 0.65))

                // Top specular rim highlight
                Capsule()
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(isDark ? 0.35 : 0.95),
                                Color.white.opacity(isDark ? 0.05 : 0.35)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 0.5
                    )

                // Hairline contrast perimeter
                Capsule()
                    .strokeBorder(
                        Color.black.opacity(isDark ? 0.40 : 0.06),
                        lineWidth: 0.5
                    )
            }
            // Tight contact shadow
            .shadow(
                color: Color.black.opacity(isDark ? 0.35 : 0.06),
                radius: 1,
                x: 0,
                y: 1
            )
            // Floating ambient drop shadow
            .shadow(
                color: Color.black.opacity(isDark ? 0.45 : 0.12),
                radius: 12,
                x: 0,
                y: 4
            )
        }
    }

    private func tabButton(_ tab: AppTab, isDark: Bool) -> some View {
        let isSelected = selection == tab
        return Button {
            if selection != tab {
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                withAnimation(.spring(response: 0.32, dampingFraction: 0.76)) {
                    selection = tab
                }
            }
        } label: {
            VStack(spacing: 2) {
                tabIcon(tab, selected: isSelected)
                    .frame(height: 20)
                Text(language.t(tab.titleKey))
                    .font(.system(size: 10, weight: isSelected ? .semibold : .medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.70)
            }
            .foregroundStyle(isSelected ? Color.dsAccent : Color.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity)
            .welcomeTourAnchor(WelcomeTourCatalog.tabAnchor(tab))
            .background {
                if isSelected {
                    Capsule()
                        .fill(Color.dsAccent.opacity(isDark ? 0.20 : 0.12))
                        .overlay(
                            Capsule()
                                .strokeBorder(Color.dsAccent.opacity(isDark ? 0.35 : 0.25), lineWidth: 0.5)
                        )
                        .matchedGeometryEffect(id: "activeTravelPill", in: travelBarNamespace)
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.t(tab.titleKey))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    @ViewBuilder
    private func tabIcon(_ tab: AppTab, selected: Bool) -> some View {
        let color = selected ? Color.dsAccent : Color.secondary
        if let symbol = tab.systemImage {
            Image(systemName: symbol)
                .font(.system(size: 16, weight: selected ? .semibold : .regular))
                .foregroundStyle(color)
        } else {
            Image(uiImage: PulseECGTabIcon.makeImage(pointSize: 16))
                .resizable()
                .renderingMode(.template)
                .scaledToFit()
                .frame(width: 20, height: 16)
                .foregroundStyle(color)
        }
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
    @Environment(\.colorScheme) private var colorScheme
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
            // Bureau's chosen row reaches into the page: draw the rail over the page's
            // shadow so the tab and the page meet cleanly.
            .zIndex(1)

            // Folio's rail rules itself off; Bureau's page edge is the division.
            if BSHDesign.active == .glass {
                Divider()
            }

            detail(for: selection)
                .id(selection)
                .environment(\.embeddedInRootSplit, true)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .modifier(BSHPadDeskPage())
        }
        .background(Self.ground)
        // Over a dark desk the clock can't be read in light mode; Onyx's white desk keeps it.
        .statusBarHidden(BSHDesign.active == .bureau && BSHPalette.bureauDeskIsDark(colorScheme))
    }

    private static var ground: Color {
        switch BSHDesign.active {
        case .glass: return Color(.systemBackground)
        case .folio: return .dsCanvas
        case .bureau: return BSHPalette.bureauFrame
        }
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
    @EnvironmentObject private var settings: SettingsPresenter
    @State private var hoveredTab: AppTab? = nil
    @State private var isSettingsHovered = false
    @State private var isHeaderToggleHovered = false
    @Namespace private var sidebarNamespace

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            header

            if isExpanded {
                Text(language.t("sidebar.desks"))
                    .font(Self.kickerFont)
                    .tracking(BSHDesign.active == .bureau ? 0 : 0.4)
                    .textCase(BSHType.kickerIsCapitals ? .uppercase : nil)
                    .foregroundStyle(BSHRailInk.muted)
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
        .background { BSHRailGround() }
    }

    /// How far the rail's edge (where Bureau's page begins) lies past a row's edge.
    private var railPadding: CGFloat { isExpanded ? 10 : 8 }

    private static var kickerFont: Font {
        BSHDesign.active == .glass ? .system(size: 11, weight: .semibold) : BSHType.kicker(11)
    }

    private static var titleFont: Font {
        BSHDesign.active == .glass ? .subheadline.weight(.semibold) : BSHType.heading(15)
    }

    private var settingsButton: some View {
        Button {
            settings.isPresented = true
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
            .foregroundStyle(isSettingsHovered ? BSHRailInk.title : BSHRailInk.muted)
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
            .background {
                if isSettingsHovered {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(BSHRailInk.hoverFill)
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
                    .font(Self.titleFont)
                    .foregroundStyle(BSHRailInk.title)
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
                    .foregroundStyle(isHeaderToggleHovered ? BSHRailInk.title : BSHRailInk.muted)
                    .frame(width: 32, height: 32)
                    .background {
                        if isHeaderToggleHovered {
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(BSHRailInk.hoverFill)
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
                        .foregroundStyle(selected ? BSHRailInk.selectedLabel : (hovered ? BSHRailInk.title : BSHRailInk.muted))
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .padding(.horizontal, isExpanded ? 10 : 0)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: isExpanded ? .leading : .center)
            .background {
                if selected {
                    Group {
                        if BSHDesign.active == .glass {
                            SidebarGlassPill(cornerRadius: 10)
                        } else {
                            BSHRailSelection(cornerRadius: 10, reachToPage: railPadding)
                        }
                    }
                    .matchedGeometryEffect(id: "activeSidebarPill", in: sidebarNamespace)
                } else if hovered {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(BSHRailInk.hoverFill)
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .welcomeTourAnchor(WelcomeTourCatalog.tabAnchor(tab))
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
        let iconColor: Color = selected ? BSHRailInk.selectedIcon : (hovered ? BSHRailInk.title : BSHRailInk.muted)
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
