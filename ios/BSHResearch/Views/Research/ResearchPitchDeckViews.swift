import SwiftUI
import UniformTypeIdentifiers

public struct MacPitchDeckDropBanner: View {
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var showFilePicker = false

    public init() {}

    public var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "doc.badge.plus")
                .foregroundStyle(Color.accentColor)
            Text("File pitch deck (PDF/PPTX) to extract terms")
                .font(.dsCaption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer(minLength: 4)
            Button("Browse…") {
                showFilePicker = true
            }
            .font(.caption2.weight(.medium))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .appleGlassTile(cornerRadius: 8)
        .fileImporter(
            isPresented: $showFilePicker,
            allowedContentTypes: [UTType.pdf, UTType("org.openxmlformats.presentationml.presentation")].compactMap { $0 },
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first {
                    store.intakeDeckURL = url
                }
            case .failure:
                break
            }
        }
    }
}

public struct MacPitchDeckIntakeSheet: View {
    public let fileURL: URL?
    @EnvironmentObject private var store: ResearchDeskStore
    @Environment(\.dismiss) private var dismiss

    @State private var companyName: String = ""
    @State private var attachTo: String = ""
    @State private var filing = false
    @State private var error: String?
    @State private var result: MacIntakeResult?

    public init(fileURL: URL?) {
        self.fileURL = fileURL
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("Document") {
                    HStack {
                        Image(systemName: "doc.text.fill").foregroundStyle(.red)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(fileURL?.lastPathComponent ?? "Deck")
                                .font(.subheadline.weight(.semibold))
                            Text(fileURL.map { $0.pathExtension.uppercased() + " · uploads to the research server" } ?? "")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if let res = result {
                    Section {
                        HStack {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(res.company.name ?? res.company.id)
                                    .font(.subheadline.weight(.semibold))
                                Text("\(res.fileName ?? "Deck") · \(res.slideCount) slides read")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if let fit = res.thesis {
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text(fit.score.map { "\($0)% fit" } ?? fit.label)
                                        .font(.caption.weight(.bold).monospacedDigit())
                                        .foregroundStyle(fitColor(fit))
                                    Text(fit.label).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if !res.fields.isEmpty {
                        Section("Extracted Metrics") {
                            ForEach(res.fields) { field in
                                HStack(alignment: .top) {
                                    Text(field.label)
                                        .font(.caption.weight(.semibold))
                                        .frame(width: 100, alignment: .leading)
                                    Text(field.display)
                                        .font(.caption.monospacedDigit().weight(.medium))
                                        .frame(width: 80, alignment: .leading)
                                    if let excerpt = field.excerpt {
                                        Text(excerpt)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(2)
                                    }
                                }
                            }
                        }
                    }

                    if let questions = res.thesis?.openQuestions, !questions.isEmpty {
                        Section("Open Questions") {
                            ForEach(questions, id: \.self) { q in
                                Label(q, systemImage: "questionmark.circle")
                                    .font(.caption)
                            }
                        }
                    }
                } else {
                    Section("Company Link") {
                        Picker("Attach to", selection: $attachTo) {
                            Text("New company").tag("")
                            ForEach(store.companies) { company in
                                Text(company.name ?? company.id).tag(company.id)
                            }
                        }

                        if attachTo.isEmpty {
                            TextField("Company name", text: $companyName)
                        }
                    }

                    if let error {
                        Section {
                            Text(error).font(.caption).foregroundStyle(.red)
                        }
                    }
                }
            }
            .navigationTitle(result == nil ? "Pitch Deck Intake" : "Deck Filed")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(result == nil ? "Cancel" : "Done") { dismiss() }
                }
                if result == nil {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(filing ? "Extracting…" : "File & Extract") {
                            file()
                        }
                        .disabled(filing || (attachTo.isEmpty && companyName.trimmingCharacters(in: .whitespaces).isEmpty))
                    }
                }
            }
            .onAppear {
                let fname = fileURL?.deletingPathExtension().lastPathComponent ?? ""
                companyName = fname.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " ")
            }
        }
    }

    private func fitColor(_ fit: MacThesisScore) -> Color {
        switch fit.fit {
        case "strong": return .green
        case "partial": return .orange
        case "weak", "disqualified": return .red
        default: return .secondary
        }
    }

    private func file() {
        guard let url = fileURL else { return }
        let name = companyName.trimmingCharacters(in: .whitespaces)
        filing = true
        error = nil
        Task {
            let accessed = url.startAccessingSecurityScopedResource()
            defer { if accessed { url.stopAccessingSecurityScopedResource() } }
            if let r = await store.intakeDeck(fileURL: url, companyName: attachTo.isEmpty ? name : nil, companyId: attachTo.isEmpty ? nil : attachTo) {
                result = r
            } else {
                error = store.error ?? "Could not file the deck."
            }
            filing = false
        }
    }
}
