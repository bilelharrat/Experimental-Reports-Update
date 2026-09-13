import SwiftUI

struct GenerateReportSheet: View {
    let company: CompanyDetail
    var onCreated: (ReportDetail) -> Void

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.dismiss) private var dismiss

    @State private var options: ReportOptions?
    @State private var reportType = "Investment Report (Auto)"
    @State private var audience = "Internal"
    @State private var reportLanguage = "en"
    @State private var submitting = false
    @State private var error: String?
    @State private var loadingOptions = true

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(company.displayName(lang: language.language))
                        .font(.headline)
                    if let ticker = company.ticker, !ticker.isEmpty {
                        Text(ticker).font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                }

                if loadingOptions {
                    Section {
                        ProgressView(language.t("common.loading"))
                    }
                } else if let options {
                    Section {
                        Picker(language.t("research.report_type"), selection: $reportType) {
                            ForEach(options.reportTypes, id: \.self) { type in
                                Text(type).tag(type)
                            }
                        }
                        Picker(language.t("research.audience"), selection: $audience) {
                            ForEach(options.audiences, id: \.self) { a in
                                Text(a).tag(a)
                            }
                        }
                        Picker(language.t("research.language"), selection: $reportLanguage) {
                            ForEach(options.languages) { lang in
                                Text(lang.label ?? lang.code.uppercased()).tag(lang.code)
                            }
                        }
                    } header: {
                        Text(language.t("research.options"))
                    } footer: {
                        Text(language.t("research.generate_hint"))
                    }
                }

                if let error {
                    Section {
                        Text(error).foregroundStyle(.red).font(.footnote)
                    }
                }
            }
            .navigationTitle(language.t("research.generate"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.t("common.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.t("research.start")) {
                        Task { await submit() }
                    }
                    .disabled(submitting || options == nil)
                }
            }
            .task { await loadOptions() }
        }
    }

    private func loadOptions() async {
        loadingOptions = true
        defer { loadingOptions = false }
        do {
            let opts: ReportOptions = try await APIClient.shared.get("options")
            options = opts
            if !opts.reportTypes.contains(reportType) {
                reportType = opts.reportTypes.first ?? reportType
            }
            if !opts.audiences.contains(audience) {
                audience = opts.audiences.first ?? audience
            }
            if !opts.languages.map(\.code).contains(reportLanguage) {
                reportLanguage = opts.languages.first?.code ?? "en"
            }
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func submit() async {
        submitting = true
        error = nil
        defer { submitting = false }
        do {
            let body = CreateReportBody(
                companyId: company.id,
                reportType: reportType,
                audience: audience,
                language: reportLanguage
            )
            let report: ReportDetail = try await APIClient.shared.post("reports", body: body)
            onCreated(report)
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
