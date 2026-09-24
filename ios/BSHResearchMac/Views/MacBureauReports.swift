//
//  MacBureauReports.swift
//  BSHResearchMac
//
//  Reports under Bureau, laid out as the website's Reports desk (ReportsView.vue and
//  DocumentViewerWindow.vue): two trays on the sheet. The list tray holds the desk's title
//  and count, the search with Generate and refresh beside it, the company and status
//  filters, and the reports (or "No reports found" and a brass Generate report); the arrow
//  in its header folds it to a rail of logos. The viewer tray holds the open report's
//  header and the Mac's reader (PDFs in PDFKit with the iPad's ink, Word files in Quick
//  Look), or "Select a report to view".
//
//  Transcripts are the Mac's own: the waveform beside the fold arrow turns the list tray to
//  the call transcripts, and the viewer to the one chosen and its highlights.
//

import AppKit
import PDFKit
import SwiftUI

// MARK: - The page

struct MacBureauReportsDesk: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    /// The Mac's "Files & memos | Transcripts" choice, kept under the key the other designs use.
    @AppStorage("mac.documents.mode") private var mode = "files"
    /// Folded to a rail of logos, as the website's `bsh.reportsListCollapsed`.
    @AppStorage("bsh.reportsListCollapsed") private var listCollapsed = false

    @State private var query = ""
    @State private var companyFilter = "all"
    @State private var statusFilter = "all"
    @State private var kindFilter = "all"
    @State private var showDismissed = false
    @State private var expandedGroups: Set<String> = []
    @State private var refreshing = false
    /// What the list reads beyond the Mac's report model: the call, its headline, the review,
    /// versions and whether a run was cleared (GET /api/reports).
    @State private var extras: [String: MacBureauReportsExtras] = [:]

    @State private var transcriptQuery = ""
    @State private var transcriptCompany = "all"
    @State private var transcriptKind = "all"
    @State private var transcriptId: String?
    @State private var transcriptsLoading = false
    @State private var showAddTranscript = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var transcriptsMode: Bool { mode == "transcripts" }
    private var model: MacBureauReportsModel {
        MacBureauReportsModel(
            reports: store.reports,
            extras: extras,
            companies: store.companies,
            query: query,
            company: companyFilter,
            status: statusFilter,
            kind: kindFilter,
            showDismissed: showDismissed,
            expanded: expandedGroups
        )
    }

    var body: some View {
        let model = model
        HStack(alignment: .top, spacing: 12) {
            if listCollapsed {
                rail(model)
            } else {
                listTray(model)
            }
            viewerTray(model)
        }
        .padding(.top, 4)
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .animation(.easeInOut(duration: 0.18), value: listCollapsed)
        .onChange(of: store.transcriptToOpen, initial: true) { _, id in
            guard let id else { return }
            mode = "transcripts"
            transcriptId = id
            store.transcriptToOpen = nil
        }
        // The rail's Reports page for a company: its reports.
        .onChange(of: store.documentsCompanyFilter, initial: true) { _, id in
            guard let id else { return }
            mode = "files"
            companyFilter = id
            store.documentsCompanyFilter = nil
        }
        .onChange(of: store.selectedReport?.id) { _, _ in openSelected() }
        .onChange(of: store.reports.isEmpty) { _, empty in
            if !empty { chooseFirst() }
        }
        .onChange(of: model.filteredIds) { _, ids in keepSelection(in: ids) }
        .task(id: extrasKey) { await loadExtras() }
        .task { chooseFirst() }
        .task(id: transcriptsMode) {
            if transcriptsMode { await loadTranscripts() }
        }
        .sheet(isPresented: $showAddTranscript) {
            MacAddTranscriptSheet { id in transcriptId = id }
        }
    }

    // MARK: Selection

    /// The desk has been shown in this session (its first showing picks as the website does).
    private static var shownOnce = false

    /// Nothing chosen: open the newest report that has something to read, as the website does.
    /// The app starts with its most recent report selected, readable or not; on the desk's
    /// first showing one that has nothing to read yields to that pick.
    private func chooseFirst() {
        guard !store.reports.isEmpty else { return }
        let first = !Self.shownOnce
        Self.shownOnce = true
        if let current = store.selectedReport, store.reports.contains(where: { $0.id == current.id }),
           !first || MacBureauReportsModel.canOpen(current, extras[current.id]) && MacBureauReportsModel.isComplete(current) {
            if store.openReportId != current.id || (store.openDocumentURL == nil && !store.openingMemo) {
                openSelected()
            }
            return
        }
        let visible = store.reports.filter { !MacBureauReportsModel.isHidden($0, extras[$0.id]) }
        let ready = visible.first { MacBureauReportsModel.isComplete($0) && MacBureauReportsModel.canOpen($0, extras[$0.id]) }
        store.selectedReport = ready ?? visible.first ?? store.reports.first
    }

    /// A filter that leaves the open report out moves the selection to the first report left.
    private func keepSelection(in ids: [String]) {
        guard !transcriptsMode else { return }
        if ids.isEmpty {
            if store.selectedReport != nil { store.selectedReport = nil }
            return
        }
        if let current = store.selectedReport?.id, ids.contains(current) { return }
        store.selectedReport = store.reports.first { $0.id == ids[0] }
    }

    private func openSelected() {
        guard let report = store.selectedReport else {
            store.closeMemo()
            return
        }
        if MacBureauReportsModel.canOpen(report, extras[report.id]) {
            Task { await store.openMemo(report, language: store.readerLanguage) }
        } else {
            store.closeMemo()
        }
    }

    private var extrasKey: String {
        store.reports.map { "\($0.id)|\($0.status ?? "")|\($0.updatedAt ?? "")" }.joined(separator: ",")
    }

    private func loadExtras() async {
        guard !store.reports.isEmpty else { return }
        if let fresh = await MacBureauReportsExtras.load() { extras = fresh }
    }

    private func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        await store.refreshReports()
        await loadExtras()
        refreshing = false
    }

    private func loadTranscripts() async {
        transcriptsLoading = true
        await store.loadTranscripts()
        transcriptsLoading = false
    }

    private func generate() {
        let company = companyFilter == "all" ? nil : store.companies.first { $0.id == companyFilter }
        store.requestNewReport(for: company)
    }

    // MARK: List tray

    private func listTray(_ model: MacBureauReportsModel) -> some View {
        VStack(spacing: 0) {
            VStack(spacing: 8) {
                titleRow(model)
                searchRow
                filterRow(model)
            }
            .padding(.top, 10)
            .padding(.horizontal, 12)
            .padding(.bottom, 8)

            if transcriptsMode {
                transcriptList
            } else if refreshing || (store.reports.isEmpty && store.loading && store.lastSyncDate == nil) {
                // Reloading, or the first load with nothing cached yet.
                listLoading
            } else if model.filtered.isEmpty {
                listEmpty(model)
            } else {
                rows(model)
            }
        }
        .frame(width: 352)
        .frame(maxHeight: .infinity, alignment: .top)
        .modifier(MacBureauReportsTray())
    }

    private func titleRow(_ model: MacBureauReportsModel) -> some View {
        HStack(spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(transcriptsMode ? "Transcripts" : "Research Reports")
                    .font(BSHType.bureauSans(15, weight: .semibold))
                    .tracking(-0.15)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .bureauLines(20, size: 15)
                    .layoutPriority(1)
                Text(transcriptsMode ? transcriptCountLabel : model.countLabel)
                    .font(BSHType.bureauSans(12).monospacedDigit())
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .fixedSize()
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if !transcriptsMode, model.runningCount > 0 {
                MacBureauReportsChip(
                    text: "\(model.runningCount) Running",
                    icon: "loader-circle",
                    spinning: true,
                    foreground: ink.reportsInfoInk,
                    background: ink.reportsInfoSoft
                )
            }

            // The Mac's transcripts sit beside the fold, the pair 4pt apart.
            HStack(spacing: 4) {
                MacBureauReportsIconButton(
                    icon: "audio-lines",
                    size: 24,
                    glyph: 14,
                    pressed: transcriptsMode,
                    help: transcriptsMode ? "Back to the reports" : "Transcripts: expert, founder and customer calls"
                ) {
                    withAnimation(.easeInOut(duration: 0.18)) { mode = transcriptsMode ? "files" : "transcripts" }
                }
                MacBureauReportsIconButton(
                    icon: "panel-left-close",
                    size: 24,
                    glyph: 14,
                    pressed: true,
                    help: "Hide the reports list"
                ) {
                    listCollapsed = true
                }
            }
            .padding(.trailing, -4)
        }
        .frame(height: 24)
    }

    private var searchRow: some View {
        HStack(spacing: 6) {
            if transcriptsMode {
                MacBureauReportsSearch(text: $transcriptQuery, placeholder: "Search transcripts…") {
                    Task { await store.loadTranscripts(query: transcriptQuery) }
                }
                MacBureauReportsIconButton(icon: "plus", size: 28, glyph: 16, help: "Add a transcript (paste, or upload .txt, .vtt, .srt, .docx or .pdf)") {
                    showAddTranscript = true
                }
                .disabled(!store.canEditSources)
                MacBureauReportsIconButton(icon: "refresh-cw", size: 28, glyph: 14, spinning: transcriptsLoading, help: "Refresh") {
                    Task { await loadTranscripts() }
                }
                .disabled(transcriptsLoading)
            } else {
                MacBureauReportsSearch(text: $query, placeholder: "Search reports or companies…")
                MacBureauReportsOrbButton(help: "Generate report (⌘N)", action: generate)
                MacBureauReportsIconButton(icon: "refresh-cw", size: 28, glyph: 14, spinning: refreshing, help: "Refresh") {
                    Task { await refresh() }
                }
                .disabled(refreshing)
            }
        }
        .frame(height: 28)
    }

    @ViewBuilder
    private func filterRow(_ model: MacBureauReportsModel) -> some View {
        // Company names run long, so the company filter gets the widest share.
        let inner: CGFloat = 352 - 24
        if transcriptsMode {
            let widths = MacBureauReportsModel.columns([1.35, 1.1], width: inner)
            HStack(spacing: 6) {
                MacBureauReportsSelect(options: transcriptCompanyOptions, selection: $transcriptCompany)
                    .frame(width: widths[0])
                MacBureauReportsSelect(options: transcriptKindOptions, selection: $transcriptKind)
                    .frame(width: widths[1])
            }
        } else if model.kindOptions.count > 1 {
            let widths = MacBureauReportsModel.columns([1.35, 1, 1.1], width: inner)
            HStack(spacing: 6) {
                MacBureauReportsSelect(options: model.companyOptions, selection: $companyFilter)
                    .frame(width: widths[0])
                MacBureauReportsSelect(options: [("all", "All types")] + model.kindOptions, selection: $kindFilter)
                    .frame(width: widths[1])
                MacBureauReportsSelect(options: MacBureauReportsModel.statusOptions, selection: $statusFilter)
                    .frame(width: widths[2])
            }
        } else {
            let widths = MacBureauReportsModel.columns([1.35, 1.1], width: inner)
            HStack(spacing: 6) {
                MacBureauReportsSelect(options: model.companyOptions, selection: $companyFilter)
                    .frame(width: widths[0])
                MacBureauReportsSelect(options: MacBureauReportsModel.statusOptions, selection: $statusFilter)
                    .frame(width: widths[1])
            }
        }
    }

    private var listLoading: some View {
        VStack(spacing: 0) {
            MacBureauReportsSpinner(size: 20)
                .foregroundStyle(ink.accent)
                .padding(.bottom, 8)
            Text("Loading preview…")
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .frame(height: 16)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func listEmpty(_ model: MacBureauReportsModel) -> some View {
        VStack(spacing: 0) {
            LucideIcon("file-text", size: 20)
                .foregroundStyle(ink.subtle)
                .frame(width: 44, height: 44)
                .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.05)))
                .padding(.bottom, 8)
            Text(model.emptyTitle)
                .font(BSHType.bureauSans(14, weight: .semibold))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .multilineTextAlignment(.center)
                .frame(minHeight: 20)
            Text("No generated reports match the current filters, or no reports have been generated yet.")
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .multilineTextAlignment(.center)
                .bureauLines(16, size: 12)
                .frame(maxWidth: 304)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)
            Button(action: generate) {
                HStack(spacing: 4.8) {
                    // Centered on the 18pt line, as the browser centers it (the text's line is 15).
                    AiOrbView(size: 14)
                        .offset(y: 0.5)
                    Text("Generate report")
                }
            }
            .buttonStyle(MacBureauPillStyle(kind: .filled))
            .controlSize(.small)
            .padding(.top, 12)
            if model.hiddenCount > 0 {
                MacBureauReportsLinkButton(title: "Show dismissed (\(model.hiddenCount))") { showDismissed = true }
                    .padding(.top, 8)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func rows(_ model: MacBureauReportsModel) -> some View {
        ScrollView {
            LazyVStack(spacing: 2) {
                ForEach(model.flatRows) { row in
                    MacBureauReportsRow(
                        report: row.report,
                        extras: extras[row.report.id],
                        company: model.workspaceCompany(for: row.report),
                        nested: row.nested,
                        olderCount: row.older,
                        expanded: expandedGroups.contains(row.report.id),
                        selected: store.selectedReport?.id == row.report.id,
                        select: { store.selectedReport = row.report },
                        toggleGroup: { toggleGroup(row.report.id) }
                    )
                }
                if model.hiddenCount > 0 {
                    MacBureauReportsLinkButton(
                        title: showDismissed ? "Hide dismissed" : "Show dismissed (\(model.hiddenCount))",
                        style: .pill
                    ) {
                        showDismissed.toggle()
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
            }
            .padding(.horizontal, 6)
            .padding(.bottom, 6)
        }
        .scrollIndicators(.automatic)
    }

    private func toggleGroup(_ id: String) {
        withAnimation(.easeInOut(duration: 0.18)) {
            if expandedGroups.contains(id) { expandedGroups.remove(id) } else { expandedGroups.insert(id) }
        }
    }

    // MARK: Folded list: a rail of logos

    private func rail(_ model: MacBureauReportsModel) -> some View {
        VStack(spacing: 4) {
            MacBureauReportsIconButton(icon: "panel-left-open", size: 28, glyph: 16, help: "Show the reports list") {
                listCollapsed = false
            }
            ScrollView(showsIndicators: false) {
                VStack(spacing: 6) {
                    ForEach(model.flatRows.map(\.report)) { report in
                        MacBureauReportsRailMark(
                            report: report,
                            extras: extras[report.id],
                            company: model.workspaceCompany(for: report),
                            selected: store.selectedReport?.id == report.id
                        ) {
                            mode = "files"
                            store.selectedReport = report
                        }
                    }
                }
                .padding(.top, 6)
                .padding(.bottom, 8)
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 8)
        .frame(width: 44)
        .frame(maxHeight: .infinity, alignment: .top)
        .modifier(MacBureauReportsTray())
    }

    // MARK: Viewer tray

    @ViewBuilder
    private func viewerTray(_ model: MacBureauReportsModel) -> some View {
        Group {
            if transcriptsMode {
                MacBureauReportsTranscriptViewer(transcriptId: $transcriptId)
            } else {
                MacBureauReportsViewer(
                    report: store.selectedReport.flatMap { selected in store.reports.first { $0.id == selected.id } ?? selected },
                    extras: store.selectedReport.flatMap { extras[$0.id] },
                    company: store.selectedReport.flatMap { model.workspaceCompany(for: $0) }
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .modifier(MacBureauReportsTray())
    }

    // MARK: Transcripts

    private var filteredTranscripts: [MacTranscript] {
        store.transcripts.filter { t in
            (transcriptCompany == "all" || t.companyId == transcriptCompany)
                && (transcriptKind == "all" || t.kind == transcriptKind)
        }
    }

    private var transcriptCountLabel: String {
        let shown = filteredTranscripts.count, total = store.transcripts.count
        let noun = total == 1 ? "transcript" : "transcripts"
        return shown == total ? "\(total) \(noun)" : "\(shown) of \(total) \(noun)"
    }

    private var transcriptCompanyOptions: [(String, String)] {
        var seen: [String: String] = [:]
        var order: [String] = []
        for t in store.transcripts {
            guard let id = t.companyId, !id.isEmpty, seen[id] == nil else { continue }
            seen[id] = t.companyName ?? store.companies.first { $0.id == id }?.name ?? id
            order.append(id)
        }
        return [("all", "All Companies")] + order.map { ($0, seen[$0] ?? $0) }
    }

    private var transcriptKindOptions: [(String, String)] {
        let known: [(String, String)] = [
            ("expert_call", "Expert call"),
            ("founder_call", "Founder call"),
            ("customer_call", "Customer call"),
            ("reference_call", "Reference call"),
        ]
        let present = Set(store.transcripts.map(\.kind))
        let extra = present.subtracting(known.map(\.0)).sorted().map { ($0, $0.replacingOccurrences(of: "_", with: " ").capitalized) }
        return [("all", "Any kind")] + known + extra
    }

    @ViewBuilder
    private var transcriptList: some View {
        let items = filteredTranscripts
        if transcriptsLoading && store.transcripts.isEmpty {
            listLoading
        } else if items.isEmpty {
            VStack(spacing: 0) {
                LucideIcon("audio-lines", size: 20)
                    .foregroundStyle(ink.subtle)
                    .frame(width: 44, height: 44)
                    .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.05)))
                    .padding(.bottom, 8)
                Text("No transcripts")
                    .font(BSHType.bureauSans(14, weight: .semibold))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .frame(height: 20)
                Text("Add expert, founder or customer calls. Every word becomes searchable in Firm Memory (⌘⇧F).")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .multilineTextAlignment(.center)
                    .bureauLines(16, size: 12)
                    .frame(maxWidth: 304)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
                Button {
                    showAddTranscript = true
                } label: {
                    HStack(spacing: 4.8) {
                        LucideIcon("plus", size: 14)
                        Text("Add transcript")
                    }
                }
                .buttonStyle(MacBureauPillStyle(kind: .filled))
                .controlSize(.small)
                .disabled(!store.canEditSources)
                .padding(.top, 12)
            }
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(items) { t in
                        MacBureauReportsTranscriptRow(
                            transcript: t,
                            company: t.companyId.flatMap { id in store.companies.first { $0.id == id } },
                            selected: transcriptId == t.id
                        ) {
                            transcriptId = t.id
                        }
                    }
                }
                .padding(.horizontal, 6)
                .padding(.bottom, 6)
            }
        }
    }
}

// MARK: - Page tokens the reports desk adds to the kit's

extension MacBureauPageInk {
    /// `--color-surface-muted` for the active desk.
    var reportsSurfaceMuted: Color { .bshFixed(reportsSurfaceMutedRGB) }

    private var reportsSurfaceMutedRGB: BSHRGB {
        let desk = BSHBureauDesk.active
        guard dark else { return desk == .onyx ? BSHRGB(226, 224, 218) : BSHRGB(233, 228, 216) }
        switch desk {
        case .onyx: return BSHRGB(11, 11, 11)
        case .green: return BSHRGB(11, 16, 14)
        case .maroon: return BSHRGB(26, 10, 14)
        case .navy: return BSHRGB(10, 14, 22)
        case .aubergine: return BSHRGB(17, 11, 17)
        case .tobacco: return BSHRGB(18, 14, 10)
        case .graphite: return BSHRGB(13, 15, 18)
        }
    }

    /// The viewer's body: `bg-surface-muted/30` over the tray.
    var reportsViewerBody: Color { .bshFixed(reportsViewerBodyRGB) }

    var reportsViewerBodyRGB: BSHRGB {
        let tones = BSHBureauDesk.active.tones.tray
        let tray = dark ? tones.dark : tones.light
        let muted = reportsSurfaceMutedRGB
        func mix(_ a: Double, _ b: Double) -> Double { (a * 0.7 + b * 0.3).rounded() }
        return BSHRGB(mix(tray.r, muted.r), mix(tray.g, muted.g), mix(tray.b, muted.b))
    }

    /// A tray's inner edge (`--shadow`): a hairline of ink by day, of white by night.
    var reportsTrayRing: Color { dark ? Color.white.opacity(0.03) : ink(0.035) }
    /// The shade along a tray's top edge, where it is pressed into the sheet.
    var reportsTrayShade: Color { dark ? Color.black.opacity(0.35) : shadow(0.04) }

    var reportsInfoSoft: Color { .bshFixed(dark ? BSHRGB(32, 36, 64) : BSHRGB(229, 232, 244)) }
    var reportsInfoInk: Color { .bshFixed(dark ? BSHRGB(184, 192, 255) : BSHRGB(52, 68, 150)) }
    var reportsNoticeSoft: Color { .bshFixed(dark ? BSHRGB(52, 45, 16) : BSHRGB(246, 236, 205)) }
    var reportsNoticeInk: Color { .bshFixed(dark ? BSHRGB(246, 220, 140) : BSHRGB(128, 94, 0)) }
    var reportsTealSoft: Color { .bshFixed(dark ? BSHRGB(16, 44, 46) : BSHRGB(220, 236, 234)) }
    var reportsTealInk: Color { .bshFixed(dark ? BSHRGB(140, 220, 226) : BSHRGB(16, 98, 106)) }
    var reportsWarningSoft: Color { .bshFixed(dark ? BSHRGB(55, 40, 16) : BSHRGB(246, 232, 208)) }
    /// A `<select>`'s double chevron (#808086, #9a9aa2 by night).
    var reportsChevron: Color { .bshFixed(dark ? BSHRGB(154, 154, 162) : BSHRGB(128, 128, 134)) }

    /// A chip's tone (`toneClasses`): its soft ground and its ink.
    func reportsTone(_ tone: MacBureauReportsTone) -> (foreground: Color, background: Color) {
        switch tone {
        case .success: return (successInk, successSoft)
        case .notice: return (reportsNoticeInk, reportsNoticeSoft)
        case .teal: return (reportsTealInk, reportsTealSoft)
        case .purple: return (purpleInk, purpleSoft)
        case .info: return (reportsInfoInk, reportsInfoSoft)
        case .warning: return (warningInk, reportsWarningSoft)
        case .danger: return (dangerInk, dangerSoft)
        case .accent: return (accentInk, accentSoft)
        case .neutral: return (secondary, ink(0.06))
        }
    }
}

enum MacBureauReportsTone {
    case success, notice, teal, purple, info, warning, danger, accent, neutral
}

// MARK: - Surfaces and controls

/// `.desk-card` under Bureau: a tray pressed into the sheet, a faint inner edge and a shade
/// along its top instead of a drop shadow (14pt corners).
struct MacBureauReportsTray: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: 14, style: .circular)
        content
            .background(
                shape.fill(ink.tray.shadow(.inner(color: ink.reportsTrayShade, radius: ink.dark ? 3 : 2, x: 0, y: 1)))
            )
            .overlay(shape.strokeBorder(ink.reportsTrayRing, lineWidth: 1).allowsHitTesting(false))
            .clipShape(shape)
    }
}

/// `.icon-btn`: a round button, its glyph in the muted ink; pointed at, a wash of ink behind
/// it; pressed (or standing open), a darker one and the glyph in ink.
struct MacBureauReportsIconButton: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    let icon: String
    var size: CGFloat = 28
    var glyph: CGFloat = 14
    var pressed = false
    var spinning = false
    let help: String
    let action: () -> Void
    @State private var hovered = false
    @State private var held = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            Group {
                if spinning {
                    MacBureauReportsSpinner(icon: icon, size: glyph)
                } else {
                    LucideIcon(icon, size: glyph)
                }
            }
            .foregroundStyle(pressed || (hovered && isEnabled) ? ink.ink : ink.muted)
            .frame(width: size, height: size)
            .background(Circle().fill(fill(ink)))
            .contentShape(Circle())
        }
        .buttonStyle(MacBureauPressReporter(pressed: $held))
        .onHover { hovered = $0 }
        .opacity(isEnabled ? 1 : 0.4)
        .help(help)
        .accessibilityLabel(help)
    }

    private func fill(_ ink: MacBureauPageInk) -> Color {
        guard isEnabled else { return pressed ? ink.ink(0.08) : .clear }
        if held { return ink.ink(0.12) }
        if hovered { return ink.ink(0.07) }
        return pressed ? ink.ink(0.08) : .clear
    }
}

/// The list's Generate button: Warren's orb in a round icon button.
private struct MacBureauReportsOrbButton: View {
    @Environment(\.colorScheme) private var colorScheme
    let help: String
    let action: () -> Void
    @State private var hovered = false
    @State private var held = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            AiOrbView(size: 16)
                .frame(width: 28, height: 28)
                .background(Circle().fill(held ? ink.ink(0.12) : hovered ? ink.ink(0.07) : .clear))
                .contentShape(Circle())
        }
        .buttonStyle(MacBureauPressReporter(pressed: $held))
        .onHover { hovered = $0 }
        .help(help)
        .accessibilityLabel("Generate report")
    }
}

/// A lucide glyph turning, as the website's `animate-spin`.
struct MacBureauReportsSpinner: View {
    var icon = "loader-circle"
    var size: CGFloat
    @State private var turning = false

    var body: some View {
        LucideIcon(icon, size: size)
            .rotationEffect(.degrees(turning ? 360 : 0))
            .onAppear {
                withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) { turning = true }
            }
    }
}

/// `.news-search-field`: a pill of fresh paper with the magnifier inside its left end; focused,
/// a brass edge and its glow.
private struct MacBureauReportsSearch: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var text: String
    let placeholder: String
    var onSubmit: () -> Void = {}
    @FocusState private var focused: Bool

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let capsule = Capsule()
        ZStack(alignment: .leading) {
            // The browser paints the field a point low in its row (it rounds its half-point
            // top down), with the magnifier still centered on the row.
            capsule
                .fill(ink.raised)
                .overlay(capsule.strokeBorder(focused ? ink.accent : ink.ink(0.14), lineWidth: 1))
                .overlay(
                    capsule
                        .inset(by: -2)
                        .stroke(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                        .padding(-0.5)
                )
                .frame(height: 26)
                .offset(y: 1)
                .allowsHitTesting(false)
            LucideIcon("search", size: 14)
                .foregroundStyle(ink.muted)
                .padding(.leading, 12)
                .allowsHitTesting(false)
            ZStack(alignment: .leading) {
                // The placeholder is drawn here: the Mac sets a field's prompt in its own gray.
                if text.isEmpty {
                    Text(placeholder)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .allowsHitTesting(false)
                }
                TextField("", text: $text)
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.ink)
                    .focused($focused)
                    .onSubmit(onSubmit)
                    .onExitCommand { text = "" }
            }
            .padding(.leading, 36)
            .padding(.trailing, 12)
            .frame(height: 26)
            .offset(y: 0.5)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 28)
        .contentShape(capsule)
    }
}

/// `select.field.field-sm.reports-filter`: fresh paper ruled in ink, the choice in 12pt ink
/// and the double chevron at its right end. It opens the Mac's menu, as a select does.
struct MacBureauReportsSelect: View {
    @Environment(\.colorScheme) private var colorScheme
    let options: [(String, String)]
    @Binding var selection: String
    @State private var hovered = false

    private var title: String {
        options.first { $0.0 == selection }?.1 ?? options.first?.1 ?? ""
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let shape = RoundedRectangle(cornerRadius: 10, style: .circular)
        Menu {
            Picker("", selection: $selection) {
                ForEach(options, id: \.0) { option in
                    Text(option.1).tag(option.0)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            Text(title)
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.ink)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauLines(16, size: 12)
                .padding(.vertical, 6)
                .padding(.leading, 10)
                .padding(.trailing, 25.6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: 28)
                .background(shape.fill(ink.raised))
                .overlay(shape.strokeBorder(ink.ink(hovered ? 0.28 : 0.14), lineWidth: 1))
                .overlay(alignment: .topLeading) {
                    // `background-position: right 0.55rem center`, which the browser rounds to
                    // whole points on the page.
                    GeometryReader { geo in
                        let frame = geo.frame(in: .global)
                        let x = (frame.minX + frame.width - 8.8 - 9).rounded() - frame.minX
                        let y = (frame.minY + (frame.height - 13) / 2).rounded() - frame.minY
                        MacBureauReportsChevron()
                            .stroke(ink.reportsChevron, style: StrokeStyle(lineWidth: 1.6 * 0.92, lineCap: .round, lineJoin: .round))
                            .frame(width: 9, height: 13)
                            .offset(x: x, y: y)
                    }
                    .allowsHitTesting(false)
                }
                .contentShape(shape)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .onHover { hovered = $0 }
        .help(title)
    }
}

/// The website's pop-up chevron (a 10 by 14 drawing, set at 9 by 13).
struct MacBureauReportsChevron: Shape {
    func path(in rect: CGRect) -> Path {
        let sx = rect.width / 10, sy = rect.height / 14
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * sx, y: rect.minY + y * sy) }
        var path = Path()
        path.move(to: p(2, 5)); path.addLine(to: p(5, 2)); path.addLine(to: p(8, 5))
        path.move(to: p(2, 9)); path.addLine(to: p(5, 12)); path.addLine(to: p(8, 9))
        return path
    }
}

/// `.chip`: a pill of 11pt semibold text on a soft ground, an optional 12pt glyph before it.
struct MacBureauReportsChip: View {
    let text: String
    var icon: String? = nil
    var spinning = false
    let foreground: Color
    let background: Color

    var body: some View {
        HStack(spacing: 4) {
            if let icon {
                if spinning {
                    MacBureauReportsSpinner(icon: icon, size: 12)
                } else {
                    LucideIcon(icon, size: 12)
                }
            }
            Text(text)
                .font(BSHType.bureauSans(11, weight: .semibold))
                .lineLimit(1)
                .fixedSize()
        }
        .foregroundStyle(foreground)
        .padding(.horizontal, 8)
        .frame(height: 18)
        .background(Capsule().fill(background))
    }
}

/// The small squared tags under a row (`rounded-[5px] px-1.5 py-px text-caption2 font-semibold`).
struct MacBureauReportsTag: View {
    let text: String
    var icon: String? = nil
    var weight: Font.Weight = .semibold
    /// `tabular`: figures of even width (the checks' counts).
    var tabular = false
    let foreground: Color
    let background: Color

    var body: some View {
        HStack(spacing: 2) {
            if let icon { LucideIcon(icon, size: 10) }
            Text(text)
                .font(tabular ? BSHType.bureauSans(10, weight: weight).monospacedDigit() : BSHType.bureauSans(10, weight: weight))
                .tracking(0.12)
                .lineLimit(1)
                .fixedSize()
        }
        .foregroundStyle(foreground)
        .padding(.horizontal, 6)
        .frame(height: 15)
        .background(RoundedRectangle(cornerRadius: 5, style: .circular).fill(background))
    }
}

/// A brass text button (`text-caption1 font-medium text-accent-ink`): bare and underlined
/// when pointed at, or in a pill washed in brass (`px-1.5 py-0.5`, `px-2.5 py-1`).
struct MacBureauReportsLinkButton: View {
    enum Style { case text, compact, pill }

    @Environment(\.colorScheme) private var colorScheme
    let title: String
    var icon: String? = nil
    var style: Style = .text
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let pad: CGFloat = style == .pill ? 10 : style == .compact ? 6 : 0
        let height: CGFloat = style == .pill ? 22 : style == .compact ? 18 : 14
        Button(action: action) {
            HStack(spacing: 2) {
                if let icon { LucideIcon(icon, size: 12) }
                Text(title)
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .tracking(0.066)
                    .underline(hovered && style == .text)
                    .fixedSize()
            }
            .foregroundStyle(ink.accentInk)
            .padding(.horizontal, pad)
            .frame(height: height)
            .background(Capsule().fill(hovered && style != .text ? ink.accent.opacity(0.08) : .clear))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - A company's mark

/// The website's Monogram (tinted): the company's logo on white, else its initials on a tint
/// chosen by a hash of its id, in a squircle of 0.28 of its size.
struct MacBureauReportsMark: View {
    let name: String
    var ticker: String?
    var companyId: String?
    var logoUrl: String?
    var website: String?
    let size: CGFloat

    init(company: MacCompany, size: CGFloat) {
        self.name = company.name ?? company.id
        self.ticker = company.ticker
        self.companyId = company.id
        self.logoUrl = company.logoUrl
        self.website = company.website
        self.size = size
    }

    init(name: String, ticker: String? = nil, companyId: String? = nil, logoUrl: String? = nil, website: String? = nil, size: CGFloat) {
        self.name = name
        self.ticker = ticker
        self.companyId = companyId
        self.logoUrl = logoUrl
        self.website = website
        self.size = size
    }

    var body: some View {
        MacBureauReportsLogo(
            primary: MacCompanyLogoResolver.resolvePrimaryLogoUrl(logoUrl: logoUrl, website: website, ticker: ticker, companyId: companyId, name: name),
            fallback: MacCompanyLogoResolver.resolveFallbackLogoUrl(website: website, ticker: ticker, companyId: companyId, name: name),
            name: name,
            tintKey: companyId ?? name,
            size: size
        )
        // A new company is a new picture: the one loaded for the last must not linger.
        .id("\(companyId ?? "")|\(logoUrl ?? "")|\(name)")
    }
}

private struct MacBureauReportsLogo: View {
    @Environment(\.colorScheme) private var colorScheme
    let primary: URL?
    let fallback: URL?
    let name: String
    let tintKey: String
    let size: CGFloat
    @State private var image: NSImage?

    init(primary: URL?, fallback: URL?, name: String, tintKey: String, size: CGFloat) {
        self.primary = primary
        self.fallback = fallback
        self.name = name
        self.tintKey = tintKey
        self.size = size
        if let p = primary, let cached = MacImageCache.shared.image(for: p) {
            _image = State(initialValue: cached)
        } else if let f = fallback, let cached = MacImageCache.shared.image(for: f) {
            _image = State(initialValue: cached)
        }
    }

    private static let tints: [BSHRGB] = [
        BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
        BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
    ]

    /// Monogram.vue's hash: (hash * 31 + code) >>> 0 over the id, mod 10.
    private var tint: BSHRGB {
        var hash: UInt32 = 0
        for unit in tintKey.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        return Self.tints[Int(hash % 10)]
    }

    private var initials: String {
        let words = name.split(whereSeparator: { $0 == " " || $0 == "-" }).filter { !$0.isEmpty }
        let letters = words.prefix(2).compactMap { $0.first.map(String.init) }.joined()
        return letters.isEmpty ? "?" : letters.uppercased()
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: size * 0.28, style: .circular)
        Group {
            if let image {
                // `object-fit: contain` inside 8% padding, the picture trimmed to the content
                // box's curve (the tile's radius less the padding), as a replaced element is.
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size * 0.84, height: size * 0.84)
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.2, style: .circular))
                    .frame(width: size, height: size)
                    .background(Color.white)
                    .clipShape(shape)
                    .overlay(shape.strokeBorder(colorScheme == .dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5))
                    .shadow(color: .black.opacity(colorScheme == .dark ? 0.35 : 0.06), radius: colorScheme == .dark ? 1.5 : 1, y: 1)
            } else {
                Text(initials)
                    .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
                    .tracking(size * 0.0037)
                    .foregroundStyle(.white)
                    .frame(width: size, height: size)
                    .background(
                        shape.fill(LinearGradient(
                            colors: [.bshFixed(tint), .bshFixed(tint, opacity: 0.72)],
                            startPoint: UnitPoint(x: 0.2, y: 0), endPoint: UnitPoint(x: 0.8, y: 1)
                        ))
                    )
                    .overlay(shape.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
            }
        }
        .frame(width: size, height: size)
        .task(id: primary?.absoluteString ?? fallback?.absoluteString ?? name) { await fetch() }
    }

    private func fetch() async {
        if image != nil { return }
        for url in [primary, fallback].compactMap({ $0 }) where !MacImageCache.shared.isFailed(url) {
            var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            if let result = try? await URLSession.shared.data(for: request),
               (result.1 as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true,
               let loaded = NSImage(data: result.0), loaded.size.width > 1 {
                MacImageCache.shared.setImage(loaded, for: url)
                image = loaded
                return
            }
            MacImageCache.shared.markFailed(url)
        }
    }
}

/// A one-line label as a CSS `truncate` flex item lays it: its own width while it fits, and all
/// the room it is offered once it has to truncate (so what follows sits at the end of that room).
struct MacBureauReportsTruncating: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard let label = subviews.first else { return .zero }
        let ideal = label.sizeThatFits(.unspecified)
        guard let width = proposal.width, width < ideal.width else { return ideal }
        return CGSize(width: max(0, width), height: label.sizeThatFits(ProposedViewSize(width: max(0, width), height: proposal.height)).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, proposal: ProposedViewSize(width: bounds.width, height: bounds.height))
    }

    func explicitAlignment(of guide: VerticalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? {
        guard let label = subviews.first else { return nil }
        return bounds.minY + label.dimensions(in: ProposedViewSize(width: bounds.width, height: bounds.height))[guide]
    }
}

/// A centered block lands on a half point as often as not; the browser paints it on the whole
/// point below. This moves it there, measuring where it lies in the window.
struct MacBureauReportsWholePoint: ViewModifier {
    @State private var shift: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .background(GeometryReader { geo in
                let y = geo.frame(in: .global).minY
                Color.clear
                    .onAppear { settle(y) }
                    .onChange(of: y) { _, value in settle(value) }
            })
            .offset(y: shift)
    }

    private func settle(_ measured: CGFloat) {
        let base = measured - shift
        let target = base.rounded(.toNearestOrAwayFromZero) - base
        if abs(target - shift) > 0.01 { shift = target }
    }
}

extension View {
    func reportsWholePoint() -> some View { modifier(MacBureauReportsWholePoint()) }
}

/// A line that keeps to the width it is offered even when its content is wider: the content
/// runs on past the right edge (and the tray clips it), as a flex row with a `shrink-0` end
/// overflows on the website, instead of widening everything above it.
struct MacBureauReportsOverflow: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard let line = subviews.first else { return .zero }
        let size = line.sizeThatFits(proposal)
        guard let width = proposal.width else { return size }
        return CGSize(width: width, height: size.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let line = subviews.first else { return }
        let size = line.sizeThatFits(ProposedViewSize(width: bounds.width, height: bounds.height))
        line.place(at: bounds.origin, proposal: ProposedViewSize(width: max(bounds.width, size.width), height: bounds.height))
    }
}
