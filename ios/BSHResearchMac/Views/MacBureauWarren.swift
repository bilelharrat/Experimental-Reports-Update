//
//  MacBureauWarren.swift
//  BSHResearchMac
//
//  Ask Warren under Bureau, as the website draws its Warren sheet (App.vue's inspector and
//  CopilotPanel.vue): his portrait and "Ask Warren" in serif over "About <company> ⌄", the
//  round buttons for earlier threads, a new chat, widening and closing; a hairline; then,
//  with no company chosen, the companies to pick from, else the Quick answer / Deep research
//  switch, the transcript (or Warren's introduction and what to ask him) and the composer.
//

import AppKit
import SwiftUI

struct MacBureauWarrenPanel: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @AppStorage("bsh.bureau.asideWidth") private var asideWidth = Double(MacBureau.asideDefault)
    @State private var prompt = ""
    @State private var copiedTurnId: String?
    @State private var fileDropTargeted = false
    @FocusState private var composerFocused: Bool

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var company: MacCompany? { store.selectedCompany }
    private var reading: Bool { store.copilotViewingThread != nil }
    private var messages: [MacCopilotMessage] { reading ? store.copilotViewingMessages : store.copilotMessages }
    private var wide: Bool { asideWidth >= Double(MacBureau.asideWide) }

    /// "ZaiNar, Inc." shouldn't end up as "Inc.…", as the website trims it.
    private var companyLabel: String {
        let name = company?.name ?? company?.title ?? ""
        return name.replacingOccurrences(of: #"[.。]\s*$"#, with: "", options: .regularExpression)
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Rectangle().fill(ink.ink(0.08)).frame(height: 1).padding(.horizontal, 16)
            VStack(spacing: 0) {
                if company == nil {
                    chooseCompany
                } else {
                    MacBureauSegmented(
                        [(false, "Quick answer"), (true, "Deep research")],
                        selection: $store.copilotDeepMode,
                        fill: true
                    )
                    .help(store.copilotDeepMode ? "A longer research session with full document access" : "A fast answer from this company’s files and memo")
                    .padding(.bottom, 12)
                    transcript
                    composer
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 12)
        }
        .background(ink.sheet)
        .task(id: store.selectedCompany?.id) { await store.loadCopilotThread(force: true) }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 10) {
            WarrenMarkView(size: 36, isBusy: store.copilotStreaming)
            VStack(alignment: .leading, spacing: 4) {
                Text("Ask Warren")
                    .font(.custom(BSHType.bureauSerif, size: 22))
                    .tracking(-0.22)
                    .foregroundStyle(ink.ink)
                    .frame(height: 26)
                companyPicker
            }
            // The title column takes what the buttons leave; a long company name truncates.
            .frame(maxWidth: .infinity, alignment: .leading)
            .layoutPriority(-1)
            if company != nil && !store.copilotDeepMode {
                MacWarrenThreadsButton(glyph: "history")
                    .buttonStyle(.plain)
                if !store.copilotMessages.isEmpty || store.copilotSessionId != nil {
                    MacWarrenNewChatButton(glyph: "square-pen") {
                        prompt = ""
                        composerFocused = true
                    }
                    .buttonStyle(.plain)
                }
            }
            Button {
                withAnimation(.easeInOut(duration: 0.18)) {
                    asideWidth = wide ? Double(MacBureau.asideDefault) : Double(MacBureau.asideWide)
                }
            } label: {
                MacBureauIconCircle(icon: wide ? "chevrons-right" : "chevrons-left")
            }
            .buttonStyle(.plain)
            .help(wide ? "Narrow Warren" : "Widen Warren")
            Button {
                withAnimation(.easeInOut(duration: 0.18)) { store.showCopilotPanel = false }
            } label: {
                MacBureauIconCircle(icon: "panel-right-close")
            }
            .buttonStyle(.plain)
            .help("Close Warren (⌥⌘C)")
        }
        .padding(.horizontal, 16)
        .padding(.top, 14)
        .padding(.bottom, 12)
    }

    /// "About <company> ⌄": the company Warren is studying.
    private var companyPicker: some View {
        Menu {
            ForEach(store.companies) { item in
                Button {
                    store.selectCompany(item)
                } label: {
                    if item.id == company?.id {
                        Label(item.name ?? item.title, systemImage: "checkmark")
                    } else {
                        Text(item.name ?? item.title)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text("About").foregroundStyle(ink.muted).fixedSize()
                Text(company.map { $0.name ?? $0.title } ?? "Choose a company")
                    .fontWeight(.semibold)
                    .foregroundStyle(company == nil ? ink.accentInk : ink.ink)
                    .lineLimit(1)
                    .truncationMode(.tail)
                LucideIcon("chevron-down", size: 14).foregroundStyle(ink.muted)
            }
            .font(BSHType.bureauSans(12))
            .bureauLines(16, size: 12)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .contentShape(Rectangle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, -6)
    }

    // MARK: No company yet

    private var chooseCompany: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                hero(
                    title: "Ask Warren",
                    body: store.companies.isEmpty
                        ? "Add a company first, then ask Warren about it."
                        : "Warren answers from one company’s memo, filings and notes. Pick one to start.",
                    width: 288
                )
                if !store.companies.isEmpty {
                    MacBureauKicker("Choose a company")
                        .padding(.horizontal, 4)
                        .padding(.top, 20)
                    VStack(spacing: 6) {
                        ForEach(store.companies) { item in
                            MacBureauAskRow(ink: ink) {
                                store.selectCompany(item)
                            } label: {
                                MacAvatar(company: item, size: 24)
                                Text(item.name ?? item.title)
                                    .font(BSHType.bureauSans(13, weight: .medium))
                                    .foregroundStyle(ink.ink)
                                    .lineLimit(1)
                                Spacer(minLength: 4)
                                if let ticker = item.ticker, !ticker.isEmpty {
                                    Text(ticker)
                                        .font(BSHType.bureauSans(11, weight: .medium))
                                        .foregroundStyle(ink.muted)
                                }
                            }
                        }
                    }
                    .padding(.top, 6)
                }
            }
        }
    }

    private func hero(title: String, body: String, width: CGFloat) -> some View {
        VStack(spacing: 0) {
            WarrenMarkView(size: 56, isBusy: store.copilotStreaming)
            Text(title)
                .font(BSHType.bureauSans(15, weight: .semibold))
                .tracking(-0.15)
                .foregroundStyle(ink.ink)
                .multilineTextAlignment(.center)
                .bureauLines(20, size: 15)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 12)
            Text(body)
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .multilineTextAlignment(.center)
                .bureauLines(19.5, size: 12)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: width)
                .padding(.top, 4)
        }
        .padding(.horizontal, 12)
        .padding(.top, 16)
        .frame(maxWidth: .infinity)
    }

    // MARK: Transcript

    private var starters: [String] {
        let label = companyLabel.isEmpty ? "this company" : companyLabel
        return [
            "Does \(label) have a durable moat? What could erode it?",
            "Is management allocating capital well at \(label)?",
            "What is \(label) worth, and is there a margin of safety at today’s price?",
            "Would you own \(label) for ten years? Why or why not?",
        ]
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView(showsIndicators: false) {
                LazyVStack(alignment: .leading, spacing: 20) {
                    if messages.isEmpty {
                        VStack(alignment: .leading, spacing: 0) {
                            hero(
                                title: "Ask Warren about \(companyLabel)",
                                body: "Moat, management, intrinsic value and margin of safety — grounded in this company’s files and memo.",
                                width: 304
                            )
                            MacBureauKicker("Try asking")
                                .padding(.horizontal, 4)
                                .padding(.top, 20)
                            VStack(spacing: 6) {
                                ForEach(starters, id: \.self) { question in
                                    MacBureauAskRow(ink: ink) {
                                        send(question)
                                    } label: {
                                        LucideIcon("message-square-text", size: 14).foregroundStyle(ink.accent)
                                        Text(question)
                                            .font(BSHType.bureauSans(13))
                                            .tracking(-0.039)
                                            .foregroundStyle(ink.ink)
                                            .multilineTextAlignment(.leading)
                                            .bureauLines(18, size: 13)
                                            .fixedSize(horizontal: false, vertical: true)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                    }
                                }
                            }
                            .padding(.top, 6)
                        }
                        .padding(.bottom, 8)
                    } else {
                        ForEach(messages) { message in
                            Group {
                                if message.role == .user {
                                    MacWarrenQuestionBubble(message: message, readOnly: reading, compact: true)
                                } else {
                                    answer(message)
                                }
                            }
                            .id(message.id)
                        }
                        if store.copilotStreaming, !reading {
                            pending.id("pending")
                        }
                    }
                }
                .padding(.vertical, 8)
            }
            .padding(.horizontal, -6)
            .onChange(of: store.copilotMessages.count) { _, _ in scroll(proxy) }
            .onChange(of: store.copilotStreaming) { _, streaming in if streaming { scroll(proxy) } }
        }
        .frame(maxHeight: .infinity)
    }

    private func answer(_ message: MacCopilotMessage) -> some View {
        let parsed = MacCopilotStructured.parse(message.text)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                WarrenMarkView(size: 22, isBusy: false)
                Text("Warren")
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.ink)
                Text(message.date.formatted(date: .omitted, time: .shortened))
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.subtle)
                Spacer()
            }
            VStack(alignment: .leading, spacing: 8) {
                if message.isError {
                    Label(message.text, systemImage: "exclamationmark.triangle.fill")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.warningInk)
                        .textSelection(.enabled)
                } else {
                    MacMarkdownText(text: parsed.body)
                        .textSelection(.enabled)
                }
                if !reading, message.id == store.copilotMessages.last?.id, let work = parsed.work {
                    MacWarrenWorkCard(work: work)
                }
            }
            .padding(.leading, 30)
            HStack(spacing: 12) {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(parsed.body, forType: .string)
                    copiedTurnId = message.id
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                        if copiedTurnId == message.id { copiedTurnId = nil }
                    }
                } label: {
                    Label(copiedTurnId == message.id ? "Copied" : "Copy", systemImage: copiedTurnId == message.id ? "checkmark" : "doc.on.doc")
                }
                Button {
                    store.sendCopilotMessage(prompt: message.text)
                } label: {
                    Label("Ask again", systemImage: "arrow.clockwise")
                }
                Spacer()
            }
            .font(BSHType.bureauSans(11))
            .foregroundStyle(ink.muted)
            .buttonStyle(.plain)
            .padding(.leading, 30)
        }
    }

    private var pending: some View {
        HStack(spacing: 8) {
            WarrenMarkView(size: 22, isBusy: true)
            Text("Warren").font(BSHType.bureauSans(12, weight: .semibold)).foregroundStyle(ink.ink)
            ProgressView().controlSize(.mini)
            Text("Reading the files…").font(BSHType.bureauSans(12)).foregroundStyle(ink.muted)
            Spacer()
        }
    }

    // MARK: Composer

    private var ready: Bool {
        !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !store.copilotStreaming && !store.copilotAttachmentsStaging
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 6) {
            MacWarrenAttachmentStrip()
                .frame(maxWidth: .infinity, alignment: .leading)
            if reading {
                MacWarrenViewingBar()
            } else {
                HStack(alignment: .bottom, spacing: 8) {
                    MacWarrenAttachButton(glyph: "paperclip")
                        .buttonStyle(.plain)
                        .padding(.bottom, 2)
                    TextField(
                        "",
                        text: $prompt,
                        prompt: Text("Ask Warren about \(companyLabel)…").foregroundStyle(ink.subtle),
                        axis: .vertical
                    )
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(13))
                    .tracking(-0.039)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1...6)
                    .focused($composerFocused)
                    .bureauLines(17.55, size: 13)
                    .padding(.vertical, 8)
                    // One row until there's a question (the website's `rows="1"`): a long
                    // placeholder wraps under the field's edge rather than growing the box.
                    .frame(minHeight: 36, maxHeight: prompt.isEmpty ? 36 : nil, alignment: .top)
                    .clipped()
                    .onSubmit { send(prompt) }
                    Button {
                        send(prompt)
                    } label: {
                        LucideIcon("arrow-up", size: 16)
                            .foregroundStyle(ready ? Color.white : ink.subtle)
                            .frame(width: 32, height: 32)
                            .background(Circle().fill(ready ? ink.accent : ink.ink(0.06)))
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(!ready)
                    .padding(.bottom, 2)
                }
                .padding(.leading, 14)
                .padding(.trailing, 6)
                .padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 16, style: .circular).fill(ink.raised))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .circular)
                        .strokeBorder(composerFocused || fileDropTargeted ? ink.accent : ink.ink(0.14), lineWidth: 1)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .circular)
                        .inset(by: -2)
                        .stroke(composerFocused ? ink.accentGlow(0.24) : .clear, lineWidth: 3)
                        .padding(-0.5)
                        .allowsHitTesting(false)
                )
                .shadow(color: ink.shadow(0.35 * 0.4), radius: 6, y: 5)
            }
            Text("Enter to send · Shift+Enter for a new line")
                .font(BSHType.bureauSans(10))
                .tracking(0.12)
                .foregroundStyle(ink.ink(0.36))
                .padding(.horizontal, 4)
        }
        .modifier(MacWarrenFileDrop(targeted: $fileDropTargeted))
        .onAppear { composerFocused = true }
    }

    private func send(_ text: String) {
        let question = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !question.isEmpty, !store.copilotStreaming else { return }
        prompt = ""
        store.sendCopilotMessage(prompt: question)
    }

    private func scroll(_ proxy: ScrollViewProxy) {
        if store.copilotStreaming {
            withAnimation { proxy.scrollTo("pending", anchor: .bottom) }
        } else if let last = store.copilotMessages.last {
            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }
}

/// `.ask-suggestion` under Bureau: a row ruled in ink, fresh paper on hover.
private struct MacBureauAskRow<Label: View>: View {
    let ink: MacBureauPageInk
    let action: () -> Void
    @ViewBuilder let label: () -> Label
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 10) { label() }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(hovered ? ink.raised : .clear))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .circular).strokeBorder(ink.ink(0.14), lineWidth: 1))
                .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}
