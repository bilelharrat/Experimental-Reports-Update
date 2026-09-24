//
//  MacCapTableSimulatorView.swift
//  BSHResearchMac
//
//  Sequoia/Carta-grade Cap Table & Dilution Waterfall Simulator.
//  Models investment check size, post-money valuation, unallocated option pool,
//  subsequent round dilution cascades, and exit return MOIC matrices.
//

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif
#if canImport(UIKit)
import UIKit
#endif

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

    @Environment(\.bureauResearchDesk) private var bureauDesk
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if BSHDesign.active == .bureau && bureauDesk {
            bureauBody
        } else {
            glassBody
        }
    }

    private var glassBody: some View {
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
                                .font(.ui(.caption))
                            Spacer()
                            Text("$\(checkSizeMillions, specifier: "%.1f")M")
                                .font(.ui(.caption).monospacedDigit().weight(.bold))
                        }
                        Slider(value: $checkSizeMillions, in: 1.0...80.0, step: 0.5)
                    }

                    // Pre-Money Valuation
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Pre-money")
                                .font(.ui(.caption))
                            Spacer()
                            Text("$\(preMoneyMillions, specifier: "%.1f")M")
                                .font(.ui(.caption).monospacedDigit().weight(.bold))
                        }
                        Slider(value: $preMoneyMillions, in: 5.0...400.0, step: 2.5)
                    }

                    // Option Pool Expansion
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Option pool")
                                .font(.ui(.caption))
                            Spacer()
                            Text("\(optionPoolPercent, specifier: "%.1f")%")
                                .font(.ui(.caption).monospacedDigit().weight(.bold))
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
                                .font(.ui(.caption).weight(.medium))
                        }
                        .toggleStyle(.checkbox)

                        if modelFutureDilution {
                            HStack {
                                Text("Cumulative dilution through exit")
                                    .font(.ui(.caption2))
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text("\(futureDilutionPercent, specifier: "%.0f")%")
                                    .font(.ui(.caption2).monospacedDigit().weight(.bold))
                            }
                            Slider(value: $futureDilutionPercent, in: 5.0...50.0, step: 1.0)
                        }
                    }
                    .padding(8)
                    .appleGlassTile(cornerRadius: 8)

                    // Reference Fund Size
                    HStack {
                        Text("Fund size")
                            .font(.ui(.caption2))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("$\(fundSizeMillions, specifier: "%.0f")M")
                            .font(.ui(.caption2).monospacedDigit().weight(.semibold))
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
                                .font(.ui(.caption).weight(.medium))
                                .frame(width: 170, alignment: .leading)

                            Text("\(finalDilutedOwnershipPercent, specifier: "%.1f")%")
                                .font(.ui(.caption).monospacedDigit())
                                .frame(width: 130, alignment: .trailing)
                                .foregroundStyle(.secondary)

                            Text("$\(proceeds, specifier: "%.1f")M")
                                .font(.ui(.caption).monospacedDigit().weight(.bold))
                                .frame(width: 130, alignment: .trailing)
                                .foregroundStyle(moic >= 10.0 ? Color.green : Color.primary)

                            Text("\(moic, specifier: "%.1f")x")
                                .font(.ui(.caption).monospacedDigit().weight(.bold))
                                .frame(width: 90, alignment: .trailing)
                                .foregroundStyle(moic >= 10.0 ? Color.green : (moic >= 3.0 ? Color.dsAccent : Color.primary))

                            HStack(spacing: 4) {
                                Text("\(fundReturnPct, specifier: "%.1f")%")
                                    .font(.ui(.caption).monospacedDigit().weight(isFundReturner ? .black : .semibold))
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
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(summary, forType: .string)
        #else
        UIPasteboard.general.string = summary
        #endif
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

// MARK: - Bureau

/// CapTableCard.vue on the Research Desk: the round terms and their sliders beside the
/// post-money tiles, the post-round ownership bar and legend, and the exit matrix.
extension MacCapTableSimulatorView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 18) {
            bureauHeader(ink)
            HStack(alignment: .top, spacing: 20) {
                bureauRoundTerms(ink)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                bureauPostMoney(ink)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            bureauOwnership(ink)
            bureauExits(ink)
        }
        .bureauDeskCard(padding: 16)
        .task(id: company.id) {
            saveState = nil
            copiedNotice = false
            resetToStandardSeriesA()
            await loadSaved()
        }
    }

    private func bureauButton(_ title: String?, icon: String, help: String = "", action: @escaping () -> Void) -> some View {
        Button(action: action) {
            if let title {
                MacBureauDeskButtonLabel(title: title, icon: icon, iconSize: 12, size: .small)
            } else {
                MacBureauDeskIcon(icon, size: 12)
            }
        }
        .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
        .help(help)
        .fixedSize()
    }

    private func bureauHeader(_ ink: MacBureauDeskInk) -> some View {
        MacBureauDeskHeaderWrap(spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                MacBureauDeskIcon("chart-pie", size: 13)
                    .foregroundStyle(ink.accent)
                    .frame(width: 18, height: 13)
                    .padding(.top, 1)
                VStack(alignment: .leading, spacing: 2) {
                    MacBureauDeskCaption(text: "Cap table & waterfall", size: 15, weight: .semibold, lineHeight: 18.75, color: ink.label)
                    MacBureauDeskCaption(
                        text: "Model the check, pre-money, option pool and later-round dilution; exits show proceeds and MOIC. Saved to the company record.",
                        size: 11,
                        lineHeight: 13.75,
                        color: ink.secondary
                    )
                }
            }
            .fixedSize()
            if !savedModelLoaded {
                MacBureauDeskSpinner()
            } else if savedModelFailed {
                HStack(spacing: 4) {
                    MacBureauDeskIcon("triangle-alert", size: 12)
                    MacBureauDeskCaption(text: "Saved inputs unavailable", size: 11, lineHeight: 13.75, color: ink.orange)
                }
                .foregroundStyle(ink.orange)
                bureauButton("Retry", icon: "rotate-cw") { Task { await loadSaved() } }
            } else if let saveState {
                MacBureauDeskCaption(text: saveState, size: 11, lineHeight: 13.75, color: ink.secondary)
            }
            if copiedNotice {
                MacBureauDeskCaption(text: "Copied", size: 11, lineHeight: 13.75, color: ink.green)
            }
            bureauButton(
                "Save",
                icon: "save",
                help: savedModelFailed
                    ? "The saved model could not be read; retry before saving so it is not overwritten with defaults"
                    : "Persist these inputs on the company record so IC Review and the decision record can cite them"
            ) {
                let inputs = MacCapModelInputs(
                    preMoneyMusd: preMoneyMillions, newMoneyMusd: checkSizeMillions, ourCheckMusd: checkSizeMillions,
                    optionPoolPctPost: optionPoolPercent, liquidationPreferenceX: 1.0, participating: false,
                    exitValuesMusd: scenarios.map(\.exitValuationMillions), notes: roundName
                )
                saveState = "Saving…"
                Task {
                    saveState = await store.saveCapModel(company.id, inputs: inputs) ? "Saved to \(company.name ?? company.id)" : "Save failed"
                }
            }
            .disabled(!store.canWriteDesk || !savedModelLoaded || savedModelFailed)
            bureauButton("Copy term sheet", icon: "copy") { copyTermSheetSummary() }
            bureauButton(nil, icon: "rotate-ccw", help: "Reset to a standard Series A") { resetToStandardSeriesA() }
        }
    }

    private func bureauLabel(_ text: String, ink: MacBureauDeskInk) -> some View {
        MacBureauDeskCaption(text: text, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
    }

    /// A caption on the left and its figure on the right.
    private func bureauReading(_ label: String, _ value: String, labelColor: Color, ink: MacBureauDeskInk) -> some View {
        HStack(spacing: 0) {
            MacBureauDeskCaption(text: label, color: labelColor)
            Spacer(minLength: 0)
            MacBureauDeskCaption(text: value, mono: true, color: ink.label)
        }
    }

    private func bureauSlider(_ label: String, _ value: String, binding: Binding<Double>, range: ClosedRange<Double>, step: Double, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            bureauReading(label, value, labelColor: ink.label, ink: ink)
            MacBureauDeskRange(value: binding, range: range, step: step)
        }
    }

    private func bureauRoundTerms(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            bureauLabel("Round terms", ink: ink)
            HStack(spacing: 12) {
                MacBureauDeskCaption(text: "Round", color: ink.label)
                MacBureauDeskSegmented(
                    selection: $roundName,
                    segments: ["Seed", "Series A", "Series B", "Series C", "Growth"].map { ($0, $0) }
                )
            }
            bureauSlider("Our check", "$\(String(format: "%.1f", checkSizeMillions))M", binding: $checkSizeMillions, range: 1...80, step: 0.5, ink: ink)
            bureauSlider("Pre-money", "$\(String(format: "%.1f", preMoneyMillions))M", binding: $preMoneyMillions, range: 5...400, step: 2.5, ink: ink)
            bureauSlider("Option pool", "\(String(format: "%.1f", optionPoolPercent))%", binding: $optionPoolPercent, range: 0...25, step: 1, ink: ink)
        }
    }

    private func bureauTile(_ label: String, _ value: String, _ detail: String, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(BSHType.bureauSans(11, weight: .medium))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(13.75, 11)
            Text(value)
                .font(BSHType.bureauSans(15, weight: .semibold).monospacedDigit())
                .foregroundStyle(ink.label)
                .lineLimit(1)
                .bureauDeskLine(18, 15)
            // `align-items: flex-start`: a line longer than the tile runs into its padding.
            Text(detail)
                .font(BSHType.bureauSans(11))
                .foregroundStyle(ink.tertiary)
                .lineLimit(1)
                .fixedSize()
                .bureauDeskLine(13.75, 11)
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
    }

    private func bureauPostMoney(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            bureauLabel("Post-money & dilution", ink: ink)
            MacBureauDeskGrid(columns: 3, spacing: 12) {
                bureauTile("Post-money", "$\(String(format: "%.1f", postMoneyMillions))M", "pre-money + check", ink: ink)
                bureauTile("Ownership at close", "\(String(format: "%.1f", initialOwnershipPercent))%", "check ÷ post-money", ink: ink)
                bureauTile(
                    "Ownership at exit",
                    "\(String(format: "%.1f", finalDilutedOwnershipPercent))%",
                    modelFutureDilution ? "after \(String(format: "%.0f", futureDilutionPercent))% later dilution" : "no later rounds modelled",
                    ink: ink
                )
            }
            VStack(alignment: .leading, spacing: 6) {
                Button {
                    modelFutureDilution.toggle()
                } label: {
                    HStack(spacing: 8) {
                        MacBureauDeskCheckMark(isOn: modelFutureDilution)
                        MacBureauDeskCaption(text: "Model later-round dilution", weight: .medium, color: ink.label)
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(MacBureauFlatButtonStyle())
                if modelFutureDilution {
                    bureauReading("Cumulative dilution through exit", "\(String(format: "%.0f", futureDilutionPercent))%", labelColor: ink.secondary, ink: ink)
                    MacBureauDeskRange(value: $futureDilutionPercent, range: 5...50, step: 1)
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 8, style: .circular), fill: ink.tile)
            bureauReading("Fund size", "$\(String(format: "%.0f", fundSizeMillions))M", labelColor: ink.secondary, ink: ink)
        }
    }

    private func bureauOwnership(_ ink: MacBureauDeskInk) -> some View {
        let total = max(0.0001, foundersPreMoneyDilutionPercent + optionPoolPercent + initialOwnershipPercent)
        let shares: [(Double, Color)] = [
            (foundersPreMoneyDilutionPercent / total, ink.blue),
            (optionPoolPercent / total, ink.orange),
            (initialOwnershipPercent / total, ink.green),
        ]
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 0) {
                bureauLabel("Post-round ownership", ink: ink)
                Spacer(minLength: 0)
                if !isOverAllocated {
                    MacBureauDeskCaption(text: "check + common + pool = 100%", size: 11, lineHeight: 13.75, mono: true, color: ink.tertiary)
                }
            }
            GeometryReader { proxy in
                let usable = max(0, proxy.size.width - 4)
                HStack(spacing: 2) {
                    ForEach(Array(shares.enumerated()), id: \.offset) { _, share in
                        Rectangle()
                            .fill(share.1)
                            .frame(width: usable * CGFloat(share.0))
                    }
                }
                .frame(width: proxy.size.width, alignment: .leading)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .circular))
                .bureauSnap(x: .whole)
            }
            .frame(height: 14)
            if isOverAllocated {
                HStack(spacing: 6) {
                    MacBureauDeskIcon("triangle-alert", size: 14)
                    MacBureauDeskCaption(text: "Check + option pool exceed 100% of post-money; lower the check or raise pre-money.", size: 11, lineHeight: 13.75, color: ink.orange)
                }
                .foregroundStyle(ink.orange)
            }
            MacBureauDeskFlow(spacing: 16) {
                bureauLegend("Founders & common", foundersPreMoneyDilutionPercent, tint: ink.blue, ink: ink)
                bureauLegend("Option pool", optionPoolPercent, tint: ink.orange, ink: ink)
                bureauLegend("Our stake · \(roundName)", initialOwnershipPercent, tint: ink.green, ink: ink)
            }
        }
    }

    private func bureauLegend(_ title: String, _ value: Double, tint: Color, ink: MacBureauDeskInk) -> some View {
        HStack(spacing: 5) {
            Circle().fill(tint).frame(width: 7, height: 7)
            MacBureauDeskCaption(text: title, color: ink.secondary)
            MacBureauDeskCaption(text: "\(String(format: "%.1f", value))%", mono: true, color: ink.label)
        }
    }

    private func bureauExits(_ ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 0) {
                bureauLabel("Exit proceeds & MOIC", ink: ink)
                Spacer(minLength: 0)
                MacBureauDeskCaption(
                    text: "at \(String(format: "%.1f", finalDilutedOwnershipPercent))% ownership at exit",
                    size: 11,
                    lineHeight: 13.75,
                    mono: true,
                    color: ink.tertiary
                )
            }
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 10) {
                    MacBureauDeskCell(text: "Exit value", width: 170, size: 11, weight: .medium, lineHeight: 13.75, trailing: false, color: ink.secondary)
                    MacBureauDeskCell(text: "Stake", width: 130, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                    MacBureauDeskCell(text: "Proceeds", width: 130, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                    MacBureauDeskCell(text: "MOIC", width: 90, size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                    Text("Fund returned")
                        .font(BSHType.bureauSans(11, weight: .medium))
                        .foregroundStyle(ink.secondary)
                        .lineLimit(1)
                        .bureauExactWidth("Fund returned", size: 11, weight: .medium)
                        .bureauDeskLine(13.75, 11)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(scenarios) { scenario in
                        bureauExitRow(scenario, ink: ink)
                    }
                }
            }
        }
    }

    private func bureauExitRow(_ scenario: ExitScenario, ink: MacBureauDeskInk) -> some View {
        let proceeds = scenario.exitValuationMillions * (finalDilutedOwnershipPercent / 100.0)
        let moic = checkSizeMillions > 0 ? proceeds / checkSizeMillions : 0.0
        let fundReturn = fundSizeMillions > 0 ? (proceeds / fundSizeMillions) * 100.0 : 0.0
        let returner = fundReturn >= 100.0
        let pct = String(format: "%.1f", fundReturn) + "%"
        return HStack(spacing: 10) {
            MacBureauDeskCell(text: scenario.label, width: 170, size: 10, lineHeight: 12.5, trailing: false, color: ink.label)
            MacBureauDeskCell(text: String(format: "%.1f", finalDilutedOwnershipPercent) + "%", width: 130, size: 10, lineHeight: 12.5, mono: true, color: ink.secondary)
            MacBureauDeskCell(text: "$" + String(format: "%.1f", proceeds) + "M", width: 130, size: 10, lineHeight: 12.5, mono: true, color: moic >= 10 ? ink.green : ink.label)
            MacBureauDeskCell(
                text: String(format: "%.1f", moic) + "x",
                width: 90,
                size: 10,
                lineHeight: 12.5,
                mono: true,
                color: moic >= 10 ? ink.green : (moic >= 3 ? ink.accent : ink.label)
            )
            HStack(spacing: 4) {
                Spacer(minLength: 0)
                MacBureauDeskCaption(text: pct, weight: returner ? .bold : .semibold, mono: true, color: returner ? ink.green : ink.secondary)
                if returner {
                    MacBureauDeskPill(text: "Returns the fund", tint: ink.green)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: returner ? ink.green.opacity(0.05) : .clear)
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
                .font(.ui(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.ui(size: 16, weight: .bold).monospacedDigit())
                .monospacedDigit()
                .foregroundStyle(Color.dsAccent)
            Text(subtext)
                .font(.ui(size: 10))
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
                .font(.ui(.caption2))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.ui(.caption2).monospacedDigit().weight(.semibold))
        }
    }
}
