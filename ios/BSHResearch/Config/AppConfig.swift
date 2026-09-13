import Foundation

enum AppConfig {
    /// API origin. Override via Info.plist `BSHBaseURL` or UserDefaults `bsh.baseURL`.
    /// Local default matches `./run.sh` (uvicorn on 8010). For production / TestFlight
    /// set `BSHBaseURL` to your public HTTPS host (see docs/DISTRIBUTION.md) or type it
    /// in Settings so the phone works with your laptop off.
    static var baseURL: URL {
        #if !targetEnvironment(simulator)
        if let override = AppGroupStore.loadBaseURL(),
           let url = URL(string: override), !override.isEmpty,
           !override.contains("10.0.0.218"),
           !override.contains("localhost"),
           !override.contains("127.0.0.1") {
            return url
        }
        #else
        if let override = AppGroupStore.loadBaseURL(),
           let url = URL(string: override), !override.isEmpty,
           !override.contains("10.0.0.218") {
            return url
        }
        #endif
        if let plist = Bundle.main.object(forInfoDictionaryKey: "BSHBaseURL") as? String,
           let url = URL(string: plist), !plist.isEmpty {
            return url
        }
        return URL(string: "http://192.168.1.181:8010")!
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
