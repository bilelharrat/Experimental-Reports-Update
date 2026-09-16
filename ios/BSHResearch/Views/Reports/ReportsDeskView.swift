import SwiftUI

enum ReportFilterScope: String, CaseIterable, Identifiable {
    case all, running, completed, failed
    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .all: return "reports.filter_all"
        case .running: return "reports.filter_running"
        case .completed: return "reports.filter_completed"
        case .failed: return "reports.filter_failed"
        }
    }

    var systemImage: String {
        switch self {
        case .all: return "doc.on.doc"
        case .running: return "arrow.triangle.2.circlepath"
        case .completed: return "checkmark.circle"
        case .failed: return "exclamationmark.triangle"
        }
    }
}

enum ReportSortOrder: String, CaseIterable, Identifiable {
    case newest, oldest, company, status
    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .newest: return "reports.sort_newest"
        case .oldest: return "reports.sort_oldest"
        case .company: return "reports.sort_company"
        case .status: return "reports.sort_status"
        }
    }
}

@MainActor
final class ReportsDeskViewModel: ObservableObject {
    @Published var reports: [ReportSummary] = []
    @Published var loading = false
    @Published var error: String?
    @Published var filterScope: ReportFilterScope = .all
    @Published var selectedCompanyId: String? = nil
    @Published var selectedReportType: String? = nil
    @Published var searchText: String = ""
    @Published var sortOrder: ReportSortOrder = .newest

    private var pollTask: Task<Void, Never>?

    init() {
        // Quick bootstrap from disk/in-memory cache
        loadFromCache()
    }

    deinit {
        pollTask?.cancel()
    }

    func loadFromCache() {
        if !AppDataCache.shared.companyReports.isEmpty {
            let cached = AppDataCache.shared.companyReports.values.flatMap { $0 }
            if !cached.isEmpty {
                self.reports = cached
            }
        }
    }

    func start() async {
        await refresh()
        startPollingIfNeeded()
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        if reports.isEmpty { loading = true }
        defer { loading = false }
        do {
            let items: [ReportSummary] = try await APIClient.shared.get("reports")
            self.reports = items
            self.error = nil
            startPollingIfNeeded()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func deleteReport(id: String) async {
        do {
            try await APIClient.shared.delete("reports/\(id)")
            reports.removeAll { $0.id == id }
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func startPollingIfNeeded() {
        pollTask?.cancel()
        let hasActive = reports.contains { $0.isRunning }
        guard hasActive else { return }

        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                guard let self = self, !Task.isCancelled else { break }
                let items: [ReportSummary]? = try? await APIClient.shared.get("reports")
                if let items = items {
                    self.reports = items
                    if !items.contains(where: { $0.isRunning }) {
                        break
                    }
                }
            }
        }
    }

    var counts: (all: Int, running: Int, completed: Int, failed: Int) {
        var r = 0, c = 0, f = 0
        for item in reports {
            if item.isRunning { r += 1 }
            else if item.status?.lowercased().hasPrefix("complete") == true { c += 1 }
            else if item.status?.lowercased().hasPrefix("failed") == true || item.status == "cancelled" { f += 1 }
        }
        return (reports.count, r, c, f)
    }

    var uniqueCompanies: [(id: String, name: String, count: Int)] {
        var dict: [String: (name: String, count: Int)] = [:]
        for r in reports {
            let cid = r.companyId ?? "unknown"
            let cname = r.companyName ?? cid
            if let existing = dict[cid] {
                dict[cid] = (existing.name, existing.count + 1)
            } else {
                dict[cid] = (cname, 1)
            }
        }
        return dict.map { (id: $0.key, name: $0.value.name, count: $0.value.count) }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var uniqueReportTypes: [(type: String, count: Int)] {
        var dict: [String: Int] = [:]
        for r in reports {
            let t = r.reportType ?? "Investment Report"
            dict[t, default: 0] += 1
        }
        return dict.map { (type: $0.key, count: $0.value) }
            .sorted { $0.count > $1.count }
    }

    var filteredReports: [ReportSummary] {
        var list = reports

        // Filter Scope
        switch filterScope {
        case .all:
            break
        case .running:
            list = list.filter { $0.isRunning }
        case .completed:
            list = list.filter { $0.status?.lowercased().hasPrefix("complete") == true }
        case .failed:
            list = list.filter {
                $0.status?.lowercased().hasPrefix("failed") == true || $0.status == "cancelled"
            }
        }

        // Company filter
        if let cid = selectedCompanyId {
            list = list.filter { $0.companyId == cid }
        }

        // Report type filter
        if let type = selectedReportType {
            list = list.filter { ($0.reportType ?? "Investment Report") == type }
        }

        // Search text
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !q.isEmpty {
            list = list.filter { r in
                (r.companyName?.lowercased().contains(q) ?? false) ||
                (r.companyId?.lowercased().contains(q) ?? false) ||
                (r.reportType?.lowercased().contains(q) ?? false) ||
                (r.audience?.lowercased().contains(q) ?? false) ||
                (r.stage?.lowercased().contains(q) ?? false) ||
                (r.status?.lowercased().contains(q) ?? false)
            }
        }

        // Sort order
        switch sortOrder {
        case .newest:
            list.sort { ($0.createdAt ?? "") > ($1.createdAt ?? "") }
        case .oldest:
            list.sort { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
        case .company:
            list.sort { ($0.companyName ?? "").localizedCaseInsensitiveCompare($1.companyName ?? "") == .orderedAscending }
        case .status:
            list.sort {
                if $0.isRunning != $1.isRunning { return $0.isRunning }
                return ($0.status ?? "") < ($1.status ?? "")
            }
        }

        return list
    }
}

struct ReportsDeskView: View {
    @StateObject private var model = ReportsDeskViewModel()
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.embeddedInRootSplit) private var embeddedInRootSplit
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.openWindow) private var openWindow

    @State private var selectedReportId: String?
    @State private var showingCreateSheet = false
    @State private var preselectedCompanyId: String?
    @State private var preselectedCompanyName: String?
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @AppStorage("bsh.reportsListExpanded") private var listExpanded = true

    /// Whether this view is running inside the iPad landscape root rail detail
    private var usesEmbeddedDualPane: Bool {
        embeddedInRootSplit
    }

    /// Whether this view is running in regular width (e.g. standalone window on iPad)
    private var usesSplitView: Bool {
        !embeddedInRootSplit && horizontalSizeClass == .regular
    }

    var body: some View {
        Group {
            if usesEmbeddedDualPane {
                embeddedDualPane
            } else if usesSplitView {
                standaloneSplitView
            } else {
                compactStack
            }
        }
        .task {
            await model.start()
        }
        .onDisappear {
            model.stop()
        }
        .onChange(of: model.filteredReports) { _, reports in
            if selectedReportId == nil, let first = reports.first {
                selectedReportId = first.id
            }
        }
        .onAppear {
            if selectedReportId == nil, let first = model.filteredReports.first {
                selectedReportId = first.id
            }
        }
        .sheet(isPresented: $showingCreateSheet) {
            CreateReportSheet(
                initialCompanyId: preselectedCompanyId,
                initialCompanyName: preselectedCompanyName
            ) { newReport in
                selectedReportId = newReport.id
                Task { await model.refresh() }
            }
        }
    }

    // MARK: - Standalone Split View (Dedicated Window on iPad)

    @ViewBuilder
    private var standaloneSplitView: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarView
        } content: {
            reportListView(isSplit: true)
        } detail: {
            detailPane(selectedId: selectedReportId)
        }
        .navigationSplitViewStyle(.balanced)
    }

    // MARK: - Embedded Dual Pane (Landscape Main Chrome)

    @ViewBuilder
    private var embeddedDualPane: some View {
        HStack(spacing: 0) {
            if listExpanded {
                NavigationStack {
                    reportListView(isSplit: true)
                }
                .frame(
                    minWidth: AdaptiveLayout.embeddedMasterMin,
                    idealWidth: AdaptiveLayout.embeddedMasterIdeal,
                    maxWidth: AdaptiveLayout.embeddedMasterIdeal
                )
                Divider()
            }

            detailPane(selectedId: selectedReportId)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button {
                    withAnimation(.easeInOut(duration: 0.22)) {
                        listExpanded.toggle()
                    }
                } label: {
                    Image(systemName: listExpanded ? "sidebar.left" : "sidebar.leading")
                }
                .help(listExpanded ? "Hide Reports List" : "Show Reports List")
            }
        }
    }

    // MARK: - Compact Stack (iPhone / Portrait iPad)

    @ViewBuilder
    private var compactStack: some View {
        NavigationStack {
            reportListView(isSplit: false)
                .navigationDestination(for: String.self) { reportId in
                    ReportDetailView(reportId: reportId)
                        .id(reportId)
                }
        }
    }

    // MARK: - Sidebar (for iPad Split View)

    @ViewBuilder
    private var sidebarView: some View {
        List {
            Section(header: Text(language.t("reports.library"))) {
                Button {
                    model.filterScope = .all
                    model.selectedCompanyId = nil
                    model.selectedReportType = nil
                } label: {
                    Label {
                        HStack {
                            Text(language.t("reports.filter_all"))
                            Spacer()
                            Text("\(model.counts.all)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "doc.on.doc")
                            .foregroundStyle(.blue)
                    }
                }

                Button {
                    model.filterScope = .running
                    model.selectedCompanyId = nil
                    model.selectedReportType = nil
                } label: {
                    Label {
                        HStack {
                            Text(language.t("reports.filter_running"))
                            Spacer()
                            Text("\(model.counts.running)")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(model.counts.running > 0 ? .orange : .secondary)
                        }
                    } icon: {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .foregroundStyle(.orange)
                    }
                }

                Button {
                    model.filterScope = .completed
                    model.selectedCompanyId = nil
                    model.selectedReportType = nil
                } label: {
                    Label {
                        HStack {
                            Text(language.t("reports.filter_completed"))
                            Spacer()
                            Text("\(model.counts.completed)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "checkmark.circle")
                            .foregroundStyle(.green)
                    }
                }

                Button {
                    model.filterScope = .failed
                    model.selectedCompanyId = nil
                    model.selectedReportType = nil
                } label: {
                    Label {
                        HStack {
                            Text(language.t("reports.filter_failed"))
                            Spacer()
                            Text("\(model.counts.failed)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
            }

            if !model.uniqueCompanies.isEmpty {
                Section(header: Text(language.t("reports.group_by_company"))) {
                    ForEach(model.uniqueCompanies, id: \.id) { comp in
                        Button {
                            model.selectedCompanyId = (model.selectedCompanyId == comp.id) ? nil : comp.id
                        } label: {
                            HStack(spacing: 8) {
                                MonogramAvatar(name: comp.name, companyId: comp.id, size: 24)
                                Text(comp.name)
                                    .lineLimit(1)
                                    .foregroundStyle(model.selectedCompanyId == comp.id ? Color.accentColor : Color.primary)
                                Spacer()
                                Text("\(comp.count)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }

            if !model.uniqueReportTypes.isEmpty {
                Section(header: Text(language.t("reports.group_by_type"))) {
                    ForEach(model.uniqueReportTypes, id: \.type) { item in
                        Button {
                            model.selectedReportType = (model.selectedReportType == item.type) ? nil : item.type
                        } label: {
                            HStack {
                                Text(item.type)
                                    .lineLimit(1)
                                    .foregroundStyle(model.selectedReportType == item.type ? Color.accentColor : Color.primary)
                                Spacer()
                                Text("\(item.count)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle(language.t("tab.reports"))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingCreateSheet = true
                } label: {
                    Image(systemName: "plus")
                }
                .help(language.t("reports.new_report"))
            }
        }
    }

    // MARK: - Report List View

    @ViewBuilder
    private func reportListView(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            // Scope Pills Filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ReportFilterScope.allCases) { scope in
                        let isSelected = model.filterScope == scope
                        Button {
                            withAnimation(.easeInOut(duration: 0.15)) {
                                model.filterScope = scope
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: scope.systemImage)
                                    .font(.caption2)
                                Text(language.t(scope.titleKey))
                                    .font(.subheadline)
                                    .fontWeight(isSelected ? .semibold : .regular)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(isSelected ? Color.accentColor : Color(.secondarySystemFill))
                            .foregroundStyle(isSelected ? Color.white : Color.primary)
                            .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .background(Color(.systemBackground))

            // Active Filters Banner (if company or type is filtered)
            if model.selectedCompanyId != nil || model.selectedReportType != nil {
                HStack(spacing: 8) {
                    if let cid = model.selectedCompanyId,
                       let comp = model.uniqueCompanies.first(where: { $0.id == cid }) {
                        HStack(spacing: 4) {
                            Text(comp.name)
                            Button {
                                model.selectedCompanyId = nil
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                            }
                        }
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.accentColor.opacity(0.15))
                        .clipShape(Capsule())
                    }

                    if let type = model.selectedReportType {
                        HStack(spacing: 4) {
                            Text(type)
                            Button {
                                model.selectedReportType = nil
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                            }
                        }
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.accentColor.opacity(0.15))
                        .clipShape(Capsule())
                    }
                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 6)
            }

            Divider()

            // List of Reports
            if model.loading && model.reports.isEmpty {
                Spacer()
                ProgressView(language.t("common.loading"))
                Spacer()
            } else if model.filteredReports.isEmpty {
                emptyListView
            } else if isSplit {
                List(selection: $selectedReportId) {
                    ForEach(model.filteredReports) { report in
                        ReportCardRow(report: report, isSelected: selectedReportId == report.id)
                            .tag(report.id)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                selectedReportId = report.id
                                if columnVisibility != .detailOnly {
                                    columnVisibility = .all
                                }
                            }
                            .listRowBackground(
                                selectedReportId == report.id
                                    ? Color.accentColor.opacity(0.12)
                                    : Color(.secondarySystemGroupedBackground)
                            )
                            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                Button(role: .destructive) {
                                    Task { await model.deleteReport(id: report.id) }
                                } label: {
                                    Label(language.t("research.delete"), systemImage: "trash")
                                }
                            }
                            .contextMenu {
                                reportContextMenu(report)
                            }
                    }
                }
                .listStyle(.insetGrouped)
            } else {
                List {
                    ForEach(model.filteredReports) { report in
                        NavigationLink(value: report.id) {
                            ReportCardRow(report: report, isSelected: false)
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                Task { await model.deleteReport(id: report.id) }
                            } label: {
                                Label(language.t("research.delete"), systemImage: "trash")
                            }
                        }
                        .contextMenu {
                            reportContextMenu(report)
                        }
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .searchable(text: $model.searchText, prompt: Text(language.t("reports.search_placeholder")))
        .navigationTitle(language.t("reports.title"))
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            await model.refresh()
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button {
                        showingCreateSheet = true
                    } label: {
                        Label(language.t("reports.new_report"), systemImage: "plus")
                    }

                    #if os(iOS)
                    Button {
                        openWindow(id: "reports")
                    } label: {
                        Label(language.t("reports.open_in_new_window"), systemImage: "macwindow.badge.plus")
                    }
                    #endif

                    Menu(language.t("market.stats")) {
                        Picker(selection: $model.sortOrder) {
                            ForEach(ReportSortOrder.allCases) { order in
                                Text(language.t(order.titleKey)).tag(order)
                            }
                        } label: {
                            EmptyView()
                        }
                    }

                    Button {
                        Task { await model.refresh() }
                    } label: {
                        Label(language.t("market.refresh"), systemImage: "arrow.clockwise")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
    }

    // MARK: - Context Menu for Reports

    @ViewBuilder
    private func reportContextMenu(_ report: ReportSummary) -> some View {
        Button {
            selectedReportId = report.id
        } label: {
            Label(language.t("research.report"), systemImage: "doc.text")
        }

        #if os(iOS)
        Button {
            openWindow(id: "report-detail", value: report.id)
        } label: {
            Label(language.t("reports.open_in_new_window"), systemImage: "macwindow.badge.plus")
        }
        #endif

        Button(role: .destructive) {
            Task { await model.deleteReport(id: report.id) }
        } label: {
            Label(language.t("research.delete"), systemImage: "trash")
        }
    }

    // MARK: - Empty List View

    @ViewBuilder
    private var emptyListView: some View {
        ContentUnavailableView {
            Label(language.t("reports.no_selected_title"), systemImage: "doc.text.magnifyingglass")
        } description: {
            Text(language.t("reports.no_selected_subtitle"))
        } actions: {
            Button(language.t("reports.new_report")) {
                showingCreateSheet = true
            }
            .buttonStyle(.borderedProminent)
        }
    }

    // MARK: - Detail Pane

    @ViewBuilder
    private func detailPane(selectedId: String?) -> some View {
        if let id = selectedId {
            Group {
                if usesSplitView {
                    ReportDetailView(reportId: id)
                        .id(id)
                        .toolbar {
                            ToolbarItem(placement: .primaryAction) {
                                #if os(iOS)
                                Button {
                                    openWindow(id: "report-detail", value: id)
                                } label: {
                                    Image(systemName: "macwindow.badge.plus")
                                }
                                .help(language.t("reports.open_in_new_window"))
                                #endif
                            }
                        }
                } else {
                    NavigationStack {
                        ReportDetailView(reportId: id)
                            .id(id)
                            .toolbar {
                                ToolbarItem(placement: .primaryAction) {
                                    #if os(iOS)
                                    Button {
                                        openWindow(id: "report-detail", value: id)
                                    } label: {
                                        Image(systemName: "macwindow.badge.plus")
                                    }
                                    .help(language.t("reports.open_in_new_window"))
                                    #endif
                                }
                            }
                    }
                }
            }
        } else {
            ContentUnavailableView {
                Label(language.t("reports.no_selected_title"), systemImage: "doc.richtext")
            } description: {
                Text(language.t("reports.no_selected_subtitle"))
            } actions: {
                Button(language.t("reports.new_report")) {
                    showingCreateSheet = true
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }
}

// MARK: - Report Card Row

struct ReportCardRow: View {
    let report: ReportSummary
    let isSelected: Bool

    @EnvironmentObject private var language: LanguageStore

    private var companyDisplayName: String {
        report.companyName ?? report.companyId ?? "—"
    }

    private var statusColor: Color {
        let s = (report.status ?? "").lowercased()
        if s.hasPrefix("complete") { return .green }
        if s.hasPrefix("fail") || s == "cancelled" { return .red }
        if report.isRunning { return .orange }
        return .secondary
    }

    private var formattedDate: String {
        guard let dt = report.createdAt ?? report.updatedAt else { return "" }
        if dt.count >= 10 {
            return String(dt.prefix(10))
        }
        return dt
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                MonogramAvatar(
                    name: companyDisplayName,
                    ticker: report.companyId,
                    companyId: report.companyId,
                    logoUrl: report.logoUrl,
                    logoDomain: report.logoDomain,
                    size: 36
                )

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(companyDisplayName)
                            .font(.headline)
                            .foregroundStyle(Color.primary)
                            .lineLimit(1)

                        if let cid = report.companyId, !cid.isEmpty {
                            Text(cid.uppercased())
                                .font(.caption2.monospaced())
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color(.tertiarySystemFill))
                                .clipShape(RoundedRectangle(cornerRadius: 3))
                                .foregroundStyle(.secondary)
                        }
                    }

                    Text(report.reportType ?? language.t("research.report"))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    StatusPill(
                        text: report.statusLabel,
                        color: statusColor
                    )

                    if !formattedDate.isEmpty {
                        Text(formattedDate)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }

            // Running Progress Bar
            if report.isRunning {
                VStack(alignment: .leading, spacing: 3) {
                    ProgressView(value: Double(report.progress ?? 20), total: 100)
                        .tint(.orange)
                    if let stage = report.stage, !stage.isEmpty {
                        Text(stage)
                            .font(.caption2)
                            .foregroundStyle(.orange)
                            .lineLimit(1)
                    }
                }
            }

            // Deliverables badges
            HStack(spacing: 8) {
                if report.downloadUrls != nil || report.previewUrls != nil {
                    HStack(spacing: 3) {
                        Image(systemName: "book.pages.fill")
                        Text("Memo")
                    }
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.green)
                }

                if report.previewUrls != nil {
                    HStack(spacing: 3) {
                        Image(systemName: "doc.text.fill")
                        Text("PDF")
                    }
                    .font(.caption2)
                    .foregroundStyle(.blue)
                }

                if report.downloadUrls != nil {
                    HStack(spacing: 3) {
                        Image(systemName: "doc.fill")
                        Text("DOCX")
                    }
                    .font(.caption2)
                    .foregroundStyle(.indigo)
                }

                if let aud = report.audience, !aud.isEmpty {
                    Text(aud)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(.tertiarySystemFill))
                        .clipShape(Capsule())
                }

                Spacer()
            }
        }
        .padding(.vertical, 4)
    }
}
