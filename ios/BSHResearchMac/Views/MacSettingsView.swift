import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var serverURL: String = UserDefaults.standard.string(forKey: MacConfig.baseURLKey) ?? "http://127.0.0.1:8010"
    @State private var sessionToken: String = MacConfig.readToken() ?? ""
    @State private var requireLogin: Bool = UserDefaults.standard.bool(forKey: MacConfig.bypassLoginKey)
    @State private var testResult: String?
    @State private var testing = false

    var body: some View {
        Form {
            Section("Backend API Origin") {
                TextField("Server Base URL", text: $serverURL)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Save URL") {
                        MacConfig.saveBaseURL(serverURL)
                        testResult = "Saved base URL: \(serverURL)"
                    }

                    Button("Test Connection") {
                        Task { await testServer() }
                    }
                    .disabled(testing)

                    if testing {
                        ProgressView().controlSize(.small)
                    }
                }

                if let testResult {
                    Text(testResult)
                        .font(.caption)
                        .foregroundStyle(testResult.contains("Success") ? Color.green : Color.orange)
                }
            }

            Section("Authentication") {
                Toggle("Require User Authentication (Disable Dev Bypass)", isOn: $requireLogin)
                    .onChange(of: requireLogin) { _, val in
                        UserDefaults.standard.set(val, forKey: MacConfig.bypassLoginKey)
                    }

                SecureField("Session Bearer Token", text: $sessionToken)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Save Token") {
                        MacConfig.writeToken(sessionToken)
                    }
                    Button("Clear Token") {
                        MacConfig.clearToken()
                        sessionToken = ""
                    }
                }
            }

            Section("Cross-Platform Synchronization (/api/desk/prefs)") {
                LabeledContent("Pinned Watchlist Tickers") {
                    Text("\(store.pinnedTickers.count) symbols")
                        .font(.body.monospacedDigit())
                }

                LabeledContent("Portfolio Book Lots") {
                    Text("\(store.bookLots.count) positions")
                        .font(.body.monospacedDigit())
                }

                LabeledContent("Price Alert Rules") {
                    Text("\(store.alertRules.count) active")
                        .font(.body.monospacedDigit())
                }

                Button {
                    Task {
                        await store.refreshDeskPrefs()
                        await store.refreshMarket()
                    }
                } label: {
                    Label("Sync Now with Web & iPad Desk", systemImage: "arrow.triangle.2.circlepath")
                }
            }

            Section("Cache & Diagnostics") {
                Button("Reload All Intelligence Data") {
                    Task { await store.bootstrap() }
                }
            }
        }
        .formStyle(.grouped)
        .frame(minWidth: 460, minHeight: 400)
        .padding()
    }

    private func testServer() async {
        testing = true
        testResult = nil
        defer { testing = false }
        do {
            let cos = try await MacAPIClient.shared.listCompanies()
            testResult = "Success: Connected! Loaded \(cos.count) research enterprises."
        } catch {
            testResult = "Connection failed: \(error.localizedDescription)"
        }
    }
}
