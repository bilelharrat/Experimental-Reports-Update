import Foundation

/// Fast, disk-backed cache for BSH Research Mac desk.
/// Provides sub-20ms hydration on startup and transparent background persistence.
final class MacDataCache: @unchecked Sendable {
    static let shared = MacDataCache()

    private let cacheDir: URL
    private let fileManager = FileManager.default
    private let queue = DispatchQueue(label: "com.bsh.macdatacache", qos: .utility)
    private let encoder: JSONEncoder = {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted]
        enc.dateEncodingStrategy = .iso8601
        return enc
    }()
    private let decoder: JSONDecoder = {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return dec
    }()

    private init() {
        let base = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())
        cacheDir = base.appendingPathComponent("BSHMacCache", isDirectory: true)
        try? fileManager.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    // MARK: - File Paths

    private func fileURL(named name: String) -> URL {
        cacheDir.appendingPathComponent("\(name).json")
    }

    // MARK: - Metadata & Sync Timestamps

    func lastSyncDate() -> Date? {
        let url = fileURL(named: "companies")
        guard let attrs = try? fileManager.attributesOfItem(atPath: url.path),
              let modDate = attrs[.modificationDate] as? Date else {
            return nil
        }
        return modDate
    }

    var hasCachedData: Bool {
        fileManager.fileExists(atPath: fileURL(named: "companies").path)
    }

    // MARK: - Companies

    func loadCompanies() -> [MacCompany]? {
        load([MacCompany].self, from: "companies")
    }

    func saveCompanies(_ companies: [MacCompany]) {
        save(companies, to: "companies")
    }

    // MARK: - Reports

    func loadReports() -> [MacReport]? {
        load([MacReport].self, from: "reports")
    }

    func saveReports(_ reports: [MacReport]) {
        save(reports, to: "reports")
    }

    // MARK: - Quotes / Watchlist

    func loadQuotes() -> [MacQuote]? {
        load([MacQuote].self, from: "quotes")
    }

    func saveQuotes(_ quotes: [MacQuote]) {
        save(quotes, to: "quotes")
    }

    // MARK: - News

    func loadNews() -> [MacNewsItem]? {
        load([MacNewsItem].self, from: "news")
    }

    func saveNews(_ news: [MacNewsItem]) {
        save(news, to: "news")
    }

    // MARK: - Pulse Brief

    func loadPulse() -> MacPulseBrief? {
        load(MacPulseBrief.self, from: "pulse")
    }

    func savePulse(_ pulse: MacPulseBrief) {
        save(pulse, to: "pulse")
    }

    // MARK: - "What Changed" Baseline Snapshots

    func loadBaselines() -> [String: Date] {
        load([String: Date].self, from: "baselines") ?? [:]
    }

    func saveBaselines(_ baselines: [String: Date]) {
        save(baselines, to: "baselines")
    }

    // MARK: - Generic Persistence Helpers

    private func save<T: Encodable>(_ value: T, to name: String) {
        queue.async { [weak self] in
            guard let self else { return }
            do {
                let data = try self.encoder.encode(value)
                let url = self.fileURL(named: name)
                try data.write(to: url, options: .atomic)
            } catch {
                // Best effort disk cache
            }
        }
    }

    private func load<T: Decodable>(_ type: T.Type, from name: String) -> T? {
        let url = fileURL(named: name)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? decoder.decode(type, from: data)
    }

    func clearAll() {
        queue.async { [weak self] in
            guard let self else { return }
            try? self.fileManager.removeItem(at: self.cacheDir)
            try? self.fileManager.createDirectory(at: self.cacheDir, withIntermediateDirectories: true)
        }
    }
}
