import SwiftUI

struct MacPulseDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Pulse Header
                HStack(alignment: .center) {
                    HStack(spacing: 12) {
                        Image(systemName: "waveform.path.ecg")
                            .font(.title)
                            .foregroundStyle(Color.red)
                            .padding(10)
                            .background(Color.red.opacity(0.12), in: Circle())

                        VStack(alignment: .leading, spacing: 2) {
                            Text("Market Pulse")
                                .font(.title.weight(.bold))
                            if let d = store.pulse?.date {
                                Text("Briefing for \(d)")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Spacer()

                    // Language Selector
                    Picker("Language", selection: $store.pulseLanguage) {
                        Text("English").tag("en")
                        Text("中文 (ZH)").tag("zh")
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 140)

                    Button {
                        Task { await store.refreshPulse() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .keyboardShortcut("r", modifiers: .command)
                }
                .padding()
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))

                // Major Indices Grid
                if let indices = store.pulse?.indices, !indices.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Benchmark Indices & Asset Classes")
                            .font(.headline)

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                            ForEach(indices) { idx in
                                let isUp = (idx.changePct1d ?? 0) >= 0
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text(idx.ticker)
                                            .font(.body.monospaced().weight(.bold))
                                        Spacer()
                                        Text(String(format: "%+.2f%%", idx.changePct1d ?? 0))
                                            .font(.caption.monospacedDigit().weight(.semibold))
                                            .foregroundStyle(isUp ? Color.green : Color.red)
                                    }

                                    Text(idx.lastPrice != nil ? String(format: "$%.2f", idx.lastPrice!) : "—")
                                        .font(.title3.monospacedDigit().weight(.semibold))
                                }
                                .padding(12)
                                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(isUp ? Color.green.opacity(0.2) : Color.red.opacity(0.2), lineWidth: 1)
                                )
                            }
                        }
                    }
                }

                // AI Macro Synthesis Note
                if let note = store.pulse?.note {
                    let headline = store.pulseLanguage == "zh"
                        ? (note.headlineZh ?? note.headlineEn ?? "全球市场宏观简报")
                        : (note.headlineEn ?? "Global Macro Economic Synthesis")

                    let bullets = store.pulseLanguage == "zh"
                        ? (note.bulletsZh ?? note.bulletsEn ?? [])
                        : (note.bulletsEn ?? [])

                    VStack(alignment: .leading, spacing: 16) {
                        HStack(spacing: 8) {
                            Image(systemName: "sparkles")
                                .foregroundStyle(.blue)
                            Text("Macro Takeaways")
                                .font(.headline)
                        }

                        Text(headline)
                            .font(.title3.weight(.bold))

                        Divider()

                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(bullets, id: \.self) { bullet in
                                HStack(alignment: .top, spacing: 10) {
                                    Image(systemName: "chevron.right.circle.fill")
                                        .font(.caption)
                                        .foregroundStyle(Color.blue)
                                        .padding(.top, 3)

                                    Text(bullet)
                                        .font(.body)
                                        .lineSpacing(4)
                                }
                            }
                        }
                    }
                    .padding(20)
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
                } else {
                    ContentUnavailableView(
                        "Pulse Briefing In Transit",
                        systemImage: "waveform.path.ecg",
                        description: Text("Morning brief is being compiled by the synthesis engine.")
                    )
                }
            }
            .padding(24)
        }
    }
}
