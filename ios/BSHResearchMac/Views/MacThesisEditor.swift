import SwiftUI

/// Firm thesis editor (Settings). Every field feeds the explainable fit score on the Pipeline.
struct MacThesisEditor: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var draft: MacThesis = .empty
    @State private var sectors = ""
    @State private var stages = ""
    @State private var geographies = ""
    @State private var keywords = ""
    @State private var mustBeTrue = ""
    @State private var disqualifiers = ""
    @State private var minCheck = ""
    @State private var maxCheck = ""
    @State private var status: String?
    @State private var saving = false

    var body: some View {
        Group {
            TextField("Thesis name", text: $draft.name, prompt: Text("e.g. Applied AI, seed to Series A"))
            field("Sectors", $sectors, hint: "AI infrastructure, fintech, healthcare")
            field("Stages", $stages, hint: "pre-seed, seed, series a")
            field("Geographies", $geographies, hint: "US, Canada, UK")
            field("Keywords", $keywords, hint: "developer tools, agents, compliance")
            field("Must be true", $mustBeTrue, hint: "one claim per comma — open questions when unknown")
            field("Disqualifiers", $disqualifiers, hint: "crypto, gambling — any match disqualifies")
            LabeledContent("Check size ($M)") {
                HStack(spacing: 6) {
                    TextField("Min", text: $minCheck, prompt: Text("min")).labelsHidden().frame(width: 70)
                    Text("to").foregroundStyle(.secondary)
                    TextField("Max", text: $maxCheck, prompt: Text("max")).labelsHidden().frame(width: 70)
                }
            }
            HStack(spacing: 10) {
                Button {
                    save()
                } label: {
                    if saving { ProgressView().controlSize(.small) } else { Label("Save thesis", systemImage: "checkmark.circle") }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(saving || !store.thesisLoaded || !store.canUpdateSettings)
                Button("Reload") { Task { await store.loadThesis(); syncFromStore() } }
                    .controlSize(.small)
                if let status {
                    Text(status).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let at = store.thesis.updatedAt {
                    Text("Updated \(MacTimeFormat.relative(at))").font(.caption2).foregroundStyle(.tertiary)
                }
            }
            Text("Weights: sector 35 · keywords 25 · stage 20 · geography 10 · check size 10. Scores show as the Fit column on the Pipeline with the reasons on hover — nothing is inferred beyond these rules.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .task {
            if !store.thesisLoaded { await store.loadThesis() }
            syncFromStore()
        }
    }

    private func field(_ label: String, _ text: Binding<String>, hint: String) -> some View {
        TextField(label, text: text, prompt: Text(hint))
    }

    private func syncFromStore() {
        draft = store.thesis
        sectors = draft.sectors.joined(separator: ", ")
        stages = draft.stages.joined(separator: ", ")
        geographies = draft.geographies.joined(separator: ", ")
        keywords = draft.keywords.joined(separator: ", ")
        mustBeTrue = draft.mustBeTrue.joined(separator: ", ")
        disqualifiers = draft.disqualifiers.joined(separator: ", ")
        minCheck = draft.checkSizeMinMusd.map { String(format: "%g", $0) } ?? ""
        maxCheck = draft.checkSizeMaxMusd.map { String(format: "%g", $0) } ?? ""
    }

    private func split(_ s: String) -> [String] {
        s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    }

    private func parseCheckSize(_ text: String) -> Double? {
        var cleaned = text
        if cleaned.hasPrefix("$") { cleaned.removeFirst() }
        if let last = cleaned.last, last == "M" || last == "m" { cleaned.removeLast() }
        cleaned = cleaned.trimmingCharacters(in: .whitespaces)
        guard !cleaned.isEmpty else { return nil }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = .current
        if let n = formatter.number(from: cleaned) { return n.doubleValue }
        return Double(cleaned)
    }

    private func save() {
        var t = draft
        t.sectors = split(sectors)
        t.stages = split(stages)
        t.geographies = split(geographies)
        t.keywords = split(keywords)
        t.mustBeTrue = split(mustBeTrue)
        t.disqualifiers = split(disqualifiers)
        let minText = minCheck.trimmingCharacters(in: .whitespaces)
        let maxText = maxCheck.trimmingCharacters(in: .whitespaces)
        let minValue = parseCheckSize(minText)
        let maxValue = parseCheckSize(maxText)
        if (!minText.isEmpty && minValue == nil) || (!maxText.isEmpty && maxValue == nil) {
            status = "Check size must be a number in $M"
            return
        }
        if let lo = minValue, let hi = maxValue, lo > hi {
            status = "Check size min must be ≤ max"
            return
        }
        if (minValue ?? 0) < 0 || (maxValue ?? 0) < 0 {
            status = "Check size cannot be negative"
            return
        }
        t.checkSizeMinMusd = minValue
        t.checkSizeMaxMusd = maxValue
        saving = true
        status = nil
        Task {
            let ok = await store.saveThesis(t)
            status = ok ? "Saved — Pipeline re-scored" : (store.error ?? "Save failed")
            saving = false
            if ok { syncFromStore() }
        }
    }
}
