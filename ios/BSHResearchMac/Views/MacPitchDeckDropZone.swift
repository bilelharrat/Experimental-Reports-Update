import SwiftUI
import UniformTypeIdentifiers

struct MacPitchDeckDropBanner: View {
    @EnvironmentObject private var store: MacAppStore
    @State private var isTargeted: Bool = false

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: isTargeted ? "arrow.down.doc.fill" : "arrow.down.doc")
                .font(.system(size: 16))
                .foregroundStyle(isTargeted ? Color.accentColor : Color.secondary)

            VStack(alignment: .leading, spacing: 1) {
                Text(isTargeted ? "Drop Pitch Deck PDF Here" : "Drag & Drop Pitch Deck (PDF)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(isTargeted ? Color.accentColor : Color.primary)
                Text("Instant metric extraction & memo generation")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button {
                selectDeckViaPicker()
            } label: {
                Text("Browse…")
                    .font(.caption2.weight(.medium))
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isTargeted ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.05))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(
                    isTargeted ? Color.accentColor : Color.secondary.opacity(0.2),
                    style: StrokeStyle(lineWidth: 1, dash: isTargeted ? [4] : [])
                )
        )
        .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
            handleDrop(providers: providers)
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url, url.pathExtension.lowercased() == "pdf" else { return }
            DispatchQueue.main.async {
                store.ingestDeck(url: url)
            }
        }
        return true
    }

    private func selectDeckViaPicker() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.prompt = "Intake Pitch Deck"
        if panel.runModal() == .OK, let url = panel.url {
            store.ingestDeck(url: url)
        }
    }
}

struct MacPitchDeckIntakeSheet: View {
    let fileURL: URL?
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var companyName: String = ""
    @State private var filing = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "doc.badge.arrow.up")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                    Text("Pitch Deck Intake")
                        .font(.headline)
                }
                Spacer()
                Button("Cancel") { dismiss() }
                    .controlSize(.small)
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(.ultraThinMaterial)

            Divider()

            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(.red)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(fileURL?.lastPathComponent ?? "Deck")
                            .font(.subheadline.weight(.semibold))
                        Text(fileURL.map { $0.pathExtension.uppercased() + " · stays on this Mac" } ?? "")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(12)
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 6) {
                    Text("Company name").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    TextField("Company", text: $companyName)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { file() }
                }

                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "info.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Adding creates the company record on the server so it shows on the Pipeline as Sourcing. Automatic extraction of round, valuation and metrics from the slides is not wired yet — attach the deck to the company from the web Files list (Use in report) so the memo pipeline can read it.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .background(Color.accentColor.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))

                if let error {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }
            .padding(20)

            Divider()

            HStack {
                Spacer()
                Button {
                    file()
                } label: {
                    if filing {
                        ProgressView().controlSize(.small)
                    } else {
                        Label("Add to Pipeline", systemImage: "plus.circle")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .keyboardShortcut(.defaultAction)
                .disabled(filing || companyName.trimmingCharacters(in: .whitespaces).isEmpty || !store.canEditSources)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)
        }
        .frame(width: 480)
        .onAppear {
            let fname = fileURL?.deletingPathExtension().lastPathComponent ?? ""
            companyName = fname.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " ")
        }
    }

    private func file() {
        let name = companyName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        filing = true
        error = nil
        Task {
            if await store.addToPipeline(MacCompanyMatch(name: name)) != nil {
                dismiss()
            } else {
                error = store.error ?? "Could not add the company."
            }
            filing = false
        }
    }
}
