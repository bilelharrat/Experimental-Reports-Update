import SwiftUI

/// Public ↔ private comps, served by `/api/companies/{id}/comps`.
/// Peer numbers are Nasdaq quote + annual income statement; the private multiple only
/// appears when the memo states post-money and revenue. Every figure names its source.
struct MacCompsRailView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    @State private var newPeer = ""
    @State private var editingPeers = false
    @State private var loading = false
    @State private var loadFailed = false
    @State private var saving = false
    @State private var peerError: String?
    @State private var peerTickers: [String]?

    private var comps: MacComps? { store.compsByCompany[company.id] }

    private var canEditPeers: Bool { store.canWriteDesk && peerTickers != nil && !loading }

    private var listedTickers: [String] { peerTickers ?? comps?.peers.map(\.ticker) ?? [] }

    private func fetchedPeer(_ ticker: String) -> MacCompPeer? {
        comps?.peers.first { $0.ticker == ticker }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MacCardHeader("Comps", subtitle: "Peer price-to-sales from live quotes and annual revenue; the private multiple only when the memo states post-money and revenue.", systemImage: "chart.bar.xaxis") {
                if loading || saving { ProgressView().controlSize(.small) }
                Button {
                    editingPeers.toggle()
                } label: {
                    Label(editingPeers ? "Done" : "Edit peers", systemImage: "slider.horizontal.3")
                }
                .controlSize(.small)
                .disabled(!canEditPeers)
                .help(peerTickers == nil ? "Peers can be edited once the saved list has loaded" : "Add or remove peer tickers")
                Button {
                    Task { await reload(refresh: true) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .controlSize(.small)
                .disabled(loading)
            }

            if let priv = comps?.privateSide {
                HStack(spacing: 16) {
                    stat("Post-money (memo)", priv.postMoneyUsd.map(money) ?? "—")
                    stat("Revenue / ARR (memo)", priv.revenueUsd.map(money) ?? "—")
                    stat("Implied multiple", priv.impliedMultiple.map { String(format: "%.1fx", $0) } ?? "—")
                    stat("Peer median P/S", comps?.peerMedianPriceToSales.map { String(format: "%.1fx", $0) } ?? "—")
                    if let diff = priv.vsPeerMedianPct {
                        stat("vs peers", String(format: "%+.0f%%", diff), color: diff <= 0 ? .green : .orange)
                    }
                }
                if priv.impliedMultiple == nil {
                    Text(priv.postMoneyUsd == nil
                         ? "No post-money on record for \(company.title): the memo doesn't state one yet."
                         : "The memo states a post-money but no revenue figure, so no multiple is implied.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if !priv.sources.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(priv.sources, id: \.self) { source in
                                Label("\(source.field ?? "fact") · \(source.section ?? "memo")", systemImage: "doc.text")
                                    .font(.caption2)
                                    .padding(.horizontal, 6).padding(.vertical, 3)
                                    .background(Color.secondary.opacity(0.1), in: Capsule())
                                    .help(source.excerpt ?? "")
                            }
                        }
                    }
                }
            }

            if editingPeers {
                HStack(spacing: 8) {
                    TextField("Add ticker", text: $newPeer)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 120)
                        .onSubmit { addPeer() }
                        .disabled(saving || !canEditPeers)
                    Button("Add") { addPeer() }
                        .controlSize(.small)
                        .disabled(newPeer.trimmingCharacters(in: .whitespaces).isEmpty || saving || !canEditPeers)
                    if let peerError {
                        Label(peerError, systemImage: "exclamationmark.triangle")
                            .font(.dsCaption)
                            .foregroundStyle(Color.dsNegative)
                            .lineLimit(1)
                    }
                    Spacer()
                }
            }

            VStack(spacing: 0) {
                HStack {
                    Text("Peer").frame(width: 190, alignment: .leading)
                    Text("Price").frame(width: 80, alignment: .trailing)
                    Text("1D").frame(width: 70, alignment: .trailing)
                    Text("P/S").frame(width: 70, alignment: .trailing)
                    Text("Revenue growth").frame(width: 100, alignment: .trailing)
                    Text("Gross margin").frame(width: 110, alignment: .trailing)
                    Spacer()
                    Text("Market cap").frame(width: 90, alignment: .trailing)
                    if editingPeers { Text("").frame(width: 28) }
                }
                .font(.dsLabel)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)

                Divider()

                if !listedTickers.isEmpty {
                    ForEach(listedTickers, id: \.self) { ticker in
                        let peer = fetchedPeer(ticker)
                        HStack {
                            HStack(spacing: 6) {
                                Text(ticker)
                                    .font(.system(size: 12, weight: .semibold))
                                Text(peer?.name ?? "")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            .frame(width: 190, alignment: .leading)
                            .contentShape(Rectangle())
                            .onTapGesture { store.showTicker(ticker) }

                            cell(peer?.lastPrice.map { String(format: "$%.2f", $0) }, width: 80)
                            cell(peer?.changePct1d.map { String(format: "%+.2f%%", $0) }, width: 70,
                                 color: (peer?.changePct1d ?? 0) >= 0 ? .green : .red)
                            cell(peer?.priceToSales.map { String(format: "%.1fx", $0) }, width: 70, bold: true)
                            cell(peer?.revenueGrowth.map { String(format: "%+.0f%%", $0) }, width: 100,
                                 color: (peer?.revenueGrowth ?? 0) >= 0 ? .green : .red)
                            cell(peer?.grossMargin.map { String(format: "%.0f%%", $0) }, width: 110)
                            Spacer()
                            cell(peer?.marketCapUsd.map(money), width: 90, secondary: true)
                            if editingPeers {
                                Button {
                                    removePeer(ticker)
                                } label: {
                                    Image(systemName: "minus.circle").foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                                .frame(width: 28)
                                .disabled(saving || !canEditPeers)
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .help(peer?.source ?? "")
                        Divider()
                    }
                } else if loadFailed && comps == nil {
                    HStack(spacing: 8) {
                        Text("Peers unavailable.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await reload(refresh: false) } }
                            .controlSize(.small)
                    }
                    .padding(10)
                } else {
                    Text(loading ? "Loading peers…" : "No peer data yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(10)
                }
            }
            .appleGlassTile(cornerRadius: 10)

            if let at = comps?.generatedAt {
                Text("Fetched \(MacTimeFormat.relative(at)) · P/S = market cap ÷ latest annual revenue")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
        .task(id: company.id) {
            if comps == nil {
                await reload(refresh: false)
            } else {
                seedPeersFromServer()
            }
        }
    }

    private func reload(refresh: Bool) async {
        loading = true
        await store.loadComps(company.id, refresh: refresh)
        loading = false
        loadFailed = comps == nil
        seedPeersFromServer()
    }

    private func seedPeersFromServer() {
        if let comps { peerTickers = comps.peers.map(\.ticker) }
    }

    private func addPeer() {
        let t = normalized(newPeer)
        guard !t.isEmpty, !saving, canEditPeers, var tickers = peerTickers else { return }
        if !tickers.contains(t) { tickers.append(t) }
        Task { await savePeers(tickers, clearingDraft: true) }
    }

    private func removePeer(_ ticker: String) {
        guard !saving, canEditPeers, let tickers = peerTickers else { return }
        Task { await savePeers(tickers.filter { $0 != ticker }, clearingDraft: false) }
    }

    private func savePeers(_ tickers: [String], clearingDraft: Bool) async {
        var clean: [String] = []
        for t in tickers.map(normalized) where !t.isEmpty && !clean.contains(t) { clean.append(t) }
        clean = Array(clean.prefix(12))
        saving = true
        peerError = nil
        defer { saving = false }
        do {
            try await MacAPIClient.shared.saveCompsPeers(companyId: company.id, tickers: clean)
            peerTickers = clean
            if clearingDraft { newPeer = "" }
            await store.loadComps(company.id, refresh: true)
            seedPeersFromServer()
        } catch {
            peerError = "Couldn't save peers: \(error.localizedDescription)"
        }
    }

    private func normalized(_ raw: String) -> String {
        String(raw.uppercased().unicodeScalars.filter { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || $0 == "." || $0 == "-") })
    }

    private func stat(_ label: String, _ value: String, color: Color = .primary) -> some View {
        MacStatTile(label: label, value: value, tone: color == .primary ? nil : color, compact: true)
    }

    private func cell(_ text: String?, width: CGFloat, bold: Bool = false, color: Color = .primary, secondary: Bool = false) -> some View {
        Text(text ?? "—")
            .font(.system(size: 12, weight: bold ? .semibold : .regular).monospacedDigit())
            .monospacedDigit()
            .foregroundStyle(text == nil ? Color.secondary : (secondary ? Color.secondary : color))
            .frame(width: width, alignment: .trailing)
    }

    private func money(_ usd: Double) -> String {
        if usd >= 1e12 { return String(format: "$%.2fT", usd / 1e12) }
        if usd >= 1e9 { return String(format: "$%.1fB", usd / 1e9) }
        if usd >= 1e6 { return String(format: "$%.1fM", usd / 1e6) }
        return String(format: "$%.0f", usd)
    }
}
