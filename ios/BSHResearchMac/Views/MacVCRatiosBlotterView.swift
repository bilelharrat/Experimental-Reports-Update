//
//  MacVCRatiosBlotterView.swift
//  BSHResearchMac
//
//  Institutional VC Ratios Blotter & Investment Committee Metrics.
//  Computes Burn Multiple, Rule of 40, Net Dollar Retention (NDR), CAC Payback,
//  and Magic Number with Bessemer / a16z / Sequoia percentile benchmarks.
//

import SwiftUI
import AppKit

struct MacVCRatiosBlotterView: View {
    let company: MacCompany

    // Interactive Inputs
    // Inputs start empty: this is a calculator over figures you type from the memo or a founder
    // update. Nothing is fetched or estimated.
    @State private var arr: Double? // $M ARR
    @State private var netNewArr: Double? // $M Net New ARR
    @State private var netBurn: Double? // $M Annual Net Burn
    @State private var arrGrowthRate: Double? // % YoY Growth
    @State private var fcfMargin: Double? // % Free Cash Flow Margin
    @State private var ndr: Double? // % Net Dollar Retention
    @State private var cacPaybackMonths: Double? // Months CAC Payback
    @State private var smSpend: Double? // $M Sales & Marketing Spend

    @State private var copiedToClipboard: Bool = false

    private static let gridColumns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    // Calculated Institutional VC Metrics
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

    private var hasAnyMetric: Bool {
        burnMultiple != nil || ruleOf40 != nil || ndr != nil || cacPaybackMonths != nil || magicNumber != nil
    }

    private var isTopTier: Bool {
        guard let burnMultiple, let ruleOf40 else { return false }
        return burnMultiple < 1.0 && ruleOf40 >= 40
    }

    private var readoutIsPositive: Bool {
        guard let burnMultiple else { return false }
        return burnMultiple <= 1.5
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            MacCardHeader("VC ratios", subtitle: "A calculator over figures you type from the memo or the latest founder update. Nothing is fetched or estimated.", systemImage: "gauge.with.needle") {
                Button {
                    copyRatiosSummary()
                } label: {
                    Label(copiedToClipboard ? "Copied" : "Copy ratios", systemImage: copiedToClipboard ? "checkmark" : "doc.on.doc")
                }
                .controlSize(.small)
                .disabled(!hasAnyMetric)
            }

            // Key Ratios Grid (Top Tier Metrics)
            LazyVGrid(columns: Self.gridColumns, spacing: 12) {
                // 1. Burn Multiple
                RatioMetricCard(
                    title: "Burn multiple",
                    value: burnMultiple.map { String(format: "%.2fx", $0) },
                    badge: burnMultiple.map { burnMultipleBadge($0).text } ?? "",
                    badgeColor: burnMultiple.map { burnMultipleBadge($0).color } ?? .secondary,
                    caption: "Net burn ÷ net new ARR",
                    target: "Under 1.0x is top decile"
                )

                // 2. Rule of 40
                RatioMetricCard(
                    title: "Rule of 40",
                    value: ruleOf40.map { String(format: "%.1f%%", $0) },
                    badge: ruleOf40.map { $0 >= 40 ? "Elite" : "Below 40" } ?? "",
                    badgeColor: (ruleOf40 ?? 0) >= 40 ? .green : .orange,
                    caption: "Growth (\(arrGrowthRate.map { String(format: "%.0f%%", $0) } ?? "—")) + FCF (\(fcfMargin.map { String(format: "%.0f%%", $0) } ?? "—"))",
                    target: "40% or more"
                )

                // 3. Net Dollar Retention (NDR)
                RatioMetricCard(
                    title: "Net retention",
                    value: ndr.map { String(format: "%.0f%%", $0) },
                    badge: ndr.map { $0 >= 130 ? "Best in class" : ($0 >= 115 ? "Strong" : "Churn risk") } ?? "",
                    badgeColor: (ndr ?? 0) >= 130 ? .purple : ((ndr ?? 0) >= 115 ? .green : .red),
                    caption: "Existing-cohort ARR expansion",
                    target: "120% or more for enterprise"
                )

                // 4. CAC Payback
                RatioMetricCard(
                    title: "CAC payback",
                    value: cacPaybackMonths.map { String(format: "%.1f mo", $0) },
                    badge: cacPaybackMonths.map { $0 <= 12 ? "Efficient" : "Slow payback" } ?? "",
                    badgeColor: (cacPaybackMonths ?? 0) <= 12 ? .green : .orange,
                    caption: "Months to recoup CAC",
                    target: "12 months or less"
                )
            }

            // Typed Inputs
            VStack(alignment: .leading, spacing: 12) {
                MacSectionLabel("Inputs", trailing: "figures from the memo or founder update")

                LazyVGrid(columns: Self.gridColumns, spacing: 12) {
                    inputField("Current ARR", unit: "$M", value: $arr)
                    inputField("Net new ARR (TTM)", unit: "$M", value: $netNewArr)
                    inputField("Annual net burn", unit: "$M", value: $netBurn)
                    inputField("S&M spend (TTM)", unit: "$M", value: $smSpend)
                    inputField("ARR growth (YoY)", unit: "%", value: $arrGrowthRate)
                    inputField("FCF margin", unit: "%", value: $fcfMargin)
                    inputField("Net dollar retention", unit: "%", value: $ndr)
                    inputField("CAC payback", unit: "months", value: $cacPaybackMonths)
                }
            }
            .padding(12)
            .appleGlassTile(cornerRadius: 10)

            // Read-out — only once there is something to read
            if let burnMultiple {
            HStack(spacing: 12) {
                Image(systemName: isTopTier ? "checkmark.seal.fill" : (readoutIsPositive ? "checkmark.circle" : "exclamationmark.triangle.fill"))
                    .font(.title3)
                    .foregroundStyle(isTopTier || readoutIsPositive ? Color.green : Color.orange)

                VStack(alignment: .leading, spacing: 2) {
                    Text(verdictTitle(burnMultiple))
                        .font(.caption.weight(.bold))
                    Text(verdictDescription(burnMultiple))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Magic Number Indicator
                if let magicNumber {
                    HStack(spacing: 6) {
                        Text("Magic Number:")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.2fx", magicNumber))
                            .font(.caption.weight(.bold).monospacedDigit())
                            .foregroundStyle(magicNumber >= 1.0 ? Color.green : Color.primary)
                        Text(magicNumber >= 1.0 ? "expand S&M" : "tune efficiency")
                            .font(.dsCaption)
                            .foregroundStyle(magicNumber >= 1.0 ? Color.green : Color.secondary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .appleGlassPill(color: magicNumber >= 1.0 ? .green : .secondary)
                }
            }
            .padding(12)
            .appleGlassTile(cornerRadius: 10, tint: isTopTier || readoutIsPositive ? Color.green : Color.orange)
            } else {
                Text("Enter net burn and net new ARR for the burn multiple; growth and FCF margin for Rule of 40; retention, CAC payback and S&M spend for the rest.")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .appleGlassCard()
    }

    private func inputField(_ label: String, unit: String, value: Binding<Double?>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 4) {
                TextField("—", value: value, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption.monospacedDigit())
                Text(unit)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - Verdict Logic
    private func burnMultipleBadge(_ value: Double) -> (text: String, color: Color) {
        if value < 1.0 {
            return ("Exceptional", .green)
        } else if value <= 1.5 {
            return ("Good", .blue)
        } else if value <= 2.0 {
            return ("Manageable", .orange)
        } else {
            return ("High burn", .red)
        }
    }

    private var missingForVerdict: [String] {
        var missing: [String] = []
        if ruleOf40 == nil { missing.append("Rule of 40") }
        if ndr == nil { missing.append("net retention") }
        return missing
    }

    private func verdictTitle(_ burn: Double) -> String {
        if isTopTier {
            return "Top-tier efficiency profile"
        } else if !missingForVerdict.isEmpty {
            return "Burn multiple only — enter \(missingForVerdict.joined(separator: " and ")) for a full read"
        } else if burn <= 1.5 {
            return "Strong venture profile with sound unit economics"
        } else {
            return "Capital intensive — scrutinize sales and marketing spend"
        }
    }

    private func verdictDescription(_ burn: Double) -> String {
        let retention = ndr.map { String(format: "%.0f%% net retention", $0) } ?? "net retention not entered"
        return "Burn multiple \(String(format: "%.2fx", burn)) with \(retention), against the benchmarks shown on each card."
    }

    private func copyRatiosSummary() {
        func money(_ v: Double?) -> String { v.map { "$" + String(format: "%.1f", $0) + "M" } ?? "not entered" }
        func pct(_ v: Double?) -> String { v.map { String(format: "%.0f%%", $0) } ?? "not entered" }
        let text = """
        --- INSTITUTIONAL VC RATIOS SUMMARY ---
        Company: \(company.name ?? company.id)
        ARR: \(money(arr))
        Net New ARR: \(money(netNewArr))
        Annual Net Burn: \(money(netBurn))
        S&M Spend: \(money(smSpend))
        ARR Growth: \(pct(arrGrowthRate))
        FCF Margin: \(pct(fcfMargin))
        Burn Multiple: \(burnMultiple.map { String(format: "%.2fx", $0) + " (" + burnMultipleBadge($0).text + ")" } ?? "not entered")
        Rule of 40: \(ruleOf40.map { String(format: "%.1f%%", $0) } ?? "not entered")
        Net Dollar Retention (NDR): \(pct(ndr))
        CAC Payback: \(cacPaybackMonths.map { String(format: "%.1f", $0) + " months" } ?? "not entered")
        Magic Number: \(magicNumber.map { String(format: "%.2fx", $0) } ?? "not entered")
        ---------------------------------------
        """
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)

        copiedToClipboard = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copiedToClipboard = false
        }
    }
}

// MARK: - Ratio Metric Card
private struct RatioMetricCard: View {
    let title: String
    let value: String?
    let badge: String
    let badgeColor: Color
    let caption: String
    let target: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                    .font(.dsLabel)
                    .foregroundStyle(.secondary)
                Spacer()
                if value != nil, !badge.isEmpty {
                    MacStatusPill(text: badge, color: badgeColor)
                }
            }

            Text(value ?? "—")
                .font(.dsMetric)
                .foregroundStyle(value == nil ? Color.secondary : Color.primary)

            Text(caption)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Divider()

            HStack {
                Image(systemName: "scope")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Text(target)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .appleGlassTile(cornerRadius: 10)
    }
}
