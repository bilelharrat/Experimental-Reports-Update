import SwiftUI

struct RootView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        Group {
            if session.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: session.isAuthenticated)
    }
}

struct MainTabView: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var router: DeepLinkRouter
    @State private var tab = 0

    var body: some View {
        TabView(selection: $tab) {
            HomeView()
                .tabItem { Label(language.t("tab.home"), systemImage: "house") }
                .tag(0)
            NewsView()
                .tabItem { Label(language.t("tab.news"), systemImage: "newspaper") }
                .tag(1)
            MarketView()
                .tabItem { Label(language.t("tab.market"), systemImage: "chart.line.uptrend.xyaxis") }
                .tag(2)
            PulseView()
                .tabItem { Label(language.t("tab.pulse"), systemImage: "flame") }
                .tag(3)
            SettingsView()
                .tabItem { Label(language.t("tab.settings"), systemImage: "gearshape") }
                .tag(4)
        }
        .onChange(of: router.pending) { _, link in
            // Home owns the deep-link destinations; make sure it's frontmost.
            if link != nil { tab = 0 }
        }
    }
}
