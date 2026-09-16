import SwiftUI

// One calm surface system for every desk: white cards on the window canvas, a hairline
// instead of shadows, SF Pro everywhere, numbers in tabular figures.

enum MacDS {
    static let page: CGFloat = 20
    static let card: CGFloat = 16
    static let gap: CGFloat = 12
    static let section: CGFloat = 20
    static let cardRadius: CGFloat = 12
    static let tileRadius: CGFloat = 8
}

#if os(macOS)
extension Color {
    static let dsCanvas = Color(nsColor: .windowBackgroundColor)
    static let dsCard = Color(nsColor: .controlBackgroundColor)
    static let dsTile = Color.primary.opacity(0.045)
    static let dsHairline = Color.primary.opacity(0.09)
    static let dsPositive = Color.green
    static let dsNegative = Color.red
    static let dsWarning = Color.orange
}
#else
extension Color {
    static let dsCanvas = Color(uiColor: .systemGroupedBackground)
    static let dsCard = Color(uiColor: .secondarySystemGroupedBackground)
    static let dsTile = Color.primary.opacity(0.045)
    static let dsHairline = Color.primary.opacity(0.09)
    static let dsPositive = Color.green
    static let dsNegative = Color.red
    static let dsWarning = Color.orange
}
#endif

extension Font {
    static let dsTitle = Font.system(size: 22, weight: .bold)
    static let dsHeadline = Font.system(size: 15, weight: .semibold)
    static let dsSubhead = Font.system(size: 13, weight: .medium)
    static let dsBody = Font.system(size: 13)
    static let dsLabel = Font.system(size: 11, weight: .medium)
    static let dsCaption = Font.system(size: 11)
    static let dsMetric = Font.system(size: 20, weight: .semibold).monospacedDigit()
    static let dsMetricSmall = Font.system(size: 15, weight: .semibold).monospacedDigit()
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
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color.accentColor)
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

extension MacCardHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil, systemImage: String? = nil) {
        self.init(title, subtitle: subtitle, systemImage: systemImage) { EmptyView() }
    }
}

/// Secondary label above a group of controls or rows.
struct MacSectionLabel: View {
    let text: String
    var trailing: String? = nil
    init(_ text: String, trailing: String? = nil) { self.text = text; self.trailing = trailing }
    var body: some View {
        HStack {
            Text(text).font(.dsLabel).foregroundStyle(.secondary)
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

extension MacDeskHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil) {
        self.init(title, subtitle: subtitle) { EmptyView() }
    }
}

/// Underline tabs (App Store style) for switching sections inside one desk.
struct MacTabBar<Item: Hashable>: View {
    let items: [(Item, String)]
    @Binding var selection: Item
    @Namespace private var underline

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 20) {
            ForEach(items, id: \.0) { item, label in
                Button {
                    withAnimation(.snappy(duration: 0.22)) { selection = item }
                } label: {
                    VStack(spacing: 6) {
                        Text(label)
                            .font(.system(size: 13, weight: selection == item ? .semibold : .regular))
                            .foregroundStyle(selection == item ? Color.primary : Color.secondary)
                            .lineLimit(1)
                            .fixedSize()
                        ZStack {
                            Rectangle().fill(Color.clear).frame(height: 2)
                            if selection == item {
                                Rectangle()
                                    .fill(Color.accentColor)
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
                    .overlay(alignment: .bottom) { Divider() }
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
    /// Standard content column for a scrolling desk.
    func dsPage() -> some View {
        self.padding(MacDS.page).frame(maxWidth: 1180, alignment: .leading).frame(maxWidth: .infinity, alignment: .center)
    }

    /// Slim material toolbar strip at the top of a pane.
    func dsToolbarStrip() -> some View {
        self.padding(.horizontal, 12).padding(.vertical, 7).background(.bar)
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
