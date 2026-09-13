import SwiftUI
import PhotosUI

// MARK: - Sessions list

@MainActor
final class ConsoleSessionsViewModel: ObservableObject {
    let companyId: String
    @Published var sessions: [ConsoleSession] = []
    @Published var loading = false
    @Published var creating = false
    @Published var error: String?

    init(companyId: String) { self.companyId = companyId }

    func load() async {
        loading = true
        defer { loading = false }
        do {
            sessions = try await APIClient.shared.get("companies/\(companyId)/console/sessions")
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func create(language: String) async -> ConsoleSession? {
        creating = true
        defer { creating = false }
        do {
            let body = ConsoleCreateBody(
                includeBackgroundDocs: true,
                includeLibraryDocs: true,
                outputLanguage: language
            )
            let session: ConsoleSession = try await APIClient.shared.post(
                "companies/\(companyId)/console/sessions", body: body
            )
            await load()
            return session
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            return nil
        }
    }
}

struct ConsoleSessionsView: View {
    let companyId: String
    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model: ConsoleSessionsViewModel
    @State private var opened: ConsoleSession?

    init(companyId: String) {
        self.companyId = companyId
        _model = StateObject(wrappedValue: ConsoleSessionsViewModel(companyId: companyId))
    }

    var body: some View {
        List {
            Section {
                Button {
                    Task {
                        if let session = await model.create(language: language.language.rawValue) {
                            opened = session
                        }
                    }
                } label: {
                    Label(
                        model.creating ? language.t("common.loading") : language.t("console.new"),
                        systemImage: "plus.bubble"
                    )
                }
                .disabled(model.creating)
                if let err = model.error {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }

            let active = model.sessions.filter { !$0.isArchived }
            let archived = model.sessions.filter(\.isArchived)

            if !active.isEmpty {
                Section(language.t("console.active")) {
                    ForEach(active) { session in
                        sessionRow(session)
                    }
                }
            }
            if !archived.isEmpty {
                Section(language.t("console.archived")) {
                    ForEach(archived) { session in
                        sessionRow(session)
                    }
                }
            }
            if model.sessions.isEmpty && !model.loading {
                Text(language.t("console.none")).foregroundStyle(.secondary)
            }
        }
        .navigationTitle(language.t("console.title"))
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.load() }
        .task { await model.load() }
        .navigationDestination(item: $opened) { session in
            ConsoleTranscriptView(companyId: companyId, session: session)
        }
    }

    private func sessionRow(_ session: ConsoleSession) -> some View {
        NavigationLink {
            ConsoleTranscriptView(companyId: companyId, session: session)
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(session.title ?? session.id)
                    .font(.subheadline.weight(.medium))
                HStack(spacing: 8) {
                    if let pct = session.pctUsed {
                        Text("\(Int(pct * 100))% ctx")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(pct >= 0.9 ? .red : pct >= 0.75 ? .orange : .secondary)
                    }
                    if let used = session.lastUsedAt {
                        Text(String(used.prefix(16)).replacingOccurrences(of: "T", with: " "))
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
    }
}

extension ConsoleSession: Hashable {
    static func == (lhs: ConsoleSession, rhs: ConsoleSession) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

// MARK: - Transcript + ask

@MainActor
final class ConsoleTranscriptViewModel: ObservableObject {
    let companyId: String
    let sessionId: String

    @Published var turns: [ConsoleTurn] = []
    @Published var pendingText = ""
    @Published var streaming = false
    @Published var error: String?

    init(companyId: String, sessionId: String) {
        self.companyId = companyId
        self.sessionId = sessionId
    }

    func load() async {
        do {
            turns = try await APIClient.shared.get(
                "companies/\(companyId)/console/sessions/\(sessionId)/turns"
            )
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func ask(prompt: String, images: [(name: String, data: Data)]) async {
        streaming = true
        pendingText = ""
        error = nil
        defer { streaming = false }
        do {
            let res: ConsoleAskResponse = try await APIClient.shared.postMultipart(
                "companies/\(companyId)/console/sessions/\(sessionId)/ask",
                fields: ["prompt": prompt],
                files: images.map { (field: "images", name: $0.name, mime: "image/jpeg", data: $0.data) }
            )
            guard let streamPath = res.streamUrl else {
                await load()
                return
            }
            let client = SSEClient()
            for try await event in await client.stream(path: streamPath) {
                if event.event == "error" {
                    if let data = event.data.data(using: .utf8),
                       let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        error = (obj["error"] as? String) ?? "Ask failed"
                    } else {
                        error = "Ask failed"
                    }
                    break
                }
                guard let data = event.data.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }
                let type = (obj["type"] as? String) ?? ""
                if type == "claude_action" {
                    let action = (obj["action"] as? String) ?? ""
                    if action == "thinking", let chunk = obj["text"] as? String {
                        pendingText += chunk
                    } else if action == "tool_use", pendingText.isEmpty {
                        pendingText = "Using \((obj["tool"] as? String) ?? "tool")…"
                    }
                } else if type == "delta" || type == "text" {
                    if let chunk = obj["text"] as? String {
                        pendingText += chunk
                    }
                } else if let message = obj["message"] as? String, type == "stage" {
                    if pendingText.isEmpty { pendingText = "· \(message)" }
                } else if type == "done" {
                    if let final = obj["text"] as? String, !final.isEmpty {
                        pendingText = final
                    }
                    break
                } else if type == "error" || type == "cancelled" {
                    error = (obj["error"] as? String) ?? "Ask failed"
                    break
                }
            }
            pendingText = ""
            await load()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct ConsoleTranscriptView: View {
    let companyId: String
    let session: ConsoleSession

    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model: ConsoleTranscriptViewModel
    @State private var draft = ""
    @State private var pickedItems: [PhotosPickerItem] = []
    @State private var pickedImages: [(name: String, data: Data)] = []

    init(companyId: String, session: ConsoleSession) {
        self.companyId = companyId
        self.session = session
        _model = StateObject(wrappedValue: ConsoleTranscriptViewModel(companyId: companyId, sessionId: session.id))
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(model.turns) { turn in
                        turnRow(turn).id(turn.id)
                    }
                    if model.streaming {
                        VStack(alignment: .leading, spacing: 6) {
                            if !model.pendingText.isEmpty {
                                bubble(model.pendingText, isUser: false)
                            }
                            HStack(spacing: 6) {
                                ProgressView().controlSize(.small)
                                Text(language.t("console.thinking"))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.leading, 6)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .id("pending")
                    }
                    if let err = model.error {
                        Text(err).font(.caption).foregroundStyle(.red)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            .background(Color(.systemGroupedBackground))
            .onChange(of: model.turns.count) { _, _ in
                if let last = model.turns.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
        .navigationTitle(session.title ?? language.t("console.title"))
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            if !session.isArchived {
                composer
            }
        }
        .task { await model.load() }
    }

    private var composer: some View {
        VStack(spacing: 6) {
            if !pickedImages.isEmpty {
                HStack {
                    ForEach(pickedImages.indices, id: \.self) { idx in
                        Label(pickedImages[idx].name, systemImage: "photo")
                            .font(.caption2)
                            .lineLimit(1)
                    }
                    Spacer()
                    Button {
                        pickedImages = []
                        pickedItems = []
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary)
                    }
                }
                .padding(.horizontal, 4)
            }
            HStack(spacing: 8) {
                PhotosPicker(selection: $pickedItems, maxSelectionCount: 3, matching: .images) {
                    Image(systemName: "photo.badge.plus")
                        .font(.title3)
                }
                .onChange(of: pickedItems) { _, items in
                    Task {
                        var loaded: [(String, Data)] = []
                        for (i, item) in items.enumerated() {
                            if let data = try? await item.loadTransferable(type: Data.self) {
                                loaded.append(("image-\(i + 1).jpg", data))
                            }
                        }
                        pickedImages = loaded
                    }
                }

                TextField(language.t("console.prompt"), text: $draft, axis: .vertical)
                    .lineLimit(1...4)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .strokeBorder(Color(.systemGray4), lineWidth: 1)
                    )

                Button {
                    let prompt = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !prompt.isEmpty else { return }
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    draft = ""
                    let images = pickedImages
                    pickedImages = []
                    pickedItems = []
                    Task { await model.ask(prompt: prompt, images: images) }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 28))
                        .symbolRenderingMode(.hierarchical)
                }
                .disabled(model.streaming || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(10)
        .background(.bar)
    }

    @ViewBuilder
    private func turnRow(_ turn: ConsoleTurn) -> some View {
        VStack(alignment: turn.isUser ? .trailing : .leading, spacing: 3) {
            if let text = turn.text, !text.isEmpty {
                bubble(text, isUser: turn.isUser)
            }
            if let err = turn.error {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(.horizontal, 6)
            }
        }
        .frame(maxWidth: .infinity, alignment: turn.isUser ? .trailing : .leading)
    }

    /// Messages-style bubble: blue/white for you, gray/primary for the model.
    private func bubble(_ text: String, isUser: Bool) -> some View {
        Text(text)
            .font(.body)
            .textSelection(.enabled)
            .foregroundStyle(isUser ? Color.white : Color.primary)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(
                isUser ? Color.accentColor : Color(.secondarySystemGroupedBackground),
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
            .frame(maxWidth: 300, alignment: isUser ? .trailing : .leading)
    }
}
