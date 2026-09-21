import SwiftUI

// MARK: - Firm memory search (⌘⇧F)

struct MacFirmSearchSheet: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var result: MacFirmSearch?
    @State private var kind: String = ""
    @State private var searching = false
    @State private var searchTask: Task<Void, Never>?
    @FocusState private var focused: Bool

    private let kinds = ["", "memo", "decision", "reference_call", "founder_update", "transcript", "comment", "chat", "company"]

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search everything the firm has written: memos, decisions, calls, updates, chat…", text: $query)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($focused)
                    .onChange(of: query) { _, _ in schedule() }
                if searching { ProgressView().controlSize(.small) }
                Button("Close") { dismiss() }.keyboardShortcut(.cancelAction).controlSize(.small)
            }
            .padding(14)
            Divider()
            HStack(spacing: 6) {
                ForEach(kinds, id: \.self) { k in
                    Button {
                        kind = k
                        schedule(immediate: true)
                    } label: {
                        Text(k.isEmpty ? "All" : k.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(kind == k ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.08), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
                if let r = result { Text("\(r.total) hits").font(.caption).foregroundStyle(.secondary) }
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
            Divider()
            if let r = result, !r.items.isEmpty {
                List(r.items) { hit in
                    Button { store.open(hit: hit) } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: hit.systemImage).foregroundStyle(Color.accentColor).frame(width: 18)
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(hit.title).font(.callout.weight(.semibold)).lineLimit(1)
                                    Text(hit.kindLabel).font(.caption2).foregroundStyle(.secondary)
                                        .padding(.horizontal, 5).padding(.vertical, 1).background(Color.secondary.opacity(0.1), in: Capsule())
                                    if let v = hit.verdict { MacStatusPill(text: v.capitalized, color: v == "invest" ? .green : (v == "pass" ? .red : .orange)) }
                                    Spacer()
                                    if let at = hit.at { Text(MacTimeFormat.relative(at)).font(.caption2).foregroundStyle(.tertiary) }
                                }
                                Text(hit.excerpt).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                            }
                        }
                        .padding(.vertical, 3)
                    }
                    .buttonStyle(.plain)
                    .draggable("\(hit.title)\n\(hit.excerpt)")
                }
                .listStyle(.inset)
            } else {
                ContentUnavailableView(
                    query.isEmpty ? "Firm memory" : (searching ? "Searching…" : "No matches"),
                    systemImage: "brain.head.profile",
                    description: Text(query.isEmpty ? "Type to search across memos, decisions, reference calls, founder updates, transcripts, comments and chat." : "Try fewer or different words.")
                )
            }
        }
        .frame(width: 760, height: 560)
        .onAppear { focused = true }
    }

    private func schedule(immediate: Bool = false) {
        searchTask?.cancel()
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else { result = nil; return }
        searchTask = Task {
            if !immediate { try? await Task.sleep(for: .milliseconds(220)) }
            guard !Task.isCancelled else { return }
            searching = true
            let r = try? await MacAPIClient.shared.firmSearch(q, kinds: kind.isEmpty ? [] : [kind])
            if !Task.isCancelled { result = r }
            searching = false
        }
    }
}

// MARK: - Comments with @mentions

struct MacCommentsView: View {
    let companyId: String
    let target: MacCommentTarget
    @EnvironmentObject private var store: MacAppStore
    @State private var draft = ""
    @State private var replyTo: MacComment?
    @State private var showResolved = false
    @State private var posting = false
    @State private var postError: String?

    private var all: [MacComment] { store.commentsByCompany[companyId]?.items ?? [] }
    private var scoped: [MacComment] {
        all.filter { ($0.target?.kind == target.kind && $0.target?.ref == target.ref) || $0.parentId != nil }
    }
    private var roots: [MacComment] { scoped.filter { $0.parentId == nil && (showResolved || !$0.isResolved) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Comments · \(target.label ?? target.ref)", systemImage: "text.bubble").font(.subheadline.weight(.semibold))
                Spacer()
                let open = scoped.filter { $0.parentId == nil && !$0.isResolved }.count
                if open > 0 { Text("\(open) open").font(.caption2).foregroundStyle(.orange) }
                Toggle("Resolved", isOn: $showResolved).toggleStyle(.checkbox).controlSize(.small)
            }
            ForEach(roots) { c in
                commentRow(c)
                ForEach(scoped.filter { $0.parentId == c.id }) { reply in
                    commentRow(reply).padding(.leading, 18)
                }
            }
            if roots.isEmpty {
                Text("No comments yet. Mention a colleague with @handle to put it in their inbox.").font(.caption).foregroundStyle(.secondary)
            }
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 3) {
                    if let r = replyTo {
                        HStack {
                            Text("Replying to \(r.authorHandle)").font(.caption2).foregroundStyle(.secondary)
                            Button("×") { replyTo = nil }.buttonStyle(.plain).font(.caption2)
                        }
                    }
                    TextField("Comment… use @handle to mention", text: $draft, axis: .vertical)
                        .lineLimit(1...4)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { post() }
                    if !store.chatHandles.isEmpty, let at = draft.lastIndex(of: "@") {
                        let partial = String(draft[draft.index(after: at)...]).lowercased()
                        let matches = store.chatHandles.filter { $0.hasPrefix(partial) && !partial.contains(" ") }.prefix(5)
                        if !matches.isEmpty && !partial.contains(" ") {
                            HStack(spacing: 4) {
                                ForEach(Array(matches), id: \.self) { h in
                                    Button("@\(h)") { draft = String(draft[..<at]) + "@\(h) " }
                                        .controlSize(.mini)
                                }
                            }
                        }
                    }
                }
                Button {
                    post()
                } label: {
                    if posting { ProgressView().controlSize(.small) } else { Image(systemName: "paperplane.fill") }
                }
                .disabled(posting || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canEditMemo)
            }
            if let postError {
                Text(postError).font(.caption2).foregroundStyle(.red)
            }
        }
        .padding(10)
        .appleGlassCard()
        .task(id: [companyId, target.ref]) {
            draft = ""
            replyTo = nil
            postError = nil
            await store.loadComments(companyId)
            if store.chatHandles.isEmpty { await store.loadChatChannels() }
        }
    }

    private func commentRow(_ c: MacComment) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(c.authorHandle).font(.caption.weight(.semibold))
                Text(MacTimeFormat.relative(c.createdAt)).font(.caption2).foregroundStyle(.secondary)
                if c.isResolved { Label("Resolved", systemImage: "checkmark").font(.caption2).foregroundStyle(.green) }
                Spacer()
                if c.parentId == nil {
                    Button("Reply") { replyTo = c }.buttonStyle(.plain).font(.caption2).foregroundStyle(Color.accentColor)
                    Button(c.isResolved ? "Reopen" : "Resolve") {
                        Task { await store.resolveComment(companyId, commentId: c.id, resolved: !c.isResolved) }
                    }
                    .buttonStyle(.plain).font(.caption2).foregroundStyle(Color.accentColor)
                    .disabled(!store.canEditMemo)
                }
                if store.canEditMemo {
                    Button { Task { await store.deleteComment(companyId, commentId: c.id) } } label: {
                        Image(systemName: "trash").font(.caption2).foregroundStyle(.secondary)
                    }.buttonStyle(.plain)
                }
            }
            mentionText(c.text)
        }
        .padding(6)
        .background(Color.secondary.opacity(c.isResolved ? 0.03 : 0.06), in: RoundedRectangle(cornerRadius: 6))
    }

    private func mentionText(_ text: String) -> Text {
        var out = Text("")
        for (i, part) in text.split(separator: " ", omittingEmptySubsequences: false).enumerated() {
            let piece = part.hasPrefix("@") ? Text(String(part)).foregroundColor(.accentColor).bold() : Text(String(part))
            out = i == 0 ? piece : out + Text(" ") + piece
        }
        return out.font(.caption)
    }

    private func post() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !posting, store.canEditMemo, !text.isEmpty else { return }
        let cid = companyId
        let parentId = replyTo.flatMap { r in all.contains(where: { $0.id == r.id }) ? r.id : nil }
        posting = true
        postError = nil
        Task {
            if await store.addComment(cid, text: text, target: target, parentId: parentId) {
                if cid == companyId {
                    if draft.trimmingCharacters(in: .whitespacesAndNewlines) == text { draft = "" }
                    replyTo = nil
                }
                await store.loadMentions()
            } else if cid == companyId {
                postError = store.error ?? "Could not post the comment."
            }
            posting = false
        }
    }
}

// MARK: - Firm chat (blotter tab)

struct MacFirmChatPane: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var draft = ""
    @State private var sending = false
    @State private var sendError: String?
    @State private var showMentions = false

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("Channels").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Spacer()
                    if let m = store.mentions, m.openCount > 0 {
                        Button {
                            showMentions.toggle()
                        } label: {
                            Label("@\(m.openCount)", systemImage: "at")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.orange)
                        }
                        .buttonStyle(.plain)
                        .help("Open mentions")
                    }
                    if let company = store.selectedCompany {
                        Button {
                            Task { await store.openChat(channel: "company:\(company.id)") }
                        } label: {
                            Image(systemName: "plus.bubble")
                        }
                        .buttonStyle(.plain)
                        .help("Open a channel for \(company.title)")
                    }
                }
                .padding(8)
                Divider()
                List(selection: Binding(get: { store.chatChannel }, set: { if let v = $0 { Task { await store.openChat(channel: v) } } })) {
                    ForEach(store.chatChannels) { ch in
                        VStack(alignment: .leading, spacing: 1) {
                            HStack {
                                Image(systemName: ch.kind == "company" ? "building.2" : "number").font(.caption2).foregroundStyle(.secondary)
                                Text(ch.label).font(.caption.weight(.medium))
                                Spacer()
                                if ch.messageCount > 0 { Text("\(ch.messageCount)").font(.caption2).foregroundStyle(.tertiary) }
                            }
                            if let last = ch.lastMessage {
                                Text("\(last.authorHandle): \(last.text)").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                        .tag(ch.id)
                        .glassListRow(isSelected: store.chatChannel == ch.id)
                    }
                    if store.chatChannels.isEmpty {
                        Text("general").tag("general")
                            .glassListRow(isSelected: store.chatChannel == "general")
                    }
                }
                .listStyle(.inset)
            }
            .frame(minWidth: 180, idealWidth: 220, maxWidth: 280)

            VStack(spacing: 0) {
                if showMentions, let m = store.mentions {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Mentions for @\(m.handle)").font(.caption.weight(.semibold))
                            Spacer()
                            Button("Hide") { showMentions = false }.controlSize(.mini)
                        }
                        ForEach(m.items.prefix(8)) { item in
                            HStack(spacing: 6) {
                                Image(systemName: item.kind == "chat" ? "bubble.left" : "text.bubble").font(.caption2).foregroundStyle(.secondary)
                                Text("\(item.from ?? "?"):").font(.caption2.weight(.semibold))
                                Text(item.text).font(.caption2).lineLimit(1)
                                Spacer()
                                if item.resolved { Image(systemName: "checkmark").font(.caption2).foregroundStyle(.green) }
                                Text(MacTimeFormat.relative(item.at)).font(.caption2).foregroundStyle(.tertiary)
                            }
                            .contentShape(Rectangle())
                            .onTapGesture {
                                if let ch = item.channel { Task { await store.openChat(channel: ch) } }
                                else if let cid = item.companyId, let c = store.companies.first(where: { $0.id == cid }) { store.showCompany(c) }
                            }
                        }
                    }
                    .padding(8)
                    .background(Color.orange.opacity(0.06))
                    Divider()
                }
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 6) {
                            ForEach(store.chatMessages) { m in
                                HStack(alignment: .top, spacing: 8) {
                                    MacMonogram(name: m.authorHandle, size: 22)
                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack(spacing: 6) {
                                            Text(m.authorHandle).font(.caption.weight(.semibold))
                                            Text(MacTimeFormat.relative(m.at)).font(.caption2).foregroundStyle(.tertiary)
                                            if let cid = m.companyId, let c = store.companies.first(where: { $0.id == cid }) {
                                                Button(c.title) { store.showCompany(c) }.buttonStyle(.plain).font(.caption2).foregroundStyle(Color.accentColor)
                                            }
                                        }
                                        Text(m.text).font(.callout).textSelection(.enabled)
                                    }
                                }
                                .id(m.id)
                                .padding(.horizontal, 10)
                            }
                            if store.chatMessages.isEmpty {
                                Text("No messages in #\(store.chatChannel) yet.").font(.caption).foregroundStyle(.secondary).padding(10)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    .onChange(of: store.chatMessages.count) { _, _ in
                        if let last = store.chatMessages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                }
                Divider()
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        TextField("Message #\(store.chatChannel) — @handle to mention", text: $draft)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { send() }
                        Button { send() } label: {
                            if sending { ProgressView().controlSize(.small) } else { Image(systemName: "paperplane.fill") }
                        }
                        .disabled(sending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canEditMemo)
                    }
                    if let sendError {
                        Text(sendError).font(.caption2).foregroundStyle(.red)
                    }
                }
                .padding(8)
            }
            .frame(minWidth: 320, maxWidth: .infinity)
        }
        .task {
            // Start before any await so a quick tab switch's onDisappear always pairs with it.
            store.startChatPolling()
            await store.loadChatChannels()
            await store.loadMentions()
            await store.openChat(channel: store.chatChannel)
        }
        .onDisappear { store.stopChatPolling() }
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sending, store.canEditMemo, !text.isEmpty else { return }
        let cid = store.chatChannel.hasPrefix("company:") ? String(store.chatChannel.dropFirst(8)) : nil
        sending = true
        sendError = nil
        Task {
            if await store.sendChat(text, companyId: cid) {
                if draft.trimmingCharacters(in: .whitespacesAndNewlines) == text { draft = "" }
            } else {
                sendError = store.error ?? "Could not send the message."
            }
            sending = false
        }
    }
}

// MARK: - Audit trail (blotter tab)

struct MacAuditPane: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var onlySelected = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Toggle("Selected company only", isOn: $onlySelected).toggleStyle(.checkbox).controlSize(.small)
                    .disabled(store.selectedCompany == nil)
                    .onChange(of: onlySelected) { _, _ in reload() }
                Spacer()
                Text("Every change made through the API, with who made it").font(.caption2).foregroundStyle(.secondary)
                Button { reload() } label: { Image(systemName: "arrow.clockwise") }.controlSize(.small)
            }
            .padding(8)
            Divider()
            Table(store.auditRows) {
                TableColumn("When") { r in Text(MacTimeFormat.relative(r.at)).font(.caption) }.width(80)
                TableColumn("Who") { r in Text(r.actor).font(.caption) }.width(min: 90, ideal: 140)
                TableColumn("Action") { r in Text(r.action).font(.caption.monospacedDigit()) }.width(min: 200, ideal: 320)
                TableColumn("Company") { r in
                    if let cid = r.companyId {
                        Text(store.companies.first { $0.id == cid }?.title ?? cid).font(.caption)
                    } else { Text("—").foregroundStyle(.tertiary) }
                }
                .width(min: 100, ideal: 160)
                TableColumn("Status") { r in
                    Text("\(r.status)").font(.caption.monospacedDigit()).foregroundStyle(r.status >= 400 ? Color.red : Color.secondary)
                }
                .width(50)
            }
            .tableStyle(.inset(alternatesRowBackgrounds: true))
        }
        .task { reload() }
        .onChange(of: store.selectedCompany?.id) { _, _ in
            if onlySelected { reload() }
        }
    }

    private func reload() {
        Task { await store.loadAudit(companyId: onlySelected ? store.selectedCompany?.id : nil) }
    }
}

// MARK: - Signal score

struct MacSignalScoreView: View {
    let companyId: String
    var compact = false
    @EnvironmentObject private var store: MacAppStore
    @State private var expanded = false

    private var score: MacSignalScore? { store.signalScoreByCompany[companyId] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().stroke(Color.secondary.opacity(0.15), lineWidth: 5)
                    Circle()
                        .trim(from: 0, to: CGFloat((score?.score ?? 0)) / 100)
                        .stroke(color, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .opacity(thinCoverage ? 0.4 : 1)
                    Text(score?.score.map { "\($0)" } ?? "—").font(.system(size: compact ? 12 : 15, weight: .bold, design: .rounded)).monospacedDigit()
                }
                .frame(width: compact ? 40 : 52, height: compact ? 40 : 52)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("Signal score").font(compact ? .dsSubhead : .dsHeadline)
                        if thinCoverage, let s = score {
                            MacStatusPill(text: "Partial · \(s.components.filter(\.available).count) of \(s.components.count)", color: .orange)
                        }
                    }
                    Text(score.map { $0.isInsufficient ? "Insufficient data · \($0.components.filter(\.available).count) of \($0.components.count)" : $0.coverage.replacingOccurrences(of: " have data", with: " with data") } ?? "Loading…")
                        .font(.dsCaption).foregroundStyle(.secondary).lineLimit(2)
                    if let s = score, !compact { Text(s.formula).font(.dsCaption).foregroundStyle(.tertiary) }
                }
                Spacer()
                Button(expanded ? "Hide" : "Formula") { expanded.toggle() }.controlSize(.mini)
                Button { Task { await store.loadSignalScore(companyId) } } label: { Image(systemName: "arrow.clockwise") }.controlSize(.mini).buttonStyle(.plain)
            }
            if expanded, let s = score {
                VStack(spacing: 0) {
                    ForEach(s.components) { c in
                        HStack(alignment: .top, spacing: 8) {
                            Text(c.name).font(.caption.weight(.semibold)).frame(width: 110, alignment: .leading)
                            Text(c.available ? String(format: "%.1f / %d", c.points ?? 0, c.max) : "not scored · \(c.max) max")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(c.available ? Color.primary : Color.secondary)
                                .frame(width: 120, alignment: .leading)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(c.formula).font(.caption2).foregroundStyle(.secondary)
                                Text(c.basis).font(.caption2).foregroundStyle(.tertiary)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 5)
                        Divider()
                    }
                }
                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(compact ? 8 : 12)
        .appleGlassCard()
        .task(id: companyId) { if score == nil { await store.loadSignalScore(companyId) } }
    }

    private var color: Color {
        guard let s = score?.score else { return .secondary }
        return s >= 70 ? .green : (s >= 40 ? .orange : .red)
    }

    /// A score built from fewer than half its components is a partial read.
    /// The caption said so in small print while the number sat in a
    /// full-strength ring; the pill says it beside the title and the ring dims.
    private var thinCoverage: Bool {
        guard let s = score, s.score != nil, !s.components.isEmpty else { return false }
        return s.components.filter(\.available).count * 2 < s.components.count
    }
}

// MARK: - Transcript library (Documents desk)

struct MacTranscriptLibraryView: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var query = ""
    @State private var selection: String?
    @State private var showAdd = false
    @State private var highlightDraft = ""
    @State private var highlightNote = ""
    @State private var highlightError: String?
    @State private var savingHighlight = false
    @State private var confirmDeleteTranscript: MacTranscript?
    @State private var deleteError: String?

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Search transcripts", text: $query)
                        .textFieldStyle(.plain)
                        .onSubmit { Task { await store.loadTranscripts(query: query) } }
                    Button { showAdd = true } label: { Image(systemName: "plus") }
                        .buttonStyle(.plain)
                        .disabled(!store.canEditSources)
                        .help("Add a transcript (paste or upload .txt/.vtt/.srt/.docx/.pdf)")
                }
                .padding(10)
                .background(.ultraThinMaterial)
                Divider()
                List(store.transcripts, selection: $selection) { t in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(t.title).font(.callout.weight(.medium)).lineLimit(1)
                        HStack(spacing: 6) {
                            Text(t.kindLabel).font(.caption2).foregroundStyle(.secondary)
                            if let n = t.companyName { Text("· \(n)").font(.caption2).foregroundStyle(.secondary) }
                            Spacer()
                            Text(t.callDate ?? "").font(.caption2).foregroundStyle(.tertiary)
                        }
                        HStack(spacing: 6) {
                            Text("\(t.wordCount) words").font(.caption2).foregroundStyle(.tertiary)
                            if t.highlightCount > 0 { Text("· \(t.highlightCount) highlights").font(.caption2).foregroundStyle(.orange) }
                        }
                    }
                    .tag(t.id)
                    .padding(.vertical, 2)
                }
                .listStyle(.inset)
                .overlay {
                    if store.transcripts.isEmpty {
                        ContentUnavailableView("No transcripts", systemImage: "waveform", description: Text("Add expert, founder or customer calls. Every word becomes searchable in Firm Memory (⌘⇧F)."))
                    }
                }
            }
                .frame(minWidth: 280, idealWidth: 320, maxWidth: 400, maxHeight: .infinity)

                Divider()

                detail
                    .frame(minWidth: 460, maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .task {
            await store.loadTranscripts()
            if let id = store.transcriptToOpen {
                selection = id
                store.transcriptToOpen = nil
            }
        }
        .onChange(of: store.transcriptToOpen) { _, id in
            if let id { selection = id; store.transcriptToOpen = nil }
        }
        .onChange(of: selection) { _, id in
            highlightDraft = ""
            highlightNote = ""
            highlightError = nil
            deleteError = nil
            if let id { Task { await store.loadTranscript(id) } }
        }
        .sheet(isPresented: $showAdd) { MacAddTranscriptSheet { id in selection = id } }
        .confirmationDialog(
            "Delete this transcript?",
            isPresented: Binding(get: { confirmDeleteTranscript != nil }, set: { if !$0 { confirmDeleteTranscript = nil } }),
            presenting: confirmDeleteTranscript
        ) { t in
            Button("Delete", role: .destructive) {
                Task {
                    await store.deleteTranscript(t.id)
                    if store.transcriptById[t.id] == nil {
                        if selection == t.id { selection = nil }
                    } else {
                        deleteError = store.error ?? "Could not delete the transcript."
                    }
                }
            }
        } message: { t in
            Text("\(t.title) and its \(t.highlightCount) highlight(s) will be permanently deleted. This cannot be undone.")
        }
    }

    @ViewBuilder
    private var detail: some View {
        if let id = selection, let t = store.transcriptById[id] {
            VStack(spacing: 0) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(t.title).font(.title3.weight(.bold))
                        Text([t.kindLabel, t.companyName, t.callDate, t.participants.isEmpty ? nil : t.participants.joined(separator: ", ")].compactMap { $0 }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary)
                        if !t.tags.isEmpty {
                            HStack(spacing: 4) {
                                ForEach(t.tags, id: \.self) { tag in
                                    Text(tag).font(.caption2).padding(.horizontal, 6).padding(.vertical, 2).background(Color.secondary.opacity(0.1), in: Capsule())
                                }
                            }
                        }
                    }
                    Spacer()
                    if let cid = t.companyId, let c = store.companies.first(where: { $0.id == cid }) {
                        Button { store.showCompany(c) } label: { Label(c.title, systemImage: "building.2") }.controlSize(.small)
                    }
                    Button(role: .destructive) { confirmDeleteTranscript = t } label: { Image(systemName: "trash") }
                        .controlSize(.small)
                        .disabled(!store.canDeleteDocuments)
                        .help("Delete transcript")
                }
                .padding(14)
                if let deleteError {
                    Text(deleteError).font(.caption2).foregroundStyle(.red).padding(.horizontal, 14).padding(.bottom, 8)
                }
                Divider()
                HSplitView {
                    ScrollView {
                        Text(t.text)
                            .font(.system(size: 13))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16)
                    }
                    .frame(minWidth: 300)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Highlights").font(.subheadline.weight(.semibold))
                        Text("Paste a passage from the transcript and a note; highlights show up in Firm Memory and the IC room.")
                            .font(.caption2).foregroundStyle(.secondary)
                        TextField("Quote", text: $highlightDraft, axis: .vertical).lineLimit(2...5).textFieldStyle(.roundedBorder)
                        TextField("Why it matters", text: $highlightNote).textFieldStyle(.roundedBorder)
                        Button("Add highlight") {
                            let q = highlightDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !q.isEmpty, !savingHighlight else { return }
                            let draft = highlightDraft, note = highlightNote, id = t.id
                            savingHighlight = true
                            highlightError = nil
                            Task {
                                let ok = await store.addHighlight(transcriptId: id, text: q, note: note)
                                savingHighlight = false
                                guard ok else {
                                    highlightError = store.error ?? "Could not save the highlight. The transcript may have been deleted."
                                    return
                                }
                                if selection == id && highlightDraft == draft && highlightNote == note {
                                    highlightDraft = ""
                                    highlightNote = ""
                                }
                            }
                        }
                        .controlSize(.small)
                        .disabled(highlightDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canEditMemo || savingHighlight)
                        if let highlightError {
                            Text(highlightError).font(.caption2).foregroundStyle(.red)
                        }
                        Divider()
                        ScrollView {
                            VStack(alignment: .leading, spacing: 6) {
                                ForEach(t.highlights) { h in
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("“\(h.text)”").font(.caption.italic())
                                        if let n = h.note, !n.isEmpty { Text(n).font(.caption2).foregroundStyle(.secondary) }
                                        HStack {
                                            Text(h.createdBy?.isEmpty == false ? h.createdBy! : "dev").font(.caption2).foregroundStyle(.tertiary)
                                            Spacer()
                                            if store.canEditMemo {
                                                Button { Task { await store.removeHighlight(transcriptId: t.id, highlightId: h.id) } } label: {
                                                    Image(systemName: "minus.circle").font(.caption2).foregroundStyle(.secondary)
                                                }.buttonStyle(.plain)
                                            }
                                        }
                                    }
                                    .padding(6)
                                    .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                                    .draggable("“\(h.text)” — \(t.title)")
                                }
                            }
                        }
                    }
                    .padding(12)
                    .frame(minWidth: 220, idealWidth: 260, maxWidth: 320)
                }
            }
        } else {
            ContentUnavailableView("Transcripts", systemImage: "waveform", description: Text("Select a transcript to read it and add highlights."))
        }
    }
}

struct MacAddTranscriptSheet: View {
    let onAdded: (String) -> Void
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var kind = "expert_call"
    @State private var companyId = ""
    @State private var tags = ""
    @State private var participants = ""
    @State private var errorText: String?
    @State private var text = ""
    @State private var fileURL: URL?
    @State private var saving = false

    var body: some View {
        VStack(spacing: 0) {
            HStack { Text("Add transcript").font(.headline); Spacer(); Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction) }.padding(16)
            Divider()
            Form {
                TextField("Title", text: $title)
                Picker("Kind", selection: $kind) {
                    Text("Expert call").tag("expert_call")
                    Text("Founder call").tag("founder_call")
                    Text("Customer call").tag("customer_call")
                    Text("Reference call").tag("reference_call")
                    Text("Earnings call").tag("earnings_call")
                    Text("Internal").tag("internal")
                    Text("Other").tag("other")
                }
                Picker("Company", selection: $companyId) {
                    Text("None").tag("")
                    ForEach(store.companies) { c in Text(c.title).tag(c.id) }
                }
                TextField("Participants (comma-separated)", text: $participants)
                TextField("Tags (comma-separated)", text: $tags)
                #if os(macOS)
                HStack {
                    Button(fileURL == nil ? "Choose file (.txt .vtt .srt .docx .pdf)…" : fileURL!.lastPathComponent) {
                        let panel = NSOpenPanel()
                        panel.allowedContentTypes = [.plainText, .text, .pdf, .init(filenameExtension: "vtt") ?? .text, .init(filenameExtension: "srt") ?? .text, .init(filenameExtension: "docx") ?? .data]
                        panel.allowsMultipleSelection = false
                        if panel.runModal() == .OK { fileURL = panel.url; if title.isEmpty { title = panel.url?.deletingPathExtension().lastPathComponent ?? "" } }
                    }
                    if fileURL != nil { Button("Clear") { fileURL = nil }.controlSize(.small) }
                }
                #endif
                if fileURL == nil {
                    TextEditor(text: $text)
                        .font(.system(size: 12))
                        .frame(minHeight: 160)
                        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.secondary.opacity(0.25)))
                }
            }
            .formStyle(.grouped)
            Divider()
            HStack {
                Text("Timestamps and cue numbers are stripped; speaker labels are kept.").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                if let errorText {
                    Text(errorText).font(.caption2).foregroundStyle(.red).lineLimit(2)
                }
                Button {
                    saving = true
                    errorText = nil
                    store.error = nil
                    Task {
                        let t: MacTranscript?
                        if let fileURL {
                            t = await store.uploadTranscript(fileURL: fileURL, title: title, kind: kind, companyId: companyId.isEmpty ? nil : companyId, tags: tags, participants: participants)
                        } else {
                            t = await store.addTranscript(fields: ["title": title, "kind": kind, "company_id": companyId.isEmpty ? nil : companyId, "tags": tags, "participants": participants, "text": text])
                        }
                        saving = false
                        if let t {
                            onAdded(t.id)
                            dismiss()
                        } else {
                            errorText = store.error ?? "Could not add the transcript."
                        }
                    }
                } label: { if saving { ProgressView().controlSize(.small) } else { Text("Add") } }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving || (fileURL == nil && text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
            }
            .padding(12)
        }
        .frame(width: 560, height: 600)
    }
}
