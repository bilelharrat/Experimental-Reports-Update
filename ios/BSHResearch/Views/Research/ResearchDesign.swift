import SwiftUI
import UIKit

// MARK: - Research Design System Tokens (iOS adaptation of MacDS)

public enum MacDS {
    public static let page: CGFloat = 16
    public static let card: CGFloat = 16
    public static let gap: CGFloat = 12
    public static let section: CGFloat = 16
    public static let cardRadius: CGFloat = 14
    public static let tileRadius: CGFloat = 10
}

public extension Color {
    static let dsCanvas = Color(uiColor: .systemGroupedBackground)
    static let dsCard = Color(uiColor: .secondarySystemGroupedBackground)
    static let dsTile = Color(uiColor: .tertiarySystemGroupedBackground)
    static let dsHairline = Color.primary.opacity(0.08)
    static let dsPositive = Color.green
    static let dsNegative = Color.red
    static let dsWarning = Color.orange
}

public extension Font {
    static let dsTitle = Font.system(size: 22, weight: .bold)
    static let dsHeadline = Font.system(size: 15, weight: .semibold)
    static let dsSubhead = Font.system(size: 13, weight: .medium)
    static let dsBody = Font.system(size: 13)
    static let dsLabel = Font.system(size: 11, weight: .medium)
    static let dsCaption = Font.system(size: 11)
    static let dsMetric = Font.system(size: 20, weight: .semibold).monospacedDigit()
    static let dsMetricSmall = Font.system(size: 15, weight: .semibold).monospacedDigit()
}

// MARK: - Glass Modifiers

public struct AppleGlassCardModifier: ViewModifier {
    public var cornerRadius: CGFloat = MacDS.cardRadius
    public var tint: Color? = nil
    public var isInteractive: Bool = false

    public func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(tint.map { $0.opacity(0.06) } ?? Color.dsCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(Color.dsHairline, lineWidth: 1)
            )
    }
}

public struct AppleGlassTileModifier: ViewModifier {
    public var cornerRadius: CGFloat = MacDS.tileRadius
    public var tint: Color? = nil

    public func body(content: Content) -> some View {
        content.background(
            RoundedRectangle(cornerRadius: min(cornerRadius, 10), style: .continuous)
                .fill(tint.map { $0.opacity(0.10) } ?? Color.dsTile)
        )
    }
}

public struct AppleGlassPillModifier: ViewModifier {
    public var color: Color = .accentColor
    public func body(content: Content) -> some View {
        content.background(Capsule().fill(color.opacity(0.14)))
    }
}

public extension View {
    func appleGlassCard(cornerRadius: CGFloat = MacDS.cardRadius, tint: Color? = nil, isInteractive: Bool = false) -> some View {
        modifier(AppleGlassCardModifier(cornerRadius: cornerRadius, tint: tint, isInteractive: isInteractive))
    }

    func appleGlassTile(cornerRadius: CGFloat = MacDS.tileRadius, tint: Color? = nil) -> some View {
        modifier(AppleGlassTileModifier(cornerRadius: cornerRadius, tint: tint))
    }

    func appleGlassPill(color: Color = .accentColor) -> some View {
        modifier(AppleGlassPillModifier(color: color))
    }

    func embeddedInAmbientGlass() -> some View {
        background(Color.dsCanvas.ignoresSafeArea())
    }

    func dsPage() -> some View {
        padding(MacDS.page)
    }
}

// MARK: - Card Anatomy Views

public struct MacCardHeader<Trailing: View>: View {
    public let title: String
    public var subtitle: String? = nil
    public var systemImage: String? = nil
    @ViewBuilder public var trailing: () -> Trailing

    public init(_ title: String, subtitle: String? = nil, systemImage: String? = nil, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = trailing
    }

    public var body: some View {
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

public extension MacCardHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil, systemImage: String? = nil) {
        self.init(title, subtitle: subtitle, systemImage: systemImage) { EmptyView() }
    }
}

public struct MacSectionLabel: View {
    public let text: String
    public var trailing: String? = nil
    public init(_ text: String, trailing: String? = nil) { self.text = text; self.trailing = trailing }
    public var body: some View {
        HStack {
            Text(text).font(.dsLabel).foregroundStyle(.secondary)
            Spacer()
            if let trailing { Text(trailing).font(.dsCaption.monospacedDigit()).foregroundStyle(.secondary) }
        }
    }
}

public struct MacStatTile: View {
    public let label: String
    public let value: String
    public var detail: String? = nil
    public var tone: Color? = nil
    public var compact = false

    public init(label: String, value: String, detail: String? = nil, tone: Color? = nil, compact: Bool = false) {
        self.label = label
        self.value = value
        self.detail = detail
        self.tone = tone
        self.compact = compact
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.dsLabel).foregroundStyle(.secondary).lineLimit(1)
            Text(value)
                .font(compact ? .dsMetricSmall : .dsMetric)
                .foregroundStyle(tone ?? .primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            if let detail, !detail.isEmpty {
                Text(detail).font(.dsCaption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(compact ? 10 : 12)
        .appleGlassTile()
    }
}

public struct MacDeskHeader<Trailing: View>: View {
    public let title: String
    public var subtitle: String? = nil
    @ViewBuilder public var trailing: () -> Trailing

    public init(_ title: String, subtitle: String? = nil, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    public var body: some View {
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

public extension MacDeskHeader where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil) {
        self.init(title, subtitle: subtitle) { EmptyView() }
    }
}

public struct MacTabBar<Item: Hashable>: View {
    public let items: [(Item, String)]
    @Binding public var selection: Item
    @Namespace private var underline

    public init(items: [(Item, String)], selection: Binding<Item>) {
        self.items = items
        self._selection = selection
    }

    public var body: some View {
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
            }
            .padding(.horizontal, 4)
        }
        .overlay(alignment: .bottom) { Divider() }
    }
}

public struct MacStatusPill: View {
    public let text: String
    public let color: Color

    public init(text: String, color: Color) {
        self.text = text
        self.color = color
    }

    public var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.16), in: Capsule())
            .lineLimit(1)
    }
}

public struct MacDot: View {
    public let color: Color
    public var size: CGFloat = 6

    public init(_ color: Color, size: CGFloat = 6) {
        self.color = color
        self.size = size
    }

    public var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
    }
}

// MARK: - Logo & Monogram Resolver

public enum MacCompanyLogoResolver {
    public static let tickerDomainMap: [String: String] = [
        "AAPL": "apple.com", "NVDA": "nvidia.com", "MSFT": "microsoft.com",
        "GOOG": "google.com", "GOOGL": "google.com", "AMZN": "amazon.com",
        "META": "meta.com", "TSLA": "tesla.com", "TSM": "tsmc.com",
        "INTC": "intel.com", "AMD": "amd.com", "AMGN": "amgen.com",
        "HIPO": "hippo.com", "NB": "niocorp.com", "JOYY": "joyy.com",
        "HIND": "vyome.com", "HIMS": "forhims.com", "BABA": "alibaba.com",
        "AVGO": "broadcom.com", "ASML": "asml.com", "QCOM": "qualcomm.com",
        "ORCL": "oracle.com", "CRM": "salesforce.com", "NFLX": "netflix.com",
        "UBER": "uber.com", "PLTR": "palantir.com", "COIN": "coinbase.com",
        "HOOD": "robinhood.com", "SNOW": "snowflake.com", "CRWD": "crowdstrike.com",
        "NET": "cloudflare.com", "ARM": "arm.com", "DELL": "dell.com",
        "IBM": "ibm.com", "CSCO": "cisco.com", "ADBE": "adobe.com",
        "NOW": "servicenow.com", "INTU": "intuit.com", "PYPL": "paypal.com",
        "SQ": "block.xyz", "SHOP": "shopify.com", "SPOT": "spotify.com",
        "ABNB": "airbnb.com", "DASH": "doordash.com", "RBLX": "roblox.com",
        "SNAP": "snapchat.com", "PINS": "pinterest.com", "RDDT": "reddit.com",
        "NN": "nextnav.com", "KO": "coca-cola.com", "OXY": "oxy.com",
        "ATE": "alten.com", "DIS": "disney.com", "NKE": "nike.com",
        "SBUX": "starbucks.com", "MCD": "mcdonalds.com", "WMT": "walmart.com",
        "COST": "costco.com", "JNJ": "jnj.com", "PFE": "pfizer.com",
        "UNH": "uhc.com", "V": "visa.com", "MA": "mastercard.com",
        "JPM": "jpmorganchase.com", "BAC": "bankofamerica.com",
        "GS": "goldmansachs.com", "MS": "morganstanley.com",
        "XOM": "exxonmobil.com", "CVX": "chevron.com"
    ]

    public static let slugDomainMap: [String: String] = [
        "anthropic": "anthropic.com",
        "anthropic-pbc": "anthropic.com",
        "openai": "openai.com",
        "open-artificial-intelligence": "openai.com",
        "open-artificial-intelligence-inc": "openai.com",
        "google": "google.com",
        "google-llc": "google.com",
        "coca-cola": "coca-cola.com",
        "coca-cola-co": "coca-cola.com",
        "ko": "coca-cola.com",
        "oxy": "oxy.com",
        "occidental-petroleum": "oxy.com",
        "cienet-technologies-beijing-co-ltd": "cienet.com",
        "cienet-technologies": "cienet.com",
        "cienet": "cienet.com",
        "clenet-technologies": "cienet.com",
        "clenet": "cienet.com",
        "ceinet-data-co-ltd-中经网数据有限公司": "cei.cn",
        "中经网数据有限公司": "cei.cn",
        "ceinet-data": "cei.cn",
        "ceinet": "cei.cn",
        "celnet-data": "cei.cn",
        "celnet": "cei.cn",
        "alten": "alten.com",
        "ate": "alten.com",
        "tsm": "tsmc.com",
        "tsmc": "tsmc.com",
        "zainar": "zainartech.com",
        "zainar-inc": "zainartech.com",
        "zainartech": "zainartech.com",
        "hims": "forhims.com",
        "forhims": "forhims.com",
        "databricks": "databricks.com",
        "stripe": "stripe.com",
        "cerebras": "cerebras.ai",
        "anduril": "anduril.com",
        "spacex": "spacex.com",
        "scale-ai": "scale.com",
        "scale": "scale.com",
        "mistral": "mistral.ai",
        "mistral-ai": "mistral.ai",
        "cohere": "cohere.com",
        "perplexity": "perplexity.ai",
        "xai": "x.ai",
        "groq": "groq.com",
        "figure": "figure.ai",
        "figure-ai": "figure.ai",
        "coreweave": "coreweave.com",
        "midjourney": "midjourney.com",
        "huggingface": "huggingface.co",
        "deepseek": "deepseek.com",
        "oasis-security": "oasis.security",
        "oasissecurity": "oasis.security",
        "oasys-now": "oasysnow.com",
        "oasysnow": "oasysnow.com"
    ]

    public static let highResLogos: [String: String] = [
        "cerebras": "https://avatars.githubusercontent.com/Cerebras?s=256",
        "anduril": "https://avatars.githubusercontent.com/anduril?s=256",
        "deepseek": "https://avatars.githubusercontent.com/deepseek-ai?s=256",
        "cohere": "https://avatars.githubusercontent.com/cohere-ai?s=256",
        "figure": "https://avatars.githubusercontent.com/Figure-AI?s=256",
        "figure-ai": "https://avatars.githubusercontent.com/Figure-AI?s=256",
        "groq": "https://avatars.githubusercontent.com/groq?s=256",
        "coreweave": "https://avatars.githubusercontent.com/coreweave?s=256",
        "oasis-security": "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
        "oasissecurity": "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
        "zainar-inc": "https://zainartech.com/favicon.ico?favicon.d517f128.ico",
        "zainar": "https://zainartech.com/favicon.ico?favicon.d517f128.ico"
    ]

    public static func normalizeDomain(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        var d = raw.lowercased()
        if let range = d.range(of: "://") { d = String(d[range.upperBound...]) }
        if let idx = d.firstIndex(where: { $0 == "/" || $0 == "?" || $0 == "#" || $0 == ":" }) {
            d = String(d[..<idx])
        }
        if d.hasPrefix("www.") { d = String(d.dropFirst(4)) }
        return d.isEmpty ? nil : d
    }

    public static func isSvgUrl(_ urlString: String) -> Bool {
        let lower = urlString.lowercased()
        if lower.hasSuffix(".svg") || lower.contains(".svg?") || lower.contains("/svg") {
            return true
        }
        if lower.contains("assets.parqet.com/logos/symbol") {
            return true
        }
        if lower.contains("simple-icons:") || lower.contains("iconify.design") {
            return true
        }
        return false
    }

    public static func googleFaviconUrl(domain: String?) -> String? {
        guard let d = normalizeDomain(domain),
              let encoded = d.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return nil }
        return "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://\(encoded)&size=128"
    }

    public static func duckduckgoFaviconUrl(domain: String?) -> String? {
        guard let d = normalizeDomain(domain),
              let encoded = d.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else { return nil }
        return "https://icons.duckduckgo.com/ip3/\(encoded).ico"
    }

    public static func googleS2FaviconUrl(domain: String?) -> String? {
        guard let d = normalizeDomain(domain),
              let encoded = d.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return nil }
        return "https://www.google.com/s2/favicons?domain=\(encoded)&sz=128"
    }

    public static func resolveDomain(
        logoDomain: String? = nil,
        website: String? = nil,
        ticker: String? = nil,
        companyId: String? = nil,
        name: String? = nil
    ) -> String? {
        if let d = normalizeDomain(logoDomain) { return d }
        if let d = normalizeDomain(website) { return d }
        if let t = ticker?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
           let d = tickerDomainMap[t] {
            return d
        }
        if let cid = companyId?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            if let d = slugDomainMap[cid] { return d }
            let idTicker = cid.uppercased()
            if let d = tickerDomainMap[idTicker] { return d }
        }
        if let n = name?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            let clean = n.filter { $0.isLetter || $0.isNumber }
            if let d = slugDomainMap[clean] { return d }
            for (key, domain) in slugDomainMap {
                let cleanKey = key.filter { $0.isLetter || $0.isNumber }
                if n.contains(key) || (!cleanKey.isEmpty && clean.contains(cleanKey)) {
                    return domain
                }
            }
        }
        return nil
    }

    public static func resolveCandidateUrls(
        logoUrl: String? = nil,
        logoDomain: String? = nil,
        website: String? = nil,
        ticker: String? = nil,
        companyId: String? = nil,
        name: String? = nil
    ) -> [URL] {
        var candidates: [URL] = []
        var seen = Set<String>()

        func add(_ urlString: String?) {
            guard let urlString = urlString?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !urlString.isEmpty,
                  !seen.contains(urlString),
                  let url = URL(string: urlString) else { return }
            seen.insert(urlString)
            candidates.append(url)
        }

        let rawUrl = logoUrl?.trimmingCharacters(in: .whitespacesAndNewlines)
        let isRawSvg = rawUrl.map { isSvgUrl($0) } ?? false

        // 1. If explicit non-SVG logo URL is provided, try it first
        if let rawUrl, !isRawSvg {
            add(rawUrl)
        }

        // 2. Curated high-resolution raster logos
        let cid = (companyId ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !cid.isEmpty, let u = highResLogos[cid] {
            add(u)
        }

        // 3. Domain-based CDN candidates (Google 128px PNG, DuckDuckGo ICO, Google S2, Clearbit)
        if let domain = resolveDomain(logoDomain: logoDomain, website: website, ticker: ticker, companyId: companyId, name: name) {
            add(googleFaviconUrl(domain: domain))
            add(duckduckgoFaviconUrl(domain: domain))
            add(googleS2FaviconUrl(domain: domain))
            add("https://logo.clearbit.com/\(domain)")
        }

        // 4. Raw SVG URL as a last-ditch candidate
        if let rawUrl, isRawSvg {
            add(rawUrl)
        }

        return candidates
    }

    public static func resolvePrimaryLogoUrl(
        logoUrl: String? = nil,
        logoDomain: String? = nil,
        website: String? = nil,
        ticker: String? = nil,
        companyId: String? = nil,
        name: String? = nil
    ) -> URL? {
        resolveCandidateUrls(
            logoUrl: logoUrl,
            logoDomain: logoDomain,
            website: website,
            ticker: ticker,
            companyId: companyId,
            name: name
        ).first
    }
}

final class MacImageCache: @unchecked Sendable {
    static let shared = MacImageCache()
    private let cache = NSCache<NSString, UIImage>()
    private let lock = NSLock()
    private var failedUrls = Set<String>()

    init() {
        cache.countLimit = 500
        cache.totalCostLimit = 100 * 1024 * 1024
    }

    func image(for url: URL) -> UIImage? {
        cache.object(forKey: url.absoluteString as NSString)
    }

    func setImage(_ img: UIImage, for url: URL) {
        let cost = Int(img.size.width * img.size.height * 4)
        cache.setObject(img, forKey: url.absoluteString as NSString, cost: cost)
    }

    func isFailed(_ url: URL) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return failedUrls.contains(url.absoluteString)
    }

    func markFailed(_ url: URL) {
        lock.lock()
        defer { lock.unlock() }
        failedUrls.insert(url.absoluteString)
    }
}

public struct MacMonogram: View {
    public let name: String
    public var ticker: String?
    public var companyId: String?
    public var logoUrl: String?
    public var logoDomain: String?
    public var website: String?
    public var size: CGFloat
    public var round: Bool
    public var showLogo: Bool

    @State private var image: UIImage?

    private static let palette: [Color] = [
        .blue, .indigo, .purple, .pink, .red, .orange, .teal, .cyan, .mint, .green
    ]

    public init(
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

    public init(
        company: MacCompany,
        size: CGFloat = 44,
        round: Bool = false,
        showLogo: Bool = true
    ) {
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

    public var body: some View {
        Group {
            if let image {
                ZStack {
                    Color.white
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .padding(size * 0.08)
                }
                .frame(width: size, height: size)
                .clipShape(RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous)
                        .strokeBorder(Color.black.opacity(0.10), lineWidth: 0.5)
                )
                .shadow(color: Color.black.opacity(0.06), radius: 1.5, x: 0, y: 0.5)
            } else {
                fallbackBadge
            }
        }
        .task(id: "\(companyId ?? "")-\(ticker ?? "")-\(logoUrl ?? "")-\(logoDomain ?? "")") {
            await loadImage()
        }
    }

    private var fallbackBadge: some View {
        let initials = name.split(separator: " ").prefix(2)
            .compactMap { $0.first.map(String.init) }.joined().uppercased()
        let color = Self.palette[abs(name.hashValue) % Self.palette.count]
        return Text(initials.isEmpty ? "?" : initials)
            .font(.system(size: size * 0.38, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(
                LinearGradient(colors: [color, color.opacity(0.72)],
                               startPoint: .topLeading, endPoint: .bottomTrailing),
                in: RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous)
                    .strokeBorder(Color.white.opacity(0.15), lineWidth: 0.5)
            )
    }

    private func loadImage() async {
        guard showLogo else { return }

        let candidates = MacCompanyLogoResolver.resolveCandidateUrls(
            logoUrl: logoUrl,
            logoDomain: logoDomain,
            website: website,
            ticker: ticker,
            companyId: companyId,
            name: name
        )
        guard !candidates.isEmpty else { return }

        // Check if any candidate is already in memory cache
        for candidate in candidates {
            if let cached = MacImageCache.shared.image(for: candidate) {
                await MainActor.run { self.image = cached }
                return
            }
        }

        // Waterfall attempt across candidates
        for candidate in candidates {
            if MacImageCache.shared.isFailed(candidate) { continue }

            do {
                var req = URLRequest(url: candidate, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8.0)
                req.setValue(
                    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                    forHTTPHeaderField: "User-Agent"
                )
                req.setValue("image/*,*/*;q=0.8", forHTTPHeaderField: "Accept")

                let (data, response) = try await URLSession.shared.data(for: req)
                if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
                    MacImageCache.shared.markFailed(candidate)
                    continue
                }

                // Check for SVG MIME type or raw SVG XML tag (UIKit cannot decode SVG data)
                if let mime = (response as? HTTPURLResponse)?.mimeType?.lowercased(), mime.contains("svg") {
                    MacImageCache.shared.markFailed(candidate)
                    continue
                }
                if data.count > 4 {
                    let prefix = String(data: data.prefix(100), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
                    if prefix.hasPrefix("<?xml") || prefix.hasPrefix("<svg") || prefix.contains("<svg") {
                        MacImageCache.shared.markFailed(candidate)
                        continue
                    }
                }

                if let uiImg = UIImage(data: data) {
                    MacImageCache.shared.setImage(uiImg, for: candidate)
                    await MainActor.run { self.image = uiImg }
                    return
                } else {
                    MacImageCache.shared.markFailed(candidate)
                }
            } catch {
                MacImageCache.shared.markFailed(candidate)
            }
        }
    }
}
