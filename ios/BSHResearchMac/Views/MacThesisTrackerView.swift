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

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Thesis Tracker", systemImage: "point.3.connected.trianglepath.dotted").font(.headline)
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
                    .font(.caption).foregroundStyle(.secondary)
            } else if rows.isEmpty {
                Text("No thesis spine yet — run the Thesis Spine tool in IC Prep.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(rows) { row in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: row.kind == "highlight" ? "arrow.up.right.circle" : "exclamationmark.shield")
                            .foregroundStyle(row.kind == "highlight" ? Color.green : Color.red)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            if let onFind {
                                Button { onFind(row.claim) } label: {
                                    Text(row.claim).font(.subheadline.weight(.medium)).multilineTextAlignment(.leading)
                                }
                                .buttonStyle(.link)
                                .help("Jump to this passage in the memo")
                            } else {
                                Text(row.claim).font(.subheadline.weight(.medium))
                            }
                            HStack(spacing: 8) {
                                MacStatusPill(text: statusLabel(row.evidenceStatus), color: statusColor(row.evidenceStatus))
                                if row.evidenceMatches > 0 {
                                    Text("\(row.evidenceMatches) evidence claim(s)").font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            if let news = row.latestNews {
                                HStack(spacing: 4) {
                                    Image(systemName: "newspaper").font(.caption2)
                                    Text(news.title ?? "").font(.caption).lineLimit(1)
                                    Text(MacTimeFormat.relative(news.publishedAt ?? news.capturedAt)).font(.caption2).foregroundStyle(.tertiary)
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
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
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
