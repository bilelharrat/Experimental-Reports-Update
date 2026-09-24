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
        if BSHDesign.active == .bureau {
            bureauBody
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
        } else {
            splitBody
        }
    }

    private var splitBody: some View {
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
            .font(.ui(.caption).weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.12), in: Capsule())
    }

    private var footer: some View {
        HStack {
            Text("\(rows.count) companies · \(validFollowedIds.count) followed")
                .font(.ui(.caption2))
                .foregroundStyle(.secondary)
            if store.rollupStale {
                Text(store.pipelineError == nil ? "· Showing the last board" : "· Showing the last board · sync failed")
                    .font(.ui(.caption2))
                    .foregroundStyle(Color.dsWarning)
            } else if let at = store.pipelineLoadedAt {
                Text("· rollup \(at.formatted(date: .omitted, time: .shortened))")
                    .font(.ui(.caption2))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text("↩ dossier · ⌘D decision · ⌘N memo · j/k move")
                .font(.ui(.caption2))
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
                        Image(systemName: "star.fill").font(.ui(.caption2)).foregroundStyle(Color.yellow)
                    }
                    Text(row.name).fontWeight(.medium)
                    if !row.ticker.isEmpty {
                        Text(row.ticker).font(.ui(.caption).monospacedDigit()).foregroundStyle(.secondary)
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
                        Text(row.decisionAt).font(.ui(.caption2)).foregroundStyle(.secondary)
                    }
                }
            }
            .width(min: 80, ideal: 100)

            TableColumn("News (7d)", value: \.newsCount) { row in
                HStack(spacing: 6) {
                    Text("\(row.newsCount)").monospacedDigit()
                    if !row.latestNews.isEmpty {
                        Text(row.latestNews).font(.ui(.caption)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
            .width(min: 120, ideal: 240)

            TableColumn("Activity", value: \.lastActivityDate) { row in
                Text(row.lastActivity).font(.ui(.caption)).foregroundStyle(.secondary)
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
                        MacMonogram(company: company, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(company.title).font(.ui(.headline))
                            Text(company.subtitle).font(.ui(.caption)).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }

                    Label(store.stage(for: company.id).rawValue, systemImage: store.stage(for: company.id).systemImage)
                        .font(.ui(.subheadline).weight(.semibold))
                        .foregroundStyle(stageColor(store.stage(for: company.id)))

                    MacSignalScoreView(companyId: company.id, compact: true)

                    if let row {
                        VStack(alignment: .leading, spacing: 6) {
                            if let action = row.nextAction?.label {
                                Label(action, systemImage: "arrow.right.circle")
                                    .font(.ui(.subheadline))
                            }
                            ForEach(row.attention) { item in
                                VStack(alignment: .leading, spacing: 2) {
                                    Label(item.label ?? item.kind ?? "Attention", systemImage: item.isHigh ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                                        .font(.ui(.caption).weight(.semibold))
                                        .foregroundStyle(item.isHigh ? Color.red : Color.orange)
                                    if let detail = item.detail, !detail.isEmpty {
                                        Text(detail).font(.ui(.caption)).foregroundStyle(.secondary)
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
                        .frame(maxWidth: BSHDesign.active == .bureau ? .infinity : nil, alignment: .leading)
                        .padding(10)
                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Decision").font(.ui(.caption).weight(.semibold)).foregroundStyle(.secondary)
                        if let decision {
                            HStack {
                                Text(decision.verdictLabel).font(.ui(.subheadline).weight(.bold)).foregroundStyle(decisionColor(decision.verdictLabel))
                                Text(MacTimeFormat.relative(decision.decidedAt ?? decision.createdAt)).font(.ui(.caption)).foregroundStyle(.secondary)
                            }
                            Text(decision.explanation).font(.ui(.caption)).lineLimit(4)
                            if let retro = decision.latestRetrospective {
                                Label("\(retro.label) — \(retro.rationaleEn ?? "")", systemImage: "clock.arrow.circlepath")
                                    .font(.ui(.caption))
                                    .foregroundStyle(retro.verdict == "still_right" ? Color.green : Color.orange)
                                    .lineLimit(3)
                            }
                        } else {
                            Text("No decision on record.").font(.ui(.caption)).foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: BSHDesign.active == .bureau ? .infinity : nil, alignment: .leading)
                    .padding(10)
                    .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))

                    VStack(spacing: 8) {
                        Button {
                            store.showCompany(company)
                        } label: {
                            Label("Open dossier", systemImage: "building.columns").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.dsProminent)

                        Button {
                            store.requestDecision(for: company)
                        } label: {
                            Label("Record decision (⌘D)", systemImage: "checkmark.seal").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.dsBordered)
                        .disabled(!store.canRunTasks)
                        .keyboardShortcut("d", modifiers: .command)

                        if let report = store.reports(for: company.id).first(where: \.canOpen) {
                            Button {
                                store.openICReview(report: report)
                            } label: {
                                Label("IC review window (⌘⇧O)", systemImage: "rectangle.split.2x1").frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.dsBordered)
                            .keyboardShortcut("o", modifiers: [.command, .shift])
                        }

                        Button {
                            store.requestNewReport(for: company)
                        } label: {
                            Label("New memo run", systemImage: "doc.badge.plus").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.dsBordered)
                        .disabled(!store.canRunTasks)

                        Button {
                            Task { await store.toggleFollow(company.id) }
                        } label: {
                            Label(store.isFollowed(company.id) ? "Unfollow" : "Follow", systemImage: store.isFollowed(company.id) ? "star.slash" : "star")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.dsBordered)
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
            Text(label).font(.ui(.caption)).foregroundStyle(.secondary).frame(width: 78, alignment: .leading)
            Text(value).font(.ui(.caption))
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

// MARK: - Bureau

/// The board under Bureau, set in the website's page anatomy: the title, the filters, the
/// board as an inset table in a tray (the chosen row a slip of fresh paper with a brass edge)
/// and the company's card beside it.
extension MacPipelineDeskView {
    var bureauBody: some View {
        MacBureauPipelinePage(
            rows: rows,
            selection: $selection,
            stageFilter: $stageFilter,
            followedOnly: $followedOnly,
            search: $search,
            sortOrder: $sortOrder,
            followedCount: validFollowedIds.count,
            detail: AnyView(bureauDetail)
        )
    }

    @ViewBuilder
    private var bureauDetail: some View {
        if selectedCompany != nil {
            detailPane
        } else {
            Text("Pick a company on the board to see its stage, next step, memo and decision.")
                .font(BSHType.bureauSans(13))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

private struct MacBureauPipelinePage: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let rows: [MacPipelineRow]
    @Binding var selection: String?
    @Binding var stageFilter: MacLifecycleStage?
    @Binding var followedOnly: Bool
    @Binding var search: String
    @Binding var sortOrder: [KeyPathComparator<MacPipelineRow>]
    let followedCount: Int
    let detail: AnyView
    @FocusState private var boardFocused: Bool

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPageHeader("Pipeline", subtitle: "Every company on the board, with its stage, next step, memo and latest decision.") {
                MacBureauButton("Refresh", icon: "refresh-cw", busy: store.pipelineLoading) {
                    Task { await store.loadPipeline() }
                }
                .disabled(store.pipelineLoading)
                MacBureauButton(store.pipelineSyncing ? "Syncing…" : "Sync all", busy: store.pipelineSyncing) {
                    store.syncAllTracking()
                }
                .disabled(store.pipelineSyncing || !store.canRunTasks || followedCount == 0)
                .help(followedCount == 0 ? "Follow companies to sync their tracked news" : "Refresh tracked news for every followed company (runs on the server; can take minutes)")
            }
            .padding(.bottom, 20)

            filters
                .padding(.bottom, 12)

            HStack(alignment: .top, spacing: 16) {
                board
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                detail
                    .frame(width: 320)
                    .frame(maxHeight: .infinity, alignment: .top)
                    .background(RoundedRectangle(cornerRadius: 14, style: .circular).fill(ink.tray))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(ink.ink(0.035), lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
            }

            footer
                .padding(.top, 10)
        }
        .padding(.horizontal, 32)
        .padding(.top, 16)
        .padding(.bottom, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(ink.sheet)
    }

    // MARK: Filters

    private var filters: some View {
        HStack(spacing: 10) {
            HStack(spacing: 6) {
                LucideIcon("search", size: 14).foregroundStyle(ink.subtle)
                TextField("", text: $search, prompt: Text("Filter pipeline…").foregroundStyle(ink.subtle))
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(13))
            }
            .padding(.horizontal, 10)
            .frame(width: 240, height: 32)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(ink.raised))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .circular).strokeBorder(ink.ink(0.14), lineWidth: 1))

            Menu {
                Button("All stages") { stageFilter = nil }
                Divider()
                ForEach(MacLifecycleStage.knownCases) { stage in
                    Button(stage.rawValue) { stageFilter = stage }
                }
            } label: {
                HStack(spacing: 6) {
                    Text(stageFilter?.rawValue ?? "All stages")
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .foregroundStyle(ink.ink)
                    LucideIcon("chevrons-up-down", size: 14).foregroundStyle(ink.muted)
                }
                .padding(.horizontal, 12)
                .frame(height: 32)
                .background(Capsule().fill(ink.raised))
                .overlay(Capsule().strokeBorder(ink.ink(0.14), lineWidth: 1))
                .contentShape(Capsule())
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
            .menuIndicator(.hidden)
            .fixedSize()

            HStack(spacing: 8) {
                MacBureauSwitch(isOn: $followedOnly, disabled: followedCount == 0)
                Text("Followed only")
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.secondary)
            }

            Spacer(minLength: 8)

            if let totals = store.rollup?.totals {
                MacBureauChip(text: "\(totals.needsActionCount ?? 0) need action", foreground: ink.warningInk, background: ink.warning.opacity(0.14))
                MacBureauChip(text: "\(totals.runningMemoCount ?? 0) running", foreground: ink.info, background: ink.info.opacity(0.12))
                MacBureauChip(text: "\(totals.failedMemoCount ?? 0) failed", foreground: ink.dangerInk, background: ink.dangerSoft)
            }
        }
    }

    // MARK: Board

    private var board: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                headerCell("Company", key: \.name, width: nil)
                headerCell("Stage", key: \.stageOrder, width: 118)
                headerCell("Fit", key: \.fitScore, width: 52)
                headerCell("Next action", key: \.nextAction, width: nil)
                headerCell("Memo", key: \.memoStatus, width: 128)
                headerCell("Decision", key: \.decision, width: 96)
            }
            .padding(.horizontal, 14)
            .frame(height: 34)
            .overlay(alignment: .bottom) { Rectangle().fill(ink.ink(0.22)).frame(height: 1) }

            if rows.isEmpty {
                Text(store.pipelineLoading ? "Loading the board…" : "No company matches.")
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.muted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(rows) { row in
                            MacBureauPipelineRowView(
                                row: row,
                                isSelected: selection == row.id,
                                ink: ink,
                                select: { selection = row.id; boardFocused = true },
                                open: { open(row.id) }
                            )
                            .contextMenu { menu(for: row.id) }
                        }
                    }
                    .padding(6)
                }
            }
        }
        .background(RoundedRectangle(cornerRadius: 14, style: .circular).fill(ink.tray))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(ink.ink(0.035), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        .focusable()
        .focused($boardFocused)
        .focusEffectDisabled()
        .onKeyPress(.return) { if let selection { open(selection) }; return .handled }
        .onKeyPress("j") { move(1); return .handled }
        .onKeyPress("k") { move(-1); return .handled }
        .onKeyPress(.downArrow) { move(1); return .handled }
        .onKeyPress(.upArrow) { move(-1); return .handled }
    }

    /// `.inset-table thead`: small capitals in the muted ink; the sorted column in ink.
    private func headerCell<Value: Comparable>(_ title: String, key: KeyPath<MacPipelineRow, Value>, width: CGFloat?) -> some View {
        let sorted = sortOrder.first?.keyPath == key
        let ascending = sortOrder.first?.order != .reverse
        return Button {
            if sorted {
                sortOrder = [KeyPathComparator(key, order: ascending ? .reverse : .forward)]
            } else {
                sortOrder = [KeyPathComparator(key)]
            }
        } label: {
            HStack(spacing: 4) {
                Text(title.uppercased())
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .tracking(0.88)
                    .foregroundStyle(sorted ? ink.ink : ink.muted)
                if sorted {
                    LucideIcon(ascending ? "chevron-up" : "chevron-down", size: 12).foregroundStyle(ink.muted)
                }
            }
            .frame(maxWidth: width == nil ? .infinity : width, alignment: .leading)
            .frame(width: width, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func menu(for id: String) -> some View {
        if let company = store.companies.first(where: { $0.id == id }) {
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
    }

    private var footer: some View {
        HStack(spacing: 4) {
            Text("\(rows.count) companies · \(followedCount) followed")
            if store.rollupStale {
                Text(store.pipelineError == nil ? "· Showing the last board" : "· Showing the last board · sync failed")
                    .foregroundStyle(ink.warningInk)
            } else if let at = store.pipelineLoadedAt {
                Text("· rollup \(at.formatted(date: .omitted, time: .shortened))")
            }
            Spacer()
            Text("↩ dossier · ⌘D decision · ⌘N memo · j/k move")
                .foregroundStyle(ink.subtle)
        }
        .font(BSHType.bureauSans(11))
        .foregroundStyle(ink.muted)
    }

    private func open(_ id: String) {
        if let company = store.companies.first(where: { $0.id == id }) { store.showCompany(company) }
    }

    private func move(_ delta: Int) {
        guard !rows.isEmpty else { return }
        let current = rows.firstIndex { $0.id == selection } ?? -1
        selection = rows[min(max(current + delta, 0), rows.count - 1)].id
    }
}

/// One company on the board. Chosen, it is a slip of fresh paper lifted from the tray with
/// a brass ribbon down its edge (the website's chosen `.doc-row`).
private struct MacBureauPipelineRowView: View {
    let row: MacPipelineRow
    let isSelected: Bool
    let ink: MacBureauPageInk
    let select: () -> Void
    let open: () -> Void
    @State private var hovered = false

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                if row.followed {
                    LucideIcon("star-fill", size: 12).foregroundStyle(ink.notice)
                }
                Text(row.name)
                    .font(BSHType.bureauSans(13, weight: .medium))
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                if !row.ticker.isEmpty {
                    Text(row.ticker)
                        .font(BSHType.bureauSans(11, weight: .semibold).monospacedDigit())
                        .foregroundStyle(ink.muted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text(row.stage.rawValue)
                .font(BSHType.bureauSans(12, weight: .medium))
                .foregroundStyle(stageInk)
                .frame(width: 118, alignment: .leading)

            Group {
                if row.fitScore < 0 {
                    Text("—").foregroundStyle(ink.subtle)
                } else {
                    Text("\(row.fitScore)%")
                        .foregroundStyle(row.fitScore >= 70 ? ink.successInk : (row.fitScore >= 40 ? ink.warningInk : ink.dangerInk))
                }
            }
            .font(BSHType.bureauSans(12).monospacedDigit())
            .frame(width: 52, alignment: .leading)
            .help(row.fitReasons)

            Group {
                if row.attention.isEmpty {
                    Text(row.nextAction.isEmpty ? "—" : row.nextAction).foregroundStyle(ink.secondary)
                } else {
                    Text(row.attention).foregroundStyle(row.attentionHigh ? ink.dangerInk : ink.warningInk)
                }
            }
            .font(BSHType.bureauSans(12))
            .lineLimit(1)
            .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: 4) {
                Text(row.memoStatus).lineLimit(1)
                if row.runningJobs > 0 { ProgressView().controlSize(.mini) }
            }
            .font(BSHType.bureauSans(12))
            .foregroundStyle(ink.secondary)
            .frame(width: 128, alignment: .leading)

            Group {
                if row.decision.isEmpty {
                    Text("—").foregroundStyle(ink.subtle)
                } else {
                    Text(row.decision).foregroundStyle(decisionInk)
                }
            }
            .font(BSHType.bureauSans(12, weight: .medium))
            .frame(width: 96, alignment: .leading)
        }
        .padding(.horizontal, 8)
        .frame(height: 38)
        .background {
            if isSelected {
                RoundedRectangle(cornerRadius: 9, style: .circular)
                    .fill(ink.raised)
                    .overlay(alignment: .leading) {
                        Rectangle().fill(ink.accentGlow(1)).frame(width: 3)
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .circular))
                    .overlay(RoundedRectangle(cornerRadius: 9, style: .circular).inset(by: -0.5).stroke(ink.ink(0.06), lineWidth: 1))
                    .shadow(color: ink.shadow(0.08), radius: 1.5, y: 1)
            } else if hovered {
                RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.ink(0.035))
            }
        }
        .contentShape(Rectangle())
        .onHover { hovered = $0 }
        .onTapGesture(count: 2) { open() }
        .onTapGesture { select() }
    }

    private var stageInk: Color {
        switch row.stage {
        case .sourcing, .unknown: return ink.secondary
        case .screening: return .bshFixed(ink.dark ? BSHRGB(140, 220, 226) : BSHRGB(16, 98, 106))
        case .diligence: return ink.info
        case .ic: return ink.purpleInk
        case .portfolio: return ink.successInk
        case .watch: return ink.warningInk
        case .passed: return ink.dangerInk
        }
    }

    private var decisionInk: Color {
        switch row.decision.lowercased() {
        case "invest": return ink.successInk
        case "pass": return ink.dangerInk
        default: return ink.warningInk
        }
    }
}
