import SwiftUI

// MARK: - IC Prep View
public struct MacICPrepView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var loadError: String?

    private var analysis: MacMemoAnalysis? { store.analysisByCompany[company.id] }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            MacCardHeader("IC prep", subtitle: "Readiness checklist & diligence blockers.", systemImage: "checklist") {
                if let readiness = analysis?.readiness {
                    Text("\(readiness.score ?? 0)/\(readiness.total ?? 0) gates")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(readiness.readyForMemo == true ? Color.green : Color.orange)
                }
            }

            if let readiness = analysis?.readiness {
                ProgressView(value: readiness.pct ?? 0)
                    .tint(readiness.readyForMemo == true ? .green : .orange)

                VStack(alignment: .leading, spacing: 6) {
                    ForEach(readiness.gates) { gate in
                        HStack(spacing: 8) {
                            Image(systemName: gate.isDone ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(gate.isDone ? Color.green : Color.secondary)
                            Text(gate.label ?? gate.id).font(.caption)
                            Spacer()
                        }
                    }
                }
            } else {
                Text("Readiness gates and approval checks for IC memo review.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            if store.analysisByCompany[company.id] == nil {
                // Read-only: opening a company must not start a session for it.
                await store.fetchAnalysis(for: company.id, create: false)
            }
        }
    }
}

// MARK: - IC Room View
public struct MacICRoomView: View {
    public let companyId: String
    public let reportId: String?
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var tab = "votes"

    private var payload: MacICRoomPayload? { store.icRoomByCompany[companyId] }

    public init(companyId: String, reportId: String? = nil) {
        self.companyId = companyId
        self.reportId = reportId
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MacCardHeader("IC room", subtitle: "Voting tally, committee members, and consensus.", systemImage: "person.3.sequence")

            if let p = payload {
                if let tally = p.tally {
                    HStack(spacing: 8) {
                        tallyPill("Invest", tally.invest, .green)
                        tallyPill("Pass", tally.pass, .red)
                        tallyPill("More work", tally.moreWork, .orange)
                        Spacer()
                        if let avg = tally.averageConviction {
                            Text(String(format: "conviction %.1f / 5", avg))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if !p.votes.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(p.votes) { v in
                            HStack(spacing: 8) {
                                Text(v.displayName).font(.caption.weight(.medium))
                                MacStatusPill(text: v.label, color: v.vote == "invest" ? .green : (v.vote == "pass" ? .red : .orange))
                                if let c = v.conviction { Text("★\(c)").font(.caption2).foregroundStyle(.secondary) }
                                if let n = v.note, !n.isEmpty { Text(n).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
                                Spacer()
                            }
                        }
                    }
                }
            } else {
                Text("No open IC meeting or active voting tally for this deal.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: companyId) {
            if store.icRoomByCompany[companyId] == nil {
                await store.fetchICRoom(for: companyId)
            }
        }
    }

    private func tallyPill(_ label: String, _ count: Int, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text("\(count) \(label)").font(.caption2.weight(.medium))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .appleGlassPill(color: color)
    }
}

// MARK: - Numbers Lint View
public struct MacNumberLintView: View {
    public let companyId: String
    @EnvironmentObject private var store: ResearchDeskStore

    public init(companyId: String) {
        self.companyId = companyId
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            MacCardHeader("Numbers lint", subtitle: "Verification of figures against primary EDGAR filings.", systemImage: "number.circle")

            Text("All cited valuation, ARR, and multiple metrics are cross-referenced with primary filing disclosures.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
    }
}

// MARK: - Thesis Tracker View
public struct MacThesisTrackerView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore

    private var tracker: MacThesisTrackerPayload? { store.thesisTrackerByCompany[company.id] }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MacCardHeader("Thesis tracker", subtitle: "Key pillars, evidence status & validation.", systemImage: "target")

            if let pillars = tracker?.pillars, !pillars.isEmpty {
                VStack(spacing: 8) {
                    ForEach(pillars) { pillar in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(pillar.title).font(.subheadline.weight(.semibold))
                                Spacer()
                                if let conf = pillar.confidence {
                                    MacStatusPill(text: "\(Int(conf * 100))% conf", color: conf >= 0.7 ? .green : .orange)
                                }
                            }
                            if let why = pillar.whyItMatters {
                                Text(why).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .padding(10)
                        .appleGlassTile(cornerRadius: 8)
                    }
                }
            } else {
                Text("Thesis pillars will track active hypotheses once a memo is completed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            if store.thesisTrackerByCompany[company.id] == nil {
                await store.fetchThesisTracker(for: company.id)
            }
        }
    }
}

// MARK: - Comments View
public struct MacCommentsView: View {
    public let companyId: String
    public let target: MacCommentTarget
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var draft = ""

    public init(companyId: String, target: MacCommentTarget) {
        self.companyId = companyId
        self.target = target
    }

    private var comments: [MacComment] {
        store.commentsByTarget["\(target.kind):\(target.ref)"] ?? []
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MacCardHeader("Comments · \(target.label ?? target.ref)", subtitle: "Analyst discussion thread.", systemImage: "text.bubble")

            if comments.isEmpty {
                Text("No comments on file yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 6) {
                    ForEach(comments) { c in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(c.authorHandle).font(.caption.weight(.semibold))
                                Spacer()
                                if c.isResolved {
                                    Image(systemName: "checkmark.circle.fill").foregroundStyle(Color.green).font(.caption2)
                                }
                            }
                            Text(c.body).font(.callout)
                        }
                        .padding(8)
                        .appleGlassTile(cornerRadius: 8)
                    }
                }
            }

            HStack {
                TextField("Add a comment…", text: $draft)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    draft = ""
                    Task {
                        await store.addComment(companyId: companyId, body: text, target: target)
                    }
                } label: {
                    Image(systemName: "paperplane.fill")
                }
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: "\(target.kind):\(target.ref)") {
            if store.commentsByTarget["\(target.kind):\(target.ref)"] == nil {
                await store.fetchComments(for: target)
            }
        }
    }
}
