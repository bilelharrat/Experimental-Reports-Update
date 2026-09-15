import SwiftUI

/// One row of the board — the rollup row, the latest decision and running jobs, flattened for `Table`.
struct MacPipelineRow: Identifiable, Hashable {
    let id: String
    let name: String
    let ticker: String
    let stage: MacLifecycleStage
    let stageOrder: Int
    let bucket: String
    let nextAction: String
    let memoStatus: String
    let warnings: Int
    let runningJobs: Int
    let decision: String
    let decisionAt: String
    let newsCount: Int
    let latestNews: String
    let attention: String
    let attentionHigh: Bool
    let followed: Bool
    let lastActivity: String
    let lastActivityDate: Date
    let fitScore: Int
    let fitLabel: String
    let fitReasons: String
}

struct MacPipelineDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var selection: String?
    @State private var stageFilter: MacLifecycleStage?
    @State private var followedOnly = false
    @State private var search = ""
    @State private var sortOrder = [KeyPathComparator(\MacPipelineRow.stageOrder)]

    private var rows: [MacPipelineRow] {
        let ids = store.pipelineCompanyIds
        var out: [MacPipelineRow] = []
        for id in ids {
            guard let company = store.companies.first(where: { $0.id == id }) ?? store.rollupRow(for: id).map({ row in
                MacCompany(id: row.id, name: row.name, ticker: row.ticker, companyType: row.companyType, status: row.status, sector: row.category, industry: nil)
            }) else { continue }
            let row = store.rollupRow(for: id)
            let decision = store.latestDecision(for: id)
            let stage = store.stage(for: id)
            let running = store.activeJobs.filter { $0.companyId == id }.count
            out.append(MacPipelineRow(
                id: id,
                name: company.title,
                ticker: company.ticker ?? "",
                stage: stage,
                stageOrder: stage.order,
                bucket: row?.bucket ?? "",
                nextAction: row?.nextAction?.label ?? "",
                memoStatus: row?.memoStatusLabel ?? (store.reports(for: id).isEmpty ? "No memo" : "—"),
                warnings: row?.memo?.warningCount ?? 0,
                runningJobs: running,
                decision: decision?.verdictLabel ?? "",
                decisionAt: decision.map { MacTimeFormat.relative($0.decidedAt ?? $0.createdAt) } ?? "",
                newsCount: row?.news?.recentCount ?? 0,
                latestNews: row?.news?.latestTitle ?? "",
                attention: row?.primaryAttention?.label ?? "",
                attentionHigh: row?.primaryAttention?.isHigh ?? false,
                followed: store.isFollowed(id),
                lastActivity: MacTimeFormat.relative(row?.lastActivityAt),
                lastActivityDate: MacTimeFormat.parse(row?.lastActivityAt) ?? .distantPast,
                fitScore: row?.thesisFit?.score ?? -1,
                fitLabel: row?.thesisFit.map { $0.score.map { "\($0)" } ?? $0.label } ?? "",
                fitReasons: row?.thesisFit?.reasons.joined(separator: "\n") ?? ""
            ))
        }
        var filtered = out
        if let stageFilter { filtered = filtered.filter { $0.stage == stageFilter } }
        if followedOnly { filtered = filtered.filter(\.followed) }
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !q.isEmpty {
            filtered = filtered.filter { $0.name.lowercased().contains(q) || $0.ticker.lowercased().contains(q) || $0.id.lowercased().contains(q) }
        }
        return filtered.sorted(using: sortOrder)
    }

    private var selectedCompany: MacCompany? {
        guard let selection else { return nil }
        return store.companies.first { $0.id == selection }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                header
                Divider()
                table
                Divider()
                footer
            }
            .frame(minWidth: 640, maxWidth: .infinity, maxHeight: .infinity)
            .layoutPriority(1)

            detailPane
                .frame(minWidth: 280, idealWidth: 320, maxWidth: 420)
                .layoutPriority(0)
        }
        .task {
            if store.rollup == nil { await store.loadPipeline() }
            if selection == nil { selection = store.selectedCompany?.id }
        }
        .onChange(of: selection) { _, id in
            if let id, let company = store.companies.first(where: { $0.id == id }) {
                store.selectCompany(company)
            }
        }
        .onChange(of: validFollowedIds.isEmpty) { _, empty in
            if empty { followedOnly = false }
        }
    }

    private var validFollowedIds: [String] {
        guard !store.companies.isEmpty else { return [] }
        let known = Set(store.companies.map(\.id))
        return store.followedCompanyIds.filter { known.contains($0) }
    }

    // MARK: - Header / footer

    private var header: some View {
        HStack(spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Filter pipeline…", text: $search)
                    .textFieldStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 7))
            .frame(maxWidth: 260)

            Picker("Stage", selection: $stageFilter) {
                Text("All stages").tag(MacLifecycleStage?.none)
                Divider()
                ForEach(MacLifecycleStage.knownCases) { stage in
                    Label(stage.rawValue, systemImage: stage.systemImage).tag(MacLifecycleStage?.some(stage))
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 170)

            Toggle("Followed only", isOn: $followedOnly)
                .toggleStyle(.checkbox)
                .disabled(validFollowedIds.isEmpty)

            Spacer()

            if let totals = store.rollup?.totals {
                HStack(spacing: 10) {
                    countPill("\(totals.needsActionCount ?? 0) need action", color: .orange)
                    countPill("\(totals.runningMemoCount ?? 0) running", color: .blue)
                    countPill("\(totals.failedMemoCount ?? 0) failed", color: .red)
                }
            }

            Button {
                Task { await store.loadPipeline() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(store.pipelineLoading)

            Button {
                store.syncAllTracking()
            } label: {
                if store.pipelineSyncing {
                    HStack(spacing: 6) { ProgressView().controlSize(.small); Text("Syncing…") }
                } else {
                    Label("Sync All", systemImage: "arrow.triangle.2.circlepath")
                }
            }
            .disabled(store.pipelineSyncing || !store.canRunTasks || validFollowedIds.isEmpty)
            .help(validFollowedIds.isEmpty
                  ? "Follow companies to sync their tracked news"
                  : "Refresh tracked news for every followed company (runs on the server; can take minutes)")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    private func countPill(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.12), in: Capsule())
    }

    private var footer: some View {
        HStack {
            Text("\(rows.count) companies · \(validFollowedIds.count) followed")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if store.rollupStale {
                Text(store.pipelineError == nil ? "· Showing the last board" : "· Showing the last board · sync failed")
                    .font(.caption2)
                    .foregroundStyle(Color.dsWarning)
            } else if let at = store.pipelineLoadedAt {
                Text("· rollup \(at.formatted(date: .omitted, time: .shortened))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text("↩ dossier · ⌘D decision · ⌘N memo · j/k move")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 5)
    }

    // MARK: - Table

    private var table: some View {
        Table(rows, selection: $selection, sortOrder: $sortOrder) {
            TableColumn("Company", value: \.name) { row in
                HStack(spacing: 8) {
                    if row.followed {
                        Image(systemName: "star.fill").font(.caption2).foregroundStyle(Color.yellow)
                    }
                    Text(row.name).fontWeight(.medium)
                    if !row.ticker.isEmpty {
                        Text(row.ticker).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
            .width(min: 180, ideal: 220)

            TableColumn("Stage", value: \.stageOrder) { row in
                Label(row.stage.rawValue, systemImage: row.stage.systemImage)
                    .foregroundStyle(stageColor(row.stage))
            }
            .width(min: 100, ideal: 120)

            TableColumn("Fit", value: \.fitScore) { row in
                if row.fitScore < 0 {
                    Text("—").foregroundStyle(.tertiary).help(row.fitLabel.isEmpty ? "" : row.fitLabel)
                } else {
                    Text("\(row.fitScore)%")
                        .monospacedDigit()
                        .foregroundStyle(row.fitScore >= 70 ? Color.green : (row.fitScore >= 40 ? Color.orange : Color.red))
                        .help(row.fitReasons)
                }
            }
            .width(min: 50, ideal: 60)

            TableColumn("Next action", value: \.nextAction) { row in
                if row.attention.isEmpty {
                    Text(row.nextAction.isEmpty ? "—" : row.nextAction).foregroundStyle(.secondary)
                } else {
                    Label(row.attention, systemImage: row.attentionHigh ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                        .foregroundStyle(row.attentionHigh ? Color.red : Color.orange)
                        .lineLimit(1)
                }
            }
            .width(min: 160, ideal: 220)

            TableColumn("Memo", value: \.memoStatus) { row in
                HStack(spacing: 4) {
                    Text(row.memoStatus).lineLimit(1)
                    if row.runningJobs > 0 {
                        ProgressView().controlSize(.mini)
                    }
                }
            }
            .width(min: 110, ideal: 150)

            TableColumn("Decision", value: \.decision) { row in
                if row.decision.isEmpty {
                    Text("—").foregroundStyle(.tertiary)
                } else {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(row.decision).foregroundStyle(decisionColor(row.decision))
                        Text(row.decisionAt).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            .width(min: 80, ideal: 100)

            TableColumn("News (7d)", value: \.newsCount) { row in
                HStack(spacing: 6) {
                    Text("\(row.newsCount)").monospacedDigit()
                    if !row.latestNews.isEmpty {
                        Text(row.latestNews).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
            .width(min: 120, ideal: 240)

            TableColumn("Activity", value: \.lastActivityDate) { row in
                Text(row.lastActivity).font(.caption).foregroundStyle(.secondary)
            }
            .width(min: 70, ideal: 90)
        }
        .contextMenu(forSelectionType: String.self) { ids in
            if let id = ids.first, let company = store.companies.first(where: { $0.id == id }) {
                Button("Open dossier") { store.showCompany(company) }
                Button("Record decision…") { store.requestDecision(for: company) }
                    .disabled(!store.canRunTasks)
                Button("New memo run…") { store.requestNewReport(for: company) }
                    .disabled(!store.canRunTasks)
                if let report = store.reports(for: company.id).first(where: \.canOpen) {
                    Button("Open IC review") { store.openICReview(report: report) }
                }
                Divider()
                Button(store.isFollowed(id) ? "Unfollow" : "Follow") {
                    Task { await store.toggleFollow(id) }
                }
                .disabled(!store.canRunTasks)
            }
        } primaryAction: { ids in
            if let id = ids.first, let company = store.companies.first(where: { $0.id == id }) {
                store.showCompany(company)
            }
        }
        .onKeyPress(.return) {
            openSelected()
            return .handled
        }
        .onKeyPress("j") { move(1); return .handled }
        .onKeyPress("k") { move(-1); return .handled }
    }

    // MARK: - Detail pane

    @ViewBuilder
    private var detailPane: some View {
        if let company = selectedCompany {
            let row = store.rollupRow(for: company.id)
            let decision = store.latestDecision(for: company.id)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 10) {
                        MacMonogram(name: company.title, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(company.title).font(.headline)
                            Text(company.subtitle).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }

                    Label(store.stage(for: company.id).rawValue, systemImage: store.stage(for: company.id).systemImage)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(stageColor(store.stage(for: company.id)))

                    MacSignalScoreView(companyId: company.id, compact: true)

                    if let row {
                        VStack(alignment: .leading, spacing: 6) {
                            if let action = row.nextAction?.label {
                                Label(action, systemImage: "arrow.right.circle")
                                    .font(.subheadline)
                            }
                            ForEach(row.attention) { item in
                                VStack(alignment: .leading, spacing: 2) {
                                    Label(item.label ?? item.kind ?? "Attention", systemImage: item.isHigh ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(item.isHigh ? Color.red : Color.orange)
                                    if let detail = item.detail, !detail.isEmpty {
                                        Text(detail).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            statLine("Memo", row.memoStatusLabel)
                            statLine("Risks open", "\((row.risks?.unresearched ?? 0) + (row.risks?.needsReview ?? 0)) of \(row.risks?.total ?? 0)")
                            statLine("Evidence", "\(row.evidence?.supported ?? 0) supported · \(row.evidence?.contradicted ?? 0) contradicted · \(row.evidence?.missing ?? 0) missing")
                            statLine("Documents", "\(row.documents?.total ?? 0) (\(row.documents?.unresolved ?? 0) unresolved)")
                            if let price = row.price, let last = price.lastPrice {
                                statLine("Price", String(format: "%.2f (%+.1f%% 1d)", last, price.changePct1d ?? 0))
                            }
                        }
                        .padding(10)
                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Decision").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        if let decision {
                            HStack {
                                Text(decision.verdictLabel).font(.subheadline.weight(.bold)).foregroundStyle(decisionColor(decision.verdictLabel))
                                Text(MacTimeFormat.relative(decision.decidedAt ?? decision.createdAt)).font(.caption).foregroundStyle(.secondary)
                            }
                            Text(decision.explanation).font(.caption).lineLimit(4)
                            if let retro = decision.latestRetrospective {
                                Label("\(retro.label) — \(retro.rationaleEn ?? "")", systemImage: "clock.arrow.circlepath")
                                    .font(.caption)
                                    .foregroundStyle(retro.verdict == "still_right" ? Color.green : Color.orange)
                                    .lineLimit(3)
                            }
                        } else {
                            Text("No decision on record.").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))

                    VStack(spacing: 8) {
                        Button {
                            store.showCompany(company)
                        } label: {
                            Label("Open dossier", systemImage: "building.columns").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)

                        Button {
                            store.requestDecision(for: company)
                        } label: {
                            Label("Record decision (⌘D)", systemImage: "checkmark.seal").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!store.canRunTasks)
                        .keyboardShortcut("d", modifiers: .command)

                        if let report = store.reports(for: company.id).first(where: \.canOpen) {
                            Button {
                                store.openICReview(report: report)
                            } label: {
                                Label("IC review window (⌘⇧O)", systemImage: "rectangle.split.2x1").frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .keyboardShortcut("o", modifiers: [.command, .shift])
                        }

                        Button {
                            store.requestNewReport(for: company)
                        } label: {
                            Label("New memo run", systemImage: "doc.badge.plus").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!store.canRunTasks)

                        Button {
                            Task { await store.toggleFollow(company.id) }
                        } label: {
                            Label(store.isFollowed(company.id) ? "Unfollow" : "Follow", systemImage: store.isFollowed(company.id) ? "star.slash" : "star")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!store.canRunTasks)
                    }
                }
                .padding(14)
            }
        } else {
            ContentUnavailableView("Select a company", systemImage: "list.bullet.rectangle", description: Text("The board shows every followed company with its stage, next action, memo state and decision."))
        }
    }

    private func statLine(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label).font(.caption).foregroundStyle(.secondary).frame(width: 78, alignment: .leading)
            Text(value).font(.caption)
            Spacer()
        }
    }

    // MARK: - Helpers

    private func stageColor(_ stage: MacLifecycleStage) -> Color {
        switch stage {
        case .sourcing: return .secondary
        case .screening: return .teal
        case .diligence: return .blue
        case .ic: return .purple
        case .portfolio: return .green
        case .watch: return .orange
        case .passed: return .red
        case .unknown: return .secondary
        }
    }

    private func decisionColor(_ label: String) -> Color {
        switch label.lowercased() {
        case "invest": return .green
        case "pass": return .red
        default: return .orange
        }
    }

    private func openSelected() {
        if let company = selectedCompany { store.showCompany(company) }
    }

    private func move(_ delta: Int) {
        let list = rows
        guard !list.isEmpty else { return }
        let current = list.firstIndex { $0.id == selection } ?? -1
        let next = min(max(current + delta, 0), list.count - 1)
        selection = list[next].id
    }
}
