import Charts
import SwiftUI

/// Private holdings: positions, founder-update KPIs, runway/burn alerts, marks, reserves and LP tear sheets.
/// Every number on screen was entered by a person or extracted verbatim from a founder update.
struct MacHoldingsDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var selection: String?
    @State private var showReserves = false
    @State private var showAddCompany = false
    @State private var sortOrder = [KeyPathComparator(\MacHoldingRow.alertRank)]

    struct MacHoldingRow: Identifiable, Hashable {
        let id: String
        let name: String
        let round: String
        let invested: Double
        let ownership: Double
        let arr: Double
        let burn: Double
        let runway: Double
        let mark: Double
        let moic: Double
        let alert: String
        let alertRank: Int
        let lastKpi: String
    }

    private var rows: [MacHoldingRow] {
        (store.portfolioDashboard?.companies ?? []).map { c in
            let top = c.highestAlert
            return MacHoldingRow(
                id: c.companyId,
                name: c.companyName,
                round: c.position.round ?? "",
                invested: c.position.investedUsd ?? 0,
                ownership: c.position.ownershipPct ?? 0,
                arr: c.latestKpi?.arrUsd ?? 0,
                burn: c.latestKpi?.burnUsdMonth ?? 0,
                runway: c.latestKpi?.runwayMonths ?? 0,
                mark: c.latestMark?.valueUsd ?? 0,
                moic: c.moic ?? 0,
                alert: top?.label ?? "",
                alertRank: top.map { $0.severity == "high" ? 0 : ($0.severity == "medium" ? 1 : 2) } ?? 3,
                lastKpi: c.latestKpi.map { MacTimeFormat.relative($0.asOf) } ?? ""
            )
        }.sorted(using: sortOrder)
    }

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                header
                Divider()
                table
                Divider()
                footer
            }
                .frame(minWidth: 620, maxWidth: .infinity, maxHeight: .infinity)
                .layoutPriority(1)

                Divider()

                detail
                    .frame(minWidth: 360, idealWidth: 440, maxWidth: 560, maxHeight: .infinity)
                    .layoutPriority(0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .task {
            if store.portfolioDashboard == nil { await store.loadPortfolioDashboard() }
            if selection == nil { selection = rows.first?.id }
        }
        .onChange(of: selection) { _, id in
            guard let id else { return }
            if let company = store.companies.first(where: { $0.id == id }) { store.selectCompany(company) }
            Task { await store.loadPortfolio(id) }
        }
        .sheet(isPresented: $showReserves) { MacReservesPlannerSheet() }
        .sheet(isPresented: $showAddCompany) {
            MacAddHoldingSheet { id in
                selection = id
            }
        }
    }

    // MARK: - Header / footer

    private var header: some View {
        HStack(spacing: 12) {
            if let t = store.portfolioDashboard?.totals {
                stat("Invested", MacMoney.short(t.investedUsd))
                stat("Marked value", t.markedValueUsd.map(MacMoney.short) ?? "—",
                     hint: t.markedCount == 0 ? "No marks entered yet" : "\(t.markedCount) of \(t.companyCount) positions have a mark")
                stat("MOIC (marked)", t.markedMoic.map { String(format: "%.2fx", $0) } ?? "—")
                stat("Alerts", "\(t.alertCount)", color: t.highAlertCount > 0 ? .red : .primary,
                     hint: "\(t.highAlertCount) high")
            }
            Spacer()
            Button {
                showReserves = true
            } label: {
                Label("Reserves", systemImage: "chart.pie")
            }
            .help("Follow-on reserves planner")
            Button {
                showAddCompany = true
            } label: {
                Label("Add holding", systemImage: "plus")
            }
            .disabled(!store.canWriteDesk)
            Button {
                Task { await store.loadPortfolioDashboard() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(store.portfolioLoading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    private func stat(_ label: String, _ value: String, color: Color = .primary, hint: String = "") -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.dsLabel).foregroundStyle(.secondary)
            Text(value).font(.dsMetricSmall).foregroundStyle(color)
        }
        .help(hint)
    }

    private var footer: some View {
        HStack {
            Text("\(rows.count) holdings · positions from Invest decisions plus anything added here")
                .font(.caption).foregroundStyle(.secondary)
            Spacer()
            if let at = store.portfolioDashboard?.generatedAt {
                Text("Updated \(MacTimeFormat.relative(at))").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Table

    private var table: some View {
        Table(rows, selection: $selection, sortOrder: $sortOrder) {
            TableColumn("Company", value: \.name) { row in
                HStack(spacing: 8) {
                    if let comp = store.companies.first(where: { $0.id == row.id }) {
                        MacMonogram(company: comp, size: 22)
                    } else {
                        MacMonogram(name: row.name, companyId: row.id, size: 22)
                    }
                    Text(row.name).font(.body.weight(.medium))
                }
            }
            .width(min: 160, ideal: 200)
            TableColumn("Round", value: \.round).width(min: 60, ideal: 80)
            TableColumn("Invested", value: \.invested) { row in
                money(row.invested)
            }
            .width(min: 70, ideal: 90)
            TableColumn("Own %", value: \.ownership) { row in
                Text(row.ownership > 0 ? String(format: "%.1f%%", row.ownership) : "—").monospacedDigit()
            }
            .width(min: 55, ideal: 65)
            TableColumn("ARR", value: \.arr) { row in money(row.arr) }.width(min: 70, ideal: 85)
            TableColumn("Burn / mo", value: \.burn) { row in money(row.burn) }.width(min: 70, ideal: 85)
            TableColumn("Runway", value: \.runway) { row in
                Text(row.runway > 0 ? String(format: "%.0f mo", row.runway) : "—")
                    .monospacedDigit()
                    .foregroundStyle(row.runway > 0 && row.runway < 9 ? Color.red : (row.runway > 0 && row.runway < 12 ? Color.orange : Color.primary))
            }
            .width(min: 60, ideal: 70)
            TableColumn("Mark", value: \.mark) { row in money(row.mark) }.width(min: 70, ideal: 85)
            TableColumn("MOIC", value: \.moic) { row in
                Text(row.moic > 0 ? String(format: "%.2fx", row.moic) : "—").monospacedDigit()
            }
            .width(min: 55, ideal: 65)
            TableColumn("Alert", value: \.alertRank) { row in
                if row.alert.isEmpty {
                    Text("—").foregroundStyle(.tertiary)
                } else {
                    Label(row.alert, systemImage: row.alertRank == 0 ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                        .foregroundStyle(row.alertRank == 0 ? Color.red : (row.alertRank == 1 ? Color.orange : Color.secondary))
                        .lineLimit(1)
                        .help(row.lastKpi.isEmpty ? "" : "Latest KPI \(row.lastKpi)")
                }
            }
            .width(min: 140, ideal: 190)
        }
        .tableStyle(.inset(alternatesRowBackgrounds: true))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay {
            if rows.isEmpty {
                ContentUnavailableView(
                    store.portfolioLoading ? "Loading holdings…" : "No holdings yet",
                    systemImage: "briefcase",
                    description: Text("Record an Invest decision (⌘D) or press Add holding.")
                )
            }
        }
    }

    private func money(_ v: Double) -> some View {
        Text(v > 0 ? MacMoney.short(v) : "—").monospacedDigit().foregroundStyle(v > 0 ? Color.primary : Color.secondary)
    }

    // MARK: - Detail

    @ViewBuilder
    private var detail: some View {
        if let id = selection {
            MacHoldingDetailView(companyId: id).id(id)
        } else {
            ContentUnavailableView("Holdings", systemImage: "briefcase", description: Text("Select a holding to see KPI history, founder updates, marks and the tear sheet."))
        }
    }
}

// MARK: - Detail pane

struct MacHoldingDetailView: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore

    @State private var tab = "kpis"
    @State private var updateText = ""
    @State private var updateSubject = ""
    @State private var updateDate = Date()
    @State private var posting = false
    @State private var markValue = ""
    @State private var markBasis = "last_round"
    @State private var markNote = ""
    @State private var savingMark = false
    @State private var editPosition = false
    @State private var kpiDraft: [String: String] = [:]
    @State private var savingKpi = false

    private var markNumber: Double? {
        Double(markValue.replacingOccurrences(of: ",", with: "").replacingOccurrences(of: "$", with: ""))
    }

    private var record: MacPortfolioCompany? { store.portfolioByCompany[companyId] }
    private var summary: MacPortfolioCompany? { store.portfolioDashboard?.companies.first { $0.companyId == companyId } }
    private var name: String { record?.companyName ?? summary?.companyName ?? companyId }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(name).font(.title3.weight(.bold))
                        if let p = record?.position ?? summary?.position {
                            Text([p.round, p.security, p.investedUsd.map { "invested \(MacMoney.short($0))" }, p.ownershipPct.map { String(format: "%.1f%% owned", $0) }]
                                .compactMap { $0 }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Menu {
                        Button("Edit position…") { editPosition = true }.disabled(!store.canWriteDesk)
                        Button("Export LP tear sheet (DOCX)…") { Task { await store.exportTearSheet(companyId, companyName: name) } }
                        Divider()
                        Button("Open dossier") {
                            if let c = store.companies.first(where: { $0.id == companyId }) { store.showCompany(c) }
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .menuStyle(.borderlessButton)
                    .frame(width: 28)
                }

                alertsBlock

                GlassSegmentedPicker("Section", selection: $tab, segments: ["kpis": "KPIs", "updates": "Founder updates", "marks": "Marks"])

                switch tab {
                case "updates": updatesBlock
                case "marks": marksBlock
                default: kpisBlock
                }
            }
            .padding(16)
        }
        .task(id: companyId) { await store.loadPortfolio(companyId) }
        .sheet(isPresented: $editPosition) {
            MacPositionEditorSheet(companyId: companyId, position: record?.position ?? summary?.position ?? .empty)
        }
    }

    private var alertsBlock: some View {
        let alerts = record?.alerts ?? summary?.alerts ?? []
        return Group {
            if !alerts.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(alerts) { alert in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: alert.isHigh ? "exclamationmark.triangle.fill" : "exclamationmark.circle")
                                .foregroundStyle(alert.isHigh ? Color.red : (alert.severity == "medium" ? Color.orange : Color.secondary))
                            VStack(alignment: .leading, spacing: 1) {
                                Text(alert.label).font(.caption.weight(.semibold))
                                if let d = alert.detail { Text(d).font(.caption2).foregroundStyle(.secondary) }
                            }
                        }
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: KPIs

    private var kpisBlock: some View {
        let kpis = record?.kpis ?? []
        return VStack(alignment: .leading, spacing: 12) {
            if kpis.count >= 2 {
                kpiChart(kpis)
            }
            if kpis.isEmpty {
                Text("No KPIs recorded. Paste a founder update or add a row by hand.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("AS OF").frame(width: 80, alignment: .leading)
                        Text("ARR").frame(width: 70, alignment: .trailing)
                        Text("BURN").frame(width: 70, alignment: .trailing)
                        Text("CASH").frame(width: 70, alignment: .trailing)
                        Text("RUNWAY").frame(width: 60, alignment: .trailing)
                        Text("HC").frame(width: 40, alignment: .trailing)
                        Spacer()
                    }
                    .font(.system(size: 10, weight: .bold).monospacedDigit()).foregroundStyle(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(Color.secondary.opacity(0.06))
                    ForEach(kpis.reversed()) { k in
                        HStack {
                            Text(String(k.asOf.prefix(10))).frame(width: 80, alignment: .leading)
                            Text(k.arrUsd.map(MacMoney.short) ?? "—").frame(width: 70, alignment: .trailing)
                            Text(k.burnUsdMonth.map(MacMoney.short) ?? "—").frame(width: 70, alignment: .trailing)
                            Text(k.cashUsd.map(MacMoney.short) ?? "—").frame(width: 70, alignment: .trailing)
                            Text(k.runwayMonths.map { String(format: "%.0f mo", $0) } ?? "—").frame(width: 60, alignment: .trailing)
                            Text(k.headcount.map(String.init) ?? "—").frame(width: 40, alignment: .trailing)
                            Spacer()
                            Image(systemName: k.isFromUpdate ? "envelope" : "pencil")
                                .font(.caption2).foregroundStyle(.secondary)
                                .help(k.isFromUpdate ? "Extracted from a founder update" : "Entered by hand")
                            if store.canWriteDesk {
                                Button { Task { await store.deletePortfolioItem(companyId, kind: "kpis", itemId: k.id) } } label: {
                                    Image(systemName: "minus.circle").foregroundStyle(.secondary)
                                }.buttonStyle(.plain)
                            }
                        }
                        .font(.system(size: 11).monospacedDigit()).monospacedDigit()
                        .padding(.horizontal, 8).padding(.vertical, 5)
                        .help(k.excerpts.values.joined(separator: "\n"))
                        Divider()
                    }
                }
                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
            }

            DisclosureGroup("Add KPI row by hand") {
                VStack(spacing: 6) {
                    HStack {
                        kpiField("As of (YYYY-MM-DD)", "as_of")
                        kpiField("ARR $", "arr_usd")
                        kpiField("Revenue $", "revenue_usd")
                    }
                    HStack {
                        kpiField("Burn $/mo", "burn_usd_month")
                        kpiField("Cash $", "cash_usd")
                        kpiField("Runway mo", "runway_months")
                    }
                    HStack {
                        kpiField("Headcount", "headcount")
                        kpiField("Customers", "customers")
                        Button {
                            guard !savingKpi else { return }
                            var fields: [String: Any?] = [:]
                            for (k, v) in kpiDraft where !v.trimmingCharacters(in: .whitespaces).isEmpty { fields[k] = v }
                            savingKpi = true
                            Task {
                                if await store.addKpi(companyId, fields: fields) { kpiDraft = [:] }
                                savingKpi = false
                            }
                        } label: {
                            if savingKpi { ProgressView().controlSize(.small) } else { Text("Add") }
                        }
                        .disabled(savingKpi || !store.canWriteDesk || kpiDraft.values.allSatisfy { $0.trimmingCharacters(in: .whitespaces).isEmpty })
                    }
                }
                .padding(.top, 6)
            }
            .font(.caption)
        }
    }

    private func kpiField(_ placeholder: String, _ key: String) -> some View {
        TextField(placeholder, text: Binding(get: { kpiDraft[key] ?? "" }, set: { kpiDraft[key] = $0 }))
            .textFieldStyle(.roundedBorder)
            .font(.caption)
    }

    private func kpiChart(_ kpis: [MacKpiRow]) -> some View {
        let points = kpis.compactMap { k -> (Date, Double, String)? in
            guard let d = k.date else { return nil }
            if let arr = k.arrUsd { return (d, arr, "ARR") }
            if let rev = k.revenueUsd { return (d, rev, "Revenue") }
            return nil
        }
        let burn = kpis.compactMap { k -> (Date, Double)? in
            guard let d = k.date, let b = k.burnUsdMonth else { return nil }
            return (d, b)
        }
        return VStack(alignment: .leading, spacing: 4) {
            Text(points.isEmpty ? "Burn per month" : "ARR / revenue vs burn").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            Chart {
                ForEach(Array(points.enumerated()), id: \.offset) { _, p in
                    LineMark(x: .value("Date", p.0), y: .value("USD", p.1), series: .value("Series", p.2))
                        .foregroundStyle(Color.accentColor)
                    PointMark(x: .value("Date", p.0), y: .value("USD", p.1)).foregroundStyle(Color.accentColor)
                }
                ForEach(Array(burn.enumerated()), id: \.offset) { _, p in
                    LineMark(x: .value("Date", p.0), y: .value("USD", p.1), series: .value("Series", "Burn"))
                        .foregroundStyle(Color.red)
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                }
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine()
                    AxisValueLabel { if let v = value.as(Double.self) { Text(MacMoney.short(v)) } }
                }
            }
            .frame(height: 140)
        }
        .padding(10)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: Founder updates

    private var updatesBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Paste a founder update").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                HStack {
                    TextField("Subject", text: $updateSubject).textFieldStyle(.roundedBorder)
                    DatePicker("", selection: $updateDate, displayedComponents: .date).labelsHidden()
                }
                TextEditor(text: $updateText)
                    .font(.system(size: 12))
                    .frame(minHeight: 110)
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.secondary.opacity(0.25)))
                HStack {
                    Text("ARR, revenue, burn, cash, runway, headcount and customers are extracted verbatim with their excerpts and become a KPI row.")
                        .font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        post()
                    } label: {
                        if posting { ProgressView().controlSize(.small) } else { Label("File update", systemImage: "tray.and.arrow.down") }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(posting || updateText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.canWriteDesk)
                }
            }
            .padding(10)
            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))

            ForEach(record?.updates ?? []) { u in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(u.subject?.isEmpty == false ? u.subject! : "Update").font(.caption.weight(.semibold))
                        Text(String(u.asOf.prefix(10))).font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        if store.canWriteDesk {
                            Button { Task { await store.deletePortfolioItem(companyId, kind: "updates", itemId: u.id) } } label: {
                                Image(systemName: "trash").font(.caption2).foregroundStyle(.secondary)
                            }.buttonStyle(.plain)
                        }
                    }
                    if !u.extracted.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(u.extracted) { f in
                                    Text("\(f.label) \(f.display)")
                                        .font(.caption2.monospacedDigit())
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(Color.accentColor.opacity(0.1), in: Capsule())
                                        .help(f.excerpt ?? "")
                                }
                            }
                        }
                    }
                    Text(u.text).font(.caption).foregroundStyle(.secondary).lineLimit(6)
                }
                .padding(10)
                .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func post() {
        posting = true
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
        Task {
            if await store.addFounderUpdate(companyId, text: updateText, asOf: df.string(from: updateDate), subject: updateSubject, source: "paste") != nil {
                updateText = ""; updateSubject = ""
            }
            posting = false
        }
    }

    // MARK: Marks

    private var marksBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                TextField("Holding value $", text: $markValue).textFieldStyle(.roundedBorder).frame(width: 130)
                Picker("Basis", selection: $markBasis) {
                    Text("Last round").tag("last_round")
                    Text("LP report").tag("lp_report")
                    Text("Secondary").tag("secondary")
                    Text("At cost").tag("cost")
                    Text("Manual").tag("manual")
                }.labelsHidden().frame(width: 120)
                TextField("Note", text: $markNote).textFieldStyle(.roundedBorder)
                Button {
                    guard !savingMark, let v = markNumber else { return }
                    savingMark = true
                    Task {
                        if await store.addMark(companyId, valueUsd: v, basis: markBasis, asOf: nil, note: markNote) { markValue = ""; markNote = "" }
                        savingMark = false
                    }
                } label: {
                    if savingMark { ProgressView().controlSize(.small) } else { Text("Mark") }
                }
                .disabled(savingMark || !store.canWriteDesk || markNumber == nil)
            }
            if let marks = record?.marks, !marks.isEmpty {
                ForEach(marks.reversed()) { m in
                    HStack {
                        Text(String(m.asOf.prefix(10))).font(.caption).foregroundStyle(.secondary).frame(width: 80, alignment: .leading)
                        Text(MacMoney.short(m.valueUsd)).font(.caption.weight(.semibold).monospacedDigit())
                        MacStatusPill(text: m.basisLabel, color: .blue)
                        if let n = m.note, !n.isEmpty { Text(n).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
                        Spacer()
                        if store.canWriteDesk {
                            Button { Task { await store.deletePortfolioItem(companyId, kind: "marks", itemId: m.id) } } label: {
                                Image(systemName: "minus.circle").foregroundStyle(.secondary)
                            }.buttonStyle(.plain)
                        }
                    }
                    Divider()
                }
            } else {
                Text("No marks. MOIC shows only once a mark is on record — it is never derived from a round we did not price.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - Position editor

struct MacPositionEditorSheet: View {
    let companyId: String
    @State var position: MacPortfolioPosition
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var round = ""
    @State private var security = ""
    @State private var entryDate = ""
    @State private var invested = ""
    @State private var ownership = ""
    @State private var postMoney = ""
    @State private var followOn = ""
    @State private var boardSeat = false
    @State private var lead = false
    @State private var notes = ""
    @State private var saving = false
    @State private var original: [String: String] = [:]

    private static func exact(_ v: Double) -> String {
        v == v.rounded() && abs(v) < 1e15 ? String(Int64(v)) : String(v)
    }

    private var textFields: [(key: String, value: String)] {
        [
            ("round", round), ("security", security), ("entry_date", entryDate),
            ("invested_usd", invested), ("ownership_pct", ownership), ("entry_post_money_usd", postMoney),
            ("planned_follow_on_usd", followOn), ("notes", notes),
        ]
    }

    private var changedFields: [String: Any?] {
        var fields: [String: Any?] = [:]
        for (key, value) in textFields {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed != (original[key] ?? "") { fields[key] = trimmed }
        }
        if boardSeat != (position.boardSeat ?? false) { fields["board_seat"] = boardSeat }
        if lead != (position.lead ?? false) { fields["lead"] = lead }
        return fields
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Position").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(16)
            Divider()
            Form {
                TextField("Round", text: $round)
                TextField("Security (e.g. Series A preferred, SAFE)", text: $security)
                TextField("Entry date (YYYY-MM-DD)", text: $entryDate)
                TextField("Invested $", text: $invested)
                TextField("Ownership % (fully diluted)", text: $ownership)
                TextField("Entry post-money $", text: $postMoney)
                TextField("Planned follow-on $ (reserves)", text: $followOn)
                Toggle("Board seat", isOn: $boardSeat)
                Toggle("We led", isOn: $lead)
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...4)
            }
            .formStyle(.grouped)
            Divider()
            HStack {
                Spacer()
                Button {
                    save()
                } label: {
                    if saving { ProgressView().controlSize(.small) } else { Text("Save") }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(saving)
            }
            .padding(12)
        }
        .frame(width: 460, height: 520)
        .onAppear {
            round = position.round ?? ""
            security = position.security ?? ""
            entryDate = position.entryDate ?? ""
            invested = position.investedUsd.map(Self.exact) ?? ""
            ownership = position.ownershipPct.map(Self.exact) ?? ""
            postMoney = position.entryPostMoneyUsd.map(Self.exact) ?? ""
            followOn = position.plannedFollowOnUsd.map(Self.exact) ?? ""
            boardSeat = position.boardSeat ?? false
            lead = position.lead ?? false
            notes = position.notes ?? ""
            original = Dictionary(uniqueKeysWithValues: textFields.map { ($0.key, $0.value) })
        }
    }

    private func save() {
        let fields = changedFields
        guard !fields.isEmpty else { dismiss(); return }
        saving = true
        Task {
            if await store.savePosition(companyId, fields: fields) { dismiss() }
            saving = false
        }
    }
}

// MARK: - Add holding

struct MacAddHoldingSheet: View {
    let onAdded: (String) -> Void
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var companyId = ""
    @State private var search = ""

    private var candidates: [MacCompany] {
        let existing = Set(store.portfolioDashboard?.companies.map(\.companyId) ?? [])
        let q = search.lowercased()
        return store.companies.filter { !existing.contains($0.id) && (q.isEmpty || $0.title.lowercased().contains(q)) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Add holding").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(16)
            Divider()
            TextField("Search companies", text: $search).textFieldStyle(.roundedBorder).padding(12)
            List(candidates, selection: $companyId) { c in
                Text(c.title).tag(c.id)
            }
            .frame(minHeight: 240)
            Divider()
            HStack {
                Text("Creates an empty position record; fill it in from the detail pane.").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Add") {
                    let id = companyId
                    Task {
                        if await store.savePosition(id, fields: ["notes": ""]) { onAdded(id); dismiss() }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(companyId.isEmpty)
            }
            .padding(12)
        }
        .frame(width: 420, height: 420)
    }
}

// MARK: - Reserves planner

struct MacReservesPlannerSheet: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @State private var fundSize = ""
    @State private var reservePct = ""
    @State private var notes = ""
    @State private var saving = false
    @State private var saveMessage: String?
    @State private var saveFailed = false

    private var plan: MacReservesPlan? { store.reservesPlan }

    private static func parse(_ raw: String, range: ClosedRange<Double>? = nil, positive: Bool = false) -> (ok: Bool, value: Double?) {
        let cleaned = raw.trimmingCharacters(in: .whitespaces)
            .replacingOccurrences(of: "$", with: "")
            .replacingOccurrences(of: ",", with: "")
            .replacingOccurrences(of: "%", with: "")
        if cleaned.isEmpty { return (true, nil) }
        guard let v = Double(cleaned), v.isFinite, v >= 0 else { return (false, nil) }
        if positive, v <= 0 { return (false, nil) }   // the server rejects a zero fund size with a 400
        if let range, !range.contains(v) { return (false, nil) }
        return (true, v)
    }

    private var fundParsed: (ok: Bool, value: Double?) { Self.parse(fundSize, positive: true) }
    private var pctParsed: (ok: Bool, value: Double?) { Self.parse(reservePct, range: 0...100) }

    private func fill() {
        fundSize = plan?.settings.fundSizeMusd.map { String(format: "%g", $0) } ?? ""
        reservePct = plan?.settings.reservePct.map { String(format: "%g", $0) } ?? ""
        notes = plan?.settings.notes ?? ""
    }

    private func save() {
        guard fundParsed.ok, pctParsed.ok, !saving else { return }
        saving = true
        saveMessage = nil
        saveFailed = false
        let settings = MacReservesSettings(fundSizeMusd: fundParsed.value, reservePct: pctParsed.value, notes: notes)
        Task {
            let ok = await store.saveReserves(settings)
            saving = false
            saveFailed = !ok
            if ok {
                fill()
                saveMessage = "Saved"
            } else {
                saveMessage = store.error ?? "Could not save the reserves settings."
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Reserves & follow-on planner").font(.headline)
                Spacer()
                Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(16)
            Divider()
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        TextField("Fund size ($M)", text: $fundSize).textFieldStyle(.roundedBorder).frame(width: 130)
                        TextField("Reserve %", text: $reservePct).textFieldStyle(.roundedBorder).frame(width: 100)
                        TextField("Notes", text: $notes).textFieldStyle(.roundedBorder)
                        Button {
                            save()
                        } label: {
                            if saving { ProgressView().controlSize(.small) } else { Text("Save") }
                        }
                        .disabled(saving || !store.canWriteDesk || store.reservesPlan == nil || !fundParsed.ok || !pctParsed.ok)
                    }
                    if !fundParsed.ok {
                        Text("Fund size must be a number in $M, e.g. 250").font(.caption).foregroundStyle(.red)
                    } else if !pctParsed.ok {
                        Text("Reserve % must be a number from 0 to 100").font(.caption).foregroundStyle(.red)
                    } else if let saveMessage {
                        Text(saveMessage).font(.caption).foregroundStyle(saveFailed ? Color.red : Color.green)
                    } else {
                        Text("Numbers only, e.g. 250 and 20. Leave a field empty to clear it.").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .onChange(of: fundSize) { _, _ in saveMessage = nil }
                .onChange(of: reservePct) { _, _ in saveMessage = nil }
                .onChange(of: notes) { _, _ in saveMessage = nil }
                if let plan {
                    HStack(spacing: 18) {
                        stat("Reserve pool", plan.reservePoolUsd.map(MacMoney.short) ?? "—")
                        stat("Planned follow-ons", MacMoney.short(plan.plannedFollowOnUsd))
                        stat("Remaining", plan.remainingUsd.map(MacMoney.short) ?? "—",
                             color: (plan.remainingUsd ?? 0) < 0 ? .red : .primary)
                    }
                    if let pool = plan.reservePoolUsd, pool > 0 {
                        ProgressView(value: min(plan.plannedFollowOnUsd / pool, 1.0))
                            .tint(plan.plannedFollowOnUsd > pool ? .red : .accentColor)
                    }
                    VStack(spacing: 0) {
                        HStack {
                            Text("COMPANY").frame(width: 180, alignment: .leading)
                            Text("INVESTED").frame(width: 90, alignment: .trailing)
                            Text("OWN %").frame(width: 60, alignment: .trailing)
                            Text("PLANNED FOLLOW-ON").frame(width: 140, alignment: .trailing)
                            Spacer()
                            Text("RUNWAY").frame(width: 150, alignment: .leading)
                        }
                        .font(.system(size: 10, weight: .bold).monospacedDigit()).foregroundStyle(.secondary)
                        .padding(.horizontal, 8).padding(.vertical, 5)
                        .background(Color.secondary.opacity(0.06))
                        ForEach(plan.companies) { c in
                            HStack {
                                Text(c.companyName).frame(width: 180, alignment: .leading)
                                Text(c.investedUsd.map(MacMoney.short) ?? "—").frame(width: 90, alignment: .trailing)
                                Text(c.ownershipPct.map { String(format: "%.1f", $0) } ?? "—").frame(width: 60, alignment: .trailing)
                                Text(c.plannedFollowOnUsd.map(MacMoney.short) ?? "—").frame(width: 140, alignment: .trailing)
                                Spacer()
                                if let a = c.runwayAlert {
                                    Label(a.label, systemImage: "exclamationmark.triangle.fill")
                                        .foregroundStyle(a.isHigh ? Color.red : Color.orange)
                                        .frame(width: 150, alignment: .leading)
                                } else {
                                    Text("—").foregroundStyle(.tertiary).frame(width: 150, alignment: .leading)
                                }
                            }
                            .font(.system(size: 11).monospacedDigit()).monospacedDigit()
                            .padding(.horizontal, 8).padding(.vertical, 5)
                            Divider()
                        }
                    }
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                    Text("Planned follow-on per company is set in each position record. Runway flags come from the latest KPI row that reports runway, or cash and burn.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            .padding(16)
        }
        .frame(width: 720, height: 520)
        .task {
            if store.reservesPlan == nil { await store.loadPortfolioDashboard() }
            fill()
        }
    }

    private func stat(_ label: String, _ value: String, color: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label.uppercased()).font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 16, weight: .bold).monospacedDigit()).foregroundStyle(color)
        }
    }
}
