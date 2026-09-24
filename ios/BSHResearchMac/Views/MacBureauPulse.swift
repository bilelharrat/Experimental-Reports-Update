//
//  MacBureauPulse.swift
//  BSHResearchMac
//
//  Bureau's Pulse is the website's (WeeklySummaryView.vue under MarketsView.vue): the
//  Market · Pulse · News sub-nav, the title with its four actions, the US market posture
//  with the breadth of the whole Nasdaq tape, the Morning Brief printed as a front page,
//  then the indexes, sectors, rates and commodities, the session's movers, the week's
//  catalysts, the researched week (or its empty state) and the research signals.
//
//  Everything is read with GETs. The runs the website starts from here (Refresh brief,
//  Build brief, Rewrite note) have no call on the Mac, so their buttons open the website's
//  Pulse in the research browser, where they run behind its token confirmation.
//

import AppKit
import SwiftUI

// MARK: - JSON, read leniently

/// A JSON object read without a schema: the page's payloads carry many optional fields in
/// two languages, and the website reads them the same forgiving way (`pick`).
struct MacBureauPNJSON {
    let raw: [String: Any]

    init(_ raw: [String: Any]) { self.raw = raw }

    init?(_ any: Any?) {
        guard let dict = any as? [String: Any] else { return nil }
        raw = dict
    }

    static func load(_ path: String) async throws -> MacBureauPNJSON {
        let data = try await MacAPIClient.shared.download(pathOrURL: path)
        guard let object = MacBureauPNJSON(try JSONSerialization.jsonObject(with: data)) else {
            throw MacAPIError.decoding
        }
        return object
    }

    func string(_ key: String) -> String? {
        if let text = raw[key] as? String {
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : text
        }
        if let number = raw[key] as? NSNumber, !Self.isBoolean(number) { return number.stringValue }
        return nil
    }

    func double(_ key: String) -> Double? {
        if let number = raw[key] as? NSNumber {
            guard !Self.isBoolean(number) else { return nil }
            return number.doubleValue.isFinite ? number.doubleValue : nil
        }
        if let text = raw[key] as? String, let value = Double(text), value.isFinite { return value }
        return nil
    }

    func bool(_ key: String) -> Bool { (raw[key] as? NSNumber)?.boolValue ?? false }

    /// JSON's true and false arrive as NSNumber too; `is Bool` would also take 0 and 1.
    static func isBoolean(_ number: NSNumber) -> Bool {
        CFGetTypeID(number) == CFBooleanGetTypeID()
    }
    func object(_ key: String) -> MacBureauPNJSON? { MacBureauPNJSON(raw[key]) }
    func array(_ key: String) -> [Any] { raw[key] as? [Any] ?? [] }
    func objects(_ key: String) -> [MacBureauPNJSON] { array(key).compactMap { MacBureauPNJSON($0) } }
    func strings(_ key: String) -> [String] { array(key).compactMap { $0 as? String }.filter { !$0.isEmpty } }
    func count(_ key: String) -> Int { array(key).count }

    /// `pick(obj, base)`: the language's field, then the plain one, then the other language.
    func pick(_ base: String, zh: Bool) -> String {
        let order = zh ? ["\(base)_zh", "\(base)_en", base] : ["\(base)_en", base, "\(base)_zh"]
        for key in order { if let value = string(key) { return value } }
        return ""
    }

    /// `pickArray(obj, base)`, the same order for lists.
    func pickArray(_ base: String, zh: Bool) -> [Any] {
        let order = zh ? ["\(base)_zh", "\(base)_en", base] : ["\(base)_en", base, "\(base)_zh"]
        for key in order {
            let list = array(key)
            if !list.isEmpty { return list }
        }
        return []
    }
}

// MARK: - The page's data

/// What Pulse reads, all with GETs: the morning brief and its archive, the weekly
/// research, the Nasdaq screener (breadth and movers), quotes for the index, sector and
/// macro tapes, the week's calendar and the signals page.
@MainActor
final class MacBureauPulseModel: ObservableObject {
    struct Breadth {
        var total = 0
        var up = 0
        var down = 0
        var flat = 0
        var pctUp: Double?
        var pctNearHigh: Double?
    }

    struct Mover: Identifiable {
        let ticker: String
        let name: String?
        let last: Double?
        /// The day's move in percent.
        let change: Double?
        var id: String { ticker }
    }

    struct ScreenerRead {
        var breadth = Breadth()
        var gainers: [Mover] = []
        var losers: [Mover] = []
        var active: [Mover] = []
    }

    @Published private(set) var brief: MacBureauPNJSON?
    @Published private(set) var briefDates: [String] = []
    @Published private(set) var briefLoaded = false
    @Published var briefError: String?
    @Published private(set) var noteScheduleRunning = false

    @Published private(set) var weekly: MacBureauPNJSON?
    @Published private(set) var weeklyLoaded = false

    @Published private(set) var screener = ScreenerRead()
    @Published private(set) var quotes: [String: MacQuote] = [:]
    @Published private(set) var calendar: [MacCalendarEvent] = []
    @Published private(set) var signalsPage: MacBureauPNJSON?
    @Published private(set) var marketLoading = true

    /// The weekly research, when it is the current schema.
    var summary: MacBureauPNJSON? {
        guard let summary = weekly?.object("summary"), summary.double("schema_version") == 2 else { return nil }
        return summary
    }

    func load() async {
        async let brief: Void = loadBrief(date: nil)
        async let weekly: Void = loadWeekly()
        async let market: Void = loadMarket()
        _ = await (brief, weekly, market)
    }

    func loadBrief(date: String?) async {
        briefError = nil
        let path = date.map { "market-brief?date=\($0)" } ?? "market-brief"
        async let archive = try? MacBureauPNJSON.load("market-brief/archive")
        async let latest = try? MacBureauPNJSON.load(path)
        let (a, l) = await (archive, latest)
        briefDates = a?.strings("dates") ?? []
        brief = l
        briefLoaded = true
    }

    func selectBriefDate(_ date: String) async {
        guard !date.isEmpty, date != brief?.string("date") else { return }
        do {
            brief = try await MacBureauPNJSON.load("market-brief?date=\(date)")
        } catch {
            briefError = "Could not load that brief"
        }
    }

    /// The morning schedule writes the note on the server; the long one takes about a
    /// minute and a half. While it does, the card shows the report taking shape.
    func pollNoteSchedule() async {
        while !Task.isCancelled {
            let state = try? await MacBureauPNJSON.load("market-brief/schedule")
            let wasRunning = noteScheduleRunning
            noteScheduleRunning = state?.bool("running") ?? false
            if wasRunning && !noteScheduleRunning {
                await loadBrief(date: brief?.string("date"))
            }
            try? await Task.sleep(for: .seconds(10))
        }
    }

    func loadWeekly() async {
        weekly = try? await MacBureauPNJSON.load("weekly-stocks")
        weeklyLoaded = true
    }

    func loadMarket() async {
        marketLoading = true
        defer { marketLoading = false }
        async let screenerTask = Self.readScreener()
        async let signalsTask = try? MacBureauPNJSON.load("research-pages/market-pulse")
        async let quotesTask = try? MacAPIClient.shared.fetchQuotes(tickers: MacBureauPulseTape.universe)
        let (read, signals, fetched) = await (screenerTask, signalsTask, quotesTask)
        if let read { screener = read }
        signalsPage = signals
        if let fetched {
            quotes = Dictionary(fetched.map { ($0.ticker.uppercased(), $0) }, uniquingKeysWith: { first, _ in first })
        }
        // The week's catalysts for the tape, this week's setups and the screener's movers.
        let stockTickers = (summary?.objects("stocks") ?? []).compactMap { $0.string("ticker") }
        let hot = Array(MacBureauPulseTape.universe.prefix(24))
            + stockTickers
            + (read?.gainers.prefix(8).map(\.ticker) ?? [])
            + (read?.losers.prefix(8).map(\.ticker) ?? [])
        var seen = Set<String>()
        let unique = hot.map { $0.uppercased() }.filter { !$0.isEmpty && seen.insert($0).inserted }
        if let cal = try? await MacAPIClient.shared.fetchQuoteCalendar(tickers: unique) {
            calendar = cal.events
        }
    }

    /// The Nasdaq screener (6,000-odd rows), read off the main thread: breadth over the
    /// whole universe (`marketBreadthFromUniverse`) and the first ten of each mover list.
    private static func readScreener() async -> ScreenerRead? {
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: "quotes/screeners") else { return nil }
        return await Task.detached(priority: .userInitiated) { () -> ScreenerRead? in
            guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
            func rows(_ key: String) -> [[String: Any]] { root[key] as? [[String: Any]] ?? [] }
            func number(_ value: Any?) -> Double? {
                if let n = value as? NSNumber {
                    // JSON booleans are NSNumbers too (and `is Bool` would take 0 and 1).
                    guard CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
                    return n.doubleValue.isFinite ? n.doubleValue : nil
                }
                if let s = value as? String, let d = Double(s), d.isFinite { return d }
                return nil
            }
            var read = ScreenerRead()
            var up = 0, down = 0, flat = 0, withHigh = 0, nearHigh = 0, total = 0
            for row in rows("universe") {
                // The screener sends `change_pct`; quote rows send `change_pct_1d`.
                guard let change = number(row["change_pct_1d"] ?? row["change_pct"]) else { continue }
                total += 1
                if change > 0.05 { up += 1 } else if change < -0.05 { down += 1 } else { flat += 1 }
                if let last = number(row["last_price"] ?? row["last"]), let high = number(row["high_52w"] ?? row["year_high"]), high > 0 {
                    withHigh += 1
                    if last / high >= 0.95 { nearHigh += 1 }
                }
            }
            read.breadth = Breadth(
                total: total, up: up, down: down, flat: flat,
                pctUp: total > 0 ? Double(up) / Double(total) * 100 : nil,
                pctNearHigh: withHigh > 0 ? Double(nearHigh) / Double(withHigh) * 100 : nil
            )
            func movers(_ key: String) -> [Mover] {
                rows(key).prefix(10).compactMap { row in
                    guard let ticker = row["ticker"] as? String, !ticker.isEmpty else { return nil }
                    return Mover(
                        ticker: ticker.uppercased(),
                        name: row["name"] as? String,
                        last: number(row["last_price"] ?? row["last"]),
                        change: number(row["change_pct_1d"] ?? row["change_pct"])
                    )
                }
            }
            read.gainers = movers("gainers")
            read.losers = movers("losers")
            read.active = movers(root["active"] != nil ? "active" : "most_active")
            return read
        }.value
    }

    func quote(_ ticker: String) -> MacQuote? { quotes[ticker.uppercased()] }
}

/// The tape Pulse quotes (marketPulseDesk.js): the indexes and style factors, the SPDR
/// sector funds and the rates, credit, dollar, commodity and volatility proxies.
enum MacBureauPulseTape {
    static let indexes: [(ticker: String, label: String)] = [
        ("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow 30"), ("IWM", "Russell 2000"),
        ("RSP", "Equal-weight S&P"), ("MTUM", "Momentum"), ("VLUE", "Value"), ("USMV", "Min vol"),
    ]
    static let sectors: [(ticker: String, label: String)] = [
        ("XLK", "Technology"), ("XLF", "Financials"), ("XLE", "Energy"), ("XLV", "Health Care"),
        ("XLI", "Industrials"), ("XLY", "Consumer Disc."), ("XLP", "Consumer Staples"), ("XLU", "Utilities"),
        ("XLB", "Materials"), ("XLRE", "Real Estate"), ("XLC", "Communication"),
    ]
    static let macro: [(ticker: String, label: String)] = [
        ("TLT", "Long bonds"), ("IEF", "7–10y Treasuries"), ("HYG", "HY credit"), ("LQD", "IG credit"),
        ("UUP", "US Dollar"), ("USO", "Crude oil"), ("GLD", "Gold"), ("VIXY", "Vol"), ("BITO", "Bitcoin"),
    ]
    private static let marketIndex = ["SPY", "QQQ", "DIA", "IWM", "EFA", "EEM", "GLD", "USO", "TLT", "VIXY", "UUP", "HYG"]
    private static let wei = ["SPY", "QQQ", "TLT", "UUP", "USO", "VIXY", "HYG", "GLD"]

    /// `pulseQuoteUniverse()`, in its order.
    static let universe: [String] = {
        var seen = Set<String>()
        let all = indexes.map(\.ticker) + sectors.map(\.ticker) + macro.map(\.ticker) + marketIndex + wei
        return all.filter { seen.insert($0).inserted }
    }()
}

// MARK: - The page

struct MacBureauPulsePage: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @StateObject private var model = MacBureauPulseModel()
    @State private var expandedPrompt = false
    @State private var noteLength = "long"
    /// The language the workspace reads in (Settings), as the website's page follows it.
    @State private var workspaceLanguage: String?

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var zh: Bool { (workspaceLanguage ?? store.pulseLanguage) == "zh" }

    var body: some View {
        GeometryReader { proxy in
            // The website's breakpoints are the window's; the sheet is 78pt narrower.
            let viewport = proxy.size.width + 78
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    MacBureauPulseNewsSubNav()
                    page(viewport: viewport)
                        .padding(.horizontal, 32)
                        .padding(.top, 16)
                        .padding(.bottom, 48)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .scrollIndicators(.automatic)
        }
        .background(Color.dsCanvas)
        .task { await model.load() }
        .task { await model.pollNoteSchedule() }
        .task {
            if let lang = (try? await MacAPIClient.shared.workspaceSettings())?.preferences?.language, lang == "en" || lang == "zh" {
                workspaceLanguage = lang
            }
        }
        .task { if store.signals.isEmpty { await store.loadSignals() } }
    }

    @ViewBuilder
    private func page(viewport: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            header(viewport: viewport)
                .padding(.bottom, 24)

            if expandedPrompt, !prompt.isEmpty {
                promptPanel.padding(.bottom, 16)
            }
            if let status = liveStatus {
                statusLine(status).padding(.bottom, 12)
            }

            VStack(alignment: .leading, spacing: 20) {
                postureTray
                morningBriefTray(viewport: viewport)
                indexesSection(viewport: viewport)
                sectorsTray
                macroTray(viewport: viewport)
                moversSection(viewport: viewport)
                calendarTray(viewport: viewport)
                weekSection(viewport: viewport)
                signalsRow(viewport: viewport)
                if !store.signals.isEmpty {
                    MacBureauPulseLedger()
                }
            }
        }
    }

    // MARK: Header

    private var weekLabel: String { model.summary?.pick("week_label", zh: zh) ?? "" }
    private var marketPulse: String { model.summary?.pick("market_pulse", zh: zh) ?? "" }
    private var benchmarkContext: String { model.summary?.pick("benchmark_context", zh: zh) ?? "" }

    private var prompt: String {
        let summary = model.summary
        if zh { return summary?.string("research_prompt_zh") ?? model.weekly?.string("prompt_zh") ?? "" }
        return summary?.string("research_prompt_en") ?? summary?.string("research_prompt")
            ?? model.weekly?.string("prompt_en") ?? model.weekly?.string("prompt") ?? ""
    }

    @ViewBuilder
    private func header(viewport: CGFloat) -> some View {
        let wide = viewport >= 1024
        VStack(alignment: .leading, spacing: 0) {
            if wide {
                HStack(alignment: .bottom, spacing: 16) {
                    titleBlock
                    Spacer(minLength: 0)
                    actions
                }
            } else {
                VStack(alignment: .leading, spacing: 16) {
                    titleBlock
                    actions
                }
            }
            Text(marketPulse.isEmpty ? "US market brief — indexes, sectors, breadth, movers, and the week’s researched setups." : marketPulse)
                .font(BSHType.bureauSans(15))
                .foregroundStyle(ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(24.375, size: 15, face: .sans)
                .frame(maxWidth: 896, alignment: .leading)
                .padding(.top, 12)
        }
    }

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !weekLabel.isEmpty {
                HStack(spacing: 8) {
                    HStack(spacing: 6) {
                        LucideIcon("calendar-clock", size: 14)
                        Text(weekLabel).font(BSHType.bureauSans(13, weight: .semibold))
                    }
                    .foregroundStyle(ink.accentInk)
                    if let updated = MacBureauPNFormat.stamp(model.summary?.string("generated_at")) {
                        Text("· Updated \(updated)")
                            .font(BSHType.bureauSans(12))
                            .foregroundStyle(ink.muted)
                    }
                }
            }
            Text("Pulse")
                .font(.custom(BSHType.bureauSerif, size: 46))
                .tracking(-0.552)
                .foregroundStyle(ink.ink)
                .lineLimit(1)
                .fixedSize()
                .frame(height: 48)
                .padding(.top, 4)
        }
    }

    private var actions: some View {
        HStack(spacing: 8) {
            MacBureauButton("Open Market") { store.selectedTab = .market }
            MacBureauButton("Signals lab") { openWeb("innovation-lab/market-pulse") }
            MacBureauButton("Prompt") { expandedPrompt.toggle() }
            MacBureauButton("Refresh brief", icon: "refresh-cw", kind: .filled, busy: weeklyRunning) {
                openWeb("weekly-summary")
            }
            .help("The weekly research runs on the website: this opens its Pulse beside the page.")
        }
    }

    private var promptPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            MacBureauPNLabel("Weekly research prompt")
            ScrollView {
                Text(prompt)
                    .font(MacBureauPNFace.mono(12))
                    .foregroundStyle(ink.secondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(19.5, size: 12, face: .mono)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 288)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    /// A weekly research run in progress (the website attaches to it the same way).
    private var weeklyJob: MacActiveJob? {
        store.activeJobs.first { $0.kind == "weekly_stocks" || $0.streamUrl == "/api/weekly-stocks/refresh/stream" }
    }

    private var weeklyRunning: Bool { weeklyJob != nil }

    private var liveStatus: String? {
        guard let job = weeklyJob else { return nil }
        return job.latestStage ?? job.lastMessage ?? "Waiting for the updated summary"
    }

    private func statusLine(_ text: String) -> some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small).frame(width: 16, height: 16)
            Text(text).lineLimit(1).truncationMode(.tail)
        }
        .font(BSHType.bureauSans(14))
        .tracking(-0.084)
        .foregroundStyle(ink.accentInk)
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func openWeb(_ path: String) {
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(MacConfig.webURL(path: path))
        }
    }

    // MARK: US market posture

    private var posture: String {
        let pctUp = model.screener.breadth.pctUp
        let spy = model.quote("SPY")?.pct
        if let pctUp, pctUp >= 62, spy.map({ $0 >= 0 }) ?? true { return "Risk-on" }
        if let pctUp, pctUp <= 38, spy.map({ $0 <= 0 }) ?? true { return "Risk-off" }
        if let pctUp, let spy, (pctUp >= 55 && spy < 0) || (pctUp <= 45 && spy > 0) { return "Mixed" }
        return "Neutral"
    }

    private var postureText: String {
        let regime = model.signalsPage?.object("sections")?.object("market_regime")
        if let summary = regime?.string("posture_summary") { return summary }
        if !benchmarkContext.isEmpty { return benchmarkContext }
        return "Live breadth across the Nasdaq universe plus index tape."
    }

    private var postureTray: some View {
        let breadth = model.screener.breadth
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauPNLabel("US market posture")
                Spacer(minLength: 8)
                MacBureauPNLine(posture, size: 14, weight: .medium, tracking: -0.084, line: 20, color: ink.ink)
            }
            .frame(height: 20)
            Text(postureText)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(20, size: 14, face: .sans)
                .padding(.top, 4)
            HStack(spacing: 8) {
                statCell("Advancers", value: "\(breadth.up)", tone: ink.successInk)
                statCell("Decliners", value: "\(breadth.down)", tone: ink.dangerInk)
                statCell("% advancing", value: breadth.pctUp.map { String(format: "%.0f%%", $0) } ?? "n/a", tone: ink.ink)
                statCell("% near 52w high", value: breadth.pctNearHigh.map { String(format: "%.0f%%", $0) } ?? "n/a", tone: ink.ink)
            }
            .padding(.top, 12)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func statCell(_ label: String, value: String, tone: Color, fill: Double = 0.6, centered: Bool = false) -> some View {
        VStack(alignment: centered ? .center : .leading, spacing: 0) {
            MacBureauPNLine(label, size: 11, tracking: 0.066, line: 14, color: ink.muted)
            MacBureauPNLine(value, size: 18, weight: .semibold, tracking: -0.252, line: 24, color: tone, tabular: true)
        }
        .padding(.horizontal, centered ? 8 : 10)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
        .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.fillTertiary.opacity(fill)))
    }

    // MARK: Morning Brief

    private var noteBuilding: Bool { model.noteScheduleRunning }

    private func morningBriefTray(viewport: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauPNLabel("Morning Brief")
                Spacer(minLength: 8)
                briefControls
            }
            .frame(minHeight: 22)
            .padding(.bottom, 8)

            if let error = model.briefError {
                Text(error)
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.danger)
                    .pnLines(20, size: 14, face: .sans)
            } else if let brief = model.brief {
                briefBody(brief, viewport: viewport)
            } else if model.briefLoaded {
                Text("No archived brief yet — build one to freeze today’s tape.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .pnLines(20, size: 14, face: .sans)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private var briefControls: some View {
        HStack(spacing: 4) {
            if !model.briefDates.isEmpty {
                MacBureauPNRangeMenu(
                    options: model.briefDates.map { (value: $0, title: $0) },
                    selection: Binding(
                        get: { model.brief?.string("date") ?? model.briefDates.first ?? "" },
                        set: { date in Task { await model.selectBriefDate(date) } }
                    )
                )
            }
            MacBureauPNRangeButton(title: "Build brief") { openWeb("weekly-summary") }
                .help("Building a brief runs on the website: this opens its Pulse beside the page.")
            if model.brief != nil {
                MacBureauPNRangeMenu(
                    options: [(value: "short", title: "Short"), (value: "long", title: "Extended")],
                    selection: $noteLength
                )
                MacBureauPNRangeButton(title: model.brief?.object("note") != nil ? "Rewrite note" : "Write note") {
                    openWeb("weekly-summary")
                }
                .help("Writing the note runs on the website: this opens its Pulse beside the page.")
            }
        }
    }

    @ViewBuilder
    private func briefBody(_ brief: MacBureauPNJSON, viewport: CGFloat) -> some View {
        let frozen = MacBureauPNFormat.stamp(brief.string("generated_at")) ?? brief.string("date") ?? ""
        MacBureauPNLine("Frozen \(frozen)", size: 11, tracking: 0.066, line: 14, color: ink.muted)

        if noteBuilding {
            MacBureauPulseNoteSkeleton(viewport: viewport)
                .padding(.top, 10)
        } else if let note = brief.object("note") {
            MacBureauPulseArticle(brief: brief, note: note, zh: zh, viewport: viewport)
                .padding(.top, 10)
        }

        let indices = Array(brief.objects("indices").prefix(6))
        if !indices.isEmpty {
            HStack(spacing: 8) {
                ForEach(Array(indices.enumerated()), id: \.offset) { _, row in
                    indexChip(row)
                }
            }
            .padding(.top, 8)
        }

        let movers = brief.object("movers")
        let gainers = Array((movers?.objects("gainers") ?? []).prefix(4))
        let losers = Array((movers?.objects("losers") ?? []).prefix(4))
        if !gainers.isEmpty || !losers.isEmpty {
            HStack(alignment: .top, spacing: 12) {
                briefMovers("Watchlist gainers", rows: gainers, tone: ink.success)
                briefMovers("Watchlist losers", rows: losers, tone: ink.danger)
            }
            .padding(.top, 12)
        }
        let alerts = brief.count("alerts_last_day")
        if alerts > 0 {
            MacBureauPNLine("\(alerts) alerts in the last day", size: 11, tracking: 0.066, line: 14, color: ink.secondary)
                .padding(.top, 8)
        }
        let events = brief.count("calendar")
        if events > 0 {
            MacBureauPNLine("\(events) events this week", size: 11, tracking: 0.066, line: 14, color: ink.muted)
        }
    }

    private func changeTone(_ value: Double?) -> Color {
        guard let value else { return ink.muted }
        return value >= 0 ? ink.successInk : ink.dangerInk
    }

    private func indexChip(_ row: MacBureauPNJSON) -> some View {
        let ticker = row.string("ticker") ?? ""
        let change = row.double("change_pct_1d")
        return MacBureauPNPlate(fill: ink.fillTertiary.opacity(0.6), hoverFill: nil) {
            store.showTicker(ticker)
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(ticker)
                    .font(MacBureauPNFace.mono(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                Text(MacBureauPNFormat.pct(change))
                    .font(BSHType.bureauSans(14).monospacedDigit())
                    .tracking(-0.084)
                    .foregroundStyle(changeTone(change))
            }
            .padding(.horizontal, 10)
            .frame(height: 36)
        }
    }

    private func briefMovers(_ title: String, rows: [MacBureauPNJSON], tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLine(title, size: 11, tracking: 0.066, line: 14, color: ink.muted)
            VStack(spacing: 2) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    let ticker = row.string("ticker") ?? ""
                    Button {
                        store.showTicker(ticker)
                    } label: {
                        HStack(spacing: 8) {
                            Text(ticker)
                                .font(BSHType.bureauSans(12).monospacedDigit())
                                .foregroundStyle(ink.ink)
                            Spacer(minLength: 8)
                            Text(MacBureauPNFormat.pct(row.double("change_pct_1d")))
                                .font(BSHType.bureauSans(14).monospacedDigit())
                                .tracking(-0.084)
                                .foregroundStyle(tone)
                        }
                        .frame(height: 20)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Indexes, sectors, rates

    private func indexesSection(viewport: CGFloat) -> some View {
        let columns = viewport >= 1280 ? 8 : (viewport >= 640 ? 4 : 2)
        return VStack(alignment: .leading, spacing: 8) {
            MacBureauPNLabel("US indexes & style")
            MacBureauPNGrid(columns: columns, spacing: 8, items: MacBureauPulseTape.indexes.map(\.ticker)) { ticker in
                let label = MacBureauPulseTape.indexes.first { $0.ticker == ticker }?.label ?? ticker
                indexCard(ticker: ticker, label: label)
            }
        }
    }

    private func indexCard(ticker: String, label: String) -> some View {
        let quote = model.quote(ticker)
        return MacBureauPNCardButton {
            store.showTicker(ticker)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 8) {
                    MacBureauPNLine(label, size: 11, tracking: 0.066, line: 14, color: ink.muted)
                        .truncationMode(.tail)
                    Spacer(minLength: 0)
                    Text(ticker)
                        .font(MacBureauPNFace.mono(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.subtle)
                        .fixedSize()
                }
                if let quote, quote.last != nil || quote.pct != nil {
                    HStack(alignment: .firstTextBaseline, spacing: 0) {
                        if let price = MacBureauPNFormat.price(quote.last) {
                            MacBureauPNLine(price, size: 18, weight: .semibold, tracking: -0.252, line: 24, color: ink.ink, tabular: true)
                                .fixedSize()
                        }
                        Spacer(minLength: 8)
                        if let change = MacBureauPNFormat.signed(quote.pct) {
                            MacBureauPNLine(change, size: 14, tracking: -0.084, line: 20, color: changeTone(quote.pct), tabular: true)
                                .fixedSize()
                        }
                    }
                    .padding(.top, 4)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var sectorRows: [(ticker: String, label: String, quote: MacQuote)] {
        MacBureauPulseTape.sectors
            .compactMap { def in model.quote(def.ticker).flatMap { $0.last != nil ? (def.ticker, def.label, $0) : nil } }
            .sorted { ($0.quote.pct ?? -.infinity) > ($1.quote.pct ?? -.infinity) }
    }

    private var sectorsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauPNLabel("Sector rotation")
                Spacer(minLength: 8)
                MacBureauPNLine("SPDR Select ETFs · 1D", size: 11, tracking: 0.066, line: 14, color: ink.muted)
            }
            .padding(.bottom, 8)
            let rows = sectorRows
            if rows.isEmpty {
                Text(model.marketLoading ? "Loading…" : "Waiting on sector quotes…")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .pnLines(20, size: 14, face: .sans)
                    .padding(.vertical, 12)
            } else {
                VStack(spacing: 6) {
                    ForEach(rows, id: \.ticker) { row in
                        MacBureauPulseSectorRow(label: row.label, ticker: row.ticker, change: row.quote.pct) {
                            store.showTicker(row.ticker)
                        }
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func macroTray(viewport: CGFloat) -> some View {
        let columns = viewport >= 1280 ? 9 : (viewport >= 768 ? 5 : (viewport >= 640 ? 3 : 2))
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Rates · FX · commodities · vol")
                .padding(.bottom, 8)
            MacBureauPNGrid(columns: columns, spacing: 8, items: MacBureauPulseTape.macro.map(\.ticker)) { ticker in
                let label = MacBureauPulseTape.macro.first { $0.ticker == ticker }?.label ?? ticker
                macroCell(ticker: ticker, label: label)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func macroCell(ticker: String, label: String) -> some View {
        let quote = model.quote(ticker)
        return MacBureauPNPlate(fill: ink.fillTertiary.opacity(0.5), hoverFill: nil) {
            store.showTicker(ticker)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauPNLine(label, size: 11, tracking: 0.066, line: 14, color: ink.muted)
                    .truncationMode(.tail)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(ticker)
                        .font(MacBureauPNFace.mono(12))
                        .foregroundStyle(ink.ink)
                    Spacer(minLength: 0)
                    Text(MacBureauPNFormat.pct(quote?.pct))
                        .font(BSHType.bureauSans(14).monospacedDigit())
                        .tracking(-0.084)
                        .foregroundStyle(changeTone(quote?.pct))
                }
                .frame(height: 20)
                .padding(.top, 2)
                if let price = MacBureauPNFormat.price(quote?.last) {
                    MacBureauPNLine(price, size: 14, tracking: -0.084, line: 20, color: ink.ink, tabular: true)
                        .padding(.top, 2)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: Movers and the week

    private func moversSection(viewport: CGFloat) -> some View {
        let buckets: [(id: String, title: String, icon: String, rows: [MacBureauPulseModel.Mover])] = [
            ("gainers", "Gainers", "trending-up", model.screener.gainers),
            ("losers", "Losers", "trending-down", model.screener.losers),
            ("active", "Most active", "activity", model.screener.active),
        ]
        return VStack(alignment: .leading, spacing: 8) {
            MacBureauPNLabel("US session movers")
            MacBureauPNGrid(columns: viewport >= 1024 ? 3 : 1, spacing: 12, items: buckets.map(\.id)) { id in
                if let bucket = buckets.first(where: { $0.id == id }) {
                    MacBureauPulseMoverList(
                        title: bucket.title,
                        icon: bucket.icon,
                        rows: bucket.rows,
                        loading: model.marketLoading
                    ) { store.showTicker($0) }
                }
            }
        }
    }

    private func calendarTray(viewport: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauPNLabel("This week’s catalysts")
                Spacer(minLength: 8)
                MacBureauPNLine("Earnings · dividends · macro", size: 11, tracking: 0.066, line: 14, color: ink.muted)
            }
            .padding(.bottom, 8)
            let days = MacBureauPulseWeek.buckets(model.calendar)
            MacBureauPNGrid(columns: viewport >= 640 ? 7 : 1, spacing: 8, items: days.map(\.key), equalHeights: true) { key in
                if let day = days.first(where: { $0.key == key }) {
                    MacBureauPulseDayCell(day: day) { store.showTicker($0) }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    @ViewBuilder
    private func weekSection(viewport: CGFloat) -> some View {
        if !model.weeklyLoaded {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small).frame(width: 16, height: 16)
                Text("Loading weekly brief…")
            }
            .font(BSHType.bureauSans(14))
            .tracking(-0.084)
            .foregroundStyle(ink.muted)
            .padding(.vertical, 24)
        } else if let summary = model.summary {
            MacBureauPulseWeek(summary: summary, zh: zh, viewport: viewport) { store.showTicker($0) }
        } else {
            emptyWeek
        }
    }

    private var emptyWeek: some View {
        VStack(spacing: 0) {
            LucideIcon("bsh-pulse", size: 28)
                .foregroundStyle(ink.accent)
            Text("No researched brief yet")
                .font(.custom(BSHType.bureauSerif, size: 23))
                .tracking(-0.23)
                .foregroundStyle(ink.ink)
                .frame(height: 28)
                .padding(.top, 12)
            Text("Live US tape above is already loading. Refresh to research the week’s hottest names and publish the narrative board.")
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(20, size: 14, face: .sans)
                .frame(maxWidth: 576)
                .padding(.top, 8)
            MacBureauButton("Refresh brief", icon: "refresh-cw", kind: .filled, busy: weeklyRunning) {
                openWeb("weekly-summary")
            }
            .help("The weekly research runs on the website: this opens its Pulse beside the page.")
            .padding(.top, 16)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 32)
        .frame(maxWidth: .infinity)
        .pnTray()
    }

    // MARK: Research signals

    private var signalRows: [MacBureauPNJSON] {
        Array((model.signalsPage?.object("sections")?.objects("ranked_signals") ?? []).prefix(10))
    }

    private var changedSince: MacBureauPNJSON? {
        model.signalsPage?.object("sections")?.object("changed_since_last_week")
    }

    private func changedCount(_ lists: [String], count: String) -> Int {
        for key in lists {
            let n = changedSince?.count(key) ?? 0
            if n > 0 { return n }
        }
        return Int(changedSince?.double(count) ?? 0)
    }

    private func signalsRow(viewport: CGFloat) -> some View {
        MacBureauPNGrid(columns: viewport >= 1024 ? 2 : 1, spacing: 16, items: ["signals", "changed"], equalHeights: true) { id in
            if id == "signals" { signalsTray } else { changedTray }
        }
    }

    private var signalsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauPNLabel("Research signals")
                Spacer(minLength: 8)
                MacBureauPNLink(title: "Signals lab", size: 11) { openWeb("innovation-lab/market-pulse") }
            }
            .padding(.bottom, 8)
            let rows = signalRows
            if rows.isEmpty {
                Text("No ranked signals yet. Open Signals after a Stock Research aggregate.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(20, size: 14, face: .sans)
                    .padding(.vertical, 12)
            } else {
                MacBureauPNGrid(columns: 2, spacing: 8, items: rows.indices.map { $0 }) { index in
                    MacBureauPulseSignalCard(signal: rows[index]) { ticker in store.showTicker(ticker) }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .pnTray()
    }

    private var changedTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Changed since last week")
                .padding(.bottom, 8)
            HStack(spacing: 8) {
                statCell("New", value: "\(changedCount(["added", "new"], count: "added_count"))", tone: ink.ink, fill: 0.5, centered: true)
                statCell("Out", value: "\(changedCount(["removed"], count: "removed_count"))", tone: ink.ink, fill: 0.5, centered: true)
                statCell("Moved", value: "\(changedCount(["changed", "updated"], count: "changed_count"))", tone: ink.ink, fill: 0.5, centered: true)
            }
            MacBureauPNLine("Full doctor and source traces live in Signals.", size: 11, tracking: 0.066, line: 14, color: ink.muted)
                .padding(.top, 8)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .pnTray()
    }
}

// MARK: - The Morning Brief, printed

/// `.morning-brief`: a front page in a tray. The dateline in brass capitals, the headline
/// and its dek in the reading serif (New York, `ui-serif`), the facts in the interface
/// face, then the sections two to a row, each under its own rule.
struct MacBureauPulseArticle: View {
    @Environment(\.colorScheme) private var colorScheme
    let brief: MacBureauPNJSON
    let note: MacBureauPNJSON
    let zh: Bool
    let viewport: CGFloat

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var sections: [MacBureauPNJSON] { note.pickArray("sections", zh: zh).compactMap { MacBureauPNJSON($0) } }
    private var bullets: [String] { note.pickArray("bullets", zh: zh).compactMap { $0 as? String } }

    private var dateline: String {
        guard let day = MacBureauPNFormat.day(brief.string("date")) else { return "Morning brief".uppercased() }
        return MacBureauPNFormat.longDay(day).uppercased()
    }

    /// `briefReadMinutes`: about 230 words a minute (400 characters for Chinese).
    private var readMinutes: Int {
        let text = (sections.map { $0.string("body") ?? "" } + bullets).joined(separator: " ")
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return 0 }
        if zh {
            let han = text.unicodeScalars.filter { (0x3400...0x9FFF).contains($0.value) }.count
            return max(1, Int((Double(han) / 400).rounded()))
        }
        let words = text.split(whereSeparator: { $0.isWhitespace }).count
        return max(1, Int((Double(words) / 230).rounded()))
    }

    private var sourceCount: Int { note.bool("researched") ? note.count("sources") : 0 }

    /// The headline takes a front page's size on a wide window, less on a narrow one.
    private var headlineMetrics: (size: CGFloat, line: CGFloat, tracking: CGFloat) {
        if viewport >= 1024 { return (36, 41.04, -0.792) }
        if viewport >= 640 { return (30, 35.4, -0.54) }
        return (23, 28.06, -0.322)
    }

    private var columns: Int { viewport >= 1800 ? 3 : (viewport >= 1024 ? 2 : 1) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            masthead
            if !bullets.isEmpty {
                bulletList.padding(.top, 10)
            }
            if !sections.isEmpty {
                sectionGrid
            }
            if note.string("length") == "long" {
                foot
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private var masthead: some View {
        let headline = headlineMetrics
        let dek = note.pick("dek", zh: zh)
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLine(dateline, size: 11, weight: .semibold, tracking: 0.88, line: 14, color: ink.accentInk)
            Text(note.pick("headline", zh: zh))
                .font(MacBureauPNFace.reading(headline.size, weight: .semibold))
                .tracking(headline.tracking)
                .foregroundStyle(ink.ink)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(headline.line, size: headline.size, face: .reading)
                .padding(.top, 10)
            if !dek.isEmpty {
                Text(dek)
                    .font(MacBureauPNFace.reading(viewport >= 640 ? 19 : 17))
                    .tracking(-0.076)
                    .foregroundStyle(ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(viewport >= 640 ? 28.5 : 25.5, size: viewport >= 640 ? 19 : 17, face: .reading)
                    .padding(.top, 8)
            }
            meta.padding(.top, 12)
        }
    }

    /// The facts, each after a centred dot but the first.
    private var meta: some View {
        let stamp = MacBureauPNFormat.stamp(note.string("generated_at")) ?? brief.string("date") ?? ""
        var facts = ["Frozen \(stamp)"]
        if !sections.isEmpty { facts.append("\(sections.count) sections") }
        if readMinutes > 0 { facts.append("\(readMinutes) min read") }
        if sourceCount > 0 { facts.append("\(sourceCount) sources") }
        return HStack(spacing: 0) {
            ForEach(Array(facts.enumerated()), id: \.offset) { index, fact in
                MacBureauPNLine(fact, size: 11, tracking: 0.066, line: 14, color: ink.muted)
                    .padding(.leading, index == 0 ? 0 : 14)
                    .overlay(alignment: .leading) {
                        if index > 0 {
                            MacBureauPNLine("·", size: 11, tracking: 0.066, line: 14, color: ink.muted)
                                .offset(x: 4.8)
                        }
                    }
            }
        }
    }

    private var bulletList: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(bullets.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(MacBureauPNFace.reading(17))
                    .tracking(-0.068)
                    .foregroundStyle(ink.ink(0.85))
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(27.2, size: 17, face: .reading)
                    .padding(.leading, 18)
                    .overlay(alignment: .topLeading) {
                        Circle().fill(ink.accent).frame(width: 4, height: 4).padding(.top, 9.6)
                    }
            }
        }
        .frame(maxWidth: 560, alignment: .leading)
    }

    private var sectionGrid: some View {
        let rows = stride(from: 0, to: sections.count, by: columns).map { Array(sections[$0..<min($0 + columns, sections.count)]) }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top, spacing: 36) {
                    ForEach(Array(row.enumerated()), id: \.offset) { _, section in
                        sectionView(section)
                    }
                    ForEach(0..<(columns - row.count), id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity, maxHeight: 1)
                    }
                }
            }
        }
    }

    private func sectionView(_ section: MacBureauPNJSON) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Rectangle().fill(ink.rule).frame(height: 1)
            Text(section.string("title") ?? "")
                .font(MacBureauPNFace.reading(17, weight: .semibold))
                .tracking(-0.136)
                .foregroundStyle(ink.ink)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(22, size: 17, face: .reading)
                .padding(.top, 14)
            Text(section.string("body") ?? "")
                .font(MacBureauPNFace.reading(16))
                .tracking(-0.048)
                .foregroundStyle(ink.ink(0.85))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(26.4, size: 16, face: .reading)
                .padding(.top, 6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 14)
    }

    /// A long note makes claims about the world, so it shows what it read.
    private var foot: some View {
        let sources = note.objects("sources")
        return VStack(alignment: .leading, spacing: 0) {
            Rectangle().fill(ink.rule).frame(height: 1)
            Group {
                if note.bool("researched"), !sources.isEmpty {
                    sourcesLine(sources)
                } else {
                    Text("Written without live sources — treat the world view as unverified.")
                }
            }
            .font(BSHType.bureauSans(11))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .fixedSize(horizontal: false, vertical: true)
            .pnLines(14, size: 11, face: .sans)
            .padding(.top, 12)
        }
        .fixedSize(horizontal: true, vertical: false)
        .frame(maxWidth: 560, alignment: .leading)
        .padding(.top, 14)
    }

    private func sourcesLine(_ sources: [MacBureauPNJSON]) -> Text {
        var line = Text("Researched from \(sources.count) sources:")
        for (index, source) in sources.prefix(4).enumerated() {
            let title = source.string("title") ?? source.string("url") ?? ""
            var link = AttributedString(title)
            if let raw = source.string("url"), let url = URL(string: raw) { link.link = url }
            link.underlineStyle = Text.LineStyle(pattern: .dot)
            link.foregroundColor = ink.muted
            line = line + Text(index == 0 ? " " : " · ") + Text(link)
        }
        return line
    }
}

/// The note while the morning schedule writes it: the shape of the report it will hold.
struct MacBureauPulseNoteSkeleton: View {
    @Environment(\.colorScheme) private var colorScheme
    let viewport: CGFloat

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauKicker("Morning brief")
                Spacer(minLength: 8)
                HStack(spacing: 4) {
                    ProgressView().controlSize(.mini)
                    Text("Writing the brief…")
                }
                .font(BSHType.bureauSans(11, weight: .semibold))
                .foregroundStyle(ink.accentInk)
                .padding(.horizontal, 8)
                .frame(height: 18)
                .background(Capsule().fill(ink.accent.opacity(0.1)))
            }
            bar(ink, width: 0.8, max: 576, height: 24).padding(.top, 10)
            bar(ink, width: 0.4, max: 288, height: 14).padding(.top, 6)
            HStack(alignment: .top, spacing: 36) {
                ForEach(0..<(viewport >= 1024 ? 2 : 1), id: \.self) { _ in
                    VStack(alignment: .leading, spacing: 6) {
                        Rectangle().fill(ink.rule).frame(height: 1).padding(.bottom, 8)
                        bar(ink, width: 0.6, max: .infinity, height: 16)
                        bar(ink, width: 1, max: .infinity, height: 12).padding(.top, 2)
                        bar(ink, width: 1, max: .infinity, height: 12)
                        bar(ink, width: 0.92, max: .infinity, height: 12)
                        bar(ink, width: 0.8, max: .infinity, height: 12)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.top, 14)
            Rectangle().fill(ink.rule).frame(height: 1).padding(.top, 14)
            Text("Reading the tape and the news behind it. This usually takes about a minute and a half.")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .padding(.top, 12)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func bar(_ ink: MacBureauPageInk, width: CGFloat, max: CGFloat, height: CGFloat) -> some View {
        GeometryReader { proxy in
            Capsule().fill(ink.fillTertiary).frame(width: min(max, proxy.size.width * width), height: height)
        }
        .frame(height: height)
    }
}

// MARK: - Pieces

/// A plate that is a button: a filled rounded square that navigates.
struct MacBureauPNPlate<Label: View>: View {
    let fill: Color
    var hoverFill: Color?
    var radius: CGFloat = 9
    let action: () -> Void
    @ViewBuilder var label: () -> Label
    @State private var hovered = false

    init(fill: Color, hoverFill: Color?, radius: CGFloat = 9, action: @escaping () -> Void, @ViewBuilder label: @escaping () -> Label) {
        self.fill = fill
        self.hoverFill = hoverFill
        self.radius = radius
        self.action = action
        self.label = label
    }

    var body: some View {
        Button(action: action) {
            label()
                .background(RoundedRectangle(cornerRadius: radius, style: .circular).fill(hovered ? (hoverFill ?? fill) : fill))
                .contentShape(RoundedRectangle(cornerRadius: radius))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// A grouped card that is a button (`news-grouped` on a `<button>`).
struct MacBureauPNCardButton<Label: View>: View {
    let action: () -> Void
    @ViewBuilder var label: () -> Label

    var body: some View {
        Button(action: action) {
            label()
                .pnTray()
                .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }
}

/// A CSS grid of equal columns: rows of `columns` cells, `spacing` apart both ways.
struct MacBureauPNGrid<Item: Hashable, Cell: View>: View {
    let columns: Int
    let spacing: CGFloat
    let items: [Item]
    var equalHeights = false
    @ViewBuilder var cell: (Item) -> Cell

    init(columns: Int, spacing: CGFloat, items: [Item], equalHeights: Bool = false, @ViewBuilder cell: @escaping (Item) -> Cell) {
        self.columns = max(1, columns)
        self.spacing = spacing
        self.items = items
        self.equalHeights = equalHeights
        self.cell = cell
    }

    var body: some View {
        let rows = stride(from: 0, to: items.count, by: columns).map { Array(items[$0..<min($0 + columns, items.count)]) }
        VStack(alignment: .leading, spacing: spacing) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top, spacing: spacing) {
                    ForEach(row, id: \.self) { item in
                        cell(item)
                            .frame(maxWidth: .infinity, maxHeight: equalHeights ? .infinity : nil, alignment: .topLeading)
                    }
                    ForEach(0..<(columns - row.count), id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity, maxHeight: 1)
                    }
                }
                .fixedSize(horizontal: false, vertical: equalHeights)
            }
        }
    }
}

/// One sector fund: its name, a bar as long as its move, its ticker and its move.
struct MacBureauPulseSectorRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let label: String
    let ticker: String
    let change: Double?
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let up = (change ?? 0) >= 0
        Button(action: action) {
            GeometryReader { proxy in
                // grid-cols-[minmax(8rem,14rem)_1fr_minmax(4rem,5rem)_minmax(4.5rem,6rem)], gap 12.
                let inner = proxy.size.width - 16
                let first = min(224, max(128, inner * 0.2))
                let third: CGFloat = 80
                let fourth: CGFloat = 96
                let bar = max(0, inner - first - third - fourth - 36)
                HStack(spacing: 12) {
                    MacBureauPNLine(label, size: 14, tracking: -0.084, line: 20, color: ink.secondary)
                        .frame(width: first, alignment: .leading)
                    ZStack(alignment: .leading) {
                        Capsule().fill(ink.fillTertiary)
                        Capsule()
                            .fill(up ? ink.success : ink.danger)
                            .frame(width: bar * min(1, (abs(change ?? 0) * 18 + 8) / 100))
                    }
                    .frame(width: bar, height: 6)
                    Text(ticker)
                        .font(MacBureauPNFace.mono(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .frame(width: third, alignment: .trailing)
                    MacBureauPNLine(MacBureauPNFormat.pct(change), size: 14, tracking: -0.084, line: 20, color: change == nil ? ink.muted : (up ? ink.successInk : ink.dangerInk), tabular: true)
                        .frame(width: fourth, alignment: .trailing)
                }
                .padding(.horizontal, 8)
                .frame(height: 32)
            }
            .frame(height: 32)
            .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(hovered ? ink.fillTertiary.opacity(0.5) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// One of the session's mover lists: a header in small capitals, then ten rows.
struct MacBureauPulseMoverList: View {
    @Environment(\.colorScheme) private var colorScheme
    let title: String
    let icon: String
    let rows: [MacBureauPulseModel.Mover]
    let loading: Bool
    let open: (String) -> Void

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                LucideIcon(icon, size: 14)
                Text(title.uppercased())
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .tracking(0.44)
            }
            .foregroundStyle(ink.muted)
            .padding(.horizontal, 12)
            .frame(height: 30, alignment: .center)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(ink.rule.opacity(0.7)).frame(height: 1) }
            .padding(.bottom, 1)

            if rows.isEmpty {
                Text(loading ? "Loading…" : "No screener rows yet.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 16)
            }
            ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                MacBureauPulseMoverRow(row: row, last: index == rows.count - 1) { open(row.ticker) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        .pnTray()
    }
}

struct MacBureauPulseMoverRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauPulseModel.Mover
    let last: Bool
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(row.ticker)
                        .font(MacBureauPNFace.mono(14, weight: .semibold))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                        .pnLines(20, size: 14, face: .mono)
                    MacBureauPNLine(row.name ?? row.ticker, size: 11, tracking: 0.066, line: 14, color: ink.muted)
                        .truncationMode(.tail)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 0) {
                    MacBureauPNLine(row.last.map { String(format: "%.2f", $0) } ?? "—", size: 14, tracking: -0.084, line: 20, color: ink.ink, tabular: true)
                    MacBureauPNLine(MacBureauPNFormat.pct(row.change), size: 11, tracking: 0.066, line: 14, color: row.change == nil ? ink.muted : ((row.change ?? 0) >= 0 ? ink.successInk : ink.dangerInk), tabular: true)
                }
                .fixedSize()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(hovered ? ink.fillTertiary.opacity(0.4) : .clear)
            .overlay(alignment: .bottom) {
                if !last { Rectangle().fill(ink.rule.opacity(0.4)).frame(height: 1) }
            }
            .padding(.bottom, last ? 0 : 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// One research signal (the signals page's ranked list).
struct MacBureauPulseSignalCard: View {
    @Environment(\.colorScheme) private var colorScheme
    let signal: MacBureauPNJSON
    let open: (String) -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let ticker = signal.string("ticker")
        Button {
            if let ticker { open(ticker) }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 8) {
                    Text(signal.string("title") ?? signal.string("theme") ?? ticker ?? "Signal")
                        .font(BSHType.bureauSans(14, weight: .medium))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                    Spacer(minLength: 0)
                    if let direction = signal.string("direction") {
                        Text(direction.uppercased())
                            .font(BSHType.bureauSans(11))
                            .tracking(0.066)
                            .foregroundStyle(ink.muted)
                    }
                }
                Text(signal.string("summary") ?? signal.string("rationale") ?? signal.string("why") ?? "")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.secondary)
                    .lineLimit(2)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(hovered ? ink.fillTertiary.opacity(0.4) : .clear))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .circular).strokeBorder(ink.rule.opacity(0.6), lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - The week's calendar

extension MacBureauPulseWeek {
    struct Day: Identifiable {
        let key: String
        let label: String
        var events: [MacCalendarEvent]
        var id: String { key }
    }

    /// `calendarWeekBuckets`: Monday to Sunday of this week, each with its events.
    static func buckets(_ events: [MacCalendarEvent], now: Date = Date()) -> [Day] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .current
        let today = calendar.startOfDay(for: now)
        let weekday = calendar.component(.weekday, from: today) // 1 = Sunday
        let mondayOffset = weekday == 1 ? -6 : 2 - weekday
        let monday = calendar.date(byAdding: .day, value: mondayOffset, to: today) ?? today
        let keyFormat = DateFormatter()
        keyFormat.locale = Locale(identifier: "en_US_POSIX")
        keyFormat.dateFormat = "yyyy-MM-dd"
        let labelFormat = DateFormatter()
        labelFormat.locale = Locale(identifier: "en_US")
        labelFormat.dateFormat = "EEE, MM/dd"
        var days: [Day] = (0..<7).compactMap { offset in
            guard let date = calendar.date(byAdding: .day, value: offset, to: monday) else { return nil }
            return Day(key: keyFormat.string(from: date), label: labelFormat.string(from: date), events: [])
        }
        for event in events {
            let key = String(event.date.prefix(10))
            if let index = days.firstIndex(where: { $0.key == key }) { days[index].events.append(event) }
        }
        return days
    }
}

/// One day of the week: its date, then up to four of its events.
struct MacBureauPulseDayCell: View {
    @Environment(\.colorScheme) private var colorScheme
    let day: MacBureauPulseWeek.Day
    let open: (String) -> Void

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLine(day.label, size: 11, weight: .medium, tracking: 0.066, line: 14, color: ink.muted)
            if day.events.isEmpty {
                MacBureauPNLine("—", size: 11, tracking: 0.066, line: 14, color: ink.subtle)
                    .padding(.top, 4)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(day.events.prefix(4).enumerated()), id: \.offset) { _, event in
                        eventLine(event, ink: ink)
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .overlay(RoundedRectangle(cornerRadius: 9, style: .circular).strokeBorder(ink.rule.opacity(0.6), lineWidth: 1))
    }

    @ViewBuilder
    private func eventLine(_ event: MacCalendarEvent, ink: MacBureauPageInk) -> some View {
        let lead: Text = {
            if let ticker = event.ticker, !ticker.isEmpty {
                return Text(ticker).font(MacBureauPNFace.mono(11)).foregroundColor(ink.ink)
            }
            return Text(event.title.isEmpty ? event.kind : event.title).foregroundColor(ink.secondary)
        }()
        let line = (lead + Text(" · \(event.kind)").foregroundColor(ink.muted))
            .font(BSHType.bureauSans(11))
            .tracking(0.066)
            .lineLimit(1)
            .truncationMode(.tail)
            .pnLines(14, size: 11, face: .sans)
        if let ticker = event.ticker, !ticker.isEmpty {
            Button { open(ticker) } label: { line }.buttonStyle(.plain)
        } else {
            line
        }
    }
}

// MARK: - The researched week

/// The weekly research when it exists: the week's narrative with its cards, the ranked
/// setups, the watchlist and sources, and the mix of themes.
struct MacBureauPulseWeek: View {
    @Environment(\.colorScheme) private var colorScheme
    let summary: MacBureauPNJSON
    let zh: Bool
    let viewport: CGFloat
    let open: (String) -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if summary.bool("scan_fallback") {
                HStack(alignment: .top, spacing: 8) {
                    LucideIcon("triangle-alert", size: 16).padding(.top, 2)
                    Text(summary.string("scan_mode") == "market_data"
                         ? "AI research was unavailable for this refresh, so these movers are ranked from market data. The price moves are real; the catalysts behind them have not been researched."
                         : "The live market scan failed for this refresh. Rankings were seeded from a static watchlist — treat narratives as unverified.")
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.warningInk)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.warning.opacity(0.12)))
                .overlay(RoundedRectangle(cornerRadius: 9, style: .circular).strokeBorder(ink.warning.opacity(0.4), lineWidth: 1))
            }
            narrative
            setups
            MacBureauPNGrid(columns: viewport >= 1024 ? 2 : 1, spacing: 16, items: ["watch", "sources"], equalHeights: true) { id in
                if id == "watch" { watchlist } else { sources }
            }
            if !summary.objects("sector_mix").isEmpty {
                themes
            }
        }
    }

    private var narrative: some View {
        let cards = summary.objects("summary_cards")
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Week narrative").padding(.bottom, 8)
            paragraph(summary.pick("market_pulse", zh: zh), color: ink.secondary)
            let context = summary.pick("benchmark_context", zh: zh)
            if !context.isEmpty {
                paragraph(context, color: ink.muted).padding(.top, 8)
            }
            if !cards.isEmpty {
                MacBureauPNGrid(columns: viewport >= 1024 ? 4 : 2, spacing: 8, items: cards.indices.map { $0 }) { index in
                    let card = cards[index]
                    VStack(alignment: .leading, spacing: 2) {
                        MacBureauPNLine(card.pick("label", zh: zh), size: 11, tracking: 0.066, line: 14, color: ink.muted)
                        MacBureauPNLine(card.string("value") ?? "", size: 14, weight: .semibold, tracking: -0.084, line: 20, color: ink.ink)
                        Text(card.pick("note", zh: zh))
                            .font(BSHType.bureauSans(11))
                            .tracking(0.066)
                            .foregroundStyle(ink.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.fillTertiary.opacity(0.5)))
                }
                .padding(.top, 12)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private func paragraph(_ text: String, color: Color) -> some View {
        Text(text)
            .font(BSHType.bureauSans(14))
            .tracking(-0.084)
            .foregroundStyle(color)
            .fixedSize(horizontal: false, vertical: true)
            .pnLines(22.75, size: 14, face: .sans)
    }

    private var setups: some View {
        let stocks = summary.objects("stocks")
        let marketData = summary.string("scan_mode") == "market_data"
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                MacBureauPNLabel(marketData ? "Top movers (price data only)" : "Researched setups")
                Spacer()
                MacBureauPNLine("\(stocks.count) names", size: 11, tracking: 0.066, line: 14, color: ink.muted)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .overlay(alignment: .bottom) { Rectangle().fill(ink.rule.opacity(0.7)).frame(height: 1) }
            HStack(spacing: 0) {
                ForEach(["#", "Symbol", "1W", "Rel vol", "RS", "Score", "Thesis"], id: \.self) { title in
                    Text(title.uppercased())
                        .font(BSHType.bureauSans(11))
                        .tracking(0.44)
                        .foregroundStyle(ink.muted)
                        .frame(width: columnWidth(title), alignment: .leading)
                        .frame(maxWidth: title == "Thesis" ? .infinity : nil, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                }
            }
            ForEach(Array(stocks.enumerated()), id: \.offset) { _, stock in
                setupRow(stock)
                    .overlay(alignment: .top) { Rectangle().fill(ink.rule.opacity(0.5)).frame(height: 1) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        .pnTray()
    }

    private func columnWidth(_ title: String) -> CGFloat? {
        switch title {
        case "#": return 16
        case "Symbol": return 176
        case "1W", "Rel vol", "RS": return 56
        case "Score": return 44
        default: return nil
        }
    }

    private func setupRow(_ stock: MacBureauPNJSON) -> some View {
        let ticker = stock.string("ticker") ?? ""
        let score = stock.double("score") ?? 0
        let unverified = stock.bool("is_fallback") || summary.bool("scan_fallback")
        let scoreTone = unverified ? ink.secondary : (score >= 85 ? ink.successInk : (score >= 70 ? ink.warningInk : ink.secondary))
        return HStack(alignment: .top, spacing: 0) {
            cell("#") { Text(stock.string("rank") ?? "").font(BSHType.bureauSans(11)).foregroundStyle(ink.muted) }
            cell("Symbol") {
                VStack(alignment: .leading, spacing: 0) {
                    Button { open(ticker) } label: {
                        Text(ticker).font(MacBureauPNFace.mono(13, weight: .semibold)).foregroundStyle(ink.ink)
                    }
                    .buttonStyle(.plain)
                    Text(stock.string("name") ?? "").font(BSHType.bureauSans(11)).foregroundStyle(ink.muted).lineLimit(1)
                    let sector = stock.pick("sector", zh: zh)
                    if !sector.isEmpty { Text(sector).font(BSHType.bureauSans(11)).foregroundStyle(ink.subtle) }
                }
            }
            cell("1W") {
                let change = stock.double("weekly_change_pct")
                Text(MacBureauPNFormat.pct(change)).font(BSHType.bureauSans(13).monospacedDigit())
                    .foregroundStyle(change == nil ? ink.muted : ((change ?? 0) >= 0 ? ink.successInk : ink.dangerInk))
            }
            cell("Rel vol") {
                Text(stock.double("relative_volume").map { String(format: "%.1fx", $0) } ?? "n/a")
                    .font(BSHType.bureauSans(13).monospacedDigit()).foregroundStyle(ink.ink)
            }
            cell("RS") {
                Text(MacBureauPNFormat.pct(stock.double("relative_strength_pct"))).font(BSHType.bureauSans(13).monospacedDigit()).foregroundStyle(ink.ink)
            }
            cell("Score") {
                Text("\(Int(score.rounded()))").font(BSHType.bureauSans(13, weight: .semibold).monospacedDigit()).foregroundStyle(scoreTone)
            }
            cell("Thesis") {
                VStack(alignment: .leading, spacing: 4) {
                    Text(stock.pick("why_awesome", zh: zh)).font(BSHType.bureauSans(14)).tracking(-0.084).foregroundStyle(ink.secondary)
                    let catalyst = stock.pick("catalyst", zh: zh)
                    if !catalyst.isEmpty { Text(catalyst).font(BSHType.bureauSans(11)).foregroundStyle(ink.muted) }
                    let risk = stock.pick("risk", zh: zh)
                    if !risk.isEmpty { Text(risk).font(BSHType.bureauSans(11)).foregroundStyle(ink.warningInk) }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func cell<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        content()
            .frame(width: columnWidth(title), alignment: .leading)
            .frame(maxWidth: title == "Thesis" ? .infinity : nil, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
    }

    private var watchlist: some View {
        let items = summary.objects("watchlist")
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Watchlist").padding(.bottom, 8)
            if items.isEmpty {
                Text("No watchlist items this week.")
                    .font(BSHType.bureauSans(14)).tracking(-0.084).foregroundStyle(ink.muted)
                    .padding(.vertical, 12)
            }
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                let ticker = item.string("ticker") ?? ""
                Button { open(ticker) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        (Text(ticker).font(MacBureauPNFace.mono(13, weight: .semibold)).foregroundColor(ink.ink)
                         + Text("  \(item.string("name") ?? "")").font(BSHType.bureauSans(13)).foregroundColor(ink.muted))
                        Text(item.pick("reason", zh: zh)).font(BSHType.bureauSans(14)).tracking(-0.084).foregroundStyle(ink.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .overlay(alignment: .top) { if index > 0 { Rectangle().fill(ink.rule.opacity(0.6)).frame(height: 1) } }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .pnTray()
    }

    private var sources: some View {
        let items = summary.objects("sources")
        return VStack(alignment: .leading, spacing: 4) {
            MacBureauPNLabel("Sources").padding(.bottom, 4)
            ForEach(Array(items.enumerated()), id: \.offset) { _, source in
                Button {
                    if let raw = source.string("url"), let url = URL(string: raw) { NSWorkspace.shared.open(url) }
                } label: {
                    HStack(alignment: .top, spacing: 8) {
                        LucideIcon("external-link", size: 14).foregroundStyle(ink.muted).padding(.top, 3)
                        VStack(alignment: .leading, spacing: 0) {
                            Text(source.pick("label", zh: zh)).font(BSHType.bureauSans(14)).tracking(-0.084).foregroundStyle(ink.secondary).lineLimit(1)
                            if let date = source.string("date") {
                                Text(date).font(BSHType.bureauSans(11)).foregroundStyle(ink.muted)
                            }
                        }
                    }
                    .padding(.horizontal, 4)
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .pnTray()
    }

    private var themes: some View {
        let mix = summary.objects("sector_mix")
        let most = max(1, mix.map { $0.double("count") ?? 0 }.max() ?? 1)
        return VStack(alignment: .leading, spacing: 8) {
            MacBureauPNLabel("Theme mix in the brief")
            ForEach(Array(mix.enumerated()), id: \.offset) { _, sector in
                let count = sector.double("count") ?? 0
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(sector.pick("sector", zh: zh)).foregroundStyle(ink.secondary)
                        Spacer()
                        Text("\(Int(count))").font(MacBureauPNFace.mono(11)).foregroundStyle(ink.muted)
                    }
                    .font(BSHType.bureauSans(11))
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(ink.fillTertiary)
                            Capsule().fill(ink.accent).frame(width: proxy.size.width * max(0.08, count / most))
                        }
                    }
                    .frame(height: 6)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }
}

// MARK: - The signal ledger

/// The calls logged from the desks, scored against the tape since (the website shows the
/// ledger only when it holds any).
struct MacBureauPulseLedger: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let rows = store.signals
        let scored = rows.compactMap(\.scorePct)
        let hits = scored.filter { $0 > 0 }.count
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 12) {
                MacBureauPNLabel("Signal ledger")
                Spacer()
                Group {
                    if !scored.isEmpty {
                        Text("Hit rate \(Int((Double(hits) / Double(scored.count) * 100).rounded()))%")
                        Text("Avg \(MacBureauPNFormat.signed(scored.reduce(0, +) / Double(scored.count)) ?? "")")
                    }
                    Text("\(rows.count) calls")
                }
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
            }
            .padding(.bottom, 4)
            ForEach(rows.prefix(8)) { row in
                HStack(spacing: 8) {
                    Button { store.showTicker(row.ticker) } label: {
                        HStack(spacing: 8) {
                            Text(row.ticker).font(BSHType.bureauSans(12).monospacedDigit()).foregroundStyle(ink.ink)
                            Text(row.direction.uppercased()).font(BSHType.bureauSans(11)).foregroundStyle(ink.muted)
                            Text(row.label ?? "").font(BSHType.bureauSans(11)).foregroundStyle(ink.secondary).lineLimit(1)
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if let score = row.scorePct {
                        Text(MacBureauPNFormat.signed(score) ?? "")
                            .font(BSHType.bureauSans(11).monospacedDigit())
                            .foregroundStyle(score >= 0 ? ink.success : ink.danger)
                    } else {
                        Text("Pending").font(BSHType.bureauSans(11)).foregroundStyle(ink.subtle)
                    }
                    Button("Drop") { Task { await store.deleteSignal(id: row.id) } }
                        .buttonStyle(.plain)
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.muted)
                        .disabled(!store.canWriteDesk)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }
}
