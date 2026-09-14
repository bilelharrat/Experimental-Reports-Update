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
    private static let keychainAccount = "bsh.research.session.mac"

    static var baseURL: URL {
        if let override = UserDefaults.standard.string(forKey: baseURLKey),
           let url = URL(string: override), !override.isEmpty {
            return url
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = URL(string: plist), !plist.isEmpty {
            return url
        }
        return URL(string: "http://127.0.0.1:8010")!
    }

    static var apiRoot: URL {
        baseURL.appendingPathComponent("api")
    }

    /// True unless the user flipped "Require User Authentication" in Settings.
    /// With the dev server's `BSH_ALLOW_ANON_DEV=1` the API accepts unauthenticated
    /// calls as a local admin; the login sheet only appears when the server says 401.
    static var bypassLogin: Bool {
        if UserDefaults.standard.object(forKey: bypassLoginKey) as? Bool == true {
            return false
        }
        return true
    }

    static func saveBaseURL(_ raw: String) {
        UserDefaults.standard.set(
            raw.trimmingCharacters(in: .whitespacesAndNewlines),
            forKey: baseURLKey
        )
    }

    // MARK: - Session token (Keychain)

    static func readToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
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
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
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
