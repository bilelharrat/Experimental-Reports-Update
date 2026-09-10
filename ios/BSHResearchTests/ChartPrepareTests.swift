import XCTest
@testable import BSHResearch

/// The chart used to rebuild its whole series inside the per-point mark loop,
/// which froze the quote screen on dense ranges (1D is ~960 points, MAX ~2500).
/// These tests pin the prepared-data path to a single cheap pass.
final class ChartPrepareTests: XCTestCase {
    private func canvas(pointCount: Int) -> QuoteChartCanvas {
        let base = 1_757_000_000
        let points = (0..<pointCount).map { i in
            ChartPoint(
                t: base + i * 60,
                close: 500 + Double(i % 37),
                open: nil,
                high: nil,
                low: nil,
                volume: nil
            )
        }
        return QuoteChartCanvas(points: points, previousClose: 505, range: .d1)
    }

    func testPrepareIsCheapForDenseIntradaySeries() {
        let view = canvas(pointCount: 960)
        let started = Date()
        let prepared = view.prepare()
        let elapsed = Date().timeIntervalSince(started)

        XCTAssertEqual(prepared.rows.count, 960)
        XCTAssertLessThan(elapsed, 0.1, "prepare() must stay off the quadratic path")
    }

    func testDrawnSeriesIsDownsampledButKeepsEndpoints() {
        let view = canvas(pointCount: 2513)
        let prepared = view.prepare()

        XCTAssertEqual(prepared.rows.count, 2513)
        XCTAssertLessThanOrEqual(prepared.drawn.count, 325)
        XCTAssertEqual(prepared.drawn.first?.id, prepared.rows.first?.id)
        XCTAssertEqual(prepared.drawn.last?.id, prepared.rows.last?.id)
    }

    func testShortSeriesIsNotDownsampled() {
        let view = canvas(pointCount: 7)
        let prepared = view.prepare()
        XCTAssertEqual(prepared.drawn.count, 7)
    }

    func testDomainCoversPreviousCloseOnIntraday() {
        let view = canvas(pointCount: 30)
        let prepared = view.prepare()
        XCTAssertLessThanOrEqual(prepared.domain.lowerBound, 500)
        XCTAssertGreaterThanOrEqual(prepared.domain.upperBound, 529)
    }
}
