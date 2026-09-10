import SwiftUI

@MainActor
final class NewsViewModel: ObservableObject {
    @Published var items: [NewsItem] = []
    @Published var query = ""
    @Published var scope: Scope = .all
    @Published var loading = false
    @Published var error: String?

    enum Scope: String, CaseIterable, Identifiable {
        case all, market, company
        var id: String { rawValue }
    }

    var filtered: [NewsItem] {
        var rows = items
        switch scope {
        case .all: break
        case .market:
            rows = rows.filter { $0.kind != "company_news" }
        case .company:
            rows = rows.filter { $0.kind == "company_news" }
        }
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return rows }
        return rows.filter {
            "\($0.title) \($0.summary ?? "") \($0.source ?? "") \($0.ticker ?? "") \($0.companyName ?? "")"
                .lowercased()
                .contains(q)
        }
    }

    func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let feedTask: [ExternalFeedDTO] = APIClient.shared.get("external/feed")
            async let companiesTask: CompaniesResponse = APIClient.shared.get("companies")
            let (feed, companiesRes) = try await (feedTask, companiesTask)
            let companies = companiesRes.companies ?? []
            items = NewsAssembler.merge(
                feed: NewsAssembler.fromExternalFeed(feed),
                companyNews: NewsAssembler.fromCompanies(companies),
                limit: 100
            )
        } catch {
            // Soft-fallback: company news alone still fills the tape.
            do {
                let companiesRes: CompaniesResponse = try await APIClient.shared.get("companies")
                items = NewsAssembler.fromCompanies(companiesRes.companies ?? [])
                if items.isEmpty {
                    self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                }
            } catch {
                self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}

struct NewsView: View {
    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model = NewsViewModel()

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker(language.t("news.scope"), selection: $model.scope) {
                        Text(language.t("news.scope_all")).tag(NewsViewModel.Scope.all)
                        Text(language.t("news.scope_market")).tag(NewsViewModel.Scope.market)
                        Text(language.t("news.scope_company")).tag(NewsViewModel.Scope.company)
                    }
                    .pickerStyle(.segmented)
                }

                if model.loading && model.items.isEmpty {
                    ProgressView(language.t("common.loading"))
                        .frame(maxWidth: .infinity, alignment: .center)
                        .listRowSeparator(.hidden)
                } else if let err = model.error, model.filtered.isEmpty {
                    ContentUnavailableView {
                        Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
                    } description: {
                        Text(err)
                    } actions: {
                        Button(language.t("common.retry")) { Task { await model.load() } }
                    }
                    .listRowSeparator(.hidden)
                } else if model.filtered.isEmpty {
                    ContentUnavailableView(language.t("news.empty"), systemImage: "newspaper")
                        .listRowSeparator(.hidden)
                } else {
                    ForEach(model.filtered) { item in
                        NavigationLink(value: item) {
                            NewsRowView(item: item)
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .compactRootChrome(
                title: language.t("tab.news"),
                searchText: $model.query,
                searchPrompt: language.t("news.search")
            )
            .navigationDestination(for: NewsItem.self) { item in
                NewsDetailView(item: item)
            }
            .refreshable { await model.load() }
            .task { await model.load() }
        }
    }
}

struct NewsDetailView: View {
    let item: NewsItem
    @EnvironmentObject private var language: LanguageStore

    var body: some View {
        List {
            Section {
                Text(item.title)
                    .font(.title3.weight(.semibold))
                HStack {
                    if let ticker = item.ticker {
                        Text(ticker).font(.caption.monospaced().weight(.semibold))
                    }
                    if let source = item.source {
                        Text(source).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(item.whenLabel).font(.caption2).foregroundStyle(.secondary)
                }
            }

            if let summary = item.summary, !summary.isEmpty {
                Section(language.t("news.summary")) {
                    Text(summary)
                }
            }

            if let category = item.category {
                Section {
                    LabeledContent(language.t("news.category"), value: category)
                }
            }

            if let urlString = item.url, let url = URL(string: urlString) {
                Section {
                    Link(language.t("news.open_source"), destination: url)
                }
            }

            if let ticker = item.ticker, !ticker.isEmpty {
                Section {
                    NavigationLink {
                        QuoteDetailView(ticker: ticker)
                    } label: {
                        Label(
                            language.t("market.open_ticker").replacingOccurrences(of: "{t}", with: ticker),
                            systemImage: "chart.xyaxis.line"
                        )
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(language.t("tab.news"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                ShareLink(item: shareText) {
                    Image(systemName: "square.and.arrow.up")
                }
            }
        }
    }

    private var shareText: String {
        var parts = [item.title]
        if let url = item.url, !url.isEmpty { parts.append(url) }
        return parts.joined(separator: "\n")
    }
}
