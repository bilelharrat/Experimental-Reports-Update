//
//  MacFounderRadarView.swift
//  BSHResearchMac
//
//  Sequoia Ampersand & Harmonic-grade Founder Pedigree & Developer Traction Radar.
//  Displays verified leadership pedigree, academic affiliations, previous exits,
//  and real-time open-source developer velocity with live deep-search trigger.
//

import SwiftUI
import AppKit

struct MacFounderRadarView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    private var dossier: MacFounderDossier? {
        store.founderDossiers[company.id]
    }

    private var isSearching: Bool {
        store.deepSearchingFounders.contains(company.id)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Header Bar
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Image(systemName: "person.3.sequence.fill")
                            .foregroundStyle(Color.accentColor)
                        Text("Founder Pedigree & Developer Traction Radar")
                            .font(.headline)

                        Text("HARMONIC / AMPERSAND")
                            .font(.system(size: 8, weight: .black))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            .foregroundStyle(Color.accentColor)

                        if dossier?.isDeepAudited == true {
                            HStack(spacing: 3) {
                                Image(systemName: "checkmark.seal.fill")
                                    .font(.system(size: 9))
                                Text("DEEP INVESTIGATED")
                                    .font(.system(size: 8, weight: .black))
                            }
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.green.opacity(0.15), in: RoundedRectangle(cornerRadius: 3))
                            .foregroundStyle(Color.green)
                        }
                    }

                    Text("Verified executive pedigree, former BigTech/lab footprints, prior startup exits, and GitHub velocity.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Live Deep-Search Button
                Button {
                    Task {
                        await store.deepSearchFounder(for: company.id)
                    }
                } label: {
                    HStack(spacing: 6) {
                        if isSearching {
                            ProgressView()
                                .controlSize(.small)
                            Text("Deep Searching…")
                        } else {
                            Image(systemName: "sparkle.magnifyingglass")
                            Text("Deep Search Founders")
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isSearching)
            }

            Divider()

            // Founders & Executive Leadership Dossier Cards
            if let dossier = dossier, !dossier.founders.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label("Founding & Executive Leadership Team", systemImage: "person.2.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(dossier.founders.count) key executives")
                            .font(.caption2.monospaced())
                            .foregroundStyle(.tertiary)
                    }

                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
                        ForEach(dossier.founders) { founder in
                            FounderCardView(founder: founder)
                        }
                    }
                }

                // Board of Directors & Strategic Advisors
                if let board = dossier.advisorsAndBoard, !board.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Board of Directors & Strategic Advisors", systemImage: "briefcase.fill")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("\(board.count) board & advisors")
                                .font(.caption2.monospaced())
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
                            Label("Company Headcount & Organization Breakdown", systemImage: "chart.bar.doc.horizontal.fill")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(team.hiringVelocity)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(Color.green)
                        }

                        HStack(spacing: 12) {
                            DevMetricPill(
                                icon: "person.3.fill",
                                color: .blue,
                                title: "TOTAL HEADCOUNT",
                                value: team.employeeCountEstimate,
                                delta: "\(team.openRolesCount) Open Roles"
                            )
                            DevMetricPill(
                                icon: "chevron.left.forwardslash.chevron.right",
                                color: .indigo,
                                title: "ENGINEERING & R&D",
                                value: "\(team.engineeringPct)%",
                                delta: "Technical Depth"
                            )
                            DevMetricPill(
                                icon: "megaphone.fill",
                                color: .green,
                                title: "GO-TO-MARKET / SALES",
                                value: "\(team.gtmSalesPct)%",
                                delta: "Distribution Core"
                            )
                            DevMetricPill(
                                icon: "gearshape.fill",
                                color: .orange,
                                title: "OPERATIONS & G&A",
                                value: "\(team.operationsPct)%",
                                delta: "Corporate Ops"
                            )
                        }

                        // Departmental Split Ratio Bar
                        GeometryReader { geo in
                            let total = max(1, CGFloat(team.engineeringPct + team.gtmSalesPct + team.operationsPct))
                            let engW = geo.size.width * CGFloat(team.engineeringPct) / total
                            let gtmW = geo.size.width * CGFloat(team.gtmSalesPct) / total
                            let opsW = geo.size.width * CGFloat(team.operationsPct) / total

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
                            Label("Open Source & Developer Velocity Radar", systemImage: "chevron.left.forwardslash.chevron.right")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                            Spacer()
                            if let repo = dev.repoUrl, let url = URL(string: repo) {
                                Link(destination: url) {
                                    HStack(spacing: 4) {
                                        Text(repo.replacingOccurrences(of: "https://github.com/", with: ""))
                                            .font(.caption2.monospaced())
                                        Image(systemName: "arrow.up.right")
                                            .font(.system(size: 9))
                                    }
                                }
                            }
                        }

                        // Metrics Ribbon
                        HStack(spacing: 12) {
                            DevMetricPill(
                                icon: "star.fill",
                                color: .yellow,
                                title: "GITHUB STARS",
                                value: "\(dev.stars.formatted())",
                                delta: dev.starsGrowthWeekly
                            )
                            DevMetricPill(
                                icon: "tuningfork",
                                color: .blue,
                                title: "FORKS",
                                value: "\(dev.forks.formatted())",
                                delta: "High Fork Ratio"
                            )
                            if let downloads = dev.weeklyDownloads {
                                DevMetricPill(
                                    icon: "arrow.down.circle.fill",
                                    color: .green,
                                    title: "WEEKLY DOWNLOADS",
                                    value: downloads,
                                    delta: "+24% MoM"
                                )
                            }
                            DevMetricPill(
                                icon: "clock.arrow.circlepath",
                                color: .purple,
                                title: "COMMIT CADENCE",
                                value: dev.commitCadence,
                                delta: "Active Maintainers"
                            )
                        }

                        // Inflection Signal Callout
                        HStack(spacing: 8) {
                            Image(systemName: "flame.fill")
                                .foregroundStyle(.orange)
                            Text("TRACTION SIGNAL:")
                                .font(.system(size: 10, weight: .black))
                                .foregroundStyle(.orange)
                            Text(dev.inflectionSignal)
                                .font(.caption.weight(.semibold))
                            Spacer()
                        }
                        .padding(10)
                        .appleGlassTile(cornerRadius: 8, tint: .orange)
                    }
                    .padding(.top, 6)
                }

                if let searchedAt = dossier.searchedAt {
                    Text("Investigated: \(searchedAt)")
                        .font(.system(size: 9).monospaced())
                        .foregroundStyle(.tertiary)
                }
            } else {
                // Loading or Placeholder
                HStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Synthesizing executive background and founder pedigree…")
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
            await store.fetchFounderDossier(for: company.id)
        }
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
        Text(tag)
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 2.5)
            .appleGlassPill(color: color)
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
                    .font(.system(size: 9))
                    .foregroundStyle(color)
                Text(title)
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .monospacedDigit()
            Text(delta)
                .font(.system(size: 9))
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
