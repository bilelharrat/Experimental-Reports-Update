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

    var body: some View {
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
                    Text(m.title).font(.caption.weight(.semibold))
                    Text("open · \(MacTimeFormat.relative(m.createdAt))").font(.caption2).foregroundStyle(.secondary)
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
                            Text(String(format: "conviction %.1f / 5", avg)).font(.caption2).foregroundStyle(.secondary)
                        }
                        if t.tied { Text("Tied").font(.caption2.weight(.semibold)).foregroundStyle(.orange) }
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
                        Text(v.displayName).font(.caption.weight(.medium))
                        MacStatusPill(text: v.label, color: v.vote == "invest" ? .green : (v.vote == "pass" ? .red : .orange))
                        if let c = v.conviction { Text("★\(c)").font(.caption2).foregroundStyle(.secondary) }
                        if let n = v.note, !n.isEmpty { Text(n).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
                        Spacer()
                    }
                }
                Divider()
                HStack(spacing: 8) {
                    GlassSegmentedPicker("Vote", selection: $form.vote, segments: ["invest": "Invest", "more_work": "More work", "pass": "Pass"])
                        .controlSize(.small).frame(width: 200)
                    Stepper("★\(form.conviction)", value: $form.conviction, in: 1...5).controlSize(.small).frame(width: 70)
                    TextField("Note", text: $form.voteNote).textFieldStyle(.roundedBorder).controlSize(.small)
                    Button("Vote as \(store.memberName)") {
                        let target = companyId
                        Task {
                            if await store.castICVote(target, meetingId: m.id, vote: form.vote, conviction: form.conviction, note: form.voteNote), target == companyId { form.voteNote = "" }
                        }
                    }
                    .controlSize(.small)
                    .buttonStyle(.borderedProminent)
                    .disabled(!store.canEditMemo)
                }
            } else {
                HStack {
                    Text(meetings.isEmpty ? "No IC meeting yet." : "No open meeting. \(meetings.count) past meeting(s).")
                        .font(.caption).foregroundStyle(.secondary)
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
                        Text(m.title).font(.caption)
                        if let t = m.tally {
                            Text("\(t.invest)/\(t.pass)/\(t.moreWork)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                                .help("invest / pass / more work")
                        }
                        if m.decisionId != nil { Label("Decision recorded", systemImage: "checkmark.seal").font(.caption2).foregroundStyle(.green) }
                        Spacer()
                        Text(MacTimeFormat.relative(m.closedAt ?? m.createdAt)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func tallyPill(_ label: String, _ n: Int, _ color: Color) -> some View {
        Text("\(n) \(label)")
            .font(.caption2.weight(.semibold).monospacedDigit())
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
                        .font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("Claude argues the other side from the memo, contradicted evidence and reference-call concerns.")
                        .font(.caption2).foregroundStyle(.secondary)
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
                Text(err).font(.caption).foregroundStyle(.red)
            }
            if let r = redTeam?.result {
                Text(r.counterThesis).font(.callout).textSelection(.enabled)
                Text("Kill risks").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(Array(r.killRisks.enumerated()), id: \.offset) { _, k in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(k.severity == "high" ? Color.red : (k.severity == "medium" ? Color.orange : Color.secondary)).frame(width: 7, height: 7)
                            Text(k.risk).font(.caption.weight(.semibold))
                            if let s = k.memoSection, !s.isEmpty {
                                if let findText {
                                    Button { findText.wrappedValue = MacFindRequest(text: s) } label: { Text("§ \(s)").font(.caption2) }.buttonStyle(.plain).foregroundStyle(Color.accentColor)
                                } else {
                                    Text("§ \(s)").font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                        Text(k.why).font(.caption2).foregroundStyle(.secondary)
                        Text("Needs: \(k.evidenceNeeded)").font(.caption2).foregroundStyle(.tertiary)
                    }
                    .padding(6)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
                bullets("Questionable assumptions", r.questionableAssumptions)
                bullets("What would change my mind", r.whatWouldChangeMyMind)
                if !r.preMortem.isEmpty {
                    Text("Pre-mortem").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text(r.preMortem).font(.caption).textSelection(.enabled)
                }
                bullets("Questions for the founders", r.questionsForFounders)
            }
        }
    }

    private func bullets(_ title: String, _ items: [String]) -> some View {
        Group {
            if !items.isEmpty {
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•").font(.caption)
                        Text(item).font(.caption).textSelection(.enabled)
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
                                Text(c.companyName).font(.caption.weight(.semibold))
                            }
                            .buttonStyle(.plain)
                            if let v = c.verdict {
                                MacStatusPill(text: v.capitalized, color: v == "invest" ? .green : (v == "pass" ? .red : .orange))
                            }
                            if let r = c.retroVerdict, r != "still_right" {
                                Text(r.replacingOccurrences(of: "_", with: " ")).font(.caption2).foregroundStyle(.orange)
                            }
                            Spacer()
                            Text("\(c.score)% overlap").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                        }
                        if let e = c.explanation, !e.isEmpty {
                            Text(e).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                        }
                        Text(c.why.joined(separator: " · ")).font(.caption2).foregroundStyle(.tertiary).lineLimit(2)
                    }
                    .padding(6)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
            } else {
                Text("No comparable past decisions: nothing in the decision ledger shares this company's sector, stage or description terms.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let b = comparables?.basis { Text(b).font(.caption2).foregroundStyle(.tertiary) }
        }
    }

    // MARK: References

    private var referencesBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let refs {
                    Text("\(refs.count) calls" + (refs.averageRating.map { String(format: " · avg %.1f / 5", $0) } ?? "") + " · \(refs.concernCount) concerns")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Button { form.showAddRef = true } label: { Label("Log call", systemImage: "phone.badge.plus") }
                    .controlSize(.small)
                    .disabled(!store.canWriteDesk)
            }
            ForEach(refs?.items ?? []) { r in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(r.contact).font(.caption.weight(.semibold))
                        Text(r.relationLabel).font(.caption2).foregroundStyle(.secondary)
                        if let role = r.role, !role.isEmpty { Text("· \(role)").font(.caption2).foregroundStyle(.secondary) }
                        if let rating = r.rating { Text(String(repeating: "★", count: rating)).font(.caption2).foregroundStyle(.yellow) }
                        Spacer()
                        Text(r.callDate ?? "").font(.caption2).foregroundStyle(.secondary)
                        if store.canWriteDesk {
                            Button { Task { await store.deleteReferenceCall(companyId, itemId: r.id) } } label: {
                                Image(systemName: "trash").font(.caption2).foregroundStyle(.secondary)
                            }.buttonStyle(.plain)
                        }
                    }
                    ForEach(Array(r.strengths.enumerated()), id: \.offset) { _, s in Label(s, systemImage: "plus.circle").font(.caption2).foregroundStyle(.green) }
                    ForEach(Array(r.concerns.enumerated()), id: \.offset) { _, s in Label(s, systemImage: "minus.circle").font(.caption2).foregroundStyle(.red) }
                    ForEach(Array(r.quotes.enumerated()), id: \.offset) { _, q in Text("“\(q)”").font(.caption2.italic()).foregroundStyle(.secondary) }
                }
                .padding(6)
                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
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
            HStack { Text("Log reference call").font(.headline); Spacer(); Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction) }
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
                .buttonStyle(.borderedProminent)
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
            Text("Close \(meeting.title)").font(.headline)
            if let t = meeting.tally {
                Text("\(t.invest) invest · \(t.pass) pass · \(t.moreWork) more work" + (t.majority.map { " → majority: \($0.replacingOccurrences(of: "_", with: " "))" } ?? (t.leading.map { " → leading: \($0.replacingOccurrences(of: "_", with: " ")) (no majority)" } ?? " → tied")))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Toggle("Record the majority as the decision (invest / pass / watch)", isOn: $record)
                .disabled(meeting.tally?.majority == nil)
                .help(meeting.tally?.majority == nil ? "A decision needs more than half of the votes on one verdict" : "")
            TextField("Explanation for the decision record (optional; defaults to the tally)", text: $explanation, axis: .vertical)
                .lineLimit(3...6)
                .textFieldStyle(.roundedBorder)
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
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving)
            }
        }
        .padding(20)
        .frame(width: 460)
    }
}
