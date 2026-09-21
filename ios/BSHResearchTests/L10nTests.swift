import XCTest
@testable import BSHResearch

final class L10nTests: XCTestCase {
    /// Chrome keys that must change when the user picks a non-English language.
    private let sampleKeys = [
        "tab.home", "tab.news", "tab.market", "tab.pulse", "tab.settings",
        "settings.language", "common.done", "login.title",
        // Settings' account section, signed in or not (with login.title).
        "settings.signed_in_as", "settings.not_signed_in", "settings.sign_out",
    ]

    func testEveryAppLanguageHasDistinctTabChromeFromEnglish() {
        for lang in AppLanguage.allCases where lang != .en {
            for key in sampleKeys {
                let localized = L10n.string(key, lang: lang)
                let english = L10n.string(key, lang: .en)
                XCTAssertFalse(localized.isEmpty, "\(lang.rawValue) \(key) empty")
                XCTAssertNotEqual(
                    localized,
                    english,
                    "\(lang.rawValue) \(key) still English — language picker would look broken"
                )
                XCTAssertNotEqual(localized, key, "\(lang.rawValue) missing key \(key)")
            }
        }
    }

    func testFrenchAndChineseTabLabels() {
        XCTAssertEqual(L10n.string("tab.home", lang: .fr), "Accueil")
        XCTAssertEqual(L10n.string("tab.settings", lang: .fr), "Réglages")
        XCTAssertEqual(L10n.string("tab.home", lang: .zh), "首页")
        XCTAssertEqual(L10n.string("tab.settings", lang: .zh), "设置")
    }

    func testAskInviteTitleLocalizesBeyondEnglishAndChinese() {
        XCTAssertEqual(AskInvestor.buffett.inviteTitle(lang: .fr), "Demander à Warren")
        XCTAssertEqual(AskInvestor.buffett.inviteTitle(lang: .es), "Preguntar a Warren")
        XCTAssertEqual(AskInvestor.buffett.inviteTitle(lang: .zh), "问沃伦")
    }
}
