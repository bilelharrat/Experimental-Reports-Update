import SwiftUI
import AppKit

// MARK: - MacCopilotSidePanel (Identical to Web CopilotPanel.vue & App.vue Drawer)

struct MacCopilotSidePanel: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var inputPrompt = ""
    @State private var copiedTurnId: String? = nil
    @FocusState private var isInputFocused: Bool

    private var activeCompany: MacCompany? {
        store.selectedCompany
    }

    private var companyLabel: String {
        if let company = activeCompany {
            return company.ticker ?? company.name ?? company.title
        }
        return "Market & Value"
    }

    private var placeholderText: String {
        if let company = activeCompany {
            let label = company.ticker ?? company.name ?? company.title
            return "Ask Warren about \(label)…"
        }
        return "Ask Warren about a company or moat…"
    }

    private var starters: [String] {
        let label = activeCompany?.ticker ?? activeCompany?.name ?? activeCompany?.title ?? "this company"
        return [
            "Does \(label) have a durable moat? What could erode it?",
            "Is management allocating capital well at \(label)?",
            "What is \(label) worth, and is there a margin of safety at today’s price?",
            "Would you own \(label) for ten years? Why or why not?"
        ]
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header matching CopilotPanel.vue: Warren portrait (size 36) + title + company picker + close
            drawerHeader

            Divider()

            // Segmented mode switcher: Quick vs Deep
            modeSegmentedBar

            Divider()

            // Chat body: Empty Hero or conversation stream
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 16) {
                        if store.copilotMessages.isEmpty {
                            emptyHeroState
                        } else {
                            ForEach(store.copilotMessages) { msg in
                                if msg.role == .user {
                                    userTurnView(msg)
                                        .id(msg.id)
                                } else {
                                    warrenTurnView(msg)
                                        .id(msg.id)
                                }
                            }

                            if store.copilotStreaming {
                                pendingWarrenTurn
                                    .id("pending_stream_turn")
                            }
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 16)
                }
                .onChange(of: store.copilotMessages.count) { _, _ in
                    scrollToBottom(proxy: proxy)
                }
                .onChange(of: store.copilotStreaming) { _, streaming in
                    if streaming {
                        scrollToBottom(proxy: proxy)
                    }
                }
            }

            Divider()

            // Bottom Input Well
            inputWell
        }
        .background(Color(NSColor.windowBackgroundColor))
        .onAppear {
            isInputFocused = true
        }
    }

    // MARK: - Drawer Header

    private var drawerHeader: some View {
        HStack(alignment: .center, spacing: 10) {
            // Warren's 36px portrait identical to <WarrenMark :size="36" />
            WarrenMarkView(size: 36, isBusy: store.copilotStreaming)

            VStack(alignment: .leading, spacing: 1) {
                Text("Ask Warren")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(.primary)

                // Company Picker Dropdown
                Menu {
                    Button {
                        store.selectedCompany = nil
                    } label: {
                        HStack {
                            Text("General Market / Macro")
                            if store.selectedCompany == nil {
                                Image(systemName: "checkmark")
                            }
                        }
                    }

                    if !store.companies.isEmpty {
                        Divider()
                        ForEach(store.companies) { company in
                            Button {
                                store.selectCompany(company)
                            } label: {
                                HStack {
                                    Text(company.ticker != nil ? "\(company.ticker!) · \(company.name ?? company.title)" : (company.name ?? company.title))
                                    if store.selectedCompany?.id == company.id {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(activeCompany != nil ? (activeCompany!.ticker ?? activeCompany!.name ?? activeCompany!.title) : "Choose a company")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(Color.accentColor)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(Color.accentColor)
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 4))
                }
                .buttonStyle(.plain)
            }

            Spacer(minLength: 6)

            // Clear chat button
            if !store.copilotMessages.isEmpty {
                Button {
                    store.copilotMessages.removeAll()
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Clear chat")
            }

            // Close drawer button
            Button {
                withAnimation(.easeInOut(duration: 0.18)) {
                    store.showCopilotPanel = false
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.semibold))
                    .padding(5)
                    .background(Color.primary.opacity(0.06), in: Circle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Close Ask Warren (⌥⌘C)")
            .keyboardShortcut("c", modifiers: [.command, .option])
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
    }

    // MARK: - Mode Segmented Bar

    private var modeSegmentedBar: some View {
        VStack(spacing: 4) {
            Picker("Mode", selection: $store.copilotDeepMode) {
                Text("Quick").tag(false)
                Text("Deep").tag(true)
            }
            .pickerStyle(.segmented)
            .controlSize(.small)

            Text(store.copilotDeepMode
                 ? "A longer research session with full document access"
                 : "A fast answer from this company’s files and memo")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.35))
    }

    // MARK: - Empty Hero State (Matching .warren-hero in CopilotPanel.vue)

    private var emptyHeroState: some View {
        VStack(spacing: 12) {
            // Big 56px Warren portrait
            WarrenMarkView(size: 56, isBusy: store.copilotStreaming)
                .padding(.top, 16)

            Text(activeCompany != nil ? "Ask Warren about \(companyLabel)" : "Ask Warren")
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.primary)

            Text("Moat, management, intrinsic value and margin of safety — grounded in this company’s files and memo.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 12)

            // Suggested Starters: "Try asking"
            VStack(alignment: .leading, spacing: 8) {
                Text("TRY ASKING")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.tertiary)
                    .padding(.leading, 2)
                    .padding(.top, 10)

                ForEach(starters, id: \.self) { prompt in
                    Button {
                        submitPrompt(prompt)
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "text.bubble")
                                .font(.caption2)
                                .foregroundStyle(Color.accentColor)

                            Text(prompt)
                                .font(.caption)
                                .foregroundStyle(.primary)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)

                            Spacer(minLength: 4)

                            Image(systemName: "arrow.up.right")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, 6)
        }
    }

    // MARK: - User Turn View

    private func userTurnView(_ msg: MacCopilotMessage) -> some View {
        HStack {
            Spacer(minLength: 48)
            VStack(alignment: .trailing, spacing: 4) {
                if let ctx = msg.contextLabel {
                    Text(ctx)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                Text(msg.text)
                    .font(.callout)
                    .textSelection(.enabled)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.accentColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    // MARK: - Warren Turn View

    private func warrenTurnView(_ msg: MacCopilotMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: WarrenMark(size: 22) + Warren + Time
            HStack(spacing: 8) {
                WarrenMarkView(size: 22, isBusy: false)

                Text("Warren")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.primary)

                Text(msg.date.formatted(date: .omitted, time: .shortened))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

                Spacer()
            }

            // Body
            VStack(alignment: .leading, spacing: 4) {
                Text(msg.text)
                    .font(.callout)
                    .textSelection(.enabled)
                    .lineSpacing(2)
                    .foregroundStyle(.primary)
            }
            .padding(.leading, 30)

            // Actions row: Copy + Ask again
            HStack(spacing: 12) {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(msg.text, forType: .string)
                    copiedTurnId = msg.id
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                        if copiedTurnId == msg.id { copiedTurnId = nil }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: copiedTurnId == msg.id ? "checkmark" : "doc.on.doc")
                        Text(copiedTurnId == msg.id ? "Copied" : "Copy")
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)

                Button {
                    store.sendCopilotMessage(prompt: msg.text)
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.clockwise")
                        Text("Ask again")
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)

                Spacer()
            }
            .padding(.leading, 30)
            .padding(.top, 2)
        }
    }

    // MARK: - Pending / Streaming Turn (Buffetting…)

    private var pendingWarrenTurn: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                WarrenMarkView(size: 22, isBusy: true)

                Text("Warren")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.primary)

                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.accentColor)
                        .frame(width: 5, height: 5)
                    Text("Buffetting…")
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(Color.accentColor)
                }

                Spacer()
            }

            HStack(spacing: 8) {
                ProgressView().controlSize(.mini)
                Text("Analyzing disclosures and value thesis…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.leading, 30)
            .padding(.vertical, 4)
        }
    }

    // MARK: - Input Well

    private var inputWell: some View {
        VStack(spacing: 6) {
            HStack(alignment: .bottom, spacing: 8) {
                TextField(placeholderText, text: $inputPrompt, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.callout)
                    .lineLimit(1...5)
                    .focused($isInputFocused)
                    .onSubmit {
                        submitCurrentPrompt()
                    }

                Button {
                    submitCurrentPrompt()
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(
                            canSubmit ? Color.accentColor : Color.secondary.opacity(0.35)
                        )
                }
                .buttonStyle(.plain)
                .disabled(!canSubmit)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.primary.opacity(0.12), lineWidth: 1)
            )

            HStack {
                Text("Enter to send · Shift+Enter for newline")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                Spacer()

                Text("Perspective: Warren Buffett")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.5))
    }

    private var canSubmit: Bool {
        !inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !store.copilotStreaming
    }

    private func submitCurrentPrompt() {
        let p = inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !p.isEmpty, !store.copilotStreaming else { return }
        inputPrompt = ""
        store.sendCopilotMessage(prompt: p)
    }

    private func submitPrompt(_ prompt: String) {
        guard !store.copilotStreaming else { return }
        store.sendCopilotMessage(prompt: prompt)
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if store.copilotStreaming {
            withAnimation { proxy.scrollTo("pending_stream_turn", anchor: .bottom) }
        } else if let last = store.copilotMessages.last {
            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }
}
