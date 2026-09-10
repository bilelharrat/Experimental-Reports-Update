import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var session: SessionStore
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var appearance: AppearanceStore
    @State private var baseURL: String = UserDefaults.standard.string(forKey: "bsh.baseURL") ?? AppConfig.baseURL.absoluteString

    var body: some View {
        NavigationStack {
            Form {
                Section(language.t("settings.signed_in_as")) {
                    Text(session.name ?? session.email ?? "—")
                }

                Section(language.t("settings.appearance")) {
                    Toggle(language.t("settings.dark_mode"), isOn: Binding(
                        get: { appearance.darkModeEnabled },
                        set: { appearance.darkModeEnabled = $0 }
                    ))
                }

                Section(language.t("settings.language")) {
                    Picker(language.t("settings.language"), selection: $language.language) {
                        ForEach(AppLanguage.allCases) { lang in
                            Text(lang.label).tag(lang)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section(language.t("settings.base_url")) {
                    TextField("http://127.0.0.1:8010", text: $baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    Button("Save") {
                        UserDefaults.standard.set(baseURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "bsh.baseURL")
                    }
                }

                Section {
                    Button(role: .destructive) {
                        Task { await session.signOut() }
                    } label: {
                        Text(language.t("settings.sign_out"))
                    }
                }
            }
            .compactRootChrome(title: language.t("tab.settings"))
        }
    }
}
