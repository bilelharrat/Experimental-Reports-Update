import Foundation

// MARK: - Unified company profile (`/api/companies/{id}/profile`)

struct MacCompanyProfile: Decodable {
    struct PublicSide: Decodable {
        let ticker: String?
        let lastPrice: Double?
        let changePct1d: Double?
        let marketCap: Double?
        let name: String?
        let asOf: String?
        // What a listed company's profile shows in place of ARR and runway.
        let peRatio: Double?
        let eps: Double?
        let fiftyTwoWeekHigh: Double?
        let fiftyTwoWeekLow: Double?
        /// A fraction (0.0031 = 0.31%), as the quote feed stores it.
        let dividendYield: Double?
        enum CodingKeys: String, CodingKey {
            case ticker, name, eps
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
            case marketCap = "market_cap"
            case asOf = "as_of"
            case peRatio = "pe_ratio"
            case fiftyTwoWeekHigh = "fifty_two_week_high"
            case fiftyTwoWeekLow = "fifty_two_week_low"
            case dividendYield = "dividend_yield"
        }
    }
    /// A figure the company record carries — the rows the memo's metric
    /// snapshot quotes — with when and where it is from.
    struct Reported: Decodable {
        let label: String
        let value: String
        let asOf: String?
        let sourceClass: String?
        enum CodingKeys: String, CodingKey {
            case label, value
            case asOf = "as_of"
            case sourceClass = "source_class"
        }
        /// "2026-06-13" → "2026-06"; a bare year or free text stays as is.
        var asOfShort: String? {
            guard let raw = asOf?.trimmingCharacters(in: .whitespaces), !raw.isEmpty else { return nil }
            let isoDay = raw.range(of: #"^\d{4}-\d{2}-\d{2}"#, options: .regularExpression) != nil
            return isoDay ? String(raw.prefix(7)) : raw
        }
        var help: String {
            [label, asOf.map { "as of \($0)" }, sourceClass].compactMap { $0 }.joined(separator: " · ")
        }
    }
    struct PrivateSide: Decodable {
        let position: MacPortfolioPosition
        let latestKpi: MacKpiRow?
        let latestMark: MacMark?
        let moic: Double?
        let alerts: [MacPortfolioAlert]
        enum CodingKeys: String, CodingKey {
            case position, moic, alerts
            case latestKpi = "latest_kpi"
            case latestMark = "latest_mark"
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            position = (try? c.decodeIfPresent(MacPortfolioPosition.self, forKey: .position)) ?? .empty
            latestKpi = try? c.decodeIfPresent(MacKpiRow.self, forKey: .latestKpi)
            latestMark = try? c.decodeIfPresent(MacMark.self, forKey: .latestMark)
            moic = try? c.decodeIfPresent(Double.self, forKey: .moic)
            alerts = (try? c.decodeIfPresent([MacPortfolioAlert].self, forKey: .alerts)) ?? []
        }
    }
    struct Fit: Decodable { let score: Int?; let fit: String?; let reasons: [String]? }
    struct Pipeline: Decodable { let stage: String?; let owner: String?; let nextStep: String?
        enum CodingKeys: String, CodingKey { case stage, owner; case nextStep = "next_step" } }
    struct Decision: Decodable { let verdict: String?; let decidedAt: String?; let explanation: String?
        enum CodingKeys: String, CodingKey { case verdict, explanation; case decidedAt = "decided_at" } }
    struct IC: Decodable {
        let openMeeting: String?; let meetingCount: Int?; let referenceCalls: Int?; let referenceRating: Double?
        enum CodingKeys: String, CodingKey {
            case openMeeting = "open_meeting"; case meetingCount = "meeting_count"
            case referenceCalls = "reference_calls"; case referenceRating = "reference_rating"
        }
    }
    struct Counts: Decodable {
        let files: Int?; let transcripts: Int?; let openComments: Int?; let decisions: Int?; let kpiRows: Int?
        enum CodingKeys: String, CodingKey {
            case files, transcripts, decisions
            case openComments = "open_comments"; case kpiRows = "kpi_rows"
        }
    }

    let companyId: String
    let name: String
    let description: String
    let sector: String
    let hq: String
    let isPublic: Bool
    let ticker: String?
    let publicSide: PublicSide?
    let privateSide: PrivateSide?
    let thesisFit: Fit?
    let pipeline: Pipeline?
    let latestDecision: Decision?
    let ic: IC?
    let counts: Counts?
    /// Keyed arr, revenue, growth, valuation, runway, tam.
    let reported: [String: Reported]

    enum CodingKeys: String, CodingKey {
        case name, description, sector, hq, ticker, pipeline, ic, counts, reported
        case companyId = "company_id"
        case isPublic = "is_public"
        case publicSide = "public"
        case privateSide = "private"
        case thesisFit = "thesis_fit"
        case latestDecision = "latest_decision"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try c.decode(String.self, forKey: .companyId)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? companyId
        description = (try? c.decodeIfPresent(String.self, forKey: .description)) ?? ""
        sector = (try? c.decodeIfPresent(String.self, forKey: .sector)) ?? ""
        hq = (try? c.decodeIfPresent(String.self, forKey: .hq)) ?? ""
        isPublic = (try? c.decodeIfPresent(Bool.self, forKey: .isPublic)) ?? false
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        publicSide = try? c.decodeIfPresent(PublicSide.self, forKey: .publicSide)
        privateSide = try? c.decodeIfPresent(PrivateSide.self, forKey: .privateSide)
        thesisFit = try? c.decodeIfPresent(Fit.self, forKey: .thesisFit)
        pipeline = try? c.decodeIfPresent(Pipeline.self, forKey: .pipeline)
        latestDecision = try? c.decodeIfPresent(Decision.self, forKey: .latestDecision)
        ic = try? c.decodeIfPresent(IC.self, forKey: .ic)
        counts = try? c.decodeIfPresent(Counts.self, forKey: .counts)
        reported = (try? c.decodeIfPresent([String: Reported].self, forKey: .reported)) ?? [:]
    }
}

// MARK: - One listed company's earnings and filings (dossier Overview)

/// `GET /api/companies/:id/earnings-filings` — the public-company counterpart
/// of the deal pipeline: next report, recent quarters against the estimate,
/// and SEC filings from the last 90 days.
struct MacCompanyEarningsFilings: Decodable {
    struct Quarter: Identifiable, Decodable {
        var id: String { (period ?? "") + (reported ?? "") }
        let period: String?
        let reported: String?
        let eps: Double?
        let estimate: Double?
        let surprisePct: Double?
        enum CodingKeys: String, CodingKey {
            case period, reported, eps, estimate
            case surprisePct = "surprise_pct"
        }
    }
    struct Earnings: Decodable {
        let nextDate: String?
        let nextEstimated: Bool
        let daysToNext: Int?
        let history: [Quarter]
        enum CodingKeys: String, CodingKey {
            case history
            case nextDate = "next_date"
            case nextEstimated = "next_estimated"
            case daysToNext = "days_to_next"
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            nextDate = try? c.decodeIfPresent(String.self, forKey: .nextDate)
            nextEstimated = (try? c.decodeIfPresent(Bool.self, forKey: .nextEstimated)) ?? false
            daysToNext = try? c.decodeIfPresent(Int.self, forKey: .daysToNext)
            history = (try? c.decodeIfPresent([Quarter].self, forKey: .history)) ?? []
        }
    }
    let ticker: String?
    let earnings: Earnings?
    let filings: [MacFiling]
    let error: String?
    enum CodingKeys: String, CodingKey { case ticker, earnings, filings, error }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        earnings = try? c.decodeIfPresent(Earnings.self, forKey: .earnings)
        filings = (try? c.decodeIfPresent([MacFiling].self, forKey: .filings)) ?? []
        error = try? c.decodeIfPresent(String.self, forKey: .error)
    }
}

extension MacFiling {
    /// EDGAR's own description is often just the form again ("FORM 4").
    var plainLabel: String {
        let desc = (description ?? "").trimmingCharacters(in: .whitespaces)
        let bare = desc.replacingOccurrences(of: "^form\\s+", with: "", options: [.regularExpression, .caseInsensitive]).uppercased()
        if !desc.isEmpty && bare != form.uppercased() { return desc }
        let labels: [String: String] = [
            "4": "Insider transaction", "8-K": "Current report", "10-Q": "Quarterly report",
            "10-K": "Annual report", "DEF 14A": "Proxy statement", "S-1": "Registration statement",
            "S-1/A": "Registration amendment", "424B4": "Prospectus",
            "SC 13D": "Ownership stake · active", "SC 13D/A": "Ownership stake · active, amended",
            "SC 13G": "Ownership stake · passive", "SC 13G/A": "Ownership stake · passive, amended",
            "6-K": "Foreign issuer report", "20-F": "Foreign annual report",
        ]
        return labels[form] ?? (desc.isEmpty ? form : desc)
    }
}

// MARK: - Filings & earnings watch

struct MacFiling: Identifiable, Hashable, Decodable {
    var id: String { "\(ticker ?? "")-\(form)-\(filed)-\(url)" }
    let form: String
    let filed: String
    let description: String?
    let url: String
    let material: Bool
    let ticker: String?
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case form, filed, description, url, material, ticker }
        let c = try decoder.container(keyedBy: Keys.self)
        form = (try? c.decodeIfPresent(String.self, forKey: .form)) ?? ""
        filed = (try? c.decodeIfPresent(String.self, forKey: .filed)) ?? ""
        description = try? c.decodeIfPresent(String.self, forKey: .description)
        url = (try? c.decodeIfPresent(String.self, forKey: .url)) ?? ""
        material = (try? c.decodeIfPresent(Bool.self, forKey: .material)) ?? false
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
    }
}

struct MacFilingsRow: Identifiable, Decodable {
    var id: String { ticker }
    struct Earnings: Decodable {
        let nextDate: String?; let nextEstimated: Bool?; let daysToNext: Int?; let lastReported: String?; let lastSurprisePct: Double?
        enum CodingKeys: String, CodingKey {
            case nextDate = "next_date"; case nextEstimated = "next_estimated"; case daysToNext = "days_to_next"
            case lastReported = "last_reported"; case lastSurprisePct = "last_surprise_pct"
        }
    }
    let ticker: String
    let companyId: String?
    let companyName: String?
    let filings: [MacFiling]
    let materialCount: Int
    let earnings: Earnings?
    let error: String?
    enum CodingKeys: String, CodingKey {
        case ticker, filings, earnings, error
        case companyId = "company_id"; case companyName = "company_name"; case materialCount = "material_count"
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ticker = try c.decode(String.self, forKey: .ticker)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        companyName = try? c.decodeIfPresent(String.self, forKey: .companyName)
        filings = (try? c.decodeIfPresent([MacFiling].self, forKey: .filings)) ?? []
        materialCount = (try? c.decodeIfPresent(Int.self, forKey: .materialCount)) ?? 0
        earnings = try? c.decodeIfPresent(Earnings.self, forKey: .earnings)
        error = try? c.decodeIfPresent(String.self, forKey: .error)
    }
}

struct MacFilingsWatch: Decodable {
    struct Upcoming: Identifiable, Decodable {
        var id: String { ticker }
        let ticker: String; let date: String?; let days: Int?; let estimated: Bool?
    }
    let generatedAt: String?
    let tickers: [MacFilingsRow]
    let upcomingEarnings: [Upcoming]
    let materialFilings: [MacFiling]
    let note: String?
    enum CodingKeys: String, CodingKey {
        case tickers, note
        case generatedAt = "generated_at"; case upcomingEarnings = "upcoming_earnings"; case materialFilings = "material_filings"
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        tickers = (try? c.decodeIfPresent([MacFilingsRow].self, forKey: .tickers)) ?? []
        upcomingEarnings = (try? c.decodeIfPresent([Upcoming].self, forKey: .upcomingEarnings)) ?? []
        materialFilings = (try? c.decodeIfPresent([MacFiling].self, forKey: .materialFilings)) ?? []
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - Signal watch

struct MacSignalMove: Identifiable, Decodable {
    var id: String { companyId }
    let companyId: String
    let companyName: String
    let score: Int?
    let previous: Int?
    let delta: Int?
    let coverage: String?
    let flags: [String]
    enum CodingKeys: String, CodingKey {
        case score, previous, delta, coverage, flags
        case companyId = "company_id"; case companyName = "company_name"
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try c.decode(String.self, forKey: .companyId)
        companyName = (try? c.decodeIfPresent(String.self, forKey: .companyName)) ?? companyId
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        previous = try? c.decodeIfPresent(Int.self, forKey: .previous)
        delta = try? c.decodeIfPresent(Int.self, forKey: .delta)
        coverage = try? c.decodeIfPresent(String.self, forKey: .coverage)
        flags = (try? c.decodeIfPresent([String].self, forKey: .flags)) ?? []
    }
}

struct MacSignalMoves: Decodable {
    let generatedAt: String?
    let previousSnapshotAt: String?
    let snapshotCount: Int
    let items: [MacSignalMove]
    let flagged: [MacSignalMove]
    enum CodingKeys: String, CodingKey {
        case items, flagged
        case generatedAt = "generated_at"; case previousSnapshotAt = "previous_snapshot_at"; case snapshotCount = "snapshot_count"
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        previousSnapshotAt = try? c.decodeIfPresent(String.self, forKey: .previousSnapshotAt)
        snapshotCount = (try? c.decodeIfPresent(Int.self, forKey: .snapshotCount)) ?? 0
        items = (try? c.decodeIfPresent([MacSignalMove].self, forKey: .items)) ?? []
        flagged = (try? c.decodeIfPresent([MacSignalMove].self, forKey: .flagged)) ?? []
    }
}

// MARK: - Numbers lint

struct MacNumberFinding: Identifiable, Hashable, Decodable {
    var id: String { key ?? "\(position)|\(section)|\(number)|\(excerpt)" }
    var position = 0
    let key: String?
    let section: String
    let number: String
    let excerpt: String
    let lookedFor: [String]
    enum CodingKeys: String, CodingKey { case key, section, number, excerpt; case lookedFor = "looked_for" }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let rawKey = try? c.decodeIfPresent(String.self, forKey: .key)
        key = (rawKey?.isEmpty ?? true) ? nil : rawKey
        section = (try? c.decodeIfPresent(String.self, forKey: .section)) ?? ""
        number = (try? c.decodeIfPresent(String.self, forKey: .number)) ?? ""
        excerpt = (try? c.decodeIfPresent(String.self, forKey: .excerpt)) ?? ""
        lookedFor = (try? c.decodeIfPresent([String].self, forKey: .lookedFor)) ?? []
    }
}

struct MacNumberLint: Decodable {
    let memoPackage: String?
    let checked: Int
    let supported: Int
    let unsupported: Int
    let coveragePct: Int?
    let findings: [MacNumberFinding]
    let sources: [String]
    let note: String?
    enum CodingKeys: String, CodingKey {
        case checked, supported, unsupported, findings, sources, note
        case memoPackage = "memo_package"; case coveragePct = "coverage_pct"
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        memoPackage = try? c.decodeIfPresent(String.self, forKey: .memoPackage)
        checked = (try? c.decodeIfPresent(Int.self, forKey: .checked)) ?? 0
        supported = (try? c.decodeIfPresent(Int.self, forKey: .supported)) ?? 0
        unsupported = (try? c.decodeIfPresent(Int.self, forKey: .unsupported)) ?? 0
        coveragePct = try? c.decodeIfPresent(Int.self, forKey: .coveragePct)
        let decoded = (try? c.decodeIfPresent([MacNumberFinding].self, forKey: .findings)) ?? []
        findings = decoded.enumerated().map { offset, finding in
            var numbered = finding
            numbered.position = offset
            return numbered
        }
        sources = (try? c.decodeIfPresent([String].self, forKey: .sources)) ?? []
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - Saved workspaces (local)

struct MacWorkspace: Codable, Identifiable, Hashable {
    var id: String { name }
    var name: String
    var tab: String
    var blotterOpen: Bool
    var blotterTab: String
    var portfolioMode: String
    var documentsMode: String
    var companyId: String?
    var savedAt: Date
}
