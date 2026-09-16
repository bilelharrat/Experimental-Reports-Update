import SwiftUI

public struct MacDecisionSheet: View {
    public let company: MacCompany
    public var seedReportId: String?

    @EnvironmentObject private var store: ResearchDeskStore
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

    public init(company: MacCompany, seedReportId: String? = nil) {
        self.company = company
        self.seedReportId = seedReportId
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("Verdict") {
                    Picker("Verdict", selection: $verdict) {
                        Text("Invest").tag("invest")
                        Text("Watch").tag("watch")
                        Text("Pass").tag("pass")
                    }
                    .pickerStyle(.segmented)

                    DatePicker("Decided", selection: $decidedAt, displayedComponents: .date)

                    if !reports.isEmpty {
                        Picker("Based on memo", selection: $reportId) {
                            Text("None").tag("")
                            ForEach(reports) { report in
                                Text(report.displayTitle).tag(report.id)
                            }
                        }
                    }
                }

                Section("Rationale (firm record)") {
                    TextEditor(text: $explanation)
                        .frame(minHeight: 120)
                }

                if let error {
                    Section {
                        Text(error).font(.caption).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Record Decision")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(submitting ? "Saving…" : "Save") {
                        Task { await submit() }
                    }
                    .disabled(submitting || explanation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .onAppear {
                if let seedReportId { reportId = seedReportId }
                else if let latest = reports.first { reportId = latest.id }
            }
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
            decidedAt: decidedAt,
            reportId: reportId.isEmpty ? nil : reportId
        )
        if ok {
            dismiss()
        } else {
            error = "Could not record decision."
        }
    }
}

public struct MacDecisionTimeline: View {
    public let companyId: String
    @EnvironmentObject private var store: ResearchDeskStore

    public init(companyId: String) {
        self.companyId = companyId
    }

    private var decisions: [MacDecision] {
        store.decisionsByCompany[companyId] ?? []
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MacCardHeader("Decisions", subtitle: "Firm voting record and investment thesis retrospectives.", systemImage: "checkmark.seal")

            if decisions.isEmpty {
                Text("No decisions on record yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(8)
            } else {
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
                            Spacer()
                        }
                        Text(decision.explanation)
                            .font(.callout)
                            .textSelection(.enabled)

                        ForEach(decision.retrospectives) { retro in
                            HStack(alignment: .top, spacing: 6) {
                                Image(systemName: retro.verdict == "still_right" ? "checkmark.circle" : (retro.verdict == "looks_wrong" ? "xmark.octagon" : "questionmark.circle"))
                                    .foregroundStyle(retro.verdict == "still_right" ? Color.green : (retro.verdict == "looks_wrong" ? Color.red : Color.orange))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("\(retro.label)")
                                        .font(.caption.weight(.semibold))
                                    if let text = retro.rationaleEn, !text.isEmpty {
                                        Text(text).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .padding(6)
                            .appleGlassTile(cornerRadius: 6)
                        }
                    }
                    .padding(10)
                    .appleGlassTile(cornerRadius: 10)
                }
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: companyId) {
            if store.decisionsByCompany[companyId] == nil {
                await store.fetchDecisions(for: companyId)
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
