//
//  MacBureauReportCustomizerModel.swift
//  BSHResearchMac
//
//  What the Generate report dialog under Bureau chooses, and what it sends, as the website's
//  dialog does (ReportCustomizerModal.vue): the same options and wording, the same locks
//  (the Buffett memo and Memo Studio fix the audience, engine and quality), the same pre-flight
//  notes, and the same request — POST /api/reports with the website's fields, or
//  POST /api/memos/studio/investigate with the company and the report type.
//

import Foundation
import SwiftUI

// MARK: - The options, as the website lists them

enum MacBureauCustomizer {
    /// `report_type` must be one of the server's REPORT_TYPES; `studio` marks the two Memo
    /// Studio can run, `template` the memos the template applies to, and the three that are
    /// not `available` are shown, disabled, and can never be chosen.
    struct Archetype: Identifiable, Equatable {
        let id: String
        let reportType: String
        let studio: Bool
        let available: Bool
        let template: Bool
        let title: String
        let badge: String
        let desc: String
    }

    struct Option: Identifiable, Equatable {
        let id: String
        let title: String
        var badge: String = ""
        let desc: String
        var disabled = false
    }

    enum Tab: String, CaseIterable, Identifiable {
        case blueprint, engine, evidence

        var id: String { rawValue }

        var title: String {
            switch self {
            case .blueprint: return "Blueprint & Framing"
            case .engine: return "Engine & Quality"
            case .evidence: return "Evidence Sources"
            }
        }

        var icon: String {
            switch self {
            case .blueprint: return "file-text"
            case .engine: return "cpu"
            case .evidence: return "database"
            }
        }
    }

    static let archetypes: [Archetype] = [
        Archetype(
            id: "auto", reportType: "Investment Report (Auto)", studio: true, available: true, template: true,
            title: "Auto-Stage Memo", badge: "Recommended",
            desc: "Detects the company's stage and writes the matching investment memo from every analysis pass."
        ),
        Archetype(
            id: "investment_memo_late_stage", reportType: "Investment Memo (Late-Stage)", studio: true, available: true, template: true,
            title: "Late-Stage Memo", badge: "Institutional",
            desc: "Growth and late-stage thesis, unit economics and the exit path."
        ),
        Archetype(
            id: "buffett_memo", reportType: "Buffett Investment Memo", studio: false, available: true, template: false,
            title: "Buffett-Method Memo", badge: "Owner's view",
            desc: "Moat durability, margin of safety, cash returns and circle of competence, judged as a prospective owner."
        ),
        Archetype(
            id: "deep_dive", reportType: "Financial Analysis", studio: false, available: false, template: false,
            title: "Financial Audit", badge: "Forensic",
            desc: "Forensic balance sheet, quality of earnings and cash-flow bridges."
        ),
        Archetype(
            id: "market_analysis", reportType: "Market Analysis", studio: false, available: false, template: false,
            title: "Market Analysis", badge: "Industry",
            desc: "TAM and SAM, competitive matrix, pricing power and headwind sensitivity."
        ),
        Archetype(
            id: "background", reportType: "Background", studio: false, available: false, template: false,
            title: "Background Dossier", badge: "Diligence",
            desc: "Management track record, cap-table history and regulatory scrutiny."
        ),
    ]

    /// `audience` must be one of the server's AUDIENCES.
    static let audiences: [Option] = [
        Option(id: "Internal", title: "Internal IC", desc: "The LP memo, plus an internal IC decision memo that never leaves BSH. The IC memo is one extra paid call."),
        Option(id: "Partner", title: "General Partner", desc: "The LP memo, plus the internal IC decision memo for partner review (one extra paid call). The IC memo never leaves BSH."),
        Option(id: "LP", title: "LPs and co-investors", desc: "The LP memo only: the document written to be shared with LPs and SPV investors. No IC memo, and no extra call."),
        Option(id: "Assistant", title: "Diligence Lead", desc: "The LP memo, plus the internal IC decision memo for the diligence team (one extra paid call). The IC memo never leaves BSH."),
    ]

    static let templates: [Option] = [
        Option(id: "standard", title: "Standard memo", desc: "Five sections, about 6,000–9,000 words including tables."),
        Option(id: "ic_v2", title: "Founder's IC template", desc: "Twelve sections with a scorecard, a verdict, citations and charts."),
    ]

    static let lengths: [Option] = [
        Option(id: "compact", title: "Executive Brief", desc: "Seven sections, roughly 15,000–17,000 words."),
        Option(id: "full", title: "Full IC Report", desc: "Twelve sections: about 10,500–13,500 words of prose, plus tables, sources and calculation notes."),
    ]

    /// Every run writes both documents, so the single-language options are shown disabled.
    static let languages: [Option] = [
        Option(id: "dual", title: "Bilingual (EN + ZH)", desc: "Both documents, every run"),
        Option(id: "en", title: "English only", desc: "Not available yet", disabled: true),
        Option(id: "zh", title: "中文 only", desc: "Not available yet", disabled: true),
    ]

    static let modes: [Option] = [
        Option(id: "one_click", title: "One-Click Autonomous", badge: "Recommended", desc: "Runs start to finish without stopping. Best for quick exploratory reads or overnight batches."),
        Option(id: "studio_review", title: "Interactive Studio Review", badge: "Curated", desc: "Pauses after Phase 2 (research and dilemmas) so analysts can curate the thesis spine cards and adjust the risk framing before the memo is written."),
    ]

    /// claude_runner's MEMO_QUALITY_LEVELS.
    static let qualities: [Option] = [
        Option(id: "balanced", title: "Balanced Pipeline", badge: "Recommended", desc: "Top model writes the memo at medium effort; research, verification and translation run on Sonnet."),
        Option(id: "best", title: "Best Frontier", badge: "Frontier", desc: "Top model at high effort across the whole writing wave. The most thorough, and the most expensive."),
        Option(id: "economy", title: "Economy Draft", badge: "Light", desc: "Everything on Sonnet. Rapid reconnaissance for initial screening and preliminary structuring."),
    ]

    static let engines: [Option] = [
        Option(id: "claude", title: "Claude", badge: "Default", desc: "Agents open the research folder themselves and re-read sources as they work."),
        Option(id: "gemini", title: "Gemini", badge: "Flash", desc: "Same pipeline and checks; research is extracted to text and handed over up front."),
    ]

    /// The website's English strings (i18n.js, `customizer.*`).
    enum Copy {
        static let selectCompany = "Select Company"
        static let searchCompany = "Search company or ticker…"
        static let close = "Close"
        static let archetypeTitle = "Report Archetype"
        static let archetypeDesc = "Select analysis blueprint"
        static let archetypeUnavailable = "This report type has no pipeline yet, so it can't be generated."
        static let notAvailable = "Not available yet"
        static let audienceTitle = "Target Audience"
        static let scopeTitle = "Report Scope & Depth"
        static let languageTitle = "Synthesis Language"
        static let languageLocked = "Every run writes both documents. Generating only one needs pipeline work."
        static let workflowTitle = "Investigation & Synthesis Workflow"
        static let workflowDesc = "Human-in-the-loop vs Autonomous"
        static let studioUnavailable = "Memo Studio runs the investment-memo blueprints only."
        static let qualityTitle = "Compute Quality & Reasoning Tier"
        static let qualityDesc = "Model depth and verification rounds"
        static let qualityLocked = "Claude only — Gemini runs one model at one effort"
        static let engineTitle = "Generation engine"
        static let engineDesc = "Same pipeline and checks either way"
        static let evidenceTitle = "Evidence Repository Attachments"
        static let evidenceDesc = "Cross-examination sources"
        static let evidenceLoading = "Loading analysed documents…"
        static let evidenceFailed = "Could not load this company's documents."
        static let evidenceEmpty = "No analysed documents yet. Upload files in the Files tab and run Analyze on them."
        static let evidenceSelectAll = "Select all"
        static let evidenceClearAll = "Clear all"
        static let cancel = "Cancel"
        static let launchStudio = "Launch Studio Investigation"
        static let generateMemo = "Generate Research Memo"
        static let initializing = "Initializing Pipeline…"
        static func generateMemoFor(_ name: String) -> String { "Generate Research Memo for \(name)" }
        static func launchStudioFor(_ name: String) -> String { "Launch Studio Investigation for \(name)" }
        static let errorNoCompany = "Please select a target company."
        static let errorLaunch = "Failed to launch report generation."
        static let templateTitle = "Memo template"
        static func templateDefaultHint(_ name: String) -> String { "Workspace default: \(name). A change here applies to this run only." }
        static func templateStudioHint(_ name: String) -> String { "Memo Studio writes on the workspace template: \(name)." }
        static let lengthStandard = "Standard (5 sections)"
        static let lengthStandardDesc = "About 6,000–9,000 words including tables."
        static let lengthLockedStandard = "The standard memo has one length. Brief and Full apply to the founder's IC template."
        static let lengthShortCompact = "Brief"
        static let lengthShortFull = "Full IC"
        static let buffettLocked = "Buffett-method memos run at one fixed length and quality."
        static let tagStudio = "Studio Paused"
        static let tagAutonomous = "Autonomous"
        static let audienceLockedBuffett = "A Buffett-method memo is one document for every reader and has no IC memo, so there is no audience to choose."
        static let audienceLockedStudio = "Memo Studio runs are written for the internal IC: the LP memo plus the IC decision memo."
        static let engineLockedBuffett = "Buffett-method memos run on Claude only."
        static let studioDefaults = "Memo Studio runs on Claude, at full length and the top quality tier, on the workspace template. These choices apply to one-click runs."
        static func preflightResets(time: String, relative: String) -> String { "Resets \(time) (\(relative))." }
        static let preflightSwitchGemini = "Switch engine to Gemini"
        static let preflightSwitchClaude = "Switch engine to Claude"
        static let preflightClaudeOnlyBuffett = "Buffett-method memos run on Claude only."
        static let preflightClaudeOnlyStudio = "Memo Studio runs on Claude only."
        static func noteSubsidiaryOf(_ parent: String) -> String { "Subsidiary of \(parent) — run on \(parent)?" }
        static func noteSubsidiaryOfMissing(_ parent: String) -> String { "Subsidiary of \(parent) — run on \(parent)? It is not in this workspace yet." }
        static func noteRunOnParent(_ name: String) -> String { "Run on \(name)" }
        static let noteSubsidiary = "Listed as a subsidiary: check whether its parent is the company to invest in."
        static let noteNonprofit = "Listed as a nonprofit: it has no shares to buy, so the memo may find nothing to act on."
        static let noteListed = "Listed company: the Buffett-method memo is the one built to value a public stock."
        static let noteUseBuffett = "Use the Buffett-method memo"
        static let estimateNone = "No runs at this setting yet"
        static func estimateTimeRange(low: Int, high: Int) -> String { "Typically \(low)–\(high) min" }
        static func estimateTimeAbout(_ n: Int) -> String { "Typically about \(n) min" }
        static func estimateCostClaude(_ cost: String) -> String { "about \(cost) API-equivalent, drawn from the Claude weekly allowance" }
        static func estimateCost(_ cost: String) -> String { "about \(cost) in API cost" }
        static let estimateUnpriced = "cost not priced"
        static func estimateSamples(_ n: Int) -> String { "from \(n) runs" }
        static func estimateCeiling(_ cost: String) -> String { "stops at \(cost)" }
        static let controlsTitle = "Run controls"
        static let controlsDesc = "Where the run pauses and how much it may spend"
        static let pauseAfterEnglish = "Pause after English"
        static let pauseAfterEnglishHelp = "Read the English before paying for the Chinese, artifacts and IC memo"
        static let pausePill = "Pauses after English"
        static let costCeiling = "Spend ceiling"
        static let costCeilingHelp = "USD, API-equivalent. Past it, the run stops before its next paid phase and delivers what is finished. Blank uses the default."
        static let costCeilingUnit = "USD"
        static let costCeilingInvalid = "Enter a positive amount, or leave it blank for the default."
        static func builtFromAll(_ n: Int) -> String { "Built from \(n) analysed documents, plus web research." }
        static let builtFromOne = "Built from 1 analysed document, plus web research."
        static func builtFromSome(_ n: Int, of total: Int) -> String { "Built from \(n) of \(total) analysed documents, plus web research." }
        static let builtFromWebOnly = "Web research only: nothing analysed is on file for this company yet. Upload files in the Files tab and run Analyze on them."
        static let builtFromNoneSelected = "Web research only: no analysed document is selected."
        static let icTemplateTag = "IC template"
    }

    /// The template the website starts from when Settings can't be read (memo_flags).
    static let defaultTemplate = "ic_v2"
    /// What a blank spend ceiling means: the server's BSH_MEMO_COST_CEILING_USD.
    static let defaultCostCeilingUsd = 60
}

// MARK: - What the server says

/// A company as `GET /api/companies` lists it, for what the dialog says about which entity a
/// run is about (the Mac's company model leaves these fields out).
struct MacBureauCompanyFacts: Decodable, Sendable {
    let id: String
    let name: String?
    let legalName: String?
    let disambiguator: String?
    let parentCompany: String?
    let website: String?
    let logoDomain: String?
    let status: String?
    let companyType: String?
    let ticker: String?
    let sector: String?
    let industry: String?

    private enum CodingKeys: String, CodingKey {
        case id, name, disambiguator, website, status, ticker, sector, industry
        case legalName = "legal_name"
        case parentCompany = "parent_company"
        case logoDomain = "logo_domain"
        case companyType = "company_type"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        func text(_ key: CodingKeys) -> String? { (try? c.decodeIfPresent(String.self, forKey: key)) ?? nil }
        name = text(.name)
        legalName = text(.legalName)
        disambiguator = text(.disambiguator)
        parentCompany = text(.parentCompany)
        website = text(.website)
        logoDomain = text(.logoDomain)
        status = text(.status)
        companyType = text(.companyType)
        ticker = text(.ticker)
        sector = text(.sector)
        industry = text(.industry)
    }
}

/// `GET /api/reports/readiness`: what would stop a run, from signals that cost nothing.
struct MacBureauReadiness: Decodable, Sendable {
    struct Item: Decodable, Sendable {
        let code: String
        let en: String?
        let zh: String?
        let resetAt: String?

        private enum CodingKeys: String, CodingKey {
            case code, en, zh
            case resetAt = "reset_at"
        }
    }

    struct Company: Decodable, Sendable { let id: String? }

    struct Engine: Decodable, Sendable {
        let available: Bool?
        let limited: Bool?
    }

    let blockers: [Item]?
    let warnings: [Item]?
    let suggestEngine: String?
    let company: Company?
    let engines: [String: Engine]?

    private enum CodingKeys: String, CodingKey {
        case blockers, warnings, company, engines
        case suggestEngine = "suggest_engine"
    }
}

/// `GET /api/reports/estimates`: finished runs' time and API-equivalent cost per setting.
struct MacBureauEstimates: Decodable, Sendable {
    struct Spread: Decodable, Sendable {
        let median: Double?
        let min: Double?
        let max: Double?
    }

    struct Row: Decodable, Sendable {
        let reportType: String?
        let modelQuality: String?
        let structureMode: String?
        let engine: String?
        let samples: Int?
        let durationMs: Spread?
        let costUsd: Spread?
        let unpriced: Bool?

        private enum CodingKeys: String, CodingKey {
            case engine, samples, unpriced
            case reportType = "report_type"
            case modelQuality = "model_quality"
            case structureMode = "structure_mode"
            case durationMs = "duration_ms"
            case costUsd = "cost_usd"
        }
    }

    let minSamples: Int?
    let costNote: String?
    let estimates: [Row]?

    private enum CodingKeys: String, CodingKey {
        case estimates
        case minSamples = "min_samples"
        case costNote = "cost_note"
    }
}

/// `GET /api/companies/{id}/documents`, as far as the Evidence tab reads it: the analysed
/// documents (a row with `analysis_of`), by record id.
struct MacBureauCompanyDocuments: Decodable, Sendable {
    struct Row: Decodable, Sendable {
        let recordId: String?
        let analysisOf: String?
        let title: String?
        let filename: String?
        let uploadedAt: String?
        let capturedAt: String?

        private enum CodingKeys: String, CodingKey {
            case title, filename
            case recordId = "record_id"
            case analysisOf = "analysis_of"
            case uploadedAt = "uploaded_at"
            case capturedAt = "captured_at"
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            func text(_ key: CodingKeys) -> String? { (try? c.decodeIfPresent(String.self, forKey: key)) ?? nil }
            recordId = text(.recordId)
            title = text(.title)
            filename = text(.filename)
            uploadedAt = text(.uploadedAt)
            capturedAt = text(.capturedAt)
            // Read as JavaScript reads it: any value that is truthy.
            if let value = text(.analysisOf) {
                analysisOf = value.isEmpty ? nil : value
            } else if let flag = (try? c.decodeIfPresent(Bool.self, forKey: .analysisOf)) ?? nil {
                analysisOf = flag ? "true" : nil
            } else if let number = (try? c.decodeIfPresent(Double.self, forKey: .analysisOf)) ?? nil {
                analysisOf = number != 0 ? String(number) : nil
            } else {
                analysisOf = nil
            }
        }
    }

    struct Group: Decodable, Sendable { let rows: [Row]? }

    let groups: [Group]?
}

/// The body of `POST /api/reports`, exactly as the website builds it in `launchReport()`.
struct MacBureauGenerateReportBody: Equatable {
    let companyId: String
    let reportType: String
    let audience: String
    let language: String
    let reportMode: String
    let quality: String
    let engine: String
    /// nil reads the whole research folder; a list narrows it.
    let evidenceFiles: [String]?
    let pauseAfterEnglish: Bool
    /// nil is the server's default ceiling.
    let costCeilingUsd: Double?
    /// Only when a template was picked here; otherwise the workspace's applies.
    let memoTemplate: String?

    /// The JSON the website sends: `JSON.stringify(payload)` — the same keys, in the same
    /// order, `null` where it sends null, and `memo_template` only when it is set.
    func json() -> Data {
        var fields: [(String, String)] = [
            ("company_id", Self.string(companyId)),
            ("report_type", Self.string(reportType)),
            ("audience", Self.string(audience)),
            ("language", Self.string(language)),
            ("report_mode", Self.string(reportMode)),
            ("quality", Self.string(quality)),
            ("engine", Self.string(engine)),
            ("evidence_files", evidenceFiles.map { "[" + $0.map(Self.string).joined(separator: ",") + "]" } ?? "null"),
            ("pause_after_english", pauseAfterEnglish ? "true" : "false"),
            ("cost_ceiling_usd", costCeilingUsd.map(Self.number) ?? "null"),
        ]
        if let memoTemplate { fields.append(("memo_template", Self.string(memoTemplate))) }
        let body = "{" + fields.map { "\(Self.string($0.0)):\($0.1)" }.joined(separator: ",") + "}"
        return Data(body.utf8)
    }

    private static func string(_ value: String) -> String { jsonString(value) }

    /// A JSON string as `JSON.stringify` writes one (no escaped slashes).
    static func jsonString(_ value: String) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed, .withoutEscapingSlashes])) ?? Data("\"\"".utf8)
        return String(decoding: data, as: UTF8.self)
    }

    /// A number as JavaScript prints one: whole numbers without a decimal point, others at
    /// their shortest round-tripping form.
    private static func number(_ value: Double) -> String {
        if value.rounded() == value, abs(value) < 1e15 { return String(Int64(value)) }
        return "\(value)"
    }
}

/// The body of `POST /api/memos/studio/investigate`, as the website sends it:
/// `{company_id, report_type}` (Memo Studio takes nothing else from the dialog).
struct MacBureauStudioBody: Equatable {
    let companyId: String
    let reportType: String

    func json() -> Data {
        Data("{\"company_id\":\(MacBureauGenerateReportBody.jsonString(companyId)),\"report_type\":\(MacBureauGenerateReportBody.jsonString(reportType))}".utf8)
    }
}

/// What the website shows for a failed request: `"<status> <statusText>: <body>"`.
struct MacBureauCustomizerHTTPError: LocalizedError {
    let message: String
    var errorDescription: String? { message }

    init(message: String) { self.message = message }

    init(status: Int, body: Data) {
        let text = String(decoding: body, as: UTF8.self)
        let reason = Self.reasons[status] ?? HTTPURLResponse.localizedString(forStatusCode: status).capitalized
        message = "\(status) \(reason)" + (text.isEmpty ? "" : ": \(text)")
    }

    private static let reasons: [Int: String] = [
        400: "Bad Request", 401: "Unauthorized", 402: "Payment Required", 403: "Forbidden", 404: "Not Found",
        405: "Method Not Allowed", 408: "Request Timeout", 409: "Conflict", 410: "Gone", 413: "Content Too Large",
        422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error", 501: "Not Implemented",
        502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
    ]
}

// MARK: - The requests (made as the client makes its own: token, client header, redirects)

extension MacAPIClient {
    /// `GET /api/companies`, read for each company's legal name, parent and domain.
    func bureauCustomizerCompanyFacts() async throws -> [MacBureauCompanyFacts] {
        try await bureauCustomizerDecode("companies", method: "GET")
    }

    /// `GET /api/reports/readiness?company_id=&engine=` (10s, as the website waits).
    func bureauReportReadiness(companyId: String, engine: String) async throws -> MacBureauReadiness {
        try await bureauCustomizerDecode(
            "reports/readiness",
            method: "GET",
            query: [URLQueryItem(name: "company_id", value: companyId), URLQueryItem(name: "engine", value: engine)],
            timeout: 10
        )
    }

    /// `GET /api/reports/estimates` (10s).
    func bureauReportEstimates() async throws -> MacBureauEstimates {
        try await bureauCustomizerDecode("reports/estimates", method: "GET", timeout: 10)
    }

    /// `GET /api/companies/{id}/documents`.
    func bureauCompanyDocuments(companyId: String) async throws -> MacBureauCompanyDocuments {
        let id = companyId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? companyId
        return try await bureauCustomizerDecode("companies/\(id)/documents", method: "GET")
    }

    /// `POST /api/reports` with the website's body. Starts a paid run: only ever on the
    /// analyst's click on Generate.
    func bureauGenerateReport(_ body: MacBureauGenerateReportBody) async throws -> MacReport {
        try await bureauCustomizerDecode("reports", method: "POST", body: body.json(), timeout: 120)
    }

    /// `POST /api/memos/studio/investigate` with `{company_id, report_type}`, as the website
    /// sends it. Starts a paid run: only ever on the analyst's click.
    func bureauStudioInvestigate(_ body: MacBureauStudioBody) async throws -> MacReport {
        try await bureauCustomizerDecode("memos/studio/investigate", method: "POST", body: body.json(), timeout: 120)
    }

    private func bureauCustomizerDecode<T: Decodable>(
        _ path: String,
        method: String,
        query: [URLQueryItem] = [],
        body: Data? = nil,
        timeout: TimeInterval = 30
    ) async throws -> T {
        guard let url = MacConfig.serverURL(path, query: query) else { throw MacAPIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request, delegate: MacRedirectPolicy.shared)
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw MacBureauCustomizerHTTPError(message: error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw MacBureauCustomizerHTTPError(message: "No HTTP response")
        }
        if http.statusCode == 401, let where_ = http.url, Self.isOwnOrigin(where_) {
            Self.onUnauthorized?(where_)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw MacBureauCustomizerHTTPError(status: http.statusCode, body: data)
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw MacAPIError.decoding
        }
    }
}

// MARK: - The dialog's state

/// The dialog's choices. Like the website's dialog, which stays mounted, it keeps what was
/// chosen from one opening to the next; each opening starts the company, the search, the
/// error and the template pick afresh.
@MainActor
final class MacBureauCustomizerModel: ObservableObject {
    typealias Catalog = MacBureauCustomizer
    typealias Copy = MacBureauCustomizer.Copy

    struct EvidenceSource: Identifiable, Equatable {
        let id: String
        let label: String
        let uploadedAt: String
        var checked: Bool
    }

    struct PreflightRow: Identifiable {
        enum Tone { case blocker, warning, note }
        struct Action {
            let label: String
            let run: () -> Void
        }
        let id: String
        let tone: Tone
        let icon: String
        let text: String
        var action: Action?
    }

    // Kept from one opening to the next.
    @Published var tab: Catalog.Tab = .blueprint
    @Published private(set) var archetypeId = "auto"
    @Published var audienceId = "Internal"
    @Published private(set) var workspaceTemplate = Catalog.defaultTemplate
    @Published private(set) var selectedTemplate = Catalog.defaultTemplate
    private(set) var templateTouched = false
    @Published var reportMode = "compact"
    @Published var language = "dual"
    @Published var generationMode = "one_click"
    @Published var quality = "balanced"
    @Published var engine = "claude"
    @Published var pauseAfterEnglish = false
    @Published var costCeilingInput = ""

    // Each opening starts these afresh.
    @Published var companyId = ""
    @Published var companySearch = ""
    @Published var pickerOpen = false
    @Published private(set) var generating = false
    @Published var error: String?

    // What the server says.
    @Published private(set) var readiness: MacBureauReadiness?
    @Published private(set) var estimates: MacBureauEstimates?
    @Published private(set) var facts: [String: MacBureauCompanyFacts] = [:]
    /// The companies in the order the server lists them, which is the website's order.
    @Published private(set) var serverOrder: [String] = []
    @Published var evidence: [EvidenceSource] = []
    @Published private(set) var evidenceLoading = false
    @Published private(set) var evidenceFailed = false
    private var evidenceCompanyId: String?
    private var readinessSequence = 0

    /// The companies the dialog can pick from (the website's workspace list).
    var companies: [MacCompany] = []

    // MARK: Opening

    /// What the website does each time the dialog opens: the company the opener named (or
    /// none), a fresh search and error, the template back to the workspace's; Studio when the
    /// opener asked for it.
    func open(companyId initial: String?, generationMode initialMode: String = "") {
        companyId = initial ?? ""
        companySearch = ""
        pickerOpen = false
        error = nil
        generating = false
        templateTouched = false
        selectedTemplate = workspaceTemplate
        if initialMode == "studio_review" {
            if !archetype.studio { archetypeId = "auto" }
            generationMode = "studio_review"
            tab = .engine
        }
        Task { await loadWorkspaceTemplate() }
        Task { await loadEstimates() }
        Task { await loadFacts() }
    }

    private func loadWorkspaceTemplate() async {
        var value = Catalog.defaultTemplate
        if let settings = try? await MacAPIClient.shared.workspaceSettings() {
            let prefs = settings.preferences
            value = Self.template(from: settings.memoTemplateEffective ?? prefs?.memoTemplateEffective ?? settings.memoTemplate ?? prefs?.memoTemplate)
        }
        workspaceTemplate = value
        if !templateTouched { selectedTemplate = value }
    }

    private static func template(from raw: String?) -> String {
        raw == "ic_v2" || raw == "standard" ? raw! : Catalog.defaultTemplate
    }

    private func loadEstimates() async {
        do {
            estimates = try await MacAPIClient.shared.bureauReportEstimates()
        } catch is CancellationError {
        } catch {
            estimates = nil
        }
    }

    private func loadFacts() async {
        guard let list = try? await MacAPIClient.shared.bureauCustomizerCompanyFacts() else { return }
        facts = Dictionary(list.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        serverOrder = list.map(\.id)
    }

    /// The pre-flight: advisory, never a gate. Re-read whenever the company or the engine
    /// the run would use changes; a stale answer is dropped.
    func loadReadiness() async {
        readinessSequence += 1
        let sequence = readinessSequence
        guard !companyId.isEmpty, company != nil else {
            readiness = nil
            return
        }
        do {
            let result = try await MacAPIClient.shared.bureauReportReadiness(companyId: companyId, engine: effectiveEngine)
            if sequence == readinessSequence { readiness = result }
        } catch is CancellationError {
        } catch {
            if sequence == readinessSequence { readiness = nil }
        }
    }

    /// The analysed documents this company has, all chosen. Read again only when the company
    /// changes, so what was unticked stays unticked, as on the website.
    func loadEvidenceIfNeeded() async {
        let id = company?.id
        guard id != evidenceCompanyId else { return }
        evidenceCompanyId = id
        guard let id else {
            evidence = []
            return
        }
        evidenceLoading = true
        evidenceFailed = false
        do {
            let payload = try await MacAPIClient.shared.bureauCompanyDocuments(companyId: id)
            guard evidenceCompanyId == id else { return }
            var seen = Set<String>()
            evidence = (payload.groups ?? []).flatMap { $0.rows ?? [] }.compactMap { row in
                guard row.analysisOf != nil, let record = row.recordId, !record.isEmpty, !seen.contains(record) else { return nil }
                seen.insert(record)
                let label = [row.title, row.filename].compactMap { $0 }.first { !$0.isEmpty } ?? record
                return EvidenceSource(id: record, label: label, uploadedAt: String((row.uploadedAt ?? row.capturedAt ?? "").prefix(10)), checked: true)
            }
            evidenceLoading = false
        } catch is CancellationError {
            if evidenceCompanyId == id { evidenceCompanyId = nil }
            evidenceLoading = false
        } catch {
            guard evidenceCompanyId == id else { return }
            evidence = []
            evidenceFailed = true
            evidenceLoading = false
        }
    }

    // MARK: Choosing

    func selectArchetype(_ archetype: Catalog.Archetype) {
        guard archetype.available else { return }
        archetypeId = archetype.id
        // Memo Studio runs the memo blueprints only: a Buffett pick drops it back to One-Click.
        if !studioAvailable && generationMode == "studio_review" { generationMode = "one_click" }
    }

    func chooseTemplate(_ id: String) {
        guard !studioSelected else { return }
        templateTouched = true
        selectedTemplate = id == "ic_v2" ? "ic_v2" : "standard"
    }

    func chooseMode(_ id: String) {
        if id == "studio_review" && !studioAvailable { return }
        generationMode = id
    }

    func toggleAllEvidence() {
        let next = !allEvidenceSelected
        for index in evidence.indices { evidence[index].checked = next }
    }

    // MARK: What follows from the choices (the website's computeds)

    var company: MacCompany? { companies.first { $0.id == companyId } }
    var companyFacts: MacBureauCompanyFacts? { facts[companyId] }

    /// The workspace's companies in the website's order (the server's), for the picker.
    private var orderedCompanies: [MacCompany] {
        guard !serverOrder.isEmpty else { return companies }
        let rank = Dictionary(serverOrder.enumerated().map { ($1, $0) }, uniquingKeysWith: { first, _ in first })
        return companies.enumerated()
            .sorted { (rank[$0.element.id] ?? serverOrder.count + $0.offset, $0.offset) < (rank[$1.element.id] ?? serverOrder.count + $1.offset, $1.offset) }
            .map(\.element)
    }

    var filteredCompanies: [MacCompany] {
        let query = companySearch.trimmingCharacters(in: .whitespaces).lowercased()
        guard !query.isEmpty else { return orderedCompanies }
        return orderedCompanies.filter { company in
            let facts = self.facts[company.id]
            return [company.name, facts?.legalName, company.ticker, company.id]
                .compactMap { $0?.lowercased() }
                .contains { $0.contains(query) }
        }
    }

    var archetype: Catalog.Archetype {
        Catalog.archetypes.first { $0.id == archetypeId && $0.available } ?? Catalog.archetypes[0]
    }

    var isBuffett: Bool { archetype.id == "buffett_memo" }
    var templateApplies: Bool { archetype.template }
    var studioSelected: Bool { generationMode == "studio_review" }
    var studioAvailable: Bool { archetype.studio }
    var shownTemplate: String { studioSelected ? workspaceTemplate : selectedTemplate }
    var lengthEnabled: Bool { templateApplies && shownTemplate == "ic_v2" && !studioSelected }

    var lengthLockReason: String {
        if isBuffett { return Copy.buffettLocked }
        if studioSelected { return Copy.studioDefaults }
        return Copy.lengthLockedStandard
    }

    var audienceLocked: Bool { isBuffett || studioSelected }
    var audienceLockReason: String { isBuffett ? Copy.audienceLockedBuffett : Copy.audienceLockedStudio }
    var sentAudience: String { audienceLocked ? "Internal" : audienceId }
    var shownAudience: Catalog.Option { Catalog.audiences.first { $0.id == sentAudience } ?? Catalog.audiences[0] }

    var engineLocked: Bool { isBuffett || studioSelected }
    var effectiveEngine: String { engineLocked ? "claude" : engine }
    var engineLockReason: String { isBuffett ? Copy.engineLockedBuffett : Copy.studioDefaults }

    var qualityLocked: Bool { effectiveEngine != "claude" || isBuffett || studioSelected }
    var qualityLockReason: String {
        if isBuffett { return Copy.buffettLocked }
        if studioSelected { return Copy.studioDefaults }
        return Copy.qualityLocked
    }
    /// A Studio investigation runs at the top tier, so that is what shows while it is chosen.
    var shownQuality: String { studioSelected ? "best" : quality }

    var runControlsLocked: Bool { studioSelected }

    var costCeilingUsd: Double? {
        let raw = costCeilingInput.trimmingCharacters(in: .whitespaces)
        guard !raw.isEmpty, let number = Double(raw), number.isFinite, number > 0 else { return nil }
        return number
    }

    var costCeilingInvalid: Bool {
        !costCeilingInput.trimmingCharacters(in: .whitespaces).isEmpty && costCeilingUsd == nil
    }

    /// The length the request carries: a locked control never files a run under a length it
    /// did not have.
    var sentReportMode: String { lengthEnabled ? reportMode : "full" }

    var lengthShortLabel: String {
        guard lengthEnabled else { return "" }
        return reportMode == "full" ? Copy.lengthShortFull : Copy.lengthShortCompact
    }

    var templateShortLabel: String {
        guard templateApplies else { return "" }
        return shownTemplate == "ic_v2" ? Copy.icTemplateTag : templateName("standard")
    }

    var audienceShortLabel: String { isBuffett ? "" : shownAudience.title }

    var qualityShortLabel: String {
        if effectiveEngine != "claude" {
            return Catalog.engines.first { $0.id == effectiveEngine }?.title ?? effectiveEngine
        }
        if isBuffett || studioSelected { return "" }
        return Catalog.qualities.first { $0.id == quality }?.title ?? ""
    }

    func templateName(_ id: String) -> String {
        id == "ic_v2" ? "Founder's IC template" : "Standard memo"
    }

    /// What this run will be, in one line.
    var tagline: String {
        [archetype.title, audienceShortLabel, templateShortLabel, lengthShortLabel, studioSelected ? Copy.tagStudio : Copy.tagAutonomous]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    var footerChips: [String] {
        var chips = [archetype.title, audienceShortLabel, templateShortLabel, lengthShortLabel, qualityShortLabel].filter { !$0.isEmpty }
        if pauseAfterEnglish && !runControlsLocked { chips.append(Copy.pausePill) }
        return chips
    }

    var launchLabel: String {
        if generating { return Copy.initializing }
        let name = company?.name
        if studioSelected {
            return name.map(Copy.launchStudioFor) ?? Copy.launchStudio
        }
        return name.map(Copy.generateMemoFor) ?? Copy.generateMemo
    }

    // MARK: Which entity

    /// The legal name, the search's disambiguator and the domain, under the company's name.
    func identityLine(for company: MacCompany?) -> String {
        guard let company else { return "" }
        let facts = self.facts[company.id]
        var parts: [String] = []
        let name = (company.name ?? facts?.name ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        let legal = (facts?.legalName ?? "").trimmingCharacters(in: .whitespaces)
        if !legal.isEmpty && legal.lowercased() != name { parts.append(legal) }
        let disambiguator = (facts?.disambiguator ?? "").trimmingCharacters(in: .whitespaces)
        if !disambiguator.isEmpty { parts.append(disambiguator) }
        if let domain = Self.normalizedDomain(facts?.website ?? company.website) ?? Self.normalizedDomain(facts?.logoDomain ?? company.logoDomain) {
            parts.append(domain)
        }
        return parts.joined(separator: " · ")
    }

    /// companyLogo.js `normalizeDomain`.
    static func normalizedDomain(_ raw: String?) -> String? {
        guard var domain = raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !domain.isEmpty else { return nil }
        if let range = domain.range(of: "^[a-z][a-z0-9+.-]*://", options: .regularExpression) { domain.removeSubrange(range) }
        domain = String(domain.split(separator: "/", omittingEmptySubsequences: false).first ?? "")
        domain = String(domain.split(separator: "?", omittingEmptySubsequences: false).first ?? "")
        domain = String(domain.split(separator: "#", omittingEmptySubsequences: false).first ?? "")
        if let at = domain.lastIndex(of: "@") { domain = String(domain[domain.index(after: at)...]) }
        domain = String(domain.split(separator: ":", omittingEmptySubsequences: false).first ?? "")
        if domain.hasPrefix("www.") { domain.removeFirst(4) }
        let pattern = "^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
        return domain.range(of: pattern, options: .regularExpression) != nil ? domain : nil
    }

    /// companyLogo.js `companyNameKey`: lower case, punctuation and trailing corporate words dropped.
    private static func nameKey(_ name: String?) -> String {
        let suffixes: Set<String> = [
            "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "pbc", "plc", "sa", "ag",
            "gmbh", "holdings", "holding", "group", "technologies", "technology", "systems", "labs", "ai", "de",
        ]
        let raw = name ?? ""
        var words = raw.lowercased().split { !($0.isASCII && ($0.isLetter || $0.isNumber)) }.map(String.init)
        while words.count > 1, let last = words.last, suffixes.contains(last) { words.removeLast() }
        let slug = words.joined()
        return slug.isEmpty ? raw.trimmingCharacters(in: .whitespaces).lowercased() : slug
    }

    private var parentRecord: MacCompany? {
        guard let company, let parent = companyFacts?.parentCompany?.trimmingCharacters(in: .whitespaces), !parent.isEmpty else { return nil }
        let key = Self.nameKey(parent)
        return companies.first { candidate in
            guard candidate.id != company.id else { return false }
            let legal = facts[candidate.id]?.legalName
            return Self.nameKey(candidate.name) == key
                || (legal.map { !$0.isEmpty && Self.nameKey($0) == key } ?? false)
                || (candidate.ticker ?? "").uppercased() == parent.uppercased()
                || candidate.id.lowercased() == parent.lowercased()
        }
    }

    private var isListed: Bool {
        guard let company else { return false }
        let status = (companyFacts?.status ?? company.status ?? "").lowercased()
        return status == "public" || (companyFacts?.companyType ?? company.companyType) == "public" || !(company.ticker ?? "").isEmpty
    }

    /// The soft notes about which entity this is: the analyst decides.
    private var identityRows: [PreflightRow] {
        guard let company else { return [] }
        var rows: [PreflightRow] = []
        let status = (companyFacts?.status ?? company.status ?? "").lowercased()
        let parent = (companyFacts?.parentCompany ?? "").trimmingCharacters(in: .whitespaces)
        if !parent.isEmpty {
            let record = parentRecord
            var row = PreflightRow(
                id: "note-parent", tone: .note, icon: "building-2",
                text: record != nil ? Copy.noteSubsidiaryOf(parent) : Copy.noteSubsidiaryOfMissing(parent)
            )
            if let record {
                row.action = PreflightRow.Action(label: Copy.noteRunOnParent(record.name ?? parent)) { [weak self] in
                    self?.companyId = record.id
                }
            }
            rows.append(row)
        } else if status == "subsidiary" || status == "nonprofit" {
            rows.append(PreflightRow(id: "note-\(status)", tone: .note, icon: "building-2", text: status == "nonprofit" ? Copy.noteNonprofit : Copy.noteSubsidiary))
        }
        if !parent.isEmpty && status == "nonprofit" {
            rows.append(PreflightRow(id: "note-nonprofit", tone: .note, icon: "building-2", text: Copy.noteNonprofit))
        }
        // A listed company going through a private-round memo: the Buffett-method memo is the
        // one built to value a public stock.
        if isListed && !isBuffett && parent.isEmpty {
            var row = PreflightRow(id: "note-listed", tone: .note, icon: "info", text: Copy.noteListed)
            row.action = PreflightRow.Action(label: Copy.noteUseBuffett) { [weak self] in
                if let buffett = Catalog.archetypes.first(where: { $0.id == "buffett_memo" }) { self?.selectArchetype(buffett) }
            }
            rows.append(row)
        }
        return rows
    }

    private func blockerRow(_ item: MacBureauReadiness.Item) -> PreflightRow {
        let reset = item.resetAt.flatMap(Self.formatReset)
        var text = Self.joinSentences(item.en ?? item.code, reset.map { Copy.preflightResets(time: $0.time, relative: $0.relative) } ?? "")
        let claudeBlocker = item.code == "claude_limited" || item.code == "claude_cli_missing"
        var row = PreflightRow(id: "blocker-\(item.code)", tone: .blocker, icon: "circle-alert", text: text)
        let engines = readiness?.engines ?? [:]
        if claudeBlocker && readiness?.suggestEngine == "gemini" && !engineLocked && effectiveEngine == "claude" {
            row.action = PreflightRow.Action(label: Copy.preflightSwitchGemini) { [weak self] in self?.engine = "gemini" }
        } else if item.code == "gemini_key_missing" && (engines["claude"]?.available ?? false) && !(engines["claude"]?.limited ?? false) {
            row.action = PreflightRow.Action(label: Copy.preflightSwitchClaude) { [weak self] in self?.engine = "claude" }
        }
        if claudeBlocker && engineLocked {
            text = Self.joinSentences(text, isBuffett ? Copy.preflightClaudeOnlyBuffett : Copy.preflightClaudeOnlyStudio)
            row = PreflightRow(id: row.id, tone: row.tone, icon: row.icon, text: text, action: row.action)
        }
        return row
    }

    var preflightRows: [PreflightRow] {
        var rows: [PreflightRow] = []
        if let readiness, readiness.company?.id == company?.id {
            rows += (readiness.blockers ?? []).map(blockerRow)
            rows += (readiness.warnings ?? []).map { PreflightRow(id: "warning-\($0.code)", tone: .warning, icon: "triangle-alert", text: $0.en ?? $0.code) }
        }
        return rows + identityRows
    }

    private static func joinSentences(_ parts: String...) -> String {
        parts.filter { !$0.isEmpty }.joined(separator: " ")
    }

    /// "3:00 PM (in 2 hr.)": the local time a limit lifts, and how far off.
    private static func formatReset(_ iso: String) -> (time: String, relative: String)? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = parser.date(from: iso) ?? {
            parser.formatOptions = [.withInternetDateTime]
            return parser.date(from: iso)
        }()
        guard let date else { return nil }
        let clock = DateFormatter()
        clock.locale = Locale(identifier: "en_US")
        clock.setLocalizedDateFormatFromTemplate(Calendar.current.isDateInToday(date) ? "h:mm a" : "EEE h:mm a")
        let minutes = Int((date.timeIntervalSinceNow / 60).rounded())
        let relative = RelativeDateTimeFormatter()
        relative.locale = Locale(identifier: "en_US")
        relative.unitsStyle = .short
        relative.dateTimeStyle = .named
        var components = DateComponents()
        if abs(minutes) < 90 { components.minute = minutes } else { components.hour = Int((Double(minutes) / 60).rounded()) }
        return (clock.string(from: date), relative.localizedString(from: components))
    }

    // MARK: Estimate

    /// undefined (nothing read yet: no line), nil (no runs at this setting) or the row.
    private var estimateRow: MacBureauEstimates.Row?? {
        guard let rows = estimates?.estimates else { return .none }
        let minSamples = estimates?.minSamples ?? 3
        let report = archetype.reportType
        let model = isBuffett ? "best" : quality
        let structure = isBuffett || sentReportMode == "full" ? "full" : sentReportMode
        let row = rows.first {
            $0.reportType == report && $0.modelQuality == model && $0.structureMode == structure && $0.engine == effectiveEngine
        }
        if let row, (row.samples ?? 0) >= minSamples { return .some(row) }
        return .some(nil)
    }

    private static func roundMinutes(_ ms: Double?) -> Int? {
        guard let ms else { return nil }
        let minutes = ms / 60000
        guard minutes.isFinite, minutes > 0 else { return nil }
        return minutes < 15 ? max(1, Int(minutes.rounded())) : Int((minutes / 5).rounded()) * 5
    }

    private static func usd(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = value >= 10 ? 0 : 2
        return formatter.string(from: NSNumber(value: value)) ?? "$\(value)"
    }

    var estimateText: String {
        if studioSelected { return "" }
        guard case .some(let row) = estimateRow else { return "" }
        var parts: [String] = []
        if let row {
            let low = Self.roundMinutes(row.durationMs?.min)
            let high = Self.roundMinutes(row.durationMs?.max)
            if let low, let high, low != high {
                parts.append(Copy.estimateTimeRange(low: low, high: high))
            } else if let n = low ?? high {
                parts.append(Copy.estimateTimeAbout(n))
            }
            if !(row.unpriced ?? false), let median = row.costUsd?.median {
                parts.append(row.engine == "claude" ? Copy.estimateCostClaude(Self.usd(median)) : Copy.estimateCost(Self.usd(median)))
            } else {
                parts.append(Copy.estimateUnpriced)
            }
            parts.append(Copy.estimateSamples(row.samples ?? 0))
        } else {
            parts.append(Copy.estimateNone)
        }
        if let ceiling = costCeilingUsd { parts.append(Copy.estimateCeiling(Self.usd(ceiling))) }
        return parts.joined(separator: " · ")
    }

    var estimateNote: String? { estimates?.costNote }

    // MARK: Evidence

    var allEvidenceSelected: Bool { !evidence.isEmpty && evidence.allSatisfy(\.checked) }

    /// nil reads the whole research folder; only a deselection narrows it.
    var selectedEvidenceIds: [String]? {
        guard !evidence.isEmpty, !allEvidenceSelected else { return nil }
        return evidence.filter(\.checked).map(\.id)
    }

    var builtFromLine: String {
        if evidenceLoading || evidenceFailed { return "" }
        let total = evidence.count
        guard total > 0 else { return Copy.builtFromWebOnly }
        let chosen = evidence.filter(\.checked).count
        if chosen == 0 { return Copy.builtFromNoneSelected }
        if chosen < total { return Copy.builtFromSome(chosen, of: total) }
        return total == 1 ? Copy.builtFromOne : Copy.builtFromAll(total)
    }

    var builtFromWebOnly: Bool { !evidenceLoading && !evidenceFailed && !evidence.contains { $0.checked } }

    // MARK: Generate

    /// The request `launchReport()` builds for a one-click run.
    func generateBody(companyId: String) -> MacBureauGenerateReportBody {
        MacBureauGenerateReportBody(
            companyId: companyId,
            reportType: archetype.reportType,
            audience: sentAudience,
            // The API takes one language and it names the lead document; both are written
            // either way, so "dual" sends "en".
            language: language == "zh" ? "zh" : "en",
            reportMode: sentReportMode,
            quality: quality,
            engine: effectiveEngine,
            evidenceFiles: selectedEvidenceIds,
            pauseAfterEnglish: pauseAfterEnglish,
            costCeilingUsd: costCeilingUsd,
            memoTemplate: templateApplies && templateTouched ? selectedTemplate : nil
        )
    }

    /// The request Generate would send now, as JSON (the endpoint first): what a check of the
    /// dialog compares with the website's. Nothing is sent.
    var pendingRequest: String? {
        guard let company, archetype.available else { return nil }
        if studioSelected {
            return "POST /api/memos/studio/investigate " + String(decoding: MacBureauStudioBody(companyId: company.id, reportType: archetype.reportType).json(), as: UTF8.self)
        }
        return "POST /api/reports " + String(decoding: generateBody(companyId: company.id).json(), as: UTF8.self)
    }

    /// Starts the run — only ever from the analyst's click on Generate. Returns the new
    /// report and its company on success; on failure the error shows whole in the banner.
    func launch() async -> (report: MacReport, companyId: String)? {
        guard let company else {
            error = Copy.errorNoCompany
            return nil
        }
        guard archetype.available, !generating else { return nil }
        generating = true
        error = nil
        defer { generating = false }
        do {
            let report: MacReport
            if studioSelected {
                report = try await MacAPIClient.shared.bureauStudioInvestigate(MacBureauStudioBody(companyId: company.id, reportType: archetype.reportType))
            } else {
                report = try await MacAPIClient.shared.bureauGenerateReport(generateBody(companyId: company.id))
            }
            return (report, company.id)
        } catch is CancellationError {
            return nil
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? ""
            self.error = message.isEmpty ? Copy.errorLaunch : message
            return nil
        }
    }
}
