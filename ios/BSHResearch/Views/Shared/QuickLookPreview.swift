import SwiftUI
import QuickLook

/// Presents a local file (DOCX/PDF/etc.) in the system Quick Look viewer.
struct QuickLookPreview: UIViewControllerRepresentable {
    let url: URL
    /// When embedded under our own paper-desk chrome, drop QL’s nav chrome.
    var hidesNavigationChrome: Bool = false

    func makeUIViewController(context: Context) -> QLPreviewController {
        let controller = ChromeAwareQLPreviewController()
        controller.hidesNavigationChrome = hidesNavigationChrome
        controller.dataSource = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: QLPreviewController, context: Context) {
        if let chrome = uiViewController as? ChromeAwareQLPreviewController {
            chrome.hidesNavigationChrome = hidesNavigationChrome
        }
        context.coordinator.url = url
        uiViewController.reloadData()
    }

    func makeCoordinator() -> Coordinator { Coordinator(url: url) }

    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        var url: URL
        init(url: URL) { self.url = url }

        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
            url as NSURL
        }
    }
}

/// QLPreviewController that can suppress its own navigation item so the host owns chrome.
private final class ChromeAwareQLPreviewController: QLPreviewController {
    var hidesNavigationChrome: Bool = false

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        applyChromePolicy()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        applyChromePolicy()
    }

    private func applyChromePolicy() {
        guard hidesNavigationChrome else { return }
        navigationController?.setNavigationBarHidden(true, animated: false)
        navigationItem.hidesBackButton = true
        navigationItem.leftBarButtonItems = []
        navigationItem.rightBarButtonItems = []
        // Prefer a document-first canvas; QL still owns zoom/scroll internally.
        view.backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.90, alpha: 1)
    }
}
