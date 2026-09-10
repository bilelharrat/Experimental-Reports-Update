import SwiftUI

@MainActor
final class PulseViewModel: ObservableObject {
    @Published var brief: MarketBrief?
    @Published var loading = false
    @Published var building = false
    @Published var writing = false
    @Published var actionStatus: String?
    @Published var error: String?

    func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            brief = try await APIClient.shared.get("market-brief")
        } catch let err as APIError {
            if case .http(let status, _) = err, status == 404 {
                brief = nil
            } else {
                error = err.errorDescription
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Rebuild today's market brief (fetches fresh quotes/movers server-side).
    func buildBrief() async {
        building = true
        actionStatus = nil
        defer { building = false }
        do {
            let _: JSONBlob = try await APIClient.shared.post("market-brief/run", timeout: 240)
            actionStatus = nil
            await load()
        } catch {
            actionStatus = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Ask the model to write/rewrite the desk note (slow: LLM call).
    func writeNote(length: String) async {
        writing = true
        actionStatus = nil
        defer { writing = false }
        do {
            struct Body: Encodable { let length: String }
            let _: JSONBlob = try await APIClient.shared.post(
                "market-brief/note", body: Body(length: length), timeout: 540
            )
            actionStatus = nil
            await load()
        } catch {
            actionStatus = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct PulseView: View {
    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model = PulseViewModel()

    var body: some View {
        NavigationStack {
            List {
                actionsSection
                if model.loading && model.brief == nil {
                    ProgressView(language.t("common.loading"))
                        .frame(maxWidth: .infinity, alignment: .center)
                        .listRowSeparator(.hidden)
                } else if let err = model.error, model.brief == nil {
                    ContentUnavailableView {
                        Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
                    } description: {
                        Text(err)
                    } actions: {
                        Button(language.t("common.retry")) { Task { await model.load() } }
                    }
                    .listRowSeparator(.hidden)
                } else if let brief = model.brief {
                    Section(language.t("pulse.brief")) {
                        if let date = brief.date {
                            Text(date).font(.subheadline).foregroundStyle(.secondary)
                        }
                        if let note = brief.note {
                            Text(note.headline(lang: language.language))
                                .font(.headline)
                            ForEach(Array(note.bullets(lang: language.language).enumerated()), id: \.offset) { _, line in
                                Text("• \(line)").font(.body)
                            }
                            ForEach(note.sections(lang: language.language)) { section in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(section.title).font(.subheadline.weight(.semibold))
                                    Text(section.body).font(.body).foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 4)
                            }
                        }
                    }

                    if let indices = brief.indices, !indices.isEmpty {
                        Section(language.t("market.indexes")) {
                            ForEach(indices.prefix(8)) { row in
                                BriefQuoteRowView(row: row)
                            }
                        }
                    }

                    if let gainers = brief.movers?.gainers, !gainers.isEmpty {
                        Section(language.t("pulse.gainers")) {
                            ForEach(gainers.prefix(6)) { row in
                                BriefQuoteRowView(row: row)
                            }
                        }
                    }

                    if let losers = brief.movers?.losers, !losers.isEmpty {
                        Section(language.t("pulse.losers")) {
                            ForEach(losers.prefix(6)) { row in
                                BriefQuoteRowView(row: row)
                            }
                        }
                    }
                } else {
                    ContentUnavailableView(language.t("pulse.no_brief"), systemImage: "doc.text")
                        .listRowSeparator(.hidden)
                }
            }
            .listStyle(.insetGrouped)
            .compactRootChrome(title: language.t("pulse.title"))
            .refreshable { await model.load() }
            .task { await model.load() }
        }
    }

    private var actionsSection: some View {
        Section {
            Button {
                Task { await model.buildBrief() }
            } label: {
                HStack {
                    Label(language.t("pulse.build"), systemImage: "hammer")
                    if model.building { Spacer(); ProgressView().controlSize(.small) }
                }
            }
            .disabled(model.building || model.writing)

            Menu {
                Button(language.t("pulse.note_short")) {
                    Task { await model.writeNote(length: "short") }
                }
                Button(language.t("pulse.note_long")) {
                    Task { await model.writeNote(length: "long") }
                }
            } label: {
                HStack {
                    Label(language.t("pulse.write_note"), systemImage: "pencil.and.outline")
                    if model.writing { Spacer(); ProgressView().controlSize(.small) }
                }
            }
            .disabled(model.building || model.writing)

            if let status = model.actionStatus {
                Text(status).font(.caption).foregroundStyle(.red)
            }
        } footer: {
            if model.writing {
                Text(language.t("pulse.note_hint"))
            }
        }
    }
}

struct BriefQuoteRowView: View {
    let row: BriefQuoteRow

    var body: some View {
        HStack {
            Text(row.ticker).font(.headline.monospaced())
            Spacer()
            Text(QuoteRow.pct(row.changePct1d))
                .font(.body.monospacedDigit().weight(.semibold))
                .foregroundStyle(QuoteRow.tone(row.changePct1d))
        }
    }
}
