import SwiftUI

/// Apple-Stocks-style percent-change capsule: white bold digits on a
/// green/red rounded rectangle, fixed width so columns of them align.
struct ChangeBadge: View {
    let value: Double?

    var body: some View {
        Text(QuoteRow.pct(value))
            .font(.subheadline.monospacedDigit().weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .frame(minWidth: 68, alignment: .trailing)
            .background(tone, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private var tone: Color {
        guard let value else { return Color(.systemGray3) }
        if value > 0 { return Color(.systemGreen) }
        if value < 0 { return Color(.systemRed) }
        return Color(.systemGray)
    }
}

/// Tinted capsule status chip ("Complete", "Running", "Failed"…).
struct StatusPill: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.16), in: Capsule())
            .lineLimit(1)
    }
}

/// Contacts-style monogram tile: company initials on a color derived
/// from the name, so each company keeps a stable hue.
struct MonogramAvatar: View {
    let name: String
    var size: CGFloat = 44

    private static let palette: [Color] = [
        .blue, .indigo, .purple, .pink, .red, .orange, .teal, .cyan, .mint, .green,
    ]

    var body: some View {
        let initials = name
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first.map(String.init) }
            .joined()
            .uppercased()
        let color = Self.palette[abs(name.hashValue) % Self.palette.count]
        Text(initials.isEmpty ? "?" : initials)
            .font(.system(size: size * 0.38, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(
                LinearGradient(
                    colors: [color, color.opacity(0.72)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: size * 0.24, style: .continuous)
            )
    }
}
