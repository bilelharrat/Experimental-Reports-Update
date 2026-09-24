import SwiftUI

// One calm surface system for every desk: cards on the window canvas, a hairline
// instead of shadows, numbers in tabular figures. The colors and title faces follow the
// chosen design (BSHDesign: Bureau, Folio or Summit Glass); sizes and anatomy don't.

enum MacDS {
    static let page: CGFloat = 20
    static let card: CGFloat = 16
    static let gap: CGFloat = 12
    static let section: CGFloat = 20
    static let tileRadius: CGFloat = 8

    /// Bureau's trays are the website's (14pt), Folio's cards are cut, Summit's are the
    /// Mac's own.
    static var cardRadius: CGFloat {
        switch BSHDesign.active {
        case .bureau: return 14
        case .folio: return 6
        case .glass: return 12
        }
    }
}

extension Color {
    static var dsCanvas: Color { BSHPalette.canvas }
    static var dsCard: Color { BSHPalette.card }
    static var dsRaised: Color { BSHPalette.raised }
    static var dsTile: Color { BSHPalette.tile }
    static var dsHairline: Color { BSHPalette.hairline }
    static var dsPositive: Color { BSHPalette.positive }
    static var dsNegative: Color { BSHPalette.negative }
    static var dsWarning: Color { BSHPalette.warning }
    /// The design's color for acting. Use it wherever the app used `Color.accentColor`.
    static var dsAccent: Color { BSHPalette.accent }
    /// The page's ink (the system's label color under Summit Glass).
    static var dsInk: Color { BSHPalette.ink ?? .primary }
}

extension ShapeStyle where Self == Color {
    static var dsAccent: Color { BSHPalette.accent }
}

extension Font {
    static var dsTitle: Font { BSHType.title(22) }
    /// A card's heading. Bureau sets it as the website sets `.text-headline`: the
    /// interface face, semibold; only titles are in the serif.
    static var dsHeadline: Font {
        BSHDesign.active == .bureau ? BSHType.bureauSans(15, weight: .semibold) : BSHType.heading(15)
    }
    static var dsSubhead: Font { .ui(size: 13, weight: .medium) }
    static var dsBody: Font { .ui(size: 13) }
    static var dsLabel: Font { .ui(size: 11, weight: .medium) }
    static var dsCaption: Font { .ui(size: 11) }
    static var dsMetric: Font { .ui(size: 20, weight: .semibold).monospacedDigit() }
    static var dsMetricSmall: Font { .ui(size: 15, weight: .semibold).monospacedDigit() }

    /// The interface face at a size: Instrument Sans under Bureau, as the website sets its
    /// interface, and the system face otherwise. Serif and monospaced type stay the
    /// system's, as the website's `font-serif` and `font-mono` do.
    static func ui(size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> Font {
        guard BSHDesign.active == .bureau, design != .monospaced, design != .serif else {
            return .system(size: size, weight: weight, design: design)
        }
        return BSHType.bureauSans(size, weight: weight)
    }

    /// The interface face at one of the Mac's text styles, at the style's size.
    static func ui(_ style: Font.TextStyle, design: Font.Design = .default) -> Font {
        guard BSHDesign.active == .bureau, design != .monospaced, design != .serif else {
            return .system(style, design: design)
        }
        let (size, weight) = MacDS.metrics(of: style)
        return BSHType.bureauSans(size, weight: weight)
    }
}

extension MacDS {
    /// The Mac's text styles (NSFont.preferredFont), for setting them in another face.
    /// The headline, bold in the system face, is semibold in Bureau's, as on the website.
    static func metrics(of style: Font.TextStyle) -> (CGFloat, Font.Weight) {
        switch style {
        case .largeTitle: return (26, .regular)
        case .title: return (22, .regular)
        case .title2: return (17, .regular)
        case .title3: return (15, .regular)
        case .headline: return (13, .semibold)
        case .subheadline: return (11, .regular)
        case .body: return (13, .regular)
        case .callout: return (12, .regular)
        case .footnote, .caption, .caption2: return (10, .regular)
        @unknown default: return (13, .regular)
        }
    }
}

// MARK: - Card anatomy

/// Title row every card starts with: optional symbol, title, one-line subtitle, trailing controls.
struct MacCardHeader<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    var systemImage: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    init(_ title: String, subtitle: String? = nil, systemImage: String? = nil, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = trailing
    }

    var body: some View {
        if BSHDesign.active == .bureau {
            bureauBody
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                if let systemImage {
                    Image(systemName: systemImage)
                        .font(.ui(size: 13, weight: .semibold))
                        .foregroundStyle(Color.dsAccent)
                        .frame(width: 18)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.dsHeadline)
                    if let subtitle, !subtitle.isEmpty {
                        Text(subtitle).font(.dsCaption).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 8)
                trailing()
            }
        }
    }

    /// The website's card heading (`.text-headline`, 15pt semibold, with a glyph in brass),
    /// its line under it in 12pt muted ink.
    private var bureauBody: some View {
        HStack(alignment: .center, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    if let systemImage {
                        Image(systemName: systemImage)
                            .font(.system(size: 12, weight: .regular))
                            .foregroundStyle(Color.dsAccent)
                            .frame(width: 16, height: 16)
                    }
                    Text(title)
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.15)
                        .lineLimit(1)
                        .frame(height: 20)
                }
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle).font(.ui(size: 12)).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            trailing()
        }
    }
}

extension MacCardHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil, systemImage: String? = nil) {
        self.init(title, subtitle: subtitle, systemImage: systemImage) { EmptyView() }
    }
}

/// Secondary label above a group of controls or rows: Bureau's italic serif kicker,
/// Folio's small tracked capitals, Summit's plain label.
struct MacSectionLabel: View {
    let text: String
    var trailing: String? = nil
    init(_ text: String, trailing: String? = nil) { self.text = text; self.trailing = trailing }
    var body: some View {
        HStack {
            if BSHDesign.active == .bureau {
                // The website's `.vogue-label`: italic serif at 15.5pt.
                MacBureauKicker(text)
            } else {
                Text(text)
                    .font(BSHType.kicker(11))
                    .tracking(BSHType.kickerIsCapitals ? 0.8 : 0)
                    .textCase(BSHType.kickerIsCapitals ? .uppercase : nil)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let trailing { Text(trailing).font(.dsCaption.monospacedDigit()).foregroundStyle(.tertiary) }
        }
    }
}

/// Label / value / detail metric, e.g. "Post-money · $75.0M · Pre + check".
struct MacStatTile: View {
    let label: String
    let value: String
    var detail: String? = nil
    var tone: Color? = nil
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.dsLabel).foregroundStyle(.secondary).lineLimit(1)
            Text(value)
                .font(compact ? .dsMetricSmall : .dsMetric)
                .foregroundStyle(tone ?? .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            if let detail, !detail.isEmpty {
                Text(detail).font(.dsCaption).foregroundStyle(.tertiary).lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(compact ? 10 : 12)
        .appleGlassTile()
    }
}

/// Large title at the top of a desk.
struct MacDeskHeader<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    init(_ title: String, subtitle: String? = nil, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    var body: some View {
        if BSHDesign.active == .bureau {
            MacBureauPageHeader(title, subtitle: subtitle) { trailing() }
        } else {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.dsTitle)
                    if let subtitle, !subtitle.isEmpty {
                        Text(subtitle).font(.dsBody).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                trailing()
            }
        }
    }
}

extension MacDeskHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil) {
        self.init(title, subtitle: subtitle) { EmptyView() }
    }
}

/// Underline tabs (App Store style) for switching sections inside one desk.
struct MacTabBar<Item: Hashable>: View {
    let items: [(Item, String)]
    @Binding var selection: Item
    /// Bureau draws the website's `.mac-tabbar` two ways: inside the Research Desk (a
    /// `.mac-desk`) the idle tabs are muted over a hairline; elsewhere (Market) they're set
    /// in ink with no hairline. `plain` is the second.
    var plain = false
    @Namespace private var underline
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if BSHDesign.active == .bureau {
            bureauBody
        } else {
            nativeBody
        }
    }

    /// `.mac-tab`: 13pt on a 19.5pt line, 4pt above and 8pt below, 20pt apart; the chosen
    /// tab semibold over a 2pt brass rule at its foot.
    private var bureauBody: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        return VStack(spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .bottom, spacing: 20) {
                    ForEach(items, id: \.0) { item, label in
                        Button {
                            withAnimation(.snappy(duration: 0.22)) { selection = item }
                        } label: {
                            Text(label)
                                .font(BSHType.bureauSans(13, weight: selection == item ? .semibold : .regular))
                                .foregroundStyle(selection == item || plain ? ink.ink : ink.muted)
                                .lineLimit(1)
                                .fixedSize()
                                .bureauLines(19.5, size: 13)
                                .padding(.top, 4)
                                .padding(.bottom, 8)
                                .overlay(alignment: .bottom) {
                                    if selection == item {
                                        Rectangle()
                                            .fill(ink.accentGlow(1))
                                            .frame(height: 2)
                                            .matchedGeometryEffect(id: "underline", in: underline)
                                    }
                                }
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer(minLength: 0)
                }
            }
            if !plain {
                Rectangle().fill(ink.rule).frame(height: 1)
            }
        }
    }

    private var nativeBody: some View {
        ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 20) {
            ForEach(items, id: \.0) { item, label in
                Button {
                    withAnimation(.snappy(duration: 0.22)) { selection = item }
                } label: {
                    VStack(spacing: 6) {
                        Text(label)
                            .font(.ui(size: 13, weight: selection == item ? .semibold : (BSHDesign.active == .bureau ? .medium : .regular)))
                            .foregroundStyle(selection == item ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                            .lineLimit(1)
                            .fixedSize()
                        ZStack {
                            Rectangle().fill(Color.clear).frame(height: 2)
                            if selection == item {
                                Rectangle()
                                    .fill(Self.underlineColor)
                                    .frame(height: 2)
                                    .matchedGeometryEffect(id: "underline", in: underline)
                            }
                        }
                    }
                    .contentShape(Rectangle())
                }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                    }
                    }
                    .overlay(alignment: .bottom) { Rectangle().fill(Color.dsHairline).frame(height: 1) }
                }

    /// Folio underlines in ink, Bureau in brass (the website's accent glow), Summit in its blue.
    private static var underlineColor: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauBrass
        case .folio: return BSHPalette.folioInk
        case .glass: return .dsAccent
        }
    }
}

/// Rounded-square initials avatar used for companies everywhere.
struct MacAvatar: View {
    let name: String
    var ticker: String? = nil
    var companyId: String? = nil
    var logoUrl: String? = nil
    var website: String? = nil
    var size: CGFloat = 28
    var round: Bool = false

    init(
        name: String,
        ticker: String? = nil,
        companyId: String? = nil,
        logoUrl: String? = nil,
        website: String? = nil,
        size: CGFloat = 28,
        round: Bool = false
    ) {
        self.name = name
        self.ticker = ticker
        self.companyId = companyId
        self.logoUrl = logoUrl
        self.website = website
        self.size = size
        self.round = round
    }

    init(company: MacCompany, size: CGFloat = 28, round: Bool = false) {
        self.name = company.name ?? company.id
        self.ticker = company.ticker
        self.companyId = company.id
        self.logoUrl = company.logoUrl
        self.website = company.website
        self.size = size
        self.round = round
    }

    var body: some View {
        MacMonogram(
            name: name,
            ticker: ticker,
            companyId: companyId,
            logoUrl: logoUrl,
            website: website,
            size: size,
            round: round
        )
    }
}

/// Dot + text status, e.g. "● Synced 10:42 PM".
struct MacDot: View {
    let color: Color
    var body: some View { Circle().fill(color).frame(width: 6, height: 6) }
}

extension View {
    /// Standard content column for a scrolling desk. Under Bureau, the website's
    /// `.page-wide`: 32pt either side, 16pt above, 48pt below, the sheet's full width.
    @ViewBuilder
    func dsPage() -> some View {
        if BSHDesign.active == .bureau {
            self.padding(.horizontal, 32).padding(.top, 16).padding(.bottom, 48)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            self.padding(MacDS.page).frame(maxWidth: 1180, alignment: .leading).frame(maxWidth: .infinity, alignment: .center)
        }
    }

    /// Slim material toolbar strip at the top of a pane.
    @ViewBuilder
    func dsToolbarStrip() -> some View {
        if BSHDesign.active.isPaper {
            // On paper a strip is the page itself, ruled off below; nothing frosts.
            self.padding(.horizontal, 12).padding(.vertical, 7)
                .background(Color.dsCanvas)
                .overlay(alignment: .bottom) { Rectangle().fill(Color.dsHairline).frame(height: 1) }
        } else {
            self.padding(.horizontal, 12).padding(.vertical, 7).background(.bar)
        }
    }
}

enum MacNumber {
    static func compact(_ value: Double?, currency: Bool = true) -> String {
        guard let value else { return "—" }
        let sign = value < 0 ? "-" : ""
        let v = abs(value)
        let prefix = currency ? "$" : ""
        func fmt(_ x: Double, _ unit: String) -> String {
            let s = x >= 100 ? String(format: "%.0f", x) : (x >= 10 ? String(format: "%.1f", x) : String(format: "%.2f", x))
            return "\(sign)\(prefix)\(s)\(unit)"
        }
        if v >= 1e12 { return fmt(v / 1e12, "T") }
        if v >= 1e9 { return fmt(v / 1e9, "B") }
        if v >= 1e6 { return fmt(v / 1e6, "M") }
        if v >= 1e3 { return fmt(v / 1e3, "K") }
        return "\(sign)\(prefix)" + String(format: v == v.rounded() ? "%.0f" : "%.2f", v)
    }

    /// "4,849,208,188,600" → "$4.85T"; leaves non-numeric strings alone.
    static func compactString(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty else { return "—" }
        let cleaned = raw.replacingOccurrences(of: ",", with: "").replacingOccurrences(of: "$", with: "").trimmingCharacters(in: .whitespaces)
        guard let value = Double(cleaned), abs(value) >= 1_000_000 else { return raw }
        return compact(value)
    }
}
