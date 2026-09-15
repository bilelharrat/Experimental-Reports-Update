import PDFKit
import PencilKit
import XCTest
@testable import BSHResearch

@MainActor
final class MemoInkLayoutTests: XCTestCase {
    private let letter = CGSize(width: 612, height: 792)
    /// What WKWebView's createPDF makes of a long memo: one very tall page.
    private let convertedMemo = CGSize(width: 612, height: 13_602)

    // MARK: Composite layout

    func testCompositePageRectsStackPagesBetweenMatchingPads() {
        let sizes = [letter, letter, CGSize(width: 612, height: 400)]
        let rects = ReportAnnotationStore.compositePageRects(pageSizes: sizes)

        XCTAssertEqual(rects.count, 3)
        XCTAssertEqual(rects[0], CGRect(x: 0, y: 36, width: 612, height: 792))
        XCTAssertEqual(rects[1].minY, rects[0].maxY + 28)
        XCTAssertEqual(rects[2].minY, rects[1].maxY + 28)

        let canvas = ReportAnnotationStore.compositeCanvasSize(pageSizes: sizes)
        XCTAssertEqual(canvas.width, 612)
        XCTAssertEqual(canvas.height, rects[2].maxY + 36)
    }

    func testCompositeDrawingPlacesPageInkInsideItsPageRect() {
        let sizes = [letter, letter]
        let pages: [Int: PKDrawing] = [
            0: stroke(from: CGPoint(x: 100, y: 120)),
            1: stroke(from: CGPoint(x: 300, y: 700)),
        ]
        let rects = ReportAnnotationStore.compositePageRects(pageSizes: sizes)
        let composite = ReportAnnotationStore.compositeDrawing(from: pages, pageSizes: sizes)

        // The reader shows the composite as-is, so each stroke must land on its own page.
        XCTAssertEqual(composite.strokes.count, 2)
        let centers = composite.strokes.map { CGPoint(x: $0.renderBounds.midX, y: $0.renderBounds.midY) }
        XCTAssertTrue(centers.contains { rects[0].contains($0) })
        XCTAssertTrue(centers.contains { rects[1].contains($0) })
    }

    func testSplitCompositeRestoresPageCoordinates() {
        let sizes = [letter, letter]
        let pages: [Int: PKDrawing] = [
            0: stroke(from: CGPoint(x: 100, y: 120)),
            1: stroke(from: CGPoint(x: 300, y: 700)),
        ]
        let composite = ReportAnnotationStore.compositeDrawing(from: pages, pageSizes: sizes)
        let split = ReportAnnotationStore.splitComposite(composite, pageSizes: sizes)

        for index in [0, 1] {
            let original = try? XCTUnwrap(pages[index]?.bounds)
            let restored = try? XCTUnwrap(split[index]?.bounds)
            XCTAssertEqual(restored?.midX ?? 0, original?.midX ?? 1, accuracy: 0.5)
            XCTAssertEqual(restored?.midY ?? 0, original?.midY ?? 1, accuracy: 0.5)
        }
    }

    func testLocalInkFormsResolveToTheSameCanvasDrawing() {
        let sizes = [letter, letter]
        let pages: [Int: PKDrawing] = [1: stroke(from: CGPoint(x: 50, y: 60))]
        let composite = ReportAnnotationStore.compositeDrawing(from: pages, pageSizes: sizes)

        let fromPages = ReportAnnotationStore.LocalInk.pages(pages).compositeDrawing(pageSizes: sizes)
        let fromComposite = ReportAnnotationStore.LocalInk.composite(composite).compositeDrawing(pageSizes: sizes)

        XCTAssertEqual(fromPages.bounds.midY, fromComposite.bounds.midY, accuracy: 0.5)
        XCTAssertTrue(ReportAnnotationStore.LocalInk.none.compositeDrawing(pageSizes: sizes).strokes.isEmpty)
    }

    // MARK: Annotated-PDF export

    func testInkBandsTileATallPageUnderTheTextureLimit() {
        let bands = ReportAnnotationStore.inkBands(forPageHeight: convertedMemo.height)

        XCTAssertEqual(bands.first?.minY, 0)
        XCTAssertEqual(bands.last?.maxY ?? 0, convertedMemo.height, accuracy: 0.001)
        for (upper, lower) in zip(bands, bands.dropFirst()) {
            XCTAssertEqual(upper.maxY, lower.minY, accuracy: 0.001)
        }
        let scale = ReportAnnotationStore.inkImageScale(forWidth: convertedMemo.width)
        for band in bands {
            XCTAssertLessThanOrEqual(band.height * scale, 8_192)
            XCTAssertLessThanOrEqual(convertedMemo.width * scale, 8_192)
        }
        XCTAssertTrue(ReportAnnotationStore.inkBands(forPageHeight: 0).isEmpty)
    }

    // MARK: Page geometry

    func testPageGeometryFlipsPDFSpaceIntoViewSpace() throws {
        let page = try firstPage(of: makePDF(pageSizes: [letter]))
        let geometry = PaperPageGeometry(page: page)

        XCTAssertEqual(geometry.displaySize, letter)
        // PDF space starts bottom-left; the view starts top-left.
        assertPoint(CGPoint(x: 0, y: 0).applying(geometry.pageToView), equals: CGPoint(x: 0, y: 792))
        assertPoint(CGPoint(x: 612, y: 792).applying(geometry.pageToView), equals: CGPoint(x: 612, y: 0))
    }

    func testPageGeometryHonoursPageRotation() throws {
        let page = try firstPage(of: makePDF(pageSizes: [letter], rotation: 90))
        let geometry = PaperPageGeometry(page: page)

        XCTAssertEqual(geometry.displaySize, CGSize(width: 792, height: 612))
        let display = CGRect(origin: .zero, size: geometry.displaySize)
        let corners = [CGPoint(x: 0, y: 0), CGPoint(x: 612, y: 0), CGPoint(x: 0, y: 792), CGPoint(x: 612, y: 792)]
        let mapped = corners.map { $0.applying(geometry.pageToView) }
        for point in mapped {
            let onCorner = [CGPoint(x: display.minX, y: display.minY), CGPoint(x: display.maxX, y: display.minY),
                            CGPoint(x: display.minX, y: display.maxY), CGPoint(x: display.maxX, y: display.maxY)]
                .contains { abs($0.x - point.x) < 0.5 && abs($0.y - point.y) < 0.5 }
            XCTAssertTrue(onCorner, "\(point) is not a corner of \(display)")
        }
    }

    // MARK: Reader

    /// The regression behind "ink only appears after I lift the Pencil": PencilKit sizes its
    /// live-stroke layer to the canvas, so the canvas must stay viewport-sized however long the memo is.
    func testReaderCanvasStaysViewportSizedForATallConvertedMemo() throws {
        let url = try writeTemporaryPDF(makePDF(pageSizes: [convertedMemo]))
        defer { try? FileManager.default.removeItem(at: url) }
        let reader = PaperDeskReaderView(frame: CGRect(x: 0, y: 0, width: 820, height: 1_180))

        reader.load(url: url)
        reader.layoutIfNeeded()

        let canvas = try XCTUnwrap(reader.subviews.compactMap { $0 as? PKCanvasView }.first)
        XCTAssertEqual(canvas.bounds.size, reader.bounds.size)
        let fit: CGFloat = 820 / 612
        XCTAssertEqual(canvas.zoomScale, fit, accuracy: 0.001)
        let document = ReportAnnotationStore.compositeCanvasSize(pageSizes: [convertedMemo])
        XCTAssertEqual(canvas.contentSize.width, document.width * fit, accuracy: 0.5)
        XCTAssertEqual(canvas.contentSize.height, document.height * fit, accuracy: 0.5)
    }

    func testReaderKeepsRelativeZoomWhenTheViewResizes() throws {
        let url = try writeTemporaryPDF(makePDF(pageSizes: [letter, letter, letter]))
        defer { try? FileManager.default.removeItem(at: url) }
        let reader = PaperDeskReaderView(frame: CGRect(x: 0, y: 0, width: 820, height: 1_180))
        reader.load(url: url)
        reader.layoutIfNeeded()
        let canvas = try XCTUnwrap(reader.subviews.compactMap { $0 as? PKCanvasView }.first)

        canvas.zoomScale = canvas.zoomScale * 2
        reader.frame = CGRect(x: 0, y: 0, width: 1_180, height: 820)
        reader.layoutIfNeeded()

        XCTAssertEqual(canvas.bounds.size, reader.bounds.size)
        XCTAssertEqual(canvas.zoomScale, 2 * 1_180 / 612, accuracy: 0.001)
    }

    // MARK: Helpers

    private func stroke(from start: CGPoint) -> PKDrawing {
        let points = (0..<5).map { step in
            PKStrokePoint(
                location: CGPoint(x: start.x + CGFloat(step) * 10, y: start.y + CGFloat(step) * 2),
                timeOffset: TimeInterval(step) * 0.02,
                size: CGSize(width: 4, height: 4),
                opacity: 1,
                force: 1,
                azimuth: 0,
                altitude: .pi / 2
            )
        }
        let path = PKStrokePath(controlPoints: points, creationDate: Date())
        return PKDrawing(strokes: [PKStroke(ink: PKInk(.pen, color: .black), path: path)])
    }

    private func makePDF(pageSizes: [CGSize], rotation: Int = 0) -> Data {
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(origin: .zero, size: pageSizes[0]))
        let data = renderer.pdfData { context in
            for size in pageSizes {
                context.beginPage(withBounds: CGRect(origin: .zero, size: size), pageInfo: [:])
                UIColor.black.setFill()
                UIRectFill(CGRect(x: 40, y: 40, width: 120, height: 16))
            }
        }
        guard rotation != 0, let document = PDFDocument(data: data) else { return data }
        for index in 0..<document.pageCount {
            document.page(at: index)?.rotation = rotation
        }
        return document.dataRepresentation() ?? data
    }

    private func firstPage(of data: Data) throws -> CGPDFPage {
        let provider = try XCTUnwrap(CGDataProvider(data: data as CFData))
        let document = try XCTUnwrap(CGPDFDocument(provider))
        return try XCTUnwrap(document.page(at: 1))
    }

    private func writeTemporaryPDF(_ data: Data) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("ink-layout-\(UUID().uuidString).pdf")
        try data.write(to: url)
        return url
    }

    private func assertPoint(_ point: CGPoint, equals expected: CGPoint, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(point.x, expected.x, accuracy: 0.5, file: file, line: line)
        XCTAssertEqual(point.y, expected.y, accuracy: 0.5, file: file, line: line)
    }
}
