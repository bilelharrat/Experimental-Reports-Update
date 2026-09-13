import SwiftUI

struct ReportsWindowRootView: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var appearance: AppearanceStore

    var body: some View {
        ReportsDeskView()
            .environment(\.embeddedInRootSplit, false)
            .navigationTitle(language.t("reports.title"))
    }
}
