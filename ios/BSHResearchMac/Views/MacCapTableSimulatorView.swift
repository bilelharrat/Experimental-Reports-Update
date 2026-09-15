//
//  MacCapTableSimulatorView.swift
//  BSHResearchMac
//
//  Sequoia/Carta-grade Cap Table & Dilution Waterfall Simulator.
//  Models investment check size, post-money valuation, unallocated option pool,
//  subsequent round dilution cascades, and exit return MOIC matrices.
//

import SwiftUI
import AppKit

struct MacCapTableSimulatorView: View {
    let company: MacCompany

    // MARK: - Investment Round Inputs
    @State private var roundName: String = "Series A"
    @State private var checkSizeMillions: Double = 15.0
    @State private var preMoneyMillions: Double = 60.0
    @State private var optionPoolPercent: Double = 10.0
    @State private var modelFutureDilution: Bool = true
    @State private var futureDilutionPercent: Double = 22.0 // cumulative Series B/C/IPO dilution
    @State private var fundSizeMillions: Double = 400.0
    @State private var copiedNotice: Bool = false
    @State private var saveState: String?
    @State private var savedModelLoaded: Bool = false
    @State private var savedModelFailed: Bool = false
    @EnvironmentObject private var store: MacAppStore

    // MARK: - Computed Cap Table Math
    private var postMoneyMillions: Double {
        preMoneyMillions + checkSizeMillions
    }

    private var initialOwnershipPercent: Double {
        guard postMoneyMillions > 0 else { return 0 }
        return (checkSizeMillions / postMoneyMillions) * 100.0
    }

    private var foundersPreMoneyDilutionPercent: Double {
        max(0, 100.0 - initialOwnershipPercent - optionPoolPercent)
    }

    private var isOverAllocated: Bool {
        initialOwnershipPercent + optionPoolPercent > 100.0
    }

    private var finalDilutedOwnershipPercent: Double {
        if modelFutureDilution {
            let retentionRate = (100.0 - futureDilutionPercent) / 100.0
            return initialOwnershipPercent * retentionRate
        } else {
            return initialOwnershipPercent
        }
    }

    // MARK: - Standard VC Exit Horizons
    private struct ExitScenario: Identifiable {
        let id = UUID()
        let exitValuationMillions: Double
        let label: String
    }

    private let scenarios: [ExitScenario] = [
        ExitScenario(exitValuationMillions: 250.0, label: "$250M · acquisition"),
        ExitScenario(exitValuationMillions: 500.0, label: "$500M · strategic"),
        ExitScenario(exitValuationMillions: 1000.0, label: "$1.0B · unicorn"),
        ExitScenario(exitValuationMillions: 3000.0, label: "$3.0B · public scale"),
        ExitScenario(exitValuationMillions: 5000.0, label: "$5.0B · decacorn"),
        ExitScenario(exitValuationMillions: 10000.0, label: "$10B · mega exit")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            MacCardHeader("Cap table & waterfall", subtitle: "Model the check, pre-money, option pool and later-round dilution; exits show proceeds and MOIC. Saved to the company record.", systemImage: "chart.pie") {
                if !savedModelLoaded {
                    ProgressView().controlSize(.small)
                } else if savedModelFailed {
                    Label("Saved inputs unavailable", systemImage: "exclamationmark.triangle")
                        .font(.dsCaption).foregroundStyle(Color.dsWarning)
                    Button("Retry") { Task { await loadSaved() } }
                        .controlSize(.small)
                } else if let saveState {
                    Text(saveState).font(.dsCaption).foregroundStyle(.secondary)
                }
                if copiedNotice {
                    Text("Copied").font(.dsCaption).foregroundStyle(.green).transition(.opacity)
                }
                Button {
                    let inputs = MacCapModelInputs(
                        preMoneyMusd: preMoneyMillions, newMoneyMusd: checkSizeMillions, ourCheckMusd: checkSizeMillions,
                        optionPoolPctPost: optionPoolPercent, liquidationPreferenceX: 1.0, participating: false,
                        exitValuesMusd: scenarios.map(\.exitValuationMillions), notes: roundName
                    )
                    saveState = "Saving…"
                    Task {
                        saveState = await store.saveCapModel(company.id, inputs: inputs) ? "Saved to \(company.title)" : "Save failed"
                    }
                } label: {
                    Label("Save", systemImage: "tray.and.arrow.down")
                }
                .controlSize(.small)
                .disabled(!store.canWriteDesk || !savedModelLoaded || savedModelFailed)
                .help(savedModelFailed
                      ? "The saved model could not be read; retry before saving so it is not overwritten with defaults"
                      : "Persist these inputs on the company record so IC Review and the decision record can cite them")
                Button {
                    copyTermSheetSummary()
                } label: {
                    Label("Copy term sheet", systemImage: "doc.on.doc")
                }
                .controlSize(.small)
                Button {
                    resetToStandardSeriesA()
                } label: {
                    Image(systemName: "arrow.counterclockwise")
                }
                .controlSize(.small)
                .help("Reset to a standard Series A")
            }

            // Round Inputs Grid
            HStack(alignment: .top, spacing: 20) {
                // Left Column: Investment Parameters
                VStack(alignment: .leading, spacing: 14) {
                    MacSectionLabel("Round terms")

                    // Target Round Picker
                    LabeledContent("Round") {
                        GlassSegmentedPicker("Round", selection: $roundName, segments: [
                            "Seed": "Seed", "Series A": "Series A", "Series B": "Series B",
                            "Series C": "Series C", "Growth": "Growth",
                        ])
                    }

                    // Check Size
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Our check")
                                .font(.caption)
                            Spacer()
                            Text("$\(checkSizeMillions, specifier: "%.1f")M")
                                .font(.caption.monospacedDigit().weight(.bold))
                        }
                        Slider(value: $checkSizeMillions, in: 1.0...80.0, step: 0.5)
                    }

                    // Pre-Money Valuation
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Pre-money")
                                .font(.caption)
                            Spacer()
                            Text("$\(preMoneyMillions, specifier: "%.1f")M")
                                .font(.caption.monospacedDigit().weight(.bold))
                        }
                        Slider(value: $preMoneyMillions, in: 5.0...400.0, step: 2.5)
                    }

                    // Option Pool Expansion
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Option pool")
                                .font(.caption)
                            Spacer()
                            Text("\(optionPoolPercent, specifier: "%.1f")%")
                                .font(.caption.monospacedDigit().weight(.bold))
                        }
                        Slider(value: $optionPoolPercent, in: 0.0...25.0, step: 1.0)
                    }
                }
                .frame(maxWidth: .infinity)

                // Right Column: Output Summary & Future Dilution
                VStack(alignment: .leading, spacing: 14) {
                    MacSectionLabel("Post-money & dilution")

                    // Key Outputs Card
                    HStack(spacing: 12) {
                        MacStatTile(label: "Post-money", value: "$\(String(format: "%.1f", postMoneyMillions))M", detail: "pre-money + check", compact: true)
                        MacStatTile(label: "Ownership at close", value: "\(String(format: "%.1f", initialOwnershipPercent))%", detail: "check ÷ post-money", compact: true)
                        MacStatTile(label: "Ownership at exit", value: "\(String(format: "%.1f", finalDilutedOwnershipPercent))%", detail: modelFutureDilution ? "after \(String(format: "%.0f", futureDilutionPercent))% later dilution" : "no later rounds modelled", compact: true)
                    }

                    // Future Dilution Toggle & Slider
                    VStack(alignment: .leading, spacing: 6) {
                        Toggle(isOn: $modelFutureDilution) {
                            Text("Model later-round dilution")
                                .font(.caption.weight(.medium))
                        }
                        .toggleStyle(.checkbox)

                        if modelFutureDilution {
                            HStack {
                                Text("Cumulative dilution through exit")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text("\(futureDilutionPercent, specifier: "%.0f")%")
                                    .font(.caption2.monospacedDigit().weight(.bold))
                            }
                            Slider(value: $futureDilutionPercent, in: 5.0...50.0, step: 1.0)
                        }
                    }
                    .padding(8)
                    .appleGlassTile(cornerRadius: 8)

                    // Reference Fund Size
                    HStack {
                        Text("Fund size")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("$\(fundSizeMillions, specifier: "%.0f")M")
                            .font(.caption2.monospacedDigit().weight(.semibold))
                    }
                }
                .frame(maxWidth: .infinity)
            }

            // Visual Cap Table Structure Bar
            VStack(alignment: .leading, spacing: 6) {
                MacSectionLabel("Post-round ownership", trailing: isOverAllocated ? nil : "check + common + pool = 100%")

                GeometryReader { geo in
                    let founders = foundersPreMoneyDilutionPercent
                    let pool = max(0, optionPoolPercent)
                    let ours = max(0, initialOwnershipPercent)
                    let total = max(0.0001, founders + pool + ours)
                    let avail = max(0, geo.size.width - 4)
                    HStack(spacing: 2) {
                        // Founders & Common
                        Rectangle()
                            .fill(Color.blue)
                            .frame(width: avail * CGFloat(founders / total))
                            .help("Founders & Prior Investors: \(String(format: "%.1f", founders))%")

                        // Option Pool
                        Rectangle()
                            .fill(Color.orange)
                            .frame(width: avail * CGFloat(pool / total))
                            .help("Unallocated Option Pool: \(String(format: "%.1f", pool))%")

                        // Our Ownership
                        Rectangle()
                            .fill(Color.green)
                            .frame(width: avail * CGFloat(ours / total))
                            .help("Our Fund (\(roundName)): \(String(format: "%.1f", ours))%")
                    }
                    .frame(width: geo.size.width, alignment: .leading)
                    .clipped()
                    .cornerRadius(4)
                }
                .frame(height: 14)

                if isOverAllocated {
                    Label("Check + option pool exceed 100% of post-money; lower the check or raise pre-money.", systemImage: "exclamationmark.triangle")
                        .font(.dsCaption)
                        .foregroundStyle(Color.dsWarning)
                }

                HStack(spacing: 16) {
                    LegendItem(color: .blue, title: "Founders & common", value: "\(String(format: "%.1f", foundersPreMoneyDilutionPercent))%")
                    LegendItem(color: .orange, title: "Option pool", value: "\(String(format: "%.1f", optionPoolPercent))%")
                    LegendItem(color: .green, title: "Our stake · \(roundName)", value: "\(String(format: "%.1f", initialOwnershipPercent))%")
                }
            }

            // Exit Return & MOIC Matrix Table
            VStack(alignment: .leading, spacing: 8) {
                MacSectionLabel("Exit proceeds & MOIC", trailing: "at \(String(format: "%.1f", finalDilutedOwnershipPercent))% ownership at exit")

                // Table Header
                HStack(spacing: 10) {
                    Text("Exit value")
                        .frame(width: 170, alignment: .leading)
                    Text("Stake")
                        .frame(width: 130, alignment: .trailing)
                    Text("Proceeds")
                        .frame(width: 130, alignment: .trailing)
                    Text("MOIC")
                        .frame(width: 90, alignment: .trailing)
                    Text("Fund returned")
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .font(.dsLabel)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)

                // Table Rows
                VStack(spacing: 4) {
                    ForEach(scenarios) { sc in
                        let proceeds = (sc.exitValuationMillions * (finalDilutedOwnershipPercent / 100.0))
                        let moic = checkSizeMillions > 0 ? proceeds / checkSizeMillions : 0.0
                        let fundReturnPct = fundSizeMillions > 0 ? (proceeds / fundSizeMillions) * 100.0 : 0.0
                        let isFundReturner = fundReturnPct >= 100.0

                        HStack(spacing: 10) {
                            Text(sc.label)
                                .font(.caption.weight(.medium))
                                .frame(width: 170, alignment: .leading)

                            Text("\(finalDilutedOwnershipPercent, specifier: "%.1f")%")
                                .font(.caption.monospacedDigit())
                                .frame(width: 130, alignment: .trailing)
                                .foregroundStyle(.secondary)

                            Text("$\(proceeds, specifier: "%.1f")M")
                                .font(.caption.monospacedDigit().weight(.bold))
                                .frame(width: 130, alignment: .trailing)
                                .foregroundStyle(moic >= 10.0 ? Color.green : Color.primary)

                            Text("\(moic, specifier: "%.1f")x")
                                .font(.caption.monospacedDigit().weight(.bold))
                                .frame(width: 90, alignment: .trailing)
                                .foregroundStyle(moic >= 10.0 ? Color.green : (moic >= 3.0 ? Color.accentColor : Color.primary))

                            HStack(spacing: 4) {
                                Text("\(fundReturnPct, specifier: "%.1f")%")
                                    .font(.caption.monospacedDigit().weight(isFundReturner ? .black : .semibold))
                                    .foregroundStyle(isFundReturner ? Color.green : Color.secondary)

                                if isFundReturner {
                                    MacStatusPill(text: "Returns the fund", color: .green)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(isFundReturner ? Color.green.opacity(0.05) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
                    }
                }
            }
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
        .task(id: company.id) {
            saveState = nil
            copiedNotice = false
            resetToStandardSeriesA()
            await loadSaved()
        }
    }

    // MARK: - Actions
    /// Loads the saved model; Save stays disabled until the server record has been read,
    /// so a failed read can't be overwritten with the defaults shown meanwhile.
    private func loadSaved() async {
        savedModelLoaded = false
        savedModelFailed = false
        await store.loadCapModel(company.id)
        guard !Task.isCancelled else { return }
        if let model = store.capModelByCompany[company.id] {
            applySaved(model)
        } else {
            savedModelFailed = true
        }
        savedModelLoaded = true
    }

    private func applySaved(_ model: MacCapModel) {
        preMoneyMillions = model.inputs.preMoneyMusd ?? 60.0
        checkSizeMillions = model.inputs.ourCheckMusd ?? model.inputs.newMoneyMusd ?? 15.0
        optionPoolPercent = model.inputs.optionPoolPctPost ?? 10.0
        roundName = model.inputs.notes.isEmpty ? "Series A" : model.inputs.notes
    }

    private func resetToStandardSeriesA() {
        roundName = "Series A"
        checkSizeMillions = 15.0
        preMoneyMillions = 60.0
        optionPoolPercent = 10.0
        modelFutureDilution = true
        futureDilutionPercent = 22.0
    }

    private func copyTermSheetSummary() {
        let summary = """
        TERM SHEET CAP TABLE SUMMARY — \(company.name ?? company.id)
        Round: \(roundName)
        Investment Check Size: $\(String(format: "%.1f", checkSizeMillions))M
        Pre-Money Valuation: $\(String(format: "%.1f", preMoneyMillions))M
        Post-Money Valuation: $\(String(format: "%.1f", postMoneyMillions))M
        Initial Ownership: \(String(format: "%.1f", initialOwnershipPercent))%
        Unallocated Option Pool: \(String(format: "%.1f", optionPoolPercent))%
        Modeled Future Dilution: \(String(format: "%.0f", futureDilutionPercent))%
        Diluted Ownership at Exit: \(String(format: "%.1f", finalDilutedOwnershipPercent))%

        EXIT SCENARIOS:
        - $250M Exit  -> Proceeds: $\(String(format: "%.1f", 250.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (250.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        - $500M Exit  -> Proceeds: $\(String(format: "%.1f", 500.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (500.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        - $1.0B Exit  -> Proceeds: $\(String(format: "%.1f", 1000.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (1000.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        - $3.0B Exit  -> Proceeds: $\(String(format: "%.1f", 3000.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (3000.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        - $5.0B Exit  -> Proceeds: $\(String(format: "%.1f", 5000.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (5000.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        - $10.0B Exit -> Proceeds: $\(String(format: "%.1f", 10000.0 * finalDilutedOwnershipPercent / 100.0))M (\(String(format: "%.1f", (10000.0 * finalDilutedOwnershipPercent / 100.0) / checkSizeMillions))x MOIC)
        """
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(summary, forType: .string)
        withAnimation {
            copiedNotice = true
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation {
                copiedNotice = false
            }
        }
    }
}

// MARK: - Output Metric Tile
private struct OutputMetricTile: View {
    let title: String
    let value: String
    let subtext: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 16, weight: .bold).monospacedDigit())
                .monospacedDigit()
                .foregroundStyle(Color.accentColor)
            Text(subtext)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))
    }
}

// MARK: - Legend Item
private struct LegendItem: View {
    let color: Color
    let title: String
    let value: String

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption2.monospacedDigit().weight(.semibold))
        }
    }
}
