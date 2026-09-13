import PDFKit
import QuickLookUI
import SwiftUI

struct MacPaperDeskReader: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color(red: 0.89, green: 0.89, blue: 0.90).ignoresSafeArea()

            VStack(spacing: 0) {
                HStack {
                    Button {
                        store.closeMemo()
                        dismiss()
                    } label: {
                        Text("Done")
                            .font(.body.weight(.semibold))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(.ultraThinMaterial, in: Capsule())
                    }
                    .buttonStyle(.plain)

                    Text(store.openReportTitle)
                        .font(.headline)
                        .lineLimit(1)

                    Spacer()

                    if let url = store.openDocumentURL {
                        ShareLink(item: url) {
                            Image(systemName: "square.and.arrow.up")
                                .padding(8)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(12)

                if let url = store.openDocumentURL {
                    Group {
                        if store.openDocumentIsPDF {
                            MacPDFKitView(url: url)
                        } else {
                            MacQuickLookView(url: url)
                        }
                    }
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .shadow(color: .black.opacity(0.14), radius: 16, y: 6)
                    .padding(.horizontal, 28)
                    .padding(.bottom, 24)
                } else {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
    }
}

struct MacPDFKitView: NSViewRepresentable {
    let url: URL
    func makeNSView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.backgroundColor = .clear
        v.document = PDFDocument(url: url)
        return v
    }
    func updateNSView(_ v: PDFView, context: Context) {
        if v.document?.documentURL != url {
            v.document = PDFDocument(url: url)
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
