//
//  MacBureauCommandPalette.swift
//  BSHResearchMac
//
//  The command palette under Bureau, drawn as the website draws it (MarketCommandPalette.vue,
//  the `.yf-cmd-*` rules in style.css and bureau.css) and at its measurements: the desk dimmed
//  by a scrim, and high over it a sheet of fresh paper 640pt wide, 14% of the window down.
//  The search line with its "esc" key, the rows (a ⌘ tile or the company's mark, the title, the
//  subtitle, a return glyph on the chosen row) and the hint along the foot. The row under the
//  cursor is lifted paper with a brass edge. It runs the website's command line
//  (MacBureauMarketCommands.swift) and takes each command to the Mac's own desk for it.
//
//  Summit Glass and Folio keep the Mac's palette (MacCommandPalette) in its sheet.
//

import AppKit
import SwiftUI

// MARK: - Presentation

extension View {
    /// The command palette: under Bureau the website's, over the whole window; under Summit
    /// Glass and Folio the Mac's own, in a sheet.
    func macCommandPalette(isPresented: Binding<Bool>) -> some View {
        modifier(MacCommandPalettePresentation(isPresented: isPresented))
    }
}

private struct MacCommandPalettePresentation: ViewModifier {
    @EnvironmentObject private var store: MacAppStore
    @Binding var isPresented: Bool

    func body(content: Content) -> some View {
        if BSHDesign.active == .bureau {
            content.overlay {
                if isPresented {
                    MacBureauCommandPalette()
                        .environmentObject(store)
                }
            }
        } else {
            content.sheet(isPresented: $isPresented) {
                MacCommandPalette()
                    .environmentObject(store)
            }
        }
    }
}

// MARK: - The palette

/// The website's palette. Over the window it is the scrim and the panel; inside a sheet (the
/// Mac's presentation, when the window still presents the palette as one) the panel alone.
struct MacBureauCommandPalette: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    var inSheet = false

    @State private var query = ""
    @State private var active = 0
    @State private var order: [String] = MacBureauCommandPaletteOrder.ids
    @State private var shown = false
    @State private var openedAt = Date()
    @FocusState private var focused: Bool

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    /// The companies in the server's order, as the website lists them (the Mac's store keeps
    /// them by name); the ones the order doesn't know yet keep the store's order, after.
    private var companies: [MacMarketCommandCompany] {
        let rank = Dictionary(order.enumerated().map { ($1, $0) }, uniquingKeysWith: { a, _ in a })
        return store.companies.enumerated()
            .sorted { (rank[$0.element.id] ?? order.count + $0.offset) < (rank[$1.element.id] ?? order.count + $1.offset) }
            .map { MacMarketCommandCompany(id: $0.element.id, ticker: $0.element.ticker, name: $0.element.name) }
    }

    private var rows: [MacMarketCommandRow] {
        MacMarketCommands.suggest(query, companies: companies, limit: 8)
    }

    var body: some View {
        Group {
            if inSheet {
                panel(width: 640, nudge: 0)
                    .presentationBackground(ink.raised)
            } else {
                GeometryReader { proxy in
                    // `pt-[14vh]`. The browser lays the page out in whole CSS pixels, so the
                    // panel lands on the nearest point and what the search line centers on its
                    // half points (the glass, the field's text, the key) on the nearest point
                    // to where it would have been.
                    let top = proxy.size.height * 0.14
                    ZStack(alignment: .top) {
                        // `.yf-cmd-backdrop::before`: the desk dimmed, not frosted. A click on it
                        // closes the palette.
                        Button(action: close) {
                            scrim
                                .opacity(shown ? 1 : 0)
                                // `fade-in 0.16s var(--ease-standard)`
                                .animation(.timingCurve(0.25, 0.1, 0.25, 1, duration: 0.16), value: shown)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(MacBureauPaletteBareButton())
                        .accessibilityHidden(true)
                        // `.yf-cmd-panel` rises into place (`sheet-rise`).
                        panel(width: min(640, max(0, proxy.size.width - 32)), nudge: (top + 17.5).rounded() - top.rounded() - 17.5)
                            .scaleEffect(shown ? 1 : 0.97)
                            .offset(y: shown ? 0 : 10)
                            .opacity(shown ? 1 : 0)
                            .padding(.top, top.rounded())
                    }
                    .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
                }
                .ignoresSafeArea()
            }
        }
        .onAppear(perform: opened)
        .onChange(of: query) { _, _ in active = 0 }
        // ⌘K (the Go menu, the masthead) while open closes it, as on the website.
        // (`$showCommandPalette` publishes before the value is stored, so this closes after.)
        .onReceive(store.$showCommandPalette.dropFirst()) { open in
            if open, Date().timeIntervalSince(openedAt) > 0.3 { DispatchQueue.main.async { close() } }
        }
        // ⌘N opens the report sheet over it; the website closes the palette first.
        .onChange(of: store.showNewReportSheet) { _, open in if open { close() } }
    }

    // MARK: Parts

    private static let placeholder = "NVDA · HP · HEAT · RRG · DESK · FA · EVTS"

    private var scrim: some View {
        ink.dark ? Color.bshFixed(BSHRGB(0, 0, 0), opacity: 0.32) : Color.bshFixed(Self.scrimRGB, opacity: 0.22)
    }

    /// `--scrim` by day, per desk (bureau.css, bureau-desks.css).
    private static var scrimRGB: BSHRGB {
        switch BSHBureauDesk.active {
        case .onyx: return BSHRGB(0, 0, 0)
        case .green: return BSHRGB(8, 16, 13)
        case .maroon: return BSHRGB(22, 6, 9)
        case .navy: return BSHRGB(6, 10, 20)
        case .aubergine: return BSHRGB(14, 7, 14)
        case .tobacco: return BSHRGB(14, 10, 6)
        case .graphite: return BSHRGB(8, 10, 12)
        }
    }

    private func panel(width: CGFloat, nudge: CGFloat) -> some View {
        let list = rows
        let shape = RoundedRectangle(cornerRadius: 20, style: .circular)
        return VStack(spacing: 0) {
            searchLine(nudge: nudge)
            ScrollView(.vertical) {
                VStack(spacing: 0) {
                    ForEach(Array(list.enumerated()), id: \.element.id) { index, row in
                        Button { run(row) } label: {
                            rowView(row, isActive: index == active).contentShape(Rectangle())
                        }
                        .buttonStyle(MacBureauPaletteBareButton())
                        .onHover { inside in if inside { active = index } }
                        .accessibilityAddTraits(index == active ? .isSelected : [])
                    }
                }
                .padding(6)
            }
            // `overflow-y: auto`: it scrolls, and gives, only when the rows overflow it.
            .scrollBounceBehavior(.basedOnSize)
            // `.yf-cmd-list`: at most 24rem, then it scrolls.
            .frame(height: min(CGFloat(list.count) * 50 + 12, 384))
            hint
        }
        .frame(width: width)
        .background(shape.fill(ink.raised))
        .clipShape(shape)
        .background { if !inSheet { MacBureauPaletteShadow(ink: ink, radius: 20) } }
    }

    /// `.yf-cmd-input-wrap`: the glass, the field and the "esc" key, ruled off below.
    private func searchLine(nudge: CGFloat) -> some View {
        HStack(spacing: 12) {
            LucideIcon("search", size: 20)
                .foregroundStyle(ink.muted)
                .offset(y: nudge)
            TextField("", text: $query)
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(18))
                .foregroundStyle(ink.ink)
                .focused($focused)
                .focusEffectDisabled()
                .autocorrectionDisabled()
                .frame(height: 27)
                // The placeholder in the page's subtle ink (a prompt would take the system's).
                .background(alignment: .leading) {
                    if query.isEmpty {
                        Text(Self.placeholder)
                            .font(BSHType.bureauSans(18))
                            .foregroundStyle(ink.subtle)
                            .lineLimit(1)
                            .allowsHitTesting(false)
                            .accessibilityHidden(true)
                    }
                }
                .accessibilityLabel(Self.placeholder)
                .onKeyPress(.downArrow) { move(1); return .handled }
                .onKeyPress(.upArrow) { move(-1); return .handled }
                .onKeyPress(.tab) { .handled }
                .onKeyPress(.escape) { close(); return .handled }
                .onExitCommand { close() }
                .onSubmit { run(rows.indices.contains(active) ? rows[active] : nil) }
                .offset(y: nudge)
            MacBureauPaletteKey(text: "esc", ink: ink)
                .offset(y: nudge)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .overlay(alignment: .bottom) { ink.ink(0.08).frame(height: 1) }
    }

    /// `.yf-cmd-hint`.
    private var hint: some View {
        Self.text("↑↓ to move · Enter to run · Esc to close · / or ⌘K to open", size: 11)
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .lineLimit(1)
            .bureauLines(14, size: 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .overlay(alignment: .top) { ink.ink(0.08).frame(height: 1) }
    }

    /// `.yf-cmd-item`: the ⌘ tile or the company's mark, the title over the subtitle, and on
    /// the chosen row the return glyph.
    private func rowView(_ row: MacMarketCommandRow, isActive: Bool) -> some View {
        HStack(spacing: 12) {
            if let companyId = row.companyId {
                MacBureauPaletteMark(companyId: companyId, name: row.subtitle.isEmpty ? row.title : row.subtitle, ticker: row.ticker, ink: ink)
            } else {
                // `.yf-cmd-glyph`; chosen, brass-tinted with its glyph in ink.
                LucideIcon("command", size: 16)
                    .foregroundStyle(isActive ? ink.ink : ink.secondary)
                    .frame(width: 30, height: 30)
                    .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(isActive ? ink.accentGlow(0.22) : ink.ink(0.06)))
            }
            VStack(alignment: .leading, spacing: 0) {
                Self.text(row.title, size: 14, weight: .semibold)
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(20, size: 14)
                Self.text(row.subtitle, size: 11)
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauLines(14, size: 11)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if isActive {
                LucideIcon("corner-down-left", size: 16)
                    .foregroundStyle(ink.muted)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background {
            if isActive { MacBureauPaletteActiveRow(ink: ink) }
        }
    }

    /// Text in the interface face, with the glyphs the website's Instrument Sans lacks (⌘ and
    /// ↑) set in the system face the browser falls back to, not the Lucida Grande (⌘) and the
    /// bundled face's own arrow (↑) the Mac would reach for.
    private static func text(_ string: String, size: CGFloat, weight: Font.Weight = .regular) -> Text {
        var result = Text(verbatim: "")
        var run = ""
        var runIsSymbol = false
        func flush() {
            guard !run.isEmpty else { return }
            result = result + Text(verbatim: run).font(runIsSymbol ? .system(size: size, weight: weight) : BSHType.bureauSans(size, weight: weight))
            run = ""
        }
        for character in string {
            let symbol = character == "⌘" || character == "↑"
            if symbol != runIsSymbol { flush(); runIsSymbol = symbol }
            run.append(character)
        }
        flush()
        return result
    }

    // MARK: Behavior

    private func opened() {
        query = store.commandPaletteSeed
        store.commandPaletteSeed = ""
        active = 0
        openedAt = Date()
        withAnimation(.timingCurve(0.32, 0.72, 0, 1, duration: 0.28)) { shown = true }
        DispatchQueue.main.async { focused = true }
        // Focusing a field selects what is in it; a query handed in reads as typed, the
        // caret after it.
        if !query.isEmpty {
            let typed = query
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { Self.placeCaret(after: typed) }
        }
        // The field took focus while the panel was still rising, and AppKit leaves its editor
        // where the rise found it (a fraction of a point off). Once the panel has settled, the
        // field takes focus again where it stands, keeping what was typed and the selection.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.32) { if focused { Self.resettleEditor(holding: query) } }
        // The server's order of the companies, which the website lists them in.
        Task {
            guard let list = try? await MacAPIClient.shared.listCompanies() else { return }
            let ids = list.map(\.id)
            MacBureauCommandPaletteOrder.ids = ids
            order = ids
        }
    }

    private static func resettleEditor(holding text: String) {
        for window in NSApp.windows {
            guard let editor = window.firstResponder as? NSTextView, editor.isFieldEditor, editor.string == text,
                  !editor.hasMarkedText(), let field = editor.delegate as? NSTextField, field.window === window else { continue }
            let selection = editor.selectedRange()
            window.makeFirstResponder(field)
            (field.currentEditor() as? NSTextView)?.setSelectedRange(selection)
        }
    }

    private static func placeCaret(after text: String) {
        for window in NSApp.windows {
            guard let editor = window.firstResponder as? NSTextView, editor.isFieldEditor, editor.string == text else { continue }
            editor.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
        }
    }

    private func move(_ delta: Int) {
        let count = rows.count
        active = delta > 0 ? min(active + 1, max(count - 1, 0)) : max(active - 1, 0)
    }

    private func close() {
        store.showCommandPalette = false
    }

    /// `run(row)`: the examples row does nothing; Generate opens the report sheet; the rest
    /// go to their desk. The palette closes first, as on the website.
    private func run(_ row: MacMarketCommandRow?) {
        guard let cmd = row?.command ?? MacMarketCommands.parse(query), cmd.action != .help else { return }
        close()
        store.runMarketCommand(cmd)
    }
}

/// The companies' order on the server (`GET /api/companies`), kept across openings so the
/// palette lists them as the website does from its first keystroke.
private enum MacBureauCommandPaletteOrder {
    nonisolated(unsafe) static var ids: [String] = []
}

// MARK: - Pieces

/// `.kbd` as `.yf-cmd-kbd` copies it: the page's tray by day with a hairline and a step
/// under it; by night a film of white.
private struct MacBureauPaletteKey: View {
    let text: String
    let ink: MacBureauPageInk

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 5, style: .circular)
        Text(text)
            .font(BSHType.bureauSans(11, weight: .medium))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .fixedSize()
            .bureauLines(14, size: 11)
            .padding(.horizontal, 4)
            .frame(minWidth: 20, minHeight: 20)
            .background {
                ZStack {
                    if ink.dark {
                        shape.fill(Color.white.opacity(0.08))
                    } else {
                        shape.fill(Color.black.opacity(0.08)).offset(y: 1)
                        shape.fill(ink.tray)
                    }
                }
            }
            .overlay(shape.inset(by: -0.25).stroke(ink.dark ? Color.white.opacity(0.14) : Color.black.opacity(0.14), lineWidth: 0.5))
    }
}

/// A button drawn as its label alone: the rows and the scrim show no press of their own.
private struct MacBureauPaletteBareButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { configuration.label }
}

/// The chosen row: a film of ink with a brass edge down its left side
/// (`inset 2px 0 0 --color-accent-glow`).
private struct MacBureauPaletteActiveRow: View {
    let ink: MacBureauPageInk

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 10, style: .circular)
        ZStack {
            shape.fill(ink.ink(0.06))
            ZStack {
                shape.fill(ink.accentGlow(1))
                shape.fill(Color.black).offset(x: 2).blendMode(.destinationOut)
            }
            .compositingGroup()
            .clipShape(shape)
        }
    }
}

/// `--shadow-sheet` on the page: a ring of ink and the long shadow under the sheet (with a
/// short one by day), each drawn as CSS draws a box shadow with a spread.
private struct MacBureauPaletteShadow: View {
    let ink: MacBureauPageInk
    let radius: CGFloat

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        ZStack {
            if ink.dark {
                cast(y: 26, blur: 60, spread: -22, color: Color.black.opacity(0.8))
                shape.inset(by: -0.5).stroke(Color.white.opacity(0.08), lineWidth: 1)
            } else {
                cast(y: 26, blur: 60, spread: -26, color: ink.shadow(0.5))
                cast(y: 6, blur: 16, spread: -8, color: ink.shadow(0.18))
                shape.inset(by: -0.5).stroke(ink.ink(0.08), lineWidth: 1)
            }
        }
        .allowsHitTesting(false)
    }

    /// `0 <y>px <blur>px <spread>px <color>`: the box grown by the spread (its corners with
    /// it), moved down, blurred by a Gaussian of half the blur.
    private func cast(y: CGFloat, blur: CGFloat, spread: CGFloat, color: Color) -> some View {
        RoundedRectangle(cornerRadius: max(0, radius + spread), style: .circular)
            .fill(color)
            .padding(-spread)
            .offset(y: y)
            .blur(radius: blur / 2)
    }
}

/// `<Monogram tinted :size="30">`: the company's logo on white, or its initials on one of
/// ten tints picked by a hash of its id.
private struct MacBureauPaletteMark: View {
    let companyId: String
    let name: String
    let ticker: String?
    let ink: MacBureauPageInk
    @State private var image: NSImage?

    private var urls: [URL] {
        [
            MacCompanyLogoResolver.resolvePrimaryLogoUrl(ticker: ticker, companyId: companyId, name: name),
            MacCompanyLogoResolver.resolveFallbackLogoUrl(ticker: ticker, companyId: companyId, name: name),
        ].compactMap { $0 }
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 8.4, style: .circular)
        Group {
            if let image = image ?? cached {
                ZStack {
                    shape.fill(Color.white)
                    shape.inset(by: 0.25).stroke(ink.dark ? Color.white.opacity(0.15) : Color.black.opacity(0.12), lineWidth: 0.5)
                    // `.monogram-logo`: 8% in, its corners the tile's less that (8.4 − 2.4).
                    Image(nsImage: image)
                        .resizable()
                        .interpolation(.high)
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 25.2, height: 25.2)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .circular))
                }
                .clipShape(shape)
                .background(
                    shape.fill(Color.black.opacity(ink.dark ? 0.35 : 0.06))
                        .offset(y: 1)
                        .blur(radius: ink.dark ? 1.5 : 1)
                )
            } else {
                Text(Self.initials(ticker: ticker, name: name))
                    .font(BSHType.bureauSans(11.1, weight: .semibold))
                    .tracking(0.111)
                    .foregroundStyle(Color.white)
                    .frame(width: 30, height: 30)
                    .background(LinearGradient(
                        colors: [tint, tint.opacity(0.72)],
                        startPoint: UnitPoint(x: 0.1007, y: -0.0704),
                        endPoint: UnitPoint(x: 0.8993, y: 1.0704)
                    ))
                    .overlay(shape.strokeBorder(Color.black.opacity(0.06), lineWidth: 1))
                    .clipShape(shape)
            }
        }
        .frame(width: 30, height: 30)
        .task(id: companyId) { await load() }
    }

    private var cached: NSImage? {
        urls.lazy.compactMap { MacImageCache.shared.image(for: $0) }.first
    }

    private func load() async {
        guard image == nil, cached == nil else { return }
        for url in urls where !MacImageCache.shared.isFailed(url) {
            var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 8)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)", forHTTPHeaderField: "User-Agent")
            if let (data, response) = try? await URLSession.shared.data(for: request),
               (response as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true,
               let loaded = NSImage(data: Self.sized(data)) {
                MacImageCache.shared.setImage(loaded, for: url)
                image = loaded
                return
            }
            MacImageCache.shared.markFailed(url)
        }
    }

    /// An SVG drawn at 1em has no size of its own to draw at.
    private static func sized(_ data: Data) -> Data {
        guard let text = String(data: data, encoding: .utf8), text.contains("<svg") else { return data }
        return text
            .replacingOccurrences(of: "width=\"1em\"", with: "width=\"64\"")
            .replacingOccurrences(of: "height=\"1em\"", with: "height=\"64\"")
            .data(using: .utf8) ?? data
    }

    /// `data-tint`: a hash of the id picks one of ten system colors.
    private var tint: Color {
        let tints = [
            BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
            BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
        ]
        var hash: UInt32 = 0
        for unit in (companyId.isEmpty ? name : companyId).utf16 { hash = hash &* 31 &+ UInt32(unit) }
        return .bshFixed(tints[Int(hash % 10)])
    }

    /// `companyInitials`.
    static func initials(ticker: String?, name: String) -> String {
        let symbol = (ticker ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if (1...5).contains(symbol.count), symbol.unicodeScalars.allSatisfy({ ("A"..."Z").contains($0) || ("a"..."z").contains($0) }) {
            return String(symbol.prefix(2)).uppercased()
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "?" }
        let separators = CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",./&+_–—-"))
        let tokens = trimmed.components(separatedBy: separators).filter { !$0.isEmpty }
        if tokens.count >= 2 {
            return (String(tokens[0].prefix(1)) + String(tokens[1].prefix(1))).uppercased()
        }
        let word = String(String.UnicodeScalarView((tokens.first ?? trimmed).unicodeScalars.filter {
            ("A"..."Z").contains($0) || ("a"..."z").contains($0) || ("0"..."9").contains($0)
        }))
        let caps = word.filter { $0.isASCII && $0.isUppercase }
        if caps.count >= 2 { return String(caps.prefix(2)) }
        if word.count >= 2 { return String(word.prefix(2)).uppercased() }
        if word.count == 1 { return word.uppercased() }
        return "?"
    }
}
