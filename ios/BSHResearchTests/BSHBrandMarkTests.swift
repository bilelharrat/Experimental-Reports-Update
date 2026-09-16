import XCTest
import SwiftUI
@testable import BSHResearch

final class BSHBrandMarkTests: XCTestCase {
    func testBrandMarkShapeGeneratesValidPath() {
        let shape = BSHBrandMarkShape()
        let rect = CGRect(x: 0, y: 0, width: 101, height: 65)
        let path = shape.path(in: rect)

        XCTAssertFalse(path.isEmpty, "BSHBrandMarkShape path should not be empty")
        let bounds = path.boundingRect
        XCTAssertGreaterThan(bounds.width, 0, "Shape width should be positive")
        XCTAssertGreaterThan(bounds.height, 0, "Shape height should be positive")
        XCTAssertLessThanOrEqual(bounds.width, 101.5, "Shape should fit target rect width")
        XCTAssertLessThanOrEqual(bounds.height, 65.5, "Shape should fit target rect height")
    }

    func testBrandMarkShapePreservesAspectRatioInSquareRect() {
        let shape = BSHBrandMarkShape()
        let rect1 = CGRect(x: 0, y: 0, width: 101, height: 65)
        let rect2 = CGRect(x: 0, y: 0, width: 200, height: 200)
        let bounds1 = shape.path(in: rect1).boundingRect
        let bounds2 = shape.path(in: rect2).boundingRect

        let ratio1 = bounds1.width / bounds1.height
        let ratio2 = bounds2.width / bounds2.height

        // Aspect ratio of the path bounding box should remain invariant regardless of container dimensions
        XCTAssertEqual(ratio1, ratio2, accuracy: 0.01)
    }

    func testBrandTileInitialization() {
        let tile = BSHBrandTile(size: 76, cornerRadius: 18)
        XCTAssertEqual(tile.size, 76)
        XCTAssertEqual(tile.cornerRadius, 18)
    }

    func testMacCompanyLogoResolverCandidates() {
        // Tickers and domains resolution
        let appleCandidates = MacCompanyLogoResolver.resolveCandidateUrls(
            logoUrl: "https://assets.parqet.com/logos/symbol/AAPL",
            logoDomain: "apple.com",
            ticker: "AAPL"
        )
        XCTAssertFalse(appleCandidates.isEmpty)
        // First candidate should NOT be the SVG, it should be the Google Favicon V2 PNG
        XCTAssertTrue(appleCandidates.first!.absoluteString.contains("gstatic.com/faviconV2"))
        XCTAssertTrue(appleCandidates.first!.absoluteString.contains("apple.com"))

        // HIMS ticker domain resolution
        let himsCandidates = MacCompanyLogoResolver.resolveCandidateUrls(
            ticker: "HIMS"
        )
        XCTAssertFalse(himsCandidates.isEmpty)
        XCTAssertTrue(himsCandidates.first!.absoluteString.contains("forhims.com"))

        // ZaiNar private company domain resolution
        let zainarCandidates = MacCompanyLogoResolver.resolveCandidateUrls(
            companyId: "zainar-inc"
        )
        XCTAssertFalse(zainarCandidates.isEmpty)
        XCTAssertTrue(zainarCandidates.first!.absoluteString.contains("zainartech.com"))
    }

    func testSvgUrlDetection() {
        XCTAssertTrue(MacCompanyLogoResolver.isSvgUrl("https://assets.parqet.com/logos/symbol/AAPL"))
        XCTAssertTrue(MacCompanyLogoResolver.isSvgUrl("https://example.com/logo.svg"))
        XCTAssertTrue(MacCompanyLogoResolver.isSvgUrl("https://api.iconify.design/simple-icons:openai.svg"))
        XCTAssertFalse(MacCompanyLogoResolver.isSvgUrl("https://t1.gstatic.com/faviconV2?url=https://apple.com"))
        XCTAssertFalse(MacCompanyLogoResolver.isSvgUrl("https://example.com/logo.png"))
    }
}
