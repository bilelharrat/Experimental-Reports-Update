import SwiftUI

enum MacDecisionDate {
    /// The picked calendar day as midnight UTC, so the stored `decided_at` reads as that day everywhere.
    static func dayInstant(_ date: Date) -> Date {
        // Read the day with a Gregorian calendar in the user's zone: a Buddhist or Japanese
        // system calendar would otherwise hand back its own year (2569, 8) for the UTC date.
        var local = Calendar(identifier: .gregorian)
        local.timeZone = .current
        let comps = local.dateComponents([.year, .month, .day], from: date)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC") ?? .current
        return utc.date(from: comps) ?? date
    }
}

/// ⌘D — put an Invest / Pass / Watch call on the record, optionally tied to a memo.
struct MacDecisionSheet: View {
    let company: MacCompany
    var seedReportId: String?

    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var verdict = "watch"
    @State private var explanation = ""
    @State private var decidedAt = Date()
    @State private var reportId: String = ""
    @State private var submitting = false
    @State private var error: String?

    private var reports: [MacReport] {
        store.reports(for: company.id).filter { $0.isComplete || $0.canOpen }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Record decision").font(.headline)
                    Text(company.title).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            .background(.ultraThinMaterial)

            Divider()

            Form {
                Section {
                    LabeledContent("Verdict") {
                        GlassSegmentedPicker(
                            "Verdict", selection: $verdict, options: ["invest", "watch", "pass"],
                            title: { ["invest": "Invest", "watch": "Watch", "pass": "Pass"][$0] ?? $0 },
                            systemImage: { ["invest": "checkmark.circle.fill", "watch": "eye", "pass": "xmark.circle"][$0] }
                        )
                    }

                    DatePicker("Decided", selection: $decidedAt, displayedComponents: .date)

                    Picker("Based on memo", selection: $reportId) {
                        Text("None").tag("")
                        ForEach(reports) { report in
                            Text("\(report.displayTitle) · \(report.dateLabel)").tag(report.id)
                        }
                    }
                }

                Section("Rationale (required — this is the firm's record)") {
                    TextEditor(text: $explanation)
                        .font(.body)
                        .frame(minHeight: 140)
                }

                if let error {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Text("Recorded as \(store.session?.displayName ?? "you")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(submitting ? "Saving…" : "Record \(verdictTitle)") {
                    Task { await submit() }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(submitting || explanation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
            .background(.ultraThinMaterial)
        }
        .frame(width: 520, height: 460)
        .onAppear {
            if let seedReportId { reportId = seedReportId }
            else if let latest = reports.first { reportId = latest.id }
        }
    }

    private var verdictTitle: String {
        switch verdict {
        case "invest": return "Invest"
        case "pass": return "Pass"
        default: return "Watch"
        }
    }

    private func submit() async {
        submitting = true
        error = nil
        defer { submitting = false }
        let ok = await store.recordDecision(
            companyId: company.id,
            verdict: verdict,
            explanation: explanation.trimmingCharacters(in: .whitespacesAndNewlines),
            decidedAt: MacDecisionDate.dayInstant(decidedAt),
            reportId: reportId.isEmpty ? nil : reportId
        )
        if ok {
            dismiss()
        } else {
            error = store.error ?? "Could not record the decision."
        }
    }
}

/// Decision history with the retrospectives the tracking sync writes.
struct MacDecisionTimeline: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore
    @State private var confirmDelete: MacDecision?

    private var decisions: [MacDecision] {
        store.decisionsByCompany[companyId] ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if decisions.isEmpty {
                Text("No decision on record yet. Press ⌘D to record Invest, Pass or Watch.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(decisions) { decision in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        MacStatusPill(text: decision.verdictLabel, color: color(for: decision.verdict))
                        Text(String((decision.decidedAt ?? decision.createdAt ?? "").prefix(10)))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                        if let by = decision.createdBy, !by.isEmpty {
                            Text("· \(by)").font(.caption).foregroundStyle(.secondary)
                        }
                        if let rid = decision.reportId, let report = store.report(for: rid) {
                            Button {
                                store.openReportWindow(report)
                            } label: {
                                Label(report.displayTitle, systemImage: "doc.text")
                                    .font(.caption)
                            }
                            .buttonStyle(.link)
                        }
                        Spacer()
                        Button {
                            confirmDelete = decision
                        } label: {
                            Image(systemName: "trash").font(.caption)
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                        .disabled(!store.canRunTasks)
                        .help("Delete this decision record")
                    }
                    Text(decision.explanation)
                        .font(.callout)
                        .textSelection(.enabled)
                    ForEach(decision.retrospectives) { retro in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: retro.verdict == "still_right" ? "checkmark.circle" : (retro.verdict == "looks_wrong" ? "xmark.octagon" : "questionmark.circle"))
                                .foregroundStyle(retro.verdict == "still_right" ? Color.green : (retro.verdict == "looks_wrong" ? Color.red : Color.orange))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(retro.label) · \(MacTimeFormat.relative(retro.assessedAt))")
                                    .font(.caption.weight(.semibold))
                                if let text = retro.rationaleEn, !text.isEmpty {
                                    Text(text).font(.caption).foregroundStyle(.secondary)
                                }
                                if !retro.newsTitles.isEmpty {
                                    Text(retro.newsTitles.prefix(2).joined(separator: " · "))
                                        .font(.caption2).foregroundStyle(.tertiary).lineLimit(2)
                                }
                            }
                        }
                        .padding(8)
                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                    }
                }
                .padding(10)
                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .confirmationDialog(
            "Delete this decision?",
            isPresented: Binding(get: { confirmDelete != nil }, set: { if !$0 { confirmDelete = nil } }),
            presenting: confirmDelete
        ) { decision in
            Button("Delete", role: .destructive) {
                Task { await store.deleteDecision(companyId: companyId, decisionId: decision.id) }
            }
        } message: { decision in
            Text("\(decision.verdictLabel) recorded \(String((decision.decidedAt ?? "").prefix(10))) will be removed from the record.")
        }
        .task(id: companyId) {
            if store.decisionsByCompany[companyId] == nil {
                await store.loadDecisions(for: [companyId])
            }
        }
    }

    private func color(for verdict: String) -> Color {
        switch verdict {
        case "invest": return .green
        case "pass": return .red
        default: return .orange
        }
    }
}
