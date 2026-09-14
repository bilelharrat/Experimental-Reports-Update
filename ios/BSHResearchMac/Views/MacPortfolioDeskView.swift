import SwiftUI

/// Companies with a standing Invest / Watch decision: tracked news by impact, recommended
/// auto-runs, and a "needs re-underwriting" filter driven by decision retrospectives.
struct MacPortfolioDeskView: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var selectedId: String?
    @State private var reunderwritingOnly = false
    @State private var lastExecute: MacAutoRunExecuteResult?

    private var entries: [(company: MacCompany, decision: MacDecision)] {
        let all = store.portfolioEntries
        guard reunderwritingOnly else { return all }
        return all.filter { needsReunderwriting($0.company.id, $0.decision) }
    }

    private func needsReunderwriting(_ companyId: String, _ decision: MacDecision) -> Bool {
        if decision.needsReunderwriting { return true }
        if let updates = store.trackingByCompany[companyId], updates.items.contains(where: { $0.impact == "high" }) { return true }
        return false
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Toggle("Needs re-underwriting", isOn: $reunderwritingOnly)
                        .toggleStyle(.checkbox)
                    Spacer()
                    Text("\(entries.count) positions")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)

                Divider()

                List(selection: $selectedId) {
                    if entries.isEmpty {
                        Text(store.portfolioEntries.isEmpty
                             ? "No Invest or Watch decisions yet. Record one with ⌘D from the Pipeline or a dossier."
                             : "Nothing needs re-underwriting.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(entries, id: \.company.id) { entry in
                        HStack(spacing: 10) {
                            MacMonogram(name: entry.company.title, size: 30)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(entry.company.title).font(.body.weight(.medium))
                                HStack(spacing: 6) {
                                    MacStatusPill(text: entry.decision.verdictLabel, color: entry.decision.verdict == "invest" ? .green : .orange)
                                    if let retro = entry.decision.latestRetrospective, retro.verdict != "still_right" {
                                        Text(retro.label).font(.caption2).foregroundStyle(Color.red)
                                    }
                                    if let updates = store.trackingByCompany[entry.company.id] {
                                        let high = updates.items.filter { $0.impact == "high" }.count
                                        if high > 0 {
                                            Text("\(high) high-impact").font(.caption2).foregroundStyle(Color.red)
                                        }
                                    }
                                }
                            }
                            Spacer()
                            if needsReunderwriting(entry.company.id, entry.decision) {
                                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Color.orange)
                            }
                        }
                        .padding(.vertical, 2)
                        .tag(entry.company.id)
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            }
            .frame(minWidth: 280, idealWidth: 320, maxWidth: 420)
            .layoutPriority(0)

            detail
                .frame(minWidth: 480, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)
        }
        .task {
            if store.rollup == nil { await store.loadPipeline() }
            if selectedId == nil { selectedId = entries.first?.company.id }
            for entry in store.portfolioEntries where store.trackingByCompany[entry.company.id] == nil {
                await store.loadTracking(entry.company.id, sync: false)
            }
        }
        .onChange(of: selectedId) { _, id in
            guard let id else { return }
            if let company = store.companies.first(where: { $0.id == id }) { store.selectCompany(company) }
            if store.trackingByCompany[id] == nil {
                Task { await store.loadTracking(id, sync: false) }
            }
        }
    }

    @ViewBuilder
    private var detail: some View {
        if let id = selectedId, let company = store.companies.first(where: { $0.id == id }) {
            let updates = store.trackingByCompany[id]
            let busy = store.trackingBusy.contains(id)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(company.title).font(.title2.weight(.bold))
                            Text(company.subtitle).font(.subheadline).foregroundStyle(.secondary)
                            if let synced = updates?.lastSyncedAt {
                                Text("Tracked news synced \(MacTimeFormat.relative(synced))").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if busy { ProgressView().controlSize(.small) }
                        Button {
                            Task { await store.loadTracking(id, sync: true) }
                        } label: {
                            Label("Sync news", systemImage: "arrow.triangle.2.circlepath")
                        }
                        .disabled(busy || !store.canRunTasks)
                        .help("Pull fresh tracked news and re-assess the standing decision")
                        Button {
                            store.showCompany(company)
                        } label: {
                            Label("Dossier", systemImage: "building.columns")
                        }
                        Button {
                            store.requestDecision(for: company)
                        } label: {
                            Label("Re-decide", systemImage: "checkmark.seal")
                        }
                        .disabled(!store.canRunTasks)
                    }
                    .padding()
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))

                    // Recommended auto-run
                    if let auto = updates?.recommendedAutoRun {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Recommended: \(auto.actionLabel)", systemImage: "sparkles")
                                .font(.headline)
                            if !auto.newsTitles.isEmpty {
                                Text("Triggered by: " + auto.newsTitles.prefix(3).joined(separator: " · "))
                                    .font(.caption).foregroundStyle(.secondary).lineLimit(3)
                            }
                            HStack {
                                Button {
                                    Task { lastExecute = await store.executeAutoRun(companyId: id, autoRun: auto) }
                                } label: {
                                    Label("Execute", systemImage: "play.fill")
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(!store.canRunTasks)
                                if let result = lastExecute {
                                    Text(result.executed ? "Started — follow it in the Jobs blotter." : result.reasonLabel)
                                        .font(.caption)
                                        .foregroundStyle(result.executed ? Color.green : Color.orange)
                                }
                            }
                        }
                        .padding()
                        .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                    }

                    // Decision + retrospectives
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Decision record").font(.headline)
                        MacDecisionTimeline(companyId: id)
                    }
                    .padding()
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))

                    // Tracked news by impact
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Tracked news").font(.headline)
                            Spacer()
                            if let updates {
                                Text("\(updates.items.count) items").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if let updates, !updates.items.isEmpty {
                            ForEach(updates.items.sorted { a, b in
                                if a.impactRank != b.impactRank { return a.impactRank < b.impactRank }
                                return (a.publishedAt ?? "") > (b.publishedAt ?? "")
                            }.prefix(30)) { item in
                                HStack(alignment: .top, spacing: 10) {
                                    MacStatusPill(text: item.impact.capitalized, color: item.impact == "high" ? .red : (item.impact == "medium" ? .orange : .secondary))
                                        .frame(width: 70, alignment: .leading)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.title ?? "Untitled").font(.subheadline.weight(.medium))
                                        if let summary = item.summary, !summary.isEmpty {
                                            Text(summary).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                                        }
                                        HStack(spacing: 6) {
                                            if let source = item.source { Text(source).font(.caption2).foregroundStyle(.tertiary) }
                                            Text(MacTimeFormat.relative(item.publishedAt ?? item.capturedAt)).font(.caption2).foregroundStyle(.tertiary)
                                            if let action = item.recommendedAction, action != "none" {
                                                Text(action.replacingOccurrences(of: "_", with: " ")).font(.caption2).foregroundStyle(Color.purple)
                                            }
                                        }
                                    }
                                    Spacer()
                                    if let url = item.url, let link = URL(string: url) {
                                        Link(destination: link) { Image(systemName: "arrow.up.right.square") }
                                    }
                                }
                                .padding(8)
                                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                            }
                        } else {
                            Text(busy ? "Loading…" : "No tracked news yet — press Sync news.")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    .padding()
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                }
                .padding(20)
            }
        } else {
            ContentUnavailableView("Portfolio & Watch", systemImage: "briefcase", description: Text("Select a position to see tracked news, auto-run recommendations and the decision record."))
        }
    }
}
