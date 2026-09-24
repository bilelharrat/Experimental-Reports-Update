//
//  MacBureauKit.swift
//  BSHResearchMac
//
//  The website's page anatomy and controls under Bureau (style.css and bureau.css), for the
//  pages Bureau draws as the website does: the page header, trays, serif headings and
//  italic kickers, segmented controls, switches, pill buttons, rows, chips and fields. The
//  colors are the page's own (the sheet's ink ladder, fills and brass) for the chosen desk
//  and appearance, as the website's tokens are.
//

import AppKit
import SwiftUI

// MARK: - The page's colors

/// The page's tokens (`--color-*` on the sheet) for the active desk and an appearance.
struct MacBureauPageInk {
    let scheme: ColorScheme
    var dark: Bool { scheme == .dark }

    private var desk: BSHBureauDesk { BSHBureauDesk.active }
    private var tones: BSHBureauTones { desk.tones }
    private func pick(_ pair: BSHBureauTones.Pair) -> BSHRGB { dark ? pair.dark : pair.light }

    // The sheet, its ink and what sits on it.
    var sheet: Color { .bshFixed(pick(tones.sheet)) }
    var ink: Color { .bshFixed(pick(tones.ink)) }
    func ink(_ opacity: Double) -> Color { .bshFixed(pick(tones.ink), opacity: opacity) }
    /// `--color-surface`: a tray pressed into the sheet.
    var tray: Color { .bshFixed(pick(tones.tray)) }
    /// `--color-surface-raised`: fresh paper lifted off it.
    var raised: Color { .bshFixed(pick(tones.raised)) }
    /// `--color-border-subtle`.
    var rule: Color { .bshFixed(pick(tones.rule)) }

    /// `--color-border-strong`, `--color-fill`, `-secondary`, `-tertiary`.
    private var fills: (strong: BSHRGB, fill: BSHRGB, second: BSHRGB, third: BSHRGB) {
        switch (desk, dark) {
        case (.onyx, false): return (BSHRGB(188, 186, 179), BSHRGB(221, 219, 213), BSHRGB(227, 225, 220), BSHRGB(234, 232, 227))
        case (.onyx, true): return (BSHRGB(66, 65, 64), BSHRGB(48, 48, 47), BSHRGB(40, 40, 39), BSHRGB(33, 33, 32))
        case (_, false): return (BSHRGB(196, 187, 168), BSHRGB(226, 220, 206), BSHRGB(232, 227, 214), BSHRGB(238, 234, 223))
        case (.green, true): return (BSHRGB(62, 74, 68), BSHRGB(44, 54, 49), BSHRGB(36, 46, 41), BSHRGB(29, 38, 34))
        case (.maroon, true): return (BSHRGB(75, 61, 62), BSHRGB(58, 43, 46), BSHRGB(51, 35, 39), BSHRGB(43, 28, 32))
        case (.navy, true): return (BSHRGB(63, 66, 71), BSHRGB(45, 48, 56), BSHRGB(37, 41, 49), BSHRGB(29, 34, 43))
        case (.aubergine, true): return (BSHRGB(71, 63, 67), BSHRGB(53, 46, 51), BSHRGB(46, 38, 44), BSHRGB(39, 31, 38))
        case (.tobacco, true): return (BSHRGB(74, 67, 60), BSHRGB(57, 50, 44), BSHRGB(50, 43, 37), BSHRGB(42, 35, 30))
        case (.graphite, true): return (BSHRGB(67, 68, 70), BSHRGB(49, 51, 55), BSHRGB(41, 44, 48), BSHRGB(34, 36, 42))
        }
    }
    var ruleStrong: Color { .bshFixed(fills.strong) }
    var fill: Color { .bshFixed(fills.fill) }
    var fillSecondary: Color { .bshFixed(fills.second) }
    var fillTertiary: Color { .bshFixed(fills.third) }

    /// The ink ladder (`--color-text-secondary`, `-muted`, `-subtle`).
    private var ladder: (secondary: BSHRGB, muted: BSHRGB, subtle: BSHRGB) {
        switch (desk, dark) {
        case (.onyx, false): return (BSHRGB(63, 63, 62), BSHRGB(96, 95, 94), BSHRGB(142, 142, 140))
        case (.onyx, true): return (BSHRGB(192, 190, 184), BSHRGB(149, 147, 143), BSHRGB(107, 106, 103))
        case (.green, false): return (BSHRGB(62, 70, 65), BSHRGB(96, 102, 95), BSHRGB(146, 148, 138))
        case (.green, true): return (BSHRGB(194, 190, 176), BSHRGB(148, 148, 136), BSHRGB(106, 110, 101))
        case (.maroon, false): return (BSHRGB(72, 64, 63), BSHRGB(104, 97, 95), BSHRGB(150, 144, 140))
        case (.maroon, true): return (BSHRGB(196, 189, 178), BSHRGB(154, 145, 138), BSHRGB(115, 103, 100))
        case (.navy, false): return (BSHRGB(63, 66, 72), BSHRGB(96, 99, 102), BSHRGB(145, 145, 145))
        case (.navy, true): return (BSHRGB(193, 190, 180), BSHRGB(148, 147, 142), BSHRGB(106, 107, 107))
        case (.aubergine, false): return (BSHRGB(69, 64, 67), BSHRGB(102, 97, 98), BSHRGB(148, 144, 142))
        case (.aubergine, true): return (BSHRGB(195, 190, 179), BSHRGB(152, 146, 140), BSHRGB(112, 105, 104))
        case (.tobacco, false): return (BSHRGB(71, 66, 61), BSHRGB(103, 99, 93), BSHRGB(149, 145, 139))
        case (.tobacco, true): return (BSHRGB(196, 191, 178), BSHRGB(154, 148, 137), BSHRGB(114, 108, 99))
        case (.graphite, false): return (BSHRGB(65, 67, 69), BSHRGB(98, 99, 99), BSHRGB(146, 146, 143))
        case (.graphite, true): return (BSHRGB(194, 191, 180), BSHRGB(150, 149, 142), BSHRGB(109, 108, 106))
        }
    }
    var secondary: Color { .bshFixed(ladder.secondary) }
    var muted: Color { .bshFixed(ladder.muted) }
    var subtle: Color { .bshFixed(ladder.subtle) }

    // Brass, and the other tones (the same on every desk).
    var accent: Color { .bshFixed(dark ? BSHRGB(158, 120, 52) : BSHRGB(148, 112, 47)) }
    var accentHover: Color { .bshFixed(dark ? BSHRGB(178, 138, 66) : BSHRGB(128, 95, 36)) }
    var accentSoft: Color { .bshFixed(dark ? BSHRGB(46, 40, 24) : BSHRGB(242, 233, 212)) }
    var accentInk: Color { .bshFixed(dark ? BSHRGB(222, 189, 122) : BSHRGB(122, 90, 31)) }
    var accentGlowRGB: BSHRGB { dark ? BSHRGB(214, 178, 104) : BSHRGB(208, 172, 100) }
    func accentGlow(_ opacity: Double) -> Color { .bshFixed(accentGlowRGB, opacity: opacity) }
    var success: Color { .bshFixed(dark ? BSHRGB(76, 180, 118) : BSHRGB(31, 128, 80)) }
    var successInk: Color { .bshFixed(dark ? BSHRGB(132, 214, 162) : BSHRGB(22, 104, 63)) }
    var successSoft: Color { .bshFixed(dark ? BSHRGB(20, 44, 31) : BSHRGB(223, 237, 226)) }
    var danger: Color { .bshFixed(dark ? BSHRGB(232, 100, 82) : BSHRGB(192, 57, 43)) }
    var dangerInk: Color { .bshFixed(dark ? BSHRGB(248, 166, 152) : BSHRGB(162, 42, 30)) }
    var dangerSoft: Color { .bshFixed(dark ? BSHRGB(58, 26, 21) : BSHRGB(246, 225, 219)) }
    var warning: Color { .bshFixed(dark ? BSHRGB(232, 158, 60) : BSHRGB(196, 118, 18)) }
    var warningInk: Color { .bshFixed(dark ? BSHRGB(244, 200, 138) : BSHRGB(150, 84, 6)) }
    var info: Color { .bshFixed(dark ? BSHRGB(140, 152, 240) : BSHRGB(70, 88, 170)) }
    var notice: Color { .bshFixed(dark ? BSHRGB(232, 196, 72) : BSHRGB(204, 160, 20)) }
    var purpleInk: Color { .bshFixed(dark ? BSHRGB(218, 186, 250) : BSHRGB(100, 56, 146)) }
    var purpleSoft: Color { .bshFixed(dark ? BSHRGB(46, 30, 60) : BSHRGB(237, 229, 243)) }

    /// `--bureau-shadow`: what the desk tints a shadow with.
    var shadowRGB: BSHRGB {
        switch desk {
        case .onyx: return dark ? BSHRGB(0, 0, 0) : BSHRGB(20, 20, 20)
        case .green: return BSHRGB(15, 31, 26)
        case .maroon: return dark ? BSHRGB(12, 3, 5) : BSHRGB(40, 9, 15)
        case .navy: return dark ? BSHRGB(2, 4, 9) : BSHRGB(10, 17, 32)
        case .aubergine: return dark ? BSHRGB(5, 2, 5) : BSHRGB(28, 12, 27)
        case .tobacco: return dark ? BSHRGB(5, 3, 2) : BSHRGB(32, 20, 10)
        case .graphite: return dark ? BSHRGB(3, 4, 5) : BSHRGB(16, 19, 24)
        }
    }
    func shadow(_ opacity: Double) -> Color { .bshFixed(shadowRGB, opacity: opacity) }

    /// A switch that is on (`--bureau-switch`): the desk's own color by day, brass by night.
    var switchOn: Color {
        if dark { return accent }
        switch desk {
        case .onyx: return .bshFixed(BSHRGB(24, 24, 24))
        case .green: return .bshFixed(BSHRGB(26, 62, 51))
        case .maroon: return .bshFixed(BSHRGB(104, 26, 40))
        case .navy: return .bshFixed(BSHRGB(30, 50, 90))
        case .aubergine: return .bshFixed(BSHRGB(74, 36, 70))
        case .tobacco: return .bshFixed(BSHRGB(84, 54, 30))
        case .graphite: return .bshFixed(BSHRGB(50, 56, 66))
        }
    }
}

extension View {
    /// The page's colors for the window's appearance.
    func withBureauPageInk<Content: View>(@ViewBuilder _ content: @escaping (MacBureauPageInk) -> Content) -> some View {
        MacBureauPageInkReader(content: content)
    }
}

private struct MacBureauPageInkReader<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    let content: (MacBureauPageInk) -> Content
    var body: some View { content(MacBureauPageInk(scheme: colorScheme)) }
}

// MARK: - Text

extension View {
    /// Sets text as the browser does with a `line-height`: lines `lineHeight` apart, each
    /// baseline where Blink puts it in its line box, the box `lineHeight` a line.
    /// `em` is the face's ascent plus descent: 1.22 for Instrument Sans, 1.30 for the serif.
    func bureauLines(_ lineHeight: CGFloat, size: CGFloat, em: CGFloat = 1.22) -> some View {
        let face = BureauLineMetrics(size: size, lineHeight: lineHeight, serif: em > 1.26)
        let top = face.webBaseline - face.laidAscent
        return self.lineSpacing(max(0, lineHeight - face.laidLine))
            .padding(.top, top)
            .padding(.bottom, lineHeight - top - face.laidLine)
    }
}

/// How the browser and SwiftUI each set a line of Instrument. Blink rounds the face's ascent
/// and descent to whole points and floors the half-leading: the baseline sits at
/// `A + ⌊(L − A − D) / 2⌋`. SwiftUI rounds the size to a point, then the ascent and the
/// descent, and puts the first baseline at the rounded ascent (12pt Instrument Sans on a
/// 16pt line: the browser's baseline 12pt down, SwiftUI's line 15pt with its baseline at 12).
private struct BureauLineMetrics {
    let webBaseline: CGFloat
    let laidAscent: CGFloat
    let laidLine: CGFloat

    init(size: CGFloat, lineHeight: CGFloat, serif: Bool) {
        // Per em, from the fonts' hhea tables.
        let a: CGFloat = serif ? 0.990005 : 0.970001
        let d: CGFloat = serif ? 0.309998 : 0.25
        let webAscent = (size * a).rounded()
        let webDescent = (size * d).rounded()
        webBaseline = webAscent + ((lineHeight - webAscent - webDescent) / 2).rounded(.down)
        let laid = size.rounded()
        laidAscent = (laid * a).rounded()
        laidLine = laidAscent + (laid * d).rounded()
    }
}

/// `.page-header`: the desk's title in Instrument Serif (46pt), a line under it, and its
/// actions to the right, level with the title's foot.
struct MacBureauPageHeader<Actions: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var actions: () -> Actions

    init(_ title: String, subtitle: String? = nil, @ViewBuilder actions: @escaping () -> Actions) {
        self.title = title
        self.subtitle = subtitle
        self.actions = actions
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(alignment: .bottom, spacing: 24) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.custom(BSHType.bureauSerif, size: 46))
                    .tracking(-0.552)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .fixedSize()
                    .frame(height: 48)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(BSHType.bureauSans(14))
                        .tracking(-0.084)
                        .foregroundStyle(ink.muted)
                        .bureauLines(20, size: 14)
                        .frame(maxWidth: 672, alignment: .leading)
                }
            }
            Spacer(minLength: 0)
            HStack(spacing: 8) { actions() }
        }
    }
}

extension MacBureauPageHeader where Actions == EmptyView {
    init(_ title: String, subtitle: String? = nil) {
        self.init(title, subtitle: subtitle) { EmptyView() }
    }
}

/// A tray's heading: an optional glyph in brass, then the title in Instrument Serif (23pt).
struct MacBureauTrayTitle: View {
    @Environment(\.colorScheme) private var colorScheme
    let title: String
    var icon: String? = nil

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 8) {
            if let icon {
                LucideIcon(icon, size: 16).foregroundStyle(ink.accent)
            }
            Text(title)
                .font(.custom(BSHType.bureauSerif, size: 23))
                .tracking(-0.23)
                .foregroundStyle(ink.ink)
                .fixedSize()
                .frame(height: 28)
        }
    }
}

/// `.vogue-label`: a section label, an italic serif kicker in sentence case.
struct MacBureauKicker: View {
    @Environment(\.colorScheme) private var colorScheme
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.custom(BSHType.bureauSerifItalic, size: 15.5))
            .foregroundStyle(MacBureauPageInk(scheme: colorScheme).secondary)
            .fixedSize()
            .bureauLines(20, size: 15.5, em: 1.30)
    }
}

// MARK: - Surfaces

/// `.group-card` / `.glass-card`: a tray pressed into the sheet (14pt corners, a faint
/// edge of the page's ink).
struct MacBureauTray: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    var padding: CGFloat = 20
    var radius: CGFloat = 14
    var highlighted = false

    func body(content: Content) -> some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: radius, style: .circular).fill(ink.tray))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .circular)
                    .strokeBorder(highlighted ? ink.accent.opacity(0.38) : ink.ink(0.035), lineWidth: 1)
            )
    }
}

extension View {
    func bureauTray(padding: CGFloat = 20, radius: CGFloat = 14, highlighted: Bool = false) -> some View {
        modifier(MacBureauTray(padding: padding, radius: radius, highlighted: highlighted))
    }
}

/// `.rounded-row`: a label and its value on a band of the sheet's fill.
struct MacBureauRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let label: String
    let value: String
    var valueTone: Color? = nil

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 12) {
            Text(label)
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .layoutPriority(1)
            Spacer(minLength: 0)
            Text(value)
                .fontWeight(.semibold)
                .foregroundStyle(valueTone ?? ink.ink)
                .lineLimit(1)
                .truncationMode(.tail)
        }
        .font(BSHType.bureauSans(14))
        .tracking(-0.084)
        .padding(.horizontal, 12)
        .frame(height: 36)
        .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(ink.fillTertiary))
    }
}

/// `.chip`: a small pill of text.
struct MacBureauChip: View {
    @Environment(\.colorScheme) private var colorScheme
    let text: String
    var foreground: Color? = nil
    var background: Color? = nil

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Text(text)
            .font(BSHType.bureauSans(11, weight: .semibold))
            .foregroundStyle(foreground ?? ink.secondary)
            .padding(.horizontal, 8)
            .frame(height: 18)
            .background(Capsule().fill(background ?? ink.fillSecondary))
    }
}

// MARK: - Controls

/// `.segmented`: a groove in the sheet; the chosen segment is a slip of fresh paper lifted
/// from it, its label in ink.
struct MacBureauSegmented<Value: Hashable>: View {
    @Environment(\.colorScheme) private var colorScheme
    let options: [(value: Value, title: String, icon: String?)]
    @Binding var selection: Value
    var disabled = false
    @Namespace private var slip
    @State private var hovered: Value?

    init(_ options: [(value: Value, title: String, icon: String?)], selection: Binding<Value>, disabled: Bool = false) {
        self.options = options
        self._selection = selection
        self.disabled = disabled
    }

    init(_ options: [(Value, String)], selection: Binding<Value>, disabled: Bool = false, fill: Bool = false) {
        self.options = options.map { (value: $0.0, title: $0.1, icon: nil) }
        self._selection = selection
        self.disabled = disabled
        self.fill = fill
    }

    /// Stretch across the width it is offered, the segments sharing it equally.
    var fill = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 2) {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                let chosen = option.value == selection
                Button {
                    guard !chosen else { return }
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.82)) { selection = option.value }
                } label: {
                    HStack(spacing: 4) {
                        if let icon = option.icon { LucideIcon(icon, size: 14) }
                        Text(option.title)
                            .font(BSHType.bureauSans(12, weight: chosen ? .semibold : .medium))
                            .fixedSize()
                            .bureauLines(16, size: 12)
                    }
                    .foregroundStyle(chosen || hovered == option.value ? ink.ink : ink.ink(0.62))
                    .padding(.horizontal, 12)
                    .frame(maxWidth: fill ? .infinity : nil)
                    .frame(height: 22)
                    .background {
                        if chosen {
                            Capsule()
                                .fill(ink.raised)
                                .overlay(Capsule().inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
                                .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                                .matchedGeometryEffect(id: "slip", in: slip)
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .onHover { inside in
                    if inside { hovered = option.value } else if hovered == option.value { hovered = nil }
                }
                .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
        .padding(3)
        // The groove, pressed in: a shade of ink with a soft shadow under its top edge.
        .background {
            Capsule()
                .fill(ink.ink(0.06))
                .overlay(MacBureauInsetShadow(color: ink.shadow(0.06), blur: 2, y: 1, shape: Capsule()))
        }
        .fixedSize(horizontal: !fill, vertical: true)
        .disabled(disabled)
    }
}

/// CSS's `box-shadow: inset 0 <y>px <blur>px <color>`: everything outside the shape, moved
/// down by `y`, blurred, and seen only inside it. (An inner shadow on a translucent fill
/// would be only as strong as the fill.)
struct MacBureauInsetShadow<S: Shape>: View {
    let color: Color
    var blur: CGFloat = 2
    var y: CGFloat = 1
    let shape: S

    var body: some View {
        GeometryReader { geo in
            let rect = CGRect(origin: .zero, size: geo.size)
            Path { path in
                path.addRect(rect.insetBy(dx: -4 * blur - 4, dy: -4 * blur - 4))
                path.addPath(shape.path(in: rect))
            }
            .fill(color, style: FillStyle(eoFill: true))
            .offset(y: y)
            // A CSS blur of b spreads a Gaussian of b / 2.
            .blur(radius: blur / 2)
        }
        .mask(shape)
        .allowsHitTesting(false)
    }
}

/// `.switch`: 38 by 22; on, it takes the desk's color by day and brass by night.
struct MacBureauSwitch: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var isOn: Bool
    var disabled = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button {
            withAnimation(.spring(response: 0.32, dampingFraction: 0.72)) { isOn.toggle() }
        } label: {
            ZStack(alignment: isOn ? .trailing : .leading) {
                Capsule()
                    .fill(isOn ? ink.switchOn : (ink.dark ? Color.white.opacity(0.18) : ink.ink(0.16)))
                    .overlay(Capsule().strokeBorder(ink.ink(0.08), lineWidth: 0.5))
                Circle()
                    .fill(Color.bshFixed(BSHRGB(255, 253, 248)))
                    .frame(width: 18, height: 18)
                    .shadow(color: .black.opacity(0.22), radius: 1, y: 1)
                    .overlay(Circle().strokeBorder(Color.black.opacity(0.06), lineWidth: 0.5))
                    .padding(2)
            }
            .frame(width: 38, height: 22)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.5 : 1)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(isOn ? "On" : "Off")
    }
}

/// The website's buttons: pills. Bordered is ruled in ink; filled is brass with light
/// across its top, and presses in rather than shrinking.
struct MacBureauButton: View {
    enum Kind { case bordered, filled, plain }
    enum Size { case regular, small }

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    let title: String
    var icon: String? = nil
    var kind: Kind = .bordered
    var size: Size = .regular
    var busy = false
    let action: () -> Void
    @State private var hovered = false
    @State private var pressed = false

    init(_ title: String, icon: String? = nil, kind: Kind = .bordered, size: Size = .regular, busy: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.kind = kind
        self.size = size
        self.busy = busy
        self.action = action
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let small = size == .small
        Button(action: action) {
            HStack(spacing: small ? 4.8 : 6) {
                if busy {
                    ProgressView().controlSize(.mini)
                } else if let icon {
                    LucideIcon(icon, size: small ? 14 : 16)
                }
                Text(title)
                    .font(BSHType.bureauSans(small ? 12 : 13, weight: .medium))
                    .tracking(small ? -0.072 : -0.078)
                    .fixedSize()
                    .bureauLines(small ? 18 : 20, size: small ? 12 : 13)
                    .underline(kind == .plain && hovered)
            }
            .foregroundStyle(foreground(ink))
            .padding(.horizontal, small ? 11.2 : 14)
            .frame(height: small ? 26 : 32)
            .background { background(ink) }
            .contentShape(Capsule())
            .offset(y: pressed ? 0.5 : 0)
        }
        .buttonStyle(MacBureauPressReporter(pressed: $pressed))
        .onHover { hovered = $0 }
        .opacity(isEnabled ? 1 : 0.4)
    }

    private func foreground(_ ink: MacBureauPageInk) -> Color {
        switch kind {
        case .filled: return .bshFixed(BSHRGB(255, 253, 246))
        case .bordered: return ink.ink
        case .plain: return ink.accentInk
        }
    }

    @ViewBuilder
    private func background(_ ink: MacBureauPageInk) -> some View {
        switch kind {
        case .filled:
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
        case .bordered:
            Capsule()
                .fill(hovered && isEnabled ? ink.ink(0.05) : .clear)
                .overlay(Capsule().strokeBorder(ink.ink(hovered && isEnabled ? 0.36 : 0.2), lineWidth: 1))
        case .plain:
            Color.clear
        }
    }
}

/// Reports whether a button is held down, so it can press in by half a point.
struct MacBureauPressReporter: ButtonStyle {
    @Binding var pressed: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .onChange(of: configuration.isPressed) { _, isPressed in pressed = isPressed }
    }
}

/// `.field`: fresh paper on the sheet, ruled in ink; focused, a brass edge and its glow.
struct MacBureauField: View {
    @Environment(\.colorScheme) private var colorScheme
    let placeholder: String
    @Binding var text: String
    var size: CGFloat = 13
    var height: CGFloat = 32
    var alignment: TextAlignment = .leading
    var secure = false
    var onSubmit: () -> Void = {}
    @FocusState private var focused: Bool

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Group {
            if secure {
                SecureField("", text: $text, prompt: Text(placeholder).foregroundStyle(ink.subtle))
            } else {
                TextField("", text: $text, prompt: Text(placeholder).foregroundStyle(ink.subtle))
            }
        }
        .textFieldStyle(.plain)
        .font(BSHType.bureauSans(size))
        .foregroundStyle(ink.ink)
        .multilineTextAlignment(alignment)
        .focused($focused)
        .onSubmit(onSubmit)
        .padding(.horizontal, 10)
        .frame(height: height)
        .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(ink.raised))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .circular)
                .strokeBorder(focused ? ink.accent : ink.ink(0.14), lineWidth: 1)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .circular)
                .inset(by: -2)
                .stroke(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                .padding(-0.5)
                .allowsHitTesting(false)
        )
    }
}

// MARK: - The Mac's own controls, drawn as the website's under Bureau

/// `.buttonStyle(.dsBordered)`: the Mac's bordered button, or under Bureau the website's
/// pill ruled in ink (`.btn-bordered`).
struct DSBorderedButtonStyle: PrimitiveButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        if BSHDesign.active == .bureau {
            Button(configuration).buttonStyle(MacBureauPillStyle(kind: .bordered))
        } else {
            Button(configuration).buttonStyle(.bordered)
        }
    }
}

/// `.buttonStyle(.dsProminent)`: the Mac's prominent button, or under Bureau the website's
/// brass pill (`.btn-filled`).
struct DSProminentButtonStyle: PrimitiveButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        if BSHDesign.active == .bureau {
            Button(configuration).buttonStyle(MacBureauPillStyle(kind: .filled))
        } else {
            Button(configuration).buttonStyle(.borderedProminent)
        }
    }
}

extension PrimitiveButtonStyle where Self == DSBorderedButtonStyle {
    static var dsBordered: DSBorderedButtonStyle { DSBorderedButtonStyle() }
}

extension PrimitiveButtonStyle where Self == DSProminentButtonStyle {
    static var dsProminent: DSProminentButtonStyle { DSProminentButtonStyle() }
}

/// The website's pill as a button style, sized by the control size: regular 32pt,
/// small 26pt, mini 20pt. A destructive button is drawn in the danger ink.
struct MacBureauPillStyle: ButtonStyle {
    let kind: MacBureauButton.Kind

    func makeBody(configuration: Configuration) -> some View {
        MacBureauPillBody(configuration: configuration, kind: kind)
    }
}

private struct MacBureauPillBody: View {
    let configuration: ButtonStyleConfiguration
    let kind: MacBureauButton.Kind
    @Environment(\.controlSize) private var controlSize
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    /// `line` is the website's line box (`.btn-sm` 18, `.btn-*` 20); mini and large have
    /// no website twin and keep the face's own line.
    private var metrics: (height: CGFloat, font: CGFloat, line: CGFloat, padding: CGFloat, tracking: CGFloat) {
        switch controlSize {
        case .mini: return (20, 11, 14, 8, 0)
        case .small: return (26, 12, 18, 11.2, -0.072)
        case .large, .extraLarge: return (36, 14, 18, 16, -0.084)
        default: return (32, 13, 20, 14, -0.078)
        }
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let m = metrics
        let destructive = configuration.role == .destructive
        configuration.label
            .font(BSHType.bureauSans(m.font, weight: .medium))
            .tracking(m.tracking)
            .lineLimit(1)
            .bureauLines(m.line, size: m.font)
            .foregroundStyle(foreground(ink, destructive: destructive))
            .padding(.horizontal, m.padding)
            .frame(minHeight: m.height)
            .background { background(ink, destructive: destructive) }
            .contentShape(Capsule())
            .offset(y: configuration.isPressed ? 0.5 : 0)
            .opacity(isEnabled ? 1 : 0.4)
            .onHover { hovered = $0 }
    }

    private func foreground(_ ink: MacBureauPageInk, destructive: Bool) -> Color {
        switch kind {
        case .filled: return .bshFixed(BSHRGB(255, 253, 246))
        case .bordered: return destructive ? ink.dangerInk : ink.ink
        case .plain: return ink.accentInk
        }
    }

    @ViewBuilder
    private func background(_ ink: MacBureauPageInk, destructive: Bool) -> some View {
        switch kind {
        case .filled:
            let metal = destructive ? ink.danger : (hovered && isEnabled ? ink.accentHover : ink.accent)
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
                .background(Capsule().inset(by: -0.5).stroke((destructive ? ink.danger : ink.accentHover).opacity(0.55), lineWidth: 1))
                .shadow(color: ink.shadow(0.18), radius: 1, y: 1)
        case .bordered:
            Capsule()
                .fill(hovered && isEnabled ? ink.ink(0.05) : .clear)
                .overlay(Capsule().strokeBorder(destructive ? ink.danger.opacity(0.5) : ink.ink(hovered && isEnabled ? 0.36 : 0.2), lineWidth: 1))
        case .plain:
            Color.clear
        }
    }
}

/// `.textFieldStyle(.dsField)`: the Mac's rounded field, or under Bureau the website's
/// `.field` (fresh paper ruled in ink; focused, a brass edge and its glow).
struct DSFieldStyle: TextFieldStyle {
    @ViewBuilder
    // swiftlint:disable:next identifier_name
    func _body(configuration: TextField<Self._Label>) -> some View {
        if BSHDesign.active == .bureau {
            MacBureauFieldFrame { configuration.textFieldStyle(.plain) }
        } else {
            configuration.textFieldStyle(.roundedBorder)
        }
    }
}

extension TextFieldStyle where Self == DSFieldStyle {
    static var dsField: DSFieldStyle { DSFieldStyle() }
}

private struct MacBureauFieldFrame<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.controlSize) private var controlSize
    @ViewBuilder var content: () -> Content
    @FocusState private var focused: Bool

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let small = controlSize == .small || controlSize == .mini
        content()
            .font(BSHType.bureauSans(small ? 12 : 13))
            .foregroundStyle(ink.ink)
            .focused($focused)
            .padding(.horizontal, 10)
            .frame(minHeight: small ? 28 : 32)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(ink.raised))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .circular)
                    .strokeBorder(focused ? ink.accent : ink.ink(0.14), lineWidth: 1)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .circular)
                    .inset(by: -2)
                    .stroke(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                    .padding(-0.5)
                    .allowsHitTesting(false)
            )
    }
}

/// `.icon-btn`: a round 32pt button's face, its glyph in half the ink; lit on hover.
struct MacBureauIconCircle: View {
    @Environment(\.colorScheme) private var colorScheme
    let icon: String
    var size: CGFloat = 16
    var isLit = false
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        LucideIcon(icon, size: size)
            .foregroundStyle(isLit || hovered ? ink.ink : ink.ink(0.5))
            .frame(width: 32, height: 32)
            .background(Circle().fill(isLit ? ink.ink(0.08) : (hovered ? ink.ink(0.07) : .clear)))
            .contentShape(Circle())
            .onHover { hovered = $0 }
    }
}
