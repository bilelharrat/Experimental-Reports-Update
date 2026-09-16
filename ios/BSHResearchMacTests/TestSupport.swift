import Foundation

/// Pins the process-wide default time zone to UTC for date-dependent tests.
///
/// `NSTimeZone.default` drives `Calendar.current`, `Calendar(identifier:)` and every
/// `DateFormatter` whose `timeZone` was never set explicitly, including instances created
/// before the pin. MacQuoteMath and the JS↔Swift parity golden both assume UTC, so a
/// test class calls `UTCPin.pin()` from `override class func setUp()` and
/// `UTCPin.restore()` from `override class func tearDown()`; later classes then run in
/// the machine's own zone again. Calls nest: only the outermost restore puts the saved
/// zone back.
enum UTCPin {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var depth = 0
    nonisolated(unsafe) private static var saved: TimeZone?

    static let utc = TimeZone(identifier: "UTC")!

    static var isPinned: Bool {
        lock.lock()
        defer { lock.unlock() }
        return depth > 0
    }

    static func pin() {
        lock.lock()
        defer { lock.unlock() }
        if depth == 0 { saved = NSTimeZone.default }
        depth += 1
        NSTimeZone.default = utc
    }

    static func restore() {
        lock.lock()
        defer { lock.unlock() }
        guard depth > 0 else { return }
        depth -= 1
        if depth == 0, let saved {
            NSTimeZone.default = saved
            self.saved = nil
        }
    }
}

/// Fixed instants for tests. Every date-dependent test passes `now` explicitly and never
/// relies on the wall clock.
enum TestDates {
    /// Parses an ISO-8601 instant such as "2026-09-14T15:00:00Z"; traps on a malformed literal.
    static func iso(_ string: String) -> Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        guard let date = formatter.date(from: string) else {
            preconditionFailure("TestDates.iso: not an ISO-8601 instant: \(string)")
        }
        return date
    }

    /// The UTC calendar day of `date` as "yyyy-MM-dd", independent of the pinned zone.
    static func utcDay(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = UTCPin.utc
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }
}
