import AppKit
import PDFKit
import QuickLookUI
import SwiftUI

struct MacDocumentsDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var searchText = ""
    @State private var selectedCompanyFilter: String = "ALL"
    @State private var selectedStatusFilter: String = "ALL"
    @State private var overlayOpacity: Double = 0.95
    @State private var listWidth: CGFloat = 340

    private var availableCompanies: [MacCompany] {
        store.companies
    }

    private var filteredReports: [MacReport] {
        var list = store.reports

        if selectedCompanyFilter != "ALL" {
            list = list.filter { $0.companyId == selectedCompanyFilter }
        }

        if selectedStatusFilter != "ALL" {
            if selectedStatusFilter == "COMPLETE" {
                list = list.filter { $0.isComplete }
            } else if selectedStatusFilter == "RUNNING" {
                list = list.filter { !$0.isComplete && !$0.isFailed }
            }
        }

        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return list }

        return list.filter {
            ($0.companyName ?? "").localizedCaseInsensitiveContains(q)
                || ($0.companyId ?? "").localizedCaseInsensitiveContains(q)
                || ($0.reportType ?? "").localizedCaseInsensitiveContains(q)
                || ($0.stage ?? "").localizedCaseInsensitiveContains(q)
                || ($0.id).localizedCaseInsensitiveContains(q)
        }
    }

    var body: some View {
        HSplitView {
            // Left Pane: Document Directory & Filter Rail
            VStack(spacing: 0) {
                // Top Search & Filter Bar
                VStack(spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(.secondary)
                        TextField("Filter memos, companies, tickers…", text: $searchText)
                            .textFieldStyle(.plain)
                        if !searchText.isEmpty {
                            Button {
                                searchText = ""
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.secondary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))

                    HStack(spacing: 8) {
                        // Company Picker
                        Picker("Company", selection: $selectedCompanyFilter) {
                            Text("All Companies").tag("ALL")
                            Divider()
                            ForEach(availableCompanies) { co in
                                Text(co.name ?? co.id).tag(co.id)
                            }
                        }
                        .pickerStyle(.menu)
                        .controlSize(.small)

                        // Status Picker
                        Picker("Status", selection: $selectedStatusFilter) {
                            Text("All Status").tag("ALL")
                            Text("Complete").tag("COMPLETE")
                            Text("Running").tag("RUNNING")
                        }
                        .pickerStyle(.menu)
                        .controlSize(.small)
                    }
                }
                .padding(10)

                Divider()

                // Document List
                if filteredReports.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        Image(systemName: "doc.text.magnifyingglass")
                            .font(.system(size: 36))
                            .foregroundStyle(.secondary)
                        Text("No documents found")
                            .font(.headline)
                        Text("Try clearing filters or search terms.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(selection: $store.selectedReport) {
                        ForEach(filteredReports) { report in
                            documentRow(report)
                                .tag(report)
                                .padding(.vertical, 4)
                        }
                    }
                    .listStyle(.inset(alternatesRowBackgrounds: true))
                }

                Divider()

                // Footer Count & Refresh
                HStack {
                    Text("\(filteredReports.count) Documents")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        Task { await store.refreshHome() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.plain)
                    .font(.caption)
                    .help("Refresh documents list")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color(NSColor.windowBackgroundColor))
            }
            .frame(minWidth: 240, idealWidth: 280, maxWidth: 380)
            .layoutPriority(0)

            // Right Pane: Native Document Viewer Canvas
            VStack(spacing: 0) {
                if let report = store.selectedReport {
                    // Document Toolbar Header
                    documentToolbar(report: report)

                    Divider()

                    // Canvas
                    documentCanvas(report: report)
                } else {
                    ContentUnavailableView(
                        "No Document Selected",
                        systemImage: "doc.richtext",
                        description: Text("Select an investment memo from the library to open in the native viewer.")
                    )
                }
            }
            .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
            .layoutPriority(1)
            .background(Color(NSColor.textBackgroundColor))
        }
        .onChange(of: store.selectedReport) { _, newReport in
            if let newReport {
                Task {
                    await store.openMemo(newReport, language: store.readerLanguage)
                }
            }
        }
        .task {
            if store.selectedReport == nil, let first = filteredReports.first {
                store.selectedReport = first
                await store.openMemo(first, language: store.readerLanguage)
            } else if let rep = store.selectedReport, store.openDocumentURL == nil {
                await store.openMemo(rep, language: store.readerLanguage)
            }
        }
    }

    // MARK: - Document List Row

    private func documentRow(_ report: MacReport) -> some View {
        HStack(spacing: 10) {
            // Company Initials Monogram
            Circle()
                .fill(report.isComplete ? Color.accentColor.opacity(0.12) : Color.orange.opacity(0.12))
                .frame(width: 32, height: 32)
                .overlay(
                    Text(monogram(report))
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(report.isComplete ? Color.accentColor : Color.orange)
                )

            VStack(alignment: .leading, spacing: 3) {
                Text(report.companyName ?? report.companyId ?? "Document")
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text(report.reportType ?? "Investment Memo")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)

                    if !report.timeAgo.isEmpty {
                        Text("·")
                            .foregroundStyle(.tertiary)
                        Text(report.timeAgo)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 3) {
                MacStatusPill(
                    text: report.statusLabel,
                    color: report.isComplete ? .green : (report.isFailed ? .red : .orange)
                )

                // iPad ink icon if annotated
                if report.id == store.openReportId && store.openDocumentOverlayData != nil {
                    Image(systemName: "pencil.tip.crop.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(Color.orange)
                        .help("Contains iPad Apple Pencil ink")
                }
            }
        }
    }

    private func monogram(_ report: MacReport) -> String {
        let name = report.companyName ?? report.companyId ?? "BS"
        let parts = name.split(separator: " ").prefix(2)
        return parts.compactMap { $0.first }.map { String($0) }.joined().uppercased()
    }

    // MARK: - Document Toolbar

    private func documentToolbar(report: MacReport) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text(report.companyName ?? report.companyId ?? "Document")
                        .font(.headline)
                        .lineLimit(1)

                    Text(store.openDocumentIsPDF ? "PDF" : "DOCX")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                }

                Text(report.displayTitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            // iPad Ink Overlay Toggle
            if store.openDocumentOverlayData != nil {
                HStack(spacing: 6) {
                    Image(systemName: "pencil.tip.crop.circle.fill")
                        .foregroundStyle(store.showAnnotationOverlay ? Color.orange : Color.secondary)
                    Toggle("iPad Ink", isOn: $store.showAnnotationOverlay)
                        .toggleStyle(.switch)
                        .controlSize(.small)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
                .help("Toggle iPad Apple Pencil ink annotations overlay")
            }

            Divider().frame(height: 18)

            // Language Toggle
            Picker("Language", selection: $store.readerLanguage) {
                Text("English").tag("en")
                Text("中文").tag("zh")
            }
            .pickerStyle(.segmented)
            .controlSize(.small)
            .frame(width: 130)
            .onChange(of: store.readerLanguage) { _, newLang in
                Task {
                    await store.openMemo(report, language: newLang)
                }
            }

            Divider().frame(height: 18)

            // Ask Warren About This Memo
            Button {
                let prompt = "I am reviewing this investment memo (\(report.displayTitle)). What are your primary reflections on the return on invested capital (ROIC), durable competitive advantages, and conservative valuation assumptions?"
                let company = store.companies.first { $0.id == report.companyId }
                store.askWarren(prompt, context: .memo(reportId: report.id, page: nil, selectionText: nil), company: company)
            } label: {
                Label("Ask Warren", systemImage: "sparkles")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Inquire with Warren Copilot about this document")

            // Open in Embedded Browser / Web Portal
            Button {
                let url = MacConfig.webReportURL(id: report.id)
                withAnimation {
                    store.openInEmbeddedBrowser(url)
                }
            } label: {
                Image(systemName: "globe")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Open in Embedded Research Browser (⌘⇧W)")

            // Share / Export File
            if let url = store.openDocumentURL {
                ShareLink(item: url) {
                    Image(systemName: "square.and.arrow.up")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help("Export or share file")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor))
    }

    // MARK: - Document Canvas

    private func documentCanvas(report: MacReport) -> some View {
        ZStack {
            Color(NSColor.windowBackgroundColor)
                .ignoresSafeArea()

            if let url = store.openDocumentURL {
                GeometryReader { geo in
                    ZStack(alignment: .topLeading) {
                        if store.openDocumentIsPDF {
                            MacPDFKitView(
                                url: url,
                                overlayData: store.showAnnotationOverlay ? store.openDocumentOverlayData : nil,
                                overlayOpacity: overlayOpacity
                            )
                        } else {
                            MacQuickLookView(url: url)
                        }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                }
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .shadow(color: .black.opacity(0.12), radius: 8, y: 3)
                .padding(14)
            } else if store.openingMemo {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Loading memo document…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "doc.questionmark")
                        .font(.system(size: 36))
                        .foregroundStyle(.secondary)
                    Text("No document preview available")
                        .font(.headline)
                    Button("Reload Document") {
                        Task { await store.openMemo(report, language: store.readerLanguage) }
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
}
