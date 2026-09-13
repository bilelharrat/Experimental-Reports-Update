#if canImport(AppKit)
import AppKit
#endif

enum MacConfig {
    static let baseURLKey = "bsh.baseURL"
    static let tokenKey = "bsh.sessionToken"
    static let bypassLoginKey = "bsh.requireLogin"

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

    static func readToken() -> String? {
        let t = UserDefaults.standard.string(forKey: tokenKey)
        return (t?.isEmpty == false) ? t : nil
    }

    static func writeToken(_ token: String) {
        UserDefaults.standard.set(token, forKey: tokenKey)
    }

    static func clearToken() {
        UserDefaults.standard.removeObject(forKey: tokenKey)
    }

    // MARK: - Web Bridges

    static func webCompanyURL(id: String) -> URL {
        baseURL.appendingPathComponent("#/companies/\(id)")
    }

    static func webReportURL(id: String) -> URL {
        baseURL.appendingPathComponent("#/reports/\(id)")
    }

    static func webQuoteURL(ticker: String) -> URL {
        baseURL.appendingPathComponent("#/market?ticker=\(ticker.uppercased())")
    }

    static func openInBrowser(_ url: URL) {
        #if canImport(AppKit)
        NSWorkspace.shared.open(url)
        #endif
    }
}
