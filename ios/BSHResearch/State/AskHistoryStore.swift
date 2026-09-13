import Foundation

struct AskHistoryEntry: Codable, Identifiable, Equatable {
    let id: String
    let companyId: String
    let companyName: String?
    let prompt: String
    let answer: String
    let sources: [AskSourceChip]
    let createdAt: String
}

struct AskSourceChip: Codable, Identifiable, Equatable, Hashable {
    var id: String { "\(kind):\(label):\(url ?? "")" }
    let kind: String
    let label: String
    let url: String?
}

enum AskHistoryStore {
    private static let prefix = "bsh.askHistory."
    private static let maxEntries = 40

    static func load(companyId: String) -> [AskHistoryEntry] {
        let key = prefix + companyId
        guard let data = UserDefaults.standard.data(forKey: key),
              let rows = try? JSONDecoder().decode([AskHistoryEntry].self, from: data)
        else { return [] }
        return rows
    }

    static func append(_ entry: AskHistoryEntry) {
        var rows = load(companyId: entry.companyId)
        rows.insert(entry, at: 0)
        if rows.count > maxEntries {
            rows = Array(rows.prefix(maxEntries))
        }
        if let data = try? JSONEncoder().encode(rows) {
            UserDefaults.standard.set(data, forKey: prefix + entry.companyId)
        }
    }

    static func extractSources(from text: String) -> [AskSourceChip] {
        var chips: [AskSourceChip] = []
        var seen = Set<String>()

        let urlPattern = #"https?://[^\s)\]>"']+"#
        if let regex = try? NSRegularExpression(pattern: urlPattern) {
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            for match in regex.matches(in: text, range: range) {
                guard let r = Range(match.range, in: text) else { continue }
                var url = String(text[r])
                while url.last == "." || url.last == "," { url.removeLast() }
                let label = URL(string: url)?.host ?? "Link"
                let chip = AskSourceChip(kind: "url", label: label, url: url)
                if seen.insert(chip.id).inserted { chips.append(chip) }
            }
        }

        let keywords: [(String, String)] = [
            ("10-K", "filing"),
            ("10-Q", "filing"),
            ("8-K", "filing"),
            ("earnings call", "transcript"),
            ("transcript", "transcript"),
            ("proxy", "filing"),
            ("annual report", "filing"),
        ]
        let lower = text.lowercased()
        for (needle, kind) in keywords {
            if lower.contains(needle.lowercased()) {
                let chip = AskSourceChip(kind: kind, label: needle, url: nil)
                if seen.insert(chip.id).inserted { chips.append(chip) }
            }
        }
        return Array(chips.prefix(6))
    }
}
