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
                        .font(.ui(.caption))
                        .foregroundStyle(.secondary)
                }
                if !priv.sources.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(priv.sources, id: \.self) { source in
                                Label("\(source.field ?? "fact") · \(source.section ?? "memo")", systemImage: "doc.text")
                                    .font(.ui(.caption2))
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
                        .textFieldStyle(.dsField)
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
                                    .font(.ui(size: 12, weight: .semibold))
                                Text(peer?.name ?? "")
                                    .font(.ui(size: 12))
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
                            .font(.ui(.caption))
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await reload(refresh: false) } }
                            .controlSize(.small)
                    }
                    .padding(10)
                } else {
                    Text(loading ? "Loading peers…" : "No peer data yet.")
                        .font(.ui(.caption))
                        .foregroundStyle(.secondary)
                        .padding(10)
                }
            }
            .appleGlassTile(cornerRadius: 10)

            if let at = comps?.generatedAt {
                Text("Fetched \(MacTimeFormat.relative(at)) · P/S = market cap ÷ latest annual revenue")
                    .font(.ui(.caption2))
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
            .font(.ui(size: 12, weight: bold ? .semibold : .regular).monospacedDigit())
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

// MARK: - Bureau

/// CompsRailCard.vue on the Research Desk: the header with Edit peers and refresh, the
/// private side on stat tiles, the peer table on a tile, and when it was fetched.
extension MacCompsRailView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 14) {
            MacBureauDeskCardHeader(
                icon: "chart-column",
                title: "Comps",
                subtitle: "Peer price-to-sales from live quotes and annual revenue; the private multiple only when the memo states post-money and revenue."
            ) {
                if loading || saving { MacBureauDeskSpinner() }
                Button {
                    editingPeers.toggle()
                } label: {
                    MacBureauDeskButtonLabel(title: editingPeers ? "Done" : "Edit peers", icon: "sliders-horizontal", iconSize: 12, size: .small)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(!canEditPeers)
                .help(peerTickers == nil ? "Peers can be edited once the saved list has loaded" : "Add or remove peer tickers")
                .fixedSize()
                Button {
                    Task { await reload(refresh: true) }
                } label: {
                    MacBureauDeskIcon("rotate-cw", size: 12)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(loading)
                .help("Refresh")
            }

            if let priv = comps?.privateSide {
                MacBureauDeskGrid(columns: 5, spacing: 10) {
                    MacBureauDeskStatTile(label: "Post-money (memo)", value: priv.postMoneyUsd.map(money) ?? "—")
                    MacBureauDeskStatTile(label: "Revenue / ARR (memo)", value: priv.revenueUsd.map(money) ?? "—")
                    MacBureauDeskStatTile(label: "Implied multiple", value: priv.impliedMultiple.map { String(format: "%.1fx", $0) } ?? "—")
                    MacBureauDeskStatTile(label: "Peer median P/S", value: comps?.peerMedianPriceToSales.map { String(format: "%.1fx", $0) } ?? "—")
                    if let diff = priv.vsPeerMedianPct {
                        MacBureauDeskStatTile(label: "vs peers", value: String(format: "%+.0f%%", diff), tone: diff <= 0 ? ink.green : ink.orange)
                    }
                }
                if priv.impliedMultiple == nil {
                    MacBureauWebParagraph(
                        text: priv.postMoneyUsd == nil
                            ? "No post-money on record for \(company.name ?? company.id): the memo doesn't state one yet."
                            : "The memo states a post-money but no revenue figure, so no multiple is implied.",
                        size: 10,
                        lineHeight: 12.5
                    )
                    .foregroundStyle(ink.secondary)
                }
                if !priv.sources.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(priv.sources, id: \.self) { source in
                                HStack(spacing: 4) {
                                    MacBureauDeskIcon("file-text", size: 10)
                                    MacBureauDeskCaption(text: "\(source.field ?? "fact") · \(source.section ?? "memo")", color: ink.secondary)
                                }
                                .foregroundStyle(ink.secondary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .bureauBox(Capsule(), fill: ink.secondary.opacity(0.10))
                                .help(source.excerpt ?? "")
                            }
                        }
                    }
                }
            }

            if editingPeers {
                HStack(spacing: 8) {
                    TextField("", text: $newPeer, prompt: Text("Add ticker").foregroundStyle(ink.tertiary))
                        .textFieldStyle(.plain)
                        .font(BSHType.bureauSans(13))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .frame(width: 120)
                        .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
                        .onSubmit { addPeer() }
                        .disabled(saving || !canEditPeers)
                    Button {
                        addPeer()
                    } label: {
                        MacBureauDeskButtonLabel(title: "Add", size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                    .disabled(normalized(newPeer).isEmpty || saving || !canEditPeers)
                    if let peerError {
                        HStack(spacing: 4) {
                            MacBureauDeskIcon("triangle-alert", size: 12)
                            Text(peerError)
                                .font(BSHType.bureauSans(11))
                                .lineLimit(1)
                                .truncationMode(.tail)
                        }
                        .foregroundStyle(ink.red)
                    }
                    Spacer(minLength: 0)
                }
            }

            bureauTable(ink)

            if let at = comps?.generatedAt {
                MacBureauWebParagraph(
                    text: "Fetched \(MacBureauMemoFormat.relative(at)) · P/S = market cap ÷ latest annual revenue",
                    size: 10,
                    lineHeight: 12.5
                )
                .foregroundStyle(ink.tertiary)
            }
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            if comps == nil {
                // Left to finish when the dossier moves on to another company: a cancelled
                // fetch would surface as an error banner over the desk.
                await Task { await reload(refresh: false) }.value
            } else {
                seedPeersFromServer()
            }
        }
    }

    /// The peer table on a tile: the column heads, a rule, and a ruled row per ticker.
    private func bureauTable(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 0) {
                MacBureauDeskCell(text: "Peer", width: 190, size: 11, weight: .medium, lineHeight: 13.75, trailing: false, color: ink.secondary)
                MacBureauDeskCell(text: "Price", width: 80, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                MacBureauDeskCell(text: "1D", width: 70, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                MacBureauDeskCell(text: "P/S", width: 70, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                MacBureauDeskCell(text: "Revenue growth", width: 100, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                MacBureauDeskCell(text: "Gross margin", width: 110, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                Spacer(minLength: 0)
                MacBureauDeskCell(text: "Market cap", width: 90, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                if editingPeers { Color.clear.frame(width: 28, height: 1) }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            MacBureauGridRule(color: ink.hairline)

            if !listedTickers.isEmpty {
                ForEach(listedTickers, id: \.self) { ticker in
                    bureauRow(ticker, ink: ink)
                    MacBureauGridRule(color: ink.hairline)
                }
            } else if loadFailed && comps == nil {
                HStack(spacing: 8) {
                    MacBureauDeskCaption(text: "Peers unavailable.", color: ink.secondary)
                    Button {
                        Task { await reload(refresh: false) }
                    } label: {
                        MacBureauDeskButtonLabel(title: "Retry", size: .small)
                    }
                    .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                }
                .padding(10)
            } else {
                MacBureauDeskCaption(text: loading ? "Loading peers…" : "No peer data yet.", color: ink.secondary)
                    .padding(10)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    private func bureauRow(_ ticker: String, ink: MacBureauDeskInk) -> some View {
        let peer = fetchedPeer(ticker)
        func value(_ text: String?, _ width: CGFloat, weight: Font.Weight = .regular, tone: Color? = nil) -> some View {
            MacBureauDeskCell(
                text: text ?? "—",
                width: width,
                weight: weight,
                mono: true,
                color: text == nil ? ink.secondary : (tone ?? ink.label)
            )
        }
        let change = peer?.changePct1d
        let growth = peer?.revenueGrowth
        return HStack(spacing: 0) {
            HStack(spacing: 6) {
                MacBureauDeskCaption(text: ticker, size: 12, weight: .semibold, lineHeight: 18, color: ink.label)
                Text(peer?.name ?? "")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(18, 12)
                    .layoutPriority(-1)
            }
            .frame(width: 190, alignment: .leading)
            .contentShape(Rectangle())
            .onTapGesture { store.showTicker(ticker) }
            value(peer?.lastPrice.map { String(format: "$%.2f", $0) }, 80)
            value(change.map { String(format: "%+.2f%%", $0) }, 70, tone: (change ?? 0) >= 0 ? ink.green : ink.red)
            value(peer?.priceToSales.map { String(format: "%.1fx", $0) }, 70, weight: .semibold)
            value(growth.map { String(format: "%+.0f%%", $0) }, 100, tone: (growth ?? 0) >= 0 ? ink.green : ink.red)
            value(peer?.grossMargin.map { String(format: "%.0f%%", $0) }, 110)
            Spacer(minLength: 0)
            value(peer?.marketCapUsd.map(money), 90, tone: ink.secondary)
            if editingPeers {
                Button {
                    removePeer(ticker)
                } label: {
                    MacBureauDeskIcon("circle-minus", size: 14)
                        .foregroundStyle(ink.secondary)
                        .frame(width: 28)
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                .disabled(saving || !canEditPeers)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .help(peer?.source ?? "")
    }
}
