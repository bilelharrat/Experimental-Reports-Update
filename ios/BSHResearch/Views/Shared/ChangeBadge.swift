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

/// Contacts-style monogram / brand logo tile.
/// Resolves high-resolution vector and Retina brand logos,
/// falling back to stable company monogram initials.
struct MonogramAvatar: View {
    let name: String
    var ticker: String? = nil
    var companyId: String? = nil
    var logoUrl: String? = nil
    var logoDomain: String? = nil
    var website: String? = nil
    var size: CGFloat = 44
    var round: Bool = false
    var showLogo: Bool = true

    init(
        name: String,
        ticker: String? = nil,
        companyId: String? = nil,
        logoUrl: String? = nil,
        logoDomain: String? = nil,
        website: String? = nil,
        size: CGFloat = 44,
        round: Bool = false,
        showLogo: Bool = true
    ) {
        self.name = name
        self.ticker = ticker
        self.companyId = companyId
        self.logoUrl = logoUrl
        self.logoDomain = logoDomain
        self.website = website
        self.size = size
        self.round = round
        self.showLogo = showLogo
    }

    init(company: Company, size: CGFloat = 44, round: Bool = false, showLogo: Bool = true) {
        self.name = company.name ?? company.id
        self.ticker = company.ticker
        self.companyId = company.id
        self.logoUrl = company.logoUrl
        self.logoDomain = company.logoDomain
        self.website = company.website
        self.size = size
        self.round = round
        self.showLogo = showLogo
    }

    var body: some View {
        MacMonogram(
            name: name,
            ticker: ticker,
            companyId: companyId,
            logoUrl: logoUrl,
            logoDomain: logoDomain,
            website: website,
            size: size,
            round: round,
            showLogo: showLogo
        )
    }
}
