import SwiftUI

public struct MacFounderRadarView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore

    @State private var loading = false
    @State private var loadFailed = false

    private var radar: MacFounderRadar? {
        store.founderRadarByCompany[company.id]
    }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            MacCardHeader("Founders & team", subtitle: "Leadership, prior exits, and engineering velocity.", systemImage: "person.3") {
                Button {
                    Task { await reload() }
                } label: {
                    if loading {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "arrow.clockwise")
                    }
                }
                .font(.caption)
                .buttonStyle(.plain)
            }

            if let dossier = radar {
                if dossier.founders.isEmpty && (dossier.advisorsAndBoard ?? []).isEmpty && dossier.teamHeadcount == nil {
                    Text("No people recorded on company profile.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Leadership
                if !dossier.founders.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        MacSectionLabel("Leadership", trailing: "\(dossier.founders.count) key people")
                        VStack(spacing: 10) {
                            ForEach(dossier.founders) { founder in
                                founderCard(founder)
                            }
                        }
                    }
                }

                // Board & Advisors
                if let board = dossier.advisorsAndBoard, !board.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        MacSectionLabel("Board & advisors", trailing: "\(board.count) members")
                        VStack(spacing: 10) {
                            ForEach(board) { advisor in
                                founderCard(advisor)
                            }
                        }
                    }
                }

                // Headcount
                if let team = dossier.teamHeadcount {
                    VStack(alignment: .leading, spacing: 10) {
                        MacSectionLabel("Headcount", trailing: team.hiringVelocity)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                devMetricPill(icon: "person.3.fill", color: .blue, title: "Total team", value: team.employeeCountEstimate ?? "—", delta: team.openRolesCount.map { "\($0) open roles" } ?? "—")
                                devMetricPill(icon: "chevron.left.forwardslash.chevron.right", color: .indigo, title: "Engineering", value: team.engineeringPct.map { "\($0)%" } ?? "—", delta: "of headcount")
                                devMetricPill(icon: "megaphone.fill", color: .green, title: "GTM / Sales", value: team.gtmSalesPct.map { "\($0)%" } ?? "—", delta: "of headcount")
                                devMetricPill(icon: "gearshape.fill", color: .orange, title: "Operations", value: team.operationsPct.map { "\($0)%" } ?? "—", delta: "of headcount")
                            }
                        }
                    }
                }

                // Developer & Open Source Traction
                if let dev = dossier.developerTraction {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            MacSectionLabel("Open source velocity")
                            Spacer()
                            if let repo = dev.repoUrl, let url = URL(string: repo) {
                                Link(destination: url) {
                                    HStack(spacing: 4) {
                                        Text(repo.replacingOccurrences(of: "https://github.com/", with: ""))
                                            .font(.caption2.monospacedDigit())
                                        Image(systemName: "arrow.up.right")
                                            .font(.system(size: 9))
                                    }
                                }
                            }
                        }

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                devMetricPill(icon: "star.fill", color: .yellow, title: "GitHub stars", value: dev.stars.map { "\($0)" } ?? "—", delta: dev.starsGrowthWeekly ?? "—")
                                devMetricPill(icon: "tuningfork", color: .blue, title: "Forks", value: dev.forks.map { "\($0)" } ?? "—", delta: "Forks")
                                if let d = dev.weeklyDownloads {
                                    devMetricPill(icon: "arrow.down.circle.fill", color: .green, title: "Downloads", value: d, delta: "Weekly")
                                }
                                devMetricPill(icon: "clock.arrow.circlepath", color: .purple, title: "Cadence", value: dev.commitCadence ?? "—", delta: "Commits")
                            }
                        }
                    }
                }
            } else if loadFailed {
                Text("Founder data unavailable.").font(.caption).foregroundStyle(.secondary)
            } else {
                Text(loading ? "Loading team…" : "No founder records on file.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            if radar == nil { await reload() }
        }
    }

    private func reload() async {
        loading = true
        await store.fetchFounderRadar(for: company.id)
        loading = false
        loadFailed = radar == nil
    }

    private func founderCard(_ founder: MacFounderProfile) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.accentColor.opacity(0.15)).frame(width: 32, height: 32)
                    Text(initials(founder.name))
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(Color.accentColor)
                }

                VStack(alignment: .leading, spacing: 1) {
                    Text(founder.name).font(.subheadline.weight(.semibold))
                    Text(founder.role).font(.caption2).foregroundStyle(.secondary)
                }

                Spacer()

                if let url = founder.linkedinUrl, let dest = URL(string: url) {
                    Link(destination: dest) {
                        Image(systemName: "link.circle.fill")
                            .font(.system(size: 16))
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if !founder.pedigreeTags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(founder.pedigreeTags, id: \.self) { tag in
                            MacStatusPill(text: tag, color: .blue)
                        }
                    }
                }
            }

            if let bio = founder.bio, !bio.isEmpty {
                Text(bio).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }

            if let exit = founder.priorExits {
                Label("Prior exit: \(exit)", systemImage: "dollarsign.circle.fill")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.green)
            }
        }
        .padding(10)
        .appleGlassTile(cornerRadius: 10)
    }

    private func devMetricPill(icon: String, color: Color, title: String, value: String, delta: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 10)).foregroundStyle(color)
                Text(title).font(.dsLabel).foregroundStyle(.secondary)
            }
            Text(value).font(.dsMetricSmall)
            Text(delta).font(.system(size: 10)).foregroundStyle(color).lineLimit(1)
        }
        .frame(width: 110, alignment: .leading)
        .padding(8)
        .appleGlassTile(cornerRadius: 8)
    }

    private func initials(_ name: String) -> String {
        let parts = name.split(separator: " ")
        if parts.count >= 2 {
            return String(parts[0].prefix(1) + parts[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }
}
