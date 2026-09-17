import Foundation
import SwiftUI

/// One row on the tour's hero card: what the app does, at a glance.
struct WelcomeTourRow: Identifiable, Equatable {
    let id: String
    let symbol: String?
    let titleKey: String
    let bodyKey: String
    var usesWarrenPortrait: Bool { symbol == nil }
}

struct WelcomeTourTip: Identifiable, Equatable {
    let textKey: String
    var symbol: String? = nil
    var id: String { textKey }
}

/// One step of the walkthrough.
///
/// The hero step is the iOS "Welcome to" card. Every step after it moves the
/// app to `tab` and points at `anchor` — the real tab button, not a picture of
/// one — the way Apple's in-app tours (Final Cut and Logic for iPad, Freeform,
/// Swift Playgrounds, Tips) walk you through the interface itself.
struct WelcomeTourPage: Identifiable, Equatable {
    let id: String
    let symbol: String?
    let titleKey: String
    let bodyKey: String
    var tips: [WelcomeTourTip] = []
    /// The desk this step is about. `nil` stays wherever the tour already is.
    var tab: AppTab? = nil
    /// Identifier of the control to spotlight, published by `welcomeTourAnchor`.
    var anchor: String? = nil
    var isHero: Bool { id == "welcome" }
    var usesWarrenPortrait: Bool { id == "warren" }

    var localizedKeys: [String] {
        [titleKey, bodyKey] + tips.map(\.textKey)
    }
}

enum WelcomeTourCatalog {
    /// Anchor id for a desk's button in the travel bar / sidebar.
    static func tabAnchor(_ tab: AppTab) -> String { "tab.\(tab.rawValue)" }
    /// Anchor id for the Ask Warren control in the navigation bar.
    static let warrenAnchor = "chrome.warren"

    static let rows: [WelcomeTourRow] = [
        WelcomeTourRow(id: "home", symbol: "magnifyingglass", titleKey: "welcome.row_home_title", bodyKey: "welcome.row_home_body"),
        WelcomeTourRow(id: "memo", symbol: "doc.text", titleKey: "welcome.row_memo_title", bodyKey: "welcome.row_memo_body"),
        WelcomeTourRow(id: "markets", symbol: "chart.line.uptrend.xyaxis", titleKey: "welcome.row_markets_title", bodyKey: "welcome.row_markets_body"),
        WelcomeTourRow(id: "warren", symbol: nil, titleKey: "welcome.row_warren_title", bodyKey: "welcome.row_warren_body"),
        WelcomeTourRow(id: "widgets", symbol: "applewatch", titleKey: "welcome.row_widgets_title", bodyKey: "welcome.row_widgets_body"),
    ]

    /// iPad adds a step on its own chrome: the landscape sidebar, windows and Apple Pencil.
    static func pages(isPad: Bool) -> [WelcomeTourPage] {
        var pages: [WelcomeTourPage] = [
            WelcomeTourPage(id: "welcome", symbol: nil, titleKey: "welcome.title", bodyKey: "welcome.subtitle"),
        ]
        if isPad {
            pages.append(WelcomeTourPage(
                id: "ipad",
                symbol: "ipad.landscape",
                titleKey: "welcome.ipad_title",
                bodyKey: "welcome.ipad_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.ipad_tip_sidebar", symbol: "sidebar.left"),
                    WelcomeTourTip(textKey: "welcome.ipad_tip_windows", symbol: "rectangle.split.2x1"),
                    WelcomeTourTip(textKey: "welcome.ipad_tip_pencil", symbol: "pencil.tip"),
                ]
            ))
        }
        pages += [
            WelcomeTourPage(
                id: "home",
                symbol: "building.2",
                titleKey: "welcome.home_title",
                bodyKey: "welcome.home_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.home_tip_follow", symbol: "star"),
                    WelcomeTourTip(textKey: "welcome.home_tip_recent", symbol: "clock"),
                ],
                tab: .home,
                anchor: tabAnchor(.home)
            ),
            WelcomeTourPage(
                id: "reports",
                symbol: "doc.text",
                titleKey: "welcome.reports_title",
                bodyKey: "welcome.reports_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.reports_tip_server", symbol: "server.rack"),
                    WelcomeTourTip(textKey: "welcome.reports_tip_languages", symbol: "character.book.closed"),
                ],
                tab: .reports,
                anchor: tabAnchor(.reports)
            ),
            WelcomeTourPage(
                id: "markets",
                symbol: "chart.line.uptrend.xyaxis",
                titleKey: "welcome.markets_title",
                bodyKey: "welcome.markets_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.markets_tip_pulse", symbol: "waveform.path.ecg"),
                    WelcomeTourTip(textKey: "welcome.markets_tip_news", symbol: "newspaper"),
                    WelcomeTourTip(textKey: "welcome.markets_tip_sync", symbol: "arrow.triangle.2.circlepath"),
                ],
                tab: .market,
                anchor: tabAnchor(.market)
            ),
            WelcomeTourPage(
                id: "warren",
                symbol: nil,
                titleKey: "welcome.warren_title",
                bodyKey: "welcome.warren_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.warren_tip_dictate", symbol: "mic"),
                    WelcomeTourTip(textKey: "welcome.warren_tip_name", symbol: "quote.bubble"),
                    WelcomeTourTip(textKey: "welcome.warren_tip_persona", symbol: "person.2"),
                ],
                tab: .research,
                anchor: warrenAnchor
            ),
            WelcomeTourPage(
                id: "widgets",
                symbol: "applewatch",
                titleKey: "welcome.widgets_title",
                bodyKey: "welcome.widgets_body",
                tips: [
                    WelcomeTourTip(textKey: "welcome.widgets_tip_widget", symbol: "square.grid.2x2"),
                    WelcomeTourTip(textKey: "welcome.widgets_tip_watch", symbol: "applewatch.watchface"),
                ]
            ),
        ]
        return pages
    }
}

/// Shows the walkthrough once per install, and again when its content is revised
/// (bump `currentVersion`), the way iOS re-shows "What's New" after a major update.
///
/// The store also owns where the tour is, because the app's tab selection
/// follows it: the walkthrough moves the real app rather than describing it.
@MainActor
final class WelcomeTourStore: ObservableObject {
    /// v2: the tour walks the app instead of paging through cards.
    static let currentVersion = 2
    static let seenVersionKey = "bsh.welcome.versionSeen"

    @Published var isPresented = false
    @Published private(set) var stepIndex = 0
    @Published private(set) var pages: [WelcomeTourPage]

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard, isPad: Bool = AdaptiveLayout.isPad) {
        self.defaults = defaults
        self.pages = WelcomeTourCatalog.pages(isPad: isPad)
    }

    var seenVersion: Int {
        defaults.integer(forKey: Self.seenVersionKey)
    }

    var needsPresentation: Bool {
        seenVersion < Self.currentVersion
    }

    var current: WelcomeTourPage? {
        pages.indices.contains(stepIndex) ? pages[stepIndex] : pages.first
    }

    var isFirstStep: Bool { stepIndex == 0 }
    var isLastStep: Bool { stepIndex >= pages.count - 1 }

    /// The desk the app should be showing for the current step, if any.
    var focusedTab: AppTab? { current?.tab }

    /// Rebuild the catalog when the app moves between iPhone and iPad chrome.
    func refreshLayout(isPad: Bool) {
        let rebuilt = WelcomeTourCatalog.pages(isPad: isPad)
        guard rebuilt != pages else { return }
        let currentID = current?.id
        pages = rebuilt
        if let currentID, let index = rebuilt.firstIndex(where: { $0.id == currentID }) {
            stepIndex = index
        } else {
            stepIndex = min(stepIndex, rebuilt.count - 1)
        }
    }

    @discardableResult
    func presentIfNeeded() -> Bool {
        guard !isPresented, needsPresentation else { return false }
        stepIndex = 0
        isPresented = true
        return true
    }

    func goTo(_ index: Int) {
        stepIndex = min(max(0, index), pages.count - 1)
    }

    /// Continue. On the last step this finishes the tour.
    func advance() {
        if isLastStep {
            complete()
        } else {
            stepIndex += 1
        }
    }

    func back() {
        guard stepIndex > 0 else { return }
        stepIndex -= 1
    }

    /// Any way out counts as seen: Get started, Skip, or dismissing the overlay.
    func complete() {
        defaults.set(Self.currentVersion, forKey: Self.seenVersionKey)
        isPresented = false
        stepIndex = 0
    }

    func replay() {
        stepIndex = 0
        isPresented = true
    }
}
