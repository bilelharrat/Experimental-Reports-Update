import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: SessionStore
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var appearance: AppearanceStore
    @EnvironmentObject private var askPersona: AskPersonaStore
    @EnvironmentObject private var desk: DeskStore
    @EnvironmentObject private var welcomeTour: WelcomeTourStore
    @EnvironmentObject private var design: BSHDesignStore
    @State private var baseURL: String = AppGroupStore.loadBaseURL() ?? AppConfig.baseURL.absoluteString
    @State private var savedPulse = false
    @State private var syncing = false
    @State private var syncMessage: String?
    @State private var showAlerts = false

    var body: some View {
        NavigationStack {
            Form {
                Group {
                    Section {
                        HStack(spacing: 12) {
                            Image(systemName: "person.crop.circle.fill")
                                .font(.system(size: 40))
                                .symbolRenderingMode(.hierarchical)
                                .foregroundStyle(.tint)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(session.name ?? session.email ?? "—")
                                    .font(.headline)
                                Text(language.t(session.isSignedIn ? "settings.signed_in_as" : "settings.not_signed_in"))
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                Text("\(language.t("roles.label")): \(session.roleLabel)")
                                    .font(.caption)
                                    .foregroundStyle(session.isReadOnly ? .orange : .secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }

                    Section {
                        Button {
                            showAlerts = true
                        } label: {
                            HStack {
                                Label {
                                    Text(language.t("alerts.title"))
                                } icon: {
                                    SettingsIcon(symbol: "bell.fill", color: .red)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.footnote.weight(.semibold))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .buttonStyle(.plain)
                    } header: {
                        BSHSectionTitle(language.t("alerts.title"))
                    }

                    Section {
                        Toggle(isOn: Binding(
                            get: { appearance.darkModeEnabled },
                            set: { appearance.darkModeEnabled = $0 }
                        )) {
                            Label {
                                Text(language.t("settings.dark_mode"))
                            } icon: {
                                SettingsIcon(symbol: "moon.fill", color: .indigo)
                            }
                        }

                        Picker(selection: language.languageBinding) {
                            ForEach(AppLanguage.allCases) { lang in
                                Text(lang.label).tag(lang)
                            }
                        } label: {
                            Label {
                                Text(language.t("settings.language"))
                            } icon: {
                                SettingsIcon(symbol: "globe", color: .blue)
                            }
                        }
                        .pickerStyle(.navigationLink)

                        // Choosing a design (or Bureau's desk) rebuilds the app in it, and
                        // Settings with it, as choosing a language does.
                        Picker(selection: $design.design) {
                            ForEach(BSHDesignCards.order) { option in
                                Text(language.t("settings.design_\(option.rawValue)")).tag(option)
                            }
                        } label: {
                            Label {
                                Text(language.t("settings.design"))
                            } icon: {
                                SettingsIcon(symbol: "paintbrush.pointed.fill", color: .brown)
                            }
                        }
                        .pickerStyle(.menu)
                        .accessibilityIdentifier("settings-design")

                        // Only Bureau has a desk to color.
                        if design.design == .bureau {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Label {
                                        Text(language.t("settings.bureau_desk"))
                                    } icon: {
                                        SettingsIcon(symbol: "swatchpalette.fill", color: .gray)
                                    }
                                    Spacer()
                                    Text(language.t("settings.bureau_desk_\(design.bureauDesk.rawValue)"))
                                        .foregroundStyle(.secondary)
                                }
                                BSHBureauDeskPicker(
                                    selection: $design.bureauDesk,
                                    title: { language.t("settings.bureau_desk_\($0.rawValue)") },
                                    size: 24
                                )
                                .padding(.leading, 40)
                            }
                            .padding(.vertical, 2)
                            .accessibilityIdentifier("settings-bureau-desk")
                        }
                    } header: {
                        BSHSectionTitle(language.t("settings.appearance"))
                    } footer: {
                        Text(language.t("settings.design_help"))
                    }

                    Section {
                        Picker(selection: $askPersona.investor) {
                            ForEach(AskInvestor.allCases) { investor in
                                Text(investor.fullName).tag(investor)
                            }
                        } label: {
                            Label {
                                Text(language.t("settings.ask_persona"))
                            } icon: {
                                Image(askPersona.investor.imageName)
                                    .resizable()
                                    .scaledToFit()
                                    .frame(width: 28, height: 28)
                                    .clipShape(Circle())
                            }
                        }
                        .pickerStyle(.navigationLink)
                    } footer: {
                        Text(language.t("settings.ask_persona_footer"))
                    }

                    Section {
                        NavigationLink {
                            PositionsEditorView()
                        } label: {
                            Label {
                                Text(language.t("positions.title"))
                            } icon: {
                                SettingsIcon(symbol: "briefcase.fill", color: .teal)
                            }
                        }
                        Button {
                            // Settings is itself a sheet; let it close before the tour presents.
                            dismiss()
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
                                welcomeTour.replay()
                            }
                        } label: {
                            Label {
                                Text(language.t("settings.welcome_tour"))
                                    .foregroundStyle(.primary)
                            } icon: {
                                SettingsIcon(symbol: "sparkles", color: .blue)
                            }
                        }
                    } header: {
                        BSHSectionTitle(language.t("settings.desk"))
                    } footer: {
                        if session.isReadOnly {
                            Text(language.t("roles.read_only_hint"))
                        }
                    }

                    Section {
                        LabeledContent {
                            TextField("http://127.0.0.1:8010", text: $baseURL)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .keyboardType(.URL)
                                .multilineTextAlignment(.trailing)
                                .font(.footnote.monospaced())
                                .onSubmit { Task { await saveBaseURLAndSync() } }
                        } label: {
                            Label {
                                Text(language.t("settings.base_url"))
                            } icon: {
                                SettingsIcon(symbol: "server.rack", color: .green)
                            }
                        }
                        Button {
                            Task { await saveBaseURLAndSync() }
                        } label: {
                            HStack {
                                Text(language.t("common.save"))
                                if savedPulse {
                                    Spacer()
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.green)
                                        .transition(.scale.combined(with: .opacity))
                                }
                            }
                        }
                        .disabled(syncing)

                        Button {
                            Task { await syncNow() }
                        } label: {
                            HStack {
                                if syncing {
                                    ProgressView()
                                        .controlSize(.small)
                                }
                                Text(syncing ? "Syncing…" : "Sync with server")
                            }
                        }
                        .disabled(syncing)

                        if let syncMessage {
                            Text(syncMessage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } footer: {
                        Text(
                            """
                            Active: \(AppConfig.baseURL.absoluteString)
                            Use the same URL as the website (this Mac’s LAN IP + :8010). Save then Sync so companies, reports, and desk match the web.
                            """
                        )
                        .font(.caption.monospaced())
                    }

                    Section {
                        if session.isSignedIn {
                            Button(role: .destructive) {
                                Task { await session.signOut() }
                            } label: {
                                Text(language.t("settings.sign_out"))
                                    .frame(maxWidth: .infinity, alignment: .center)
                            }
                        } else {
                            // Open through the local bypass with nobody signed
                            // in: there is nothing to sign out of.
                            Button {
                                dismiss()
                                session.showSignIn()
                            } label: {
                                Text(language.t("login.title"))
                                    .frame(maxWidth: .infinity, alignment: .center)
                            }
                        }
                    }
                }
                .bshListRows()
            }
            .bshListSurface()
            .readableContentWidth()
            .compactRootChrome(title: language.t("tab.settings")) {
                Button(language.t("common.done")) {
                    dismiss()
                }
                .font(.body.weight(.semibold))
            }
            .sheet(isPresented: $showAlerts) {
                AlertsView()
                    .bshSheetChrome()
            }
        }
    }

    private func saveBaseURLAndSync() async {
        AppGroupStore.saveBaseURL(baseURL)
        withAnimation(.spring(duration: 0.3)) { savedPulse = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation { savedPulse = false }
        }
        await syncNow()
    }

    private func syncNow() async {
        syncing = true
        syncMessage = nil
        defer { syncing = false }
        await session.refreshMe()
        await desk.forceReload()
        await AppDataCache.shared.invalidateAndReload(lang: language.language)
        let count = AppDataCache.shared.companies.count
        syncMessage = count == 0
            ? "Synced — no companies on \(AppConfig.baseURL.host ?? "server"). Check the URL."
            : "Synced — \(count) companies from \(AppConfig.baseURL.host ?? "server")."
    }
}

/// The rounded colored icon tile used by the system Settings app.
struct SettingsIcon: View {
    let symbol: String
    let color: Color

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: 28, height: 28)
            .background(color, in: RoundedRectangle(cornerRadius: 6.5, style: .continuous))
    }
}
