//
//  MacFounderRadarView.swift
//  BSHResearchMac
//
//  Founder pedigree and developer traction, read from the company record.
//  Displays leadership, board, headcount and open-source velocity when recorded;
//  the refresh button re-reads the record (no external lookup).
//

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

struct MacFounderRadarView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    private var dossier: MacFounderDossier? {
        store.founderDossiers[company.id]
    }

    private var isSearching: Bool {
        store.deepSearchingFounders.contains(company.id)
    }

    @State private var loadFailed = false
    @State private var loading = false

    private func hasPeople(_ dossier: MacFounderDossier) -> Bool {
        !dossier.founders.isEmpty
            || !(dossier.advisorsAndBoard ?? []).isEmpty
            || dossier.teamHeadcount != nil
            || dossier.developerTraction != nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            MacCardHeader("Founders & team", subtitle: "People from the company record, prior companies and exits, and open-source velocity when a repo is known.", systemImage: "person.3") {
                Button {
                    // No token confirmation: the deep search rebuilds the
                    // dossier from the company record and calls no model.
                    Task {
                        await store.deepSearchFounder(for: company.id)
                    }
                } label: {
                    HStack(spacing: 6) {
                        if isSearching {
                            ProgressView()
                                .controlSize(.small)
                            Text("Refreshing…")
                        } else {
                            Image(systemName: "arrow.clockwise")
                            Text("Refresh from record")
                        }
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(isSearching)
                .help("Re-read people, board and links from the company record")
            }

            if let dossier = dossier {
                if !hasPeople(dossier) {
                    ContentUnavailableView(
                        "No people on the company record",
                        systemImage: "person.3",
                        description: Text("Founders, board members and headcount appear here once they are recorded on the company.")
                    )
                }

                // Founders & Executive Leadership Dossier Cards
                if !dossier.founders.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label("Leadership", systemImage: "person.2")
                            .font(.dsLabel)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(dossier.founders.count) key executives")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.tertiary)
                    }

                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
                        ForEach(dossier.founders) { founder in
                            FounderCardView(founder: founder)
                        }
                    }
                }
                }

                // Board of Directors & Strategic Advisors
                if let board = dossier.advisorsAndBoard, !board.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Board & advisors", systemImage: "briefcase")
                                .font(.dsLabel)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("\(board.count) board & advisors")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.tertiary)
                        }

                        LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
                            ForEach(board) { advisor in
                                FounderCardView(founder: advisor)
                            }
                        }
                    }
                    .padding(.top, 4)
                }

                // Company Headcount & Organization Breakdown
                if let team = dossier.teamHeadcount {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Headcount", systemImage: "chart.bar.doc.horizontal")
                                .font(.dsLabel)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(team.hiringVelocity ?? "")
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(Color.green)
                        }

                        HStack(spacing: 12) {
                            DevMetricPill(
                                icon: "person.3.fill",
                                color: .blue,
                                title: "Total headcount",
                                value: team.employeeCountEstimate ?? "—",
                                delta: team.openRolesCount.map { "\($0) open roles" } ?? "Open roles unknown"
                            )
                            DevMetricPill(
                                icon: "chevron.left.forwardslash.chevron.right",
                                color: .indigo,
                                title: "Engineering & R&D",
                                value: team.engineeringPct.map { "\($0)%" } ?? "—",
                                delta: "of headcount"
                            )
                            DevMetricPill(
                                icon: "megaphone.fill",
                                color: .green,
                                title: "Go-to-market",
                                value: team.gtmSalesPct.map { "\($0)%" } ?? "—",
                                delta: "of headcount"
                            )
                            DevMetricPill(
                                icon: "gearshape.fill",
                                color: .orange,
                                title: "Operations & G&A",
                                value: team.operationsPct.map { "\($0)%" } ?? "—",
                                delta: "of headcount"
                            )
                        }

                        // Departmental Split Ratio Bar
                        GeometryReader { geo in
                            let eng = team.engineeringPct ?? 0
                            let gtm = team.gtmSalesPct ?? 0
                            let ops = team.operationsPct ?? 0
                            let total = max(1, CGFloat(eng + gtm + ops))
                            let engW = geo.size.width * CGFloat(eng) / total
                            let gtmW = geo.size.width * CGFloat(gtm) / total
                            let opsW = geo.size.width * CGFloat(ops) / total

                            HStack(spacing: 2) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.indigo.opacity(0.85))
                                    .frame(width: max(4, engW))
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.green.opacity(0.85))
                                    .frame(width: max(4, gtmW))
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.orange.opacity(0.85))
                                    .frame(width: max(4, opsW))
                            }
                        }
                        .frame(height: 7)
                    }
                    .padding(12)
                    .appleGlassTile(cornerRadius: 10)
                    .padding(.top, 4)
                }

                // Developer & Open Source Traction Radar
                if let dev = dossier.developerTraction {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Open source velocity", systemImage: "chevron.left.forwardslash.chevron.right")
                                .font(.dsLabel)
                                .foregroundStyle(.secondary)
                            Spacer()
                            if let repo = dev.repoUrl, let url = URL(string: repo) {
                                Link(destination: url) {
                                    HStack(spacing: 4) {
                                        Text(repo.replacingOccurrences(of: "https://github.com/", with: ""))
                                            .font(.caption2.monospacedDigit())
                                        Image(systemName: "arrow.up.right")
                                            .font(.system(size: 10))
                                    }
                                }
                            }
                        }

                        // Metrics Ribbon
                        HStack(spacing: 12) {
                            DevMetricPill(
                                icon: "star.fill",
                                color: .yellow,
                                title: "GitHub stars",
                                value: dev.stars.map { $0.formatted() } ?? "—",
                                delta: dev.starsGrowthWeekly ?? "Not tracked yet"
                            )
                            DevMetricPill(
                                icon: "tuningfork",
                                color: .blue,
                                title: "Forks",
                                value: dev.forks.map { $0.formatted() } ?? "—",
                                delta: "Forks"
                            )
                            if let downloads = dev.weeklyDownloads {
                                DevMetricPill(
                                    icon: "arrow.down.circle.fill",
                                    color: .green,
                                    title: "Weekly downloads",
                                    value: downloads,
                                    delta: "Weekly"
                                )
                            }
                            DevMetricPill(
                                icon: "clock.arrow.circlepath",
                                color: .purple,
                                title: "Commit cadence",
                                value: dev.commitCadence ?? "—",
                                delta: "Commit cadence"
                            )
                        }

                        // Inflection Signal Callout
                        HStack(spacing: 8) {
                            Image(systemName: "flame.fill")
                                .foregroundStyle(.orange)
                            Text("Traction signal")
                                .font(.dsLabel)
                                .foregroundStyle(.orange)
                            Text(dev.inflectionSignal ?? "—")
                                .font(.caption.weight(.semibold))
                            Spacer()
                        }
                        .padding(10)
                        .appleGlassTile(cornerRadius: 8, tint: .orange)
                    }
                    .padding(.top, 6)
                }

                if let refreshError = store.founderDossierErrors[company.id] {
                    Label("Refresh failed: \(refreshError)", systemImage: "exclamationmark.triangle")
                        .font(.dsCaption)
                        .foregroundStyle(Color.dsNegative)
                        .lineLimit(2)
                }

                Text("Built from the company record")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            } else if loadFailed && !loading {
                ContentUnavailableView {
                    Label("Couldn't load people", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(store.founderDossierErrors[company.id] ?? "The company record could not be read from the server.")
                } actions: {
                    Button("Retry") { Task { await load() } }
                        .controlSize(.small)
                }
            } else {
                HStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Loading people from the company record…")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 20)
                .frame(maxWidth: .infinity, alignment: .center)
            }
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
        .task(id: company.id) {
            loadFailed = false
            await load()
        }
    }

    private func load() async {
        loading = true
        await store.fetchFounderDossier(for: company.id)
        guard !Task.isCancelled else { return }
        loading = false
        loadFailed = store.founderDossiers[company.id] == nil
    }
}

// MARK: - Founder Card View
private struct FounderCardView: View {
    let founder: MacFounderProfile

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header: Name & Role
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 36, height: 36)
                    Text(initials(founder.name))
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(Color.accentColor)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(founder.name)
                        .font(.subheadline.weight(.bold))
                    Text(founder.role)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(.secondary)
                }

                Spacer()

                if let url = founder.linkedinUrl, let dest = URL(string: url) {
                    Link(destination: dest) {
                        Image(systemName: "link.circle.fill")
                            .font(.system(size: 16))
                            .foregroundStyle(.secondary)
                    }
                    .help("Open LinkedIn Profile")
                }
            }

            // Pedigree Badges Flow
            FlowLayout(spacing: 6) {
                ForEach(founder.pedigreeTags, id: \.self) { tag in
                    PedigreeBadgeView(tag: tag)
                }
            }

            // Bio
            if let bio = founder.bio, !bio.isEmpty {
                Text(bio)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Divider()

            // Details Stack
            VStack(alignment: .leading, spacing: 5) {
                if let edu = founder.education {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "graduationcap.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .frame(width: 14)
                        Text(edu)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                if !founder.pastCompanies.isEmpty {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "building.2.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .frame(width: 14)
                        Text(founder.pastCompanies.joined(separator: ", "))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                if let exit = founder.priorExits {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "dollarsign.circle.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(.green)
                            .frame(width: 14)
                        Text("Prior Exit: \(exit)")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.green)
                            .lineLimit(1)
                    }
                }
            }
        }
        .padding(12)
        .appleGlassTile(cornerRadius: 10)
    }

    private func initials(_ name: String) -> String {
        let parts = name.split(separator: " ")
        if parts.count >= 2 {
            return String(parts[0].prefix(1) + parts[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }
}

// MARK: - Pedigree Badge View
private struct PedigreeBadgeView: View {
    let tag: String

    var color: Color {
        let lower = tag.lowercased()
        if lower.contains("openai") || lower.contains("deepmind") || lower.contains("fair") {
            return .purple
        } else if lower.contains("stanford") || lower.contains("mit") || lower.contains("berkeley") {
            return .red
        } else if lower.contains("founder") || lower.contains("exit") {
            return .green
        } else if lower.contains("yc") || lower.contains("stripe") {
            return .orange
        }
        return .blue
    }

    var body: some View {
        MacStatusPill(text: tag, color: color)
    }
}

// MARK: - Developer Metric Pill
private struct DevMetricPill: View {
    let icon: String
    let color: Color
    let title: String
    let value: String
    let delta: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 10))
                    .foregroundStyle(color)
                Text(title)
                    .font(.dsLabel)
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.dsMetricSmall)
            Text(delta)
                .font(.system(size: 10))
                .foregroundStyle(color)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .appleGlassTile(cornerRadius: 8)
    }
}

// MARK: - Flow Layout for Badges
private struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 300
        var height: CGFloat = 0
        var currentX: CGFloat = 0
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if currentX + size.width > width && currentX > 0 {
                height += rowHeight + spacing
                currentX = 0
                rowHeight = 0
            }
            currentX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        height += rowHeight
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var currentX = bounds.minX
        var currentY = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if currentX + size.width > bounds.maxX && currentX > bounds.minX {
                currentY += rowHeight + spacing
                currentX = bounds.minX
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: currentX, y: currentY), proposal: .unspecified)
            currentX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
