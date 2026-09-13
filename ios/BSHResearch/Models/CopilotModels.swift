import Foundation

struct CopilotContextBody: Encodable {
    var surface: String?
    var tab: String?
    var selection: [String: JSONValue] = [:]
    var attention: [String: JSONValue] = [:]
    var job: [String: JSONValue] = [:]
    var documentIds: [String] = []

    enum CodingKeys: String, CodingKey {
        case surface, tab, selection, attention, job
        case documentIds = "document_ids"
    }
}

struct CopilotAskBody: Encodable {
    let prompt: String
    var context: CopilotContextBody = CopilotContextBody()
    var outputLanguage: String = "en"
    var mode: String = "quick"

    enum CodingKeys: String, CodingKey {
        case prompt, context, mode
        case outputLanguage = "output_language"
    }
}

struct CopilotAction: Decodable, Identifiable, Hashable {
    let id: String
    let labelKey: String?
    let promptKey: String?

    enum CodingKeys: String, CodingKey {
        case id
        case labelKey = "label_key"
        case promptKey = "prompt_key"
    }
}

struct CopilotProactive: Decodable, Identifiable, Hashable {
    var id: String { actionId ?? labelKey ?? UUID().uuidString }
    let kind: String?
    let actionId: String?
    let labelKey: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case actionId = "action_id"
        case labelKey = "label_key"
    }
}

struct CopilotSessionRef: Decodable {
    let id: String?
    let hydrationStatus: String?
    let title: String?

    enum CodingKeys: String, CodingKey {
        case id, title
        case hydrationStatus = "hydration_status"
    }
}

struct CopilotContextResponse: Decodable {
    let companyId: String?
    let label: String?
    let surface: String?
    let tab: String?
    let actions: [CopilotAction]?
    let proactive: [CopilotProactive]?
    let autoPrompt: String?
    let session: CopilotSessionRef?
    let deepSession: CopilotSessionRef?

    enum CodingKeys: String, CodingKey {
        case label, surface, tab, actions, proactive, session
        case companyId = "company_id"
        case autoPrompt = "auto_prompt"
        case deepSession = "deep_session"
    }
}

struct CopilotAskResponse: Decodable {
    let mode: String?
    let sessionId: String?
    let turnId: String?
    let queuePosition: Int?
    let streamUrl: String?
    let hydrationStatus: String?
    let hydrateStreamUrl: String?

    enum CodingKeys: String, CodingKey {
        case mode
        case sessionId = "session_id"
        case turnId = "turn_id"
        case queuePosition = "queue_position"
        case streamUrl = "stream_url"
        case hydrationStatus = "hydration_status"
        case hydrateStreamUrl = "hydrate_stream_url"
    }
}

/// Lightweight JSON bag for nested context maps.
enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Double.self) {
            self = .number(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([String: JSONValue].self) {
            self = .object(v)
        } else if let v = try? container.decode([JSONValue].self) {
            self = .array(v)
        } else {
            self = .null
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .number(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }
}

struct CopilotMessage: Identifiable, Equatable {
    let id: String
    let role: Role
    var text: String
    var sources: [AskSourceChip] = []

    enum Role: Equatable {
        case user
        case assistant
    }
}
