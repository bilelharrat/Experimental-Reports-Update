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

                    // Ask Warren — suggested actions for what's on screen
                    VStack(alignment: .leading, spacing: 6) {
                        Label("Ask Warren", systemImage: "sparkles")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        if let chip = store.copilotContext.chipLabel {
                            Text(chip).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                        }
                        if let actions = store.copilotContextInfo?.actions, !actions.isEmpty {
                            ForEach(actions.prefix(5)) { action in
                                Button {
                                    store.askWarren(action.prompt, context: store.copilotContext, company: company)
                                } label: {
                                    Text(action.label).font(.caption).frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                                .disabled(!store.canRunTasks)
                            }
                        } else {
                            Button {
                                store.askWarren(
                                    "Provide an investment thesis summary for \(company.name ?? company.id).",
                                    context: store.copilotContext,
                                    company: company
                                )
                            } label: {
                                Label("Thesis summary", systemImage: "bubble.left.and.bubble.right.fill")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                            .disabled(!store.canRunTasks)
                        }
                        if let prov = store.copilotContextInfo?.provenance, !prov.sources.isEmpty {
                            Text("Sources").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                            ForEach(prov.sources.prefix(4)) { source in
                                Label(source.filename ?? source.locator ?? "source", systemImage: "doc.text")
                                    .font(.caption2)
                                    .lineLimit(1)
                                    .help(source.excerpt ?? "")
                            }
                        }
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))
                    .task(id: company.id) {
                        // Default context for the dossier: the company's top attention item, if any.
                        if store.copilotContext == .none || store.copilotContext.surface == "research" {
                            if let item = store.rollupRow(for: company.id)?.primaryAttention {
                                store.setCopilotContext(.attention(kind: item.kind ?? "", detail: item.detail, count: item.count))
                            } else {
                                store.setCopilotContext(MacCopilotContext(surface: "research", tab: "memo"))
                            }
                        }
                    }

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
