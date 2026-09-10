import Foundation

/// Minimal Server-Sent Events client. Sends Bearer auth (query tokens are gone).
actor SSEClient {
    struct Event: Sendable {
        let event: String?
        let data: String
    }

    enum StreamError: Error, LocalizedError {
        case invalidURL
        case badStatus(Int)
        case cancelled

        var errorDescription: String? {
            switch self {
            case .invalidURL: return "Invalid stream URL"
            case .badStatus(let code): return "Stream HTTP \(code)"
            case .cancelled: return "Stream cancelled"
            }
        }
    }

    func stream(path: String) -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await self.run(path: path, continuation: continuation)
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func run(
        path: String,
        continuation: AsyncThrowingStream<Event, Error>.Continuation
    ) async throws {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        // Paths may be absolute API paths like "/api/memos/.../stream"
        let url: URL
        if trimmed.hasPrefix("api/") {
            var components = URLComponents(url: AppConfig.baseURL, resolvingAgainstBaseURL: false)!
            components.path = "/" + trimmed
            guard let built = components.url else { throw StreamError.invalidURL }
            url = built
        } else {
            var components = URLComponents(url: AppConfig.apiRoot, resolvingAgainstBaseURL: false)!
            let root = AppConfig.apiRoot.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            components.path = "/" + [root, trimmed].filter { !$0.isEmpty }.joined(separator: "/")
            guard let built = components.url else { throw StreamError.invalidURL }
            url = built
        }

        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("ios", forHTTPHeaderField: "X-BSH-Client")
        if let token = TokenStore.read() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw StreamError.badStatus(http.statusCode)
        }

        var eventName: String?
        var dataLines: [String] = []

        for try await line in bytes.lines {
            try Task.checkCancellation()
            if line.hasPrefix(":") { continue } // comment / keepalive
            if line.isEmpty {
                if !dataLines.isEmpty {
                    continuation.yield(Event(event: eventName, data: dataLines.joined(separator: "\n")))
                }
                eventName = nil
                dataLines = []
                continue
            }
            if line.hasPrefix("event:") {
                eventName = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("data:") {
                dataLines.append(String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces))
            }
        }
        if !dataLines.isEmpty {
            continuation.yield(Event(event: eventName, data: dataLines.joined(separator: "\n")))
        }
    }
}
