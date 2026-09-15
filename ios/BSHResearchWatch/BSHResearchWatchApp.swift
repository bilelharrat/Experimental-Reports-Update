import SwiftUI

@main
struct BSHResearchWatchApp: App {
    @StateObject private var quotes = WatchQuotesStore()

    var body: some Scene {
        WindowGroup {
            WatchRootView()
                .environmentObject(quotes)
                .environment(\.colorScheme, .light)
                .preferredColorScheme(.light)
                .foregroundStyle(Color.black)
                .background(Color.white)
        }
    }
}
