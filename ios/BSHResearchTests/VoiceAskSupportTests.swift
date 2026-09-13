import XCTest
@testable import BSHResearch

final class VoiceAskSupportTests: XCTestCase {
    func testResolvedLocaleMapsBareEnglishToEnUS() {
        let supported: Set<Locale> = [
            Locale(identifier: "en-US"),
            Locale(identifier: "en-GB"),
            Locale(identifier: "zh-CN"),
        ]
        let resolved = VoiceAskSupport.resolvedSpeechLocale(
            from: Locale(identifier: "en"),
            supported: supported
        )
        XCTAssertEqual(resolved.identifier, "en-US")
    }

    func testResolvedLocaleMapsZhHans() {
        let supported: Set<Locale> = [
            Locale(identifier: "en-US"),
            Locale(identifier: "zh-CN"),
            Locale(identifier: "zh-Hans"),
        ]
        let resolved = VoiceAskSupport.resolvedSpeechLocale(
            from: Locale(identifier: "zh-Hans"),
            supported: supported
        )
        XCTAssertTrue(["zh-Hans", "zh-CN"].contains(resolved.identifier))
    }

    func testJoinCommitted() {
        XCTAssertEqual(VoiceAskSupport.joinCommitted("", piece: "hello"), "hello")
        XCTAssertEqual(VoiceAskSupport.joinCommitted("hello", piece: "world"), "hello world")
        XCTAssertEqual(VoiceAskSupport.joinCommitted("hello", piece: ""), "hello")
    }

    func testSpeechAuthMessages() {
        XCTAssertNil(VoiceAskSupport.speechAuthMessage(.authorized))
        XCTAssertNotNil(VoiceAskSupport.speechAuthMessage(.denied))
        XCTAssertNotNil(VoiceAskSupport.speechAuthMessage(.restricted))
        XCTAssertNotNil(VoiceAskSupport.speechAuthMessage(.notDetermined))
    }

    func testRetryableRecognitionErrors() {
        let cancelled = NSError(domain: "kAFAssistantErrorDomain", code: 216)
        XCTAssertTrue(VoiceAskSupport.isRetryableRecognitionError(cancelled))
        let noSpeech = NSError(domain: "kAFAssistantErrorDomain", code: 1110)
        XCTAssertTrue(VoiceAskSupport.isRetryableRecognitionError(noSpeech))
        let hardFail = NSError(domain: "kAFAssistantErrorDomain", code: 1)
        XCTAssertFalse(VoiceAskSupport.isRetryableRecognitionError(hardFail))
    }
}
