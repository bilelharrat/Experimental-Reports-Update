import SwiftUI

struct MacPulseDeskView: View {
    @EnvironmentObject private var store: MacAppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                MacDeskHeader("Market Pulse", subtitle: store.pulse?.date.map { "Briefing for \($0)" } ?? "The morning brief: benchmarks and the macro read.") {
                    GlassSegmentedPicker("Language", selection: $store.pulseLanguage, segments: ["en": "English", "zh": "中文"])
                    .frame(width: 140)

                    Button {
                        Task { await store.refreshPulse() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }

                // Major Indices Grid
                if let indices = store.pulse?.indices, !indices.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Benchmarks")
                            .font(.dsHeadline)

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                            ForEach(indices) { idx in
                                let isUp = (idx.changePct1d ?? 0) >= 0
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text(idx.ticker)
                                            .font(.body.monospacedDigit().weight(.bold))
                                        Spacer()
                                        Text(String(format: "%+.2f%%", idx.changePct1d ?? 0))
                                            .font(.caption.monospacedDigit().weight(.semibold))
                                            .foregroundStyle(isUp ? Color.green : Color.red)
                                    }

                                    Text(idx.lastPrice != nil ? String(format: "$%.2f", idx.lastPrice!) : "—")
                                        .font(.title3.monospacedDigit().weight(.semibold))
                                }
                                .padding(12)
                                .appleGlassCard()
                            }
                        }
                    }
                }

                // AI Macro Synthesis Note
                if let note = store.pulse?.note {
                    let headline = store.pulseLanguage == "zh"
                        ? (note.headlineZh ?? note.headlineEn ?? "全球市场宏观简报")
                        : (note.headlineEn ?? "Global Macro Economic Synthesis")

                    let zh = store.pulseLanguage == "zh"
                    let bullets = note.bullets(zh: zh)
                    let sections = note.sections(zh: zh)

                    VStack(alignment: .leading, spacing: 16) {
                        MacCardHeader("Macro takeaways", systemImage: "sparkles")

                        Text(headline)
                            .font(.title3.weight(.bold))

                        Divider()

                        if !bullets.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                ForEach(Array(bullets.enumerated()), id: \.offset) { _, bullet in
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

                        if !sections.isEmpty {
                            VStack(alignment: .leading, spacing: 14) {
                                ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(section.title)
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(.secondary)
                                        Text(section.body)
                                            .font(.body)
                                            .lineSpacing(4)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                }
                            }
                        }
                    }
                    .padding(20)
                    .appleGlassCard()
                } else {
                    ContentUnavailableView(
                        "No briefing yet",
                        systemImage: "waveform.path.ecg",
                        description: Text("The morning brief appears here once the synthesis run has finished. Refresh to check.")
                    )
                    .frame(maxWidth: .infinity, minHeight: 360)
                }
            }
            .dsPage()
        }
        .background(Color.dsCanvas)
    }
}
