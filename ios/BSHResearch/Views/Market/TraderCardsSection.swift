import SwiftUI

/// Six-card trader snapshot for public companies, embedded in the company
/// research screen. Refresh kicks the server job and tails its SSE stream.
struct TraderCardsSection: View {
    let companyId: String
    let snapshot: TraderSnapshot?
    var onRefreshed: () -> Void

    @EnvironmentObject private var language: LanguageStore
    @State private var refreshing = false
    @State private var refreshStatus = ""
    @State private var refreshError: String?
    @State private var confirmRefresh = false

    var body: some View {
        Section {
            Button {
                // A trader refresh re-runs the Claude snapshot passes, so
                // it asks first (owner policy 2026-09-15).
                confirmRefresh = true
            } label: {
                HStack {
                    Label(
                        refreshing ? language.t("trader.refreshing") : language.t("trader.refresh"),
                        systemImage: "arrow.clockwise.circle"
                    )
                    if refreshing { Spacer(); ProgressView().controlSize(.small) }
                }
            }
            .disabled(refreshing)
            if refreshing && !refreshStatus.isEmpty {
                Text(refreshStatus).font(.caption).foregroundStyle(.secondary)
            }
            if let err = refreshError {
                Text(err).font(.caption).foregroundStyle(.red)
            }

            if let snapshot, !snapshot.isEmpty {
                if let price = snapshot.priceCard {
                    priceCard(price)
                }
                if let momentum = snapshot.momentumCard {
                    textCard(
                        title: language.t("trader.momentum"),
                        badge: momentum.trend?.capitalized,
                        body: momentum.trendText(lang: language.language)
                    )
                }
                if let sentiment = snapshot.sentimentCard {
                    sentimentCard(sentiment)
                }
                if let catalysts = snapshot.catalysts, !catalysts.isEmpty {
                    catalystsCard(catalysts)
                }
                if let news = snapshot.traderNews, !news.isEmpty {
                    newsCard(news)
                }
                if let movers = snapshot.techMovers?.movers, !movers.isEmpty {
                    moversCard(movers)
                }
            } else if !refreshing {
                Text(language.t("trader.empty"))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text(language.t("trader.title"))
        } footer: {
            if let at = snapshot?.refreshedAt {
                Text(language.t("trader.refreshed_at").replacingOccurrences(of: "{t}", with: String(at.prefix(16)).replacingOccurrences(of: "T", with: " ")))
            }
        }
        .confirmationDialog(
            language.t("tokens.confirm"),
            isPresented: $confirmRefresh,
            titleVisibility: .visible
        ) {
            Button(language.t("tokens.confirm_continue")) {
                Task { await refresh() }
            }
            Button(language.t("common.cancel"), role: .cancel) {}
        }
    }

    // MARK: Cards

    private func priceCard(_ card: TraderPriceCard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            cardTitle(language.t("trader.price"))
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(QuoteRow.price(card.lastPrice, currency: card.currency))
                    .font(.title3.monospacedDigit().weight(.bold))
                Text(QuoteRow.pct(card.changePct1d))
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .foregroundStyle(QuoteRow.tone(card.changePct1d))
            }
            HStack(spacing: 12) {
                pctChip("5D", card.changePct5d)
                pctChip("30D", card.changePct30d)
                pctChip("YTD", card.changePctYtd)
                pctChip("1Y", card.changePct1y)
            }
            if card.vsSp50030dPct != nil || card.vsSector30dPct != nil {
                HStack(spacing: 12) {
                    if let v = card.vsSp50030dPct {
                        Text("vs S&P 30d \(QuoteRow.pct(v))")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(QuoteRow.tone(v))
                    }
                    if let v = card.vsSector30dPct {
                        Text("vs sector 30d \(QuoteRow.pct(v))")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(QuoteRow.tone(v))
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func pctChip(_ label: String, _ value: Double?) -> some View {
        VStack(spacing: 1) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(QuoteRow.pct(value))
                .font(.caption.monospacedDigit().weight(.semibold))
                .foregroundStyle(QuoteRow.tone(value))
        }
    }

    private func textCard(title: String, badge: String?, body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                cardTitle(title)
                if let badge, !badge.isEmpty {
                    Text(badge)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(.tertiarySystemFill), in: Capsule())
                }
            }
            Text(body).font(.footnote)
        }
        .padding(.vertical, 4)
    }

    private func sentimentCard(_ card: TraderSentimentCard) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            cardTitle(language.t("trader.sentiment"))
            Text(card.consensusText(lang: language.language)).font(.footnote)
            if let target = card.targetPrice, let mean = target.mean {
                Text("Target \(QuoteRow.price(mean, currency: nil))  ·  \(QuoteRow.price(target.low, currency: nil)) – \(QuoteRow.price(target.high, currency: nil))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func catalystsCard(_ catalysts: [TraderCatalyst]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            cardTitle(language.t("trader.catalysts"))
            ForEach(catalysts.prefix(4)) { c in
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        if let date = c.date {
                            Text(date).font(.caption2.monospaced()).foregroundStyle(.secondary)
                        }
                        if let type = c.type {
                            Text(type).font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                    Text(c.titleText(lang: language.language))
                        .font(.footnote.weight(.medium))
                        .lineLimit(2)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func newsCard(_ news: [TraderNewsItem]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            cardTitle(language.t("trader.news"))
            ForEach(news.prefix(4)) { n in
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        if let date = n.date {
                            Text(date).font(.caption2.monospaced()).foregroundStyle(.secondary)
                        }
                        if let bias = n.bias {
                            Text(bias)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(bias == "positive" ? .green : bias == "negative" ? .red : .secondary)
                        }
                    }
                    Text(n.headlineText(lang: language.language))
                        .font(.footnote)
                        .lineLimit(2)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func moversCard(_ movers: [TraderMover]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            cardTitle(language.t("trader.movers"))
            ForEach(movers.prefix(5)) { m in
                HStack {
                    Text(m.ticker ?? "—").font(.caption.monospaced().weight(.semibold))
                    Text(m.companyText(lang: language.language))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Spacer()
                    Text(QuoteRow.pct(m.changePct1d))
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(QuoteRow.tone(m.changePct1d))
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func cardTitle(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.caption2.weight(.bold))
            .foregroundStyle(.secondary)
    }

    // MARK: Refresh

    private func refresh() async {
        refreshing = true
        refreshError = nil
        refreshStatus = language.t("trader.refreshing")
        defer { refreshing = false }
        do {
            let start: TraderRefreshStart = try await APIClient.shared.post(
                "companies/\(companyId)/trader/refresh"
            )
            guard let streamPath = start.streamUrl else {
                onRefreshed()
                return
            }
            let client = SSEClient()
            for try await event in await client.stream(path: streamPath) {
                guard let data = event.data.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }
                let type = (obj["type"] as? String) ?? ""
                if type == "stage" {
                    refreshStatus = (obj["message"] as? String)
                        ?? (obj["stage"] as? String) ?? refreshStatus
                } else if type == "done" {
                    break
                } else if type == "error" {
                    refreshError = (obj["error"] as? String) ?? "Refresh failed"
                    return
                }
            }
            onRefreshed()
        } catch {
            refreshError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
