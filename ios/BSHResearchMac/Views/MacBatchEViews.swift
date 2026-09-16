#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

// MARK: - Unified public/private profile card (dossier header)

struct MacUnifiedProfileView: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore

    private var profile: MacCompanyProfile? { store.profileByCompany[companyId] }
    @State private var loadAttempted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Profile", systemImage: "square.on.square.dashed")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                if let p = profile {
                    MacStatusPill(text: p.isPublic ? "Public" : "Private", color: p.isPublic ? .blue : .purple)
                }
                Button { Task { await store.loadProfile(companyId) } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.plain).controlSize(.mini)
            }
            if let p = profile {
                HStack(alignment: .top, spacing: 14) {
                    column("Public") {
                        if let q = p.publicSide, let price = q.lastPrice {
                            fact("Ticker", q.ticker ?? "—")
                            fact("Last", String(format: "$%.2f", price), color: (q.changePct1d ?? 0) >= 0 ? .green : .red)
                            fact("1D", q.changePct1d.map { String(format: "%+.2f%%", $0) } ?? "—")
                            fact("Mkt cap", MacMoney.short(q.marketCap))
                        } else if p.isPublic {
                            Text("Quote unavailable").font(.caption2).foregroundStyle(.secondary)
                        } else {
                            Text("No public listing").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    column("Private") {
                        if let pr = p.privateSide {
                            fact("Position", [pr.position.round, pr.position.investedUsd.map(MacMoney.short)].compactMap { $0 }.joined(separator: " · ").ifEmpty("—"))
                            fact("Own", pr.position.ownershipPct.map { String(format: "%.1f%%", $0) } ?? "—")
                            fact("ARR", MacMoney.short(pr.latestKpi?.arrUsd))
                            fact("Runway", pr.latestKpi?.runwayMonths.map { String(format: "%.0f mo", $0) } ?? "—",
                                 color: (pr.latestKpi?.runwayMonths ?? 99) < 9 ? .red : .primary)
                            fact("Mark · MOIC", [pr.latestMark.map { MacMoney.short($0.valueUsd) }, pr.moic.map { String(format: "%.2fx", $0) }].compactMap { $0 }.joined(separator: " · ").ifEmpty("—"))
                        } else {
                            Text("No position on file").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    column("Process") {
                        fact("Stage", store.dealPipelines[companyId]?.stage ?? p.pipeline?.stage ?? store.stage(for: companyId).rawValue)
                        fact("Thesis fit", p.thesisFit?.score.map { "\($0)%" } ?? (p.thesisFit?.fit ?? "—").capitalized)
                        fact("Decision", p.latestDecision?.verdict?.capitalized ?? "—",
                             color: p.latestDecision?.verdict == "invest" ? .green : (p.latestDecision?.verdict == "pass" ? .red : .primary))
                        fact("IC", (p.ic?.openMeeting != nil ? "Meeting open" : "\(p.ic?.meetingCount ?? 0) meetings") + " · \(p.ic?.referenceCalls ?? 0) refs")
                        if let c = p.counts {
                            fact("On file", "\(c.files ?? 0) files · \(c.transcripts ?? 0) transcripts · \(c.openComments ?? 0) open comments")
                        }
                    }
                }
                if !p.description.isEmpty {
                    Text(p.description).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
            } else if loadAttempted {
                HStack(spacing: 8) {
                    Text("Profile unavailable on this server.").font(.caption2).foregroundStyle(.secondary)
                    Button("Retry") { Task { await load() } }.controlSize(.mini)
                }
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .padding(12)
        .appleGlassCard(cornerRadius: 12)
        .task(id: companyId) {
            loadAttempted = false
            if profile == nil { await load() }
        }
    }

    private func load() async {
        await store.loadProfile(companyId)
        guard !Task.isCancelled else { return }
        loadAttempted = true
    }

    private func column<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.dsLabel).foregroundStyle(.secondary)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func fact(_ label: String, _ value: String, color: Color = .primary) -> some View {
        HStack(spacing: 6) {
            Text(label).font(.caption2).foregroundStyle(.secondary).frame(width: 74, alignment: .leading)
            Text(value).font(.caption.monospacedDigit()).foregroundStyle(color).lineLimit(1)
        }
    }
}

private extension String {
    func ifEmpty(_ fallback: String) -> String { isEmpty ? fallback : self }
}

// MARK: - Filings & earnings watch (Market Radar › Filings)

struct MacFilingsWatchPane: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(store.filingsWatch.map { "Updated \(MacTimeFormat.relative($0.generatedAt))" } ?? "SEC filings · earnings")
                    .font(.caption2).foregroundStyle(.secondary)
                Spacer()
                if store.filingsLoading { ProgressView().controlSize(.mini) }
                Button { Task { await store.loadFilingsWatch(refresh: true) } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.plain).controlSize(.mini).disabled(store.filingsLoading)
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            Divider()
            List {
                if let w = store.filingsWatch {
                    if !w.upcomingEarnings.isEmpty {
                        Section("Earnings in the next 14 days") {
                            ForEach(w.upcomingEarnings) { e in
                                HStack {
                                    Text(e.ticker).font(.caption.monospacedDigit().weight(.bold))
                                    Text(e.date ?? "").font(.caption)
                                    if e.estimated == true { Text("est.").font(.caption2).foregroundStyle(.secondary) }
                                    Spacer()
                                    Text(e.days.map { $0 == 0 ? "today" : "in \($0)d" } ?? "").font(.caption2).foregroundStyle(.orange)
                                }
                                .contentShape(Rectangle())
                                .onTapGesture { store.showTicker(e.ticker) }
                            }
                        }
                    }
                    Section("Material filings · 90 days") {
                        if w.materialFilings.isEmpty {
                            Text("None on the watched tickers.").font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(w.materialFilings) { f in
                            HStack(alignment: .top, spacing: 6) {
                                Text(f.ticker ?? "").font(.caption.monospacedDigit().weight(.bold)).frame(width: 52, alignment: .leading)
                                VStack(alignment: .leading, spacing: 1) {
                                    HStack(spacing: 4) {
                                        Text(f.form).font(.caption.weight(.semibold))
                                        Text(f.filed).font(.caption2).foregroundStyle(.secondary)
                                    }
                                    if let d = f.description, !d.isEmpty { Text(d).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
                                }
                                Spacer()
                                if let url = URL(string: f.url) {
                                    Link(destination: url) { Image(systemName: "arrow.up.right.square") }.font(.caption)
                                }
                            }
                        }
                    }
                    Section("Watched tickers") {
                        ForEach(w.tickers) { row in
                            HStack {
                                Text(row.ticker).font(.caption.monospacedDigit().weight(.bold)).frame(width: 52, alignment: .leading)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(row.companyName ?? "").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                                    if let e = row.earnings, let next = e.nextDate {
                                        Text("Next earnings \(next)\(e.nextEstimated == true ? " (est.)" : "")" + (e.lastSurprisePct.map { String(format: " · last surprise %+.0f%%", $0) } ?? ""))
                                            .font(.caption2).foregroundStyle(.secondary)
                                    } else if let err = row.error {
                                        Text(err).font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
                                    }
                                }
                                Spacer()
                                Text("\(row.filings.count)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                            }
                            .contentShape(Rectangle())
                            .onTapGesture { store.showTicker(row.ticker) }
                        }
                    }
                    if let note = w.note { Text(note).font(.caption2).foregroundStyle(.tertiary) }
                } else {
                    Text(store.filingsLoading ? "Fetching EDGAR and earnings…" : "No data yet.").font(.caption).foregroundStyle(.secondary)
                }
            }
            .listStyle(.inset)
        }
        .task { if store.filingsWatch == nil { await store.loadFilingsWatch() } }
    }
}

// MARK: - Signal watch strip (Signals blotter)

struct MacSignalMovesStrip: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        HStack(spacing: 10) {
            Label("Score moves", systemImage: "waveform.path.ecg").font(.caption.weight(.semibold))
            if let m = store.signalMoves {
                if m.flagged.isEmpty {
                    Text(m.previousSnapshotAt == nil ? "No snapshot yet — take one to start tracking moves." : "No threshold crossings or big moves since \(MacTimeFormat.relative(m.previousSnapshotAt)).")
                        .font(.caption2).foregroundStyle(.secondary)
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(m.flagged.prefix(12)) { move in
                                Button {
                                    if let c = store.companies.first(where: { $0.id == move.companyId }) { store.showCompany(c) }
                                } label: {
                                    HStack(spacing: 4) {
                                        Text(move.companyName).font(.caption2.weight(.semibold))
                                        Text(move.score.map { "\($0)" } ?? "—").font(.caption2.monospacedDigit())
                                        if let d = move.delta {
                                            Text(String(format: "%+d", d)).font(.caption2.monospacedDigit().weight(.bold))
                                                .foregroundStyle(d >= 0 ? Color.green : Color.red)
                                        }
                                        if move.flags.contains("crossed_up") { Image(systemName: "arrow.up.right").font(.caption2).foregroundStyle(.green) }
                                        if move.flags.contains("crossed_down") { Image(systemName: "arrow.down.right").font(.caption2).foregroundStyle(.red) }
                                    }
                                    .padding(.horizontal, 7).padding(.vertical, 3)
                                    .background(Color.secondary.opacity(0.08), in: Capsule())
                                }
                                .buttonStyle(.plain)
                                .help(move.coverage ?? "")
                            }
                        }
                    }
                }
            } else {
                Text("Loading…").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Snapshot now") { Task { await store.snapshotSignals() } }
                .controlSize(.mini)
                .disabled(!store.canWriteDesk)
                .help("Record every company's signal score; moves are measured against the last snapshot")
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .task { if store.signalMoves == nil { await store.loadSignalMoves() } }
    }
}

// MARK: - No-invented-numbers lint

struct MacNumberLintView: View {
    let companyId: String
    var findText: Binding<MacFindRequest?>? = nil
    @EnvironmentObject private var store: MacAppStore
    @State private var expanded = false

    private var lint: MacNumberLint? { store.numberLintByCompany[companyId] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Numbers lint", systemImage: "number.circle").font(.subheadline.weight(.semibold))
                Spacer()
                if let l = lint {
                    if l.memoPackage == nil {
                        Text("No memo yet").font(.caption2).foregroundStyle(.secondary)
                    } else {
                        Text("\(l.supported) of \(l.checked) figures found in sources")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(l.unsupported == 0 ? Color.green : Color.orange)
                        if l.unsupported > 0 {
                            Button(expanded ? "Hide" : "Show \(l.unsupported)") { expanded.toggle() }.controlSize(.mini)
                        }
                    }
                }
                Button { Task { await store.loadNumberLint(companyId) } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.plain).controlSize(.mini)
            }
            if let l = lint, l.memoPackage != nil {
                if let pct = l.coveragePct {
                    ProgressView(value: Double(pct) / 100).tint(l.unsupported == 0 ? .green : .orange)
                }
                if expanded {
                    ForEach(Array(l.findings.enumerated()), id: \.offset) { _, f in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(f.number).font(.caption.monospacedDigit().weight(.bold)).foregroundStyle(.orange)
                                if !f.section.isEmpty {
                                    if let findText {
                                        Button { findText.wrappedValue = MacFindRequest(text: f.number) } label: { Text("§ \(f.section)").font(.caption2) }
                                            .buttonStyle(.plain).foregroundStyle(Color.accentColor)
                                            .help("Find this figure in the memo")
                                    } else {
                                        Text("§ \(f.section)").font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            Text(f.excerpt).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                        }
                        .padding(6)
                        .background(Color.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 6))
                    }
                    Text("Checked against: " + l.sources.joined(separator: " · ")).font(.caption2).foregroundStyle(.tertiary)
                }
                if let n = l.note, !expanded { Text(n).font(.caption2).foregroundStyle(.tertiary) }
            }
        }
        .padding(10)
        .appleGlassCard()
        .task(id: companyId) { if lint == nil { await store.loadNumberLint(companyId) } }
    }
}

#if os(macOS)
// MARK: - Menu-bar extra

struct MacMenuBarExtraContent: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let s = store.menuBarSummary
        Text("BSH Research")
        Divider()
        Text("\(s.jobs) running job\(s.jobs == 1 ? "" : "s") · \(s.alerts) price alert\(s.alerts == 1 ? "" : "s")")
        Text("\(s.mentions) open mention\(s.mentions == 1 ? "" : "s") · \(s.highHoldings) high holding alert\(s.highHoldings == 1 ? "" : "s")")
        Divider()
        Button("Open Desk") { showDesk() }
        Button("Attention Queue") { showDesk(); store.selectedTab = .attention }
        Button("Command Line…") { showDesk(); store.openCommandPalette() }
        Button("Firm Memory Search…") { showDesk(); store.showFirmSearch = true }
        Button("Chat") { showDesk(); store.showBlotter = true; store.blotterTab = .chat }
        Divider()
        Button("Refresh") { Task { await store.loadMentions(); await store.loadPortfolioDashboard(); await store.refreshJobs() } }
    }

    private func showDesk() {
        NSApp.activate(ignoringOtherApps: true)
        if let desk = NSApp.windows.first(where: { $0.identifier?.rawValue.hasPrefix("main") == true && ($0.isVisible || $0.isMiniaturized) }) {
            desk.makeKeyAndOrderFront(nil)
        } else {
            openWindow(id: "main")
        }
    }
}

// MARK: - Workspace name prompt

enum MacWorkspacePrompt {
    @MainActor
    static func ask(_ completion: @escaping (String) -> Void) {
        let alert = NSAlert()
        alert.messageText = "Save current layout"
        alert.informativeText = "Desk, blotter, portfolio and documents modes and the selected company are saved on this Mac."
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        field.placeholderString = "Layout name"
        alert.accessoryView = field
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Cancel")
        alert.window.initialFirstResponder = field
        if alert.runModal() == .alertFirstButtonReturn {
            completion(field.stringValue)
        }
    }
}
#endif
