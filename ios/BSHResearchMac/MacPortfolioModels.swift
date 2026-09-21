import Foundation

// MARK: - Private portfolio (`/api/portfolio`)

struct MacPortfolioPosition: Codable, Equatable {
    var round: String?
    var security: String?
    var entryDate: String?
    var investedUsd: Double?
    var ownershipPct: Double?
    var entryPostMoneyUsd: Double?
    var plannedFollowOnUsd: Double?
    var boardSeat: Bool?
    var lead: Bool?
    var notes: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case round, security, lead, notes
        case entryDate = "entry_date"
        case investedUsd = "invested_usd"
        case ownershipPct = "ownership_pct"
        case entryPostMoneyUsd = "entry_post_money_usd"
        case plannedFollowOnUsd = "planned_follow_on_usd"
        case boardSeat = "board_seat"
        case updatedAt = "updated_at"
    }

    static let empty = MacPortfolioPosition()

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        round = try? c.decodeIfPresent(String.self, forKey: .round)
        security = try? c.decodeIfPresent(String.self, forKey: .security)
        entryDate = try? c.decodeIfPresent(String.self, forKey: .entryDate)
        investedUsd = try? c.decodeIfPresent(Double.self, forKey: .investedUsd)
        ownershipPct = try? c.decodeIfPresent(Double.self, forKey: .ownershipPct)
        entryPostMoneyUsd = try? c.decodeIfPresent(Double.self, forKey: .entryPostMoneyUsd)
        plannedFollowOnUsd = try? c.decodeIfPresent(Double.self, forKey: .plannedFollowOnUsd)
        boardSeat = try? c.decodeIfPresent(Bool.self, forKey: .boardSeat)
        lead = try? c.decodeIfPresent(Bool.self, forKey: .lead)
        notes = try? c.decodeIfPresent(String.self, forKey: .notes)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

struct MacKpiRow: Identifiable, Hashable, Decodable {
    let id: String
    let asOf: String
    let source: String?
    let note: String?
    let arrUsd: Double?
    let revenueUsd: Double?
    let burnUsdMonth: Double?
    let cashUsd: Double?
    let runwayMonths: Double?
    let headcount: Int?
    let customers: Int?
    let excerpts: [String: String]

    enum CodingKeys: String, CodingKey {
        case id, source, note, headcount, customers, excerpts
        case asOf = "as_of"
        case arrUsd = "arr_usd"
        case revenueUsd = "revenue_usd"
        case burnUsdMonth = "burn_usd_month"
        case cashUsd = "cash_usd"
        case runwayMonths = "runway_months"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        asOf = (try? c.decodeIfPresent(String.self, forKey: .asOf)) ?? ""
        source = try? c.decodeIfPresent(String.self, forKey: .source)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        arrUsd = try? c.decodeIfPresent(Double.self, forKey: .arrUsd)
        revenueUsd = try? c.decodeIfPresent(Double.self, forKey: .revenueUsd)
        burnUsdMonth = try? c.decodeIfPresent(Double.self, forKey: .burnUsdMonth)
        cashUsd = try? c.decodeIfPresent(Double.self, forKey: .cashUsd)
        runwayMonths = try? c.decodeIfPresent(Double.self, forKey: .runwayMonths)
        headcount = try? c.decodeIfPresent(Int.self, forKey: .headcount)
        customers = try? c.decodeIfPresent(Int.self, forKey: .customers)
        excerpts = (try? c.decodeIfPresent([String: String].self, forKey: .excerpts)) ?? [:]
    }

    /// `as_of` is a calendar date stored as UTC midnight; place it on that same local day.
    var date: Date? {
        let parts = asOf.prefix(10).split(separator: "-")
        if parts.count == 3, let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]),
           let day = Calendar.current.date(from: DateComponents(year: y, month: m, day: d)) {
            return day
        }
        return MacTimeFormat.parse(asOf)
    }
    var isFromUpdate: Bool { source?.hasPrefix("founder_update:") ?? false }
}

struct MacFounderUpdate: Identifiable, Hashable, Decodable {
    let id: String
    let asOf: String
    let receivedAt: String?
    let source: String?
    let subject: String?
    let text: String
    let extracted: [MacIntakeField]
    let kpiId: String?

    enum CodingKeys: String, CodingKey {
        case id, source, subject, text, extracted
        case asOf = "as_of"
        case receivedAt = "received_at"
        case kpiId = "kpi_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        asOf = (try? c.decodeIfPresent(String.self, forKey: .asOf)) ?? ""
        receivedAt = try? c.decodeIfPresent(String.self, forKey: .receivedAt)
        source = try? c.decodeIfPresent(String.self, forKey: .source)
        subject = try? c.decodeIfPresent(String.self, forKey: .subject)
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        extracted = (try? c.decodeIfPresent([MacIntakeField].self, forKey: .extracted)) ?? []
        kpiId = try? c.decodeIfPresent(String.self, forKey: .kpiId)
    }
}

struct MacMark: Identifiable, Hashable, Decodable {
    let id: String
    let asOf: String
    let valueUsd: Double
    let basis: String
    let note: String?

    enum CodingKeys: String, CodingKey {
        case id, basis, note
        case asOf = "as_of"
        case valueUsd = "value_usd"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        asOf = (try? c.decodeIfPresent(String.self, forKey: .asOf)) ?? ""
        valueUsd = (try? c.decodeIfPresent(Double.self, forKey: .valueUsd)) ?? 0
        basis = (try? c.decodeIfPresent(String.self, forKey: .basis)) ?? "manual"
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }

    var basisLabel: String {
        switch basis {
        case "last_round": return "Last round"
        case "lp_report": return "LP report"
        case "secondary": return "Secondary"
        case "cost": return "At cost"
        default: return "Manual"
        }
    }
}

struct MacPortfolioAlert: Identifiable, Hashable, Decodable {
    var id: String { "\(companyId ?? "")-\(kind)-\(label)" }
    let kind: String
    let severity: String
    let label: String
    let detail: String?
    let companyId: String?
    let companyName: String?

    enum CodingKeys: String, CodingKey {
        case kind, severity, label, detail
        case companyId = "company_id"
        case companyName = "company_name"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = (try? c.decodeIfPresent(String.self, forKey: .kind)) ?? "alert"
        severity = (try? c.decodeIfPresent(String.self, forKey: .severity)) ?? "low"
        label = (try? c.decodeIfPresent(String.self, forKey: .label)) ?? ""
        detail = try? c.decodeIfPresent(String.self, forKey: .detail)
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        companyName = try? c.decodeIfPresent(String.self, forKey: .companyName)
    }

    var isHigh: Bool { severity == "high" }
}

struct MacPortfolioCompany: Identifiable, Decodable {
    var id: String { companyId }
    let companyId: String
    let companyName: String
    let ticker: String?
    let position: MacPortfolioPosition
    let latestKpi: MacKpiRow?
    let latestMark: MacMark?
    let moic: Double?
    let alerts: [MacPortfolioAlert]
    let kpiCount: Int
    let updateCount: Int
    // Only present on the per-company endpoint.
    let kpis: [MacKpiRow]
    let updates: [MacFounderUpdate]
    let marks: [MacMark]

    enum CodingKeys: String, CodingKey {
        case ticker, position, moic, alerts, kpis, updates, marks
        case companyId = "company_id"
        case companyName = "company_name"
        case latestKpi = "latest_kpi"
        case latestMark = "latest_mark"
        case kpiCount = "kpi_count"
        case updateCount = "update_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try c.decode(String.self, forKey: .companyId)
        companyName = (try? c.decodeIfPresent(String.self, forKey: .companyName)) ?? companyId
        ticker = try? c.decodeIfPresent(String.self, forKey: .ticker)
        position = (try? c.decodeIfPresent(MacPortfolioPosition.self, forKey: .position)) ?? .empty
        latestKpi = try? c.decodeIfPresent(MacKpiRow.self, forKey: .latestKpi)
        latestMark = try? c.decodeIfPresent(MacMark.self, forKey: .latestMark)
        moic = try? c.decodeIfPresent(Double.self, forKey: .moic)
        alerts = (try? c.decodeIfPresent([MacPortfolioAlert].self, forKey: .alerts)) ?? []
        kpiCount = (try? c.decodeIfPresent(Int.self, forKey: .kpiCount)) ?? 0
        updateCount = (try? c.decodeIfPresent(Int.self, forKey: .updateCount)) ?? 0
        kpis = (try? c.decodeIfPresent([MacKpiRow].self, forKey: .kpis)) ?? []
        updates = (try? c.decodeIfPresent([MacFounderUpdate].self, forKey: .updates)) ?? []
        marks = (try? c.decodeIfPresent([MacMark].self, forKey: .marks)) ?? []
    }

    var highestAlert: MacPortfolioAlert? {
        alerts.sorted { rank($0.severity) < rank($1.severity) }.first
    }

    private func rank(_ s: String) -> Int { s == "high" ? 0 : (s == "medium" ? 1 : 2) }
}

struct MacPortfolioTotals: Decodable {
    let companyCount: Int
    let investedUsd: Double
    let markedCount: Int
    let markedValueUsd: Double?
    let markedCostUsd: Double?
    let markedMoic: Double?
    let alertCount: Int
    let highAlertCount: Int

    enum CodingKeys: String, CodingKey {
        case companyCount = "company_count"
        case investedUsd = "invested_usd"
        case markedCount = "marked_count"
        case markedValueUsd = "marked_value_usd"
        case markedCostUsd = "marked_cost_usd"
        case markedMoic = "marked_moic"
        case alertCount = "alert_count"
        case highAlertCount = "high_alert_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyCount = (try? c.decodeIfPresent(Int.self, forKey: .companyCount)) ?? 0
        investedUsd = (try? c.decodeIfPresent(Double.self, forKey: .investedUsd)) ?? 0
        markedCount = (try? c.decodeIfPresent(Int.self, forKey: .markedCount)) ?? 0
        markedValueUsd = try? c.decodeIfPresent(Double.self, forKey: .markedValueUsd)
        markedCostUsd = try? c.decodeIfPresent(Double.self, forKey: .markedCostUsd)
        markedMoic = try? c.decodeIfPresent(Double.self, forKey: .markedMoic)
        alertCount = (try? c.decodeIfPresent(Int.self, forKey: .alertCount)) ?? 0
        highAlertCount = (try? c.decodeIfPresent(Int.self, forKey: .highAlertCount)) ?? 0
    }
}

struct MacReservesSettings: Codable, Equatable {
    var fundSizeMusd: Double?
    var reservePct: Double?
    var notes: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case notes
        case fundSizeMusd = "fund_size_musd"
        case reservePct = "reserve_pct"
        case updatedAt = "updated_at"
    }

    init(fundSizeMusd: Double? = nil, reservePct: Double? = nil, notes: String? = nil, updatedAt: String? = nil) {
        self.fundSizeMusd = fundSizeMusd
        self.reservePct = reservePct
        self.notes = notes
        self.updatedAt = updatedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        fundSizeMusd = try? c.decodeIfPresent(Double.self, forKey: .fundSizeMusd)
        reservePct = try? c.decodeIfPresent(Double.self, forKey: .reservePct)
        notes = try? c.decodeIfPresent(String.self, forKey: .notes)
        updatedAt = try? c.decodeIfPresent(String.self, forKey: .updatedAt)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(fundSizeMusd, forKey: .fundSizeMusd)
        try c.encode(reservePct, forKey: .reservePct)
        try c.encodeIfPresent(notes, forKey: .notes)
    }
}

struct MacReservesCompany: Identifiable, Decodable {
    var id: String { companyId }
    let companyId: String
    let companyName: String
    let investedUsd: Double?
    let plannedFollowOnUsd: Double?
    let ownershipPct: Double?
    let runwayAlert: MacPortfolioAlert?

    enum CodingKeys: String, CodingKey {
        case companyId = "company_id"
        case companyName = "company_name"
        case investedUsd = "invested_usd"
        case plannedFollowOnUsd = "planned_follow_on_usd"
        case ownershipPct = "ownership_pct"
        case runwayAlert = "runway_alert"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try c.decode(String.self, forKey: .companyId)
        companyName = (try? c.decodeIfPresent(String.self, forKey: .companyName)) ?? companyId
        investedUsd = try? c.decodeIfPresent(Double.self, forKey: .investedUsd)
        plannedFollowOnUsd = try? c.decodeIfPresent(Double.self, forKey: .plannedFollowOnUsd)
        ownershipPct = try? c.decodeIfPresent(Double.self, forKey: .ownershipPct)
        runwayAlert = try? c.decodeIfPresent(MacPortfolioAlert.self, forKey: .runwayAlert)
    }
}

struct MacReservesPlan: Decodable {
    let settings: MacReservesSettings
    let reservePoolUsd: Double?
    let plannedFollowOnUsd: Double
    let remainingUsd: Double?
    let companies: [MacReservesCompany]

    enum CodingKeys: String, CodingKey {
        case settings, companies
        case reservePoolUsd = "reserve_pool_usd"
        case plannedFollowOnUsd = "planned_follow_on_usd"
        case remainingUsd = "remaining_usd"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        settings = (try? c.decodeIfPresent(MacReservesSettings.self, forKey: .settings)) ?? MacReservesSettings()
        reservePoolUsd = try? c.decodeIfPresent(Double.self, forKey: .reservePoolUsd)
        plannedFollowOnUsd = (try? c.decodeIfPresent(Double.self, forKey: .plannedFollowOnUsd)) ?? 0
        remainingUsd = try? c.decodeIfPresent(Double.self, forKey: .remainingUsd)
        companies = (try? c.decodeIfPresent([MacReservesCompany].self, forKey: .companies)) ?? []
    }
}

struct MacPortfolioDashboard: Decodable {
    let generatedAt: String?
    let companies: [MacPortfolioCompany]
    let totals: MacPortfolioTotals?
    let alerts: [MacPortfolioAlert]
    let reserves: MacReservesPlan?

    enum CodingKeys: String, CodingKey {
        case companies, totals, alerts, reserves
        case generatedAt = "generated_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        companies = (try? c.decodeIfPresent([MacPortfolioCompany].self, forKey: .companies)) ?? []
        totals = try? c.decodeIfPresent(MacPortfolioTotals.self, forKey: .totals)
        alerts = (try? c.decodeIfPresent([MacPortfolioAlert].self, forKey: .alerts)) ?? []
        reserves = try? c.decodeIfPresent(MacReservesPlan.self, forKey: .reserves)
    }
}

enum MacMoney {
    static func short(_ usd: Double?) -> String {
        guard let usd else { return "—" }
        let a = abs(usd)
        // Listed companies reach trillions: Apple read "$4943.00B".
        if a >= 1e12 { return String(format: "$%.2fT", usd / 1e12) }
        if a >= 1e9 { return String(format: "$%.2fB", usd / 1e9) }
        if a >= 1e6 { return String(format: "$%.1fM", usd / 1e6) }
        if a >= 1e3 { return String(format: "$%.0fK", usd / 1e3) }
        return String(format: "$%.0f", usd)
    }
}
