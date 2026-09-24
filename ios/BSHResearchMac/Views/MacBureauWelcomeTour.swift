//
//  MacBureauWelcomeTour.swift
//  BSHResearchMac
//
//  The welcome tour under Bureau, as the website gives it (WelcomeTour.vue and
//  welcomeTour.js, drawn by style.css and bureau.css; DesignLookCards.vue and
//  BureauDeskPicker.vue for the look step): the same nine steps in the same words, the
//  callout on the page's tray with the page's shadow, the real control ringed in brass with a
//  light dim everywhere else, and a flat light scrim for the welcome card and the look step.
//  The steps drive the Mac's own desks and rail, which Bureau lays out as the website does.
//

import SwiftUI

// MARK: - The website's steps

extension MacWelcomeTourCatalog {
    /// Anchor ids for the Bureau window's own controls (set in MacBureauHome and the rail).
    static let bureauHomeSearchAnchor = "bureau.home.search"
    static let bureauCompaniesAnchor = "bureau.companies"
    static let bureauFolderAnchor = "bureau.folder"

    /// The website's tour, step for step (welcomeTour.js, and the words in i18n.js).
    static let bureauPages: [MacWelcomeTourPage] = [
        MacWelcomeTourPage(
            id: "welcome", symbol: "",
            title: "Welcome to BSH Research Center",
            body: "Your research desk, memos, markets and Warren, in one place. Here's a quick tour."
        ),
        MacWelcomeTourPage(
            id: "home", symbol: "search",
            title: "Start with a company",
            body: "Home is where research begins. Search for a company or add a new one; your recent and followed companies stay a click away.",
            tips: [
                MacWelcomeTourTip(text: "Jump to any company, desk or ticker from anywhere.", symbol: "", keys: ["⌘", "K"]),
                MacWelcomeTourTip(text: "Adding a company opens its Research Desk.", symbol: ""),
            ],
            tab: .home,
            anchor: bureauHomeSearchAnchor
        ),
        MacWelcomeTourPage(
            id: "research", symbol: "building-2",
            title: "The Research Desk",
            body: "One workspace per company: profile, files, evidence, memos and decisions.",
            tips: [
                MacWelcomeTourTip(text: "Files with Use in report on ground the memo and Warren.", symbol: ""),
                MacWelcomeTourTip(text: "Record a decision, Invest, Pass or Watch, right from the desk.", symbol: ""),
            ],
            tab: .home,
            anchor: bureauCompaniesAnchor
        ),
        MacWelcomeTourPage(
            id: "folders", symbol: "folder-open",
            title: "Open a company like a folder",
            body: "Click a company in the sidebar and its pages open under it: Reports, News and its Research Desk, plus Market when it's listed.",
            tips: [
                MacWelcomeTourTip(text: "Reports and News show how many reports and headlines each holds.", symbol: ""),
                MacWelcomeTourTip(text: "Click the company again to close it, or use the arrow keys.", symbol: "", keys: ["←", "→"]),
            ],
            tab: .research,
            anchor: bureauFolderAnchor
        ),
        MacWelcomeTourPage(
            id: "memo", symbol: "file-text",
            title: "Investment memos",
            body: "Generate a late-stage or Buffett-style memo. It arrives as English and Simplified Chinese documents with cited sources, and Reports keeps every run.",
            tips: [
                MacWelcomeTourTip(text: "Start a new memo run.", symbol: "", keys: ["⌘", "N"]),
                MacWelcomeTourTip(text: "Open a memo in Memo Studio to review it section by section.", symbol: ""),
            ],
            tab: .documents,
            anchor: tabAnchor(.documents)
        ),
        MacWelcomeTourPage(
            id: "markets", symbol: "trending-up",
            title: "Markets, Pulse and News",
            body: "Market Radar holds your watchlists, live quotes, charts and alert rules, and they sync to iPhone, iPad and Mac.",
            tips: [
                MacWelcomeTourTip(text: "Pulse is the weekly market brief.", symbol: "bsh-pulse"),
                MacWelcomeTourTip(text: "The News desk follows the tape for the companies you cover.", symbol: "newspaper"),
                MacWelcomeTourTip(text: "Alert rules fire while you're away; the history is waiting when you're back.", symbol: "bell"),
            ],
            tab: .market,
            anchor: tabAnchor(.market)
        ),
        MacWelcomeTourPage(
            id: "tracking", symbol: "gauge",
            title: "Tracking",
            body: "Follow a company and it joins Tracking, which shows what changed since your last visit: filings, price moves, memo runs and news.",
            tips: [
                MacWelcomeTourTip(text: "The number on Tracking in the sidebar is how many companies you follow.", symbol: ""),
            ],
            tab: .portfolio,
            anchor: tabAnchor(.portfolio)
        ),
        // Near the end, once the app has been seen: the three designs, applied as they are
        // picked, with Bureau's desk colors. Home stays behind the callout.
        MacWelcomeTourPage(
            id: "look", symbol: "palette",
            title: "Choose a look",
            body: "Pick the design you like best. The whole app changes at once, and Settings can switch it any time.",
            tab: .home
        ),
        MacWelcomeTourPage(
            id: "warren", symbol: "",
            title: "Meet Warren",
            body: "Warren is the research assistant on every page. He reads the company you're looking at, its memo and its files, and answers with citations.",
            tips: [
                MacWelcomeTourTip(text: "Open him from the toolbar or any Ask Warren button.", symbol: ""),
                MacWelcomeTourTip(text: "Drag a memo point onto Warren to discuss it.", symbol: ""),
                MacWelcomeTourTip(text: "He answers to his name. Just say Warren.", symbol: ""),
            ],
            anchor: tabAnchor(.copilot)
        ),
    ]

    /// What the welcome card lists (the website's feature rows).
    static let bureauRows: [MacWelcomeTourRow] = [
        MacWelcomeTourRow(id: "home", symbol: "search", title: "Find a company",
                          body: "Search or add a company from Home. Everything about it lives on its Research Desk."),
        MacWelcomeTourRow(id: "memo", symbol: "file-text", title: "Generate an investment memo",
                          body: "A bilingual, source-cited memo from the company's files, in minutes."),
        MacWelcomeTourRow(id: "markets", symbol: "trending-up", title: "Watch the markets",
                          body: "Market Radar quotes and alerts, the weekly Pulse and the News desk."),
        MacWelcomeTourRow(id: "tracking", symbol: "gauge", title: "Track what changes",
                          body: "Follow companies and Tracking shows what moved since you last looked."),
        MacWelcomeTourRow(id: "warren", symbol: "", title: "Ask Warren",
                          body: "The research assistant who sees what's on your screen."),
    ]

    /// Where a step's callout goes beside its control, how round the control is (the
    /// spotlight is 8pt rounder), and how far the reported frame reaches past the control.
    static func bureauTarget(_ id: String) -> (beside: Bool, radius: CGFloat, inset: CGFloat) {
        switch id {
        case "home": return (false, 20, 0)
        case "research", "folders": return (true, 10, 0)
        case "memo", "markets", "tracking": return (true, 12, 0)
        // The Warren pill is reported with the 3pt its masthead slot adds round it.
        case "warren": return (false, 9999, 3)
        default: return (false, 10, 0)
        }
    }
}

// MARK: - Overlay

/// Resolves reported window frames against the overlay's own origin.
struct MacBureauWelcomeTourFrame: View {
    let origin: CGPoint
    let container: CGSize

    @EnvironmentObject private var anchors: MacTourAnchorStore

    var body: some View {
        MacBureauWelcomeTour(
            spotlight: { id in
                guard let frame = anchors.frames[id] else { return nil }
                return frame.offsetBy(dx: -origin.x, dy: -origin.y)
            },
            container: container
        )
    }
}

struct MacBureauWelcomeTour: View {
    var spotlight: (String) -> CGRect?
    var container: CGSize

    @EnvironmentObject private var store: MacAppStore
    @EnvironmentObject private var design: BSHDesignStore
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var calloutHeight: CGFloat = 0

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var pages: [MacWelcomeTourPage] { MacWelcomeTourCatalog.bureauPages }
    private var index: Int { min(max(0, store.welcomeTourStep), pages.count - 1) }
    private var page: MacWelcomeTourPage { pages[index] }
    private var isFirst: Bool { index == 0 }
    private var isLast: Bool { index >= pages.count - 1 }

    /// The control's box and 8pt round it, its corners 8pt rounder (WelcomeTour.vue measure()).
    private var spot: MacBureauTourSpot? {
        guard !page.isHero, let id = page.anchor, let frame = spotlight(id) else { return nil }
        let target = MacWelcomeTourCatalog.bureauTarget(page.id)
        let box = frame.insetBy(dx: target.inset, dy: target.inset)
        guard box.width > 0, box.height > 0 else { return nil }
        return MacBureauTourSpot(rect: box.insetBy(dx: -8, dy: -8), radius: target.radius + 8)
    }

    var body: some View {
        if store.showWelcomeTour {
            let spot = self.spot
            let width = calloutWidth
            let origin = calloutOrigin(spot: spot, width: width)
            ZStack(alignment: .topLeading) {
                MacBureauTourDim(spot: spot, dark: colorScheme == .dark, ink: ink)
                    .contentShape(Rectangle())
                    // Tapping the dimmed area moves on, the way Apple's coach marks do.
                    .onTapGesture { if !page.isHero { advance() } }
                    .accessibilityHidden(true)

                callout(width: width)
                    .background {
                        GeometryReader { geo in
                            Color.clear
                                .onAppear { calloutHeight = geo.size.height }
                                .onChange(of: geo.size.height) { _, height in calloutHeight = height }
                        }
                    }
                    .offset(x: origin.x, y: origin.y)
            }
            .frame(width: container.width, height: container.height, alignment: .topLeading)
            .animation(reduceMotion ? nil : .timingCurve(0.2, 0.9, 0.3, 1, duration: 0.4), value: store.welcomeTourStep)
            .background {
                // Esc leaves the tour, like the command palette.
                Button("") { store.completeWelcomeTour() }
                    .keyboardShortcut(.cancelAction)
                    .frame(width: 0, height: 0)
                    .opacity(0)
            }
            .onChange(of: store.welcomeTourStep) { _, _ in followStep() }
            .onAppear {
                #if DEBUG
                // QA: open the tour on a given step (`-bsh.launchWelcomeStep 3`).
                let step = UserDefaults.standard.integer(forKey: "bsh.launchWelcomeStep")
                if step > 0, store.welcomeTourStep == 0 { store.welcomeTourStep = min(step, pages.count - 1) }
                #endif
                followStep()
            }
            .accessibilityIdentifier("welcome-tour")
        }
    }

    // MARK: Where the tour takes the window

    /// The folders step opens a company's page, and with it the company's folder on the rail:
    /// the one opened last, else the one at the top of the rail.
    private func followStep() {
        guard store.showWelcomeTour, page.id == "folders", let company = tourCompany else { return }
        if store.heldCompanyId != company.id || store.selectedTab != .research {
            store.openCompanyPage(company)
        }
    }

    private var tourCompany: MacCompany? {
        if let selected = store.selectedCompany, let company = store.companies.first(where: { $0.id == selected.id }) {
            return company
        }
        let sort = MacCompanySort(rawValue: UserDefaults.standard.string(forKey: "bsh.sidebar.companySort") ?? "") ?? .az
        return MacCompanySort.apply(
            sort, to: store.companies,
            followed: Set(store.followedCompanyIds),
            visits: store.visitedCompanyTimestamps
        ).first
    }

    private func advance() {
        if isLast {
            store.completeWelcomeTour()
        } else {
            store.welcomeTourStep = index + 1
        }
    }

    private func goTo(_ next: Int) {
        let clamped = min(max(0, next), pages.count - 1)
        guard clamped != index else { return }
        store.welcomeTourStep = clamped
    }

    // MARK: Placement (WelcomeTour.vue calloutStyle)

    private var calloutWidth: CGFloat {
        let room = max(280, container.width - 32)
        return min(page.isHero || page.choosesLook ? 560 : 380, room)
    }

    private func calloutOrigin(spot: MacBureauTourSpot?, width: CGFloat) -> CGPoint {
        let vw = container.width
        let vh = container.height
        guard let spot, !page.isHero else {
            let height = calloutHeight > 0 ? calloutHeight : 400
            return CGPoint(x: (vw - width) / 2, y: (vh - height) / 2)
        }
        let s = spot.rect
        func clamp(_ value: CGFloat, _ low: CGFloat, _ high: CGFloat) -> CGFloat { max(low, min(high, value)) }
        if MacWelcomeTourCatalog.bureauTarget(page.id).beside {
            let right = s.maxX + 14
            let fitsRight = right + width + 16 <= vw
            var left = fitsRight ? right : s.minX - width - 14
            if left < 16 { left = fitsRight ? right : 16 }
            return CGPoint(x: left, y: clamp(s.midY - 150, 16, max(16, vh - 340)))
        }
        let left = clamp(s.midX - width / 2, 16, max(16, vw - width - 16))
        let below = s.maxY + 14
        let top = below + 300 + 16 <= vh ? below : max(16, s.minY - 300 - 14)
        return CGPoint(x: left, y: top)
    }

    // MARK: Callout

    private func callout(width: CGFloat) -> some View {
        let maxHeight = min(container.height * 0.92, 720)
        return VStack(spacing: 0) {
            ViewThatFits(in: .vertical) {
                calloutBody
                ScrollView(.vertical, showsIndicators: false) { calloutBody }
            }
            footer
        }
        .frame(width: width)
        .frame(maxHeight: maxHeight)
        .fixedSize(horizontal: false, vertical: true)
        .background(RoundedRectangle(cornerRadius: 16, style: .circular).fill(ink.tray))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .circular))
        .overlay(alignment: .topTrailing) {
            if !isLast {
                MacBureauTourCloseButton { store.completeWelcomeTour() }
                    .padding(10)
                    .accessibilityIdentifier("welcome-tour-skip")
            }
        }
        .background { MacBureauSheetShadow(radius: 16, ink: ink) }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private var calloutBody: some View {
        if page.isHero {
            heroBody
                .padding(.top, 40)
                .padding(.horizontal, 32)
                .padding(.bottom, 4)
        } else {
            stepBody
                .padding(.top, 24)
                .padding(.horizontal, 24)
                .padding(.bottom, 4)
        }
    }

    /// The welcome card: the house seal, the title in the serif, what the app does.
    private var heroBody: some View {
        VStack(spacing: 0) {
            MacBureauTourSeal(ink: ink)
            Text(page.title)
                .font(.custom(BSHType.bureauSerif, size: 36))
                .tracking(-0.36)
                .foregroundStyle(ink.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .bureauLines(40, size: 36, em: 1.30)
                .padding(.top, 20)
                .accessibilityIdentifier("welcome-tour-title")
            // max-width: 40ch, at Instrument Sans's figure width.
            Text(page.body)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .bureauLines(20, size: 14)
                .frame(maxWidth: 372.96)
                .padding(.top, 8)
            VStack(alignment: .leading, spacing: 16) {
                ForEach(MacWelcomeTourCatalog.bureauRows) { row in
                    HStack(alignment: .top, spacing: 16) {
                        Group {
                            if row.usesWarrenPortrait {
                                MacBureauWarrenPortrait(size: 36, ink: ink)
                            } else {
                                LucideIcon(row.symbol, size: 20).foregroundStyle(ink.accentInk)
                            }
                        }
                        .frame(width: 40, height: 40)
                        .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(ink.accentSoft))
                        VStack(alignment: .leading, spacing: 0) {
                            Text(row.title)
                                .font(BSHType.bureauSans(15, weight: .semibold))
                                .tracking(-0.15)
                                .foregroundStyle(ink.ink)
                                .bureauLines(20, size: 15)
                            Text(row.body)
                                .font(BSHType.bureauSans(13))
                                .tracking(-0.039)
                                .foregroundStyle(ink.muted)
                                .fixedSize(horizontal: false, vertical: true)
                                .bureauLines(18, size: 13)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 28)
        }
        .frame(maxWidth: .infinity)
    }

    /// A step on the real screen: compact, left-aligned, beside the control it describes.
    private var stepBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                MacBureauTourGlyph(page: page, ink: ink)
                VStack(alignment: .leading, spacing: 0) {
                    Text(page.title)
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.15)
                        .foregroundStyle(ink.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .bureauLines(20, size: 15)
                        .accessibilityIdentifier("welcome-tour-title")
                    Text(page.body)
                        .font(BSHType.bureauSans(13))
                        .tracking(-0.039)
                        .foregroundStyle(ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .bureauLines(18, size: 13)
                        .padding(.top, 6)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.trailing, 24)
            }

            // The look step: the designs as cards and, once Bureau is picked, its desks.
            if page.choosesLook {
                MacBureauLookCards(selection: $design.design, desk: design.bureauDesk, ink: ink)
                    .padding(.top, 16)
                    .accessibilityIdentifier("welcome-tour-designs")
                if design.design == .bureau {
                    VStack(alignment: .leading, spacing: 0) {
                        MacBureauKicker("Desk color")
                            .padding(.bottom, 8)
                        MacBureauDeskSwatches(selection: $design.bureauDesk)
                    }
                    .padding(.top, 16)
                    .accessibilityIdentifier("welcome-tour-desks")
                }
            }

            if !page.tips.isEmpty {
                VStack(spacing: 8) {
                    ForEach(page.tips) { tip in
                        MacBureauTourTip(tip: tip, ink: ink)
                    }
                }
                .padding(.top, 16)
            }
        }
    }

    // MARK: Footer

    private var footer: some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                ForEach(pages.indices, id: \.self) { dot in
                    let current = dot == index
                    Button {
                        goTo(dot)
                    } label: {
                        Circle()
                            .fill(current ? ink.accent : ink.ink(0.18))
                            .frame(width: 8, height: 8)
                            .scaleEffect(current ? 1.15 : 1)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Page \(dot + 1) of \(pages.count)")
                    .accessibilityAddTraits(current ? .isSelected : [])
                }
            }
            .frame(maxWidth: .infinity)

            HStack(spacing: 8) {
                if !isFirst {
                    MacBureauButton("Back", icon: "chevron-left", kind: .plain) {
                        store.welcomeTourStep = index - 1
                    }
                    .accessibilityIdentifier("welcome-tour-back")
                }
                Spacer(minLength: 0)
                Button(action: advance) {
                    Text(isLast ? "Get started" : "Continue")
                        .frame(minWidth: 152 - 28)
                }
                .buttonStyle(MacBureauPillStyle(kind: .filled))
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("welcome-tour-next")
            }

            if page.isHero {
                Text("You can replay this tour any time from Settings.")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.subtle)
                    .multilineTextAlignment(.center)
                    .bureauLines(14, size: 11)
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(.top, page.isHero ? 8 : 12)
        .padding(.horizontal, page.isHero ? 32 : 24)
        .padding(.bottom, page.isHero ? 28 : 20)
    }
}

// MARK: - The dim

struct MacBureauTourSpot: Equatable {
    let rect: CGRect
    let radius: CGFloat
}

/// Flat for the welcome card and the look step; otherwise a cutout round the control, ringed
/// in brass with a glow, as the website's spotlight's shadows draw it (all of them outside
/// the control only, the dim on top).
private struct MacBureauTourDim: View {
    let spot: MacBureauTourSpot?
    let dark: Bool
    let ink: MacBureauPageInk

    var body: some View {
        if let spot {
            let s = spot.rect
            ZStack(alignment: .topLeading) {
                // 0 0 26px -2px glow / 0.65
                rounded(s.insetBy(dx: 2, dy: 2), spot.radius - 2)
                    .fill(ink.accentGlow(dark ? 0.7 : 0.65))
                    .blur(radius: dark ? 15 : 13)
                // 0 0 0 5px accent / 0.22
                rounded(s.insetBy(dx: -5, dy: -5), spot.radius + 5)
                    .fill(ink.accent.opacity(dark ? 0.26 : 0.22))
                // 0 0 0 2px accent / 0.9
                rounded(s.insetBy(dx: -2, dy: -2), spot.radius + 2)
                    .fill(ink.accent.opacity(dark ? 0.95 : 0.9))
                // 0 0 0 9999px black: the dim, light enough to read the page through.
                Rectangle().fill(Color.black.opacity(dark ? 0.26 : 0.16))
            }
            .compositingGroup()
            .mask {
                Rectangle()
                    .overlay(alignment: .topLeading) {
                        rounded(s, spot.radius).fill(Color.black).blendMode(.destinationOut)
                    }
                    .compositingGroup()
            }
        } else {
            Rectangle().fill(Color.black.opacity(dark ? 0.34 : 0.24))
        }
    }

    /// A rounded box at `rect`, its corners clamped as CSS clamps them.
    private func rounded(_ rect: CGRect, _ radius: CGFloat) -> some Shape {
        MacBureauPlacedRoundedRect(rect: rect, radius: max(0, min(radius, min(rect.width, rect.height) / 2)))
    }
}

/// A rounded rectangle drawn at a fixed place in its container, so it animates as a shape.
private struct MacBureauPlacedRoundedRect: Shape {
    var rect: CGRect
    var radius: CGFloat

    var animatableData: AnimatablePair<AnimatablePair<CGFloat, CGFloat>, AnimatablePair<AnimatablePair<CGFloat, CGFloat>, CGFloat>> {
        get {
            AnimatablePair(
                AnimatablePair(rect.origin.x, rect.origin.y),
                AnimatablePair(AnimatablePair(rect.size.width, rect.size.height), radius)
            )
        }
        set {
            rect = CGRect(
                x: newValue.first.first, y: newValue.first.second,
                width: newValue.second.first.first, height: newValue.second.first.second
            )
            radius = newValue.second.second
        }
    }

    func path(in _: CGRect) -> Path {
        Path(roundedRect: rect, cornerRadius: radius, style: .circular)
    }
}

// MARK: - Pieces

/// `--shadow-sheet`: a hairline round the paper and the shadow it casts on the page.
struct MacBureauSheetShadow: View {
    let radius: CGFloat
    let ink: MacBureauPageInk

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        ZStack {
            if ink.dark {
                // 0 26px 60px -22px rgb(0 0 0 / 0.8)
                Rectangle()
                    .fill(Color.black.opacity(0.8))
                    .padding(22)
                    .offset(y: 26)
                    .blur(radius: 30)
            } else {
                // 0 26px 60px -26px shadow / 0.5, 0 6px 16px -8px shadow / 0.18
                Rectangle()
                    .fill(ink.shadow(0.5))
                    .padding(26)
                    .offset(y: 26)
                    .blur(radius: 30)
                RoundedRectangle(cornerRadius: max(0, radius - 8), style: .circular)
                    .fill(ink.shadow(0.18))
                    .padding(8)
                    .offset(y: 6)
                    .blur(radius: 8)
            }
            // 0 0 0 1px: ink / 0.08 by day, white / 0.08 by night.
            shape
                .inset(by: -0.5)
                .stroke(ink.dark ? Color.white.opacity(0.08) : ink.ink(0.08), lineWidth: 1)
        }
        .allowsHitTesting(false)
    }
}

/// `.welcome-tour-hero-tile`: the house mark on a tile of lit paper.
private struct MacBureauTourSeal: View {
    let ink: MacBureauPageInk

    /// `--color-surface-muted`, which the tile's light runs down to by day.
    private var muted: Color {
        BSHBureauDesk.active == .onyx ? .bshFixed(BSHRGB(226, 224, 218)) : .bshFixed(BSHRGB(233, 228, 216))
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 22, style: .circular)
        BSHBrandMarkShape()
            .fill(ink.ink)
            .frame(width: 44, height: 28)
            .frame(width: 88, height: 88)
            .background {
                shape.fill(LinearGradient(
                    colors: ink.dark
                        ? [Color.white.opacity(0.12), Color.white.opacity(0.04)]
                        : [Color.white.opacity(0.98), muted],
                    startPoint: .top, endPoint: .bottom
                ))
            }
            // inset 0 1px 0: light along the top edge.
            .overlay {
                ZStack {
                    shape.fill(Color.white.opacity(ink.dark ? 0.2 : 0.9))
                    shape.fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                }
                .compositingGroup()
                .allowsHitTesting(false)
            }
            // 0 0 0 0.5px, and 0 12px 28px -10px.
            .background {
                shape.inset(by: -0.25).stroke(ink.dark ? Color.white.opacity(0.14) : Color.black.opacity(0.1), lineWidth: 0.5)
            }
            .background {
                shape
                    .fill(ink.dark ? Color.black.opacity(0.6) : ink.accentGlow(0.45))
                    .padding(10)
                    .offset(y: 12)
                    .blur(radius: 14)
            }
            .accessibilityHidden(true)
    }
}

/// `.welcome-tour-glyph`: the step's glyph in brass on a tile of brass wash; Warren's
/// portrait on his own step.
private struct MacBureauTourGlyph: View {
    let page: MacWelcomeTourPage
    let ink: MacBureauPageInk

    var body: some View {
        Group {
            if page.usesWarrenPortrait {
                MacBureauWarrenPortrait(size: 38, ink: ink)
                    .frame(width: 44, height: 44)
            } else {
                LucideIcon(page.symbol, size: 20)
                    .foregroundStyle(ink.accentInk)
                    .frame(width: 44, height: 44)
                    .background(RoundedRectangle(cornerRadius: 13, style: .circular).fill(ink.accentSoft))
                    .overlay(RoundedRectangle(cornerRadius: 13, style: .circular).strokeBorder(ink.accent.opacity(0.12), lineWidth: 0.5))
            }
        }
        .accessibilityHidden(true)
    }
}

/// Warren's portrait (WarrenMark.vue): a hairline of ink round it and a breath of shadow.
struct MacBureauWarrenPortrait: View {
    let size: CGFloat
    let ink: MacBureauPageInk

    var body: some View {
        Image("AskMark")
            .renderingMode(.original)
            .resizable()
            .interpolation(.high)
            .scaledToFill()
            .frame(width: size, height: size)
            .clipShape(Circle())
            .background(Circle().inset(by: -0.25).stroke(ink.ink(0.14), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.08), radius: 1, y: 1)
            .accessibilityHidden(true)
    }
}

/// `.welcome-tour-tip`: a band of the tray's fill, a brass dot or glyph, the line, its keys.
private struct MacBureauTourTip: View {
    let tip: MacWelcomeTourTip
    let ink: MacBureauPageInk

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Group {
                if tip.symbol.isEmpty {
                    Circle().fill(ink.accent).frame(width: 6, height: 6)
                } else {
                    LucideIcon(tip.symbol, size: 15).foregroundStyle(ink.accentInk)
                }
            }
            .frame(width: 24, height: 24)
            Text(tip.text)
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.ink)
                .fixedSize(horizontal: false, vertical: true)
                .bureauLines(16, size: 12)
                .frame(maxWidth: .infinity, alignment: .leading)
            if !tip.keys.isEmpty {
                HStack(spacing: 2) {
                    ForEach(tip.keys, id: \.self) { key in
                        MacBureauKeyCap(key: key, ink: ink)
                    }
                }
                .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(ink.fillTertiary))
    }
}

/// `.kbd` under Bureau: fresh paper, ruled in ink, with a line under it.
private struct MacBureauKeyCap: View {
    let key: String
    let ink: MacBureauPageInk

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 5, style: .circular)
        Text(key)
            .font(BSHType.bureauSans(11, weight: .medium))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .fixedSize()
            .bureauLines(14, size: 11)
            .padding(.horizontal, 4)
            .frame(minWidth: 20, minHeight: 20)
            .background(shape.fill(ink.raised))
            .overlay(shape.strokeBorder(ink.ink(0.14), lineWidth: 1))
            // 0 1px 0 ink / 0.1: a line along the cap's foot.
            .background(shape.fill(ink.ink(0.1)).offset(y: 1))
    }
}

/// `.icon-btn` with the tour's ×: muted ink, lit on hover.
private struct MacBureauTourCloseButton: View {
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            LucideIcon("x", size: 15)
                .foregroundStyle(hovered ? ink.ink : ink.muted)
                .frame(width: 32, height: 32)
                .background(Circle().fill(hovered ? ink.ink(0.07) : .clear))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help("Skip the tour")
        .accessibilityLabel("Skip the tour")
    }
}

// MARK: - Choose a look

/// DesignLookCards.vue: the three designs as cards, each with a miniature of its ground and
/// page, painted in the design's own colors; picking one applies it at once.
private struct MacBureauLookCards: View {
    @Binding var selection: BSHDesign
    let desk: BSHBureauDesk
    let ink: MacBureauPageInk

    private static let order: [BSHDesign] = [.glass, .bureau, .folio]

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            ForEach(Self.order) { option in
                MacBureauLookCard(design: option, chosen: selection == option, desk: desk, ink: ink) {
                    selection = option
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct MacBureauLookCard: View {
    let design: BSHDesign
    let chosen: Bool
    let desk: BSHBureauDesk
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    private var name: String {
        switch design {
        case .glass: return "Summit Glass"
        case .bureau: return "Bureau"
        case .folio: return "Folio"
        }
    }

    private var line: String {
        switch design {
        case .glass: return "The original: calm white cards and glass, like the Mac app."
        case .bureau: return "The page laid on a desk, with the desks as tabs along its top."
        case .folio: return "Paper and ink, with titles in a book serif."
        }
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 13, style: .circular)
        Button(action: action) {
            VStack(alignment: .leading, spacing: 9) {
                MacBureauLookPreview(design: design, desk: desk, dark: ink.dark)
                    .frame(height: 62)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(name)
                            .font(BSHType.bureauSans(13, weight: .semibold))
                            .foregroundStyle(ink.ink)
                            .fixedSize()
                            .bureauLines(17, size: 13)
                        if design == BSHDesign.defaultDesign {
                            Text("Default")
                                .font(BSHType.bureauSans(10, weight: .semibold))
                                .tracking(0.2)
                                .foregroundStyle(ink.accentInk)
                                .fixedSize()
                                .bureauLines(16, size: 10)
                                .padding(.horizontal, 6)
                                .background(Capsule().fill(ink.accentSoft))
                        }
                    }
                    Text(line)
                        .font(BSHType.bureauSans(11.5))
                        .foregroundStyle(ink.muted)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .bureauLines(15, size: 11.5)
                }
                .padding(.horizontal, 2)
            }
            .padding(.top, 8)
            .padding(.horizontal, 8)
            .padding(.bottom, 11)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(shape.fill(chosen ? ink.accent.opacity(0.07) : (hovered ? ink.fillSecondary : ink.fillTertiary)))
            .overlay(shape.strokeBorder(chosen ? ink.accent : ink.ink(0.07), lineWidth: chosen ? 2 : 1))
            .overlay(alignment: .topTrailing) {
                if chosen {
                    LucideIcon("check", size: 12)
                        .foregroundStyle(.white)
                        .frame(width: 20, height: 20)
                        .background(Circle().fill(ink.accent))
                        .shadow(color: .black.opacity(0.25), radius: 1.5, y: 1)
                        .padding(12)
                }
            }
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .accessibilityLabel(name)
        .accessibilityValue(line)
        .accessibilityAddTraits(chosen ? .isSelected : [])
        .accessibilityIdentifier("design-look-\(design.rawValue)")
    }
}

/// A design's miniature: its ground, and its page with a title line and an accent mark.
private struct MacBureauLookPreview: View {
    let design: BSHDesign
    let desk: BSHBureauDesk
    let dark: Bool

    /// The website's swatch colors for each desk (design.js BUREAU_DESK_COLORS).
    private var deskColors: (desk: Color, sheet: Color) {
        let hex: (String, String, String, String)
        switch desk {
        case .onyx: hex = ("ffffff", "050505", "f1f0ec", "181818")
        case .green: hex = ("0f1f1a", "080d0b", "f7f4ec", "151d1a")
        case .maroon: hex = ("50121e", "16060a", "f7f4ec", "231318")
        case .navy: hex = ("101c34", "060910", "f7f4ec", "141923")
        case .aubergine: hex = ("30162e", "0c070c", "f7f4ec", "1e161e")
        case .tobacco: hex = ("362212", "0b0805", "f7f4ec", "221b16")
        case .graphite: hex = ("1e2228", "08090b", "f7f4ec", "191c22")
        }
        return (Self.hex(dark ? hex.1 : hex.0), Self.hex(dark ? hex.3 : hex.2))
    }

    private static func hex(_ value: String) -> Color {
        let n = Int(value, radix: 16) ?? 0
        return .bshFixed(BSHRGB(Double((n >> 16) & 255), Double((n >> 8) & 255), Double(n & 255)))
    }

    var body: some View {
        let frame = RoundedRectangle(cornerRadius: 8, style: .circular)
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .topLeading) {
                ground
                // inset 0 0 0 1px: under the page, which covers it where it runs off the edge.
                frame.strokeBorder(dark ? Color.white.opacity(0.1) : Color.black.opacity(0.08), lineWidth: 1)
                page(width: w)
            }
            .frame(width: w, height: 62, alignment: .topLeading)
        }
        .frame(height: 62)
        .clipShape(frame)
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private var ground: some View {
        switch design {
        case .glass:
            Canvas { context, size in
                context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Self.hex(dark ? "141417" : "eef0f4")))
                // radial-gradient(90% 120% at 8% 0%, sky / 0.22, transparent 62%)
                let rx = size.width * 0.9, ry = size.height * 1.2
                let sky = Color.bshFixed(BSHRGB(56, 168, 232), opacity: dark ? 0.16 : 0.22)
                context.translateBy(x: size.width * 0.08, y: 0)
                context.scaleBy(x: 1, y: ry / rx)
                context.fill(
                    Path(CGRect(x: -size.width, y: -size.height * rx / ry, width: size.width * 3, height: size.height * 3 * rx / ry)),
                    with: .radialGradient(
                        Gradient(stops: [.init(color: sky, location: 0), .init(color: sky.opacity(0), location: 0.62)]),
                        center: .zero, startRadius: 0, endRadius: rx
                    )
                )
            }
        case .bureau:
            deskColors.desk
        case .folio:
            Self.hex(dark ? "161513" : "f4f2ed")
        }
    }

    /// The page, placed as the website insets it, with its title line and accent mark.
    @ViewBuilder
    private func page(width: CGFloat) -> some View {
        switch design {
        case .glass:
            let size = CGSize(width: width - 40, height: 43)
            let shape = RoundedRectangle(cornerRadius: 6, style: .circular)
            marks(ink: Self.hex(dark ? "f2f2f4" : "1d1d1f"), accent: Self.hex(dark ? "38a8e8" : "0b87d6"), width: size.width)
                .frame(width: size.width, height: size.height, alignment: .topLeading)
                .background(shape.fill(Self.hex(dark ? "232327" : "ffffff")))
                .background(shape.inset(by: -0.25).stroke(dark ? Color.white.opacity(0.12) : Color.black.opacity(0.1), lineWidth: 0.5))
                // 0 4px 10px -4px
                .background(shape.fill(Color.black.opacity(dark ? 0.5 : 0.2)).padding(4).offset(y: 4).blur(radius: 5))
                .offset(x: 30, y: 10)
        case .bureau:
            let size = CGSize(width: width - 24, height: 48)
            let shape = UnevenRoundedRectangle(topLeadingRadius: 6, topTrailingRadius: 6, style: .circular)
            marks(ink: Self.hex(dark ? "eae5d6" : "181818"), accent: Self.hex(dark ? "d6b268" : "b08a42"), width: size.width)
                .frame(width: size.width, height: size.height, alignment: .topLeading)
                .background(shape.fill(deskColors.sheet))
                .background(shape.inset(by: -0.5).stroke(dark ? Color.white.opacity(0.07) : Color.black.opacity(0.1), lineWidth: 1))
                .offset(x: 18, y: 14)
        case .folio:
            let size = CGSize(width: width - 24, height: 53)
            let shape = UnevenRoundedRectangle(topLeadingRadius: 3, topTrailingRadius: 3, style: .circular)
            marks(ink: Self.hex(dark ? "ece8df" : "1c1a17"), accent: Self.hex(dark ? "8193ff" : "263cd4"), width: size.width)
                .frame(width: size.width, height: size.height, alignment: .topLeading)
                .background(shape.fill(Self.hex(dark ? "211f1c" : "fbfaf7")))
                .background(shape.inset(by: -0.5).stroke(dark ? Color.white.opacity(0.12) : Color.bshFixed(BSHRGB(28, 26, 23), opacity: 0.16), lineWidth: 1))
                .offset(x: 12, y: 9)
        }
    }

    /// A title line (42% of the page, the page's ink at half strength) and an accent mark.
    private func marks(ink: Color, accent: Color, width: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 2, style: .circular)
                .fill(ink.opacity(0.5))
                .frame(width: width * 0.42, height: 4)
                .offset(x: 8, y: 8)
            RoundedRectangle(cornerRadius: 2, style: .circular)
                .fill(accent)
                .frame(width: 18, height: 4)
                .offset(x: 8, y: 17)
        }
    }
}

extension View {
    /// Mark this view as something the tour can spotlight, while `active`.
    @ViewBuilder
    func macWelcomeTourAnchor(_ id: String, when active: Bool) -> some View {
        if active {
            macWelcomeTourAnchor(id)
        } else {
            self
        }
    }
}
