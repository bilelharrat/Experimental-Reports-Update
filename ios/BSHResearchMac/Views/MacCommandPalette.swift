import SwiftUI

/// Bloomberg-style function codes: `ANTHROPIC MEMO`, `DBRX GP`, `SNOW N`.
enum MacCommandCode: String, CaseIterable {
    case des = "DES"
    case memo = "MEMO"
    case gp = "GP"
    case q = "Q"
    case n = "N"
    case new = "NEW"
    case ask = "ASK"

    var help: String {
        switch self {
        case .des: return "Dossier"
        case .memo: return "Latest memo"
        case .gp: return "Price chart"
        case .q: return "Quote workspace"
        case .n: return "News"
        case .new: return "New memo run"
        case .ask: return "Ask Warren"
        }
    }
}

struct MacParsedCommand {
    let subject: String
    let code: MacCommandCode?

    static func parse(_ raw: String) -> MacParsedCommand {
        var tokens = raw
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: " ")
            .map(String.init)
        guard let last = tokens.last else { return MacParsedCommand(subject: "", code: nil) }
        let candidate = last.uppercased().trimmingCharacters(in: CharacterSet(charactersIn: "+"))
        if tokens.count > 1, let code = MacCommandCode(rawValue: candidate) {
            tokens.removeLast()
            return MacParsedCommand(subject: tokens.joined(separator: " "), code: code)
        }
        return MacParsedCommand(subject: tokens.joined(separator: " "), code: nil)
    }
}

enum MacCommandResult: Identifiable {
    case company(MacCompany)
    case hit(MacAutocompleteHit)
    case symbol(MacSymbolMatch)
    case match(MacCompanyMatch)
    case deepSearch(String)

    var id: String {
        switch self {
        case .company(let c): return "company|\(c.id)"
        case .hit(let h): return "hit|\(h.id)"
        case .symbol(let s): return "symbol|\(s.symbol)"
        case .match(let m): return "match|\(m.id)"
        case .deepSearch(let q): return "deep|\(q)"
        }
    }
}

struct MacCommandPalette: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var query = ""
    @State private var selection = 0
    @State private var hits: [MacAutocompleteHit] = []
    @State private var symbols: [MacSymbolMatch] = []
    @State private var deepMatches: [MacCompanyMatch] = []
    @State private var searching = false
    @State private var deepStatus: String?
    @State private var searchTask: Task<Void, Never>?
    @State private var deepTask: Task<Void, Never>?
    @State private var busy = false
    @FocusState private var focused: Bool

    private var parsed: MacParsedCommand { MacParsedCommand.parse(query) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "terminal")
                    .font(.title3)
                    .foregroundStyle(Color.accentColor)
                TextField("Company, ticker, or  NAME CODE  —  MEMO · DES · GP · N · NEW · ASK", text: $query)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($focused)
                    .onSubmit { runSelected() }
                    .onKeyPress(.downArrow) {
                        selection = min(selection + 1, max(results.count - 1, 0))
                        return .handled
                    }
                    .onKeyPress(.upArrow) {
                        selection = max(selection - 1, 0)
                        return .handled
                    }
                if searching || busy {
                    ProgressView().controlSize(.small)
                }
                if let code = parsed.code {
                    Text(code.rawValue)
                        .font(.caption.monospaced().weight(.bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15), in: RoundedRectangle(cornerRadius: 4))
                        .help(code.help)
                }
            }
            .padding(14)

            Divider()

            List {
                ForEach(Array(results.enumerated()), id: \.element.id) { index, result in
                    row(result)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            selection = index
                            runSelected()
                        }
                        .listRowBackground(index == selection ? Color.accentColor.opacity(0.16) : Color.clear)
                }
                if results.isEmpty {
                    Text(query.isEmpty ? "Start typing a company or ticker." : "Nothing matches yet.")
                        .foregroundStyle(.secondary)
                }
            }
            .listStyle(.plain)
            .frame(minHeight: 260)

            Divider()

            HStack(spacing: 14) {
                ForEach(MacCommandCode.allCases, id: \.rawValue) { code in
                    HStack(spacing: 3) {
                        Text(code.rawValue).font(.caption2.monospaced().weight(.bold))
                        Text(code.help).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if let deepStatus {
                    Text(deepStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)

            // Esc closes the palette.
            Button("") { dismiss() }
                .keyboardShortcut(.cancelAction)
                .frame(width: 0, height: 0)
                .opacity(0)
        }
        .frame(width: 700, height: 440)
        .onAppear {
            query = store.commandPaletteSeed
            store.commandPaletteSeed = ""
            focused = true
        }
        .onChange(of: query) { _, _ in
            selection = 0
            scheduleSearch()
        }
        .onDisappear {
            searchTask?.cancel()
            deepTask?.cancel()
        }
    }

    // MARK: - Results

    private var results: [MacCommandResult] {
        let subject = parsed.subject.lowercased()
        var out: [MacCommandResult] = []

        var local: [MacCompany]
        if subject.isEmpty {
            local = Array(store.companies.prefix(8))
        } else {
            let prefix = store.companies.filter { company in
                (company.name ?? "").lowercased().hasPrefix(subject)
                    || (company.ticker ?? "").lowercased() == subject
                    || company.id.lowercased().hasPrefix(subject)
            }
            let contains = store.companies.filter { company in
                !prefix.contains(company)
                    && ((company.name ?? "").lowercased().contains(subject)
                        || (company.ticker ?? "").lowercased().contains(subject)
                        || company.id.lowercased().contains(subject))
            }
            local = Array((prefix + contains).prefix(8))
        }
        out.append(contentsOf: local.map { .company($0) })

        let localNames = Set(store.companies.compactMap { $0.name?.lowercased() })
        let localTickers = Set(store.companies.compactMap { $0.ticker?.uppercased() })
        for hit in hits {
            if let name = hit.name, localNames.contains(name.lowercased()) { continue }
            if let t = hit.ticker, localTickers.contains(t.uppercased()) { continue }
            out.append(.hit(hit))
        }
        for symbol in symbols where !localTickers.contains(symbol.symbol) && !hits.contains(where: { $0.ticker?.uppercased() == symbol.symbol }) {
            out.append(.symbol(symbol))
        }
        for match in deepMatches {
            out.append(.match(match))
        }
        if !subject.isEmpty, store.canRunTasks, parsed.code == nil || parsed.code == .des {
            out.append(.deepSearch(parsed.subject))
        }
        return out
    }

    @ViewBuilder
    private func row(_ result: MacCommandResult) -> some View {
        switch result {
        case .company(let company):
            HStack(spacing: 10) {
                MacMonogram(name: company.title, size: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(company.title).font(.body.weight(.medium))
                    Text(company.subtitle.isEmpty ? "In pipeline" : company.subtitle)
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text(actionLabel(for: company))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        case .hit(let hit):
            HStack(spacing: 10) {
                Image(systemName: "plus.circle").foregroundStyle(Color.accentColor).frame(width: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(hit.displayTitle).font(.body.weight(.medium))
                    Text(hit.displaySubtitle).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text(store.canEditSources ? "Add to pipeline" : (hit.ticker != nil ? "Chart" : ""))
                    .font(.caption).foregroundStyle(.secondary)
            }
        case .symbol(let symbol):
            HStack(spacing: 10) {
                Image(systemName: "chart.line.uptrend.xyaxis").foregroundStyle(.secondary).frame(width: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(symbol.symbol).font(.body.monospaced().weight(.semibold))
                    Text([symbol.name, symbol.exchange].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("Quote").font(.caption).foregroundStyle(.secondary)
            }
        case .match(let match):
            HStack(spacing: 10) {
                Image(systemName: "sparkles").foregroundStyle(Color.purple).frame(width: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(match.name).font(.body.weight(.medium))
                    Text([match.ticker, match.sector ?? match.industry, match.description]
                            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Text("Add to pipeline").font(.caption).foregroundStyle(.secondary)
            }
        case .deepSearch(let q):
            HStack(spacing: 10) {
                Image(systemName: "sparkle.magnifyingglass").foregroundStyle(Color.purple).frame(width: 26)
                Text("Deep Search with Claude for “\(q)”").font(.body)
                Spacer()
                Text("↩").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func actionLabel(for company: MacCompany) -> String {
        switch parsed.code {
        case .memo:
            return store.reports(for: company.id).contains(where: \.canOpen) ? "Open latest memo" : "No memo — start one"
        case .gp, .q:
            return company.ticker == nil ? "No ticker" : "Chart"
        case .n: return "News"
        case .new: return "New memo run"
        case .ask: return "Ask Warren"
        case .des, .none: return "Dossier"
        }
    }

    // MARK: - Search

    private func scheduleSearch() {
        searchTask?.cancel()
        deepMatches = []
        deepStatus = nil
        let subject = parsed.subject
        guard !subject.isEmpty else {
            hits = []
            symbols = []
            searching = false
            return
        }
        searching = true
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 180_000_000)
            if Task.isCancelled { return }
            async let a = MacAPIClient.shared.searchAutocomplete(query: subject, limit: 6)
            let looksLikeTicker = subject.count <= 6 && !subject.contains(" ")
            async let s: [MacSymbolMatch] = looksLikeTicker
                ? (try? await MacAPIClient.shared.searchSymbols(query: subject)) ?? []
                : []
            let hitsResult = (try? await a) ?? []
            let symbolsResult = await s
            if Task.isCancelled { return }
            hits = hitsResult
            symbols = Array(symbolsResult.prefix(4))
            searching = false
        }
    }

    private func startDeepSearch(_ q: String) {
        deepTask?.cancel()
        deepStatus = "Asking Claude…"
        busy = true
        deepTask = Task {
            defer { busy = false }
            do {
                let start = try await MacAPIClient.shared.startDeepSearch(query: q)
                if let matches = start.matches, !matches.isEmpty {
                    deepMatches = matches
                    deepStatus = "\(matches.count) match(es) from cache"
                    return
                }
                if let stream = start.streamUrl, !stream.isEmpty {
                    for try await event in MacAPIClient.shared.streamEvents(path: stream) {
                        if Task.isCancelled { return }
                        let obj = event.json
                        let type = (obj?["type"] as? String) ?? event.event ?? ""
                        if let message = obj?["message"] as? String, !message.isEmpty {
                            deepStatus = message
                        }
                        if type == "done" || type == "error" { break }
                    }
                }
                let matches = try await MacAPIClient.shared.fetchDeepSearchResults(query: q)
                deepMatches = matches
                deepStatus = matches.isEmpty ? "Claude found nothing for “\(q)”" : "\(matches.count) match(es)"
            } catch {
                deepStatus = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    // MARK: - Execute

    private func runSelected() {
        let list = results
        guard !list.isEmpty else { return }
        let index = min(max(selection, 0), list.count - 1)
        run(list[index])
    }

    private func run(_ result: MacCommandResult) {
        switch result {
        case .company(let company):
            open(company, code: parsed.code)
            dismiss()
        case .hit(let hit):
            if let existing = store.companies.first(where: {
                ($0.name?.lowercased() == hit.name?.lowercased()) || ($0.ticker != nil && $0.ticker?.uppercased() == hit.ticker?.uppercased())
            }) {
                open(existing, code: parsed.code)
                dismiss()
            } else if store.canEditSources {
                let code = parsed.code
                busy = true
                Task {
                    if let company = await store.addToPipeline(MacCompanyMatch(hit: hit)) {
                        open(company, code: code)
                    }
                    busy = false
                    dismiss()
                }
            } else if let ticker = hit.ticker, !ticker.isEmpty {
                store.showTicker(ticker)
                dismiss()
            }
        case .symbol(let symbol):
            store.showTicker(symbol.symbol)
            dismiss()
        case .match(let match):
            let code = parsed.code
            busy = true
            Task {
                if let company = await store.addToPipeline(match) {
                    open(company, code: code)
                }
                busy = false
                dismiss()
            }
        case .deepSearch(let q):
            startDeepSearch(q)
        }
    }

    private func open(_ company: MacCompany, code: MacCommandCode?) {
        switch code {
        case .memo:
            if let report = store.reports(for: company.id).first(where: \.canOpen) {
                store.selectCompany(company)
                store.openReportWindow(report)
            } else {
                store.showCompany(company)
                store.requestNewReport(for: company)
            }
        case .gp, .q:
            if let ticker = company.ticker, !ticker.isEmpty {
                store.selectCompany(company)
                store.showTicker(ticker)
            } else {
                store.showCompany(company)
            }
        case .n:
            store.selectCompany(company)
            store.selectedTab = .news
        case .new:
            store.showCompany(company)
            store.requestNewReport(for: company)
        case .ask:
            store.selectCompany(company)
            store.selectedTab = .copilot
        case .des, .none:
            store.showCompany(company)
        }
    }
}
