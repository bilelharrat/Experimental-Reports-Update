import XCTest
@testable import BSHResearch

final class QuoteFormatTests: XCTestCase {
    func testPctFormatting() {
        XCTAssertEqual(QuoteRow.pct(1.25), "+1.3%")
        XCTAssertEqual(QuoteRow.pct(-0.5), "-0.5%")
        XCTAssertEqual(QuoteRow.pct(nil), "—")
    }

    func testPriceFormatting() {
        XCTAssertEqual(QuoteRow.price(100.5, currency: "USD"), "$100.50")
        XCTAssertEqual(QuoteRow.price(nil, currency: "USD"), "—")
    }

    func testBriefNoteLanguagePick() {
        let note = BriefNote(
            length: "short",
            headlineEn: "Risk-off",
            headlineZh: "避险",
            bulletsEn: ["A"],
            bulletsZh: ["甲"],
            sectionsEn: nil,
            sectionsZh: nil
        )
        XCTAssertEqual(note.headline(lang: .en), "Risk-off")
        XCTAssertEqual(note.headline(lang: .zh), "避险")
        XCTAssertEqual(note.bullets(lang: .zh), ["甲"])
    }
}
