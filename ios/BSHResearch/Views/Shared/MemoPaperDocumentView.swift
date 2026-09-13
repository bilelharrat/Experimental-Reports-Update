import PDFKit
import PencilKit
import SwiftUI
import UIKit

/// Full-bleed “paper on a desk” PDF reader with a scroll-synced PencilKit layer.
///
/// Pages use real `PDFView` surfaces so text remains selectable while reading.
/// A single transparent `PKCanvasView` covers the stack so ink stays locked to
/// the document while scrolling and pinching. Annotation mode disables page
/// hit-testing so PencilKit owns the gesture stream.
struct MemoPaperDocumentView: UIViewRepresentable {
    let url: URL
    @Binding var drawing: PKDrawing
    var isAnnotating: Bool
    var showsToolPicker: Bool
    var canvasRef: Binding<PKCanvasView?>
    var replaceToken: Int
    /// Prefer Pencil-only drawing on iPad so a finger can still pan/zoom.
    var pencilOnly: Bool
    /// Edit-menu title for selection → Ask (persona invite, e.g. "Ask Warren").
    var askMenuTitle: String = "Ask"
    /// Fired when the user chooses Ask from the PDF selection menu / callout.
    var onAskSelection: ((String) -> Void)? = nil

    func makeCoordinator() -> Coordinator {
        Coordinator(drawing: $drawing)
    }

    func makeUIView(context: Context) -> PaperDeskHostView {
        let host = PaperDeskHostView()
        host.onDrawingChange = { newDrawing in
            context.coordinator.drawing.wrappedValue = newDrawing
        }
        host.onAskSelection = { text in context.coordinator.onAskSelection?(text) }
        host.askMenuTitle = askMenuTitle
        host.load(url: url)
        context.coordinator.host = host
        context.coordinator.onAskSelection = onAskSelection
        return host
    }

    func updateUIView(_ host: PaperDeskHostView, context: Context) {
        context.coordinator.host = host
        context.coordinator.onAskSelection = onAskSelection
        host.onDrawingChange = { newDrawing in
            context.coordinator.drawing.wrappedValue = newDrawing
        }
        host.onAskSelection = { text in context.coordinator.onAskSelection?(text) }
        host.askMenuTitle = askMenuTitle
        canvasRef.wrappedValue = host.canvasView

        if context.coordinator.appliedReplaceToken != replaceToken {
            context.coordinator.appliedReplaceToken = replaceToken
            host.applyDrawing(drawing, suppressDelegate: true)
        }

        host.setAnnotating(isAnnotating, pencilOnly: pencilOnly)
        host.setToolPickerVisible(showsToolPicker && isAnnotating)
    }

    static func dismantleUIView(_ host: PaperDeskHostView, coordinator: Coordinator) {
        host.setToolPickerVisible(false)
        coordinator.host = nil
    }

    final class Coordinator {
        var drawing: Binding<PKDrawing>
        var appliedReplaceToken = -1
        weak var host: PaperDeskHostView?
        var onAskSelection: ((String) -> Void)?

        init(drawing: Binding<PKDrawing>) {
            self.drawing = drawing
        }
    }
}

// MARK: - Selectable PDF page

/// Single-page PDF surface sized to the media box. Supports text selection and
/// an Ask action via edit menu (UIMenuController + UIMenuBuilder) plus a host
/// floating callout when selection changes — PDFKit’s internal first responder
/// often swallows custom menu items alone.
final class MemoSelectablePDFPageView: PDFView, UIEditMenuInteractionDelegate {
    var askMenuTitle: String = "Ask" {
        didSet { refreshAskMenuItem() }
    }
    var onAskSelection: ((String) -> Void)?
    var onSelectionPresenceChange: ((MemoSelectablePDFPageView, Bool) -> Void)?

    private var editMenuInteraction: UIEditMenuInteraction?

    override init(frame: CGRect) {
        super.init(frame: frame)
        configure()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configure()
    }

    private func configure() {
        displayMode = .singlePage
        displayDirection = .vertical
        displayBox = .mediaBox
        autoScales = false
        backgroundColor = .white
        isOpaque = true
        isUserInteractionEnabled = true
        if #available(iOS 16.0, *) {
            pageShadowsEnabled = false
        }

        let interaction = UIEditMenuInteraction(delegate: self)
        addInteraction(interaction)
        editMenuInteraction = interaction

        refreshAskMenuItem()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleOwnSelectionChanged(_:)),
            name: .PDFViewSelectionChanged,
            object: self
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    func configurePage(document: PDFDocument, pageIndex: Int) {
        self.document = document
        if let page = document.page(at: pageIndex) {
            go(to: page)
        }
        fitScaleToBounds()
        disableInternalScrolling()
    }

    func fitScaleToBounds() {
        guard let page = currentPage else { return }
        let media = page.bounds(for: .mediaBox)
        guard media.width > 1, bounds.width > 1 else { return }
        minScaleFactor = 0.1
        maxScaleFactor = 4.0
        scaleFactor = bounds.width / media.width
        disableInternalScrolling()
    }

    private func disableInternalScrolling() {
        for sub in subviews {
            guard let scroll = sub as? UIScrollView else { continue }
            scroll.isScrollEnabled = false
            scroll.bounces = false
            scroll.showsVerticalScrollIndicator = false
            scroll.showsHorizontalScrollIndicator = false
            scroll.contentOffset = .zero
        }
    }

    private func refreshAskMenuItem() {
        // Legacy path still honored by PDFKit on current iOS alongside buildMenu.
        let items = (UIMenuController.shared.menuItems ?? []).filter {
            $0.action != #selector(askSelectedText(_:))
        }
        UIMenuController.shared.menuItems = items + [
            UIMenuItem(title: askMenuTitle, action: #selector(askSelectedText(_:))),
        ]
    }

    override var canBecomeFirstResponder: Bool { true }

    override func canPerformAction(_ action: Selector, withSender sender: Any?) -> Bool {
        if action == #selector(askSelectedText(_:)) {
            return hasAskableSelection
        }
        return super.canPerformAction(action, withSender: sender)
    }

    override func target(forAction action: Selector, withSender sender: Any?) -> Any? {
        if action == #selector(askSelectedText(_:)), hasAskableSelection {
            return self
        }
        return super.target(forAction: action, withSender: sender)
    }

    override func buildMenu(with builder: UIMenuBuilder) {
        super.buildMenu(with: builder)
        guard hasAskableSelection else { return }
        let ask = UIAction(title: askMenuTitle, image: UIImage(systemName: "bubble.left")) { [weak self] _ in
            self?.askSelectedText(nil)
        }
        builder.insertSibling(
            UIMenu(options: .displayInline, children: [ask]),
            afterMenu: .standardEdit
        )
    }

    // MARK: UIEditMenuInteractionDelegate

    func editMenuInteraction(
        _ interaction: UIEditMenuInteraction,
        menuFor configuration: UIEditMenuConfiguration,
        suggestedActions: [UIMenuElement]
    ) -> UIMenu? {
        var actions = suggestedActions
        if hasAskableSelection {
            let ask = UIAction(title: askMenuTitle, image: UIImage(systemName: "bubble.left")) { [weak self] _ in
                self?.askSelectedText(nil)
            }
            actions.insert(ask, at: 0)
        }
        return UIMenu(children: actions)
    }

    @objc func askSelectedText(_ sender: Any?) {
        guard let text = currentSelection?.string?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !text.isEmpty
        else { return }
        onAskSelection?(text)
        clearSelection()
        onSelectionPresenceChange?(self, false)
    }

    private var hasAskableSelection: Bool {
        !(currentSelection?.string?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty ?? true)
    }

    @objc private func handleOwnSelectionChanged(_ note: Notification) {
        guard hasAskableSelection else {
            onSelectionPresenceChange?(self, false)
            return
        }
        // Become first responder so UIMenuController / edit menu can resolve
        // our custom Ask selector even when PDFKit’s internal view held focus.
        _ = becomeFirstResponder()
        refreshAskMenuItem()
        onSelectionPresenceChange?(self, true)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        fitScaleToBounds()
        if hasAskableSelection {
            onSelectionPresenceChange?(self, true)
        }
    }
}

// MARK: - Host view

final class PaperDeskHostView: UIView, UIScrollViewDelegate, PKCanvasViewDelegate {
    let scrollView = UIScrollView()
    let contentView = UIView()
    let pagesContainer = UIView()
    let canvasView = PKCanvasView()

    var onDrawingChange: ((PKDrawing) -> Void)?
    var onAskSelection: ((String) -> Void)?
    var askMenuTitle: String = "Ask" {
        didSet {
            pagePDFViews.forEach { $0.askMenuTitle = askMenuTitle }
            askCallout.setTitle(askMenuTitle, for: .normal)
        }
    }

    private let toolPicker = PKToolPicker()
    private var pageViews: [UIView] = []
    private var pagePDFViews: [MemoSelectablePDFPageView] = []
    private var hasSetInitialZoom = false
    private var suppressDelegate = false
    private var contentWidth: CGFloat = 612
    private var documentURL: URL?
    private var pdfDocument: PDFDocument?
    private weak var activeSelectionPage: MemoSelectablePDFPageView?

    /// Host-level Ask chip — sits above the scroll/canvas stack so it is never
    /// covered by the transparent PencilKit layer.
    private lazy var askCallout: UIButton = {
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .capsule
        config.baseBackgroundColor = .systemBlue
        config.baseForegroundColor = .white
        config.contentInsets = NSDirectionalEdgeInsets(top: 8, leading: 14, bottom: 8, trailing: 14)
        config.image = UIImage(systemName: "bubble.left.fill")
        config.imagePadding = 6
        config.titleTextAttributesTransformer = UIConfigurationTextAttributesTransformer { incoming in
            var out = incoming
            out.font = .systemFont(ofSize: 14, weight: .semibold)
            return out
        }
        let button = UIButton(configuration: config)
        button.setTitle(askMenuTitle, for: .normal)
        button.addTarget(self, action: #selector(handleAskCalloutTap), for: .touchUpInside)
        button.layer.shadowColor = UIColor.black.cgColor
        button.layer.shadowOpacity = 0.22
        button.layer.shadowRadius = 8
        button.layer.shadowOffset = CGSize(width: 0, height: 3)
        button.isHidden = true
        return button
    }()

    private let pageGap: CGFloat = 28
    private let deskTopPadding: CGFloat = 36
    private let deskBottomPadding: CGFloat = 80

    override init(frame: CGRect) {
        super.init(frame: frame)
        configure()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configure()
    }

    private func configure() {
        backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.90, alpha: 1)

        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.delegate = self
        scrollView.backgroundColor = .clear
        scrollView.alwaysBounceVertical = true
        scrollView.alwaysBounceHorizontal = true
        scrollView.showsVerticalScrollIndicator = true
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.contentInsetAdjustmentBehavior = .never
        scrollView.decelerationRate = .fast
        // Don’t delay touches — text selection + callout taps feel snappier.
        scrollView.delaysContentTouches = false
        addSubview(scrollView)

        contentView.backgroundColor = .clear
        scrollView.addSubview(contentView)
        contentView.addSubview(pagesContainer)

        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.drawingPolicy = .pencilOnly
        canvasView.isUserInteractionEnabled = false
        canvasView.overrideUserInterfaceStyle = .light
        canvasView.delegate = self
        // Keep canvas above pages for ink visibility, but pass hits through when
        // not annotating so PDF text selection remains interactive.
        contentView.addSubview(canvasView)

        addSubview(askCallout)

        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: topAnchor),
            scrollView.leadingAnchor.constraint(equalTo: leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
    }

    @objc private func handleAskCalloutTap() {
        guard let page = activeSelectionPage else { return }
        page.askSelectedText(nil)
        hideAskCallout()
    }

    func showAskCallout(for pdfPage: MemoSelectablePDFPageView) {
        guard let selection = pdfPage.currentSelection, let page = pdfPage.currentPage else {
            hideAskCallout()
            return
        }
        let boundsInPage = selection.bounds(for: page)
        let rectInPDF = pdfPage.convert(boundsInPage, from: page)
        guard !rectInPDF.isNull, boundsInPage.width > 0 else {
            hideAskCallout()
            return
        }
        let rect = convert(rectInPDF, from: pdfPage)
        activeSelectionPage = pdfPage
        askCallout.setTitle(askMenuTitle, for: .normal)
        askCallout.sizeToFit()
        let size = askCallout.bounds.size.width > 1
            ? askCallout.bounds.size
            : askCallout.intrinsicContentSize
        let width = max(size.width, 96)
        let height = max(size.height, 36)
        var x = rect.midX - width / 2
        var y = rect.minY - height - 12
        x = min(max(8, x), max(8, bounds.width - width - 8))
        if y < 8 {
            y = min(rect.maxY + 12, max(8, bounds.height - height - 8))
        }
        askCallout.frame = CGRect(x: x, y: y, width: width, height: height)
        askCallout.isHidden = false
        bringSubviewToFront(askCallout)
    }

    func hideAskCallout() {
        askCallout.isHidden = true
        activeSelectionPage = nil
    }

    func load(url: URL) {
        documentURL = url
        hasSetInitialZoom = false
        pageViews.forEach { $0.removeFromSuperview() }
        pageViews.removeAll()
        pagePDFViews.removeAll()

        guard let document = PDFDocument(url: url), document.pageCount > 0 else { return }
        pdfDocument = document

        var maxWidth: CGFloat = 0
        var y: CGFloat = deskTopPadding
        var pageFrames: [(UIView, CGRect)] = []

        for index in 0..<document.pageCount {
            guard let page = document.page(at: index) else { continue }
            let media = page.bounds(for: .mediaBox)
            maxWidth = max(maxWidth, media.width)

            let pageCard = UIView(frame: CGRect(origin: CGPoint(x: 0, y: y), size: media.size))
            pageCard.backgroundColor = .clear
            pageCard.layer.shadowColor = UIColor.black.cgColor
            pageCard.layer.shadowOpacity = 0.16
            pageCard.layer.shadowRadius = 12
            pageCard.layer.shadowOffset = CGSize(width: 0, height: 5)
            pageCard.layer.shadowPath = UIBezierPath(roundedRect: pageCard.bounds, cornerRadius: 2).cgPath
            pageCard.clipsToBounds = false

            let pdfPage = MemoSelectablePDFPageView(frame: pageCard.bounds)
            pdfPage.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            pdfPage.askMenuTitle = askMenuTitle
            pdfPage.onAskSelection = { [weak self] text in
                self?.onAskSelection?(text)
            }
            pdfPage.onSelectionPresenceChange = { [weak self] activePage, hasSelection in
                guard let self else { return }
                if hasSelection {
                    for other in self.pagePDFViews where other !== activePage {
                        other.clearSelection()
                    }
                    self.showAskCallout(for: activePage)
                } else if self.activeSelectionPage === activePage {
                    self.hideAskCallout()
                }
            }
            pdfPage.configurePage(document: document, pageIndex: index)
            pdfPage.layer.cornerRadius = 2
            pdfPage.clipsToBounds = true
            pageCard.addSubview(pdfPage)

            pagesContainer.addSubview(pageCard)
            pageViews.append(pageCard)
            pagePDFViews.append(pdfPage)
            pageFrames.append((pageCard, pageCard.frame))
            y += media.height + pageGap
        }

        contentWidth = max(maxWidth, 1)
        let contentHeight = max(y - pageGap + deskBottomPadding, 1)

        // Center pages horizontally inside the content width.
        for (pageCard, frame) in pageFrames {
            let centered = CGRect(
                x: (contentWidth - frame.width) / 2,
                y: frame.origin.y,
                width: frame.width,
                height: frame.height
            )
            pageCard.frame = centered
        }

        pagesContainer.frame = CGRect(x: 0, y: 0, width: contentWidth, height: contentHeight)
        canvasView.frame = pagesContainer.frame
        contentView.frame = pagesContainer.frame
        scrollView.contentSize = CGSize(width: contentWidth, height: contentHeight)

        setNeedsLayout()
    }

    func applyDrawing(_ drawing: PKDrawing, suppressDelegate: Bool) {
        self.suppressDelegate = suppressDelegate
        canvasView.drawing = drawing
        self.suppressDelegate = false
    }

    func setAnnotating(_ enabled: Bool, pencilOnly: Bool) {
        canvasView.isUserInteractionEnabled = enabled
        canvasView.drawingPolicy = pencilOnly ? .pencilOnly : .anyInput
        // While annotating, pages stop stealing touches (selection is secondary).
        for pdf in pagePDFViews {
            pdf.isUserInteractionEnabled = !enabled
            if enabled {
                pdf.clearSelection()
            }
        }
        if enabled {
            hideAskCallout()
            _ = canvasView.becomeFirstResponder()
        }
    }

    func setToolPickerVisible(_ visible: Bool) {
        if visible {
            toolPicker.setVisible(true, forFirstResponder: canvasView)
            toolPicker.addObserver(canvasView)
            DispatchQueue.main.async { [weak self] in
                _ = self?.canvasView.becomeFirstResponder()
            }
        } else {
            toolPicker.setVisible(false, forFirstResponder: canvasView)
            toolPicker.removeObserver(canvasView)
            if canvasView.isFirstResponder {
                canvasView.resignFirstResponder()
            }
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard contentWidth > 0, bounds.width > 0 else { return }

        let hInset: CGFloat = AdaptiveLayout.isPad ? 52 : 18
        let available = max(bounds.width - hInset * 2, 120)
        let fit = available / contentWidth

        scrollView.minimumZoomScale = max(0.35, fit * 0.92)
        scrollView.maximumZoomScale = max(fit * 4.5, 2.5)

        if !hasSetInitialZoom {
            scrollView.zoomScale = fit
            hasSetInitialZoom = true
            centerContentIfNeeded()
            // Nudge down slightly so the first page breathes under the status area.
            scrollView.contentOffset = CGPoint(
                x: scrollView.contentOffset.x,
                y: -scrollView.adjustedContentInset.top
            )
        } else {
            centerContentIfNeeded()
        }
    }

    /// When not annotating, the ink canvas must never steal hits from PDF text
    /// selection or the Ask callout sitting under it.
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        let hit = super.hitTest(point, with: event)
        guard let hit else { return nil }
        if !canvasView.isUserInteractionEnabled,
           hit === canvasView || hit.isDescendant(of: canvasView) {
            let pointInPages = pagesContainer.convert(point, from: self)
            if let pageHit = pagesContainer.hitTest(pointInPages, with: event) {
                return pageHit
            }
            let pointInScroll = scrollView.convert(point, from: self)
            return scrollView.hitTest(pointInScroll, with: event)
        }
        return hit
    }

    // MARK: UIScrollViewDelegate

    func viewForZooming(in scrollView: UIScrollView) -> UIView? {
        contentView
    }

    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        if let page = activeSelectionPage {
            showAskCallout(for: page)
        }
    }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centerContentIfNeeded()
        if let page = activeSelectionPage {
            showAskCallout(for: page)
        }
    }

    private func centerContentIfNeeded() {
        let boundsSize = scrollView.bounds.size
        var frame = contentView.frame
        if frame.size.width < boundsSize.width {
            frame.origin.x = (boundsSize.width - frame.size.width) * 0.5
        } else {
            frame.origin.x = 0
        }
        if frame.size.height < boundsSize.height {
            frame.origin.y = (boundsSize.height - frame.size.height) * 0.5
        } else {
            frame.origin.y = 0
        }
        contentView.frame = frame
    }

    // MARK: PKCanvasViewDelegate

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        guard !suppressDelegate else { return }
        onDrawingChange?(canvasView.drawing)
    }
}
