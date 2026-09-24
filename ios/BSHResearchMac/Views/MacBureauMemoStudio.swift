//
//  MacBureauMemoStudio.swift
//  BSHResearchMac
//
//  The Memo Studio Workbench on Bureau's Research Desk, drawn as the website draws it
//  (components/MemoStudioEditor.vue and memo/MemoStudioBulletTree.vue): the header with
//  Refresh, Export Memo and Generate report; the spine banner; the not-investigated note;
//  the readiness strip; the jump bar; the five editorial sections, the readiness gates and
//  the evidence claims; and Warren's action queue beside the recoverable history.
//
//  It reads the memo editor as the website does (its options, top gate, ranks and history
//  are fields the Mac's model leaves out) and keeps the Mac's own card edits (include,
//  expand, rename, move, remove, add, rating, likelihood, refine framing) going through the
//  store. What the Mac's client has no call for yet (choose a conclusion, rerun a section,
//  open an appendix block, export, a task's status, a point's text) goes through the small
//  request helper below, with the same headers and token the client sends.
//

import AppKit
import SwiftUI

// MARK: - The memo editor as the website reads it

struct MacBureauMemo: Decodable {
    struct Ref: Decodable { let sourceClass: String? }
    struct Bullet: Decodable, Identifiable {
        let id: String
        let text: String?
        let sourceClass: String?
        let sourceRefs: [Ref]?
        let children: [Bullet]?
    }
    struct Card: Decodable, Identifiable {
        let id: String
        let title: String?
        let category: String?
        let severity: String?
        let likelihood: String?
        let agentRating: String?
        let included: Bool?
        let rank: Int?
        let expanded: Bool?
        let placeholder: Bool?
        let sourceClass: String?
        let sourceRefs: [Ref]?
        let bullets: [Bullet]?
    }
    struct CardSection: Decodable {
        let status: String?
        let cards: [Card]?
    }
    struct Summary: Decodable {
        let status: String?
        let body: String?
        let recommendation: String?
        let round: String?
        let topGate: String?
        let sourceClass: String?
        let sourceRefs: [Ref]?
    }
    struct Option: Decodable, Identifiable {
        let id: String
        let label: String?
        let text: String?
        let sourceClass: String?
        let sourceRefs: [Ref]?
    }
    struct Conclusion: Decodable {
        let status: String?
        let selectedOptionId: String?
        let options: [Option]?
    }
    struct Block: Decodable, Identifiable {
        let id: String
        let title: String?
        let status: String?
        let expanded: Bool?
        let facts: [String]?
        let sourceClass: String?
        let sourceRefs: [Ref]?
    }
    struct Appendix: Decodable {
        let status: String?
        let blocks: [Block]?
    }
    struct Sections: Decodable {
        let executiveSummary: Summary?
        let investmentThesis: CardSection?
        let risksMitigations: CardSection?
        let conclusion: Conclusion?
        let appendix: Appendix?
    }
    struct AgentRun: Decodable {
        let mode: String?
        let seededAt: String?
    }
    struct Audit: Decodable, Identifiable {
        let id: String?
        let event: String?
        let createdAt: String?
        var identity: String { id ?? (event ?? "") + (createdAt ?? "") }
    }
    struct MemoTask: Decodable, Identifiable {
        let id: String
        let title: String?
        let description: String?
        let status: String?
    }

    let versionId: String?
    let revisionId: String?
    let status: String?
    let updatedAt: String?
    let sections: Sections
    let agentRun: AgentRun?
    let auditRecords: [Audit]?
    let memoTasks: [MemoTask]?
}

struct MacBureauMemoHistory: Decodable {
    struct Version: Decodable {
        let revisionId: String?
        let event: String?
        let createdAt: String?
    }
    let versions: [Version]?
    let auditRecords: [MacBureauMemo.Audit]?
    let memoTasks: [MacBureauMemo.MemoTask]?
}

/// What an export projection answered.
struct MacBureauMemoExport: Decodable {
    struct Missing: Decodable {
        let location: String?
        let text: String?
        let terms: [String]?
    }
    struct Coverage: Decodable { let coverage: Double? }
    let blocked: Bool?
    let blockReason: String?
    let missingSources: [Missing]?
    let sourceCoverage: Coverage?
}

/// The memo editor's reads and the writes the Mac's API client has no call for yet, sent
/// with the client's headers and session token. Every write is a person's click.
enum MacBureauMemoRequests {
    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static func request(_ path: String, method: String, body: [String: Any]? = nil) throws -> URLRequest {
        guard let url = MacConfig.serverURL(path) else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        return req
    }

    private static func data(_ req: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    static func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        try decoder.decode(T.self, from: try await data(request(path, method: "GET")))
    }

    @discardableResult
    static func send(_ path: String, method: String, body: [String: Any]? = nil) async throws -> Data {
        try await data(request(path, method: method, body: body))
    }

    static func decode<T: Decodable>(_ type: T.Type, from data: Data) -> T? {
        try? decoder.decode(T.self, from: data)
    }
}

// MARK: - Scrolling the dossier to a section

private struct MacBureauDossierScrollKey: EnvironmentKey {
    static let defaultValue: ((String) -> Void)? = nil
}

extension EnvironmentValues {
    /// Scrolls the dossier to the view with the given id (the jump bar's sections).
    var bureauDossierScroll: ((String) -> Void)? {
        get { self[MacBureauDossierScrollKey.self] }
        set { self[MacBureauDossierScrollKey.self] = newValue }
    }
}

// MARK: - The workbench

struct MacBureauMemoStudio: View {
    let company: MacCompany
    let isPublic: Bool
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.bureauDossierScroll) private var scrollTo

    @State private var memo: MacBureauMemo?
    @State private var history: MacBureauMemoHistory?
    @State private var loading = true
    @State private var loadFailed = false
    @State private var actionFailed = false
    @State private var gatesLoaded = false
    @State private var gatesBusy = false
    @State private var activeNav = "executive_summary"
    @State private var addingSection: String?
    @State private var newCardTitle = ""
    @State private var editingTitleId: String?
    @State private var titleDraft = ""
    @State private var refiningRiskId: String?
    @State private var refineFraming = "other"
    @State private var refineNote = ""
    @State private var refineBusy = false
    @State private var refinedRiskIds: Set<String> = []
    @State private var exporting = false
    @State private var exportResult: MacBureauMemoExport?
    @State private var exportFailed = false
    @State private var synthesizing = false
    @State private var synthesisStarted = false
    @State private var saving: String?

    private var ink: MacBureauDeskInk { MacBureauDeskInk(colorScheme) }
    private var base: String { "companies/\(company.id)/memo-editor" }

    private static let sectionIds = ["executive_summary", "investment_thesis", "risks_mitigations", "conclusion", "appendix"]
    private static let doneStatuses: Set<String> = ["done", "complete", "completed", "approved", "ready"]

    private var reports: [MacReport] { store.reports(for: company.id) }
    private var awaitingStudioReport: MacReport? { reports.first { $0.status == "awaiting_studio" } }
    private var latestOpenableReport: MacReport? {
        reports.filter(\.canOpen).sorted { ($0.createdAt ?? "") > ($1.createdAt ?? "") }.first
    }

    private func cards(_ section: MacBureauMemo.CardSection?) -> [MacBureauMemo.Card] {
        var seen = Set<String>()
        return (section?.cards ?? [])
            .sorted { ($0.rank ?? 0) < ($1.rank ?? 0) }
            .filter { card in
                let bullets = (card.bullets ?? []).map { $0.text ?? "" }.joined(separator: "|")
                let signature = "\(card.title ?? "")|\(bullets)".lowercased()
                    .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
                guard !signature.isEmpty, !seen.contains(signature) else { return false }
                seen.insert(signature)
                return true
            }
    }

    private var thesisCards: [MacBureauMemo.Card] { cards(memo?.sections.investmentThesis) }
    private var riskCards: [MacBureauMemo.Card] { cards(memo?.sections.risksMitigations) }

    private var completedSections: Int {
        guard let s = memo?.sections else { return 0 }
        let statuses = [s.executiveSummary?.status, s.investmentThesis?.status, s.risksMitigations?.status, s.conclusion?.status, s.appendix?.status]
        return statuses.filter { Self.doneStatuses.contains(($0 ?? "").lowercased()) }.count
    }

    private var progress: Int { Int((Double(completedSections) / 5 * 100).rounded()) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            banner
            provenance
            if loading && memo == nil {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.mini)
                    Text("Loading memo editor…").font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary)
                }
                .padding(.vertical, 16)
            } else if loadFailed && memo == nil {
                errorNote(actionFailed ? "That memo action could not be completed. Please try again." : "The memo editor could not be loaded. Please try again.")
            } else if memo != nil {
                if actionFailed { errorNote("That memo action could not be completed. Please try again.") }
                readinessStrip
                if let exportResult { exportTile(exportResult) }
                if exportFailed {
                    Text("The memo export could not be prepared. Please try again.")
                        .font(BSHType.bureauSans(11)).foregroundStyle(ink.red)
                }
                jumpBar
                summarySection.id("memo-sec-executive_summary")
                thesisSection.id("memo-sec-investment_thesis")
                risksSection.id("memo-sec-risks_mitigations")
                conclusionSection.id("memo-sec-conclusion")
                appendixSection.id("memo-sec-appendix")
                gatesSection.id("memo-sec-readiness_gates")
                evidenceSection.id("memo-sec-evidence_claims")
                historyRow
            }
        }
        .padding(1 + 18)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 12, style: .circular), fill: ink.card, stroke: ink.hairline)
        .task(id: company.id) {
            memo = nil
            history = nil
            gatesLoaded = false
            synthesisStarted = false
            refiningRiskId = nil
            exportResult = nil
            await load()
        }
        .onChange(of: store.memoEditorByCompany[company.id]?.revisionId) { _, _ in
            // A card edit the store made: read the editor again for the fields it keeps.
            Task { await reloadMemo() }
        }
    }

    // MARK: Loading

    private func load() async {
        loading = true
        loadFailed = false
        actionFailed = false
        await reloadMemo()
        loading = false
        await loadHistory()
        await loadGates(create: false)
        if store.memoEditorByCompany[company.id] == nil { await store.loadMemoEditor(company.id) }
    }

    private func reloadMemo() async {
        do {
            memo = try await MacBureauMemoRequests.get(base, as: MacBureauMemo.self)
            loadFailed = false
        } catch {
            if memo == nil { loadFailed = true }
        }
    }

    private func loadHistory() async {
        history = try? await MacBureauMemoRequests.get("\(base)/history", as: MacBureauMemoHistory.self)
    }

    private func loadGates(create: Bool) async {
        gatesBusy = true
        await store.loadMemoAnalysis(company.id, create: create)
        await store.loadEvidence(company.id)
        gatesLoaded = true
        gatesBusy = false
    }

    /// Runs a write the Mac's client doesn't make, then reads the editor again.
    private func write(_ key: String, _ path: String, method: String, body: [String: Any]? = nil) {
        guard saving == nil else { return }
        saving = key
        actionFailed = false
        Task {
            do {
                try await MacBureauMemoRequests.send(path, method: method, body: body)
                await reloadMemo()
                await store.loadMemoEditor(company.id)
            } catch {
                actionFailed = true
            }
            saving = nil
        }
    }

    private func errorNote(_ text: String) -> some View {
        Text(text)
            .font(BSHType.bureauSans(11))
            .foregroundStyle(ink.red)
            .bureauDeskLine(13.75, 11)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.red.opacity(0.08))
    }

    // MARK: Header

    private var titleBlock: some View {
        HStack(spacing: 12) {
            MacBureauDeskIcon("sliders-horizontal", size: 16)
                .foregroundStyle(ink.accent)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text("Memo Studio Workbench")
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.3)
                        .foregroundStyle(ink.label)
                        .bureauDeskLine(18.75, 15)
                    Text("HUMAN-IN-THE-LOOP")
                        .font(BSHType.bureauSans(9, weight: .bold))
                        .tracking(0.225)
                        .foregroundStyle(ink.accent)
                        .bureauDeskLine(13.5, 9)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .bureauBox(Capsule(), fill: ink.accent.opacity(0.12))
                        .fixedSize()
                }
                Text("Direct analyst curation of AI thesis spine, dilemma weights, and readiness gates prior to synthesis")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .fixedSize()
                    .bureauDeskLine(13.75, 11)
            }
        }
        .fixedSize()
    }

    private var headerButtons: some View {
        HStack(spacing: 8) {
            Button {
                Task { await refresh() }
            } label: {
                MacBureauDeskButtonLabel(title: "Refresh", icon: "refresh-cw", iconSize: 12, size: .small)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
            .help("Refresh")

            Button {
                exportProjection()
            } label: {
                HStack(spacing: 4) {
                    if exporting { ProgressView().controlSize(.mini).frame(width: 12, height: 12) }
                    MacBureauDeskButtonLabel(title: "Export Memo", icon: exporting ? nil : "download", iconSize: 12, size: .small)
                }
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
            .disabled(exporting || loading)

            Button {
                store.requestNewReport(for: company)
            } label: {
                MacBureauDeskButtonLabel(title: "Generate report", orb: true, iconSize: 12, size: .small)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small))
            .disabled(!store.canRunTasks || loading)
        }
        .fixedSize()
    }

    /// The title and the buttons share a line when it is wide enough; otherwise the buttons
    /// wrap under it, as the website's flex-wrap row does.
    private var header: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: 12) {
                titleBlock
                Spacer(minLength: 8)
                headerButtons
            }
            VStack(alignment: .leading, spacing: 12) {
                titleBlock
                headerButtons
            }
        }
    }

    private func refresh() async {
        await store.loadMemoEditor(company.id)
        await reloadMemo()
        await loadHistory()
        await loadGates(create: false)
    }

    private func exportProjection() {
        guard !exporting else { return }
        exporting = true
        exportFailed = false
        Task {
            do {
                let data = try await MacBureauMemoRequests.send("\(base)/export-projection", method: "POST")
                exportResult = MacBureauMemoRequests.decode(MacBureauMemoExport.self, from: data)
                await loadHistory()
            } catch {
                exportFailed = true
            }
            exporting = false
        }
    }

    // MARK: Banners

    @ViewBuilder
    private var banner: some View {
        if let awaiting = awaitingStudioReport, !synthesisStarted {
            HStack(spacing: 12) {
                Circle().fill(ink.orange).frame(width: 10, height: 10)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Investigation Parked · Awaiting Studio Review")
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .foregroundStyle(ink.orange)
                        .bureauDeskLine(16.9, 13)
                    MacBureauWebParagraph(text: "Phases 1 & 2 completed. Refine thesis cards below and trigger institutional synthesis when ready.", size: 11, lineHeight: 13.75)
                        .foregroundStyle(ink.secondary)
                }
                Spacer(minLength: 8)
                Button {
                    guard !synthesizing else { return }
                    synthesizing = true
                    Task {
                        do {
                            _ = try await store.generateReportFromStudio(reportId: awaiting.id)
                            synthesisStarted = true
                        } catch {
                            actionFailed = true
                        }
                        synthesizing = false
                    }
                } label: {
                    MacBureauDeskButtonLabel(title: "Synthesize Phase 3 Memo", icon: "sparkles", iconSize: 12, size: .small)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small, tint: ink.orange))
                .disabled(synthesizing)
                .help("Freeze studio cards and synthesize Phase 3 memo")
            }
            .padding(12)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.orange.opacity(0.08), stroke: ink.orange.opacity(0.25))
        } else {
            HStack(spacing: 10) {
                MacBureauDeskIcon("circle-check", size: 14)
                    .foregroundStyle(ink.green)
                Text(synthesisStarted
                     ? "Phase 3 synthesis started — follow the run in Reports; this editor stays live."
                     : "Spine Editor Active · Live mutations persist immediately to the server.")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .bureauDeskLine(13.75, 11)
                Spacer(minLength: 8)
                if let report = latestOpenableReport {
                    Button {
                        store.openICReview(report: report)
                    } label: {
                        MacBureauDeskButtonLabel(title: "Open Memo View", icon: "book-open", iconSize: 12, size: .mini)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.secondary.opacity(0.04))
        }
    }

    @ViewBuilder
    private var provenance: some View {
        if let run = memo?.agentRun {
            Text("Cards seeded by the \(run.mode ?? "agent") agent run · \(String((run.seededAt ?? "").prefix(10))). Your edits become pinned facts the report must honor.")
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.accent.opacity(0.06))
        } else if !loading, memo != nil {
            HStack(spacing: 10) {
                MacBureauDeskIcon("triangle-alert", size: 16)
                    .foregroundStyle(ink.orange)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Not investigated yet")
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .foregroundStyle(ink.label)
                        .bureauDeskLine(16.9, 13)
                    MacBureauWebParagraph(
                        text: "The thesis and risk cards below are a starting template built from the company record, not research. Run Deep Investigate to replace them with source-backed cards.",
                        size: 11, lineHeight: 13.75
                    )
                    .foregroundStyle(ink.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    store.requestNewReport(for: company)
                } label: {
                    MacBureauDeskButtonLabel(title: "Run Deep Investigate", icon: "sparkles", iconSize: 12, size: .mini)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .mini))
                .disabled(!store.canRunTasks)
                .help(store.canRunTasks ? "Opens the report customizer on Studio review" : "Sign in with an analyst or partner role to run investigations")
            }
            .padding(12)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.orange.opacity(0.09))
        }
    }

    // MARK: Readiness strip

    private var readinessStrip: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 12) {
                    Text("\(completedSections) of 5 sections ready")
                        .font(BSHType.bureauSans(11))
                        .bureauDeskLine(13.75, 11)
                    Spacer(minLength: 0)
                    Text("\(progress)%")
                        .font(BSHType.bureauSans(11).monospacedDigit())
                        .bureauExactWidth("\(progress)%", size: 11, mono: true)
                        .bureauDeskLine(13.75, 11)
                }
                .foregroundStyle(ink.secondary)
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(ink.secondary.opacity(0.15))
                        Capsule()
                            .fill(progress == 100 ? ink.green : ink.accent)
                            .frame(width: proxy.size.width * CGFloat(progress) / 100)
                    }
                }
                .frame(height: 4)
            }
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)

            VStack(alignment: .leading, spacing: 2) {
                Text("\(memo?.versionId ?? "v1") · \(MacBureauMemoFormat.status(memo?.status, fallback: "Draft"))")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(14.3, 11)
                Text("Updated \(MacBureauMemoFormat.day(memo?.updatedAt, fallback: "Pending"))")
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(12.5, 10)
            }
            .fixedSize()
            .padding(12)
            .frame(maxHeight: .infinity, alignment: .top)
            .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func exportTile(_ result: MacBureauMemoExport) -> some View {
        let blocked = result.blocked == true
        let tone = blocked ? ink.orange : ink.green
        return HStack(alignment: .top, spacing: 10) {
            MacBureauDeskIcon(blocked ? "triangle-alert" : "circle-check", size: 16)
                .foregroundStyle(tone)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(blocked ? (result.blockReason ?? "Blocked") : "Export projection ready")
                    .font(BSHType.bureauSans(13, weight: .medium))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(16.9, 13)
                Text(result.sourceCoverage?.coverage.map { "\(Int(($0 * 100).rounded()))% source coverage" } ?? "coverage pending")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(13.75, 11)
                if blocked {
                    ForEach(Array((result.missingSources ?? []).enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text("\(item.location ?? ""):").font(BSHType.bureauSans(11, weight: .semibold))
                            Text((item.terms ?? []).joined(separator: ", ")).font(BSHType.bureauSans(11))
                        }
                        .foregroundStyle(ink.label)
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: tone.opacity(blocked ? 0.08 : 0.07), stroke: tone.opacity(blocked ? 0.25 : 0.22))
    }

    // MARK: Jump bar

    private var navItems: [(id: String, num: String, label: String, count: Int?)] {
        [
            ("executive_summary", "01", "Executive Summary", nil),
            ("investment_thesis", "02", "Investment Thesis", thesisCards.count),
            ("risks_mitigations", "03", "Risks and Mitigations", riskCards.count),
            ("conclusion", "04", "Conclusion", nil),
            ("appendix", "05", "Appendix", nil),
            ("readiness_gates", "06", "Readiness Gates", nil),
            ("evidence_claims", "07", "Evidence Claims", nil),
        ]
    }

    /// `.mac-tabbar` of the sections: its number, its name and, for the card sections, how
    /// many cards; the one last jumped to in ink and semibold.
    private var jumpBar: some View {
        VStack(spacing: 0) {
            // Not a scroll view: AppKit sets one on a whole device pixel, which moved the
            // names off the website's. What doesn't fit is cut off, as the website hides its
            // bar's overflow.
            Group {
                HStack(alignment: .bottom, spacing: 20) {
                    ForEach(navItems, id: \.id) { item in
                        let active = activeNav == item.id
                        Button {
                            activeNav = item.id
                            scrollTo?("memo-sec-\(item.id)")
                        } label: {
                            HStack(spacing: 6) {
                                Text(item.num)
                                    .font(BSHType.bureauSans(10).monospacedDigit())
                                    .foregroundStyle(active ? ink.accent : ink.secondary)
                                    .bureauExactWidth(item.num, size: 10, mono: true)
                                    .bureauDeskLine(12.5, 10)
                                Text(item.label)
                                    .font(BSHType.bureauSans(13, weight: active ? .semibold : .regular))
                                    .foregroundStyle(active ? ink.label : ink.secondary)
                                    .bureauExactWidth(item.label, size: 13, weight: active ? .semibold : .regular)
                                    .bureauDeskLine(19.5, 13)
                                if let count = item.count, count > 0 {
                                    Text("\(count)")
                                        .font(BSHType.bureauSans(10, weight: .bold).monospacedDigit())
                                        .foregroundStyle(active ? ink.label : ink.secondary)
                                        .bureauDeskLine(15, 10)
                                        .padding(.horizontal, 4)
                                        .bureauBox(Capsule(), fill: ink.label(0.08))
                                        .fixedSize()
                                }
                            }
                            .padding(.top, 4)
                            .padding(.bottom, 8)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 4)
                .fixedSize()
            }
            .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
            .frame(height: 31.5, alignment: .top)
            .clipped()
            MacBureauGridRule(color: ink.hairline)
        }
        .padding(.horizontal, -4)
    }

    // MARK: Section anatomy

    /// A section's head: its number, its title at 15pt semibold, what it keeps at the right,
    /// over a rule.
    private func sectionHead<Trailing: View>(_ num: String, _ title: String, numTone: Color? = nil, icon: String? = nil, @ViewBuilder trailing: () -> Trailing) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 8) {
                Text(num)
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(numTone ?? ink.accent)
                    .bureauExactWidth(num, size: 10, mono: true)
                    .bureauDeskLine(12.5, 10)
                HStack(spacing: 6) {
                    if let icon {
                        MacBureauDeskIcon(icon, size: 14).foregroundStyle(ink.accent)
                    }
                    Text(title)
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.3)
                        .foregroundStyle(ink.label)
                        .bureauDeskLine(18.75, 15)
                }
                Spacer(minLength: 8)
                trailing()
            }
            .frame(minHeight: 18.75)
            .padding(.bottom, 8)
            MacBureauGridRule(color: ink.hairline)
        }
    }

    private func miniButton(_ title: String, tint: Bool = false, disabled: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            MacBureauDeskButtonLabel(title: title, size: .mini)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: tint ? .tint : .bordered, size: .mini))
        .disabled(disabled)
    }

    private func rerun(_ sectionId: String) -> some View {
        miniButton("Rerun", disabled: saving == "rerun:\(sectionId)") {
            write("rerun:\(sectionId)", "\(base)/sections/\(sectionId)/rerun", method: "POST")
        }
    }

    private func tag(_ text: String, _ tint: Color) -> some View {
        MacBureauDeskTag(text: text, tint: tint)
    }

    private func sourceLabel(_ sourceClass: String?, _ refs: [MacBureauMemo.Ref]?) -> String {
        if let sourceClass, !sourceClass.isEmpty { return sourceClass }
        if let first = refs?.first?.sourceClass, !first.isEmpty { return first }
        return "source pending"
    }

    private func statusTone(_ status: String?) -> Color {
        let value = (status ?? "").lowercased()
        if Self.doneStatuses.contains(value) { return ink.green }
        if ["error", "failed", "blocked"].contains(value) { return ink.red }
        return ink.secondary
    }

    // MARK: 01 · Executive Summary

    private var summarySection: some View {
        let summary = memo?.sections.executiveSummary
        return VStack(alignment: .leading, spacing: 10) {
            sectionHead("01", "Executive Summary") {
                tag(MacBureauMemoFormat.status(summary?.status, fallback: "Not started"), statusTone(summary?.status))
                tag(sourceLabel(summary?.sourceClass, summary?.sourceRefs), ink.secondary)
                rerun("executive_summary")
            }
            VStack(alignment: .leading, spacing: 10) {
                MacBureauWebParagraph(text: summary?.body ?? "", size: 13, lineHeight: 19.5)
                    .foregroundStyle(ink.secondary)
                MacBureauDeskGrid(columns: isPublic ? 2 : 3, spacing: 10) {
                    summaryTile("Recommendation", summary?.recommendation ?? "")
                    if !isPublic {
                        summaryTile("Round", (summary?.round).flatMap { $0.isEmpty ? nil : $0 } ?? "Pending")
                    }
                    summaryTile("Top Gate", summary?.topGate ?? "")
                }
            }
            .padding(.leading, 3 + 12)
            .padding(.trailing, 12)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBackground {
                RoundedRectangle(cornerRadius: 10, style: .circular)
                    .fill(ink.tile)
                    .overlay(alignment: .leading) { stripe(ink.accent) }
            }
        }
    }

    /// The 3pt rule down a tile's left edge, following its rounded corners.
    private func stripe(_ tone: Color) -> some View {
        UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 10, style: .circular)
            .fill(tone)
            .frame(width: 10)
            .mask(alignment: .leading) { Rectangle().frame(width: 3) }
    }

    private func summaryTile(_ label: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
            MacBureauWebParagraph(text: text, size: 11, lineHeight: 15.4)
                .foregroundStyle(ink.secondary)
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
    }

    // MARK: 02 · Investment Thesis and 03 · Risks

    private var thesisSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHead("02", "Investment Thesis") { cardHeadTrailing("investment_thesis", count: thesisCards.count) }
            VStack(spacing: 8) {
                ForEach(Array(thesisCards.enumerated()), id: \.element.id) { index, card in
                    cardTile(card, section: "investment_thesis", index: index, total: thesisCards.count)
                }
            }
        }
    }

    private var includedRisks: Int { riskCards.filter { $0.included ?? true }.count }

    private var risksSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHead("03", "Risks and Mitigations", numTone: ink.red) {
                if includedRisks < 4 || includedRisks > 6 {
                    Text("\(includedRisks) included — aim for 4-6 risks")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.orange)
                        .bureauDeskLine(13.75, 11)
                        .fixedSize()
                }
                cardHeadTrailing("risks_mitigations", count: riskCards.count)
            }
            VStack(spacing: 8) {
                ForEach(Array(riskCards.enumerated()), id: \.element.id) { index, card in
                    cardTile(card, section: "risks_mitigations", index: index, total: riskCards.count)
                }
            }
        }
    }

    @ViewBuilder
    private func cardHeadTrailing(_ section: String, count: Int) -> some View {
        Text("\(count) cards")
            .font(BSHType.bureauSans(11))
            .foregroundStyle(ink.secondary)
            .bureauDeskLine(13.75, 11)
            .fixedSize()
        if addingSection == section {
            TextField("", text: $newCardTitle, prompt: Text("New card title").foregroundStyle(ink.tertiary))
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.label)
                .padding(.horizontal, 8)
                .frame(width: 192, height: 20)
                .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
                .onSubmit { addCard(section) }
        }
        miniButton(addingSection == section ? "Save card" : "Add card", tint: addingSection == section) {
            if addingSection == section {
                addCard(section)
            } else {
                addingSection = section
                newCardTitle = ""
            }
        }
        rerun(section)
    }

    private func addCard(_ section: String) {
        let title = newCardTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            addingSection = nil
            return
        }
        Task {
            await store.addMemoCard(companyId: company.id, sectionId: section, title: title)
            newCardTitle = ""
            addingSection = nil
            await reloadMemo()
        }
    }

    private func patch(_ section: String, _ card: MacBureauMemo.Card, included: Bool? = nil, expanded: Bool? = nil, title: String? = nil, severity: String? = nil, likelihood: String? = nil, rating: String? = nil) {
        Task {
            await store.patchMemoCard(
                companyId: company.id, sectionId: section, cardId: card.id,
                included: included, expanded: expanded, title: title,
                severity: severity, likelihood: likelihood, agentRating: rating
            )
            await reloadMemo()
        }
    }

    private func cardStripe(_ section: String, _ card: MacBureauMemo.Card) -> Color {
        guard section == "risks_mitigations" else { return ink.accent }
        switch (card.severity ?? "").lowercased() {
        case "high", "critical": return ink.red
        case "medium": return ink.orange
        default: return ink.secondary
        }
    }

    private func severityTint(_ severity: String?) -> Color {
        switch (severity ?? "").lowercased() {
        case "critical": return ink.red
        case "high": return ink.orange
        case "medium": return ink.yellow
        case "low": return ink.green
        default: return ink.secondary
        }
    }

    private func cardTile(_ card: MacBureauMemo.Card, section: String, index: Int, total: Int) -> some View {
        let isRisk = section == "risks_mitigations"
        let included = card.included ?? true
        let expanded = card.expanded ?? false
        return HStack(alignment: .top, spacing: 8) {
            MacBureauDeskIcon("grip-vertical", size: 14)
                .foregroundStyle(ink.secondary)
                .padding(2)
                .padding(.top, 2)
                .help("Drag to reorder")
            MacBureauDeskCheckbox(isOn: included) { patch(section, card, included: !included) }
                .padding(.top, 2)
                .help("Include \(card.title ?? "")")
            Text("\(card.rank ?? index + 1)")
                .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                .foregroundStyle(ink.label)
                .bureauDeskLine(18, 12)
                .frame(width: 20)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 0) {
                if editingTitleId == card.id {
                    TextField("", text: $titleDraft)
                        .textFieldStyle(.plain)
                        .font(BSHType.bureauSans(13, weight: .semibold))
                        .foregroundStyle(ink.label)
                        .padding(.horizontal, 8)
                        .frame(height: 24)
                        .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
                        .onSubmit { commitTitle(section, card) }
                        .onExitCommand { editingTitleId = nil }
                } else {
                    Button {
                        patch(section, card, expanded: !expanded)
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(card.title ?? "")
                                    .font(BSHType.bureauSans(13, weight: .medium))
                                    .foregroundStyle(card.placeholder == true ? ink.secondary : ink.label)
                                    .multilineTextAlignment(.leading)
                                    .bureauDeskLine(16.9, 13)
                                cardTags(card, isRisk: isRisk)
                            }
                            Spacer(minLength: 0)
                            MacBureauDeskIcon(expanded ? "chevron-down" : "chevron-right", size: 14)
                                .foregroundStyle(ink.secondary)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    .simultaneousGesture(TapGesture(count: 2).onEnded {
                        editingTitleId = card.id
                        titleDraft = card.title ?? ""
                    })
                    .help("Click to expand · double-click to rename")
                }
                if isRisk {
                    riskControls(card)
                        .padding(.top, 6)
                    if refiningRiskId == card.id {
                        refinePanel(card)
                            .padding(.top, 8)
                    }
                }
                if expanded {
                    MacBureauMemoBullets(
                        bullets: card.bullets ?? [],
                        depth: 0,
                        base: "\(base)/sections/\(section)/cards/\(card.id)",
                        cardTitle: card.title ?? "",
                        onChange: { Task { await reloadMemo() } },
                        onDiscuss: { text in discuss(card: card, section: section, text: text) }
                    )
                    .padding(.top, 10)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 2) {
                cardControl("chevron-up", disabled: index == 0, help: "Move up") {
                    Task {
                        await store.moveMemoCard(companyId: company.id, sectionId: section, cardId: card.id, direction: "up")
                        await reloadMemo()
                    }
                }
                cardControl("chevron-down", disabled: index == total - 1, help: "Move down") {
                    Task {
                        await store.moveMemoCard(companyId: company.id, sectionId: section, cardId: card.id, direction: "down")
                        await reloadMemo()
                    }
                }
                cardControl("x", disabled: false, help: "Remove card") {
                    Task {
                        await store.deleteMemoCard(companyId: company.id, sectionId: section, cardId: card.id)
                        await reloadMemo()
                    }
                }
            }
        }
        .padding(.leading, 3 + 10)
        .padding(.trailing, 10)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBackground {
            RoundedRectangle(cornerRadius: 10, style: .circular)
                .fill(ink.tile)
                .overlay(alignment: .leading) { stripe(cardStripe(section, card)) }
        }
        .opacity(included ? 1 : 0.55)
    }

    private func cardControl(_ icon: String, disabled: Bool, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            MacBureauDeskIcon(icon, size: 12)
                .foregroundStyle(ink.secondary)
                .padding(2)
                .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauFlatButtonStyle())
        .disabled(disabled)
        .opacity(disabled ? 0.3 : 1)
        .help(help)
    }

    private func cardTags(_ card: MacBureauMemo.Card, isRisk: Bool) -> some View {
        HStack(spacing: 6) {
            if card.placeholder == true {
                tag("Template", ink.orange)
                    .help("Built from the company record, not researched. Edit it, or run Deep Investigate to replace it.")
            }
            if isRisk {
                Text((card.severity.flatMap { $0.isEmpty ? nil : $0 } ?? "risk").uppercased())
                    .font(BSHType.bureauSans(9, weight: .bold))
                    .foregroundStyle(severityTint(card.severity))
                    .bureauDeskLine(13.5, 9)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .bureauBox(Capsule(), fill: severityTint(card.severity).opacity(0.15))
                    .fixedSize()
            }
            if let category = card.category, !category.isEmpty {
                tag(category, ink.secondary)
            }
            tag(sourceLabel(card.sourceClass, card.sourceRefs), ink.secondary)
            if isRisk, refinedRiskIds.contains(card.id) {
                tag("Refined", ink.green)
            }
            if !isRisk {
                Text("\(card.sourceRefs?.count ?? 0) sources")
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(12.5, 10)
                    .fixedSize()
            }
        }
    }

    private func commitTitle(_ section: String, _ card: MacBureauMemo.Card) {
        let title = titleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        editingTitleId = nil
        guard !title.isEmpty, title != card.title else { return }
        patch(section, card, title: title)
    }

    private static let ratings = (1...10).reversed().map { "\($0)/10" }
    private static let likelihoods = ["High", "Medium", "Low"]

    private func severity(fromRating rating: String) -> String {
        guard let value = Int(rating.split(separator: "/").first ?? "") else { return "medium" }
        return value >= 8 ? "high" : (value >= 5 ? "medium" : "low")
    }

    private func riskControls(_ card: MacBureauMemo.Card) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 4) {
                Text("Rating").font(BSHType.bureauSans(10)).foregroundStyle(ink.secondary).bureauDeskLine(12.5, 10)
                MacBureauDeskSelect(value: card.agentRating ?? "", options: Self.ratings, width: 55) { rating in
                    patch("risks_mitigations", card, severity: severity(fromRating: rating), rating: rating)
                }
            }
            HStack(spacing: 4) {
                Text("Likelihood").font(BSHType.bureauSans(10)).foregroundStyle(ink.secondary).bureauDeskLine(12.5, 10)
                MacBureauDeskSelect(value: card.likelihood ?? "", options: Self.likelihoods, width: 69) { likelihood in
                    patch("risks_mitigations", card, likelihood: likelihood)
                }
            }
            Spacer(minLength: 0)
            Button {
                if refiningRiskId == card.id {
                    refiningRiskId = nil
                } else {
                    refiningRiskId = card.id
                    refineFraming = "other"
                    refineNote = ""
                }
            } label: {
                MacBureauDeskButtonLabel(title: refiningRiskId == card.id ? "Done" : "Refine Framing", icon: "sliders-horizontal", iconSize: 10, size: .mini)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: refiningRiskId == card.id ? .tint : .bordered, size: .mini))
        }
    }

    private static let framings: [(String, String)] = [
        ("other", "Other / Nuanced"), ("overstated", "Overstated Threat"),
        ("understated", "Understated Risk"), ("mitigated", "Adequately Mitigated"),
    ]

    private func refinePanel(_ card: MacBureauMemo.Card) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Text("Framing Override:")
                    .font(BSHType.bureauSans(10, weight: .semibold))
                    .foregroundStyle(ink.label)
                Picker("", selection: $refineFraming) {
                    ForEach(Self.framings, id: \.0) { value, label in Text(label).tag(value) }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .controlSize(.small)
                .fixedSize()
            }
            TextField("", text: $refineNote, prompt: Text("Add analyst steering note (injected into Phase 3 synthesis)…").foregroundStyle(ink.tertiary))
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(13))
                .foregroundStyle(ink.label)
                .padding(.horizontal, 8)
                .frame(height: 26)
                .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
            HStack {
                Spacer()
                Button {
                    guard !refineBusy else { return }
                    refineBusy = true
                    Task {
                        await store.refineRisk(companyId: company.id, riskId: card.id, framing: refineFraming, analystNote: refineNote)
                        refinedRiskIds.insert(card.id)
                        refiningRiskId = nil
                        refineBusy = false
                        await reloadMemo()
                    }
                } label: {
                    MacBureauDeskButtonLabel(title: "Apply Refinement", size: .small)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small))
                .disabled(refineBusy)
            }
        }
        .padding(10)
        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.04))
    }

    private func discuss(card: MacBureauMemo.Card, section: String, text: String) {
        let point = card.title?.isEmpty == false ? card.title! : "memo point"
        let body: [String: Any] = [
            "action_type": "discuss",
            "title": "Discuss: \(point)",
            "description": text.isEmpty ? "Review this memo point with Warren." : text,
            "context": ["section_id": section, "card_id": card.id, "card_title": card.title ?? "", "bullet_text": text, "company_id": company.id, "memo_version_id": memo?.versionId ?? ""],
            "status": "proposed",
        ]
        Task {
            _ = try? await MacBureauMemoRequests.send("\(base)/tasks", method: "POST", body: body)
            await loadHistory()
        }
        store.askWarren(
            "Discuss this memo point: \(text.isEmpty ? point : text)",
            context: MacCopilotContext(surface: "research", tab: "memo"),
            company: company
        )
    }

    // MARK: 04 · Conclusion

    private var conclusionSection: some View {
        let conclusion = memo?.sections.conclusion
        return VStack(alignment: .leading, spacing: 10) {
            sectionHead("04", "Conclusion") { rerun("conclusion") }
            MacBureauDeskGrid(columns: 3, spacing: 10) {
                ForEach(conclusion?.options ?? []) { option in
                    let chosen = conclusion?.selectedOptionId == option.id
                    Button {
                        guard !chosen else { return }
                        write("conclusion:\(option.id)", "\(base)/conclusion/select", method: "POST", body: ["conclusion_id": option.id])
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                MacBureauDeskIcon(chosen ? "circle-check" : "circle", size: 14)
                                    .foregroundStyle(chosen ? ink.accent : ink.secondary)
                                Text(option.label ?? "")
                                    .font(BSHType.bureauSans(13, weight: .medium))
                                    .foregroundStyle(ink.label)
                                    .bureauDeskLine(16.9, 13)
                            }
                            MacBureauWebParagraph(text: option.text ?? "", size: 11, lineHeight: 15.95)
                                .foregroundStyle(ink.secondary)
                            Text(sourceLabel(option.sourceClass, option.sourceRefs))
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(ink.tertiary)
                                .bureauDeskLine(12.5, 10)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                        .bureauBox(
                            RoundedRectangle(cornerRadius: 10, style: .circular),
                            fill: chosen ? ink.accent.opacity(0.1) : ink.tile,
                            stroke: chosen ? ink.accent.opacity(0.4) : nil
                        )
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                }
            }
        }
    }

    // MARK: 05 · Appendix

    private var appendixSection: some View {
        let blocks = memo?.sections.appendix?.blocks ?? []
        return VStack(alignment: .leading, spacing: 10) {
            sectionHead("05", "Appendix") {
                Text("Collapsed by default")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(13.75, 11)
                    .fixedSize()
                rerun("appendix")
            }
            VStack(spacing: 0) {
                ForEach(Array(blocks.enumerated()), id: \.element.id) { index, block in
                    VStack(alignment: .leading, spacing: 0) {
                        if index > 0 { MacBureauGridRule(color: ink.hairline) }
                        VStack(alignment: .leading, spacing: 8) {
                            Button {
                                write("appendix:\(block.id)", "\(base)/appendix/\(block.id)", method: "PATCH", body: ["expanded": !(block.expanded ?? false)])
                            } label: {
                                HStack(spacing: 12) {
                                    HStack(spacing: 6) {
                                        Text(block.title ?? "")
                                            .font(BSHType.bureauSans(13, weight: .medium))
                                            .foregroundStyle(ink.label)
                                            .bureauDeskLine(16.9, 13)
                                        tag(MacBureauMemoFormat.status(block.status, fallback: "Pending"), statusTone(block.status))
                                        tag(sourceLabel(block.sourceClass, block.sourceRefs), ink.secondary)
                                    }
                                    Spacer(minLength: 0)
                                    MacBureauDeskIcon(block.expanded == true ? "chevron-down" : "chevron-right", size: 14)
                                        .foregroundStyle(ink.secondary)
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(MacBureauFlatButtonStyle())
                            if block.expanded == true {
                                VStack(alignment: .leading, spacing: 4) {
                                    ForEach(Array((block.facts ?? []).enumerated()), id: \.offset) { _, fact in
                                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                                            Text("•").font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary)
                                            MacBureauWebParagraph(text: fact, size: 11, lineHeight: 13.75)
                                                .foregroundStyle(ink.secondary)
                                        }
                                    }
                                }
                                .padding(.leading, 8)
                            }
                        }
                        .padding(10)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
        }
    }

    // MARK: 06 · Readiness Gates and 07 · Evidence Claims

    private var gatesSection: some View {
        let areas = store.analysisByCompany[company.id]?.additionalAreas ?? []
        return VStack(alignment: .leading, spacing: 10) {
            sectionHead("06", "Readiness Gates", icon: "list-checks") {
                if gatesBusy { ProgressView().controlSize(.mini) }
                miniButton(gatesLoaded ? "Refresh" : "Load", disabled: gatesBusy) {
                    Task { await loadGates(create: true) }
                }
            }
            if !gatesLoaded {
                Text("Loads readiness areas and evidence claims from the company's Memo Studio session on the server.")
                    .font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary).bureauDeskLine(13.75, 11)
            } else if areas.isEmpty {
                emptyState(icon: "list-checks", title: "No diligence readiness areas logged yet.", hint: "Run the readiness tool or memo analysis to compute stage compliance.")
            } else {
                ForEach(areas, id: \.id) { area in
                    let status = (area.status ?? "open").lowercased()
                    let tone = ["clear", "passed", "approved", "reviewed"].contains(status) ? ink.green
                        : (["blocker", "critical", "failed"].contains(status) ? ink.red : ink.orange)
                    let icon = ["clear", "passed", "approved", "reviewed"].contains(status) ? "circle-check"
                        : (status == "waived" ? "circle-minus" : (["blocker", "critical", "failed"].contains(status) ? "circle-x" : "triangle-alert"))
                    HStack(spacing: 10) {
                        MacBureauDeskIcon(icon, size: 14).foregroundStyle(tone)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(area.area ?? area.id)
                                .font(BSHType.bureauSans(13, weight: .medium))
                                .foregroundStyle(ink.label)
                                .bureauDeskLine(16.9, 13)
                            if let notes = area.rationale ?? area.whyItMatters, !notes.isEmpty {
                                MacBureauWebParagraph(text: notes, size: 11, lineHeight: 13.75, maxLines: 2)
                                    .foregroundStyle(ink.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        tag((area.status ?? "open").prefix(1).uppercased() + (area.status ?? "open").dropFirst(), tone)
                    }
                    .padding(10)
                    .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
                }
            }
        }
    }

    private var evidenceSection: some View {
        let evidence = store.evidenceByCompany[company.id]
        let claims = evidence?.claims ?? []
        return VStack(alignment: .leading, spacing: 10) {
            sectionHead("07", "Evidence Claims", icon: "file-search") {
                if evidence != nil {
                    Text("\(claims.count)")
                        .font(BSHType.bureauSans(11).monospacedDigit())
                        .foregroundStyle(ink.secondary)
                        .bureauExactWidth("\(claims.count)", size: 11, mono: true)
                        .bureauDeskLine(13.75, 11)
                }
            }
            if evidence == nil {
                Text("Loaded together with the readiness gates above.")
                    .font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary).bureauDeskLine(13.75, 11)
            } else if claims.isEmpty {
                emptyState(icon: "file-search", title: "No factual claims logged in evidence matrix.", hint: "Evidence matrix is generated during deep research extraction.")
            } else {
                ForEach(claims) { claim in
                    let status = claim.statusLabel.lowercased()
                    let tone = status == "supported" ? ink.green : (status == "contradicted" ? ink.red : (status == "partial" || status == "mixed" ? ink.orange : ink.secondary))
                    let label = status == "supported" ? "SUPPORTED" : (status == "contradicted" ? "CONTRADICTED" : (status == "partial" || status == "mixed" ? "MIXED" : "UNVERIFIED"))
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .top, spacing: 8) {
                            Text(label)
                                .font(BSHType.bureauSans(9, weight: .bold))
                                .foregroundStyle(tone)
                                .bureauDeskLine(13.5, 9)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .bureauBox(Capsule(), fill: tone.opacity(0.12))
                                .fixedSize()
                            MacBureauWebParagraph(text: claim.claim, size: 13, weight: .medium, lineHeight: 16.9)
                                .foregroundStyle(ink.label)
                        }
                        ForEach(Array(claim.supportingEvidence.prefix(3).enumerated()), id: \.offset) { _, entry in
                            if let excerpt = entry.excerpt, !excerpt.isEmpty {
                                MacBureauWebParagraph(text: excerpt, size: 11, lineHeight: 13.75, maxLines: 2)
                                    .foregroundStyle(ink.secondary)
                                    .padding(.leading, 12)
                            }
                        }
                    }
                    .padding(10)
                    .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
                }
            }
        }
    }

    private func emptyState(icon: String, title: String, hint: String) -> some View {
        VStack(spacing: 4) {
            MacBureauDeskIcon(icon, size: 24).foregroundStyle(ink.tertiary)
            Text(title)
                .font(BSHType.bureauSans(13, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(16.9, 13)
            Text(hint)
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.tertiary)
                .bureauDeskLine(13.75, 11)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
    }

    // MARK: Action queue and history

    private var tasks: [MacBureauMemo.MemoTask] {
        var seen = Set<String>()
        return (history?.memoTasks ?? memo?.memoTasks ?? []).filter { task in
            let signature = "\(task.title ?? "")|\(task.description ?? "")".lowercased()
                .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
            guard !signature.isEmpty, !seen.contains(signature) else { return false }
            seen.insert(signature)
            return true
        }
    }

    private var audits: [MacBureauMemo.Audit] { history?.auditRecords ?? memo?.auditRecords ?? [] }
    private var versions: [MacBureauMemoHistory.Version] { history?.versions ?? [] }

    /// `grid-cols-[1.1fr_0.9fr]`: the queue a little wider than the history, both as tall
    /// as the taller.
    private var historyRow: some View {
        MacBureauDeskColumns(weights: [1.1, 0.9], spacing: 12) {
            actionQueue
            recoverableHistory
        }
    }

    private func tileHead(_ label: String, _ title: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
            Text(title)
                .font(BSHType.bureauSans(15, weight: .semibold))
                .foregroundStyle(ink.label)
                .bureauDeskLine(18.75, 15)
        }
    }

    private var actionQueue: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                tileHead("Tasks from Warren", "Action queue")
                Spacer(minLength: 0)
                Text("\(tasks.count)")
                    .font(BSHType.bureauSans(11).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                    .bureauExactWidth("\(tasks.count)", size: 11, mono: true)
                    .bureauDeskLine(13.75, 11)
            }
            if tasks.isEmpty {
                Text("Edit, research, and discussion actions will appear here.")
                    .font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary).bureauDeskLine(13.75, 11)
            }
            ForEach(tasks) { task in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .top, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(task.title ?? "")
                                .font(BSHType.bureauSans(13, weight: .medium))
                                .foregroundStyle(ink.label)
                                .bureauDeskLine(16.9, 13)
                            if let description = task.description, !description.isEmpty {
                                MacBureauWebParagraph(text: description, size: 11, lineHeight: 15.4)
                                    .foregroundStyle(ink.secondary)
                            }
                        }
                        Spacer(minLength: 0)
                        let status = (task.status ?? "").lowercased()
                        tag(MacBureauMemoFormat.status(task.status, fallback: "Pending"),
                            status == "accepted" || status == "completed" ? ink.green : (status == "rejected" ? ink.red : ink.secondary))
                    }
                    HStack(spacing: 6) {
                        taskButton(task, "accepted", "Accept", prominent: true)
                        taskButton(task, "rejected", "Dismiss")
                        taskButton(task, "completed", "Complete")
                    }
                }
                .padding(10)
                .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private func taskButton(_ task: MacBureauMemo.MemoTask, _ status: String, _ title: String, prominent: Bool = false) -> some View {
        Button {
            write("task:\(task.id)", "\(base)/tasks/\(task.id)", method: "PATCH", body: ["status": status])
            Task { await loadHistory() }
        } label: {
            MacBureauDeskButtonLabel(title: title, size: .mini)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: prominent ? .prominent : .bordered, size: .mini))
        .disabled(saving == "task:\(task.id)" || task.status == status)
    }

    private var recoverableHistory: some View {
        VStack(alignment: .leading, spacing: 10) {
            tileHead("Audit & Versions", "Recoverable history")
            MacBureauDeskGrid(columns: 2, spacing: 8) {
                stat("Revisions", versions.count)
                stat("Audit events", audits.count)
            }
            if !versions.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(MacBureauMemoFormat.runs(versions, key: { $0.event ?? "" }).prefix(6).enumerated()), id: \.offset) { index, run in
                        VStack(alignment: .leading, spacing: 0) {
                            if index > 0 { MacBureauGridRule(color: ink.hairline) }
                            VStack(alignment: .leading, spacing: 0) {
                                HStack(spacing: 12) {
                                    Text(Self.revisionLabel(first: run.first, last: run.last, count: run.count))
                                        .font(BSHType.bureauSans(10))
                                        .foregroundStyle(ink.label)
                                        .bureauDeskLine(12.5, 10)
                                    Spacer(minLength: 0)
                                    Text(Self.eventLabel(run.first.event, count: run.count))
                                        .font(BSHType.bureauSans(10))
                                        .foregroundStyle(ink.secondary)
                                        .bureauDeskLine(12.5, 10)
                                }
                                // An inline span under the row: it rides the block's 24pt line.
                                Text(MacBureauMemoFormat.relative(run.first.createdAt))
                                    .font(BSHType.bureauSans(10).monospacedDigit())
                                    .foregroundStyle(ink.tertiary)
                                    .bureauStrutLine(10)
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                        }
                    }
                }
                .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
            }
            if !audits.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(MacBureauMemoFormat.runs(audits, key: { "\($0.event ?? "")|\(MacBureauMemoFormat.day($0.createdAt, fallback: ""))" }).prefix(8).enumerated()), id: \.offset) { _, run in
                        HStack(spacing: 0) {
                            Text(Self.eventLabel(run.first.event, count: run.count))
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(ink.secondary)
                                .bureauStrutLine(10)
                            Text(Self.dayLabel(run.first.createdAt))
                                .font(BSHType.bureauSans(10).monospacedDigit())
                                .foregroundStyle(ink.tertiary)
                                .bureauStrutLine(10)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.tile)
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private static func revisionLabel(first: MacBureauMemoHistory.Version, last: MacBureauMemoHistory.Version, count: Int) -> String {
        let newest = first.revisionId ?? ""
        return count > 1 ? "\(last.revisionId ?? "") – \(newest)" : newest
    }

    private static func eventLabel(_ event: String?, count: Int) -> String {
        let label = MacBureauMemoFormat.status(event, fallback: "Pending")
        return count > 1 ? "\(label) ×\(count)" : label
    }

    private static func dayLabel(_ stamp: String?) -> String {
        " · " + MacBureauMemoFormat.day(stamp, fallback: "")
    }

    private func stat(_ label: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
            Text("\(value)")
                .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                .foregroundStyle(ink.label)
                .bureauDeskLine(18, 15)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
    }
}

// MARK: - A card's points

/// MemoStudioBulletTree: each point in 11pt ink with its source under it, ruled off from
/// the next; its Edit, Dive deeper and Discuss appear when the pointer is over it.
private struct MacBureauMemoBullets: View {
    let bullets: [MacBureauMemo.Bullet]
    let depth: Int
    let base: String
    let cardTitle: String
    let onChange: () -> Void
    let onDiscuss: (String) -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var editingId: String?
    @State private var draft = ""
    @State private var busyId: String?
    @State private var hoveredId: String?
    @State private var failed: String?

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(bullets.enumerated()), id: \.element.id) { index, bullet in
                VStack(alignment: .leading, spacing: 0) {
                    if index > 0 || depth > 0 { MacBureauGridRule(color: ink.hairline) }
                    point(bullet, ink: ink)
                        .padding(.vertical, 8)
                    if let children = bullet.children, !children.isEmpty {
                        MacBureauMemoBullets(bullets: children, depth: depth + 1, base: base, cardTitle: cardTitle, onChange: onChange, onDiscuss: onDiscuss)
                            .padding(.leading, 12)
                            .overlay(alignment: .leading) { Rectangle().fill(ink.hairline).frame(width: 1) }
                            .padding(.top, 6)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func point(_ bullet: MacBureauMemo.Bullet, ink: MacBureauDeskInk) -> some View {
        if editingId == bullet.id {
            VStack(alignment: .leading, spacing: 8) {
                TextEditor(text: $draft)
                    .font(BSHType.bureauSans(13))
                    .scrollContentBackground(.hidden)
                    .padding(4)
                    .frame(minHeight: 60)
                    .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
                HStack(spacing: 6) {
                    Button {
                        save(bullet)
                    } label: {
                        MacBureauDeskButtonLabel(title: busyId == bullet.id ? "Saving…" : "Save", icon: "save", iconSize: 12, size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small))
                    .disabled(busyId == bullet.id)
                    Button {
                        editingId = nil
                    } label: {
                        MacBureauDeskButtonLabel(title: "Cancel", icon: "x", iconSize: 12, size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                MacBureauWebParagraph(text: bullet.text ?? "", size: 11, lineHeight: 16.5)
                    .foregroundStyle(ink.label)
                HStack(spacing: 6) {
                    MacBureauDeskTag(text: bullet.sourceClass.flatMap { $0.isEmpty ? nil : $0 } ?? bullet.sourceRefs?.first?.sourceClass ?? "source pending", tint: ink.secondary)
                    Spacer(minLength: 0)
                    HStack(spacing: 4) {
                        action("pencil", help: "Edit") {
                            editingId = bullet.id
                            draft = bullet.text ?? ""
                        }
                        action("circle-plus", help: "Dive deeper") { diveDeeper(bullet) }
                            .disabled(busyId == bullet.id)
                        action("message-square", help: "Discuss") { onDiscuss(bullet.text ?? "") }
                    }
                    .opacity(hoveredId == bullet.id ? 1 : 0)
                }
                if failed == bullet.id {
                    Text("That memo action could not be completed. Please try again.")
                        .font(BSHType.bureauSans(10)).foregroundStyle(ink.red)
                }
            }
            .contentShape(Rectangle())
            .onHover { inside in
                if inside { hoveredId = bullet.id } else if hoveredId == bullet.id { hoveredId = nil }
            }
        }
    }

    private func action(_ icon: String, help: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            MacBureauDeskIcon(icon, size: 12).frame(height: 12)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: .plain, size: .mini))
        .help(help)
    }

    private func save(_ bullet: MacBureauMemo.Bullet) {
        busyId = bullet.id
        failed = nil
        Task {
            do {
                try await MacBureauMemoRequests.send("\(base)/bullets/\(bullet.id)", method: "PATCH", body: ["text": draft])
                editingId = nil
                onChange()
            } catch {
                failed = bullet.id
            }
            busyId = nil
        }
    }

    private func diveDeeper(_ bullet: MacBureauMemo.Bullet) {
        busyId = bullet.id
        failed = nil
        Task {
            do {
                try await MacBureauMemoRequests.send("\(base)/bullets/\(bullet.id)/dive-deeper", method: "POST", body: ["text": NSNull()])
                onChange()
                onDiscuss(bullet.text ?? "")
            } catch {
                failed = bullet.id
            }
            busyId = nil
        }
    }
}

// MARK: - Controls

/// The website's checkbox (`accent-color` brass): a 14pt rounded square, filled with brass
/// and checked when on, fresh paper ruled in gray when off.
struct MacBureauDeskCheckbox: View {
    let isOn: Bool
    let toggle: () -> Void

    var body: some View {
        Button(action: toggle) {
            MacBureauDeskCheckMark(isOn: isOn)
                .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauFlatButtonStyle())
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(isOn ? "On" : "Off")
    }
}

/// A small `select.mac-field`: the value (or "—") on fresh paper with the menu's chevron.
private struct MacBureauDeskSelect: View {
    let value: String
    let options: [String]
    let width: CGFloat
    let choose: (String) -> Void
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        Menu {
            ForEach(options, id: \.self) { option in
                Button(option) { choose(option) }
            }
        } label: {
            HStack(spacing: 2) {
                Text(value.isEmpty ? "—" : value)
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(12.5, 10)
                Spacer(minLength: 0)
                MacBureauDeskIcon("chevron-down", size: 10)
                    .foregroundStyle(ink.label)
            }
            .padding(.horizontal, 5)
            .frame(width: width, height: 19)
            .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
            .contentShape(Rectangle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
    }
}

// MARK: - Words

enum MacBureauMemoFormat {
    private static let labels: [String: String] = [
        "complete": "Ready", "completed": "Ready", "awaiting_studio": "Cards ready",
        "complete_with_warnings": "Needs attention", "english_ready_paused": "English ready — paused",
        "failed": "Failed", "failed_during_analysis": "Failed", "failed_scope_check": "Failed",
        "failed_quality_gate": "Failed", "failed_orphaned": "Failed", "memo_task_created": "Task created",
        "in_progress": "Running", "ready_for_input": "Needs input", "not_started": "Not started",
        "proposed": "Proposed", "accepted": "Accepted", "rejected": "Dismissed",
    ]

    /// humanizeStatus (formatters.js).
    static func status(_ value: String?, fallback: String) -> String {
        let normalized = (value ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        guard !normalized.isEmpty else { return fallback }
        if let label = labels[normalized] { return label }
        return normalized
            .replacingOccurrences(of: "[_-]+", with: " ", options: .regularExpression)
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    /// formatIsoDate: the day of an ISO stamp.
    static func day(_ value: String?, fallback: String) -> String {
        guard let value, value.count >= 10 else { return fallback }
        return String(value.prefix(10))
    }

    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    /// formatRelativeTime: "16 hr. ago", as Intl's short style says it.
    static func relative(_ value: String?) -> String {
        guard let value, let date = iso.date(from: value) ?? isoPlain.date(from: value) else { return day(value, fallback: "") }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        formatter.dateTimeStyle = .named
        formatter.locale = Locale(identifier: "en_US")
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    /// collapseRuns: consecutive rows that say the same thing, folded into one.
    static func runs<Row>(_ rows: [Row], key: (Row) -> String) -> [(first: Row, last: Row, count: Int)] {
        var result: [(key: String, first: Row, last: Row, count: Int)] = []
        for row in rows {
            let k = key(row)
            if let tail = result.last, tail.key == k {
                result[result.count - 1] = (k, tail.first, row, tail.count + 1)
            } else {
                result.append((k, row, row, 1))
            }
        }
        return result.map { ($0.first, $0.last, $0.count) }
    }
}
