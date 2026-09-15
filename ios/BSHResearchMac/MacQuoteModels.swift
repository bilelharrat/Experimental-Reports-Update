import Foundation

// Quote detail payloads beyond the chart: the Nasdaq workspace blocks
// (`GET /api/quotes/{ticker}/workspace`), relative performance (`/peers`) and the
// event calendar (`/calendar`). The server mixes numbers and display strings, so every
// field decodes leniently and a bad value only blanks that field.

private extension KeyedDecodingContainer {
    func lenientString(_ key: Key) -> String? {
        if let s = try? decodeIfPresent(String.self, forKey: key) { return s }
        if let d = try? decodeIfPresent(Double.self, forKey: key) {
            return d == d.rounded() && abs(d) < 1e15 ? String(Int64(d)) : String(d)
        }
        return nil
    }

    func lenientDouble(_ key: Key) -> Double? {
        if let d = try? decodeIfPresent(Double.self, forKey: key) { return d }
        if let s = try? decodeIfPresent(String.self, forKey: key) { return MacFinNumber.parse(s) }
        return nil
    }
}

/// "$1,234", "12.5%", "1.2B", "--" → Double (the web's `parseFinNumber`).
enum MacFinNumber {
    static func parse(_ raw: String?) -> Double? {
        guard var text = raw?.trimmingCharacters(in: .whitespaces), !text.isEmpty else { return nil }
        text = text.replacingOccurrences(of: ",", with: "")
            .replacingOccurrences(of: "$", with: "")
            .replacingOccurrences(of: "%", with: "")
            .replacingOccurrences(of: " ", with: "")
        guard !text.isEmpty, text != "-", text != "--", text != "—" else { return nil }
        var multiplier = 1.0
        if let last = text.last?.lowercased() {
            switch last {
            case "t": multiplier = 1e12
            case "b": multiplier = 1e9
            case "m": multiplier = 1e6
            case "k": multiplier = 1e3
            default: break
            }
            if multiplier != 1 { text.removeLast() }
        }
        guard let value = Double(text), value.isFinite else { return nil }
        return value * multiplier
    }
}

// MARK: - Workspace blocks

struct MacFinTable: Decodable {
    struct Row: Decodable, Identifiable {
        let id = UUID()
        let label: String
        let section: Bool
        let values: [String]

        enum CodingKeys: String, CodingKey { case label, section, values }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            label = c.lenientString(.label) ?? ""
            section = (try? c.decodeIfPresent(Bool.self, forKey: .section)) ?? false
            if let strings = try? c.decodeIfPresent([String?].self, forKey: .values) {
                values = strings.map { $0 ?? "" }
            } else if let numbers = try? c.decodeIfPresent([Double?].self, forKey: .values) {
                values = numbers.map { $0.map { String($0) } ?? "" }
            } else {
                values = []
            }
        }
    }

    let headers: [String]
    let rows: [Row]

    enum CodingKeys: String, CodingKey { case headers, rows }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headers = (try? c.decodeIfPresent([String].self, forKey: .headers)) ?? []
        rows = (try? c.decodeIfPresent([Row].self, forKey: .rows)) ?? []
    }
}

struct MacQuoteFinancials: Decodable {
    let income: MacFinTable?
    let balance: MacFinTable?
    let cashflow: MacFinTable?
    let ratios: MacFinTable?

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case income, balance, cashflow, ratios }
        let c = try decoder.container(keyedBy: K.self)
        income = try? c.decodeIfPresent(MacFinTable.self, forKey: .income)
        balance = try? c.decodeIfPresent(MacFinTable.self, forKey: .balance)
        cashflow = try? c.decodeIfPresent(MacFinTable.self, forKey: .cashflow)
        ratios = try? c.decodeIfPresent(MacFinTable.self, forKey: .ratios)
    }
}

struct MacQuoteEstimate: Decodable, Identifiable {
    var id: String { period }
    let period: String
    let consensus: Double?
    let high: Double?
    let low: Double?
    let estimates: Double?
    let revisionsUp: Double?
    let revisionsDown: Double?

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey {
            case period, consensus, high, low, estimates
            case revisionsUp = "revisions_up", revisionsDown = "revisions_down"
        }
        let c = try decoder.container(keyedBy: K.self)
        period = c.lenientString(.period) ?? "—"
        consensus = c.lenientDouble(.consensus)
        high = c.lenientDouble(.high)
        low = c.lenientDouble(.low)
        estimates = c.lenientDouble(.estimates)
        revisionsUp = c.lenientDouble(.revisionsUp)
        revisionsDown = c.lenientDouble(.revisionsDown)
    }
}

struct MacQuoteAnalysis: Decodable {
    let target: Double?
    let targetLow: Double?
    let targetHigh: Double?
    let buy: Int
    let hold: Int
    let sell: Int
    let quarterly: [MacQuoteEstimate]
    let yearly: [MacQuoteEstimate]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey {
            case target, buy, hold, sell, quarterly, yearly
            case targetLow = "target_low", targetHigh = "target_high"
        }
        let c = try decoder.container(keyedBy: K.self)
        target = c.lenientDouble(.target)
        targetLow = c.lenientDouble(.targetLow)
        targetHigh = c.lenientDouble(.targetHigh)
        buy = Int(c.lenientDouble(.buy) ?? 0)
        hold = Int(c.lenientDouble(.hold) ?? 0)
        sell = Int(c.lenientDouble(.sell) ?? 0)
        quarterly = (try? c.decodeIfPresent([MacQuoteEstimate].self, forKey: .quarterly)) ?? []
        yearly = (try? c.decodeIfPresent([MacQuoteEstimate].self, forKey: .yearly)) ?? []
    }
}

struct MacQuoteHolder: Decodable, Identifiable {
    let id = UUID()
    let owner: String
    let date: String?
    let shares: String?
    let change: String?
    let changePct: String?
    let value: String?

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case owner, name, date, shares, change, value; case changePct = "change_pct" }
        let c = try decoder.container(keyedBy: K.self)
        owner = c.lenientString(.owner) ?? c.lenientString(.name) ?? "—"
        date = c.lenientString(.date)
        shares = c.lenientString(.shares)
        change = c.lenientString(.change)
        changePct = c.lenientString(.changePct)
        value = c.lenientString(.value)
    }
}

struct MacQuoteHolders: Decodable {
    let ownershipPct: String?
    let sharesOut: String?
    let holdingsValue: String?
    let holders: [MacQuoteHolder]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey {
            case holders
            case ownershipPct = "ownership_pct", sharesOut = "shares_out", holdingsValue = "holdings_value"
        }
        let c = try decoder.container(keyedBy: K.self)
        ownershipPct = c.lenientString(.ownershipPct)
        sharesOut = c.lenientString(.sharesOut)
        holdingsValue = c.lenientString(.holdingsValue)
        holders = (try? c.decodeIfPresent([MacQuoteHolder].self, forKey: .holders)) ?? []
    }
}

struct MacQuoteInsiders: Decodable {
    struct Summary: Decodable, Identifiable {
        var id: String { label }
        let label: String
        let months3: String?
        let months12: String?

        init(from decoder: Decoder) throws {
            enum K: String, CodingKey { case label, months3, months12 }
            let c = try decoder.container(keyedBy: K.self)
            label = c.lenientString(.label) ?? "—"
            months3 = c.lenientString(.months3)
            months12 = c.lenientString(.months12)
        }
    }

    struct Trade: Decodable, Identifiable {
        let id = UUID()
        let insider: String
        let relation: String?
        let lastDate: String?
        let transactionType: String?
        let sharesTraded: String?
        let lastPrice: String?
        let sharesHeld: String?

        init(from decoder: Decoder) throws {
            enum K: String, CodingKey { case insider, relation, lastDate, transactionType, sharesTraded, lastPrice, sharesHeld }
            let c = try decoder.container(keyedBy: K.self)
            insider = c.lenientString(.insider) ?? "—"
            relation = c.lenientString(.relation)
            lastDate = c.lenientString(.lastDate)
            transactionType = c.lenientString(.transactionType)
            sharesTraded = c.lenientString(.sharesTraded)
            lastPrice = c.lenientString(.lastPrice)
            sharesHeld = c.lenientString(.sharesHeld)
        }
    }

    let summary: [Summary]
    let recent: [Trade]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case summary, recent }
        let c = try decoder.container(keyedBy: K.self)
        summary = (try? c.decodeIfPresent([Summary].self, forKey: .summary)) ?? []
        recent = (try? c.decodeIfPresent([Trade].self, forKey: .recent)) ?? []
    }
}

struct MacOptionRow: Decodable, Identifiable {
    let id = UUID()
    let expiry: String
    let strike: Double?
    let callLast: String?
    let callBid: String?
    let callAsk: String?
    let callVolume: String?
    let callOi: String?
    let putLast: String?
    let putBid: String?
    let putAsk: String?
    let putVolume: String?
    let putOi: String?

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey {
            case expiry, strike
            case callLast = "call_last", callBid = "call_bid", callAsk = "call_ask", callVolume = "call_volume", callOi = "call_oi"
            case putLast = "put_last", putBid = "put_bid", putAsk = "put_ask", putVolume = "put_volume", putOi = "put_oi"
        }
        let c = try decoder.container(keyedBy: K.self)
        expiry = c.lenientString(.expiry) ?? ""
        strike = c.lenientDouble(.strike)
        callLast = c.lenientString(.callLast)
        callBid = c.lenientString(.callBid)
        callAsk = c.lenientString(.callAsk)
        callVolume = c.lenientString(.callVolume)
        callOi = c.lenientString(.callOi)
        putLast = c.lenientString(.putLast)
        putBid = c.lenientString(.putBid)
        putAsk = c.lenientString(.putAsk)
        putVolume = c.lenientString(.putVolume)
        putOi = c.lenientString(.putOi)
    }
}

struct MacQuoteOptions: Decodable {
    let lastTrade: String?
    let rows: [MacOptionRow]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case rows; case lastTrade = "last_trade" }
        let c = try decoder.container(keyedBy: K.self)
        lastTrade = c.lenientString(.lastTrade)
        rows = (try? c.decodeIfPresent([MacOptionRow].self, forKey: .rows)) ?? []
    }
}

struct MacQuoteEarnings: Decodable {
    struct Print: Decodable, Identifiable {
        let id = UUID()
        let period: String
        let reported: String?
        let eps: Double?
        let estimate: Double?
        let surprisePct: Double?

        init(from decoder: Decoder) throws {
            enum K: String, CodingKey { case period, reported, eps, estimate; case surprisePct = "surprise_pct" }
            let c = try decoder.container(keyedBy: K.self)
            period = c.lenientString(.period) ?? "—"
            reported = c.lenientString(.reported)
            eps = c.lenientDouble(.eps)
            estimate = c.lenientDouble(.estimate)
            surprisePct = c.lenientDouble(.surprisePct)
        }
    }

    let nextDate: String?
    let nextEstimated: Bool
    let past: [Print]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case past; case nextDate = "next_date", nextEstimated = "next_estimated" }
        let c = try decoder.container(keyedBy: K.self)
        nextDate = c.lenientString(.nextDate)
        nextEstimated = (try? c.decodeIfPresent(Bool.self, forKey: .nextEstimated)) ?? false
        past = (try? c.decodeIfPresent([Print].self, forKey: .past)) ?? []
    }
}

// MARK: - Peers (relative performance)

struct MacPeerRow: Decodable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let name: String?
    let sector: String?
    let last: Double?
    let change1d: Double?
    let ret1m: Double?
    let retYtd: Double?
    let ret1y: Double?
    let drawdown1y: Double?
    let high1y: Double?
    let low1y: Double?
    let marketCap: Double?
    let peRatio: Double?
    let revenueGrowth: Double?
    let grossMargin: Double?
    let operatingMargin: Double?
    let spark: [Double]
    let points: [MacChartPoint]
    let vsSpy1m: Double?
    let vsSpy1y: Double?

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey {
            case ticker, name, sector, last, spark, points
            case change1d = "change_1d", ret1m = "ret_1m", retYtd = "ret_ytd", ret1y = "ret_1y"
            case drawdown1y = "drawdown_1y", high1y = "high_1y", low1y = "low_1y"
            case marketCap = "market_cap", peRatio = "pe_ratio", revenueGrowth = "revenue_growth"
            case grossMargin = "gross_margin", operatingMargin = "operating_margin"
            case vsSpy1m = "vs_spy_1m", vsSpy1y = "vs_spy_1y"
        }
        let c = try decoder.container(keyedBy: K.self)
        ticker = c.lenientString(.ticker) ?? "—"
        name = c.lenientString(.name)
        sector = c.lenientString(.sector)
        last = c.lenientDouble(.last)
        change1d = c.lenientDouble(.change1d)
        ret1m = c.lenientDouble(.ret1m)
        retYtd = c.lenientDouble(.retYtd)
        ret1y = c.lenientDouble(.ret1y)
        drawdown1y = c.lenientDouble(.drawdown1y)
        high1y = c.lenientDouble(.high1y)
        low1y = c.lenientDouble(.low1y)
        marketCap = c.lenientDouble(.marketCap)
        peRatio = c.lenientDouble(.peRatio)
        revenueGrowth = c.lenientDouble(.revenueGrowth)
        grossMargin = c.lenientDouble(.grossMargin)
        operatingMargin = c.lenientDouble(.operatingMargin)
        spark = ((try? c.decodeIfPresent([Double?].self, forKey: .spark)) ?? []).compactMap { $0 }
        points = (try? c.decodeIfPresent([MacChartPoint].self, forKey: .points)) ?? []
        vsSpy1m = c.lenientDouble(.vsSpy1m)
        vsSpy1y = c.lenientDouble(.vsSpy1y)
    }
}

struct MacQuotePeers: Decodable {
    let primary: MacPeerRow?
    let benchmark: MacPeerRow?
    let peers: [MacPeerRow]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case primary, benchmark, peers }
        let c = try decoder.container(keyedBy: K.self)
        primary = try? c.decodeIfPresent(MacPeerRow.self, forKey: .primary)
        benchmark = try? c.decodeIfPresent(MacPeerRow.self, forKey: .benchmark)
        peers = (try? c.decodeIfPresent([MacPeerRow].self, forKey: .peers)) ?? []
    }
}

// MARK: - Calendar

struct MacCalendarEvent: Decodable, Identifiable {
    let id = UUID()
    let ticker: String?
    let name: String?
    let date: String
    let time: String?
    let kind: String
    let title: String
    let confirmed: Bool

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case ticker, name, date, time, kind, title, confirmed }
        let c = try decoder.container(keyedBy: K.self)
        ticker = c.lenientString(.ticker)
        name = c.lenientString(.name)
        date = c.lenientString(.date) ?? ""
        time = c.lenientString(.time)
        kind = c.lenientString(.kind) ?? "event"
        title = c.lenientString(.title) ?? ""
        confirmed = (try? c.decodeIfPresent(Bool.self, forKey: .confirmed)) ?? false
    }
}

struct MacQuoteCalendar: Decodable {
    let events: [MacCalendarEvent]

    init(from decoder: Decoder) throws {
        enum K: String, CodingKey { case events }
        let c = try decoder.container(keyedBy: K.self)
        events = (try? c.decodeIfPresent([MacCalendarEvent].self, forKey: .events)) ?? []
    }
}
