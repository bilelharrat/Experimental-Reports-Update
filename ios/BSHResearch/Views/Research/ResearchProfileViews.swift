import SwiftUI

// MARK: - Unified Public/Private Profile Card (Dossier Header)

public struct MacUnifiedProfileView: View {
    public let companyId: String
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var loadAttempted = false

    private var profile: MacCompanyProfile? { store.profileByCompany[companyId] }

    public init(companyId: String) {
        self.companyId = companyId
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Profile", systemImage: "square.on.square.dashed")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                if let p = profile {
                    let isPub = p.publicSide?.ticker != nil
                    MacStatusPill(text: isPub ? "Public" : "Private", color: isPub ? .blue : .purple)
                }
                Button {
                    Task { await store.loadProfile(for: companyId) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .font(.caption)
            }

            if let p = profile {
                VStack(spacing: 12) {
                    HStack(alignment: .top, spacing: 14) {
                        column("Public") {
                            if let q = p.publicSide, let price = q.lastPrice {
                                fact("Ticker", q.ticker ?? "—")
                                fact("Last", String(format: "$%.2f", price), color: (q.changePct1d ?? 0) >= 0 ? .green : .red)
                                fact("1D", q.changePct1d.map { String(format: "%+.2f%%", $0) } ?? "—")
                                fact("Mkt cap", formatUsd(q.marketCapUsd))
                            } else {
                                Text("No public listing").font(.caption2).foregroundStyle(.secondary)
                            }
                        }

                        Divider()

                        column("Private") {
                            if let pr = p.privateSide {
                                fact("Position", pr.position ?? "—")
                                fact("Own", pr.ownershipPct.map { String(format: "%.1f%%", $0) } ?? "—")
                                fact("ARR", formatUsd(pr.arrUsd))
                                fact("Runway", pr.runwayMonths.map { String(format: "%.0f mo", $0) } ?? "—",
                                     color: (pr.runwayMonths ?? 99) < 9 ? .red : .primary)
                                fact("Mark · MOIC", [formatUsd(pr.currentMarkUsd), pr.moic.map { String(format: "%.2fx", $0) }].compactMap { $0 }.joined(separator: " · "))
                            } else {
                                Text("No private position").font(.caption2).foregroundStyle(.secondary)
                            }
                        }

                        Divider()

                        column("Process") {
                            fact("Stage", store.dealPipelines[companyId]?.stage ?? p.process?.stage ?? "Sourced")
                            fact("Thesis fit", p.process?.thesisFit ?? "—")
                            fact("Decision", p.process?.lastDecision?.capitalized ?? "—",
                                 color: p.process?.lastDecision == "invest" ? .green : (p.process?.lastDecision == "pass" ? .red : .primary))
                            fact("IC", "\(p.process?.icVotesCount ?? 0) votes")
                        }
                    }
                }
            } else if loadAttempted {
                HStack(spacing: 8) {
                    Text("Profile currently unpopulated on server.").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Button("Retry") {
                        Task { await load() }
                    }
                    .font(.caption2.weight(.medium))
                }
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: companyId) {
            loadAttempted = false
            if profile == nil { await load() }
        }
    }

    private func load() async {
        await store.loadProfile(for: companyId)
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
        HStack(spacing: 4) {
            Text(label).font(.caption2).foregroundStyle(.secondary).frame(width: 60, alignment: .leading)
            Text(value.isEmpty ? "—" : value).font(.caption.monospacedDigit()).foregroundStyle(color).lineLimit(1)
        }
    }

    private func formatUsd(_ val: Double?) -> String {
        guard let v = val else { return "—" }
        if v >= 1e9 { return String(format: "$%.1fB", v / 1e9) }
        if v >= 1e6 { return String(format: "$%.1fM", v / 1e6) }
        if v >= 1e3 { return String(format: "$%.0fK", v / 1e3) }
        return String(format: "$%.0f", v)
    }
}

// MARK: - Signal Score Meter & Breakdown

public struct MacSignalScoreView: View {
    public let companyId: String
    public var compact: Bool = false
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var expanded: Bool = false

    private var score: MacSignalScore? { store.signalScoreByCompany[companyId] }

    public init(companyId: String, compact: Bool = false) {
        self.companyId = companyId
        self.compact = compact
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                ZStack {
                    Circle().stroke(Color.secondary.opacity(0.15), lineWidth: 5)
                    Circle()
                        .trim(from: 0, to: CGFloat(score?.score ?? 0) / 100)
                        .stroke(color, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                    Text(score?.score.map { "\($0)" } ?? "—")
                        .font(.system(size: compact ? 12 : 16, weight: .bold, design: .rounded))
                        .monospacedDigit()
                }
                .frame(width: compact ? 38 : 50, height: compact ? 38 : 50)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Signal score").font(compact ? .dsSubhead : .dsHeadline)
                    Text(score?.headline ?? "Quantitative traction & composite signal strength")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer()

                Button(expanded ? "Hide" : "Breakdown") {
                    withAnimation { expanded.toggle() }
                }
                .font(.caption2.weight(.medium))

                Button {
                    Task { await store.loadSignalScore(for: companyId) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .font(.caption)
                .buttonStyle(.plain)
            }

            if expanded, let b = score?.breakdown {
                VStack(spacing: 6) {
                    barRow("Market Momentum", val: b.momentum)
                    barRow("Fundamental Health", val: b.fundamentals)
                    barRow("Developer Traction", val: b.devTraction)
                    barRow("Sentiment Index", val: b.sentiment)
                    barRow("Risk Adjusted", val: b.riskAdjusted)
                }
                .padding(10)
                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(compact ? 10 : 14)
        .appleGlassCard()
        .task(id: companyId) {
            if score == nil { await store.loadSignalScore(for: companyId) }
        }
    }

    private var color: Color {
        guard let s = score?.score else { return .secondary }
        return s >= 70 ? .green : (s >= 40 ? .orange : .red)
    }

    private func barRow(_ title: String, val: Double?) -> some View {
        HStack {
            Text(title).font(.caption).foregroundStyle(.secondary).frame(width: 140, alignment: .leading)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.secondary.opacity(0.12))
                    Capsule().fill(Color.accentColor).frame(width: geo.size.width * CGFloat(min(max((val ?? 0) / 100, 0), 1)))
                }
            }
            .frame(height: 6)
            Text(val.map { String(format: "%.0f", $0) } ?? "—")
                .font(.caption.monospacedDigit().weight(.semibold))
                .frame(width: 28, alignment: .trailing)
        }
    }
}
