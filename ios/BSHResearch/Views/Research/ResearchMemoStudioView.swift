import SwiftUI

public struct MacMemoStudioView: View {
    public let company: MacCompany
    @EnvironmentObject private var store: ResearchDeskStore

    public enum StudioSection: String, CaseIterable, Identifiable {
        case thesis = "Thesis Spine"
        case risks = "Risk Matrix"
        case readiness = "Readiness Gates"
        case evidence = "Evidence Claims"

        public var id: String { rawValue }
        public var icon: String {
            switch self {
            case .thesis: return "brain.head.profile"
            case .risks: return "exclamationmark.triangle"
            case .readiness: return "checklist.checked"
            case .evidence: return "magnifyingglass.circle"
            }
        }
    }

    @State private var activeTab: StudioSection = .thesis

    private var analysis: MacMemoAnalysis? {
        store.analysisByCompany[company.id]
    }

    public init(company: MacCompany) {
        self.company = company
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MacCardHeader("Memo studio", subtitle: "Thesis spine, strategic risk matrix & readiness gates.", systemImage: "slider.horizontal.3")

            // Tab bar
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(StudioSection.allCases) { tab in
                        Button {
                            withAnimation { activeTab = tab }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: tab.icon).font(.caption2)
                                Text(tab.rawValue).font(.system(size: 12, weight: activeTab == tab ? .bold : .medium))
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(activeTab == tab ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.08), in: Capsule())
                            .foregroundStyle(activeTab == tab ? Color.accentColor : Color.primary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Tab Content
            switch activeTab {
            case .thesis:
                thesisTab
            case .risks:
                risksTab
            case .readiness:
                readinessTab
            case .evidence:
                evidenceTab
            }
        }
        .padding(14)
        .appleGlassCard(cornerRadius: 14)
    }

    // MARK: - Thesis Spine Tab
    private var thesisTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let pillars = analysis?.thesisSpine?.pillars, !pillars.isEmpty {
                ForEach(Array(pillars.enumerated()), id: \.offset) { idx, pillar in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Pillar \(idx + 1)").font(.dsLabel).foregroundStyle(Color.accentColor)
                            Spacer()
                            if let conf = pillar.confidence {
                                MacStatusPill(text: "\(Int(conf * 100))% confidence", color: conf >= 0.7 ? .green : .orange)
                            }
                        }
                        Text(pillar.title).font(.subheadline.weight(.semibold))
                        if let why = pillar.whyItMatters {
                            Text(why).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .appleGlassTile(cornerRadius: 8)
                }
            } else {
                VStack(spacing: 6) {
                    Image(systemName: "brain.head.profile").font(.system(size: 24)).foregroundStyle(.secondary)
                    Text("Thesis spine will populate when investigation memos are synthesized.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            }
        }
    }

    // MARK: - Strategic Risk Matrix Tab
    private var risksTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let risks = analysis?.risks, !risks.isEmpty {
                ForEach(risks) { risk in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(risk.category).font(.dsLabel).foregroundStyle(.secondary)
                            Spacer()
                            MacStatusPill(text: risk.severity.capitalized, color: risk.severity == "critical" ? .red : (risk.severity == "high" ? .orange : .blue))
                        }
                        Text(risk.title).font(.subheadline.weight(.semibold))
                        if let mit = risk.mitigation, !mit.isEmpty {
                            Text("Mitigation: \(mit)").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .appleGlassTile(cornerRadius: 8)
                }
            } else {
                Text("No strategic risk dilemmas flagged.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Readiness Gates Tab
    private var readinessTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let gates = analysis?.readinessGates, !gates.isEmpty {
                ForEach(gates) { gate in
                    HStack(spacing: 10) {
                        Image(systemName: gate.passed ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                            .foregroundStyle(gate.passed ? Color.green : Color.orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(gate.name).font(.subheadline.weight(.medium))
                            if let notes = gate.notes {
                                Text(notes).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        MacStatusPill(text: gate.passed ? "Ready" : "Blocked", color: gate.passed ? .green : .orange)
                    }
                    .padding(10)
                    .appleGlassTile(cornerRadius: 8)
                }
            } else {
                Text("IC readiness gates will be checked upon memo drafting.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Evidence Claims Tab
    private var evidenceTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let claims = analysis?.evidenceClaims, !claims.isEmpty {
                ForEach(claims) { claim in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(claim.metric ?? "Fact").font(.dsLabel).foregroundStyle(.secondary)
                            Spacer()
                            if let verified = claim.verified {
                                MacStatusPill(text: verified ? "Verified" : "Unverified", color: verified ? .green : .orange)
                            }
                        }
                        Text(claim.claim).font(.caption.weight(.medium))
                        if let src = claim.source {
                            Text("Source: \(src)").font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                    .padding(8)
                    .appleGlassTile(cornerRadius: 8)
                }
            } else {
                Text("Evidence claims verified against EDGAR and source documents will appear here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
