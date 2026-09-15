import SwiftUI

/// Ask Warren: one chat about one company, seen through one lens. Everything the user can
/// change (company, lens, answer depth, saved sessions) lives in a single header row; the
/// on-screen context rides above the input like an attachment.
struct MacCopilotView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var inputPrompt = ""
    @State private var showSessions = false
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

                Button {
                    store.clearCopilot()
                    inputPrompt = ""
                    isInputFocused = true
                } label: {
                    Label("New Chat", systemImage: "square.and.pencil")
                }
                .disabled(store.copilotMessages.isEmpty)
                .help("Start a new conversation")
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

            HStack(alignment: .bottom, spacing: 10) {
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
                    .stroke(isInputFocused ? Color.accentColor.opacity(0.5) : Color.dsHairline, lineWidth: 1)
            )

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
        canAsk && !inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
        HStack {
            Spacer(minLength: 80)
            VStack(alignment: .trailing, spacing: 4) {
                if let ctx = message.contextLabel {
                    Label(ctx, systemImage: "scope")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text(message.text)
                    .font(.system(size: 14))
                    .textSelection(.enabled)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.accentColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
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
                    MacMarkdownText(text: message.text)
                        .textSelection(.enabled)

                    HStack(spacing: 12) {
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(message.text, forType: .string)
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
