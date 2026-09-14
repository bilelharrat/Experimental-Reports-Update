import SwiftUI

struct MacCopilotView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var inputPrompt = ""
    @State private var mode = "quick"
    @FocusState private var isInputFocused: Bool

    private let suggestions = [
        "Evaluate economic moat & durability",
        "Analyze capital allocation & ROIC",
        "Assess balance sheet debt & liquidity",
        "Summarize growth drivers vs headwinds"
    ]

    var body: some View {
        VStack(spacing: 0) {
            modeBar
            Divider()
            if mode == "sessions", let company = store.selectedCompany {
                MacConsoleView(company: company)
            } else {
                quickChat
            }
        }
    }

    private var modeBar: some View {
        HStack(spacing: 12) {
            Picker("", selection: $mode) {
                Label("Quick Ask", systemImage: "bolt").tag("quick")
                Label("Sessions", systemImage: "terminal").tag("sessions")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 220)
            Text(mode == "quick"
                 ? "Context-aware answers about what's on screen."
                 : "Persistent per-company sessions with staged documents and attachments.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private var quickChat: some View {
        VStack(spacing: 0) {
            // Top Toolbar: Persona & Context Selector
            HStack(spacing: 12) {
                // Persona Picker
                Picker("Persona", selection: $store.copilotPersona) {
                    ForEach(MacCopilotPersona.allCases) { p in
                        Label(p.displayName, systemImage: p.icon).tag(p)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 180)

                Divider().frame(height: 18)

                // Context Enterprise Selector
                HStack(spacing: 6) {
                    Text("Target:")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Picker("Target Company", selection: Binding(
                        get: { store.selectedCompany?.id ?? "general" },
                        set: { newId in
                            if let found = store.companies.first(where: { $0.id == newId }) {
                                store.selectCompany(found)
                            }
                        }
                    )) {
                        Text("General Market / Macro").tag("general")
                        ForEach(store.companies) { c in
                            Text(c.ticker != nil ? "\(c.ticker!) · \(c.name ?? c.id)" : (c.name ?? c.id)).tag(c.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: 240)
                }

                Spacer()

                Toggle(isOn: $store.copilotDeepMode) {
                    Label("Deep", systemImage: "brain")
                }
                .toggleStyle(.checkbox)
                .help("Deep mode stages the company's research files and runs as a background job in the blotter")

                if !store.copilotMessages.isEmpty {
                    Button {
                        store.copilotMessages.removeAll()
                    } label: {
                        Label("Clear Chat", systemImage: "trash")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial)

            Divider()

            // Context strip: what's on screen + the server's suggested actions + source chips
            if let chip = store.copilotContext.chipLabel {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Label(chip, systemImage: "scope")
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Color.accentColor.opacity(0.12), in: Capsule())
                        if let label = store.copilotContextInfo?.label, !label.isEmpty {
                            Text(label).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer()
                        Button { store.clearCopilotContext() } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain)
                            .foregroundStyle(.secondary)
                            .help("Drop the on-screen context")
                    }
                    if let actions = store.copilotContextInfo?.actions, !actions.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(actions) { action in
                                    Button(action.label) { store.sendCopilotMessage(prompt: action.prompt) }
                                        .controlSize(.small)
                                        .disabled(store.copilotStreaming || !store.canRunTasks)
                                }
                            }
                        }
                    }
                    if let prov = store.copilotContextInfo?.provenance, !prov.sources.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(prov.sources) { source in
                                    Label(source.filename ?? source.locator ?? "source", systemImage: "doc.text")
                                        .font(.caption2)
                                        .padding(.horizontal, 6).padding(.vertical, 3)
                                        .background(Color.secondary.opacity(0.1), in: Capsule())
                                        .help(source.excerpt ?? "")
                                }
                                ForEach(prov.contradictions) { source in
                                    Label(source.filename ?? "contradiction", systemImage: "exclamationmark.bubble")
                                        .font(.caption2)
                                        .foregroundStyle(Color.red)
                                        .padding(.horizontal, 6).padding(.vertical, 3)
                                        .background(Color.red.opacity(0.1), in: Capsule())
                                        .help(source.excerpt ?? "")
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Color(nsColor: .controlBackgroundColor))
                Divider()
            }

            // Chat Messages Scroll
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 16) {
                        if store.copilotMessages.isEmpty {
                            VStack(spacing: 16) {
                                Image(systemName: store.copilotPersona.icon)
                                    .font(.system(size: 40))
                                    .foregroundStyle(Color.accentColor)
                                    .padding(.top, 40)

                                Text("Ask \(store.copilotPersona.displayName)")
                                    .font(.title2.weight(.bold))

                                Text("Powered by real-time investment reasoning, financial disclosures, and value principles.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .multilineTextAlignment(.center)
                                    .frame(maxWidth: 440)

                                // Quick Prompt Chips
                                VStack(spacing: 8) {
                                    ForEach(suggestions, id: \.self) { s in
                                        Button {
                                            store.sendCopilotMessage(prompt: s)
                                        } label: {
                                            HStack {
                                                Image(systemName: "sparkle")
                                                    .foregroundStyle(Color.accentColor)
                                                Text(s)
                                                    .font(.subheadline)
                                                Spacer()
                                                Image(systemName: "arrow.up.right")
                                                    .font(.caption2)
                                                    .foregroundStyle(.secondary)
                                            }
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 10)
                                            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 8)
                                                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
                                            )
                                        }
                                        .buttonStyle(.plain)
                                        .frame(maxWidth: 440)
                                    }
                                }
                                .padding(.top, 12)
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                        } else {
                            ForEach(store.copilotMessages) { msg in
                                CopilotBubbleView(message: msg)
                                    .id(msg.id)
                            }
                        }
                    }
                    .padding(20)
                }
                .onChange(of: store.copilotMessages.count) { _, _ in
                    if let last = store.copilotMessages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            Divider()

            // Input Bar
            VStack(spacing: 8) {
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Inquire with \(store.copilotPersona.displayName) (Press Return or ⌘Enter to send)…", text: $inputPrompt, axis: .vertical)
                        .textFieldStyle(.plain)
                        .lineLimit(1...6)
                        .focused($isInputFocused)
                        .onSubmit {
                            submitPrompt()
                        }

                    Button {
                        submitPrompt()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                            .foregroundStyle(inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.copilotStreaming ? Color.secondary : Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .disabled(inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.copilotStreaming)
                    .keyboardShortcut(.defaultAction)
                }
                .padding(12)
                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
                )

                HStack {
                    Text("Perspective: \(store.copilotPersona.displayName)\(store.copilotDeepMode ? " · deep" : "")")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer()
                    if store.copilotStreaming {
                        HStack(spacing: 4) {
                            ProgressView().controlSize(.mini)
                            Text(store.copilotCurrentThinking ?? "Thinking…")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(16)
            .background(.ultraThinMaterial)
        }
    }

    private func submitPrompt() {
        let p = inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !p.isEmpty, !store.copilotStreaming else { return }
        inputPrompt = ""
        store.sendCopilotMessage(prompt: p)
    }
}

// MARK: - Bubble View

struct CopilotBubbleView: View {
    let message: MacCopilotMessage

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if message.role == .assistant {
                Image(systemName: "building.columns.circle.fill")
                    .font(.title2)
                    .foregroundStyle(Color.accentColor)
                    .padding(.top, 2)
            } else {
                Spacer()
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 6) {
                if message.role == .user, let ctx = message.contextLabel {
                    Label(ctx, systemImage: "scope")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if message.role == .assistant && message.text.isEmpty {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Thinking…")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(12)
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                } else {
                    Text(message.text)
                        .font(.body)
                        .lineSpacing(4)
                        .textSelection(.enabled)
                        .padding(12)
                        .background(
                            message.role == .user
                                ? Color.accentColor.opacity(0.12)
                                : Color(nsColor: .controlBackgroundColor),
                            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
                        )
                }

                Text(message.date.formatted(date: .omitted, time: .shortened))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if message.role == .user {
                Image(systemName: "person.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.secondary)
                    .padding(.top, 2)
            } else {
                Spacer()
            }
        }
    }
}
