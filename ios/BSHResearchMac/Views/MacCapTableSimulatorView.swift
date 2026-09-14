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

    // MARK: - Computed Cap Table Math
    private var postMoneyMillions: Double {
        preMoneyMillions + checkSizeMillions
    }

    private var initialOwnershipPercent: Double {
        guard postMoneyMillions > 0 else { return 0 }
        return (checkSizeMillions / postMoneyMillions) * 100.0
    }

    private var foundersPreMoneyDilutionPercent: Double {
        100.0 - initialOwnershipPercent - optionPoolPercent
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
        ExitScenario(exitValuationMillions: 250.0, label: "$250M (Acquisition)"),
        ExitScenario(exitValuationMillions: 500.0, label: "$500M (Strategic)"),
        ExitScenario(exitValuationMillions: 1000.0, label: "$1.0B (Unicorn)"),
        ExitScenario(exitValuationMillions: 3000.0, label: "$3.0B (Public Scale)"),
        ExitScenario(exitValuationMillions: 5000.0, label: "$5.0B (Decacorn)"),
        ExitScenario(exitValuationMillions: 10000.0, label: "$10.0B (Mega Exit)")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Header with Round Selector & Action
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Image(systemName: "chart.pie.fill")
                            .foregroundStyle(Color.accentColor)
                        Text("Cap Table & Waterfall Dilution Simulator")
                            .font(.headline)
                        Text("CARTA / EXCEL GRADE")
                            .font(.system(size: 8, weight: .black))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            .foregroundStyle(Color.accentColor)
                    }
                    Text("Model term sheet pricing, option pool shuffles, multi-round dilution, and fund return multiples.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                HStack(spacing: 8) {
                    if copiedNotice {
                        Text("Copied to Clipboard!")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(.green)
                            .transition(.opacity)
                    }

                    Button {
                        copyTermSheetSummary()
                    } label: {
                        Label("Copy Term Sheet", systemImage: "doc.on.doc")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button {
                        resetToStandardSeriesA()
                    } label: {
                        Label("Reset", systemImage: "arrow.counterclockwise")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }

            Divider()

            // Round Inputs Grid
            HStack(alignment: .top, spacing: 20) {
                // Left Column: Investment Parameters
                VStack(alignment: .leading, spacing: 14) {
                    Text("Round & Valuation Terms")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)

                    // Target Round Picker
                    Picker("Round", selection: $roundName) {
                        Text("Seed").tag("Seed")
                        Text("Series A").tag("Series A")
                        Text("Series B").tag("Series B")
                        Text("Series C").tag("Series C")
                        Text("Growth").tag("Growth")
                    }
                    .pickerStyle(.segmented)

                    // Check Size
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Our Check Size:")
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
                            Text("Pre-Money Valuation:")
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
                            Text("Unallocated Option Pool:")
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
                    Text("Post-Money & Dilution Mechanics")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)

                    // Key Outputs Card
                    HStack(spacing: 12) {
                        OutputMetricTile(
                            title: "POST-MONEY",
                            value: "$\(String(format: "%.1f", postMoneyMillions))M",
                            subtext: "Pre + Check"
                        )
                        OutputMetricTile(
                            title: "INITIAL OWNERSHIP",
                            value: "\(String(format: "%.1f", initialOwnershipPercent))%",
                            subtext: "At Close"
                        )
                        OutputMetricTile(
                            title: "DILUTED AT EXIT",
                            value: "\(String(format: "%.1f", finalDilutedOwnershipPercent))%",
                            subtext: modelFutureDilution ? "Post-\(String(format: "%.0f", futureDilutionPercent))% Dilution" : "Uncut"
                        )
                    }

                    // Future Dilution Toggle & Slider
                    VStack(alignment: .leading, spacing: 6) {
                        Toggle(isOn: $modelFutureDilution) {
                            Text("Model Subsequent Rounds Dilution")
                                .font(.caption.weight(.medium))
                        }
                        .toggleStyle(.checkbox)

                        if modelFutureDilution {
                            HStack {
                                Text("Cumulative Future Dilution (Series B/C/IPO):")
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
                        Text("Reference Fund Size:")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("$\(fundSizeMillions, specifier: "%.0f")M Fund")
                            .font(.caption2.monospacedDigit().weight(.semibold))
                    }
                }
                .frame(maxWidth: .infinity)
            }

            // Visual Cap Table Structure Bar
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Post-Round Cap Table Breakdown")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("Check + Common + Pool = 100%")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                }

                GeometryReader { geo in
                    HStack(spacing: 2) {
                        // Founders & Common
                        Rectangle()
                            .fill(Color.blue)
                            .frame(width: max(4, geo.size.width * CGFloat(foundersPreMoneyDilutionPercent / 100.0)))
                            .help("Founders & Prior Investors: \(String(format: "%.1f", foundersPreMoneyDilutionPercent))%")

                        // Option Pool
                        Rectangle()
                            .fill(Color.orange)
                            .frame(width: max(4, geo.size.width * CGFloat(optionPoolPercent / 100.0)))
                            .help("Unallocated Option Pool: \(String(format: "%.1f", optionPoolPercent))%")

                        // Our Ownership
                        Rectangle()
                            .fill(Color.green)
                            .frame(width: max(4, geo.size.width * CGFloat(initialOwnershipPercent / 100.0)))
                            .help("Our Fund (\(roundName)): \(String(format: "%.1f", initialOwnershipPercent))%")
                    }
                    .cornerRadius(4)
                }
                .frame(height: 14)

                HStack(spacing: 16) {
                    LegendItem(color: .blue, title: "Founders & Common", value: "\(String(format: "%.1f", foundersPreMoneyDilutionPercent))%")
                    LegendItem(color: .orange, title: "Option Pool", value: "\(String(format: "%.1f", optionPoolPercent))%")
                    LegendItem(color: .green, title: "Our Investment (\(roundName))", value: "\(String(format: "%.1f", initialOwnershipPercent))%")
                }
            }

            // Exit Return & MOIC Matrix Table
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Exit Proceeds & Fund Return Multiples (MOIC)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("Based on \(String(format: "%.1f", finalDilutedOwnershipPercent))% diluted terminal equity")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                }

                // Table Header
                HStack(spacing: 10) {
                    Text("Exit Valuation")
                        .frame(width: 170, alignment: .leading)
                    Text("Diluted Ownership")
                        .frame(width: 130, alignment: .trailing)
                    Text("Gross Proceeds")
                        .frame(width: 130, alignment: .trailing)
                    Text("Net MOIC")
                        .frame(width: 90, alignment: .trailing)
                    Text("Fund Returned")
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .appleGlassTile(cornerRadius: 6)

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
                                    Text("FUND MAKER")
                                        .font(.system(size: 7, weight: .bold))
                                        .padding(.horizontal, 5)
                                        .padding(.vertical, 1.5)
                                        .foregroundStyle(Color.green)
                                        .appleGlassPill(color: .green)
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
    }

    // MARK: - Actions
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
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 16, weight: .bold, design: .monospaced))
                .monospacedDigit()
                .foregroundStyle(Color.accentColor)
            Text(subtext)
                .font(.system(size: 9))
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
