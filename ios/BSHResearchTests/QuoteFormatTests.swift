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
            dekEn: nil,
            dekZh: nil,
            bulletsEn: ["A"],
            bulletsZh: ["甲"],
            sectionsEn: nil,
            sectionsZh: nil
        )
        XCTAssertEqual(note.headline(lang: .en), "Risk-off")
        XCTAssertEqual(note.headline(lang: .zh), "避险")
        XCTAssertEqual(note.bullets(lang: .zh), ["甲"])
    }

    func testNewsBriefDecodesSingleLanguagePayload() throws {
        let json = """
        {
          "what_happened": "A long body of the story.",
          "why_it_matters": "The investment read.",
          "context": ["Prior event"],
          "watch_next": ["Q3 print"],
          "confidence": "high"
        }
        """.data(using: .utf8)!
        let brief = try JSONDecoder().decode(NewsBrief.self, from: json)
        XCTAssertEqual(brief.whatHappened(lang: .en), "A long body of the story.")
        XCTAssertEqual(brief.whyItMatters(lang: .en), "The investment read.")
        XCTAssertEqual(brief.context(lang: .en), ["Prior event"])
        XCTAssertEqual(brief.watchNext(lang: .en), ["Q3 print"])
    }

    func testNewsBriefPrefersLanguageSuffix() throws {
        let json = """
        {
          "what_happened": "Bare",
          "what_happened_en": "English body",
          "what_happened_zh": "中文正文"
        }
        """.data(using: .utf8)!
        let brief = try JSONDecoder().decode(NewsBrief.self, from: json)
        XCTAssertEqual(brief.whatHappened(lang: .en), "English body")
        XCTAssertEqual(brief.whatHappened(lang: .zh), "中文正文")
    }
}
