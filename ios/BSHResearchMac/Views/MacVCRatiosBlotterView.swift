//
//  MacVCRatiosBlotterView.swift
//  BSHResearchMac
//
//  Institutional VC Ratios Blotter & Investment Committee Metrics.
//  Computes Burn Multiple, Rule of 40, Net Dollar Retention (NDR), CAC Payback,
//  and Magic Number with Bessemer / a16z / Sequoia percentile benchmarks.
//

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif
#if canImport(UIKit)
import UIKit
#endif

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
                    .font(.ui(.title3))
                    .foregroundStyle(isTopTier || readoutIsPositive ? Color.green : Color.orange)

                VStack(alignment: .leading, spacing: 2) {
                    Text(verdictTitle(burnMultiple))
                        .font(.ui(.caption).weight(.bold))
                    Text(verdictDescription(burnMultiple))
                        .font(.ui(.caption2))
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Magic Number Indicator
                if let magicNumber {
                    HStack(spacing: 6) {
                        Text("Magic Number:")
                            .font(.ui(.caption2))
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.2fx", magicNumber))
                            .font(.ui(.caption).weight(.bold).monospacedDigit())
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
                .font(.ui(.caption2))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 4) {
                TextField("—", value: value, format: .number)
                    .textFieldStyle(.dsField)
                    .font(.ui(.caption).monospacedDigit())
                Text(unit)
                    .font(.ui(.caption2))
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
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        #else
        UIPasteboard.general.string = text
        #endif

        copiedToClipboard = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copiedToClipboard = false
        }
    }
}

// MARK: - Bureau

/// VCRatiosCard.vue on the Research Desk: the four ratios on tiles, the typed inputs on a
/// tile, and the read-out once there is a burn multiple to read.
extension MacVCRatiosBlotterView {
    private var bureauBody: some View {
        let ink = MacBureauDeskInk(colorScheme)
        return VStack(alignment: .leading, spacing: 18) {
            MacBureauDeskCardHeader(
                icon: "gauge",
                title: "VC ratios",
                subtitle: "A calculator over figures you type from the memo or the latest founder update. Nothing is fetched or estimated."
            ) {
                Button {
                    copyRatiosSummary()
                } label: {
                    MacBureauDeskButtonLabel(title: copiedToClipboard ? "Copied" : "Copy ratios", icon: copiedToClipboard ? "check" : "copy", iconSize: 12, size: .small)
                }
                .buttonStyle(MacBureauDeskButtonStyle(kind: .bordered, size: .small))
                .disabled(!hasAnyMetric)
                .fixedSize()
            }

            MacBureauDeskGrid(columns: 4, spacing: 12) {
                bureauTile(
                    "Burn multiple",
                    value: burnMultiple.map { String(format: "%.2fx", $0) },
                    badge: burnMultiple.map { value in
                        value < 1.0 ? ("Exceptional", ink.green) : value <= 1.5 ? ("Good", ink.blue) : value <= 2.0 ? ("Manageable", ink.orange) : ("High burn", ink.red)
                    },
                    caption: "Net burn ÷ net new ARR",
                    target: "Under 1.0x is top decile",
                    ink: ink
                )
                bureauTile(
                    "Rule of 40",
                    value: ruleOf40.map { String(format: "%.1f%%", $0) },
                    badge: ruleOf40.map { $0 >= 40 ? ("Elite", ink.green) : ("Below 40", ink.orange) },
                    caption: "Growth (\(arrGrowthRate.map { String(format: "%.0f%%", $0) } ?? "—")) + FCF (\(fcfMargin.map { String(format: "%.0f%%", $0) } ?? "—"))",
                    target: "40% or more",
                    ink: ink
                )
                bureauTile(
                    "Net retention",
                    value: ndr.map { String(format: "%.0f%%", $0) },
                    badge: ndr.map { $0 >= 130 ? ("Best in class", ink.purple) : $0 >= 115 ? ("Strong", ink.green) : ("Churn risk", ink.red) },
                    caption: "Existing-cohort ARR expansion",
                    target: "120% or more for enterprise",
                    ink: ink
                )
                bureauTile(
                    "CAC payback",
                    value: cacPaybackMonths.map { String(format: "%.1f mo", $0) },
                    badge: cacPaybackMonths.map { $0 <= 12 ? ("Efficient", ink.green) : ("Slow payback", ink.orange) },
                    caption: "Months to recoup CAC",
                    target: "12 months or less",
                    ink: ink
                )
            }

            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 0) {
                    MacBureauDeskCaption(text: "Inputs", size: 11, weight: .medium, lineHeight: 13.75, color: ink.secondary)
                    Spacer(minLength: 0)
                    MacBureauDeskCaption(text: "figures from the memo or founder update", size: 11, lineHeight: 13.75, mono: true, color: ink.tertiary)
                }
                MacBureauDeskGrid(columns: 4, spacing: 12) {
                    bureauField("Current ARR", unit: "$M", value: $arr, ink: ink)
                    bureauField("Net new ARR (TTM)", unit: "$M", value: $netNewArr, ink: ink)
                    bureauField("Annual net burn", unit: "$M", value: $netBurn, ink: ink)
                    bureauField("S&M spend (TTM)", unit: "$M", value: $smSpend, ink: ink)
                    bureauField("ARR growth (YoY)", unit: "%", value: $arrGrowthRate, ink: ink)
                    bureauField("FCF margin", unit: "%", value: $fcfMargin, ink: ink)
                    bureauField("Net dollar retention", unit: "%", value: $ndr, ink: ink)
                    bureauField("CAC payback", unit: "months", value: $cacPaybackMonths, ink: ink)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)

            if let burnMultiple {
                bureauReadout(burnMultiple, ink: ink)
            } else {
                MacBureauWebParagraph(
                    text: "Enter net burn and net new ARR for the burn multiple; growth and FCF margin for Rule of 40; retention, CAC payback and S&M spend for the rest.",
                    size: 11,
                    lineHeight: 13.75
                )
                .foregroundStyle(ink.secondary)
            }
        }
        .bureauDeskCard(padding: 16)
    }

    private func bureauTile(
        _ title: String,
        value: String?,
        badge: (String, Color)?,
        caption: String,
        target: String,
        ink: MacBureauDeskInk
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(title)
                    .font(BSHType.bureauSans(11, weight: .medium))
                    .foregroundStyle(ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .bureauDeskLine(13.75, 11)
                Spacer(minLength: 0)
                if value != nil, let badge {
                    MacBureauDeskPill(text: badge.0, tint: badge.1)
                }
            }
            .frame(height: 13.75)
            Text(value ?? "—")
                .font(BSHType.bureauSans(20, weight: .semibold).monospacedDigit())
                .foregroundStyle(value == nil ? ink.secondary : ink.label)
                .lineLimit(1)
                .bureauDeskLine(23, 20)
            Text(caption)
                .font(BSHType.bureauSans(10))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(12.5, 10)
            MacBureauGridRule(color: ink.hairline)
            HStack(spacing: 6) {
                MacBureauDeskIcon("crosshair", size: 10)
                    .foregroundStyle(ink.secondary)
                MacBureauDeskCaption(text: target, color: ink.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: ink.tile)
    }

    /// A number field: 13pt figures on the card colour, ruled like a button, the unit after it.
    private func bureauField(_ label: String, unit: String, value: Binding<Double?>, ink: MacBureauDeskInk) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(BSHType.bureauSans(10))
                .foregroundStyle(ink.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .bureauDeskLine(12.5, 10)
            HStack(spacing: 4) {
                TextField("", value: value, format: .number, prompt: Text("—").foregroundStyle(ink.tertiary))
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(13).monospacedDigit())
                    .foregroundStyle(ink.label)
                    .padding(.horizontal, 6)
                    .frame(height: 25.5)
                    .frame(maxWidth: .infinity)
                    .bureauBox(RoundedRectangle(cornerRadius: 6, style: .circular), fill: ink.card, stroke: ink.label(0.2))
                MacBureauDeskCaption(text: unit, color: ink.tertiary)
            }
        }
    }

    private func bureauReadout(_ burn: Double, ink: MacBureauDeskInk) -> some View {
        let good = isTopTier || readoutIsPositive
        let tint = good ? ink.green : ink.orange
        return HStack(spacing: 12) {
            MacBureauDeskIcon(isTopTier ? "badge-check" : (readoutIsPositive ? "circle-check" : "triangle-alert"), size: 17)
                .foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 2) {
                MacBureauWebParagraph(text: verdictTitle(burn), size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.label)
                MacBureauWebParagraph(text: verdictDescription(burn), size: 10, lineHeight: 12.5)
                    .foregroundStyle(ink.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let magicNumber {
                HStack(spacing: 6) {
                    MacBureauDeskCaption(text: "Magic Number:", color: ink.secondary)
                    MacBureauDeskCaption(text: String(format: "%.2fx", magicNumber), mono: true, color: magicNumber >= 1 ? ink.green : ink.label)
                    MacBureauDeskCaption(text: magicNumber >= 1 ? "expand S&M" : "tune efficiency", size: 11, lineHeight: 13.75, color: magicNumber >= 1 ? ink.green : ink.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .bureauBox(Capsule(), fill: (magicNumber >= 1 ? ink.green : ink.secondary).opacity(0.14))
                .fixedSize()
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bureauBox(RoundedRectangle(cornerRadius: 10, style: .circular), fill: tint.opacity(0.10))
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
                .font(.ui(.caption2))
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Divider()

            HStack {
                Image(systemName: "scope")
                    .font(.ui(size: 10))
                    .foregroundStyle(.secondary)
                Text(target)
                    .font(.ui(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .appleGlassTile(cornerRadius: 10)
    }
}
