import SwiftUI

@main
struct BSHResearchMacApp: App {
    var body: some Scene {
        WindowGroup("BSH Research") {
            MacRootView()
                .frame(minWidth: 1100, minHeight: 700)
        }
        .defaultSize(width: 1280, height: 820)
    }
}
