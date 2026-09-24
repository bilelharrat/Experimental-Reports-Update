import SwiftUI

/// A company's mark under Bureau, as the website's `Monogram.vue` draws it: the logo inset
/// on a white tile with rounded corners of its own, or, without a logo, its initials on a
/// tint hashed from the company's id.
enum MacBureauMonogram {
    /// `companyInitials`: a short ticker, else the first letters of two words.
    static func initials(name: String, ticker: String?) -> String {
        let ticker = (ticker ?? "").trimmingCharacters(in: .whitespaces)
        if ticker.range(of: "^[A-Za-z]{1,5}$", options: .regularExpression) != nil {
            return String(ticker.prefix(2)).uppercased()
        }
        let name = name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return "?" }
        let tokens = name.components(separatedBy: CharacterSet(charactersIn: " \t\n,./&+_–—-")).filter { !$0.isEmpty }
        if tokens.count >= 2, let a = tokens[0].first, let b = tokens[1].first { return "\(a)\(b)".uppercased() }
        let word = (tokens.first ?? name).filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        let caps = word.filter { $0.isUppercase }
        if caps.count >= 2 { return String(caps.prefix(2)) }
        if word.count >= 2 { return String(word.prefix(2)).uppercased() }
        return word.isEmpty ? "?" : word.uppercased()
    }

    /// The tint `Monogram.vue` hashes from the company's id (its name when there is none).
    static func tint(for key: String) -> BSHRGB {
        let tints = [
            BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
            BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
        ]
        var hash: UInt32 = 0
        for unit in key.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        return tints[Int(hash % 10)]
    }
}

/// The logo on its tile: white, corners at 0.28 of the size, the logo inset by 0.08 with its
/// own corners rounded, a hairline ring and a small shadow.
struct MacBureauLogoTile: View {
    @Environment(\.colorScheme) private var colorScheme
    let image: NSImage
    let size: CGFloat

    var body: some View {
        let dark = colorScheme == .dark
        let radius = size * 0.28
        let inset = size * 0.08
        let tile = RoundedRectangle(cornerRadius: radius, style: .circular)
        Image(nsImage: image)
            .resizable()
            .interpolation(.high)
            .aspectRatio(contentMode: .fit)
            .frame(width: size - inset * 2, height: size - inset * 2)
            .clipShape(RoundedRectangle(cornerRadius: radius - inset, style: .circular))
            .frame(width: size, height: size)
            .background(Color.white)
            .overlay(tile.strokeBorder(dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5))
            .clipShape(tile)
            .background(
                // `0 1px 2px` by day, `0 1px 3px` by night.
                tile.fill(Color.white)
                    .shadow(color: .black.opacity(dark ? 0.35 : 0.06), radius: dark ? 3 : 2, y: 1)
            )
    }
}

/// The initials on the company's tint, fading toward the lower right.
struct MacBureauInitialsTile: View {
    let initials: String
    let tint: BSHRGB
    let size: CGFloat

    var body: some View {
        let tile = RoundedRectangle(cornerRadius: size * 0.28, style: .circular)
        Text(initials)
            .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
            .tracking(size * 0.0037)
            .foregroundStyle(Color.white)
            .frame(width: size, height: size)
            .background(LinearGradient(
                colors: [.bshFixed(tint), .bshFixed(tint, opacity: 0.72)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            ))
            .overlay(tile.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
            .clipShape(tile)
    }
}
