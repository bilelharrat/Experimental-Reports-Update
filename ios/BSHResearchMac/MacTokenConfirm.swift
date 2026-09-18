#if os(macOS)
import AppKit

/// Ask before any manual action that spends tokens.
///
/// Owner policy (2026-09-15): a button that costs money says so first.
/// Report generation is the one exception — everybody already knows a memo
/// run costs, and confirming it twice only trains people to click through.
/// Conversational sends (Ask, Console) are exempt for the same reason.
///
/// The Mac UI has no language switch, so the alert carries both languages.
enum MacTokenConfirm {
    @MainActor
    static func ask(detail: String? = nil) -> Bool {
        let alert = NSAlert()
        alert.messageText = "This action will cost tokens."
        var lines = ["该操作会消耗 Token 额度。"]
        if let detail, !detail.isEmpty { lines.append(detail) }
        alert.informativeText = lines.joined(separator: "\n\n")
        alert.addButton(withTitle: "Continue")
        alert.addButton(withTitle: "Cancel")
        return alert.runModal() == .alertFirstButtonReturn
    }
}
#endif
