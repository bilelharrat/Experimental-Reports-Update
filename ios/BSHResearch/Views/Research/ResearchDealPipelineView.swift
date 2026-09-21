import SwiftUI

public struct MacDealPipelineView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore
    @State private var saving = false
    @State private var saveError: String?
    @State private var loadAttempted = false
    @State private var editing: PipelineField?

    public enum PipelineField: String, CaseIterable, Identifiable {
        case introPath = "intro_path"
        case lastTouchpoint = "last_touchpoint"
        case nextStep = "next_step"
        public var id: String { rawValue }
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

            // Intro path · Last touchpoint · Next step — tap any to edit. They
            // read "Not recorded" on every company while the card only showed
            // them; the server has accepted edits all along.
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(PipelineField.allCases) { tile($0) }
                }
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(PipelineField.allCases) { tile($0) }
                }
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
        .task(id: company.id) {
            saveError = nil
            loadAttempted = false
            await load()
        }
        .sheet(item: $editing) { field in
            PipelineFieldEditor(
                field: field,
                initialText: value(field) ?? "",
                initialDue: field == .nextStep ? pipeline?.nextStepDue : nil
            ) { text, due in
                var fields: [String: String?] = [field.rawValue: text.isEmpty ? nil : text]
                if field == .nextStep { fields["next_step_due"] = due }
                return await store.updateDealFields(companyId: company.id, fields: fields)
            }
            .presentationDetents([.medium])
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

    private func value(_ field: PipelineField) -> String? {
        switch field {
        case .introPath: return pipeline?.introPath
        case .lastTouchpoint: return pipeline?.lastTouchpoint
        case .nextStep: return pipeline?.nextStep
        }
    }

    private func tile(_ field: PipelineField) -> some View {
        let isNext = field == .nextStep
        let overdue = isNext && pipeline?.nextStepOverdue == true
        let tint: Color? = isNext ? (overdue ? Color.dsNegative : Color.accentColor) : nil
        return Button {
            if pipeline != nil { editing = field }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Label(field.title, systemImage: field.icon)
                    .font(.dsLabel)
                    .foregroundStyle(tint ?? Color.secondary)
                Text(value(field) ?? field.empty)
                    .font(field == .introPath ? .caption.weight(.semibold) : (isNext ? .caption.weight(.medium) : .caption))
                    .foregroundStyle(tint ?? (value(field) == nil ? Color.secondary : Color.primary))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                if isNext, pipeline?.nextStep != nil, let due = pipeline?.nextStepDue {
                    Text(overdue ? "Overdue · was due \(due)" : "Due \(due)")
                        .font(.caption2.monospacedDigit().weight(overdue ? .bold : .regular))
                        .foregroundStyle(tint ?? .secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .appleGlassTile(cornerRadius: 10, tint: tint)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Edits \(field.title.lowercased())")
    }
}

/// Edits one pipeline field; the next step also takes an optional due date.
private struct PipelineFieldEditor: View {
    let field: MacDealPipelineView.PipelineField
    let initialText: String
    let initialDue: String?
    /// Saves; returns an error message, or nil once saved.
    let save: (String, String?) async -> String?

    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var hasDue = false
    @State private var due = Date()
    @State private var saving = false
    @State private var error: String?

    /// Calendar days in the device's own time zone, as the server stores them.
    private static let dayFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(field.title, text: $text, axis: .vertical)
                        .lineLimit(2...5)
                }
                if field == .nextStep {
                    Section {
                        Toggle("Due date", isOn: $hasDue)
                        if hasDue {
                            DatePicker("Due", selection: $due, displayedComponents: .date)
                        }
                    }
                }
                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.caption)
                            .foregroundStyle(Color.dsNegative)
                    }
                }
            }
            .navigationTitle(field.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            saving = true
                            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            let dueText = hasDue ? Self.dayFormat.string(from: due) : nil
                            error = await save(trimmed, dueText)
                            saving = false
                            if error == nil { dismiss() }
                        }
                    }
                    .disabled(saving)
                }
            }
        }
        .onAppear {
            text = initialText
            if let initialDue, let date = Self.dayFormat.date(from: initialDue) {
                hasDue = true
                due = date
            }
        }
    }
}
