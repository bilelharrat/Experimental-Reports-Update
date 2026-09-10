import SwiftUI

@MainActor
final class ReportDetailViewModel: ObservableObject {
    let reportId: String

    @Published var report: ReportDetail?
    @Published var loading = false
    @Published var error: String?
    @Published var actionError: String?
    @Published var readerLang: AppLanguage = .en
    @Published var previewURL: URL?
    @Published var shareURL: URL?
    @Published var downloading = false
    @Published var liveLog: [String] = []
    @Published var artifactText: String?
    @Published var artifactTitle: String?
    @Published var loadingArtifact = false

    private var pollTask: Task<Void, Never>?
    private var streamTask: Task<Void, Never>?

    init(reportId: String) {
        self.reportId = reportId
    }

    deinit {
        pollTask?.cancel()
        streamTask?.cancel()
    }

    func start(preferredLang: AppLanguage) async {
        readerLang = preferredLang
        await refresh()
        beginPolling()
        attachStreamIfNeeded()
    }

    func stop() {
        pollTask?.cancel()
        streamTask?.cancel()
        pollTask = nil
        streamTask = nil
    }

    func refresh() async {
        loading = report == nil
        defer { loading = false }
        do {
            let detail: ReportDetail = try await APIClient.shared.get("reports/\(reportId)")
            report = detail
            if detail.isTerminal {
                stop()
            } else {
                attachStreamIfNeeded()
            }
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func cancel() async {
        actionError = nil
        do {
            try await APIClient.shared.postEmpty("reports/\(reportId)/cancel")
            await refresh()
            stop()
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func resume() async {
        actionError = nil
        do {
            try await APIClient.shared.postEmpty("reports/\(reportId)/resume")
            await refresh()
            beginPolling()
            attachStreamIfNeeded()
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func dismissReport() async {
        actionError = nil
        do {
            try await APIClient.shared.postEmpty("reports/\(reportId)/dismiss")
            await refresh()
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func deleteReport() async {
        actionError = nil
        do {
            try await APIClient.shared.delete("reports/\(reportId)")
            report = nil
            stop()
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Download a memo DOCX (or PDF preview) and open it in Quick Look.
    func openDocument(language code: String, preferPreview: Bool = false) async {
        let path: String?
        if preferPreview {
            path = report?.previewUrls?[code]
                ?? report?.downloadUrls?[code]
        } else {
            path = report?.downloadUrls?[code]
        }
        guard let path else { return }
        downloading = true
        defer { downloading = false }
        do {
            let (data, name) = try await APIClient.shared.download(path)
            let fileName: String
            if let name, !name.isEmpty {
                fileName = name
            } else {
                fileName = "\(reportId)-\(code).docx"
            }
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)
            try data.write(to: url, options: .atomic)
            previewURL = url
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func shareDocument(language code: String) async {
        guard let path = report?.downloadUrls?[code] else { return }
        downloading = true
        defer { downloading = false }
        do {
            let (data, name) = try await APIClient.shared.download(path)
            let fileName = name ?? "\(reportId)-\(code).docx"
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)
            try data.write(to: url, options: .atomic)
            shareURL = url
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func loadArtifact(_ artifact: AnalysisArtifact) async {
        guard let path = artifact.downloadUrl else { return }
        loadingArtifact = true
        defer { loadingArtifact = false }
        do {
            let (data, _) = try await APIClient.shared.download(path)
            artifactTitle = artifact.label ?? artifact.filename ?? "Analysis"
            artifactText = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .isoLatin1)
                ?? ""
        } catch {
            actionError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func beginPolling() {
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_500_000_000)
                guard !Task.isCancelled else { break }
                await refresh()
                if report?.summary.isTerminal == true { break }
            }
        }
    }

    private func attachStreamIfNeeded() {
        guard let stream = report?.streamUrl, !stream.isEmpty else { return }
        guard streamTask == nil else { return }
        streamTask = Task {
            let client = SSEClient()
            do {
                for try await event in await client.stream(path: stream) {
                    guard !Task.isCancelled else { break }
                    if let payload = parseJSON(event.data) {
                        let type = (payload["type"] as? String) ?? event.event ?? "event"
                        let message = (payload["message"] as? String)
                            ?? (payload["stage"] as? String)
                            ?? (payload["error"] as? String)
                            ?? type
                        liveLog.append(message)
                        if liveLog.count > 40 { liveLog.removeFirst(liveLog.count - 40) }
                        if ["done", "error"].contains(type) {
                            await refresh()
                            break
                        }
                    } else if !event.data.isEmpty {
                        liveLog.append(event.data)
                    }
                }
            } catch {
                // Polling remains the safety net.
            }
            streamTask = nil
        }
    }

    private func parseJSON(_ text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return obj
    }
}

private extension ReportDetail {
    var isTerminal: Bool { summary.isTerminal }
}

struct ReportDetailView: View {
    let reportId: String
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: ReportDetailViewModel
    @State private var confirmDelete = false

    init(reportId: String) {
        self.reportId = reportId
        _model = StateObject(wrappedValue: ReportDetailViewModel(reportId: reportId))
    }

    var body: some View {
        List {
            if model.loading && model.report == nil {
                ProgressView(language.t("common.loading"))
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if let err = model.error, model.report == nil {
                Text(err).foregroundStyle(.red)
            } else if let report = model.report {
                statusSection(report)
                openMemoSection(report)
                actionsSection(report)
                if let actionError = model.actionError {
                    Section {
                        Text(actionError).foregroundStyle(.red).font(.footnote)
                    }
                }
                analysisSection(report)
                if !model.liveLog.isEmpty {
                    Section(language.t("research.live_log")) {
                        ForEach(Array(model.liveLog.suffix(12).enumerated()), id: \.offset) { _, line in
                            Text(line).font(.caption.monospaced())
                        }
                    }
                }
                bodySection(report)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(language.t("research.report"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task {
            await model.start(preferredLang: language.language)
        }
        .onDisappear { model.stop() }
        .sheet(item: Binding(
            get: { model.shareURL.map { IdentifiedURL(url: $0) } },
            set: { model.shareURL = $0?.url }
        )) { item in
            ShareSheet(items: [item.url])
        }
        .sheet(item: Binding(
            get: { model.previewURL.map { IdentifiedURL(url: $0) } },
            set: { model.previewURL = $0?.url }
        )) { item in
            NavigationStack {
                QuickLookPreview(url: item.url)
                    .ignoresSafeArea()
                    .navigationTitle(item.url.lastPathComponent)
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button(language.t("common.done")) { model.previewURL = nil }
                        }
                        ToolbarItem(placement: .primaryAction) {
                            ShareLink(item: item.url) {
                                Image(systemName: "square.and.arrow.up")
                            }
                        }
                    }
            }
        }
        .sheet(isPresented: Binding(
            get: { model.artifactText != nil },
            set: { if !$0 { model.artifactText = nil; model.artifactTitle = nil } }
        )) {
            NavigationStack {
                ScrollView {
                    Text(model.artifactText ?? "")
                        .font(.body)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .textSelection(.enabled)
                }
                .navigationTitle(model.artifactTitle ?? language.t("research.analysis"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(language.t("common.done")) {
                            model.artifactText = nil
                            model.artifactTitle = nil
                        }
                    }
                }
            }
        }
        .confirmationDialog(language.t("research.delete_confirm"), isPresented: $confirmDelete) {
            Button(language.t("research.delete"), role: .destructive) {
                Task {
                    await model.deleteReport()
                    dismiss()
                }
            }
        }
    }

    @ViewBuilder
    private func statusSection(_ report: ReportDetail) -> some View {
        Section {
            LabeledContent(language.t("research.report_type"), value: report.reportType ?? "—")
            LabeledContent(language.t("research.audience"), value: report.audience ?? "—")
            if report.summary.isRunning {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(report.stage ?? report.status ?? "—")
                        .font(.subheadline.weight(.medium))
                    Spacer()
                    if let started = Self.parseDate(report.createdAt) {
                        // Live elapsed timer so long stages don't look frozen.
                        Text(started, style: .timer)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
            } else {
                LabeledContent(language.t("research.status"), value: report.stage ?? report.status ?? "—")
            }
            if report.progress != nil {
                // Tick every second so the elapsed-time estimate keeps moving
                // even when the server is still parked on a long Claude stage.
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    let shown = Self.displayProgress(for: report)
                    ProgressView(value: shown, total: 100) {
                        Text("\(Int(shown.rounded()))%")
                    }
                }
            }
            if report.summary.isRunning {
                Text(language.t("research.running_hint"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let err = report.error, !(report.status ?? "").hasPrefix("complete") {
                Text(err).font(.footnote).foregroundStyle(.red)
            }
            if let warnings = report.qualityWarnings ?? report.warnings, !warnings.isEmpty {
                ForEach(warnings, id: \.self) { w in
                    Text(w).font(.caption).foregroundStyle(.orange)
                }
            }
        } header: {
            Text(report.companyName ?? report.companyId ?? reportId)
        }
    }

    private static func parseDate(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }

    /// While analysis is parked on a long Claude stage the server used to
    /// leave progress at 15. Prefer the larger of the server value and an
    /// elapsed-time estimate so the meter never looks frozen.
    private static func displayProgress(for report: ReportDetail) -> Double {
        let server = Double(report.progress ?? 0)
        guard report.summary.isRunning, server < 80,
              let started = parseDate(report.createdAt)
        else { return server }
        let elapsed = max(0, Date().timeIntervalSince(started))
        let floor = 15.0
        let ceiling = 78.0
        let halfLife = 300.0
        let frac = 1.0 - pow(0.5, elapsed / halfLife)
        let estimated = floor + (ceiling - floor) * frac
        return min(ceiling, max(server, estimated))
    }

    @ViewBuilder
    private func actionsSection(_ report: ReportDetail) -> some View {
        Section(language.t("research.actions")) {
            if report.summary.isRunning {
                Button(role: .destructive) {
                    Task { await model.cancel() }
                } label: {
                    Label(language.t("research.cancel"), systemImage: "stop.circle")
                }
            }
            if report.resumeAvailable == true {
                Button {
                    Task { await model.resume() }
                } label: {
                    Label(language.t("research.resume"), systemImage: "arrow.clockwise")
                }
            }
            Button {
                Task { await model.dismissReport() }
            } label: {
                Label(language.t("research.dismiss"), systemImage: "eye.slash")
            }
            Button(role: .destructive) {
                confirmDelete = true
            } label: {
                Label(language.t("research.delete"), systemImage: "trash")
            }
            Button {
                Task { await model.refresh() }
            } label: {
                Label(language.t("common.retry"), systemImage: "arrow.clockwise.circle")
            }
        }
    }

    @ViewBuilder
    private func openMemoSection(_ report: ReportDetail) -> some View {
        let urls = report.downloadUrls ?? [:]
        if !urls.isEmpty {
            Section {
                ForEach(urls.keys.sorted(), id: \.self) { key in
                    Button {
                        Task { await model.openDocument(language: key) }
                    } label: {
                        Label(
                            model.downloading
                                ? language.t("common.loading")
                                : String(format: language.t("research.open_memo"), key.uppercased()),
                            systemImage: "doc.richtext"
                        )
                    }
                    .disabled(model.downloading)

                    Button {
                        Task { await model.shareDocument(language: key) }
                    } label: {
                        Label(
                            String(format: language.t("research.share_memo"), key.uppercased()),
                            systemImage: "square.and.arrow.up"
                        )
                    }
                    .disabled(model.downloading)
                }
            } header: {
                Text(language.t("research.memo_files"))
            } footer: {
                Text(language.t("research.memo_files_hint"))
            }
        } else if report.isComplete {
            Section {
                Text(language.t("research.no_docx"))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func analysisSection(_ report: ReportDetail) -> some View {
        let arts = report.analysisArtifacts ?? []
        if !arts.isEmpty {
            Section {
                ForEach(arts) { art in
                    Button {
                        Task { await model.loadArtifact(art) }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(art.label ?? art.filename ?? "Note")
                                    .font(.subheadline.weight(.medium))
                                if let file = art.filename {
                                    Text(file).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            if model.loadingArtifact {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
            } header: {
                Text(language.t("research.analysis"))
            } footer: {
                Text(language.t("research.analysis_hint"))
            }
        }
    }

    @ViewBuilder
    private func bodySection(_ report: ReportDetail) -> some View {
        let text = report.bodyText(lang: model.readerLang)
        // Most memo runs store the deliverable as DOCX, not inline text —
        // only show the reader when there is actual body content.
        if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            Section {
                Picker(language.t("research.reader_lang"), selection: $model.readerLang) {
                    Text("EN").tag(AppLanguage.en)
                    Text("中文").tag(AppLanguage.zh)
                }
                .pickerStyle(.segmented)

                Text(text)
                    .font(.body)
                    .textSelection(.enabled)
            } header: {
                Text(language.t("research.body"))
            }
        }
    }
}

private struct IdentifiedURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}
