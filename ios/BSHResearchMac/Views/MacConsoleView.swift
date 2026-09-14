import SwiftUI
import UniformTypeIdentifiers

/// Persistent Ask Warren sessions per company: survive restarts, hold staged documents,
/// take drag-in attachments, can be cancelled and archived.
struct MacConsoleView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    @State private var prompt = ""
    @State private var attachments: [URL] = []
    @State private var includeLibraryDocs = true
    @State private var creating = false
    @State private var dropTargeted = false
    @FocusState private var focused: Bool

    private var sessions: [MacConsoleSession] { store.consoleSessions[company.id] ?? [] }
    private var selected: MacConsoleSession? { sessions.first { $0.id == store.consoleSelectedSessionId } }
    private var turns: [MacConsoleTurn] { selected.map { store.consoleTurns[$0.id] ?? [] } ?? [] }
    private var streaming: Bool { store.consoleStreamingTurn?.sessionId == selected?.id }

    var body: some View {
        HSplitView {
            sessionList
                .frame(minWidth: 220, idealWidth: 260, maxWidth: 340)
                .layoutPriority(0)
            transcript
                .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)
        }
        .task(id: company.id) {
            await store.loadConsoleSessions(companyId: company.id)
            if let sid = store.consoleSelectedSessionId {
                await store.loadConsoleTurns(companyId: company.id, sessionId: sid)
            }
        }
        .onChange(of: store.consoleSelectedSessionId) { _, sid in
            guard let sid else { return }
            Task { await store.loadConsoleTurns(companyId: company.id, sessionId: sid) }
        }
    }

    // MARK: - Sessions

    private var sessionList: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Sessions").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer()
                Button {
                    creating = true
                    Task {
                        await store.createConsoleSession(companyId: company.id, includeLibraryDocs: includeLibraryDocs, language: "en")
                        creating = false
                    }
                } label: {
                    if creating { ProgressView().controlSize(.mini) } else { Image(systemName: "plus") }
                }
                .buttonStyle(.plain)
                .disabled(creating || !store.canRunTasks)
                .help("New session (stages research + library documents)")
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            Toggle("Include document library", isOn: $includeLibraryDocs)
                .toggleStyle(.checkbox)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.bottom, 6)

            Divider()

            List(selection: $store.consoleSelectedSessionId) {
                if sessions.isEmpty {
                    Text("No sessions yet. Press + to start one.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                ForEach(sessions) { session in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(session.displayTitle).font(.subheadline.weight(.medium)).lineLimit(1)
                            if session.isArchived {
                                Text("archived").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        HStack(spacing: 6) {
                            Text(MacTimeFormat.relative(session.lastUsedAt)).font(.caption2).foregroundStyle(.secondary)
                            if let pct = session.pctUsed {
                                Text("· \(Int(pct * 100))% ctx").font(.caption2).foregroundStyle(.secondary)
                            }
                            if let cost = session.totalCostUsd, cost > 0 {
                                Text(String(format: "· $%.2f", cost)).font(.caption2).foregroundStyle(.secondary)
                            }
                            if session.hydrationStatus == "in_progress" {
                                ProgressView().controlSize(.mini)
                            }
                        }
                        if !session.includedFiles.isEmpty {
                            Text("\(session.includedFiles.count) staged file(s)").font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                    .padding(.vertical, 2)
                    .tag(session.id)
                    .contextMenu {
                        if !session.isArchived {
                            Button("Archive") { Task { await store.archiveConsoleSession(companyId: company.id, sessionId: session.id) } }
                        }
                        Button("Delete", role: .destructive) { Task { await store.deleteConsoleSession(companyId: company.id, sessionId: session.id) } }
                            .disabled(!store.canDeleteDocuments)
                    }
                }
            }
            .listStyle(.inset)
        }
    }

    // MARK: - Transcript

    @ViewBuilder
    private var transcript: some View {
        if let session = selected {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(session.displayTitle).font(.headline)
                        if let headline = session.summaryHeadline, !headline.isEmpty {
                            Text(headline).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        } else if !session.includedFiles.isEmpty {
                            Text(session.includedFiles.prefix(4).compactMap(\.filename).joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                    Spacer()
                    if let activity = store.consoleActivity, streaming {
                        HStack(spacing: 4) { ProgressView().controlSize(.mini); Text(activity).font(.caption).foregroundStyle(.secondary) }
                    }
                    if !session.isArchived {
                        Button {
                            Task { await store.archiveConsoleSession(companyId: company.id, sessionId: session.id) }
                        } label: {
                            Label("Archive", systemImage: "archivebox")
                        }
                        .controlSize(.small)
                        .disabled(streaming)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)

                Divider()

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            if turns.isEmpty {
                                Text(session.isArchived ? "Archived session." : "Ask anything about \(company.title). Staged documents are already in context.")
                                    .font(.subheadline).foregroundStyle(.secondary).padding(.top, 30)
                            }
                            ForEach(turns) { turn in
                                turnBubble(turn)
                                    .id(turn.id)
                            }
                        }
                        .padding(16)
                    }
                    .onChange(of: turns.count) { _, _ in
                        if let last = turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                }

                Divider()

                if !session.isArchived {
                    inputBar(session: session)
                } else if let bullets = Optional(session.summaryBullets), !bullets.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(bullets, id: \.self) { Text("• \($0)").font(.caption) }
                    }
                    .padding(12)
                }
            }
        } else {
            ContentUnavailableView("No session", systemImage: "terminal", description: Text("Create a session to talk to Warren with this company's documents staged."))
        }
    }

    private func turnBubble(_ turn: MacConsoleTurn) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if turn.isUser { Spacer() } else {
                Image(systemName: "building.columns.circle.fill").font(.title2).foregroundStyle(Color.accentColor).padding(.top, 2)
            }
            VStack(alignment: turn.isUser ? .trailing : .leading, spacing: 4) {
                if !turn.isUser && turn.text.isEmpty {
                    HStack(spacing: 6) { ProgressView().controlSize(.small); Text(store.consoleActivity ?? "Thinking…").font(.subheadline).foregroundStyle(.secondary) }
                        .padding(12)
                        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                } else {
                    Text(turn.text)
                        .font(.body)
                        .lineSpacing(3)
                        .textSelection(.enabled)
                        .padding(12)
                        .background(turn.isUser ? Color.accentColor.opacity(0.12) : Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                if !turn.attachments.isEmpty {
                    Text(turn.attachments.compactMap(\.name).joined(separator: ", ")).font(.caption2).foregroundStyle(.secondary)
                }
                HStack(spacing: 6) {
                    Text(MacTimeFormat.relative(turn.ts)).font(.caption2).foregroundStyle(.secondary)
                    if let cost = turn.costUsd { Text(String(format: "$%.3f", cost)).font(.caption2).foregroundStyle(.tertiary) }
                    if let err = turn.error, !err.isEmpty { Text(err).font(.caption2).foregroundStyle(Color.red).lineLimit(1) }
                }
            }
            if turn.isUser {
                Image(systemName: "person.circle.fill").font(.title2).foregroundStyle(.secondary).padding(.top, 2)
            } else { Spacer() }
        }
    }

    private func inputBar(session: MacConsoleSession) -> some View {
        VStack(spacing: 8) {
            if !attachments.isEmpty {
                HStack(spacing: 6) {
                    ForEach(attachments, id: \.self) { url in
                        HStack(spacing: 4) {
                            Image(systemName: "paperclip").font(.caption2)
                            Text(url.lastPathComponent).font(.caption).lineLimit(1)
                            Button { attachments.removeAll { $0 == url } } label: { Image(systemName: "xmark.circle.fill").font(.caption2) }
                                .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Color.secondary.opacity(0.1), in: Capsule())
                    }
                    Spacer()
                }
            }
            HStack(alignment: .bottom, spacing: 10) {
                Button {
                    let panel = NSOpenPanel()
                    panel.allowsMultipleSelection = true
                    panel.canChooseDirectories = false
                    panel.allowedContentTypes = [.png, .jpeg, .webP, .pdf, UTType("com.microsoft.word.doc"), UTType("org.openxmlformats.wordprocessingml.document")].compactMap { $0 }
                    if panel.runModal() == .OK { attachments.append(contentsOf: panel.urls) }
                } label: {
                    Image(systemName: "paperclip")
                }
                .buttonStyle(.plain)
                .help("Attach images, PDFs or Word files (or drop them here)")

                TextField("Ask in this session… (drop files to attach)", text: $prompt, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...6)
                    .focused($focused)
                    .onSubmit { send(session) }

                if streaming {
                    Button("Cancel") { Task { await store.cancelConsoleTurn(companyId: company.id) } }
                        .controlSize(.small)
                } else {
                    Button { send(session) } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.title2)
                            .foregroundStyle(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? Color.secondary : Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canRunTasks)
                    .keyboardShortcut(.defaultAction)
                }
            }
            .padding(12)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(dropTargeted ? Color.accentColor : Color.secondary.opacity(0.2), lineWidth: dropTargeted ? 2 : 1))
        }
        .padding(14)
        .background(.ultraThinMaterial)
        .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
            for provider in providers {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                    var url: URL?
                    if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
                    if let u = item as? URL { url = u }
                    if let url {
                        DispatchQueue.main.async { attachments.append(url) }
                    }
                }
            }
            return true
        }
    }

    private func send(_ session: MacConsoleSession) {
        let text = prompt
        let files = attachments
        prompt = ""
        attachments = []
        store.askConsole(companyId: company.id, sessionId: session.id, prompt: text, attachments: files)
    }
}
