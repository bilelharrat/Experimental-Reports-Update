import SwiftUI

/// ⌘⇧O — memo on the left, thesis spine / risks / evidence / decision on the right.
/// Open several side by side, or project one in the IC room.
struct MacICReviewWindowView: View {
    let request: MacICReviewRequest
    @EnvironmentObject private var store: MacAppStore

    @State private var verdict = "watch"
    @State private var explanation = ""
    @State private var decidedAt = Date()
    @State private var submitting = false
    @State private var saved = false
    @State private var findText: MacFindRequest?
    @State private var showDecision = false

    private var company: MacCompany? {
        store.companies.first { $0.id == request.companyId }
    }

    private var analysis: MacMemoAnalysis? { store.analysisByCompany[request.companyId] }
    private var evidence: MacEvidenceMatrix? { store.evidenceByCompany[request.companyId] }

    var body: some View {
        HSplitView {
            MacMemoWindowView(request: MacMemoWindowRequest(reportId: request.reportId, language: request.language), findText: $findText)
                .frame(minWidth: 520, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)

            sidePanel
                .frame(minWidth: 320, idealWidth: 380, maxWidth: 520)
                .layoutPriority(0)
        }
        .frame(minWidth: 1100, minHeight: 700)
        .navigationTitle("IC Review — \(company?.title ?? request.companyId)")
        .focusedSceneValue(\.deskTarget, MacDeskCommandTarget(
            companyId: request.companyId,
            reportId: request.reportId,
            recordDecision: { showDecision = true },
            openICReview: {}
        ))
        .sheet(isPresented: $showDecision) {
            if let company {
                MacDecisionSheet(company: company, seedReportId: request.reportId)
                    .environmentObject(store)
            }
        }
        .task {
            await store.loadMemoAnalysis(request.companyId)
            await store.loadEvidence(request.companyId)
            await store.loadDecisions(for: [request.companyId])
        }
    }

    private var sidePanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let company {
                    HStack(spacing: 10) {
                        MacMonogram(name: company.title, size: 34)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(company.title).font(.headline)
                            Text(company.subtitle).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Label(store.stage(for: company.id).rawValue, systemImage: store.stage(for: company.id).systemImage)
                            .font(.caption.weight(.semibold))
                    }
                }

                if let spine = analysis?.thesisSpine, !spine.isEmpty {
                    section("Thesis spine", systemImage: "point.3.connected.trianglepath.dotted") {
                        if let logic = spine.recommendationLogic, !logic.isEmpty {
                            Text(logic).font(.callout).textSelection(.enabled)
                        }
                        claimList("Investment highlights", spine.investmentHighlights, color: .green)
                        claimList("Investment risks", spine.investmentRisks, color: .red)
                        if !spine.riskValuationSensitivities.isEmpty {
                            Text("Valuation sensitivities").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            ForEach(spine.riskValuationSensitivities) { row in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(row.sensitivity ?? "").font(.caption.weight(.medium))
                                    if let impact = row.downsideImpact, !impact.isEmpty {
                                        Text(impact).font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                                .padding(6)
                                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                } else if store.analysisBusy.contains(request.companyId) {
                    ProgressView("Loading thesis…").controlSize(.small)
                } else {
                    section("Thesis spine", systemImage: "point.3.connected.trianglepath.dotted") {
                        Text("No thesis spine yet — run the Thesis Spine tool from IC Prep on the dossier.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                if let analysis, !analysis.rankedRisks.isEmpty {
                    section("Top risks", systemImage: "exclamationmark.shield") {
                        ForEach(analysis.rankedRisks.prefix(5)) { risk in
                            HStack(alignment: .top, spacing: 8) {
                                MacStatusPill(text: (risk.severity ?? "medium").capitalized, color: risk.severity == "high" ? .red : .orange)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(risk.title ?? risk.id).font(.caption.weight(.semibold))
                                    if let why = risk.whyItMatters ?? risk.description, !why.isEmpty {
                                        Text(why).font(.caption2).foregroundStyle(.secondary).lineLimit(3)
                                    }
                                }
                            }
                        }
                    }
                }

                if let company {
                    MacThesisTrackerView(company: company, onFind: { claim in findText = MacFindRequest(text: claim) })
                }

                if let evidence {
                    section("Evidence", systemImage: "doc.text.magnifyingglass") {
                        HStack(spacing: 12) {
                            evidenceStat("Supported", evidence.count("supported"), .green)
                            evidenceStat("Partial", evidence.count("partial"), .teal)
                            evidenceStat("Mixed", evidence.count("mixed"), .orange)
                            evidenceStat("Contradicted", evidence.count("contradicted"), .red)
                            evidenceStat("Missing", evidence.count("missing"), .secondary)
                        }
                        ForEach(evidence.claims.filter { $0.status == "contradicted" || $0.status == "mixed" }.prefix(4)) { claim in
                            VStack(alignment: .leading, spacing: 2) {
                                Label(claim.claim, systemImage: "exclamationmark.bubble")
                                    .font(.caption)
                                    .foregroundStyle(Color.red)
                                    .lineLimit(2)
                                if let contra = claim.contradictingEvidence.first?.excerpt {
                                    Text(contra).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                        }
                    }
                }

                MacNumberLintView(companyId: request.companyId, findText: $findText)

                MacICRoomView(companyId: request.companyId, reportId: request.reportId, findText: $findText)

                MacCommentsView(companyId: request.companyId, target: MacCommentTarget(kind: "report", ref: request.reportId, label: "This memo"))

                section("Decision", systemImage: "checkmark.seal") {
                    LabeledContent("Verdict") {
                        GlassSegmentedPicker("Verdict", selection: $verdict, segments: ["invest": "Invest", "watch": "Watch", "pass": "Pass"])
                    }
                    DatePicker("Decided", selection: $decidedAt, displayedComponents: .date)
                        .controlSize(.small)
                    TextEditor(text: $explanation)
                        .font(.callout)
                        .frame(minHeight: 90)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.2)))
                    HStack {
                        Text("Based on this memo").font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        if saved {
                            Label("Recorded", systemImage: "checkmark").font(.caption).foregroundStyle(Color.green)
                        }
                        Button(submitting ? "Saving…" : "Record") {
                            submitting = true
                            saved = false
                            Task {
                                let ok = await store.recordDecision(
                                    companyId: request.companyId,
                                    verdict: verdict,
                                    explanation: explanation.trimmingCharacters(in: .whitespacesAndNewlines),
                                    decidedAt: MacDecisionDate.dayInstant(decidedAt),
                                    reportId: request.reportId
                                )
                                submitting = false
                                if ok {
                                    saved = true
                                    explanation = ""
                                }
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(submitting || !store.canRunTasks || explanation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    MacDecisionTimeline(companyId: request.companyId)
                }
            }
            .padding(14)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func section<Content: View>(_ title: String, systemImage: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
            content()
        }
        .padding(10)
        .appleGlassCard()
    }

    private func claimList(_ title: String, _ claims: [MacThesisClaim], color: Color) -> some View {
        Group {
            if !claims.isEmpty {
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(claims) { claim in
                    HStack(alignment: .top, spacing: 6) {
                        Circle().fill(color).frame(width: 6, height: 6).padding(.top, 5)
                        VStack(alignment: .leading, spacing: 1) {
                            Button {
                                findText = MacFindRequest(text: claim.claim ?? "")
                            } label: {
                                Text(claim.claim ?? "").font(.caption.weight(.medium)).multilineTextAlignment(.leading)
                            }
                            .buttonStyle(.link)
                            .help("Jump to this claim in the memo")
                            if let detail = claim.detail, !detail.isEmpty {
                                Text(detail).font(.caption2).foregroundStyle(.secondary).lineLimit(3)
                            }
                            if claim.needsStrongerEvidence == true {
                                Text("needs stronger evidence").font(.caption2).foregroundStyle(Color.orange)
                            }
                        }
                    }
                }
            }
        }
    }

    private func evidenceStat(_ label: String, _ value: Int, _ color: Color) -> some View {
        VStack(spacing: 1) {
            Text("\(value)").font(.subheadline.monospacedDigit().weight(.bold)).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
