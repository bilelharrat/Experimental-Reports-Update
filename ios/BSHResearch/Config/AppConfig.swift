import Foundation

enum AppConfig {
    /// API origin. Override via Info.plist `BSHBaseURL` or UserDefaults `bsh.baseURL`.
    /// Local default matches `./run.sh` (uvicorn on 8010). Production mounts under `/research`.
    static var baseURL: URL {
        if let override = UserDefaults.standard.string(forKey: "bsh.baseURL"),
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

    /// Skip the login screen. Local backends run with ``BSH_ALLOW_ANON_DEV=1``,
    /// so the API accepts requests with no Bearer token. Flip off in Settings
    /// (or set UserDefaults ``bsh.requireLogin`` = true) when you want real auth.
    static var bypassLogin: Bool {
        if UserDefaults.standard.object(forKey: "bsh.requireLogin") as? Bool == true {
            return false
        }
        return true
    }
}
