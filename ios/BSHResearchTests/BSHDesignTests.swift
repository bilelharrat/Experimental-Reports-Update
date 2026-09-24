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

    func testSummitGlassIsTheDefaultAndOnyxIsBureausDesk() {
        XCTAssertEqual(BSHDesign.defaultDesign, .glass)
        XCTAssertEqual(BSHDesign.storageKey, "bsh.research.design")
        XCTAssertEqual(BSHDesign.stored(in: freshDefaults()), .glass)
        XCTAssertEqual(BSHBureauDesk.defaultDesk, .onyx)
        XCTAssertEqual(BSHBureauDesk.storageKey, "bsh.research.bureauDesk")
        XCTAssertEqual(BSHBureauDesk.stored(in: freshDefaults()), .onyx)
    }

    func testUnknownStoredChoicesFallBackToTheDefaults() {
        let defaults = freshDefaults()
        defaults.set("reactor", forKey: BSHDesign.storageKey)
        defaults.set("chartreuse", forKey: BSHBureauDesk.storageKey)
        XCTAssertEqual(BSHDesign.stored(in: defaults), .glass)
        XCTAssertEqual(BSHBureauDesk.stored(in: defaults), .onyx)
    }

    func testTheStoreRemembersTheChoiceAndAppliesItBeforeTheRebuild() {
        let saved = (BSHDesign.active, BSHBureauDesk.active)
        defer { (BSHDesign.active, BSHBureauDesk.active) = saved }
        let defaults = freshDefaults()
        var applied: [BSHDesign] = []

        let store = BSHDesignStore(defaults: defaults, onApply: { applied.append($0) })
        XCTAssertEqual(store.design, .glass)
        XCTAssertEqual(store.bureauDesk, .onyx)
        XCTAssertEqual(store.identity, "glass")

        store.design = .bureau
        store.bureauDesk = .maroon

        XCTAssertEqual(defaults.string(forKey: BSHDesign.storageKey), "bureau")
        XCTAssertEqual(defaults.string(forKey: BSHBureauDesk.storageKey), "maroon")
        XCTAssertEqual(BSHDesign.active, .bureau)
        XCTAssertEqual(BSHBureauDesk.active, .maroon)
        XCTAssertEqual(store.identity, "bureau-maroon", "a desk change rebuilds the windows too")
        XCTAssertEqual(applied, [.glass, .bureau, .bureau], "applied at launch, then on each change")

        let relaunched = BSHDesignStore(defaults: defaults)
        XCTAssertEqual(relaunched.design, .bureau, "the next launch reads it back")
        XCTAssertEqual(relaunched.bureauDesk, .maroon)
    }

    func testOnlyOnyxHasALightDeskAndOnlyByDay() {
        XCTAssertFalse(BSHBureauDesk.onyx.isDark(in: .light))
        XCTAssertTrue(BSHBureauDesk.onyx.isDark(in: .dark))
        for desk in BSHBureauDesk.allCases where desk != .onyx {
            XCTAssertTrue(desk.isDark(in: .light), "\(desk) by day")
            XCTAssertTrue(desk.isDark(in: .dark), "\(desk) by night")
        }
    }

    func testBureausTokensFollowTheDesk() {
        let saved = (BSHDesign.active, BSHBureauDesk.active)
        defer { (BSHDesign.active, BSHBureauDesk.active) = saved }
        BSHDesign.active = .bureau

        BSHBureauDesk.active = .onyx
        XCTAssertEqual(rgb(BSHPalette.bureauFrame, .light), [255, 255, 255], "a white desk by day")
        XCTAssertEqual(rgb(BSHPalette.bureauFrame, .dark), [5, 5, 5], "a black one by night")
        XCTAssertEqual(rgb(.dsCanvas, .light), [241, 240, 236], "Onyx's stone sheet")
        XCTAssertEqual(rgb(BSHPalette.bureauOnFrame, .light), [24, 24, 24], "written in ink on the white desk")

        BSHBureauDesk.active = .maroon
        XCTAssertEqual(rgb(BSHPalette.bureauFrame, .light), [80, 18, 30])
        XCTAssertEqual(rgb(.dsCanvas, .light), [247, 244, 236], "the colored desks share the ivory sheet")
        XCTAssertEqual(rgb(.dsCanvas, .dark), [35, 19, 24])
        XCTAssertEqual(rgb(.dsAccent, .light), [148, 112, 47], "brass on every desk")
    }

    func testTokensFollowTheActiveDesign() {
        let saved = (BSHDesign.active, BSHBureauDesk.active)
        defer { (BSHDesign.active, BSHBureauDesk.active) = saved }

        BSHDesign.active = .bureau
        BSHBureauDesk.active = .green
        XCTAssertEqual(rgb(.dsCanvas, .light), [247, 244, 236], "bottle green's ivory sheet")
        XCTAssertEqual(rgb(.dsCanvas, .dark), [21, 29, 26], "its green slate at night")
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
        var keys = ["settings.design", "settings.design_help", "settings.design_bureau", "settings.design_folio", "settings.design_glass", "settings.bureau_desk"]
        keys += BSHBureauDesk.allCases.map { "settings.bureau_desk_\($0.rawValue)" }
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
