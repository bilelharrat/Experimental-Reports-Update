import PencilKit
import SwiftUI
import UIKit

/// Transparent PencilKit canvas for freehand ink over a document preview (DOCX / QL fallback).
struct PencilCanvasView: UIViewRepresentable {
    @Binding var drawing: PKDrawing
    var isDrawingEnabled: Bool
    var showsToolPicker: Bool
    var canvasRef: Binding<PKCanvasView?>
    /// Bump to force-replace the canvas drawing from the binding (clear / load).
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
/// Uses a paper-desk PDF surface when the file is a PDF; falls back to Quick Look for DOCX.
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
    @State private var isAnnotating = false
    @State private var canvasView: PKCanvasView?
    @State private var replaceToken = 0
    @State private var saveTask: Task<Void, Never>?
    @State private var syncTask: Task<Void, Never>?
    @State private var strokeCount = 0
    @State private var suppressAutosave = false
    @State private var showAsk = false
    @State private var askPrompt: String?
    @State private var askSessionID = UUID()

    private var supportsAnnotating: Bool {
        AdaptiveLayout.isPad || sizeClass == .regular
    }

    private var isPDF: Bool {
        url.pathExtension.lowercased() == "pdf"
    }

    private var usePaperDesk: Bool {
        isPDF
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
        .onAppear {
            suppressAutosave = true
            let local = ReportAnnotationStore.loadLocal(reportId: reportId)
            drawing = local.drawing
            strokeCount = local.drawing.strokes.count
            replaceToken += 1
            suppressAutosave = false
            syncTask?.cancel()
            syncTask = Task { await pullRemoteIfNeeded() }
        }
        .onChange(of: drawing.strokes.count) { _, count in
            strokeCount = count
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

    /// Document + always-visible floating chrome. Scoped here so Share/Ask never
    /// sit under the inline Copilot inspector.
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
                    ShareLink(item: url) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.body.weight(.semibold))
                            .frame(width: 42, height: 42)
                            .background {
                                Circle()
                                    .fill(.ultraThinMaterial)
                                    .shadow(color: .black.opacity(0.12), radius: 10, y: 3)
                            }
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
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
                if supportsAnnotating {
                    floatingAnnotationControls
                        .padding(.bottom, AdaptiveLayout.isPad ? 22 : 12)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.snappy(duration: 0.22), value: isAnnotating)
    }

    @ViewBuilder
    private var documentStack: some View {
        ZStack {
            if usePaperDesk {
                MemoPaperDocumentView(
                    url: url,
                    drawing: $drawing,
                    isAnnotating: isAnnotating,
                    showsToolPicker: isAnnotating && supportsAnnotating,
                    canvasRef: $canvasView,
                    replaceToken: replaceToken,
                    pencilOnly: AdaptiveLayout.isPad,
                    askMenuTitle: askPersona.investor.inviteTitle(lang: language.language),
                    onAskSelection: { text in openAsk(withSelection: text) }
                )
                .ignoresSafeArea()
            } else {
                // DOCX / other: full-bleed Quick Look with ink overlay (not scroll-synced).
                ZStack {
                    Color(red: 0.89, green: 0.89, blue: 0.90)
                        .ignoresSafeArea()
                    QuickLookPreview(url: url, hidesNavigationChrome: true)
                        .ignoresSafeArea(edges: .bottom)
                        .allowsHitTesting(!isAnnotating)

                    PencilCanvasView(
                        drawing: $drawing,
                        isDrawingEnabled: isAnnotating,
                        showsToolPicker: isAnnotating && supportsAnnotating,
                        canvasRef: $canvasView,
                        replaceToken: replaceToken,
                        pencilOnly: AdaptiveLayout.isPad
                    )
                    .ignoresSafeArea(edges: .bottom)
                    .allowsHitTesting(isAnnotating)
                    .opacity(strokeCount == 0 && !isAnnotating ? 0 : 1)
                }
            }
        }
    }

    private func askPanelWidth(for totalWidth: CGFloat) -> CGFloat {
        min(420, max(320, totalWidth * 0.42))
    }

    // MARK: Floating chrome (always visible — no auto-hide, no full-width bar)

    private var floatingAnnotationControls: some View {
        HStack(spacing: 8) {
            if isAnnotating {
                toolButton(
                    systemName: "arrow.uturn.backward",
                    label: language.t("research.ink_undo"),
                    disabled: strokeCount == 0
                ) {
                    canvasView?.undoManager?.undo()
                    syncFromCanvas()
                }

                toolButton(
                    systemName: "trash",
                    label: language.t("research.ink_clear"),
                    disabled: strokeCount == 0,
                    role: .destructive
                ) {
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
        .frame(maxWidth: AdaptiveLayout.isPad ? 520 : .infinity)
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

    // MARK: Dismiss / Ask

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

    // MARK: Persistence

    private func currentCanvasSize() -> CGSize? {
        guard let canvasView else { return nil }
        let size = canvasView.bounds.size
        guard size.width > 1, size.height > 1 else { return nil }
        return size
    }

    private func syncFromCanvas() {
        guard let canvasView else { return }
        drawing = canvasView.drawing
        strokeCount = canvasView.drawing.strokes.count
        scheduleSave()
    }

    private func scheduleSave() {
        saveTask?.cancel()
        // Snapshot after stroke end; debounce local+cloud write (~0.4s).
        let snapshot = drawing
        let size = currentCanvasSize()
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            let latest = canvasView?.drawing ?? snapshot
            ReportAnnotationStore.save(latest, reportId: reportId, canvasSize: size)
            _ = await ReportAnnotationStore.push(
                latest,
                reportId: reportId,
                canvasSize: size ?? currentCanvasSize()
            )
        }
    }

    private func persistNow(pushRemote: Bool) {
        saveTask?.cancel()
        if let canvasView {
            drawing = canvasView.drawing
            strokeCount = canvasView.drawing.strokes.count
        }
        let size = currentCanvasSize()
        ReportAnnotationStore.save(drawing, reportId: reportId, canvasSize: size)
        guard pushRemote else { return }
        let snapshot = drawing
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
            strokeCount = remote.strokes.count
            replaceToken += 1
            suppressAutosave = false
        }
    }
}

/// Back-compat alias used by older call sites / previews.
typealias AnnotatableDocumentPreview = PaperDeskReader
