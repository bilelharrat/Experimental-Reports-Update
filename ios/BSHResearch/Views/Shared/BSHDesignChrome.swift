//
//  BSHDesignChrome.swift
//  BSHResearch (iPhone, iPad)
//
//  The app's shell in each design (BSHDesign). The desks themselves only use the tokens
//  and components in ResearchDesign.swift; this file is where the shell changes shape:
//
//  - Summit Glass: the floating glass travel bar and the glass rail (RootView), untouched.
//  - Folio: paper throughout. The desk bar is ruled off the page and the desk you are on
//    is set in solid ink; on the iPad rail the chosen row is a bookmark.
//  - Bureau: the page lies on a green desk. On iPhone and portrait iPad the page's bottom
//    edge rests on the desk and the desk you are on is a tab cut from the page; on the
//    landscape iPad rail the desks are written on the green in ivory and the chosen one
//    is a tab of the sheet reaching into the rail.
//

import SwiftUI
import UIKit

// MARK: - Lists and forms on paper

extension View {
    /// A List or Form's ground: the design's paper under Bureau and Folio (the system's
    /// grouped background is hidden), untouched under Summit Glass.
    @ViewBuilder
    func bshListSurface() -> some View {
        if BSHDesign.active.isPaper {
            self.scrollContentBackground(.hidden)
                .background(Color.dsCanvas)
        } else {
            self
        }
    }

    /// A List or Form's rows: Bureau's trays pressed into the sheet, Folio's fresher
    /// sheets (`.card`), or rows written straight on the page (`.bare`, for plain lists),
    /// ruled with the design's hairline. Apply it to the list's content (a Group around
    /// its sections) or to a row; a row's own `listRowBackground` still wins.
    @ViewBuilder
    func bshListRows(_ ground: BSHListRowGround = .card) -> some View {
        if BSHDesign.active.isPaper {
            self.listRowBackground(ground == .card ? Color.dsCard : Color.clear)
                .listRowSeparatorTint(Color.dsHairline)
        } else {
            self
        }
    }
}

enum BSHListRowGround {
    case card
    case bare
}

/// A list section's title. Under Summit Glass it is the system's header, untouched. On
/// paper a prominent header (`.headerProminence(.increased)`) is set in the design's
/// serif, and a standard one as the design's kicker: Bureau's italic serif, Folio's
/// small tracked capitals.
struct BSHSectionTitle: View {
    let title: String
    @Environment(\.headerProminence) private var prominence

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        if !BSHDesign.active.isPaper {
            Text(verbatim: title)
        } else if prominence == .increased {
            Text(verbatim: title)
                .font(BSHType.heading(19))
                .foregroundStyle(Color.dsInk)
                .textCase(nil)
        } else {
            Text(verbatim: title)
                .font(BSHType.kicker(12))
                .tracking(BSHType.kickerIsCapitals ? 0.8 : 0)
                .textCase(BSHType.kickerIsCapitals ? .uppercase : nil)
        }
    }
}

// MARK: - UIKit bars

/// The bars UIKit draws for SwiftUI (navigation bars, segmented pickers) take their look
/// from appearance proxies, which only reach bars created afterwards. The app rebuilds
/// its windows when the design changes, so `BSHDesignStore` calls `apply` first.
enum BSHUIKitChrome {
    @MainActor
    static func apply(_ design: BSHDesign) {
        let bar = UINavigationBar.appearance()
        let segments = UISegmentedControl.appearance()
        guard design.isPaper, let ink = BSHPalette.ink else {
            // Summit Glass: the system's own bars.
            bar.standardAppearance = UINavigationBarAppearance()
            bar.compactAppearance = nil
            bar.scrollEdgeAppearance = nil
            bar.compactScrollEdgeAppearance = nil
            bar.tintColor = nil
            segments.selectedSegmentTintColor = nil
            segments.setTitleTextAttributes(nil, for: .selected)
            return
        }

        let inkColor = UIColor(ink)
        let titleAttributes: [NSAttributedString.Key: Any] = [
            .font: titleFont(design, size: 17),
            .foregroundColor: inkColor,
        ]
        let largeTitleAttributes: [NSAttributedString.Key: Any] = [
            .font: titleFont(design, size: 34),
            .foregroundColor: inkColor,
        ]

        // Scrolled: paper ruled off from the page below. At rest: the page itself.
        let standard = UINavigationBarAppearance()
        standard.configureWithOpaqueBackground()
        standard.backgroundColor = UIColor(Color.dsCanvas)
        standard.shadowColor = UIColor(Color.dsHairline)
        standard.titleTextAttributes = titleAttributes
        standard.largeTitleTextAttributes = largeTitleAttributes

        let atRest = standard.copy()
        atRest.shadowColor = .clear

        bar.standardAppearance = standard
        bar.compactAppearance = standard
        bar.scrollEdgeAppearance = atRest
        bar.compactScrollEdgeAppearance = atRest
        bar.tintColor = UIColor(Color.dsAccent)

        switch design {
        case .folio:
            // Folio sets the chosen segment in solid ink, as on the website.
            segments.selectedSegmentTintColor = UIColor(BSHPalette.folioInk)
            segments.setTitleTextAttributes([.foregroundColor: UIColor(BSHPalette.folioOnInk)], for: .selected)
        default:
            segments.selectedSegmentTintColor = UIColor(Color.dsRaised)
            segments.setTitleTextAttributes(nil, for: .selected)
        }
    }

    /// Bureau's Instrument Serif runs lighter and narrower than SF, so it is set larger;
    /// Folio's Iowan Old Style is set bold at SF's size.
    private static func titleFont(_ design: BSHDesign, size: CGFloat) -> UIFont {
        switch design {
        case .bureau:
            return UIFont(name: BSHType.bureauSerif, size: (size * 1.3).rounded())
                ?? .systemFont(ofSize: size, weight: .semibold)
        case .folio:
            let roman = UIFont(name: BSHType.folioSerif, size: size)
            if let bold = roman?.fontDescriptor.withSymbolicTraits(.traitBold) {
                return UIFont(descriptor: bold, size: size)
            }
            return roman ?? .systemFont(ofSize: size, weight: .semibold)
        case .glass:
            return .systemFont(ofSize: size, weight: .semibold)
        }
    }
}

// MARK: - The desk bar (iPhone, portrait iPad)

/// A desk's icon in the bars: its SF Symbol, or the Pulse trace.
struct BSHDeskTabIcon: View {
    let tab: AppTab
    var selected: Bool
    var size: CGFloat = 16

    var body: some View {
        if let symbol = tab.systemImage {
            Image(systemName: symbol)
                .font(.system(size: size, weight: selected ? .semibold : .regular))
        } else {
            Image(uiImage: PulseECGTabIcon.makeImage(pointSize: size))
                .resizable()
                .renderingMode(.template)
                .scaledToFit()
                .frame(width: size + 4, height: size)
        }
    }
}

/// Bureau: the page (the desks above) rests on the green desk; the desks are written on
/// the desk in ivory, and the one you are on is a tab of the page itself, hanging from
/// its bottom edge and flaring into it.
struct BureauDeskBar: View {
    @Binding var selection: AppTab
    @EnvironmentObject private var language: LanguageStore
    @Namespace private var tabSpace

    /// The page's bottom corners; the bar keeps its tabs clear of them.
    static let pageRadius: CGFloat = 22
    static let flare: CGFloat = 10
    static let tabHeight: CGFloat = 50

    var body: some View {
        HStack(spacing: 0) {
            ForEach(AppTab.allCases) { tab in
                button(tab)
            }
        }
        .padding(.horizontal, Self.pageRadius + Self.flare)
        .padding(.bottom, 4)
    }

    private func button(_ tab: AppTab) -> some View {
        let isSelected = selection == tab
        return Button {
            guard selection != tab else { return }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                selection = tab
            }
        } label: {
            VStack(spacing: 3) {
                BSHDeskTabIcon(tab: tab, selected: isSelected, size: 16)
                    .foregroundStyle(isSelected ? Color.dsAccent : BSHPalette.bureauOnFrame.opacity(0.6))
                    .frame(height: 20)
                Text(language.t(tab.titleKey))
                    .font(.system(size: 10, weight: isSelected ? .semibold : .medium))
                    .foregroundStyle(isSelected ? BSHPalette.bureauInk : BSHPalette.bureauOnFrame.opacity(0.66))
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
            .padding(.horizontal, 3)
            .frame(maxWidth: .infinity)
            .frame(height: Self.tabHeight)
            .background(alignment: .top) {
                if isSelected {
                    // Reaches a point up into the page so no seam shows where they meet.
                    BSHJoinedTabShape(join: .top, radius: Self.flare)
                        .fill(BSHPalette.bureauSheet)
                        .padding(.top, -1)
                        .matchedGeometryEffect(id: "bureauDeskTab", in: tabSpace)
                }
            }
            .contentShape(Rectangle())
            .welcomeTourAnchor(WelcomeTourCatalog.tabAnchor(tab))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.t(tab.titleKey))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

/// Folio: the desks on the page's own paper, ruled off above; the one you are on is set
/// in solid ink, its name knocked out in paper.
struct FolioDeskBar: View {
    @Binding var selection: AppTab
    @EnvironmentObject private var language: LanguageStore
    @Namespace private var tabSpace

    var body: some View {
        HStack(spacing: 2) {
            ForEach(AppTab.allCases) { tab in
                button(tab)
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 6)
        .padding(.bottom, 4)
    }

    private func button(_ tab: AppTab) -> some View {
        let isSelected = selection == tab
        return Button {
            guard selection != tab else { return }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            withAnimation(.snappy(duration: 0.24)) {
                selection = tab
            }
        } label: {
            VStack(spacing: 2) {
                BSHDeskTabIcon(tab: tab, selected: isSelected, size: 16)
                    .frame(height: 20)
                Text(language.t(tab.titleKey))
                    .font(.system(size: 10, weight: isSelected ? .semibold : .medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
            .foregroundStyle(isSelected ? BSHPalette.folioOnInk : BSHPalette.folioInk.opacity(0.58))
            .padding(.horizontal, 4)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity)
            .background {
                if isSelected {
                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .fill(BSHPalette.folioInk)
                        .matchedGeometryEffect(id: "folioDeskTab", in: tabSpace)
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
            .welcomeTourAnchor(WelcomeTourCatalog.tabAnchor(tab))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.t(tab.titleKey))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

/// The page shape that rests on Bureau's desk: rounded where it meets the desk, square
/// where it runs off the top of the screen.
struct BSHPageShape: Shape {
    var topRadius: CGFloat = 0
    var bottomRadius: CGFloat = BureauDeskBar.pageRadius

    func path(in rect: CGRect) -> Path {
        UnevenRoundedRectangle(
            topLeadingRadius: topRadius,
            bottomLeadingRadius: bottomRadius,
            bottomTrailingRadius: bottomRadius,
            topTrailingRadius: topRadius,
            style: .continuous
        )
        .path(in: rect)
    }
}

extension View {
    /// Bureau's page on the desk: the desk's content clipped to the page and its shadow
    /// cast on the green. A page that runs off the top of the screen carries its paper
    /// up under the status bar, so the clock is on paper in either appearance.
    func bureauPage(_ shape: BSHPageShape = BSHPageShape()) -> some View {
        self
            .clipShape(shape)
            .background {
                shape
                    .fill(BSHPalette.bureauSheet)
                    .shadow(color: .black.opacity(0.34), radius: 14, y: 6)
                    .ignoresSafeArea(edges: shape.topRadius == 0 ? .top : [])
            }
    }
}

// MARK: - The landscape iPad rail

/// Colors of the rail's writing in each design: ivory on Bureau's desk, ink on Folio's
/// paper, the system's labels under Summit Glass.
enum BSHRailInk {
    static var title: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauOnFrame
        case .folio: return BSHPalette.folioInk
        case .glass: return .primary
        }
    }

    static var muted: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauOnFrame.opacity(0.64)
        case .folio: return BSHPalette.folioInk.opacity(0.6)
        case .glass: return .secondary
        }
    }

    static var hoverFill: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauOnFrame.opacity(0.07)
        case .folio: return BSHPalette.folioInk.opacity(0.05)
        case .glass: return Color.primary.opacity(0.045)
        }
    }

    /// A chosen row's label: Bureau's is on the page, so it takes the page's ink.
    static var selectedLabel: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauInk
        case .folio: return BSHPalette.folioInk
        case .glass: return .primary
        }
    }

    static var selectedIcon: Color {
        BSHDesign.active == .folio ? BSHPalette.folioInk : .dsAccent
    }
}

/// The ground the rail is drawn on.
struct BSHRailGround: View {
    var body: some View {
        switch BSHDesign.active {
        case .bureau:
            BSHPalette.bureauFrame.ignoresSafeArea()
        case .folio:
            Color.dsCanvas
                .overlay(alignment: .trailing) {
                    Rectangle().fill(Color.dsHairline).frame(width: 1)
                }
                .ignoresSafeArea()
        case .glass:
            ZStack {
                Color.dsPage.opacity(0.70)
                Rectangle().fill(.ultraThinMaterial)
            }
            .ignoresSafeArea()
        }
    }
}

/// A chosen rail row on paper. Folio: a bookmark, a wash of ink with a ribbon down its
/// leading edge. Bureau: a tab of the sheet, reaching from the row across the rail's
/// trailing padding to the page and flaring into it.
struct BSHRailSelection: View {
    var cornerRadius: CGFloat = 10
    /// How far the rail's edge (and so the page) lies past the row's trailing edge.
    var reachToPage: CGFloat

    var body: some View {
        switch BSHDesign.active {
        case .bureau:
            BSHJoinedTabShape(join: .trailing, radius: cornerRadius)
                .fill(BSHPalette.bureauSheet)
                .padding(.trailing, -(reachToPage + 1))
        case .folio:
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(BSHPalette.folioInk.opacity(0.07))
                .overlay(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 1, style: .continuous)
                        .fill(BSHPalette.folioInk)
                        .frame(width: 3)
                        .padding(.vertical, 5)
                }
        case .glass:
            EmptyView()
        }
    }
}

/// The desk beside the rail. Bureau: the page laid on the green with a gutter above,
/// to its right and below, and straight along the rail so the chosen row's tab joins it.
/// The status bar is hidden there (a clock on the green would be dark on dark), as a
/// full-screen desk. Folio and Summit: the detail as it is.
struct BSHPadDeskPage: ViewModifier {
    static let gutter: CGFloat = 8

    func body(content: Content) -> some View {
        if BSHDesign.active == .bureau {
            content
                .bureauPage(BSHPageShape(topRadius: 16, bottomRadius: 16))
                .padding([.top, .trailing, .bottom], Self.gutter)
        } else {
            content
        }
    }
}
