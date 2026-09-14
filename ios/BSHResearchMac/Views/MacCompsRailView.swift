import SwiftUI

/// A public peer. Fundamentals stay nil until the comps endpoint (Phase 5) supplies them —
/// nothing here is estimated on the client.
struct PublicCompPeer: Identifiable, Hashable {
    var id: String { ticker }
    let ticker: String
    let name: String
    var evRevenue: Double? = nil
    var yoyGrowth: Double? = nil
    var marketCapBillions: Double? = nil
}

struct MacCompsRailView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    @State private var customPeerTickers: [String] = []

    // Default institutional peer comps based on sector
    private var defaultPeers: [PublicCompPeer] {
        let sec = (company.sector ?? "").lowercased()
        if sec.contains("health") || sec.contains("bio") {
            return [
                PublicCompPeer(ticker: "ISRG", name: "Intuitive Surgical"),
                PublicCompPeer(ticker: "VEEV", name: "Veeva Systems"),
                PublicCompPeer(ticker: "DXCM", name: "DexCom")
            ]
        } else if sec.contains("fin") || sec.contains("bank") {
            return [
                PublicCompPeer(ticker: "SQ", name: "Block"),
                PublicCompPeer(ticker: "PYPL", name: "PayPal"),
                PublicCompPeer(ticker: "AFRM", name: "Affirm Holdings")
            ]
        } else {
            // Enterprise Software / AI / Cloud default
            return [
                PublicCompPeer(ticker: "PLTR", name: "Palantir Tech"),
                PublicCompPeer(ticker: "CRWD", name: "CrowdStrike"),
                PublicCompPeer(ticker: "DDOG", name: "Datadog"),
                PublicCompPeer(ticker: "SNOW", name: "Snowflake"),
                PublicCompPeer(ticker: "MDB", name: "MongoDB")
            ]
        }
    }

    /// Live quotes for the peer set (fetched on appear; the desk watchlist rarely holds peers).
    @State private var peerQuotes: [String: MacQuote] = [:]

    /// The company's own implied multiple is only shown when a memo fact supplies it — never guessed.
    private var targetImpliedEVMultiple: Double? { nil }

    private var medianPeerMultiple: Double? {
        let vals = defaultPeers.compactMap(\.evRevenue).sorted()
        guard !vals.isEmpty else { return nil }
        let mid = vals.count / 2
        return vals.count % 2 == 0 ? (vals[mid - 1] + vals[mid]) / 2.0 : vals[mid]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Header
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Image(systemName: "chart.bar.xaxis")
                            .foregroundStyle(Color.accentColor)
                        Text("Public ↔ Private Comps Rail")
                            .font(.headline)
                        Text("LIVE PEER SET")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2.5)
                            .appleGlassPill(color: .secondary)
                    }
                    Text("Valuation benchmarking: implied target multiple vs live public trading comps")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                HStack(spacing: 6) {
                    Text(medianPeerMultiple.map { "Median: \(String(format: "%.1fx", $0)) EV/Sales" } ?? "Peer EV/Sales: not loaded")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(Color.primary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .appleGlassTile(cornerRadius: 6)
                }
            }

            if let target = targetImpliedEVMultiple, let median = medianPeerMultiple {
                HStack {
                    Text("Implied \(String(format: "%.1fx", target)) EV/Sales")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    let diff = ((target - median) / median) * 100.0
                    Text(String(format: "%+.1f%% vs peer median", diff))
                        .font(.caption.monospacedDigit().weight(.medium))
                        .foregroundStyle(diff <= 0 ? Color.green : Color.orange)
                }
            } else {
                Text("No round-implied multiple on record for \(company.title). It appears here once a memo fact supplies post-money and revenue.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Comps Peer Table
            VStack(spacing: 0) {
                // Table Header
                HStack {
                    Text("TICKER / PEER")
                        .frame(width: 160, alignment: .leading)
                    Text("PRICE")
                        .frame(width: 80, alignment: .trailing)
                    Text("1D %")
                        .frame(width: 70, alignment: .trailing)
                    Text("EV / SALES")
                        .frame(width: 90, alignment: .trailing)
                    Text("YOY GROWTH")
                        .frame(width: 90, alignment: .trailing)
                    Spacer()
                    Text("MKT CAP")
                        .frame(width: 80, alignment: .trailing)
                }
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.secondary.opacity(0.06))

                Divider()

                // Table Rows
                ForEach(defaultPeers) { peer in
                    let liveQuote = peerQuotes[peer.ticker] ?? store.watchlist.first(where: { $0.ticker == peer.ticker })
                    HStack {
                        // Ticker & Name
                        HStack(spacing: 6) {
                            Text(peer.ticker)
                                .font(.system(size: 12, weight: .bold, design: .monospaced))
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            Text(peer.name)
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .frame(width: 160, alignment: .leading)

                        // Live Price
                        Text(liveQuote?.priceText ?? "—")
                            .font(.system(size: 12, design: .monospaced))
                            .monospacedDigit()
                            .frame(width: 80, alignment: .trailing)

                        // 1D Change
                        Text(liveQuote?.pctText ?? "—")
                            .font(.system(size: 12, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle((liveQuote?.isUp ?? true) ? Color.green : Color.red)
                            .frame(width: 70, alignment: .trailing)

                        // EV/Sales
                        Text(peer.evRevenue.map { String(format: "%.1fx", $0) } ?? "—")
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .monospacedDigit()
                            .frame(width: 90, alignment: .trailing)

                        // YoY Growth
                        Text(peer.yoyGrowth.map { String(format: "%+.0f%%", $0 * 100.0) } ?? "—")
                            .font(.system(size: 12, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle((peer.yoyGrowth ?? 0) >= 0 ? Color.green : Color.red)
                            .frame(width: 90, alignment: .trailing)

                        Spacer()

                        // Mkt Cap
                        Text(peer.marketCapBillions.map { String(format: "$%.1fB", $0) } ?? "—")
                            .font(.system(size: 12, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                            .frame(width: 80, alignment: .trailing)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)

                    Divider()
                }
            }
            .appleGlassTile(cornerRadius: 10)

            // Transparency footer
            HStack(spacing: 8) {
                Image(systemName: "info.circle")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Prices and 1D moves are live quotes. EV/Sales, growth and market cap populate from the comps endpoint (not wired yet) — nothing is estimated.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
        .task(id: company.id) {
            let tickers = defaultPeers.map(\.ticker)
            if let quotes = try? await MacAPIClient.shared.fetchQuotes(tickers: tickers) {
                peerQuotes = Dictionary(uniqueKeysWithValues: quotes.map { ($0.ticker, $0) })
            }
        }
    }
}
