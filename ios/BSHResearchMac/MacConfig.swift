import Foundation
import Security
#if canImport(AppKit)
import AppKit
#endif

enum MacConfig {
    static let baseURLKey = "bsh.baseURL"
    /// Pre-Keychain token slot. Read once and migrated into the Keychain.
    static let legacyTokenKey = "bsh.sessionToken"
    static let bypassLoginKey = "bsh.requireLogin"
    static let requireLoginKey = bypassLoginKey
    private static let keychainAccountBase = "bsh.research.session.mac"
    private static let defaultBaseURL = URL(string: "http://127.0.0.1:8010")!

    static var baseURL: URL {
        if let override = UserDefaults.standard.string(forKey: baseURLKey),
           !override.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            if let url = normalizedBaseURL(override) {
                return url
            }
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = normalizedBaseURL(plist) {
            return url
        }
        return defaultBaseURL
    }

    /// Non-nil when a stored base URL exists but cannot be used; the default applies instead.
    static var storedBaseURLError: String? {
        guard let override = UserDefaults.standard.string(forKey: baseURLKey) else { return nil }
        let trimmed = override.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, normalizedBaseURL(trimmed) == nil else { return nil }
        return "Invalid base URL “\(trimmed)” — include a scheme and host, e.g. http://192.168.1.5:8010. Using \(baseURL.absoluteString)."
    }

    static var apiRoot: URL {
        baseURL.appendingPathComponent("api")
    }

    /// Canonical server identity ("host:port", lowercased, with the mount path) used to
    /// scope per-server state such as the disk cache and the Keychain session.
    static var serverScope: String {
        let url = baseURL
        let scheme = (url.scheme ?? "http").lowercased()
        let host = (url.host ?? "").lowercased()
        let port = url.port ?? (scheme == "https" ? 443 : 80)
        let path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return path.isEmpty ? "\(host):\(port)" : "\(host):\(port)/\(path)"
    }

    /// True unless the user flipped "Require User Authentication" in Settings.
    /// With the dev server's `BSH_ALLOW_ANON_DEV=1` the API accepts unauthenticated
    /// calls as a local admin; the login sheet only appears when the server says 401.
    static var bypassLogin: Bool {
        !requireLogin
    }

    static var requireLogin: Bool {
        UserDefaults.standard.object(forKey: requireLoginKey) as? Bool == true
    }

    /// Cleans a user-typed base URL: trims, adds a missing `http://`, requires an http(s)
    /// scheme and a host, drops trailing slashes and a trailing `/api` segment.
    static func normalizedBaseURL(_ raw: String) -> URL? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        let lower = text.lowercased()
        if (lower.hasPrefix("http:") || lower.hasPrefix("https:")), !text.contains("://") {
            return nil
        }
        if !text.contains("://") {
            text = "http://" + text
        }
        guard var components = URLComponents(string: text),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host, !host.isEmpty,
              !components.path.hasPrefix("//")
        else { return nil }
        components.scheme = scheme
        components.query = nil
        components.fragment = nil
        var segments = components.path
            .split(separator: "/", omittingEmptySubsequences: true)
            .map(String.init)
        if segments.last?.lowercased() == "api" {
            segments.removeLast()
        }
        components.path = segments.isEmpty ? "" : "/" + segments.joined(separator: "/")
        return components.url
    }

    @discardableResult
    static func saveBaseURL(_ raw: String) -> Bool {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            UserDefaults.standard.removeObject(forKey: baseURLKey)
            return true
        }
        guard let url = normalizedBaseURL(trimmed) else { return false }
        UserDefaults.standard.set(url.absoluteString, forKey: baseURLKey)
        return true
    }

    /// Builds a URL on the configured server for an API route or a server-relative path.
    /// Absolute http(s) strings pass through. A base mount path (e.g. `/research`) is
    /// kept and never doubled; `api/` is prepended when missing. Any `?query` in the
    /// value is preserved as-is, `query` items are appended.
    static func serverURL(_ pathOrURL: String, query: [URLQueryItem] = []) -> URL? {
        let lower = pathOrURL.lowercased()
        if lower.hasPrefix("http://") || lower.hasPrefix("https://") {
            guard var components = URLComponents(string: pathOrURL) else { return nil }
            if !query.isEmpty {
                components.queryItems = (components.queryItems ?? []) + query
                components.percentEncodedQuery = escapePlus(components.percentEncodedQuery)
            }
            return components.url
        }
        var route = pathOrURL
        var rawQuery: String?
        if let q = route.firstIndex(of: "?") {
            rawQuery = String(route[route.index(after: q)...])
            route = String(route[..<q])
        }
        route = route.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let base = baseURL.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if !base.isEmpty {
            if route == base {
                route = ""
            } else if route.hasPrefix(base + "/") {
                route = String(route.dropFirst(base.count + 1))
            }
        }
        if route != "api", !route.hasPrefix("api/") {
            route = route.isEmpty ? "api" : "api/" + route
        }
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.path = "/" + [base, route].filter { !$0.isEmpty }.joined(separator: "/")
        components.query = nil
        if let rawQuery, !rawQuery.isEmpty {
            let allowed = CharacterSet.urlQueryAllowed.union(CharacterSet(charactersIn: "%"))
            if rawQuery.rangeOfCharacter(from: allowed.inverted) == nil {
                components.percentEncodedQuery = rawQuery
            } else {
                components.query = rawQuery
            }
        }
        if !query.isEmpty {
            let existing = components.percentEncodedQuery ?? ""
            var extra = URLComponents()
            extra.queryItems = query
            let encoded = escapePlus(extra.percentEncodedQuery) ?? ""
            components.percentEncodedQuery = existing.isEmpty ? encoded : existing + "&" + encoded
        }
        return components.url
    }

    /// URLComponents leaves '+' literal in queries; Starlette decodes it as a space.
    static func escapePlus(_ percentEncodedQuery: String?) -> String? {
        percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
    }

    // MARK: - Session token (Keychain, one entry per server)

    private static var keychainAccount: String {
        keychainAccountBase + "@" + serverScope
    }

    private static func keychainRead(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
           let data = item as? Data,
           let token = String(data: data, encoding: .utf8),
           !token.isEmpty {
            return token
        }
        return nil
    }

    private static func keychainDelete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }

    static func readToken() -> String? {
        if let token = keychainRead(account: keychainAccount) {
            return token
        }
        // One-time migration from the unscoped Keychain entry.
        if let unscoped = keychainRead(account: keychainAccountBase) {
            writeToken(unscoped)
            keychainDelete(account: keychainAccountBase)
            return unscoped
        }
        // One-time migration from the old UserDefaults slot.
        if let legacy = UserDefaults.standard.string(forKey: legacyTokenKey), !legacy.isEmpty {
            writeToken(legacy)
            UserDefaults.standard.removeObject(forKey: legacyTokenKey)
            return legacy
        }
        return nil
    }

    static func writeToken(_ token: String) {
        clearToken()
        guard !token.isEmpty else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
            kSecValueData as String: Data(token.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    static func clearToken() {
        keychainDelete(account: keychainAccount)
        UserDefaults.standard.removeObject(forKey: legacyTokenKey)
    }

    // MARK: - Web bridges (mirror frontend/src/router.js — history mode, no hash)

    static func webURL(path: String, query: [String: String] = [:]) -> URL {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        let base = baseURL.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let route = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [base, route].filter { !$0.isEmpty }.joined(separator: "/")
        let items = query
            .filter { !$0.value.isEmpty }
            .sorted { $0.key < $1.key }
            .map { URLQueryItem(name: $0.key, value: $0.value) }
        components.queryItems = items.isEmpty ? nil : items
        if !items.isEmpty {
            components.percentEncodedQuery = escapePlus(components.percentEncodedQuery)
        }
        return components.url ?? baseURL
    }

    static func webCompanyURL(id: String) -> URL {
        webURL(path: id)
    }

    static func webReportURL(id: String) -> URL {
        webURL(path: "reports", query: ["id": id])
    }

    static func webCompanyMemoURL(companyId: String, reportId: String) -> URL {
        webURL(path: companyId, query: ["tab": "memo", "report": reportId])
    }

    static func webQuoteURL(ticker: String) -> URL {
        webURL(path: "market-radar", query: ["ticker": ticker.uppercased()])
    }

    static func webNewsURL() -> URL {
        webURL(path: "news-desk")
    }

    static func openInBrowser(_ url: URL) {
        #if canImport(AppKit)
        NSWorkspace.shared.open(url)
        #endif
    }
}
