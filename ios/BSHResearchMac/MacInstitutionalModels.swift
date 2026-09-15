import Foundation

// MARK: - Thesis (`/api/thesis`)

struct MacThesis: Codable, Equatable {
    var name: String
    var sectors: [String]
    var stages: [String]
    var geographies: [String]
    var checkSizeMinMusd: Double?
    var checkSizeMaxMusd: Double?
    var keywords: [String]
    var mustBeTrue: [String]
    var disqualifiers: [String]
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case name, sectors, stages, geographies, keywords, disqualifiers
        case checkSizeMinMusd = "check_size_min_musd"
        case checkSizeMaxMusd = "check_size_max_musd"
        case mustBeTrue = "must_be_true"
        case updatedAt = "updated_at"
    }

    static let empty = MacThesis(name: "BSH thesis", sectors: [], stages: [], geographies: [], checkSizeMinMusd: nil, checkSizeMaxMusd: nil, keywords: [], mustBeTrue: [], disqualifiers: [], updatedAt: nil)

    init(name: String, sectors: [String], stages: [String], geographies: [String], checkSizeMinMusd: Double?, checkSizeMaxMusd: Double?, keywords: [String], mustBeTrue: [String], disqualifiers: [String], updatedAt: String?) {
        self.name = name
        self.sectors = sectors
        self.stages = stages
        self.geographies = geographies
        self.checkSizeMinMusd = checkSizeMinMusd
        self.checkSizeMaxMusd = checkSizeMaxMusd
        self.keywords = keywords
        self.mustBeTrue = mustBeTrue
        self.disqualifiers = disqualifiers
        self.updatedAt = updatedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? "BSH thesis"
        sectors = (try? c.decodeIfPresent([String].self, forKey: .sectors)) ?? []
        stages = (try? c.decodeIfPresent([String].self, forKey: .stages)) ?? []
        geographies = (try? c.decodeIfPresent([String].self, forKey: .geographies)) ?? []
        checkSizeMinMusd = try? c.decodeIfPresent(Double.self, forKey: .checkSizeMinMusd)
        checkSizeMaxMusd = try? c.decodeIfPresent(Double.self, forKey: .checkSizeMaxMusd)
        keywords = (try? c.decodeIfPresent([String].self, forKey: .keywords)) ?? []
        mustBeTrue = (try? c.decodeIfPresent([String].self, forKey: .mustBeTrue)) ?? []
        disqualifiers = (try? c.decodeIfPresent([String].self, forKey: .disqualifiers)) ?? []
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(name, forKey: .name)
        try c.encode(sectors, forKey: .sectors)
        try c.encode(stages, forKey: .stages)
        try c.encode(geographies, forKey: .geographies)
        try c.encode(checkSizeMinMusd, forKey: .checkSizeMinMusd)
        try c.encode(checkSizeMaxMusd, forKey: .checkSizeMaxMusd)
        try c.encode(keywords, forKey: .keywords)
        try c.encode(mustBeTrue, forKey: .mustBeTrue)
        try c.encode(disqualifiers, forKey: .disqualifiers)
    }

    var isConfigured: Bool { !sectors.isEmpty || !stages.isEmpty || !keywords.isEmpty || !geographies.isEmpty }
}

struct MacThesisScore: Codable, Hashable {
    let score: Int?
    let fit: String
    let reasons: [String]
    let disqualifiedBy: [String]
    let openQuestions: [String]
    let configured: Bool

    enum CodingKeys: String, CodingKey {
        case score, fit, reasons, configured
        case disqualifiedBy = "disqualified_by"
        case openQuestions = "open_questions"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        fit = (try? c.decodeIfPresent(String.self, forKey: .fit)) ?? "unconfigured"
        reasons = (try? c.decodeIfPresent([String].self, forKey: .reasons)) ?? []
        disqualifiedBy = (try? c.decodeIfPresent([String].self, forKey: .disqualifiedBy)) ?? []
        openQuestions = (try? c.decodeIfPresent([String].self, forKey: .openQuestions)) ?? []
        configured = (try? c.decodeIfPresent(Bool.self, forKey: .configured)) ?? false
    }

    var label: String {
        switch fit {
        case "strong": return "Strong fit"
        case "partial": return "Partial fit"
        case "weak": return "Weak fit"
        case "disqualified": return "Disqualified"
        default: return "No thesis"
        }
    }

    var rank: Int {
        switch fit {
        case "strong": return 0
        case "partial": return 1
        case "weak": return 2
        case "disqualified": return 3
        default: return 4
        }
    }
}

// MARK: - Deck intake (`POST /api/intake/decks`)

struct MacIntakeField: Identifiable, Hashable, Decodable {
    var id: String { name }
    let name: String
    let value: String
    let usd: Double?
    let page: Int?
    let excerpt: String?

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case name, value, usd, page, excerpt }
        let c = try decoder.container(keyedBy: Keys.self)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? "field"
        if let s = try? c.decodeIfPresent(String.self, forKey: .value) {
            value = s
        } else if let d = try? c.decodeIfPresent(Double.self, forKey: .value) {
            value = String(d)
        } else {
            value = ""
        }
        usd = try? c.decodeIfPresent(Double.self, forKey: .usd)
        page = try? c.decodeIfPresent(Int.self, forKey: .page)
        excerpt = try? c.decodeIfPresent(String.self, forKey: .excerpt)
    }

    var label: String {
        switch name {
        case "post_money": return "Post-money"
        case "arr": return "ARR"
        default: return name.capitalized
        }
    }

    var display: String {
        if let usd {
            if usd >= 1e9 { return String(format: "$%.2fB", usd / 1e9) }
            if usd >= 1e6 { return String(format: "$%.1fM", usd / 1e6) }
            if usd >= 1e3 { return String(format: "$%.0fK", usd / 1e3) }
        }
        if name == "runway" { return "\(value) months" }
        return value
    }
}

struct MacIntakeResult: Decodable {
    let company: MacCompany
    let fileId: String?
    let fileName: String?
    let slideCount: Int
    let fields: [MacIntakeField]
    let thesis: MacThesisScore?

    private struct FileRef: Decodable { let id: String?; let filename: String? }
    private struct Extraction: Decodable { let fields: [MacIntakeField]? }

    enum CodingKeys: String, CodingKey {
        case company, file, extraction, thesis
        case slideCount = "slide_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        company = try c.decode(MacCompany.self, forKey: .company)
        let file = try? c.decodeIfPresent(FileRef.self, forKey: .file)
        fileId = file?.id
        fileName = file?.filename
        slideCount = (try? c.decodeIfPresent(Int.self, forKey: .slideCount)) ?? 0
        fields = (try? c.decodeIfPresent(Extraction.self, forKey: .extraction))?.fields ?? []
        thesis = try? c.decodeIfPresent(MacThesisScore.self, forKey: .thesis)
    }
}

// MARK: - Comps (`/api/companies/{id}/comps`)

struct MacCompPeer: Identifiable, Hashable, Decodable {
    var id: String { ticker }
    let ticker: String
    let name: String?
    let lastPrice: Double?
    let changePct1d: Double?
    let marketCapUsd: Double?
    let revenueUsd: Double?
    let priceToSales: Double?
    let revenueGrowth: Double?
    let grossMargin: Double?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case ticker, name, source
        case lastPrice = "last_price"
        case changePct1d = "change_pct_1d"
        case marketCapUsd = "market_cap_usd"
        case revenueUsd = "revenue_usd"
        case priceToSales = "price_to_sales"
        case revenueGrowth = "revenue_growth"
        case grossMargin = "gross_margin"
    }
}

struct MacCompsPrivate: Decodable {
    struct Source: Hashable, Decodable {
        let field: String?
        let section: String?
        let excerpt: String?
    }
    let postMoneyUsd: Double?
    let revenueUsd: Double?
    let impliedMultiple: Double?
    let vsPeerMedianPct: Double?
    let basis: String?
    let sources: [Source]

    enum CodingKeys: String, CodingKey {
        case sources, basis
        case postMoneyUsd = "post_money_usd"
        case revenueUsd = "revenue_usd"
        case impliedMultiple = "implied_multiple"
        case vsPeerMedianPct = "vs_peer_median_pct"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        postMoneyUsd = try? c.decodeIfPresent(Double.self, forKey: .postMoneyUsd)
        revenueUsd = try? c.decodeIfPresent(Double.self, forKey: .revenueUsd)
        impliedMultiple = try? c.decodeIfPresent(Double.self, forKey: .impliedMultiple)
        vsPeerMedianPct = try? c.decodeIfPresent(Double.self, forKey: .vsPeerMedianPct)
        basis = try? c.decodeIfPresent(String.self, forKey: .basis)
        sources = (try? c.decodeIfPresent([Source].self, forKey: .sources)) ?? []
    }
}

struct MacComps: Decodable {
    let companyId: String?
    let generatedAt: String?
    let peers: [MacCompPeer]
    let peerMedianPriceToSales: Double?
    let privateSide: MacCompsPrivate?
    let note: String?

    enum CodingKeys: String, CodingKey {
        case peers, note
        case companyId = "company_id"
        case generatedAt = "generated_at"
        case peerMedianPriceToSales = "peer_median_price_to_sales"
        case privateSide = "private"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        peers = (try? c.decodeIfPresent([MacCompPeer].self, forKey: .peers)) ?? []
        peerMedianPriceToSales = try? c.decodeIfPresent(Double.self, forKey: .peerMedianPriceToSales)
        privateSide = try? c.decodeIfPresent(MacCompsPrivate.self, forKey: .privateSide)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - Cap model (`/api/companies/{id}/cap-model`)

struct MacCapModelInputs: Codable, Equatable {
    var preMoneyMusd: Double?
    var newMoneyMusd: Double?
    var ourCheckMusd: Double?
    var optionPoolPctPost: Double?
    var liquidationPreferenceX: Double?
    var participating: Bool
    var exitValuesMusd: [Double]
    var notes: String

    enum CodingKeys: String, CodingKey {
        case participating, notes
        case preMoneyMusd = "pre_money_musd"
        case newMoneyMusd = "new_money_musd"
        case ourCheckMusd = "our_check_musd"
        case optionPoolPctPost = "option_pool_pct_post"
        case liquidationPreferenceX = "liquidation_preference_x"
        case exitValuesMusd = "exit_values_musd"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        preMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .preMoneyMusd)
        newMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .newMoneyMusd)
        ourCheckMusd = try? c.decodeIfPresent(Double.self, forKey: .ourCheckMusd)
        optionPoolPctPost = try? c.decodeIfPresent(Double.self, forKey: .optionPoolPctPost)
        liquidationPreferenceX = try? c.decodeIfPresent(Double.self, forKey: .liquidationPreferenceX)
        participating = (try? c.decodeIfPresent(Bool.self, forKey: .participating)) ?? false
        exitValuesMusd = (try? c.decodeIfPresent([Double].self, forKey: .exitValuesMusd)) ?? []
        notes = (try? c.decodeIfPresent(String.self, forKey: .notes)) ?? ""
    }

    init(preMoneyMusd: Double?, newMoneyMusd: Double?, ourCheckMusd: Double?, optionPoolPctPost: Double?, liquidationPreferenceX: Double?, participating: Bool, exitValuesMusd: [Double], notes: String) {
        self.preMoneyMusd = preMoneyMusd
        self.newMoneyMusd = newMoneyMusd
        self.ourCheckMusd = ourCheckMusd
        self.optionPoolPctPost = optionPoolPctPost
        self.liquidationPreferenceX = liquidationPreferenceX
        self.participating = participating
        self.exitValuesMusd = exitValuesMusd
        self.notes = notes
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(preMoneyMusd, forKey: .preMoneyMusd)
        try c.encode(newMoneyMusd, forKey: .newMoneyMusd)
        try c.encode(ourCheckMusd, forKey: .ourCheckMusd)
        try c.encode(optionPoolPctPost, forKey: .optionPoolPctPost)
        try c.encode(liquidationPreferenceX, forKey: .liquidationPreferenceX)
        try c.encode(participating, forKey: .participating)
        try c.encode(exitValuesMusd, forKey: .exitValuesMusd)
        try c.encode(notes, forKey: .notes)
    }
}

struct MacCapWaterfallRow: Identifiable, Hashable, Decodable {
    var id: Double { exitMusd }
    let exitMusd: Double
    let ourProceedsMusd: Double?
    let multipleOnCheck: Double?
    let converted: Bool?

    enum CodingKeys: String, CodingKey {
        case converted
        case exitMusd = "exit_musd"
        case ourProceedsMusd = "our_proceeds_musd"
        case multipleOnCheck = "multiple_on_check"
    }
}

struct MacCapModelResult: Decodable {
    let ready: Bool
    let reason: String?
    let postMoneyMusd: Double?
    let roundOwnershipPct: Double?
    let ourOwnershipPct: Double?
    let existingOwnershipPctAfter: Double?
    let waterfall: [MacCapWaterfallRow]

    enum CodingKeys: String, CodingKey {
        case ready, reason, waterfall
        case postMoneyMusd = "post_money_musd"
        case roundOwnershipPct = "round_ownership_pct"
        case ourOwnershipPct = "our_ownership_pct"
        case existingOwnershipPctAfter = "existing_ownership_pct_after"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ready = (try? c.decodeIfPresent(Bool.self, forKey: .ready)) ?? false
        reason = try? c.decodeIfPresent(String.self, forKey: .reason)
        postMoneyMusd = try? c.decodeIfPresent(Double.self, forKey: .postMoneyMusd)
        roundOwnershipPct = try? c.decodeIfPresent(Double.self, forKey: .roundOwnershipPct)
        ourOwnershipPct = try? c.decodeIfPresent(Double.self, forKey: .ourOwnershipPct)
        existingOwnershipPctAfter = try? c.decodeIfPresent(Double.self, forKey: .existingOwnershipPctAfter)
        waterfall = (try? c.decodeIfPresent([MacCapWaterfallRow].self, forKey: .waterfall)) ?? []
    }
}

struct MacCapModel: Decodable {
    let companyId: String?
    let inputs: MacCapModelInputs
    let result: MacCapModelResult?

    enum CodingKeys: String, CodingKey {
        case inputs, result
        case companyId = "company_id"
    }
}
