import Foundation

struct ReportOptions: Decodable {
    let reportTypes: [String]
    let audiences: [String]
    let languages: [ReportLanguageOption]

    enum CodingKeys: String, CodingKey {
        case audiences, languages
        case reportTypes = "report_types"
    }
}

struct ReportLanguageOption: Decodable, Identifiable {
    var id: String { code }
    let code: String
    let label: String?
}

struct ReportSummary: Decodable, Identifiable, Hashable {
    let id: String
    let companyId: String?
    let companyName: String?
    let reportType: String?
    let audience: String?
    let language: String?
    let status: String?
    let progress: Int?
    let stage: String?
    let error: String?
    let kind: String?
    let createdAt: String?
    let updatedAt: String?
    let streamUrl: String?
    let downloadUrls: [String: String]?
    let previewUrls: [String: String]?
    let resumeAvailable: Bool?

    enum CodingKeys: String, CodingKey {
        case id, audience, language, status, progress, stage, error, kind
        case companyId = "company_id"
        case companyName = "company_name"
        case reportType = "report_type"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case streamUrl = "stream_url"
        case downloadUrls = "download_urls"
        case previewUrls = "preview_urls"
        case resumeAvailable = "resume_available"
    }

    var isTerminal: Bool {
        let s = (status ?? "").lowercased()
        return s.hasPrefix("complete") || s.hasPrefix("failed") || s == "cancelled" || s == "awaiting_studio"
    }

    var isRunning: Bool {
        !isTerminal && !(status ?? "").isEmpty
    }

    var statusLabel: String {
        stage ?? status ?? "—"
    }
}

struct ReportDetail: Decodable, Identifiable {
    let id: String
    let companyId: String?
    let companyName: String?
    let reportType: String?
    let audience: String?
    let language: String?
    let status: String?
    let progress: Int?
    let stage: String?
    let error: String?
    let kind: String?
    let content: String?
    let contentEn: String?
    let contentZh: String?
    let streamUrl: String?
    let downloadUrls: [String: String]?
    let previewUrls: [String: String]?
    let qualityWarnings: [String]?
    let warnings: [String]?
    let resumeAvailable: Bool?
    let createdAt: String?
    let updatedAt: String?
    let analysisArtifacts: [AnalysisArtifact]?

    enum CodingKeys: String, CodingKey {
        case id, audience, language, status, progress, stage, error, kind, content, warnings
        case companyId = "company_id"
        case companyName = "company_name"
        case reportType = "report_type"
        case contentEn = "content_en"
        case contentZh = "content_zh"
        case streamUrl = "stream_url"
        case downloadUrls = "download_urls"
        case previewUrls = "preview_urls"
        case qualityWarnings = "quality_warnings"
        case resumeAvailable = "resume_available"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case analysisArtifacts = "analysis_artifacts"
    }

    func bodyText(lang: AppLanguage) -> String {
        if lang == .zh {
            return contentZh ?? contentEn ?? content ?? ""
        }
        return contentEn ?? content ?? contentZh ?? ""
    }

    var summary: ReportSummary {
        ReportSummary(
            id: id,
            companyId: companyId,
            companyName: companyName,
            reportType: reportType,
            audience: audience,
            language: language,
            status: status,
            progress: progress,
            stage: stage,
            error: error,
            kind: kind,
            createdAt: createdAt,
            updatedAt: updatedAt,
            streamUrl: streamUrl,
            downloadUrls: downloadUrls,
            previewUrls: previewUrls,
            resumeAvailable: resumeAvailable
        )
    }

    var isComplete: Bool {
        (status ?? "").lowercased().hasPrefix("complete")
    }
}

/// Markdown analysis pass attached to a finished memo run.
struct AnalysisArtifact: Decodable, Identifiable, Hashable {
    var id: String { filename ?? label ?? downloadUrl ?? UUID().uuidString }
    let label: String?
    let filename: String?
    let path: String?
    let downloadUrl: String?

    enum CodingKeys: String, CodingKey {
        case label, filename, path
        case downloadUrl = "download_url"
    }
}

struct CreateReportBody: Encodable {
    let companyId: String
    let reportType: String
    let audience: String
    let language: String
}

struct AutocompleteHit: Decodable, Identifiable, Hashable {
    var id: String { stableId }
    let source: String?
    let companyId: String?
    let ticker: String?
    let name: String?
    let sector: String?
    let industry: String?
    let category: String?
    let description: String?
    let status: String?
    let companyType: String?
    let exchange: String?

    enum CodingKeys: String, CodingKey {
        case source, ticker, name, sector, industry, category, description, status, exchange
        case companyId = "id"
        case companyType = "company_type"
    }

    var stableId: String {
        companyId ?? "\(source ?? "hit"):\(name ?? ticker ?? UUID().uuidString)"
    }

    var hasLocalId: Bool { companyId != nil }
}

struct SelectCompanyBody: Encodable {
    let name: String
    let ticker: String?
    let description: String?
    let sector: String?
    let industry: String?
    let exchange: String?
    let status: String?
    let companyType: String?
}

struct DeepSearchStart: Decodable {
    let cached: Bool?
    let source: String?
    let matches: [AutocompleteHit]?
    let cachedAt: String?
    let jobId: String?
    let streamUrl: String?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case cached, source, matches, status
        case cachedAt = "cached_at"
        case jobId = "job_id"
        case streamUrl = "stream_url"
    }
}

struct CompanyDetail: Decodable, Identifiable {
    let id: String
    let name: String?
    let ticker: String?
    let companyType: String?
    let status: String?
    let sector: String?
    let industry: String?
    let description: String?
    let website: String?
    let nameZh: String?
    let descriptionZh: String?
    let traderSnapshot: TraderSnapshot?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector, industry, description, website
        case companyType = "company_type"
        case nameZh = "name_zh"
        case descriptionZh = "description_zh"
        case traderSnapshot = "trader_snapshot"
    }

    var isPublic: Bool {
        let type = (companyType ?? "").lowercased()
        let st = (status ?? "").lowercased()
        return type == "public" || st == "public"
    }

    func displayName(lang: AppLanguage) -> String {
        if lang.prefersChineseContent, let nameZh, !nameZh.isEmpty { return nameZh }
        return name ?? id
    }

    func displayDescription(lang: AppLanguage) -> String {
        if lang.prefersChineseContent, let descriptionZh, !descriptionZh.isEmpty { return descriptionZh }
        return description ?? ""
    }
}
