import SwiftUI

public struct MacCompsRailView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore

    @State private var loading = false
    @State private var loadFailed = false

    private var comps: MacComps? { store.compsByCompany[company.id] }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MacCardHeader("Comps", subtitle: "Public & private multiples comparison.", systemImage: "chart.bar.xaxis") {
                if loading { ProgressView().controlSize(.small) }
                Button {
                    Task { await reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .font(.caption)
                .buttonStyle(.plain)
                .disabled(loading)
            }

            if let priv = comps?.privateSide {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        statTile("Post-money", priv.postMoneyUsd.map(money) ?? "—")
                        statTile("Revenue / ARR", priv.revenueUsd.map(money) ?? "—")
                        statTile("Implied multiple", priv.impliedMultiple.map { String(format: "%.1fx", $0) } ?? "—")
                        statTile("Peer median P/S", comps?.peerMedianPriceToSales.map { String(format: "%.1fx", $0) } ?? "—")
                        if let diff = priv.vsPeerMedianPct {
                            statTile("vs peers", String(format: "%+.0f%%", diff), tone: diff <= 0 ? .green : .orange)
                        }
                    }
                }
            }

            // Peers Table (Horizontally Scrollable)
            VStack(alignment: .leading, spacing: 0) {
                ScrollView(.horizontal, showsIndicators: true) {
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(spacing: 0) {
                            Text("Peer").frame(width: 140, alignment: .leading)
                            Text("Price").frame(width: 75, alignment: .trailing)
                            Text("1D").frame(width: 65, alignment: .trailing)
                            Text("P/S").frame(width: 65, alignment: .trailing)
                            Text("Rev growth").frame(width: 90, alignment: .trailing)
                            Text("Gross margin").frame(width: 95, alignment: .trailing)
                            Text("Mkt cap").frame(width: 85, alignment: .trailing)
                        }
                        .font(.dsLabel)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)

                        Divider()

                        if let peers = comps?.peers, !peers.isEmpty {
                            ForEach(peers) { peer in
                                HStack(spacing: 0) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(peer.ticker)
                                            .font(.system(size: 12, weight: .semibold))
                                        Text(peer.name ?? "")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                    }
                                    .frame(width: 140, alignment: .leading)

                                    cell(peer.lastPrice.map { String(format: "$%.2f", $0) }, width: 75)
                                    cell(peer.changePct1d.map { String(format: "%+.2f%%", $0) }, width: 65,
                                         tone: (peer.changePct1d ?? 0) >= 0 ? .green : .red)
                                    cell(peer.priceToSales.map { String(format: "%.1fx", $0) }, width: 65, bold: true)
                                    cell(peer.revenueGrowth.map { String(format: "%+.0f%%", $0) }, width: 90,
                                         tone: (peer.revenueGrowth ?? 0) >= 0 ? .green : .red)
                                    cell(peer.grossMargin.map { String(format: "%.0f%%", $0) }, width: 95)
                                    cell(peer.marketCapUsd.map(money), width: 85, tone: .secondary)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 7)
                                Divider()
                            }
                        } else if loadFailed {
                            Text("Peers unavailable.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(12)
                        } else {
                            Text(loading ? "Loading peers…" : "No peers on file.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(12)
                        }
                    }
                }
            }
            .appleGlassTile(cornerRadius: 10)
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            if comps == nil { await reload() }
        }
    }

    private func reload() async {
        loading = true
        await store.fetchComps(for: company.id)
        loading = false
        loadFailed = comps == nil
    }

    private func statTile(_ label: String, _ value: String, tone: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.dsLabel).foregroundStyle(.secondary)
            Text(value).font(.dsHeadline).foregroundStyle(tone)
        }
        .padding(8)
        .appleGlassTile(cornerRadius: 8)
    }

    private func cell(_ val: String?, width: CGFloat, tone: Color = .primary, bold: Bool = false) -> some View {
        Text(val ?? "—")
            .font(bold ? .caption.monospacedDigit().weight(.bold) : .caption.monospacedDigit())
            .foregroundStyle(tone)
            .frame(width: width, alignment: .trailing)
    }

    private func money(_ amount: Double) -> String {
        if amount >= 1e9 { return String(format: "$%.1fB", amount / 1e9) }
        if amount >= 1e6 { return String(format: "$%.1fM", amount / 1e6) }
        return String(format: "$%.0fK", amount / 1e3)
    }
}
