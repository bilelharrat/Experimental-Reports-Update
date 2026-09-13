import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case http(status: Int, detail: String)
    case decoding(Error)
    case transport(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid API URL"
        case .unauthorized: return "Signed out — please sign in again"
        case .http(_, let detail): return detail
        case .decoding(let err): return "Bad response: \(err.localizedDescription)"
        case .transport(let err): return err.localizedDescription
        }
    }
}

/// Thin async HTTP client. Bearer auth; snake_case JSON.
actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(session: URLSession = .shared) {
        self.session = session
        let decoder = JSONDecoder()
        // Prefer camelCase CodingKeys on models — avoid convertFromSnakeCase
        // (it breaks nested trader CodingKeys; see docs/ios-app-implementation.md §17).
        self.decoder = decoder
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await request(path, method: "GET", query: query)
    }

    nonisolated func getCached<T: Decodable>(_ path: String, query: [URLQueryItem] = []) -> T? {
        let key = APIResponseCache.cacheKey(path: path, query: query)
        guard let data = APIResponseCache.shared.load(for: key) else { return nil }
        let decoder = JSONDecoder()
        return try? decoder.decode(T.self, from: data)
    }

    func post<Body: Encodable, T: Decodable>(_ path: String, body: Body, timeout: TimeInterval? = nil) async throws -> T {
        try await request(path, method: "POST", body: body, timeout: timeout)
    }

    func post<T: Decodable>(_ path: String, query: [URLQueryItem] = [], timeout: TimeInterval? = nil) async throws -> T {
        try await request(path, method: "POST", query: query, body: Optional<String>.none, timeout: timeout)
    }

    /// Multipart POST (Console ask: `prompt` field + optional `images[]`).
    func postMultipart<T: Decodable>(
        _ path: String,
        fields: [String: String],
        files: [(field: String, name: String, mime: String, data: Data)] = []
    ) async throws -> T {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        var components = URLComponents(url: AppConfig.apiRoot, resolvingAgainstBaseURL: false)!
        let root = AppConfig.apiRoot.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [root, trimmed].filter { !$0.isEmpty }.joined(separator: "/")
        guard let url = components.url else { throw APIError.invalidURL }

        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        func append(_ s: String) { body.append(Data(s.utf8)) }
        for (name, value) in fields {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            append("\(value)\r\n")
        }
        for f in files {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(f.field)\"; filename=\"\(f.name)\"\r\n")
            append("Content-Type: \(f.mime)\r\n\r\n")
            body.append(f.data)
            append("\r\n")
        }
        append("--\(boundary)--\r\n")

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 120
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("ios", forHTTPHeaderField: "X-BSH-Client")
        if let token = TokenStore.read() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = body

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.http(status: -1, detail: "No HTTP response")
        }
        if http.statusCode == 401 {
            TokenStore.clear()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(status: http.statusCode, detail: Self.detail(from: data, status: http.statusCode))
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    func put<Body: Encodable, T: Decodable>(_ path: String, body: Body) async throws -> T {
        try await request(path, method: "PUT", body: body)
    }

    func postEmpty(_ path: String) async throws {
        let _: Empty = try await request(path, method: "POST", body: Optional<String>.none)
    }

    func delete(_ path: String) async throws {
        let _: Empty = try await request(path, method: "DELETE", body: Optional<String>.none)
    }

    func download(_ path: String) async throws -> (Data, String?) {
        let url: URL
        if path.hasPrefix("http") {
            guard let remote = URL(string: path) else { throw APIError.invalidURL }
            url = remote
        } else {
            let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            var components = URLComponents(url: AppConfig.baseURL, resolvingAgainstBaseURL: false)!
            if let qIndex = trimmed.firstIndex(of: "?") {
                components.path = "/" + String(trimmed[..<qIndex])
                components.query = String(trimmed[trimmed.index(after: qIndex)...])
            } else {
                components.path = "/" + trimmed
            }
            guard let built = components.url else { throw APIError.invalidURL }
            url = built
        }

        var req = URLRequest(url: url)
        req.setValue("ios", forHTTPHeaderField: "X-BSH-Client")
        if let token = TokenStore.read() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.http(status: -1, detail: "No HTTP response")
        }
        if http.statusCode == 401 {
            TokenStore.clear()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(status: http.statusCode, detail: Self.detail(from: data, status: http.statusCode))
        }
        let name = http.value(forHTTPHeaderField: "Content-Disposition")
            .flatMap { disposition -> String? in
                if let starRange = disposition.range(of: "filename*=", options: .caseInsensitive) {
                    let raw = disposition[starRange.upperBound...]
                        .trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
                    if let quoteIdx = raw.range(of: "''") {
                        let encName = String(raw[quoteIdx.upperBound...])
                        return encName.removingPercentEncoding ?? encName
                    }
                    return raw.removingPercentEncoding ?? raw
                }
                guard let range = disposition.range(of: "filename=", options: .caseInsensitive) else { return nil }
                return disposition[range.upperBound...]
                    .components(separatedBy: ";").first?
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
            }
        return (data, name)
    }

    private func request<T: Decodable>(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        timeout: TimeInterval? = nil
    ) async throws -> T {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard var components = URLComponents(url: AppConfig.apiRoot, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidURL
        }
        let rootPath = AppConfig.apiRoot.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [rootPath, trimmed].filter { !$0.isEmpty }.joined(separator: "/")
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.invalidURL }

        var req = URLRequest(url: url)
        req.httpMethod = method
        if let timeout { req.timeoutInterval = timeout }
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("ios", forHTTPHeaderField: "X-BSH-Client")
        if let token = TokenStore.read() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try encoder.encode(AnyEncodable(body))
        }

        let cacheKey = APIResponseCache.cacheKey(path: path, query: query)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            if method == "GET", let cached = APIResponseCache.shared.load(for: cacheKey) {
                if T.self == Empty.self { return Empty() as! T }
                if let decoded = try? decoder.decode(T.self, from: cached) {
                    return decoded
                }
            }
            throw APIError.transport(error)
        }
        guard let http = response as? HTTPURLResponse else {
            throw APIError.http(status: -1, detail: "No HTTP response")
        }
        if http.statusCode == 401 {
            TokenStore.clear()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            if method == "GET", let cached = APIResponseCache.shared.load(for: cacheKey) {
                if T.self == Empty.self { return Empty() as! T }
                if let decoded = try? decoder.decode(T.self, from: cached) {
                    return decoded
                }
            }
            throw APIError.http(status: http.statusCode, detail: Self.detail(from: data, status: http.statusCode))
        }
        if method == "GET" {
            APIResponseCache.shared.save(data: data, for: cacheKey)
        }
        if T.self == Empty.self {
            return Empty() as! T
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private static func detail(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = obj["detail"] as? String { return detail }
            if let detail = obj["detail"] as? [String: Any],
               let message = detail["message"] as? String { return message }
        }
        if let text = String(data: data, encoding: .utf8), !text.isEmpty { return text }
        return "HTTP \(status)"
    }
}

private struct Empty: Decodable {}

private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ value: any Encodable) {
        encodeFunc = { try value.encode(to: $0) }
    }
    func encode(to encoder: Encoder) throws { try encodeFunc(encoder) }
}
