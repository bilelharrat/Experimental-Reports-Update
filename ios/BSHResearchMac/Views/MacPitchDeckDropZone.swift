import SwiftUI
import UniformTypeIdentifiers

struct MacPitchDeckDropBanner: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var isTargeted: Bool = false
    @State private var notice: String?
    @State private var noticeTask: Task<Void, Never>?

    private static let deckExtensions: Set<String> = ["pdf", "pptx"]
    private static var deckContentTypes: [UTType] {
        [UTType.pdf, UTType("org.openxmlformats.presentationml.presentation")].compactMap { $0 }
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: isTargeted ? "arrow.down.doc.fill" : (notice == nil ? "doc.badge.plus" : "exclamationmark.triangle"))
                .foregroundStyle(isTargeted ? Color.accentColor : (notice == nil ? Color.secondary : Color.orange))
            Text(isTargeted ? "Drop the deck to file it" : (notice ?? "Drop a pitch deck (PDF or PPTX) to file and extract it"))
                .font(.dsCaption)
                .foregroundStyle(isTargeted ? Color.accentColor : (notice == nil ? Color.secondary : Color.orange))
                .lineLimit(1)
            Spacer(minLength: 4)
            Button("Browse…") { selectDeckViaPicker() }
                .controlSize(.small)
                .disabled(!store.canEditSources)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(isTargeted ? Color.accentColor.opacity(0.10) : Color.clear)
        .overlay(alignment: .top) {
            if isTargeted { Rectangle().fill(Color.accentColor).frame(height: 2) }
        }
        .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
            handleDrop(providers: providers)
        }
        .help("Files the deck under a company, reads the slides and pulls round, raise, post-money, ARR, burn, runway and headcount with page references")
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        let candidates = providers.filter { $0.canLoadObject(ofClass: URL.self) }
        guard !candidates.isEmpty else { return false }
        let group = DispatchGroup()
        let collected = MacDroppedURLs(count: candidates.count)
        for (index, provider) in candidates.enumerated() {
            group.enter()
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                collected.set(url, at: index)
                group.leave()
            }
        }
        group.notify(queue: .main) {
            let dropped = collected.urls
            if let deck = dropped.first(where: { Self.deckExtensions.contains($0.pathExtension.lowercased()) }) {
                store.ingestDeck(url: deck)
            } else {
                let names = dropped.map(\.lastPathComponent).joined(separator: ", ")
                showNotice("Only PDF or PPTX decks can be filed" + (names.isEmpty ? "" : " — \(names) skipped"))
            }
        }
        return true
    }

    private func showNotice(_ text: String) {
        notice = text
        noticeTask?.cancel()
        noticeTask = Task {
            try? await Task.sleep(for: .seconds(6))
            if !Task.isCancelled { notice = nil }
        }
    }

    private func selectDeckViaPicker() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = Self.deckContentTypes
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.prompt = "Intake Pitch Deck"
        if panel.runModal() == .OK, let url = panel.url {
            store.ingestDeck(url: url)
        }
    }
}

private final class MacDroppedURLs: @unchecked Sendable {
    private let lock = NSLock()
    private var slots: [URL?]

    init(count: Int) { slots = Array(repeating: nil, count: count) }

    func set(_ url: URL?, at index: Int) {
        lock.lock(); defer { lock.unlock() }
        slots[index] = url
    }

    var urls: [URL] {
        lock.lock(); defer { lock.unlock() }
        return slots.compactMap { $0 }
    }
}

struct MacPitchDeckIntakeSheet: View {
    let fileURL: URL?
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var companyName: String = ""
    @State private var attachTo: String = ""   // existing company id, or "" for a new record
    @State private var filing = false
    @State private var error: String?
    @State private var result: MacIntakeResult?

    private var canFile: Bool {
        !filing && fileURL != nil && store.canEditSources
            && !(attachTo.isEmpty && companyName.trimmingCharacters(in: .whitespaces).isEmpty)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "doc.badge.arrow.up")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                    Text(result == nil ? "Pitch Deck Intake" : "Deck filed")
                        .font(.headline)
                }
                Spacer()
                Button(result == nil ? "Cancel" : "Close") { dismiss() }
                    .controlSize(.small)
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(.ultraThinMaterial)

            Divider()

            if let result {
                resultBody(result)
            } else {
                formBody
            }

            Divider()

            HStack {
                if let result {
                    Button {
                        if let company = store.companies.first(where: { $0.id == result.company.id }) {
                            store.selectCompany(company)
                            store.selectedTab = .pipeline
                        }
                        dismiss()
                    } label: {
                        Label("Open on Pipeline", systemImage: "rectangle.stack")
                    }
                    .controlSize(.small)
                    if let fileId = result.fileId {
                        Button {
                            Task { await store.summarizeFile(companyId: result.company.id, fileId: fileId) }
                            dismiss()
                        } label: {
                            Label("Summarize with Claude", systemImage: "sparkles")
                        }
                        .controlSize(.small)
                        .disabled(!store.canRunTasks)
                        .help("Runs the structured deck summary on the server; progress shows in the Jobs blotter")
                    }
                }
                Spacer()
                if result == nil {
                    Button {
                        file()
                    } label: {
                        if filing {
                            HStack(spacing: 6) { ProgressView().controlSize(.small); Text("Extracting…") }
                        } else {
                            Label("File & extract", systemImage: "plus.circle")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canFile)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)
        }
        .frame(width: 520)
        .onAppear {
            let fname = fileURL?.deletingPathExtension().lastPathComponent ?? ""
            companyName = fname.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " ")
        }
    }

    private var formBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "doc.text.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(.red)
                VStack(alignment: .leading, spacing: 2) {
                    Text(fileURL?.lastPathComponent ?? "Deck")
                        .font(.subheadline.weight(.semibold))
                    Text(fileURL.map { $0.pathExtension.uppercased() + " · uploads to the research server" } ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(12)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 6) {
                Text("Attach to").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Picker("Attach to", selection: $attachTo) {
                    Text("New company").tag("")
                    Divider()
                    ForEach(store.companies) { company in
                        Text(company.title).tag(company.id)
                    }
                }
                .labelsHidden()
                .disabled(filing)
            }

            if attachTo.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Company name").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    TextField("Company", text: $companyName)
                        .textFieldStyle(.roundedBorder)
                        .disabled(filing)
                        .onSubmit { file() }
                }
            }

            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("The deck is filed under the company, slides are read, and round / raise / post-money / ARR / burn / runway / headcount are pulled with the page each came from. The thesis fit is scored from the extracted text. Nothing is estimated: fields the deck doesn't state stay empty.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(10)
            .background(Color.accentColor.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))

            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
        }
        .padding(20)
    }

    private func resultBody(_ result: MacIntakeResult) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 2) {
                    Text(result.company.title).font(.subheadline.weight(.semibold))
                    Text("\(result.fileName ?? "Deck") · \(result.slideCount) slides read")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let fit = result.thesis {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(fit.score.map { "\($0)% fit" } ?? fit.label)
                            .font(.caption.weight(.bold).monospacedDigit())
                            .foregroundStyle(fitColor(fit))
                        Text(fit.label).font(.caption2).foregroundStyle(.secondary)
                    }
                    .help(fit.reasons.joined(separator: "\n"))
                }
            }

            if result.fields.isEmpty {
                Text("No round or metric statements were found in the slide text. Scanned decks without a text layer read as empty — the summary job can still OCR them.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                VStack(spacing: 0) {
                    ForEach(result.fields) { field in
                        HStack(alignment: .top, spacing: 10) {
                            Text(field.label)
                                .font(.caption.weight(.semibold))
                                .frame(width: 90, alignment: .leading)
                            Text(field.display)
                                .font(.caption.monospacedDigit().weight(.medium))
                                .frame(width: 90, alignment: .leading)
                            VStack(alignment: .leading, spacing: 1) {
                                if let page = field.page {
                                    Text("p. \(page)").font(.caption2.weight(.semibold)).foregroundStyle(Color.accentColor)
                                }
                                if let excerpt = field.excerpt {
                                    Text(excerpt).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 10).padding(.vertical, 6)
                        Divider()
                    }
                }
                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            }

            if let fit = result.thesis, !fit.openQuestions.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Open questions for the thesis").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    ForEach(fit.openQuestions, id: \.self) { q in
                        Label(q, systemImage: "questionmark.circle").font(.caption)
                    }
                }
            }
        }
        .padding(20)
    }

    private func fitColor(_ fit: MacThesisScore) -> Color {
        switch fit.fit {
        case "strong": return .green
        case "partial": return .orange
        case "weak", "disqualified": return .red
        default: return .secondary
        }
    }

    private func file() {
        guard canFile, let fileURL else { return }
        let name = companyName.trimmingCharacters(in: .whitespaces)
        filing = true
        error = nil
        Task {
            let accessed = fileURL.startAccessingSecurityScopedResource()
            defer { if accessed { fileURL.stopAccessingSecurityScopedResource() } }
            if let r = await store.intakeDeck(fileURL: fileURL, companyName: attachTo.isEmpty ? name : nil, companyId: attachTo.isEmpty ? nil : attachTo) {
                result = r
            } else {
                error = store.error ?? "Could not file the deck."
            }
            filing = false
        }
    }
}
