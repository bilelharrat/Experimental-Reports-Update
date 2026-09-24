import SwiftUI

/// IC room card: live votes, the red-team memo, comparable past decisions and reference calls.
/// Used in the IC Review window side panel and in the dossier's IC section.
struct MacICRoomView: View {
    let companyId: String
    let reportId: String?
    var findText: Binding<MacFindRequest?>? = nil
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.openWindow) private var openWindow

    @State private var form = ICRoomForm()
    @State private var closing = false

    private struct ICRoomForm: Equatable {
        var tab = "votes"
        var vote = "invest"
        var conviction = 3
        var voteNote = ""
        var showAddRef = false
        var showCloseSheet = false
    }

    private var meetings: [MacICMeeting] { store.icMeetingsByCompany[companyId] ?? [] }
    private var openMeeting: MacICMeeting? { meetings.first { $0.isOpen } }
    private var refs: MacReferenceCalls? { store.referenceCallsByCompany[companyId] }
    private var comparables: MacComparables? { store.comparablesByCompany[companyId] }
    private var redTeam: MacRedTeam? { store.redTeamByCompany[companyId] }

    @Environment(\.bureauResearchDesk) private var bureauDesk
    @Environment(\.colorScheme) private var colorScheme
    @State private var bureauLoading = false

    var body: some View {
        if BSHDesign.active == .bureau && bureauDesk {
            bureauBody
        } else {
            glassBody
        }
    }

    private var glassBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                    Label("IC room", systemImage: "person.3.sequence")
                        .font(.dsHeadline)
                    Spacer()
                }
                GlassSegmentedPicker("Section", selection: $form.tab, segments: ["votes": "Votes", "red": "Red team", "comps": "Comparables", "refs": "References"])
                .controlSize(.small)
                .frame(maxWidth: .infinity)
            switch form.tab {
            case "red": redTeamBlock
            case "comps": comparablesBlock
            case "refs": referencesBlock
            default: votesBlock
            }
        }
        .padding(10)
        .appleGlassCard()
        .task(id: companyId) {
            if form != ICRoomForm() { form = ICRoomForm() }
            await store.loadICRoom(companyId)
        }
        .sheet(isPresented: $form.showAddRef) { MacReferenceCallSheet(companyId: companyId) }
        .sheet(isPresented: $form.showCloseSheet) {
            if let m = openMeeting { MacCloseMeetingSheet(companyId: companyId, meeting: m) }
        }
    }

    // MARK: Votes

    private var votesBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let m = openMeeting {
                HStack {
                    Text(m.title).font(.ui(.caption).weight(.semibold))
                    Text("open · \(MacTimeFormat.relative(m.createdAt))").font(.ui(.caption2)).foregroundStyle(.secondary)
                    Spacer()
                    Button("Close meeting…") { form.showCloseSheet = true }
                        .controlSize(.small)
                        .disabled(!store.canEditMemo)
                }
                if let t = m.tally {
                    HStack(spacing: 8) {
                        tallyPill("Invest", t.invest, .green)
                        tallyPill("Pass", t.pass, .red)
                        tallyPill("More work", t.moreWork, .orange)
                        Spacer()
                        if let avg = t.averageConviction {
                            Text(String(format: "conviction %.1f / 5", avg)).font(.ui(.caption2)).foregroundStyle(.secondary)
                        }
                        if t.tied { Text("Tied").font(.ui(.caption2).weight(.semibold)).foregroundStyle(.orange) }
                    }
                    if t.total > 0 {
                        GeometryReader { geo in
                            HStack(spacing: 1) {
                                Rectangle().fill(Color.green).frame(width: geo.size.width * CGFloat(t.invest) / CGFloat(t.total))
                                Rectangle().fill(Color.orange).frame(width: geo.size.width * CGFloat(t.moreWork) / CGFloat(t.total))
                                Rectangle().fill(Color.red).frame(width: geo.size.width * CGFloat(t.pass) / CGFloat(t.total))
                            }
                        }
                        .frame(height: 6)
                        .clipShape(Capsule())
                    }
                }
                ForEach(m.votes) { v in
                    HStack(spacing: 6) {
                        Text(v.displayName).font(.ui(.caption).weight(.medium))
                        MacStatusPill(text: v.label, color: v.vote == "invest" ? .green : (v.vote == "pass" ? .red : .orange))
                        if let c = v.conviction { Text("★\(c)").font(.ui(.caption2)).foregroundStyle(.secondary) }
                        if let n = v.note, !n.isEmpty { Text(n).font(.ui(.caption2)).foregroundStyle(.secondary).lineLimit(1) }
                        Spacer()
                    }
                }
                Divider()
                HStack(spacing: 8) {
                    GlassSegmentedPicker("Vote", selection: $form.vote, segments: ["invest": "Invest", "more_work": "More work", "pass": "Pass"])
                        .controlSize(.small).frame(width: 200)
                    Stepper("★\(form.conviction)", value: $form.conviction, in: 1...5).controlSize(.small).frame(width: 70)
                    TextField("Note", text: $form.voteNote).textFieldStyle(.dsField).controlSize(.small)
                    Button("Vote as \(store.memberName)") {
                        let target = companyId
                        Task {
                            if await store.castICVote(target, meetingId: m.id, vote: form.vote, conviction: form.conviction, note: form.voteNote), target == companyId { form.voteNote = "" }
                        }
                    }
                    .controlSize(.small)
                    .buttonStyle(.dsProminent)
                    .disabled(!store.canEditMemo)
                }
            } else {
                HStack {
                    Text(meetings.isEmpty ? "No IC meeting yet." : "No open meeting. \(meetings.count) past meeting(s).")
                        .font(.ui(.caption)).foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        Task { await store.openICMeeting(companyId, title: "", reportId: reportId) }
                    } label: {
                        Label("Open meeting", systemImage: "plus")
                    }
                    .controlSize(.small)
                    .disabled(!store.canEditMemo)
                }
                ForEach(meetings.prefix(3)) { m in
                    HStack(spacing: 6) {
                        Text(m.title).font(.ui(.caption))
                        if let t = m.tally {
                            Text("\(t.invest)/\(t.pass)/\(t.moreWork)").font(.ui(.caption2).monospacedDigit()).foregroundStyle(.secondary)
                                .help("invest / pass / more work")
                        }
                        if m.decisionId != nil { Label("Decision recorded", systemImage: "checkmark.seal").font(.ui(.caption2)).foregroundStyle(.green) }
                        Spacer()
                        Text(MacTimeFormat.relative(m.closedAt ?? m.createdAt)).font(.ui(.caption2)).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func tallyPill(_ label: String, _ n: Int, _ color: Color) -> some View {
        Text("\(n) \(label)")
            .font(.ui(.caption2).weight(.semibold).monospacedDigit())
            .foregroundStyle(color)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(color.opacity(0.12), in: Capsule())
    }

    // MARK: Red team

    private var redTeamBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let rt = redTeam, let at = rt.generatedAt, rt.result != nil {
                    Text("Argued \(MacTimeFormat.relative(at)) · \(rt.memoBlocksUsed) memo blocks · \(rt.referenceConcerns) reference concerns")
                        .font(.ui(.caption2)).foregroundStyle(.secondary)
                } else {
                    Text("Claude argues the other side from the memo, contradicted evidence and reference-call concerns.")
                        .font(.ui(.caption2)).foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    guard MacTokenConfirm.ask() else { return }
                    Task { await store.runRedTeam(companyId) }
                } label: {
                    if redTeam?.isRunning == true {
                        HStack(spacing: 4) { ProgressView().controlSize(.mini); Text("Arguing…") }
                    } else {
                        Label(redTeam?.result == nil ? "Run red team" : "Re-run", systemImage: "flag.checkered")
                    }
                }
                .controlSize(.small)
                .disabled(redTeam?.isRunning == true || !store.canRunTasks)
            }
            if let err = redTeam?.error, redTeam?.result == nil {
                Text(err).font(.ui(.caption)).foregroundStyle(.red)
            }
            if let r = redTeam?.result {
                Text(r.counterThesis).font(.ui(.callout)).textSelection(.enabled)
                Text("Kill risks").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(Array(r.killRisks.enumerated()), id: \.offset) { _, k in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(k.severity == "high" ? Color.red : (k.severity == "medium" ? Color.orange : Color.secondary)).frame(width: 7, height: 7)
                            Text(k.risk).font(.ui(.caption).weight(.semibold))
                            if let s = k.memoSection, !s.isEmpty {
                                if let findText {
                                    Button { findText.wrappedValue = MacFindRequest(text: s) } label: { Text("§ \(s)").font(.ui(.caption2)) }.buttonStyle(.plain).foregroundStyle(Color.dsAccent)
                                } else {
                                    Text("§ \(s)").font(.ui(.caption2)).foregroundStyle(.secondary)
                                }
                            }
                        }
                        Text(k.why).font(.ui(.caption2)).foregroundStyle(.secondary)
                        Text("Needs: \(k.evidenceNeeded)").font(.ui(.caption2)).foregroundStyle(.tertiary)
                    }
                    .padding(6)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
                bullets("Questionable assumptions", r.questionableAssumptions)
                bullets("What would change my mind", r.whatWouldChangeMyMind)
                if !r.preMortem.isEmpty {
                    Text("Pre-mortem").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                    Text(r.preMortem).font(.ui(.caption)).textSelection(.enabled)
                }
                bullets("Questions for the founders", r.questionsForFounders)
            }
        }
    }

    private func bullets(_ title: String, _ items: [String]) -> some View {
        Group {
            if !items.isEmpty {
                Text(title).font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•").font(.ui(.caption))
                        Text(item).font(.ui(.caption)).textSelection(.enabled)
                    }
                }
            }
        }
    }

    // MARK: Comparables

    private var comparablesBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let items = comparables?.items, !items.isEmpty {
                ForEach(items) { c in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Button {
                                if let company = store.companies.first(where: { $0.id == c.companyId }) {
                                    store.showCompany(company)
                                    openWindow.revealDesk()
                                }
                            } label: {
                                Text(c.companyName).font(.ui(.caption).weight(.semibold))
                            }
                            .buttonStyle(.plain)
                            if let v = c.verdict {
                                MacStatusPill(text: v.capitalized, color: v == "invest" ? .green : (v == "pass" ? .red : .orange))
                            }
                            if let r = c.retroVerdict, r != "still_right" {
                                Text(r.replacingOccurrences(of: "_", with: " ")).font(.ui(.caption2)).foregroundStyle(.orange)
                            }
                            Spacer()
                            Text("\(c.score)% overlap").font(.ui(.caption2).monospacedDigit()).foregroundStyle(.secondary)
                        }
                        if let e = c.explanation, !e.isEmpty {
                            Text(e).font(.ui(.caption2)).foregroundStyle(.secondary).lineLimit(2)
                        }
                        Text(c.why.joined(separator: " · ")).font(.ui(.caption2)).foregroundStyle(.tertiary).lineLimit(2)
                    }
                    .padding(6)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
            } else {
                Text("No comparable past decisions: nothing in the decision ledger shares this company's sector, stage or description terms.")
                    .font(.ui(.caption)).foregroundStyle(.secondary)
            }
            if let b = comparables?.basis { Text(b).font(.ui(.caption2)).foregroundStyle(.tertiary) }
        }
    }

    // MARK: References

    private var referencesBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let refs {
                    Text("\(refs.count) calls" + (refs.averageRating.map { String(format: " · avg %.1f / 5", $0) } ?? "") + " · \(refs.concernCount) concerns")
                        .font(.ui(.caption2)).foregroundStyle(.secondary)
                }
                Spacer()
                Button { form.showAddRef = true } label: { Label("Log call", systemImage: "phone.badge.plus") }
                    .controlSize(.small)
                    .disabled(!store.canWriteDesk)
            }
            ForEach(refs?.items ?? []) { r in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(r.contact).font(.ui(.caption).weight(.semibold))
                        Text(r.relationLabel).font(.ui(.caption2)).foregroundStyle(.secondary)
                        if let role = r.role, !role.isEmpty { Text("· \(role)").font(.ui(.caption2)).foregroundStyle(.secondary) }
                        if let rating = r.rating { Text(String(repeating: "★", count: rating)).font(.ui(.caption2)).foregroundStyle(.yellow) }
                        Spacer()
                        Text(r.callDate ?? "").font(.ui(.caption2)).foregroundStyle(.secondary)
                        if store.canWriteDesk {
                            Button { Task { await store.deleteReferenceCall(companyId, itemId: r.id) } } label: {
                                Image(systemName: "trash").font(.ui(.caption2)).foregroundStyle(.secondary)
                            }.buttonStyle(.plain)
                        }
                    }
                    ForEach(Array(r.strengths.enumerated()), id: \.offset) { _, s in Label(s, systemImage: "plus.circle").font(.ui(.caption2)).foregroundStyle(.green) }
                    ForEach(Array(r.concerns.enumerated()), id: \.offset) { _, s in Label(s, systemImage: "minus.circle").font(.ui(.caption2)).foregroundStyle(.red) }
                    ForEach(Array(r.quotes.enumerated()), id: \.offset) { _, q in Text("“\(q)”").font(.ui(.caption2).italic()).foregroundStyle(.secondary) }
                }
                .padding(6)
                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
            }
        }
    }
}

// MARK: - Bureau

/// ICRoomCard.vue on the Research Desk: the title, the four sections on a segmented control,
/// and each section as the website sets it.
extension MacICRoomView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("users", size: 16)
                    .foregroundStyle(ink.accent)
                MacBureauDeskCaption(text: "IC room", size: 15, weight: .semibold, lineHeight: 18.75, color: ink.label)
                Spacer(minLength: 0)
                if bureauLoading { MacBureauDeskSpinner() }
            }
            MacBureauDeskSegmented(
                selection: $form.tab,
                segments: [("votes", "Votes"), ("red", "Red team"), ("comps", "Comparables"), ("refs", "References")]
            )
            switch form.tab {
            case "red": bureauRedTeam(ink)
            case "comps": bureauComparables(ink)
            case "refs": bureauReferences(ink)
            default: bureauVotes(ink)
            }
        }
        .bureauDeskCard(padding: 10)
        .task(id: companyId) {
            if form != ICRoomForm() { form = ICRoomForm() }
            bureauLoading = true
            await store.loadICRoom(companyId)
            bureauLoading = false
        }
        .sheet(isPresented: $form.showAddRef) { MacReferenceCallSheet(companyId: companyId) }
        .sheet(isPresented: $form.showCloseSheet) {
            if let m = openMeeting { MacCloseMeetingSheet(companyId: companyId, meeting: m) }
        }
    }

    private func bureauLines(_ text: String, weight: Font.Weight = .regular, color: Color, maxLines: Int? = nil) -> some View {
        MacBureauWebParagraph(text: text, size: 10, weight: weight, lineHeight: 12.5, maxLines: maxLines)
            .foregroundStyle(color)
    }

    private func bureauButton(_ title: String, icon: String? = nil, kind: MacBureauDeskButtonStyle.Kind = .bordered, disabled: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            MacBureauDeskButtonLabel(title: title, icon: icon, iconSize: 12, size: .small)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: kind, size: .small))
        .disabled(disabled)
        .fixedSize()
    }

    private func bureauVoteTint(_ vote: String?, _ ink: MacBureauDeskInk) -> Color {
        vote == "invest" ? ink.green : (vote == "pass" ? ink.red : ink.orange)
    }

    // MARK: Votes

    @ViewBuilder
    private func bureauVotes(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let m = openMeeting {
                HStack(spacing: 8) {
                    MacBureauDeskCaption(text: m.title, color: ink.label)
                    MacBureauDeskCaption(text: "open · \(MacBureauMemoFormat.relative(m.createdAt))", color: ink.secondary)
                    Spacer(minLength: 0)
                    bureauButton("Close meeting…", disabled: !store.canEditMemo) { form.showCloseSheet = true }
                }
                if let t = m.tally {
                    HStack(spacing: 8) {
                        bureauTally("Invest", t.invest, ink.green)
                        bureauTally("Pass", t.pass, ink.red)
                        bureauTally("More work", t.moreWork, ink.orange)
                        Spacer(minLength: 0)
                        if let avg = t.averageConviction {
                            MacBureauDeskCaption(text: String(format: "conviction %.1f / 5", avg), color: ink.secondary)
                        }
                        if t.tied {
                            MacBureauDeskCaption(text: "Tied", color: ink.orange)
                        }
                    }
                    if t.total > 0 {
                        GeometryReader { geo in
                            let unit = max(0, geo.size.width - 2) / CGFloat(t.total)
                            HStack(spacing: 1) {
                                Rectangle().fill(ink.green).frame(width: unit * CGFloat(t.invest))
                                Rectangle().fill(ink.orange).frame(width: unit * CGFloat(t.moreWork))
                                Rectangle().fill(ink.red).frame(width: unit * CGFloat(t.pass))
                            }
                        }
                        .frame(height: 6)
                        .clipShape(Capsule())
                    }
                }
                ForEach(m.votes) { v in
                    HStack(spacing: 6) {
                        MacBureauDeskCaption(text: v.displayName, color: ink.label)
                        MacBureauDeskPill(text: v.label, tint: bureauVoteTint(v.vote, ink))
                        if let c = v.conviction {
                            MacBureauDeskCaption(text: "★\(c)", color: ink.secondary)
                        }
                        if let n = v.note, !n.isEmpty {
                            Text(n)
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(ink.secondary)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .bureauDeskLine(12.5, 10)
                        }
                        Spacer(minLength: 0)
                    }
                }
                MacBureauGridRule(color: ink.hairline)
                HStack(spacing: 8) {
                    MacBureauDeskSegmented(
                        selection: $form.vote,
                        segments: [("invest", "Invest"), ("more_work", "More work"), ("pass", "Pass")]
                    )
                    .frame(width: 210)
                    bureauStepper(ink)
                    TextField("", text: $form.voteNote, prompt: Text("Note").foregroundStyle(ink.tertiary))
                        .textFieldStyle(.plain)
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.label)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .frame(maxWidth: .infinity)
                        .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
                    bureauButton("Vote as \(store.memberName)", kind: .prominent, disabled: !store.canEditMemo) {
                        let target = companyId
                        Task {
                            if await store.castICVote(target, meetingId: m.id, vote: form.vote, conviction: form.conviction, note: form.voteNote), target == companyId {
                                form.voteNote = ""
                            }
                        }
                    }
                }
            } else {
                HStack(spacing: 8) {
                    MacBureauDeskCaption(
                        text: meetings.isEmpty ? "No IC meeting yet." : "No open meeting. \(meetings.count) past meeting(s).",
                        color: ink.secondary
                    )
                    Spacer(minLength: 0)
                    bureauButton("Open meeting", icon: "plus", disabled: !store.canEditMemo) {
                        Task { await store.openICMeeting(companyId, title: "", reportId: reportId) }
                    }
                }
                ForEach(meetings.prefix(3)) { m in
                    HStack(spacing: 6) {
                        MacBureauDeskCaption(text: m.title, color: ink.label)
                        if let t = m.tally {
                            MacBureauDeskCaption(text: "\(t.invest)/\(t.pass)/\(t.moreWork)", mono: true, color: ink.secondary)
                                .help("invest / pass / more work")
                        }
                        if m.decisionId != nil {
                            HStack(spacing: 4) {
                                MacBureauDeskIcon("badge-check", size: 12)
                                MacBureauDeskCaption(text: "Decision recorded", color: ink.green)
                            }
                            .foregroundStyle(ink.green)
                        }
                        Spacer(minLength: 0)
                        MacBureauDeskCaption(text: MacBureauMemoFormat.relative(m.closedAt ?? m.createdAt), color: ink.secondary)
                    }
                }
            }
        }
    }

    private func bureauTally(_ label: String, _ n: Int, _ tint: Color) -> some View {
        MacBureauDeskCaption(text: "\(n) \(label)", mono: true, color: tint)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .bureauBox(Capsule(), fill: tint.opacity(0.12))
    }

    /// ★n and a pair of − / + keys joined on one rim.
    private func bureauStepper(_ ink: MacBureauDeskInk) -> some View {
        HStack(spacing: 4) {
            MacBureauDeskCaption(text: "★\(form.conviction)", mono: true, color: ink.label)
                .frame(width: 24, alignment: .leading)
            HStack(spacing: 0) {
                Button {
                    form.conviction = max(1, form.conviction - 1)
                } label: {
                    MacBureauDeskIcon("minus", size: 10).frame(width: 18, height: 18).contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                .disabled(form.conviction <= 1)
                Rectangle().fill(ink.hairline).frame(width: 1, height: 18)
                Button {
                    form.conviction = min(5, form.conviction + 1)
                } label: {
                    MacBureauDeskIcon("plus", size: 10).frame(width: 18, height: 18).contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                .disabled(form.conviction >= 5)
            }
            .foregroundStyle(ink.label)
            .background(ink.raised)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .circular))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .circular).strokeBorder(ink.label(0.2), lineWidth: 1))
        }
    }

    // MARK: Red team

    @ViewBuilder
    private func bureauRedTeam(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                if let rt = redTeam, let at = rt.generatedAt, rt.result != nil {
                    bureauLines("Argued \(MacBureauMemoFormat.relative(at)) · \(rt.memoBlocksUsed) memo blocks · \(rt.referenceConcerns) reference concerns", color: ink.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    bureauLines("Claude argues the other side from the memo, contradicted evidence and reference-call concerns.", color: ink.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Button {
                    guard MacTokenConfirm.ask() else { return }
                    Task { await store.runRedTeam(companyId) }
                } label: {
                    if redTeam?.isRunning == true {
                        HStack(spacing: 4) {
                            MacBureauDeskSpinner(size: 11)
                            MacBureauDeskButtonLabel(title: "Arguing…", size: .small)
                        }
                    } else {
                        MacBureauDeskButtonLabel(title: redTeam?.result == nil ? "Run red team" : "Re-run", icon: "flag", iconSize: 12, size: .small)
                    }
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(redTeam?.isRunning == true || !store.canRunTasks)
                .fixedSize()
            }
            if let err = redTeam?.error, redTeam?.result == nil {
                bureauLines(err, color: ink.red)
            }
            if let r = redTeam?.result {
                MacBureauWebParagraph(text: r.counterThesis, size: 12, lineHeight: 15.6)
                    .foregroundStyle(ink.label)
                    .textSelection(.enabled)
                MacBureauDeskCaption(text: "Kill risks", color: ink.secondary)
                ForEach(Array(r.killRisks.enumerated()), id: \.offset) { _, k in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle()
                                .fill(k.severity == "high" ? ink.red : (k.severity == "medium" ? ink.orange : ink.secondary))
                                .frame(width: 7, height: 7)
                            MacBureauDeskCaption(text: k.risk, color: ink.label)
                            if let s = k.memoSection, !s.isEmpty {
                                if let findText {
                                    Button {
                                        findText.wrappedValue = MacFindRequest(text: s)
                                    } label: {
                                        MacBureauDeskCaption(text: "§ \(s)", color: ink.accent)
                                    }
                                    .buttonStyle(MacBureauFlatButtonStyle())
                                } else {
                                    MacBureauDeskCaption(text: "§ \(s)", color: ink.secondary)
                                }
                            }
                        }
                        bureauLines(k.why, color: ink.secondary)
                        bureauLines("Needs: \(k.evidenceNeeded)", color: ink.tertiary)
                    }
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.05))
                }
                bureauBullets("Questionable assumptions", r.questionableAssumptions, ink)
                bureauBullets("What would change my mind", r.whatWouldChangeMyMind, ink)
                if !r.preMortem.isEmpty {
                    MacBureauDeskCaption(text: "Pre-mortem", color: ink.secondary)
                    bureauLines(r.preMortem, color: ink.label)
                        .textSelection(.enabled)
                }
                bureauBullets("Questions for the founders", r.questionsForFounders, ink)
            }
        }
    }

    @ViewBuilder
    private func bureauBullets(_ title: String, _ items: [String], _ ink: MacBureauDeskInk) -> some View {
        if !items.isEmpty {
            MacBureauDeskCaption(text: title, color: ink.secondary)
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 6) {
                    MacBureauDeskCaption(text: "•", color: ink.label)
                    bureauLines(item, color: ink.label)
                        .textSelection(.enabled)
                }
            }
        }
    }

    // MARK: Comparables

    @ViewBuilder
    private func bureauComparables(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let items = comparables?.items, !items.isEmpty {
                ForEach(items) { c in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Button {
                                if let company = store.companies.first(where: { $0.id == c.companyId }) {
                                    store.showCompany(company)
                                    openWindow.revealDesk()
                                }
                            } label: {
                                MacBureauDeskCaption(text: c.companyName, color: ink.label)
                            }
                            .buttonStyle(MacBureauFlatButtonStyle())
                            if let v = c.verdict {
                                MacBureauDeskPill(text: v.prefix(1).uppercased() + v.dropFirst(), tint: bureauVoteTint(v == "watch" ? "more_work" : v, ink))
                            }
                            if let r = c.retroVerdict, r != "still_right" {
                                MacBureauDeskCaption(text: r.replacingOccurrences(of: "_", with: " "), color: ink.orange)
                            }
                            Spacer(minLength: 0)
                            MacBureauDeskCaption(text: "\(c.score)% overlap", mono: true, color: ink.secondary)
                        }
                        if let e = c.explanation, !e.isEmpty {
                            bureauLines(e, color: ink.secondary, maxLines: 2)
                        }
                        if !c.why.isEmpty {
                            bureauLines(c.why.joined(separator: " · "), color: ink.tertiary, maxLines: 2)
                        }
                    }
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.05))
                }
            } else {
                bureauLines(
                    "No comparable past decisions: nothing in the decision ledger shares this company's sector, stage or description terms.",
                    color: ink.secondary
                )
            }
            if let b = comparables?.basis, !b.isEmpty {
                bureauLines(b, color: ink.tertiary)
            }
        }
    }

    // MARK: References

    @ViewBuilder
    private func bureauReferences(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                if let refs {
                    MacBureauDeskCaption(
                        text: "\(refs.count) calls" + (refs.averageRating.map { String(format: " · avg %.1f / 5", $0) } ?? "") + " · \(refs.concernCount) concerns",
                        color: ink.secondary
                    )
                }
                Spacer(minLength: 0)
                bureauButton("Log call", icon: "phone", disabled: !store.canWriteDesk) { form.showAddRef = true }
            }
            ForEach(refs?.items ?? []) { r in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        MacBureauDeskCaption(text: r.contact, color: ink.label)
                        MacBureauDeskCaption(text: r.relationLabel, color: ink.secondary)
                        if let role = r.role, !role.isEmpty {
                            MacBureauDeskCaption(text: "· \(role)", color: ink.secondary)
                        }
                        if let rating = r.rating, rating > 0 {
                            MacBureauDeskCaption(text: String(repeating: "★", count: rating), color: ink.yellow)
                        }
                        Spacer(minLength: 0)
                        MacBureauDeskCaption(text: r.callDate ?? "", color: ink.secondary)
                        if store.canWriteDesk {
                            Button {
                                Task { await store.deleteReferenceCall(companyId, itemId: r.id) }
                            } label: {
                                MacBureauDeskIcon("trash-2", size: 12)
                                    .foregroundStyle(ink.secondary)
                                    .padding(2)
                            }
                            .buttonStyle(MacBureauFlatButtonStyle())
                            .help("Delete")
                        }
                    }
                    ForEach(Array(r.strengths.enumerated()), id: \.offset) { _, s in
                        HStack(spacing: 4) {
                            MacBureauDeskIcon("circle-plus", size: 12)
                            bureauLines(s, color: ink.green)
                        }
                        .foregroundStyle(ink.green)
                    }
                    ForEach(Array(r.concerns.enumerated()), id: \.offset) { _, s in
                        HStack(spacing: 4) {
                            MacBureauDeskIcon("circle-minus", size: 12)
                            bureauLines(s, color: ink.red)
                        }
                        .foregroundStyle(ink.red)
                    }
                    ForEach(Array(r.quotes.enumerated()), id: \.offset) { _, q in
                        Text("“\(q)”")
                            .font(BSHType.bureauSans(10).italic())
                            .foregroundStyle(ink.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.05))
            }
        }
    }
}

// MARK: - Sheets

struct MacReferenceCallSheet: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var contact = ""
    @State private var role = ""
    @State private var relation = "customer"
    @State private var callDate = Date()
    @State private var rating = 0
    @State private var strengths = ""
    @State private var concerns = ""
    @State private var quotes = ""
    @State private var notes = ""
    @State private var saving = false

    var body: some View {
        VStack(spacing: 0) {
            HStack { Text("Log reference call").font(.ui(.headline)); Spacer(); Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction) }
                .padding(16)
            Divider()
            Form {
                TextField("Contact name", text: $contact)
                TextField("Their role / company", text: $role)
                Picker("Relation", selection: $relation) {
                    Text("Customer").tag("customer")
                    Text("Former employee").tag("former_employee")
                    Text("Investor").tag("investor")
                    Text("Partner").tag("partner")
                    Text("Founder peer").tag("founder_peer")
                    Text("Other").tag("other")
                }
                DatePicker("Call date", selection: $callDate, displayedComponents: .date)
                Picker("Rating", selection: $rating) {
                    Text("—").tag(0)
                    ForEach(1...5, id: \.self) { Text(String(repeating: "★", count: $0)).tag($0) }
                }
                TextField("Strengths (one per line)", text: $strengths, axis: .vertical).lineLimit(2...4)
                TextField("Concerns (one per line)", text: $concerns, axis: .vertical).lineLimit(2...4)
                TextField("Verbatim quotes (one per line)", text: $quotes, axis: .vertical).lineLimit(2...4)
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...5)
            }
            .formStyle(.grouped)
            Divider()
            HStack {
                Spacer()
                Button {
                    saving = true
                    let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
                    let fields: [String: Any?] = [
                        "contact": contact, "role": role, "relation": relation, "call_date": df.string(from: callDate),
                        "rating": rating == 0 ? nil : rating, "strengths": strengths, "concerns": concerns, "quotes": quotes, "notes": notes,
                    ]
                    Task {
                        if await store.addReferenceCall(companyId, fields: fields) { dismiss() }
                        saving = false
                    }
                } label: { if saving { ProgressView().controlSize(.small) } else { Text("Save") } }
                .buttonStyle(.dsProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving || contact.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(12)
        }
        .frame(width: 480, height: 560)
    }
}

struct MacCloseMeetingSheet: View {
    let companyId: String
    let meeting: MacICMeeting
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var record = true
    @State private var explanation = ""
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Close \(meeting.title)").font(.ui(.headline))
            if let t = meeting.tally {
                Text("\(t.invest) invest · \(t.pass) pass · \(t.moreWork) more work" + (t.majority.map { " → majority: \($0.replacingOccurrences(of: "_", with: " "))" } ?? (t.leading.map { " → leading: \($0.replacingOccurrences(of: "_", with: " ")) (no majority)" } ?? " → tied")))
                    .font(.ui(.caption)).foregroundStyle(.secondary)
            }
            Toggle("Record the majority as the decision (invest / pass / watch)", isOn: $record)
                .disabled(meeting.tally?.majority == nil)
                .help(meeting.tally?.majority == nil ? "A decision needs more than half of the votes on one verdict" : "")
            TextField("Explanation for the decision record (optional; defaults to the tally)", text: $explanation, axis: .vertical)
                .lineLimit(3...6)
                .textFieldStyle(.dsField)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button {
                    saving = true
                    Task {
                        if await store.closeICMeeting(companyId, meetingId: meeting.id, recordDecision: record && meeting.tally?.majority != nil, explanation: explanation) { dismiss() }
                        saving = false
                    }
                } label: { if saving { ProgressView().controlSize(.small) } else { Text("Close meeting") } }
                .buttonStyle(.dsProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving)
            }
        }
        .padding(20)
        .frame(width: 460)
    }
}
