//
//  MacBureauShell.swift
//  BSHResearchMac
//
//  Bureau's window, drawn the way the website draws it (frontend/src/bureau.css, App.vue,
//  Sidebar.vue) and at its measurements. The window is the desk. The desks are index tabs
//  along the top edge of one sheet laid on it, the companies a rail of logos down its left
//  edge, and the one you are on is cut from the sheet and flares into it. The standing
//  actions (Add, Commands, Task history, Generate report, Ask Warren) sit on the desk to the
//  right of the tabs, and Warren (or the research browser) opens as a second sheet beside
//  the page. Summit Glass and Folio keep the Mac's own split view (MacRootView).
//
//  The Mac differs from the page in one place: its traffic lights stand where the website's
//  house mark does, at the head of the rail, on the masthead's control line.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Measurements and colors

/// The website's Bureau measurements (bureau.css, App.vue, Sidebar.vue).
enum MacBureau {
    /// The masthead (`.app-toolbar-row`, 52px).
    static let masthead: CGFloat = 52
    /// The masthead's controls sit on this line: its 8pt top padding, then centered.
    static let controlLine: CGFloat = 30
    /// The desk showing round the sheet (`--bureau-gutter`).
    static let gutter: CGFloat = 10
    /// The sheet's corners (`--bureau-radius`).
    static let sheetRadius: CGFloat = 18
    /// A tab's corners and flares (`--bureau-tab-radius`).
    static let tabRadius: CGFloat = 12
    static let tabHeight: CGFloat = 40
    /// The company rail folded, and the company index open.
    static let rail: CGFloat = 68
    static let index: CGFloat = 268
    /// Warren's sheet, and the research browser's, beside the page (the website's
    /// copilotWidth.js: 392 by default, 720 widened, 340–880 by hand).
    static let asideDefault: CGFloat = 392
    static let asideWide: CGFloat = 720
    static let asideRange: ClosedRange<CGFloat> = 340...880

    static let brass = BSHRGB(208, 172, 100)
    static let brassDeep = BSHRGB(176, 138, 66)
    static let brassHover = BSHRGB(224, 192, 126)
    /// The page's brass ink by day (`--color-accent-ink`).
    static let brassInk = BSHRGB(122, 90, 31)
}

/// The chrome's colors, resolved for the window's appearance. A dark desk is dark in
/// either appearance, as on the website, so nothing here is left to the system.
struct MacBureauInk {
    let scheme: ColorScheme

    private var tones: BSHBureauTones { BSHBureauDesk.active.tones }
    private func pick(_ pair: BSHBureauTones.Pair) -> BSHRGB { scheme == .dark ? pair.dark : pair.light }

    /// Every desk is dark except Onyx's white one by day.
    var deskIsDark: Bool { BSHBureauDesk.active.isDark(in: scheme) }
    /// Onyx & White by day: a pencil rim sets the sheet, its tabs and its seal off the white.
    var lightDesk: Bool { !deskIsDark }

    var desk: Color { .bshFixed(pick(tones.frame)) }
    func onDesk(_ opacity: Double = 1) -> Color { .bshFixed(pick(tones.onFrame), opacity: opacity) }
    var sheet: Color { .bshFixed(pick(tones.sheet)) }
    func ink(_ opacity: Double = 1) -> Color { .bshFixed(pick(tones.ink), opacity: opacity) }

    /// `--bureau-rim`, drawn only on Onyx's white desk by day.
    var rim: Color { Color.black.opacity(0.1) }

    var brass: Color { .bshFixed(MacBureau.brass) }
    var brassDeep: Color { .bshFixed(MacBureau.brassDeep) }
    func brass(_ opacity: Double) -> Color { .bshFixed(MacBureau.brass, opacity: opacity) }

    /// What is written on brass: the desk's own color, or the ink on the white desk.
    var onBrass: Color { lightDesk ? onDesk() : desk }

    /// The lamp's warm pool in the desk's top-left corner (none on Onyx).
    var lamp: Color? {
        guard BSHBureauDesk.active != .onyx else { return nil }
        return .bshFixed(BSHRGB(214, 178, 104), opacity: scheme == .dark ? 0.08 : 0.13)
    }

    /// The grain tile: ivory specks, or Onyx's faint gray ones by night.
    var grain: String {
        BSHBureauDesk.active == .onyx && scheme == .dark ? "BureauGrainOnyx" : "BureauGrain"
    }
}

private struct MacBureauInkKey: EnvironmentKey {
    static let defaultValue = MacBureauInk(scheme: .light)
}

extension EnvironmentValues {
    /// The chrome's colors, set by the shell for the window's appearance.
    var bureauInk: MacBureauInk {
        get { self[MacBureauInkKey.self] }
        set { self[MacBureauInkKey.self] = newValue }
    }
}

// MARK: - The shell

/// The window under Bureau: rail, masthead, the sheet with the desk on it, and the sheets
/// beside it.
struct MacBureauShell<Page: View>: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    /// Folded to a rail of logos, as the website starts; opened, the company index.
    @AppStorage("bsh.bureau.companyIndexOpen") private var indexOpen = false
    @AppStorage("bsh.bureau.asideWidth") private var asideWidth = Double(MacBureau.asideDefault)
    /// The inspector, a sheet beside the page here rather than the split view's column.
    @Binding var showInspector: Bool
    @ViewBuilder var page: () -> Page

    private var ink: MacBureauInk { MacBureauInk(scheme: colorScheme) }
    private var railWidth: CGFloat { indexOpen ? MacBureau.index : MacBureau.rail }

    /// How much of the window the sheets beside the page take, gutters included.
    private var asidesWidth: CGFloat {
        let open = [store.showBrowserPanel, store.showCopilotPanel, showInspector].filter { $0 }.count
        return CGFloat(open) * (CGFloat(asideWidth) + MacBureau.gutter)
    }

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            // The masthead runs over the page's column only; a sheet beside the page has the
            // desk above it, as on the website.
            let mainWidth = max(0, size.width - asidesWidth)
            ZStack(alignment: .topLeading) {
                MacBureauDesk()

                HStack(alignment: .top, spacing: MacBureau.gutter) {
                    MacBureauSheet {
                        // Text that sets no face of its own is in the interface face, and a
                        // button that sets no style of its own is the website's pill.
                        page()
                            .font(BSHType.bureauSans(13))
                            .buttonStyle(.dsBordered)
                            .textFieldStyle(.dsField)
                    }
                    .zIndex(0)
                    if store.showBrowserPanel {
                        aside { MacEmbeddedBrowserPanel() }
                    }
                    if store.showCopilotPanel {
                        aside { MacCopilotSidePanel() }
                    }
                    if showInspector {
                        aside { MacInspectorView() }
                    }
                }
                .padding(.leading, railWidth)
                .padding(.top, MacBureau.masthead)
                .padding(.trailing, MacBureau.gutter)
                .padding(.bottom, MacBureau.gutter)
                .frame(width: size.width, height: size.height, alignment: .topLeading)

                // The masthead covers the sheet's top edge, as the website's does, and
                // redraws it on the white desk; the lit tab stands on it.
                MacBureauMastheadBand(railWidth: railWidth, width: mainWidth)

                MacBureauMasthead(
                    width: mainWidth - railWidth,
                    heldCompanyId: $store.heldCompanyId
                )
                .frame(width: mainWidth - railWidth, height: MacBureau.masthead)
                .offset(x: railWidth)

                MacBureauRail(indexOpen: $indexOpen, heldCompanyId: $store.heldCompanyId)
                    .frame(width: railWidth, height: size.height)
            }
            .frame(width: size.width, height: size.height, alignment: .topLeading)
            // The title bar's band (taller here, for the traffic lights) is the desk's:
            // nothing in the window keeps clear of it.
            .ignoresSafeArea()
        }
        .environment(\.bureauInk, ink)
        .modifier(MacBureauNoScrollEdge())
        .ignoresSafeArea()
        .background(MacBureauWindowChrome())
        .background {
            // The split view's toolbar carried this shortcut; the masthead has no button for it.
            Button("Inspector") { withAnimation(.easeInOut(duration: 0.18)) { showInspector.toggle() } }
                .keyboardShortcut("i", modifiers: [.command, .option])
                .hidden()
        }
        .animation(.easeInOut(duration: 0.18), value: indexOpen)
        .onChange(of: store.selectedTab) { _, tab in
            if !MacBureauCompanyPage.tabs.contains(tab) { store.heldCompanyId = nil }
        }
        .onChange(of: store.selectedCompany?.id) { _, id in
            if store.heldCompanyId != nil, store.heldCompanyId != id { store.heldCompanyId = nil }
        }
    }

    /// A second sheet beside the page, with its left edge to drag.
    private func aside<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        let panel = content()
        // The panel is given exactly its width, so nothing inside can widen the sheet.
        return MacBureauSheet { panel.frame(width: CGFloat(asideWidth)).clipped() }
            .frame(width: CGFloat(asideWidth))
            .overlay(alignment: .leading) {
                MacBureauResizeHandle(width: $asideWidth)
                    .offset(x: -MacBureau.gutter)
            }
            .transition(.move(edge: .trailing).combined(with: .opacity))
    }
}

extension MacCompany {
    /// What the company is, as the website words it (companyStatusLine): its industry or
    /// sector, else whether it is listed.
    var bureauStatusLine: String? {
        for value in [industry, sector] {
            if let value, !value.isEmpty { return value }
        }
        if companyType == "public" || status == "public" { return "Public equity" }
        if companyType == "private" || status == "private" { return "Private company" }
        return nil
    }
}

extension MacAppStore {
    /// Opens the company's page (its Research Desk dossier) as the website's cards and
    /// rail do: the company holds the selection until another desk is chosen.
    func openCompanyPage(_ company: MacCompany) {
        selectCompany(company)
        selectedTab = .research
        heldCompanyId = company.id
    }
}

/// What a company's folder opens on the rail, and the desk each page is.
enum MacBureauCompanyPage: String, CaseIterable, Identifiable {
    case reports, news, desk, market

    var id: String { rawValue }

    static let tabs: Set<MacTab> = [.documents, .news, .research, .market]

    var tab: MacTab {
        switch self {
        case .reports: return .documents
        case .news: return .news
        case .desk: return .research
        case .market: return .market
        }
    }

    var title: String {
        switch self {
        case .reports: return "Reports"
        case .news: return "News"
        case .desk: return "Research Desk"
        case .market: return "Market"
        }
    }

    /// The website's glyph for the page (lucide).
    var icon: String {
        switch self {
        case .reports: return "file-text"
        case .news: return "newspaper"
        case .desk: return "building-2"
        case .market: return "bsh-market"
        }
    }

    static func pages(for company: MacCompany) -> [MacBureauCompanyPage] {
        let listed = !(company.ticker ?? "").isEmpty
        return [.reports, .news, .desk] + (listed ? [.market] : [])
    }
}

// MARK: - The desk

/// The desk under everything: its color, the lamp's pool of light in the top-left corner
/// and a grain of specks, all fixed to the window as the website fixes them to the page.
struct MacBureauDesk: View {
    @Environment(\.bureauInk) private var ink

    var body: some View {
        ZStack {
            ink.desk
            if let lamp = ink.lamp {
                // radial-gradient(74rem 38rem at 8% -14rem, lamp, transparent 70%)
                Canvas { context, size in
                    let rx: CGFloat = 1184, ry: CGFloat = 608
                    context.translateBy(x: size.width * 0.08, y: -224)
                    context.scaleBy(x: rx / ry, y: 1)
                    context.fill(
                        Path(ellipseIn: CGRect(x: -ry, y: -ry, width: ry * 2, height: ry * 2)),
                        with: .radialGradient(
                            Gradient(stops: [
                                .init(color: lamp, location: 0),
                                .init(color: lamp.opacity(0), location: 0.7),
                            ]),
                            center: .zero, startRadius: 0, endRadius: ry
                        )
                    )
                }
            }
            Image(ink.grain)
                .resizable(resizingMode: .tile)
        }
        .allowsHitTesting(false)
    }
}

/// The sheet: the page's paper with rounded corners, a hairline round it, the light along
/// its top edge and the shadow it casts on the desk (the website's `.app-sheet`).
struct MacBureauSheet<Content: View>: View {
    @Environment(\.bureauInk) private var ink
    @ViewBuilder var content: () -> Content

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: MacBureau.sheetRadius, style: .circular)
    }

    var body: some View {
        content()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(ink.sheet)
            .clipShape(shape)
            .overlay {
                // inset 0 1px 0 rgb(255 255 255 / 0.5): the light along the top edge.
                if let light = topLight {
                    ZStack {
                        shape.fill(light)
                        shape.fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                    }
                    .compositingGroup()
                    .allowsHitTesting(false)
                }
            }
            .background {
                // 0 0 0 1px: the hairline just outside the paper.
                shape.inset(by: -0.5).stroke(ring, lineWidth: 1)
            }
            .background {
                // 0 30px 70px -40px: the shadow, pulled in and dropped below the sheet.
                shape
                    .fill(Color.black.opacity(dropOpacity))
                    .padding(40)
                    .offset(y: 30)
                    .blur(radius: 35)
                    .allowsHitTesting(false)
            }
    }

    private var topLight: Color? {
        if ink.lightDesk { return nil }
        return Color.white.opacity(ink.scheme == .dark ? 0.04 : 0.5)
    }

    private var ring: Color {
        if ink.lightDesk { return ink.rim }
        return ink.scheme == .dark ? Color.white.opacity(0.05) : Color.black.opacity(0.18)
    }

    private var dropOpacity: Double {
        if ink.lightDesk { return 0.28 }
        return ink.scheme == .dark ? 0.9 : 0.65
    }
}

/// Drag the second sheet's left edge to widen or narrow it.
private struct MacBureauResizeHandle: View {
    @Binding var width: Double
    @State private var start: Double?

    var body: some View {
        Color.clear
            .frame(width: MacBureau.gutter)
            .contentShape(Rectangle())
            .onHover { inside in
                if inside { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() }
            }
            .gesture(
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { value in
                        let base = start ?? width
                        if start == nil { start = width }
                        let next = base - Double(value.translation.width)
                        let ceiling = min(Double(MacBureau.asideRange.upperBound), Double((NSApp.keyWindow?.frame.width ?? 1600) * 0.6))
                        width = min(max(next, Double(MacBureau.asideRange.lowerBound)), max(Double(MacBureau.asideRange.lowerBound), ceiling))
                    }
                    .onEnded { _ in start = nil }
            )
            .onTapGesture(count: 2) { width = Double(MacBureau.asideDefault) }
            .help("Drag to resize")
    }
}

// MARK: - The masthead

/// The strip of desk along the top, over the sheet's top edge. On Onyx's white desk by day
/// the sheet's edge is drawn on it as a pencil rim (the website's toolbar `::before`).
private struct MacBureauMastheadBand: View {
    @Environment(\.bureauInk) private var ink
    let railWidth: CGFloat
    let width: CGFloat

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            MacBureauDesk()
                .frame(height: MacBureau.masthead, alignment: .top)
                .clipped()
            if ink.lightDesk {
                ink.rim
                    .frame(width: max(0, width - railWidth - MacBureau.gutter - 2 * MacBureau.sheetRadius), height: 1)
                    .offset(x: railWidth + MacBureau.sheetRadius)
            }
        }
        .frame(width: width, height: MacBureau.masthead, alignment: .topLeading)
        .background(MacWindowDragArea())
    }
}

/// The desks as index tabs, then the standing actions: Add, Commands and Task history,
/// Generate report in brass, and Ask Warren.
private struct MacBureauMasthead: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    /// The masthead's own width: it gives way by it, as the website's container queries do.
    let width: CGFloat
    @Binding var heldCompanyId: String?

    /// The website's desks, in its order.
    static let desks: [(tab: MacTab, title: String, icon: String)] = [
        (.home, "Home", "house"),
        (.documents, "Reports", "file-text"),
        (.research, "Research Desk", "building-2"),
        (.news, "News", "newspaper"),
        (.pulse, "Pulse", "bsh-pulse"),
        (.market, "Market", "bsh-market"),
        (.portfolio, "Tracking", "gauge"),
    ]

    /// The Mac's own desks (⌘0, ⌘2 and the Go menu reach them): a tab of their own only
    /// while one is open, so the masthead is otherwise the website's. Settings and the
    /// Warren desk light no tab, as on the website.
    static let macDesks: [MacTab: (title: String, icon: String)] = [
        .attention: ("Attention", "bell"),
        .pipeline: ("Pipeline", "clipboard-list"),
    ]

    private var shownDesks: [(tab: MacTab, title: String, icon: String)] {
        guard let extra = Self.macDesks[store.selectedTab] else { return Self.desks }
        return Self.desks + [(store.selectedTab, extra.title, extra.icon)]
    }

    /// The website's thresholds (bureau.css container queries), moved along by an extra
    /// tab's width while one shows, so the masthead gives way at the same fullness.
    private var extraTabs: CGFloat { shownDesks.count > Self.desks.count ? 96 : 0 }
    private var iconsOnly: Bool { width < 800 + extraTabs }
    private var tabPadding: CGFloat { iconsOnly ? 12 : (width < 920 + extraTabs ? 11 : 15) }
    private var generateLabel: Bool { width >= 1040 + extraTabs }
    private var warrenLabel: Bool { width >= 920 + extraTabs }
    private var showsJump: Bool { width >= 1320 + extraTabs }
    private var showsSync: Bool { width >= 1580 + extraTabs }

    private var litTab: MacTab? {
        heldCompanyId == nil ? store.selectedTab : nil
    }

    var body: some View {
        HStack(alignment: .center, spacing: 6) {
            HStack(alignment: .bottom, spacing: 2) {
                ForEach(shownDesks, id: \.tab) { desk in
                    MacBureauDeskTab(
                        title: desk.title,
                        icon: desk.icon,
                        count: desk.tab == .portfolio ? store.validFollowedIds.count : 0,
                        isLit: litTab == desk.tab,
                        iconsOnly: iconsOnly,
                        padding: tabPadding
                    ) {
                        heldCompanyId = nil
                        store.selectedTab = desk.tab
                    }
                    .macWelcomeTourAnchor(MacWelcomeTourCatalog.tabAnchor(desk.tab))
                }
            }
            .frame(maxHeight: .infinity, alignment: .bottom)
            .padding(.top, 12 - 8)

            Spacer(minLength: 0)

            if showsSync { MacBureauSyncStatus() }
            if showsJump { MacBureauJumpField() }

            HStack(spacing: 2) {
                MacBureauAddMenu()
                MacBureauIconButton(icon: "command", size: 17, help: "Commands (⌘K)", isPressed: store.showCommandPalette) {
                    store.openCommandPalette()
                }
                .macWelcomeTourAnchor(MacWelcomeTourCatalog.commandAnchor)
                MacBureauIconButton(icon: "history", help: "Task history", isPressed: store.showBlotter) {
                    store.toggleBlotter()
                }
            }
            .padding(.horizontal, 3)
            .frame(height: 36)

            MacBureauGenerateButton(showsLabel: generateLabel)

            MacBureauWarrenButton(showsLabel: warrenLabel)
                .padding(3)
                .macWelcomeTourAnchor(MacWelcomeTourCatalog.tabAnchor(.copilot))
        }
        .padding(.top, 8)
        .padding(.leading, 24)
        .padding(.trailing, MacBureau.gutter + 2)
        .frame(width: width, height: MacBureau.masthead)
        .environment(\.colorScheme, ink.deskIsDark ? .dark : .light)
    }
}

/// One desk tab. At rest a label written on the desk; lit, a piece of the sheet standing on
/// its top edge, flared into it, with a brass mark along its top.
private struct MacBureauDeskTab: View {
    @Environment(\.bureauInk) private var ink
    let title: String
    let icon: String
    let count: Int
    let isLit: Bool
    let iconsOnly: Bool
    let padding: CGFloat
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                if iconsOnly {
                    LucideIcon(icon, size: 17)
                } else {
                    Text(title)
                        .font(BSHType.bureauSans(13.5, weight: isLit ? .semibold : .medium))
                        .tracking(0.054)
                        .fixedSize()
                    if count > 0 {
                        Text("\(count)")
                            .font(BSHType.bureauSans(11, weight: .medium).monospacedDigit())
                            .foregroundStyle(isLit ? Color.bshFixed(BSHRGB(255, 253, 246)) : countInk)
                            .padding(.horizontal, 4.8)
                            .frame(minWidth: 20, minHeight: 18)
                            .background(Capsule().fill(isLit ? Color.dsAccent : ink.brass(0.85)))
                    }
                }
            }
            .foregroundStyle(isLit ? ink.ink() : ink.onDesk(hovered ? 1 : 0.64))
            .padding(.horizontal, padding)
            .frame(height: MacBureau.tabHeight)
            .background { background }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(title)
        .accessibilityAddTraits(isLit ? .isSelected : [])
    }

    private var countInk: Color { ink.lightDesk ? ink.onDesk() : ink.desk }

    @ViewBuilder
    private var background: some View {
        if isLit {
            let tab = BSHJoinedTabShape(join: .bottom, radius: MacBureau.tabRadius)
            ZStack(alignment: .top) {
                tab.fill(ink.sheet)
                if ink.lightDesk {
                    BSHJoinedTabShape(join: .bottom, radius: MacBureau.tabRadius, includesJoin: false)
                        .stroke(ink.rim, lineWidth: 1)
                }
                // The brass mark: 14×2, 6pt below the tab's top edge.
                Rectangle()
                    .fill(ink.brassDeep)
                    .frame(width: 14, height: 2)
                    .offset(y: 6)
            }
        } else if hovered {
            UnevenRoundedRectangle(topLeadingRadius: MacBureau.tabRadius, topTrailingRadius: MacBureau.tabRadius, style: .circular)
                .fill(ink.onDesk(0.07))
        }
    }
}

/// A round 30pt button on the desk, its glyph in the desk's ink.
private struct MacBureauIconButton: View {
    @Environment(\.bureauInk) private var ink
    let icon: String
    var size: CGFloat = 18
    let help: String
    var isPressed = false
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            MacBureauIconGlyph(icon: icon, size: size, isLit: isPressed || hovered)
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(help)
        .accessibilityLabel(help)
    }
}

private struct MacBureauIconGlyph: View {
    @Environment(\.bureauInk) private var ink
    let icon: String
    var size: CGFloat = 18
    var isLit = false

    var body: some View {
        LucideIcon(icon, size: size)
            .foregroundStyle(ink.onDesk(isLit ? 1 : 0.66))
            .frame(width: 30, height: 30)
            .background(Circle().fill(isLit ? ink.onDesk(0.09) : .clear))
            .contentShape(Circle())
    }
}

/// Add: on the website a menu of what can be filed. On the Mac: a report, or a pitch deck.
private struct MacBureauAddMenu: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var hovered = false

    var body: some View {
        Menu {
            Button("Generate report") { store.requestNewReport() }
                .disabled(!store.canRunTasks)
            Button("File a pitch deck…") { pickDeck() }
                .disabled(!store.canEditSources)
        } label: {
            MacBureauIconGlyph(icon: "plus", isLit: hovered)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .onHover { hovered = $0 }
        .help(store.selectedCompany.map { "Add to \($0.name ?? $0.id)" } ?? "Add")
    }

    private func pickDeck() {
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
}

/// Generate report: the standing action, a brass pill on the desk, Warren's orb struck in
/// the button's own metal.
private struct MacBureauGenerateButton: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    let showsLabel: Bool
    @State private var hovered = false
    @State private var pressed = false

    var body: some View {
        Button {
            store.requestNewReport()
        } label: {
            HStack(spacing: 7) {
                AiOrbView(size: 16)
                    .grayscale(1)
                    .contrast(1.2)
                    .brightness(0.08)
                    .blendMode(.multiply)
                if showsLabel {
                    Text("Generate report")
                        .font(BSHType.bureauSans(13, weight: .semibold))
                        .tracking(0.065)
                        .fixedSize()
                }
            }
            .foregroundStyle(ink.onBrass)
            .padding(.leading, showsLabel ? 10 : 0)
            .padding(.trailing, showsLabel ? 14 : 0)
            .frame(width: showsLabel ? nil : 32, height: 32)
            .background {
                Capsule()
                    .fill(metal)
                    .overlay(
                        Capsule().fill(LinearGradient(
                            stops: [.init(color: .white.opacity(0.28), location: 0), .init(color: .white.opacity(0), location: 0.55)],
                            startPoint: .top, endPoint: .bottom
                        ))
                    )
            }
            .compositingGroup()
            .overlay {
                // inset 0 1px 0 rgb(255 255 255 / 0.35)
                ZStack {
                    Capsule().fill(Color.white.opacity(0.35))
                    Capsule().fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                }
                .compositingGroup()
                .clipShape(Capsule())
                .allowsHitTesting(false)
            }
            .background {
                Capsule().inset(by: -0.5).stroke(ringColor, lineWidth: 1)
            }
            .shadow(color: .black.opacity(ink.lightDesk ? 0.28 : 0.5), radius: ink.lightDesk ? 3 : 4, y: ink.lightDesk ? 3 : 4)
            .contentShape(Capsule())
            .offset(y: pressed ? 0.5 : 0)
        }
        .buttonStyle(MacBureauPressStyle(pressed: $pressed))
        .onHover { hovered = $0 }
        .disabled(!store.canRunTasks)
        .help(store.canRunTasks ? "Generate report (⌘N)" : "Sign in with an analyst or partner role to run memos")
    }

    private var metal: Color {
        if pressed { return ink.brassDeep }
        return hovered ? .bshFixed(MacBureau.brassHover) : ink.brass
    }

    private var ringColor: Color {
        ink.lightDesk ? .bshFixed(BSHRGB(120, 90, 30), opacity: 0.28) : .black.opacity(0.25)
    }
}

/// Ask Warren: his portrait and name, ruled in the desk's ink; open, in brass.
private struct MacBureauWarrenButton: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    let showsLabel: Bool
    @State private var hovered = false

    private var isOpen: Bool { store.showCopilotPanel }

    var body: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.18)) { store.showCopilotPanel.toggle() }
        } label: {
            HStack(spacing: 6) {
                WarrenMarkView(size: 22, isBusy: store.copilotStreaming)
                if showsLabel {
                    Text("Ask Warren")
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .fixedSize()
                }
            }
            .foregroundStyle(labelColor)
            .padding(.leading, 6)
            .padding(.trailing, showsLabel ? 12 : 6)
            .frame(height: 30)
            .background(Capsule().fill(fill))
            .overlay(Capsule().strokeBorder(rule, lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help("Ask Warren (⌥⌘C)")
    }

    private var labelColor: Color {
        guard isOpen else { return ink.onDesk() }
        return ink.lightDesk ? .bshFixed(MacBureau.brassInk) : ink.brass
    }

    private var fill: Color {
        if isOpen { return ink.brass(0.12) }
        return hovered ? ink.onDesk(0.08) : .clear
    }

    private var rule: Color {
        isOpen ? ink.brass(0.6) : ink.onDesk(0.2)
    }
}

/// Presses in by half a point, as the website's buttons do, and reports it.
private struct MacBureauPressStyle: ButtonStyle {
    @Binding var pressed: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .onChange(of: configuration.isPressed) { _, isPressed in pressed = isPressed }
    }
}

/// The sync state, shown only where the masthead is wide enough (the website: 1580pt).
private struct MacBureauSyncStatus: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink

    var body: some View {
        Button {
            Task { await store.bootstrap() }
        } label: {
            HStack(spacing: 6) {
                Circle().fill(dot).frame(width: 6, height: 6)
                Text(label)
                    .font(BSHType.bureauSans(12, weight: .medium).monospacedDigit())
            }
            .foregroundStyle(ink.onDesk(0.55))
            .padding(.horizontal, 8)
            .frame(height: 28)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Refresh all desks (⌘R)")
    }

    private var dot: Color {
        if store.isOfflineMode { return .orange }
        if store.homeSyncError != nil { return .red }
        return store.lastSyncDate == nil ? ink.onDesk(0.4) : .green
    }

    private var label: String {
        if store.isOfflineMode { return "Offline · cached" }
        if store.homeSyncError != nil { return "Sync failed" }
        if let date = store.lastSyncDate {
            return "Synced \(date.formatted(date: .omitted, time: .shortened))"
        }
        return "Syncing…"
    }
}

/// The jump field (the website shows it where the masthead is 1320pt wide): it opens the
/// command line, which finds companies and commands alike.
private struct MacBureauJumpField: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    @State private var hovered = false

    var body: some View {
        Button {
            store.openCommandPalette()
        } label: {
            HStack(spacing: 8) {
                LucideIcon("search", size: 14)
                    .foregroundStyle(ink.onDesk(0.5))
                Text("Jump to a company or command")
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.onDesk(0.5))
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text("⌘K")
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .foregroundStyle(ink.onDesk(0.7))
                    .padding(.horizontal, 5)
                    .frame(height: 18)
                    .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(ink.onDesk(0.2), lineWidth: 1))
            }
            .padding(.leading, 12)
            .padding(.trailing, 8)
            .frame(width: 280, height: 32)
            .background(Capsule().fill(ink.onDesk(hovered ? 0.1 : 0.07)))
            .overlay(Capsule().strokeBorder(ink.onDesk(0.12), lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help("Commands (⌘K)")
    }
}

// MARK: - The company rail

/// The companies down the sheet's left edge: a rail of logos, or opened, the company
/// index. The company on screen is a tab cut from the sheet; its folder holds its pages.
private struct MacBureauRail: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    @Binding var indexOpen: Bool
    @Binding var heldCompanyId: String?
    @AppStorage("bsh.sidebar.companySort") private var sortRaw = MacCompanySort.az.rawValue
    @State private var openCompanyId: String?
    @State private var filter = ""
    @State private var sector = Self.allSectors
    @State private var diffsOnly = false

    private static let allSectors = "All sectors"
    /// A filter field earns its place once the list outgrows a glance (web: > 8).
    private static let filterThreshold = 8

    private var sort: MacCompanySort { MacCompanySort(rawValue: sortRaw) ?? .az }

    private var sectors: [String] {
        let found = Set(store.companies.compactMap(\.sector).filter { !$0.isEmpty })
        return [Self.allSectors] + found.sorted()
    }

    private var visible: [MacCompany] {
        let query = filter.trimmingCharacters(in: .whitespacesAndNewlines)
        return MacCompanySort.apply(
            sort,
            to: store.companies,
            followed: Set(store.followedCompanyIds),
            visits: store.visitedCompanyTimestamps
        )
        .filter { company in
            if diffsOnly && !store.isCompanyModified(company.id) { return false }
            if sector != Self.allSectors && company.sector != sector { return false }
            guard !query.isEmpty else { return true }
            return (company.name ?? "").localizedCaseInsensitiveContains(query)
                || (company.ticker ?? "").localizedCaseInsensitiveContains(query)
                || company.id.localizedCaseInsensitiveContains(query)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            brand
            companies
                .macWelcomeTourAnchor(MacWelcomeTourCatalog.bureauCompaniesAnchor)
            account
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .environment(\.colorScheme, ink.deskIsDark ? .dark : .light)
        // A company's folder opens with its page, however it was reached, as on the
        // website; otherwise only by hand.
        .onChange(of: heldCompanyId, initial: true) { _, id in
            if let id { openCompanyId = id }
        }
    }

    // MARK: Head of the rail

    /// Where the website sets its house mark the Mac has its traffic lights, so the head
    /// of the rail is left to them and to the index toggle.
    private var brand: some View {
        ZStack(alignment: .topLeading) {
            MacWindowDragArea()
            MacBureauIndexToggle(isOpen: $indexOpen)
                .offset(x: indexOpen ? 226 : 18, y: indexOpen ? 14 : 58)
        }
        .frame(width: indexOpen ? MacBureau.index : MacBureau.rail, height: indexOpen ? 62 : 96, alignment: .topLeading)
    }

    // MARK: Companies

    private var companies: some View {
        VStack(alignment: .leading, spacing: 0) {
            if indexOpen {
                indexHeader
                if store.companies.count > Self.filterThreshold {
                    filterField
                }
                if sectors.count > 2 || !store.companies.isEmpty {
                    filterRow
                }
            }
            ScrollView(.vertical, showsIndicators: false) {
                LazyVStack(alignment: .leading, spacing: 1) {
                    if indexOpen && store.companies.isEmpty {
                        note("No companies yet")
                    } else if indexOpen && visible.isEmpty {
                        note(filter.isEmpty ? "Nothing changed since you last looked" : "No company matches")
                    }
                    ForEach(visible) { company in
                        companyEntry(company)
                    }
                }
                .padding(.leading, 10)
                .padding(.vertical, indexOpen ? 4 : 12)
            }
            .scrollClipDisabled()
        }
        .padding(.top, 6)
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private var indexHeader: some View {
        HStack(spacing: 6) {
            Text("Companies")
                .font(.custom(BSHType.bureauSerifItalic, size: 15.5))
                .foregroundStyle(ink.onDesk(0.6))
            Spacer(minLength: 4)
            Text("\(visible.count)")
                .font(BSHType.bureauSans(11).monospacedDigit())
                .foregroundStyle(ink.onDesk(0.45))
            Menu {
                Picker("Sort", selection: $sortRaw) {
                    ForEach(MacCompanySort.allCases) { option in
                        Text(option.title).tag(option.rawValue)
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
            } label: {
                HStack(spacing: 4) {
                    LucideIcon("arrow-up-down", size: 14)
                    Text(sort.shortTitle)
                        .font(BSHType.bureauSans(11, weight: .medium))
                }
                .foregroundStyle(ink.onDesk(0.5))
                .padding(.horizontal, 6)
                .frame(height: 24)
                .contentShape(Capsule())
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Sort companies")
        }
        .padding(.leading, 18)
        .padding(.trailing, 10)
        .padding(.bottom, 4)
    }

    private var filterField: some View {
        HStack(spacing: 6) {
            LucideIcon("search", size: 14)
                .foregroundStyle(ink.onDesk(0.45))
            TextField("Filter companies", text: $filter)
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(13))
                .foregroundStyle(ink.onDesk())
                .onExitCommand { filter = "" }
        }
        .padding(.horizontal, 10)
        .frame(height: 30)
        .background(Capsule().fill(ink.onDesk(0.07)))
        .overlay(Capsule().strokeBorder(ink.onDesk(0.1), lineWidth: 1))
        .padding(.horizontal, 10)
        .padding(.bottom, 6)
    }

    /// Sector and Diffs: the two filters the Research desk's directory carried.
    private var filterRow: some View {
        HStack(spacing: 6) {
            if sectors.count > 2 {
                Picker("Sector", selection: $sector) {
                    ForEach(sectors, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .controlSize(.small)
            }
            Button {
                diffsOnly.toggle()
            } label: {
                HStack(spacing: 3) {
                    LucideIcon(diffsOnly ? "sparkle" : "sparkles", size: 12)
                    Text("Diffs")
                        .font(BSHType.bureauSans(10, weight: .medium))
                }
                .foregroundStyle(diffsOnly ? ink.brass : ink.onDesk())
                .padding(.horizontal, 7)
                .frame(height: 15)
                .background(Capsule().fill(diffsOnly ? ink.brass(0.16) : ink.onDesk(0.06)))
                .overlay(Capsule().strokeBorder(ink.onDesk(0.14), lineWidth: 0.5))
                .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .help("Only companies with updates or new memos since you last looked")
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 6)
    }

    private func note(_ text: String) -> some View {
        Text(text)
            .font(BSHType.bureauSans(12))
            .foregroundStyle(ink.onDesk(0.5))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
    }

    /// Whether the company's page is what the sheet shows.
    private func holds(_ company: MacCompany) -> Bool {
        heldCompanyId == company.id && store.selectedCompany?.id == company.id
            && MacBureauCompanyPage.tabs.contains(store.selectedTab)
    }

    private func litPage(for company: MacCompany) -> MacBureauCompanyPage? {
        guard holds(company) else { return nil }
        return MacBureauCompanyPage.allCases.first { $0.tab == store.selectedTab }
    }

    @ViewBuilder
    private func companyEntry(_ company: MacCompany) -> some View {
        let isOpen = openCompanyId == company.id
        let held = holds(company)
        if indexOpen {
            VStack(alignment: .leading, spacing: 1) {
                MacBureauIndexRow(
                    company: company,
                    isOpen: isOpen,
                    isHeld: held && litPage(for: company) == nil,
                    toggle: { toggleFolder(company) }
                )
                .contextMenu { companyMenu(company) }
                if isOpen {
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(MacBureauCompanyPage.pages(for: company)) { page in
                            MacBureauIndexPageRow(
                                page: page,
                                count: page == .reports ? store.reports.filter { $0.companyId == company.id }.count : nil,
                                isLit: litPage(for: company) == page
                            ) { go(company, to: page) }
                        }
                    }
                    .padding(.leading, 30)
                    .padding(.top, 1)
                    .padding(.bottom, 4)
                }
            }
            .macWelcomeTourAnchor(MacWelcomeTourCatalog.bureauFolderAnchor, when: isOpen)
        } else {
            MacBureauRailFolder(
                company: company,
                isOpen: isOpen,
                isHeld: held,
                pages: MacBureauCompanyPage.pages(for: company),
                litPage: litPage(for: company),
                toggle: { toggleFolder(company) },
                open: { page in go(company, to: page) }
            )
            .contextMenu { companyMenu(company) }
            .macWelcomeTourAnchor(MacWelcomeTourCatalog.bureauFolderAnchor, when: isOpen)
        }
    }

    @ViewBuilder
    private func companyMenu(_ company: MacCompany) -> some View {
        Button("Open Research Desk") { go(company, to: .desk) }
        Button(store.isFollowed(company.id) ? "Unfollow" : "Follow") {
            Task { await store.toggleFollow(company.id) }
        }
    }

    /// As on the website, opening a company only opens its folder; its pages go somewhere.
    private func toggleFolder(_ company: MacCompany) {
        withAnimation(.easeOut(duration: 0.15)) {
            openCompanyId = openCompanyId == company.id ? nil : company.id
        }
    }

    /// Select the company (so every desk and Warren follow it), then open the page.
    private func go(_ company: MacCompany, to page: MacBureauCompanyPage) {
        store.selectCompany(company)
        switch page {
        case .reports: store.documentsCompanyFilter = company.id
        case .news: store.newsCompanyFocus = company
        case .desk: break
        case .market:
            if let ticker = company.ticker, !ticker.isEmpty { store.selectTicker(ticker) }
        }
        store.selectedTab = page.tab
        heldCompanyId = company.id
    }

    // MARK: Account

    private var account: some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(ink.onDesk(0.1))
                .frame(height: 1)
                .padding(.horizontal, 16)
                .padding(.bottom, 6)
            MacBureauAccountRow(indexOpen: indexOpen)
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
        }
    }
}

/// The index toggle at the head of the rail.
private struct MacBureauIndexToggle: View {
    @Environment(\.bureauInk) private var ink
    @Binding var isOpen: Bool
    @State private var hovered = false

    var body: some View {
        Button {
            isOpen.toggle()
        } label: {
            LucideIcon(isOpen ? "panel-left-close" : "panel-left", size: 18)
                .foregroundStyle(ink.onDesk(isOpen || hovered ? 1 : 0.5))
                .frame(width: 32, height: 32)
                .background(Circle().fill(isOpen ? ink.onDesk(0.08) : (hovered ? ink.onDesk(0.07) : .clear)))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(isOpen ? "Fold the index to a rail" : "Open the company index")
    }
}

/// A company on the folded rail: its logo; its folder, when open, holds its pages as
/// glyphs. The company on screen is a tab cut from the sheet, folder and all.
private struct MacBureauRailFolder: View {
    @Environment(\.bureauInk) private var ink
    let company: MacCompany
    let isOpen: Bool
    let isHeld: Bool
    let pages: [MacBureauCompanyPage]
    let litPage: MacBureauCompanyPage?
    let toggle: () -> Void
    let open: (MacBureauCompanyPage) -> Void
    @State private var hovered = false

    var body: some View {
        VStack(spacing: 0) {
            Button(action: toggle) {
                MacAvatar(company: company, size: 30)
                    .frame(width: 58, height: 44)
                    .background {
                        if !isHeld && hovered {
                            UnevenRoundedRectangle(topLeadingRadius: MacBureau.tabRadius, bottomLeadingRadius: MacBureau.tabRadius, style: .circular)
                                .fill(ink.onDesk(0.07))
                        }
                    }
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .onHover { hovered = $0 }
            .help(company.name ?? company.id)

            if isOpen {
                VStack(spacing: 1) {
                    ForEach(pages) { page in
                        MacBureauRailPageGlyph(page: page, isLit: litPage == page, onSheet: isHeld) { open(page) }
                    }
                }
                .padding(.vertical, isHeld ? 0 : 3)
                .background {
                    if !isHeld {
                        UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 10, style: .circular)
                            .fill(ink.onDesk(0.05))
                    }
                }
                .padding(.leading, isHeld ? 4 : 6)
                .padding(.trailing, isHeld ? 8 : 0)
                .padding(.top, isHeld ? 0 : 2)
                .padding(.bottom, isHeld ? 4 : 6)
            }
        }
        .frame(width: 58)
        .background { if isHeld { MacBureauRailTab() } }
        .padding(.vertical, isHeld ? 4 : 0)
    }
}

/// A page of the open company on the folded rail: its glyph.
private struct MacBureauRailPageGlyph: View {
    @Environment(\.bureauInk) private var ink
    let page: MacBureauCompanyPage
    let isLit: Bool
    let onSheet: Bool
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            LucideIcon(page.icon, size: 15)
                .foregroundStyle(glyphColor)
                .frame(maxWidth: .infinity)
                .frame(height: 27)
                .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(fill))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(page.title)
    }

    private var glyphColor: Color {
        if onSheet {
            if isLit { return ink.brassDeep }
            return ink.ink(hovered ? 1 : 0.5)
        }
        return ink.onDesk(hovered ? 1 : 0.72)
    }

    private var fill: Color {
        if isLit { return ink.brass(0.2) }
        if hovered && !onSheet { return ink.onDesk(0.07) }
        return .clear
    }
}

/// A company in the open index: logo, name and what it is; the company on screen is a
/// tab cut from the sheet.
private struct MacBureauIndexRow: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    let company: MacCompany
    let isOpen: Bool
    let isHeld: Bool
    let toggle: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: toggle) {
            HStack(spacing: 10) {
                MacAvatar(company: company, size: 26)
                VStack(alignment: .leading, spacing: 0) {
                    Text(company.name ?? company.id)
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .tracking(-0.078)
                        .lineLimit(1)
                    if let line = statusLine, !line.isEmpty {
                        Text(line)
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(isHeld ? ink.ink(0.55) : ink.onDesk(0.5))
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 4)
                if isOpen {
                    LucideIcon("chevron-down", size: 14)
                        .foregroundStyle(isHeld ? ink.ink(0.62) : ink.onDesk(0.5))
                }
            }
            .foregroundStyle(isHeld ? ink.ink() : ink.onDesk(hovered ? 1 : 0.72))
            .padding(.leading, 8)
            .padding(.trailing, 10)
            .padding(.vertical, 5)
            .frame(minHeight: 40)
            .background {
                if isHeld {
                    MacBureauRailTab()
                } else if hovered {
                    UnevenRoundedRectangle(topLeadingRadius: MacBureau.tabRadius, bottomLeadingRadius: MacBureau.tabRadius, style: .circular)
                        .fill(ink.onDesk(0.07))
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(company.name ?? company.id)
    }

    private var statusLine: String? { company.bureauStatusLine }
}

/// A page under the open company in the index.
private struct MacBureauIndexPageRow: View {
    @Environment(\.bureauInk) private var ink
    let page: MacBureauCompanyPage
    let count: Int?
    let isLit: Bool
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                LucideIcon(page.icon, size: 15)
                    .foregroundStyle(isLit ? ink.ink(0.62) : ink.onDesk(0.6))
                Text(page.title)
                    .font(BSHType.bureauSans(13, weight: .medium))
                    .tracking(-0.078)
                    .lineLimit(1)
                Spacer(minLength: 4)
                if let count {
                    Text("\(count)")
                        .font(BSHType.bureauSans(11).monospacedDigit())
                        .foregroundStyle(isLit ? ink.ink(0.45) : ink.onDesk(0.45))
                }
            }
            .foregroundStyle(isLit ? ink.ink() : ink.onDesk(hovered ? 1 : 0.72))
            .padding(.horizontal, 10)
            .frame(height: 31.5)
            .background {
                if isLit {
                    MacBureauRailTab()
                } else if hovered {
                    UnevenRoundedRectangle(topLeadingRadius: MacBureau.tabRadius, bottomLeadingRadius: MacBureau.tabRadius, style: .circular)
                        .fill(ink.onDesk(0.07))
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(page.title)
    }
}

/// A tab down the sheet's left edge: the sheet's paper, flared into it at both corners,
/// ruled in pencil on the white desk.
private struct MacBureauRailTab: View {
    @Environment(\.bureauInk) private var ink

    var body: some View {
        ZStack {
            BSHJoinedTabShape(join: .trailing, radius: MacBureau.tabRadius)
                .fill(ink.sheet)
            if ink.lightDesk {
                BSHJoinedTabShape(join: .trailing, radius: MacBureau.tabRadius, includesJoin: false)
                    .stroke(ink.rim, lineWidth: 1)
            }
        }
    }
}

/// Who is signed in, at the foot of the rail, with the account's menu.
private struct MacBureauAccountRow: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.bureauInk) private var ink
    let indexOpen: Bool
    @State private var hovered = false

    private var label: String {
        guard let session = store.session else { return store.authChecked ? "Not signed in" : "Connecting…" }
        return session.isAnonDev ? "Account" : session.displayName
    }

    private var detail: String? {
        guard let session = store.session else { return store.authChecked ? "Read-only until you sign in" : nil }
        if session.isAnonDev { return "Local development" }
        if let email = session.email, email.lowercased() != label.lowercased() { return email }
        return session.roleLabel
    }

    private var initials: String {
        guard let session = store.session, !session.isAnonDev else { return "?" }
        let words = session.displayName.split(whereSeparator: { $0 == " " || $0 == "@" || $0 == "." })
        return words.prefix(2).compactMap(\.first).map(String.init).joined().uppercased()
    }

    var body: some View {
        Menu {
            Button("Settings") { store.selectedTab = .settings }
            Divider()
            if let session = store.session, !session.isAnonDev {
                Button("Sign Out") { Task { await store.signOut() } }
            } else {
                Button("Sign In…") { store.showLoginSheet = true }
            }
        } label: {
            HStack(spacing: 10) {
                seal(size: indexOpen ? 28 : 32)
                if indexOpen {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(label)
                            .font(BSHType.bureauSans(13, weight: .medium))
                            .foregroundStyle(ink.onDesk())
                            .lineLimit(1)
                        if let detail {
                            Text(detail)
                                .font(BSHType.bureauSans(11))
                                .foregroundStyle(ink.onDesk(0.5))
                                .lineLimit(1)
                        }
                    }
                    Spacer(minLength: 4)
                    LucideIcon("chevrons-up-down", size: 14)
                        .foregroundStyle(ink.onDesk(0.45))
                }
            }
            .padding(.horizontal, indexOpen ? 8 : 0)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: indexOpen ? .leading : .center)
            .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(hovered ? ink.onDesk(0.07) : .clear))
            .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .onHover { hovered = $0 }
        .help(label)
    }

    /// An ivory seal rather than a hashed color.
    private func seal(size: CGFloat) -> some View {
        Text(initials)
            .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
            .tracking(size * 0.0037)
            .foregroundStyle(ink.onDesk())
            .frame(width: size, height: size)
            .background(Circle().fill(ink.onDesk(0.1)))
            .overlay(Circle().strokeBorder(ink.onDesk(0.28), lineWidth: 1))
    }
}

/// The desk carries no frosted band under the title bar (macOS 26 draws one over a
/// window's content); the masthead is the desk, not a bar.
private struct MacBureauNoScrollEdge: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 15.0, *) {
            content
                .toolbarBackground(.hidden, for: .windowToolbar)
                .toolbarBackgroundVisibility(.hidden, for: .windowToolbar)
        } else {
            content.toolbarBackground(.hidden, for: .windowToolbar)
        }
    }
}

// MARK: - Glyphs

/// One of the website's icons (lucide, as it bundles them; Assets.xcassets/Lucide), drawn
/// as a template in the current foreground style. Stroke 2 on a 24pt grid, so at 18pt a
/// stroke is 1.5pt, as on the page.
struct LucideIcon: View {
    let name: String
    var size: CGFloat

    init(_ name: String, size: CGFloat = 18) {
        self.name = name
        self.size = size
    }

    var body: some View {
        Image("lucide-\(name)")
            .renderingMode(.template)
            .resizable()
            .interpolation(.high)
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

// MARK: - The window

/// Drags the window from the desk, and zooms it (or whatever the Dock setting asks) on a
/// double click, as a title bar does.
struct MacWindowDragArea: NSViewRepresentable {
    func makeNSView(context: Context) -> DragView { DragView() }
    func updateNSView(_ nsView: DragView, context: Context) {}

    final class DragView: NSView {
        override var mouseDownCanMoveWindow: Bool { true }

        override func mouseDown(with event: NSEvent) {
            guard let window else { return }
            if event.clickCount == 2 {
                switch UserDefaults.standard.string(forKey: "AppleActionOnDoubleClick") {
                case "Minimize": window.performMiniaturize(nil)
                case "None": break
                default: window.performZoom(nil)
                }
            } else {
                window.performDrag(with: event)
            }
        }
    }
}

/// The window under Bureau: no title bar of its own (the desk runs to the top edge, under a
/// transparent one), and the traffic lights on the masthead's control line. Put back as it
/// was when the window leaves Bureau.
struct MacBureauWindowChrome: NSViewRepresentable {
    func makeNSView(context: Context) -> ChromeView { ChromeView() }
    func updateNSView(_ view: ChromeView, context: Context) { view.apply() }
    static func dismantleNSView(_ view: ChromeView, coordinator: ()) { view.restore() }

    final class ChromeView: NSView {
        private weak var configured: NSWindow?
        private var saved: (transparent: Bool, visibility: NSWindow.TitleVisibility, fullSize: Bool, separator: NSTitlebarSeparatorStyle)?
        private var observers: [NSObjectProtocol] = []
        /// SwiftUI sets the window's title bar up again as the content changes; these put
        /// Bureau's back.
        private var watches: [NSKeyValueObservation] = []

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if window == nil { restore() } else { apply() }
        }

        func apply() {
            guard let window else { return }
            if configured !== window {
                restore()
                configured = window
                saved = (window.titlebarAppearsTransparent, window.titleVisibility, window.styleMask.contains(.fullSizeContentView), window.titlebarSeparatorStyle)
                configureTitlebar(window)
                watches = [
                    window.observe(\.titleVisibility) { [weak self] window, _ in
                        DispatchQueue.main.async { self?.configureTitlebar(window) }
                    },
                    window.observe(\.titlebarAppearsTransparent) { [weak self] window, _ in
                        DispatchQueue.main.async { self?.configureTitlebar(window) }
                    },
                    window.observe(\.styleMask) { [weak self] window, _ in
                        DispatchQueue.main.async { self?.configureTitlebar(window) }
                    },
                ]
                let center = NotificationCenter.default
                let names: [Notification.Name] = [
                    NSWindow.didResizeNotification, NSWindow.didEndLiveResizeNotification,
                    NSWindow.didExitFullScreenNotification, NSWindow.didBecomeKeyNotification,
                    NSWindow.didResignKeyNotification, NSWindow.didChangeScreenNotification,
                ]
                observers = names.map { name in
                    center.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                        self?.placeTrafficLights()
                        DispatchQueue.main.async { self?.placeTrafficLights() }
                    }
                }
            }
            placeTrafficLights()
            DispatchQueue.main.async { [weak self] in self?.placeTrafficLights() }
        }

        private func configureTitlebar(_ window: NSWindow) {
            guard configured === window else { return }
            if !window.titlebarAppearsTransparent { window.titlebarAppearsTransparent = true }
            if window.titleVisibility != .hidden { window.titleVisibility = .hidden }
            if !window.styleMask.contains(.fullSizeContentView) { window.styleMask.insert(.fullSizeContentView) }
            if window.titlebarSeparatorStyle != .none { window.titlebarSeparatorStyle = .none }
            placeTrafficLights()
        }

        func restore() {
            watches.forEach { $0.invalidate() }
            watches = []
            observers.forEach(NotificationCenter.default.removeObserver)
            observers = []
            guard let window = configured, let saved else { configured = nil; return }
            window.titlebarAppearsTransparent = saved.transparent
            window.titleVisibility = saved.visibility
            if !saved.fullSize { window.styleMask.remove(.fullSizeContentView) }
            window.titlebarSeparatorStyle = saved.separator
            if let close = window.standardWindowButton(.closeButton), let container = close.superview?.superview {
                container.needsLayout = true
                container.superview?.needsLayout = true
            }
            configured = nil
            self.saved = nil
        }

        /// Makes the title bar exactly the masthead's band and centers the traffic lights on
        /// its control line, where the website's controls (and its house mark) sit. The band
        /// ends where the sheet begins: taller, the title bar would reach over the sheet's
        /// scroll views and frost itself over them.
        func placeTrafficLights() {
            guard let window, configured === window, !window.styleMask.contains(.fullScreen),
                  let close = window.standardWindowButton(.closeButton),
                  let mini = window.standardWindowButton(.miniaturizeButton),
                  let zoom = window.standardWindowButton(.zoomButton),
                  let titlebar = close.superview,
                  let container = titlebar.superview
            else { return }
            let band = MacBureau.masthead
            var frame = container.frame
            if abs(frame.height - band) > 0.5 {
                frame.size.height = band
                frame.origin.y = window.frame.height - band
                container.frame = frame
            }
            if abs(titlebar.frame.height - band) > 0.5 {
                titlebar.frame = container.bounds
            }
            for button in [close, mini, zoom] {
                // Unflipped: measured up from the band's foot.
                let y = (band - MacBureau.controlLine - button.frame.height / 2).rounded()
                if abs(button.frame.origin.y - y) > 0.5 {
                    button.setFrameOrigin(NSPoint(x: button.frame.origin.x, y: y))
                }
            }
        }
    }
}
