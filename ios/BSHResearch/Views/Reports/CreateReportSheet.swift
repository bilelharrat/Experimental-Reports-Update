import SwiftUI

struct CreateReportSheet: View {
    var initialCompanyId: String? = nil
    var initialCompanyName: String? = nil
    var onCreated: (ReportDetail) -> Void

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.dismiss) private var dismiss

    @State private var companies: [Company] = []
    @State private var selectedCompanyId: String = ""
    @State private var options: ReportOptions?
    @State private var reportType = "Investment Report (Auto)"
    @State private var audience = "Internal"
    @State private var reportLanguage = "en"
    @State private var submitting = false
    @State private var loadingOptions = true
    @State private var loadingCompanies = false
    @State private var error: String?

    init(
        initialCompanyId: String? = nil,
        initialCompanyName: String? = nil,
        onCreated: @escaping (ReportDetail) -> Void
    ) {
        self.initialCompanyId = initialCompanyId
        self.initialCompanyName = initialCompanyName
        self.onCreated = onCreated
        _selectedCompanyId = State(initialValue: initialCompanyId ?? "")
    }

    private var selectedCompany: Company? {
        companies.first { $0.id == selectedCompanyId }
    }

    var body: some View {
        NavigationStack {
            Form {
                companySection

                if !selectedCompanyId.isEmpty {
                    optionsSection
                }

                if let error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle(language.t("reports.new_report"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.t("common.cancel")) {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if submitting {
                        ProgressView()
                    } else {
                        Button(language.t("research.generate")) {
                            Task { await submit() }
                        }
                        .disabled(selectedCompanyId.isEmpty || loadingOptions || submitting)
                    }
                }
            }
            .task {
                await loadCompanies()
                await loadOptions()
            }
        }
    }

    @ViewBuilder
    private var companySection: some View {
        Section(header: Text(language.t("reports.group_by_company"))) {
            if let company = selectedCompany {
                HStack(spacing: 12) {
                    MonogramAvatar(name: company.displayName(lang: language.language), size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(company.displayName(lang: language.language))
                            .font(.headline)
                        if let ticker = company.ticker, !ticker.isEmpty {
                            Text(ticker)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    if initialCompanyId == nil {
                        Button(language.t("search.title")) {
                            selectedCompanyId = ""
                        }
                        .font(.caption)
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.vertical, 4)
            } else {
                if loadingCompanies {
                    ProgressView()
                } else {
                    Picker(language.t("reports.group_by_company"), selection: $selectedCompanyId) {
                        Text("—").tag("")
                        ForEach(companies) { c in
                            Text(c.displayName(lang: language.language) + (c.ticker.map { " (\($0))" } ?? ""))
                                .tag(c.id)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }
        }
    }

    @ViewBuilder
    private var optionsSection: some View {
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
    }

    private func loadCompanies() async {
        if !AppDataCache.shared.companies.isEmpty {
            companies = AppDataCache.shared.companies
            if selectedCompanyId.isEmpty, let first = companies.first?.id, initialCompanyId == nil {
                selectedCompanyId = first
            }
            return
        }

        loadingCompanies = true
        defer { loadingCompanies = false }
        do {
            let res: CompaniesResponse = try await APIClient.shared.get("companies")
            let list = res.companies ?? []
            companies = list
            if selectedCompanyId.isEmpty, let first = list.first?.id, initialCompanyId == nil {
                selectedCompanyId = first
            }
        } catch {
            // Non-critical
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
        guard !selectedCompanyId.isEmpty else { return }
        submitting = true
        error = nil
        defer { submitting = false }
        do {
            let body = CreateReportBody(
                companyId: selectedCompanyId,
                reportType: reportType,
                audience: audience,
                language: reportLanguage
            )
            let report: ReportDetail = try await APIClient.shared.post("reports", body: body)
            onCreated(report)
            dismiss()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
