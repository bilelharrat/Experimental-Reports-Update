import SwiftUI

/// Renders Ask replies like Notes/Messages: real bold/lists, no raw `**`,
/// and strips trailing JSON/code fences the model sometimes dumps.
enum AskAnswerFormatter {
    private static let fencePattern = #"```[\s\S]*?```"#
    private static let leftoverBold = #"\*\*(.+?)\*\*"#
    private static let leftoverItalic = #"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"#

    static func clean(_ raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let regex = try? NSRegularExpression(pattern: fencePattern) {
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            text = regex.stringByReplacingMatches(in: text, range: range, withTemplate: "")
        }
        // Collapse excess blank lines left by fence removal.
        while text.contains("\n\n\n") {
            text = text.replacingOccurrences(of: "\n\n\n", with: "\n\n")
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func attributed(_ raw: String) -> AttributedString {
        let cleaned = clean(raw)
        var options = AttributedString.MarkdownParsingOptions()
        options.interpretedSyntax = .full
        options.failurePolicy = .returnPartiallyParsedIfPossible
        if let parsed = try? AttributedString(markdown: cleaned, options: options) {
            return parsed
        }
        // Fallback: strip leftover markdown markers so the user never sees `**`.
        var plain = cleaned
        if let bold = try? NSRegularExpression(pattern: leftoverBold) {
            let range = NSRange(plain.startIndex..<plain.endIndex, in: plain)
            plain = bold.stringByReplacingMatches(in: plain, range: range, withTemplate: "$1")
        }
        if let italic = try? NSRegularExpression(pattern: leftoverItalic) {
            let range = NSRange(plain.startIndex..<plain.endIndex, in: plain)
            plain = italic.stringByReplacingMatches(in: plain, range: range, withTemplate: "$1")
        }
        return AttributedString(plain)
    }
}

struct AskAnswerText: View {
    let text: String
    var isUser = false

    var body: some View {
        Text(isUser ? AttributedString(text) : AskAnswerFormatter.attributed(text))
            .font(.body)
            .foregroundStyle(isUser ? Color.white : Color.primary)
            .lineSpacing(3)
            .multilineTextAlignment(isUser ? .trailing : .leading)
            .textSelection(.enabled)
    }
}
