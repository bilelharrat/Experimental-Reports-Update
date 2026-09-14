//
//  MacDealPipelineView.swift
//  BSHResearchMac
//
//  Affinity-grade Deal Pipeline & Relationship Warmth Tracker.
//  Tracks institutional pipeline stages (Sourced -> Intro -> Tech DD -> Term Sheet -> Portfolio),
//  warm introduction pathways, and relationship warmth index.
//

import SwiftUI
import AppKit

struct MacDealPipelineView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore

    private var pipeline: MacDealPipeline? {
        store.dealPipelines[company.id]
    }

    private let defaultStages = [
        "Sourced",
        "Partner Intro",
        "Technical Diligence",
        "Term Sheet / IC",
        "Portfolio"
    ]

    private var currentStage: String {
        pipeline?.stage ?? "Sourced"
    }

    private var currentStages: [String] {
        pipeline?.stages ?? defaultStages
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header Bar
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Image(systemName: "point.3.filled.connected.trianglepath.dotted")
                            .foregroundStyle(Color.accentColor)
                        Text("Deal Pipeline & Relationship Warmth")
                            .font(.headline)

                        Text("AFFINITY CRM GRADE")
                            .font(.system(size: 8, weight: .black))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                            .foregroundStyle(Color.accentColor)

                        // Warmth Score Badge
                        if let score = pipeline?.warmthScore {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(score >= 80 ? Color.green : Color.orange)
                                    .frame(width: 6, height: 6)
                                Text("Warmth: \(score)/100")
                                    .font(.system(size: 9, weight: .bold))
                                    .monospacedDigit()
                            }
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .foregroundStyle(score >= 80 ? Color.green : Color.orange)
                            .appleGlassPill(color: score >= 80 ? .green : .orange)
                        }
                    }

                    Text("Active pipeline progression, diligence milestone tracking, and relationship pathway.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Deal Lead Pill
                if let lead = pipeline?.dealLead {
                    HStack(spacing: 5) {
                        Image(systemName: "person.crop.circle.badge.checkmark")
                            .font(.caption)
                        Text(lead)
                            .font(.caption.weight(.medium))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                }
            }

            Divider()

            // Interactive Pipeline Stages Stepper
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Pipeline Stage")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    if let days = pipeline?.daysInStage {
                        Text("\(days) days in \(currentStage)")
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 6) {
                    ForEach(Array(currentStages.enumerated()), id: \.offset) { index, stage in
                        let isCurrent = (stage == currentStage)
                        let isPast = stageIndex(stage) < stageIndex(currentStage)

                        Button {
                            Task {
                                await store.updateDealStage(companyId: company.id, newStage: stage)
                            }
                        } label: {
                            HStack(spacing: 6) {
                                ZStack {
                                    Circle()
                                        .fill(isCurrent ? Color.accentColor : (isPast ? Color.green : Color.secondary.opacity(0.2)))
                                        .frame(width: 16, height: 16)
                                    if isPast {
                                        Image(systemName: "checkmark")
                                            .font(.system(size: 8, weight: .bold))
                                            .foregroundStyle(.white)
                                    } else {
                                        Text("\(index + 1)")
                                            .font(.system(size: 9, weight: .bold))
                                            .foregroundStyle(isCurrent ? Color.white : Color.secondary)
                                    }
                                }

                                Text(stage)
                                    .font(.system(size: 11, weight: isCurrent ? .bold : .medium))
                                    .foregroundStyle(isCurrent ? Color.accentColor : (isPast ? Color.primary : Color.secondary))
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .frame(maxWidth: .infinity)
                            .appleGlassTile(cornerRadius: 8, tint: isCurrent ? Color.accentColor : (isPast ? Color.green : nil))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Relationship Pathway & CRM Interactions
            HStack(spacing: 14) {
                // Intro Path Card
                VStack(alignment: .leading, spacing: 4) {
                    Label("Sourced / Warm Intro Pathway", systemImage: "link")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)

                    Text(pipeline?.introPath ?? "Not recorded")
                        .font(.caption.weight(.semibold))
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .appleGlassTile(cornerRadius: 10)

                // Last Touchpoint
                VStack(alignment: .leading, spacing: 4) {
                    Label("Last Touchpoint", systemImage: "message.fill")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)

                    Text(pipeline?.lastTouchpoint ?? "Not recorded")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .appleGlassTile(cornerRadius: 10)

                // Next Step
                VStack(alignment: .leading, spacing: 4) {
                    Label("Next Action", systemImage: "calendar.badge.clock")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Color.accentColor)

                    Text(pipeline?.nextStep ?? "Not set")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Color.accentColor)
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .appleGlassTile(cornerRadius: 10, tint: Color.accentColor)
            }
        }
        .padding(16)
        .appleGlassCard(cornerRadius: 16)
        .task(id: company.id) {
            await store.fetchDealPipeline(for: company.id)
        }
    }

    private func stageIndex(_ stage: String) -> Int {
        currentStages.firstIndex(of: stage) ?? 0
    }
}
