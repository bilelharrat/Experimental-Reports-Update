import SwiftUI

enum PaletteItemKind: Hashable {
    case action(icon: String, title: String, subtitle: String, shortcut: String?, handler: () -> Void)
    case company(MacCompany)
    case report(MacReport)
    case quote(MacQuote)

    static func == (lhs: PaletteItemKind, rhs: PaletteItemKind) -> Bool {
        switch (lhs, rhs) {
        case (.action(_, let t1, _, _, _), .action(_, let t2, _, _, _)):
            return t1 == t2
        case (.company(let c1), .company(let c2)):
            return c1.id == c2.id
        case (.report(let r1), .report(let r2)):
            return r1.id == r2.id
        case (.quote(let q1), .quote(let q2)):
            return q1.ticker == q2.ticker
        default:
            return false
        }
    }

    func hash(into hasher: inout Hasher) {
        switch self {
        case .action(_, let title, _, _, _):
            hasher.combine("action")
            hasher.combine(title)
        case .company(let company):
            hasher.combine("company")
            hasher.combine(company.id)
        case .report(let report):
            hasher.combine("report")
            hasher.combine(report.id)
        case .quote(let quote):
            hasher.combine("quote")
            hasher.combine(quote.ticker)
        }
    }
}

struct MacCommandPalette: View {
    @EnvironmentObject private var store: MacAppStore
    @Binding var isPresented: Bool

    @State private var query: String = ""
    @State private var selectedIndex: Int = 0
    @FocusState private var isFieldFocused: Bool

    private var allItems: [PaletteItemKind] {
        var items: [PaletteItemKind] = []

        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        // 1. Actions
        let actions: [(String, String, String, String?, () -> Void)] = [
            ("plus.rectangle.on.rectangle", "New Investment Memo", "Generate analysis for target company", "⌘N", {
                isPresented = false
                // Handled via root sheet
            }),
            ("globe", "Toggle Embedded Browser", "Side-by-side web research panel", "⌘B", {
                isPresented = false
                store.showBrowserPanel.toggle()
            }),
            ("safari", "Open Portal on Web", "View current company on web portal", "⌘⇧W", {
                isPresented = false
                let url: URL
                if let company = store.selectedCompany {
                    url = MacConfig.webCompanyURL(id: company.id)
                } else {
                    url = MacConfig.baseURL
                }
                store.openInEmbeddedBrowser(url)
            }),
            ("arrow.clockwise", "Refresh All Desks", "Re-query APIs and persist to local cache", "⌘R", {
                isPresented = false
                Task { await store.bootstrap() }
            }),
            ("questionmark.circle", "Keyboard Shortcuts", "View institutional terminal cheat sheet", "?", {
                isPresented = false
                store.showShortcutSheet = true
            }),
            ("house.fill", "Go to Home Desk", "Portfolio overview and activity stream", "⌘1", {
                isPresented = false
                store.selectedTab = .home
            }),
            ("building.columns", "Go to Research Desk", "Company dossiers and memo catalog", "⌘2", {
                isPresented = false
                store.selectedTab = .research
            }),
            ("doc.text.magnifyingglass", "Go to Documents Desk", "Multi-language document viewer", "⌘3", {
                isPresented = false
                store.selectedTab = .documents
            }),
            ("chart.line.uptrend.xyaxis", "Go to Market Radar", "Institutional blotter and charting", "⌘4", {
                isPresented = false
                store.selectedTab = .market
            }),
            ("newspaper", "Go to News Desk", "Market intelligence and AI summaries", "⌘5", {
                isPresented = false
                store.selectedTab = .news
            }),
            ("waveform.path.ecg", "Go to Market Pulse", "Macro regime and ranked signals", "⌘6", {
                isPresented = false
                store.selectedTab = .pulse
            }),
            ("bubble.left.and.bubble.right.fill", "Ask Warren Copilot", "Terminal AI investment copilot", "⌘7", {
                isPresented = false
                store.selectedTab = .copilot
            })
        ]

        for a in actions {
            if q.isEmpty || a.1.lowercased().contains(q) || a.2.lowercased().contains(q) {
                items.append(.action(icon: a.0, title: a.1, subtitle: a.2, shortcut: a.3, handler: a.4))
            }
        }

        // 2. Matching Companies
        for c in store.companies {
            let nameMatch = (c.name ?? "").lowercased().contains(q)
            let idMatch = c.id.lowercased().contains(q)
            let tickerMatch = (c.ticker ?? "").lowercased().contains(q)
            if q.isEmpty || nameMatch || idMatch || tickerMatch {
                items.append(.company(c))
            }
        }

        // 3. Matching Memos
        for r in store.reports.prefix(30) {
            let titleMatch = r.displayTitle.lowercased().contains(q)
            let compMatch = (r.companyName ?? "").lowercased().contains(q)
            if !q.isEmpty && (titleMatch || compMatch) {
                items.append(.report(r))
            }
        }

        // 4. Matching Quotes
        for qItem in store.watchlist {
            let tMatch = qItem.ticker.lowercased().contains(q)
            let nMatch = (qItem.name ?? "").lowercased().contains(q)
            if !q.isEmpty && (tMatch || nMatch) {
                items.append(.quote(qItem))
            }
        }

        return items
    }

    var body: some View {
        ZStack {
            // Dimmed background
            Color.black.opacity(0.4)
                .ignoresSafeArea()
                .onTapGesture {
                    isPresented = false
                }

            // Command Card
            VStack(spacing: 0) {
                // Search Input Header
                HStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(.secondary)

                    TextField("Type a command, company, ticker, or memo…", text: $query)
                        .textFieldStyle(.plain)
                        .font(.system(size: 16))
                        .focused($isFieldFocused)
                        .onSubmit {
                            executeSelected()
                        }

                    if !query.isEmpty {
                        Button {
                            query = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }

                    Text("ESC to close")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)

                Divider()

                // Results list
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 2) {
                            ForEach(Array(allItems.prefix(35).enumerated()), id: \.offset) { index, item in
                                PaletteRow(
                                    item: item,
                                    isSelected: index == selectedIndex
                                )
                                .id(index)
                                .onTapGesture {
                                    selectedIndex = index
                                    executeSelected()
                                }
                            }
                        }
                        .padding(.vertical, 6)
                        .padding(.horizontal, 8)
                    }
                    .frame(maxHeight: 380)
                    .onChange(of: selectedIndex) { newIndex in
                        proxy.scrollTo(newIndex, anchor: .center)
                    }
                }

                Divider()

                // Footer
                HStack {
                    HStack(spacing: 12) {
                        Label("Navigate", systemImage: "arrow.up.arrow.down")
                        Label("Run", systemImage: "return")
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                    Spacer()

                    Text("\(allItems.count) results")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
            }
            .frame(width: 580)
            .appleGlassCard(cornerRadius: 18)
            .shadow(color: .black.opacity(0.35), radius: 32, x: 0, y: 16)
        }
        .onAppear {
            isFieldFocused = true
            selectedIndex = 0
        }
        // Keyboard navigation bindings
        .onKeyPress(.downArrow) {
            if selectedIndex < min(allItems.count - 1, 34) {
                selectedIndex += 1
            }
            return .handled
        }
        .onKeyPress(.upArrow) {
            if selectedIndex > 0 {
                selectedIndex -= 1
            }
            return .handled
        }
        .onKeyPress(.escape) {
            isPresented = false
            return .handled
        }
    }

    private func executeSelected() {
        guard selectedIndex >= 0 && selectedIndex < allItems.count else { return }
        let selected = allItems[selectedIndex]
        switch selected {
        case .action(_, _, _, _, let handler):
            handler()
        case .company(let company):
            store.selectCompany(company)
            store.selectedTab = .research
            store.markCompanyVisited(company.id)
            isPresented = false
        case .report(let report):
            store.openReportInViewer(report)
            isPresented = false
        case .quote(let quote):
            store.selectTicker(quote.ticker)
            store.selectedTab = .market
            isPresented = false
        }
    }
}

private struct PaletteRow: View {
    let item: PaletteItemKind
    let isSelected: Bool

    var body: some View {
        HStack(spacing: 12) {
            switch item {
            case .action(let icon, let title, let subtitle, let shortcut, _):
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundStyle(isSelected ? Color.white : Color.accentColor)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(isSelected ? Color.white : Color.primary)
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
                }

                Spacer()

                if let sc = shortcut {
                    Text(sc)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(isSelected ? Color.white : Color.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(
                            (isSelected ? Color.white.opacity(0.2) : Color.secondary.opacity(0.12)),
                            in: RoundedRectangle(cornerRadius: 3)
                        )
                }

            case .company(let c):
                Image(systemName: "building.2")
                    .font(.system(size: 14))
                    .foregroundStyle(isSelected ? Color.white : Color.blue)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(c.name ?? c.id)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(isSelected ? Color.white : Color.primary)
                        if let ticker = c.ticker, !ticker.isEmpty {
                            Text(ticker)
                                .font(.system(size: 10, design: .monospaced))
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(
                                    (isSelected ? Color.white.opacity(0.2) : Color.secondary.opacity(0.12)),
                                    in: RoundedRectangle(cornerRadius: 3)
                                )
                        }
                    }
                    Text(c.subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
                }

                Spacer()

                Text("Company")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)

            case .report(let r):
                Image(systemName: "doc.text")
                    .font(.system(size: 14))
                    .foregroundStyle(isSelected ? Color.white : Color.orange)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 2) {
                    Text(r.displayTitle)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(isSelected ? Color.white : Color.primary)
                    Text("\(r.companyName ?? "General") · \(r.dateLabel)")
                        .font(.system(size: 11))
                        .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
                }

                Spacer()

                Text("Memo")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)

            case .quote(let q):
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 14))
                    .foregroundStyle(isSelected ? Color.white : Color.green)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(q.ticker)
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundStyle(isSelected ? Color.white : Color.primary)
                        if let name = q.name {
                            Text(name)
                                .font(.system(size: 12))
                                .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
                        }
                    }
                    Text("\(q.priceText) (\(q.pctText))")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(isSelected ? Color.white.opacity(0.9) : (q.isUp ? Color.green : Color.red))
                }

                Spacer()

                Text("Market")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(
            isSelected ? Color.accentColor : Color.clear,
            in: RoundedRectangle(cornerRadius: 8, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(isSelected ? Color.white.opacity(0.35) : Color.clear, lineWidth: 1)
        )
    }
}
