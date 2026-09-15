import AppKit
import PDFKit
import QuickLookUI
import SwiftUI

/// A "jump to this passage" request. Each click creates a new request so repeating the same
/// text still jumps.
struct MacFindRequest: Equatable {
    let text: String
    let id: UUID

    init(text: String) {
        self.text = text
        self.id = UUID()
    }
}

/// PDF canvas with the iPad Apple Pencil ink overlay composited on top.
/// Reports text selections (for "Ask about this passage") and jumps to `findText` when set.
struct MacPDFKitView: NSViewRepresentable {
    let url: URL
    let overlayData: Data?
    let overlayOpacity: Double
    var findText: String? = nil
    var findRequest: MacFindRequest? = nil
    var overlayCanvasSize: CGSize? = nil
    var onSelection: ((String?) -> Void)? = nil
    var onPageChange: ((Int) -> Void)? = nil

    func makeCoordinator() -> Coordinator {
        Coordinator(onSelection: onSelection, onPageChange: onPageChange)
    }

    func makeNSView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.backgroundColor = NSColor.windowBackgroundColor
        v.document = PDFDocument(url: url)
        v.pageOverlayViewProvider = context.coordinator
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.selectionChanged(_:)),
            name: .PDFViewSelectionChanged,
            object: v
        )
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.pageChanged(_:)),
            name: .PDFViewPageChanged,
            object: v
        )
        return v
    }

    func updateNSView(_ v: PDFView, context: Context) {
        let coordinator = context.coordinator
        coordinator.onSelection = onSelection
        coordinator.onPageChange = onPageChange

        if v.document?.documentURL != url {
            v.document = PDFDocument(url: url)
            coordinator.invalidateOverlay()
        }

        // Jump to a passage (thesis claim → memo text) when the caller sets a find request.
        if let findRequest, !findRequest.text.isEmpty, findRequest.id != coordinator.lastFindID {
            coordinator.lastFindID = findRequest.id
            coordinator.lastFind = findRequest.text
            coordinator.jump(to: findRequest.text, in: v)
        } else if findRequest == nil, let findText, !findText.isEmpty, findText != coordinator.lastFind {
            coordinator.lastFind = findText
            coordinator.jump(to: findText, in: v)
        }

        coordinator.updateOverlay(data: overlayData, canvasSize: overlayCanvasSize, opacity: overlayOpacity, in: v)
    }

    static func dismantleNSView(_ v: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
        v.pageOverlayViewProvider = nil
    }

    final class Coordinator: NSObject, PDFPageOverlayViewProvider {
        var onSelection: ((String?) -> Void)?
        var onPageChange: ((Int) -> Void)?
        var lastFind: String?
        var lastFindID: UUID?

        private var overlayData: Data?
        private var overlayCanvasSize: CGSize?
        private var overlayOpacity: Double = 1
        private var compositeImage: CGImage?
        private var pageCrops: [Int: CGImage] = [:]
        private var overlayViews: [Int: MacInkOverlayView] = [:]

        init(onSelection: ((String?) -> Void)?, onPageChange: ((Int) -> Void)?) {
            self.onSelection = onSelection
            self.onPageChange = onPageChange
        }

        func jump(to text: String, in view: PDFView) {
            guard let document = view.document else { return }
            let needle = String(text.split(separator: " ").prefix(7).joined(separator: " "))
            let hits = document.findString(needle, withOptions: [.caseInsensitive])
            if let first = hits.first {
                view.go(to: first)
                view.setCurrentSelection(first, animate: true)
            }
        }

        // MARK: Ink overlay

        func invalidateOverlay() {
            pageCrops.removeAll()
            for (_, overlay) in overlayViews {
                overlay.image = nil
                overlay.needsDisplay = true
            }
        }

        func updateOverlay(data: Data?, canvasSize: CGSize?, opacity: Double, in view: PDFView) {
            let dataChanged = data != overlayData
            let canvasChanged = canvasSize != overlayCanvasSize
            let opacityChanged = opacity != overlayOpacity
            guard dataChanged || canvasChanged || opacityChanged else { return }

            overlayOpacity = opacity
            if dataChanged {
                overlayData = data
                compositeImage = data.flatMap { NSBitmapImageRep(data: $0)?.cgImage }
            }
            if canvasChanged {
                overlayCanvasSize = canvasSize
            }
            if dataChanged || canvasChanged {
                pageCrops.removeAll()
            }

            guard let document = view.document else { return }
            for (index, overlay) in overlayViews {
                if dataChanged || canvasChanged {
                    overlay.image = crop(forPageIndex: index, in: document)
                }
                overlay.alphaValue = CGFloat(opacity)
                overlay.needsDisplay = true
            }
        }

        private func pageSizes(in document: PDFDocument) -> [CGSize] {
            (0..<document.pageCount).map { index in
                document.page(at: index)?.bounds(for: .mediaBox).size ?? MacInkComposite.fallbackPageSize
            }
        }

        private func crop(forPageIndex index: Int, in document: PDFDocument) -> CGImage? {
            if let cached = pageCrops[index] { return cached }
            guard let compositeImage else { return nil }
            let sizes = pageSizes(in: document)
            guard index < sizes.count else { return nil }
            let canvas = overlayCanvasSize ?? MacInkComposite.canvasSize(pageSizes: sizes)
            guard canvas.width > 0 else { return nil }
            let scale = CGFloat(compositeImage.width) / canvas.width
            let tops = MacInkComposite.pageTops(pageSizes: sizes)
            let page = sizes[index]
            let rect = CGRect(
                x: 0,
                y: tops[index] * scale,
                width: page.width * scale,
                height: page.height * scale
            ).intersection(CGRect(x: 0, y: 0, width: compositeImage.width, height: compositeImage.height))
            guard !rect.isEmpty, let cropped = compositeImage.cropping(to: rect.integral) else { return nil }
            pageCrops[index] = cropped
            return cropped
        }

        func pdfView(_ view: PDFView, overlayViewFor page: PDFPage) -> NSView? {
            guard let document = view.document else { return nil }
            let index = document.index(for: page)
            let overlay = overlayViews[index] ?? MacInkOverlayView()
            overlay.image = crop(forPageIndex: index, in: document)
            overlay.alphaValue = CGFloat(overlayOpacity)
            overlay.needsDisplay = true
            overlayViews[index] = overlay
            return overlay
        }

        func pdfView(_ view: PDFView, willEndDisplayingOverlayView overlayView: NSView, for page: PDFPage) {
            guard let document = view.document else { return }
            let index = document.index(for: page)
            if overlayViews[index] === overlayView {
                overlayViews[index] = nil
            }
        }

        // MARK: Notifications

        @objc func selectionChanged(_ notification: Notification) {
            let view = notification.object as? PDFView
            let text = view?.currentSelection?.string?.trimmingCharacters(in: .whitespacesAndNewlines)
            onSelection?((text?.isEmpty ?? true) ? nil : text)
        }

        @objc func pageChanged(_ notification: Notification) {
            guard let view = notification.object as? PDFView,
                  let page = view.currentPage,
                  let document = view.document else { return }
            onPageChange?(document.index(for: page) + 1)
        }
    }
}

/// Layout of the vertically stacked ink composite shared with the iPad (`ReportAnnotationStore`)
/// and the web overlay: a top pad, then each page followed by a gap.
enum MacInkComposite {
    static let gap: CGFloat = 28
    static let topPad: CGFloat = 36
    static let fallbackPageSize = CGSize(width: 612, height: 792)

    static func pageTops(pageSizes: [CGSize]) -> [CGFloat] {
        var tops: [CGFloat] = []
        var y = topPad
        for size in pageSizes {
            tops.append(y)
            y += size.height + gap
        }
        return tops
    }

    static func canvasSize(pageSizes: [CGSize]) -> CGSize {
        let sizes = pageSizes.isEmpty ? [fallbackPageSize] : pageSizes
        let totalHeight = sizes.reduce(0) { $0 + $1.height }
            + CGFloat(max(0, sizes.count - 1)) * gap
            + topPad * 2
        let maxWidth = sizes.map(\.width).max() ?? fallbackPageSize.width
        return CGSize(width: maxWidth, height: totalHeight)
    }
}

/// Pass-through view drawing one page's band of the ink composite; PDFKit keeps it attached
/// to the page through scrolling and zooming.
final class MacInkOverlayView: NSView {
    var image: CGImage?

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        guard let image, let context = NSGraphicsContext.current?.cgContext else { return }
        context.saveGState()
        context.interpolationQuality = .high
        if isFlipped {
            context.translateBy(x: 0, y: bounds.height)
            context.scaleBy(x: 1, y: -1)
        }
        context.draw(image, in: bounds)
        context.restoreGState()
    }
}

struct MacQuickLookView: NSViewRepresentable {
    let url: URL
    func makeNSView(context: Context) -> QLPreviewView {
        let v = QLPreviewView(frame: .zero, style: .normal)!
        v.autostarts = true
        v.previewItem = url as QLPreviewItem
        return v
    }
    func updateNSView(_ v: QLPreviewView, context: Context) {
        if (v.previewItem as? URL) != url {
            v.previewItem = url as QLPreviewItem
        }
    }
}
