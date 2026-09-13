import SwiftUI
import WebKit

// MARK: - MacWKWebView (NSViewRepresentable)

struct MacWKWebView: NSViewRepresentable {
    @Binding var url: URL
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool
    @Binding var isLoading: Bool
    @Binding var pageTitle: String
    let webView: WKWebView

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeNSView(context: Context) -> WKWebView {
        webView.navigationDelegate = context.coordinator
        context.coordinator.setupObservers(for: webView)
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        if nsView.url != url && !context.coordinator.isNavigatingInternal {
            nsView.load(URLRequest(url: url))
        }
    }

    class Coordinator: NSObject, WKNavigationDelegate {
        var parent: MacWKWebView
        var isNavigatingInternal = false
        private var kvoTokens: [NSKeyValueObservation] = []

        init(_ parent: MacWKWebView) {
            self.parent = parent
        }

        func setupObservers(for webView: WKWebView) {
            kvoTokens.append(webView.observe(\.canGoBack, options: .new) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.parent.canGoBack = wv.canGoBack }
            })
            kvoTokens.append(webView.observe(\.canGoForward, options: .new) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.parent.canGoForward = wv.canGoForward }
            })
            kvoTokens.append(webView.observe(\.isLoading, options: .new) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.parent.isLoading = wv.isLoading }
            })
            kvoTokens.append(webView.observe(\.title, options: .new) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.parent.pageTitle = wv.title ?? "" }
            })
            kvoTokens.append(webView.observe(\.url, options: .new) { [weak self] wv, _ in
                guard let newURL = wv.url else { return }
                DispatchQueue.main.async {
                    self?.isNavigatingInternal = true
                    self?.parent.url = newURL
                    self?.isNavigatingInternal = false
                }
            })
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            DispatchQueue.main.async { self.parent.isLoading = true }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async { self.parent.isLoading = false }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            DispatchQueue.main.async { self.parent.isLoading = false }
        }
    }
}

// MARK: - MacEmbeddedBrowserPanel (Cursor Style Side Drawer)

struct MacEmbeddedBrowserPanel: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var webView = WKWebView()
    @State private var canGoBack = false
    @State private var canGoForward = false
    @State private var isLoading = false
    @State private var pageTitle = ""
    @State private var inputURLString = ""

    private var activeCompanyTicker: String? {
        store.selectedCompany?.ticker
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header: Cursor / Safari style Omnibox and Nav Bar
            browserHeader

            Divider()

            // Quick Jump Preset Ribbon
            presetsBar

            Divider()

            // Native WebKit Viewport
            MacWKWebView(
                url: $store.browserCurrentURL,
                canGoBack: $canGoBack,
                canGoForward: $canGoForward,
                isLoading: $isLoading,
                pageTitle: $pageTitle,
                webView: webView
            )
            .background(Color(NSColor.textBackgroundColor))
        }
        .background(Color(NSColor.windowBackgroundColor))
        .onAppear {
            inputURLString = store.browserCurrentURL.absoluteString
        }
        .onChange(of: store.browserCurrentURL) { _, newURL in
            inputURLString = newURL.absoluteString
        }
    }

    // MARK: - Header Controls

    private var browserHeader: some View {
        HStack(spacing: 8) {
            // Navigation Buttons (Back / Forward / Refresh)
            HStack(spacing: 4) {
                Button {
                    webView.goBack()
                } label: {
                    Image(systemName: "chevron.backward")
                }
                .buttonStyle(.plain)
                .disabled(!canGoBack)
                .help("Back (⌘[)")
                .keyboardShortcut("[", modifiers: .command)

                Button {
                    webView.goForward()
                } label: {
                    Image(systemName: "chevron.forward")
                }
                .buttonStyle(.plain)
                .disabled(!canGoForward)
                .help("Forward (⌘])")
                .keyboardShortcut("]", modifiers: .command)

                Button {
                    if isLoading {
                        webView.stopLoading()
                    } else {
                        webView.reload()
                    }
                } label: {
                    Image(systemName: isLoading ? "xmark" : "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help(isLoading ? "Stop" : "Reload (⌘R)")
            }
            .foregroundStyle(.secondary)
            .padding(.trailing, 2)

            // Omnibox / Address Field
            HStack(spacing: 6) {
                Image(systemName: store.browserCurrentURL.scheme == "https" ? "lock.fill" : "globe")
                    .font(.caption2)
                    .foregroundStyle(store.browserCurrentURL.scheme == "https" ? .green : .secondary)

                TextField("Enter URL or search…", text: $inputURLString)
                    .textFieldStyle(.plain)
                    .font(.callout.monospaced())
                    .onSubmit {
                        commitAddressInput()
                    }

                if isLoading {
                    ProgressView()
                        .controlSize(.mini)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
            )

            // Pop out to External Safari
            Button {
                MacConfig.openInBrowser(store.browserCurrentURL)
            } label: {
                Image(systemName: "arrow.up.right.square")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Open in External Browser")

            // Close Side Panel Button
            Button {
                withAnimation(.easeInOut(duration: 0.18)) {
                    store.showBrowserPanel = false
                }
            } label: {
                Image(systemName: "xmark")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Close Browser Panel (⌘B)")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color(NSColor.windowBackgroundColor))
    }

    // MARK: - Presets Bar

    private var presetsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                // Web Portal Preset
                PresetChip(label: "Web Portal", icon: "desktopcomputer") {
                    navigate(to: MacConfig.baseURL)
                }

                // SEC EDGAR Search Preset
                PresetChip(label: "SEC EDGAR", icon: "building.columns") {
                    let secURL: URL
                    if let ticker = activeCompanyTicker, !ticker.isEmpty {
                        secURL = URL(string: "https://www.sec.gov/edgar/searchedgar/companysearch?cik=\(ticker)")
                            ?? URL(string: "https://www.sec.gov/edgar/searchedgar/companysearch")!
                    } else {
                        secURL = URL(string: "https://www.sec.gov/edgar/searchedgar/companysearch")!
                    }
                    navigate(to: secURL)
                }

                // Yahoo Finance Preset
                if let ticker = activeCompanyTicker, !ticker.isEmpty {
                    PresetChip(label: "\(ticker) Quote", icon: "chart.xyaxis.line") {
                        if let u = URL(string: "https://finance.yahoo.com/quote/\(ticker)") {
                            navigate(to: u)
                        }
                    }
                }

                // Google Finance Preset
                if let ticker = activeCompanyTicker, !ticker.isEmpty {
                    PresetChip(label: "Google Finance", icon: "magnifyingglass") {
                        if let u = URL(string: "https://www.google.com/finance/quote/\(ticker):NASDAQ") {
                            navigate(to: u)
                        }
                    }
                }

                // Current Company Portal Preset
                if let company = store.selectedCompany {
                    PresetChip(label: company.name ?? company.id, icon: "doc.text") {
                        navigate(to: MacConfig.webCompanyURL(id: company.id))
                    }
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
        .background(Color(NSColor.controlBackgroundColor).opacity(0.4))
    }

    private func commitAddressInput() {
        let trimmed = inputURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        if trimmed.hasPrefix("http://") || trimmed.hasPrefix("https://") {
            if let valid = URL(string: trimmed) {
                navigate(to: valid)
            }
        } else if trimmed.contains(".") && !trimmed.contains(" ") {
            if let valid = URL(string: "https://\(trimmed)") {
                navigate(to: valid)
            }
        } else {
            // Search Google
            let query = trimmed.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? trimmed
            if let searchURL = URL(string: "https://www.google.com/search?q=\(query)") {
                navigate(to: searchURL)
            }
        }
    }

    private func navigate(to target: URL) {
        store.browserCurrentURL = target
        inputURLString = target.absoluteString
        webView.load(URLRequest(url: target))
    }
}

// MARK: - Preset Chip

private struct PresetChip: View {
    let label: String
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.caption2)
                Text(label)
                    .font(.caption2.weight(.medium))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.secondary.opacity(0.12), in: Capsule())
            .foregroundStyle(.primary)
        }
        .buttonStyle(.plain)
    }
}
