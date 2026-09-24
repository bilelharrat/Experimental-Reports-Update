import SwiftUI
import UIKit
import XCTest
@testable import BSHResearch

@MainActor
final class BSHDesignTests: XCTestCase {
    private func freshDefaults() -> UserDefaults {
        let suite = "design-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return defaults
    }

    /// The color's channels on the 0–255 scale, resolved in the given appearance.
    private func rgb(_ color: Color, _ style: UIUserInterfaceStyle) -> [Int] {
        let resolved = UIColor(color).resolvedColor(with: UITraitCollection(userInterfaceStyle: style))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        resolved.getRed(&r, green: &g, blue: &b, alpha: &a)
        return [r, g, b].map { Int(($0 * 255).rounded()) }
    }

    func testBureauIsTheDefaultAndTheKeyIsTheWebsites() {
        XCTAssertEqual(BSHDesign.defaultDesign, .bureau)
        XCTAssertEqual(BSHDesign.storageKey, "bsh.research.design")
        XCTAssertEqual(BSHDesign.stored(in: freshDefaults()), .bureau)
    }

    func testAnUnknownStoredDesignFallsBackToBureau() {
        let defaults = freshDefaults()
        defaults.set("reactor", forKey: BSHDesign.storageKey)
        XCTAssertEqual(BSHDesign.stored(in: defaults), .bureau)
    }

    func testTheStoreRemembersTheChoiceAndAppliesItBeforeTheRebuild() {
        let saved = BSHDesign.active
        defer { BSHDesign.active = saved }
        let defaults = freshDefaults()
        var applied: [BSHDesign] = []

        let store = BSHDesignStore(defaults: defaults, onApply: { applied.append($0) })
        XCTAssertEqual(store.design, .bureau)
        store.design = .folio

        XCTAssertEqual(defaults.string(forKey: BSHDesign.storageKey), "folio")
        XCTAssertEqual(BSHDesign.active, .folio)
        XCTAssertEqual(applied, [.bureau, .folio], "applied at launch, then on the change")
        XCTAssertEqual(BSHDesignStore(defaults: defaults).design, .folio, "the next launch reads it back")
    }

    func testTokensFollowTheActiveDesign() {
        let saved = BSHDesign.active
        defer { BSHDesign.active = saved }

        BSHDesign.active = .bureau
        XCTAssertEqual(rgb(.dsCanvas, .light), [247, 244, 236], "Bureau's ivory sheet")
        XCTAssertEqual(rgb(.dsCanvas, .dark), [21, 29, 26], "Bureau's green slate at night")
        XCTAssertEqual(rgb(.dsAccent, .light), [148, 112, 47], "brass")
        XCTAssertEqual(MacDS.cardRadius, 14)

        BSHDesign.active = .folio
        XCTAssertEqual(rgb(.dsCanvas, .light), [244, 242, 237], "Folio's paper")
        XCTAssertEqual(rgb(.dsAccent, .light), [38, 60, 212], "ultramarine")
        XCTAssertEqual(MacDS.cardRadius, 6)

        BSHDesign.active = .glass
        XCTAssertEqual(rgb(.dsCard, .light), rgb(Color(uiColor: .secondarySystemGroupedBackground), .light))
        XCTAssertEqual(rgb(.dsPage, .dark), rgb(Color(uiColor: .systemBackground), .dark))
        XCTAssertEqual(MacDS.cardRadius, 14)
    }

    func testTheDesignsFacesAreAvailable() {
        BSHType.registerBundledFonts()
        XCTAssertNotNil(UIFont(name: BSHType.bureauSerif, size: 17), "Instrument Serif ships in the bundle")
        XCTAssertNotNil(UIFont(name: BSHType.bureauSerifItalic, size: 17))
        XCTAssertNotNil(UIFont(name: BSHType.folioSerif, size: 17), "Iowan Old Style ships with iOS")
        XCTAssertNotNil(UIFont(name: BSHType.folioSerifItalic, size: 17))
    }

    func testAJoinedTabFlaresIntoThePageAlongItsJoin() {
        let rect = CGRect(x: 0, y: 0, width: 60, height: 50)

        let hanging = BSHJoinedTabShape(join: .top, radius: 10).path(in: rect).boundingRect
        XCTAssertEqual(hanging.minX, -10, accuracy: 0.01)
        XCTAssertEqual(hanging.maxX, 70, accuracy: 0.01)
        XCTAssertEqual(hanging.minY, 0, accuracy: 0.01)
        XCTAssertEqual(hanging.maxY, 50, accuracy: 0.01)

        let reaching = BSHJoinedTabShape(join: .trailing, radius: 10).path(in: rect).boundingRect
        XCTAssertEqual(reaching.minY, -10, accuracy: 0.01)
        XCTAssertEqual(reaching.maxY, 60, accuracy: 0.01)
        XCTAssertEqual(reaching.minX, 0, accuracy: 0.01)
        XCTAssertEqual(reaching.maxX, 60, accuracy: 0.01)
    }

    func testTheDesignSettingIsLocalized() {
        let keys = ["settings.design", "settings.design_help", "settings.design_bureau", "settings.design_folio", "settings.design_glass"]
        for key in keys {
            for lang in AppLanguage.allCases {
                let value = L10n.string(key, lang: lang)
                XCTAssertNotEqual(value, key, "\(lang.rawValue) missing \(key)")
                XCTAssertFalse(value.isEmpty, "\(lang.rawValue) empty \(key)")
            }
        }
        for lang in AppLanguage.allCases where lang != .en {
            XCTAssertNotEqual(L10n.string("settings.design_help", lang: lang), L10n.string("settings.design_help", lang: .en), "\(lang.rawValue) help still English")
        }
        XCTAssertEqual(L10n.string("settings.design_bureau", lang: .zh), "Bureau 书案")
    }
}
