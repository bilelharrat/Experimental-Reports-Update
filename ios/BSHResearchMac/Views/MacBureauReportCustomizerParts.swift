//
//  MacBureauReportCustomizerParts.swift
//  BSHResearchMac
//
//  The pieces the Generate report dialog under Bureau is drawn with (cards, badges, pills,
//  tabs, the company picker, the monogram), and how they land where Chrome paints them:
//  Chrome lays the page out on fractions of a point, then paints every box, glyph and
//  baseline on a whole point; SwiftUI would paint the half points as they are.
//

import AppKit
import SwiftUI

// MARK: - Chrome's whole points

enum MacBureauCustomizerSpace {
    /// The dialog's coordinate space: its top-left corner, border included.
    static let panel = "bureau.customizer.panel"
}

private struct MacBureauCustomizerPhaseKey: EnvironmentKey {
    static let defaultValue: CGSize = .zero
}

extension EnvironmentValues {
    /// Where Chrome's layout puts the dialog's corner, less where it paints it (the dialog
    /// is drawn at the painted corner). Every box and line inside is painted at
    /// `round(position + phase)`, as Chrome paints it.
    var bureauCustomizerPhase: CGSize {
        get { self[MacBureauCustomizerPhaseKey.self] }
        set { self[MacBureauCustomizerPhaseKey.self] = newValue }
    }
}

/// Paints a leaf (a line of text, a glyph) on the whole point Chrome paints it on: its top,
/// and for a glyph its left edge too (text keeps its fractional advance across the line).
private struct MacBureauCustomizerSnap: ViewModifier {
    var horizontal: Bool
    @Environment(\.bureauCustomizerPhase) private var phase

    func body(content: Content) -> some View {
        let phase = phase
        let horizontal = horizontal
        return content.visualEffect { effect, proxy in
            let frame = proxy.frame(in: .named(MacBureauCustomizerSpace.panel))
            let dy = (frame.minY + phase.height).rounded() - frame.minY
            let dx = horizontal ? (frame.minX + phase.width).rounded() - frame.minX : 0
            return effect.offset(x: dx, y: dy)
        }
    }
}

extension View {
    func customizerSnap(horizontal: Bool = false) -> some View {
        modifier(MacBureauCustomizerSnap(horizontal: horizontal))
    }
}

/// A box's face (fill, rule, ring) drawn in the rectangle Chrome paints the box in: each
/// edge rounded to a whole point. Put it in a `.background`.
struct MacBureauCustomizerSnapped<Content: View>: View {
    @ViewBuilder var content: () -> Content
    @Environment(\.bureauCustomizerPhase) private var phase

    var body: some View {
        GeometryReader { proxy in
            let frame = proxy.frame(in: .named(MacBureauCustomizerSpace.panel))
            let left = (frame.minX + phase.width).rounded(), right = (frame.maxX + phase.width).rounded()
            let top = (frame.minY + phase.height).rounded(), bottom = (frame.maxY + phase.height).rounded()
            content()
                .frame(width: max(0, right - left), height: max(0, bottom - top))
                .offset(x: left - frame.minX, y: top - frame.minY)
        }
        .allowsHitTesting(false)
    }
}

/// A rounded box: its fill, a 1pt rule inside its edge, and optionally a 1pt ring outside it
/// (`ring-1`).
struct MacBureauCustomizerBoxFace: View {
    let radius: CGFloat
    var fill: Color = .clear
    var border: Color? = nil
    var ring: Color? = nil

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: radius, style: .circular).fill(fill)
            if let border {
                RoundedRectangle(cornerRadius: radius, style: .circular).strokeBorder(border, lineWidth: 1)
            }
            if let ring {
                RoundedRectangle(cornerRadius: radius + 1, style: .circular)
                    .strokeBorder(ring, lineWidth: 1)
                    .padding(-1)
            }
        }
    }
}

/// `flex items-center justify-between`: the first view takes what the second leaves (or,
/// with `flexibleLast`, the other way round), both centered on the row.
struct MacBureauCustomizerRow: Layout {
    var spacing: CGFloat
    var flexibleLast = false

    private func sizes(_ width: CGFloat?, _ subviews: Subviews) -> [CGSize] {
        guard subviews.count == 2 else { return subviews.map { $0.sizeThatFits(.unspecified) } }
        let fixed = flexibleLast ? 0 : 1, flexible = flexibleLast ? 1 : 0
        let fixedSize = subviews[fixed].sizeThatFits(.unspecified)
        let room = width.map { max(0, $0 - spacing - fixedSize.width) }
        let flexibleSize = subviews[flexible].sizeThatFits(ProposedViewSize(width: room, height: nil))
        var result = [CGSize.zero, .zero]
        result[fixed] = fixedSize
        result[flexible] = CGSize(width: room ?? flexibleSize.width, height: flexibleSize.height)
        return result
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let s = sizes(proposal.width, subviews)
        let width = proposal.width ?? (s.map(\.width).reduce(0, +) + spacing * CGFloat(max(0, s.count - 1)))
        return CGSize(width: width, height: s.map(\.height).max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let s = sizes(bounds.width, subviews)
        guard s.count == 2 else {
            for (index, subview) in subviews.enumerated() {
                subview.place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(s[index]))
            }
            return
        }
        subviews[0].place(
            at: CGPoint(x: bounds.minX, y: bounds.minY + (bounds.height - s[0].height) / 2),
            anchor: .topLeading, proposal: ProposedViewSize(s[0])
        )
        subviews[1].place(
            at: CGPoint(x: bounds.maxX - s[1].width, y: bounds.minY + (bounds.height - s[1].height) / 2),
            anchor: .topLeading, proposal: ProposedViewSize(s[1])
        )
    }
}

// MARK: - Type

enum MacBureauCustomizerType {
    /// Instrument Sans at a size and weight, as CoreText sets it (for measuring and breaking).
    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> CTFont {
        let name: String
        switch weight {
        case .medium: name = "InstrumentSans-Medium"
        case .semibold: name = "InstrumentSans-SemiBold"
        case .bold: name = "InstrumentSans-Bold"
        default: name = BSHType.bureauSans
        }
        return CTFontCreateWithName(name as CFString, size, nil)
    }

    /// Instrument Sans slanted as Chrome slants a face it has no italic for: the roman's
    /// outlines skewed a quarter of their height to the right. (SwiftUI's `.italic()` leaves
    /// a face with no italic upright.)
    static func oblique(_ size: CGFloat) -> Font {
        var skew = CGAffineTransform(a: 1, b: 0, c: 0.25, d: 1, tx: 0, ty: 0)
        return Font(CTFontCreateWithName(BSHType.bureauSans as CFString, size, &skew))
    }

    /// A run of text's exact advance, letter-spacing included, as Chrome lays it out.
    /// (SwiftUI rounds a Text's width up to the pixel; in a row of chips or tabs the half
    /// points add up.)
    static func advance(_ text: String, font: CTFont, tracking: CGFloat = 0) -> CGFloat {
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [.font: font]))
        return CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil)) + tracking * CGFloat(text.count)
    }

    /// A paragraph broken into lines as Chrome breaks it. (SwiftUI's own breaking pushes a
    /// word down to spare a lone word on the last line; Chrome, and CoreText's framesetter,
    /// do not.) With `clamp`, Chrome's `line-clamp`: the lines as broken, the last one kept
    /// ended with "…", shortened further only if the ellipsis would not fit.
    static func lines(_ text: String, font: CTFont, width: CGFloat, clamp: Int? = nil) -> [String] {
        guard width > 0 else { return [text] }
        let setter = CTFramesetterCreateWithAttributedString(NSAttributedString(string: text, attributes: [.font: font]))
        let path = CGPath(rect: CGRect(x: 0, y: 0, width: width, height: 100_000), transform: nil)
        let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path, nil)
        guard let laid = CTFrameGetLines(frame) as? [CTLine], !laid.isEmpty else { return [text] }
        let ns = text as NSString
        var lines = laid.map { line -> String in
            let range = CTLineGetStringRange(line)
            return ns.substring(with: NSRange(location: range.location, length: range.length))
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let clamp, clamp > 0, lines.count > clamp {
            lines = Array(lines.prefix(clamp))
            var last = lines[clamp - 1]
            func fits(_ candidate: String) -> Bool {
                advance(candidate + "…", font: font) <= width
            }
            while !last.isEmpty, !fits(last) {
                last = String(last.dropLast()).trimmingCharacters(in: .whitespaces)
            }
            lines[clamp - 1] = last + "…"
        }
        return lines
    }
}

extension View {
    /// Lays a line of text out at its exact advance, as Chrome does, capped at `maxWidth`
    /// (where it truncates instead).
    func customizerAdvance(_ text: String, font: CTFont, tracking: CGFloat = 0, maxWidth: CGFloat? = nil) -> some View {
        let exact = MacBureauCustomizerType.advance(text, font: font, tracking: tracking)
        return Group {
            if let maxWidth, exact > maxWidth {
                self.frame(width: maxWidth, alignment: .leading)
            } else {
                self.fixedSize().frame(width: exact, alignment: .leading)
            }
        }
    }
}

/// A paragraph set as Chrome sets it: broken where Chrome breaks it, each line its own line
/// box `lineHeight` tall, each painted on the whole point Chrome paints it on.
struct MacBureauCustomizerParagraph: View {
    let text: String
    let size: CGFloat
    var weight: Font.Weight = .regular
    let lineHeight: CGFloat
    var oblique = false
    var clamp: Int? = nil
    var alignment: TextAlignment = .leading
    @State private var width: CGFloat = 0

    private var font: Font { oblique ? MacBureauCustomizerType.oblique(size) : BSHType.bureauSans(size, weight: weight) }

    private var frameAlignment: Alignment {
        switch alignment {
        case .center: return .center
        case .trailing: return .trailing
        default: return .leading
        }
    }

    private var stackAlignment: HorizontalAlignment {
        switch alignment {
        case .center: return .center
        case .trailing: return .trailing
        default: return .leading
        }
    }

    var body: some View {
        Group {
            if width > 0 {
                let broken = MacBureauCustomizerType.lines(text, font: MacBureauCustomizerType.sans(size, oblique ? .regular : weight), width: width, clamp: clamp)
                VStack(alignment: stackAlignment, spacing: 0) {
                    ForEach(Array(broken.enumerated()), id: \.offset) { _, line in
                        Text(line)
                            .font(font)
                            .lineLimit(1)
                            .bureauLines(lineHeight, size: size)
                            .customizerSnap()
                            .customizerAdvance(line, font: MacBureauCustomizerType.sans(size, oblique ? .regular : weight))
                    }
                }
            } else {
                Text(text)
                    .font(font)
                    .lineLimit(clamp)
                    .multilineTextAlignment(alignment)
                    .fixedSize(horizontal: false, vertical: true)
                    .bureauLines(lineHeight, size: size)
            }
        }
        .frame(maxWidth: .infinity, alignment: frameAlignment)
        .background(GeometryReader { geo in
            Color.clear
                .onAppear { width = geo.size.width }
                .onChange(of: geo.size.width) { _, new in width = new }
        })
    }
}

// MARK: - Colors the kit leaves out

extension MacBureauPageInk {
    /// `--color-surface-muted`: the well a badge or a chip sits in.
    var customizerSurfaceMuted: Color {
        let desk = BSHBureauDesk.active
        guard dark else { return .bshFixed(desk == .onyx ? BSHRGB(226, 224, 218) : BSHRGB(233, 228, 216)) }
        switch desk {
        case .onyx: return .bshFixed(BSHRGB(11, 11, 11))
        case .green: return .bshFixed(BSHRGB(11, 16, 14))
        case .maroon: return .bshFixed(BSHRGB(26, 10, 14))
        case .navy: return .bshFixed(BSHRGB(10, 14, 22))
        case .aubergine: return .bshFixed(BSHRGB(17, 11, 17))
        case .tobacco: return .bshFixed(BSHRGB(18, 14, 10))
        case .graphite: return .bshFixed(BSHRGB(13, 15, 18))
        }
    }

    /// `--color-warning-soft`.
    var customizerWarningSoft: Color { .bshFixed(dark ? BSHRGB(55, 40, 16) : BSHRGB(246, 232, 208)) }

    /// `--scrim`: a dialog's shade over the desk, tinted toward the desk by day.
    var customizerScrim: Color {
        if dark { return Color.black.opacity(0.32) }
        switch BSHBureauDesk.active {
        case .onyx: return Color.black.opacity(0.22)
        case .green: return .bshFixed(BSHRGB(8, 16, 13), opacity: 0.22)
        case .maroon: return .bshFixed(BSHRGB(22, 6, 9), opacity: 0.22)
        case .navy: return .bshFixed(BSHRGB(6, 10, 20), opacity: 0.22)
        case .aubergine: return .bshFixed(BSHRGB(14, 7, 14), opacity: 0.22)
        case .tobacco: return .bshFixed(BSHRGB(14, 10, 6), opacity: 0.22)
        case .graphite: return .bshFixed(BSHRGB(8, 10, 12), opacity: 0.22)
        }
    }
}

// MARK: - Controls

/// A button that draws only its label: no dimming of its own when disabled (the control
/// dims itself as one piece, as CSS opacity does).
struct MacBureauCustomizerBareStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { configuration.label }
}

/// `.vogue-label` under Bureau: Instrument Serif Italic at 15.5pt on a 20pt line, in the
/// secondary ink. (A `.custom` font is set at a whole point, so the face is built at 15.5.)
struct MacBureauCustomizerKicker: View {
    let text: String
    @Environment(\.colorScheme) private var colorScheme
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(Font(CTFontCreateWithName(BSHType.bureauSerifItalic as CFString, 15.5, nil)))
            .foregroundStyle(MacBureauPageInk(scheme: colorScheme).secondary)
            .lineLimit(1)
            .fixedSize()
            .frame(height: 20, alignment: .top)
            .customizerSnap()
    }
}

/// An option card (`rounded-xl border p-…`): the tray ruled in the page's line; chosen, brass
/// ringed in the glow on a wash of the soft brass; hovered, a stronger rule.
struct MacBureauCustomizerCard<Content: View>: View {
    let chosen: Bool
    var enabled = true
    /// The card's opacity while it can't be chosen.
    var dimmed: Double = 0.4
    var padding: CGFloat
    var alignment: Alignment = .topLeading
    /// Engine and quality cards keep the chosen look while locked (the run still uses it).
    var keepsChosenLook = false
    /// In a grid row the card takes the row's height; elsewhere its own.
    var fillsHeight = true
    let action: () -> Void
    @ViewBuilder let content: () -> Content

    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    init(
        chosen: Bool, enabled: Bool = true, dimmed: Double = 0.4, padding: CGFloat, alignment: Alignment = .topLeading,
        keepsChosenLook: Bool = false, fillsHeight: Bool = true, action: @escaping () -> Void, @ViewBuilder content: @escaping () -> Content
    ) {
        self.chosen = chosen
        self.enabled = enabled
        self.dimmed = dimmed
        self.padding = padding
        self.alignment = alignment
        self.keepsChosenLook = keepsChosenLook
        self.fillsHeight = fillsHeight
        self.action = action
        self.content = content
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let lit = chosen && (enabled || keepsChosenLook)
        Button(action: action) {
            content()
                .padding(padding + 1)
                .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil, alignment: alignment)
                .background(MacBureauCustomizerSnapped {
                    MacBureauCustomizerBoxFace(
                        radius: 12,
                        fill: lit ? ink.accentSoft.opacity(0.5) : ink.tray,
                        border: lit ? ink.accent : (hovered && enabled ? ink.ruleStrong : ink.rule),
                        ring: lit ? ink.accentGlow(1) : nil
                    )
                })
                .contentShape(RoundedRectangle(cornerRadius: 12, style: .circular))
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .disabled(!enabled)
        .onHover { hovered = $0 }
        .compositingGroup()
        .opacity(enabled ? 1 : dimmed)
    }
}

/// A card's badge: 10pt semibold on a pill — brass with white type when its card is chosen,
/// otherwise the muted well ruled in the page's line.
struct MacBureauCustomizerBadge: View {
    let text: String
    let filled: Bool
    let lineHeight: CGFloat
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Text(text)
            .font(BSHType.bureauSans(10, weight: .semibold))
            .foregroundStyle(filled ? Color.white : ink.muted)
            .lineLimit(1)
            .bureauLines(lineHeight, size: 10)
            .customizerSnap()
            .customizerAdvance(text, font: MacBureauCustomizerType.sans(10, .semibold))
            .padding(.horizontal, filled ? 8 : 9)
            .padding(.vertical, filled ? 2 : 3)
            .background(MacBureauCustomizerSnapped {
                MacBureauCustomizerBoxFace(radius: 999, fill: filled ? ink.accent : ink.customizerSurfaceMuted, border: filled ? nil : ink.rule)
            })
    }
}

/// The audience's radio: a 16pt ring in the strong rule, or brass with a white check.
struct MacBureauCustomizerRadio: View {
    let on: Bool
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        ZStack {
            if on {
                LucideIcon("check", size: 10)
                    .foregroundStyle(Color.white)
                    .customizerSnap(horizontal: true)
            }
        }
        .frame(width: 16, height: 16)
        .background(MacBureauCustomizerSnapped {
            ZStack {
                Circle().fill(on ? ink.accent : ink.tray)
                Circle().strokeBorder(on ? ink.accent : ink.ruleStrong, lineWidth: 1)
            }
        })
    }
}

/// The dialog's tab: 12pt medium with its glyph; chosen, a brass pill with white type.
struct MacBureauCustomizerTabButton: View {
    let tab: MacBureauCustomizer.Tab
    let chosen: Bool
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 8) {
                LucideIcon(tab.icon, size: 14)
                    .customizerSnap(horizontal: true)
                Text(tab.title)
                    .font(BSHType.bureauSans(12, weight: .medium))
                    .lineLimit(1)
                    .bureauLines(16, size: 12)
                    .customizerSnap()
                    .customizerAdvance(tab.title, font: MacBureauCustomizerType.sans(12, .medium))
            }
            .foregroundStyle(chosen ? Color.white : (hovered ? ink.ink : ink.secondary))
            .padding(.horizontal, 14)
            .frame(height: 28)
            .background(MacBureauCustomizerSnapped {
                RoundedRectangle(cornerRadius: 8, style: .circular)
                    .fill(chosen ? ink.accent : (hovered ? ink.customizerSurfaceMuted : Color.clear))
            })
            .contentShape(RoundedRectangle(cornerRadius: 8, style: .circular))
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .onHover { hovered = $0 }
    }
}

/// The company's name as a button that opens the picker: 16pt semibold with a chevron;
/// brass ink on hover.
struct MacBureauCustomizerCompanyButton: View {
    let title: String
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title)
                    .font(BSHType.bureauSans(16, weight: .semibold))
                    .foregroundStyle(hovered ? ink.accentInk : ink.ink)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(24, size: 16)
                    .customizerSnap()
                    .customizerAdvance(title, font: MacBureauCustomizerType.sans(16, .semibold), maxWidth: 400)
                LucideIcon("chevron-down", size: 16)
                    .foregroundStyle(ink.muted)
                    .customizerSnap(horizontal: true)
            }
            .frame(height: 24)
            .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .onHover { hovered = $0 }
    }
}

/// The header's close button: a 20pt ✕ in the muted ink on a 32pt square; lit on hover.
struct MacBureauCustomizerCloseButton: View {
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            LucideIcon("x", size: 20)
                .foregroundStyle(hovered ? ink.ink : ink.muted)
                .customizerSnap(horizontal: true)
                .frame(width: 32, height: 32)
                .background(MacBureauCustomizerSnapped {
                    RoundedRectangle(cornerRadius: 8, style: .circular).fill(hovered ? ink.customizerSurfaceMuted : Color.clear)
                })
                .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .onHover { hovered = $0 }
        .help(MacBureauCustomizer.Copy.close)
        .accessibilityLabel(MacBureauCustomizer.Copy.close)
    }
}

/// The company picker hanging under the name: a 320pt tray with a search field and the
/// workspace's companies.
struct MacBureauCustomizerCompanyPicker: View {
    @ObservedObject var model: MacBureauCustomizerModel
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(alignment: .leading, spacing: 8) {
            ZStack(alignment: .leading) {
                MacBureauCustomizerField(placeholder: MacBureauCustomizer.Copy.searchCompany, text: $model.companySearch, leading: 32)
                LucideIcon("search", size: 14)
                    .foregroundStyle(ink.muted)
                    .padding(.leading, 10)
                    .allowsHitTesting(false)
            }
            ScrollView(.vertical) {
                VStack(spacing: 2) {
                    ForEach(model.filteredCompanies) { company in
                        MacBureauCustomizerPickerRow(
                            company: company,
                            identity: model.identityLine(for: company),
                            chosen: company.id == model.company?.id
                        ) {
                            model.companyId = company.id
                            model.pickerOpen = false
                        }
                    }
                }
            }
            .frame(maxHeight: 256)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(9)
        .frame(width: 320, alignment: .topLeading)
        .background(MacBureauCustomizerSnapped {
            ZStack {
                MacBureauCustomizerBoxFace(radius: 12, fill: ink.tray, border: ink.rule)
                // The tray's own pressed-in edge (`--shadow` under Bureau).
                RoundedRectangle(cornerRadius: 11, style: .circular)
                    .strokeBorder(ink.ink(0.035), lineWidth: 1)
                    .padding(1)
            }
        })
    }
}

struct MacBureauCustomizerPickerRow: View {
    let company: MacCompany
    let identity: String
    let chosen: Bool
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(alignment: .center, spacing: 8) {
                MacBureauCustomizerMonogram(company: company, size: 20)
                VStack(alignment: .leading, spacing: 0) {
                    Text(company.name ?? company.id)
                        .font(BSHType.bureauSans(14, weight: chosen ? .medium : .regular))
                        .foregroundStyle(chosen ? ink.accentInk : ink.ink)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauLines(20, size: 14)
                        .customizerSnap()
                    if !identity.isEmpty {
                        Text(identity)
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.muted)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .bureauLines(20, size: 11)
                            .customizerSnap()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let ticker = company.ticker, !ticker.isEmpty {
                    Text(ticker.uppercased())
                        .font(BSHType.bureauSans(12, weight: chosen ? .medium : .regular))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                        .fixedSize()
                        .customizerSnap()
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(MacBureauCustomizerSnapped {
                RoundedRectangle(cornerRadius: 8, style: .circular)
                    .fill(chosen ? ink.accent.opacity(0.1) : (hovered ? ink.customizerSurfaceMuted : Color.clear))
            })
            .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .onHover { hovered = $0 }
    }
}

/// An analysed document on the Evidence tab: its check, its title and the day it came in.
struct MacBureauCustomizerEvidenceRow: View {
    @Binding var source: MacBureauCustomizerModel.EvidenceSource
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button { source.checked.toggle() } label: {
            HStack(alignment: .center, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 3, style: .circular)
                        .fill(source.checked ? ink.accent : ink.raised)
                    RoundedRectangle(cornerRadius: 3, style: .circular)
                        .strokeBorder(source.checked ? ink.accent : ink.ruleStrong, lineWidth: 1)
                    if source.checked {
                        LucideIcon("check", size: 11).foregroundStyle(Color.white)
                    }
                }
                .frame(width: 14, height: 14)
                .customizerSnap(horizontal: true)
                Text(source.label)
                    .font(BSHType.bureauSans(14, weight: .medium))
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
                    .customizerSnap()
                Spacer(minLength: 8)
                if !source.uploadedAt.isEmpty {
                    Text(source.uploadedAt)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                        .customizerSnap()
                }
            }
            .padding(15)
            .background(MacBureauCustomizerSnapped {
                MacBureauCustomizerBoxFace(radius: 12, fill: ink.tray, border: hovered ? ink.ruleStrong : ink.rule)
            })
            .contentShape(RoundedRectangle(cornerRadius: 12, style: .circular))
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .onHover { hovered = $0 }
    }
}

/// The run controls' switch as the website renders it inside the dialog: the page's rule for
/// checkboxes (`.mac-desk input[type=checkbox]`, 14pt) shrinks its `.switch` to a 14pt dot,
/// with the 18pt knob (2pt in, 16pt further when on) drawn over it.
struct MacBureauCustomizerSwitch: View {
    @Binding var isOn: Bool
    var disabled = false
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button {
            withAnimation(.spring(response: 0.32, dampingFraction: 0.72)) { isOn.toggle() }
        } label: {
            ZStack(alignment: .topLeading) {
                Circle()
                    .fill(isOn ? ink.switchOn : ink.ink(0.16))
                    .overlay(Circle().strokeBorder(ink.ink(0.08), lineWidth: 0.5))
                    .frame(width: 14, height: 14)
                Circle()
                    .fill(Color.bshFixed(BSHRGB(255, 253, 248)))
                    .overlay(Circle().strokeBorder(Color.black.opacity(0.06), lineWidth: 0.5).padding(-0.5))
                    .shadow(color: .black.opacity(0.22), radius: 1, y: 1)
                    .frame(width: 18, height: 18)
                    .offset(x: isOn ? 18 : 2, y: 2)
            }
            .frame(width: 14, height: 14, alignment: .topLeading)
            .customizerSnap(horizontal: true)
            .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauCustomizerBareStyle())
        .disabled(disabled)
        .opacity(disabled ? 0.5 : 1)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(isOn ? "On" : "Off")
    }
}

/// The website's small pill (`.btn-sm`): 12pt medium on a 26pt capsule — bordered in the
/// page's ink, or brass with light across its top. Pressed, it sinks half a point.
struct MacBureauCustomizerPill: View {
    let title: String
    var filled = false
    var busy = false
    var fontSize: CGFloat = 12
    var verticalPadding: CGFloat = 4
    var tracking: CGFloat = -0.072
    var maxLabelWidth: CGFloat? = nil
    let action: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovered = false
    @State private var pressed = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 4.8) {
                if filled {
                    Group {
                        if busy {
                            MacBureauCustomizerSpinner()
                        } else {
                            AiOrbView(size: 16)
                        }
                    }
                    .customizerSnap(horizontal: true)
                }
                Text(title)
                    .font(BSHType.bureauSans(fontSize, weight: .medium))
                    .tracking(tracking)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(18, size: fontSize)
                    .customizerSnap()
                    .customizerAdvance(title, font: MacBureauCustomizerType.sans(fontSize, .medium), tracking: tracking, maxWidth: maxLabelWidth)
            }
            .foregroundStyle(filled ? Color.bshFixed(BSHRGB(255, 253, 246)) : ink.ink)
            .padding(.horizontal, 11.2)
            .padding(.vertical, verticalPadding)
            .background(MacBureauCustomizerSnapped { face(ink) })
            .contentShape(Capsule())
            .offset(y: pressed ? 0.5 : 0)
        }
        .buttonStyle(MacBureauPressReporter(pressed: $pressed))
        .onHover { hovered = $0 }
        .compositingGroup()
        .opacity(isEnabled ? 1 : 0.4)
    }

    @ViewBuilder
    private func face(_ ink: MacBureauPageInk) -> some View {
        if filled {
            Capsule()
                .fill(hovered && isEnabled ? ink.accentHover : ink.accent)
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
                .background(Capsule().inset(by: -0.5).stroke(ink.accentHover.opacity(0.55), lineWidth: 1))
                .shadow(color: ink.shadow(0.18), radius: 1, y: 1)
        } else {
            Capsule()
                .fill(hovered && isEnabled ? ink.ink(0.05) : Color.clear)
                .overlay(Capsule().strokeBorder(ink.ink(hovered && isEnabled ? 0.36 : 0.2), lineWidth: 1))
        }
    }
}

/// The website's `Loader2 animate-spin`: the loader glyph turning once a second.
struct MacBureauCustomizerSpinner: View {
    @State private var turning = false

    var body: some View {
        LucideIcon("loader-circle", size: 16)
            .rotationEffect(.degrees(turning ? 360 : 0))
            .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: turning)
            .onAppear { turning = true }
    }
}

/// The website's Monogram: the company's logo on a white tile (28% corners, the logo 8% in),
/// or its initials on the tint its id hashes to while the logo loads or when there is none.
struct MacBureauCustomizerMonogram: View {
    let company: MacCompany
    let size: CGFloat
    @Environment(\.colorScheme) private var colorScheme
    @State private var image: NSImage?

    private var primaryURL: URL? {
        MacCompanyLogoResolver.resolvePrimaryLogoUrl(
            logoUrl: company.logoUrl, logoDomain: company.logoDomain, website: company.website,
            ticker: company.ticker, companyId: company.id, name: company.name
        )
    }

    private var fallbackURL: URL? {
        MacCompanyLogoResolver.resolveFallbackLogoUrl(
            logoDomain: company.logoDomain, website: company.website, ticker: company.ticker,
            companyId: company.id, name: company.name
        )
    }

    var body: some View {
        let dark = colorScheme == .dark
        let shape = RoundedRectangle(cornerRadius: size * 0.28, style: .circular)
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .padding(size * 0.08)
                    .frame(width: size, height: size)
                    .background(shape.fill(Color.white))
                    .clipShape(shape)
                    .overlay(shape.strokeBorder(dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5))
                    .shadow(color: .black.opacity(dark ? 0.35 : 0.06), radius: dark ? 1.5 : 1, y: 1)
            } else {
                let tint = Self.tint(for: company.id)
                Text(Self.initials(company))
                    .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
                    .tracking(size * 0.37 * 0.01)
                    .foregroundStyle(Color.white)
                    .frame(width: size, height: size)
                    .background(shape.fill(LinearGradient(
                        colors: [Color.bshFixed(tint), Color.bshFixed(tint, opacity: 0.72)],
                        startPoint: UnitPoint(x: 0.21, y: 0.09), endPoint: UnitPoint(x: 0.79, y: 0.91)
                    )))
                    .overlay(shape.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
            }
        }
        .customizerSnap(horizontal: true)
        .task(id: primaryURL?.absoluteString ?? fallbackURL?.absoluteString ?? company.id) { await load() }
    }

    private func load() async {
        for url in [primaryURL, fallbackURL].compactMap({ $0 }) {
            if let cached = MacImageCache.shared.image(for: url) {
                image = cached
                return
            }
        }
        for url in [primaryURL, fallbackURL].compactMap({ $0 }) where !MacImageCache.shared.isFailed(url) {
            var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            if let (data, response) = try? await URLSession.shared.data(for: request),
               (response as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true,
               let loaded = NSImage(data: data) {
                MacImageCache.shared.setImage(loaded, for: url)
                image = loaded
                return
            }
            MacImageCache.shared.markFailed(url)
        }
    }

    /// formatters.js `companyInitials`.
    static func initials(_ company: MacCompany) -> String {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        if (1...5).contains(ticker.count), ticker.allSatisfy({ $0.isASCII && $0.isLetter }) {
            return String(ticker.prefix(2)).uppercased()
        }
        let name = (company.name ?? "").trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return "?" }
        let tokens = name.split { " \t\n,./&+_–—-".contains($0) }.map(String.init)
        if tokens.count >= 2 {
            return (String(tokens[0].prefix(1)) + String(tokens[1].prefix(1))).uppercased()
        }
        let word = (tokens.first ?? name).filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let caps = word.filter { $0.isUppercase }
        if caps.count >= 2 { return String(caps.prefix(2)) }
        if word.count >= 2 { return String(word.prefix(2)).uppercased() }
        return word.isEmpty ? "?" : word.uppercased()
    }

    /// Monogram.vue's tint: a stable hash of the id into ten colors.
    static func tint(for id: String) -> BSHRGB {
        var hash: UInt32 = 0
        for unit in id.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        let tints = [
            BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
            BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
        ]
        return tints[Int(hash % 10)]
    }
}

/// The website's small field under Bureau (`.field.field-sm`): 12pt on fresh paper, 28pt
/// tall, ruled in the page's ink; hovered, the rule darkens; focused, a brass edge and its glow.
struct MacBureauCustomizerField: View {
    let placeholder: String
    @Binding var text: String
    var leading: CGFloat = 10
    var alignment: TextAlignment = .leading
    /// `tabular`: figures set to one width.
    var digits = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @FocusState private var focused: Bool
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        TextField("", text: $text, prompt: Text(placeholder).foregroundStyle(ink.subtle))
            .textFieldStyle(.plain)
            .font(digits ? BSHType.bureauSans(12).monospacedDigit() : BSHType.bureauSans(12))
            .foregroundStyle(ink.ink)
            .multilineTextAlignment(alignment)
            .focused($focused)
            .padding(.leading, leading)
            .padding(.trailing, 10)
            .frame(height: 28)
            .background(MacBureauCustomizerSnapped {
                MacBureauCustomizerBoxFace(radius: 10, fill: ink.raised, border: focused ? ink.accent : ink.ink(hovered && isEnabled ? 0.28 : 0.14))
            })
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .circular)
                    .strokeBorder(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                    .padding(-3)
                    .allowsHitTesting(false)
            )
            .onHover { hovered = $0 }
    }
}

// MARK: - Layout

/// One row of the website's grid: `columns` equal columns `spacing` apart; each cell as tall
/// as the row's tallest.
struct MacBureauCustomizerRowLayout: Layout {
    let columns: Int
    let spacing: CGFloat

    private func columnWidth(_ width: CGFloat) -> CGFloat {
        max(0, (width - spacing * CGFloat(columns - 1)) / CGFloat(columns))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 600
        let column = columnWidth(width)
        let height = subviews.map { $0.sizeThatFits(ProposedViewSize(width: column, height: nil)).height }.max() ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let column = columnWidth(bounds.width)
        for (index, subview) in subviews.enumerated() {
            let x = bounds.minX + CGFloat(index) * (column + spacing)
            subview.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(width: column, height: bounds.height))
        }
    }
}

/// `flex flex-wrap items-center gap-…`: in a line while they fit, then onto the next.
struct MacBureauCustomizerFlowLayout: Layout {
    let spacing: CGFloat

    private func lines(_ width: CGFloat, _ subviews: Subviews) -> [[(Int, CGSize)]] {
        var lines: [[(Int, CGSize)]] = [[]]
        var x: CGFloat = 0
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            if !lines[lines.count - 1].isEmpty && x + spacing + size.width > width {
                lines.append([])
                x = 0
            }
            x += (lines[lines.count - 1].isEmpty ? 0 : spacing) + size.width
            lines[lines.count - 1].append((index, size))
        }
        return lines
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let limit = proposal.width ?? .infinity
        let all = lines(limit, subviews)
        let width = all.map { line in line.reduce(0) { $0 + $1.1.width } + spacing * CGFloat(max(line.count - 1, 0)) }.max() ?? 0
        let height = all.map { $0.map(\.1.height).max() ?? 0 }.reduce(0, +) + spacing * CGFloat(max(all.count - 1, 0))
        return CGSize(width: min(width, limit), height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in lines(bounds.width, subviews) {
            let height = line.map(\.1.height).max() ?? 0
            var x = bounds.minX
            for (index, size) in line {
                subviews[index].place(at: CGPoint(x: x, y: y + (height - size.height) / 2), anchor: .topLeading, proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += height + spacing
        }
    }
}

/// The footer's `flex flex-wrap items-center justify-between gap-3` with the buttons pushed
/// right (`ml-auto`): the summary and the buttons share a line while they fit; otherwise the
/// buttons go under it, still at the right.
struct MacBureauCustomizerFooterLayout: Layout {
    let gap: CGFloat

    private func measure(_ width: CGFloat, _ subviews: Subviews) -> (left: CGSize, right: CGSize, wraps: Bool) {
        guard subviews.count == 2 else { return (.zero, .zero, false) }
        let right = subviews[1].sizeThatFits(.unspecified)
        let natural = subviews[0].sizeThatFits(.unspecified)
        if natural.width + gap + right.width <= width {
            return (natural, right, false)
        }
        let left = subviews[0].sizeThatFits(ProposedViewSize(width: min(natural.width, width), height: nil))
        return (left, right, true)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 998
        let m = measure(width, subviews)
        let height = m.wraps ? m.left.height + gap + m.right.height : max(m.left.height, m.right.height)
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let m = measure(bounds.width, subviews)
        if m.wraps {
            subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(m.left))
            subviews[1].place(at: CGPoint(x: bounds.maxX - m.right.width, y: bounds.minY + m.left.height + gap), anchor: .topLeading, proposal: ProposedViewSize(m.right))
        } else {
            let height = max(m.left.height, m.right.height)
            subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.minY + (height - m.left.height) / 2), anchor: .topLeading, proposal: ProposedViewSize(m.left))
            subviews[1].place(at: CGPoint(x: bounds.maxX - m.right.width, y: bounds.minY + (height - m.right.height) / 2), anchor: .topLeading, proposal: ProposedViewSize(m.right))
        }
    }
}

/// No frosted band where the choices scroll under the tabs (macOS 26 draws one).
struct MacBureauCustomizerNoScrollEdge: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 26.0, *) {
            content.scrollEdgeEffectHidden(true, for: .all)
        } else {
            content
        }
    }
}
