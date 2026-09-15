import PDFKit
import Foundation
import PencilKit
import UIKit

/// Persists freehand memo annotations (`PKDrawing`) per report id locally,
/// anchored per PDF page, and syncs composite ink to the signed-in account via
/// `/api/reports/{id}/annotations`.
enum ReportAnnotationStore {
    private static let folderName = "ReportAnnotations"

    struct MultiPageDrawingArchive: Codable {
        var version: Int = 1
        var pages: [String: String] // "\(pageIndex)" -> base64 encoded PKDrawing data
    }

    struct RemotePayload: Codable {
        let reportId: String
        let updatedAt: String?
        let etag: String?
        let hasDrawingPk: Bool
        let hasOverlay: Bool
        let drawingPkBase64: String?
        let overlayPngBase64: String?
        let overlayUrl: String?
        let canvasWidth: Double?
        let canvasHeight: Double?
        let cleared: Bool?

        enum CodingKeys: String, CodingKey {
            case reportId = "report_id"
            case updatedAt = "updated_at"
            case etag
            case hasDrawingPk = "has_drawing_pk"
            case hasOverlay = "has_overlay"
            case drawingPkBase64 = "drawing_pk_base64"
            case overlayPngBase64 = "overlay_png_base64"
            case overlayUrl = "overlay_url"
            case canvasWidth = "canvas_width"
            case canvasHeight = "canvas_height"
            case cleared
        }
    }

    /// Encoded with APIClient's convertToSnakeCase strategy.
    struct PutBody: Encodable {
        let drawingPkBase64: String?
        let overlayPngBase64: String?
        let canvasWidth: Double?
        let canvasHeight: Double?
        let clear: Bool
    }

    struct LocalMeta: Codable {
        var updatedAt: String
        var etag: String?
        var canvasWidth: Double?
        var canvasHeight: Double?
        var cleared: Bool
    }

    // MARK: Local disk (per-page archive + composite)

    /// Ink found on disk for a report, in whichever form was saved last.
    enum LocalInk {
        case none
        /// Page-anchored strokes (page coordinates) — what the reader writes.
        case pages([Int: PKDrawing])
        /// Composite-space strokes only, e.g. synced from another device before this one saved.
        case composite(PKDrawing)

        /// The ink laid out in composite space for a document with `pageSizes`.
        func compositeDrawing(pageSizes: [CGSize]) -> PKDrawing {
            switch self {
            case .none:
                return PKDrawing()
            case .pages(let pages):
                return ReportAnnotationStore.compositeDrawing(from: pages, pageSizes: pageSizes)
            case .composite(let drawing):
                return drawing
            }
        }
    }

    static func loadLocalInk(reportId: String) -> LocalInk {
        if let data = try? Data(contentsOf: pagesURL(for: reportId)),
           let archive = try? JSONDecoder().decode(MultiPageDrawingArchive.self, from: data) {
            var pages: [Int: PKDrawing] = [:]
            for (key, b64) in archive.pages {
                if let index = Int(key),
                   let raw = Data(base64Encoded: b64),
                   let drawing = try? PKDrawing(data: raw) {
                    pages[index] = drawing
                }
            }
            if !pages.isEmpty {
                return .pages(pages)
            }
        }
        let composite = load(reportId: reportId)
        return composite.strokes.isEmpty ? .none : .composite(composite)
    }

    /// Save the reader's composite ink: the page-anchored archive plus the composite copy the cloud sync sends.
    static func saveComposite(_ composite: PKDrawing, reportId: String, pageSizes: [CGSize]) {
        do {
            try ensureDirectory()
            var archive = MultiPageDrawingArchive(version: 1, pages: [:])
            for (index, drawing) in splitComposite(composite, pageSizes: pageSizes) where !drawing.strokes.isEmpty {
                archive.pages[String(index)] = drawing.dataRepresentation().base64EncodedString()
            }
            let data = try JSONEncoder().encode(archive)
            try data.write(to: pagesURL(for: reportId), options: .atomic)
            save(composite, reportId: reportId, canvasSize: compositeCanvasSize(pageSizes: pageSizes))
        } catch {
            // Local ink is best effort
        }
    }

    // MARK: Composite layout (pages stacked vertically — the coordinate space the web overlay uses)

    private static let compositeGap: CGFloat = 28
    private static let compositeTopPad: CGFloat = 36
    private static let fallbackPageSize = CGSize(width: 612, height: 792)

    /// Top y of each page in composite space, for `count` pages.
    private static func compositePageTops(pageSizes: [CGSize], count: Int) -> [CGFloat] {
        var tops: [CGFloat] = []
        var y = compositeTopPad
        for index in 0..<count {
            tops.append(y)
            let size = index < pageSizes.count ? pageSizes[index] : fallbackPageSize
            y += size.height + compositeGap
        }
        return tops
    }

    /// Where each page sits in composite space. The memo reader lays its pages out exactly here,
    /// so the canvas drawing *is* the composite drawing.
    static func compositePageRects(pageSizes: [CGSize]) -> [CGRect] {
        let tops = compositePageTops(pageSizes: pageSizes, count: pageSizes.count)
        return zip(tops, pageSizes).map { top, size in
            CGRect(x: 0, y: top, width: size.width, height: size.height)
        }
    }

    /// Size of the composite canvas the web overlay is rendered against.
    static func compositeCanvasSize(pageSizes: [CGSize]) -> CGSize {
        let sizes = pageSizes.isEmpty ? [fallbackPageSize] : pageSizes
        let totalHeight = sizes.reduce(0) { $0 + $1.height }
            + CGFloat(max(0, sizes.count - 1)) * compositeGap
            + compositeTopPad * 2
        let maxWidth = sizes.map(\.width).max() ?? fallbackPageSize.width
        return CGSize(width: maxWidth, height: totalHeight)
    }

    /// Create a single vertically stacked PKDrawing from per-page drawings.
    static func compositeDrawing(from pageDrawings: [Int: PKDrawing], pageSizes: [CGSize]) -> PKDrawing {
        var composite = PKDrawing()
        let maxCount = max(pageSizes.count, (pageDrawings.keys.max() ?? -1) + 1)
        let tops = compositePageTops(pageSizes: pageSizes, count: maxCount)
        for index in 0..<maxCount {
            if let drawing = pageDrawings[index], !drawing.strokes.isEmpty {
                let transform = CGAffineTransform(translationX: 0, y: tops[index])
                var pageCopy = drawing
                pageCopy.transform(using: transform)
                composite = composite.appending(pageCopy)
            }
        }
        return composite
    }

    /// Inverse of `compositeDrawing`: assign each stroke back to the page whose band contains it.
    /// Used when a cloud copy (composite space) has to be shown on page-anchored canvases.
    static func splitComposite(_ composite: PKDrawing, pageSizes: [CGSize]) -> [Int: PKDrawing] {
        guard !composite.strokes.isEmpty else { return [:] }
        let sizes = pageSizes.isEmpty ? [fallbackPageSize] : pageSizes
        let tops = compositePageTops(pageSizes: sizes, count: sizes.count)
        var perPage: [Int: [PKStroke]] = [:]
        for stroke in composite.strokes {
            let midY = stroke.renderBounds.midY
            var index = 0
            for (i, top) in tops.enumerated() where midY >= top {
                index = i
            }
            var moved = stroke
            moved.transform = moved.transform.concatenating(CGAffineTransform(translationX: 0, y: -tops[index]))
            perPage[index, default: []].append(moved)
        }
        var result: [Int: PKDrawing] = [:]
        for (index, strokes) in perPage {
            result[index] = PKDrawing(strokes: strokes)
        }
        return result
    }

    /// High-resolution PDF renderer that burns per-page Apple PencilKit drawings directly into PDF pages.
    /// Returns the URL to the annotated PDF file.
    static func renderAnnotatedPDF(
        document: PDFDocument,
        pageDrawings: [Int: PKDrawing],
        reportId: String
    ) -> URL? {
        let outputURL = annotatedPDFURL(for: reportId)
        let format = UIGraphicsPDFRendererFormat()
        let renderer = UIGraphicsPDFRenderer(bounds: .zero, format: format)

        let pdfData = renderer.pdfData { context in
            for index in 0..<document.pageCount {
                guard let page = document.page(at: index) else { continue }
                let mediaBox = page.bounds(for: .mediaBox)
                context.beginPage(withBounds: mediaBox, pageInfo: [:])
                let cgContext = context.cgContext

                // Draw original PDF page contents
                cgContext.saveGState()
                cgContext.translateBy(x: 0, y: mediaBox.height)
                cgContext.scaleBy(x: 1.0, y: -1.0)
                page.draw(with: .mediaBox, to: cgContext)
                cgContext.restoreGState()

                // Burn the ink in bands: one image for a whole long page would exceed
                // Metal's texture limit (a converted memo is a single ~14,000 pt page).
                if let drawing = pageDrawings[index], !drawing.strokes.isEmpty {
                    let scale = inkImageScale(forWidth: mediaBox.width)
                    for band in inkBands(forPageHeight: mediaBox.height) {
                        let source = CGRect(x: 0, y: band.minY, width: mediaBox.width, height: band.height)
                        let image = drawing.image(from: source, scale: scale)
                        image.draw(in: source.offsetBy(dx: mediaBox.minX, dy: mediaBox.minY))
                    }
                }
            }
        }

        do {
            try ensureDirectory()
            try pdfData.write(to: outputURL, options: .atomic)
            return outputURL
        } catch {
            return nil
        }
    }

    /// Tallest slice of a page rendered as one ink image (at `inkImageScale` that stays far below 8192 px).
    static let inkBandHeight: CGFloat = 2_000

    /// Vertical slices (page coordinates) that tile a page of `height` points top to bottom.
    static func inkBands(forPageHeight height: CGFloat) -> [CGRect] {
        guard height > 0 else { return [] }
        var bands: [CGRect] = []
        var y: CGFloat = 0
        while y < height {
            let h = min(inkBandHeight, height - y)
            bands.append(CGRect(x: 0, y: y, width: 0, height: h))
            y += h
        }
        return bands
    }

    static func inkImageScale(forWidth width: CGFloat) -> CGFloat {
        min(2.0, max(0.25, 7_800 / max(width, 1)))
    }

    static func load(reportId: String) -> PKDrawing {
        let url = drawingURL(for: reportId)
        guard let data = try? Data(contentsOf: url), !data.isEmpty else {
            return PKDrawing()
        }
        return (try? PKDrawing(data: data)) ?? PKDrawing()
    }

    static func loadMeta(reportId: String) -> LocalMeta? {
        let url = metaURL(for: reportId)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(LocalMeta.self, from: data)
    }

    static func save(
        _ drawing: PKDrawing,
        reportId: String,
        canvasSize: CGSize? = nil,
        updatedAt: String? = nil,
        etag: String? = nil
    ) {
        let url = drawingURL(for: reportId)
        do {
            try ensureDirectory()
            let data = drawing.dataRepresentation()
            try data.write(to: url, options: .atomic)
            let stamp = updatedAt ?? isoNow()
            let meta = LocalMeta(
                updatedAt: stamp,
                etag: etag ?? loadMeta(reportId: reportId)?.etag,
                canvasWidth: canvasSize.map { Double($0.width) } ?? loadMeta(reportId: reportId)?.canvasWidth,
                canvasHeight: canvasSize.map { Double($0.height) } ?? loadMeta(reportId: reportId)?.canvasHeight,
                cleared: drawing.strokes.isEmpty
            )
            try writeMeta(meta, reportId: reportId)
        } catch {
            // Local ink is best-effort; ignore disk errors.
        }
    }

    static func clear(reportId: String) {
        try? FileManager.default.removeItem(at: drawingURL(for: reportId))
        try? FileManager.default.removeItem(at: pagesURL(for: reportId))
        try? FileManager.default.removeItem(at: annotatedPDFURL(for: reportId))
        let meta = LocalMeta(
            updatedAt: isoNow(),
            etag: nil,
            canvasWidth: nil,
            canvasHeight: nil,
            cleared: true
        )
        try? ensureDirectory()
        try? writeMeta(meta, reportId: reportId)
    }

    static func hasInk(reportId: String) -> Bool {
        let pagesUrl = pagesURL(for: reportId)
        if FileManager.default.fileExists(atPath: pagesUrl.path) {
            return true
        }
        let url = drawingURL(for: reportId)
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = attrs[.size] as? NSNumber
        else { return false }
        return size.intValue > 0
    }

    /// Render a transparent PNG of the ink for web clients.
    static func overlayPNG(from drawing: PKDrawing, canvasSize: CGSize?) -> Data? {
        guard !drawing.strokes.isEmpty else { return nil }
        let bounds: CGRect
        if let canvasSize, canvasSize.width > 1, canvasSize.height > 1 {
            bounds = CGRect(origin: .zero, size: canvasSize)
        } else {
            let ink = drawing.bounds
            guard ink.width > 1, ink.height > 1 else { return nil }
            bounds = ink.insetBy(dx: -24, dy: -24)
        }
        // A whole-document composite can be thousands of points tall; keep the Metal
        // render inside the 8192 px texture limit (simulator) and the PNG small.
        let maxDimension = max(bounds.width, bounds.height)
        let scale = min(2.0, max(0.25, 7_800 / maxDimension))
        let image = drawing.image(from: bounds, scale: scale)
        return image.pngData()
    }

    // MARK: Cloud sync

    /// Local-first open: return cached drawing immediately; caller should also `pullIfNewer`.
    static func loadLocal(reportId: String) -> (drawing: PKDrawing, meta: LocalMeta?) {
        (load(reportId: reportId), loadMeta(reportId: reportId))
    }

    /// Fetch server copy; apply if newer / missing locally (or if server cleared more recently).
    /// If the local cache is newer, push it so other devices catch up.
    @discardableResult
    static func pullIfNewer(reportId: String) async -> PKDrawing? {
        let localMeta = loadMeta(reportId: reportId)
        let localDrawing = load(reportId: reportId)
        do {
            let remote: RemotePayload = try await APIClient.shared.get(
                "reports/\(reportId)/annotations",
                query: [URLQueryItem(name: "include_drawing", value: "true")]
            )
            let remoteAt = remote.updatedAt
            let localAt = localMeta?.updatedAt

            if let localAt, remoteAt == nil || localAt > (remoteAt ?? "") {
                // Local wins — push so web / other devices see it.
                if localMeta?.cleared == true || !localDrawing.strokes.isEmpty {
                    let size: CGSize? = {
                        guard let w = localMeta?.canvasWidth, let h = localMeta?.canvasHeight else {
                            return nil
                        }
                        return CGSize(width: w, height: h)
                    }()
                    _ = await push(localDrawing, reportId: reportId, canvasSize: size)
                }
                return nil
            }

            if remote.cleared == true {
                clear(reportId: reportId)
                if let stamp = remoteAt {
                    try? writeMeta(
                        LocalMeta(
                            updatedAt: stamp,
                            etag: remote.etag,
                            canvasWidth: nil,
                            canvasHeight: nil,
                            cleared: true
                        ),
                        reportId: reportId
                    )
                }
                return PKDrawing()
            }

            guard let b64 = remote.drawingPkBase64,
                  let data = Data(base64Encoded: b64),
                  let drawing = try? PKDrawing(data: data)
            else {
                return nil
            }

            let size: CGSize? = {
                guard let w = remote.canvasWidth, let h = remote.canvasHeight else { return nil }
                return CGSize(width: w, height: h)
            }()
            save(
                drawing,
                reportId: reportId,
                canvasSize: size,
                updatedAt: remoteAt ?? isoNow(),
                etag: remote.etag
            )
            return drawing
        } catch {
            // Offline / auth hiccup — keep local ink.
        }
        return nil
    }

    /// Push current local drawing (+ overlay PNG) to the account store.
    @discardableResult
    static func push(
        _ drawing: PKDrawing,
        reportId: String,
        canvasSize: CGSize?
    ) async -> RemotePayload? {
        let overlay = overlayPNG(from: drawing, canvasSize: canvasSize)
        let body: PutBody
        if drawing.strokes.isEmpty {
            body = PutBody(
                drawingPkBase64: nil,
                overlayPngBase64: nil,
                canvasWidth: nil,
                canvasHeight: nil,
                clear: true
            )
        } else {
            body = PutBody(
                drawingPkBase64: drawing.dataRepresentation().base64EncodedString(),
                overlayPngBase64: overlay?.base64EncodedString(),
                canvasWidth: canvasSize.map { Double($0.width) },
                canvasHeight: canvasSize.map { Double($0.height) },
                clear: false
            )
        }
        do {
            let remote: RemotePayload = try await APIClient.shared.put(
                "reports/\(reportId)/annotations",
                body: body
            )
            save(
                drawing,
                reportId: reportId,
                canvasSize: canvasSize,
                updatedAt: remote.updatedAt ?? isoNow(),
                etag: remote.etag
            )
            return remote
        } catch {
            // Keep local; next autosave / open will retry.
            return nil
        }
    }

    // MARK: Paths

    private static func isoNow() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: Date())
    }

    private static func writeMeta(_ meta: LocalMeta, reportId: String) throws {
        let data = try JSONEncoder().encode(meta)
        try data.write(to: metaURL(for: reportId), options: .atomic)
    }

    private static func drawingURL(for reportId: String) -> URL {
        let safe = reportId
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: ":", with: "_")
        return directoryURL().appendingPathComponent("\(safe).pkdrawing")
    }

    private static func pagesURL(for reportId: String) -> URL {
        let safe = reportId
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: ":", with: "_")
        return directoryURL().appendingPathComponent("\(safe).pages.json")
    }

    static func annotatedPDFURL(for reportId: String) -> URL {
        let safe = reportId
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: ":", with: "_")
        return directoryURL().appendingPathComponent("\(safe)_annotated.pdf")
    }

    private static func metaURL(for reportId: String) -> URL {
        let safe = reportId
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: ":", with: "_")
        return directoryURL().appendingPathComponent("\(safe).meta.json")
    }

    private static func directoryURL() -> URL {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return root.appendingPathComponent(folderName, isDirectory: true)
    }

    private static func ensureDirectory() throws {
        try FileManager.default.createDirectory(at: directoryURL(), withIntermediateDirectories: true)
    }
}
