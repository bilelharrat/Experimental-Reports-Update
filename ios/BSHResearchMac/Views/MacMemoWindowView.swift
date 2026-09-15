import SwiftUI
import AppKit

extension OpenWindowAction {
    /// Bring the main desk forward (or open it) after a secondary window changed its state.
    func revealDesk() {
        NSApp.activate(ignoringOtherApps: true)
        if let desk = NSApp.windows.first(where: { ($0.identifier?.rawValue ?? "").hasPrefix("main") && ($0.isVisible || $0.isMiniaturized) }) {
            desk.makeKeyAndOrderFront(nil)
        } else {
            callAsFunction(id: "main")
        }
    }
}

/// A memo in its own window — open several side by side for IC prep.
/// Select text → "Ask about this passage"; IC Review can drive `findText` to jump to a claim.
struct MacMemoWindowView: View {
    let request: MacMemoWindowRequest
    var findText: Binding<MacFindRequest?>? = nil
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.openWindow) private var openWindow

    @State private var showDecision = false
    @State private var loaded: MacLoadedMemo?
    @State private var language: String
    @State private var loading = false
    @State private var error: String?
    @State private var showInk = true
    @State private var selectionText: String?
    @State private var currentPage: Int?

    init(request: MacMemoWindowRequest, findText: Binding<MacFindRequest?>? = nil) {
        self.request = request
        self.findText = findText
        _language = State(initialValue: request.language)
    }

    private var report: MacReport? {
        loaded?.report ?? store.report(for: request.reportId)
    }

    private var company: MacCompany? {
        guard let cid = report?.companyId else { return nil }
        return store.companies.first { $0.id == cid }
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            content
        }
        .frame(minWidth: 700, minHeight: 560)
        .navigationTitle(loaded?.title ?? report.map { "\($0.companyName ?? "") — \($0.displayTitle)" } ?? "Memo")
        .focusedSceneValue(\.deskTarget, MacDeskCommandTarget(
            companyId: report?.companyId,
            reportId: request.reportId,
            recordDecision: { showDecision = true },
            openICReview: { if let report { store.openICReview(report: report) } }
        ))
        .sheet(isPresented: $showDecision) {
            if let company {
                MacDecisionSheet(company: company, seedReportId: request.reportId)
                    .environmentObject(store)
            }
        }
        .task(id: language) {
            await load()
        }
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(loaded?.title ?? "Investment Memo")
                    .font(.dsHeadline)
                    .lineLimit(1)
                    .help("Report \(request.reportId)")
                HStack(spacing: 6) {
                    if let report {
                        MacStatusPill(
                            text: report.statusTone,
                            color: report.isComplete ? .green : (report.isFailed ? .red : .orange)
                        )
                    }
                    if let page = currentPage {
                        Text("p. \(page)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            if loaded?.overlayData != nil {
                HStack(spacing: 6) {
                    Image(systemName: "pencil.tip.crop.circle.fill")
                        .foregroundStyle(showInk ? Color.orange : Color.secondary)
                    Toggle("iPad Ink", isOn: $showInk)
                        .toggleStyle(.switch)
                        .controlSize(.small)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                .help("Toggle iPad Apple Pencil ink overlay")
            }

            GlassSegmentedPicker("Language", selection: $language, segments: ["en": "English", "zh": "中文"])
            .frame(width: 140)

            // Context-aware Ask: the selected passage travels with the question.
            Button {
                let prompt = selectionText != nil
                    ? "Explain and challenge this passage of the memo."
                    : "Give me your primary reflections on this memo: thesis strength, key risks and what would change the recommendation."
                store.askWarren(
                    prompt,
                    context: .memo(reportId: request.reportId, page: currentPage, selectionText: selectionText),
                    company: company
                )
                openWindow.revealDesk()
            } label: {
                Label(selectionText == nil ? "Ask about memo" : "Ask about selection", systemImage: "sparkles")
            }
            .disabled(!store.canRunTasks || company == nil || store.copilotStreaming)
            .help(selectionText == nil ? "Ask Warren with this memo as context; the answer opens on the desk" : "Ask Warren about the selected passage; the answer opens on the desk")

            if let company {
                Button {
                    store.showCompany(company)
                    openWindow.revealDesk()
                } label: {
                    Label("Dossier", systemImage: "building.columns")
                }
                    .help("Show this company on the Research Desk")
            }

            Button {
                let url: URL
                if let cid = report?.companyId {
                    url = MacConfig.webCompanyMemoURL(companyId: cid, reportId: request.reportId)
                } else {
                    url = MacConfig.webReportURL(id: request.reportId)
                }
                MacConfig.openInBrowser(url)
            } label: {
                Label("Open on Web", systemImage: "safari")
            }

            if let url = loaded?.url {
                ShareLink(item: url) {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
                }
        }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.bar)
        }

        @ViewBuilder
        private var content: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor).ignoresSafeArea()

            if let loaded {
                GeometryReader { geo in
                    Group {
                        if loaded.isPDF {
                            MacPDFKitView(
                                url: loaded.url,
                                overlayData: showInk ? loaded.overlayData : nil,
                                overlayOpacity: 0.95,
                                findRequest: findText?.wrappedValue,
                                onSelection: { text in selectionText = text },
                                onPageChange: { page in currentPage = page }
                            )
                        } else {
                            MacQuickLookView(url: loaded.url)
                        }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                }
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
                .padding(16)
            } else if loading {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Loading memo…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            } else {
                ContentUnavailableView(
                    "Memo not available",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text(error ?? "This report has no \(language.uppercased()) file yet. Follow the run in the Jobs blotter.")
                )
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        selectionText = nil
        defer { loading = false }
        do {
            loaded = try await store.loadMemoDocument(reportId: request.reportId, language: language)
        } catch {
            loaded = nil
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
