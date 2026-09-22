import XCTest
@testable import BSHResearch

@MainActor
final class ReportsDeskTests: XCTestCase {

    func testAppTabReportsIntegration() {
        let tab = AppTab.reports
        XCTAssertEqual(tab.rawValue, "reports")
        XCTAssertEqual(tab.index, 2)
        XCTAssertEqual(tab.titleKey, "tab.reports")
        XCTAssertEqual(tab.systemImage, "doc.text")
        XCTAssertEqual(AppTab.from(index: 2), .reports)
    }

    func testDeepLinkReportsTab() {
        let url = URL(string: "bshresearch://tab/reports")!
        let link = DeepLink(url: url)
        XCTAssertEqual(link, .tab(.reports))
    }

    func testDeepLinkReportDetail() {
        let url = URL(string: "bshresearch://report/memo-12345")!
        let link = DeepLink(url: url)
        XCTAssertEqual(link, .report("memo-12345"))
    }

    func testAppTabsCountAndPulseOnSameRow() {
        XCTAssertEqual(AppTab.allCases.count, 6)
        XCTAssertEqual(AppTab.allCases, [.home, .research, .reports, .news, .pulse, .market])
        XCTAssertEqual(AppTab.pulse.index, 4)
        XCTAssertEqual(AppTab.market.index, 5)
    }

    func testDeepLinkSettings() {
        let urlDirect = URL(string: "bshresearch://settings")!
        XCTAssertEqual(DeepLink(url: urlDirect), .settings)

        let urlTab = URL(string: "bshresearch://tab/settings")!
        XCTAssertEqual(DeepLink(url: urlTab), .settings)
    }

    func testFilterScopeLocalizations() {
        for lang in AppLanguage.allCases {
            for scope in ReportFilterScope.allCases {
                let text = L10n.string(scope.titleKey, lang: lang)
                XCTAssertFalse(text.isEmpty)
                XCTAssertNotEqual(text, scope.titleKey)
            }
        }
    }

    func testReportsDeskFilteringAndSorting() {
        let model = ReportsDeskViewModel()

        let r1 = ReportSummary(
            id: "r1",
            companyId: "aapl",
            companyName: "Apple Inc.",
            reportType: "Investment Memo",
            audience: "Internal",
            language: "en",
            status: "completed",
            progress: 100,
            stage: "Completed",
            error: nil,
            kind: "memo",
            createdAt: "2026-09-01T10:00:00Z",
            updatedAt: "2026-09-01T10:05:00Z",
            streamUrl: nil,
            downloadUrls: ["en": "/download/r1"],
            previewUrls: ["en": "/preview/r1"],
            resumeAvailable: false,
            logoUrl: nil,
            logoDomain: nil
        )

        let r2 = ReportSummary(
            id: "r2",
            companyId: "nvda",
            companyName: "NVIDIA Corp.",
            reportType: "Executive Brief",
            audience: "Public",
            language: "en",
            status: "running",
            progress: 45,
            stage: "Financial Analysis",
            error: nil,
            kind: "brief",
            createdAt: "2026-09-10T12:00:00Z",
            updatedAt: "2026-09-10T12:02:00Z",
            streamUrl: "/stream/r2",
            downloadUrls: nil,
            previewUrls: nil,
            resumeAvailable: false,
            logoUrl: nil,
            logoDomain: nil
        )

        let r3 = ReportSummary(
            id: "r3",
            companyId: "msft",
            companyName: "Microsoft Corp.",
            reportType: "Investment Memo",
            audience: "Internal",
            language: "en",
            status: "failed",
            progress: 80,
            stage: "Error",
            error: "Timeout",
            kind: "memo",
            createdAt: "2026-08-20T08:00:00Z",
            updatedAt: "2026-08-20T08:05:00Z",
            streamUrl: nil,
            downloadUrls: nil,
            previewUrls: nil,
            resumeAvailable: true,
            logoUrl: nil,
            logoDomain: nil
        )

        model.reports = [r1, r2, r3]

        // Counts
        XCTAssertEqual(model.counts.all, 3)
        XCTAssertEqual(model.counts.running, 1)
        XCTAssertEqual(model.counts.completed, 1)
        XCTAssertEqual(model.counts.failed, 1)

        // Unique companies and types
        XCTAssertEqual(model.uniqueCompanies.count, 3)
        XCTAssertEqual(model.uniqueReportTypes.count, 2)

        // Filter Scope: running
        model.filterScope = .running
        XCTAssertEqual(model.filteredReports.map(\.id), ["r2"])

        // Filter Scope: completed
        model.filterScope = .completed
        XCTAssertEqual(model.filteredReports.map(\.id), ["r1"])

        // Filter Scope: failed
        model.filterScope = .failed
        XCTAssertEqual(model.filteredReports.map(\.id), ["r3"])

        // Filter Scope: all with search
        model.filterScope = .all
        model.searchText = "nvidia"
        XCTAssertEqual(model.filteredReports.map(\.id), ["r2"])

        model.searchText = "investment"
        XCTAssertEqual(model.filteredReports.count, 2)

        // Sorting: newest first
        model.searchText = ""
        model.sortOrder = .newest
        XCTAssertEqual(model.filteredReports.first?.id, "r2")
        XCTAssertEqual(model.filteredReports.last?.id, "r3")

        // Sorting: company name
        model.sortOrder = .company
        XCTAssertEqual(model.filteredReports.map(\.id), ["r1", "r3", "r2"])
    }
}
