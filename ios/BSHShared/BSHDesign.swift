//
//  BSHDesign.swift
//  Shared by BSHResearch (iPhone, iPad) and BSHResearchMac.
//
//  The app's three designs, as on the website (frontend/src/design.js):
//
//  - Bureau, the page on a desk: a bottle-green desk, one ivory sheet laid on it,
//    brass for acting, Instrument Serif titles. Where you are is cut from the page.
//  - Folio, paper and ink: warm paper, ruled cards, a book serif (Iowan Old Style),
//    selection set in solid ink, ultramarine for acting.
//  - Summit Glass, the original: the system's own materials and blue.
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
    static let defaultDesign: BSHDesign = .bureau

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

/// Holds the chosen design and persists it. The app reads `design` to rebuild its root
/// (`.id(design)`), so every token re-resolves at once.
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

    private let defaults: UserDefaults
    private let onApply: (@MainActor (BSHDesign) -> Void)?

    /// - Parameter onApply: runs with the design at launch and after every change, before
    ///   the windows rebuild (the iPhone and iPad app points UIKit's bars at it here).
    init(defaults: UserDefaults = .standard, onApply: (@MainActor (BSHDesign) -> Void)? = nil) {
        self.defaults = defaults
        self.onApply = onApply
        let stored = BSHDesign.stored(in: defaults)
        design = stored
        BSHDesign.active = stored
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

/// Every design-dependent color, resolved against `BSHDesign.active`. The values are the
/// website's (bureau.css, folio.css), so a desk looks the same on every surface.
enum BSHPalette {
    // Bureau's desk and sheet, named apart from the page tokens so chrome on the desk
    // can still reach the page's colors.
    private static let bureauFrameRGB = (light: BSHRGB(15, 31, 26), dark: BSHRGB(7, 11, 9))
    private static let bureauSheetRGB = (light: BSHRGB(247, 244, 236), dark: BSHRGB(21, 29, 26))
    private static let bureauInkRGB = (light: BSHRGB(24, 30, 27), dark: BSHRGB(234, 229, 214))
    static let bureauFrame = Color.bshTone(bureauFrameRGB.light, bureauFrameRGB.dark)
    static let bureauFrameRaised = Color.bshTone(BSHRGB(25, 45, 39), BSHRGB(17, 26, 22))
    static let bureauOnFrame = Color.bshTone(BSHRGB(238, 232, 216), BSHRGB(230, 225, 210))
    static let bureauSheet = Color.bshTone(bureauSheetRGB.light, bureauSheetRGB.dark)
    static let bureauInk = Color.bshTone(bureauInkRGB.light, bureauInkRGB.dark)

    // The same, fixed to the page's appearance. Chrome on the desk draws in the dark
    // appearance in either mode (as the website's desk does), so what it borrows from
    // the page is resolved against the page's own appearance instead.
    static func bureauFrame(for page: ColorScheme) -> Color {
        .bshFixed(page == .dark ? bureauFrameRGB.dark : bureauFrameRGB.light)
    }

    static func bureauSheet(for page: ColorScheme) -> Color {
        .bshFixed(page == .dark ? bureauSheetRGB.dark : bureauSheetRGB.light)
    }

    static func bureauInk(for page: ColorScheme) -> Color {
        .bshFixed(page == .dark ? bureauInkRGB.dark : bureauInkRGB.light)
    }
    static let bureauBrass = Color.bshFixed(BSHRGB(208, 172, 100))
    static let bureauBrassDeep = Color.bshFixed(BSHRGB(176, 138, 66))
    static let bureauSwitchOn = Color.bshTone(BSHRGB(26, 62, 51), BSHRGB(158, 120, 52))

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
        case .bureau: return .bshTone(BSHRGB(240, 236, 226), BSHRGB(14, 20, 17))
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
        case .bureau: return .bshTone(BSHRGB(255, 253, 248), BSHRGB(30, 39, 35))
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
        case .bureau: return .bshTone(BSHRGB(24, 30, 27), BSHRGB(234, 229, 214), opacity: 0.05)
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
        case .bureau: return .bshTone(BSHRGB(222, 215, 200), BSHRGB(40, 50, 45))
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
        switch BSHDesign.active {
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

    func path(in rect: CGRect) -> Path {
        let r = min(radius, rect.width / 2, rect.height / 2)
        let k: CGFloat = 0.5523 // cubic approximation of a quarter circle
        var p = Path()
        switch join {
        case .top:
            // Page above, tab hanging below it: flares at the top corners.
            p.move(to: CGPoint(x: rect.minX - r, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.maxX + r, y: rect.minY))
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
            p.move(to: CGPoint(x: rect.maxX, y: rect.minY - r))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY + r))
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
        p.closeSubpath()
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
