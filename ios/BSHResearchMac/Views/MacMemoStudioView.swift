import SwiftUI

/// Institutional Memo Studio Workbench for macOS.
/// Provides full interactive human-in-the-loop control over the AI Thesis Spine,
/// Strategic Dilemma Risk Matrix, IC Readiness Gates, and Phase 3 Synthesis.
struct MacMemoStudioView: View {
    let company: MacCompany

    @EnvironmentObject private var store: MacAppStore

    enum StudioSection: String, CaseIterable, Identifiable {
        case thesis = "Thesis Spine"
        case risks = "Risk Matrix"
        case readiness = "Readiness Gates"
        case evidence = "Evidence Claims"

        var id: String { rawValue }
        var icon: String {
            switch self {
            case .thesis: return "brain.head.profile"
            case .risks: return "exclamationmark.triangle"
            case .readiness: return "checklist.checked"
            case .evidence: return "magnifyingglass.circle"
            }
        }
    }

    @State private var activeTab: StudioSection = .thesis
    @State private var isSynthesizing = false
    @State private var showAddCardSheet = false
    @State private var newCardTitle = ""
    @State private var newCardCategory = "Moat"
    @State private var newCardSeverity = "high"
    @State private var refiningRiskId: String?
    @State private var refineFraming = "other"
    @State private var refineNote = ""
    @State private var editingCardId: String?
    @State private var editedCardTitle = ""

    private var editorState: MacMemoEditorState? {
        store.memoEditorByCompany[company.id]
    }

    private var analysis: MacMemoAnalysis? {
        store.analysisByCompany[company.id]
    }

    private var evidence: MacEvidenceMatrix? {
        store.evidenceByCompany[company.id]
    }

    private var awaitingStudioReport: MacReport? {
        store.reports(for: company.id).first { $0.status == "awaiting_studio" }
    }

    private var latestReport: MacReport? {
        store.reports(for: company.id).first
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            studioHeader
            studioActionBar

            if store.memoEditorBusy.contains(company.id) && editorState == nil {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text("Loading Memo Studio configuration…")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 20)
                .frame(maxWidth: .infinity)
            } else {
                tabSelector
                tabContent
            }
        }
        .padding(18)
        .appleGlassCard(cornerRadius: MacDS.cardRadius)
        .task {
            await store.loadMemoEditor(company.id)
            await store.loadMemoAnalysis(company.id)
            await store.loadEvidence(company.id)
        }
        .sheet(isPresented: $showAddCardSheet) {
            addCardModal
        }
    }

    // MARK: - Studio Header

    private var studioHeader: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "slider.horizontal.3")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color.accentColor)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text("Memo Studio Workbench")
                        .font(.dsHeadline)
                    Text("HUMAN-IN-THE-LOOP")
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.12))
                        .foregroundStyle(Color.accentColor)
                        .clipShape(Capsule())
                }
                Text("Direct analyst curation of AI thesis spine, dilemma weights, and readiness gates prior to synthesis")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            // Refresh button
            Button {
                Task {
                    await store.loadMemoEditor(company.id)
                    await store.loadMemoAnalysis(company.id)
                }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain)
            .help("Refresh Studio State")
        }
    }

    // MARK: - Studio Action Banner

    @ViewBuilder
    private var studioActionBar: some View {
        if let awaiting = awaitingStudioReport {
            HStack(spacing: 12) {
                Circle()
                    .fill(Color.orange)
                    .frame(width: 10, height: 10)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Investigation Parked · Awaiting Studio Review")
                        .font(.dsSubhead.weight(.semibold))
                        .foregroundStyle(Color.orange)
                    Text("Phases 1 & 2 completed. Refine thesis cards below and trigger institutional synthesis when ready.")
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button {
                    Task {
                        isSynthesizing = true
                        defer { isSynthesizing = false }
                        _ = try? await store.generateReportFromStudio(reportId: awaiting.id)
                    }
                } label: {
                    HStack(spacing: 6) {
                        if isSynthesizing {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "sparkles")
                        }
                        Text("Synthesize Phase 3 Memo")
                    }
                    .font(.dsSubhead.weight(.semibold))
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSynthesizing)
            }
            .padding(12)
            .background(Color.orange.opacity(0.08))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(Color.orange.opacity(0.25), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        } else {
            HStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(Color.green)
                    .font(.system(size: 14))

                Text("Spine Editor Active · Live mutations persist immediately to the server.")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)

                Spacer()

                if let rep = latestReport, rep.canOpen {
                    Button {
                        store.openICReview(report: rep)
                    } label: {
                        Label("Open Memo View", systemImage: "doc.text.magnifyingglass")
                            .font(.dsCaption.weight(.medium))
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.primary.opacity(0.06))
                    .clipShape(Capsule())
                }
            }
            .padding(10)
            .background(Color.primary.opacity(0.02))
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
    }

    // MARK: - Tab Selector

    private var tabSelector: some View {
        HStack(spacing: 6) {
            ForEach(StudioSection.allCases) { tab in
                Button {
                    activeTab = tab
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: tab.icon)
                            .font(.system(size: 11, weight: .medium))
                        Text(tab.rawValue)
                            .font(.dsSubhead)
                        if tab == .thesis, let count = editorState?.sections.investmentThesis?.cards.count {
                            countPill("\(count)")
                        } else if tab == .risks, let count = editorState?.sections.risksMitigations?.cards.count {
                            countPill("\(count)")
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(activeTab == tab ? Color.accentColor.opacity(0.12) : Color.clear)
                    .foregroundStyle(activeTab == tab ? Color.accentColor : Color.secondary)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .buttonStyle(.plain)
            }
            Spacer()

            if activeTab == .thesis {
                Button {
                    showAddCardSheet = true
                } label: {
                    Label("Add Card", systemImage: "plus")
                        .font(.dsCaption.weight(.medium))
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.1))
                .foregroundStyle(Color.accentColor)
                .clipShape(Capsule())
            }
        }
        .padding(.vertical, 4)
    }

    private func countPill(_ count: String) -> some View {
        Text(count)
            .font(.system(size: 10, weight: .bold))
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(Color.primary.opacity(0.08))
            .clipShape(Capsule())
    }

    // MARK: - Tab Content

    @ViewBuilder
    private var tabContent: some View {
        switch activeTab {
        case .thesis:
            thesisTabContent
        case .risks:
            risksTabContent
        case .readiness:
            readinessTabContent
        case .evidence:
            evidenceTabContent
        }
    }

    // MARK: - Tab 1: Thesis Spine

    private var thesisTabContent: some View {
        let cards = editorState?.sections.investmentThesis?.cards ?? []
        return VStack(alignment: .leading, spacing: 10) {
            if cards.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "brain.head.profile")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text("No thesis spine cards generated yet.")
                        .font(.dsSubhead)
                        .foregroundStyle(.secondary)
                    Text("Run a Studio Investigation or add a custom card to begin structuring the thesis.")
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ForEach(Array(cards.enumerated()), id: \.element.id) { index, card in
                    thesisCardRow(card: card, index: index, total: cards.count)
                }
            }
        }
    }

    private func thesisCardRow(card: MacMemoEditorCard, index: Int, total: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                // Inclusion Toggle
                Button {
                    Task {
                        await store.patchMemoCard(
                            companyId: company.id,
                            sectionId: "investment_thesis",
                            cardId: card.id,
                            included: !card.isCardIncluded
                        )
                    }
                } label: {
                    Image(systemName: card.isCardIncluded ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 15))
                        .foregroundStyle(card.isCardIncluded ? Color.accentColor : Color.secondary)
                }
                .buttonStyle(.plain)

                // Category pill
                if let cat = card.category, !cat.isEmpty {
                    Text(cat.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.primary.opacity(0.06))
                        .foregroundStyle(.secondary)
                        .clipShape(Capsule())
                }

                // Title
                if editingCardId == card.id {
                    TextField("Card Title", text: $editedCardTitle, onCommit: {
                        Task {
                            await store.patchMemoCard(
                                companyId: company.id,
                                sectionId: "investment_thesis",
                                cardId: card.id,
                                title: editedCardTitle
                            )
                            editingCardId = nil
                        }
                    })
                    .textFieldStyle(.plain)
                    .font(.dsHeadline)
                } else {
                    Text(card.title)
                        .font(.dsHeadline)
                        .foregroundStyle(card.isCardIncluded ? Color.primary : Color.secondary)
                        .onTapGesture(count: 2) {
                            editingCardId = card.id
                            editedCardTitle = card.title
                        }
                }

                Spacer()

                // Move Controls
                HStack(spacing: 4) {
                    Button {
                        Task {
                            await store.moveMemoCard(
                                companyId: company.id,
                                sectionId: "investment_thesis",
                                cardId: card.id,
                                direction: "up"
                            )
                        }
                    } label: {
                        Image(systemName: "chevron.up")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .buttonStyle(.plain)
                    .disabled(index == 0)

                    Button {
                        Task {
                            await store.moveMemoCard(
                                companyId: company.id,
                                sectionId: "investment_thesis",
                                cardId: card.id,
                                direction: "down"
                            )
                        }
                    } label: {
                        Image(systemName: "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .buttonStyle(.plain)
                    .disabled(index == total - 1)

                    Button {
                        Task {
                            await store.deleteMemoCard(
                                companyId: company.id,
                                sectionId: "investment_thesis",
                                cardId: card.id
                            )
                        }
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 11))
                            .foregroundStyle(Color.red.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                    .help("Delete Card")
                }
            }

            // Bullets
            if !card.bullets.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(card.bullets) { bullet in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                                .font(.dsCaption)
                                .foregroundStyle(.secondary)
                            Text(bullet.text)
                                .font(.dsCaption)
                                .foregroundStyle(card.isCardIncluded ? Color.primary : Color.secondary)
                        }
                    }
                }
                .padding(.leading, 26)
            }
        }
        .padding(12)
        .background(card.isCardIncluded ? Color.primary.opacity(0.02) : Color.primary.opacity(0.01))
        .overlay(
            RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                .stroke(card.isCardIncluded ? Color.dsHairline : Color.dsHairline.opacity(0.5), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        .opacity(card.isCardIncluded ? 1.0 : 0.6)
    }

    // MARK: - Tab 2: Risk Matrix

    private var risksTabContent: some View {
        let cards = editorState?.sections.risksMitigations?.cards ?? []
        return VStack(alignment: .leading, spacing: 10) {
            if cards.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text("No strategic risk cards extracted yet.")
                        .font(.dsSubhead)
                        .foregroundStyle(.secondary)
                    Text("Phase 1 investigations will evaluate 8 key dilemma dimensions.")
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ForEach(cards) { card in
                    riskCardRow(card: card)
                }
            }
        }
    }

    private func riskCardRow(card: MacMemoEditorCard) -> some View {
        let isRefining = refiningRiskId == card.id
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                // Included Toggle
                Button {
                    Task {
                        await store.patchMemoCard(
                            companyId: company.id,
                            sectionId: "risks_mitigations",
                            cardId: card.id,
                            included: !card.isCardIncluded
                        )
                    }
                } label: {
                    Image(systemName: card.isCardIncluded ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 15))
                        .foregroundStyle(card.isCardIncluded ? Color.accentColor : Color.secondary)
                }
                .buttonStyle(.plain)

                // Severity Badge
                severityBadge(card.severity ?? "medium")

                // Title
                Text(card.title)
                    .font(.dsHeadline)
                    .foregroundStyle(card.isCardIncluded ? Color.primary : Color.secondary)

                Spacer()

                // Refine button
                Button {
                    if isRefining {
                        refiningRiskId = nil
                    } else {
                        refiningRiskId = card.id
                        refineFraming = "other"
                        refineNote = ""
                    }
                } label: {
                    Label(isRefining ? "Done" : "Refine Framing", systemImage: isRefining ? "chevron.up" : "slider.horizontal.2.square")
                        .font(.dsCaption.weight(.medium))
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(isRefining ? Color.accentColor.opacity(0.12) : Color.primary.opacity(0.05))
                .foregroundStyle(isRefining ? Color.accentColor : Color.secondary)
                .clipShape(Capsule())
            }

            // Bullets & Mitigations
            if !card.bullets.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(card.bullets) { bullet in
                        HStack(alignment: .top, spacing: 6) {
                            Text("—")
                                .font(.dsCaption)
                                .foregroundStyle(.secondary)
                            Text(bullet.text)
                                .font(.dsCaption)
                                .foregroundStyle(card.isCardIncluded ? Color.primary : Color.secondary)
                        }
                    }
                }
                .padding(.leading, 26)
            }

            // Inline Refinement Panel
            if isRefining {
                VStack(alignment: .leading, spacing: 8) {
                    Divider().opacity(0.2)

                    HStack(spacing: 12) {
                        Text("Framing Override:")
                            .font(.dsCaption.weight(.semibold))

                        Picker("", selection: $refineFraming) {
                            Text("Other / Nuanced").tag("other")
                            Text("Overstated Threat").tag("overstated")
                            Text("Understated Risk").tag("understated")
                            Text("Adequately Mitigated").tag("mitigated")
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: 180)
                    }

                    TextField("Add analyst steering note (injected into Phase 3 synthesis)…", text: $refineNote)
                        .textFieldStyle(.plain)
                        .font(.dsCaption)
                        .padding(8)
                        .background(Color.primary.opacity(0.04))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))

                    HStack {
                        Spacer()
                        Button("Apply Refinement") {
                            Task {
                                await store.refineRisk(
                                    companyId: company.id,
                                    riskId: card.id,
                                    framing: refineFraming,
                                    analystNote: refineNote
                                )
                                refiningRiskId = nil
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .font(.dsCaption.weight(.semibold))
                    }
                }
                .padding(10)
                .background(Color.primary.opacity(0.02))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
        }
        .padding(12)
        .background(card.isCardIncluded ? Color.primary.opacity(0.02) : Color.primary.opacity(0.01))
        .overlay(
            RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                .stroke(card.isCardIncluded ? Color.dsHairline : Color.dsHairline.opacity(0.5), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        .opacity(card.isCardIncluded ? 1.0 : 0.6)
    }

    private func severityBadge(_ severity: String) -> some View {
        let (color, label) = {
            switch severity.lowercased() {
            case "critical": return (Color.red, "CRITICAL")
            case "high": return (Color.orange, "HIGH")
            case "medium": return (Color.yellow, "MEDIUM")
            case "low": return (Color.green, "LOW")
            default: return (Color.secondary, severity.uppercased())
            }
        }()

        return Text(label)
            .font(.system(size: 9, weight: .bold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    // MARK: - Tab 3: Readiness Gates

    private var readinessTabContent: some View {
        let areas = analysis?.additionalAreas ?? []
        return VStack(alignment: .leading, spacing: 10) {
            if areas.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "checklist.checked")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text("No diligence readiness areas logged yet.")
                        .font(.dsSubhead)
                        .foregroundStyle(.secondary)
                    Text("Run the readiness tool or memo analysis to compute stage compliance.")
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ForEach(areas, id: \.id) { area in
                    let statColor = readinessStatusColor(area.status)
                    let statIcon = readinessStatusIcon(area.status)
                    HStack(spacing: 12) {
                        Image(systemName: statIcon)
                            .foregroundStyle(statColor)
                            .font(.system(size: 14))

                        VStack(alignment: .leading, spacing: 2) {
                            Text(area.area ?? area.id)
                                .font(.dsHeadline)
                            if let notes = area.rationale ?? area.whyItMatters, !notes.isEmpty {
                                Text(notes)
                                    .font(.dsCaption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        Spacer()

                        Text((area.status ?? "Open").capitalized)
                            .font(.system(size: 10, weight: .bold))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(statColor.opacity(0.15))
                            .foregroundStyle(statColor)
                            .clipShape(Capsule())
                    }
                    .padding(10)
                    .background(Color.primary.opacity(0.02))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.dsHairline, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
        }
    }

    private func readinessStatusIcon(_ status: String?) -> String {
        switch (status ?? "").lowercased() {
        case "clear", "passed", "approved": return "checkmark.circle.fill"
        case "warning", "open": return "exclamationmark.triangle.fill"
        case "blocker", "critical", "failed": return "xmark.circle.fill"
        default: return "circle"
        }
    }

    private func readinessStatusColor(_ status: String?) -> Color {
        switch (status ?? "").lowercased() {
        case "clear", "passed", "approved": return Color.green
        case "warning", "open": return Color.orange
        case "blocker", "critical", "failed": return Color.red
        default: return Color.secondary
        }
    }

    // MARK: - Tab 4: Evidence Claims

    private var evidenceTabContent: some View {
        let claims = evidence?.claims ?? []
        return VStack(alignment: .leading, spacing: 10) {
            if claims.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "magnifyingglass.circle")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text("No factual claims logged in evidence matrix.")
                        .font(.dsSubhead)
                        .foregroundStyle(.secondary)
                    Text("Evidence matrix is generated during deep research extraction.")
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ForEach(claims) { claim in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            claimStatusPill(claim.statusLabel)
                            Text(claim.claim)
                                .font(.dsHeadline)
                            Spacer()
                        }

                        if !claim.supportingEvidence.isEmpty {
                            ForEach(claim.supportingEvidence, id: \.self) { entry in
                                HStack(alignment: .top, spacing: 6) {
                                    Image(systemName: "doc.text")
                                        .font(.system(size: 10))
                                        .foregroundStyle(Color.accentColor)
                                    if let exc = entry.excerpt {
                                        Text(exc)
                                            .font(.dsCaption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(2)
                                    }
                                }
                                .padding(.leading, 12)
                            }
                        }
                    }
                    .padding(10)
                    .background(Color.primary.opacity(0.02))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.dsHairline, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
        }
    }

    private func claimStatusPill(_ label: String) -> some View {
        let (color, text) = {
            switch label.lowercased() {
            case "supported": return (Color.green, "SUPPORTED")
            case "contradicted": return (Color.red, "CONTRADICTED")
            case "partial", "mixed": return (Color.orange, "MIXED")
            default: return (Color.secondary, "UNVERIFIED")
            }
        }()

        return Text(text)
            .font(.system(size: 9, weight: .bold))
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    // MARK: - Add Custom Thesis Card Sheet

    private var addCardModal: some View {
        VStack(spacing: 16) {
            HStack {
                Text("Add Custom Thesis Card")
                    .font(.dsTitle)
                Spacer()
                Button("Cancel") { showAddCardSheet = false }
                    .keyboardShortcut(.cancelAction)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Thesis Headline / Argument")
                    .font(.dsCaption.weight(.medium))
                TextField("e.g. Proprietary data moat compounds faster than open-weight checkpoints", text: $newCardTitle)
                    .textFieldStyle(.roundedBorder)
            }

            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Category")
                        .font(.dsCaption.weight(.medium))
                    Picker("", selection: $newCardCategory) {
                        Text("Moat & Defensibility").tag("Moat")
                        Text("Financials & Unit Economics").tag("Financials")
                        Text("Market & TAM").tag("Market")
                        Text("Team & Execution").tag("Team")
                        Text("Strategic Catalysts").tag("Catalyst")
                    }
                    .pickerStyle(.menu)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Strength / Priority")
                        .font(.dsCaption.weight(.medium))
                    Picker("", selection: $newCardSeverity) {
                        Text("High Conviction").tag("high")
                        Text("Moderate").tag("medium")
                        Text("Watch Item").tag("low")
                    }
                    .pickerStyle(.menu)
                }
            }

            HStack {
                Spacer()
                Button("Add to Thesis Spine") {
                    let title = newCardTitle.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !title.isEmpty else { return }
                    Task {
                        await store.addMemoCard(
                            companyId: company.id,
                            sectionId: "investment_thesis",
                            title: title,
                            category: newCardCategory,
                            severity: newCardSeverity
                        )
                        newCardTitle = ""
                        showAddCardSheet = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(newCardTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 460)
    }
}
