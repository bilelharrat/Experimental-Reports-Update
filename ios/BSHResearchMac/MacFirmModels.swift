import Foundation

// MARK: - Firm search

struct MacSearchHit: Identifiable, Decodable {
    var id: String { "\(position)-\(kind)-\(companyId ?? "")-\(ref)-\(chunk ?? -1)" }
    var position = 0
    let kind: String
    let title: String
    let companyId: String?
    let ref: String
    let at: String?
    let score: Double
    let excerpt: String
    let verdict: String?
    let channel: String?
    let chunk: Int?

    enum CodingKeys: String, CodingKey {
        case kind, title, ref, at, score, excerpt, verdict, channel, chunk
        case companyId = "company_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = (try? c.decodeIfPresent(String.self, forKey: .kind)) ?? "doc"
        title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? ""
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        ref = (try? c.decodeIfPresent(String.self, forKey: .ref)) ?? ""
        at = try? c.decodeIfPresent(String.self, forKey: .at)
        score = (try? c.decodeIfPresent(Double.self, forKey: .score)) ?? 0
        excerpt = (try? c.decodeIfPresent(String.self, forKey: .excerpt)) ?? ""
        verdict = try? c.decodeIfPresent(String.self, forKey: .verdict)
        channel = try? c.decodeIfPresent(String.self, forKey: .channel)
        chunk = try? c.decodeIfPresent(Int.self, forKey: .chunk)
    }

    var kindLabel: String {
        switch kind {
        case "reference_call": return "Reference"
        case "founder_update": return "Founder update"
        case "retrospective": return "Retro"
        default: return kind.capitalized
        }
    }

    var systemImage: String {
        switch kind {
        case "company": return "building.2"
        case "decision", "retrospective": return "checkmark.seal"
        case "memo": return "doc.text"
        case "reference_call": return "phone"
        case "founder_update": return "envelope"
        case "comment": return "text.bubble"
        case "chat": return "bubble.left.and.bubble.right"
        case "transcript", "highlight": return "waveform"
        default: return "doc"
        }
    }
}

struct MacFirmSearch: Decodable {
    let query: String
    let items: [MacSearchHit]
    let total: Int
    let kinds: [String]

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case query, items, total, kinds }
        let c = try decoder.container(keyedBy: Keys.self)
        query = (try? c.decodeIfPresent(String.self, forKey: .query)) ?? ""
        let decoded = (try? c.decodeIfPresent([MacSearchHit].self, forKey: .items)) ?? []
        items = decoded.enumerated().map { offset, hit in
            var numbered = hit
            numbered.position = offset
            return numbered
        }
        total = (try? c.decodeIfPresent(Int.self, forKey: .total)) ?? items.count
        kinds = (try? c.decodeIfPresent([String].self, forKey: .kinds)) ?? []
    }
}

// MARK: - Comments & mentions

struct MacCommentTarget: Hashable, Codable {
    let kind: String
    let ref: String
    let label: String?
}

struct MacComment: Identifiable, Hashable, Decodable {
    let id: String
    let companyId: String?
    let author: String?
    let authorHandle: String
    let text: String
    let mentions: [String]
    let target: MacCommentTarget?
    let parentId: String?
    let createdAt: String?
    let resolvedAt: String?
    let resolvedBy: String?

    enum CodingKeys: String, CodingKey {
        case id, author, text, mentions, target
        case companyId = "company_id"
        case authorHandle = "author_handle"
        case parentId = "parent_id"
        case createdAt = "created_at"
        case resolvedAt = "resolved_at"
        case resolvedBy = "resolved_by"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        author = try? c.decodeIfPresent(String.self, forKey: .author)
        authorHandle = (try? c.decodeIfPresent(String.self, forKey: .authorHandle)) ?? "dev"
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        mentions = (try? c.decodeIfPresent([String].self, forKey: .mentions)) ?? []
        target = try? c.decodeIfPresent(MacCommentTarget.self, forKey: .target)
        parentId = try? c.decodeIfPresent(String.self, forKey: .parentId)
        createdAt = try? c.decodeIfPresent(String.self, forKey: .createdAt)
        resolvedAt = try? c.decodeIfPresent(String.self, forKey: .resolvedAt)
        resolvedBy = try? c.decodeIfPresent(String.self, forKey: .resolvedBy)
    }

    var isResolved: Bool { resolvedAt != nil }
}

struct MacComments: Decodable {
    let items: [MacComment]
    let openCount: Int
    enum CodingKeys: String, CodingKey { case items; case openCount = "open_count" }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = (try? c.decodeIfPresent([MacComment].self, forKey: .items)) ?? []
        openCount = (try? c.decodeIfPresent(Int.self, forKey: .openCount)) ?? items.filter { !$0.isResolved }.count
    }
}

struct MacMention: Identifiable, Decodable {
    let id: String
    let kind: String
    let at: String?
    let from: String?
    let text: String
    let companyId: String?
    let channel: String?
    let resolved: Bool
    let target: MacCommentTarget?

    enum CodingKeys: String, CodingKey {
        case id, kind, at, from, text, channel, resolved, target
        case companyId = "company_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        kind = (try? c.decodeIfPresent(String.self, forKey: .kind)) ?? "comment"
        at = try? c.decodeIfPresent(String.self, forKey: .at)
        from = try? c.decodeIfPresent(String.self, forKey: .from)
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        channel = try? c.decodeIfPresent(String.self, forKey: .channel)
        resolved = (try? c.decodeIfPresent(Bool.self, forKey: .resolved)) ?? false
        target = try? c.decodeIfPresent(MacCommentTarget.self, forKey: .target)
    }
}

struct MacMentions: Decodable {
    let handle: String
    let items: [MacMention]
    let openCount: Int
    enum CodingKeys: String, CodingKey { case handle, items; case openCount = "open_count" }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        handle = (try? c.decodeIfPresent(String.self, forKey: .handle)) ?? "dev"
        items = (try? c.decodeIfPresent([MacMention].self, forKey: .items)) ?? []
        openCount = (try? c.decodeIfPresent(Int.self, forKey: .openCount)) ?? 0
    }
}

// MARK: - Chat

struct MacChatMessage: Identifiable, Hashable, Decodable {
    let id: String
    let channel: String?
    let author: String?
    let authorHandle: String
    let text: String
    let mentions: [String]
    let companyId: String?
    let reportId: String?
    let at: String

    enum CodingKeys: String, CodingKey {
        case id, channel, author, text, mentions, at
        case authorHandle = "author_handle"
        case companyId = "company_id"
        case reportId = "report_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        channel = try? c.decodeIfPresent(String.self, forKey: .channel)
        author = try? c.decodeIfPresent(String.self, forKey: .author)
        authorHandle = (try? c.decodeIfPresent(String.self, forKey: .authorHandle)) ?? "dev"
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        mentions = (try? c.decodeIfPresent([String].self, forKey: .mentions)) ?? []
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        reportId = try? c.decodeIfPresent(String.self, forKey: .reportId)
        at = (try? c.decodeIfPresent(String.self, forKey: .at)) ?? ""
    }
}

struct MacChatChannel: Identifiable, Decodable {
    let id: String
    let label: String
    let kind: String
    let companyId: String?
    let messageCount: Int
    let lastMessage: MacChatMessage?

    enum CodingKeys: String, CodingKey {
        case id, label, kind
        case companyId = "company_id"
        case messageCount = "message_count"
        case lastMessage = "last_message"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        label = (try? c.decodeIfPresent(String.self, forKey: .label)) ?? id
        kind = (try? c.decodeIfPresent(String.self, forKey: .kind)) ?? "firm"
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        messageCount = (try? c.decodeIfPresent(Int.self, forKey: .messageCount)) ?? 0
        lastMessage = try? c.decodeIfPresent(MacChatMessage.self, forKey: .lastMessage)
    }
}

struct MacChatChannels: Decodable {
    let items: [MacChatChannel]
    let handles: [String]
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case items, handles }
        let c = try decoder.container(keyedBy: Keys.self)
        items = (try? c.decodeIfPresent([MacChatChannel].self, forKey: .items)) ?? []
        handles = (try? c.decodeIfPresent([String].self, forKey: .handles)) ?? []
    }
}

struct MacChatPage: Decodable {
    let channel: String
    let items: [MacChatMessage]
    let latest: String?
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case channel, items, latest }
        let c = try decoder.container(keyedBy: Keys.self)
        channel = (try? c.decodeIfPresent(String.self, forKey: .channel)) ?? "general"
        items = (try? c.decodeIfPresent([MacChatMessage].self, forKey: .items)) ?? []
        latest = try? c.decodeIfPresent(String.self, forKey: .latest)
    }
}

// MARK: - Audit

struct MacAuditRow: Identifiable, Hashable, Decodable {
    var id: String { serverId ?? "idx-\(position)-\(at)-\(action)-\(path)-\(actor)" }
    var position = 0
    let serverId: String?
    let at: String
    let actor: String
    let action: String
    let path: String
    let status: Int
    let companyId: String?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case id, at, actor, action, path, status, detail
        case companyId = "company_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let rawId = (try? c.decodeIfPresent(String.self, forKey: .id))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .id)).map(String.init)
        serverId = (rawId?.isEmpty ?? true) ? nil : rawId
        at = (try? c.decodeIfPresent(String.self, forKey: .at)) ?? ""
        actor = (try? c.decodeIfPresent(String.self, forKey: .actor)) ?? "anon-dev"
        action = (try? c.decodeIfPresent(String.self, forKey: .action)) ?? ""
        path = (try? c.decodeIfPresent(String.self, forKey: .path)) ?? ""
        status = (try? c.decodeIfPresent(Int.self, forKey: .status)) ?? 0
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        detail = try? c.decodeIfPresent(String.self, forKey: .detail)
    }
}

struct MacAuditPage: Decodable {
    let items: [MacAuditRow]
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case items }
        let c = try decoder.container(keyedBy: Keys.self)
        let decoded = (try? c.decodeIfPresent([MacAuditRow].self, forKey: .items)) ?? []
        items = decoded.enumerated().map { offset, row in
            var numbered = row
            numbered.position = offset
            return numbered
        }
    }
}

// MARK: - Transcripts

struct MacHighlight: Identifiable, Hashable, Decodable {
    let id: String
    let text: String
    let note: String?
    let createdBy: String?
    let at: String?
    enum CodingKeys: String, CodingKey { case id, text, note, at; case createdBy = "created_by" }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        createdBy = try? c.decodeIfPresent(String.self, forKey: .createdBy)
        at = try? c.decodeIfPresent(String.self, forKey: .at)
    }
}

struct MacTranscript: Identifiable, Decodable {
    let id: String
    let title: String
    let kind: String
    let companyId: String?
    let companyName: String?
    let callDate: String?
    let participants: [String]
    let tags: [String]
    let text: String
    let highlights: [MacHighlight]
    let wordCount: Int
    let highlightCount: Int
    let preview: String?
    let sourceFilename: String?
    let createdBy: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, kind, participants, tags, text, highlights, preview
        case companyId = "company_id"
        case companyName = "company_name"
        case callDate = "call_date"
        case wordCount = "word_count"
        case highlightCount = "highlight_count"
        case sourceFilename = "source_filename"
        case createdBy = "created_by"
        case createdAt = "created_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = (try? c.decodeIfPresent(String.self, forKey: .title)) ?? "Transcript"
        kind = (try? c.decodeIfPresent(String.self, forKey: .kind)) ?? "other"
        companyId = try? c.decodeIfPresent(String.self, forKey: .companyId)
        companyName = try? c.decodeIfPresent(String.self, forKey: .companyName)
        callDate = try? c.decodeIfPresent(String.self, forKey: .callDate)
        participants = (try? c.decodeIfPresent([String].self, forKey: .participants)) ?? []
        tags = (try? c.decodeIfPresent([String].self, forKey: .tags)) ?? []
        text = (try? c.decodeIfPresent(String.self, forKey: .text)) ?? ""
        highlights = (try? c.decodeIfPresent([MacHighlight].self, forKey: .highlights)) ?? []
        let words = try? c.decodeIfPresent(Int.self, forKey: .wordCount)
        wordCount = words ?? text.split(whereSeparator: \.isWhitespace).count
        highlightCount = (try? c.decodeIfPresent(Int.self, forKey: .highlightCount)) ?? highlights.count
        preview = try? c.decodeIfPresent(String.self, forKey: .preview)
        sourceFilename = try? c.decodeIfPresent(String.self, forKey: .sourceFilename)
        createdBy = try? c.decodeIfPresent(String.self, forKey: .createdBy)
        createdAt = try? c.decodeIfPresent(String.self, forKey: .createdAt)
    }

    var kindLabel: String { kind.replacingOccurrences(of: "_", with: " ").capitalized }
}

struct MacTranscriptList: Decodable {
    let items: [MacTranscript]
    let count: Int
    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case items, count }
        let c = try decoder.container(keyedBy: Keys.self)
        items = (try? c.decodeIfPresent([MacTranscript].self, forKey: .items)) ?? []
        count = (try? c.decodeIfPresent(Int.self, forKey: .count)) ?? items.count
    }
}

// MARK: - Signal score

struct MacSignalComponent: Identifiable, Hashable, Decodable {
    var id: String { name }
    let name: String
    let points: Double?
    let max: Int
    let formula: String
    let basis: String
    let available: Bool

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case name, points, max, formula, basis, available }
        let c = try decoder.container(keyedBy: Keys.self)
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? ""
        points = try? c.decodeIfPresent(Double.self, forKey: .points)
        max = (try? c.decodeIfPresent(Int.self, forKey: .max)) ?? 0
        formula = (try? c.decodeIfPresent(String.self, forKey: .formula)) ?? ""
        basis = (try? c.decodeIfPresent(String.self, forKey: .basis)) ?? ""
        available = (try? c.decodeIfPresent(Bool.self, forKey: .available)) ?? false
    }
}

struct MacSignalScore: Decodable {
    let score: Int?
    let provisionalScore: Int?
    let sufficientCoverage: Bool?
    let note: String?
    let points: Double
    let maxAvailable: Int
    let maxPossible: Int
    let coverage: String
    let components: [MacSignalComponent]
    let formula: String

    var isInsufficient: Bool { score == nil && provisionalScore != nil }

    enum CodingKeys: String, CodingKey {
        case score, points, coverage, components, formula, note
        case provisionalScore = "provisional_score"
        case sufficientCoverage = "sufficient_coverage"
        case maxAvailable = "max_available"
        case maxPossible = "max_possible"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        provisionalScore = try? c.decodeIfPresent(Int.self, forKey: .provisionalScore)
        sufficientCoverage = try? c.decodeIfPresent(Bool.self, forKey: .sufficientCoverage)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        points = (try? c.decodeIfPresent(Double.self, forKey: .points)) ?? 0
        maxAvailable = (try? c.decodeIfPresent(Int.self, forKey: .maxAvailable)) ?? 0
        maxPossible = (try? c.decodeIfPresent(Int.self, forKey: .maxPossible)) ?? 100
        coverage = (try? c.decodeIfPresent(String.self, forKey: .coverage)) ?? ""
        components = (try? c.decodeIfPresent([MacSignalComponent].self, forKey: .components)) ?? []
        formula = (try? c.decodeIfPresent(String.self, forKey: .formula)) ?? ""
    }
}
