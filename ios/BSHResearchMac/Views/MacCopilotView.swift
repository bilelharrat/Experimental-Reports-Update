import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Ask Warren: one chat about one company, seen through one lens. Everything the user can
/// change (company, lens, answer depth, saved sessions) lives in a single header row; the
/// on-screen context rides above the input like an attachment.
struct MacCopilotView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var inputPrompt = ""
    @State private var showSessions = false
    @State private var fileDropTargeted = false
    @FocusState private var isInputFocused: Bool

    private var company: MacCompany? { store.selectedCompany ?? store.companies.first }
    private var persona: MacCopilotPersona { store.copilotPersona }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if showSessions {
                if let company {
                    MacConsoleView(company: company)
                } else {
                    noCompanyState
                }
            } else {
                chat
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.dsCanvas)
        // Each time Warren opens: what the team asked meanwhile is on the server.
        .task(id: company?.id) { await store.loadCopilotThread(force: true) }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            companyMenu
            if !showSessions {
                personaMenu
            }
            Spacer(minLength: 8)
            if !showSessions {
                GlassSegmentedPicker("Answer", selection: $store.copilotDeepMode, segments: [false: "Quick", true: "Deep"])
                .fixedSize()
                .help("Quick: an answer in under a minute.\nDeep: reads every research file on this company and runs in the background (a few minutes; progress shows in Jobs).")

                MacWarrenThreadsButton()
                MacWarrenNewChatButton {
                    inputPrompt = ""
                    isInputFocused = true
                }
            }
            Button {
                showSessions.toggle()
            } label: {
                Label(showSessions ? "Back to Chat" : "Sessions",
                      systemImage: showSessions ? "bubble.left.and.bubble.right" : "clock.arrow.circlepath")
            }
            .help(showSessions
                  ? "Return to the quick chat"
                  : "Saved conversations that keep this company's documents loaded and accept file attachments")
        }
        .controlSize(.regular)
        .dsToolbarStrip()
    }

    private var companyMenu: some View {
        Menu {
            if store.companies.isEmpty {
                Text("No companies yet")
            }
            ForEach(store.companies) { c in
                Button {
                    guard c.id != company?.id else { return }
                    store.clearCopilotContext()
                    store.selectCompany(c)
                } label: {
                    if c.id == company?.id {
                        Label(companyLabel(c), systemImage: "checkmark")
                    } else {
                        Text(companyLabel(c))
                    }
                }
            }
        } label: {
            Label(company.map(companyLabel) ?? "Choose a company", systemImage: "building.2")
        }
        .fixedSize()
        .disabled(store.companies.isEmpty)
        .help("The company Warren answers about")
    }

    private var personaMenu: some View {
        Menu {
            ForEach(MacCopilotPersona.allCases) { p in
                Button {
                    store.copilotPersona = p
                } label: {
                    Image(systemName: p == persona ? "checkmark" : p.icon)
                    Text(p.displayName)
                    Text(p.tagline)
                }
            }
        } label: {
            Label(persona.displayName, systemImage: persona.icon)
        }
        .fixedSize()
        .help("The lens the answer is written through: \(persona.tagline.lowercased())")
    }

    private func companyLabel(_ c: MacCompany) -> String {
        if let ticker = c.ticker, !ticker.isEmpty { return "\(ticker) · \(c.title)" }
        return c.title
    }

    // MARK: - Chat

    private var chat: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    Group {
                        if company == nil {
                            noCompanyState.padding(.top, 60)
                        } else if store.copilotViewingThread != nil {
                            earlierThread
                        } else if store.copilotMessages.isEmpty {
                            emptyState
                        } else {
                            transcript
                        }
                    }
                    .frame(maxWidth: 780)
                    .frame(maxWidth: .infinity)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 20)
                }
                .onChange(of: store.copilotMessages.count) { _, _ in
                    scrollToBottom(proxy)
                }
                .onChange(of: store.copilotMessages.last?.text) { _, _ in
                    scrollToBottom(proxy)
                }
            }

            composer
        }
        .onAppear { isInputFocused = true }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        guard let last = store.copilotMessages.last else { return }
        withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(last.id, anchor: .bottom) }
    }

    private var noCompanyState: some View {
        ContentUnavailableView {
            Label(store.companies.isEmpty ? "No companies yet" : "Pick a company", systemImage: "building.2")
        } description: {
            Text(store.companies.isEmpty
                 ? "Add a company on the Pipeline desk, then come back to ask Warren about it."
                 : "Warren answers using one company's memos, filings and notes. Choose which one from the menu at the top left.")
        } actions: {
            if store.companies.isEmpty {
                Button("Open Pipeline") { store.selectedTab = .pipeline }
            }
        }
    }

    // MARK: Empty state

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 22) {
            VStack(alignment: .leading, spacing: 6) {
                Text("What do you want to know about \(company?.title ?? "this company")?")
                    .font(.dsTitle)
                Text("Answers draw on this company's memos, filings and research notes.")
                    .font(.dsBody)
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 12)

            VStack(alignment: .leading, spacing: 8) {
                sectionLabel("Lens")
                HStack(spacing: 8) {
                    ForEach(MacCopilotPersona.allCases) { p in
                        lensCard(p)
                    }
                }
            }

            if let actions = store.visibleCopilotContextInfo?.actions, !actions.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    sectionLabel(store.copilotContext.isSpecific
                                 ? "About \(store.copilotContext.chipLabel ?? "what's on screen")"
                                 : "From the research desk")
                    ForEach(actions) { action in
                        suggestionRow(action.label, icon: "sparkles") {
                            store.sendCopilotMessage(prompt: action.prompt)
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                sectionLabel("Try asking")
                ForEach(persona.starters(company: company?.ticker ?? company?.title ?? "this company"), id: \.self) { s in
                    suggestionRow(s, icon: "text.bubble") {
                        store.sendCopilotMessage(prompt: s)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.dsLabel)
            .foregroundStyle(.secondary)
    }

    private func lensCard(_ p: MacCopilotPersona) -> some View {
        let selected = p == persona
        return Button {
            store.copilotPersona = p
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Image(systemName: p.icon)
                    Text(p.displayName).font(.dsSubhead)
                    Spacer(minLength: 0)
                    if selected {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(Color.accentColor)
                    }
                }
                Text(p.tagline)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .padding(10)
            .frame(maxWidth: .infinity, minHeight: 64, alignment: .topLeading)
            .background(selected ? Color.accentColor.opacity(0.10) : Color.dsCard,
                        in: RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(selected ? Color.accentColor.opacity(0.6) : Color.dsHairline, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func suggestionRow(_ text: String, icon: String, action: @escaping () -> Void) -> some View {
        SuggestionRow(text: text, icon: icon, action: action)
            .disabled(!canAsk)
            .help(askBlockedReason ?? "Ask this")
    }

    // MARK: Transcript

    /// An earlier thread, read-only: nobody adds to a closed thread.
    private var earlierThread: some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(store.copilotViewingMessages) { msg in
                CopilotBubbleView(message: msg, readOnly: true)
                    .id(msg.id)
            }
        }
    }

    private var transcript: some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(store.copilotMessages) { msg in
                CopilotBubbleView(
                    message: msg,
                    isLatestAnswer: msg.id == store.copilotMessages.last?.id && msg.role == .assistant,
                    activity: store.copilotCurrentThinking,
                    deepMode: store.copilotDeepMode,
                    onRetry: store.copilotStreaming ? nil : { store.retryLastCopilotQuestion() }
                )
                .id(msg.id)
            }

            if !store.copilotStreaming, let last = store.copilotMessages.last,
               last.role == .assistant, !last.isError, !last.text.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(MacCopilotPersona.followUps, id: \.self) { f in
                            Button(f) { store.sendCopilotMessage(prompt: f) }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                                .disabled(!canAsk)
                        }
                    }
                    .padding(.leading, 40)
                }
            }
        }
    }

    // MARK: - Composer

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let blocked = askBlockedReason, company != nil {
                HStack(spacing: 8) {
                    Image(systemName: "lock.fill").foregroundStyle(.secondary)
                    Text(blocked).font(.dsCaption).foregroundStyle(.secondary)
                    Spacer()
                    if !store.canRunTasks {
                        Button("Sign In…") { store.showLoginSheet = true }
                            .controlSize(.small)
                    }
                }
            }

            if store.copilotContext.isSpecific, let chip = store.copilotContext.chipLabel {
                contextChip(chip)
            }

            MacWarrenAttachmentStrip()

            if store.copilotViewingThread != nil {
                MacWarrenViewingBar()
            } else {
            HStack(alignment: .bottom, spacing: 10) {
                MacWarrenAttachButton()
                    .padding(.bottom, 3)

                TextField(placeholder, text: $inputPrompt, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .lineLimit(1...8)
                    .focused($isInputFocused)
                    .onSubmit(submitPrompt)
                    .padding(.vertical, 3)

                if store.copilotStreaming {
                    Button {
                        store.cancelCopilot()
                    } label: {
                        Image(systemName: "stop.circle.fill").font(.system(size: 22))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.primary)
                    .help("Stop the answer")
                } else {
                    Button(action: submitPrompt) {
                        Image(systemName: "arrow.up.circle.fill").font(.system(size: 22))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(canSend ? Color.accentColor : Color.secondary.opacity(0.5))
                    .disabled(!canSend)
                    .keyboardShortcut(.return, modifiers: .command)
                    .help(askBlockedReason ?? "Send (Return)")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.dsCard, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(isInputFocused || fileDropTargeted ? Color.accentColor.opacity(0.5) : Color.dsHairline,
                            lineWidth: fileDropTargeted ? 2 : 1)
            )
            }

            HStack(spacing: 6) {
                Text("Return to send · ⌥Return for a new line")
                Spacer()
                if store.copilotDeepMode {
                    Image(systemName: "brain")
                    Text("Deep answer · runs in the background, progress in Jobs")
                } else {
                    Image(systemName: "bolt")
                    Text("Quick answer")
                }
            }
            .font(.dsCaption)
            .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: 780)
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 24)
        .padding(.top, 10)
        .padding(.bottom, 14)
        .background(.bar)
        .overlay(alignment: .top) { Divider() }
        .modifier(MacWarrenFileDrop(targeted: $fileDropTargeted))
    }

    private func contextChip(_ chip: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "scope").font(.caption)
            Text("About: \(chip)").font(.dsCaption.weight(.medium)).lineLimit(1)
            if let prov = store.visibleCopilotContextInfo?.provenance, !prov.sources.isEmpty || !prov.contradictions.isEmpty {
                Text("· \(prov.sources.count) source\(prov.sources.count == 1 ? "" : "s")"
                     + (prov.contradictions.isEmpty ? "" : ", \(prov.contradictions.count) contradicted"))
                    .font(.dsCaption)
                    .foregroundStyle(prov.contradictions.isEmpty ? Color.secondary : Color.red)
                    .help((prov.sources + prov.contradictions)
                        .compactMap { $0.filename ?? $0.locator }
                        .joined(separator: "\n"))
            }
            Button {
                store.clearCopilotContext()
            } label: {
                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Ask without this context")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.accentColor.opacity(0.12), in: Capsule())
    }

    // MARK: - State

    private var placeholder: String {
        guard let company else { return "Pick a company to start…" }
        return "Ask \(persona.shortName) about \(company.ticker ?? company.title)…"
    }

    /// Why asking is unavailable right now, in words the user can act on.
    private var askBlockedReason: String? {
        if !store.canRunTasks { return "Your current sign-in can't ask questions. Sign in with an analyst or partner account." }
        if company == nil { return "Pick a company first." }
        return nil
    }

    private var canAsk: Bool { askBlockedReason == nil && !store.copilotStreaming }

    private var canSend: Bool {
        canAsk && !store.copilotAttachmentsStaging
            && !inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func submitPrompt() {
        let p = inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canSend else { return }
        inputPrompt = ""
        store.sendCopilotMessage(prompt: p)
    }
}

// MARK: - Suggestion row

private struct SuggestionRow: View {
    let text: String
    let icon: String
    let action: () -> Void
    @State private var hovering = false
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 16)
                Text(text)
                    .font(.dsBody)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 8)
                Image(systemName: "arrow.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .opacity(hovering ? 1 : 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(hovering && isEnabled ? Color.primary.opacity(0.06) : Color.dsCard,
                        in: RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(Color.dsHairline, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.55)
        .onHover { hovering = $0 }
    }
}

// MARK: - Bubble View

struct CopilotBubbleView: View {
    let message: MacCopilotMessage
    var isLatestAnswer = false
    var activity: String?
    var deepMode = false
    var onRetry: (() -> Void)?
    /// An earlier thread: no editing, no offers to act on.
    var readOnly = false

    @State private var hovering = false
    @State private var copied = false

    var body: some View {
        if message.role == .user {
            userBubble
        } else {
            assistantRow
        }
    }

    private var userBubble: some View {
        MacWarrenQuestionBubble(message: message, readOnly: readOnly)
    }

    private var assistantRow: some View {
        let persona = message.persona ?? .warren
        return HStack(alignment: .top, spacing: 12) {
            Image(systemName: persona.icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 28, height: 28)
                .background(Color.accentColor, in: Circle())

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text(persona.displayName).font(.dsSubhead)
                    Text(message.date.formatted(date: .omitted, time: .shortened))
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                }

                if message.text.isEmpty {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text(activity ?? (deepMode ? "Reading the research files… this can take a few minutes" : "Thinking…"))
                            .font(.dsBody)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                } else if message.isError {
                    VStack(alignment: .leading, spacing: 8) {
                        Label {
                            Text(message.text).font(.dsBody).fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Color.dsWarning)
                        }
                        .textSelection(.enabled)
                        if isLatestAnswer, let onRetry {
                            Button("Try Again", action: onRetry).controlSize(.small)
                        }
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.dsWarning.opacity(0.08), in: RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
                } else {
                    let parsed = MacCopilotStructured.parse(message.text)
                    MacMarkdownText(text: parsed.body)
                        .textSelection(.enabled)

                    if isLatestAnswer, !readOnly, let work = parsed.work {
                        MacWarrenWorkCard(work: work)
                    }

                    HStack(spacing: 12) {
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(parsed.body, forType: .string)
                            copied = true
                            Task { try? await Task.sleep(for: .seconds(1.5)); copied = false }
                        } label: {
                            Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                        }
                        if isLatestAnswer, let onRetry {
                            Button(action: onRetry) {
                                Label("Ask again", systemImage: "arrow.clockwise")
                            }
                        }
                    }
                    .buttonStyle(.borderless)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .opacity(hovering || isLatestAnswer ? 1 : 0)
                }
            }
            Spacer(minLength: 40)
        }
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
    }
}

// MARK: - Markdown

/// Renders the block-level markdown the assistant writes (headings, bullets, numbered lists,
/// code fences, paragraphs); inline emphasis and links go through `AttributedString`.
struct MacMarkdownText: View {
    let text: String

    private enum Block: Hashable {
        case heading(String, Int)
        case bullet(String, Int)
        case numbered(String, String)
        case code(String)
        case paragraph(String)
        case rule
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(Self.blocks(text).enumerated()), id: \.offset) { _, block in
                view(for: block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func view(for block: Block) -> some View {
        switch block {
        case .heading(let s, let level):
            Text(Self.inline(s))
                .font(level <= 1 ? .system(size: 17, weight: .bold) : (level == 2 ? .system(size: 15, weight: .semibold) : .system(size: 14, weight: .semibold)))
                .padding(.top, 4)
        case .bullet(let s, let depth):
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(depth == 0 ? "•" : "◦").foregroundStyle(.secondary)
                Text(Self.inline(s)).fixedSize(horizontal: false, vertical: true)
            }
            .font(.system(size: 14))
            .lineSpacing(3)
            .padding(.leading, CGFloat(depth) * 16)
        case .numbered(let n, let s):
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(n + ".").foregroundStyle(.secondary).monospacedDigit()
                Text(Self.inline(s)).fixedSize(horizontal: false, vertical: true)
            }
            .font(.system(size: 14))
            .lineSpacing(3)
        case .code(let s):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(s).font(.system(size: 12, design: .monospaced)).padding(10)
            }
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        case .paragraph(let s):
            Text(Self.inline(s))
                .font(.system(size: 14))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
        case .rule:
            Divider()
        }
    }

    private static func inline(_ s: String) -> AttributedString {
        (try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(s)
    }

    private static func blocks(_ text: String) -> [Block] {
        var out: [Block] = []
        var paragraph: [String] = []
        var code: [String]?

        func flush() {
            if !paragraph.isEmpty { out.append(.paragraph(paragraph.joined(separator: "\n"))) }
            paragraph = []
        }

        for raw in text.components(separatedBy: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if let c = code { out.append(.code(c.joined(separator: "\n"))); code = nil } else { flush(); code = [] }
                continue
            }
            if code != nil { code?.append(raw); continue }
            if line.isEmpty { flush(); continue }
            if line == "---" || line == "***" { flush(); out.append(.rule); continue }
            if line.hasPrefix("#") {
                let level = line.prefix(while: { $0 == "#" }).count
                let title = line.dropFirst(level).trimmingCharacters(in: .whitespaces)
                if level <= 6, !title.isEmpty { flush(); out.append(.heading(title, level)); continue }
            }
            if let marker = ["- ", "* ", "• "].first(where: { line.hasPrefix($0) }) {
                flush()
                let indent = raw.prefix(while: { $0 == " " }).count
                out.append(.bullet(String(line.dropFirst(marker.count)), min(indent / 2, 3)))
                continue
            }
            let digits = line.prefix(while: \.isNumber)
            if !digits.isEmpty, line.dropFirst(digits.count).hasPrefix(". ") {
                flush()
                out.append(.numbered(String(digits), String(line.dropFirst(digits.count + 2))))
                continue
            }
            paragraph.append(line)
        }
        if let c = code { out.append(.code(c.joined(separator: "\n"))) }
        flush()
        return out
    }
}

// MARK: - Warren: pieces the desk and the side panel share

/// The files Warren reads: images and PDFs by eye, everything else as text the server
/// pulls out when the file is staged. Kept in step with the web's
/// `ATTACHMENT_ALLOWED_EXT` (frontend/src/console.js).
enum MacWarrenFiles {
    static let extensions: [String] = [
        "png", "jpg", "jpeg", "gif", "webp",
        "pdf", "doc", "docx", "xlsx", "pptx", "rtf",
        "txt", "log", "md", "markdown", "csv", "tsv",
        "json", "yaml", "yml", "html", "htm",
    ]

    static func accepts(_ url: URL) -> Bool {
        extensions.contains(url.pathExtension.lowercased())
    }

    static func pick() -> [URL] {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = extensions.compactMap { UTType(filenameExtension: $0) }
        panel.message = "Attach documents, spreadsheets, decks or images for Warren to read"
        return panel.runModal() == .OK ? panel.urls : []
    }
}

/// Drop files anywhere on a composer to attach them.
struct MacWarrenFileDrop: ViewModifier {
    @EnvironmentObject private var store: MacAppStore
    @Binding var targeted: Bool

    func body(content: Content) -> some View {
        content.onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
            for provider in providers {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                    var url: URL?
                    if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
                    if let direct = item as? URL { url = direct }
                    guard let url, MacWarrenFiles.accepts(url) else { return }
                    DispatchQueue.main.async { store.stageCopilotAttachments([url]) }
                }
            }
            return true
        }
    }
}

struct MacWarrenAttachButton: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        Button {
            store.stageCopilotAttachments(MacWarrenFiles.pick())
        } label: {
            Image(systemName: "paperclip")
                .font(.system(size: 15))
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
        .help("Attach a document, spreadsheet, deck or image (or drop it here)")
        .disabled(store.copilotStreaming || !store.canRunTasks || store.selectedCompany == nil)
    }
}

/// The files picked for the next question: uploading, ready, or refused with the
/// server's reason — refused here, while the analyst can still do something about it.
struct MacWarrenAttachmentStrip: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        if !store.copilotAttachments.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(store.copilotAttachments) { item in
                            chip(item)
                        }
                    }
                }
                ForEach(store.copilotAttachments) { item in
                    if case .failed(let reason) = item.state {
                        Text("\(item.name): \(reason)")
                            .font(.dsCaption)
                            .foregroundStyle(Color.dsWarning)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    private func chip(_ item: MacStagedAttachment) -> some View {
        HStack(spacing: 4) {
            switch item.state {
            case .staging:
                ProgressView().controlSize(.mini)
            case .ready:
                Image(systemName: "paperclip").font(.caption2)
            case .failed:
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundStyle(Color.dsWarning)
            }
            Text(item.name)
                .font(.caption)
                .lineLimit(1)
                .truncationMode(.middle)
            Button {
                store.removeCopilotAttachment(item.id)
            } label: {
                Image(systemName: "xmark.circle.fill").font(.caption2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Remove this file")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Color.secondary.opacity(0.12), in: Capsule())
        .frame(maxWidth: 240)
    }
}

/// A question in the thread: signed when someone else asked it, marked when it has
/// been rewritten, and editable in place — the edit re-asks it for everyone.
struct MacWarrenQuestionBubble: View {
    @EnvironmentObject private var store: MacAppStore
    let message: MacCopilotMessage
    var readOnly = false
    var compact = false

    @State private var editing = false
    @State private var draft = ""
    @State private var hovering = false
    @FocusState private var focused: Bool

    private var canEdit: Bool {
        !readOnly && message.turnId != nil && !store.copilotStreaming
    }

    private var byline: String {
        [message.author, message.edited ? "edited" : nil]
            .compactMap { $0 }
            .joined(separator: " · ")
    }

    var body: some View {
        HStack {
            Spacer(minLength: compact ? 48 : 80)
            VStack(alignment: .trailing, spacing: 4) {
                if let ctx = message.contextLabel {
                    Label(ctx, systemImage: "scope")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if editing {
                    editor
                } else {
                    bubble
                }
                if !editing, !byline.isEmpty || canEdit {
                    HStack(spacing: 8) {
                        if !byline.isEmpty {
                            Text(byline)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        if canEdit {
                            Button {
                                startEditing()
                            } label: {
                                Label("Edit", systemImage: "pencil")
                            }
                            .buttonStyle(.borderless)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .opacity(hovering ? 1 : 0)
                            .help("Rewrite this question and ask it again")
                        }
                    }
                }
            }
        }
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
    }

    private var bubble: some View {
        VStack(alignment: .trailing, spacing: 6) {
            Text(message.text)
                .font(.system(size: compact ? 13 : 14))
                .textSelection(.enabled)
            if !message.files.isEmpty {
                HStack(spacing: 4) {
                    ForEach(message.files, id: \.self) { name in
                        Label(name, systemImage: "paperclip")
                            .font(.caption2)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 2)
                            .background(Color.primary.opacity(0.07), in: Capsule())
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.accentColor.opacity(0.14),
                    in: RoundedRectangle(cornerRadius: compact ? 12 : 14, style: .continuous))
        .contextMenu {
            if canEdit {
                Button("Edit Question") { startEditing() }
            }
            Button("Copy") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(message.text, forType: .string)
            }
        }
    }

    private var editor: some View {
        VStack(alignment: .trailing, spacing: 6) {
            TextField("Question", text: $draft, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .lineLimit(1...8)
                .focused($focused)
                .onSubmit(save)
                .onExitCommand { editing = false }
                .padding(8)
                .background(Color.dsCard, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            HStack(spacing: 8) {
                Button("Cancel") { editing = false }
                Button("Save & Ask", action: save)
                    .buttonStyle(.borderedProminent)
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .controlSize(.small)
        }
        .padding(8)
        .frame(maxWidth: 520)
        .background(Color.accentColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func startEditing() {
        draft = message.text
        editing = true
        DispatchQueue.main.async { focused = true }
    }

    private func save() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        editing = false
        guard !text.isEmpty, text != message.text else { return }
        store.editCopilotQuestion(message, to: text)
    }
}

/// Work Warren offered to start, under his latest answer. He proposes; nothing runs
/// until the analyst presses the button.
struct MacWarrenWorkCard: View {
    @EnvironmentObject private var store: MacAppStore
    let work: MacCopilotWork

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "play.circle.fill")
                    .foregroundStyle(Color.accentColor)
                VStack(alignment: .leading, spacing: 3) {
                    Text(work.title)
                        .font(.system(size: 13, weight: .semibold))
                    if !work.why.isEmpty {
                        Text(work.why)
                            .font(.dsCaption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let detail = work.detailLine {
                        Text(detail)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            if let note = store.copilotWorkNote {
                Label(note, systemImage: "checkmark.circle.fill")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            } else {
                if let problem = store.copilotWorkError {
                    Text(problem)
                        .font(.dsCaption)
                        .foregroundStyle(Color.dsWarning)
                }
                HStack(spacing: 8) {
                    Button {
                        Task { await store.confirmCopilotWork(work) }
                    } label: {
                        HStack(spacing: 4) {
                            if store.copilotWorkRunning { ProgressView().controlSize(.mini) }
                            Text(work.confirmLabel)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(store.copilotWorkRunning || !store.canRunTasks)
                    if work.kind == .report, let company = store.selectedCompany {
                        Button("Set Options…") { store.requestNewReport(for: company) }
                            .help("Open the report customizer on this company")
                    }
                }
                .controlSize(.small)
            }
        }
        .padding(10)
        .frame(maxWidth: 520, alignment: .leading)
        .background(Color.dsCard, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Color.accentColor.opacity(0.35), lineWidth: 1)
        )
    }
}

/// Starts a new thread for everyone and files this one in the history.
struct MacWarrenNewChatButton: View {
    @EnvironmentObject private var store: MacAppStore
    var iconOnly = false
    var onStart: () -> Void = {}

    var body: some View {
        Button {
            onStart()
            Task { await store.newCopilotThread() }
        } label: {
            if iconOnly {
                Image(systemName: "square.and.pencil").font(.caption)
            } else {
                Label("New Chat", systemImage: "square.and.pencil")
            }
        }
        .disabled(store.copilotStreaming
                  || (store.copilotMessages.isEmpty && store.copilotSessionId == nil))
        .help("File this thread in the history and start a new one — for everyone on this company")
    }
}

/// Warren's earlier threads on this company, shared with the team.
struct MacWarrenThreadsButton: View {
    @EnvironmentObject private var store: MacAppStore
    var iconOnly = false
    @State private var showing = false

    var body: some View {
        Button {
            showing.toggle()
            if showing { Task { await store.refreshCopilotThreads() } }
        } label: {
            if iconOnly {
                Image(systemName: "clock.arrow.circlepath").font(.caption)
            } else {
                Label("Earlier Threads", systemImage: "clock.arrow.circlepath")
            }
        }
        .help("Warren's earlier threads on this company, shared with the team")
        .disabled(store.selectedCompany == nil)
        .popover(isPresented: $showing, arrowEdge: .bottom) {
            list
                .frame(width: 340)
                .padding(12)
        }
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Earlier threads").font(.headline)
            Text("Warren's threads are shared with everyone on this company.")
                .font(.dsCaption)
                .foregroundStyle(.secondary)
            if store.copilotThreadsLoading && store.copilotThreads.isEmpty {
                ProgressView().controlSize(.small)
            } else if store.copilotThreads.isEmpty {
                Text("No earlier threads yet.")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(spacing: 2) {
                        ForEach(store.copilotThreads) { thread in
                            row(thread)
                        }
                    }
                }
                .frame(maxHeight: 360)
            }
        }
    }

    private func row(_ thread: MacCopilotThread) -> some View {
        Button {
            showing = false
            Task { await store.openCopilotThread(thread) }
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(thread.openingQuestion.isEmpty ? "Nothing asked yet" : thread.openingQuestion)
                        .font(.system(size: 13))
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text(when(thread))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                HStack(spacing: 4) {
                    if thread.active {
                        Text("Current").foregroundStyle(Color.accentColor)
                    }
                    Text("\(thread.questionCount) question\(thread.questionCount == 1 ? "" : "s")")
                    if !thread.askers.isEmpty {
                        Text("· " + thread.askers.joined(separator: ", ")).lineLimit(1)
                    }
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(thread.active ? Color.accentColor.opacity(0.08) : Color.clear,
                        in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func when(_ thread: MacCopilotThread) -> String {
        guard let date = MacTimeFormat.parse(thread.lastAt ?? thread.startedAt) else { return "" }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }
}

/// Shown in place of the composer while an earlier thread is open.
struct MacWarrenViewingBar: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        if let thread = store.copilotViewingThread {
            HStack(spacing: 8) {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundStyle(.secondary)
                Text("Reading an earlier thread"
                     + (thread.askers.isEmpty ? "" : " · " + thread.askers.joined(separator: ", ")))
                    .lineLimit(1)
                Spacer(minLength: 8)
                Button("Back to the Current Thread") { store.backToCurrentCopilotThread() }
                    .controlSize(.small)
            }
            .font(.dsCaption)
            .padding(10)
            .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }
}
