import Foundation

// The website's Settings page reads three things, and the Mac's Settings (under Bureau, laid
// out as the website's) reads the same: the workspace settings (preferences, the account and
// Warren's engine), the user center (the team, usage and system status) and the fund
// return policy.

/// `GET /api/workspace/settings`.
struct MacWorkspaceSettings: Decodable {
    struct Account: Decodable {
        let name: String?
        let email: String?
        let workspace: String?
        let role: String?
        let plan: String?
        let auth: String?
        let permissions: [String]?
    }

    struct Preferences: Decodable {
        let weeklySummary: Bool?
        let stockAutoRefresh: Bool?
        let agentAlerts: Bool?
        let compactDensity: Bool?
        let language: String?
        let memoParallelRuns: Int?
        let memoTemplate: String?
        let memoTemplateEffective: String?
        let researchEngine: String?
        let warrenEngine: String?

        enum CodingKeys: String, CodingKey {
            case weeklySummary = "weekly_summary"
            case stockAutoRefresh = "stock_auto_refresh"
            case agentAlerts = "agent_alerts"
            case compactDensity = "compact_density"
            case language
            case memoParallelRuns = "memo_parallel_runs"
            case memoTemplate = "memo_template"
            case memoTemplateEffective = "memo_template_effective"
            case researchEngine = "research_engine"
            case warrenEngine = "warren_engine"
        }
    }

    struct Warren: Decodable {
        let engine: String?
        let geminiAvailable: Bool?
        let geminiModel: String?
        let claudeAvailable: Bool?
        let claudeResting: String?

        enum CodingKeys: String, CodingKey {
            case engine
            case geminiAvailable = "gemini_available"
            case geminiModel = "gemini_model"
            case claudeAvailable = "claude_available"
            case claudeResting = "claude_resting"
        }
    }

    let account: Account?
    let preferences: Preferences?
    let adapterScope: String?
    let memoTemplate: String?
    let memoTemplateEffective: String?
    let warren: Warren?

    enum CodingKeys: String, CodingKey {
        case account, preferences, warren
        case adapterScope = "adapter_scope"
        case memoTemplate = "memo_template"
        case memoTemplateEffective = "memo_template_effective"
    }
}

/// `GET /api/workspace/user-center`.
struct MacUserCenter: Decodable {
    struct Team: Decodable {
        let licensedSeats: Int?
        let activeUsers: Int?

        enum CodingKeys: String, CodingKey {
            case licensedSeats = "licensed_seats"
            case activeUsers = "active_users"
        }
    }

    struct Usage: Decodable {
        let analyticsEvents: Int?

        enum CodingKeys: String, CodingKey {
            case analyticsEvents = "analytics_events"
        }
    }

    let account: MacWorkspaceSettings.Account?
    let team: Team?
    let usage: Usage?
    /// The system's status lines, in the server's order, each value as text.
    let status: [(key: String, value: String)]

    enum CodingKeys: String, CodingKey {
        case account, team, usage, status
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        account = try c.decodeIfPresent(MacWorkspaceSettings.Account.self, forKey: .account)
        team = try? c.decodeIfPresent(Team.self, forKey: .team)
        usage = try? c.decodeIfPresent(Usage.self, forKey: .usage)
        status = (try? c.decodeIfPresent(MacLooseObject.self, forKey: .status))?.pairs ?? []
    }
}

/// A JSON object read as text pairs, in order, whatever its values' types.
struct MacLooseObject: Decodable {
    let pairs: [(key: String, value: String)]

    private struct Key: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        pairs = c.allKeys.compactMap { key in
            if let s = try? c.decode(String.self, forKey: key) { return (key.stringValue, s) }
            if let b = try? c.decode(Bool.self, forKey: key) { return (key.stringValue, b ? "true" : "false") }
            if let i = try? c.decode(Int.self, forKey: key) { return (key.stringValue, String(i)) }
            if let d = try? c.decode(Double.self, forKey: key) { return (key.stringValue, String(d)) }
            return nil
        }
    }
}

/// `GET /api/settings/fund-policy`: the return each stage's memos answer to.
struct MacFundPolicy: Decodable {
    struct Stage: Codable, Equatable {
        var targetMoic: Double?
        var targetIrrPct: Double?
        var maxHoldYears: Double?
        var maxPositionPct: Double?
        var basis: String?

        enum CodingKeys: String, CodingKey {
            case targetMoic = "target_moic"
            case targetIrrPct = "target_irr_pct"
            case maxHoldYears = "max_hold_years"
            case maxPositionPct = "max_position_pct"
            case basis
        }
    }

    struct Context: Decodable {
        let fundSizeMusd: Double?
        let checkSizeMinMusd: Double?
        let checkSizeMaxMusd: Double?

        enum CodingKeys: String, CodingKey {
            case fundSizeMusd = "fund_size_musd"
            case checkSizeMinMusd = "check_size_min_musd"
            case checkSizeMaxMusd = "check_size_max_musd"
        }
    }

    let isSet: Bool?
    let stages: [String: Stage]
    let updatedAt: String?
    let updatedBy: String?
    let context: Context?

    enum CodingKeys: String, CodingKey {
        case isSet = "set"
        case stages
        case updatedAt = "updated_at"
        case updatedBy = "updated_by"
        case context
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        isSet = try c.decodeIfPresent(Bool.self, forKey: .isSet)
        // A stage the policy leaves open is null.
        let raw = try c.decodeIfPresent([String: Stage?].self, forKey: .stages) ?? [:]
        stages = raw.compactMapValues { $0 }
        updatedAt = try c.decodeIfPresent(String.self, forKey: .updatedAt)
        updatedBy = try c.decodeIfPresent(String.self, forKey: .updatedBy)
        context = try c.decodeIfPresent(Context.self, forKey: .context)
    }
}

/// `PUT /api/settings/fund-policy`'s body: every stage, a null one cleared.
struct MacFundPolicyUpdate: Encodable {
    let stages: [String: MacFundPolicy.Stage?]

    private struct Key: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    func encode(to encoder: Encoder) throws {
        var root = encoder.container(keyedBy: Key.self)
        var nested = root.nestedContainer(keyedBy: Key.self, forKey: Key(stringValue: "stages"))
        for (stage, entry) in stages {
            if let entry {
                try nested.encode(entry, forKey: Key(stringValue: stage))
            } else {
                try nested.encodeNil(forKey: Key(stringValue: stage))
            }
        }
    }
}
