import SwiftUI
import UIKit

@MainActor
final class CopilotSheetViewModel: ObservableObject {
    let companyId: String
    let companyName: String?
    let surface: String
    let reportId: String?

    @Published var contextLabel: String?
    @Published var messages: [CopilotMessage] = []
    @Published var suggestions: [String] = []
    @Published var draft = ""
    @Published var streaming = false
    @Published var pendingText = ""
    @Published var loadingContext = false
    @Published var error: String?
    @Published var history: [AskHistoryEntry] = []

    private var contextBody = CopilotContextBody()
    private var streamTask: Task<Void, Never>?
    private var lastUserPrompt: String?

    init(companyId: String, companyName: String?, surface: String, reportId: String? = nil) {
        self.companyId = companyId
        self.companyName = companyName
        self.surface = surface
        self.reportId = reportId
        self.contextBody.surface = surface
        self.contextBody.tab = "ask"
        if let reportId, !reportId.isEmpty {
            contextBody.selection = [
                "kind": .string("memo_report"),
                "report_id": .string(reportId),
            ]
            contextBody.attention = [
                "report_id": .string(reportId),
            ]
        }
    }

    func applyInitialPrompt(_ prompt: String?) {
        guard let prompt, !prompt.isEmpty, draft.isEmpty, messages.isEmpty else { return }
        draft = prompt
    }

    deinit {
        streamTask?.cancel()
    }

    func loadContext(language: AppLanguage) async {
        loadingContext = true
        error = nil
        defer { loadingContext = false }
        history = AskHistoryStore.load(companyId: companyId)
        do {
            contextBody.surface = surface
            let res: CopilotContextResponse = try await APIClient.shared.post(
                "companies/\(companyId)/copilot/context",
                body: contextBody
            )
            contextLabel = res.label
            if let auto = res.autoPrompt, !auto.isEmpty, messages.isEmpty {
                draft = auto
            }
            suggestions = Self.buildSuggestions(from: res, language: language)
        } catch {
            // Context is optional — Ask still works without it.
            suggestions = Self.defaultSuggestions(language: language)
        }
    }

    func reopen(_ entry: AskHistoryEntry) {
        messages = [
            CopilotMessage(id: UUID().uuidString, role: .user, text: entry.prompt),
            CopilotMessage(
                id: UUID().uuidString,
                role: .assistant,
                text: entry.answer,
                sources: entry.sources
            ),
        ]
        error = nil
    }

    func send(language: AppLanguage) async {
        let prompt = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !streaming else { return }
        draft = ""
        error = nil
        lastUserPrompt = prompt
        messages.append(CopilotMessage(id: UUID().uuidString, role: .user, text: prompt))
        streaming = true
        pendingText = ""
        streamTask?.cancel()
        streamTask = Task { await self.runAsk(prompt: prompt, language: language.rawValue) }
        await streamTask?.value
    }

    func useSuggestion(_ text: String) {
        guard !streaming else { return }
        draft = text
    }

    private func runAsk(prompt: String, language: String) async {
        defer {
            streaming = false
            pendingText = ""
        }
        do {
            let body = CopilotAskBody(
                prompt: prompt,
                context: contextBody,
                outputLanguage: language,
                mode: "quick"
            )
            let res: CopilotAskResponse = try await APIClient.shared.post(
                "companies/\(companyId)/copilot/ask",
                body: body,
                timeout: 60
            )
            guard let streamPath = res.streamUrl, !streamPath.isEmpty else {
                error = "No stream from Co-Pilot"
                return
            }
            // Do not wait on hydrate — web opens the ask stream immediately.
            // Hydrate (when present) runs in the background for later turns.
            if let hydrate = res.hydrateStreamUrl, !hydrate.isEmpty {
                Task { await self.drainHydrate(path: hydrate) }
            }
            let client = SSEClient()
            var assembled = ""
            for try await event in await client.stream(path: streamPath) {
                if Task.isCancelled { break }
                // Named SSE errors: `event: error` + `data: {"error":"..."}`
                if event.event == "error" {
                    if let data = event.data.data(using: .utf8),
                       let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        error = (obj["error"] as? String) ?? "Ask failed"
                    } else {
                        error = event.data.isEmpty ? "Ask failed" : event.data
                    }
                    break
                }
                guard let data = event.data.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }
                let type = (obj["type"] as? String) ?? ""
                if type == "claude_action" {
                    let action = (obj["action"] as? String) ?? ""
                    if action == "thinking", let chunk = obj["text"] as? String, !chunk.isEmpty {
                        assembled += chunk
                        pendingText = assembled
                    } else if action == "tool_use", assembled.isEmpty {
                        pendingText = "Looking it up…"
                    }
                } else if type == "delta" || type == "text" {
                    if let chunk = obj["text"] as? String {
                        assembled += chunk
                        pendingText = assembled
                    }
                } else if type == "stage" {
                    if let message = obj["message"] as? String, assembled.isEmpty {
                        pendingText = message
                    }
                } else if type == "job_init" {
                    if assembled.isEmpty {
                        let status = (obj["status"] as? String) ?? ""
                        pendingText = status == "queued" ? "Queued…" : "Starting…"
                    }
                } else if type == "done" {
                    if let final = obj["text"] as? String, !final.isEmpty {
                        assembled = final
                        pendingText = final
                    }
                    break
                } else if type == "error" || type == "cancelled" {
                    error = (obj["error"] as? String)
                        ?? (obj["message"] as? String)
                        ?? "Ask failed"
                    break
                }
            }
            let finalText = assembled.trimmingCharacters(in: .whitespacesAndNewlines)
            if !finalText.isEmpty {
                appendAssistant(finalText)
            } else if error == nil, let sessionId = res.sessionId {
                // Fallback: pull the finished assistant turn if stream chunks were missed.
                if let text = await fetchLatestAssistantTurn(
                    sessionId: sessionId,
                    afterTurnId: res.turnId
                ) {
                    appendAssistant(text)
                } else {
                    error = "No reply came back — try again."
                }
            }
        } catch {
            if !Task.isCancelled {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    private func fetchLatestAssistantTurn(sessionId: String, afterTurnId: String?) async -> String? {
        struct TurnRow: Decodable {
            let id: String?
            let role: String?
            let text: String?
        }
        do {
            let turns: [TurnRow] = try await APIClient.shared.get(
                "companies/\(companyId)/console/sessions/\(sessionId)/turns"
            )
            if let afterTurnId,
               let idx = turns.firstIndex(where: { $0.id == afterTurnId }),
               idx + 1 < turns.count {
                let following = turns[(idx + 1)...]
                if let assistant = following.first(where: { ($0.role ?? "") == "assistant" }),
                   let text = assistant.text?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !text.isEmpty {
                    return text
                }
            }
            return turns.last(where: { ($0.role ?? "") == "assistant" })?
                .text?
                .trimmingCharacters(in: .whitespacesAndNewlines)
        } catch {
            return nil
        }
    }

    private func appendAssistant(_ text: String) {
        let cleaned = AskAnswerFormatter.clean(text)
        let sources = AskHistoryStore.extractSources(from: cleaned)
        messages.append(
            CopilotMessage(
                id: UUID().uuidString,
                role: .assistant,
                text: cleaned,
                sources: sources
            )
        )
        if let prompt = lastUserPrompt {
            AskHistoryStore.append(
                AskHistoryEntry(
                    id: UUID().uuidString,
                    companyId: companyId,
                    companyName: companyName,
                    prompt: prompt,
                    answer: cleaned,
                    sources: sources,
                    createdAt: ISO8601DateFormatter().string(from: Date())
                )
            )
            history = AskHistoryStore.load(companyId: companyId)
        }
    }

    private func drainHydrate(path: String) async {
        do {
            let client = SSEClient()
            for try await event in await client.stream(path: path) {
                if Task.isCancelled { break }
                guard let data = event.data.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }
                let type = (obj["type"] as? String) ?? ""
                if type == "done" || type == "error" { break }
                if let message = obj["message"] as? String, pendingText.isEmpty {
                    pendingText = message
                }
            }
        } catch {
            // Hydration is best-effort; ask stream still proceeds.
        }
    }

    private static func buildSuggestions(from res: CopilotContextResponse, language: AppLanguage) -> [String] {
        var out = defaultSuggestions(language: language)
        if let auto = res.autoPrompt, !auto.isEmpty {
            out.insert(auto, at: 0)
        }
        // Deduplicate while preserving order
        var seen = Set<String>()
        return out.filter { seen.insert($0).inserted }.prefix(4).map { $0 }
    }

    private static func defaultSuggestions(language: AppLanguage) -> [String] {
        switch language {
        case .zh:
            return [
                "现在最重要的是什么？",
                "总结多空双方观点",
                "最大的风险在哪里？",
                "接下来该深入研究什么？",
            ]
        case .hi:
            return [
                "अभी सबसे ज़रूरी क्या है?",
                "तेज़ी और मंदी दोनों पक्षों का सारांश दें",
                "सबसे बड़े जोखिम कहाँ हैं?",
                "अगला क्या गहराई से देखूँ?",
            ]
        case .es:
            return [
                "¿Qué importa más ahora mismo?",
                "Resume el caso alcista y bajista",
                "¿Dónde están los mayores riesgos?",
                "¿En qué debería profundizar después?",
            ]
        case .fr:
            return [
                "Qu’est-ce qui compte le plus maintenant ?",
                "Résumez le scénario haussier et baissier",
                "Où sont les plus grands risques ?",
                "Que dois-je approfondir ensuite ?",
            ]
        case .ar:
            return [
                "ما الأهم الآن؟",
                "لخّص وجهة النظر الصاعدة والهابطة",
                "أين أكبر المخاطر؟",
                "ما الذي يجب أن أتعمق فيه بعد ذلك؟",
            ]
        case .bn:
            return [
                "এখন সবচেয়ে গুরুত্বপূর্ণ কী?",
                "বুল ও বেয়ার কেস সংক্ষেপে বলুন",
                "সবচেয়ে বড় ঝুঁকি কোথায়?",
                "এরপর কী গভীরে দেখব?",
            ]
        case .pt:
            return [
                "O que mais importa neste momento?",
                "Resuma o cenário de alta e de baixa",
                "Onde estão os maiores riscos?",
                "No que devo aprofundar a seguir?",
            ]
        case .ru:
            return [
                "Что сейчас важнее всего?",
                "Кратко: бычий и медвежий сценарии",
                "Где самые большие риски?",
                "Что изучить дальше?",
            ]
        case .ur:
            return [
                "اب سب سے اہم کیا ہے؟",
                "بُل اور بیئر کیس کا خلاصہ دیں",
                "سب سے بڑے خطرات کہاں ہیں؟",
                "اگلا کیا گہرائی سے دیکھوں؟",
            ]
        case .en:
            return [
                "What matters most right now?",
                "Summarize the bull and bear case",
                "Where are the biggest risks?",
                "What should I dig into next?",
            ]
        }
    }
}

struct CopilotSheet: View {
    let companyId: String
    let companyName: String?
    var surface: String = "ios_company"
    var initialPrompt: String? = nil
    var reportId: String? = nil
    /// When true, presented as an inline inspector (no sheet chrome / environment dismiss).
    var embedded: Bool = false
    var onClose: (() -> Void)? = nil

    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var askPersona: AskPersonaStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: CopilotSheetViewModel
    @StateObject private var voice = VoiceAskController()
    @State private var showHistory = false
    @FocusState private var composerFocused: Bool

    init(
        companyId: String,
        companyName: String?,
        surface: String = "ios_company",
        initialPrompt: String? = nil,
        reportId: String? = nil,
        embedded: Bool = false,
        onClose: (() -> Void)? = nil
    ) {
        self.companyId = companyId
        self.companyName = companyName
        self.surface = surface
        self.initialPrompt = initialPrompt
        self.reportId = reportId
        self.embedded = embedded
        self.onClose = onClose
        _model = StateObject(
            wrappedValue: CopilotSheetViewModel(
                companyId: companyId,
                companyName: companyName,
                surface: surface,
                reportId: reportId
            )
        )
    }

    var body: some View {
        NavigationStack {
            ZStack {
                background
                VStack(spacing: 0) {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 20) {
                                hero
                                if model.messages.isEmpty && !model.streaming {
                                    suggestions
                                    if !model.history.isEmpty {
                                        historyStrip
                                    }
                                }
                                ForEach(model.messages) { message in
                                    messageBubble(message)
                                        .id(message.id)
                                }
                                if model.streaming {
                                    streamingBlock
                                        .id("pending")
                                }
                                if let err = model.error {
                                    Text(err)
                                        .font(.footnote)
                                        .foregroundStyle(.red)
                                        .padding(.horizontal, 4)
                                }
                            }
                            .padding(.horizontal, 20)
                            .padding(.top, 8)
                            .padding(.bottom, 24)
                        }
                        .scrollDismissesKeyboard(.interactively)
                        .onChange(of: model.messages.count) { _, _ in
                            scrollToAnswerTop(proxy)
                        }
                        .onChange(of: model.pendingText) { oldValue, newValue in
                            // Pin the start of the answer once; do not chase the bottom
                            // as tokens stream in.
                            if oldValue.isEmpty && !newValue.isEmpty {
                                scrollToAnswerTop(proxy)
                            }
                        }
                    }
                    composer
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.t("common.done")) { close() }
                        .fontWeight(.semibold)
                        .accessibilityLabel(language.t("common.done"))
                }
                ToolbarItemGroup(placement: .primaryAction) {
                    ShareLink(item: shareTranscript) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .disabled(model.messages.isEmpty)
                    Button { showHistory = true } label: {
                        Image(systemName: "clock")
                    }
                    .accessibilityLabel(language.t("copilot.history"))
                    NavigationLink {
                        ConsoleSessionsView(companyId: companyId)
                    } label: {
                        Image(systemName: "rectangle.and.pencil.and.ellipsis")
                    }
                    .accessibilityLabel(language.t("copilot.open_console"))
                }
            }
            // Embedded inspector: keep a visible nav bar so Done always dismisses
            // back to the full memo (no swipe-only escape hatch).
            .toolbarBackground(embedded ? .visible : .automatic, for: .navigationBar)
            .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
            .sheet(isPresented: $showHistory) {
                NavigationStack {
                    List(model.history) { entry in
                        Button {
                            model.reopen(entry)
                            showHistory = false
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.prompt)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.primary)
                                    .lineLimit(2)
                                Text(entry.answer)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                            }
                        }
                    }
                    .navigationTitle(language.t("copilot.history"))
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button(language.t("common.done")) { showHistory = false }
                        }
                    }
                }
                .bshSheetChrome(allowsMedium: true)
            }
            .onChange(of: voice.transcript) { _, text in
                guard !text.isEmpty else { return }
                model.draft = text
            }
            .onChange(of: voice.isListening) { _, listening in
                // TextField focus can swallow external draft updates on device;
                // drop focus while dictating so transcript always lands.
                if listening {
                    composerFocused = false
                }
            }
            .onDisappear {
                voice.stop()
            }
            .task {
                await model.loadContext(language: language.language)
                model.applyInitialPrompt(initialPrompt)
                composerFocused = true
            }
        }
        .modifier(CopilotSheetChromeModifier(embedded: embedded))
    }

    private func close() {
        if let onClose {
            onClose()
        } else {
            dismiss()
        }
    }

    private var background: some View {
        LinearGradient(
            colors: [
                Color(.systemBackground),
                Color.accentColor.opacity(0.06),
                Color(.systemBackground),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                AskMark(size: 52)
                    .opacity(model.streaming ? 0.85 : 1)
                Text(askPersona.investor.inviteTitle(lang: language.language))
                    .font(.largeTitle.weight(.bold))
                    .tracking(-0.5)
            }
            Text(model.contextLabel ?? companyName ?? companyId)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
            if model.messages.isEmpty {
                Text(language.t("copilot.subtitle"))
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 4)
    }

    private var suggestions: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(model.suggestions, id: \.self) { suggestion in
                Button {
                    model.useSuggestion(suggestion)
                    Task { await model.send(language: language.language) }
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "arrow.up.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.tertiary)
                            .padding(.top, 2)
                        Text(suggestion)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(.ultraThinMaterial)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(Color.primary.opacity(0.06), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
                .disabled(model.streaming)
            }
        }
        .padding(.top, 8)
    }

    private var historyStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.t("copilot.recent"))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(model.history.prefix(3)) { entry in
                Button {
                    model.reopen(entry)
                } label: {
                    Text(entry.prompt)
                        .font(.footnote)
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Color(.tertiarySystemBackground))
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 4)
    }

    private func messageBubble(_ message: CopilotMessage) -> some View {
        HStack(alignment: .bottom, spacing: 0) {
            if message.role == .user { Spacer(minLength: 56) }
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 10) {
                AskAnswerText(text: message.text, isUser: message.role == .user)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(message.role == .user
                                  ? Color.accentColor
                                  : Color(.secondarySystemBackground))
                    )
                if message.role == .assistant, !message.sources.isEmpty {
                    sourceChips(message.sources)
                }
            }
            .frame(maxWidth: 340, alignment: message.role == .user ? .trailing : .leading)
            if message.role == .assistant { Spacer(minLength: 56) }
        }
    }

    private func sourceChips(_ sources: [AskSourceChip]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(sources) { chip in
                    Button {
                        handleSource(chip)
                    } label: {
                        Text(chip.label)
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule(style: .continuous)
                                    .fill(Color(.tertiarySystemFill))
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func handleSource(_ chip: AskSourceChip) {
        if let urlString = chip.url, let url = URL(string: urlString) {
            UIApplication.shared.open(url)
            return
        }
        model.draft = "Open the \(chip.label) and summarize the key points with page references."
        Task { await model.send(language: language.language) }
    }

    private var streamingBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !model.pendingText.isEmpty {
                AskAnswerText(text: AskAnswerFormatter.clean(model.pendingText))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .frame(maxWidth: 340, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(Color(.secondarySystemBackground))
                    )
            }
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text(askPersona.investor.thinkingLabel(lang: language.language))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.leading, 4)
        }
        .padding(.trailing, 56)
    }

    private var composer: some View {
        VStack(spacing: 0) {
            Divider().opacity(0.4)
            if let voiceError = voice.error, !voiceError.isEmpty {
                Text(voiceError)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(Color.red.opacity(0.92), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .accessibilityLabel("Voice error: \(voiceError)")
            }
            HStack(alignment: .bottom, spacing: 10) {
                Button {
                    voice.toggle(locale: language.locale)
                } label: {
                    Image(systemName: voice.isListening ? "mic.fill" : "mic")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(voice.isListening ? Color.red : Color.secondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(language.t("copilot.voice"))
                TextField(language.t("copilot.prompt"), text: $model.draft, axis: .vertical)
                    .lineLimit(1...6)
                    .focused($composerFocused)
                    .disabled(voice.isListening)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .fill(Color(.secondarySystemBackground))
                    )
                Button {
                    voice.stop()
                    Task { await model.send(language: language.language) }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 34))
                        .symbolRenderingMode(.hierarchical)
                        .foregroundStyle(canSend ? Color.accentColor : Color.secondary.opacity(0.45))
                }
                .disabled(!canSend)
                .accessibilityLabel(language.t("copilot.send"))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.bar)
        }
    }

    private var canSend: Bool {
        !model.streaming && !model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var shareTranscript: String {
        let header = companyName ?? companyId
        let body = model.messages.map { msg in
            (msg.role == .user ? "You" : "Ask") + ": " + msg.text
        }.joined(separator: "\n\n")
        return "\(header)\n\n\(body)"
    }

    private func scrollToAnswerTop(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.2)) {
            if model.streaming {
                proxy.scrollTo("pending", anchor: .top)
            } else if let last = model.messages.last {
                // Prefer the start of the latest assistant answer at the top
                // of the viewport (not the end / bottom of the chat).
                proxy.scrollTo(last.id, anchor: .top)
            }
        }
    }
}

/// Compact company-page entry — one clear invitation, not a settings dump.
struct CopilotInviteCard: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var askPersona: AskPersonaStore

    var body: some View {
        HStack(spacing: 14) {
            AskMark(size: 56)
            VStack(alignment: .leading, spacing: 2) {
                Text(askPersona.investor.inviteTitle(lang: language.language))
                    .font(.headline)
                    .foregroundStyle(.primary)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(askPersona.investor.inviteTitle(lang: language.language))
    }
}

private struct CopilotSheetChromeModifier: ViewModifier {
    var embedded: Bool

    func body(content: Content) -> some View {
        if embedded {
            content
        } else {
            content.bshSheetChrome()
        }
    }
}
