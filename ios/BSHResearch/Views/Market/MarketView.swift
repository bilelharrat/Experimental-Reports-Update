import SwiftUI

@MainActor
final class MarketViewModel: ObservableObject {
    @Published var quotes: [Quote] = []
    @Published var gainers: [ScreenerRow] = []
    @Published var losers: [ScreenerRow] = []
    @Published var actives: [ScreenerRow] = []
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
            let (indexRes, screeners) = try await (indexTask, screenerTask)
            quotes = indexes.compactMap { ticker in
                indexRes.quotes[ticker]
            }
            gainers = Array((screeners.gainers ?? []).prefix(12))
            losers = Array((screeners.losers ?? []).prefix(12))
            actives = Array((screeners.active ?? []).prefix(12))
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
    @StateObject private var model = MarketViewModel()

    var body: some View {
        NavigationStack {
            List {
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
                            NavigationLink(value: model.searchTicker) {
                                Label(
                                    language.t("market.open_ticker").replacingOccurrences(of: "{t}", with: model.searchTicker),
                                    systemImage: "magnifyingglass"
                                )
                            }
                        }
                    }

                    Section(language.t("market.indexes")) {
                        ForEach(model.quotes) { quote in
                            NavigationLink(value: quote.ticker) {
                                QuoteRow(quote: quote)
                            }
                        }
                    }

                    if !model.gainers.isEmpty {
                        Section(language.t("pulse.gainers")) {
                            ForEach(model.gainers) { row in
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }

                    if !model.losers.isEmpty {
                        Section(language.t("pulse.losers")) {
                            ForEach(model.losers) { row in
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }

                    if !model.actives.isEmpty {
                        Section(language.t("market.actives")) {
                            ForEach(model.actives) { row in
                                NavigationLink(value: row.ticker) {
                                    ScreenerRowView(row: row)
                                }
                            }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .compactRootChrome(
                title: language.t("market.title"),
                searchText: $model.query,
                searchPrompt: language.t("market.search_ticker")
            ) {
                Button(language.t("market.refresh")) { Task { await model.load() } }
                    .font(.subheadline.weight(.semibold))
            }
            .refreshable { await model.load() }
            .navigationDestination(for: String.self) { ticker in
                QuoteDetailView(ticker: ticker)
            }
            .task { await model.load() }
        }
    }
}

struct ScreenerRowView: View {
    let row: ScreenerRow

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.ticker).font(.headline.monospaced())
                if let name = row.name {
                    Text(name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(QuoteRow.price(row.last, currency: "USD"))
                    .font(.body.monospacedDigit())
                Text(QuoteRow.pct(row.change))
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(QuoteRow.tone(row.change))
            }
        }
        .padding(.vertical, 2)
    }
}

struct QuoteRow: View {
    let quote: Quote

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(quote.ticker).font(.headline.monospaced())
                if let name = quote.name {
                    Text(name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(Self.price(quote.lastPrice, currency: quote.currency))
                    .font(.body.monospacedDigit())
                Text(Self.pct(quote.changePct1d))
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(Self.tone(quote.changePct1d))
            }
        }
        .padding(.vertical, 2)
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
