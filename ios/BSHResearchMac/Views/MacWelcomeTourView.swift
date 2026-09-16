//
//  MacWelcomeTourView.swift
//  BSHResearchMac
//
//  The first-launch walkthrough. The welcome card introduces the terminal;
//  every step after it selects the real desk it is describing and rings the
//  real sidebar row, the way Apple's in-app tours walk you through the
//  interface rather than describing it from behind a modal.
//

import SwiftUI

// MARK: - Anchoring

/// Where the real chrome is, in window coordinates.
///
/// The sidebar is a `List`, and preferences do not propagate out of List rows
/// dependably on macOS, so anchors are reported by geometry callback instead of
/// `anchorPreference`. That works the same for a List row, a toolbar button or
/// anything else that can hold a background.
@MainActor
final class MacTourAnchorStore: ObservableObject {
    @Published private(set) var frames: [String: CGRect] = [:]

    /// Called from layout, so the write is deferred to the next runloop turn.
    func report(_ id: String, _ frame: CGRect) {
        guard frames[id] != frame else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self, self.frames[id] != frame else { return }
            self.frames[id] = frame
        }
    }
}

private struct MacTourAnchorReporter: ViewModifier {
    let id: String
    @EnvironmentObject private var anchors: MacTourAnchorStore

    func body(content: Content) -> some View {
        content.background {
            GeometryReader { geo in
                Color.clear
                    .onAppear { anchors.report(id, geo.frame(in: .global)) }
                    .onChange(of: geo.frame(in: .global)) { _, frame in
                        anchors.report(id, frame)
                    }
            }
        }
    }
}

extension View {
    /// Mark this view as something the welcome tour can spotlight.
    func macWelcomeTourAnchor(_ id: String) -> some View {
        modifier(MacTourAnchorReporter(id: id))
    }

    /// Hang the tour over the window, converting reported window frames into
    /// this view's own space.
    func macWelcomeTourOverlay() -> some View {
        overlay {
            GeometryReader { proxy in
                MacWelcomeTourFrame(origin: proxy.frame(in: .global).origin, container: proxy.size)
            }
        }
    }
}

/// Resolves reported window frames against the overlay's own origin.
private struct MacWelcomeTourFrame: View {
    let origin: CGPoint
    let container: CGSize

    @EnvironmentObject private var anchors: MacTourAnchorStore

    var body: some View {
        MacWelcomeTourView(
            spotlight: { id in
                guard let frame = anchors.frames[id] else { return nil }
                return frame.offsetBy(dx: -origin.x, dy: -origin.y)
            },
            container: container
        )
    }
}

private extension View {
    /// Punch `mask` out of this view — the dim everywhere but the control.
    @ViewBuilder
    func cutOut<Mask: View>(@ViewBuilder _ mask: () -> Mask) -> some View {
        self.mask {
            Rectangle()
                .overlay { mask().blendMode(.destinationOut) }
                .compositingGroup()
        }
    }
}

// MARK: - Overlay

struct MacWelcomeTourView: View {
    var spotlight: (String) -> CGRect? = { _ in nil }
    var container: CGSize = .zero

    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var calloutSize: CGSize = .zero

    private var pages: [MacWelcomeTourPage] { MacWelcomeTourCatalog.pages }
    private var page: MacWelcomeTourPage { pages[min(max(0, store.welcomeTourStep), pages.count - 1)] }
    private var isFirst: Bool { store.welcomeTourStep == 0 }
    private var isLast: Bool { store.welcomeTourStep >= pages.count - 1 }

    /// Light on purpose: the desk underneath is the thing being explained.
    private var dimOpacity: Double { colorScheme == .dark ? 0.26 : 0.16 }
    private var flatDimOpacity: Double { colorScheme == .dark ? 0.34 : 0.24 }

    private var halo: CGRect? {
        guard !page.isHero, let id = page.anchor, let rect = spotlight(id) else { return nil }
        guard rect.width > 0, rect.height > 0 else { return nil }
        return rect.insetBy(dx: -6, dy: -4)
    }

    var body: some View {
        if store.showWelcomeTour {
            ZStack(alignment: .topLeading) {
                dim
                if let halo {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Color.accentColor, lineWidth: 2)
                        .frame(width: halo.width, height: halo.height)
                        .position(x: halo.midX, y: halo.midY)
                        .shadow(color: Color.accentColor.opacity(0.5), radius: 10)
                        .allowsHitTesting(false)
                }

                callout
                    .frame(width: calloutWidth)
                    .background {
                        GeometryReader { geo in
                            Color.clear
                                .onAppear { calloutSize = geo.size }
                                .onChange(of: geo.size) { _, size in calloutSize = size }
                        }
                    }
                    .offset(x: calloutOrigin.x, y: calloutOrigin.y)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .animation(reduceMotion ? nil : .spring(response: 0.4, dampingFraction: 0.86), value: store.welcomeTourStep)
            .background {
                // Esc leaves the tour, like the command palette.
                Button("") { store.completeWelcomeTour() }
                    .keyboardShortcut(.cancelAction)
                    .frame(width: 0, height: 0)
                    .opacity(0)
            }
            .accessibilityIdentifier("welcome-tour")
        }
    }

    // MARK: Dim

    @ViewBuilder
    private var dim: some View {
        let base = Rectangle().fill(Color.black.opacity(halo == nil ? flatDimOpacity : dimOpacity))
        Group {
            if let halo {
                base.cutOut {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .frame(width: halo.width, height: halo.height)
                        .position(x: halo.midX, y: halo.midY)
                }
            } else {
                base
            }
        }
        .contentShape(Rectangle())
        .onTapGesture { if !page.isHero { advance() } }
        .accessibilityHidden(true)
    }

    // MARK: Callout

    private var calloutWidth: CGFloat {
        let maximum = max(280, container.width - 48)
        return page.isHero ? min(520, maximum) : min(420, maximum)
    }

    /// Beside the row it is describing, centred when there is nothing to point at.
    private var calloutOrigin: CGPoint {
        let width = calloutWidth
        let height = calloutSize.height > 0 ? calloutSize.height : 320
        let margin: CGFloat = 20

        guard let halo else {
            return CGPoint(
                x: max(margin, (container.width - width) / 2),
                y: max(margin, (container.height - height) / 2)
            )
        }

        // Sidebar rows sit at the left edge, so the callout goes to their right.
        let toRight = halo.maxX + 18
        let x = toRight + width + margin <= container.width
            ? toRight
            : max(margin, halo.minX - width - 18)
        let y = min(
            max(margin, halo.midY - height / 2),
            max(margin, container.height - height - margin)
        )
        return CGPoint(x: x, y: y)
    }

    private var callout: some View {
        VStack(alignment: .leading, spacing: 0) {
            if page.isHero {
                heroContent
            } else {
                stepContent
            }
            footer
        }
        .padding(page.isHero ? 28 : 18)
        .appleGlassCard(cornerRadius: 18)
        .shadow(color: Color.black.opacity(0.3), radius: 28, y: 12)
    }

    private var heroContent: some View {
        VStack(spacing: 0) {
            BSHBrandTile(size: 76, cornerRadius: 18)
                .padding(.bottom, 16)

            Text(page.title)
                .font(.system(size: 24, weight: .bold))
                .multilineTextAlignment(.center)
                .accessibilityIdentifier("welcome-tour-title")

            Text(page.body)
                .font(.system(size: 12.5))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 13) {
                ForEach(MacWelcomeTourCatalog.rows) { row in
                    HStack(alignment: .top, spacing: 12) {
                        rowIcon(row)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.title).font(.system(size: 13, weight: .semibold))
                            Text(row.body)
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 8)
                        MacTourKeyCaps(keys: row.keys)
                    }
                }
            }
            .padding(.top, 22)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var stepContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                glyph(page)
                VStack(alignment: .leading, spacing: 3) {
                    Text(page.title)
                        .font(.system(size: 16, weight: .semibold))
                        .accessibilityIdentifier("welcome-tour-title")
                    Text(page.body)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }

            VStack(spacing: 6) {
                ForEach(page.tips) { tip in
                    HStack(spacing: 10) {
                        Image(systemName: tip.symbol)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(Color.accentColor)
                            .frame(width: 16)
                        Text(tip.text)
                            .font(.system(size: 12))
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        MacTourKeyCaps(keys: tip.keys)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .appleGlassTile(cornerRadius: 9)
                }
            }
        }
    }

    @ViewBuilder
    private func glyph(_ entry: MacWelcomeTourPage) -> some View {
        if entry.usesWarrenPortrait {
            WarrenMarkView(size: 42)
        } else {
            Image(systemName: entry.symbol)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 42, height: 42)
                .background(
                    Color.accentColor.opacity(colorScheme == .dark ? 0.18 : 0.12),
                    in: RoundedRectangle(cornerRadius: 11, style: .continuous)
                )
        }
    }

    @ViewBuilder
    private func rowIcon(_ row: MacWelcomeTourRow) -> some View {
        if row.usesWarrenPortrait {
            WarrenMarkView(size: 32)
        } else {
            Image(systemName: row.symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 32, height: 32)
                .background(
                    Color.accentColor.opacity(colorScheme == .dark ? 0.18 : 0.12),
                    in: RoundedRectangle(cornerRadius: 9, style: .continuous)
                )
        }
    }

    // MARK: Footer

    private var footer: some View {
        VStack(spacing: 12) {
            HStack(spacing: 6) {
                ForEach(pages.indices, id: \.self) { index in
                    Circle()
                        .fill(index == store.welcomeTourStep ? Color.accentColor : Color.primary.opacity(0.18))
                        .frame(width: 6, height: 6)
                }
            }

            HStack(spacing: 10) {
                if !isFirst {
                    Button("Back") { store.welcomeTourStep -= 1 }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color.accentColor)
                        .accessibilityIdentifier("welcome-tour-back")
                } else if !isLast {
                    Button("Skip") { store.completeWelcomeTour() }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("welcome-tour-skip")
                }

                Spacer(minLength: 0)

                Button(isLast ? "Get started" : "Continue") { advance() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
                    .keyboardShortcut(.defaultAction)
                    .accessibilityIdentifier("welcome-tour-next")
            }

            if page.isHero {
                Text("Replay this tour any time from Settings.")
                    .font(.system(size: 11))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.top, 16)
    }

    private func advance() {
        if isLast {
            store.completeWelcomeTour()
        } else {
            store.welcomeTourStep += 1
        }
    }
}

// MARK: - Key caps

/// The shortcut for a row or tip, styled like the shortcut sheet's caps.
struct MacTourKeyCaps: View {
    let keys: [String]

    var body: some View {
        if !keys.isEmpty {
            HStack(spacing: 3) {
                ForEach(keys, id: \.self) { key in
                    Text(key)
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.primary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .appleGlassTile(cornerRadius: 4)
                }
            }
            .accessibilityHidden(true)
        }
    }
}

// MARK: - Catalog

struct MacWelcomeTourRow: Identifiable {
    let id: String
    let symbol: String
    let title: String
    let body: String
    var keys: [String] = []
    var usesWarrenPortrait: Bool { id == "warren" }
}

struct MacWelcomeTourTip: Identifiable {
    let text: String
    let symbol: String
    var keys: [String] = []
    var id: String { text }
}

struct MacWelcomeTourPage: Identifiable {
    let id: String
    let symbol: String
    let title: String
    let body: String
    var tips: [MacWelcomeTourTip] = []
    /// The desk this step is about. `nil` leaves the terminal where it is.
    var tab: MacTab? = nil
    /// Id of the chrome to ring, published by `macWelcomeTourAnchor`.
    var anchor: String? = nil
    var isHero: Bool { id == "welcome" }
    var usesWarrenPortrait: Bool { id == "warren" }
}

enum MacWelcomeTourCatalog {
    /// Anchor id for a desk's row in the sidebar.
    static func tabAnchor(_ tab: MacTab) -> String { "tab.\(tab.rawValue)" }
    /// Anchor id for the command-line button in the toolbar.
    static let commandAnchor = "chrome.command"

    static let rows: [MacWelcomeTourRow] = [
        MacWelcomeTourRow(id: "attention", symbol: "bell.badge", title: "Attention queue",
                          body: "What needs you today: stale coverage, drawdowns, unfiled uploads.", keys: ["⌘", "0"]),
        MacWelcomeTourRow(id: "pipeline", symbol: "list.bullet.rectangle.portrait", title: "Pipeline",
                          body: "The deal board with every stage, decision and running job.", keys: ["⌘", "2"]),
        MacWelcomeTourRow(id: "research", symbol: "building.columns", title: "Research Desk",
                          body: "Dossiers, thesis tracker and IC room for every company.", keys: ["⌘", "3"]),
        MacWelcomeTourRow(id: "documents", symbol: "doc.text.magnifyingglass", title: "Documents",
                          body: "Memos, files and transcripts in a native viewer.", keys: ["⌘", "4"]),
        MacWelcomeTourRow(id: "warren", symbol: "bubble.left.and.bubble.right.fill", title: "Ask Warren",
                          body: "The research assistant who sees what's on your desk.", keys: ["⌘", "9"]),
    ]

    static let pages: [MacWelcomeTourPage] = [
        MacWelcomeTourPage(
            id: "welcome", symbol: "",
            title: "Welcome to BSH Research",
            body: "The institutional terminal: pipeline, dossiers, memos, markets and Warren, with a keyboard shortcut for everything. Here's a quick tour."
        ),
        MacWelcomeTourPage(
            id: "command", symbol: "terminal.fill",
            title: "The command line",
            body: "Press ⌘K from anywhere. Type a company name and a code: MEMO starts a memo run, DES opens the dossier, GP records a decision, N adds a note, NEW adds a company and ASK hands the company to Warren.",
            tips: [
                MacWelcomeTourTip(text: "Jump to any desk, company or ticker by name.", symbol: "magnifyingglass", keys: ["⌘", "K"]),
                MacWelcomeTourTip(text: "Deep Search with Claude for a name that isn't in the pipeline yet.", symbol: "sparkles", keys: ["⌘", "⏎"]),
                MacWelcomeTourTip(text: "Every shortcut, on one sheet.", symbol: "keyboard", keys: ["⌘", "/"]),
            ],
            anchor: commandAnchor
        ),
        MacWelcomeTourPage(
            id: "attention", symbol: "bell.badge",
            title: "Start the day at Attention",
            body: "The Attention queue is what changed since your last launch: coverage that went stale, holdings in drawdown, decks waiting to be filed and jobs that need a look.",
            tips: [
                MacWelcomeTourTip(text: "Open the queue.", symbol: "bell.badge", keys: ["⌘", "0"]),
                MacWelcomeTourTip(text: "Refresh keeps comparing against the previous launch, so nothing slips.", symbol: "arrow.clockwise", keys: ["⌘", "R"]),
                MacWelcomeTourTip(text: "Drop a pitch deck on the window to file it into the pipeline.", symbol: "arrow.down.doc"),
            ],
            tab: .attention,
            anchor: tabAnchor(.attention)
        ),
        MacWelcomeTourPage(
            id: "pipeline", symbol: "building.columns",
            title: "Pipeline and the Research Desk",
            body: "The Pipeline board is every deal with its stage and latest decision. Select a company and the Research Desk opens its dossier: profile, files, thesis tracker and IC room.",
            tips: [
                MacWelcomeTourTip(text: "Pipeline board.", symbol: "list.bullet.rectangle.portrait", keys: ["⌘", "2"]),
                MacWelcomeTourTip(text: "Research Desk.", symbol: "building.columns", keys: ["⌘", "3"]),
                MacWelcomeTourTip(text: "Record a decision: Invest, Pass or Watch.", symbol: "checkmark.seal", keys: ["⌘", "D"]),
                MacWelcomeTourTip(text: "IC Review window: memo, thesis and the decision form side by side.", symbol: "rectangle.split.3x1", keys: ["⇧", "⌘", "O"]),
            ],
            tab: .pipeline,
            anchor: tabAnchor(.pipeline)
        ),
        MacWelcomeTourPage(
            id: "memo", symbol: "doc.text.magnifyingglass",
            title: "Memos and Documents",
            body: "Start an investment memo run for the selected company. Finished memos, files and transcripts live on the Documents desk, and any memo can open in its own window.",
            tips: [
                MacWelcomeTourTip(text: "New investment memo run.", symbol: "doc.badge.plus", keys: ["⌘", "N"]),
                MacWelcomeTourTip(text: "Documents desk.", symbol: "doc.text.magnifyingglass", keys: ["⌘", "4"]),
                MacWelcomeTourTip(text: "The Jobs & Alerts blotter follows every run.", symbol: "tray.full", keys: ["⌥", "⌘", "J"]),
            ],
            tab: .documents,
            anchor: tabAnchor(.documents)
        ),
        MacWelcomeTourPage(
            id: "markets", symbol: "chart.line.uptrend.xyaxis",
            title: "Markets, News, Pulse and Portfolio",
            body: "Market Radar has native quote charts and your watchlists, synced with the web, iPhone and iPad. News follows the tape, Pulse is the market brief, and Portfolio & Watch holds holdings, runway and marks.",
            tips: [
                MacWelcomeTourTip(text: "Market Radar.", symbol: "chart.line.uptrend.xyaxis", keys: ["⌘", "5"]),
                MacWelcomeTourTip(text: "News Desk.", symbol: "newspaper", keys: ["⌘", "6"]),
                MacWelcomeTourTip(text: "Market Pulse.", symbol: "waveform.path.ecg", keys: ["⌘", "7"]),
                MacWelcomeTourTip(text: "Portfolio & Watch.", symbol: "briefcase.fill", keys: ["⌘", "8"]),
            ],
            tab: .market,
            anchor: tabAnchor(.market)
        ),
        MacWelcomeTourPage(
            id: "warren", symbol: "",
            title: "Meet Warren",
            body: "Warren is the research assistant built into the terminal. He reads the selected company, its memo and its files, and answers with citations. Firm memory search finds anything the firm has ever written.",
            tips: [
                MacWelcomeTourTip(text: "Ask Warren desk.", symbol: "bubble.left.and.bubble.right.fill", keys: ["⌘", "9"]),
                MacWelcomeTourTip(text: "Toggle the Ask Warren side panel next to any desk.", symbol: "sidebar.right", keys: ["⌥", "⌘", "C"]),
                MacWelcomeTourTip(text: "Firm memory search.", symbol: "brain.head.profile", keys: ["⇧", "⌘", "F"]),
                MacWelcomeTourTip(text: "He answers to his name. Just say Warren.", symbol: "quote.bubble"),
            ],
            tab: .copilot,
            anchor: tabAnchor(.copilot)
        ),
    ]
}
