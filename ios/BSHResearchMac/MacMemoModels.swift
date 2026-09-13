import Foundation

struct MacCompany: Identifiable, Hashable, Decodable {
    let id: String
    let name: String?
    let ticker: String?
    let companyType: String?
    let status: String?
    let sector: String?
    let industry: String?

    enum CodingKeys: String, CodingKey {
        case id, name, ticker, status, sector, industry
        case companyType = "company_type"
    }

    var title: String { name ?? id }

    var subtitle: String {
        [ticker, sector ?? industry]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

struct MacMemoFile: Decodable, Hashable {
    let language: String?
    let path: String?
    let pdfPath: String?

    enum CodingKeys: String, CodingKey {
        case language, path
        case pdfPath = "pdf_path"
    }
}

struct MacReport: Identifiable, Hashable, Decodable {
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
    let downloadUrls: [String: String]?
    let previewUrls: [String: String]?
    let memoFiles: [MacMemoFile]?

    enum CodingKeys: String, CodingKey {
        case id, audience, language, status, progress, stage, error, kind
        case companyId = "company_id"
        case companyName = "company_name"
        case reportType = "report_type"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case downloadUrls = "download_urls"
        case previewUrls = "preview_urls"
        case memoFiles = "memo_files"
    }

    /// Human title — not "Investment Memo Latestage".
    var displayTitle: String {
        let raw = (reportType ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !raw.isEmpty { return raw }
        switch (kind ?? "").lowercased() {
        case "investment_memo_latestage": return "Investment memo"
        case "buffett_memo", "buffett-memo": return "Buffett memo"
        default:
            return (kind ?? "Research memo")
                .replacingOccurrences(of: "_", with: " ")
                .replacingOccurrences(of: "-", with: " ")
                .capitalized
        }
    }

    var isComplete: Bool {
        let s = (status ?? "").lowercased()
        return s.hasPrefix("complete")
    }

    var isFailed: Bool {
        (status ?? "").lowercased().contains("fail")
    }

    /// Openable on Mac: PDF preview and/or DOCX download (most desk memos are DOCX-only).
    var canOpen: Bool {
        !(previewUrls ?? [:]).isEmpty || !(downloadUrls ?? [:]).isEmpty || !(memoFiles ?? []).isEmpty
    }

    var statusTone: String {
        let s = (status ?? "").lowercased()
        if s.hasPrefix("complete") { return "Complete" }
        if s.contains("fail") { return "Failed" }
        if s.contains("run") || s.contains("progress") || !(stage ?? "").isEmpty { return stage ?? "Running" }
        return status ?? "—"
    }

    var dateLabel: String {
        String((updatedAt ?? createdAt ?? "").prefix(10))
    }

    func documentPath(prefer language: String) -> (path: String, isPDF: Bool)? {
        if let urls = previewUrls {
            if let p = urls[language] ?? urls["en"] ?? urls["zh"] ?? urls.values.first {
                return (p, true)
            }
        }
        if let urls = downloadUrls {
            if let p = urls[language] ?? urls["en"] ?? urls["zh"] ?? urls.values.first {
                return (p, false)
            }
        }
        // Fallback: construct download URL when memo_files exist but maps omitted.
        if !(memoFiles ?? []).isEmpty {
            return ("/api/reports/\(id)/download?language=\(language)", false)
        }
        return nil
    }
}

struct MacAuthTokenResponse: Decodable {
    let token: String
}

struct MacAnnotationPayload: Decodable {
    let overlayPngBase64: String?
    let overlayUrl: String?

    enum CodingKeys: String, CodingKey {
        case overlayPngBase64 = "overlay_png_base64"
        case overlayUrl = "overlay_url"
    }
}
