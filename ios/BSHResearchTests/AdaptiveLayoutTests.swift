import XCTest
@testable import BSHResearch

final class AdaptiveLayoutTests: XCTestCase {
    func testPortraitAspectNeverPrefersRootSidebar() {
        // When running on iPhone, isPad is false → always false.
        // When running on iPad, portrait aspect must also be false.
        XCTAssertFalse(AdaptiveLayout.prefersRootSidebar(width: 834, height: 1194))
        XCTAssertFalse(AdaptiveLayout.prefersRootSidebar(width: 1024, height: 1366))
        XCTAssertFalse(AdaptiveLayout.prefersRootSidebar(width: 0, height: 0))
    }

    func testLandscapeAspectPrefersRootSidebarOnlyOnPad() {
        let wide = AdaptiveLayout.prefersRootSidebar(width: 1194, height: 834)
        if AdaptiveLayout.isPad {
            XCTAssertTrue(wide)
        } else {
            XCTAssertFalse(wide)
        }
    }

    func testReadableWidthSkippedInRootSidebarDetail() {
        XCTAssertFalse(
            AdaptiveLayout.shouldConstrainReadableWidth(
                sizeClass: .regular,
                embeddedInRootSplit: true
            )
        )
    }

    func testReadableWidthAppliesOnRegularOutsideSidebar() {
        XCTAssertTrue(
            AdaptiveLayout.shouldConstrainReadableWidth(
                sizeClass: .regular,
                embeddedInRootSplit: false
            )
        )
        XCTAssertFalse(
            AdaptiveLayout.shouldConstrainReadableWidth(
                sizeClass: .compact,
                embeddedInRootSplit: false
            )
        )
    }
}
