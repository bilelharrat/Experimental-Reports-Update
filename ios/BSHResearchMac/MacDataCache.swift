import CryptoKit
import Foundation

/// Fast, disk-backed cache for BSH Research Mac desk.
/// Provides sub-20ms hydration on startup and transparent background persistence.
/// Files live in one folder per server (`BSHMacCache/<hash of host:port>/`).
final class MacDataCache: @unchecked Sendable {
    static let shared = MacDataCache()

    private let rootDir: URL
    private let fileManager = FileManager.default
    private let queue = DispatchQueue(label: "com.bsh.macdatacache", qos: .utility)
    private let lock = NSLock()
    private var preparedScopes = Set<String>()
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
        rootDir = base.appendingPathComponent("BSHMacCache", isDirectory: true)
        try? fileManager.createDirectory(at: rootDir, withIntermediateDirectories: true)
        removeLegacyUnscopedFiles()
    }

    // MARK: - File Paths

    /// Folder for the currently configured server.
    var cacheDir: URL {
        scopeDir(for: MacConfig.serverScope)
    }

    private func scopeDir(for scope: String) -> URL {
        let digest = SHA256.hash(data: Data(scope.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
            .prefix(16)
        let name = String(digest)
        let dir = rootDir.appendingPathComponent(name, isDirectory: true)
        lock.lock()
        defer { lock.unlock() }
        if !preparedScopes.contains(name) {
            try? fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
            preparedScopes.insert(name)
        }
        return dir
    }

    private func fileURL(named name: String) -> URL {
        cacheDir.appendingPathComponent("\(name).json")
    }

    /// Files written by versions that kept one unscoped folder mixed data from
    /// several servers; drop them once.
    private func removeLegacyUnscopedFiles() {
        guard let items = try? fileManager.contentsOfDirectory(
            at: rootDir, includingPropertiesForKeys: nil
        ) else { return }
        for item in items where item.pathExtension == "json" {
            try? fileManager.removeItem(at: item)
        }
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

    func loadRollup() -> MacRollup? {
        load(MacRollup.self, from: "rollup")
    }

    func saveRollup(_ rollup: MacRollup) {
        save(rollup, to: "rollup")
    }

    func loadDecisions() -> [String: [MacDecision]]? {
        load([String: [MacDecision]].self, from: "decisions")
    }

    func saveDecisions(_ decisions: [String: [MacDecision]]) {
        save(decisions, to: "decisions")
    }

    func loadBaselines() -> [String: Date] {
        load([String: Date].self, from: "baselines") ?? [:]
    }

    func saveBaselines(_ baselines: [String: Date]) {
        save(baselines, to: "baselines")
    }

    // MARK: - Generic Persistence Helpers

    private func save<T: Encodable>(_ value: T, to name: String) {
        let url = fileURL(named: name)
        queue.async { [weak self] in
            guard let self else { return }
            do {
                let data = try self.encoder.encode(value)
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

    /// Removes the current server's cached files. Waits for pending writes so a
    /// `load()` issued right after cannot observe stale data.
    func clearAll() {
        let dir = cacheDir
        queue.sync {
            try? fileManager.removeItem(at: dir)
            try? fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
        }
    }

    /// Removes every server's cached files.
    func clearAllServers() {
        queue.sync {
            try? fileManager.removeItem(at: rootDir)
            try? fileManager.createDirectory(at: rootDir, withIntermediateDirectories: true)
            lock.lock()
            preparedScopes.removeAll()
            lock.unlock()
        }
    }
}
