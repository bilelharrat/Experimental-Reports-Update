//
//  MacDealPipelineView.swift
//  BSHResearchMac
//
//  Affinity-grade Deal Pipeline & Relationship Warmth Tracker.
//  Tracks institutional pipeline stages (Sourced -> Intro -> Tech DD -> Term Sheet -> Portfolio),
//  warm introduction pathways, and relationship warmth index.
//

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

struct MacDealPipelineView: View {
    let company: MacCompany
    @EnvironmentObject private var store: MacAppStore
    @State private var saving = false
    @State private var saveError: String?
    @State private var loadAttempted = false
    @State private var editing: PipelineField?
    @State private var draft = ""
    @State private var hasDue = false
    @State private var draftDue = Date()
    @State private var fieldSaving = false

    enum PipelineField: String, CaseIterable, Identifiable {
        case introPath = "intro_path"
        case lastTouchpoint = "last_touchpoint"
        case nextStep = "next_step"
        var id: String { rawValue }
        var title: String {
            switch self {
            case .introPath: return "Intro path"
            case .lastTouchpoint: return "Last touchpoint"
            case .nextStep: return "Next step"
            }
        }
        var icon: String {
            switch self {
            case .introPath: return "link"
            case .lastTouchpoint: return "message"
            case .nextStep: return "calendar.badge.clock"
            }
        }
        var empty: String { self == .nextStep ? "Not set" : "Not recorded" }
    }

    /// Calendar days in the Mac's own time zone, as the server stores them.
    private static let dayFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

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

            // Intro path · Last touchpoint · Next step — click any to edit.
            // They read "Not recorded" on every company while the card only
            // displayed them; the server has accepted edits all along.
            HStack(alignment: .top, spacing: 14) {
                ForEach(PipelineField.allCases) { field in
                    tile(field)
                }
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

    private func value(_ field: PipelineField) -> String? {
        switch field {
        case .introPath: return pipeline?.introPath
        case .lastTouchpoint: return pipeline?.lastTouchpoint
        case .nextStep: return pipeline?.nextStep
        }
    }

    @ViewBuilder
    private func tile(_ field: PipelineField) -> some View {
        let isNext = field == .nextStep
        let overdue = isNext && pipeline?.nextStepOverdue == true
        let tint: Color? = isNext ? (overdue ? Color.dsNegative : Color.accentColor) : nil
        VStack(alignment: .leading, spacing: 6) {
            Label(field.title, systemImage: field.icon)
                .font(.dsLabel)
                .foregroundStyle(tint ?? Color.secondary)

            if editing == field {
                TextField(field.title, text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...4)
                    .font(.caption)
                    .disabled(fieldSaving)
                    .onSubmit { Task { await saveEdit() } }
                    #if os(macOS)
                    .onExitCommand { editing = nil }
                    #endif
                if isNext {
                    HStack(spacing: 6) {
                        Toggle("Due", isOn: $hasDue).toggleStyle(.checkbox).font(.caption)
                        if hasDue {
                            DatePicker("", selection: $draftDue, displayedComponents: .date)
                                .labelsHidden()
                                .datePickerStyle(.field)
                                .controlSize(.small)
                        }
                    }
                }
                HStack(spacing: 6) {
                    Button("Save") { Task { await saveEdit() } }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .keyboardShortcut(.defaultAction)
                    Button("Cancel") { editing = nil }
                        .controlSize(.small)
                    if fieldSaving { ProgressView().controlSize(.mini) }
                }
                .disabled(fieldSaving)
            } else {
                Button {
                    startEdit(field)
                } label: {
                    Text(value(field) ?? field.empty)
                        .font(field == .introPath ? .caption.weight(.semibold) : (isNext ? .caption.weight(.medium) : .caption))
                        .foregroundStyle(tint ?? (value(field) == nil ? Color.secondary : Color.primary))
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!store.canWriteDesk || pipeline == nil)
                .help(store.canWriteDesk ? "Click to edit" : "A read-only session cannot edit the pipeline")

                if isNext, pipeline?.nextStep != nil, let due = pipeline?.nextStepDue {
                    Text(overdue ? "Overdue · was due \(due)" : "Due \(due)")
                        .font(.caption2.monospacedDigit().weight(overdue ? .bold : .regular))
                        .foregroundStyle(tint ?? .secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .appleGlassTile(cornerRadius: 10, tint: tint)
    }

    private func startEdit(_ field: PipelineField) {
        guard store.canWriteDesk, pipeline != nil, !fieldSaving else { return }
        saveError = nil
        draft = value(field) ?? ""
        if field == .nextStep, let due = pipeline?.nextStepDue, let date = Self.dayFormat.date(from: due) {
            hasDue = true
            draftDue = date
        } else {
            hasDue = false
            draftDue = Date()
        }
        editing = field
    }

    private func saveEdit() async {
        guard let field = editing, !fieldSaving else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        var fields: [String: Any] = [field.rawValue: text.isEmpty ? NSNull() : text]
        if field == .nextStep {
            fields["next_step_due"] = hasDue ? Self.dayFormat.string(from: draftDue) : NSNull()
        }
        fieldSaving = true
        defer { fieldSaving = false }
        do {
            store.dealPipelines[company.id] = try await MacAPIClient.shared.updateDealPipeline(
                companyId: company.id,
                fields: fields
            )
            editing = nil
        } catch {
            saveError = "Not saved: \(error.localizedDescription)"
        }
    }
}
