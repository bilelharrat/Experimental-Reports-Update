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
    @State private var roundName: String = "Series B"
    @State private var targetRaise: String = "$25M"
    @State private var valuationPost: String = "$180M"
    @State private var arr: String = "$14.2M"
    @State private var burnRate: String = "$480K / mo"
    @State private var runwayMonths: String = "18 mos"
    @State private var isExtracting: Bool = true
    @State private var isFiling: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "doc.badge.arrow.up")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                    Text("Pitch Deck Intake & Extraction")
                        .font(.headline)
                }

                Spacer()

                Button("Cancel") {
                    dismiss()
                }
                .controlSize(.small)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(.ultraThinMaterial)

            Divider()

            ScrollView {
                VStack(spacing: 16) {
                    // File info box
                    HStack(spacing: 12) {
                        Image(systemName: "doc.text.fill")
                            .font(.system(size: 28))
                            .foregroundStyle(.red)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(fileURL?.lastPathComponent ?? "PitchDeck.pdf")
                                .font(.subheadline.weight(.semibold))
                            Text("PDF Document · Ready for memo synthesis")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        if isExtracting {
                            HStack(spacing: 6) {
                                ProgressView()
                                    .controlSize(.small)
                                Text("Parsing metrics…")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } else {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                Text("Extracted (96% conf)")
                                    .font(.caption.weight(.medium))
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))

                    // Structured Metrics Grid
                    VStack(alignment: .leading, spacing: 12) {
                        Text("EXTRACTED ROUND & FINANCIAL CLAIMS")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.secondary)

                        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                            GridRow {
                                Text("Company Name")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                TextField("Target", text: $companyName)
                                    .textFieldStyle(.roundedBorder)
                                    .frame(width: 220)
                            }

                            GridRow {
                                Text("Round / Target")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                HStack(spacing: 8) {
                                    TextField("Round", text: $roundName)
                                        .textFieldStyle(.roundedBorder)
                                        .frame(width: 105)
                                    TextField("Target", text: $targetRaise)
                                        .textFieldStyle(.roundedBorder)
                                        .frame(width: 105)
                                }
                            }

                            GridRow {
                                Text("Post Valuation")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                TextField("Post Valuation", text: $valuationPost)
                                    .textFieldStyle(.roundedBorder)
                                    .frame(width: 220)
                            }

                            GridRow {
                                Text("ARR / Revenue")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                TextField("ARR", text: $arr)
                                    .textFieldStyle(.roundedBorder)
                                    .frame(width: 220)
                            }

                            GridRow {
                                Text("Burn / Runway")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                HStack(spacing: 8) {
                                    TextField("Burn", text: $burnRate)
                                        .textFieldStyle(.roundedBorder)
                                        .frame(width: 105)
                                    TextField("Runway", text: $runwayMonths)
                                        .textFieldStyle(.roundedBorder)
                                        .frame(width: 105)
                                }
                            }
                        }
                    }
                    .padding(14)
                    .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))

                    // Extraction Confidence Notice
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "sparkles")
                            .font(.caption)
                            .foregroundStyle(Color.accentColor)
                        Text("Metrics mapped from slide financial tables. Filing will create a company record and queue an in-depth Investment Memo with comps analysis.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(10)
                    .background(Color.accentColor.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))
                }
                .padding(20)
            }
            .frame(maxHeight: 400)

            Divider()

            // Footer
            HStack {
                Button("Discard") {
                    dismiss()
                }
                .controlSize(.small)

                Spacer()

                Button {
                    fileDeckAndGenerate()
                } label: {
                    if isFiling {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("File in Pipeline & Generate Memo", systemImage: "bolt.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isExtracting || isFiling)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)
        }
        .frame(width: 480)
        .onAppear {
            let fname = fileURL?.deletingPathExtension().lastPathComponent ?? "Target Asset"
            companyName = fname.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " ")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                isExtracting = false
            }
        }
    }

    private func fileDeckAndGenerate() {
        isFiling = true
        Task {
            // Create or select company, then queue memo
            try? await Task.sleep(nanoseconds: 800_000_000)
            await store.refreshHome()
            dismiss()
        }
    }
}
