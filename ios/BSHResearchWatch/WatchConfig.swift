import Foundation

enum WatchLayoutStyle: String, CaseIterable, Identifiable {
    case deskHome
    case tileHub
    case heroTicker

    var id: String { rawValue }

    var title: String {
        switch self {
        case .deskHome: return "A · Desk Home"
        case .tileHub: return "B · Tile Hub"
        case .heroTicker: return "C · Hero Ticker"
        }
    }

    var shortTitle: String {
        switch self {
        case .deskHome: return "Desk Home"
        case .tileHub: return "Tile Hub"
        case .heroTicker: return "Hero Ticker"
        }
    }
}

enum WatchConfig {
    /// Always on the tape / resolved fetch list.
    static let defaultIndexTickers = ["SPY", "QQQ"]
    /// Used when the watchlist has no equity pins yet.
    static let defaultEquityPins = ["NVDA", "AAPL"]
    static let appGroupSuite = "group.com.bilelharrrat.bshresearch"
    static let watchlistKey = "bsh.marketPinnedTickers"
    static let baseURLKey = "bsh.baseURL"
    static let layoutStyleKey = "bsh.watch.layoutStyle"

    static var sharedDefaults: UserDefaults {
        UserDefaults(suiteName: appGroupSuite) ?? .standard
    }

    /// Prefer App Group (phone Settings), then watch override, then Info.plist, then LAN default.
    static var baseURL: URL {
        if let override = sharedDefaults.string(forKey: baseURLKey),
           let url = URL(string: override), !override.isEmpty {
            return url
        }
        if let local = UserDefaults.standard.string(forKey: baseURLKey),
           let url = URL(string: local), !local.isEmpty {
            return url
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = URL(string: plist), !plist.isEmpty {
            return url
        }
        return URL(string: "http://192.168.1.181:8010")!
    }

    static var apiRoot: URL {
        baseURL.appendingPathComponent("api")
    }

    static func saveBaseURL(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        sharedDefaults.set(trimmed, forKey: baseURLKey)
        UserDefaults.standard.set(trimmed, forKey: baseURLKey)
    }

    static var layoutStyle: WatchLayoutStyle {
        get {
            let raw = UserDefaults.standard.string(forKey: layoutStyleKey)
                ?? sharedDefaults.string(forKey: layoutStyleKey)
            return WatchLayoutStyle(rawValue: raw ?? "") ?? .tileHub
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: layoutStyleKey)
            sharedDefaults.set(newValue.rawValue, forKey: layoutStyleKey)
        }
    }

    static func loadWatchlist() -> [String] {
        if let shared = sharedDefaults.array(forKey: watchlistKey) as? [String], !shared.isEmpty {
            return shared.map { $0.uppercased() }
        }
        if let local = UserDefaults.standard.array(forKey: watchlistKey) as? [String], !local.isEmpty {
            return local.map { $0.uppercased() }
        }
        return defaultIndexTickers + defaultEquityPins
    }

    /// SPY, QQQ, then first pin (or NVDA/AAPL), capped for watch bandwidth.
    static func resolvedTapeTickers() -> [String] {
        var pins = loadWatchlist()
        let equities = pins.filter { !defaultIndexTickers.contains($0) }
        if equities.isEmpty {
            pins.append(contentsOf: defaultEquityPins)
        }

        var out: [String] = []
        var seen = Set<String>()
        for ticker in defaultIndexTickers + pins {
            let t = ticker.uppercased()
            if seen.insert(t).inserted {
                out.append(t)
            }
        }
        return Array(out.prefix(8))
    }

    /// Offline / first-launch quotes so the tape is never empty.
    static func demoQuotes() -> [WatchQuote] {
        [
            WatchQuote(ticker: "SPY", last: 530.42, pct: 0.4, name: "SPDR S&P 500 ETF"),
            WatchQuote(ticker: "QQQ", last: 468.10, pct: -0.2, name: "Invesco QQQ Trust"),
            WatchQuote(ticker: "NVDA", last: 128.40, pct: 1.8, name: "NVIDIA Corp"),
            WatchQuote(ticker: "AAPL", last: 227.52, pct: 0.3, name: "Apple Inc"),
        ]
    }

    static func phoneDeepLink(ticker: String) -> URL? {
        URL(string: "bshresearch://ticker/\(ticker.uppercased())")
    }
}
