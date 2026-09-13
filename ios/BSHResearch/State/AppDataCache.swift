import Foundation
import SwiftUI
import Combine

/// Disk-backed cache for raw API JSON payloads, keyed by request path and sorted query.
final class APIResponseCache: @unchecked Sendable {
    static let shared = APIResponseCache()

    private let cacheDir: URL
    private let fileManager = FileManager.default
    private let queue = DispatchQueue(label: "com.bsh.apiresponsecache", qos: .utility)

    init() {
        let base = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())
        cacheDir = base.appendingPathComponent("BSHDataCache", isDirectory: true)
        try? fileManager.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    static func cacheKey(path: String, query: [URLQueryItem] = []) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let sorted = query.sorted { $0.name < $1.name }
            .map { "\($0.name)=\($0.value ?? "")" }
            .joined(separator: "&")
        if sorted.isEmpty { return trimmed }
        return "\(trimmed)?\(sorted)"
    }

    private func fileURL(for key: String) -> URL {
        let safeKey = key
            .replacingOccurrences(of: "/", with: "__")
            .replacingOccurrences(of: "?", with: "_Q_")
            .replacingOccurrences(of: "&", with: "_A_")
            .replacingOccurrences(of: "=", with: "_E_")
            .replacingOccurrences(of: ":", with: "_C_")
        return cacheDir.appendingPathComponent("\(safeKey).json")
    }

    func save(data: Data, for key: String) {
        queue.async { [weak self] in
            guard let self else { return }
            let url = self.fileURL(for: key)
            try? data.write(to: url, options: .atomic)
        }
    }

    func load(for key: String) -> Data? {
        let url = fileURL(for: key)
        return try? Data(contentsOf: url)
    }

    func remove(for key: String) {
        queue.async { [weak self] in
            guard let self else { return }
            let url = self.fileURL(for: key)
            try? self.fileManager.removeItem(at: url)
        }
    }

    func clearAll() {
        queue.async { [weak self] in
            guard let self else { return }
            try? self.fileManager.removeItem(at: self.cacheDir)
            try? self.fileManager.createDirectory(at: self.cacheDir, withIntermediateDirectories: true)
        }
    }
}

/// Central in-memory and disk preloader for all company dossiers, reports, quotes, and news.
@MainActor
final class AppDataCache: ObservableObject {
    static let shared = AppDataCache()

    // MARK: - Published State
    @Published private(set) var companies: [Company] = []
    @Published private(set) var companyDetails: [String: CompanyDetail] = [:]
    @Published private(set) var companyReports: [String: [ReportSummary]] = [:]
    @Published private(set) var quotes: [String: Quote] = [:]
    @Published private(set) var newsItems: [NewsItem] = []
    @Published private(set) var briefs: [String: NewsBrief] = [:]

    @Published private(set) var isPreloading = false
    @Published private(set) var preloadProgress: Double = 0.0
    @Published private(set) var lastPreloadDate: Date?

    init() {
        restoreFromDisk()
    }

    // MARK: - Cold-Start Disk Restoration

    /// Immediately restores whatever is cached on disk into memory synchronously on launch (0ms).
    func restoreFromDisk() {
        let decoder = JSONDecoder()

        // 1. Companies
        if let data = APIResponseCache.shared.load(for: "companies") {
            if let resp = try? decoder.decode(CompaniesResponse.self, from: data), let list = resp.companies {
                self.companies = list
                for comp in list {
                    restoreCompanyDiskCache(id: comp.id, decoder: decoder)
                }
            }
        }

        // 2. Quotes
        let cachedQuotes = QuoteCache.load()
        if !cachedQuotes.isEmpty {
            self.quotes = cachedQuotes.compactMapValues { $0.asQuote }
        }

        // 3. News
        let feedData = APIResponseCache.shared.load(for: "external/feed")
        let liveData = APIResponseCache.shared.load(for: APIResponseCache.cacheKey(path: "quotes/news", query: [URLQueryItem(name: "limit", value: "50")]))
            ?? APIResponseCache.shared.load(for: APIResponseCache.cacheKey(path: "quotes/news", query: [URLQueryItem(name: "limit", value: "40")]))
            ?? APIResponseCache.shared.load(for: APIResponseCache.cacheKey(path: "quotes/news", query: [URLQueryItem(name: "limit", value: "100")]))

        let feedDTOs = feedData.flatMap { try? decoder.decode([ExternalFeedDTO].self, from: $0) } ?? []
        let liveDTOs = liveData.flatMap { try? decoder.decode(LiveNewsResponse.self, from: $0) }?.items ?? []

        let assembled = NewsAssembler.merge(
            live: NewsAssembler.fromLive(liveDTOs),
            feed: NewsAssembler.fromExternalFeed(feedDTOs),
            companyNews: NewsAssembler.fromCompanies(companies),
            limit: 100
        )
        if !assembled.isEmpty {
            self.newsItems = assembled
        }
    }

    private func restoreCompanyDiskCache(id: String, decoder: JSONDecoder) {
        if let detailData = APIResponseCache.shared.load(for: "companies/\(id)"),
           let detail = try? decoder.decode(CompanyDetail.self, from: detailData) {
            self.companyDetails[id] = detail
        }
        if let reportsData = APIResponseCache.shared.load(for: "companies/\(id)/reports"),
           let reports = try? decoder.decode([ReportSummary].self, from: reportsData) {
            self.companyReports[id] = reports
        }
    }

    // MARK: - Preload Everything

    /// Concurrent eager preloader: downloads and caches all 28 company dossiers, reports, quotes,
    /// full news feeds, and kicks off server prewarming for news briefs.
    func preloadAll(lang: AppLanguage = .en, force: Bool = false) async {
        guard !isPreloading || force else { return }
        isPreloading = true
        preloadProgress = 0.05
        defer { isPreloading = false }

        // Stage 1: Load companies catalog & feeds in parallel
        async let companiesReq: CompaniesResponse? = {
            try? await APIClient.shared.get("companies")
        }()
        async let feedReq: [ExternalFeedDTO]? = {
            try? await APIClient.shared.get("external/feed")
        }()
        async let liveNewsReq: LiveNewsResponse? = {
            try? await APIClient.shared.get("quotes/news", query: [URLQueryItem(name: "limit", value: "50")])
        }()

        let (compRes, feedRes, liveRes) = await (companiesReq, feedReq, liveNewsReq)

        if let compList = compRes?.companies, !compList.isEmpty {
            self.companies = compList
        }

        let feedDTOs = feedRes ?? []
        let liveDTOs = liveRes?.items ?? []
        let initialNews = NewsAssembler.merge(
            live: NewsAssembler.fromLive(liveDTOs),
            feed: NewsAssembler.fromExternalFeed(feedDTOs),
            companyNews: NewsAssembler.fromCompanies(companies),
            limit: 100
        )
        if !initialNews.isEmpty {
            self.newsItems = initialNews
        }

        preloadProgress = 0.25

        // Stage 2: Concurrently fetch full company dossiers and reports for all companies
        let compList = self.companies
        let totalItems = max(compList.count, 1)
        var completedCount = 0

        await withTaskGroup(of: (String, CompanyDetail?, [ReportSummary]?).self) { group in
            for comp in compList {
                group.addTask {
                    async let detailReq: CompanyDetail? = {
                        try? await APIClient.shared.get("companies/\(comp.id)")
                    }()
                    async let reportsReq: [ReportSummary]? = {
                        try? await APIClient.shared.get("companies/\(comp.id)/reports")
                    }()
                    let (d, r) = await (detailReq, reportsReq)
                    return (comp.id, d, r)
                }
            }

            for await (id, detail, reports) in group {
                if let detail {
                    self.companyDetails[id] = detail
                }
                if let reports {
                    self.companyReports[id] = reports
                }
                completedCount += 1
                self.preloadProgress = 0.25 + (0.50 * Double(completedCount) / Double(totalItems))
            }
        }

        // Stage 3: Merge any new news items parsed from company dossiers
        let refreshedNews = NewsAssembler.merge(
            live: NewsAssembler.fromLive(liveDTOs),
            feed: NewsAssembler.fromExternalFeed(feedDTOs),
            companyNews: NewsAssembler.fromCompanies(companies),
            limit: 100
        )
        if !refreshedNews.isEmpty {
            self.newsItems = refreshedNews
        }

        preloadProgress = 0.80

        // Stage 4: Batch fetch quotes for all public company tickers
        let publicTickers = Array(
            Set(
                self.companies
                    .compactMap { $0.ticker?.uppercased() }
                    .filter { !$0.isEmpty }
            )
        )
        if !publicTickers.isEmpty {
            let quotesRes: QuotesResponse? = try? await APIClient.shared.get(
                "quotes",
                query: publicTickers.map { URLQueryItem(name: "ticker", value: $0) }
            )
            if let quotesDict = quotesRes?.quotes {
                for (t, q) in quotesDict {
                    self.quotes[t.uppercased()] = q
                }
                QuoteCache.save(Array(quotesDict.values))
            }
        }

        preloadProgress = 0.90

        // Stage 5: Eagerly prewarm news briefings in background
        prewarmNewsBriefs(lang: lang)

        preloadProgress = 1.0
        lastPreloadDate = Date()
    }

    // MARK: - News Brief Prewarming

    private func prewarmNewsBriefs(lang: AppLanguage) {
        let topHeadlines = Array(newsItems.prefix(5))
        for item in topHeadlines {
            let key = "\(item.title.lowercased())_\(lang.rawValue)"
            if briefs[key] != nil { continue }

            Task(priority: .utility) {
                var query = [
                    URLQueryItem(name: "title", value: item.title),
                    URLQueryItem(name: "lang", value: lang.rawValue)
                ]
                if let company = item.companyName {
                    query.append(URLQueryItem(name: "company", value: company))
                }
                if let brief: NewsBrief = try? await APIClient.shared.get("news/brief", query: query) {
                    await MainActor.run {
                        self.briefs[key] = brief
                    }
                }
            }
        }
    }

    // MARK: - Cache Accessors

    func cachedCompany(id: String) -> CompanyDetail? {
        companyDetails[id]
    }

    func cachedReports(for companyId: String) -> [ReportSummary]? {
        companyReports[companyId]
    }

    func cachedQuote(for ticker: String) -> Quote? {
        quotes[ticker.uppercased()]
    }

    func cachedBrief(title: String, lang: AppLanguage) -> NewsBrief? {
        briefs["\(title.lowercased())_\(lang.rawValue)"]
    }

    func update(company: CompanyDetail) {
        companyDetails[company.id] = company
    }

    func update(reports: [ReportSummary], for companyId: String) {
        companyReports[companyId] = reports
    }

    func update(news: [NewsItem]) {
        self.newsItems = news
    }
}

private struct Plan: Decodable {
    let queued: Int?
    let started: Bool?
    let workers: Int?
    let parallel: Bool?
}
