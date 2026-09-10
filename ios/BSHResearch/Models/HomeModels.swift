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
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .abbreviated
            return formatter.localizedString(for: date, relativeTo: Date())
        }
        return String(raw.prefix(10))
    }
}

private extension ISO8601DateFormatter {
    static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

enum NewsAssembler {
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

    static func merge(feed: [NewsItem], companyNews: [NewsItem], limit: Int = 80) -> [NewsItem] {
        var seen = Set<String>()
        var out: [NewsItem] = []
        for item in (feed + companyNews).sorted(by: { ($0.capturedAt ?? "") > ($1.capturedAt ?? "") }) {
            let key = item.title.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            out.append(item)
            if out.count >= limit { break }
        }
        return out
    }
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
