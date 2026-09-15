import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var store: MacAppStore

    @State private var serverURL: String = MacConfig.baseURL.absoluteString
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
                    if store.needsPasswordReset {
                        Label("Password reset required — change it in the web portal.", systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                    LabeledContent("Permissions") {
                        Text(session.permissions.isEmpty ? "read-only" : session.permissions.sorted().joined(separator: ", "))
                            .font(.caption.monospacedDigit())
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

            Section("Thesis") {
                MacThesisEditor()
            }

            Section("Server") {
                TextField("Base URL", text: $serverURL)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Save") {
                        saveServer()
                    }

                    Button("Test connection") {
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
                Toggle("Require sign-in in this app", isOn: $requireLogin)
                    .onChange(of: requireLogin) { _, val in
                        UserDefaults.standard.set(val, forKey: MacConfig.bypassLoginKey)
                        Task {
                            if val {
                                await store.refreshSession()
                                if store.session == nil || store.session?.isAnonDev == true { store.showLoginSheet = true }
                            } else {
                                await store.bootstrap()
                                if store.session != nil { store.showLoginSheet = false }
                            }
                        }
                    }
                Text("Hides the local dev identity behind the sign-in sheet. The server still accepts unauthenticated requests while BSH_ALLOW_ANON_DEV=1.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                SecureField("Service token (read-only, for tooling)", text: $serviceToken)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Use token") {
                        MacConfig.writeToken(serviceToken)
                        serviceToken = ""
                        Task { await store.bootstrap() }
                    }
                    .disabled(serviceToken.isEmpty)
                    Button("Forget stored token") {
                        MacConfig.clearToken()
                        Task { await store.signOut() }
                    }
                }
                Text("Sessions are stored in the macOS Keychain. Sign in above for a personal session; the service token is only for tooling.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Desk sync · web, iPad and Mac") {
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
                    Label("Sync now", systemImage: "arrow.triangle.2.circlepath")
                }
            }

            Section("MCP connector") {
                Text("Expose the firm's memory — memos, decisions, calls, transcripts, portfolio, signal scores — to any MCP client. Read-only.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("uv run python scripts/bsh_mcp.py")
                    .font(.caption.monospacedDigit())
                    .textSelection(.enabled)
                Button("Copy Claude Desktop config") {
                    let cfg = """
                    {"mcpServers": {"bsh-research": {"command": "uv", "args": ["run", "--directory", "/PATH/TO/bsh-research-center", "python", "scripts/bsh_mcp.py"]}}}
                    """
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(cfg, forType: .string)
                }
                .controlSize(.small)
            }

            Section("Data") {
                Button("Reload everything") {
                    Task { await store.bootstrap() }
                }
            }
        }
        .formStyle(.grouped)
        .frame(minWidth: 480, minHeight: 460)
        .padding()
    }

    private func saveServer() {
        guard let url = MacConfig.normalizedBaseURL(serverURL) else {
            testResult = "Invalid base URL: include a host, e.g. http://192.168.1.5:8010"
            return
        }
        let target = url.absoluteString
        testResult = "Saved base URL: \(target)"
        Task {
            await store.switchServer(to: target)
            serverURL = MacConfig.baseURL.absoluteString
        }
    }

    private func testServer() async {
        testing = true
        testResult = nil
        defer { testing = false }
        guard let base = MacConfig.normalizedBaseURL(serverURL) else {
            let stored = MacConfig.storedBaseURLError.map { " \($0)" } ?? ""
            testResult = "Connection failed: enter a full http(s) URL (current: \(MacConfig.baseURL.absoluteString))\(stored)"
            return
        }
        let saved = base.absoluteString == MacConfig.baseURL.absoluteString
        let suffix = saved ? "" : " (not saved yet; current: \(MacConfig.baseURL.absoluteString))"
        var req = URLRequest(url: base.appendingPathComponent("api").appendingPathComponent("health"), timeoutInterval: 5)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            switch status {
            case 200..<300:
                testResult = "Success: \(base.absoluteString) is reachable\(suffix)"
            case 401:
                testResult = "Reachable, but \(base.absoluteString) requires sign-in\(suffix)"
            default:
                testResult = "Connection failed: HTTP \(status) from \(base.absoluteString)\(suffix)"
            }
        } catch {
            testResult = "Connection failed: \(error.localizedDescription)\(suffix)"
        }
    }
}
