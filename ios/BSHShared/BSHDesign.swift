//
//  BSHDesign.swift
//  Shared by BSHResearch (iPhone, iPad) and BSHResearchMac.
//
//  The app's three designs, as on the website (frontend/src/design.js):
//
//  - Summit Glass, the original and the default: the system's own materials and blue.
//  - Bureau, the page on a desk: one sheet laid on a desk (white by day and black by
//    night unless another desk color is chosen), brass for acting, Instrument Serif
//    titles. Where you are is cut from the page.
//  - Folio, paper and ink: warm paper, ruled cards, a book serif (Iowan Old Style),
//    selection set in solid ink, ultramarine for acting.
//
//  Views don't read the choice. They use the `Color.ds*` / `Font.ds*` tokens and the
//  card, tile and selection components (MacDesign.swift / ResearchDesign.swift), which
//  resolve against `BSHDesign.active`; the app re-renders its root when the design
//  changes. Only the shells (the Mac sidebar, the iPhone bar, the iPad rail) branch
//  on the design themselves.
//

import CoreText
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif
#if canImport(AppKit)
import AppKit
#endif

enum BSHDesign: String, CaseIterable, Identifiable {
    case bureau
    case folio
    case glass

    var id: String { rawValue }

    /// The same key the website keeps its choice under (per device here, per browser there).
    static let storageKey = "bsh.research.design"
    static let defaultDesign: BSHDesign = .glass

    /// The design every token resolves against. Kept by `BSHDesignStore`.
    nonisolated(unsafe) static var active: BSHDesign = stored()

    static func stored(in defaults: UserDefaults = .standard) -> BSHDesign {
        defaults.string(forKey: storageKey).flatMap(BSHDesign.init(rawValue:)) ?? defaultDesign
    }

    var title: String {
        switch self {
        case .bureau: return "Bureau"
        case .folio: return "Folio"
        case .glass: return "Summit Glass"
        }
    }

    /// Bureau and Folio draw their own paper; Summit Glass keeps the system's surfaces.
    var isPaper: Bool { self != .glass }
}

/// Bureau's desk. Onyx & White is the standard: a white desk by day and a black one by
/// night, with a stone sheet. The others lay the ivory sheet on a colored desk; bottle
/// green is where Bureau began. The website keeps the same choice (`data-desk`).
enum BSHBureauDesk: String, CaseIterable, Identifiable {
    case onyx
    case green
    case maroon
    case navy
    case aubergine
    case tobacco
    case graphite

    var id: String { rawValue }

    /// The website's key for the same choice (per device here, per browser there).
    static let storageKey = "bsh.research.bureauDesk"
    static let defaultDesk: BSHBureauDesk = .onyx

    /// The desk Bureau's tokens resolve against. Kept by `BSHDesignStore`.
    nonisolated(unsafe) static var active: BSHBureauDesk = stored()

    static func stored(in defaults: UserDefaults = .standard) -> BSHBureauDesk {
        defaults.string(forKey: storageKey).flatMap(BSHBureauDesk.init(rawValue:)) ?? defaultDesk
    }

    var title: String {
        switch self {
        case .onyx: return "Onyx & White"
        case .green: return "Bottle green"
        case .maroon: return "Maroon"
        case .navy: return "Navy"
        case .aubergine: return "Aubergine"
        case .tobacco: return "Tobacco"
        case .graphite: return "Graphite"
        }
    }

    /// Whether the desk is dark in the given appearance: every desk is, except Onyx's
    /// white desk by day. Chrome on a dark desk draws in the dark appearance.
    func isDark(in scheme: ColorScheme) -> Bool {
        self != .onyx || scheme == .dark
    }

    /// The desk's color as a swatch shows it (its daytime desk).
    var swatch: Color { .bshFixed(tones.frame.light) }

    var tones: BSHBureauTones {
        // The ivory sheet the colored desks share by day, and its trays and rules.
        let ivory = BSHRGB(247, 244, 236)
        let onDesk = (light: BSHRGB(238, 232, 216), dark: BSHRGB(230, 225, 210))
        let nightInk = BSHRGB(234, 229, 214)
        func colored(
            frame: (BSHRGB, BSHRGB), raised: (BSHRGB, BSHRGB), sheet: BSHRGB, ink: BSHRGB,
            tray: BSHRGB, lifted: BSHRGB, rule: BSHRGB
        ) -> BSHBureauTones {
            BSHBureauTones(
                frame: (frame.0, frame.1),
                frameRaised: (raised.0, raised.1),
                onFrame: onDesk,
                sheet: (ivory, sheet),
                ink: (ink, nightInk),
                tray: (BSHRGB(240, 236, 226), tray),
                raised: (BSHRGB(255, 253, 248), lifted),
                rule: (BSHRGB(222, 215, 200), rule)
            )
        }
        switch self {
        case .onyx:
            return BSHBureauTones(
                frame: (BSHRGB(255, 255, 255), BSHRGB(5, 5, 5)),
                frameRaised: (BSHRGB(242, 242, 242), BSHRGB(17, 17, 17)),
                onFrame: (BSHRGB(24, 24, 24), BSHRGB(232, 229, 222)),
                sheet: (BSHRGB(241, 240, 236), BSHRGB(24, 24, 24)),
                ink: (BSHRGB(24, 24, 24), BSHRGB(232, 229, 222)),
                tray: (BSHRGB(233, 231, 226), BSHRGB(15, 15, 15)),
                raised: (BSHRGB(251, 251, 249), BSHRGB(33, 33, 33)),
                rule: (BSHRGB(216, 214, 208), BSHRGB(44, 43, 43))
            )
        case .green:
            return colored(
                frame: (BSHRGB(15, 31, 26), BSHRGB(7, 11, 9)), raised: (BSHRGB(25, 45, 39), BSHRGB(17, 26, 22)),
                sheet: BSHRGB(21, 29, 26), ink: BSHRGB(24, 30, 27),
                tray: BSHRGB(14, 20, 17), lifted: BSHRGB(30, 39, 35), rule: BSHRGB(40, 50, 45)
            )
        case .maroon:
            return colored(
                frame: (BSHRGB(80, 18, 30), BSHRGB(22, 6, 10)), raised: (BSHRGB(89, 30, 40), BSHRGB(33, 18, 21)),
                sheet: BSHRGB(35, 19, 24), ink: BSHRGB(33, 24, 25),
                tray: BSHRGB(29, 13, 17), lifted: BSHRGB(44, 28, 33), rule: BSHRGB(54, 39, 42)
            )
        case .navy:
            return colored(
                frame: (BSHRGB(16, 28, 52), BSHRGB(6, 9, 16)), raised: (BSHRGB(28, 39, 61), BSHRGB(18, 21, 27)),
                sheet: BSHRGB(20, 25, 35), ink: BSHRGB(22, 27, 36),
                tray: BSHRGB(13, 17, 26), lifted: BSHRGB(30, 34, 43), rule: BSHRGB(40, 44, 52)
            )
        case .aubergine:
            return colored(
                frame: (BSHRGB(48, 22, 46), BSHRGB(12, 7, 12)), raised: (BSHRGB(58, 34, 55), BSHRGB(24, 19, 23)),
                sheet: BSHRGB(30, 22, 30), ink: BSHRGB(30, 24, 30),
                tray: BSHRGB(21, 15, 21), lifted: BSHRGB(39, 31, 38), rule: BSHRGB(49, 42, 47)
            )
        case .tobacco:
            return colored(
                frame: (BSHRGB(54, 34, 18), BSHRGB(11, 8, 5)), raised: (BSHRGB(64, 45, 29), BSHRGB(23, 20, 16)),
                sheet: BSHRGB(34, 27, 22), ink: BSHRGB(32, 27, 22),
                tray: BSHRGB(23, 18, 14), lifted: BSHRGB(43, 36, 31), rule: BSHRGB(53, 46, 40)
            )
        case .graphite:
            return colored(
                frame: (BSHRGB(30, 34, 40), BSHRGB(8, 9, 11)), raised: (BSHRGB(41, 45, 50), BSHRGB(20, 21, 22)),
                sheet: BSHRGB(25, 28, 34), ink: BSHRGB(25, 28, 32),
                tray: BSHRGB(17, 19, 23), lifted: BSHRGB(34, 37, 42), rule: BSHRGB(45, 47, 51)
            )
        }
    }
}

/// One Bureau desk's colors by day and by night, as the website sets them (bureau.css).
struct BSHBureauTones {
    typealias Pair = (light: BSHRGB, dark: BSHRGB)

    /// The desk.
    let frame: Pair
    /// A control lifted off the desk.
    let frameRaised: Pair
    /// What is written on the desk.
    let onFrame: Pair
    /// The page, and its ink.
    let sheet: Pair
    let ink: Pair
    /// A card pressed into the page, paper lifted off it, and a rule on it.
    let tray: Pair
    let raised: Pair
    let rule: Pair
}

/// Holds the chosen design (and Bureau's desk) and persists it. The app rebuilds its
/// windows on `identity`, so every token re-resolves at once.
@MainActor
final class BSHDesignStore: ObservableObject {
    @Published var design: BSHDesign {
        didSet {
            defaults.set(design.rawValue, forKey: BSHDesign.storageKey)
            BSHDesign.active = design
            // Before the rebuild, so chrome created by it (UIKit's bars) picks it up.
            onApply?(design)
        }
    }

    @Published var bureauDesk: BSHBureauDesk {
        didSet {
            defaults.set(bureauDesk.rawValue, forKey: BSHBureauDesk.storageKey)
            BSHBureauDesk.active = bureauDesk
            onApply?(design)
        }
    }

    /// What a window rebuilds on: the design and, under Bureau, its desk.
    var identity: String {
        design == .bureau ? "\(design.rawValue)-\(bureauDesk.rawValue)" : design.rawValue
    }

    private let defaults: UserDefaults
    private let onApply: (@MainActor (BSHDesign) -> Void)?

    /// - Parameter onApply: runs with the design at launch and after every change (of the
    ///   design or the desk), before the windows rebuild (the iPhone and iPad app points
    ///   UIKit's bars at it here).
    init(defaults: UserDefaults = .standard, onApply: (@MainActor (BSHDesign) -> Void)? = nil) {
        self.defaults = defaults
        self.onApply = onApply
        let stored = BSHDesign.stored(in: defaults)
        let storedDesk = BSHBureauDesk.stored(in: defaults)
        design = stored
        bureauDesk = storedDesk
        BSHDesign.active = stored
        BSHBureauDesk.active = storedDesk
        onApply?(stored)
    }
}

// MARK: - Colors

/// An RGB triple on the 0–255 scale, as the web's tokens are written.
struct BSHRGB: Equatable {
    let r: Double
    let g: Double
    let b: Double

    init(_ r: Double, _ g: Double, _ b: Double) {
        self.r = r
        self.g = g
        self.b = b
    }
}

extension Color {
    /// A color that follows the appearance: `light` in light mode, `dark` in dark.
    static func bshTone(_ light: BSHRGB, _ dark: BSHRGB, opacity: Double = 1) -> Color {
        #if canImport(UIKit)
        return Color(uiColor: UIColor { traits in
            let rgb = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255, alpha: opacity)
        })
        #else
        return Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            let rgb = isDark ? dark : light
            return NSColor(srgbRed: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255, alpha: opacity)
        })
        #endif
    }

    /// The same color in either appearance.
    static func bshFixed(_ rgb: BSHRGB, opacity: Double = 1) -> Color {
        Color(.sRGB, red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255, opacity: opacity)
    }
}

/// Every design-dependent color, resolved against `BSHDesign.active` (and, under Bureau,
/// `BSHBureauDesk.active`). The values are the website's (bureau.css, folio.css), so a
/// desk looks the same on every surface.
enum BSHPalette {
    // Bureau's desk and sheet, named apart from the page tokens so chrome on the desk
    // can still reach the page's colors.
    private static var desk: BSHBureauTones { BSHBureauDesk.active.tones }

    private static func tone(_ pair: BSHBureauTones.Pair, opacity: Double = 1) -> Color {
        .bshTone(pair.light, pair.dark, opacity: opacity)
    }

    private static func fixed(_ pair: BSHBureauTones.Pair, _ page: ColorScheme) -> Color {
        .bshFixed(page == .dark ? pair.dark : pair.light)
    }

    static var bureauFrame: Color { tone(desk.frame) }
    static var bureauFrameRaised: Color { tone(desk.frameRaised) }
    static var bureauOnFrame: Color { tone(desk.onFrame) }
    static var bureauSheet: Color { tone(desk.sheet) }
    static var bureauInk: Color { tone(desk.ink) }

    // The same, fixed to the page's appearance. Chrome on a dark desk draws in the dark
    // appearance in either mode (as the website's desk does), so what it borrows from
    // the page is resolved against the page's own appearance instead.
    static func bureauFrame(for page: ColorScheme) -> Color { fixed(desk.frame, page) }
    static func bureauSheet(for page: ColorScheme) -> Color { fixed(desk.sheet, page) }
    static func bureauInk(for page: ColorScheme) -> Color { fixed(desk.ink, page) }

    /// Whether Bureau's desk is dark in `scheme`: every desk but Onyx's white one by day.
    static func bureauDeskIsDark(_ scheme: ColorScheme) -> Bool {
        BSHBureauDesk.active.isDark(in: scheme)
    }

    static let bureauBrass = Color.bshFixed(BSHRGB(208, 172, 100))
    static let bureauBrassDeep = Color.bshFixed(BSHRGB(176, 138, 66))

    // Folio's ink, which selection is set in, and the paper that shows through it.
    static let folioInk = Color.bshTone(BSHRGB(26, 25, 22), BSHRGB(238, 235, 227))
    static let folioOnInk = Color.bshTone(BSHRGB(250, 248, 243), BSHRGB(22, 21, 19))

    /// The page ground.
    static var canvas: Color {
        switch BSHDesign.active {
        case .bureau: return bureauSheet
        case .folio: return .bshTone(BSHRGB(244, 242, 237), BSHRGB(22, 21, 19))
        case .glass:
            #if canImport(UIKit)
            return Color(uiColor: .systemGroupedBackground)
            #else
            return Color(nsColor: .windowBackgroundColor)
            #endif
        }
    }

    /// A card: Bureau's tray pressed into the sheet, Folio's fresher sheet.
    static var card: Color {
        switch BSHDesign.active {
        case .bureau: return tone(desk.tray)
        case .folio: return .bshTone(BSHRGB(251, 250, 247), BSHRGB(30, 29, 26))
        case .glass:
            #if canImport(UIKit)
            return Color(uiColor: .secondarySystemGroupedBackground)
            #else
            return Color(nsColor: .controlBackgroundColor)
            #endif
        }
    }

    /// Paper lifted off the page: menus, fields, a chosen chip.
    static var raised: Color {
        switch BSHDesign.active {
        case .bureau: return tone(desk.raised)
        case .folio: return .bshTone(BSHRGB(253, 252, 250), BSHRGB(40, 39, 35))
        case .glass:
            #if canImport(UIKit)
            return Color(uiColor: .systemBackground)
            #else
            return Color(nsColor: .controlBackgroundColor)
            #endif
        }
    }

    /// A small tile inside a card.
    static var tile: Color {
        switch BSHDesign.active {
        case .bureau: return tone(desk.ink, opacity: 0.05)
        case .folio: return .bshTone(BSHRGB(26, 25, 22), BSHRGB(238, 235, 227), opacity: 0.045)
        case .glass:
            #if canImport(UIKit)
            return Color(uiColor: .tertiarySystemGroupedBackground)
            #else
            return Color.primary.opacity(0.045)
            #endif
        }
    }

    /// A rule between things.
    static var hairline: Color {
        switch BSHDesign.active {
        case .bureau: return tone(desk.rule)
        case .folio: return .bshTone(BSHRGB(224, 220, 212), BSHRGB(54, 52, 47))
        case .glass:
            #if canImport(UIKit)
            return Color.primary.opacity(0.08)
            #else
            return Color.primary.opacity(0.09)
            #endif
        }
    }

    /// Acting: buttons, links, the chosen control. Brass, ultramarine, Summit blue.
    /// One value serves as icon and text color and as a filled button's ground, so
    /// each appearance's value reads on the page (≥ 4.5:1) and still carries a
    /// button's white label at display weight.
    static var accent: Color {
        switch BSHDesign.active {
        case .bureau: return .bshTone(BSHRGB(148, 112, 47), BSHRGB(176, 138, 66))
        case .folio: return .bshTone(BSHRGB(38, 60, 212), BSHRGB(122, 138, 255))
        case .glass: return .accentColor
        }
    }

    /// The page's ink, where a design sets its own.
    static var ink: Color? {
        switch BSHDesign.active {
        case .bureau: return bureauInk
        case .folio: return folioInk
        case .glass: return nil
        }
    }

    static var positive: Color {
        switch BSHDesign.active {
        case .bureau: return .bshTone(BSHRGB(31, 128, 80), BSHRGB(76, 180, 118))
        case .folio: return .bshTone(BSHRGB(26, 140, 76), BSHRGB(72, 196, 120))
        case .glass: return .green
        }
    }

    static var negative: Color {
        switch BSHDesign.active {
        case .bureau: return .bshTone(BSHRGB(192, 57, 43), BSHRGB(232, 100, 82))
        case .folio: return .bshTone(BSHRGB(205, 48, 36), BSHRGB(240, 96, 80))
        case .glass: return .red
        }
    }

    static var warning: Color {
        switch BSHDesign.active {
        case .bureau: return .bshTone(BSHRGB(196, 118, 18), BSHRGB(232, 158, 60))
        case .folio: return .bshTone(BSHRGB(214, 120, 0), BSHRGB(240, 160, 40))
        case .glass: return .orange
        }
    }
}

// MARK: - Type

/// Titles and kickers per design. Figures and controls stay in the system face.
enum BSHType {
    static let bureauSerif = "InstrumentSerif-Regular"
    static let bureauSerifItalic = "InstrumentSerif-Italic"
    static let folioSerif = "IowanOldStyle-Roman"
    static let folioSerifItalic = "IowanOldStyle-Italic"

    /// A desk or page title. Instrument Serif is set larger than SF because it is a
    /// lighter, narrower face; Iowan sits close to SF's size.
    static func title(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        switch BSHDesign.active {
        case .bureau: return .custom(bureauSerif, size: (size * 1.3).rounded())
        case .folio: return .custom(folioSerif, size: (size * 1.08).rounded())
        case .glass: return .system(size: size, weight: weight)
        }
    }

    /// A card or section heading.
    static func heading(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        heading(size, weight: weight, in: BSHDesign.active)
    }

    /// A heading in a given design's face, whichever design is active (the design
    /// choosers set each design's name in its own type).
    static func heading(_ size: CGFloat, weight: Font.Weight = .semibold, in design: BSHDesign) -> Font {
        switch design {
        case .bureau: return .custom(bureauSerif, size: (size * 1.3).rounded())
        case .folio: return .custom(folioSerif, size: (size * 1.1).rounded()).weight(.semibold)
        case .glass: return .system(size: size, weight: weight)
        }
    }

    /// A section label's face: Bureau's italic serif kicker, otherwise the system label.
    static func kicker(_ size: CGFloat) -> Font {
        switch BSHDesign.active {
        case .bureau: return .custom(bureauSerifItalic, size: (size * 1.3).rounded())
        case .folio: return .system(size: max(size - 0.5, 9), weight: .semibold)
        case .glass: return .system(size: size, weight: .medium)
        }
    }

    /// Folio sets its labels in small tracked capitals.
    static var kickerIsCapitals: Bool { BSHDesign.active == .folio }

    /// Registers the bundled faces (Instrument Serif) for this process. Iowan Old Style
    /// ships with iOS and macOS. Safe to call more than once.
    static func registerBundledFonts(in bundle: Bundle = .main) {
        for name in [bureauSerif, bureauSerifItalic] {
            guard let url = bundle.url(forResource: name, withExtension: "ttf") else { continue }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}

// MARK: - Where a control sits

private struct BSHOnFrameKey: EnvironmentKey {
    static let defaultValue = false
}

private struct BSHPageSchemeKey: EnvironmentKey {
    static let defaultValue: ColorScheme? = nil
}

extension EnvironmentValues {
    /// True inside chrome drawn on Bureau's desk (the Mac sidebar, the iPad rail), where a
    /// chosen row is cut from the sheet instead of lifted from it.
    var bshOnFrame: Bool {
        get { self[BSHOnFrameKey.self] }
        set { self[BSHOnFrameKey.self] = newValue }
    }

    /// The page's appearance, inside desk chrome that draws dark in either mode; nil
    /// elsewhere (the page's appearance is then `colorScheme`).
    var bshPageScheme: ColorScheme? {
        get { self[BSHPageSchemeKey.self] }
        set { self[BSHPageSchemeKey.self] = newValue }
    }
}

// MARK: - A tab cut from the page

/// A tab joined to the page along one edge: its free corners are rounded and, where it
/// meets the page, its corners flare outward into it, so tab and page read as one piece
/// of paper (Bureau's selection, as on the website's desk tabs and company rail). The
/// flares are drawn outside the shape's frame by `radius` on each side.
struct BSHJoinedTabShape: Shape {
    /// The edge the tab is joined to the page along.
    var join: Edge
    var radius: CGFloat = 12
    /// False draws only the free edges, open along the join, for a rim that doesn't
    /// cross between the tab and the page (on Onyx's white desk by day).
    var includesJoin: Bool = true

    func path(in rect: CGRect) -> Path {
        let r = min(radius, rect.width / 2, rect.height / 2)
        let k: CGFloat = 0.5523 // cubic approximation of a quarter circle
        var p = Path()
        switch join {
        case .top:
            // Page above, tab hanging below it: flares at the top corners.
            if includesJoin {
                p.move(to: CGPoint(x: rect.minX - r, y: rect.minY))
                p.addLine(to: CGPoint(x: rect.maxX + r, y: rect.minY))
            } else {
                p.move(to: CGPoint(x: rect.maxX + r, y: rect.minY))
            }
            p.addCurve(
                to: CGPoint(x: rect.maxX, y: rect.minY + r),
                control1: CGPoint(x: rect.maxX + r - k * r, y: rect.minY),
                control2: CGPoint(x: rect.maxX, y: rect.minY + r - k * r)
            )
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - r))
            p.addCurve(
                to: CGPoint(x: rect.maxX - r, y: rect.maxY),
                control1: CGPoint(x: rect.maxX, y: rect.maxY - r + k * r),
                control2: CGPoint(x: rect.maxX - r + k * r, y: rect.maxY)
            )
            p.addLine(to: CGPoint(x: rect.minX + r, y: rect.maxY))
            p.addCurve(
                to: CGPoint(x: rect.minX, y: rect.maxY - r),
                control1: CGPoint(x: rect.minX + r - k * r, y: rect.maxY),
                control2: CGPoint(x: rect.minX, y: rect.maxY - r + k * r)
            )
            p.addLine(to: CGPoint(x: rect.minX, y: rect.minY + r))
            p.addCurve(
                to: CGPoint(x: rect.minX - r, y: rect.minY),
                control1: CGPoint(x: rect.minX, y: rect.minY + r - k * r),
                control2: CGPoint(x: rect.minX - r + k * r, y: rect.minY)
            )
        case .bottom:
            // Page below, tab standing on it: flares at the bottom corners.
            p.move(to: CGPoint(x: rect.minX - r, y: rect.maxY))
            p.addCurve(
                to: CGPoint(x: rect.minX, y: rect.maxY - r),
                control1: CGPoint(x: rect.minX - r + k * r, y: rect.maxY),
                control2: CGPoint(x: rect.minX, y: rect.maxY - r + k * r)
            )
            p.addLine(to: CGPoint(x: rect.minX, y: rect.minY + r))
            p.addCurve(
                to: CGPoint(x: rect.minX + r, y: rect.minY),
                control1: CGPoint(x: rect.minX, y: rect.minY + r - k * r),
                control2: CGPoint(x: rect.minX + r - k * r, y: rect.minY)
            )
            p.addLine(to: CGPoint(x: rect.maxX - r, y: rect.minY))
            p.addCurve(
                to: CGPoint(x: rect.maxX, y: rect.minY + r),
                control1: CGPoint(x: rect.maxX - r + k * r, y: rect.minY),
                control2: CGPoint(x: rect.maxX, y: rect.minY + r - k * r)
            )
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - r))
            p.addCurve(
                to: CGPoint(x: rect.maxX + r, y: rect.maxY),
                control1: CGPoint(x: rect.maxX, y: rect.maxY - r + k * r),
                control2: CGPoint(x: rect.maxX + r - k * r, y: rect.maxY)
            )
        case .trailing:
            // Page to the right, tab reaching into it from the left: flares at the
            // trailing corners.
            if includesJoin {
                p.move(to: CGPoint(x: rect.maxX, y: rect.minY - r))
                p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY + r))
            } else {
                p.move(to: CGPoint(x: rect.maxX, y: rect.maxY + r))
            }
            p.addCurve(
                to: CGPoint(x: rect.maxX - r, y: rect.maxY),
                control1: CGPoint(x: rect.maxX, y: rect.maxY + r - k * r),
                control2: CGPoint(x: rect.maxX - r + k * r, y: rect.maxY)
            )
            p.addLine(to: CGPoint(x: rect.minX + r, y: rect.maxY))
            p.addCurve(
                to: CGPoint(x: rect.minX, y: rect.maxY - r),
                control1: CGPoint(x: rect.minX + r - k * r, y: rect.maxY),
                control2: CGPoint(x: rect.minX, y: rect.maxY - r + k * r)
            )
            p.addLine(to: CGPoint(x: rect.minX, y: rect.minY + r))
            p.addCurve(
                to: CGPoint(x: rect.minX + r, y: rect.minY),
                control1: CGPoint(x: rect.minX, y: rect.minY + r - k * r),
                control2: CGPoint(x: rect.minX + r - k * r, y: rect.minY)
            )
            p.addLine(to: CGPoint(x: rect.maxX - r, y: rect.minY))
            p.addCurve(
                to: CGPoint(x: rect.maxX, y: rect.minY - r),
                control1: CGPoint(x: rect.maxX - r + k * r, y: rect.minY),
                control2: CGPoint(x: rect.maxX, y: rect.minY - r + k * r)
            )
        case .leading:
            // Page to the left, tab reaching into it from the right.
            p.move(to: CGPoint(x: rect.minX, y: rect.minY - r))
            p.addCurve(
                to: CGPoint(x: rect.minX + r, y: rect.minY),
                control1: CGPoint(x: rect.minX, y: rect.minY - r + k * r),
                control2: CGPoint(x: rect.minX + r - k * r, y: rect.minY)
            )
            p.addLine(to: CGPoint(x: rect.maxX - r, y: rect.minY))
            p.addCurve(
                to: CGPoint(x: rect.maxX, y: rect.minY + r),
                control1: CGPoint(x: rect.maxX - r + k * r, y: rect.minY),
                control2: CGPoint(x: rect.maxX, y: rect.minY + r - k * r)
            )
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - r))
            p.addCurve(
                to: CGPoint(x: rect.maxX - r, y: rect.maxY),
                control1: CGPoint(x: rect.maxX, y: rect.maxY - r + k * r),
                control2: CGPoint(x: rect.maxX - r + k * r, y: rect.maxY)
            )
            p.addLine(to: CGPoint(x: rect.minX + r, y: rect.maxY))
            p.addCurve(
                to: CGPoint(x: rect.minX, y: rect.maxY + r),
                control1: CGPoint(x: rect.minX + r - k * r, y: rect.maxY),
                control2: CGPoint(x: rect.minX, y: rect.maxY + r - k * r)
            )
        }
        if includesJoin {
            p.closeSubpath()
        }
        return p
    }
}

// MARK: - Root

extension View {
    /// Applies the design to a window's root: its accent to controls, and its ink to text,
    /// so `.secondary` and `.tertiary` derive from the page's ink rather than system gray.
    @ViewBuilder
    func bshDesignRoot() -> some View {
        if let ink = BSHPalette.ink {
            self.tint(BSHPalette.accent).foregroundStyle(ink)
        } else {
            self.tint(BSHPalette.accent)
        }
    }
}
