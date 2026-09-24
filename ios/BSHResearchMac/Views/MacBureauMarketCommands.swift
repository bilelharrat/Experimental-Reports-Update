//
//  MacBureauMarketCommands.swift
//  BSHResearchMac
//
//  The website's Bloomberg-style command line (frontend/src/marketCommands.js), ported as it
//  is: the verb table, the parser, the suggestions (same rows, order and wording for the same
//  query and companies) and the web route each command opens. `MacBureauCommandRoute` then
//  takes a command to the Mac's own destination for that route: the Market desk with the
//  ticker, a company's page, News, Pulse, Tracking, Reports, Settings, the report sheet, or,
//  where the Mac has no desk of its own for the route, the website's page in the research
//  browser (as Settings → Advanced tools opens Workbench, Stats and Labs).
//

import SwiftUI

// MARK: - Commands

/// What a command does: the website's `action` strings.
enum MacMarketCommandAction: String {
    case quote, news, comp, calendar, tracking, home, pulse, hp, fa, screener, wei, owners, alerts
    case heatmap, rrg, desk, session, filings, lots, two, ics, notes, newsdesk, signals, brief
    case stats, stockresearch, library, settings, hormuz, lab, reports, generate
    /// A company row without a ticker, the free-text fallback and the examples row.
    case company, search, help
}

/// A parsed command (`parseMarketCommand`'s result).
struct MacMarketCommand: Equatable {
    var action: MacMarketCommandAction
    var ticker: String?
    var label: String
    var raw: String
    var desk: String? = nil
    var screen: String? = nil
    var query: String? = nil
    var companyId: String? = nil
}

/// A row of the palette (`suggestMarketCommands`' result).
struct MacMarketCommandRow: Identifiable, Equatable {
    let id: String
    let title: String
    let subtitle: String
    let action: MacMarketCommandAction
    var ticker: String? = nil
    var companyId: String? = nil
    var query: String? = nil
    var screen: String? = nil

    /// As a command to run (the website runs the row object itself).
    var command: MacMarketCommand {
        MacMarketCommand(action: action, ticker: ticker, label: action.rawValue, raw: title, screen: screen, query: query, companyId: companyId)
    }
}

/// A company as the suggestions read it: `{ id, ticker, name }`.
struct MacMarketCommandCompany: Equatable {
    let id: String
    let ticker: String?
    let name: String?
}

enum MacMarketCommands {
    /// `/^[A-Z][A-Z0-9.-]{0,9}$/`
    static func isTicker(_ token: String) -> Bool {
        let scalars = Array(token.unicodeScalars)
        guard (1...10).contains(scalars.count), let first = scalars.first, ("A"..."Z").contains(first) else { return false }
        return scalars.dropFirst().allSatisfy { ("A"..."Z").contains($0) || ("0"..."9").contains($0) || $0 == "." || $0 == "-" }
    }

    static let verbs: [String: MacMarketCommandAction] = [
        "DES": .quote, "Q": .quote, "QUOTE": .quote,
        "NEWS": .news, "N": .news, "HL": .news, "CN": .news,
        "COMP": .comp, "PEER": .comp, "PEERS": .comp, "RV": .comp, "REL": .comp,
        "CAL": .calendar, "EVTS": .calendar, "EVENTS": .calendar, "EARN": .calendar,
        "TRACK": .tracking, "WL": .tracking, "WATCH": .tracking,
        "HOME": .home, "H": .home,
        "PULSE": .pulse, "MP": .pulse,
        "HP": .hp, "G": .hp, "GRAPH": .hp,
        "FA": .fa, "FIN": .fa,
        "EQS": .screener, "SCR": .screener, "SCREEN": .screener,
        "WEI": .wei, "MACRO": .wei,
        "OWN": .owners, "HOLD": .owners,
        "ALERT": .alerts, "ALERTS": .alerts,
        "HEAT": .heatmap, "HEATMAP": .heatmap,
        "RRG": .rrg, "ROT": .rrg,
        "DESK": .desk, "WORK": .desk,
        "SESSION": .session, "SES": .session,
        "FILING": .filings, "FILINGS": .filings, "EDGAR": .filings,
        "LOTS": .lots,
        "TWO": .two, "DES2": .two,
        "ICS": .ics,
        "NOTE": .notes, "NOTES": .notes,
        "ND": .newsdesk, "NEWSDESK": .newsdesk,
        "SIG": .signals, "SIGNALS": .signals,
        "BRIEF": .brief, "MB": .brief,
        "STATS": .stats,
        "SR": .stockresearch,
        "LIB": .library,
        "SET": .settings, "SETTINGS": .settings,
        "HORMUZ": .hormuz,
        "LAB": .lab,
        "REPORT": .reports, "REPORTS": .reports, "RP": .reports,
        "GEN": .generate, "GENERATE": .generate, "MEMO": .generate, "NEWMEMO": .generate, "NEWREPORT": .generate,
    ]

    /// Verbs that just open an app view — no ticker argument.
    private static let navActions: Set<MacMarketCommandAction> = [
        .newsdesk, .reports, .signals, .brief, .stats, .stockresearch, .library, .settings, .hormuz, .lab,
    ]

    /// `normalizeToken`: upper case, then only A–Z, 0–9, "." and "-".
    static func normalizeToken(_ token: String) -> String {
        let upper = token.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return String(String.UnicodeScalarView(upper.unicodeScalars.filter {
            ("A"..."Z").contains($0) || ("0"..."9").contains($0) || $0 == "." || $0 == "-"
        }))
    }

    /// `parseMarketCommand`.
    static func parse(_ raw: String) -> MacMarketCommand? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        let parts = text.split(whereSeparator: \.isWhitespace).map { normalizeToken(String($0)) }.filter { !$0.isEmpty }
        guard let first = parts.first else { return nil }
        let second = parts.count > 1 ? parts[1] : ""
        let action = verbs[first]
        let label = first.lowercased()
        // A second token that is a ticker and not itself a verb.
        let tickerArg: String? = !second.isEmpty && isTicker(second) && verbs[second] == nil ? second : nil

        if let action {
            switch action {
            case .home, .pulse, .wei, .alerts, .heatmap, .rrg, .session, .ics:
                return MacMarketCommand(action: action, ticker: nil, label: label, raw: text)
            case _ where navActions.contains(action):
                return MacMarketCommand(action: action, ticker: nil, label: label, raw: text)
            case .two, .notes:
                return MacMarketCommand(action: action, ticker: tickerArg, label: label, raw: text)
            case .desk:
                return MacMarketCommand(action: .desk, ticker: nil, label: "desk", raw: text, desk: second.isEmpty ? nil : second)
            case .lots:
                return MacMarketCommand(action: .lots, ticker: nil, label: "lots", raw: text)
            case .calendar, .screener:
                let screen = action == .screener && !second.isEmpty && tickerArg == nil ? second : nil
                return MacMarketCommand(action: action, ticker: tickerArg, label: label, raw: text, screen: screen)
            case .tracking:
                return MacMarketCommand(action: .tracking, ticker: tickerArg, label: "track", raw: text)
            case .generate:
                return MacMarketCommand(action: .generate, ticker: tickerArg, label: "generate", raw: text)
            case .news, .comp:
                return MacMarketCommand(action: action, ticker: tickerArg, label: label, raw: text)
            case .hp, .fa, .owners, .filings:
                return MacMarketCommand(action: action, ticker: tickerArg, label: label, raw: text)
            case .quote:
                // With a ticker, a quote; bare, it falls through to the ticker test and search.
                if let tickerArg { return MacMarketCommand(action: .quote, ticker: tickerArg, label: label, raw: text) }
            default:
                break
            }
        }

        if isTicker(first) && verbs[first] == nil && parts.count == 1 {
            return MacMarketCommand(action: .quote, ticker: first, label: "des", raw: text)
        }
        return MacMarketCommand(action: .search, ticker: nil, label: "search", raw: text, query: text)
    }

    /// `suggestMarketCommands`.
    static func suggest(_ raw: String, companies: [MacMarketCommandCompany], limit: Int = 8) -> [MacMarketCommandRow] {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let parsed = parse(text)
        var rows: [MacMarketCommandRow] = []
        func push(_ row: MacMarketCommandRow) {
            guard rows.count < limit, !rows.contains(where: { $0.id == row.id }) else { return }
            rows.append(row)
        }

        if let parsed, parsed.action == .quote, let ticker = parsed.ticker {
            push(MacMarketCommandRow(id: "quote:\(ticker)", title: ticker, subtitle: "DES · Market quote", action: .quote, ticker: ticker))
            push(MacMarketCommandRow(id: "news:\(ticker)", title: "NEWS \(ticker)", subtitle: "Headlines for this symbol", action: .news, ticker: ticker))
            push(MacMarketCommandRow(id: "comp:\(ticker)", title: "PEER \(ticker)", subtitle: "COMP / RV peers", action: .comp, ticker: ticker))
            push(MacMarketCommandRow(id: "hp:\(ticker)", title: "HP \(ticker)", subtitle: "History / compare graph", action: .hp, ticker: ticker))
            push(MacMarketCommandRow(id: "gen:\(ticker)", title: "GEN \(ticker)", subtitle: "Generate investment memo for this symbol (⌘N)", action: .generate, ticker: ticker))
        } else if let parsed, parsed.action != .search {
            push(MacMarketCommandRow(
                id: "\(parsed.action.rawValue):\(parsed.ticker ?? parsed.screen ?? "")",
                title: parsed.raw.uppercased(),
                subtitle: subtitle(for: parsed),
                action: parsed.action,
                ticker: parsed.ticker,
                companyId: parsed.companyId,
                query: parsed.query,
                screen: parsed.screen
            ))
        }

        let q = text.lowercased()
        if !q.isEmpty && ("generate".contains(q) || "memo".contains(q) || "report".contains(q)) {
            push(MacMarketCommandRow(id: "generate", title: "GENERATE", subtitle: "Launch Report Customizer / Generate Memo (⌘N)", action: .generate))
        }
        if !q.isEmpty {
            let upper = text.uppercased()
            for company in companies {
                let ticker = (company.ticker ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                let name = company.name ?? ""
                let hay = "\(ticker) \(name)".lowercased()
                guard hay.contains(q) || (!ticker.isEmpty && ticker.hasPrefix(upper)) else { continue }
                push(MacMarketCommandRow(
                    id: "company:\(company.id)",
                    title: ticker.isEmpty ? name : ticker,
                    subtitle: name,
                    action: ticker.isEmpty ? .company : .quote,
                    ticker: ticker.isEmpty ? nil : ticker,
                    companyId: company.id
                ))
            }
        }

        if rows.isEmpty {
            push(MacMarketCommandRow(id: "help", title: "NVDA · HP · FA · HEAT · RRG · DESK · EVTS", subtitle: "Command examples", action: .help))
        }
        return Array(rows.prefix(limit))
    }

    /// `commandSubtitle`.
    static func subtitle(for parsed: MacMarketCommand) -> String {
        switch parsed.action {
        case .news: return "Open Market headlines"
        case .comp: return "Open COMP / RV peers"
        case .calendar: return "Watchlist event calendar"
        case .tracking: return "Open Tracking"
        case .generate: return "Generate Report / Research Memo (⌘N)"
        case .home: return "Home desk"
        case .pulse: return "Pulse"
        case .quote: return "Market quote"
        case .hp: return "HP history workbench"
        case .fa: return "FA lite financials"
        case .screener: return "EQS screener"
        case .wei: return "WEI macro strip"
        case .owners: return "Ownership summary"
        case .alerts: return "Alert rules"
        case .heatmap: return "Sector heat map"
        case .rrg: return "RRG-lite rotation"
        case .desk: return "Saved Market desk"
        case .session: return "1D session + VWAP"
        case .filings: return "EDGAR filings"
        case .lots: return "Book lots"
        case .two: return "2-up DES quotes"
        case .ics: return "Export EVTS calendar"
        case .notes: return "Ticker notes"
        case .newsdesk: return "News desk"
        case .signals: return "Signals lab"
        case .brief: return "Morning Brief on Pulse"
        case .stats: return "Trader stats"
        case .stockresearch: return "Stock research trackers"
        case .library: return "Source library"
        case .settings: return "Settings"
        case .hormuz: return "Hormuz library"
        case .lab: return "Innovation lab"
        // The website has no subtitle of its own for Reports.
        case .reports, .company, .search, .help: return "Run command"
        }
    }

    /// `routeForMarketCommand`: the website's path and query for a command (nil when it opens
    /// nothing). The path is the router's, without its leading slash.
    static func webRoute(for cmd: MacMarketCommand) -> (path: String, query: [String: String])? {
        let t: [String: String] = cmd.ticker.map { ["ticker": $0] } ?? [:]
        func radar(_ query: [String: String]) -> (String, [String: String]) { ("market-radar", query) }
        switch cmd.action {
        case .home: return ("", [:])
        case .tracking: return ("tracking", [:])
        case .pulse: return ("weekly-summary", [:])
        case .company: return cmd.companyId.map { ($0, [:]) }
        case .calendar: return radar(t.merging(["panel": "calendar"]) { $1 })
        case .news: return radar(t.merging(["panel": "news"]) { $1 })
        case .comp: return radar(t.merging(["panel": "peers"]) { $1 })
        case .hp: return radar(t.merging(["panel": "hp"]) { $1 })
        case .fa: return radar(t.merging(["panel": "fa", "tab": "financials"]) { $1 })
        case .screener: return radar(["panel": "screener"].merging(cmd.screen.map { ["screen": $0] } ?? [:]) { $1 })
        case .wei: return radar(["panel": "wei"])
        case .owners: return radar(t.merging(["panel": "owners", "tab": "holders"]) { $1 })
        case .alerts: return radar(["panel": "alerts"])
        case .heatmap: return radar(["panel": "heatmap"])
        case .rrg: return radar(t.merging(["panel": "rrg"]) { $1 })
        case .session: return radar(t.merging(["panel": "hp", "range": "1d"]) { $1 })
        case .filings: return radar(t.merging(["panel": "filings"]) { $1 })
        case .desk: return radar(["panel": "desk"].merging(cmd.desk.map { ["desk": $0] } ?? [:]) { $1 })
        case .lots: return ("tracking", ["panel": "lots"])
        case .two: return radar(t.merging(["two": "1"]) { $1 })
        case .ics: return radar(["panel": "calendar", "ics": "1"])
        case .notes: return radar(t.merging(["panel": "notes"]) { $1 })
        case .quote: return cmd.ticker == nil ? nil : radar(t)
        case .newsdesk: return ("news-desk", [:])
        case .reports: return ("reports", [:])
        case .signals: return ("innovation-lab/market-pulse", [:])
        case .brief: return ("weekly-summary", ["panel": "brief"])
        case .stats: return ("trader-stats", [:])
        case .stockresearch: return ("stock-research", [:])
        case .library: return ("source-library", [:])
        case .settings: return ("settings", [:])
        case .hormuz: return ("innovation-lab/hormuz", [:])
        case .lab: return ("innovation-lab", [:])
        case .search: return cmd.query.map { ("", ["q": $0]) }
        case .generate, .help: return nil
        }
    }
}

// MARK: - Where a command goes on the Mac

/// The Mac's destination for a command's web route.
enum MacBureauCommandRoute: Equatable {
    /// A desk of the masthead (or Settings).
    case desk(MacTab)
    /// The Market desk with a symbol chosen.
    case ticker(String)
    /// A company's page (its Research Desk dossier, held on the rail).
    case company(String)
    /// The report sheet, for a company when the command names one the Mac knows.
    case generate(companyId: String?)
    /// A page the Mac has no desk of its own for: the website's route in the research browser.
    case browser(path: String, query: [String: String])
    case none

    /// Every `market-radar` route is a section of the one Market page, which the Mac's
    /// Market desk also is; its 2-up view (TWO) and the calendar export (ICS) are not on the
    /// Mac, so those two stay on the website.
    static func of(_ cmd: MacMarketCommand, companies: [MacCompany]) -> MacBureauCommandRoute {
        switch cmd.action {
        case .help: return .none
        case .generate:
            let found = cmd.ticker.flatMap { ticker in
                companies.first { ($0.ticker ?? "").uppercased() == ticker.uppercased() }
            }
            return .generate(companyId: found?.id ?? cmd.companyId)
        case .home, .search: return .desk(.home)
        case .tracking, .lots: return .desk(.portfolio)
        case .pulse, .brief: return .desk(.pulse)
        case .newsdesk: return .desk(.news)
        case .reports: return .desk(.documents)
        case .settings: return .desk(.settings)
        case .company:
            return cmd.companyId.map { .company($0) } ?? .none
        case .quote, .news, .comp, .calendar, .hp, .fa, .screener, .wei, .owners, .alerts, .heatmap,
             .rrg, .session, .filings, .desk, .notes:
            if cmd.action == .quote && cmd.ticker == nil { return .none }
            return cmd.ticker.map { .ticker($0) } ?? .desk(.market)
        case .two, .ics, .signals, .stats, .stockresearch, .library, .hormuz, .lab:
            guard let route = MacMarketCommands.webRoute(for: cmd) else { return .none }
            return .browser(path: route.path, query: route.query)
        }
    }
}

extension MacAppStore {
    /// Runs a palette command where the Mac keeps that page (see `MacBureauCommandRoute`).
    /// Nothing here starts a run: Generate only opens the report sheet.
    func runMarketCommand(_ cmd: MacMarketCommand) {
        switch MacBureauCommandRoute.of(cmd, companies: companies) {
        case .none:
            return
        case .desk(let tab):
            heldCompanyId = nil
            selectedTab = tab
        case .ticker(let ticker):
            heldCompanyId = nil
            showTicker(ticker)
        case .company(let id):
            if let company = companies.first(where: { $0.id == id }) { openCompanyPage(company) }
        case .generate(let id):
            requestNewReport(for: id.flatMap { id in companies.first { $0.id == id } })
        case .browser(let path, let query):
            withAnimation(.easeInOut(duration: 0.18)) {
                openInEmbeddedBrowser(MacConfig.webURL(path: path, query: query))
            }
        }
    }
}
