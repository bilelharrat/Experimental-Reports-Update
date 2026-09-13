import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @EnvironmentObject private var language: LanguageStore
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: 14) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 76, height: 76)
                    .background(
                        LinearGradient(
                            colors: [Color.accentColor, Color.accentColor.opacity(0.7)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        in: RoundedRectangle(cornerRadius: 18, style: .continuous)
                    )
                    .shadow(color: Color.accentColor.opacity(0.3), radius: 12, y: 6)

                Text("BSH Research")
                    .font(.title.weight(.bold))
                Text(language.t("login.hint"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .padding(.bottom, 28)
            .readableContentWidth(420)

            VStack(spacing: 12) {
                TextField(language.t("login.email"), text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(14)
                    .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                SecureField(language.t("login.password"), text: $password)
                    .textContentType(.password)
                    .padding(14)
                    .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                if let err = session.lastError {
                    Text(err)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button {
                    Task {
                        busy = true
                        await session.signIn(email: email, password: password)
                        busy = false
                    }
                } label: {
                    Group {
                        if busy {
                            ProgressView().tint(.white)
                        } else {
                            Text(language.t("login.submit"))
                                .font(.headline)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(busy || email.isEmpty || password.isEmpty)
            }
            .padding(.horizontal, 24)
            .readableContentWidth(420)

            Spacer()

            if AppConfig.bypassLogin {
                Button("Continue without signing in") {
                    session.enterWithoutSigningIn()
                }
                .font(.subheadline)
                .padding(.bottom, 20)
            }
        }
        .background(Color(.systemGroupedBackground))
    }
}
