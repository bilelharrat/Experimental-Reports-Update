//
//  MacBureauPulseNewsKit.swift
//  BSHResearchMac
//
//  What Bureau's Pulse and News desks share with the website's (MarketsView.vue,
//  WeeklySummaryView.vue, NewsDeskView.vue): the Market · Pulse · News sub-nav, the
//  grouped tray (`.news-grouped`), the small range pills (`.yf-range-item`), the type
//  steps they set their labels in, and the website's number formats.
//

import AppKit
import SwiftUI

// MARK: - The sub-nav

/// MarketsView.vue: Market, Pulse and News are one desk, so the three sit as underline tabs
/// (the Mac's MacTabBar, the website's `.mac-tabbar`) at the top of each, 24pt in from the
/// sheet's edge and 8pt down (`px-6 pt-2`), and scroll away with the page.
struct MacBureauPulseNewsSubNav: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        // Outside a `.mac-desk`: idle tabs in ink, no hairline under the bar.
        MacTabBar(
            items: [(MacTab.market, "Market"), (.pulse, "Pulse"), (.news, "News")],
            selection: $store.selectedTab,
            plain: true
        )
        .padding(.horizontal, 24)
        .padding(.top, 8)
    }
}

// MARK: - Surfaces

/// `.news-grouped` (and `.morning-brief`, `.news-lead`): a tray pressed into the sheet: the
/// surface color, a hairline of ink and a shadow cast inward from its top edge.
struct MacBureauPNTray: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    var radius: CGFloat = 14

    func body(content: Content) -> some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        content
            .background(shape.fill(ink.tray))
            // `inset 0 1px 2px` (by night `0 1px 3px`): the top edge pressed in.
            .overlay(MacBureauInsetShadow(
                color: ink.dark ? Color.black.opacity(0.35) : Color.bshFixed(BSHRGB(20, 20, 20), opacity: 0.04),
                blur: ink.dark ? 4.5 : 2,
                y: 1,
                shape: shape
            ))
            .overlay {
                shape
                    .strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.ink(0.035), lineWidth: 1)
                    .allowsHitTesting(false)
            }
    }
}

extension View {
    func pnTray(radius: CGFloat = 14) -> some View {
        modifier(MacBureauPNTray(radius: radius))
    }

    /// Sets text as CSS does with a `line-height` (as `bureauLines` does for Instrument):
    /// lines `lineHeight` apart, the first baseline where Blink puts it. A face taller than
    /// its line (a display headline) can't be drawn tighter with `lineSpacing`, so where the
    /// system can (macOS 26) its lines are set exactly `lineHeight` apart and the block is
    /// moved so its first baseline lands where Blink's does.
    @ViewBuilder
    func pnLines(_ lineHeight: CGFloat, size: CGFloat, face: MacBureauPNFace) -> some View {
        let m = face.metrics(size)
        // Blink: the ascent and descent rounded to points, the half-leading floored.
        let webAscent = m.ascent.rounded()
        let webBaseline = webAscent + ((lineHeight - webAscent - m.descent.rounded()) / 2).rounded(.down)
        let top = webBaseline - m.laidAscent
        if lineHeight >= m.laidLine {
            MacBureauPNLineBox(lineHeight: lineHeight) {
                self.lineSpacing(lineHeight - m.laidLine)
                    .padding(.top, top)
                    .padding(.bottom, lineHeight - top - m.laidLine)
            }
        } else if #available(macOS 26.0, *) {
            MacBureauPNLineBox(lineHeight: lineHeight) {
                self.lineHeight(.exact(points: lineHeight)).offset(y: webBaseline - face.exactAscent(size))
            }
        } else {
            self.padding(.top, top).padding(.bottom, lineHeight - top - m.laidLine)
        }
    }
}

/// A block of text exactly a whole number of CSS lines tall, as the browser makes it:
/// SwiftUI rounds a text's height up to the pixel, and gives a block set with an exact line
/// height a little more, which adds up down a long page.
private struct MacBureauPNLineBox: Layout {
    let lineHeight: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard let text = subviews.first else { return .zero }
        let size = text.sizeThatFits(proposal)
        let lines = max(1, (size.height / lineHeight).rounded())
        return CGSize(width: size.width, height: lines * lineHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, proposal: ProposedViewSize(width: bounds.width, height: nil))
    }
}

/// The faces the two desks set: their ascent and descent per point, and the line SwiftUI
/// lays them in (the size and each extent rounded to a whole point).
enum MacBureauPNFace {
    case sans, serif, reading, mono, system

    private var ratios: (ascent: CGFloat, descent: CGFloat) {
        switch self {
        case .sans: return (0.970001, 0.25)
        case .serif: return (0.990005, 0.309998)
        case .reading: return (1.036133, 0.329102)
        case .mono: return (0.928223, 0.235840)
        case .system: return (0.966797, 0.210938)
        }
    }

    func metrics(_ size: CGFloat) -> (ascent: CGFloat, descent: CGFloat, laidAscent: CGFloat, laidLine: CGFloat) {
        let r = ratios
        let laid = size.rounded()
        let laidAscent = (laid * r.ascent).rounded()
        return (size * r.ascent, size * r.descent, laidAscent, laidAscent + (laid * r.descent).rounded())
    }

    /// Where SwiftUI puts the first baseline of a block set with an exact line height
    /// (measured): at the rounded ascent for Instrument, and one em down for Iowan Old Style
    /// (a point above its ascent at display sizes).
    func exactAscent(_ size: CGFloat) -> CGFloat {
        self == .reading ? size.rounded() : metrics(size).laidAscent
    }

    /// The brief's reading face. The website asks for `ui-serif, "New York", "Iowan Old
    /// Style", …`; Chrome has neither of the first two, so it sets Iowan Old Style, the
    /// 600 weight as its Bold, and the Mac sets the same.
    static func reading(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let bold = weight == .semibold || weight == .bold || weight == .heavy || weight == .black
        return .custom(bold ? "IowanOldStyle-Bold" : "IowanOldStyle-Roman", fixedSize: size)
    }

    /// `font-mono`. The website asks for `ui-monospace, "SF Mono", SFMono-Regular, Menlo, …`;
    /// Chrome reaches Menlo, its semibold as Menlo Bold, and the Mac sets the same.
    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let bold = weight == .semibold || weight == .bold || weight == .heavy || weight == .black
        return .custom(bold ? "Menlo-Bold" : "Menlo-Regular", fixedSize: size)
    }
}

// MARK: - Labels

/// A tray's label (`text-footnote font-semibold text-ink-muted`).
struct MacBureauPNLabel: View {
    @Environment(\.colorScheme) private var colorScheme
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(BSHType.bureauSans(12, weight: .semibold))
            .foregroundStyle(MacBureauPageInk(scheme: colorScheme).muted)
            .lineLimit(1)
            .pnLines(16, size: 12, face: .sans)
    }
}

/// One line of interface text set in its CSS line box.
struct MacBureauPNLine: View {
    let text: String
    var size: CGFloat
    var weight: Font.Weight = .regular
    var tracking: CGFloat = 0
    var line: CGFloat
    var color: Color
    var tabular = false

    init(_ text: String, size: CGFloat, weight: Font.Weight = .regular, tracking: CGFloat = 0, line: CGFloat, color: Color, tabular: Bool = false) {
        self.text = text
        self.size = size
        self.weight = weight
        self.tracking = tracking
        self.line = line
        self.color = color
        self.tabular = tabular
    }

    var body: some View {
        Text(text)
            .font(tabular ? BSHType.bureauSans(size, weight: weight).monospacedDigit() : BSHType.bureauSans(size, weight: weight))
            .tracking(tracking)
            .foregroundStyle(color)
            .lineLimit(1)
            .pnLines(line, size: size, face: .sans)
    }
}

// MARK: - Range pills

/// `.yf-range-item`: a small pill of muted capitals-free text that inks on hover.
struct MacBureauPNRangeButton: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    let title: String
    var icon: String? = nil
    var selected = false
    var busy = false
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 4) {
                if busy {
                    ProgressView().controlSize(.mini).frame(width: 14, height: 14)
                } else if let icon {
                    LucideIcon(icon, size: 14)
                }
                Text(title)
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .tracking(0.066)
                    .fixedSize()
            }
            .foregroundStyle((hovered && isEnabled) || selected ? ink.ink : ink.muted)
            .padding(.horizontal, 10)
            .frame(height: 22)
            .background {
                if selected {
                    Capsule()
                        .fill(ink.raised)
                        .overlay(Capsule().inset(by: -0.5).stroke(ink.ink(0.1), lineWidth: 1))
                        .shadow(color: ink.shadow(0.12), radius: 1.5, y: 1)
                } else {
                    Capsule().fill(hovered && isEnabled ? ink.ink(0.05) : .clear)
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .opacity(isEnabled ? 1 : 0.5)
    }
}

/// `select.yf-range-item`: the pill as a pop-up menu, with the website's small up-down
/// chevron at its right.
struct MacBureauPNRangeMenu<Value: Hashable>: View {
    @Environment(\.colorScheme) private var colorScheme
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let current = options.first { $0.value == selection }?.title ?? ""
        Menu {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                Button {
                    selection = option.value
                } label: {
                    if option.value == selection {
                        Label(option.title, systemImage: "checkmark")
                    } else {
                        Text(option.title)
                    }
                }
            }
        } label: {
            Text(current)
                .font(BSHType.bureauSans(11, weight: .semibold))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .fixedSize()
                .padding(.leading, 10)
                .padding(.trailing, 24)
                .frame(height: 22)
                .overlay(alignment: .trailing) {
                    MacBureauPNSelectChevron()
                        .frame(width: 8, height: 11)
                        .padding(.trailing, 8)
                }
                .background(Capsule().fill(hovered ? ink.ink(0.05) : .clear))
                .contentShape(Capsule())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .onHover { hovered = $0 }
    }
}

/// The website's select chevron (style.css `select.yf-range-item`): two strokes in
/// #808086, 1.6 wide on a 10 by 14 box, drawn 8 by 11.
struct MacBureauPNSelectChevron: View {
    var body: some View {
        Canvas { context, size in
            let sx = size.width / 10
            let sy = size.height / 14
            var path = Path()
            path.move(to: CGPoint(x: 2 * sx, y: 5 * sy))
            path.addLine(to: CGPoint(x: 5 * sx, y: 2 * sy))
            path.addLine(to: CGPoint(x: 8 * sx, y: 5 * sy))
            path.move(to: CGPoint(x: 2 * sx, y: 9 * sy))
            path.addLine(to: CGPoint(x: 5 * sx, y: 12 * sy))
            path.addLine(to: CGPoint(x: 8 * sx, y: 9 * sy))
            context.stroke(
                path,
                with: .color(Color.bshFixed(BSHRGB(128, 128, 134))),
                style: StrokeStyle(lineWidth: 1.6 * (sx + sy) / 2, lineCap: .round, lineJoin: .round)
            )
        }
        .accessibilityHidden(true)
    }
}

/// A link set in brass ink (`text-accent-ink font-medium`), underlined on hover.
struct MacBureauPNLink: View {
    @Environment(\.colorScheme) private var colorScheme
    let title: String
    var size: CGFloat = 12
    var trailingIcon: String? = nil
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 0) {
                Text(title)
                    .font(BSHType.bureauSans(size, weight: .medium))
                    .tracking(size == 11 ? 0.066 : 0)
                    .underline(hovered)
                    .fixedSize()
                if let trailingIcon {
                    Spacer(minLength: 4)
                    LucideIcon(trailingIcon, size: 16)
                }
            }
            .foregroundStyle(ink.accentInk)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Numbers and dates, as the website writes them

enum MacBureauPNFormat {
    /// `fmtPct`: a sign on gains, one decimal under 10%, none above.
    static func pct(_ value: Double?) -> String {
        guard let n = value, n.isFinite else { return "n/a" }
        let digits = abs(n) >= 10 ? 0 : 1
        return "\(n > 0 ? "+" : "")\(String(format: "%.\(digits)f", n))%"
    }

    /// `signedChange`: a sign on gains, one decimal.
    static func signed(_ value: Double?) -> String? {
        guard let n = value, n.isFinite else { return nil }
        return "\(n > 0 ? "+" : "")\(String(format: "%.1f", n))%"
    }

    /// `lastPriceLabel`: dollars, grouped, up to two decimals.
    static func price(_ value: Double?) -> String? {
        guard let n = value, n.isFinite else { return nil }
        return "$" + (priceFormatter.string(from: NSNumber(value: n)) ?? String(format: "%.2f", n))
    }

    private static let priceFormatter: NumberFormatter = {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_US")
        f.numberStyle = .decimal
        f.minimumFractionDigits = 0
        f.maximumFractionDigits = 2
        return f
    }()

    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static func date(_ iso: String?) -> Date? {
        guard let raw = iso?.trimmingCharacters(in: .whitespaces), !raw.isEmpty else { return nil }
        if let d = isoFractional.date(from: raw) ?? isoPlain.date(from: raw) { return d }
        // A bare day reads as its midnight in UTC, as `Date.parse` reads it.
        if raw.count == 10, raw.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil {
            return isoPlain.date(from: raw + "T00:00:00Z")
        }
        // Microseconds and no zone ("2026-09-24T06:56:02.947482"): read as UTC.
        let trimmed = raw.replacingOccurrences(of: #"(\.\d{3})\d+"#, with: "$1", options: .regularExpression)
        if let d = isoFractional.date(from: trimmed) { return d }
        if let d = isoFractional.date(from: trimmed + "Z") ?? isoPlain.date(from: raw + "Z") { return d }
        return nil
    }

    /// `refreshedAtLabel`: "Sep 23, 11:56 PM".
    static func stamp(_ iso: String?) -> String? {
        guard let d = date(iso) else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: d)
    }

    /// A bare YYYY-MM-DD read as that day here, not shifted by UTC.
    static func day(_ ymd: String?) -> Date? {
        let parts = (ymd ?? "").prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return Calendar.current.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    /// "Thursday, September 24".
    static func longDay(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.dateFormat = "EEEE, MMMM d"
        return f.string(from: date)
    }

    /// `newsAgeParts` in words: "just now", "18m ago", "1h ago", "2d ago".
    static func age(_ iso: String?, now: Date = Date()) -> String? {
        guard let d = date(iso) else { return nil }
        let sec = max(0, (now.timeIntervalSince(d)).rounded())
        if sec < 60 { return "just now" }
        if sec < 3600 { return "\(Int((sec / 60).rounded()))m ago" }
        if sec < 86400 { return "\(Int((sec / 3600).rounded()))h ago" }
        return "\(Int((sec / 86400).rounded()))d ago"
    }
}
