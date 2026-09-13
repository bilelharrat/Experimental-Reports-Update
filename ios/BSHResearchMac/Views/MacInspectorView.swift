import SwiftUI

struct MacInspectorView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                // Header
                HStack {
                    Text("Inspector")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Image(systemName: "sidebar.trailing")
                        .foregroundStyle(.secondary)
                }

                Divider()

                if let company = store.selectedCompany {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(company.name ?? company.id)
                                .font(.title3.weight(.bold))
                            Spacer()
                            if let ticker = company.ticker, !ticker.isEmpty {
                                Button {
                                    Task { await store.toggleWatchlist(ticker) }
                                } label: {
                                    Image(systemName: store.isPinned(ticker) ? "star.fill" : "star")
                                        .foregroundStyle(store.isPinned(ticker) ? Color.yellow : Color.secondary)
                                }
                                .buttonStyle(.plain)
                                .help("Toggle pinned on desk")
                            }
                        }

                        if let ticker = company.ticker {
                            Text(ticker)
                                .font(.subheadline.monospaced().weight(.semibold))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                        }

                        Text(company.subtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(12)
                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))

                    // Desk Sync Status
                    VStack(alignment: .leading, spacing: 6) {
                        Label("Desk State Sync", systemImage: "arrow.triangle.2.circlepath")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        if let ticker = company.ticker, store.isPinned(ticker) {
                            HStack(spacing: 6) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                Text("Pinned on Web & iPad Desk")
                                    .font(.caption)
                            }
                        } else {
                            Text("Not pinned to shared desk watchlist.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))

                    // Documents count
                    let reports = store.reports(for: company.id)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Research Documents (\(reports.count))")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        ForEach(reports.prefix(3)) { rep in
                            HStack {
                                Image(systemName: rep.isComplete ? "doc.text.fill" : "gearshape")
                                    .font(.caption2)
                                    .foregroundStyle(rep.isComplete ? Color.blue : Color.orange)
                                Text(rep.displayTitle)
                                    .font(.caption)
                                    .lineLimit(1)
                                Spacer()
                            }
                        }
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))

                    // Actions
                    VStack(spacing: 8) {
                        Button {
                            let url = MacConfig.webCompanyURL(id: company.id)
                            MacConfig.openInBrowser(url)
                        } label: {
                            Label("Open in Web", systemImage: "safari")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)

                        Button {
                            store.sendCopilotMessage(prompt: "Provide an investment thesis summary for \(company.name ?? company.id).")
                        } label: {
                            Label("Ask Warren", systemImage: "bubble.left.and.bubble.right.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                } else if let ticker = store.selectedTicker {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(ticker)
                            .font(.title2.monospaced().weight(.bold))
                        Text("Selected quote on Market Radar")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Button {
                            let url = MacConfig.webQuoteURL(ticker: ticker)
                            MacConfig.openInBrowser(url)
                        } label: {
                            Label("Open on Web", systemImage: "safari")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(12)
                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                } else {
                    Text("Select a company or ticker to inspect financial metadata and desk synchronization.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
        }
        .frame(minWidth: 220, idealWidth: 260, maxWidth: 320)
    }
}
