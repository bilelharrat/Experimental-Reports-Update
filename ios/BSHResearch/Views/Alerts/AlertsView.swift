import SwiftUI
import UserNotifications

@MainActor
final class AlertsViewModel: ObservableObject {
    @Published var events: [AlertEvent] = []
    @Published var checking = false
    @Published var status: String?
    @Published var error: String?

    func loadEvents() async {
        do {
            let res: AlertEventsResponse = try await APIClient.shared.get(
                "alerts/events",
                query: [URLQueryItem(name: "limit", value: "50")]
            )
            events = res.events
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Evaluate rules server-side right now; fire local notifications for hits.
    func checkNow() async {
        checking = true
        error = nil
        status = nil
        defer { checking = false }
        do {
            let res: AlertCheckResponse = try await APIClient.shared.post("alerts/check")
            let fired = res.fired ?? []
            status = fired.isEmpty ? "No alerts fired" : "\(fired.count) alert(s) fired"
            for event in fired {
                Self.notify(event)
            }
            await loadEvents()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    static func requestPermission() {
        UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    static func notify(_ event: AlertEvent) {
        let content = UNMutableNotificationContent()
        content.title = event.ticker ?? "Alert"
        content.body = event.message ?? "Alert fired"
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: event.id,
            content: content,
            trigger: nil // deliver immediately
        )
        UNUserNotificationCenter.current().add(request)
    }
}

struct AlertsView: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var desk: DeskStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model = AlertsViewModel()
    @State private var showAdd = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button {
                        Task { await model.checkNow() }
                    } label: {
                        Label(
                            model.checking ? language.t("common.loading") : language.t("alerts.check_now"),
                            systemImage: "bolt.badge.clock"
                        )
                    }
                    .disabled(model.checking)
                    if let status = model.status {
                        Text(status).font(.caption).foregroundStyle(.secondary)
                    }
                    if let err = model.error ?? desk.syncError {
                        Text(err).font(.caption).foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        showAdd = true
                    } label: {
                        Label(language.t("alerts.add"), systemImage: "plus.circle")
                    }
                    if desk.alertRules.isEmpty {
                        Text(language.t("alerts.none")).foregroundStyle(.secondary)
                    } else {
                        ForEach(desk.alertRules) { rule in
                            ruleRow(rule)
                        }
                    }
                } header: {
                    Text(language.t("alerts.rules"))
                }

                Section(language.t("alerts.history")) {
                    if model.events.isEmpty {
                        Text(language.t("alerts.no_events")).foregroundStyle(.secondary)
                    } else {
                        ForEach(model.events) { event in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(event.message ?? "\(event.ticker ?? "?")")
                                    .font(.subheadline)
                                if let at = event.firedAt {
                                    Text(at.replacingOccurrences(of: "T", with: " ").prefix(19))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle(language.t("alerts.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.t("common.done")) { dismiss() }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddAlertRuleSheet()
            }
            .task {
                AlertsViewModel.requestPermission()
                await desk.loadIfNeeded()
                await model.loadEvents()
            }
        }
    }

    private func ruleRow(_ rule: AlertRule) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("\(rule.ticker)  \(rule.kind) \(rule.direction) \(rule.threshold, specifier: "%g")")
                    .font(.subheadline.monospaced())
            }
            Spacer()
            Toggle("", isOn: Binding(
                get: { rule.enabled },
                set: { on in
                    var updated = rule
                    updated.enabled = on
                    Task { await desk.updateRule(updated) }
                }
            ))
            .labelsHidden()
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                Task { await desk.deleteRule(id: rule.id) }
            } label: {
                Label(language.t("research.delete"), systemImage: "trash")
            }
        }
    }
}

struct AddAlertRuleSheet: View {
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var desk: DeskStore
    @Environment(\.dismiss) private var dismiss

    @State private var ticker = ""
    @State private var kind = "price"
    @State private var direction = "above"
    @State private var threshold = ""

    var body: some View {
        NavigationStack {
            Form {
                TextField(language.t("market.search_ticker"), text: $ticker)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                Picker(language.t("alerts.kind"), selection: $kind) {
                    Text(language.t("alerts.kind_price")).tag("price")
                    Text(language.t("alerts.kind_pct")).tag("pct")
                }
                .pickerStyle(.segmented)
                Picker(language.t("alerts.direction"), selection: $direction) {
                    Text(language.t("alerts.above")).tag("above")
                    Text(language.t("alerts.below")).tag("below")
                }
                .pickerStyle(.segmented)
                TextField(language.t("alerts.threshold"), text: $threshold)
                    .keyboardType(.decimalPad)
            }
            .navigationTitle(language.t("alerts.add"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.t("common.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.t("common.save")) {
                        let t = ticker.trimmingCharacters(in: .whitespaces).uppercased()
                        guard !t.isEmpty, let value = Double(threshold) else { return }
                        let rule = AlertRule(
                            id: "\(t)-\(kind)-\(Int(Date().timeIntervalSince1970))",
                            ticker: t,
                            kind: kind,
                            threshold: value,
                            window: nil,
                            direction: direction,
                            enabled: true
                        )
                        Task {
                            await desk.addRule(rule)
                            dismiss()
                        }
                    }
                    .disabled(ticker.isEmpty || Double(threshold) == nil)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
