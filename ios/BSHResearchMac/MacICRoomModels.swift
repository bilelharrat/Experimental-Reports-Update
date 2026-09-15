import Foundation

// MARK: - Reference calls

struct MacReferenceCall: Identifiable, Hashable, Decodable {
    let id: String
    let contact: String
    let role: String?
    let relation: String
    let callDate: String?
    let strengths: [String]
    let concerns: [String]
    let quotes: [String]
    let rating: Int?
    let wouldBackAgain: Bool?
    let notes: String?
    let createdBy: String?

    enum CodingKeys: String, CodingKey {
        case id, contact, role, relation, strengths, concerns, quotes, rating, notes
        case callDate = "call_date"
        case wouldBackAgain = "would_back_again"
        case createdBy = "created_by"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        contact = (try? c.decodeIfPresent(String.self, forKey: .contact)) ?? "Contact"
        role = try? c.decodeIfPresent(String.self, forKey: .role)
        relation = (try? c.decodeIfPresent(String.self, forKey: .relation)) ?? "other"
        callDate = try? c.decodeIfPresent(String.self, forKey: .callDate)
        strengths = (try? c.decodeIfPresent([String].self, forKey: .strengths)) ?? []
        concerns = (try? c.decodeIfPresent([String].self, forKey: .concerns)) ?? []
        quotes = (try? c.decodeIfPresent([String].self, forKey: .quotes)) ?? []
        rating = try? c.decodeIfPresent(Int.self, forKey: .rating)
        wouldBackAgain = try? c.decodeIfPresent(Bool.self, forKey: .wouldBackAgain)
        notes = try? c.decodeIfPresent(String.self, forKey: .notes)
        createdBy = try? c.decodeIfPresent(String.self, forKey: .createdBy)
    }

    var relationLabel: String {
        switch relation {
        case "customer": return "Customer"
        case "former_employee": return "Former employee"
        case "investor": return "Investor"
        case "partner": return "Partner"
        case "founder_peer": return "Founder peer"
        default: return "Other"
        }
    }
}

struct MacReferenceCalls: Decodable {
    let items: [MacReferenceCall]
    let count: Int
    let averageRating: Double?
    let concernCount: Int

    enum CodingKeys: String, CodingKey {
        case items, count
        case averageRating = "average_rating"
        case concernCount = "concern_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = (try? c.decodeIfPresent([MacReferenceCall].self, forKey: .items)) ?? []
        count = (try? c.decodeIfPresent(Int.self, forKey: .count)) ?? items.count
        averageRating = try? c.decodeIfPresent(Double.self, forKey: .averageRating)
        concernCount = (try? c.decodeIfPresent(Int.self, forKey: .concernCount)) ?? 0
    }
}

// MARK: - IC meetings & votes

struct MacICVote: Identifiable, Hashable, Decodable {
    var id: String { member }
    let member: String
    let memberName: String?
    let vote: String
    let conviction: Int?
    let note: String?
    let at: String?

    var displayName: String {
        if let memberName, !memberName.isEmpty { return memberName }
        return member
    }

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case member, vote, conviction, note, at, memberName = "member_name" }
        let c = try decoder.container(keyedBy: Keys.self)
        member = (try? c.decodeIfPresent(String.self, forKey: .member)) ?? "?"
        memberName = try? c.decodeIfPresent(String.self, forKey: .memberName)
        vote = (try? c.decodeIfPresent(String.self, forKey: .vote)) ?? "more_work"
        conviction = try? c.decodeIfPresent(Int.self, forKey: .conviction)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        at = try? c.decodeIfPresent(String.self, forKey: .at)
    }

    var label: String { vote == "invest" ? "Invest" : (vote == "pass" ? "Pass" : "More work") }
}

struct MacICTally: Decodable {
    let invest: Int
    let pass: Int
    let moreWork: Int
    let total: Int
    let leading: String?
    let majority: String?
    let tied: Bool
    let averageConviction: Double?

    enum CodingKeys: String, CodingKey {
        case invest, pass, total, leading, tied, majority
        case moreWork = "more_work"
        case averageConviction = "average_conviction"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        invest = (try? c.decodeIfPresent(Int.self, forKey: .invest)) ?? 0
        pass = (try? c.decodeIfPresent(Int.self, forKey: .pass)) ?? 0
        moreWork = (try? c.decodeIfPresent(Int.self, forKey: .moreWork)) ?? 0
        total = (try? c.decodeIfPresent(Int.self, forKey: .total)) ?? 0
        leading = try? c.decodeIfPresent(String.self, forKey: .leading)
        majority = try? c.decodeIfPresent(String.self, forKey: .majority)
        tied = (try? c.decodeIfPresent(Bool.self, forKey: .tied)) ?? false
        averageConviction = try? c.decodeIfPresent(Double.self, forKey: .averageConviction)
    }
}

struct MacICMeeting: Identifiable, Decodable {
    let id: String
    let title: String
    let scheduledAt: String?
    let reportId: String?
    let status: String
    let createdAt: String?
    let closedAt: String?
    let votes: [MacICVote]
    let tally: MacICTally?
    let decisionId: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, votes, tally
        case scheduledAt = "scheduled_at"
        case reportId = "report_id"
        case createdAt = "created_at"
        case closedAt = "closed_at"
        case decisionId = "decision_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? "IC"
        scheduledAt = try? c.decodeIfPresent(String.self, forKey: .scheduledAt)
        reportId = try? c.decodeIfPresent(String.self, forKey: .reportId)
        status = (try? c.decodeIfPresent(String.self, forKey: .status)) ?? "open"
        createdAt = try? c.decodeIfPresent(String.self, forKey: .createdAt)
        closedAt = try? c.decodeIfPresent(String.self, forKey: .closedAt)
        votes = (try? c.decodeIfPresent([MacICVote].self, forKey: .votes)) ?? []
        tally = try? c.decodeIfPresent(MacICTally.self, forKey: .tally)
        decisionId = try? c.decodeIfPresent(String.self, forKey: .decisionId)
    }

    var isOpen: Bool { status == "open" }
}

struct MacICMeetings: Decodable {
    let items: [MacICMeeting]
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case items }
        let c = try decoder.container(keyedBy: Keys.self)
        items = (try? c.decodeIfPresent([MacICMeeting].self, forKey: .items)) ?? []
    }
}

// MARK: - Comparable past decisions

struct MacComparableDecision: Identifiable, Decodable {
    var id: String { companyId }
    let companyId: String
    let companyName: String
    let score: Int
    let why: [String]
    let verdict: String?
    let decidedAt: String?
    let explanation: String?
    let retroVerdict: String?
    let retroNote: String?
    let decisionCount: Int

    private struct Decision: Decodable { let verdict: String?; let decided_at: String?; let explanation: String? }
    private struct Retro: Decodable { let verdict: String?; let note: String? }

    enum CodingKeys: String, CodingKey {
        case score, why, decision, retrospective
        case companyId = "company_id"
        case companyName = "company_name"
        case decisionCount = "decision_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        companyId = try c.decode(String.self, forKey: .companyId)
        companyName = (try? c.decodeIfPresent(String.self, forKey: .companyName)) ?? companyId
        score = (try? c.decodeIfPresent(Int.self, forKey: .score)) ?? 0
        why = (try? c.decodeIfPresent([String].self, forKey: .why)) ?? []
        let d = try? c.decodeIfPresent(Decision.self, forKey: .decision)
        verdict = d?.verdict
        decidedAt = d?.decided_at
        explanation = d?.explanation
        let r = try? c.decodeIfPresent(Retro.self, forKey: .retrospective)
        retroVerdict = r?.verdict
        retroNote = r?.note
        decisionCount = (try? c.decodeIfPresent(Int.self, forKey: .decisionCount)) ?? 1
    }
}

struct MacComparables: Decodable {
    let items: [MacComparableDecision]
    let basis: String?
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case items, basis }
        let c = try decoder.container(keyedBy: Keys.self)
        items = (try? c.decodeIfPresent([MacComparableDecision].self, forKey: .items)) ?? []
        basis = try? c.decodeIfPresent(String.self, forKey: .basis)
    }
}

// MARK: - Red-team memo

struct MacKillRisk: Identifiable, Hashable, Decodable {
    var id: String { risk }
    let risk: String
    let why: String
    let severity: String
    let evidenceNeeded: String
    let memoSection: String?

    enum CodingKeys: String, CodingKey {
        case risk, why, severity
        case evidenceNeeded = "evidence_needed"
        case memoSection = "memo_section"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        risk = (try? c.decodeIfPresent(String.self, forKey: .risk)) ?? ""
        why = (try? c.decodeIfPresent(String.self, forKey: .why)) ?? ""
        severity = (try? c.decodeIfPresent(String.self, forKey: .severity)) ?? "medium"
        evidenceNeeded = (try? c.decodeIfPresent(String.self, forKey: .evidenceNeeded)) ?? ""
        memoSection = try? c.decodeIfPresent(String.self, forKey: .memoSection)
    }
}

struct MacRedTeamResult: Decodable {
    let counterThesis: String
    let killRisks: [MacKillRisk]
    let questionableAssumptions: [String]
    let whatWouldChangeMyMind: [String]
    let preMortem: String
    let questionsForFounders: [String]

    enum CodingKeys: String, CodingKey {
        case counterThesis = "counter_thesis"
        case killRisks = "kill_risks"
        case questionableAssumptions = "questionable_assumptions"
        case whatWouldChangeMyMind = "what_would_change_my_mind"
        case preMortem = "pre_mortem"
        case questionsForFounders = "questions_for_founders"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        counterThesis = (try? c.decodeIfPresent(String.self, forKey: .counterThesis)) ?? ""
        killRisks = (try? c.decodeIfPresent([MacKillRisk].self, forKey: .killRisks)) ?? []
        questionableAssumptions = (try? c.decodeIfPresent([String].self, forKey: .questionableAssumptions)) ?? []
        whatWouldChangeMyMind = (try? c.decodeIfPresent([String].self, forKey: .whatWouldChangeMyMind)) ?? []
        preMortem = (try? c.decodeIfPresent(String.self, forKey: .preMortem)) ?? ""
        questionsForFounders = (try? c.decodeIfPresent([String].self, forKey: .questionsForFounders)) ?? []
    }
}

struct MacRedTeam: Decodable {
    let status: String
    let generatedAt: String?
    let error: String?
    let result: MacRedTeamResult?
    let memoBlocksUsed: Int
    let referenceConcerns: Int

    private struct Provenance: Decodable { let memo_blocks_used: Int?; let reference_concerns: Int? }

    enum CodingKeys: String, CodingKey {
        case status, error, result, provenance
        case generatedAt = "generated_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = (try? c.decodeIfPresent(String.self, forKey: .status)) ?? "none"
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        error = try? c.decodeIfPresent(String.self, forKey: .error)
        result = try? c.decodeIfPresent(MacRedTeamResult.self, forKey: .result)
        let p = try? c.decodeIfPresent(Provenance.self, forKey: .provenance)
        memoBlocksUsed = p?.memo_blocks_used ?? 0
        referenceConcerns = p?.reference_concerns ?? 0
    }

    var isRunning: Bool { status == "running" || status == "queued" }
}
