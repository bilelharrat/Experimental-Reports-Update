import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @EnvironmentObject private var language: LanguageStore
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(language.t("login.email"), text: $email)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField(language.t("login.password"), text: $password)
                        .textContentType(.password)
                } footer: {
                    Text(language.t("login.hint"))
                }

                if let err = session.lastError {
                    Section {
                        Text(err).foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        Task {
                            busy = true
                            await session.signIn(email: email, password: password)
                            busy = false
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if busy { ProgressView() }
                            Text(language.t("login.submit"))
                            Spacer()
                        }
                    }
                    .disabled(busy || email.isEmpty || password.isEmpty)

                    if AppConfig.bypassLogin {
                        Button("Continue without signing in") {
                            session.enterWithoutSigningIn()
                        }
                    }
                }
            }
            .navigationTitle(language.t("login.title"))
        }
    }
}
