import XCTest
@testable import BSHResearch

@MainActor
final class WelcomeTourTests: XCTestCase {
    private func freshDefaults() -> UserDefaults {
        let suite = "welcome-tour-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return defaults
    }

    func testFreshInstallPresentsOnceAndRemembersCompletion() {
        let defaults = freshDefaults()
        let store = WelcomeTourStore(defaults: defaults, isPad: false)
        XCTAssertTrue(store.needsPresentation)
        XCTAssertTrue(store.presentIfNeeded())
        XCTAssertTrue(store.isPresented)
        XCTAssertFalse(store.presentIfNeeded(), "an open tour must not be re-triggered")

        store.complete()
        XCTAssertFalse(store.isPresented)
        XCTAssertEqual(defaults.integer(forKey: WelcomeTourStore.seenVersionKey), WelcomeTourStore.currentVersion)
        XCTAssertFalse(store.needsPresentation)
        XCTAssertFalse(store.presentIfNeeded())
    }

    func testOlderSeenVersionPresentsAgain() {
        let defaults = freshDefaults()
        defaults.set(WelcomeTourStore.currentVersion - 1, forKey: WelcomeTourStore.seenVersionKey)
        let store = WelcomeTourStore(defaults: defaults, isPad: false)
        XCTAssertTrue(store.presentIfNeeded())
    }

    func testReplayPresentsWithoutTouchingTheSeenVersion() {
        let defaults = freshDefaults()
        let store = WelcomeTourStore(defaults: defaults, isPad: false)
        store.complete()
        store.replay()
        XCTAssertTrue(store.isPresented)
        XCTAssertEqual(defaults.integer(forKey: WelcomeTourStore.seenVersionKey), WelcomeTourStore.currentVersion)
    }

    func testIPadGetsItsOwnPageRightAfterTheWelcome() {
        let phone = WelcomeTourCatalog.pages(isPad: false)
        let pad = WelcomeTourCatalog.pages(isPad: true)
        XCTAssertEqual(phone.first?.id, "welcome")
        XCTAssertEqual(phone.last?.id, "widgets")
        XCTAssertEqual(pad.count, phone.count + 1)
        XCTAssertEqual(pad[1].id, "ipad")
        XCTAssertFalse(phone.contains { $0.id == "ipad" })
        XCTAssertTrue(phone.contains { $0.usesWarrenPortrait })
    }

    func testEveryStepAfterTheWelcomeOpensTheScreenItExplains() {
        for isPad in [false, true] {
            let pages = WelcomeTourCatalog.pages(isPad: isPad)
            XCTAssertTrue(pages[0].isHero)
            XCTAssertNil(pages[0].tab, "the welcome card must not move the app")
            // Every step that names a desk carries the tab the app should show.
            XCTAssertEqual(pages.first { $0.id == "home" }?.tab, .home)
            XCTAssertEqual(pages.first { $0.id == "reports" }?.tab, .reports)
            XCTAssertEqual(pages.first { $0.id == "markets" }?.tab, .market)
            XCTAssertEqual(pages.first { $0.id == "warren" }?.tab, .research)
            // And the ones about a desk point at that desk's real control.
            XCTAssertEqual(pages.first { $0.id == "home" }?.anchor, WelcomeTourCatalog.tabAnchor(.home))
            XCTAssertEqual(pages.first { $0.id == "reports" }?.anchor, WelcomeTourCatalog.tabAnchor(.reports))
            XCTAssertEqual(pages.first { $0.id == "markets" }?.anchor, WelcomeTourCatalog.tabAnchor(.market))
        }
    }

    func testWalkingForwardAndBackTracksTheFocusedDesk() {
        let store = WelcomeTourStore(defaults: freshDefaults(), isPad: false)
        store.presentIfNeeded()
        XCTAssertTrue(store.isFirstStep)
        XCTAssertNil(store.focusedTab, "the welcome card leaves the app where it is")

        store.advance()
        XCTAssertEqual(store.current?.id, "home")
        XCTAssertEqual(store.focusedTab, .home)

        store.advance()
        XCTAssertEqual(store.focusedTab, .reports)

        store.back()
        XCTAssertEqual(store.focusedTab, .home)

        // Back from the first step is a no-op, not a crash.
        store.back()
        store.back()
        XCTAssertTrue(store.isFirstStep)
    }

    func testAdvancingOffTheLastStepFinishesTheTour() {
        let defaults = freshDefaults()
        let store = WelcomeTourStore(defaults: defaults, isPad: false)
        store.presentIfNeeded()
        while !store.isLastStep { store.advance() }
        XCTAssertTrue(store.isPresented)

        store.advance()
        XCTAssertFalse(store.isPresented)
        XCTAssertEqual(defaults.integer(forKey: WelcomeTourStore.seenVersionKey), WelcomeTourStore.currentVersion)
        XCTAssertEqual(store.stepIndex, 0, "a replay starts at the welcome card")
    }

    func testSwitchingToPadChromeKeepsTheStepYouAreOn() {
        let store = WelcomeTourStore(defaults: freshDefaults(), isPad: false)
        store.presentIfNeeded()
        store.advance()
        store.advance()
        let before = store.current?.id
        XCTAssertEqual(before, "reports")

        // Rotating an iPad into landscape rebuilds the catalog mid-tour.
        store.refreshLayout(isPad: true)
        XCTAssertEqual(store.current?.id, before)
        XCTAssertTrue(store.pages.contains { $0.id == "ipad" })
    }

    func testEveryTourStringIsLocalizedInEnglishAndChinese() {
        var keys = WelcomeTourCatalog.pages(isPad: true).flatMap(\.localizedKeys)
        keys += WelcomeTourCatalog.rows.flatMap { [$0.titleKey, $0.bodyKey] }
        keys += ["welcome.close", "welcome.back", "welcome.continue", "welcome.get_started", "welcome.replay_hint", "welcome.page_of", "settings.welcome_tour"]
        for key in keys {
            for lang in [AppLanguage.en, .zh] {
                let value = L10n.string(key, lang: lang)
                XCTAssertNotEqual(value, key, "\(lang.rawValue) missing \(key)")
                XCTAssertFalse(value.isEmpty, "\(lang.rawValue) empty \(key)")
            }
            XCTAssertNotEqual(L10n.string(key, lang: .zh), L10n.string(key, lang: .en), "zh \(key) still English")
        }
    }
}
