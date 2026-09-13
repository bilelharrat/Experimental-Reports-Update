import PDFKit
import PencilKit
import SwiftUI
import UIKit

/// Full-bleed native PDF reader with page-locked Apple Pencil & finger annotations via `PDFPageOverlayViewProvider`.
///
/// Annotations are anchored directly to individual PDF pages in page coordinates.
/// As the user scrolls or zooms the document, drawings move and scale with the page content.
///
/// Architecture highlights:
/// - Real-time in-flight Metal ink rendering (120 FPS Promotion on iPad Pro).
/// - PDFView scroll pan gestures and text selection gestures are configured with `allowedTouchTypes = [.direct]`
///   so Apple Pencil touches bypass all scroll delays and flow directly to `PKCanvasView.drawingGestureRecognizer`.
/// - Automatic responder promotion on touch hit-test ensures the canvas is always ready for live ink.
/// - Independent per-page canvas instances maintain clean state without tool picker multi-canvas lockups.
struct MemoPaperDocumentView: UIViewRepresentable {
    let url: URL
    @Binding var drawing: PKDrawing
    @Binding var pageDrawings: [Int: PKDrawing]
    var isAnnotating: Bool
    var showsToolPicker: Bool
    var canvasRef: Binding<PKCanvasView?>
    var replaceToken: Int
    var pencilOnly: Bool
    var askMenuTitle: String = "Ask Warren"
    var onAskSelection: ((String) -> Void)? = nil
    var onPageDrawingsChanged: (([Int: PKDrawing]) -> Void)? = nil

    func makeCoordinator() -> Coordinator {
        Coordinator(
            drawing: $drawing,
            pageDrawings: $pageDrawings,
            canvasRef: canvasRef,
            onAskSelection: onAskSelection,
            onPageDrawingsChanged: onPageDrawingsChanged
        )
    }

    func makeUIView(context: Context) -> PaperDeskPDFHostView {
        let host = PaperDeskPDFHostView()
        host.coordinator = context.coordinator
        context.coordinator.host = host
        host.askMenuTitle = askMenuTitle
        host.load(url: url, pageDrawings: pageDrawings)
        host.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
        return host
    }

    func updateUIView(_ host: PaperDeskPDFHostView, context: Context) {
        context.coordinator.host = host
        context.coordinator.onAskSelection = onAskSelection
        context.coordinator.onPageDrawingsChanged = onPageDrawingsChanged
        host.askMenuTitle = askMenuTitle

        if host.currentURL != url || host.pdfView.document == nil {
            host.load(url: url, pageDrawings: pageDrawings)
        }

        if context.coordinator.appliedReplaceToken != replaceToken {
            context.coordinator.appliedReplaceToken = replaceToken
            host.applyPageDrawings(pageDrawings)
        }

        host.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
    }

    static func dismantleUIView(_ host: PaperDeskPDFHostView, coordinator: Coordinator) {
        host.teardown()
        coordinator.host = nil
    }

    // MARK: - Coordinator

    final class Coordinator: NSObject {
        var drawing: Binding<PKDrawing>
        var pageDrawings: Binding<[Int: PKDrawing]>
        var canvasRef: Binding<PKCanvasView?>
        var appliedReplaceToken = -1
        weak var host: PaperDeskPDFHostView?
        var onAskSelection: ((String) -> Void)?
        var onPageDrawingsChanged: (([Int: PKDrawing]) -> Void)?

        init(
            drawing: Binding<PKDrawing>,
            pageDrawings: Binding<[Int: PKDrawing]>,
            canvasRef: Binding<PKCanvasView?>,
            onAskSelection: ((String) -> Void)?,
            onPageDrawingsChanged: (([Int: PKDrawing]) -> Void)?
        ) {
            self.drawing = drawing
            self.pageDrawings = pageDrawings
            self.canvasRef = canvasRef
            self.onAskSelection = onAskSelection
            self.onPageDrawingsChanged = onPageDrawingsChanged
        }
    }
}

// MARK: - Dedicated Page Canvas View

final class PageCanvasView: PKCanvasView {
    override var canBecomeFirstResponder: Bool { true }

    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        let view = super.hitTest(point, with: event)
        if view != nil && !isFirstResponder {
            _ = becomeFirstResponder()
        }
        return view
    }
}

// MARK: - Native PaperDeskPDFHostView

final class PaperDeskPDFHostView: UIView, PDFPageOverlayViewProvider, PKCanvasViewDelegate, PKToolPickerObserver {
    weak var coordinator: MemoPaperDocumentView.Coordinator?
    var askMenuTitle: String = "Ask Warren"

    let pdfView = PDFView()
    private let toolPicker = PKToolPicker()
    private var activeTool: PKTool = PKInkingTool(.pen, color: .black, width: 3)

    private var canvasMap: [PDFPage: PageCanvasView] = [:]
    private var pageDrawingsMap: [Int: PKDrawing] = [:]
    private var isAnnotating = false
    private var pencilOnly = true
    private var showsToolPicker = false
    private var saveDebounceTimer: Timer?
    private(set) var currentURL: URL?

    private(set) weak var activeCanvasView: PageCanvasView?

    // Ask Warren callout button
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
        commonInit()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        commonInit()
    }

    private func commonInit() {
        toolPicker.selectedTool = activeTool
        toolPicker.addObserver(self)
        setup()
    }

    private func setup() {
        backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1.0)

        // Configure single continuous PDFView
        pdfView.translatesAutoresizingMaskIntoConstraints = false
        pdfView.displayMode = .singlePageContinuous
        pdfView.displayDirection = .vertical
        pdfView.displayBox = .mediaBox
        pdfView.autoScales = true
        pdfView.displaysPageBreaks = true
        pdfView.pageBreakMargins = UIEdgeInsets(top: 14, left: 0, bottom: 14, right: 0)
        pdfView.backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1.0)
        pdfView.usePageViewController(false)
        if #available(iOS 16.0, *) {
            pdfView.isInMarkupMode = true
        }
        pdfView.pageOverlayViewProvider = self
        addSubview(pdfView)

        // Floating Ask Callout
        askCalloutButton.translatesAutoresizingMaskIntoConstraints = false
        askCalloutButton.addTarget(self, action: #selector(handleAskCalloutTapped), for: .touchUpInside)
        addSubview(askCalloutButton)

        NSLayoutConstraint.activate([
            pdfView.topAnchor.constraint(equalTo: topAnchor),
            pdfView.bottomAnchor.constraint(equalTo: bottomAnchor),
            pdfView.leadingAnchor.constraint(equalTo: leadingAnchor),
            pdfView.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])

        optimizeGesturesForDrawing()

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleSelectionChanged),
            name: .PDFViewSelectionChanged,
            object: pdfView
        )
    }

    /// Eliminates all touch delivery delays and ensures Apple Pencil touches are never intercepted by PDFKit scroll/pan gestures.
    func optimizeGesturesForDrawing() {
        func configureView(_ v: UIView) {
            if let sv = v as? UIScrollView {
                sv.delaysContentTouches = false
                sv.canCancelContentTouches = true
            }

            for g in v.gestureRecognizers ?? [] {
                g.delaysTouchesBegan = false

                if let pan = g as? UIPanGestureRecognizer {
                    if pencilOnly {
                        // CRITICAL: Restrict PDFView pan gesture to direct finger touches only!
                        // Apple Pencil touches completely bypass the scroll gesture, eliminating any in-flight delay.
                        pan.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
                    } else {
                        pan.allowedTouchTypes = [
                            NSNumber(value: UITouch.TouchType.direct.rawValue),
                            NSNumber(value: UITouch.TouchType.pencil.rawValue)
                        ]
                    }
                } else if let longPress = g as? UILongPressGestureRecognizer {
                    if isAnnotating {
                        // Prevent text selection long-press from hijacking Apple Pencil while drawing
                        longPress.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
                    }
                }
            }

            for sub in v.subviews {
                configureView(sub)
            }
        }

        configureView(pdfView)
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        optimizeGesturesForDrawing()
        if window != nil && isAnnotating && showsToolPicker {
            activateToolPickerForActiveCanvas()
        }
    }

    func teardown() {
        saveDebounceTimer?.invalidate()
        saveDebounceTimer = nil
        flushDrawingsNow()

        NotificationCenter.default.removeObserver(self)
        toolPicker.removeObserver(self)
        if let target = activeCanvasView ?? canvasMap.values.first {
            toolPicker.setVisible(false, forFirstResponder: target)
        }
        for canvas in canvasMap.values {
            toolPicker.removeObserver(canvas)
            canvas.delegate = nil
        }
        canvasMap.removeAll()
    }

    // MARK: - Document Loading & Drawing Application

    func load(url: URL, pageDrawings: [Int: PKDrawing]) {
        self.currentURL = url
        self.pageDrawingsMap = pageDrawings
        guard let doc = PDFDocument(url: url) else { return }
        pdfView.document = doc

        if #available(iOS 16.0, *) {
            pdfView.isInMarkupMode = isAnnotating
        }
        optimizeGesturesForDrawing()

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.pdfView.autoScales = true
            self.optimizeGesturesForDrawing()
            if let firstPage = doc.page(at: 0) {
                self.pdfView.go(to: firstPage)
            }
        }
    }

    func applyPageDrawings(_ drawings: [Int: PKDrawing]) {
        self.pageDrawingsMap = drawings
        guard let doc = pdfView.document else { return }
        for (page, canvas) in canvasMap {
            let index = doc.index(for: page)
            if index != NSNotFound {
                let target = drawings[index] ?? PKDrawing()
                if canvas.drawing != target {
                    canvas.drawing = target
                }
            }
        }
    }

    // MARK: - Annotation Mode & Tool Picker

    func setAnnotating(_ annotating: Bool, pencilOnly: Bool, showsToolPicker: Bool) {
        self.isAnnotating = annotating
        self.pencilOnly = pencilOnly
        self.showsToolPicker = showsToolPicker

        if #available(iOS 16.0, *) {
            pdfView.isInMarkupMode = annotating
        }
        optimizeGesturesForDrawing()

        if annotating {
            hideAskCallout()
            pdfView.clearSelection()
        }

        for canvas in canvasMap.values {
            canvas.isUserInteractionEnabled = annotating
            canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
            canvas.tool = activeTool
        }

        let target = activeCanvasView ?? canvasMap.values.first
        if annotating && showsToolPicker, let target = target {
            toolPicker.setVisible(true, forFirstResponder: target)
            _ = target.becomeFirstResponder()
        } else if let target = target {
            toolPicker.setVisible(false, forFirstResponder: target)
        }
    }

    private func activateToolPickerForActiveCanvas() {
        guard isAnnotating && showsToolPicker,
              let target = activeCanvasView ?? canvasMap.values.first else { return }
        toolPicker.setVisible(true, forFirstResponder: target)
        _ = target.becomeFirstResponder()
    }

    // MARK: - PKToolPickerObserver

    func toolPickerSelectedToolDidChange(_ toolPicker: PKToolPicker) {
        activeTool = toolPicker.selectedTool
        for canvas in canvasMap.values {
            canvas.tool = activeTool
        }
    }

    func toolPickerIsRulerActiveDidChange(_ toolPicker: PKToolPicker) {
        for canvas in canvasMap.values {
            canvas.isRulerActive = toolPicker.isRulerActive
        }
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
        canvas.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        canvas.isScrollEnabled = false
        canvas.bounces = false
        canvas.delaysContentTouches = false
        canvas.canCancelContentTouches = false
        canvas.drawingGestureRecognizer.delaysTouchesBegan = false
        canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        canvas.isUserInteractionEnabled = isAnnotating
        canvas.tool = activeTool

        if let existingDrawing = pageDrawingsMap[index] {
            canvas.drawing = existingDrawing
        }

        canvas.delegate = self
        canvas.tag = index
        canvasMap[page] = canvas

        if activeCanvasView == nil {
            activeCanvasView = canvas
            if isAnnotating && showsToolPicker {
                toolPicker.setVisible(true, forFirstResponder: canvas)
                _ = canvas.becomeFirstResponder()
            }
        }

        return canvas
    }

    func pdfView(_ view: PDFView, willDisplayOverlayView overlayView: UIView, for page: PDFPage) {
        guard let canvas = overlayView as? PageCanvasView else { return }
        activeCanvasView = canvas
        optimizeGesturesForDrawing()

        if isAnnotating && showsToolPicker {
            toolPicker.setVisible(true, forFirstResponder: canvas)
            _ = canvas.becomeFirstResponder()
        }
    }

    func pdfView(_ view: PDFView, willEndDisplayingOverlayView overlayView: UIView, for page: PDFPage) {
        guard let canvas = overlayView as? PageCanvasView else { return }
        if activeCanvasView === canvas {
            activeCanvasView = canvasMap.values.first(where: { $0 !== canvas })
            if let next = activeCanvasView, isAnnotating && showsToolPicker {
                toolPicker.setVisible(true, forFirstResponder: next)
                _ = next.becomeFirstResponder()
            }
        }
    }

    // MARK: - PKCanvasViewDelegate

    func canvasViewDidBeginUsingTool(_ canvasView: PKCanvasView) {
        guard let pageCanvas = canvasView as? PageCanvasView else { return }
        activeCanvasView = pageCanvas
        if isAnnotating && showsToolPicker {
            toolPicker.setVisible(true, forFirstResponder: pageCanvas)
            _ = pageCanvas.becomeFirstResponder()
        }
    }

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        let index = canvasView.tag
        guard index >= 0 else { return }

        pageDrawingsMap[index] = canvasView.drawing
        if let pageCanvas = canvasView as? PageCanvasView {
            activeCanvasView = pageCanvas
        }

        // Debounce syncing to coordinator so the 120Hz drawing pipeline is never interrupted
        scheduleSaveDebounce()
    }

    private func scheduleSaveDebounce() {
        saveDebounceTimer?.invalidate()
        saveDebounceTimer = Timer.scheduledTimer(withTimeInterval: 0.6, repeats: false) { [weak self] _ in
            self?.flushDrawingsNow()
        }
    }

    private func flushDrawingsNow() {
        saveDebounceTimer?.invalidate()
        saveDebounceTimer = nil

        guard let doc = pdfView.document else { return }
        var pageSizes: [CGSize] = []
        for i in 0..<doc.pageCount {
            if let p = doc.page(at: i) {
                pageSizes.append(p.bounds(for: .mediaBox).size)
            }
        }
        let composite = ReportAnnotationStore.compositeDrawing(from: pageDrawingsMap, pageSizes: pageSizes)

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.coordinator?.pageDrawings.wrappedValue = self.pageDrawingsMap
            self.coordinator?.drawing.wrappedValue = composite
            self.coordinator?.onPageDrawingsChanged?(self.pageDrawingsMap)
        }
    }

    // MARK: - Text Selection & Ask Warren Floating Callout

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
        coordinator?.onAskSelection?(text)
    }
}
