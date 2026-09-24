//
//  MacBureauDossier.swift
//  BSHResearchMac
//
//  A company's dossier on Bureau's Research Desk, as the website draws it
//  (components/research/CompanyDossierView.vue and its cards): the header with the logo,
//  the name in Instrument Serif, its line, Generate report, Decision and the "…" menu; the
//  section tabs with the brass underline; then the cards in the website's order, each a
//  tray (`.mac-card`: the sheet's tray color, a rule round it, 12pt corners) whose title is
//  the interface face at 15pt semibold.
//

import AppKit
import SwiftUI

// MARK: - Sections

/// The dossier's tabs, in the website's order and words (dossierSections.js).
enum MacBureauDossierSection: String, CaseIterable, Identifiable {
    case overview, memos, files, decisions, team, pipeline, capTable, comps, ratios, all

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: return "Overview"
        case .memos: return "Memo Studio"
        case .files: return "Files"
        case .decisions: return "Decisions"
        case .team: return "Team"
        case .pipeline: return "Pipeline"
        case .capTable: return "Cap table"
        case .comps: return "Comps"
        case .ratios: return "Ratios"
        case .all: return "All"
        }
    }

    /// The tab a launch asks for (`bsh.launchDossierSection`, by title or by id).
    static var launch: MacBureauDossierSection {
        let raw = UserDefaults.standard.string(forKey: "bsh.launchDossierSection") ?? ""
        return allCases.first { $0.title == raw || $0.rawValue == raw } ?? .overview
    }
}

// MARK: - Card anatomy

private struct MacBureauDeskCardFrame: ViewModifier {
    var padding: CGFloat
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
        let ink = MacBureauDeskInk(colorScheme)
        let shape = RoundedRectangle(cornerRadius: 12, style: .circular)
        content
            .padding(padding + 1)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .bureauBox(shape, fill: ink.card, stroke: ink.hairline)
    }
}

extension View {
    /// `.mac-card`: a tray on the sheet with a rule round it (the rule inside the box, as
    /// CSS draws a border), then `padding` inside it.
    func bureauDeskCard(padding: CGFloat) -> some View {
        modifier(MacBureauDeskCardFrame(padding: padding))
    }
}

/// `.mac-cardheader`: the glyph in brass in an 18pt column, the title at 15pt semibold, its
/// line under it, and whatever the card keeps at the right, all hung from the top.
struct MacBureauDeskCardHeader<Trailing: View>: View {
    let icon: String
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var trailing: () -> Trailing
    @Environment(\.colorScheme) private var colorScheme

    init(icon: String, title: String, subtitle: String? = nil, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.icon = icon
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        HStack(alignment: .top, spacing: 8) {
            MacBureauDeskIcon(icon, size: 13)
                .foregroundStyle(ink.accent)
                .frame(width: 18, height: 13)
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(BSHType.bureauSans(15, weight: .semibold))
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .bureauDeskLine(18.75, 15)
                if let subtitle, !subtitle.isEmpty {
                    MacBureauWebParagraph(text: subtitle, size: 11, lineHeight: 13.75)
                        .foregroundStyle(ink.secondary)
                }
            }
            Spacer(minLength: 8)
            trailing()
        }
    }
}

extension MacBureauDeskCardHeader where Trailing == EmptyView {
    init(icon: String, title: String, subtitle: String? = nil) {
        self.init(icon: icon, title: title, subtitle: subtitle) { EmptyView() }
    }
}

/// `.mac-status-pill`: 10pt semibold in the tint, on the tint at 16%.
struct MacBureauDeskPill: View {
    let text: String
    let tint: Color

    var body: some View {
        Text(text)
            .font(BSHType.bureauSans(10, weight: .semibold))
            .foregroundStyle(tint)
            .lineLimit(1)
            .bureauExactWidth(text, size: 10, weight: .semibold)
            .bureauDeskLine(12, 10)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .bureauBox(Capsule(), fill: tint.opacity(0.16))
            .fixedSize()
    }
}

/// `.mac-status-tag`: the lighter tag, 10pt medium on the tint at 14%.
struct MacBureauDeskTag: View {
    let text: String
    let tint: Color

    var body: some View {
        Text(text)
            .font(BSHType.bureauSans(10, weight: .medium))
            .foregroundStyle(tint)
            .lineLimit(1)
            .bureauExactWidth(text, size: 10, weight: .medium)
            .bureauDeskLine(12, 10)
            .padding(.horizontal, 7)
            .padding(.vertical, 2.5)
            .bureauBox(Capsule(), fill: tint.opacity(0.14))
            .fixedSize()
    }
}

/// `.mac-stattile`: a label over a figure on the tile colour (`is-compact`: 10pt in).
struct MacBureauDeskStatTile: View {
    let label: String
    let value: String
    var tone: Color? = nil
    var compact = true
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(13.75, 11)
            Text(value)
                .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                .foregroundStyle(tone ?? ink.label)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(18, 15)
        }
        .padding(compact ? 10 : 12)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
    }
}

/// A table cell set as the website sets a fixed-width span: the text as wide as the browser
/// lays it out, at the cell's leading or trailing edge.
struct MacBureauDeskCell: View {
    let text: String
    let width: CGFloat
    var size: CGFloat = 12
    var weight: Font.Weight = .regular
    var lineHeight: CGFloat = 18
    var mono = false
    var trailing = true
    let color: Color

    var body: some View {
        Text(text)
            .font(mono ? BSHType.bureauSans(size, weight: weight).monospacedDigit() : BSHType.bureauSans(size, weight: weight))
            .foregroundStyle(color)
            .lineLimit(1)
            .bureauExactWidth(text, size: size, weight: weight, mono: mono)
            .bureauDeskLine(lineHeight, size)
            .frame(width: width, alignment: trailing ? .trailing : .leading)
    }
}

/// A native `input[type=range]` as Chrome draws it with the brass accent: an 8pt track,
/// brass (ruled a shade darker) up to the thumb and light grey past it, and a 15pt brass
/// thumb, in a 16pt box.
struct MacBureauDeskRange: View {
    @Binding var value: Double
    let range: ClosedRange<Double>
    var step: Double = 1
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled

    private static let thumb: CGFloat = 15

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let span = max(0.000_001, range.upperBound - range.lowerBound)
        let fraction = CGFloat(max(0, min(1, (value - range.lowerBound) / span)))
        GeometryReader { proxy in
            let width = proxy.size.width
            let centre = Self.thumb / 2 + fraction * max(0, width - Self.thumb)
            ZStack(alignment: .leading) {
                // The rest of the track (a point in from either end), then the brass up to
                // the thumb.
                Capsule()
                    .fill(Color.bshFixed(BSHRGB(239, 239, 239)))
                    .overlay(Capsule().strokeBorder(Color.bshFixed(BSHRGB(178, 178, 178)), lineWidth: 1))
                    .frame(width: max(8, width - 2), height: 8)
                    .offset(x: 1)
                Capsule()
                    .fill(ink.accent)
                    .overlay(Capsule().strokeBorder(Color.bshFixed(ink.dark ? BSHRGB(140, 119, 85) : BSHRGB(134, 115, 82)), lineWidth: 1))
                    .frame(width: max(8, centre - 1), height: 8)
                    .offset(x: 1)
                Circle()
                    .fill(ink.accent)
                    .frame(width: Self.thumb, height: Self.thumb)
                    .offset(x: centre - Self.thumb / 2)
            }
            .frame(width: width, height: 16, alignment: .leading)
            // Blink paints the control on whole pixels.
            .bureauSnap(x: .whole)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { drag in
                        let usable = max(1, width - Self.thumb)
                        let f = Double(max(0, min(1, (drag.location.x - Self.thumb / 2) / usable)))
                        let raw = range.lowerBound + f * span
                        let stepped = (raw / step).rounded() * step
                        value = max(range.lowerBound, min(range.upperBound, stepped))
                    }
            )
        }
        .frame(height: 16)
        .opacity(isEnabled ? 1 : 0.5)
        .accessibilityElement()
        .accessibilityValue(String(format: "%.1f", value))
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: value = min(range.upperBound, value + step)
            case .decrement: value = max(range.lowerBound, value - step)
            @unknown default: break
            }
        }
    }
}

/// `.mac-cardheader.flex-wrap`: the glyph and title block, then the controls at the right of
/// the first line while they fit and wrapping onto lines of their own from the left, 8pt
/// apart both ways — the first subview is the title block.
struct MacBureauDeskHeaderWrap: Layout {
    var spacing: CGFloat = 8

    private struct Lines {
        var first: [Int] = []
        var rest: [[Int]] = []
    }

    private func lines(_ subviews: Subviews, width: CGFloat) -> Lines {
        var result = Lines()
        guard subviews.count > 1 else { return result }
        let lead = subviews[0].sizeThatFits(.unspecified).width
        // The title block, a gap, the spacer at its 8pt minimum and a gap before the controls.
        var used = lead + spacing + 8
        var open = true
        var x: CGFloat = 0
        for index in 1..<subviews.count {
            let w = subviews[index].sizeThatFits(.unspecified).width
            if open, used + spacing + w <= width {
                result.first.append(index)
                used += spacing + w
                continue
            }
            open = false
            if result.rest.isEmpty || x + w > width {
                result.rest.append([index])
                x = w + spacing
            } else {
                result.rest[result.rest.count - 1].append(index)
                x += w + spacing
            }
        }
        return result
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 600
        let split = lines(subviews, width: width)
        guard !subviews.isEmpty else { return .zero }
        var height = ([0] + split.first).map { subviews[$0].sizeThatFits(.unspecified).height }.max() ?? 0
        for line in split.rest {
            height += spacing + (line.map { subviews[$0].sizeThatFits(.unspecified).height }.max() ?? 0)
        }
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let split = lines(subviews, width: bounds.width)
        let lead = subviews[0].sizeThatFits(.unspecified)
        subviews[0].place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(lead))
        let firstSizes = split.first.map { subviews[$0].sizeThatFits(.unspecified) }
        let firstWidth = firstSizes.map(\.width).reduce(0, +) + spacing * CGFloat(max(0, firstSizes.count - 1))
        var x = bounds.maxX - firstWidth
        for (index, size) in zip(split.first, firstSizes) {
            subviews[index].place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(size))
            x += size.width + spacing
        }
        var y = bounds.minY + (([lead.height] + firstSizes.map(\.height)).max() ?? 0)
        for line in split.rest {
            y += spacing
            var lx = bounds.minX
            let sizes = line.map { subviews[$0].sizeThatFits(.unspecified) }
            for (index, size) in zip(line, sizes) {
                subviews[index].place(at: CGPoint(x: lx, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
                lx += size.width + spacing
            }
            y += sizes.map(\.height).max() ?? 0
        }
    }
}

/// The refresh glyph every card keeps at its right (`.mac-btn--mini.mac-btn--plain`), turning
/// while it loads.
struct MacBureauDeskRefreshButton: View {
    var busy = false
    var help = "Refresh"
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            MacBureauDeskIcon("rotate-cw", size: 12)
                .rotationEffect(.degrees(busy ? 360 : 0))
                .animation(busy ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: busy)
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: .plain, size: .mini))
        .disabled(busy)
        .help(help)
    }
}

/// A CSS grid of equal columns: every cell as wide as the others and, row by row, as tall
/// as the tallest (align-items: stretch).
struct MacBureauDeskGrid: Layout {
    var columns: Int
    var spacing: CGFloat
    var rowSpacing: CGFloat? = nil

    private func columnWidth(_ width: CGFloat) -> CGFloat {
        max(0, (width - spacing * CGFloat(columns - 1)) / CGFloat(columns))
    }

    private func rowHeights(_ subviews: Subviews, width: CGFloat) -> [CGFloat] {
        let w = columnWidth(width)
        return stride(from: 0, to: subviews.count, by: columns).map { start in
            subviews[start..<min(start + columns, subviews.count)]
                .map { $0.sizeThatFits(ProposedViewSize(width: w, height: nil)).height }
                .max() ?? 0
        }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? (subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0) * CGFloat(columns)
            + spacing * CGFloat(columns - 1)
        let heights = rowHeights(subviews, width: width)
        let gaps = (rowSpacing ?? spacing) * CGFloat(max(0, heights.count - 1))
        return CGSize(width: width, height: heights.reduce(0, +) + gaps)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let w = columnWidth(bounds.width)
        let heights = rowHeights(subviews, width: bounds.width)
        var y = bounds.minY
        for (row, height) in heights.enumerated() {
            for column in 0..<columns {
                let index = row * columns + column
                guard index < subviews.count else { break }
                subviews[index].place(
                    at: CGPoint(x: bounds.minX + CGFloat(column) * (w + spacing), y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(width: w, height: height)
                )
            }
            y += height + (rowSpacing ?? spacing)
        }
    }
}

/// Columns in proportion to `weights` (CSS `fr` units), each as tall as the tallest.
struct MacBureauDeskColumns: Layout {
    var weights: [CGFloat]
    var spacing: CGFloat

    private func widths(_ total: CGFloat, count: Int) -> [CGFloat] {
        let w = Array(weights.prefix(count)) + Array(repeating: 1, count: max(0, count - weights.count))
        let sum = w.reduce(0, +)
        let free = max(0, total - spacing * CGFloat(max(0, count - 1)))
        return w.map { free * $0 / max(sum, 0.0001) }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width ?? 600
        let ws = widths(total, count: subviews.count)
        let height = zip(subviews, ws).map { $0.sizeThatFits(ProposedViewSize(width: $1, height: nil)).height }.max() ?? 0
        return CGSize(width: total, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let ws = widths(bounds.width, count: subviews.count)
        var x = bounds.minX
        for (subview, w) in zip(subviews, ws) {
            subview.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(width: w, height: bounds.height))
            x += w + spacing
        }
    }
}

// MARK: - The dossier

/// The dossier: header, tabs and cards, in a column 20pt in from the sheet (and never wider
/// than 1180pt), scrolling under nothing.
struct MacBureauDossier: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var section: MacBureauDossierSection = .launch
    @Namespace private var underline

    private var ink: MacBureauDeskInk { MacBureauDeskInk(colorScheme) }

    private func shows(_ sections: MacBureauDossierSection...) -> Bool {
        section == .all || sections.contains(section)
    }

    /// Listed on an exchange: a ticker or a public status, unless the record says private.
    private var isListed: Bool {
        let status = (company.status ?? "").lowercased()
        if status == "private" { return false }
        return !(company.ticker ?? "").trimmingCharacters(in: .whitespaces).isEmpty || status == "public"
    }

    private var companyReports: [MacReport] { store.reports(for: company.id) }
    private var runningReports: [MacReport] { companyReports.filter { !$0.isComplete && !$0.isFailed } }

    /// ticker · sector (or industry) · status, as the website's headerSubtitle.
    private var headerLine: String {
        var parts: [String] = []
        if let t = company.ticker, !t.isEmpty { parts.append(t.uppercased()) }
        if let s = company.sector, !s.isEmpty { parts.append(s) } else if let i = company.industry, !i.isEmpty { parts.append(i) }
        if let status = company.status, !status.isEmpty { parts.append(status.prefix(1).uppercased() + status.dropFirst()) }
        return parts.isEmpty ? company.subtitle : parts.joined(separator: " · ")
    }

    var body: some View {
        ScrollViewReader { reader in
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    tabBar
                    overviewCards
                    sectionCards
                }
                .padding(20)
                .frame(maxWidth: 1180, alignment: .topLeading)
                // The scroll view rounds its content's height up to a device pixel; pinned
                // to the top, the content keeps its place instead of centring in the spare.
                .frame(maxWidth: .infinity, alignment: .top)
                .bureauPixelGrid("bureauDossier")
                // The section views the IC Review window shares draw as Research Desk cards here.
                .environment(\.bureauResearchDesk, true)
            }
            .scrollIndicators(.automatic)
            .environment(\.bureauDossierScroll) { id in
                withAnimation(.easeInOut(duration: 0.3)) { reader.scrollTo(id, anchor: .top) }
            }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            MacBureauDeskLogo(company: company, size: 48)
            // The website centres the block (47.94pt) in the logo's 48 and paints the title
            // and its line on whole pixels: 72 and 102 on the page.
            VStack(alignment: .leading, spacing: 3.6) {
                HStack(spacing: 10) {
                    Text(company.name ?? company.id)
                        .font(.custom(BSHType.bureauSerif, size: 22))
                        .tracking(-0.22)
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauDeskLine(26.4, 22, serif: true)
                    if store.isFollowed(company.id) {
                        MacBureauDeskIcon("star-fill", size: 12)
                            .foregroundStyle(ink.yellow)
                            .help("Followed on the Pipeline board")
                    }
                }
                Text(headerLine)
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(17.55, 13)
            }
            .frame(height: 48, alignment: .top)
            Spacer(minLength: 12)
            actions
                .fixedSize()
        }
        .frame(height: 48)
        .padding(.bottom, 4)
    }

    private var actions: some View {
        HStack(spacing: 8) {
            Button {
                store.requestNewReport(for: company)
            } label: {
                MacBureauDeskButtonLabel(title: "Generate report", orb: true, iconSize: 14)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent))
            .disabled(!store.canRunTasks)
            .help(store.canRunTasks ? "Generate report (⌘N)" : "Sign in with an analyst or partner role to run memos")

            Button {
                store.requestDecision(for: company)
            } label: {
                MacBureauDeskButtonLabel(title: "Decision", icon: "badge-check", iconSize: 14)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered))
            .disabled(!store.canRunTasks)
            .help("Record Invest / Pass / Watch (⌘D)")

            if let report = companyReports.first(where: \.canOpen) {
                Button {
                    store.openICReview(report: report)
                } label: {
                    MacBureauDeskButtonLabel(title: "IC Review", icon: "columns-2", iconSize: 14)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered))
                .help("Memo beside thesis, risks, evidence and the decision form (⌘⇧O)")
            }

            moreMenu
                .offset(y: -0.75)
        }
    }

    /// The "…" menu: follow, the research browser, the web, and Warren.
    private var moreMenu: some View {
        Menu {
            Button {
                Task { await store.toggleFollow(company.id) }
            } label: {
                Label(store.isFollowed(company.id) ? "Unfollow" : "Follow on Pipeline", systemImage: store.isFollowed(company.id) ? "star.slash" : "star")
            }
            .disabled(!store.canRunTasks)
            Button {
                withAnimation { store.openInEmbeddedBrowser(MacConfig.webCompanyURL(id: company.id)) }
            } label: {
                Label("Open in Research Browser", systemImage: "globe")
            }
            Button {
                MacConfig.openInBrowser(MacConfig.webCompanyURL(id: company.id))
            } label: {
                Label("Open on Web", systemImage: "safari")
            }
            Divider()
            Button {
                store.askWarren(
                    "Give me the one-paragraph state of play for \(company.title).",
                    context: MacCopilotContext(surface: "research", tab: "memo"),
                    company: company
                )
            } label: {
                Label("Ask Warren", systemImage: "bubble.left.and.bubble.right")
            }
            .disabled(!store.canRunTasks)
        } label: {
            MacBureauDeskMenuPill()
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More actions")
    }

    // MARK: Tabs

    /// `.mac-tabbar`: the sections at 13pt, the open one semibold in ink over a 2pt brass
    /// underline that slides between them, all on a rule.
    private var tabBar: some View {
        VStack(spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .bottom, spacing: 20) {
                    ForEach(MacBureauDossierSection.allCases) { item in
                        tab(item)
                    }
                }
            }
            .scrollClipDisabled()
            .frame(height: 31.5)
            MacBureauGridRule(color: ink.hairline)
        }
    }

    private func tab(_ item: MacBureauDossierSection) -> some View {
        let active = item == section
        return Button {
            withAnimation(.timingCurve(0.2, 0.9, 0.3, 1, duration: 0.22)) { section = item }
        } label: {
            Text(item.title)
                .font(BSHType.bureauSans(13, weight: active ? .semibold : .regular))
                .foregroundStyle(active ? ink.label : ink.secondary)
                .fixedSize()
                // As wide as the browser sets the word, so the tabs don't creep right.
                .frame(width: MacBureauWebLine.width(item.title, size: 13, weight: active ? .semibold : .regular), alignment: .leading)
                .bureauDeskLine(19.5, 13)
                .padding(.top, 4)
                .padding(.bottom, 8)
                .overlay(alignment: .bottom) {
                    if active {
                        MacBureauGridRule(color: ink.underline, thickness: 2)
                            .matchedGeometryEffect(id: "underline", in: underline)
                    }
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(active ? .isSelected : [])
    }

    // MARK: Cards

    @ViewBuilder
    private var overviewCards: some View {
        if shows(.overview) {
            MacBureauProfileCard(company: company)
            MacBureauSignalCard(companyId: company.id)
        }
        if isListed && shows(.overview) {
            MacBureauEarningsCard(company: company)
                .id(company.id)
        }
        if isListed ? shows(.pipeline) : shows(.pipeline, .overview) {
            MacDealPipelineView(company: company)
        }
        if shows(.comps) {
            MacCompsRailView(company: company)
                .id(company.id)
        }
        if shows(.capTable) {
            MacCapTableSimulatorView(company: company)
                .id(company.id)
        }
        if shows(.files) {
            MacBureauFilesCard(company: company)
                .id(company.id)
            MacBureauFactLedgerCard(companyId: company.id)
                .id(company.id)
        }
        if shows(.team) {
            MacFounderRadarView(company: company)
        }
        if shows(.ratios) {
            MacVCRatiosBlotterView(company: company)
                .id(company.id)
        }
    }

    @ViewBuilder
    private var sectionCards: some View {
        if shows(.memos, .overview) && !runningReports.isEmpty {
            activePipelines
        }
        if shows(.memos, .overview) {
            MacBureauReportsCard(company: company, reports: companyReports)
            MacBureauMemoStudio(company: company, isPublic: isListed)
        }
        if shows(.decisions, .overview) {
            MacBureauDecisionRecordCard(company: company)
        }
        if shows(.decisions) {
            MacICPrepView(company: company)
            MacICRoomView(companyId: company.id, reportId: nil)
                .id(company.id)
            MacBureauNumberLintCard(companyId: company.id)
            MacThesisTrackerView(company: company)
            MacBureauCommentsCard(companyId: company.id, target: MacCommentTarget(kind: "company", ref: company.id, label: company.title))
                .id(company.id)
        }
    }

    /// Runs still working, on a faint wash of ink.
    private var activePipelines: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("refresh-cw", size: 14)
                    .foregroundStyle(ink.accent)
                Text("Active Analysis Pipelines")
                    .font(BSHType.bureauSans(13, weight: .semibold))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(16.9, 13)
            }
            ForEach(runningReports) { report in
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text(report.displayTitle)
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                    Text(report.stage ?? "Processing…")
                        .font(BSHType.bureauSans(10).monospacedDigit())
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                }
                .padding(10)
                .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.orange.opacity(0.08))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.secondary.opacity(0.05))
    }
}

/// The "…" button's face: a pill ruled in ink round the ellipsis.
private struct MacBureauDeskMenuPill: View {
    @Environment(\.colorScheme) private var colorScheme
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        MacBureauDeskIcon("circle-ellipsis", size: 15)
            .foregroundStyle(ink.label)
            .padding(.horizontal, 12)
            .padding(.vertical, 4.5)
            .bureauBox(Capsule(), fill: hovered ? ink.label(0.05) : .clear, stroke: ink.label(0.2))
            .contentShape(Capsule())
            .onHover { hovered = $0 }
    }
}

// MARK: - Profile

/// UnifiedProfileCard: the Profile head (layers glyph, Public or Private pill, refresh), then
/// three columns of facts (public quote; the market or the private position; the process)
/// and the company's line, two lines at most.
struct MacBureauProfileCard: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var loadAttempted = false
    @State private var loading = false

    private var profile: MacCompanyProfile? { store.profileByCompany[company.id] }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("layers", size: 14)
                    .foregroundStyle(ink.accent)
                Text("Profile")
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(14.3, 11)
                Spacer(minLength: 0)
                if let p = profile {
                    MacBureauDeskPill(text: p.isPublic ? "Public" : "Private", tint: p.isPublic ? ink.blue : ink.purple)
                }
                MacBureauDeskRefreshButton(busy: loading) { Task { await load() } }
            }
            .frame(height: 18)

            if let p = profile {
                MacBureauDeskGrid(columns: 3, spacing: 14) {
                    publicColumn(p, ink: ink)
                    if p.isPublic && p.privateSide == nil {
                        marketColumn(p, ink: ink)
                    } else {
                        privateColumn(p, ink: ink)
                    }
                    processColumn(p, ink: ink)
                }
                if !p.description.isEmpty {
                    MacBureauWebParagraph(text: p.description, size: 10, lineHeight: 12.5, maxLines: 2)
                        .foregroundStyle(ink.secondary)
                }
            } else if loadAttempted {
                HStack(spacing: 8) {
                    Text("Profile unavailable on this server.")
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.secondary)
                    Button { Task { await load() } } label: { MacBureauDeskButtonLabel(title: "Retry", size: .mini) }
                        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                }
            } else {
                ProgressView().controlSize(.small).padding(.vertical, 4)
            }
        }
        .bureauDeskCard(padding: 12)
        .task(id: company.id) {
            loadAttempted = false
            if profile == nil { await load() } else { loadAttempted = true }
        }
    }

    private func load() async {
        loading = true
        await store.loadProfile(company.id)
        loading = false
        guard !Task.isCancelled else { return }
        loadAttempted = true
    }

    private func column<Content: View>(_ title: String, ink: MacBureauDeskInk, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private func fact(_ label: String, _ value: String, ink: MacBureauDeskInk, tone: Color? = nil, asOf: String? = nil, help: String? = nil) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .font(BSHType.bureauSans(10))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .bureauDeskLine(12.5, 10)
                .frame(width: 74, alignment: .leading)
            Text(value)
                .font(BSHType.bureauSans(10).monospacedDigit())
                .foregroundStyle(tone ?? ink.label)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(12.5, 10)
                .help(help ?? "")
            if let asOf, !asOf.isEmpty {
                Text(asOf)
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.tertiary)
                    .lineLimit(1)
                    .fixedSize()
                    .bureauDeskLine(12.5, 10)
                    .help(help ?? "")
            }
        }
    }

    private func note(_ text: String, ink: MacBureauDeskInk) -> some View {
        Text(text)
            .font(BSHType.bureauSans(10))
            .foregroundStyle(ink.secondary)
            .bureauDeskLine(12.5, 10)
    }

    private func publicColumn(_ p: MacCompanyProfile, ink: MacBureauDeskInk) -> some View {
        column("Public", ink: ink) {
            if let q = p.publicSide, let price = q.lastPrice {
                fact("Ticker", q.ticker ?? company.ticker ?? "—", ink: ink)
                fact("Last", String(format: "$%.2f", price), ink: ink, tone: (q.changePct1d ?? 0) >= 0 ? ink.green : ink.red)
                fact("1D", q.changePct1d.map { String(format: "%@%.2f%%", $0 >= 0 ? "+" : "", $0) } ?? "—", ink: ink)
                fact("Mkt cap", q.marketCap.map { "$" + Self.compact($0) } ?? "—", ink: ink)
            } else {
                note(p.isPublic ? "Quote unavailable" : "No public listing", ink: ink)
            }
        }
    }

    private func marketColumn(_ p: MacCompanyProfile, ink: MacBureauDeskInk) -> some View {
        column("Market", ink: ink) {
            let q = p.publicSide
            fact("P/E", q?.peRatio.map { String(format: "%.1f", $0) } ?? "—", ink: ink)
            fact("EPS", q?.eps.map { String(format: "$%.2f", $0) } ?? "—", ink: ink)
            fact("52-wk range", {
                guard let low = q?.fiftyTwoWeekLow, let high = q?.fiftyTwoWeekHigh else { return "—" }
                return String(format: "$%.2f – $%.2f", low, high)
            }(), ink: ink)
            fact("Div. yield", q?.dividendYield.map { String(format: "%.2f%%", $0 * 100) } ?? "—", ink: ink)
        }
    }

    private func privateColumn(_ p: MacCompanyProfile, ink: MacBureauDeskInk) -> some View {
        column("Private", ink: ink) {
            if p.privateSide != nil || !p.reported.isEmpty {
                let pr = p.privateSide
                let position = [pr?.position.round, pr?.position.investedUsd.map { "$" + Self.compact($0) }]
                    .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                fact("Position", position.isEmpty ? "—" : position, ink: ink)
                fact("Own", pr?.position.ownershipPct.map { String(format: "%.1f%%", $0) } ?? "—", ink: ink)
                if let arr = pr?.latestKpi?.arrUsd {
                    fact("ARR", "$" + Self.compact(arr), ink: ink)
                } else {
                    let reported = p.reported["arr"]
                    fact("ARR", reported?.value ?? "—", ink: ink, asOf: reported?.asOfShort, help: reported?.help)
                }
                if let runway = pr?.latestKpi?.runwayMonths {
                    fact("Runway", String(format: "%.0f mo", runway), ink: ink, tone: runway < 9 ? ink.red : nil)
                } else {
                    let reported = p.reported["runway"]
                    fact("Runway", reported?.value ?? "—", ink: ink, asOf: reported?.asOfShort, help: reported?.help)
                }
                let mark = [pr?.latestMark.map { "$" + Self.compact($0.valueUsd) }, pr?.moic.map { String(format: "%.2fx", $0) }]
                    .compactMap { $0 }.joined(separator: " · ")
                fact("Mark · MOIC", mark.isEmpty ? "—" : mark, ink: ink)
            } else {
                note("No position on file", ink: ink)
            }
        }
    }

    private func processColumn(_ p: MacCompanyProfile, ink: MacBureauDeskInk) -> some View {
        column("Process", ink: ink) {
            if !p.isPublic {
                fact("Stage", p.pipeline?.stage ?? store.dealPipelines[company.id]?.stage ?? "Sourced", ink: ink)
                fact("Thesis fit", p.thesisFit?.score.map { "\($0)%" } ?? Self.capitalized(p.thesisFit?.fit ?? "—"), ink: ink)
            }
            let verdict = (p.latestDecision?.verdict ?? "").lowercased()
            fact(
                "Decision",
                verdict.isEmpty ? "—" : Self.capitalized(verdict),
                ink: ink,
                tone: verdict == "invest" ? ink.green : (verdict == "pass" ? ink.red : nil)
            )
            fact("IC", (p.ic?.openMeeting != nil ? "Meeting open" : "\(p.ic?.meetingCount ?? 0) meetings") + " · \(p.ic?.referenceCalls ?? 0) refs", ink: ink)
            let c = p.counts
            fact("On file", "\(c?.files ?? 0) files · \(c?.transcripts ?? 0) transcripts · \(c?.openComments ?? 0) open comments", ink: ink)
        }
    }

    private static func capitalized(_ value: String) -> String {
        value.isEmpty ? value : value.prefix(1).uppercased() + value.dropFirst()
    }

    /// formatCompactNumber (formatters.js): one decimal under 100 of a unit, none above.
    static func compact(_ value: Double) -> String {
        let v = abs(value)
        let (scale, unit): (Double, String) = v >= 1e12 ? (1e12, "T") : v >= 1e9 ? (1e9, "B") : v >= 1e6 ? (1e6, "M") : v >= 1e3 ? (1e3, "K") : (1, "")
        let scaled = v / scale
        let digits = (scale == 1 || scaled >= 100) ? 0 : 1
        return (value < 0 ? "-" : "") + String(format: "%.\(digits)f", scaled) + unit
    }
}

// MARK: - Signal score

/// SignalScoreCard: the 52pt ring, the title, what it covers and its formula; Formula opens
/// the breakdown by component.
struct MacBureauSignalCard: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var expanded = false
    @State private var loading = false

    private var score: MacSignalScore? { store.signalScoreByCompany[companyId] }

    private var thinCoverage: Bool {
        guard let s = score, s.score != nil, !s.components.isEmpty else { return false }
        return s.components.filter(\.available).count * 2 < s.components.count
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ring(ink)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("Signal score")
                            .font(BSHType.bureauSans(15, weight: .semibold))
                            .tracking(-0.3)
                            .foregroundStyle(ink.label)
                            .bureauDeskLine(18.75, 15)
                        if thinCoverage, let s = score {
                            MacBureauDeskPill(text: "Partial · \(s.components.filter(\.available).count) of \(s.components.count)", tint: ink.orange)
                        }
                    }
                    Text(coverage)
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(13.75, 11)
                        .lineLimit(2)
                    if let s = score, !s.formula.isEmpty {
                        MacBureauWebText.text(s.formula, size: 11)
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.tertiary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .bureauDeskLine(13.75, 11)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 6) {
                    Button { expanded.toggle() } label: { MacBureauDeskButtonLabel(title: expanded ? "Hide" : "Formula", size: .mini) }
                        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                    MacBureauDeskRefreshButton(busy: loading) {
                        Task {
                            loading = true
                            await store.loadSignalScore(companyId)
                            loading = false
                        }
                    }
                }
            }
            if expanded, let s = score {
                VStack(spacing: 0) {
                    ForEach(Array(s.components.enumerated()), id: \.offset) { index, c in
                        HStack(alignment: .top, spacing: 8) {
                            Text(c.name)
                                .font(BSHType.bureauSans(10, weight: .semibold))
                                .foregroundStyle(ink.label)
                                .lineLimit(1)
                                .frame(width: 110, alignment: .leading)
                            Text(c.available ? String(format: "%.1f / %d", c.points ?? 0, c.max) : "not scored · \(c.max) max")
                                .font(BSHType.bureauSans(10).monospacedDigit())
                                .foregroundStyle(c.available ? ink.label : ink.secondary)
                                .frame(width: 120, alignment: .leading)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(c.formula).font(BSHType.bureauSans(10)).foregroundStyle(ink.secondary)
                                if !c.basis.isEmpty {
                                    Text(c.basis).font(BSHType.bureauSans(10)).foregroundStyle(ink.tertiary)
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .overlay(alignment: .top) {
                            if index > 0 { Rectangle().fill(ink.hairline).frame(height: 1) }
                        }
                    }
                }
                .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .circular))
            }
        }
        .bureauDeskCard(padding: 12)
        .task(id: companyId) { if score == nil { await store.loadSignalScore(companyId) } }
    }

    private var coverage: String {
        guard let s = score else { return "Loading…" }
        if s.isInsufficient {
            return "Insufficient data · \(s.components.filter(\.available).count) of \(s.components.count)"
        }
        return s.coverage.replacingOccurrences(of: " have data", with: " with data")
    }

    private func ring(_ ink: MacBureauDeskInk) -> some View {
        let value = score?.score
        let tone: Color = value.map { $0 >= 70 ? ink.green : ($0 >= 40 ? ink.orange : ink.red) } ?? ink.secondary
        return ZStack {
            Circle()
                .stroke(ink.secondary.opacity(0.15), lineWidth: 5)
                .padding(2.5)
            Circle()
                .trim(from: 0, to: CGFloat(min(max(value ?? 0, 0), 100)) / 100)
                .stroke(tone, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .padding(2.5)
                .opacity(thinCoverage ? 0.4 : 1)
                .animation(.easeOut(duration: 0.7), value: value)
            Text(value.map { "\($0)" } ?? "—")
                .font(BSHType.bureauSans(15, weight: .bold).monospacedDigit())
                .foregroundStyle(ink.label)
                .bureauDeskLine(22.5, 15)
        }
        .frame(width: 52, height: 52)
        .bureauSnap(x: .whole)
    }
}

// MARK: - Earnings & filings

/// EarningsFilingsCard: the next report on a brass wash, the recent quarters against the
/// estimate, and the SEC filings of the last 90 days.
struct MacBureauEarningsCard: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var refreshing = false

    private var data: MacCompanyEarningsFilings? { store.earningsFilingsByCompany[company.id] }
    private var failed: Bool { store.earningsFilingsFailed.contains(company.id) }

    /// Five rows, material filings first in line for them, shown newest first.
    private var filings: [MacFiling] {
        let rows = data?.filings ?? []
        let material = rows.filter(\.material)
        let rest = rows.filter { !$0.material }
        return (Array(material.prefix(5)) + Array(rest.prefix(max(0, 5 - material.count))))
            .sorted { $0.filed > $1.filed }
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 14) {
            MacBureauDeskCardHeader(
                icon: "trending-up",
                title: "Earnings & filings",
                subtitle: "Next report, recent quarters against estimates, and SEC filings from the last 90 days."
            ) {
                MacBureauDeskRefreshButton(busy: refreshing, help: "Refresh from SEC EDGAR and Nasdaq") {
                    Task {
                        refreshing = true
                        await store.loadEarningsFilings(company.id, refresh: true)
                        refreshing = false
                    }
                }
            }

            if data == nil && failed {
                HStack(spacing: 8) {
                    Text("Earnings and filings couldn't be loaded.")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.secondary)
                    Button { Task { await store.loadEarningsFilings(company.id) } } label: { MacBureauDeskButtonLabel(title: "Retry", size: .mini) }
                        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                }
            } else if let data {
                MacBureauDeskGrid(columns: 2, spacing: 14) {
                    nextTile(data.earnings, ink: ink)
                    quartersTile(data.earnings?.history ?? [], ink: ink)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("SEC filings · 90 days")
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(13.75, 11)
                    if filings.isEmpty {
                        Text(data.error ?? "No watched filings in the last 90 days.")
                            .font(BSHType.bureauSans(10))
                            .foregroundStyle(ink.secondary)
                            .bureauDeskLine(12.5, 10)
                    }
                    ForEach(filings) { filing in
                        filingRow(filing, ink: ink)
                    }
                }
            } else {
                ProgressView().controlSize(.small).padding(.vertical, 4)
            }
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            if data == nil { await store.loadEarningsFilings(company.id) }
        }
    }

    private func nextTile(_ earnings: MacCompanyEarningsFilings.Earnings?, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                MacBureauDeskIcon("calendar-clock", size: 12)
                Text("Next earnings")
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .bureauDeskLine(13.75, 11)
            }
            .foregroundStyle(ink.accent)
            if let date = earnings?.nextDate {
                Text(date)
                    .font(BSHType.bureauSans(13, weight: .medium).monospacedDigit())
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(16.9, 13)
                Text([whenText(earnings?.daysToNext), earnings?.nextEstimated == true ? "estimated" : nil].compactMap { $0 }.joined(separator: " · "))
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(12.5, 10)
            } else {
                Text("Not set")
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(12.5, 10)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.accent.opacity(0.1))
    }

    private func quartersTile(_ quarters: [MacCompanyEarningsFilings.Quarter], ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Quarters vs. estimates")
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .bureauDeskLine(13.75, 11)
            if quarters.isEmpty {
                Text("No earnings history available for this ticker.")
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(12.5, 10)
            }
            ForEach(quarters) { q in
                HStack(spacing: 8) {
                    Text(q.period ?? q.reported ?? "")
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .bureauDeskLine(12.5, 10)
                        .frame(width: 64, alignment: .leading)
                    Text("EPS \(money(q.eps)) vs \(money(q.estimate))")
                        .font(BSHType.bureauSans(10).monospacedDigit())
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .bureauDeskLine(12.5, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(surprise(q.surprisePct))
                        .font(BSHType.bureauSans(10).monospacedDigit())
                        .foregroundStyle(surpriseTone(q.surprisePct, ink: ink))
                        .bureauExactWidth(surprise(q.surprisePct), size: 10, mono: true)
                        .bureauDeskLine(12.5, 10)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private func filingRow(_ filing: MacFiling, ink: MacBureauDeskInk) -> some View {
        Button {
            if let url = URL(string: filing.url) { MacConfig.openInBrowser(url) }
        } label: {
            HStack(spacing: 8) {
                MacBureauDeskIcon("file-text", size: 12)
                    .foregroundStyle(ink.secondary)
                Text(filing.form)
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .bureauDeskLine(12.5, 10)
                    .frame(width: 52, alignment: .leading)
                Text(filing.plainLabel)
                    .font(BSHType.bureauSans(10))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .bureauDeskLine(12.5, 10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if filing.material {
                    MacBureauDeskTag(text: "Material", tint: ink.orange)
                }
                Text(filing.filed)
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(ink.tertiary)
                    .bureauExactWidth(filing.filed, size: 10, mono: true)
                    .bureauDeskLine(12.5, 10)
                MacBureauDeskIcon("external-link", size: 12)
                    .foregroundStyle(ink.tertiary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Open on SEC EDGAR")
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
        return String(format: "%@%.1f%%", pct > 0 ? "+" : "", pct)
    }

    private func surpriseTone(_ pct: Double?, ink: MacBureauDeskInk) -> Color {
        guard let pct, pct != 0 else { return ink.secondary }
        return pct > 0 ? ink.green : ink.red
    }
}

// MARK: - Research Reports & Memos

/// ReportsMemosCard: the company's memos, newest first, each with its language and status
/// tags, when it was updated and for whom, and what can be done with it.
struct MacBureauReportsCard: View {
    let company: MacCompany
    let reports: [MacReport]
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 14) {
            MacBureauDeskCardHeader(
                icon: "file-text",
                title: "Research Reports & Memos",
                subtitle: reports.isEmpty ? nil : "\(reports.count) dossiers on file"
            ) {
                Button {
                    store.requestNewReport(for: company)
                } label: {
                    MacBureauDeskButtonLabel(title: "Generate report", orb: true, iconSize: 13, size: .small)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small))
                .disabled(!store.canRunTasks)
                .help("Generate report (⌘N)")
            }

            if reports.isEmpty {
                VStack(spacing: 8) {
                    Text("No research reports on file yet.")
                        .font(BSHType.bureauSans(13, weight: .medium))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(16.9, 13)
                    Button {
                        store.requestNewReport(for: company)
                    } label: {
                        MacBureauDeskButtonLabel(title: "Generate report", orb: true, iconSize: 13, size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    .disabled(!store.canRunTasks)
                }
                .padding(.vertical, 24)
                .frame(maxWidth: .infinity)
            } else {
                VStack(spacing: 8) {
                    ForEach(reports) { report in
                        MacBureauMemoRow(report: report)
                    }
                }
            }
        }
        .bureauDeskCard(padding: 16)
    }
}

/// A memo on the desk (MemoRowView): its glyph, title, tags and line, then Read (or
/// Synthesize, or Follow run) and the web.
private struct MacBureauMemoRow: View {
    let report: MacReport
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        HStack(spacing: 12) {
            MacBureauDeskIcon(report.isComplete ? "file-text" : "file-cog", size: 17)
                .foregroundStyle(report.isComplete ? ink.blue : ink.orange)
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(report.displayTitle)
                        .font(BSHType.bureauSans(13, weight: .semibold))
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .bureauDeskLine(17.55, 13)
                    if store.isReportNew(report) {
                        MacBureauDeskTag(text: "NEW", tint: ink.accent)
                    }
                    ForEach(languages, id: \.self) { lang in
                        Text(lang.uppercased())
                            .font(BSHType.bureauSans(10).monospacedDigit())
                            .foregroundStyle(ink.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .bureauBox(RoundedRectangle(cornerRadius: 3, style: .circular), fill: ink.secondary.opacity(0.12))
                    }
                    MacBureauDeskTag(text: report.statusLabel, tint: statusTone(ink))
                }
                Text("Updated \(report.dateLabel.isEmpty ? "—" : report.dateLabel) · \(report.audience ?? "Internal")")
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .bureauDeskLine(12.5, 10)
            }
            Spacer(minLength: 4)
            action
            Button {
                let url = report.companyId.map { MacConfig.webCompanyMemoURL(companyId: $0, reportId: report.id) }
                    ?? MacConfig.webReportURL(id: report.id)
                MacConfig.openInBrowser(url)
            } label: {
                MacBureauDeskIcon("compass", size: 12)
                    .frame(height: 13.2)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
            .help("Open memo on Web")
        }
        .padding(10)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
        .onDrag {
            NSItemProvider(object: ((report.companyName ?? "Memo") + " - " + report.displayTitle) as NSString)
        }
    }

    /// The documents on file, as language chips.
    private var languages: [String] {
        (report.downloadUrls ?? [:]).keys.filter { $0 == "en" || $0 == "zh" }.sorted()
    }

    private func statusTone(_ ink: MacBureauDeskInk) -> Color {
        if report.isComplete { return report.canOpen ? ink.green : ink.gray }
        if report.isFailed { return ink.red }
        return ink.orange
    }

    @ViewBuilder
    private var action: some View {
        if report.status == "awaiting_studio" {
            Button {
                Task { _ = try? await store.generateReportFromStudio(reportId: report.id) }
            } label: {
                MacBureauDeskButtonLabel(title: "Synthesize Memo", icon: "sparkles", iconSize: 12, size: .small)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small, tint: MacBureauDeskInk(colorScheme).orange))
            .help("Freeze studio cards and synthesize Phase 3 memo")
        } else if report.canOpen {
            Button {
                store.openReportWindow(report)
            } label: {
                MacBureauDeskButtonLabel(title: "Read Memo", icon: "book-open", iconSize: 12, size: .small)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .small))
            .help("Open in its own memo window")
        } else if !report.isComplete && !report.isFailed {
            Button {
                store.showBlotter = true
                store.blotterTab = .jobs
                store.selectedJobId = report.id
            } label: {
                MacBureauDeskButtonLabel(title: "Follow run", icon: "activity", iconSize: 12, size: .small)
            }
            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
            .help("Follow this run in the Jobs blotter")
        }
    }
}

// MARK: - Decision record

/// DecisionsCard: the firm's record for the company — verdict, date, author, the memo it
/// rests on, the explanation and the retrospectives the tracking sync adds. Recording is
/// the ⌘D sheet's.
struct MacBureauDecisionRecordCard: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var confirmDelete: MacDecision?

    private var decisions: [MacDecision] { store.decisionsByCompany[company.id] ?? [] }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 12) {
            MacBureauDeskCardHeader(
                icon: "badge-check",
                title: "Decision record",
                subtitle: store.dealPipelines[company.id]?.stage ?? "Sourced"
            )
            VStack(alignment: .leading, spacing: 10) {
                if decisions.isEmpty {
                    MacBureauWebText.text("No decision on record yet. Press ⌘D to record Invest, Pass or Watch.", size: 11)
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(13.75, 11)
                }
                ForEach(decisions) { decision in
                    row(decision, ink: ink)
                }
            }
        }
        .bureauDeskCard(padding: 16)
        .confirmationDialog(
            "Delete this decision?",
            isPresented: Binding(get: { confirmDelete != nil }, set: { if !$0 { confirmDelete = nil } }),
            presenting: confirmDelete
        ) { decision in
            Button("Delete", role: .destructive) {
                Task { await store.deleteDecision(companyId: company.id, decisionId: decision.id) }
            }
        } message: { decision in
            Text("\(decision.verdictLabel) recorded \(String((decision.decidedAt ?? "").prefix(10))) will be removed from the record.")
        }
        .task(id: company.id) {
            if store.decisionsByCompany[company.id] == nil {
                await store.loadDecisions(for: [company.id])
            }
        }
    }

    private func tint(_ verdict: String, ink: MacBureauDeskInk) -> Color {
        switch verdict.lowercased() {
        case "invest": return ink.green
        case "pass": return ink.red
        default: return ink.orange
        }
    }

    private func row(_ decision: MacDecision, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                MacBureauDeskPill(text: decision.verdictLabel, tint: tint(decision.verdict, ink: ink))
                Text(String((decision.decidedAt ?? decision.createdAt ?? "").prefix(10)))
                    .font(BSHType.bureauSans(10).monospacedDigit())
                    .foregroundStyle(ink.secondary)
                if let by = decision.createdBy, !by.isEmpty {
                    Text("· \(by)")
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.secondary)
                }
                if let rid = decision.reportId, let report = store.report(for: rid) {
                    Button {
                        store.openReportWindow(report)
                    } label: {
                        HStack(spacing: 4) {
                            MacBureauDeskIcon("file-text", size: 12)
                            Text("View memo").font(BSHType.bureauSans(10))
                        }
                        .foregroundStyle(ink.accent)
                    }
                    .buttonStyle(.plain)
                }
                Spacer(minLength: 0)
                Button {
                    confirmDelete = decision
                } label: {
                    MacBureauDeskIcon("trash-2", size: 12)
                        .foregroundStyle(ink.secondary)
                        .padding(2)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!store.canRunTasks)
                .help("Delete decision")
            }
            Text(decision.explanation)
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.label)
                .bureauDeskLine(15.6, 12)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(decision.retrospectives) { retro in
                HStack(alignment: .top, spacing: 6) {
                    MacBureauDeskIcon(
                        retro.verdict == "still_right" ? "circle-check" : (retro.verdict == "looks_wrong" ? "octagon-x" : "circle-question-mark"),
                        size: 14
                    )
                    .foregroundStyle(retro.verdict == "still_right" ? ink.green : (retro.verdict == "looks_wrong" ? ink.red : ink.orange))
                    .padding(.top, 1)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(retro.label) · \(MacTimeFormat.relative(retro.assessedAt))")
                            .font(BSHType.bureauSans(10, weight: .semibold))
                            .foregroundStyle(ink.label)
                        if let text = retro.rationaleEn, !text.isEmpty {
                            Text(text).font(BSHType.bureauSans(10)).foregroundStyle(ink.secondary)
                        }
                        if !retro.newsTitles.isEmpty {
                            Text(retro.newsTitles.prefix(2).joined(separator: " · "))
                                .font(BSHType.bureauSans(10))
                                .foregroundStyle(ink.tertiary)
                                .lineLimit(2)
                        }
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.secondary.opacity(0.05))
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.secondary.opacity(0.04))
    }
}

// MARK: - Files

// MARK: - Deal pipeline

/// DealPipelineCard under Bureau. The state and the saving stay MacDealPipelineView's; this
/// draws them as the website does.
struct MacBureauDealPipelineCard: View {
    typealias Field = MacDealPipelineView.PipelineField

    let company: MacCompany
    let pipeline: MacDealPipeline?
    let stages: [String]
    let currentStage: String
    let loadAttempted: Bool
    let saving: Bool
    let saveError: String?
    let editing: Field?
    @Binding var draft: String
    @Binding var hasDue: Bool
    @Binding var draftDue: Date
    let fieldSaving: Bool
    let canWrite: Bool
    let value: (Field) -> String?
    let reload: () -> Void
    let changeStage: (String) -> Void
    let startEdit: (Field) -> Void
    let saveEdit: () -> Void
    let cancelEdit: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 16) {
            MacBureauDeskCardHeader(
                icon: "waypoints",
                title: "Deal pipeline",
                subtitle: "Stage, intro path, last touchpoint and next step — as recorded by the team."
            ) {
                HStack(spacing: 8) {
                    if let score = pipeline?.warmthScore {
                        MacBureauDeskPill(text: "Warmth \(score)", tint: score >= 80 ? ink.green : ink.orange)
                    }
                    if let lead = pipeline?.dealLead, !lead.isEmpty {
                        HStack(spacing: 4) {
                            MacBureauDeskIcon("circle-user", size: 12)
                            Text(lead)
                                .font(BSHType.bureauSans(11))
                                .bureauDeskLine(13.75, 11)
                        }
                        .foregroundStyle(ink.secondary)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 0) {
                    Text("Stage")
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .foregroundStyle(ink.secondary)
                        .bureauDeskLine(13.75, 11)
                    Spacer(minLength: 0)
                    if let pipeline {
                        Text("\(pipeline.daysInStage) days in \(currentStage)")
                            .font(BSHType.bureauSans(11).monospacedDigit())
                            .foregroundStyle(ink.tertiary)
                            .bureauExactWidth("\(pipeline.daysInStage) days in \(currentStage)", size: 11, mono: true)
                            .bureauDeskLine(13.75, 11)
                    }
                }

                if pipeline == nil && loadAttempted {
                    HStack(spacing: 8) {
                        MacBureauDeskIcon("triangle-alert", size: 14)
                            .foregroundStyle(ink.orange)
                        Text("Couldn't load the deal pipeline.")
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.secondary)
                        Button(action: reload) { MacBureauDeskButtonLabel(title: "Retry", size: .small) }
                            .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    }
                } else if pipeline == nil {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading pipeline…")
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.secondary)
                    }
                } else {
                    MacBureauDeskGrid(columns: 5, spacing: 6) {
                        ForEach(Array(stages.enumerated()), id: \.offset) { index, stage in
                            stageCell(stage, number: index + 1, ink: ink)
                        }
                    }
                    if let saveError {
                        HStack(spacing: 6) {
                            MacBureauDeskIcon("triangle-alert", size: 14)
                            Text(saveError).font(BSHType.bureauSans(11))
                        }
                        .foregroundStyle(ink.red)
                    }
                }
            }

            MacBureauDeskGrid(columns: 3, spacing: 14) {
                ForEach(Field.allCases) { field in
                    tile(field, ink: ink)
                }
            }
        }
        .bureauDeskCard(padding: 16)
    }

    private func index(of stage: String) -> Int { stages.firstIndex(of: stage) ?? 0 }

    private func stageCell(_ stage: String, number: Int, ink: MacBureauDeskInk) -> some View {
        let isCurrent = stage == currentStage
        let isPast = index(of: stage) < index(of: currentStage)
        let tint: Color? = isCurrent ? ink.accent : (isPast ? ink.green : nil)
        return Button {
            changeStage(stage)
        } label: {
            HStack(spacing: 6) {
                ZStack {
                    Circle().fill(tint ?? ink.secondary.opacity(0.2))
                    if isPast {
                        Image(systemName: "checkmark")
                            .font(.system(size: 6.5, weight: .heavy))
                            .foregroundStyle(.white)
                    } else {
                        Text("\(number)")
                            .font(BSHType.bureauSans(10, weight: .bold))
                            .foregroundStyle(isCurrent ? Color.white : ink.secondary)
                            .bureauDeskLine(15, 10)
                    }
                }
                .frame(width: 16, height: 16)
                .bureauSnap(x: .whole)
                Text(stage)
                    .font(BSHType.bureauSans(11, weight: isCurrent ? .bold : .medium))
                    .foregroundStyle(isCurrent ? ink.accent : (isPast ? ink.label : ink.secondary))
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(16.5, 11)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: tint.map { $0.opacity(0.1) } ?? ink.tile)
            .contentShape(Rectangle())
        }
        .buttonStyle(MacBureauFlatButtonStyle())
        .disabled(!canWrite || saving || isCurrent)
        .help(canWrite ? "Move \(company.title) to \(stage)" : "A read-only session cannot change the stage")
    }

    @ViewBuilder
    private func tile(_ field: Field, ink: MacBureauDeskInk) -> some View {
        let isNext = field == .nextStep
        let overdue = isNext && pipeline?.nextStepOverdue == true
        let tint: Color? = isNext ? (overdue ? ink.red : ink.accent) : nil
        let icon = field == .introPath ? "link-2" : (field == .lastTouchpoint ? "message-square" : "calendar-clock")
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                MacBureauDeskIcon(icon, size: 12)
                Text(field.title)
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .bureauDeskLine(13.75, 11)
            }
            .foregroundStyle(tint ?? ink.secondary)

            if editing == field {
                TextField(field.title, text: $draft, axis: .vertical)
                    .textFieldStyle(.dsField)
                    .controlSize(.small)
                    .lineLimit(2...4)
                    .font(BSHType.bureauSans(10))
                    .disabled(fieldSaving)
                    .onSubmit(saveEdit)
                    .onExitCommand(perform: cancelEdit)
                if isNext {
                    HStack(spacing: 6) {
                        Toggle("Due", isOn: $hasDue)
                            .toggleStyle(.checkbox)
                            .font(BSHType.bureauSans(10))
                        if hasDue {
                            DatePicker("", selection: $draftDue, displayedComponents: .date)
                                .labelsHidden()
                                .datePickerStyle(.field)
                                .controlSize(.small)
                        }
                    }
                }
                HStack(spacing: 6) {
                    Button(action: saveEdit) { MacBureauDeskButtonLabel(title: "Save", size: .mini) }
                        .buttonStyle(MacBureauDeskButtonStyle(kind: .prominent, size: .mini))
                        .keyboardShortcut(.defaultAction)
                    Button(action: cancelEdit) { MacBureauDeskButtonLabel(title: "Cancel", size: .mini) }
                        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                    if fieldSaving { ProgressView().controlSize(.mini) }
                }
                .disabled(fieldSaving)
            } else {
                let text = value(field)
                Button {
                    startEdit(field)
                } label: {
                    Text(text ?? field.empty)
                        .font(BSHType.bureauSans(10, weight: field == .introPath ? .semibold : (isNext ? .medium : .regular)))
                        .foregroundStyle(tint ?? (text == nil ? ink.secondary : ink.label))
                        .bureauDeskLine(12.5, 10)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                .disabled(!canWrite || pipeline == nil)
                .help(canWrite ? "Click to edit" : "A read-only session cannot edit the pipeline")

                if isNext, pipeline?.nextStep != nil, let due = pipeline?.nextStepDue {
                    Text(overdue ? "Overdue · was due \(due)" : "Due \(due)")
                        .font(BSHType.bureauSans(10, weight: overdue ? .bold : .regular).monospacedDigit())
                        .foregroundStyle(tint ?? ink.secondary)
                        .bureauDeskLine(12.5, 10)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: tint.map { $0.opacity(0.1) } ?? ink.tile)
    }
}
