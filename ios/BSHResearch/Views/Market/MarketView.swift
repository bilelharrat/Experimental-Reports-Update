import SwiftUI

@MainActor
final class MarketViewModel: ObservableObject {
    @Published var quotes: [Quote] = []
    @Published var gainers: [ScreenerRow] = []
    @Published var losers: [ScreenerRow] = []
    @Published var actives: [ScreenerRow] = []
    @Published var calendarEvents: [MarketCalendarEvent] = []
    @Published var query = ""
    @Published var loading = false
    @Published var error: String?

    private let indexes = ["SPY", "QQQ", "DIA", "IWM", "GLD", "USO", "TLT", "VIXY", "UUP"]

    var searchTicker: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let indexTask: QuotesResponse = APIClient.shared.get(
                "quotes",
                query: indexes.map { URLQueryItem(name: "ticker", value: $0) }
            )
            async let screenerTask: ScreenersResponse = APIClient.shared.get("quotes/screeners")
            async let calendarTask: MarketCalendarResponse = APIClient.shared.get("quotes/calendar")
            let (indexRes, screeners, calendar) = try await (indexTask, screenerTask, calendarTask)
            quotes = indexes.compactMap { ticker in
                indexRes.quotes[ticker]
            }
            gainers = Array((screeners.gainers ?? []).prefix(12))
            losers = Array((screeners.losers ?? []).prefix(12))
            actives = Array((screeners.active ?? []).prefix(12))
            calendarEvents = Array((calendar.events ?? []).prefix(20))
        } catch {
            // Indexes alone still useful if screeners fail.
            do {
                let indexRes: QuotesResponse = try await APIClient.shared.get(
                    "quotes",
                    query: indexes.map { URLQueryItem(name: "ticker", value: $0) }
                )
                quotes = indexes.compactMap { indexRes.quotes[$0] }
            } catch {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}

struct ScreenerRow: Decodable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let name: String?
    let last: Double?
    let change: Double?
    let volume: Double?

    enum CodingKeys: String, CodingKey {
        case ticker, name, last, change, volume
        case lastPrice = "last_price"
        case changePct = "change_pct"
        case changePct1d = "change_pct_1d"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        ticker = try box.decode(String.self, forKey: .ticker)
        name = try box.decodeIfPresent(String.self, forKey: .name)
        last = try box.decodeIfPresent(Double.self, forKey: .last)
            ?? box.decodeIfPresent(Double.self, forKey: .lastPrice)
        change = try box.decodeIfPresent(Double.self, forKey: .changePct)
            ?? box.decodeIfPresent(Double.self, forKey: .changePct1d)
            ?? box.decodeIfPresent(Double.self, forKey: .change)
        volume = try box.decodeIfPresent(Double.self, forKey: .volume)
    }
}

struct ScreenersResponse: Decodable {
    let gainers: [ScreenerRow]?
    let losers: [ScreenerRow]?
    let active: [ScreenerRow]?
}

struct MarketView: View {
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.embeddedInRootSplit) private var embeddedInRootSplit
    @StateObject private var model = MarketViewModel()
    @State private var selectedTicker: String?

    /// Dual-pane only inside landscape root sidebar detail. Portrait iPad must
    /// match iPhone: push navigation inside the bottom TabView — no split chrome.
    private var usesDualPane: Bool {
        embeddedInRootSplit
    }

    var body: some View {
        Group {
            if usesDualPane {
                embeddedDualPane
            } else {
                compactStack
            }
        }
        .task { await model.load() }
        .onChange(of: model.quotes.map(\.ticker)) { _, _ in
            syncSelectionIfNeeded()
        }
        .onChange(of: model.searchTicker) { _, ticker in
            guard usesDualPane, !ticker.isEmpty, ticker.count <= 10 else { return }
            selectedTicker = ticker
        }
    }

    private var compactStack: some View {
        NavigationStack {
            marketList(selectionMode: false)
                .navigationDestination(for: String.self) { ticker in
                    QuoteDetailView(ticker: ticker)
                }
        }
    }

    private var embeddedDualPane: some View {
        NavigationStack {
            HStack(spacing: 0) {
                marketList(selectionMode: true)
                    .frame(
                        minWidth: AdaptiveLayout.embeddedMasterMin,
                        idealWidth: AdaptiveLayout.embeddedMasterIdeal,
                        maxWidth: AdaptiveLayout.embeddedMasterIdeal
                    )
                Divider()
                marketDetailPane
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    @ViewBuilder
    private var marketDetailPane: some View {
        if let ticker = selectedTicker {
            QuoteDetailView(ticker: ticker)
                .id(ticker)
        } else {
            ContentUnavailableView(
                language.t("market.empty"),
                systemImage: "chart.line.uptrend.xyaxis",
                description: Text(language.t("market.search_ticker"))
            )
        }
    }

    @ViewBuilder
    private func marketList(selectionMode: Bool) -> some View {
        List(selection: selectionMode ? $selectedTicker : .constant(nil)) {
            if model.loading && model.quotes.isEmpty {
                ProgressView(language.t("common.loading"))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else if let err = model.error, model.quotes.isEmpty {
                ContentUnavailableView {
                    Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
                } description: {
                    Text(err)
                } actions: {
                    Button(language.t("common.retry")) { Task { await model.load() } }
                }
                .listRowSeparator(.hidden)
            } else {
                if !model.searchTicker.isEmpty, model.searchTicker.count <= 10 {
                    Section {
                        if selectionMode {
                            Label(
                                language.t("market.open_ticker").replacingOccurrences(of: "{t}", with: model.searchTicker),
                                systemImage: "magnifyingglass"
                            )
                            .tag(model.searchTicker)
                        } else {
                            NavigationLink(value: model.searchTicker) {
                                Label(
                                    language.t("market.open_ticker").replacingOccurrences(of: "{t}", with: model.searchTicker),
                                    systemImage: "magnifyingglass"
                                )
                            }
                        }
                    }
                }

                Section(language.t("market.indexes")) {
                    ForEach(model.quotes) { quote in
                        if selectionMode {
                            QuoteRow(quote: quote)
                                .tag(quote.ticker)
                        } else {
                            NavigationLink(value: quote.ticker) {
                                QuoteRow(quote: quote)
                            }
                        }
                    }
                }

                if !model.calendarEvents.isEmpty {
                    Section(language.t("market.calendar")) {
                        ForEach(model.calendarEvents.prefix(12)) { event in
                            if let ticker = event.ticker, !ticker.isEmpty {
                                if selectionMode {
                                    calendarRow(event)
                                        .tag(ticker)
                                } else {
                                    NavigationLink(value: ticker) {
                                        calendarRow(event)
                                    }
                                }
                            } else {
                                calendarRow(event)
                            }
                        }
                    }
                }

                if !model.gainers.isEmpty {
                    Section(language.t("pulse.gainers")) {
                        ForEach(model.gainers) { row in
                            if selectionMode {
                                ScreenerRowView(row: row)
                                    .tag(row.ticker)
                            } else {
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }
                }

                if !model.losers.isEmpty {
                    Section(language.t("pulse.losers")) {
                        ForEach(model.losers) { row in
                            if selectionMode {
                                ScreenerRowView(row: row)
                                    .tag(row.ticker)
                            } else {
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }
                }

                if !model.actives.isEmpty {
                    Section(language.t("market.actives")) {
                        ForEach(model.actives) { row in
                            if selectionMode {
                                ScreenerRowView(row: row)
                                    .tag(row.ticker)
                            } else {
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .headerProminence(.increased)
        .compactRootChrome(
            title: language.t("market.title"),
            searchText: $model.query,
            searchPrompt: language.t("market.search_ticker")
        ) {
            Button {
                Task { await model.load() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.body.weight(.semibold))
            }
        }
        .refreshable { await model.load() }
    }

    private func syncSelectionIfNeeded() {
        guard usesDualPane else { return }
        if let selectedTicker,
           model.quotes.contains(where: { $0.ticker == selectedTicker })
            || model.gainers.contains(where: { $0.ticker == selectedTicker })
            || model.losers.contains(where: { $0.ticker == selectedTicker })
            || model.actives.contains(where: { $0.ticker == selectedTicker }) {
            return
        }
        selectedTicker = model.quotes.first?.ticker
    }

    private func calendarRow(_ event: MarketCalendarEvent) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(event.ticker ?? event.kind ?? "Event")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                if let date = event.date {
                    Text(String(date.prefix(10)))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            Text(event.label ?? event.title ?? event.kind ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
    }
}

struct ScreenerRowView: View {
    let row: ScreenerRow

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.ticker).font(.headline)
                if let name = row.name {
                    Text(name).font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            SparklineView(ticker: row.ticker)
            VStack(alignment: .trailing, spacing: 4) {
                Text(QuoteRow.price(row.last, currency: "USD"))
                    .font(.body.monospacedDigit().weight(.semibold))
                ChangeBadge(value: row.change)
            }
        }
        .padding(.vertical, 3)
    }
}

struct QuoteRow: View {
    let quote: Quote

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(quote.ticker).font(.headline)
                if let name = quote.name {
                    Text(name).font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            SparklineView(ticker: quote.ticker)
            VStack(alignment: .trailing, spacing: 4) {
                Text(Self.price(quote.lastPrice, currency: quote.currency))
                    .font(.body.monospacedDigit().weight(.semibold))
                ChangeBadge(value: quote.changePct1d)
            }
        }
        .padding(.vertical, 3)
    }

    static func price(_ value: Double?, currency: String?) -> String {
        guard let value else { return "—" }
        let symbol = (currency == nil || currency == "USD") ? "$" : "\(currency!) "
        return "\(symbol)\(String(format: "%.2f", value))"
    }

    static func pct(_ value: Double?) -> String {
        guard let value else { return "—" }
        // Round half away from zero (printf's %.1f is half-even: 1.25 → 1.2).
        let rounded = (value * 10).rounded() / 10
        return String(format: "%+.1f%%", rounded)
    }

    static func tone(_ value: Double?) -> Color {
        guard let value else { return .secondary }
        if value > 0 { return .green }
        if value < 0 { return .red }
        return .secondary
    }
}
