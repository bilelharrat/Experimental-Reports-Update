import SwiftUI

/// One row per thesis claim: evidence status, the latest tracked news that touched it, and the
/// standing decision. Click a claim to jump to that passage in the memo (when a memo window is driving `onFind`).
struct MacThesisTrackerView: View {
    let company: MacCompany
    var onFind: ((String) -> Void)? = nil
    @EnvironmentObject private var store: MacAppStore

    private struct Row: Identifiable {
        let id: String
        let kind: String        // "highlight" | "risk"
        let claim: String
        let detail: String?
        let evidenceStatus: String   // supported | contradicted | mixed | missing
        let evidenceMatches: Int
        let latestNews: MacTrackingItem?
    }

    private var analysis: MacMemoAnalysis? { store.analysisByCompany[company.id] }
    private var evidence: MacEvidenceMatrix? { store.evidenceByCompany[company.id] }
    private var tracking: MacTrackingUpdates? { store.trackingByCompany[company.id] }
    private var decision: MacDecision? { store.latestDecision(for: company.id) }

    private static let stopwords: Set<String> = [
        "about", "above", "after", "again", "against", "their", "there", "these", "those", "which", "while",
        "would", "could", "should", "because", "before", "between", "through", "under", "where", "other",
        "company", "market", "business", "revenue", "growth", "customers", "product", "products", "still",
    ]

    private static func keywords(_ text: String) -> Set<String> {
        Set(text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { $0.count >= 5 && !stopwords.contains($0) })
    }

    private var rows: [Row] {
        guard let spine = analysis?.thesisSpine else { return [] }
        let claims = spine.investmentHighlights.map { ("highlight", $0) } + spine.investmentRisks.map { ("risk", $0) }
        let evidenceRows = evidence?.claims ?? []
        let news = tracking?.items ?? []
        return claims.compactMap { kind, claim in
            guard let text = claim.claim, !text.isEmpty else { return nil }
            let words = Self.keywords(text + " " + (claim.detail ?? ""))
            let matches = evidenceRows.filter { Self.keywords($0.claim).intersection(words).count >= 2 }
            let status: String
            if matches.contains(where: { $0.status == "contradicted" }) { status = "contradicted" }
            else if matches.contains(where: { $0.status == "mixed" }) { status = "mixed" }
            else if matches.contains(where: { $0.status == "supported" || $0.status == "partial" }) { status = "supported" }
            else { status = "missing" }
            let hit = news
                .filter { Self.keywords(($0.title ?? "") + " " + ($0.summary ?? "")).intersection(words).count >= 2 }
                .sorted { ($0.publishedAt ?? "") > ($1.publishedAt ?? "") }
                .first
            return Row(id: claim.id + kind, kind: kind, claim: text, detail: claim.detail, evidenceStatus: status, evidenceMatches: matches.count, latestNews: hit)
        }
    }

    @Environment(\.bureauResearchDesk) private var bureauDesk
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if BSHDesign.active == .bureau && bureauDesk {
            bureauBody
        } else {
            glassBody
        }
    }

    private var glassBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Thesis tracker", systemImage: "point.3.connected.trianglepath.dotted").font(.dsHeadline)
                Spacer()
                if let decision {
                    MacStatusPill(text: decision.verdictLabel, color: decision.verdict == "invest" ? .green : (decision.verdict == "pass" ? .red : .orange))
                }
                Button {
                    Task {
                        await store.loadMemoAnalysis(company.id)
                        await store.loadEvidence(company.id)
                        await store.loadTracking(company.id, sync: false)
                    }
                } label: {
                    Label(analysis == nil ? "Load thesis" : "Refresh", systemImage: "arrow.clockwise")
                }
                .controlSize(.small)
                .disabled(store.analysisBusy.contains(company.id))
            }

            if analysis == nil {
                Text("Loads the thesis spine, the evidence matrix and tracked news for this company.")
                    .font(.ui(.caption)).foregroundStyle(.secondary)
            } else if rows.isEmpty {
                Text("No thesis spine yet — run the Thesis Spine tool in IC Prep.")
                    .font(.ui(.caption)).foregroundStyle(.secondary)
            } else {
                ForEach(rows) { row in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: row.kind == "highlight" ? "arrow.up.right.circle" : "exclamationmark.shield")
                            .foregroundStyle(row.kind == "highlight" ? Color.green : Color.red)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            if let onFind {
                                Button { onFind(row.claim) } label: {
                                    Text(row.claim).font(.ui(.subheadline).weight(.medium)).multilineTextAlignment(.leading)
                                }
                                .buttonStyle(.link)
                                .help("Jump to this passage in the memo")
                            } else {
                                Text(row.claim).font(.ui(.subheadline).weight(.medium))
                            }
                            HStack(spacing: 8) {
                                MacStatusPill(text: statusLabel(row.evidenceStatus), color: statusColor(row.evidenceStatus))
                                if row.evidenceMatches > 0 {
                                    Text("\(row.evidenceMatches) evidence claim(s)").font(.ui(.caption2)).foregroundStyle(.secondary)
                                }
                            }
                            if let news = row.latestNews {
                                HStack(spacing: 4) {
                                    Image(systemName: "newspaper").font(.ui(.caption2))
                                    Text(news.title ?? "").font(.ui(.caption)).lineLimit(1)
                                    Text(MacTimeFormat.relative(news.publishedAt ?? news.capturedAt)).font(.ui(.caption2)).foregroundStyle(.tertiary)
                                    MacStatusPill(text: news.impact.capitalized, color: news.impact == "high" ? .red : (news.impact == "medium" ? .orange : .secondary))
                                }
                                .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                    }
                    .padding(8)
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding()
        .appleGlassCard()
        .task(id: company.id) {
            if analysis != nil {
                if evidence == nil { await store.loadEvidence(company.id) }
                if tracking == nil { await store.loadTracking(company.id, sync: false) }
            }
        }
    }

    private func statusLabel(_ s: String) -> String {
        switch s {
        case "supported": return "Supported"
        case "contradicted": return "Contradicted"
        case "mixed": return "Mixed"
        default: return "No evidence"
        }
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case "supported": return .green
        case "contradicted": return .red
        case "mixed": return .orange
        default: return .secondary
        }
    }
}

// MARK: - Bureau

/// ThesisTrackerCard.vue on the Research Desk: the title, the standing decision and Load /
/// Refresh, then one row per thesis claim with its evidence status and the latest news that
/// touched it.
extension MacThesisTrackerView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let busy = store.analysisBusy.contains(company.id)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("waypoints", size: 16)
                    .foregroundStyle(ink.accent)
                MacBureauDeskCaption(text: "Thesis tracker", size: 15, weight: .semibold, lineHeight: 18.75, color: ink.label)
                Spacer(minLength: 0)
                if let decision {
                    MacBureauDeskPill(text: decision.verdictLabel, tint: bureauVerdictTint(decision.verdict, ink))
                }
                Button {
                    Task {
                        await store.loadMemoAnalysis(company.id)
                        await store.loadEvidence(company.id)
                        await store.loadTracking(company.id, sync: false)
                    }
                } label: {
                    HStack(spacing: 4) {
                        if busy {
                            MacBureauDeskSpinner(size: 11)
                        } else {
                            MacBureauDeskIcon("rotate-cw", size: 12)
                        }
                        MacBureauDeskButtonLabel(title: analysis == nil ? "Load thesis" : "Refresh", size: .small)
                    }
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(busy)
                .fixedSize()
            }

            if analysis == nil {
                MacBureauWebParagraph(text: "Loads the thesis spine, the evidence matrix and tracked news for this company.", size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.secondary)
            } else if rows.isEmpty {
                MacBureauWebParagraph(text: "No thesis spine yet — run the Thesis Spine tool in IC Prep.", size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.secondary)
            } else {
                ForEach(rows) { row in
                    bureauRow(row, ink: ink)
                }
            }
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            if analysis != nil {
                if evidence == nil { await store.loadEvidence(company.id) }
                if tracking == nil { await store.loadTracking(company.id, sync: false) }
            }
        }
    }

    private func bureauRow(_ row: Row, ink: MacBureauDeskInk) -> some View {
        HStack(alignment: .top, spacing: 10) {
            MacBureauDeskIcon(row.kind == "highlight" ? "circle-arrow-out-up-right" : "shield-alert", size: 14)
                .foregroundStyle(row.kind == "highlight" ? ink.green : ink.red)
                .frame(width: 18)
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 3) {
                if let onFind {
                    Button {
                        onFind(row.claim)
                    } label: {
                        MacBureauWebParagraph(text: row.claim, size: 11, lineHeight: 14.3)
                            .foregroundStyle(ink.label)
                    }
                    .buttonStyle(MacBureauFlatButtonStyle())
                    .help("Jump to this passage in the memo")
                } else {
                    MacBureauWebParagraph(text: row.claim, size: 11, lineHeight: 14.3)
                        .foregroundStyle(ink.label)
                }
                HStack(spacing: 8) {
                    MacBureauDeskPill(text: statusLabel(row.evidenceStatus), tint: bureauStatusTint(row.evidenceStatus, ink))
                    if row.evidenceMatches > 0 {
                        MacBureauDeskCaption(text: "\(row.evidenceMatches) evidence claim(s)", color: ink.secondary)
                    }
                }
                if let news = row.latestNews {
                    HStack(spacing: 4) {
                        MacBureauDeskIcon("newspaper", size: 12)
                        Text(news.title ?? "")
                            .font(BSHType.bureauSans(10))
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .bureauDeskLine(12.5, 10)
                            .layoutPriority(-1)
                        MacBureauDeskCaption(text: MacBureauMemoFormat.relative(news.publishedAt ?? news.capturedAt), color: ink.tertiary)
                        if !news.impact.isEmpty {
                            MacBureauDeskPill(
                                text: news.impact.prefix(1).uppercased() + news.impact.dropFirst(),
                                tint: news.impact == "high" ? ink.red : (news.impact == "medium" ? ink.orange : ink.secondary)
                            )
                        }
                    }
                    .foregroundStyle(ink.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.secondary.opacity(0.04))
    }

    private func bureauVerdictTint(_ verdict: String?, _ ink: MacBureauDeskInk) -> Color {
        switch verdict {
        case "invest": return ink.green
        case "pass": return ink.red
        default: return ink.orange
        }
    }

    private func bureauStatusTint(_ status: String, _ ink: MacBureauDeskInk) -> Color {
        switch status {
        case "supported": return ink.green
        case "contradicted": return ink.red
        case "mixed": return ink.orange
        default: return ink.secondary
        }
    }
}
