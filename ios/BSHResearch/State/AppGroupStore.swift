import Foundation

enum AppGroupStore {
    static let suiteName = "group.com.bilelharrrat.bshresearch"
    static let watchlistKey = "bsh.marketPinnedTickers"
    static let lastLookedKey = "bsh.desk.lastLookedAt"
    static let baseURLKey = "bsh.baseURL"

    /// Prefer App Group when the capability is enabled; otherwise standard defaults.
    static var defaults: UserDefaults {
        if let shared = UserDefaults(suiteName: suiteName) {
            // Writing succeeds even without the entitlement on some OS versions;
            // also mirror to standard so Lock Screen / Watch still work later.
            return shared
        }
        return .standard
    }

    static func saveWatchlist(_ tickers: [String]) {
        defaults.set(tickers, forKey: watchlistKey)
        UserDefaults.standard.set(tickers, forKey: watchlistKey)
    }

    static func loadWatchlist() -> [String] {
        if let shared = defaults.array(forKey: watchlistKey) as? [String], !shared.isEmpty {
            return shared
        }
        return (UserDefaults.standard.array(forKey: watchlistKey) as? [String]) ?? []
    }

    static func saveBaseURL(_ url: String) {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        defaults.set(trimmed, forKey: baseURLKey)
        UserDefaults.standard.set(trimmed, forKey: baseURLKey)
    }

    static func loadBaseURL() -> String? {
        if let shared = defaults.string(forKey: baseURLKey), !shared.isEmpty {
            return shared
        }
        if let standard = UserDefaults.standard.string(forKey: baseURLKey), !standard.isEmpty {
            return standard
        }
        return nil
    }

    static func markLookedNow() {
        let iso = ISO8601DateFormatter().string(from: Date())
        defaults.set(iso, forKey: lastLookedKey)
        UserDefaults.standard.set(iso, forKey: lastLookedKey)
    }

    static func lastLookedAt() -> String? {
        defaults.string(forKey: lastLookedKey)
            ?? UserDefaults.standard.string(forKey: lastLookedKey)
    }
}
