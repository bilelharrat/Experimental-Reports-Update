import Foundation

struct ConsoleSession: Decodable, Identifiable {
    let id: String
    let companyId: String?
    let model: String?
    let status: String?          // "active" | "archived"
    let title: String?
    let createdAt: String?
    let lastUsedAt: String?
    let archivedAt: String?
    let outputLanguage: String?
    let hydrationStatus: String?
    let pctUsed: Double?
    let contextUsed: Int?
    let contextWindow: Int?

    enum CodingKeys: String, CodingKey {
        case id, model, status, title
        case companyId = "company_id"
        case createdAt = "created_at"
        case lastUsedAt = "last_used_at"
        case archivedAt = "archived_at"
        case outputLanguage = "output_language"
        case hydrationStatus = "hydration_status"
        case pctUsed = "pct_used"
        case contextUsed = "context_used"
        case contextWindow = "context_window"
    }

    var isArchived: Bool { (status ?? "") == "archived" }
}

struct ConsoleTurn: Decodable, Identifiable {
    let id: String
    let ts: String?
    let role: String?            // "user" | "assistant"
    let text: String?
    let subtype: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id, ts, role, text, subtype, error
    }

    var isUser: Bool { (role ?? "") == "user" }
}

struct ConsoleCreateBody: Encodable {
    let includeBackgroundDocs: Bool
    let includeLibraryDocs: Bool
    let outputLanguage: String

    enum CodingKeys: String, CodingKey {
        case includeBackgroundDocs = "include_background_docs"
        case includeLibraryDocs = "include_library_docs"
        case outputLanguage = "output_language"
    }
}

struct ConsoleAskResponse: Decodable {
    let turnId: String
    let queuePosition: Int?
    let streamUrl: String?

    enum CodingKeys: String, CodingKey {
        case turnId = "turn_id"
        case queuePosition = "queue_position"
        case streamUrl = "stream_url"
    }
}
