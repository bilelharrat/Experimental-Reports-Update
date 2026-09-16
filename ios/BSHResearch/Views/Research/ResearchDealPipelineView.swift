import SwiftUI

public struct MacDealPipelineView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore
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

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MacCardHeader("Deal pipeline", subtitle: "Stage, intro path, and touchpoints.", systemImage: "point.3.filled.connected.trianglepath.dotted") {
                if let score = pipeline?.warmthScore {
                    MacStatusPill(text: "Warmth \(score)", color: score >= 80 ? .green : .orange)
                }
                if let lead = pipeline?.dealLead {
                    Label(lead, systemImage: "person.crop.circle")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                MacSectionLabel("Stage", trailing: pipeline.map { "\($0.daysInStage) days in \(currentStage)" })

                if pipeline == nil && loadAttempted {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .foregroundStyle(Color.dsWarning)
                        Text("Couldn't load pipeline.")
                            .font(.dsCaption)
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await load() } }
                            .font(.caption2.weight(.medium))
                    }
                } else if pipeline == nil {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading pipeline…").font(.dsCaption).foregroundStyle(.secondary)
                    }
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
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
                                    .appleGlassTile(cornerRadius: 8, tint: isCurrent ? Color.accentColor : (isPast ? Color.green : nil))
                                }
                                .buttonStyle(.plain)
                                .disabled(saving || isCurrent)
                            }
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
            HStack(spacing: 10) {
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
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            saveError = nil
            loadAttempted = false
            await load()
        }
    }

    private func load() async {
        await store.fetchDealPipeline(for: company.id)
        loadAttempted = true
    }

    private func changeStage(to stage: String) async {
        guard !saving, stage != currentStage, var optimistic = pipeline else { return }
        saving = true
        saveError = nil
        optimistic.stage = stage
        optimistic.daysInStage = 0
        store.dealPipelines[company.id] = optimistic
        defer { saving = false }

        await store.updateDealPipeline(
            companyId: company.id,
            stage: stage,
            dealLead: optimistic.dealLead,
            warmthScore: optimistic.warmthScore,
            nextStep: optimistic.nextStep
        )
    }

    private func stageIndex(_ stage: String) -> Int {
        currentStages.firstIndex(of: stage) ?? 0
    }
}
