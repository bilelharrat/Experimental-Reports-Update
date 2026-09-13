import Foundation
import PencilKit
import UIKit

/// Persists freehand memo annotations (`PKDrawing`) per report id locally,
/// and syncs them to the signed-in account via `/api/reports/{id}/annotations`.
enum ReportAnnotationStore {
    private static let folderName = "ReportAnnotations"

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

    // MARK: Local disk

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
        let image = drawing.image(from: bounds, scale: 2.0)
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
