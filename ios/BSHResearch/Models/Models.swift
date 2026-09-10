import Foundation

struct AuthTokenResponse: Decodable {
    let token: String
    let email: String?
    let name: String?
    let expiresAt: String?

    enum CodingKeys: String, CodingKey {
        case token, email, name
        case expiresAt = "expires_at"
    }
}

struct AuthMeResponse: Decodable {
    let email: String?
    let name: String?
    let authenticated: Bool?
}

struct LoginBody: Encodable {
    let email: String
    let password: String
}

struct Company: Identifiable, Decodable, Hashable {
    let id: String
    let name: String?
    let ticker: String?
    let companyType: String?
    let status: String?
    let sector: String?
    let nameZh: String?
    let companyNews: [CompanyNewsDTO]?
    let recentNews: [CompanyNewsDTO]?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector
        case companyType = "company_type"
        case nameZh = "name_zh"
        case companyNews = "company_news"
        case recentNews = "recent_news"
    }

    func displayName(lang: AppLanguage) -> String {
        if lang == .zh, let nameZh, !nameZh.isEmpty { return nameZh }
        return name ?? id
    }
}

struct CompaniesResponse: Decodable {
    let companies: [Company]?

    init(from decoder: Decoder) throws {
        if let list = try? decoder.singleValueContainer().decode([Company].self) {
            companies = list
            return
        }
        let box = try decoder.container(keyedBy: CodingKeys.self)
        companies = try box.decodeIfPresent([Company].self, forKey: .companies)
    }

    enum CodingKeys: String, CodingKey { case companies }
}

struct Quote: Decodable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let lastPrice: Double?
    let changePct1d: Double?
    let currency: String?
    let asOf: String?
    let name: String?

    enum CodingKeys: String, CodingKey {
        case ticker, currency, name
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
        case asOf = "as_of"
    }
}

struct QuotesResponse: Decodable {
    let generatedAt: String?
    let quotes: [String: Quote]
    let missing: [String]?

    enum CodingKeys: String, CodingKey {
        case quotes, missing
        case generatedAt = "generated_at"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try box.decodeIfPresent(String.self, forKey: .generatedAt)
        missing = try box.decodeIfPresent([String].self, forKey: .missing)
        let raw = try box.decodeIfPresent([String: QuoteDTO].self, forKey: .quotes) ?? [:]
        var mapped: [String: Quote] = [:]
        for (ticker, dto) in raw {
            mapped[ticker] = Quote(
                ticker: ticker,
                lastPrice: dto.lastPrice,
                changePct1d: dto.changePct1d,
                currency: dto.currency,
                asOf: dto.asOf,
                name: dto.name
            )
        }
        quotes = mapped
    }

    private struct QuoteDTO: Decodable {
        let lastPrice: Double?
        let changePct1d: Double?
        let currency: String?
        let asOf: String?
        let name: String?
        enum CodingKeys: String, CodingKey {
            case name, currency
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
            case asOf = "as_of"
        }
    }
}

struct BriefQuoteRow: Decodable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let lastPrice: Double?
    let changePct1d: Double?

    enum CodingKeys: String, CodingKey {
        case ticker
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
    }
}

struct MarketBrief: Decodable {
    let date: String?
    let generatedAt: String?
    let indices: [BriefQuoteRow]?
    let movers: BriefMovers?
    let note: BriefNote?

    enum CodingKeys: String, CodingKey {
        case date, indices, movers, note
        case generatedAt = "generated_at"
    }
}

struct BriefMovers: Decodable {
    let gainers: [BriefQuoteRow]?
    let losers: [BriefQuoteRow]?
}

struct BriefNote: Decodable {
    let length: String?
    let headlineEn: String?
    let headlineZh: String?
    let bulletsEn: [String]?
    let bulletsZh: [String]?
    let sectionsEn: [BriefSection]?
    let sectionsZh: [BriefSection]?

    enum CodingKeys: String, CodingKey {
        case length
        case headlineEn = "headline_en"
        case headlineZh = "headline_zh"
        case bulletsEn = "bullets_en"
        case bulletsZh = "bullets_zh"
        case sectionsEn = "sections_en"
        case sectionsZh = "sections_zh"
    }

    func headline(lang: AppLanguage) -> String {
        lang == .zh ? (headlineZh ?? headlineEn ?? "") : (headlineEn ?? headlineZh ?? "")
    }

    func bullets(lang: AppLanguage) -> [String] {
        lang == .zh ? (bulletsZh ?? bulletsEn ?? []) : (bulletsEn ?? bulletsZh ?? [])
    }

    func sections(lang: AppLanguage) -> [BriefSection] {
        lang == .zh ? (sectionsZh ?? sectionsEn ?? []) : (sectionsEn ?? sectionsZh ?? [])
    }
}

struct BriefSection: Decodable, Identifiable {
    var id: String { "\(title)|\(body.hashValue)" }
    let title: String
    let body: String
}
