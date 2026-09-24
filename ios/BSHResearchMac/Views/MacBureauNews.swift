//
//  MacBureauNews.swift
//  BSHResearchMac
//
//  Bureau's News is the website's front page (NewsDeskView.vue, HomeNewsDesk.vue and
//  HomeMarketPanel.vue under MarketsView.vue): the Market · Pulse · News sub-nav, today's
//  date over the title, the live tape, the companies you follow, the filters and search,
//  the lead story with its buttons and its briefing, the latest stories under it, and the
//  Markets column beside them.
//
//  The story is read where the website shows it: the one chosen from Latest becomes the
//  lead, and its briefing loads in the lead's lower half, as the Mac's reader did. The
//  cadence of the scheduled briefings and "Refresh AI briefs now" are the website's own
//  controls (the Mac has no call for them), so they open its News desk beside the page.
//

import AppKit
import SwiftUI

// MARK: - Rows

/// One story on the desk: the Mac's news item and the workspace company it names.
struct MacBureauNewsRow: Identifiable, Hashable {
    let item: MacNewsItem
    let company: MacCompany?
    var id: String { item.id }

    /// A story that names none of the workspace's companies is market news.
    var market: Bool { company == nil }

    /// Ticker, else company: the kicker above a headline.
    var kicker: String? {
        let ticker = (item.ticker ?? "").trimmingCharacters(in: .whitespaces)
        if !ticker.isEmpty { return ticker.uppercased() }
        if let name = item.companyName, !name.isEmpty { return name }
        return company?.name
    }

    /// `storyByline`: the source (or the company) and how long ago.
    var byline: String {
        let source = [item.source, item.companyName, company?.name].compactMap { $0 }.first { !$0.isEmpty } ?? ""
        return [source, MacBureauPNFormat.age(item.publishedAt) ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var canRead: Bool { item.url.flatMap(URL.init(string:)) != nil }

    /// The story as the briefing knows it: the server keys a briefing by headline and
    /// company, and the website names the company the story matched.
    var briefItem: MacNewsItem {
        guard (item.companyName ?? "").isEmpty, let name = company?.name, !name.isEmpty else { return item }
        return MacNewsItem(
            id: item.id, title: item.title, summary: item.summary, source: item.source,
            publishedAt: item.publishedAt, ticker: item.ticker, url: item.url,
            category: item.category, kind: item.kind, companyName: name
        )
    }
}

enum MacBureauNewsDesk {
    /// Headlines say "Intel", not "Intel Corp": legal suffixes come off before matching.
    private static let suffix = try? NSRegularExpression(
        pattern: #"[,\s]+(incorporated|inc\.?|corporation|corp\.?|company|co\.?|ltd\.?|limited|plc|llc|l\.?p\.?|holdings?|group|n\.v\.|s\.a\.|ag|se)$"#,
        options: [.caseInsensitive]
    )

    static func nameKeys(_ company: MacCompany) -> [String] {
        let full = (company.name ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        var keys: [String] = []
        if full.count >= 3 { keys.append(full) }
        var short = full
        for _ in 0..<3 {
            guard let suffix else { break }
            let next = suffix.stringByReplacingMatches(in: short, range: NSRange(short.startIndex..., in: short), withTemplate: "")
                .trimmingCharacters(in: .whitespaces)
            if next == short { break }
            short = next
        }
        if short.count >= 3, !keys.contains(short) { keys.append(short) }
        return keys
    }

    static func containsWord(_ hay: String, _ needle: String) -> Bool {
        guard !needle.isEmpty else { return false }
        let escaped = NSRegularExpression.escapedPattern(for: needle)
        return hay.range(of: "(^|[^a-z0-9])\(escaped)($|[^a-z0-9])", options: .regularExpression) != nil
    }

    /// `matchCompaniesForNews`: the story's ticker, then a company's name or ticker as a
    /// whole word in its headline, summary or source.
    static func company(for item: MacNewsItem, in companies: [MacCompany]) -> MacCompany? {
        let ticker = (item.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        if !ticker.isEmpty, let hit = companies.first(where: { ($0.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased() == ticker }) {
            return hit
        }
        let hay = [item.title, item.summary, item.companyName, item.ticker, item.source, item.category]
            .compactMap { $0 }.joined(separator: " ").lowercased()
        return companies.first { company in
            let own = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).lowercased()
            return nameKeys(company).contains { containsWord(hay, $0) } || (!own.isEmpty && containsWord(hay, own))
        }
    }

    /// A company's own stored news (`company_news`, else `recent_news` on the company).
    struct Stored {
        let companyId: String
        let item: MacNewsItem
    }

    /// `assembleDeskNews`: the live wire and the companies' stored news, newest first, one
    /// row per headline. Stored news older than two weeks drops out once live headlines are
    /// in, except for the company the desk is narrowed to: that archive is its news page.
    static func rows(_ news: [MacNewsItem], stored: [Stored], companies: [MacCompany], focusId: String?) -> [MacBureauNewsRow] {
        let live = news.map { MacBureauNewsRow(item: $0, company: company(for: $0, in: companies)) }
        let cutoff = Date().addingTimeInterval(-14 * 24 * 3600)
        let archive = stored.compactMap { entry -> MacBureauNewsRow? in
            guard let company = companies.first(where: { $0.id == entry.companyId }) else { return nil }
            let keepAll = focusId == entry.companyId
            if !keepAll, !live.isEmpty {
                guard let stamp = MacBureauPNFormat.date(entry.item.publishedAt) ?? MacBureauPNFormat.day(entry.item.publishedAt),
                      stamp >= cutoff else { return nil }
            }
            return MacBureauNewsRow(item: entry.item, company: company)
        }
        let candidates = (live + archive)
            .filter { focusId == nil || $0.company?.id == focusId }
            .sorted { ($0.item.publishedAt ?? "") > ($1.item.publishedAt ?? "") }
        var seen = Set<String>()
        var rows: [MacBureauNewsRow] = []
        for row in candidates {
            let title = row.item.title.trimmingCharacters(in: .whitespacesAndNewlines)
            let key = "\(row.item.url ?? "")|\(title)|\(row.company?.id ?? "")"
            guard !title.isEmpty, !seen.contains(title.lowercased()), !seen.contains("id:\(row.id)"), !seen.contains(key) else { continue }
            seen.insert(title.lowercased())
            seen.insert("id:\(row.id)")
            seen.insert(key)
            rows.append(row)
            if rows.count >= 100 { break }
        }
        return rows
    }

    /// Reads the stored news off the workspace's companies (`GET /api/companies`).
    static func loadStored() async -> [Stored] {
        guard let data = try? await MacAPIClient.shared.download(pathOrURL: "companies"),
              let list = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return [] }
        var out: [Stored] = []
        for company in list {
            guard let id = company["id"] as? String, !id.isEmpty else { continue }
            let own = company["company_news"] as? [[String: Any]] ?? []
            let local = own.isEmpty ? (company["recent_news"] as? [[String: Any]] ?? []) : own
            for (index, raw) in local.enumerated() {
                let title = ((raw["title"] as? String) ?? (raw["headline"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                guard !title.isEmpty else { continue }
                let url = ((raw["url"] as? String) ?? (raw["source_url"] as? String) ?? "").trimmingCharacters(in: .whitespaces)
                let stamp = [raw["published_at"], raw["captured_at"], raw["date"], raw["created_at"]].compactMap { $0 as? String }.first { !$0.isEmpty }
                let rowId = url.isEmpty ? "company:\(id):\(title):\(stamp ?? String(index))" : "company:\(id):\(url)"
                let source = [raw["source"], raw["domain"], raw["kind"]].compactMap { $0 as? String }.first { !$0.isEmpty }
                let summary = (raw["summary"] as? String) ?? (raw["description"] as? String)
                out.append(Stored(companyId: id, item: MacNewsItem(
                    id: rowId,
                    title: title,
                    summary: summary?.trimmingCharacters(in: .whitespacesAndNewlines),
                    source: source,
                    publishedAt: stamp,
                    ticker: (company["ticker"] as? String)?.uppercased(),
                    url: url.isEmpty ? nil : url,
                    category: (raw["category"] as? String) ?? (raw["tag"] as? String),
                    kind: "company_news",
                    companyName: company["name"] as? String
                )))
            }
        }
        return out
    }

    /// The iOS news palette the website draws its leads and thumbnails in.
    enum Tone: CaseIterable {
        case blue, indigo, purple, teal, orange, pink, mint

        func color(dark: Bool) -> Color {
            switch self {
            case .blue: return .bshFixed(BSHRGB(10, 132, 255))
            case .indigo: return .bshFixed(dark ? BSHRGB(94, 92, 230) : BSHRGB(88, 86, 214))
            case .purple: return .bshFixed(dark ? BSHRGB(191, 90, 242) : BSHRGB(175, 82, 222))
            case .teal: return .bshFixed(dark ? BSHRGB(64, 200, 224) : BSHRGB(48, 176, 199))
            case .orange: return .bshFixed(dark ? BSHRGB(255, 159, 10) : BSHRGB(255, 149, 0))
            case .pink: return .bshFixed(dark ? BSHRGB(255, 55, 95) : BSHRGB(255, 45, 85))
            case .mint: return .bshFixed(dark ? BSHRGB(102, 212, 207) : BSHRGB(0, 199, 190))
            }
        }
    }

    /// `newsToneKey`: the website's stable hash of the headline, so a story keeps its tone.
    static func tone(_ seed: String, withMint: Bool) -> Tone {
        var hash: Int32 = 0
        for unit in seed.utf16 { hash = hash &* 31 &+ Int32(unit) }
        let size = withMint ? 7 : 6
        return Tone.allCases[Int(abs(Int64(hash)) % Int64(size))]
    }

    /// `categorySymbol`.
    static func symbol(_ category: String?) -> String {
        let c = (category ?? "").lowercased()
        if c.contains("earning") { return "chart-column" }
        if c.contains("deal") || c.contains("m&a") { return "git-merge" }
        if c.contains("product") { return "package" }
        if c.contains("regulat") || c.contains("legal") { return "building-2" }
        if c.contains("partner") { return "users" }
        return "newspaper"
    }
}

// MARK: - The briefing

/// The lead story's briefing, read as the website reads it: the stored briefing first; with
/// none, the server's plain one pulled from the article (`refresh: false` never calls a
/// model). Regenerating writes a new one, and only on the analyst's word.
@MainActor
final class MacBureauNewsBriefModel: ObservableObject {
    @Published private(set) var brief: MacNewsBrief?
    /// `kind: "basic"`: the article's opening, no AI yet.
    @Published private(set) var basic = false
    @Published private(set) var keyFigures: [String] = []
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    @Published private(set) var key: String?
    private var generation = 0

    static func key(_ item: MacNewsItem, lang: String) -> String { "\(item.id)|\(lang)" }

    func open(_ item: MacNewsItem, lang: String) async {
        let key = Self.key(item, lang: lang)
        if self.key == key, brief != nil || loading { return }
        await load(item, lang: lang, refresh: false)
    }

    func regenerate(_ item: MacNewsItem, lang: String) async {
        await load(item, lang: lang, refresh: true)
    }

    private func load(_ item: MacNewsItem, lang: String, refresh: Bool) async {
        generation += 1
        let token = generation
        key = Self.key(item, lang: lang)
        if !refresh {
            brief = nil
            basic = false
            keyFigures = []
        }
        loading = true
        error = nil
        defer { if token == generation { loading = false } }

        if !refresh, let (stored, raw) = try? await Self.stored(item, lang: lang) {
            guard token == generation else { return }
            adopt(stored, raw: raw, lang: lang)
            return
        }
        do {
            let fresh = try await MacAPIClient.shared.fetchNewsBrief(item: item, lang: lang, refresh: refresh)
            guard token == generation else { return }
            adopt(fresh, raw: nil, lang: lang)
        } catch {
            guard token == generation, !Task.isCancelled else { return }
            if brief == nil || refresh { self.error = error.localizedDescription }
        }
    }

    private func adopt(_ brief: MacNewsBrief, raw: [String: Any]?, lang: String) {
        self.brief = brief
        if let raw {
            basic = (raw["kind"] as? String) == "basic"
            let localized = raw["key_figures_\(lang)"] as? [String] ?? []
            keyFigures = (localized.isEmpty ? (raw["key_figures"] as? [String] ?? []) : localized).filter { !$0.isEmpty }
        } else {
            // The plain briefing carries no judgement and nothing to watch.
            basic = brief.confidence == nil && brief.whyItMatters(lang: lang).isEmpty && brief.contextBullets(lang: lang).isEmpty
            keyFigures = []
        }
    }

    /// `GET /api/news/brief`: the briefing stored for this headline, with the fields the
    /// Mac's model leaves out (its kind and key figures).
    private static func stored(_ item: MacNewsItem, lang: String) async throws -> (MacNewsBrief, [String: Any]) {
        var query = [URLQueryItem(name: "title", value: item.title), URLQueryItem(name: "lang", value: lang)]
        if let company = item.companyName, !company.isEmpty { query.append(URLQueryItem(name: "company", value: company)) }
        guard let url = MacConfig.serverURL("news/brief", query: query) else { throw MacAPIError.invalidURL }
        let data = try await MacAPIClient.shared.download(pathOrURL: url.absoluteString)
        let brief = try JSONDecoder().decode(MacNewsBrief.self, from: data)
        let raw = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return (brief, raw)
    }
}

// MARK: - The page

struct MacBureauNewsPage: View {
    enum Scope: String, CaseIterable { case all, book, market }

    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @StateObject private var briefing = MacBureauNewsBriefModel()
    /// The website keeps the wide layout in `bsh.newsDesk.expanded`; the Mac keeps its own.
    @AppStorage("bsh.bureau.newsDeskExpanded") private var expanded = false
    @State private var scope: Scope = .all
    @State private var query = ""
    @State private var selectedId: String?
    @State private var focusCompany: MacCompany?
    @State private var autoUpdate: MacBureauPNJSON?
    @State private var refreshStatus: MacBureauPNJSON?
    @State private var tapeQuotes: [String: MacBureauPNJSON] = [:]
    @State private var storedNews: [MacBureauNewsDesk.Stored] = []
    @State private var language = "en"

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    // MARK: Rows

    private var allRows: [MacBureauNewsRow] {
        MacBureauNewsDesk.rows(store.news, stored: storedNews, companies: store.companies, focusId: focusCompany?.id)
    }

    /// The companies you follow, then the ones you opened (`followingCompanies`).
    private var following: [MacCompany] {
        var seen = Set<String>()
        let followed = store.validFollowedIds.compactMap { id in store.companies.first { $0.id == id } }
        let visits = store.visitedCompanyTimestamps
        let recent = store.companies
            .filter { visits[$0.id] != nil }
            .sorted { (visits[$0.id] ?? .distantPast) > (visits[$1.id] ?? .distantPast) }
            .prefix(8)
        return (followed + recent).filter { seen.insert($0.id).inserted }
    }

    private var rows: [MacBureauNewsRow] {
        let book = Set(following.map(\.id))
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allRows.filter { row in
            switch scope {
            case .all: break
            case .book: if !(row.company.map { book.contains($0.id) } ?? false) { return false }
            case .market: if !row.market { return false }
            }
            guard !q.isEmpty else { return true }
            let hay = "\(row.item.title) \(row.item.summary ?? "") \(row.item.source ?? "")".lowercased()
            return hay.contains(q)
        }
    }

    private var selected: MacBureauNewsRow? {
        let list = rows
        return list.first { $0.id == selectedId } ?? list.first
    }

    var body: some View {
        GeometryReader { proxy in
            let viewport = proxy.size.width + 78
            ScrollViewReader { reader in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        MacBureauPulseNewsSubNav()
                        page(viewport: viewport, reader: reader)
                            .padding(.horizontal, viewport >= 768 ? 32 : 20)
                            .padding(.top, 16)
                            .padding(.bottom, 48)
                            .frame(maxWidth: expanded ? .infinity : 1152)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .background(Color.dsCanvas)
        .onChange(of: selected?.id) { _, _ in openBriefing() }
        .onChange(of: language) { _, _ in openBriefing() }
        .onChange(of: store.newsFocusId) { _, _ in adoptFocus() }
        .onChange(of: store.newsCompanyFocus?.id) { _, _ in adoptCompanyFocus() }
        .task {
            adoptFocus()
            adoptCompanyFocus()
            openBriefing()
            await loadDesk()
        }
        .task {
            // The website polls the wire while the desk is open; so does this page.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                guard !Task.isCancelled else { return }
                await store.refreshNews()
            }
        }
    }

    private func openBriefing() {
        guard let item = selected?.briefItem else { return }
        Task { await briefing.open(item, lang: language) }
    }

    /// The cadence of the scheduled briefings, the refresh status, the tape's quotes and
    /// the language the workspace reads in. All GETs.
    private func loadDesk() async {
        async let updates = try? MacBureauPNJSON.load("auto-updates")
        async let status = try? MacBureauPNJSON.load("news/brief/refresh")
        async let settings = try? MacAPIClient.shared.workspaceSettings()
        async let quotes = loadTapeQuotes()
        async let stored = MacBureauNewsDesk.loadStored()
        let (u, s, w, _, n) = await (updates, status, settings, quotes, stored)
        storedNews = n
        autoUpdate = u?.objects("channels").first { $0.string("id") == "news_brief" }
        refreshStatus = s
        if let lang = w?.preferences?.language, lang == "en" || lang == "zh", lang != language { language = lang }
        if store.marketPulsePayload == nil { await store.refreshIndices() }
    }

    /// The tape's quotes with their as-of stamps (`GET /api/quotes`).
    private func loadTapeQuotes() async {
        let tickers = tapeTickers
        guard !tickers.isEmpty,
              let url = MacConfig.serverURL("quotes", query: tickers.map { URLQueryItem(name: "ticker", value: $0) }),
              let payload = try? await MacBureauPNJSON.load(url.absoluteString),
              let quotes = payload.object("quotes") else { return }
        var read: [String: MacBureauPNJSON] = [:]
        for ticker in tickers { if let q = quotes.object(ticker) { read[ticker] = q } }
        tapeQuotes = read
    }

    private var followingTickers: [String] {
        var seen = Set<String>()
        return following.compactMap { company in
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            return !ticker.isEmpty && seen.insert(ticker).inserted ? ticker : nil
        }
    }

    private var tapeTickers: [String] {
        var seen = Set<String>()
        return store.companies.compactMap { company in
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            return !ticker.isEmpty && seen.insert(ticker).inserted ? ticker : nil
        }
    }

    /// A story a link named (`?story=`): lead with it.
    private func adoptFocus() {
        guard let id = store.newsFocusId else { return }
        store.newsFocusId = nil
        guard store.news.contains(where: { $0.id == id }) else { return }
        scope = .all
        query = ""
        focusCompany = nil
        selectedId = id
    }

    /// A company's News page from the rail (`?company=`): the desk on that company.
    private func adoptCompanyFocus() {
        guard let company = store.newsCompanyFocus else { return }
        store.newsCompanyFocus = nil
        focusCompany = company
        scope = .all
        query = ""
        selectedId = nil
    }

    // MARK: Layout

    @ViewBuilder
    private func page(viewport: CGFloat, reader: ScrollViewProxy) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            header.padding(.bottom, 20)

            let watchTape = expanded && !followingTickers.isEmpty
            if !tapeTickers.isEmpty || watchTape {
                VStack(spacing: 8) {
                    if !tapeTickers.isEmpty {
                        MacBureauNewsTape(tickers: tapeTickers, quotes: tapeQuotes)
                    }
                    // Wide, the companies you follow get a tape of their own.
                    if watchTape {
                        MacBureauNewsTape(tickers: followingTickers, quotes: tapeQuotes, label: "Watchlist")
                    }
                }
                .padding(.bottom, 20)
            }

            if !expanded, !following.isEmpty {
                followingSection.padding(.bottom, 24)
            }

            if expanded || viewport < 1024 {
                VStack(alignment: .leading, spacing: 24) {
                    desk(reader: reader)
                    if !expanded { MacBureauNewsMarkets() }
                }
            } else {
                MacBureauNewsColumns(gap: 32) {
                    desk(reader: reader)
                } side: {
                    MacBureauNewsMarkets()
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLine(MacBureauPNFormat.longDay(Date()).uppercased(), size: 11, weight: .semibold, tracking: 2.2, line: 16.5, color: ink.accentInk)
            Text("News")
                .font(.custom(BSHType.bureauSerif, size: 46))
                .tracking(-0.552)
                .foregroundStyle(ink.ink)
                .lineLimit(1)
                .fixedSize()
                .frame(height: 48)
                .padding(.top, 2)
        }
    }

    private var followingSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Following")
                .font(.custom(BSHType.bureauSerif, size: 28))
                .tracking(-0.28)
                .foregroundStyle(ink.ink)
                .frame(height: 34)
                .padding(.horizontal, 4)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(following) { company in
                        MacBureauNewsFollowChip(company: company, companies: store.companies) { open(company) }
                    }
                }
                .padding(.bottom, 4)
            }
        }
    }

    private func open(_ company: MacCompany) {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces)
        if !ticker.isEmpty {
            store.showTicker(ticker)
        } else {
            store.openCompanyPage(company)
        }
    }

    // MARK: The desk

    private func desk(reader: ScrollViewProxy) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            filters
            cadenceRow.padding(.top, 12)
            if let focus = focusCompany {
                focusRow(focus).padding(.top, 16)
            }
            if let lead = selected {
                MacBureauNewsLead(
                    row: lead,
                    briefing: briefing,
                    language: language,
                    open: open,
                    regenerate: regenerate
                )
                .id("lead")
                .padding(.top, 20)
            } else {
                Text(focusCompany.map { "No recent news for \($0.name ?? $0.id) on the desk." } ?? "Nothing here yet. Open a company or add a link from Home.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 40)
                    .frame(maxWidth: .infinity)
                    .pnTray()
                    .padding(.top, 20)
            }
            let rest = rows.filter { $0.id != selected?.id }
            if !rest.isEmpty {
                latest(rest, reader: reader).padding(.top, 20)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var filters: some View {
        HStack(spacing: 12) {
            MacBureauSegmented(
                [(Scope.all, "Today"), (.book, "Following"), (.market, "Market")],
                selection: $scope
            )
            Spacer(minLength: 0)
            HStack(spacing: 8) {
                MacBureauNewsSearch(query: $query)
                MacBureauPNRangeButton(title: expanded ? "Collapse" : "Expand", icon: expanded ? "minimize-2" : "maximize-2", selected: expanded) {
                    withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                }
                .help(expanded ? "Collapse" : "Expand")
            }
            .frame(minWidth: 192, maxWidth: 448)
        }
    }

    private var cadence: String { autoUpdate?.string("cadence") ?? "" }

    /// `refreshLabel`: what the scheduled briefings are doing.
    private var refreshLabel: String {
        guard let status = refreshStatus else { return "" }
        if status.bool("running") {
            let done = Int((status.double("done") ?? 0) + (status.double("failed") ?? 0))
            return "Writing AI briefs: \(done) of \(Int(status.double("total") ?? 0))"
        }
        if status.string("note") == "nothing_to_write" { return "Every top headline already has an AI briefing." }
        guard let hours = status.double("interval_hours"), hours > 0 else { return "" }
        let h = hours.rounded() == hours ? String(Int(hours)) : String(hours)
        guard let next = MacBureauPNFormat.date(status.string("next_refresh_at")) else { return "AI briefs refresh every \(h) hours" }
        let n = max(0, Int((next.timeIntervalSinceNow / 3600).rounded(.up)))
        return "AI briefs refresh every \(h) hours · next in about \(n) h"
    }

    private var cadenceRow: some View {
        MacBureauPNFlexRow(spacing: 8, lineSpacing: 8) {
            if autoUpdate != nil {
                MacBureauPNFlexRow(spacing: 12, lineSpacing: 6, justify: false) {
                    MacBureauSegmented(
                        cadenceChoices.map { ($0, cadenceTitle($0)) },
                        selection: Binding(
                            get: { cadence },
                            set: { _ in openWebNews() }
                        )
                    )
                    .help("The schedule is the website's: this opens its News desk beside the page.")
                    if cadence == "manual" {
                        MacBureauPNLine("Manual only — nothing runs on its own.", size: 11, tracking: 0.066, line: 14, color: ink.muted)
                    } else if let next = MacBureauPNFormat.date(autoUpdate?.string("next_run_at")) {
                        MacBureauPNLine("Next run \(next.formatted(date: .numeric, time: .standard))", size: 11, tracking: 0.066, line: 14, color: ink.muted)
                    }
                }
            }
            MacBureauPNLine(refreshLabel, size: 11, tracking: 0.066, line: 14, color: ink.muted)
            Button { openWebNews() } label: {
                HStack(spacing: 6) {
                    LucideIcon("sparkles", size: 14)
                    Text("Refresh AI briefs now")
                }
            }
            .buttonStyle(MacBureauPillStyle(kind: .bordered))
            .disabled(refreshStatus?.bool("running") ?? false || allRows.isEmpty)
            .help("AI briefings are written on the website: this opens its News desk beside the page.")
        }
    }

    private var cadenceChoices: [String] {
        let choices = autoUpdate?.strings("choices") ?? []
        return choices.isEmpty ? ["manual", "6h", "12h", "1d", "3d"] : choices
    }

    private func cadenceTitle(_ value: String) -> String {
        switch value {
        case "manual": return "Manual"
        case "6h": return "Every 6h"
        case "12h": return "Every 12h"
        case "1d": return "Daily"
        case "3d": return "Every 3 days"
        default: return "Custom"
        }
    }

    private func openWebNews() {
        withAnimation(.easeInOut(duration: 0.18)) {
            store.openInEmbeddedBrowser(MacConfig.webNewsURL())
        }
    }

    /// The chip naming the company the desk is narrowed to, and the way back to all news.
    private func focusRow(_ company: MacCompany) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 4) {
                LucideIcon("building-2", size: 14)
                MacBureauPNLine("News for \(company.name ?? company.id)", size: 11, weight: .semibold, line: 14, color: ink.accentInk)
            }
            .foregroundStyle(ink.accentInk)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(Capsule().fill(ink.accent.opacity(0.1)))
            Button {
                focusCompany = nil
                selectedId = nil
            } label: {
                HStack(spacing: 6) {
                    LucideIcon("x", size: 14)
                    Text("All news")
                }
            }
            .buttonStyle(MacBureauPillStyle(kind: .bordered))
        }
    }

    private func regenerate() {
        guard let item = selected?.briefItem, !briefing.loading else { return }
        guard MacTokenConfirm.ask() else { return }
        Task { await briefing.regenerate(item, lang: language) }
    }

    // MARK: Latest

    private func latest(_ rest: [MacBureauNewsRow], reader: ScrollViewProxy) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            MacBureauPNLabel("Latest").padding(.horizontal, 4)
            VStack(spacing: 0) {
                ForEach(Array(rest.enumerated()), id: \.element.id) { index, row in
                    MacBureauNewsStoryRow(row: row, first: index == 0) {
                        let same = selectedId == row.id
                        selectedId = row.id
                        if !same { withAnimation(.easeInOut(duration: 0.25)) { reader.scrollTo("lead", anchor: .top) } }
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
            .pnTray()
        }
    }
}

// MARK: - Pieces

/// The 12-column grid under the header: the desk over eight columns, Markets over four.
struct MacBureauNewsColumns<Main: View, Side: View>: View {
    let gap: CGFloat
    @ViewBuilder var main: () -> Main
    @ViewBuilder var side: () -> Side

    var body: some View {
        MacBureauNewsColumnsLayout(gap: gap) {
            main()
            side()
        }
    }
}

private struct MacBureauNewsColumnsLayout: Layout {
    let gap: CGFloat

    private func widths(_ total: CGFloat) -> (CGFloat, CGFloat) {
        let column = (total - 11 * gap) / 12
        return (column * 8 + gap * 7, column * 4 + gap * 3)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total = proposal.width ?? 1088
        let (a, b) = widths(total)
        let ha = subviews.first?.sizeThatFits(ProposedViewSize(width: a, height: nil)).height ?? 0
        let hb = subviews.count > 1 ? subviews[1].sizeThatFits(ProposedViewSize(width: b, height: nil)).height : 0
        return CGSize(width: total, height: max(ha, hb))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (a, b) = widths(bounds.width)
        subviews.first?.place(at: bounds.origin, proposal: ProposedViewSize(width: a, height: nil))
        if subviews.count > 1 {
            subviews[1].place(at: CGPoint(x: bounds.minX + a + gap, y: bounds.minY), proposal: ProposedViewSize(width: b, height: nil))
        }
    }
}

/// `flex flex-wrap items-center justify-between`: a row of pieces that wraps, each line's
/// first piece at the left and its last at the right.
struct MacBureauPNFlexRow: Layout {
    var spacing: CGFloat
    var lineSpacing: CGFloat
    var justify = true

    private func lines(_ subviews: Subviews, width: CGFloat) -> [[(index: Int, size: CGSize)]] {
        var lines: [[(index: Int, size: CGSize)]] = [[]]
        var x: CGFloat = 0
        for (index, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if size.width == 0 && size.height == 0 { continue }
            if !lines[lines.count - 1].isEmpty, x + spacing + size.width > width + 0.5 {
                lines.append([])
                x = 0
            }
            x += (lines[lines.count - 1].isEmpty ? 0 : spacing) + size.width
            lines[lines.count - 1].append((index, size))
        }
        return lines.filter { !$0.isEmpty }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let found = lines(subviews, width: width)
        let height = found.reduce(0) { $0 + ($1.map(\.size.height).max() ?? 0) } + lineSpacing * CGFloat(max(0, found.count - 1))
        let used = found.map { line in line.reduce(0) { $0 + $1.size.width } + spacing * CGFloat(line.count - 1) }.max() ?? 0
        return CGSize(width: justify && proposal.width != nil ? width : used, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in lines(subviews, width: bounds.width) {
            let lineHeight = line.map(\.size.height).max() ?? 0
            let used = line.reduce(0) { $0 + $1.size.width }
            let gap = justify && line.count > 1 ? max(spacing, (bounds.width - used) / CGFloat(line.count - 1)) : spacing
            var x = bounds.minX
            for piece in line {
                subviews[piece.index].place(
                    at: CGPoint(x: x, y: y + (lineHeight - piece.size.height) / 2),
                    proposal: ProposedViewSize(piece.size)
                )
                x += piece.size.width + gap
            }
            y += lineHeight + lineSpacing
        }
    }
}

/// `.news-search-field`: a pill of fresh paper ruled in ink, the glass at its left.
struct MacBureauNewsSearch: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var query: String
    @FocusState private var focused: Bool

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        ZStack(alignment: .leading) {
            LucideIcon("search", size: 16)
                .foregroundStyle(ink.muted)
                .padding(.leading, 12)
            TextField("", text: $query, prompt: Text("Search stories").foregroundStyle(ink.muted))
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .focused($focused)
                .padding(.leading, 36)
                .padding(.trailing, 12)
                .onExitCommand { query = "" }
        }
        .frame(height: 34)
        .frame(maxWidth: .infinity)
        .background(Capsule().fill(ink.raised))
        .overlay(Capsule().strokeBorder(focused ? ink.accent : ink.ink(0.14), lineWidth: 1))
        .overlay(
            Capsule()
                .inset(by: -2)
                .stroke(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                .padding(-0.5)
                .allowsHitTesting(false)
        )
    }
}

/// The live tape on the News desk (LiveTickerTape.vue): your listed companies, each with
/// its price, its move and how fresh the print is.
struct MacBureauNewsTape: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let tickers: [String]
    let quotes: [String: MacBureauPNJSON]
    var label = "Live"

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(spacing: 0) {
            Button { store.selectedTab = .portfolio } label: {
                HStack(spacing: 6) {
                    Circle()
                        .fill(ink.success)
                        .frame(width: 5.66, height: 5.66)
                        .background(Circle().fill(ink.success.opacity(0.16)).frame(width: 11.66, height: 11.66))
                    Text(label)
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Tracking")
            .padding(.leading, 4)
            .padding(.trailing, 12)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(tickers, id: \.self) { ticker in
                        MacBureauNewsTapeItem(ticker: ticker, quote: quotes[ticker] ?? fallback(ticker), ink: ink) {
                            store.showTicker(ticker)
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
        .overlay(RoundedRectangle(cornerRadius: 14, style: .circular).strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.ink(0.035), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
    }

    /// Until the tape's own quotes land, the store's watchlist prints stand in.
    private func fallback(_ ticker: String) -> MacBureauPNJSON? {
        guard let quote = store.watchlist.first(where: { $0.ticker.uppercased() == ticker }) else { return nil }
        var raw: [String: Any] = [:]
        if let last = quote.last { raw["last_price"] = last }
        if let pct = quote.pct { raw["change_pct_1d"] = pct }
        return MacBureauPNJSON(raw)
    }
}

private struct MacBureauNewsTapeItem: View {
    let ticker: String
    let quote: MacBureauPNJSON?
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    /// `quoteStaleness`: "just now" under a minute, minutes under an hour, a warning past 20.
    private var asOf: (text: String, stale: Bool)? {
        guard let stamp = MacBureauPNFormat.date(quote?.string("as_of")) else { return nil }
        let minutes = max(0, Int((Date().timeIntervalSince(stamp) / 60).rounded()))
        if minutes >= 20 { return ("Stale \(minutes)m", true) }
        if minutes < 1 { return ("just now", false) }
        return ("\(minutes)m ago", false)
    }

    var body: some View {
        let change = quote?.double("change_pct_1d")
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(ticker)
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.ink)
                if let price = MacBureauPNFormat.price(quote?.double("last_price")) {
                    Text(price)
                        .font(BSHType.bureauSans(12).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(ink.secondary)
                }
                if let change, let text = MacBureauPNFormat.signed(change) {
                    Text(text)
                        .font(BSHType.bureauSans(12, weight: .semibold).monospacedDigit())
                        .tracking(-0.12)
                        .foregroundStyle(change >= 0 ? ink.success : ink.danger)
                } else {
                    Text("Waiting")
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.subtle)
                }
                if let asOf {
                    Text(asOf.text)
                        .font(BSHType.bureauSans(10))
                        .tracking(0.12)
                        .foregroundStyle(asOf.stale ? ink.warningInk : ink.subtle)
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 24)
            .background(RoundedRectangle(cornerRadius: 8, style: .circular).fill(hovered ? ink.ink(0.045) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(ticker)
    }
}

/// One of the companies you follow: a round seal of its ticker's first letters, its label.
struct MacBureauNewsFollowChip: View {
    @Environment(\.colorScheme) private var colorScheme
    let company: MacCompany
    let companies: [MacCompany]
    let action: () -> Void

    private var label: String {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        return ticker.isEmpty ? (company.name ?? company.id) : ticker
    }

    private var initials: String {
        let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        if !ticker.isEmpty { return String(ticker.prefix(2)) }
        return String((company.name ?? "?").trimmingCharacters(in: .whitespaces).prefix(1)).uppercased()
    }

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        Button(action: action) {
            VStack(spacing: 6) {
                Text(initials)
                    .font(BSHType.bureauSans(12, weight: .semibold))
                    .foregroundStyle(ink.ink)
                    .frame(width: 48, height: 48)
                    .background(
                        Circle().fill(LinearGradient(colors: [ink.ink(0.05), ink.ink(0.1)], startPoint: .top, endPoint: .bottom))
                    )
                    .overlay {
                        // inset 0 1px 0 white/0.5: a sliver of light along the top, under
                        // the ring (the first of CSS's shadows paints on top).
                        Path { path in
                            path.addEllipse(in: CGRect(x: 0, y: 0, width: 48, height: 48))
                            path.addEllipse(in: CGRect(x: 0, y: 1, width: 48, height: 48))
                        }
                        .fill(Color.white.opacity(0.5), style: FillStyle(eoFill: true))
                        .clipShape(Circle())
                        .allowsHitTesting(false)
                    }
                    .overlay(Circle().strokeBorder(ink.ink(0.1), lineWidth: 0.5))
                Text(label)
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .tracking(0.066)
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 72)
            }
            .padding(.vertical, 4)
            .frame(width: 68)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(company.name ?? label)
    }
}

// MARK: - The lead story

/// `.news-lead`: the chosen story set large. Its kicker in brass capitals and its headline
/// in Instrument Serif over a rule, the byline and the actions under it, then the briefing.
struct MacBureauNewsLead: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauNewsRow
    @ObservedObject var briefing: MacBureauNewsBriefModel
    let language: String
    let open: (MacCompany) -> Void
    let regenerate: () -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var item: MacNewsItem { row.item }
    private var isCurrent: Bool { briefing.key == MacBureauNewsBriefModel.key(row.briefItem, lang: language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            banner
            details
            briefPanel
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .circular))
        .pnTray(radius: 18)
    }

    private var banner: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let kicker = row.kicker {
                Text(kicker.uppercased())
                    .font(BSHType.bureauSans(11, weight: .bold))
                    .tracking(1.54)
                    .foregroundStyle(ink.accentInk)
                    .pnLines(16.5, size: 11, face: .sans)
            }
            Text(item.title)
                .font(.custom(BSHType.bureauSerif, size: 36))
                .tracking(-0.36)
                .foregroundStyle(ink.ink)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(40, size: 36, face: .serif)
                .textSelection(.enabled)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .bottom) { Rectangle().fill(ink.rule).frame(height: 1) }
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.secondary)
                    .lineLimit(8)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(22.75, size: 14, face: .sans)
            }
            MacBureauPNLine(row.byline, size: 11, tracking: 0.066, line: 14, color: ink.muted)
            MacBureauPNFlexRow(spacing: 8, lineSpacing: 8, justify: false) {
                MacBureauButton("Read Story", kind: .filled) { readStory() }
                    .disabled(!row.canRead)
                if let company = row.company {
                    MacBureauButton(company.name ?? company.id) { open(company) }
                }
                Button { askWarren() } label: {
                    HStack(spacing: 6) {
                        WarrenMarkView(size: 20)
                        Text("Ask Warren")
                    }
                    .padding(.leading, -8)
                }
                .buttonStyle(MacBureauPillStyle(kind: .bordered))
                .disabled(!store.canRunTasks)
                Button { regenerate() } label: {
                    HStack(spacing: 6) {
                        if briefing.loading && isCurrent {
                            ProgressView().controlSize(.mini).frame(width: 14, height: 14)
                        } else {
                            LucideIcon("refresh-cw", size: 14)
                        }
                        Text("Regenerate briefing")
                    }
                }
                .buttonStyle(MacBureauPillStyle(kind: .bordered))
                .disabled(briefing.loading || !store.canRunTasks)
                if let ticker = item.ticker, !ticker.isEmpty {
                    MacBureauButton("Log signal", icon: "flag") { store.openSignalLog(seedTicker: ticker) }
                        .help("Log a bullish / bearish call on \(ticker) from this story (⌘L)")
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func readStory() {
        guard let raw = item.url, let url = URL(string: raw) else { return }
        withAnimation(.easeInOut(duration: 0.18)) { store.openInEmbeddedBrowser(url) }
    }

    private func askWarren() {
        store.askWarren(
            "What matters about this headline for our coverage: \(item.title)",
            context: .news(item: item),
            company: row.company
        )
    }

    // MARK: Briefing

    private var briefPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            if isCurrent, let brief = briefing.brief {
                MacBureauNewsBriefing(brief: brief, basic: briefing.basic, keyFigures: briefing.keyFigures, title: item.title, language: language)
            } else if isCurrent, briefing.loading {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small).tint(ink.accent).frame(width: 16, height: 16)
                    Text("Loading the briefing…")
                }
                .font(BSHType.bureauSans(15))
                .foregroundStyle(ink.secondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.04)))
            } else {
                VStack(spacing: 10) {
                    HStack(spacing: 8) {
                        LucideIcon("sparkles", size: 16).foregroundStyle(ink.accent)
                        MacBureauPNLine("Full briefing", size: 15, weight: .semibold, tracking: -0.15, line: 20, color: ink.ink)
                    }
                    Text("Load this story's briefing. AI briefings are written on a schedule; a story without one shows the article's opening.")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .pnLines(16, size: 12, face: .sans)
                    MacBureauButton("Load the briefing", kind: .filled) {
                        Task { await briefing.open(row.briefItem, lang: language) }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity)
                .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.04)))
            }
            if isCurrent, let error = briefing.error {
                Text(error)
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.danger)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(16, size: 12, face: .sans)
                    .padding(.top, 12)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 1)
        .overlay(alignment: .top) { Rectangle().fill(ink.rule.opacity(0.7)).frame(height: 1) }
    }
}

/// The briefing as the website sets it: small muted kickers over the interface face at a
/// reading size, bullets on brass dots, the sources, and the confidence.
struct MacBureauNewsBriefing: View {
    @Environment(\.colorScheme) private var colorScheme
    let brief: MacNewsBrief
    let basic: Bool
    let keyFigures: [String]
    let title: String
    let language: String

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        let headline = ((language == "zh" ? brief.headlineZh : nil) ?? brief.headlineEn ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let what = brief.whatHappened(lang: language).trimmingCharacters(in: .whitespacesAndNewlines)
        let why = brief.whyItMatters(lang: language).trimmingCharacters(in: .whitespacesAndNewlines)
        let context = brief.contextBullets(lang: language).filter { !$0.isEmpty }
        let watch = brief.watchNextBullets(lang: language).filter { !$0.isEmpty }
        let sources = (brief.sources ?? []).filter { ($0.url ?? "").isEmpty == false }
        VStack(alignment: .leading, spacing: 20) {
            if basic {
                Text("No AI briefing yet. This is the article's opening and its figures, pulled without AI. The next scheduled refresh writes the AI briefing.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(16, size: 12, face: .sans)
            }
            if !headline.isEmpty, headline != title {
                Text(headline)
                    .font(BSHType.bureauSans(18, weight: .semibold))
                    .tracking(-0.252)
                    .foregroundStyle(ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(24, size: 18, face: .sans)
            }
            if !what.isEmpty { prose("What happened", what) }
            if !why.isEmpty { prose("Why it matters", why) }
            if !keyFigures.isEmpty { bullets("Key figures", keyFigures) }
            if !context.isEmpty { bullets("Context", context) }
            if !watch.isEmpty { bullets("What to watch", watch) }
            if !sources.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    kicker("Sources")
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(sources.enumerated()), id: \.offset) { _, source in
                            if let raw = source.url, let url = URL(string: raw) {
                                MacBureauNewsSourceLink(title: source.title ?? raw, url: url)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
            }
            if let confidence = brief.confidence, !confidence.isEmpty {
                let level = confidence.lowercased()
                MacBureauPNLine(confidence.capitalized, size: 11, weight: .semibold, line: 16.5,
                                color: level == "high" ? ink.success : (level == "low" ? ink.warning : ink.muted))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// `.news-brief-kicker`: 12pt on the page's 1.5 line.
    private func kicker(_ text: String) -> some View {
        Text(text)
            .font(BSHType.bureauSans(12, weight: .semibold))
            .tracking(-0.036)
            .foregroundStyle(ink.muted)
            .pnLines(18, size: 12, face: .sans)
    }

    private func prose(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            kicker(title)
            // `.news-brief-body` asks for the display stack by name, which Bureau doesn't
            // restyle: the website sets it in the system face.
            Text(body)
                .font(.system(size: 17))
                .foregroundStyle(ink.ink)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .pnLines(26.35, size: 17, face: .system)
                .padding(.top, 8)
        }
    }

    private func bullets(_ title: String, _ rows: [String]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            kicker(title)
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, line in
                    HStack(alignment: .top, spacing: 10) {
                        Circle().fill(ink.accentGlow(1)).frame(width: 5, height: 5).padding(.top, 8)
                        Text(line)
                            .font(BSHType.bureauSans(15))
                            .foregroundStyle(ink.ink)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .pnLines(21.75, size: 15, face: .sans)
                    }
                }
            }
            .padding(.top, 8)
        }
    }
}

private struct MacBureauNewsSourceLink: View {
    @Environment(\.colorScheme) private var colorScheme
    let title: String
    let url: URL
    @State private var hovered = false

    var body: some View {
        Button { NSWorkspace.shared.open(url) } label: {
            Text(title)
                .font(BSHType.bureauSans(12))
                .foregroundStyle(MacBureauPageInk(scheme: colorScheme).accent)
                .underline(hovered)
                .multilineTextAlignment(.leading)
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Latest

/// `.news-magazine-row`: the kicker and source, the headline, the summary and the byline,
/// and a tile in the story's tone at the right.
struct MacBureauNewsStoryRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let row: MacBureauNewsRow
    let first: Bool
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let tone = MacBureauNewsDesk.tone(row.item.title, withMint: true).color(dark: ink.dark)
        Button(action: action) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 6) {
                        if let kicker = row.kicker {
                            MacBureauPNLine(kicker, size: 10, weight: .bold, tracking: 0.12, line: 13, color: ink.accent)
                        }
                        if let source = row.item.source, !source.isEmpty, source != row.item.companyName {
                            MacBureauPNLine(source, size: 10, tracking: 0.12, line: 13, color: ink.muted)
                        }
                    }
                    Text(row.item.title)
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.15)
                        .foregroundStyle(ink.ink)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .pnLines(20, size: 15, face: .sans)
                        .padding(.top, 4)
                    if let summary = row.item.summary, !summary.isEmpty {
                        Text(summary)
                            .font(BSHType.bureauSans(16))
                            .foregroundStyle(ink.secondary)
                            .lineLimit(6)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .pnLines(22, size: 16, face: .sans)
                            .padding(.top, 6)
                    }
                    MacBureauPNLine(row.byline, size: 10, tracking: 0.12, line: 13, color: ink.subtle)
                        .padding(.top, 6)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                LucideIcon(MacBureauNewsDesk.symbol(row.item.category), size: 20)
                    .foregroundStyle(tone)
                    .frame(width: 58, height: 58)
                    .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(tone.opacity(0.12)))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(hovered ? ink.ink(0.03) : .clear)
            .overlay(alignment: .top) { if !first { Rectangle().fill(ink.rule).frame(height: 1) } }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Markets

/// HomeMarketPanel.vue: the market's posture from the signals page, your companies' moves,
/// the top signals, and the ways on to Pulse and Tracking.
struct MacBureauNewsMarkets: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var regime: MacMarketPulsePayload.MarketRegime? { store.marketPulsePayload?.sections?.marketRegime }

    private var postureLabel: String {
        switch (regime?.posture ?? "empty").replacingOccurrences(of: "-", with: "_") {
        case "risk_on": return "Risk-on"
        case "risk_off": return "Risk-off"
        case "neutral": return "Neutral"
        case "empty": return "No pulse yet"
        default: return regime?.posture ?? "No pulse yet"
        }
    }

    /// `quoteMovers`: your listed companies by the size of their move.
    private var movers: [(company: MacCompany, quote: MacQuote)] {
        store.companies.compactMap { company -> (MacCompany, MacQuote)? in
            let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            guard !ticker.isEmpty, let quote = store.watchlist.first(where: { $0.ticker.uppercased() == ticker }), quote.pct != nil else { return nil }
            return (company, quote)
        }
        .sorted { abs($0.1.pct ?? 0) > abs($1.1.pct ?? 0) }
        .prefix(6)
        .map { $0 }
    }

    private var signals: [MacMarketPulsePayload.RankedSignal] {
        Array((store.marketPulsePayload?.sections?.rankedSignals ?? []).prefix(3))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .bottom) {
                Text("Markets")
                    .font(.custom(BSHType.bureauSerif, size: 28))
                    .tracking(-0.28)
                    .foregroundStyle(ink.ink)
                    .frame(height: 34)
                Spacer()
                MacBureauPNLink(title: "Open Pulse") { store.selectedTab = .pulse }
                    .padding(.horizontal, 4)
                    .frame(height: 16)
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 8)

            VStack(alignment: .leading, spacing: 12) {
                posture
                watchlist
                if !signals.isEmpty { topSignals }
                MacBureauPNLink(title: "Tracking", trailingIcon: "chevron-right") { store.selectedTab = .portfolio }
                    .padding(.horizontal, 4)
                    .frame(height: 16)
            }
        }
    }

    private var posture: some View {
        let breadth = regime?.breadth
        return VStack(alignment: .leading, spacing: 4) {
            MacBureauPNLabel(postureLabel)
            MacBureauPNLine("\(breadth?.positiveSignals ?? 0) up · \(breadth?.negativeSignals ?? 0) down · \(breadth?.neutralSignals ?? 0) flat", size: 12, line: 16, color: ink.secondary)
            if let top = store.marketPulsePayload?.summary?.topSignal, !top.isEmpty {
                Text(top)
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .pnLines(20, size: 14, face: .sans)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pnTray()
    }

    private var watchlist: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Watchlist")
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 4)
            let rows = movers
            if rows.isEmpty {
                Text("No live moves on names you follow.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .padding(.bottom, 16)
            }
            ForEach(rows, id: \.company.id) { row in
                MacBureauNewsMoverRow(company: row.company, quote: row.quote) {
                    store.showTicker(row.quote.ticker)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        .pnTray()
    }

    private var topSignals: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauPNLabel("Top signals")
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 4)
            ForEach(signals) { signal in
                VStack(alignment: .leading, spacing: 2) {
                    Text(signal.signal ?? "")
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.15)
                        .foregroundStyle(ink.ink)
                    MacBureauPNLine(signal.relatedTickers?.first ?? signal.direction ?? "", size: 11, tracking: 0.066, line: 14, color: ink.muted)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
        .pnTray()
    }
}

private struct MacBureauNewsMoverRow: View {
    @Environment(\.colorScheme) private var colorScheme
    let company: MacCompany
    let quote: MacQuote
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let up = (quote.pct ?? 0) >= 0
        Button(action: action) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 0) {
                    MacBureauPNLine(quote.ticker, size: 15, weight: .semibold, tracking: -0.15, line: 20, color: ink.ink, tabular: true)
                    MacBureauPNLine(company.name ?? quote.ticker, size: 11, tracking: 0.066, line: 14, color: ink.muted)
                        .truncationMode(.tail)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 0) {
                    if let price = MacBureauPNFormat.price(quote.last) {
                        MacBureauPNLine(price, size: 12, line: 16, color: ink.ink, tabular: true)
                    }
                    // An inline pill on the row's 24pt line: its text on that line's baseline.
                    Text(MacBureauPNFormat.signed(quote.pct) ?? "")
                        .font(BSHType.bureauSans(11, weight: .semibold).monospacedDigit())
                        .tracking(0.066)
                        .foregroundStyle(up ? ink.successInk : ink.dangerInk)
                        .pnLines(14, size: 11, face: .sans)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill(up ? ink.successSoft : ink.dangerSoft))
                        .padding(.top, 5)
                        .padding(.bottom, 1)
                }
                .fixedSize()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(hovered ? ink.ink(0.03) : .clear)
            .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}
