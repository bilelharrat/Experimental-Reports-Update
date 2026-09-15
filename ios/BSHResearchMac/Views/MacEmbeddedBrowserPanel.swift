import SwiftUI
import WebKit

// MARK: - MacWKWebView (NSViewRepresentable)

struct MacWKWebView: NSViewRepresentable {
    @Binding var url: URL
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool
    @Binding var isLoading: Bool
    @Binding var pageTitle: String
    @Binding var loadError: String?
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
                    guard let self, self.parent.loadError == nil else { return }
                    self.isNavigatingInternal = true
                    self.parent.url = newURL
                    self.isNavigatingInternal = false
                }
            })
        }

        private func report(_ error: Error) {
            let nsError = error as NSError
            guard nsError.code != NSURLErrorCancelled else { return }
            let failing = (nsError.userInfo[NSURLErrorFailingURLErrorKey] as? URL)?.absoluteString
                ?? (nsError.userInfo[NSURLErrorFailingURLStringErrorKey] as? String)
            let text = failing.map { "\($0) — \(error.localizedDescription)" } ?? error.localizedDescription
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadError = text
            }
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isLoading = true
                self.parent.loadError = nil
            }
        }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            DispatchQueue.main.async { self.parent.loadError = nil }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async { self.parent.isLoading = false }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            report(error)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            report(error)
        }
    }
}

final class MacBrowserController: ObservableObject {
    let webView = WKWebView()
}

// MARK: - MacEmbeddedBrowserPanel (Cursor Style Side Drawer)

struct MacEmbeddedBrowserPanel: View {
    @EnvironmentObject private var store: MacAppStore

    @StateObject private var browser = MacBrowserController()
    @State private var canGoBack = false
    @State private var canGoForward = false
    @State private var isLoading = false
    @State private var pageTitle = ""
    @State private var inputURLString = ""
    @State private var loadError: String?

    private var webView: WKWebView { browser.webView }

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

            if let loadError {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.dsLabel)
                        .foregroundStyle(Color.dsWarning)
                    Text(loadError)
                        .font(.dsCaption)
                        .lineLimit(2)
                        .textSelection(.enabled)
                    Spacer(minLength: 8)
                    Button {
                        self.loadError = nil
                    } label: {
                        Image(systemName: "xmark").font(.dsLabel)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.dsWarning.opacity(0.10))
                Divider()
            }

            // Native WebKit Viewport
            MacWKWebView(
                url: $store.browserCurrentURL,
                canGoBack: $canGoBack,
                canGoForward: $canGoForward,
                isLoading: $isLoading,
                pageTitle: $pageTitle,
                loadError: $loadError,
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
                    .font(.callout.monospacedDigit())
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
                        if let u = Self.yahooQuoteURL(ticker: ticker) {
                            navigate(to: u)
                        }
                    }
                }

                // Google Finance Preset
                if let ticker = activeCompanyTicker, !ticker.isEmpty {
                    PresetChip(label: "Google Finance", icon: "magnifyingglass") {
                        var c = URLComponents(string: "https://www.google.com/finance")!
                        c.queryItems = [URLQueryItem(name: "q", value: ticker)]
                        if let u = c.url {
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

    static func yahooQuoteURL(ticker: String) -> URL? {
        let upper = ticker.uppercased()
        var symbol = upper
        if upper.range(of: "^[A-Z]{1,5}\\.[A-Z]$", options: .regularExpression) != nil {
            symbol = upper.replacingOccurrences(of: ".", with: "-")
        }
        let encoded = symbol.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? symbol
        return URL(string: "https://finance.yahoo.com/quote/\(encoded)")
    }

    static func looksLikeHost(_ input: String) -> Bool {
        guard !input.contains(" ") else { return false }
        var host = input
        if let slash = host.firstIndex(of: "/") { host = String(host[..<slash]) }
        if let colon = host.lastIndex(of: ":"), host[host.index(after: colon)...].allSatisfy(\.isNumber) {
            host = String(host[..<colon])
        }
        guard !host.isEmpty else { return false }
        if host == "localhost" { return true }
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        if labels.count == 4, labels.allSatisfy({ !$0.isEmpty && $0.allSatisfy(\.isNumber) }) { return true }
        guard labels.count >= 2, let last = labels.last else { return false }
        return last.count >= 2 && last.allSatisfy(\.isLetter)
    }

    static func searchURL(for text: String) -> URL? {
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "&=+#?")
        var c = URLComponents(string: "https://www.google.com/search")!
        c.percentEncodedQuery = "q=" + (text.addingPercentEncoding(withAllowedCharacters: allowed) ?? text)
        return c.url
    }

    private func commitAddressInput() {
        let trimmed = inputURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        if trimmed.hasPrefix("http://") || trimmed.hasPrefix("https://") {
            if let valid = URL(string: trimmed) {
                navigate(to: valid)
            } else if let searchURL = Self.searchURL(for: trimmed) {
                navigate(to: searchURL)
            }
        } else if Self.looksLikeHost(trimmed), let valid = URL(string: "https://\(trimmed)") {
            navigate(to: valid)
        } else if let searchURL = Self.searchURL(for: trimmed) {
            navigate(to: searchURL)
        }
    }

    private func navigate(to target: URL) {
        loadError = nil
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
