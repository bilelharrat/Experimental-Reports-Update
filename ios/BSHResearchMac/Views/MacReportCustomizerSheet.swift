import SwiftUI

/// Institutional-grade research report customizer modal for macOS.
/// Provides deep control over report archetypes, target audience, human-in-the-loop studio workflow,
/// reasoning quality tiers, analyst directives, and document ingestion.
struct MacReportCustomizerSheet: View {
    let company: MacCompany
    var onGenerate: ((MacReport) -> Void)? = nil

    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    enum CustomizerTab: String, CaseIterable, Identifiable {
        case blueprint = "Blueprint"
        case engine = "Engine & Quality"
        case directives = "Directives & Focus"
        case sources = "Evidence Sources"

        var id: String { rawValue }
        var icon: String {
            switch self {
            case .blueprint: return "doc.text.below.ecg"
            case .engine: return "cpu"
            case .directives: return "target"
            case .sources: return "tray.full"
            }
        }
    }

    @State private var activeTab: CustomizerTab = .blueprint
    @State private var config = MacReportCustomizerConfig()
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    // Archetype catalog
    private struct ArchetypeOption: Identifiable {
        let id: String
        let title: String
        let subtitle: String
        let icon: String
        let isDefault: Bool
    }

    private let archetypes: [ArchetypeOption] = [
        ArchetypeOption(
            id: "Investment Report (Auto)",
            title: "Investment Report (Auto)",
            subtitle: "Stage-calibrated autonomous evaluation across financial, moat, and execution dimensions.",
            icon: "wand.and.stars",
            isDefault: true
        ),
        ArchetypeOption(
            id: "Investment Memo (Late-Stage)",
            title: "Investment Memo (Late-Stage)",
            subtitle: "Institutional IC report with 8-dimension risk matrix, thesis spine, and return model.",
            icon: "doc.text.magnifyingglass",
            isDefault: false
        ),
        ArchetypeOption(
            id: "Buffett Investment Memo",
            title: "Buffett Investment Memo",
            subtitle: "Capital allocation, moat durability, management integrity, and margin of safety.",
            icon: "chart.pie.fill",
            isDefault: false
        ),
        ArchetypeOption(
            id: "Financial Analysis",
            title: "Financial Analysis",
            subtitle: "Unit economics, gross margin bridge, runway burn, and capital structure teardown.",
            icon: "chart.line.uptrend.xyaxis",
            isDefault: false
        ),
        ArchetypeOption(
            id: "Market & Competitive Analysis",
            title: "Market & Competitive Analysis",
            subtitle: "TAM sizing, moat durability, Big Tech coexistence, and competitive positioning.",
            icon: "network",
            isDefault: false
        ),
        ArchetypeOption(
            id: "Background Dossier",
            title: "Background Dossier",
            subtitle: "Executive team history, cap table evolution, and product timeline.",
            icon: "person.2.fill",
            isDefault: false
        ),
    ]

    private let audiences = [
        ("Internal", "Internal / IC", "Skeptical, unhedged, downside & margin-of-safety focus", "shield.lefthalf.filled"),
        ("Partner", "Partner / Inflection", "High-level thesis, key catalysts, and deal structuring", "person.badge.key"),
        ("LP", "LP / Co-Invest", "Institutional governance, defensibility, and track record", "building.columns"),
        ("Assistant", "Diligence Associate", "Fact-checking audit trail and evidentiary gaps checklist", "checklist.checked"),
    ]

    private let focusPillarOptions = [
        "Moat & Pricing Power",
        "Cap Table & Dilution Scenarios",
        "Big Tech Displacement Threat",
        "Unit Economics & Burn Runway",
        "Customer Concentration & NDR",
        "Regulatory & Antitrust Risks",
        "Management & Key-Man Dependency",
        "Secondary Market & Exit Multiples",
    ]

    private let starterDirectives = [
        "Scrutinize customer concentration in top accounts and renewal risks.",
        "Evaluate whether GPU cluster depreciation will compress 2026 gross margins.",
        "Test claimed moat durability against open-source foundation models.",
        "Audit enterprise contracts for termination for convenience clauses.",
    ]

    private let companyTypeLenses = [
        ("auto", "Auto (Stage-Calibrated)"),
        ("foundation_model", "AI Foundation Models"),
        ("ai_infra", "AI Infrastructure & Compute"),
        ("ai_app", "Enterprise AI Application"),
        ("short_video", "AI Video & Media"),
        ("robotics", "Robotics & Embodied AI"),
        ("saas", "B2B Cloud SaaS"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider().opacity(0.15)
            tabBar
            Divider().opacity(0.15)

            // Main Tab Content
            ScrollView {
                VStack(spacing: 20) {
                    switch activeTab {
                    case .blueprint:
                        blueprintTabContent
                    case .engine:
                        engineTabContent
                    case .directives:
                        directivesTabContent
                    case .sources:
                        sourcesTabContent
                    }
                }
                .padding(24)
            }

            if let error = errorMessage {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(Color.red)
                    Text(error).font(.dsCaption).foregroundStyle(Color.red)
                    Spacer()
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 8)
                .background(Color.red.opacity(0.1))
            }

            Divider().opacity(0.15)
            bottomActionBar
        }
        .frame(minWidth: 720, idealWidth: 780, maxWidth: 840, minHeight: 620, idealHeight: 680, maxHeight: 760)
        .background(Color.dsCard.ignoresSafeArea())
    }

    // MARK: - Header Bar

    private var headerBar: some View {
        HStack(spacing: 14) {
            // Company Logo Squircle Badge
            MacMonogram(company: company, size: 40)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(company.name ?? company.id)
                        .font(.dsTitle)
                        .foregroundStyle(.primary)

                    if let ticker = company.ticker, !ticker.isEmpty {
                        Text(ticker.uppercased())
                            .font(.system(size: 11, weight: .bold).monospaced())
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12))
                            .foregroundStyle(Color.accentColor)
                            .clipShape(Capsule())
                    }

                    if let sector = company.sector ?? company.industry, !sector.isEmpty {
                        Text(sector)
                            .font(.dsCaption)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.primary.opacity(0.06))
                            .clipShape(Capsule())
                            .foregroundStyle(.secondary)
                    }
                }

                Text("Custom Research Memo Specification · Stage & Framing Controls")
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .frame(width: 26, height: 26)
                    .background(Color.primary.opacity(0.06))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 16)
    }

    // MARK: - Tab Bar

    private var tabBar: some View {
        HStack(spacing: 6) {
            ForEach(CustomizerTab.allCases) { tab in
                Button {
                    activeTab = tab
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: tab.icon)
                            .font(.system(size: 12, weight: .medium))
                        Text(tab.rawValue)
                            .font(.dsSubhead)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(activeTab == tab ? Color.accentColor.opacity(0.15) : Color.clear)
                    .foregroundStyle(activeTab == tab ? Color.accentColor : Color.secondary)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 8)
        .background(Color.primary.opacity(0.02))
    }

    // MARK: - Tab 1: Blueprint

    private var blueprintTabContent: some View {
        VStack(alignment: .leading, spacing: 22) {
            // Report Archetype Selection
            VStack(alignment: .leading, spacing: 10) {
                MacSectionLabel("REPORT ARCHETYPE", trailing: "Determines section outline, scorecard and thesis structure")
                
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(archetypes) { option in
                        archetypeCard(option)
                    }
                }
            }

            // Target Audience
            VStack(alignment: .leading, spacing: 10) {
                MacSectionLabel("TARGET AUDIENCE & PERSPECTIVE", trailing: "Calibrates tone, skepticism, and detail density")

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(audiences, id: \.0) { (key, label, desc, icon) in
                        audienceCard(key: key, label: label, description: desc, icon: icon)
                    }
                }
            }

            // Scope & Language in a row
            HStack(alignment: .top, spacing: 16) {
                // Scope
                VStack(alignment: .leading, spacing: 10) {
                    MacSectionLabel("REPORT DEPTH & SCOPE")
                    HStack(spacing: 10) {
                        scopeCard(
                            id: "full",
                            label: "Full IC Dossier",
                            desc: "All 8-risk cards, scenario models, appendices",
                            icon: "doc.text.fill"
                        )
                        scopeCard(
                            id: "compact",
                            label: "Compact Brief",
                            desc: "3–4 page partner summary with bulleted risk register",
                            icon: "doc.plaintext"
                        )
                    }
                }
                .frame(maxWidth: .infinity)

                // Language
                VStack(alignment: .leading, spacing: 10) {
                    MacSectionLabel("DELIVERY LANGUAGE")
                    HStack(spacing: 8) {
                        languagePill("en", label: "English", flag: "🇺🇸")
                        languagePill("zh", label: "Chinese", flag: "🇨🇳")
                        languagePill("dual", label: "Dual Pack", flag: "🌐")
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
    }

    private func archetypeCard(_ option: ArchetypeOption) -> some View {
        let isSelected = config.reportType == option.id
        return Button {
            config.reportType = option.id
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: option.icon)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(option.title)
                            .font(.dsHeadline)
                            .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                        Spacer()
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                    Text(option.subtitle)
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func audienceCard(key: String, label: String, description: String, icon: String) -> some View {
        let isSelected = config.audience == key
        return Button {
            config.audience = key
        } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    .frame(width: 20)

                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(label)
                            .font(.dsSubhead.weight(.semibold))
                            .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                        Spacer()
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                    Text(description)
                        .font(.dsCaption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func scopeCard(id: String, label: String, desc: String, icon: String) -> some View {
        let isSelected = config.reportMode == id
        return Button {
            config.reportMode = id
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    Text(label)
                        .font(.dsSubhead.weight(.semibold))
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 13))
                            .foregroundStyle(Color.accentColor)
                    }
                }
                Text(desc)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func languagePill(_ lang: String, label: String, flag: String) -> some View {
        let isSelected = config.language == lang
        return Button {
            config.language = lang
        } label: {
            HStack(spacing: 5) {
                Text(flag)
                Text(label)
                    .font(.dsCaption.weight(.medium))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(isSelected ? Color.accentColor.opacity(0.12) : Color.primary.opacity(0.04))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Tab 2: Engine & Quality

    private var engineTabContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Workflow mode
            VStack(alignment: .leading, spacing: 10) {
                MacSectionLabel("EXECUTION WORKFLOW MODE", trailing: "Control autonomous vs human-in-the-loop checkpoints")

                HStack(spacing: 12) {
                    workflowCard(
                        mode: "studio_review",
                        title: "Studio Review (Human-in-the-Loop)",
                        desc: "Agents run deep investigation (Phases 1-2) and park at Awaiting Studio. Review, edit, and curate Thesis Spine cards and Risk cards before generating the final Phase 3 memo.",
                        badge: "RECOMMENDED",
                        icon: "slider.horizontal.3"
                    )

                    workflowCard(
                        mode: "one_click",
                        title: "One-Click Autonomous Pipeline",
                        desc: "Autonomous multi-agent pipeline runs straight through investigation, drafting, Chinese parity translation, and .docx/PDF rendering without pausing.",
                        badge: "AUTONOMOUS",
                        icon: "bolt.fill"
                    )
                }
            }

            // Quality Tiers
            VStack(alignment: .leading, spacing: 10) {
                MacSectionLabel("MODEL REASONING TIER & COMPUTE QUALITY", trailing: "Frontier reasoning budget across research passes")

                HStack(spacing: 12) {
                    qualityCard(
                        id: "best",
                        title: "Best Tier (Frontier)",
                        desc: "All frontier reasoning models at full effort. Deepest forensic scrutiny, exhaustive risk modeling, and full citation hygiene.",
                        icon: "sparkles",
                        badge: "MAX SCRUTINY"
                    )

                    qualityCard(
                        id: "balanced",
                        title: "Balanced",
                        desc: "High-throughput models for broad data gathering and frontier models for thesis synthesis and final drafting.",
                        icon: "scale.3d",
                        badge: "DEFAULT"
                    )

                    qualityCard(
                        id: "economy",
                        title: "Economy",
                        desc: "Efficient token budget and faster turnaround for preliminary checks and rapid triage.",
                        icon: "leaf.fill",
                        badge: "FAST"
                    )
                }
            }
        }
    }

    private func workflowCard(mode: String, title: String, desc: String, badge: String, icon: String) -> some View {
        let isSelected = config.generationMode == mode
        return Button {
            config.generationMode = mode
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    Text(badge)
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(isSelected ? Color.accentColor.opacity(0.2) : Color.primary.opacity(0.06))
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                        .clipShape(Capsule())
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 15))
                            .foregroundStyle(Color.accentColor)
                    }
                }

                Text(title)
                    .font(.dsHeadline)
                    .foregroundStyle(isSelected ? Color.primary : Color.secondary)

                Text(desc)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 130, alignment: .topLeading)
            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func qualityCard(id: String, title: String, desc: String, icon: String, badge: String) -> some View {
        let isSelected = config.quality == id
        return Button {
            config.quality = id
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    Text(badge)
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(isSelected ? Color.accentColor.opacity(0.2) : Color.primary.opacity(0.06))
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                        .clipShape(Capsule())
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 13))
                            .foregroundStyle(Color.accentColor)
                    }
                }

                Text(title)
                    .font(.dsSubhead.weight(.semibold))

                Text(desc)
                    .font(.dsCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous)
                    .stroke(isSelected ? Color.accentColor : Color.dsHairline, lineWidth: isSelected ? 1.5 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Tab 3: Directives & Focus

    private var directivesTabContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Freeform Analyst Directive
            VStack(alignment: .leading, spacing: 8) {
                MacSectionLabel("ANALYST DIRECTIVES & FOCUS QUESTIONS", trailing: "Freeform guidance provided directly to the research agents")

                TextEditor(text: $config.customPrompt)
                    .font(.dsBody)
                    .frame(minHeight: 85, maxHeight: 110)
                    .padding(8)
                    .background(Color.primary.opacity(0.03))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.dsHairline, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                // Starter chips
                HStack(alignment: .center, spacing: 6) {
                    Text("Suggestions:")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.tertiary)

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(starterDirectives, id: \.self) { starter in
                                Button {
                                    if config.customPrompt.isEmpty {
                                        config.customPrompt = starter
                                    } else {
                                        config.customPrompt += " " + starter
                                    }
                                } label: {
                                    Text(starter)
                                        .font(.system(size: 10))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.primary.opacity(0.05))
                                        .clipShape(Capsule())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }

            // Strategic Dilemma Focus Chips
            VStack(alignment: .leading, spacing: 8) {
                MacSectionLabel("STRATEGIC DILIGENCE PILLARS", trailing: "Select core dimensions to weight in risk matrix")

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(focusPillarOptions, id: \.self) { pillar in
                        let isSelected = config.focusPillars.contains(pillar)
                        Button {
                            if isSelected {
                                config.focusPillars.removeAll { $0 == pillar }
                            } else {
                                config.focusPillars.append(pillar)
                            }
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                                Text(pillar)
                                    .font(.dsCaption.weight(.medium))
                                    .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                                Spacer()
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Company Type Lens Override
            VStack(alignment: .leading, spacing: 8) {
                MacSectionLabel("COMPANY SECTOR LENS OVERRIDE", trailing: "Overrides vertical-specific scorecard weights")

                Picker("", selection: $config.companyTypeLens) {
                    ForEach(companyTypeLenses, id: \.0) { (key, label) in
                        Text(label).tag(key)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 320)
            }
        }
    }

    // MARK: - Tab 4: Sources & Evidence

    private var sourcesTabContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            MacSectionLabel("PRIOR RESEARCH & EVIDENCE ATTACHMENTS", trailing: "Select prior dossiers to cross-reference as baseline context")

            let reports = store.reports(for: company.id)
            if reports.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "doc.badge.plus")
                        .font(.system(size: 32))
                        .foregroundStyle(.tertiary)
                    Text("No prior research dossiers for \(company.name ?? company.id) yet.")
                        .font(.dsSubhead)
                        .foregroundStyle(.secondary)
                    Text("Research agents will leverage public filings, company website, earnings calls, and industry databases.")
                        .font(.dsCaption)
                        .foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, minHeight: 160)
                .background(Color.primary.opacity(0.02))
                .clipShape(RoundedRectangle(cornerRadius: MacDS.tileRadius, style: .continuous))
            } else {
                VStack(spacing: 8) {
                    ForEach(reports) { rep in
                        let isSelected = config.selectedDocumentIds.contains(rep.id)
                        Button {
                            if isSelected {
                                config.selectedDocumentIds.removeAll { $0 == rep.id }
                            } else {
                                config.selectedDocumentIds.append(rep.id)
                            }
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                                Image(systemName: "doc.text.fill")
                                    .foregroundStyle(Color.accentColor)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rep.displayTitle)
                                        .font(.dsSubhead)
                                    Text("Created \(rep.dateLabel) · \(rep.audience ?? "Internal")")
                                        .font(.dsCaption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if isSelected {
                                    Text("PRIOR CONTEXT")
                                        .font(.system(size: 9, weight: .bold))
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.accentColor.opacity(0.15))
                                        .foregroundStyle(Color.accentColor)
                                        .clipShape(Capsule())
                                }
                            }
                            .padding(10)
                            .background(isSelected ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.03))
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: - Bottom Action Bar

    private var bottomActionBar: some View {
        HStack(spacing: 16) {
            // Live Summary Badges
            HStack(spacing: 6) {
                summaryBadge(config.reportType.replacingOccurrences(of: "Investment ", with: ""))
                summaryBadge(config.audience)
                summaryBadge(config.reportMode == "full" ? "Full IC" : "Compact")
                summaryBadge(config.quality.capitalized)
                summaryBadge(config.generationMode == "studio_review" ? "Studio Review" : "One-Click")
            }

            Spacer()

            Button("Cancel") {
                dismiss()
            }
            .keyboardShortcut(.cancelAction)

            Button {
                Task { await submit() }
            } label: {
                HStack(spacing: 6) {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: config.generationMode == "studio_review" ? "sparkles" : "arrow.triangle.2.circlepath")
                    }
                    Text(config.generationMode == "studio_review" ? "Launch Studio Investigation" : "Generate Research Memo")
                }
                .font(.dsSubhead.weight(.semibold))
            }
            .buttonStyle(.borderedProminent)
            .disabled(isSubmitting)
            .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(Color.primary.opacity(0.02))
    }

    private func summaryBadge(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.primary.opacity(0.06))
            .clipShape(Capsule())
            .foregroundStyle(.secondary)
    }

    private func submit() async {
        isSubmitting = true
        errorMessage = nil
        do {
            let report = try await store.launchCustomReport(companyId: company.id, config: config)
            onGenerate?(report)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            isSubmitting = false
        }
    }
}
