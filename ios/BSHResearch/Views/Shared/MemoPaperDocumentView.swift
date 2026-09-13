import OSLog
import PDFKit
import PencilKit
import SwiftUI
import UIKit

private let inkLog = Logger(subsystem: "com.bilelharrrat.bshresearch", category: "ink")

// MARK: - Ink controller (state + persistence, owned by the SwiftUI reader)

/// Owns the per-page ink for one open report and persists it off the main thread.
///
/// The PencilKit canvases inside `PaperDeskPDFHostView` are the live surface; this
/// object is the source of truth the host reads when it (re)creates a page overlay,
/// and the only place that talks to `ReportAnnotationStore`. All disk / network /
/// PNG work runs on the `InkPersistence` actor so nothing heavy ever executes on the
/// main thread while the user is writing.
@MainActor
final class PaperDeskInkController: ObservableObject {
    let reportId: String

    /// Total committed strokes across pages — drives Undo / Clear enablement.
    @Published private(set) var strokeCount = 0
    /// Height of the docked `PKToolPicker` overlapping the bottom of the reader (0 when floating/hidden).
    @Published private(set) var toolPickerBottomInset: CGFloat = 0

    private(set) var pageDrawings: [Int: PKDrawing] = [:]
    private(set) var pageSizes: [CGSize] = []

    weak var host: PaperDeskPDFHostView?

    private let persistence = InkPersistence()
    private var localSaveTask: Task<Void, Never>?
    private var pushTask: Task<Void, Never>?
    private var pullTask: Task<Void, Never>?

    init(reportId: String) {
        self.reportId = reportId
        pageDrawings = ReportAnnotationStore.loadPageDrawings(reportId: reportId)
        strokeCount = Self.count(pageDrawings)
    }

    // MARK: Host → controller

    func documentDidLoad(pageSizes: [CGSize]) {
        self.pageSizes = pageSizes
        pullRemote()
    }

    func drawing(forPage index: Int) -> PKDrawing {
        pageDrawings[index] ?? PKDrawing()
    }

    /// Called once per committed stroke / erase / undo. Cheap: updates state and arms timers.
    func noteDrawingChanged(page index: Int, drawing: PKDrawing) {
        pageDrawings[index] = drawing
        strokeCount = Self.count(pageDrawings)
        scheduleLocalSave(after: 1.0)
        schedulePush(after: 4.0)
    }

    func setToolPickerBottomInset(_ inset: CGFloat) {
        guard abs(toolPickerBottomInset - inset) > 0.5 else { return }
        toolPickerBottomInset = inset
    }

    // MARK: Reader → controller

    func undo() {
        host?.undoLastStroke()
    }

    func clearAll() {
        pageDrawings.removeAll()
        strokeCount = 0
        host?.clearAllCanvases()
        localSaveTask?.cancel()
        pushTask?.cancel()
        let reportId = reportId
        let persistence = persistence
        Task.detached(priority: .utility) {
            await persistence.clear(reportId: reportId)
        }
    }

    /// Persist now (local + cloud). Safe to call often; work is serialized off-main.
    func flush() {
        localSaveTask?.cancel()
        pushTask?.cancel()
        let snapshot = pageDrawings
        let sizes = pageSizes
        let reportId = reportId
        let persistence = persistence
        Task.detached(priority: .utility) {
            await persistence.saveLocal(snapshot, reportId: reportId, pageSizes: sizes)
            await persistence.push(snapshot, reportId: reportId, pageSizes: sizes)
        }
    }

    // MARK: Timers

    private func scheduleLocalSave(after delay: TimeInterval) {
        localSaveTask?.cancel()
        localSaveTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, let self else { return }
            let snapshot = self.pageDrawings
            let sizes = self.pageSizes
            let reportId = self.reportId
            let persistence = self.persistence
            Task.detached(priority: .utility) {
                await persistence.saveLocal(snapshot, reportId: reportId, pageSizes: sizes)
            }
        }
    }

    private func schedulePush(after delay: TimeInterval) {
        pushTask?.cancel()
        pushTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, let self else { return }
            // Never compete with a live stroke for the GPU — try again shortly.
            if self.host?.strokeInFlight == true {
                self.schedulePush(after: 2.0)
                return
            }
            let snapshot = self.pageDrawings
            let sizes = self.pageSizes
            let reportId = self.reportId
            let persistence = self.persistence
            Task.detached(priority: .utility) {
                await persistence.push(snapshot, reportId: reportId, pageSizes: sizes)
            }
        }
    }

    private func pullRemote() {
        pullTask?.cancel()
        let reportId = reportId
        let sizes = pageSizes
        let persistence = persistence
        pullTask = Task { [weak self] in
            guard let remote = await persistence.pull(reportId: reportId) else { return }
            let split = ReportAnnotationStore.splitComposite(remote, pageSizes: sizes)
            guard !Task.isCancelled, let self else { return }
            self.pageDrawings = split
            self.strokeCount = Self.count(split)
            self.host?.applyPageDrawings(split)
        }
    }

    private static func count(_ pages: [Int: PKDrawing]) -> Int {
        pages.values.reduce(0) { $0 + $1.strokes.count }
    }
}

/// Serializes every disk / network / image-render operation for the ink store.
actor InkPersistence {
    func saveLocal(_ pages: [Int: PKDrawing], reportId: String, pageSizes: [CGSize]) {
        ReportAnnotationStore.savePageDrawings(pages, reportId: reportId, pageSizes: pageSizes)
    }

    func push(_ pages: [Int: PKDrawing], reportId: String, pageSizes: [CGSize]) async {
        let composite = ReportAnnotationStore.compositeDrawing(from: pages, pageSizes: pageSizes)
        let size = ReportAnnotationStore.compositeCanvasSize(pageSizes: pageSizes)
        _ = await ReportAnnotationStore.push(composite, reportId: reportId, canvasSize: size)
    }

    func pull(reportId: String) async -> PKDrawing? {
        await ReportAnnotationStore.pullIfNewer(reportId: reportId)
    }

    func clear(reportId: String) async {
        ReportAnnotationStore.clear(reportId: reportId)
        _ = await ReportAnnotationStore.push(PKDrawing(), reportId: reportId, canvasSize: nil)
    }
}

// MARK: - SwiftUI wrapper

/// Full-bleed native PDF reader with page-locked Apple Pencil & finger annotations via `PDFPageOverlayViewProvider`.
///
/// Live-ink rules (these are what keep PencilKit's in-flight stroke visible on iPad):
/// - One `PKCanvasView` per page, hosted by PDFKit itself; `isInMarkupMode` routes Pencil to the
///   overlays and fingers to scrolling. No gesture-recognizer surgery, no hit-test tricks.
/// - Nothing touches the canvas hierarchy, first responder, tool, or PDF layout while a
///   stroke is in flight (`strokeInFlight` gates every mutation and defers it to stroke end).
/// - SwiftUI only ever receives a stroke *count*; drawings never round-trip through view state.
/// - Persistence and the cloud PNG render run on a background actor, seconds after the last stroke.
struct MemoPaperDocumentView: UIViewRepresentable {
    let url: URL
    let controller: PaperDeskInkController
    var isAnnotating: Bool
    var showsToolPicker: Bool
    var pencilOnly: Bool
    var askMenuTitle: String = "Ask Warren"
    var onAskSelection: ((String) -> Void)? = nil

    func makeUIView(context: Context) -> PaperDeskPDFHostView {
        let host = PaperDeskPDFHostView()
        host.controller = controller
        controller.host = host
        host.askMenuTitle = askMenuTitle
        host.onAskSelection = onAskSelection
        host.load(url: url)
        host.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
        return host
    }

    func updateUIView(_ host: PaperDeskPDFHostView, context: Context) {
        host.askMenuTitle = askMenuTitle
        host.onAskSelection = onAskSelection
        if host.currentURL != url {
            host.load(url: url)
        }
        host.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
    }

    static func dismantleUIView(_ host: PaperDeskPDFHostView, coordinator: ()) {
        host.teardown()
    }
}

// MARK: - Page canvas

final class PageCanvasView: PKCanvasView {
    override var canBecomeFirstResponder: Bool { true }
}

// MARK: - Host view

final class PaperDeskPDFHostView: UIView, PDFPageOverlayViewProvider, PKCanvasViewDelegate, PKToolPickerObserver {
    weak var controller: PaperDeskInkController?
    var askMenuTitle: String = "Ask Warren"
    var onAskSelection: ((String) -> Void)?

    let pdfView = PDFView()
    private let toolPicker = PKToolPicker()

    private var canvasMap: [PDFPage: PageCanvasView] = [:]
    /// Overlays PDFKit currently has on screen, in display order.
    private var displayedCanvases: [PageCanvasView] = []
    private weak var lastEditedCanvas: PageCanvasView?

    private var isAnnotating = false
    private var pencilOnly = true
    private var showsToolPicker = false
    private(set) var currentURL: URL?

    /// True from tool-down to tool-up. Every hierarchy / responder / layout mutation is gated on it.
    private(set) var strokeInFlight = false
    private var pendingConfig: (annotating: Bool, pencilOnly: Bool, picker: Bool)?
    private var pendingResponderFix = false
    private var pendingPageDrawings: [Int: PKDrawing]?
    private var pendingClear = false

    private let askCalloutButton: UIButton = {
        let btn = UIButton(type: .system)
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .capsule
        config.buttonSize = .mini
        config.baseBackgroundColor = UIColor(red: 0.10, green: 0.12, blue: 0.18, alpha: 0.94)
        config.baseForegroundColor = .white
        config.imagePadding = 6
        config.contentInsets = NSDirectionalEdgeInsets(top: 8, leading: 14, bottom: 8, trailing: 14)
        btn.configuration = config
        btn.layer.shadowColor = UIColor.black.cgColor
        btn.layer.shadowOpacity = 0.22
        btn.layer.shadowOffset = CGSize(width: 0, height: 4)
        btn.layer.shadowRadius = 8
        btn.alpha = 0
        btn.isHidden = true
        return btn
    }()

    private var selectedText: String?

    override init(frame: CGRect) {
        super.init(frame: frame)
        setup()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setup()
    }

    private func setup() {
        backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1.0)

        pdfView.translatesAutoresizingMaskIntoConstraints = false
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.displayBox = .mediaBox
        pdfView.autoScales = true
        pdfView.displaysPageBreaks = true
        pdfView.pageBreakMargins = UIEdgeInsets(top: 14, left: 0, bottom: 14, right: 0)
        pdfView.backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1.0)
        pdfView.usePageViewController(false)
        pdfView.pageOverlayViewProvider = self
        addSubview(pdfView)

        askCalloutButton.translatesAutoresizingMaskIntoConstraints = false
        askCalloutButton.addTarget(self, action: #selector(handleAskCalloutTapped), for: .touchUpInside)
        addSubview(askCalloutButton)

        NSLayoutConstraint.activate([
            pdfView.topAnchor.constraint(equalTo: topAnchor),
            pdfView.bottomAnchor.constraint(equalTo: bottomAnchor),
            pdfView.leadingAnchor.constraint(equalTo: leadingAnchor),
            pdfView.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])

        toolPicker.selectedTool = PKInkingTool(.pen, color: .black, width: 3)
        toolPicker.addObserver(self)

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleSelectionChanged),
            name: .PDFViewSelectionChanged,
            object: pdfView
        )
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else { return }
        DispatchQueue.main.async { [weak self] in
            self?.ensureToolPickerActive()
            self?.reportToolPickerInset()
        }
    }

    func teardown() {
        NotificationCenter.default.removeObserver(self)
        toolPicker.removeObserver(self)
        if let responder = displayedCanvases.first(where: { $0.isFirstResponder }) ?? canvasMap.values.first {
            toolPicker.setVisible(false, forFirstResponder: responder)
            if responder.isFirstResponder {
                responder.resignFirstResponder()
            }
        }
        for canvas in canvasMap.values {
            toolPicker.removeObserver(canvas)
            canvas.delegate = nil
        }
        canvasMap.removeAll()
        displayedCanvases.removeAll()
    }

    // MARK: - Document loading

    func load(url: URL) {
        currentURL = url
        guard let doc = PDFDocument(url: url) else { return }

        for canvas in canvasMap.values {
            toolPicker.removeObserver(canvas)
            canvas.delegate = nil
        }
        canvasMap.removeAll()
        displayedCanvases.removeAll()
        lastEditedCanvas = nil

        pdfView.document = doc
        pdfView.isInMarkupMode = isAnnotating

        var sizes: [CGSize] = []
        for i in 0..<doc.pageCount {
            if let page = doc.page(at: i) {
                sizes.append(page.bounds(for: .mediaBox).size)
            }
        }
        controller?.documentDidLoad(pageSizes: sizes)

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.pdfView.autoScales = true
            if let firstPage = doc.page(at: 0) {
                self.pdfView.go(to: firstPage)
            }
        }
    }

    /// Replace on-screen ink with `drawings` (e.g. after a cloud pull). Deferred while a stroke is in flight.
    func applyPageDrawings(_ drawings: [Int: PKDrawing]) {
        guard !strokeInFlight else {
            pendingPageDrawings = drawings
            return
        }
        for canvas in canvasMap.values {
            let target = drawings[canvas.tag] ?? PKDrawing()
            let current = canvas.drawing
            if current.strokes.count != target.strokes.count || current.bounds != target.bounds {
                canvas.drawing = target
            }
        }
    }

    func clearAllCanvases() {
        guard !strokeInFlight else {
            pendingClear = true
            return
        }
        for canvas in canvasMap.values where !canvas.drawing.strokes.isEmpty {
            canvas.drawing = PKDrawing()
        }
    }

    func undoLastStroke() {
        guard !strokeInFlight else { return }
        guard let canvas = lastEditedCanvas ?? displayedCanvases.first(where: { !$0.drawing.strokes.isEmpty }) else {
            return
        }
        if let undoManager = canvas.undoManager, undoManager.canUndo {
            undoManager.undo()
        } else {
            var drawing = canvas.drawing
            guard !drawing.strokes.isEmpty else { return }
            drawing.strokes.removeLast()
            canvas.drawing = drawing
        }
        controller?.noteDrawingChanged(page: canvas.tag, drawing: canvas.drawing)
    }

    // MARK: - Annotation mode & tool picker

    func setAnnotating(_ annotating: Bool, pencilOnly: Bool, showsToolPicker: Bool) {
        let changed = self.isAnnotating != annotating
            || self.pencilOnly != pencilOnly
            || self.showsToolPicker != showsToolPicker
        guard changed else {
            ensureToolPickerActive()
            return
        }
        guard !strokeInFlight else {
            pendingConfig = (annotating, pencilOnly, showsToolPicker)
            return
        }

        inkLog.info("setAnnotating \(annotating) pencilOnly=\(pencilOnly) picker=\(showsToolPicker)")
        self.isAnnotating = annotating
        self.pencilOnly = pencilOnly
        self.showsToolPicker = showsToolPicker

        pdfView.isInMarkupMode = annotating
        if annotating {
            hideAskCallout()
            pdfView.clearSelection()
        }

        for canvas in canvasMap.values {
            canvas.isUserInteractionEnabled = annotating
            canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        }

        if annotating && showsToolPicker {
            ensureToolPickerActive()
        } else {
            for canvas in canvasMap.values where canvas.isFirstResponder {
                toolPicker.setVisible(false, forFirstResponder: canvas)
                canvas.resignFirstResponder()
            }
            reportToolPickerInset()
        }
    }

    /// Show the tool picker for one on-screen canvas if none currently owns it. Cheap no-op otherwise.
    private func ensureToolPickerActive() {
        guard isAnnotating, showsToolPicker, window != nil, !strokeInFlight else { return }
        if displayedCanvases.contains(where: { $0.isFirstResponder }) { return }
        let target = pdfView.currentPage.flatMap { canvasMap[$0] }
            ?? displayedCanvases.first
            ?? canvasMap.values.first
        guard let target else { return }
        toolPicker.setVisible(true, forFirstResponder: target)
        _ = target.becomeFirstResponder()
        inkLog.info("tool picker activated for page \(target.tag)")
    }

    private func reportToolPickerInset() {
        guard let controller else { return }
        var inset: CGFloat = 0
        if toolPicker.isVisible, bounds.height > 0 {
            let obscured = toolPicker.frameObscured(in: self)
            if !obscured.isNull, obscured.height > 0, obscured.width > bounds.width * 0.5 {
                inset = max(0, bounds.maxY - obscured.minY)
            }
        }
        controller.setToolPickerBottomInset(inset)
    }

    private func applyPendingMutations() {
        if let config = pendingConfig {
            pendingConfig = nil
            setAnnotating(config.annotating, pencilOnly: config.pencilOnly, showsToolPicker: config.picker)
        }
        if pendingResponderFix {
            pendingResponderFix = false
            ensureToolPickerActive()
        }
        if pendingClear {
            pendingClear = false
            clearAllCanvases()
        }
        if let drawings = pendingPageDrawings {
            pendingPageDrawings = nil
            applyPageDrawings(drawings)
        }
    }

    // MARK: - PKToolPickerObserver

    func toolPickerFramesObscuredDidChange(_ toolPicker: PKToolPicker) {
        reportToolPickerInset()
    }

    func toolPickerVisibilityDidChange(_ toolPicker: PKToolPicker) {
        reportToolPickerInset()
    }

    // MARK: - PDFPageOverlayViewProvider

    func pdfView(_ view: PDFView, overlayViewFor page: PDFPage) -> UIView? {
        if let existing = canvasMap[page] {
            return existing
        }
        guard let doc = view.document else { return nil }
        let index = doc.index(for: page)
        guard index != NSNotFound else { return nil }

        let bounds = page.bounds(for: .mediaBox)
        let canvas = PageCanvasView(frame: CGRect(origin: .zero, size: bounds.size))
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        canvas.isScrollEnabled = false
        canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        canvas.isUserInteractionEnabled = isAnnotating
        canvas.tool = toolPicker.selectedTool
        canvas.isRulerActive = toolPicker.isRulerActive
        canvas.tag = index
        canvas.delegate = self
        if let controller {
            let drawing = controller.drawing(forPage: index)
            if !drawing.strokes.isEmpty {
                canvas.drawing = drawing
            }
        }
        toolPicker.addObserver(canvas)
        canvasMap[page] = canvas
        return canvas
    }

    func pdfView(_ view: PDFView, willDisplayOverlayView overlayView: UIView, for page: PDFPage) {
        guard let canvas = overlayView as? PageCanvasView else { return }
        if !displayedCanvases.contains(where: { $0 === canvas }) {
            displayedCanvases.append(canvas)
        }
        if strokeInFlight {
            pendingResponderFix = true
        } else {
            ensureToolPickerActive()
        }
    }

    func pdfView(_ view: PDFView, willEndDisplayingOverlayView overlayView: UIView, for page: PDFPage) {
        guard let canvas = overlayView as? PageCanvasView else { return }
        displayedCanvases.removeAll { $0 === canvas }
        guard canvas.isFirstResponder else { return }
        // PDFKit is about to pull this view out of the window, which drops first responder
        // and hides the tool picker — hand it to another visible page.
        if strokeInFlight {
            pendingResponderFix = true
        } else if let next = displayedCanvases.first {
            toolPicker.setVisible(true, forFirstResponder: next)
            _ = next.becomeFirstResponder()
        }
    }

    // MARK: - PKCanvasViewDelegate

    func canvasViewDidBeginUsingTool(_ canvasView: PKCanvasView) {
        strokeInFlight = true
        if let canvas = canvasView as? PageCanvasView {
            lastEditedCanvas = canvas
        }
        inkLog.debug("stroke begin page \(canvasView.tag) window=\(canvasView.window != nil) responder=\(canvasView.isFirstResponder)")
    }

    func canvasViewDidEndUsingTool(_ canvasView: PKCanvasView) {
        strokeInFlight = false
        inkLog.debug("stroke end page \(canvasView.tag)")
        applyPendingMutations()
    }

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        if let canvas = canvasView as? PageCanvasView {
            lastEditedCanvas = canvas
        }
        controller?.noteDrawingChanged(page: canvasView.tag, drawing: canvasView.drawing)
    }

    // MARK: - Text selection & Ask callout

    @objc private func handleSelectionChanged(_ notification: Notification) {
        guard !isAnnotating else {
            hideAskCallout()
            return
        }

        guard let selection = pdfView.currentSelection,
              let raw = selection.string?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else {
            hideAskCallout()
            return
        }

        selectedText = raw
        guard let page = selection.pages.first else {
            hideAskCallout()
            return
        }

        let pageBounds = selection.bounds(for: page)
        let rectInPDFView = pdfView.convert(pageBounds, from: page)
        let centerPoint = CGPoint(x: rectInPDFView.midX, y: max(rectInPDFView.minY - 24, 60))

        showAskCallout(at: centerPoint)
    }

    private func showAskCallout(at point: CGPoint) {
        var config = askCalloutButton.configuration ?? UIButton.Configuration.filled()
        config.title = askMenuTitle
        config.image = UIImage(systemName: "sparkles")
        askCalloutButton.configuration = config

        askCalloutButton.center = point
        askCalloutButton.isHidden = false

        UIView.animate(withDuration: 0.22, delay: 0, options: [.curveEaseOut, .beginFromCurrentState]) {
            self.askCalloutButton.alpha = 1.0
            self.askCalloutButton.transform = .identity
        }
    }

    private func hideAskCallout() {
        guard !askCalloutButton.isHidden else { return }
        UIView.animate(withDuration: 0.18, delay: 0, options: [.curveEaseIn, .beginFromCurrentState]) {
            self.askCalloutButton.alpha = 0
            self.askCalloutButton.transform = CGAffineTransform(scaleX: 0.85, y: 0.85)
        } completion: { _ in
            self.askCalloutButton.isHidden = true
            self.selectedText = nil
        }
    }

    @objc private func handleAskCalloutTapped() {
        guard let text = selectedText else { return }
        hideAskCallout()
        pdfView.clearSelection()
        onAskSelection?(text)
    }
}
