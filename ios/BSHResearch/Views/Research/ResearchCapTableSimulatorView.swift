import SwiftUI
import UIKit

public struct MacCapTableSimulatorView: View {
    public let company: MacCompany

    @State private var roundName: String = "Series A"
    @State private var checkSizeMillions: Double = 15.0
    @State private var preMoneyMillions: Double = 60.0
    @State private var optionPoolPercent: Double = 10.0
    @State private var modelFutureDilution: Bool = true
    @State private var futureDilutionPercent: Double = 22.0
    @State private var fundSizeMillions: Double = 400.0
    @State private var copiedNotice: Bool = false
    @State private var saveState: String?
    @State private var savedModelLoaded: Bool = false
    @State private var savedModelFailed: Bool = false
    @EnvironmentObject private var store: ResearchDeskStore

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

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            MacCardHeader("Cap table & waterfall", subtitle: "Round check, pre-money, option pool & dilution.", systemImage: "chart.pie") {
                if !savedModelLoaded {
                    ProgressView().controlSize(.small)
                } else if let saveState {
                    Text(saveState).font(.dsCaption).foregroundStyle(.secondary)
                }
                if copiedNotice {
                    Text("Copied").font(.dsCaption).foregroundStyle(.green)
                }
                Button {
                    let inputs = MacCapModelInputs(
                        preMoneyMusd: preMoneyMillions,
                        newMoneyMusd: checkSizeMillions,
                        ourCheckMusd: checkSizeMillions,
                        optionPoolPctPost: optionPoolPercent,
                        liquidationPreferenceX: 1.0,
                        participating: false,
                        exitValuesMusd: scenarios.map(\.exitValuationMillions),
                        notes: roundName
                    )
                    saveState = "Saving…"
                    Task {
                        await store.saveCapModel(for: company.id, inputs: inputs)
                        saveState = "Saved"
                    }
                } label: {
                    Label("Save", systemImage: "tray.and.arrow.down")
                }
                .font(.caption2.weight(.medium))

                Button {
                    copyTermSheetSummary()
                } label: {
                    Image(systemName: "doc.on.doc")
                }
                .font(.caption)
                .buttonStyle(.plain)
            }

            // Inputs
            VStack(spacing: 12) {
                // Round Picker
                Picker("Round", selection: $roundName) {
                    Text("Seed").tag("Seed")
                    Text("Series A").tag("Series A")
                    Text("Series B").tag("Series B")
                    Text("Series C").tag("Series C")
                    Text("Growth").tag("Growth")
                }
                .pickerStyle(.segmented)

                // Sliders
                sliderRow("Our check", value: $checkSizeMillions, range: 1.0...80.0, step: 0.5, format: "$%.1fM")
                sliderRow("Pre-money", value: $preMoneyMillions, range: 5.0...400.0, step: 2.5, format: "$%.1fM")
                sliderRow("Option pool", value: $optionPoolPercent, range: 0.0...25.0, step: 1.0, format: "%.1f%%")

                // Metrics
                HStack(spacing: 8) {
                    MacStatTile(label: "Post-money", value: "$\(String(format: "%.1f", postMoneyMillions))M", compact: true)
                    MacStatTile(label: "Ownership close", value: "\(String(format: "%.1f", initialOwnershipPercent))%", compact: true)
                    MacStatTile(label: "Ownership exit", value: "\(String(format: "%.1f", finalDilutedOwnershipPercent))%", compact: true)
                }

                // Dilution toggle
                Toggle("Model later-round dilution (\(String(format: "%.0f", futureDilutionPercent))%)", isOn: $modelFutureDilution)
                    .font(.caption)
                if modelFutureDilution {
                    Slider(value: $futureDilutionPercent, in: 5.0...50.0, step: 1.0)
                }
            }

            // Ownership Breakdown Bar
            VStack(alignment: .leading, spacing: 6) {
                MacSectionLabel("Post-round ownership")
                GeometryReader { geo in
                    let founders = foundersPreMoneyDilutionPercent
                    let pool = max(0, optionPoolPercent)
                    let ours = max(0, initialOwnershipPercent)
                    let total = max(0.0001, founders + pool + ours)
                    let avail = geo.size.width
                    HStack(spacing: 2) {
                        Rectangle().fill(Color.blue).frame(width: avail * CGFloat(founders / total))
                        Rectangle().fill(Color.orange).frame(width: avail * CGFloat(pool / total))
                        Rectangle().fill(Color.green).frame(width: avail * CGFloat(ours / total))
                    }
                    .cornerRadius(4)
                }
                .frame(height: 12)

                HStack(spacing: 12) {
                    legendItem(color: .blue, title: "Founders", value: String(format: "%.1f%%", foundersPreMoneyDilutionPercent))
                    legendItem(color: .orange, title: "Pool", value: String(format: "%.1f%%", optionPoolPercent))
                    legendItem(color: .green, title: "Our stake", value: String(format: "%.1f%%", initialOwnershipPercent))
                }
            }

            // Exit Waterfall
            VStack(alignment: .leading, spacing: 8) {
                MacSectionLabel("Exit proceeds & MOIC", trailing: "\(String(format: "%.1f", finalDilutedOwnershipPercent))% stake")

                ScrollView(.horizontal, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(scenarios) { sc in
                            let proceeds = (sc.exitValuationMillions * (finalDilutedOwnershipPercent / 100.0))
                            let moic = checkSizeMillions > 0 ? proceeds / checkSizeMillions : 0.0
                            let fundReturnPct = fundSizeMillions > 0 ? (proceeds / fundSizeMillions) * 100.0 : 0.0
                            let isFundReturner = fundReturnPct >= 100.0

                            HStack(spacing: 12) {
                                Text(sc.label)
                                    .font(.caption.weight(.medium))
                                    .frame(width: 140, alignment: .leading)
                                Text("$\(proceeds, specifier: "%.1f")M")
                                    .font(.caption.monospacedDigit().weight(.bold))
                                    .frame(width: 80, alignment: .trailing)
                                    .foregroundStyle(moic >= 10.0 ? Color.green : Color.primary)
                                Text("\(moic, specifier: "%.1f")x")
                                    .font(.caption.monospacedDigit().weight(.bold))
                                    .frame(width: 55, alignment: .trailing)
                                    .foregroundStyle(moic >= 10.0 ? Color.green : (moic >= 3.0 ? Color.accentColor : Color.primary))
                                if isFundReturner {
                                    MacStatusPill(text: "Returns fund", color: .green)
                                }
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(isFundReturner ? Color.green.opacity(0.06) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
                        }
                    }
                }
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            saveState = nil
            copiedNotice = false
            await loadSaved()
        }
    }

    private func sliderRow(_ label: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double, format: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.caption)
                Spacer()
                Text(String(format: format, value.wrappedValue)).font(.caption.monospacedDigit().weight(.semibold))
            }
            Slider(value: value, in: range, step: step)
        }
    }

    private func legendItem(color: Color, title: String, value: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(title).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.caption2.monospacedDigit().weight(.semibold))
        }
    }

    private func loadSaved() async {
        savedModelLoaded = false
        await store.fetchCapModel(for: company.id)
        if let model = store.capModelByCompany[company.id] {
            preMoneyMillions = model.inputs.preMoneyMusd ?? 60.0
            checkSizeMillions = model.inputs.ourCheckMusd ?? model.inputs.newMoneyMusd ?? 15.0
            optionPoolPercent = model.inputs.optionPoolPctPost ?? 10.0
            if !model.inputs.notes.isEmpty { roundName = model.inputs.notes }
        }
        savedModelLoaded = true
    }

    private func copyTermSheetSummary() {
        let summary = """
        TERM SHEET CAP TABLE — \(company.name ?? company.id)
        Round: \(roundName)
        Check: $\(String(format: "%.1f", checkSizeMillions))M
        Pre-Money: $\(String(format: "%.1f", preMoneyMillions))M
        Post-Money: $\(String(format: "%.1f", postMoneyMillions))M
        Initial Ownership: \(String(format: "%.1f", initialOwnershipPercent))%
        Option Pool: \(String(format: "%.1f", optionPoolPercent))%
        Diluted Ownership at Exit: \(String(format: "%.1f", finalDilutedOwnershipPercent))%
        """
        UIPasteboard.general.string = summary
        copiedNotice = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copiedNotice = false
        }
    }
}
