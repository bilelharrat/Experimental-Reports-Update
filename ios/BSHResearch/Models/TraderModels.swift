import Foundation

/// Trader snapshot payload attached to public companies
/// (`company.trader_snapshot`). Bilingual fields carry `_en` / `_zh`
/// variants; accessors pick per app language.
struct TraderSnapshot: Decodable {
    let refreshedAt: String?
    let priceCard: TraderPriceCard?
    let momentumCard: TraderMomentumCard?
    let sentimentCard: TraderSentimentCard?
    let catalysts: [TraderCatalyst]?
    let traderNews: [TraderNewsItem]?
    let techMovers: TraderTechMovers?
    let marketSession: TraderMarketSession?

    enum CodingKeys: String, CodingKey {
        case catalysts
        case refreshedAt = "refreshed_at"
        case priceCard = "price_card"
        case momentumCard = "momentum_card"
        case sentimentCard = "sentiment_card"
        case traderNews = "trader_news"
        case techMovers = "tech_movers"
        case marketSession = "market_session"
    }

    var isEmpty: Bool {
        priceCard == nil && momentumCard == nil && sentimentCard == nil
            && (catalysts ?? []).isEmpty && (traderNews ?? []).isEmpty
    }
}

struct TraderPriceCard: Decodable {
    let lastPrice: Double?
    let currency: String?
    let asOf: String?
    let changePct1d: Double?
    let changePct5d: Double?
    let changePct30d: Double?
    let changePctYtd: Double?
    let changePct1y: Double?
    let vsSector30dPct: Double?
    let vsSp50030dPct: Double?

    enum CodingKeys: String, CodingKey {
        case currency
        case lastPrice = "last_price"
        case asOf = "as_of"
        case changePct1d = "change_pct_1d"
        case changePct5d = "change_pct_5d"
        case changePct30d = "change_pct_30d"
        case changePctYtd = "change_pct_ytd"
        case changePct1y = "change_pct_1y"
        case vsSector30dPct = "vs_sector_30d_pct"
        case vsSp50030dPct = "vs_sp500_30d_pct"
    }
}

struct TraderMomentumCard: Decodable {
    let trend: String?
    let trendEn: String?
    let trendZh: String?
    let above50dma: Bool?
    let above200dma: Bool?
    let breakoutSignalsEn: String?
    let breakoutSignalsZh: String?

    enum CodingKeys: String, CodingKey {
        case trend
        case trendEn = "trend_en"
        case trendZh = "trend_zh"
        case above50dma = "above_50dma"
        case above200dma = "above_200dma"
        case breakoutSignalsEn = "breakout_signals_en"
        case breakoutSignalsZh = "breakout_signals_zh"
    }

    func trendText(lang: AppLanguage) -> String {
        (lang == .zh ? trendZh : trendEn) ?? trendEn ?? trend ?? ""
    }

    func breakoutText(lang: AppLanguage) -> String {
        (lang == .zh ? breakoutSignalsZh : breakoutSignalsEn) ?? breakoutSignalsEn ?? ""
    }
}

struct TraderSentimentCard: Decodable {
    let analystConsensus: String?
    let analystConsensusEn: String?
    let analystConsensusZh: String?
    let coverageCount: Int?
    let targetPrice: TraderTargetPrice?

    enum CodingKeys: String, CodingKey {
        case analystConsensus = "analyst_consensus"
        case analystConsensusEn = "analyst_consensus_en"
        case analystConsensusZh = "analyst_consensus_zh"
        case coverageCount = "coverage_count"
        case targetPrice = "target_price"
    }

    func consensusText(lang: AppLanguage) -> String {
        (lang == .zh ? analystConsensusZh : analystConsensusEn)
            ?? analystConsensusEn ?? analystConsensus ?? ""
    }
}

struct TraderTargetPrice: Decodable {
    let mean: Double?
    let high: Double?
    let low: Double?
}

struct TraderCatalyst: Decodable, Identifiable {
    var id: String { "\(date ?? "")-\(titleEn ?? title ?? UUID().uuidString)" }
    let date: String?
    let type: String?
    let title: String?
    let titleEn: String?
    let titleZh: String?
    let summaryEn: String?
    let summaryZh: String?

    enum CodingKeys: String, CodingKey {
        case date, type, title
        case titleEn = "title_en"
        case titleZh = "title_zh"
        case summaryEn = "summary_en"
        case summaryZh = "summary_zh"
    }

    func titleText(lang: AppLanguage) -> String {
        (lang == .zh ? titleZh : titleEn) ?? titleEn ?? title ?? ""
    }

    func summaryText(lang: AppLanguage) -> String {
        (lang == .zh ? summaryZh : summaryEn) ?? summaryEn ?? ""
    }
}

struct TraderNewsItem: Decodable, Identifiable {
    var id: String { "\(date ?? "")-\(headlineEn ?? headline ?? UUID().uuidString)" }
    let date: String?
    let bias: String?
    let headline: String?
    let headlineEn: String?
    let headlineZh: String?
    let summaryEn: String?
    let summaryZh: String?
    let sourceUrl: String?

    enum CodingKeys: String, CodingKey {
        case date, bias, headline
        case headlineEn = "headline_en"
        case headlineZh = "headline_zh"
        case summaryEn = "summary_en"
        case summaryZh = "summary_zh"
        case sourceUrl = "source_url"
    }

    func headlineText(lang: AppLanguage) -> String {
        (lang == .zh ? headlineZh : headlineEn) ?? headlineEn ?? headline ?? ""
    }
}

struct TraderTechMovers: Decodable {
    let movers: [TraderMover]?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case movers
        case updatedAt = "updated_at"
    }
}

struct TraderMover: Decodable, Identifiable {
    var id: String { ticker ?? UUID().uuidString }
    let ticker: String?
    let companyEn: String?
    let companyZh: String?
    let changePct1d: Double?
    let direction: String?
    let marketDriverEn: String?
    let marketDriverZh: String?

    enum CodingKeys: String, CodingKey {
        case ticker, direction
        case companyEn = "company_en"
        case companyZh = "company_zh"
        case changePct1d = "change_pct_1d"
        case marketDriverEn = "market_driver_en"
        case marketDriverZh = "market_driver_zh"
    }

    func companyText(lang: AppLanguage) -> String {
        (lang == .zh ? companyZh : companyEn) ?? companyEn ?? ticker ?? ""
    }

    func driverText(lang: AppLanguage) -> String {
        (lang == .zh ? marketDriverZh : marketDriverEn) ?? marketDriverEn ?? ""
    }
}

struct TraderMarketSession: Decodable {
    let exchange: String?
    let isOpenNow: Bool?
    let asOf: String?

    enum CodingKeys: String, CodingKey {
        case exchange
        case isOpenNow = "is_open_now"
        case asOf = "as_of"
    }
}

/// `POST /companies/{id}/trader/refresh` response.
struct TraderRefreshStart: Decodable {
    let jobId: String?
    let streamUrl: String?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case status
        case jobId = "job_id"
        case streamUrl = "stream_url"
    }
}
