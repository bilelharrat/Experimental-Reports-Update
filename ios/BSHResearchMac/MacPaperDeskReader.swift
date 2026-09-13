import AppKit
import PDFKit
import QuickLookUI
import SwiftUI

struct MacPaperDeskReader: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var zoomScale: CGFloat = 1.0
    @State private var overlayOpacity: Double = 0.95

    var body: some View {
        VStack(spacing: 0) {
            // Modern macOS Reader Unified Toolbar
            HStack(spacing: 12) {
                Button {
                    store.closeMemo()
                    dismiss()
                } label: {
                    Label("Done", systemImage: "xmark.circle.fill")
                        .font(.body.weight(.medium))
                }
                .buttonStyle(.bordered)
                .keyboardShortcut(.cancelAction)

                Divider().frame(height: 18)

                VStack(alignment: .leading, spacing: 2) {
                    Text(store.openReportTitle.isEmpty ? "Investment Memo" : store.openReportTitle)
                        .font(.headline)
                        .lineLimit(1)
                    if !store.openReportId.isEmpty {
                        Text("ID: \(store.openReportId)")
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // iPad Pencil Annotations Badge & Toggle
                if store.openDocumentOverlayData != nil {
                    HStack(spacing: 6) {
                        Image(systemName: "pencil.tip.crop.circle.fill")
                            .foregroundStyle(store.showAnnotationOverlay ? Color.orange : Color.secondary)
                        Toggle("iPad Ink", isOn: $store.showAnnotationOverlay)
                            .toggleStyle(.switch)
                            .controlSize(.small)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .help("Toggle iPad Apple Pencil ink overlay")
                }

                Divider().frame(height: 18)

                // Language toggle if applicable
                Picker("Language", selection: $store.readerLanguage) {
                    Text("English").tag("en")
                    Text("中文").tag("zh")
                }
                .pickerStyle(.segmented)
                .frame(width: 140)

                // Open on Web bridge
                if !store.openReportId.isEmpty {
                    Button {
                        let url = MacConfig.webReportURL(id: store.openReportId)
                        MacConfig.openInBrowser(url)
                    } label: {
                        Label("Open on Web", systemImage: "safari")
                    }
                    .buttonStyle(.bordered)
                    .help("Open this memo in the Web Research Center (⌘⇧W)")
                    .keyboardShortcut("w", modifiers: [.command, .shift])
                }

                if let url = store.openDocumentURL {
                    ShareLink(item: url) {
                        Label("Share", systemImage: "square.and.arrow.up")
                    }
                    .buttonStyle(.bordered)
                    .help("Export or share memo document")
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial)

            Divider()

            // Document Canvas
            ZStack {
                Color(nsColor: .windowBackgroundColor)
                    .ignoresSafeArea()

                if let url = store.openDocumentURL {
                    GeometryReader { geo in
                        ZStack(alignment: .topLeading) {
                            if store.openDocumentIsPDF {
                                MacPDFKitView(
                                    url: url,
                                    overlayData: store.showAnnotationOverlay ? store.openDocumentOverlayData : nil,
                                    overlayOpacity: overlayOpacity
                                )
                            } else {
                                MacQuickLookView(url: url)
                            }
                        }
                        .frame(width: geo.size.width, height: geo.size.height)
                    }
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
                    .padding(16)
                } else if store.openingMemo {
                    VStack(spacing: 12) {
                        ProgressView()
                        Text("Loading research memo…")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ContentUnavailableView(
                        "No Document Loaded",
                        systemImage: "doc.text.magnifyingglass",
                        description: Text("Select an investment memo from the Research Desk to view.")
                    )
                }
            }
        }
        .frame(minWidth: 700, minHeight: 600)
    }
}

struct MacPDFKitView: NSViewRepresentable {
    let url: URL
    let overlayData: Data?
    let overlayOpacity: Double

    func makeNSView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.backgroundColor = NSColor.windowBackgroundColor
        v.document = PDFDocument(url: url)
        return v
    }

    func updateNSView(_ v: PDFView, context: Context) {
        if v.document?.documentURL != url {
            v.document = PDFDocument(url: url)
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
