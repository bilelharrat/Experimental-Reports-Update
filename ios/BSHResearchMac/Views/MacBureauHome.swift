//
//  MacBureauHome.swift
//  BSHResearchMac
//
//  Bureau's Home opens as the website's does (HomeView.vue, bureau.css "Home: a title
//  page"): the date in brass capitals, "Find a Company" set large in Instrument Serif, a
//  line of help, the search plate with its three intake actions, and the live tape of the
//  companies you follow; then the companies you opened last and the ones you starred.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// The title page at the head of Bureau's Home.
struct MacBureauHomeHero: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @Binding var query: String
    let hits: [MacAutocompleteHit]
    let searching: Bool
    let open: (MacAutocompleteHit) -> Void
    @FocusState private var focused: Bool

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var dateline: String {
        Date().formatted(.dateTime.weekday(.wide).month(.wide).day()).uppercased()
    }

    var body: some View {
        VStack(spacing: 0) {
            // The dateline, in brass capitals.
            Text(dateline)
                .font(BSHType.bureauSans(11, weight: .semibold))
                .tracking(2.2)
                .foregroundStyle(ink.accentInk)
                .bureauLines(16.5, size: 11)

            // line-height 0.98: the glyphs stand out of their line, as CSS lets them.
            Text("Find a Company")
                .font(.custom(BSHType.bureauSerif, size: 88))
                .tracking(-0.88)
                .foregroundStyle(ink.ink)
                .lineLimit(1)
                .fixedSize()
                .frame(height: 86.24)
                .padding(.top, 8)

            // The website balances the two lines (text-wrap: balance); this width breaks
            // them where it does.
            Text("Search or add a company. Names you already follow appear as you type.")
                .font(BSHType.bureauSans(15))
                .foregroundStyle(ink.muted)
                .multilineTextAlignment(.center)
                // Blink rounds each baseline to a whole point, and here the two lines of
                // the 20.625pt leading land 20pt apart; the paragraph keeps its height.
                .lineSpacing(1)
                .bureauLines(20.625, size: 15)
                .padding(.bottom, 0.625)
                .frame(maxWidth: 262)
                .frame(maxWidth: 448)
                // Its box starts at 254.73pt, where Blink rounds the baseline down to a
                // whole 270; SwiftUI snaps the box to 254.5. Start it on the point instead.
                .padding(.top, 12.26)
                .padding(.bottom, -0.26)
        }
        .frame(maxWidth: 672)
        .padding(.top, 80)
        .padding(.bottom, 32)

        searchPlate
            .frame(maxWidth: 768)
            .macWelcomeTourAnchor(MacWelcomeTourCatalog.bureauHomeSearchAnchor)
            .zIndex(1)

        MacBureauLiveTape()
            .frame(maxWidth: 768)
            .padding(.top, 16)
    }

    // MARK: Search plate

    private var ready: Bool { !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    private var searchPlate: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .leading) {
                LucideIcon("search", size: 16)
                    .foregroundStyle(ink.muted)
                    .padding(.leading, 14)
                TextField("", text: $query, prompt: Text("Search or add a company…").foregroundStyle(ink.subtle))
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(15))
                    .tracking(-0.33)
                    .foregroundStyle(ink.ink)
                    .focused($focused)
                    .padding(.leading, 40)
                    .padding(.trailing, 48)
                    .onSubmit(submit)
                    .onExitCommand { query = "" }
                HStack {
                    Spacer()
                    Button(action: submit) {
                        LucideIcon("arrow-right", size: 14)
                            .foregroundStyle(ready ? Color.white : ink.subtle)
                            .frame(width: 28, height: 28)
                            .background(Circle().fill(ready ? ink.accent : .clear))
                            .shadow(color: ready ? Color.bshFixed(BSHRGB(148, 112, 47), opacity: 0.5) : .clear, radius: 5, y: 3)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .help("Search")
                    .padding(.trailing, 6)
                }
            }
            .frame(height: 38)

            // The three intake actions, ruled off below the field.
            HStack(spacing: 4) {
                intake("Link", icon: "link", tone: ink.accent) { openWebIntake("link") }
                intake("File", icon: "upload", tone: ink.info) { pickDeck() }
                intake("Note", icon: "scroll-text", tone: ink.warning) { openWebIntake("note") }
            }
            .frame(height: 24)
            .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
        }
        .padding(6)
        .background {
            RoundedRectangle(cornerRadius: 20, style: .circular)
                .fill(ink.raised)
                .shadow(color: ink.shadow(0.45 * 0.55), radius: 13, y: 12)
        }
        .overlay {
            // material-glass: a hairline of ink; focused, a brass edge and its glow.
            RoundedRectangle(cornerRadius: 20, style: .circular)
                .inset(by: -0.5)
                .stroke(focused ? ink.accent : ink.ink(0.1), lineWidth: 1)
            if focused {
                RoundedRectangle(cornerRadius: 20, style: .circular)
                    .inset(by: -2.5)
                    .stroke(ink.accentGlow(0.2), lineWidth: 4)
                    .padding(-0.5)
                    .allowsHitTesting(false)
            }
        }
        .overlay(alignment: .top) {
            if ready && (searching || !hits.isEmpty) {
                suggestions
                    .offset(y: 74 + 8)
            }
        }
        .onAppear { focused = true }
    }

    private func intake(_ title: String, icon: String, tone: Color, action: @escaping () -> Void) -> some View {
        MacBureauIntakeButton(title: title, icon: icon, tone: tone, ink: ink, action: action)
    }

    /// The website's suggestions menu: fresh paper over the page.
    private var suggestions: some View {
        VStack(alignment: .leading, spacing: 0) {
            if searching && hits.isEmpty {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Searching…").font(BSHType.bureauSans(14)).foregroundStyle(ink.muted)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            ForEach(hits.prefix(6)) { hit in
                MacBureauSuggestionRow(hit: hit, ink: ink) { open(hit) }
            }
        }
        .padding(6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 18, style: .circular).fill(ink.raised))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .circular).inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1))
        .shadow(color: .black.opacity(colorScheme == .dark ? 0.5 : 0.18), radius: 16, y: 12)
    }

    private func submit() {
        if let first = hits.first {
            open(first)
        } else if ready {
            store.openCommandPalette(seed: query)
        }
    }

    /// Link and Note are the website's own intake tools; the Mac opens them in the
    /// research browser beside the page.
    private func openWebIntake(_ kind: String) {
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(MacConfig.webURL(path: "", query: ["intake": kind]))
        }
    }

    /// File: a pitch deck or memo input, filed into the pipeline as the Mac files decks.
    private func pickDeck() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [
            .pdf,
            UTType("org.openxmlformats.presentationml.presentation"),
            UTType("com.microsoft.powerpoint.ppt"),
        ].compactMap { $0 }
        if panel.runModal() == .OK, let url = panel.url {
            store.ingestDeck(url: url)
        }
    }
}

/// One of the search plate's intake actions: a glyph in its tone and a label.
private struct MacBureauIntakeButton: View {
    let title: String
    let icon: String
    let tone: Color
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                LucideIcon(icon, size: 14).foregroundStyle(tone)
                Text(title)
                    .font(BSHType.bureauSans(12, weight: .medium))
                    .tracking(-0.072)
            }
            .foregroundStyle(hovered ? ink.ink : ink.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// A suggestion under the search plate: the company's mark, name and what it is.
private struct MacBureauSuggestionRow: View {
    let hit: MacAutocompleteHit
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                MacMonogram(name: hit.name ?? hit.ticker ?? "?", ticker: hit.ticker, companyId: hit.companyId, size: 32)
                VStack(alignment: .leading, spacing: 1) {
                    Text(hit.displayTitle)
                        .font(BSHType.bureauSans(14, weight: .medium))
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                    HStack(spacing: 4) {
                        if let ticker = hit.ticker, !ticker.isEmpty {
                            Text(ticker.uppercased())
                                .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                        }
                        Text(hit.displaySubtitle).lineLimit(1)
                    }
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                }
                Spacer(minLength: 8)
                LucideIcon("arrow-right", size: 14).foregroundStyle(ink.subtle)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(hovered ? ink.accent.opacity(0.08) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// The live tape (LiveTickerTape.vue): the listed companies you follow, each with its
/// last price and day's move, on one hairline strip that fades out at its end.
struct MacBureauLiveTape: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private struct Item: Identifiable {
        let ticker: String
        let quote: MacQuote?
        var id: String { ticker }
    }

    private var items: [Item] {
        var seen = Set<String>()
        return store.companies.compactMap { company -> Item? in
            guard let ticker = company.ticker?.uppercased(), !ticker.isEmpty, seen.insert(ticker).inserted else { return nil }
            return Item(ticker: ticker, quote: store.watchlist.first { $0.ticker.uppercased() == ticker })
        }
    }

    var body: some View {
        let items = items
        if !items.isEmpty {
            HStack(spacing: 0) {
                HStack(spacing: 6) {
                    Circle().fill(ink.success).frame(width: 6, height: 6)
                    Text("Live")
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                }
                .padding(.leading, 4)
                .padding(.trailing, 12)

                ScrollView(.horizontal, showsIndicators: false) {
                    TimelineView(.periodic(from: .now, by: 30)) { context in
                        HStack(spacing: 4) {
                            ForEach(items) { item in
                                MacBureauTapeItem(ticker: item.ticker, quote: item.quote, fetchedAt: store.watchlistFetchedAt, now: context.date, ink: ink) {
                                    store.showTicker(item.ticker)
                                }
                            }
                        }
                    }
                    .padding(.leading, 6)
                    .padding(.trailing, 24)
                }
                .mask {
                    HStack(spacing: 0) {
                        Color.black
                        LinearGradient(colors: [.black, .clear], startPoint: .leading, endPoint: .trailing).frame(width: 40)
                    }
                }
                .overlay(alignment: .leading) { Rectangle().fill(ink.ink(0.08)).frame(width: 1) }
            }
            .padding(.vertical, 6)
            .padding(.leading, 10)
            .frame(height: 36)
            .background(RoundedRectangle(cornerRadius: 14, style: .circular).fill(ink.tray.opacity(0.8)))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(ink.ink(0.035), lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        }
    }
}

/// The website's quote labels (`liveTicker.js`): `lastPriceLabel` is dollars, grouped, at most
/// two decimals; `signedChange` is one decimal with a plus only above zero.
enum MacBureauQuoteText {
    private static let price: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.minimumFractionDigits = 0
        f.maximumFractionDigits = 2
        return f
    }()

    static func price(_ value: Double) -> String {
        "$" + (price.string(from: NSNumber(value: value)) ?? String(value))
    }

    static func change(_ pct: Double) -> String {
        (pct > 0 ? "+" : "") + String(format: "%.1f%%", pct)
    }
}

private struct MacBureauTapeItem: View {
    let ticker: String
    let quote: MacQuote?
    let fetchedAt: Date?
    let now: Date
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    /// The website's `quoteStaleness` read out: fresh quotes say how old they are, and past
    /// twenty minutes the tape calls them stale.
    private var ageHint: (text: String, stale: Bool)? {
        guard let fetchedAt else { return nil }
        let minutes = max(0, Int((now.timeIntervalSince(fetchedAt) / 60).rounded()))
        if minutes >= 20 { return ("Stale \(minutes)m", true) }
        if minutes < 1 { return ("just now", false) }
        return ("\(minutes)m ago", false)
    }

    var body: some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(ticker)
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.ink)
                if let last = quote?.last {
                    Text(MacBureauQuoteText.price(last))
                        .font(BSHType.bureauSans(12).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(ink.secondary)
                }
                if let pct = quote?.pct {
                    Text(MacBureauQuoteText.change(pct))
                        .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(pct >= 0 ? ink.success : ink.danger)
                } else {
                    Text("Waiting")
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.subtle)
                }
                if quote?.last != nil, let hint = ageHint {
                    Text(hint.text)
                        .font(BSHType.bureauSans(10))
                        .tracking(0.12)
                        .foregroundStyle(hint.stale ? ink.warningInk : ink.subtle)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(ticker)
    }
}

// MARK: - Recent and Tracked

/// Below the title page, as on the website: the companies you opened last and the ones you
/// starred, each a grid of company cards under a serif heading.
struct MacBureauHomeSections: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var recentExpanded = true
    @State private var trackedExpanded = true

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    /// The website ranks by how often a company was opened; the Mac keeps when it was
    /// last opened, so the most recent come first.
    private var recent: [MacCompany] {
        let visits = store.visitedCompanyTimestamps
        return store.companies
            .filter { visits[$0.id] != nil }
            .sorted { (visits[$0.id] ?? .distantPast) > (visits[$1.id] ?? .distantPast) }
            .prefix(8)
            .map { $0 }
    }

    private var tracked: [MacCompany] {
        let ids = Set(store.validFollowedIds)
        return store.companies.filter { ids.contains($0.id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !recent.isEmpty {
                section(
                    title: "Recent",
                    hint: "Recently opened companies from this workspace.",
                    companies: recent,
                    expanded: $recentExpanded
                )
                .padding(.top, 56)
            }
            if !tracked.isEmpty {
                section(
                    title: "Tracked",
                    hint: "Companies you starred for ongoing monitoring.",
                    companies: tracked,
                    expanded: $trackedExpanded
                )
                .padding(.top, recent.isEmpty ? 56 : 48)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func section(title: String, hint: String, companies: [MacCompany], expanded: Binding<Bool>) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.custom(BSHType.bureauSerif, size: 23))
                        .tracking(-0.23)
                        .foregroundStyle(ink.ink)
                        .frame(height: 28)
                    Text(hint)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .frame(height: 16)
                }
                Spacer(minLength: 8)
                MacBureauPlainButton(title: expanded.wrappedValue ? "Show less" : "Show more", icon: expanded.wrappedValue ? "chevron-up" : "chevron-down", ink: ink) {
                    withAnimation(.easeInOut(duration: 0.2)) { expanded.wrappedValue.toggle() }
                }
            }
            if expanded.wrappedValue {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12, alignment: .top), count: 4), alignment: .leading, spacing: 12) {
                    ForEach(companies) { company in
                        MacBureauCompanyCard(company: company, ink: ink)
                    }
                }
            }
        }
    }
}

/// `btn-plain btn-sm`: brass ink, underlined on hover.
private struct MacBureauPlainButton: View {
    let title: String
    let icon: String
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4.8) {
                Text(title)
                    .font(BSHType.bureauSans(12, weight: .medium))
                    .tracking(-0.072)
                    .underline(hovered)
                LucideIcon(icon, size: 14)
            }
            .foregroundStyle(ink.accentInk)
            .padding(.horizontal, 11.2)
            .frame(height: 26)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// CompanyBoardCard.vue: a tray with the company's mark, name and what it is, and along
/// its foot the ticker, last price and the day's move.
private struct MacBureauCompanyCard: View {
    @EnvironmentObject private var store: MacAppStore
    let company: MacCompany
    let ink: MacBureauPageInk
    @State private var hovered = false

    private var quote: MacQuote? {
        guard let ticker = company.ticker?.uppercased(), !ticker.isEmpty else { return nil }
        return store.watchlist.first { $0.ticker.uppercased() == ticker }
    }

    private var followed: Bool { store.isFollowed(company.id) }

    var body: some View {
        Button {
            store.openCompanyPage(company)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 12) {
                    MacAvatar(company: company, size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(company.name ?? company.id)
                            .font(BSHType.bureauSans(14, weight: .semibold))
                            .tracking(-0.084)
                            .foregroundStyle(ink.ink)
                            .lineLimit(1)
                            .frame(height: 20)
                        Text(company.bureauStatusLine ?? "Status pending")
                            .font(BSHType.bureauSans(12))
                            .foregroundStyle(ink.muted)
                            .lineLimit(2)
                            .bureauLines(16.5, size: 12)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.trailing, 28)
                Spacer(minLength: 12)
                if let ticker = company.ticker, !ticker.isEmpty {
                    HStack(spacing: 8) {
                        Text(ticker.uppercased())
                            .font(BSHType.bureauSans(11, weight: .semibold))
                            .tracking(0.275)
                            .foregroundStyle(ink.secondary)
                            .lineLimit(1)
                            .fixedSize()
                        Spacer(minLength: 0)
                        if let last = quote?.last {
                            Text(MacBureauQuoteText.price(last))
                                .font(BSHType.bureauSans(14, weight: .medium).monospacedDigit())
                                .tracking(-0.14)
                                .foregroundStyle(ink.ink)
                                .lineLimit(1)
                                .fixedSize()
                        }
                        if let quote, let pct = quote.pct {
                            Text(MacBureauQuoteText.change(pct))
                                .font(BSHType.bureauSans(11, weight: .semibold).monospacedDigit())
                                .tracking(0.066)
                                .lineLimit(1)
                                .fixedSize()
                                .foregroundStyle(quote.isUp ? Color.bshFixed(BSHRGB(22, 104, 63)) : Color.bshFixed(BSHRGB(162, 42, 30)))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill((quote.isUp ? ink.success : ink.danger).opacity(0.13)))
                        }
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: 14, style: .circular).fill(ink.tray))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(hovered ? ink.accent.opacity(0.38) : ink.ink(0.035), lineWidth: 1))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .overlay(alignment: .topTrailing) {
            if followed || hovered {
                Button {
                    Task { await store.toggleFollow(company.id) }
                } label: {
                    LucideIcon(followed ? "star-fill" : "star", size: 16)
                        .foregroundStyle(followed ? Color.bshFixed(BSHRGB(204, 160, 20)) : ink.ink(0.66))
                        .frame(width: 28, height: 28)
                        .background(Circle().fill(followed ? ink.ink(0.08) : .clear))
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .help(followed ? "Unfollow" : "Follow")
                .padding(8)
            }
        }
    }
}
