//
//  MacBureauReportCustomizer.swift
//  BSHResearchMac
//
//  The Generate report dialog under Bureau, drawn as the website draws it
//  (ReportCustomizerModal.vue with style.css and bureau.css): a light scrim over the whole
//  window and the dialog's sheet on it — the company and what the run will be, three tabs
//  (Blueprint & Framing, Engine & Quality, Evidence Sources), the pre-flight notes and the
//  footer with the run's summary, Cancel and Generate. Its state and requests are in
//  MacBureauReportCustomizerModel.swift; the pieces it is drawn with (and how they land on
//  the pixels Chrome paints them on) in MacBureauReportCustomizerParts.swift.
//

import AppKit
import SwiftUI

// MARK: - Presenting it

extension View {
    /// Under Bureau, the Generate report dialog as the website presents it: over the whole
    /// window (masthead and rail included) on a light scrim, not as a system sheet. Opens on
    /// `store.showNewReportSheet`; put it on the window's root, beside the tour's overlay.
    func bureauReportCustomizerOverlay() -> some View {
        modifier(MacBureauReportCustomizerHost())
    }
}

extension Binding where Value == Bool {
    /// A presentation flag for the system sheet that is never raised under Bureau, where the
    /// dialog is drawn over the window instead (`bureauReportCustomizerOverlay()`).
    var systemSheetUnlessBureau: Binding<Bool> {
        Binding(
            get: { BSHDesign.active != .bureau && wrappedValue },
            set: { wrappedValue = $0 }
        )
    }
}

private struct MacBureauReportCustomizerHost: ViewModifier {
    @EnvironmentObject private var store: MacAppStore
    @StateObject private var model = MacBureauCustomizerModel()
    /// Raised once the dialog's state is reset for this opening, so it never shows the last one.
    @State private var presented = false

    func body(content: Content) -> some View {
        content
            .overlay {
                ZStack {
                    if BSHDesign.active == .bureau && presented && store.showNewReportSheet {
                        MacBureauReportCustomizerLayer(model: model) { store.showNewReportSheet = false }
                            .transition(.opacity)
                    }
                }
                .animation(.easeOut(duration: 0.2), value: presented && store.showNewReportSheet)
            }
            .onChange(of: store.showNewReportSheet, initial: true) { _, open in
                guard BSHDesign.active == .bureau else { return }
                if open {
                    model.companies = store.companies
                    model.open(companyId: initialCompanyId())
                }
                presented = open
            }
            .onChange(of: store.companies) { _, companies in model.companies = companies }
    }

    /// The company the dialog opens on, decided as the website decides it: the one the
    /// opener named; else, on a company's page, that company; anywhere else none, and the
    /// dialog asks (a silent default is how a run once started on another desk's company).
    private func initialCompanyId() -> String? {
        let fallback = store.selectedCompany ?? store.companies.first
        if let named = store.newReportCompany, named.id != fallback?.id { return named.id }
        if let held = store.heldCompanyId, store.companies.contains(where: { $0.id == held }) { return held }
        return nil
    }
}

/// The scrim and the dialog on it, placed as the website places its sheet in the window.
private struct MacBureauReportCustomizerLayer: View {
    @ObservedObject var model: MacBureauCustomizerModel
    let close: () -> Void
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        GeometryReader { proxy in
            let placement = Self.placement(in: proxy.size)
            ZStack(alignment: .topLeading) {
                // A dialog dims the desk lightly; it doesn't frost it.
                Rectangle()
                    .fill(MacBureauPageInk(scheme: colorScheme).customizerScrim)
                    .contentShape(Rectangle())
                    .onTapGesture { close() }
                MacBureauReportCustomizer(model: model, windowWidth: proxy.size.width, close: close) { report, companyId in
                    finish(report: report, companyId: companyId)
                }
                .frame(width: placement.frame.width, height: placement.layoutHeight)
                .environment(\.bureauCustomizerPhase, placement.phase)
                .offset(x: placement.frame.minX, y: placement.frame.minY)
            }
        }
        .ignoresSafeArea()
    }

    /// Where the website puts its sheet: `fixed inset-0 flex items-center justify-center
    /// p-3 sm:p-5 md:p-8` around a `w-[96vw] max-w-[1040px] h-[92vh]` sheet, the container
    /// being the Bureau desk's height (100vh less the masthead and the gutter) from 768pt up,
    /// so the sheet sits just under the window's top edge. Chrome lays it out on 64ths of a
    /// point and paints it on whole points; `phase` is the difference, which every box and
    /// line inside is painted with (`customizerSnap`).
    static func placement(in size: CGSize) -> (frame: CGRect, layoutHeight: CGFloat, phase: CGSize) {
        let padding: CGFloat = size.width >= 768 ? 32 : (size.width >= 640 ? 20 : 12)
        let layoutUnit = { (value: CGFloat) in (value * 64).rounded() / 64 }
        let width = layoutUnit(min(size.width * 0.96, 1040))
        let height = (size.height * 0.92 * 64).rounded(.down) / 64
        let container = size.width >= 768 ? size.height - MacBureau.masthead - MacBureau.gutter : size.height
        let x = layoutUnit(padding + (size.width - 2 * padding - width) / 2)
        let y = layoutUnit(padding + (container - 2 * padding - height) / 2)
        let left = x.rounded(), top = y.rounded()
        let frame = CGRect(x: left, y: top, width: (x + width).rounded() - left, height: (y + height).rounded() - top)
        // Laid out at Chrome's height, so what hangs from the bottom (the footer) sits where
        // Chrome lays it; the sheet's face is painted on whole points.
        return (frame, height, CGSize(width: x - left, height: y - top))
    }

    /// What the website does when a run starts: close, reload, and open the company's page
    /// on the new run.
    private func finish(report: MacReport, companyId: String) {
        store.handleCreatedReport(report)
        if let company = store.companies.first(where: { $0.id == companyId }) {
            store.openCompanyPage(company)
        }
        close()
    }
}

/// The same dialog when a view presents it as a system sheet (MacReportCustomizerSheet under
/// Bureau): the website's size, on the company it was opened for.
struct MacBureauReportCustomizerSheet: View {
    let company: MacCompany
    var onGenerate: ((MacReport) -> Void)?
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model = MacBureauCustomizerModel()

    var body: some View {
        MacBureauReportCustomizer(model: model, close: { dismiss() }) { report, _ in
            onGenerate?(report)
            dismiss()
        }
        .frame(width: 1040, height: 754)
        .onAppear {
            model.companies = store.companies
            model.open(companyId: company.id)
        }
        .onChange(of: store.companies) { _, companies in model.companies = companies }
    }
}

// MARK: - The dialog

/// The website's `.sheet-panel`: 16pt corners ruled in the page's line, the sheet's color,
/// its header, tabs, the scrolling choices, the pre-flight and the footer.
struct MacBureauReportCustomizer: View {
    typealias Catalog = MacBureauCustomizer
    typealias Copy = MacBureauCustomizer.Copy
    typealias Kind = MacBureauCustomizerType

    @ObservedObject var model: MacBureauCustomizerModel
    /// The window's width: the website's grids follow the viewport's breakpoints.
    var windowWidth: CGFloat = 1280
    let close: () -> Void
    let created: (MacReport, String) -> Void

    @Environment(\.colorScheme) private var colorScheme
    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var sm: Bool { windowWidth >= 640 }
    private var md: Bool { windowWidth >= 768 }
    private var lg: Bool { windowWidth >= 1024 }

    var body: some View {
        VStack(spacing: 0) {
            header
                .zIndex(2)
            rule
            tabBar
            rule
            ScrollView(.vertical) {
                tabContent
                    .padding(md ? 24 : 20)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .modifier(MacBureauCustomizerNoScrollEdge())
            .frame(maxHeight: .infinity)
            if let error = model.error {
                errorBanner(error)
            }
            let rows = model.preflightRows
            if !rows.isEmpty {
                rule
                preflight(rows)
            }
            rule
            footer
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(ink.sheet)
        .padding(1)
        .mask(MacBureauCustomizerSnapped { RoundedRectangle(cornerRadius: 16, style: .circular) })
        .overlay(MacBureauCustomizerSnapped { RoundedRectangle(cornerRadius: 16, style: .circular).strokeBorder(ink.rule, lineWidth: 1) })
        .background(MacBureauCustomizerSnapped { sheetEdge })
        .coordinateSpace(name: MacBureauCustomizerSpace.panel)
        .environment(\.font, BSHType.bureauSans(16))
        .task(id: "\(model.companyId)|\(model.effectiveEngine)") { await model.loadReadiness() }
        .task(id: model.companyId) { await model.loadEvidenceIfNeeded() }
        .onExitCommand { close() }
        #if DEBUG
        // QA: `-bshCustomizerRequestLog <file>` appends the request Generate would send each
        // time the choices change, so a check can compare it with the website's without
        // anything being sent.
        .onChange(of: model.pendingRequest, initial: true) { _, request in
            guard let path = UserDefaults.standard.string(forKey: "bshCustomizerRequestLog"), let request else { return }
            let line = Data((request + "\n").utf8)
            if let handle = FileHandle(forWritingAtPath: path) {
                handle.seekToEndOfFile()
                handle.write(line)
                handle.closeFile()
            } else {
                FileManager.default.createFile(atPath: path, contents: line)
            }
        }
        #endif
    }

    /// The sheet's border (`border-subtle`), its ring (`--shadow-sheet`'s first line) and the
    /// shadows under it.
    private var sheetEdge: some View {
        let dark = ink.dark
        return ZStack {
            // 0 26px 60px -26px (by night -22px): a shadow smaller than the sheet, dropped far.
            GeometryReader { geo in
                let spread: CGFloat = dark ? 22 : 26
                RoundedRectangle(cornerRadius: max(0, 16 - spread), style: .circular)
                    .fill(dark ? Color.black.opacity(0.8) : ink.shadow(0.5))
                    .frame(width: max(0, geo.size.width - 2 * spread), height: max(0, geo.size.height - 2 * spread))
                    .offset(x: spread, y: spread + 26)
                    .blur(radius: 30)
                if !dark {
                    // 0 6px 16px -8px
                    RoundedRectangle(cornerRadius: 8, style: .circular)
                        .fill(ink.shadow(0.18))
                        .frame(width: max(0, geo.size.width - 16), height: max(0, geo.size.height - 16))
                        .offset(x: 8, y: 8 + 6)
                        .blur(radius: 8)
                }
            }
            RoundedRectangle(cornerRadius: 17, style: .circular)
                .fill(dark ? Color.white.opacity(0.08) : ink.ink(0.08))
                .padding(-1)
            RoundedRectangle(cornerRadius: 16, style: .circular)
                .fill(ink.sheet)
        }
        .compositingGroup()
        .allowsHitTesting(false)
    }

    /// A 1pt rule between the dialog's bands (`border-t border-subtle`), on a whole point.
    private var rule: some View {
        Color.clear.frame(height: 1)
            .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.rule) })
    }

    // MARK: Header

    private var header: some View {
        let company = model.company
        let identity = model.identityLine(for: company)
        return HStack(alignment: .center, spacing: 0) {
            HStack(alignment: .center, spacing: 14) {
                if let company {
                    MacBureauCustomizerMonogram(company: company, size: 38)
                } else {
                    LucideIcon("building-2", size: 20)
                        .foregroundStyle(ink.accent)
                        .customizerSnap(horizontal: true)
                        .frame(width: 38, height: 38)
                        .background(MacBureauCustomizerSnapped { RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.accent.opacity(0.1)) })
                }
                VStack(alignment: .leading, spacing: 0) {
                    HStack(alignment: .center, spacing: 8) {
                        MacBureauCustomizerCompanyButton(title: company?.name ?? Copy.selectCompany) {
                            model.pickerOpen.toggle()
                        }
                        .overlay(alignment: .topLeading) {
                            if model.pickerOpen {
                                MacBureauCustomizerCompanyPicker(model: model)
                                    .offset(y: 32)
                            }
                        }
                        if let ticker = company?.ticker, !ticker.isEmpty {
                            let label = ticker.uppercased()
                            Text(label)
                                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                                .foregroundStyle(ink.secondary)
                                .lineLimit(1)
                                .bureauLines(16, size: 12)
                                .customizerSnap()
                                .customizerAdvance(label, font: NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold) as CTFont)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 3)
                                .background(MacBureauCustomizerSnapped { MacBureauCustomizerBoxFace(radius: 6, fill: ink.customizerSurfaceMuted, border: ink.rule) })
                        }
                        if sm, let sector = [company?.sector, company?.industry].compactMap({ $0 }).first(where: { !$0.isEmpty }) {
                            Text(sector)
                                .font(BSHType.bureauSans(12))
                                .foregroundStyle(ink.muted)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .bureauLines(16, size: 12)
                                .customizerSnap()
                                // `max-w-[140px]`, padding and rule included.
                                .customizerAdvance(sector, font: Kind.sans(12), maxWidth: 122)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 3)
                                .background(MacBureauCustomizerSnapped { MacBureauCustomizerBoxFace(radius: 6, fill: ink.customizerSurfaceMuted, border: ink.rule) })
                        }
                    }
                    .frame(height: 24)
                    .zIndex(1)
                    if !identity.isEmpty {
                        line(identity, size: 12, lineHeight: 16, color: ink.secondary)
                            .padding(.top, 2)
                    }
                    line(model.tagline, size: 12, lineHeight: 16, color: ink.muted)
                        .padding(.top, 2)
                }
            }
            Spacer(minLength: 12)
            MacBureauCustomizerCloseButton(action: close)
        }
        .padding(.horizontal, 20)
        .frame(height: 14 + (company == nil || identity.isEmpty ? 42 : 60) + 14)
        .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.tray) })
    }

    // MARK: Tabs

    private var tabBar: some View {
        HStack(spacing: 4) {
            ForEach(Catalog.Tab.allCases) { tab in
                MacBureauCustomizerTabButton(tab: tab, chosen: model.tab == tab) { model.tab = tab }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .frame(height: 44)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.tray.opacity(0.8)) })
    }

    @ViewBuilder
    private var tabContent: some View {
        switch model.tab {
        case .blueprint: blueprintTab
        case .engine: engineTab
        case .evidence: evidenceTab
        }
    }

    // MARK: Blueprint & Framing

    private var blueprintTab: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 12) {
                sectionHead(Copy.archetypeTitle, trailing: Copy.archetypeDesc)
                grid(Catalog.archetypes, columns: lg ? 3 : (sm ? 2 : 1), spacing: 12) { archetype in
                    archetypeCard(archetype)
                }
            }
            if md {
                HStack(alignment: .top, spacing: 24) {
                    audienceColumn
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                    choicesColumn
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                }
            } else {
                VStack(alignment: .leading, spacing: 24) {
                    audienceColumn
                    choicesColumn
                }
            }
        }
    }

    private func archetypeCard(_ archetype: Catalog.Archetype) -> some View {
        let chosen = archetype.available && model.archetype.id == archetype.id
        return MacBureauCustomizerCard(chosen: chosen, enabled: archetype.available, dimmed: 0.4, padding: 14) {
            model.selectArchetype(archetype)
        } content: {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauCustomizerRow(spacing: 8) {
                    line(archetype.title, size: 14, weight: .semibold, lineHeight: 20, color: ink.ink, wraps: true)
                    MacBureauCustomizerBadge(text: archetype.available ? archetype.badge : Copy.notAvailable, filled: chosen, lineHeight: 20)
                }
                .padding(.bottom, 4)
                line(archetype.desc, size: 12, lineHeight: 16, color: ink.muted, lines: 2)
                    .padding(.top, 2)
            }
        }
        .help(archetype.available ? "" : Copy.archetypeUnavailable)
    }

    private var audienceColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauCustomizerKicker(Copy.audienceTitle)
                .opacity(model.audienceLocked ? 0.5 : 1)
                .padding(.bottom, model.audienceLocked ? 6 : 10)
            if model.audienceLocked {
                line(model.audienceLockReason, size: 11, lineHeight: 16.5, color: ink.muted, wraps: true, oblique: true)
                    .padding(.bottom, 10)
            }
            VStack(spacing: 8) {
                ForEach(Catalog.audiences) { audience in
                    audienceRow(audience)
                }
            }
        }
    }

    private func audienceRow(_ audience: Catalog.Option) -> some View {
        let locked = model.audienceLocked
        let chosen = !locked && model.audienceId == audience.id
        return MacBureauCustomizerCard(chosen: chosen, enabled: !locked, dimmed: 0.4, padding: 12, fillsHeight: false) {
            if !locked { model.audienceId = audience.id }
        } content: {
            HStack(alignment: .top, spacing: 12) {
                MacBureauCustomizerRadio(on: chosen)
                    .padding(.top, 2)
                VStack(alignment: .leading, spacing: 0) {
                    line(audience.title, size: 14, weight: .medium, lineHeight: 20, color: ink.ink, wraps: true)
                    line(audience.desc, size: 12, lineHeight: 16, color: ink.muted, wraps: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var choicesColumn: some View {
        VStack(alignment: .leading, spacing: 20) {
            if model.templateApplies {
                templateChoice
            }
            scopeChoice
            languageChoice
        }
    }

    private var templateChoice: some View {
        let studio = model.studioSelected
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauCustomizerKicker(Copy.templateTitle)
                .opacity(studio ? 0.5 : 1)
                .padding(.bottom, 10)
            grid(Catalog.templates, columns: sm ? 2 : 1, spacing: 8) { option in
                smallCard(option, chosen: model.shownTemplate == option.id, enabled: !studio, dimmed: 0.5) {
                    model.chooseTemplate(option.id)
                }
            }
            line(
                studio ? Copy.templateStudioHint(model.templateName(model.workspaceTemplate)) : Copy.templateDefaultHint(model.templateName(model.workspaceTemplate)),
                size: 11, lineHeight: 16.5, color: ink.muted, wraps: true
            )
            .padding(.top, 6)
        }
    }

    private var scopeChoice: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauCustomizerKicker(Copy.scopeTitle)
                .opacity(model.lengthEnabled ? 1 : 0.5)
                .padding(.bottom, 10)
            if model.lengthEnabled {
                grid(Catalog.lengths, columns: 2, spacing: 8) { option in
                    smallCard(option, chosen: model.reportMode == option.id, enabled: true, dimmed: 1) {
                        model.reportMode = option.id
                    }
                }
            } else {
                let title = model.isBuffett
                    ? "Buffett-Method Memo"
                    : (model.shownTemplate == "ic_v2" ? Catalog.lengths[1].title : Copy.lengthStandard)
                let desc: String? = model.isBuffett
                    ? nil
                    : (model.shownTemplate == "ic_v2" ? Catalog.lengths[1].desc : Copy.lengthStandardDesc)
                MacBureauCustomizerCard(chosen: false, enabled: false, dimmed: 0.6, padding: 12, fillsHeight: false) {} content: {
                    VStack(alignment: .leading, spacing: 0) {
                        line(title, size: 12, weight: .semibold, lineHeight: 16, color: ink.ink, wraps: true)
                        if let desc {
                            line(desc, size: 11, lineHeight: 16.5, color: ink.muted, wraps: true)
                                .padding(.top, 4)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                line(model.lengthLockReason, size: 11, lineHeight: 16.5, color: ink.muted, wraps: true, oblique: true)
                    .padding(.top, 6)
            }
        }
    }

    private var languageChoice: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauCustomizerKicker(Copy.languageTitle)
                .padding(.bottom, 8)
            grid(Catalog.languages, columns: 3, spacing: 8) { option in
                MacBureauCustomizerCard(chosen: !option.disabled && model.language == option.id, enabled: !option.disabled, dimmed: 0.4, padding: 10, alignment: .center) {
                    if !option.disabled { model.language = option.id }
                } content: {
                    VStack(spacing: 0) {
                        line(option.title, size: 12, weight: .semibold, lineHeight: 16, color: ink.ink, centered: true)
                        line(option.desc, size: 10, lineHeight: 15, color: ink.muted, centered: true)
                            .padding(.top, 2)
                    }
                    .frame(maxWidth: .infinity)
                }
                .help(option.disabled ? Copy.languageLocked : "")
            }
        }
    }

    /// A template or length card: its name in 12pt semibold and a line of 11pt under it.
    private func smallCard(_ option: Catalog.Option, chosen: Bool, enabled: Bool, dimmed: Double, action: @escaping () -> Void) -> some View {
        MacBureauCustomizerCard(chosen: chosen, enabled: enabled, dimmed: dimmed, padding: 12, action: action) {
            VStack(alignment: .leading, spacing: 0) {
                line(option.title, size: 12, weight: .semibold, lineHeight: 16, color: ink.ink, wraps: true)
                line(option.desc, size: 11, lineHeight: 16.5, color: ink.muted, wraps: true)
                    .padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Engine & Quality

    private var engineTab: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 12) {
                sectionHead(Copy.workflowTitle, trailing: Copy.workflowDesc)
                grid(Catalog.modes, columns: sm ? 2 : 1, spacing: 12) { mode in
                    let unavailable = mode.id == "studio_review" && !model.studioAvailable
                    let chosen = !unavailable && model.generationMode == mode.id
                    MacBureauCustomizerCard(chosen: chosen, enabled: !unavailable, dimmed: 0.4, padding: 16) {
                        model.chooseMode(mode.id)
                    } content: {
                        VStack(alignment: .leading, spacing: 0) {
                            MacBureauCustomizerRow(spacing: 8) {
                                line(mode.title, size: 14, weight: .semibold, lineHeight: 20, color: ink.ink)
                                MacBureauCustomizerBadge(text: mode.badge, filled: model.generationMode == mode.id, lineHeight: 15)
                            }
                            .padding(.bottom, 6)
                            line(mode.desc, size: 12, lineHeight: 19.5, color: ink.muted, wraps: true)
                        }
                    }
                    .help(unavailable ? Copy.studioUnavailable : "")
                }
            }

            VStack(alignment: .leading, spacing: 12) {
                sectionHead(Copy.engineTitle, trailing: model.engineLocked ? model.engineLockReason : Copy.engineDesc, dim: model.engineLocked, oblique: model.engineLocked)
                grid(Catalog.engines, columns: sm ? 2 : 1, spacing: 12) { engine in
                    tierCard(engine, chosen: model.effectiveEngine == engine.id, locked: model.engineLocked) {
                        if !model.engineLocked { model.engine = engine.id }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 12) {
                sectionHead(Copy.qualityTitle, trailing: model.qualityLocked ? model.qualityLockReason : Copy.qualityDesc, dim: model.qualityLocked, oblique: model.qualityLocked)
                grid(Catalog.qualities, columns: sm ? 3 : 1, spacing: 12) { quality in
                    tierCard(quality, chosen: model.shownQuality == quality.id, locked: model.qualityLocked) {
                        model.quality = quality.id
                    }
                }
            }

            runControls
        }
    }

    /// An engine or quality card: its name in 12pt semibold with its badge, the description
    /// set loose (`leading-relaxed`).
    private func tierCard(_ option: Catalog.Option, chosen: Bool, locked: Bool, action: @escaping () -> Void) -> some View {
        MacBureauCustomizerCard(chosen: chosen, enabled: !locked, dimmed: 0.4, padding: 14, keepsChosenLook: true, action: action) {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauCustomizerRow(spacing: 8) {
                    line(option.title, size: 12, weight: .semibold, lineHeight: 16, color: ink.ink)
                    MacBureauCustomizerBadge(text: option.badge, filled: chosen, lineHeight: 15)
                }
                .padding(.bottom, 4)
                line(option.desc, size: 12, lineHeight: 19.5, color: ink.muted, wraps: true)
            }
        }
    }

    private var runControls: some View {
        let locked = model.runControlsLocked
        return VStack(alignment: .leading, spacing: 12) {
            sectionHead(Copy.controlsTitle, trailing: locked ? Copy.studioDefaults : Copy.controlsDesc, dim: locked, oblique: locked)
            VStack(spacing: 0) {
                MacBureauCustomizerRow(spacing: 12) {
                    VStack(alignment: .leading, spacing: 0) {
                        line(Copy.pauseAfterEnglish, size: 14, weight: .semibold, lineHeight: 20, color: ink.ink, wraps: true)
                        line(Copy.pauseAfterEnglishHelp, size: 12, lineHeight: 19.5, color: ink.muted, wraps: true)
                    }
                    MacBureauCustomizerSwitch(isOn: $model.pauseAfterEnglish, disabled: locked)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .compositingGroup()
                .opacity(locked ? 0.4 : 1)
                Rectangle().fill(Color.clear).frame(height: 1)
                    .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.rule) })
                MacBureauCustomizerRow(spacing: 12) {
                    VStack(alignment: .leading, spacing: 0) {
                        line(Copy.costCeiling, size: 14, weight: .semibold, lineHeight: 20, color: ink.ink, wraps: true)
                        line(Copy.costCeilingHelp, size: 12, lineHeight: 19.5, color: ink.muted, wraps: true)
                        if model.costCeilingInvalid {
                            line(Copy.costCeilingInvalid, size: 12, lineHeight: 16, color: ink.danger, wraps: true)
                        }
                    }
                    HStack(spacing: 6) {
                        MacBureauCustomizerField(placeholder: String(Catalog.defaultCostCeilingUsd), text: $model.costCeilingInput, alignment: .trailing, digits: true)
                            .frame(width: 96)
                            .disabled(locked)
                            .opacity(locked ? 0.55 : 1)
                        line(Copy.costCeilingUnit, size: 12, lineHeight: 16, color: ink.muted)
                            .fixedSize()
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .compositingGroup()
                .opacity(locked ? 0.4 : 1)
            }
            .padding(1)
            .background(MacBureauCustomizerSnapped { MacBureauCustomizerBoxFace(radius: 12, fill: ink.tray, border: ink.rule) })
        }
    }

    // MARK: Evidence Sources

    private var evidenceTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            sectionHead(Copy.evidenceTitle, trailing: Copy.evidenceDesc)
            let built = model.builtFromLine
            if !built.isEmpty {
                let webOnly = model.builtFromWebOnly
                HStack(alignment: .top, spacing: 8) {
                    LucideIcon(webOnly ? "triangle-alert" : "database", size: 14)
                        .customizerSnap(horizontal: true)
                        .padding(.top, 1)
                    line(built, size: 12, lineHeight: 16, color: webOnly ? ink.warningInk : ink.secondary, wraps: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .foregroundStyle(webOnly ? ink.warningInk : ink.secondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(MacBureauCustomizerSnapped { RoundedRectangle(cornerRadius: 8, style: .circular).fill(webOnly ? ink.customizerWarningSoft : ink.fillTertiary) })
            }
            if model.evidenceLoading {
                line(Copy.evidenceLoading, size: 14, lineHeight: 20, color: ink.muted)
            } else if model.evidenceFailed {
                line(Copy.evidenceFailed, size: 14, lineHeight: 20, color: ink.danger)
            } else if model.evidence.isEmpty && built.isEmpty {
                line(Copy.evidenceEmpty, size: 14, lineHeight: 20, color: ink.muted, wraps: true)
            } else if !model.evidence.isEmpty {
                Button { model.toggleAllEvidence() } label: {
                    line(model.allEvidenceSelected ? Copy.evidenceClearAll : Copy.evidenceSelectAll, size: 12, weight: .medium, lineHeight: 16, color: ink.accent)
                        .fixedSize()
                }
                .buttonStyle(MacBureauCustomizerBareStyle())
                VStack(spacing: 8) {
                    ForEach($model.evidence) { $source in
                        MacBureauCustomizerEvidenceRow(source: $source)
                    }
                }
            }
        }
    }

    // MARK: Error, pre-flight, footer

    private func errorBanner(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            LucideIcon("circle-alert", size: 16)
                .customizerSnap(horizontal: true)
                .padding(.top, 1)
            ScrollView(.vertical) {
                line(message, size: 12, lineHeight: 16, color: ink.danger, wraps: true)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 108)
            .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(ink.danger)
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(ink.danger.opacity(0.1))
        .overlay(alignment: .top) { Rectangle().fill(ink.danger.opacity(0.2)).frame(height: 1) }
    }

    private func preflight(_ rows: [MacBureauCustomizerModel.PreflightRow]) -> some View {
        let list = VStack(spacing: 6) {
            ForEach(rows) { row in
                preflightRow(row)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        return Group {
            if rows.count > 3 {
                ScrollView(.vertical) { list }.frame(height: 159)
            } else {
                list
            }
        }
        .frame(maxWidth: .infinity)
        .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.tray) })
    }

    private func preflightRow(_ row: MacBureauCustomizerModel.PreflightRow) -> some View {
        let tone: (fill: Color, text: Color) = {
            switch row.tone {
            case .blocker: return (ink.dangerSoft, ink.dangerInk)
            case .warning: return (ink.customizerWarningSoft, ink.warningInk)
            case .note: return (ink.fillTertiary, ink.secondary)
            }
        }()
        return HStack(alignment: .top, spacing: 8) {
            LucideIcon(row.icon, size: 14)
                .customizerSnap(horizontal: true)
                .padding(.top, 1)
            line(row.text, size: 12, lineHeight: 16.5, color: tone.text, wraps: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let action = row.action {
                MacBureauCustomizerPill(title: action.label, fontSize: 11, verticalPadding: 2, tracking: -0.066, action: action.run)
            }
        }
        .foregroundStyle(tone.text)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(MacBureauCustomizerSnapped { RoundedRectangle(cornerRadius: 8, style: .circular).fill(tone.fill) })
    }

    private var footer: some View {
        MacBureauCustomizerFooterLayout(gap: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if sm {
                    MacBureauCustomizerFlowLayout(spacing: 6) {
                        ForEach(Array(model.footerChips.enumerated()), id: \.offset) { _, chip in
                            line(chip, size: 12, weight: .medium, lineHeight: 16, color: ink.muted)
                                .customizerAdvance(chip, font: Kind.sans(12, .medium))
                                .padding(.horizontal, 11)
                                .padding(.vertical, 3)
                                .background(MacBureauCustomizerSnapped { MacBureauCustomizerBoxFace(radius: 999, fill: ink.customizerSurfaceMuted, border: ink.rule) })
                        }
                    }
                }
                let estimate = model.estimateText
                if !estimate.isEmpty {
                    HStack(alignment: .top, spacing: 6) {
                        LucideIcon("clock-3", size: 12)
                            .foregroundStyle(ink.muted)
                            .customizerSnap(horizontal: true)
                            .padding(.top, 1)
                        line(estimate, size: 11, lineHeight: 15.125, color: ink.muted, wraps: true)
                    }
                    .help(model.estimateNote ?? "")
                }
            }
            HStack(spacing: 8) {
                MacBureauCustomizerPill(title: Copy.cancel, action: close)
                    .disabled(model.generating)
                    .keyboardShortcut(.cancelAction)
                MacBureauCustomizerPill(title: model.launchLabel, filled: true, busy: model.generating, maxLabelWidth: 352) {
                    Task {
                        if let result = await model.launch() { created(result.report, result.companyId) }
                    }
                }
                .disabled(model.generating || model.company == nil)
                .help(model.launchLabel)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity)
        .background(MacBureauCustomizerSnapped { Rectangle().fill(ink.tray) })
    }

    // MARK: Pieces

    /// A section's label (the italic serif kicker) and, to the right, what it is for — or,
    /// locked, why, in the slanted face.
    private func sectionHead(_ title: String, trailing: String, dim: Bool = false, oblique: Bool = false) -> some View {
        MacBureauCustomizerRow(spacing: 12, flexibleLast: true) {
            MacBureauCustomizerKicker(title)
                .opacity(dim ? 0.5 : 1)
            line(trailing, size: 12, lineHeight: 16, color: ink.muted, wraps: true, trailing: true, oblique: oblique)
        }
    }

    /// Text as the website sets it: the interface face at a size, weight and line height,
    /// on the whole points Chrome paints its lines on. Wrapped text is broken as Chrome breaks
    /// it and set line by line; `lines` clamps it as `line-clamp` does.
    private func line(
        _ text: String, size: CGFloat, weight: Font.Weight = .regular, lineHeight: CGFloat, color: Color,
        wraps: Bool = false, lines: Int? = nil, centered: Bool = false, trailing: Bool = false, oblique: Bool = false
    ) -> some View {
        let alignment: TextAlignment = centered ? .center : (trailing ? .trailing : .leading)
        return Group {
            if wraps || lines != nil {
                MacBureauCustomizerParagraph(text: text, size: size, weight: weight, lineHeight: lineHeight, oblique: oblique, clamp: lines, alignment: alignment)
            } else {
                Text(text)
                    .font(oblique ? Kind.oblique(size) : BSHType.bureauSans(size, weight: weight))
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(lineHeight, size: size)
                    .customizerSnap()
            }
        }
        .foregroundStyle(color)
    }

    /// The website's CSS grid: equal columns, each row as tall as its tallest card.
    private func grid<Item: Identifiable, Cell: View>(
        _ items: [Item], columns: Int, spacing: CGFloat, @ViewBuilder cell: @escaping (Item) -> Cell
    ) -> some View {
        let count = max(columns, 1)
        let rows = stride(from: 0, to: items.count, by: count).map { Array(items[$0..<min($0 + count, items.count)]) }
        return VStack(alignment: .leading, spacing: spacing) {
            ForEach(rows.indices, id: \.self) { index in
                MacBureauCustomizerRowLayout(columns: count, spacing: spacing) {
                    ForEach(rows[index]) { item in
                        cell(item)
                    }
                }
            }
        }
    }
}
