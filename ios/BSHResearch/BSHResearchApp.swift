import SwiftUI

@main
struct BSHResearchApp: App {
    @StateObject private var session = SessionStore()
    @StateObject private var language = LanguageStore()
    @StateObject private var appearance = AppearanceStore()
    @StateObject private var desk = DeskStore()
    @StateObject private var router = DeepLinkRouter()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(language)
                .environmentObject(appearance)
                .environmentObject(desk)
                .environmentObject(router)
                .environment(\.locale, language.locale)
                .preferredColorScheme(appearance.appearance.colorScheme)
                .onOpenURL { url in
                    if let link = DeepLink(url: url) {
                        router.pending = link
                    }
                }
        }
    }
}
