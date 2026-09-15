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
    @State private var saving = false
    @State private var saveError: String?
    @State private var loadAttempted = false

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
            MacCardHeader("Deal pipeline", subtitle: "Stage, intro path, last touchpoint and next step — as recorded by the team.", systemImage: "point.3.filled.connected.trianglepath.dotted") {
                if let score = pipeline?.warmthScore {
                    MacStatusPill(text: "Warmth \(score)", color: score >= 80 ? .green : .orange)
                }
                if let lead = pipeline?.dealLead {
                    Label(lead, systemImage: "person.crop.circle")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                }
            }

            // Interactive Pipeline Stages Stepper
            VStack(alignment: .leading, spacing: 6) {
                MacSectionLabel("Stage", trailing: pipeline.map { "\($0.daysInStage) days in \(currentStage)" })

                if pipeline == nil && loadAttempted {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .foregroundStyle(Color.dsWarning)
                        Text("Couldn't load the deal pipeline.")
                            .font(.dsCaption)
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await load() } }
                            .controlSize(.small)
                    }
                } else if pipeline == nil {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading pipeline…").font(.dsCaption).foregroundStyle(.secondary)
                    }
                } else {
                HStack(spacing: 6) {
                    ForEach(Array(currentStages.enumerated()), id: \.offset) { index, stage in
                        let isCurrent = (stage == currentStage)
                        let isPast = stageIndex(stage) < stageIndex(currentStage)

                        Button {
                            Task { await changeStage(to: stage) }
                        } label: {
                            HStack(spacing: 6) {
                                ZStack {
                                    Circle()
                                        .fill(isCurrent ? Color.accentColor : (isPast ? Color.green : Color.secondary.opacity(0.2)))
                                        .frame(width: 16, height: 16)
                                    if isPast {
                                        Image(systemName: "checkmark")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundStyle(.white)
                                    } else {
                                        Text("\(index + 1)")
                                            .font(.system(size: 10, weight: .bold))
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
                        .disabled(!store.canWriteDesk || saving || isCurrent)
                        .help(store.canWriteDesk ? "Move \(company.title) to \(stage)" : "A read-only session cannot change the stage")
                    }
                }
                if let saveError {
                    Label(saveError, systemImage: "exclamationmark.triangle")
                        .font(.dsCaption)
                        .foregroundStyle(Color.dsNegative)
                }
                }
            }

            // Relationship Pathway & CRM Interactions
            HStack(spacing: 14) {
                // Intro Path Card
                VStack(alignment: .leading, spacing: 4) {
                    Label("Intro path", systemImage: "link")
                        .font(.dsLabel)
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
                    Label("Last touchpoint", systemImage: "message")
                        .font(.dsLabel)
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
                    Label("Next step", systemImage: "calendar.badge.clock")
                        .font(.dsLabel)
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
            saveError = nil
            loadAttempted = false
            await load()
        }
    }

    private func load() async {
        await store.fetchDealPipeline(for: company.id)
        guard !Task.isCancelled else { return }
        loadAttempted = true
    }

    private func changeStage(to stage: String) async {
        guard store.canWriteDesk, !saving, stage != currentStage, var optimistic = pipeline else { return }
        let previous = pipeline
        saving = true
        saveError = nil
        optimistic.stage = stage
        optimistic.daysInStage = 0
        store.dealPipelines[company.id] = optimistic
        defer { saving = false }
        do {
            store.dealPipelines[company.id] = try await MacAPIClient.shared.updateDealPipeline(
                companyId: company.id,
                fields: ["stage": stage]
            )
        } catch {
            store.dealPipelines[company.id] = previous
            saveError = "Stage change wasn't saved: \(error.localizedDescription)"
        }
    }

    private func stageIndex(_ stage: String) -> Int {
        currentStages.firstIndex(of: stage) ?? 0
    }
}
