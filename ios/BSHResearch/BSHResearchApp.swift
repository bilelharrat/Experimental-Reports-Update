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
    @StateObject private var welcomeTour = WelcomeTourStore()
    /// Summit Glass, Bureau (and its desk) or Folio. Every window rebuilds when it
    /// changes, so the design's tokens re-resolve everywhere at once; UIKit's bars are
    /// pointed at the new design first.
    @StateObject private var design = BSHDesignStore(onApply: { BSHUIKitChrome.apply($0) })
    @StateObject private var settings = SettingsPresenter()

    init() {
        BSHType.registerBundledFonts()
    }

    /// What a window's content is rebuilt on: the language (fresh `language.t(...)`
    /// strings in TabView chrome) and the design with Bureau's desk (fresh tokens).
    private var rootIdentity: String {
        "\(language.language.rawValue)-\(design.identity)"
    }

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
                .environmentObject(welcomeTour)
                .environmentObject(ResearchDeskStore.shared)
                .environmentObject(design)
                .environmentObject(settings)
                .bshDesignRoot()
                .task {
                    async let cachePreload: Void = dataCache.preloadAll(lang: language.language)
                    async let deskPreload: Void = ResearchDeskStore.shared.loadAll()
                    _ = await (cachePreload, deskPreload)
                }
                // Read `language.language` (not only the computed locale) so App
                // body invalidates; `.id` forces TabView chrome to rebuild with
                // fresh `language.t(...)` strings after an in-app switch, and every
                // token to re-resolve after a design switch.
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(rootIdentity)
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
                // Settings hangs above the rebuilt content, so choosing a language, a
                // design or Bureau's desk rebuilds it in place and keeps it open.
                .sheet(isPresented: $settings.isPresented) {
                    SettingsView()
                        .environmentObject(session)
                        .environmentObject(language)
                        .environmentObject(appearance)
                        .environmentObject(desk)
                        .environmentObject(askPersona)
                        .environmentObject(router)
                        .environmentObject(dataCache)
                        .environmentObject(welcomeTour)
                        .environmentObject(ResearchDeskStore.shared)
                        .environmentObject(design)
                        .environmentObject(settings)
                        .bshDesignRoot()
                        .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                        .id(rootIdentity)
                        .bshSheetChrome()
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
                .environmentObject(welcomeTour)
                .environmentObject(design)
                .environmentObject(settings)
                .bshDesignRoot()
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(rootIdentity)
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
                .environmentObject(welcomeTour)
                .environmentObject(design)
                .environmentObject(settings)
                .bshDesignRoot()
                .environment(\.locale, Locale(identifier: language.language.localeIdentifier))
                .id(rootIdentity)
                .preferredColorScheme(appearance.appearance.colorScheme)
            }
        }
    }
}
