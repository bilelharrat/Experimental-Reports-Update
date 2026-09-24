//
//  MacBureauResearch.swift
//  BSHResearchMac
//
//  Bureau's Research Desk, drawn as the website draws it (ResearchDeskView.vue,
//  components/research/CompanyDossierView.vue and the research cards, with style.css's
//  `.mac-desk` family and bureau.css): the company directory in a tray on the left of the
//  sheet — the sector popup, Diffs, the search field, the list and the deck drop at its
//  foot — and the dossier beside it: the header, the section tabs with the brass
//  underline, and the cards. Measurements are the website's, in points.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - The desk's tokens

/// `--mac-*` on the Research Desk under Bureau (style.css `.mac-desk`, bureau.css), read
/// from the page's colors for the active desk and appearance.
struct MacBureauDeskInk {
    let page: MacBureauPageInk
    init(_ scheme: ColorScheme) { page = MacBureauPageInk(scheme: scheme) }

    var dark: Bool { page.dark }
    /// `--mac-label`, `--mac-secondary`, `--mac-tertiary`.
    var label: Color { page.ink }
    func label(_ opacity: Double) -> Color { page.ink(opacity) }
    var secondary: Color { page.muted }
    var tertiary: Color { page.subtle }
    /// `--mac-hairline`, `--mac-tile`, `--mac-card`.
    var hairline: Color { page.rule }
    var tile: Color { page.fillTertiary }
    var card: Color { page.tray }
    var raised: Color { page.raised }
    /// `--mac-accent` (brass), `--mac-blue` (brass ink), the brass underline.
    var accent: Color { page.accent }
    var accentHover: Color { page.accentHover }
    var blue: Color { page.accentInk }
    var underline: Color { page.accentGlow(1) }
    var green: Color { page.success }
    var red: Color { page.danger }
    var orange: Color { page.warning }
    var yellow: Color { page.notice }
    var indigo: Color { page.info }
    var purple: Color { .bshFixed(dark ? BSHRGB(190, 140, 236) : BSHRGB(124, 78, 170)) }
    var gray: Color { page.muted }
    func shadow(_ opacity: Double) -> Color { page.shadow(opacity) }
}

private struct MacBureauDeskInkReader<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    let content: (MacBureauDeskInk) -> Content
    var body: some View { content(MacBureauDeskInk(colorScheme)) }
}

// MARK: - Type

/// The desk's type scale (`.mac-t-*`), in Instrument Sans, each line set as CSS sets it.
private enum DeskType {
    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        BSHType.bureauSans(size, weight: weight)
    }

    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        BSHType.bureauSans(size, weight: weight).monospacedDigit()
    }
}

/// Where the browser and SwiftUI put a line of Instrument. Blink rounds the face's ascent
/// and descent to whole pixels, adds half the leading to the ascent and floors the sum: that
/// is the first baseline, below the top of a line box `lineHeight` tall (measured on the
/// website: 10/12.5 → 9, 11/13.75 → 10, 13/16.9 → 13, 15/18.75 → 14, serif 22/26.4 → 20).
/// SwiftUI rounds the size, then the ascent and the descent, and sets the first baseline at
/// the rounded ascent.
enum MacBureauWebLine {
    private static func face(_ serif: Bool) -> (a: CGFloat, d: CGFloat) {
        serif ? (0.990005, 0.309998) : (0.970001, 0.25)
    }

    static func baseline(_ lineHeight: CGFloat, size: CGFloat, serif: Bool = false) -> CGFloat {
        let f = face(serif)
        let ascent = (size * f.a).rounded(), descent = (size * f.d).rounded()
        return ((lineHeight - ascent - descent) / 2 + ascent).rounded(.down)
    }

    static func laid(size: CGFloat, serif: Bool = false) -> (ascent: CGFloat, line: CGFloat) {
        let f = face(serif)
        let s = size.rounded()
        let ascent = (s * f.a).rounded()
        return (ascent, ascent + (s * f.d).rounded())
    }
}

extension MacBureauWebLine {
    /// A run of Instrument Sans as wide as the browser lays it out: the advances summed,
    /// not rounded up to the pixel grid as a SwiftUI text's frame is.
    static func width(_ text: String, size: CGFloat, weight: Font.Weight = .regular, mono: Bool = false) -> CGFloat {
        let face: String
        switch weight {
        case .medium: face = "InstrumentSans-Medium"
        case .semibold: face = "InstrumentSans-SemiBold"
        case .bold, .heavy, .black: face = "InstrumentSans-Bold"
        default: face = "InstrumentSans-Regular"
        }
        guard var font = NSFont(name: face, size: size) else { return 0 }
        if mono {
            // tabular-nums: the same digits SwiftUI's monospacedDigit() picks.
            let descriptor = font.fontDescriptor.addingAttributes([
                .featureSettings: [[
                    NSFontDescriptor.FeatureKey.typeIdentifier: kNumberSpacingType,
                    NSFontDescriptor.FeatureKey.selectorIdentifier: kMonospacedNumbersSelector,
                ]],
            ])
            font = NSFont(descriptor: descriptor, size: size) ?? font
        }
        // Characters the face lacks are measured in the system face, as they are drawn.
        let system = NSFont.systemFont(ofSize: size, weight: weight == .medium ? .medium : weight == .semibold ? .semibold : weight == .bold ? .bold : .regular)
        let measured = NSMutableAttributedString()
        for character in text {
            var units = Array(String(character).utf16)
            var glyphs = [CGGlyph](repeating: 0, count: units.count)
            let covered = CTFontGetGlyphsForCharacters(font as CTFont, &units, &glyphs, units.count)
            measured.append(NSAttributedString(string: String(character), attributes: [.font: covered ? font : system]))
        }
        return measured.size().width
    }
}

extension View {
    /// Lays a line of text out as wide as the browser sets it (its advances summed, not
    /// rounded up to the pixel grid), hanging from its leading edge, so what follows it or
    /// is measured from the other side lands where the website's does.
    func bureauExactWidth(_ text: String, size: CGFloat, weight: Font.Weight = .regular, mono: Bool = false) -> some View {
        fixedSize().frame(width: MacBureauWebLine.width(text, size: size, weight: weight, mono: mono), alignment: .leading)
    }
}

extension View {
    /// Text at `size` set as the website sets it with `line-height: height`: each line
    /// `height` apart, the first baseline where the browser puts it, the box `height` a line.
    func bureauDeskLine(_ lineHeight: CGFloat, _ size: CGFloat, serif: Bool = false) -> some View {
        // Blink keeps lengths in 1/64ths of a pixel, cutting the rest: a 16.9px line is
        // 16.890625 there, and the fractions it drops add up over a card.
        let height = (lineHeight * 64).rounded(.down) / 64
        let laid = MacBureauWebLine.laid(size: size, serif: serif)
        let top = MacBureauWebLine.baseline(height, size: size, serif: serif) - laid.ascent
        return self
            .lineSpacing(max(0, height - laid.line))
            .padding(.top, top)
            .padding(.bottom, height - top - laid.line)
            .bureauSnap(x: .devicePixel)
    }
}

// MARK: - The website's pixel grid

/// Blink lays a page out in fractions (13.75pt lines and the like) but paints on whole CSS
/// pixels: every box's edges rounded to the nearest pixel, every line of text set on a whole
/// pixel. SwiftUI lays out the same fractions and paints them on half points, so the Mac's
/// rules, tiles and lines of text landed up to a point off the website's. Inside a container
/// marked `bureauPixelGrid(_:)` — whose origin sits on a whole point of the window — these
/// paint as Blink does.
enum MacBureauGrid {
    static func round(_ value: CGFloat) -> CGFloat { (value + 0.0001).rounded() }

    /// How far to move each edge of `rect` to put it on the grid (as padding: + moves an
    /// edge inward).
    static func insets(for rect: CGRect) -> EdgeInsets {
        guard !rect.isNull, rect.width.isFinite, rect.height.isFinite else { return EdgeInsets() }
        return EdgeInsets(
            top: round(rect.minY) - rect.minY,
            leading: round(rect.minX) - rect.minX,
            bottom: rect.maxY - round(rect.maxY),
            trailing: rect.maxX - round(rect.maxX)
        )
    }
}

private struct MacBureauGridKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    /// The coordinate space the website's pixel grid is measured in, when there is one.
    var bureauPixelGrid: String? {
        get { self[MacBureauGridKey.self] }
        set { self[MacBureauGridKey.self] = newValue }
    }
}

extension View {
    /// Marks the coordinate space whose whole points are the website's pixels.
    func bureauPixelGrid(_ name: String) -> some View {
        coordinateSpace(.named(name)).environment(\.bureauPixelGrid, name)
    }

    /// Paints the view with its top on a whole point of the grid, and its left edge on a
    /// whole point (a glyph or a logo, as Blink snaps a replaced box) or on a device pixel
    /// (a line of text, which Blink sets at its fractional x and CoreText would floor).
    func bureauSnap(x: MacBureauSnapX = .none) -> some View {
        modifier(MacBureauSnapOffset(snapX: x))
    }

    /// Draws `background` behind the view with its edges on the grid, as Blink paints a box.
    func bureauBackground<Background: View>(@ViewBuilder _ background: () -> Background) -> some View {
        modifier(MacBureauSnapBackground(background: background()))
    }

    /// A box on the grid: `shape` filled, and ruled inside its edge when `stroke` is given.
    func bureauBox<S: InsettableShape>(_ shape: S, fill: Color, stroke: Color? = nil, lineWidth: CGFloat = 1) -> some View {
        bureauBackground {
            ZStack {
                shape.fill(fill)
                if let stroke { shape.strokeBorder(stroke, lineWidth: lineWidth) }
            }
        }
    }

}

/// A rule `thickness` tall across its width, on the website's pixel grid.
struct MacBureauGridRule: View {
    let color: Color
    var thickness: CGFloat = 1

    var body: some View {
        Color.clear.frame(height: thickness).bureauBox(Rectangle(), fill: color)
    }
}

extension View {
    /// Small text set inline in a block whose own face is larger (the page's 16px on a 24px
    /// line): the line is `lineHeight` tall and the text sits on the block's baseline, as a
    /// span does on its parent's strut.
    func bureauStrutLine(_ size: CGFloat, lineHeight: CGFloat = 24, strut: CGFloat = 16) -> some View {
        let laid = MacBureauWebLine.laid(size: size)
        let top = MacBureauWebLine.baseline(lineHeight, size: strut) - laid.ascent
        return self
            .padding(.top, top)
            .padding(.bottom, lineHeight - top - laid.line)
            .bureauSnap(x: .devicePixel)
    }
}

/// How `bureauSnap` treats a view's left edge.
enum MacBureauSnapX {
    case none, devicePixel, whole
}

private struct MacBureauSnapOffset: ViewModifier {
    var snapX: MacBureauSnapX = .none
    @Environment(\.bureauPixelGrid) private var grid
    @State private var delta = CGSize.zero

    func body(content: Content) -> some View {
        content
            .offset(delta)
            .onGeometryChange(for: CGPoint.self) { proxy in
                grid.map { proxy.frame(in: .named($0)).origin } ?? CGPoint(x: CGFloat.nan, y: CGFloat.nan)
            } action: { origin in
                guard origin.x.isFinite, origin.y.isFinite else { delta = .zero; return }
                let x: CGFloat
                switch snapX {
                case .none: x = 0
                case .devicePixel: x = MacBureauGrid.round(origin.x * 2) / 2 - origin.x
                case .whole: x = MacBureauGrid.round(origin.x) - origin.x
                }
                delta = CGSize(width: x, height: MacBureauGrid.round(origin.y) - origin.y)
            }
    }
}

private struct MacBureauSnapBackground<Background: View>: ViewModifier {
    let background: Background
    @Environment(\.bureauPixelGrid) private var grid
    @State private var insets = EdgeInsets()

    func body(content: Content) -> some View {
        content
            .background { background.padding(insets) }
            .onGeometryChange(for: CGRect.self) { proxy in
                grid.map { proxy.frame(in: .named($0)) } ?? .null
            } action: { rect in
                insets = MacBureauGrid.insets(for: rect)
            }
    }
}

/// Text in Instrument Sans with every character the face lacks (Σ, ≥, ⌘) set in the system
/// face, as the browser falls back to it; CoreText would reach for Helvetica or Lucida
/// Grande, whose glyphs are narrower and shift the rest of the line.
enum MacBureauWebText {
    static func attributed(_ string: String, size: CGFloat, weight: Font.Weight = .regular) -> AttributedString {
        let face: String
        switch weight {
        case .medium: face = "InstrumentSans-Medium"
        case .semibold: face = "InstrumentSans-SemiBold"
        case .bold, .heavy, .black: face = "InstrumentSans-Bold"
        default: face = "InstrumentSans-Regular"
        }
        var result = AttributedString()
        guard let font = NSFont(name: face, size: size) else { return AttributedString(string) }
        var run = ""
        var runCovered = true
        func flush() {
            guard !run.isEmpty else { return }
            var piece = AttributedString(run)
            piece.font = runCovered ? BSHType.bureauSans(size, weight: weight) : .system(size: size, weight: weight)
            result += piece
            run = ""
        }
        for character in string {
            var units = Array(String(character).utf16)
            var glyphs = [CGGlyph](repeating: 0, count: units.count)
            let covered = CTFontGetGlyphsForCharacters(font as CTFont, &units, &glyphs, units.count)
            if covered != runCovered { flush(); runCovered = covered }
            run.append(character)
        }
        flush()
        return result
    }

    static func text(_ string: String, size: CGFloat, weight: Font.Weight = .regular) -> Text {
        Text(attributed(string, size: size, weight: weight))
    }
}

/// A paragraph of Instrument Sans set as the browser sets it: broken into lines where the
/// browser breaks them, each line `lineHeight` below the last with its baseline on the pixel
/// grid. (SwiftUI can't set lines closer than the font's own line, 14pt for 11pt Instrument,
/// where the website's are 13.75.) `maxLines` clamps it, the last line ending in "…".
struct MacBureauWebParagraph: View {
    let text: String
    var size: CGFloat
    var weight: Font.Weight = .regular
    var lineHeight: CGFloat
    var maxLines: Int? = nil
    /// `text-align`: each line set at the leading edge, or centred.
    var alignment: HorizontalAlignment = .leading
    @State private var width: CGFloat = 0

    var body: some View {
        let lines = Self.lines(text, size: size, weight: weight, width: width, maxLines: maxLines)
        VStack(alignment: alignment, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                Text(line)
                    .font(BSHType.bureauSans(size, weight: weight))
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .fixedSize(horizontal: index < lines.count - 1, vertical: false)
                    .bureauDeskLine(lineHeight, size)
            }
        }
        .frame(maxWidth: .infinity, alignment: Alignment(horizontal: alignment, vertical: .top))
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
    }

    /// The lines CoreText breaks `text` into at `width` (the browser breaks the same words);
    /// clamped, the last line carries the rest of the text to be cut with an ellipsis.
    static func lines(_ text: String, size: CGFloat, weight: Font.Weight, width: CGFloat, maxLines: Int?) -> [String] {
        guard width > 1 else { return [text] }
        let face: String
        switch weight {
        case .medium: face = "InstrumentSans-Medium"
        case .semibold: face = "InstrumentSans-SemiBold"
        case .bold, .heavy, .black: face = "InstrumentSans-Bold"
        default: face = "InstrumentSans-Regular"
        }
        guard let font = NSFont(name: face, size: size) else { return [text] }
        let string = NSAttributedString(string: text, attributes: [.font: font])
        let setter = CTFramesetterCreateWithAttributedString(string)
        let path = CGPath(rect: CGRect(x: 0, y: 0, width: width + 0.01, height: 100_000), transform: nil)
        let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path, nil)
        guard let ctLines = CTFrameGetLines(frame) as? [CTLine] else { return [text] }
        let ns = text as NSString
        var result: [String] = []
        for (index, line) in ctLines.enumerated() {
            let range = CTLineGetStringRange(line)
            if let maxLines, index == maxLines - 1, ctLines.count > maxLines {
                result.append(ns.substring(from: range.location).trimmingCharacters(in: .whitespacesAndNewlines))
                break
            }
            result.append(ns.substring(with: NSRange(location: range.location, length: range.length)).trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return result.isEmpty ? [text] : result
    }
}

// MARK: - Buttons (`.mac-btn`)

/// The website's `.mac-btn` on the desk: a pill ruled in ink, the brass `--prominent`, the
/// `--plain` glyph button and the `--tint` toggle, at 13pt, 11pt (`--sm`) and 10pt
/// (`--mini`).
struct MacBureauDeskButtonStyle: ButtonStyle {
    enum Kind { case bordered, prominent, plain, tint }
    enum Size { case regular, small, mini }

    var kind: Kind = .bordered
    var size: Size = .regular
    /// The tint of a `--tint` button or a tinted prominent one.
    var tint: Color? = nil

    func makeBody(configuration: Configuration) -> some View {
        MacBureauDeskButtonBody(configuration: configuration, kind: kind, size: size, tint: tint)
    }

    struct Metrics {
        let font: CGFloat, line: CGFloat, padX: CGFloat, padY: CGFloat, gap: CGFloat
    }

    static func metrics(_ size: Size) -> Metrics {
        switch size {
        case .regular: return Metrics(font: 13, line: 15.6, padX: 12, padY: 4.5, gap: 5)
        case .small: return Metrics(font: 11, line: 13.2, padX: 9, padY: 2.5, gap: 4)
        case .mini: return Metrics(font: 10, line: 12, padX: 7, padY: 1.5, gap: 3)
        }
    }
}

/// A lucide glyph as the website paints it: on whole pixels, as Blink snaps an inline svg.
struct MacBureauDeskIcon: View {
    let name: String
    var size: CGFloat

    init(_ name: String, size: CGFloat = 18) {
        self.name = name
        self.size = size
    }

    var body: some View {
        LucideIcon(name, size: size).bureauSnap(x: .whole)
    }
}

/// A `.mac-btn` label: its glyph (a lucide icon, or the AI orb) and its words, the words on
/// the button's line box and as wide as the browser sets them, so a row of buttons lines up
/// with the website's to the pixel.
struct MacBureauDeskButtonLabel: View {
    let title: String
    var icon: String? = nil
    var orb = false
    var iconSize: CGFloat = 14
    var size: MacBureauDeskButtonStyle.Size = .regular

    var body: some View {
        let m = MacBureauDeskButtonStyle.metrics(size)
        HStack(spacing: m.gap) {
            if orb {
                AiOrbView(size: iconSize)
            } else if let icon {
                MacBureauDeskIcon(icon, size: iconSize)
            }
            Text(title)
                .fixedSize()
                .frame(width: MacBureauWebLine.width(title, size: m.font, weight: .medium), alignment: .leading)
                .bureauDeskLine(m.line, m.font)
        }
    }
}

private struct MacBureauDeskButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let kind: MacBureauDeskButtonStyle.Kind
    let size: MacBureauDeskButtonStyle.Size
    let tint: Color?
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let m = MacBureauDeskButtonStyle.metrics(size)
        let live = hovered && isEnabled
        configuration.label
            .font(DeskType.sans(m.font, .medium))
            .lineLimit(1)
            .foregroundStyle(foreground(ink, live: live))
            .padding(.horizontal, m.padX)
            .padding(.vertical, m.padY)
            .bureauBackground { background(ink, live: live) }
            .contentShape(Capsule())
            .brightness(configuration.isPressed && kind != .plain ? -0.04 : 0)
            .opacity(isEnabled ? 1 : 0.45)
            .onHover { hovered = $0 }
    }

    private func foreground(_ ink: MacBureauDeskInk, live: Bool) -> Color {
        switch kind {
        case .bordered: return ink.label
        case .prominent: return .bshFixed(BSHRGB(255, 253, 246))
        case .plain: return live ? ink.label : ink.secondary
        case .tint: return tint ?? ink.accent
        }
    }

    @ViewBuilder
    private func background(_ ink: MacBureauDeskInk, live: Bool) -> some View {
        switch kind {
        case .bordered:
            // --mac-btn-edge: inset 0 0 0 1px ink / 0.2; hover ink / 0.05.
            Capsule()
                .fill(live ? ink.label(0.05) : .clear)
                .overlay(Capsule().strokeBorder(ink.label(0.2), lineWidth: 1))
        case .prominent:
            // Brass with light across its top, an inner highlight and a darker brass rim.
            let metal = tint ?? (live ? ink.accentHover : ink.accent)
            Capsule()
                .fill(metal)
                .overlay(Capsule().fill(LinearGradient(
                    stops: [.init(color: .white.opacity(0.16), location: 0), .init(color: .white.opacity(0), location: 0.6)],
                    startPoint: .top, endPoint: .bottom
                )))
                .overlay(
                    ZStack {
                        Capsule().fill(Color.white.opacity(0.22))
                        Capsule().fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                    }
                    .compositingGroup()
                    .clipShape(Capsule())
                )
                .background(Capsule().inset(by: -0.5).stroke((tint ?? ink.accentHover).opacity(0.55), lineWidth: 1))
        case .plain:
            Capsule().fill(live ? ink.tile : .clear)
        case .tint:
            Capsule().fill((tint ?? ink.accent).opacity(live ? 0.21 : 0.15))
        }
    }
}

// MARK: - Logos (`.monogram`)

/// The website's company tile: the logo on white inset by 8%, corners at 28% of the size,
/// a hairline and a soft shadow; without a logo, the initials on a tint picked from the
/// company id (bureau.css flattens the tint's rim).
struct MacBureauDeskLogo: View {
    let company: MacCompany
    var size: CGFloat
    /// The collapsed directory's open company: lifted, with a deeper shadow.
    var lifted = false

    var body: some View {
        // A new company is a new tile: nothing of the last one's logo carries over.
        MacBureauDeskLogoTile(company: company, size: size, lifted: lifted)
            .id(company.id)
    }
}

private struct MacBureauDeskLogoTile: View {
    let company: MacCompany
    var size: CGFloat
    var lifted = false
    @Environment(\.colorScheme) private var colorScheme
    @State private var image: NSImage?

    private var urls: [URL] {
        [
            MacCompanyLogoResolver.resolvePrimaryLogoUrl(
                logoUrl: company.logoUrl, website: company.website, ticker: company.ticker,
                companyId: company.id, name: company.name ?? company.id
            ),
            MacCompanyLogoResolver.resolveFallbackLogoUrl(
                website: company.website, ticker: company.ticker, companyId: company.id, name: company.name ?? company.id
            ),
        ].compactMap { $0 }
    }

    init(company: MacCompany, size: CGFloat, lifted: Bool = false) {
        self.company = company
        self.size = size
        self.lifted = lifted
        for url in urls {
            if let cached = MacImageCache.shared.image(for: url) {
                _image = State(initialValue: cached)
                break
            }
        }
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: size * 0.28, style: .circular)
        let dark = colorScheme == .dark
        Group {
            if let image {
                // The logo is clipped to its content box's curve (the tile's corner less
                // the 8% padding), as the browser clips a replaced element.
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.2, style: .circular))
                    .padding(size * 0.08)
                    .frame(width: size, height: size)
                    .background(Color.white)
                    .clipShape(shape)
                    .overlay(shape.strokeBorder(dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5))
                    .shadow(
                        color: .black.opacity(lifted ? (dark ? 0.55 : 0.2) : (dark ? 0.35 : 0.06)),
                        radius: lifted ? (dark ? 3 : 2.5) : (dark ? 1.5 : 1),
                        y: lifted ? 2 : 1
                    )
            } else {
                Text(initials)
                    .font(DeskType.sans(size * 0.37, .semibold))
                    .tracking(size * 0.0037)
                    .foregroundStyle(.white)
                    .frame(width: size, height: size)
                    .background(shape.fill(LinearGradient(
                        colors: [tint, tint.opacity(0.72)],
                        startPoint: UnitPoint(x: 0.21, y: 0.09), endPoint: UnitPoint(x: 0.79, y: 0.91)
                    )))
                    .overlay(shape.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
            }
        }
        .frame(width: size, height: size)
        .task(id: company.id) { await load() }
    }

    /// companyInitials (formatters.js): a short ticker, else the first letters of two words.
    private var initials: String {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        if (1...5).contains(ticker.count), ticker.allSatisfy({ $0.isASCII && $0.isLetter }) {
            return String(ticker.prefix(2)).uppercased()
        }
        let name = (company.name ?? "").trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return "?" }
        let tokens = name.split(whereSeparator: { " ,./&+_–—-".contains($0) || $0.isWhitespace })
        if tokens.count >= 2, let a = tokens[0].first, let b = tokens[1].first {
            return "\(a)\(b)".uppercased()
        }
        let word = String((tokens.first.map(String.init) ?? name).filter { $0.isASCII && ($0.isLetter || $0.isNumber) })
        let caps = word.filter(\.isUppercase)
        if caps.count >= 2 { return String(caps.prefix(2)) }
        if word.count >= 2 { return String(word.prefix(2)).uppercased() }
        return word.isEmpty ? "?" : word.uppercased()
    }

    /// The tint the website hashes from the company id.
    private var tint: Color {
        let key = company.id
        var hash: UInt32 = 0
        for unit in key.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        let tints: [BSHRGB] = [
            BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
            BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
        ]
        return .bshFixed(tints[Int(hash % 10)])
    }

    private func load() async {
        guard image == nil else { return }
        for url in urls {
            if let cached = MacImageCache.shared.image(for: url) { image = cached; return }
            guard !MacImageCache.shared.isFailed(url) else { continue }
            var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            if let (data, response) = try? await URLSession.shared.data(for: request),
               (response as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true,
               let loaded = NSImage(data: Self.sanitized(data)) {
                MacImageCache.shared.setImage(loaded, for: url)
                image = loaded
                return
            }
            MacImageCache.shared.markFailed(url)
        }
    }

    /// An SVG sized in ems has no size of its own to draw at.
    private static func sanitized(_ data: Data) -> Data {
        guard var text = String(data: data, encoding: .utf8), text.contains("<svg") else { return data }
        text = text.replacingOccurrences(of: "width=\"1em\"", with: "width=\"64\"")
        text = text.replacingOccurrences(of: "height=\"1em\"", with: "height=\"64\"")
        return text.data(using: .utf8) ?? data
    }
}

// MARK: - The desk

/// Bureau's Research Desk: the directory tray on the left of the sheet and the dossier
/// of the chosen company beside it (ResearchDeskView.vue at `md` and up).
struct MacBureauResearchDesk: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    /// The website's key, so the tray stays folded as it was left.
    @AppStorage("bsh.researchDirectoryCollapsed") private var collapsed = false
    @AppStorage("bsh.sidebar.companySort") private var sortRaw = MacCompanySort.az.rawValue
    @State private var searchText = ""
    @State private var sector = "All"
    @State private var diffsOnly = false

    private var sectors: [String] {
        let found = Set(store.companies.compactMap { $0.sector?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty })
        return ["All"] + found.sorted()
    }

    /// Sorted as the rail sorts, then filtered as the website filters.
    private var companies: [MacCompany] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return MacCompanySort.apply(
            MacCompanySort(rawValue: sortRaw) ?? .az,
            to: store.companies,
            followed: Set(store.followedCompanyIds),
            visits: store.visitedCompanyTimestamps
        )
        .filter { company in
            if diffsOnly && !store.bureauDeskModified(company.id) { return false }
            if sector != "All" && company.sector != sector { return false }
            guard !query.isEmpty else { return true }
            return (company.name ?? "").lowercased().contains(query)
                || (company.ticker ?? "").lowercased().contains(query)
                || company.id.lowercased().contains(query)
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            MacBureauResearchDirectory(
                collapsed: $collapsed,
                searchText: $searchText,
                sector: $sector,
                diffsOnly: $diffsOnly,
                sectors: sectors,
                companies: companies,
                selectedId: store.selectedCompany?.id,
                select: { store.openCompanyPage($0) }
            )
            .frame(width: collapsed ? 44 : 270)
            .frame(maxHeight: .infinity)
            .padding(.vertical, 8)
            .padding(.leading, 8)
            .animation(.easeInOut(duration: 0.28), value: collapsed)

            Group {
                if let company = store.selectedCompany {
                    MacBureauDossier(company: company)
                } else {
                    emptyState
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    /// ContentUnavailableView("No Company Selected", building.2), as the website words it.
    private var emptyState: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(spacing: 0) {
            MacBureauDeskIcon("building-2", size: 44)
                .foregroundStyle(ink.secondary)
            Text("No Company Selected")
                .font(DeskType.sans(17, .semibold))
                .foregroundStyle(ink.label)
                .bureauDeskLine(21.25, 17)
                .padding(.top, 16)
            Text("Select an enterprise from the directory to review research dossiers and investment memos.")
                .font(DeskType.sans(13))
                .foregroundStyle(ink.secondary)
                .multilineTextAlignment(.center)
                .bureauDeskLine(17.55, 13)
                .frame(maxWidth: 384)
                .padding(.top, 6)
        }
        .padding(.horizontal, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - The directory

/// The company directory: a tray pressed into the sheet (bureau.css), holding the sector
/// popup, Diffs, the count and the collapse button; the search field; the list, the open
/// company lifted as fresh paper; and the pitch-deck drop at its foot. Folded, a rail of
/// logos with the button that opens it again.
struct MacBureauResearchDirectory: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Binding var collapsed: Bool
    @Binding var searchText: String
    @Binding var sector: String
    @Binding var diffsOnly: Bool
    let sectors: [String]
    let companies: [MacCompany]
    let selectedId: String?
    let select: (MacCompany) -> Void

    private var ink: MacBureauDeskInk { MacBureauDeskInk(colorScheme) }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 18, style: .circular)
        ZStack(alignment: .topLeading) {
            if collapsed {
                rail
            } else {
                VStack(spacing: 0) {
                    toolbar
                    search
                    list
                    MacBureauDeckDrop()
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .bureauPixelGrid("bureauDirectory")
        .background(shape.fill(ink.card))
        // --shadow: a faint rim of ink and a little shade along the top, pressed in.
        .overlay(shape.strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.label(0.035), lineWidth: 1))
        .overlay(
            shape
                .stroke(ink.dark ? Color.black.opacity(0.35) : ink.shadow(0.04), lineWidth: ink.dark ? 3 : 2)
                .offset(y: 1)
                .blur(radius: ink.dark ? 1.5 : 1)
                .clipShape(shape)
                .allowsHitTesting(false)
        )
        .clipShape(shape)
    }

    // MARK: Toolbar strip

    private var toolbar: some View {
        HStack(spacing: 8) {
            sectorPopup
            Spacer(minLength: 0)
            Button {
                diffsOnly.toggle()
            } label: {
                MacBureauDeskButtonLabel(title: "Diffs", icon: diffsOnly ? "sparkle" : "sparkles", iconSize: 12, size: .mini)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: diffsOnly ? .tint : .bordered, size: .mini))
            .help("Show only companies with updates or new memos since last visit")

            Text("\(companies.count)")
                .font(DeskType.mono(11))
                .foregroundStyle(ink.secondary)
                .bureauExactWidth("\(companies.count)", size: 11, mono: true)
                .bureauDeskLine(13.75, 11)

            Button {
                withAnimation(.easeInOut(duration: 0.28)) { collapsed = true }
            } label: {
                MacBureauDeskIcon("panel-left-close", size: 14)
                    .frame(height: 15.6)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .plain, size: .regular))
            .padding(.horizontal, -6)
            .help("Hide the company directory")
            .accessibilityLabel("Hide the company directory")
        }
        .padding(.horizontal, 12)
        .frame(height: 37)
    }

    /// The sector pop-up (`.mac-popup`): a small pill as wide as its longest sector, ⌃⌄ at
    /// its right.
    private var sectorPopup: some View {
        Menu {
            Picker("Sector", selection: $sector) {
                ForEach(sectors, id: \.self) { value in
                    Text(value).tag(value)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            ZStack(alignment: .leading) {
                // The select is as wide as its widest option.
                ForEach(sectors, id: \.self) { value in
                    Text(value).hidden()
                }
                Text(sector)
            }
            .font(DeskType.sans(11, .medium))
            .foregroundStyle(ink.label)
            .lineLimit(1)
            .bureauDeskLine(13.2, 11)
            .padding(.leading, 9)
            .padding(.trailing, 20)
            .padding(.vertical, 3)
            .overlay(alignment: .trailing) {
                MacBureauDeskIcon("chevrons-up-down", size: 10)
                    .foregroundStyle(ink.secondary)
                    .padding(.trailing, 7)
            }
            .bureauBox(Capsule(), fill: .clear, stroke: ink.label(0.2))
            .contentShape(Capsule())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Sector")
    }

    // MARK: Search

    private var search: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                MacBureauDeskIcon("search", size: 14)
                    .foregroundStyle(ink.secondary)
                TextField("", text: $searchText, prompt: Text("Search companies or tickers…").foregroundStyle(ink.tertiary))
                    .textFieldStyle(.plain)
                    .font(DeskType.sans(13))
                    .foregroundStyle(ink.label)
                    .onExitCommand { searchText = "" }
                    // The input's baseline sits 17pt below the field's top on the website.
                    .padding(.bottom, 2)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        MacBureauDeskIcon("x", size: 12)
                            .foregroundStyle(ink.secondary)
                            .padding(2)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 26)
            .bureauBox(Capsule(), fill: ink.raised, stroke: ink.label(0.14))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            MacBureauGridRule(color: ink.hairline)
        }
    }

    // MARK: List

    private var list: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(companies) { company in
                    MacBureauDirectoryRow(
                        company: company,
                        selected: company.id == selectedId,
                        modified: store.bureauDeskModified(company.id)
                    ) {
                        select(company)
                    }
                }
                if companies.isEmpty {
                    Text("No companies match")
                        .font(DeskType.sans(11))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(13.75, 11)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 48)
                }
            }
            .padding(.vertical, 4)
        }
        .scrollIndicators(.automatic)
        .frame(maxHeight: .infinity)
    }

    // MARK: Folded

    /// The folded directory: the button that opens it, then a logo per company, the open
    /// one lifted.
    private var rail: some View {
        VStack(spacing: 4) {
            Button {
                withAnimation(.easeInOut(duration: 0.28)) { collapsed = false }
            } label: {
                MacBureauDeskIcon("panel-left-open", size: 16)
                    .foregroundStyle(ink.label(0.5))
                    .frame(width: 28, height: 28)
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .help("Show the company directory")
            .accessibilityLabel("Show the company directory")

            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 6) {
                    ForEach(companies) { company in
                        let chosen = company.id == selectedId
                        Button {
                            select(company)
                        } label: {
                            MacBureauDeskLogo(company: company, size: 26, lifted: chosen)
                                .padding(3)
                                .contentShape(RoundedRectangle(cornerRadius: 9, style: .circular))
                        }
                        .buttonStyle(MacBureauRailMarkStyle(selected: chosen))
                        .help(company.name ?? company.id)
                    }
                }
                .padding(.top, 6)
                .padding(.bottom, 8)
                .frame(maxWidth: .infinity)
            }
            .scrollClipDisabled()
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }
}

/// A logo on the folded directory: it grows a little when pointed at, and the open
/// company's stays grown.
private struct MacBureauRailMarkStyle: ButtonStyle {
    let selected: Bool

    func makeBody(configuration: Configuration) -> some View {
        MarkBody(configuration: configuration, selected: selected)
    }

    private struct MarkBody: View {
        let configuration: ButtonStyleConfiguration
        let selected: Bool
        @State private var hovered = false

        var body: some View {
            configuration.label
                .scaleEffect(configuration.isPressed ? 1.04 : (selected ? 1.14 : (hovered ? 1.1 : 1)))
                .animation(.spring(response: 0.3, dampingFraction: 0.6), value: hovered)
                .animation(.spring(response: 0.3, dampingFraction: 0.6), value: selected)
                .onHover { hovered = $0 }
        }
    }
}

/// A company in the directory (`.mac-row`): its logo, its name and line, the modified pip
/// and the private dot; the open company sits on a slip of fresh paper.
private struct MacBureauDirectoryRow: View {
    let company: MacCompany
    let selected: Bool
    let modified: Bool
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    /// ticker · sector (or industry) · a status that is neither public nor private.
    private var line: String {
        var parts: [String] = []
        if let t = company.ticker, !t.isEmpty { parts.append(t.uppercased()) }
        if let s = company.sector, !s.isEmpty { parts.append(s) } else if let i = company.industry, !i.isEmpty { parts.append(i) }
        let status = (company.status ?? "").lowercased()
        if !status.isEmpty, status != "public", status != "private" { parts.append(status.prefix(1).uppercased() + status.dropFirst()) }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        Button(action: action) {
            HStack(spacing: 10) {
                MacBureauDeskLogo(company: company, size: 30)
                    .bureauSnap(x: .whole)
                    .overlay(alignment: .topTrailing) {
                        if modified {
                            Circle()
                                .fill(ink.accent)
                                .frame(width: 8, height: 8)
                                .overlay(Circle().inset(by: -0.75).stroke(ink.card, lineWidth: 1.5))
                                .offset(x: 3, y: -3)
                        }
                    }
                VStack(alignment: .leading, spacing: 2) {
                    Text(company.name ?? company.id)
                        .font(DeskType.sans(13, .medium))
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauDeskLine(16.9, 13)
                    Text(line.isEmpty ? " " : line)
                        .font(DeskType.sans(11))
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauDeskLine(13.75, 11)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if (company.status ?? "").lowercased() == "private" {
                    Circle()
                        .fill(ink.purple)
                        .frame(width: 6, height: 6)
                        .bureauSnap(x: .whole)
                        .help("Private Company")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBackground {
                let pill = RoundedRectangle(cornerRadius: 8, style: .circular)
                if selected {
                    // --mac-pill-fill, --mac-pill-contact and --mac-pill-drop.
                    pill.fill(ink.raised)
                        .overlay(pill.inset(by: -0.5).stroke(ink.label(0.08), lineWidth: 1))
                        .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                } else if hovered {
                    pill.fill(ink.tile)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .accessibilityAddTraits(selected ? .isSelected : [])
        .help(company.name ?? company.id)
    }
}

/// The directory's foot (MacPitchDeckDropBanner): drop a deck to file it, or browse for
/// one. The sheet that files it is the desk's.
private struct MacBureauDeckDrop: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var targeted = false
    @State private var notice: String?
    @State private var noticeTask: Task<Void, Never>?

    private static let deckExtensions: Set<String> = ["pdf", "pptx"]
    private static var deckTypes: [UTType] {
        [UTType.pdf, UTType("org.openxmlformats.presentationml.presentation")].compactMap { $0 }
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let tone = targeted ? ink.accent : (notice == nil ? ink.secondary : ink.orange)
        VStack(spacing: 0) {
            MacBureauGridRule(color: ink.hairline)
            HStack(spacing: 8) {
                MacBureauDeskIcon(targeted ? "file-down" : (notice == nil ? "file-plus-corner" : "triangle-alert"), size: 14)
                    .foregroundStyle(tone)
                MacBureauWebParagraph(
                    text: targeted ? "Drop the deck to file it" : (notice ?? "Drop a pitch deck (PDF or PPTX) to file and extract it"),
                    size: 11,
                    lineHeight: 13.75
                )
                .foregroundStyle(tone)
                Button { browse() } label: { MacBureauDeskButtonLabel(title: "Browse…", size: .small) }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    .fixedSize()
                    .disabled(!store.canEditSources)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(targeted ? ink.accent.opacity(0.1) : .clear)
            .overlay(alignment: .top) {
                if targeted { Rectangle().fill(ink.accent).frame(height: 2) }
            }
        }
        .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
            handleDrop(providers)
        }
        .help("Files the deck under a company, reads the slides and pulls round, raise, post-money, ARR, burn, runway and headcount with page references")
    }

    private func browse() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = Self.deckTypes
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.prompt = "Intake Pitch Deck"
        if panel.runModal() == .OK, let url = panel.url {
            store.ingestDeck(url: url)
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        let candidates = providers.filter { $0.canLoadObject(ofClass: URL.self) }
        guard !candidates.isEmpty else { return false }
        let collected = MacBureauDroppedURLs(count: candidates.count)
        let group = DispatchGroup()
        for (index, provider) in candidates.enumerated() {
            group.enter()
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                collected.set(url, at: index)
                group.leave()
            }
        }
        group.notify(queue: .main) {
            let dropped = collected.urls
            if let deck = dropped.first(where: { Self.deckExtensions.contains($0.pathExtension.lowercased()) }) {
                store.ingestDeck(url: deck)
            } else {
                let names = dropped.map(\.lastPathComponent).joined(separator: ", ")
                showNotice("Only PDF or PPTX decks can be filed — \(names) skipped")
            }
        }
        return true
    }

    private func showNotice(_ text: String) {
        notice = text
        noticeTask?.cancel()
        noticeTask = Task {
            try? await Task.sleep(for: .seconds(6))
            if !Task.isCancelled { notice = nil }
        }
    }
}

private final class MacBureauDroppedURLs: @unchecked Sendable {
    private let lock = NSLock()
    private var slots: [URL?]

    init(count: Int) { slots = Array(repeating: nil, count: count) }

    func set(_ url: URL?, at index: Int) {
        lock.lock(); defer { lock.unlock() }
        slots[index] = url
    }

    var urls: [URL] {
        lock.lock(); defer { lock.unlock() }
        return slots.compactMap { $0 }
    }
}

extension MacAppStore {
    /// The website's "modified" rule for the directory (state.js isCompanyModified): a
    /// company you have not opened counts only when it has memos on file; one you have
    /// opened counts when a memo changed since.
    func bureauDeskModified(_ companyId: String) -> Bool {
        if visitedCompanyTimestamps[companyId] == nil {
            return reports.contains { $0.companyId == companyId }
        }
        return isCompanyModified(companyId)
    }
}

/// A button drawn exactly as its label: pressing or disabling it changes nothing on screen,
/// as the website's disabled stage cells and tiles keep their look.
struct MacBureauFlatButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}
