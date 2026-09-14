import AppKit
import PDFKit
import QuickLookUI
import SwiftUI

/// PDF canvas with the iPad Apple Pencil ink overlay composited on top.
/// Reports text selections (for "Ask about this passage") and jumps to `findText` when set.
struct MacPDFKitView: NSViewRepresentable {
    let url: URL
    let overlayData: Data?
    let overlayOpacity: Double
    var findText: String? = nil
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
        context.coordinator.onSelection = onSelection
        context.coordinator.onPageChange = onPageChange

        if v.document?.documentURL != url {
            v.document = PDFDocument(url: url)
        }

        // Jump to a passage (thesis claim → memo text) when the caller sets findText.
        if let findText, !findText.isEmpty, findText != context.coordinator.lastFind {
            context.coordinator.lastFind = findText
            if let document = v.document {
                let needle = String(findText.split(separator: " ").prefix(7).joined(separator: " "))
                let hits = document.findString(needle, withOptions: [.caseInsensitive])
                if let first = hits.first {
                    v.go(to: first)
                    v.setCurrentSelection(first, animate: true)
                }
            }
        }

        // Manage overlay subview for iPad Apple Pencil drawing
        let overlayTag = 998811
        if let existingOverlay = v.subviews.first(where: { $0.tag == overlayTag }) {
            existingOverlay.removeFromSuperview()
        }

        if let overlayData, let image = NSImage(data: overlayData) {
            let imgView = NSImageView()
            imgView.tag = overlayTag
            imgView.image = image
            imgView.imageScaling = .scaleProportionallyUpOrDown
            imgView.alphaValue = overlayOpacity
            imgView.isEditable = false
            imgView.translatesAutoresizingMaskIntoConstraints = false

            v.addSubview(imgView)
            NSLayoutConstraint.activate([
                imgView.topAnchor.constraint(equalTo: v.topAnchor),
                imgView.bottomAnchor.constraint(equalTo: v.bottomAnchor),
                imgView.leadingAnchor.constraint(equalTo: v.leadingAnchor),
                imgView.trailingAnchor.constraint(equalTo: v.trailingAnchor),
            ])
        }
    }

    static func dismantleNSView(_ v: PDFView, coordinator: Coordinator) {
        NotificationCenter.default.removeObserver(coordinator)
    }

    final class Coordinator: NSObject {
        var onSelection: ((String?) -> Void)?
        var onPageChange: ((Int) -> Void)?
        var lastFind: String?

        init(onSelection: ((String?) -> Void)?, onPageChange: ((Int) -> Void)?) {
            self.onSelection = onSelection
            self.onPageChange = onPageChange
        }

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
