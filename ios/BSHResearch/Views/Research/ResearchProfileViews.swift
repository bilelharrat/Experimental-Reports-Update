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
                    MacStatusPill(text: p.isPublic ? "Public" : "Private", color: p.isPublic ? .blue : .purple)
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
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top, spacing: 14) {
                        column("Public") {
                            if let q = p.publicSide, let price = q.lastPrice {
                                fact("Ticker", q.ticker ?? "—")
                                fact("Last", String(format: "$%.2f", price), color: (q.changePct1d ?? 0) >= 0 ? .green : .red)
                                fact("1D", q.changePct1d.map { String(format: "%+.2f%%", $0) } ?? "—")
                                fact("Mkt cap", formatUsd(q.marketCap))
                            } else {
                                Text(p.isPublic ? "Quote unavailable" : "No public listing").font(.caption2).foregroundStyle(.secondary)
                            }
                        }

                        Divider()

                        // A listed company is not a startup deal: unless the firm
                        // holds it, show how the market values it instead of
                        // Position / ARR / Runway / Mark, which read "—" for
                        // every public name.
                        if p.isPublic && p.privateSide == nil {
                            column("Market") {
                                let q = p.publicSide
                                fact("P/E", q?.peRatio.map { String(format: "%.1f", $0) } ?? "—")
                                fact("EPS", q?.eps.map { String(format: "$%.2f", $0) } ?? "—")
                                fact("52-wk", {
                                    guard let low = q?.fiftyTwoWeekLow, let high = q?.fiftyTwoWeekHigh else { return "—" }
                                    return String(format: "$%.0f – $%.0f", low, high)
                                }())
                                fact("Yield", q?.dividendYield.map { String(format: "%.2f%%", $0 * 100) } ?? "—")
                            }
                        } else {
                            column("Private") {
                                if p.privateSide != nil || !p.reported.isEmpty {
                                    let pr = p.privateSide
                                    fact("Position", [pr?.round, pr?.investedUsd.map { formatUsd($0) }].compactMap { $0 }.joined(separator: " · "))
                                    fact("Own", pr?.ownershipPct.map { String(format: "%.1f%%", $0) } ?? "—")
                                    // The portfolio KPI when there is one, else the
                                    // company record's own figure — the one the memo
                                    // quotes — with its date.
                                    if let arr = pr?.arrUsd {
                                        fact("ARR", formatUsd(arr))
                                    } else {
                                        reportedFact("ARR", p.reported["arr"])
                                    }
                                    if let runway = pr?.runwayMonths {
                                        fact("Runway", String(format: "%.0f mo", runway), color: runway < 9 ? .red : .primary)
                                    } else {
                                        reportedFact("Runway", p.reported["runway"])
                                    }
                                    fact("Mark · MOIC", [pr?.markUsd.map { formatUsd($0) }, pr?.moic.map { String(format: "%.2fx", $0) }].compactMap { $0 }.joined(separator: " · "))
                                } else {
                                    Text("No private position").font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }

                        Divider()

                        column("Process") {
                            // Deal stage and VC thesis fit mean nothing for a listed name.
                            if !p.isPublic {
                                fact("Stage", store.dealPipelines[companyId]?.stage ?? p.pipelineStage ?? "Sourced")
                                fact("Thesis fit", p.thesisFitScore.map { "\($0)%" } ?? (p.thesisFitLabel ?? "—").capitalized)
                            }
                            fact("Decision", p.latestVerdict?.capitalized ?? "—",
                                 color: p.latestVerdict == "invest" ? .green : (p.latestVerdict == "pass" ? .red : .primary))
                            fact("IC", (p.icOpenMeeting ? "Meeting open" : "\(p.icMeetingCount) meetings") + " · \(p.icReferenceCalls) refs")
                            fact("On file", "\(p.filesCount) files · \(p.openCommentsCount) comments")
                        }
                    }
                    if let description = p.description, !description.isEmpty {
                        Text(description).font(.caption).foregroundStyle(.secondary).lineLimit(2)
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

    /// A figure from the company record, with its as-of month beside it.
    private func reportedFact(_ label: String, _ fact: MacCompanyProfile.Reported?) -> some View {
        HStack(spacing: 4) {
            Text(label).font(.caption2).foregroundStyle(.secondary).frame(width: 60, alignment: .leading)
            Text(fact?.value ?? "—").font(.caption.monospacedDigit()).lineLimit(1)
            if let asOf = fact?.asOfShort {
                Text(asOf).font(.caption2.monospacedDigit()).foregroundStyle(.tertiary).lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func formatUsd(_ val: Double?) -> String {
        guard let v = val else { return "—" }
        if v >= 1e12 { return String(format: "$%.2fT", v / 1e12) }
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
                        // A partial read keeps its number but not full strength.
                        .opacity(score?.isPartial == true ? 0.4 : 1)
                    Text(score?.score.map { "\($0)" } ?? "—")
                        .font(.system(size: compact ? 12 : 16, weight: .bold, design: .rounded))
                        .monospacedDigit()
                }
                .frame(width: compact ? 38 : 50, height: compact ? 38 : 50)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("Signal score").font(compact ? .dsSubhead : .dsHeadline)
                        if let s = score, s.isPartial {
                            MacStatusPill(text: "Partial · \(s.availableCount) of \(s.components.count)", color: .orange)
                        }
                    }
                    Text(subtitle)
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer()

                if score?.components.isEmpty == false {
                    Button(expanded ? "Hide" : "Breakdown") {
                        withAnimation { expanded.toggle() }
                    }
                    .font(.caption2.weight(.medium))
                }

                Button {
                    Task { await store.loadSignalScore(for: companyId) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .font(.caption)
                .buttonStyle(.plain)
            }

            if expanded, let s = score {
                VStack(spacing: 6) {
                    ForEach(s.components) { c in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(c.name).font(.caption).foregroundStyle(.secondary).frame(width: 130, alignment: .leading)
                            Text(c.available ? String(format: "%.1f / %d", c.points ?? 0, c.max) : "not scored · \(c.max) max")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(c.available ? Color.primary : Color.secondary)
                            Spacer(minLength: 0)
                        }
                    }
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

    /// The server's own coverage line, e.g. "2 of 6 components have data".
    private var subtitle: String {
        guard let s = score else { return "Loading…" }
        if s.score == nil {
            return "Insufficient data · \(s.availableCount) of \(s.components.count)"
        }
        return (s.coverage ?? "").replacingOccurrences(of: " have data", with: " with data")
    }

    private var color: Color {
        guard let s = score?.score else { return .secondary }
        return s >= 70 ? .green : (s >= 40 ? .orange : .red)
    }
}

// MARK: - Earnings & filings (a listed company's Overview)

/// The public-company counterpart of the deal pipeline: when it next reports,
/// how recent quarters landed against the estimate, and what it filed.
/// Twin of the Mac's MacEarningsFilingsView and the web's EarningsFilingsCard.
public struct MacEarningsFilingsView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var refreshing = false

    public init(company: MacCompany) {
        self.company = company
    }

    private var data: MacCompanyEarningsFilings? { store.earningsFilingsByCompany[company.id] }
    private var failed: Bool { store.earningsFilingsFailed.contains(company.id) }

    /// Five rows, material filings first in line for them, newest-first.
    private var filings: [MacFiling] {
        let rows = data?.filings ?? []
        let material = rows.filter(\.material)
        let rest = rows.filter { !$0.material }
        return (Array(material.prefix(5)) + Array(rest.prefix(max(0, 5 - material.count))))
            .sorted { $0.filed > $1.filed }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            MacCardHeader(
                "Earnings & filings",
                subtitle: "Next report, recent quarters against estimates, and SEC filings from the last 90 days.",
                systemImage: "chart.line.uptrend.xyaxis"
            ) {
                Button {
                    Task {
                        refreshing = true
                        await store.loadEarningsFilings(for: company.id, refresh: true)
                        refreshing = false
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .font(.caption)
                .disabled(refreshing)
                .accessibilityLabel("Refresh earnings and filings")
            }

            if data == nil && failed {
                HStack(spacing: 8) {
                    Text("Earnings and filings couldn't be loaded.").font(.dsCaption).foregroundStyle(.secondary)
                    Button("Retry") { Task { await store.loadEarningsFilings(for: company.id) } }
                        .font(.caption2.weight(.medium))
                }
            } else if let data {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 10) {
                        nextReportTile(data.earnings)
                        quartersTile(data.earnings?.history ?? [])
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        nextReportTile(data.earnings)
                        quartersTile(data.earnings?.history ?? [])
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("SEC filings · 90 days").font(.dsLabel).foregroundStyle(.secondary)
                    if filings.isEmpty {
                        Text(data.error ?? "No watched filings in the last 90 days.")
                            .font(.dsCaption).foregroundStyle(.secondary)
                    }
                    ForEach(filings) { filing in
                        filingRow(filing)
                    }
                }
            } else {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Loading earnings and filings…").font(.dsCaption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            if data == nil { await store.loadEarningsFilings(for: company.id) }
        }
    }

    private func nextReportTile(_ earnings: MacCompanyEarningsFilings.Earnings?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("Next earnings", systemImage: "calendar.badge.clock")
                .font(.dsLabel)
                .foregroundStyle(Color.accentColor)
            if let date = earnings?.nextDate {
                Text(date).font(.headline.monospacedDigit())
                Text([whenText(earnings?.daysToNext), earnings?.nextEstimated == true ? "estimated" : nil]
                        .compactMap { $0 }.joined(separator: " · "))
                    .font(.dsCaption).foregroundStyle(.secondary)
            } else {
                Text("Not set").font(.dsCaption).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .appleGlassTile(cornerRadius: 10, tint: Color.accentColor)
    }

    private func quartersTile(_ quarters: [MacCompanyEarningsFilings.Quarter]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Quarters vs. estimates").font(.dsLabel).foregroundStyle(.secondary)
            if quarters.isEmpty {
                Text("No earnings history available for this ticker.").font(.dsCaption).foregroundStyle(.secondary)
            }
            ForEach(quarters) { q in
                HStack(spacing: 6) {
                    Text(q.period ?? q.reported ?? "").font(.caption2).foregroundStyle(.secondary)
                        .frame(width: 58, alignment: .leading)
                    Text("EPS \(money(q.eps)) vs \(money(q.estimate))").font(.caption.monospacedDigit()).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(surprise(q.surprisePct))
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(surpriseColor(q.surprisePct))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .appleGlassTile(cornerRadius: 10)
    }

    @ViewBuilder
    private func filingRow(_ filing: MacFiling) -> some View {
        let row = HStack(spacing: 8) {
            Text(filing.form).font(.caption.monospacedDigit().weight(.semibold)).frame(width: 48, alignment: .leading)
            Text(filing.plainLabel).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            Spacer(minLength: 6)
            if filing.material { MacStatusPill(text: "Material", color: .orange) }
            Text(filing.filed).font(.caption2.monospacedDigit()).foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .appleGlassTile(cornerRadius: 8)
        if let url = URL(string: filing.url) {
            Link(destination: url) { row }.buttonStyle(.plain)
        } else {
            row
        }
    }

    private func whenText(_ days: Int?) -> String? {
        guard let days else { return nil }
        if days == 0 { return "today" }
        return days > 0 ? "in \(days) days" : "\(-days) days ago"
    }

    private func money(_ value: Double?) -> String {
        value.map { String(format: "$%.2f", $0) } ?? "—"
    }

    private func surprise(_ pct: Double?) -> String {
        guard let pct else { return "—" }
        return String(format: "%+.1f%%", pct)
    }

    private func surpriseColor(_ pct: Double?) -> Color {
        guard let pct, pct != 0 else { return .secondary }
        return pct > 0 ? .green : .red
    }
}
