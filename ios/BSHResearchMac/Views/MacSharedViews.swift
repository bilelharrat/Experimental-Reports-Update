import SwiftUI

struct MacStatusPill: View {
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

// MARK: - Company Logo Resolver & Asset Pipeline

enum MacCompanyLogoResolver {
    static let tickerDomainMap: [String: String] = [
        "AAPL": "apple.com",
        "NVDA": "nvidia.com",
        "MSFT": "microsoft.com",
        "GOOG": "google.com",
        "GOOGL": "google.com",
        "AMZN": "amazon.com",
        "META": "meta.com",
        "TSLA": "tesla.com",
        "TSM": "tsmc.com",
        "INTC": "intel.com",
        "AMD": "amd.com",
        "AMGN": "amgen.com",
        "HIPO": "hippo.com",
        "NB": "niocorp.com",
        "JOYY": "joyy.com",
        "HIND": "vyome.com",
        "BABA": "alibaba.com",
        "AVGO": "broadcom.com",
        "ASML": "asml.com",
        "QCOM": "qualcomm.com",
        "ORCL": "oracle.com",
        "CRM": "salesforce.com",
        "NFLX": "netflix.com",
        "UBER": "uber.com",
        "PLTR": "palantir.com",
        "COIN": "coinbase.com",
        "HOOD": "robinhood.com",
        "SNOW": "snowflake.com",
        "CRWD": "crowdstrike.com",
        "NET": "cloudflare.com",
        "ARM": "arm.com",
        "DELL": "dell.com",
        "IBM": "ibm.com",
        "CSCO": "cisco.com",
        "ADBE": "adobe.com",
        "NOW": "servicenow.com",
        "INTU": "intuit.com",
        "PYPL": "paypal.com",
        "SQ": "block.xyz",
        "SHOP": "shopify.com",
        "SPOT": "spotify.com",
        "ABNB": "airbnb.com",
        "DASH": "doordash.com",
        "RBLX": "roblox.com",
        "SNAP": "snapchat.com",
        "PINS": "pinterest.com",
        "RDDT": "reddit.com",
        "NN": "nextnav.com",
        "KO": "coca-cola.com",
        "OXY": "oxy.com",
        "ATE": "alten.com",
        "DIS": "disney.com",
        "NKE": "nike.com",
        "SBUX": "starbucks.com",
        "MCD": "mcdonalds.com",
        "WMT": "walmart.com",
        "COST": "costco.com",
        "JNJ": "jnj.com",
        "PFE": "pfizer.com",
        "UNH": "uhc.com",
        "V": "visa.com",
        "MA": "mastercard.com",
        "JPM": "jpmorganchase.com",
        "BAC": "bankofamerica.com",
        "GS": "goldmansachs.com",
        "MS": "morganstanley.com",
        "XOM": "exxonmobil.com",
        "CVX": "chevron.com",
        "HIMS": "forhims.com"
    ]

    static let slugDomainMap: [String: String] = [
        "anthropic": "anthropic.com",
        "anthropic-pbc": "anthropic.com",
        "openai": "openai.com",
        "open-artificial-intelligence": "openai.com",
        "open-artificial-intelligence-inc": "openai.com",
        "google-llc": "google.com",
        "google": "google.com",
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
        "ate": "alten.com",
        "alten": "alten.com",
        "oasys-now": "oasysnow.com",
        "oasysnow": "oasysnow.com",
        "oasis-security": "oasis.security",
        "oasissecurity": "oasis.security",
        "cerebras": "cerebras.ai",
        "databricks": "databricks.com",
        "stripe": "stripe.com",
        "mistral": "mistral.ai",
        "mistral-ai": "mistral.ai",
        "perplexity": "perplexity.ai",
        "spacex": "spacex.com",
        "anduril": "anduril.com",
        "scale-ai": "scale.com",
        "scale": "scale.com",
        "midjourney": "midjourney.com",
        "huggingface": "huggingface.co",
        "deepseek": "deepseek.com",
        "cohere": "cohere.com",
        "figure": "figure.ai",
        "figure-ai": "figure.ai",
        "groq": "groq.com",
        "coreweave": "coreweave.com",
        "xai": "x.ai",
        "zainar-inc": "zainartech.com",
        "zainar": "zainartech.com",
        "hims": "forhims.com"
    ]

    static let highResLogos: [String: String] = [
        "anthropic": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://anthropic.com&size=128",
        "anthropic-pbc": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://anthropic.com&size=128",
        "openai": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://openai.com&size=128",
        "open-artificial-intelligence": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://openai.com&size=128",
        "open-artificial-intelligence-inc": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://openai.com&size=128",
        "google-llc": "https://assets.parqet.com/logos/symbol/GOOG",
        "google": "https://assets.parqet.com/logos/symbol/GOOG",
        "ko": "https://assets.parqet.com/logos/symbol/KO",
        "oxy": "https://assets.parqet.com/logos/symbol/OXY",
        "tsm": "https://assets.parqet.com/logos/symbol/TSM",
        "cienet-technologies-beijing-co-ltd": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
        "cienet-technologies": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
        "cienet": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
        "clenet-technologies": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
        "clenet": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
        "ceinet-data-co-ltd-中经网数据有限公司": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "中经网数据有限公司": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "ceinet-data": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "ceinet": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "celnet-data": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "celnet": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
        "ate": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://alten.com&size=128",
        "alten": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://alten.com&size=128",
        "oasys-now": "https://framerusercontent.com/images/ctwK8JfDzLYECpwWHw7fd1rrZU.svg",
        "oasysnow": "https://framerusercontent.com/images/ctwK8JfDzLYECpwWHw7fd1rrZU.svg",
        "oasis-security": "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
        "oasissecurity": "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
        "cerebras": "https://avatars.githubusercontent.com/Cerebras?s=256",
        "databricks": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://databricks.com&size=128",
        "stripe": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://stripe.com&size=128",
        "mistral": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://mistral.ai&size=128",
        "mistral-ai": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://mistral.ai&size=128",
        "perplexity": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://perplexity.ai&size=128",
        "spacex": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://spacex.com&size=128",
        "anduril": "https://avatars.githubusercontent.com/anduril?s=256",
        "scale-ai": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://scale.com&size=128",
        "scale": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://scale.com&size=128",
        "midjourney": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://midjourney.com&size=128",
        "huggingface": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://huggingface.co&size=128",
        "deepseek": "https://avatars.githubusercontent.com/deepseek-ai?s=256",
        "cohere": "https://avatars.githubusercontent.com/cohere-ai?s=256",
        "figure": "https://avatars.githubusercontent.com/Figure-AI?s=256",
        "figure-ai": "https://avatars.githubusercontent.com/Figure-AI?s=256",
        "groq": "https://avatars.githubusercontent.com/groq?s=256",
        "coreweave": "https://avatars.githubusercontent.com/coreweave?s=256",
        "xai": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://x.ai&size=128",
        "zainar-inc": "https://zainartech.com/favicon.ico?favicon.d517f128.ico",
        "zainar": "https://zainartech.com/favicon.ico?favicon.d517f128.ico"
    ]

    static func normalizeDomain(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        var d = raw.lowercased()
        if let range = d.range(of: "://") {
            d = String(d[range.upperBound...])
        }
        if let idx = d.firstIndex(where: { $0 == "/" || $0 == "?" || $0 == "#" || $0 == ":" }) {
            d = String(d[..<idx])
        }
        if d.hasPrefix("www.") {
            d = String(d.dropFirst(4))
        }
        return d.isEmpty ? nil : d
    }

    static func parqetLogoUrl(ticker: String?) -> String? {
        guard let t = ticker?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(), !t.isEmpty else { return nil }
        guard let encoded = t.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else { return nil }
        return "https://assets.parqet.com/logos/symbol/\(encoded)"
    }

    static func googleFaviconUrl(domain: String?) -> String? {
        guard let d = normalizeDomain(domain) else { return nil }
        guard let encoded = d.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return nil }
        return "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://\(encoded)&size=128"
    }

    static func duckduckgoFaviconUrl(domain: String?) -> String? {
        guard let d = normalizeDomain(domain) else { return nil }
        guard let encoded = d.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else { return nil }
        return "https://icons.duckduckgo.com/ip3/\(encoded).ico"
    }

    static func resolveDomain(
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

    static func resolvePrimaryLogoUrl(
        logoUrl: String? = nil,
        logoDomain: String? = nil,
        website: String? = nil,
        ticker: String? = nil,
        companyId: String? = nil,
        name: String? = nil
    ) -> URL? {
        if let lu = logoUrl?.trimmingCharacters(in: .whitespacesAndNewlines), !lu.isEmpty, let url = URL(string: lu) {
            return url
        }
        let cid = (companyId ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !cid.isEmpty, let u = highResLogos[cid], let url = URL(string: u) {
            return url
        }
        let n = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let clean = n.filter { $0.isLetter || $0.isNumber }
        if !clean.isEmpty, let u = highResLogos[clean], let url = URL(string: u) {
            return url
        }

        // Entity name pattern matching
        if n.contains("coca") && n.contains("cola") {
            if let u = parqetLogoUrl(ticker: "KO"), let url = URL(string: u) { return url }
        }
        if n.contains("openai") || (n.contains("open") && n.contains("intelligence")) {
            if let u = highResLogos["openai"], let url = URL(string: u) { return url }
        }
        if n.contains("occidental") {
            if let u = parqetLogoUrl(ticker: "OXY"), let url = URL(string: u) { return url }
        }
        if n.contains("google") || n.contains("alphabet") {
            if let u = parqetLogoUrl(ticker: "GOOG"), let url = URL(string: u) { return url }
        }
        if n.contains("anthropic") {
            if let u = highResLogos["anthropic"], let url = URL(string: u) { return url }
        }
        if n.contains("taiwan semiconductor") || n.contains("tsmc") {
            if let u = parqetLogoUrl(ticker: "TSM"), let url = URL(string: u) { return url }
        }

        // Public stock symbol vector SVG
        var effectiveTicker = (ticker ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if effectiveTicker.isEmpty && cid.count <= 5 && tickerDomainMap[cid.uppercased()] != nil {
            effectiveTicker = cid.uppercased()
        }
        if !effectiveTicker.isEmpty, let u = parqetLogoUrl(ticker: effectiveTicker), let url = URL(string: u) {
            return url
        }

        // Google Edge Favicon CDN (128px high-res)
        if let domain = resolveDomain(logoDomain: logoDomain, website: website, ticker: ticker, companyId: companyId, name: name),
           let u = googleFaviconUrl(domain: domain),
           let url = URL(string: u) {
            return url
        }

        return nil
    }

    static func resolveFallbackLogoUrl(
        logoDomain: String? = nil,
        website: String? = nil,
        ticker: String? = nil,
        companyId: String? = nil,
        name: String? = nil
    ) -> URL? {
        guard let domain = resolveDomain(logoDomain: logoDomain, website: website, ticker: ticker, companyId: companyId, name: name) else {
            return nil
        }
        let effectiveTicker = (ticker ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let cid = (companyId ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !effectiveTicker.isEmpty || highResLogos[cid] != nil {
            if let u = googleFaviconUrl(domain: domain), let url = URL(string: u) {
                return url
            }
        }
        if let u = duckduckgoFaviconUrl(domain: domain), let url = URL(string: u) {
            return url
        }
        return nil
    }
}

// MARK: - In-Memory Image Cache

final class MacImageCache: @unchecked Sendable {
    static let shared = MacImageCache()
    private let cache = NSCache<NSString, NSImage>()
    private let lock = NSLock()
    private var failedUrls = Set<String>()

    init() {
        cache.countLimit = 500
        cache.totalCostLimit = 100 * 1024 * 1024 // 100 MB
    }

    func image(for url: URL) -> NSImage? {
        cache.object(forKey: url.absoluteString as NSString)
    }

    func setImage(_ img: NSImage, for url: URL) {
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

// MARK: - Company Logo Image View

struct MacCompanyLogoView: View {
    let primaryUrl: URL?
    let fallbackUrl: URL?
    let fallbackName: String
    let size: CGFloat
    let round: Bool

    @State private var image: NSImage?

    init(
        primaryUrl: URL?,
        fallbackUrl: URL?,
        fallbackName: String,
        size: CGFloat,
        round: Bool
    ) {
        self.primaryUrl = primaryUrl
        self.fallbackUrl = fallbackUrl
        self.fallbackName = fallbackName
        self.size = size
        self.round = round

        if let p = primaryUrl, let cached = MacImageCache.shared.image(for: p) {
            _image = State(initialValue: cached)
        } else if let f = fallbackUrl, let cached = MacImageCache.shared.image(for: f) {
            _image = State(initialValue: cached)
        }
    }

    var body: some View {
        Group {
            if let img = image {
                Image(nsImage: img)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .padding(max(2, size * 0.1))
                    .frame(width: size, height: size)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.22), style: .continuous)
                            .strokeBorder(Color.black.opacity(0.12), lineWidth: 0.5)
                    )
                    .shadow(color: Color.black.opacity(0.10), radius: 1.5, x: 0, y: 0.5)
            } else {
                fallbackBadge
            }
        }
        .task(id: primaryUrl?.absoluteString ?? fallbackUrl?.absoluteString ?? fallbackName) {
            await fetchIfNeeded()
        }
    }

    private var fallbackBadge: some View {
        let initials = fallbackName.split(separator: " ").prefix(2)
            .compactMap { $0.first.map(String.init) }.joined().uppercased()
        let palette: [Color] = [
            .blue, .indigo, .purple, .pink, .red, .orange, .teal, .cyan, .mint, .green,
        ]
        let color = palette[abs(fallbackName.hashValue) % palette.count]
        return Text(initials.isEmpty ? "?" : initials)
            .font(.system(size: size * 0.38, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(
                LinearGradient(colors: [color, color.opacity(0.72)],
                               startPoint: .topLeading, endPoint: .bottomTrailing),
                in: RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.24), style: .continuous)
            )
    }

    private func fetchIfNeeded() async {
        if image != nil { return }
        if let p = primaryUrl, !MacImageCache.shared.isFailed(p) {
            if let img = await fetchImage(from: p) {
                self.image = img
                MacImageCache.shared.setImage(img, for: p)
                return
            } else {
                MacImageCache.shared.markFailed(p)
            }
        }
        if let f = fallbackUrl, !MacImageCache.shared.isFailed(f) {
            if let img = await fetchImage(from: f) {
                self.image = img
                MacImageCache.shared.setImage(img, for: f)
                return
            } else {
                MacImageCache.shared.markFailed(f)
            }
        }
    }

    private func fetchImage(from url: URL) async -> NSImage? {
        do {
            var req = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8.0)
            req.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            let (data, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
                return nil
            }
            let clean = sanitizeImageData(data)
            return NSImage(data: clean)
        } catch {
            return nil
        }
    }

    private func sanitizeImageData(_ data: Data) -> Data {
        guard let str = String(data: data, encoding: .utf8), str.contains("<svg") else {
            return data
        }
        var clean = str
        if clean.contains("width=\"1em\"") {
            clean = clean.replacingOccurrences(of: "width=\"1em\"", with: "width=\"64\"")
        }
        if clean.contains("height=\"1em\"") {
            clean = clean.replacingOccurrences(of: "height=\"1em\"", with: "height=\"64\"")
        }
        return clean.data(using: .utf8) ?? data
    }
}

// MARK: - MacMonogram (Unified Company Logo & Squircle Tile)

struct MacMonogram: View {
    let name: String
    var ticker: String?
    var companyId: String?
    var logoUrl: String?
    var website: String?
    var size: CGFloat
    var round: Bool
    var showLogo: Bool

    private static let palette: [Color] = [
        .blue, .indigo, .purple, .pink, .red, .orange, .teal, .cyan, .mint, .green,
    ]

    init(
        name: String,
        ticker: String? = nil,
        companyId: String? = nil,
        logoUrl: String? = nil,
        website: String? = nil,
        size: CGFloat = 44,
        round: Bool = false,
        showLogo: Bool = true
    ) {
        self.name = name
        self.ticker = ticker
        self.companyId = companyId
        self.logoUrl = logoUrl
        self.website = website
        self.size = size
        self.round = round
        self.showLogo = showLogo
    }

    init(
        company: MacCompany,
        size: CGFloat = 44,
        round: Bool = false,
        showLogo: Bool = true
    ) {
        self.name = company.name ?? company.id
        self.ticker = company.ticker
        self.companyId = company.id
        self.logoUrl = company.logoUrl
        self.website = company.website
        self.size = size
        self.round = round
        self.showLogo = showLogo
    }

    private var primaryUrl: URL? {
        guard showLogo else { return nil }
        return MacCompanyLogoResolver.resolvePrimaryLogoUrl(
            logoUrl: logoUrl,
            website: website,
            ticker: ticker,
            companyId: companyId,
            name: name
        )
    }

    private var fallbackUrl: URL? {
        guard showLogo else { return nil }
        return MacCompanyLogoResolver.resolveFallbackLogoUrl(
            website: website,
            ticker: ticker,
            companyId: companyId,
            name: name
        )
    }

    var body: some View {
        if showLogo && (primaryUrl != nil || fallbackUrl != nil) {
            MacCompanyLogoView(
                primaryUrl: primaryUrl,
                fallbackUrl: fallbackUrl,
                fallbackName: name,
                size: size,
                round: round
            )
        } else {
            fallbackBadge
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
                in: RoundedRectangle(cornerRadius: size * (round ? 0.5 : 0.24), style: .continuous)
            )
    }
}
