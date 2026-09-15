import Foundation
import Combine
import SwiftUI

/// UI / content preference. Ordered as the world's most-spoken languages
/// (total speakers): English, Mandarin, Hindi, Spanish, French, Arabic,
/// Bengali, Portuguese, Russian, Urdu. Every case has a full L10n chrome
/// map; the same code also drives generated content (news briefs, etc.).
enum AppLanguage: String, CaseIterable, Identifiable, Hashable {
    case en, zh, hi, es, fr, ar, bn, pt, ru, ur

    var id: String { rawValue }

    /// Native endonym for the Settings picker.
    var label: String {
        switch self {
        case .en: return "English"
        case .zh: return "中文"
        case .hi: return "हिन्दी"
        case .es: return "Español"
        case .fr: return "Français"
        case .ar: return "العربية"
        case .bn: return "বাংলা"
        case .pt: return "Português"
        case .ru: return "Русский"
        case .ur: return "اردو"
        }
    }

    var localeIdentifier: String {
        switch self {
        case .en: return "en"
        case .zh: return "zh-Hans"
        case .hi: return "hi"
        case .es: return "es"
        case .fr: return "fr"
        case .ar: return "ar"
        case .bn: return "bn"
        case .pt: return "pt"
        case .ru: return "ru"
        case .ur: return "ur"
        }
    }

    /// Prefer Chinese bilingual fields only for 中文; everything else reads
    /// the English/bare channel (which carries the requested-language text
    /// for generated briefings).
    var prefersChineseContent: Bool { self == .zh }
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
    /// Avoid `@Published` + `didSet` — that combo can skip `objectWillChange`
    /// for some Picker/Binding write paths, leaving chrome stuck on the old language.
    @Published private(set) var language: AppLanguage

    var locale: Locale { Locale(identifier: language.localeIdentifier) }

    init() {
        let raw = UserDefaults.standard.string(forKey: "bsh.language") ?? "en"
        language = AppLanguage(rawValue: raw) ?? .en
    }

    func setLanguage(_ next: AppLanguage) {
        guard next != language else { return }
        language = next
        UserDefaults.standard.set(next.rawValue, forKey: "bsh.language")
    }

    /// Binding for Settings (and any other) pickers.
    var languageBinding: Binding<AppLanguage> {
        Binding(
            get: { self.language },
            set: { self.setLanguage($0) }
        )
    }

    func t(_ key: String) -> String {
        L10n.string(key, lang: language)
    }
}

enum DeepLink: Equatable {
    case ticker(String)
    case company(String)
    case report(String)
    case tab(AppTab)
    case settings

    /// bshresearch://ticker/NVDA · bshresearch://company/zainar-inc
    /// bshresearch://report/abc123 · bshresearch://tab/news · bshresearch://settings
    init?(url: URL) {
        guard url.scheme == "bshresearch", let kind = url.host else { return nil }
        if kind == "settings" {
            self = .settings
            return
        }
        let value = url.pathComponents.count > 1
            ? url.pathComponents[1]
            : url.host.map { _ in url.lastPathComponent } ?? ""
        guard !value.isEmpty else { return nil }
        switch kind {
        case "ticker": self = .ticker(value.uppercased())
        case "company": self = .company(value)
        case "report": self = .report(value)
        case "tab":
            if value.lowercased() == "settings" {
                self = .settings
            } else if let tab = AppTab(rawValue: value.lowercased()) {
                self = .tab(tab)
            } else {
                return nil
            }
        default: return nil
        }
    }
}

enum AppTab: String, CaseIterable, Identifiable, Hashable {
    case home, reports, news, pulse, market

    var id: String { rawValue }

    var index: Int {
        switch self {
        case .home: return 0
        case .reports: return 1
        case .news: return 2
        case .pulse: return 3
        case .market: return 4
        }
    }

    static func from(index: Int) -> AppTab {
        allCases.first { $0.index == index } ?? .home
    }

    var titleKey: String {
        switch self {
        case .home: return "tab.home"
        case .reports: return "tab.reports"
        case .news: return "tab.news"
        case .pulse: return "tab.pulse"
        case .market: return "tab.market"
        }
    }

    /// SF Symbol for tabs that don't use a custom asset. Pulse uses `PulseECGTabIcon`.
    var systemImage: String? {
        switch self {
        case .home: return "house"
        case .reports: return "doc.text"
        case .news: return "newspaper"
        case .pulse: return nil
        case .market: return "chart.line.uptrend.xyaxis"
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
    @Published private(set) var role: String?
    @Published private(set) var permissions: Set<String> = []
    @Published var lastError: String?

    var canWriteDesk: Bool {
        permissions.contains("desk:write") || permissions.contains("memo:edit") || role == "admin" || role == "analyst" || role == "partner" || role == "research_ops" || (AppConfig.bypassLogin && TokenStore.read() == nil)
    }

    var isReadOnly: Bool {
        !canWriteDesk
    }

    var roleLabel: String {
        if AppConfig.bypassLogin, TokenStore.read() == nil { return "local analyst" }
        return role ?? "guest"
    }

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
            await refreshMe()
            await AppDataCache.shared.invalidateAndReload()
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
        role = nil
        permissions = []
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
            role = me.role
            permissions = Set(me.permissions ?? [])
            isAuthenticated = true
        } catch {
            if case APIError.unauthorized = error {
                if AppConfig.bypassLogin {
                    name = "Local dev"
                    role = "analyst"
                    permissions = ["desk:write", "memo:edit", "memo:export", "tasks:action"]
                    isAuthenticated = true
                } else {
                    isAuthenticated = false
                    role = nil
                    permissions = []
                }
            }
        }
    }
}
