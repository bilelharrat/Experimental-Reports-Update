import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var serverURL: String = UserDefaults.standard.string(forKey: MacConfig.baseURLKey) ?? MacConfig.baseURL.absoluteString
    @State private var serviceToken: String = ""
    @State private var requireLogin: Bool = UserDefaults.standard.bool(forKey: MacConfig.bypassLoginKey)
    @State private var testResult: String?
    @State private var testing = false
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        Form {
            Section("Account") {
                if let session = store.session {
                    LabeledContent("Signed in as") {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(session.displayName).font(.body.weight(.semibold))
                            if let mail = session.email, mail != session.displayName {
                                Text(mail).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    LabeledContent("Role", value: session.roleLabel + (session.isAnonDev ? " (local dev bypass)" : ""))
                    LabeledContent("Permissions") {
                        Text(session.permissions.isEmpty ? "read-only" : session.permissions.sorted().joined(separator: ", "))
                            .font(.caption.monospaced())
                            .multilineTextAlignment(.trailing)
                    }
                    HStack {
                        if session.isAnonDev {
                            Button("Sign In…") { store.showLoginSheet = true }
                        } else {
                            Button("Sign Out", role: .destructive) {
                                Task { await store.signOut() }
                            }
                        }
                    }
                } else {
                    TextField("Email", text: $email)
                        .textFieldStyle(.roundedBorder)
                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)
                    HStack {
                        Button("Sign In") {
                            Task { await store.signIn(email: email, password: password) }
                        }
                        .disabled(store.signingIn || email.isEmpty || password.isEmpty)
                        if store.signingIn {
                            ProgressView().controlSize(.small)
                        }
                    }
                    if let err = store.authError {
                        Text(err).font(.caption).foregroundStyle(.red)
                    }
                }
            }

            Section("Backend API Origin") {
                TextField("Server Base URL", text: $serverURL)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Save URL") {
                        MacConfig.saveBaseURL(serverURL)
                        testResult = "Saved base URL: \(serverURL)"
                        Task { await store.bootstrap() }
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

            Section("Advanced Authentication") {
                Toggle("Require User Authentication (Disable Dev Bypass)", isOn: $requireLogin)
                    .onChange(of: requireLogin) { _, val in
                        UserDefaults.standard.set(val, forKey: MacConfig.bypassLoginKey)
                        if val && store.session?.isAnonDev == true {
                            store.showLoginSheet = true
                        }
                    }

                SecureField("Service Bearer Token (read-only machine credential)", text: $serviceToken)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Use Token") {
                        MacConfig.writeToken(serviceToken)
                        serviceToken = ""
                        Task { await store.bootstrap() }
                    }
                    .disabled(serviceToken.isEmpty)
                    Button("Forget Stored Token") {
                        MacConfig.clearToken()
                        Task { await store.signOut() }
                    }
                }
                Text("Sessions are stored in the macOS Keychain. Sign in above for a personal session; the service token is only for tooling.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
                    Text("\(store.alertRules.filter(\.enabled).count) active of \(store.alertRules.count)")
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
        .frame(minWidth: 480, minHeight: 460)
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
