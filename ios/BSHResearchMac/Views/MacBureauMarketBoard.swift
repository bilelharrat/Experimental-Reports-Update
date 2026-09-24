//
//  MacBureauMarketBoard.swift
//  BSHResearchMac
//
//  The lower half of Bureau's Market page and its aside, as on the website: the Nasdaq
//  quote workspace (Profile … Earnings), the desk calendar (EVTS), breadth, the market
//  board with its sector heat, and the Tape with the book's risk and lens above it.
//

import AppKit
import SwiftUI

// MARK: - Quote workspace (QuoteWorkspace.vue)

struct MacBureauMarketWorkspace: View {
    @Environment(\.colorScheme) private var colorScheme
    let ticker: String
    let workspace: MacQuoteWorkspace?
    let points: [MacChartPoint]
    let range: MacChartRange
    let lastPrice: Double?
    @ObservedObject var feed: MacBureauMarketFeed
    @AppStorage("mac.quote.workspaceTab") private var tabRaw = "Profile"

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private static let tabs = ["Profile", "Statistics", "Financials", "Analysis", "Holders", "Options", "Historical", "Earnings"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Press [ ] to flip workspace tabs")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .lineLimit(1)
                .bureauLines(14, size: 11)
                .padding(.top, 24)
            MacBureauMarketSegmented(Self.tabs.map { ($0, $0) }, selection: $tabRaw)
                .padding(.top, 24 + 8)
                .padding(.bottom, 12)
            if workspace == nil {
                Text("Loading…")
                    .font(BSHType.bureauSans(14))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
                    .padding(.vertical, 24)
                    .padding(.horizontal, 4)
            } else {
                content
            }
        }
        .background(
            // `[` and `]` flip the tabs, as on the website.
            Group {
                Button("") { flip(-1) }.keyboardShortcut("[", modifiers: [])
                Button("") { flip(1) }.keyboardShortcut("]", modifiers: [])
            }
            .opacity(0)
            .allowsHitTesting(false)
        )
    }

    private func flip(_ step: Int) {
        let index = Self.tabs.firstIndex(of: tabRaw) ?? 0
        tabRaw = Self.tabs[(index + step + Self.tabs.count) % Self.tabs.count]
    }

    @ViewBuilder
    private var content: some View {
        switch tabRaw {
        case "Statistics": statistics
        case "Financials": financials
        case "Analysis": analysis
        case "Holders": holders
        case "Options": options
        case "Historical": history
        case "Earnings": earnings
        default: profile
        }
    }

    private func sectionLabel(_ text: String) -> some View {
        MacBureauMarketLabel(text)
    }

    private func emptyLine(_ text: String) -> some View {
        Text(text)
            .font(BSHType.bureauSans(14))
            .tracking(-0.084)
            .foregroundStyle(ink.muted)
            .lineLimit(1)
            .bureauLines(20, size: 14)
    }

    // Profile

    private var profile: some View {
        let p = workspace?.profile
        let s = workspace?.summary
        let description = (p?.description?.isEmpty == false) ? p?.description : nil
        return VStack(alignment: .leading, spacing: 12) {
            Text(description ?? "No company profile for this symbol.")
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .bureauLines(20, size: 14)
                .textSelection(.enabled)
            if let book = MacBureauMarketETFBook.book(ticker) {
                etfBook(book)
            }
            MacBureauMarketStats(items: [
                ("Sector", p?.sector ?? s?.sector ?? "—", nil),
                ("Industry", p?.industry ?? s?.industry ?? "—", nil),
                ("Region", p?.region ?? "—", nil),
                ("Website", p?.website ?? "—", nil),
            ])
        }
    }

    /// The illustrative ETF weights the website keeps for the index funds.
    private struct ETFMove {
        let ticker: String
        let weight: Double
        let change: Double?
        let contribution: Double?
        let order: Int
    }

    /// etfContributorMoves: each holding's move and its share of the fund's, largest first.
    private func etfMoves(_ book: MacBureauMarketETFBook.Book) -> [ETFMove] {
        var moves: [ETFMove] = []
        for (index, holding) in book.holdings.enumerated() {
            let change = feed.quote(holding.ticker)?.changePct
            let contribution: Double? = change.map { $0 * holding.weight / 100 }
            moves.append(ETFMove(ticker: holding.ticker, weight: holding.weight, change: change, contribution: contribution, order: index))
        }
        return moves.sorted { a, b in
            let x = abs(a.contribution ?? 0), y = abs(b.contribution ?? 0)
            return x != y ? x > y : a.order < b.order
        }
    }

    private func etfCells(_ move: ETFMove) -> [(String, Color?)] {
        let changeTone: Color? = (move.change ?? 0) >= 0 ? ink.success : ink.danger
        let contributionTone: Color? = (move.contribution ?? 0) >= 0 ? ink.success : ink.danger
        let contribution = move.contribution.map { ($0 >= 0 ? "+" : "") + String(format: "%.2f", $0) } ?? "—"
        return [
            (move.ticker, nil),
            (String(format: "%.1f%%", move.weight), nil),
            (MacBureauMarketFormat.signed(move.change) ?? "—", changeTone),
            (contribution, contributionTone),
        ]
    }

    private func etfBook(_ book: MacBureauMarketETFBook.Book) -> some View {
        let rows: [[(String, Color?)]] = etfMoves(book).map(etfCells)
        return VStack(alignment: .leading, spacing: 8) {
            Text("ETF HOLDINGS (ILLUSTRATIVE)")
                .font(BSHType.bureauSans(12, weight: .semibold))
                .tracking(0.72)
                .foregroundStyle(ink.notice)
                .lineLimit(1)
                .bureauLines(16, size: 12)
            Text("Illustrative weights — not live holdings")
                .font(BSHType.bureauSans(11, weight: .medium))
                .tracking(0.066)
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .bureauLines(14, size: 11)
            Text("\(book.name) · \(book.asOf)")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .lineLimit(1)
                .bureauLines(14, size: 11)
            MacBureauMarketTable(headers: ["Symbol", "Weight", "Change", "Contrib"], rows: rows)
        }
        // px-3 py-2 inside a 1pt CSS border, which takes up room of its own.
        .padding(.horizontal, 12 + 1)
        .padding(.vertical, 8 + 1)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill(ink.fillTertiary.opacity(0.45)))
        .overlay(RoundedRectangle(cornerRadius: 6, style: .circular).strokeBorder(ink.rule, lineWidth: 1))
    }

    // Statistics

    private var statistics: some View {
        let s = workspace?.summary
        let p = workspace?.profile
        return MacBureauMarketStats(items: [
            ("1y target", s?.oneYearTarget ?? "—", nil), ("Bid", s?.bid ?? "—", nil), ("Ask", s?.ask ?? "—", nil),
            ("Dividend", s?.dividend ?? "—", nil), ("Ex-dividend", s?.exDividend ?? "—", nil), ("Beta", s?.beta ?? "—", nil),
            ("Alpha", s?.alpha ?? "—", nil), ("AUM", s?.aum ?? "—", nil), ("Expense ratio", s?.expenseRatio ?? "—", nil),
            ("Sector", s?.sector ?? p?.sector ?? "—", nil), ("Industry", s?.industry ?? p?.industry ?? "—", nil), ("Yield", s?.yield ?? "—", nil),
        ])
    }

    // Financials

    private var financials: some View {
        let lines = MacQuoteMath.faLite(workspace?.financials)
        let sheets: [(String, MacFinTable?)] = [
            ("Income statement", workspace?.financials?.income),
            ("Balance sheet", workspace?.financials?.balance),
            ("Cash flow", workspace?.financials?.cashflow),
            ("Financial ratios", workspace?.financials?.ratios),
        ]
        return VStack(alignment: .leading, spacing: 20) {
            if !lines.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        sectionLabel("FA lite")
                        Spacer()
                        Text("YoY").font(BSHType.bureauSans(11)).foregroundStyle(ink.muted)
                    }
                    MacBureauMarketStats(items: lines.map { line in
                        (line.label, line.latestRaw + (line.yoy.map { String(format: "  %+.1f%% YoY", $0) } ?? ""), nil)
                    })
                }
            }
            ForEach(sheets, id: \.0) { sheet in
                VStack(alignment: .leading, spacing: 8) {
                    sectionLabel(sheet.0)
                    if let table = sheet.1, !table.rows.isEmpty {
                        MacBureauMarketTable(
                            headers: [""] + table.headers,
                            rows: table.rows.map { row in
                                [(row.label, nil)] + (0..<table.headers.count).map { index in
                                    (index < row.values.count && !row.values[index].isEmpty ? row.values[index] : "—", nil)
                                }
                            }
                        )
                    } else {
                        emptyLine("No financial statements for this symbol.")
                    }
                }
            }
        }
    }

    // Analysis

    private var analysis: some View {
        let a = workspace?.analysis
        let total = (a?.buy ?? 0) + (a?.hold ?? 0) + (a?.sell ?? 0)
        return VStack(alignment: .leading, spacing: 16) {
            MacBureauMarketStats(items: [
                ("1y target", MacBureauMarketFormat.price(a?.target), nil),
                ("Target low", MacBureauMarketFormat.price(a?.targetLow), nil),
                ("Target high", MacBureauMarketFormat.price(a?.targetHigh), nil),
                ("Buy", "\(a?.buy ?? 0)", nil), ("Hold", "\(a?.hold ?? 0)", nil), ("Sell", "\(a?.sell ?? 0)", nil),
            ])
            if total > 0 {
                Text("\(total) analyst ratings")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
            }
            MacBureauMarketTable(
                headers: ["Period", "EPS", "High", "Low", "Est."],
                rows: (a?.quarterly ?? []).map { row in
                    [
                        (row.period, nil),
                        (row.consensus.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                        (row.high.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                        (row.low.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                        (row.estimates.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                    ]
                }
            )
        }
    }

    // Holders

    private var holders: some View {
        let h = workspace?.holders
        let movers = MacQuoteMath.ownershipMovers(h)
        return VStack(alignment: .leading, spacing: 16) {
            MacBureauMarketStats(items: [
                ("Inst. ownership", h?.ownershipPct ?? "—", nil),
                ("Shares out", h?.sharesOut ?? "—", nil),
                ("Holdings value", h?.holdingsValue ?? "—", nil),
            ])
            if !movers.buyers.isEmpty || !movers.sellers.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    moverList("Top increases", movers.buyers.map { ($0.owner, $0.changePct ?? "—") }, tone: ink.success)
                    moverList("Top decreases", movers.sellers.map { ($0.owner, $0.changePct ?? "—") }, tone: ink.danger)
                }
            }
            MacBureauMarketTable(
                headers: ["Holder", "Shares", "Change", "Value"],
                rows: (h?.holders ?? []).map { [($0.owner, nil), ($0.shares ?? "—", nil), ($0.changePct ?? "—", nil), ($0.value ?? "—", nil)] }
            )
            if let summary = workspace?.insiders?.summary, !summary.isEmpty {
                MacBureauMarketTable(
                    headers: ["Insider activity", "3 mo", "12 mo"],
                    rows: summary.map { [($0.label, nil), ($0.months3 ?? "—", nil), ($0.months12 ?? "—", nil)] }
                )
            }
        }
    }

    private func moverList(_ title: String, _ rows: [(String, String)], tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionLabel(title)
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                (Text(row.0 + " ").foregroundColor(ink.ink) + Text(row.1).foregroundColor(tone))
                    .font(BSHType.bureauSans(12))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // Options

    private var options: some View {
        let rows = workspace?.options?.rows ?? []
        return VStack(alignment: .leading, spacing: 16) {
            if let move = MacQuoteMath.expectedMove(rows, spot: lastPrice) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    MacBureauMarketLabel("Expected move")
                    Text(String(format: "±%.1f%%", move.movePct))
                        .font(MacBureauMarketText.font(14, weight: .semibold, tabular: true))
                        .foregroundStyle(ink.ink)
                    Text("to \(move.expiry) (\(move.days)d)")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.muted)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill(ink.fillSecondary))
            }
            if let snap = MacQuoteMath.optionsSnapshot(rows, spot: lastPrice) {
                MacBureauMarketStats(items: [
                    ("Nearest expiry", snap.nearestExpiry ?? "—", nil),
                    ("ATM strike", snap.atmStrike.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                    ("Put/call vol", snap.putCallVolume.map { String(format: "%.2f", $0) } ?? "—", nil),
                    ("Put/call OI", snap.putCallOi.map { String(format: "%.2f", $0) } ?? "—", nil),
                    ("Call volume", MacBureauMarketFormat.compact(snap.callVolume), nil),
                    ("Put volume", MacBureauMarketFormat.compact(snap.putVolume), nil),
                ])
            }
            if rows.isEmpty {
                emptyLine("No option chain for this symbol.")
            } else {
                MacBureauMarketTable(
                    headers: ["Expiry", "Call", "Strike", "Put", "Volume"],
                    rows: rows.map { [($0.expiry, nil), ($0.callLast ?? "—", nil), ($0.strike.map { MacBureauMarketFormat.number($0) } ?? "—", nil), ($0.putLast ?? "—", nil), ("\($0.callVolume ?? "—") / \($0.putVolume ?? "—")", nil)] }
                )
            }
        }
    }

    // Historical

    private var history: some View {
        MacBureauMarketTable(
            headers: ["Date", "Open", "High", "Low", "Price", "Volume"],
            rows: points.suffix(80).reversed().map { p in
                [
                    (MacChartFormat.stamp(p.t, range: range), nil),
                    (MacBureauMarketFormat.price(p.open), nil),
                    (MacBureauMarketFormat.price(p.high), nil),
                    (MacBureauMarketFormat.price(p.low), nil),
                    (MacBureauMarketFormat.price(p.close), nil),
                    (MacBureauMarketFormat.compact(p.volume), nil),
                ]
            }
        )
    }

    // Earnings

    private var earnings: some View {
        let e = workspace?.earnings
        return VStack(alignment: .leading, spacing: 16) {
            MacBureauMarketStats(items: [("Next earnings", (e?.nextDate ?? "—") + ((e?.nextEstimated ?? false) ? " est." : ""), nil)])
            if let past = e?.past, !past.isEmpty {
                MacBureauMarketTable(
                    headers: ["Period", "Date", "EPS", "Est.", "Surprise"],
                    rows: past.map { row in
                        [
                            (row.period, nil),
                            (row.reported ?? "—", nil),
                            (row.eps.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                            (row.estimate.map { MacBureauMarketFormat.number($0) } ?? "—", nil),
                            (row.surprisePct.map { "\(MacBureauMarketFormat.number($0))%" } ?? "—", nil),
                        ]
                    }
                )
            } else {
                emptyLine("No earnings history for this symbol.")
            }
        }
    }
}

/// `.yf-fin-table`: 11pt tabular rows, 6 × 8pt cells; the first column is the row's label
/// in secondary ink, the header row in muted semibold. Wide tables scroll sideways.
struct MacBureauMarketTable: View {
    @Environment(\.colorScheme) private var colorScheme
    let headers: [String]
    let rows: [[(String, Color?)]]

    var body: some View {
        if !rows.isEmpty {
            ViewThatFits(in: .horizontal) {
                grid
                ScrollView(.horizontal, showsIndicators: false) { grid.fixedSize(horizontal: true, vertical: false) }
            }
        }
    }

    private var grid: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        return Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                    GridRow {
                        ForEach(Array(headers.enumerated()), id: \.offset) { _, header in
                            Text(header)
                                .font(BSHType.bureauSans(11, weight: .semibold))
                                .tracking(0.066)
                                .foregroundStyle(ink.muted)
                                .lineLimit(1)
                                .padding(.horizontal, 8)
                                .frame(height: 26, alignment: .leading)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        GridRow {
                            ForEach(Array(row.enumerated()), id: \.offset) { index, cell in
                                Text(cell.0)
                                    .font(BSHType.bureauSans(11, weight: index == 0 ? .medium : .regular).monospacedDigit())
                                    .tracking(0.066)
                                    .foregroundStyle(cell.1 ?? (index == 0 ? ink.secondary : ink.ink))
                                    .lineLimit(1)
                                    .padding(.horizontal, 8)
                                    .frame(height: 26, alignment: .leading)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                }
        .frame(minWidth: 576, maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - EVTS · Desk calendar

struct MacBureauMarketCalendar: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let select: (String) -> Void
    @State private var filter = "all"
    @State private var week = true

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var events: [MacCalendarEvent] {
        let sorted = feed.calendar.sorted { $0.date < $1.date }
        let kinds: [String: String] = ["earnings": "earnings", "dividends": "dividend", "macro": "macro", "book": "catalyst"]
        guard filter != "all" else { return Array(sorted.prefix(60)) }
        let wanted = kinds[filter] ?? filter
        return Array(sorted.filter { $0.kind == wanted || ($0.kind == "dividends" && wanted == "dividend") }.prefix(60))
    }

    /// macroWeekGrid: Monday to Sunday of this week, in UTC as the website counts it.
    private var weekDays: [(date: String, label: String, events: [MacCalendarEvent])] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let now = Date()
        let weekday = calendar.component(.weekday, from: now) // 1 = Sunday
        let mondayOffset = weekday == 1 ? -6 : 2 - weekday
        let today = calendar.startOfDay(for: now)
        let monday = calendar.date(byAdding: .day, value: mondayOffset, to: today) ?? today
        let iso = DateFormatter()
        iso.locale = Locale(identifier: "en_US_POSIX")
        iso.timeZone = TimeZone(identifier: "UTC")
        iso.dateFormat = "yyyy-MM-dd"
        let label = DateFormatter()
        label.locale = Locale(identifier: "en_US")
        label.timeZone = TimeZone(identifier: "UTC")
        label.dateFormat = "EEE"
        return (0..<7).map { offset in
            let day = calendar.date(byAdding: .day, value: offset, to: monday) ?? monday
            let key = iso.string(from: day)
            return (key, label.string(from: day), events.filter { $0.date.prefix(10) == key })
        }
    }

    private func title(_ event: MacCalendarEvent) -> String {
        switch event.kind {
        case "dividend", "dividends": return "Ex-dividend"
        case "macro": return event.title.isEmpty ? "Economic print" : event.title
        case "catalyst": return event.title.isEmpty ? "Catalyst" : event.title
        default: return event.title.isEmpty ? "Earnings" : event.title
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauMarketLabel("EVTS · Desk calendar")
                Spacer(minLength: 0)
                if !events.isEmpty {
                    MacBureauMarketRangeItem("Export ICS", action: exportICS)
                }
                if feed.calendarLoading {
                    Text("Loading…").font(BSHType.bureauSans(11)).foregroundStyle(ink.muted)
                }
            }
            .frame(height: 22)
            .padding(.bottom, 8)
            HStack(spacing: 4) {
                ForEach([("all", "All"), ("earnings", "Earnings"), ("dividends", "Dividends"), ("macro", "Macro"), ("book", "Book")], id: \.0) { item in
                    MacBureauMarketRangeItem(item.1, selected: filter == item.0) { filter = item.0 }
                }
            }
            .padding(.bottom, 8)
            HStack(spacing: 4) {
                MacBureauMarketRangeItem("List", selected: !week) { week = false }
                MacBureauMarketRangeItem("Week", selected: week) { week = true }
            }
            .padding(.bottom, 12)
            if week {
                weekGrid
                    .padding(.bottom, 12)
            }
            if events.isEmpty {
                Text("No events in this filter for the watchlist window.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
            } else if !week {
                MacBureauMarketTable(
                    headers: ["Date", "Symbol", "Event", "Session"],
                    rows: events.map { event in
                        [
                            (event.date, nil),
                            (event.ticker ?? event.name ?? "—", event.ticker == nil ? ink.muted : nil),
                            (title(event) + (event.confirmed ? "" : " est."), nil),
                            (event.time ?? "—", nil),
                        ]
                    }
                )
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
    }

    private var weekGrid: some View {
        HStack(alignment: .top, spacing: 8) {
            ForEach(weekDays, id: \.date) { day in
                VStack(alignment: .leading, spacing: 0) {
                    Text("\(day.label) · \(day.date.dropFirst(5))")
                        .font(BSHType.bureauSans(11, weight: .semibold))
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .bureauLines(16.5, size: 11)
                        .padding(.bottom, 5.6)
                    ForEach(Array(day.events.prefix(4).enumerated()), id: \.offset) { _, event in
                        MacBureauMarketWeekEvent(label: event.ticker ?? event.kind, title: title(event), ink: ink) {
                            if let t = event.ticker { select(t) }
                        }
                        .padding(.bottom, 4)
                    }
                }
                .padding(7.2)
                .frame(maxWidth: .infinity, minHeight: 88, maxHeight: .infinity, alignment: .topLeading)
                .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(ink.ink(0.04)))
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// Writes the events to an .ics file the user saves (the website's Export ICS).
    private func exportICS() {
        var lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BSH//EVTS//EN", "X-WR-CALNAME:BSH EVTS"]
        for event in events {
            let day = event.date.prefix(10).replacingOccurrences(of: "-", with: "")
            lines += [
                "BEGIN:VEVENT",
                "UID:\(event.id.uuidString)@bsh",
                "DTSTART;VALUE=DATE:\(day)",
                "SUMMARY:\([event.ticker, title(event)].compactMap { $0 }.joined(separator: " "))",
                "END:VEVENT",
            ]
        }
        lines.append("END:VCALENDAR")
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "bsh-evts.ics"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? lines.joined(separator: "\r\n").write(to: url, atomically: true, encoding: .utf8)
    }
}

/// `.yf-week-event`: the symbol (or the kind) and the event, clipped to the day.
private struct MacBureauMarketWeekEvent: View {
    let label: String
    let title: String
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            Text("\(label) \(title)")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(hovered ? ink.ink : ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .padding(.horizontal, 4)
                .frame(maxWidth: .infinity, alignment: .leading)
                .bureauLines(18, size: 11)
                .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill(hovered ? ink.accent.opacity(0.1) : .clear))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Breadth

struct MacBureauMarketBreadth: View {
    @Environment(\.colorScheme) private var colorScheme
    let rows: [MacBureauMarketBoardRow]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let changes = rows.compactMap(\.change)
        let adv = changes.filter { $0 > 0.05 }.count
        let dec = changes.filter { $0 < -0.05 }.count
        let ranged = rows.compactMap { row -> Double? in
            guard let last = row.last, let high = row.weekHigh, let low = row.weekLow, high > low else { return nil }
            return (last - low) / (high - low)
        }
        let nearHigh = ranged.isEmpty ? nil : Double(ranged.filter { $0 >= 0.95 }.count) / Double(ranged.count) * 100
        return VStack(alignment: .leading, spacing: 8) {
            MacBureauMarketLabel("Breadth")
            HStack(spacing: 20) {
                Text("Adv \(adv)")
                Text("Dec \(dec)")
                if let nearHigh {
                    Text("\(Int(nearHigh.rounded()))% near high")
                }
            }
            .font(MacBureauMarketText.font(12.48))
            .foregroundStyle(ink.ink)
            .lineLimit(1)
            .bureauLines(18.72, size: 12.48)
            .padding(.horizontal, 13.6)
            .padding(.vertical, 10.4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.ink(0.04)))
        }
    }
}

// MARK: - The market board

struct MacBureauMarketBoard: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let boardRows: [MacBureauMarketBoardRow]
    let watchRows: [MacBureauMarketBoardRow]
    let selected: String
    let select: (String) -> Void
    @State private var tab = "gainers"
    @State private var sector = ""
    @State private var query = ""

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var gainers: [MacBureauMarketBoardRow] {
        Array(boardRows.filter { ($0.change ?? 0) > 0 }.sorted { ($0.change ?? 0) > ($1.change ?? 0) }.prefix(12))
    }
    private var losers: [MacBureauMarketBoardRow] {
        Array(boardRows.filter { ($0.change ?? 0) < 0 }.sorted { ($0.change ?? 0) < ($1.change ?? 0) }.prefix(12))
    }
    private var active: [MacBureauMarketBoardRow] {
        Array(boardRows.filter { ($0.volume ?? 0) > 0 }.sorted { ($0.volume ?? 0) > ($1.volume ?? 0) }.prefix(12))
    }
    private var screener: [MacBureauMarketBoardRow] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return feed.universe
            .filter { sector.isEmpty || $0.sector == sector }
            .filter { q.isEmpty || "\($0.ticker) \($0.name ?? "") \($0.sector ?? "")".lowercased().contains(q) }
            .sorted { ($0.marketCap ?? 0) > ($1.marketCap ?? 0) }
            .prefix(40)
            .map { MacBureauMarketBoardRow(ticker: $0.ticker, name: $0.name ?? $0.ticker, last: $0.last, change: $0.changePct, volume: $0.volume, weekHigh: nil, weekLow: nil, currency: "USD", sector: $0.sector, marketCap: $0.marketCap) }
    }

    private var rows: [MacBureauMarketBoardRow] {
        switch tab {
        case "losers": return losers
        case "active": return active
        case "watchlist": return watchRows
        case "screener": return screener
        default: return gainers
        }
    }

    /// sectorHeatmap: each sector's average move, its biggest mover and how many names.
    private var heat: [(sector: String, avg: Double, leader: String?, count: Int)] {
        var buckets: [String: (sum: Double, count: Int, leader: (String, Double)?)] = [:]
        for row in feed.universe {
            guard let change = row.changePct else { continue }
            let sector = (row.sector ?? "").trimmingCharacters(in: .whitespaces).isEmpty ? "Unknown" : row.sector!
            var bucket = buckets[sector] ?? (0, 0, nil)
            bucket.sum += change
            bucket.count += 1
            if abs(change) > abs(bucket.leader?.1 ?? -1) || bucket.leader == nil { bucket.leader = (row.ticker, change) }
            buckets[sector] = bucket
        }
        return buckets
            .filter { $0.value.count >= 2 }
            .map { (sector: $0.key, avg: $0.value.sum / Double($0.value.count), leader: $0.value.leader?.0, count: $0.value.count) }
            .sorted { abs($0.avg) > abs($1.avg) }
            .prefix(12)
            .map { $0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketSegmented(options: [
                ("gainers", "Gainers", gainers.count),
                ("losers", "Losers", losers.count),
                ("active", "Most Active", active.count),
                ("watchlist", "Watchlist", watchRows.count),
                ("screener", "Screener", screener.count),
            ], selection: $tab)
            .padding(.bottom, 12)

            if tab == "screener" {
                screenerFilters
                    .padding(.bottom, 12)
            }

            if !heat.isEmpty && (tab == "screener" || tab == "gainers") {
                VStack(alignment: .leading, spacing: 8) {
                    MacBureauMarketLabel("Sector heat")
                    MacBureauMarketAutoGrid(minimum: 120, spacing: 8) {
                        ForEach(heat, id: \.sector) { cell in
                            MacBureauMarketHeatCell(sector: cell.sector, leader: cell.leader, avg: cell.avg, count: cell.count, ink: ink) {
                                sector = cell.sector
                                tab = "screener"
                                if let leader = cell.leader { select(leader) }
                            }
                        }
                    }
                }
                .padding(.bottom, 16)
            }

            table
        }
    }

    private var screenerFilters: some View {
        HStack(alignment: .bottom, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Sector").font(BSHType.bureauSans(11, weight: .medium)).foregroundStyle(ink.muted)
                Picker("", selection: $sector) {
                    Text("Any").tag("")
                    ForEach(feed.sectors, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .frame(width: 180)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Search").font(BSHType.bureauSans(11, weight: .medium)).foregroundStyle(ink.muted)
                MacBureauField(placeholder: "Name or ticker", text: $query, size: 13, height: 28)
                    .frame(width: 220)
            }
        }
    }

    private var table: some View {
        let screenerTab = tab == "screener"
        return VStack(spacing: 0) {
            MacBureauMarketBoardLine(screener: screenerTab) {
                headText("Symbol")
            } price: {
                headText("Price")
            } change: {
                headText("Change")
            } extra: {
                headText(screenerTab ? "Mkt cap" : "Volume")
            }
            // The line reads its width, so it takes its height from here: one 14pt line.
            .frame(height: 14)
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 8)

            if rows.isEmpty {
                Text("No live quotes yet for names in this list.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .frame(maxWidth: .infinity)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
                    .padding(.vertical, 32)
            } else {
                ForEach(rows) { row in
                    MacBureauMarketBoardRowView(row: row, screener: screenerTab, selected: row.ticker == selected, ink: ink) {
                        select(row.ticker)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .bureauMarketTray()
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
    }

    private func headText(_ title: String) -> some View {
        Text(title)
            .font(BSHType.bureauSans(11, weight: .semibold))
            .tracking(0.066)
            .foregroundStyle(ink.muted)
            .lineLimit(1)
            .bureauLines(14, size: 11)
    }
}

/// The board's grid: `minmax(0,1.6fr) minmax(0,.8fr) minmax(0,.7fr) minmax(0,.7fr)`, 12pt apart.
private struct MacBureauMarketBoardLine<A: View, B: View, C: View, D: View>: View {
    let screener: Bool
    @ViewBuilder var symbol: () -> A
    @ViewBuilder var price: () -> B
    @ViewBuilder var change: () -> C
    @ViewBuilder var extra: () -> D

    var body: some View {
        GeometryReader { geo in
            let unit = (geo.size.width - 36) / 3.8
            HStack(spacing: 12) {
                symbol().frame(width: unit * 1.6, alignment: .leading)
                price().frame(width: unit * 0.8, alignment: .trailing)
                change().frame(width: unit * 0.7, alignment: .trailing)
                extra().frame(width: unit * 0.7, alignment: .trailing)
            }
            .frame(height: geo.size.height)
        }
    }
}

private struct MacBureauMarketBoardRowView: View {
    let row: MacBureauMarketBoardRow
    let screener: Bool
    let selected: Bool
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            MacBureauMarketBoardLine(screener: screener) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(row.ticker)
                        .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                        .tracking(-0.15)
                        .foregroundStyle(ink.ink)
                        .lineLimit(1)
                        .bureauLines(20, size: 15)
                    Text(row.name)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .bureauLines(14, size: 11)
                }
            } price: {
                Text(MacBureauMarketFormat.price(row.last, currency: row.currency))
                    .font(BSHType.bureauSans(12).monospacedDigit())
                    .tracking(-0.12)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .bureauLines(16, size: 12)
            } change: {
                if let signed = MacBureauMarketFormat.signed(row.change) {
                    Text(signed)
                        .font(BSHType.bureauSans(11, weight: .semibold).monospacedDigit())
                        .tracking(0.066)
                        .foregroundStyle((row.change ?? 0) >= 0 ? ink.successInk : ink.dangerInk)
                        .padding(.horizontal, 6)
                        .lineLimit(1)
                        .bureauLines(18, size: 11)
                        .background(RoundedRectangle(cornerRadius: 6, style: .circular).fill((row.change ?? 0) >= 0 ? ink.successSoft : ink.dangerSoft))
                        // An inline-block on the cell's 24pt line (16pt type): its baseline on the line's.
                        .padding(.top, 5)
                        .frame(height: 24, alignment: .top)
                } else {
                    Text("—").font(BSHType.bureauSans(11)).foregroundStyle(ink.subtle)
                }
            } extra: {
                Text(screener ? MacBureauMarketFormat.money(row.marketCap, compact: true) : MacBureauMarketFormat.compact(row.volume))
                    .font(BSHType.bureauSans(11).monospacedDigit())
                    .tracking(-0.11)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(14, size: 11)
            }
            .frame(height: 34)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(selected ? ink.accent.opacity(0.08) : (hovered ? ink.ink(0.03) : Color.clear))
            .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// `.yf-heat-cell`: the sector, its leader, the average move and the count on a wash from
/// danger to success.
private struct MacBureauMarketHeatCell: View {
    let sector: String
    let leader: String?
    let avg: Double
    let count: Int
    let ink: MacBureauPageInk
    let action: () -> Void

    private var wash: Color {
        let heat = min(1, max(-1, avg / 3))
        let t = (heat + 1) / 2
        let danger = ink.dark ? BSHRGB(232, 100, 82) : BSHRGB(192, 57, 43)
        let success = ink.dark ? BSHRGB(76, 180, 118) : BSHRGB(31, 128, 80)
        func mix(_ a: Double, _ b: Double) -> Double { a + (b - a) * t }
        return Color(.sRGB, red: mix(Double(danger.r), Double(success.r)) / 255, green: mix(Double(danger.g), Double(success.g)) / 255, blue: mix(Double(danger.b), Double(success.b)) / 255, opacity: 0.36)
    }

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 2.4) {
                Text(sector)
                    .font(BSHType.bureauSans(11, weight: .semibold))
                    .foregroundStyle(ink.secondary)
                    .multilineTextAlignment(.leading)
                    .bureauLines(16.5, size: 11)
                if let leader {
                    Text(leader)
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .bureauLines(14, size: 11)
                }
                Text(MacBureauMarketFormat.signed(avg) ?? "—")
                    .font(BSHType.bureauSans(16, weight: .semibold).monospacedDigit())
                    .foregroundStyle(avg >= 0 ? ink.success : ink.danger)
                    .lineLimit(1)
                    .bureauLines(24, size: 16)
                Text(verbatim: String(count))
                    .font(MacBureauMarketText.font(10.4))
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(15.6, size: 10.4)
            }
            .padding(.horizontal, 10.4)
            .padding(.vertical, 8.8)
            // A grid cell stretches to its row's tallest.
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(wash))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Aside: book risk, book lens, the Tape

struct MacBureauMarketAside: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let expanded: Bool
    let select: (String) -> Void

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var followed: [MacCompany] {
        let ids = Set(store.validFollowedIds)
        return store.companies.filter { ids.contains($0.id) }
    }

    var body: some View {
        if expanded {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    if !store.bookLots.isEmpty { bookRisk }
                    if !followed.isEmpty { bookLens }
                }
                MacBureauMarketTape(feed: feed, select: select, expanded: true)
            }
        } else {
            VStack(alignment: .leading, spacing: 16) {
                if !store.bookLots.isEmpty { bookRisk }
                if !followed.isEmpty { bookLens }
                MacBureauMarketTape(feed: feed, select: select, expanded: false)
            }
        }
    }

    private func price(_ ticker: String) -> Double? {
        feed.quote(ticker)?.lastPrice ?? store.watchlist.first { $0.ticker == ticker.uppercased() }?.last
    }

    /// bookBetaRisk + bookPnl: the book's beta, its SPY-equivalent, the move the day implies
    /// and each lot's day P&L.
    private var bookRisk: some View {
        let lots = store.bookLots
        let rows = lots.map { lot -> (ticker: String, shares: Double, value: Double?, day: Double?, unrealized: Double?, beta: Double?) in
            let last = price(lot.ticker)
            let quote = feed.quote(lot.ticker)
            let value = last.map { $0 * lot.shares }
            let day = value.flatMap { v in quote?.changePct.map { v * $0 / (100 + $0) } }
            return (lot.ticker, lot.shares, value, day, last.map { ($0 - lot.costBasis) * lot.shares }, quote?.beta)
        }
        let total = rows.compactMap(\.value).reduce(0, +)
        let betaWeighted = rows.reduce(0.0) { $0 + ($1.value ?? 0) * ($1.beta ?? 1) }
        let beta = total > 0 ? betaWeighted / total : nil
        let spyChange = feed.quote("SPY")?.changePct
        let expected = beta.flatMap { b in spyChange.map { b * $0 } }
        let dayTotal = rows.compactMap(\.day).reduce(0, +)
        let unrealized = rows.compactMap(\.unrealized).reduce(0, +)
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("Book risk")
            if let beta {
                Text("β \(String(format: "%.2f", beta))")
                    .font(MacBureauMarketText.font(12))
                    .foregroundStyle(ink.ink)
                    .padding(.top, 4)
                Text("SPY-eq \(MacBureauMarketFormat.money(total * beta, compact: true))")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.muted)
                if let expected {
                    Text("Expected move \(MacBureauMarketFormat.signed(expected) ?? "—")")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(expected >= 0 ? ink.success : ink.danger)
                }
            } else {
                Text("Follow names to see book risk.")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.muted)
                    .padding(.top, 4)
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    MacBureauMarketLabel("Book P&L")
                    Spacer()
                    Text(MacBureauMarketFormat.money(total, compact: true))
                        .font(BSHType.bureauSans(12).monospacedDigit())
                        .foregroundStyle(ink.ink)
                }
                (Text("Day \(MacBureauMarketFormat.money(dayTotal, compact: true))").foregroundColor(dayTotal >= 0 ? ink.success : ink.danger)
                    + Text(" · ").foregroundColor(ink.subtle)
                    + Text("Unrealized \(MacBureauMarketFormat.money(unrealized, compact: true))").foregroundColor(unrealized >= 0 ? ink.success : ink.danger))
                    .font(BSHType.bureauSans(11))
                ForEach(Array(rows.prefix(6).enumerated()), id: \.offset) { _, row in
                    Button { select(row.ticker) } label: {
                        HStack {
                            (Text(row.ticker).foregroundColor(ink.ink) + Text(" ×\(MacBureauMarketFormat.number(row.shares))").font(BSHType.bureauSans(11)).foregroundColor(ink.muted))
                                .font(BSHType.bureauSans(12, weight: .medium))
                            Spacer()
                            Text(row.day.map { MacBureauMarketFormat.money($0, compact: true) } ?? "—")
                                .font(BSHType.bureauSans(11).monospacedDigit())
                                .foregroundStyle((row.day ?? 0) >= 0 ? ink.success : ink.danger)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, 8)
            .overlay(alignment: .top) { Rectangle().fill(ink.rule).frame(height: 1) }
            .padding(.top, 12)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
    }

    /// bookConcentration: the followed names' average beta, sector mix and biggest movers.
    private var bookLens: some View {
        let tickers = followed.compactMap { $0.ticker?.uppercased() }
        let betas = tickers.compactMap { feed.quote($0)?.beta }
        let avgBeta = betas.isEmpty ? nil : betas.reduce(0, +) / Double(betas.count)
        var sectors: [String: Int] = [:]
        for company in followed { sectors[company.sector ?? "Other", default: 0] += 1 }
        let mix = sectors.sorted { $0.value > $1.value }.prefix(4)
        let movers = tickers.compactMap { t -> (String, Double)? in
            guard let change = feed.quote(t)?.changePct else { return nil }
            return (t, change)
        }
        .sorted { abs($0.1) > abs($1.1) }
        .prefix(4)
        return VStack(alignment: .leading, spacing: 0) {
            MacBureauMarketLabel("Book lens")
            if let avgBeta {
                Text("Avg beta \(String(format: "%.2f", avgBeta))")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .padding(.top, 4)
            }
            if !mix.isEmpty {
                HStack(spacing: 4) {
                    ForEach(Array(mix), id: \.key) { entry in
                        Text("\(entry.key) \(Int((Double(entry.value) / Double(max(followed.count, 1)) * 100).rounded()))%")
                    }
                }
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.muted)
                .padding(.top, 8)
            }
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(movers), id: \.0) { mover in
                    Button { select(mover.0) } label: {
                        HStack {
                            Text(mover.0).font(BSHType.bureauSans(12, weight: .medium)).foregroundStyle(ink.ink)
                            Spacer()
                            Text(MacBureauMarketFormat.signed(mover.1) ?? "—")
                                .font(BSHType.bureauSans(11).monospacedDigit())
                                .foregroundStyle(mover.1 >= 0 ? ink.success : ink.danger)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, 8)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
    }
}

// MARK: - The Tape

struct MacBureauMarketTape: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var feed: MacBureauMarketFeed
    let select: (String) -> Void
    let expanded: Bool
    @State private var scope = "all"

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private static let filingRE = "\\b(10-k|10-q|8-k|s-1|sec filing|earnings|13f)\\b"

    private func isFiling(_ item: MacNewsItem) -> Bool {
        let category = (item.category ?? "").lowercased()
        if ["filings", "filing", "sec", "earnings"].contains(category) { return true }
        return "\(item.title) \(item.summary ?? "")".lowercased().range(of: Self.filingRE, options: .regularExpression) != nil
    }

    /// rankDeskNews: the chosen symbol and its name first, filings and wires up, then the
    /// freshest; twelve after duplicates fold.
    private var headlines: [MacNewsItem] {
        let symbol = (store.selectedTicker ?? "").lowercased()
        let company = store.companies.first { $0.ticker?.lowercased() == symbol }
        let label = (company?.name ?? "").lowercased()
        let book = Set(store.companies.filter { Set(store.validFollowedIds).contains($0.id) }.compactMap { $0.ticker?.uppercased() })
        let now = Date()
        let scored = store.news.map { item -> (MacNewsItem, Double) in
            var score = 0.0
            let hay = "\(item.title) \(item.summary ?? "")".lowercased()
            if let t = item.ticker?.uppercased(), book.contains(t) { score += 40 }
            if !symbol.isEmpty, hay.contains(symbol) { score += 30 }
            if label.count > 3, hay.contains(label) { score += 18 }
            if isFiling(item) { score += 22 }
            if (item.source ?? "").lowercased().range(of: "reuters|bloomberg|wsj|ft|sec\\.gov|edgar", options: .regularExpression) != nil { score += 10 }
            if let stamp = MacBureauMarketFormat.parse(item.publishedAt) {
                score += max(0, 24 - max(0, now.timeIntervalSince(stamp) / 3600))
            }
            return (item, score)
        }
        .sorted { $0.1 != $1.1 ? $0.1 > $1.1 : ($0.0.publishedAt ?? "") > ($1.0.publishedAt ?? "") }
        var seen = Set<String>()
        var rows: [MacNewsItem] = []
        for (item, _) in scored {
            let key = String(item.title.lowercased().filter { $0.isLetter || $0.isNumber || $0 == " " }.prefix(48))
            guard !key.isEmpty, seen.insert(key).inserted else { continue }
            switch scope {
            case "filings": if !isFiling(item) { continue }
            case "book": if !(item.ticker.map { book.contains($0.uppercased()) } ?? false) { continue }
            default: break
            }
            rows.append(item)
            if rows.count >= 12 { break }
        }
        return rows
    }

    var body: some View {
        let rows = headlines
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauMarketLabel("Tape")
                Spacer(minLength: 0)
                MacBureauMarketTapeLinks(select: select)
            }
            .frame(height: 16)
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 4)

            VStack(alignment: .leading, spacing: 0) {
                Text(MacBureauMarketPulse.posture(store.marketPulsePayload))
                    .font(BSHType.bureauSans(15, weight: .semibold))
                    .tracking(-0.15)
                    .foregroundStyle(ink.ink)
                    .lineLimit(1)
                    .bureauLines(20, size: 15)
                Text(MacBureauMarketPulse.breadth(store.marketPulsePayload))
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .bureauLines(16, size: 12)
                    .padding(.top, 4)
                if let top = store.marketPulsePayload?.summary?.topSignal, !top.isEmpty {
                    Text(top)
                        .font(BSHType.bureauSans(14))
                        .foregroundStyle(ink.ink)
                        .bureauLines(20, size: 14)
                        .padding(.top, 8)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            Rectangle().fill(ink.rule).frame(height: 1)

            HStack(spacing: 4) {
                MacBureauMarketRangeItem("All", selected: scope == "all") { scope = "all" }
                MacBureauMarketRangeItem("Book", selected: scope == "book") { scope = "book" }
                MacBureauMarketRangeItem("Filings", selected: scope == "filings") { scope = "filings" }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            if rows.isEmpty {
                Text("Nothing new right now.")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.muted)
                    .lineLimit(1)
                    .bureauLines(20, size: 14)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 20)
            } else if expanded {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 0), GridItem(.flexible(), spacing: 0)], spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.element.id) { index, item in
                        MacBureauMarketStoryRow(item: item, first: index < 2, filing: isFiling(item), ink: ink)
                    }
                }
            } else {
                ForEach(Array(rows.enumerated()), id: \.element.id) { index, item in
                    MacBureauMarketStoryRow(item: item, first: index == 0, filing: isFiling(item), ink: ink)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauMarketTray()
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .circular))
    }
}

/// The Tape's brass links: Ask Warren, Why is this moving?, News.
private struct MacBureauMarketTapeLinks: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    let select: (String) -> Void

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        let ticker = store.selectedTicker ?? "SPY"
        let company = store.companies.first { $0.ticker?.uppercased() == ticker }
        HStack(spacing: 8) {
            MacBureauMarketLink(title: "Ask Warren", ink: ink) {
                store.setCopilotContext(.market(ticker: ticker), company: company)
                store.showCopilotPanel = true
            }
            MacBureauMarketLink(title: "Why is this moving?", ink: ink) {
                let headlines = store.news
                    .filter { "\($0.title) \($0.summary ?? "")".uppercased().contains(ticker) || $0.ticker?.uppercased() == ticker }
                    .prefix(4)
                    .map { "- \($0.title)" }
                let prompt = "Why is \(ticker) moving?\n\nRecent headlines:\n" + (headlines.isEmpty ? "(no matched headlines in the workspace feed)" : headlines.joined(separator: "\n"))
                store.askWarren(prompt, context: .market(ticker: ticker), company: company)
            }
            .disabled(!store.canRunTasks)
            MacBureauMarketLink(title: "News", ink: ink) {
                store.selectedTab = .news
            }
        }
    }
}

/// `.news-story-row`: the newspaper glyph, the headline in headline type and its age.
private struct MacBureauMarketStoryRow: View {
    let item: MacNewsItem
    let first: Bool
    let filing: Bool
    let ink: MacBureauPageInk
    @EnvironmentObject private var store: MacAppStore
    @State private var hovered = false

    var body: some View {
        Button {
            store.newsFocusId = item.id
            store.selectedTab = .news
        } label: {
            HStack(alignment: .center, spacing: 12) {
                LucideIcon("newspaper", size: 16)
                    .foregroundStyle(ink.muted)
                    .padding(.top, 2)
                VStack(alignment: .leading, spacing: 0) {
                    Text(item.title)
                        .font(BSHType.bureauSans(15, weight: .semibold))
                        .tracking(-0.15)
                        .foregroundStyle(ink.ink)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .bureauLines(20, size: 15)
                    Text((filing ? "Filings · " : "") + MacBureauMarketFormat.age(item.publishedAt))
                        .font(BSHType.bureauSans(11))
                        .tracking(0.066)
                        .foregroundStyle(ink.muted)
                        .lineLimit(1)
                        .bureauLines(14, size: 11)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(hovered ? ink.ink(0.03) : Color.clear)
            .overlay(alignment: .top) {
                if !first { Rectangle().fill(ink.rule).frame(height: 1) }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}
