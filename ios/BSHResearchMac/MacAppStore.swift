import AppKit
import Combine
import Foundation

@MainActor
final class MacAppStore: ObservableObject {
    @Published private(set) var companies: [MacCompany] = []
    @Published private(set) var reports: [MacReport] = []
    @Published private(set) var news: [MacNewsItem] = []
    @Published private(set) var watchlist: [MacQuote] = []
    @Published private(set) var gainers: [MacQuote] = []
    @Published private(set) var losers: [MacQuote] = []
    @Published private(set) var pulse: MacPulseBrief?
    @Published private(set) var loading = false
    @Published var error: String?

    @Published var openDocumentURL: URL?
    @Published var openDocumentIsPDF = false
    @Published var openReportTitle = ""
    @Published var readerLanguage = "en"
    @Published private(set) var openingMemo = false

    private var tempFiles: [URL] = []

    var recentReports: [MacReport] {
        reports
            .sorted { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
            .prefix(20)
            .map { $0 }
    }

    var runningReports: [MacReport] {
        reports.filter { !$0.isComplete && !$0.isFailed && !($0.status ?? "").isEmpty }
    }

    func bootstrap() async {
        await refreshHome()
    }

    func refreshHome() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let cos = MacAPIClient.shared.listCompanies()
            async let reps = MacAPIClient.shared.listReports()
            companies = try await cos.sorted {
                ($0.name ?? $0.id).localizedCaseInsensitiveCompare($1.name ?? $1.id) == .orderedAscending
            }
            reports = try await reps
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshMarket() async {
        do {
            let tickers = Array(
                Set(companies.compactMap { $0.ticker?.uppercased() }.filter { !$0.isEmpty })
            ).prefix(24)
            let pins = ["SPY", "QQQ", "DIA", "IWM"] + tickers
            async let quotes = MacAPIClient.shared.fetchQuotes(tickers: Array(pins.prefix(20)))
            async let screeners = MacAPIClient.shared.fetchScreeners(limit: 10)
            watchlist = try await quotes
            let s = try await screeners
            gainers = s.gainers
            losers = s.losers
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshNews() async {
        do {
            let tickers = companies.compactMap(\.ticker).prefix(10).map { $0 }
            news = try await MacAPIClient.shared.fetchNews(tickers: Array(tickers), limit: 40)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func refreshPulse() async {
        do {
            pulse = try await MacAPIClient.shared.fetchPulse()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func reports(for companyId: String) -> [MacReport] {
        reports
            .filter { $0.companyId == companyId }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
    }

    func openMemo(_ report: MacReport, language: String? = nil) async {
        let lang = language ?? readerLanguage
        readerLanguage = lang
        openingMemo = true
        defer { openingMemo = false }
        do {
            var detail = report
            if let fetched = try? await MacAPIClient.shared.getReport(id: report.id) {
                detail = fetched
            }
            guard let doc = detail.documentPath(prefer: lang) else {
                error = "No memo file for \(lang.uppercased())"
                return
            }
            let data = try await MacAPIClient.shared.download(pathOrURL: doc.path)
            let ext = doc.isPDF ? "pdf" : "docx"
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("bsh-memo-\(detail.id)-\(lang).\(ext)")
            try data.write(to: url, options: .atomic)
            tempFiles.append(url)
            openDocumentURL = url
            openDocumentIsPDF = doc.isPDF
            openReportTitle = "\(detail.companyName ?? "") — \(detail.displayTitle)"
        } catch {
            self.error = error.localizedDescription
        }
    }

    func closeMemo() {
        openDocumentURL = nil
        openReportTitle = ""
    }
}

struct MacNewsItem: Identifiable, Hashable {
    let id: String
    let title: String
    let source: String?
    let publishedAt: String?
    let ticker: String?
    let url: String?
}

struct MacQuote: Identifiable, Hashable {
    var id: String { ticker }
    let ticker: String
    let last: Double?
    let pct: Double?
    let name: String?

    var priceText: String {
        guard let last else { return "—" }
        return String(format: "%.2f", last)
    }

    var pctText: String {
        guard let pct else { return "—" }
        return String(format: "%+.2f%%", pct)
    }

    var isUp: Bool { (pct ?? 0) >= 0 }
}

struct MacPulseBrief: Decodable {
    let date: String?
    let indices: [MacPulseQuote]?
    let note: MacPulseNote?

    struct MacPulseQuote: Decodable, Identifiable {
        var id: String { ticker }
        let ticker: String
        let lastPrice: Double?
        let changePct1d: Double?
        enum CodingKeys: String, CodingKey {
            case ticker
            case lastPrice = "last_price"
            case changePct1d = "change_pct_1d"
        }
    }

    struct MacPulseNote: Decodable {
        let headlineEn: String?
        let bulletsEn: [String]?
        enum CodingKeys: String, CodingKey {
            case headlineEn = "headline_en"
            case bulletsEn = "bullets_en"
        }
    }
}
