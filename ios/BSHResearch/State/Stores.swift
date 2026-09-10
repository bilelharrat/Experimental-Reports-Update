import Foundation
import Combine
import SwiftUI

enum AppLanguage: String, CaseIterable, Identifiable, Hashable {
    case en, zh
    var id: String { rawValue }
    var label: String { self == .en ? "English" : "中文" }
}

enum AppAppearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }

    func label(lang: AppLanguage) -> String {
        switch self {
        case .system: return L10n.string("settings.appearance_system", lang: lang)
        case .light: return L10n.string("settings.appearance_light", lang: lang)
        case .dark: return L10n.string("settings.appearance_dark", lang: lang)
        }
    }
}

@MainActor
final class LanguageStore: ObservableObject {
    @Published var language: AppLanguage {
        didSet { UserDefaults.standard.set(language.rawValue, forKey: "bsh.language") }
    }

    var locale: Locale { Locale(identifier: language == .zh ? "zh-Hans" : "en") }

    init() {
        let raw = UserDefaults.standard.string(forKey: "bsh.language") ?? "en"
        language = AppLanguage(rawValue: raw) ?? .en
    }

    func t(_ key: String) -> String {
        L10n.string(key, lang: language)
    }
}

enum DeepLink: Equatable {
    case ticker(String)
    case company(String)
    case report(String)

    /// bshresearch://ticker/NVDA · bshresearch://company/zainar-inc · bshresearch://report/abc123
    init?(url: URL) {
        guard url.scheme == "bshresearch" else { return nil }
        let value = url.pathComponents.count > 1
            ? url.pathComponents[1]
            : url.host.map { _ in url.lastPathComponent } ?? ""
        guard let kind = url.host, !value.isEmpty else { return nil }
        switch kind {
        case "ticker": self = .ticker(value.uppercased())
        case "company": self = .company(value)
        case "report": self = .report(value)
        default: return nil
        }
    }
}

@MainActor
final class DeepLinkRouter: ObservableObject {
    @Published var pending: DeepLink?
}

@MainActor
final class AppearanceStore: ObservableObject {
    @Published var appearance: AppAppearance {
        didSet { UserDefaults.standard.set(appearance.rawValue, forKey: "bsh.appearance") }
    }

    /// Convenience for a simple Dark Mode toggle (off → light, on → dark).
    var darkModeEnabled: Bool {
        get { appearance == .dark }
        set { appearance = newValue ? .dark : .light }
    }

    init() {
        let raw = UserDefaults.standard.string(forKey: "bsh.appearance") ?? "light"
        appearance = AppAppearance(rawValue: raw) ?? .light
    }
}

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var isAuthenticated: Bool
    @Published private(set) var email: String?
    @Published private(set) var name: String?
    @Published var lastError: String?

    init() {
        // Local anon-dev: enter the app immediately. A stored token still
        // wins when present (real session); otherwise API calls go unauthed
        // and the server accepts them under BSH_ALLOW_ANON_DEV=1.
        isAuthenticated = AppConfig.bypassLogin || TokenStore.read() != nil
        if isAuthenticated {
            Task { await refreshMe() }
        }
    }

    func enterWithoutSigningIn() {
        lastError = nil
        isAuthenticated = true
        Task { await refreshMe() }
    }

    func signIn(email: String, password: String) async {
        lastError = nil
        do {
            let body = LoginBody(email: email.trimmingCharacters(in: .whitespacesAndNewlines), password: password)
            let res: AuthTokenResponse = try await APIClient.shared.post("auth/token", body: body)
            TokenStore.write(res.token)
            self.email = res.email ?? email
            self.name = res.name
            isAuthenticated = true
        } catch {
            lastError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            isAuthenticated = false
        }
    }

    func signOut() async {
        do { try await APIClient.shared.postEmpty("auth/logout") } catch { /* ignore */ }
        TokenStore.clear()
        email = nil
        name = nil
        // Stay in the app when login is bypassed (local anon-dev).
        isAuthenticated = AppConfig.bypassLogin
        if isAuthenticated {
            await refreshMe()
        }
    }

    func refreshMe() async {
        do {
            let me: AuthMeResponse = try await APIClient.shared.get("auth/me")
            email = me.email
            name = me.name ?? (AppConfig.bypassLogin && TokenStore.read() == nil ? "Local dev" : me.name)
            isAuthenticated = true
        } catch {
            if case APIError.unauthorized = error {
                if AppConfig.bypassLogin {
                    name = "Local dev"
                    isAuthenticated = true
                } else {
                    isAuthenticated = false
                }
            }
        }
    }
}
