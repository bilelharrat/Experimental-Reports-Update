import SwiftUI

@main
struct BSHResearchApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var session = SessionStore()
    @StateObject private var language = LanguageStore()
    @StateObject private var appearance = AppearanceStore()
    @StateObject private var desk = DeskStore()
    @StateObject private var askPersona = AskPersonaStore()
    @StateObject private var router = DeepLinkRouter()
    @StateObject private var dataCache = AppDataCache.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(language)
                .environmentObject(appearance)
                .environmentObject(desk)
                .environmentObject(askPersona)
                .environmentObject(router)
                .environmentObject(dataCache)
                .environmentObject(ResearchDeskStore.shared)
                .task {
                    async let cachePreload: Void = dataCache.preloadAll(lang: language.language)
                    async let deskPreload: Void = ResearchDeskStore.shared.loadAll()
                    _ = await (cachePreload, deskPreload)
                }
                // Read `language.language` (not only the computed locale) so App
                // body invalidates; `.id` forces TabView chrome to rebuild with
                // fresh `language.t(...)` strings after an in-app switch.
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(language.language)
                .preferredColorScheme(appearance.appearance.colorScheme)
                .onOpenURL { url in
                    if let link = DeepLink(url: url) {
                        router.pending = link
                    }
                }
                .onReceive(NotificationCenter.default.publisher(for: .bshOpenDeepLink)) { note in
                    if let link = note.object as? DeepLink {
                        router.pending = link
                    }
                }
        }

        WindowGroup(id: "reports") {
            ReportsWindowRootView()
                .environmentObject(session)
                .environmentObject(language)
                .environmentObject(appearance)
                .environmentObject(desk)
                .environmentObject(askPersona)
                .environmentObject(router)
                .environmentObject(dataCache)
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(language.language)
                .preferredColorScheme(appearance.appearance.colorScheme)
        }

        WindowGroup(id: "report-detail", for: String.self) { $reportId in
            if let id = reportId {
                NavigationStack {
                    ReportDetailView(reportId: id)
                        .id(id)
                }
                .environmentObject(session)
                .environmentObject(language)
                .environmentObject(appearance)
                .environmentObject(desk)
                .environmentObject(askPersona)
                .environmentObject(router)
                .environmentObject(dataCache)
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(language.language)
                .preferredColorScheme(appearance.appearance.colorScheme)
            }
        }
    }
}
