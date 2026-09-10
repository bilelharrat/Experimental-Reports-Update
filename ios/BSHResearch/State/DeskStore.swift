import Foundation
import Combine

/// Watchlist + alert rules, synced with the server desk-prefs blob
/// (`GET/PUT /api/desk/prefs`). The blob is shared with the web desk, so we
/// read-modify-write only our keys and round-trip everything else untouched.
@MainActor
final class DeskStore: ObservableObject {
    static let watchlistKey = "bsh.marketPinnedTickers"
    static let alertRulesKey = "bsh.marketAlertRules"

    @Published private(set) var watchlist: [String] = []
    @Published private(set) var alertRules: [AlertRule] = []
    @Published var syncError: String?

    private var blob: [String: AnyCodable] = [:]
    private var loaded = false

    func loadIfNeeded() async {
        guard !loaded else { return }
        await load()
    }

    func load() async {
        do {
            let res: DeskPrefsResponse = try await APIClient.shared.get("desk/prefs")
            blob = res.data?.value ?? [:]
            watchlist = (blob[Self.watchlistKey]?.value as? [Any])?
                .compactMap { $0 as? String } ?? []
            alertRules = Self.decodeRules(blob[Self.alertRulesKey]?.value)
            loaded = true
            syncError = nil
        } catch {
            syncError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            // Fall back to whatever we last cached locally.
            if let data = UserDefaults.standard.data(forKey: "bsh.watchlist.cache"),
               let cached = try? JSONDecoder().decode([String].self, from: data) {
                watchlist = cached
            }
        }
    }

    func isWatched(_ ticker: String) -> Bool {
        watchlist.contains(ticker.uppercased())
    }

    func toggleWatch(_ ticker: String) async {
        let t = ticker.uppercased()
        if watchlist.contains(t) {
            watchlist.removeAll { $0 == t }
        } else {
            watchlist.append(t)
        }
        await push()
    }

    func addRule(_ rule: AlertRule) async {
        alertRules.append(rule)
        await push()
    }

    func updateRule(_ rule: AlertRule) async {
        if let idx = alertRules.firstIndex(where: { $0.id == rule.id }) {
            alertRules[idx] = rule
            await push()
        }
    }

    func deleteRule(id: String) async {
        alertRules.removeAll { $0.id == id }
        await push()
    }

    private func push() async {
        UserDefaults.standard.set(
            try? JSONEncoder().encode(watchlist), forKey: "bsh.watchlist.cache"
        )
        blob[Self.watchlistKey] = AnyCodable(watchlist)
        blob[Self.alertRulesKey] = AnyCodable(Self.encodeRules(alertRules))
        do {
            struct Body: Encodable {
                let data: JSONBlob
            }
            let _: DeskPrefsResponse = try await APIClient.shared.put(
                "desk/prefs", body: Body(data: JSONBlob(blob))
            )
            syncError = nil
        } catch {
            syncError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private static func decodeRules(_ raw: Any?) -> [AlertRule] {
        guard let arr = raw as? [Any],
              let data = try? JSONSerialization.data(withJSONObject: arr)
        else { return [] }
        return (try? JSONDecoder().decode([LooseRule].self, from: data))?
            .compactMap(\.rule) ?? []
    }

    private static func encodeRules(_ rules: [AlertRule]) -> [[String: Any]] {
        rules.map { r in
            [
                "id": r.id,
                "ticker": r.ticker,
                "kind": r.kind,
                "threshold": r.threshold,
                "window": r.window as Any,
                "direction": r.direction,
                "enabled": r.enabled,
            ]
        }
    }

    /// Web rules include kinds the iOS UI doesn't create (sma_cross, earnings…).
    /// Decode leniently and keep them intact when pushing back.
    private struct LooseRule: Decodable {
        let id: String?
        let ticker: String?
        let kind: String?
        let threshold: Double?
        let window: Int?
        let direction: String?
        let enabled: Bool?

        var rule: AlertRule? {
            guard let id, let ticker else { return nil }
            return AlertRule(
                id: id,
                ticker: ticker,
                kind: kind ?? "price",
                threshold: threshold ?? 0,
                window: window,
                direction: direction ?? "above",
                enabled: enabled ?? true
            )
        }
    }
}

/// Last-good quote cache so the desk still renders when the network blips.
enum QuoteCache {
    private static let key = "bsh.quotes.cache"

    static func save(_ quotes: [Quote]) {
        var all = load()
        for q in quotes {
            all[q.ticker.uppercased()] = CachedQuote(from: q)
        }
        if let data = try? JSONEncoder().encode(all) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    static func load() -> [String: CachedQuote] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let all = try? JSONDecoder().decode([String: CachedQuote].self, from: data)
        else { return [:] }
        return all
    }

    static func quotes(for tickers: [String]) -> [Quote] {
        let all = load()
        return tickers.compactMap { all[$0.uppercased()]?.asQuote }
    }
}
