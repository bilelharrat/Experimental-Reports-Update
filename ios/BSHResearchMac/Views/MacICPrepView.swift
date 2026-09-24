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

    @Environment(\.bureauResearchDesk) private var bureauDesk
    @Environment(\.colorScheme) private var colorScheme

    private var analysis: MacMemoAnalysis? { store.analysisByCompany[company.id] }
    private var busy: Bool { store.analysisBusy.contains(company.id) }

    var body: some View {
        if BSHDesign.active == .bureau && bureauDesk {
            bureauBody
        } else {
            glassBody
        }
    }

    private var glassBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("IC prep", systemImage: "checklist")
                                    .font(.dsHeadline)
                if let readiness = analysis?.readiness {
                    Text("\(readiness.score ?? 0)/\(readiness.total ?? 0) gates")
                        .font(.ui(.caption).monospacedDigit().weight(.semibold))
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
                Text(loadError).font(.ui(.caption)).foregroundStyle(.red)
            } else if !busy {
                Text("Readiness gates, risk cards and analysis tools for the memo. Loading opens a Memo Studio session for this company.")
                    .font(.ui(.caption))
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
                            Text(gate.label ?? gate.id).font(.ui(.caption))
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
                Text("Blocking approval").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(blockers) { blocker in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: blocker.severity == "high" ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                            .foregroundStyle(blocker.severity == "high" ? Color.red : Color.orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(blocker.label ?? blocker.id).font(.ui(.caption).weight(.medium))
                            if let reason = blocker.reason, !reason.isEmpty {
                                Text(reason).font(.ui(.caption)).foregroundStyle(.secondary)
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
                Text("Areas to review").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(analysis.additionalAreas) { area in
                    HStack(spacing: 8) {
                        Image(systemName: area.isOpen ? "circle" : (area.status == "waived" ? "minus.circle.fill" : "checkmark.circle.fill"))
                            .foregroundStyle(area.isOpen ? Color.secondary : (area.status == "waived" ? Color.orange : Color.green))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(area.area ?? area.id).font(.ui(.caption).weight(.medium))
                            if let why = area.whyItMatters, !why.isEmpty {
                                Text(why).font(.ui(.caption2)).foregroundStyle(.secondary).lineLimit(2)
                            }
                            if let rationale = area.rationale, !rationale.isEmpty {
                                Text("↳ \(rationale)").font(.ui(.caption2)).foregroundStyle(.tertiary).lineLimit(2)
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
                                Text(risk.title ?? risk.id).font(.ui(.caption).weight(.semibold))
                                if let why = risk.whyItMatters ?? risk.description, !why.isEmpty {
                                    Text(why).font(.ui(.caption2)).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                            Spacer()
                            Text((risk.status ?? "unresearched").replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.ui(.caption2))
                                .foregroundStyle(risk.isOpen ? Color.orange : Color.green)
                        }
                        .padding(6)
                        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                    }
                }
                .padding(.top, 4)
            } label: {
                Text("Risk cards (\(analysis.risks.count), \(analysis.risks.filter(\.isOpen).count) open)")
                    .font(.ui(.caption).weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }

        // Tools
        VStack(alignment: .leading, spacing: 6) {
            Text("Analysis tools").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
            ForEach(analysis.tools.filter { !$0.isHidden }) { tool in
                HStack(spacing: 8) {
                    Image(systemName: tool.isDone ? "checkmark.circle.fill" : (tool.isRunning ? "circle.dotted" : (tool.status == "error" ? "xmark.circle" : "circle")))
                        .foregroundStyle(tool.isDone ? Color.green : (tool.status == "error" ? Color.red : Color.secondary))
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(tool.label ?? tool.name).font(.ui(.caption).weight(.medium))
                            if tool.critical == true {
                                Text("core").font(.ui(.caption2)).foregroundStyle(.secondary)
                            }
                        }
                        if let summary = tool.error ?? tool.summary, !summary.isEmpty {
                            Text(summary).font(.ui(.caption2)).foregroundStyle(tool.error == nil ? .secondary : Color.red).lineLimit(1)
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
                    .font(.ui(.caption).weight(.semibold))
                    .foregroundStyle(Color.green)
                Spacer()
                Button {
                    store.requestNewReport(for: company)
                } label: {
                    Label("Generate IC Memo", systemImage: "doc.badge.plus")
                }
                .buttonStyle(.dsProminent)
                .disabled(!store.canRunTasks)
            } else {
                Text(analysis.readiness?.readyForApproval == true
                     ? "All gates pass — approve to unlock the analysis-backed memo."
                     : "Clear the blockers above before approving.")
                    .font(.ui(.caption))
                    .foregroundStyle(.secondary)
                Spacer()
                Button(approving ? "Approving…" : "Approve for memo") {
                    approving = true
                    Task {
                        await store.approveMemoAnalysis(companyId: company.id)
                        approving = false
                    }
                }
                .buttonStyle(.dsProminent)
                .disabled(approving || !store.can("memo:edit") || analysis.readiness?.readyForApproval != true)
            }
        }
    }

    private func runButton(_ tool: MacMemoTool) -> some View {
        Button(tool.isDone ? "Re-run" : "Run") {
            guard MacTokenConfirm.ask() else { return }
            Task { await store.runMemoTool(companyId: company.id, tool: tool.name) }
        }
        .controlSize(.small)
        .disabled(tool.isRunning || !store.canRunTasks)
        .help(tool.description ?? "")
    }
}

// MARK: - Bureau

/// ICPrepCard.vue on the Research Desk: the header with the gate count and Load / refresh,
/// then — once loaded — the gates on a thin bar, what blocks approval, the areas to review,
/// the ranked risk cards, the analysis tools and the approval that unlocks the memo.
extension MacICPrepView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("list-checks", size: 16)
                    .foregroundStyle(ink.accent)
                MacBureauDeskCaption(text: "IC prep", size: 15, weight: .semibold, lineHeight: 18.75, color: ink.label)
                if let readiness = analysis?.readiness {
                    MacBureauDeskCaption(
                        text: "\(readiness.score ?? 0)/\(readiness.total ?? 0) gates",
                        mono: true,
                        color: readiness.readyForMemo == true ? ink.green : ink.orange
                    )
                }
                Spacer(minLength: 0)
                if busy { MacBureauDeskSpinner() }
                if analysis == nil {
                    Button {
                        Task { await load() }
                    } label: {
                        MacBureauDeskButtonLabel(title: busy ? "Loading…" : (loadError == nil ? "Load IC prep" : "Retry"), size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    .disabled(busy)
                } else {
                    Button {
                        Task { await load() }
                    } label: {
                        MacBureauDeskIcon("rotate-cw", size: 12)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    .disabled(busy)
                    .help("Refresh")
                }
            }

            if let analysis {
                bureauContent(analysis, ink: ink)
            } else if let loadError {
                MacBureauWebParagraph(text: loadError, size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.red)
            } else if !busy {
                MacBureauWebParagraph(
                    text: "Readiness gates, risk cards and analysis tools for the memo. Loading opens a Memo Studio session for this company.",
                    size: 10,
                    lineHeight: 12.5
                )
                .foregroundStyle(ink.secondary)
            }
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            if loadError != nil { loadError = nil }
        }
        .sheet(item: $reviewArea) { area in
            MacReadinessReviewSheet(companyId: company.id, area: area)
                .environmentObject(store)
        }
    }

    /// A caption that wraps (`.mac-t-caption10`), clamped as the website clamps it.
    private func bureauLines(_ text: String, weight: Font.Weight = .regular, color: Color, maxLines: Int? = nil) -> some View {
        MacBureauWebParagraph(text: text, size: 10, weight: weight, lineHeight: 12.5, maxLines: maxLines)
            .foregroundStyle(color)
    }

    private func bureauSmallButton(_ title: String, disabled: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            MacBureauDeskButtonLabel(title: title, size: .small)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
        .disabled(disabled)
        .fixedSize()
    }

    @ViewBuilder
    private func bureauContent(_ analysis: MacMemoAnalysis, ink: MacBureauDeskInk) -> some View {
        // Gates on a thin bar, two to a row.
        if let readiness = analysis.readiness {
            VStack(alignment: .leading, spacing: 6) {
                MacBureauDeskMeter(fraction: readiness.pct ?? 0, tint: readiness.readyForMemo == true ? ink.green : ink.orange)
                MacBureauDeskGrid(columns: 2, spacing: 6) {
                    ForEach(readiness.gates) { gate in
                        HStack(spacing: 6) {
                            MacBureauDeskIcon(gate.isDone ? "circle-check" : "circle", size: 14)
                                .foregroundStyle(gate.isDone ? ink.green : ink.secondary)
                            Text(gate.label ?? gate.id)
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(ink.label)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .bureauDeskLine(12.5, 10)
                            Spacer(minLength: 0)
                        }
                    }
                }
            }
        }

        // What blocks approval, each with the tool that clears it.
        let blockers = analysis.readiness?.approvalBlockers ?? []
        if !blockers.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                MacBureauDeskCaption(text: "Blocking approval", color: ink.secondary)
                ForEach(blockers) { blocker in
                    HStack(alignment: .top, spacing: 8) {
                        MacBureauDeskIcon(blocker.severity == "high" ? "triangle-alert" : "circle-alert", size: 14)
                            .foregroundStyle(blocker.severity == "high" ? ink.red : ink.orange)
                            .padding(.top, 1)
                        VStack(alignment: .leading, spacing: 2) {
                            bureauLines(blocker.label ?? blocker.id, color: ink.label)
                            if let reason = blocker.reason, !reason.isEmpty {
                                bureauLines(reason, color: ink.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if let tool = blocker.tool, let def = analysis.tools.first(where: { $0.name == tool }) {
                            bureauRunButton(def)
                        } else if blocker.kind == "additional_area",
                                  let area = analysis.additionalAreas.first(where: { $0.id == blocker.id }) {
                            bureauSmallButton("Review…", disabled: !store.can("memo:edit")) { reviewArea = area }
                        }
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.05))
                }
            }
        }

        // Areas a reviewer signs off or waives.
        if !analysis.additionalAreas.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                MacBureauDeskCaption(text: "Areas to review", color: ink.secondary)
                ForEach(analysis.additionalAreas) { area in
                    HStack(spacing: 8) {
                        MacBureauDeskIcon(area.isOpen ? "circle" : (area.status == "waived" ? "circle-minus" : "circle-check"), size: 14)
                            .foregroundStyle(area.isOpen ? ink.secondary : (area.status == "waived" ? ink.orange : ink.green))
                        VStack(alignment: .leading, spacing: 1) {
                            bureauLines(area.area ?? area.id, color: ink.label)
                            if let why = area.whyItMatters, !why.isEmpty {
                                bureauLines(why, color: ink.secondary, maxLines: 2)
                            }
                            if let rationale = area.rationale, !rationale.isEmpty {
                                bureauLines("↳ \(rationale)", color: ink.tertiary, maxLines: 2)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        bureauSmallButton(area.isOpen ? "Review…" : "Edit…", disabled: !store.can("memo:edit")) { reviewArea = area }
                    }
                }
            }
        }

        // The ranked risk cards, behind a disclosure.
        if !analysis.rankedRisks.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Button {
                    showRisks.toggle()
                } label: {
                    HStack(spacing: 4) {
                        MacBureauDeskIcon(showRisks ? "chevron-down" : "chevron-right", size: 12)
                        MacBureauDeskCaption(
                            text: "Risk cards (\(analysis.risks.count), \(analysis.risks.filter(\.isOpen).count) open)",
                            color: ink.secondary
                        )
                    }
                    .foregroundStyle(ink.secondary)
                    .contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                if showRisks {
                    ForEach(analysis.rankedRisks.prefix(8)) { risk in
                        HStack(alignment: .top, spacing: 8) {
                            let severity = (risk.severity ?? "medium").lowercased()
                            MacBureauDeskPill(
                                text: severity.prefix(1).uppercased() + severity.dropFirst(),
                                tint: severity == "high" ? ink.red : (severity == "low" ? ink.secondary : ink.orange)
                            )
                            VStack(alignment: .leading, spacing: 2) {
                                bureauLines(risk.title ?? risk.id, color: ink.label)
                                if let why = risk.whyItMatters ?? risk.description, !why.isEmpty {
                                    bureauLines(why, color: ink.secondary, maxLines: 2)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            let status = (risk.status ?? "unresearched").replacingOccurrences(of: "_", with: " ")
                            MacBureauDeskCaption(
                                text: status.prefix(1).uppercased() + status.dropFirst(),
                                color: risk.isOpen ? ink.orange : ink.green
                            )
                        }
                        .padding(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.04))
                    }
                }
            }
        }

        // The analysis tools, each with Run / Re-run.
        VStack(alignment: .leading, spacing: 6) {
            MacBureauDeskCaption(text: "Analysis tools", color: ink.secondary)
            ForEach(analysis.tools.filter { !$0.isHidden }) { tool in
                HStack(spacing: 8) {
                    MacBureauDeskIcon(
                        tool.isDone ? "circle-check" : (tool.isRunning ? "circle-dashed" : (tool.status == "error" ? "circle-x" : "circle")),
                        size: 14
                    )
                    .foregroundStyle(tool.isDone ? ink.green : (tool.status == "error" ? ink.red : ink.secondary))
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            MacBureauDeskCaption(text: tool.label ?? tool.name, color: ink.label)
                            if tool.critical == true {
                                MacBureauDeskCaption(text: "core", color: ink.secondary)
                            }
                        }
                        if let summary = tool.error ?? tool.summary, !summary.isEmpty {
                            Text(summary)
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(tool.error == nil ? ink.secondary : ink.red)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .bureauDeskLine(12.5, 10)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if tool.isRunning { MacBureauDeskSpinner(size: 11) }
                    bureauRunButton(tool)
                }
            }
        }

        MacBureauGridRule(color: ink.hairline)

        // Approval, then the memo it unlocks.
        HStack(spacing: 10) {
            if analysis.approvedForMemo {
                HStack(spacing: 6) {
                    MacBureauDeskIcon("badge-check", size: 14)
                    MacBureauDeskCaption(
                        text: "Approved for memo \(MacBureauMemoFormat.relative(analysis.approvedAt))",
                        color: ink.green
                    )
                }
                .foregroundStyle(ink.green)
                Spacer(minLength: 0)
                Button {
                    store.requestNewReport(for: company)
                } label: {
                    MacBureauDeskButtonLabel(title: "Generate IC Memo", icon: "file-plus-corner", iconSize: 14)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent))
                .disabled(!store.canRunTasks)
            } else {
                bureauLines(
                    analysis.readiness?.readyForApproval == true
                        ? "All gates pass — approve to unlock the analysis-backed memo."
                        : "Clear the blockers above before approving.",
                    color: ink.secondary
                )
                .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    approving = true
                    Task {
                        await store.approveMemoAnalysis(companyId: company.id)
                        approving = false
                    }
                } label: {
                    MacBureauDeskButtonLabel(title: approving ? "Approving…" : "Approve for memo")
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent))
                .disabled(approving || !store.can("memo:edit") || analysis.readiness?.readyForApproval != true)
                .fixedSize()
            }
        }
    }

    /// Run or re-run a tool — each run spends tokens, so it asks first, as the other designs do.
    private func bureauRunButton(_ tool: MacMemoTool) -> some View {
        bureauSmallButton(tool.isDone ? "Re-run" : "Run", disabled: tool.isRunning || !store.canRunTasks) {
            guard MacTokenConfirm.ask() else { return }
            Task { await store.runMemoTool(companyId: company.id, tool: tool.name) }
        }
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
            Text(area.area ?? area.id).font(.ui(.headline))
            if let why = area.whyItMatters, !why.isEmpty {
                Text(why).font(.ui(.callout)).foregroundStyle(.secondary)
            }
            LabeledContent("Status") {
                GlassSegmentedPicker("Status", selection: $status, segments: ["reviewed": "Reviewed", "waived": "Waived", "open": "Open"])
            }
            Text("Rationale").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
            TextEditor(text: $rationale)
                .font(.ui(.body))
                .frame(minHeight: 100)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.2)))
            if let errorText {
                Text(errorText).font(.ui(.caption)).foregroundStyle(.red)
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
                .buttonStyle(.dsProminent)
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
