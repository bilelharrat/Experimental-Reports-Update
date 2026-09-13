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

    /// Download a memo for deep reading. Prefers the rendered PDF when available
    /// (paper-desk + Pencil); falls back to the DOCX for Quick Look.
    func openDocument(language code: String, preferPreview: Bool = true) async {
        let candidates: [String] = {
            if preferPreview {
                return [
                    report?.previewUrls?[code],
                    report?.downloadUrls?[code],
                ].compactMap { $0 }
            }
            return [report?.downloadUrls?[code]].compactMap { $0 }
        }()
        guard !candidates.isEmpty else { return }
        downloading = true
        defer { downloading = false }
        var lastError: Error?
        for path in candidates {
            do {
                let (data, name) = try await APIClient.shared.download(path)
                let fileName: String
                if let name, !name.isEmpty {
                    fileName = name
                } else if path.contains("/preview") {
                    fileName = "\(reportId)-\(code).pdf"
                } else {
                    fileName = "\(reportId)-\(code).docx"
                }
                let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)
                try data.write(to: url, options: .atomic)
                previewURL = url
                return
            } catch {
                lastError = error
            }
        }
        if let lastError {
            actionError = (lastError as? LocalizedError)?.errorDescription
                ?? lastError.localizedDescription
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

    private var previewBinding: Binding<IdentifiedURL?> {
        Binding(
            get: { model.previewURL.map { IdentifiedURL(url: $0) } },
            set: { model.previewURL = $0?.url }
        )
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
        .readableContentWidth()
        .navigationTitle(language.t("research.report"))
        .navigationBarTitleDisplayMode(.inline)
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
        // iPad: full-screen paper desk. iPhone: large sheet is enough.
        .modifier(MemoReaderPresenter(
            item: previewBinding,
            reportId: reportId,
            companyId: model.report?.companyId,
            companyName: model.report?.companyName,
            onDismiss: { model.previewURL = nil }
        ))
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
            HStack(spacing: 12) {
                MonogramAvatar(name: report.companyName ?? report.companyId ?? reportId, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(report.reportType ?? language.t("research.report"))
                        .font(.headline)
                    Text(report.audience ?? "—")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                StatusPill(text: statusText(report), color: statusTone(report))
            }
            .padding(.vertical, 2)
            if report.summary.isRunning {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(report.stage ?? report.status ?? "—")
                        .font(.subheadline.weight(.medium))
                        .lineLimit(1)
                    Spacer()
                    if let started = Self.parseDate(report.createdAt) {
                        // Live elapsed timer so long stages don't look frozen.
                        Text(started, style: .timer)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if report.progress != nil {
                // Tick every second so the elapsed-time estimate keeps moving
                // even when the server is still parked on a long Claude stage.
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    let shown = Self.displayProgress(for: report)
                    VStack(alignment: .leading, spacing: 4) {
                        ProgressView(value: shown, total: 100)
                            .tint(statusTone(report))
                        Text("\(Int(shown.rounded()))%")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 2)
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

    private func statusText(_ report: ReportDetail) -> String {
        let raw = (report.status ?? "").lowercased()
        if raw.hasPrefix("complete") { return "Complete" }
        if raw.hasPrefix("failed") { return "Failed" }
        if raw == "cancelled" { return "Cancelled" }
        if report.summary.isRunning { return "Running" }
        return report.status ?? "—"
    }

    private func statusTone(_ report: ReportDetail) -> Color {
        let raw = (report.status ?? "").lowercased()
        if raw.hasPrefix("complete") { return .green }
        if raw.hasPrefix("failed") || raw == "cancelled" { return .red }
        if report.summary.isRunning { return .orange }
        return .secondary
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
        return Group {
            if !urls.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 12) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Color.accentColor.opacity(0.12))
                                    .frame(width: 40, height: 40)
                                Image(systemName: "doc.richtext.fill")
                                    .font(.title3)
                                    .foregroundStyle(Color.accentColor)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Investment Diligence Memo")
                                    .font(.subheadline.weight(.semibold))
                                Text("Full institutional analysis deliverable")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        HStack(spacing: 8) {
                            if urls["en"] != nil {
                                Button {
                                    Task { await model.openDocument(language: "en") }
                                } label: {
                                    Label(
                                        model.downloading ? language.t("common.loading") : "Read (EN)",
                                        systemImage: "book.pages"
                                    )
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(model.downloading)
                            }

                            if urls["zh"] != nil {
                                Button {
                                    Task { await model.openDocument(language: "zh") }
                                } label: {
                                    Label(
                                        model.downloading ? language.t("common.loading") : "Read (ZH)",
                                        systemImage: "book.pages"
                                    )
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                }
                                .buttonStyle(.bordered)
                                .disabled(model.downloading)
                            }

                            ForEach(urls.keys.filter { $0 != "en" && $0 != "zh" }.sorted(), id: \.self) { key in
                                Button {
                                    Task { await model.openDocument(language: key) }
                                } label: {
                                    Label(
                                        model.downloading ? language.t("common.loading") : "Read (\(key.uppercased()))",
                                        systemImage: "book.pages"
                                    )
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                }
                                .buttonStyle(.bordered)
                                .disabled(model.downloading)
                            }

                            Spacer(minLength: 4)

                            if urls.count == 1, let singleKey = urls.keys.first {
                                Button {
                                    Task { await model.shareDocument(language: singleKey) }
                                } label: {
                                    Image(systemName: "square.and.arrow.up")
                                        .font(.subheadline)
                                }
                                .buttonStyle(.bordered)
                                .disabled(model.downloading)
                            } else {
                                Menu {
                                    ForEach(urls.keys.sorted(), id: \.self) { key in
                                        Button {
                                            Task { await model.shareDocument(language: key) }
                                        } label: {
                                            Label("Share (\(key.uppercased()))", systemImage: "square.and.arrow.up")
                                        }
                                    }
                                } label: {
                                    Image(systemName: "square.and.arrow.up")
                                        .font(.subheadline)
                                }
                                .buttonStyle(.bordered)
                                .disabled(model.downloading)
                            }
                        }
                    }
                    .padding(.vertical, 4)
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

/// iPad gets an immersive full-screen paper desk; iPhone keeps a large sheet.
private struct MemoReaderPresenter: ViewModifier {
    @Binding var item: IdentifiedURL?
    let reportId: String
    var companyId: String?
    var companyName: String?
    var onDismiss: () -> Void

    func body(content: Content) -> some View {
        if AdaptiveLayout.isPad {
            content
                .fullScreenCover(item: $item) { preview in
                    PaperDeskReader(
                        url: preview.url,
                        reportId: reportId,
                        companyId: companyId,
                        companyName: companyName,
                        onDismiss: onDismiss
                    )
                }
        } else {
            content
                .sheet(item: $item) { preview in
                    PaperDeskReader(
                        url: preview.url,
                        reportId: reportId,
                        companyId: companyId,
                        companyName: companyName,
                        onDismiss: onDismiss
                    )
                    .bshSheetChrome()
                }
        }
    }
}
