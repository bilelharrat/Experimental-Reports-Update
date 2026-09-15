import OSLog
import PDFKit
import PencilKit
import SwiftUI
import UIKit

private let inkLog = Logger(subsystem: "com.bilelharrrat.bshresearch", category: "ink")

// MARK: - Ink controller (state + persistence, owned by the SwiftUI reader)

/// Owns one open report's ink and persists it off the main thread.
///
/// The reader's single `PKCanvasView` is the live surface. This object holds the last committed
/// copy of its drawing — in composite space, where `ReportAnnotationStore.compositePageRects`
/// stacks the pages — and is the only place that talks to `ReportAnnotationStore`. Disk, PNG and
/// network work runs serially on `InkPersistence`, never on the main thread.
@MainActor
final class PaperDeskInkController: ObservableObject {
    let reportId: String

    /// Strokes on the canvas — drives Undo / Clear enablement.
    @Published private(set) var strokeCount = 0

    /// Display size of each page; empty until the document loads.
    private(set) var pageSizes: [CGSize] = []
    /// Last committed canvas drawing, in composite space.
    private(set) var drawing = PKDrawing()

    weak var host: PaperDeskReaderView?

    private let persistence = InkPersistence()
    private let localInk: ReportAnnotationStore.LocalInk
    private var needsLocalSave = false
    private var needsPush = false
    private var localSaveTask: Task<Void, Never>?
    private var pushTask: Task<Void, Never>?
    private var pullTask: Task<Void, Never>?
    /// Tail of the serial persistence queue.
    private var persistTail: Task<Void, Never>?

    init(reportId: String) {
        self.reportId = reportId
        localInk = ReportAnnotationStore.loadLocalInk(reportId: reportId)
    }

    /// Ink per page, in page coordinates (annotated-PDF export).
    var pageDrawings: [Int: PKDrawing] {
        ReportAnnotationStore.splitComposite(drawing, pageSizes: pageSizes)
    }

    // MARK: Host → controller

    /// The document is laid out: returns the ink to show, then reconciles with the cloud copy.
    func documentDidLoad(pageSizes: [CGSize]) -> PKDrawing {
        self.pageSizes = pageSizes
        drawing = localInk.compositeDrawing(pageSizes: pageSizes)
        strokeCount = drawing.strokes.count
        pullRemote()
        return drawing
    }

    /// A stroke was committed, erased or undone. PencilKit never calls this mid-stroke.
    func canvasDrawingDidChange(_ drawing: PKDrawing) {
        self.drawing = drawing
        strokeCount = drawing.strokes.count
        needsLocalSave = true
        needsPush = true
        scheduleLocalSave(after: 1.0)
        schedulePush(after: 4.0)
    }

    // MARK: Reader → controller

    func undo() {
        host?.undo()
    }

    func clearAll() {
        localSaveTask?.cancel()
        pushTask?.cancel()
        pullTask?.cancel()
        needsLocalSave = false
        needsPush = false
        drawing = PKDrawing()
        strokeCount = 0
        host?.clearDrawing()
        let reportId = reportId
        enqueue { await $0.clear(reportId: reportId) }
    }

    /// Persist unsaved edits now (local + cloud). No-op when nothing changed.
    func flush() {
        localSaveTask?.cancel()
        pushTask?.cancel()
        saveLocalNow()
        pushNow()
    }

    // MARK: Persistence

    private func scheduleLocalSave(after delay: TimeInterval) {
        localSaveTask?.cancel()
        localSaveTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            self?.saveLocalNow()
        }
    }

    private func schedulePush(after delay: TimeInterval) {
        pushTask?.cancel()
        pushTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, let self else { return }
            // The cloud push renders a PNG; never compete with a live stroke for the GPU.
            if self.host?.strokeInFlight == true {
                self.schedulePush(after: 2.0)
                return
            }
            self.pushNow()
        }
    }

    private func saveLocalNow() {
        guard needsLocalSave, !pageSizes.isEmpty else { return }
        needsLocalSave = false
        let snapshot = drawing
        let sizes = pageSizes
        let reportId = reportId
        enqueue { await $0.saveLocal(snapshot, reportId: reportId, pageSizes: sizes) }
    }

    private func pushNow() {
        guard needsPush, !pageSizes.isEmpty else { return }
        needsPush = false
        let snapshot = drawing
        let sizes = pageSizes
        let reportId = reportId
        enqueue { await $0.push(snapshot, reportId: reportId, pageSizes: sizes) }
    }

    private func pullRemote() {
        pullTask?.cancel()
        let reportId = reportId
        let persistence = persistence
        pullTask = Task { [weak self] in
            guard let remote = await persistence.pull(reportId: reportId) else { return }
            guard !Task.isCancelled, let self else { return }
            // Strokes made while the request was out are newer than the server copy; they push shortly.
            guard !self.needsLocalSave, !self.needsPush, remote != self.drawing else { return }
            inkLog.info("applying newer cloud ink: \(remote.strokes.count) strokes")
            self.drawing = remote
            self.strokeCount = remote.strokes.count
            self.host?.showDrawing(remote)
            self.needsLocalSave = true
            self.saveLocalNow()
        }
    }

    /// Runs persistence operations one at a time, in the order they were requested.
    private func enqueue(_ operation: @escaping @Sendable (InkPersistence) async -> Void) {
        let previous = persistTail
        let persistence = persistence
        persistTail = Task.detached(priority: .utility) {
            await previous?.value
            await operation(persistence)
        }
    }
}

/// Disk, PNG-render and network work for the ink store, off the main thread.
actor InkPersistence {
    func saveLocal(_ drawing: PKDrawing, reportId: String, pageSizes: [CGSize]) {
        ReportAnnotationStore.saveComposite(drawing, reportId: reportId, pageSizes: pageSizes)
    }

    func push(_ drawing: PKDrawing, reportId: String, pageSizes: [CGSize]) async {
        let size = ReportAnnotationStore.compositeCanvasSize(pageSizes: pageSizes)
        _ = await ReportAnnotationStore.push(drawing, reportId: reportId, canvasSize: size)
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

/// Full-bleed memo reader with Apple Pencil ink.
///
/// Live-ink rules — these are what keep PencilKit's in-flight stroke on screen:
/// - Exactly one `PKCanvasView`, the size of the viewport, doing its own scrolling and zooming
///   (the Notes setup). PencilKit sizes the Metal layer that shows a stroke *while it's being
///   drawn* to the canvas bounds. A canvas as big as the document — a converted memo is a single
///   ~14,000 pt page — asks for a drawable far past the GPU texture limit, gets none ("No drawable
///   available; skipping frame"), and the stroke only appears once PencilKit commits it at lift.
/// - PDF pages are tiled views underneath the ink, inside the canvas, laid out in the same
///   composite space as the drawing, so ink stays locked to the text while scrolling and zooming.
/// - Nothing mutates the canvas, zoom or tool picker while a stroke is in flight; it waits for tool-up.
/// - SwiftUI only ever sees a stroke count; drawings persist off-main, seconds after the last stroke.
struct MemoPaperDocumentView: UIViewRepresentable {
    let url: URL
    let controller: PaperDeskInkController
    var isAnnotating: Bool
    var showsToolPicker: Bool
    var pencilOnly: Bool
    var askMenuTitle: String = "Ask Warren"
    var onAskSelection: ((String) -> Void)? = nil

    func makeUIView(context: Context) -> PaperDeskReaderView {
        let reader = PaperDeskReaderView()
        reader.controller = controller
        controller.host = reader
        reader.askMenuTitle = askMenuTitle
        reader.onAskSelection = onAskSelection
        reader.load(url: url)
        reader.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
        return reader
    }

    func updateUIView(_ reader: PaperDeskReaderView, context: Context) {
        reader.askMenuTitle = askMenuTitle
        reader.onAskSelection = onAskSelection
        if reader.currentURL != url {
            reader.load(url: url)
        }
        reader.setAnnotating(isAnnotating, pencilOnly: pencilOnly, showsToolPicker: showsToolPicker)
    }

    static func dismantleUIView(_ reader: PaperDeskReaderView, coordinator: ()) {
        reader.teardown()
    }
}

// MARK: - Pages

/// Where a PDF page's content lands in a y-down view the page's display size.
struct PaperPageGeometry {
    /// Page size as shown (media box, with the page's own rotation applied).
    let displaySize: CGSize
    /// PDF page space (y-up, media box coordinates) → view coordinates.
    let pageToView: CGAffineTransform

    init(page: CGPDFPage) {
        let box = page.getBoxRect(.mediaBox)
        let quarterTurns = (Int(page.rotationAngle) % 360 + 360) % 360 / 90
        let size = quarterTurns % 2 == 0 ? box.size : CGSize(width: box.height, height: box.width)
        let fit = page.getDrawingTransform(
            .mediaBox,
            rect: CGRect(origin: .zero, size: size),
            rotate: 0,
            preserveAspectRatio: true
        )
        let flip = CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty: size.height)
        displaySize = size
        pageToView = fit.concatenating(flip)
    }
}

/// One page of paper: white sheet, shadow, tiled PDF content and the text-selection highlight.
/// Its bounds are in page points; the reader scales it with a transform as the canvas zooms.
final class PaperPageView: UIView {
    let displaySize: CGSize
    let pageToView: CGAffineTransform
    let viewToPage: CGAffineTransform
    private let selectionLayer = CAShapeLayer()

    init(page: CGPDFPage, pageNumber: Int) {
        let geometry = PaperPageGeometry(page: page)
        displaySize = geometry.displaySize
        pageToView = geometry.pageToView
        viewToPage = geometry.pageToView.inverted()
        super.init(frame: CGRect(origin: .zero, size: geometry.displaySize))
        isUserInteractionEnabled = false
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOpacity = 0.16
        layer.shadowPath = UIBezierPath(rect: bounds).cgPath

        addSubview(PaperPageTilesView(page: page, pageToView: geometry.pageToView, size: geometry.displaySize))

        selectionLayer.frame = bounds
        selectionLayer.fillColor = UIColor.systemBlue.withAlphaComponent(0.32).cgColor
        selectionLayer.compositingFilter = "multiplyBlendMode"
        layer.addSublayer(selectionLayer)

        isAccessibilityElement = true
        accessibilityLabel = "Page \(pageNumber)"
    }

    required init?(coder: NSCoder) {
        return nil
    }

    /// Keep the sheet's shadow the same size on screen at every zoom.
    func zoomDidChange(_ zoom: CGFloat) {
        layer.shadowRadius = 5 / zoom
        layer.shadowOffset = CGSize(width: 0, height: 1 / zoom)
    }

    func setSelectionPath(_ path: CGPath?) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        selectionLayer.path = path
        CATransaction.commit()
    }
}

private final class PaperPageTiledLayer: CATiledLayer {
    override class func fadeDuration() -> CFTimeInterval { 0.05 }
}

/// Draws a page with Core Graphics from CATiledLayer's background threads, tile by tile, at
/// whatever resolution the current zoom needs — no PDFKit and no main-thread rendering.
private final class PaperPageTilesView: UIView {
    override class var layerClass: AnyClass { PaperPageTiledLayer.self }

    private let page: CGPDFPage
    private let pageToView: CGAffineTransform

    init(page: CGPDFPage, pageToView: CGAffineTransform, size: CGSize) {
        self.page = page
        self.pageToView = pageToView
        super.init(frame: CGRect(origin: .zero, size: size))
        isUserInteractionEnabled = false
        backgroundColor = .white
        if let tiled = layer as? CATiledLayer {
            // Levels from 1/2x to 32x page resolution: fit-width through 5x zoom on a 2x screen.
            tiled.levelsOfDetail = 7
            tiled.levelsOfDetailBias = 5
            tiled.tileSize = CGSize(width: 512, height: 512)
        }
        layer.setNeedsDisplay()
    }

    required init?(coder: NSCoder) {
        return nil
    }

    override func draw(_ layer: CALayer, in ctx: CGContext) {
        ctx.setFillColor(UIColor.white.cgColor)
        ctx.fill(ctx.boundingBoxOfClipPath)
        ctx.concatenate(pageToView)
        ctx.drawPDFPage(page)
    }
}

/// The reader's one canvas. Keeps the page underlay beneath PencilKit's own content views.
final class PaperCanvasView: PKCanvasView {
    weak var underlay: UIView?

    override var canBecomeFirstResponder: Bool { true }

    override func layoutSubviews() {
        super.layoutSubviews()
        if let underlay, subviews.first !== underlay {
            sendSubviewToBack(underlay)
        }
    }
}

// MARK: - Reader view

final class PaperDeskReaderView: UIView, PKCanvasViewDelegate, UIGestureRecognizerDelegate {
    weak var controller: PaperDeskInkController?
    var askMenuTitle = "Ask Warren"
    var onAskSelection: ((String) -> Void)?

    private(set) var currentURL: URL?
    /// True from tool-down to tool-up. Canvas, zoom and tool-picker changes wait for it.
    private(set) var strokeInFlight = false

    private static let deskColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1.0)
    /// Zoom range as multiples of fit-width.
    private static let minZoomFactor: CGFloat = 0.5
    private static let maxZoomFactor: CGFloat = 5

    private let canvas = PaperCanvasView()
    private let pagesView = UIView()
    private let toolPicker = PKToolPicker()

    private var document: PDFDocument?
    private var pageViews: [PaperPageView] = []
    /// Page frames in composite space (= canvas content at zoom 1).
    private var pageRects: [CGRect] = []
    private var documentSize: CGSize = .zero

    private var isAnnotating = false
    private var pencilOnly = true
    private var showsToolPicker = false

    private var fitScale: CGFloat = 1
    private var placedSize: CGSize = .zero
    private var didPlaceDocument = false
    private var userMovedDocument = false

    private var pendingConfig: (annotating: Bool, pencilOnly: Bool, picker: Bool)?
    private var pendingDrawing: PKDrawing?
    private var pendingClear = false
    private var pendingPlacement = false
    private var pendingPickerRefresh = false
    private var isApplyingDrawing = false

    // Text selection (reading mode).
    private struct PageHit {
        let page: Int
        /// PDF page space.
        let point: CGPoint
    }

    private let selectPress = UILongPressGestureRecognizer()
    private let tapGesture = UITapGestureRecognizer()
    private var selection: PDFSelection?
    private var selectionAnchor: PageHit?
    /// First highlighted line: page index and rect in that page view's coordinates.
    private var selectionHead: (page: Int, rect: CGRect)?
    private var lastSelectionUpdate: CFTimeInterval = 0
    private var dragLocation: CGPoint = .zero
    private var autoscrollLink: CADisplayLink?
    private var autoscrollSpeed: CGFloat = 0

    private let askCalloutButton: UIButton = {
        let button = UIButton(type: .system)
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .capsule
        config.buttonSize = .mini
        config.baseBackgroundColor = UIColor(red: 0.10, green: 0.12, blue: 0.18, alpha: 0.94)
        config.baseForegroundColor = .white
        config.imagePadding = 6
        config.contentInsets = NSDirectionalEdgeInsets(top: 8, leading: 14, bottom: 8, trailing: 14)
        button.configuration = config
        button.layer.shadowColor = UIColor.black.cgColor
        button.layer.shadowOpacity = 0.22
        button.layer.shadowOffset = CGSize(width: 0, height: 4)
        button.layer.shadowRadius = 8
        button.alpha = 0
        button.isHidden = true
        return button
    }()

    override init(frame: CGRect) {
        super.init(frame: frame)
        setup()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setup()
    }

    private func setup() {
        backgroundColor = Self.deskColor

        canvas.frame = bounds
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        // Ink colors are chosen for white paper; don't let PencilKit invert them in Dark Mode.
        canvas.overrideUserInterfaceStyle = .light
        canvas.drawingPolicy = .pencilOnly
        canvas.drawingGestureRecognizer.isEnabled = false
        canvas.alwaysBounceVertical = true
        canvas.bouncesZoom = true
        canvas.delegate = self
        addSubview(canvas)

        pagesView.isUserInteractionEnabled = false
        pagesView.backgroundColor = .clear
        canvas.addSubview(pagesView)
        canvas.underlay = pagesView
        canvas.sendSubviewToBack(pagesView)

        toolPicker.stateAutosaveName = "BSHMemoReaderInk"
        toolPicker.colorUserInterfaceStyle = .light
        toolPicker.addObserver(canvas)

        selectPress.addTarget(self, action: #selector(handleSelectPress(_:)))
        selectPress.minimumPressDuration = 0.35
        selectPress.delegate = self
        canvas.addGestureRecognizer(selectPress)

        tapGesture.addTarget(self, action: #selector(handleTap(_:)))
        tapGesture.delegate = self
        canvas.addGestureRecognizer(tapGesture)

        askCalloutButton.addTarget(self, action: #selector(handleAskCalloutTapped), for: .touchUpInside)
        addSubview(askCalloutButton)
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.strokeInFlight else { return }
            self.updateToolPicker()
        }
    }

    func teardown() {
        stopAutoscroll()
        toolPicker.setVisible(false, forFirstResponder: canvas)
        toolPicker.removeObserver(canvas)
        if canvas.isFirstResponder {
            canvas.resignFirstResponder()
        }
        canvas.delegate = nil
    }

    // MARK: Document

    func load(url: URL) {
        currentURL = url
        clearSelection()
        pageViews.forEach { $0.removeFromSuperview() }
        pageViews = []
        pageRects = []
        documentSize = .zero
        document = nil
        didPlaceDocument = false
        placedSize = .zero
        userMovedDocument = false

        guard let pdf = PDFDocument(url: url),
              let source = CGPDFDocument(url as CFURL),
              pdf.pageCount > 0,
              source.numberOfPages == pdf.pageCount
        else {
            inkLog.error("could not open \(url.lastPathComponent, privacy: .public)")
            return
        }
        let pages = (1...source.numberOfPages).compactMap { source.page(at: $0) }
        guard pages.count == pdf.pageCount else { return }

        document = pdf
        var sizes: [CGSize] = []
        for (offset, page) in pages.enumerated() {
            let view = PaperPageView(page: page, pageNumber: offset + 1)
            pagesView.addSubview(view)
            pageViews.append(view)
            sizes.append(view.displaySize)
        }
        pageRects = ReportAnnotationStore.compositePageRects(pageSizes: sizes)
        documentSize = ReportAnnotationStore.compositeCanvasSize(pageSizes: sizes)
        showDrawing(controller?.documentDidLoad(pageSizes: sizes) ?? PKDrawing())
        setNeedsLayout()
    }

    // MARK: Layout & zoom

    override func layoutSubviews() {
        super.layoutSubviews()
        if canvas.frame != bounds {
            canvas.frame = bounds
        }
        guard !pageRects.isEmpty, bounds.width > 1, bounds.height > 1, bounds.size != placedSize else { return }
        guard !strokeInFlight else {
            pendingPlacement = true
            return
        }
        placeDocument()
    }

    override func safeAreaInsetsDidChange() {
        super.safeAreaInsetsDidChange()
        DispatchQueue.main.async { [weak self] in
            guard let self, self.didPlaceDocument, !self.strokeInFlight else { return }
            self.updateContentGeometry()
            if !self.userMovedDocument {
                self.canvas.contentOffset = CGPoint(x: self.canvas.contentOffset.x, y: -self.canvas.adjustedContentInset.top)
            }
        }
    }

    /// Fit the document to the width on first layout; on later size changes (rotation, the Ask
    /// panel, window resizing) keep the zoom relative to fit-width and the line at the top of the view.
    private func placeDocument() {
        let size = bounds.size
        let newFit = max(0.01, size.width / documentSize.width)

        guard didPlaceDocument else {
            didPlaceDocument = true
            placedSize = size
            fitScale = newFit
            canvas.minimumZoomScale = newFit * Self.minZoomFactor
            canvas.maximumZoomScale = newFit * Self.maxZoomFactor
            setZoom(newFit)
            canvas.contentOffset = CGPoint(x: -canvas.adjustedContentInset.left, y: -canvas.adjustedContentInset.top)
            return
        }

        let oldZoom = canvas.zoomScale
        let anchor = CGPoint(
            x: (canvas.contentOffset.x + canvas.bounds.width / 2) / oldZoom,
            y: (canvas.contentOffset.y + canvas.adjustedContentInset.top) / oldZoom
        )
        let relativeZoom = oldZoom / fitScale
        placedSize = size
        fitScale = newFit
        canvas.minimumZoomScale = newFit * Self.minZoomFactor
        canvas.maximumZoomScale = newFit * Self.maxZoomFactor
        let zoom = min(max(relativeZoom * newFit, canvas.minimumZoomScale), canvas.maximumZoomScale)
        setZoom(zoom)
        canvas.contentOffset = clampedOffset(CGPoint(
            x: anchor.x * zoom - canvas.bounds.width / 2,
            y: anchor.y * zoom - canvas.adjustedContentInset.top
        ))
    }

    private func setZoom(_ zoom: CGFloat) {
        if abs(canvas.zoomScale - zoom) > 0.000_1 {
            canvas.zoomScale = zoom
        }
        updateContentGeometry()
    }

    /// Size the scrollable content and place every page for the current zoom.
    private func updateContentGeometry() {
        guard !pageRects.isEmpty else { return }
        let zoom = canvas.zoomScale
        let scaled = CGSize(width: documentSize.width * zoom, height: documentSize.height * zoom)
        if canvas.contentSize != scaled {
            canvas.contentSize = scaled
        }
        pagesView.frame = CGRect(origin: .zero, size: scaled)
        for (index, view) in pageViews.enumerated() where index < pageRects.count {
            let rect = pageRects[index]
            view.center = CGPoint(x: rect.midX * zoom, y: rect.midY * zoom)
            view.transform = CGAffineTransform(scaleX: zoom, y: zoom)
            view.zoomDidChange(zoom)
        }
        // Center the paper when it's smaller than the view (zoomed out past fit-width).
        let safe = canvas.safeAreaInsets
        let spareWidth = max(0, canvas.bounds.width - safe.left - safe.right - scaled.width) / 2
        let spareHeight = max(0, canvas.bounds.height - safe.top - safe.bottom - scaled.height) / 2
        let centering = UIEdgeInsets(top: spareHeight, left: spareWidth, bottom: spareHeight, right: spareWidth)
        if canvas.contentInset != centering {
            canvas.contentInset = centering
        }
    }

    private func clampedOffset(_ point: CGPoint) -> CGPoint {
        let inset = canvas.adjustedContentInset
        let minX = -inset.left
        let minY = -inset.top
        let maxX = max(minX, canvas.contentSize.width + inset.right - canvas.bounds.width)
        let maxY = max(minY, canvas.contentSize.height + inset.bottom - canvas.bounds.height)
        return CGPoint(x: min(max(point.x, minX), maxX), y: min(max(point.y, minY), maxY))
    }

    // MARK: Annotation mode & tool picker

    func setAnnotating(_ annotating: Bool, pencilOnly: Bool, showsToolPicker: Bool) {
        guard annotating != isAnnotating
            || pencilOnly != self.pencilOnly
            || showsToolPicker != self.showsToolPicker
        else { return }
        guard !strokeInFlight else {
            pendingConfig = (annotating, pencilOnly, showsToolPicker)
            scheduleStrokeWatchdog()
            return
        }

        inkLog.info("annotating=\(annotating) pencilOnly=\(pencilOnly) picker=\(showsToolPicker)")
        isAnnotating = annotating
        self.pencilOnly = pencilOnly
        self.showsToolPicker = showsToolPicker

        canvas.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        canvas.drawingGestureRecognizer.isEnabled = annotating
        selectPress.isEnabled = !annotating
        tapGesture.isEnabled = !annotating
        if annotating {
            clearSelection()
        }
        // This runs inside SwiftUI's view update. Changing first responder / showing the tool
        // picker there re-lays out the hosting view mid-update and SwiftUI drops the frame (the
        // reader's controls render one state behind), so do it on the next turn of the run loop.
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.strokeInFlight else { return }
            self.updateToolPicker()
        }
    }

    private func updateToolPicker() {
        guard window != nil else { return }
        let wantsPicker = isAnnotating && showsToolPicker
        toolPicker.setVisible(wantsPicker, forFirstResponder: canvas)
        if wantsPicker {
            if !canvas.isFirstResponder {
                canvas.becomeFirstResponder()
            }
        } else if canvas.isFirstResponder {
            canvas.resignFirstResponder()
        }
    }

    // MARK: Ink

    /// Replace the canvas ink (document load, a newer cloud copy). Waits for tool-up.
    func showDrawing(_ drawing: PKDrawing) {
        guard !strokeInFlight else {
            pendingDrawing = drawing
            scheduleStrokeWatchdog()
            return
        }
        isApplyingDrawing = true
        canvas.drawing = drawing
        isApplyingDrawing = false
    }

    func clearDrawing() {
        guard !strokeInFlight else {
            pendingClear = true
            scheduleStrokeWatchdog()
            return
        }
        showDrawing(PKDrawing())
    }

    func undo() {
        guard !strokeInFlight else { return }
        if let undoManager = canvas.undoManager, undoManager.canUndo {
            undoManager.undo()
        } else if !canvas.drawing.strokes.isEmpty {
            var drawing = canvas.drawing
            drawing.strokes.removeLast()
            // Reported through canvasViewDrawingDidChange like any edit.
            canvas.drawing = drawing
        }
    }

    private func applyPendingChanges() {
        guard !strokeInFlight else { return }
        if let config = pendingConfig {
            pendingConfig = nil
            setAnnotating(config.annotating, pencilOnly: config.pencilOnly, showsToolPicker: config.picker)
        }
        if pendingClear {
            pendingClear = false
            pendingDrawing = nil
            // As an edit, so the controller also persists the clear over the stroke just committed.
            canvas.drawing = PKDrawing()
        } else if let drawing = pendingDrawing {
            pendingDrawing = nil
            showDrawing(drawing)
        }
        if pendingPlacement {
            pendingPlacement = false
            setNeedsLayout()
        }
        if pendingPickerRefresh {
            pendingPickerRefresh = false
            updateToolPicker()
        }
    }

    /// Recovers if PencilKit ever skips `canvasViewDidEndUsingTool`, so queued changes still land.
    private func scheduleStrokeWatchdog() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            guard let self, self.strokeInFlight else { return }
            if self.canvas.drawingGestureRecognizer.numberOfTouches == 0 {
                inkLog.error("stroke end was never reported; releasing queued changes")
                self.strokeInFlight = false
                self.applyPendingChanges()
            } else {
                self.scheduleStrokeWatchdog()
            }
        }
    }

    // MARK: PKCanvasViewDelegate

    func canvasViewDidBeginUsingTool(_ canvasView: PKCanvasView) {
        strokeInFlight = true
        // TEMP DIAG
        do {
            var lines = ["DIAG canvas bounds=\(canvasView.bounds.size) zoom=\(canvasView.zoomScale) contentSize=\(canvasView.contentSize)"]
            func walk(_ layer: CALayer, _ path: String) {
                if let metal = layer as? CAMetalLayer {
                    lines.append("DIAG metal \(path) bounds=\(metal.bounds.size) drawable=\(metal.drawableSize) scale=\(metal.contentsScale)")
                }
                for (i, s) in (layer.sublayers ?? []).enumerated() { walk(s, path + "/\(i)") }
            }
            if let window { walk(window.layer, "w") }
            for line in lines { inkLog.error("\(line, privacy: .public)") }
        }
        if isAnnotating, showsToolPicker, !canvas.isFirstResponder {
            // Something else took first responder (e.g. the Ask panel); bring the picker back after this stroke.
            pendingPickerRefresh = true
        }
    }

    func canvasViewDidEndUsingTool(_ canvasView: PKCanvasView) {
        strokeInFlight = false
        // Let PencilKit finish committing the stroke before anything touches the canvas.
        DispatchQueue.main.async { [weak self] in
            self?.applyPendingChanges()
        }
    }

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        guard !isApplyingDrawing else { return }
        // The user's edit supersedes a cloud copy that was waiting for tool-up.
        pendingDrawing = nil
        controller?.canvasDrawingDidChange(canvasView.drawing)
    }

    // MARK: UIScrollViewDelegate

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        updateContentGeometry()
        updateCalloutPosition()
    }

    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        updateCalloutPosition()
    }

    func scrollViewWillBeginDragging(_ scrollView: UIScrollView) {
        userMovedDocument = true
    }

    func scrollViewWillBeginZooming(_ scrollView: UIScrollView, with view: UIView?) {
        userMovedDocument = true
    }

    // MARK: Text selection (reading mode)

    private func pageHit(at location: CGPoint, clampToNearestPage: Bool) -> PageHit? {
        var nearest: (page: Int, point: CGPoint, distance: CGFloat)?
        for (index, view) in pageViews.enumerated() {
            let point = view.convert(location, from: self)
            if view.bounds.contains(point) {
                return PageHit(page: index, point: point.applying(view.viewToPage))
            }
            guard clampToNearestPage else { continue }
            let clamped = CGPoint(
                x: min(max(point.x, view.bounds.minX), view.bounds.maxX),
                y: min(max(point.y, view.bounds.minY), view.bounds.maxY)
            )
            let distance = hypot(clamped.x - point.x, clamped.y - point.y)
            if nearest.map({ distance < $0.distance }) ?? true {
                nearest = (index, clamped, distance)
            }
        }
        guard let nearest else { return nil }
        return PageHit(page: nearest.page, point: nearest.point.applying(pageViews[nearest.page].viewToPage))
    }

    private func word(at location: CGPoint) -> (hit: PageHit, word: PDFSelection)? {
        guard let hit = pageHit(at: location, clampToNearestPage: false),
              let word = document?.page(at: hit.page)?.selectionForWord(at: hit.point),
              !(word.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return (hit, word)
    }

    @objc private func handleSelectPress(_ gesture: UILongPressGestureRecognizer) {
        let location = gesture.location(in: self)
        switch gesture.state {
        case .began:
            guard let found = word(at: location) else { return }
            hideAskCallout()
            selectionAnchor = found.hit
            dragLocation = location
            applySelection(found.word)
            UISelectionFeedbackGenerator().selectionChanged()
        case .changed:
            dragLocation = location
            extendSelection(to: location, force: false)
            updateAutoscroll(for: location)
        case .ended:
            stopAutoscroll()
            extendSelection(to: location, force: true)
            showAskCallout()
        case .cancelled, .failed:
            stopAutoscroll()
            showAskCallout()
        default:
            break
        }
    }

    private func extendSelection(to location: CGPoint, force: Bool) {
        let now = CACurrentMediaTime()
        guard force || now - lastSelectionUpdate > 1.0 / 30 else { return }
        lastSelectionUpdate = now
        guard let anchor = selectionAnchor,
              let document,
              let hit = pageHit(at: location, clampToNearestPage: true),
              let anchorPage = document.page(at: anchor.page),
              let endPage = document.page(at: hit.page)
        else { return }
        // Reading order: page, then top-down (PDF y grows upward), then left-right.
        let forward = (hit.page, -hit.point.y, hit.point.x) >= (anchor.page, -anchor.point.y, anchor.point.x)
        let range = forward
            ? document.selection(from: anchorPage, at: anchor.point, to: endPage, at: hit.point)
            : document.selection(from: endPage, at: hit.point, to: anchorPage, at: anchor.point)
        let extended = range ?? PDFSelection(document: document)
        if let word = anchorPage.selectionForWord(at: anchor.point) {
            extended.add(word)
        }
        if let word = endPage.selectionForWord(at: hit.point) {
            extended.add(word)
        }
        applySelection(extended)
    }

    private func applySelection(_ newSelection: PDFSelection?) {
        var paths: [Int: CGMutablePath] = [:]
        var head: (page: Int, rect: CGRect)?
        let text = newSelection?.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if let newSelection, let document, !text.isEmpty {
            for line in newSelection.selectionsByLine() {
                for page in line.pages {
                    let index = document.index(for: page)
                    guard index != NSNotFound, index < pageViews.count else { continue }
                    let rect = line.bounds(for: page).applying(pageViews[index].pageToView)
                    guard !rect.isNull, !rect.isEmpty else { continue }
                    let path = paths[index] ?? CGMutablePath()
                    path.addRect(rect)
                    paths[index] = path
                    if head == nil {
                        head = (index, rect)
                    }
                }
            }
        }
        selection = text.isEmpty ? nil : newSelection
        selectionHead = selection == nil ? nil : head
        for (index, view) in pageViews.enumerated() {
            view.setSelectionPath(paths[index])
        }
    }

    private func clearSelection() {
        selectionAnchor = nil
        stopAutoscroll()
        applySelection(nil)
        hideAskCallout()
    }

    private func updateAutoscroll(for location: CGPoint) {
        let margin: CGFloat = 64
        let top = safeAreaInsets.top + margin
        let bottom = bounds.height - safeAreaInsets.bottom - margin
        if location.y < top {
            autoscrollSpeed = -min(24, (top - location.y) * 0.4)
        } else if location.y > bottom {
            autoscrollSpeed = min(24, (location.y - bottom) * 0.4)
        } else {
            stopAutoscroll()
            return
        }
        guard autoscrollLink == nil else { return }
        let link = CADisplayLink(target: self, selector: #selector(autoscrollTick))
        link.add(to: .main, forMode: .common)
        autoscrollLink = link
    }

    @objc private func autoscrollTick() {
        let current = canvas.contentOffset
        let target = clampedOffset(CGPoint(x: current.x, y: current.y + autoscrollSpeed))
        guard target != current else { return }
        canvas.contentOffset = target
        extendSelection(to: dragLocation, force: false)
    }

    private func stopAutoscroll() {
        autoscrollLink?.invalidate()
        autoscrollLink = nil
        autoscrollSpeed = 0
    }

    @objc private func handleTap(_ gesture: UITapGestureRecognizer) {
        if selection != nil {
            clearSelection()
            return
        }
        guard let hit = pageHit(at: gesture.location(in: self), clampToNearestPage: false),
              let page = document?.page(at: hit.page),
              let annotation = page.annotation(at: hit.point)
        else { return }
        if let url = annotation.url ?? (annotation.action as? PDFActionURL)?.url {
            UIApplication.shared.open(url)
        } else if let destination = (annotation.action as? PDFActionGoTo)?.destination ?? annotation.destination {
            scroll(to: destination)
        }
    }

    private func scroll(to destination: PDFDestination) {
        guard let document, let page = destination.page else { return }
        let index = document.index(for: page)
        guard index != NSNotFound, index < pageViews.count, index < pageRects.count else { return }
        var viewY: CGFloat = 0
        if destination.point.y != kPDFDestinationUnspecifiedValue {
            viewY = CGPoint(x: 0, y: destination.point.y).applying(pageViews[index].pageToView).y
        }
        let zoom = canvas.zoomScale
        let target = CGPoint(
            x: canvas.contentOffset.x,
            y: (pageRects[index].minY + viewY) * zoom - canvas.adjustedContentInset.top - 12
        )
        canvas.setContentOffset(clampedOffset(target), animated: true)
    }

    // MARK: UIGestureRecognizerDelegate

    override func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        if gestureRecognizer === selectPress {
            return !isAnnotating && word(at: selectPress.location(in: self)) != nil
        }
        if gestureRecognizer === tapGesture {
            return !isAnnotating
        }
        return super.gestureRecognizerShouldBegin(gestureRecognizer)
    }

    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldBeRequiredToFailBy otherGestureRecognizer: UIGestureRecognizer
    ) -> Bool {
        // A press on text may still become a selection; hold the scroll until it can't.
        gestureRecognizer === selectPress && otherGestureRecognizer === canvas.panGestureRecognizer
    }

    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
    ) -> Bool {
        gestureRecognizer === tapGesture
    }

    // MARK: Ask callout

    private func showAskCallout() {
        guard selection != nil, onAskSelection != nil else {
            hideAskCallout()
            return
        }
        var config = askCalloutButton.configuration ?? UIButton.Configuration.filled()
        config.title = askMenuTitle
        config.image = UIImage(systemName: "sparkles")
        askCalloutButton.configuration = config
        askCalloutButton.bounds.size = askCalloutButton.intrinsicContentSize
        askCalloutButton.isHidden = false
        updateCalloutPosition()
        bringSubviewToFront(askCalloutButton)
        UIView.animate(withDuration: 0.22, delay: 0, options: [.curveEaseOut, .beginFromCurrentState]) {
            self.askCalloutButton.alpha = 1.0
            self.askCalloutButton.transform = .identity
        }
    }

    private func updateCalloutPosition() {
        guard !askCalloutButton.isHidden, let head = selectionHead, head.page < pageViews.count else { return }
        let rect = pageViews[head.page].convert(head.rect, to: self)
        let size = askCalloutButton.bounds.size
        // Stay clear of the reader's top controls.
        let minY = safeAreaInsets.top + 72 + size.height / 2
        let maxY = bounds.height - safeAreaInsets.bottom - size.height / 2 - 12
        var y = rect.minY - size.height / 2 - 10
        if y < minY {
            y = rect.maxY + size.height / 2 + 10
        }
        let x = min(max(rect.midX, size.width / 2 + 12), bounds.width - size.width / 2 - 12)
        askCalloutButton.center = CGPoint(x: x, y: min(max(y, minY), max(minY, maxY)))
    }

    private func hideAskCallout() {
        guard !askCalloutButton.isHidden else { return }
        UIView.animate(withDuration: 0.18, delay: 0, options: [.curveEaseIn, .beginFromCurrentState]) {
            self.askCalloutButton.alpha = 0
            self.askCalloutButton.transform = CGAffineTransform(scaleX: 0.85, y: 0.85)
        } completion: { _ in
            if self.askCalloutButton.alpha == 0 {
                self.askCalloutButton.isHidden = true
            }
        }
    }

    @objc private func handleAskCalloutTapped() {
        guard let text = selection?.string?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return
        }
        clearSelection()
        onAskSelection?(text)
    }
}
