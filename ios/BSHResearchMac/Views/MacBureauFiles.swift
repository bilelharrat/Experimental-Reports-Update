//
//  MacBureauFiles.swift
//  BSHResearchMac
//
//  The dossier's Files section under Bureau, as the website draws it: the company's
//  research folder (components/UnifiedDocumentsView.vue — the eyebrow and title, Add file,
//  Add folder and Filter, the filter panel, the documents by group or the empty note) and
//  the fact ledger (components/research/FactLedgerCard.vue). Listing and reading are GETs;
//  uploading, saving and deleting happen only on a click.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Tokens the section needs

extension MacBureauDeskInk {
    /// `--color-surface-muted` for the active desk: a shade under the tray.
    var surfaceMuted: Color {
        let rgb: BSHRGB
        switch (BSHBureauDesk.active, dark) {
        case (.onyx, false): rgb = BSHRGB(226, 224, 218)
        case (.onyx, true): rgb = BSHRGB(11, 11, 11)
        case (.green, true): rgb = BSHRGB(11, 16, 14)
        case (.maroon, true): rgb = BSHRGB(26, 10, 14)
        case (.navy, true): rgb = BSHRGB(10, 14, 22)
        case (.aubergine, true): rgb = BSHRGB(17, 11, 17)
        case (.tobacco, true): rgb = BSHRGB(18, 14, 10)
        case (.graphite, true): rgb = BSHRGB(13, 15, 18)
        case (_, false): rgb = BSHRGB(233, 228, 216)
        }
        return .bshFixed(rgb)
    }
}

extension View {
    /// `bg-surface border border-subtle rounded-card shadow-card`: the tray with its rule,
    /// pressed a shade into the sheet (a faint rim inside the rule and shade along the top).
    func bureauPressedTray(radius: CGFloat, ink: MacBureauDeskInk) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .circular)
        let inner = RoundedRectangle(cornerRadius: max(0, radius - 1), style: .circular)
        return bureauBox(shape, fill: ink.card, stroke: ink.hairline)
            .overlay(
                ZStack {
                    inner.strokeBorder(ink.dark ? Color.white.opacity(0.03) : ink.label(0.035), lineWidth: 1)
                    inner
                        .stroke(ink.dark ? Color.black.opacity(0.35) : ink.shadow(0.04), lineWidth: ink.dark ? 3 : 2)
                        .offset(y: 1)
                        .blur(radius: ink.dark ? 1.5 : 1)
                        .clipShape(inner)
                }
                .padding(1)
                .allowsHitTesting(false)
            )
    }
}

/// The site's `.btn-bordered` (not the desk's `.mac-btn`): 13pt medium on a 20pt line,
/// 14pt either side, 32pt tall, a 16pt glyph 6pt before the words, ruled in ink at 20%.
struct MacBureauSiteButton: View {
    let title: String
    var icon: String? = nil
    var busy = false
    var pressed = false
    let action: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovered = false

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        let live = hovered && isEnabled
        Button(action: action) {
            HStack(spacing: 6) {
                if busy {
                    MacBureauDeskSpinner(size: 16)
                } else if let icon {
                    MacBureauDeskIcon(icon, size: 16)
                }
                Text(title)
                    .font(BSHType.bureauSans(13, weight: .medium))
                    .tracking(-0.078)
                    .lineLimit(1)
                    .fixedSize()
                    .frame(width: MacBureauWebLine.width(title, size: 13, weight: .medium) - 0.078 * CGFloat(title.count), alignment: .leading)
                    .bureauDeskLine(20, 13)
            }
            .foregroundStyle(ink.label)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .bureauBackground {
                Capsule()
                    .fill(live ? ink.label(0.05) : .clear)
                    .overlay(Capsule().strokeBorder(ink.label(live ? 0.36 : 0.2), lineWidth: 1))
            }
            .contentShape(Capsule())
        }
        .buttonStyle(MacBureauSitePressStyle())
        .opacity(isEnabled ? 1 : 0.4)
        .onHover { hovered = $0 }
        .accessibilityAddTraits(pressed ? .isSelected : [])
    }
}

/// Buttons sink half a point while held, as the site's do.
private struct MacBureauSitePressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.offset(y: configuration.isPressed ? 0.5 : 0)
    }
}

// MARK: - The research folder

/// GET /companies/{id}/documents: every file on the company, grouped.
struct MacBureauDocuments: Decodable {
    struct Provenance: Decodable {
        let origin: String?
        let url: String?
    }

    struct Record: Decodable {
        let sizeBytes: Int?
    }

    struct Summary: Decodable {
        struct Exec: Decodable { let en: String? }
        let execSummary: Exec?
    }

    struct QuickSummary: Decodable {
        let summaryEn: String?
        let summary: String?
    }

    struct Row: Decodable, Identifiable {
        let id: String
        let recordId: String?
        let backend: String?
        let title: String?
        let filename: String?
        let kind: String?
        let typeBadge: String?
        let category: String?
        let sourceClass: String?
        let sourceClassLabel: String?
        let status: String?
        let language: String?
        let capturedAt: String?
        let uploadedAt: String?
        let provenance: Provenance?
        let sourceTraceCount: Int?
        let record: Record?
        let summary: Summary?
        let quickSummary: QuickSummary?
        let editableMetadata: Bool?

        var excerpt: String? {
            let text = summary?.execSummary?.en ?? quickSummary?.summaryEn ?? quickSummary?.summary
            return (text?.isEmpty ?? true) ? nil : text
        }
    }

    struct Group: Decodable {
        let id: String?
        let rows: [Row]?
    }

    struct Category: Decodable {
        let id: String
        let label: String?
    }

    struct Filters: Decodable {
        let languages: [String]?
        let statuses: [String]?
    }

    let groups: [Group]?
    let categories: [Category]?
    let sourceClasses: [String]?
    let filters: Filters?
    let unresolvedIntakeCount: Int?

    var rows: [Row] { (groups ?? []).flatMap { $0.rows ?? [] } }
}

/// UnifiedDocumentsView on the desk: the research folder every memo pass reads.
struct MacBureauFilesCard: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var payload: MacBureauDocuments?
    @State private var loading = true
    @State private var loadFailed = false
    @State private var actionFailed = false
    @State private var uploading = false
    @State private var uploadFailed = false
    @State private var filtersOpen = false
    @State private var query = ""
    @State private var category = "all"
    @State private var sourceClass = "all"
    @State private var language = "all"
    @State private var status = "all"

    private var filtersActive: Bool {
        category != "all" || sourceClass != "all" || language != "all" || status != "all"
            || !query.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var visibleRows: [MacBureauDocuments.Row] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return (payload?.rows ?? []).filter { row in
            if category != "all" && row.category != category { return false }
            if sourceClass != "all" && row.sourceClass != sourceClass { return false }
            if language != "all" && (row.language ?? "unknown") != language { return false }
            if status != "all" && (row.status ?? "pending") != status { return false }
            guard !q.isEmpty else { return true }
            return [row.title, row.filename, row.provenance?.origin, row.provenance?.url]
                .compactMap { $0 }
                .joined(separator: " ")
                .lowercased()
                .contains(q)
        }
    }

    /// Generated memos first, then everything uploaded — each group only when it has rows.
    private var groups: [(id: String, label: String, rows: [MacBureauDocuments.Row])] {
        let rows = visibleRows
        return [
            ("generated-memos", "Generated Memos", rows.filter { $0.backend == "generated_report" }),
            ("uploaded-documents", "Uploaded Documents", rows.filter { $0.backend != "generated_report" }),
        ]
        .filter { !$0.2.isEmpty }
        .map { (id: $0.0, label: $0.1, rows: $0.2) }
    }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 0) {
            header(ink)
            if uploadFailed {
                banner("The upload could not be completed. Please try again.", ink: ink)
                    .padding(.top, 12)
            }
            if filtersOpen || filtersActive {
                filterPanel(ink)
                    .padding(.top, 20)
            }
            content(ink)
                .padding(.top, 24)
        }
        .padding(25)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .bureauPressedTray(radius: 14, ink: ink)
        .task(id: company.id) { await load(quiet: false) }
    }

    // MARK: Header

    private func header(_ ink: MacBureauDeskInk) -> some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 0) {
                Text("Files")
                    .font(.custom(BSHType.bureauSerifItalic, size: 15.5))
                    .foregroundStyle(ink.page.secondary)
                    .lineLimit(1)
                    .bureauDeskLine(20, 15.5, serif: true)
                Text("Files")
                    .font(.custom(BSHType.bureauSerif, size: 20))
                    .tracking(-0.2)
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .bureauDeskLine(28, 20, serif: true)
            }
            Spacer(minLength: 0)
            HStack(spacing: 8) {
                MacBureauSiteButton(title: "Add file", icon: "cloud-upload", busy: uploading) { addFiles() }
                    .disabled(uploading || !store.canEditSources)
                MacBureauSiteButton(title: "Add folder", icon: "folder") { addFolder() }
                    .disabled(uploading || !store.canEditSources)
                MacBureauSiteButton(title: "Filter", icon: "funnel", pressed: filtersOpen || filtersActive) {
                    withAnimation(.snappy(duration: 0.2)) { filtersOpen.toggle() }
                }
            }
            .fixedSize()
        }
    }

    // MARK: Filters

    private func filterPanel(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 0) {
                Text("\(visibleRows.count)")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(ink.label)
                Text(" visible")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                if let pending = payload?.unresolvedIntakeCount, pending > 0 {
                    Text(" · ")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.secondary)
                    Text("\(pending)")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(ink.yellow)
                    Text(" awaiting review")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.secondary)
                }
            }
            .lineLimit(1)
            .bureauDeskLine(16, 12)
            MacBureauDeskColumns(weights: [1.4, 1, 1, 1, 1], spacing: 12) {
                searchField(ink)
                select(
                    value: $category,
                    all: "All types",
                    options: (payload?.categories ?? []).map { ($0.id, $0.label ?? $0.id) },
                    ink: ink
                )
                select(value: $sourceClass, all: "All sources", options: (payload?.sourceClasses ?? []).map { ($0, $0) }, ink: ink)
                select(value: $language, all: "All languages", options: (payload?.filters?.languages ?? []).map { ($0, $0.uppercased()) }, ink: ink)
                select(value: $status, all: "All statuses", options: (payload?.filters?.statuses ?? []).map { ($0, Self.humanize($0)) }, ink: ink)
            }
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 9, style: .circular), fill: ink.surfaceMuted.opacity(0.6), stroke: ink.hairline)
    }

    private func searchField(_ ink: MacBureauDeskInk) -> some View {
        HStack(spacing: 8) {
            MacBureauDeskIcon("search", size: 16)
                .foregroundStyle(ink.secondary)
            // `.field`: 14pt with the site's −0.006em.
            TextField("", text: $query, prompt: Text("Filter").tracking(-0.084).foregroundStyle(ink.tertiary))
                .textFieldStyle(.plain)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.label)
                .offset(y: 0.5)
        }
        .padding(.leading, 12)
        .padding(.trailing, 12)
        .frame(height: 34)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.raised, stroke: ink.label(0.14))
    }

    private func select(value: Binding<String>, all: String, options: [(String, String)], ink: MacBureauDeskInk) -> some View {
        let label = options.first(where: { $0.0 == value.wrappedValue })?.1 ?? all
        return Menu {
            Button(all) { value.wrappedValue = "all" }
            ForEach(options, id: \.0) { option in
                Button(option.1) { value.wrappedValue = option.0 }
            }
        } label: {
            HStack(spacing: 0) {
                Text(label)
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.label)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(20, 14)
                Spacer(minLength: 0)
                MacBureauSelectChevrons()
                    .frame(width: 9, height: 13)
            }
            .padding(.leading, 12)
            .padding(.trailing, 10.4)
            .frame(height: 34)
            .frame(maxWidth: .infinity)
            .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.raised, stroke: ink.label(0.14))
            .contentShape(Rectangle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
    }

    // MARK: Documents

    @ViewBuilder
    private func content(_ ink: MacBureauDeskInk) -> some View {
        if loading {
            HStack(spacing: 8) {
                MacBureauDeskSpinner(size: 16)
                Text("Loading documents…")
                    .font(BSHType.bureauSans(14))
                    .foregroundStyle(ink.secondary)
                    .bureauDeskLine(20, 14)
            }
        } else if loadFailed || actionFailed {
            banner(
                loadFailed ? "Documents could not be loaded. Please try again." : "That document action could not be completed. Please try again.",
                ink: ink
            )
        } else if groups.isEmpty {
            MacBureauWebParagraph(text: "No documents match the current filters.", size: 14, lineHeight: 20)
                .foregroundStyle(ink.secondary)
                .padding(25)
                .frame(maxWidth: .infinity, alignment: .leading)
                .bureauBox(RoundedRectangle(cornerRadius: 9, style: .circular), fill: ink.surfaceMuted)
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .circular)
                        .strokeBorder(ink.hairline, style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                )
        } else {
            VStack(alignment: .leading, spacing: 20) {
                ForEach(groups, id: \.id) { group in
                    groupSection(group.label, rows: group.rows, ink: ink)
                }
            }
        }
    }

    private func banner(_ text: String, ink: MacBureauDeskInk) -> some View {
        HStack(alignment: .top, spacing: 8) {
            MacBureauDeskIcon("circle-alert", size: 16)
                .padding(.top, 2)
            MacBureauWebParagraph(text: text, size: 14, lineHeight: 20)
        }
        .foregroundStyle(ink.red)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 9, style: .circular), fill: ink.red.opacity(0.08), stroke: ink.red.opacity(0.25))
    }

    private func groupSection(_ label: String, rows: [MacBureauDocuments.Row], ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("chevron-down", size: 16)
                    .foregroundStyle(ink.secondary)
                Text(label)
                    .font(.custom(BSHType.bureauSerif, size: 16))
                    .foregroundStyle(ink.label)
                    .bureauDeskLine(24, 16, serif: true)
                Spacer(minLength: 0)
                Text("\(rows.count)")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(ink.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            ForEach(rows) { row in
                MacBureauGridRule(color: ink.hairline)
                documentRow(row, ink: ink)
            }
        }
        .bureauBox(RoundedRectangle(cornerRadius: 9, style: .circular), fill: ink.card, stroke: ink.hairline)
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .circular))
    }

    private func documentRow(_ row: MacBureauDocuments.Row, ink: MacBureauDeskInk) -> some View {
        let type = Self.fileType(row)
        let tint = Self.typeTint(type, ink: ink)
        return HStack(alignment: .top, spacing: 12) {
            Text(type)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(tint ?? ink.page.secondary)
                .frame(width: 44, height: 44)
                .background((tint ?? ink.surfaceMuted).opacity(tint == nil ? 1 : 0.14), in: RoundedRectangle(cornerRadius: 8, style: .circular))
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(row.title ?? row.filename ?? "Untitled")
                        .font(BSHType.bureauSans(14, weight: .semibold))
                        .foregroundStyle(ink.label)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    badge(Self.sourceLabel(row), ink: ink)
                    badge(Self.humanize(row.status ?? "pending"), ink: ink)
                }
                Text(Self.meta(row))
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                if let excerpt = row.excerpt {
                    MacBureauWebParagraph(text: excerpt, size: 12, lineHeight: 19.5, maxLines: 2)
                        .foregroundStyle(ink.page.secondary)
                        .padding(.top, 4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 6) {
                rowButton(row.backend == "generated_report" ? "Open" : "View", icon: "eye") { open(row) }
                if row.editableMetadata == true, row.backend != "generated_report" {
                    rowButton("Delete", icon: "trash-2") { delete(row) }
                        .disabled(!store.canEditSources)
                }
            }
            .fixedSize()
        }
        .padding(16)
    }

    private func badge(_ text: String, ink: MacBureauDeskInk) -> some View {
        Text(text)
            .font(BSHType.bureauSans(11))
            .foregroundStyle(ink.page.secondary)
            .lineLimit(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(ink.card, in: Capsule())
            .overlay(Capsule().strokeBorder(ink.hairline, lineWidth: 1))
            .fixedSize()
    }

    private func rowButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        let ink = MacBureauDeskInk(colorScheme)
        return Button(action: action) {
            HStack(spacing: 4) {
                MacBureauDeskIcon(icon, size: 14)
                Text(title).font(BSHType.bureauSans(12))
            }
            .foregroundStyle(ink.page.secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(ink.card, in: Capsule())
            .overlay(Capsule().strokeBorder(ink.hairline, lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(MacBureauSitePressStyle())
    }

    // MARK: Row text

    static func fileType(_ row: MacBureauDocuments.Row) -> String {
        let source = (row.filename ?? row.title ?? row.kind ?? "").lowercased()
        let kind = (row.kind ?? "").lowercased()
        if row.provenance?.url != nil || kind == "url" { return "URL" }
        if source.hasSuffix(".pdf") || kind == "pdf" { return "PDF" }
        if source.hasSuffix(".xls") || source.hasSuffix(".xlsx") || ["xls", "xlsx"].contains(kind) { return "XLSX" }
        if source.hasSuffix(".md") || kind == "md" { return "MD" }
        if source.hasSuffix(".doc") || source.hasSuffix(".docx") || ["doc", "docx"].contains(kind) { return "DOCX" }
        if source.hasSuffix(".ppt") || source.hasSuffix(".pptx") || ["ppt", "pptx"].contains(kind) { return "PPTX" }
        return (row.typeBadge ?? row.kind ?? "file").uppercased()
    }

    private static func typeTint(_ type: String, ink: MacBureauDeskInk) -> Color? {
        switch type {
        case "PDF": return ink.red
        case "XLSX": return ink.green
        case "URL": return ink.blue
        case "DOCX", "DOC": return ink.indigo
        case "PPTX", "PPT": return ink.purple
        case "MD": return ink.green
        default: return nil
        }
    }

    private static func sourceLabel(_ row: MacBureauDocuments.Row) -> String {
        let value = (row.sourceClass ?? "").lowercased()
        if value == "generated memo" { return "Generated memo" }
        if value == "internal note" { return "Internal note" }
        if value.isEmpty || value == "unknown/pending" { return "Pending" }
        return row.sourceClassLabel ?? row.sourceClass ?? ""
    }

    static func humanize(_ status: String) -> String {
        let text = status.replacingOccurrences(of: "_", with: " ")
        return text.prefix(1).uppercased() + text.dropFirst()
    }

    private static func meta(_ row: MacBureauDocuments.Row) -> String {
        var parts = [row.filename ?? "No file attached"]
        if let bytes = row.record?.sizeBytes, bytes > 0 {
            if bytes < 1024 { parts.append("\(bytes) B") }
            else if bytes < 1024 * 1024 { parts.append("\(Int((Double(bytes) / 1024).rounded())) KB") }
            else { parts.append(String(format: "%.1f MB", Double(bytes) / 1024 / 1024)) }
        }
        parts.append(String((row.capturedAt ?? row.uploadedAt ?? "Date pending").prefix(10)))
        parts.append((row.language ?? "unknown").uppercased())
        if let origin = row.provenance?.origin, !origin.isEmpty { parts.append("Source: \(origin)") }
        if let traces = row.sourceTraceCount, traces > 0 { parts.append("\(traces) traces") }
        return parts.joined(separator: "   ")
    }

    // MARK: Loading and actions

    private func load(quiet: Bool) async {
        let id = company.id
        if !quiet { loading = true }
        loadFailed = false
        do {
            let result = try await MacBureauMemoRequests.get("companies/\(id)/documents", as: MacBureauDocuments.self)
            guard id == company.id else { return }
            payload = result
        } catch {
            guard id == company.id else { return }
            loadFailed = true
        }
        loading = false
    }

    /// Add file: one or more files into the research folder the memo passes read.
    private func addFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [
            .pdf, .plainText, .image, .png, .jpeg, .gif, .webP,
            UTType("org.openxmlformats.presentationml.presentation"),
            UTType("org.openxmlformats.wordprocessingml.document"),
            UTType("com.microsoft.word.doc"),
            UTType("net.daringfireball.markdown"),
        ].compactMap { $0 }
        panel.prompt = "Add"
        guard panel.runModal() == .OK, !panel.urls.isEmpty else { return }
        upload(panel.urls, folder: nil)
    }

    /// Add folder: every file in it, filed together under the folder's name.
    private func addFolder() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Add Folder"
        guard panel.runModal() == .OK, let folder = panel.url else { return }
        let junk: Set<String> = [".ds_store", "thumbs.db", "desktop.ini"]
        let files = (FileManager.default.enumerator(at: folder, includingPropertiesForKeys: [.isRegularFileKey], options: [.skipsHiddenFiles])?
            .compactMap { $0 as? URL } ?? [])
            .filter { (try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true }
            .filter { !junk.contains($0.lastPathComponent.lowercased()) }
            .sorted { $0.path < $1.path }
        guard !files.isEmpty else { return }
        upload(files, folder: folder.lastPathComponent)
    }

    private func upload(_ files: [URL], folder: String?) {
        let id = company.id
        uploading = true
        uploadFailed = false
        Task {
            var folderId: String?
            var failed = false
            for file in files {
                do {
                    var fields: [String: String] = [:]
                    if let folder { fields["folder_name"] = folder }
                    if let folderId { fields["folder_id"] = folderId }
                    let minted = try await MacBureauResearchUpload.send(companyId: id, file: file, fields: fields)
                    if folderId == nil { folderId = minted }
                } catch {
                    failed = true
                    if folder == nil { break }
                }
            }
            if id == company.id {
                uploadFailed = failed
                await load(quiet: true)
            }
            uploading = false
        }
    }

    /// View: fetch the file as this Mac is signed in and hand it to the app that opens it.
    private func open(_ row: MacBureauDocuments.Row) {
        let record = row.recordId ?? row.id
        let path: String
        switch row.backend {
        case "document_library": path = "companies/\(company.id)/files/\(record)"
        case "generated_report":
            // A generated memo opens in the memo window, as Open does on the website.
            if let report = store.reports.first(where: { $0.id == record }) { store.openReportWindow(report) }
            return
        default: path = "companies/\(company.id)/research-files/\(record)"
        }
        let name = row.filename ?? row.title ?? record
        Task {
            if let url = try? await MacBureauResearchUpload.download(path, named: name) {
                NSWorkspace.shared.open(url)
            } else {
                actionFailed = true
            }
        }
    }

    private func delete(_ row: MacBureauDocuments.Row) {
        let alert = NSAlert()
        alert.messageText = "Delete \(row.title ?? row.filename ?? "this file")?"
        alert.addButton(withTitle: "Delete")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn, let record = row.recordId else { return }
        let path = row.backend == "document_library"
            ? "companies/\(company.id)/files/\(record)"
            : "companies/\(company.id)/research-files/\(record)"
        Task {
            do {
                try await MacBureauMemoRequests.send(path, method: "DELETE")
                await load(quiet: true)
            } catch {
                actionFailed = true
            }
        }
    }
}

/// The select's up-and-down chevrons (the website draws them as a background image).
private struct MacBureauSelectChevrons: View {
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let sx = size.width / 10, sy = size.height / 14
            var path = Path()
            path.move(to: CGPoint(x: 2 * sx, y: 5 * sy))
            path.addLine(to: CGPoint(x: 5 * sx, y: 2 * sy))
            path.addLine(to: CGPoint(x: 8 * sx, y: 5 * sy))
            path.move(to: CGPoint(x: 2 * sx, y: 9 * sy))
            path.addLine(to: CGPoint(x: 5 * sx, y: 12 * sy))
            path.addLine(to: CGPoint(x: 8 * sx, y: 9 * sy))
            let tint = colorScheme == .dark ? BSHRGB(154, 154, 162) : BSHRGB(128, 128, 134)
            context.stroke(path, with: .color(.bshFixed(tint)), style: StrokeStyle(lineWidth: 1.6 * sx, lineCap: .round, lineJoin: .round))
        }
    }
}

/// Uploads into, and downloads from, the company's research folder — the website's
/// `uploadResearchFile` and file links, which the Mac client doesn't carry yet.
enum MacBureauResearchUpload {
    private struct Filed: Decodable {
        let folderId: String?
        enum CodingKeys: String, CodingKey { case folderId = "folder_id" }
    }

    /// Files one document; returns the folder id the server minted, when it filed a folder.
    static func send(companyId: String, file: URL, fields: [String: String]) async throws -> String? {
        guard let url = MacConfig.serverURL("companies/\(companyId)/research-files") else { throw URLError(.badURL) }
        let data = try Data(contentsOf: file)
        let boundary = "bsh-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        for (name, value) in fields.sorted(by: { $0.key < $1.key }) { field(name, value) }
        let type = UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(file.lastPathComponent)\"\r\nContent-Type: \(type)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 180
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        req.httpBody = body
        let (reply, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONDecoder().decode(Filed.self, from: reply))?.folderId
    }

    /// Fetches a file into the temporary folder and returns where it landed.
    static func download(_ path: String, named name: String) async throws -> URL {
        guard let url = MacConfig.serverURL(path) else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.timeoutInterval = 120
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("bsh-files", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let safe = name.replacingOccurrences(of: "/", with: "-")
        let target = dir.appendingPathComponent(safe.isEmpty ? "file" : safe)
        try data.write(to: target, options: .atomic)
        return target
    }
}

// MARK: - Fact ledger

/// FactLedgerCard: dated headline facts every memo run reads first, edited in place and
/// saved on a click.
struct MacBureauFactLedgerCard: View {
    let companyId: String
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var ledger: Ledger?
    @State private var draft = ""
    @State private var loading = false
    @State private var saving = false
    @State private var saved = false
    @State private var errorText = ""

    struct Ledger: Decodable {
        let exists: Bool?
        let text: String?
        let updatedAt: String?
        let maxChars: Int?
    }

    private var maxChars: Int { ledger?.maxChars ?? 6000 }
    private var dirty: Bool { ledger != nil && draft != (ledger?.text ?? "") }
    private var overLimit: Bool { draft.count > maxChars }

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                MacBureauDeskIcon("book-open", size: 14)
                    .foregroundStyle(ink.accent)
                MacBureauDeskCaption(text: "Fact ledger", size: 11, weight: .semibold, lineHeight: 14.3, color: ink.label)
                Spacer(minLength: 0)
                if let ledger, ledger.exists != true, !dirty {
                    Text("No ledger yet — headline facts depend on what each memo run happens to retrieve")
                        .font(BSHType.bureauSans(10))
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .bureauExactWidth("No ledger yet — headline facts depend on what each memo run happens to retrieve", size: 10)
                        .bureauDeskLine(12.5, 10)
                        .layoutPriority(-1)
                } else if let updated = ledger?.updatedAt, !updated.isEmpty, !dirty {
                    MacBureauDeskCaption(text: "Updated \(updated.prefix(10))", color: ink.secondary)
                }
                if saved && !dirty {
                    MacBureauDeskCaption(text: "Saved", color: ink.green)
                }
                Button {
                    save()
                } label: {
                    MacBureauDeskButtonLabel(title: "Save", size: .mini)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .mini))
                .disabled(!dirty || saving || overLimit || !store.canEditSources)
                MacBureauDeskRefreshButton(busy: loading) {
                    Task { await load() }
                }
            }
            .frame(minHeight: 15)

            MacBureauWebParagraph(
                text: "Dated headline facts every memo run reads first. One line per fact: date, the fact, where it came from.",
                size: 10,
                lineHeight: 12.5
            )
            .foregroundStyle(ink.tertiary)

            MacBureauDeskLedgerField(
                text: $draft,
                placeholder: "- 2026-06-13: Contracted book revised to $500M+; 95+ patents (company announcement)"
            )

            HStack(spacing: 8) {
                MacBureauDeskCaption(text: "\(draft.count) / \(maxChars)", mono: true, color: overLimit ? ink.red : ink.secondary)
                Spacer(minLength: 0)
                if !errorText.isEmpty {
                    MacBureauDeskCaption(text: errorText, color: ink.red)
                }
            }
        }
        .bureauDeskCard(padding: 10)
        .task(id: companyId) { await load() }
    }

    private func load() async {
        let id = companyId
        loading = true
        errorText = ""
        do {
            let result = try await MacBureauMemoRequests.get("companies/\(id)/fact-ledger", as: Ledger.self)
            guard id == companyId else { return }
            ledger = result
            draft = result.text ?? ""
        } catch {
            guard id == companyId else { return }
            ledger = nil
        }
        loading = false
    }

    private func save() {
        guard !saving, !overLimit, dirty else { return }
        let id = companyId
        let text = draft
        saving = true
        errorText = ""
        Task {
            do {
                let data = try await MacBureauMemoRequests.send("companies/\(id)/fact-ledger", method: "PUT", body: ["text": text])
                if id == companyId, let result = MacBureauMemoRequests.decode(Ledger.self, from: data) {
                    ledger = result
                    draft = result.text ?? ""
                    saved = true
                }
            } catch {
                if id == companyId { errorText = "Could not save the ledger" }
            }
            saving = false
        }
    }
}

/// The ledger's `textarea.mac-field.mac-mono`, seven rows of 13pt on 21.125pt lines, with
/// the grip that drags it taller.
struct MacBureauDeskLedgerField: View {
    @Binding var text: String
    let placeholder: String
    var rows = 7
    @Environment(\.colorScheme) private var colorScheme
    @State private var extra: CGFloat = 0
    @State private var dragBase: CGFloat?

    private static let lineHeight: CGFloat = 21.125

    var body: some View {
        let ink = MacBureauDeskInk(colorScheme)
        ZStack(alignment: .topLeading) {
            if text.isEmpty {
                Text(placeholder)
                    .font(BSHType.bureauSans(13).monospacedDigit())
                    .foregroundStyle(ink.tertiary)
                    .lineLimit(1)
                    .bureauDeskLine(Self.lineHeight, 13)
                    .allowsHitTesting(false)
            }
            TextEditor(text: $text)
                .font(BSHType.bureauSans(13).monospacedDigit())
                .foregroundStyle(ink.label)
                .scrollContentBackground(.hidden)
                .lineSpacing(Self.lineHeight - 16)
                .padding(.leading, -5)
                .padding(.top, 2)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .frame(height: Self.lineHeight * CGFloat(rows) + 8 + extra)
        .bureauBox(RoundedRectangle(cornerRadius: 7, style: .circular), fill: ink.raised)
        .overlay(alignment: .bottomTrailing) {
            MacBureauDeskResizeGrip(extra: $extra, dragBase: $dragBase)
        }
    }
}

/// The corner grip of a resizable field: two strokes with a lighter edge beside each.
struct MacBureauDeskResizeGrip: View {
    @Binding var extra: CGFloat
    @Binding var dragBase: CGFloat?
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let dark = colorScheme == .dark
        Canvas { context, size in
            let w = size.width, h = size.height
            var strokes = Path()
            strokes.move(to: CGPoint(x: w - 8, y: h - 1.5))
            strokes.addLine(to: CGPoint(x: w - 1.5, y: h - 8))
            strokes.move(to: CGPoint(x: w - 4, y: h - 1.5))
            strokes.addLine(to: CGPoint(x: w - 1.5, y: h - 4))
            let edge = strokes.offsetBy(dx: 0.9, dy: 0.4)
            context.stroke(edge, with: .color(.bshFixed(dark ? BSHRGB(164, 164, 164) : BSHRGB(194, 194, 194))), lineWidth: 0.6)
            context.stroke(strokes, with: .color(.bshFixed(dark ? BSHRGB(8, 8, 8) : BSHRGB(100, 100, 100))), lineWidth: 1)
        }
        .frame(width: 10, height: 10)
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 1)
                .onChanged { value in
                    if dragBase == nil { dragBase = extra }
                    extra = max(0, min(600, (dragBase ?? 0) + value.translation.height))
                }
                .onEnded { _ in dragBase = nil }
        )
        .onHover { inside in
            if inside { NSCursor.resizeUpDown.push() } else { NSCursor.pop() }
        }
    }
}
