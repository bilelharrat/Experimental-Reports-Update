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
    case firm = "FIRM"
    case hold = "HOLD"
    case tr = "TR"
    case chat = "CHAT"

    var help: String {
        switch self {
        case .des: return "Dossier"
        case .memo: return "Latest memo"
        case .gp: return "Price chart"
        case .q: return "Quote workspace"
        case .n: return "News desk"
        case .new: return "New memo run"
        case .ask: return "Ask Warren"
        case .firm: return "Firm memory search"
        case .hold: return "Holdings"
        case .tr: return "Transcripts"
        case .chat: return "Company chat"
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
    @State private var deepSearchArmed = false
    @State private var pendingSubmit = false
    @State private var deepQuery: String?
    @FocusState private var focused: Bool

    private var parsed: MacParsedCommand { MacParsedCommand.parse(query) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "terminal")
                    .font(.title3)
                    .foregroundStyle(Color.accentColor)
                TextField("Company or ticker — add a code: MEMO · DES · GP · N · NEW · ASK · FIRM · HOLD", text: $query)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($focused)
                    .onSubmit { runSelected() }
                    .onKeyPress(.downArrow) {
                        moveSelection(by: 1)
                        return .handled
                    }
                    .onKeyPress(.upArrow) {
                        moveSelection(by: -1)
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

            ScrollViewReader { proxy in
                List {
                    ForEach(Array(results.enumerated()), id: \.element.id) { index, result in
                        row(result)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                selection = index
                                if case .deepSearch = result { deepSearchArmed = true }
                                runSelected()
                            }
                            .glassListRow(isSelected: index == selection)
                            .id(result.id)
                    }
                    if results.isEmpty {
                        Text(query.isEmpty ? "Start typing a company or ticker." : "Nothing matches yet.")
                            .foregroundStyle(.secondary)
                    }
                }
                .listStyle(.plain)
                .frame(minHeight: 260)
                .onChange(of: selection) { _, newValue in
                    let list = results
                    guard list.indices.contains(newValue) else { return }
                    proxy.scrollTo(list[newValue].id)
                }
                .onChange(of: hits.count) { _, _ in clampSelection() }
                .onChange(of: symbols.count) { _, _ in clampSelection() }
                .onChange(of: deepMatches.count) { _, _ in clampSelection() }
            }

            Divider()

            VStack(alignment: .leading, spacing: 6) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 128), spacing: 10, alignment: .leading)], alignment: .leading, spacing: 4) {
                    ForEach(MacCommandCode.allCases, id: \.rawValue) { code in
                        HStack(spacing: 5) {
                            Text(code.rawValue)
                                .font(.caption2.monospaced().weight(.bold))
                                .foregroundStyle(Color.accentColor)
                            Text(code.help)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
                if let deepStatus {
                    Text(deepStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.bar)

            // Esc closes the palette.
            Button("") { dismiss() }
                .keyboardShortcut(.cancelAction)
                .frame(width: 0, height: 0)
                .opacity(0)

            Button("") {
                let subject = parsed.subject
                if !subject.isEmpty, store.canRunTasks { startDeepSearch(subject) }
            }
            .keyboardShortcut(.return, modifiers: .command)
            .frame(width: 0, height: 0)
            .opacity(0)
        }
        .frame(width: 720, height: 470)
        .onAppear {
            query = store.commandPaletteSeed
            store.commandPaletteSeed = ""
            focused = true
        }
        .onChange(of: query) { _, _ in
            selection = 0
            deepSearchArmed = false
            pendingSubmit = false
            scheduleSearch()
        }
        .onDisappear {
            pendingSubmit = false
            searchTask?.cancel()
            deepTask?.cancel()
        }
    }

    private func moveSelection(by delta: Int) {
        let list = results
        let next = min(max(selection + delta, 0), max(list.count - 1, 0))
        selection = next
        if list.indices.contains(next), case .deepSearch = list[next] {
            deepSearchArmed = true
        }
    }

    private func clampSelection() {
        selection = min(selection, max(results.count - 1, 0))
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
                Text("⌘↩").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func actionLabel(for company: MacCompany) -> String {
        switch parsed.code {
        case .memo:
            if store.reports(for: company.id).contains(where: \.canOpen) { return "Open latest memo" }
            return store.canRunTasks ? "No memo — start one" : "No memo — dossier"
        case .gp, .q:
            return company.ticker == nil ? "No ticker" : "Chart"
        case .n: return "News desk"
        case .new: return store.canRunTasks ? "New memo run" : "Dossier"
        case .ask: return "Ask Warren"
        case .firm: return "Search firm memory"
        case .hold: return "Holdings"
        case .tr: return "Transcripts"
        case .chat: return "Company chat"
        case .des, .none: return "Dossier"
        }
    }

    // MARK: - Search

    private func scheduleSearch() {
        searchTask?.cancel()
        let subject = parsed.subject
        if let dq = deepQuery, dq.caseInsensitiveCompare(subject) != .orderedSame {
            deepTask?.cancel()
            deepTask = nil
            deepQuery = nil
            busy = false
        }
        deepMatches = []
        deepStatus = nil
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
            if Task.isCancelled { return }
            hits = hitsResult
            let symbolsResult = await s
            if Task.isCancelled { return }
            symbols = Array(symbolsResult.prefix(4))
            searching = false
            if pendingSubmit {
                pendingSubmit = false
                runSelected()
            }
        }
    }

    private func startDeepSearch(_ q: String) {
        if busy, deepQuery?.caseInsensitiveCompare(q) == .orderedSame { return }
        deepTask?.cancel()
        deepStatus = "Asking Claude…"
        busy = true
        deepQuery = q
        deepTask = Task {
            @MainActor func isCurrent() -> Bool {
                !Task.isCancelled && parsed.subject.caseInsensitiveCompare(q) == .orderedSame
            }
            // `deepQuery` stays set until a different subject cancels this run, so the
            // defer below can tell "my run ended" from "a newer run took over".
            defer { if deepQuery == q { busy = false } }
            do {
                let start = try await MacAPIClient.shared.startDeepSearch(query: q)
                guard isCurrent() else { return }
                if let matches = start.matches, !matches.isEmpty {
                    deepMatches = matches
                    deepStatus = "\(matches.count) match(es) from cache"
                    return
                }
                guard let stream = start.streamUrl, !stream.isEmpty else {
                    deepMatches = []
                    deepStatus = "Claude found nothing for “\(q)”"
                    return
                }
                var terminal = false
                for try await event in MacAPIClient.shared.streamEvents(path: stream) {
                    guard isCurrent() else { return }
                    let obj = event.json
                    let type = (obj?["type"] as? String) ?? event.event ?? ""
                    if type == "done" {
                        let matches = Self.decodeMatches(obj?["matches"]) ?? []
                        deepMatches = matches
                        if let reason = obj?["reason"] as? String, !reason.isEmpty {
                            deepStatus = reason
                        } else {
                            deepStatus = matches.isEmpty ? "Claude found nothing for “\(q)”" : "\(matches.count) match(es)"
                        }
                        terminal = true
                        break
                    }
                    if type == "error", let matches = Self.decodeMatches(obj?["matches"]) {
                        deepMatches = matches
                        if let reason = obj?["reason"] as? String, !reason.isEmpty {
                            deepStatus = reason
                        } else {
                            deepStatus = (obj?["error"] as? String) ?? "Deep search failed"
                        }
                        terminal = true
                        break
                    }
                    if type == "error" || type == "cancelled" {
                        deepMatches = []
                        deepStatus = (obj?["error"] as? String) ?? (obj?["message"] as? String) ?? "Deep search failed"
                        terminal = true
                        break
                    }
                    if let text = (obj?["error"] as? String) ?? (obj?["message"] as? String), !text.isEmpty {
                        deepStatus = text
                    }
                }
                guard isCurrent() else { return }
                if !terminal {
                    deepMatches = []
                    deepStatus = "Search stream ended unexpectedly"
                }
            } catch {
                if error is CancellationError || !isCurrent() { return }
                deepMatches = []
                deepStatus = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    private static func decodeMatches(_ raw: Any?) -> [MacCompanyMatch]? {
        guard let list = raw as? [Any], JSONSerialization.isValidJSONObject(list),
              let data = try? JSONSerialization.data(withJSONObject: list) else { return nil }
        return (try? JSONDecoder().decode([MacCompanyMatch].self, from: data)) ?? []
    }

    // MARK: - Execute

    private func runSelected() {
        let list = results
        guard !list.isEmpty else { return }
        let index = min(max(selection, 0), list.count - 1)
        if case .deepSearch = list[index], !deepSearchArmed {
            if searching {
                pendingSubmit = true
            } else {
                deepStatus = "No match — ↓ then ↩, or ⌘↩, to Deep Search with Claude"
            }
            return
        }
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
        case .firm:
            store.selectCompany(company)
            store.showFirmSearch = true
        case .hold:
            store.selectCompany(company)
            UserDefaults.standard.set("holdings", forKey: "mac.portfolio.mode")
            store.selectedTab = .portfolio
        case .tr:
            store.selectCompany(company)
            UserDefaults.standard.set("transcripts", forKey: "mac.documents.mode")
            store.selectedTab = .documents
        case .chat:
            store.selectCompany(company)
            store.showBlotter = true
            store.blotterTab = .chat
            Task { await store.openChat(channel: "company:\(company.id)") }
        case .des, .none:
            store.showCompany(company)
        }
    }
}
