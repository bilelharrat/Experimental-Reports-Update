import SwiftUI

/// Bottom strip: every running Claude job with a live log, plus fired price alerts.
struct MacBlotterView: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var confirmDelete: MacJobHistoryRow?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            switch store.blotterTab {
            case .jobs:
                jobsPane
            case .alerts:
                alertsPane
            case .signals:
                MacSignalsPane()
            case .chat:
                MacFirmChatPane()
            case .audit:
                MacAuditPane()
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .confirmationDialog(
            "Delete this report record?",
            isPresented: Binding(get: { confirmDelete != nil }, set: { if !$0 { confirmDelete = nil } }),
            presenting: confirmDelete
        ) { row in
            Button("Delete", role: .destructive) {
                if let id = row.reportId {
                    Task { await store.deleteReport(id: id) }
                }
            }
        } message: { row in
            Text("\(row.title ?? "This memo") leaves the library. The run folder stays on disk.")
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 12) {
            GlassSegmentedPicker("Panel", selection: $store.blotterTab, segments: [
                .jobs: "Jobs \(store.activeJobs.isEmpty ? "" : "· \(store.activeJobs.count)")",
                .alerts: "Alerts \(store.alertEvents.isEmpty ? "" : "· \(min(store.alertEvents.count, 99))")\(store.unseenAlertCount > 0 ? " · \(store.unseenAlertCount) new" : "")",
                .signals: "Signals \(store.signals.isEmpty ? "" : "· \(store.signals.count)")",
                .chat: "Chat \((store.mentions?.openCount ?? 0) == 0 ? "" : "· @\(store.mentions?.openCount ?? 0)")",
                .audit: "Audit",
            ])
            .frame(width: 460)

            Spacer()

            switch store.blotterTab {
            case .jobs:
                Button {
                    Task { await store.refreshJobs() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .controlSize(.small)
            case .signals:
                Button {
                    Task { await store.loadSignals() }
                } label: {
                    Label("Re-score", systemImage: "arrow.clockwise")
                }
                .controlSize(.small)
                .disabled(store.signalsLoading)
                .help("Score every logged call against live prices")
            case .alerts:
                if let last = store.lastAlertCheck {
                    Text("Checked \(last.formatted(date: .omitted, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(!MacAppStore.isUSMarketOpen()
                     ? "Market closed"
                     : (store.armedAlertRules.isEmpty ? "Market open · no armed alert rules" : "Market open · auto-check every minute"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button {
                    Task { await store.runAlertCheck(notify: true, reveal: true) }
                } label: {
                    Label("Check now", systemImage: "bell.badge")
                }
                .controlSize(.small)
                .disabled(store.checkingAlerts || store.armedAlertRules.isEmpty)
                .help(store.armedAlertRules.isEmpty ? "No enabled price or % alert rules on the desk yet" : "Evaluate every rule against live quotes")
            case .chat, .audit:
                EmptyView()
            }

            Button {
                store.showBlotter = false
            } label: {
                Image(systemName: "xmark")
            }
            .buttonStyle(.plain)
            .help("Hide blotter (⌥⌘J)")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }

    // MARK: - Jobs

    private var jobsPane: some View {
        HSplitView {
            List(selection: $store.selectedJobId) {
                if !store.activeJobs.isEmpty {
                    Section("Running") {
                        ForEach(store.activeJobs) { job in
                            activeRow(job).tag(job.id)
                                .glassListRow(isSelected: store.selectedJobId == job.id)
                        }
                    }
                }
                Section(store.activeJobs.isEmpty ? "Recent" : "Finished") {
                    if store.jobHistory.isEmpty {
                        Text("No AI tasks yet. Start a memo with ⌘N.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(store.jobHistory) { row in
                        historyRow(row).tag(row.reportId ?? row.id)
                            .glassListRow(isSelected: store.selectedJobId == (row.reportId ?? row.id))
                    }
                }
            }
            .listStyle(.inset)
            .frame(minWidth: 420)
            .layoutPriority(1)

            logPane
                .frame(minWidth: 260, idealWidth: 380)
                .layoutPriority(0)
        }
    }

    private func activeRow(_ job: MacActiveJob) -> some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(job.title ?? job.kind ?? "Task")
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                    if let cid = job.companyId, let company = store.companies.first(where: { $0.id == cid }) {
                        Text(company.name ?? cid)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Text(job.stageText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            if let progress = job.progress {
                Text("\(progress)%")
                    .font(.caption.monospacedDigit().weight(.bold))
                    .foregroundStyle(Color.accentColor)
            }
            if !job.elapsedText.isEmpty {
                Text(job.elapsedText)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .frame(width: 64, alignment: .trailing)
            }

            if job.reportReady, let report = store.report(for: job.reportId), report.canOpen {
                Button("Open") { store.openReportWindow(report) }
                    .controlSize(.small)
            }
            if job.isMemo, job.reportId != nil {
                Button("Cancel") {
                    Task { await store.cancelJob(job) }
                }
                .controlSize(.small)
                .disabled(!store.canRunTasks)
            }
        }
        .padding(.vertical, 2)
    }

    private func historyRow(_ row: MacJobHistoryRow) -> some View {
        let report = store.report(for: row.reportId)
        return HStack(spacing: 10) {
            Image(systemName: row.failed ? "xmark.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(row.failed ? Color.red : Color.green)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(row.title ?? row.kind ?? "Task")
                        .font(.subheadline.weight(.medium))
                        .lineLimit(1)
                    if let cid = row.companyId, let company = store.companies.first(where: { $0.id == cid }) {
                        Text(company.name ?? cid)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Text([row.outcomeLabel, MacTimeFormat.relative(row.finishedAt), row.error ?? row.subtitle ?? ""]
                        .filter { !$0.isEmpty }
                        .joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(row.failed ? Color.red.opacity(0.85) : Color.secondary)
                    .lineLimit(1)
            }

            Spacer()

            if let cost = row.claudeCostUsd {
                Text(String(format: "$%.2f", cost))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            if let report, report.canOpen {
                Button("Open") { store.openReportWindow(report) }
                    .controlSize(.small)
            }
            if row.canResume, let id = row.reportId {
                Button("Resume") { Task { await store.resumeReport(id: id) } }
                    .controlSize(.small)
                    .disabled(!store.canRunTasks)
            }
            if row.canDismiss, let id = row.reportId {
                Button("Dismiss") { Task { await store.dismissReport(id: id) } }
                    .controlSize(.small)
                    .disabled(!store.canRunTasks)
            }
            if report != nil {
                Button {
                    confirmDelete = row
                } label: {
                    Image(systemName: "trash")
                }
                .controlSize(.small)
                .disabled(!store.canDeleteDocuments)
                .help("Delete report record")
            }
        }
        .padding(.vertical, 2)
    }

    private var logPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Live log")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                if let id = store.selectedJobId, store.activeJobs.contains(where: { $0.id == id }) {
                    Text("streaming")
                        .font(.caption2)
                        .foregroundStyle(Color.green)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            Divider()

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(selectedLogLines.enumerated()), id: \.offset) { index, line in
                            Text(line)
                                .font(.caption.monospacedDigit())
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(index)
                        }
                        if selectedLogLines.isEmpty {
                            Text(store.selectedJobId == nil ? "Select a job to follow its log." : "Waiting for events…")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                }
                .onChange(of: selectedLogLines.count) { _, count in
                    if count > 0 { proxy.scrollTo(count - 1, anchor: .bottom) }
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
    }

    private var selectedLogLines: [String] {
        guard let id = store.selectedJobId else { return [] }
        if let lines = store.jobLogs[id], !lines.isEmpty { return lines }
        if let row = store.jobHistory.first(where: { ($0.reportId ?? $0.id) == id }) {
            return [row.outcomeLabel, row.error ?? "", row.subtitle ?? ""].filter { !$0.isEmpty }
        }
        return []
    }

    // MARK: - Alerts

    private var alertsPane: some View {
        List {
            if store.alertEvents.isEmpty {
                Text(store.alertRules.isEmpty
                     ? "No alert rules yet — add one from Market Radar."
                     : "No alerts have fired. \(store.armedAlertRules.count) rule(s) armed.")
                    .foregroundStyle(.secondary)
            }
            ForEach(store.alertEvents) { event in
                HStack(spacing: 10) {
                    Image(systemName: "bell.fill")
                        .foregroundStyle(Color.orange)
                    Text(event.ticker ?? "—")
                        .font(.subheadline.monospacedDigit().weight(.bold))
                        .frame(width: 64, alignment: .leading)
                    Text(event.headline)
                        .font(.subheadline)
                        .lineLimit(1)
                    Spacer()
                    if let price = event.lastPrice {
                        Text(String(format: "$%.2f", price))
                            .font(.caption.monospacedDigit())
                    }
                    Text(MacTimeFormat.relative(event.firedAt))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(width: 70, alignment: .trailing)
                    if let ticker = event.ticker {
                        Button("Chart") { store.showTicker(ticker) }
                            .controlSize(.small)
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .listStyle(.inset)
    }
}

// MARK: - Signal log (⌘L)

/// Log a call from Market Radar or a news brief; the server scores it against live prices.
struct MacSignalsPane: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var ticker = ""
    @State private var direction = "bullish"
    @State private var label = ""
    @State private var saving = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                TextField("Ticker", text: $ticker)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 90)
                    .onSubmit { log() }
                GlassSegmentedPicker("Direction", selection: $direction, segments: ["bullish": "Bullish", "bearish": "Bearish", "watch": "Watch"])
                .frame(width: 220)
                TextField("What's the call? (e.g. breakout above 200d, guide raise into print)", text: $label)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { log() }
                Button(saving ? "Logging…" : "Log signal") { log() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(saving || !store.canWriteDesk || ticker.trimmingCharacters(in: .whitespaces).isEmpty)
                    .help(store.canWriteDesk ? "Record the call in the signal ledger" : "A read-only session cannot log signals")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider()

            MacSignalMovesStrip()

            Divider()

            List {
                if store.signals.isEmpty {
                    Text(store.signalsLoading ? "Loading…" : "No signals logged yet. Log a call above — the ledger scores it against live prices over time.")
                        .foregroundStyle(.secondary)
                }
                ForEach(store.signals) { signal in
                    HStack(spacing: 10) {
                        Text(signal.ticker)
                            .font(.subheadline.monospacedDigit().weight(.bold))
                            .frame(width: 64, alignment: .leading)
                        Text(signal.direction.capitalized)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(signal.direction == "bullish" ? Color.green : (signal.direction == "bearish" ? Color.red : Color.orange))
                            .frame(width: 56, alignment: .leading)
                        Text(signal.label ?? "").font(.subheadline).lineLimit(1)
                        Spacer()
                        if let base = signal.priceAtSignal {
                            Text(String(format: "@ %.2f", base)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }
                        if let last = signal.lastPrice {
                            Text(String(format: "→ %.2f", last)).font(.caption.monospacedDigit())
                        }
                        if let score = signal.scorePct {
                            Text(String(format: "%+.1f%%", score))
                                .font(.caption.monospacedDigit().weight(.bold))
                                .foregroundStyle(score >= 0 ? Color.green : Color.red)
                                .frame(width: 60, alignment: .trailing)
                        } else if let ret = signal.returnSincePct {
                            Text(String(format: "%+.1f%%", ret))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                                .frame(width: 60, alignment: .trailing)
                        }
                        Text(MacTimeFormat.relative(signal.recordedAt))
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(width: 70, alignment: .trailing)
                        Button("Chart") { store.showTicker(signal.ticker) }.controlSize(.small)
                        Button {
                            Task { await store.deleteSignal(id: signal.id) }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .controlSize(.small)
                        .disabled(!store.canWriteDesk)
                    }
                    .padding(.vertical, 2)
                }
            }
            .listStyle(.inset)
        }
        .task {
            if store.signals.isEmpty { await store.loadSignals() }
            if let seed = store.signalSeedTicker, ticker.isEmpty { ticker = seed }
        }
        .onChange(of: store.signalSeedTicker) { _, seed in
            if let seed { ticker = seed }
        }
    }

    private func log() {
        let t = ticker.trimmingCharacters(in: .whitespaces).uppercased()
        guard !t.isEmpty, store.canWriteDesk, !saving else { return }
        saving = true
        Task {
            if await store.logSignal(ticker: t, direction: direction, label: label.trimmingCharacters(in: .whitespaces)) {
                label = ""
            }
            saving = false
        }
    }
}
