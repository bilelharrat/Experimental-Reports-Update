import PDFKit
import PencilKit
import QuickLook
import SwiftUI
import UIKit
import WebKit

// MARK: - Document Converter (DOCX to PDF)

@MainActor
final class DocumentConverter: NSObject, WKNavigationDelegate {
    static let shared = DocumentConverter()
    private var webView: WKWebView?
    private var continuation: CheckedContinuation<URL?, Never>?
    private var targetURL: URL?

    func convertDocxToPDF(sourceURL: URL, destinationURL: URL) async -> URL? {
        if sourceURL.pathExtension.lowercased() == "pdf" {
            return sourceURL
        }
        if FileManager.default.fileExists(atPath: destinationURL.path) {
            return destinationURL
        }

        return await withCheckedContinuation { cont in
            self.continuation = cont
            self.targetURL = destinationURL
            let config = WKWebViewConfiguration()
            let wv = WKWebView(frame: CGRect(x: 0, y: 0, width: 612, height: 792), configuration: config)
            wv.navigationDelegate = self
            self.webView = wv
            wv.loadFileURL(sourceURL, allowingReadAccessTo: sourceURL.deletingLastPathComponent())
        }
    }

    nonisolated func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Task { @MainActor in
            let config = WKPDFConfiguration()
            webView.createPDF(configuration: config) { [weak self] result in
                guard let self = self else { return }
                switch result {
                case .success(let data):
                    if let dest = self.targetURL {
                        try? data.write(to: dest, options: .atomic)
                        self.continuation?.resume(returning: dest)
                    } else {
                        self.continuation?.resume(returning: nil)
                    }
                case .failure:
                    self.continuation?.resume(returning: nil)
                }
                self.continuation = nil
                self.webView = nil
            }
        }
    }

    nonisolated func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        Task { @MainActor in
            self.continuation?.resume(returning: nil)
            self.continuation = nil
            self.webView = nil
        }
    }

    nonisolated func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        Task { @MainActor in
            self.continuation?.resume(returning: nil)
            self.continuation = nil
            self.webView = nil
        }
    }
}

// MARK: - Native QuickLook Document Viewer

struct QuickLookDocViewer: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> QLPreviewController {
        let controller = QLPreviewController()
        controller.dataSource = context.coordinator
        return controller
    }

    func updateUIViewController(_ controller: QLPreviewController, context: Context) {
        if context.coordinator.url != url {
            context.coordinator.url = url
            controller.reloadData()
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url)
    }

    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        var url: URL

        init(url: URL) {
            self.url = url
        }

        func numberOfPreviewItems(in controller: QLPreviewController) -> Int {
            1
        }

        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
            url as NSURL
        }
    }
}

// MARK: - Legacy PencilCanvasView (backwards compatibility)

struct PencilCanvasView: UIViewRepresentable {
    @Binding var drawing: PKDrawing
    var isDrawingEnabled: Bool
    var showsToolPicker: Bool
    var canvasRef: Binding<PKCanvasView?>
    var replaceToken: Int
    var pencilOnly: Bool = false

    func makeCoordinator() -> Coordinator {
        Coordinator(drawing: $drawing)
    }

    func makeUIView(context: Context) -> PKCanvasView {
        let canvas = PKCanvasView()
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        canvas.drawing = drawing
        canvas.delegate = context.coordinator
        canvasRef.wrappedValue = canvas
        context.coordinator.appliedReplaceToken = replaceToken
        context.coordinator.toolPicker = PKToolPicker()
        return canvas
    }

    func updateUIView(_ canvas: PKCanvasView, context: Context) {
        canvasRef.wrappedValue = canvas
        canvas.isUserInteractionEnabled = isDrawingEnabled
        canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput

        if context.coordinator.appliedReplaceToken != replaceToken {
            context.coordinator.appliedReplaceToken = replaceToken
            context.coordinator.suppressDelegate = true
            canvas.drawing = drawing
            context.coordinator.suppressDelegate = false
        }

        guard let picker = context.coordinator.toolPicker else { return }
        if showsToolPicker, isDrawingEnabled {
            picker.setVisible(true, forFirstResponder: canvas)
            picker.addObserver(canvas)
            DispatchQueue.main.async {
                _ = canvas.becomeFirstResponder()
            }
        } else {
            picker.setVisible(false, forFirstResponder: canvas)
            picker.removeObserver(canvas)
            if canvas.isFirstResponder {
                canvas.resignFirstResponder()
            }
        }
    }

    static func dismantleUIView(_ canvas: PKCanvasView, coordinator: Coordinator) {
        coordinator.toolPicker?.setVisible(false, forFirstResponder: canvas)
        coordinator.toolPicker?.removeObserver(canvas)
    }

    final class Coordinator: NSObject, PKCanvasViewDelegate {
        var drawing: Binding<PKDrawing>
        var toolPicker: PKToolPicker?
        var appliedReplaceToken = -1
        var suppressDelegate = false

        init(drawing: Binding<PKDrawing>) {
            self.drawing = drawing
        }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            guard !suppressDelegate else { return }
            drawing.wrappedValue = canvasView.drawing
        }
    }
}

// MARK: - Paper desk reader

/// Full-screen memo reader optimized for deep reading + Apple Pencil on iPad.
/// Uses native continuous PDFView with page-locked Apple PencilKit annotations.
/// Drawings scroll, zoom, and stay locked to the exact document pages.
struct PaperDeskReader: View {
    let url: URL
    let reportId: String
    var companyId: String? = nil
    var companyName: String? = nil
    var onDismiss: () -> Void

    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var askPersona: AskPersonaStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.scenePhase) private var scenePhase

    @State private var drawing = PKDrawing()
    @State private var pageDrawings: [Int: PKDrawing] = [:]
    @State private var isAnnotating = false
    @State private var pencilOnly = AdaptiveLayout.isPad
    @State private var canvasView: PKCanvasView?
    @State private var replaceToken = 0
    @State private var saveTask: Task<Void, Never>?
    @State private var syncTask: Task<Void, Never>?
    @State private var strokeCount = 0
    @State private var suppressAutosave = false
    @State private var showAsk = false
    @State private var askPrompt: String?
    @State private var askSessionID = UUID()

    @State private var resolvedURL: URL?
    @State private var isConverting = false
    @State private var shareItems: [Any]?
    @State private var isPreparingShare = false

    private var supportsAnnotating: Bool {
        AdaptiveLayout.isPad || sizeClass == .regular
    }

    private var canAsk: Bool {
        guard let companyId, !companyId.isEmpty else { return false }
        return true
    }

    /// Trailing inspector keeps the memo visible on iPad; phone uses a sheet.
    private var useInlineAskPanel: Bool {
        AdaptiveLayout.isPad && canAsk
    }

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                documentPane
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                if showAsk, useInlineAskPanel, let companyId {
                    CopilotSheet(
                        companyId: companyId,
                        companyName: companyName,
                        surface: "ios_memo",
                        initialPrompt: askPrompt,
                        reportId: reportId,
                        embedded: true,
                        onClose: { closeAsk() }
                    )
                    .id(askSessionID)
                    .frame(width: askPanelWidth(for: geo.size.width))
                    .background(Color(.systemBackground))
                    .overlay(alignment: .leading) {
                        Divider()
                    }
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }
            .animation(.snappy(duration: 0.28), value: showAsk)
        }
        .statusBarHidden(false)
        .sheet(isPresented: Binding(
            get: { showAsk && !useInlineAskPanel },
            set: { if !$0 { closeAsk() } }
        )) {
            if let companyId {
                CopilotSheet(
                    companyId: companyId,
                    companyName: companyName,
                    surface: "ios_memo",
                    initialPrompt: askPrompt,
                    reportId: reportId,
                    onClose: { closeAsk() }
                )
                .id(askSessionID)
            }
        }
        .sheet(isPresented: Binding(
            get: { shareItems != nil },
            set: { if !$0 { shareItems = nil } }
        )) {
            if let items = shareItems {
                ShareSheet(items: items)
            }
        }
        .task {
            await prepareDocument()
        }
        .onAppear {
            loadAnnotations()
        }
        .onChange(of: strokeCount) { _, _ in
            guard !suppressAutosave else { return }
            scheduleSave()
        }
        .onChange(of: isAnnotating) { _, annotating in
            if !annotating {
                persistNow(pushRemote: true)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background || phase == .inactive {
                persistNow(pushRemote: true)
            }
        }
        .onDisappear {
            persistNow(pushRemote: true)
            saveTask?.cancel()
            syncTask?.cancel()
        }
    }

    // MARK: - Document Pane & Navigation

    private var documentPane: some View {
        documentStack
            .overlay(alignment: .topLeading) {
                Button(action: closeReader) {
                    Text(language.t("common.done"))
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 9)
                }
                .buttonStyle(.borderedProminent)
                .clipShape(Capsule(style: .continuous))
                .shadow(color: .black.opacity(0.14), radius: 10, y: 3)
                .accessibilityLabel(language.t("common.done"))
                .padding(.top, 10)
                .padding(.leading, 14)
            }
            .overlay(alignment: .topTrailing) {
                HStack(spacing: 10) {
                    // Share Button (Annotated PDF export)
                    Button {
                        Task { await handleShare() }
                    } label: {
                        Group {
                            if isPreparingShare {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Image(systemName: "square.and.arrow.up")
                                    .font(.body.weight(.semibold))
                            }
                        }
                        .frame(width: 42, height: 42)
                        .background {
                            Circle()
                                .fill(.ultraThinMaterial)
                                .shadow(color: .black.opacity(0.12), radius: 10, y: 3)
                        }
                        .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(isPreparingShare)
                    .accessibilityLabel(language.t("common.share"))

                    if canAsk {
                        Button {
                            openAsk(withSelection: nil)
                        } label: {
                            AskMark(size: 28)
                                .frame(width: 42, height: 42)
                                .background {
                                    Circle()
                                        .fill(.ultraThinMaterial)
                                        .shadow(color: .black.opacity(0.12), radius: 10, y: 3)
                                }
                                .contentShape(Circle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(askPersona.investor.inviteTitle(lang: language.language))
                    }
                }
                .padding(.top, 10)
                .padding(.trailing, 14)
            }
            .overlay(alignment: .bottom) {
                if resolvedURL?.pathExtension.lowercased() == "pdf" {
                    floatingAnnotationControls
                        .padding(.bottom, 16)
                }
            }
    }

    @ViewBuilder
    private var documentStack: some View {
        ZStack {
            if let activeURL = resolvedURL {
                if activeURL.pathExtension.lowercased() == "pdf" {
                    MemoPaperDocumentView(
                        url: activeURL,
                        drawing: $drawing,
                        pageDrawings: $pageDrawings,
                        isAnnotating: isAnnotating,
                        showsToolPicker: isAnnotating && supportsAnnotating,
                        canvasRef: $canvasView,
                        replaceToken: replaceToken,
                        pencilOnly: pencilOnly,
                        askMenuTitle: askPersona.investor.inviteTitle(lang: language.language),
                        onAskSelection: { text in openAsk(withSelection: text) },
                        onPageDrawingsChanged: { updated in
                            pageDrawings = updated
                            strokeCount = updated.values.reduce(0) { $0 + $1.strokes.count }
                        }
                    )
                    .ignoresSafeArea()
                } else {
                    QuickLookDocViewer(url: activeURL)
                        .ignoresSafeArea()
                }
            } else if isConverting {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)
                    Text("Preparing document…")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(red: 0.89, green: 0.89, blue: 0.91).ignoresSafeArea())
            } else {
                QuickLookDocViewer(url: url)
                    .ignoresSafeArea()
            }
        }
    }

    private func askPanelWidth(for totalWidth: CGFloat) -> CGFloat {
        min(420, max(320, totalWidth * 0.42))
    }

    // MARK: - Floating Annotation Controls

    private var floatingAnnotationControls: some View {
        HStack(spacing: 8) {
            if isAnnotating {
                // Undo
                toolButton(
                    systemName: "arrow.uturn.backward",
                    label: language.t("research.ink_undo"),
                    disabled: strokeCount == 0
                ) {
                    canvasView?.undoManager?.undo()
                }

                // Apple Pencil vs Finger Drawing Toggle
                if AdaptiveLayout.isPad {
                    Button {
                        withAnimation(.snappy(duration: 0.2)) {
                            pencilOnly.toggle()
                        }
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: pencilOnly ? "applepencil.and.scribble" : "hand.draw")
                            Text(pencilOnly ? "Pencil Only" : "Draw with Finger")
                                .font(.caption2.weight(.bold))
                        }
                        .padding(.horizontal, 10)
                        .frame(height: 42)
                        .background(
                            Capsule().fill(pencilOnly ? Color.secondary.opacity(0.12) : Color.orange.opacity(0.2))
                        )
                        .foregroundStyle(pencilOnly ? Color.primary : Color.orange)
                    }
                    .buttonStyle(.plain)
                    .help(pencilOnly ? "Only Apple Pencil draws; fingers scroll" : "Finger draws on document")
                }

                // Clear
                toolButton(
                    systemName: "trash",
                    label: language.t("research.ink_clear"),
                    disabled: strokeCount == 0,
                    role: .destructive
                ) {
                    pageDrawings.removeAll()
                    drawing = PKDrawing()
                    strokeCount = 0
                    replaceToken += 1
                    ReportAnnotationStore.clear(reportId: reportId)
                    Task {
                        _ = await ReportAnnotationStore.push(
                            PKDrawing(),
                            reportId: reportId,
                            canvasSize: currentCanvasSize()
                        )
                    }
                }
            }

            // Annotate Toggle Button
            Button {
                withAnimation(.snappy(duration: 0.2)) {
                    isAnnotating.toggle()
                }
            } label: {
                Label(
                    language.t(isAnnotating ? "research.ink_done" : "research.ink_annotate"),
                    systemImage: isAnnotating ? "pencil.tip.crop.circle.fill" : "pencil.tip.crop.circle"
                )
                .font(.subheadline.weight(.semibold))
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    Capsule(style: .continuous)
                        .fill(isAnnotating ? Color.accentColor : Color.primary.opacity(0.08))
                )
                .foregroundStyle(isAnnotating ? Color.white : Color.primary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(language.t(isAnnotating ? "research.ink_done" : "research.ink_annotate"))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background {
            Capsule(style: .continuous)
                .fill(.ultraThinMaterial)
                .shadow(color: .black.opacity(0.14), radius: 14, y: 5)
        }
        .frame(maxWidth: AdaptiveLayout.isPad ? 560 : .infinity)
        .frame(maxWidth: .infinity)
    }

    private func toolButton(
        systemName: String,
        label: String,
        disabled: Bool = false,
        role: ButtonRole? = nil,
        action: @escaping () -> Void
    ) -> some View {
        Button(role: role, action: action) {
            Image(systemName: systemName)
                .font(.body.weight(.semibold))
                .frame(width: 42, height: 42)
                .background(Circle().fill(Color.primary.opacity(0.08)))
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.35 : 1)
        .accessibilityLabel(label)
    }

    // MARK: - Document Preparation & Share

    private func prepareDocument() async {
        if url.pathExtension.lowercased() == "pdf" {
            resolvedURL = url
            return
        }

        // If a converted PDF already exists in temp, use it immediately
        let tempDir = FileManager.default.temporaryDirectory
        let safeName = reportId.replacingOccurrences(of: "/", with: "_")
        let dest = tempDir.appendingPathComponent("\(safeName)_converted.pdf")
        if FileManager.default.fileExists(atPath: dest.path) {
            resolvedURL = dest
            return
        }

        // DOCX or other office format: try quick conversion or fallback to native QuickLook
        isConverting = true
        let conversionTask = Task { @MainActor () -> URL? in
            await DocumentConverter.shared.convertDocxToPDF(sourceURL: url, destinationURL: dest)
        }
        let timeoutTask = Task { () -> URL? in
            try? await Task.sleep(nanoseconds: 2_000_000_000) // 2.0s max wait
            return nil
        }

        let pdfURL = await withTaskGroup(of: URL?.self) { group in
            group.addTask { await conversionTask.value }
            group.addTask { await timeoutTask.value }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }

        if let pdf = pdfURL {
            resolvedURL = pdf
        } else {
            // Native QuickLook handles .docx with complete formatting and pinch-zoom
            resolvedURL = url
        }
        isConverting = false
    }

    private func handleShare() async {
        isPreparingShare = true
        defer { isPreparingShare = false }

        guard let activeURL = resolvedURL else { return }

        // If there are annotations, bake them into the actual PDF for export
        if strokeCount > 0, let doc = PDFDocument(url: activeURL) {
            if let annotatedURL = ReportAnnotationStore.renderAnnotatedPDF(
                document: doc,
                pageDrawings: pageDrawings,
                reportId: reportId
            ) {
                shareItems = [annotatedURL]
                return
            }
        }

        shareItems = [activeURL]
    }

    // MARK: - Dismiss / Ask

    private func closeReader() {
        persistNow(pushRemote: true)
        onDismiss()
        dismiss()
    }

    private func openAsk(withSelection selection: String?) {
        guard canAsk else { return }
        if let selection {
            askPrompt = Self.prompt(forSelection: selection)
        } else {
            askPrompt = nil
        }
        askSessionID = UUID()
        withAnimation(.snappy(duration: 0.28)) {
            showAsk = true
        }
    }

    private func closeAsk() {
        withAnimation(.snappy(duration: 0.28)) {
            showAsk = false
        }
        askPrompt = nil
    }

    private static func prompt(forSelection text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        let clipped: String
        if trimmed.count > 1400 {
            clipped = String(trimmed.prefix(1400)) + "…"
        } else {
            clipped = trimmed
        }
        return "Explain / challenge this:\n\n\"\(clipped)\""
    }

    // MARK: - Persistence & Sync

    private func loadAnnotations() {
        suppressAutosave = true
        pageDrawings = ReportAnnotationStore.loadPageDrawings(reportId: reportId)
        drawing = ReportAnnotationStore.load(reportId: reportId)
        strokeCount = pageDrawings.values.reduce(0) { $0 + $1.strokes.count }
        replaceToken += 1
        suppressAutosave = false
        syncTask?.cancel()
        syncTask = Task { await pullRemoteIfNeeded() }
    }

    private func currentCanvasSize() -> CGSize? {
        guard let canvasView else { return nil }
        let size = canvasView.bounds.size
        guard size.width > 1, size.height > 1 else { return nil }
        return size
    }

    private func scheduleSave() {
        saveTask?.cancel()
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            persistNow(pushRemote: true)
        }
    }

    private func persistNow(pushRemote: Bool) {
        saveTask?.cancel()
        ReportAnnotationStore.savePageDrawings(pageDrawings, reportId: reportId)

        guard pushRemote else { return }
        let snapshot = drawing
        let size = currentCanvasSize()
        Task {
            _ = await ReportAnnotationStore.push(
                snapshot,
                reportId: reportId,
                canvasSize: size
            )
        }
    }

    private func pullRemoteIfNeeded() async {
        guard let remote = await ReportAnnotationStore.pullIfNewer(reportId: reportId) else {
            return
        }
        await MainActor.run {
            suppressAutosave = true
            drawing = remote
            // Refresh per-page drawings if local was empty
            if pageDrawings.isEmpty && !remote.strokes.isEmpty {
                pageDrawings = [0: remote]
            }
            strokeCount = pageDrawings.values.reduce(0) { $0 + $1.strokes.count }
            replaceToken += 1
            suppressAutosave = false
        }
    }
}

/// Back-compat alias used by older call sites / previews.
typealias AnnotatableDocumentPreview = PaperDeskReader
