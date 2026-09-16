import SwiftUI
import UIKit

public struct MacVCRatiosBlotterView: View {
    public let company: MacCompany

    @State private var arr: Double?
    @State private var netNewArr: Double?
    @State private var netBurn: Double?
    @State private var arrGrowthRate: Double?
    @State private var fcfMargin: Double?
    @State private var ndr: Double?
    @State private var cacPaybackMonths: Double?
    @State private var smSpend: Double?

    @State private var copiedToClipboard: Bool = false

    private var burnMultiple: Double? {
        guard let netBurn, let netNewArr, netNewArr > 0 else { return nil }
        return netBurn / netNewArr
    }

    private var ruleOf40: Double? {
        guard let arrGrowthRate, let fcfMargin else { return nil }
        return arrGrowthRate + fcfMargin
    }

    private var magicNumber: Double? {
        guard let netNewArr, let smSpend, smSpend > 0 else { return nil }
        return netNewArr / smSpend
    }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MacCardHeader("VC ratios", subtitle: "Unit economics, efficiency & Rule of 40.", systemImage: "gauge.with.needle") {
                Button {
                    copyRatiosSummary()
                } label: {
                    Label(copiedToClipboard ? "Copied" : "Copy", systemImage: copiedToClipboard ? "checkmark" : "doc.on.doc")
                }
                .font(.caption2.weight(.medium))
            }

            // Key Ratios Grid
            let columns = [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)]
            LazyVGrid(columns: columns, spacing: 10) {
                ratioCard(
                    title: "Burn multiple",
                    value: burnMultiple.map { String(format: "%.2fx", $0) },
                    badge: burnMultiple.map { burnMultipleBadge($0).text } ?? "",
                    color: burnMultiple.map { burnMultipleBadge($0).color } ?? .secondary,
                    target: "< 1.0x top decile"
                )
                ratioCard(
                    title: "Rule of 40",
                    value: ruleOf40.map { String(format: "%.1f%%", $0) },
                    badge: ruleOf40.map { $0 >= 40 ? "Elite" : "Below 40" } ?? "",
                    color: (ruleOf40 ?? 0) >= 40 ? .green : .orange,
                    target: "40%+ benchmark"
                )
                ratioCard(
                    title: "Net retention (NDR)",
                    value: ndr.map { String(format: "%.0f%%", $0) },
                    badge: ndr.map { $0 >= 130 ? "Best in class" : ($0 >= 115 ? "Strong" : "Churn risk") } ?? "",
                    color: (ndr ?? 0) >= 130 ? .purple : ((ndr ?? 0) >= 115 ? .green : .red),
                    target: "120%+ target"
                )
                ratioCard(
                    title: "CAC payback",
                    value: cacPaybackMonths.map { String(format: "%.1f mo", $0) },
                    badge: cacPaybackMonths.map { $0 <= 12 ? "Efficient" : "Slow" } ?? "",
                    color: (cacPaybackMonths ?? 0) <= 12 ? .green : .orange,
                    target: "≤ 12 months"
                )
            }

            // Interactive Input Fields
            VStack(alignment: .leading, spacing: 10) {
                MacSectionLabel("Inputs", trailing: "Type to calculate")
                LazyVGrid(columns: columns, spacing: 8) {
                    inputCell("Current ARR", unit: "$M", value: $arr)
                    inputCell("Net new ARR (TTM)", unit: "$M", value: $netNewArr)
                    inputCell("Annual net burn", unit: "$M", value: $netBurn)
                    inputCell("S&M spend (TTM)", unit: "$M", value: $smSpend)
                    inputCell("ARR growth (YoY)", unit: "%", value: $arrGrowthRate)
                    inputCell("FCF margin", unit: "%", value: $fcfMargin)
                    inputCell("Net retention", unit: "%", value: $ndr)
                    inputCell("CAC payback", unit: "mo", value: $cacPaybackMonths)
                }
            }
            .padding(10)
            .appleGlassTile(cornerRadius: 10)

            if let magic = magicNumber {
                HStack {
                    Text("Magic Number:")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.2fx", magic))
                        .font(.caption.monospacedDigit().weight(.bold))
                        .foregroundStyle(magic >= 1.0 ? Color.green : Color.primary)
                    Spacer()
                    MacStatusPill(text: magic >= 1.0 ? "Efficient S&M" : "Low efficiency", color: magic >= 1.0 ? .green : .orange)
                }
                .padding(8)
                .appleGlassTile(cornerRadius: 8)
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
    }

    private func ratioCard(title: String, value: String?, badge: String, color: Color, target: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.dsLabel).foregroundStyle(.secondary)
                Spacer()
                if value != nil, !badge.isEmpty {
                    MacStatusPill(text: badge, color: color)
                }
            }
            Text(value ?? "—").font(.dsMetricSmall).foregroundStyle(value == nil ? .secondary : .primary)
            Text(target).font(.caption2).foregroundStyle(.tertiary)
        }
        .padding(10)
        .appleGlassTile(cornerRadius: 10)
    }

    private func inputCell(_ label: String, unit: String, value: Binding<Double?>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            HStack(spacing: 4) {
                TextField("—", value: value, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption.monospacedDigit())
                    .keyboardType(.decimalPad)
                Text(unit).font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    private func burnMultipleBadge(_ value: Double) -> (text: String, color: Color) {
        if value < 1.0 { return ("Exceptional", .green) }
        if value <= 1.5 { return ("Good", .blue) }
        if value <= 2.0 { return ("Manageable", .orange) }
        return ("High burn", .red)
    }

    private func copyRatiosSummary() {
        let text = """
        VC RATIOS — \(company.name ?? company.id)
        Burn Multiple: \(burnMultiple.map { String(format: "%.2fx", $0) } ?? "—")
        Rule of 40: \(ruleOf40.map { String(format: "%.1f%%", $0) } ?? "—")
        NDR: \(ndr.map { String(format: "%.0f%%", $0) } ?? "—")
        CAC Payback: \(cacPaybackMonths.map { String(format: "%.1f mo", $0) } ?? "—")
        """
        UIPasteboard.general.string = text
        copiedToClipboard = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copiedToClipboard = false
        }
    }
}
