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
    @State private var arr: Double = 0 // $M ARR
    @State private var netNewArr: Double = 0 // $M Net New ARR
    @State private var netBurn: Double = 0 // $M Annual Net Burn
    @State private var arrGrowthRate: Double = 0 // % YoY Growth
    @State private var fcfMargin: Double = 0 // % Free Cash Flow Margin
    @State private var ndr: Double = 0 // % Net Dollar Retention
    @State private var cacPaybackMonths: Double = 0 // Months CAC Payback
    @State private var smSpend: Double = 0 // $M Sales & Marketing Spend

    @State private var copiedToClipboard: Bool = false

    // Calculated Institutional VC Metrics
    private var burnMultiple: Double {
        guard netNewArr > 0 else { return 0 }
        return netBurn / netNewArr
    }

    private var ruleOf40: Double {
        return arrGrowthRate + fcfMargin
    }

    private var magicNumber: Double {
        guard smSpend > 0 else { return 0 }
        return netNewArr / smSpend
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Header Bar
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Image(systemName: "gauge.with.needle.fill")
                            .foregroundStyle(Color.accentColor)
                        Text("Institutional VC Ratios & Efficiency Blotter")
                            .font(.headline)

                        Text("BESSEMER / a16z / SEQUOIA")
                            .font(.system(size: 8, weight: .black))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            .foregroundStyle(Color.accentColor)
                    }

                    Text("Calculator — enter figures from the memo or the latest founder update. Nothing here is fetched or estimated.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button {
                    copyRatiosSummary()
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: copiedToClipboard ? "checkmark" : "doc.on.doc")
                        Text(copiedToClipboard ? "Copied" : "Copy Diligence Ratios")
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            Divider()

            // Key Ratios Grid (Top Tier Metrics)
            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12)
            ], spacing: 12) {
                // 1. Burn Multiple
                RatioMetricCard(
                    title: "BURN MULTIPLE",
                    value: String(format: "%.2fx", burnMultiple),
                    badge: burnMultipleBadge.text,
                    badgeColor: burnMultipleBadge.color,
                    caption: "Net Burn / Net New ARR",
                    target: "< 1.0x (Top Decile)"
                )

                // 2. Rule of 40
                RatioMetricCard(
                    title: "RULE OF 40",
                    value: String(format: "%.1f%%", ruleOf40),
                    badge: ruleOf40 >= 40 ? "ELITE" : "SUB-40",
                    badgeColor: ruleOf40 >= 40 ? .green : .orange,
                    caption: "Growth (\(Int(arrGrowthRate))%) + FCF (\(Int(fcfMargin))%)",
                    target: "≥ 40.0% Target"
                )

                // 3. Net Dollar Retention (NDR)
                RatioMetricCard(
                    title: "NET RETENTION (NDR)",
                    value: String(format: "%.0f%%", ndr),
                    badge: ndr >= 130 ? "UNIFIED UNICORN" : (ndr >= 115 ? "STRONG" : "CHURN RISK"),
                    badgeColor: ndr >= 130 ? .purple : (ndr >= 115 ? .green : .red),
                    caption: "Existing Cohort ARR Expansion",
                    target: "≥ 120% Enterprise Grade"
                )

                // 4. CAC Payback
                RatioMetricCard(
                    title: "CAC PAYBACK",
                    value: String(format: "%.1f mo", cacPaybackMonths),
                    badge: cacPaybackMonths <= 12 ? "CAPITAL EFFICIENT" : "SLOW PAYBACK",
                    badgeColor: cacPaybackMonths <= 12 ? .green : .orange,
                    caption: "Gross Profit Recoup Months",
                    target: "≤ 12 Months Target"
                )
            }

            // Interactive Assumption Sliders Bar
            VStack(alignment: .leading, spacing: 12) {
                Text("Underwriting Assumptions & Live Inputs")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)

                HStack(spacing: 20) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Current ARR:")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("$\(String(format: "%.1f", arr))M")
                                .font(.caption2.weight(.bold).monospaced())
                        }
                        Slider(value: $arr, in: 1.0...100.0, step: 0.5)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Net New ARR (TTM):")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("$\(String(format: "%.1f", netNewArr))M")
                                .font(.caption2.weight(.bold).monospaced())
                        }
                        Slider(value: $netNewArr, in: 0.5...50.0, step: 0.5)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Annual Net Burn:")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("$\(String(format: "%.1f", netBurn))M")
                                .font(.caption2.weight(.bold).monospaced())
                        }
                        Slider(value: $netBurn, in: 0.5...40.0, step: 0.5)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Net Dollar Retention:")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("\(Int(ndr))%")
                                .font(.caption2.weight(.bold).monospaced())
                        }
                        Slider(value: $ndr, in: 80.0...160.0, step: 1.0)
                    }
                }
            }
            .padding(12)
            .appleGlassTile(cornerRadius: 10)

            // Investment Committee Verdict Callout
            HStack(spacing: 12) {
                Image(systemName: burnMultiple <= 1.0 && ruleOf40 >= 40 ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .font(.title3)
                    .foregroundStyle(burnMultiple <= 1.0 && ruleOf40 >= 40 ? Color.green : Color.orange)

                VStack(alignment: .leading, spacing: 2) {
                    Text(verdictTitle)
                        .font(.caption.weight(.bold))
                    Text(verdictDescription)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Magic Number Indicator
                HStack(spacing: 6) {
                    Text("Magic Number:")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.2fx", magicNumber))
                        .font(.caption.weight(.bold).monospaced())
                        .foregroundStyle(magicNumber >= 1.0 ? Color.green : Color.primary)
                    Text(magicNumber >= 1.0 ? "(Expand S&M)" : "(Tune Efficiency)")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(magicNumber >= 1.0 ? Color.green : Color.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .appleGlassPill(color: magicNumber >= 1.0 ? .green : .secondary)
            }
            .padding(12)
            .appleGlassTile(cornerRadius: 10, tint: burnMultiple <= 1.0 && ruleOf40 >= 40 ? Color.green : Color.orange)
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
    }

    // MARK: - Verdict Logic
    private var burnMultipleBadge: (text: String, color: Color) {
        if burnMultiple < 1.0 {
            return ("EXCEPTIONAL", .green)
        } else if burnMultiple <= 1.5 {
            return ("GOOD", .blue)
        } else if burnMultiple <= 2.0 {
            return ("MANAGEABLE", .orange)
        } else {
            return ("HIGH BURN", .red)
        }
    }

    private var verdictTitle: String {
        if burnMultiple < 1.0 && ruleOf40 >= 40 {
            return "IC VERDICT: TIER-1 INSTITUTIONAL OUTPERFORMER"
        } else if burnMultiple <= 1.5 {
            return "IC VERDICT: STRONG VENTURE PROFILE — SOUND UNIT ECONOMICS"
        } else {
            return "IC VERDICT: CAPITAL INTENSIVE — SCRUTINIZE S&M SPEND"
        }
    }

    private var verdictDescription: String {
        "Burn Multiple of \(String(format: "%.2fx", burnMultiple)) with \(Int(ndr))% NDR places \(company.name ?? company.id) in the top tier of institutional growth benchmarks."
    }

    private func copyRatiosSummary() {
        let text = """
        --- INSTITUTIONAL VC RATIOS SUMMARY ---
        Company: \(company.name ?? company.id)
        ARR: $\(String(format: "%.1f", arr))M
        Net New ARR: $\(String(format: "%.1f", netNewArr))M
        Annual Net Burn: $\(String(format: "%.1f", netBurn))M
        Burn Multiple: \(String(format: "%.2fx", burnMultiple)) (\(burnMultipleBadge.text))
        Rule of 40: \(String(format: "%.1f%%", ruleOf40))
        Net Dollar Retention (NDR): \(Int(ndr))%
        CAC Payback: \(String(format: "%.1f", cacPaybackMonths)) months
        Magic Number: \(String(format: "%.2fx", magicNumber))
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
    let value: String
    let badge: String
    let badgeColor: Color
    let caption: String
    let target: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(badge)
                    .font(.system(size: 8, weight: .black))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .foregroundStyle(badgeColor)
                    .appleGlassPill(color: badgeColor)
            }

            Text(value)
                .font(.system(size: 20, weight: .bold, design: .monospaced))
                .monospacedDigit()

            Text(caption)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Divider()

            HStack {
                Image(systemName: "scope")
                    .font(.system(size: 8))
                    .foregroundStyle(.secondary)
                Text(target)
                    .font(.system(size: 8, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .appleGlassTile(cornerRadius: 10)
    }
}
