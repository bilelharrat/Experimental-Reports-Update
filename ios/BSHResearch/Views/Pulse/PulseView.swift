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

    /// "Up 4 · down 2" style tally across the index strip.
    var tape: (up: Int, down: Int) {
        let rows = brief?.indices ?? []
        return (
            rows.filter { ($0.changePct1d ?? 0) > 0 }.count,
            rows.filter { ($0.changePct1d ?? 0) < 0 }.count
        )
    }
}

struct PulseView: View {
    @EnvironmentObject private var language: LanguageStore
    @StateObject private var model = PulseViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    if model.loading && model.brief == nil {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let err = model.error, model.brief == nil {
                        ContentUnavailableView {
                            Label(language.t("common.error"), systemImage: "exclamationmark.triangle")
                        } description: {
                            Text(err)
                        } actions: {
                            Button(language.t("common.retry")) { Task { await model.load() } }
                        }
                        .padding(.top, 40)
                    } else if let brief = model.brief {
                        runningBanner
                        datelineCard(brief)
                        noteCard(brief)
                        indexStrip(brief)
                        moversCard(brief)
                        alertsCard(brief)
                        calendarCard(brief)
                    } else {
                        emptyState
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 4)
                .padding(.bottom, 12)
                .readableContentWidth(AdaptiveLayout.wideReadableMaxWidth)
            }
            .background(Color(.systemGroupedBackground))
            .compactRootChrome(title: language.t("pulse.title")) {
                Menu {
                    if let brief = model.brief {
                        ShareLink(item: briefShareText(brief)) {
                            Label(language.t("common.share"), systemImage: "square.and.arrow.up")
                        }
                    }
                    Button {
                        Task { await model.buildBrief() }
                    } label: {
                        Label(language.t("pulse.build"), systemImage: "arrow.clockwise")
                    }
                    Divider()
                    Button {
                        Task { await model.writeNote(length: "long") }
                    } label: {
                        Label(language.t("pulse.note_long"), systemImage: "text.document")
                    }
                    Button {
                        Task { await model.writeNote(length: "short") }
                    } label: {
                        Label(language.t("pulse.note_short"), systemImage: "pencil.line")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.title3)
                }
                .disabled(model.building || model.writing)
            }
            .refreshable { await model.load() }
            .task { await model.load() }
        }
    }

    // MARK: - Cards

    @ViewBuilder
    private var runningBanner: some View {
        if model.building || model.writing || model.actionStatus != nil {
            VStack(alignment: .leading, spacing: 6) {
                if model.building || model.writing {
                    HStack(spacing: 10) {
                        ProgressView().controlSize(.small)
                        Text(model.building ? language.t("pulse.build") : language.t("pulse.write_note"))
                            .font(.subheadline.weight(.medium))
                        Spacer()
                    }
                    if model.writing {
                        Text(language.t("pulse.note_hint"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                if let status = model.actionStatus {
                    Label(status, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    /// Apple News Today masthead: kicker, huge date, tape chips.
    private func datelineCard(_ brief: MarketBrief) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(language.t("pulse.morning_brief").uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .tracking(1.1)
                    Text(prettyDate(brief.date))
                        .font(.system(.largeTitle, design: .serif).weight(.bold))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                Image(systemName: "sun.horizon.fill")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(.orange)
                    .symbolRenderingMode(.hierarchical)
            }
            HStack(spacing: 8) {
                tapeChip("\(model.tape.up)", systemImage: "arrow.up.right", tone: Color(.systemGreen))
                tapeChip("\(model.tape.down)", systemImage: "arrow.down.right", tone: Color(.systemRed))
                if let generated = brief.generatedAt {
                    Text(relativeStamp(generated))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.leading, 4)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func tapeChip(_ text: String, systemImage: String, tone: Color) -> some View {
        Label(text, systemImage: systemImage)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(tone)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(tone.opacity(0.12), in: Capsule())
    }

    @ViewBuilder
    private func noteCard(_ brief: MarketBrief) -> some View {
        if let note = brief.note {
            VStack(alignment: .leading, spacing: 14) {
                Text(note.headline(lang: language.language))
                    .font(.system(.title2, design: .serif).weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)

                let bullets = note.bullets(lang: language.language)
                if !bullets.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(Array(bullets.enumerated()), id: \.offset) { _, line in
                            HStack(alignment: .top, spacing: 10) {
                                Circle()
                                    .fill(Color.accentColor)
                                    .frame(width: 5, height: 5)
                                    .padding(.top, 7)
                                Text(line)
                                    .font(.callout)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }

                ForEach(note.sections(lang: language.language)) { section in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(section.title.uppercased())
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                            .tracking(0.6)
                        Text(section.body)
                            .font(.system(.body, design: .serif))
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .textSelection(.enabled)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Label(language.t("pulse.no_note"), systemImage: "text.quote")
                    .font(.headline)
                Text(language.t("pulse.no_note_hint"))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Button(language.t("pulse.note_long")) {
                    Task { await model.writeNote(length: "long") }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(model.writing)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }

    @ViewBuilder
    private func indexStrip(_ brief: MarketBrief) -> some View {
        if let rows = brief.indices, !rows.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                cardHeader(language.t("pulse.indexes"))
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(rows) { row in
                            NavigationLink {
                                QuoteDetailView(ticker: row.ticker)
                            } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(row.ticker)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    SparklineView(ticker: row.ticker)
                                    Text(QuoteRow.price(row.lastPrice, currency: nil))
                                        .font(.headline.monospacedDigit())
                                        .foregroundStyle(.primary)
                                    ChangeBadge(value: row.changePct1d)
                                }
                                .padding(14)
                                .frame(width: 132, alignment: .leading)
                                .background(Color(.secondarySystemGroupedBackground))
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func moversCard(_ brief: MarketBrief) -> some View {
        let gainers = Array((brief.movers?.gainers ?? []).prefix(6))
        let losers = Array((brief.movers?.losers ?? []).prefix(6))
        if !gainers.isEmpty {
            quoteStack(title: language.t("pulse.gainers"), rows: gainers)
        }
        if !losers.isEmpty {
            quoteStack(title: language.t("pulse.losers"), rows: losers)
        }
        if let watch = brief.watchlist, !watch.isEmpty {
            quoteStack(title: language.t("pulse.watchlist"), rows: Array(watch.prefix(8)))
        }
    }

    private func quoteStack(title: String, rows: [BriefQuoteRow]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            cardHeader(title)
            VStack(spacing: 0) {
                ForEach(rows) { row in
                    moverRow(row)
                    if row.id != rows.last?.id {
                        Divider().padding(.leading, 14)
                    }
                }
            }
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
    }

    private func moverRow(_ row: BriefQuoteRow) -> some View {
        NavigationLink {
            QuoteDetailView(ticker: row.ticker)
        } label: {
            HStack(spacing: 12) {
                Text(row.ticker)
                    .font(.headline)
                    .foregroundStyle(.primary)
                Spacer(minLength: 4)
                SparklineView(ticker: row.ticker)
                Text(QuoteRow.price(row.lastPrice, currency: nil))
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.primary)
                ChangeBadge(value: row.changePct1d)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func alertsCard(_ brief: MarketBrief) -> some View {
        if let alerts = brief.alertsLastDay, !alerts.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                cardHeader(language.t("pulse.alerts"))
                VStack(spacing: 0) {
                    ForEach(alerts.prefix(6)) { alert in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "bell.badge.fill")
                                .font(.footnote)
                                .foregroundStyle(.orange)
                                .padding(.top, 2)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(alert.message ?? "\(alert.ticker ?? "") \(alert.kind ?? "")")
                                    .font(.subheadline)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let pct = alert.changePct1d {
                                    Text(QuoteRow.pct(pct))
                                        .font(.caption.monospacedDigit().weight(.semibold))
                                        .foregroundStyle(QuoteRow.tone(pct))
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(14)
                        if alert.id != alerts.prefix(6).last?.id {
                            Divider().padding(.leading, 14)
                        }
                    }
                }
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
        }
    }

    @ViewBuilder
    private func calendarCard(_ brief: MarketBrief) -> some View {
        if let events = brief.calendar, !events.isEmpty {
            let shown = Array(events.prefix(12))
            VStack(alignment: .leading, spacing: 10) {
                cardHeader(language.t("pulse.calendar"))
                VStack(spacing: 0) {
                    ForEach(shown) { event in
                        HStack(spacing: 12) {
                            VStack(spacing: 1) {
                                Text(dayNumber(event.date))
                                    .font(.headline.monospacedDigit())
                                Text(monthLabel(event.date))
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.secondary)
                            }
                            .frame(width: 38)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(event.label)
                                    .font(.subheadline.weight(.medium))
                                    .lineLimit(2)
                                HStack(spacing: 6) {
                                    if let ticker = event.ticker, !ticker.isEmpty {
                                        Text(ticker)
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(Color.accentColor)
                                    }
                                    if let consensus = event.consensus, !consensus.isEmpty {
                                        Text("\(language.t("pulse.consensus")) \(consensus)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            Spacer(minLength: 0)
                            if event.confirmed == true {
                                Image(systemName: "checkmark.seal.fill")
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        if event.id != shown.last?.id {
                            Divider().padding(.leading, 62)
                        }
                    }
                }
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label(language.t("pulse.no_brief"), systemImage: "sun.horizon")
        } description: {
            Text(language.t("pulse.no_brief_hint"))
        } actions: {
            Button(language.t("pulse.build")) { Task { await model.buildBrief() } }
                .buttonStyle(.borderedProminent)
                .disabled(model.building)
        }
        .padding(.top, 40)
    }

    private func cardHeader(_ text: String) -> some View {
        Text(text)
            .font(.title2.weight(.bold))
    }

    // MARK: - Formatting

    private func briefShareText(_ brief: MarketBrief) -> String {
        var lines: [String] = ["BSH Morning Brief — \(brief.date ?? "")"]
        if let note = brief.note {
            let headline = note.headline(lang: language.language)
            if !headline.isEmpty { lines.append(headline) }
            for bullet in note.bullets(lang: language.language).prefix(8) {
                lines.append("• \(bullet)")
            }
        }
        if let idxs = brief.indices, !idxs.isEmpty {
            lines.append("")
            lines.append("Indexes:")
            for row in idxs.prefix(6) {
                let pct = row.changePct1d.map { String(format: "%+.1f%%", $0) } ?? "—"
                lines.append("\(row.ticker) \(pct)")
            }
        }
        return lines.joined(separator: "\n")
    }

    private func prettyDate(_ raw: String?) -> String {
        guard let raw else { return "—" }
        let parser = DateFormatter()
        parser.dateFormat = "yyyy-MM-dd"
        parser.timeZone = TimeZone(identifier: "UTC")
        guard let date = parser.date(from: raw) else { return raw }
        return date.formatted(.dateTime.weekday(.wide).month(.wide).day())
    }

    private func relativeStamp(_ raw: String) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = iso.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) else {
            return ""
        }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func dayNumber(_ raw: String?) -> String {
        guard let raw, raw.count >= 10 else { return "—" }
        return String(raw.dropFirst(8).prefix(2))
    }

    private func monthLabel(_ raw: String?) -> String {
        guard let raw, raw.count >= 7 else { return "" }
        let month = Int(raw.dropFirst(5).prefix(2)) ?? 0
        let symbols = DateFormatter().shortMonthSymbols ?? []
        guard month >= 1, month <= symbols.count else { return "" }
        return symbols[month - 1].uppercased()
    }
}

struct BriefQuoteRowView: View {
    let row: BriefQuoteRow

    var body: some View {
        HStack {
            Text(row.ticker).font(.headline)
            Spacer()
            ChangeBadge(value: row.changePct1d)
        }
        .padding(.vertical, 1)
    }
}
