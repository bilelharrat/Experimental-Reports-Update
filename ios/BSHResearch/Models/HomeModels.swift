import Foundation

struct MarketPulsePayload: Decodable {
    let generatedAt: String?
    let status: String?
    let summary: MarketPulseSummary?
    let sections: MarketPulseSections?

    enum CodingKeys: String, CodingKey {
        case status, summary, sections
        case generatedAt = "generated_at"
    }
}

struct MarketPulseSummary: Decodable {
    let periodId: String?
    let signalCount: Int?
    let topSignal: String?

    enum CodingKeys: String, CodingKey {
        case periodId = "period_id"
        case signalCount = "signal_count"
        case topSignal = "top_signal"
    }
}

struct MarketPulseSections: Decodable {
    let marketRegime: MarketRegime?
    let rankedSignals: [RankedSignal]?

    enum CodingKeys: String, CodingKey {
        case marketRegime = "market_regime"
        case rankedSignals = "ranked_signals"
    }
}

struct MarketRegime: Decodable {
    let posture: String?
    let breadth: MarketBreadth?
}

struct MarketBreadth: Decodable {
    let positiveSignals: Int?
    let negativeSignals: Int?
    let neutralSignals: Int?

    enum CodingKeys: String, CodingKey {
        case positiveSignals = "positive_signals"
        case negativeSignals = "negative_signals"
        case neutralSignals = "neutral_signals"
    }
}

struct RankedSignal: Decodable, Identifiable {
    var id: String { signalId ?? signal ?? UUID().uuidString }
    let signalId: String?
    let signal: String?
    let direction: String?
    let relatedTickers: [String]?
    let relatedThemes: [String]?
    let trackerId: String?

    enum CodingKeys: String, CodingKey {
        case signal, direction
        case signalId = "signal_id"
        case relatedTickers = "related_tickers"
        case relatedThemes = "related_themes"
        case trackerId = "tracker_id"
    }

    var badge: String {
        relatedTickers?.first ?? relatedThemes?.first ?? direction ?? trackerId ?? ""
    }
}

struct NewsItem: Identifiable, Hashable {
    let id: String
    let title: String
    let summary: String?
    let source: String?
    let url: String?
    let capturedAt: String?
    let category: String?
    let kind: String
    let companyName: String?
    let ticker: String?

    var whenLabel: String {
        guard let raw = capturedAt, !raw.isEmpty else { return "" }
        if let date = ISO8601DateFormatter().date(from: raw)
            ?? ISO8601DateFormatter.fractional.date(from: raw) {
            return Self.label(for: date)
        }
        // Plain calendar dates ("2026-04-20") are common in stored news.
        if let date = DateFormatter.plainDay.date(from: String(raw.prefix(10))) {
            return Self.label(for: date)
        }
        return String(raw.prefix(10))
    }

    /// Recent items read better relative ("2h ago"), older ones as a date.
    private static func label(for date: Date) -> String {
        if abs(date.timeIntervalSinceNow) < 60 * 60 * 24 * 5 {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .abbreviated
            return formatter.localizedString(for: date, relativeTo: Date())
        }
        let sameYear = Calendar.current.component(.year, from: date)
            == Calendar.current.component(.year, from: Date())
        return sameYear
            ? date.formatted(.dateTime.month(.abbreviated).day())
            : date.formatted(.dateTime.month(.abbreviated).day().year())
    }
}

/// The long, web-grounded expansion of a headline (server `news_brief`).
struct NewsBrief: Decodable {
    let key: String?
    let generatedAt: String?
    let headlineEn: String?
    let headlineZh: String?
    let whatHappenedEn: String?
    let whatHappenedZh: String?
    let whyItMattersEn: String?
    let whyItMattersZh: String?
    let contextEn: [String]?
    let contextZh: [String]?
    let watchNextEn: [String]?
    let watchNextZh: [String]?
    let confidence: String?
    let sources: [NewsBriefSource]?

    enum CodingKeys: String, CodingKey {
        case key, confidence, sources, headline, context
        case generatedAt = "generated_at"
        case headlineEn = "headline_en"
        case headlineZh = "headline_zh"
        case whatHappened = "what_happened"
        case whatHappenedEn = "what_happened_en"
        case whatHappenedZh = "what_happened_zh"
        case whyItMatters = "why_it_matters"
        case whyItMattersEn = "why_it_matters_en"
        case whyItMattersZh = "why_it_matters_zh"
        case contextEn = "context_en"
        case contextZh = "context_zh"
        case watchNext = "watch_next"
        case watchNextEn = "watch_next_en"
        case watchNextZh = "watch_next_zh"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        key = try box.decodeIfPresent(String.self, forKey: .key)
        generatedAt = try box.decodeIfPresent(String.self, forKey: .generatedAt)
        confidence = try box.decodeIfPresent(String.self, forKey: .confidence)
        sources = try box.decodeIfPresent([NewsBriefSource].self, forKey: .sources)
        let bareHeadline = try box.decodeIfPresent(String.self, forKey: .headline)
        headlineEn = try box.decodeIfPresent(String.self, forKey: .headlineEn) ?? bareHeadline
        headlineZh = try box.decodeIfPresent(String.self, forKey: .headlineZh)
        let bareWhat = try box.decodeIfPresent(String.self, forKey: .whatHappened)
        whatHappenedEn = try box.decodeIfPresent(String.self, forKey: .whatHappenedEn) ?? bareWhat
        whatHappenedZh = try box.decodeIfPresent(String.self, forKey: .whatHappenedZh)
        let bareWhy = try box.decodeIfPresent(String.self, forKey: .whyItMatters)
        whyItMattersEn = try box.decodeIfPresent(String.self, forKey: .whyItMattersEn) ?? bareWhy
        whyItMattersZh = try box.decodeIfPresent(String.self, forKey: .whyItMattersZh)
        let bareContext = try box.decodeIfPresent([String].self, forKey: .context)
        contextEn = try box.decodeIfPresent([String].self, forKey: .contextEn) ?? bareContext
        contextZh = try box.decodeIfPresent([String].self, forKey: .contextZh)
        let bareWatch = try box.decodeIfPresent([String].self, forKey: .watchNext)
        watchNextEn = try box.decodeIfPresent([String].self, forKey: .watchNextEn) ?? bareWatch
        watchNextZh = try box.decodeIfPresent([String].self, forKey: .watchNextZh)
    }

    private func pick(_ en: String?, _ zh: String?, _ lang: AppLanguage) -> String {
        let zhText = (zh ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let enText = (en ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return lang.prefersChineseContent && !zhText.isEmpty ? zhText : enText
    }

    private func pick(_ en: [String]?, _ zh: [String]?, _ lang: AppLanguage) -> [String] {
        let zhRows = zh ?? []
        return lang.prefersChineseContent && !zhRows.isEmpty ? zhRows : (en ?? [])
    }

    func headline(lang: AppLanguage) -> String { pick(headlineEn, headlineZh, lang) }
    func whatHappened(lang: AppLanguage) -> String { pick(whatHappenedEn, whatHappenedZh, lang) }
    func whyItMatters(lang: AppLanguage) -> String { pick(whyItMattersEn, whyItMattersZh, lang) }
    func context(lang: AppLanguage) -> [String] { pick(contextEn, contextZh, lang) }
    func watchNext(lang: AppLanguage) -> [String] { pick(watchNextEn, watchNextZh, lang) }
}

struct NewsBriefSource: Decodable, Identifiable, Hashable {
    var id: String { url }
    let title: String?
    let url: String
}

private extension ISO8601DateFormatter {
    static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

private extension DateFormatter {
    static let plainDay: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()
}

enum NewsAssembler {
    /// Local company archive rows older than this are dropped once live
    /// headlines are available — they were flooding the tape with 2025/early-2026.
    static let maxArchiveAgeDays: Double = 14

    static func fromExternalFeed(_ rows: [ExternalFeedDTO]) -> [NewsItem] {
        rows.compactMap { row in
            let title = row.title ?? row.headline ?? ""
            guard !title.isEmpty else { return nil }
            return NewsItem(
                id: row.id ?? "\(title)-\(row.capturedAt ?? "")",
                title: title,
                summary: row.summary ?? row.description,
                source: row.siteName ?? row.domain ?? row.source,
                url: row.finalUrl ?? row.sourceUrl ?? row.url,
                capturedAt: row.capturedAt ?? row.publishedAt,
                category: row.documentCategory ?? row.category,
                kind: row.kind ?? "news",
                companyName: nil,
                ticker: nil
            )
        }
    }

    static func fromLive(_ rows: [LiveNewsDTO]) -> [NewsItem] {
        rows.compactMap { row in
            let title = row.title ?? ""
            guard !title.isEmpty else { return nil }
            return NewsItem(
                id: row.id ?? "live:\(title)",
                title: title,
                summary: row.summary,
                source: row.source,
                url: row.url,
                capturedAt: row.publishedAt ?? row.capturedAt,
                category: row.category ?? "markets",
                kind: row.kind ?? "live_news",
                companyName: nil,
                ticker: row.ticker
            )
        }
    }

    static func fromCompanies(_ companies: [Company]) -> [NewsItem] {
        var items: [NewsItem] = []
        for company in companies {
            let name = company.name
            let ticker = company.ticker
            for (index, row) in (company.companyNews ?? []).enumerated() {
                let title = row.title ?? ""
                guard !title.isEmpty else { continue }
                items.append(
                    NewsItem(
                        id: "company:\(company.id):\(index):\(title)",
                        title: title,
                        summary: row.summary,
                        source: row.source ?? name,
                        url: row.url,
                        capturedAt: row.publishedAt,
                        category: row.category,
                        kind: "company_news",
                        companyName: name,
                        ticker: ticker
                    )
                )
            }
            for (index, row) in (company.recentNews ?? []).enumerated() {
                let title = row.headline ?? row.title ?? ""
                guard !title.isEmpty else { continue }
                items.append(
                    NewsItem(
                        id: "recent:\(company.id):\(index):\(title)",
                        title: title,
                        summary: row.summary,
                        source: name,
                        url: row.url,
                        capturedAt: row.date ?? row.publishedAt,
                        category: row.category,
                        kind: "company_news",
                        companyName: name,
                        ticker: ticker
                    )
                )
            }
        }
        return items
    }

    static func merge(
        live: [NewsItem] = [],
        feed: [NewsItem],
        companyNews: [NewsItem],
        limit: Int = 80
    ) -> [NewsItem] {
        let cutoff = Date().addingTimeInterval(-maxArchiveAgeDays * 24 * 60 * 60)
        let freshArchive = companyNews.filter { item in
            guard let raw = item.capturedAt, let date = parseDate(raw) else {
                // Undated archive rows only survive when nothing live is in.
                return live.isEmpty
            }
            return date >= cutoff
        }
        var seen = Set<String>()
        var out: [NewsItem] = []
        // Live Yahoo headlines first, then external feed, then fresh archive.
        for item in (live + feed + freshArchive).sorted(by: {
            dateKey($0.capturedAt) > dateKey($1.capturedAt)
        }) {
            let key = item.title.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            out.append(item)
            if out.count >= limit { break }
        }
        return out
    }

    private static func dateKey(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty else { return "" }
        // ISO timestamps sort correctly as strings; plain "2026-04-20" also does.
        return raw
    }

    private static func parseDate(_ raw: String) -> Date? {
        if let date = ISO8601DateFormatter().date(from: raw)
            ?? ISO8601DateFormatter.fractional.date(from: raw) {
            return date
        }
        return DateFormatter.plainDay.date(from: String(raw.prefix(10)))
    }
}

struct LiveNewsDTO: Decodable {
    let id: String?
    let kind: String?
    let title: String?
    let summary: String?
    let source: String?
    let url: String?
    let publishedAt: String?
    let capturedAt: String?
    let category: String?
    let ticker: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, summary, source, url, category, ticker
        case publishedAt = "published_at"
        case capturedAt = "captured_at"
    }
}

struct LiveNewsResponse: Decodable {
    let items: [LiveNewsDTO]?
}

struct ExternalFeedDTO: Decodable {
    let id: String?
    let kind: String?
    let title: String?
    let headline: String?
    let summary: String?
    let description: String?
    let siteName: String?
    let domain: String?
    let source: String?
    let sourceUrl: String?
    let finalUrl: String?
    let url: String?
    let capturedAt: String?
    let publishedAt: String?
    let documentCategory: String?
    let category: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, headline, summary, description, domain, source, url, category
        case siteName = "site_name"
        case sourceUrl = "source_url"
        case finalUrl = "final_url"
        case capturedAt = "captured_at"
        case publishedAt = "published_at"
        case documentCategory = "document_category"
    }
}

struct CompanyNewsDTO: Decodable, Hashable {
    let title: String?
    let headline: String?
    let summary: String?
    let source: String?
    let url: String?
    let publishedAt: String?
    let date: String?
    let category: String?

    enum CodingKeys: String, CodingKey {
        case title, headline, summary, source, url, date, category
        case publishedAt = "published_at"
    }
}
