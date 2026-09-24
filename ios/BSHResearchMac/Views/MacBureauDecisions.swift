//
//  MacBureauDecisions.swift
//  BSHResearchMac
//
//  The Research Desk's Decisions cards under Bureau, as the website draws them
//  (components/research/ICPrepCard.vue, ICRoomCard.vue, NumberLintCard.vue,
//  ThesisTrackerCard.vue and CompanyCommentsCard.vue): the controls they share — the
//  segmented control, the spinner, the checkbox and the comment field — and the numbers-lint
//  and comments cards. IC prep, the IC room and the thesis tracker keep their Bureau bodies
//  in their own files, drawn from the same state as their other designs.
//

import SwiftUI

// MARK: - Where the cards are

private struct MacBureauResearchDeskKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True inside the Bureau dossier. IC prep, the IC room and the thesis tracker also sit
    /// in the IC Review window, which keeps its own look; only the dossier draws them as the
    /// website's Research Desk cards.
    var bureauResearchDesk: Bool {
        get { self[MacBureauResearchDeskKey.self] }
        set { self[MacBureauResearchDeskKey.self] = newValue }
    }
}

// MARK: - Type

/// One line of the desk's small type (`.mac-t-caption10` and friends): the face at `size`,
/// on the website's line box, as wide as the browser sets it.
struct MacBureauDeskCaption: View {
    let text: String
    var size: CGFloat = 10
    var weight: Font.Weight = .regular
    var lineHeight: CGFloat = 12.5
    var mono = false
    let color: Color

    var body: some View {
        Text(text)
            .font(mono ? BSHType.bureauSans(size, weight: weight).monospacedDigit() : BSHType.bureauSans(size, weight: weight))
            .foregroundStyle(color)
            .lineLimit(1)
            .bureauExactWidth(text, size: size, weight: weight, mono: mono)
            .bureauDeskLine(lineHeight, size)
    }
}

// MARK: - Controls

/// `.mac-segmented`: segments sharing the width equally on a sunken capsule; the chosen one
/// fresh paper with a hairline and a small shadow under it, the others ink at 75%.
struct MacBureauDeskSegmented<Value: Hashable>: View {
    @Binding var selection: Value
    let segments: [(Value, String)]
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        HStack(spacing: 0) {
            ForEach(segments, id: \.0) { value, label in
                MacBureauDeskSegment(label: label, chosen: value == selection) {
                    withAnimation(.snappy(duration: 0.2)) { selection = value }
                }
            }
        }
        .padding(2)
        .bureauBackground {
            // color-mix(label 6%), pressed in: inset 0 1px 2px shadow / 0.06.
            Capsule()
                .fill(ink.label(0.06))
                .overlay(
                    Capsule()
                        .stroke(ink.shadow(0.06), lineWidth: 2)
                        .offset(y: 1)
                        .blur(radius: 1)
                        .clipShape(Capsule())
                )
        }
    }
}

private struct MacBureauDeskSegment: View {
    let label: String
    let chosen: Bool
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        Button(action: action) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(chosen ? ink.label : ink.label(0.75))
                .lineLimit(1)
                .bureauExactWidth(label, size: 11, weight: .medium)
                .bureauDeskLine(13.2, 11)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .frame(maxWidth: .infinity)
                .bureauBackground {
                    if chosen {
                        // --mac-pill-fill with --mac-pill-contact and --mac-thumb-drop.
                        Capsule()
                            .fill(ink.raised)
                            .overlay(Capsule().inset(by: -0.5).stroke(ink.label(0.08), lineWidth: 1))
                            .shadow(color: ink.shadow(0.14), radius: 1.5, y: 1)
                    } else if hovered {
                        Capsule().fill(ink.label(0.05))
                    }
                }
                .contentShape(Capsule())
        }
        .buttonStyle(MacBureauFlatButtonStyle())
        .onHover { hovered = $0 }
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }
}

/// `.mac-spinner`: a ring of ink at 15% with its top quarter in the secondary ink, turning.
struct MacBureauDeskSpinner: View {
    var size: CGFloat = 14
    @Environment(\.colorScheme) private var colorScheme
    @State private var turning = false

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let width = min(2, size / 6)
        ZStack {
            Circle().strokeBorder(ink.label(0.15), lineWidth: width)
            Circle()
                .inset(by: width / 2)
                .trim(from: 0.625, to: 0.875)
                .stroke(ink.secondary, lineWidth: width)
        }
        .frame(width: size, height: size)
        .rotationEffect(.degrees(turning ? 360 : 0))
        .animation(.linear(duration: 0.8).repeatForever(autoreverses: false), value: turning)
        .onAppear { turning = true }
        .accessibilityLabel("Loading")
    }
}

/// A native checkbox as Chrome draws one on the desk (`accent-color` brass): paper ruled in
/// grey, or brass with a white tick.
struct MacBureauDeskCheckMark: View {
    let isOn: Bool
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let box = RoundedRectangle(cornerRadius: 2, style: .circular)
        ZStack {
            if isOn {
                box.fill(ink.accent)
                // Chrome's tick: two strokes meeting low and left of centre.
                Path { path in
                    path.move(to: CGPoint(x: 3.3, y: 7.0))
                    path.addLine(to: CGPoint(x: 5.5, y: 9.2))
                    path.addLine(to: CGPoint(x: 10.4, y: 3.4))
                }
                .stroke(Color.white, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .miter))
            } else {
                // Chrome's form controls: #FFF ruled #767676, or #3B3B3B ruled #858585 in dark.
                box.fill(Color.bshFixed(ink.dark ? BSHRGB(59, 59, 59) : BSHRGB(255, 255, 255)))
                box.strokeBorder(Color.bshFixed(ink.dark ? BSHRGB(133, 133, 133) : BSHRGB(118, 118, 118)), lineWidth: 1)
            }
        }
        .frame(width: 14, height: 14)
        .bureauSnap(x: .whole)
    }
}

/// A one-row `textarea.mac-field` that grows as it's written in and can be dragged taller
/// by its grip: 13pt on an 18.2pt line, 4pt above and below and 8pt either side, on fresh
/// paper with 7pt corners.
struct MacBureauDeskTextArea: View {
    @Binding var text: String
    let placeholder: String
    var onSubmit: () -> Void = {}
    @Environment(\.colorScheme) private var colorScheme
    @State private var extra: CGFloat = 0
    @State private var dragBase: CGFloat?

    /// 18.2px lines (18.1875 in Blink's 64ths) plus the padding.
    private static let rowHeight: CGFloat = 26.1875

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        ZStack(alignment: .topLeading) {
            if text.isEmpty {
                Text(placeholder)
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.tertiary)
                    .lineLimit(1)
                    .bureauDeskLine(18.2, 13)
                    .allowsHitTesting(false)
            }
            TextField("", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(13))
                .foregroundStyle(ink.label)
                .lineLimit(1...6)
                .padding(.top, 1)
                .onSubmit(onSubmit)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, minHeight: Self.rowHeight + extra, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
        .overlay(alignment: .bottomTrailing) {
            MacBureauDeskResizeGrip(extra: $extra, dragBase: $dragBase)
        }
    }
}

// MARK: - Numbers lint

/// NumberLintCard: what the numbers check found in the latest memo, with the untraced figures
/// behind "Show".
struct MacBureauNumberLintCard: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var expanded = false
    @State private var loading = false

    private var lint: MacNumberLint? { store.numberLintByCompany[companyId] }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("hash", size: 14)
                    .foregroundStyle(ink.accent)
                MacBureauDeskCaption(text: "Numbers lint", size: 11, weight: .semibold, lineHeight: 14.3, color: ink.label)
                Spacer(minLength: 0)
                if let lint {
                    if lint.memoPackage == nil {
                        MacBureauDeskCaption(text: "No memo yet", color: ink.secondary)
                    } else {
                        MacBureauDeskCaption(
                            text: "\(lint.supported) of \(lint.checked) figures found in sources",
                            mono: true,
                            color: lint.unsupported == 0 ? ink.green : ink.orange
                        )
                        if lint.unsupported > 0 && !lint.findings.isEmpty {
                            Button {
                                expanded.toggle()
                            } label: {
                                MacBureauDeskButtonLabel(title: expanded ? "Hide" : "Show \(lint.unsupported)", size: .mini)
                            }
                            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                        }
                    }
                }
                MacBureauDeskRefreshButton(busy: loading) {
                    Task { await reload() }
                }
            }
            .frame(minHeight: 15)

            if let lint, lint.memoPackage != nil {
                if let pct = lint.coveragePct {
                    MacBureauDeskMeter(fraction: Double(pct) / 100, tint: lint.unsupported == 0 ? ink.green : ink.orange)
                }
                if expanded {
                    ForEach(lint.findings, id: \.position) { finding in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                MacBureauDeskCaption(text: finding.number, mono: true, color: ink.orange)
                                if !finding.section.isEmpty {
                                    MacBureauDeskCaption(text: "§ \(finding.section)", color: ink.secondary)
                                }
                            }
                            MacBureauWebParagraph(text: finding.excerpt, size: 10, lineHeight: 12.5, maxLines: 2)
                                .foregroundStyle(ink.secondary)
                        }
                        .padding(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.orange.opacity(0.07))
                    }
                    if !lint.sources.isEmpty {
                        MacBureauWebParagraph(text: "Checked against: " + lint.sources.joined(separator: " · "), size: 10, lineHeight: 12.5)
                            .foregroundStyle(ink.tertiary)
                    }
                } else if let note = lint.note, !note.isEmpty {
                    MacBureauWebParagraph(text: note, size: 10, lineHeight: 12.5)
                        .foregroundStyle(ink.tertiary)
                }
            }
        }
        .bureauDeskCard(padding: 10)
        .task(id: companyId) {
            expanded = false
            if lint == nil { await reload() }
        }
    }

    private func reload() async {
        loading = true
        await store.loadNumberLint(companyId)
        loading = false
    }
}

/// The desk's thin bar (`h-1 rounded-full`): the secondary ink at 15%, filled to `fraction`.
struct MacBureauDeskMeter: View {
    let fraction: Double
    let tint: Color
    var height: CGFloat = 4
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(ink.secondary.opacity(0.15))
                Capsule()
                    .fill(tint)
                    .frame(width: proxy.size.width * CGFloat(max(0, min(1, fraction))))
            }
        }
        .frame(height: height)
        .animation(.easeOut(duration: 0.5), value: fraction)
    }
}

// MARK: - Comments

/// CompanyCommentsCard: the threads on the company, replies set in 18pt, and the field that
/// posts a comment and mentions a colleague with @handle.
struct MacBureauCommentsCard: View {
    let companyId: String
    let target: MacCommentTarget
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
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
    private var openCount: Int { scoped.filter { $0.parentId == nil && !$0.isResolved }.count }
    private var canPost: Bool {
        !posting && store.canEditMemo && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("message-square", size: 14)
                    .foregroundStyle(ink.accent)
                Text("Comments · \(target.label ?? target.ref)")
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(14.3, 11)
                    .layoutPriority(-1)
                Spacer(minLength: 0)
                if openCount > 0 {
                    MacBureauDeskCaption(text: "\(openCount) open", color: ink.orange)
                }
                Button {
                    showResolved.toggle()
                } label: {
                    HStack(spacing: 6) {
                        MacBureauDeskCheckMark(isOn: showResolved)
                        MacBureauDeskCaption(text: "Resolved", color: ink.label)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                .accessibilityAddTraits(.isToggle)
                .accessibilityValue(showResolved ? "On" : "Off")
            }
            .frame(minHeight: 14.3)

            ForEach(roots) { comment in
                row(comment, ink: ink)
                ForEach(scoped.filter { $0.parentId == comment.id }) { reply in
                    row(reply, ink: ink)
                        .padding(.leading, 18)
                }
            }
            if roots.isEmpty {
                MacBureauWebParagraph(text: "No comments yet. Use @handle to mention a colleague.", size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.secondary)
            }

            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    if let replyTo {
                        HStack(spacing: 4) {
                            MacBureauDeskCaption(text: "Replying to \(replyTo.authorHandle)", color: ink.secondary)
                            Button {
                                self.replyTo = nil
                            } label: {
                                MacBureauDeskCaption(text: "×", color: ink.secondary)
                            }
                            .buttonStyle(MacBureauFlatButtonStyle())
                        }
                    }
                    MacBureauDeskTextArea(text: $draft, placeholder: "Comment… use @handle to mention") { post() }
                    let suggestions = handleSuggestions
                    if !suggestions.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(suggestions, id: \.self) { handle in
                                Button {
                                    if let at = draft.lastIndex(of: "@") { draft = String(draft[..<at]) + "@\(handle) " }
                                } label: {
                                    MacBureauDeskButtonLabel(title: "@\(handle)", size: .mini)
                                }
                                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                            }
                        }
                    }
                }
                Button {
                    post()
                } label: {
                    if posting {
                        MacBureauDeskSpinner(size: 12)
                    } else {
                        MacBureauDeskIcon("send", size: 12)
                    }
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(!canPost)
                .help("Post")
            }
            if let postError {
                MacBureauWebParagraph(text: postError, size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.red)
            }
        }
        .bureauDeskCard(padding: 10)
        .task(id: [companyId, target.ref]) {
            draft = ""
            replyTo = nil
            postError = nil
            await store.loadComments(companyId)
            if store.chatHandles.isEmpty { await store.loadChatChannels() }
        }
    }

    /// Handles that finish the @word being typed.
    private var handleSuggestions: [String] {
        guard !store.chatHandles.isEmpty, let at = draft.lastIndex(of: "@") else { return [] }
        let partial = String(draft[draft.index(after: at)...]).lowercased()
        guard !partial.contains(" ") else { return [] }
        return Array(store.chatHandles.filter { $0.hasPrefix(partial) }.prefix(5))
    }

    private func row(_ comment: MacComment, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                MacBureauDeskCaption(text: comment.authorHandle, color: ink.label)
                MacBureauDeskCaption(text: MacBureauMemoFormat.relative(comment.createdAt), color: ink.secondary)
                if comment.isResolved {
                    HStack(spacing: 2) {
                        MacBureauDeskIcon("check", size: 10)
                        MacBureauDeskCaption(text: "Resolved", color: ink.green)
                    }
                    .foregroundStyle(ink.green)
                }
                Spacer(minLength: 0)
                if comment.parentId == nil {
                    Button {
                        replyTo = comment
                    } label: {
                        MacBureauDeskCaption(text: "Reply", color: ink.accent)
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    Button {
                        Task { await store.resolveComment(companyId, commentId: comment.id, resolved: !comment.isResolved) }
                    } label: {
                        MacBureauDeskCaption(text: comment.isResolved ? "Reopen" : "Resolve", color: ink.accent)
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    .disabled(!store.canEditMemo)
                }
                if store.canEditMemo {
                    Button {
                        Task { await store.deleteComment(companyId, commentId: comment.id) }
                    } label: {
                        MacBureauDeskIcon("trash-2", size: 10)
                            .foregroundStyle(ink.secondary)
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    .help("Delete")
                }
            }
            mentionText(comment.text, ink: ink)
                .lineSpacing(0.5)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
        }
        .padding(6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(comment.isResolved ? 0.03 : 0.06))
    }

    /// The comment with each @mention in brass and bold.
    private func mentionText(_ text: String, ink: MacBureauDeskInk) -> Text {
        var out = Text("")
        for (index, part) in text.split(separator: " ", omittingEmptySubsequences: false).enumerated() {
            let word = String(part)
            let piece = word.hasPrefix("@")
                ? Text(word).font(BSHType.bureauSans(10, weight: .bold)).foregroundColor(ink.accent)
                : Text(word).font(BSHType.bureauSans(10)).foregroundColor(ink.label)
            out = index == 0 ? piece : out + Text(" ").font(BSHType.bureauSans(10)) + piece
        }
        return out
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
