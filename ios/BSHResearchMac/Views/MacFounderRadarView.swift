//
//  MacFounderRadarView.swift
//  BSHResearchMac
//
//  Founder pedigree and developer traction: the company record, plus Gemini
//  web research when someone presses Research team (server/founder_dossier.py).
//  Displays leadership, board, headcount and open-source velocity.
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

    @Environment(\.bureauResearchDesk) private var bureauDesk
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if BSHDesign.active == .bureau && bureauDesk {
            bureauBody
        } else {
            glassBody
        }
    }

    private var glassBody: some View {
        VStack(alignment: .leading, spacing: 18) {
            MacCardHeader("Founders & team", subtitle: "People from the company record and Gemini web research: prior companies and exits, board seats, headcount, and open-source velocity when a repo is known.", systemImage: "person.3") {
                Button {
                    // A Gemini web-research call, so it asks first like
                    // every paid button.
                    guard MacTokenConfirm.ask(detail: "Researches this team on the web with Gemini 3.8 Flash (about a minute).") else { return }
                    Task {
                        await store.deepSearchFounder(for: company.id)
                    }
                } label: {
                    HStack(spacing: 6) {
                        if isSearching {
                            ProgressView()
                                .controlSize(.small)
                            Text("Researching… about a minute")
                        } else {
                            Image(systemName: "sparkle.magnifyingglass")
                            Text("Research team")
                        }
                    }
                }
                .buttonStyle(.dsBordered)
                .controlSize(.small)
                .disabled(isSearching)
                .help("Search the web with Gemini for founders, board, headcount and hiring, and add what it finds to the record")
            }

            if let dossier = dossier {
                if !hasPeople(dossier) {
                    ContentUnavailableView(
                        "No people on the company record",
                        systemImage: "person.3",
                        description: Text("Nothing on the company record yet. Research team finds the founders, board and headcount on the web.")
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
                            .font(.ui(.caption2).monospacedDigit())
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
                                .font(.ui(.caption2).monospacedDigit())
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
                                .font(.ui(.caption2).weight(.semibold))
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
                                            .font(.ui(.caption2).monospacedDigit())
                                        Image(systemName: "arrow.up.right")
                                            .font(.ui(size: 10))
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
                                .font(.ui(.caption).weight(.semibold))
                            Spacer()
                        }
                        .padding(10)
                        .appleGlassTile(cornerRadius: 8, tint: .orange)
                    }
                    .padding(.top, 6)
                }

                if let refreshError = store.founderDossierErrors[company.id] {
                    Label("Research failed: \(refreshError)", systemImage: "exclamationmark.triangle")
                        .font(.dsCaption)
                        .foregroundStyle(Color.dsNegative)
                        .lineLimit(2)
                }

                if let researchError = dossier.researchError, !researchError.isEmpty {
                    // The server degrades instead of erroring: the people
                    // above are what it had, and this is why nothing changed.
                    Label("The research pass could not run — \(researchError)", systemImage: "exclamationmark.triangle")
                        .font(.dsCaption)
                        .foregroundStyle(.orange)
                        .lineLimit(2)
                } else if let engine = dossier.engine {
                    let sourceCount = dossier.sources?.count ?? 0
                    Text("Researched by \(engine)\(dossier.model.map { " (\($0))" } ?? "") · \(sourceCount > 0 ? "read \(sourceCount) sources" : "no sources reported")")
                        .font(.ui(size: 10))
                        .foregroundStyle(.tertiary)
                } else {
                    Text("Built from the company record")
                        .font(.ui(size: 10))
                        .foregroundStyle(.tertiary)
                }
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
                        .font(.ui(.subheadline))
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

// MARK: - Bureau

/// FounderRadarCard.vue on the Research Desk: leadership and board on tiles two to a row,
/// headcount and open-source velocity on stat tiles, and where the people came from.
extension MacFounderRadarView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 18) {
            MacBureauDeskCardHeader(
                icon: "users",
                title: "Founders & team",
                subtitle: "People from the company record and Gemini web research: prior companies and exits, board seats, headcount, and open-source velocity when a repo is known."
            ) {
                Button {
                    // A Gemini web-research call, so it asks first like every paid button.
                    guard MacTokenConfirm.ask(detail: "Researches this team on the web with Gemini 3.8 Flash (about a minute).") else { return }
                    Task { await store.deepSearchFounder(for: company.id) }
                } label: {
                    HStack(spacing: 4) {
                        if isSearching {
                            MacBureauDeskSpinner(size: 12)
                        } else {
                            MacBureauDeskIcon("rotate-cw", size: 12)
                        }
                        MacBureauDeskButtonLabel(title: isSearching ? "Researching… about a minute" : "Research team", size: .small)
                    }
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(isSearching)
                .help("Search the web with Gemini for founders, board, headcount and hiring, and add what it finds to the record")
                .fixedSize()
            }

            if let dossier {
                if !hasPeople(dossier) {
                    bureauUnavailable(
                        icon: "users",
                        title: "No people on the company record",
                        detail: "Nothing on the company record yet. Research team finds the founders, board and headcount on the web.",
                        ink: ink
                    )
                }
                if !dossier.founders.isEmpty {
                    bureauSection("Leadership", icon: "users", count: "\(dossier.founders.count) key executives", ink: ink) {
                        MacBureauDeskGrid(columns: 2, spacing: 14) {
                            ForEach(dossier.founders) { founder in
                                bureauPerson(founder, details: true, ink: ink)
                            }
                        }
                    }
                }
                if let board = dossier.advisorsAndBoard, !board.isEmpty {
                    bureauSection("Board & advisors", icon: "briefcase", count: "\(board.count) board & advisors", ink: ink) {
                        MacBureauDeskGrid(columns: 2, spacing: 14) {
                            ForEach(board) { advisor in
                                bureauPerson(advisor, details: false, ink: ink)
                            }
                        }
                    }
                }
                if let team = dossier.teamHeadcount {
                    bureauHeadcount(team, ink: ink)
                }
                if let dev = dossier.developerTraction {
                    bureauTraction(dev, ink: ink)
                }
                if let refreshError = store.founderDossierErrors[company.id] {
                    bureauWarning("Research failed: \(refreshError)", tint: ink.red)
                }
                if let researchError = dossier.researchError, !researchError.isEmpty {
                    bureauWarning("The research pass could not run — \(researchError)", tint: ink.orange)
                } else if let engine = dossier.engine {
                    let sourceCount = dossier.sources?.count ?? 0
                    MacBureauWebParagraph(
                        text: "Researched by \(engine)\(dossier.model.map { " (\($0))" } ?? "") · \(sourceCount > 0 ? "read \(sourceCount) sources" : "no sources reported")",
                        size: 10,
                        lineHeight: 12.5
                    )
                    .foregroundStyle(ink.tertiary)
                } else {
                    MacBureauDeskCaption(text: "Built from the company record", color: ink.tertiary)
                }
            } else if loadFailed && !loading {
                VStack(spacing: 8) {
                    bureauUnavailable(
                        icon: "triangle-alert",
                        title: "Couldn't load people",
                        detail: store.founderDossierErrors[company.id] ?? "The company record could not be read from the server.",
                        ink: ink
                    )
                    Button {
                        Task { await load() }
                    } label: {
                        MacBureauDeskButtonLabel(title: "Retry", size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                }
                .frame(maxWidth: .infinity)
            } else {
                HStack(spacing: 12) {
                    MacBureauDeskSpinner()
                    Text("Loading people from the company record…")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(14.3, 11)
                }
                .padding(.vertical, 20)
                .frame(maxWidth: .infinity)
            }
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            loadFailed = false
            await load()
        }
    }

    private func bureauSection<Content: View>(_ title: String, icon: String, count: String, ink: MacBureauDeskInk, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                MacBureauDeskIcon(icon, size: 12)
                MacBureauDeskCaption(text: title, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                Spacer(minLength: 0)
                MacBureauDeskCaption(text: count, mono: true, color: ink.tertiary)
            }
            .foregroundStyle(ink.secondary)
            content()
        }
    }

    private func bureauPerson(_ person: MacFounderProfile, details: Bool, ink: MacBureauDeskInk) -> some View {
        let link = [person.linkedinUrl, person.profileUrl].compactMap { $0 }.first { !$0.isEmpty }.flatMap(URL.init(string:))
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Text(Self.initials(person.name))
                    .font(BSHType.bureauSans(13, weight: .bold))
                    .foregroundStyle(ink.accent)
                    .bureauDeskLine(19.5, 13)
                    .frame(width: 36, height: 36)
                    .bureauBox(Circle(), fill: ink.accent.opacity(0.15))
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.name)
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauDeskLine(14.3, 11)
                    Text(person.role.isEmpty ? (details ? "Founder" : "Advisor") : person.role)
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauDeskLine(12.5, 10)
                }
                Spacer(minLength: 0)
                if let link {
                    Link(destination: link) {
                        MacBureauDeskIcon("link", size: 16)
                            .foregroundStyle(ink.secondary)
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    .help("Open LinkedIn Profile")
                }
            }
            if !person.pedigreeTags.isEmpty {
                MacBureauDeskFlow(spacing: 6) {
                    ForEach(person.pedigreeTags, id: \.self) { tag in
                        MacBureauDeskPill(text: tag, tint: Self.pedigreeTint(tag, ink: ink))
                    }
                }
            }
            if let bio = person.bio, !bio.isEmpty {
                MacBureauWebParagraph(text: bio, size: 10, lineHeight: 12.5, maxLines: 2)
                    .foregroundStyle(ink.secondary)
            }
            if details {
                MacBureauGridRule(color: ink.hairline)
                VStack(alignment: .leading, spacing: 5) {
                    if let edu = person.education, !edu.isEmpty {
                        bureauDetail("graduation-cap", edu, tint: ink.secondary, ink: ink)
                    }
                    if !person.pastCompanies.isEmpty {
                        bureauDetail("building-2", person.pastCompanies.joined(separator: ", "), tint: ink.secondary, ink: ink)
                    }
                    if let exit = person.priorExits, !exit.isEmpty {
                        bureauDetail("circle-dollar-sign", "Prior Exit: \(exit)", tint: ink.green, ink: ink)
                    }
                }
                .frame(minHeight: 0)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private func bureauDetail(_ icon: String, _ text: String, tint: Color, ink: MacBureauDeskInk) -> some View {
        HStack(alignment: .top, spacing: 6) {
            MacBureauDeskIcon(icon, size: 12)
                .frame(width: 14)
                .padding(.top, 1)
            Text(text)
                .font(BSHType.bureauSans(10))
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(12.5, 10)
        }
        .foregroundStyle(tint)
    }

    private func bureauStat(_ icon: String, _ title: String, value: String, caption: String, tint: Color, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                MacBureauDeskIcon(icon, size: 10)
                    .foregroundStyle(tint)
                MacBureauDeskCaption(text: title, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
            }
            Text(value)
                .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                .foregroundStyle(ink.label)
                .lineLimit(1)
                .bureauDeskLine(18, 15)
            Text(caption)
                .font(BSHType.bureauSans(10))
                .foregroundStyle(tint)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(12.5, 10)
        }
        .padding(8)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
    }

    private func bureauHeadcount(_ team: MacTeamHeadcount, ink: MacBureauDeskInk) -> some View {
        let eng = CGFloat(team.engineeringPct ?? 0), gtm = CGFloat(team.gtmSalesPct ?? 0), ops = CGFloat(team.operationsPct ?? 0)
        let total = max(1, eng + gtm + ops)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                MacBureauDeskIcon("chart-bar", size: 12)
                    .foregroundStyle(ink.secondary)
                MacBureauDeskCaption(text: "Headcount", size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                Spacer(minLength: 0)
                if let velocity = team.hiringVelocity, !velocity.isEmpty {
                    MacBureauDeskCaption(text: velocity, color: ink.green)
                }
            }
            .frame(height: 13.75)
            MacBureauDeskGrid(columns: 4, spacing: 12) {
                bureauStat("users", "Total headcount", value: team.employeeCountEstimate ?? "—",
                           caption: team.openRolesCount.map { "\($0) open roles" } ?? "Open roles unknown", tint: ink.blue, ink: ink)
                bureauStat("code", "Engineering & R&D", value: team.engineeringPct.map { "\($0)%" } ?? "—",
                           caption: "of headcount", tint: ink.indigo, ink: ink)
                bureauStat("megaphone", "Go-to-market", value: team.gtmSalesPct.map { "\($0)%" } ?? "—",
                           caption: "of headcount", tint: ink.green, ink: ink)
                bureauStat("settings", "Operations & G&A", value: team.operationsPct.map { "\($0)%" } ?? "—",
                           caption: "of headcount", tint: ink.orange, ink: ink)
            }
            // The department split: each share of the width, a sliver at least.
            GeometryReader { proxy in
                let width = proxy.size.width
                HStack(spacing: 2) {
                    RoundedRectangle(cornerRadius: 3, style: .circular)
                        .fill(ink.indigo.opacity(0.85))
                        .frame(width: width * max(0.01, eng / total))
                    RoundedRectangle(cornerRadius: 3, style: .circular)
                        .fill(ink.green.opacity(0.85))
                        .frame(width: width * max(0.01, gtm / total))
                    RoundedRectangle(cornerRadius: 3, style: .circular)
                        .fill(ink.orange.opacity(0.85))
                        .frame(width: width * max(0.01, ops / total))
                }
                .bureauSnap(x: .whole)
            }
            .frame(height: 7)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private func bureauTraction(_ dev: MacDeveloperTraction, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                MacBureauDeskIcon("code", size: 12)
                    .foregroundStyle(ink.secondary)
                MacBureauDeskCaption(text: "Open source velocity", size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                Spacer(minLength: 0)
                if let repo = dev.repoUrl, let url = URL(string: repo) {
                    Link(destination: url) {
                        HStack(spacing: 4) {
                            MacBureauDeskCaption(text: repo.replacingOccurrences(of: "https://github.com/", with: ""), mono: true, color: ink.accent)
                            MacBureauDeskIcon("arrow-up-right", size: 10)
                                .foregroundStyle(ink.accent)
                        }
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                }
            }
            MacBureauDeskGrid(columns: 4, spacing: 12) {
                bureauStat("star", "GitHub stars", value: dev.stars.map { $0.formatted() } ?? "—",
                           caption: dev.starsGrowthWeekly ?? "Not tracked yet", tint: ink.yellow, ink: ink)
                bureauStat("git-fork", "Forks", value: dev.forks.map { $0.formatted() } ?? "—",
                           caption: "Forks", tint: ink.blue, ink: ink)
                if let downloads = dev.weeklyDownloads {
                    bureauStat("circle-arrow-down", "Weekly downloads", value: downloads, caption: "Weekly", tint: ink.green, ink: ink)
                }
                bureauStat("history", "Commit cadence", value: dev.commitCadence ?? "—",
                           caption: "Commit cadence", tint: ink.purple, ink: ink)
            }
            HStack(spacing: 8) {
                MacBureauDeskIcon("flame", size: 14)
                    .foregroundStyle(ink.orange)
                MacBureauDeskCaption(text: "Traction signal", size: 11, weight: .medium, lineHeight: 13.75, color: ink.orange)
                Text(dev.inflectionSignal ?? "—")
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(12.5, 10)
                Spacer(minLength: 0)
            }
            .padding(10)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.orange.opacity(0.10))
        }
    }

    private func bureauUnavailable(icon: String, title: String, detail: String, ink: MacBureauDeskInk) -> some View {
        VStack(spacing: 8) {
            MacBureauDeskIcon(icon, size: 36)
                .foregroundStyle(ink.secondary)
            Text(title)
                .font(BSHType.bureauSans(15, weight: .semibold))
                .foregroundStyle(ink.label)
                .bureauDeskLine(18.75, 15)
            MacBureauWebParagraph(text: detail, size: 13, lineHeight: 17.55, alignment: .center)
                .foregroundStyle(ink.secondary)
                .frame(maxWidth: 384)
        }
        .padding(.vertical, 32)
        .frame(maxWidth: .infinity)
    }

    private func bureauWarning(_ text: String, tint: Color) -> some View {
        HStack(spacing: 6) {
            MacBureauDeskIcon("triangle-alert", size: 12)
            Text(text)
                .font(BSHType.bureauSans(11))
                .lineLimit(2)
        }
        .foregroundStyle(tint)
    }

    private static func initials(_ name: String) -> String {
        let parts = name.split(whereSeparator: \.isWhitespace)
        if parts.count >= 2 { return (String(parts[0].prefix(1)) + String(parts[1].prefix(1))).uppercased() }
        return String(name.isEmpty ? "?" : String(name.prefix(2))).uppercased()
    }

    private static func pedigreeTint(_ tag: String, ink: MacBureauDeskInk) -> Color {
        let lower = tag.lowercased()
        if lower.contains("openai") || lower.contains("deepmind") || lower.contains("fair") { return ink.purple }
        if lower.contains("stanford") || lower.contains("mit") || lower.contains("berkeley") { return ink.red }
        if lower.contains("founder") || lower.contains("exit") { return ink.green }
        if lower.contains("yc") || lower.contains("stripe") { return ink.orange }
        return ink.blue
    }
}

/// Pills that wrap onto as many rows as they need (`flex flex-wrap`).
struct MacBureauDeskFlow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 300
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width && x > 0 {
                y += row + spacing
                x = 0
                row = 0
            }
            x += size.width + spacing
            row = max(row, size.height)
        }
        return CGSize(width: width, height: y + row)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, row: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX && x > bounds.minX {
                y += row + spacing
                x = bounds.minX
                row = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: .unspecified)
            x += size.width + spacing
            row = max(row, size.height)
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
                        .fill(Color.dsAccent.opacity(0.15))
                        .frame(width: 36, height: 36)
                    Text(initials(founder.name))
                        .font(.ui(size: 13, weight: .bold))
                        .foregroundStyle(Color.dsAccent)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(founder.name)
                        .font(.ui(.subheadline).weight(.bold))
                    Text(founder.role)
                        .font(.ui(.caption2).weight(.medium))
                        .foregroundStyle(.secondary)
                }

                Spacer()

                if let url = founder.linkedinUrl, let dest = URL(string: url) {
                    Link(destination: dest) {
                        Image(systemName: "link.circle.fill")
                            .font(.ui(size: 16))
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
                    .font(.ui(.caption))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Divider()

            // Details Stack
            VStack(alignment: .leading, spacing: 5) {
                if let edu = founder.education {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "graduationcap.fill")
                            .font(.ui(size: 10))
                            .foregroundStyle(.secondary)
                            .frame(width: 14)
                        Text(edu)
                            .font(.ui(.caption2))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                if !founder.pastCompanies.isEmpty {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "building.2.fill")
                            .font(.ui(size: 10))
                            .foregroundStyle(.secondary)
                            .frame(width: 14)
                        Text(founder.pastCompanies.joined(separator: ", "))
                            .font(.ui(.caption2))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                if let exit = founder.priorExits {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "dollarsign.circle.fill")
                            .font(.ui(size: 10))
                            .foregroundStyle(.green)
                            .frame(width: 14)
                        Text("Prior Exit: \(exit)")
                            .font(.ui(.caption2).weight(.semibold))
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
                    .font(.ui(size: 10))
                    .foregroundStyle(color)
                Text(title)
                    .font(.dsLabel)
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.dsMetricSmall)
            Text(delta)
                .font(.ui(size: 10))
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
