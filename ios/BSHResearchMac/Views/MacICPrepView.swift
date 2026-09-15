import SwiftUI

/// IC Prep card for a company dossier: readiness gates, reviewable areas, ranked risk cards,
/// tool runs, and the approval that unlocks an analysis-backed memo.
///
/// Loading a session creates one on the server, so the card is collapsed until asked.
struct MacICPrepView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @State private var loadError: String?
    @State private var reviewArea: MacReadinessArea?
    @State private var approving = false
    @State private var showRisks = true

    private var analysis: MacMemoAnalysis? { store.analysisByCompany[company.id] }
    private var busy: Bool { store.analysisBusy.contains(company.id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("IC prep", systemImage: "checklist")
                                    .font(.dsHeadline)
                if let readiness = analysis?.readiness {
                    Text("\(readiness.score ?? 0)/\(readiness.total ?? 0) gates")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(readiness.readyForMemo == true ? Color.green : Color.orange)
                }
                Spacer()
                if busy { ProgressView().controlSize(.small) }
                if analysis == nil {
                    Button(busy ? "Loading…" : (loadError == nil ? "Load IC prep" : "Retry")) {
                        Task { await load() }
                    }
                    .disabled(busy)
                    .controlSize(.small)
                } else {
                    Button {
                        Task { await load() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .controlSize(.small)
                    .disabled(busy)
                }
            }

            if let analysis {
                content(analysis)
            } else if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.red)
            } else if !busy {
                Text("Readiness gates, risk cards and analysis tools for the memo. Loading opens a Memo Studio session for this company.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .appleGlassCard()
        .task(id: company.id) {
            if loadError != nil { loadError = nil }
        }
        .sheet(item: $reviewArea) { area in
            MacReadinessReviewSheet(companyId: company.id, area: area)
                .environmentObject(store)
        }
    }

    private func load() async {
        let id = company.id
        loadError = nil
        store.error = nil
        await store.loadMemoAnalysis(id)
        guard id == company.id, store.analysisByCompany[id] == nil, !store.analysisBusy.contains(id) else { return }
        loadError = store.error ?? "Could not load IC prep."
    }

    @ViewBuilder
    private func content(_ analysis: MacMemoAnalysis) -> some View {
        // Gates
        if let readiness = analysis.readiness {
            VStack(alignment: .leading, spacing: 6) {
                ProgressView(value: readiness.pct ?? 0)
                    .tint(readiness.readyForMemo == true ? .green : .orange)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 6) {
                    ForEach(readiness.gates) { gate in
                        HStack(spacing: 6) {
                            Image(systemName: gate.isDone ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(gate.isDone ? Color.green : Color.secondary)
                            Text(gate.label ?? gate.id).font(.caption)
                            Spacer(minLength: 0)
                        }
                    }
                }
            }
        }

        // Blockers with a tool to run
        let blockers = analysis.readiness?.approvalBlockers ?? []
        if !blockers.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Blocking approval").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(blockers) { blocker in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: blocker.severity == "high" ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                            .foregroundStyle(blocker.severity == "high" ? Color.red : Color.orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(blocker.label ?? blocker.id).font(.caption.weight(.medium))
                            if let reason = blocker.reason, !reason.isEmpty {
                                Text(reason).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if let tool = blocker.tool, let def = analysis.tools.first(where: { $0.name == tool }) {
                            runButton(def)
                        } else if blocker.kind == "additional_area",
                                  let area = analysis.additionalAreas.first(where: { $0.id == blocker.id }) {
                            Button("Review…") { reviewArea = area }
                                .controlSize(.small)
                                .disabled(!store.can("memo:edit"))
                        }
                    }
                    .padding(8)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
            }
        }

        // Reviewable areas
        if !analysis.additionalAreas.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Areas to review").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(analysis.additionalAreas) { area in
                    HStack(spacing: 8) {
                        Image(systemName: area.isOpen ? "circle" : (area.status == "waived" ? "minus.circle.fill" : "checkmark.circle.fill"))
                            .foregroundStyle(area.isOpen ? Color.secondary : (area.status == "waived" ? Color.orange : Color.green))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(area.area ?? area.id).font(.caption.weight(.medium))
                            if let why = area.whyItMatters, !why.isEmpty {
                                Text(why).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                            }
                            if let rationale = area.rationale, !rationale.isEmpty {
                                Text("↳ \(rationale)").font(.caption2).foregroundStyle(.tertiary).lineLimit(2)
                            }
                        }
                        Spacer()
                        Button(area.isOpen ? "Review…" : "Edit…") { reviewArea = area }
                            .controlSize(.small)
                            .disabled(!store.can("memo:edit"))
                    }
                }
            }
        }

        // Risk cards
        if !analysis.rankedRisks.isEmpty {
            DisclosureGroup(isExpanded: $showRisks) {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(analysis.rankedRisks.prefix(8)) { risk in
                        HStack(alignment: .top, spacing: 8) {
                            MacStatusPill(text: (risk.severity ?? "medium").capitalized, color: risk.severity == "high" ? .red : (risk.severity == "low" ? .secondary : .orange))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(risk.title ?? risk.id).font(.caption.weight(.semibold))
                                if let why = risk.whyItMatters ?? risk.description, !why.isEmpty {
                                    Text(why).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                            Spacer()
                            Text((risk.status ?? "unresearched").replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption2)
                                .foregroundStyle(risk.isOpen ? Color.orange : Color.green)
                        }
                        .padding(6)
                        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                    }
                }
                .padding(.top, 4)
            } label: {
                Text("Risk cards (\(analysis.risks.count), \(analysis.risks.filter(\.isOpen).count) open)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }

        // Tools
        VStack(alignment: .leading, spacing: 6) {
            Text("Analysis tools").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(analysis.tools.filter { !$0.isHidden }) { tool in
                HStack(spacing: 8) {
                    Image(systemName: tool.isDone ? "checkmark.circle.fill" : (tool.isRunning ? "circle.dotted" : (tool.status == "error" ? "xmark.circle" : "circle")))
                        .foregroundStyle(tool.isDone ? Color.green : (tool.status == "error" ? Color.red : Color.secondary))
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(tool.label ?? tool.name).font(.caption.weight(.medium))
                            if tool.critical == true {
                                Text("core").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        if let summary = tool.error ?? tool.summary, !summary.isEmpty {
                            Text(summary).font(.caption2).foregroundStyle(tool.error == nil ? .secondary : Color.red).lineLimit(1)
                        }
                    }
                    Spacer()
                    if tool.isRunning {
                        ProgressView().controlSize(.mini)
                    }
                    runButton(tool)
                }
            }
        }

        Divider()

        // Approval → memo
        HStack(spacing: 10) {
            if analysis.approvedForMemo {
                Label("Approved for memo \(MacTimeFormat.relative(analysis.approvedAt))", systemImage: "checkmark.seal.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.green)
                Spacer()
                Button {
                    store.requestNewReport(for: company)
                } label: {
                    Label("Generate IC Memo", systemImage: "doc.badge.plus")
                }
                .buttonStyle(.borderedProminent)
                .disabled(!store.canRunTasks)
            } else {
                Text(analysis.readiness?.readyForApproval == true
                     ? "All gates pass — approve to unlock the analysis-backed memo."
                     : "Clear the blockers above before approving.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(approving ? "Approving…" : "Approve for memo") {
                    approving = true
                    Task {
                        await store.approveMemoAnalysis(companyId: company.id)
                        approving = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(approving || !store.can("memo:edit") || analysis.readiness?.readyForApproval != true)
            }
        }
    }

    private func runButton(_ tool: MacMemoTool) -> some View {
        Button(tool.isDone ? "Re-run" : "Run") {
            Task { await store.runMemoTool(companyId: company.id, tool: tool.name) }
        }
        .controlSize(.small)
        .disabled(tool.isRunning || !store.canRunTasks)
        .help(tool.description ?? "")
    }
}

/// Mark an additional area reviewed or waived — the server insists on a rationale.
struct MacReadinessReviewSheet: View {
    let companyId: String
    let area: MacReadinessArea
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var status = "reviewed"
    @State private var rationale = ""
    @State private var saving = false
    @State private var errorText: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(area.area ?? area.id).font(.headline)
            if let why = area.whyItMatters, !why.isEmpty {
                Text(why).font(.callout).foregroundStyle(.secondary)
            }
            LabeledContent("Status") {
                GlassSegmentedPicker("Status", selection: $status, segments: ["reviewed": "Reviewed", "waived": "Waived", "open": "Open"])
            }
            Text("Rationale").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            TextEditor(text: $rationale)
                .font(.body)
                .frame(minHeight: 100)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.2)))
            if let errorText {
                Text(errorText).font(.caption).foregroundStyle(.red)
            }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button(saving ? "Saving…" : "Save") {
                    saving = true
                    errorText = nil
                    let trimmed = rationale.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task {
                        store.error = nil
                        await store.reviewReadinessArea(companyId: companyId, areaId: area.id, status: status, rationale: trimmed)
                        saving = false
                        let stored = store.analysisByCompany[companyId]?.additionalAreas.first { $0.id == area.id }
                        let saved = store.error == nil && stored?.status == status && (stored?.rationale ?? "") == trimmed
                        if saved {
                            dismiss()
                        } else {
                            errorText = store.error ?? "Could not save the review. It may not have been recorded; try again."
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving || (status != "open" && rationale.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
            }
        }
        .padding(20)
        .frame(width: 460)
        .onChange(of: status) { _, _ in errorText = nil }
        .onChange(of: rationale) { _, _ in errorText = nil }
        .onAppear {
            status = area.status ?? "reviewed"
            if status == "open" { status = "reviewed" }
            rationale = area.rationale ?? ""
        }
    }
}
