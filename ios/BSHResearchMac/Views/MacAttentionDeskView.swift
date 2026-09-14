import SwiftUI

/// ⌘0 — "what needs me today": pipeline attention, stale coverage & drawdowns,
/// what changed since the last launch, and uploads nobody has filed.
struct MacAttentionDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    private var attention: [MacAttentionItem] { store.rollup?.attention ?? [] }
    private var staleCoverage: [MacScreenerItem] { store.screenerItems.filter { $0.kind == "stale_memo" } }
    private var drawdowns: [MacScreenerItem] { store.screenerItems.filter { $0.kind == "drawdown" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Attention Queue").font(.title2.weight(.bold))
                        Text(summaryLine).font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if store.attentionLoading { ProgressView().controlSize(.small) }
                    Button {
                        Task { await store.loadAttention() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .disabled(store.attentionLoading)
                }

                section("Needs a decision or a fix", systemImage: "exclamationmark.triangle", count: attention.count, empty: "Nothing is blocked on you. The pipeline is clear.") {
                    ForEach(attention) { item in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: item.isHigh ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                                .foregroundStyle(item.isHigh ? Color.red : Color.orange)
                                .frame(width: 20)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(item.companyName ?? item.companyId ?? "").font(.subheadline.weight(.semibold))
                                    Text(item.label ?? item.kind ?? "").font(.subheadline)
                                }
                                if let detail = item.detail, !detail.isEmpty {
                                    Text(detail).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                            Spacer()
                            if let cid = item.companyId, let company = store.companies.first(where: { $0.id == cid }) {
                                Button("Open") { store.showCompany(company) }
                                    .controlSize(.small)
                                Button {
                                    store.askWarren(
                                        actionPrompt(for: item),
                                        context: .attention(kind: item.kind ?? "", detail: item.detail, count: item.count),
                                        company: company
                                    )
                                } label: {
                                    Image(systemName: "sparkles")
                                }
                                .controlSize(.small)
                                .disabled(!store.canRunTasks)
                                .help("Ask Warren about this")
                            }
                        }
                        .padding(10)
                        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                    }
                }

                HStack(alignment: .top, spacing: 16) {
                    section("Stale coverage", systemImage: "clock.badge.exclamationmark", count: staleCoverage.count, empty: "Every company has a memo from the last 30 days.") {
                        ForEach(staleCoverage) { item in
                            HStack(spacing: 8) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(item.title ?? item.id).font(.subheadline.weight(.medium))
                                    Text(item.detail ?? "").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if let cid = item.companyId, let company = store.companies.first(where: { $0.id == cid }) {
                                    Button("Dossier") { store.showCompany(company) }.controlSize(.small)
                                    Button("Memo…") { store.requestNewReport(for: company) }
                                        .controlSize(.small)
                                        .disabled(!store.canRunTasks)
                                }
                            }
                            .padding(8)
                            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                    .frame(maxWidth: .infinity)

                    section("Watchlist drawdowns", systemImage: "arrow.down.right.circle", count: drawdowns.count, empty: "No pinned ticker is down more than 3% today.") {
                        ForEach(drawdowns) { item in
                            HStack(spacing: 8) {
                                Text(item.ticker ?? "").font(.subheadline.monospaced().weight(.bold))
                                Text(item.title ?? "").font(.subheadline).foregroundStyle(Color.red)
                                Spacer()
                                if let t = item.ticker {
                                    Button("Chart") { store.showTicker(t) }.controlSize(.small)
                                }
                            }
                            .padding(8)
                            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                    .frame(maxWidth: .infinity)
                }

                section("What changed since last launch", systemImage: "sparkles.rectangle.stack", count: store.digestItems.count, empty: "Nothing moved, landed or finished since you were last here.") {
                    ForEach(store.digestItems) { item in
                        HStack(spacing: 10) {
                            Image(systemName: digestIcon(item.kind))
                                .foregroundStyle(.secondary)
                                .frame(width: 18)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(item.title ?? "").font(.subheadline.weight(.medium)).lineLimit(1)
                                Text(item.detail ?? "").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            }
                            Spacer()
                            if let rid = item.reportId, let report = store.report(for: rid), report.canOpen {
                                Button("Open memo") { store.openReportWindow(report) }.controlSize(.small)
                            } else if item.kind == "news", let href = item.href, let url = URL(string: href) {
                                Link(destination: url) { Image(systemName: "arrow.up.right.square") }
                            } else if let t = item.ticker, !t.isEmpty, item.kind == "mover" {
                                Button("Chart") { store.showTicker(t) }.controlSize(.small)
                            }
                        }
                        .padding(8)
                        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                    }
                }

                section("Unfiled uploads", systemImage: "tray.full", count: store.intakeItems.count, empty: "Every upload has been filed to a company.") {
                    ForEach(store.intakeItems) { item in
                        HStack(spacing: 10) {
                            Image(systemName: "doc.badge.ellipsis").foregroundStyle(.secondary).frame(width: 18)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(item.title ?? item.id).font(.subheadline.weight(.medium)).lineLimit(1)
                                HStack(spacing: 6) {
                                    if let kind = item.kind { Text(kind.replacingOccurrences(of: "_", with: " ")).font(.caption).foregroundStyle(.secondary) }
                                    if let a = item.assignment {
                                        if let name = a.companyName {
                                            Text("→ \(name) (\(Int((a.companyConfidence ?? 0) * 100))%)").font(.caption).foregroundStyle(.secondary)
                                        } else if let reason = a.reviewReason, !reason.isEmpty {
                                            Text(reason).font(.caption).foregroundStyle(Color.orange)
                                        }
                                    }
                                    Text(MacTimeFormat.relative(item.createdAt)).font(.caption).foregroundStyle(.tertiary)
                                }
                            }
                            Spacer()
                            Button("Resolve on web") {
                                store.openInEmbeddedBrowser(MacConfig.webURL(path: "source-library"))
                            }
                            .controlSize(.small)
                        }
                        .padding(8)
                        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: 1100, alignment: .leading)
        }
        .task {
            if store.attentionLoadedAt == nil {
                await store.loadAttention()
                store.stampLaunch()
            }
        }
    }

    private var summaryLine: String {
        var parts: [String] = []
        if !attention.isEmpty { parts.append("\(attention.count) blocked") }
        if !staleCoverage.isEmpty { parts.append("\(staleCoverage.count) stale") }
        if !drawdowns.isEmpty { parts.append("\(drawdowns.count) drawdowns") }
        if !store.digestItems.isEmpty { parts.append("\(store.digestItems.count) changes") }
        if !store.intakeItems.isEmpty { parts.append("\(store.intakeItems.count) unfiled") }
        if parts.isEmpty { return store.attentionLoadedAt == nil ? "Loading…" : "All clear." }
        return parts.joined(separator: " · ")
    }

    private func actionPrompt(for item: MacAttentionItem) -> String {
        switch item.kind {
        case "memo_failed": return "The memo run failed. Explain the failure and the concrete next step."
        case "evidence_contradicted": return "List the contradicted evidence claims and propose how to resolve each one."
        case "memo_warnings": return "Walk through the memo's quality warnings and which ones matter for the investment committee."
        case "risks_open": return "Which open risks should we research first, and what evidence would close them?"
        case "evidence_missing": return "Where are the evidence gaps in our thesis, ranked by how much they could change the decision?"
        case "unapproved_work": return "Summarize the unapproved analysis work and whether it's ready to approve for the memo."
        default: return "What needs my attention on this company right now?"
        }
    }

    private func digestIcon(_ kind: String?) -> String {
        switch kind {
        case "mover": return "chart.line.uptrend.xyaxis"
        case "news": return "newspaper"
        case "memo": return "doc.text"
        default: return "circle"
        }
    }

    private func section<Content: View>(_ title: String, systemImage: String, count: Int, empty: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(title, systemImage: systemImage).font(.headline)
                if count > 0 {
                    Text("\(count)").font(.caption.weight(.bold)).foregroundStyle(.secondary)
                }
                Spacer()
            }
            if count == 0 {
                Text(empty).font(.caption).foregroundStyle(.secondary)
            } else {
                content()
            }
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}
